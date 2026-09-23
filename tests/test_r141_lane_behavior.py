"""R141 · 档位标签真的改变路径（后端半）。

题面一句话：R32 拒交前端选择器，理由是「要让标签真改变行为，得动 nodes.py 与
orchestrator.py，两者皆在写域外」。今天那两枚文件空了，本单把那一格补成
**行为差 + 读数**两件事，两件事都要能机器验证。

三档的行为差（判据①，逐格对应用例）：
  问答档   只允许 doc 一条腿；不付拆题那一发；supervisor 要派 chart/export 也照砍。
  分析档   允许 doc/data/chart，砍 export；本轮带了数据文件就**必须**派 data（地板）。
  报告档   四条腿全允许，且**无条件补 export**（地板）——题目里没写"导出"二字也要补。
  不声明   图内没有任何天花板/地板，路径与 R141 之前逐字节相同（判据② 的另一半）。

读数（判据① 要的"读数而不是散文"）：lane_source ∈ {r42, explicit, not_routed, resumed}
四处出口同源一份：HTTP 响应头、canonical 的 request.started 帧、trace 的 request.started
载荷、以及本文件直接调 resolve_turn_lane 的返回值。

全程离线：零模型往返（``_make_model`` 是被调即抛的活桩）、零 socket（R56 那道
``blocked connect attempts to host model port`` 必须仍是 0）、零数据库（会话与文档落库
全部顶掉）、零 HTTP 服务（直接 await 协程函数，读 ``body_iterator``）。
"""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Send

from app.agents import nodes, orchestrator
from app.agents.nodes import (
    DECLARED_LANE_KEY,
    LANE_EXEMPT_WORKERS,
    LANE_PRIMARY_LEG,
    LANE_QA,
    LANE_ANALYSIS,
    LANE_REPORT,
    LANE_REQUIRED_WORKERS,
    LANE_SOURCE_EXPLICIT,
    LANE_SOURCE_NOT_ROUTED,
    LANE_SOURCE_R42,
    LANE_SOURCE_RESUMED,
    LANE_WORKERS,
    WORK_LEGS,
    decide_workers,
    not_routed_lane,
    resolve_turn_lane,
    resumed_lane,
)
from app.api.v1 import chat
from app.common.identity import Principal
from app.storage.sessions import SessionRegistry

REPO = Path(__file__).resolve().parents[1]
CHAT_SOURCE = REPO / "app" / "api" / "v1" / "chat.py"

SESSION = "r141-session"
IDEMPOTENCY = "r141-idem"
#: 一句"重问题"：R42 判别器会把它判到分析档，因此三档声明里只有问答档会**改**它的道。
#: 判据① 要的就是这一格反差：同一句话，只换档位标签。
HEAVY = "把各季度营收统计出来并且画成柱状图"
#: 一句轻问题：判别器判问答档，声明报告档则必须**多**出 export 腿。
LIGHT = "住宿费标准是多少？"
ANSWER = "住宿费凭发票据实报销，单晚上限 500 元。"

#: 每档允许的腿（判据① 的第一格：这张表与 nodes.LANE_WORKERS 同值就是分流的方向）
_CEILINGS = {
    LANE_QA: ("doc",),
    LANE_ANALYSIS: ("doc", "data", "chart"),
    LANE_REPORT: ("doc", "data", "chart", "export"),
}


def _principal(**overrides) -> Principal:
    user = {"id": "u-r141", "username": "alice", "role": "manager", "department": "finance"}
    user.update(overrides)
    return Principal.from_user(user)


def _http_request(principal: Principal):
    return SimpleNamespace(
        state=SimpleNamespace(principal=principal, username=principal.username), headers={}
    )


def _config(declared=None, **extra):
    """造一枚与 run_with_stream 同形的 config（没声明时连键都不加，与图内一致）。"""
    configurable = {"thread_id": SESSION, **extra}
    if declared:
        configurable[DECLARED_LANE_KEY] = declared
    return {"configurable": configurable}


def _dispatch_state(question, workers, answer=""):
    msg = AIMessage(
        content=answer,
        tool_calls=[{"name": "dispatch", "args": {"workers": list(workers)}, "id": "call-1"}]
        if workers else [],
    )
    return {"messages": [HumanMessage(content=question), msg], "plan": [], "worker_results": {}}


