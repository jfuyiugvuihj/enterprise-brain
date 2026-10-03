# -*- coding: utf-8 -*-
"""R597 · 裁定词表只许有一处定义（账面单：本格只收账面与实际不一致，不改任何产品行为）。

病（凭据）：``docs/testing/r593-verdict-must-follow-rows-2026-10-03.md:144-158`` 与 R593 交回时点名的
四处散文——词表从三词变四词之后，它们仍按旧三词手抄裁定词或手抄「再生件第几行」。手抄的账不会跟着
真源改口：R593 把那一格按现读改了判，抄在它散文里的那一枚词当天就变成假话。

真源只有一枚：``scripts/r483_empty_tables_triage.py`` 的 ``VERDICTS``（词表）与 ``TRIAGE``（逐格裁定），
对外由它的 ``--json`` 交回。本文件**一枚裁定词都不拼**：词表、逐格裁定、词的形状（首段/末段）全部从
真源现取——一把量「不许手抄词表」的尺自己抄一份词表，就是本单要拦的那个形状。

| 判据 | 钉 |
|---|---|
| ① 四处散文改派生 | test_the_product_tree_and_the_gate_name_no_verdict_word / test_every_named_prose_spot_points_at_the_true_source |
| ② 在册断言不放宽 | 本文件不改任何在册件；改口前后逐字对照与同名件复跑数见 ``docs/testing/r597-*.md`` |
| ③ 词表只有一处定义 | test_no_source_file_hands_out_its_own_word_list / test_only_the_true_source_defines_the_vocabulary / test_a_file_may_mention_the_words_only_by_pointing_at_the_true_source / test_no_word_of_the_verdict_shape_is_outside_the_true_vocabulary |
| ④ 反证（常驻两把） | test_a_shadow_that_hands_out_its_own_word_list_is_the_only_one_named / test_dropping_a_word_from_the_true_source_blinds_every_reference |
| ⑤ 纸面 | test_the_paper_declares_the_header_and_names_every_spot |
| 派生不是摆设（结构钉） | test_the_gate_reaches_the_word_only_through_its_handle |
| 行号引用天生过期 | test_no_source_file_cites_a_line_of_the_generated_ledger |
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TRIAGE_REL = "scripts/r483_empty_tables_triage.py"
GATE_REL = "scripts/r577_demo_sample_seed.py"
LEDGER_DOC = "docs/testing/r483-empty-tables-2026-09-29.md"
PAPER_GLOB = "r597-*.md"
PAPER_HEADER = "本格只收账面与实际不一致，不改任何产品行为"
#: 真源散文里的中文数字（只为核它那一句词表计数，不为了自己造一份账）。
CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CODE_LAYERS = ("app", "scripts", "tests")
DOC_LAYER = "docs"
TRIAGE_POINTER = "r483_empty_tables_triage"


def load_module(rel: str, name: str, root: Path | None = None):
    """把某一枚在册件读进内存（只读）：每枚模块用独立名字，影子刀不许污染真盘面。"""
    base = REPO if root is None else root
    spec = importlib.util.spec_from_file_location(name, base / rel)
    assert spec and spec.loader, rel
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TRIAGE = load_module(TRIAGE_REL, "r483_triage_for_r597")
#: 词表只从这里取。本文件后面所有判据都对着这一枚元组算，包括「多少个词」。
WORDS = tuple(TRIAGE.VERDICTS)
#: 那把闸也现取一枚（只读）：本文件判它「取词的把手只有一枚」，不复制它的判定逻辑。
GATE = load_module(GATE_REL, "r597_gate_for_r597")
#: 词的形状也从词表派生（首段 + 末段），用来抓「第五个自造词」而不必抄一份词表。
WORD_FIRSTS = tuple(sorted({word.split("_")[0] for word in WORDS}))
WORD_LASTS = tuple(sorted({word.split("_")[-1] for word in WORDS}))
#: 形状 = 首段 + 至少一枚中间段 + 末段。🔴 词表里只有两段的那些词刻意落在射程之外：
#: ``no_owner`` 这类普通词组在别的词表里合法在册（现取一例
#: ``tests/test_r492_live_claim_boundary.py``），把它当裁定词就是「用一把量不到的尺宣布达标」。
WORD_SHAPE_RE = re.compile(
    r"\b(?:" + "|".join(WORD_FIRSTS) + ")_[a-z][a-z_]*_(?:" + "|".join(WORD_LASTS) + r")\b"
)
#: 词表里符合这一枚形状的那些词（尺子空转检查对着它核，不对着整个词表核）。
SHAPE_COVERED = tuple(word for word in WORDS if word.count("_") >= 2)
#: 再生件的行号引用：``<那枚生成物>:104`` 这种坐标在再生之后必漂（R593 §七已点名同一格病）。
LEDGER_LINE_CITE_RE = re.compile(re.escape(LEDGER_DOC) + r"[:：][0-9]+")


def text_of(path: Path) -> str:
    """读文本并把 CRLF 折成 LF：判据看的是内容，不是行结束符形状。"""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def source_lines(root: Path, rel: str) -> list[str]:
    return text_of(root / rel).split("\n")


def py_files(root: Path = REPO, layers=CODE_LAYERS) -> list[str]:
    found = []
    for layer in layers:
        base = root / layer
        found += [path.relative_to(root).as_posix() for path in sorted(base.rglob("*.py"))
                  if "__pycache__" not in path.parts]
    return found


def distinct_words(text: str) -> set:
    return {word for word in WORDS if word in text}


def word_lists_in_source(root: Path = REPO) -> dict:
    """抓「自己拼了一份词表清单」：同一行、同一枚字符串字面量、或同一枚容器里出现 ≥2 枚不同的裁定词。

    真源豁免（它是唯一定义处，它自己的 ``VERDICTS``/``ZERO_ROW_VERDICTS`` 正是这一枚尺要保的东西）。
    """
    findings: dict[str, list] = {}
    for rel in py_files(root):
        if rel == TRIAGE_REL:
            continue
        text = text_of(root / rel)
        hits = []
        for number, line in enumerate(text.split("\n"), 1):
            if len(distinct_words(line)) >= 2:
                hits.append(("line", number, sorted(distinct_words(line))))
        try:
            tree = ast.parse(text)
        except SyntaxError:  # 语法都过不去的文件不该由本尺放行，但它不是「手抄词表」这一格
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if len(distinct_words(node.value)) >= 2:
                        hits.append(("literal", node.lineno, sorted(distinct_words(node.value))))
                elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                    words = [element.value for element in node.elts
                             if isinstance(element, ast.Constant) and isinstance(element.value, str)]
                    joined = distinct_words(" ".join(words))
                    if len(joined) >= 2:
                        hits.append(("container", node.lineno, sorted(joined)))
        if hits:
            findings[rel] = sorted(hits)
    return findings


def coined_words(root: Path = REPO, layers=CODE_LAYERS + (DOC_LAYER,)) -> list:
    """词的形状之内、词表之外的自造词（第五个说法）。形状与词表都从真源派生。"""
    offenders = []
    rels = [rel for rel in py_files(root, layers=tuple(lay for lay in layers if lay != DOC_LAYER))]
    if DOC_LAYER in layers:
        rels += [path.relative_to(root).as_posix()
                 for path in sorted((root / DOC_LAYER).rglob("*.md"))]
    for rel in rels:
        for number, line in enumerate(text_of(root / rel).split("\n"), 1):
            for token in WORD_SHAPE_RE.findall(line):
                if token not in WORDS:
                    offenders.append((rel, number, token))
    return offenders


def ledger_line_cites(root: Path = REPO) -> list:
    """代码层（app/scripts/tests）对再生件的「第几行」引用。

    🔴 射程写在代码层：纸面（含本单的纸）要交出改前原文做逐字对照，引用旧坐标正是它的活，
    不该被这一把尺当成罪证——那是 R593 §七 与本单的分界：代码不许抄坐标，纸必须留原文。
    """
    cites = []
    for rel in py_files(root):
        for number, line in enumerate(text_of(root / rel).split("\n"), 1):
            if LEDGER_LINE_CITE_RE.search(line):
                cites.append((rel, number))
    return cites


def words_by_layer(root: Path = REPO) -> dict:
    """③ 要的扫描读数：四层各点名「提到裁定词的文件 -> 提及枚数」，与是否指向真源。"""
    readings = {}
    for layer in CODE_LAYERS + (DOC_LAYER,):
        rows = {}
        if layer == DOC_LAYER:
            paths = sorted((root / layer).rglob("*.md"))
        else:
            paths = [root / rel for rel in py_files(root, (layer,))]
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            text = text_of(path)
            mentions = sum(text.count(word) for word in WORDS)
            if mentions:
                rows[path.relative_to(root).as_posix()] = {
                    "mentions": mentions,
                    "points_at_true_source": TRIAGE_POINTER in text,
                }
        readings[layer] = rows
    return readings


#: ① 派工词点名的四处散文。行号一律不作判据：位置由符号与锚语现取（同一棵树一天能漂 150 行）。
#: (文件, 取法, 锚)——``comment`` 取包住锚语的整段注释，``function`` 取函数源码，``module_docstring`` 取模块文档串。
PROSE_SPOTS = (
    ("app/rag/retrieval_pipeline.py", "comment", "产品问答道的检索留痕（R536）"),
    ("scripts/r577_demo_sample_seed.py", "function", "attributed_alerts"),
    ("scripts/r577_demo_sample_seed.py", "function", "require_attributed_alerts"),
    ("tests/test_r577_demo_sample_seed.py", "function", "test_unattributed_alert_rows_are_refused"),
    ("tests/test_r536_retrieval_completed_on_product_lane.py", "module_docstring", ""),
    ("tests/test_r536_single_emission_point.py", "module_docstring", ""),
)


def region_of(root: Path, rel: str, kind: str, anchor: str) -> str:
    """按符号取那一处散文的原文：取不到就抛——「找不到」必须是一种红，不是一种跳过。"""
    text = text_of(root / rel)
    if kind == "module_docstring":
        doc = ast.get_docstring(ast.parse(text))
        if not doc:
            raise AssertionError(rel + " 没有模块文档串，本单的判据无处可落")
        return doc
    if kind == "function":
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == anchor:
                segment = ast.get_source_segment(text, node)
                if segment:
                    return segment
        raise AssertionError(rel + " 里找不到函数 " + anchor)
    if kind == "comment":
        lines = text.split("\n")
        try:
            start = next(index for index, line in enumerate(lines) if anchor in line)
        except StopIteration:
            raise AssertionError(rel + " 里找不到锚语 " + anchor) from None
        top = start
        while top > 0 and lines[top - 1].lstrip().startswith("#"):
            top -= 1
        bottom = start
        while bottom + 1 < len(lines) and lines[bottom + 1].lstrip().startswith("#"):
            bottom += 1
        return "\n".join(lines[top:bottom + 1])
    raise AssertionError("未知的取法：" + kind)


# ==================================================================== ①/③ 判据
def test_the_product_tree_and_the_gate_name_no_verdict_word():
    """``app/**`` 与那把闸件的源码里一枚裁定词都不许出现：产品码不替台账抄答案。"""
    offenders = {}
    for rel in py_files(REPO, ("app",)) + [GATE_REL]:
        found = sorted(distinct_words(text_of(REPO / rel)))
        if found:
            offenders[rel] = found
    assert offenders == {}, offenders


def test_every_named_prose_spot_points_at_the_true_source():
    """① 逐处点名：四处散文各交出原文，既不含手抄的裁定词，也不含对再生件的行号引用。"""
    report = []
    for rel, kind, anchor in PROSE_SPOTS:
        region = region_of(REPO, rel, kind, anchor)
        report.append((rel, kind, anchor, len(distinct_words(region))))
        assert distinct_words(region) == set(), (rel, kind, anchor, region[:200])
        assert not LEDGER_LINE_CITE_RE.search(region), (rel, kind, anchor, region[:200])
        assert TRIAGE_POINTER in region or "guarded_verdict" in region, (rel, region[:200])
    assert len(report) == len(PROSE_SPOTS), report


def test_no_source_file_hands_out_its_own_word_list():
    """③ 词表只有一处定义：任何非真源的源文件自己拼一份词表清单（≥2 枚不同的词），当场红。"""
    assert word_lists_in_source() == {}, word_lists_in_source()


def test_only_the_true_source_defines_the_vocabulary():
    """③ 定义处计数：把 ≥2 枚裁定词写成一份字面量容器的文件，全仓只许有真源那一枚。

    顺带核真源自己散文里那句词表计数：它必须等于 ``len(VERDICTS)``——连「有几个词」都不许靠人记。
    """
    containers = []
    for rel in py_files(REPO):
        for node in ast.walk(ast.parse(text_of(REPO / rel))):
            if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                continue
            values = [element.value for element in node.elts
                      if isinstance(element, ast.Constant) and isinstance(element.value, str)]
            if len(distinct_words(" ".join(values))) >= 2:
                containers.append((rel, node.lineno))
    assert {rel for rel, _ in containers} == {TRIAGE_REL}, containers
    claim = re.search(r"裁定只有([一二两三四五六七八九]|\d+)个?词", text_of(REPO / TRIAGE_REL))
    assert claim is not None, "真源里那句词表计数不见了：尺读不到出处，不去猜"
    digits = claim.group(1)
    counted = int(digits) if digits.isdigit() else CHINESE_DIGITS[digits]
    assert counted == len(WORDS), (claim.group(0), WORDS)


def _shape_catches_every_true_word():
    """尺子不许空转：射程内的每一枚在册词都要被形状认回来，一枚都不能漏。"""
    return set(WORD_SHAPE_RE.findall(" / ".join(WORDS))) == set(SHAPE_COVERED)

def test_a_file_may_mention_the_words_only_by_pointing_at_the_true_source():
    """③ 扫描读数（app/scripts/tests）：提到裁定词的文件必须指名真源；``app/**`` 与 ``scripts/**`` 里除真源一枚都不许提。"""
    readings = words_by_layer(REPO)
    assert readings["app"] == {}, readings["app"]
    assert sorted(readings["scripts"]) == [TRIAGE_REL], readings["scripts"]
    silent = {rel: row for rel, row in readings["tests"].items() if not row["points_at_true_source"]}
    assert silent == {}, (silent, readings["tests"])


def test_no_word_of_the_verdict_shape_is_outside_the_true_vocabulary():
    """不许出现第五个自造词：形状从词表派生（首段 + 中间段 + 末段），形状之内、词表之外的字点名。

    🔴 这一把尺的射程写在 ``SHAPE_COVERED`` 里，只有两段的词落在射程之外（理由见形状那一段注释）；
    射程内的词必须枚枚认得回来，否则这一把就是空转——射程之外那一格由本纸如实登记。
    """
    assert coined_words() == [], coined_words()
    assert _shape_catches_every_true_word(), (SHAPE_COVERED, WORD_FIRSTS, WORD_LASTS)



def test_no_source_file_cites_a_line_of_the_generated_ledger():
    """再生件的行号会漂：代码层的源文件不许写「那张台账第几行」这种坐标（射程见上）。"""
    assert ledger_line_cites() == [], ledger_line_cites()


def test_the_gate_reaches_the_word_only_through_its_handle():
    """那把闸只许通过一枚把手取词（结构钉）：把手之外再有一处碰 ``TRIAGE``/``VERDICTS`` 就红。"""
    text = text_of(REPO / GATE_REL)
    tree = ast.parse(text)
    chains = {}

    def walk(node, ancestors):
        for child in ast.iter_child_nodes(node):
            chain = ancestors
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chain = ancestors + [child.name]
            chains[id(child)] = chain
            walk(child, chain)

    walk(tree, [])
    touching = sorted({tuple(chains.get(id(node), ()))
                       for node in ast.walk(tree)
                       if isinstance(node, ast.Attribute) and node.attr in ("TRIAGE", "VERDICTS")})
    assert touching == [("guarded_verdict",)], touching
    handlers = [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "guarded_verdict"]
    assert len(handlers) == 1, len(handlers)
    assert chains[id(handlers[0])] == ["require_attributed_alerts"], chains[id(handlers[0])]
    assert "def guarded_verdict" in text and "def triage_tool" in text, text[:200]


# ==================================================================== ④ 反证（常驻两把）
def _copy_for_shadow(shadow: Path, rel: str) -> Path:
    target = shadow / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / rel, target)
    return target


def test_a_shadow_that_hands_out_its_own_word_list_is_the_only_one_named(tmp_path):
    """反证④第一把（常驻版）：把旧散文连手抄词表塞回产品码注释，尺必须只点名那一枚文件。

    影子端正控先跑：同一棵影子树在没动之前交回空清单——否则这一把等于没动东西。
    """
    shadow = tmp_path / "handcopied"
    pipeline = _copy_for_shadow(shadow, "app/rag/retrieval_pipeline.py")
    assert word_lists_in_source(shadow) == {}, "影子端正控就不干净"

    original = pipeline.read_bytes()
    before = hashlib.sha256(original).hexdigest()[:12]
    text = pipeline.read_text(encoding="utf-8")
    anchor = "# scripts/" + TRIAGE_POINTER + ".py::TRIAGE"
    assert text.count(anchor) == 1, text.count(anchor)
    stale = ("# 裁定原文在 " + LEDGER_DOC + ":104 —— 词表只有 "
             + " / ".join(WORDS[:3]) + " 三词；")
    pipeline.write_text(text.replace(anchor, stale, 1), encoding="utf-8", newline="")
    after = hashlib.sha256(pipeline.read_bytes()).hexdigest()[:12]
    findings = word_lists_in_source(shadow)
    cites = ledger_line_cites(shadow)
    pipeline.write_bytes(original)
    restored = hashlib.sha256(pipeline.read_bytes()).hexdigest()[:12]

    assert before != after, (before, after)
    assert restored == before and pipeline.read_bytes() == original, (before, restored)
    assert list(findings) == ["app/rag/retrieval_pipeline.py"], findings
    assert findings["app/rag/retrieval_pipeline.py"][0][2] == sorted(WORDS[:3]), findings
    assert [rel for rel, _ in cites] == ["app/rag/retrieval_pipeline.py"], cites
    assert word_lists_in_source(shadow) == {}, "还原之后尺必须重新闭嘴"


def test_dropping_a_word_from_the_true_source_blinds_every_reference(tmp_path):
    """反证④第二把（常驻版）：把真源里那一枚在册的裁定词删掉，引用处必须跟着红。

    引用是真派生而不是摆设，判据就这一条：真源少一枚词 ⇒ 那把闸的把手取不到词 ⇒ 在册钉红。
    全程只在 ``tmp_path`` 的副本上动手，真源与盘面上的 ``scripts/`` 一字节都不改（正控同样落影子端）。
    """
    import test_r577_demo_sample_seed as pins

    guarded_cell = GATE.GUARDED_TABLE
    live_word = str(TRIAGE.TRIAGE[guarded_cell]["verdict"])
    assert live_word in WORDS, (live_word, WORDS)

    control = tmp_path / "control"
    _copy_for_shadow(control, TRIAGE_REL)
    gate_rel_path = _copy_for_shadow(control, GATE_REL)
    control_module = load_module(GATE_REL, "r597_control_gate", control)
    assert control_module.ROOT == control.resolve(), control_module.ROOT
    assert control_module.guarded_verdict() == live_word
    original_seed = pins.seed
    pins.seed = control_module
    try:
        pins.test_unattributed_alert_rows_are_refused()
    finally:
        pins.seed = original_seed

    bladed = tmp_path / "bladed"
    shadow_triage = _copy_for_shadow(bladed, TRIAGE_REL)
    shadow_gate = _copy_for_shadow(bladed, GATE_REL)
    triage_bytes = shadow_triage.read_bytes()
    before = hashlib.sha256(triage_bytes).hexdigest()[:12]
    triage_text = triage_bytes.decode("utf-8")
    line = next(row for row in triage_text.splitlines() if row.startswith("VERDICTS ="))
    dropped = "VERDICTS = (" + ", ".join(repr(w) for w in WORDS if w != live_word) + ")"
    shadow_triage.write_bytes(triage_text.replace(line, dropped, 1).encode("utf-8"))
    after = hashlib.sha256(shadow_triage.read_bytes()).hexdigest()[:12]
    assert before != after and after != hashlib.sha256(
        (REPO / TRIAGE_REL).read_bytes()).hexdigest()[:12], (before, after)

    gate = load_module(GATE_REL, "r597_bladed_gate", bladed)
    assert gate.ROOT == bladed.resolve(), gate.ROOT
    with pytest.raises(RuntimeError) as blind:
        gate.guarded_verdict()
    assert TRIAGE_POINTER in str(blind.value) and "词表" in str(blind.value), str(blind.value)

    pins.seed = gate
    try:
        with pytest.raises(RuntimeError):
            pins.test_unattributed_alert_rows_are_refused()
    finally:
        pins.seed = original_seed

    shadow_triage.write_bytes(triage_bytes)
    restored = hashlib.sha256(shadow_triage.read_bytes()).hexdigest()[:12]
    assert restored == before and shadow_triage.read_bytes() == triage_bytes, (before, restored)
    assert (REPO / TRIAGE_REL).read_bytes() == shadow_triage.read_bytes()
    assert shadow_gate.read_bytes() == (REPO / GATE_REL).read_bytes()
    assert word_lists_in_source(bladed) == {}, word_lists_in_source(bladed)


# ==================================================================== ⑤ 纸面
def test_the_paper_declares_the_header_and_names_every_spot():
    """⑤ 本单的纸：抬头那句「只收账面、不改产品行为」在场，① 的四处逐一点名，③ 的扫描读数在场。"""
    papers = sorted((REPO / DOC_LAYER / "testing").glob(PAPER_GLOB))
    assert len(papers) == 1, papers
    text = text_of(papers[0])
    assert PAPER_HEADER in text, text.split("\n")[:6]
    for rel, _kind, anchor in PROSE_SPOTS:
        assert rel in text, rel
        if anchor:
            assert anchor in text, anchor
    assert "docs/handoff" not in text or "写域" in text
    for layer in CODE_LAYERS + (DOC_LAYER,):
        assert layer in text, layer
