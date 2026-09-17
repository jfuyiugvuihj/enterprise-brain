"""R41：流式回答必须带来源（canonical ``sources`` 事件），且 legacy 事件名零下线。

判据的落地方式：

1. ``sources`` 是走 ``canonical_sse_event`` 的 canonical 事件（带 request_id/trace_id/
   task_id/sequence/status/timestamp），内容经过与旧 ``/chat`` 端点同一套
   ``scope.allows(...)`` 过滤——本文件把那个谓词逐字复跑一遍再比对结果集合；
2. 改动后的事件名清单必须是改动前基线的**超集**（基线由本文件的记录测试在改动前实取，
   命令与时间戳见 ``BASELINE_*`` 三个常量的注释）；
3. 无权限来源（跨部门、跨密级）进入事件的条数为 0，并且文档名连 raw body 都不许出现。

取证用离线假检索命中 + 假编排流，不打真实 Ollama、不碰真实 Chroma：命中先进
``app/agents/evidence.py::record_document_hits``（工具边界写证据的唯一入口），再由
``build_agent_result`` 落成 canonical AgentResult，最后由假的 ``run_with_stream`` 吐给
``/api/v1/ask``——也就是说，事件里的来源来自工具实际检到的东西，不是从答案文本反推的。
"""
import asyncio
import json
import os
from collections import Counter

import pytest

from app.agents import evidence as evidence_module
from app.common.identity import Principal
from app.rag.filters import resolve_document_retrieval_scope
from app.storage.sessions import SessionRegistry

FINANCE_DOC = "travel-policy.pdf"
HR_DOC = "hr-salary-band.pdf"
SECRET_DOC = "board-minutes.pdf"

# -------------------------------------------------------------------- 基线取证
# 取于改动**前**（HEAD fd8ae7c，``git diff --numstat`` 对 chat.py 为空）。同一份基线用两版
# 夹具各跑一次，两次输出 sha256 相同，说明基线不依赖本文件的夹具写法：
#   Copy-Item app/api/v1/chat.py $env:TEMP\chat_patched.py; git checkout -- app/api/v1/chat.py
#   $env:SSE_EVENT_INVENTORY_OUT = "$env:TEMP\sse_inventory_before_final.jsonl"
#   python -m pytest tests/test_sse_sources.py -q -k test_record_sse_event_name_inventory
#   -> 4 passed @ 2026-09-17 16:24:43 +08:00，sha256=6485800F...DF7E4
#   随后 Copy-Item $env:TEMP\chat_patched.py 回 app/api/v1/chat.py（sha256 已核对一致）
BASELINE_RECORDED_AT = "2026-09-17 16:24:43 +08:00 (HEAD fd8ae7c, pre-change)"
BASELINE_SHA256 = "6485800FA894FCFFBB2C2085276C259F0B801A7306467B58E3D23073712DF7E4"
BASELINE_SSE_EVENT_NAMES = {
    "hitl": ["status", "request.started", "text", "hitl", "request.completed", "done"],
    "success": ["status", "request.started", "text", "request.completed", "done"],
    "success_no_evidence": ["status", "request.started", "text", "request.completed", "done"],
    "unproductive": ["status", "request.started", "error", "request.failed", "done"],
}


# -------------------------------------------------------------------- 离线夹具
def fake_retriever_hits() -> list[dict]:
    """一个假 retriever 的返回，形状与 ``app/rag/retriever.py`` 逐键对齐。

    三条命中刻意覆盖：本部门可看、跨部门、本部门但超出密级上限（manager=2）。
    """
    return [
        {
            "content": "财务部差旅报销上限 2000 元。",
            "source": FINANCE_DOC,
            "chunk_index": 0,
            "classification": 2,
            "department": "finance",
        },
        {
            "content": "HR 薪酬带宽表。",
            "source": HR_DOC,
            "chunk_index": 1,
            "classification": 1,
            "department": "hr",
        },
        {
            "content": "董事会纪要（机密）。",
            "source": SECRET_DOC,
            "chunk_index": 2,
            "classification": 3,
            "department": "finance",
        },
    ]


def doc_agent_result(worker: str, hits: list[dict], answer: str) -> dict:
    """走一遍真实的证据写入边界，拿到与线上同形的 AgentResult 字典。"""
    bag = evidence_module.new_evidence_bag()
    recorded = evidence_module.record_document_hits(bag, query="差旅报销上限", hits=hits)
    assert recorded == len(hits), "证据边界没收下这些命中，本文件的取证就没有意义"
    result = evidence_module.build_agent_result(
        worker=worker,
        answer=answer,
        bag=bag,
        request_id="req-r41",
        trace_id="trace-r41",
        task_id="task-r41",
        session_id="r41-sources",
    )
    return result.model_dump(mode="json")


def doc_state(hits: list[dict], answer: str = "财务部差旅上限 2000 元。") -> dict:
    return {
        "messages": [],
        "worker_results": {"doc": answer},
        "agent_results": {"doc": doc_agent_result("doc", hits, answer)},
        "final_answer": answer,
    }


