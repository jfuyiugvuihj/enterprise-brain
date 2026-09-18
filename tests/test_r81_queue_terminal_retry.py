"""R81 —— 队列不认账：契约判定不可重试的终态被盲重试到 dead。

缺陷（deploy/queue_worker.py:93-96）：对任何非 success/partial 结论一律 fail_or_retry，
而 ReliableQueue.fail_or_retry 在 attempts < max_attempts 时无条件 rpush 回 pending；
AgentResult.error.retryable（出厂值 False，且 model_dump() 一定带这个字段）在队列层根本没人看。
后果：一条被 row_scope_denied / no_visible_rows 拒掉的任务要白烧掉整个 max_attempts 的
模型往返才进 dead，日志满屏错误，客户端轮询在 queued/processing 之间反复振荡。

本文件的用例是**先红后绿**写的：第一条用例在改前实测红，红的原文抄在下面 ① 段末尾。

判据 → 用例
①  先红复现            test_a_final_denial_is_not_put_back_into_pending
②  直接落 dead 不耗名额  test_the_final_terminal_lands_dead_without_burning_a_retry_slot
                         test_the_denied_task_never_takes_a_second_model_round_trip
③  其余路径逐字节不变    test_a_success_conclusion_still_completes_with_the_unchanged_log_line
                         test_a_partial_conclusion_still_completes_even_with_a_final_error
                         test_a_retryable_error_still_requeues_with_the_byte_identical_log_line
                         test_a_record_that_never_states_finality_keeps_the_old_retry_path
                         test_an_empty_record_still_goes_through_the_old_retry_path
                         test_a_record_with_a_bare_string_error_keeps_the_exception_path
                         test_an_unexpected_exception_still_uses_the_old_recovery_path
                         test_cancellation_still_outranks_the_final_verdict
④  可测性与导入形状      test_the_finality_predicate_is_a_pure_single_argument_decision
                         test_the_worker_is_reachable_from_deploy_without_touching_the_layout
⑤  不新增稳定码         test_the_reason_token_is_not_a_stable_error_code
⑥  两种 dead 分得开      test_a_direct_dead_and_an_exhausted_dead_are_tellable_apart

跑法（离线，FakeRedis，一根 socket 都不开）：
    python -m pytest tests/test_r81_queue_terminal_retry.py -q
"""

import inspect
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

from app.agents.contracts import AgentResult, ErrorEnvelope
from tests.test_reliable_queue import FakeRedis

REASON = "non_retryable_terminal"
ENUM_CODES = set(get_args(ErrorEnvelope.model_fields["code"].annotation))


# ==================== ① 先红后绿的复现用例 ====================
# 改前 @6d5f5ab 实测红（原文，满 CPU 复跑一致）：
#   E   AssertionError: 契约已判定不可重试的终态被重排回了 pending：
#         status='queued' attempts=1 max_attempts=3 pending=['<request_id>'] dead=[]
#   E   assert 'queued' == 'dead'
# 也就是说这条被拒的任务还会被同一个 worker 再取走、再烧一次模型，一直到名额耗尽。


@pytest.mark.parametrize("code", ["row_scope_denied", "no_visible_rows"])
def test_a_final_denial_is_not_put_back_into_pending(monkeypatch, code):
    """判据①：R64/R65 收口的两枚授权终态（retryable 出厂 False）不得回到 pending。"""
    ctx = _install(monkeypatch, name="worker:r81-repro", record=_contract_result(code))

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    failure = ctx.queue.failure(request_id)
    assert ctx.queue.status(request_id) == "dead", (
        "契约已判定不可重试的终态被重排回了 pending："
        f"status={ctx.queue.status(request_id)!r} "
        f"attempts={failure['attempts']} max_attempts={failure['max_attempts']} "
        f"pending={_list(ctx.queue, ctx.queue.pending_key)} "
        f"dead={_list(ctx.queue, ctx.queue.dead_key)}"
    )
    assert _list(ctx.queue, ctx.queue.pending_key) == []
    assert _list(ctx.queue, ctx.queue.dead_key) == [request_id]
    assert _list(ctx.queue, ctx.queue.processing_key) == []


# ==================== ② 直接落 dead，且一个重试名额都不烧 ====================


