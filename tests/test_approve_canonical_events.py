"""R55：/api/v1/approve 也要发 canonical SSE 信封事件。

`/ask` 早有 request.started / request.completed / request.failed / request.cancelled /
sources 五类 canonical 事件，而 `/approve` 此前只有取消分支发过 canonical，其余四条分支
（正常完成 / 超时限 / worker 抛错 / 空结果）只有 legacy 事件——同一个客户端要接两套语义。
本单只`加`事件，legacy 一个不减：

1. 五条分支的 canonical 事件名清单与顺序必须与 `/ask` 同构（判据 ①）。同构不照抄常量：
   `test_canonical_sequence_is_isomorphic_with_the_ask_branch` 用同一份假状态分别驱动
   两个端点，再比对 canonical 序列；
2. legacy 零削减（判据 ②）：与改动前实取的 `BASELINE_APPROVE_EVENT_NAMES` 做 Counter
   **重数**比对，事件名与每个名字的出现次数只许多不许少；
3. `sources` 走与 `/ask` 同一个 `_authorized_source_rows` → `filters.allows` 判定
   （判据 ③）：跨部门/跨密级 0 条，无检索报 0，没有产出的轮次干脆不发该事件；
4. 认领 chat.py 注释里那条长期缺口（判据 ④）：批准后图又停在下一个 HITL 节点时，必须把
   挂起记成新的 awaiting 行并发出挂起事件；
5. 「停止 ≠ 拒绝」（判据 ⑥）：新事件不得把 abandoned 变成 refused，也不得反过来。

取证全程离线：假编排 + 临时会话注册表 + 进程内待批账本，不打 Ollama、不开真端口、
不碰真实 Chroma。
"""
import asyncio
import json
import os
import time
from collections import Counter

import pytest
from langchain_core.messages import AIMessage

from app.agents import evidence as evidence_module
from app.common.identity import Principal
from app.rag.filters import resolve_document_retrieval_scope
from app.storage import pending_approvals as store
from app.storage.sessions import SessionRegistry

FINANCE_DOC = "travel-policy.pdf"
HR_DOC = "hr-salary-band.pdf"
SECRET_DOC = "board-minutes.pdf"
ANSWER = "财务部差旅报销上限 2000 元。"
SESSION_ID = "r55-approve"
PENDING_CHART = {"pending": ["chart"], "labels": ["📈 生成图表"]}

CANONICAL_EVENTS = (
    "request.started",
    "request.completed",
    "request.failed",
    "request.cancelled",
    "sources",
)

# -------------------------------------------------------------------- 改动前基线
# 取于改动`前`（HEAD 6ee2f79，`git status --porcelain -uall` 对 chat.py 为空）。同一份基线
# 同一个驱动连跑两次，两份取证文件 sha256 相同，说明各分支的判定不随线程调度先后抖动：
#   $env:APPROVE_EVENT_INVENTORY_OUT = "$env:TEMP\r55_inventory_before.jsonl"
#   & "<venv>\python.exe" -m pytest tests/test_approve_canonical_events.py -q -k record_approve
# BASELINE_* 由该次输出逐字誊抄。改动之后少一个 legacy 事件、或者某个名字的出现次数变少，
# 都会被 test_legacy_event_names_are_a_superset_of_the_recorded_baseline 抓住（判据 ②）。
# 注意改动前 canonical 只有取消分支那一条，其余四条分支一个都没有——这正是本单要补的。
BASELINE_RECORDED_AT = "2026-09-17 17:18:27 +08:00 (HEAD 6ee2f79, pre-change)"
BASELINE_INVENTORY_SHA256 = "9EAA3CCF360D934121064DC91EEF3F221F6AF969B71880250A7F950A87F5E817"  # 取证 jsonl 的哈希
BASELINE_APPROVE_EVENT_NAMES: dict[str, list[str]] = {
    "cancelled": ["request.cancelled", "cancelled"],
    "completed_with_sources": ["text", "done"],
    "completed_without_evidence": ["text", "done"],
    "hitl_repark": ["text", "done"],
    "hitl_repark_no_text": ["done"],
    "timeout": ["error"],
    "unproductive": ["done"],
    "worker_error": ["error"],
}