def _routed(state, config):
    """跑真的 route_main，只取它派出去的腿名（"reflect" 原样回传）。"""
    out = orchestrator.route_main(state, config)
    if isinstance(out, str):
        return out
    return [node.node for node in out if isinstance(node, Send)]


# ==================== A 组 · 腿的有无（判据① 的第一格） ====================


@pytest.mark.parametrize("lane", [LANE_QA, LANE_ANALYSIS, LANE_REPORT])
def test_every_declared_tier_owns_a_named_ceiling_of_legs(lane):
    """天花板必须是**具名腿的表**，不是一句形容词——读数里读不到腿就等于没有分流。"""
    turn = resolve_turn_lane(HEAVY, lane)

    assert turn.source == LANE_SOURCE_EXPLICIT
    assert turn.lane == lane
    assert turn.allowed_workers == LANE_WORKERS[lane] + LANE_EXEMPT_WORKERS
    assert turn.allowed_workers[: len(_CEILINGS[lane])] == _CEILINGS[lane]


def test_the_ceilings_form_a_monotone_ladder_downwards():
    """往便宜档选 = 少付。这条不成立就说明档位是并列的口味而不是阶梯（判据④ 的方向）。"""
    assert set(LANE_WORKERS[LANE_QA]) < set(LANE_WORKERS[LANE_ANALYSIS]) < set(LANE_WORKERS[LANE_REPORT])
    assert set(LANE_WORKERS[LANE_REPORT]) == set(WORK_LEGS)


def test_declaring_qa_cuts_every_heavy_leg_from_the_dispatch():
    turn = resolve_turn_lane(HEAVY, LANE_QA)

    kept, cut, added = decide_workers(turn, ["doc", "data", "chart", "export"])

    assert kept == ("doc",)
    assert cut == ("data", "chart", "export")
    assert added == ()


def test_declaring_analysis_cuts_export_but_keeps_the_read_and_compute_legs():
    turn = resolve_turn_lane(HEAVY, LANE_ANALYSIS)

    kept, cut, _added = decide_workers(turn, ["doc", "data", "chart", "export"])

    assert kept == ("doc", "data", "chart")
    assert cut == ("export",)


def test_declaring_report_cuts_nothing_and_adds_nothing_when_the_legs_are_already_there():
    turn = resolve_turn_lane(HEAVY, LANE_REPORT)

    kept, cut, added = decide_workers(turn, ["doc", "data", "chart", "export"])

    assert kept == ("doc", "data", "chart", "export")
    assert cut == () and added == ()


@pytest.mark.parametrize("lane", ["", "   ", None])
def test_an_undeclared_turn_cuts_and_adds_nothing(lane):
    """判据② 的行为半：没声明就是 R141 之前那条路，一个字符都不许多改。"""
    turn = resolve_turn_lane(HEAVY, lane)

    kept, cut, added = decide_workers(turn, ["doc", "data", "chart", "export"])

    assert turn.source == LANE_SOURCE_R42
    assert (kept, cut, added) == (("doc", "data", "chart", "export"), (), ())


def test_the_report_floor_adds_export_even_when_the_question_never_asks_for_a_file():
    """地板存在的理由：只有天花板时，"选报告档"在一句不含导出词的题上什么都不改变，
    那正是 R32 拒交选择器的那张脸。"""
    turn = resolve_turn_lane(LIGHT, LANE_REPORT)

    kept, cut, added = decide_workers(turn, ["doc"])

    assert added == ("export",)
    assert kept == ("doc", "export")
    assert cut == ()


@pytest.mark.parametrize("has_data,expected", [(True, ("data",)), (False, ())])
def test_the_analysis_floor_adds_data_only_when_there_is_a_data_file(has_data, expected):
    """没料硬派 pandas 是编造数字，不是分流：地板条件 has_data 就是这条边界。"""
    turn = resolve_turn_lane(HEAVY, LANE_ANALYSIS)

    _kept, _cut, added = decide_workers(turn, ["doc"], has_data=has_data)

    assert added == expected


