"""R254 · 队列道交回来的终态必须是真的（判据①②③④⑥）。

来历：09-25 17:51:42–18:18:00 那扇真机窗（判读全文
`docs/testing/run8-phase2-readout-2026-09-25.md`，账件 `docs/testing/sidecar-run8p2.jsonl`
与 `docs/testing/answers-run8p2.jsonl`）。报告档 20 题在 `REPORT_LANE_VIA_QUEUE=on` 下量红：

| 那一窗实测到的 | 本文件钉住它不复发的那一枚用例 |
|---|---|
| 20 行终态里 `awaiting_hitl=True` 有 12 枚，其中 11 枚把同一句 37 字挂起文案当正文交回，队列侧照报 `final=done` | ① → `test_a_parked_turn_...` |
| `events[]` 直方图只有 `{queued: 20, done: 20}`，含 `sources` 的行 0/20，answers 里 `evidence` 非空 0 | ② → `test_the_source_rows_published_by_the_worker...` |
| `done` 载荷与 `/queue/status` 上没有任何 token 读数，而真库 `model_calls` 在这 20 个 request_id 上有 70 行（Σinput 91,271 / Σoutput 18,859） | ③ → `test_the_queue_readout_reports_the_tokens...` |
| request_id `64c3ef3b49174fc4b03994af7b0364a6` 在 `model_calls` 里一枚记录都没有，队列侧仍 `final=done` | ④ → `test_a_run_that_never_called_a_model...` |

判据⑤（两道同形）与同步道那六处 `done` 出口在 `tests/test_r254_sync_lane_terminal.py`；
契约文字在 `docs/api/contract-v1.md` 的 `## Long Task Status` 与
`### Structured terminal readout` 两节。

全程离线：`FakeRedis` 加真 `StateGraph`，一发模型都不打、一个端口都不开、一行生产 redis
都不写。`model_calls` 台账换成只回脚本行的替身，待批账本走进程内那一腿。
"""

import json
import re
from types import SimpleNamespace

import pytest

from app.common import reliable_queue
from app.common.reliable_queue import ReliableQueue
from app.storage import pending_approvals
from deploy import queue_worker
from tests.test_approve_canonical_events import (
    FINANCE_DOC,
    HR_DOC,
    SECRET_DOC,
    doc_agent_result,
    finance_principal,
    retriever_hits,
)
from tests.test_r37_report_lane_worker import (
    BACKGROUND_ANSWER,
    PARK_EXPORT,
    USERNAME,
    USER_ID,
    FakeRedis,
    _FakeStream,
    _SinkWorker,
    _install_worker,
    _parked_graph,
    _request_id,
    _state,
)

#: 客户端读终态那扇门的真实前缀（判据①的可寻址断言从它反推批准门的地址）。
QUEUE_STATUS_PATH = "/api/v1/queue/status/"

#: 09-25 那一窗真库里的两枚实际读数（Σinput 91,271 / Σoutput 18,859），本文件用它当尺子。
WINDOW_PROMPT_TOKENS = 91_271
WINDOW_COMPLETION_TOKENS = 18_859
WINDOW_USAGE_ROWS = [
    {"input_tokens": 45_623, "output_tokens": 9_430},
    {"input_tokens": 45_648, "output_tokens": 9_429},
]


# ==================== 台账替身：读数只许来自它，一枚都不许多 ====================


class _Ledger:
    """顶替真库的 `model_calls`：按 request_id 回脚本里的行，并记下每一次怎么被问的。"""

    def __init__(self, rows):
        # 没写 request_id 的脚本行对任意一轮都应答；写了的就只对它那一轮应答。
        self.rows = [dict(row, any_request="request_id" not in row) for row in rows]
        self.calls = []

    def fetch_table(self, table, where, *params):
        request_id = str(params[0]) if params else ""
        self.calls.append({"table": table, "where": where, "request_id": request_id})
        return [
            dict(row, request_id=request_id)
            for row in self.rows
            if row.get("any_request") or row.get("request_id") == request_id
        ]


class _BrokenLedger:
    """台账连不上：文案里带主机与账号，用来验凭据不许进日志。"""

    def __init__(self):
        self.calls = 0

    def fetch_table(self, *_args, **_kwargs):
        self.calls += 1
        raise RuntimeError(
            "connection to server failed: host=db.internal user=postgres password=hunter2"
        )


def _window_rows():
    return [dict(row, any_request=True) for row in WINDOW_USAGE_ROWS]


