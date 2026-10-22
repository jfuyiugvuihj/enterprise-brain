"""R27 判据①③：确定性计划命中的轮次，Supervisor 只发一发模型往返。

钉死三件事：
1. 第二发是谁发的。route_main 在 app/agents/orchestrator.py:332 返回
   ["main_tools", Send(worker)...]，而 _builder 上 main_tools 与每个 worker 都挂着
   无条件回到 supervisor 的硬边（app/agents/orchestrator.py:688-693），所以只要派发过
   就必然再进一次 main_agent_node；:201 那一发的 prompt 只有 [sys_msg,
   current_user_msg]，worker 结果一个字都不进上下文，temperature=0 之下第 2 发只能把
   第 1 发的决策复读一遍 —— 15.931 s 的纯空转
   （docs/perf/latency-budget-2026-09-16.md §3.3）。
2. 命中确定性计划时 invoke 计数 == 1；未命中（plan 不是确定性产物、或 reflect 判了
   redo）时保持今天的原值。原值 2 是拿本文件在未打补丁的 orchestrator.py 上实测得到的
   （见交接记录里的"补丁前"输出），不是猜的。
3. 省掉第二发之后 route_main 的收敛、分层派发、HITL 拒绝不再重派都没变。

打桩对象是模块级 orchestrator.main_model（产品路径上只有 :201 用它）。全程不连
Ollama、不跑真实 worker 子图、不做任何端到端计时。
"""
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages

from app.agents import orchestrator
from app.agents.orchestrator import main_agent_node, route_main
from app.agents.planner import build_task_plan

# 表一原题："标准" 命中 planner 的 has_doc ⇒ 确定性计划就是单步 ["doc"]。
POLICY_QUESTION = "我们经销商的标准回款周期是多少天？超期多久会停发新货？"
# "营收" 命中 data、"柱状图" 命中 chart ⇒ 两步计划，用来验分层派发。
CHART_QUESTION = "把各季度营收画成柱状图"
DOC_ANSWER = "标准回款周期 30 天，超期 60 天停发新货。"
DATA_ANSWER = "Q1 120 万、Q2 180 万、Q3 150 万、Q4 210 万。"
REFUSED_NOTE = "已取消，未执行：📈 生成图表"


def dispatch_message(*workers):
    """supervisor 第 1 发的形状：只有 tool_calls，没有正文。"""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "dispatch",
                "args": {"workers": list(workers)},
                "id": "supervisor-dispatch",
                "type": "tool_call",
            }
        ],
    )


def worker_message(worker, text):
    """镜像 _make_worker_wrapper 追加的那条收尾消息（orchestrator.py:439）。"""
    return AIMessage(content=f"【{worker} Agent 返回】\n{text}")


class _CountingModel:
    """记录每一次 invoke 的桩模型：真实推理一次都不该发生。"""

    def __init__(self, workers=("doc",)):
        self.calls = []
        self._workers = list(workers)

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        return dispatch_message(*self._workers)

    @property
    def roundtrips(self):
        return len(self.calls)


def _stub_model(monkeypatch, workers=("doc",)):
    fake = _CountingModel(workers=workers)
    monkeypatch.setattr(orchestrator, "main_model", fake)
    return fake


def _state(question, plan_workers, worker_results=None, **extra):
    state = {
        "messages": [HumanMessage(content=question)],
        "plan": [{"worker": w, "objective": f"step-{w}"} for w in plan_workers],
    }
    if worker_results is not None:
        state["worker_results"] = dict(worker_results)
    state.update(extra)
    return state


def _advance(state, update):
    """按生产 reducer（add_messages）把节点返回值合回 state，返回新 state。"""
    merged = dict(state)
    merged["messages"] = add_messages(state["messages"], update.get("messages") or [])
    for key, value in update.items():
        if key != "messages":
            merged[key] = value
    return merged


def _back_to_supervisor(state, worker, text):
    """复刻 route_main 派发之后回到 supervisor 时 messages 的实际形状：
    supervisor 的决策 → main_tools 的 ToolMessage → worker 的收尾 AIMessage。
    """
    appended = [
        ToolMessage(content="已派发 1 个子Agent", tool_call_id="supervisor-dispatch", name="dispatch"),
        worker_message(worker, text),
    ]
    merged = _advance(state, {"messages": appended})
    merged["worker_results"] = {**(state.get("worker_results") or {}), worker: text}
    return merged


def _normal_edges():
    raw = orchestrator._builder.edges
    pairs = set()
    if isinstance(raw, dict):
        for source, targets in raw.items():
            if isinstance(source, tuple):
                pairs.add((str(source[0]), str(source[1])))
            elif isinstance(targets, (set, list, tuple)):
                pairs.update((str(source), str(target)) for target in targets)
            else:
                pairs.add((str(source), str(targets)))
    else:
        for edge in raw:
            pairs.add((str(edge[0]), str(edge[1])))
    return pairs


