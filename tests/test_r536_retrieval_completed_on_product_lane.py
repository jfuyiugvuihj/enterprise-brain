# -*- coding: utf-8 -*-
"""R536 判据① —— 产品问答道（``POST /ask``：流式腿与批准续跑腿）确实发出 ``retrieval.completed``。

症状与裁定（09-30 的历史陈述，不是今天的读数）：全仓发这枚事件的只有 ``app/rag/debug.py`` 那一枚
RAG 调试面，正常问答链一枚都不发 ⇒ ``retrieval_traces`` 当时读数为 0 行。裁定与词表只有一份真源：
``scripts/r483_empty_tables_triage.py::TRIAGE["retrieval_traces"]``（现取用它的 ``--json``；再生件
``docs/testing/r483-empty-tables-2026-09-29.md`` 里那一节由它渲染，行号会漂，本文件不引行号——那一格
今天已按现读改过判，抄词与抄行号都会当场过期（R593／R597）。
🔴 同一条裁定钉着口径：**不许拿 ``POST /retrieval/debug`` 那一腿冒充产品道** —— 所以本文件把
「调试面仍旧只发它自己那一枚」也钉成判据（``test_the_debug_face_still_emits_exactly_one``）。

发射实现只有一处（``app/rag/retrieval_pipeline.py`` 末节），调用点只有一处
（``RetrievalPipeline.search_for_principal``）；唯一性见
``tests/test_r536_single_emission_point.py``，反证刀见 ``tests/test_r536_counter_evidence_teeth.py``。

身份传递这一格不是推断：``_ask`` / ``_approve`` 两枚用例真的驱动 ``app/api/v1/chat.py`` 的端点，
让假编排跑在 ``loop.run_in_executor(_executor, _run)`` 的工作线程里、在那一侧跑真
``search_for_principal``，所以「跨不跨得过那枚 executor」是被量出来的。
全程离线：不建 PersistentClient、不打 Ollama、不起服务、不动 docker。
"""
import asyncio
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

from app.agents.contracts import Principal
from app.rag import retrieval_pipeline
from app.rag.filters import resolve_document_retrieval_scope
from app.rag.retrieval_pipeline import (
    RetrievalTraceContext,
    arm_retrieval_trace,
    current_retrieval_trace_context,
    record_retrieval_completed,
    reset_retrieval_trace,
)
from app.storage import pending_approvals as approval_store
from app.storage.sessions import SessionRegistry
from app.trace.projections import project_event, project_run

QUERY = "差旅报销上限是多少？"
SESSION_ID = "r536-turn"
TRACE_ID = "trace-r536"
REQUEST_ID = "req-r536"
TASK_ID = "task-r536"
TRACE_STORE_GETTER = "_product_trace_store"

#: 三条候选：本部门且档内可看、跨部门、同部门但越密级（manager 上限 2）。
CORPUS = [
    {"content": "财务部差旅报销上限 2000 元。", "source": "travel-policy.pdf", "chunk_index": 0,
     "classification": 2, "department": "finance"},
    {"content": "HR 薪酬带宽表。", "source": "hr-salary-band.pdf", "chunk_index": 1,
     "classification": 1, "department": "hr"},
    {"content": "董事会纪要（机密）。", "source": "board-minutes.pdf", "chunk_index": 2,
     "classification": 3, "department": "finance"},
]

#: 消费方 project_retrieval 现读的几格；缺任何一枚都算「发了但读不出」。
CONSUMER_KEYS = ("owner_id", "query_hash", "filters", "hits")


def principal() -> Principal:
    """非管理员：部门 finance、密级上限 2（manager），与在册那批权限用例同一份主体形状。"""
    return Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )


# ------------------------------------------------------------------ 离线检索腿
class StubSemantic:
    def __init__(self, corpus):
        self.corpus = corpus
        self.asks = []

    def search(self, query, k=10, where=None):
        self.asks.append({"query": query, "k": k, "where": where})
        return [dict(doc) for doc in self.corpus][:k]


