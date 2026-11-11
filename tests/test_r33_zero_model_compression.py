"""R33 判据①②：历史裁剪零模型，而且这件事钉在 AST 与计数桩上，不钉在 grep 文本上。

现场事实（总控在 ``fd6aa8e`` 实测、本班复核一致）：``app/agents/orchestrator.py`` 里那句
``compress_messages(all_msgs, _make_model(ModelTier.COMPRESS))`` 让"裁剪"这件事自己多发一发
模型往返 —— ``app/memory/summarizer.py`` 旧版 ``summarize()`` 里就是 ``model.invoke(...)``。
R33 把这条腿换成确定性裁剪。判据原文见跟进单 §21 表 L505 的 ②「裁剪过程零模型调用」，
改写版见 ``docs/handoff/2026-09-20-unblock-map.md`` §G-4。

为什么用 AST 而不是 grep：判据① 要的是"摘掉当场红、写回也当场红"。grep 版两头都漏 ——
注释里合理出现 COMPRESS 这个词（本文件与 summarizer 的 docstring 都必须写它）会误报，
而把 ``ModelTier.COMPRESS`` 先赋给局部变量再用又能绕过行匹配。AST 看的是属性访问这件事本身。

为什么枚举行不删：``ModelTier.COMPRESS`` 仍被 ``tests/test_r30_timeout_budget.py`` 用来量档位
预算（:108 与 :191 两处都在拿它验 ``tier_profile`` / ``model_tier_budget`` 口径）。删成员要同批
改 ``model_budget.py:185``、``contracts.py`` 枚举、``stage_timing.py:51-60`` 三处表，blast radius
大且与本单判据无关。本单收的是**生产路径上的调用点**，不收"这个档位存在"这件事。
"""
import ast
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import orchestrator
from app.agents.contracts import ModelTier
from app.memory.summarizer import TRUNCATION_SUFFIX, trim_history

#: 计数桩直接复用 R42 那台仪器，不另造一套（判据② 点名的形状）。
from test_r42_zero_model_calls import _CountingFactory

REPO = Path(__file__).resolve().parents[1]
ORCHESTRATOR_SOURCE = (REPO / "app" / "agents" / "orchestrator.py").read_text(encoding="utf-8")

#: 旧版那一发的原样形状：反空转对照要用它证明 AST 探针真的看得见。
OLD_COMPRESS_CALL = (
    "from app.agents.contracts import ModelTier\n"
    "all_msgs = compress_messages(all_msgs, _make_model(ModelTier.COMPRESS))\n"
)


def _tier_attributes(source: str) -> list[str]:
    """所有 ``ModelTier.X`` 属性访问里的 X（注释与字符串字面量都不算）。"""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ModelTier"
        ):
            found.append(node.attr)
    return found


def _compress_calls(source: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "compress_messages"
    ]


class _RecordingMainModel:
    """替掉 ``orchestrator.main_model``：只记录 supervisor 那一发真正发出了什么。"""

    def __init__(self):
        self.seen: list[list] = []

    def invoke(self, messages, **kwargs):
        self.seen.append(list(messages))

        class _Resp:
            content = "本轮无需派发。"
            tool_calls: list = []

        return _Resp()


def _history(rounds: int):
    """40 条（12 条 20 条都算）超过旧版 THRESHOLD=20 的历史，长答是旧版会掏模型去摘要的那种。"""
    messages = []
    for turn in range(rounds):
        messages.append(HumanMessage(content="第%d问：住宿费标准是多少？" % turn))
        messages.append(
            AIMessage(content="第%d答：" % turn + "标准按职级分档，详细口径见制度文件正文。" * 30)
        )
    return messages


