"""R401 · 甲/乙那 10 枚：锚词的出处必须是**从语料现算出来的**，而且新锚词必须还咬得住。

【本文件钉的四件事】
  1. 处置账铺得满：甲 ∪ 乙 ∪ 丙 == 审计文档 §2.1 记的那 29 枚（清单从文档原文现抠，不是抄常量）。
  2. 出处是派生的：每一枚甲/乙的 anchor_provenance 都要能拿 documents/*.txt 重算出一模一样的
     篇路径 / 原始行原文 / 归一化后 utf-8 字节区间。手抄一个字节位置都会在这里当场红。
  3. 新锚词仍咬得住：每枚附"模型答错最可能说的原话"喂进真判分器 app/quality/eval.py::_is_correct，
     必须**不命中**；同时金标答案自己必须命中（不然就是换了个词把题目判死）。
  4. 守恒与零改动：题源 105 行、行序、id、tier、category、requires_evidence、成对题字段全部
     与基点 69e0035 逐字段相等；documents/** 与基点比一个字节都没动（判据①）。

全程离线：只读题源、语料、审计文档，零模型、零网络、零连库、零起服务；写盘只发生在 tmp 影子副本。
"""
import collections
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_REV = "69e0035"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
AUDIT_DOC = REPO_ROOT / "docs" / "handoff" / "2026-09-19-eval-evidence-audit.md"
R401_SCRIPT = REPO_ROOT / "scripts" / "r401_anchor_provenance.py"
COVERAGE_SCRIPT = REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py"

MARKER_FIELD = "r401"
ANCHOR_FIELD = "anchor_provenance"
TIER_COUNTS = {"问答": 50, "分析": 35, "报告": 20}
CATEGORY_COUNTS = {
    "文档问答": 19, "多轮对话": 12, "口径冲突": 19, "Excel计算": 12, "主动洞察": 7,
    "图表生成": 4, "审批判断": 6, "跨部门权限": 6, "无证据问题": 4, "工具调用": 4,
    "报告生成": 12,
}
#: 判据②③里"改到了题面"的枚只有乙案那 3 枚，甲案一枚都不许动题面。
YI_IDS = {"approval-03", "approval-05", "data-12"}