def finance_principal() -> Principal:
    """非管理员：部门限定 finance、密级上限 2（manager）。"""
    return Principal.from_user({"id": "alice", "username": "alice", "role": "manager", "department": "finance"})


def _http_request(principal: Principal):
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


def patch_offline(monkeypatch, tmp_path, streamed, pending=None):
    """把 /ask 的整条依赖摘成离线件：假编排、假会话、假缓存。"""
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: pending)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", lambda *_a, **_k: iter(streamed))
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    return chat


async def consume(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def drive(monkeypatch, tmp_path, streamed, principal, pending=None) -> str:
    chat = patch_offline(monkeypatch, tmp_path, streamed, pending)
    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message="差旅报销上限是多少？", session_id="r41-sources"),
            http_request=_http_request(principal),
        )
    )
    return asyncio.run(consume(response))


def event_names(body: str) -> list[str]:
    return [line.removeprefix("event: ").strip() for line in body.splitlines() if line.startswith("event: ")]


def events(body: str) -> list[tuple[str, dict]]:
    """把每一行 ``event:`` 与紧跟它的 ``data:`` 配成一对。"""
    pairs: list[tuple[str, dict]] = []
    name = None
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and name:
            pairs.append((name, json.loads(line.removeprefix("data: "))))
            name = None
    return pairs


def sources_event(body: str) -> dict:
    matches = [data for name, data in events(body) if name == "sources"]
    assert len(matches) == 1, f"一轮回答应恰好一个 sources 事件，实际 {len(matches)} 个"
    return matches[0]


SCENARIOS = {
    # 成功轮：证据里混入跨部门与跨密级命中
    "success": lambda hits: [doc_state(hits)],
    # 无证据成功轮（纯数据问答）
    "success_no_evidence": lambda _hits: [
        {"messages": [], "worker_results": {"data": "营收合计 100 万"}, "final_answer": "营收合计 100 万"}
    ],
    # 空产出轮：走 request.failed
    "unproductive": lambda _hits: [{"messages": [], "worker_results": {}, "final_answer": ""}],
    # 挂起轮：图停在 interrupt_before 之前
    "hitl": lambda _hits: [{"messages": [], "worker_results": {}, "final_answer": ""}],
}

PENDING = {"hitl": {"pending": ["chart"], "labels": ["chart step"]}}


# -------------------------------------------------------------------- 取证记录
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_record_sse_event_name_inventory(monkeypatch, tmp_path, scenario):
    """把每个场景实际发出的事件名按顺序写进取证文件（改动前后各跑一次）。

    输出路径由 ``SSE_EVENT_INVENTORY_OUT`` 指定；没设时跳过，免得正常跑测试的人被写出脏文件。
    """
    target = os.environ.get("SSE_EVENT_INVENTORY_OUT", "")
    if not target:
        pytest.skip("SSE_EVENT_INVENTORY_OUT not set; this test only records evidence")
    body = drive(
        monkeypatch,
        tmp_path,
        SCENARIOS[scenario](fake_retriever_hits()),
        finance_principal(),
        pending=PENDING.get(scenario),
    )
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"scenario": scenario, "events": event_names(body)}, ensure_ascii=False) + "\n")
    dump = os.environ.get("SSE_EVENT_BODY_DUMP", "")
    if dump:
        with open(dump, "a", encoding="utf-8") as handle:
            handle.write(f"===== scenario={scenario} =====\n{body}")


# -------------------------------------------------------------------- 判据 ②
@pytest.mark.parametrize("scenario", sorted(BASELINE_SSE_EVENT_NAMES))
def test_legacy_event_names_are_a_superset_of_the_recorded_baseline(monkeypatch, tmp_path, scenario):
    """基线（``BASELINE_RECORDED_AT``）里的每一个事件名、每一次出现，改动后都要还在。

    只断言"集合相等"是不够的：某个 legacy 事件从每轮一次变成零次也是"还在名单里"。
    所以这里比的是 Counter 的**重数**。
    """
    body = drive(
        monkeypatch,
        tmp_path,
        SCENARIOS[scenario](fake_retriever_hits()),
        finance_principal(),
        pending=PENDING.get(scenario),
    )
    before = Counter(BASELINE_SSE_EVENT_NAMES[scenario])
    after = Counter(event_names(body))
    missing = {name: after[name] - count for name, count in before.items() if after[name] < count}
    assert not missing, f"scenario={scenario} 丢了 legacy 事件（次数不足）: {missing}"
    assert set(before) <= set(after)


# -------------------------------------------------------------------- 判据 ①
def test_canonical_sources_event_carries_the_envelope_and_arrives_before_done(monkeypatch, tmp_path):
    body = drive(monkeypatch, tmp_path, SCENARIOS["success"](fake_retriever_hits()), finance_principal())

    payload = sources_event(body)
    for field in ("request_id", "trace_id", "task_id", "sequence", "timestamp", "status", "data"):
        assert field in payload, f"canonical 事件缺少字段 {field}"
    assert payload["status"] == "completed"
    assert payload["data"]["session_id"] == "r41-sources"

    names = event_names(body)
    assert names.index("sources") > names.index("request.completed"), "来源要挂在已完成的请求上"
    assert names.index("sources") < names.index("done"), "done 之后不能再发事件，客户端已经收工"
    completed = next(data for name, data in events(body) if name == "request.completed")
    assert payload["sequence"] == completed["sequence"] + 1, "sequence 必须连续，不能撞号"
    assert payload["request_id"] == completed["request_id"]


