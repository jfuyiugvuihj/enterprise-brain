"""R94 常驻钉：评测证据覆盖度复算器必须永远给出审计文档记的那 29 条。

背景（数字本身见 docs/handoff/2026-09-19-eval-evidence-audit.md）：
  * §2.1 记「至少缺一个出处的行 = 29」，§3.2 记四桶分解 A 1 / B 8 / C 5 / D 15 = 29，
    附录 A 记每行缺的那个词条。此前这条数只活在一次性脚本里（be-r93/_audit/，未跟踪），
    而跟进单 §25.3 引用的 be-r34/r36q/verify_r66.py 根本不存在（§2.4 第 4 条）。
    本用例把「复算 == 文档」钉成仓库里的常驻断言。
  * 下面所有 golden 常量都是那份文档的**抄本**，不是独立结论。抄本与文档不一致时，
    test_golden_constants_still_match_the_audit_doc_text 会拿文档当场对质。

全程离线：只读仓内文本文件，零模型、零网络、零容器、零连库。
"""
import importlib.util
import json
import re
import shutil
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py"
AUDIT_DOC = REPO_ROOT / "docs" / "handoff" / "2026-09-19-eval-evidence-audit.md"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 口径漂移时失败信息里必须出现的句子（教学义务：不许只说 expected != got）。
TEACHING = "两处一起更新"

# --- golden：审计文档 §2.1 的 29 个题号（原样顺序） -------------------------------
MISSING_IDS_29 = (
    "doc-07 doc-14 doc-15 doc-17 chat-02 chat-08 chat-09 chat-11 chat-12 "
    "data-07 data-08 data-12 insight-05 insight-06 insight-07 approval-03 "
    "approval-05 scope-03 scope-04 scope-06 unsupported-01 unsupported-02 "
    "unsupported-03 unsupported-04 tool-03 report-03 report-07 report-08 report-09"
).split()

# --- golden：审计文档 §3.2 的四桶归桶 --------------------------------------------
BUCKET_IDS = {
    "A": "approval-05".split(),
    "B": "doc-07 doc-14 doc-15 doc-17 chat-02 chat-08 approval-03 report-07".split(),
    "C": "data-07 data-08 data-12 insight-05 insight-06".split(),
    "D": (
        "chat-09 chat-11 chat-12 insight-07 scope-03 scope-04 scope-06 "
        "unsupported-01 unsupported-02 unsupported-03 unsupported-04 tool-03 "
        "report-03 report-08 report-09"
    ).split(),
}
BUCKET_COUNTS = {"A": 1, "B": 8, "C": 5, "D": 15}

# --- golden：审计文档附录 A 的 题号 -> 缺的那个词条（29 行 / 25 个不同词条） ------
TERM_BY_ID = {
    "approval-05": "需补开发票",
    "approval-03": "无需超额审批",
    "chat-02": "之后",
    "chat-08": "不叠加",
    "doc-07": "计发",
    "doc-14": "离职结算",
    "doc-15": "不需要打印",
    "doc-17": "公司抬头",
    "report-07": "审批路径",
    "data-07": "前五",
    "data-08": "小计",
    "data-12": "变化率",
    "insight-05": "长期未处理",
    "insight-06": "超标率",
    "chat-09": "不矛盾",
    "chat-11": "800元",
    "chat-12": "无法确认",
    "insight-07": "不确定性",
    "report-03": "一页纸",
    "report-08": "未索引",
    "report-09": "继续生成",
    "scope-03": "超出可见范围",
    "scope-04": "需单独授权",
    "scope-06": "不可以",
    "tool-03": "重新生成",
    "unsupported-01": "无法确认",
    "unsupported-02": "无法确认",
    "unsupported-03": "无法确认",
    "unsupported-04": "无法确认",
}

