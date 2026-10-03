# -*- coding: utf-8 -*-
"""R585｜`dead` 终态在可读面一个键都不交，客户只看到「没字」（P1）。

缺陷本体（真机单子 `request_id=a55ef916eb43486789a9a68f81cb9f7c`，run15 09:57）：worker
那一头**早就算出了成因码**——日志原文一句 `报告档终态不可重试，不再重投 -> dead:
context_limit_exceeded (reason=non_retryable_terminal attempts=1 max_attempts=3)`；可
`GET /api/v1/queue/status/<id>` 在 `dead` 这一枚终态上**一个键都不交**（量具读出
`terminal.shape="no_keys"`、`schema`／`state`／`sources_present` 全 null），客户屏上只剩
哨兵 `<no-bytes-emitted>`。

本单的形状：**不新造一套原因码**，只把那枚已经算出来的码接上持久面（队列账本里那一笔
`dead_verdict`）与可读面（轮询响应里的 `terminal_state` / `reason` / `retryable`）。
🔴 本单不治上下文窗口参数——那是 R586（已由总控并树 `9c9a0b1`，两半 8192 实测 `paired`）。

五格判据 → 钉（凭据全文见 `docs/testing/r585-dead-terminal-reason-2026-10-03.md`）：

* 判据① 在册码：`test_a_dead_turn_now_speaks_its_reason_on_the_polling_surface` /
  `test_the_reason_is_a_registered_code_for_every_ledger_shape` /
  `test_the_fallback_is_the_one_registered_code_and_no_new_code_lives_in_the_readout`
* 判据② 成功形状一字不改：`test_the_success_terminal_payload_key_order_is_frozen` /
  `test_a_done_answer_still_answers_the_frozen_key_sequence`
* 判据③ 两种 dead 分得开：`test_two_deads_with_identical_counters_stay_tellable_apart` /
  `test_the_verdict_lands_on_the_durable_face_verbatim` /
  `test_a_row_recorded_before_this_change_says_the_reason_but_not_the_verdict`
* 判据④ 三把刀：锚点由 `test_the_three_counter_evidence_anchors_are_still_in_place` 钉在位；
  摘除后的红与摘前摘后 sha256 逐把记在交工纸（本文件不许自带夹具去改生产码）
* 判据⑤ 纸面逐字引日志原文与 `terminal.shape` 读数

跑法（离线：FakeRedis，零容器 / 零模型 / 零 PG / 不碰生产那枚 `a55ef916…` 的账）：
    python -m pytest tests/test_r585_dead_terminal_reason.py -o addopts= -p no:cacheprovider -q
"""
from __future__ import annotations

import json
import logging
import re

import pytest

from app.agents.contracts import CONTEXT_LIMIT_CODE
from app.common import reliable_queue
from tests.test_r448_deterministic_refusal_no_retry import RUN9C_WINDOW_ERROR

#: 在册码那把尺**借**自在册件，本文件不抄第二份（R548/R578 同一口径：尺只有一把）。
from tests.test_r81_queue_terminal_retry import ENUM_CODES
from tests.test_reliable_queue import FakeRedis

SUBJECT = "r585-owner"
#: 判据②那把冻结钉的尺：成功终态载荷的键序（R254 定形、R504 追加末格，本单一格都不许动）。
SUCCESS_TERMINAL_KEYS = [
    "schema",
    "terminal_state",
    "answer_present",
    "worker_status",
    "sources",
    "sources_present",
    "scope_reason_code",
    "sources_error",
    "usage",
    "approval",
]
#: 可读面在 `done` 上交回的键序：`result` 在前、终态十二格在后，两处都由
#: `queue_terminal_readout` 一处的书写顺序决定。多一格、少一格、换序都算改形状。
DONE_RESPONSE_KEYS = [
    "status",
    "request_id",
    "failure",
    "result",
    "terminal_schema",
    "terminal_state",
    "answer_present",
    "answer_is_park_notice",
    "worker_status",
    "sources_present",
    "sources",
    "scope_reason_code",
    "sources_error",
    "usage",
    "approval",
    "terminal_note",
]
#: 死终态这一格从今天起的形状。`usage`／`sources`／`approval` **不在位**是设计而不是漏：
#: 这一轮没跑完，交一枚空值就是把「没说」洗成「说了零」——R254 刚治过的那枚谎不许复发。
DEAD_READOUT_KEYS = [
    "terminal_schema",
    "terminal_state",
    "reason",
    "retryable",
    "answer_present",
    "terminal_note",
]
DEAD_RESPONSE_KEYS = ["status", "request_id", "failure"] + DEAD_READOUT_KEYS


