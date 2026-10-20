"""R294 · 排队载荷不许把身份（连部门一起）冻结在入队时刻。

病灶（跟进单 §101.15 · R294）：入队侧 `app/api/v1/chat.py:2132` 把整份
`principal.model_dump(mode="json")` 冻进队列载荷，`deploy/queue_worker.py` 三处用
`payload.get("principal")` 还原，`app/agents/tools.py:53` 再把它当权威身份。后果是
R290（`PUT /users/department`）的成果在后台跑的那一轮里直接失效——人换了部门，队列里
那一轮仍拿旧部门跑检索面。

唯一不变量：**消费时刻的作用域，必须与此刻重新发一个请求逐字相等。** 方向只许两个：
收缩到当前身份，或判失效。本单取"漂移即判失效"，因为换部门是一次新的授权决定，该由
用户重发那一轮来做，不该由队列替他决定。绝不允许的是第三种：按旧快照跑完再交差。

判据 → 用例

① 换部门之后已在队列里的那一轮     test_a_department_move_after_enqueue_... 等五枚
② 两条路径的 Principal 逐字段相等   test_the_identity_at_consumption_...[report|legacy] 等四枚
③ 权限只准收缩不准放大、篡改判失效  test_a_payload_rewritten_to_... 三枚 + 一枚量越权面
④ 旧载荷不崩、不猜默认值、不跑全库  test_a_legacy_payload_... / test_the_memory_... 等七枚
⑤ 反证 ≥4（逐条对 ①②③④）          test_counter_evidence_... 五枚
⑥ 无 skip / xfail / 删件；本单未改口任何一枚既有件

载荷形状一格未动（`test_the_enqueued_payload_shape_is_unchanged` 钉着），所以
`tests/test_r37_report_lane_enqueue.py:287` 与 `tests/test_r32_lane_contract.py` 那两组
逐字段钉原样绿。

全程离线：FakeRedis + 假图 + 进程内假用户表（只换 `auth.get_user` 与
`auth.user_storage_state` 两枚现成读点），一根 socket 都不开、一发模型都不打。
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents import tools
from app.agents.contracts import AgentResult, Principal
from app.common import auth
from app.common.reliable_queue import ReliableQueue
from app.rag import filters
from deploy import queue_worker
from tests.test_r37_report_lane_worker import FakeRedis, _FakeStream, _state

REPO = Path(__file__).resolve().parents[1]
WORKER_SOURCE = REPO / "deploy" / "queue_worker.py"
TOOLS_SOURCE = REPO / "app" / "agents" / "tools.py"

SESSION = "r294-session"
USERNAME = "r294-staff"
FINANCE = "finance"
RESEARCH = "research"
MESSAGE = "把本部门上季度的报销情况整理成一页纸"
ANSWER = "后台跑完的结论"
IDEM = "r294-idempotency-key"

#: 一张跨部门 × 跨密级的对照表：判据③要数"越权面几条"，得先有一张可数的面。
#: staff 的密级档位是 1（`app/common/rbac.py:31`），所以普通账号本行只该看见一枚。
CORPUS = (
    {"classification": 1, "department": FINANCE},
    {"classification": 2, "department": FINANCE},
    {"classification": 3, "department": FINANCE},
    {"classification": 1, "department": RESEARCH},
    {"classification": 2, "department": RESEARCH},
    {"classification": 3, "department": RESEARCH},
)


# ==================== 夹具 ====================


class _UserStore:
    """进程内假用户表。生产形态下它是跨进程共享的 PG `users`，用例就是那只中途挪人的手。

    刻意只回 `app/common/auth.py:582-593` 今天真回的三列（username/role/department）：
    多回一列就是替生产侧造一条 `Principal.from_user` 读不到的通路，那一路得到的身份与
    "此刻新发一个请求"拿到的不再同源，判据②的逐字相等会退化成自说自话。
    """

    def __init__(self, row, storage_mode="postgres"):
        self.rows = {row["username"]: dict(row)}
        self.storage_mode = storage_mode
        self.lookups = []

    def get_user(self, username):
        self.lookups.append(username)
        row = self.rows.get(username)
        return dict(row) if row else None

    def user_storage_state(self):
        durable = self.storage_mode == "postgres"
        return {
            "storage_mode": self.storage_mode,
            "durable": durable,
            "shared_across_processes": durable,
            "protection": "none" if durable else "refuse_start",
            "detail": "r294 fixture",
        }

    def move_department(self, username, department):
        """R290 那枚端点在产品侧做的事，这里就是那一格。"""
        self.rows[username]["department"] = department

    def promote(self, username, role):
        self.rows[username]["role"] = role

    def drop(self, username):
        del self.rows[username]


def _row(**overrides):
    row = {"username": USERNAME, "role": "staff", "department": FINANCE}
    row.update(overrides)
    return row


def _row_principal(**overrides):
    """一份"刚从用户库里读出来的行"投影成身份：与 `Principal.from_user` 同一个构造。"""
    return Principal.from_user(_row(**overrides))


def _fresh_request_principal(store):
    """"此刻重新发一个请求"拿到的身份：逐字照 `app/main.py:277-283` 那三行。"""
    return Principal.from_user(store.get_user(USERNAME))


def _surface(subject):
    """把"某一份身份能看见几行"量成可比较的形状。闸门拒 = 空面——判据③可数的那一半。"""
    principal = subject if isinstance(subject, Principal) else Principal.model_validate(subject)
    try:
        scope = filters.resolve_document_retrieval_scope(principal)
    except filters.RetrievalScopeError:
        return frozenset()
    return frozenset(scope.reason_code + ":" + json.dumps(row, sort_keys=True) for row in CORPUS if scope.allows(row))


def _stored(queue, request_id):
    """读队列里真实躺着的那一行（走的是 JSON 往返，不是内存对象）。"""
    raw = queue.redis.get(queue._message_key(request_id))
    body = json.loads(raw)
    return body, body["payload"]


def _rewrite_stored(queue, request_id, mutate):
    """替用例改写躺在队列里的那一行：模拟有人在 worker 取走之前动了这张单子。"""
    body, payload = _stored(queue, request_id)
    mutate(payload)
    queue.redis.set(
        queue._message_key(request_id),
        json.dumps(body, ensure_ascii=False, separators=(",", ":")),
    )


def _request_id(queue):
    raw = queue.redis.get(queue._idempotency_key(IDEM))
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def _enqueue(monkeypatch, queue, principal, *, lane):
    """走真入队口收单：载荷由 `chat._enqueue_ask_turn` 自己构造，本件不抄第二份。"""
    from app.api.v1 import chat
    from app.common import reliable_queue

    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", lambda: queue)
    http_request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(principal=principal, username=principal.username),
    )
    chat._enqueue_ask_turn(
        request=SimpleNamespace(idempotency_key=IDEM),
        http_request=http_request,
        thread_id=SESSION,
        rewritten_msg=MESSAGE,
        username=principal.username,
        principal=principal,
        lane=lane,
    )


def _ok_record():
    return AgentResult.model_validate(
        {
            "worker": "orchestrator",
            "status": "success",
            "answer": ANSWER,
            "request_id": "req-r294",
            "trace_id": "trace-r294",
            "task_id": "task-r294",
            "error": None,
        }
    )


def _install(monkeypatch, tmp_path, *, lane="report", storage_mode="postgres", row=None):
    """入队（真口）与消费（假图）两头的机器都摆好，用例只管挪中间那只手。"""
    from app.agents import orchestrator
    from app.api.v1 import chat
    from app.trace.store import TraceStore

    store = _UserStore(row or _row(), storage_mode=storage_mode)
    monkeypatch.setattr(auth, "get_user", store.get_user)
    monkeypatch.setattr(auth, "user_storage_state", store.user_storage_state)
    # 闸门在没有部门时会替拒绝落一行账（`app/rag/filters.py:83-91`）。本件的可见性对照是
    # 纯读数，不该往审计通路上写东西：换成一只记录器，判定本体一个字不改。
    refusals = []
    monkeypatch.setattr(
        filters,
        "_record_refusal",
        lambda principal, code: refusals.append((getattr(principal, "username", ""), code)),
    )

    queue = ReliableQueue(FakeRedis(), name="r294-" + (lane or "legacy"), lease_seconds=30)
    _enqueue(monkeypatch, queue, Principal.from_user(store.get_user(USERNAME)), lane=lane)

    stream = _FakeStream([_state(ANSWER)])
    graphs = []

    def fake_run(user_message, thread_id="default", user=None):
        graphs.append(user)
        return _ok_record()

    recorded, history = [], []
    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        queue_worker, "record_agent_result", lambda rec, **kw: recorded.append(rec)
    )
    monkeypatch.setattr(orchestrator, "run_with_stream", stream)
    monkeypatch.setattr(orchestrator, "run_orchestrator_result", fake_run)
    monkeypatch.setattr(orchestrator, "_trace_store", TraceStore(tmp_path / "traces.jsonl"))
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)
    monkeypatch.setattr(
        chat, "_save_message", lambda *args, **kw: history.append(tuple(args))
    )

    return SimpleNamespace(
        store=store,
        queue=queue,
        request_id=_request_id(queue),
        stream=stream,
        graphs=graphs,
        recorded=recorded,
        history=history,
        refusals=refusals,
        lookups_at_enqueue=len(store.lookups),
        worker=queue_worker,
    )


def _handed_to_graph(ctx):
    """两条腿里真交给图的那一份身份投影，连同它的出处签名。"""
    user = None
    if ctx.stream.calls:
        user = ctx.stream.calls[-1]["user"]
    elif ctx.graphs:
        user = ctx.graphs[-1]
    assert user is not None, "这一轮压根没进图"
    return user["principal"], user.get(queue_worker.PRINCIPAL_PROVENANCE_KEY)


def _ran(ctx):
    return bool(ctx.stream.calls) or bool(ctx.graphs)


def _outcome(ctx):
    failure = ctx.queue.failure(ctx.request_id)
    return {
        "status": ctx.queue.status(ctx.request_id),
        "last_error": failure["last_error"],
        "attempts": failure["attempts"],
        "result": ctx.queue.result(ctx.request_id),
        "ran": _ran(ctx),
        "recorded": len(ctx.recorded),
        "history": list(ctx.history),
        "re-lookups": len(ctx.store.lookups) - ctx.lookups_at_enqueue,
    }


def _as_if_before_fix(monkeypatch):
    """把消费侧退回改前那一版：载荷快照就是权威身份（反证钉的靶子）。"""

    def _before_fix(payload):
        snapshot = payload.get("principal")
        return (
            snapshot if isinstance(snapshot, dict) else {},
            queue_worker.CONSUMPTION_PRINCIPAL_PROVENANCE,
            "",
        )

    monkeypatch.setattr(queue_worker, "resolve_consumption_principal", _before_fix)


# ==================== 判据①：换部门之后那一轮，要么生效、要么判失效 ====================


def test_a_department_move_after_enqueue_invalidates_the_queued_turn(monkeypatch, tmp_path):
    """判据①正题：入队之后、消费之前换了部门 ⇒ 这一轮判失效，一个字都不跑。

    这一格就是 R290 的成果今天丢掉的地方。允许的两个方向里本单选"判失效"：换部门是一次
    新的授权决定，该由用户重发那一轮来做。"入队后改部门、消费前生效"这一时序正是靶心。
    """
    ctx = _install(monkeypatch, tmp_path, lane="report")
    ctx.store.move_department(USERNAME, RESEARCH)
    assert _surface(_row_principal(department=FINANCE)) != _surface(
        _row_principal(department=RESEARCH)
    ), (
        "对照表要让部门这一维真的改变可见面，否则本枚钉是空的"
    )

    assert ctx.worker.process_one() is True

    outcome = _outcome(ctx)
    assert outcome["status"] == "dead"
    assert outcome["last_error"] == queue_worker.IDENTITY_STALE
    assert outcome["ran"] is False, "判失效的这一轮不许有一个模型被打"
    assert outcome["result"] is None, "判失效的这一轮没有资格留下答案"
    assert outcome["recorded"] == 0, "一条 trace 记账都不许留下，更不许记成谁的新成果"
    assert outcome["re-lookups"] == 1, "消费时刻真的向用户库现取过一次，而不是读了快照"
    # 会话历史里不许留一句没人回答的问话（R37 判据③④的口径），但交回的必须是
    # "未产出结论"那一句，不是答案，也不是按旧部门跑出来的东西。
    assert outcome["history"] == [(SESSION, "assistant", queue_worker.REPORT_TURN_FAILURE_TEXT)]


def test_a_department_move_before_enqueue_runs_and_the_old_scope_is_gone(monkeypatch, tmp_path):
    """判据①的另一半：入队之前就已经换完部门 ⇒ 照跑，跑的是新部门。

    钉这一格是为了说清"判失效"不是把队列道打死：漂移比对只在快照与现取不一致时咬人。
    """
    ctx = _install(monkeypatch, tmp_path, lane="report", row=_row(department=RESEARCH))

    assert ctx.worker.process_one() is True

    projection, _provenance = _handed_to_graph(ctx)
    assert projection["department"] == RESEARCH
    assert _outcome(ctx)["status"] == "done"
    assert _surface(projection) == _surface(_fresh_request_principal(ctx.store))


def test_a_role_move_between_enqueue_and_consumption_is_invalidated(monkeypatch, tmp_path):
    """判据①不止部门：角色一动，密级/权限/roles 同时漂移，同样判失效。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    ctx.store.promote(USERNAME, "admin")

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "dead"
    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False