def test_the_qa_floor_refuses_the_empty_round_but_not_an_answered_one():
    """abstained 条件：supervisor 弃权且没给正文 ⇒ 补一条读腿（与 R42 那句补派同一触发）；
    已经答完的轮次不许多花一发模型。"""
    turn = resolve_turn_lane(LIGHT, LANE_QA)

    assert decide_workers(turn, [], abstained=True)[2] == ("doc",)
    assert decide_workers(turn, [], abstained=False) == ((), (), ())


def test_cutting_every_leg_still_delivers_the_cheapest_read_instead_of_a_dead_round():
    """砍到零不许变成"什么都不做"：route_main 在 workers 为空时 return "reflect"，
    那会再烧一发 supervisor —— 恰恰是 R42 省掉的那种空转。"""
    turn = resolve_turn_lane("把上季度经营情况导出成 PDF 报告", LANE_QA)

    kept, cut, added = decide_workers(turn, ["export"])

    assert kept == added == (LANE_PRIMARY_LEG,)
    assert cut == ("export",)


def test_approval_is_never_inside_a_ceiling():
    """批准闸不是工作腿：把它关进任何一档，等于"选问答档 ⇒ 待确认卡消失"。"""
    for lane in (LANE_QA, LANE_ANALYSIS, LANE_REPORT):
        kept, cut, _added = decide_workers(resolve_turn_lane(HEAVY, lane), ["doc", "approval"])
        assert "approval" in kept, lane
        assert "approval" not in cut, lane
        # 报告档的地板会另外补 export，那一格由上面的地板用例管，这里不比全表。
        assert kept[:2] == ("doc", "approval"), lane
        assert cut == (), lane


def test_the_floor_table_only_uses_conditions_the_code_understands():
    """地板表写错一格条件名就要当场炸，而不是静默少补一条腿。"""
    turn = resolve_turn_lane(HEAVY, LANE_REPORT)
    broken = nodes.TurnLane(**{**turn.__dict__, "required_workers": (("export", "alwayz"),)})

    with pytest.raises(ValueError, match="unknown floor condition"):
        decide_workers(broken, ["doc"])


# ==================== B 组 · 三态与未知值（判据②） ====================


def test_the_four_readout_states_are_pairwise_distinguishable():
    """判据②：缺省 / 显式 / 没走图 / 批准后续跑，四格读数两两不同，且都不是"未知值"。"""
    readouts = {
        resolve_turn_lane(HEAVY, "").source,
        resolve_turn_lane(HEAVY, LANE_QA).source,
        not_routed_lane(LANE_REPORT).source,
        resumed_lane().source,
    }

    assert readouts == {LANE_SOURCE_R42, LANE_SOURCE_EXPLICIT, LANE_SOURCE_NOT_ROUTED, LANE_SOURCE_RESUMED}


@pytest.mark.parametrize("junk", ["REPORT", "repot", "chat", "问答", "qa report"])
def test_an_unknown_tier_fails_loudly_instead_of_becoming_undeclared(junk):
    """图内守门：拼错的档位绝不许静默降级成"没声明"。

    那是最贵的一种第三态——调用方以为选了档，路径照旧，而读数会说"系统判的"。
    """
    with pytest.raises(ValueError, match="unknown declared lane"):
        resolve_turn_lane(HEAVY, junk)


def test_a_not_routed_turn_keeps_the_declaration_but_claims_no_effect():
    """入队/缓存命中那一轮：声明留着（那是给 worker 或排障的交代），lane 读空串。"""
    readout = not_routed_lane(LANE_REPORT).as_dict()

    assert readout["lane"] == "" and readout["declared_lane"] == LANE_REPORT
    assert readout["lane_source"] == LANE_SOURCE_NOT_ROUTED
    assert readout["allowed_workers"] == []


def test_a_resumed_turn_does_not_claim_a_declaration_the_ledger_does_not_hold():
    """账上没这一格时（旧行、0008 尚无此列的 PG 后端、本轮压根没声明），resumed 的
    declared 必须是空串。

    这句在 R141 当时是"原始声明跨不过 HITL 那道门"，R172 把那条腿接上了：声明随挂起行
    存下来、批准后续跑轮读回来，于是这一枚钉的是**读不到**的那一侧 —— 读不到就明说读不到，
    补成一档就是"读数替缺口遮丑"。读得到的那一侧由
    tests/test_r172_lane_across_hitl.py 端到端钉（三处出口逐字同一份读数）。
    """
    readout = resumed_lane().as_dict()

    assert readout["declared_lane"] == ""
    assert readout["lane_source"] == LANE_SOURCE_RESUMED


