"""R595 常驻钉（一）：A① 的分群必须由夹具 ``category`` 现派生，规则一改就必须红。

钉的四件事（判据②）：
① 三份名单逐字等于计划书 ``2026-09-17-perf-architecture-plan.md:352``（09-20 裁定·R440 :383 延续）那几族；
② 拿在册题集复现板上历史那两枚数：``category`` 维问答类 n=64／分析·报告类 n=35／未入群（审批判断）6，加总 105；
   ``tier`` 维给的是 50／35／20 ⇒ 板上 :3993「问答 64／分析 35／报告 20」那句加总 119 是**两维并排印**，不是同一个母集
   （跟进单 :4176 已判「不同母集，谁都不许抄谁」）——这一格从此由钉子守着，不再靠手推；
③ 夹具里长出名单之外的 category ⇒ 点名并 rc=RC_CALIBER，不自创群、不静默并入；
④ n 必带（母集／有跨度／进 p95 三枚都在纸面上），p95 判据口径 = 最近秩，且与在册 ``build_latency_cell`` 同一枚数。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r595_latency_readout", REPO_ROOT / "scripts" / "r595_latency_readout.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

BANK = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 计划书 :352 字面那份名单（改动它 = 改口径 = 本钉必红；要改先改纸面）。
BOOK_QA = ("文档问答", "多轮对话", "口径冲突", "无证据问题", "工具调用", "跨部门权限")
BOOK_ANALYSIS_REPORT = ("Excel计算", "报告生成", "图表生成", "主动洞察")
BOOK_UNGROUPED = ("审批判断",)


def write_jsonl(path: Path, rows) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sample_rows():
    """最小三本件：六枚，覆盖两群 + 未入群 + 一枚没被 :352 覆盖的族（由各用例自己挑）。"""
    fixture = [
        {"id": "q-01", "tier": "问答", "category": "文档问答", "question": "住宿费？"},
        {"id": "q-02", "tier": "问答", "category": "口径冲突", "question": "两份口径？"},
        {"id": "q-03", "tier": "问答", "category": "审批判断", "question": "能批吗？"},
        {"id": "a-01", "tier": "分析", "category": "Excel计算", "question": "算总额"},
        {"id": "r-01", "tier": "报告", "category": "报告生成", "question": "写年报"},
        {"id": "r-02", "tier": "报告", "category": "主动洞察", "question": "看趋势"},
    ]
    answers = [{"id": row["id"], "answer": "略", "evidence": [], "latency_ms": 1.0} for row in fixture]
    sidecar = [{"id": row["id"], "kind": "ok", "attempt": 1, "wall_ms": 1000.0 + index * 500.0}
               for index, row in enumerate(fixture)]
    return fixture, answers, sidecar


def make_case(tmp_path, fixture=None, answers=None, sidecar=None, transport_source=None, label="t"):
    fixture = fixture if fixture is not None else sample_rows()[0]
    answers = answers if answers is not None else sample_rows()[1]
    sidecar = sidecar if sidecar is not None else sample_rows()[2]
    paths = {}
    for name, rows in (("fixture", fixture), ("answers", answers), ("sidecar", sidecar)):
        path = Path(tmp_path) / ("%s-%s.jsonl" % (name, label))
        write_jsonl(path, rows)
        paths[name] = path
    kwargs = {"transport_source": Path(transport_source) if transport_source else mod.DEFAULT_TRANSPORT_SOURCE,
              "label": label}
    return paths, mod.collect(paths["answers"], paths["fixture"], paths["sidecar"], **kwargs)


def test_membership_lists_are_the_book_verbatim():
    assert mod.QA_CATEGORIES == BOOK_QA
    assert mod.ANALYSIS_REPORT_CATEGORIES == BOOK_ANALYSIS_REPORT
    assert mod.UNGROUPED_CATEGORIES == BOOK_UNGROUPED
    assert mod.GROUPS == (mod.GROUP_QA, mod.GROUP_ANALYSIS_REPORT, mod.GROUP_ALL)


def test_derivation_moves_a_row_when_the_rule_moves(tmp_path):
    """口径改一个字就红：把「主动洞察」从分析·报告类挪到问答类，成员数必须跟着变。"""
    _, data = make_case(tmp_path)
    assert sorted(data["derived"]["groups"][mod.GROUP_QA]) == ["q-01", "q-02"]
    assert sorted(data["derived"]["groups"][mod.GROUP_ANALYSIS_REPORT]) == ["a-01", "r-01", "r-02"]
    assert data["derived"]["ungrouped"] == ["q-03"]

    moved = mod.QA_CATEGORIES + ("主动洞察",)
    try:
        mod.QA_CATEGORIES = moved
        mod.CATEGORY_TO_GROUP["主动洞察"] = mod.GROUP_QA
        _, after = make_case(tmp_path, label="moved")
        assert sorted(after["derived"]["groups"][mod.GROUP_QA]) == ["q-01", "q-02", "r-02"]
        assert sorted(after["derived"]["groups"][mod.GROUP_ANALYSIS_REPORT]) == ["a-01", "r-01"]
        assert after["cells"][mod.GROUP_QA]["n"] == 3
    finally:
        mod.QA_CATEGORIES = BOOK_QA
        mod.CATEGORY_TO_GROUP["主动洞察"] = mod.GROUP_ANALYSIS_REPORT


def test_bank_reproduces_the_two_published_partitions(tmp_path):
    """板上那两枚历史 n：category 维 64/35/6，tier 维 50/35/20，两维各自加总都是 105。"""
    rows = [json.loads(line) for line in BANK.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    fixture, _collisions = mod.fold_latest(rows, "fixture")
    derived = mod.derive_groups(fixture)
    counts = {name: len(derived["groups"][name]) for name in mod.GROUPS}
    assert counts == {mod.GROUP_QA: 64, mod.GROUP_ANALYSIS_REPORT: 35, mod.GROUP_ALL: 105}
    assert len(derived["ungrouped"]) == 6
    assert all(str(fixture[i]["category"]) == "审批判断" for i in derived["ungrouped"])
    assert sorted(derived["ungrouped"])[0] == "approval-01"
    # tier 维是另一个母集（看板 :3993 把两维并排印在同一句话里 ⇒ 119 ≠ 105，这一格从此有钉子）
    tiers = {name: len(ids) for name, ids in derived["tiers"].items()}
    assert tiers == {"问答": 50, "分析": 35, "报告": 20}
    assert sum(tiers.values()) == 105 and counts[mod.GROUP_QA] + counts[mod.GROUP_ANALYSIS_REPORT] != 105
    assert not derived["uncovered"]


def test_unknown_category_is_named_and_refuses_to_invent(tmp_path):
    fixture = sample_rows()[0] + [{"id": "x-01", "tier": "问答", "category": "新的一族", "question": "?"}]
    answers = [{"id": row["id"], "answer": "略", "evidence": [], "latency_ms": 1.0} for row in fixture]
    sidecar = [{"id": row["id"], "kind": "ok", "attempt": 1, "wall_ms": 1000.0} for row in fixture]
    paths, data = make_case(tmp_path, fixture=fixture, answers=answers, sidecar=sidecar, label="unc")
    assert data["derived"]["uncovered"] == {"新的一族": ["x-01"]}
    assert "x-01" not in data["derived"]["groups"][mod.GROUP_QA]
    assert "x-01" in data["derived"]["groups"][mod.GROUP_ALL]      # 整表照旧数它，不丢题
    rc = mod.main(["--answers", str(paths["answers"]), "--fixture", str(paths["fixture"]),
                   "--sidecar", str(paths["sidecar"]), "--label", "unc"])
    assert rc == mod.RC_CALIBER


def test_n_is_always_carried_even_when_the_group_is_empty(tmp_path):
    """判据① 那句「n 必带」：空群也要印 n，不许变成「无量」两个字混过去。"""
    fixture = [{"id": "r-01", "tier": "报告", "category": "报告生成", "question": "写年报"}]
    answers = [{"id": "r-01", "answer": "略", "evidence": [], "latency_ms": 1.0}]
    sidecar = [{"id": "r-01", "kind": "ok", "attempt": 1, "wall_ms": 1234.5}]
    paths, data = make_case(tmp_path, fixture=fixture, answers=answers, sidecar=sidecar, label="one")
    assert data["cells"][mod.GROUP_QA]["n"] == 0
    assert data["cells"][mod.GROUP_QA]["n_used"] == 0
    lines = "\n".join(mod.render(data))
    assert "问答类：n=0（母集）／0（有诚实跨度）／0（进 p95）" in lines
    assert "分析·报告类：n=1（母集）／1（有诚实跨度）／1（进 p95）" in lines
    assert rc_ok(data, paths)


def rc_ok(data, paths) -> int:
    return mod.main(["--answers", str(paths["answers"]), "--fixture", str(paths["fixture"]),
                     "--sidecar", str(paths["sidecar"])]) == mod.RC_OK


def test_p95_caliber_is_nearest_rank_and_matches_the_inbook_ruler(tmp_path):
    """判据口径 = 最近秩（app/quality/eval.py:628 那一把），线性插值只作对照并同时印出。"""
    spans = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert mod.nearest_rank(spans, 0.95) == 100.0        # ceil(10*0.95)=10 → 第 10 枚
    assert mod.linear_rank(spans, 0.95) == pytest.approx(95.5)   # 两把尺在这里就不同数
    assert mod.nearest_rank(spans, 0.5) == 50.0
    from app.quality.eval import build_latency_cell
    assert build_latency_cell(spans)["p95"] == mod.nearest_rank(spans, 0.95)
    assert mod.nearest_rank([], 0.95) is None and mod.linear_rank([], 0.5) is None

    _, data = make_case(tmp_path)
    for name in mod.GROUPS:
        assert data["scale"][name]["agree"] is True, data["scale"][name]
        assert data["scale"][name]["inbook_p95"] == data["cells"][name]["p95_rank"]

def test_an_empty_group_never_claims_the_two_rulers_agree(tmp_path):
    """空群那一格：在册那把尺对空集交回 0、本件交回 None ⇒ 不许拿「相等」冒充「同数」（总控 12:3x 点出的病）。"""
    fixture = [{"id": "r-01", "tier": "报告", "category": "报告生成", "question": "写年报"}]
    answers = [{"id": "r-01", "answer": "略", "evidence": [], "latency_ms": 1.0}]
    sidecar = [{"id": "r-01", "kind": "ok", "attempt": 1, "wall_ms": 1234.5}]
    paths, data = make_case(tmp_path, fixture=fixture, answers=answers, sidecar=sidecar, label="emp")
    check = data["scale"][mod.GROUP_QA]
    assert check["empty"] is True, check
    assert check["agree"] is False, "空群被印成两把尺同数 = 假绿：%s" % check
    assert check["local_p95"] is None and check["inbook_p95"] == 0, check
    lines = "\n".join(mod.render(data))
    qa_line = [x for x in lines.splitlines() if x.startswith("- 问答类：这一格空群")]
    assert len(qa_line) == 1, lines
    assert "不拿「相等」冒充「同数」" in qa_line[0]
    assert "agree=True" not in qa_line[0]
    filled = data["scale"][mod.GROUP_ANALYSIS_REPORT]
    assert filled["empty"] is False and filled["agree"] is True, filled


def test_the_two_dimensions_are_not_the_same_partition(tmp_path):
    """看板 :3993 那句「问答 64／分析 35／报告 20」= 119 ≠ 105 的账，闭合到枚：21 枚被两维各数一遍、7 枚谁都没数。

    这一格不许靠人嘴解释（R440 在跟进单 :4176 已判「不同母集，谁都不许抄谁」），钉子把 64／55／98／21／7／14 六个数全钉住。
    """
    rows = [json.loads(line) for line in BANK.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    qa = set(BOOK_QA)
    by_category = {row["id"] for row in rows if row["category"] in qa}
    by_tier = {row["id"] for row in rows if row["tier"] in ("分析", "报告")}
    every_id = {row["id"] for row in rows}
    assert (len(by_category), len(by_tier), len(every_id)) == (64, 55, 105)
    assert len(by_category | by_tier) == 98
    assert len(by_category & by_tier) == 21          # 两维各数一遍的那 21 枚
    assert sorted(every_id - by_category - by_tier) == [   # 谁都没数的 7 枚
        "approval-01", "approval-02", "approval-03", "approval-04", "approval-05",
        "approval-06", "chart-03"]
    assert 64 + 35 + 20 - 105 == 14 == 21 - 7
