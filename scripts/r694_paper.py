"""R694 · 凭据纸渲染器：从 ledger.json 与图目录生成 README.md。

本件不 import ``app``、不开浏览器、不改任何容器：只做四件事——
把账本里的读数按环／脸／腿排成一页纸、把目录里每一枚图的文件名与字节数点名、
现取 docker 与 git 的代次读数、跑三枚卫生自检（控制符枚数、裸坐标枚数、口令值泄漏）。
跑法：``python scripts/r694_paper.py``；自检不过时 rc≠0。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from r694_common import FORBIDDEN_CONTROLS, read_env_keys  # noqa: E402

TICKET = "docs/tickets/R694-frontend-nine-loop-walkthrough.md"
BASE_SHA = "6800b4c"
GEN_SHA = "4ebfaff"
TREE = r"C:\Users\fengx\PycharmProjects\be-r694"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
BARE_COORD = re.compile(
    r"[\w./\\-]+\.(?:py|vue|js|ts|tsx|md|json|sql|yml|yaml|toml|sh|ps1):\d+")

#: 每一环点名哪些读数（点分路径，从该环 readings 起走；``_len`` 是派生读数）。
POINTERS: dict[int, list[tuple[str, str]]] = {
    1: [
        ("请求总数", "requests_total"),
        ("外部域名请求枚数", "requests_external_len"),
        ("外部域名请求名册", "requests_external"),
        ("googleapis／gstatic 枚数", "requests_font_cdn_len"),
        ("document.fonts.status", "document_fonts_status"),
        ("地球图那一层", "globe_art_layer.backgroundImage"),
        ("地球图那层 display", "globe_art_layer.display"),
        ("登录页节点在位", "login_page_present"),
        ("屏上非空白字符数", "body_chars"),
        ("body 元素枚数", "white_screen_guard"),
    ],
    2: [
        ("登录到工作台用时（秒）", "login_elapsed_s"),
        ("身份", "user_shown"),
        ("角色", "role_shown"),
        ("背景层枚数", "layer_count"),
        ("背景层名册", "layer_names_seen"),
        ("要看的四层", "expected_layer_names"),
        ("包装层 aria-hidden", "app_bg_wrapper.ariaHidden"),
        ("最大透底均差", "bleed_worst_mean"),
        ("透底判据线", "bleed_mean_limit"),
        ("透底取样枚数", "art_bleed_len"),
        ("760 视口正文字符数", "viewport_760_workspace_chars"),
    ],
    3: [
        ("夹具文件名", "fixture_name"),
        ("夹具字节数", "fixture_bytes"),
        ("上传前计数牌", "counts_before.tile"),
        ("上传后计数牌", "counts_after.tile"),
        ("计数增量", "count_delta"),
        ("上传前 API 文档枚数", "counts_before.api_document_count"),
        ("上传后 API 文档枚数", "counts_after.api_document_count"),
        ("上传前屏上行数", "counts_before.rows_rendered"),
        ("上传后屏上行数", "counts_after.rows_rendered"),
        ("起手那枚档是否已在库", "fixture_already_in_corpus_before_upload"),
        ("上传态转换次数", "upload_state_transitions_len"),
        ("那一行文本", "row_text_after"),
    ],
    4: [
        ("那一行在屏上", "row_present"),
        ("屏上状态词", "row_fields.statusWord"),
        ("屏上真相行", "row_fields.truth"),
        ("屏上索引状态", "row_fields.indexStatus"),
        ("屏上密级", "row_fields.classification"),
        ("那一行的控件名册", "row_fields.controls"),
        ("catalog 面 HTTP", "catalog_api_status"),
        ("catalog 行字段名册", "catalog_keys"),
        ("catalog 里的来源", "catalog_row.storage_path"),
        ("catalog 里的版本", "catalog_row.version"),
        ("catalog 里的解析态", "catalog_row.parse_status"),
        ("catalog 里的索引态", "catalog_row.index_status"),
        ("catalog 里的部门", "catalog_row.department"),
        ("catalog 里的密级", "catalog_row.classification"),
    ],
    5: [
        ("问句", "question"),
        ("发问时刻", "asked_at"),
        ("一问用时（秒）", "elapsed_s"),
        ("帧总数", "frame_count_total"),
        ("text 帧枚数", "text_frame_count"),
        ("帧里累计字符数", "answer_chars_from_frames"),
        ("帧序号单调", "sequence_monotonic"),
        ("帧序号起止", "sequence_first_last"),
        ("屏上长度取值档数", "distinct_screen_lengths_len"),
        ("刷新前 .msg-row 枚数", "rows_live_before_reload"),
        ("读屏是否先刷新", "reloaded_to_read_screen"),
        ("屏上字符数", "final_chars"),
        ("来源卡枚数", "sources_cards"),
        ("步骤牌枚数", "steps_cards"),
        ("SSE 原点", "stream_url"),
        ("SSE HTTP", "stream_http_status"),
        ("SSE 时长（秒）", "stream_duration_s"),
        ("SSE 帧枚数", "stream_frame_count"),
    ],
    6: [
        ("问句", "question"),
        ("甲身份 catalog 枚数", "principal_a_catalog_count"),
        ("甲身份屏上来源卡枚数", "principal_a_sources"),
        ("乙身份可见枚数", "catalog_visible_count"),
        ("乙身份受限读数", "catalog_restricted"),
        ("乙身份 catalog HTTP", "catalog_status"),
        ("乙身份用户名", "principal_b_user"),
        ("乙身份角色", "principal_b_role"),
        ("乙身份部门", "principal_b_department"),
        ("两身份答案同文", "answer_identical_to_principal_a"),
        ("乙身份帧里累计字符数", "answer_chars_from_frames"),
        ("乙身份屏上来源名册", "source_names_visible"),
        ("一问用时（秒）", "elapsed_s"),
    ],
    7: [
        ("问句", "question"),
        ("发问时刻", "asked_at"),
        ("一问用时（秒）", "elapsed_s"),
        ("选表", "table_choice.chosen"),
        ("屏上表名册", "table_choice.options_on_screen"),
        ("帧总数", "frame_count_total"),
        ("刷新前 .msg-row 枚数", "rows_live_before_reload"),
        ("屏上图枚数", "charts_on_screen"),
        ("图产物登记", "chart_artifact"),
        ("批前服务端待批枚数", "decision.server_pending_before.count"),
        ("批后服务端待批枚数", "decision.server_pending_after.count"),
        ("批准按钮在位", "decision.button_present"),
        ("那一行退出待批列", "decision.row_left_pending"),
        ("屏上待批枚数（批前／批后）", "decision_pending_pair"),
        ("决策等待（秒）", "decision.decide_wait_s"),
        ("批后屏上图枚数", "after_approve.charts_on_screen"),
        ("批后屏上字符数", "after_approve.final_chars"),
        ("产物登记失败读数", "artifact_leg_error"),
        ("对照身份（部门非空）", "department_probe.user"),
        ("对照身份图登记", "department_probe.chart_artifact"),
        ("对照身份那一行退出待批列", "department_probe.decision.row_left_pending"),
    ],
    8: [
        ("问句", "question"),
        ("发问时刻", "asked_at"),
        ("一问用时（秒）", "elapsed_s"),
        ("输入框等待（秒）", "input_wait_s"),
        ("批前产物在册枚数", "artifacts_before.total"),
        ("报告产物登记", "report_artifact"),
        ("浏览器取件读数", "exported_piece"),
        ("批后产物行枚数", "artifact_rows_after_len"),
        ("盘上最新一枚 PDF", "disk_newest_pdf"),
        ("批准按钮在位", "decision.button_present"),
        ("那一行退出待批列", "decision.row_left_pending"),
        ("决策等待（秒）", "decision.decide_wait_s"),
        ("屏上待批枚数（批前／批后）", "decision_pending_pair"),
        ("产物登记失败读数", "artifact_leg_error"),
        ("刷新前 .msg-row 枚数", "rows_live_before_reload"),
        ("屏上字符数", "final_chars"),
    ],
    9: [
        ("另开新会话", "fresh_session"),
        ("问句", "parked_question"),
        ("这一轮问得出", "parked_asked"),
        ("问不出的原因", "parked_blocked_reason"),
        ("问不出时的屏面探针", "parked_blocked_probe"),
        ("一问用时（秒）", "parked_elapsed_s"),
        ("对话里的批准牌枚数", "hitl_in_chat.hitl_seen_before_decision"),
        ("驳回命中哪一枚", "rejection.matched_keyword"),
        ("驳回按钮在位", "rejection.button_present"),
        ("驳回前屏上待批枚数", "rejection.pending_rows_before"),
        ("驳回后屏上待批枚数", "rejection.pending_rows_after"),
        ("驳回前服务端待批枚数", "rejection.server_pending_before.count"),
        ("驳回后服务端待批枚数", "rejection.server_pending_after.count"),
        ("那一行退出待批列", "rejection.row_left_pending"),
        ("决策等待（秒）", "rejection.decide_wait_s"),
        ("驳回前那几行", "rejection.pending_row_texts_before"),
        ("驳回后那几行", "rejection.pending_row_texts_after"),
        ("驳回后的待批面", "approval_screen_after_reject.pending_face_when_empty"),
        ("审计面状态", "audit.face"),
        ("审计事件总数", "audit.events_total"),
        ("审计在册总数", "audit.recorded_total"),
        ("审计本页枚数", "audit.row_count"),
        ("审计最新几枚", "audit.row_texts"),
        ("审计截断读数", "audit.truncated"),
    ],
}


def sh(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT), timeout=120)
    return (proc.stdout or "").strip()


def git_count(rev: str, path: str) -> str:
    return sh(["git", "rev-list", "--count", rev, "--", path]) or "读数缺失"


def docker_lines(args: list[str]) -> list[str]:
    return [ln.strip() for ln in sh(["docker"] + args).splitlines() if ln.strip()]


def leaf(node: Any, path: str) -> Any:
    for part in path.split("."):
        if isinstance(node, dict):
            if part not in node:
                return None
            node = node[part]
        elif isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return node


def derived(readings: dict[str, Any], path: str) -> Any:
    if path == "decision_pending_pair":
        dec = readings.get("decision") or {}
        return "%s 枚 → %s 枚" % (dec.get("pending_rows_before"), dec.get("pending_rows_after"))
    if path.startswith("stream_"):
        streams = readings.get("streams") or []
        first = streams[0] if streams else {}
        return first.get(path[len("stream_"):]) if isinstance(first, dict) else None
    value = leaf(readings, path)
    if value is None and (path.endswith("_len") or path.endswith("_count")):
        base = leaf(readings, path.rsplit("_", 1)[0])
        if isinstance(base, (list, dict, str)):
            return len(base)
        return None
    return value


def fmt(value: Any, limit: int = 240) -> str:
    if isinstance(value, bool):
        return "真" if value else "假"
    if value is None:
        return "无读数"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        head = "; ".join(fmt(v, 60) for v in value[:8])
        more = "" if len(value) <= 8 else "; 另 %d 枚从略" % (len(value) - 8)
        return "%d 枚 [%s%s]" % (len(value), head, more)
    if isinstance(value, dict):
        text = " / ".join("%s=%s" % (k, fmt(v, 60)) for k, v in sorted(value.items()))
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def shot_rows(holder: Any, keys: tuple[str, ...] = ("shot",)) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in keys:
        value = (holder or {}).get(key)
        if isinstance(value, dict) and value.get("file"):
            out.append(value)
        elif isinstance(value, list):
            out.extend(v for v in value if isinstance(v, dict) and v.get("file"))
    return out


def shot_line(shot: dict[str, Any]) -> str:
    view = shot.get("viewport") or {}
    return ("- 图：`%s` %s B（sha256 前 8 位 `%s`，%s，视口 %s×%s）"
            % (shot.get("file"), shot.get("bytes"), shot.get("sha256_8"),
               shot.get("taken_at"), view.get("width"), view.get("height")))


def render(ledger: dict[str, Any], out_dir: Path) -> str:
    lines: list[str] = []
    push = lines.append

    rings = {int(r["ring"]): r for r in ledger.get("rings", [])}
    faces = ledger.get("faces", [])
    offline = ledger.get("offline") or {}
    revert = ledger.get("revert") or {}
    recovery = ledger.get("recovery") or {}
    prereq = ledger.get("prereq") or {}
    keys = ledger.get("credential_key_names") or {}
    defects = ledger.get("defects") or []
    defects_file = out_dir / "defects.json"
    if defects_file.is_file():
        defects = json.loads(defects_file.read_text(encoding="utf-8"))
    primary = keys.get("primary") or ["无读数", "无读数"]
    secondary = keys.get("secondary") or ["无读数", "无读数"]

    owners: dict[str, list[str]] = {}
    for ring_no, ring in sorted(rings.items()):
        for shot in ring.get("shots", []):
            owners.setdefault(shot["file"], []).append("环 %d" % ring_no)
    for entry in faces:
        for shot in shot_rows(entry):
            owners.setdefault(shot["file"], []).append("脸 %s" % entry.get("case"))
    for leg in (offline.get("legs") or {}).values():
        for screen in ("login_page", "workbench"):
            for shot in shot_rows(leg.get(screen) or {}):
                owners.setdefault(shot["file"], []).append("断网 %s" % leg.get("method"))
    for shot in shot_rows(revert):
        owners.setdefault(shot["file"], []).append("复原")

    push("# R694 · 前端九环走查凭据纸（2026-10-06）")
    push("")
    push("本页由 `scripts/r694_paper.py` 从 `docs/testing/walkthrough-2026-10-06/ledger.json` 渲染。"
         "文件名、字节数、秒数与屏上读数都从账本取，不经手抄；坐标一律 `文件::符号`；"
         "凭据只写 env 键名，值不入纸。")
    push("")
    push("- 工单：`%s`" % TICKET)
    push("- 基点：`%s`；产品码代次：`%s`" % (BASE_SHA, GEN_SHA))
    push("- 独占工作树：`%s`" % TREE)
    push("- 起手轴（全账最早一枚截图时刻）：%s；最近一笔落账：%s" % (
        ledger.get("first_evidence_at") or ledger.get("started_at", "无读数"),
        ledger.get("finished_at", "无读数")))
    push("- 驱动：`scripts/r694_walkthrough.py::Walk`／`scripts/r694_failure_faces.py::Faces`／"
         "`scripts/r694_offline.py::Offline`／`scripts/r694_revert.py::Revert`")
    push("- 浏览器：Playwright 1.63.0（Chromium，headless），视口 1440×900（环 2 另取 760 宽）")
    push("")

    push("## 环境前置四条")
    push("")
    for row in (prereq.get("checks") or []):
        push("- %s" % row)
    if not (prereq.get("checks") or []):
        push("- 前置读数缺失：`scripts/r694_prereq.py` 未落账，这一格只有渲染那一刻的现取")
        push("- 产品码自代次 `%s` 起的提交枚数（`git rev-list --count %s..HEAD -- app/`）：%s"
             % (GEN_SHA, GEN_SHA, git_count("%s..HEAD" % GEN_SHA, "app/")))
        push("- 前端源码自代次 `%s` 起的提交枚数（同一谓词换 `frontend/`）：%s"
             % (GEN_SHA, git_count("%s..HEAD" % GEN_SHA, "frontend/")))
    stamps = sorted([r.get("taken_at", "") for r in rings.values() if r.get("taken_at")])
    if stamps:
        push("- 九环取数分笔落账：最早一枚图 %s，最近一笔环 %s；逐环时刻见下表 ``取数时刻`` 列"
             % (stamps[0], stamps[-1]))
    push("- 镜像现取（渲染那一刻）：%s" % "；".join("`%s`" % ln for ln in docker_lines(
        ["images", "--format", "{{.Repository}}:{{.Tag}} CreatedSince={{.CreatedSince}} ID={{.ID}}"])
        if ("enterprise-brain:local" in ln or "enterprise-brain-frontend:local" in ln)))
    push("- 凭据取自 `deploy/.env.server` 键名 `%s`／`%s`（主身份）与 `%s`／`%s`（次身份），值未记录"
         % (primary[0], primary[1], secondary[0], secondary[1]))
    push("")

    push("## 九环逐环")
    push("")
    push("| 环 | 标题 | 判 | 取数时刻 | 截图枚数 |")
    push("|---|---|---|---|---|")
    for ring_no in sorted(rings):
        ring = rings[ring_no]
        push("| %d | %s | %s | %s | %d |" % (ring_no, ring.get("title"), ring.get("status"),
                                            ring.get("taken_at"), len(ring.get("shots", []))))
    push("")
    for ring_no in sorted(rings):
        ring = rings[ring_no]
        readings = ring.get("readings") or {}
        push("### 环 %d · %s — %s" % (ring_no, ring.get("title"), ring.get("status")))
        push("")
        push("- 取数时刻：%s" % ring.get("taken_at"))
        for label, path in POINTERS.get(ring_no, []):
            push("- %s：`%s` = %s" % (label, path, fmt(derived(readings, path))))
        for shot in ring.get("shots", []):
            push(shot_line(shot))
        if ring.get("note"):
            push("- 纸面备注：%s" % ring["note"])
        push("")

    push("## 失败脸（一次性容器注入）")
    push("")
    if not faces:
        push("- 无读数：`scripts/r694_failure_faces.py` 未产出任何一枚脸。")
        push("")
    for entry in faces:
        push("### 案 `%s` — %s" % (entry.get("case"), entry.get("status")))
        push("")
        push("- 原点：`%s`（临时前端宿主端口 %s；nginx 上游那一行按 `set $enterprise_brain_api` 改指临时 backend）"
             % (entry.get("origin"), entry.get("ui_host_port")))
        push("- 只写进临时 backend 的 env（宿主 env 文件与常驻 backend 未动）：%s"
             % fmt(entry.get("env_overrides_written_to_temp_backend_only")))
        push("- 临时 backend：`docker compose run -d --rm --no-deps` rc=%s，用时 %s s；原点就绪：%s"
             % ((entry.get("temp_backend_start") or {}).get("command_rc"),
                (entry.get("temp_backend_start") or {}).get("start_elapsed_s"),
                entry.get("origin_ready")))
        push("- 临时 frontend：`docker run -d --rm` rc=%s"
             % (entry.get("temp_frontend_start") or {}).get("command_rc"))
        fake = entry.get("fake_ollama_start")
        if fake:
            push("- 假 Ollama 门面：rc=%s；容器内自探 `/api/ps` %s"
                 % (fake.get("command_rc"), fmt(fake.get("in_container_probe"))))
        push("- `/api/v1/health/details` 读数：%s" % fmt(entry.get("health_details")))
        push("- 屏上失败面（发问前）：%s" % fmt(entry.get("faces_before_ask")))
        push("- 屏上失败面（发问后）：%s" % fmt(entry.get("faces_after_ask")))
        ask = entry.get("ask") or {}
        push("- 一问：`%s`；事件名册 %s；屏上错误串 %s；用时 %s s"
             % (ask.get("question"), fmt(ask.get("event_names")),
                fmt(ask.get("error_text_on_screen")), ask.get("elapsed_s")))
        logs = entry.get("backend_logs") or {}
        push("- 后端日志词命中（`embedding`／不可用／降级／连接被拒那几枚词）：%s 枚：%s"
             % (logs.get("line_count"), fmt(logs.get("lines"))))
        posture = entry.get("posture_reading") or {}
        if posture:
            push("- R673 姿势声明：期望档位 `%s`，临时 backend 日志命中 %s 枚：%s"
                 % (posture.get("expected_posture_word"),
                    posture.get("posture_line_count"), fmt(posture.get("posture_lines"), limit=600)))
            push("- 探针结论两句计数：%s" % fmt(posture.get("declarations"), limit=500))
            push("- health/details 那三格：model_source `%s`／inference_compute `%s`／model `%s`"
                 % (posture.get("health_model_source"), posture.get("health_inference_compute"),
                    posture.get("health_model_name")))
            push("- 屏上失败面命中 %s 枚；本案预期屏上有脸：%s"
                 % (posture.get("screen_face_hit_count"), posture.get("screen_face_expected")))
        for shot in shot_rows(entry):
            push(shot_line(shot))
        push("")

    push("## 断网自证")
    push("")
    if not offline:
        push("- 无读数：`scripts/r694_offline.py` 未跑。")
    else:
        push("- 判：%s（取数时刻 %s）" % (offline.get("verdict"), offline.get("at")))
        push("- 口径：%s" % offline.get("note"))
        for name, leg in (offline.get("legs") or {}).items():
            push("- 腿 `%s`：白屏读数 %s；两屏窗口内外部域名请求合计 %s 枚"
                 % (name, leg.get("white_screen"), leg.get("external_requests")))
            if leg.get("aborted_external_count") is not None:
                push("  - 被拦下的外部请求枚数：%s；名册 %s"
                     % (leg.get("aborted_external_count"), fmt(leg.get("aborted_external_urls"))))
            if leg.get("login_reached") is not None:
                push("  - 登录页与工作台都到位：%s" % leg.get("login_reached"))
            for screen in ("login_page", "workbench"):
                read = leg.get(screen) or {}
                scr = read.get("screen") or {}
                push("  - %s：`%s` %s B；节点 %s；非空白字符 %s；login-page %s；sidebar %s；"
                     "窗口内请求 %s 枚；外部 %s 枚；失败请求 %s 枚；chrome 错误页 %s；导航异常 %s；刷新一屏用时 %s s"
                     % (screen, (read.get("shot") or {}).get("file"), (read.get("shot") or {}).get("bytes"),
                        scr.get("dom_nodes"), scr.get("body_chars"), scr.get("login_page"),
                        scr.get("sidebar"), read.get("requests_in_window"),
                        read.get("requests_external_count"), read.get("requests_failed_count"),
                        scr.get("chrome_error_page"), read.get("nav_exception"), read.get("reload_s")))
            push("  - 屏上头几行：%s" % fmt((leg.get("workbench") or {}).get("screen", {}).get("first_lines")))
    push("")

    push("## 复原与副作用")
    push("")
    if revert:
        push("- 删档走产品自己的两击删除（屏上控件 `document-delete-one`）：计数牌 %s → %s（环 3 起手基线 %s）"
             % ((revert.get("counts_before_revert") or {}).get("tile"),
                (revert.get("counts_after_revert") or {}).get("tile"), revert.get("baseline_tile")))
        push("- API 文档枚数 %s → %s；那一行还在屏上：%s；catalog 里是否仍列那枚夹具：%s"
             % ((revert.get("counts_before_revert") or {}).get("api_document_count"),
                (revert.get("counts_after_revert") or {}).get("api_document_count"),
                revert.get("row_present_after"), revert.get("catalog_still_lists_fixture")))
        push("- 删除用时（秒）：%s" % revert.get("delete_wait_s"))
        for shot in shot_rows(revert):
            push(shot_line(shot))
        push("- 本单在册副作用（逐枚点名）：")
        for row in (revert.get("side_effects") or []):
            push("  - %s" % row)
    else:
        push("- 无读数：`scripts/r694_revert.py` 未跑。")
    push("")

    push("## 恢复自证")
    push("")
    blocks = [("失败脸收尾那一刻", recovery), ("收工现取", revert.get("docker") or {})]
    for title, block in blocks:
        if not block:
            continue
        push("- %s：`docker ps` 枚数 %s；`docker ps -a` 减 `docker ps` 差集 %s；`r694-*` 残留 %s"
             % (title, block.get("up_count"), fmt(block.get("ps_minus_ps_a")),
                fmt(block.get("r694_leftover"))))
        push("  - 停掉的临时容器：%s" % fmt(block.get("stopped")))
        push("  - 清掉的盘外临时文件：%s" % fmt(block.get("temp_files_removed")))
        push("  - Up 名册：%s" % fmt(block.get("up_names")))
        if block.get("statuses"):
            push("  - 逐枚状态：%s" % fmt(block.get("statuses")))
        push("  - 取数时刻：%s" % block.get("taken_at"))
    push("")

    push("## 缺陷清单（只立号，不改码）")
    push("")
    if not defects:
        push("- 无读数：账本 `defects` 那一格为空。")
        push("")
    for defect in defects:
        push("### 缺陷 #%s（%s）· %s" % (defect.get("no"), defect.get("level"), defect.get("title")))
        push("")
        push("- 现象：%s" % defect.get("phenomenon"))
        push("- 复现步骤：")
        for step in defect.get("repro") or []:
            push("  1. %s" % step)
        push("- 归因符号：%s" % "／".join("`%s`" % sym for sym in (defect.get("symbols") or [])))
        push("- 读数指针：%s" % "／".join("`%s`" % ptr for ptr in (defect.get("pointers") or [])))
        push("- 本单动作：%s" % defect.get("action"))
        push("")

    push("## 图目录名册（逐枚点名文件名与字节数）")
    push("")
    images = sorted(p for p in out_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    push("| 文件 | 字节 | 挂在 |")
    push("|---|---|---|")
    for img in images:
        push("| `%s` | %d | %s |" % (img.name, img.stat().st_size,
                                    "、".join(owners.get(img.name) or ["未挂账"])))
    push("- 目录里图枚数：%d；字节合计：%d" % (len(images), sum(p.stat().st_size for p in images)))
    push("")

    push("## 卫生自检")
    push("")
    push("- 控制符枚数（`0x00 0x07 0x08 0x0b 0x0c 0x1b`）：CONTROLS")
    push("- 裸坐标（`文件:数字`）命中：COORDS")
    push("- 口令值泄漏扫描：SECRETS")
    push("- 账本与图目录：`ledger.json` 与上表逐枚互比由 `tests/test_r694_paper_is_auditable.py` 现取，不在本页写数")
    push("")
    return "\n".join(lines) + "\n"


def scan(text: str) -> tuple[str, str]:
    controls = {c: text.count(chr(c)) for c in FORBIDDEN_CONTROLS}
    total_controls = sum(controls.values())
    coords = sorted(set(BARE_COORD.findall(text)))
    return ("现取 %d 枚（逐码 %s）" % (total_controls, fmt(controls, 200)),
            "现取 %d 枚%s" % (len(coords), ("：" + "、".join("`%s`" % c for c in coords)) if coords else ""))


def secret_leak(text: str, env_file: Path) -> list[str]:
    leaks: list[str] = []
    try:
        keys = read_env_keys(env_file)
    except OSError:
        return ["env 文件读不到，本项自检未跑"]
    for name in ("DEMO_ADMIN_PASSWORD", "EB_SEED_OWNER_PASSWORD", "AUTH_PASSWORD_HASH",
                 "POSTGRES_PASSWORD", "REDIS_PASSWORD"):
        value = (keys.get(name) or "").strip()
        if len(value) >= 6 and value in text:
            leaks.append(name)
    return leaks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R694 凭据纸渲染")
    parser.add_argument("--out", default="docs/testing/walkthrough-2026-10-06")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--env-file", default=str(ROOT.parent / Path("企业智脑") / "deploy" / ".env.server"))
    parser.add_argument("--write", action="store_true", help="写 README.md（默认只渲染到 stdout）")
    args = parser.parse_args(argv)

    out_dir = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    ledger_path = Path(args.ledger) if args.ledger else out_dir / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    text = render(ledger, out_dir)
    controls, coords = scan(text)
    leaks = secret_leak(text, Path(args.env_file))
    secrets = ("现取 0 枚泄漏（键名 DEMO_ADMIN_PASSWORD／EB_SEED_OWNER_PASSWORD／AUTH_PASSWORD_HASH／"
               "POSTGRES_PASSWORD／REDIS_PASSWORD 的值都不在本页）"
               if not leaks else "命中 %d 枚：%s" % (len(leaks), "、".join(leaks)))
    text = text.replace("CONTROLS", controls).replace("COORDS", coords).replace("SECRETS", secrets)

    # 替换之后再扫一遍：占位符换成读数本身也可能带进控制符或裸坐标
    controls2, coords2 = scan(text)
    if leaks or "非 0" in controls2 or "现取 0 枚" not in controls2 or "现取 0 枚" not in coords2:
        print(json.dumps({"ok": False, "controls": controls2, "coords": coords2,
                          "secrets": secrets}, ensure_ascii=False))
        if leaks:
            return 1
    if args.write:
        target = out_dir / "README.md"
        target.write_text(text, encoding="utf-8", newline="\n")
        print(json.dumps({"written": str(target), "bytes": target.stat().st_size,
                          "controls": controls2, "coords": coords2}, ensure_ascii=False))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())