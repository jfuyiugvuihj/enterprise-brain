"""R123 甲案（采集侧）：HITL 挂起要按契约批准到终答，批准失败不许静默。

判据原文：跟进单 §57 立的 R123（三选一，业主 09-20 裁甲案）+ 施工单 R123 判据 ①②③⑤。
全程离线：urllib 的 opener 被换成记账的假传输（真 `_open` 仍负责拼 URL、Bearer 头与 JSON
体，所以"同一个 token"这句话是被断言的而不是被假定的），零网络 / 零模型 / 零容器 / 零连库，
侧车写进 tmp_path。真机单题探针不在这里（那要真打模型，见交付说明的探针三段证据）。

钉住的四件事：
  ① 批准只走 POST /api/v1/approve，同一个 session、同一个 Bearer token；
  ② 侧车既有九键不动，甲案新增 pre_*/approval_* 两把尺都留得下来；
  ③ 批准失败（非 2xx / 超时 / 批准后仍无终答 / 批到上限仍挂着）一律 approval_failed，
     正文换占位串、出处清空、sentinel=true，绝不拿批准前那一帧冒充终答；
  ④ attempt / sentinel / 每题独立 session_id 三样语义没被放宽。
"""
from __future__ import annotations

import importlib.util
import io
import json
import socket
import urllib.error
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
COLLECTOR_PATH = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 侧车既有九键（判据 2：名字、顺序、语义一个都不许动）。
SIDECAR_BASE_KEYS = ("id", "kind", "attempt", "sentinel", "evidence_n",
                     "answer_chars", "tool_calls", "wall_ms", "ts")
#: 甲案新增的键；pre_answer 只有真挂起过的题才写。
APPROVAL_EXTRA_KEYS = {"pre_kind", "pre_answer_chars", "pre_evidence_n", "approved",
                       "approval_rounds", "approval_http_status", "approval_error"}
#: 适配器交回采集器的载荷键（四键里的三个 + 采集器自己补 id/latency_ms/answer_source）。
PAYLOAD_KEYS = {"answer", "evidence", "first_token_at", "thinking_chars", "tool_calls"}

PARK_TEXT = "本轮在「生成图表」前等待你确认，确认后才会执行，目前尚未产出回答内容。"
TERMINAL_TEXT = "只有支付截图不能入账，需补开发票后由财务复核。"
TOKEN_VALUE = "eval-bearer-token"
#: 批准端点的真路径：chat.router 挂在 /api/v1 上（app/main.py:80），没有 chat 那一段。
APPROVAL_PATH = "/api/v1/approve"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLLECTOR = _load("r123_collect_answers", COLLECTOR_PATH)


def fixture_row(row_id):
    """从真夹具里取一行（只读）。夹具属业主，本单一个字都不改。"""
    for line in FIXTURE_105.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) == row_id:
                return row
    raise AssertionError(f"{row_id} 不在 {FIXTURE_105.name} 里")


