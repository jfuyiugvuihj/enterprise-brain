r"""R710 判据 3 —— 终态答复不许拿文字冒充一枚查不回来的报告文件。

病形（走查环 8，ledger.json 的 rings[ring=8]）：导出腿自报 ``status=failed`` 交回 51 字，
``report_artifact.total=0``、``artifact_rows_after=[]``、``/api/v1/artifacts`` 零枚在册，
而交回客户的终答里写着报告文件已导出并点了 ``.pdf`` 文件名。图那一格（环 7）由 R703 的
``app/agents/nodes.py::_carry_chart_truth`` 治了，报告这一格今天一句话都拦不住。

守卫形状照那枚在册正例抄：只追加、不改写，判据只读物证（本轮证据袋里真登记过的 report 件），
读不出件型的老形状一律当没这回事。四条都可失败：
  1) 声称"报告文件已导出"而台账零枚 ⇒ 末尾追加一句真话，且日志点名是哪条腿（leg=export）；
  2) 🔴 反证牙：把台账置空 ⇒ 本腿必须开口（把登记读死的那一版会当场红在这里）；
  3) 台账里放一枚真件 ⇒ 必须闭嘴，一个字都不许多；
  4) 光提到"导出"、给建议、或工具腿自己那句诚实的"本轮没有导出报告文件" ⇒ 必须闭嘴。

全程离线：不产文件、不打模型、不起容器。
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes

QUESTION = "请生成一份 2026 年上半年经营情况分析报告，并导出成报告文件"

#: 导出腿真交付那一轮的工具正文（``app/agents/tools.py::_export_report`` 的完成态）。
EXPORT_LINE = "报告已生成: [📋 下载报告](/api/v1/artifacts/art-710/download)"

#: 走查环 8 终答里那一句的复刻：文件名都点了，台账里却一枚都没有。
IMPersonATED_ANSWER = (
    "2026 年上半年经营情况分析报告已生成。\n\n"
    "📁 报告文件已导出：report_a8e1bc3666.pdf"
)

#: 工具腿今天说的那句诚实话（改后形状）：本腿对它必须闭嘴，否则就是把两句真话钉成互相打脸。
HONEST_REFUSAL = (
    "本轮没有导出报告文件：产物台账要求发起这一轮的账号有部门归属，而这个账号的部门是空的。"
    "（error_code=department_scope_required）"
)

#: 环 8 那一轮正文里真实躺着的两句建议 —— 反证牙，本腿对它们不许开口。
SUGGESTIONS = (
    "如需结合《报销明细表.csv》数据进行更详细的财务分析，请提供该文件的具体内容或上传该文件。",
    "建议导出 Excel 格式后，用 Excel 另存为 PDF。",
    "我可以将分析结果整理为 Markdown，您可复制后转换为报告。",
)


def _state(legs: dict, artifacts: list | None, worker: str = "export") -> dict:
    """一轮的终态：legs = 各条腿交回的正文，artifacts = 本轮登记下来的件（可为空）。"""
    return {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": dict(legs),
        "agent_results": {
            worker: {
                "worker": worker,
                "status": "failed" if not artifacts else "success",
                "answer": next(iter(legs.values()), ""),
                "artifacts": list(artifacts or []),
                "evidence": [],
            }
        },
    }


def _report_row() -> dict:
    return {
        "artifact_id": "art-" + uuid4().hex[:8],
        "artifact_type": "report",
        "download_url": f"/api/v1/artifacts/art-710/download",
    }


# ==================== 1) 声称已导出而台账零枚 ⇒ 钉一句真话 ====================


@pytest.mark.parametrize("claim", [IMPersonATED_ANSWER, EXPORT_LINE, HONEST_REFUSAL + "\n\n" + IMPersonATED_ANSWER])
def test_a_report_claim_without_any_registered_report_gets_one_truth_sentence(claim) -> None:
    result = nodes.synthesize(_state({"export": claim}, []))

    final = result["final_answer"]
    assert nodes.REPORT_TRUTH_SENTENCE in final, final
    assert final.endswith(nodes.REPORT_TRUTH_SENTENCE), "补写必须落在末尾，不许插进已经写的字"
    assert final.startswith(claim), "只许追加，不许改写"
    assert list(result["worker_results"]) == ["export"], result["worker_results"]


def test_the_ledger_line_names_the_leg_that_is_impersonating(caplog) -> None:
    """判据 3 要"点名是哪条腿在冒充"：光说 artifacts=0 不够，得写出是哪一条腿在说话。

    两半都可失败：日志那一行必须带 ``leg=export``；而"冒充"这对读数本身是
    声称在正文里、物证在台账外 —— ``_report_artifacts_in_state`` 交回零枚这件事得和正文
    那句声称同框出现，换一条腿（chart）来顶就把这一格判错。
    """
    state = _state({"export": IMPersonATED_ANSWER}, [])
    assert nodes._report_artifacts_in_state(state) == []
    assert nodes._claims_an_exported_report(state["worker_results"]["export"])

    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        final = nodes.synthesize(state)["final_answer"]

    assert nodes.REPORT_TRUTH_SENTENCE in final, final[-200:]
    marked = [record.message for record in caplog.records if nodes.REPORT_TRUTH_MARKER in record.message]
    assert marked, caplog.messages
    assert "leg=export" in marked[0], marked[0]
    assert "artifacts=0" in marked[0], marked[0]


def test_multi_leg_round_keeps_every_leg_and_writes_the_whole_table_back() -> None:
    """收端整张覆盖 worker_results：回写只带一条腿会把别的腿洗掉，追加只落最后那条有字的腿。"""
    legs = {"doc": "上半年营收完成年度预算目标的 48.7%。", "export": IMPersonATED_ANSWER}
    before = "\n\n".join(legs.values())

    result = nodes.synthesize(_state(legs, []))

    assert list(result["worker_results"]) == ["doc", "export"], result["worker_results"]
    assert result["worker_results"]["doc"] == legs["doc"], "别的腿被改了字"
    assert result["final_answer"].startswith(before), "已发帧必须是终答前缀"
    assert result["final_answer"] == "\n\n".join(
        [result["worker_results"][key] for key in ("doc", "export")]
    )


def test_the_truth_sentence_says_nothing_about_failure_or_permission() -> None:
    """措辞红线（抄 CHART_TRUTH_SENTENCE 那条）：这一格的事实只有"台账里没有这枚件"。"""
    for banned in ("失败", "错误", "权限", "无权", "抱歉", "无法访问"):
        assert banned not in nodes.REPORT_TRUTH_SENTENCE, banned


# ==================== 2)＋3) 🔴 反证牙：台账置空必开口，放一枚真件必闭嘴 ====================


def test_an_empty_ledger_forces_the_sentence_even_when_the_answer_looks_finished(monkeypatch) -> None:
    """把台账读数置空 ⇒ 本腿必须开口。

    这一枚就是判据 3 的反证牙：把守卫写成"信正文里那条链接"（不读物证），它在这里当场红。
    """
    artifacts = [_report_row()]
    state = _state({"export": EXPORT_LINE}, artifacts)
    assert nodes._report_artifacts_in_state(state) == artifacts

    monkeypatch.setattr(nodes, "_report_artifacts_in_state", lambda _state: [])

    assert nodes.REPORT_TRUTH_SENTENCE in nodes.synthesize(state)["final_answer"]


def test_one_registered_report_artifact_keeps_the_leg_silent() -> None:
    result = nodes.synthesize(_state({"export": IMPersonATED_ANSWER}, [_report_row()]))

    assert result["final_answer"] == IMPersonATED_ANSWER, result
    assert "worker_results" not in result, "一个字都没补，却回写了 worker_results"


def test_a_chart_row_does_not_speak_for_a_report_row() -> None:
    """件型只认 report：本轮真登记的是一枚图，报告那句话仍然没人还。"""
    chart_row = {"artifact_id": "art-chart", "artifact_type": "chart", "download_url": "/x"}

    result = nodes.synthesize(_state({"export": IMPersonATED_ANSWER}, [chart_row]))

    assert nodes.REPORT_TRUTH_SENTENCE in result["final_answer"], result["final_answer"][-200:]


def test_legacy_bare_string_artifacts_are_not_evidence(monkeypatch) -> None:
    """老形状里 artifacts 允许躺一枚裸字符串：带不出件型就判不了，判不了就当没这回事。"""
    state = _state({"export": EXPORT_LINE}, [])
    state["agent_results"]["export"]["artifacts"] = ["/api/v1/artifacts/art-9/content.png"]

    assert nodes._report_artifacts_in_state(state) == []
    assert nodes.REPORT_TRUTH_SENTENCE in nodes.synthesize(state)["final_answer"]


def test_the_report_guard_does_not_silence_the_chart_guard() -> None:
    """同族两格各说各的：图与报告都没在册 ⇒ 两句真话都得在，且各在其位。"""
    legs = {"chart": "图表已生成：![月度报销柱状图](/static/chart.png)", "export": IMPersonATED_ANSWER}

    final = nodes.synthesize(_state(legs, []))["final_answer"]

    assert nodes.CHART_TRUTH_SENTENCE in final, final
    assert nodes.REPORT_TRUTH_SENTENCE in final, final
    assert final.index(nodes.CHART_TRUTH_SENTENCE) < final.index(nodes.REPORT_TRUTH_SENTENCE)


# ==================== 4) 反证牙：光提到导出、给建议、或工具腿自己说了实话 ====================


def test_the_honest_refusal_from_the_export_leg_is_not_called_a_claim() -> None:
    """工具腿那句「本轮没有导出报告文件」已经是真话，本腿再补一句就是替客户多一句假话。"""
    result = nodes.synthesize(_state({"export": HONEST_REFUSAL}, []))

    assert result["final_answer"] == HONEST_REFUSAL, result
    assert nodes.REPORT_TRUTH_SENTENCE not in result["final_answer"]


@pytest.mark.parametrize("answer", SUGGESTIONS)
def test_advice_about_exporting_is_not_a_claim_that_it_happened(answer) -> None:
    result = nodes.synthesize(_state({"doc": answer}, []))

    assert nodes.REPORT_TRUTH_SENTENCE not in result["final_answer"], result["final_answer"][-200:]
    assert "worker_results" not in result


def test_the_users_own_question_is_not_a_claim() -> None:
    """"并导出成报告文件"是问话，不是声称。"""
    state = _state({"doc": "好的，我会为您生成报告。"}, [])
    state["messages"] = [HumanMessage(content=QUESTION)]

    result = nodes.synthesize(state)

    assert nodes.REPORT_TRUTH_SENTENCE not in result["final_answer"]


def test_an_empty_round_produces_no_claim_and_no_appendage() -> None:
    state = _state({"export": ""}, [])
    state["final_answer"] = ""
    state["agent_results"] = {}

    result = nodes.synthesize(state)

    assert nodes.REPORT_TRUTH_SENTENCE not in str(result.get("final_answer") or "")


# ==================== 判定口自己：什么算"声称已交付" ====================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (IMPersonATED_ANSWER, True),
        (EXPORT_LINE, True),
        ("报告文件已导出，请在产物面板查回。", True),
        ("本轮报告已交付：/api/v1/artifacts/art-1/download。", True),
        (HONEST_REFUSAL, False),
        ("如需更详细的财务分析，请上传该文件。", False),
        ("报告生成就到这里，本轮没有落文件。", False),
        ("本月合计 17100 元。", False),
        ("", False),
        (None, False),
    ],
)
def test_claims_an_exported_report_recognises_completed_claims_only(text, expected) -> None:
    assert nodes._claims_an_exported_report(text) is expected, text


def test_the_guard_reads_the_ledger_not_the_answer_for_evidence() -> None:
    """判据形态是读数：件型常量只此一处，正文里的 URL 从不参与判定。"""
    row = _report_row()
    state = _state({"export": IMPersonATED_ANSWER}, [row])

    assert nodes._report_artifacts_in_state(state) == [row]
    assert row["download_url"] not in IMPersonATED_ANSWER