def _pg_ledger(monkeypatch, rows):
    """PG 六表在位的那台机器（唯一 authoritative 的一本账）。"""
    from app.trace import store as trace_store

    ledger = _Ledger(rows)
    monkeypatch.setattr(
        trace_store,
        "default_trace_store",
        lambda: SimpleNamespace(database=ledger, persistence=None),
    )
    return ledger


def _broken_ledger(monkeypatch):
    from app.trace import store as trace_store

    ledger = _BrokenLedger()
    monkeypatch.setattr(
        trace_store,
        "default_trace_store",
        lambda: SimpleNamespace(database=ledger, persistence=None),
    )
    return ledger


def _side_ledger(monkeypatch):
    """PG 不在位的部署：只有那台机器自己看得见的 JSON 侧账。

    返回那本账的**活**列表：`request_id` 要等入队之后才知道，所以行在跑之前就补进去。
    按 request_id 过滤这件事在侧账这一腿上是 `app/api/v1/chat.py::model_call_rows` 自己做的
    （PG 那一腿交给 SQL 谓词），所以这一本账才是判据③「只数这一轮」的真测试。
    """
    from app.trace import store as trace_store

    rows = []
    monkeypatch.setattr(
        trace_store,
        "default_trace_store",
        lambda: SimpleNamespace(
            database=None, persistence=SimpleNamespace(list=lambda _table: list(rows))
        ),
    )
    return rows


def _queue_principal():
    """部门/密级取 finance 那一档（本轮才有一条真能放行的出处），归属人沿用 r37 夹具那枚 user_id。

    这两格分不开的话，判据②的用例就得先造一个不属于自己的主体——那是拿越权当测试前提，
    本单一条都不许出现。
    """
    dumped = finance_principal().model_dump()
    dumped["user_id"] = USER_ID
    dumped["username"] = USERNAME
    return dumped


# ==================== 驱动器 ====================


def _parked_turn(monkeypatch, tmp_path, *, name, session, rows=()):
    """报告档在队列里挂起的一轮：真 StateGraph + interrupt_before，导出节点一次都不执行。"""
    ledger = _pg_ledger(monkeypatch, rows)
    sink = tmp_path / f"{name}-artifact-must-not-exist"
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name=name,
        payload={"session_id": session},
        graph=_parked_graph(_SinkWorker(sink)),
    )
    ctx.sink = sink
    ctx.ledger = ledger
    return ctx


def _answered_turn(monkeypatch, tmp_path, *, name, session, rows, hits=None, max_attempts=3):
    """报告档在队列里跑完并交回正文的一轮；`hits=None` 是「本轮压根没有文档证据」。"""
    ledger = _pg_ledger(monkeypatch, rows)
    evidence = {} if hits is None else {"doc": doc_agent_result(hits)}
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name=name,
        max_attempts=max_attempts,
        payload={"session_id": session, "principal": _queue_principal()},
        stream=_FakeStream([_state(BACKGROUND_ANSWER, evidence)]),
    )
    ctx.ledger = ledger
    return ctx


def _poll(monkeypatch, ctx, *, user_id=USER_ID, username=USERNAME):
    """走真那扇门 `GET /api/v1/queue/status/{id}`：客户端读到什么，这里就是什么。"""
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app as fastapi_app

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: ctx.queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda name: {"id": user_id, "username": name, "role": "admin"},
    )
    response = TestClient(fastapi_app).get(
        QUEUE_STATUS_PATH + _request_id(ctx),
        headers={"Authorization": "Bearer " + create_token(username)},
    )
    assert response.status_code == 200, response.text
    return response.json()

# ==================== 判据①：挂起的一轮不许报 done，也不许把挂起文案当正文 ====================


def test_a_parked_turn_stops_saying_done(monkeypatch, tmp_path):
    """反证：把 `deploy/queue_worker.py` 挂起那一支的 `terminal=` 摘掉，这一枚先红在 status。

    09-25 实测的 11 枚就是这个形状：worker 记 `awaiting_hitl=True`、把 37 字文案当 `result`
    交回、队列侧 `final=done`。同步道靠客户端 `APPROVAL_ROUNDS` 一轮轮顶过去，队列道顶不
    过去 ⇒ 报告档在队列里根本走不完。那是 P1 产品缺陷，不是慢。
    """
    ctx = _parked_turn(monkeypatch, tmp_path, name="r254-park", session="r254-park-session")

    assert ctx.worker.process_one() is True

    request_id = _request_id(ctx)
    assert ctx.queue.status(request_id) == "awaiting_approval"
    assert ctx.sink.exists() is False, "挂起没保住就等于自动批准"