def sse(events):
    """服务端每事件三行：event / data / 空行（app/api/v1/chat.py:218-219）。"""
    lines = []
    for name, data in events:
        lines.append(("event: " + name + "\n").encode("utf-8"))
        lines.append(("data: " + json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        lines.append(b"\n")
    return lines


class FakeResponse:
    def __init__(self, lines=None, body=b"{}"):
        self._lines = lines or []
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return self._body


ASK_PARK = [
    ("status", {"type": "status", "content": "正在检索制度依据"}),
    ("step", {"type": "step", "name": "doc"}),
    ("text", {"type": "text", "content": PARK_TEXT}),
    ("hitl", {"type": "hitl", "pending": ["chart"], "labels": ["生成图表"]}),
    ("sources", {"data": {"sources": [{"source_name": "口径登记表", "locator": "第1行"}],
                           "hit_count": 1}}),
    ("done", {"type": "done"}),
]
ASK_CLEAN = [
    ("step", {"type": "step", "name": "doc"}),
    ("text", {"type": "text", "content": TERMINAL_TEXT}),
    ("sources", {"data": {"sources": [{"source_name": "差旅制度", "locator": "第3页"}],
                           "hit_count": 1}}),
    ("done", {"type": "done"}),
]
ASK_BLANK = [("step", {"type": "step", "name": "doc"}), ("done", {"type": "done"})]
APPROVE_TEXT = [
    ("step", {"type": "step", "name": "chart"}),
    ("text", {"type": "text", "content": TERMINAL_TEXT}),
    ("sources", {"data": {"sources": [{"source_name": "差旅制度", "locator": "第3页"},
                                      {"source_name": "口径登记表", "locator": "第9行"}],
                           "hit_count": 2}}),
    ("done", {"type": "done"}),
]
APPROVE_PARK_AGAIN = [("hitl", {"type": "hitl", "pending": ["export"], "labels": ["导出报告"]}),
                      ("done", {"type": "done"})]
APPROVE_NO_ANSWER = [("error", {"type": "error", "content": "本轮未产出任何结论，请重试。"}),
                     ("done", {"type": "done"})]
APPROVE_CACHED = [("text", {"type": "text", "content": TERMINAL_TEXT, "cached": True}),
                  ("done", {"type": "done"})]


def http_error(path, code=403, detail=b'{"detail":"permission_denied"}'):
    return urllib.error.HTTPError("http://eval.test" + path, code, "rejected", None,
                                  io.BytesIO(detail))


class RecordingOpener:
    """只挡网络：记录 URL 路径、JSON 体与真 _open 拼出来的 Authorization 头。"""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def open(self, request, timeout=None):
        path = urlparse(request.full_url).path
        body = request.data
        self.calls.append({"path": path, "method": request.get_method(),
                           "payload": json.loads(body.decode("utf-8")) if body else None,
                           "authorization": request.get_header("Authorization")})
        outcome = self.script.get(path)
        if isinstance(outcome, BaseException):
            raise outcome
        if path == "/api/v1/login":
            return FakeResponse(body=json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        return FakeResponse(lines=sse(outcome or []))

    def paths(self):
        return [call["path"] for call in self.calls]

    def only(self, path):
        return [call for call in self.calls if call["path"] == path]


@pytest.fixture
def adapter(tmp_path):
    module = _load("r123_transport_under_test", SCRIPT_PATH)
    module.BASE_URL = "http://eval.test"
    module.SIDECAR = tmp_path / "sidecar-run6.jsonl"
    module.MIN_GAP_SECONDS = 0.0
    module.ATTEMPTS = 3
    module.RETRY_SLEEP = 0.0
    module.MAX_BLANKS = 5
    module.APPROVAL_ROUNDS = 3
    module._TOKEN = ""
    module._BLANKS = 0
    module._APPROVAL_FAILURES = 0
    module._LAST_CALL = 0.0
    return module


def drive(module, script, row):
    opener = RecordingOpener(script)
    module._OPENER = opener
    payload = module.transport(row)
    rows = [json.loads(line) for line in
            module.SIDECAR.read_text(encoding="utf-8").splitlines() if line.strip()]
    return payload, opener, rows


def test_parked_question_is_approved_over_http_and_the_terminal_answer_is_scored(adapter):
    row = fixture_row("approval-05")
    payload, opener, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_TEXT}, row)
    asks, approves = opener.only("/api/v1/ask"), opener.only(APPROVAL_PATH)
    assert len(asks) == 1 and len(approves) == 1
    # 🔴 判据 1：批准走正道 —— POST /api/v1/approve，同一个 session、同一个 Bearer token
    assert approves[0]["method"] == "POST"
    assert approves[0]["path"] == APPROVAL_PATH
    assert approves[0]["payload"] == {"session_id": asks[0]["payload"]["session_id"],
                                      "approved": True}
    assert approves[0]["authorization"] == "Bearer " + TOKEN_VALUE
    assert approves[0]["authorization"] == asks[0]["authorization"]
    # 交回采集器的是批准后的终答，不是「等待确认」那一帧
    assert payload["answer"] == TERMINAL_TEXT
    assert row["must_contain"][0] in payload["answer"]
    assert [item["source_name"] for item in payload["evidence"]] == ["差旅制度", "口径登记表"]
    assert set(payload) == PAYLOAD_KEYS
    record = rows[0]
    assert record["kind"] == "approved_ok"
    assert record["pre_kind"] == "hitl" and record["pre_answer"] == PARK_TEXT
    assert record["approved"] is True and record["approval_rounds"] == 1
    assert record["approval_http_status"] == 200 and record["approval_error"] == ""
    assert record["sentinel"] is False
    assert record["answer_chars"] == len(TERMINAL_TEXT)
    assert record["pre_answer_chars"] == len(PARK_TEXT)
    assert record["evidence_n"] == 2 and record["pre_evidence_n"] == 1
    assert record["tool_calls"] == 2  # 挂起轮 1 步 + 恢复轮 1 步，这一题的账合起来记
    assert record["attempt"] == 1


def test_answers_line_contract_keeps_four_keys_and_three_trace_keys(adapter):
    """判据 2/4：甲案不许动采集器的行契约 —— 那四键三 trace 键由采集器当场校验。"""
    row = fixture_row("approval-05")
    payload, _, _ = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_TEXT}, row)
    answer = COLLECTOR.build_answer(row, payload, measured_ms=1234.5,
                                    answer_source="eval_transport_ask_v2:transport")
    COLLECTOR.assert_line_contract(answer)
    COLLECTOR.assert_coverage([row], [answer])
    assert set(COLLECTOR.RUNNER_REQUIRED_KEYS) == {"id", "answer", "evidence", "latency_ms"}
    assert set(COLLECTOR.TRACE_KEYS) == {"first_token_at", "thinking_chars", "tool_calls"}
    assert answer["thinking_chars"] is None  # HTTP 侧看不见思维链 ⇒ null，禁止估算
    assert answer["tool_calls"] == 2