def test_the_readout_is_json_safe_for_the_trace_and_sse_outlets():
    """trace 载荷走 json.dumps，SSE 帧也是：任何一格不可序列化就是线上炸。"""
    payload = json.dumps(resolve_turn_lane(HEAVY, LANE_REPORT).as_dict(), ensure_ascii=False)

    assert '"lane_source": "explicit"' in payload


# ==================== C 组 · 那一发拆题模型的付与不付（真花钱的行为差） ====================


class _ModelSpy:
    """被调即记账的模型工厂：plan() 的 MODEL 出入口只有 ``_make_model``。"""

    def __init__(self):
        self.calls = []

    def __call__(self, tier=object(), **_kwargs):
        self.calls.append(getattr(tier, "value", str(tier)))
        return self

    def invoke(self, _messages):
        return SimpleNamespace(content="[]")


@pytest.fixture
def plan_probe(monkeypatch):
    """把确定性计划顶空，让控制流真走到 plan() 的档位闸门。

    为什么可以顶：build_task_plan 命中它会就地 return，压根到不了闸门（现场量过：
    本题面族全部命中确定性计划）。闸门本身要测的是"这一发拆题模型付不付"，
    与计划器怎么排任务是两件事，见 tests/test_r42_zero_model_calls.py 用同一手法。
    """
    spy = _ModelSpy()
    monkeypatch.setattr(nodes, "_make_model", spy)
    monkeypatch.setattr(nodes, "build_task_plan", lambda _q: [])
    return spy


# "不声明"在 HEAVY 上照付：R42 判别器把它判到分析档，闸门本来就不放行。
@pytest.mark.parametrize(
    "declared,expect_paid",
    [("", True), (LANE_QA, False), (LANE_ANALYSIS, True), (LANE_REPORT, True)],
)
def test_only_the_qa_tier_refuses_the_splitting_model_call(plan_probe, declared, expect_paid):
    """判据① 的钱袋子那一格：选了问答档就真的少打一发模型，另两档照付。

    对照基准是 HEAVY：R42 判别器把它判到分析档，所以"不声明"与"声明分析档"在这里
    必须同价；只有声明问答档时才免付。
    """
    result = nodes.plan({"messages": [HumanMessage(content=HEAVY)]}, _config(declared or None))

    assert result == {"plan": []}
    assert (plan_probe.calls == ["plan"]) is expect_paid, plan_probe.calls


def test_the_plan_gate_keeps_the_r42_log_anchors_byte_identical(plan_probe, monkeypatch):
    """判据④ 的前置：R51 读表靠 ``[R42]`` 与 ``[Plan] 问答档 → 不拆题`` 两枚锚点。

    本单改了 plan() 的闸门写法，锚点字面与频次必须一字不动 —— 这两枚 pattern 是
    app/common/stage_timing.py 逐字节钉着的，谁的口径都不许被"顺手改文案"带走。
    """
    from app.common import stage_timing

    logged = []

    class _Recorder:
        def info(self, message, *args):
            logged.append(str(message) % args if args else str(message))

        warning = info

    monkeypatch.setattr(nodes, "logger", _Recorder())
    nodes.plan({"messages": [HumanMessage(content=HEAVY)]}, _config(LANE_QA))
    text = "\n".join(logged)

    assert stage_timing.R42_LOG_PATTERN.search(text), logged
    assert stage_timing.R42_PLAN_SKIP_PATTERN.search(text), logged
    assert len([line for line in logged if line.startswith("[R42]")]) == 1, (
        "一次 plan() 敲两枚 [R42] 钟：R51 的 lane 归组会跟着漂"
    )