def test_a_deleted_account_between_enqueue_and_consumption_is_invalidated(monkeypatch, tmp_path):
    """判据①：人被从用户库里摘掉，队列里那一轮也判失效——按快照跑完就是给一个此刻无权
    存在的人记成果。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    ctx.store.drop(USERNAME)

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "dead"
    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False


@pytest.mark.parametrize("lane", ["report", ""])
def test_both_queue_legs_go_through_the_same_identity_gate(monkeypatch, tmp_path, lane):
    """判据①覆盖面：报告档与超限那条老腿共用同一道闸，谁都不许从载荷里拿身份。"""
    ctx = _install(monkeypatch, tmp_path, lane=lane)
    ctx.store.move_department(USERNAME, RESEARCH)

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False


# ==================== 判据②：消费时刻的作用域与"此刻新发一个请求"逐字相等 ====================


@pytest.mark.parametrize("lane", ["report", ""])
def test_the_identity_at_consumption_is_field_for_field_what_a_fresh_request_gets(
    monkeypatch, tmp_path, lane
):
    """判据②：同一身份两条路径拿到的 Principal **全部字段**逐个相等，不是只比部门。

    字段清单从模型现取（`Principal.model_fields`），所以往模型里加一格而漏比，这里立刻红。
    """
    ctx = _install(monkeypatch, tmp_path, lane=lane)

    assert ctx.worker.process_one() is True

    projection, provenance = _handed_to_graph(ctx)
    dumped = _fresh_request_principal(ctx.store).model_dump(mode="json")

    assert set(projection) == set(dumped), "两条路径的字段集不再相等"
    for field in Principal.model_fields:
        assert projection[field] == dumped[field], f"字段 {field} 两道路径读出不一致"
    assert provenance == queue_worker.CONSUMPTION_PRINCIPAL_PROVENANCE
    assert Principal.model_validate(projection) == _fresh_request_principal(ctx.store)
    assert _surface(projection) == _surface(dumped)


def test_the_frozen_snapshot_alone_cannot_open_the_tool_boundary(monkeypatch, tmp_path):
    """判据②的另一半：`app/agents/tools.py` 那一族不再把"一份 dict"当身份。

    在场请求交的是 `Principal` 对象（不签也认），后台交的是消费时刻的投影（必须带签名）。
    一张从队列里捞出来的快照想直接当身份 = 拒。
    """
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    snapshot = dict(payload["principal"])

    with pytest.raises(PermissionError) as caught:
        tools._tool_principal({"configurable": {"principal": snapshot}})
    assert "authorization_required" in str(caught.value)

    fresh = _fresh_request_principal(ctx.store)
    assert tools._tool_principal({"configurable": {"principal": fresh}}) is fresh
    resolved = tools._tool_principal(
        {
            "configurable": {
                "principal": snapshot,
                tools.PRINCIPAL_PROVENANCE_KEY: tools.CONSUMPTION_PRINCIPAL_PROVENANCE,
            }
        }
    )
    assert resolved.model_dump(mode="json") == fresh.model_dump(mode="json")


def test_the_two_paths_present_the_same_principal_at_the_tool_boundary(monkeypatch, tmp_path):
    """判据②最字面的那一读：同一身份，在场道与后台道在工具闸门口拿到的东西全等。

    在场道交给图的是 `Principal` 对象（`app/api/v1/chat.py:2242-2244` 加
    `_agent_user_context`），后台道交的是带签名的消费时刻投影。两条路各自过一遍
    `tools._tool_principal` 与 `tools._tool_context`，字段集与字段值都必须相等——
    这才叫"与此刻重新发一个请求逐字相等"，只比 department 一维不算。
    """
    from app.api.v1 import chat

    ctx = _install(monkeypatch, tmp_path, lane="report")

    assert ctx.worker.process_one() is True

    projection, provenance = _handed_to_graph(ctx)
    fresh = _fresh_request_principal(ctx.store)
    background = {
        "principal": projection,
        queue_worker.PRINCIPAL_PROVENANCE_KEY: provenance,
    }
    in_place = chat._agent_user_context(fresh)
    assert in_place is not None

    left = tools._tool_principal({"configurable": dict(in_place)})
    right = tools._tool_principal({"configurable": dict(background)})
    assert left == right == fresh
    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    left_view = tools._tool_context({"configurable": dict(in_place)})
    right_view = tools._tool_context({"configurable": dict(background)})
    assert set(left_view) == set(right_view) == {
        "username",
        "role",
        "department",
        "permissions",
        "clearance",
    }
    assert left_view == right_view, right_view
    assert _surface(left) == _surface(right)


def test_the_provenance_name_has_one_source_of_truth():
    """与 `REPORT_LANE` 同一条纪律：两侧各声明一次的字符串，取值必须逐字相等。"""
    assert tools.PRINCIPAL_PROVENANCE_KEY == queue_worker.PRINCIPAL_PROVENANCE_KEY
    assert tools.CONSUMPTION_PRINCIPAL_PROVENANCE == queue_worker.CONSUMPTION_PRINCIPAL_PROVENANCE


def test_the_enqueued_payload_shape_is_unchanged(monkeypatch, tmp_path):
    """载荷形状一格未动：入队侧仍然交整份快照，但它的身份已经降级成"证据"。

    钉这一格是为了让下一读代码的人明白：R294 没往载荷里塞新字段，所以判据④里
    "没有新字段的载荷"说的就是**每一条在途载荷**，而不是一小部分。
    """
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)

    assert set(payload) == {
        "task_type",
        "message",
        "session_id",
        "username",
        "principal",
        "lane",
        "write_back_session",
    }
    assert set(payload["principal"]) == set(Principal.model_fields)
    assert payload["principal"]["department"] == FINANCE


# ==================== 判据③：权限只准收缩不准放大 ====================


def test_a_payload_rewritten_to_a_higher_clearance_is_invalidated(monkeypatch, tmp_path):
    """反证对象（判据③点名）：载荷被篡改成更高密级 ⇒ 判失效，不是"照更高密级跑"。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    widened = dict(payload["principal"], clearance=3, clearance_label="admin")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": widened}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "dead"
    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False, "篡改过的载荷连一次模型都不该骗到"


