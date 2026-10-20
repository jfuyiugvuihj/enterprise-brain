"""R206a：口径题的知识库腿必须出门（run6 逐题凭据驱动，跟进单 §93.14）。

事实基线（全部来自本仓已并树的只读产物，不是执行层自述）：
- `docs/testing/sidecar-run6.jsonl` 里 `evidence_n = 0` 的口径题共 9 道：
  metric-02 / 04 / 07 / 11 / 12 / 13 / 14 / 15 / 17，其中 8 道判错。
- 那 8 道的答案正文讲的是"上传的报销明细表.csv 里没有客户字段""表里只有销售部供应链部"
  ——数据分析腿从 Excel 里凑出来的通用说法，知识库一个字都没读
  （凭据见 `docs/testing/answers-run6.jsonl` 同题号那条）。
- 机制在 `app/agents/orchestrator.py::route_main` 的关键词兜底：
  `doc_kw` 那条"制度类必须只派 doc"的分支要求**一条 `data_kw` 都不命中**，
  而这类题面里恰好带裸"统计"（metric-04/05）或裸"哪个"（metric-11/12/13/14/15），
  一票否决之后落到 `elif data_kw → 追加 data`；metric-07/17 两条兜底都不命中，
  supervisor 派什么就是什么。⇒ 派工里根本没有 doc 腿。

本单只做一件事：**已经有真实派工、而派工里没有知识库腿**的口径题，补一条 doc。
只加不减——数据分析腿一条都不撤，副作用一轮（chart/export）不改派。
"""
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes, orchestrator
from app.agents.nodes import KB_CALIBER_MARKERS, _CALIBER_MARKERS, _DEFINITIONAL_MARKERS
from app.agents.orchestrator import kb_leg_for_caliber, route_main

REPO = Path(__file__).resolve().parents[1]
SIDECAR = REPO / "docs" / "testing" / "sidecar-run6.jsonl"
ANSWERS = REPO / "docs" / "testing" / "answers-run6.jsonl"
FIXTURE = REPO / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: run6 现场：supervisor 把口径题派给数据分析腿、知识库腿整条缺席的那一批题号。
RUN6_ZERO_EVIDENCE_CALIBER = (
    "metric-02",
    "metric-04",
    "metric-07",
    "metric-11",
    "metric-12",
    "metric-13",
    "metric-14",
    "metric-15",
    "metric-17",
)


def _fixture_questions() -> dict:
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: (row.get("question") or row.get("query") or "") for row in rows}


