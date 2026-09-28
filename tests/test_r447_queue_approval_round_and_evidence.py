# -*- coding: utf-8 -*-
"""R447 判据①..⑥：队列道的批准轮必须走、出处必须随答案交回。全程离线。

派工词与本件的对应关系：
  ① 队列道读到 ``awaiting_approval`` ⇒ 按契约批准到终答；取不到终答记 ``approval_failed``
     （正文空、出处空、sentinel=true）。那句 37 字挂起文案一个字都不许当正文交回评分器
     （R254 判据① 口径不变）。legacy 那一路一起管：旧行的 ``result`` 逐字就是那句文案，
     而可读面 ``answer_is_park_notice`` 是服务端**现算的真读数**（R254 兼容节）。
  ② 新 kind ``queued_approved`` 与既有十枚 ``queued_*`` 一枚都不混，不冒充 ``queued_polled``
     （那枚说的是「从队列 ``result`` 取回了一份字」），也不冒充同步道的 ``approved_ok``；
     sidecar 那一行仍受 ``tests/test_r123_hitl_approval.py:243`` 的「甲案七键子集」约束 ——
     本件把**队列道那三路**也钉上，从前只有同步道被钉过。
  ③ 出处随答案交回：可读面 ``sources_n>0`` 的题，交回评分器的那一份 ``evidence`` 必须非空
     且枚数逐枚对得上（``scripts/collect_evaluation_answers.py`` 落盘之后照样对得上）。
  ④ 同步流道（``ok`` / ``approved_ok`` / ``error_event``）逐字节不变：三行金样由基点
     ``227949e`` 的原件在同一具假钟、同一份假出口下跑出，sidecar / 帧账 / payload 逐字符对判。
  ⑤ 可失败钉五把（R253 纪律：变异只落 ``tmp_path`` 影子副本，原件 sha 当场复验）：
     甲 摘掉批准轮 / 乙 把挂起文案当正文 / 丙 ``sources_n>0`` 而 ``evidence`` 空 /
     丁 动 sidecar 键集 / 戊 把 ``dead``·``done_no_bytes`` 并进挂起族。
  ⑥ 判读件 ``scripts/eval_lane_readout.py`` 取不到的格继续 ``rc=2`` 明写「取不到，不编数」。

零服务 / 零模型 / 零容器 / 零连库 / 零真跑分：urllib 的 opener 换成会记账的假出口，真 ``_open``
仍负责拼 URL、JSON 体与 Authorization 头 ⇒「同一个 session、同一个 Bearer token」这句话是
被断言的，不是被假定的。替身复用 ``tests/_r259_queue_ruler``（不新造一套桩），只补它从前
**不该打**的那一发 ``/api/v1/approve``。
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
from urllib.parse import urlparse

import pytest

from tests import _r259_queue_ruler as Q

REPO_ROOT = Q.REPO_ROOT
COLLECTOR_PATH = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"
SIDECAR_BASE_KEYS = Q.SIDECAR_BASE_KEYS
R123_EXTRA_KEYS = Q.R123_EXTRA_KEYS
PARK_NOTICE = Q.PARK_NOTICE
#: 批准端点的真路径（与量具 ``APPROVAL_PATH`` 逐字对判；``chat.router`` 挂在 ``/api/v1`` 上）。
APPROVAL_PATH = "/api/v1/approve"
#: 既有十枚队列 kind（``_r259_queue_ruler`` 只有五枚 + 三枚没读到终局，这里补齐 R259 那一枚）。
TEN_QUEUE_KINDS = ("queued_polled", "queued_done_no_bytes", Q.PARKED_KIND,
                   "queued_cancelled", "queued_dead", "queued_expired", "queued_failed",
                   "queued_stalled", "queued_deadline", "queued_no_status")
#: 同步流道的四枚 kind（判据④：这一族一枚都不许多、一枚都不许改）。
SYNC_KINDS = ("ok", "approved_ok", "hitl", "error_event")

#: 批准之后由恢复流交回的终答与出处（形状抄自同步道那枚 ``sources`` 事件）。
APPROVED_TEXT = "批准之后跑出来的终答：Q3 营收 1,284 万元，同比 +12%。"
APPROVED_ROWS = [{"worker": "doc", "source": "经营月报.pdf", "source_id": "doc-1"},
                 {"worker": "data", "source": "sales.csv", "source_id": "data-1"}]
APPROVE_STREAM = [("step", {"tool": "export", "status": "completed"}),
                  ("text", {"content": APPROVED_TEXT}),
                  ("sources", {"data": {"sources": APPROVED_ROWS, "hit_count": 2}}),
                  ("done", {"type": "done"})]
#: 批准之后图又停在下一个闸：那一帧正文就是挂起文案（chat.py 的 hitl_park_text 走 text 道）。
APPROVE_PARK_AGAIN = [("text", {"content": PARK_NOTICE}),
                      ("hitl", {"type": "hitl", "pending": ["export"], "labels": ["📋 导出报告"]}),
                      ("done", {"type": "done"})]


def load_collector():
    spec = importlib.util.spec_from_file_location("r447_collect_answers", str(COLLECTOR_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLLECTOR = load_collector()


class QueueOpener:
    """只挡网络：逐发记 URL / JSON 体 / Authorization 头（``test_r123`` 那具记录器的形状）。

    ``statuses`` 逐发交回 ``/queue/status`` 载荷，读完还不停就抛 ⇒「这一枚终态真停住了表」
    是被量到的而不是被脚本刚好耗尽。``approves`` 同理：不该打的批准轮一旦被打了，红的就是
    批准轮这一格，不会漂到别的断言上去。
    """

    def __init__(self, ask_events=(), statuses=(), approves=()):
        self.ask_events = list(ask_events)
        self.statuses = list(statuses)
        self.approves = list(approves)
        self.calls = []

    def open(self, request, timeout=None):
        path = urlparse(request.full_url).path
        body = request.data
        self.calls.append({"path": path, "method": request.get_method(),
                           "payload": json.loads(body.decode("utf-8")) if body else None,
                           "authorization": request.get_header("Authorization")})
        if path == "/api/v1/login":
            return Q.FakeResponse(body=json.dumps({"token": Q.TOKEN_VALUE}).encode("utf-8"))
        if path.startswith("/api/v1/queue/status/"):
            if not self.statuses:
                raise AssertionError("状态全读完了还在轮 ⇒ 这一枚终态没停住表")
            item = self.statuses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return Q.FakeResponse(body=json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if path == APPROVAL_PATH:
            if not self.approves:
                raise AssertionError("这一枚结局不该打批准轮：" + path)
            item = self.approves.pop(0)
            if isinstance(item, BaseException):
                raise item
            return Q.FakeResponse(lines=Q.sse(item))
        if path == "/api/v1/ask":
            return Q.FakeResponse(lines=Q.sse(self.ask_events))
        raise AssertionError("本单不该打这一发：" + path)

    def only(self, path):
        return [call for call in self.calls if call["path"] == path]

    def paths(self):
        return [call["path"] for call in self.calls]


def drive(module, opener, row):
    """走真 ``transport`` 的完整一题：两份证据件落 tmp_path，回 (payload, sidecar, 帧账)。"""
    module._OPENER = opener
    payload = module.transport(row)
    return payload, Q.read_jsonl(module.SIDECAR), Q.read_jsonl(module.frame_ledger_path())


@pytest.fixture
def adapter(tmp_path):
    """一具装进观测态的量具：假钟、假凭据、两份证据件落 tmp_path，仓内零字节。"""
    return Q.configure(Q.load("r447_transport_under_test"), tmp_path, name="r447")


def redact_sessions(line):
    """每题一枚 ``uuid4().hex``：金样对判前把它折成 ``<SESSION>``，其余逐字符比。"""
    return re.sub(r'"[0-9a-f]{32}"', '"<SESSION>"', line)


# ==================== 判据① + ②：批准轮必须走，新 kind 不许混 ====================

def assert_parked_turn_is_approved(module, tmp_path, approves=None, rounds=1):
    """挂起的那一轮：批准到终答并交回评分器（判据①），kind 自成一枚（判据②）。"""
    Q.configure(module, tmp_path, name="r447-approved")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.parked_body()],
                         approves=list(approves if approves is not None else [APPROVE_STREAM]))
    payload, sidecar, frames = drive(module, opener, {"id": "report-01", "question": "Q3 营收多少？",
                                                      "tier": "报告"})
    record, row = sidecar[0], frames[0]
    assert payload["answer"] == APPROVED_TEXT, (
        "判据①：批准后的终答没交回评分器（交回的是 " + repr(payload["answer"]) + "）")
    assert payload["evidence"] == APPROVED_ROWS, (
        "判据①：批准那条流交回的出处没跟着进评分器（" + repr(payload["evidence"]) + "）")
    assert record["kind"] == module.QUEUED_APPROVED_KIND == "queued_approved", (
        "判据②：批到终答没落 queued_approved（读成 " + repr(record["kind"]) + "）")
    assert record["kind"] != "queued_polled" and record["kind"] != "approved_ok", (
        "判据②：队列道批到终答冒充了别的 kind")
    assert record["pre_kind"] == Q.PARKED_KIND, (
        "判据②：pre_kind 没记下批准之前的停表读数（" + repr(record["pre_kind"]) + "）")
    assert record["sentinel"] is False and record["answer_chars"] == len(APPROVED_TEXT), (
        "判据①：批到终答的一枚不许带哨兵")
    assert record["approved"] is True and record["approval_rounds"] == rounds, (
        "判据①：批准轮数没记进侧车（rounds=" + repr(record["approval_rounds"]) + "）")
    assert record["approval_http_status"] == 200 and record["approval_error"] == ""
    assert record["evidence_n"] == len(APPROVED_ROWS)
    assert "pre_answer" not in record, "队列道一枚都不写 pre_answer（挂起交回的是零字节）"
    assert payload["first_token_at"] is None, (
        "队列道 first_token_at 留 null：后台那一程的首字观测不到（不许混第二种零点）")
    assert payload["tool_calls"] == 1 and set(payload) == {"answer", "evidence", "first_token_at",
                                                           "thinking_chars", "tool_calls"}
    asks, approves_calls = opener.only("/api/v1/ask"), opener.only(APPROVAL_PATH)
    assert [call["method"] for call in approves_calls] == ["POST"] * rounds
    assert approves_calls[0]["payload"] == {"session_id": asks[0]["payload"]["session_id"],
                                            "approved": True}, (
        "判据①：批准没按契约走（session_id 不是本题那一枚）")
    assert approves_calls[0]["authorization"] == asks[0]["authorization"] == (
        "Bearer " + Q.TOKEN_VALUE), "判据①：批准换了票 ⇒ 不是「跑分账号批自己挂起的那一轮」"
    assert len(approves_calls) == rounds and not opener.approves, "批准轮数与恢复流对不上"
    assert row["kind"] == "queued_approved" and row["queue"]["final"] == "awaiting_approval"
    assert row["queue"]["terminal"]["approval_notice_chars"] == len(PARK_NOTICE), (
        "判据①：批准轮不该把可读面的挂起读数弄丢")
    written = (str(module.SIDECAR.read_text(encoding="utf-8"))
               + module.frame_ledger_path().read_text(encoding="utf-8"))
    assert PARK_NOTICE not in written and PARK_NOTICE not in json.dumps(
        payload, ensure_ascii=False, default=str), "判据①：那句挂起文案又冒充正文了"
    assert module._PARKED == 1 and module._BLANKS == 0 and module._APPROVAL_FAILURES == 0
    assert module.summary()["queued_approved_turns"] == 1
    return payload, record, row


def test_a_parked_queue_turn_is_approved_to_the_terminal_answer(adapter, tmp_path):
    """判据①：读到 awaiting_approval 不再交空正文 —— 批准轮真打了 POST /api/v1/approve。"""
    assert adapter.APPROVAL_PATH == APPROVAL_PATH, "批准端点的抄本漂了"
    assert_parked_turn_is_approved(adapter, tmp_path / "approved")


def test_a_second_approval_round_is_walked_when_the_resume_stream_parks_again(adapter, tmp_path):
    """判据①：批准后图又停在下一个闸 ⇒ 再批一轮（上限 EVAL_APPROVAL_ROUNDS），文案仍旧不交回。"""
    assert_parked_turn_is_approved(
        adapter, tmp_path / "twice",
        approves=[APPROVE_PARK_AGAIN, APPROVE_STREAM], rounds=2)


def test_a_parked_queue_turn_that_cannot_be_approved_is_approval_failed(adapter, tmp_path):
    """判据① 后半：批准没被接受 ⇒ approval_failed（正文空、出处空、sentinel=true）。"""
    Q.configure(adapter, tmp_path, name="r447-failed")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.parked_body()],
                         approves=[Q.http_error(403)])
    payload, sidecar, frames = drive(adapter, opener, {"id": "report-02", "question": "Q",
                                                       "tier": "报告"})
    record = sidecar[0]
    assert record["kind"] == "approval_failed", "批准失败没落 approval_failed（" + repr(record["kind"]) + "）"
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL
    assert payload["evidence"] == [] and record["sentinel"] is True
    assert payload["answer"] != PARK_NOTICE and PARK_NOTICE not in json.dumps(payload, default=str)
    assert record["approved"] is False and record["approval_http_status"] == 403
    assert "approve HTTP 403" in record["approval_error"], record["approval_error"]
    assert record["pre_kind"] == Q.PARKED_KIND and "pre_answer" not in record
    assert adapter._APPROVAL_FAILURES == 1 and adapter._BLANKS == 0, "批准失败不该喂白烧闸"
    assert frames[0]["queue"]["final"] == "awaiting_approval"


def test_the_approval_round_exhausting_its_rounds_still_never_delivers_the_notice(adapter, tmp_path):
    """批到上限还挂着 ⇒ approval_failed，一句文案都不交回（R123 甲案口径分家不分家都一样）。"""
    Q.configure(adapter, tmp_path, name="r447-exhaust")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.parked_body()],
                         approves=[APPROVE_PARK_AGAIN] * 3)
    payload, sidecar, _frames = drive(adapter, opener, {"id": "report-03", "question": "Q",
                                                        "tier": "报告"})
    assert sidecar[0]["kind"] == "approval_failed" and sidecar[0]["approval_rounds"] == 3
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL and payload["evidence"] == []
    assert PARK_NOTICE not in json.dumps(payload, ensure_ascii=False, default=str)


# ==================== 判据③：出处随答案交回 ====================

def assert_polled_sources_are_delivered(module, tmp_path, body=None):
    """可读面交了 N 枚出处 ⇒ 评分器那一份必须正好拿到 N 枚，逐字同一身行。"""
    body = json.loads(json.dumps(Q.answered_body())) if body is None else body
    expected = [row for row in body["sources"] if isinstance(row, dict)]
    Q.configure(module, tmp_path, name="r447-polled")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[body])
    row_id = "metric-16" if expected else "report-06"
    payload, sidecar, frames = drive(module, opener, {"id": row_id, "question": "Q3 营收多少？",
                                                      "tier": "报告"})
    record, frame_row = sidecar[0], frames[0]
    terminal = frame_row["queue"]["terminal"]
    assert record["kind"] == "queued_polled" and payload["answer"] == body["result"]
    assert payload["evidence"] == expected, (
        "判据③：可读面交了 " + str(len(expected)) + " 枚出处而评分器拿到 "
        + str(len(payload["evidence"])) + " 枚")
    assert terminal["sources_n"] == len(expected), "取回账的枚数与载荷对不上（" + repr(terminal["sources_n"]) + "）"
    assert record["evidence_n"] == terminal["sources_n"], (
        "判据③：侧车 evidence_n 与可读面 sources_n 对不上（逐枚点名差在哪）")
    assert record["pre_evidence_n"] == len(expected)
    answer = COLLECTOR.build_answer({"id": row_id}, payload, measured_ms=1234.5,
                                    answer_source="eval_transport_ask_v2:transport")
    COLLECTOR.assert_line_contract(answer)
    assert answer["evidence"] == expected, "判据③：落进 answers 文件的那一份又空了"
    assert "sources_rows" not in frame_row["queue"], "出处行不该抄进第二份证据件（帧账只留计数）"
    assert set(frame_row) == Q.FRAME_ROW_KEYS, (
        "判据②：帧账那一行的键集漂了 " + str(set(frame_row) ^ Q.FRAME_ROW_KEYS))
    assert tuple(list(record)[:9]) == SIDECAR_BASE_KEYS, "判据②：侧车那一行的键集与顺序漂了"
    assert set(record) - set(SIDECAR_BASE_KEYS) <= (R123_EXTRA_KEYS | {"pre_answer"}), (
        "判据②：侧车那一行的键集多出了新键（甲案七键子集那枚钉）")
    return payload, record, frame_row


def test_queued_polled_delivers_the_readable_face_sources(adapter, tmp_path):
    """run9c 的病根：7 枚 sources_n>0 而 evidence 全空 ⇒ 今天逐枚交回。"""
    payload, record, frame_row = assert_polled_sources_are_delivered(adapter, tmp_path / "polled")
    assert record["evidence_n"] == 3 and len(payload["evidence"]) == 3


def test_a_zero_source_answered_row_delivers_nothing_and_says_zero(adapter, tmp_path):
    """可读面真说「零枚」⇒ 交回空表是达标，不是缺证词（与「说不出」是两件事）。"""
    body = Q.answered_body(sources=[], sources_present=False)
    _payload, record, frame_row = assert_polled_sources_are_delivered(
        adapter, tmp_path / "zero", body=body)
    assert frame_row["queue"]["terminal"]["sources_n"] == 0
    assert Q.sources_cell(frame_row["queue"]) == "read_zero"
    assert record["evidence_n"] == 0


def test_a_legacy_row_never_launders_its_placeholder_sources(adapter, tmp_path):
    """旧行说不出自己有没有出处 ⇒ 不拿占位空表洗成「查过了，零枚」，也不补出处。"""
    Q.configure(adapter, tmp_path, name="r447-legacy")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.legacy_row_body()], approves=[])
    payload, sidecar, frames = drive(adapter, opener, {"id": "report-04", "question": "Q",
                                                       "tier": "报告"})
    assert sidecar[0]["kind"] == "queued_polled"
    assert payload["evidence"] == []
    assert frames[0]["queue"]["terminal"]["sources_n"] is None, "旧行那一格读不出枚数"
    assert Q.sources_cell(frames[0]["queue"]) == "row_cannot_say"
    assert opener.only(APPROVAL_PATH) == []


# ==================== 判据① 后半段：legacy 那一路的挂起文案 ====================

def assert_notice_row_goes_to_the_approval_round(module, tmp_path):
    """点名判据（判据① 后半段）：文案行不是终答，它进批准轮。"""
    Q.configure(module, tmp_path, name="r447-notice")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM,
                         statuses=[Q.legacy_row_body(park_notice=True)],
                         approves=[APPROVE_STREAM])
    payload, sidecar, frames = drive(module, opener, {"id": "report-05", "question": "Q",
                                                      "tier": "报告"})
    record = sidecar[0]
    assert PARK_NOTICE not in payload["answer"] and payload["answer"] == APPROVED_TEXT, (
        "判据①：那句 37 字挂起文案又当正文交回评分器了")
    assert record["kind"] == "queued_approved", (
        "判据①：文案行没被认成「还在等人批准」（读成 " + repr(record["kind"]) + "）")
    assert record["pre_kind"] == "queued_polled", "停表读数照旧是取回了一份字，别的不许改写"
    assert record["pre_answer_chars"] == len(PARK_NOTICE) and "pre_answer" not in record
    assert frames[0]["queue"]["terminal"]["answer_is_park_notice"] is True
    assert module._PARKED == 1 and module._BLANKS == 0
    return payload, record


def test_a_legacy_park_notice_row_is_not_scored_as_an_answer(adapter, tmp_path):
    """result 逐字就是那句文案 ⇒ 「取回了一份字」不等于「取回了一份终答」，进批准轮。"""
    assert_notice_row_goes_to_the_approval_round(adapter, tmp_path / "notice")


# ==================== 判据⑤ 戊：dead / done_no_bytes 不许并进挂起族 ====================

def assert_unanswered_never_enters_the_approval_family(module, tmp_path, status_body,
                                                       expected_kind):
    """后端已宣布这一轮不会有正文 ⇒ 一枚批准轮都不许多打，白烧闸照旧喂（判据⑤ 戊的正面）。"""
    Q.configure(module, tmp_path, name="r447-not-parked")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[status_body],
                         approves=[APPROVE_STREAM])
    payload, sidecar, _frames = drive(module, opener, {"id": "report-06", "question": "Q",
                                                       "tier": "报告"})
    assert sidecar[0]["kind"] == expected_kind, (
        "判据⑤ 戊：未答终态被并进了挂起族（读成 " + repr(sidecar[0]["kind"]) + "）")
    assert payload["answer"] == module.BLANK_SENTINEL and payload["evidence"] == []
    assert opener.only(APPROVAL_PATH) == [], "这一枚结局不该打批准轮"
    assert module._PARKED == 0 and module._BLANKS == 1, "白烧闸口径漂了"
    assert sidecar[0]["approved"] is False and sidecar[0]["approval_rounds"] == 0


@pytest.mark.parametrize("status_body,expected_kind", [
    (Q.bare_done_body(status="dead"), "queued_dead"),
    ({"status": "done"}, "queued_done_no_bytes"),
    (Q.bare_done_body(status="cancelled"), "queued_cancelled"),
])
def test_an_unanswered_terminal_never_enters_the_approval_family(adapter, tmp_path, status_body,
                                                                expected_kind):
    assert_unanswered_never_enters_the_approval_family(
        adapter, tmp_path / expected_kind, status_body, expected_kind)


def test_queued_approved_is_not_one_of_the_ten_stop_kinds(adapter):
    """判据②：新 kind 只长在批准那一层，十枚停表读数与总控那枚 AST 钉一个字没动。"""
    assert adapter.QUEUED_APPROVED_KIND == "queued_approved"
    assert adapter.QUEUED_APPROVED_KIND not in TEN_QUEUE_KINDS
    assert adapter.QUEUED_APPROVED_KIND not in SYNC_KINDS
    seen = set()
    for status, expected in sorted(Q.FINAL_KINDS.items()):
        body = {"status": status}
        if status == "done":
            body["result"] = Q.ANSWER
        seen.add(Q.poll(adapter, [body])[0][0])
    seen.add(Q.poll(adapter, [{"status": "done"}])[0][0])
    seen.add(Q.poll(adapter, [Q.parked_body()])[0][0])
    seen.add(Q.poll(adapter, [{"status": "processing"}] * 500)[0][0])
    seen.add(Q.poll(adapter, [{"status": "queued", "position": n + 1} for n in range(400)])[0][0])
    seen.add(Q.poll(adapter, [Q.url_error()] * 400)[0][0])
    assert seen == set(TEN_QUEUE_KINDS), seen ^ set(TEN_QUEUE_KINDS)
    assert adapter.QUEUED_APPROVED_KIND not in seen
    stops = Q.stop_vocabulary(REPO_ROOT)
    assert "awaiting_approval" in stops and set(Q.FINAL_KINDS) <= set(stops), stops
    assert stops == sorted(set(stops))


# ==================== 判据④：同步流道逐字节不变（与基点金样对判） ====================
# 三行金样由基点 227949e 的 scripts/eval_transport_ask_v2.py 在同一具假钟、同一份假出口、
# 同一份 tmp_path 配置下跑出，session_id（每题一枚 uuid4().hex）折成 <SESSION>，其余逐字符比。
# 判据④ 点名的四枚里今天能交到采集器手上的就是这三枚：``hitl`` 自 R123 甲案起只作为
# ``pre_kind`` 露脸（park 那一枚金样里就是它），终答要么批下来（approved_ok）要么落
# approval_failed —— 所以它也在金样的覆盖里。

GOLDEN_CLEAN_SIDE = (
    '{"id": "metric-01", "kind": "ok", "attempt": 1, "sentinel": false, "evidence_n": 1, "answer_'
    'chars": 6, "tool_calls": 1, "wall_ms": 0.0, "ts": "FIXED-TS", "pre_kind": "ok", "pre_answer_'
    'chars": 6, "pre_evidence_n": 1, "approved": false, "approval_rounds": 0, "approval_http_stat'
    'us": null, "approval_error": ""}'
)
GOLDEN_CLEAN_FRAME = (
    '{"id": "metric-01", "kind": "ok", "attempt": 1, "sentinel": false, "session_id": "<SESSION>"'
    ', "ts": "FIXED-TS", "frames": [{"stream": 0, "at": 1, "arrival_at": 1790000000.0, "elapsed_m'
    's": 0.0, "chars": 6, "sha": "c8cdb432717b", "prefix_break": false}], "events": [{"stream": 0'
    ', "at": 1, "event": "step", "class": "render", "arrival_at": 1790000000.0, "elapsed_ms": 0.0'
    '}, {"stream": 0, "at": 2, "event": "text", "class": "render", "arrival_at": 1790000000.0, "e'
    'lapsed_ms": 0.0}, {"stream": 0, "at": 3, "event": "sources", "class": "render", "arrival_at"'
    ': 1790000000.0, "elapsed_ms": 0.0}, {"stream": 0, "at": 4, "event": "done", "class": "termin'
    'al", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}], "stream_clock": [{"stream": 0, "reques'
    't_sent_at": 1790000000.0, "first_event_at": 1790000000.0, "elapsed_base": "request_sent_at"}'
    '], "queue": {}, "first_visible_at": 1790000000.0, "first_visible_event": "step", "first_visi'
    'ble_ms": 0.0, "text_frames": 1, "prefix_breaks": 0, "corrective_replacements": 0, "uncorrect'
    'ed_breaks": 0, "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answer": true, "last'
    '_frame_chars": 6, "last_frame_sha": "c8cdb432717b", "answer_chars": 6, "answer_sha": "c8cdb4'
    '32717b", "streams": 1, "max_stream_frames": 1, "per_stream": [{"frames": 1, "breaks": 0, "fi'
    'rst_break_at": 0}], "criterion_two_holds": false}'
)
GOLDEN_CLEAN_PAYLOAD = {"answer": "终端答案文本", "evidence": [{"locator": "第3页", "source_name": "差旅制度"}],
                        "first_token_at": 1790000000.0, "thinking_chars": None, "tool_calls": 1}

GOLDEN_PARK_SIDE = (
    '{"id": "report-01", "kind": "approved_ok", "attempt": 1, "sentinel": false, "evidence_n": 1,'
    ' "answer_chars": 6, "tool_calls": 1, "wall_ms": 0.0, "ts": "FIXED-TS", "pre_kind": "hitl", "'
    'pre_answer_chars": 37, "pre_evidence_n": 0, "approved": true, "approval_rounds": 1, "approva'
    'l_http_status": 200, "approval_error": "", "pre_answer": "本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答'
    '内容。"}'
)
GOLDEN_PARK_FRAME = (
    '{"id": "report-01", "kind": "approved_ok", "attempt": 1, "sentinel": false, "session_id": "<'
    'SESSION>", "ts": "FIXED-TS", "frames": [{"stream": 0, "at": 1, "arrival_at": 1790000000.0, "'
    'elapsed_ms": 0.0, "chars": 37, "sha": "b50b23c46bcc", "prefix_break": false}, {"stream": 1, '
    '"at": 1, "arrival_at": 1790000000.0, "elapsed_ms": 0.0, "chars": 6, "sha": "fcd91d900376", "'
    'prefix_break": false}], "events": [{"stream": 0, "at": 1, "event": "text", "class": "render"'
    ', "arrival_at": 1790000000.0, "elapsed_ms": 0.0}, {"stream": 0, "at": 2, "event": "hitl", "c'
    'lass": "render", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}, {"stream": 0, "at": 3, "eve'
    'nt": "done", "class": "terminal", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}, {"stream":'
    ' 1, "at": 1, "event": "step", "class": "render", "arrival_at": 1790000000.0, "elapsed_ms": 0'
    '.0}, {"stream": 1, "at": 2, "event": "text", "class": "render", "arrival_at": 1790000000.0, '
    '"elapsed_ms": 0.0}, {"stream": 1, "at": 3, "event": "sources", "class": "render", "arrival_a'
    't": 1790000000.0, "elapsed_ms": 0.0}, {"stream": 1, "at": 4, "event": "done", "class": "term'
    'inal", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}], "stream_clock": [{"stream": 0, "requ'
    'est_sent_at": 1790000000.0, "first_event_at": 1790000000.0, "elapsed_base": "request_sent_at'
    '"}, {"stream": 1, "request_sent_at": null, "first_event_at": 1790000000.0, "elapsed_base": "'
    'first_event_at"}], "queue": {}, "first_visible_at": 1790000000.0, "first_visible_event": "st'
    'ep", "first_visible_ms": 0.0, "text_frames": 2, "prefix_breaks": 0, "corrective_replacements'
    '": 0, "uncorrected_breaks": 0, "missing_chars": 0, "extra_chars": 0, "last_frame_covers_answ'
    'er": true, "last_frame_chars": 6, "last_frame_sha": "fcd91d900376", "answer_chars": 6, "answ'
    'er_sha": "fcd91d900376", "streams": 2, "max_stream_frames": 1, "per_stream": [{"frames": 1, '
    '"breaks": 0, "first_break_at": 0}, {"frames": 1, "breaks": 0, "first_break_at": 0}], "criter'
    'ion_two_holds": false}'
)
GOLDEN_PARK_PAYLOAD = {"answer": "导出后的终答", "evidence": [{"locator": "第9行", "source_name": "口径登记表"}],
                       "first_token_at": 1790000000.0, "thinking_chars": None, "tool_calls": 1}

GOLDEN_ERR_SIDE = (
    '{"id": "tool-01", "kind": "error_event", "attempt": 1, "sentinel": false, "evidence_n": 0, "'
    'answer_chars": 14, "tool_calls": 0, "wall_ms": 0.0, "ts": "FIXED-TS", "pre_kind": "error_eve'
    'nt", "pre_answer_chars": 14, "pre_evidence_n": 0, "approved": false, "approval_rounds": 0, "'
    'approval_http_status": null, "approval_error": ""}'
)
GOLDEN_ERR_FRAME = (
    '{"id": "tool-01", "kind": "error_event", "attempt": 1, "sentinel": false, "session_id": "<SE'
    'SSION>", "ts": "FIXED-TS", "frames": [], "events": [{"stream": 0, "at": 1, "event": "error",'
    ' "class": "render", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}, {"stream": 0, "at": 2, "'
    'event": "done", "class": "terminal", "arrival_at": 1790000000.0, "elapsed_ms": 0.0}], "strea'
    'm_clock": [{"stream": 0, "request_sent_at": 1790000000.0, "first_event_at": 1790000000.0, "e'
    'lapsed_base": "request_sent_at"}], "queue": {}, "first_visible_at": 1790000000.0, "first_vis'
    'ible_event": "error", "first_visible_ms": 0.0, "text_frames": 0, "prefix_breaks": 0, "correc'
    'tive_replacements": 0, "uncorrected_breaks": 0, "missing_chars": 0, "extra_chars": 14, "last'
    '_frame_covers_answer": false, "last_frame_chars": 0, "last_frame_sha": "e3b0c44298fc", "answ'
    'er_chars": 14, "answer_sha": "2240862cd8c8", "streams": 1, "max_stream_frames": 0, "per_stre'
    'am": [{"frames": 0, "breaks": 0, "first_break_at": 0}], "criterion_two_holds": false}'
)
GOLDEN_ERR_PAYLOAD = {"answer": "本轮未产出任何结论，请重试。", "evidence": [], "first_token_at": None,
                      "thinking_chars": None, "tool_calls": 0}

SYNC_STREAMS = {
    "clean": {"row": {"id": "metric-01", "question": "Q", "tier": "分析"},
              "script": {"/api/v1/ask": [
                  ("step", {"type": "step", "name": "doc"}),
                  ("text", {"type": "text", "content": "终端答案文本"}),
                  ("sources", {"data": {"sources": [{"source_name": "差旅制度", "locator": "第3页"}],
                                         "hit_count": 1}}),
                  ("done", {"type": "done"})]},
              "sidecar": GOLDEN_CLEAN_SIDE, "frame": GOLDEN_CLEAN_FRAME,
              "payload": GOLDEN_CLEAN_PAYLOAD},
    "park": {"row": {"id": "report-01", "question": "Q", "tier": "报告"},
             "script": {"/api/v1/ask": [
                 ("text", {"type": "text", "content": PARK_NOTICE}),
                 ("hitl", {"type": "hitl", "pending": ["export"], "labels": ["📋 导出报告"]}),
                 ("done", {"type": "done"})],
                 APPROVAL_PATH: [
                     ("step", {"type": "step", "name": "export"}),
                     ("text", {"type": "text", "content": "导出后的终答"}),
                     ("sources", {"data": {"sources": [{"source_name": "口径登记表",
                                                        "locator": "第9行"}], "hit_count": 1}}),
                     ("done", {"type": "done"})]},
             "sidecar": GOLDEN_PARK_SIDE, "frame": GOLDEN_PARK_FRAME,
             "payload": GOLDEN_PARK_PAYLOAD},
    "err": {"row": {"id": "tool-01", "question": "Q", "tier": "问答"},
            "script": {"/api/v1/ask": [
                ("error", {"type": "error", "content": "本轮未产出任何结论，请重试。"}),
                ("done", {"type": "done"})]},
            "sidecar": GOLDEN_ERR_SIDE, "frame": GOLDEN_ERR_FRAME,
            "payload": GOLDEN_ERR_PAYLOAD},
}


class SyncOpener:
    """同步道那一路的假出口：按路径交回流，一次都不碰 /queue/status。"""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def open(self, request, timeout=None):
        path = urlparse(request.full_url).path
        self.calls.append(path)
        if path == "/api/v1/login":
            return Q.FakeResponse(body=json.dumps({"token": Q.TOKEN_VALUE}).encode("utf-8"))
        outcome = self.script.get(path)
        if isinstance(outcome, BaseException):
            raise outcome
        return Q.FakeResponse(lines=Q.sse(outcome or []))


@pytest.mark.parametrize("label", sorted(SYNC_STREAMS))
def test_the_sync_lane_still_writes_the_base_revision_bytes(adapter, tmp_path, label):
    """判据④：``ok`` / ``approved_ok`` / ``error_event`` 三路逐字节 = 基点金样。"""
    case = SYNC_STREAMS[label]
    Q.configure(adapter, tmp_path, name="r447-sync-" + label)
    adapter._OPENER = SyncOpener(case["script"])
    payload = adapter.transport(dict(case["row"]))
    side = redact_sessions(adapter.SIDECAR.read_text(encoding="utf-8").strip())
    frame = redact_sessions(adapter.frame_ledger_path().read_text(encoding="utf-8").strip())
    assert side == case["sidecar"], "判据④：侧车那一行的字节漂了（" + label + "）"
    assert frame == case["frame"], "判据④：帧账那一行的字节漂了（" + label + "）"
    assert payload == case["payload"], "判据④：交回采集器的那一份漂了（" + label + "）"


# ==================== 判据⑥：判读件的两格 + 「取不到，不编数」 ====================

def load_readout(name="r447_readout"):
    spec = importlib.util.spec_from_file_location(
        name, str(REPO_ROOT / "scripts" / "eval_lane_readout.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_lane_artifacts(module, tmp_path, label="r447-readout"):
    """一扇假窗：一枚批到终答、一枚取回带出处、一枚 dead；answers 由真采集器落盘。"""
    Q.configure(module, tmp_path, name=label)
    outcomes = []
    for row_id, statuses, approves in (
            ("report-01", [Q.parked_body()], [APPROVE_STREAM]),
            ("metric-16", [Q.answered_body()], []),
            ("report-04", [Q.bare_done_body(status="dead")], [])):
        module._OPENER = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=statuses,
                                     approves=approves)
        payload = module.transport({"id": row_id, "question": "Q3 营收多少？", "tier": "报告"})
        outcomes.append((row_id, payload))
    answers_path = tmp_path / ("answers-" + label + ".jsonl")
    with io.open(str(answers_path), "w", encoding="utf-8") as handle:
        for row_id, payload in outcomes:
            handle.write(json.dumps(COLLECTOR.build_answer(
                {"id": row_id}, payload, measured_ms=1000.0,
                answer_source="eval_transport_ask_v2:transport"), ensure_ascii=False) + "\n")
    return label, answers_path, outcomes


def test_the_readout_judges_the_approval_round_and_the_provenance(tmp_path, capsys):
    """判据⑥ 的正面：批准轮那一格逐枚点名，出处交回对判读得出「达标」。"""
    label, _answers, _outcomes = build_lane_artifacts(Q.load("r447_readout_src"), tmp_path)
    readout = load_readout()
    rc = readout.main(["--label", label, "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "批到终答=1 题号=['report-01']" in out, out
    assert "仍停在挂起读数（批准轮没走）=0 题号=无" in out, out
    assert "批准失败=0 题号=无" in out, out
    assert "出处交回对判（可读面 sources_n>0 ↔ answers.evidence 枚数）：对不上=0" in out, out
    assert "达标 —— 可读面说了几枚，交出去的就是几枚" in out, out
    assert "queued_approved" in out and "'report-04': 3" not in out, out


def test_the_readout_names_every_provenance_gap_instead_of_silence(tmp_path, capsys):
    """判据⑥：交回侧空了，判读件必须点名到题号并判不达标（不许静默跳过、不许补零）。"""
    label, answers_path, _outcomes = build_lane_artifacts(Q.load("r447_gap_src"), tmp_path)
    rows = [json.loads(line) for line in io.open(str(answers_path), encoding="utf-8")]
    for row in rows:
        row["evidence"] = []  # 手工制造 run9c 那个形状：可读面说了 3 枚而交回去的是零枚
    with io.open(str(answers_path), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    readout = load_readout("r447_readout_gap")
    rc = readout.main(["--label", label, "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "对不上=1 逐枚=[('metric-16', 3, 0)]" in out, out
    assert "🔴 判据③ 不达标" in out, out


def test_the_readout_still_says_it_cannot_read_instead_of_inventing_numbers(tmp_path, capsys):
    """判据⑥ 的后半段：件不在 ⇒ rc=2 明写「取不到，不编数」，一枚都不许补零。"""
    readout = load_readout("r447_readout_missing")
    rc = readout.main(["--label", "run-does-not-exist", "--dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 2, out
    assert "取不到件" in out and "取不到，不编数" in out, out
    assert "🔴 取不到件" in out, out


# ==================== 判据⑤：五把可失败钉（变异只落影子副本） ====================

DROP_APPROVAL_ROUND = ('        if kind == "hitl" or pending_approval:\n',
                       '        if kind == "hitl":\n')
LAUNDER_THE_NOTICE = ('            kind == "queued_polled" and _bytes_are_the_park_notice('
                      'frames["queue"]))', '            False)')
DROP_SOURCE_FOLD = ('                evidence = _queue_evidence(frames["queue"], out["evidence"])',
                    '                evidence = list(out["evidence"])')
WIDEN_SIDECAR_KEYS = ('    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,\n'
                      '           "evidence_n": len(payload.get("evidence") or []),',
                      '    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,\n'
                      '           "sources_n": 0,\n'
                      '           "evidence_n": len(payload.get("evidence") or []),')
MERGE_UNANSWERED_INTO_PARKED = (
    '        pending_approval = kind == "queued_awaiting_approval" or (',
    '        pending_approval = kind in ("queued_awaiting_approval",\n'
    '                                   "queued_dead", "queued_done_no_bytes") or (')


def test_counter_evidence_dropping_the_approval_round_goes_red_here(tmp_path):
    """反证甲（⑤a）：摘掉批准轮 ⇒ 红必须落在「终答没交回」这一格。"""
    module, _ = Q.mutant(tmp_path, "drop_approval_round", *DROP_APPROVAL_ROUND)
    with pytest.raises(AssertionError) as exc:
        assert_parked_turn_is_approved(module, tmp_path / "mut-a")
    assert "批准后的终答没交回评分器" in str(exc.value), str(exc.value)
    Q.configure(module, tmp_path, name="mut-a-reading")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.parked_body()],
                         approves=[APPROVE_STREAM])
    payload, sidecar, _frames = drive(module, opener, {"id": "report-01", "question": "Q",
                                                       "tier": "报告"})
    assert sidecar[0]["kind"] == Q.PARKED_KIND and payload["answer"] == ""
    assert opener.only(APPROVAL_PATH) == [], "批准轮还在打 ⇒ 这枚反证是空的"


def test_counter_evidence_laundering_the_notice_goes_red_here(tmp_path):
    """反证乙（⑤b）：不把挂起文案当挂起 ⇒ 那句 37 字文案直接进评分器，红落在文案这一格。"""
    module, _ = Q.mutant(tmp_path, "launder_notice", *LAUNDER_THE_NOTICE)
    Q.configure(module, tmp_path, name="mut-b")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM,
                         statuses=[Q.legacy_row_body(park_notice=True)], approves=[APPROVE_STREAM])
    payload, sidecar, _frames = drive(module, opener, {"id": "report-05", "question": "Q",
                                                       "tier": "报告"})
    assert payload["answer"] == PARK_NOTICE, str(payload["answer"])
    assert sidecar[0]["kind"] == "queued_polled"
    assert PARK_NOTICE in json.dumps(payload, ensure_ascii=False, default=str), (
        "反证乙是空的：文案没被交出去")
    with pytest.raises(AssertionError) as exc:
        assert_notice_row_goes_to_the_approval_round(module, tmp_path / "mut-b-check")
    assert "挂起文案又当正文交回评分器" in str(exc.value), str(exc.value)


def test_counter_evidence_dropping_the_source_fold_goes_red_here(tmp_path):
    """反证丙（⑤c）：出处搬运被摘 ⇒ sources_n>0 而 evidence 空，红落在「交回」这一格。"""
    module, _ = Q.mutant(tmp_path, "drop_source_fold", *DROP_SOURCE_FOLD)
    with pytest.raises(AssertionError) as exc:
        assert_polled_sources_are_delivered(module, tmp_path / "mut-c")
    assert "而评分器拿到" in str(exc.value), str(exc.value)
    Q.configure(module, tmp_path, name="mut-c-reading")
    opener = QueueOpener(ask_events=Q.QUEUED_STREAM, statuses=[Q.answered_body()], approves=[])
    payload, sidecar, frames = drive(module, opener, {"id": "metric-16", "question": "Q",
                                                      "tier": "报告"})
    assert payload["evidence"] == [] and sidecar[0]["evidence_n"] == 0
    assert frames[0]["queue"]["terminal"]["sources_n"] == 3, "可读面明明说了三枚 ⇒ 这就是差在哪"


def test_counter_evidence_widening_the_sidecar_keys_goes_red_here(tmp_path):
    """反证丁（⑤d）：往侧车那一行并进新键 ⇒ 红落在「甲案七键子集」那枚钉上。"""
    module, _ = Q.mutant(tmp_path, "widen_sidecar_keys", *WIDEN_SIDECAR_KEYS)
    with pytest.raises(AssertionError) as exc:
        assert_polled_sources_are_delivered(module, tmp_path / "mut-d")
    assert "判据②：侧车那一行的键集" in str(exc.value), str(exc.value)


def test_counter_evidence_merging_unanswered_terminals_goes_red_here(tmp_path):
    """反证戊（⑤e）：把 dead / done_no_bytes 并进挂起族 ⇒ 红落在「不该打批准轮」这一格。"""
    module, _ = Q.mutant(tmp_path, "merge_unanswered", *MERGE_UNANSWERED_INTO_PARKED)
    with pytest.raises(AssertionError) as exc:
        assert_unanswered_never_enters_the_approval_family(
            module, tmp_path / "mut-e", Q.bare_done_body(status="dead"), "queued_dead")
    assert "未答终态被并进了挂起族" in str(exc.value), str(exc.value)