#: 审计文档 §2.3 / §3.10 记的两个备选口径数。
CSV_CALIBER_ROWS = 29
PDF_CALIBER_ROWS = 27


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_eval_evidence_coverage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def no_network(monkeypatch):
    """离线是一句主张，所以得有机闸：任何 socket 动作都算失败。"""

    def _boom(*args, **kwargs):
        raise AssertionError("本用例禁止任何网络动作")

    monkeypatch.setattr(socket.socket, "__init__", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


def _run(checker, argv):
    return checker.main([str(arg) for arg in argv])


def _missing(checker, root=REPO_ROOT, **flags):
    rows = checker.load_rows(root / checker.FIXTURE_REL)
    corpus = checker.load_corpus(root, **flags)
    return checker.find_missing_terms(rows, corpus)


def _teaching(expected_ids, got_ids):
    return (
        "复算结果与审计文档 §2.1 / §3 记录的集合不一致。\n"
        "  文档记 {0} 条，本次复算得到 {1} 条。\n"
        "  文档有而复算没有: {2}\n  复算有而文档没记:   {3}\n"
        "{4}\n"
        "    (1) docs/handoff/2026-09-19-eval-evidence-audit.md 的 §2.1 题号清单、§3 四桶归桶、"
        "附录 A；\n"
        "    (2) tests/test_r94_eval_evidence_coverage.py 的 MISSING_IDS_29 / BUCKET_IDS / "
        "BUCKET_COUNTS / TERM_BY_ID，以及 scripts/check_eval_evidence_coverage.py 的口径常量。\n"
        "  只改一处 = 把口径漂移藏起来，这条断言存在的意义就是不让人这么干。"
    ).format(
        len(expected_ids),
        len(got_ids),
        " ".join(sorted(set(expected_ids) - set(got_ids))) or "(无)",
        " ".join(sorted(set(got_ids) - set(expected_ids))) or "(无)",
        TEACHING,
    )


def _assert_matches_pinned_29(got_ids):
    """那条"钉"本身。主用例走它，反证用例也用 pytest.raises 走它 —— 必须是同一条判定路径。"""
    assert sorted(got_ids) == sorted(MISSING_IDS_29), _teaching(MISSING_IDS_29, got_ids)


def _shadow_root(tmp_path, overrides):
    """造一棵影子仓库：题源原样复制，语料按 overrides 换掉若干篇的**正文**（篇数不变）。

    篇数不变是故意的 —— 只有规模闸不响，才能证明"覆盖度变了"是**钉**在管，
    而不是 fail-closed 顺手挡掉的。所有写入都落在 tmp_path 里，绝不碰真语料。
    """
    root = tmp_path / "shadow"
    (root / "tests" / "fixtures").mkdir(parents=True)
    shutil.copyfile(FIXTURE_105, root / "tests" / "fixtures" / "business_evaluation_100.jsonl")
    docs = root / "documents"
    docs.mkdir()
    for source in sorted((REPO_ROOT / "documents").glob("*.txt")):
        text = overrides.get(source.name)
        if text is None:
            shutil.copyfile(source, docs / source.name)
        else:
            (docs / source.name).write_text(text, encoding="utf-8")
    return root


def _audit_doc_missing_ids():
    """从审计文档 §2.1 那行原文里抠出题号，用来和上面的 golden 常量当场对质。"""
    doc = AUDIT_DOC.read_text(encoding="utf-8")
    line = next((l for l in doc.splitlines() if l.startswith("**29 个题号")), "")
    return re.findall(r"[a-z]+-\d+", line)


def _audit_doc_buckets():
    """从审计文档 §3.2 表格里抠出四桶，形如 {"A": (1, ["approval-05"]), ...}。"""
    doc = AUDIT_DOC.read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| \*\*([ABCD]) [^|]*\*\* \| \*\*(\d+)\*\* \| ([^|]*)\|$", doc, re.MULTILINE
    )
    return {name: (int(count), ids.strip().split()) for name, count, ids in rows}


# ---------------------------------------------------------------------------
# ① 可重跑 + ④ golden 口径
# ---------------------------------------------------------------------------

