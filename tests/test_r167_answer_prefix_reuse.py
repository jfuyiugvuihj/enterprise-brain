# -*- coding: utf-8 -*-
"""R167（= R43b）· 答案腿 prompt 的可复用前缀：固定指令在前、可变内容在末尾。

判据出处：跟进单 §84 六（本单全文）、§81 三（R43 拆两半的原单与硬约束）。R43a（``4586bb4``）
交的是**改写腿** ``REWRITE_PROMPT`` 那半张（可复用前缀 39.7% → 85.5%）；本件把同一套打法落到
**答案腿**，口径逐字沿用 R43a：同角色、同档、连发两发、逐字节比公共前缀。全程离线，一次模型
都不打（``tests/conftest.py`` 的哨兵 ``__eb_test_disabled__`` + socket 闸门之下必须绿）。

==================== 判据① · 现状账（施工基点 ``3d7ced6`` 逐枚实测；字节 = UTF-8）====================

答案腿今天进模型的 prompt 只有四处组装点，全在本单写域内。"框架" = ``<|role|>\n``：provider 按
ChatML 渲染，角色标签本身就是字节，所以"段序"必须被量到（R43a 那条腿只有一枚 user 消息，不必
面对这件事；这里不量框架就会把"把资料挪到 system 之前"读成没变化）。

  腿            组装点                          段序（F=固定 V=可变，单位 B）                可复用前缀
  1 supervisor  orchestrator.py:390 ,:404        F MAIN_SYSTEM 774 → V 记忆块 → V 画像块 → V 问题   783（框架 9 + 774）
  2 doc 应答     orchestrator.py:216 → :644       F DOC_PROMPT 186 → V 问题 → V 工具调用 → V 检索料   207（11+186+1+9）
  3 data/chart/export  orchestrator.py:217-219    同上，固定段 268 / 182 / 71                    289 / 203 / 92
  4 闲聊作答     nodes.py:1388                    V 问题（固定段 0 B）                            9（只剩角色标签）
  5 plan 拆题    nodes.py:1463-1469               F 99 → V 问题                                  108 —— 🔴 今天走不到

可变段自带两枚标签（27 B 的 ``\\n\\n【用户历史记忆】\\n``、21 B 的 ``\\n\\n【用户画像】\\n``），紧贴
各自内容、落在固定块之后。整段里唯一排在可变字节之后的固定字节，就是那枚 21 B 的画像标签（它落在
记忆正文之后）：它是段标签不是指令，挪它等于改 prompt 的可读文本（判据④ 禁），净收益 21 B ⇒ 登记为
"已知不可挪"。除此之外**没有任何一枚固定指令字节排在可变字节之后**。逐处点名"可变内容夹在固定指令
中间"＝**本写域内 0 处**，由
``test_no_prompt_byte_sits_after_variable_bytes_in_the_two_files`` 按 AST 逐枚数出来（两枚文件今天
共数出 20 余处"固定落在可变之后"的候选，逐枚定性全是 ``logger.*`` 日志行、审批终答散文与 trace
标识，一枚都不上模型；候选被数成 0 会先红，那是尺子坏了）。

判据② 的合成样本实测（同一把尺、同一份夹具；分母一并钉进用例，那几个百分比要能复算）：

  supervisor 同用户两问          893 /  939 B = 95.10%
  supervisor 跨用户(对方有记忆)  812 /  939 B = 86.47%   ← 多出的 29 B = 两枚段标签 + 项目符号
  supervisor 跨用户(对方无记忆)  784 /  939 B = 83.49%   ← 保证值：固定块 783 B + 一枚框架换行
  doc 应答腿 跨用户              207 / 3385 B =  6.11%   ← 前缀之后全是问题与检索料，无可挪固定字节
  闲聊作答腿                       9 /   55 B = 16.36%   ← 这一腿今天没有固定段，补指令 = 改语义（禁）

⇒ **判据② 在本写域内净位移 0 字节**：改前 = 改后，逐枚见上表。再多一寸只有两条路——把按题抖的记忆
或检索料提到问题之前（前缀当场按题抖，等于没有），或把部门提进可命中段（撞硬红线）。剩下三处真夹心
全在写域外，本单只具名登记、不动手：
``app/agents/tools.py:1039`` pandas 代码腿 F 33 → V 列结构 → **F 242 落在其后** → V 问题；
``app/api/v1/chat.py:961`` 追问改写腿 F 2 行 → V 上一问 → V 当前问 → **F 39 尾句**；
``app/api/v1/chat.py:1319`` 旧 ``/chat`` 答案腿 F 角色行 → V 参考文档 → V 问题 → **F 149 ``## 要求`` 尾块**。
这三处的字节数被 ``test_the_three_registered_sandwiches_all_live_outside_the_write_scope`` 复算钉住：
谁修好了其中一处，本件当场红，账就得重刻（这是登记，不是豁免）。

判据① 点名要查的三类漏网，实测结论：
- 时间戳 / uuid：``planner.py:9`` 的 ``task_id`` 带 ``uuid4().hex[:8]``、``orchestrator.py:400`` 的
  ``supervisor-replay-{uuid4}``、``profile.py:110`` 读回的 ``updated_at``（它进 ``get_profile`` 的
  dict，被 ``compose_profile_context`` 整枚丢掉）——三处**都不进 prompt 字节**，本件钉在门外。
- 字典序：``synthesize`` 按 ``worker_results`` 的**完成顺序**拼终答（``nodes.py:1554``），并行 worker
  谁先落谁在前 ⇒ 终答字节序按完成顺序抖。它今天不进任何 prompt（supervisor 报文恒等于
  ``[sys_msg, current_user_msg]``，R27 已钉），所以不破前缀；改它等于改用户可见正文的次序 =
  判据④ 禁的"语义"，本单只登记不修。这条序一旦哪天被接进 prompt，前缀当场按完成顺序抖。
- 身份：画像块带 ``department:`` / ``role:``（``profile.py:19-28``）。它今天排在固定块之后、且排在
  **按题抖**的记忆块之后 ⇒ 跨用户最多领到 783 B 固定字节，一个身份字节都领不到。这枚次序是
  **安全序不是漏网**：把画像提到记忆块之前能多得 41 B 前缀，而共享前缀缓存按字节命中，部门进
  可命中段 = 跨用户越权面（硬红线原文）。本单反向把这条例外钉死。

🔴 本件只钉形状，一个字都不宣布"前缀缓存生效"：本机 Ollama 与 Docker 今天不可用，真机那一格
留给跑分窗；外部锚（llm-d TTFT 0.542 s / 94.865 s）不是我们的读数。
"""
import ast
import hashlib
import io
import os
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app.agents import nodes, orchestrator, tools
from app.agents.orchestrator import (
    CHART_PROMPT,
    DATA_PROMPT,
    DOC_PROMPT,
    EXPORT_PROMPT,
    MAIN_SYSTEM,
    doc_graph,
    main_agent_node,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODES_SRC = os.path.join(REPO, "app", "agents", "nodes.py")
ORCH_SRC = os.path.join(REPO, "app", "agents", "orchestrator.py")
WRITE_SCOPE = ("app/agents/nodes.py", "app/agents/orchestrator.py")

#: 判据① 那张表的字节分母。改任何一段固定指令都会打红这张表——这是有意的：前缀占比的分母
#: 必须跟着账走，不许一边改 prompt 一边沿用旧读数。
ACCOUNT_FIXED_BYTES = {
    "MAIN_SYSTEM": 774,
    "DOC_PROMPT": 186,
    "DATA_PROMPT": 268,
    "CHART_PROMPT": 182,
    "EXPORT_PROMPT": 71,
    "PLAN_INSTRUCTION": 99,
}
#: 写域外那三处真夹心：落在可变内容之后的固定字节数（复算见 _trailing_fixed_bytes）。
ACCOUNT_DEBT_BYTES = {
    ("app/agents/tools.py", "_llm_pandas_code"): 242,
    ("app/api/v1/chat.py", "_rewrite_followup"): 39,
    ("app/api/v1/chat.py", "generate"): 149,
}

MEMORY_LABEL = "\n\n【用户历史记忆】\n"
PROFILE_LABEL = "\n\n【用户画像】\n"
FRAME_USER = "<|user|>\n"
FRAME_SYSTEM = "<|system|>\n"

Q_A = "员工出差住宿费的报销上限是多少"
Q_B = "今年各门店营收排名前三是谁"
MEM_A = ["年假 5 天"]
PROFILE_A = "department: 财务部\nrole: accountant"

#: 泄漏面（口径与 R43a 逐字相同）。
CLOCK_PATTERNS = (
    r"\d{4}-\d{2}-\d{2}",
    r"\d{2}:\d{2}:\d{2}",
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}",
    r"\b\d{10,13}\b",
    r"uuid",
)
IDENTITY_TOKENS = (
    "principal",
    "department",
    "dept",
    "user_id",
    "userid",
    "owner",
    "tenant",
    "scope_reason",
    "密级",
    "权限",
    "部门",
    "角色",
)

