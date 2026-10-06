"""R694 · 前端九环浏览器走查驱动。

Playwright 开真浏览器打真栈，逐环取**可失败读数**并把截图落进走查目录。
本件只读产品码：不改任何 ``app/**``／``frontend/**``／``deploy/**``，
不建容器，不 rebuild，不 recreate。凭据一律按 env **键名**取，值不落纸。

跑法（Python 侧未装 playwright，用 uv 的一次性环境，不动 ``pyproject.toml``）::

    uv run --no-project --with playwright==1.63.0 python scripts/r694_walkthrough.py \
        --env-file ../企业智脑/deploy/.env.server --rings 1,2,3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import BrowserContext, Page, sync_playwright  # noqa: E402

from r694_common import (  # noqa: E402
    Ledger,
    env_key,
    epoch,
    is_external,
    register_shot,
    seconds_since,
    stamp,
    wait_for,
)

#: 屏上文案的取样间隔（秒）：进度态与逐帧生长都按这个节拍读。
SAMPLE_S = 0.2
#: 一问的墙上时钟上限：问答档 p95 在册 50.1 s，报告档 85.6 s；本机单跑留到七分钟。
ANSWER_TIMEOUT_S = 420.0

PRIMARY_USER_KEY = "AUTH_USERNAME"
PRIMARY_PASS_KEY = "DEMO_ADMIN_PASSWORD"
SECOND_USER = "dataowner"
SECOND_PASS_KEY = "EB_SEED_OWNER_PASSWORD"

#: SSE 取帧器。挂在 fetch 上，把 ``text/event-stream`` 的响应 tee 一份自己解析；
#: 交给产品码的那一份一字不动，所以屏上走的还是产品自己的解析腿。
SSE_TAP = """
(() => {
  const streams = [];
  window.__r694 = { streams };
  const orig = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const asked = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const resp = await orig(...args);
    try {
      const ct = (resp.headers && resp.headers.get('content-type')) || '';
      if (ct.indexOf('text/event-stream') >= 0 && resp.body) {
        const rec = {
          url: resp.url || asked, status: resp.status, startedAt: Date.now(),
          endedAt: null, closed: false, frames: [], error: null,
        };
        streams.push(rec);
        const [keep, tap] = resp.body.tee();
        const reader = tap.getReader();
        const decoder = new TextDecoder();
        let rest = '';
        const pump = async () => {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            rest += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = rest.indexOf('\\n\\n')) >= 0) {
              const block = rest.slice(0, cut);
              rest = rest.slice(cut + 2);
              let name = '', payload = '';
              for (const line of block.split('\\n')) {
                if (line.indexOf('event:') === 0) name = line.slice(6).trim();
                else if (line.indexOf('data:') === 0) payload += line.slice(5).trim();
              }
              let seq = null, chars = null;
              try {
                const j = JSON.parse(payload);
                seq = typeof j.sequence === 'number' ? j.sequence : null;
                chars = typeof j.content === 'string' ? j.content.length : null;
              } catch (e) { /* 非 JSON 帧只记名字 */ }
              rec.frames.push({ t: Date.now(), event: name, sequence: seq, chars: chars, bytes: block.length });
            }
          }
          rec.closed = true;
          rec.endedAt = Date.now();
        };
        pump().catch((e) => { rec.error = String(e); rec.closed = true; rec.endedAt = Date.now(); });
        return new Response(keep, {
          status: resp.status, statusText: resp.statusText, headers: resp.headers,
        });
      }
    } catch (e) { window.__r694.tapError = String(e); }
    return resp;
  };
})();
"""

#: 屏上「最新那一气泡」的正文长度与来源卡枚数——逐帧生长的 DOM 侧凭据。
BUBBLE_PROBE = """
() => {
  const bubbles = Array.from(document.querySelectorAll('.msg-bubble-wrap'));
  const last = bubbles[bubbles.length - 1] || null;
  const content = last ? (last.querySelector('.msg-content') || {}).textContent || '' : '';
  return {
    bubbles: bubbles.length,
    chars: content.length,
    sources: document.querySelectorAll('[data-testid=source-card]').length,
    steps: document.querySelectorAll('.steps-bar .step-card').length,
    charts: document.querySelectorAll('.chart-card, .chart-img').length,
    hitlCard: document.querySelectorAll('[data-testid=hitl-approve-chat]').length,
    faces: Array.from(document.querySelectorAll('[data-testid=runtime-face]')).map((e) => e.textContent.trim().slice(0, 120)),
  };
}
"""

#: 工作台正文卡片的取样范围：只在工作区里挑矩形完整落在视口内的卡片。
CARD_JS = """
() => {
  const scope = document.querySelector('[data-testid=workspace]') || document.body;
  const out = [];
  for (const sel of ['.reference-kpi', '.reference-card', '.panel-card']) {
    for (const el of scope.querySelectorAll(sel)) {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 24) continue;
      if (r.y < 0 || r.bottom > innerHeight || r.x < 0 || r.right > innerWidth) continue;
      out.push({
        sel, tag: el.tagName.toLowerCase(), cls: String(el.className),
        testid: el.getAttribute('data-testid') || '',
        selfBg: cs.backgroundColor, selfImage: cs.backgroundImage.slice(0, 150),
        backdrop: cs.backdropFilter,
        rect: {x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height)},
      });
      if (out.length >= 8) return out;
    }
  }
  return out;
}
"""

#: 把背景美术层显／隐各拍一枚矩形，两态像素差＝「透底」多少（通道尺度 0–255）。
ART_TOGGLE_JS = """
(on) => {
  const layers = Array.from(document.querySelectorAll('.app-bg__art'));
  for (const el of layers) el.style.display = on ? 'none' : '';
  return layers.length;
}
"""

#: 判据「正文卡片实心不透底」的数值线：像素均差超过这一格即判未达。
BLEED_MEAN_LIMIT = 6.0

#: 产品自己的 API 前缀；少了这一格，`http://localhost/documents` 只会撞上 SPA 回落页。
API_PREFIX = "/api/v1"

#: 输入框迟迟不松开时取一枚屏面探针：只读数，不重试，不改任何东西。
BLOCKED_PROBE_JS = r"""
() => {
  const flag = (sel) => { const n = document.querySelector(sel); return n ? { present: 1, disabled: !!n.disabled, readOnly: !!n.readOnly } : { present: 0 }; };
  return {
    chat_input: flag('[data-testid=chat-input]'),
    chat_send: flag('[data-testid=chat-send]'),
    streams_open: (window.__r694.streams || []).filter((s) => !s.closed).length,
    streams_total: (window.__r694.streams || []).length,
    chat_note: (() => { const n = document.querySelector('[data-testid=chat-note]'); return n ? n.innerText.trim().slice(0, 200) : null; })(),
    hitl_cards: document.querySelectorAll('[data-testid=hitl-approve-chat]').length,
    msg_rows: document.querySelectorAll('.msg-row').length,
  };
}
"""

#: 审批屏那一列是异步读的：给它这么久落定，再判「今天没有待批」。
PENDING_SETTLE_S = 25.0

#: 点了批准或驳回之后，等那一行从待批列里退出来给多久。
DECIDE_WAIT_S = 90.0

#: 批准后等产物登记上来的上限：出图与出报告各自都要穿过模型与绘图两腿。
ARTIFACT_WAIT_S = 150.0

#: 现读后端日志往回看多少分钟（只读日志，不改任何东西）。
LOG_LOOKBACK_MIN = 45


class Walk:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out / "ledger.json", fresh=bool(getattr(args, "fresh", False)))
        self.ledger.set_root("started_at", stamp())
        self.ledger.set_root("base_url", args.base_url)
        self.ledger.set_root("origin_host", urlparse(args.base_url).hostname)
        self.ledger.set_root("fixture", str(args.fixture))
        self.ledger.set_root("fixture_bytes", Path(args.fixture).stat().st_size)
        self.ledger.set_root("credential_key_names", {
            "primary": [PRIMARY_USER_KEY, PRIMARY_PASS_KEY],
            "secondary": [SECOND_USER, SECOND_PASS_KEY],
        })
        self.pw = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.requests: list[str] = []
        self.state: dict[str, Any] = {}
        #: 本轮编号：同一枚问句第二次问会命中答案缓存，缓存那一发只给一帧，量不到逐帧长出。
        self.nonce = time.strftime("%H%M%S")

    # ---------------------------------------------------------------- 生命周期
    def __enter__(self) -> "Walk":
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

    # ------------------------------------------------------------------ 工具台
    def open_page(self, width: int = 1440, height: int = 900) -> Page:
        """开一枚独立 context（独立 localStorage），只把页面摆好，不登录。"""
        context = self.browser.new_context(viewport={"width": width, "height": height})
        context.add_init_script(SSE_TAP)
        page = context.new_page()
        seen: list[str] = []
        page.on("request", lambda r: seen.append(r.url))
        page.on("requestfailed", lambda r: seen.append("FAILED " + r.url))
        page.context.__setattr__("r694_requests", seen)
        return page

    def new_principal(self, username: str, password: str, width: int = 1440, height: int = 900) -> Page:
        """开一枚新的身份并登录到同一台栈。"""
        page = self.open_page(width, height)
        self._login(page, username, password)
        self.state["last_seen_requests"] = list(page.context.r694_requests)
        return page

    def _login(self, page: Page, username: str, password: str) -> None:
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=20000)
        page.fill("[data-testid=login-username]", username)
        page.fill("[data-testid=login-password]", password)
        page.click("[data-testid=login-submit]")
        page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
        page.wait_for_timeout(600)

    def open_screen(self, nav_testid: str, wait_testid: str) -> None:
        assert self.page is not None
        self.page.click("[data-testid=%s]" % nav_testid)
        self.page.wait_for_selector("[data-testid=%s]" % wait_testid, timeout=20000)
        self.page.wait_for_timeout(500)

    def api(self, path: str) -> Any:
        """在浏览器里带着产品自己的 token 打一次 GET：读数出自屏所在的那条腿。"""
        assert self.page is not None
        parsed = urlparse(self.args.base_url)
        root = "%s://%s" % (parsed.scheme, parsed.netloc)
        return self.page.evaluate(
            """async (p) => {
                const token = localStorage.getItem('eb_token') || '';
                const r = await fetch(p, { headers: { Authorization: 'Bearer ' + token } });
                return { status: r.status, body: await r.json().catch(() => null) };
            }""",
            root + API_PREFIX + path,
        )

    def shot(self, name: str, **kwargs: Any) -> dict[str, Any]:
        assert self.page is not None
        return register_shot(self.page, self.out, name, **kwargs)

    def question(self, text: str) -> str:
        """把问句钉成本轮唯一的一发：缓存命中路径只交一帧，逐帧生长就没得量了。"""
        return "%s（走查编号 %s）" % (text, self.nonce)

    def finish(self, ring: int, title: str, status: str, readings: dict[str, Any], shots: list[dict[str, Any]], note: str = "") -> None:
        self.ledger.record("rings", {
            "ring": ring,
            "title": title,
            "status": status,
            "readings": readings,
            "shots": shots,
            "note": note,
        })
        print("[ring %s] %s -> %s" % (ring, title, status))

    # ------------------------------------------------------------------ 实心度
    def _card_solidity(self, page: Page, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """实心度读数取自屏上像素，不取自样式声明：声明可以写错，两张图不能。

        同一枚矩形在背景美术层「显」与「隐」两态各拍一次，两态逐通道绝对差取回：
        均差越小＝卡片越实心（背景美术透不上来）。
        """
        import io

        from PIL import Image, ImageChops

        out: list[dict[str, Any]] = []
        for cand in cards[:4]:
            clip = dict(cand["rect"])
            over = page.screenshot(clip=clip, animations="disabled")
            hidden = page.evaluate(ART_TOGGLE_JS, True)
            under = page.screenshot(clip=clip, animations="disabled")
            page.evaluate(ART_TOGGLE_JS, False)
            left = Image.open(io.BytesIO(over)).convert("RGB")
            right = Image.open(io.BytesIO(under)).convert("RGB")
            if left.size != right.size:
                right = right.resize(left.size)
            delta = ImageChops.difference(left, right)
            hist = delta.histogram()
            pixels = left.size[0] * left.size[1]
            summed = sum(sum(hist[ch * 256 + k] * k for k in range(256)) for ch in range(3))
            out.append({
                "sel": cand["sel"],
                "cls": cand["cls"],
                "testid": cand["testid"],
                "rect": clip,
                "self_bg": cand["selfBg"],
                "self_image": cand["selfImage"],
                "art_layers_toggled": hidden,
                "bleed_mean_delta": round(summed / float(pixels * 3), 3),
                "bleed_max_delta": max(ext[1] for ext in delta.getextrema()),
            })
        return out

    # --------------------------------------------------------------------- 环
    def ring1(self) -> None:
        page = self.open_page()
        self.context = page.context
        self.page = page
        page.goto(self.args.base_url, wait_until="load")
        page.wait_for_selector("[data-testid=login-page]", timeout=20000)
        page.wait_for_timeout(1200)
        requests = list(page.context.r694_requests)
        external = [u for u in requests if is_external(u)]
        font_hosts = [u for u in requests if "googleapis" in u or "gstatic" in u]
        art = page.eval_on_selector(
            ".login-bg__art",
            "el => ({ backgroundImage: getComputedStyle(el).backgroundImage, display: getComputedStyle(el).display })",
        )
        readings = {
            "requests_total": len(requests),
            "requests_external": external,
            "requests_font_cdn": font_hosts,
            "login_page_present": page.locator("[data-testid=login-page]").count(),
            "globe_art_layer": art,
            "document_fonts_status": page.evaluate("() => document.fonts.status"),
            "body_chars": page.evaluate("() => document.body.innerText.replace(/\\s+/g,' ').length"),
            "visible_cards": page.locator("[data-testid=login-panel]").count(),
            "white_screen_guard": page.evaluate(
                "() => document.querySelectorAll('body *').length"
            ),
        }
        status = "达" if (not external and not font_hosts and art["backgroundImage"].find("url") >= 0 and readings["body_chars"] > 40) else "未达"
        shots = [self.shot("r694-r1-login-1440.png")]
        self.finish(1, "登录页", status, readings, shots)

    def ring2(self) -> None:
        """环 2 接在环 1 同一枚 context 上：登录动作本身就是要验的那一格。"""
        page = self.page
        assert page is not None
        login_started = epoch()
        self._login(
            page,
            env_key(self.args.env_file, PRIMARY_USER_KEY),
            env_key(self.args.env_file, PRIMARY_PASS_KEY),
        )
        login_elapsed = seconds_since(login_started)
        layers = page.eval_on_selector_all(
            "div.app-bg > *",
            "els => els.map(e => ({ cls: e.className, ariaHidden: e.getAttribute('aria-hidden'), "
            "display: getComputedStyle(e).display, bg: getComputedStyle(e).backgroundImage.slice(0, 60) }))",
        )
        wrap = page.eval_on_selector(
            "div.app-bg",
            "el => ({ cls: el.className, ariaHidden: el.getAttribute('aria-hidden') })",
        )
        first_screen_cards = page.evaluate(CARD_JS)
        solidity = self._card_solidity(page, first_screen_cards)
        first_screen_count = len(solidity)
        # 首屏只躺得下 KPI 那一排，正文卡（reference-card）在更下面：滚进视口再测一批。
        page.evaluate(
            "() => { const el = document.querySelector('[data-testid=dashboard-risk-card]');"
            " if (el) el.scrollIntoView({block: 'center'}); }"
        )
        page.wait_for_timeout(400)
        lower = page.evaluate(CARD_JS)
        solidity += self._card_solidity(page, lower)
        readings = {
            "login_elapsed_s": login_elapsed,
            "app_bg_wrapper": wrap,
            "app_bg_layers": layers,
            "layer_count": len(layers),
            "expected_layer_names": ["app-bg__base", "app-bg__art", "app-bg__grid", "app-bg__scrim"],
            "layer_names_seen": [lay["cls"] for lay in layers],
            "body_cards": first_screen_cards,
            "art_bleed": solidity,
            "art_bleed_first_screen": solidity[:first_screen_count],
            "art_bleed_after_scroll": solidity[first_screen_count:],
            "user_shown": page.evaluate("() => localStorage.getItem('eb_user')"),
            "role_shown": page.evaluate("() => localStorage.getItem('eb_role')"),
        }
        names = [lay["cls"] for lay in layers]
        needed = readings["expected_layer_names"]
        layers_ok = all(any(n in name for name in names) for n in needed)
        bleed_ok = bool(solidity) and all(s["bleed_mean_delta"] <= BLEED_MEAN_LIMIT for s in solidity)
        readings["bleed_mean_limit"] = BLEED_MEAN_LIMIT
        readings["bleed_worst_mean"] = max([s["bleed_mean_delta"] for s in solidity], default=None)
        status = "达" if (layers_ok and wrap["ariaHidden"] == "true" and bleed_ok) else "未达"
        shots = [self.shot("r694-r2-workbench-1440.png")]
        page.set_viewport_size({"width": 760, "height": 1024})
        page.wait_for_timeout(700)
        readings["viewport_760_workspace_chars"] = page.evaluate(
            "() => (document.querySelector('[data-testid=workspace]') || {}).innerText ? document.querySelector('[data-testid=workspace]').innerText.length : 0"
        )
        shots.append(self.shot("r694-r2-workbench-760.png"))
        self.finish(2, "登录成功进工作台", status, readings, shots)

    def ring3(self) -> None:
        assert self.page is not None
        page = self.page
        page.set_viewport_size({"width": 1440, "height": 900})
        self.open_screen("nav-feed", "documents-panel")
        fixture = Path(self.args.fixture)
        # 上一笔走查没复原时，同名档只会开出新版本，计数不按 +1 走——先现读这一格，别让它冒充回归。
        pre_existing = page.locator("[data-testid=doc-row]").filter(has_text=fixture.name).count()
        before = self._doc_counts()
        shots = [self.shot("r694-r3-upload-before.png")]
        page.set_input_files("[data-testid=document-upload-input]", str(fixture))
        states = []
        deadline = time.time() + 60
        while time.time() < deadline:
            line = page.evaluate(
                """() => {
                    const items = Array.from(document.querySelectorAll('.upload-item'));
                    return items.map(e => ({ cls: e.className, msg: (e.querySelector('.up-msg') || {}).textContent || '',
                                             phase: (e.querySelector('[data-testid=upload-item-classification]') || {}).textContent || '' }));
                }"""
            )
            sig = json.dumps(line, ensure_ascii=False, sort_keys=True)
            if not states or states[-1]["sig"] != sig:
                states.append({"at": epoch(), "t_s": None, "sig": sig, "items": line})
            row = page.locator("[data-testid=doc-row]").filter(has_text=fixture.name)
            if row.count() and _row_is_retrievable(row.first.inner_text()):
                break
            time.sleep(SAMPLE_S)
        for s in states:
            s["t_s"] = round(s["at"] - states[0]["at"], 3)
        mid_shot = self.shot("r694-r3-upload-progress.png")
        retried = wait_for(lambda: page.locator("[data-testid=doc-row]").filter(has_text=fixture.name).count() > 0, 90)
        row_text = ""
        if retried:
            row_text = page.locator("[data-testid=doc-row]").filter(has_text=fixture.name).first.inner_text()
        after = self._doc_counts()
        shots.append(mid_shot)
        shots.append(self.shot("r694-r3-upload-after.png"))
        readings = {
            "fixture_name": fixture.name,
            "fixture_bytes": fixture.stat().st_size,
            "fixture_already_in_corpus_before_upload": pre_existing,
            "tile_source": "喂料面板标题栏 .panel-hd-left .badge（docs.length）",
            "counts_before": before,
            "counts_after": after,
            "count_delta": (after.get("tile") or 0) - (before.get("tile") or 0) if after.get("tile") is not None and before.get("tile") is not None else None,
            "upload_state_transitions": [
                {"t_s": s["t_s"], "items": s["items"]} for s in states
            ],
            "row_text_after": row_text.replace("\n", " | "),
            "row_present": bool(retried),
        }
        status = "达" if (
            pre_existing == 0
            and readings["count_delta"] == 1
            and _row_is_retrievable(row_text)
            and len(readings["upload_state_transitions"]) >= 1
        ) else "未达"
        self.state["uploaded"] = fixture.name
        self.finish(3, "上传文档", status, readings, shots)

    def _doc_counts(self) -> dict[str, Any]:
        assert self.page is not None
        tile = self.page.evaluate(
            "() => { const b = document.querySelector("
            "'[data-testid=documents-panel] .panel-hd-left .badge');"
            " return b ? Number(b.textContent.trim()) : null; }"
        )
        rows = self.page.locator("[data-testid=doc-row]").count()
        api = self.api("/documents")
        listed = api["body"].get("documents") if isinstance(api["body"], dict) else None
        return {
            "tile": tile,
            "rows_rendered": rows,
            "api_status": api["status"],
            "api_document_count": len(listed) if isinstance(listed, list) else None,
        }

    def ring4(self) -> None:
        assert self.page is not None
        page = self.page
        name = self.args.fixture_name or self.state.get("uploaded") or Path(self.args.fixture).name
        self.open_screen("nav-feed", "documents-panel")
        page.wait_for_timeout(800)
        row = page.locator("[data-testid=doc-row]").filter(has_text=name)
        present = row.count() > 0
        fields = {}
        if present:
            fields = row.first.evaluate(
                """el => {
                    const grab = (sel) => { const n = el.querySelector(sel); return n ? n.textContent.trim() : null; };
                    return {
                        filename: grab('.doc-name') || el.innerText.split('\\n')[0],
                        statusWord: grab('[data-testid=doc-retrieval]') || grab('[data-testid=doc-index-status]'),
                        truth: grab('[data-testid=doc-row-truth]'),
                        indexStatus: grab('[data-testid=doc-index-status]'),
                        classification: grab('.doc-class') || grab('[data-testid=doc-class]'),
                        controls: Array.from(el.querySelectorAll('button')).map(b => b.getAttribute('data-testid') || b.innerText.trim()).filter(Boolean),
                        rawText: el.innerText.replace(/\\n+/g, ' | '),
                    };
                }"""
            )
        catalog = self.api("/documents/catalog")
        catalog_row = None
        if isinstance(catalog["body"], dict):
            entries = catalog["body"].get("catalog") or catalog["body"].get("documents") or catalog["body"].get("items") or []
            if isinstance(entries, list):
                for entry in entries:
                    blob = json.dumps(entry, ensure_ascii=False)
                    if name and name in blob:
                        catalog_row = entry
                        break
        readings = {
            "row_present": present,
            "row_fields": fields,
            "catalog_api_status": catalog["status"],
            "catalog_keys": sorted(list(catalog_row.keys())) if isinstance(catalog_row, dict) else None,
            "catalog_row": catalog_row,
            "catalog_top_level_keys": sorted(list(catalog["body"].keys())) if isinstance(catalog["body"], dict) else None,
        }
        shots = [self.shot("r694-r4-catalog.png")]
        status = "达" if (present and fields.get("truth") and catalog_row) else "未达"
        self.finish(4, "文档列表／状态", status, readings, shots)

    # ------------------------------------------------------------- 问答三兄弟
    def _pick_table(self, page: Page, wanted: str) -> None:
        """选一张数据表：清单是 lazy 的，伸手（focus／改选／点重读）才发那一枪。

        读数把「屏上选项名册」与「最终选中那一枚」都记下来；wanted 匹配不到时
        取第一枚真实选项，并把这一格照记，不冒充命中。
        """
        select = page.locator("[data-testid=chat-data-table-select]")
        choice: dict[str, Any] = {"wanted": wanted, "select_present": select.count()}
        if not select.count():
            self.state["table_choice"] = choice
            return
        select.first.focus()
        page.wait_for_timeout(600)
        if page.locator("[data-testid=chat-data-table-reload]").count():
            page.click("[data-testid=chat-data-table-reload]")
            page.wait_for_timeout(2000)
        labels = select.first.evaluate(
            "el => Array.from(el.options).map(o => (o.textContent || '').trim()).filter(Boolean)"
        )
        real = [x for x in labels if x != "不指定"]
        hit = next((x for x in real if wanted in x), real[0] if real else None)
        if hit:
            select.first.select_option(label=hit)
            page.wait_for_timeout(400)
        choice.update({
            "options_on_screen": labels,
            "chosen": hit,
            "picker_face": (page.locator("[data-testid=chat-data-table-face]").first.inner_text()
                            if page.locator("[data-testid=chat-data-table-face]").count() else None),
        })
        self.state["table_choice"] = choice

    def _stream_frames(self, page: Page) -> list[dict[str, Any]]:
        """取帧器里那几段流的逐帧账（事件名、序号、每帧字符数、到达毫秒）。"""
        return page.evaluate(
            """() => window.__r694.streams.map(s => ({
                    url: s.url, status: s.status, startedAt: s.startedAt, endedAt: s.endedAt,
                    closed: s.closed, error: s.error,
                    frames: s.frames.map(f => ({ t: f.t, event: f.event, sequence: f.sequence, chars: f.chars }))
                }))"""
        )

    def ask(self, question: str, approve_in_chat: bool = True, table: str | None = None, lane: str | None = None) -> dict[str, Any]:
        """在「问一句」里用真键盘问一句，取帧账、生长曲线、来源卡与 HITL 牌。

        屏上正文这一腿今天要先刷新一次才画得出来（见纸「缺陷清单」缺陷 #1），
        所以两态分开取：帧账与 live 屏面在刷新之前拿，屏上正文/来源卡/图在刷新之后拿，
        两态之间的差别本身也是读数，不许并成一格冒充「屏上一直有」。
        """
        assert self.page is not None
        page = self.page
        if table or lane:
            if lane:
                page.select_option("#chat-lane-select", label=lane)
            if table:
                self._pick_table(page, table)
        # 上一发还在飞的时候输入框是 disabled：先等它自己松开，别把「按不动」记成「走不下去」。
        input_wait_started = epoch()
        field = page.locator("[data-testid=chat-input]")
        unlocked = wait_for(lambda: field.count() > 0 and field.first.is_enabled(), ANSWER_TIMEOUT_S, poll_s=1.0)
        input_wait_s = seconds_since(input_wait_started)
        if not unlocked:
            return {
                "question": question,
                "asked": False,
                "blocked_probe": page.evaluate(BLOCKED_PROBE_JS),
                "blocked_reason": "输入框在 %s s 内没有松开（上一发仍未落地）" % round(input_wait_s, 1),
                "input_wait_s": input_wait_s,
                "streams": [], "frame_count_total": 0, "text_frame_count": 0,
                "answer_chars_from_frames": 0, "final_chars": 0, "sources_cards": 0,
                "steps_cards": 0, "charts_on_screen": 0, "runtime_faces": [],
                "rows_live_before_reload": page.locator(".msg-row").count(),
                "reloaded_to_read_screen": False, "sequence_monotonic": None,
                "sequence_first_last": [], "mid_shot": None, "hitl": {},
                "growth_samples": [], "growth_sample_count": 0,
            }
        page.click("[data-testid=chat-input]")
        page.keyboard.type(question, delay=18)
        started = epoch()
        # 取帧器是跨轮累积的：不清掉上一轮那几段，第一枚取样就会把旧帧当「本轮已闭」判错。
        page.evaluate("() => { window.__r694.streams.length = 0; }")
        page.click("[data-testid=chat-send]")
        samples: list[dict[str, Any]] = []
        mid_shot: dict[str, Any] | None = None
        stream_done = False
        deadline = started + ANSWER_TIMEOUT_S
        while time.time() < deadline:
            probe = page.evaluate(BUBBLE_PROBE)
            streams = page.evaluate(
                "() => window.__r694.streams.map(s => ({closed: s.closed, frames: s.frames.length}))"
            )
            frame_total = sum(s["frames"] for s in streams) if streams else 0
            samples.append({"t_s": round(time.time() - started, 3), "frames": frame_total, **probe})
            stream_done = bool(streams) and all(s["closed"] for s in streams)
            hitl = page.locator("[data-testid=hitl-approve-chat]").count()
            slot = self.state.get("mid_shot_slot")
            if mid_shot is None and slot and frame_total >= 3 and not stream_done:
                mid_shot = self.shot("r694-%s-stream-mid.png" % slot)
            if stream_done and (probe["chars"] > 0 or hitl or frame_total >= 2):
                break
            time.sleep(SAMPLE_S)
        frames = self._stream_frames(page)
        rows_live = page.locator(".msg-row").count()
        decision: dict[str, Any] = {
            "hitl_seen_before_decision": page.locator("[data-testid=hitl-approve-chat]").count(),
        }
        if approve_in_chat and decision["hitl_seen_before_decision"]:
            page.click("[data-testid=hitl-approve-chat]")
            decision["resumed_samples"] = self._wait_after_resume(started)
            frames = self._stream_frames(page)
        reloaded = False
        if not page.locator(".msg-row").count():
            page.reload(wait_until="load")
            page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            page.wait_for_timeout(1500)
            reloaded = True
        screen = page.evaluate(BUBBLE_PROBE)
        text_frames = [f for s in frames for f in s["frames"] if f["event"] == "text"]
        stamps = [f["t"] for s in frames for f in s["frames"]]
        t0 = min(stamps) if stamps else 0
        readings = {
            "question": question,
            "asked": True,
            "input_wait_s": input_wait_s,
            "asked_at": stamp(),
            "started_epoch_s": round(started, 3),
            "finished_epoch_s": round(time.time(), 3),
            "elapsed_s": seconds_since(started),
            "streams": [
                {
                    "url": s["url"],
                    "http_status": s["status"],
                    "closed": s["closed"],
                    "started_ms": s["startedAt"],
                    "ended_ms": s["endedAt"],
                    "duration_s": round(((s["endedAt"] or 0) - s["startedAt"]) / 1000.0, 3) if s["endedAt"] else None,
                    "frame_count": len(s["frames"]),
                    "event_names": _ordered(f["event"] for f in s["frames"]),
                    "sequences": [f["sequence"] for f in s["frames"] if f["sequence"] is not None],
                    "frames_raw": s["frames"][:400],
                }
                for s in frames
            ],
            "text_frame_count": len(text_frames),
            "text_frame_curve": [
                {"ms": f["t"] - t0, "chars": f["chars"]} for f in text_frames[:80]
            ],
            "answer_chars_from_frames": sum(f["chars"] or 0 for f in text_frames),
            "growth_samples": samples[-120:],
            "growth_sample_count": len(samples),
            "distinct_frame_counts": _ordered(sample["frames"] for sample in samples),
            "distinct_screen_lengths": _ordered(sample["chars"] for sample in samples),
            "rows_live_before_reload": rows_live,
            "reloaded_to_read_screen": reloaded,
            "screen_probe": screen,
            "final_chars": screen["chars"],
            "sources_cards": screen["sources"],
            "steps_cards": screen["steps"],
            "charts_on_screen": screen["charts"],
            "runtime_faces": screen["faces"],
            "hitl": decision,
        }
        seq_all = [q for s in readings["streams"] for q in s["sequences"]]
        readings["sequence_monotonic"] = all(b > a for a, b in zip(seq_all, seq_all[1:])) if len(seq_all) > 1 else None
        readings["sequence_first_last"] = [seq_all[0], seq_all[-1]] if seq_all else []
        readings["frame_count_total"] = sum(s["frame_count"] for s in readings["streams"])
        readings["mid_shot"] = mid_shot
        return readings

    def _wait_after_resume(self, started: float) -> list[dict[str, Any]]:
        page = self.page
        assert page is not None
        samples = []
        deadline = time.time() + ANSWER_TIMEOUT_S
        while time.time() < deadline:
            probe = page.evaluate(BUBBLE_PROBE)
            streams = page.evaluate("() => window.__r694.streams.map(s => s.closed)")
            samples.append({"t_s": round(time.time() - started, 3), **probe})
            if all(streams) and probe["chars"] > 0:
                break
            time.sleep(SAMPLE_S)
        return samples[-80:]

    # ------------------------------------------------------------- 批准与读屏
    def ensure_login(self) -> None:
        """单独跑某一环时自己把身份补齐：环与环之间只共享这一枚 context。"""
        if self.context is None:
            self.page = self.new_principal(
                env_key(self.args.env_file, PRIMARY_USER_KEY),
                env_key(self.args.env_file, PRIMARY_PASS_KEY),
            )
            self.context = self.page.context

    def approve_pending(self, click: bool = True) -> dict[str, Any]:
        """在「审批与待办」屏批准最新一枚待批，取批准前后两态。

        对话里那张批准牌今天拿不到：live 那一屏连气泡都没画（缺陷 #1），
        所以批准这一腿走审批屏——它本来就是同一条出口（POST /api/v1/approve）。
        """
        page = self.page
        assert page is not None
        self.open_screen("nav-approval", "hitl-pending")
        rows = page.locator("[data-testid=hitl-row]")
        settled = wait_for(lambda: rows.count() > 0, PENDING_SETTLE_S, poll_s=1.0)
        if not settled and page.locator("[data-testid=hitl-reload]").count():
            page.click("[data-testid=hitl-reload]")
            settled = wait_for(lambda: rows.count() > 0, PENDING_SETTLE_S, poll_s=1.0)
        rows_before = rows.count()
        texts_before = [t.replace("\n", " | ")[:220] for t in rows.all_inner_texts()]
        out: dict[str, Any] = {
            "pending_rows_before": rows_before,
            "pending_row_texts_before": texts_before,
            "pending_settled": bool(settled),
            "pending_face_when_empty": (
                None if rows_before else page.evaluate(
                    "() => { const n = document.querySelector('[data-testid=hitl-pending]');"
                    " return n ? n.innerText.trim().slice(0, 200) : null; }")
            ),
        }
        approved = False
        outcomes: list[str] = []
        if rows_before and click:
            page.locator("[data-testid=hitl-approve]").first.click()
            approved = True
            deadline = time.time() + ANSWER_TIMEOUT_S
            while time.time() < deadline:
                outcomes = page.locator("[data-testid=hitl-outcome]").all_inner_texts()
                if page.locator("[data-testid=hitl-row]").count() == 0 or outcomes:
                    break
                time.sleep(1.0)
        elif rows_before:
            outcomes = page.locator("[data-testid=hitl-outcome]").all_inner_texts()
        out["approved_clicked"] = approved
        out["pending_rows_after"] = page.locator("[data-testid=hitl-row]").count()
        out["outcome_faces_after"] = [t.replace("\n", " | ")[:200] for t in outcomes]
        out["outcome_codes"] = page.locator("[data-testid=hitl-outcome-code]").all_inner_texts()
        return out

    def read_chat_screen(self) -> dict[str, Any]:
        """回到「问一句」读屏上那一截；live 没画出来就刷新一次再读，两态都记。"""
        page = self.page
        assert page is not None
        self.open_screen("nav-chat", "chat-panel")
        page.wait_for_timeout(1200)
        rows_live = page.locator(".msg-row").count()
        reloaded = False
        if not rows_live:
            page.reload(wait_until="load")
            page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            page.wait_for_timeout(1500)
            reloaded = True
        probe = page.evaluate(BUBBLE_PROBE)
        answer = page.evaluate(
            "() => { const b = document.querySelectorAll('.msg-bubble-wrap');"
            " return b.length ? b[b.length-1].innerText : ''; }"
        )
        chart_src = page.evaluate(
            "() => Array.from(document.querySelectorAll('.chart-img')).map(i => i.getAttribute('src'))"
        )
        return {
            "rows_live_before_reload": rows_live,
            "reloaded_to_read_screen": reloaded,
            "screen_probe": probe,
            "final_chars": probe["chars"],
            "sources_cards": probe["sources"],
            "steps_cards": probe["steps"],
            "charts_on_screen": probe["charts"],
            "chart_srcs": chart_src[:4],
            "answer_tail": answer[-700:].replace("\n", " | "),
            "terminal_answer_readouts": page.locator(
                "[data-testid=terminal-answer-readout]").all_inner_texts(),
        }

    # --------------------------------------------------------------------- 环
    def ring5(self) -> None:
        self.state["mid_shot_slot"] = "r5"
        self.ensure_login()
        self.open_screen("nav-chat", "chat-panel")
        readings = self.ask(self.question(self.args.question), approve_in_chat=False)
        shots = [r for r in [readings.pop("mid_shot")] if r]
        shots.append(self.shot("r694-r5-answer-final.png"))
        status = "达" if (
            readings["frame_count_total"] > 1
            and readings["answer_chars_from_frames"] > 40
            and readings["final_chars"] > 40
            and readings["sources_cards"] > 0
            and readings["sequence_monotonic"] is not False
        ) else "未达"
        self.state["ring5_sources"] = readings["sources_cards"]
        self.state["ring5_final_chars"] = readings["final_chars"]
        self.state["ring5_answer_chars"] = readings["answer_chars_from_frames"]
        self.state["ring5_question"] = readings["question"]
        note = ("屏上正文取自刷新之后的同一会话（刷新前 .msg-row 枚数见 rows_live_before_reload）；"
                "帧账与逐帧字符取自刷新之前的取帧器。" if readings["reloaded_to_read_screen"] else "")
        self.finish(5, "知识问答（流式）", status, readings, shots, note)

    def ring6(self) -> None:
        primary_sources = self.state.get("ring5_sources")
        page_b = self.new_principal(SECOND_USER, env_key(self.args.env_file, SECOND_PASS_KEY))
        page_b.click("[data-testid=nav-chat]")
        page_b.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
        saved_page, saved_context = self.page, self.context
        self.page, self.context = page_b, page_b.context
        self.state["mid_shot_slot"] = None
        readings = self.ask(self.state.get("ring5_question") or self.question(self.args.question),
                            approve_in_chat=False)
        shots = [self.shot("r694-r6-principal-b-chat.png")]
        visible = page_b.evaluate(
            "() => Array.from(document.querySelectorAll('[data-testid=source-card] .source-name,"
            " [data-testid=source-card] .src-name, [data-testid=source-card]'))"
            ".map(e => (e.textContent || '').trim().slice(0, 80)).slice(0, 20)"
        )
        restricted = page_b.evaluate(
            "() => { const n = document.querySelector('[data-testid=documents-restricted]');"
            " return n ? n.textContent.trim() : null; }"
        )
        catalog = self.api("/documents/catalog")
        body = catalog["body"] if isinstance(catalog["body"], dict) else {}
        readings["source_names_visible"] = visible
        readings["restricted_face"] = restricted
        readings["catalog_status"] = catalog["status"]
        readings["catalog_visible_count"] = len(body.get("documents") or [])
        readings["catalog_restricted"] = body.get("restricted")
        readings["principal_b_user"] = SECOND_USER
        readings["principal_b_role"] = page_b.evaluate("() => localStorage.getItem('eb_role')")
        readings["principal_b_department"] = page_b.evaluate("() => localStorage.getItem('eb_department')")
        readings["principal_a_sources"] = primary_sources
        primary_catalog = saved_page.evaluate(
            """async () => {
                const token = localStorage.getItem('eb_token') || '';
                const r = await fetch('/api/v1/documents/catalog', { headers: { Authorization: 'Bearer ' + token } });
                const b = await r.json().catch(() => ({}));
                return (b.documents || []).length;
            }"""
        )
        readings["principal_a_catalog_count"] = primary_catalog
        same_answer = readings["answer_chars_from_frames"] == self.state.get("ring5_answer_chars")
        readings["answer_identical_to_principal_a"] = same_answer
        status = (
            "达"
            if primary_sources is not None
            and readings["catalog_visible_count"] != primary_catalog
            else "未达"
        )
        note = (
            "两枚身份的可见集枚数已对照；生产库 department/classification 全空那一格不由本环翻绿，"
            "合成标签也不作为本环凭据。"
        )
        self.page, self.context = saved_page, saved_context
        page_b.context.close()
        self.finish(6, "权限隔离", status, readings, shots, note)

    # -------------------------------------------------------------- 环 7-9 共用
    def pending_rows(self) -> list[str]:
        """审批屏那一列待批的行文本，逐枚取回来，用来定位「生成图表」「导出报告」。"""
        return [t.replace("\n", " | ")
                for t in self.page.locator("[data-testid=hitl-row]").all_inner_texts()]

    def decide_parked(self, keyword: Any, action: str = "approve",
                      settle_s: float = PENDING_SETTLE_S,
                      decide_s: float = DECIDE_WAIT_S) -> dict[str, Any]:
        """在审批屏里按名字批准或驳回那一枚待批，并取决策前后两态。

        keyword 允许给一串候选：屏上挂的是「生成图表」还是「导出报告」由模型那一轮决定，
        按名册依次匹配，命中哪一枚就记在 matched_keyword 那一格。
        """
        page = self.page
        assert page is not None
        self.open_screen("nav-approval", "hitl-pending")
        rows = page.locator("[data-testid=hitl-row]")
        if not wait_for(lambda: rows.count() > 0, settle_s, poll_s=1.0):
            if page.locator("[data-testid=hitl-reload]").count():
                page.click("[data-testid=hitl-reload]")
                wait_for(lambda: rows.count() > 0, settle_s, poll_s=1.0)
        texts = self.pending_rows()
        names = [keyword] if isinstance(keyword, str) else list(keyword)
        index = None
        matched = None
        for name in names:
            index = next((i for i, t in enumerate(texts) if name in t), None)
            if index is not None:
                matched = name
                break
        out: dict[str, Any] = {
            "keyword": keyword,
            "keyword_candidates": names,
            "matched_keyword": matched,
            "action": action,
            "pending_rows_before": len(texts),
            "pending_row_texts_before": [t[:220] for t in texts],
            "matched_index": index,
        }
        if index is None:
            out["decided"] = False
            return out
        testid = "hitl-approve" if action == "approve" else "hitl-reject"
        button = rows.nth(index).locator("[data-testid=%s]" % testid)
        out["button_present"] = button.count()
        server_before = self.pending_api()
        before = rows.count()
        decided_at = epoch()
        button.first.click()
        left = wait_for(lambda: self.pending_api()["count"] < server_before["count"], decide_s, poll_s=1.0)
        if page.locator("[data-testid=hitl-reload]").count():
            page.click("[data-testid=hitl-reload]")
            wait_for(lambda: rows.count() < before, 15.0, poll_s=1.0)
        out.update({
            "decided": True,
            "row_left_pending": bool(left),
            "server_pending_before": server_before,
            "server_pending_after": self.pending_api(),
            "decide_wait_s": seconds_since(decided_at),
            "pending_rows_after": rows.count(),
            "pending_row_texts_after": [t[:220] for t in self.pending_rows()],
            "outcome_faces_after": [t.replace("\n", " | ")[:200] for t in
                                    page.locator("[data-testid=hitl-outcome]").all_inner_texts()],
            "outcome_codes": page.locator("[data-testid=hitl-outcome-code]").all_inner_texts(),
        })
        return out

    def pending_api(self) -> dict[str, Any]:
        """服务端那本待批账：面板列的是它，屏上没刷新不等于服务端没落地。"""
        api = self.api("/hitl/pending?limit=50")
        body = api["body"] if isinstance(api["body"], dict) else {}
        rows = [r for r in (body.get("items") or body.get("pending") or []) if isinstance(r, dict)]
        return {"http_status": api["status"],
                "count": len(rows),
                "faces": [str(r.get("title") or r.get("step") or r.get("action") or "")[:60] for r in rows],
                "request_ids": [str(r.get("request_id") or "") for r in rows],
                "keys": sorted(rows[0].keys()) if rows else []}

    def artifacts(self) -> dict[str, Any]:
        api = self.api("/artifacts?limit=50")
        body = api["body"] if isinstance(api["body"], dict) else {}
        return {"http_status": api["status"], "total": body.get("total"),
                "rows": (body.get("artifacts") or [])[:10]}

    def fetch_piece(self, url: str) -> dict[str, Any]:
        """带着产品自己的 token 取一次产物字节——判「导出件字节数 >0」用的是这条腿。"""
        return self.page.evaluate(
            """async (u) => {
                const token = localStorage.getItem('eb_token') || '';
                const r = await fetch(u, { headers: { Authorization: 'Bearer ' + token } });
                const buf = new Uint8Array(await r.arrayBuffer());
                const magic = Array.from(buf.slice(0, 8)).map(b => b.toString(16).padStart(2, '0')).join('');
                return { status: r.status, bytes: buf.length, magic_hex8: magic,
                         content_type: r.headers.get('content-type') };
            }""",
            url)

    def wait_for_artifact(self, kinds: tuple[str, ...],
                          timeout_s: float = ARTIFACT_WAIT_S) -> dict[str, Any]:
        """等那一枚产物登记上来：只认 artifact_type，不靠屏上写了什么字。"""
        started = epoch()
        arts: dict[str, Any] = {}
        while True:
            arts = self.artifacts()
            hits = [r for r in arts["rows"]
                    if str(r.get("artifact_type") or "").lower() in kinds]
            if hits:
                return {"found": True, "wait_s": seconds_since(started), "newest": hits[0],
                        "total": arts["total"], "http_status": arts["http_status"]}
            if time.time() - started > timeout_s:
                return {"found": False, "wait_s": seconds_since(started), "newest": None,
                        "total": arts["total"], "http_status": arts["http_status"]}
            time.sleep(2.0)

    def artifact_leg_error(self) -> list[str] | None:
        """从后端日志里现读那一行产物登记失败的读数——只读，不改任何东西。"""
        proc = subprocess.run(
            ["docker", "logs", "--since", "%dm" % LOG_LOOKBACK_MIN, "enterprise-brain-backend-1"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        blob = (proc.stdout or "") + (proc.stderr or "")
        marks = ("报告生成失败", "图表生成失败", "artifact creation denied", "完成 status=failed")
        hits = [ln.strip()[:300] for ln in blob.splitlines() if any(w in ln for w in marks)]
        return hits[-3:] or None

    def container_newest_export(self) -> dict[str, Any]:
        """容器里 static/exports 最新一枚 PDF 的文件名与字节数（盘上态，与 API 态分开记）。"""
        proc = subprocess.run(
            ["docker", "exec", "enterprise-brain-backend-1", "sh", "-c",
             "cd /app/static/exports && ls -t | head -1 | xargs -I{} stat -c '%n %s %y' {}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        line = (proc.stdout or "").strip()
        if not line:
            return {"readable": False, "raw": (proc.stderr or "").strip()[:200]}
        parts = line.split()
        return {"readable": True, "path": parts[0], "bytes": int(parts[1]) if len(parts) > 1 else None,
                "mtime": " ".join(parts[2:5])}

    def chart_ask(self, page: Page) -> dict[str, Any]:
        """在给定那一屏上用真键盘问一句要图的，只报提问有没有送出去与屏上读数。"""
        try:
            if page.locator("#chat-lane-select").count():
                page.select_option("#chat-lane-select", label="分析档")
        except Exception as exc:  # noqa: BLE001 - 档位旋钮在另一枚身份下可能不给
            return {"asked": False, "blocked_reason": "档位选不中: %s" % exc}
        self._pick_table(page, self.args.data_table)
        field = page.locator("[data-testid=chat-input]")
        if not wait_for(lambda: field.count() > 0 and field.first.is_enabled(), 90.0, poll_s=1.0):
            return {"asked": False, "blocked_reason": "输入框 90 s 内没松开（上一发仍在飞）"}
        page.click("[data-testid=chat-input]")
        page.keyboard.type(self.args.analysis_question, delay=18)
        page.evaluate("() => { window.__r694.streams.length = 0; }")
        page.click("[data-testid=chat-send]")
        started = epoch()
        deadline = started + ANSWER_TIMEOUT_S
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = page.evaluate(BUBBLE_PROBE)
            closed = page.evaluate("() => window.__r694.streams.map(s => s.closed)")
            frames = page.evaluate("() => window.__r694.streams.reduce((n, s) => n + s.frames.length, 0)")
            if closed and all(closed) and (frames >= 2 or last["chars"] > 0 or last["hitlCard"]):
                break
            time.sleep(SAMPLE_S)
        reloaded = False
        if not page.locator(".msg-row").count():
            page.reload(wait_until="load")
            page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            page.wait_for_timeout(1500)
            reloaded = True
        screen = page.evaluate(BUBBLE_PROBE)
        return {"asked": True, "wait_s": seconds_since(started),
                "live_rows": page.locator(".msg-row").count(),
                "reloaded_to_read_screen": reloaded,
                "live_chars": last.get("chars"),
                "screen_chars": screen["chars"],
                "screen_steps": screen["steps"],
                "screen_faces": screen["faces"],
                "screen_tail": page.evaluate(
                    "() => { const b = document.querySelectorAll('.msg-bubble-wrap');"
                    " return b.length ? b[b.length-1].innerText.slice(-400) : ''; }").replace("\n", " | "),
                "hitl_card_in_chat": page.locator("[data-testid=hitl-approve-chat]").count()}

    def read_audit_screen(self) -> dict[str, Any]:
        """进「审计事件」面读那一格：计数与头几行的原文，屏上读数不是散文。"""
        self.open_screen("nav-audit-events", "audit-panel")
        probe = self.page.evaluate(
            """() => {
                const grab = (t) => { const n = document.querySelector('[data-testid=' + t + ']');
                                      return n ? n.innerText.trim().slice(0, 160) : null; };
                const rows = Array.from(document.querySelectorAll('[data-testid=audit-events-table] tbody tr'));
                return {
                    face: (document.querySelector('[data-testid=audit-panel]') || {}).dataset?.face || null,
                    event_count: grab('audit-event-count'),
                    events_total: grab('audit-events-total'),
                    recorded_total: grab('audit-recorded-total'),
                    truncated: grab('audit-truncated'),
                    order_text: grab('audit-order'),
                    empty_face: grab('audit-empty'),
                    failure: grab('audit-failure'),
                    row_texts: rows.slice(0, 5).map(r => r.innerText.split(String.fromCharCode(10)).join(' | ').slice(0, 200)),
                    row_count: rows.length,
                };
            }"""
        )
        probe["rows_read"] = probe["row_count"]
        return probe

    def ring7(self) -> None:
        """环 7 数据分析：真键盘问一句要图的，批掉挂起的「生成图表」，再读图与产物登记。"""
        self.ensure_login()
        self.open_screen("nav-chat", "chat-panel")
        self.state["mid_shot_slot"] = "r7"
        readings = self.ask(self.args.analysis_question, approve_in_chat=True,
                            table=self.args.data_table, lane="分析档")
        shots = [r for r in [readings.pop("mid_shot")] if r]
        shots.append(self.shot("r694-r7-analysis-parked.png"))
        readings["table_choice"] = self.state.get("table_choice")
        readings["artifacts_before"] = self.artifacts()
        if readings["hitl"].get("hitl_seen_before_decision"):
            readings["decision"] = {"face": "对话里的批准牌", "clicked": True,
                                    "resumed_tail": readings["hitl"].get("resumed_samples", [])[-3:]}
        else:
            readings["decision"] = self.decide_parked("生成图表", "approve")
        shots.append(self.shot("r694-r7-approval-face.png"))
        chart = self.wait_for_artifact(("chart", "image"))
        readings["chart_artifact"] = chart
        if chart["found"]:
            url = chart["newest"].get("content_url") or chart["newest"].get("download_url")
            readings["chart_piece"] = self.fetch_piece(url)
            readings["chart_piece_url"] = url
        after = self.read_chat_screen()
        readings["after_approve"] = after
        shots.append(self.shot("r694-r7-chart-face.png"))
        readings["artifact_leg_error"] = self.artifact_leg_error()
        readings["department_probe"] = self.department_probe()
        status = "达" if (chart["found"] or after["charts_on_screen"]) else "未达"
        note = (
            "出图那一枚批准先在对话里找牌（hitl-approve-chat），拿不到就走审批屏；两态分开记。"
            if status == "达" else
            "未达差在「图能出」那半条：图登记这一腿交回的读数记在 artifact_leg_error，"
            "对照读数记在 department_probe（同一句问话、一枚部门非空的账号）。"
        )
        self.finish(7, "数据分析", status, readings, shots, note)

    def department_probe(self) -> dict[str, Any]:
        """差分探针：同一句要图的话，换一枚「部门非空」的账号再问一次，只比产物登记这一腿。"""
        saved_page, saved_context = self.page, self.context
        try:
            page_b = self.new_principal(SECOND_USER, env_key(self.args.env_file, SECOND_PASS_KEY))
            self.page, self.context = page_b, page_b.context
            self.open_screen("nav-chat", "chat-panel")
            out: dict[str, Any] = {"user": SECOND_USER, "ask": self.chart_ask(page_b)}
            hitl = page_b.locator("[data-testid=hitl-approve-chat]")
            if hitl.count():
                out["decision_face"] = "对话里的批准牌"
                hitl.first.click()
                wait_for(lambda: page_b.locator("[data-testid=hitl-approve-chat]").count() == 0,
                         DECIDE_WAIT_S, poll_s=1.0)
            else:
                out["decision_face"] = "审批屏"
                out["decision"] = self.decide_parked("生成图表", "approve")
            chart = self.wait_for_artifact(("chart", "image"))
            out["chart_artifact"] = {k: v for k, v in chart.items() if k != "newest"}
            if chart["found"]:
                row = chart["newest"]
                out["chart_row"] = {k: row.get(k) for k in
                                    ("artifact_id", "artifact_type", "filename", "owner_id",
                                     "department_ids", "classification", "created_at")}
                url = row.get("content_url") or row.get("download_url")
                out["chart_piece"] = self.fetch_piece(url)
            register_shot(page_b, self.out, "r694-r7b-department-account.png")
            out["shot"] = "r694-r7b-department-account.png"
            return out
        finally:
            self.page, self.context = saved_page, saved_context
            page_b.context.close()

    def ring8(self) -> None:
        """环 8 报告导出：报告档问一句，批掉「导出报告」，取导出件字节数（API 腿与盘上腿分开记）。"""
        self.ensure_login()
        self.open_screen("nav-chat", "chat-panel")
        self.state["mid_shot_slot"] = "r8"
        readings = self.ask(self.args.report_question, approve_in_chat=False,
                            table=self.args.data_table, lane="报告档")
        shots = [r for r in [readings.pop("mid_shot")] if r]
        shots.append(self.shot("r694-r8-report-parked.png"))
        readings["table_choice"] = self.state.get("table_choice")
        readings["artifacts_before"] = self.artifacts()
        readings["decision"] = self.decide_parked("导出报告", "approve")
        shots.append(self.shot("r694-r8-approval-face.png"))
        report = self.wait_for_artifact(("report", "document", "export", "pdf"))
        readings["report_artifact"] = report
        exported = None
        if report["found"]:
            row = report["newest"]
            url = row.get("download_url") or row.get("content_url")
            exported = {"artifact_id": row.get("artifact_id"), "filename": row.get("filename"),
                        "url": url, **self.fetch_piece(url)}
        readings["exported_piece"] = exported
        readings["artifact_rows_after"] = self.artifacts()["rows"]
        readings["disk_newest_pdf"] = self.container_newest_export()
        readings["artifact_leg_error"] = self.artifact_leg_error()
        after = self.read_chat_screen()
        readings["after_approve"] = after
        shots.append(self.shot("r694-r8-report-face.png"))
        status = "达" if (exported and exported["bytes"] > 0 and exported["status"] == 200) else "未达"
        note = (
            "导出件字节数走的是浏览器里那枚带 token 的 GET；盘上最新一枚 PDF 另记在 disk_newest_pdf，"
            "两态不许并成一格。" if status == "达" else
            "未达差在「导出件可查回」这一条：文件已在容器盘上落出来，但产物登记那一腿交回的是 "
            "artifact_leg_error 那一行读数，所以 /api/v1/artifacts 里零枚在册。"
        )
        self.finish(8, "报告导出", status, readings, shots, note)

    def ring9(self) -> None:
        """环 9 HITL／审计：再挂一枚待批，先按驳回取两态，再读审计事件面。"""
        self.ensure_login()
        self.open_screen("nav-chat", "chat-panel")
        # 上一发的回答还挂着时输入框不松开，这一环要的是自己那一枚待批，先另开一枚会话。
        opened = {"clicked": False, "testid": "new-session"}
        if self.page.locator("[data-testid=new-session]").count():
            self.page.click("[data-testid=new-session]")
            self.page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            self.page.wait_for_timeout(1200)
            opened = {"clicked": True, "testid": "new-session",
                      "screen_name": self.page.locator("[data-testid=chat-screen-name]").count()}
        readings_open = opened
        self.state["mid_shot_slot"] = "r9"
        ask = self.ask(self.args.analysis_question, approve_in_chat=False,
                       table=self.args.data_table, lane="分析档")
        readings: dict[str, Any] = {
            "fresh_session": readings_open,
            "parked_question": ask["question"],
            "parked_asked": ask["asked"],
            "parked_blocked_reason": ask.get("blocked_reason"),
            "parked_blocked_probe": ask.get("blocked_probe"),
            "parked_elapsed_s": ask.get("elapsed_s"),
            "hitl_in_chat": ask.get("hitl"),
            "artifacts_before": self.artifacts(),
        }
        shots = [r for r in [ask.pop("mid_shot")] if r]
        readings["rejection"] = self.decide_parked(["生成图表", "导出报告"], "reject")
        shots.append(self.shot("r694-r9-hitl-rejected.png"))
        readings["approval_screen_after_reject"] = self.approve_pending(click=False)
        readings["audit"] = self.read_audit_screen()
        shots.append(self.shot("r694-r9-audit-events.png"))
        readings["after_reject"] = self.read_chat_screen()
        rej = readings["rejection"]
        status = "达" if (
            rej["pending_rows_before"] > 0 and rej["decided"]
            and rej["row_left_pending"] and rej["pending_rows_after"] < rej["pending_rows_before"]
        ) else "未达"
        note = (
            "批准那一腿的凭据在环 7 与环 8（各自批掉自己挂起的那一枚）；这一环补的是驳回那一腿与审计面。"
            if status == "达" else
            "未达差在「待批准那一条能出现并可批准或驳回」：驳回点下去了但那一行没从待批列里退出来，"
            "读数记在 rejection 那一格。"
        )
        self.finish(9, "HITL／审计", status, readings, shots, note)

def _ordered(items: Any) -> list[Any]:
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _row_is_retrievable(text: str) -> bool:
    return "已可检索" in (text or "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R694 前端九环走查驱动")
    parser.add_argument("--base-url", default="http://localhost/")
    parser.add_argument("--env-file", required=True, help="deploy/.env.server 的路径（按键名取值，值不落纸）")
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    parser.add_argument("--rings", default="1,2,3,4,5,6,7,8,9")
    parser.add_argument("--fixture", default="docs/testing/rehearse-run6-summary.txt")
    parser.add_argument("--fixture-name", default="")
    parser.add_argument("--question", default="费用报销需要经过哪些审批环节？")
    parser.add_argument("--analysis-question", default="按月份统计报销金额，并画一张柱状图")
    parser.add_argument("--report-question", default="请生成一份 2026 年上半年经营情况分析报告，并导出成报告文件")
    parser.add_argument("--data-table", default="报销")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="起手清空账本再跑：正式那一遍必须只装这一遍的读数，不留上一笔的旧环",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fixture = Path(args.fixture)
    if not fixture.is_absolute():
        fixture = Path(__file__).resolve().parents[1] / args.fixture
    args.fixture = str(fixture)
    rings = [int(x) for x in args.rings.split(",") if x.strip()]
    methods = {
        1: "ring1", 2: "ring2", 3: "ring3", 4: "ring4", 5: "ring5",
        6: "ring6", 7: "ring7", 8: "ring8", 9: "ring9",
    }
    with Walk(args) as walk:
        for ring in rings:
            getattr(walk, methods[ring])()
        walk.ledger.set_root("finished_at", stamp())
    print(json.dumps({"rings": rings, "out": str(Path(args.out))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
