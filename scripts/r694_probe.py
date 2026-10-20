"""R694 选择器取证器：登录到真栈，按屏 dump DOM 事实（类名/计算样式/testid 名册）。

只在走查途中作侦察用，不写任何账面，不 import app，不改产品码。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402

from r694_common import env_key  # noqa: E402

TESTIDS = """
() => Array.from(document.querySelectorAll('[data-testid]'))
  .map(el => el.getAttribute('data-testid')).filter((v, i, a) => a.indexOf(v) === i)
"""

#: 类名命中正则的候选卡片：连自身与祖先的背景合成就读一并交回。
CARDS = """
(re) => {
  const rx = new RegExp(re);
  const scope = document.querySelector('[data-testid=workspace]') || document.body;
  const alpha = (c) => {
    if (!c || c === 'transparent') return 0;
    const m = c.match(/rgba?\\(([^)]+)\\)/);
    if (!m) return c === 'none' ? 0 : 1;
    const p = m[1].split(',').map(s => Number(s.trim()));
    return p.length < 4 ? 1 : p[3];
  };
  const out = [];
  for (const el of scope.querySelectorAll('*')) {
    const cls = String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || '');
    const tid = el.getAttribute('data-testid') || '';
    if (!rx.test(cls + ' ' + tid)) continue;
    const cs = getComputedStyle(el);
    let cover = 0, chain = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      const a = alpha(s.backgroundColor);
      if (a > 0) { chain.push((n.tagName.toLowerCase()) + '.' + String(n.className).split(' ')[0] + '@' + a); cover = 1 - (1 - cover) * (1 - a); }
      if (cover === 1) break;
    }
    const r = el.getBoundingClientRect();
    out.push({tag: el.tagName.toLowerCase(), cls, testid: tid, selfBg: cs.backgroundColor,
              selfAlpha: alpha(cs.backgroundColor), ancestorCover: Math.round(cover * 1000) / 1000,
              chain, w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y)});
  }
  return out;
}
"""


CHAT_STATE = """
() => {
  const q = (s) => document.querySelectorAll(s).length;
  const txt = (s) => { const n = document.querySelector(s); return n ? n.innerText.trim().slice(0, 300) : null; };
  return {
    url: location.href,
    search: location.search,
    msg_row: q('.msg-row'),
    bubble_wrap: q('.msg-bubble-wrap'),
    msg_content: q('.msg-content'),
    welcome: q('.welcome-screen'),
    deep_note: txt('[data-testid=deep-link-note]'),
    deep_badge: txt('[data-testid=deep-link-badge]'),
    deep_retry: q('[data-testid=deep-link-retry]'),
    source_cards: q('[data-testid=source-card]'),
    terminal_readout: txt('[data-testid=terminal-answer-readout]'),
    chat_note: txt('[data-testid=chat-note]'),
    panel_tail: txt('[data-testid=chat-panel]'),
  };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost/")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--nav", default="nav-overview")
    ap.add_argument("--wait-testid", default="")
    ap.add_argument("--what", default="testids", help="testids|cards|chat")
    ap.add_argument("--rx", default="card|kpi|stat|tile|panel")
    ap.add_argument("--question", default="")
    ap.add_argument("--watch-s", type=float, default=90.0)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=20000)
        page.fill("[data-testid=login-username]", env_key(args.env_file, "AUTH_USERNAME"))
        page.fill("[data-testid=login-password]", env_key(args.env_file, "DEMO_ADMIN_PASSWORD"))
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.wait_for_timeout(800)
        if args.nav:
            page.click("[data-testid=%s]" % args.nav)
            page.wait_for_timeout(1500)
        if args.wait_testid:
            page.wait_for_selector("[data-testid=%s]" % args.wait_testid, timeout=20000)
        if args.what == "cards":
            data = page.evaluate(CARDS, args.rx)
            print("count=%s" % len(data))
            for item in data[: args.limit]:
                print(json.dumps(item, ensure_ascii=False))
        elif args.what == "chat":
            page.click("[data-testid=nav-chat]")
            page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            page.wait_for_timeout(1200)
            ticks = [dict(at=0.0, **page.evaluate(CHAT_STATE))]
            if args.question:
                page.click("[data-testid=chat-input]")
                page.keyboard.type(args.question, delay=18)
                page.click("[data-testid=chat-send]")
                started = time.time()
                while time.time() - started < args.watch_s:
                    time.sleep(1.0)
                    ticks.append(dict(at=round(time.time() - started, 2), **page.evaluate(CHAT_STATE)))
                    if ticks[-1]["bubble_wrap"] and not ticks[-1]["msg_row"]:
                        break
            seen = set()
            for tick in ticks:
                key = json.dumps({k: v for k, v in tick.items() if k != "panel_tail"}, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                print(json.dumps(tick, ensure_ascii=False))
        else:
            print(json.dumps(page.evaluate(TESTIDS), ensure_ascii=False))
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