def test_a_parked_turn_publishes_no_answer_at_all(monkeypatch, tmp_path):
    """那一轮的 `result` 是「没有正文」（null），不是那句 37 字挂起说明。"""
    ctx = _parked_turn(monkeypatch, tmp_path, name="r254-noresult", session="r254-noresult-session")

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    assert body["result"] is None
    assert body["answer_present"] is False
    assert body["answer_is_park_notice"] is False
    assert PARK_EXPORT not in json.dumps(body, ensure_ascii=False, default=str).replace(
        body["approval"]["notice"], ""
    ), "挂起文案除 `approval.notice` 之外还出现在别的地方"


@pytest.mark.parametrize(
    ("node", "label"),
    [("export", "📋 导出报告"), ("chart", "📈 生成图表")],
)
def test_either_hitl_step_parks_with_a_readable_handle(monkeypatch, tmp_path, node, label):
    """那一窗挂的两枚步骤（导出 ×10、生成图表 ×1）都得交出可批准的东西，不是只有导出。"""
    from langgraph.graph import END, START, StateGraph

    from app.agents import orchestrator
    from app.agents.state import AgentState

    ledger = _pg_ledger(monkeypatch, [{"input_tokens": 5_012, "output_tokens": 640}])
    sink = tmp_path / f"r254-{node}-artifact"
    builder = StateGraph(AgentState)
    builder.add_node(node, orchestrator._make_worker_wrapper(_SinkWorker(sink), node))
    builder.add_edge(node, END)
    builder.add_edge(START, node)
    session = "r254-handle-" + node
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r254-handle-" + node,
        payload={"session_id": session},
        graph=builder.compile(
            checkpointer=_parked_checkpointer(), interrupt_before=[node]
        ),
    )

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    assert body["status"] == "awaiting_approval"
    approval = body["approval"]
    assert approval["pending_steps"] == [node]
    assert approval["labels"] == [label]
    assert approval["session_id"] == session
    assert ledger.calls, "token 读数没去过台账"


def _parked_checkpointer():
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def test_the_approval_handle_points_at_a_route_that_actually_exists(monkeypatch, tmp_path):
    """可寻址：把手里那三格照抄就能批准，不必重发本轮问题，也不必自己猜 session。

    前缀不抄字面：`_poll` 刚刚真真切切走过 `/api/v1/queue/status/...` 那一扇门并读到 200，
    同一个前缀拼上 `chat.router` 在位的 `/approve`（POST）就是把手该指的地方。
    """
    from app.api.v1 import chat

    ctx = _parked_turn(monkeypatch, tmp_path, name="r254-route", session="r254-route-session")

    assert ctx.worker.process_one() is True

    approval = _poll(monkeypatch, ctx)["approval"]
    assert approval["decide_method"] == "POST"
    assert approval["decide_body"] == {"session_id": approval["session_id"], "approved": True}
    routes = {
        (route.path, method)
        for route in chat.router.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert ("/approve", "POST") in routes, "把手指向了一条不存在的门"
    prefix = QUEUE_STATUS_PATH.rsplit("/queue/status/", 1)[0]
    assert approval["decide_path"] == prefix + "/approve"
    assert approval["decide_body"].keys() == {"session_id", "approved"}


def test_the_poll_re_reads_the_ledger_so_a_decision_taken_elsewhere_shows_up(monkeypatch, tmp_path):
    """`ledger_status` 是问出来的，不是抄来的：批准在别处发生之后，再轮询一次就读到 resumed。

    反证：把 `app/api/v1/chat.py::queue_terminal_readout` 里那一行
    `approval["ledger_status"] = approval_ledger_state(...)` 摘掉，第二次轮询仍旧读 awaiting。
    """
    ctx = _parked_turn(monkeypatch, tmp_path, name="r254-flip", session="r254-flip-session")

    assert ctx.worker.process_one() is True

    first = _poll(monkeypatch, ctx)["approval"]
    assert first["ledger_status"] == pending_approvals.AWAITING
    assert pending_approvals.mark_status(first["session_id"], pending_approvals.RESUMED) is not None

    assert _poll(monkeypatch, ctx)["approval"]["ledger_status"] == pending_approvals.RESUMED
    # 队列那一行不改口：这一轮对轮询是终态，对任务不是。
    assert ctx.queue.status(_request_id(ctx)) == "awaiting_approval"


def test_the_parked_turn_still_opens_a_pending_row_for_its_owner(monkeypatch, tmp_path):
    """越权面零变化：待办行的归属仍是载荷里解析出的 user_id，读状态那扇门仍旧只认本人。"""
    session = "r254-owner-session"
    ctx = _parked_turn(monkeypatch, tmp_path, name="r254-owner", session=session)

    assert ctx.worker.process_one() is True

    row = pending_approvals.get_row(session)
    assert row is not None and row.status == pending_approvals.AWAITING
    assert row.owner_user_id == USER_ID
    stranger = _poll_denies(monkeypatch, ctx)
    assert stranger == 403, "别人排在队列里的这一轮被另一个人读走了批准把手"


def _poll_denies(monkeypatch, ctx):
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app as fastapi_app

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: ctx.queue)
    monkeypatch.setattr(
        auth, "get_user", lambda name: {"id": "u-" + name, "username": name, "role": "admin"}
    )
    return TestClient(fastapi_app).get(
        QUEUE_STATUS_PATH + _request_id(ctx),
        headers={"Authorization": "Bearer " + create_token("intruder")},
    ).status_code

