"""R694 · 把「问一句」整块面板的 DOM 原样落进临时目录，供逐字看。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from playwright.sync_api import sync_playwright  # noqa: E402

from r694_common import env_key  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--question", default="费用报销需要经过哪些审批环节？")
    ap.add_argument("--wait-s", type=float, default=25.0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out_dir = Path(args.out or (Path(os.environ.get("TEMP") or ".") / "evalrun" / "r694"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=20000)
        page.fill("[data-testid=login-username]", env_key(args.env_file, "AUTH_USERNAME"))
        page.fill("[data-testid=login-password]", env_key(args.env_file, "DEMO_ADMIN_PASSWORD"))
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.click("[data-testid=nav-chat]")
        page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
        page.wait_for_timeout(1000)
        page.click("[data-testid=chat-input]")
        page.keyboard.type(args.question, delay=18)
        page.click("[data-testid=chat-send]")
        deadline = time.time() + args.wait_s
        while time.time() < deadline:
            time.sleep(2.0)
        html = page.evaluate("() => document.querySelector('[data-testid=chat-panel]').outerHTML")
        target = out_dir / "chat-panel-after-ask.html"
        target.write_text(html, encoding="utf-8")
        print(json.dumps({"file": str(target), "bytes": target.stat().st_size,
                          "msg_row": page.locator(".msg-row").count(),
                          "comments": html.count("<!---->")}, ensure_ascii=False))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
