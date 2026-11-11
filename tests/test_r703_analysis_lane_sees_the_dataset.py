"""R703 · 分析档带着表那一轮：数据集必须真进 Data 腿（判据 1、判据 2）

病形现取（判据原文引的走查账，环 7 未达）：客户带着 报销明细表.csv 问「按月份统计报销金额，
并画一张柱状图」，屏上回的是「文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件…」，
并让客户自己去 SAP／用友导出 Excel。

取证结论（一手现读，逐条坐标见凭据纸 docs/testing/r703-2026-10-06.md）：Data 腿今天**确实**
拿到了这张表 —— 但 ``app/agents/tools.py::_answer_query`` 的分组汇总那一支按五枚硬写字面触发
（对比／比较／分组／按区域／按类型，后两枚是别家夹具的列名手抄），真表真问法一枚都不命中；
选列那一支做的是 ``tc in query`` 单向包含，列名「发生月份」不是问法「按月份…」的子串。
于是交回的只有 ``📈 数值统计`` 一段，没有一个月的数字。两腿的上下文不合并
（``app/agents/orchestrator.py::_make_worker_wrapper`` 只喂一枚 HumanMessage，合流发生在
``app/agents/nodes.py::synthesize`` 的 ``"\\n\\n".join``），所以 Doc 腿从头到尾没看见这张表。

本件钉四格，每条都可失败：
  1) 判据 1 —— 表带着走：Data 腿的上下文里读得出这张表的**行数与列数**（可解析的读数，不是"好像有"）；
  2) 判据 2 —— 不许再答「没有数据」：分组汇总按维度真列名给全月度数字，答复里不许出现
     「文档里没有数据」那一张脸；本轮真算过有行的表而答复仍走那一支时，末尾必须钉上一句真话；
  3) 🔴 反证牙 —— 盘上副本改成零行：走「量不到」那一支并点名是哪张表零行，不许含糊拒答、不许编数据；
  4) 新补的那条触发通路自己 —— 维度在这张表的列名里对不上时，不许凭空长出一段汇总。

全程离线：模型那一条腿用本仓在册的假腿 ``app/agents/nodes.py::_OfflineModel``（conftest 把
LOCAL_MODEL_NAME 关死），一发真模型都不打、一个容器不起、一块 GPU 不碰；数据集台账落 tmp_path。

🔴 夹具口径：判据 1 原文写「附 tests/fixtures 里现成的 csv」，10-06 现取
`git ls-files tests/fixtures` 交回 12 枚（2 枚 jsonl／4 枚 pdf／6 枚 py，csv 零枚）—— 那一格
前提是错的。本件按判据 6 不为此造新链路，照 ``tests/test_r178_dataset_visibility_faces.py``
在册的临时台账写法把同一张表的形状写进 tmp_path：9 枚列名与发生月份那 6 枚值和
`data/报销明细表.csv` 逐字同形，行数按夹具缩到 18（判据钉的是形状可指认，不是行数大小）。
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.agents import evidence, nodes, orchestrator, tools
from app.agents.planner import build_task_plan

DEPT = "r703-报销测试部"
TABLE = "报销明细表.csv"
EMPTY_TABLE = "零行报销明细表.csv"
QUESTION = "按月份统计报销金额，并画一张柱状图"

HEADER = "单据号,部门,报销人,费用类型,金额,发生月份,出差天数,提交日期,审批状态"
COLUMN_COUNT = 9
MONTHS = ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06")
ROWS_PER_MONTH = 3
ROW_COUNT = len(MONTHS) * ROWS_PER_MONTH

#: 夹具里每月报销金额合计。写死，不照产品算法回算：分组算错的一族（选错列、漏一组、
#: 把均值当合计）必须由这一枚独立期望值当场抓住。
MONTH_TOTALS = {
    "2026-01": 600.0,
    "2026-02": 1500.0,
    "2026-03": 2400.0,
    "2026-04": 3300.0,
    "2026-05": 4200.0,
    "2026-06": 5100.0,
}
GRAND_TOTAL = 17100.0

#: 走查里那句客户看见的话（终答逐字取自 ledger 环 7 的 after_approve.answer_tail，此处只留
#: 承重那一句）。判据 2 要钉红的正是"答复走这一支"。
ABSENCE_BLAME_ANSWER = (
    "无法直接生成按月份统计的报销金额柱状图，因为：\n"
    "1. 文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件，不包含具体的报销金额、月份等统计数据。"
)

#: ``📁 {文件}: {行}行 × {列}列 — 列: …`` —— 判据 1 要的那枚"数据形状可指认"。
SHAPE_LINE = re.compile(r"📁 (?P<file>[^:]+): (?P<rows>\d+)行 × (?P<cols>\d+)列 — 列: (?P<columns>.+)")


def _table_text(rows_per_month: int = ROWS_PER_MONTH) -> str:
    """9 列 × 6 个月的报销明细表；金额逐行 +100，于是每月合计就是 MONTH_TOTALS 那枚数。"""
    depts = ("销售部", "研发部", "财务部")
    people = ("张三", "李四", "王五")
    types = ("差旅", "招待", "办公")
    lines = [HEADER]
    index = 0
    for month in MONTHS:
        for _ in range(rows_per_month):
            index += 1
            lines.append(
                ",".join(
                    [
                        f"BX-{index:04d}",
                        depts[index % 3],
                        people[index % 3],
                        types[index % 3],
                        str(100 * index),
                        month,
                        str(index % 4),
                        f"{month}-05",
                        "已通过",
                    ]
                )
            )
    return "\n".join(lines) + "\n"


def _registry(monkeypatch, tmp_path, slug: str = "main"):
    """一枚用例一座临时台账（照 R178 在册写法：台账名唯一，共用就互相顶掉）。"""
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / slug
    registry = DatasetRegistry(root=root, metadata_path=tmp_path / (slug + "-meta.json"))
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    return registry


def _register(registry, filename: str, text: str, *, department: str = DEPT):
    from app.agents.contracts import Principal

    path = registry.root / filename
    path.write_text(text, encoding="utf-8-sig")
    return registry.register(
        path,
        principal=Principal.from_user(
            {"id": "u-r703-owner", "username": "r703-owner", "role": "admin", "department": department}
        ),
        classification="1",
    )


def _config(**overrides) -> dict:
    configurable = {
        "id": "u-r703-asker",
        "username": "r703-admin",
        "role": "admin",
        "department": DEPT,
        # 每次调用一座新会话：data_graph 自带 checkpointer，同名 thread 复用会把上一枚
        # 用例的消息历史带进来，读数就不再是“这一轮”的。
        "thread_id": "t-r703-" + uuid4().hex[:8],
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _data_leg_graph():
    """生产 Data 腿那一格：同一枚 ``DATA_PROMPT``、同两枚工具，模型换成本仓在册的假腿。

    🔴 不许直接 invoke 模块级的 ``app/agents/orchestrator.py::data_graph``：它按 ANALYSIS 档
    装配真模型，一发就朝 127.0.0.1:11434 开插座，判据明令零真模型（``tests/conftest.py``
    那枚 R56 端口闸门会当场把这枚用例记成 error）。本件复用全仓在册的
    ``app/agents/nodes.py::_OfflineModel`` —— 它先发一枚 ``analyze_data`` 调用，再把工具返回串
    逐字当作正文，于是"Data 腿交出什么"就等于"工具边界交出什么"，中间没有第二份话术。
    """
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        nodes._OfflineModel(),
        [tools.analyze_data, tools.query_data],
        prompt=orchestrator.DATA_PROMPT,
    )


def _run_leg(config: dict, question: str = QUESTION) -> str:
    """真 Data 腿（生产装配 + 假模型腿）跑完交回的正文。"""
    result = _data_leg_graph().invoke({"messages": [HumanMessage(content=question)]}, config=config)
    for message in reversed(result.get("messages", [])):
        if getattr(message, "content", "") and not getattr(message, "tool_calls", None):
            return str(message.content)
    return ""


def _agent_results_from_bag(bag: dict, answer: str, worker: str = "data") -> dict:
    """把工具边界记下的证据袋折成 ``agent_results`` 那一格的形状。

    映射走生产唯一的出口 ``app/agents/evidence.py::evidence_from_bag`` —— 本件不手写第二份
    字段搬运，也不编读数。
    """
    rows = [item.model_dump() for item in evidence.evidence_from_bag(bag)]
    return {worker: {"worker": worker, "status": "success", "answer": answer, "evidence": rows}}


def _synthesize(doc_answer: str, data_answer: str, bag: dict) -> dict:
    """分析档那一轮的合流：两条腿各交一份正文，终答由 ``synthesize`` 折出来。"""
    state = {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": {"doc": doc_answer, "data": data_answer},
        "agent_results": _agent_results_from_bag(bag, data_answer),
    }
    return nodes.synthesize(state)


# ==================== 判据 1 · 数据形状可指认 ====================


def test_the_round_dispatches_the_data_leg_before_anything_else() -> None:
    """判据 1 的前提：这一轮 Data 腿**在场** —— 病不在派工，在派出去之后手里没数字。

    走确定性规则腿 ``app/agents/planner.py::build_task_plan``（零模型）：这道闸今天就把
    data 排进了计划，``route_main`` 也照计划派发。取证里那枚"根本没派 Data 腿"的猜想
    因此不成立，本件后面的钉子全部落在"派出去之后拿没拿到这张表"。
    """
    planned = [str(task.get("worker")) for task in build_task_plan(QUESTION)]

    assert "data" in planned, planned
    assert "doc" in planned, planned




def test_the_data_leg_carries_a_parseable_row_and_column_readout(monkeypatch, tmp_path) -> None:
    registry = _registry(monkeypatch, tmp_path)
    _register(registry, TABLE, _table_text())
    config = _config()

    answer = _run_leg(config)

    lines = [line for line in answer.splitlines() if line.startswith("📁 ")]
    assert len(lines) == 1, lines
    match = SHAPE_LINE.fullmatch(lines[0])
    assert match is not None, lines[0]
    assert match["file"] == TABLE
    assert int(match["rows"]) == ROW_COUNT, "行数读数与夹具不符"
    assert int(match["cols"]) == COLUMN_COUNT, "表头枚数读数与夹具不符"
    named = [item.strip() for item in match["columns"].split(",")]
    assert len(named) == COLUMN_COUNT, named


def test_the_shape_readout_survives_without_a_selected_filename(monkeypatch, tmp_path) -> None:
    """本轮没把 ``data_filename`` 递进 configurable（走查那一轮的真实形状）也必须看得见表。

    出处记在凭据纸：``app/api/v1/chat.py::_should_use_data_context`` 因为问法里有「报销」
    那枚 document_terms 就否掉了点名文件。本件不碰那一枚函数（禁区），钉的是"没点名
    也不能把整张表洗掉"这一格 —— 台账里可见的数据集仍要进 Data 腿。
    """
    registry = _registry(monkeypatch, tmp_path, slug="no-selection")
    _register(registry, TABLE, _table_text())
    config = _config()
    assert "data_filename" not in config["configurable"]

    answer = _run_leg(config)

    assert f"{TABLE}: {ROW_COUNT}行 × {COLUMN_COUNT}列" in answer, answer[:400]


# ==================== 判据 2 · 不许再答「没有数据」 ====================


def test_monthly_aggregate_reaches_the_answer_with_the_real_column_name(monkeypatch, tmp_path) -> None:
    registry = _registry(monkeypatch, tmp_path, slug="aggregate")
    _register(registry, TABLE, _table_text())
    config = _config()

    answer = _run_leg(config)

    assert "📋 按 发生月份 分组汇总:" in answer, answer[:600]
    for month, total in MONTH_TOTALS.items():
        assert f"{month}: 金额={total:.1f}" in answer, (month, answer[:600])
    assert f"合计: 金额: {GRAND_TOTAL:.1f}" in answer, answer[:600]


def test_the_data_leg_says_no_absence_blame_when_the_table_has_rows(monkeypatch, tmp_path) -> None:
    registry = _registry(monkeypatch, tmp_path, slug="no-blame")
    _register(registry, TABLE, _table_text())
    config = _config()

    answer = _run_leg(config)

    for phrase in nodes._DATASET_ABSENCE_BLAME:
        assert phrase not in answer, (phrase, answer[:400])
    assert "文件里没有数据行" not in answer


def test_an_answer_blaming_documents_gets_one_truth_sentence(monkeypatch, tmp_path) -> None:
    """Doc 腿没看见这张表（两腿不合流），它的"文档里没有数据"必须被钉一句真话。

    追加而不改写：原话一个字都不许被替掉，收端折出来的正文仍以补写前那一份为前缀。
    """
    registry = _registry(monkeypatch, tmp_path, slug="truth")
    _register(registry, TABLE, _table_text())
    config = _config()
    data_answer = _run_leg(config)

    result = _synthesize(ABSENCE_BLAME_ANSWER, data_answer, config["configurable"]["evidence_bag"])

    final = result["final_answer"]
    truth = f"本轮带着数据文件：{TABLE}（{ROW_COUNT} 行 × {COLUMN_COUNT} 列）。"
    assert truth in final, final[-400:]
    assert final.endswith(nodes.DATASET_TRUTH_SENTENCE.format(names=f"{TABLE}（{ROW_COUNT} 行 × {COLUMN_COUNT} 列）"))
    before = "\n\n".join((ABSENCE_BLAME_ANSWER, data_answer))
    assert final.startswith(before), "补写改写了模型已经写过的字"
    assert list(result["worker_results"]) == ["doc", "data"], "回写只带一条腿会把别的腿洗掉"
    assert "__reset__" not in result["worker_results"]


def test_the_truth_sentence_is_not_spoken_when_the_answer_never_blames_the_documents(
    monkeypatch, tmp_path
) -> None:
    """没有"没有数据"那句话时本腿必须闭嘴 —— 否则是给好答复后面缀一句多余的免责。"""
    registry = _registry(monkeypatch, tmp_path, slug="quiet")
    _register(registry, TABLE, _table_text())
    config = _config()
    data_answer = _run_leg(config)

    result = _synthesize("2026 年上半年报销合计 17100 元，逐月见上一段。", data_answer,
                         config["configurable"]["evidence_bag"])

    assert nodes.DATASET_TRUTH_SENTENCE.split("：")[0] not in result["final_answer"]
    assert "worker_results" not in result, result


# ==================== 判据 2 反证牙 · 零行的那一张表 ====================


def test_a_zero_row_copy_is_named_and_no_number_is_invented(monkeypatch, tmp_path) -> None:
    """盘上副本改成零行 ⇒ 走「量不到」那一支并点名是哪张表零行，不许含糊拒答、不许编数据。"""
    registry = _registry(monkeypatch, tmp_path, slug="zero-row")
    _register(registry, EMPTY_TABLE, HEADER + "\n")
    config = _config(thread_id="t-r703-zero")

    answer = _run_leg(config)

    assert f"📧 {EMPTY_TABLE}: 文件里没有数据行" in answer, answer
    codes = [
        str(item.get("error_code") or "")
        for item in config["configurable"]["evidence_bag"]["tool_statuses"]
    ]
    assert "no_visible_rows" in codes, codes
    assert "分组汇总" not in answer, answer
    for month in MONTHS:
        assert month not in answer, (month, answer)
    assert f"{GRAND_TOTAL:.1f}" not in answer
    for face in ("暂无数据文件", "暂无数据：", "一份都读不到"):
        assert face not in answer, answer

    result = _synthesize(ABSENCE_BLAME_ANSWER, answer, config["configurable"]["evidence_bag"])
    assert "本轮带着数据文件" not in result["final_answer"], "零行的表被说成带着数据＝新假话"


# ==================== 新通路自己不许长出假汇总 ====================


#: 「按月看报销」那一例是**故意钉住的边界**，不是漏网：单字候选只认等值（见
#: ``app/agents/tools.py::_named_dimension_column``），「月」对「发生月份」不许成立 ——
#: 允许单字包含匹配，任何列名里带「月」的表都会被一次「按月」判成按那一列分组。
@pytest.mark.parametrize(
    ("query", "columns", "expected"),
    [
        ("按月份统计报销金额", ["发生月份"], "发生月份"),
        ("按发生月份统计报销金额", ["发生月份"], "发生月份"),
        ("各费用类型的报销金额", ["费用类型"], "费用类型"),
        ("逐部门的报销合计", ["部门"], "部门"),
        ("分月份看报销", ["发生月份"], "发生月份"),
        ("按月份统计报销金额", ["部门", "费用类型"], None),
        ("按人统计报销金额", ["报销人", "部门"], None),
        ("按月看报销", ["发生月份"], None),
        ("分析金额分布", ["部门"], None),
        ("", ["发生月份"], None),
    ],
)
def test_the_dimension_resolves_only_against_a_real_column_name(query, columns, expected) -> None:
    assert tools._named_dimension_column(query, columns) == expected, query


def test_a_dimension_the_table_does_not_have_adds_no_summary_block() -> None:
    import pandas as pd

    frame = pd.DataFrame({"部门": ["销售部", "研发部"], "金额": [10.0, 20.0]})
    blocks = tools._answer_query(frame, QUESTION, ["金额"], ["部门"])

    assert not [block for block in blocks if "分组汇总" in block], blocks