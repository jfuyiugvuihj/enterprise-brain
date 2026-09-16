"""R13：挂起待办的写入、复核与 ``GET /hitl/pending``。

口径来自已批准的设计件 §3.4/§3.5：
- 列端点**必须自带 check_interrupt() 复核**，否则面板列出的是已经跑完的假挂起；
- 归属判定复用 app/storage/sessions.py:85 的 is_owned_by，与 /approve 同一个谓词；
- 访问他人会话回 **404 resource_not_found，不是 403**（本仓现行惯例，
  app/api/v1/chat.py:241-245）；
- 批准/拒绝/停止分别把行改成 resumed/refused/abandoned，改不动的留在 awaiting。
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.agents import orchestrator
from app.storage import pending_approvals as store


@pytest.fixture(autouse=True)
def memory_backend(monkeypatch):
    """离线跑：PG 不可用时走进程内账本，绝不碰真库。"""
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)
    return None


class _Result:
    """psycopg 的 Result 替身。写成类而不是 ``type(...)` + lambda``：类字典里的
    lambda 会被当方法绑定，多接一个 self。"""

    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows if rows is not None else []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


def _park(session_id="s-1", owner="u-1", steps=("chart",), **kw):
    return store.record_awaiting(
        session_id, owner, list(steps), request_id="req-1", trace_id="trace-1",
        task_id="task-1", **kw
    )


# ---------------------------------------------------------------- 写入


def test_parking_records_who_which_steps_and_until_when():
    record = _park()

    assert record.owner_user_id == "u-1"
    assert record.parked_steps == ["chart"]
    assert record.status == "awaiting"
    assert record.decided_at is None
    assert record.expires_at > record.created_at, "到期时间必须可比，面板要能显示还剩多久"
    assert (record.request_id, record.trace_id, record.task_id) == (
        "req-1",
        "trace-1",
        "task-1",
    )


def test_a_second_park_supersedes_the_previous_open_row():
    """> 一个会话同时只能有一条待批：新一轮挂起要把旧行判 stale，而不是叠两条待办。

    0008 上有 partial unique 索引兜底，所以写入侧必须先让旧行闭合，否则第二次 park
    在真库里直接违反约束。
    """
    first = _park(steps=("chart",))
    second = _park(steps=("export",))

    assert first.status == "stale"
    assert second.status == "awaiting"
    assert store.open_items(owner_user_id="u-1") == [second]


def test_an_expired_row_is_not_offered_as_a_todo():
    _park(expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())

    assert store.open_items(owner_user_id="u-1") == []
    assert store.mark_status("s-1", "resumed") is None, "过期的挂起不该还能被批准"


# ---------------------------------------------------------------- 决策三态


@pytest.mark.parametrize("status", ["resumed", "refused"])
def test_a_decision_closes_the_row(status):
    """approved=True/False 分别落 resumed/refused。

    refused 这一支是 84af113「拒绝必须真的拒绝」的账面部分：拒绝必须留下记录。
    """
    _park()

    closed = store.mark_status("s-1", status)

    assert closed.status == status
    assert closed.decided_at is not None
    assert store.open_items(owner_user_id="u-1") == []


def test_a_stopped_run_marks_the_row_abandoned_not_refused():
    """裁定 ④甲：停止 != 拒绝。账面必须能区分这两件事。"""
    _park()

    closed = store.mark_status("s-1", "abandoned")

    assert closed.status == "abandoned"
    assert "refused" not in [record.status for record in store._all_rows()]


def test_an_unparked_session_has_nothing_to_decide():
    assert store.mark_status("never-parked", "resumed") is None


# ---------------------------------------------------------------- 端点


def _request_for(user_id, username):
    from app.common.identity import Principal

    principal = Principal(user_id=user_id, username=username, roles=["staff"], department="R&D")
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": username})()},
    )(), principal


def _hitl_pending(http_request, session_id=""):
    from app.api.v1 import chat

    return asyncio.run(
        chat.hitl_pending(http_request=http_request, session_id=session_id)
    )


def test_the_list_endpoint_rechecks_the_graph_and_drops_a_finished_row(monkeypatch):
    """图里已经不挂起了，就不许再列出来——这条是"面板不撒谎"的唯一保险。"""
    _park(session_id="s-1", owner="u-1")
    _park(session_id="s-2", owner="u-1", steps=("export",))
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda thread_id: {"pending": ["export"], "labels": ["导出"]} if thread_id == "s-2" else None,
    )

    http_request, _principal = _request_for("u-1", "tester")
    payload = _hitl_pending(http_request)

    assert [item["session_id"] for item in payload["items"]] == ["s-2"]
    assert payload["count"] == 1
    assert store.get_row("s-1").status == "stale", "复核不过的行要就地标 stale"
    assert store.get_row("s-2").status == "awaiting"


def test_the_list_endpoint_only_shows_the_callers_own_items(monkeypatch):
    _park(session_id="mine", owner="u-1")
    _park(session_id="theirs", owner="u-2")
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda thread_id: {"pending": ["chart"], "labels": ["图表"]},
    )

    http_request, _principal = _request_for("u-1", "tester")

    assert [item["session_id"] for item in _hitl_pending(http_request)["items"]] == ["mine"]


def test_listing_someone_elses_session_is_404_not_403(monkeypatch):
    """本仓对"会话属主"的既有口径：别人的会话像不存在一样（app/api/v1/chat.py:241-245）。"""
    """别人的会话要像不存在一样，而不是"存在但没权限"。

    刻意用假的 registry 而不是往 tmp_path 造真文件：这里要钉的是 404/403 这一格，
    不是 SessionRegistry 自己的测试。
    """
    from fastapi import HTTPException
    from app.api.v1 import chat

    class _Registry:
        def is_owned_by(self, session_id, principal):
            return str(principal.user_id) == "u-1"

    monkeypatch.setattr(chat, "session_registry", _Registry())
    http_request, _principal = _request_for("u-2", "intruder")

    with pytest.raises(HTTPException) as caught:
        _hitl_pending(http_request, session_id="mine")

    assert caught.value.status_code == 404
    assert caught.value.detail == "resource_not_found"
    assert caught.value.status_code != 403


def test_anonymous_caller_gets_authentication_required():
    from fastapi import HTTPException

    http_request = type(
        "Request", (), {"state": type("State", (), {"principal": None, "username": ""})()}
    )()

    with pytest.raises(HTTPException) as caught:
        _hitl_pending(http_request)

    assert caught.value.status_code == 401
    assert caught.value.detail == "authentication_required"


def test_the_endpoint_payload_carries_the_labels_the_panel_shows(monkeypatch):
    _park(session_id="s-1", owner="u-1", steps=("chart", "export"))
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda thread_id: {"pending": ["chart", "export"], "labels": ["甲", "乙"]},
    )

    http_request, _principal = _request_for("u-1", "tester")
    item = _hitl_pending(http_request)["items"][0]

    assert item["parked_steps"] == ["chart", "export"]
    assert item["labels"] == ["甲", "乙"]
    assert item["status"] == "awaiting"
    assert {"session_id", "owner_user_id", "expires_at", "request_id", "trace_id"} <= set(item)
    assert json.dumps(item, ensure_ascii=False)


# ------------------------------------------------- 写入侧接线（真调用链）


def _offline_ask_stubs(monkeypatch, chat, tmp_path):
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda _q, scope="": None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))


def _request_for_user(principal):
    return type(
        "Request",
        (),
        {
            "state": type(
                "State", (), {"principal": principal, "username": principal.username}
            )()
        },
    )()


def test_asking_a_turn_that_parks_writes_the_awaiting_row(monkeypatch, tmp_path):
    """真调用链：/ask -> 图停在 HITL 前 -> 账本里必须出现一行 awaiting。

    与 R12 同一类缺陷的形状：读端和写端各写各的，中间没人接线，功能就恒等于不生效。
    这条走 chat.ask，不手工拼任何记录。
    """
    from app.api.v1 import chat
    from app.common.identity import Principal

    session_id = "hitl-wire-ask"
    principal = Principal.from_user(
        {"id": "u-9", "username": "wire", "role": "staff", "department": "R&D"}
    )
    _offline_ask_stubs(monkeypatch, chat, tmp_path)

    def fake_stream(*_args, **_kwargs):
        yield {
            "messages": [],
            "worker_results": {},
            "final_answer": "",
        }

    monkeypatch.setattr(orchestrator, "run_with_stream", fake_stream)
    monkeypatch.setattr(
        orchestrator,
        "check_interrupt",
        lambda thread_id: {"pending": ["chart"], "labels": ["生成图表"]},
    )

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message="把销量画成图并导出", session_id=session_id),
            http_request=_request_for_user(principal),
        )
    )

    async def consume():
        chunks = []
        async for item in response.body_iterator:
            chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
        return "".join(chunks)

    body = asyncio.run(consume())

    assert "event: hitl" in body, "本轮没有挂起事件，这条测试就没有意义"
    row = store.get_row(session_id)
    assert row is not None, "/ask 发了 hitl 事件却没写账，面板永远列不到它"
    assert row.status == store.AWAITING
    assert row.owner_user_id == "u-9"
    assert row.parked_steps == ["chart"]


def test_approving_and_refusing_close_the_row(monkeypatch, tmp_path):
    """真调用链：/approve 收尾必须把 awaiting 闭合，批准与拒绝分落两个终态。"""
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "session-registry.json")
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        orchestrator,
        "check_interrupt",
        lambda thread_id: {"pending": ["chart"], "labels": ["生成图表"]},
    )

    def fake_stream(*_args, **_kwargs):
        yield {
            "messages": [],
            "worker_results": {"chart": "图已生成"},
            "final_answer": "图已生成",
        }

    monkeypatch.setattr(orchestrator, "run_interrupt_stream", fake_stream)

    for approved, expected in ((True, store.RESUMED), (False, store.REFUSED)):
        session_id = f"hitl-wire-approve-{approved}"
        principal = Principal.from_user(
            {"id": "u-9", "username": "wire", "role": "staff", "department": "R&D"}
        )
        registry.bind(session_id, principal)
        store.record_awaiting(session_id, "u-9", ["chart"])

        response = asyncio.run(
            chat.approve(
                chat.ApproveRequest(session_id=session_id, approved=approved),
                http_request=_request_for_user(principal),
            )
        )

        async def consume():
            chunks = []
            async for item in response.body_iterator:
                chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
            return "".join(chunks)

        asyncio.run(consume())

        assert store.get_row(session_id).status == expected, session_id
        assert store.open_items(owner_user_id="u-9") == [], session_id


# ---------------------------------------------------------------- PG 路径


def test_production_without_the_table_fails_loudly_instead_of_using_memory(monkeypatch):
    """生产期缺表必须显式报错，不能静默降级到进程内账本（设计件 §3.4 第 5 条）。"""
    monkeypatch.setattr(store, "_database_available", lambda: True)

    class MissingTableConnection:
        """真 psycopg 连接是上下文管理器（``with conn() as c`` 开事务），假的要一样。"""

        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            return _Result({"table_name": None})

        def close(self):
            pass

    conn = MissingTableConnection()
    monkeypatch.setattr(store, "_conn", lambda: conn)

    with pytest.raises(RuntimeError, match="pending_approvals table is required"):
        store.record_awaiting("s-1", "u-1", ["chart"])


def test_the_insert_binds_the_columns_0008_declares(monkeypatch):
    """钉住 SQL 形状：别让某个字段悄悄变成 JSON blob 的一部分。"""
    monkeypatch.setattr(store, "_database_available", lambda: True)

    class FakeConnection:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            self.statements.append((sql, params))
            if "to_regclass" in sql.lower():
                # 假库里表是在的：这条测试要钉的是 INSERT 的列，不是缺表分支
                return _Result({"table_name": "pending_approvals"})
            return _Result({"id": 1})

        def close(self):
            pass

    conn = FakeConnection()
    monkeypatch.setattr(store, "_conn", lambda: conn)

    store.record_awaiting("s-1", "u-1", ["chart"], request_id="req-1", trace_id="tr-1", task_id="tk-1")

    insert = next((sql, params) for sql, params in conn.statements if "INSERT INTO pending_approvals" in sql)
    lowered = insert[0].lower()
    for column in ("session_id", "owner_user_id", "parked_steps", "expires_at", "request_id", "trace_id", "task_id"):
        assert column in lowered, column
    assert "jsonb" in lowered or "%s" in insert[0]
    assert "to_regclass" in " ".join(sql.lower() for sql, _ in conn.statements)