def test_the_final_terminal_lands_dead_without_burning_a_retry_slot(monkeypatch):
    """判据②：状态可读成 dead、码还在 last_error 里、attempts 真的没涨。"""
    ctx = _install(monkeypatch, name="worker:r81-dead", record=_contract_result("row_scope_denied"))
    request_id = ctx.message.request_id

    before = ctx.queue.failure(request_id)
    assert before == {"attempts": 0, "last_error": None, "max_attempts": 3}

    assert ctx.worker.process_one() is True

    # attempts 只涨了一次，而且涨在 reserve 记账的那一次真实执行上：落 dead 这一步
    # 自己一个名额都没消耗，还剩两次没用。改前的实现会一路重排到 3 才进 dead。
    after = ctx.queue.failure(request_id)
    assert after["attempts"] == 1, "不可重试终态不该占用重试名额，还剩两次没用"
    assert after["max_attempts"] == 3
    assert after["last_error"] == "row_scope_denied", "落 dead 不许丢码，运维要能读"
    assert ctx.queue.status(request_id) == "dead"
    assert ctx.queue.result(request_id) is None
    # trace 账本照写不误：本单只改队列收敛，不许顺手把审计记录也省了。
    assert len(ctx.recorded) == 1
    assert ctx.recorded[0]["error"]["retryable"] is False


def test_the_denied_task_never_takes_a_second_model_round_trip(monkeypatch):
    """判据②：白烧模型往返是这个缺陷最贵的部分，这里直接数往返次数。"""
    ctx = _install(monkeypatch, name="worker:r81-trips", record=_contract_result("no_visible_rows"))

    assert ctx.worker.process_one() is True
    assert ctx.worker.process_one() is False, "队列已空，这条任务不该再被取走"
    assert len(ctx.calls) == 1, f"模型往返必须只有一次，实测 {len(ctx.calls)} 次"
    assert ctx.queue.failure(ctx.message.request_id)["attempts"] == 1


# ==================== ③ 其余路径逐字节不变（本单最重要护栏） ====================


def test_a_success_conclusion_still_completes_with_the_unchanged_log_line(monkeypatch, caplog):
    """判据③：success 的 complete 与日志文案一字不改。"""
    ctx = _install(monkeypatch, name="worker:r81-success", record=_ok_result("success", "R81 结论"))
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "done"
    assert ctx.queue.result(request_id) == "R81 结论"
    messages = _messages(caplog)
    assert f"request_id={request_id} 完成 status=success evidence=0" in messages
    assert "未产生业务结论" not in " ".join(messages)
    assert REASON not in " ".join(messages)


def test_a_discarded_success_still_logs_the_same_line(monkeypatch, caplog):
    """判据③：运行途中被取消 ⇒ 丢弃结果的日志文案一字不改。"""
    ctx = _install(
        monkeypatch,
        name="worker:r81-discard",
        record=_ok_result("success", "不该发布的答案"),
        pre_run=lambda queue, message: queue.cancel(message.request_id),
    )
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    messages = _messages(caplog)
    assert ctx.queue.status(request_id) == "cancelled"
    assert ctx.queue.result(request_id) is None
    assert (
        f"request_id={request_id} 结果已丢弃：运行途中被取消或租约已丢失 terminal_status=cancelled"
        in messages
    )
    assert REASON not in " ".join(messages)


def test_a_partial_conclusion_still_completes_even_with_a_final_error(monkeypatch):
    """判据③＋反证刀「动 success/partial 集合」：partial 带着不可重试错误也必须照常发布。"""
    record = _contract_result("row_scope_denied", status="partial", answer="只有知识侧的结论")
    ctx = _install(monkeypatch, name="worker:r81-partial", record=record)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "done"
    assert ctx.queue.result(request_id) == "只有知识侧的结论"
    assert _list(ctx.queue, ctx.queue.dead_key) == []
    assert ctx.queue.failure(request_id)["attempts"] == 1