def test_resolve_turn_lane_never_logs_the_r42_anchor(monkeypatch):
    """读数用的是规则本体，不是 classify_route：它一次都不该替 R42 敲钟。"""
    logged = []

    class _Recorder:
        def info(self, message, *args):
            logged.append(str(message))

        warning = info

    monkeypatch.setattr(nodes, "logger", _Recorder())
    for declared in ("", LANE_QA, LANE_ANALYSIS, LANE_REPORT):
        resolve_turn_lane(HEAVY, declared)

    assert logged == [], logged


# ==================== D 组 · 派发真的不同（跑真的 route_main） ====================


def test_a_declared_qa_turn_never_dispatches_the_heavy_legs():
    """supervisor 派了 data+chart，声明问答档 ⇒ 出门的只有 doc（砍腿具名可读）。"""
    routed = _routed(_dispatch_state(HEAVY, ["data", "chart"]), _config(LANE_QA))

    assert routed == ["doc"]


def test_a_declared_analysis_turn_keeps_compute_but_drops_the_artifact_leg():
    """题面刻意不带任何兜底关键词：这一格比的是天花板，不是关键词改写。

    chart 的 _UPSTREAM 是 (doc, data)，同批只放行依赖就绪的一层，所以首批是 doc+data；
    被砍的是 export —— 那一格在问答档与分析档之间才是真差。
    """
    neutral = "帮我把这份材料理一理"

    routed = _routed(_dispatch_state(neutral, ["doc", "data", "chart", "export"]), _config(LANE_ANALYSIS))

    assert routed == ["doc", "data"]
    assert "export" not in routed
    # 对照：同样的输入不声明 ⇒ 产物腿照样排进后续批次；声明分析档就整条砍掉。
    done = dict(_dispatch_state(neutral, ["doc", "export"]))
    done["worker_results"] = {"doc": ANSWER}
    assert _routed(done, _config()) == ["export"]
    assert _routed(done, _config(LANE_ANALYSIS)) == "reflect"


def test_a_declared_report_turn_adds_the_artifact_leg_after_the_reads_finish():
    """报告档的地板：doc 先跑完，下一轮 export 单独占一个 superstep（HITL 挂起在前）。"""
    state = _dispatch_state(LIGHT, ["doc"])
    first = _routed(state, _config(LANE_REPORT))
    assert first == ["doc"], "首轮不许把挂起节点和真实工作混在同一批"

    done = dict(state)
    done["worker_results"] = {"doc": ANSWER}
    second = _routed(done, _config(LANE_REPORT))

    assert second == ["export"], "选了报告档却没有产物腿，那一格控件就是假的"


def test_a_declared_turn_with_no_data_file_is_not_forced_into_pandas():
    """没带数据文件 ⇒ 分析档的地板不触发：不派 data 也就不会编出一串数字。"""
    routed = _routed(_dispatch_state(HEAVY, ["doc"]), _config(LANE_ANALYSIS))

    assert "data" not in routed


@pytest.mark.parametrize("question", [HEAVY, LIGHT, "统计各季度营收并且画成柱状图", "你好"])
def test_an_undeclared_turn_routes_exactly_what_r141_before_routed(question):
    """判据② 的结构半：没声明时 config 里连键都没有 ⇒ 派发与不传 config 逐格相同。"""
    state = _dispatch_state(question, ["data"])

    assert _routed(state, _config()) == _routed(state, None)
    assert _routed(state, _config()) == _routed(state, {"configurable": {}})


def test_declaration_travels_through_configurable_not_state():
    """通道本身也要钉：lane 走 config，不塞进要被 checkpointer 序列化的 state。"""
    assert DECLARED_LANE_KEY == "declared_lane"
    assert nodes.declared_lane_from_config(_config(LANE_REPORT)) == LANE_REPORT
    assert "declared_lane" not in _dispatch_state(HEAVY, ["doc"])
    assert "lane" not in nodes.AgentState.__annotations__ if hasattr(nodes, "AgentState") else True


# ==================== E 组 · /ask 端到端：声明进图 + 三处读数（全离线） ====================


class _QueueStub:
    def __init__(self):
        self.calls = []

    def enqueue(self, payload, idempotency_key):
        self.calls.append({"payload": payload, "idempotency_key": idempotency_key})
        return SimpleNamespace(request_id="r141-reliable-request")


def _canonical(body, name):
    for block in body.split("\n\n"):
        lines = block.splitlines()
        if len(lines) >= 2 and lines[0] == f"event: {name}":
            return json.loads(lines[1][len("data: "):])
    return None


