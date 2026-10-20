# -*- coding: utf-8 -*-
"""R545 —— 队列道「失败有终态与原因码」的离线牙（真 ReliableQueue + 假 Redis + 假时钟，零 socket）。

这单只交离线半张：量具 `scripts/r545_queue_failure_probe.py` + 本件这两枚牙 + 取证纸
`docs/testing/r545-queue-failure-probe-2026-10-04.md`。真容器那一遍归总控开窗跑。

咬住的东西（判据逐枚对点名）：
  判据① 失败必带原因码，且原因码在**终态载荷**里读得出
        -> test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload
        -> test_the_route_readback_of_a_dead_row_feeds_the_probe_evidence（走真路由那一扇门）
  判据② 缺证词记 None，不许折算成 0 或空表
        -> test_the_expired_row_speaks_nothing_and_the_probe_records_none
        -> test_a_key_that_is_absent_resolves_to_nothing_not_zero
  判据③ 重试计数不越界 / 不可重试不占名额 / 死信深度数得对
        -> test_the_retry_counter_never_exceeds_the_budget_and_dead_lands_at_the_ceiling
        -> test_a_non_retryable_verdict_does_not_burn_a_retry_slot
        -> test_the_dead_letter_depth_counts_dead_rows_not_attempts
  判据④ 幂等键生效
        -> test_the_idempotency_key_maps_to_exactly_one_request_id
  判据⑤ 终态词表由代码派生，第六枚 awaiting_approval 认得出来；少认一枚必须红
        -> test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word
        -> test_the_stop_words_come_from_the_derived_vocabulary
  判据⑥ 量具自己的三条纪律：产物落仓外、退出码 2 不是通过、注入姿势不 armed 就不问出去
        -> test_the_probe_refuses_an_artifact_directory_inside_the_repo
        -> test_zero_never_comes_from_an_empty_window / test_the_exit_code_is_two_when_a_cell_cannot_be_measured
        -> test_the_budget_and_endpoint_postures_only_arm_on_a_live_knob
        -> test_the_probe_help_text_renders_and_still_declares_the_exit_codes
        -> test_the_derivation_does_not_depend_on_the_checkout_line_endings

全程离线：不打模型、不开端口、不起容器、不动生产 Redis、不连 PG。假 Redis 沿用在册那枚
`tests/test_reliable_queue.py::FakeRedis`，只补 `llen`（数深度）与 `expire`（续租）两枚补角。

跑法：
    python -m pytest tests/test_r545_queue_failure_teeth.py -o addopts= -p no:cacheprovider -q
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api.v1 import chat
from app.common import reliable_queue
from app.common.reliable_queue import ReliableQueue
from tests.test_reliable_queue import FakeRedis

REPO = Path(__file__).resolve().parents[1]
PROBE_PATH = REPO / "scripts" / "r545_queue_failure_probe.py"
SUBJECT = "r545-owner"

_spec = importlib.util.spec_from_file_location("r545_probe", str(PROBE_PATH))
assert _spec is not None and _spec.loader is not None
PROBE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PROBE)

#: 在册那枚确定性拒绝码（R30），本件只消费、不新造。
CONTEXT_CODE = "context_limit_exceeded"
UNKNOWN_MESSAGE = "worker crashed with an unrecognised stack trace"


class QueueRedis(FakeRedis):
    """在册假 Redis 的两枚补角：LLEN（数深度）与 EXPIRE（租约还在不在），其余一律继承。"""

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def expire(self, key: str, seconds) -> int:
        return int(key in self.values)


def _queue(name: str, *, max_attempts: int = 3, message: dict | None = None):
    """真队列 + 假 Redis + 一个入队好的 request_id：与 R81/R448/R585 同一套夹具。"""
    queue = ReliableQueue(QueueRedis(), name="r545-" + name, lease_seconds=30,
                          max_attempts=max_attempts)
    payload = message or {"message": "生成本月差旅费用分析周报", "session_id": "session-r545",
                          "username": SUBJECT,
                          "principal": {"user_id": SUBJECT, "username": SUBJECT, "roles": ["admin"]}}
    made = queue.enqueue(payload, "idem-" + name)
    return queue, made.request_id


def _strip_verdict(queue, request_id) -> None:
    """复现「R585 之前」那一形：账本还在位，只是当年没记终局判定。"""
    raw = queue.redis.get(queue._message_key(request_id))
    ledger = json.loads(raw)
    ledger.pop(reliable_queue.DEAD_VERDICT_LEDGER_KEY, None)
    queue.redis.set(queue._message_key(request_id), json.dumps(ledger, ensure_ascii=False))


def _dead_row(queue, request_id) -> dict:
    """把队列在 dead 状态下**本该交出的那一格**拼成量具读回来的形状（门外的等价物）。"""
    body = {"status": queue.status(request_id), "request_id": request_id,
            "failure": queue.failure(request_id)}
    body.update(chat.queue_dead_readout(queue, request_id, reliable_queue.DEAD_STATUS))
    return body


def _row(posture="budget", *, armed=True, body=None, request_id="req-1", idem=None, **extra):
    row = {"posture": posture, "armed": armed, "gate_reason": "测试夹具", "recipe": "",
           "witness": {}, "note": "", "side_effects": "测试", "idempotency_key": "idem-x",
           "request_id": request_id, "http_status": 200 if body is not None else 0,
           "row": body, "raw_sha256": "", "polls": 3, "blips": 0, "stop_kind": "stopped"}
    row["idempotency"] = idem if idem is not None else {"state": "read", "key": "k",
                                                        "maps_to": request_id,
                                                        "matches_request_id": True, "note": ""}
    row.update(extra)
    return row


def _head(rows, *, before=0, after=0) -> dict:
    return {"rows": rows, "depth_before": before, "depth_after": after,
            "handle_note": "", "terminal_words": list(_vocab()["terminal"]),
            "polls": sum(int(row.get("polls") or 0) for row in rows), "blips": 0}


def _args(**kw) -> SimpleNamespace:
    base = {"expect_rev": "", "build_info_text": "", "build_info_path": "/app/BUILD_INFO"}
    base.update(kw)
    return SimpleNamespace(**base)


def _vocab() -> dict:
    return PROBE.derive_vocabulary()


def _judge(rows, vocab=None, *, before=0, after=0, args=None) -> dict:
    return PROBE.judge(_head(rows, before=before, after=after), vocab or _vocab(), args or _args())


# ==================== 判据① 失败必带原因码，且原因码在终态载荷里读得出 ====================


def test_a_dead_turn_carries_a_registered_reason_readable_on_the_terminal_payload():
    vocab = _vocab()
    queue, request_id = _queue("reason")
    queue.reserve()
    outcome = queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    assert outcome == "dead"

    row = _dead_row(queue, request_id)
    evidence = PROBE.evidence_from_row(vocab["dead_status"], row, vocab,
                                       depth=queue.dead_letter_depth(),
                                       idempotency=PROBE.read_idempotency(queue, "idem-reason", request_id))

    assert evidence["reason_code_field"] == "reason"
    assert evidence["reason_code"] == CONTEXT_CODE
    assert evidence["terminal_schema"] == vocab["dead_schema"]
    assert evidence["retryable"] is False
    assert evidence["last_error"] == CONTEXT_CODE
    assert evidence["last_error_is_stable_code"] is True
    assert evidence["attempts"] == 1 and evidence["max_attempts"] == 3
    assert evidence["dead_letter_depth"] == 1
    assert evidence["idempotency"]["matches_request_id"] is True

    cells = _judge([_row(body=row, request_id=request_id)], vocab, before=0, after=1)
    assert cells["cells"]["failure_reason"]["verdict"] == PROBE.PASS
    assert cells["cells"]["dead_keys"]["verdict"] == PROBE.PASS
    assert cells["cells"]["dead_keys"]["value"]["per_row"][0]["reason"] == CONTEXT_CODE


def test_the_reason_code_is_a_registered_stable_code_and_no_new_code_lives_in_the_readout():
    """可定位证据里的原因码只许是 `ErrorEnvelope.code` 的成员；认不出来就兜到在册那一枚。"""
    vocab = _vocab()
    queue, request_id = _queue("codes")
    queue.reserve()
    queue.fail_or_retry(request_id, UNKNOWN_MESSAGE, retryable=False)

    row = _dead_row(queue, request_id)
    assert row["reason"] in set(vocab["stable_codes"])
    assert row[PROBE.REASON_KEY] == "internal_error"
    assert row["failure"][PROBE.LAST_ERROR_KEY] == UNKNOWN_MESSAGE
    assert vocab["dead_schema"] not in set(vocab["stable_codes"])


def test_an_unregistered_reason_code_on_the_readout_reddens_the_dead_cell():
    """可读面只许消费 ErrorEnvelope.code 那枚枚举：发明一枚新码，dead_keys 那一格当场红。"""
    vocab = _vocab()
    queue, request_id = _queue("invented")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    row = _dead_row(queue, request_id)
    row["reason"] = "clearly_invented_code"
    verdict = _judge([_row(body=row, request_id=request_id)], vocab, after=1)
    assert verdict["cells"]["dead_keys"]["verdict"] == PROBE.FAIL
    assert "不在 ErrorEnvelope.code" in verdict["cells"]["dead_keys"]["note"]


def test_the_verdict_lands_on_the_durable_ledger_verbatim():
    """持久面那笔账的形状就是判据③ 分家的那枚凭据：摘掉它，两枚 dead 就重新洗成一枚。"""
    queue, request_id = _queue("durable")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    ledger = json.loads(queue.redis.get(queue._message_key(request_id)))
    assert ledger[reliable_queue.DEAD_VERDICT_LEDGER_KEY] == {"reason": CONTEXT_CODE,
                                                              "retryable": False}
    assert ledger[PROBE.LAST_ERROR_KEY] == CONTEXT_CODE
    assert queue.dead_verdict(request_id)["retryable"] is False


def test_a_row_recorded_before_the_verdict_says_the_reason_but_not_the_verdict():
    """摘掉 dead_verdict 那一笔 = 复现旧行：`retryable` 说「读不出」，绝不拿 False 冒充「不可重试」。"""
    vocab = _vocab()
    queue, request_id = _queue("legacy-verdict")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    _strip_verdict(queue, request_id)

    row = _dead_row(queue, request_id)
    assert row[PROBE.RETRYABLE_KEY] is None
    evidence = PROBE.evidence_from_row(vocab["dead_status"], row, vocab, depth=1)
    assert evidence["reason_code"] == CONTEXT_CODE
    verdict = _judge([_row(body=row, request_id=request_id)], vocab, after=1)["cells"]["dead_keys"]
    assert verdict["verdict"] == PROBE.PASS
    assert verdict["value"]["per_row"][0]["retryable_note"]


# ==================== 判据② 缺证记 None：不折 0、不折空表 ====================


def test_the_expired_row_speaks_nothing_and_the_probe_records_none():
    """路由在 expired 那一格只交 status + message（AST 现取的早退形状），证据格一律 None。"""
    vocab = _vocab()
    early = [item for item in vocab["faces"]["early_returns"] if item["status"] == "expired"]
    assert early and PROBE.FAILURE_FIELD not in early[0]["keys"]

    row = {"status": "expired", "message": "请求已过期，请重新提交"}
    evidence = PROBE.evidence_from_row("expired", row, vocab, depth=None, idempotency=None)
    assert evidence["reason_code_field"] is None
    assert evidence["last_error"] is None
    assert evidence["attempts"] is None and evidence["max_attempts"] is None
    assert evidence["dead_letter_depth"] is None
    assert evidence["idempotency"] is None
    assert evidence["absent_evidence"]
    assert all(cell["value"] is None for cell in evidence["terminal_keys"]["cells"].values())
    # expired 不算「一次失败读数」：它压根没进过队列账本，那一格只能量不到
    assert _judge([_row(posture="expired", body=row, request_id="never")],
                  vocab)["cells"]["failure_reason"]["verdict"] == PROBE.UNMEASURED


def test_the_dead_row_answers_all_four_readout_keys_with_an_explicit_verdict():
    """判据② 的字面要求：四枚键每一枚都得有一句证词，这一形说不出也要登记 None，不许沉默。"""
    vocab = _vocab()
    queue, request_id = _queue("four-keys")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    cells = PROBE.terminal_key_cells(_dead_row(queue, request_id), vocab, vocab["dead_status"])
    assert sorted(cells["asked"]) == sorted(PROBE.REQUIRED_TERMINAL_KEYS)
    assert cells["cells"]["terminal_state"]["speaks"] == PROBE.SPEAKS_READ
    assert cells["cells"]["sources_present"]["speaks"] == PROBE.SPEAKS_CANNOT
    assert cells["cells"]["usage"]["value"] is None
    assert cells["cells"]["usage"]["note"]
    assert cells["unreadable_from_code"] == ["sources_present", "usage"]


def test_a_key_that_is_absent_resolves_to_nothing_not_zero():
    """`resolve_in_row` 走不通的格子交 KeyError（缺格），而不是 0／空表——折算就是假绿。"""
    row = {"status": "dead", "failure": {"attempts": 1, "last_error": None, "max_attempts": 3}}
    with pytest.raises(KeyError):
        PROBE.resolve_in_row(row, "usage")
    with pytest.raises(KeyError):
        PROBE.resolve_in_row(row, "failure.last_error.absent")
    assert PROBE._absent("usage", "这一行不交")["value"] is None
    assert PROBE._present("usage", {"total_tokens": 0})["value"] == {"total_tokens": 0}


def test_a_null_key_in_place_is_reported_as_read_not_as_missing():
    """legacy 行交回 usage=null 是「读到一枚 null」，与「这一格不交」是两句话。"""
    vocab = _vocab()
    queue, request_id = _queue("legacy-null")
    queue.reserve()
    queue.complete(request_id, "上一季度毛利率 38.2%。", terminal=None)  # 旧行：没有终态载荷
    row = chat.queue_terminal_readout(queue, request_id, {}, queue.status(request_id))
    assert row["usage"] is None and "usage" in row
    cells = PROBE.terminal_key_cells(row, vocab, "done")
    assert cells["cells"]["usage"]["speaks"] == PROBE.SPEAKS_READ
    assert "值为 null" in cells["cells"]["usage"]["note"]


# ==================== 判据③ 重试计数 / 名额 / 死信深度 ====================


def test_the_retry_counter_never_exceeds_the_budget_and_dead_lands_at_the_ceiling():
    vocab = _vocab()
    queue, request_id = _queue("budget", max_attempts=3)
    seen = []
    for _ in range(6):
        queue.reserve()
        outcome = queue.fail_or_retry(request_id, "model_unavailable")
        seen.append((queue.status(request_id), queue.failure(request_id)["attempts"]))
        if outcome == "dead":
            break
    assert [word for word, _ in seen][-1] == "dead"
    assert max(attempts for _, attempts in seen) <= 3
    assert queue.failure(request_id)["attempts"] == 3
    cells = _judge([_row(body=_dead_row(queue, request_id))], vocab, after=queue.dead_letter_depth())
    assert cells["cells"]["retry_budget"]["verdict"] == PROBE.PASS


def test_a_non_retryable_verdict_does_not_burn_a_retry_slot():
    """契约那句「首发即落 dead，没有占用重试名额」：attempts 停在 1，深度加一。"""
    queue, request_id = _queue("slot", max_attempts=3)
    queue.reserve()
    assert queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False) == "dead"
    ledger = queue.failure(request_id)
    assert ledger["attempts"] < ledger["max_attempts"]
    assert queue.dead_letter_depth() == 1
    assert queue.pending_depth() == 0


def test_the_dead_letter_depth_counts_dead_rows_not_attempts():
    """深度数的是停在死信表上的**请求**，一枚请求打三回也只占一格。"""
    queue, first = _queue("depth-a")
    queue.reserve()
    queue.fail_or_retry(first, "model_unavailable")   # 回队列，不进死信
    assert queue.dead_letter_depth() == 0
    for _ in range(3):
        queue.reserve()
        if queue.fail_or_retry(first, "model_unavailable") == "dead":
            break
    assert queue.dead_letter_depth() == 1
    other = queue.enqueue({"message": "第二问", "username": SUBJECT,
                           "principal": {"user_id": SUBJECT, "username": SUBJECT}},
                          "idem-depth-b").request_id
    queue.reserve()
    queue.fail_or_retry(other, CONTEXT_CODE, retryable=False)
    assert queue.dead_letter_depth() == 2
    verdict = _judge([_row(body=_dead_row(queue, other))], _vocab(), before=1, after=2)
    assert verdict["cells"]["dead_letter_depth"]["verdict"] == PROBE.PASS


def test_the_depth_cell_refuses_to_call_a_still_list_unmeasured():
    """没有 dead 行的那一遍不许把盘面深度当「已验」：那一格只能量不到。"""
    verdict = _judge([_row(posture="expired", body={"status": "expired", "message": "x"},
                            request_id="never")], _vocab(), before=7, after=7)
    assert verdict["cells"]["dead_letter_depth"]["verdict"] == PROBE.UNMEASURED
    assert verdict["cells"]["dead_letter_depth"]["value"]["before"] == 7


def test_a_dead_row_that_got_no_further_entry_reddens_the_depth_cell():
    queue, request_id = _queue("depth-lie")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    row = _dead_row(queue, request_id)
    verdict = _judge([_row(body=row, request_id=request_id)], _vocab(), before=5, after=5)
    assert verdict["cells"]["dead_letter_depth"]["verdict"] == PROBE.FAIL


# ==================== 判据④ 幂等键生效 ====================


def test_the_idempotency_key_maps_to_exactly_one_request_id():
    vocab = _vocab()
    queue, request_id = _queue("idem")
    again = queue.enqueue({"message": "换个字也不许开第二笔", "username": SUBJECT}, "idem-idem")
    assert again.request_id == request_id

    block = PROBE.read_idempotency(queue, "idem-idem", request_id)
    assert block["state"] == "read" and block["maps_to"] == request_id
    assert block["matches_request_id"] is True
    assert block["key"] == "r545-idem:idempotency:idem-idem"

    wrong = PROBE.read_idempotency(queue, "idem-idem", "somebody-elses-turn")
    assert wrong["matches_request_id"] is False
    verdict = _judge([_row(body=_dead_row(queue, request_id), request_id=request_id,
                           idem=wrong)], vocab, after=queue.dead_letter_depth())
    assert verdict["cells"]["idempotency"]["verdict"] == PROBE.FAIL


def test_the_idempotency_cell_says_unavailable_instead_of_inventing_a_key():
    verdict = _judge([_row(body={"status": "dead", "failure": {}},
                           idem=PROBE.read_idempotency(None, "k", "req-1"))], _vocab())
    assert verdict["cells"]["idempotency"]["verdict"] == PROBE.FAIL
    assert "没有队列连接" in json.dumps(verdict["cells"]["idempotency"]["value"], ensure_ascii=False)


# ==================== 取消那一族：原因码前缀读得出 ====================


def test_the_cancel_discard_records_the_stable_discard_prefix():
    """跑途中被取消：结果丢弃那一支把 `result_discarded:cancelled` 写进账，量具要读得出前缀。"""
    vocab = _vocab()
    queue, request_id = _queue("cancel-discard")
    queue.reserve()
    queue.cancel(request_id)
    assert queue.complete(request_id, "半截正文", terminal=None) is False
    assert queue.status(request_id) == "cancelled"
    assert queue.result(request_id) is None

    row = {"status": "cancelled", "request_id": request_id, "failure": queue.failure(request_id)}
    evidence = PROBE.evidence_from_row("cancelled", row, vocab, depth=queue.dead_letter_depth())
    assert evidence["reason_code_field"] == "failure.last_error"
    assert evidence["last_error"] == "result_discarded:cancelled"
    assert evidence["last_error_prefix"] == vocab["discard_prefix"]
    assert evidence["attempts"] == 1
    verdict = _judge([_row(posture="cancel", body=row, request_id=request_id)], vocab)
    assert verdict["cells"]["failure_reason"]["verdict"] == PROBE.PASS


def test_a_pending_cancel_speaks_no_reason_and_the_probe_still_says_none():
    """还没开跑就被按住的取消：契约把成因记在状态词上，那一格没有 last_error，也不许判失败。"""
    queue, request_id = _queue("cancel-pending")
    assert queue.cancel(request_id) is True
    assert queue.status(request_id) == "cancelled"
    row = {"status": "cancelled", "request_id": request_id, "failure": queue.failure(request_id)}
    evidence = PROBE.evidence_from_row("cancelled", row, _vocab(), depth=0)
    assert evidence["last_error"] is None and evidence["absent_evidence"]
    verdict = _judge([_row(posture="cancel", body=row, request_id=request_id)], _vocab())
    assert verdict["cells"]["failure_reason"]["verdict"] == PROBE.PASS
    assert "cancel_without_reason" in json.dumps(verdict["cells"]["failure_reason"]["value"],
                                                 ensure_ascii=False)


# ==================== 判据⑤ 词表派生 + 停表词表同源 ====================


def test_the_terminal_vocabulary_is_derived_and_names_the_sixth_word():
    vocab = _vocab()
    assert sorted(vocab["terminal"]) == ["awaiting_approval", "cancelled", "dead",
                                         "done", "expired", "failed"]
    assert vocab["sixth_terminal_named"] is True
    assert vocab["awaiting_word"] == "awaiting_approval"
    assert vocab["route_only"] == ["expired"]
    assert len(vocab["queue_written"]) == 8
    assert sorted(vocab["non_terminal"]) == ["cancel_requested", "processing", "queued"]
    assert vocab["blind_spots"] == [] and vocab["drift"] == []
    assert vocab["sites"]["awaiting_approval"] and vocab["sites"]["dead"]


def test_the_derivation_says_the_gauge_paper_still_claims_five_terminals():
    """散文不是契约：纸面那句「五枚终态」记成转出项，不许把它洗成口径一致，也不许算成 FAIL。"""
    vocab = _vocab()
    assert vocab["stale_prose"] == [5]
    cell = PROBE.judge_vocabulary({}, vocab)
    assert cell["verdict"] == PROBE.PASS
    assert "转出项" in cell["note"] and len(vocab["terminal"]) == 6


def test_the_stop_words_come_from_the_derived_vocabulary():
    """停表只认派生名单：读到 dead 就停，读到 cancel_requested 接着轮（非终态不是停表理由）。"""
    vocab = _vocab()
    scripted = [("processing", None), ("cancel_requested", None), ("queued", None), ("dead", None)]

    class FakeSession:
        base = "http://test"
        blips = 0
        polls = 0

        def __init__(self):
            self.reads = 0

        def poll_status(self, request_id, since=0):
            self.reads += 1
            status = scripted[self.reads - 1][0] if self.reads <= len(scripted) else "processing"
            return 200, b"{}", {"status": status, "failure": {"attempts": 1, "max_attempts": 3}}

    session = FakeSession()
    now = [1000.0]
    read = PROBE.poll_until_stop(session, "req-1", vocab["terminal"], interval=0.0,
                                 deadline=900.0, stall=300.0,
                                 clock=lambda: now[0], sleeper=lambda _s: now.__setitem__(0, now[0] + 1))
    assert read["kind"] == "stopped" and read["final"] == "dead"
    assert read["polls"] == 4


def test_the_polling_exit_path_is_derived_not_copied():
    """量具走的那扇门与 cancel 门都由 AST 现取；抄来的路径会为别人的一次编辑而哑。"""
    vocab = _vocab()
    assert PROBE.POLL_PATH_FRAGMENT in vocab["poll_path"]
    assert PROBE.derived_cancel_path(PROBE.read_source(PROBE.CHAT_REL)) == \
        "/api/v1/queue/{request_id}/cancel"


# ==================== 判据⑥ 量具自己的纪律：仓外产物 / 退出码 / 姿势闸 ====================


def test_the_probe_refuses_an_artifact_directory_inside_the_repo(tmp_path):
    """判据③：证据件落仓外是硬闸——指到 scripts/ 或 docs/ 就 rc=2 拒绝，缺省落 %TEMP%。"""
    for target in ("scripts", "docs/testing/r545-evidence", str(REPO / "tests"), "app", "."):
        with pytest.raises(PROBE.GaugeFailure):
            PROBE.resolve_out_dir(target, REPO)
    assert PROBE.is_inside_repo(PROBE.default_out_dir(), REPO) is False
    assert PROBE.resolve_out_dir("", REPO) == PROBE.default_out_dir()
    assert PROBE.resolve_out_dir(str(tmp_path), REPO) == tmp_path
    assert PROBE.resolve_out_dir(str(REPO.parent / "r545-evidence"), REPO)


def test_zero_never_comes_from_an_empty_window():
    """一字节都没读回来的那一遍：rc=2。把「没跑」读成「通过」正是本件要消灭的那枚假绿。"""
    report = _judge([_row(armed=False, body=None, request_id="")], _vocab())
    assert report["rc"] == 2
    assert report["cells"]["failure_reason"]["verdict"] == PROBE.UNMEASURED
    assert report["cells"]["terminal_keys"]["verdict"] == PROBE.UNMEASURED
    assert PROBE.overall([{"verdict": PROBE.PASS}] * 9 + [{"verdict": PROBE.UNMEASURED}]) == 2
    assert PROBE.overall([{"verdict": PROBE.PASS}] * 9 + [{"verdict": PROBE.FAIL}]) == 1
    assert PROBE.overall([{"verdict": PROBE.PASS}] * 9) == 0


def test_the_exit_code_is_two_when_a_cell_cannot_be_measured():
    """真失败在位：九格才有脸报 0；provenance 没给 expect-rev 时仍旧是 2。"""
    queue, request_id = _queue("rc0")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)
    row = _dead_row(queue, request_id)
    vocab = _vocab()
    report = _judge([_row(body=row, request_id=request_id)], vocab, after=1, args=_args())
    assert report["cells"]["provenance"]["verdict"] == PROBE.UNMEASURED
    assert report["rc"] == 2
    armed = _args(expect_rev="a" * 40, build_info_text="revision=" + "a" * 40 + "\n",
                  build_info_path="/app/BUILD_INFO")
    report = _judge([_row(body=row, request_id=request_id)], vocab, after=1, args=armed)
    assert report["cells"]["provenance"]["verdict"] == PROBE.PASS
    assert report["rc"] == 0, json.dumps(report["cells"], ensure_ascii=False)[:900]


def test_the_budget_and_endpoint_postures_only_arm_on_a_live_knob():
    """注入姿势靠旋钮说话：旋钮不在位就交回命令原文，绝不在没 armed 的时候问出去。"""
    names = ["MODEL_CONTEXT_TOKENS", "LOCAL_MODEL_BASE_URL", "OLLAMA_BASE_URL"]
    bare = PROBE.env_witness(names, environ={})
    budget = PROBE.posture_gate("budget", bare, environ={})
    assert budget["armed"] is False and "MODEL_CONTEXT_TOKENS" in budget["recipe"]
    small = PROBE.env_witness(names, environ={"MODEL_CONTEXT_TOKENS": "2048"})
    assert PROBE.posture_gate("budget", small, environ={"MODEL_CONTEXT_TOKENS": "2048"})["armed"] is True
    wide = PROBE.env_witness(names, environ={"MODEL_CONTEXT_TOKENS": "32768"})
    assert PROBE.posture_gate("budget", wide, environ={"MODEL_CONTEXT_TOKENS": "32768"})["armed"] is False

    pointed = PROBE.env_witness(names, environ={"LOCAL_MODEL_BASE_URL": "http://127.0.0.1:1"})
    armed = PROBE.posture_gate("endpoint", pointed,
                               environ={"LOCAL_MODEL_BASE_URL": "http://127.0.0.1:1"},
                               connector=lambda host, port, timeout: False)
    assert armed["armed"] is True
    listening = PROBE.posture_gate("endpoint", pointed,
                                   environ={"LOCAL_MODEL_BASE_URL": "http://127.0.0.1:1"},
                                   connector=lambda host, port, timeout: True)
    assert listening["armed"] is False and "仍可达" in listening["reason"]
    unprobed = PROBE.posture_gate("endpoint", pointed,
                                  environ={"LOCAL_MODEL_BASE_URL": "http://127.0.0.1:1"},
                                  connector=None)
    assert unprobed["armed"] is True and "未验" in unprobed["reason"]
    assert PROBE.posture_gate("cancel", bare, environ={})["armed"] is True


def test_the_probe_only_asks_the_queue_for_readings_never_mutates_it():
    """量具对队列那一腿只许读：AST 扫一遍，`handle.`／`queue.` 上不许出现任何一枚写动作。

    写在纪律纸上不算数——判据要能在别人改出一枚写点的那天当场红。
    """
    mutating = {"enqueue", "reserve", "ack", "complete", "fail_or_retry", "renew_lease",
                "append_piece_batch", "set", "delete", "rpush", "lrem", "expire", "lpop",
                "rpoplpush", "brpoplpush", "requeue_expired"}
    offenders = []
    for node in ast.walk(ast.parse(PROBE_PATH.read_bytes().decode("utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        base = node.func
        while isinstance(base.value, ast.Attribute):
            base = base.value
        if isinstance(base.value, ast.Name) and base.value.id in {"handle", "queue"} \
                and node.func.attr in mutating:
            offenders.append("%d: %s" % (node.lineno, node.func.attr))
    assert offenders == []
    assert "--force-recreate" in PROBE.RECIPE_BUDGET and "不是镜像重建" in PROBE.RECIPE_BUDGET


# ==================== 走真路由那一扇门读回（同进程、零 socket） ====================


def _route_body(monkeypatch, queue, request_id) -> dict:
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(auth, "get_user", lambda username: {
        "id": username, "username": username, "role": "admin", "status": "active"})
    monkeypatch.setattr(auth, "user_storage_state", lambda: {"storage_mode": "postgres"})
    client = TestClient(app)
    response = client.get("/api/v1" + PROBE.POLL_PATH_FRAGMENT + request_id,
                          headers={"Authorization": "Bearer " + create_token(SUBJECT)})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_route_readback_of_a_dead_row_feeds_the_probe_evidence(monkeypatch):
    """判据① 的那句「在终态载荷里读得出」只认真门：同进程真路由 + 真载荷喂给量具。"""
    vocab = _vocab()
    queue, request_id = _queue("route")
    queue.reserve()
    queue.fail_or_retry(request_id, CONTEXT_CODE, retryable=False)

    body = _route_body(monkeypatch, queue, request_id)
    assert body["status"] == "dead"
    evidence = PROBE.evidence_from_row("dead", body, vocab, depth=queue.dead_letter_depth(),
                                      idempotency=PROBE.read_idempotency(queue, "idem-route", request_id))
    assert evidence["reason_code"] == CONTEXT_CODE
    assert evidence["terminal_schema"] == vocab["dead_schema"]
    assert evidence["terminal_keys"]["cells"]["terminal_state"]["value"] == "dead"
    report = _judge([_row(body=body, request_id=request_id)], vocab, after=1,
                    args=_args(expect_rev="b" * 40, build_info_text="revision=" + "b" * 40))
    assert report["cells"]["dead_keys"]["verdict"] == PROBE.PASS
    assert report["cells"]["terminal_keys"]["verdict"] == PROBE.PASS


def test_the_probe_help_text_renders_and_still_declares_the_exit_codes(capsys):
    """说明书本身也要交得出去：argparse 对每枚 help= 跑 %-插值，字面 % 没写成 %% 时
    `--help` 当场 ValueError（本单一手踩过）；渲染出来的退出码语义必须逐档都在。"""
    with pytest.raises(SystemExit) as exit_info:
        PROBE.main(["--help"])
    assert exit_info.value.code == 0
    text = capsys.readouterr().out
    assert "--out" in text and "--print-recipe" in text
    # 渲染后必须是单枚 %：留双份说明 help= 里那枚 %% 没被插值吃掉
    assert "%%" not in text
    assert "%TEMP%" in text
    for phrase in ("0 = ", "1 = ", "2 = ", "2 永远不是通过"):
        assert phrase in text, phrase


def test_the_derivation_does_not_depend_on_the_checkout_line_endings():
    """本仓 autocrlf=true，检出来是 CRLF：一枚字面 `\r` 躲在 `$` 前面会把契约那枚
    ``status` is one of ...`` 枚举行静默读成「纸面没有」（本单一手踩进量具里，本牙是赎罪券）。
    判据：同一份契约喂 CRLF 与喂 LF，派生读数逐枚相等——量具不许看检出口径的脸色。"""
    direct = PROBE.read_source(PROBE.CONTRACT_REL)
    assert chr(13) not in direct                       # read_source 自己先把行尾归一
    table = PROBE.contract_status_table(direct)
    assert table["enum_line_present"] is True          # 纸面那枚枚举行其实一直在
    crlf = direct.replace("\n", "\r\n")
    assert chr(13) in crlf
    assert PROBE.contract_status_table(crlf) == table
    vocab_crlf = PROBE.derive_vocabulary(contract_text=crlf)
    vocab = _vocab()
    for key in ("terminal", "non_terminal", "route_only", "blind_spots", "drift", "unreadable"):
        assert vocab_crlf[key] == vocab[key], key
    assert vocab_crlf["faces"]["contract"]["enum_line_present"] is True