@pytest.mark.parametrize("parked", [False, True])
def test_sidecar_keeps_the_nine_original_keys_first_and_appends_only_declared_ones(
        adapter, parked):
    script = {"/api/v1/ask": ASK_PARK if parked else ASK_CLEAN}
    if parked:
        script[APPROVAL_PATH] = APPROVE_TEXT
    _, _, rows = drive(adapter, script, fixture_row("approval-05"))
    record = rows[0]
    assert tuple(list(record)[:9]) == SIDECAR_BASE_KEYS
    assert set(record) - set(SIDECAR_BASE_KEYS) <= (APPROVAL_EXTRA_KEYS | {"pre_answer"})
    assert ("pre_answer" in record) is parked
    assert record["pre_kind"] == ("hitl" if parked else "ok")
    assert record["approved"] is parked
    assert record["kind"] == ("approved_ok" if parked else "ok")


def test_pre_kind_column_reproduces_the_run4_run5_kind_distribution(adapter):
    """判据 2：run6 之后仍要从同一份侧车还原「旧口径」那一列 ⇒ pre_kind 每题必写。"""
    drive(adapter, {"/api/v1/ask": ASK_CLEAN}, fixture_row("approval-05"))
    drive(adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_TEXT},
          fixture_row("chart-01"))
    rows = [json.loads(line) for line in
            adapter.SIDECAR.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["pre_kind"] for row in rows] == ["ok", "hitl"]
    assert [row["kind"] for row in rows] == ["ok", "approved_ok"]


def test_a_row_that_never_parks_is_still_collected_exactly_as_before(adapter):
    payload, opener, rows = drive(adapter, {"/api/v1/ask": ASK_CLEAN}, fixture_row("approval-05"))
    assert opener.paths() == ["/api/v1/login", "/api/v1/ask"]  # 一次都不许多打
    assert payload["answer"] == TERMINAL_TEXT
    record = rows[0]
    assert record["approved"] is False and record["approval_rounds"] == 0
    assert record["approval_http_status"] is None and record["approval_error"] == ""
    assert "pre_answer" not in record


def test_approval_non_2xx_is_recorded_as_approval_failed_not_as_an_answer(adapter):
    """判据 3 具名用例：/approve 非 2xx ⇒ approval_failed，不许静默当答完。"""
    payload, opener, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK,
                  APPROVAL_PATH: http_error(APPROVAL_PATH, 403)},
        fixture_row("approval-05"))
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL
    assert payload["answer"] != PARK_TEXT  # 🔴 绝不拿批准前那一帧冒充终答
    assert payload["evidence"] == [] and payload["first_token_at"] is None
    assert len(opener.only(APPROVAL_PATH)) == 1
    record = rows[0]
    assert record["kind"] == "approval_failed" and record["pre_kind"] == "hitl"
    assert record["sentinel"] is True and record["approved"] is False
    assert record["approval_http_status"] == 403 and "HTTP 403" in record["approval_error"]
    assert record["evidence_n"] == 0 and record["answer_chars"] == len(payload["answer"])


def test_approval_timeout_is_recorded_as_approval_failed(adapter):
    payload, _, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: socket.timeout("timed out")},
        fixture_row("approval-05"))
    record = rows[0]
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL
    assert record["kind"] == "approval_failed" and record["approval_http_status"] is None
    assert "timed out" in record["approval_error"]


def test_approval_that_yields_no_terminal_answer_is_approval_failed(adapter):
    payload, _, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_NO_ANSWER},
        fixture_row("approval-05"))
    record = rows[0]
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL
    assert record["kind"] == "approval_failed" and record["approved"] is True
    assert "无终答" in record["approval_error"]


