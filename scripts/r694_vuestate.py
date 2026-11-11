"""R694 · 顺着 Vue 的实例树把「问一句」那一屏的状态抄回来。

只读：不改产品码、不改屏上任何东西。取的是 ``#app.__vue_app__._instance`` 往下那棵
``subTree``，逐个组件问一次 ``setupState``——类名与变量名都在生产包里被压掉了，
所以按「哪一枚组件的 setupState 里有 messages 与 deepBlocked」定位，不靠名字。
"""
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

WALK = """
(keys) => {
  const app = document.querySelector('#app');
  const vueApp = app && app.__vue_app__;
  const root = (app && app._vnode && app._vnode.component)
    || (vueApp && (vueApp._instance || (vueApp._container && vueApp._container._vnode
        && vueApp._container._vnode.component)));
  if (!root) return {error: 'no vue root instance'};
  const found = [];
  const brief = (v) => {
    if (Array.isArray(v)) return {kind: 'array', length: v.length,
      head: v.slice(0, 3).map(x => x && typeof x === 'object'
        ? {role: x.role, chars: x.content ? String(x.content).length : null, keys: Object.keys(x).slice(0, 16)}
        : typeof x)};
    if (v && typeof v === 'object') {
      const o = {kind: 'object', keys: Object.keys(v).slice(0, 16)};
      for (const k of ['state', 'face', 'session', 'request', 'turn', 'from', 'text', 'headline']) {
        if (k in v) o[k] = v[k];
      }
      return o;
    }
    return {kind: typeof v, value: v};
  };
  const seen = new Set();
  const visit = (inst, depth) => {
    if (!inst || depth > 12 || seen.has(inst)) return;
    seen.add(inst);
    const s = inst.setupState || {};
    let has = null;
    try { has = keys.filter(k => k in s); } catch (e) { has = []; }
    const name = (inst.type && (inst.type.__name || inst.type.name)) || '?';
    if (has.length) {
      found.push({name, depth, keys: has, values: Object.fromEntries(has.map(k => [k, brief(s[k])]))});
    }
    const kids = [];
    const collect = (vn) => {
      if (!vn) return;
      if (vn.component) kids.push(vn.component);
      if (Array.isArray(vn.children)) vn.children.forEach(collect);
      if (vn.suspense) collect(vn.suspense.subpense);
      if (vn.subTree) collect(vn.subTree);
    };
    collect(inst.subTree);
    kids.forEach(k => visit(k, depth + 1));
  };
  visit(root, 0);
  return {found, components_seen: seen.size};
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--question", default="费用报销需要经过哪些审批环节？")
    ap.add_argument("--wait-s", type=float, default=25.0)
    ap.add_argument("--ask", default="1")
    args = ap.parse_args()
    keys = ["messages", "deepLink", "deepBlocked", "sessions", "activeId", "loading", "input"]
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
        if args.ask == "1":
            page.click("[data-testid=chat-input]")
            page.keyboard.type(args.question, delay=18)
            page.click("[data-testid=chat-send]")
            deadline = time.time() + args.wait_s
            while time.time() < deadline:
                time.sleep(2.0)
        print(json.dumps(page.evaluate(WALK, keys), ensure_ascii=False, indent=1)[:6000])
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
