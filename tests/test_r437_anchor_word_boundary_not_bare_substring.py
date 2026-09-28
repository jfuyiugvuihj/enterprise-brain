"""R437 常驻钉：拉丁锚词要按**词边界（token）**判出处，裸子串不许再替它冒充「有出处」。

病灶（上一格 Darwin/R435 抓到、总控主树复核）：量具按「归一化后子串」判命中，于是锚词
`Word` 因为在 `password` / `your_password` 里出现过就被判「有出处」—— 那枚导出题在语料里
一个独立成词的地方都没有。件口径那句「这枚锚词有出处」是量具替题目说的假话。

本件钉住四件事：
  ① 两档规则写死：按**锚词自身**归一化后含不含 CJK 字符分档 —— ascii 档要独立成词，
     cjk 档保持子串语义（中文没有词边界，「一页纸」「不需要打印」照旧必须能命中）。
     分界只认字符，不认题号，没有逐枚特例。
  ② 双口径同时出数：件口径（账上那把尺，tests/test_r94_eval_evidence_coverage.py 钉它）与
     语义口径一起报，分歧逐枚点名 —— 哪枚题、哪枚锚词、被哪个整 token 吞了、在语料哪一行。
  ③ 翻转面单向且枚枚有名：语义口径只准在件口径之上加严；反向翻转、中文档分歧、藏命中形
     都由 audit_calibers / render_caliber_block 当场拒绝出数。
  ④ 不许「查不出」的静默：语料读不出、编码不通、锚词字段坏了 —— 一律指名报错。

反证刀（用例名带 counter_evidence 的都是刀，形状与预期红/绿就地写在各枚 docstring 里）：
  刀 a 摘掉词边界 ⇒ 语义口径退化成与件口径同数、分歧表变空 ⇒ 交叉对账红。
  刀 b 报告只带一把尺 ⇒ render 当场 StructureDrift ⇒ pytest.raises 咬住。
  刀 c 把 word 这类命中形写死豁免 ⇒ 该点名的分歧不再点名 ⇒ 逐枚点名断言红；
     并且全模块扫不出一枚以锚词为内容的名单（豁免名单就是病灶本身）。
  刀 d 把词边界推广到 Unicode 字母并绕过分档 ⇒ 中文真命中被判没 ⇒ 交叉对账红。
  刀 e 分歧不交代命中形 ⇒ 空表由 audit_calibers 指名拒绝；伪造「独立成词」由点名断言咬红。

⑦ 期望数一律现算：件口径来自 find_missing_terms 的原样调用，语义口径来自本文件自带的第二份
实现（与生产不共享一个函数），条目总数取自脚本常量 EXPECTED_TERM_TOTAL —— 文件里没有一个手抄题数。
全程离线：只读仓内文本 + tmp 影子树，零模型、零网络、零容器、零连库；不写 docs/**。
"""
import importlib.util
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

# ---------------------------------------------------------------------------
# 第二份独立实现 —— 对账用的尺，故意不与生产代码共享任何一个函数
# ---------------------------------------------------------------------------

TEST_CJK_PATTERN = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"
)
TEST_CONTINUATION = re.compile(r"[0-9a-z_]")
TEST_WHITESPACE = re.compile(r"\s+")


def _bare(text: str) -> str:
    """件口径的第二份实现：NFKC → 去所有空白 → casefold。"""
    return TEST_WHITESPACE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def _spaced(text: str) -> str:
    """语义口径的第二份实现：与 _bare 同三步，只把空白折成一枚分隔符。"""
    return TEST_WHITESPACE.sub("\u0000", unicodedata.normalize("NFKC", text)).casefold()


def _tier(term: str) -> str:
    """本文件自己判档：只看锚词含不含 CJK，不借生产函数（否则刀 d 就砍不动了）。"""
    return "cjk" if TEST_CJK_PATTERN.search(_bare(term)) else "ascii"


def _delimited(text: str, start: int, end: int) -> bool:
    left = text[start - 1] if start > 0 else ""
    right = text[end] if end < len(text) else ""
    return not (left and TEST_CONTINUATION.match(left)) and not (
        right and TEST_CONTINUATION.match(right)
    )


def _token_hit(term: str, spaced_text: str) -> bool:
    needle = _spaced(term)
    cursor = 0
    while True:
        index = spaced_text.find(needle, cursor)
        if index < 0:
            return False
        if _delimited(spaced_text, index, index + len(needle)):
            return True
        cursor = index + 1