class StubBm25:
    def search(self, query, k=10, pred=None):
        return []


class StubReranker:
    def rerank(self, query, docs, top_k=5):
        for index, doc in enumerate(docs):
            doc["_score"] = round(0.9 - 0.1 * index, 2)
        return docs[:top_k]


class StubRewriter:
    def rewrite(self, question):
        return {}


class RecordingStore:
    """只记账的 TraceStore 替身：``record_event`` 的入参原样落进 events。"""

    def __init__(self):
        self.events = []

    def record_event(self, **kwargs):
        event = {
            "sequence": len(self.events) + 1,
            "timestamp": "2026-09-30T09:30:00+08:00",
            "task_id": kwargs.get("task_id", ""),
            **kwargs,
        }
        self.events.append(event)
        return event


class ExplodingStore:
    """遥测后端炸了：留痕发不出去，但一轮问答照旧交回它的检索结果。"""

    def record_event(self, **kwargs):
        raise RuntimeError("trace backend down")


def build_pipeline(module=retrieval_pipeline):
    """按 ``__new__`` 造一枚 RetrievalPipeline：一枚真实协作者都不构造（不碰向量库与模型）。"""
    pipeline = module.RetrievalPipeline.__new__(module.RetrievalPipeline)
    pipeline.semantic = StubSemantic(CORPUS)
    pipeline.bm25 = StubBm25()
    pipeline.reranker = StubReranker()
    pipeline.rewriter = StubRewriter()
    return pipeline


class store_front:
    """把某一枚模块的 ``_product_trace_store`` 换成替身，退出时**逐字还原**。"""

    def __init__(self, module, store):
        self.module = module
        self.store = store

    def __enter__(self):
        self.previous = getattr(self.module, TRACE_STORE_GETTER)
        setattr(self.module, TRACE_STORE_GETTER, lambda: self.store)
        return self

    def __exit__(self, *_exc):
        setattr(self.module, TRACE_STORE_GETTER, self.previous)
        return False


def run_leg(module=retrieval_pipeline, *, who=None, armed=True, top_k=5):
    """跑一发产品道检索，交回 (命中, 事件清单, 改写清单)。``armed=False`` 就是没挂身份那一支。"""
    recorder = RecordingStore()
    # 用**这一枚模块自己**的挂/交回：影子副本（反证刀）带着另一枚 contextvar，
    # 拿真模块去挂变异体，量到的就不是它声称的那一格。
    token = (
        getattr(module, "arm_retrieval_trace")(
            trace_id=TRACE_ID, request_id=REQUEST_ID, task_id=TASK_ID
        )
        if armed
        else None
    )
    with store_front(module, recorder):
        try:
            docs, rewrites = build_pipeline(module).search_for_principal(
                QUERY, who or principal(), top_k=top_k, tier="fast"
            )
        finally:
            getattr(module, "reset_retrieval_trace")(token)
    return docs, list(recorder.events), rewrites


