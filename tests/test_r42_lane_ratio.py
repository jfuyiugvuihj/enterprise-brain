"""R42 判据③（已按总控 09-18 裁定降级）：占比只报告，不判红。

裁定原文：计划书 §21 的"③ 问答档占比 ≥60%（对齐 70:25:5）"里，70:25:5 说的是
**生产流量形状**，不是这份 fixture 的形状；本评测集自带标注是
问答 50 / 分析 35 / 报告 20 = 47.6% : 33.3% : 19.0%，一个"复刻标注"的判别器
最多 47.6%，③ 在这 105 条题面上永远红。⇒ 成本占比门移交 R51 用真机分段观测回读，
本文件只留：① 分母钉死，② 三档都非空，③ 精度/召回两道反灌水门（水位不许降），
④ 一条把实测占比与标注占比**并排打印**的报告用例。
真正的硬门换成了判据⑤：tests/test_r42_numeric_questions.py。

纯离线判别：只拿 tests/fixtures/business_evaluation_100.jsonl 的 105 条题面喂给
app/agents/nodes.py::classify_route 的规则判别器，不连模型、不连库、不起服务。
fixture 只读，一条都不许改：用例先用三条结构断言把"还是那 105 条"钉住。

判别器是 R30 档位形状的使用方，不是它的修改方：输出的 lane 决定"走哪条道"，
tier 决定"用哪个档"，全部由规则给出，判别路径上零模型调用（判据①在
tests/test_r42_zero_model_calls.py）。
"""
import json
from collections import Counter
from pathlib import Path

from app.agents.nodes import (
    LANE_ANALYSIS,
    LANE_QA,
    LANE_REPORT,
    classify_route,
)

FIXTURE = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"

#: fixture 自己标注的档位（R36 的评测口径），用来核对判别器没有把比例刷成"全快道"。
LABEL_TO_LANE = {"问答": LANE_QA, "分析": LANE_ANALYSIS, "报告": LANE_REPORT}

#: 反灌水门：问答档里至少 7 成是 fixture 标注的问答题，否则"占比"就是把所有题塞进快道刷出来的。
QA_PRECISION_FLOOR = 0.70
#: 反灌水门二：fixture 标注为问答的题至少 9 成要落在快道，否则快道判别漏得太多。
QA_RECALL_FLOOR = 0.90


def _rows():
    lines = FIXTURE.read_text(encoding="utf-8-sig").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _distribution():
    rows = _rows()
    lanes = Counter(classify_route(row["question"]).lane for row in rows)
    total = len(rows)
    return rows, lanes, total


def test_fixture_is_still_the_105_question_set():
    """占比判据的分母只有在这 105 条上才成立，题面被改动时必须先红在这里。"""
    rows = _rows()
    assert len(rows) == 105, f"评测集题面数量已变：{len(rows)}"
    assert len({row["id"] for row in rows}) == 105, "题面 id 出现重复"
    assert all(str(row.get("question") or "").strip() for row in rows), "存在空题面"


def test_every_lane_is_populated():
    """三档都不能为空：为空说明判别器退化成一刀切，占比数字就没有意义。"""
    _, lanes, total = _distribution()
    assert total == 105
    for lane in (LANE_QA, LANE_ANALYSIS, LANE_REPORT):
        assert lanes[lane] > 0, f"{lane} 档一条都没命中，判别器已退化"


def test_question_lane_is_not_won_by_dumping_hard_questions_into_it():
    """问答档的精度门：快道里必须主要是 fixture 标注的问答题。"""
    rows, _, _ = _distribution()
    fast = [row for row in rows if classify_route(row["question"]).lane == LANE_QA]
    truly_fast = [row for row in fast if row["tier"] == "问答"]
    precision = len(truly_fast) / len(fast)
    wrong = [f"{row['id']}({row['tier']})" for row in fast if row["tier"] != "问答"]
    assert precision >= QA_PRECISION_FLOOR, (
        f"问答档精度 {precision:.2%} 低于门槛 {QA_PRECISION_FLOOR:.0%}，快道吞掉了重活：{wrong}"
    )


def test_question_lane_does_not_miss_the_light_questions():
    """问答档的召回门：fixture 标注为问答的题几乎都该落在快道。"""
    rows = _rows()
    labelled = [row for row in rows if row["tier"] == "问答"]
    in_fast = [row for row in labelled if classify_route(row["question"]).lane == LANE_QA]
    recall = len(in_fast) / len(labelled)
    missed = [f"{row['id']}" for row in labelled if row not in in_fast]
    assert recall >= QA_RECALL_FLOOR, (
        f"快道漏掉 {len(missed)} 条标注问答题，召回 {recall:.2%} 低于门槛 {QA_RECALL_FLOOR:.0%}：{missed}"
    )


def test_report_measured_share_beside_labelled_share():
    """判据③降级后的报告用例：实测占比与 fixture 标注占比必须并排打出来。

    这条不断言比例（比例红不红由 R51 的真机分段观测说了算），但**必须打印**，
    且必须一次打印两个口径——只报判别器的占比、不报标注的占比，就是拿
    47.6% 的评测集冒充 70:25:5 的生产流量形状。
    """
    rows, lanes, total = _distribution()
    labelled = Counter(row["tier"] for row in rows)
    mismatches = [
        row["id"]
        for row in rows
        if LABEL_TO_LANE[row["tier"]] != classify_route(row["question"]).lane
    ]
    print(
        "[R42-③报告] n={n} | 判别器：问答档={qa}({qa_share:.2%}) 分析档={an} 报告档={rp} "
        "| fixture标注：问答={lq}({lq_share:.2%}) 分析={la} 报告={lr} "
        "| 不一致={mm}条".format(
            n=total,
            qa=lanes[LANE_QA],
            qa_share=lanes[LANE_QA] / total,
            an=lanes[LANE_ANALYSIS],
            rp=lanes[LANE_REPORT],
            lq=labelled["问答"],
            lq_share=labelled["问答"] / total,
            la=labelled["分析"],
            lr=labelled["报告"],
            mm=len(mismatches),
        )
    )
    assert total == 105
    assert lanes[LANE_QA] + lanes[LANE_ANALYSIS] + lanes[LANE_REPORT] == total
    assert labelled["问答"] == 50 and labelled["分析"] == 35 and labelled["报告"] == 20, (
        f"评测集标注形状已变：{dict(labelled)}，两个占比不再同源可比"
    )

    # ⑥：判据⑤落盘后的完整混淆矩阵与快道精度/召回，一并打印（只报不判红，
    # 判红由上面两道门各自负责）。
    matrix = Counter((row["tier"], classify_route(row["question"]).lane) for row in rows)
    fast = [row for row in rows if classify_route(row["question"]).lane == LANE_QA]
    light = [row for row in rows if row["tier"] == "问答"]
    precision = sum(1 for row in fast if row["tier"] == "问答") / len(fast)
    recall = sum(1 for row in light if classify_route(row["question"]).lane == LANE_QA) / len(light)
    print("[R42-⑥矩阵] 标注→判别 " + " ".join(f"{label}/{lane}={matrix[(label, lane)]}" for label, lane in sorted(matrix)))
    print(
        "[R42-⑥水位] 快道精度={p:.2%}（门槛 {pf:.0%}） 快道召回={r:.2%}（门槛 {rf:.0%}）".format(
            p=precision, pf=QA_PRECISION_FLOOR, r=recall, rf=QA_RECALL_FLOOR
        )
    )