# -------------------------------------------------------------------- 离线夹具
def retriever_hits() -> list[dict]:
    """三条命中：本部门可看、跨部门、本部门但超出密级上限（manager=2）。"""
    return [
        {"content": ANSWER, "source": FINANCE_DOC, "chunk_index": 0,
         "classification": 2, "department": "finance"},
        {"content": "HR 薪酬带宽表。", "source": HR_DOC, "chunk_index": 1,
         "classification": 1, "department": "hr"},
        {"content": "董事会纪要（机密）。", "source": SECRET_DOC, "chunk_index": 2,
         "classification": 3, "department": "finance"},
    ]


def doc_agent_result(hits: list[dict]) -> dict:
    """证据先进工具边界唯一的写入口，再落成 canonical AgentResult——不从正文反推。"""
    bag = evidence_module.new_evidence_bag()
    recorded = evidence_module.record_document_hits(bag, query="差旅报销上限", hits=hits)
    assert recorded == len(hits), "证据边界没收下这些命中，本文件的取证就没有意义"
    result = evidence_module.build_agent_result(
        worker="doc",
        answer=ANSWER,
        bag=bag,
        request_id="req-r55",
        trace_id="trace-r55",
        task_id="task-r55",
        session_id=SESSION_ID,
    )
    return result.model_dump(mode="json")


def answer_state(*, hits: list[dict] | None = None) -> dict:
    chunk = {
        "messages": [AIMessage(content=ANSWER)],
        "worker_results": {"doc": ANSWER},
        "final_answer": ANSWER,
    }
    if hits is not None:
        chunk["agent_results"] = {"doc": doc_agent_result(hits)}
    return chunk


def parked_state() -> dict:
    """本轮没有正文：可能因为图停在节点前，也可能因为什么都没产出。"""
    return {"messages": [], "worker_results": {}, "final_answer": ""}


def answer_stream(*_args, **_kwargs):
    yield answer_state(hits=retriever_hits())


def no_evidence_stream(*_args, **_kwargs):
    yield answer_state()


def empty_stream(*_args, **_kwargs):
    return
    yield  # pragma: no cover - 只为把本函数变成生成器


def raising_stream(*_args, **_kwargs):
    raise RuntimeError("worker exploded")
    yield  # pragma: no cover - 只为把本函数变成生成器


def slow_stream(*_args, **_kwargs):
    # 比 CHAT_REQUEST_TIMEOUT 长，保证超时限分支一定被走到；0.3s 不会拖慢测试会话。
    time.sleep(0.3)
    yield answer_state()


def cancelling_stream(*_args, **kwargs):
    # 先置位再产出：工作线程那侧会把这条 event 丢掉，主流只在取消分支收尾，于是
    # legacy text 会不会出现不再取决于线程调度先后。
    kwargs["cancel_event"].set()
    yield parked_state()


SCENARIOS = {
    "completed_with_sources": {"stream": answer_stream},
    "completed_without_evidence": {"stream": no_evidence_stream},
    "unproductive": {"stream": empty_stream},
    # 钉住超时上限：这一支要测的是抛错，不能让机器上恰好设了很小的
    # CHAT_REQUEST_TIMEOUT 把它提前撞进超时限分支。
    "worker_error": {"stream": raising_stream, "env": {"CHAT_REQUEST_TIMEOUT": "300"}},
    "timeout": {"stream": slow_stream, "env": {"CHAT_REQUEST_TIMEOUT": "0.01"}},
    "cancelled": {"stream": cancelling_stream},
    "hitl_repark": {"stream": answer_stream, "pending": PENDING_CHART},
    "hitl_repark_no_text": {"stream": empty_stream, "pending": PENDING_CHART},
}


@pytest.fixture(autouse=True)
def memory_ledger(monkeypatch):
    """待批账本走进程内后端：判据 ④/⑥ 要读账面，但绝不允许碰真库。"""
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)
    return None


def finance_principal() -> Principal:
    """非管理员：部门限定 finance、密级上限 2（manager）。"""
    return Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )


def _http_request(principal: Principal):
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": principal.username})()},
    )()


