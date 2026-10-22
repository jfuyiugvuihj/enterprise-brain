"""R395 · 身份过 worker 边界这一格：交出去的那一份必须带着它的出处。

全离线：不连模型、不起服务、不动数据；检索腿照 R117 那样 ``monkeypatch`` 掉 ``_get_pipeline``。

病灶（本单取证实量，2026-09-27）：R294（并树 ``70fef378``）把 ``configurable["principal"]``
认成两种投影——在场请求直接下发的 ``Principal`` 对象，以及后台 worker 在消费时刻现取并**签名**
的那一份 dict（签名键 ``principal_provenance=consumption-time``，``app/agents/tools.py``）。
签名长在 configurable 上而不是 ``Principal`` 字段里。``app/api/v1/chat.py`` 与
``deploy/queue_worker.py`` 都按这份契约交出两枚键，而 ``orchestrator._make_worker_wrapper``
只按白名单往子图搬字段：``principal`` 在名单里，与它成对的签名不在。四枚子图里的工具因此
拿到的是「一枚 dict + 没有出处」＝按 R294 判拒。

判据：
① 签了名的那一发，过 ``_make_worker_wrapper`` 之后签名还在，``_tool_principal`` 认得出主体；
② 同一份载荷走真装配时，装箱账照样落一行（钉的是"身份没丢"这件事，不是"日志好看"）；
③ 🔴 没签名的冻结快照照旧拒——本单修的是搬运，不是把闸改松（原文与字节长度一并钉住）。
"""
import logging

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.agents import orchestrator, tools
from app.agents.contracts import Principal
from app.agents.state import AgentState
from app.agents.tools import CONSUMPTION_PRINCIPAL_PROVENANCE, PRINCIPAL_PROVENANCE_KEY

#: R294 交回给图的那一份投影：dict 形状 + 随行签名，两枚键缺一都不算消费时刻现取。
SIGNED_SNAPSHOT = {
    "user_id": "u-r395",
    "username": "r395",
    "roles": ["staff"],
    "department": "财务部",
    "status": "active",
}

#: 工具在缺身份时交回的那句原文（判据③）。51 枚字符 / 87 字节 UTF-8，本单实测值。
REFUSAL_TEXT = "未找到：当前请求缺少有效授权主体（error_code=authorization_required）"
REFUSAL_CHARS = 51
REFUSAL_UTF8_BYTES = 87

KEY_FIGURE = "600"


class FakePipeline:
    def __init__(self, hits):
        self._hits = hits

    def search_for_principal(self, query, principal, top_k, **kwargs):
        return list(self._hits), ["住宿费限额"]


def _hits(count):
    filler = "差旅报销制度条款：住宿费限额按职级分档，部门负责人标准每日 %s 元。" % KEY_FIGURE
    return [
        {
            "source": "差旅报销制度_%d.pdf" % (index + 1),
            "chunk_index": index,
            "_score": 0.9,
            "content": (filler * 20 + str(index))[:500],
        }
        for index in range(count)
    ]


@pytest.fixture(autouse=True)
def _offline_retrieval(monkeypatch):
    monkeypatch.setattr(tools, "_get_pipeline", lambda: FakePipeline(_hits(2)))
    for book in (tools._pack_ledger, getattr(tools, "_retrieval_pack_support", None)):
        if book is not None:
            book.clear()
    yield
    for book in (tools._pack_ledger, getattr(tools, "_retrieval_pack_support", None)):
        if book is not None:
            book.clear()


def _parent_config(**extra):
    conf = {
        "thread_id": "r395-thread",
        "username": "r395",
        "role": "staff",
        "request_id": "req-r395",
        "trace_id": "trace-r395",
        "task_id": "task-r395",
    }
    conf.update(extra)
    return {"configurable": conf}


class _RecordingChild:
    """子图替身：只把 ``_make_worker_wrapper`` 真正交下来的那份 config 记走。"""

    def __init__(self):
        self.config = None

    def invoke(self, _payload, config=None):
        self.config = config
        return {"messages": [AIMessage(content="本轮已按身份检索。")]}


def _run_wrapper(child, config):
    node = orchestrator._make_worker_wrapper(child, "doc")
    node({"messages": [HumanMessage(content="住宿费限额是多少")]}, config)
    return child.config


# ==================== 判据①：签名必须跟着 principal 一起过边界 ====================


def test_the_signed_handoff_survives_the_worker_wrapper():
    """后台 worker 签了名的那一份交出去，过完 wrapper 还得是签了名的。

    今天（R294 并树之后）这一格是断的：白名单搬 ``principal`` 不搬 ``principal_provenance``，
    交进子图的那份 config 里只剩一枚没人作证的 dict。
    """
    config = _parent_config(
        principal=dict(SIGNED_SNAPSHOT),
        **{PRINCIPAL_PROVENANCE_KEY: CONSUMPTION_PRINCIPAL_PROVENANCE},
    )
    child_cfg = _run_wrapper(_RecordingChild(), config)

    child_conf = child_cfg["configurable"]
    assert child_conf["thread_id"] == "r395-thread:doc", child_conf["thread_id"]
    assert child_conf.get("principal") == SIGNED_SNAPSHOT, child_conf.get("principal")
    assert child_conf.get(PRINCIPAL_PROVENANCE_KEY) == CONSUMPTION_PRINCIPAL_PROVENANCE, (
        "签名没跟着身份过边界：子图里的工具只会把这一份 dict 当成入队冻结快照判拒。实测 "
        + repr(child_conf.get(PRINCIPAL_PROVENANCE_KEY))
    )
    principal = tools._tool_principal(child_cfg)
    assert principal.department == "财务部", principal.department
    assert principal.user_id == "u-r395", principal.user_id


