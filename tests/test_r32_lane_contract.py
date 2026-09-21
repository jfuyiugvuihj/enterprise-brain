"""R32 · 三档（问答／分析／报告）进契约：取值闸、入队判定、检索权限面、假控件禁令。

工单判据与本文件的对应关系（每条用例的 docstring 里再点名一次）：
  ① ``AskRequest.lane`` 是四值闭集，非法档 ``400`` + 稳定码            -> 第 ① 节
  ② 档位标签不得改变入队判定（R37/R42 四件既有钉必须仍绿）              -> 第 ② 节
  ③ 三档下 ``resolve_document_retrieval_scope`` 入参与命中集合逐字节相同 -> 第 ③ 节
  ④ 契约里那三行 ``gated: needs lane labels`` 不许撤，trace 也不落 lane  -> 第 ④ 节
  ⑤⑥ 客户端选档到底改了什么行为：可读数矩阵回答，并钉住"改不了就不许做控件" -> 第 ⑤⑥ 节

纪律：不打模型、不连库、不起服务。图、队列、会话库、缓存全是桩；**真**跑着的是
``/ask`` 路由本体、``AskRequest``、``_require_valid_lane`` 这道闸，以及来源事件里
``app/rag/filters.py`` 的权限计算——判据③ 要的就是后两样真的跑过。
"""
import ast
import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agents import evidence as evidence_module
from app.agents import nodes
from app.agents.contracts import ErrorEnvelope
from app.api.v1 import chat
from app.common.identity import Principal
from app.storage.sessions import SessionRegistry

REPO = Path(__file__).resolve().parents[1]
CHAT_SOURCE = REPO / "app" / "api" / "v1" / "chat.py"
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"
TRACE_DIR = REPO / "app" / "trace"
FRONTEND_SRC = REPO / "frontend" / "src"

#: R105 甲半那段的位置（按 ``## `` 标题定位，别按行号——行号会为别人的一次编辑而漂）
SLO_SECTION_TITLE = "## Three-Tier SLO Contract (2026-09-20, R105 甲半)"
GATED_CELL = "gated: needs lane labels"

SESSION = "r32-lane-session"
IDEMPOTENCY = "r32-idem-key"
#: 三档共用同一句话：判据③ 要的是"别的都不变，只有档位标签变"
MESSAGE = "差旅报销上限是多少？"
ANSWER = "财务部差旅报销上限 2000 元。"

#: 三条假命中，刻意覆盖：本部门且密级内 / 跨部门 / 本部门但超出 manager 的密级上限
FIXTURE_HITS = (
    {"content": "财务部差旅报销上限 2000 元。", "source": "travel-policy.pdf",
     "chunk_index": 0, "classification": 2, "department": "finance"},
    {"content": "HR 薪酬带宽表。", "source": "hr-salary-band.pdf",
     "chunk_index": 1, "classification": 1, "department": "hr"},
    {"content": "董事会纪要（机密）。", "source": "board-minutes.pdf",
     "chunk_index": 2, "classification": 3, "department": "finance"},
)
#: manager=2 + department=finance ⇒ 三条里只有一条看得见。钉绝对值，防"恒等于全放行"式假绿。
VISIBLE_VECTOR = (True, False, False)

_UNSET = object()


def _principal(**overrides) -> Principal:
    user = {"id": "u-r32", "username": "alice", "role": "manager", "department": "finance"}
    user.update(overrides)
    return Principal.from_user(user)


def _http_request(principal: Principal):
    return SimpleNamespace(
        state=SimpleNamespace(principal=principal, username=principal.username), headers={}
    )


def _doc_state() -> dict:
    """把三条假命中送过**真实的**证据边界，拿到与线上同形的 ``agent_results``。"""
    bag = evidence_module.new_evidence_bag()
    recorded = evidence_module.record_document_hits(bag, query=MESSAGE, hits=[dict(hit) for hit in FIXTURE_HITS])
    assert recorded == len(FIXTURE_HITS), "证据边界没收下这些命中，判据③ 的取证就是空的"
    result = evidence_module.build_agent_result(
        worker="doc", answer=ANSWER, bag=bag,
        request_id="req-r32", trace_id="trace-r32", task_id="task-r32", session_id=SESSION,
    )
    return {
        "messages": [],
        "worker_results": {"doc": ANSWER},
        "agent_results": {"doc": result.model_dump(mode="json")},
        "final_answer": ANSWER,
    }