def test_a_payload_rewritten_to_another_department_is_invalidated(monkeypatch, tmp_path):
    """判据③：换个部门（不是更高，只是不同）同样判失效——那一轮的题面不属于这个范围。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    moved = dict(payload["principal"], department=RESEARCH)
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": moved}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False


def test_a_payload_rewritten_to_another_owner_id_is_invalidated(monkeypatch, tmp_path):
    """判据③：把单子的归属人改成别人 ⇒ 判失效。这是"按旧账跑完再记成新身份的成果"
    最直白的一种写法。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    stolen = dict(payload["principal"], user_id="u-somebody-else")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": stolen}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False
    assert _outcome(ctx)["recorded"] == 0


def test_the_cross_scope_surface_stays_at_zero(monkeypatch, tmp_path):
    """判据③可数的那一半：交付的身份看见的行与此刻新发一个请求看见的同一批；
    篡改那三枚想拿到的宽面，一条都没到手。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    baseline = _surface(_fresh_request_principal(ctx.store))
    _body, payload = _stored(ctx.queue, ctx.request_id)
    widened = dict(payload["principal"], department=RESEARCH, clearance=3, clearance_label="admin")

    assert len(baseline) == 1, "对照表要先可信：staff 只看得见本部门最低档那一枚"
    assert len(_surface(widened)) > len(baseline), "面没有变宽，反证就无从谈起"

    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": widened}))
    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["ran"] is False, "越权面一条都不该被交付"
    assert not _ran(ctx)


# ==================== 判据④：队列里已经在位的旧载荷 ====================


def test_a_legacy_payload_without_scope_fields_is_invalidated_not_defaulted(monkeypatch, tmp_path):
    """判据④（最容易漏的那一枚）：旧载荷只带 `user_id/username/roles`——本仓队列测试里
    最常见的真实形状。消费时既不 500，也不许拿默认值补一格"无部门低密级"地跑。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    legacy = {"user_id": USERNAME, "username": USERNAME, "roles": ["staff"]}
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": legacy}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "dead"
    assert _outcome(ctx)["last_error"] == queue_worker.IDENTITY_STALE
    assert _outcome(ctx)["ran"] is False


