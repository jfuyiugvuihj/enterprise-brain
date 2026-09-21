"""R112 · doc 腿与 data 腿的上下文装箱（跟进单 §52 判据 2/4/5/6 + §53 判据 1/2/3/4）。

全离线：不连模型、不起服务、不动数据。模型名由 tests/conftest.py 的哨兵挡住；本文件里的
"模型"全是脚本化假 model，检索/数据结果全是测试自造的假 hits，一次 socket 都不该开。

R116（跟进单 §54 / §57 / §62 二）把下面那族 46 枚 ``WINDOW_IDS`` 钉桩从"合成 token 尺寸"
升级成**按真机实测 ``prompt_tokens`` 复算 room**：每枚钉桩现在都答得出三个数——这一发的
room 是多少（估算口径与实测口径各一个）、实得料多少条几枚、拒发多少条几枚——数全部来自
``scripts/perf_probe_run5_ledger.py`` 烘进来的 run5 实测表，尺子全部是被测代码自己的
``estimate_text_tokens`` / ``pack_prefix_by_rank`` / ``_fit_unit_to_room``。

那两枚预留常数（``CONTEXT_SHELL_RESERVE_TOKENS`` / ``CONTEXT_HISTORY_RESERVE_TOKENS``）不是
抄来的，是下面 ``test_*reserve*`` 两枚用例复算出来的。测量口径：拿四条 worker 腿各自的真
system 段（``DOC_PROMPT`` 等）经真 ``create_react_agent`` 组装，量"最终 ``prompt_tokens``
− 本轮工具串 token"；扫 4 条腿 × 题面 10/64/256/400 字 × 规划文字 0/120/360 字 × 1~3 轮
工具调用 取最大值，历史另按"每轮上一问一答"实测单价留两轮。同一个口径也抄了一份在
``app/rag/retrieval_pipeline.py`` 装箱那一节的注释里——system 段变长就当场红。
"""
import ast
import io
import json
import logging
import math
import os
import re
import warnings

import pytest

warnings.filterwarnings("ignore", message=".*create_react_agent.*")

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool as lc_tool
from langgraph.prebuilt import create_react_agent