def _mixed_history(old_rounds: int = 12, recent_rounds: int = 2):
    """旧轮长答 + 最近几轮短答：只有这种形状才能把"截断"与"整条丢掉"分成两个可分辨的档位。

    最近 8 条本身就值两千多 token，所以拿 _history() 那种"最近几轮也是长答"的数据去量，
    任何预算都直接跳到丢弃档，截断这一半永远看不见 —— 那是数据的问题，不是规则的问题。
    """
    messages = []
    for turn in range(old_rounds):
        messages.append(HumanMessage(content="旧%d问：住宿费标准是多少？" % turn))
        messages.append(
            AIMessage(content="旧%d答：" % turn + "标准按职级分档，详细口径见制度文件正文。" * 30)
        )
    for turn in range(recent_rounds):
        messages.append(HumanMessage(content="近%d问：今天的口径呢？" % turn))
        messages.append(AIMessage(content="近%d答：今天按新口径执行。" % turn))
    return messages


@pytest.fixture
def model_counter(monkeypatch):
    """把两个模块的模型工厂都换成 R42 的计数桩（裁剪若还想发模型，必从这里过）。"""
    counter = _CountingFactory()
    monkeypatch.setattr(orchestrator, "_make_model", counter)
    monkeypatch.setattr("app.agents.nodes._make_model", counter)
    return counter


# ==================== 判据① AST 级零调用点 ====================

def test_the_ast_instrument_really_sees_a_compress_call():
    """反空转对照：这台仪器不是永远交空表 —— 旧那一发写回去，它当场报 COMPRESS。"""
    assert _tier_attributes(OLD_COMPRESS_CALL) == ["COMPRESS"], (
        "AST 探针自己坏了，下面那条 0 全部无效"
    )
    calls = _compress_calls(OLD_COMPRESS_CALL)
    assert len(calls) == 1 and len(calls[0].args) == 2, (
        "探针认不出旧签名 compress_messages(msgs, model) 的第二枚位置参数"
    )


def test_orchestrator_builds_no_compress_tier_model():
    """判据① 主体：``orchestrator.py`` 里 ``ModelTier.COMPRESS`` 的调用点必须为零。"""
    attributes = _tier_attributes(ORCHESTRATOR_SOURCE)
    assert "COMPRESS" not in attributes, (
        "R33 判据①：orchestrator.py 又出现 ModelTier.COMPRESS 调用点。现有档位访问 = %r"
        % sorted(set(attributes))
    )


def test_orchestrator_hands_no_model_to_the_history_trim():
    """判据① 另一半：那条裁剪调用只吃消息列表与档位，不吃模型对象。"""
    calls = _compress_calls(ORCHESTRATOR_SOURCE)
    assert len(calls) == 1, (
        "生产路径上就该有一处历史裁剪，多出来的一处没人审过：%d 枚" % len(calls)
    )
    call = calls[0]
    assert len(call.args) == 1, (
        "裁剪第二枚位置参数在 R33 之前是模型对象，现在不许再有：%r" % call.args
    )
    keywords = sorted(kw.arg for kw in call.keywords)
    assert "model" not in keywords, "不许再把模型递给裁剪：%r" % keywords
    assert keywords == ["tier"], "裁剪入口的关键字参数形状变了，请连同本判据一起改：%r" % keywords


def test_the_compress_tier_member_still_exists_for_budget_calibration():
    """枚举行**保留**的账：档位还在（R30 拿它量表），只是生产路径不再调它。"""
    assert ModelTier.COMPRESS.value == "compress"
    assert "COMPRESS" not in _tier_attributes(ORCHESTRATOR_SOURCE)


# ==================== 判据② 零 provider 调用 ====================

def test_a_history_over_the_old_threshold_costs_no_model_round_trip(model_counter, monkeypatch):
    """判据② 主体：40 条历史（远超旧版 THRESHOLD=20）跑完 supervisor 这一发，零模型工厂调用。"""
    recorded = _RecordingMainModel()
    monkeypatch.setattr(orchestrator, "main_model", recorded)  # 产品路径上它只在 :259 造、:397 用
    orchestrator.main_agent_node({"messages": _history(20), "memory": {}})

    assert model_counter.calls == [], (
        "R33 判据②：历史裁剪又发模型了，计数桩读到 %r" % model_counter.calls
    )
    assert len(recorded.seen) == 1, "supervisor 那一发仍应只发一次"