def test_a_live_principal_object_is_carried_over_too():
    """在场请求那一臂（``Principal`` 对象）今天就能过界：钉住它，修搬运不许把它改坏。"""
    config = _parent_config(principal=Principal(**SIGNED_SNAPSHOT))
    child_cfg = _run_wrapper(_RecordingChild(), config)
    assert tools._tool_principal(child_cfg).username == "r395"


# ==================== 判据②：真装配里，签名的那一发照样落装箱账 ====================


class _OneShotModel(BaseChatModel):
    """假模型：第一拍并发一发 ``search_docs``，第二拍只抄 prompt 里活着的料。"""

    issued: int = 0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            bodies = "\n".join(
                str(message.content) for message in messages if isinstance(message, ToolMessage)
            )
            read = KEY_FIGURE if KEY_FIGURE in bodies else "NONE"
            answer = "限额读数=%s｜本轮可见串%d字" % (read, len(bodies))
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])
        self.issued += 1
        call = {"name": "search_docs", "args": {"query": "住宿费限额"}, "id": "c%d" % self.issued}
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="我先查制度原文。", tool_calls=[call]))
            ]
        )

    def bind_tools(self, _tools, **_kwargs):
        return self

    @property
    def _llm_type(self):
        return "r395-oneshot"


def _nested_turn(caplog, config):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    child = create_react_agent(
        _OneShotModel(), [tools.search_docs], prompt=orchestrator.DOC_PROMPT,
        checkpointer=MemorySaver(),
    )
    builder = StateGraph(AgentState)
    builder.add_node("doc", orchestrator._make_worker_wrapper(child, "doc"))
    builder.add_edge(START, "doc")
    builder.add_edge("doc", END)
    parent = builder.compile(checkpointer=MemorySaver())
    state = parent.invoke(
        {"messages": [HumanMessage(content="住宿费限额是多少")]}, config=config
    )
    pack_lines = [
        record.getMessage()
        for record in caplog.records
        if "[PromptPack]" in record.getMessage() and "leg=doc" in record.getMessage()
    ]
    answer = str((state.get("worker_results") or {}).get("doc", ""))
    record = (state.get("agent_results") or {}).get("doc") or {}
    return pack_lines, answer, record


def test_a_signed_queue_turn_packs_a_ledger_line(caplog):
    config = _parent_config(
        principal=dict(SIGNED_SNAPSHOT),
        **{PRINCIPAL_PROVENANCE_KEY: CONSUMPTION_PRINCIPAL_PROVENANCE},
    )
    pack_lines, answer, _record = _nested_turn(caplog, config)
    assert pack_lines, "签了名的一轮在子图里装箱账一行都没有＝身份过界就丢了"
    assert KEY_FIGURE in answer, answer


def test_a_live_principal_turn_packs_a_ledger_line(caplog):
    config = _parent_config(principal=Principal(**SIGNED_SNAPSHOT))
    pack_lines, answer, _record = _nested_turn(caplog, config)
    assert pack_lines, "在场请求那一臂也不许空手回来"
    assert KEY_FIGURE in answer, answer


# ==================== 判据③：闸不许因为本单而变松 ====================


def test_an_unsigned_frozen_dict_is_still_refused_by_name():
    """没签名的 dict ＝ 入队冻结快照冒充主体：照旧拒，拒的那句原文与长度一并钉住。"""
    config = _parent_config(principal=dict(SIGNED_SNAPSHOT))
    with pytest.raises(PermissionError) as refused:
        tools._tool_principal(config)
    assert "consumption-time" in str(refused.value), str(refused.value)

    text = tools.search_docs.invoke({"query": "住宿费限额"}, config=config)
    assert text == REFUSAL_TEXT, text
    assert len(text) == REFUSAL_CHARS, len(text)
    assert len(text.encode("utf-8")) == REFUSAL_UTF8_BYTES, len(text.encode("utf-8"))


def test_a_refused_turn_keeps_the_rejection_on_its_face(caplog):
    """过界丢身份的另一种脸：装箱账一行没有，出口就得报 rejected/permission_denied。

    钉的是"拒绝被说成答完了"这一族（``orchestrator.py`` 那行 ``status=`` 日志是本轮唯一现场凭据）。
    它同时是反证刀③的咬点：把 ``app/agents/evidence.py`` 里把拒绝折成 ``permission_denied``
    的那一条改回旧形状，这一发交回的 ``error.code`` 就不再是 ``permission_denied``。
    """
    config = _parent_config(principal=dict(SIGNED_SNAPSHOT))
    pack_lines, answer, record = _nested_turn(caplog, config)
    assert not pack_lines, "没签名的一轮不该装箱：" + repr(pack_lines)
    assert KEY_FIGURE not in answer, answer
    assert record.get("status") == "rejected", record
    assert (record.get("error") or {}).get("code") == "permission_denied", record