def test_a_retryable_error_still_requeues_with_the_byte_identical_log_line(monkeypatch, caplog):
    """判据③：retryable 是 True 的结论，重排与日志与改前逐字一致。"""
    record = _contract_result(
        "model_unavailable",
        status="model_unavailable",
        answer="离线模式：模型不可用（error_code=model_unavailable）",
        error={"code": "model_unavailable", "message": "model down", "retryable": True},
    )
    ctx = _install(monkeypatch, name="worker:r81-retryable", record=record)
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "queued"
    assert _list(ctx.queue, ctx.queue.pending_key) == [request_id]
    assert _list(ctx.queue, ctx.queue.dead_key) == []
    messages = _messages(caplog)
    assert f"[QueueWorker] request_id={request_id} 未产生业务结论: model_unavailable" in messages
    assert REASON not in " ".join(messages)
    assert ctx.queue.failure(request_id) == {
        "attempts": 1,
        "last_error": "model_unavailable",
        "max_attempts": 3,
    }


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        # 字段缺失：raw dict 绕过契约才有这种形状 ⇒ 队列层不替契约宣布终局，照旧重试。
        ({"code": "row_scope_denied", "message": "行级拒绝"}, "row_scope_denied"),
        ({"code": "no_visible_rows"}, "no_visible_rows"),
        ({}, "rejected"),
        (None, "rejected"),
        # 不是 False 的每一档异形，行为都与改前一致。
        ({"code": "row_scope_denied", "message": "x", "retryable": None}, "row_scope_denied"),
        ({"code": "row_scope_denied", "message": "x", "retryable": 0}, "row_scope_denied"),
        ({"code": "row_scope_denied", "message": "x", "retryable": "False"}, "row_scope_denied"),
        ({"code": "row_scope_denied", "message": "x", "retryable": "false"}, "row_scope_denied"),
        ({"code": "row_scope_denied", "message": "x", "retryable": True}, "row_scope_denied"),
    ],
)
def test_a_record_that_never_states_finality_keeps_the_old_retry_path(monkeypatch, caplog, error, expected_code):
    """判据③：字段缺失/不是 False 的任何形态，仍旧走 fail_or_retry，日志逐字不变。"""
    record = {"worker": "orchestrator", "status": "rejected", "answer": "", "error": error}
    ctx = _install(monkeypatch, name="worker:r81-shapes", record=record)
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "queued"
    assert _list(ctx.queue, ctx.queue.pending_key) == [request_id]
    assert _list(ctx.queue, ctx.queue.dead_key) == []
    assert ctx.queue.failure(request_id)["last_error"] == expected_code
    messages = _messages(caplog)
    assert f"[QueueWorker] request_id={request_id} 未产生业务结论: {expected_code}" in messages
    assert REASON not in " ".join(messages)


def test_an_empty_record_still_goes_through_the_old_retry_path(monkeypatch):
    """判据③：record 为空（{} 或 None）时兜底码与重排语义都不变。"""
    for record in ({}, None):
        ctx = _install(monkeypatch, name=f"worker:r81-empty-{type(record).__name__}", record=record)

        assert ctx.worker.process_one() is True

        request_id = ctx.message.request_id
        assert ctx.queue.status(request_id) == "queued"
        assert ctx.queue.failure(request_id)["last_error"] == "internal_error"
        assert _list(ctx.queue, ctx.queue.dead_key) == []


def test_a_record_with_a_bare_string_error_keeps_the_exception_path(monkeypatch, caplog):
    """判据③：error 不是 dict 时改前就在 :94 炸、由 :115 兜住；本单不得改这条语义。"""
    record = {"worker": "orchestrator", "status": "rejected", "answer": "", "error": "row_scope_denied"}
    ctx = _install(monkeypatch, name="worker:r81-bare", record=record)
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "queued"
    assert _list(ctx.queue, ctx.queue.dead_key) == []
    assert "has no attribute" in ctx.queue.failure(request_id)["last_error"]
    messages = _messages(caplog)
    assert any(f"[QueueWorker] 失败 request_id={request_id}:" in line for line in messages)
    assert f"[QueueWorker] request_id={request_id} -> queued" in messages
    assert REASON not in " ".join(messages)