def test_a_legacy_payload_that_still_matches_the_store_runs_as_usual(monkeypatch, tmp_path):
    """判据④的另一头：旧载荷不是"坏了"，只是"没带新字段"——本单没加新字段，所以每一条
    在途载荷都该照常跑得动，只要现取结果与它一致。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    legacy = {
        key: payload["principal"][key]
        for key in queue_worker.PRINCIPAL_SCOPE_FIELDS
    }
    assert "request_id" not in legacy and "auth_source" not in legacy
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": legacy}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "done"
    assert _handed_to_graph(ctx)[0]["department"] == FINANCE


def test_a_payload_without_a_principal_is_refused_without_a_crash(monkeypatch, tmp_path):
    """判据④：`principal: null` 这一格改前改后都是拒，而且要拒得干净（不 500、不跑）。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": None}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["ran"] is False
    assert _outcome(ctx)["last_error"] == "authorization_required"


@pytest.mark.parametrize("junk", ["u-r294", 7, ["a", "b"]])
def test_a_payload_whose_principal_is_not_a_mapping_is_refused_without_a_crash(
    monkeypatch, tmp_path, junk
):
    """判据④：异形载荷（字符串/数字/列表）一律拒，一条异常都不许从 worker 里逃出来。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": junk}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["ran"] is False
    assert _outcome(ctx)["status"] in {"dead", "queued"}


@pytest.mark.parametrize(
    "broken",
    [
        {"user_id": USERNAME, "username": USERNAME, "clearance": "很高"},
        {"user_id": USERNAME, "username": USERNAME, "roles": "staff"},
        {"username": {"nested": 1}, "user_id": USERNAME},
    ],
)
def test_a_principal_dict_with_unreadable_dimensions_is_invalidated_not_guessed(
    monkeypatch, tmp_path, broken
):
    """判据④：一份带 user_id 却把某一维写成不可读形状的 dict，判失效而不是替它猜一次。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": broken}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["ran"] is False
    assert _outcome(ctx)["last_error"] in {
        queue_worker.IDENTITY_STALE,
        queue_worker.IDENTITY_SUBJECT_MISMATCH,
    }