# ==================== 判据②：出处要回得到客户端 ====================


def test_the_source_rows_published_by_the_worker_reach_the_queue_readout(monkeypatch, tmp_path):
    """反证：把 `queue.complete(..., terminal=terminal)` 里那份 `sources` 摘掉，读回 0 条。

    09-25 那一窗含 `sources` 的行是 0/20 —— 因为 `queue.complete` 那条腿只存一枚正文字符串，
    `sources` 折进 `aggregate_agent_result` 之后再没回到客户端。
    """
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-sources",
        session="r254-sources-session",
        rows=[{"input_tokens": 1_204, "output_tokens": 118}],
        hits=retriever_hits(),
    )

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    assert body["status"] == "done"
    assert [row["source"] for row in body["sources"]] == [FINANCE_DOC]
    assert body["sources_present"] is True
    assert body["scope_reason_code"], "放行理由没交出来，客户端无从复核这一条为什么能看"
    assert body["sources_error"] == ""


def test_an_authorized_source_row_survives_the_round_trip_through_redis(monkeypatch, tmp_path):
    """redis 那一趟必须把行原样搬回来：取证键一枚不少，且不夹带未放行的行。"""
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-roundtrip",
        session="r254-roundtrip-session",
        rows=[{"input_tokens": 2_048, "output_tokens": 233}],
        hits=retriever_hits(),
    )

    assert ctx.worker.process_one() is True

    published = ctx.queue.terminal(_request_id(ctx))["payload"]["sources"]
    read_back = _poll(monkeypatch, ctx)["sources"]
    assert read_back == published
    row = published[0]
    assert row["worker"] == "doc"
    assert row["source"] == FINANCE_DOC
    assert row["excerpt"], "命中句没跟着回来，出处就只剩一个文件名"
    assert row["permission_checked"] is True


def test_the_source_decision_is_the_same_scope_allows_predicate(monkeypatch, tmp_path):
    """队列道不新增、也不放宽任何一道放行判定：逐行复跑 `scope.allows` 比对。"""
    from app.api.v1 import chat
    from app.rag.filters import resolve_document_retrieval_scope

    principal = finance_principal()
    payload_principal = principal.model_dump()
    scope = resolve_document_retrieval_scope(principal)
    for hit in retriever_hits():
        rows, reason, error = chat.queue_turn_sources(
            {"doc": doc_agent_result([hit])}, payload_principal
        )
        expected = [hit] if scope.allows(hit) else []
        assert error == ""
        assert [row["source"] for row in rows] == [row["source"] for row in expected], (
            f"department={hit['department']} classification={hit['classification']} 的判定"
            "与 scope.allows 不一致"
        )
        assert bool(rows) is bool(expected)
        assert reason or not rows


def test_a_turn_that_retrieved_nothing_reports_zero_instead_of_an_error(monkeypatch, tmp_path):
    """「查到 0 条」是结论：`sources_error` 必须留空，`sources_present` 才是 False。"""
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-zerosource",
        session="r254-zerosource-session",
        rows=[{"input_tokens": 300, "output_tokens": 60}],
        hits=[],
    )

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    assert body["status"] == "done"
    assert body["sources"] == []
    assert body["sources_present"] is False
    assert body["sources_error"] == ""


def test_a_principal_that_cannot_be_restored_says_so_instead_of_reporting_zero(monkeypatch, tmp_path):
    """「压根没查成」与「查到 0 条」是两件事：前者写进 `sources_error`，不许洗成空清单。"""
    from app.api.v1 import chat

    rows, reason, error = chat.queue_turn_sources({"doc": doc_agent_result(retriever_hits())}, None)
    assert (rows, reason, error) == ([], "", "principal_unavailable")

    rows, reason, error = chat.queue_turn_sources({}, {"user_id": "u", "username": "n"})
    assert error == "", error


# ==================== 判据③：token 读数上到客户可读面，值取自真库同源 ====================


