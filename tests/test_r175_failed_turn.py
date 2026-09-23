"""R175：员工批过板而那一轮被系统跑挂了 —— 那一行账必须闭合，而且屏上要有那句话。

复现的原文（本树实读逐行核对，不抄留档结论）：
- ``app/api/v1/chat.py`` 的 ``kind == "error"`` 腿发 ``request.failed(internal_error)``
  之后 ``break``，整条腿一次都没调用 ``_decide_pending_approval``；
- ``budget.expired()`` 腿发 ``request.failed(task_timeout)`` 之后 ``break``，同样没闭合；
- 对照：取消腿写 ``ABANDONED``、收尾腿写 ``RESUMED``/``REFUSED``。
⇒ 只有「跑挂了」和「跑超时了」这两条路把员工已经拍过板的那一行留在 ``awaiting``。
员工视角：待办屏要么把同一件事当新待办原样列回来（图还挂在同一个中断上，等于让同一轮
resume 第二遍），要么下次开屏被复核腿就地判成 ``stale``（「已作废」），中间没有任何一处
对他说「你批过了，但那一轮失败了」。而审计里躺着一行 approved —— 三处各讲一句话。

判据逐条：
① 两条出口都闭合，且不复用 ``REFUSED``（故障 != 拒批：与取消腿「停止 != 拒绝，写
   abandoned 绝不写 refused」同一条裁定）。反证 ①②③ =
   ``test_a_crashed_round_closes...`` / ``test_a_timed_out_round_closes...`` /
   ``test_a_failed_round_never_writes_anything_but_failed``。
② 员工看得见：闭合后不再作为待办列出，而以 ``failed_turns`` 回到同一屏。
③ 不许把失败伪装成完成：两条腿一条 ``request.completed`` 都不许有。
④ 审计走既有 ``record_audit``，白名单只放 主体/资源标识/判定结果/稳定码，零正文。
⑤ 反证常驻：本文件就是那三把，摘掉任一处闭合或改写成 refused，当场红。

全进程内：假编排 + 临时会话注册表 + 进程内账本。不打模型、不开真端口、不连 PG、不碰 chroma_db。
"""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from app.common.identity import Principal
from app.storage import pending_approvals as store
from app.storage.sessions import SessionRegistry
from test_r190_status_failed_domain import (  # noqa: T401  共用同一份离线 DDL 重放，词表不外抄
    CATALOG_TAIL_VERSION,
    status_domain_through,
)

SESSION_ID = "r175-crash"
OWNER = "u-r175"
PARKED_STEPS = ("chart",)

#: 两条漏闭的出口。这一枚名字是全部判据的主键，与 chat.py 发出的 error_code 逐字相同。
EXITS = ("internal_error", "task_timeout")

#: 哨兵：那一刻它确实存在于进程里（worker 抛出的原文），所以「顺手把上下文写进审计」
#: 这种实现一旦落在本格上就会当场红。
BODY_SENTINEL = "R175T 这一段是那一轮 worker 抛出的原文 一个字都不许进审计台账"


def crashing_stream(*_args, **_kwargs):
    raise RuntimeError(BODY_SENTINEL)
    yield  # pragma: no cover - 只为把本函数变成生成器


def hanging_stream(*_args, **_kwargs):
    # 比 CHAT_REQUEST_TIMEOUT 长，保证超时限那一腿一定被走到；0.3s 不拖慢测试会话。
    time.sleep(0.3)
    yield {"messages": [], "worker_results": {}, "final_answer": ""}


def exit_stream(error_code: str):
    return crashing_stream if error_code == "internal_error" else hanging_stream


def exit_env(error_code: str) -> dict:
    return {} if error_code == "internal_error" else {"CHAT_REQUEST_TIMEOUT": "0.01"}


#: 两条腿各自在现场备着的那句「人读的原文」。它必须真的出现在流里（否则本文件的哨兵
#: 什么都没证），又必须一个字都不进审计台账。
EXIT_BODY_TOKEN = {
    "internal_error": BODY_SENTINEL,
    "task_timeout": "请求超过系统处理时限",
}


def _principal(user_id: str = OWNER, username: str = "r175-approver") -> Principal:
    return Principal.from_user(
        {"id": user_id, "username": username, "role": "manager", "department": "finance"}
    )


def _request_for(principal: Principal):
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


