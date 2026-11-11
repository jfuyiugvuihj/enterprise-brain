"""R694 · 两张失败脸：只用一次性容器注入，拍屏上那一句人话，拍完把栈交回去。

禁区照本单：不改产品码、不改宿主 env 文件、不动常驻 backend／frontend 容器、
不 rebuild、不 recreate。注入手段只有三件——
① 一枚临时 backend（compose ``run``，配置从覆盖文件来，覆盖文件写在盘外临时目录）；
② 一枚临时 frontend（``docker run`` 挂一份只改上游那一行的 nginx conf）；
③ 一枚假 Ollama 门面（``scripts/r694_fake_ollama.py``，只改算力读数）。
所有临时容器都带 ``--rm``，收尾用 ``docker stop``，并把 ``docker ps -a`` 与 ``docker ps``
的差集现读进账本，作为「机器交回去时是干净的」那一枚凭据。
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from r694_common import Ledger, env_key, epoch, register_shot, seconds_since, stamp, wait_for  # noqa: E402
from r694_walkthrough import PRIMARY_PASS_KEY, PRIMARY_USER_KEY, SECOND_PASS_KEY, SECOND_USER, SSE_TAP  # noqa: E402

UI_HOST = "127.0.0.1"
POSTURE_LOG_MARKER = "R673 GPU 姿势声明"

#: 两种姿势各自具名：``app/common/model_capabilities.py::POSTURE_DECLARATION_REQUIRE_GPU``
#: 与同件里的 ``::POSTURE_DECLARATION_FAIL_OPEN``，日志里点名的词按档位取。
POSTURE_WORDS: dict[str, str] = {
    "gpu-hard": "posture=require_gpu",
    "gpu-failopen": "posture=fail_open",
}
#: 探针结论那两句：``::HARD_REFUSAL_DECLARATION`` 与 ``::CPU_LEG_DECLARATION``。
DECLARATION_WORDS = ("R673 硬门触发", "R673 确证 CPU 腿")

#: 四枚注入案的写集：每条只写临时 backend 的 env，宿主 env 文件与常驻 backend 一律不动。
#: 算力探针读 ``LOCAL_MODEL_BASE_URL``（``app/common/model_config.py::_cached_discovery`` 那一路），
#: embedding 调用读 ``OLLAMA_BASE_URL``（``app/rag/retriever.py`` 那一路）：两枚键各管一条腿。
INJECTIONS: dict[str, dict[str, Any]] = {
    "embedding": {
        "fake": True, "break_embeddings": True, "passthrough_ps": True,
        "ollama_base": "fake", "local_model_base": False, "env": {},
        "note": "只掐 /api/embeddings（假门面交回 503），/api/tags 与 /api/ps 原样转发：算力档保持真",
    },
    "embedding-unreachable": {
        "fake": False, "break_embeddings": False, "passthrough_ps": False,
        "ollama_base": "http://127.0.0.1:1", "local_model_base": False, "env": {},
        "note": "OLLAMA_BASE_URL 指到没人听的端口：embedding 与 registry 两条腿一起不可达",
    },
    "gpu-hard": {
        "fake": True, "break_embeddings": False, "passthrough_ps": False,
        "ollama_base": "fake", "local_model_base": True, "unset_configured_model": True,
        "env": {"OLLAMA_REQUIRE_GPU": "1"},
        "note": "假 /api/ps 报 cpu 且不给 size_vram，硬门在位（R673 require_gpu 那一档）；"
                "另在临时 backend 里把 LOCAL_MODEL_NAME／OLLAMA_MODEL 撤成空值，"
                "逼 app/common/model_config.py::get_local_model_settings 走 discovered 那一腿",
    },
    "gpu-failopen": {
        "fake": True, "break_embeddings": False, "passthrough_ps": False,
        "ollama_base": "fake", "local_model_base": True, "unset_configured_model": True,
        "env": {"OLLAMA_REQUIRE_GPU": ""},
        "note": "同一枚假读数，撤掉硬门（R673 fail_open 那一档）；撤键同上",
    },
}
PROBLEMS_JS = """
async () => {
  const token = localStorage.getItem('eb_token') || '';
  const read = async (p) => {
    const r = await fetch(p, { headers: { Authorization: 'Bearer ' + token } });
    return { status: r.status, body: await r.json().catch(() => null) };
  };
  const details = await read('/api/v1/health/details');
  const b = details.body || {};
  const model = b.model || {};
  return {
    http_status: details.status,
    status: b.status,
    problems: b.problems,
    model_keys: Object.keys(model).sort(),
    model_name: model.name,
    model_source: model.source,
    embedding: b.embedding ?? model.embedding ?? null,
    inference_compute: model.inference_compute ?? b.inference_compute ?? null,
    dependencies_ollama: (b.dependencies || {}).ollama ?? null,
  };
}
"""

#: 屏上那张失败脸：顶栏那枚状态、面板里的提示条、runtime-face 那几张牌，全按名字取回。
FACES_JS = """
() => {
  const text = (sel) => { const n = document.querySelector(sel); return n ? n.innerText.trim() : null; };
  const many = (sel) => Array.from(document.querySelectorAll(sel)).map((n) => n.innerText.trim());
  const banners = {};
  for (const n of document.querySelectorAll('[data-testid]')) {
    const k = n.getAttribute('data-testid');
    if (k.indexOf('degradation-banner') === 0) banners[k] = n.innerText.trim().slice(0, 400);
  }
  return {
    model_status: text('[data-testid=model-status]'),
    model_degraded_notice: text('[data-testid=model-degraded-notice]'),
    runtime_faces: many('[data-testid=runtime-face]'),
    runtime_faces_wrap: many('[data-testid=runtime-faces]'),
    degradation_banners: banners,
    session_body_fault: text('[data-testid=session-body-fault]'),
    answer_headline: text('[data-testid=r48-headline-card]'),
    chat_note: text('[data-testid=chat-note]'),
    error_events: many('[data-testid=chat-error], .msg-error'),
    ui_error_state: text('[data-testid=ui-error-state]'),
    ui_error_state_code: text('[data-testid=ui-error-state-code]'),
    ui_error_code: text('[data-testid=ui-error-code]'),
    degradation_banner_title: text('[data-testid=degradation-banner-title]'),
    degradation_banner_faces: many('[data-testid=degradation-banner-face]'),
    login_error: text('[data-testid=login-error]'),
    hitl_cards: document.querySelectorAll('[data-testid=hitl-approve-chat]').length,
    last_bubble_tail: (() => {
      const bs = Array.from(document.querySelectorAll('.msg-bubble-wrap'));
      const last = bs[bs.length - 1];
      const c = last ? ((last.querySelector('.msg-content') || {}).textContent || '') : '';
      return c.slice(-320);
    })(),
  };
}
"""


def sh(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """跑一条 docker 命令：命令里不含任何口令明文（env 文件只按路径传给 compose）。"""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)


def docker_names(all_containers: bool = False) -> list[str]:
    cmd = ["docker", "ps"] + (["--all"] if all_containers else []) + ["--format", "{{.Names}}"]
    out = sh(cmd)
    return sorted(x for x in (out.stdout or "").splitlines() if x.strip())


class Faces:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.temp = Path(args.temp_dir)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.out / "ledger.json")
        self.owned: list[str] = []
        self.case_seq = 0
        self.own_files: list[Path] = []

    # ------------------------------------------------------------------ 注入件
    def write_nginx_conf(self, case: str, backend_name: str) -> Path:
        source = Path(self.args.nginx_conf)
        conf = source.read_text(encoding="utf-8")
        target = self.temp / ("nginx-%s.conf" % case)
        changed = 0
        kept: list[str] = []
        for line in conf.splitlines():
            if line.strip().startswith("set $enterprise_brain_api"):
                kept.append("    set $enterprise_brain_api http://%s:8001;" % backend_name)
                changed += 1
            else:
                kept.append(line)
        if changed != 1:
            raise RuntimeError("nginx 片段里那枚上游变量命中 %s 次，不是 1 次" % changed)
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
        self.own_files.append(target)
        return target

    def write_override(self, case: str, backend_name: str, extra_env: dict[str, str]) -> Path:
        target = self.temp / ("override-%s.yml" % case)
        lines = ["services:", "  backend:", "    environment:"]
        for key, value in extra_env.items():
            lines.append("      %s: \"%s\"" % (key, value))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.own_files.append(target)
        return target

    def start_backend(self, override: Path, name: str) -> dict[str, Any]:
        cmd = [
            "docker", "compose",
            "--project-directory", self.args.compose_dir,
            "--env-file", self.args.env_file,
            "-f", str(Path(self.args.compose_dir) / "docker-compose.yml"),
            "-f", str(override),
            "run", "-d", "--rm", "--no-deps", "--name", name, "backend",
        ]
        started = epoch()
        proc = sh(cmd)
        self.owned.append(name)
        return {"command_rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-400:],
                "started_at": stamp(), "start_elapsed_s": seconds_since(started)}

    def start_frontend(self, conf: Path, name: str, host_port: int) -> dict[str, Any]:
        cmd = [
            "docker", "run", "-d", "--rm", "--name", name,
            "--network", self.args.network,
            "-p", "%s:%d:80" % (UI_HOST, host_port),
            "-v", "%s:/etc/nginx/conf.d/default.conf:ro" % conf,
            self.args.frontend_image,
        ]
        proc = sh(cmd)
        self.owned.append(name)
        return {"command_rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-400:]}

    def start_fake_ollama(self, name: str, break_embeddings: bool = False,
                          passthrough_ps: bool = False) -> dict[str, Any]:
        script = ROOT / "scripts" / "r694_fake_ollama.py"
        cmd = [
            "docker", "run", "-d", "--rm", "--name", name,
            "--network", self.args.network,
            "--entrypoint", "python",
            "-v", "%s:/r694_fake_ollama.py:ro" % script,
        ]
        if break_embeddings:
            cmd += ["-e", "R694_BREAK_EMBEDDINGS=1"]
        if passthrough_ps:
            cmd += ["-e", "R694_PASSTHROUGH_PS=1"]
        cmd += [self.args.backend_image, "/r694_fake_ollama.py"]
        proc = sh(cmd)
        self.owned.append(name)
        return {"command_rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-400:]}

    #: 后端日志里要点名的词：GPU 姿势声明、embedding 那一腿的失败词、降级与不可达词。
    LOG_WORDS = ("embedding", "EmbeddingUnavailable", "不可用", "降级",
                 "unavailable", "timed out", "Connection refused", "503")

    def logs(self, name: str, marker: str | None = None,
             extra_markers: tuple[str, ...] = ()) -> dict[str, Any]:
        proc = sh(["docker", "logs", name])
        blob = (proc.stdout or "") + (proc.stderr or "")
        rows = [ln.strip() for ln in blob.splitlines() if ln.strip()]
        marker_lines = [ln for ln in rows if marker and marker in ln]
        secondary = {
            word: {"count": sum(1 for ln in rows if word in ln),
                   "lines": [ln[:400] for ln in rows if word in ln][:4]}
            for word in extra_markers
        }
        hits: list[str] = []
        for word in self.LOG_WORDS:
            for ln in rows:
                if word.lower() in ln.lower() and ln[:300] not in hits:
                    hits.append(ln[:300])
        return {"marker": marker, "marker_lines": marker_lines[:6],
                "secondary_markers": secondary,
                "marker_line_count": len(marker_lines),
                "lines": hits[:14], "line_count": len(hits),
                "tail": rows[-10:], "log_lines_total": len(rows),
                "log_bytes": len(blob.encode("utf-8"))}

    # -------------------------------------------------------------------- 取屏
    def shoot(self, case: str, origin: str, shot_name: str, ask_question: str) -> dict[str, Any]:
        if ask_question:
            # 缓存按整句问话命中，缓存那一发根本不碰检索与 embedding 腿——本轮编号把它隔开。
            ask_question = "%s（脸编 %s）" % (ask_question, time.strftime("%H%M%S"))
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.add_init_script(SSE_TAP)
            page = context.new_page()
            page.goto(origin, wait_until="load")
            page.wait_for_selector("[data-testid=login-page]", timeout=25000)
            page.fill("[data-testid=login-username]", env_key(self.args.env_file, PRIMARY_USER_KEY))
            page.fill("[data-testid=login-password]", env_key(self.args.env_file, PRIMARY_PASS_KEY))
            page.click("[data-testid=login-submit]")
            page.wait_for_selector("[data-testid=sidebar]", timeout=30000)
            page.click("[data-testid=nav-chat]")
            page.wait_for_selector("[data-testid=chat-panel]", timeout=20000)
            page.wait_for_timeout(3000)
            health = page.evaluate(PROBLEMS_JS)
            faces_before = page.evaluate(FACES_JS)
            asked = None
            if ask_question:
                page.click("[data-testid=chat-input]")
                page.keyboard.type(ask_question, delay=18)
                asked_at = epoch()
                page.click("[data-testid=chat-send]")
                deadline = asked_at + self.args.ask_timeout_s
                frames: list[dict[str, Any]] = []
                while time.time() < deadline:
                    frames = page.evaluate(
                        "() => window.__r694.streams.map(s => ({closed: s.closed,"
                        " frames: s.frames.map(f => f.event)})).flatMap(x => x.frames)"
                    )
                    if any(name == "error" for name in frames):
                        break
                    if page.locator("[data-testid=session-body-fault]").count():
                        break
                    if any(name == "done" for name in frames):
                        break
                    time.sleep(0.4)
                asked = {
                    "question": ask_question,
                    "asked_at": stamp(),
                    "elapsed_s": seconds_since(asked_at),
                    "event_names": frames,
                    "error_text_on_screen": page.evaluate(FACES_JS)["error_events"],
                }
                page.wait_for_timeout(800)
            faces_after = page.evaluate(FACES_JS)
            shot = register_shot(page, self.out, shot_name)
            context.close()
            browser.close()
            return {"health_details": health, "faces_before_ask": faces_before,
                    "faces_after_ask": faces_after, "ask": asked, "shot": shot}

    @staticmethod
    def face_verdict(entry: dict[str, Any]) -> dict[str, Any]:
        """屏上给出人话的失败面才算达：状态牌变了、提示条在位、错误串在位，任一命中即记名。

        判据原文是「UI 必须给出人话的失败面，不是转圈或白屏」，所以这里不认「图拍到了」，
        只认屏上那几枚具名读数；命中哪几枚就逐枚写进 hits。
        """
        before = entry.get("faces_before_ask") or {}
        after = entry.get("faces_after_ask") or {}
        ask = entry.get("ask") or {}
        hits: list[str] = []
        if after.get("model_status") and after.get("model_status") != before.get("model_status"):
            hits.append("model_status：%s → %s" % (before.get("model_status"), after.get("model_status")))
        for key in ("model_degraded_notice", "session_body_fault", "answer_headline", "chat_note"):
            if after.get(key):
                hits.append("%s：%s" % (key, str(after[key])[:200]))
        for key in ("runtime_faces", "runtime_faces_wrap", "error_events"):
            if after.get(key):
                hits.append("%s：%s" % (key, " | ".join(str(v)[:200] for v in after[key])))
        if after.get("degradation_banners"):
            hits.append("degradation_banners：%s" % json.dumps(
                after["degradation_banners"], ensure_ascii=False)[:400])
        if ask.get("error_text_on_screen"):
            hits.append("ask_error_text：%s" % str(ask["error_text_on_screen"])[:200])
        if "error" in (ask.get("event_names") or []):
            hits.append("sse_error_event：1 枚")
        screen = after.get("model_status") or ""
        white = not after and not ask.get("event_names")
        return {"hits": hits, "hit_count": len(hits), "blank_screen": bool(white),
                "model_status_after": screen,
                "degraded_banner_count": len(after.get("degradation_banners") or {})}

    # -------------------------------------------------------------------- 单案
    def run_case(self, case: str) -> dict[str, Any]:
        backend_name = "r694-%s" % case
        ui_name = "r694-ui-%s" % case
        self.case_seq += 1
        host_port = self.args.base_port + self.case_seq
        extra_env: dict[str, str] = {}
        fake_started: dict[str, Any] | None = None
        marker: str | None = None
        injection = INJECTIONS[case]
        if injection["fake"]:
            fake_name = "r694-fake-%s" % case
            fake_started = self.start_fake_ollama(
                fake_name, break_embeddings=injection["break_embeddings"],
                passthrough_ps=injection["passthrough_ps"])
            fake_started["fake_name"] = fake_name
            fake_started["in_container_probe"] = self._probe_inside(
                fake_name, "http://127.0.0.1:11434/api/ps")
            fake_started["embeddings_probe"] = self._probe_inside(
                fake_name, "http://127.0.0.1:11434/api/embeddings")
            if injection["ollama_base"] == "fake":
                extra_env["OLLAMA_BASE_URL"] = "http://%s:11434" % fake_name
            if injection["local_model_base"]:
                extra_env["LOCAL_MODEL_BASE_URL"] = "http://%s:11434/v1" % fake_name
        elif injection["ollama_base"]:
            extra_env["OLLAMA_BASE_URL"] = injection["ollama_base"]
        if injection.get("unset_configured_model"):
            #: 宿主 env 里 LOCAL_MODEL_NAME 有值 ⇒ get_local_model_settings 直接走 configured 那一腿，
            #: 不做发现、不架算力探针，R673 的姿势声明因此永远不会落到日志上。撤成空值才摸得到探针。
            extra_env["LOCAL_MODEL_NAME"] = ""
            extra_env["OLLAMA_MODEL"] = ""
        for env_key_name, env_value in injection["env"].items():
            extra_env[env_key_name] = env_value
        if case.startswith("gpu"):
            marker = POSTURE_LOG_MARKER
        conf = self.write_nginx_conf(case, backend_name)
        override = self.write_override(case, backend_name, extra_env)
        started = self.start_backend(override, backend_name)
        ui = self.start_frontend(conf, ui_name, host_port)
        origin = "http://%s:%d/" % (UI_HOST, host_port)
        ready = wait_for(lambda: self._ready(origin), 120.0, poll_s=1.0)
        entry: dict[str, Any] = {
            "case": case,
            "ring": "face-%s" % case,
            "origin": origin,
            "ui_host_port": host_port,
            "env_overrides_written_to_temp_backend_only": extra_env,
            "injection_note": injection["note"],
            "temp_backend_start": started,
            "temp_frontend_start": ui,
            "fake_ollama_start": fake_started,
            "origin_ready": bool(ready),
            "nginx_upstream_swapped_lines": 1,
        }
        if ready:
            entry.update(self.shoot(case, origin, "r694-face-%s.png" % case, self.args.ask_question))
        posture_word = POSTURE_WORDS.get(case)
        entry["backend_logs"] = self.logs(
            backend_name, marker, extra_markers=DECLARATION_WORDS if posture_word else ())
        entry["face"] = self.face_verdict(entry)
        if posture_word:
            logs = entry["backend_logs"]
            hits = [ln for ln in logs["marker_lines"] if posture_word in ln]
            health = entry.get("health_details") or {}
            entry["posture_reading"] = {
                "expected_posture_word": posture_word,
                "posture_line_count": len(hits),
                "posture_lines": [ln[:400] for ln in hits[:3]],
                "declarations": logs["secondary_markers"],
                "health_model_source": health.get("model_source"),
                "health_inference_compute": health.get("inference_compute"),
                "health_model_name": health.get("model_name"),
                "screen_face_hit_count": entry["face"]["hit_count"],
                "screen_face_expected": case != "gpu-failopen",
            }
            posted = entry["posture_reading"]["posture_line_count"] >= 1
            if case == "gpu-failopen":
                ok = bool(ready and entry.get("shot") and posted)
            else:
                ok = bool(ready and entry.get("shot") and posted
                          and entry["face"]["hit_count"] > 0)
        else:
            ok = bool(ready and entry.get("shot") and entry["face"]["hit_count"] > 0)
        entry["status"] = "达" if ok else "未达"
        self.ledger.record("faces", entry)
        return entry

    def _ready(self, url: str) -> bool:
        """原点通不通：健康端点会要鉴权（401/403 也算站点活着），只要不是连不上。"""
        import urllib.error
        import urllib.request

        target = url.rstrip("/") + "/api/v1/health"
        try:
            with urllib.request.urlopen(target, timeout=3) as resp:  # noqa: S310
                return resp.status == 200
        except urllib.error.HTTPError as exc:
            return exc.code in (401, 403)
        except Exception:
            return False

    def _probe_inside(self, name: str, url: str) -> dict[str, Any]:
        """在容器里问一次自己：门面没起成的话，读数当场留痕，不靠事后猜。"""
        code = (
            "import json,urllib.request;"
            "r=urllib.request.urlopen('%s',timeout=5);"
            "print(json.dumps({'status':r.status,'body':json.loads(r.read().decode())})[:600])" % url
        )
        proc = sh(["docker", "exec", name, "python", "-c", code])
        return {"rc": proc.returncode, "stdout_tail": (proc.stdout or "")[-400:],
                "stderr_tail": (proc.stderr or "")[-200:]}

    # -------------------------------------------------------------------- 收尾
    def teardown(self) -> dict[str, Any]:
        stopped: dict[str, Any] = {}
        for name in self.owned:
            proc = sh(["docker", "stop", name])
            stopped[name] = {"rc": proc.returncode, "stderr_tail": (proc.stderr or "")[-200:]}
        removed: list[str] = []
        for f in self.own_files:
            if f.is_file():
                f.unlink()
                removed.append(f.name)
        alive = docker_names(all_containers=False)
        everything = docker_names(all_containers=True)
        leftover = [n for n in everything if n.startswith("r694-")]
        return {
            "stopped": stopped,
            "owned_names": self.owned,
            "temp_files_removed": removed,
            "ps_minus_ps_a": [n for n in everything if n not in alive],
            "r694_leftover": leftover,
            "up_count": len(alive),
            "up_names": alive,
            "taken_at": stamp(),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R694 两张失败脸（一次性容器注入）")
    parser.add_argument("--case", default="embedding",
                        help="embedding | gpu-hard | gpu-failopen | all")
    parser.add_argument("--env-file", required=True, help="deploy/.env.server 的绝对路径（只按键名取值）")
    parser.add_argument("--compose-dir", default=r"C:\Users\fengx\PycharmProjects\企业智脑",
                        help="compose 项目目录（env 文件与 docker-compose.yml 所在处，只读）")
    parser.add_argument("--nginx-conf", default=str(ROOT / "deploy" / "nginx.conf"))
    parser.add_argument("--network", default="enterprise-brain_default")
    parser.add_argument("--frontend-image", default="enterprise-brain-frontend:local")
    parser.add_argument("--backend-image", default="enterprise-brain:local")
    parser.add_argument("--absent-embedding-model", default="r694-absent-embed-text")
    parser.add_argument("--unreachable-base", default="http://127.0.0.1:1",
                        help="embedding-unreachable 案用：把 OLLAMA_BASE_URL 指到没人听的端口")
    parser.add_argument("--temp-dir", default=str(Path(args_temp_default())))
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    parser.add_argument("--base-port", type=int, default=8088)
    parser.add_argument("--ask-question", default="费用报销需要经过哪些审批环节？")
    parser.add_argument("--ask-timeout-s", type=float, default=180.0)
    return parser


def args_temp_default() -> str:
    import os

    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".").resolve() / "evalrun" / "r694"
    return str(base)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    faces = Faces(args)
    cases = ([c.strip() for c in args.case.split(",") if c.strip()]
             if args.case != "single-placeholder" else [])
    if args.case == "all":
        cases = ["embedding", "embedding-unreachable", "gpu-hard", "gpu-failopen"]
    print(json.dumps({"cases": cases, "owned_before": faces.owned}, ensure_ascii=False))
    try:
        for case in cases:
            entry = faces.run_case(case)
            print("[face %s] %s origin=%s shot=%s" % (
                case, entry["status"], entry["origin"],
                (entry.get("shot") or {}).get("file")))
    finally:
        recovery = faces.teardown()
        faces.ledger.set_root("recovery", recovery)
        print(json.dumps({"recovery": recovery}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