from app.agents import tools
from app.agents.contracts import CONTEXT_LIMIT_CODE, ModelTier
from app.agents.tools import (
    PACK_MIN_STUB_BODY_TOKENS,
    PACK_STUB_KEPT,
    PACK_STUB_NONE,
    PACK_STUB_REFUSED,
    PACK_TRUNCATION_MARK,
)
from app.common.model_budget import (
    estimate_prompt_tokens,
    estimate_text_tokens,
    model_tier_budget,
)
from scripts import perf_probe_run5_ledger as run5
from app.rag.retrieval_pipeline import (
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_PACK_TIER,
    CONTEXT_SHELL_RESERVE_TOKENS,
    DOC_HIT_CONTENT_CHARS,
    PROMPT_PACK_MARKER,
    context_pack_capacity,
    context_pack_room,
    pack_prefix_by_rank,
    text_pack_tokens,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESERVE = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS
COVERED_HISTORY_TURNS = 2

#: run2 收窗后从采集侧车（仓外 ``%LOCALAPPDATA%\Temp\evalrun\sidecar-run2.jsonl``，105 行
#: = 50 ``ok`` + 9 ``hitl`` + 46 ``error_event``）逐行读出的**全部** 46 枚撞墙题号，按侧车
#: 里的出现顺序原样抄在这里：46 枚的 ``answer_chars`` 全是 21、``evidence_n`` 全是 0。
#: 判据 4 只用这串真号，一枚都不许凭想象补；题面不抄第二份，从
#: tests/fixtures/business_evaluation_100.jsonl 读原文（夹具一字不改）。
WINDOW_IDS = (
    "doc-12", "doc-14", "doc-16", "doc-17",
    "chat-02", "chat-05", "chat-07", "chat-11",
    "metric-02", "metric-06", "metric-08", "metric-11", "metric-16", "metric-17",
    "metric-18", "metric-19",
    "data-01", "data-03", "data-04", "data-05", "data-06", "data-07", "data-08", "data-12",
    "insight-02", "insight-03", "insight-05", "insight-06", "insight-07",
    "chart-04",
    "approval-02", "approval-03", "approval-04", "approval-05", "approval-06",
    "scope-02", "scope-06", "tool-03",
    "report-01", "report-04", "report-05", "report-08", "report-09", "report-10",
    "report-11", "report-12",
)


def test_window_ids_are_the_whole_run2_refusal_set():
    """判据 4 的骨架完整性：46 枚、去重后仍是 46 枚、每一枚都能在夹具里找到题面原文。"""
    assert len(WINDOW_IDS) == 46, len(WINDOW_IDS)
    assert len(set(WINDOW_IDS)) == len(WINDOW_IDS)
    for row_id in WINDOW_IDS:
        assert _fixture_question(row_id).strip(), row_id

#: 总控在 §52 逐字抄回的两枚真机 prompt_tokens：装箱前它们确实撞墙，这枚用例钉住这个事实。
REAL_REFUSED_PROMPT_TOKENS = {"doc-12": 3897, "doc-14": 4610}


def _fixture_question(row_id):
    path = os.path.join(REPO, "tests", "fixtures", "business_evaluation_100.jsonl")
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if str(row.get("id")) == row_id:
                return str(row.get("question") or "")
    raise AssertionError(f"题号 {row_id} 不在评测夹具里（判据 4 不许凭想象造题号）")


def _source_prompt(name):
    """从 orchestrator 源码里取那一枚 system 段：不 import 它，免得把 checkpointer 拖进测试。"""
    with io.open(os.path.join(REPO, "app", "agents", "orchestrator.py"), encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Constant):
                return str(value.value)
            if isinstance(value, ast.Call):
                args = value.args or [keyword.value for keyword in value.keywords]
                return str(args[0].value)
    raise AssertionError(f"app/agents/orchestrator.py 里找不到 {name}")


@pytest.fixture(autouse=True)
def _clean_pack_ledger():
    """装箱账是进程内的：用例之间必须清干净，否则上一条用例的账会吃掉下一条的 room。"""
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()
    yield
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()


class _ScriptedModel(BaseChatModel):
    """脚本化假模型：把每一发组装到的消息记下来，再按脚本回答。绝不出网。"""

    replies: list = []
    seen: list = []

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        index = len(self.seen) - 1
        message = self.replies[index] if index < len(self.replies) else AIMessage(content="结论如上。")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "scripted"


def _assemble_and_measure(system_text, question, tool_chars, prose, rounds=1, history=0):
    """真 ``create_react_agent`` 组装一发 worker 腿，返回 (最终 prompt_tokens, 本轮工具串 token)。"""

    @lc_tool("probe_tool")
    def _probe(query: str) -> str:
        """取回一批资料。"""
        return "测" * tool_chars

    replies = [
        AIMessage(
            content=prose,
            tool_calls=[{"name": "probe_tool", "args": {"query": question[:24]}, "id": f"c{index}"}],
        )
        for index in range(rounds)
    ]
    model = _ScriptedModel(replies=replies, seen=[])
    graph = create_react_agent(model, [_probe], prompt=system_text)
    seed = []
    for turn in range(history):
        seed.append(HumanMessage(content=f"上一轮的问题（{turn}）：住宿费限额到底是多少？"))
        seed.append(AIMessage(content=("上一轮的结论：限额以制度为准，来源见文件名。" * 6)[:400]))
    seed.append(HumanMessage(content=question))
    graph.invoke({"messages": seed}, config={"recursion_limit": 60})

    messages = model.seen[-1]
    tool_tokens = sum(
        estimate_text_tokens(str(message.content))
        for message in messages
        if isinstance(message, ToolMessage) and str(getattr(message, "tool_call_id", "")).startswith("c")
    )
    return estimate_prompt_tokens(messages), tool_tokens


SHELL_PROBE_CASES = (
    # (system 段, 题面, 规划文字, 工具调用轮数)
    ("DOC_PROMPT", "审批通过后多久打款？", "", 1),
    ("DOC_PROMPT", "那财务是在部门负责人之前还是之后？", "我先查制度原文。", 1),
    ("DOC_PROMPT", "住宿费限额是多少？" * 10, "我先查制度原文，重点看时限与例外情形。", 2),
    ("DOC_PROMPT", "请把公司差旅报销制度里关于住宿费、餐费和交通费的限额、审批链条、打款时限、"
                   "超标处理和发票要求全部列出来并逐条对比，同时给出财务部与销售部口径差异的"
                   "原文依据，并注明每一条出自哪一份文件的哪一个章节。" * 2,
     "我先查制度原文，重点看时限与例外情形，再补一次关键词覆盖发票抬头与超标处理。" * 3, 3),
    ("DATA_PROMPT", "哪个部门花费最高？", "先看排名再看环比。", 2),
    ("DATA_PROMPT", "本季度和上季度费用总额相比变化多少？" * 8, "我按两个季度分别汇总后对比。", 3),
    ("CHART_PROMPT", "把各部门费用画成柱状图。", "先取真实数据再画图。", 2),
    ("EXPORT_PROMPT", "导出这份报告。", "", 1),
)


def _measured_shell_ceiling():
    """把上面那张形态表全跑一遍，取"最终 prompt − 本轮工具串"的最大值＝壳的实测上界。"""
    ceiling = 0
    for prompt_name, question, prose, rounds in SHELL_PROBE_CASES:
        total, tool_tokens = _assemble_and_measure(
            _source_prompt(prompt_name), question, DOC_HIT_CONTENT_CHARS, prose, rounds=rounds
        )
        ceiling = max(ceiling, total - tool_tokens)
    return ceiling


def _measured_history_unit_price():
    """同会话里"上一问 + 上一答"每轮实测多花多少枚 token（历史单价）。"""
    base_total, base_tool = _assemble_and_measure(
        _source_prompt("DOC_PROMPT"), "住宿费限额是多少？", DOC_HIT_CONTENT_CHARS, "我先查制度原文。", rounds=1
    )
    deep_total, deep_tool = _assemble_and_measure(
        _source_prompt("DOC_PROMPT"), "住宿费限额是多少？", DOC_HIT_CONTENT_CHARS, "我先查制度原文。",
        rounds=1, history=COVERED_HISTORY_TURNS,
    )
    return ((deep_total - deep_tool) - (base_total - base_tool)) / float(COVERED_HISTORY_TURNS)


# ==================== §53 判据 1：容量取真源、预留取实测 ====================


def test_pack_capacity_tracks_the_budget_property(monkeypatch):
    """装箱容量必须是 ``ModelBudget.input_budget_tokens`` 本身：改配置它就跟着改。"""
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", raising=False)
    budget = model_tier_budget(ModelTier.ANALYSIS)
    assert context_pack_capacity() == budget.input_budget_tokens
    assert context_pack_room() == budget.input_budget_tokens - RESERVE

    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "8192")
    monkeypatch.setenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", "2048")
    moved = model_tier_budget(ModelTier.ANALYSIS)
    assert context_pack_capacity() == moved.input_budget_tokens == 8192 - 2048
    assert context_pack_room() == 8192 - 2048 - RESERVE