class _FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue(self, payload, idempotency_key):
        self.calls.append({"payload": payload, "idempotency_key": idempotency_key})
        return SimpleNamespace(request_id="r32-reliable-request")


def _bytes(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _scope_snapshot(scope) -> str:
    """把一次权限判定压成可比较的字节串（NamedTuple 里有 dict 与 frozenset，不能直接 ==）。"""
    return _bytes({
        "filters": scope.filters,
        "reason_code": scope.reason_code,
        "classification_levels": sorted(scope.classification_levels),
        "departments": None if scope.departments is None else sorted(scope.departments),
    })


def _principal_dump(principal) -> str:
    return "<none>" if principal is None else _bytes(principal.model_dump(mode="json"))


def drive(monkeypatch, tmp_path, *, lane=_UNSET, switch=None, principal=None, anonymous=False, with_sources=False):
    """跑真 ``/ask``，把所有会花钱或会留下痕迹的出口换成计数器。"""
    from app.agents import orchestrator
    from app.common import reliable_queue
    from app.rag.filters import resolve_document_retrieval_scope as real_resolve_scope

    calls = SimpleNamespace(
        sessions_table=[], ensure_session=[], saved=[], model=[], graph=[], scope_args=[], scopes=[],
    )
    queue = _FakeQueue()

    def _no_model(*args, **kwargs):
        calls.model.append((args, kwargs))
        raise AssertionError("档位标签不许多花一发模型调用")

    def _record_scope(request_principal):
        calls.scope_args.append(_principal_dump(request_principal))
        scope = real_resolve_scope(request_principal)
        calls.scopes.append(scope)
        return scope

    def _stream(user_message, thread_id="default", user=None, **kwargs):
        calls.graph.append({"user_message": user_message, "kwargs": sorted(kwargs)})
        yield _doc_state() if with_sources else {
            "messages": [], "worker_results": {"doc": ANSWER}, "final_answer": ANSWER,
        }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: calls.sessions_table.append(1))
    monkeypatch.setattr(chat, "_ensure_session", lambda *args, **kwargs: calls.ensure_session.append(args))
    monkeypatch.setattr(chat, "_save_message", lambda *args, **kwargs: calls.saved.append(list(args)))
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    monkeypatch.setattr(chat, "resolve_document_retrieval_scope", _record_scope)
    monkeypatch.setattr(chat.model_handler, "chat", _no_model)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.answer_cache_origin", lambda *_a, **_k: {})
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", lambda: queue)
    monkeypatch.setattr(orchestrator, "run_with_stream", _stream)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: None)
    monkeypatch.setattr(nodes, "_make_model", _no_model)
    if hasattr(orchestrator, "_make_model"):
        monkeypatch.setattr(orchestrator, "_make_model", _no_model)
    if switch is None:
        monkeypatch.delenv(chat.REPORT_LANE_QUEUE_ENV, raising=False)
    else:
        monkeypatch.setenv(chat.REPORT_LANE_QUEUE_ENV, switch)

    fields = {"message": MESSAGE, "session_id": SESSION, "idempotency_key": IDEMPOTENCY}
    if lane is not _UNSET:
        fields["lane"] = lane
    request = chat.AskRequest(**fields)
    http_request = None if anonymous else _http_request(principal or _principal())

    status_code, detail, body = None, None, ""
    try:
        response = asyncio.run(chat.ask(request, http_request=http_request))
    except HTTPException as caught:
        status_code, detail = caught.status_code, caught.detail
    else:
        async def collect():
            parts = []
            async for chunk in response.body_iterator:
                parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
            return "".join(parts)

        body = asyncio.run(collect())

    events = _event_pairs(body)
    # canonical 信封里有 request_id/trace_id/task_id/timestamp，每一轮天然不同；判据③ 比的是
    # 信封里那个 data 身体（来源行与两个计数），所以先把身体单独拿出来压成字节。
    sources = [payload.get("data") for name, payload in events if name == "sources"]
    summary = {
        "status_code": status_code,
        "detail_code": detail.get("code") if isinstance(detail, dict) else detail,
        "model_calls": len(calls.model),
        "graph_calls": len(calls.graph),
        "enqueue_calls": len(queue.calls),
        "enqueue_lanes": [row["payload"].get("lane") for row in queue.calls],
        "enqueue_payload_keys": sorted({key for row in queue.calls for key in row["payload"]}),
        "sessions_table_calls": len(calls.sessions_table),
        "ensure_session_calls": len(calls.ensure_session),
        "saved_rows": len(calls.saved),
        "scope_calls": len(calls.scope_args),
        "event_names": [name for name, _ in events],
    }
    return SimpleNamespace(
        **summary,
        detail=detail,
        body=body,
        events=events,
        enqueue=list(queue.calls),
        graph_messages=[row["user_message"] for row in calls.graph],
        scope_args=list(calls.scope_args),
        scope_snapshots=[_scope_snapshot(scope) for scope in calls.scopes],
        scopes=list(calls.scopes),
        saved=list(calls.saved),
        sources_data=sources[0] if sources else None,
        sources_payload=None if not sources else _bytes(sources[0]).encode("utf-8"),
        summary=lambda: dict(summary),
    )