def _drive(monkeypatch, tmp_path, *, lane=None, cached=None, rate_allowed=True, switch=None,
           data_filename="", principal=None):
    """跑真的 ``/ask``：只把"会花钱 / 会留痕 / 会打网络"的出口换成桩或计数器。"""
    from app.common import reliable_queue

    seen = {"calls": 0, "kwargs": None, "user_message": None, "user": None}
    queue = _QueueStub()

    def _no_model(*_args, **_kwargs):
        raise AssertionError("档位分流不许多花模型往返")

    def _stream(user_message, thread_id="default", user=None, **kwargs):
        seen["calls"] += 1
        seen["kwargs"] = sorted(kwargs)
        seen["user_message"] = user_message
        seen["user"] = user
        yield {"messages": [], "worker_results": {"doc": ANSWER}, "final_answer": ANSWER}

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *a, **k: None)
    monkeypatch.setattr(chat, "_save_message", lambda *a, **k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_cached_source_manifest", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    monkeypatch.setattr(chat.model_handler, "chat", _no_model)
    monkeypatch.setattr(nodes, "_make_model", _no_model)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (rate_allowed, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: cached)
    monkeypatch.setattr("app.common.cache.answer_cache_origin", lambda *_a, **_k: {})
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", lambda: queue)
    monkeypatch.setattr(orchestrator, "run_with_stream", _stream)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: None)
    if switch is None:
        monkeypatch.delenv(chat.REPORT_LANE_QUEUE_ENV, raising=False)
    else:
        monkeypatch.setenv(chat.REPORT_LANE_QUEUE_ENV, switch)

    fields = {"message": HEAVY, "session_id": SESSION, "idempotency_key": IDEMPOTENCY}
    if data_filename:
        fields["data_filename"] = data_filename
    if lane is not None:
        fields["lane"] = lane
    request = chat.AskRequest(**fields)
    http_request = _http_request(principal or _principal())

    response = asyncio.run(chat.ask(request, http_request=http_request))

    async def collect():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    body = asyncio.run(collect())
    return SimpleNamespace(
        body=body,
        headers=dict(response.headers),
        started=_canonical(body, "request.started"),
        seen=seen,
        queue=queue,
    )


def test_an_undeclared_turn_does_not_even_add_the_config_key(monkeypatch, tmp_path):
    """判据② 的落点：不声明 ⇒ 连 ``declared_lane`` 这一格都不传（R149 钉的那份注册参数集不动）。"""
    run = _drive(monkeypatch, tmp_path, lane=None)

    assert "declared_lane" not in run.seen["kwargs"], run.seen["kwargs"]
    assert run.seen["calls"] == 1


@pytest.mark.parametrize("lane", [LANE_QA, LANE_ANALYSIS, LANE_REPORT])
def test_a_declared_turn_reaches_the_graph_with_the_declaration(monkeypatch, tmp_path, lane):
    """判据① 的进图半：标签不是存进库里就完事，它必须抵达那个能改派发的地方。"""
    run = _drive(monkeypatch, tmp_path, lane=lane)

    assert run.seen["kwargs"].count("declared_lane") == 1
    assert run.seen["user_message"] == HEAVY, "问题文本一个字都不许被标签改写"


def test_the_started_frame_carries_the_effective_tier_and_who_chose_it(monkeypatch, tmp_path):
    """判据① 的读数半：帧里读得到"本轮按哪条道、是谁定的、系统原判哪条"。"""
    run = _drive(monkeypatch, tmp_path, lane=LANE_QA)

    data = run.started["data"]
    assert data["lane"] == LANE_QA
    assert data["lane_source"] == LANE_SOURCE_EXPLICIT
    assert data["declared_lane"] == LANE_QA
    assert data["rules_lane"] == LANE_ANALYSIS, "HEAVY 本来被判到分析档，两格必须同时可读"
    assert data["allowed_workers"] == list(LANE_WORKERS[LANE_QA] + LANE_EXEMPT_WORKERS)