def test_an_unexpected_exception_still_uses_the_old_recovery_path(monkeypatch, caplog):
    """判据③：:115 往后那条 except 路径语义不得变（本单一个字没碰它）。"""
    ctx = _install(monkeypatch, name="worker:r81-raise")
    _watch(caplog)

    def boom(*args, **kwargs):
        raise RuntimeError("temporary")

    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", boom)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "queued"
    assert ctx.queue.reserve().request_id == request_id
    messages = _messages(caplog)
    assert f"[QueueWorker] 失败 request_id={request_id}: temporary" in messages
    assert f"[QueueWorker] request_id={request_id} -> queued" in messages
    assert REASON not in " ".join(messages)


def test_cancellation_still_outranks_the_final_verdict(monkeypatch, caplog):
    """判据③：取消仍旧优先于本单新增的收敛，不会被伪装成 dead。"""
    ctx = _install(
        monkeypatch,
        name="worker:r81-cancel",
        record=_contract_result("no_visible_rows"),
        pre_run=lambda queue, message: queue.cancel(message.request_id),
    )
    _watch(caplog)

    assert ctx.worker.process_one() is True

    request_id = ctx.message.request_id
    assert ctx.queue.status(request_id) == "cancelled"
    assert _list(ctx.queue, ctx.queue.dead_key) == []
    assert _list(ctx.queue, ctx.queue.pending_key) == []
    # 既存语义，逐字保留：fail_or_retry 的取消分支在写 last_error 之前就 return 了，
    # 所以被取消的任务不会留下错误码。本单不许把这条改成"取消也记账"。
    assert ctx.queue.failure(request_id)["last_error"] is None

    # 新分支也不许谎报：取消优先落地之后，那行日志必须写 cancelled 而不是 dead。
    marker_lines = [line for line in _messages(caplog) if REASON in line]
    assert len(marker_lines) == 1, marker_lines
    assert f"-> cancelled: no_visible_rows" in marker_lines[0]
    assert "-> dead" not in marker_lines[0]


# ==================== ④ 可测性：判定收成一个纯函数 ====================


def test_the_finality_predicate_is_a_pure_single_argument_decision():
    """判据④：deploy/queue_worker.py 原本不在任何用例覆盖内，判定必须能脱离 Redis 单测。"""
    from deploy import queue_worker

    predicate = queue_worker.is_non_retryable_error
    assert list(inspect.signature(predicate).parameters) == ["record"]

    assert predicate(_contract_result("row_scope_denied").model_dump()) is True
    assert predicate(_contract_result("no_visible_rows").model_dump()) is True
    # 判定只看错误自己怎么声明，不看状态：状态闸门留在 worker 那条一字未改的分支里，
    # 所以一条"partial + 不可重试错误"的记录在纯函数这里仍旧是 True，由 worker 放它发布。
    assert predicate(_contract_result("row_scope_denied", status="partial").model_dump()) is True
    assert predicate(_ok_result("success").model_dump()) is False

    for junk in (None, {}, [], "", 0, object(), {"status": "rejected"}):
        assert predicate(junk) is False, junk


def test_the_worker_is_reachable_from_deploy_without_touching_the_layout():
    """判据④：deploy/ 不在包里，导入靠隐式命名空间包 + conftest 的仓库根 sys.path。"""
    from deploy import queue_worker

    path = Path(queue_worker.__file__).resolve()
    assert path.name == "queue_worker.py"
    assert path.parent.name == "deploy"
    assert not (path.parent / "__init__.py").exists(), "不许为测试给 deploy/ 加 __init__.py"
    assert not (path.parent / "conftest.py").exists(), "不许为测试在 deploy/ 放 conftest"
    assert path == Path(__file__).resolve().parents[1] / "deploy" / "queue_worker.py"


# ==================== ⑤ 错误码词表：本单消费契约，不发明契约 ====================


def test_the_reason_token_is_not_a_stable_error_code():
    """判据⑤：新增的只有日志原因码，稳定码集合一个字没加，码本身也从记录里原样取。"""
    from deploy import queue_worker

    assert queue_worker.NON_RETRYABLE_DEAD_REASON == REASON
    assert REASON not in ENUM_CODES
    assert "authorization_required" not in ENUM_CODES  # 既有兜底拒绝码也不在枚举里，本单不动它

    source = Path(queue_worker.__file__).read_text(encoding="utf-8")
    # worker 里出现过的稳定码字面量，改前实测只有兜底的那一枚，本单不许增加。
    codes_in_worker = set(re.findall(r'"([a-z][a-z_]+)"', source)) & ENUM_CODES
    assert codes_in_worker == {"internal_error"}
    # 既有的"无授权主体"拒绝码原样保留，既不换新码也不摘掉。
    assert '"authorization_required"' in source