def _independent_calibers(rows, corpus_raw, field):
    """自己走一遍两把尺：返回 (件口径缺的题号, 语义口径缺的题号, 分歧条目, 条目总数)。"""
    bare_docs = [_bare(raw) for _path, raw in corpus_raw.values()]
    spaced_docs = [_spaced(raw) for _path, raw in corpus_raw.values()]
    case_missing: set = set()
    semantic_missing: set = set()
    divergent: list = []
    total = 0
    for row in rows:
        row_id = str(row["id"])
        for term in row[field]:
            term_text = str(term)
            total += 1
            hit_case = any(_bare(term_text) in text for text in bare_docs)
            if _tier(term_text) == "cjk":
                hit_semantic = hit_case
            else:
                hit_semantic = hit_case and any(
                    _token_hit(term_text, text) for text in spaced_docs
                )
            if not hit_case:
                case_missing.add(row_id)
            if not hit_semantic:
                semantic_missing.add(row_id)
            if hit_case and not hit_semantic:
                divergent.append((row_id, term_text))
    return case_missing, semantic_missing, divergent, total


# ---------------------------------------------------------------------------
# 装载与公共断言
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_eval_evidence_coverage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _view(checker, root=None, **flags):
    """一次读取取回两把尺的全部输入（与 main() 走同一条语料装载路径）。"""
    root = REPO_ROOT if root is None else root
    rows = checker.load_rows(root / checker.FIXTURE_REL)
    entries = checker._corpus_entries(root, **flags)
    corpus = {label: checker.normalize(raw) for label, _path, raw in entries}
    corpus_raw = {label: (path, raw) for label, path, raw in entries}
    missing = checker.find_missing_terms(rows, corpus)
    audit = checker.audit_calibers(rows, missing, corpus, corpus_raw)
    return rows, corpus, corpus_raw, missing, audit


def _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit):
    """双口径对账：生产读数必须与本文件的第二份实现逐集合相等（判据②③；刀 a/d 的靶）。"""
    case_ids, semantic_ids, divergent, total = _independent_calibers(
        rows, corpus_raw, checker.MUST_CONTAIN_FIELD
    )
    assert audit["case"]["row_ids"] == sorted(case_ids), (
        "件口径的账变了：这把尺本单一个字都不该动（tests/test_r94_eval_evidence_coverage.py 钉它）"
    )
    assert audit["semantic"]["row_ids"] == sorted(semantic_ids), (
        "语义口径与第二份实现不等：要么词边界写坏了，要么它吃进了中文锚词"
    )
    assert {(item["row_id"], item["term"]) for item in audit["divergence"]} == set(divergent), (
        "分歧表没有正好点名两把尺判定不同的那批锚词（少一枚是藏起来，多一枚是误伤）"
    )
    assert audit["entry_total"] == total == checker.EXPECTED_TERM_TOTAL, (
        "翻转面对账的条目数与题源词条总数不符"
    )
    assert set(audit["case"]["row_ids"]) <= set(audit["semantic"]["row_ids"]), (
        "语义口径只准在件口径之上加严，不许反向放宽"
    )
    for item in audit["flips"]:
        assert item["case_hit"] and not item["semantic_hit"], (
            "翻转面里出现了「缺出处 → 有出处」的反向条目：" + repr(item)
        )


def _assert_divergence_names_who_swallowed_it(audit, checker):
    """每条分歧都得交代「被谁吞进去」：命中形在、比锚词长、且确实不是独立成词（判据⑥e）。"""
    for item in audit["divergence"]:
        assert item["tier"] == _tier(item["term"]) == "ascii", (
            "cjk 档锚词进了分歧表 —— 中文没有词边界，这一条就是误伤：" + repr(item["term"])
        )
        forms = item["hit_forms"]
        assert forms, "分歧条目没有命中形，等于把分歧藏起来：" + repr(item)
        needle = _bare(item["term"])
        for form in forms:
            assert form["path"], "命中形必须指名到文件：" + repr(form)
            if form["kind"] == "cross_line_only":
                assert form["note"], "跨行拼接出来的命中也必须说明白，不许凭空消失"
                continue
            token = form["enclosing_token"]
            assert form["raw_line_number"], "命中形必须给出行号：" + repr(form)
            assert needle in token and len(token) > len(needle), (
                "这一处并不是「被更长的 token 吞掉」，分歧表在说谎：" + repr(form)
            )
            assert not form["independent_word"], (
                "分歧条目里出现独立成词的命中形，两把尺的账自相矛盾：" + repr(form)
            )