def _watch(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")


def _queue(name, *, max_attempts=3):
    """真 `ReliableQueue` + 假 Redis：与 R448/R81 同一套夹具，不碰容器、不碰生产键。"""
    queue = reliable_queue.ReliableQueue(
        FakeRedis(), name="r585-" + name, lease_seconds=30, max_attempts=max_attempts
    )
    message = queue.enqueue(
        {
            "message": "生成本月差旅费用分析周报",
            "session_id": "session-r585",
            "username": SUBJECT,
            "principal": {"user_id": SUBJECT, "username": SUBJECT, "roles": ["admin"]},
        },
        "idem-r585-" + name,
    )
    return queue, message.request_id


def _ledger(queue, request_id) -> dict:
    """持久面原文：message 键上那本 JSON。判据③要看的正是这一格真落了字没有。"""
    raw = queue.redis.get(queue._message_key(request_id))
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


def _strip_verdict(queue, request_id) -> None:
    """把本单新加的那一笔账从一枚在位行上摘掉，复现「R585 之前」的那份形状。"""
    ledger = _ledger(queue, request_id)
    ledger.pop(reliable_queue.DEAD_VERDICT_LEDGER_KEY, None)
    queue.redis.set(
        queue._message_key(request_id),
        json.dumps(ledger, ensure_ascii=False, separators=(",", ":")),
    )


def _client_for(monkeypatch, queue):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "admin",
            "status": "active",
        },
    )
    return TestClient(app), create_token(SUBJECT)