@pytest.fixture(scope="module")
def r401():
    spec = importlib.util.spec_from_file_location("r401_anchor_provenance", R401_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cov(r401):
    """派生与复算用的是同一把尺：直接借 r401 件里那份 check_eval_evidence_coverage。"""
    return r401.cov


@pytest.fixture(scope="module")
def rows(r401):
    return r401.read_rows(REPO_ROOT)


@pytest.fixture(scope="module")
def corpus(r401):
    return r401.corpus_by_name(REPO_ROOT)


def _by_id(rows):
    return {str(row["id"]): row for row in rows}


def _fixture_lines(path):
    return [
        line
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _base_rows():
    """拿基点 69e0035 那份题源 blob（git 只读；没有 git 的用例自己 skip）。"""
    run = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", "{0}:{1}".format(BASE_REV, FIXTURE_105.relative_to(REPO_ROOT).as_posix())],
        capture_output=True,
    )
    if run.returncode != 0:
        return None
    return [json.loads(line) for line in run.stdout.decode("utf-8-sig").splitlines() if line.strip()]


def _audit_doc_orphan_ids():
    """审计文档 §2.1 那行「**29 个题号**」原文里现抠题号（判据②的对账基准）。"""
    doc = AUDIT_DOC.read_text(encoding="utf-8")
    line = next((l for l in doc.splitlines() if l.startswith("**29 个题号")), "")
    return re.findall(r"[a-z]+-[0-9]+", line)


# ---------------------------------------------------------------------------
# ① 处置账铺得满
# ---------------------------------------------------------------------------

def test_disposition_ledger_covers_exactly_the_29_in_the_audit_doc(r401, rows):
    doc_ids = _audit_doc_orphan_ids()
    assert len(doc_ids) == 29, "审计文档 §2.1 抠出来的题号不是 29 个，对手换了"
    assert sorted(r401.ORPHAN_IDS_29) == sorted(doc_ids), (
        "R401 的处置计划没有正好铺满当年那 29 枚：差集 "
        + "、".join(sorted(set(r401.ORPHAN_IDS_29) ^ set(doc_ids)))
    )
    marked = {str(row["id"]) for row in rows if MARKER_FIELD in row}
    assert marked == set(doc_ids), (
        "题源里带处置标记的集合与 29 枚不等：多标 "
        + "、".join(sorted(marked - set(doc_ids)))
        + "；漏标 "
        + "、".join(sorted(set(doc_ids) - marked))
    )
    counts = collections.Counter(
        row[MARKER_FIELD].get("disposition") for row in rows if MARKER_FIELD in row
    )
    assert dict(counts) == {"甲": 7, "乙": 3, "丙": 19}, counts
    assert set(r401.DETAILS) - YI_IDS == {
        row_id for row_id, plan in r401.DETAILS.items() if plan["disposition"] == "甲"
    }


def test_no_row_is_left_without_a_written_reason(r401, rows):
    for row in rows:
        marker = row.get(MARKER_FIELD)
        if marker is None:
            continue
        assert str(marker.get("reason", "")).strip(), "{0} 的处置没写理由".format(row["id"])
        assert str(marker.get("pool", "")).strip(), (
            "{0} 处置了却没交代待派池去向（丙案必须挂回待派池）".format(row["id"])
        )


# ---------------------------------------------------------------------------
# ② 出处是派生的，不是手抄的
# ---------------------------------------------------------------------------

def test_every_resolved_anchor_re_derives_to_the_recorded_address(r401, rows, corpus, cov):
    failures = []
    for row in rows:
        marker = row.get(MARKER_FIELD)
        if not marker or marker.get("disposition") == "丙":
            continue
        records = row.get(ANCHOR_FIELD)
        assert isinstance(records, list) and len(records) == len(row["must_contain"]), (
            "{0} 的 {1} 必须与 must_contain 等长：逐词条对账".format(row["id"], ANCHOR_FIELD)
        )
        for term, record in zip([str(t) for t in row["must_contain"]], records):
            assert record["path"].startswith("documents/") and record["path"].endswith(".txt"), (
                "{0} 锚词 {1!r} 的出处不在 documents/*.txt 里：{2}（判据①只认这 95 篇）".format(
                    row["id"], term, record["path"]
                )
            )
            fresh = r401.derive_record(
                corpus, term, record["file_name"], record["raw_line_number"]
            )
            if fresh != record:
                failures.append("{0} {1!r} 重算 != 记录：{2}".format(row["id"], term, (record, fresh)))
            text = corpus[record["file_name"]][1]
            encoded = cov.normalize(text).encode("utf-8")
            sliced = encoded[
                record["normalized_byte_start"] : record["normalized_byte_start"]
                + record["normalized_byte_length"]
            ].decode("utf-8")
            if sliced != cov.normalize(term):
                failures.append(
                    "{0} {1!r} 的字节区间 {2}+{3} 切出来是 {4!r}".format(
                        row["id"], term, record["normalized_byte_start"],
                        record["normalized_byte_length"], sliced,
                    )
                )
    assert not failures, "派生对账失败：\n" + "\n".join(failures)


def test_verify_module_reports_the_shipped_tree_clean(r401):
    assert r401.verify(REPO_ROOT) == [], "r401 件自己的对账没过，题源不可信"


def test_pointer_that_is_not_unique_in_its_line_is_refused(r401, corpus):
    """"禁手抄"的另一半：指针含糊就必须拒派生，不许"差不多那一行"蒙过去。"""
    with pytest.raises(r401.DerivationError, match="不唯一"):
        r401.derive_record(corpus, "同比", "2026年Q1经营分析报告.txt", 5)
    with pytest.raises(r401.DerivationError, match="命中 0 次"):
        r401.derive_record(corpus, "机密级", "差旅费报销细则_2026版.txt", 21)
    with pytest.raises(r401.DerivationError):
        r401.derive_record(corpus, "机密级", "没有这一篇.txt", 21)
    with pytest.raises(r401.DerivationError):
        r401.derive_record(corpus, "机密级", "企业管理制度手册.txt", 99999)


# ---------------------------------------------------------------------------
# ③ 新锚词仍然咬得住
# ---------------------------------------------------------------------------

def test_wrong_answer_samples_miss_the_real_judge(r401, rows):
    """判分器用的是 app/quality/eval.py 里那把真尺，本文件不复刻一份平行实现。"""
    from app.quality.eval import _is_correct

    by_id = _by_id(rows)
    assert set(r401.WRONG_ANSWER_SAMPLES) == set(r401.DETAILS), (
        "每一枚甲/乙都得附反证样本，一枚不许少"
    )
    for row_id, samples in r401.WRONG_ANSWER_SAMPLES.items():
        row = by_id[row_id]
        assert samples, "{0} 的反证样本是空的".format(row_id)
        assert _is_correct(row, {"answer": row["answer"]}) is True, (
            "{0} 连自己的金标都判不过，换了个把题目判死的锚词".format(row_id)
        )
        for sample in samples:
            assert _is_correct(row, {"answer": sample}) is False, (
                "{0} 的新锚词被错答 {1!r} 命中了：这一枚只是把缺口换了个形状".format(row_id, sample)
            )


def test_resolved_rows_still_satisfy_their_own_gold_answer(rows):
    for row in rows:
        if MARKER_FIELD not in row or row[MARKER_FIELD].get("disposition") == "丙":
            continue
        for term in row["must_contain"]:
            assert str(term) in row["answer"], "{0} 锚词 {1!r} 不在金标里".format(row["id"], term)


# ---------------------------------------------------------------------------
# ④ 守恒：桶数、category 分布、没动过的字段
# ---------------------------------------------------------------------------

def test_tier_and_category_buckets_are_conserved(rows):
    assert len(rows) == 105
    assert dict(collections.Counter(row["tier"] for row in rows)) == TIER_COUNTS
    assert dict(collections.Counter(row["category"] for row in rows)) == CATEGORY_COUNTS


def test_fields_that_should_not_move_are_byte_identical_to_the_base(r401, rows):
    base = _base_rows()
    if base is None:
        pytest.skip("基点 {0} 的题源 blob 读不出来（浅克隆/历史被改写）".format(BASE_REV))
    assert [str(row["id"]) for row in base] == [str(row["id"]) for row in rows], "行序或 id 变了"
    stable = ("tier", "category", "requires_evidence", "conflict_pair", "metric", "department", "id")
    for old, new in zip(base, rows):
        for field in stable:
            assert old.get(field) == new.get(field), "{0}.{1} 动了：判据②要求桶与 category 守恒".format(
                old["id"], field
            )
    changed = {str(new["id"]) for old, new in zip(base, rows) if any(
        old.get(f) != new.get(f) for f in ("question", "answer", "must_contain")
    )}
    assert changed == set(r401.DETAILS) , (
        "真正被改过题面/金标/锚词的枚与处置账不等：多改了 "
        + "、".join(sorted(changed - set(r401.DETAILS)))
        + "，少改了 "
        + "、".join(sorted(set(r401.DETAILS) - changed))
    )


def test_only_the_three_yi_rows_have_their_question_text_changed(r401, rows):
    base = _base_rows()
    if base is None:
        pytest.skip("基点 {0} 的题源 blob 读不出来".format(BASE_REV))
    by_id = {str(row["id"]): row for row in base}
    changed = set()
    for row in rows:
        old = by_id[str(row["id"])]
        if MARKER_FIELD in row and str(row["question"]) != str(old["question"]):
            changed.add(str(row["id"]))
    assert changed == YI_IDS, "动到题面的必须是且只是乙案那 3 枚：" + "、".join(sorted(changed))


def test_documents_tree_is_byte_identical_to_the_base_commit():
    """判据①：语料零变化。用 git 拿基点与工作树比，不靠人保证"我没动过"。"""
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", BASE_REV, "--", "documents/"],
        capture_output=True,
    )
    if listed.returncode != 0:
        pytest.skip("基点 {0} 不可比较（浅克隆/历史被改写）".format(BASE_REV))
    touched = [line for line in listed.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    assert not touched, "documents/** 被动过了：" + "、".join(touched)
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "documents/*.txt"], capture_output=True
    )
    names = [line for line in tracked.stdout.decode("utf-8").splitlines() if line.strip()]
    assert len(names) == 95, "跟踪中的 txt 不是 95 篇：{0}".format(len(names))


def test_the_coverage_tool_still_refuses_to_read_the_disposition_marker(r401):
    """判据②红线：不许给覆盖度工具加排除名单、也不许让它读我的处置标记，否则缺口变成自证。

    判定函数与反证刀 K7 共用 `scripts/r401_anchor_provenance.py:audit_tool_is_marker_free`，
    所以这把刀能红就证明这条绿不是靠"断言写得松"混过去的。
    """
    source = COVERAGE_SCRIPT.read_text(encoding="utf-8")
    assert r401.audit_tool_is_marker_free(source) == []