# ---------------------------------------------------------------------------
# ①②③ 双口径本体
# ---------------------------------------------------------------------------


def test_both_calibers_are_reported_and_neither_is_switched_off(checker, capsys):
    """两把尺同时出数：件口径 == find_missing_terms 原样，语义口径 == 加严后的读数（②⑦）。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    assert sorted(missing) == audit["case"]["row_ids"], "件口径视图必须就是原那把尺的结果"
    assert audit["tier_rule"] == checker.TERM_TIER_RULE
    assert audit["semantic"]["latin_match_mode"] == checker.LATIN_MATCH_MODE
    assert audit["semantic"]["cjk_match_mode"] == checker.CJK_MATCH_MODE == checker.MATCH_MODE

    assert checker.main(["--repo-root", str(REPO_ROOT)]) == checker.EXIT_OK
    out = capsys.readouterr().out
    assert "查无出处的行 = {0}".format(audit["case"]["row_count"]) in out, "件口径的数没出门"
    assert "复核后 = {0}".format(audit["semantic"]["row_count"]) in out, "语义口径的数没出门"
    assert out.count("查无出处的行 = ") == 1, "件口径的出数行只许有一枚（test_r94 按它解析）"
    assert out.count("缺出处的题号") == 1, "题号清单只许有一份（test_r94 按它切报告）"
    assert "两把尺同时出数" in out and "分歧来源" in out and "翻转面对账" in out
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)


def test_the_delta_between_rulers_is_exactly_the_buried_anchors(checker):
    """两把尺的差集必须正好是「只在更长 token 里出现」的那批锚词，枚枚有名（①②③）。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    _assert_divergence_names_who_swallowed_it(audit, checker)
    _case, _semantic, divergent, _total = _independent_calibers(
        rows, corpus_raw, checker.MUST_CONTAIN_FIELD
    )
    assert {(item["row_id"], item["term"]) for item in audit["divergence"]} == set(divergent), (
        "分歧表与第二份实现算出的埋没锚词不是同一批"
    )
    extra_rows = sorted(set(audit["semantic"]["row_ids"]) - set(audit["case"]["row_ids"]))
    assert extra_rows == sorted({item["row_id"] for item in audit["divergence"]}), (
        "语义口径多报的题与分歧表点名的题不是同一批"
    )
    for item in audit["divergence"]:
        assert item["row_id"] not in missing, (
            "分歧条目在件口径眼里本来就该是缺的 —— 那它不叫假阳性：" + repr(item)
        )


def test_latin_anchor_needs_its_own_token_not_a_longer_one(checker, tmp_path, monkeypatch):
    """影子树正证：锚词只以子串形式出现 ⇒ 语义口径判缺；独立成词出现 ⇒ 判有（按证据不按名字）。"""
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    terms = _ascii_terms(rows, checker.MUST_CONTAIN_FIELD)
    assert terms, "题源里一枚 ascii 档锚词都没有，本用例的形状需随题源一起改写"
    monkeypatch.setattr(checker, "EXPECTED_CORPUS_TXT_COUNT", 1)

    buried = _shadow_root(
        tmp_path / "buried", checker, {"buried.txt": " ".join("zz" + t + "qq" for t in terms)}
    )
    rows_b, _corpus_b, raw_b, _missing_b, audit_b = _view(checker, root=buried)
    assert sorted({item["term"] for item in audit_b["divergence"]}) == terms, (
        "只以子串形式出现的 ascii 锚词没有被逐枚点名 —— 词边界这一格根本没修上"
    )
    _assert_divergence_names_who_swallowed_it(audit_b, checker)
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows_b, raw_b, audit_b)
    for item in audit_b["divergence"]:
        tokens = {form["enclosing_token"] for form in item["hit_forms"]}
        assert all(token.lower() != _bare(item["term"]) for token in tokens), (
            "命中形自己就等于锚词：这一处其实是独立成词，影子语料写得不算数"
        )

    genuine = _shadow_root(
        tmp_path / "genuine",
        checker,
        {"genuine.txt": "把结果导出成 " + " / ".join(terms) + " 就行"},
    )
    rows_g, _corpus_g, raw_g, missing_g, audit_g = _view(checker, root=genuine)
    assert audit_g["divergence"] == [], (
        "这些锚词在影子语料里已经独立成词，还判缺出处就是按名字定罪，不是按证据定罪"
    )
    assert missing_g, "影子树上中文锚词照样缺 —— 尺没有塌成「全都算有出处」"
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows_g, raw_g, audit_g)


