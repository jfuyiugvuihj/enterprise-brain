"""R216（代号 Lacaille）：引对了原文却选错边 —— 互斥口径必须按题面点名的那一侧作答。

病灶与凭据：`docs/testing/a4-metric-conflict-attribution-2026-09-24.md` §5 五分类**第 4 格**
（`metric-08`）。R206a 治派工（第 1 格），R206b 治逐字保真（第 2、3 格），本单治第 4 格：
登记料里同时躺着一份一般条款与一份只管某个范围的特例条款，特例也被引到了，结论段却按一般
条款作答 ⇒ 答反了。🔴 本件的每一枚断言都只讲"哪一侧算结论"，不讲"原话有没有进正文"——
判据① 与派工词都写明这两味收益不许互记。

全程离线：假 provider（``ChatOpenAI._generate`` 记账器，R167 同一打法）+ 合成事件 + 真语料
切块。不发 HTTP、不起服务、不打宿主模型、不动数据库、不改评测集。三样东西是真的：

* 片段正文取自版本控制的 ``documents/制度与口径登记表.txt``，按 ``app/rag/retriever.py`` 那把
  切块尺切出来的整块喂入，本件不抄第二份语料；
* `metric-08` 那一发的名次取自 ``docs/testing/r59b-recall-comparison-2026-09-24.json`` 与
  ``docs/testing/answers-run6.jsonl`` 两本只读原件的并集，不是本件挑的；
* 判分器是线上那一枚 ``app.quality.eval._is_correct``。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTER_DOC = REPO_ROOT / "documents" / "制度与口径登记表.txt"
ANSWERS_RUN6 = REPO_ROOT / "docs" / "testing" / "answers-run6.jsonl"
RECALL_R59B = REPO_ROOT / "docs" / "testing" / "r59b-recall-comparison-2026-09-24.json"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 判据① 的两枚主角，逐字取自语料，本件一个字都不改写。
SPECIAL_WORDING = "退款不冲减销售额，按下单口径保留原签约金额。"
GENERAL_CARVEOUT = "销售部的签约统计另按 cp-03 销售部一侧执行。"
RUN6_CONCLUSION = "在销售部口径下，**发生退款时销售额 = 原销售额 − 退款金额**"

#: 择边段落里"本题结论"那一行的起手字：判据③④ 两族用例都拿它当"本腿开过口"的锚。
SPECIAL_HINT = "本题结论"


# ==================== 离线 harness（假 provider + 真 doc 腿） ====================


class Transport:
    """站在 provider 边界的记账器：它是"发请求之前"的最后一道闸，也是"模型发了几发"的尺。"""

    def __init__(self, monkeypatch, replies=()):
        self.captured = []
        self._replies = list(replies)
        monkeypatch.setattr(ChatOpenAI, "_generate", self._generate)

    def _generate(self, input=None, stop=None, run_manager=None, **kwargs):  # noqa: A002
        messages = input if input is not None else kwargs.get("messages")
        self.captured.append(list(messages))
        index = min(len(self.captured) - 1, max(len(self._replies) - 1, 0))
        reply = self._replies[index] if self._replies else AIMessage(content="已作答。")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    @property
    def calls(self) -> int:
        return len(self.captured)


def search_reply(query: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": "search_docs", "args": {"query": query}, "id": "call-r216", "type": "tool_call"}],
    )


def _doc_config(thread_id: str) -> dict:
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r216", "role": "clerk", "department": "销售部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf.update({
        "thread_id": thread_id, "request_id": "req-" + thread_id,
        "trace_id": "trace-" + thread_id, "task_id": "task-" + thread_id, "worker": "doc",
    })
    return {"configurable": conf}


class _FakePipeline:
    """假检索管线：只把**真实名次读数**那块料原样交回，装箱仍走 ``search_docs`` 里那一枚真尺。"""

    def __init__(self, hits):
        self.hits = hits

    def search_for_principal(self, query, principal, top_k, context_pack=False):
        return list(self.hits), [query]


def register_chunks() -> dict:
    """按 ``app/rag/retriever.py`` 那把尺切真语料，交回 ``{块号: 整块正文}``。

    本件不发明第二把尺：切块尺寸从现网代码里读（与 ``test_r206_caliber_quotes`` 同源）。
    """
    import re

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    source = (REPO_ROOT / "app" / "rag" / "retriever.py").read_text(encoding="utf-8")
    sizes = [int(n) for n in re.findall(r"chunk_size=(\d+)", source)]
    assert sizes, "切块尺寸读不到了：这一件的位置也变了，去看 retriever 的 splitter"
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=sizes[0], chunk_overlap=50, separators=["\n\n", "\n", "。", "；", "　", " ", ""])
    return {index: text for index, text in enumerate(splitter.split_text(REGISTER_DOC.read_text(encoding="utf-8")))}


# ==================== 判据①：先取证，再动手 ====================


def recorded_ranks_for_metric08() -> list:
    """``metric-08`` 这一发**真实**被召回过的那几块：两本只读原件的并集，按名次排。

    - ``r59b``：两侧引擎（Chroma 索引腿 / PG 精确腿）同一批 5 块，逐字相同；
    - ``answers-run6``：真机那一发装箱后记进证据袋的 4 块（R112：装进 prompt 的才算引证）。
    并集不是本件挑的，两本原件里随便哪一本漂了这枚用例就红。
    """
    r59b = json.loads(RECALL_R59B.read_text(encoding="utf-8"))
    row = next(item for item in r59b["questions"] if item.get("id") == "metric-08")
    vector_leg = [int(str(pid).rsplit("_", 1)[1]) for pid in row["chroma_ids"]]
    assert row["chroma_ids"] == row["pg_ids"], "两腿名次已漂 ⇒ 这份取证的前提不再成立，本件该红"
    answers = {}
    for line in ANSWERS_RUN6.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            item = json.loads(line)
            answers[str(item.get("id"))] = item
    packed = [int(item["chunk_index"]) for item in answers["metric-08"]["evidence"]
              if str(item.get("source") or "").startswith("制度与口径登记表")]
    union = []
    for index in vector_leg + packed:
        if index not in union:
            union.append(index)
    return union


def test_metric08_assembled_prompt_carries_special_and_general_together(monkeypatch, capsys):
    """判据①：把 metric-08 离线真实组装出来的 prompt 摊开，两枚条款必须同时在场。

    🔴 这条用例是**取证**不是效果：它一次都不碰择边规则，只证明"特殊条款进了上下文、且与
    通用条款同时在场"这个立单前提量测得到。前提一旦漂了，后面每一条判据都失去地基，
    这条用例就该红，本单就该退回——所以它必须长在测试里，而不是长在我的报告里。
    """
    from app.agents import tools
    from app.agents.orchestrator import doc_graph

    chunks = register_chunks()
    ranks = recorded_ranks_for_metric08()
    hits = [{"source": "制度与口径登记表.txt", "chunk_index": index, "_score": 0.71,
             "content": chunks[index]} for index in ranks if index in chunks]
    assert any(SPECIAL_WORDING in hit["content"] for hit in hits), "特例那一块不在真实名次里"

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(hits))
    transport = Transport(monkeypatch, replies=[
        search_reply("发生退款时 销售部 销售额 口径"),
        AIMessage(content=RUN6_CONCLUSION),
    ])
    doc_graph.invoke({"messages": [HumanMessage(content="发生退款时，销售部口径下的销售额怎么算？")]},
                     config=_doc_config("thread-r216-forensics"))
    assert transport.calls == 2, transport.calls

    prompt = "\n".join(str(message.content) for message in transport.captured[-1])
    with capsys.disabled():
        print("\n" + "=" * 30 + " R216 判据①：metric-08 离线真实组装的 prompt " + "=" * 30)
        print(prompt)
        print("=" * 88 + "\n")
    assert SPECIAL_WORDING in prompt, "特殊条款的原文没进 prompt ⇒ 判据① 不成立，本单该退回"
    assert GENERAL_CARVEOUT in prompt, "一般条款（带让边子句）没进 prompt ⇒ 无从谈'选错边'"
    assert "| cp-03 | 销售额退款处理 | 客服部 |" in prompt, "并列对侧不在场 ⇒ 这不是'互斥口径同场'的形状"


# ==================== 判据②：修的是可泛化的择边规则，不是这一道题 ====================

#: 三形状各钉一格。🔴 只有第 1 格来自真语料，另外两格是本件**现造**的合成登记表：
#: 部门换了、条款方向换了（"不冲减"→"不以…确认"→"不摊入"）、金额也换了，而"哪一条才是
#: 特例"与"特例说什么"两件事都跟原题不同。同一套规则必须三格都选对边。
#:
#: 第 3 格刻意把被点名的那一侧放到登记表的**最后一行**，且让一般条款的正文里也出现同一个
#: 部门名（"华东大区"）——它考的是"点名"这件事只能靠**范围格**判定：一般条款在自己的正文里
#: 提一个部门，不等于它就管那个部门。
CONFLICT_SHAPES = [
    pytest.param(
        "制度与口径登记表（真语料）",
        ["| cp-03 | 销售额退款处理 | 销售部 | 退款不冲减销售额，按下单口径保留原签约金额。 | 本表 cp-03 | V1.0 |",
         "| cp-03 | 销售额退款处理 | 客服部 | 退款冲减当期销售额，在退款发生当期记红字。 | 本表 cp-03 | V1.0 |",
         "| t-02 | 退款是否计入费用 | 退款不计入费用。费用按实际支付且未被退回的金额统计；发生退款时在退款当期冲减对应费用记录，并在报表中说明是否含退款及依据（默认口径为不含退款）。销售部的签约统计另按 cp-03 销售部一侧执行。 | 本表 cp-03、cp-04 |"],
        "发生退款时，销售部口径下的销售额怎么算？",
        "退款不冲减销售额，按下单口径保留原签约金额。",
        id="shape-1-register-corpus-sales",
    ),
    pytest.param(
        "质保金登记表（合成·换部门·换方向·换金额）",
        ["| sp-11 | 质保金确认时点 | 华东大区 | 质保金不以发货确认，按终验通过当日确认，金额 480 万元。 | 本表 sp-11 | V2.0 |",
         "| sp-11 | 质保金确认时点 | 华南大区 | 质保金以发货确认，发货当期即计入 129 万元。 | 本表 sp-11 | V2.0 |",
         "| tp-04 | 质保金是否计入应收 | 质保金一律计入当期应收，发货即确认，不等多退少补。华东大区的质保金另按 sp-11 华东大区一侧执行。 | 本表 sp-11、tp-01 |"],
        "华东大区的质保金按什么时点确认？",
        "质保金不以发货确认，按终验通过当日确认，金额 480 万元。",
        id="shape-2-synthetic-east-region",
    ),
    pytest.param(
        "工时口径登记表（合成·被点名侧在末行·一般条款正文里也带部门名）",
        ["| wl-07 | 工时是否摊入停线 | 总装车间 | 工时摊入停线，停线当期按 3,700 工时计。 | 本表 wl-07 | V4.2 |",
         "| wl-07 | 工时是否摊入停线 | 涂装车间 | 工时不摊入停线，停线工时单列，不计入 3,700 工时。 | 本表 wl-07 | V4.2 |",
         "| hk-03 | 停线工时怎么进报表 | 停线工时一律并入总工时报表，按合并后的口径考核，涂装车间不得除外。涂装车间的工时另按 wl-07 涂装车间一侧执行。 | 本表 wl-07、hk-01 |"],
        "涂装车间的工时要不要摊进停线？",
        "工时不摊入停线，停线工时单列，不计入 3,700 工时。",
        id="shape-3-synthetic-named-side-last",
    ),
]

WRONG_CONCLUSION = "按合并后的口径考核，停线工时一律并入总工时报表。"


def state_of(question: str, answer: str, rows: list) -> dict:
    """拼一发最小现场：``rows`` 那些登记行确实进了 prompt（装箱后的证据袋），模型交回``answer``。"""
    return {
        "messages": [HumanMessage(content=question)],
        "worker_results": {"doc": answer},
        "agent_results": {"doc": {"worker": "doc", "status": "success", "answer": answer,
                                  "evidence": [{
                                      "source_type": "document",
                                      "source_name": "制度与口径登记表.txt",
                                      "source_id": "制度与口径登记表.txt#chunk=1",
                                      "excerpt": "\n".join(rows),
                                      "provenance_status": "verified",
                                      "permission_checked": True,
                                  }]}},
    }


def run_synthesize(state: dict) -> str:
    from app.agents.nodes import synthesize

    return synthesize(state)["final_answer"]


def side_verdict(body: str) -> dict:
    """只取「口径择边」那一段的账，再把模型自己写过的字隔出去。

    必须这么切：正文里已经有 R206b 补写的「口径原文」段与模型自己写的引证块，按行全收会把
    别人的字算进本腿的收益（判据① 那条纪律就是防这个）。
    """
    from app.agents.nodes import CLAUSE_SIDE_LABEL

    marker = body.find(CLAUSE_SIDE_LABEL)
    if marker < 0:
        return {}
    rows = {}
    role = None
    for line in body[marker:].splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("（依据条号"):
            continue
        if line.startswith("- 本题结论"):
            role = "conclusion"
        elif line.startswith("- 不适用本题的一般条款"):
            role = "general"
        elif line.startswith("- 并列对侧"):
            role = "peer"
        if role:
            rows.setdefault(role, []).append(line.split("：", 1)[-1] if role != "general" else line)
    return rows


@pytest.mark.parametrize("title, rows, question, special_wording", CONFLICT_SHAPES)
def test_the_named_side_wins_over_the_general_clause(title, rows, question, special_wording):
    """三格各选各的边：结论段必须是**题面点名那一侧**的登记口径，一般条款只许被记名为不适用。"""
    body = run_synthesize(state_of(question, WRONG_CONCLUSION, rows))
    verdict = side_verdict(body)

    assert verdict, f"{title}：本腿一个字都没说，选边规则没落地"
    assert verdict.get("conclusion") == [special_wording], (
        f"{title}：本题结论不是被点名那一侧的原话 ⇒ {verdict.get('conclusion')}")
    assert special_wording in body, "特例那句没进正文"
    assert not any(special_wording in line for line in verdict.get("peer", [])), (
        f"{title}：对侧串进了本题结论")


@pytest.mark.parametrize("title, rows, question, special_wording", CONFLICT_SHAPES)
def test_the_general_clause_is_named_as_inapplicable_not_as_the_answer(title, rows, question, special_wording):
    """一般条款必须被**指名道姓**判为不适用，而不是被静悄悄丢掉。

    制度 §〇.2 要的就是"同时说明与之冲突的另一侧口径及其依据"：只报一侧在这里也算答错，
    所以本腿既要抬对边、也要留对侧。
    """
    verdict = side_verdict(run_synthesize(state_of(question, WRONG_CONCLUSION, rows)))
    assert verdict.get("general"), "一般条款没有被指名 ⇒ 读者无从知道冲突存在"
    assert len(verdict["general"]) == 1, verdict["general"]
    assert verdict.get("peer"), "同一条号下的另一侧没并列给出 ⇒ 变成只报一侧"
    assert "依据条号" in run_synthesize(state_of(question, WRONG_CONCLUSION, rows))


@pytest.mark.parametrize("question, expected", [
    ("发生退款时，销售部口径下的销售额怎么算？", "退款不冲减销售额，按下单口径保留原签约金额。"),
    ("发生退款时，客服部口径下的销售额怎么算？", "退款冲减当期销售额，在退款发生当期记红字。"),
])
def test_the_rule_follows_the_named_side_instead_of_a_fixed_answer(question, expected):
    """同一份登记料、换一枚被点名的部门，结论必须跟着换边。

    这一条挡的是最省事的假修法（把某一句钉成"永远的答案"）：那样两问会交回同一份文字。
    """
    rows = [row for row in (
        "| cp-03 | 销售额退款处理 | 销售部 | 退款不冲减销售额，按下单口径保留原签约金额。 | 本表 cp-03 | V1.0 |",
        "| cp-03 | 销售额退款处理 | 客服部 | 退款冲减当期销售额，在退款发生当期记红字。 | 本表 cp-03 | V1.0 |",
        "| t-02 | 退款是否计入费用 | 退款不计入费用。费用按实际支付且未被退回的金额统计；发生退款时在退款当期冲减对应费用记录，并在报表中说明是否含退款及依据（默认口径为不含退款）。销售部的签约统计另按 cp-03 销售部一侧执行。 | 本表 cp-03、cp-04 |",
    )]
    verdict = side_verdict(run_synthesize(state_of(question, WRONG_CONCLUSION, rows)))
    assert verdict.get("conclusion") == [expected], (question, verdict.get("conclusion"))


def _r216_executable_literals():
    """把本单新增那一段里**会执行的**字符串字面量抠出来，连注释与 docstring 一起排除。

    注释里写"销售部"是给下一班读病因，代码里写"销售部"就是为这一道题写死。只有后者要判红，
    所以尺子必须走 AST：``ast.walk`` 会把 docstring 也 walk 出来，得按顶层节点自己挑。

    切法：从本单抬头那行虚线注释起，到下一枚函数定义（``_cited_caliber_fragments``）止。
    """
    import ast

    source = (REPO_ROOT / "app" / "agents" / "nodes.py").read_text(encoding="utf-8")
    region = source[source.index("# ==================== R216"):source.index("def _cited_caliber_fragments")]
    literals = []
    for node in ast.parse(region).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            statements = list(node.body)
            if statements and isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant):
                statements = statements[1:]  # docstring：散文，不是判据
            roots = statements
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            roots = [node]
        else:
            roots = []
        for root in roots:
            for part in ast.walk(root):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    literals.append(part.value)
    return region, literals


@pytest.mark.skipif(not REGISTER_DOC.exists(), reason="语料不在本树")
def test_the_rule_reads_its_vocabulary_from_the_evidence_not_from_itself():
    """🔴 没收工条款的机器版：产品代码里不许出现任何题目关键词、部门名或语料原文片段。

    判据② 明写这条。名单里前 8 枚来自真语料与评测题面，后面的来自本件现造的合成登记表：
    换部门、换方向、换金额那几格的名字要是冒出来，就说明规则背下了用例而不是读懂了表。
    """
    from app.agents import nodes

    banned = ["销售部", "客服部", "退款", "销售额", "cp-03", "t-02", "metric-08", "must_contain",
              "质保金", "涂装车间", "华东大区", "总装车间", "sp-11", "wl-07", "停线", "佣金"]
    region, literals = _r216_executable_literals()
    assert region.strip(), "读不到本单新增的那段代码 ⇒ 尺子坏了，先怀疑这条用例自己"
    assert literals, "本单新增的那段代码里一枚执行字面量都没有？那择边规则说不出人话"
    leaked = sorted({word for word in banned for text in literals if word in text})
    assert not leaked, f"择边规则的执行字面量里有题目/语料词 ⇒ 换一份制度文件就失效：{leaked}"
    assert callable(nodes.select_caliber_side), "本单的规则读不到了"


# ==================== 派工词那条纪律：本单的收益不许记进"逐字保真" ====================


@pytest.mark.parametrize("label, rows, question, special_wording", CONFLICT_SHAPES)
def test_the_verbatim_leg_alone_does_not_pick_the_right_side(label, rows, question, special_wording, monkeypatch):
    """把本单的腿摘掉、只留 R206b 那一腿，同一发必须仍然**站在那一侧都不许动的一般条款**上。

    派工词写死了"不许把本单的收益算进逐字保真，也不许改口说 A④ 那三格是本单救的"。光在报告里
    这么说不算证据，所以这里把它做成一枚用例：摘掉择边腿之后，逐字保真腿按它自己的尺（与题面
    的字面重合度）挑出来的那一行恰恰是**一般条款**——它不但救不了这一格，还会把错的那一侧再
    逐字强调一遍。两枚守卫的地盘由此机器可分：谁都没替谁干活。
    """
    from app.agents import nodes

    monkeypatch.setattr(nodes, "_apply_caliber_side",
                        lambda state_, question_, final_, worker_results_, model_answer="": (final_, None))
    body = nodes.synthesize(state_of(question, WRONG_CONCLUSION, rows))["final_answer"]

    assert body.startswith(WRONG_CONCLUSION)
    assert SPECIAL_HINT not in body, "摘掉了择边腿却还冒出本题结论 ⇒ 这一枚反证钉自己坏了"
    assert special_wording not in body, (
        f"{label}：只留逐字保真腿也能把特例那句带进正文 ⇒ 这一格本就不该另立一单")
    quoting = [line[2:] for line in body.splitlines() if line.startswith("> |")]
    assert quoting, f"{label}：逐字保真腿一个字都没补，那这枚反证没量到它"
    assert all(special_wording not in line for line in quoting), (
        f"{label}：逐字保真腿自己就能选对边 ⇒ 这一格不需要另立一单，本单判据该退")
    assert any("另按" in line for line in quoting), (
        f"{label}：补进来的不是那枚让边的一般条款 ⇒ 反证对象错了，两枚守卫的边界没量出来")


# ==================== 判据③：不涉及冲突的形状，交付答案逐字节不变、模型发数不变 ====================

#: 四枚"与本单无关"的形状，覆盖 ``doc-*``（制度问答）与 ``report-*``（报告生成）两族。
#: 它们今天真跑在客户面前，本单一枚都不许把它们改出新形状。
CONFLICT_FREE_SHAPES = [
    pytest.param("doc-01 单侧登记行", "住宿费标准是多少？", "500 元/晚，凭发票报销。",
                 ["| t-06 | 紧急出差未提前申请 | 紧急出差来不及提前申请的，必须在返回后 24 小时内补提出差申请并说明原因，经部门负责人确认后按正常流程受理；超过 24 小时补提的，按无事前审批处理。 | 《差旅费报销细则（2026 版）》 |"],
                 id="doc-single-registered-row"),
    pytest.param("doc-04 散文条款（没有条号）", "发票抬头开错了怎么办？", "一律退回重开。",
                 ["员工出差取得的发票，抬头应当与公司登记名称一致；抬头开错的，财务不予受理，退回后重新开具。"],
                 id="doc-prose-no-code"),
    pytest.param("report-02 报告口径不点名", "把上半年销售额写成月报口径。", "上半年销售额按入账月汇总。",
                 ["| cp-04 | 费用归属期间 | 财务部 | 费用以入账月归属，按凭证过账期间确定所属月份。 | 本表 cp-04 | V1.0 |",
                  "| cp-04 | 费用归属期间 | 市场部 | 费用以发生月归属，按活动执行期间确定所属月份。 | 本表 cp-04 | V1.0 |"],
                 id="report-two-sides-nobody-named"),
    pytest.param("report-07 表格残块", "把库存周转那一节重排一下。", "按出库成本口径重排。",
                 ["## 一、口径冲突登记表（同一指标，多部门口径并存）",
                  "| 冲突编号 | 指标 | 部门 | 该部门登记的统计口径 | 口径来源 | 生效制度版本 |",
                  "|---|---|---|---|---|---|"],
                 id="report-heading-and-table-header"),
]


def baseline_synthesize(state: dict, monkeypatch) -> str:
    """前任态：把本单新增的那一腿摘掉，其余一字不动地跑真 ``synthesize``。"""
    from app.agents import nodes

    monkeypatch.setattr(nodes, "_apply_caliber_side",
                        lambda state_, question, final, worker_results, model_answer="": (final, None))
    return nodes.synthesize(state)["final_answer"]


@pytest.mark.parametrize("label, question, answer, rows", CONFLICT_FREE_SHAPES)
def test_a_conflict_free_answer_is_byte_identical_across_the_fix(label, question, answer, rows, monkeypatch):
    """判据③：不涉"特例 vs 一般"冲突的形状，修复前后**交付答案逐字节相同**。"""
    import hashlib

    state = state_of(question, answer, rows)
    before = baseline_synthesize(json.loads(json.dumps(state, default=str)) and state, monkeypatch)
    after = run_synthesize(json.loads(json.dumps(state, default=str)) and state)
    assert before == after, f"{label}：本腿把一型不涉冲突的答案改出了新形状"
    assert hashlib.sha256(before.encode("utf-8")).digest() == hashlib.sha256(after.encode("utf-8")).digest()


@pytest.mark.parametrize("title, rows, question, special_wording", CONFLICT_SHAPES)
def test_the_side_leg_buys_no_extra_model_call(title, rows, question, special_wording, monkeypatch):
    """🔴 钉住"这一单没有偷偷多打一发模型"：择边腿是纯字符串推理，provider 调用数必须恒为 0。

    前一枚用例量的是"不涉冲突的形状不变"，这一枚量的是"变了形状也没多花钱"——两回事，
    分开钉：真机跑分窗（run7）只看得到发数，看不到字节。
    """
    transport = Transport(monkeypatch)
    body = run_synthesize(state_of(question, WRONG_CONCLUSION, rows))
    assert transport.calls == 0, f"{title}：择边腿打了 {transport.calls} 发模型"
    assert SPECIAL_HINT in body



@pytest.mark.parametrize("title, rows, question, special_wording", CONFLICT_SHAPES)
def test_appending_keeps_the_delivered_answer_a_prefix(title, rows, question, special_wording):
    """只许往末尾追加：模型已经交回的那一段必须仍是终答的前缀（R203 流式帧的红线）。"""
    from app.agents.nodes import synthesize

    state = state_of(question, WRONG_CONCLUSION, rows)
    result = synthesize(state)
    assert result["final_answer"].startswith(WRONG_CONCLUSION), f"{title}：改写了模型写的字"
    assert "worker_results" in result, f"{title}：追加了却没回写 worker_results，收端会读到旧字"
    assert list(result["worker_results"]) == list(state["worker_results"]), f"{title}：洗掉了别的腿"
