"""R401 · 反证刀（判据⑥）：八把，全部落在 tmp 影子副本上，真盘一个字节都不改。

【每把刀要证明的那句话】
  K1 锚词换成一个不存在的词，缺口仍然会被指名（== "把词换掉"不等于"把账做平"）。
  K2 置空 must_contain 当场红（fail-closed 拒绝出数，而不是给出一个更小的数）。
  K3 删一行 105→104 当场红，且守恒 diff 立刻非空。
  K4 甲案锚词与派生出处不符 ⇒ 派生钉红。
  K5 改 category ⇒ 桶守恒钉红。
  K6 偷偷把某枚丙案的锚词换成一个有出处的词 ⇒ **双红**（复算缺口少了 + 点名账不认）。
  K7 给覆盖度件塞排除名单 ⇒ 静态闸红（与绿件同一条判定函数）。
  K8 出处指针改指到语料里另一行真在位的位置 ⇒ 派生钉红（证明钉的是地址，不是"这词存在过"）。

K0（真·基点干净影子克隆里的三件基线）不在这里跑：那是一次性取证，读数与命令见回执 §①/§⑦。
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_REV = "69e0035"
FIXTURE_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
FIXTURE_105 = REPO_ROOT / FIXTURE_REL
COVERAGE_SCRIPT = REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py"
R401_SCRIPT = REPO_ROOT / "scripts" / "r401_anchor_provenance.py"
MARKER_FIELD = "r401"


@pytest.fixture(scope="module")
def r401():
    spec = importlib.util.spec_from_file_location("r401_anchor_provenance_t3", R401_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def shadow(tmp_path):
    """造影子树：题源用调用方给的文本，语料按文件名原样复制 95 篇（真盘零改动）。"""

    def build(fixture_rows):
        root = tmp_path / "shadow"
        (root / "tests" / "fixtures").mkdir(parents=True, exist_ok=True)
        body = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\r\n" for row in fixture_rows
        )
        (root / FIXTURE_REL).write_bytes(body.encode("utf-8"))
        docs = root / "documents"
        docs.mkdir()
        for source in sorted((REPO_ROOT / "documents").glob("*.txt")):
            shutil.copyfile(source, docs / source.name)
        return root

    return build


def _rows(root):
    return [
        json.loads(line)
        for line in (root / FIXTURE_REL).read_bytes().decode("utf-8-sig").splitlines()
        if line.strip()
    ]


def _replace_term(root, row_id, old_term, new_term, field="must_contain"):
    """在影子副本上换掉一枚词条/字段值，返回改后的行列表（真盘不写）。"""
    rows = _rows(root)
    for row in rows:
        if str(row["id"]) != row_id:
            continue
        if field == "must_contain" and old_term is not None:
            row[field] = [new_term if str(t) == old_term else t for t in row[field]]
        else:
            row[field] = new_term
    return rows


def _counts(r401, root):
    rows = r401.cov.load_rows(root / r401.cov.FIXTURE_REL)
    corpus = r401.cov.load_corpus(root)
    return rows, r401.cov.find_missing_terms(rows, corpus)


def _base_rows(r401):
    run = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", "{0}:{1}".format(BASE_REV, FIXTURE_REL.as_posix())],
        capture_output=True,
    )
    if run.returncode != 0:
        return None
    return [json.loads(line) for line in run.stdout.decode("utf-8-sig").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 绿件那一头：处置账与基点比，守恒成立（下面每把刀都复用同一个函数）
# ---------------------------------------------------------------------------

def test_the_shipped_tree_passes_every_conservation_check(r401):
    base = _base_rows(r401)
    assert base is not None, "基点 {0} 的题源 blob 读不出来，无法证守恒".format(BASE_REV)
    assert r401.conservation_diff(base, r401.read_rows(REPO_ROOT)) == []
    source = COVERAGE_SCRIPT.read_text(encoding="utf-8")
    assert r401.audit_tool_is_marker_free(source) == []


# ---------------------------------------------------------------------------
# K1 锚词换成不存在的词，缺口仍被指名
# ---------------------------------------------------------------------------

def test_knife1_unresolvable_anchor_is_still_named(r401, shadow):
    """把手抄味最重的那一种改法（把「按自然日计算」写成金标里的「按自然日计发」）当场抓出来。"""
    rows = _replace_term(REPO_ROOT, "doc-07", "按自然日计算", "按自然日计发")
    root = shadow(rows)
    _, missing = _counts(r401, root)
    assert "doc-07" in missing and missing["doc-07"] == ["按自然日计发"], missing.get("doc-07")
    assert len(missing) == 20, "本该只多出一枚缺口，看到 {0}".format(len(missing))
    failures = r401.verify(root)
    assert any("doc-07" in line for line in failures), failures
    assert any("仍查无出处" in line for line in failures), failures


# ---------------------------------------------------------------------------
# K2 置空 must_contain 当场红
# ---------------------------------------------------------------------------

def test_knife2_emptied_must_contain_refuses_to_produce_a_number(r401, shadow, capsys):
    rows = _replace_term(REPO_ROOT, "report-03", None, [], field="must_contain")
    root = shadow(rows)
    with pytest.raises(r401.cov.StructureDrift, match="must_contain 为空"):
        r401.cov.load_rows(root / r401.cov.FIXTURE_REL)
    assert r401.cov.main(["--repo-root", str(root)]) == r401.cov.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "report-03" in captured.err, captured.err
    assert "查无出处的行" not in captured.out, "结构不对还出数，等于把红藏起来"


# ---------------------------------------------------------------------------
# K3 删一行 ⇒ 守恒钉红
# ---------------------------------------------------------------------------

def test_knife3_dropping_a_row_trips_fail_closed_and_conservation(r401, shadow, capsys):
    rows = [row for row in _rows(REPO_ROOT) if str(row["id"]) != "tool-03"]
    assert len(rows) == 104
    root = shadow(rows)
    assert r401.cov.main(["--repo-root", str(root)]) == r401.cov.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "看到 104 行，期望 105 行" in captured.err, captured.err
    assert "查无出处的行" not in captured.out
    base = _base_rows(r401)
    if base is None:
        pytest.skip("没有 git，无法与基点比守恒")
    drift = r401.conservation_diff(base, rows)
    assert drift and any("行序或 id 集合变了" in line for line in drift), drift


# ---------------------------------------------------------------------------
# K4 甲案锚词与派生出处不符 ⇒ 派生钉红
# ---------------------------------------------------------------------------

def test_knife4_anchor_that_no_longer_matches_its_recorded_provenance_is_red(r401, shadow):
    """scope-03 的锚词换成同样在语料里、但记录里不是它的那一枚（机密级 → 内部级）。"""
    rows = _replace_term(REPO_ROOT, "scope-03", "机密级", "内部级")
    root = shadow(rows)
    failures = r401.verify(root)
    assert any("scope-03" in line and "内部级" in line for line in failures), failures
    assert any("题源锚词" in line for line in failures), failures


# ---------------------------------------------------------------------------
# K5 改 category ⇒ 桶守恒钉红
# ---------------------------------------------------------------------------

def test_knife5_category_edit_breaks_the_bucket_pin(r401, shadow):
    base = _base_rows(r401)
    if base is None:
        pytest.skip("没有 git，无法与基点比守恒")
    rows = _replace_term(REPO_ROOT, "doc-14", None, "口径冲突", field="category")
    root = shadow(rows)
    drift = r401.conservation_diff(base, rows)
    assert any("category 桶分布变了" in line for line in drift), drift
    assert any("doc-14.category 动了" in line for line in drift), drift
    # 复算那边看不出任何异常 —— 这正是守恒必须单独钉一把的原因
    _, missing = _counts(r401, root)
    assert "doc-14" not in missing


# ---------------------------------------------------------------------------
# K6 偷偷换掉一枚丙案的锚词 ⇒ 双红
# ---------------------------------------------------------------------------

def test_knife6_sneaky_anchor_swap_on_an_unscorable_row_is_red_twice(r401, shadow):
    base = _base_rows(r401)
    rows = _replace_term(REPO_ROOT, "data-08", "小计", "合计")
    root = shadow(rows)
    _, missing = _counts(r401, root)
    assert len(missing) == 18 and "data-08" not in missing, sorted(missing)
    failures = r401.verify(root)
    assert any("data-08" in line and "复算缺口" in line for line in failures), failures
    if base is not None:
        drift = r401.conservation_diff(base, rows)
        assert any("判丙却改了" in line for line in drift), drift


# ---------------------------------------------------------------------------
# K7 给覆盖度件加排除名单 ⇒ 静态闸红
# ---------------------------------------------------------------------------

def test_knife7_exclusion_list_in_the_coverage_tool_is_red(r401):
    source = COVERAGE_SCRIPT.read_text(encoding="utf-8")
    assert r401.audit_tool_is_marker_free(source) == [], "真件已经不干净了，先修它再谈刀"
    smuggled = source.replace(
        "    missing: dict[str, list[str]] = {}",
        '    EXCLUDE_IDS = {"chat-02"}  # 暂时放行\n    missing: dict[str, list[str]] = {}',
        1,
    )
    assert smuggled != source, "注入点变了，这把刀就空转了"
    violations = r401.audit_tool_is_marker_free(smuggled)
    assert any("EXCLUDE" in line for line in violations), violations
    keyed = source.replace(
        "    documents = list(corpus.values())",
        '    documents = list(corpus.values())\n'
        '    rows = [row for row in rows if str(row.get("' + MARKER_FIELD + '")) != "丙"]',
        1,
    )
    assert keyed != source, "注入点变了，这把刀就空转了"
    assert any("disposition" in line or MARKER_FIELD in line
               for line in r401.audit_tool_is_marker_free(keyed)), keyed[:200]


# ---------------------------------------------------------------------------
# K8 出处指针改指到别处 ⇒ 派生钉红
# ---------------------------------------------------------------------------

def test_knife8_redirected_pointer_is_red_even_though_the_word_exists(r401, shadow):
    """手册:151 与手册:156 都含「机密级」：把指针挪到 156 行，词仍然在，地址就不再是它。"""
    rows = _rows(REPO_ROOT)
    moved = 0
    for row in rows:
        if str(row["id"]) != "scope-03":
            continue
        for record in row["anchor_provenance"]:
            if record["anchor"] == "机密级":
                assert "机密级" in record["raw_line"]
                record["raw_line_number"] = 156
                moved += 1
    assert moved == 1
    root = shadow(rows)
    _, missing = _counts(r401, root)
    assert "scope-03" not in missing, "词当然还在语料里，所以只查「这词存在过」根本不够"
    failures = r401.verify(root)
    assert any("scope-03" in line for line in failures), failures
    assert any("与语料现算结果不符" in line for line in failures), failures