def _patch_offline(monkeypatch, tmp_path, stream, pending):
    """把两个端点的依赖摘成离线件：假编排、临时会话注册表、假缓存、假持久化。"""
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", stream)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", stream)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: pending)
    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION_ID, finance_principal())
    monkeypatch.setattr(chat, "session_registry", registry)
    return chat


async def _consume(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _drive(monkeypatch, tmp_path, chat, endpoint, *, approved=True) -> str:
    principal = finance_principal()
    if endpoint == "approve":
        response = asyncio.run(
            chat.approve(
                chat.ApproveRequest(session_id=SESSION_ID, approved=approved),
                http_request=_http_request(principal),
            )
        )
    else:
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message="差旅报销上限是多少？", session_id=SESSION_ID),
                http_request=_http_request(principal),
            )
        )
    return asyncio.run(_consume(response))


def _drive_scenario(monkeypatch, tmp_path, scenario, endpoint, *, approved=True):
    spec = SCENARIOS[scenario]
    chat = _patch_offline(monkeypatch, tmp_path, spec["stream"], spec.get("pending"))
    for name, value in (spec.get("env") or {}).items():
        monkeypatch.setenv(name, str(value))
    return _drive(monkeypatch, tmp_path, chat, endpoint, approved=approved)


def drive_approve(monkeypatch, tmp_path, scenario, *, approved=True) -> str:
    return _drive_scenario(monkeypatch, tmp_path, scenario, "approve", approved=approved)


def drive_ask(monkeypatch, tmp_path, scenario) -> str:
    return _drive_scenario(monkeypatch, tmp_path, scenario, "ask")


def drive_approve_chunk(monkeypatch, tmp_path, chunk) -> str:
    """单条状态直驱 `/approve`，给逐行密级判定这类一次性场景用。"""
    chat = _patch_offline(monkeypatch, tmp_path, lambda *_a, **_k: iter([chunk]), None)
    return _drive(monkeypatch, tmp_path, chat, "approve")


def event_names(body: str) -> list[str]:
    return [
        line.removeprefix("event: ").strip()
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


def events(body: str) -> list[tuple[str, dict]]:
    """把每一行 `event:` 与紧跟它的 `data:` 配成一对。"""
    pairs: list[tuple[str, dict]] = []
    name = None
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and name:
            pairs.append((name, json.loads(line.removeprefix("data: "))))
            name = None
    return pairs


def canonical_names(body: str) -> list[str]:
    return [name for name in event_names(body) if name in CANONICAL_EVENTS]


def payload_of(body: str, name: str) -> dict:
    matches = [data for event, data in events(body) if event == name]
    assert len(matches) == 1, f"一轮应恰好一个 {name} 事件，实际 {len(matches)} 个"
    return matches[0]


def sources_event(body: str) -> dict:
    return payload_of(body, "sources")


# -------------------------------------------------------------------- 取证记录
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_record_approve_event_name_inventory(monkeypatch, tmp_path, scenario):
    """把每个分支实际发出的事件名按顺序写进取证文件（改动前后各跑一次）。

    输出路径由 `APPROVE_EVENT_INVENTORY_OUT` 指定；没设时跳过，免得正常跑测试的人被写出脏文件。
    """
    target = os.environ.get("APPROVE_EVENT_INVENTORY_OUT", "")
    if not target:
        pytest.skip("APPROVE_EVENT_INVENTORY_OUT not set; this test only records evidence")
    body = drive_approve(monkeypatch, tmp_path, scenario)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"scenario": scenario, "events": event_names(body)}, ensure_ascii=False) + "\n"
        )


# -------------------------------------------------------------------- 判据 ②
@pytest.mark.parametrize("scenario", sorted(BASELINE_APPROVE_EVENT_NAMES))
def test_legacy_event_names_are_a_superset_of_the_recorded_baseline(monkeypatch, tmp_path, scenario):
    """基线里的每一个事件名、每一次出现，改动后都要还在（canonical 只能加在旁边）。"""
    body = drive_approve(monkeypatch, tmp_path, scenario)
    before = Counter(BASELINE_APPROVE_EVENT_NAMES[scenario])
    after = Counter(event_names(body))
    # 正锚点：基线非空且这轮真的产出了事件，否则"没有削减"会因为两边都空而虚假成立。
    assert before, "基线为空，本用例无从判定"
    assert sum(after.values()) >= sum(before.values()) > 0, f"scenario={scenario} 的流是空的"
    missing = {name: count - after[name] for name, count in before.items() if after[name] < count}
    assert not missing, f"scenario={scenario} 丢了 legacy 事件（次数不足）: {missing}"
    assert set(before) <= set(after)