def test_cjk_anchor_verdicts_are_identical_across_the_two_rulers(checker):
    """分档规则的正面：全部 cjk 档条目在两把尺下判定恒等（中文保持子串语义）（①）。"""
    rows, corpus, corpus_raw, _missing, audit = _view(checker)
    cjk_entries = [item for item in audit["entries"] if _tier(item["term"]) == "cjk"]
    assert cjk_entries, "题源里没有中文锚词，本用例的形状需随题源一起改写"
    assert all(item["tier"] == "cjk" for item in cjk_entries), (
        "生产分档与第二份实现的分档不一致：分界规则被改成了认题号的形状"
    )
    assert all(item["case_hit"] == item["semantic_hit"] for item in cjk_entries), (
        "有中文锚词被词边界误伤：判据①明令 cjk 档保持子串语义"
    )
    assert [item for item in cjk_entries if item["case_hit"]], (
        "语料里一个中文锚词都没命中，本用例的正证需随语料一起改写"
    )
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)


def test_naive_unicode_word_boundary_would_break_the_cjk_tier(checker):
    """①的分档理由钉成可执行：``\\b`` 那一类写法（认 CJK 为单词字符）会成片吃掉中文命中。"""
    rows, corpus, corpus_raw, _missing, audit = _view(checker)
    sample = "本报告请导出PDF并附一页纸说明"
    assert not re.search(r"(?<!\w)pdf(?!\w)", _spaced(sample), re.UNICODE), (
        "反例形状失效：\\b 在这里居然也能命中"
    )
    assert checker.find_token_positions("PDF", checker.normalize_word_spaced(sample)), (
        "本件的词边界规则把中文里独立成词的 PDF 判掉了 —— 那就是判据①的反面"
    )
    assert _bare("一页纸") in _bare(sample), "中文子串语义照旧（归一化没被拆）"

    naive_lost = 0
    for item in audit["entries"]:
        if _tier(item["term"]) != "cjk" or not item["case_hit"]:
            continue
        needle = _bare(item["term"])
        if not any(
            re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", _spaced(raw), re.UNICODE)
            for _path, raw in corpus_raw.values()
        ):
            naive_lost += 1
    assert naive_lost, "反例形状失效：\\w 式写法在这里居然不吃中文锚词"


def test_flip_surface_covers_every_anchor_entry_in_one_direction(checker):
    """③：全部锚词条目 before/after 全量在案，方向只准「有出处 → 缺出处」。"""
    rows, corpus, corpus_raw, _missing, audit = _view(checker)
    assert len(audit["entries"]) == checker.EXPECTED_TERM_TOTAL
    assert audit["ascii_entries"] + audit["cjk_entries"] == audit["entry_total"]
    assert audit["flips"] == [item for item in audit["entries"] if item["changed"]]
    assert audit["semantic"]["row_count"] >= audit["case"]["row_count"]
    assert audit["semantic"]["term_count"] >= audit["case"]["term_count"], (
        "语义口径判缺的锚词只准不比件口径少（加严），少了就是放宽"
    )
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)


