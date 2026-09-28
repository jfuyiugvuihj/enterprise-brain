"""R448 —— 确定性拒绝不该重试三发：队列 worker 白烧 373 秒。

真机实测（run9c，总控 09-28 14:19 现读）：报告档 report-04 走队列道，同一枚
request_id=9bf335ef3b954f3681ab2d9bc159c929 连吃**三发完全同因**的拒绝才判 dead
（14:06:33 / 14:08:37 / 14:10:46 三行 [ModelBudget] ... error_code=context_limit_exceeded，
prompt_tokens=2691/2693/2695、required_n_ctx=4227~4231、MODEL_CONTEXT_TOKENS=4096），
wait_ms=373712 里约 248 s 是纯白烧。缺陷不在队列层（app/common/reliable_queue.py 的
fail_or_retry 一直尊重 caller 的终局判定），在报告档交给它的那枚记录本身：

  ① 码无条件写成兜底值 internal_error —— 台账因此读成「未产生业务结论: internal_error」；
  ② 记录不带 error["retryable"] —— deploy/queue_worker.py:is_non_retryable_error 只认显式
     False，缺这一键就是"还能救"。

跑法（离线：FakeRedis + 直接 import deploy.queue_worker，零容器 / 零模型 / 零 app.api.v1.chat
那条 17 s 起子链，也就绕开本机 torch 双导入那一族跑法假红）：
    python -m pytest tests/test_r448_deterministic_refusal_no_retry.py -q

判据 -> 用例
① 认码只许用在册那把尺      test_the_worker_holds_the_registered_meter_and_no_second_one
② 白名单派生不许手抄        test_the_whitelist_is_derived_from_the_registered_anchor
                            test_a_drifted_anchor_raises_instead_of_defaulting
③ 保留原码 + 显式终局判定    test_the_recogniser_keeps_the_original_code_and_states_finality
④ 兄弟形状同族已一并改      test_both_report_lane_failure_sites_hand_the_recogniser
⑤ 其余码逐字节不变          test_the_record_for_an_unrecognised_failure_is_byte_identical_to_before
                            test_a_non_whitelist_failure_still_burns_the_same_three_attempts
⑥ 台账那一行的口径不洗      test_the_non_whitelist_ledger_line_keeps_its_own_code
牙 a 首发即终态              test_a_context_limit_refusal_dies_on_the_first_attempt
牙 b 名额没被动              test_a_non_whitelist_failure_still_burns_the_same_three_attempts
牙 c 原码留在台账与日志      test_the_ledger_and_the_log_both_keep_the_original_code
牙 d 那一笔字段是唯一决定者  test_the_retryable_field_alone_decides_one_shot_versus_three
"""

import inspect
import json
import logging
from pathlib import Path
from typing import get_args

import pytest

from app.agents.contracts import CONTEXT_LIMIT_CODE, ErrorEnvelope
from app.agents.evidence import _RETRIABLE_CODES
from app.common.model_budget import CONTEXT_ERROR_FRAGMENTS, context_error_code
from tests.test_reliable_queue import FakeRedis
from deploy import queue_worker

WORKER_SOURCE = Path(queue_worker.__file__).read_text(encoding="utf-8")

#: run9c 那一发的原句，逐字取自 app/common/model_budget.py:120-128 的拼装式，
#: 数字用总控现读的 prompt_tokens=2695 / required_n_ctx=4231 / over_by=135 / 4096。
RUN9C_WINDOW_ERROR = (
    "Local model context window cannot hold this request "
    f"(error_code={CONTEXT_LIMIT_CODE}): prompt_tokens=2695 plus this tier's "
    "declared max_tokens=1536 needs n_ctx=4231, which is 135 tokens more than "
    "the configured MODEL_CONTEXT_TOKENS=4096 -- that window leaves 2560 tokens "
    "for the prompt. No request was sent and no business conclusion was generated."
)
#: ModelClockUnaffordable（app/common/model_budget.py:379-408）那一族：它是窗口拒绝的
#: 子类，但说的是钟不是窗口，码是在册可重试的 task_timeout —— 它绝不该被本单的白名单吃进去。
CLOCK_ERROR = (
    "Local model clock cannot write this tier's answer inside its own ceiling "
    "(error_code=task_timeout): prompt_tokens=3897 and max_tokens=1536 need more "
    "than the 300s ceiling at 8tok/s, where the most this clock can pay for is "
    "affordable_max_tokens=900 -- below the min_answer_tokens=1536 this model "
    "answers at. No request was sent and no business conclusion was generated."
)
#: 今天真机上被洗成兜底码的那一发之外的一切失败：认不出码就照旧走老路。
PLAIN_ERRORS = [
    "模型暂时不可用",
    "psycopg.errors.ConnectionTimeout: connection attempt timed out",
    CLOCK_ERROR,
]