def test_packing_sites_carry_no_copied_window_numbers():
    """装箱这两处不许再抄一枚窗口/输出常数：2560、4096、1536 不许出现在代码行里。"""
    offenders = []
    for relative in (os.path.join("app", "agents", "tools.py"),
                     os.path.join("app", "rag", "retrieval_pipeline.py")):
        with io.open(os.path.join(REPO, relative), encoding="utf-8") as handle:
            for number, line in enumerate(handle.read().splitlines(), start=1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\b(2560|4096|1536)\b", line):
                    offenders.append(f"{relative}:{number}:{line.strip()}")
    assert offenders == [], "装箱容量只许问真源：" + " | ".join(offenders)


def test_shell_reserve_covers_the_measured_assembly_shell():
    """真组装量出来的壳，预留必须盖得住；盖不住就是常数该重测了。"""
    ceiling = _measured_shell_ceiling()
    assert ceiling > 0, "组装没量到东西，这条用例就是空响"
    assert CONTEXT_SHELL_RESERVE_TOKENS >= ceiling, (
        f"实测壳 {ceiling} 枚超过预留 {CONTEXT_SHELL_RESERVE_TOKENS} 枚：预留是量出来的，"
        f"system 段或壳变长了就重测再重填（口径见本文件 docstring 与 SHELL_PROBE_CASES）"
    )


def test_history_reserve_covers_the_pinned_number_of_turns():
    """历史那份额外预留：按实测单价 × 覆盖轮数核，留少了红。"""
    unit = _measured_history_unit_price()
    assert unit > 0, "历史单价量成 0 说明夹具没真的往消息里加东西"
    needed = math.ceil(unit) * COVERED_HISTORY_TURNS
    assert CONTEXT_HISTORY_RESERVE_TOKENS >= needed, (
        f"每轮历史实测 {unit:.1f} 枚，{COVERED_HISTORY_TURNS} 轮要 {needed} 枚，"
        f"现在只留 {CONTEXT_HISTORY_RESERVE_TOKENS} 枚"
    )


def test_reserves_are_measured_numbers_not_round_guesses():
    """两枚预留都得是"量出来的怪数"：整十整百在这里就是拍脑袋的证据。"""
    assert CONTEXT_SHELL_RESERVE_TOKENS % 10 != 0, CONTEXT_SHELL_RESERVE_TOKENS
    assert CONTEXT_HISTORY_RESERVE_TOKENS % 10 != 0, CONTEXT_HISTORY_RESERVE_TOKENS
    assert 0 < RESERVE < context_pack_capacity(), "预留吃光了容量，或压根没留"


# ==================== §52 判据 1 + §53 判据 2：装箱与那行账 ====================


class _FakePipeline:
    """交回 N 条 ``DOC_HIT_CONTENT_CHARS`` 长的命中——真机 doc 腿就是默认 5 条 × 500 字。"""

    def __init__(self, hits, pack_at_source=True):
        self.hits = hits
        self.pack_at_source = pack_at_source
        self.context_pack_flags = []

    def search_for_principal(self, query, principal, top_k, context_pack=False):
        self.context_pack_flags.append(context_pack)
        docs = list(self.hits)
        if context_pack and self.pack_at_source:
            from app.rag.retrieval_pipeline import pack_hit_list

            docs, _dropped, _tokens = pack_hit_list(docs, context_pack_room())
        return docs, ["住宿费 打款 时限"]


def _hits(count, *, filler="住宿费限额按职级分档执行并需事前审批。", source="差旅费报销制度"):
    filler = filler * 90
    return [
        {
            "source": f"{source}{index}.pdf",
            "chunk_index": index,
            "_score": round(0.91 - 0.11 * index, 2),
            "content": (filler + str(index))[:DOC_HIT_CONTENT_CHARS],
        }
        for index in range(1, count + 1)
    ]


def _doc_config(step_id="trace-r112:worker:doc"):
    conf = {"username": "r112", "role": "admin", "department": "财务部"}
    if step_id:
        conf["step_id"] = step_id
    return {"configurable": conf}


def _pack_spy(monkeypatch):
    """把装箱前后的单元都录下来：断言用真实数据，不在测试里重抄一遍工具拼法。"""
    record = {}
    original = tools._pack_into_prompt_room

    def spy(config, *, leg, units, keep_first_truncated=False):
        fitted = original(config, leg=leg, units=units, keep_first_truncated=keep_first_truncated)
        record[leg] = {"before": list(units), "after": list(fitted)}
        return fitted

    monkeypatch.setattr(tools, "_pack_into_prompt_room", spy)
    return record


@pytest.fixture
def info_log(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _pack_fields(line):
    """把 ``[PromptPack]`` 那一行拆成字段字典：断言读字段，不拿正则去凑第二段。"""
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


def _pack_lines(log, leg):
    return [
        record.message
        for record in log.records
        if PROMPT_PACK_MARKER in record.message and f"leg={leg}" in record.message
    ]


def test_doc_leg_asks_the_retrieval_leg_to_pack_too(monkeypatch):
    pipeline = _FakePipeline(_hits(5))
    monkeypatch.setattr(tools, "_get_pipeline", lambda: pipeline)

    tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config())

    assert pipeline.context_pack_flags == [True], "最终 top-k 那一层也得装箱，不然第一道闸形同虚设"


def test_a_retrieval_leg_without_the_flag_is_still_packed_not_broken(monkeypatch, info_log):
    """旧签名的检索腿（存量替身与客户子类）不认 ``context_pack``：照旧调用，装箱这层不许
    因此把一次正常检索变成 ``retrieval_unavailable``。"""

    class _LegacyPipeline:
        def search_for_principal(self, query, principal, top_k):
            return _hits(5), []

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _LegacyPipeline())

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config("trace-r112:legacy"))

    assert "文档检索不可用" not in out, out
    assert text_pack_tokens(out) <= context_pack_room(), "第二层装箱照样得把返回串压进 room"
    lines = _pack_lines(info_log, "doc")
    assert len(lines) == 1 and int(dict(re.findall(r"(\w+)=([^\s]+)", lines[0]))["candidates"]) == 5


def test_doc_leg_pack_account_is_one_greppable_line(monkeypatch, info_log):
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(5), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config())

    lines = _pack_lines(info_log, "doc")
    assert len(lines) == 1, lines
    fields = dict(re.findall(r"(\w+)=([^\s]+)", lines[0]))
    assert fields["leg"] == "doc" and fields["tier"] == CONTEXT_PACK_TIER
    assert int(fields["candidates"]) == 5
    assert int(fields["fitted"]) + int(fields["dropped"]) == int(fields["candidates"])
    assert int(fields["fitted"]) < int(fields["candidates"]), "5 条 × 500 字本来就该裁掉几条"
    assert fields["dropped_labels"] != "-"
    assert int(fields["packed_tokens"]) == sum(
        text_pack_tokens(part) for part in out.split("\n\n---\n\n")
    ), "账里的 packed_tokens 必须等于真装进返回串的那几段之和"
    assert int(fields["prompt_estimate_tokens"]) == RESERVE + int(fields["ledger_packed_tokens"])
    assert int(fields["prompt_estimate_tokens"]) <= context_pack_capacity()