def test_case_caliber_and_r401_credentials_are_untouched(checker):
    """件口径与 R401 取证件都不许被本单带偏（⑤行为保持；两把尺不许互相代用）。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    own = {}
    for row in rows:
        bad = [
            str(term)
            for term in row[checker.MUST_CONTAIN_FIELD]
            if not any(_bare(str(term)) in text for text in corpus.values())
        ]
        if bad:
            own[str(row["id"])] = bad
    assert missing == own, "件口径不再是裸子串的结果：这把尺本单一个字都不该动"
    assert checker.MATCH_MODE == "substring_within_single_document"
    assert checker.NORMALIZATION_STEPS == ("NFKC", "strip_all_whitespace", "casefold")
    assert audit["case"]["missing_by_row"] == missing, "双口径账里的件口径与函数结果不是同一份"
    for item in audit["divergence"]:
        records = checker.derive_term_provenance(item["term"], corpus_raw)
        assert records, (
            "R401 的派生出处被本单改没了 —— 取证件（裸子串）与判分尺（两档）是两件事"
        )


def test_casefold_step_is_still_load_bearing(checker, monkeypatch):
    """归一化第三步不许摘：摘掉它件口径的账当场就变（这是上一格反证刀 a 的靶子）。"""
    rows, corpus, _raw, missing, audit = _view(checker)
    baseline = audit["case"]["row_count"]

    def _no_casefold(text: str) -> str:
        return TEST_WHITESPACE.sub("", unicodedata.normalize("NFKC", text))

    # 第二把尺不看了，只看件口径自己：把归一化的第三步摘掉，账必须当场变。
    corpus_plain = {label: _no_casefold(raw) for label, raw in _raw_texts(checker).items()}
    moved = len(checker.find_missing_terms(rows, corpus_plain))
    assert moved != baseline, "摘掉 casefold 之后件口径的账却没变：说明这步早就不承重"


def _raw_texts(checker):
    """{文件标签: 原始文本} —— 走件口径同一份装载路径，只是不归一化。"""
    return {label: raw for label, _path, raw in checker._corpus_entries(REPO_ROOT)}


def test_caliber_json_carries_both_rulers_and_the_full_comparison(checker, tmp_path):
    """--caliber-json：两把尺 + 逐枚分歧 + 全部条目 before/after 一起交（③⑦的机器面）。"""
    target = tmp_path / "nested" / "calibers.json"
    argv = ["--repo-root", str(REPO_ROOT), "--caliber-json", str(target)]
    assert checker.main(argv) == checker.EXIT_OK
    payload = json.loads(target.read_text(encoding="utf-8"))
    rows, _corpus, corpus_raw, missing, audit = _view(checker)
    assert payload["case"]["row_ids"] == sorted(missing)
    assert payload["case"]["row_ids"] == audit["case"]["row_ids"]
    assert payload["semantic"]["row_ids"] == audit["semantic"]["row_ids"]
    assert payload["tier_rule"] == checker.TERM_TIER_RULE
    assert len(payload["entries"]) == checker.EXPECTED_TERM_TOTAL
    for item in payload["entries"]:
        assert {"row_id", "term", "tier", "case_hit", "semantic_hit", "changed"} <= set(item)
    for item in payload["divergence"]:
        assert item["hit_forms"], "每条分歧都得带上命中形"
        assert item["case_documents"], "每条分歧都得带上件口径算的出处篇目"
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, payload)


# ---------------------------------------------------------------------------
# ④ 不许「查不出」的静默
# ---------------------------------------------------------------------------


def test_undecodable_corpus_file_is_named_not_skipped(checker, capsys, tmp_path, monkeypatch):
    """语料编码不通 ⇒ 指名文件拒绝出数，既不当「这一篇没出处」，也不当空气跳过。"""
    root = _shadow_root(tmp_path, checker, {"ok.txt": "正常一篇"})
    (root / "documents" / "broken.txt").write_bytes(b"\xff\xfe\xff\x80\x81\xff")
    monkeypatch.setattr(checker, "EXPECTED_CORPUS_TXT_COUNT", 2)
    assert checker.main(["--repo-root", str(root)]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "broken.txt" in captured.err, "解码失败必须指名是哪一个文件"
    assert "查无出处的行" not in captured.out, "读不出语料时不许静默给出一个数"


def test_unreadable_corpus_entry_is_named_not_skipped(checker, capsys, tmp_path, monkeypatch):
    """清单里有一篇、盘上取不到字节 ⇒ read_corpus_bytes 指名报错，不许少一篇照样出数。"""
    root = _shadow_root(tmp_path, checker, {"kept.txt": "跟踪中的一篇"})
    monkeypatch.setattr(checker, "EXPECTED_CORPUS_TXT_COUNT", 2)
    monkeypatch.setattr(
        checker,
        "corpus_scope",
        lambda directory, pattern: sorted(directory.glob(pattern)) + [directory / "gone.txt"],
    )
    assert checker.main(["--repo-root", str(root)]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "gone.txt" in captured.err, "取不到的语料必须指名"
    assert "查无出处的行" not in captured.out


@pytest.mark.parametrize(
    "label,term_value",
    [("缺字段", None), ("空列表", []), ("非字符串", [123]), ("归一化为空", ["   "])],
)
def test_broken_must_contain_field_is_named_per_row(
    checker, capsys, tmp_path, monkeypatch, label, term_value
):
    """某题 must_contain 坏了（缺失/空/非字符串/归一化为空）⇒ 指名题号拒绝出数（④）。"""
    source = [
        json.loads(line)
        for line in FIXTURE_105.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    rows = [dict(row) for row in source]
    if term_value is None:
        rows[0].pop("must_contain")
    else:
        rows[0]["must_contain"] = term_value
    root = tmp_path / label
    (root / "tests" / "fixtures").mkdir(parents=True)
    (root / "tests" / "fixtures" / "business_evaluation_100.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    assert checker.main(["--repo-root", str(root)]) == checker.EXIT_STRUCTURE, label
    captured = capsys.readouterr()
    assert str(rows[0]["id"]) in captured.err, "{0} 的报错必须点到题号：{1}".format(
        label, captured.err
    )
    assert "查无出处的行" not in captured.out


# ---------------------------------------------------------------------------
# ⑥ 反证刀 a / b / c / d / e
# ---------------------------------------------------------------------------


def test_counter_evidence_disabling_word_boundary_collapses_the_second_ruler(checker, monkeypatch):
    """刀 a：摘掉词边界（退回裸子串）⇒ 两把尺同数 + 分歧表变空 ⇒ 交叉对账必须红。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)

    def _no_boundary(term, boundary_text):
        needle = _bare(term)
        index = boundary_text.find(needle)
        return [] if index < 0 else [(index, len(needle))]

    monkeypatch.setattr(checker, "find_token_positions", _no_boundary)
    collapsed = checker.audit_calibers(rows, missing, corpus, corpus_raw)
    assert collapsed["divergence"] == [], "反例形状失效：摘掉词边界居然还有分歧"
    assert collapsed["semantic"]["row_count"] == collapsed["case"]["row_count"]
    with pytest.raises(AssertionError):
        _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, collapsed)