def test_the_memory_user_store_runs_on_the_snapshot_and_says_so(monkeypatch, tmp_path):
    """判据④的回退口径（写死在这里，不留在实现里猜）：用户表长在进程内时 worker 无从
    现取，本轮按快照执行，并在日志里明写"未经现取校验"。"""
    ctx = _install(monkeypatch, tmp_path, lane="report", storage_mode="memory")
    ctx.store.move_department(USERNAME, RESEARCH)  # 这一档里那是别人进程的表，无从比对

    assert ctx.worker.process_one() is True

    projection, provenance = _handed_to_graph(ctx)
    assert provenance == queue_worker.CONSUMPTION_PRINCIPAL_PROVENANCE
    assert projection["department"] == FINANCE, "回退口径 = 按快照原样，不补默认值也不换身份"
    assert _outcome(ctx)["status"] == "done"


def test_a_department_less_snapshot_never_scans_the_library(monkeypatch, tmp_path):
    """判据④最要紧的那句"不得静默按无部门跑遍全库"是可证的，不只是个愿望：
    闸门对没有部门的主体直接拒（`app/rag/filters.py:135-139`），可见行数为 0。"""
    ctx = _install(monkeypatch, tmp_path, lane="report", storage_mode="memory")
    thin = {"user_id": USERNAME, "username": USERNAME, "roles": ["staff"]}
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": thin}))

    assert ctx.worker.process_one() is True

    projection, _provenance = _handed_to_graph(ctx)
    assert _surface(projection) == frozenset()
    assert ctx.refusals[-1] == (USERNAME, "authorization_unavailable")