#: 假检索料刻意避开 IDENTITY_TOKENS 里的每个词：那批字是"资料"，权限判定不在报文里。
MATERIAL_A = "周转天数按期末库存除以日均出库量计算并需季度复核。"
SOURCE_A = "库存周转口径"

ROLE_TAGS = {"human": "user", "system": "system", "ai": "assistant", "tool": "tool"}


def framed(messages) -> str:
    """把"发请求之前组装出来的那串 prompt"渲染成一条可比字节的串。"""
    return "".join("<|%s|>\n%s\n" % (ROLE_TAGS.get(m.type, m.type), m.content) for m in messages)


def as_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def common_prefix(a: str, b: str) -> str:
    limit = min(len(a), len(b))
    index = 0
    while index < limit and a[index] == b[index]:
        index += 1
    return a[:index]


# ==================== 尺子：一把 AST 量"固定落在可变之后"====================


def segments(node):
    """把一枚表达式摊成 ``[("F"|"V", 字节数)]``：字面量是 F，其余（名字/调用/插值）是 V。"""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, str):
            return []
        return [("F", len(node.value.encode("utf-8")))]
    if isinstance(node, ast.JoinedStr):
        return [row for part in node.values for row in segments(part)]
    if isinstance(node, ast.FormattedValue):
        return [("V", 0)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return segments(node.left) + segments(node.right)
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call, ast.Starred)):
        return [("V", 0)]
    return [("V", 0)]