def test_still_parked_after_the_round_cap_is_approval_failed(adapter):
    adapter.APPROVAL_ROUNDS = 2
    _, opener, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_PARK_AGAIN},
        fixture_row("approval-05"))
    record = rows[0]
    assert len(opener.only(APPROVAL_PATH)) == 2  # 批到上限为止，不多打
    assert record["kind"] == "approval_failed" and record["approved"] is True
    assert record["approval_rounds"] == 2
    assert "EVAL_APPROVAL_ROUNDS" in record["approval_error"]


def test_approval_failure_does_not_burn_the_attempt_budget(adapter):
    """判据 5：attempt 记的还是「这一题的 /ask 打到第几次」，批准失败不整题重来。"""
    _, opener, rows = drive(
        adapter, {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: http_error(APPROVAL_PATH, 500)},
        fixture_row("approval-05"))
    assert len(opener.only("/api/v1/ask")) == 1
    assert rows[0]["attempt"] == 1


def test_ask_transport_still_gives_up_after_the_attempt_budget(adapter):
    opener = RecordingOpener({"/api/v1/ask": urllib.error.URLError("no route")})
    adapter._OPENER = opener
    with pytest.raises(RuntimeError, match="3 次都没打通"):
        adapter.transport(fixture_row("approval-05"))
    assert len(opener.only("/api/v1/ask")) == 3
    assert not adapter.SIDECAR.exists()  # 打通不了的题不写侧车，跟改造前一样


def test_sentinel_still_marks_only_placeholder_answers(adapter):
    """判据 5：零字节那一套没被放宽，阈值照样停窗。"""
    adapter.MAX_BLANKS = 1
    _, _, rows = drive(adapter, {"/api/v1/ask": ASK_BLANK}, fixture_row("approval-05"))
    assert rows[0]["kind"] == "blank" and rows[0]["sentinel"] is True
    assert rows[0]["answer_chars"] == len(adapter.BLANK_SENTINEL)
    opener = RecordingOpener({"/api/v1/ask": ASK_BLANK})
    adapter._OPENER = opener
    with pytest.raises(RuntimeError, match="系统性故障"):
        adapter.transport(fixture_row("chart-01"))
    assert adapter._BLANKS == 2


def test_approval_failure_does_not_count_toward_the_blank_stop(adapter):
    """批准失败是产品结局，不是零字节系统性故障：它不该把整轮拖停，也不该骗过哨兵。"""
    adapter.MAX_BLANKS = 1
    script = {"/api/v1/ask": ASK_PARK,
              APPROVAL_PATH: http_error(APPROVAL_PATH, 403)}
    drive(adapter, script, fixture_row("approval-05"))
    drive(adapter, script, fixture_row("chart-01"))
    rows = [json.loads(line) for line in
            adapter.SIDECAR.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["kind"] for row in rows] == ["approval_failed", "approval_failed"]
    assert all(row["sentinel"] is True for row in rows)
    assert adapter._BLANKS == 0 and adapter._APPROVAL_FAILURES == 2


def test_every_question_still_gets_its_own_session_and_approve_targets_that_one(adapter):
    """runbook §1 红线③：共 session 会被答案缓存喂，量出来的是缓存不是模型。"""
    script = {"/api/v1/ask": ASK_PARK, APPROVAL_PATH: APPROVE_TEXT}
    first = drive(adapter, script, fixture_row("approval-05"))
    second = drive(adapter, script, fixture_row("chart-01"))
    pairs = []
    for _, opener, _ in (first, second):
        ask = opener.only("/api/v1/ask")[0]
        approve = opener.only(APPROVAL_PATH)[0]
        pairs.append((ask["payload"]["session_id"], approve["payload"]["session_id"],
                      ask["payload"]["idempotency_key"]))
    ask_sessions = [pair[0] for pair in pairs]
    assert len(set(ask_sessions)) == 2, pairs
    for ask_session, approve_session, _ in pairs:
        assert approve_session == ask_session  # 批的正是这一题挂起的那一轮


def test_cache_hit_after_approval_still_stops_the_window(adapter):
    """P-18 / runbook I-3：批准之后也不能让缓存喂出来的假时延进分。"""
    opener = RecordingOpener({"/api/v1/ask": ASK_PARK,
                              APPROVAL_PATH: APPROVE_CACHED})
    adapter._OPENER = opener
    with pytest.raises(RuntimeError, match="缓存命中"):
        adapter.transport(fixture_row("approval-05"))


def test_approval_never_bypasses_http_to_call_the_internal_graph():
    """判据 1 的下半句：不许绕过鉴权 / 不许直接调内部函数抄近路（源码级钉）。"""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "run_interrupt_stream(" not in source
    assert "from app." not in source and "import app." not in source
    assert 'APPROVAL_PATH = "/api/v1/approve"' in source
    assert "_open(APPROVAL_PATH" in source