def test_the_snapshot_fallback_is_unreachable_in_a_production_deployment(monkeypatch):
    """回退口径不是生产侧的一道洞：`storage_mode == memory` 在生产形态下不可达。

    判据④点名要查的就是“这一档默认值究竟谁来吃”，所以不照签名猜，直接按调用点取证：
    `app/common/auth.py:163-188` 的取值只有三个来源，PG 不可达时生产侧回 ``unavailable``
    （本单判失效那一档），只有非生产才回 ``memory``（本单的回退口径）。
    """
    monkeypatch.setenv("APP_ENV", "production")
    state = auth.user_storage_state()
    assert state["storage_mode"] in {"postgres", "unavailable"}, state

    monkeypatch.setenv("APP_ENV", "development")
    assert auth.user_storage_state()["storage_mode"] == "memory"


def test_the_unreachable_user_store_invalidates_and_keeps_the_retry_budget(monkeypatch, tmp_path):
    """判据④的第三档：生产形态下用户库不可达（`storage_mode=unavailable`）判失效，
    但它是故障不是授权判定——照旧回 pending 重投，不占死这枚名额。"""
    ctx = _install(monkeypatch, tmp_path, lane="report", storage_mode="unavailable")

    assert ctx.worker.process_one() is True

    outcome = _outcome(ctx)
    assert outcome["ran"] is False
    assert outcome["last_error"] == queue_worker.IDENTITY_STORE_UNAVAILABLE
    assert outcome["status"] == "queued", "用户库连不上是故障，重投有可能救回来"
    assert outcome["attempts"] == 1
    assert outcome["history"] == [], "还要重试的这一轮不是终态，历史里不许先写一行失败"