@pytest.fixture(autouse=True)
def memory_ledger(monkeypatch):
    """待批账本走进程内后端：判据要读账面，但绝不允许碰真库。"""
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)


def _park(session_id: str = SESSION_ID, owner: str = OWNER) -> None:
    """预置一行「员工已经在待办屏上点了同意」的账。"""
    store.record_awaiting(
        session_id,
        owner,
        list(PARKED_STEPS),
        request_id="req-r175-parked",
        trace_id="trace-r175-parked",
        task_id="task-r175-parked",
    )


def _offline(monkeypatch, tmp_path, stream, *, pending=PARKED_STEPS, env=None):
    """把 /approve 的依赖摘成离线件，并预置那一行 awaiting。"""
    from app.api.v1 import chat

    principal = _principal()
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", stream)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", stream)
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda _tid: None if pending is None else {"pending": list(pending), "labels": ["📈 生成图表"]},
    )
    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION_ID, principal)
    monkeypatch.setattr(chat, "session_registry", registry)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, str(value))
    _park()
    return chat, principal


def _approve_request(chat, principal):
    """端点协程（不起服务、不开端口）。要在跑着的循环里边读边取证时用这一枚。"""
    return chat.approve(
        chat.ApproveRequest(session_id=SESSION_ID, approved=True),
        http_request=_request_for(principal),
    )


def _drive_approve(chat, principal):
    """一次性驱动整条 /approve：返回 StreamingResponse。"""
    return asyncio.run(_approve_request(chat, principal))


