"""R694 · 断网自证：两态各刷一次登录页与工作台，外部域名请求逐枚点名。

两条腿都跑，因为「DevTools 切 Offline」在 Chromium 里是 ``Network.emulateNetworkConditions``，
它把**本站原点的请求也一起掐了**——那种情况下页面出不来是浏览器的错误页，不是产品的白屏。
所以本件交回两枚读数：

- ``hard_offline``：``context.set_offline(True)`` 之后刷登录页与工作台，取回 Chromium
  自己那枚错误页证据（``chrome_error_page`` 与失败请求名册）；
- ``external_blocked``：只掐外部域名（``context.route`` 对非本站主机 ``abort``），
  本站照常服务——判据「不许白屏／外部域名请求 0 条」在这一条腿上量。

只读产品码：不建容器，不改 env，不动 ``frontend/**``。凭据按 env 键名取，值不落纸。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from playwright.sync_api import Route, sync_playwright  # noqa: E402

from r694_common import (  # noqa: E402
    Ledger,
    env_key,
    epoch,
    is_external,
    register_shot,
    seconds_since,
    stamp,
)
from r694_walkthrough import (  # noqa: E402
    PRIMARY_PASS_KEY,
    PRIMARY_USER_KEY,
    SSE_TAP,
)

#: 白屏判据：屏上有内容 = body 里节点数与非空白字符数都过线，且本站原点请求成功。
SCREEN_JS = r"""
() => {
  const txt = (document.body ? document.body.innerText : '') || '';
  return {
    dom_nodes: document.querySelectorAll('body *').length,
    body_chars: txt.replace(/\s+/g, '').length,
    login_page: document.querySelectorAll('[data-testid=login-page]').length,
    sidebar: document.querySelectorAll('[data-testid=sidebar]').length,
    app_bg_layers: document.querySelectorAll('.app-bg > *').length,
    document_title: document.title,
    chrome_error_page: /ERR_[A-Z_]+|无法访问此网站|访问此网站|This site can/.test(txt),
    first_lines: txt.split(String.fromCharCode(10)).map((l) => l.trim()).filter(Boolean).slice(0, 4),
  };
}
"""


class Offline:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out / "ledger.json")
        self.pw = None
        self.browser = None
        self.context: Any = None

    def __enter__(self) -> "Offline":
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.pw:
            self.pw.stop()

    # ------------------------------------------------------------------ 取页腿
    def new_page(self) -> Any:
        context = self.browser.new_context(viewport={"width": self.args.width,
                                                     "height": self.args.height})
        context.add_init_script(SSE_TAP)
        page = context.new_page()
        seen: list[str] = []
        page.on("request", lambda r: seen.append(r.url))
        page.on("requestfailed", lambda r: seen.append("FAILED " + r.url))
        page.context.__setattr__("r694_requests", seen)
        self.context = context
        return page

    def login(self, page: Any) -> None:
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=25000)
        page.fill("[data-testid=login-username]",
                  env_key(self.args.env_file, PRIMARY_USER_KEY))
        page.fill("[data-testid=login-password]",
                  env_key(self.args.env_file, PRIMARY_PASS_KEY))
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.wait_for_timeout(800)

    def read_leg(self, page: Any, mark: int) -> dict[str, Any]:
        """取回这一刻的屏上读数 + 这一段时间里的请求名册（按 mark 切片）。"""
        urls = list(page.context.r694_requests)[mark:]
        external = [u for u in urls if is_external(u)]
        failed = [u[len("FAILED "):] for u in urls if u.startswith("FAILED ")]
        return {"screen": self.screen_reading(page),
                "requests_in_window": len(urls),
                "requests_external": external,
                "requests_external_count": len(external),
                "requests_failed": failed[:20],
                "requests_failed_count": len(failed),
                "document_host": urlparse(page.url).hostname,
                "page_url": page.url}

    @staticmethod
    def screen_reading(page: Any) -> dict[str, Any]:
        """断网那一腿屏上是 Chromium 自己的错误页，执行上下文说没就没：取不到就当成一枚读数记。"""
        last_error: str | None = None
        for _attempt in range(3):
            try:
                return page.evaluate(SCREEN_JS)
            except Exception as exc:  # noqa: BLE001 - 上下文销毁是这条腿的正常形状
                last_error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:140]
                try:
                    page.wait_for_load_state("load", timeout=4000)
                except Exception:  # noqa: BLE001 - 等不到也算等过
                    pass
        return {"dom_nodes": 0, "body_chars": 0, "login_page": 0, "sidebar": 0,
                "app_bg_layers": 0, "document_title": urlparse(page.url).hostname or "",
                "chrome_error_page": True, "first_lines": [],
                "evaluate_error": last_error}

    def shot(self, page: Any, name: str) -> dict[str, Any]:
        return register_shot(page, self.out, name)

    # ---------------------------------------------------------------- 两条腿
    def hard_offline(self) -> dict[str, Any]:
        page = self.new_page()
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=25000)
        online_mark = len(page.context.r694_requests)
        entry: dict[str, Any] = {"method": "hard_offline", "at": stamp()}
        # 刷登录页：先切 Offline，再刷
        page.context.set_offline(True)
        started = epoch()
        try:
            page.reload(wait_until="load", timeout=30000)
            nav_error = None
        except Exception as exc:  # noqa: BLE001 - 导航本身就是要记的读数
            nav_error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:120]
        login_leg = self.read_leg(page, online_mark)
        login_leg["nav_exception"] = nav_error
        login_leg["reload_s"] = seconds_since(started)
        login_leg["shot"] = self.shot(page, "r694-offline-login-1440.png")
        entry["login_page"] = login_leg
        # 断网态下刷不出登录页，就先在线登录，再切 Offline 刷工作台
        page.context.set_offline(False)
        page.reload(wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=25000)
        self.login(page)
        mark = len(page.context.r694_requests)
        page.context.set_offline(True)
        started = epoch()
        try:
            page.reload(wait_until="load", timeout=30000)
            nav_error = None
        except Exception as exc:  # noqa: BLE001
            nav_error = type(exc).__name__ + ": " + str(exc).splitlines()[0][:120]
        work_leg = self.read_leg(page, mark)
        work_leg["nav_exception"] = nav_error
        work_leg["reload_s"] = seconds_since(started)
        work_leg["shot"] = self.shot(page, "r694-offline-workbench-1440.png")
        entry["workbench"] = work_leg
        page.context.set_offline(False)
        entry["white_screen"] = bool(
            login_leg["screen"]["dom_nodes"] < 20 or work_leg["screen"]["dom_nodes"] < 20)
        entry["external_requests"] = (login_leg["requests_external_count"]
                                      + work_leg["requests_external_count"])
        return entry

    def external_blocked(self) -> dict[str, Any]:
        page = self.new_page()
        aborted: list[str] = []

        def handler(route: Route) -> None:
            url = route.request.url
            if is_external(url):
                aborted.append(url)
                route.abort()
            else:
                route.continue_()

        page.context.route("**/*", handler)
        entry: dict[str, Any] = {"method": "external_blocked", "at": stamp()}
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=25000)
        page.wait_for_timeout(1200)
        login_leg = self.read_leg(page, 0)
        login_leg["shot"] = self.shot(page, "r694-offline-blocked-login-1440.png")
        entry["login_page"] = login_leg
        self.login(page)
        mark = len(page.context.r694_requests)
        page.reload(wait_until="load")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.wait_for_timeout(1500)
        work_leg = self.read_leg(page, mark)
        work_leg["shot"] = self.shot(page, "r694-offline-blocked-workbench-1440.png")
        entry["workbench"] = work_leg
        entry["aborted_external_urls"] = aborted[:20]
        entry["aborted_external_count"] = len(aborted)
        entry["external_requests"] = (login_leg["requests_external_count"]
                                      + work_leg["requests_external_count"])
        entry["white_screen"] = bool(
            login_leg["screen"]["dom_nodes"] < 20 or work_leg["screen"]["dom_nodes"] < 20)
        entry["login_reached"] = bool(login_leg["screen"]["login_page"]
                                      and work_leg["screen"]["sidebar"])
        page.context.unroute("**/*", handler)
        return entry

    def run(self) -> dict[str, Any]:
        legs = {"hard_offline": self.hard_offline(),
                "external_blocked": self.external_blocked()}
        blocked = legs["external_blocked"]
        verdict = "达" if (blocked["login_reached"] and not blocked["white_screen"]
                          and blocked["external_requests"] == 0
                          and legs["hard_offline"]["external_requests"] == 0) else "未达"
        out = {"verdict": verdict, "legs": legs, "at": stamp(),
               "note": ("hard_offline 那一腿把本站原点的文档请求也掐了，屏上是 Chromium 自己的错误页；"
                        "读数记在 legs.hard_offline.*.screen 与 requests_failed。"
                        "判据按 external_blocked 那一腿量：只掐外部域名，本站照常服务。")}
        self.ledger.set_root("offline", out)
        return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R694 断网自证（两态各刷登录页与工作台）")
    parser.add_argument("--base-url", default="http://localhost/")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with Offline(args) as run:
        out = run.run()
    print(json.dumps({"verdict": out["verdict"],
                      "hard_external": out["legs"]["hard_offline"]["external_requests"],
                      "blocked_external": out["legs"]["external_blocked"]["external_requests"],
                      "white_screen_blocked": out["legs"]["external_blocked"]["white_screen"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())