# ==================== 判据⑤：反证钉（逐条对 ①②③④） ====================


def test_counter_evidence_trusting_the_snapshot_runs_the_old_department(monkeypatch, tmp_path):
    """反证一（判据①）：把消费侧退回改前那一版，旧部门就真的跑完了——正题不是空转。

    改动只落在内存里的一枚替身上，收尾再核一次工作树的 sha256（写法照
    `tests/test_r290_department_endpoint.py:653`）。
    """
    digest = hashlib.sha256(WORKER_SOURCE.read_bytes()).hexdigest()
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _as_if_before_fix(monkeypatch)
    ctx.store.move_department(USERNAME, RESEARCH)

    assert ctx.worker.process_one() is True

    projection, _provenance = _handed_to_graph(ctx)
    assert projection["department"] == FINANCE, "改前的形状：跑的是入队那一刻冻住的旧部门"
    assert _outcome(ctx)["status"] == "done", "而且被记成了一次成功"
    assert _surface(projection) != _surface(_fresh_request_principal(ctx.store))
    assert hashlib.sha256(WORKER_SOURCE.read_bytes()).hexdigest() == digest, "反证钉不许动工作树"


def test_counter_evidence_dropping_department_from_the_drift_fields_blinds_the_tamper_gate(
    monkeypatch, tmp_path
):
    """反证二（判据③）：从漂移维度里摘掉 `department`，篡改载荷就再也读不出来。

    摘掉之后跑的还是现取身份——不变量仍然守住（作用域等于此刻新发一个请求），丢掉的是
    两样别的东西：一份被改成别的部门的单子不再被拒，以及"入队与消费之间又变了"那一格
    从判失效退化成悄悄换面。这两样正是判据③与判据①各自点名要挡的形状。
    """
    digest = hashlib.sha256(WORKER_SOURCE.read_bytes()).hexdigest()
    assert "department" in queue_worker.PRINCIPAL_SCOPE_FIELDS

    # 第一格：篡改部门。带着那一维时它判失效（`test_a_payload_rewritten_to_another_department_is_invalidated`），摘掉之后闸门就瞎了。
    tampered = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(tampered.queue, tampered.request_id)
    forged = dict(payload["principal"], department=RESEARCH)
    _rewrite_stored(tampered.queue, tampered.request_id, lambda p: p.update({"principal": forged}))
    monkeypatch.setattr(
        queue_worker,
        "PRINCIPAL_SCOPE_FIELDS",
        tuple(f for f in queue_worker.PRINCIPAL_SCOPE_FIELDS if f != "department"),
    )

    assert tampered.worker.process_one() is True

    outcome = _outcome(tampered)
    assert outcome["ran"] is True, "摘掉那一维，篡改就读不出来了：那一维是牙"
    assert outcome["status"] == "done", outcome["last_error"]
    projection, _provenance = _handed_to_graph(tampered)
    assert projection["department"] == FINANCE, "放行不等于放宽：权威仍是现取那一行"
    assert _surface(projection) == _surface(_fresh_request_principal(tampered.store))

    # 第二格：同一次摘维把判失效换成悄悄换面——本单不许的那第三种方向又回来了。
    moved = _install(monkeypatch, tmp_path, lane="report")
    moved.store.move_department(USERNAME, RESEARCH)
    assert moved.worker.process_one() is True

    assert _outcome(moved)["status"] == "done"
    assert _handed_to_graph(moved)[0]["department"] == RESEARCH, "悄悄换了面"
    assert hashlib.sha256(WORKER_SOURCE.read_bytes()).hexdigest() == digest