def _watch(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")


def _messages(caplog):
    return [record.getMessage() for record in caplog.records]


def _queue(name, *, max_attempts=3):
    """真 ReliableQueue + 假 Redis：与 tests/test_r81_queue_terminal_retry.py 同一套夹具。"""
    from app.common.reliable_queue import ReliableQueue

    queue = ReliableQueue(
        FakeRedis(), name=f"r448-{name}", lease_seconds=30, max_attempts=max_attempts
    )
    message = queue.enqueue(
        {
            "message": "把上季度的经营情况写成报告",
            "session_id": "session-r448",
            "principal": {"user_id": "u-r448", "username": "staff-r448", "roles": ["staff"]},
        },
        f"idem-r448-{name}",
    )
    return queue, message.request_id


def _burn_with_record(queue, request_id, make_record, *, limit=10):
    """模拟 worker 的重投循环：一直取到队列不再重投为止，数一共烧了几发。

    记录由 ``make_record()`` 现交：牙 d 那一把要用同一套夹具喂两枚只差一个键的记录，
    所以这里收的是"怎么造记录"，而不是"记录是什么"。

    这一枚件走的就是报告档那两个失败分支真正做的两件事（先交 ``report_failure_record``
    认码，再交 ``_fail_report_turn`` 判终态），只是不连着跑 ``_process_report_lane_turn``
    本体：那一枚函数一进来就 ``import app.api.v1.chat``（本机实测 17 s 起子链外加一次
    向量库写），而用例又在本文件模块层就 import 了它 —— 那正是本单要的离线形。两处
    调用点由 ``test_both_report_lane_failure_sites_hand_the_recogniser`` 从源码钉住。
    """
    shots = 0
    while shots < limit:
        reserved = queue.reserve(timeout=0)
        if reserved is None:
            break
        shots += 1
        queue_worker._fail_report_turn(
            queue, reserved.request_id, make_record(), session_id="", write_back=False
        )
        if queue.status(request_id) in {"dead", "cancelled"}:
            break
    return shots


def _burn(queue, request_id, error, *, limit=10):
    """走完整合流：报告档那两个分支对一发失败做的两件事，逐件重放。"""
    return _burn_with_record(
        queue, request_id, lambda: queue_worker.report_failure_record(error), limit=limit
    )


# ==================== 牙 a：白名单那一族首发即终态 ====================


def test_a_context_limit_refusal_dies_on_the_first_attempt(caplog):
    """判据② 牙 a：确定性拒绝第二发都不该有（改前实测红，见下面的原文）。"""
    _watch(caplog)
    queue, request_id = _queue("first-shot")

    shots = _burn(queue, request_id, Exception(RUN9C_WINDOW_ERROR))

    assert shots == 1, f"确定性拒绝被打了 {shots} 发（改前实测 3 发）"
    assert queue.status(request_id) == "dead"


def test_the_refused_turn_never_goes_back_into_pending():
    """牙 a 的另一半：名额一格都不占，pending 里不许再出现这一枚 request_id。"""
    queue, request_id = _queue("no-requeue")

    #: 先让 worker 真取走这一发（reserve 才会把 attempts 记上并把它挪出 pending），
    #: 再判终态 —— 与真机那三发的取法逐字同一条路。
    assert _burn(queue, request_id, Exception(RUN9C_WINDOW_ERROR), limit=1) == 1

    assert queue.status(request_id) == "dead"
    assert request_id not in list(queue.redis.lists.get(queue.pending_key, []))
    assert list(queue.redis.lists.get(queue.dead_key, [])) == [request_id]
    assert queue.failure(request_id) == {
        "attempts": 1,
        "last_error": CONTEXT_LIMIT_CODE,
        "max_attempts": 3,
    }


# ==================== 牙 c：原码留在台账与日志（判据③加⑥） ====================


def test_the_recogniser_keeps_the_original_code_and_states_finality():
    """判据③ 的上半句：认得出码就保留原码，并把终局判定显式写进那一格。"""
    record = queue_worker.report_failure_record(Exception(RUN9C_WINDOW_ERROR))

    assert record["error"]["code"] == CONTEXT_LIMIT_CODE
    assert record["error"]["retryable"] is False
    assert record["status"] == "failed"
    assert record["error"]["message"] == RUN9C_WINDOW_ERROR


def test_the_ledger_and_the_log_both_keep_the_original_code(caplog):
    """牙 c：兜底码不许冒充台账。改前这里读到的只有 internal_error。"""
    _watch(caplog)
    queue, request_id = _queue("keep-code")

    assert _burn(queue, request_id, Exception(RUN9C_WINDOW_ERROR), limit=1) == 1

    assert queue.failure(request_id)["last_error"] == CONTEXT_LIMIT_CODE
    line = next(m for m in _messages(caplog) if "request_id=" in m and "报告档" in m)
    assert f"-> dead: {CONTEXT_LIMIT_CODE}" in line
    assert f"reason={queue_worker.NON_RETRYABLE_DEAD_REASON}" in line
    assert "attempts=1 max_attempts=3" in line
    assert "internal_error" not in line, "原码那一格不许被兜底文案顶掉"
    assert "未产生业务结论" not in line


# ==================== 牙 b 加判据⑤：其余码逐字节不变 ====================


def test_the_record_for_an_unrecognised_failure_is_byte_identical_to_before():
    """判据⑤：认不出码就一个字都不许多——改前那一枚 dict 的键集就是 {code, message}。"""
    for text in PLAIN_ERRORS:
        record = queue_worker.report_failure_record(Exception(text))
        assert record == {"status": "failed", "error": {"code": "internal_error", "message": text}}
        assert "retryable" not in record["error"]


@pytest.mark.parametrize("text", PLAIN_ERRORS)
def test_a_non_whitelist_failure_still_burns_the_same_three_attempts(text, caplog):
    """牙 b：非白名单码的名额、退避与那行日志一个字都不许动（改前实测就是三发）。"""
    _watch(caplog)
    queue, request_id = _queue(f"budget-{PLAIN_ERRORS.index(text)}")

    shots = _burn(queue, request_id, Exception(text))

    assert shots == 3, "重试名额属于队列，不属于这一单"
    assert queue.status(request_id) == "dead"
    assert queue.failure(request_id) == {
        "attempts": 3,
        "last_error": "internal_error",
        "max_attempts": 3,
    }
    assert any("报告档未产生业务结论: internal_error" in m for m in _messages(caplog))
    assert queue_worker.NON_RETRYABLE_DEAD_REASON not in " ".join(_messages(caplog))


def test_the_non_whitelist_ledger_line_keeps_its_own_code(caplog):
    """判据⑥：那行「未产生业务结论」的口径不许被洗成兜底文案。

    走过契约的记录（老腿）本来带真码：这一发证明本单没把那条日志的 {code} 换掉。
    """
    _watch(caplog)
    queue, request_id = _queue("legacy-code")
    record = {
        "status": "failed",
        "error": {"code": "model_unavailable", "message": "model down", "retryable": True},
    }

    queue_worker._fail_report_turn(queue, request_id, record, session_id="", write_back=False)

    assert any("报告档未产生业务结论: model_unavailable" in m for m in _messages(caplog))
    assert queue.failure(request_id)["last_error"] == "model_unavailable"


# ==================== 牙 d：那一笔字段是唯一决定者 ====================


def test_the_retryable_field_alone_decides_one_shot_versus_three():
    """牙 d：同一枚原码、同一套夹具，只摘掉 retryable 这一键 —— 一发必须变三发。

    这一把要证的是"三发变一发"由这一个字段决定，不是被别的顺路改到的：认码、
    白名单、日志、队列对象四样在两支里逐字相等，唯一变量就是那一格。
    """
    record = queue_worker.report_failure_record(Exception(RUN9C_WINDOW_ERROR))
    stripped = json.loads(json.dumps(record))
    del stripped["error"]["retryable"]
    assert stripped["error"] == {k: v for k, v in record["error"].items() if k != "retryable"}
    assert stripped["status"] == record["status"]

    assert queue_worker.is_non_retryable_error(record) is True
    assert queue_worker.is_non_retryable_error(stripped) is False

    with_field = _queue("decider-with")
    without_field = _queue("decider-without")
    shots_with = _burn_with_record(
        with_field[0], with_field[1], lambda: json.loads(json.dumps(record))
    )
    shots_without = _burn_with_record(
        without_field[0], without_field[1], lambda: json.loads(json.dumps(stripped))
    )

    assert shots_with == 1
    assert shots_without == 3, "摘掉这一笔还判一发，就是别处顺路改了判定"
    #: 两支交回台账的原码必须相同：这一格相等而发数不同，才说明决定权在字段本身。
    assert with_field[0].failure(with_field[1])["last_error"] == CONTEXT_LIMIT_CODE
    assert without_field[0].failure(without_field[1])["last_error"] == CONTEXT_LIMIT_CODE


# ==================== 判据①：认码只许用在册那把尺 ====================


def test_the_worker_holds_the_registered_meter_and_no_second_one():
    """判据①：尺只有一把，且本文件不许再写一遍它的刻度。"""
    assert queue_worker.context_error_code is context_error_code
    for fragment in CONTEXT_ERROR_FRAGMENTS:
        assert fragment not in WORKER_SOURCE, f"worker 里抄了在册刻度：{fragment!r}"
    assert "def context_error_code" not in WORKER_SOURCE


# ==================== 判据②：白名单派生不许手抄，读不出锚就报错停手 ====================


def test_the_whitelist_is_derived_from_the_registered_anchor():
    """面值一个字都不许抄进 worker：白名单必须等于现读出来的那枚锚。"""
    assert queue_worker.DETERMINISTIC_REFUSAL_CODES == frozenset({CONTEXT_LIMIT_CODE})
    assert f'"{CONTEXT_LIMIT_CODE}"' not in WORKER_SOURCE, "白名单是手抄的，不是派生的"
    assert queue_worker._derive_deterministic_refusal_codes() == queue_worker.DETERMINISTIC_REFUSAL_CODES
    # 反面清单在这里是否决用的：在册可重试码一律不许混进终态表。
    assert not (queue_worker.DETERMINISTIC_REFUSAL_CODES & frozenset(_RETRIABLE_CODES))


@pytest.mark.parametrize(
    "anchor, why",
    [
        ("", "锚读成空字符串"),
        ("   ", "锚只剩空白"),
        ("not_a_ratified_code", "锚不在封闭词表里"),
        ("model_unavailable", "锚与在册可重试清单正面矛盾"),
    ],
)
def test_a_drifted_anchor_raises_instead_of_defaulting(monkeypatch, anchor, why):
    """判据② 的下半句：读不出锚就报错，绝不静默退成"全部可重试"或"全部不可重试"。"""
    monkeypatch.setattr(queue_worker, "CONTEXT_LIMIT_CODE", anchor)

    with pytest.raises(RuntimeError):
        queue_worker._derive_deterministic_refusal_codes()


def test_the_anchor_semantics_are_the_ones_the_contract_states():
    """语义锚取证：这一族之所以不可重试，是契约自己说的，不是本单推断的。"""
    from app.agents import contracts

    contract_source = Path(contracts.__file__).read_text(encoding="utf-8")
    assert "它不是可重试的错" in contract_source
    assert "所以不进 evidence._RETRIABLE_CODES" in contract_source
    enum_codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert CONTEXT_LIMIT_CODE in enum_codes


# ==================== 判据④：兄弟形状同族，两处一起改 ====================


def test_both_report_lane_failure_sites_hand_the_recogniser():
    """判据④：两处洗码形状同族（同一串字面量、同样不带 retryable、同一个消费者），一并改。"""
    body = inspect.getsource(queue_worker._process_report_lane_turn)

    assert body.count("report_failure_record(") == 2, "两处合流点都必须交回认码那一个处"
    assert '"code": "internal_error"' not in WORKER_SOURCE, "洗码字面量还留在树上"
    assert "报告档后台报错" in body and "报告档后台执行异常" in body


def test_the_legacy_lane_paths_and_the_reason_token_are_untouched():
    """R81 钉成逐字文案的那一支（deploy/queue_worker.py:838）本单不碰；原因码仍不是稳定码。"""
    assert 'queue.fail_or_retry(request_id, str(e))' in WORKER_SOURCE
    enum_codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert queue_worker.NON_RETRYABLE_DEAD_REASON not in enum_codes
    assert queue_worker.NO_MODEL_CALL_READOUT not in enum_codes
    assert CONTEXT_LIMIT_CODE in enum_codes