async def _read_all(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _run_exit(monkeypatch, tmp_path, error_code: str) -> str:
    """真驱动一条出口，返回整条 SSE 正文。"""
    chat, principal = _offline(
        monkeypatch, tmp_path, exit_stream(error_code), env=exit_env(error_code)
    )
    return asyncio.run(_read_all(_drive_approve(chat, principal)))


def event_names(body: str) -> list[str]:
    return [
        line.removeprefix("event: ").strip()
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


def payload_of(body: str, name: str) -> dict:
    matches = []
    current = None
    for line in body.splitlines():
        if line.startswith("event: "):
            current = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and current == name:
            matches.append(json.loads(line.removeprefix("data: ")))
            current = None
    assert len(matches) == 1, f"{name} 应当恰好一条，实际 {len(matches)} 条"
    return matches[0]


def _list_pending(chat, principal, **kwargs) -> dict:
    return asyncio.run(chat.hitl_pending(http_request=_request_for(principal), **kwargs))


# ------------------------------------------------- 判据① · 两条漏闭的出口各自闭合


def test_a_crashed_round_closes_the_row_the_approver_already_decided(monkeypatch, tmp_path):
    """反证 ①：摘掉 error 腿的闭合，本用例当场红。"""
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    assert store.get_row(SESSION_ID).status == store.AWAITING, "前提：这一轮员工刚批过"

    body = asyncio.run(_read_all(_drive_approve(chat, principal)))

    assert payload_of(body, "request.failed")["data"]["error_code"] == "internal_error", (
        "前提不成立：这一轮没走挂掉那条腿"
    )
    row = store.get_row(SESSION_ID)
    assert row.status == store.FAILED, (
        "那一行必须落在 failed 这一格：留在 awaiting = 同一轮被 resume 第二遍，"
        "写成 refused = 把故障说成员工驳回"
    )
    assert row.decided_at, "闭合必须留下时间，否则事后查不到它是哪一秒结束的"
    assert store.open_items(owner_user_id=OWNER) == []


def test_a_timed_out_round_closes_the_row_the_approver_already_decided(monkeypatch, tmp_path):
    """反证 ②：摘掉 timeout 腿的闭合，本用例当场红。"""
    chat, principal = _offline(
        monkeypatch, tmp_path, hanging_stream, env={"CHAT_REQUEST_TIMEOUT": "0.01"}
    )

    body = asyncio.run(_read_all(_drive_approve(chat, principal)))

    assert payload_of(body, "request.failed")["data"]["error_code"] == "task_timeout"
    row = store.get_row(SESSION_ID)
    assert row.status == store.FAILED, "超时限同样是一轮失败，账不许留在 awaiting 等下次开屏"
    assert store.open_items(owner_user_id=OWNER) == []


@pytest.mark.parametrize("error_code", EXITS)
def test_the_ledger_is_closed_before_the_failed_frame_leaves(
    monkeypatch, tmp_path, error_code
):
    """次序也要钉：闭合排在发帧之前，与取消腿/收尾腿同一个次序。

    客户端在读到失败帧这一刻断线（真实 SSE 里天天发生），那一行账也必须已经闭合；
    把 ``_fail_pending_approval_turn`` 挪到 yield 之后就红。
    """
    chat, principal = _offline(
        monkeypatch, tmp_path, exit_stream(error_code), env=exit_env(error_code)
    )

    async def read_until_failed_frame():
        status_at_frame = None
        response = await _approve_request(chat, principal)
        async for chunk in response.body_iterator:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            if "event: request.failed" in text:
                status_at_frame = store.get_row(SESSION_ID).status
                break
        return status_at_frame

    assert asyncio.run(read_until_failed_frame()) == store.FAILED


# ---------------------------------------- 判据① 的牙齿 · 故障不许冒充任何一格人的决定


@pytest.mark.parametrize("error_code", EXITS)
def test_a_failed_round_never_writes_anything_but_failed(monkeypatch, tmp_path, error_code):
    """反证 ③：把这一格写成 REFUSED（故障冒充拒批）就红；写成 ABANDONED/STALE 同样红。

    账面上只留一行，而且那一行必须说「系统没跑完」。refused 说的是员工的决定，
    abandoned 说的是员工按了停止，stale 说的是图不再确认这次挂起 —— 三句都不是这里发生的事。
    """
    _run_exit(monkeypatch, tmp_path, error_code)

    statuses = [row.status for row in store._all_rows()]
    assert statuses == [store.FAILED], f"把 {error_code} 写成 {statuses} 就是替员工说了一句他没说的话"
    assert store.REFUSED not in statuses
    assert store.ABANDONED not in statuses


def test_the_failure_status_goes_through_the_existing_state_machine():
    """判据①「不许新造第二套状态机」：新终态走的就是既有那组常量与同一个 mark_status。"""
    assert store.FAILED in store.ALL_STATUSES
    assert store.FAILED in store.DECIDED_STATUSES, "failed 是一格闭合，不是半开"
    assert store.AWAITING not in store.DECIDED_STATUSES
    _park()
    assert store.mark_status(SESSION_ID, store.FAILED).status == store.FAILED
    with pytest.raises(ValueError, match="unsupported pending approval status"):
        store.mark_status(SESSION_ID, "exploded")


def test_every_status_the_code_can_write_now_reaches_pg_including_the_failure():
    """R175 交工时那半条腿写不进 PG；0013 前滚之后六枚全通 —— 凭据是把目录重放到尾号。

    这枚钉子原来是「``failed`` 是唯一一枚 PG 写不进去的」（Kepler 具名：多一枚漏一枚都红）。
    R190 之后它测的已经不是事实，按判据改口成现行凭据，**不删枚不置灰**：取值一律从
    ``migrations/*.sql`` 经 ``app.db.migrations`` 的 loader 重放出来，与 ``PG_STATUSES`` /
    ``ALL_STATUSES`` 逐枚对判，本文件不抄词表。反向那一格仍然留着：0008 单独重放出来的域不许
    含 ``failed`` —— 放开只许发生在前滚的那一版，已发布的迁移文本一字不许改，改了就又是 R175
    当时那种形状（代码六枚、DDL 五枚），而且 ``app/api/v1/chat.py`` 那条注释也得跟着摘。
    """
    domain = status_domain_through(CATALOG_TAIL_VERSION)

    assert domain == set(store.PG_STATUSES) == set(store.ALL_STATUSES)
    assert store.FAILED in domain, "批准之后跑挂/超时的那一轮必须能写进 PG，而不是留在 awaiting"
    assert set(store.ALL_STATUSES) - domain == set(), sorted(set(store.ALL_STATUSES) - domain)
    assert store.FAILED not in status_domain_through("0008"), (
        "0008 是已发布迁移：它放开就意味着有人改了历史文件的字节，清单与 schema_migrations 会一起对不上"
    )


# ---------------------------------------------------- 判据③ · 失败不许穿完成的衣服


@pytest.mark.parametrize("error_code", EXITS)
def test_neither_failure_exit_dresses_the_failure_up_as_completion(
    monkeypatch, tmp_path, error_code
):
    """与 chat.py:2597-2618 的 no_answer_produced 同一裁定：什么都没产出就不许报 completed。"""
    body = _run_exit(monkeypatch, tmp_path, error_code)

    names = event_names(body)
    assert "request.completed" not in names, f"{error_code} 那一腿报 completed 就是伪装完成"
    assert names == ["request.started", "request.failed", "error"], names
    assert payload_of(body, "request.failed")["data"]["error_code"] == error_code


# -------------------------------------------------- 判据② · 员工那屏看得见这件事


@pytest.mark.parametrize("error_code", EXITS)
def test_the_todo_screen_stops_listing_the_closed_round(monkeypatch, tmp_path, error_code):
    """闭合之后：不许再当新待办列出来，而要以「失败的那一轮」回到同一屏。"""
    chat, principal = _offline(
        monkeypatch, tmp_path, exit_stream(error_code), env=exit_env(error_code)
    )
    body = asyncio.run(_read_all(_drive_approve(chat, principal)))
    assert f'"error_code": "{error_code}"' in body, "前提不成立：这一轮没走那条出口"

    payload = _list_pending(chat, principal)

    assert [item["session_id"] for item in payload["items"]] == [], "同一件事又当新待办列回来"
    turns = payload["failed_turns"]
    assert [turn["session_id"] for turn in turns] == [SESSION_ID]
    assert turns[0]["status"] == store.FAILED
    assert turns[0]["parked_steps"] == list(PARKED_STEPS)
    assert turns[0]["request_id"] == "req-r175-parked", "要能对着那一轮，不然这句话没有主语"
    assert payload["failed_turns_has_more"] is False


def test_the_recheck_leg_never_judges_a_failed_turn_stale(monkeypatch, tmp_path):
    """「已作废」这一格不许再落到批过板的人头上：复核腿压根不该看见失败行。

    这里刻意让图不再确认这次挂起（跑挂了之后图可能已推进，也可能还在同一个中断上），
    旧行为是把它就地判成 stale；闭合之后它压根不进那条循环。
    """
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    asyncio.run(_read_all(_drive_approve(chat, principal)))
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)

    payload = _list_pending(chat, principal)

    assert store.get_row(SESSION_ID).status == store.FAILED
    assert store.STALE not in [row.status for row in store._all_rows()]
    assert [turn["session_id"] for turn in payload["failed_turns"]] == [SESSION_ID]


def test_the_panel_asks_the_graph_once_per_todo_and_zero_times_per_failed_turn(
    monkeypatch, tmp_path
):
    """复核是有代价的（每行一枪），也是危险的（对失败行开枪就会写出 stale）：都要钉住。"""
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    asyncio.run(_read_all(_drive_approve(chat, principal)))
    other = "r175-still-open"
    registry = chat.session_registry
    registry.bind(other, principal)
    _park(other)
    calls = []
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda tid: calls.append(tid) or {"pending": list(PARKED_STEPS), "labels": ["📈 生成图表"]},
    )

    payload = _list_pending(chat, principal)

    assert [item["session_id"] for item in payload["items"]] == [other]
    assert [turn["session_id"] for turn in payload["failed_turns"]] == [SESSION_ID]
    assert calls == [other], f"失败行不许向图复核，实际开枪 {calls}"