def test_doc_leg_keeps_top_ranked_and_drops_the_lowest_whole(monkeypatch):
    record = _pack_spy(monkeypatch)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(5), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config())

    before = record["doc"]["before"]
    assert text_pack_tokens("\n\n---\n\n".join(before)) > context_pack_room(), "夹具得先真的是装不下的形状"
    kept = record["doc"]["after"]
    assert kept and kept == before[: len(kept)], "丢的必须是名次最低的那一段后缀，不许打洞"
    assert len(kept) < len(before)
    assert text_pack_tokens(out) <= context_pack_room()
    for index in range(len(kept), len(before)):
        assert f"[{index + 1}] 来源:" not in out, "被丢掉的整条不许还留在返回串里"
    assert "住宿费限额按职级分档执行" in out


def test_second_tool_call_in_one_step_only_gets_the_remaining_room(monkeypatch, info_log):
    record = _pack_spy(monkeypatch)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(2), pack_at_source=False))
    step_id = "trace-r112:worker:doc:two-calls"
    config = _doc_config(step_id)

    first = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)
    second = tools.search_docs.invoke({"query": "打款时限补充"}, config=config)

    lines = [_pack_fields(line) for line in _pack_lines(info_log, "doc")]
    assert len(lines) == 2, lines
    first_billed = int(lines[0]["ledger_packed_tokens"])
    total_billed = int(lines[1]["ledger_packed_tokens"])
    assert int(lines[1]["room_left"]) == context_pack_room() - first_billed, "第二发的 room 必须是第一发剩下的"
    assert total_billed == first_billed + int(lines[1]["packed_tokens"]), "账要累得平"
    assert total_billed == tools._pack_ledger["step:" + step_id], "账本与日志得是同一笔数"
    assert total_billed <= context_pack_room(), f"两发各自装满＝照样撞墙：合计 {total_billed}"
    assert total_billed + RESERVE <= context_pack_capacity(), "累加完仍要落在守卫认的容量内"
    assert len(record["doc"]["before"]) == 2
    assert record["doc"]["after"], "第二发还剩 room 时不该整批发空"
    assert text_pack_tokens(second) <= int(lines[1]["room_left"]) + 4