def test_the_queue_readout_reports_the_tokens_the_ledger_actually_has(monkeypatch, tmp_path):
    """尺子用的是那一窗的真读数（Σinput 91,271 / Σoutput 18,859），不是现编的数。"""
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-usage",
        session="r254-usage-session",
        rows=_window_rows(),
    )

    assert ctx.worker.process_one() is True

    request_id = _request_id(ctx)
    usage = _poll(monkeypatch, ctx)["usage"]
    assert usage == {
        "prompt_tokens": WINDOW_PROMPT_TOKENS,
        "completion_tokens": WINDOW_COMPLETION_TOKENS,
        "total_tokens": WINDOW_PROMPT_TOKENS + WINDOW_COMPLETION_TOKENS,
        "model_calls": 2,
        "calls_with_token_readout": 2,
        "calls_missing_token_readout": 0,
        "token_readout_complete": True,
        "authoritative": True,
        "ledger": "postgres_model_calls",
    }
    # 同源：读的就是这一轮自己的 request_id，键与谓词一字不改。
    assert ctx.ledger.calls == [
        {"table": "model_calls", "where": "request_id = %s", "request_id": request_id}
    ]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_a_null_token_cell_is_counted_as_missing_not_as_zero(monkeypatch, tmp_path):
    """`model_calls.input_tokens` 允许是 NULL：那一格不折算成 0，也不假装账齐。"""
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-nulltoken",
        session="r254-nulltoken-session",
        rows=[
            {"input_tokens": 1_000, "output_tokens": 200},
            {"input_tokens": None, "output_tokens": None},
        ],
    )

    assert ctx.worker.process_one() is True

    usage = _poll(monkeypatch, ctx)["usage"]
    assert usage["model_calls"] == 2
    assert usage["calls_with_token_readout"] == 1
    assert usage["calls_missing_token_readout"] == 1
    assert usage["token_readout_complete"] is False
    assert usage["prompt_tokens"] == 1_000


def test_an_unreadable_ledger_reads_as_null_and_the_zero_call_gate_stays_ashamed(
    monkeypatch, tmp_path
):
    """台账读不到 ⇒ 四格 null（不是 0），而零调用闸不许借此杀人，也不许借此过关。

    反证：把 `app/api/v1/chat.py::read_model_call_usage` 里 `rows is None` 那一支退化成空
    列表，这一枚会红在 null 上，判据④的用例则会被一台连不上库的机器误杀。
    """
    broken = _broken_ledger(monkeypatch)
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r254-brokenledger",
        payload={"session_id": "r254-brokenledger-session"},
        stream=_FakeStream([_state(BACKGROUND_ANSWER)]),
    )

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    assert body["status"] == "done", "读不到台账不等于一次模型都没打"
    usage = body["usage"]
    assert broken.calls == 1
    assert usage["model_calls"] is None
    assert usage["prompt_tokens"] is None
    assert usage["total_tokens"] is None
    assert usage["authoritative"] is False
    assert usage["ledger"] == "ledger_unavailable"


def test_the_side_ledger_is_filtered_down_to_this_turn_and_is_never_authoritative(
    monkeypatch, tmp_path
):
    """只有一台机器看得见的那本账：照数，但 `authoritative` 一律 false，且只数本轮的行。

    两件事一起钉：
    · 别的 request_id 的行一枚都不许折进来——侧账这一腿的过滤写在被测代码里，不是 SQL 谓词；
    · 侧账读数永远不带 authoritative，判据④的闸因此不会拿它当证明。
    """
    rows = _side_ledger(monkeypatch)
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r254-sideledger",
        payload={"session_id": "r254-sideledger-session"},
        stream=_FakeStream([_state(BACKGROUND_ANSWER)]),
    )
    rows.extend(
        [
            {"request_id": "someone-elses-turn", "input_tokens": 9_000, "output_tokens": 9_000},
            {"request_id": _request_id(ctx), "input_tokens": 120, "output_tokens": 30},
        ]
    )

    assert ctx.worker.process_one() is True

    usage = _poll(monkeypatch, ctx)["usage"]
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["total_tokens"] == 150
    assert usage["model_calls"] == 1
    assert usage["authoritative"] is False
    assert usage["ledger"] == "persistence_model_calls"


def test_credentials_never_ride_the_usage_readout(monkeypatch, tmp_path, caplog):
    """台账连不上时只落异常类名：连接失败的文案里带着主机与账号。"""
    _broken_ledger(monkeypatch)
    with caplog.at_level("WARNING"):
        _answered_probe(monkeypatch)
    assert "hunter2" not in caplog.text
    assert "db.internal" not in caplog.text