def test_counter_evidence_report_with_one_ruler_is_refused(checker):
    """刀 b：报告只带一把尺 ⇒ render 当场拒绝出数（StructureDrift），不许默默少一把。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    one_ruler = {"case": dict(audit["case"]), "tier_rule": audit["tier_rule"]}
    with pytest.raises(checker.StructureDrift, match="只留一把"):
        checker.render_caliber_block(one_ruler)
    with pytest.raises(checker.StructureDrift, match="只留一把"):
        checker.render_caliber_block({"case": dict(audit["case"])})
    with pytest.raises(TypeError):
        checker.render_report(
            missing, rows=len(rows), term_total=audit["entry_total"], corpus_desc="影子语料"
        )
    rendered = checker.render_report(
        missing,
        rows=len(rows),
        term_total=audit["entry_total"],
        corpus_desc="影子语料",
        audit=audit,
    )
    assert "件口径" in rendered and "语义口径" in rendered, "两把尺都必须在报告里出数"


def test_counter_evidence_buried_anchor_is_not_exempted_by_name(checker):
    """刀 c：把某枚锚词写死豁免 ⇒ 分歧表不再点名 ⇒ 逐枚点名断言必须红；模块里也不许有名单。"""
    rows, corpus, corpus_raw, _missing, audit = _view(checker)
    _assert_divergence_names_who_swallowed_it(audit, checker)
    assert audit["divergence"], "本树今天就有该点名的分歧；空表说明豁免名单已经进来了"
    exempted = {**audit, "divergence": [], "flips": []}
    with pytest.raises(AssertionError):
        _assert_the_divergence_table_is_not_silenced(exempted, rows, corpus_raw, checker)
    allowlists = [
        name
        for name, value in vars(checker).items()
        if not name.startswith("_")
        and isinstance(value, (list, tuple, set, frozenset, dict))
        and _holds_anchor_name(value, audit)
    ]
    assert allowlists == [], (
        "覆盖度工具里出现了以锚词为内容的名单 —— 豁免名单就是病灶本身：" + repr(allowlists)
    )


def _assert_the_divergence_table_is_not_silenced(audit, rows, corpus_raw, checker):
    """豁免形状的靶：该点名的埋没锚词必须一枚不少地点名出来。"""
    _case, _semantic, divergent, _total = _independent_calibers(
        rows, corpus_raw, checker.MUST_CONTAIN_FIELD
    )
    named = {(item["row_id"], item["term"]) for item in audit["divergence"]}
    assert named == set(divergent), "分歧表被清空/裁剪了：埋没锚词一枚都不许从账上消失"
    assert len(audit["divergence"]) == len(named), "分歧表里出现了重复条目"


def _holds_anchor_name(value, audit) -> bool:
    named = {item["term"].casefold() for item in audit["divergence"]}
    if not named:
        return False
    flat = list(value.values()) + list(value.keys()) if isinstance(value, dict) else list(value)
    for element in flat:
        if isinstance(element, str) and element.casefold() in named:
            return True
    return False


def test_glued_cjk_anchor_counts_as_provenance_in_both_rulers(checker, tmp_path, monkeypatch):
    """①的正面：中文锚词粘在中文里（中文没有词边界）也必须算出处，两把尺同判。"""
    rows, glued_root = _glued_shadow(tmp_path, checker, monkeypatch)
    _r, corpus, corpus_raw, _missing, audit = _view(checker, root=glued_root)
    cjk_hits = [item for item in audit["entries"] if item["tier"] == "cjk" and item["case_hit"]]
    assert len(cjk_hits) >= 20, "影子语料没造出成片的中文粘连命中，正证失效"
    assert all(item["semantic_hit"] for item in cjk_hits), (
        "粘在中文里的锚词被语义口径判没了 —— 词边界吃进中文，正是判据①的反面"
    )
    assert not [item for item in audit["divergence"] if item["tier"] == "cjk"], (
        "cjk 档条目进了分歧表：两把尺对中文的判定本该恒等"
    )
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)

    label = sorted(corpus)[0]
    spaced_text = _spaced(corpus_raw[label][1])
    for item in cjk_hits[:20]:
        needle = _bare(item["term"])
        index = spaced_text.find(needle)
        assert index >= 0, "影子语料里找不到这枚锚词：正证造形失效 " + repr(item["term"])
        assert not re.search(
            r"(?<!\w)" + re.escape(needle) + r"(?!\w)", spaced_text, re.UNICODE
        ), (
            "反例形状失效：粘连的中文锚词居然也能过 ``\\b`` 这一关，那这把刀就没有靶"
        )


def test_counter_evidence_unicode_word_boundary_would_harm_cjk_anchors(
    checker, tmp_path, monkeypatch
):
    """刀 d：把词边界推广到 Unicode 字母（``\b`` 那一类写法）并绕过分档 ⇒ 中文粘连命中判没 ⇒ 红。"""
    rows, glued_root = _glued_shadow(tmp_path, checker, monkeypatch)
    _r, corpus, corpus_raw, missing, audit = _view(checker, root=glued_root)
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)
    monkeypatch.setattr(checker, "contains_cjk", lambda text: False)
    monkeypatch.setattr(checker, "is_ascii_word_char", lambda char: char.isalnum())
    harmed = checker.audit_calibers(rows, missing, corpus, corpus_raw)
    hurt = [item for item in harmed["divergence"] if _tier(item["term"]) == "cjk"]
    assert hurt, "反例形状失效：这种写法居然没有误伤中文锚词"
    with pytest.raises(AssertionError):
        _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, harmed)


def test_counter_evidence_divergence_without_hit_forms_is_refused(checker, monkeypatch):
    """刀 e：分歧不交代命中形 ⇒ 空表由 audit_calibers 指名拒绝；伪造独立成词由点名断言咬红。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    assert audit["divergence"], "本树今天应有分歧可咬；空表说明前一格已被绕过"
    first = audit["divergence"][0]

    monkeypatch.setattr(checker, "describe_hit_forms", lambda term, documents, raw: [])
    with pytest.raises(checker.StructureDrift, match="一处命中形都指不出来"):
        checker.audit_calibers(rows, missing, corpus, corpus_raw)

    monkeypatch.setattr(
        checker,
        "describe_hit_forms",
        lambda term, documents, raw: [
            {
                "kind": "line",
                "path": documents[0],
                "label": documents[0],
                "raw_line_number": 1,
                "enclosing_token": _bare(term),
                "independent_word": True,
            }
        ],
    )
    lied = checker.audit_calibers(rows, missing, corpus, corpus_raw)
    assert lied["divergence"], "伪造命中形之后分歧条目还在，靶才对得上"
    with pytest.raises(AssertionError):
        _assert_divergence_names_who_swallowed_it(lied, checker)
    assert first["hit_forms"], "正证：正常路径下命中形本来就在账上"


