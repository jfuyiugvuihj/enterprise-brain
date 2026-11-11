"""R694 · 会话区结构取证：问一句之后，把 .chat-messages 那一截 DOM 原样交回来。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from playwright.sync_api import sync_playwright  # noqa: E402

from r694_common import env_key  # noqa: E402

DUMP = """
() => {
  const box = document.querySelector('.chat-messages');
  const kids = box ? Array.from(box.children).map(e => ({
    tag: e.tagName.toLowerCase(),
    cls: String(e.className),
    testid: e.getAttribute('data-testid'),
    display: getComputedStyle(e).display,
    childCount: e.children.length,
    text: (e.innerText || '').slice(0, 160),
  })) : null;
  const rows = Array.from(document.querySelectorAll('[data-turn]')).map(e => ({
    turn: e.getAttribute('data-turn'), cls: String(e.className), text: (e.innerText || '').slice(0, 120),
  }));
  return {
    chat_messages_present: !!box,
    chat_messages_child_count: box ? box.children.length : null,
    chat_messages_html_head: box ? box.innerHTML.slice(0, 900) : null,
    children: kids,
    data_turn_rows: rows,
    panel_html_len: (document.querySelector('[data-testid=chat-panel]') || {innerHTML: ''}).innerHTML.length,
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--question", default="费用报销需要经过哪些审批环节？")
    ap.add_argument("--wait-s", type=float, default=40.0)
    args = ap.parse_args()
    import time

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        events: list[str] = []
        page.on("console", lambda m: events.append("console.%s %s" % (m.type, m.text[:400])))
        page.on("pageerror", lambda e: events.append("pageerror %s" % str(e)[:400]))
        page.on("requestfailed", lambda r: events.append("requestfailed %s" % r.url[:200]))
        page.goto(args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=20000)
        page.fill("[data-testid=login-username]", env_key(args.env_file, "AUTH_USERNAME"))
        page.fill("[data-testid=login-password]", env_key(args.env_file, "DEMO_ADMIN_PASSWORD"))
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.click("[data-testid=nav-chat]")
        page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
        page.wait_for_timeout(1000)
        print("BEFORE " + json.dumps(page.evaluate(DUMP), ensure_ascii=False))
        page.click("[data-testid=chat-input]")
        page.keyboard.type(args.question, delay=18)
        page.click("[data-testid=chat-send]")
        deadline = time.time() + args.wait_s
        last = ""
        while time.time() < deadline:
            time.sleep(2.0)
            blob = json.dumps(page.evaluate(DUMP), ensure_ascii=False)
            if blob != last:
                print("AFTER " + blob[:2600])
                last = blob
        print("CONSOLE " + json.dumps(events[:40], ensure_ascii=False))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