def test_recomputed_missing_ids_equal_the_29_recorded_in_the_audit_doc(checker, no_network):
    got = sorted(_missing(checker))
    _assert_matches_pinned_29(got)
    assert len(got) == 29


def test_row_count_equals_term_count_fingerprint(checker, no_network):
    """§2.2 的结构指纹：29 行各缺 1 词，行数 == 词条数。这条比 29 更难撞对。"""
    missing = _missing(checker)
    assert len(missing) == sum(len(terms) for terms in missing.values()), (
        "行数 != 词条数，口径指纹已破（§2.2）。若你确实补了语料或改了题，" + TEACHING
    )


def test_each_missing_row_is_missing_exactly_the_term_in_appendix_a(checker, no_network):
    missing = _missing(checker)
    assert missing == {key: [value] for key, value in TERM_BY_ID.items()}, _teaching(
        sorted(TERM_BY_ID), sorted(missing)
    )
    assert len({value for value in TERM_BY_ID.values()}) == 25


def test_four_bucket_counts_are_pinned_and_partition_the_29(checker, no_network):
    """四桶计数（A1 / B8 / C5 / D15）是钉住的常量，且必须无重叠地铺满复算得到的 29 条。"""
    assert {bucket: len(ids) for bucket, ids in BUCKET_IDS.items()} == BUCKET_COUNTS
    union = [item for ids in BUCKET_IDS.values() for item in ids]
    assert len(union) == len(set(union)) == 29, "四桶之间有重叠或总数不是 29，" + TEACHING
    assert sorted(union) == sorted(MISSING_IDS_29), "四桶并集与 §2.1 的 29 条不等，" + TEACHING
    got = sorted(_missing(checker))
    assert got == sorted(union), _teaching(union, got)


# ---------------------------------------------------------------------------
# 常量与文档双向对质：常量抄错、文档被重排，都得当场红
# ---------------------------------------------------------------------------

def test_golden_constants_still_match_the_audit_doc_text():
    doc_ids = _audit_doc_missing_ids()
    assert len(doc_ids) == 29, (
        "在审计文档 §2.1 里抠出的题号不是 29 个（看到 "
        + str(len(doc_ids))
        + "）。若你重排了那份文档，"
        + TEACHING
    )
    assert sorted(doc_ids) == sorted(MISSING_IDS_29), "本文件常量与审计文档 §2.1 不等，" + TEACHING

    buckets = _audit_doc_buckets()
    assert "".join(sorted(buckets)) == "ABCD", "§3.2 表格形状变了，四桶解析不出来，" + TEACHING
    assert {name: count for name, (count, _) in buckets.items()} == BUCKET_COUNTS, (
        "文档 §3.2 的四桶计数与本文件 BUCKET_COUNTS 不等，" + TEACHING
    )
    for name, (_, ids) in buckets.items():
        assert sorted(ids) == sorted(BUCKET_IDS[name]), (
            "桶 " + name + " 的题号与本文件常量不等，" + TEACHING
        )


# ---------------------------------------------------------------------------
# ② 口径写死在代码里（显式常量而非散在逻辑里），备选口径用开关表达
# ---------------------------------------------------------------------------

def test_caliber_is_expressed_as_explicit_constants(checker):
    assert checker.NORMALIZATION_STEPS == ("NFKC", "strip_all_whitespace", "casefold")
    assert checker.MATCH_MODE == "substring_within_single_document"
    assert checker.ROW_RULE == "row_counts_as_missing_if_any_term_missing"
    assert checker.CORPUS_DIR_REL == Path("documents")
    assert checker.CORPUS_TXT_GLOB == "*.txt"
    assert checker.CORPUS_DECODINGS == ("utf-8", "utf-8-sig", "gb18030")
    assert checker.FIXTURE_ENCODING == "utf-8-sig"
    # 三步都真的在函数里生效：全角转半角、去**所有**空白、大小写折叠。
    assert checker.normalize(" Ａ Ｂ c ") == "abc"
    assert checker.normalize("Word") == checker.normalize("word")