# ==================== ⑥ 运维可见：两种 dead 必须分得开 ====================


def test_a_direct_dead_and_an_exhausted_dead_are_tellable_apart(monkeypatch, caplog):
    """判据⑥：前者是授权设计的正常后果，后者是故障，混在一行里运维会查错地方。"""
    from app.common.reliable_queue import ReliableQueue

    # 直接落 dead：一条不可重试终态，名额还剩两次。
    direct = _install(monkeypatch, name="worker:r81-direct", record=_contract_result("row_scope_denied"))
    _watch(caplog)
    assert direct.worker.process_one() is True
    direct_id = direct.message.request_id
    direct_messages = _messages(caplog)
    assert len(direct_messages) > 0
    direct_line = next(line for line in direct_messages if REASON in line)
    assert f"request_id={direct_id}" in direct_line
    assert f"-> dead: row_scope_denied" in direct_line
    assert "attempts=1 max_attempts=3" in direct_line
    assert isinstance(direct.queue, ReliableQueue)

    # 重试耗尽落 dead：走改前的老路，那行日志一个字没改，也没有新原因码。
    caplog.clear()
    exhausted = _install(
        monkeypatch,
        name="worker:r81-exhausted",
        max_attempts=1,
        record=_contract_result(
            "model_unavailable",
            status="model_unavailable",
            error={"code": "model_unavailable", "message": "model down", "retryable": True},
        ),
    )
    _watch(caplog)
    assert exhausted.worker.process_one() is True
    exhausted_id = exhausted.message.request_id
    exhausted_messages = _messages(caplog)
    assert exhausted.queue.status(exhausted_id) == "dead"
    assert exhausted.queue.failure(exhausted_id) == {
        "attempts": 1,
        "last_error": "model_unavailable",
        "max_attempts": 1,
    }
    assert f"[QueueWorker] request_id={exhausted_id} 未产生业务结论: model_unavailable" in exhausted_messages
    assert REASON not in " ".join(exhausted_messages)


# ==================== 支撑用的最小夹具（全部离线） ====================


def _install(monkeypatch, *, name="worker:r81", max_attempts=3, record=None, pre_run=None):
    """照 tests/test_queue_worker_reliability.py 的路子：真 ReliableQueue + FakeRedis + 桩图。"""
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name=name, lease_seconds=30, max_attempts=max_attempts)
    message = queue.enqueue(_payload(), f"idem-{name}")
    calls = []
    recorded = []

    def fake_run(user_message, thread_id="default", user=None):
        if pre_run is not None:
            pre_run(queue, message)
        calls.append({"user_message": user_message, "thread_id": thread_id})
        return record

    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(queue_worker, "record_agent_result", lambda rec, **kwargs: recorded.append(rec))
    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", fake_run)
    return SimpleNamespace(
        queue=queue,
        message=message,
        calls=calls,
        recorded=recorded,
        worker=queue_worker,
    )


def _payload(**overrides):
    payload = {
        "message": "华东区上个季度的报销标准是多少",
        "session_id": "session-r81",
        "principal": {"user_id": "u-r81", "username": "staff-r81", "roles": ["staff"]},
    }
    payload.update(overrides)
    return payload


def _contract_result(code, **overrides):
    """走过真契约的记录：retryable 由 ErrorEnvelope 出厂值决定，不手抄。"""
    data = {
        "worker": "orchestrator",
        "status": "rejected",
        "answer": "",
        "request_id": "req-r81",
        "trace_id": "trace-r81",
        "task_id": "task-r81",
        "error": {"code": code, "message": "这些行不在你的可见范围内"},
    }
    data.update(overrides)
    return AgentResult.model_validate(data)


def _ok_result(status="success", answer="R81 结论"):
    return _contract_result("internal_error", status=status, answer=answer, error=None)


def _list(queue, key):
    return list(queue.redis.lists.get(key, []))


def _watch(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")


def _messages(caplog):
    return [record.getMessage() for record in caplog.records]