def test_an_expired_failed_turn_stops_occupying_the_screen(monkeypatch, tmp_path):
    """这一格有界：过期的失败行仍留在账本与审计里，但不再长期占用屏上那一块。

    口径不是新造的 —— 与「过期挂起不再算待办」用的是同一枚 ``expires_at``（账本层唯一的
    行动窗口）。没有这一条，失败列表只会随时间单调增长。
    """
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    asyncio.run(_read_all(_drive_approve(chat, principal)))
    assert store.failed_items(owner_user_id=OWNER), "前提：还没到期"

    later = store._NOW() + timedelta(hours=48)
    monkeypatch.setattr(store, "_NOW", lambda: later)

    assert store.failed_items(owner_user_id=OWNER) == []
    assert _list_pending(chat, principal)["failed_turns"] == []
    assert store.get_row(SESSION_ID).status == store.FAILED, "行不许被删，只是不再上屏"


def test_someone_elses_failed_turn_is_not_listed(monkeypatch, tmp_path):
    """归属过滤 fail-closed：别人的失败那一轮，连这句话都不该在别人屏上出现。"""
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    asyncio.run(_read_all(_drive_approve(chat, principal)))
    _park("r175-foreign", owner="u-someone-else")

    payload = _list_pending(chat, principal)

    assert [turn["session_id"] for turn in payload["failed_turns"]] == [SESSION_ID]
    # 别人的那一行确实存在，只是归不到本账号头上 —— 两边各钉一次，防止「空列表」
    # 是因为根本没写进行而虚假成立。
    store.mark_status("r175-foreign", store.FAILED)
    assert [row.session_id for row in store.failed_items(owner_user_id="u-someone-else")] == [
        "r175-foreign"
    ]
    assert [row.session_id for row in store.failed_items(owner_user_id=OWNER)] == [SESSION_ID]