def _event_pairs(body: str):
    pairs, name = [], None
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line[len("event: "):].strip()
        elif line.startswith("data: ") and name:
            pairs.append((name, json.loads(line[len("data: "):])))
            name = None
    return pairs


def _contract_text() -> str:
    return CONTRACT_DOC.read_text(encoding="utf-8")


def _slo_section() -> str:
    text = _contract_text()
    start = text.index(SLO_SECTION_TITLE)
    following = re.compile(r"^## ", re.MULTILINE).search(text, start + len(SLO_SECTION_TITLE))
    return text[start: following.start() if following else len(text)]


def _table_rows(section: str, *, cells: int):
    rows = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        found = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(found) == cells:
            rows.append(found)
    return rows


def _chat_tree() -> ast.Module:
    return ast.parse(CHAT_SOURCE.read_text(encoding="utf-8"))


def _junk_detail(lane: str = "REPORT") -> dict:
    """不经 HTTP 外壳，直接构造非法档的 400 身体（同一个函数、同一个分支）。"""
    try:
        chat._require_valid_lane(chat.AskRequest(message=MESSAGE, lane=lane))
    except HTTPException as caught:
        assert caught.status_code == 400
        return caught.detail
    raise AssertionError(f"_require_valid_lane 竟然放行了 {lane!r}")


# ==================== 判据①：四值闭集，非法档当场 400 ====================

#: 契约与 chat.py 必须同时认这四个值：多一个是开洞，少一个是撤档。
ALLOWED_ON_THE_WIRE = ("", "qa", "analysis", "report")
#: 十四枚 junk：大小写变体、拼接、中文档位名、长得像布尔的字面量——从前全部静默忽略。
JUNK_LANES = ("REPORT", "QA", "Qa", "qa-", "qa x", "analysis,qa", "报告", "问答", "chat", "auto",
              "fast", "false", "0", "report lane")


def test_the_lane_field_is_a_closed_set_of_three_tiers_plus_empty():
    """判据①：取值集合恰是 {"" , qa , analysis , report}，而不是"任何字符串"。"""
    assert set(chat.ASK_LANE_VALUES) == set(ALLOWED_ON_THE_WIRE)
    assert (chat.LANE_QA, chat.LANE_ANALYSIS, chat.LANE_REPORT) == ("qa", "analysis", "report")
    assert "" in chat.ASK_LANE_VALUES


def test_the_second_lane_spelling_cannot_drift_from_the_discriminator():
    """chat.py 那份档位名是第二次落地（R37 的规矩：不抓并发同事的私有名）——钉两份相等。"""
    assert chat.LANE_QA == nodes.LANE_QA
    assert chat.LANE_ANALYSIS == nodes.LANE_ANALYSIS
    assert chat.LANE_REPORT == nodes.LANE_REPORT
    assert set(chat.ASK_LANE_VALUES) - {""} == set(nodes.LANE_TIERS), "R42 加了第四档而闸没跟上"


