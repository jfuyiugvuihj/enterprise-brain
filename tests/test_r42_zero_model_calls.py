"""R42 判据①：判别路径上零模型调用。

证据形态是指定的"可执行断言"，不是"我看代码没有"：把 app/agents/nodes.py 与
app/agents/orchestrator.py 里的模型工厂换成计数桩，跑完判别路径再断言计数 == 0。
桩同时记录 tier，所以"零调用"和"调了几次、哪个档"是同一台仪器读出来的。

反空转对照（test_the_counter_...）先证明这台仪器数得出来：复合题走 plan 时必须是 1。
没有这条对照，"0"可以靠桩坏掉刷出来。

全程不连 Ollama：tests/conftest.py 的 R56 宿主端口闸门负责兜底，交付里引用它末尾三行
（blocked / offline discovery stub / pin re-installed 必须全为 0）。
"""
import inspect
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier
from app.agents.nodes import LANE_QA, classify_intent, classify_route, plan
from app.agents.orchestrator import route_main

FIXTURE = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"

#: 一个可执行的反例：判别器必须能"看见"真实调用，否则 0 没有意义。
COMPOUND_QUESTION = "查一下报销制度，并且看看门店利润"


def _questions():
    lines = FIXTURE.read_text(encoding="utf-8-sig").splitlines()
    return [json.loads(line)["question"] for line in lines if line.strip()]


class _CountingFactory:
    """替换 ``_make_model`` 的计数桩：记下每一次"本该发生的模型调用"及其档位。"""

    def __init__(self):
        self.calls = []

    def __call__(self, tier=ModelTier.ANALYSIS, *, prompt=None):
        self.calls.append(getattr(tier, "value", str(tier)))
        return _StubModel()

    @property
    def count(self):
        return len(self.calls)


class _StubModel:
    """被调用也不发请求：invoke/stream 只是把桩自己的形状交回去。"""

    def invoke(self, _messages):
        return AIMessage(content="[]")

    def stream(self, _messages):
        yield AIMessage(content="[]")


@pytest.fixture
def model_counter(monkeypatch):
    counter = _CountingFactory()
    monkeypatch.setattr(nodes, "_make_model", counter)
    monkeypatch.setattr(orchestrator, "_make_model", counter)
    # 确定性计划命中时 plan() 走的是 planner，不进判别器；这里把它摘掉，
    # 让 plan() 必须经过 R42 判别器才能决定拆不拆题。
    monkeypatch.setattr(nodes, "build_task_plan", lambda question: [])
    return counter


def test_the_counter_actually_counts_a_real_model_call(model_counter):
    """反空转对照：分析档的复合题确实会付一发 PLAN，仪器数得出来。"""
    result = plan({"messages": [HumanMessage(content=COMPOUND_QUESTION)]})

    assert model_counter.count == 1, (
        "计数桩没有观察到任何模型调用，后面的 0 全部无效"
    )
    assert model_counter.calls == [ModelTier.PLAN.value]
    assert result["plan"] == []


def test_classifying_all_105_questions_never_builds_a_model(model_counter):
    """判据①主体：105 条题面全量判别，模型工厂零调用。"""
    questions = _questions()
    assert len(questions) == 105

    for question in questions:
        classify_route(question)

    assert model_counter.count == 0, f"判别路径上调了 {model_counter.calls}"


def test_the_intent_node_stays_model_free(model_counter):
    """classify_intent 与判别器同处一个节点，两条都必须是零调用。"""
    for question in _questions():
        classify_intent({"messages": [HumanMessage(content=question)]})

    assert model_counter.count == 0, f"意图节点上调了 {model_counter.calls}"


def test_the_question_lane_skips_the_splitting_call(model_counter):
    """判别器的实际作用：问答档的题不再付那发拆题模型。

    题面刻意选评测集 doc-08 原题——它带一个裸"和"，正是今天 `_COMPLEX`
    会命中并掏模型的那种问题。摘掉 plan() 里的问答档闸门，这条必须变红。
    """
    light = "餐费和住宿费的票能开在一张上吗？"
    assert classify_route(light).lane == LANE_QA
    assert any(marker in light for marker in nodes._COMPLEX), (
        "题面不带任何旧的复合连接词，这条对照就不成立"
    )

    result = plan({"messages": [HumanMessage(content=light)]})

    assert result["plan"] == []
    assert model_counter.count == 0, f"问答档仍调了模型：{model_counter.calls}"


def test_a_plain_question_lane_turn_still_spends_nothing(model_counter):
    """问答档的常规题：判别 + 计划两步合起来零调用。"""
    light = "住宿费标准是多少？"

    classify_intent({"messages": [HumanMessage(content=light)]})
    classify_route(light)
    plan({"messages": [HumanMessage(content=light)]})

    assert model_counter.count == 0, f"问答档一轮里调了模型：{model_counter.calls}"


def test_route_main_decisions_never_build_a_model(model_counter):
    """route_main 也是判别路径的一部分（问答档补派 doc），同样必须零调用。"""
    for question in _questions():
        route_main({"messages": [HumanMessage(content=question), AIMessage(content="")]})

    assert model_counter.count == 0, f"路由段上调了模型：{model_counter.calls}"


@pytest.mark.parametrize(
    "fn_name",
    ["classify_route", "_route_rules", "classify_intent", "_markers_hit"],
)
def test_the_discriminator_source_has_no_call_sites(fn_name):
    """源码级第二道锁：判别器自己的函数体里不许出现任何模型出入口。"""
    source = inspect.getsource(getattr(nodes, fn_name))

    for forbidden in (".invoke", ".stream", ".astream", "_make_model", "ChatOpenAI", "httpx"):
        assert forbidden not in source, f"{fn_name} 里出现了 {forbidden}"
