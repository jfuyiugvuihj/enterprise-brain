"""R122 · 装不下时不许交一枚假料当检索结果（跟进单 §55A 判据 ①–④）。

全离线：不连模型、不起服务、不动数据库、不碰 ``chroma_db/**``。检索腿一律 monkeypatch 掉
``tools._get_pipeline``，数据腿只替到"能拼出返回串"那一层；``LOCAL_MODEL_NAME`` 由
tests/conftest.py 的哨兵挡住，一次 socket 都不该开。

现场（§55A 真机）：同一轮连发 ``search_docs``，第一发把 room 吃满，第二三发只剩几十枚残料，
而 ``_fit_unit_to_room`` 照样交回「行头 + 一小截正文 + 截断标记」——``packed=31`` 那一发里
行头 18 枚、标记 10 枚，正文只剩几个字，模型读到的是一条看着像证据的空壳。本文件钉四件事：

- ① 门槛 ``PACK_MIN_STUB_BODY_TOKENS`` 由真语料正文长度分布定（本文件最后一枚用例复算）；
- ② 够不上门槛就不交桩，改交「本轮检索预算已用尽，未取回新料（已装 N 枚 / 剩 M 枚）」；
- ③ ``[PromptPack]`` 台账只新增 ``stub=`` 一枚，旧字段名与相对顺序一枚都不动；
- ④ 同轮连发三次：第三次拿到那句人话，而不是一枚 31 枚的桩。
"""
import logging
import os
import re
import statistics

import pytest

