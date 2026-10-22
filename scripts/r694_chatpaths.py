"""R694 · 问一句之后的三种落点各读一次：就地／点会话／刷新。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from playwright.sync_api import sync_playwright  # noqa: E402

from r694_common import env_key  # noqa: E402

STATE = """
() => ({
  msg_row: document.querySelectorAll('.msg-row').length,
  bubble: document.querySelectorAll('.msg-bubble-wrap').length,
  content_chars: Array.from(document.querySelectorAll('.msg-content')).map(e => e.innerText.trim().length),
  welcome: document.querySelectorAll('.welcome-screen').length,
  comments_in_box: (document.querySelector('.chat-messages') || {innerHTML: ''}).innerHTML.split('<!---->').length - 1,
  session_titles: Array.from(document.querySelectorAll('.session-title')).slice(0, 4).map(e => e.textContent.trim()),
  url: location.href,
})
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--question", default="费用报销需要经过哪些审批环节？")
    ap.add_argument("--wait-s", type=float, default=25.0)
    args = ap.parse_args()
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
        print("OPEN " + json.dumps(page.evaluate(STATE), ensure_ascii=False))
        page.click("[data-testid=chat-input]")
        page.keyboard.type(args.question, delay=18)
        page.click("[data-testid=chat-send]")
        deadline = time.time() + args.wait_s
        while time.time() < deadline:
            time.sleep(2.0)
        print("JUST_ASKED " + json.dumps(page.evaluate(STATE), ensure_ascii=False))
        page.click(".session-item")
        page.wait_for_timeout(2500)
        print("AFTER_CLICK_SESSION " + json.dumps(page.evaluate(STATE), ensure_ascii=False))
        page.reload(wait_until="load")
        page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
        page.wait_for_timeout(2500)
        print("AFTER_RELOAD " + json.dumps(page.evaluate(STATE), ensure_ascii=False))
        page.click("[data-testid=nav-overview]")
        page.wait_for_timeout(1500)
        page.click("[data-testid=nav-chat]")
        page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
        page.wait_for_timeout(2000)
        print("AFTER_SCREEN_SWITCH " + json.dumps(page.evaluate(STATE), ensure_ascii=False))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
