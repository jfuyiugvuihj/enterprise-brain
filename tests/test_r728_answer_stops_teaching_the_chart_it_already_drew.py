"""R728 · 图已经画出来了，正文不许再教客户怎么画（附 R727：同一句提示只说一遍）

病形现取（10-07 16:36 官方九环之后，业主拿同一枚问法在屏上读到的那一份正文）：
客户问「按月份统计报销金额，并画一张柱状图」，屏上「本轮生成的图表」那张柱状图是好的
（一根色、标题写得出维度×度量），可它下面那段正文里还躺着一整段 matplotlib 配方，
颜色那一行写的正是 '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'
——业主先前纠的「六道彩虹」在正文里活着，客户看了只会更懵：到底图有了没有？
同一段末尾还重复出现两遍「本轮带着数据文件：报销明细表.csv（144 行 × 9 列）…」，
那是批准续跑那一轮把补写腿又走了一遍、上一遍补的那句已经躺在正文里。

钉四格，每条都可失败：
  1) 本轮真登记过图表件 ⇒ 点名绘图库的围栏代码块必须从正文里摘掉，其余文字一个字不动；
  2) 🔴 反证牙 —— 本轮没出图 ⇒ 那段配方必须留着。「怎么画」那时是客户唯一能拿走的回答；
  3) 🔴 反证牙 —— 出图的轮次里一段非绘图的代码（SQL）不许被顺手摘掉；
  4) 数据真话那句在一轮里只许出现一次（补写幂等），且不许牵连别的腿。

全程离线：不起容器、不打模型、不落真图，只喂 synthesize 一轮的终态。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.agents import nodes

QUESTION = "按月份统计报销金额，并画一张柱状图"
TABLE = "报销明细表.csv"

#: 走查里 Doc 腿那句把客户推去自己导出的话（承重那一句逐字取自环 7 正文）。
DOC_BLAME = (
    "根据现有文档，无法直接生成按月份统计的报销金额柱状图，因为：\n"
    "1. 文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件。"
)

#: 业主屏上那一段的真形状（10-07 17:0x 逐字）：结论 + 一节"可视化建议" + 引导句 + 围栏配方。
#: 头尾那两句人话是判据 1 的反证：摘的只有配方那一节，别处的字一个不许少。
PLOT_RECIPE = (
    "以下是按月份统计的报销金额汇总。\n"
    "\n"
    "半年总计 466,860 元，平均每月约 77,810 元。\n"
    "\n"
    "### 📉 柱状图可视化建议\n"
    "\n"
    "如需绘制柱状图，可使用以下Python代码：\n"
    "\n"
    "```python\n"
    "import matplotlib.pyplot as plt\n"
    "months = ['2026-01', '2026-02', '2026-03']\n"
    "amounts = [67770, 52710, 82830]\n"
    "plt.bar(months, amounts, color=['#3498db', '#e74c3c', '#2ecc71'])\n"
    "plt.title('按月报销金额统计')\n"
    "plt.show()\n"
    "```\n"
    "\n"
    "如需按部门再切一刀，请告知。"
)

SQL_BLOCK = (
    "口径落在这样一句查询上：\n"
    "\n"
    "```sql\n"
    "SELECT month, sum(amount) FROM reimbursements GROUP BY month;\n"
    "```\n"
)

CHART_ARTIFACT = {
    "artifact_id": "art-r728-chart",
    "artifact_type": "chart",
    "download_url": "/api/v1/artifacts/art-r728-chart/download",
}


def _dataset_evidence(rows: int = 144) -> list[dict]:
    """``app/agents/tools.py::_record_dataset_evidence`` 在装箱之后记进袋的那一格的形状。"""
    return [
        {
            "source_type": "dataset",
            "source_name": TABLE,
            "locator": {"filename": TABLE},
            "metadata": {"row_count": rows, "columns": ["单据号", "金额", "发生月份"]},
        }
    ]


def _state(legs: dict, artifacts: list[dict], evidence: list[dict]) -> dict:
    return {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": dict(legs),
        "agent_results": {
            "chart": {
                "worker": "chart",
                "status": "success",
                "answer": next(iter(legs.values()), ""),
                "artifacts": list(artifacts),
                "evidence": list(evidence),
            }
        },
    }


# ==================== 判据 1 · 出了图就不许再递配方 ====================


def test_a_round_that_drew_the_chart_does_not_also_teach_the_customer_to_draw_it() -> None:
    legs = {"doc": DOC_BLAME, "data": PLOT_RECIPE}

    result = nodes.synthesize(_state(legs, [CHART_ARTIFACT], []))

    final = result["final_answer"]
    assert "plt.bar" not in final, final
    assert "matplotlib" not in final, final
    assert "#e74c3c" not in final, "那串彩虹色正是业主纠的东西，不许还留在正文里"
    assert "柱状图可视化建议" not in final, "只摘围栏会留下一节空标题，比留着代码更懵"
    assert "如需绘制柱状图" not in final, final
    assert "以下是按月份统计的报销金额汇总。" in final, "摘的只有那一节，别处的字一个不许少"
    assert "半年总计 466,860 元" in final, final
    assert "如需按部门再切一刀" in final, final
    assert "```" not in final, final
    assert list(result["worker_results"]) == ["doc", "data"], "回写只带一条腿会把别的腿洗掉"


def test_the_chart_still_lands_on_screen_after_the_recipe_is_dropped() -> None:
    """摘配方与贴图打的是两格：图那一行 markdown 必须还在（R725 的活儿不能被本腿顺手洗掉）。"""
    result = nodes.synthesize(_state({"data": PLOT_RECIPE}, [CHART_ARTIFACT], []))

    final = result["final_answer"]
    assert "art-r728-chart" in final, final
    assert final.count("plt.bar") == 0


# ==================== 判据 2/3 · 反证牙 ====================


def test_the_recipe_stays_when_no_chart_landed_this_round() -> None:
    """没出图的轮次里「怎么画」就是答案本身，摘它是替客户把回答撕了。"""
    result = nodes.synthesize(_state({"data": PLOT_RECIPE}, [], []))

    final = result["final_answer"]
    assert "plt.bar" in final, final
    assert "```python" in final, final
    assert "柱状图可视化建议" in final, "没出图的轮次连标题一起留着，那一节本来就是答案"
    assert "worker_results" not in result, "一个字都没动，却回写了 worker_results"


def test_a_charted_round_keeps_a_non_plotting_code_block() -> None:
    """本腿只认点名绘图库的那几段；一段 SQL 不是它该管的东西。"""
    result = nodes.synthesize(_state({"data": SQL_BLOCK}, [CHART_ARTIFACT], []))

    final = result["final_answer"]
    assert "SELECT month" in final, final
    assert "```sql" in final, final


# ==================== R727 · 同一句真话只说一遍 ====================


def test_the_dataset_truth_sentence_is_spoken_once_even_when_the_round_runs_again() -> None:
    """批准续跑那一轮会把补写腿再走一遍：上一遍补的那句已躺在正文里，不许再补第二遍。"""
    block = nodes.DATASET_TRUTH_SENTENCE.format(names=f"{TABLE}（144 行 × 3 列）")
    legs = {"doc": DOC_BLAME, "data": "月度合计 17100 元。\n\n" + block}

    result = nodes.synthesize(_state(legs, [], _dataset_evidence()))

    final = result["final_answer"]
    assert final.count(block) == 1, final[-400:]
    assert final.endswith(block), "补写落点仍在末尾，不许插进客户已经读过的字里"


def test_the_dataset_truth_sentence_is_still_added_when_it_was_never_spoken() -> None:
    """反证牙的另一侧：幂等不许把第一次的那一句也挡掉。"""
    block = nodes.DATASET_TRUTH_SENTENCE.format(names=f"{TABLE}（144 行 × 3 列）")
    legs = {"doc": DOC_BLAME, "data": "月度合计 17100 元。"}

    result = nodes.synthesize(_state(legs, [], _dataset_evidence()))

    final = result["final_answer"]
    assert final.count(block) == 1, final[-400:]