# --------------------------------------------------------------------- 判据本体
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def judge_event(event, *, who, scope, hits, top_k=5) -> list[str]:
    """把「这一枚事件算不算发对了」折成一串违规；空清单 = 达标。

    逐格对照消费方 ``project_retrieval`` 现读要的入参（判据① 的后半句就钉在这儿）。
    """
    problems = []
    if event is None:
        return ["产品问答道没发出任何 retrieval.completed"]
    if event.get("event_type") != "retrieval.completed":
        problems.append(f"事件名不是 retrieval.completed：{event.get('event_type')!r}")
    if event.get("status") != "completed":
        problems.append(f"status 不是 completed：{event.get('status')!r}")
    if event.get("trace_id") != TRACE_ID:
        problems.append(f"trace_id 没挂上本轮：{event.get('trace_id')!r}")
    if event.get("request_id") != REQUEST_ID:
        problems.append(f"request_id 没挂上本轮：{event.get('request_id')!r}")
    if event.get("task_id") != TASK_ID:
        problems.append(f"task_id 没挂上本轮：{event.get('task_id')!r}")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return problems + ["payload 不是 dict"]
    for key in CONSUMER_KEYS:
        if key not in payload:
            problems.append(f"消费方要的 payload[{key!r}] 这一格根本没发")
    if payload.get("owner_id") != str(getattr(who, "user_id", "") or ""):
        problems.append(f"owner_id 不是这一轮的主体：{payload.get('owner_id')!r}")
    digest = str(payload.get("query_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        problems.append(f"query_hash 不是 64 位十六进制摘要（表列是 CHAR(64) NOT NULL）：{digest!r}")
    elif digest != _sha(QUERY):
        problems.append("query_hash 不是这一发查询的 sha256")
    if payload.get("filters") != scope.filters:
        problems.append("filter_snapshot 的来源不是 scope.filters 那一份判定")
    ledger = payload.get("hits")
    if not isinstance(ledger, list) or len(ledger) != len(hits):
        problems.append(f"hits 与实际交回的命中不同数：{ledger!r}")
    else:
        if any("content" in row for row in ledger):
            problems.append("检索留痕把正文抄进了 trace 表")
        if [row.get("source") for row in ledger] != [doc.get("source") for doc in hits]:
            problems.append("hits 的来源清单与实际交回的命中不一致")
    if payload.get("scope_reason") != scope.reason_code:
        problems.append(f"scope_reason 与 scope 的因由不同：{payload.get('scope_reason')!r}")
    if payload.get("top_k") != top_k:
        problems.append(f"top_k 这一格：{payload.get('top_k')!r}")
    if not isinstance(payload.get("duration_ms"), (int, float)):
        problems.append(f"duration_ms 不是一个数：{payload.get('duration_ms')!r}")
    return problems


def judge_projection(event, hits) -> list[str]:
    """把事件喂给**在册真消费方**，逐格核它折出来的那一行 retrieval_traces。"""
    rows = [
        projection
        for projection in project_event(
            event, owner_id=event["payload"]["owner_id"], fetch=lambda *_a: None
        )
        if projection.collection == "retrieval_traces"
    ]
    if len(rows) != 1:
        return [f"project_event 折出的 retrieval_traces 行数是 {len(rows)}，不是 1"]
    projection = rows[0]
    row = projection.values
    problems = []
    if projection.record_id != f"{TRACE_ID}:{event['sequence']}":
        problems.append(f"主键不是 trace:sequence：{projection.record_id!r}")
    if row["agent_run_id"] != f"{TRACE_ID}:orchestrator":
        problems.append(f"agent_run_id 没落到本轮的 run：{row['agent_run_id']!r}")
    if row["request_id"] != REQUEST_ID or row["trace_id"] != TRACE_ID:
        problems.append("行上的 request_id / trace_id 与本轮不同源")
    if row["status"] != "completed":
        problems.append(f"行上的 status：{row['status']!r}")
    if row["created_at"] != event["timestamp"]:
        problems.append("created_at 不是事件的时间戳")
    if row["result_summary"] != {"hit_count": len(hits)}:
        problems.append(f"result_summary.hit_count：{row['result_summary']!r}")
    if not row["filter_snapshot"]:
        problems.append(f"filter_snapshot 不是那份谓词：{row['filter_snapshot']!r}")
    if row["index_version_id"] is not None:
        problems.append("index_version_id 今天没有真源，不许凭空填一格")
    return problems


# ==================================================================== 判据① 本体
def test_the_principal_aware_retrieval_leg_emits_one_event():
    who = principal()
    scope = resolve_document_retrieval_scope(who)
    docs, events, rewrites = run_leg(who=who)

    assert rewrites == []
    assert len(events) == 1, events
    assert judge_event(events[0], who=who, scope=scope, hits=docs) == []
    # 权限口径一个字都没动：越权的那两条既不进命中也不进留痕
    assert [doc["source"] for doc in docs] == ["travel-policy.pdf"]


def test_the_event_is_what_the_registered_consumer_reads():
    docs, events, _rewrites = run_leg(who=principal())
    assert judge_projection(events[0], docs) == []


def test_the_row_lands_in_retrieval_traces_through_the_real_store(tmp_path):
    """不靠替身：真 ``TraceStore`` + JSON 持久化 ⇒ 投影完的行必须真的躺在 ``retrieval_traces`` 上。

    这就是 C 门「检索留痕」那半格从今天起能升级到生产读数的形状；至于库里
    ``retrieval_traces.rows > 0``，本单不起服务不打模型 ⇒ 那一格交回读数纸。
    """
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    persistence = JsonPersistenceAdapter(tmp_path / "records.json")
    store = TraceStore(tmp_path / "traces.jsonl", persistence=persistence)
    who = principal()

    with store_front(retrieval_pipeline, store):
        token = arm_retrieval_trace(trace_id=TRACE_ID, request_id=REQUEST_ID, task_id=TASK_ID)
        try:
            docs, _ = build_pipeline().search_for_principal(QUERY, who, top_k=5, tier="fast")
        finally:
            reset_retrieval_trace(token)

    row = persistence.get("retrieval_traces", f"{TRACE_ID}:1")
    assert row is not None, "事件发出去了，retrieval_traces 却没有行"
    assert row["result_summary"]["hit_count"] == len(docs) == 1
    assert row["owner_id"] == who.user_id
    assert row["status"] == "completed"
    assert row["query_hash"] == _sha(QUERY)
    assert row["filter_snapshot"] == resolve_document_retrieval_scope(who).filters


def test_the_ask_stream_lane_arms_the_worker_thread_it_really_runs_in(monkeypatch, tmp_path):
    """驱动真 ``chat.ask``：身份必须在图跑的那枚工作线程里读得到，留痕才会挂上本轮的 trace。"""
    from app.api.v1 import chat

    seen: list = []
    store = RecordingStore()
    monkeypatch.setattr(retrieval_pipeline, TRACE_STORE_GETTER, lambda: store)
    # 端点自己那几处 default_trace_store（读数腿与续跑轮的第三处出口）也接到同一枚替身上：
    # 本单不许往盘面写 data/traces/events.jsonl 这类野文件，而同一本账反而能核对 trace 同源。
    monkeypatch.setattr("app.trace.store.default_trace_store", lambda: store)

    def fake_stream(*_args, **_kwargs):
        seen.append(current_retrieval_trace_context())
        build_pipeline().search_for_principal(QUERY, principal(), top_k=5, tier="fast")
        yield {
            "messages": [],
            "worker_results": {"doc": "上限 2000 元。"},
            "final_answer": "上限 2000 元。",
        }

    _patch_chat_offline(monkeypatch, chat, tmp_path, fake_stream)
    # 端点是 async def：先把它 await 成 StreamingResponse，再单独把帧抽干（在册同族
    # tests/test_approve_canonical_events.py:219-232 就是这个两段式形状）
    response = asyncio.run(chat.ask(
        chat.AskRequest(message=QUERY, session_id=SESSION_ID),
        http_request=_http_request(principal()),
    ))
    body = asyncio.run(_consume(response))

    assert seen and isinstance(seen[0], RetrievalTraceContext), "工作线程里读不到问答身份"
    retrieval = [item for item in store.events if item["event_type"] == "retrieval.completed"]
    assert len(retrieval) == 1, store.events
    event = retrieval[0]
    assert event["trace_id"] == seen[0].trace_id
    assert event["payload"]["owner_id"] == principal().user_id
    # 客户端在这一轮拿到的 trace 编号，就是能在 retrieval_traces 上查到的那一枚
    assert event["trace_id"] in body, body[:600]


def test_the_approval_continuation_lane_emits_too(monkeypatch, tmp_path):
    """``POST /approve`` 的续跑腿：图 resume 之后那条检索腿同样要留痕（判据① 点名的一格）。"""
    from app.api.v1 import chat

    seen: list = []
    store = RecordingStore()
    monkeypatch.setattr(retrieval_pipeline, TRACE_STORE_GETTER, lambda: store)
    monkeypatch.setattr("app.trace.store.default_trace_store", lambda: store)

    def fake_stream(*_args, **_kwargs):
        seen.append(current_retrieval_trace_context())
        build_pipeline().search_for_principal(QUERY, principal(), top_k=5, tier="fast")
        yield {
            "messages": [],
            "worker_results": {"doc": "已批准。"},
            "final_answer": "已批准。",
        }

    _patch_chat_offline(monkeypatch, chat, tmp_path, fake_stream)
    response = asyncio.run(chat.approve(
        chat.ApproveRequest(session_id=SESSION_ID, approved=True),
        http_request=_http_request(principal()),
    ))
    body = asyncio.run(_consume(response))

    assert seen and isinstance(seen[0], RetrievalTraceContext), "批准续跑的工作线程里读不到身份"
    retrieval = [item for item in store.events if item["event_type"] == "retrieval.completed"]
    assert len(retrieval) == 1, store.events
    assert retrieval[0]["trace_id"] == seen[0].trace_id
    assert retrieval[0]["trace_id"] in body, body[:600]
    # R172 的第三处出口（request.started）与这一枚留痕挂在同一枚 trace 上：/approve 的这一支
    # 因此不会种出一枚「只有检索、没有开始」的孤儿 run 行。
    started = [item for item in store.events if item["event_type"] == "request.started"]
    assert started and started[0]["trace_id"] == retrieval[0]["trace_id"], store.events


def test_the_debug_face_still_emits_exactly_one():
    """🔴 口径钉：``POST /retrieval/debug`` 那一腿不许因为本单变成两行。

    调试面不挂问答身份 ⇒ 末节那枚发射器在它上面直接返回 None，它仍旧只发 ``app/rag/debug.py``
    自己那一枚。摘掉「没身份就不发」那一格，本钉当场红（反证刀 K2）。
    """
    from app.rag.debug import run_retrieval_debug

    store = RecordingStore()
    documents, events, _rewrites = run_leg(who=principal(), armed=False)
    assert documents and events == []

    report = run_retrieval_debug(
        QUERY,
        principal(),
        pipeline=build_pipeline(),
        trace_store=store,
        trace_id="retrieval-debug:x",
        request_id="retrieval-debug:y",
    )
    assert report["results"]
    assert len(store.events) == 1, store.events
    assert store.events[0]["payload"].get("sources") is not None, "调试面自己那一枚的形状被改写了"


# ------------------------------------------------------------------- 边界四条
def test_an_unarmed_retrieval_emits_nothing_and_returns_the_same_hits():
    armed_docs, armed_events, _ = run_leg(who=principal(), armed=True)
    bare_docs, bare_events, _ = run_leg(who=principal(), armed=False)

    assert armed_events and not bare_events
    assert [doc["source"] for doc in armed_docs] == [doc["source"] for doc in bare_docs]


def test_arm_refuses_to_invent_an_identity():
    """缺任何一枚硬身份都不挂：宁可不发，也不把一轮问答挂到编出来的 trace 上。"""
    assert arm_retrieval_trace(trace_id="", request_id=REQUEST_ID) is None
    assert arm_retrieval_trace(trace_id=TRACE_ID, request_id="  ") is None
    assert current_retrieval_trace_context() is None
    assert record_retrieval_completed(query=QUERY, hits=[], scope=None) is None


def test_the_identity_does_not_leak_to_the_next_turn_on_a_reused_thread():
    """executor 的线程会被复用：``finally`` 里那枚 token 不交回，下一轮就挂着上一轮的 trace。"""
    store = RecordingStore()
    with store_front(retrieval_pipeline, store):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_one_turn).result()
            pool.submit(_bare_turn).result()

    assert len(store.events) == 1, store.events
    assert store.events[0]["trace_id"] == TRACE_ID


def _one_turn():
    token = arm_retrieval_trace(trace_id=TRACE_ID, request_id=REQUEST_ID, task_id=TASK_ID)
    try:
        build_pipeline().search_for_principal(QUERY, principal(), top_k=5, tier="fast")
    finally:
        reset_retrieval_trace(token)


def _bare_turn():
    # 同一枚线程、没挂身份：这一发检索必须一个字都不写，而不是沿用上一轮的 trace 编号
    build_pipeline().search_for_principal(QUERY, principal(), top_k=5, tier="fast")


def test_a_dead_trace_backend_does_not_break_the_answer():
    """留痕是遥测：后端炸了也不许打断已经跑到手的这一轮（与 ``_record_trace`` 同一裁定）。"""
    token = arm_retrieval_trace(trace_id=TRACE_ID, request_id=REQUEST_ID)
    try:
        with store_front(retrieval_pipeline, ExplodingStore()):
            docs, _rewrites = build_pipeline().search_for_principal(QUERY, principal(), top_k=5, tier="fast")
    finally:
        reset_retrieval_trace(token)
    assert [doc["source"] for doc in docs] == ["travel-policy.pdf"]


def test_a_lone_retrieval_event_seeds_the_run_row_completed_and_says_so():
    """现状钉（不是愿望）：留痕是某一枚 trace 的第一枚事件时，``project_run`` 会把那枚 run
    直接种成 ``completed``。``/ask`` 碰不到这一支（orchestrator 的 ``request.started`` 一定在先）。

    🔴 09-30 **R551 改口**（本文件唯一被点名授权改动的一枚）：``/approve`` 那一格**原先**的竞窗口
    ——第三处出口排在 ``_run`` 提交之后——已经从产品道治掉：chat.py 把 ``request.started`` 上移到
    提交之前。产品道凭据在 ``tests/test_r551_resumed_lane_seeds_before_executor.py``（顺序两形
    ＋失败轮不许显示 ``completed``）。本枚钉**留下不走**：它钉的是投影层语义本身——谁先落第一枚
    事件谁就定这枚 run 的种子，这条规则一个字都没改，改的只是谁先落。"""
    event = {
        "trace_id": TRACE_ID, "request_id": REQUEST_ID, "task_id": TASK_ID, "sequence": 1,
        "timestamp": "2026-09-30T09:30:00+08:00", "event_type": "retrieval.completed",
        "status": "completed",
        "payload": {"owner_id": "alice", "query_hash": _sha(QUERY), "hits": [], "filters": {}},
    }
    assert project_run(event, "alice", {}).values["status"] == "completed"
    # 而 request.started 在先时，这一枚留痕一个字都不改那枚 run 的结论
    assert project_run(event, "alice", {"status": "running"}).values["status"] == "running"


# ---------------------------------------------------------------- chat.py 的离线夹具
def _http_request(who: Principal):
    return type("Request", (), {"state": type("State", (), {
        "principal": who, "username": who.username
    })()})()


async def _consume(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _patch_chat_offline(monkeypatch, chat, tmp_path, stream):
    """与 tests/test_approve_canonical_events.py 同一套摘法：假编排、临时会话、假缓存、假账本。"""
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", stream)
    monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", stream)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)
    monkeypatch.setattr(approval_store, "_MEM_ROWS", {})
    monkeypatch.setattr(approval_store, "_database_available", lambda: False)
    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION_ID, principal())
    monkeypatch.setattr(chat, "session_registry", registry)
    return chat