def test_a_second_park_after_a_failure_is_not_blocked_by_the_failed_row(monkeypatch, tmp_path):
    """新挂起与旧失败行必须共存：0008 的 partial unique 只圈 awaiting。

    同时钉住一句话不许被顶掉 —— 重新问一次而再次挂起时，那一笔新的在待办里，
    「你批过而失败了」那一笔仍然在，两句各说各的事。
    """
    chat, principal = _offline(monkeypatch, tmp_path, crashing_stream)
    asyncio.run(_read_all(_drive_approve(chat, principal)))

    _park(SESSION_ID)

    payload = _list_pending(chat, principal)
    statuses = sorted(row.status for row in store._all_rows())
    assert statuses == sorted([store.AWAITING, store.FAILED]), statuses
    assert [item["session_id"] for item in payload["items"]] == [SESSION_ID]
    assert len(payload["failed_turns"]) == 1, "旧的那一句不许被新一轮顶掉"


# -------------------------------------------------------- 判据④ · 审计零正文


@pytest.fixture()
def audit_rows(monkeypatch) -> list[dict]:
    """把 record_audit 包一层：原实现照调（落点已由 tests/conftest.py 沙箱），顺手取调用参数。"""
    import app.api.v1.chat as chat_module
    import app.common.audit as audit_module

    original = audit_module.record_audit
    rows: list[dict] = []

    def _record(principal, action, outcome, resource="", reason="", **kwargs):
        event = original(principal, action, outcome, resource, reason, **kwargs)
        rows.append(
            {
                "action": str(action),
                "outcome": str(outcome),
                "resource": str(resource),
                "reason": str(reason),
                "kwargs": kwargs,
                "event": event,
            }
        )
        return event

    monkeypatch.setattr(chat_module, "record_audit", _record)
    return rows


@pytest.mark.parametrize("error_code", EXITS)
def test_each_failure_exit_leaves_exactly_one_audit_line_with_no_body(
    monkeypatch, tmp_path, audit_rows, error_code
):
    """一条腿一行账：主体 + 资源标识 + 判定结果 + 稳定码，其余一格都不许多。"""
    body = _run_exit(monkeypatch, tmp_path, error_code)

    token = EXIT_BODY_TOKEN[error_code]
    assert token in body, "前提不成立：那句原文没经过本用例，哨兵就没在证任何事"
    lines = [row for row in audit_rows if row["resource"] == store_ledger_surface()]
    assert len(lines) == 1, f"应当恰好一行，实际 {len(lines)} 行"
    line = lines[0]

    assert line["action"] == "resource:approve"
    assert line["outcome"] == "failure"
    assert line["reason"] == error_code, "稳定码必须是稳定码，不是人读的那句原文"
    assert str(line["kwargs"]["request_id"] or "").startswith("req-")
    event = line["event"]
    assert event["username"] == "r175-approver", "主体由 record_audit 自己投影，这里不另写一份"
    assert event["owner_id"] == OWNER
    assert token not in json.dumps(event, ensure_ascii=False), "人读的原文灌进台账 = 往审计里塞内容"
    assert not event["before_summary"] and not event["after_summary"]
    assert event["resource"] == store_ledger_surface()


def store_ledger_surface() -> str:
    """面名从实现里读，不在测试里抄第二份常量（抄的那份迟早漂）。"""
    from app.api.v1.chat import HITL_LEDGER_SURFACE

    return HITL_LEDGER_SURFACE