# -------------------------------------------------------------------- 判据 ①
EXPECTED_CANONICAL = {
    "completed_with_sources": ["request.started", "request.completed", "sources"],
    "completed_without_evidence": ["request.started", "request.completed", "sources"],
    "unproductive": ["request.started", "request.failed"],
    "worker_error": ["request.started", "request.failed"],
    "timeout": ["request.started", "request.failed"],
    "cancelled": ["request.started", "request.cancelled"],
    "hitl_repark": ["request.started", "request.completed", "sources"],
    "hitl_repark_no_text": ["request.started", "request.completed", "sources"],
}


@pytest.mark.parametrize("scenario", sorted(EXPECTED_CANONICAL))
def test_approve_branch_emits_the_expected_canonical_sequence(monkeypatch, tmp_path, scenario):
    body = drive_approve(monkeypatch, tmp_path, scenario)
    assert canonical_names(body) == EXPECTED_CANONICAL[scenario]


@pytest.mark.parametrize(
    ("scenario", "approved"),
    [
        ("completed_with_sources", True),
        ("unproductive", True),
        ("worker_error", True),
        ("timeout", True),
        ("cancelled", True),
    ],
)
def test_canonical_sequence_is_isomorphic_with_the_ask_branch(
    monkeypatch, tmp_path, scenario, approved
):
    """同构要实测：同一份假状态分别喂给两个端点，canonical 序列必须一字不差。"""
    approve_body = drive_approve(monkeypatch, tmp_path, scenario, approved=approved)
    ask_body = drive_ask(monkeypatch, tmp_path, scenario)
    assert canonical_names(approve_body) == canonical_names(ask_body)


@pytest.mark.parametrize("scenario", sorted(EXPECTED_CANONICAL))
def test_every_canonical_event_carries_the_envelope_and_a_contiguous_sequence(
    monkeypatch, tmp_path, scenario
):
    """信封七字段齐全、三个 id 全程一致、sequence 从 1 起连续，与 `/ask` 同一个形状。"""
    body = drive_approve(monkeypatch, tmp_path, scenario)
    canonical = [(name, data) for name, data in events(body) if name in CANONICAL_EVENTS]
    assert canonical
    ids = {(data["request_id"], data["trace_id"], data["task_id"]) for _, data in canonical}
    assert len(ids) == 1, "一轮之内的三个 id 必须自始至终是同一套"
    request_id, trace_id, task_id = ids.pop()
    assert request_id.startswith("req-")
    assert trace_id.startswith("trace-")
    assert task_id.startswith("task-")
    assert [data["sequence"] for _, data in canonical] == list(range(1, len(canonical) + 1))
    for name, data in canonical:
        for field in ("request_id", "trace_id", "task_id", "sequence", "timestamp", "status", "data"):
            assert field in data, f"{name} 缺信封字段 {field}"
        assert data["timestamp"].endswith("Z")
    assert canonical[0][0] == "request.started"
    assert canonical[0][1]["status"] == "running"


def test_canonical_sources_event_arrives_after_completed_and_before_legacy_done(monkeypatch, tmp_path):
    """顺序契约：completed → sources → legacy done，done 仍是流结束的唯一信号。"""
    names = event_names(drive_approve(monkeypatch, tmp_path, "completed_with_sources"))
    assert names.index("request.completed") < names.index("sources") < names.index("done")


# -------------------------------------------------------------------- 判据 ③
def test_sources_event_reuses_the_same_visibility_decision_as_ask(monkeypatch, tmp_path):
    """跨部门 + 跨密级各 1 条必须被拒，且文件名连 raw body 都不许出现。"""
    body = drive_approve(monkeypatch, tmp_path, "completed_with_sources")
    data = sources_event(body)["data"]
    visible = [row["source"] for row in data["sources"]]
    assert visible == [FINANCE_DOC], f"越权来源泄漏进事件: {visible}"
    assert data["hit_count"] == 1
    assert data["unauthorized_count"] == 2
    assert HR_DOC not in body
    assert SECRET_DOC not in body