def test_the_frame_readout_and_the_constructor_are_the_same_object_shape(monkeypatch, tmp_path):
    """三处出口同源一份：帧里的读数必须逐格等于构造器给的那一份，不许第二套口径。"""
    run = _drive(monkeypatch, tmp_path, lane=LANE_ANALYSIS)
    direct = resolve_turn_lane(HEAVY, LANE_ANALYSIS).as_dict()

    assert {key: run.started["data"][key] for key in direct} == direct


def test_the_response_headers_read_back_the_same_tier_the_graph_got(monkeypatch, tmp_path):
    """不看 SSE 的客户端（curl / 网关日志）也要能读到同一句话。"""
    run = _drive(monkeypatch, tmp_path, lane=LANE_REPORT)

    assert run.headers[chat.EFFECTIVE_LANE_HEADER] == LANE_REPORT
    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_EXPLICIT
    assert run.headers[chat.DECLARED_LANE_HEADER] == LANE_REPORT


def test_an_undeclared_turn_reports_r42_without_claiming_a_declaration(monkeypatch, tmp_path):
    run = _drive(monkeypatch, tmp_path, lane="")

    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_R42
    assert chat.DECLARED_LANE_HEADER not in run.headers, "没声明就不该有这一格读数"
    assert run.started["data"]["declared_lane"] == ""


def test_a_cache_hit_says_the_tier_played_no_part(monkeypatch, tmp_path):
    """判据②：缓存命中这一轮没走图，读数必须说 not_routed，而不是把声明抄成生效。"""
    run = _drive(monkeypatch, tmp_path, lane=LANE_REPORT, cached=ANSWER)

    assert run.seen["calls"] == 0, "命中缓存就不该进图"
    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_NOT_ROUTED
    assert chat.EFFECTIVE_LANE_HEADER not in run.headers
    assert run.headers[chat.DECLARED_LANE_HEADER] == LANE_REPORT, "声明本身还是要留痕"


def test_the_over_limit_enqueue_reads_not_routed_and_still_keeps_the_label(monkeypatch, tmp_path):
    run = _drive(monkeypatch, tmp_path, lane=LANE_ANALYSIS, rate_allowed=False)

    assert run.queue.calls, "超限这一轮该入队"
    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_NOT_ROUTED
    assert run.headers[chat.DECLARED_LANE_HEADER] == LANE_ANALYSIS
    # R37 的逐字段钉：载荷一格不许多（读头走 HTTP 头，不走队列载荷）
    assert set(run.queue.calls[0]["payload"]) == {
        "task_type", "message", "session_id", "username", "principal",
    }


def test_run_with_stream_routes_through_configurable_and_records_the_readout(monkeypatch):
    """图内两格：声明真的进了 configurable（route_main/plan 读的就是这一格），
    而 trace 的 request.started 载荷带着同一份读数。"""
    captured = {}
    recorded = []

    def _stream(graph, payload, config, **_kwargs):
        captured["config"] = config
        return iter([])

    monkeypatch.setattr(orchestrator, "_cancellable_stream", _stream)
    store = SimpleNamespace(record_event=lambda **kw: recorded.append(kw))

    list(orchestrator.run_with_stream(HEAVY, thread_id="r141-trace", declared_lane=LANE_QA,
                                      trace_store=store))

    assert captured["config"]["configurable"][DECLARED_LANE_KEY] == LANE_QA
    started = [row for row in recorded if row["event_type"] == "request.started"]
    assert len(started) == 1
    payload = started[0]["payload"]
    assert payload["lane"] == LANE_QA and payload["lane_source"] == LANE_SOURCE_EXPLICIT
    assert payload["required_workers"] == [list(pair) for pair in LANE_REQUIRED_WORKERS[LANE_QA]]


def test_run_with_stream_adds_no_key_when_nothing_is_declared(monkeypatch):
    captured = {}

    def _stream(graph, payload, config, **_kwargs):
        captured["config"] = config
        return iter([])

    monkeypatch.setattr(orchestrator, "_cancellable_stream", _stream)
    list(orchestrator.run_with_stream(HEAVY, thread_id="r141-trace2",
                                      trace_store=SimpleNamespace(record_event=lambda **_kw: None)))

    assert DECLARED_LANE_KEY not in captured["config"]["configurable"]


