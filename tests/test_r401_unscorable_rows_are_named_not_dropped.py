"""R401 · 丙案那 19 枚：题目保留、锚词不动、从 correctness 分母里**显式点名**扣除。

【本文件钉的三件事】
  1. 丙案不是"删题 / 置空 must_contain / 给工具加排除名单"这三条捷径的别名：
     105 行还是 105 行，锚词一个字节没动，覆盖度件也读不到我的处置标记。
  2. 扣的是**分母**，不是账：correctness 分母 = 105 - 19 = 86，19 枚逐枚带理由与待派池去向；
     evidence_coverage 与 total 仍按 105 行走（题还在集里，只是今天不判它对错）。
  3. 判据③那一节（unsupported-01..04 考的是"不编"）落地形态：能用语料具名码的那一枚
     （unsupported-03，未登记指标）换成登记表§〇.4 规定的「无口径登记」——**判据变更**：
     从"像人话的拒答"升级成"必须给出登记表规定的具名码"，不是把词换松；
     其余三枚今天不可考，判丙并点名。R129 提过的「没有找到」那一类本单**没有采用**，
     这条由下面的"松弛词零出现"钉守着。

🔴 未接线要说在前面：判分器在 app/quality/eval.py（本单写域外），它算的 answer_correctness
   仍按 105 分母出。本件给出的 86 是**账**与**可跑的子集夹具**，接线要改 app/**，请总控裁定。
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
REGISTRY_DOC = REPO_ROOT / "documents" / "制度与口径登记表.txt"
R401_SCRIPT = REPO_ROOT / "scripts" / "r401_anchor_provenance.py"

MARKER_FIELD = "r401"
UNSCORABLE = "丙"
RESOLVED = ("甲", "乙")
#: R129 §3/T2 里"拿判分变松换分"的那几个词：本单一个都不许进 must_contain。
RELAXED_REFUSAL_WORDS = ("没有找到", "无法回答", "找不到", "未找到")
REFUSAL_ROWS = (
    "unsupported-01", "unsupported-02", "unsupported-03", "unsupported-04",
)


@pytest.fixture(scope="module")
def r401():
    spec = importlib.util.spec_from_file_location("r401_anchor_provenance_t2", R401_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rows(r401):
    return r401.read_rows(REPO_ROOT)


def _markers(rows):
    return {
        str(row["id"]): row[MARKER_FIELD]
        for row in rows
        if isinstance(row.get(MARKER_FIELD), dict)
    }


def _base_rows():
    run = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show",
         "{0}:{1}".format(BASE_REV, FIXTURE_105.relative_to(REPO_ROOT).as_posix())],
        capture_output=True,
    )
    if run.returncode != 0:
        return None
    return [json.loads(line) for line in run.stdout.decode("utf-8-sig").splitlines() if line.strip()]


def _registered_refusal_code():
    """从登记表§〇.4 原文里**现抠**具名码，不在测试里抄一份字面。"""
    text = REGISTRY_DOC.read_text(encoding="utf-8")
    line = next((l for l in text.splitlines() if "未登记的指标被问到" in l), "")
    assert line, "登记表§〇.4 那条原文不在了，具名码无从派生"
    quoted = re.findall("(?:{0}|{1}|{2})(.+?)(?:{0}|{1}|{2})".format(chr(34), "“", "”"), line)
    assert quoted, "登记表§〇.4 里抠不出被引号包住的具名码"
    return quoted[0], line


# ---------------------------------------------------------------------------
# ① 丙案 = 点名扣除，不是三条捷径里的任何一条
# ---------------------------------------------------------------------------

def test_unscorable_rows_are_present_named_and_untouched(r401, rows):
    markers = _markers(rows)
    unscorable = sorted(
        row_id for row_id, marker in markers.items() if marker.get("disposition") == UNSCORABLE
    )
    assert len(unscorable) == 19
    assert unscorable == sorted(r401.UNSCORABLE)
    base = _base_rows()
    by_id = {str(row["id"]): row for row in rows}
    for row_id in unscorable:
        row = by_id[row_id]
        marker = row[MARKER_FIELD]
        assert str(marker.get("reason", "")).strip(), row_id
        assert "待派池" in str(marker.get("pool", "")), "{0} 判丙没挂回待派池".format(row_id)
        assert marker.get("missing_term"), "{0} 没记今天仍缺的那个词".format(row_id)
        assert str(marker["missing_term"]) in [str(t) for t in row["must_contain"]]
        assert "pre" not in marker, "{0} 判丙却留了改前值：丙案不动题面".format(row_id)
        assert "anchor_provenance" not in row, "{0} 判丙却有派生出处：丙案不换锚词".format(row_id)
        if base is not None:
            old = next(item for item in base if str(item["id"]) == row_id)
            for field in ("question", "answer", "must_contain", "tier", "category", "requires_evidence"):
                assert row.get(field) == old.get(field), (
                    "丙案的 {0}.{1} 被动过了：判丙只允许点名扣除".format(row_id, field)
                )


def test_nothing_was_dropped_emptied_or_excluded(rows, r401):
    assert len(rows) == 105
    assert len({str(row["id"]) for row in rows}) == 105
    for row in rows:
        assert isinstance(row["must_contain"], list) and row["must_contain"], (
            "{0} 的 must_contain 被置空了：判据②明令禁止".format(row["id"])
        )
        for term in row["must_contain"]:
            assert str(term).strip(), "空白锚词等于没锚词"
    # 覆盖度件的规模闸还在：105/121 与 95 篇，任一被绕过都出不了数
    assert r401.cov.EXPECTED_FIXTURE_ROWS == 105
    assert r401.cov.EXPECTED_TERM_TOTAL == 121
    assert r401.cov.EXPECTED_CORPUS_TXT_COUNT == 95
    assert sum(len(row["must_contain"]) for row in rows) == r401.cov.EXPECTED_TERM_TOTAL


def test_main_caliber_reading_now_equals_the_unscorable_count(r401, rows):
    """判据⑤：改后"查无出处的行"必须正好只剩丙案那 19 枚，且行数==词条数的指纹不破。"""
    missing = r401.cov.find_missing_terms(rows, r401.cov.load_corpus(REPO_ROOT))
    unscorable = sorted(
        str(row["id"]) for row in rows
        if isinstance(row.get(MARKER_FIELD), dict) and row[MARKER_FIELD].get("disposition") == UNSCORABLE
    )
    assert sorted(missing) == unscorable
    assert len(missing) == sum(len(terms) for terms in missing.values()) == 19


# ---------------------------------------------------------------------------
# ② correctness 分母：账要能算，子集要能跑
# ---------------------------------------------------------------------------

def test_correctness_denominator_is_named_and_arithmetic_is_open(r401, rows):
    den = r401.denominator(rows)
    assert den["total_rows"] == 105
    assert den["unscorable_n"] == 19
    assert den["correctness_denominator"] == 86
    assert den["unscorable_ids"] == sorted(den["unscorable_ids"])
    assert len(den["unscorable_ids"]) == den["unscorable_n"]
    for piece in ("105", "19", "86"):
        assert piece in den["rule"], "分母规则没把三个数写明白：" + den["rule"]
    assert "evidence_coverage" in den["rule"], "要说清 evidence 与 total 仍按 105 走"


def test_the_scorable_subset_is_a_runnable_fixture(r401, rows, tmp_path):
    """86 枚那一份得真能当夹具跑：证明"扣分母"是可执行的账，不是一句说明。"""
    from app.quality.eval import evaluate_evaluation_set

    den = r401.denominator(rows)
    scorable = [row for row in rows if str(row["id"]) not in set(den["unscorable_ids"])]
    assert len(scorable) == den["correctness_denominator"] == 86

    path = tmp_path / "scorable86.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in scorable),
        encoding="utf-8",
    )
    reference = {str(row["id"]): row for row in scorable}

    def answer_fn(row):
        target = reference[str(row["id"])]
        return {
            "answer": " ".join([str(target["answer"])] + [str(t) for t in target["must_contain"]]),
            "evidence": [{"source_name": "制度与口径登记表", "locator": "第1行"}],
            "confidence_label": "high",
            "latency_ms": 100,
        }

    report = evaluate_evaluation_set(path, answer_fn)
    assert report["total"] == 86
    assert report["answer_correctness"] == 1.0
    assert report["evidence_coverage"] == 1.0
    assert set(den["unscorable_ids"]) & set(reference) == set(), "丙案没被真正从子集里剔除"
    assert set(reference) | set(den["unscorable_ids"]) == {str(row["id"]) for row in rows}, (
        "可判子集 + 丙案点名应当正好还原成 105 枚：一分母都没丢，只是分开记"
    )


def test_the_full_105_set_still_runs_with_the_unscorable_rows_inside_it(rows, tmp_path):
    """题没删：整套 105 行仍然可跑，丙案那 19 枚照旧出 correctness（只是不进本单的分母）。"""
    from app.quality.eval import evaluate_evaluation_set

    reference = {str(row["id"]): row for row in rows}

    def answer_fn(row):
        target = reference[str(row["id"])]
        return {
            "answer": " ".join([str(target["answer"])] + [str(t) for t in target["must_contain"]]),
            "evidence": [{"source_name": "制度与口径登记表", "locator": "第1行"}],
            "confidence_label": "high",
            "latency_ms": 100,
        }

    path = tmp_path / "full105.jsonl"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    report = evaluate_evaluation_set(path, answer_fn)
    assert report["total"] == 105
    assert report["answer_correctness"] == 1.0


# ---------------------------------------------------------------------------
# ③ 判据③那一节：unsupported-01..04 考的是"不编"
# ---------------------------------------------------------------------------

def test_refusal_rows_all_live_in_the_no_evidence_bucket(rows):
    by_id = {str(row["id"]): row for row in rows}
    for row_id in REFUSAL_ROWS:
        assert by_id[row_id]["category"] == "无证据问题", row_id
        assert by_id[row_id]["tier"] == "问答", row_id


def test_the_one_row_the_corpus_covers_now_demands_the_registered_code(rows):
    """unsupported-03（未登记指标）⇒ 用登记表§〇.4 的具名码；这是**判据变更**，不是放宽。"""
    code, registry_line = _registered_refusal_code()
    by_id = {str(row["id"]): row for row in rows}
    row = by_id["unsupported-03"]
    assert [str(t) for t in row["must_contain"]] == [code], (
        "具名码与登记表§〇.4 现抠出来的那个词不等：{0}".format(row["must_contain"])
    )
    records = row["anchor_provenance"]
    assert len(records) == 1 and records[0]["anchor"] == code
    assert records[0]["path"].endswith("制度与口径登记表.txt")
    assert "未登记的指标被问到" in records[0]["raw_line"], "出处行不是§〇.4 那一行"
    assert "必须回答" in records[0]["raw_line"]
    assert row[MARKER_FIELD]["disposition"] in RESOLVED
    reason = row[MARKER_FIELD]["reason"]
    assert "判据变更" in reason and "放宽" in reason, (
        "这一枚必须在理由里写明是判据变更而不是放宽：" + reason
    )


def test_the_three_refusals_that_are_not_caliber_questions_stay_named_unscorable(rows):
    by_id = {str(row["id"]): row for row in rows}
    for row_id in ("unsupported-01", "unsupported-02", "unsupported-04"):
        row = by_id[row_id]
        assert row[MARKER_FIELD]["disposition"] == UNSCORABLE, row_id
        assert "无法确认" in [str(t) for t in row["must_contain"]], (
            "{0} 的锚词被动过了：丙案只点名，不换词".format(row_id)
        )
        assert row[MARKER_FIELD]["missing_term"] == "无法确认", row_id
        reason = str(row[MARKER_FIELD]["reason"])
        if row_id == "unsupported-01":
            # 这一枚有两条独立的不可考：真行为缺陷（R129 禁改题掩盖）+ 30 行母集冻结。
            assert "行为缺陷" in reason and "母集" in reason, row_id
        assert "具名码" in reason, (
            "{0} 判丙的理由要交代为什么登记表具名码这条路也不成立：{1}".format(row_id, reason)
        )


def test_no_relaxed_refusal_word_entered_any_must_contain(rows):
    """🔴 反"把分抬上去"的那条线：R129 里靠换松弛词能救的三枚，本单一枚没采纳。"""
    offenders = {
        str(row["id"]): [str(t) for t in row["must_contain"] if str(t) in RELAXED_REFUSAL_WORDS]
        for row in rows
        if any(str(t) in RELAXED_REFUSAL_WORDS for t in row["must_contain"])
    }
    assert not offenders, "松弛拒答词进了判分锚词：" + json.dumps(offenders, ensure_ascii=False)


def test_confabulated_answers_still_miss_the_refusal_rows(rows):
    from app.quality.eval import _is_correct

    by_id = {str(row["id"]): row for row in rows}
    confabulations = {
        "unsupported-01": "公司没有火星基地。",
        "unsupported-02": "公司在海外没有自建工厂。",
        "unsupported-03": "CEO 持股 65%，其余为机构投资人。",
        "unsupported-04": "下个月不会裁员，请放心。",
    }
    for row_id, text in confabulations.items():
        assert _is_correct(by_id[row_id], {"answer": text}) is False, (
            "{0} 被一本正经的编造命中了：这一枚根本没在考'不编'".format(row_id)
        )


def test_unscorable_rows_carry_a_bone_fide_reason_and_a_destination(rows):
    """逐枚"为什么今天不可考"：理由要具体到事，不能是"暂无"。"""
    reasons = {
        str(row["id"]): row[MARKER_FIELD]
        for row in rows
        if isinstance(row.get(MARKER_FIELD), dict) and row[MARKER_FIELD].get("disposition") == UNSCORABLE
    }
    assert len(reasons) == 19
    for row_id, marker in reasons.items():
        assert len(str(marker["reason"])) >= 40, "{0} 的理由只有 {1} 字".format(row_id, len(str(marker["reason"])))
        assert str(marker["pool"]).startswith("待派池"), row_id
    kinds = collections.Counter(
        "语料互斥" in str(marker["reason"]) for marker in reasons.values()
    )
    assert kinds[True] == 2, "语料互斥未裁那两枚（doc-15/doc-17）应正好是 2 枚"