def test_sources_rows_are_deduplicated_and_name_the_worker_that_retrieved_them(monkeypatch, tmp_path):
    hits = fake_retriever_hits()[:1]
    streamed = [
        {"messages": [], "worker_results": {}, "agent_results": {"doc": doc_agent_result("doc", hits, "a")}, "final_answer": ""},
        doc_state(hits),
    ]
    body = drive(monkeypatch, tmp_path, streamed, finance_principal())
    rows = sources_event(body)["data"]["sources"]
    assert [row["source"] for row in rows] == [FINANCE_DOC], "同一命中两次上报只应留一行"
    assert rows[0]["worker"] == "doc"
    assert rows[0]["chunk_index"] == 0
    assert rows[0]["permission_checked"] is True


def test_sources_event_reaches_a_real_http_client_over_asgi_transport(monkeypatch, tmp_path):
    """走一遍真实 ASGI 栈（TestClient 的异步等价物），确认事件没被中间件/编码吞掉。"""
    import httpx

    from app.api.v1 import chat
    from app.common.auth import create_token

    patch_offline(monkeypatch, tmp_path, SCENARIOS["success"](fake_retriever_hits()))
    monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)

    async def fetch():
        transport = httpx.ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream(
                "POST",
                "/api/v1/ask",
                json={"message": "差旅报销上限是多少？", "session_id": "r41-asgi"},
                headers={"Authorization": f"Bearer {create_token('admin')}"},
            ) as response:
                assert response.status_code == 200, await response.aread()
                return "\n".join([line async for line in response.aiter_lines()])

    body = asyncio.run(fetch())
    payload = sources_event(body)
    assert payload["data"]["hit_count"] == len(payload["data"]["sources"])
    assert FINANCE_DOC in json.dumps(payload, ensure_ascii=False)


# -------------------------------------------------------------------- 判据 ③ P0
def test_cross_department_and_cross_classification_sources_are_dropped(monkeypatch, tmp_path):
    """无权限来源进入事件的条数必须是 0，而且文件名连 raw body 都不许出现。"""
    body = drive(monkeypatch, tmp_path, SCENARIOS["success"](fake_retriever_hits()), finance_principal())

    payload = sources_event(body)["data"]
    visible = [row["source"] for row in payload["sources"]]
    assert visible == [FINANCE_DOC], f"越权来源泄漏进事件: {visible}"
    assert payload["hit_count"] == 1
    assert payload["unauthorized_count"] == 2, "跨部门 + 跨密级各 1 条，必须被计入被拒次数"
    assert HR_DOC not in body, "被拒来源的文件名不得出现在流的任何位置"
    assert SECRET_DOC not in body, "被拒来源的文件名不得出现在流的任何位置"


@pytest.mark.parametrize(
    ("department", "classification", "expect_visible"),
    [
        ("finance", 2, True),
        ("hr", 1, False),
        ("finance", 3, False),
        ("finance", None, False),  # 缺密级元数据：一律不可见
    ],
)
def test_each_row_is_decided_by_the_same_allows_predicate_as_the_legacy_chat_path(
    monkeypatch, tmp_path, department, classification, expect_visible
):
    """把旧 ``/chat`` 里那句 ``scope.allows(source)`` 逐字复跑，比对事件内容与它一致。"""
    hit = {
        "content": "正文",
        "source": "scoped-doc.pdf",
        "chunk_index": 0,
        "classification": classification,
        "department": department,
    }
    scope = resolve_document_retrieval_scope(finance_principal())
    expected = [candidate for candidate in [hit] if scope.allows(candidate)]

    body = drive(monkeypatch, tmp_path, SCENARIOS["success"]([hit]), finance_principal())
    rows = sources_event(body)["data"]["sources"]

    assert [row["source"] for row in rows] == [row["source"] for row in expected], (
        f"department={department} classification={classification} 的判定与 scope.allows 不一致"
    )
    assert bool(rows) is expect_visible


def test_a_turn_with_no_retrieved_documents_reports_zero_instead_of_fabricating(monkeypatch, tmp_path):
    """没有检到文档就报 0 条：来源不能从答案文本里反推出来。"""
    body = drive(monkeypatch, tmp_path, SCENARIOS["success_no_evidence"](None), finance_principal())
    payload = sources_event(body)["data"]
    assert payload["sources"] == []
    assert payload["hit_count"] == 0
    assert payload["unauthorized_count"] == 0


def test_an_unproductive_turn_emits_no_sources_event(monkeypatch, tmp_path):
    """失败轮既没有 canonical 完成事件，也不许有来源事件。"""
    body = drive(monkeypatch, tmp_path, SCENARIOS["unproductive"](None), finance_principal())
    assert "request.failed" in event_names(body)
    assert "sources" not in event_names(body)
