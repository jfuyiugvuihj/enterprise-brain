"""R694 · 复原与交还：把走查留下的那枚上传档删回基线，并现取交还读数。

三件事，全部只走产品自己的门：
1. 环 3 那枚夹具用屏上两击删除（`document-delete-one`）删掉，计数牌与 API 枚数各取一次；
2. catalog 面复跑一次，看那一行是否还可查回（查回＝删没删干净，是读数不是判断）；
3. 交还机器那一刻现取 `docker ps` 与 `docker ps --all`，把差集与逐枚健康读数写进账本根 ``revert``。

不删容器、不动卷、不碰宿主 ``%TEMP%`` 里非本单的目录（规矩⑫）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r694_common import (  # noqa: E402
    Ledger,
    env_key,
    epoch,
    register_shot,
    seconds_since,
    stamp,
    wait_for,
)
from r694_walkthrough import (  # noqa: E402
    API_PREFIX,
    PRIMARY_PASS_KEY,
    PRIMARY_USER_KEY,
)

STACK = ("enterprise-brain-backend-1", "enterprise-brain-worker-1", "enterprise-brain-scheduler-1",
         "enterprise-brain-frontend-1", "enterprise-brain-postgres-1", "enterprise-brain-redis-1",
         "enterprise-brain-ollama-1")

COUNT_JS = """() => {
  const b = document.querySelector('[data-testid=documents-panel] .panel-hd-left .badge');
  return b ? Number(b.textContent.trim()) : null;
}"""

CATALOG_JS = """async (arg) => {
  const token = localStorage.getItem('eb_token') || '';
  const r = await fetch(arg.url, { headers: { Authorization: 'Bearer ' + token } });
  const body = await r.json().catch(() => null);
  const rows = body ? (body.catalog || body.documents || body.items || []) : [];
  const hits = Array.isArray(rows) ? rows.filter((x) => JSON.stringify(x).indexOf(arg.name) >= 0) : [];
  return { status: r.status, rows: Array.isArray(rows) ? rows.length : null, hits: hits.length,
           hit_fields: hits.length ? Object.keys(hits[0]).sort() : [] };
}"""


def docker_status_rows(all_containers: bool) -> list[dict[str, str]]:
    cmd = ["docker", "ps"] + (["--all"] if all_containers else []) + [
        "--format", "{{.Names}}|{{.Status}}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    rows: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines():
        if "|" in line:
            name, status = line.split("|", 1)
            rows.append({"name": name.strip(), "status": status.strip()})
    return rows


class Revert:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out / "ledger.json")
        self.pw = None
        self.browser = None
        self.context = None
        self.page: Page | None = None

    def __enter__(self) -> "Revert":
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            if self.context:
                self.context.close()
        finally:
            if self.browser:
                self.browser.close()
            if self.pw:
                self.pw.stop()

    # ------------------------------------------------------------------ 页面腿
    def login(self) -> Page:
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        page = self.context.new_page()
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=25000)
        page.fill("[data-testid=login-username]", env_key(self.args.env_file, PRIMARY_USER_KEY))
        page.fill("[data-testid=login-password]", env_key(self.args.env_file, PRIMARY_PASS_KEY))
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        self.page = page
        return page

    def open_docs(self) -> None:
        page = self.page
        assert page is not None
        page.click("[data-testid=nav-feed]")
        page.wait_for_selector("[data-testid=documents-panel]", timeout=20000)
        page.wait_for_timeout(800)

    def counts(self) -> dict[str, Any]:
        page = self.page
        assert page is not None
        api = page.evaluate("""async (prefix) => {
            const token = localStorage.getItem('eb_token') || '';
            const r = await fetch(prefix + '/documents', { headers: { Authorization: 'Bearer ' + token } });
            const b = await r.json().catch(() => null);
            const list = b ? (b.documents || b.items || []) : [];
            return { status: r.status, count: Array.isArray(list) ? list.length : null };
        }""", API_PREFIX)
        return {"tile": page.evaluate(COUNT_JS),
                "rows_rendered": page.locator("[data-testid=doc-row]").count(),
                "api_status": api.get("status"), "api_document_count": api.get("count")}

    def catalog_check(self, name: str) -> dict[str, Any]:
        page = self.page
        assert page is not None
        url = page.evaluate("() => window.location.origin") + API_PREFIX + "/documents/catalog"
        return page.evaluate(CATALOG_JS, {"url": url, "name": name})

    # -------------------------------------------------------------------- 主流程
    def run(self) -> dict[str, Any]:
        name = Path(self.args.fixture).name
        ring3 = next((r for r in self.ledger.data.get("rings", []) if r.get("ring") == 3), {})
        baseline = ((ring3.get("readings") or {}).get("counts_before") or {}).get("tile")
        self.login()
        self.open_docs()
        before = self.counts()
        row = self.page.locator("[data-testid=doc-row]").filter(has_text=name)
        present_before = row.count()
        shot_before = register_shot(self.page, self.out, "r694-revert-before-delete.png")
        delete_wait_started = epoch()
        deleted = None
        if present_before:
            self.page.click("[data-testid=document-delete-one]")
            armed = wait_for(
                lambda: self.page.locator("[data-testid=document-delete-one-cancel]").count() > 0,
                15.0, poll_s=0.2)
            confirm = self.page.locator("[data-testid=document-delete-one]")
            if armed and confirm.count():
                confirm.first.click()
                deleted = wait_for(
                    lambda: self.page.locator("[data-testid=doc-row]").filter(has_text=name).count() == 0,
                    90.0, poll_s=0.5)
        self.open_docs()
        after = self.counts()
        row_after = self.page.locator("[data-testid=doc-row]").filter(has_text=name).count()
        shot_after = register_shot(self.page, self.out, "r694-revert-after-delete.png")
        catalog = self.catalog_check(name)
        up = docker_status_rows(all_containers=False)
        everything = docker_status_rows(all_containers=True)
        names_up = [r["name"] for r in up]
        r694_left = [r["name"] for r in everything if r["name"].startswith("r694-")]
        docker = {
            "up_count": len(up),
            "up_names": sorted(names_up),
            "statuses": ["%s %s" % (r["name"], r["status"]) for r in up
                         if r["name"] in STACK],
            "ps_minus_ps_a": sorted(r["name"] for r in everything if r["name"] not in names_up),
            "r694_leftover": sorted(r694_left),
            "taken_at": stamp(),
        }
        side_effects = [
            "语料：环 3 上传 `%s`（起手基线 %s 枚，删后现取 %s 枚，屏上计数牌 %s→%s）" % (
                name, baseline, after.get("api_document_count"),
                (before or {}).get("tile"), (after or {}).get("tile")),
            "catalog 面里那枚夹具还可查回：%s 枚命中（HTTP %s）" % (
                catalog.get("hits"), catalog.get("status")),
            "chat 会话：本单在跑期间新建若干轮问答（屏上会话列表 `new-session` 逐轮另开），"
            "会话与审计事件留在库里，未删——删除动作不在本单写域",
            "待批：环 9 驳回掉本轮那一枚（读数在 rings[9].rejection）；"
            "起手时在册那枚 `req-9267` 由别笔走查挂起，最迟 2026-10-07 过期，本单未替它决策",
            "`static/exports/`：本单跑出的 PDF 逐枚见 side_effect_exports 那一格",
        ]
        entry = {
            "fixture": name,
            "baseline_tile": baseline,
            "counts_before_revert": before,
            "counts_after_revert": after,
            "row_present_before": present_before,
            "row_present_after": row_after,
            "delete_armed": bool(present_before) and "armed" in locals(),
            "deleted_from_screen": bool(deleted),
            "delete_wait_s": seconds_since(delete_wait_started),
            "catalog_still_lists_fixture": catalog,
            "shots": [shot_before, shot_after],
            "side_effects": side_effects,
            "docker": docker,
            "taken_at": stamp(),
        }
        self.ledger.set_root("revert", entry)
        return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R694 复原：删回基线并现取交还读数")
    parser.add_argument("--base-url", default="http://localhost/")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    parser.add_argument("--fixture", default="docs/testing/rehearse-run6-summary.txt")
    args = parser.parse_args(argv)
    fixture = Path(args.fixture)
    if not fixture.is_absolute():
        fixture = ROOT / args.fixture
    args.fixture = str(fixture)
    with Revert(args) as run:
        entry = run.run()
    print(json.dumps({
        "fixture": entry["fixture"],
        "tile": "%s→%s" % (entry["counts_before_revert"]["tile"],
                          entry["counts_after_revert"]["tile"]),
        "api_count": entry["counts_after_revert"]["api_document_count"],
        "row_present_after": entry["row_present_after"],
        "catalog_hits": entry["catalog_still_lists_fixture"]["hits"],
        "up_count": entry["docker"]["up_count"],
        "r694_leftover": entry["docker"]["r694_leftover"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())