def test_the_graph_never_receives_a_smuggled_snapshot_field(
    monkeypatch, tmp_path
):
    """直证"快照不是权威"：把两枚**不参与**漂移比对的非授权维改成与用户库不同的值。

    漂移比对放行（这两维说的是出处与本轮读数，不是可见范围），但交给图的那一份里
    它们必须是现取的值——载荷想靠这两格夹带任何东西，都带不进去。
    """
    ctx = _install(monkeypatch, tmp_path, lane="report")
    _body, payload = _stored(ctx.queue, ctx.request_id)
    smuggled = dict(payload["principal"], auth_source="sso", request_id="req-frozen-at-enqueue")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": smuggled}))

    assert ctx.worker.process_one() is True

    assert _outcome(ctx)["status"] == "done", "这两维不该造出假失效"
    projection, _provenance = _handed_to_graph(ctx)
    fresh = _fresh_request_principal(ctx.store)
    assert projection["auth_source"] == fresh.auth_source == "local"
    assert projection["request_id"] == fresh.request_id == ""


def test_counter_evidence_a_provenance_that_any_dict_may_carry_blinds_the_tool_gate(monkeypatch):
    """反证三（判据②）：把签名取值放宽成"没有也算"，冻结快照就能冒充身份。"""
    digest = hashlib.sha256(TOOLS_SOURCE.read_bytes()).hexdigest()
    snapshot = Principal.from_user(_row()).model_dump(mode="json")

    with pytest.raises(PermissionError):
        tools._tool_principal({"configurable": {"principal": snapshot}})

    monkeypatch.setattr(tools, "CONSUMPTION_PRINCIPAL_PROVENANCE", "")
    let_through = tools._tool_principal({"configurable": {"principal": snapshot}})
    assert let_through.model_dump(mode="json") == snapshot, "放宽之后快照又能当身份了"
    assert hashlib.sha256(TOOLS_SOURCE.read_bytes()).hexdigest() == digest


def test_counter_evidence_defaulting_a_legacy_snapshot_is_a_silent_no_department_run(
    monkeypatch, tmp_path
):
    """反证四（判据④）：改前那一版遇到"没带部门的旧载荷"会用 pydantic 默认值静默补齐
    ——部门空、密级 1——正是判据④点名不许的那种形状；今天它被判失效。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    legacy = {"user_id": USERNAME, "username": USERNAME, "roles": ["staff"]}
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": legacy}))
    _as_if_before_fix(monkeypatch)

    assert ctx.worker.process_one() is True

    projection, _provenance = _handed_to_graph(ctx)
    filled = Principal.model_validate(projection)
    assert filled.department == "" and filled.clearance == 1, "改前：默认值被当成身份用了"
    assert _surface(filled) == frozenset()


def test_counter_evidence_the_gate_is_what_keeps_the_widened_surface_from_running(
    monkeypatch, tmp_path
):
    """反证五（判据③可数的那一半）：同一枚篡改载荷，改前跑出来的越权行确实比基准宽。"""
    ctx = _install(monkeypatch, tmp_path, lane="report")
    baseline = _surface(_fresh_request_principal(ctx.store))
    _body, payload = _stored(ctx.queue, ctx.request_id)
    widened = dict(payload["principal"], department=RESEARCH, clearance=3, clearance_label="admin")
    _rewrite_stored(ctx.queue, ctx.request_id, lambda p: p.update({"principal": widened}))
    _as_if_before_fix(monkeypatch)

    assert ctx.worker.process_one() is True

    projection, _provenance = _handed_to_graph(ctx)
    assert len(_surface(projection)) > len(baseline)
    assert _outcome(ctx)["ran"] is True, "改前这一轮会跑完：闸门才是把面收住的那一格"


def test_the_worker_no_longer_hands_the_frozen_snapshot_to_the_graph():
    """钉在文本上，因为它是形状问题：改前三处 `payload.get("principal")` 直接喂给图与
    出处复核，今天这三处都换成了消费时刻的投影。整块读源码，不靠注释自觉。"""
    source = WORKER_SOURCE.read_text(encoding="utf-8")

    for gone in (
        'principal=payload.get("principal")',
        'user={"principal": payload.get("principal")}',
        'agent_results, payload.get("principal")',
        '{"orchestrator": record}, payload.get("principal")',
    ):
        assert gone not in source, f"病灶又被写回去了：{gone}"
    assert source.count("resolve_consumption_principal(") >= 2, "定义之外还要有调用点"