@pytest.mark.parametrize(
    ("department", "classification", "expect_visible"),
    [("finance", 2, True), ("hr", 1, False), ("finance", 3, False), ("finance", None, False)],
)
def test_each_row_is_decided_by_the_same_allows_predicate_as_the_legacy_chat_path(
    monkeypatch, tmp_path, department, classification, expect_visible
):
    """把旧 `/chat` 里那句 `scope.allows(source)` 逐字复跑，比对事件内容与它一致。"""
    hit = {
        "content": "正文",
        "source": "scoped-doc.pdf",
        "chunk_index": 0,
        "classification": classification,
        "department": department,
    }
    scope = resolve_document_retrieval_scope(finance_principal())
    expected = [candidate for candidate in [hit] if scope.allows(candidate)]

    body = drive_approve_chunk(monkeypatch, tmp_path, answer_state(hits=[hit]))
    rows = sources_event(body)["data"]["sources"]
    assert [row["source"] for row in rows] == [row["source"] for row in expected], (
        f"department={department} classification={classification} 的判定与 scope.allows 不一致"
    )
    assert bool(rows) is expect_visible


def test_a_turn_that_retrieved_nothing_reports_zero_instead_of_fabricating(monkeypatch, tmp_path):
    body = drive_approve(monkeypatch, tmp_path, "completed_without_evidence")
    data = sources_event(body)["data"]
    assert data["sources"] == []
    assert data["hit_count"] == 0
    assert data["unauthorized_count"] == 0


@pytest.mark.parametrize("scenario", ["unproductive", "worker_error", "timeout", "cancelled"])
def test_a_turn_without_an_answer_emits_no_sources_event(monkeypatch, tmp_path, scenario):
    """没有产出的一轮不许有来源事件：空结果/抛错/超时/取消一律不发。

    负断言配正锚点：同一轮的 canonical 首尾事件必须真的在，否则"没发 sources"会因为
    整条流是空的而虚假通过。
    """
    names = canonical_names(drive_approve(monkeypatch, tmp_path, scenario))
    expected = EXPECTED_CANONICAL[scenario]
    assert names[:1] == expected[:1], f"scenario={scenario} 连 {expected[0]} 都没有，本断言失去意义"
    assert "sources" not in names


def test_the_timeout_branch_reports_task_timeout_and_keeps_the_legacy_error(monkeypatch, tmp_path):
    """超时限：canonical 的 error_code 与 `/ask` 同名，legacy error 原文照发。

    与 worker 抛错分成两个用例：monkeypatch 是函数级的，把 0.01s 的超时env 留给同一个
    用例的后半段会让抛错分支先撞上超时限，测到的是别的分支。
    """
    body = drive_approve(monkeypatch, tmp_path, "timeout")
    assert payload_of(body, "request.failed")["data"]["error_code"] == "task_timeout"
    assert "请求超过系统处理时限" in body
    assert canonical_names(body) == ["request.started", "request.failed"]


def test_the_worker_error_branch_reports_internal_error_and_keeps_the_legacy_error(monkeypatch, tmp_path):
    """编排线程抛错：码走 canonical，legacy error 原文照发。"""
    body = drive_approve(monkeypatch, tmp_path, "worker_error")
    assert payload_of(body, "request.failed")["data"]["error_code"] == "internal_error"
    assert "worker exploded" in body
    assert canonical_names(body) == ["request.started", "request.failed"]


def test_an_unproductive_turn_fails_instead_of_completing(monkeypatch, tmp_path):
    body = drive_approve(monkeypatch, tmp_path, "unproductive")
    payload = payload_of(body, "request.failed")
    assert payload["status"] == "failed"
    assert payload["data"]["error_code"] == "no_answer_produced"
    assert "request.completed" not in event_names(body)