def _answered_probe(monkeypatch):
    from app.api.v1 import chat

    return chat.read_model_call_usage("req-r254-probe")

# ==================== 判据④：零枚模型调用的一轮没有资格叫 done ====================


def test_a_run_that_never_called_a_model_cannot_land_done(monkeypatch, tmp_path):
    """真库说这一轮一枚 `model_calls` 都没有 ⇒ 队列不落 done，正文一个字节都不发布。

    09-25 那一窗的原案：request_id `64c3ef3b49174fc4b03994af7b0364a6`（题面「把上面那张图表
    插进正文」，tool 档）在 `model_calls` 里一枚都没有，worker 记 `status=partial
    awaiting_hitl=True`，队列侧仍 `final=done`。与 R37 立的「谎报终态」同形状，只是换了条道。
    """
    ctx = _answered_turn(
        monkeypatch, tmp_path, name="r254-zerocalls", session="r254-zerocalls-session", rows=[]
    )

    assert ctx.worker.process_one() is True

    request_id = _request_id(ctx)
    assert ctx.queue.status(request_id) == "queued"
    assert ctx.queue.result(request_id) is None
    assert ctx.queue.terminal(request_id) == {"state": "absent", "payload": None}
    failure = ctx.queue.failure(request_id)
    assert failure["last_error"] == queue_worker.NO_MODEL_CALL_READOUT
    assert failure["attempts"] == 1, "闸自己不该多烧一枚重试名额"


def test_the_zero_call_verdict_does_not_declare_the_task_over(monkeypatch, tmp_path):
    """队列层没资格替契约宣布终局：名额用完才 dead，而 dead 那一支仍旧补历史一句话。

    反证：给 `queue.fail_or_retry(request_id, NO_MODEL_CALL_READOUT)` 加上 `retryable=False`，
    第一枚断言立刻红在 dead 上——那一枚是「账本暂时没读到」也能走到的出口，会把可救的一轮
    判死。
    """
    ctx = _answered_turn(
        monkeypatch,
        tmp_path,
        name="r254-zerocalls-dead",
        session="r254-zerocalls-dead-session",
        rows=[],
        max_attempts=1,
    )

    assert ctx.worker.process_one() is True

    request_id = _request_id(ctx)
    assert ctx.queue.status(request_id) == "dead"
    assert ctx.queue.failure(request_id)["last_error"] == queue_worker.NO_MODEL_CALL_READOUT
    assert [entry[1:] for entry in ctx.history] == [
        ("assistant", queue_worker.REPORT_TURN_FAILURE_TEXT)
    ], "落到 dead 也不许在会话里留一句没人回答的问话"


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({"authoritative": True, "model_calls": 0}, True),
        ({"authoritative": True, "model_calls": 1}, False),
        ({"authoritative": False, "model_calls": 0}, False),
        ({"authoritative": False, "model_calls": None}, False),
        ({"model_calls": 0}, False),
        (None, False),
        ({}, False),
    ],
)
def test_only_an_authoritative_zero_proves_no_model_was_called(usage, expected):
    """「没读到」与「读到零」分得开：只有 authoritative 台账里那枚 0 才算证明。"""
    from app.api.v1 import chat

    assert chat.usage_proves_zero_model_calls(usage) is expected


# ==================== 判据⑥：三枚假终态各有一枚参数化用例 ====================


@pytest.mark.parametrize(
    "shape",
    [
        "done_without_a_body",
        "done_without_sources",
        "done_without_a_single_model_call",
    ],
)
def test_the_three_false_terminals_are_readable_as_what_they_are(monkeypatch, tmp_path, shape):
    """09-25 量红的三枚「final=done 而其实没有」，今天每一枚都自报家门。

    共同的不可能形状（三枚一起参数化，是因为它们共享同一条契约）：状态词说 `done` 而载荷
    说这一轮没有正文。挂起文案冒充正文那一枚也在这一条上被拦住——那一轮的 `result` 是 null。
    """
    name = "r254-false-" + shape
    session = name + "-session"
    if shape == "done_without_a_body":
        ctx = _parked_turn(monkeypatch, tmp_path, name=name, session=session)
    else:
        ctx = _answered_turn(
            monkeypatch,
            tmp_path,
            name=name,
            session=session,
            rows=[] if shape.endswith("model_call") else [{"input_tokens": 40, "output_tokens": 8}],
            hits=[] if shape == "done_without_sources" else None,
        )

    assert ctx.worker.process_one() is True

    body = _poll(monkeypatch, ctx)
    state = body.get("terminal_state", "")
    assert body["status"] != "done" or (state == "answered" and body["answer_present"] is True), (
        f"shape={shape}：状态说 done 而载荷说这一轮没交正文"
    )
    assert body.get("result") != PARK_EXPORT
    if shape == "done_without_a_body":
        assert (body["status"], state, body["result"]) == (
            "awaiting_approval",
            "awaiting_approval",
            None,
        )
        assert body["approval"] is not None
    if shape == "done_without_sources":
        assert (body["status"], state) == ("done", "answered")
        assert (body["sources_present"], body["sources"], body["sources_error"]) == (
            False,
            [],
            "",
        )
    if shape == "done_without_a_single_model_call":
        # 压根没发布的一轮不许有终态读数，但必须说清为什么没发布。
        assert body["status"] == "queued", "零枚模型调用的一轮落到了 " + str(body["status"])
        assert "terminal_state" not in body and "result" not in body
        assert body["failure"]["last_error"] == queue_worker.NO_MODEL_CALL_READOUT


