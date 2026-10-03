"""R598 · 反证刀（判据⑧）：砍在**本单自己的量具与待授权账**上，全部落 tmp 影子副本，真盘零改动。

【每把刀要证明的那句话】
  T1 置空某枚 must_contain ⇒ 台账拒绝出数（fail-closed），不是给一个更小的数。
  T2 删一行 105→104 ⇒ 同上，且守恒账立刻非空。
  T3 把某枚的 category 挪一档 ⇒ 桶守恒刀红（判据②）。
  T4 待授权甲案的出处指针造假（同篇另一行 / 另一篇那一行）⇒ 派生腿红：钉的是**地址**，
     不是「这个词在语料里存在过」。锚词「须为公司全称」全库唯一命中细则:32 一次，已由本刀现算。
  T5 甲案锚词换成一枚语料里不存在的词 ⇒ 影子根读数**不降**且这枚仍被指名：换词不等于救题。
  T6 从归桶账里摘掉一枚 ⇒ 处置表抛（判据①「一枚不落」）。
  T7 归桶账里留一枚已不在缺口名册上的 id ⇒ 处置表抛（防「名册变了账不变」）。
  T8 待授权账的 replaced_term 抄错一枚字 ⇒ 现算缺口对账抛（判据③「禁手抄」）。

与在册同族件的分工：`tests/test_r401_teeth.py` 的 K1-K8 砍 R401 那套账（它钉的是已落地的 10 枚）；
本件砍 R598 这套账（19 枚归桶 + 那枚待授权的甲 + 台账这把尺）。三片完整性那 7 把在
`tests/test_r598_r97_shards_are_derived.py`。反证钉不分层出门（AGENTS.md 回归纪律）。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCRIPT = REPO_ROOT / "scripts" / "r598_disposition_ledger.py"
PENDING_SCRIPT = REPO_ROOT / "scripts" / "r598_pending_jia.py"
MASTER_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
CORPUS_REL = Path("documents")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger():
    return _load("r598_ledger_t2", LEDGER_SCRIPT)


@pytest.fixture(scope="module")
def pending():
    return _load("r598_pending_t2", PENDING_SCRIPT)


@pytest.fixture()
def shadow(tmp_path):
    """影子根：95 篇语料原样复制 + 调用方给的题源文本。真盘一个字节不动。"""

    def build(rows):
        root = tmp_path / "shadow"
        (root / MASTER_REL.parent).mkdir(parents=True, exist_ok=True)
        body = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\r\n" for row in rows
        )
        (root / MASTER_REL).write_bytes(body.encode("utf-8"))
        docs = root / CORPUS_REL
        docs.mkdir()
        for source in sorted((REPO_ROOT / CORPUS_REL).glob("*.txt")):
            shutil.copyfile(source, docs / source.name)
        return root

    return build


def _rows():
    return [
        json.loads(line)
        for line in (REPO_ROOT / MASTER_REL).read_bytes().decode("utf-8-sig").splitlines()
        if line.strip()
    ]


def _edited(row_id, field, value):
    rows = _rows()
    for row in rows:
        if str(row["id"]) == row_id:
            row[field] = value
    return rows


# ---------------------------------------------------------------------------
# T1 / T2 尺子本身 fail-closed
# ---------------------------------------------------------------------------

def test_T1_emptied_must_contain_refuses_to_produce_a_number(ledger, shadow):
    cov = ledger.load_deps()["cov"]
    root = shadow(_edited("doc-01", "must_contain", []))
    with pytest.raises(cov.StructureDrift):
        ledger.coverage_reading(root)


def test_T2_dropping_a_row_trips_the_scale_and_the_conservation_pin(ledger, shadow):
    cov = ledger.load_deps()["cov"]
    rows = _rows()[:-1]
    root = shadow(rows)
    with pytest.raises(cov.StructureDrift):
        ledger.coverage_reading(root)
    report = ledger.conservation_between(_rows(), rows)
    assert report["violations"], "删掉一行而守恒账毫无反应 ⇒ 这枚刀是空转"


# ---------------------------------------------------------------------------
# T3 桶守恒
# ---------------------------------------------------------------------------

def test_T3_moving_a_row_to_another_category_breaks_the_bucket_pin(ledger):
    base = ledger.base_rows(REPO_ROOT)
    assert base is not None, "基点 blob 读不出来，守恒无法判"
    moved = _edited("doc-01", "category", "多轮对话")
    report = ledger.conservation_between(base, moved)
    assert any("category" in item for item in report["violations"]), report["violations"]
    assert any(item.startswith("doc-01.category") for item in report["violations"]), (
        "逐枚那一格也要指名：只报分布不报枚，改回来时没人知道改了谁")


# ---------------------------------------------------------------------------
# T4 甲案出处指针造假 ⇒ 派生腿红
# ---------------------------------------------------------------------------

def test_T4_forged_provenance_pointer_is_red_though_the_word_exists(ledger, pending, shadow):
    dd = pending.deps(REPO_ROOT)
    r401 = dd["r401"]
    corpus = r401.corpus_by_name(REPO_ROOT)
    anchor = pending.PENDING_JIA["doc-17"]["fields"]["must_contain"][0]
    #: 全库唯一命中：细则:32 一次。这一条是 T4 成立的前提，先把它钉死。
    hits = dd["cov"].derive_term_provenance(anchor, dd["cov"].load_corpus_raw(REPO_ROOT))
    assert [(hit["path"], hit["raw_line_numbers"]) for hit in hits] == [
        ("documents/差旅费报销细则_2026版.txt", [32])], "锚词命中面变了，T4 要重算"
    for fake in (("企业管理制度手册.txt", 65), ("差旅费报销细则_2026版.txt", 31)):
        with pytest.raises(r401.DerivationError):
            r401.provenance_for_row(corpus, "doc-17", [anchor], {anchor: fake})


# ---------------------------------------------------------------------------
# T5 换成不存在的词：影子根读数不降，且这枚仍被指名
# ---------------------------------------------------------------------------

def test_T5_unresolvable_replacement_anchor_still_gets_named(ledger, shadow):
    before = ledger.coverage_reading(REPO_ROOT)
    rows = _edited("doc-17", "must_contain", ["须为个人抬头"])
    after = ledger.coverage_reading(shadow(rows))
    assert "doc-17" in after["missing_ids"], "换了枚语料没有的词，缺口居然消失了 ⇒ 尺子被换词骗了"
    assert after["missing_by_row"]["doc-17"] == ["须为个人抬头"], (
        "指名的是旧词不是新词：说明账是从纸面抄的，不是现算的")
    assert after["missing_rows"] == before["missing_rows"], (
        "换成语料不存在的词反而让缺口变小，这把尺就白装了")


def test_T5b_the_legitimate_anchor_is_the_one_that_actually_moves_the_number(ledger, shadow, pending):
    """与 T5 成对：唯一能让缺口降一格的，是**在位**那枚词，而且是派生出来的那枚。"""
    planned, proofs = pending.planned_rows(
        REPO_ROOT, _rows(), pending.deps(REPO_ROOT)["cov"], pending.deps(REPO_ROOT)["r401"])
    after = ledger.coverage_reading(shadow(planned))
    assert after["missing_rows"] == 18 and "doc-17" not in after["missing_ids"]
    assert proofs["doc-17"]["derived_records"][0]["raw_line"] , "派生出处是空的"


# ---------------------------------------------------------------------------
# T6 / T7 归桶账
# ---------------------------------------------------------------------------

def test_T6_dropping_a_row_from_the_bucket_ledger_is_red(ledger, monkeypatch):
    monkeypatch.delitem(ledger.BUCKET_OF, "doc-15", raising=False)
    with pytest.raises(AssertionError):
        ledger.disposition_table(REPO_ROOT)


def test_T7_stale_id_in_the_bucket_ledger_is_red(ledger, monkeypatch):
    monkeypatch.setitem(ledger.BUCKET_OF, "ghost-99", "X 编的一枚")
    with pytest.raises(AssertionError):
        ledger.disposition_table(REPO_ROOT)


# ---------------------------------------------------------------------------
# T8 被替换词必须由现算缺口背书（禁手抄）
# ---------------------------------------------------------------------------

def test_T8_hand_copied_replaced_term_is_red(pending, monkeypatch):
    monkeypatch.setitem(
        pending.PENDING_JIA["doc-17"], "replaced_term", "公司抬投")  # 故意把字面抄错一位
    with pytest.raises(AssertionError):
        pending.check_replaced_terms(REPO_ROOT)


def test_T8b_pending_ledger_refuses_a_row_that_is_no_longer_missing(pending, monkeypatch):
    """待授权账里那枚如果已经被别人落地（不再缺出处），本件必须拒绝继续出数而不是继续算它的账。"""
    monkeypatch.setitem(pending.PENDING_JIA, "doc-01", pending.PENDING_JIA["doc-17"])
    with pytest.raises(AssertionError):
        pending.check_replaced_terms(REPO_ROOT)