def _status_body(monkeypatch, queue, request_id) -> dict:
    """走真路由（含 R295 那扇门）：判据①②③里那句「可读面」只认这一条读法。"""
    client, token = _client_for(monkeypatch, queue)
    response = client.get(
        f"/api/v1/queue/status/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _readout(queue, request_id) -> dict:
    """同一格读数的进程内读法：只给「门之外」那一族钉用，路由钉一律走 `_status_body`。"""
    from app.api.v1 import chat

    assert queue.status(request_id) == "dead"
    return chat.queue_dead_readout(queue, request_id, reliable_queue.DEAD_STATUS)


# ==================== 判据①：死终态要交回 state=dead ＋ 一枚在册稳定码 ====================


def test_a_dead_turn_now_speaks_its_reason_on_the_polling_surface(monkeypatch, caplog):
    """判据①（真链路）：日志里本来就有那枚码，今天同一扇门必须也交出来。"""
    from deploy import queue_worker

    _watch(caplog)
    queue, request_id = _queue("run15-chain")
    queue.reserve()
    record = queue_worker.report_failure_record(Exception(RUN9C_WINDOW_ERROR))
    queue_worker._fail_report_turn(queue, request_id, record, session_id="", write_back=False)

    assert queue.status(request_id) == "dead"
    logged = [item.getMessage() for item in caplog.records]
    line = next(text for text in logged if "不再重投" in text)
    assert "-> dead: %s " % CONTEXT_LIMIT_CODE in line, "先证日志里本来就有这枚码"
    assert "reason=non_retryable_terminal" in line

    body = _status_body(monkeypatch, queue, request_id)
    assert list(body) == DEAD_RESPONSE_KEYS, list(body)
    assert body["status"] == "dead"
    assert body["terminal_state"] == "dead"
    assert body["reason"] == CONTEXT_LIMIT_CODE, "日志里有、面上没有——本单治的就是这一格"
    assert body["reason"] in ENUM_CODES, "面上那枚码必须本来就在那把尺里"
    assert body["terminal_schema"] == reliable_queue.DEAD_TERMINAL_SCHEMA
    assert body["retryable"] is False
    assert body["answer_present"] is False
    assert body["failure"]["last_error"] == CONTEXT_LIMIT_CODE


def test_the_readout_state_is_the_very_word_the_queue_wrote():
    """判据①：`terminal_state` 逐字回显状态键上那枚词，不在第二处拼写它。"""
    from app.api.v1 import chat

    queue_source = open(reliable_queue.__file__, encoding="utf-8").read()
    assert reliable_queue.DEAD_STATUS == "dead"
    assert 'self.redis.set(self._status_key(request_id), "dead")' in queue_source

    chat_source = open(chat.__file__, encoding="utf-8").read()
    assert "elif status == reliable_queue.DEAD_STATUS:" in chat_source
    assert chat_source.count('"terminal_state": status,') == 1


@pytest.mark.parametrize(
    "recorded,expected",
    [
        (CONTEXT_LIMIT_CODE, CONTEXT_LIMIT_CODE),
        ("model_unavailable", "model_unavailable"),
        ("queue_unavailable", "queue_unavailable"),
        ("internal_error", "internal_error"),
        # 这三枚今天真在吐，但按 R142 那本账留在封闭枚举外：面上不许拿它们当稳定码卖。
        ("lease_expired", "internal_error"),
        ("authorization_required", "internal_error"),
        ("no_model_call_recorded", "internal_error"),
        (reliable_queue.RESULT_DISCARDED + ":lease_lost", "internal_error"),
        ("模型暂时不可用", "internal_error"),
        ("", "internal_error"),
    ],
    ids=[
        "context-limit",
        "model-unavailable",
        "queue-unavailable",
        "internal-error",
        "lease-expired",
        "authorization-required",
        "no-model-call",
        "result-discarded",
        "raw-exception-text",
        "empty",
    ],
)
def test_the_reason_is_a_registered_code_for_every_ledger_shape(recorded, expected):
    """判据①：在册的原样交回，不在册的兜到 `internal_error`，原文一律另留一格。"""
    from app.api.v1 import chat

    queue, request_id = _queue("vocab", max_attempts=1)
    queue.reserve()
    assert queue.fail_or_retry(request_id, recorded) == "dead"

    readout = chat.queue_dead_readout(queue, request_id, reliable_queue.DEAD_STATUS)
    assert readout["reason"] == expected, recorded
    assert readout["reason"] in ENUM_CODES, recorded
    #: 收窄成枚举不等于把信息丢掉：原始文本仍旧在同一扇门的 `failure` 那一格里。
    assert queue.failure(request_id)["last_error"] == recorded


def test_a_dead_row_without_a_verdict_says_the_reason_and_invents_nothing():
    """那一格没记：兜底码照交、终局判定说 None，绝不现编一枚 `queue_dead` 之类的字面量。"""
    from app.api.v1 import chat

    queue, request_id = _queue("no-verdict")
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE, retryable=False) == "dead"
    _strip_verdict(queue, request_id)
    assert queue.dead_verdict(request_id) is None

    readout = chat.queue_dead_readout(queue, request_id, reliable_queue.DEAD_STATUS)
    assert readout["reason"] == CONTEXT_LIMIT_CODE, "要说成因就从账本里读，不是从字面拼一枚"
    assert readout["retryable"] is None, "说不出那一笔就说说不出，不许拿 False 顶"


def test_the_fallback_is_the_one_registered_code_and_no_new_code_lives_in_the_readout():
    """判据④ 第二把刀的锚：R585 那一段里以字面量出现的在册码，只许有兜底那一枚。"""
    from app.api.v1 import chat

    assert chat.DEAD_REASON_FALLBACK == "internal_error"
    assert chat.DEAD_REASON_FALLBACK in ENUM_CODES
    assert chat.STABLE_ERROR_CODES == frozenset(ENUM_CODES), "投影与尺之间不许多出第二份词表"

    block = _r585_block(open(chat.__file__, encoding="utf-8").read())
    codes = set(re.findall(r'"([a-z][a-z_]+)"', block)) & set(ENUM_CODES)
    assert codes == {"internal_error"}, sorted(codes)

    queue_codes = set(re.findall(r'"([a-z][a-z_]+)"', open(
        reliable_queue.__file__, encoding="utf-8").read())) & set(ENUM_CODES)
    assert queue_codes == {"queue_unavailable"}, "持久面那一段一枚在册码都没新写：它只搬不调码"