# ==================== 存量队列行：读得回来，且明说自己说不出 ====================


def test_a_row_published_before_this_change_still_reads_back(monkeypatch, tmp_path):
    """今天 redis 里在位的 3 枚旧行不许在升级之后炸量具：`complete(rid, text)` 两枚参数照旧。"""
    queue = ReliableQueue(FakeRedis(), name="r254-legacy", lease_seconds=30)
    message = queue.enqueue(
        {"message": "旧的一轮", "principal": {"user_id": USER_ID, "username": USERNAME}},
        "r254-legacy-idem",
    )
    queue.reserve()
    assert queue.complete(message.request_id, "旧行正文") is True

    ctx = SimpleNamespace(queue=queue, message=message)
    body = _poll(monkeypatch, ctx)
    assert body["status"] == "done"
    assert body["result"] == "旧行正文"
    assert body["terminal_schema"] == "legacy"
    assert body["terminal_state"] == "legacy_row"
    assert body["usage"] is None, "旧行没有终态载荷，拿零去填就是替它编一本账"
    assert body["sources"] == [] and body["sources_present"] is False
    assert body["approval"] is None
    assert body["terminal_note"]


def test_a_legacy_row_whose_body_is_the_park_notice_is_recognised(monkeypatch, tmp_path):
    """旧行里那 11 枚把挂起文案当正文的：文案照样能认出来，不必等人翻日志。

    认出来之后两格并存：`answer_present` 说的是「那一格里确实有一句字」（这一格旧行说不出
    更多，所以照字面报），`answer_is_park_notice` 说的是「那句字不是正文」。
    """
    from app.api.v1 import chat

    queue = ReliableQueue(FakeRedis(), name="r254-legacy-park", lease_seconds=30)
    message = queue.enqueue(
        {"message": "旧的一轮", "principal": {"user_id": USER_ID, "username": USERNAME}},
        "r254-legacy-park-idem",
    )
    queue.reserve()
    queue.complete(message.request_id, PARK_EXPORT)

    body = _poll(monkeypatch, SimpleNamespace(queue=queue, message=message))
    assert body["answer_is_park_notice"] is True
    assert body["answer_present"] is True, "旧行只读得出「有没有一句字」，不许改口"
    assert chat.is_hitl_park_notice(PARK_EXPORT) is True
    assert chat.is_hitl_park_notice(BACKGROUND_ANSWER) is False
    assert chat.is_hitl_park_notice("本轮在「导出报告」前等待你确认") is False


def test_a_terminal_key_that_will_not_parse_is_reported_as_corruption(monkeypatch, tmp_path):
    """「没有这一格」与「这一格解不开」是两枚诊断，混了就等于把损坏说成兼容。"""
    queue = ReliableQueue(FakeRedis(), name="r254-corrupt", lease_seconds=30)
    message = queue.enqueue(
        {"message": "坏掉的一轮", "principal": {"user_id": USER_ID, "username": USERNAME}},
        "r254-corrupt-idem",
    )
    queue.reserve()
    queue.complete(message.request_id, "正文还在")
    queue.redis.set(queue._terminal_key(message.request_id), '{"terminal_state": ')

    body = _poll(monkeypatch, SimpleNamespace(queue=queue, message=message))
    assert body["terminal_schema"] == "unreadable"
    assert body["terminal_state"] == "unreadable_terminal"
    assert body["result"] == "正文还在"
    assert body["usage"] is None
    assert queue.terminal(message.request_id)["state"] == "unreadable"