def test_the_data_file_attachment_is_what_arms_the_analysis_floor(monkeypatch, tmp_path):
    """带 data_filename 的那一轮，config 里真有那一格 ⇒ 地板的 has_data 不是自说自话。"""
    run = _drive(monkeypatch, tmp_path, lane=LANE_ANALYSIS, data_filename="sales-2026.xlsx")

    assert run.seen["user"]["data_filename"] == "sales-2026.xlsx"


# ==================== F 组 · /chat 那张脸：拒收声明，不发惰性标签（判据②） ====================


def _drive_chat(monkeypatch, *, lane=None):
    monkeypatch.setattr(chat, "retriever", SimpleNamespace(search=lambda *_a, **_k: []))
    monkeypatch.setattr(chat.model_handler, "chat",
                        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("/chat 不该被消费")))
    fields = {"message": LIGHT}
    if lane is not None:
        fields["lane"] = lane
    return chat.ChatRequest(**fields), _http_request(_principal())


@pytest.mark.parametrize("lane", [LANE_QA, LANE_ANALYSIS, LANE_REPORT, "REPORT"])
def test_chat_refuses_every_declared_tier_because_it_has_no_legs_to_route(monkeypatch, lane):
    """"收了标签但路径照旧"就是 R32 拒交选择器的那张脸，本单不在 /chat 上重做一遍。"""
    request, http_request = _drive_chat(monkeypatch, lane=lane)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(chat.chat(request, http_request))

    assert caught.value.status_code == 400
    assert caught.value.detail["code"] == chat.LANE_ERROR_CODE
    assert caught.value.detail["details"]["endpoint"] == "/chat"
    assert caught.value.detail["details"]["use_instead"] == "/api/v1/ask"


def test_chat_still_works_for_the_callers_that_declare_nothing(monkeypatch):
    request, http_request = _drive_chat(monkeypatch)

    response = asyncio.run(chat.chat(request, http_request))

    assert response.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_NOT_ROUTED
    assert chat.EFFECTIVE_LANE_HEADER not in response.headers
    assert chat.DECLARED_LANE_HEADER not in response.headers


# ==================== G 组 · 单源与落点（结构证据） ====================


def test_the_declaration_reaches_the_graph_through_exactly_one_channel():
    source = CHAT_SOURCE.read_text(encoding="utf-8")

    assert source.count('"declared_lane": declared') == 1
    # R172 起，chat.py 里那份归一后的声明有了第二个去处：挂起账本。原钉写的是
    # "declared_lane=declared 一次都不许多出现"，它防的是**第二道进图的通道**；今天进图
    # 仍旧只有上面那一枚（run_with_stream 的 configurable），所以改钉成"带 declared_lane
    # 关键字的调用点闭集里只有账本那两枚，图不在其中" —— 保护的是同一件事，钉得更直。
    tree = ast.parse(source)
    callees = {
        getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(keyword.arg == "declared_lane" for keyword in node.keywords)
    }

    assert callees == {"_record_pending_approval", "record_awaiting"}, callees
    assert "run_with_stream" not in callees, "图那边多了一道带声明的入口"
    assert source.count("request.lane") == 0, "直读属性就是绕过那四枚具名读口"


def test_the_label_never_reaches_the_retrieval_arguments():
    """判据② 的反面：档位不许顺手去调 k 或 where，那是另一单的口径。"""
    import re

    source = CHAT_SOURCE.read_text(encoding="utf-8")
    calls = re.findall(r"retriever\.search\([^)]*\)", source, re.S)

    assert calls, "检索出口不见了，这条对照就是空的"
    for call in calls:
        assert "lane" not in call, call
        assert "k=5" in call, call


def test_the_lane_tables_are_the_only_source_for_the_readout():
    """读数的腿边界来自那张表，不是各出口手抄：逐枚点名出口读的是同一枚对象。"""
    source = CHAT_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert {"_declared_lane", "_turn_lane_readout", "_resumed_lane_readout",
            "_lane_readout_headers", "_require_no_lane_on_chat"} <= names
    for lane in (LANE_QA, LANE_ANALYSIS, LANE_REPORT):
        assert resolve_turn_lane(HEAVY, lane).allowed_workers == LANE_WORKERS[lane] + LANE_EXEMPT_WORKERS
