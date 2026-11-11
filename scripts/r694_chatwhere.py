"""R694 · 问一句之后，问题与答案在 DOM 的哪儿（枚数、路径、是否可见）。"""
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

DUMP = """
(needle) => {
  const paths = [];
  const walk = (el, prefix) => {
    for (const child of el.children) {
      const label = prefix + '>' + child.tagName.toLowerCase() +
        (child.className ? '.' + String(child.className).split(' ')[0] : '');
      if (child.children.length === 0 && (child.textContent || '').indexOf(needle) >= 0) {
        paths.push({path: label, text: child.textContent.trim().slice(0, 120)});
      }
      if (child.children.length && child.children.length < 200) walk(child, label);
    }
  };
  walk(document.body, 'body');
  return {
    chat_messages_count: document.querySelectorAll('.chat-messages').length,
    msg_row_count: document.querySelectorAll('.msg-row').length,
    bubble_count: document.querySelectorAll('.msg-bubble-wrap').length,
    session_rows: Array.from(document.querySelectorAll('.session-item, [data-testid]'))
      .map(e => e.getAttribute('data-testid')).filter(v => v && v.indexOf('session') >= 0),
    body_has_question: (document.body.innerText || '').indexOf(needle) >= 0,
    question_leaf_paths: paths.slice(0, 8),
    vue_devtools_hook: typeof window.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined',
    app_el_keys: Object.keys(document.querySelector('#app') || {}).slice(0, 8),
  };
}
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
        page.click("[data-testid=chat-input]")
        page.keyboard.type(args.question, delay=18)
        page.click("[data-testid=chat-send]")
        deadline = time.time() + args.wait_s
        while time.time() < deadline:
            time.sleep(2.0)
        print(json.dumps(page.evaluate(DUMP, args.question), ensure_ascii=False, indent=1))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
