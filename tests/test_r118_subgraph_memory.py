"""R127（= R118 乙案·乙-1）· 子图 checkpointer 只写不读：跨轮 prompt 形状钉。

判据出处：定策纸 `docs/handoff/2026-09-20-r118-subgraph-memory.md` §4-2 判据①②，立案原文跟进单 §55。

要钉住的事实（**今天全仓没有任何用例看得见它**：`git grep -c checkpoint_ns -- tests` 在本单之前是空输出）：
生产装配（`orchestrator._make_worker_wrapper` 在父节点内手工 ``child.invoke``）下，worker 子图
虽然带着 checkpointer（``orchestrator.py`` 建图那四行），但 langgraph 给嵌套 invoke 注入的
``checkpoint_ns`` 每轮换成新的 ``doc:<task uuid>``，于是**每轮都写、永远不回读**：子图每轮进模型
的 prompt 恒等于 ``[SystemMessage, 本轮那条 HumanMessage]``。

全离线：不连模型、不起服务、不动数据。模型是脚本化假 model，检索腿 ``monkeypatch`` 掉
``tools._get_pipeline``，一次 socket 都不开、``chroma_db/**`` 一个字节都不碰。

摘掉源码里那两行注释不会让本文件变红（判据是形状与文字各自独立钉住的）；把装配改回"真 resume"
（清掉继承的父 config、或把子图直接当节点、或给子图加/减 ``checkpointer=``）会当场红。
"""
import os
from pathlib import Path

import pytest

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.agents import orchestrator, tools
from app.agents.state import AgentState
from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS

#: 连问几轮。三轮是下限：两轮分不清"回读了上一轮"与"本轮自己新长的历史"。
ROUNDS = 3

#: 一份资料里的关键数字：用来证明每轮子图**确实**拿到过一段真实的工具串（形状钉不是空转）。
KEY_FIGURE = "600"

#: 四条 worker 腿的图对象名（判据①的反证 (b) 逐枚点名）。
WORKER_GRAPHS = ("doc_graph", "data_graph", "chart_graph", "export_graph")


def _hits(count):
    """每条命中都装到工具允许的最大正文，一发的串就有几百枚 token——旧装配若真回读，绝不可能看不见它。"""
    filler = (
        "差旅报销制度条款：住宿费限额按职级分档，部门负责人标准每日 %s 元，"
        "超标须事前审批，发票在三十日内提交财务部复核后打款。" % KEY_FIGURE
    ) * 20
    return [
        {
            "source": "差旅报销制度_%d.pdf" % (index + 1),
            "chunk_index": index,
            "_score": round(0.93 - 0.07 * index, 2),
            "content": (filler + str(index))[:DOC_HIT_CONTENT_CHARS],
        }
        for index in range(count)
    ]


class FakePipeline:
    def __init__(self, hits):
        self._hits = hits

    def search_for_principal(self, query, principal, top_k, **kwargs):
        return list(self._hits), ["住宿费限额"]


