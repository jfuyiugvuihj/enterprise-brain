"""R703 · 判据 3 —— 答复侧不许拿文字冒充屏上的图

病形同族（走查环 7 与环 8 同一格读数：``charts_on_screen=0``、``chart_srcs=[]``、
``artifact_total=0``）：文字里说图已经有了，屏上/台账里一枚可查回的件都没有。
本单只在**答复侧**钉一句真话，导出件那一格另立号；批准链在 ``app/api/v1/chat.py``（禁区），
本件一个字都不碰，也不替客户点批准。

钉四格，每条都可失败：
  1) 声称有图（图片 markdown 或"图表已生成"那族完成态短语）而本轮查不回 ``artifact_type == "chart"``
     的件 ⇒ 末尾追加一句真话；
  2) 本轮真有图表件 ⇒ 本腿闭嘴（句子上屏是对的，不许冤称客户没有图）；
  3) 🔴 反证牙 —— 光**提到**图、或明说"无法生成柱状图"的那一份答复 ⇒ 本腿闭嘴。走查那一轮
     客户看见的话就是这个形状，本腿若对它开口，就是把一句真话钉成第枚假话；
  4) 件型只认 ``app/agents/evidence.py::record_artifact`` 落的那一格，不拿 URL 字符串对盘
     （工具侧 embed 的是 ``content_url``、袋里记的是 ``download_url``，两枚天生不同串，
     按 URL 匹配必假红）。

全程离线：不生成任何真图（不落 static/、不调 matplotlib）、不打模型、不起容器。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes

QUESTION = "按月份统计报销金额，并画一张柱状图"

#: 工具侧真产物那一行的形状（``app/agents/tools.py::_generate_chart`` 交回的正文）。
CHART_LINE = "图表已生成: ![月度报销柱状图](/api/v1/artifacts/art-1/content.png)"

#: 走查环 7 客户真正看见的那一句（终答逐字，节选承重部分）。它通篇说的是"生不成图"，
#: 判据 3 的反证牙要的就是：本腿对这一份必须闭嘴。
REFUSAL_ANSWER = (
    "无法直接生成按月份统计的报销金额柱状图，因为：\n"
    "1. 文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件。"
)


def _state(legs: dict, artifacts: list[dict] | None) -> dict:
    """一轮的终态：legs = 各条腿交回的正文，artifacts = 本轮登记下来的件（可为空）。"""
    return {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": dict(legs),
        "agent_results": {
            "chart": {
                "worker": "chart",
                "status": "success",
                "answer": next(iter(legs.values()), ""),
                "artifacts": list(artifacts or []),
                "evidence": [],
            }
        },
    }


def _run(state: dict) -> dict:
    return nodes.synthesize(state)


# ==================== 声称有图而查不回件 ⇒ 钉一句真话 ====================


@pytest.mark.parametrize(
    "claim",
    [
        CHART_LINE,
        "图表已生成，请查看：![柱状图](/static/chart.png)",
        "月度合计已经算出，见下图。\n<img src=\"/api/v1/artifacts/art-2/content.png\">",
    ],
)
def test_a_chart_claim_without_any_registered_chart_gets_one_truth_sentence(claim) -> None:
    result = _run(_state({"chart": claim}, []))

    final = result["final_answer"]
    assert nodes.CHART_TRUTH_SENTENCE in final, final
    assert final.endswith(nodes.CHART_TRUTH_SENTENCE), "补写必须落在末尾，不许插进模型已经写的字"
    assert final.startswith(claim), "只许追加，不许改写"
    assert list(result["worker_results"]) == ["chart"], result["worker_results"]


def test_multi_leg_round_keeps_every_leg_and_writes_the_whole_table_back() -> None:
    """收端（``app/api/v1/chat.py::_select_final_answer``）是整张覆盖 worker_results 的，
    回写只带一条腿会把别的腿洗掉；追加只落最后那条有字的腿。"""
    legs = {"data": "月度合计 17100 元。", "chart": CHART_LINE}
    before = "\n\n".join(legs.values())

    result = _run(_state(legs, []))

    assert list(result["worker_results"]) == ["data", "chart"], result["worker_results"]
    assert result["worker_results"]["data"] == "月度合计 17100 元。", "别的腿被改了字"
    assert result["final_answer"].startswith(before), "已发帧必须是终答前缀"
    assert result["final_answer"] == "\n\n".join(
        [result["worker_results"][key] for key in ("data", "chart")]
    ), "终答与 worker_results 折出来的文字不一致"


def test_the_truth_sentence_says_nothing_about_failure_or_permission() -> None:
    """措辞红线：这一格的事实只有"没生成件"，说成"失败"或"没权限"都是替客户猜因由。"""
    for banned in ("失败", "错误", "权限", "无权", "抱歉", "无法访问"):
        assert banned not in nodes.CHART_TRUTH_SENTENCE, banned


# ==================== 判据 3 反证牙：有件、以及根本没声称 ====================


def test_a_registered_chart_artifact_keeps_the_leg_silent() -> None:
    artifacts = [
        {
            "artifact_id": "art-" + uuid4().hex[:8],
            "artifact_type": "chart",
            "download_url": "/api/v1/artifacts/art-1/download",
        }
    ]

    result = _run(_state({"chart": CHART_LINE}, artifacts))

    assert result["final_answer"] == CHART_LINE, result
    assert "worker_results" not in result, "一个字都没补，却回写了 worker_results"


def test_the_guard_matches_the_artifact_type_not_the_url() -> None:
    """袋里记的是 ``download_url``，正文 embed 的是 ``content_url`` —— 两枚天生不同串。

    按 URL 对盘的写法会在这枚用例上假红：正文里的 URL 一个字都不出现在登记行里，
    而件确实在册。判据只读物证那一格的真实现就是件型。
    """
    artifacts = [
        {
            "artifact_id": "art-1",
            "artifact_type": "chart",
            "download_url": "/api/v1/artifacts/art-1/download?token=abc",
        }
    ]

    result = _run(_state({"chart": CHART_LINE}, artifacts))

    assert nodes.CHART_TRUTH_SENTENCE not in result["final_answer"]


def test_a_refusal_to_draw_is_not_a_chart_claim() -> None:
    """走查那一轮的真话形状：它说的是"生不成"，本腿对它必须闭嘴。"""
    result = _run(_state({"doc": REFUSAL_ANSWER}, []))

    assert result["final_answer"].startswith(REFUSAL_ANSWER)
    assert nodes.CHART_TRUTH_SENTENCE not in result["final_answer"], result["final_answer"][-300:]


@pytest.mark.parametrize(
    "answer",
    [
        "建议用 Excel 选中两列后插入柱状图。",
        "本月报销合计 17100 元，明细见上表。",
        "如需趋势图可再提一轮出图请求。",
        "表格如下：月份 / 金额。",
    ],
)
def test_mentioning_a_chart_or_a_table_is_not_claiming_one_was_delivered(answer) -> None:
    result = _run(_state({"doc": answer}, []))

    assert nodes.CHART_TRUTH_SENTENCE not in result["final_answer"], result["final_answer"][-300:]
    assert "worker_results" not in result


def test_an_empty_round_produces_no_claim_and_no_appendage() -> None:
    """两条腿都空：本腿不许凭空长出一句"没有图"——那时连一个字都没交付，
    包装空正文是 R439 已经钉过的病，不归本单治。"""
    state = _state({"doc": ""}, [])
    state["final_answer"] = ""
    state["agent_results"] = {}

    result = _run(state)

    assert nodes.CHART_TRUTH_SENTENCE not in str(result.get("final_answer") or "")


# ==================== 判定口自己：什么算声称 ====================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CHART_LINE, True),
        ("![柱状图](/static/a.png)", True),
        ('<IMG SRC="chart.png">', True),
        # 边界：不提图/表/chart 的一枚 img 标签不算图表声称——知识库原文里也可能躺着一张
        # 图片，那一句「本轮没有生成图表文件」钉上去就是另一枚假话。
        ('<img src="/static/logo.png">', False),
        ("图表如下。", True),
        ("如图所示，报销金额逐月上升。", True),
        (REFUSAL_ANSWER, False),
        ("本月合计 17100 元。", False),
        ("", False),
        (None, False),
    ],
)
def test_claims_a_chart_recognises_completed_claims_only(text, expected) -> None:
    assert nodes._claims_a_chart(text) is expected, text


def test_chart_artifact_reader_ignores_legacy_bare_string_artifacts() -> None:
    """老形状里 artifacts 允许躺一枚裸字符串：带不出件型就判不了，判不了就当没这回事。
    宁可少钉一句，也不许把"读不出来"说成"客户没有图"。"""
    state = _state({"chart": CHART_LINE}, [])
    state["agent_results"]["chart"]["artifacts"] = ["/api/v1/artifacts/art-9/content.png"]

    assert nodes._chart_artifacts_in_state(state) == []
    assert nodes.CHART_TRUTH_SENTENCE in _run(state)["final_answer"]