def test_expected_scale_constants_are_pinned_in_the_script(checker):
    assert (checker.EXPECTED_FIXTURE_ROWS, checker.EXPECTED_TERM_TOTAL) == (105, 121)
    assert checker.EXPECTED_CORPUS_TXT_COUNT == 95


def test_include_pdf_flag_reads_the_other_caliber_and_help_says_so(checker, capsys, no_network):
    assert _run(checker, ["--repo-root", REPO_ROOT]) == checker.EXIT_OK
    assert "查无出处的行 = 29" in capsys.readouterr().out

    assert _run(checker, ["--repo-root", REPO_ROOT, "--include-pdf"]) == checker.EXIT_OK
    pdf_out = capsys.readouterr().out
    assert "查无出处的行 = {0}".format(PDF_CALIBER_ROWS) in pdf_out, (
        "§3.10 记着：把 2 篇 PDF 算出处会变 " + str(PDF_CALIBER_ROWS)
        + "。对不上说明语料侧变了，" + TEACHING
    )
    listed = pdf_out.split("缺出处的题号")[1]
    for row_id in ("chat-02", "insight-07"):
        assert row_id not in listed, (
            "PDF 口径下 " + row_id + " 应被救回（§3.10），" + TEACHING
        )

    help_text = checker.build_parser().format_help()
    assert "另一种口径" in help_text and "主口径排除" in help_text, (
        "--help 必须写明 PDF 是另一种口径、主口径排除，否则下一个人会把 27 当成本件的失败"
    )


def test_include_csv_flag_leaves_the_number_alone(checker, capsys, no_network):
    """§2.3：把报销明细表.csv 当出处，0 行被救回，仍是 29。"""
    assert _run(checker, ["--repo-root", REPO_ROOT, "--include-csv"]) == checker.EXIT_OK
    assert "查无出处的行 = {0}".format(CSV_CALIBER_ROWS) in capsys.readouterr().out, (
        "§2.3 记着加不加 CSV 都是 " + str(CSV_CALIBER_ROWS) + "，" + TEACHING
    )


# ---------------------------------------------------------------------------
# ③ fail-closed：规模变了必须当场红，且不许把数字吐出来
# ---------------------------------------------------------------------------

def test_normal_run_exits_zero_and_prints_the_id_list(checker, capsys, no_network):
    assert _run(checker, ["--repo-root", REPO_ROOT]) == checker.EXIT_OK
    out = capsys.readouterr().out
    assert "查无出处的行 = 29" in out
    for row_id in ("approval-05", "unsupported-04", "report-09"):
        assert row_id in out, "题号清单里没有 " + row_id