def test_the_same_counter_would_have_recorded_a_compress_call(model_counter):
    """反空转对照：同一个 fixture 下，真发一发 COMPRESS 就立刻看得见 —— 上面那个 0 不是桩坏了。"""
    orchestrator._make_model(ModelTier.COMPRESS)
    assert model_counter.calls == ["compress"]


def test_the_trim_itself_refuses_a_model():
    """判据② 的机制账：谁想把模型塞回裁剪入口，当场 TypeError，而不是静默多花一发往返。"""
    from app.memory import compress_messages

    with pytest.raises(TypeError) as refused:
        compress_messages(_history(20), model=object())
    assert "R33" in str(refused.value), refused.value


def test_trimming_is_recomputable_byte_for_byte():
    """判据② 的确定性：同输入两次裁剪逐条同形，且这一档确实只截不丢。"""
    from app.common.model_budget import estimate_prompt_tokens

    history = _mixed_history()
    full = estimate_prompt_tokens(history)
    # 预算取实测的一半：装不下原文（必须动手），又留得下"每条截到 200 字"的整份清单
    # （只到丢弃档之前），这样这条用例量的才是"按字符截断"而不是"整条丢掉"。
    budget = full // 2
    first = trim_history(history, budget_tokens=budget)
    second = trim_history(list(history), budget_tokens=budget)
    assert len(first) == len(history), (
        "这一档不该丢整条：%d 条 → %d 条（full=%d，budget=%d）"
        % (len(history), len(first), full, budget)
    )

    assert [type(m).__name__ for m in first] == [type(m).__name__ for m in second]
    assert [m.content for m in first] == [m.content for m in second], (
        "两次裁剪不同形：里面掺了时间、随机数或模型输出"
    )
    assert any(TRUNCATION_SUFFIX in m.content for m in first), (
        "这组数据裁完一条都没截，本用例就成了空转（换预算，别换判据）"
    )
    assert all(TRUNCATION_SUFFIX not in m.content for m in first if type(m).__name__ == "HumanMessage"), (
        "人类问题被截了：旧轮问题要原样留在历史里"
    )


def test_the_supervisor_prompt_does_not_depend_on_the_trim(model_counter, monkeypatch):
    """本单不改答案内容：同一份历史，裁与不裁，supervisor 实际发出的 prompt 逐字相同。

    这正是 R33 之前那发模型往返最尴尬的地方 —— 它算出来的摘要串根本进不了 supervisor 的
    prompt（``tests/test_supervisor_roundtrip.py:7-9`` 已把这一点当既成事实钉着），所以撤掉
    它不会改动任何一发给模型的字。真机质量回归仍由总控在 run6 观察，这条只钉"形状没变"。
    """
    recorded = _RecordingMainModel()
    monkeypatch.setattr(orchestrator, "main_model", recorded)
    # 计数桩同时是防线：R33 之前的装配在这一发里会真去连 127.0.0.1:11434（conftest 的 R56
    # 端口闸门实测记到 2 次 blocked connect），有桩在，回归时看到的是干净断言而不是 socket 报错。
    assert model_counter.calls == []
    history = _history(20)

    orchestrator.main_agent_node({"messages": history, "memory": {}})
    before = [[type(m).__name__, m.content] for m in recorded.seen[-1]]
    orchestrator.main_agent_node({"messages": trim_history(history, budget_tokens=1), "memory": {}})
    after = [[type(m).__name__, m.content] for m in recorded.seen[-1]]

    assert before == after, "裁剪改变了 supervisor 的 prompt，本单就不该只改裁剪"