@pytest.mark.parametrize("lane", ALLOWED_ON_THE_WIRE)
def test_a_declared_tier_is_accepted_and_still_runs_in_person(monkeypatch, tmp_path, lane):
    """判据①：四值都放行；开关关着时，三档与"不声明"走同一条在场道。"""
    run = drive(monkeypatch, tmp_path, lane=lane)

    assert run.detail is None, run.detail
    assert run.enqueue_calls == 0
    assert run.graph_calls == 1
    assert run.graph_messages == [MESSAGE], "放行不等于改写：问题文本一个字都不许动"


@pytest.mark.parametrize("lane", JUNK_LANES)
def test_an_unknown_tier_is_refused_with_the_ratified_stable_code(monkeypatch, tmp_path, lane):
    """判据①：非法档 400，码走封闭枚举（复用既有的 validation_error，本单不造新码名）。"""
    run = drive(monkeypatch, tmp_path, lane=lane)

    assert run.status_code == 400, (lane, run.status_code)
    assert run.detail["code"] == chat.LANE_ERROR_CODE == "validation_error"
    assert run.graph_calls == 0 and run.enqueue == []


@pytest.mark.parametrize("lane", JUNK_LANES)
def test_the_refusal_leaves_no_session_row_queue_entry_or_model_call(monkeypatch, tmp_path, lane):
    """判据①的副作用面：闸跑在建表、绑会话、落库、入队、模型之前，非法档留下零痕迹。"""
    run = drive(monkeypatch, tmp_path, lane=lane, switch="1")

    assert run.sessions_table_calls == 0, lane
    assert run.ensure_session_calls == 0, lane
    assert run.saved_rows == 0, lane
    assert run.enqueue_calls == 0, lane
    assert run.graph_calls == 0, lane
    assert run.model_calls == 0, lane
    assert run.scope_calls == 0, lane


def test_the_error_body_is_a_valid_envelope_and_names_the_field():
    """判据①的形状面：身体过得了封闭枚举，details 说得出哪个字段、允许哪些值、收到了什么。"""
    envelope = ErrorEnvelope(**_junk_detail())

    assert envelope.code == "validation_error"
    assert envelope.retryable is False
    assert envelope.details["field"] == "lane"
    assert envelope.details["allowed"] == list(chat.ASK_LANE_VALUES)
    assert envelope.details["given"] == "REPORT"


@pytest.mark.parametrize("lane", ["  ", "", " qa ", "report\t"])
def test_whitespace_alone_declares_nothing(monkeypatch, tmp_path, lane):
    """带空白的写法先 strip 再判：``"   "`` 与 ``""`` 同解，与 ``_queue_lane`` 口径一致。"""
    run = drive(monkeypatch, tmp_path, lane=lane)

    assert run.detail is None, lane
    assert run.graph_calls == 1, lane


def test_a_wrongly_typed_lane_is_the_request_models_job_not_this_gates():
    """类型层面（lane 不是字符串）仍由 pydantic 拒：与仓内所有 str 字段同一个 422 口径。

    本单**不**为了把类型错误也拧成 400 而把字段退化成 ``Any``——那会让契约里的
    ``lane: str`` 变成假话，也会改掉 R37 那枚"字段是可选字符串"的既有断言。
    """
    with pytest.raises(ValidationError):
        chat.AskRequest(message=MESSAGE, lane=7)
    with pytest.raises(ValidationError):
        chat.AskRequest(message=MESSAGE, lane=["qa"])


def test_the_gate_answers_401_before_it_answers_400(monkeypatch, tmp_path):
    """未鉴权者不许靠一个非法档位探服务端的取值集合：顺序是安全属性，不是风格。"""
    run = drive(monkeypatch, tmp_path, lane="chaos-not-a-tier", anonymous=True)

    assert run.status_code == 401, run.status_code
    assert run.saved_rows == 0


def test_the_wire_default_is_declare_nothing_not_qa():
    """老调用方一个字都不用改：默认值仍是空串，而空串**不等于**问答档。"""
    assert chat.AskRequest(message=MESSAGE).lane == ""
    assert "" in chat.ASK_LANE_VALUES
    assert nodes.LANE_QA != "", "把空串解释成 qa 就是替调用方猜心思：R42 可能把这句判到分析档"


# ==================== 判据②：档位标签不得改变入队判定 ====================