def test_calls_without_a_step_are_not_billed_together(monkeypatch, info_log):
    """没有 step 身份（直接调工具、MCP 单次调用）就不假装它们是同一步：账记 ``ledger=off``。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(1), pack_at_source=False))
    config = _doc_config(step_id=None)

    first = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)
    second = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)

    assert first == second
    lines = _pack_lines(info_log, "doc")
    assert [re.search(r"ledger=(\w+)", line).group(1) for line in lines] == ["off", "off"]


def test_every_pack_writes_an_account_even_when_nothing_is_dropped(monkeypatch, info_log):
    """装得下也要留账：判据 2 要的是"装箱后 prompt_tokens"，不是只有丢东西才记账。"""
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(1), pack_at_source=False))

    tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config("trace-r112:worker:doc:quiet"))

    lines = _pack_lines(info_log, "doc")
    assert len(lines) == 1, lines
    assert "dropped=0" in lines[0] and "prompt_estimate_tokens=" in lines[0]


# ==================== data 腿：查询结果同样撑爆过 ====================


def _patch_data_leg_boundaries(monkeypatch, frame, stub_dataset_evidence=True):
    """两条数据腿的公共替身：绕开数据集准入、Excel 与行级口径，只留"返回串"这一条路。

    ``stub_dataset_evidence=False`` 留给"证据袋到底记了谁"那两枚用例：那条路必须真走
    ``_record_dataset_evidence``，否则测的就只是替身本身。
    """
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.storage import datasets as dataset_storage

    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: ([("费用明细.xlsx", "p")], None))
    monkeypatch.setattr(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)
    if stub_dataset_evidence:
        monkeypatch.setattr(tools, "_record_dataset_evidence", lambda config, filename, df: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: frame)
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (df, {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])}),
    )
    return excel


def _wide_frame():
    import pandas as pd

    columns = {f"金额指标{index}": [float(row * index) for row in range(60)] for index in range(1, 41)}
    columns["门店"] = [f"某某某某门店{row % 12}号分店" for row in range(60)]
    return pd.DataFrame(columns)


def test_analyze_data_return_string_is_packed_and_accounted(monkeypatch, info_log):
    import app.tools.excel as excel

    frame = _wide_frame()
    excel = _patch_data_leg_boundaries(monkeypatch, frame)
    monkeypatch.setattr(
        excel,
        "profile_dataframe",
        lambda df: {"rows": int(df.shape[0]), "columns": [{"name": c, "dtype": "float64"} for c in df.columns]},
    )

    out = tools._analyze_data("按金额指标1排名", _doc_config("trace-r112:worker:data"))

    assert out.startswith("数据分析结果:")
    assert text_pack_tokens(out) <= context_pack_room() + text_pack_tokens("数据分析结果:")
    lines = _pack_lines(info_log, "data")
    assert len(lines) == 1, lines
    fields = dict(re.findall(r"(\w+)=([^\s]+)", lines[0]))
    assert int(fields["dropped"]) + int(fields["fitted"]) == int(fields["candidates"])
    assert int(fields["dropped"]) > 0, "40 列 × 60 行的样本 JSON 不裁就等着撞墙"


def test_query_data_result_is_truncated_with_a_visible_mark(monkeypatch, info_log):
    import pandas as pd

    frame = pd.DataFrame({"金额": [1.0, 2.0]})
    excel = _patch_data_leg_boundaries(monkeypatch, frame)
    monkeypatch.setattr(tools, "_llm_pandas_code", lambda df, query: "df.sum()")
    monkeypatch.setattr(
        excel,
        "safe_query",
        lambda df, code: {
            "error": None,
            "result": {"明细": [{"科目": f"费用科目{row}", "金额": float(row)} for row in range(4000)]},
        },
    )

    out = tools._query_data("各部门报销金额明细", _doc_config("trace-r112:worker:query"))

    assert out.startswith("📊 费用明细.xlsx 查询结果:")
    assert text_pack_tokens(out) <= context_pack_room()
    assert tools.PACK_TRUNCATION_MARK in out, "裁了就得让模型看得见，不留静默丢"
    lines = _pack_lines(info_log, "query")
    assert len(lines) == 1 and "truncated=1" in lines[0], lines


# ==================== §53 判据 3：裁无可裁才拒，且与"模型坏了"分色 ====================


def test_no_room_left_names_this_question_and_the_window_not_the_model(monkeypatch):
    """容量被配置压到 room=0 时，工具自己得说清是本题检索料超窗，不是模型故障。"""
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "1600")
    assert context_pack_room() == 0
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(3), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config("trace-r112:worker:doc:zero"))

    assert "本机上下文窗口" in out and "不是模型故障" in out, out
    assert "本题的文档检索料超出本机上下文" in out, out
    assert out != "本轮未产出任何结论，请重试或补充数据范围。", "那枚 21 字不许再当遮羞布"


def test_pack_prefix_drops_nothing_when_it_fits():
    room = context_pack_room()
    units = ["甲" * 40, "乙" * 40]
    fitted, dropped, used = pack_prefix_by_rank(units, room)
    assert fitted == units and dropped == []
    assert used == text_pack_tokens(units[0]) + text_pack_tokens(units[1])


# ==================== §52 判据 4：真机撞墙题号的回归（R116 改成按实测复算） ============

#: run5 逐发实测账，按题号分组（一题两条腿就两条都算，各自出一组三个数）。
_MEASURED_BY_ROW = {}
for _measured_row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS):
    _MEASURED_BY_ROW.setdefault(_measured_row["row_id"], []).append(_measured_row)

#: run5 里这些题压根没走到装箱（supervisor 直接终答，``[ASK] steps=0``、侧车 tool_calls=0），
#: 没有实测 prompt_tokens 可复算 ⇒ 照实记账并单独钉一条，不许拿别的题的数顶替。
_MEASURED_NOT_PACKED = {
    row[0]: {"tool_calls": row[1], "ask_steps": row[2], "answer_chars": row[3], "wall_s": row[4]}
    for row in run5.MEASURED_NOT_PACKED_RUN5
}


def _measured_hit_head(monkeypatch) -> str:
    """让被测渲染器自己交出命中行头（含换行）：单位形状与行头枚数都不在测试里抄第二份。"""
    spy = _pack_spy(monkeypatch)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(1), pack_at_source=False))
    tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_doc_config("trace-r116:head"))
    unit = str(spy["doc"]["before"][0])
    head, separator, _body = unit.partition("\n")
    assert separator == "\n" and head.startswith("[1] "), unit
    return head + "\n"


def _measured_replay_units(head: str, prices: list) -> list:
    """按实测逐条枚数造候选：条数与每条枚数都来自 run5 那一行，内容只是占位符。"""
    head_tokens = text_pack_tokens(head)
    assert min(prices) > head_tokens, (
        f"真机票价最低 {min(prices)} 枚连行头 {head_tokens} 枚都装不下，实测表与尺子对不上"
    )
    return [head + "费" * (int(price) - head_tokens) for price in prices]


def _assert_priced_as_the_table(prices: list, units: list) -> None:
    """候选必须逐条等于表里那枚数：尺子是被测自己的 ``text_pack_tokens``，不许测试另造一把。"""
    measured = [text_pack_tokens(unit) for unit in units]
    assert measured == [int(price) for price in prices], (
        f"复算用的候选逐条枚数是 {measured}，与实测表反推的 {list(prices)} 不符——尺子被换过了"
    )


def _replay_pack(info_log, *, record, units, delivered: int, step: str):
    """把"本轮已装"回填进账，再让**被测装箱函数**在同一发候选上重跑，返回它自己记的那本账。"""
    tools._pack_ledger["step:" + step] = delivered
    first = len(info_log.records)
    packed = tools._pack_into_prompt_room(
        _doc_config(step), leg=record["leg"], units=units, keep_first_truncated=True
    )
    lines = [r.message for r in info_log.records[first:] if PROMPT_PACK_MARKER in r.message]
    assert len(lines) == 1, (
        f"{record['row_id']}/{record['leg']}：这一发留下 {len(lines)} 行账，应恰好 1 行"
    )
    return packed, _pack_fields(lines[0])


def _stub_branch(unit: str, room_left: int) -> tuple:
    """整批一条都装不下时被测会落哪一档：裁尾与"够不够读"两枚判断全走被测真原语。

    这里**只**复用被测的裁尾/量正文两件工具，room 本身仍是复算出来的那个数；甲口径下这条
    分支还要与被测、与 run5 真机记录三方对齐（见 ``_assert_measured_room_account``），
    所以对不上时红的是断言，不是被悄悄换掉的尺子。
    """
    stub = tools._fit_unit_to_room(unit, int(room_left))
    if not stub:                                    # 连截断标记都装不下：交一枚空桩不如不交
        return PACK_STUB_NONE, 0
    if tools._stub_body_tokens(stub, unit) < PACK_MIN_STUB_BODY_TOKENS:
        return PACK_STUB_REFUSED, 0                 # R122 门槛：正文不够读就不当证据交出去
    return PACK_STUB_KEPT, text_pack_tokens(stub)


def _predict_pack(prices: list, units: list, room_left: int) -> tuple:
    """整批发数/丢数/枚数 + 桩档位的完整预测：整条装得下就不落桩，装不下才进 _stub_branch。"""
    room_left = max(0, int(room_left))
    fitted, dropped, used = run5.fit_prices(prices, room_left)
    if fitted:
        return fitted, dropped, used, PACK_STUB_NONE, 0
    stub, stub_used = _stub_branch(str(units[0]), room_left)
    if stub == PACK_STUB_KEPT:
        return 1, dropped - 1, stub_used, stub, 1
    return 0, dropped, stub_used, stub, 0


def _assert_measured_room_account(monkeypatch, info_log, row_id) -> list:
    """判据 1：同一题面的 room / 实得料 / 拒发，按真机 ``prompt_tokens`` 复算并逐枚钉死。

    两个口径各跑一次**被测装箱函数**，装箱算法一行都不换，只换 room 的真源：

    * 甲＝今天的估算口径（``context_pack_room()``）。它必须一字不差复现 run5 那一发真机记录
      的 ``room_left`` / ``fitted`` / ``dropped`` / ``packed_tokens`` / ``stub`` / ``truncated``
      ——复现不上就说明复算点与真机不是同一发，或估算 room 已经动过。
    * 乙＝按该发实测 ``prompt_tokens`` 反推的 room（壳＝``prompt_tokens − ledger_packed_tokens``，
      实测 room＝``context_pack_capacity() − 壳``）。它答的是"要是房按真机算，这发能得几条料、
      拒几条"。
    """
    if row_id in _MEASURED_NOT_PACKED:
        fact = _MEASURED_NOT_PACKED[row_id]
        assert row_id not in _MEASURED_BY_ROW, f"{row_id}：表里既有实测行又有「未装箱」记录，台账自相矛盾"
        assert fact["tool_calls"] == 0 and fact["ask_steps"] == 0, (
            f"{row_id}：侧车说它走了工具（tool_calls={fact['tool_calls']}、steps={fact['ask_steps']}），"
            "那就必须有装箱账，这张表得重出"
        )
        return []

    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", raising=False)
    budget = model_tier_budget(ModelTier.ANALYSIS)
    capacity, estimated = context_pack_capacity(), context_pack_room()
    head = _measured_hit_head(monkeypatch)
    answers = []
    for record in _MEASURED_BY_ROW[row_id]:
        tag = f"{row_id}/{record['leg']}"
        assert record["room_total"] == estimated, (
            f"{tag}：真机那发记账的 room_total={record['room_total']} 与今天的真源 room="
            f"{estimated} 不再相等——预留或容量动过，run5 这张表必须重测重填"
        )
        shell = run5.measured_shell(record)
        measured = run5.measured_room(record, capacity)
        extra = measured - estimated
        prices = run5.replay_prices(record)
        assert shell > 0, f"{tag}：实测壳 {shell} 枚不是正数，配对配错了"
        assert prices and len(prices) == record["candidates"], f"{tag}：逐条价表与候选数不齐"
        units = _measured_replay_units(head, prices)
        _assert_priced_as_the_table(prices, units)
        room_b = max(0, record["room_left"] + extra)

        # 甲＝估算口径：必须复现真机那一发的全部六枚数。
        packed_a, fields_a = _replay_pack(
            info_log, record=record, units=units,
            delivered=record["delivered_before_tokens"], step=f"trace-r116:estimate:{tag}",
        )
        assert int(fields_a["room_total"]) == estimated, tag
        assert int(fields_a["room_left"]) == record["room_left"], (
            f"{tag}：估算口径复算的 room_left={fields_a.get('room_left')} 对不上真机记录的 "
            f"{record['room_left']}——复算点与真机不是同一发"
        )
        got_a = (
            len(packed_a), packed_a.dropped_count, packed_a.packed_tokens,
            packed_a.stub, packed_a.truncated_count,
        )
        real_a = (
            record["fitted"], record["dropped"], record["packed_tokens"],
            record["stub"], record["truncated"],
        )
        assert got_a == real_a, (
            f"{tag}：估算口径复现不了真机那一发（被测 {got_a}，真机 {real_a}）"
        )
        assert got_a == _predict_pack(prices, units, record["room_left"]), (
            f"{tag}：估算口径下被测与整数复算各说各话（被测 {got_a}）"
        )
        assert int(fields_a["ledger_packed_tokens"]) == record["delivered_tokens"], (
            f"{tag}：复算后的本轮已装 {fields_a.get('ledger_packed_tokens')} 枚与真机 "
            f"{record['delivered_tokens']} 枚不等，预扣的账对不上"
        )

        # 乙＝实测 prompt_tokens 复算的 room：只改配置真源，装箱算法一行都不换。
        with monkeypatch.context() as metered:
            metered.setenv("MODEL_CONTEXT_TOKENS", str(budget.context_limit_tokens + extra))
            assert context_pack_capacity() == capacity + extra, tag
            assert context_pack_room() == measured, tag
            packed_b, fields_b = _replay_pack(
                info_log, record=record, units=units,
                delivered=record["delivered_before_tokens"], step=f"trace-r116:measured:{tag}",
            )
        assert int(fields_b["room_total"]) == measured, tag
        assert int(fields_b["room_left"]) == room_b, (
            f"{tag}：按实测 room 复算的那一发，剩余房应是 {room_b} 枚，被测记的是 "
            f"{fields_b.get('room_left')} 枚（room_total={fields_b.get('room_total')}，"
            f"预扣 {record['delivered_before_tokens']} 枚）"
        )
        want_b = _predict_pack(prices, units, room_b)
        got_b = (
            len(packed_b), packed_b.dropped_count, packed_b.packed_tokens,
            packed_b.stub, packed_b.truncated_count,
        )
        assert got_b == want_b, f"{tag}：按实测 room 复算的实得/拒发与复算不符（被测 {got_b}，复算 {want_b}）"
        assert got_b[0] >= got_a[0] and got_b[2] >= got_a[2], (
            f"{tag}：房放宽之后装出去的料反而少了（{got_a} -> {got_b}），装箱单调性破了"
        )
        if record["stub"] == PACK_STUB_REFUSED:
            assert want_b[4] == 0 and want_b[3] == PACK_STUB_NONE, (
                f"{tag}：真机这发是 stub=refused，按实测 room 复算只许交出**整条**实料，"
                f"不许换成裁尾桩（复算 {want_b}）"
            )
        answers.append({
            "row_id": row_id, "leg": record["leg"], "estimated_room": estimated,
            "measured_room": measured, "measured_shell": shell, "over_reserve": extra,
            "candidate_prices": prices, "estimated": got_a, "measured": got_b,
            "real": record,
        })
    return answers


@pytest.mark.parametrize("row_id", WINDOW_IDS)
def test_packed_real_window_questions_no_longer_refused(monkeypatch, info_log, row_id):
    """同一题面：装箱前会被 ``n_ctx`` 判拒，装箱后不再判拒，且进 prompt 的条数只减不增。

    R116 追加：同一枚用例还必须答出这一发的 room（估算/实测两个口径）、实得料、拒发。
    """
    record = _pack_spy(monkeypatch)
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", raising=False)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(5), pack_at_source=False))
    question = _fixture_question(row_id)
    assert question.strip(), row_id

    out = tools.search_docs.invoke({"query": question}, config=_doc_config(f"trace-r112:worker:doc:{row_id}"))

    budget = model_tier_budget(ModelTier.ANALYSIS)
    before = record["doc"]["before"]
    unpacked = RESERVE + text_pack_tokens("\n\n---\n\n".join(before))
    packed = RESERVE + text_pack_tokens(out)
    assert budget.context_window_code(unpacked) == CONTEXT_LIMIT_CODE, (
        f"{row_id}：装箱前的形状（prompt≈{unpacked}）本来就该撞墙，撞不上说明夹具是空的"
    )
    assert budget.context_window_code(packed) is None, f"{row_id}：装箱后仍被判拒，prompt≈{packed}"
    assert len(record["doc"]["after"]) <= len(before), "进 prompt 的条数只减不增"
    assert record["doc"]["after"], f"{row_id}：装箱后一条检索料都不剩，等于换个姿势不答题"

    # ---- R116 判据 1：46 枚钉桩按真机实测 prompt_tokens 复算 room ----
    _assert_measured_room_account(monkeypatch, info_log, row_id)


def test_measured_run5_table_covers_the_whole_window_id_set():
    """46 枚钉桩与实测表一对一：表里没盖到的题号必须**点名**说明为什么盖不到，不许静默少一枚。"""
    covered = set(_MEASURED_BY_ROW)
    missing = sorted(set(WINDOW_IDS) - covered - set(_MEASURED_NOT_PACKED))
    assert not missing, f"实测表盖不到这些钉桩题号，复算无从下手：{missing}"
    assert sorted(_MEASURED_NOT_PACKED) == sorted(run5.MEASURED_NOT_PACKED_IDS), (
        "run5 未装箱的题号清单与探针模块不一致"
    )
    window_rows = [row for row_id in WINDOW_IDS for row in _MEASURED_BY_ROW.get(row_id, [])]
    assert len(window_rows) == 47, (
        f"46 枚钉桩应摊到 47 发实测装箱账（doc/data 两条腿），现表里是 {len(window_rows)} 发"
    )


def test_measured_run5_shell_is_far_below_the_pinned_reserve():
    """R116 的正面结论也要钉住：真机壳远小于 954 枚预留，所以 room 长期被估窄。"""
    shells = [
        run5.measured_shell(row)
        for row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)
    ]
    assert len(shells) == len(run5.MEASURED_PACKS_RUN5)
    median = sorted(shells)[len(shells) // 2]
    assert median == run5.RUN5_SHELL_MEDIAN, (
        f"全量实测壳中位数 {median} 与表里记的 {run5.RUN5_SHELL_MEDIAN} 不符"
    )
    assert median < RESERVE, f"实测壳中位数 {median} 已不低于预留 {RESERVE}，本单的结论要重写"
    window = [
        run5.measured_shell(row)
        for row_id in WINDOW_IDS
        for row in _MEASURED_BY_ROW.get(row_id, [])
    ]
    assert sorted(window)[len(window) // 2] == run5.RUN5_SHELL_MEDIAN_PACKS, (
        f"46 枚钉桩子集的实测壳中位数与表里记的 {run5.RUN5_SHELL_MEDIAN_PACKS} 不符"
    )


@pytest.mark.parametrize(("row_id", "prompt_tokens"), sorted(REAL_REFUSED_PROMPT_TOKENS.items()))
def test_real_refused_prompt_sizes_are_still_refused_by_the_guard(monkeypatch, row_id, prompt_tokens):
    """把总控抄回的两枚真机 prompt_tokens 钉在守卫上：它们是超窗，不是模型坏了。"""
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", raising=False)
    budget = model_tier_budget(ModelTier.ANALYSIS)

    assert budget.context_window_code(prompt_tokens) == CONTEXT_LIMIT_CODE
    assert budget.context_window_code(context_pack_capacity()) is None, "装箱后的上限必须落在守卫认的范围内"


# ==================== R112 复验第 2 条：装箱之后才结清证据袋与 trace ====================


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """一枚离线的 trace store：装箱后的 summary 要能从真行里读出来，不是断言源码。"""
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "events.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "records.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    return store


def _bag_config(step_id="trace-r112:worker:doc", worker="doc"):
    """带证据袋与真身份的 config：装箱后的账要同时落进 bag 与 trace，缺一样就是暗账。"""
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r112", "role": "admin", "department": "财务部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf.update(
        {
            "thread_id": "thread-r112",
            "request_id": "req-r112",
            "trace_id": "trace-r112",
            "task_id": "task-r112",
            "worker": worker,
        }
    )
    if step_id:
        conf["step_id"] = step_id
    return {"configurable": conf}, conf["evidence_bag"]


def _single_tool_row(trace_store):
    rows = trace_store.persistence.list("tool_calls")
    assert len(rows) == 1, rows
    return rows[0]


def test_doc_evidence_bag_holds_only_the_hits_that_actually_went_out(monkeypatch, trace_store):
    """装 3 丢 2：证据袋与这一发 span 都只能说那 3 条，被丢的两条不许还挂着出处。"""
    from app.agents.evidence import evidence_from_bag

    config, bag = _bag_config()
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(5), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)

    units = out.split("\n\n---\n\n")
    assert (len(units), 5 - len(units)) == (3, 2), units
    recorded = [document["source_name"] for document in bag["documents"]]
    assert recorded == ["差旅费报销制度1.pdf", "差旅费报销制度2.pdf", "差旅费报销制度3.pdf"]
    for index, name in enumerate(recorded, start=1):
        assert f"[{index}] 来源:{name}" in out, name
    for name in ("差旅费报销制度4.pdf", "差旅费报销制度5.pdf"):
        assert name not in out, "被装箱丢掉的那两条不许还有出处"
    assert len(evidence_from_bag(bag)) == len(recorded), "客户看到的 evidence 列表也只许有装出去的那几条"

    summary = _single_tool_row(trace_store)["result_summary"]
    assert summary["hit_count"] == 5, "找回几条仍然要说清"
    assert summary["packed_count"] == 3 and summary["dropped_count"] == 2
    assert summary["truncated"] == 0


def test_an_empty_batch_records_no_source_but_still_reports_hits(monkeypatch, trace_store):
    """裁无可裁那一发：证据袋什么都不记，而 trace 要读得出「找回 4 条、送出 0 条」。"""
    from app.agents.evidence import evidence_from_bag

    config, bag = _bag_config(step_id="trace-r112:worker:doc:zero")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "1600")
    assert context_pack_room() == 0
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(4), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)

    assert "不是模型故障" in out, out
    assert bag["documents"] == [] and evidence_from_bag(bag) == [], "一条都没读到就不许有出处"

    row = _single_tool_row(trace_store)
    assert row["status"] == "completed", "整批判空不是「没检索到」，那条路是 status=empty"
    assert bag["tool_statuses"][-1]["status"] == "completed"
    summary = row["result_summary"]
    assert summary["hit_count"] == 4 > summary["packed_count"] == 0
    assert summary["dropped_count"] == 4 and summary["truncated"] == 0


def test_the_truncated_head_is_recorded_with_the_body_that_was_sent(monkeypatch, trace_store):
    """被裁过尾那一条按实际送出的正文记：excerpt 与 content_sha256 都不许说「读过整段」。"""
    import hashlib

    from app.agents.contracts import ModelTier
    from app.common.model_budget import tier_max_tokens

    config, bag = _bag_config(step_id="trace-r112:worker:doc:cut")
    # room = n_ctx − 该档声明输出 − 两枚实测预留：把 n_ctx 调到刚够装下一条开头的一小截
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", str(tier_max_tokens(ModelTier.ANALYSIS) + RESERVE + 160))
    assert context_pack_room() == 160
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(_hits(2), pack_at_source=False))

    out = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)

    units = out.split("\n\n---\n\n")
    assert len(units) == 1 and units[0].endswith(tools.PACK_TRUNCATION_MARK), units
    assert len(bag["documents"]) == 1, bag
    document = bag["documents"][0]
    sent_body = units[0].split("\n", 1)[1][: -len(tools.PACK_TRUNCATION_MARK)]
    assert sent_body and sent_body != _hits(1)[0]["content"]
    assert document["excerpt"] == sent_body, "证据袋记的必须是模型真读到的那一截"
    assert document["metadata"]["content_sha256"] == hashlib.sha256(sent_body.encode("utf-8")).hexdigest()

    summary = _single_tool_row(trace_store)["result_summary"]
    assert summary["hit_count"] == 2 and summary["packed_count"] == 1
    assert summary["dropped_count"] == 1 and summary["truncated"] == 1


def test_analyze_data_only_records_the_dataset_that_reached_the_prompt(monkeypatch, trace_store):
    """两个文件、只有第一个装得出去：证据袋只许记那一个数据集（与 doc 腿同一读法）。"""
    import app.common.rbac as rbac
    import app.tools.excel as excel

    from app.storage import datasets as dataset_storage

    frames = {"甲表.xlsx": _wide_frame(), "乙表.xlsx": _wide_frame()}
    monkeypatch.setattr(
        tools, "_authorized_dataset_files", lambda config: ([(name, name) for name in frames], None)
    )
    monkeypatch.setattr(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: frames[path])
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (df, {"rows_in": 60, "rows_out": 60}),
    )
    monkeypatch.setattr(
        excel,
        "profile_dataframe",
        lambda df: {"rows": 60, "columns": [{"name": c, "dtype": "float64"} for c in df.columns]},
    )
    # 甲表自己就吃掉一整个 room 还多：乙表的第一段必然装不出去，这正是以前会撒谎的形状
    monkeypatch.setattr(
        tools, "_answer_query", lambda df, query, numeric_cols, text_cols: ["结论：" + "数" * 600] * 6
    )
    config, bag = _bag_config(step_id="trace-r112:worker:data:two-files", worker="data")

    out = tools._analyze_data("按金额指标1排名", config)

    assert out.startswith("数据分析结果:")
    recorded = [dataset["source_name"] for dataset in bag["datasets"]]
    assert recorded == ["甲表.xlsx"], "乙表一条都没装出去，证据袋不许说模型读过它"
    assert "📁 甲表.xlsx: " in out
    assert "📁 乙表.xlsx: " not in out


def test_query_data_records_no_dataset_when_the_block_never_goes_out(monkeypatch, trace_store):
    """查询结果整块装不出去 ⇒ 那一发什么都不记；装得出去才记那一个数据集。"""
    import pandas as pd

    frame = pd.DataFrame({"金额": [1.0, 2.0]})
    excel = _patch_data_leg_boundaries(monkeypatch, frame, stub_dataset_evidence=False)
    monkeypatch.setattr(tools, "_llm_pandas_code", lambda df, query: "df.sum()")
    monkeypatch.setattr(
        excel,
        "safe_query",
        lambda df, code: {
            "error": None,
            "result": {"明细": [{"科目": f"费用科目{row}", "金额": float(row)} for row in range(4000)]},
        },
    )

    config, bag = _bag_config(step_id="trace-r112:worker:query:zero", worker="query")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "1600")
    assert context_pack_room() == 0
    out = tools._query_data("各部门报销金额明细", config)

    assert "不是模型故障" in out, out
    assert bag["datasets"] == [], "整块没送出去，证据袋不许记这个数据集"

    config, bag = _bag_config(step_id="trace-r112:worker:query:fits", worker="query")
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)  # 上一段把 room 压成 0，这一段要恢复
    assert context_pack_room() > 0
    out = tools._query_data("各部门报销金额明细", config)

    assert out.startswith("📊 费用明细.xlsx 查询结果:")
    assert [dataset["source_name"] for dataset in bag["datasets"]] == ["费用明细.xlsx"]