def test_a_discarded_turn_takes_the_terminal_payload_with_it(monkeypatch, tmp_path):
    """正文与读数同生同死：丢弃的一轮不许留下「正文没了、读数还在」。"""
    queue = ReliableQueue(FakeRedis(), name="r254-discard", lease_seconds=30)
    message = queue.enqueue(
        {"message": "要丢弃的一轮", "principal": {"user_id": USER_ID, "username": USERNAME}},
        "r254-discard-idem",
    )
    queue.reserve()
    terminal = _terminal(answered=True)
    assert queue.complete(message.request_id, "正文", terminal=terminal) is True
    assert queue.terminal(message.request_id)["state"] == "ok"

    queue.cancel(message.request_id)
    assert queue.complete(message.request_id, "正文", terminal=terminal) is False

    assert queue.result(message.request_id) is None
    assert queue.terminal(message.request_id) == {"state": "absent", "payload": None}


def _terminal(*, answered: bool):
    from app.api.v1 import chat

    state = chat.TERMINAL_STATE_ANSWERED if answered else chat.TERMINAL_STATE_AWAITING_APPROVAL
    return chat.build_queue_terminal(
        terminal_state=state,
        answer_present=answered,
        usage=None,
        approval=None if answered else {"session_id": "s", "pending_steps": ["export"]},
    )

# ==================== 队列层：不许静默降级，也不许第二份词表 ====================


@pytest.mark.parametrize("state", ["done", "answered ", "", "no_answer", None, 0])
def test_the_queue_refuses_a_terminal_state_it_does_not_know(state):
    """认得两枚，第三枚当场 raise：载荷说在等人、状态说已跑完这种自相矛盾就是这么挡的。"""
    queue = ReliableQueue(FakeRedis(), name="r254-refuse", lease_seconds=30)
    message = queue.enqueue(
        {"message": "异形终态", "principal": {"user_id": USER_ID, "username": USERNAME}},
        "r254-refuse-" + str(state),
    )
    queue.reserve()

    with pytest.raises(ValueError):
        queue.complete(message.request_id, "正文", terminal={"terminal_state": state})

    assert queue.status(message.request_id) == "processing"
    assert queue.result(message.request_id) is None


def test_the_terminal_builder_only_hands_out_the_two_states_a_queue_can_carry():
    """构造点与落库点之间不存在第二份词表：`no_answer` 是同步道的读数，进不了队列。"""
    from app.api.v1 import chat

    for state in (chat.TERMINAL_STATE_ANSWERED, chat.TERMINAL_STATE_AWAITING_APPROVAL):
        payload = chat.build_queue_terminal(terminal_state=state, answer_present=True)
        assert payload["schema"] == reliable_queue.TERMINAL_SCHEMA
    for state in (
        chat.TERMINAL_STATE_NO_ANSWER,
        chat.TERMINAL_STATE_QUEUED,
        chat.TERMINAL_STATE_LEGACY,
        "",
    ):
        with pytest.raises(ValueError):
            chat.build_queue_terminal(terminal_state=state, answer_present=False)


def test_the_status_word_is_derived_from_the_payload_not_supplied_alongside_it():
    """`complete()` 的签名里没有第二枚状态参数：两枚各填各的才会造出谎报。"""
    import inspect

    from app.common.reliable_queue import ReliableQueue as _Queue

    params = list(inspect.signature(_Queue.complete).parameters)
    assert params == ["self", "request_id", "result", "terminal"]
    assert inspect.signature(_Queue.complete).parameters["result"].annotation is not None


def test_every_publish_site_in_the_worker_carries_a_terminal():
    """三条发布腿一条不许漏：`queue.complete(...)` 每一处都带着终态载荷。

    反证：把 `deploy/queue_worker.py` 老腿那一处 `terminal=terminal` 摘掉，本枚先红。
    """
    from pathlib import Path

    text = Path("deploy/queue_worker.py").read_text(encoding="utf-8")
    sites = re.findall(r"queue\.complete\(([^)]*)\)", text)
    assert len(sites) == 3, sites
    assert all("terminal=" in site for site in sites), sites


def test_the_parked_notice_is_still_constructed_from_the_shared_builder():
    """那句话说它该说的地方（`approval.notice` 与会话历史），一个字都不许多，也不许换字。"""
    from app.api.v1 import chat

    assert chat.hitl_park_text({"labels": ["📋 导出报告"]}) == PARK_EXPORT
    assert chat.is_hitl_park_notice(PARK_EXPORT) is True


def test_the_new_status_word_is_written_as_a_literal_at_exactly_one_site():
    """R232 的 AST 只认「往 status 键写字面量」这一种形状：写成常量会落进它的 blind spot。"""
    from pathlib import Path

    text = Path("app/common/reliable_queue.py").read_text(encoding="utf-8")
    assert text.count('_status_key(request_id), "awaiting_approval"') == 1
    assert "TERMINAL_STATE_TO_STATUS" in text