@pytest.mark.parametrize("switch", [None, "1"])
@pytest.mark.parametrize("lane", ["", "qa", "analysis"])
def test_a_non_report_label_never_enters_the_queue(monkeypatch, tmp_path, lane, switch):
    """判据②的正体：进不进队列只由 (档位==report, 开关) 决定，与另外两档无关。"""
    run = drive(monkeypatch, tmp_path, lane=lane, switch=switch)

    assert run.enqueue == [], (switch, lane)
    assert run.graph_calls == 1, (switch, lane)


def test_the_report_label_still_owns_the_only_real_queue_route(monkeypatch, tmp_path):
    """对照组：开关开时 report 确实入队——否则上面那枚"从不入队"是空转出来的。"""
    run = drive(monkeypatch, tmp_path, lane="report", switch="1")

    assert run.graph_calls == 0
    assert run.enqueue_lanes == ["report"]
    assert run.enqueue[0]["payload"]["write_back_session"] is True
    assert run.enqueue[0]["idempotency_key"] == IDEMPOTENCY


@pytest.mark.parametrize("lane", ["", "qa", "analysis"])
def test_a_non_report_turn_completes_in_person_and_publishes_no_queue_receipt(monkeypatch, tmp_path, lane):
    """三档的在场路径自己会说话：走完 request.completed，载荷里根本不存在 lane 字段。"""
    run = drive(monkeypatch, tmp_path, lane=lane, switch="1")

    assert run.enqueue_calls == 0, lane
    assert run.event_names.count("request.completed") == 1, lane


def test_an_illegal_label_never_reaches_the_queue_even_with_the_switch_on(monkeypatch, tmp_path):
    """反证②的第二把：非法档不返 400 的话，这一枚就地红。"""
    run = drive(monkeypatch, tmp_path, lane="Report", switch="1")

    assert run.status_code == 400
    assert run.enqueue == []


def test_the_gate_and_the_queue_predicate_do_not_call_each_other():
    """结构面：校验闸不改判别，判别也不越权校验——两枚函数互不调用。"""
    bodies = {
        node.name: {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        }
        for node in ast.walk(_chat_tree())
        if isinstance(node, ast.FunctionDef)
    }

    assert "_queue_lane" not in bodies["_require_valid_lane"]
    assert "_require_valid_lane" not in bodies["_queue_lane"]

# ==================== 判据③：同一题在三档下的检索权限面逐字节相同 ====================


def _allows_vector(scope) -> tuple:
    """用真谓词把三条假命中各判一次——"命中集合"的算法面，不看响应文案。"""
    return tuple(scope.allows(dict(hit)) for hit in FIXTURE_HITS)


def test_the_three_tiers_ask_for_the_same_authorization_scope_in_the_same_way(monkeypatch, tmp_path):
    """判据③：入参、判定结果、发出去的来源集合，四档之间一个字节都不许多。"""
    observed = {
        lane: drive(monkeypatch, tmp_path, lane=lane, with_sources=True)
        for lane in ALLOWED_ON_THE_WIRE
    }
    base = observed[""]

    assert [run.status_code for run in observed.values()] == [None] * len(ALLOWED_ON_THE_WIRE)
    assert base.scope_calls >= 1, "这一轮根本没走到权限判定，后面的比较是空的"
    for lane, run in observed.items():
        assert run.scope_args == base.scope_args, f"{lane} 档给 scope 换了入参"
        assert run.scope_snapshots == base.scope_snapshots, f"{lane} 档算出了另一个权限范围"
        assert run.sources_payload == base.sources_payload, f"{lane} 档发出去的来源不同"
        assert _allows_vector(run.scopes[0]) == _allows_vector(base.scopes[0]), lane


def test_the_visible_hit_set_is_the_one_this_principal_is_entitled_to(monkeypatch, tmp_path):
    """判据③的绝对值：三档相同还不够，必须相同在"看得见一条"上，防"恒等于全放行"式假绿。"""
    run = drive(monkeypatch, tmp_path, lane="analysis", with_sources=True)

    assert _allows_vector(run.scopes[0]) == VISIBLE_VECTOR
    data = run.sources_data
    assert data["hit_count"] == 1, data
    assert data["unauthorized_count"] == 2, data
    assert data["scope_reason_code"] == run.scopes[0].reason_code