def _r585_block(source: str) -> str:
    """把 chat.py 里 R585 那一整段现抠出来（本单节起点到 R295 那节之前），供字面量钉扫。"""
    start = source.index("# ==================== R585")
    end = source.index("# ==================== R295", start)
    return source[start:end]


# ==================== 判据②：成功终态形状一字不改 ====================


def test_the_success_terminal_payload_key_order_is_frozen():
    """判据②：`queue-terminal-v1` 现有键不许增、不许删、不许改序（多塞一键必须红）。"""
    from app.api.v1 import chat

    payload = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True
    )
    assert payload["schema"] == reliable_queue.TERMINAL_SCHEMA
    assert list(payload) == SUCCESS_TERMINAL_KEYS, list(payload)

    with_file = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        dataset_files=["q3.xlsx"],
    )
    assert list(with_file) == SUCCESS_TERMINAL_KEYS + ["data_filename"], list(with_file)
    parked = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_AWAITING_APPROVAL, answer_present=False
    )
    assert list(parked) == SUCCESS_TERMINAL_KEYS, list(parked)


def test_a_done_answer_still_answers_the_frozen_key_sequence(monkeypatch):
    """判据②：可读面在 `done` 上的键序一并冻住——本单只在 `dead` 那一支加格。"""
    from app.api.v1 import chat

    queue, request_id = _queue("done-shape")
    queue.reserve()
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True
    )
    assert queue.complete(request_id, "本月差旅费用 12,480 元。", terminal=terminal) is True

    body = _status_body(monkeypatch, queue, request_id)
    assert list(body) == DONE_RESPONSE_KEYS, list(body)
    assert body["terminal_schema"] == reliable_queue.TERMINAL_SCHEMA
    assert body["terminal_state"] == "answered"
    assert "reason" not in body, "成功那一支不许出现本单新加的那格"
    assert "retryable" not in body


def test_the_dead_readout_invents_no_source_usage_or_approval_slot():
    """判据②的对面：死终态也不许顺手把成功形状那一族空值抄过来。"""
    queue, request_id = _queue("no-slots", max_attempts=1)
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE, retryable=False) == "dead"

    readout = _readout(queue, request_id)
    assert list(readout) == DEAD_READOUT_KEYS, list(readout)
    for slot in ("sources", "sources_present", "sources_error", "usage", "approval",
                 "worker_status", "scope_reason_code", "answer_is_park_notice", "result"):
        assert slot not in readout, slot


# ==================== 判据③：不可重试与可重试两种 dead 分得开 ====================


def test_two_deads_with_identical_counters_stay_tellable_apart(monkeypatch):
    """判据③：两枚 `attempts=1 / max_attempts=1` 的 dead，只有账本分得开它们。

    这一格为什么**不能**从计数器反推：名额恰好用完、而契约又恰好判了不可重试，两种成因
    在 `attempts` 与 `max_attempts` 上逐字相等。R448 的口径是「调用方显式说
    `retryable is False`」，所以那一枚判定必须由队列替它记下来，面才说得出分家。
    """
    direct_queue, direct_id = _queue("direct", max_attempts=1)
    exhausted_queue, exhausted_id = _queue("exhausted", max_attempts=1)
    for queue, request_id, retryable in (
        (direct_queue, direct_id, False),
        (exhausted_queue, exhausted_id, True),
    ):
        queue.reserve()
        assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE, retryable=retryable) == "dead"

    first = _status_body(monkeypatch, direct_queue, direct_id)
    second = _status_body(monkeypatch, exhausted_queue, exhausted_id)
    assert first["failure"] == second["failure"], "两枚的计数器逐字相等"
    assert first["retryable"] is False and second["retryable"] is True
    assert first["terminal_note"] != second["terminal_note"]
    assert first["reason"] == second["reason"] == CONTEXT_LIMIT_CODE


def test_the_verdict_lands_on_the_durable_face_verbatim():
    """判据③（持久面）：这一笔账真落在 message 键上，不是只在返回值里活过一行。"""
    queue, request_id = _queue("durable")
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE, retryable=False) == "dead"

    ledger = _ledger(queue, request_id)
    assert ledger[reliable_queue.DEAD_VERDICT_LEDGER_KEY] == {
        "reason": CONTEXT_LIMIT_CODE,
        "retryable": False,
    }
    assert queue.dead_verdict(request_id) == ledger[reliable_queue.DEAD_VERDICT_LEDGER_KEY]
    assert ledger["last_error"] == CONTEXT_LIMIT_CODE, "旧那一格一个字都没被搬走"