def trailing_fixed_bytes(node) -> int:
    """第一枚可变字节之后还跟着多少固定字节 —— 夹心的尺寸，0 = 这一处形状是对的。"""
    seen_variable = False
    total = 0
    for kind, size in segments(node):
        if kind == "V":
            seen_variable = True
        elif seen_variable:
            total += size
    return total


def leading_fixed_bytes(node) -> int:
    """第一枚可变字节**之前**有多少固定字节 —— 这一段才是服务端可复用的前缀本体。"""
    total = 0
    for kind, size in segments(node):
        if kind == "V":
            break
        total += size
    return total


def _parent_map(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _statement_of(node, parents, source):
    current = node
    while not isinstance(current, (ast.Assign, ast.AnnAssign, ast.Return, ast.Expr, ast.If, ast.Module)):
        current = parents.get(current)
        if current is None:
            return None, ""
    return current, ast.get_source_segment(source, current) or ""


def sandwich_candidates(path):
    """数出一份文件里每一处"固定落在可变之后"，连同它所在的语句原文一起交回。"""
    source = io.open(path, encoding="utf-8").read()
    tree = ast.parse(source)
    parents = _parent_map(tree)
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.JoinedStr, ast.BinOp)):
            continue
        size = trailing_fixed_bytes(node)
        if not size:
            continue
        statement, text = _statement_of(node, parents, source)
        rows.append({"line": node.lineno, "trailing": size, "statement": text.strip()})
    return rows


def is_prompt_statement(text: str) -> bool:
    """这一枚语句上的串会不会进模型？日志行与终答散文都答"不"。"""
    if "logger." in text:
        return False
    markers = ("_make_model", ".invoke(", ".stream(", "HumanMessage(", "SystemMessage(", "prompt")
    return any(marker in text for marker in markers)


def plan_instruction_ast():
    for node in ast.walk(ast.parse(io.open(NODES_SRC, encoding="utf-8").read())):
        if isinstance(node, ast.JoinedStr):
            literals = [part for part in node.values if isinstance(part, ast.Constant)]
            variables = [part for part in node.values if not isinstance(part, ast.Constant)]
            if variables and any("拆成" in str(part.value) for part in literals):
                return node
    raise AssertionError("plan() 里那枚固定指令字面量找不到了")


# ==================== 取证边界：provider 边界，发请求之前 ====================