def test_the_scope_recorder_can_tell_two_principals_apart(monkeypatch, tmp_path):
    """对照组：换一个真会改变权限的输入，快照与来源都必须不同——否则上面那枚相等是恒真。"""
    manager = drive(monkeypatch, tmp_path, lane="qa", with_sources=True)
    other = drive(monkeypatch, tmp_path, lane="qa", with_sources=True,
                  principal=_principal(role="staff", department="hr"))

    assert other.scope_snapshots != manager.scope_snapshots, "recorder 或 scope 已经瞎了"
    assert other.sources_payload != manager.sources_payload


# ==================== 判据④：那三行 gated 不许撤，lane 也不许被本单顺手落进 trace ====================


def test_the_three_end_to_end_slots_are_still_gated_on_lane_labels():
    """④：三档的端到端槽位仍写着 gated: needs lane labels——撤它的前提今天不成立。"""
    rows = [row for row in _table_rows(_slo_section(), cells=5) if row[0].strip("`") in ALLOWED_ON_THE_WIRE[1:]]
    assert len(rows) == 6, rows  # qa×3 + analysis×2 + report×1（R105 甲半那张表）

    gated = [row for row in rows if GATED_CELL in row[3]]
    assert len(gated) == 3, [[row[0], row[3]] for row in rows]
    assert {row[0].strip("`") for row in gated} == {"qa", "analysis", "report"}
    assert all("end_to_end_p95_ms" in row[1] for row in gated), "被 gated 的必须是端到端那一枚，别拿别的槽位凑数"
    assert _contract_text().count(GATED_CELL) == 3, "全文件里这五个字只许出现在那三行"


def test_this_ticket_left_no_lane_on_the_trace_layer():
    """④ 的实证面：全仓 trace 里 "lane" 出现 0 次，spans 的那条 record_stage_sample 也不带 lane=。"""
    sources = sorted(TRACE_DIR.rglob("*.py"))
    assert sources, "app/trace 不见了，这条钉要先改指向"
    hits = [path.relative_to(REPO).as_posix() for path in sources if "lane" in path.read_text(encoding="utf-8")]
    assert hits == [], "trace 层出现了 lane：那是 §28.5 的跟进单该做的事，本单不许顺手做，但 gated 三行仍不许撤"

    tree = ast.parse((TRACE_DIR / "spans.py").read_text(encoding="utf-8"))
    stage_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "record_stage_sample"
    ]
    assert stage_calls, "spans.py 不再调 record_stage_sample：契约里那条 blocker 的指向要先改"
    assert all("lane" not in {keyword.arg for keyword in call.keywords} for call in stage_calls)


def test_the_contract_still_names_the_lane_attribution_blocker():
    """④：blocker 的名字也要留着——它和那三行 gated 是同一句话的两种写法。"""
    text = _contract_text()

    assert "lane_attribution_absent" in text
    assert "app/trace/spans.py" in text


def test_the_prose_line_about_the_lane_field_tells_todays_truth():
    """①/⑥ 的散文面：契约不许再写"非法档不返 400"是现在时，也不许把三档说成已生效。"""
    text = _contract_text()

    assert "closed set of four" in text, "契约不再写 lane 的取值闭集了"
    assert "validation_error" in text, "契约不再指名非法档的稳定码"
    assert "still ships no tier selector" in text, "契约不再交代前端为什么没有选择器"
    for position in [match.start() for match in re.finditer(r"is not\s+implemented", text)]:
        window = re.sub(r"\s+", " ", text[max(0, position - 240) : position + 40])
        assert "previous draft" in window, "契约又把「非法档不返 400」写成现在时的缺口了"


# ==================== 判据⑤⑥：客户端选档到底改了什么行为（可读数） ====================