def test_a_failure_that_is_still_retrying_records_no_terminal_verdict():
    """还在重投的这一轮不是终态：一个字节都不许盖成 dead 的账（与 `complete()` 同口径）。"""
    queue, request_id = _queue("still-alive")
    queue.reserve()
    assert queue.fail_or_retry(request_id, "model_unavailable") == "queued"
    assert queue.status(request_id) == "queued"

    ledger = _ledger(queue, request_id)
    assert ledger["last_error"] == "model_unavailable"
    assert reliable_queue.DEAD_VERDICT_LEDGER_KEY not in ledger
    assert queue.dead_verdict(request_id) is None


def test_a_row_recorded_before_this_change_says_the_reason_but_not_the_verdict(monkeypatch):
    """在位旧行（生产那枚 `a55ef916…` 的形状）：面上读得到码，但不许假造终局判定。"""
    queue, request_id = _queue("legacy-row", max_attempts=1)
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE) == "dead"
    _strip_verdict(queue, request_id)

    body = _status_body(monkeypatch, queue, request_id)
    assert list(body) == DEAD_RESPONSE_KEYS, list(body)
    assert body["terminal_state"] == "dead"
    assert body["reason"] == CONTEXT_LIMIT_CODE
    assert body["retryable"] is None, "读不到那一笔就说读不到，不许拿 False 冒充不可重试"
    assert "R585 之前" in body["terminal_note"]


def test_a_broken_ledger_still_names_the_terminal_without_inventing_a_cause():
    """账本坏了（半截 JSON）：`dead_verdict` 交回 None，成因兜底，本函数一枚都不许抛。"""
    queue, request_id = _queue("broken-ledger", max_attempts=1)
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE) == "dead"
    queue.redis.set(queue._message_key(request_id), '{"attempts": 1,')

    assert queue.dead_verdict(request_id) is None
    readout = _readout(queue, request_id)
    assert readout["terminal_state"] == "dead"
    assert readout["reason"] == "internal_error"
    assert readout["retryable"] is None


def test_the_dead_readout_reports_an_answer_only_when_one_is_really_there():
    """`answer_present` 是从答案键现算的读数，不是写死的一枚 False。"""
    queue, request_id = _queue("stray-answer", max_attempts=1)
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_LIMIT_CODE, retryable=False) == "dead"
    assert _readout(queue, request_id)["answer_present"] is False

    queue.redis.set(queue._result_key(request_id), " leftover body ")
    assert _readout(queue, request_id)["answer_present"] is True


# ==================== 判据④：三把刀的锚点必须在位 ====================

#: 三把刀各自下刀的那一行。锚点一漂刀就砍空，所以先把锚钉住；摘除后的红逐把记在交工纸。
COUNTER_EVIDENCE_ANCHORS = {
    "K1-reason-assembly": '"reason": raw if raw in STABLE_ERROR_CODES else DEAD_REASON_FALLBACK,',
    "K2-registered-fallback": 'DEAD_REASON_FALLBACK = "internal_error"',
    "K3-success-payload": '        "approval": approval,\n    }\n    return attach_terminal_data_filename(payload, dataset_files)',
}


def test_the_three_counter_evidence_anchors_are_still_in_place():
    """判据④：每一把刀的锚点逐字现读一次，出现次数恰为一。"""
    from app.api.v1 import chat

    source = open(chat.__file__, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    for label, anchor in COUNTER_EVIDENCE_ANCHORS.items():
        assert source.count(anchor) == 1, "%s 的锚点漂了：这把刀会砍空" % label


def test_this_file_adds_no_skip_and_no_xfail():
    """本单不许拿跳过代替判据：AST 现读全文，一枚 skip / xfail / skipif 都没有。"""
    import ast

    tree = ast.parse(open(__file__, encoding="utf-8").read())
    banned = {"skip", "xfail", "skipif"}
    hits = [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in banned]
    assert not hits, hits