class Transport:
    """把 ``ChatOpenAI._generate`` 换成记录器：它是"发请求之前"的最后一道边界。

    判据③ 明写比的是**发请求之前组装出来的那串 prompt**、不许靠日志。这里不真打模型（conftest
    的 socket 闸门也打不出去），也不换产品装配：supervisor 腿走真 ``main_agent_node``，doc 应答腿
    走真 ``doc_graph``，本类只站在报文出口记账。挂的是普通函数而不是绑定方法：langchain 以
    ``self._generate(input, ...)`` 调用，绑定方法会先吃掉 ChatOpenAI 那一枚位置。
    """

    def __init__(self, monkeypatch, replies=()):
        self.captured = []
        self._replies = list(replies)
        monkeypatch.setattr(ChatOpenAI, "_generate", self._generate)

    def _generate(self, input=None, stop=None, run_manager=None, **kwargs):  # noqa: A002 - 形参名由 langchain 定
        messages = input if input is not None else kwargs.get("messages")
        self.captured.append(list(messages))
        index = min(len(self.captured) - 1, max(len(self._replies) - 1, 0))
        reply = self._replies[index] if self._replies else AIMessage(content="已作答。")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    @property
    def prompts(self):
        return [framed(messages) for messages in self.captured]

    @property
    def roles(self):
        return [[m.type for m in messages] for messages in self.captured]


def search_reply(query):
    return AIMessage(
        content="",
        tool_calls=[{"name": "search_docs", "args": {"query": query}, "id": "call-r167", "type": "tool_call"}],
    )


def supervisor_state(question, long_mem=(), profile_ctx=""):
    return {
        "messages": [HumanMessage(content=question)],
        "memory": {"long": list(long_mem), "work": [], "profile": {}, "profile_context": profile_ctx},
        "intent": "task",
    }


def supervisor_prompt(monkeypatch, question, long_mem=(), profile_ctx=""):
    transport = Transport(monkeypatch)
    main_agent_node(supervisor_state(question, long_mem, profile_ctx))
    assert len(transport.captured) == 1, transport.roles
    return transport.prompts[0]


class _FakePipeline:
    """假检索管线：交回真形状的命中（键名照 ``tests/test_r112_prompt_packing.py`` 那套抄）。"""

    def __init__(self, hits):
        self.hits = hits

    def search_for_principal(self, query, principal, top_k, context_pack=False):
        return list(self.hits), [query]


def _doc_config(thread_id):
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r167", "role": "clerk", "department": "仓储部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf.update(
        {
            "thread_id": thread_id,
            "request_id": "req-" + thread_id,
            "trace_id": "trace-" + thread_id,
            "task_id": "task-" + thread_id,
            "worker": "doc",
        }
    )
    return {"configurable": conf}


def _hits(count, filler, source):
    from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS

    body = (filler * 90)[:DOC_HIT_CONTENT_CHARS]
    return [
        {"source": "%s%d.pdf" % (source, index), "chunk_index": index, "_score": 0.71, "content": body}
        for index in range(1, count + 1)
    ]