# ---------------------------------------------------------------------------
# ⑤ 复核代价：第二把尺只重看真出现过锚词的篇，不许把全部语料重跑一遍
# ---------------------------------------------------------------------------


def test_second_ruler_only_reopens_documents_that_the_first_ruler_hit(checker):
    """语义口径的重扫面必须是件口径命中篇的子集，且严格小于全库（⑤不许劣化）。"""
    rows, corpus, corpus_raw, missing, audit = _view(checker)
    candidates: set = set()
    for row in rows:
        row_id = str(row["id"])
        for term in row[checker.MUST_CONTAIN_FIELD]:
            term_text = str(term)
            if _tier(term_text) != "ascii" or term_text in missing.get(row_id, []):
                continue
            candidates |= {
                label for label, text in corpus.items() if _bare(term_text) in text
            }
    built = set(audit["boundary_documents_built"])
    assert built <= candidates, "语义口径重看了件口径没命中的篇：那是把全部语料又扫了一遍"
    assert len(built) < audit["corpus_document_count"], (
        "两把尺的语料扫描面一样宽 = 第二把尺把第一把尺的活重做了一遍"
    )
    for item in audit["divergence"]:
        assert set(item["case_documents"]) <= built, (
            "分歧条目没有把它在件口径眼里命中的每一篇都重看过一遍，命中形不可信"
        )