def _dispatched(route):
    assert isinstance(route, list), "本轮没有派发任何 worker"
    assert route[0] == "main_tools"
    return [getattr(item, "node", None) for item in route if not isinstance(item, str)]


def test_fixture_questions_match_the_deterministic_plans_used_below():
    """桩数据的根：这两道题的确定性计划必须是下面用例假设的形状。"""
    assert [task["worker"] for task in build_task_plan(POLICY_QUESTION)] == ["doc"]
    assert [task["worker"] for task in build_task_plan(CHART_QUESTION)] == ["data", "chart"]


def test_second_supervisor_trip_is_triggered_by_unconditional_edges():
    """判据①：回 supervisor 的边全是硬边，所以派发过就必然有第二发。"""
    pairs = _normal_edges()
    assert ("main_tools", "supervisor") in pairs
    for worker in ("doc", "data", "chart", "export", "approval"):
        assert (worker, "supervisor") in pairs
    assert "main_tools" not in orchestrator._builder.branches


def test_first_trip_still_asks_the_model(monkeypatch):
    fake = _stub_model(monkeypatch, workers=("doc",))

    main_agent_node(_state(POLICY_QUESTION, ["doc"]))

    assert fake.roundtrips == 1


def test_deterministic_plan_hit_asks_the_supervisor_model_once(monkeypatch):
    """判据③：确定性计划命中 ⇒ 模型往返 2 → 1，且 route_main 仍以 reflect 收敛。"""
    fake = _stub_model(monkeypatch, workers=("doc",))
    entry1 = _state(POLICY_QUESTION, ["doc"])

    first = main_agent_node(entry1)
    assert fake.roundtrips == 1
    mid = _advance(entry1, first)
    assert _dispatched(route_main(mid)) == ["doc"]

    entry2 = _back_to_supervisor(mid, "doc", DOC_ANSWER)
    second = main_agent_node(entry2)

    assert fake.roundtrips == 1, "确定性计划命中时第二发 Supervisor 仍打到了模型"
    merged = _advance(entry2, second)
    replayed = merged["messages"][-1]
    assert replayed.tool_calls[0]["args"]["workers"] == ["doc"]
    assert replayed.id != mid["messages"][-1].id
    assert route_main(merged) == "reflect"


def test_second_layer_still_dispatches_without_a_model_trip(monkeypatch):
    """省掉第二发不能把分层派发一起省掉：data 完成后 chart 照样放行。"""
    fake = _stub_model(monkeypatch, workers=("data",))
    entry1 = _state(CHART_QUESTION, ["data", "chart"])

    first = main_agent_node(entry1)
    mid = _advance(entry1, first)
    assert _dispatched(route_main(mid)) == ["data"]

    entry2 = _back_to_supervisor(mid, "data", DATA_ANSWER)
    second = main_agent_node(entry2)

    assert fake.roundtrips == 1, "第二层派发又花了一次模型往返"
    assert _dispatched(route_main(_advance(entry2, second))) == ["chart"]


def test_refused_hitl_step_is_not_redispatched(monkeypatch):
    """run_interrupt_stream 的拒绝收尾（Command(goto="supervisor")）不得重派被拒动作。"""
    fake = _stub_model(monkeypatch, workers=("data",))
    entry1 = _state(CHART_QUESTION, ["data", "chart"])

    mid = _advance(entry1, main_agent_node(entry1))
    entry2 = _back_to_supervisor(mid, "data", DATA_ANSWER)
    entry2 = _advance(entry2, {"messages": [AIMessage(content=REFUSED_NOTE)]})
    entry2["worker_results"] = {**entry2["worker_results"], "chart": REFUSED_NOTE}

    second = main_agent_node(entry2)

    assert fake.roundtrips == 1
    assert route_main(_advance(entry2, second)) == "reflect"


def test_plan_that_is_not_deterministic_keeps_todays_two_trips(monkeypatch):
    """未命中确定性计划 ⇒ 路径与今天逐字一致，第二发照旧问模型（今天实测 = 2）。"""
    fake = _stub_model(monkeypatch, workers=("export",))
    entry1 = _state(POLICY_QUESTION, ["export"])

    mid = _advance(entry1, main_agent_node(entry1))
    assert fake.roundtrips == 1

    entry2 = _back_to_supervisor(mid, "export", "报告已生成。")
    main_agent_node(entry2)

    assert fake.roundtrips == 2


def test_reflect_redo_keeps_todays_two_trips(monkeypatch):
    """reflect 判 redo 回炉时模型仍是唯一纠正面 ⇒ 保持今天的 2 发。"""
    fake = _stub_model(monkeypatch, workers=("doc",))
    entry1 = _state(POLICY_QUESTION, ["doc"])

    mid = _advance(entry1, main_agent_node(entry1))
    entry2 = _back_to_supervisor(mid, "doc", DOC_ANSWER)
    entry2["redo"] = True
    main_agent_node(entry2)

    assert fake.roundtrips == 2