def doc_leg_prompt(monkeypatch, question, seed):
    """真 ``doc_graph`` 跑一轮，取第二发（手里已经有检索资料的那一发）的报文。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(2, MATERIAL_A, SOURCE_A)))
    transport = Transport(monkeypatch, replies=[search_reply("周转 天数"), AIMessage(content="按季度复核。")])
    doc_graph.invoke({"messages": [HumanMessage(content=question)]}, config=_doc_config("thread-r167-" + seed))
    assert len(transport.captured) == 2, transport.roles
    return transport.prompts[1], transport.captured[1]


# ==================== 判据① · 现状账：分母、段序、夹心普查 ====================


def test_the_account_fixed_segments_measure_what_the_ledger_claims():
    sizes = {
        "MAIN_SYSTEM": len(as_bytes(MAIN_SYSTEM.content)),
        "DOC_PROMPT": len(as_bytes(DOC_PROMPT)),
        "DATA_PROMPT": len(as_bytes(DATA_PROMPT)),
        "CHART_PROMPT": len(as_bytes(CHART_PROMPT)),
        "EXPORT_PROMPT": len(as_bytes(EXPORT_PROMPT)),
        "PLAN_INSTRUCTION": len(as_bytes(_leading_text(plan_instruction_ast()))),
    }
    assert sizes == ACCOUNT_FIXED_BYTES, sizes


def _leading_text(joined) -> str:
    """plan 腿那枚固定指令的字面本体（从 AST 取，不手抄）。"""
    return "".join(str(part.value) for part in joined.values if isinstance(part, ast.Constant))


def test_the_supervisor_row_is_frame_plus_fixed_block_then_variable_tail(monkeypatch):
    prompt = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    head = FRAME_USER + MAIN_SYSTEM.content
    assert prompt.startswith(head)
    tail = prompt[len(head):]
    assert tail.startswith(MEMORY_LABEL), tail[:24]
    assert tail.endswith(PROFILE_LABEL + PROFILE_A + "\n" + FRAME_USER + Q_A + "\n")


def test_the_memory_and_profile_labels_sit_behind_the_fixed_block(monkeypatch):
    """两枚标签（27 B / 21 B）紧贴各自内容、落在固定块之后：整段账要能逐字节复算。"""
    prompt = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    head = FRAME_USER + MAIN_SYSTEM.content
    assert len(as_bytes(MEMORY_LABEL)) == 27
    assert len(as_bytes(PROFILE_LABEL)) == 21
    assert prompt[len(head):] == MEMORY_LABEL + "- " + MEM_A[0] + PROFILE_LABEL + PROFILE_A + "\n" + FRAME_USER + Q_A + "\n"


@pytest.mark.parametrize(
    "name,text",
    [
        ("DOC_PROMPT", DOC_PROMPT),
        ("DATA_PROMPT", DATA_PROMPT),
        ("CHART_PROMPT", CHART_PROMPT),
        ("EXPORT_PROMPT", EXPORT_PROMPT),
    ],
)
def test_every_worker_leg_leads_with_its_own_fixed_system_segment(name, text):
    assert framed([SystemMessage(content=text), HumanMessage(content=Q_A)]).startswith(FRAME_SYSTEM + text + "\n")
    assert not text.endswith("\n"), "固定段末尾不许多带换行：那会把可变内容往前提一位"
    assert len(as_bytes(text)) == ACCOUNT_FIXED_BYTES[name]


def test_the_captured_prompts_are_the_ones_the_real_graph_sends(monkeypatch):
    """取证点自检：捕获到的确实是真图发出去的报文，不是本文件自己拼的第二套装配。"""
    transport = Transport(monkeypatch, replies=[search_reply("周转"), AIMessage(content="好。")])
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(1, MATERIAL_A, SOURCE_A)))
    doc_graph.invoke({"messages": [HumanMessage(content=Q_A)]}, config=_doc_config("thread-r167-selfcheck"))

    assert transport.roles == [["system", "human"], ["system", "human", "ai", "tool"]], transport.roles
    assert str(transport.captured[0][0].content) == DOC_PROMPT
    assert str(transport.captured[0][1].content) == Q_A
    assert MATERIAL_A in str(transport.captured[1][-1].content)


@pytest.mark.parametrize("path", [NODES_SRC, ORCH_SRC], ids=list(WRITE_SCOPE))
def test_no_prompt_byte_sits_after_variable_bytes_in_the_two_files(path):
    """判据① 的机器版本：本写域内"可变内容夹在固定指令中间"= 0 处。

    两头都防：候选被数成 0 说明尺子坏了（两枚文件今天确实数得出 20 余处，全在日志与散文里），
    候选里冒出一处落在 prompt 语句上就是真夹心。
    """
    candidates = sandwich_candidates(path)
    assert candidates, "%s 里一处'固定落在可变之后'都没有？尺子坏了，先修尺子" % os.path.basename(path)

    on_the_wire = [row for row in candidates if is_prompt_statement(row["statement"])]
    assert on_the_wire == [], "这些 prompt 组装点把固定指令排到了可变内容之后：%s" % on_the_wire


def test_the_three_registered_sandwiches_all_live_outside_the_write_scope():
    """写域外三处真夹心：登记在册、字节数复算，本单一枚都不动。"""
    for (relative, function_name), expected in ACCOUNT_DEBT_BYTES.items():
        assert relative not in WRITE_SCOPE, relative
        source = io.open(os.path.join(REPO, relative), encoding="utf-8").read()
        tree = ast.parse(source)
        sizes = [
            trailing_fixed_bytes(node)
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == function_name
            for node in ast.walk(fn)
            if isinstance(node, (ast.JoinedStr, ast.BinOp))
        ]
        assert sizes, (relative, function_name)
        assert max(sizes) == expected, "%s::%s 的固定尾巴现在是 %d B，账上写的是 %d B" % (
            relative,
            function_name,
            max(sizes),
            expected,
        )


# ==================== 判据③：连发两发，前缀字节级相同 ====================


def test_two_supervisor_rounds_from_one_user_share_a_byte_identical_prefix(monkeypatch):
    a = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    b = supervisor_prompt(monkeypatch, Q_B, MEM_A, PROFILE_A)
    assert a != b, "两发内容相同就不是在比前缀"

    prefix = common_prefix(a, b)
    assert prefix == (
        FRAME_USER + MAIN_SYSTEM.content + MEMORY_LABEL + "- " + MEM_A[0] + PROFILE_LABEL + PROFILE_A + "\n" + FRAME_USER
    )
    assert as_bytes(prefix) == as_bytes(a[: len(prefix)])
    assert hashlib.sha256(as_bytes(prefix)).hexdigest() == hashlib.sha256(as_bytes(b[: len(prefix)])).hexdigest()
    assert a[len(prefix):] == Q_A + "\n"
    assert b[len(prefix):] == Q_B + "\n"


def test_a_second_user_with_no_memory_shares_exactly_the_fixed_block(monkeypatch):
    """跨用户可复用前缀 = 固定块本体（+ 一枚框架换行），多一寸都是记忆或身份漏进了前缀。"""
    with_memory = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    without_memory = supervisor_prompt(monkeypatch, Q_A)

    prefix = common_prefix(with_memory, without_memory)
    assert prefix == FRAME_USER + MAIN_SYSTEM.content + "\n", prefix[-40:]
    assert len(as_bytes(prefix)) == len(FRAME_USER) + ACCOUNT_FIXED_BYTES["MAIN_SYSTEM"] + 1
    assert MEMORY_LABEL not in prefix and PROFILE_LABEL not in prefix


def test_the_supervisor_prefix_survives_eight_rounds_and_a_memory_refresh(monkeypatch):
    prompts = [supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A) for _ in range(8)]
    assert len(set(prompts)) == 1, "同一枚问题连发必须逐字节复现"

    refreshed = supervisor_prompt(monkeypatch, Q_A, ["加班费 走调休"], PROFILE_A)
    assert common_prefix(prompts[0], refreshed) == FRAME_USER + MAIN_SYSTEM.content + MEMORY_LABEL + "- "


def test_the_doc_leg_prompt_orders_fixed_then_question_then_material(monkeypatch):
    prompt, messages = doc_leg_prompt(monkeypatch, Q_A, "order")
    head = FRAME_SYSTEM + DOC_PROMPT + "\n"
    assert prompt.startswith(head)
    assert prompt[len(head):].startswith(FRAME_USER + Q_A + "\n"), prompt[:200]
    assert prompt.endswith(str(messages[-1].content) + "\n"), "检索资料之后不许再排固定指令"
    assert MATERIAL_A in str(messages[-1].content)


def test_two_doc_leg_rounds_share_a_byte_identical_prefix_across_users(monkeypatch):
    a, _ = doc_leg_prompt(monkeypatch, Q_A, "u1")
    b, _ = doc_leg_prompt(monkeypatch, Q_B, "u2")

    prefix = common_prefix(a, b)
    assert prefix == FRAME_SYSTEM + DOC_PROMPT + "\n" + FRAME_USER
    assert len(as_bytes(prefix)) == len(FRAME_SYSTEM) + ACCOUNT_FIXED_BYTES["DOC_PROMPT"] + 1 + len(FRAME_USER)
    assert hashlib.sha256(as_bytes(prefix)).hexdigest() == hashlib.sha256(as_bytes(b[: len(prefix)])).hexdigest()
    assert MATERIAL_A not in prefix and SOURCE_A not in prefix


def test_retrieved_material_never_precedes_the_question(monkeypatch):
    """反"夹心"主钉：资料一旦被提到问题之前，答案腿的可复用前缀当场短一截。"""
    prompt, _ = doc_leg_prompt(monkeypatch, Q_A, "material")
    assert prompt.index(Q_A) < prompt.index(MATERIAL_A)
    assert prompt[: prompt.index(Q_A)] == FRAME_SYSTEM + DOC_PROMPT + "\n" + FRAME_USER


def test_the_prefix_share_is_already_at_its_ceiling_for_every_reachable_leg(monkeypatch):
    """判据②：X% = Y%。每枚可达腿今天的前缀占比就是它的上限，本单净位移 0 字节。

    上限 = 固定块 + 框架。想再多一寸只有两条路：把按题抖的记忆/检索料提到问题之前（前缀当场
    按题抖），或把部门提进固定块之后（撞硬红线）。所以这张表不是在报"没干活"，是在报
    "这一格里已经没有可挪的字节"。
    """
    shares = {}

    same_user_a = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    same_user_b = supervisor_prompt(monkeypatch, Q_B, MEM_A, PROFILE_A)
    shares["supervisor(同用户两问)"] = (common_prefix(same_user_a, same_user_b), same_user_a)
    foreign = supervisor_prompt(monkeypatch, Q_A, ["加班费 走调休"], "department: 仓储部\nrole: clerk")
    bare = supervisor_prompt(monkeypatch, Q_A)
    shares["supervisor(跨用户)"] = (common_prefix(same_user_a, foreign), same_user_a)
    shares["supervisor(有无记忆)"] = (common_prefix(same_user_a, bare), same_user_a)
    doc_a, _ = doc_leg_prompt(monkeypatch, Q_A, "share-a")
    doc_b, _ = doc_leg_prompt(monkeypatch, Q_B, "share-b")
    shares["doc 应答(跨用户)"] = (common_prefix(doc_a, doc_b), doc_a)
    chat = framed([HumanMessage(content=Q_A)])
    shares["闲聊作答"] = (FRAME_USER, chat)

    for leg, (prefix, total) in shares.items():
        assert 0 < len(as_bytes(prefix)) <= len(as_bytes(total)), (leg, prefix, total)
    assert len(as_bytes(shares["supervisor(跨用户)"][0])) == 812, shares["supervisor(跨用户)"]
    assert len(as_bytes(shares["supervisor(有无记忆)"][0])) == 784, shares["supervisor(有无记忆)"]
    assert len(as_bytes(shares["doc 应答(跨用户)"][0])) == 207, shares.keys()
    totals = {leg: len(as_bytes(total)) for leg, (_, total) in shares.items()}
    #: 分母同样钉住：回执里那几个百分比必须能由这张表复算，合成样本的尺寸不许漂。
    assert sorted(totals.values()) == [55, 939, 939, 939, 3385], totals
    assert round(100.0 * 812 / totals["supervisor(跨用户)"], 1) == 86.5, totals
    assert round(100.0 * 207 / totals["doc 应答(跨用户)"], 1) == 6.1, totals
    assert len(as_bytes(shares["闲聊作答"][0])) == len(FRAME_USER), "闲聊腿今天没有固定段：前缀只剩角色标签"


def test_the_plan_leg_sends_no_prompt_at_all_in_production(monkeypatch):
    """判据① 的诚实一格：plan 腿那 108 B 今天走不到，因此不计进前缀账。

    ``build_task_plan`` 对任何非空问题恒交回 ≥1 条任务（``planner.py`` 末尾兜底那一格），
    ``plan()`` 在发问之前就 return ⇒ 那枚 LLM 拆题报文是死路。钉"零发"是因为它一旦复活，前缀
    形状得按同一把尺重测——本件不肯替一条走不到的腿宣称收益。
    """
    transport = Transport(monkeypatch)
    for question in ("", "员工手册在哪", "各部门人均产值以及代码量，哪个部门更该加人"):
        messages = [HumanMessage(content=question)] if question else []
        nodes.plan({"messages": messages, "intent": "task"})
    assert transport.captured == [], transport.roles


# ==================== 红线：身份 / 时钟 / uuid / 字典序 / 档位 ====================


def test_no_identity_bytes_reach_the_cross_user_prefix(monkeypatch):
    prompt = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    fixed = FRAME_USER + MAIN_SYSTEM.content
    assert prompt.startswith(fixed)
    lowered = fixed.lower()
    for token in IDENTITY_TOKENS:
        assert token not in lowered, "固定块里出现了身份词 %r" % token
    assert "department" in prompt and prompt.index("department") > prompt.index(MEMORY_LABEL)


def test_the_profile_block_stays_behind_the_question_dependent_memory_block(monkeypatch):
    """安全序钉：画像（``department`` / ``role``）必须排在**按题抖**的记忆块之后。

    把画像提到前面能多得 41 B 前缀，但那等于把部门塞进一段跨轮可命中的字节：共享前缀缓存按
    字节命中，部门进可命中段 = 跨用户越权面。所以这枚次序是设计，不是没来得及优化。
    """
    prompt = supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    assert prompt.index(MEMORY_LABEL) < prompt.index(PROFILE_LABEL) < prompt.index(FRAME_USER + Q_A)


def test_worker_leg_prompts_carry_no_identity_bytes_at_all(monkeypatch):
    """doc 应答腿整串报文里身份一个字都没有——权限过滤住在工具层，不写进 prompt。"""
    prompt, _ = doc_leg_prompt(monkeypatch, Q_A, "identity")
    lowered = prompt.lower()
    for token in IDENTITY_TOKENS:
        assert token not in lowered, "worker 腿 prompt 带上了身份词 %r" % token
    assert "仓储部" not in prompt and "clerk" not in prompt


def test_no_clock_no_uuid_no_epoch_digits_reach_the_prompt(monkeypatch):
    prompts = [supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A), doc_leg_prompt(monkeypatch, Q_A, "clock")[0]]
    for prompt in prompts:
        for pattern in CLOCK_PATTERNS:
            assert not re.search(pattern, prompt), "prompt 里出现了 %s" % pattern


def test_worker_completion_order_cannot_reach_the_supervisor_prompt(monkeypatch):
    """字典序钉：上一轮 worker 谁先落，都不许改本轮 supervisor 的报文字节。"""

    def messages_for(order):
        rows = [HumanMessage(content=Q_A)]
        for worker in order:
            rows.append(AIMessage(content="【%s Agent 返回】\n结论甲" % worker))
        return rows

    first = Transport(monkeypatch)
    state = supervisor_state(Q_A)
    state["messages"] = messages_for(["doc", "data"])
    main_agent_node(state)
    second = Transport(monkeypatch)
    state = supervisor_state(Q_A)
    state["messages"] = messages_for(["data", "doc"])
    main_agent_node(state)

    assert first.prompts == second.prompts
    assert "Agent 返回" not in first.prompts[0]


def test_the_declared_lane_changes_the_legs_not_the_prompt_bytes(monkeypatch):
    """R141 的两张表一字不动，且档位读数不许渗进 prompt 字节。"""
    assert nodes.LANE_WORKERS == {
        nodes.LANE_QA: ("doc",),
        nodes.LANE_ANALYSIS: ("doc", "data", "chart"),
        nodes.LANE_REPORT: ("doc", "data", "chart", "export"),
    }
    assert nodes.LANE_REQUIRED_WORKERS == {
        nodes.LANE_QA: (("doc", "abstained"),),
        nodes.LANE_ANALYSIS: (("data", "has_data"),),
        nodes.LANE_REPORT: (("export", "always"), ("data", "has_data")),
    }

    transport = Transport(monkeypatch)
    for declared in ("", "qa", "analysis", "report"):
        state = supervisor_state(Q_A, MEM_A, PROFILE_A)
        state["configurable"] = {nodes.DECLARED_LANE_KEY: declared}
        main_agent_node(state)
    assert len(set(transport.prompts)) == 1
    assert transport.prompts[0].startswith(FRAME_USER + MAIN_SYSTEM.content)


# ==================== 判据④：不许顺手（锚点频次、契约、装配点） ====================


def test_the_r42_anchor_still_parses_and_the_assembly_path_adds_no_ring(monkeypatch, caplog):
    from app.common.stage_timing import R42_LOG_PATTERN

    with caplog.at_level("INFO"):
        supervisor_prompt(monkeypatch, Q_A, MEM_A, PROFILE_A)
    assert "[R42]" not in caplog.text, "supervisor 组装开始敲 R42 的钟：频次也是口径"

    with caplog.at_level("INFO"):
        nodes.classify_route(Q_A)
    line = next((rec.getMessage() for rec in caplog.records if "[R42]" in rec.getMessage()), "")
    match = R42_LOG_PATTERN.search(line)
    assert match and match.group("question") == Q_A, line


def test_the_worker_graphs_are_still_assembled_from_these_constants():
    """本件用常量复现装配：四张子图的 ``prompt=`` 一旦被换掉，复现就与产品脱钩，必须红。"""
    tree = ast.parse(io.open(ORCH_SRC, encoding="utf-8").read())
    assembled = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "create_react_agent"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "prompt" and isinstance(keyword.value, ast.Name):
                assembled.add(keyword.value.id)
    assert {"DOC_PROMPT", "DATA_PROMPT", "CHART_PROMPT", "EXPORT_PROMPT"} <= assembled, assembled


def test_the_fixed_segments_are_still_single_string_literals():
    """固定段仍是单独的字面量：拆成运行时拼接＝把前缀交给运行时的东西决定。"""
    tree = ast.parse(io.open(ORCH_SRC, encoding="utf-8").read())
    literals = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            literals.add(node.targets[0].id)
        elif (
            isinstance(value, ast.Call)
            and getattr(value.func, "id", "") == "HumanMessage"
            and value.keywords
            and isinstance(value.keywords[0].value, ast.Constant)
        ):
            literals.add(node.targets[0].id)
    assert set(ACCOUNT_FIXED_BYTES) - {"PLAN_INSTRUCTION"} <= literals, sorted(literals)


def test_the_rewrite_leg_contract_is_untouched_by_this_ticket():
    """本单不碰改写腿：``REWRITE_PROMPT`` 的 JSON 契约与 ``{{ }}`` 转义仍在原处原样。"""
    from app.rag.retrieval_pipeline import REWRITE_PROMPT

    assert REWRITE_PROMPT.endswith("用户问题: {question}")
    assert '{{"rewrites":["改写1","改写2","改写3"]' in REWRITE_PROMPT