def test_alternate_corpus_scope_still_reports_both_rulers(checker, capsys):
    """备选口径（--include-csv）也得出两把尺，且件口径行为保持不变（⑤）。"""
    assert checker.main(["--repo-root", str(REPO_ROOT), "--include-csv"]) == checker.EXIT_OK
    out = capsys.readouterr().out
    assert "件口径" in out and "语义口径" in out, "备选口径也必须两把尺一起报"
    rows, corpus, corpus_raw, missing, audit = _view(checker, include_csv=True)
    assert out.count("查无出处的行 = ") == 1
    assert "查无出处的行 = {0}".format(len(missing)) in out, "CSV 口径的件口径读数与函数不一致"
    _assert_two_rulers_agree_with_an_independent_ruler(checker, rows, corpus_raw, audit)
    _assert_divergence_names_who_swallowed_it(audit, checker)


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------


def _glued_shadow(tmp_path, checker, monkeypatch):
    """影子树：把题源里的中文锚词全部**粘在中文里**写进一篇语料（中文没有词边界）。

    「一页纸」「不需要打印」这类命中形态本来就该算出处，所以这棵树既给判据①做正证，
    也给刀 d 当靶：把词边界推广到 Unicode 字母之后，这些粘连命中会成片消失。
    """
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    field = checker.MUST_CONTAIN_FIELD
    cjk_terms = sorted(
        {
            str(term)
            for row in rows
            for term in row[field]
            if _tier(str(term)) == "cjk" and len(_bare(str(term))) >= 2
        }
    )
    assert len(cjk_terms) >= 20, "题源里两字以上的中文锚词太少，本用例的形状需随题源一起改写"
    body = "说明如下" + "".join("含{0}字样并且".format(term) for term in cjk_terms) + "完毕"
    root = _shadow_root(tmp_path / "glued", checker, {"glued.txt": body})
    monkeypatch.setattr(checker, "EXPECTED_CORPUS_TXT_COUNT", 1)
    return rows, root


def _ascii_terms(rows, field):
    """题源里全部 ascii 档锚词（按第二份实现现算；不抄题号也不抄词条名）。"""
    return sorted(
        {
            str(term)
            for row in rows
            for term in row[field]
            if _tier(str(term)) == "ascii"
        }
    )


def _shadow_root(tmp_path, checker, docs):
    """影子树：题源原样复制（规模闸照常有效），语料换成指定的几篇，篇数闸由用例改到同数。"""
    root = tmp_path / "shadow"
    (root / "tests" / "fixtures").mkdir(parents=True)
    shutil.copyfile(FIXTURE_105, root / checker.FIXTURE_REL)
    docs_dir = root / "documents"
    docs_dir.mkdir()
    for name, text in docs.items():
        (docs_dir / name).write_text(text, encoding="utf-8")
    return root