from app.agents import tools
from app.agents.contracts import ModelTier
from app.common.model_budget import tier_max_tokens
from app.rag.retrieval_pipeline import (
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_SHELL_RESERVE_TOKENS,
    DOC_HIT_CONTENT_CHARS,
    PROMPT_PACK_MARKER,
    context_pack_room,
    format_relevance,
    text_pack_tokens,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESERVE = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS
MARK = tools.PACK_TRUNCATION_MARK

#: ``[PromptPack]`` 台账的字段顺序（判据 ③）：R122 只在 ``truncated=`` 之后插一枚 ``stub=``，
#: 其余一枚不改名、不改相对位置——run3/run4 的日志口径要连续。
PACK_FIELDS_BEFORE_R122 = (
    "leg",
    "tier",
    "room_total",
    "room_left",
    "candidates",
    "fitted",
    "dropped",
    "truncated",
    "packed_tokens",
    "ledger_packed_tokens",
    "prompt_estimate_tokens",
    "ledger",
    "dropped_labels",
)
PACK_FIELDS_AFTER_R122 = (
    "leg",
    "tier",
    "room_total",
    "room_left",
    "candidates",
    "fitted",
    "dropped",
    "truncated",
    "stub",
    "packed_tokens",
    "ledger_packed_tokens",
    "prompt_estimate_tokens",
    "ledger",
    "dropped_labels",
)


@pytest.fixture(autouse=True)
def _clean_pack_ledger():
    """装箱账是进程内的：用例之间必须清干净，否则上一条的账会吃掉下一条的 room。"""
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()
    yield
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()


@pytest.fixture
def pack_log(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _fields(line):
    return dict(re.findall(r"([a-z_]+)=(\S+)", line))


def _pack_lines(log, leg):
    """只取装箱那一发账（带 ``room_total=`` 的行）：data 腿另有一行 ``dataset=... recorded=``，
    它说的不是装箱形状，别混进来当同一枚字段读。"""
    return [
        _fields(record.getMessage())
        for record in log.records
        if PROMPT_PACK_MARKER in record.getMessage()
        and f"leg={leg}" in record.getMessage()
        and "room_total=" in record.getMessage()
    ]


def _tool_config(step_id="trace-r122:worker:doc"):
    """带真身份与证据袋的 config：三条腿都要过授权那一关，缺身份就走不到装箱那一层。"""
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r122", "role": "admin", "department": "财务部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf["thread_id"] = "thread-r122"
    conf["worker"] = "doc"
    if step_id:
        conf["step_id"] = step_id
    bag = conf["evidence_bag"]
    return {"configurable": conf}, bag


def _pin_room(monkeypatch, room_tokens):
    """把 room 钉成想要的数：只动 ``MODEL_CONTEXT_TOKENS``，容量真源不抄第二份。"""
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", str(room_tokens + RESERVE + tier_max_tokens(ModelTier.ANALYSIS)))
    assert context_pack_room() == room_tokens
    return room_tokens


def _hit(index, *, body_chars=240):
    """一枚与真机同形状的命中：正文是 ``body_chars`` 个汉字（一枚汉字＝一枚 token，可算准）。"""
    return {
        "source": "差旅费报销制度.pdf",
        "chunk_index": index,
        "_score": round(0.93 - 0.01 * index, 2),
        "content": ("住宿费限额按职级分档执行并需事前审批发票三十日内提交财务部复核后打款。" * 40)[:body_chars],
    }


def _unit(index, hit):
    """``search_docs`` 拼返回串的那一公式：行头一行 + 正文（截到 ``DOC_HIT_CONTENT_CHARS``）。"""
    return (
        f"[{index}] 来源:{hit['source']} 相关度:{format_relevance(hit)}\n"
        f"{hit['content'][:DOC_HIT_CONTENT_CHARS]}"
    )


class _FakePipeline:
    def __init__(self, hits):
        self.hits = hits

    def search_for_principal(self, query, principal, top_k, context_pack=False):
        return list(self.hits), ["住宿费 打款 时限"]


def _doc_hits(count=5):
    return [_hit(index) for index in range(1, count + 1)]


# ==================== 判据 ④：同轮连发三次，第三次不许再交桩 ====================


def test_three_searches_in_one_turn_refuse_the_third_stub(monkeypatch, pack_log):
    """同轮第三发只剩几十枚残料：拿到「预算用尽」那句，而不是一枚 31 枚的桩。"""
    hits = _doc_hits(5)
    costs = [text_pack_tokens(_unit(index, hit)) for index, hit in enumerate(hits, 1)]
    header_cost = text_pack_tokens(_unit(1, hits[0]).split("\n", 1)[0])
    # 第一发装得下整批，第二发恰好装得下最高分那一条，第三发只剩"行头+标记+12 个汉字"那么点房
    leftover = header_cost + text_pack_tokens(MARK) + 12
    room = _pin_room(monkeypatch, sum(costs) + costs[0] + leftover)
    assert costs[1] > leftover, "夹具不成立：第二发就该装下两条，第三发的形状不是真机那一发"
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(hits))

    config, bag = _tool_config(step_id="r122:worker:doc:three")
    first = tools.search_docs.invoke({"query": "住宿费打款时限"}, config=config)
    second = tools.search_docs.invoke({"query": "住宿费打款时限 打款时限"}, config=config)
    seen = len(bag["documents"])
    third = tools.search_docs.invoke({"query": "住宿费打款时限 财务复核"}, config=config)

    assert MARK not in first and MARK not in second, "前两发交的是整条命中，不是桩"
    assert third.startswith("本轮检索预算已用尽，未取回新料"), third
    assert MARK not in third, "被拦下来的那一发一个字正文都不许交出去"
    assert "差旅费报销制度.pdf" not in third, "不许再把行头冒充成一条命中"

    lines = _pack_lines(pack_log, "doc")
    assert [line["stub"] for line in lines] == ["none", "none", "refused"], lines
    last = lines[2]
    assert int(last["fitted"]) == 0 and int(last["dropped"]) == len(hits), last
    assert int(last["truncated"]) == 0 and int(last["packed_tokens"]) == 0, "没送出去就不许记账"
    assert int(last["room_left"]) == leftover, last
    # 判据 ②：句子里的 N/M 是账上的真数，不是写死的
    assert f"已装 {int(last['ledger_packed_tokens'])} 枚" in third, third
    assert f"剩 {int(last['room_left'])} 枚" in third, third
    assert int(last["ledger_packed_tokens"]) + int(last["room_left"]) == room

    assert len(bag["documents"]) == seen, "空手那一发不许给证据袋添任何出处"


# ==================== 判据 ①②：门槛只拦残料，达标那档照旧交 ====================


def test_a_stub_that_clears_the_threshold_is_still_delivered(monkeypatch, pack_log):
    """半条命中仍是证据：正文够门槛的桩照旧交出去，账记 ``truncated=1 stub=kept``。"""
    hits = _doc_hits(5)
    costs = [text_pack_tokens(_unit(index, hit)) for index, hit in enumerate(hits, 1)]
    header_cost = text_pack_tokens(_unit(1, hits[0]).split("\n", 1)[0])
    body = tools.PACK_MIN_STUB_BODY_TOKENS + 20
    _pin_room(monkeypatch, header_cost + text_pack_tokens(MARK) + body)
    assert min(costs) > header_cost + text_pack_tokens(MARK) + body, "夹具不成立：整条本来装得下"
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(hits))

    out = tools.search_docs.invoke(
        {"query": "住宿费打款时限"}, config=_tool_config(step_id="r122:worker:doc:kept")[0]
    )

    assert out.endswith(MARK), out
    assert tools._stub_body_tokens(out, _unit(1, hits[0])) >= tools.PACK_MIN_STUB_BODY_TOKENS
    line = _pack_lines(pack_log, "doc")[-1]
    assert line["stub"] == "kept" and int(line["truncated"]) == 1, line


