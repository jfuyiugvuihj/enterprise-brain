"""R694 · 会话区那一截 DOM 的完整读数（含注释占位枚数与 Vue 组件状态）。"""
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
  const html = box ? box.innerHTML : null;
  const comments = html ? (html.match(/<!---->/g) || []).length : null;
  // 顺着 DOM 找 ChatPanel 的组件实例，把 setup 里那几枚 ref/computed 的当前值抄回来。
  let probe = null;
  const host = document.querySelector('[data-testid=chat-panel]');
  let node = host;
  while (node && !probe) {
    const inst = node.__vueParentComponent;
    if (inst && inst.setupState && ('messages' in inst.setupState || 'deepLink' in inst.setupState)) {
      const s = inst.setupState;
      const shape = (v) => {
        if (Array.isArray(v)) return {kind: 'array', length: v.length,
          items: v.slice(0, 4).map(x => ({role: x && x.role, chars: x && x.content ? String(x.content).length : null,
                                          keys: x ? Object.keys(x).slice(0, 14) : []}))};
        if (v && typeof v === 'object') return {kind: 'object', keys: Object.keys(v).slice(0, 14), state: v.state,
                                                session: v.session, request: v.request, face: v.face, turn: v.turn};
        return {kind: typeof v, value: v};
      };
      probe = {
        has_messages: 'messages' in s,
        messages: shape(s.messages),
        deepLink: shape(s.deepLink),
        deepBlocked: s.deepBlocked,
        deepFace: shape(s.deepFace),
        activeSessionId: s.activeSessionId ?? s.currentSessionId ?? null,
        session_keys: Object.keys(s).filter(k => /session|active|current/i.test(k)).slice(0, 12),
      };
    }
    node = node.parentElement;
  }
  return {child_count: box ? box.children.length : null, comments, html, probe};
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
        data = page.evaluate(DUMP)
        html = data.pop("html") or ""
        print(json.dumps(data, ensure_ascii=False))
        print("HTML_TAIL " + html[-500:])
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