def test_fail_closed_when_fixture_row_count_drifts(checker, capsys, monkeypatch):
    monkeypatch.setattr(checker, "EXPECTED_FIXTURE_ROWS", 104)  # 真实是 105
    assert _run(checker, ["--repo-root", REPO_ROOT]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "看到 105 行，期望 104 行" in captured.err, "报错必须说出它实际看到了什么"
    assert TEACHING in captured.err
    assert "查无出处的行" not in captured.out, "结构漂移时不许静默给出一个新数"


def test_fail_closed_when_term_total_drifts(checker, capsys, monkeypatch):
    monkeypatch.setattr(checker, "EXPECTED_TERM_TOTAL", 120)  # 真实是 121
    assert _run(checker, ["--repo-root", REPO_ROOT]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "看到 121 个，期望 120 个" in captured.err
    assert "查无出处的行" not in captured.out


def test_fail_closed_when_corpus_txt_count_drifts(checker, capsys, monkeypatch):
    monkeypatch.setattr(checker, "EXPECTED_CORPUS_TXT_COUNT", 94)  # 真实是 95
    assert _run(checker, ["--repo-root", REPO_ROOT]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "看到 95 篇，期望 94 篇" in captured.err
    assert TEACHING in captured.err
    assert "查无出处的行" not in captured.out, "补了语料也不许沿用旧口径闷声出数"


def test_fail_closed_when_corpus_directory_is_missing(checker, capsys, tmp_path):
    fake_root = tmp_path / "no-corpus"
    (fake_root / "tests" / "fixtures").mkdir(parents=True)
    (fake_root / "tests" / "fixtures" / "business_evaluation_100.jsonl").write_text(
        FIXTURE_105.read_text(encoding="utf-8-sig"), encoding="utf-8"
    )
    assert _run(checker, ["--repo-root", fake_root]) == checker.EXIT_STRUCTURE
    captured = capsys.readouterr()
    assert "语料目录不存在" in captured.err
    assert "chroma_db" in captured.err, "必须提示不许拿快照冒充语料（§3.9 / runbook P-9）"
    assert "查无出处的行" not in captured.out


def test_fail_closed_when_fixture_is_missing(checker, capsys, tmp_path):
    assert _run(checker, ["--repo-root", tmp_path]) == checker.EXIT_STRUCTURE
    assert "题源不存在" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 产物与零副作用
# ---------------------------------------------------------------------------

def test_json_output_matches_the_console_report(checker, capsys, tmp_path, no_network):
    target = tmp_path / "nested" / "no_provenance_r0.json"
    assert _run(checker, ["--repo-root", REPO_ROOT, "--json", target]) == checker.EXIT_OK
    assert "已写出" in capsys.readouterr().out
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == {key: [value] for key, value in TERM_BY_ID.items()}


def test_script_is_a_reader_not_a_business_dependency(checker):
    """本件是取证件：不许 import app.*、不许碰网络/子进程、不许把向量库当语料源。"""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert not re.search(r"^(from|import)\s+app\b", source, re.MULTILINE), "取证件不许依赖 app/"
    for banned in ("subprocess", "requests", "urllib", "httpx", "socket.", "chromadb"):
        assert banned not in source, "取证件不该出现 " + banned
    assert "def main" in source and '__name__ == "__main__"' in source

# ---------------------------------------------------------------------------
# 反证用例（常驻）：故意破坏覆盖度，钉必须红
#    两个方向都做 —— 把 29 条缺口人为填平、把已有出处人为抽走。
#    两棵影子树的 txt 篇数都还是 95，所以 fail-closed **不该**出手（用例里当场断言退出码 0）；
#    红只能由钉来给。少了这两条，本文件只是在复述文件内容，守不住 29 这条账。
# ---------------------------------------------------------------------------


def test_counter_evidence_saturated_corpus_turns_the_pin_red(checker, capsys, tmp_path, no_network):
    """反证一：拿一篇把**全部 121 个词条**都写进去的假语料顶掉一篇真语料 ⇒ 缺口变 0，钉必须红。

    这就是「补料补到覆盖度做满」的形状：题没动、篇数没动（仍 95，fail-closed 不该响），只有覆盖度动了。
    补的是全部词条而不只那 29 个，是为了不管被顶掉的那篇是不是别的词的唯一出处，缺口都必然归 0
    —— 否则这条反证会随语料形状偶然失效。
    """
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    all_terms = sorted({str(term) for row in rows for term in row[checker.MUST_CONTAIN_FIELD]})
    occurrences = sum(len(row[checker.MUST_CONTAIN_FIELD]) for row in rows)
    assert (occurrences, len(all_terms)) == (checker.EXPECTED_TERM_TOTAL, 105), "词条总数/去重数与本件口径不符，" + TEACHING
    victim = sorted(p.name for p in (REPO_ROOT / "documents").glob("*.txt"))[-1]
    shadow = _shadow_root(tmp_path, {victim: "伪造语料（反证用例） " + " ".join(all_terms)})

    assert _run(checker, ["--repo-root", shadow]) == checker.EXIT_OK, "规模没变，fail-closed 不该拦"
    out = capsys.readouterr().out
    assert "查无出处的行 = 0" in out, "伪造语料没能把 29 条缺口填平，反证本身失效"
    assert sorted(_missing(checker, root=shadow)) == []
    with pytest.raises(AssertionError, match=TEACHING):
        _assert_matches_pinned_29([])


def test_counter_evidence_removed_evidence_turns_the_pin_red(checker, capsys, tmp_path, no_network):
    """反证二：把某个已覆盖词条的**唯一出处**那一篇清空 ⇒ 缺口只会变多，钉同样必须红。"""
    corpus = checker.load_corpus(REPO_ROOT)
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    already_missing = _missing(checker)
    target = None
    for row in rows:
        row_id = str(row["id"])
        if row_id in already_missing:
            continue
        for term in row[checker.MUST_CONTAIN_FIELD]:
            sources = [name for name, text in corpus.items() if checker.normalize(str(term)) in text]
            if len(sources) == 1:
                target = (row_id, str(term), sources[0])
                break
        if target:
            break
    assert target is not None, (
        "语料里找不到任何「唯一出处」词条，这条反证需随语料形状一起改写，" + TEACHING
    )
    row_id, term, source = target

    shadow = _shadow_root(tmp_path, {source: "本篇正文已清空（反证用例）"})
    assert _run(checker, ["--repo-root", shadow]) == checker.EXIT_OK, "规模没变，fail-closed 不该拦"
    printed = [
        line for line in capsys.readouterr().out.splitlines() if "查无出处的行 = " in line
    ]
    assert len(printed) == 1, "脚本没按约定格式出数，反证本身失效"
    rows_now = int(printed[0].split("= ")[1])
    # 一篇文档可能是若干词条共同的唯一出处，所以只断言"严格变多"，不钉死成 30。
    assert rows_now > 29, "清空 " + source + " 之后缺口没有变多"

    got = sorted(_missing(checker, root=shadow))
    assert row_id in got, "被清空的 " + row_id + " 没有变成缺口"
    assert set(already_missing) < set(got), "新缺口应当严格包住旧的 29 条"
    with pytest.raises(AssertionError, match=TEACHING):
        _assert_matches_pinned_29(got)


# ---------------------------------------------------------------------------
# 语料目录的卫生（09-19 并主干后补）—— 本件读的是目录，脏一次就全体红一次
# ---------------------------------------------------------------------------

def test_the_corpus_directory_holds_no_upload_litter(checker):
    """documents/ 兼作上传落地区，混进残片之后，95 篇就不是同一个 95 篇了。

    09-19 并主干当天主树实测 115 个 .txt（多出的 20 个是 browser_ / codex-upload- /
    kb_policy_ / qa_ 之流的 __vN 版本副本），data/ 实测 7 个 csv ⇒ 本文件 11 条用例在干净树
    绿、在这棵树上红。根因不在脚本，在目录。R49 早已在自己文件里写下同一句话（取 git 清单
    而不是目录列表），本件按主口径就是目录列表，所以这条钉负责让残片别悄悄回来。
    """
    txt = sorted(path.name for path in (REPO_ROOT / "documents").glob("*.txt"))
    assert len(txt) == checker.EXPECTED_CORPUS_TXT_COUNT, (
        "documents/ 里的 .txt 不再是主口径那 " + str(checker.EXPECTED_CORPUS_TXT_COUNT)
        + " 篇。多出来的是上传/浏览器测试残片：把它们移出语料目录，别就地删 —— 没进 git 的那几份"
        "是 KB 里对应行的唯一源字节，移走前先确认那一行还在服务器上。"
    )

    pdf = sorted(path.name for path in (REPO_ROOT / "documents").glob("*.pdf"))
    assert len(pdf) == 2, (
        "--include-pdf 那个备选口径钉的是 2 篇 PDF（§3.10 的 " + str(PDF_CALIBER_ROWS)
        + " 行），多一篇算出来的就不是那个数"
    )

    csv = sorted(path.name for path in (REPO_ROOT / "data").glob("*.csv"))
    assert csv == ["报销明细表.csv"], (
        "data/ 里只有明细表是语料，其余 csv 是浏览器测试残片 ⇒ --include-csv 口径会被它们动过"
    )