def test_a_stub_cut_inside_the_header_counts_as_zero_body(monkeypatch, pack_log):
    """裁在行头之内的桩＝零枚正文：行头是元数据，不是模型能据以作答的料。"""
    hits = _doc_hits(5)
    header_cost = text_pack_tokens(_unit(1, hits[0]).split("\n", 1)[0])
    _pin_room(monkeypatch, header_cost + text_pack_tokens(MARK) - 1)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(hits))

    out = tools.search_docs.invoke(
        {"query": "住宿费打款时限"}, config=_tool_config(step_id="r122:worker:doc:head")[0]
    )

    assert out.startswith("本轮检索预算已用尽，未取回新料"), out
    assert _pack_lines(pack_log, "doc")[-1]["stub"] == "refused"


# ==================== 判据 ③：台账只新增一枚，旧字段一枚不改 ====================


def test_prompt_pack_line_only_adds_the_stub_field(monkeypatch, pack_log):
    hits = _doc_hits(5)
    _pin_room(monkeypatch, 900)
    monkeypatch.setattr(tools, "_get_pipeline", lambda: _FakePipeline(hits))

    tools.search_docs.invoke({"query": "住宿费打款时限"}, config=_tool_config(step_id="r122:worker:doc:fields")[0])

    messages = [
        record.getMessage()
        for record in pack_log.records
        if PROMPT_PACK_MARKER in record.getMessage() and "leg=doc" in record.getMessage()
    ]
    assert messages, "一行装箱账都没有，这条用例就成了空响"
    names = tuple(re.findall(r"([a-z_]+)=", messages[0]))
    assert names == PACK_FIELDS_AFTER_R122, messages[0]
    old = tuple(name for name in names if name != "stub")
    assert old == PACK_FIELDS_BEFORE_R122, "旧字段一枚不许改名、不许挪位置"


# ==================== 三条腿：data 腿与 query 腿共用同一枚门槛 ====================


def _patch_data_leg(monkeypatch, frame):
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.storage import datasets as dataset_storage

    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: ([("费用明细.xlsx", "p")], None))
    monkeypatch.setattr(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)
    monkeypatch.setattr(tools, "_record_dataset_evidence", lambda config, filename, df: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: frame)
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (df, {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])}),
    )
    return excel


def _many_column_frame():
    import pandas as pd

    columns = {f"金额指标{index}": [float(row * index) for row in range(20)] for index in range(1, 41)}
    return pd.DataFrame(columns)


def test_data_leg_refuses_an_unreadable_stub(monkeypatch, pack_log):
    """analyze_data 腿：room 只剩几十枚时，第一段的文件名尾巴不是分析结论。"""
    excel = _patch_data_leg(monkeypatch, _many_column_frame())
    monkeypatch.setattr(excel, "profile_dataframe", lambda df: {"rows": int(df.shape[0]), "columns": [{"name": c, "dtype": "float64"} for c in df.columns]})
    _pin_room(monkeypatch, 40)

    out = tools._analyze_data("按金额指标1排名", _tool_config(step_id="r122:worker:data")[0])

    assert out.startswith("本轮检索预算已用尽，未取回新料"), out
    assert MARK not in out and "金额指标1" not in out, out
    line = _pack_lines(pack_log, "data")[-1]
    assert line["stub"] == "refused" and int(line["fitted"]) == 0, line