def _sidecar() -> dict:
    rows = [json.loads(line) for line in SIDECAR.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def _dispatched(*workers):
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


def _routed(question, supervisor):
    """走一遍真 route_main，返回本轮真实派发的 worker 列表（顺序敏感）。"""
    state = {"messages": [HumanMessage(content=question), supervisor]}
    result = route_main(state)
    assert result != "reflect", f"本轮没有派发任何 worker：{question}"
    assert result[0] == "main_tools"
    return [getattr(item, "node", None) for item in result if not isinstance(item, str)]


# ==================== 判据①：run6 那 9 道题，派工里必须有 doc ====================


@pytest.mark.parametrize("question_id", RUN6_ZERO_EVIDENCE_CALIBER)
def test_a_run6_caliber_question_that_skipped_the_knowledge_base_now_sends_doc(question_id):
    """按 run6 当时的错派（只有 data）重走一遍：知识库腿必须被补上。"""
    question = _fixture_questions()[question_id]
    assert any(marker in question for marker in KB_CALIBER_MARKERS), question_id + " 不在词集覆盖面内，题号表已过期"

    dispatched = _routed(question, _dispatched("data"))

    assert "doc" in dispatched, f"{question_id}「{question}」仍然没出门查知识库：{dispatched}"


def test_the_run6_zero_evidence_set_is_still_exactly_these_ids():
    """钉住判据的事实面：sidecar 里 evidence_n=0 且命中口径词的题号就是上面那九道。

    这条一旦变红，说明跑分产物换了批而题号表没跟着换——判据①的覆盖面不能靠散文维持。

    `kind != "ok"` 的题排除在外：那是 HITL 批准的副作用一轮（chart-04 就是），
    由判据④另行豁免，不算本规则的漏网面。
    """
    sidecar, questions = _sidecar(), _fixture_questions()
    measured = sorted(
        qid
        for qid, row in sidecar.items()
        if row["kind"] == "ok"
        and row["evidence_n"] == 0
        and qid in questions
        and any(marker in questions[qid] for marker in KB_CALIBER_MARKERS)
    )

    assert measured == sorted(RUN6_ZERO_EVIDENCE_CALIBER), measured


# ==================== 判据②：只加不减，数据分析腿一条都不撤 ====================


@pytest.mark.parametrize("question_id", RUN6_ZERO_EVIDENCE_CALIBER)
def test_the_data_leg_is_never_removed_to_make_room(question_id):
    """补派读腿不许把人家的文件分析撤掉：题面里真带着上传文件的时候需要它。"""
    question = _fixture_questions()[question_id]

    assert _routed(question, _dispatched("data")) == ["data", "doc"], question_id

    assert _routed(question, _dispatched("data", "doc")) == ["data", "doc"], question_id


def test_an_already_dispatched_doc_leg_is_not_duplicated():
    """知识库腿在场就一个字都不动（metric-06/09 这类今天已对的题走的就是这支）。"""
    question = _fixture_questions()["metric-06"]

    assert _routed(question, _dispatched("doc")) == ["doc"]

    assert kb_leg_for_caliber("按财务部口径算本月销售额是多少？", ["doc", "data"]) == ["doc", "data"]


# ==================== 判据③：词集是闭集，放宽就会反噬纯算数的题 ====================


def test_a_plain_aggregation_question_still_runs_the_data_leg_only():
    """不带口径词的算数题不许被拖进知识库：那是阶段 A 时延账里的钱。"""
    assert _routed("统计一下三个区域的营收情况", _dispatched("data")) == ["data"]

    assert _routed("各部门人数排名", _dispatched("data")) == ["data"]


def test_the_marker_set_is_a_union_of_the_two_existing_closed_sets():
    """判据③的另一半：不许新造第三张表——两张已裁定的闭集并起来就是它。"""
    assert KB_CALIBER_MARKERS == tuple(dict.fromkeys(_CALIBER_MARKERS + _DEFINITIONAL_MARKERS))

    assert "口径" in KB_CALIBER_MARKERS and "哪个月" in KB_CALIBER_MARKERS

    #: 裸"多少"/裸"统计"刻意不在词集里：那是问数，不是问口径。
    assert not any(marker in "本月销售额是多少？" for marker in KB_CALIBER_MARKERS)
    assert not any(marker in "统计一下三个区域的营收情况" for marker in KB_CALIBER_MARKERS)


# ==================== 判据④：副作用一轮不改派 ====================


def test_a_side_effect_turn_is_not_relayered_by_this_rule():
    """chart/export 是 HITL 挂起的副作用一轮，补一条读腿要多烧一个 superstep：本单不动。"""
    chart_question = _fixture_questions()["chart-04"]
    assert any(marker in chart_question for marker in KB_CALIBER_MARKERS), "题面变了，本判据前提失效"

    assert _routed(chart_question, _dispatched("chart")) == ["chart"]


def test_an_abstained_turn_is_left_to_the_existing_question_lane_fill():
    """弃权轮仍归 R42 那条补派管：本规则只在已有真实派工时开口。

    metric-07 的题面一条兜底关键词都不命中、判别器又把它判到分析档（口径×取值动词），
    所以今天它以 reflect 收尾——本规则不许把这一支改成一次真实派发。
    """
    assert kb_leg_for_caliber("销售部的活跃客户数按什么口径统计？", []) == []

    question = _fixture_questions()["metric-07"]
    state = {"messages": [HumanMessage(content=question), AIMessage(content="")]}
    assert route_main(state) == "reflect"


# ==================== 判据⑤：反证钉（摘掉守卫，对应用例必须当场变红）====================


def test_counter_evidence_removing_the_fill_turns_the_run6_set_red(monkeypatch):
    """把补派变成恒等：run6 那 9 道题必须立刻回到"知识库腿缺席"的形状。"""
    monkeypatch.setattr(orchestrator, "kb_leg_for_caliber", lambda text, workers: list(workers))
    questions = _fixture_questions()

    still_missing = []
    for question_id in RUN6_ZERO_EVIDENCE_CALIBER:
        dispatched = _routed(questions[question_id], _dispatched("data"))
        if "doc" not in dispatched:
            still_missing.append(question_id)

    assert still_missing == list(RUN6_ZERO_EVIDENCE_CALIBER), still_missing


def test_counter_evidence_widening_the_marker_set_turns_the_narrowness_pin_red(monkeypatch):
    """反过来把词集放宽成"任何题都补 doc"：判据③那条必须变红，不许放宽不报账。"""
    monkeypatch.setattr(nodes, "KB_CALIBER_MARKERS", ("统计", "多少", "排名"))
    monkeypatch.setattr(
        orchestrator,
        "kb_leg_for_caliber",
        lambda text, workers: list(workers)
        if "doc" in workers or any(leg in workers for leg in orchestrator._SIDE_EFFECT_LEGS)
        or not any(marker in text for marker in nodes.KB_CALIBER_MARKERS)
        else list(workers) + ["doc"],
    )

    with pytest.raises(AssertionError):
        # 判据③ 的断言在放宽之后必须不成立：纯算数的题被拖进了知识库。
        assert _routed("统计一下三个区域的营收情况", _dispatched("data")) == ["data"]


def test_the_answers_that_motivated_this_ticket_still_say_the_file_has_no_answer():
    """钉住病灶本身：这 9 道里至少 metric-04/11 的 run6 原文确实在讲上传文件里没有该字段。

    哪天这句话不再出现在答案里，说明病灶已换，本单的判据要重新对一遍。
    """
    rows = {
        json.loads(line)["id"]: json.loads(line)
        for line in ANSWERS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    assert "不含客户" in rows["metric-04"]["answer"] or "不包含客户" in rows["metric-04"]["answer"]
    assert '没有“市场部”' in rows["metric-11"]["answer"]
    assert rows["metric-04"]["evidence"] == [] and rows["metric-11"]["evidence"] == []
