"""R694 · 把 .chat-messages 的 vnode 树与 DOM 树并排读一次（谁在骗人）。"""
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
() => {
  const box = document.querySelector('.chat-messages');
  if (!box) return {error: 'no .chat-messages'};
  const shape = (vn, depth) => {
    if (!vn) return null;
    if (Array.isArray(vn)) return vn.map(v => shape(v, depth + 1));
    const t = vn.type;
    let name;
    if (t === null) name = 'static-comment-or-text';
    else if (typeof t === 'symbol') name = String(t.description || t).replace('Symbol(', '').replace(')', '');
    else if (typeof t === 'function') name = 'component:' + (t.__name || t.name || 'anon');
    else name = 'el:' + t;
    const out = {name, keys: vn.props ? Object.keys(vn.props).slice(0, 6) : []};
    if (typeof vn.children === 'string') out.text = vn.children.slice(0, 60);
    else if (Array.isArray(vn.children)) out.children = vn.children.map(c => shape(c, depth + 1));
    else if (vn.component) out.component = shape(vn.component.subTree, depth + 1);
    if (vn.el) { out.el_tag = vn.el.nodeName; out.el_class = String(vn.el.className || '').slice(0, 60); }
    return out;
  };
  const vnode = box._vnode;
  return {
    dom_children: Array.from(box.childNodes).map(n => ({nodeType: n.nodeType, name: n.nodeName, cls: (n.className || '').slice(0, 40)})),
    vnode: shape(vnode, 0),
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--question", default="")
    ap.add_argument("--wait-s", type=float, default=20.0)
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
        if args.question:
            page.click("[data-testid=chat-input]")
            page.keyboard.type(args.question, delay=18)
            page.click("[data-testid=chat-send]")
            deadline = time.time() + args.wait_s
            while time.time() < deadline:
                time.sleep(2.0)
        print(json.dumps(page.evaluate(DUMP), ensure_ascii=False, indent=1)[:5000])
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