def test_query_leg_refuses_an_unreadable_stub(monkeypatch, pack_log):
    """query_data 腿：查询结果是一整块，只裁出「📊 x.xlsx 查询结果:」加几个字就不许交。"""
    import pandas as pd

    frame = pd.DataFrame({"金额": [1.0, 2.0]})
    excel = _patch_data_leg(monkeypatch, frame)
    monkeypatch.setattr(tools, "_llm_pandas_code", lambda df, query: "df.sum()")
    monkeypatch.setattr(
        excel,
        "safe_query",
        lambda df, code: {"error": None, "result": "各部门报销金额合计 3.0 元，明细如下：" + "费" * 900},
    )
    _pin_room(monkeypatch, 42)

    out = tools._query_data("各部门报销金额明细", _tool_config(step_id="r122:worker:query")[0])

    assert out.startswith("本轮检索预算已用尽，未取回新料"), out
    assert MARK not in out and "查询结果" not in out, out
    line = _pack_lines(pack_log, "query")[-1]
    assert line["stub"] == "refused" and int(line["fitted"]) == 0, line


# ==================== 判据 ①复算：门槛值来自真语料正文长度分布 ====================


def _corpus_bodies():
    """把 ``documents/*.txt`` 按生产 splitter 重切，取每枚 chunk 真正会进 prompt 的那段正文。

    刻意不读 ``chroma_db``（评测窗口在跑，一个字节都不碰），也不读 ``tests/fixtures``：
    这里要的是"这家客户的资料切成块之后有多长"，不是测试夹具凑出来的字数。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    from app.rag.loader import load_txt

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=DOC_HIT_CONTENT_CHARS,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", "　", " ", ""],
    )
    directory = os.path.join(REPO, "documents")
    paths = sorted(
        os.path.join(directory, name) for name in os.listdir(directory) if name.endswith(".txt")
    )
    assert len(paths) >= 50, f"真语料只剩 {len(paths)} 份原文，这枚复算就没有样本了"
    bodies = []
    for path in paths:
        for chunk in splitter.split_text(load_txt(path)):
            if chunk.strip():
                bodies.append(chunk[:DOC_HIT_CONTENT_CHARS])
    return bodies


def _percentile(values, share):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(share * (len(ordered) - 1)))))
    return ordered[index]


def test_stub_threshold_sits_in_the_measured_band():
    """门槛压在"真料够不着、残料够得着"那条带上：两端的数都从真语料现算。"""
    bodies = _corpus_bodies()
    assert len(bodies) >= 300, f"样本只剩 {len(bodies)} 枚，不足以定这枚门槛"
    sizes = [text_pack_tokens(body) for body in bodies]
    # 一、整条交付的正文长度下界（p05）：门槛必须在它以下，否则真料会被这档误伤
    p05_full_hit = _percentile(sizes, 0.05)
    assert tools.PACK_MIN_STUB_BODY_TOKENS < p05_full_hit, (
        f"门槛 {tools.PACK_MIN_STUB_BODY_TOKENS} 已顶到真料 p05={p05_full_hit}，会拦下真命中"
    )
    # 二、"到第一个完整句尾需要多少枚正文"的中位数：门槛至少要到这条线，桩才可能含一句完整话
    first_sentences = []
    for body in bodies:
        match = re.search(r"[。！？；]", body)
        if match:
            first_sentences.append(text_pack_tokens(body[: match.end()]))
    median_sentence = statistics.median(first_sentences)
    assert tools.PACK_MIN_STUB_BODY_TOKENS >= median_sentence, (
        f"门槛 {tools.PACK_MIN_STUB_BODY_TOKENS} 低于中位完整句长 {median_sentence}，放行的桩仍然读不出话"
    )