class ShapeModel(BaseChatModel):
    """脚本化假模型：每轮一发 ``search_docs``，并把"每次进模型时看到的消息列表"逐份记下来。"""

    seen: list = []
    round_starts: list = []
    issued: int = 0

    @property
    def _llm_type(self):
        return "r127-shape-leg"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        last = messages[-1]
        if isinstance(last, ToolMessage):
            bodies = "\n".join(
                str(message.content) for message in messages if isinstance(message, ToolMessage)
            )
            read = KEY_FIGURE if ("每日 " + KEY_FIGURE + " 元") in bodies else "NONE"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="限额读数=" + read))])
        if isinstance(last, HumanMessage):
            # 本轮第一次进模型：这一刻的 prompt 就是"子图到底记不记得上一轮"的判点。
            self.round_starts.append(list(messages))
            self.issued += 1
            call = {"name": "search_docs", "args": {"query": "住宿费限额"}, "id": "call%d" % self.issued}
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="我先查制度原文。", tool_calls=[call]))]
            )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="本轮收尾。"))])

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture(autouse=True)
def _offline_search_leg(monkeypatch):
    """检索腿打桩 + 进程内装箱账清零：本钉只管形状，不管 room，也不开一次 socket。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(2)))
    books = [book for book in (getattr(tools, "_pack_ledger", None), getattr(tools, "_retrieval_pack_support", None)) if book is not None]
    for book in books:
        book.clear()
    yield
    for book in books:
        book.clear()


def _nested_session(rounds=ROUNDS):
    """真装配连问若干轮：父线程**恒定**，每轮换 request/trace/task（生产就是每请求新生成）。

    形状与 ``tests/test_r117_ledger_turn_scoped.py`` 的 ``_nested_session`` 同源：
    父图节点 = ``orchestrator._make_worker_wrapper(child, "doc")``，
    子图 = 真 ``create_react_agent`` + 真 ``DOC_PROMPT`` + 真 ``search_docs`` + 带 checkpointer，
    子线程 = ``{父会话}:doc``。
    """
    saver = MemorySaver()
    model = ShapeModel(seen=[], round_starts=[], issued=0)
    child = create_react_agent(
        model, [tools.search_docs], prompt=orchestrator.DOC_PROMPT, checkpointer=saver
    )
    builder = StateGraph(AgentState)
    builder.add_node("doc", orchestrator._make_worker_wrapper(child, "doc"))
    builder.add_edge(START, "doc")
    builder.add_edge("doc", END)
    parent = builder.compile(checkpointer=saver)

    thread_id = "r127-" + os.urandom(5).hex()
    questions = []
    for turn in range(1, rounds + 1):
        question = "住宿费限额是多少（第 %d 问）" % turn
        questions.append(question)
        parent.invoke(
            {"messages": [HumanMessage(content=question)]},
            {
                "configurable": {
                    "thread_id": thread_id,
                    "username": "r127",
                    "role": "staff",
                    "department": "财务部",
                    "request_id": "req-%s-%d" % (thread_id, turn),
                    "trace_id": "trace-%s-%d" % (thread_id, turn),
                    "task_id": "task-%s-%d" % (thread_id, turn),
                    "principal": {
                        "user_id": "u-r127",
                        "username": "r127",
                        "roles": ["staff"],
                        "department": "财务部",
                        "status": "active",
                    },
                }
            },
        )
    return model, saver, "%s:doc" % thread_id, questions


def _orchestrator_source():
    return Path(orchestrator.__file__).read_text(encoding="utf-8")


# ==================== 判据 ① · 形状钉：子图每轮只看得到本轮那条问题 ====================


def test_worker_child_prompt_is_system_plus_this_round_question_every_round():
    """连问 3 轮（父线程恒定）：子图每轮**开局**的 prompt 必须恰是 [SystemMessage, 本轮 HumanMessage]。"""
    model, _saver, _child_thread, questions = _nested_session()

    starts = model.round_starts
    assert len(starts) == ROUNDS, "每轮该且只该有一次『开局进模型』，实测 %d 次" % len(starts)
    for index, prompt in enumerate(starts):
        kinds = [type(message).__name__ for message in prompt]
        assert kinds == ["SystemMessage", "HumanMessage"], (
            "R127 判据①：第 %d 轮子图开局的 prompt 形状不是 [system, 本轮问题]，实测 %s。"
            "若这里变红，说明装配已经能跨轮 resume（清掉了继承的父 config / 把子图直接当节点），"
            "那么跟进单 §55 的定性、orchestrator 的注释、以及 R117 的『跨轮不扣房』口径要一起重开。" % (index + 1, kinds)
        )
        assert str(prompt[-1].content) == questions[index]

    joined = ["\n".join(str(message.content) for message in prompt) for prompt in starts]
    for index, text in enumerate(joined):
        for earlier in questions[:index]:
            assert earlier not in text, (
                "R127 判据①：第 %d 轮的子图 prompt 里读到了第 %d 轮的问题原文 ⇒ 子图已经在回读上一轮，"
                "本钉的前提（跨轮不回读）已不成立。" % (index + 1, joined.index(earlier) + 1)
            )
    for text in joined:
        assert "ToolMessage" not in text


def test_each_round_really_produced_its_own_tool_string_so_the_pin_is_not_vacuous():
    """反空转：每轮子图**确实**各带进过一枚 ToolMessage（真实检索串），下一轮的开局却一枚都不剩。

    没有这一枚，`test_..._every_round` 会因为"子图根本没跑过工具"而假绿。
    """
    model, _saver, _child_thread, _questions = _nested_session()

    kinds_per_call = [[type(message).__name__ for message in prompt] for prompt in model.seen]
    with_tool = [kinds for kinds in kinds_per_call if "ToolMessage" in kinds]
    assert len(with_tool) == ROUNDS, (
        "每轮应当各出现一次『带 ToolMessage 的第二发』，实测 %d 次：%r" % (len(with_tool), kinds_per_call)
    )
    for kinds in with_tool:
        assert kinds.count("ToolMessage") == 1, "本轮内只该有一发检索串，实测 %r" % (kinds,)


def test_child_checkpoint_namespace_changes_every_round_so_history_is_never_read_back():
    """机制账：同一枚子线程 ``{父会话}:doc`` 下，``checkpoint_ns`` 每轮换一枚新 uuid ⇒ 只写不读。

    这一枚是"为什么"那一半：thread 恒定（``orchestrator.py`` 的 ``f"{parent}:{name}"``），
    回读失败**不是**因为线程号变了，而是因为 langgraph 给嵌套 invoke 注入的 ``checkpoint_ns``
    逐轮换。谁要把这行改成稳定 ns，本钉当场红。
    """
    _model, saver, child_thread, _questions = _nested_session()

    assert child_thread in saver.storage, "子线程 %r 压根没写过 checkpoint：装配形状与判据①描述不一致" % child_thread
    namespaces = set(saver.storage[child_thread].keys())
    assert len(namespaces) == ROUNDS, (
        "R127 判据①：跑了 %d 轮，子线程 %r 的 checkpoint_ns 却只有 %d 枚（%r）。"
        "枚数 == 轮数 是【当前装配】的指纹（每轮写一本新账、永不回读）。只剩 1 枚有两种读法："
        "① 真的能跨轮回读了；② 只是把 checkpoint_ns 钉死成一枚而仍然不回读——定策纸 §1-2 实测过 "
        "② 是无效修法。谁是因由 test_worker_child_prompt_is_system_plus_this_round_question_every_round"
        "判，两枚要一起读。"
        % (ROUNDS, child_thread, len(namespaces), sorted(namespaces))
    )
    assert "" not in namespaces, (
        "子线程下出现了空 checkpoint_ns %r：ns 已被钉死，装配形状与本钉的描述不一致。"
        % (sorted(namespaces),)
    )
    assert all(name.startswith("doc:") for name in namespaces), (
        "checkpoint_ns 应当带父节点名 'doc' 前缀（langgraph 注入的 task 命名空间），实测 %r" % sorted(namespaces)
    )


# ==================== 判据 ① 的反证 (b) · 四条腿的 checkpointer 一枚都不许多也不少 ====================


def test_four_worker_children_still_carry_the_parent_checkpointer():
    """doc/data/chart/export 四张子图各自挂的必须**就是**父图那枚 checkpointer 对象。

    钉的是"带着但不回读"这个**当前**形状：摘掉 ``checkpointer=`` 让本钉红（那是 R128 的另一刀，
    要显式改这里才算批过）；换成第二枚 saver 也让本钉红。
    """
    for name in WORKER_GRAPHS:
        graph = getattr(orchestrator, name)
        assert graph.checkpointer is orchestrator._checkpointer, (
            "R127 判据①反证(b)：%s 的 checkpointer 不再是模块级那枚 _checkpointer（实测 %r）。"
            "定策纸 §1-2 的结论『带 checkpointer，但每轮换 checkpoint_ns ⇒ 只写不读』只对**当前**装配成立；"
            "撤掉它是 R128/乙-2 的决策，必须连同本钉、注释、契约三段一起改。" % (name, graph.checkpointer)
        )


# ==================== 判据 ② · 注释与事实同色（摘掉注释不会误伤判据①，反之亦然） ====================


def test_worker_subgraph_section_comment_states_the_real_shape():
    """`:201` 那句段标题不许再写"可持久化"了事：必须限定在"仅本轮内"，并指名跨轮不回读。"""
    source = _orchestrator_source()
    headers = [line for line in source.splitlines() if "Worker 子图" in line]
    assert len(headers) == 1, "段标题应当唯一，实测 %r" % headers
    header = headers[0]

    assert "带 checkpointer" in header
    assert "仅本轮内" in header, (
        "R127 判据②：段标题没写『仅本轮内』——那句与事实不符的老注释（可持久化）不许回来。"
    )
    assert "跨轮不回读" in header, "R127 判据②：段标题必须明写『跨轮不回读』，否则下一个人还会当它有记忆。"
    assert "checkpoint_ns" in header, "R127 判据②：注释要点名真凶 checkpoint_ns，不能只说结论。"
    assert "R118" in header or "R127" in header, "R127 判据②：注释必须指名 R118/R127，防被写回老说法。"
    assert "带 checkpointer，可持久化" not in source, (
        "R127 判据②反证(a)：全仓源码里又出现了裸的『带 checkpointer，可持久化』。"
    )


def test_child_thread_comment_names_the_stable_thread_and_the_rotating_namespace():
    """`child_conf = {"thread_id": f"{parent}:{name}"}` 旁边那段注释也要同色：线程稳定 ≠ 能回读。"""
    source = _orchestrator_source()
    lines = source.splitlines()
    anchors = [index for index, line in enumerate(lines) if 'child_conf = {"thread_id": f"{parent}:{name}"}' in line]
    assert len(anchors) == 1, "子线程号那一行应当唯一，实测 %d 处" % len(anchors)
    window = "\n".join(lines[max(0, anchors[0] - 8) : anchors[0]])
    assert "R118" in window or "R127" in window, "子线程号上方 8 行内必须留一条指名 R118/R127 的注释。"
    assert "checkpoint_ns" in window, "那段注释必须点明 checkpoint_ns 逐轮换 ⇒ 跨轮不回读。"
    assert "稳定" in window or "恒定" in window, "那段注释要写清 thread_id 本身是稳定的，免得下一个人去查错方向。"