def test_the_client_label_changes_exactly_one_behaviour_and_it_is_default_off(monkeypatch, tmp_path):
    """⑥：四档 × 两开关态，逐维度比可读数——qa/analysis 与"不声明"必须处处相同。"""
    cells = {
        (switch, lane): drive(monkeypatch, tmp_path, lane=lane, switch=switch, with_sources=True).summary()
        for switch in (None, "1")
        for lane in ALLOWED_ON_THE_WIRE
    }
    dimensions = sorted(cells[(None, "")])

    # 维度 A：模型开销。八格全 0 ⇒ 选档不买任何一次调用。
    assert {cell["model_calls"] for cell in cells.values()} == {0}
    # 维度 B：qa / analysis 与"不声明"在**每一个**维度上相等（含 event 序列、入队、来源次数）。
    for switch in (None, "1"):
        for lane in ("qa", "analysis"):
            assert cells[(switch, lane)] == cells[(switch, "")], (switch, lane, dimensions)
    # 维度 C：唯一会变的那一条——report 且开关打开。
    assert cells[(None, "report")] == cells[(None, "")], "开关关时报告档与不声明必须同路"
    assert cells[("1", "report")] != cells[("1", "")], "开关开时 report 该有区别，否则这条道是假的"
    assert cells[("1", "report")]["enqueue_calls"] == 1
    assert cells[("1", "report")]["graph_calls"] == 0
    assert cells[("1", "")]["enqueue_calls"] == 0 and cells[("1", "")]["graph_calls"] == 1


def test_nothing_outside_the_two_lane_functions_reads_the_request_label():
    """⑥ 的结构证据：全 chat.py 里读 request.lane 的只有两枚函数，没有第三处把它喂给图或检索。"""
    readers = set()
    for node in ast.walk(_chat_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            direct = isinstance(inner, ast.Attribute) and inner.attr == "lane"
            via_getattr = (
                isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
                and inner.func.id == "getattr" and len(inner.args) > 1
                and isinstance(inner.args[1], ast.Constant) and inner.args[1].value == "lane"
            )
            if direct or via_getattr:
                readers.add(node.name)

    assert readers == {"_queue_lane", "_require_valid_lane"}, readers


def test_the_gate_is_called_once_and_before_the_store(monkeypatch, tmp_path):
    """①的落点面：闸在 /ask 里恰好调一次，且位置在建表与落库之前。"""
    source = CHAT_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    route = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ask"
    )
    calls = {
        node.func.id: node.lineno
        for node in ast.walk(route)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert source.count("_require_valid_lane(") == 2, "定义之外只许一处调用"
    assert calls["_require_valid_lane"] < calls["_ensure_sessions_table"] < calls["_save_message"]


def test_the_model_counters_have_teeth(monkeypatch, tmp_path):
    """反空转：两处模型入口都是"一被调用就抛"的活桩，矩阵里的 0 不是默认值。"""
    drive(monkeypatch, tmp_path, lane="qa")

    with pytest.raises(AssertionError, match="不许多花一发模型"):
        nodes._make_model()
    with pytest.raises(AssertionError, match="不许多花一发模型"):
        chat.model_handler.chat(messages=[{"role": "user", "content": "x"}])


def test_the_frontend_ships_no_tier_selector_while_the_label_is_inert():
    """⑥ 假控件禁令（这条比做出来更重要）：改不了任何行为的控件就是假料壳。

    今天前端一个 lane 都不发。这枚钉**该被改掉**而不是被绕过的那一天，是 qa/analysis 在
    /ask 上真分出轻重的那一天——那要动 ``app/agents/nodes.py`` 与 orchestrator 的写域，
    在本单之外（已具名报总控）。到那一天连同控件一起评审。
    """
    files = [path for path in FRONTEND_SRC.rglob("*") if path.suffix in {".vue", ".js", ".ts"}]
    assert len(files) > 20, f"只读到 {len(files)} 枚前端源文件，本钉已经空转"

    hits = [
        path.relative_to(REPO).as_posix() for path in files
        if re.search(r"\blane\b", path.read_text(encoding="utf-8"), re.IGNORECASE)
    ]
    assert hits == [], f"前端开始发档位了：{hits} —— 先证明服务端认，再谈控件"


def test_the_four_hundred_renders_honestly_on_the_client_without_new_frontend():
    """⑤：非法档的人话文案不需要新前端件——errcodes.js 里 validation_error 早就是真源之一。"""
    text = (FRONTEND_SRC / "lib" / "errcodes.js").read_text(encoding="utf-8")

    assert re.search(r"^\s*validation_error:\s*\{\s*message:\s*'[^']+',", text, re.MULTILINE), \
        "前端没有 validation_error 的人话句，400 会渲染成裸码"
    assert "400: 'validation_error'" in text, "HTTP 400 不再映射到 validation_error，这条 400 会走兜底文案"