# -------------------------------------------------------------------- 判据 ④
def test_approving_a_park_that_parks_again_opens_a_new_awaiting_row(monkeypatch, tmp_path):
    """注释里那条长期缺口：批准后图又停在下一个节点，账面必须记成新的 awaiting。"""
    from app.api.v1 import chat

    old = store.record_awaiting(
        SESSION_ID, "alice", ["doc"], request_id="req-old", trace_id="trace-old", task_id="task-old"
    )
    body = drive_approve(monkeypatch, tmp_path, "hitl_repark")
    completed = payload_of(body, "request.completed")
    assert completed["data"]["awaiting_hitl"] is True
    assert completed["data"]["awaiting_steps"] == ["chart"]

    pending = payload_of(body, "hitl")
    assert pending["pending"] == ["chart"]
    assert pending["labels"] == PENDING_CHART["labels"]

    rows = chat.pending_approvals._all_rows()
    assert len(rows) == 2, "闭合一条、新记一条，账面上只该多出一行"
    assert old.status == store.RESUMED, "上一轮挂起必须先闭合"
    fresh = [row for row in rows if row is not old]
    assert len(fresh) == 1
    assert fresh[0].status == store.AWAITING
    assert fresh[0].parked_steps == ["chart"]
    assert fresh[0].owner_user_id == "alice", "新待办必须记在批准人自己名下"
    assert fresh[0].request_id == completed["request_id"], "新 awaiting 行要能被这轮流事件对上号"


def test_a_park_with_no_text_is_completed_awaiting_not_failed(monkeypatch, tmp_path):
    """图停在下一个节点时本轮确实没有正文：那是等待确认，不是没产出，不许报 failed。"""
    body = drive_approve(monkeypatch, tmp_path, "hitl_repark_no_text")
    names = event_names(body)
    assert "request.failed" not in names
    assert "hitl" in names
    assert payload_of(body, "request.completed")["data"]["awaiting_hitl"] is True


def test_an_unparked_turn_sends_no_hitl_event(monkeypatch, tmp_path):
    body = drive_approve(monkeypatch, tmp_path, "completed_with_sources")
    assert "hitl" not in event_names(body)
    assert payload_of(body, "request.completed")["data"]["awaiting_hitl"] is False


# -------------------------------------------------------------------- 判据 ⑥
def test_a_stop_still_writes_abandoned_and_never_refused(monkeypatch, tmp_path):
    from app.api.v1 import chat

    old = store.record_awaiting(
        SESSION_ID, "alice", ["chart"], request_id="req-old", trace_id="trace-old", task_id="task-old"
    )
    body = drive_approve(monkeypatch, tmp_path, "cancelled")

    assert canonical_names(body) == ["request.started", "request.cancelled"]
    names = event_names(body)
    assert names.index("request.cancelled") < names.index("cancelled"), "canonical 在 legacy 之前"
    assert "refused" not in body
    assert chat.pending_approvals._all_rows() == [old]
    assert old.status == store.ABANDONED
    assert old.decided_at is not None


def test_a_refusal_still_writes_refused_and_not_abandoned(monkeypatch, tmp_path):
    old = store.record_awaiting(
        SESSION_ID, "alice", ["chart"], request_id="req-old", trace_id="trace-old", task_id="task-old"
    )
    drive_approve(monkeypatch, tmp_path, "completed_with_sources", approved=False)

    from app.api.v1 import chat

    row = chat.pending_approvals.get_row(SESSION_ID)
    assert row is not None, "账面上连行都读不回来，本断言会失去意义"
    assert row is old, "读回的不是本轮那一行"
    assert row.status == store.REFUSED
    assert old.status != store.ABANDONED, "拒绝被写成了停止"


# -------------------------------------------------------------------- 走真栈
def test_canonical_events_survive_a_real_asgi_stack(monkeypatch, tmp_path):
    """经 TestClient（进程内 ASGI，不开真端口）确认事件没被中间件/编码吞掉。"""
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common.auth import create_token, get_user
    from app.main import app

    user = get_user("admin")
    assert user, "夹具要用的 admin 必须能离线解析出来"
    registry = SessionRegistry(tmp_path / "session-registry.json")
    registry.bind(SESSION_ID, Principal.from_user(user))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", answer_stream)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: None)

    client = TestClient(app)
    response = client.post(
        "/api/v1/approve",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"session_id": SESSION_ID, "approved": True},
    )
    assert response.status_code == 200, response.text
    assert canonical_names(response.text) == ["request.started", "request.completed", "sources"]
    assert FINANCE_DOC in response.text
    assert ANSWER in response.text
