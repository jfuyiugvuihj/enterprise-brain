#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""评测集 must_contain「出处覆盖度」复算器（R94 常驻件）。

【它回答的唯一问题】
    把 tests/fixtures/business_evaluation_100.jsonl 里 105 题的 must_contain 词条，逐个拿到
    documents/*.txt 语料里找**字面**出处，有几行至少缺一个出处？在 9626b7d 上这个数 = 29
    （与 R66 结案自述一致，也与审计文档 §2.1 的题号清单逐字相同）。

【为什么它得长在仓库里】
    跟进单 §25.3 引用的复算脚本 be-r34/r36q/verify_r66.py 在盘上根本不存在（审计文档 §2.4
    第 4 条已核实），而 R93 的等价实现躺在未跟踪的 be-r93/_audit/recount.py 里，随那棵工作树
    一朝蒸发 ⇒ 「29」这个数至今没有一个可重跑的入库工件。本件把它变成常驻可跑的脚本，
    并由 tests/test_r94_eval_evidence_coverage.py 钉住题号集合与四桶计数。

【三条硬规矩】
    1. 只读取证：零模型调用、零网络、零连库、零起服务、零改动仓库内容。产物只在显式指定的
       --json / --provenance 路径上落盘。
    2. 口径不商量：判据全在下面「口径常量」区块里，以显式常量 + 注释表达。要换口径请用开关
       （--include-pdf / --include-csv），不要改常量。
    3. fail-closed：输入规模与本口径钉死的期望值不一致时**拒绝给数**，非 0 退出并打印它实际
       看到了什么。这个数字变了必须让人当场知道，不许静默吐出一个新数。

【退出码】
    0 = 正常出数；1 = 命令行用法错误；2 = 结构漂移（题源/语料规模与口径不符）或开关依赖缺失。

【R437：两把尺同时出数（件口径 / 语义口径）】
    §1.5 那条「归一化后子串即算有出处」的判据是账上的尺（**件口径**），本件一字未动，
    tests/test_r94_eval_evidence_coverage.py 钉的还是它。但它有一处会说谎的形状：拉丁锚词
    会因为在更长的词里出现过就被判「有出处」—— 例如锚词 Word 命中在 password / your_password
    内部，那枚「导出成 Word」的题就被算成有出处，而语料里根本没有独立成词的 Word。
    语义口径因此另起一把尺，分档规则只有一条、按锚词自身判（不认题号、没有豁免名单）：
      ascii 档：要独立成词（两侧不挨 ASCII 字母/数字/下划线）才算有出处；
      cjk  档：保持子串语义 —— 中文没有词边界，「一页纸」「不需要打印」照旧必须能命中。
    两把尺一起报，分歧逐枚点名（哪枚题、哪枚锚词、被哪个整 token 吞了、在语料哪一行）。
    🔴 只准加严不许放宽：语义口径的缺口集合 ⊇ 件口径的缺口集合，出现反向翻转就拒绝出数。
    关掉一把、把两把合成一把、给某枚锚词开豁免名单 —— 都是本件明令不许的形状（判据②）。

【用法】
    python scripts/check_eval_evidence_coverage.py
    python scripts/check_eval_evidence_coverage.py --json _r94/no_provenance_r0.json
    python scripts/check_eval_evidence_coverage.py --provenance _r401tmp/anchor_provenance.json
    python scripts/check_eval_evidence_coverage.py --include-pdf
    python scripts/check_eval_evidence_coverage.py --caliber-json _r437/calibers.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# 口径常量 —— 逐条抄自 docs/handoff/2026-09-19-eval-evidence-audit.md §1 主规则 R0。
# 这些值不是"默认参数"，是**判据本身**：改动其中任何一个，算出来的就不再是 29 那个口径。
# ---------------------------------------------------------------------------

#: §1.1 题源。文件名里的 100 是历史名，实为 105 行（runbook §11.1 已备案）。
FIXTURE_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
#: §1.1 题源编码：带 BOM 时也能读出干净的首个 id，故 utf-8-sig。
FIXTURE_ENCODING = "utf-8-sig"
#: §1.1 词条字段名。判分口径见 app/quality/eval.py 的 _is_correct（逐项子串对答案文本）。
MUST_CONTAIN_FIELD = "must_contain"

#: §1.2 语料目录。
CORPUS_DIR_REL = Path("documents")
#: §1.2 语料**只算** *.txt。PDF 与 xlsx 排除的理由见 --help 的口径分歧段（§3.10）。
CORPUS_TXT_GLOB = "*.txt"
#: §3.10 备选口径才读的扩展名，主口径不读。
PDF_GLOB = "*.pdf"
#: §1.7 主规则里 data/ 下的表**不算出处**；--include-csv 才读它（读了仍是 29，见 §2.3）。
DATA_DIR_REL = Path("data")
DATA_CSV_GLOB = "*.csv"

#: §1.3 语料解码试探顺序，与 be-r34/r36q/build_corpus.py 一致；本树 95 篇无一失败。
CORPUS_DECODINGS = ("utf-8", "utf-8-sig", "gb18030")

#: §1.4 归一化三步，**顺序固定、不可调换、不可省略**。审计文档 §2.3 的 6x2 网格已经量过：
#: 换成"不去空白"或"不 casefold"等替代口径会得到 30 而不是 29，所以这里不留调参余地。
NORMALIZATION_STEPS = ("NFKC", "strip_all_whitespace", "casefold")
#: 步骤 2 的实现：去掉**所有**空白（正则全局替换），不是 str.strip()。
WHITESPACE_PATTERN = re.compile(r"\s+")

#: §1.5 匹配方式：归一化后的词条是归一化后的**单篇**文档文本的子串，即算「有出处」。
#: 按单篇而非全库拼接，是为了不让跨文档边界的偶然拼接冒充出处。不做分词/同义改写/编辑距离
#: ——一旦允许同义改写，B 桶整桶消失，那是替业主裁定，本件不做。
MATCH_MODE = "substring_within_single_document"
#: §1.6 计行规则：一行里**任一个**词条查无出处，该行即计入（与 diff55.py 的 any(...) 同）。
ROW_RULE = "row_counts_as_missing_if_any_term_missing"

#: ---------------------------------------------------------------------------
#: R437 词边界档 —— 件口径那把尺一个字节不动，旁边另加一把语义口径的尺。
#: 病灶：§1.5 的裸子串会把「Word」从「password」里救出来 —— 量具替题目说了一句
#: 「有出处」，而语料里没有任何一处这枚锚词是独立成词的。不修它，覆盖度这张账就是假的。
#: 🔴 件口径（MATCH_MODE）仍是账上那把尺：tests/test_r94_eval_evidence_coverage.py 与审计文档
#:    §2.1 钉的都是它，本件不重算它、不放宽它、也不拿它替语义口径出数。两把尺同时出数，
#:    一把也不关（R401 判据②：不许置空 must_contain、不许删题、不许加排除名单）。
#: ---------------------------------------------------------------------------
#: 语义口径下 ASCII 档锚词的匹配方式；CJK 档锚词沿用上面的 MATCH_MODE（子串语义照旧）。
LATIN_MATCH_MODE = "word_boundary_token_within_single_document"
CJK_MATCH_MODE = MATCH_MODE
#: 两档唯一的分支规则：按**锚词自身**归一化之后含不含 CJK 字符分档。不认题号、不设特例、
#: 没有豁免名单 —— 中文没有词边界，「一页纸」「不需要打印」这类命中形态本来就该算命中。
TERM_TIER_RULE = "cjk_term_keeps_substring_ascii_term_requires_word_boundary"
#: CJK 字符类（中日韩文字 + 中文标点 + 全角形式），只用来回答「这枚锚词归哪一档」。
CJK_CHARACTER_PATTERN = re.compile(
    r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]"
)
#: 词边界的定义：锚词两侧紧邻的字符不许是 ASCII 字母/数字/下划线，其余（含 CJK、标点、
#: 空白折出来的分隔符、串头串尾）一律算边界。故意不用 ``\b`` —— ``\b`` 认 CJK 为单词字符，
#: 会把中文正文里独立成词的「PDF」（如「导出PDF」）判成某个词的内部，那是把判据反面写进生产代码。
ASCII_WORD_CHAR_PATTERN = re.compile(r"[0-9a-z_]")
#: 语义口径的归一化把空白折成这枚分隔符（件口径是把空白直接删掉；两者看到的字符集一致）。
#: \u0000 不属于任何自然语言或标识符字符 ⇒「词边界命中 ⊆ 裸子串命中」是一条可证的包含关系，
#: audit_calibers() 对它当场自检，破了就拒绝出数，而不是悄悄多报或少报一枚。
BOUNDARY_SEPARATOR = "\u0000"
#: 分歧表里一枚锚词最多列几处命中形；全量在 --caliber-json 里，一条不少。
MAX_HIT_FORMS_IN_REPORT = 8

# --- fail-closed 的期望规模：变了必须当场报错，不许静默给新数 ----------------------
#: §1.1 评测集行数。
EXPECTED_FIXTURE_ROWS = 105
#: §1.1 must_contain 词条总数。
EXPECTED_TERM_TOTAL = 121
#: §1.2 语料 txt 篇数（含 R66 9f2f869 补的 制度与口径登记表.txt）。
EXPECTED_CORPUS_TXT_COUNT = 95

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_STRUCTURE = 2

#: 漂移报错里反复出现的那句话 —— 只改一处 = 口径漂移藏起来。
UPDATE_BOTH_PLACES = (
    "补了语料或改了题之后，两处一起更新：\n"
    "    (1) docs/handoff/2026-09-19-eval-evidence-audit.md 的 §2.1 题号清单与 §3 四桶归桶；\n"
    "    (2) scripts/check_eval_evidence_coverage.py 的口径常量 / "
    "tests/test_r94_eval_evidence_coverage.py 的 golden 常量。"
)


class StructureDrift(RuntimeError):
    """输入与本脚本钉死的主口径不一致 —— 拒绝出数。

    message 里必须自带「看到了什么 / 期望什么 / 该同步更新哪两处」，这样人或测试把它打印出来
    就能自解释，不需要再去翻源码。
    """


def normalize(text: str) -> str:
    """按 NORMALIZATION_STEPS 归一化。题面词与语料文本两侧走的是同一个函数。"""
    folded = unicodedata.normalize("NFKC", text)   # 步骤 1：兼容字符/全半角统一
    folded = WHITESPACE_PATTERN.sub("", folded)    # 步骤 2：去掉所有空白
    return folded.casefold()                       # 步骤 3：大小写折叠


def contains_cjk(text: str) -> bool:
    """这串文本里有没有 CJK 字符 —— 判据①那条分界线只看字符本身，不看它是哪道题。"""
    return bool(CJK_CHARACTER_PATTERN.search(text))


def term_tier(term: str) -> str:
    """两档匹配唯一的分支点：cjk 档保持子串语义 / ascii 档要独立成词。

    档位判的是**归一化之后的锚词自身**。像「800元」这种混排词落在 cjk 档：它含中文，
    中文侧本来没有词边界可用，硬套词边界只会把真命中判没 —— 那是判据①明令不许的形状。
    """
    return "cjk" if contains_cjk(normalize(term)) else "ascii"


def normalize_word_spaced(text: str) -> str:
    """语义口径的归一化：与 normalize() 同一条三步流水，只把第 2 步「删掉空白」换成
    「空白折成一枚分隔符」。

    为什么要另起一份而不是改 normalize()：件口径那把尺是账（tests/test_r94_* 钉着它），
    一个字符也不能动。这份变体看到的字符与 normalize() 完全一致，只是词的接缝还留着 ——
    于是「词边界命中 ⊆ 裸子串命中」成了可证的包含关系，语义口径只准多报缺、不准少报缺。
    第 3 步 casefold 照旧在场（摘掉它就是反证刀 a 的靶子，不是可交付形态）。
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = WHITESPACE_PATTERN.sub(BOUNDARY_SEPARATOR, folded)
    return folded.casefold()


def is_ascii_word_char(char: str) -> bool:
    """这一格字符算不算「同一个拉丁词的下一位」。"""
    return bool(ASCII_WORD_CHAR_PATTERN.match(char))


def is_word_delimited(text: str, start: int, end: int) -> bool:
    """[start, end) 这一段在 text 里是不是独立成词：两侧都不挨 ASCII 字母/数字/下划线。

    串头/串尾算边界；CJK、标点、空白折出来的分隔符也都算边界（见 ASCII_WORD_CHAR_PATTERN）。
    """
    left = text[start - 1] if start > 0 else ""
    right = text[end] if end < len(text) else ""
    return not (left and is_ascii_word_char(left)) and not (right and is_ascii_word_char(right))


def enclosing_token(text: str, start: int, end: int) -> str:
    """把命中形两侧继续扩张到词边界，返回**吞掉锚词的那个整 token**（例如 password）。

    分歧表要说清「锚词被谁吞进去」靠的就是它。它只在归一化文本上量，不改写语料、不改判据。
    """
    left = start
    while left > 0 and is_ascii_word_char(text[left - 1]):
        left -= 1
    right = end
    while right < len(text) and is_ascii_word_char(text[right]):
        right += 1
    return text[left:right]


def find_token_positions(term: str, boundary_text: str) -> list[tuple[int, int]]:
    """锚词在一篇「保留词接缝」的归一化文本里全部**独立成词**命中的 (字符起点, 长度)。

    与 find_term_positions() 的分工写清在此：那枚是 R401 取证件的字节区间口径（裸子串，
    本单一字未动），这枚只回答「独立成词了吗」，不产凭据，两枚不许互相代用。
    游标步进 1 而不是整词长：passwordpassword 这类重叠命中也得数到，少一处就少一分证据。
    """
    needle = refuse_empty_needle(term, normalize_word_spaced(term))
    positions: list[tuple[int, int]] = []
    cursor = 0
    while True:
        index = boundary_text.find(needle, cursor)
        if index < 0:
            return positions
        end = index + len(needle)
        if is_word_delimited(boundary_text, index, end):
            positions.append((index, len(needle)))
        cursor = index + 1


def refuse_empty_needle(term: str, needle: str) -> str:
    """归一化之后是空串的锚词必须**指名报错**（判据④）。

    空串在子串语义下命中一切，在词边界语义下一处都不命中 —— 两种都是量具说谎；
    而「跳过这一枚」是第三种：它会让缺口数悄悄变小。
    """
    if not needle:
        raise StructureDrift(
            "锚词 {0!r} 归一化之后是空串：它要么命中一切、要么一处不中，两种都是假话。"
            "指名报错，不许静默跳过。".format(term)
        )
    return needle


def read_corpus_bytes(path: Path) -> bytes:
    """读语料原始字节；读不出就**指名文件**报错（判据④：少一篇语料就不是同一张账）。

    「这一篇打不开」若被当成「这一篇没有出处」，缺口数会平白多几枚；若被当成「跳过」，
    缺口数会平白少几枚。两种都不可复算，所以只能当场拒绝出数。
    """
    try:
        return path.read_bytes()
    except OSError as exc:
        raise StructureDrift(
            "语料文件读不出：{0}（{1}）。本件不在缺了一篇语料的树上出数，也不许把它当空气跳过。".format(
                path, exc
            )
        )


def decode_text_bytes(raw: bytes, source: str = "<未知来源>") -> str:
    """§1.3：按 CORPUS_DECODINGS 顺序试解码，取第一个成功的；全失败**指名文件**抛 StructureDrift。"""
    for encoding in CORPUS_DECODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StructureDrift(
        "语料解码失败：{0} —— 依次试过 {1} 都不通。本脚本不猜编码，猜了就不可复算。".format(
            source, " / ".join(CORPUS_DECODINGS)
        )
    )


# ---------------------------------------------------------------------------
# 输入装载 —— 每一处规模核对不过就 StructureDrift
# ---------------------------------------------------------------------------

def load_rows(fixture_path: Path) -> list[dict]:
    """读评测集，并核对 §1.1 的四个结构事实：行数、id 唯一、must_contain 非空、词条总数。"""
    if not fixture_path.is_file():
        raise StructureDrift("题源不存在：{0}。没有它就没有口径可言。".format(fixture_path))
    lines = [
        line
        for line in fixture_path.read_text(encoding=FIXTURE_ENCODING).splitlines()
        if line.strip()
    ]
    if len(lines) != EXPECTED_FIXTURE_ROWS:
        raise StructureDrift(
            "题源行数对不上主口径：看到 {0} 行，期望 {1} 行（{2}）。\n{3}".format(
                len(lines), EXPECTED_FIXTURE_ROWS, fixture_path, UPDATE_BOTH_PLACES
            )
        )
    rows = [json.loads(line) for line in lines]
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("id"))
        counts[key] = counts.get(key, 0) + 1
    duplicated = sorted("{0} x{1}".format(k, v) for k, v in counts.items() if v > 1)
    if duplicated:
        raise StructureDrift("题源 id 不唯一：{0}".format("、".join(duplicated)))
    empty_term = [str(row.get("id")) for row in rows if not row.get(MUST_CONTAIN_FIELD)]
    if empty_term:
        raise StructureDrift(
            "题源有 {0} 行 must_contain 为空（{1}），与 §1.1「105 行全部带非空 must_contain」不符。".format(
                len(empty_term), " ".join(empty_term)
            )
        )
    term_total = sum(len(row[MUST_CONTAIN_FIELD]) for row in rows)
    if term_total != EXPECTED_TERM_TOTAL:
        raise StructureDrift(
            "must_contain 词条总数对不上主口径：看到 {0} 个，期望 {1} 个。\n{2}".format(
                term_total, EXPECTED_TERM_TOTAL, UPDATE_BOTH_PLACES
            )
        )
    for row in rows:  # 判据④：锚词字段本身有毛病必须指名报错，不许在复算里当空气跳过
        row_id = str(row.get("id"))
        for index, term in enumerate(row[MUST_CONTAIN_FIELD], start=1):
            if not isinstance(term, str):
                raise StructureDrift(
                    "题源 {0} 的第 {1} 个 must_contain 不是字符串（看到 {2!r}）。"
                    "本件不替它猜一个词形：猜了就不可复算。".format(row_id, index, term)
                )
            if not normalize(term):
                raise StructureDrift(
                    "题源 {0} 的第 {1} 个 must_contain 归一化之后是空串（原文 {2!r}）："
                    "空锚词既不可能有出处、也不可能当出处，指名报错，不许静默跳过。".format(
                        row_id, index, term
                    )
                )
    return rows


def read_pdf_text(pdf_path: Path) -> str:
    """--include-pdf 专用。pypdf 不可用时抛 StructureDrift（退出码 2），不静默退回 txt 口径。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise StructureDrift(
            "--include-pdf 需要 pypdf，本机 import 失败：{0}。主口径不需要它。".format(exc)
        )
    chunks = []
    try:
        for page in PdfReader(str(pdf_path)).pages:
            chunks.append(page.extract_text() or "")
    except Exception as exc:  # pypdf 的解析异常名目很多，报出是哪一个文件比按类别分更有用（判据④）
        raise StructureDrift(
            "--include-pdf 读不出语料：{0}（{1}）。备选口径也不许在缺了一篇语料的树上出数。".format(
                pdf_path, exc
            )
        )
    return "\n".join(chunks)


def corpus_scope(directory: Path, pattern: str) -> list[Path]:
    """Return the files this audit may read: the corpus git tracks, not the ambient directory.

    A working tree is not a deployment. documents/ doubles as the upload landing area
    (H16), so a live checkout collects versioned copies of every file anyone ever posted
    -- the main tree held 115 .txt against 95 tracked ones on 09-19, and 7 csv in data/
    against 1. Debris is absent on a customer machine, so it must not move this number in
    either direction: neither rescue a term nor trip the count gate. That is the standing
    hygiene rule recorded in the human-gates file (钉版本化清单，禁止吃 ambient 目录), and
    tests/test_r49_corpus_calibration.py already reads the corpus the same way. Where git
    cannot answer -- an export, or the shadow trees this file's own cases build -- the
    disk glob is the scope instead.
    """
    disk = sorted(directory.glob(pattern))
    try:
        listing = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-z", "--", pattern],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return disk
    if listing.returncode != 0:
        return disk
    names = {name.decode("utf-8") for name in listing.stdout.split(b"\0") if name}
    if not names:
        return disk
    on_disk = {path.name for path in disk}
    vanished = sorted(name for name in names if name not in on_disk)
    if vanished:
        raise StructureDrift(
            "git 跟踪的语料在盘上找不到：{0}。把文件放回去，或者说明它去哪了——跟踪中的语料"
            "凭空消失，正是本件要防的那件事。".format("、".join(vanished))
        )
    return sorted(directory / name for name in names)


def _corpus_entries(
    root: Path,
    *,
    include_pdf: bool = False,
    include_csv: bool = False,
) -> list[tuple[str, Path, str]]:
    """按口径装载语料，返回 [(文件标签, 仓内相对路径, 原始文本)]。

    主口径（两个开关都不开）只读 documents/*.txt 的 git 跟踪集，且必须正好
    EXPECTED_CORPUS_TXT_COUNT 篇；工作树里没跟踪的残片不算语料（见 corpus_scope）。

    R401 抽出这一层是为了「派生出处」：出处地址必须落在**原始字节**上（行号、归一化后
    字节区间都得从同一份文本现算），所以取证件得同时留得住原文，不能只留归一化后的残骸。
    归一化规则一个字没动 —— 主口径 load_corpus() 现在只是本函数的一层薄包装。
    """
    corpus_dir = root / CORPUS_DIR_REL
    if not corpus_dir.is_dir():
        raise StructureDrift(
            "语料目录不存在：{0}。本脚本不会退回任何缓存/快照冒充语料——上一轮废跑的根因就是\n"
            "  拿宿主 chroma_db 快照当语料真相源（审计文档 §3.9、runbook P-9）。".format(corpus_dir)
        )
    txt_files = corpus_scope(corpus_dir, CORPUS_TXT_GLOB)
    if len(txt_files) != EXPECTED_CORPUS_TXT_COUNT:
        raise StructureDrift(
            "语料 txt 篇数对不上主口径：看到 {0} 篇，期望 {1} 篇（{2}）。\n{3}".format(
                len(txt_files), EXPECTED_CORPUS_TXT_COUNT, corpus_dir, UPDATE_BOTH_PLACES
            )
        )
    entries = [
        (
            path.name,
            path.relative_to(root),
            decode_text_bytes(read_corpus_bytes(path), str(path)),
        )
        for path in txt_files
    ]
    if include_pdf:
        for path in corpus_scope(corpus_dir, PDF_GLOB):
            entries.append(
                (
                    "{0} [PDF 备选口径]".format(path.name),
                    path.relative_to(root),
                    read_pdf_text(path),
                )
            )
    if include_csv:
        for path in corpus_scope(root / DATA_DIR_REL, DATA_CSV_GLOB):
            entries.append(
                (
                    "{0} [CSV 备选口径]".format(path.name),
                    path.relative_to(root),
                    decode_text_bytes(read_corpus_bytes(path), str(path)),
                )
            )
    return entries


def load_corpus(
    root: Path,
    *,
    include_pdf: bool = False,
    include_csv: bool = False,
) -> dict[str, str]:
    """R94 原口径读法：{文件标签: 归一化后的文本}。判据与返回值一字节未改。"""
    return {
        label: normalize(raw)
        for label, _path, raw in _corpus_entries(
            root, include_pdf=include_pdf, include_csv=include_csv
        )
    }


def load_corpus_raw(
    root: Path,
    *,
    include_pdf: bool = False,
    include_csv: bool = False,
) -> dict[str, tuple[Path, str]]:
    """R401 派生读法：{文件标签: (仓内相对路径, 原始文本)}。读的文件集与主口径同一个。"""
    return {
        label: (path, raw)
        for label, path, raw in _corpus_entries(
            root, include_pdf=include_pdf, include_csv=include_csv
        )
    }


def find_term_positions(term: str, normalized_text: str) -> list[tuple[int, int]]:
    """一个词条在**归一化后文本**里的全部 (utf-8 字节起点, 字节长度) 区间。

    地址口径写死在这里，因为它就是甲案的凭据格式：偏移量数的是 normalize() 输出串再
    encode("utf-8") 的字节，不是原始文件的字节 —— 原始文件里同一个词挨不挨空白/全半角
    都不固定，归一化之后的串才是可复算的地址（与 §1.4 的三步规则同一把尺）。
    utf-8 自同步 ⇒ 命中必落在字符边界；真解不开或解回来的不是这个词，当场 StructureDrift，
    绝不吐一个「看着对」的位置给下游当出处。
    """
    needle = refuse_empty_needle(term, normalize(term))
    encoded = normalized_text.encode("utf-8")
    needle_bytes = needle.encode("utf-8")
    positions: list[tuple[int, int]] = []
    cursor = 0
    while True:
        index = encoded.find(needle_bytes, cursor)
        if index < 0:
            return positions
        chunk = encoded[index : index + len(needle_bytes)]
        try:
            decoded = chunk.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StructureDrift(
                "归一化字节区间 {0}+{1} 解不出 utf-8：位置口径与文本对不上，派生作废（{2}）".format(
                    index, len(needle_bytes), exc
                )
            )
        if decoded != needle:
            raise StructureDrift(
                "归一化字节区间 {0}+{1} 解回来是 {2!r}，不是词条 {3!r}：utf-8 自同步假设破了".format(
                    index, len(needle_bytes), decoded, needle
                )
            )
        positions.append((index, len(needle_bytes)))
        cursor = index + len(needle_bytes)


def derive_term_provenance(term: str, corpus_raw: dict[str, tuple[Path, str]]) -> list[dict]:
    """从语料**现取**一个词条的出处：篇路径 + 命中的原始行号 + 归一化后 utf-8 字节区间。

    这是 R401 甲案「禁手抄」的执行体：锚词的出处只能由本函数产出。它不判断"该不该算出处"
    （那是 §1.5 的 MATCH_MODE 与 §1.7 的语料集，一个字没改），它只回答"这个词在语料的哪里"。
    同一词命中多篇/多行时全部如实列出，由调用方选，选完还得被 tests/test_r401_* 复算一遍。
    """
    needle = refuse_empty_needle(term, normalize(term))
    records = []
    for label in sorted(corpus_raw):
        path, raw = corpus_raw[label]
        positions = find_term_positions(term, normalize(raw))
        if not positions:
            continue
        lines = [
            number
            for number, line in enumerate(raw.splitlines(), start=1)
            if needle in normalize(line)
        ]
        records.append(
            {
                "term": term,
                "path": path.as_posix(),
                "label": label,
                "raw_line_numbers": lines,
                "normalized_byte_ranges": [
                    {"start": start, "length": length} for start, length in positions
                ],
            }
        )
    return records


def derive_provenance_for_rows(rows: list[dict], corpus_raw: dict[str, tuple[Path, str]]) -> dict:
    """题源里每一个 must_contain 词条的派生出处，按词条去重后一次性算完。"""
    seen: list[str] = []
    visited = set()
    for row in rows:
        for term in row[MUST_CONTAIN_FIELD]:
            key = str(term)
            if key not in visited:
                visited.add(key)
                seen.append(key)
    return {term: derive_term_provenance(term, corpus_raw) for term in seen}


# ---------------------------------------------------------------------------
# 复算
# ---------------------------------------------------------------------------

def find_missing_terms(rows: list[dict], corpus: dict[str, str]) -> dict[str, list[str]]:
    """返回 {题号: [查无出处的词条, ...]}，按 ROW_RULE 计行、MATCH_MODE 匹配。"""
    documents = list(corpus.values())
    missing: dict[str, list[str]] = {}
    for row in rows:
        bad = [
            str(term)
            for term in row[MUST_CONTAIN_FIELD]
            if not any(normalize(str(term)) in text for text in documents)
        ]
        if bad:
            missing[str(row["id"])] = bad
    return missing


def find_provenance_documents(term: str, corpus: dict[str, str]) -> list[str]:
    """件口径眼里「这枚锚词在哪几篇有裸子串出处」—— 只为语义复核圈定该重看哪几篇。

    先问件口径、再开边界文本，是守住判据⑤那张性能账的前提：95 篇里只有真出现过锚词的
    那几篇需要重看一遍词的接缝，其余一篇都不碰（这个「碰了几篇」的数由 audit_calibers
    如实报在 boundary_documents_built 里，用例钉的是它，不是墙上时钟）。
    """
    needle = refuse_empty_needle(term, normalize(term))
    return [label for label in sorted(corpus) if needle in corpus[label]]


def describe_hit_forms(
    term: str,
    documents: list[str],
    corpus_raw: dict[str, tuple[Path, str]],
) -> list[dict]:
    """逐处交代「锚词在原始语料里被谁吞进去」：文件 + 原始行号 + 吞掉它的整 token。

    枚枚要有下落（判据④⑥e）：
      * 行内找得到的，给出整 token，并说明它这一处到底独立成词没有；
      * 篇级确实命中、却一行都指不出来的，点名「跨行拼接」，不许让这一处凭空消失。
    """
    needle = refuse_empty_needle(term, normalize_word_spaced(term))
    forms: list[dict] = []
    for label in documents:
        path, raw = corpus_raw[label]
        found_in_lines = 0
        for number, line in enumerate(raw.splitlines(), start=1):
            boundary_line = normalize_word_spaced(line)
            cursor = 0
            while True:
                index = boundary_line.find(needle, cursor)
                if index < 0:
                    break
                end = index + len(needle)
                found_in_lines += 1
                forms.append(
                    {
                        "kind": "line",
                        "path": path.as_posix(),
                        "label": label,
                        "raw_line_number": number,
                        "enclosing_token": enclosing_token(boundary_line, index, end),
                        "independent_word": is_word_delimited(boundary_line, index, end),
                    }
                )
                cursor = index + 1
        if found_in_lines == 0:
            forms.append(
                {
                    "kind": "cross_line_only",
                    "path": path.as_posix(),
                    "label": label,
                    "raw_line_number": None,
                    "enclosing_token": None,
                    "independent_word": False,
                    "note": "篇级命中，但没有任何一行能单独容下这枚锚词（跨行拼接出来的命中）",
                }
            )
    return forms


def audit_calibers(
    rows: list[dict],
    case_missing: dict[str, list[str]],
    corpus: dict[str, str],
    corpus_raw: dict[str, tuple[Path, str]],
) -> dict:
    """两把尺同时出数 + 逐枚点名分歧 + 全部锚词条目的 before/after（判据②③⑦）。

    件口径 = 传进来的 case_missing（find_missing_terms 的原样结果，本函数一个字不重算它）；
    语义口径 = 在它之上**只准加严**：
      * cjk 档锚词：判定与件口径恒等（中文没有词边界，子串语义照旧）；
      * ascii 档锚词：件口径判「有出处」的那几篇里，必须至少有一处独立成词才仍然算数。

    🔴 四条自检不过就拒绝出数（StructureDrift）—— 一把会说谎的第二把尺比没有第二把尺更坏：
      1. 不许出现「缺出处 → 有出处」的反向翻转（加严只能单向，判据③）；
      2. 不许出现 cjk 档分歧（分档规则说了中文走子串，判据①）；
      3. 分歧条目必须拿得出命中形，指不出「被谁吞了」就不许交（判据④⑥e）；
      4. 两把尺的读数必须都在场，缺任何一把都由 render_report 当场拒绝（判据②⑥b）。
    """
    boundary_cache: dict[str, str] = {}
    entries: list[dict] = []
    for row in rows:
        row_id = str(row["id"])
        absent = set(case_missing.get(row_id, ()))
        for term in row[MUST_CONTAIN_FIELD]:
            term_text = str(term)
            tier = term_tier(term_text)
            case_hit = term_text not in absent
            semantic_hit = case_hit
            case_documents: list[str] = []
            if tier == "ascii" and case_hit:
                case_documents = find_provenance_documents(term_text, corpus)
                semantic_hit = False
                for label in case_documents:
                    if label not in boundary_cache:
                        boundary_cache[label] = normalize_word_spaced(corpus_raw[label][1])
                    if find_token_positions(term_text, boundary_cache[label]):
                        semantic_hit = True
                        break
            entries.append(
                {
                    "row_id": row_id,
                    "term": term_text,
                    "tier": tier,
                    "case_hit": case_hit,
                    "semantic_hit": semantic_hit,
                    "case_documents": case_documents,
                    "changed": case_hit != semantic_hit,
                }
            )

    semantic_missing: dict[str, list[str]] = {}
    for entry in entries:
        if not entry["semantic_hit"]:
            semantic_missing.setdefault(entry["row_id"], []).append(entry["term"])

    loosened = [entry for entry in entries if not entry["case_hit"] and entry["semantic_hit"]]
    if loosened:
        raise StructureDrift(
            "语义口径把 {0} 枚锚词从「缺出处」翻成了「有出处」（{1}）：两把尺的关系是加严，"
            "不是放宽。出现这一条说明词边界实现写坏了，拒绝出数。".format(
                len(loosened),
                "、".join("{0}/{1}".format(e["row_id"], e["term"]) for e in loosened),
            )
        )
    cjk_divergent = [entry for entry in entries if entry["tier"] == "cjk" and entry["changed"]]
    if cjk_divergent:
        raise StructureDrift(
            "cjk 档锚词出现了分歧（{0}）：中文没有词边界，判据①要求两把尺对它们的判定恒等。"
            "要么分档规则被写坏了，要么词边界吃到了中文 —— 两种都拒绝出数。".format(
                "、".join("{0}/{1}".format(e["row_id"], e["term"]) for e in cjk_divergent)
            )
        )

    divergence: list[dict] = []
    for entry in entries:
        if not entry["changed"]:
            continue
        forms = describe_hit_forms(entry["term"], entry["case_documents"], corpus_raw)
        if not forms:
            raise StructureDrift(
                "分歧条目 {0}（题 {1}）在件口径眼里命中了 {2} 篇，却一处命中形都指不出来："
                "把分歧藏起来正是本单要治的病灶，拒绝出数。".format(
                    entry["term"], entry["row_id"], len(entry["case_documents"])
                )
            )
        item = dict(entry)
        item["hit_forms"] = forms
        divergence.append(item)

    case_row_ids = sorted(case_missing)
    semantic_row_ids = sorted(semantic_missing)
    return {
        "tier_rule": TERM_TIER_RULE,
        "case": {
            "match_mode": MATCH_MODE,
            "missing_by_row": case_missing,
            "row_ids": case_row_ids,
            "row_count": len(case_row_ids),
            "term_count": sum(len(terms) for terms in case_missing.values()),
        },
        "semantic": {
            "latin_match_mode": LATIN_MATCH_MODE,
            "cjk_match_mode": CJK_MATCH_MODE,
            "row_ids": semantic_row_ids,
            "row_count": len(semantic_row_ids),
            "term_count": sum(len(terms) for terms in semantic_missing.values()),
            "missing_by_row": semantic_missing,
        },
        "entries": entries,
        "entry_total": len(entries),
        "ascii_entries": sum(1 for entry in entries if entry["tier"] == "ascii"),
        "cjk_entries": sum(1 for entry in entries if entry["tier"] == "cjk"),
        "flips": [entry for entry in entries if entry["changed"]],
        "divergence": divergence,
        "corpus_document_count": len(corpus),
        "boundary_documents_built": sorted(boundary_cache),
    }


def render_caliber_block(audit: dict) -> list[str]:
    """把两把尺的读数、逐枚分歧、翻转面对账写成报告行（判据②③⑥b/⑥e 的输出面）。

    🔴 两把尺一把也不关：件口径排在前面（账上那把尺），语义口径紧跟其后，分歧枚枚点名。
    这里的措辞刻意避开「查无出处的行 = 」和「缺出处的题号」这两枚串 —— 它们各是
    tests/test_r94_eval_evidence_coverage.py 的解析锚点（一把尺只许出一行、题号清单只许有
    一份），多出现一次就会把那条钉带偏；双口径的数走「至少缺一个锚词出处的题」这个说法。
    """
    for key, name in (("case", "件口径"), ("semantic", "语义口径")):
        view = audit.get(key)
        if not isinstance(view, dict) or "row_count" not in view:
            raise StructureDrift(
                "报告里 {0}（字段 {1}）这把尺的读数不在位：双口径只留一把 = 把分歧抹平，"
                "拒绝出数。两把尺必须一起交（判据②）。".format(name, key)
            )
    case_view = audit["case"]
    semantic_view = audit["semantic"]
    divergence = audit["divergence"]
    flips = audit["flips"]
    built = audit["boundary_documents_built"]
    out = [
        "",
        "  两把尺同时出数（R437 词边界；一把也不关，也不合成一把）：",
        "    件口径   ：{0} —— 至少缺一个锚词出处的题 = {1}，缺的锚词 = {2}".format(
            case_view["match_mode"], case_view["row_count"], case_view["term_count"]
        ),
        "    语义口径 ：{0}".format(audit["tier_rule"]),
        "              ascii 档按 {0}，cjk 档按 {1}（中文没有词边界，判定与件口径恒等）".format(
            semantic_view["latin_match_mode"], semantic_view["cjk_match_mode"]
        ),
        "              —— 同一套语料上加严复核后 = {0}，缺的锚词 = {1}".format(
            semantic_view["row_count"], semantic_view["term_count"]
        ),
        "    两尺关系：语义口径只准在件口径之上加严（件的缺口集合 ⊆ 语义的缺口集合）；"
        "本次分歧 {0} 枚，枚枚见下".format(len(divergence)),
        "    复核代价：件口径扫全部 {0} 篇语料，语义口径只对 {1} 篇重看词的接缝：{2}".format(
            audit["corpus_document_count"],
            len(built),
            "、".join(built) or "(无)",
        ),
    ]
    if divergence:
        out += [
            "",
            "  分歧来源（件口径判「有出处」、语义口径判「没有」的锚词；一枚都不许藏）：",
        ]
        for item in divergence:
            forms = item["hit_forms"]
            out.append(
                "    题 {0}  锚词 {1}  档位 {2}".format(
                    item["row_id"], item["term"], item["tier"]
                )
            )
            out.append(
                "      独立成词命中 0 处（否则它进不了这张表）；件口径算的裸子串命中 {0} 处，"
                "逐处「被谁吞进去」：".format(len(forms))
            )
            for form in forms[:MAX_HIT_FORMS_IN_REPORT]:
                if form["kind"] == "cross_line_only":
                    out.append("        {0}  {1}".format(form["path"], form["note"]))
                else:
                    out.append(
                        "        {0}:{1}  锚词 {2} 落在整 token「{3}」内部 —— {4}".format(
                            form["path"],
                            form["raw_line_number"],
                            item["term"],
                            form["enclosing_token"],
                            "两侧不挨拉丁字符，独立成词"
                            if form["independent_word"]
                            else "两侧仍挨拉丁字符 ⇒ 不算独立成词",
                        )
                    )
            if len(forms) > MAX_HIT_FORMS_IN_REPORT:
                out.append(
                    "        还有 {0} 处未列，全量在 --caliber-json（一条没丢）".format(
                        len(forms) - MAX_HIT_FORMS_IN_REPORT
                    )
                )
            out.append(
                "      ⇒ 这枚锚词在语料里从未独立成词：件口径那句「有出处」是裸子串替它说的假话。"
            )
    else:
        out += [
            "",
            "  分歧来源：本次两把尺判定一致（0 枚分歧），词边界复核没有东西可翻案 —— "
            "两把尺的数因此相同，不是有人关掉了其中一把。",
        ]
    case_yes = audit["entry_total"] - case_view["term_count"]
    semantic_yes = audit["entry_total"] - semantic_view["term_count"]
    out += [
        "",
        "  翻转面对账（{0} 枚锚词条目 before/after，本脚本现算，不手抄）：".format(
            audit["entry_total"]
        ),
        "    件口径判有出处 = {0} 枚 → 语义口径判有出处 = {1} 枚；判定改变 = {2} 枚".format(
            case_yes, semantic_yes, len(flips)
        ),
        "    档位分布：ascii 档 {0} 枚 / cjk 档 {1} 枚；cjk 档的判定改变数恒为 0，"
        "破了由 audit_calibers 拒绝出数".format(audit["ascii_entries"], audit["cjk_entries"]),
        "    改变方向只允许「有出处 → 缺出处」（加严）；反向翻转在自检里就是错。",
    ]
    if flips:
        out.append("    改变的条目逐枚点名：")
        for item in flips:
            out.append(
                "      题 {0}  锚词 {1}  档位 {2}  有出处 → 缺出处".format(
                    item["row_id"], item["term"], item["tier"]
                )
            )
    out.append(
        "    其余 {0} 枚判定未变（其中件口径本就判缺出处的 {1} 枚，两把尺对它们本来就是同一句话）。".format(
            audit["entry_total"] - len(flips), case_view["term_count"]
        )
    )
    return out


def corpus_label(include_pdf: bool, include_csv: bool) -> str:
    parts = [
        "{0}/{1}（{2} 篇，主口径）".format(
            CORPUS_DIR_REL, CORPUS_TXT_GLOB, EXPECTED_CORPUS_TXT_COUNT
        )
    ]
    if include_pdf:
        parts.append("+ documents/*.pdf【备选口径】")
    if include_csv:
        parts.append("+ data/*.csv【备选口径】")
    return " ".join(parts)


def render_report(
    missing: dict[str, list[str]],
    *,
    rows: int,
    term_total: int,
    corpus_desc: str,
    audit: dict,
) -> str:
    missing_term_total = sum(len(terms) for terms in missing.values())
    out = [
        "评测集 must_contain 出处覆盖度复算",
        "  归一化口径 : {0}（题面与语料两侧同规则；{1}）".format(
            " -> ".join(NORMALIZATION_STEPS), MATCH_MODE
        ),
        "  计行规则   : {0}".format(ROW_RULE),
        "  题源       : {0} 行 / {1} 个 must_contain 词条".format(rows, term_total),
        "  语料       : {0}".format(corpus_desc),
        "",
        "  >> 查无出处的行 = {0}".format(len(missing)),
        "  >> 查无出处的词 = {0}".format(missing_term_total),
    ]
    if len(missing) != missing_term_total:
        out += [
            "  !! 口径指纹破了：行数({0}) != 词条数({1})。审计文档 §2.2 说这条差值在主规则下"
            "必须为 0；".format(len(missing), missing_term_total),
            "  !! 说明本机题源或归一化与文档不同，**这个数不要引用**。",
        ]
    else:
        out.append("  口径指纹（§2.2）: 行数 == 词条数，与主规则一致")
    out += render_caliber_block(audit)
    out += [
        "",
        "  缺出处的题号（件口径 {0} 条）：".format(len(missing)),
        "    " + " ".join(sorted(missing)),
        "",
        "  逐条：",
    ]
    for row_id in sorted(missing):
        out.append("    {0}\t{1}".format(row_id, " | ".join(missing[row_id])))
    return "\n".join(out)


EPILOG = """\
口径分歧（主口径为什么排除 PDF）：
  主规则把「出处」限定在 documents/*.txt 这 95 篇。把 2 篇 PDF 也算进语料会得到 27 而不是 29，
  被 PDF「救回」的恰好是 chat-02（词条「之后」命中 refactor_guide.pdf）与 insight-07（词条
  「不确定性」命中 AI-Agent 学习路线图.pdf）——跟进单 §25.0 早把这两篇定性为「与经营无关的
  PDF」。拿它们当出处等于让「差旅报销顺序」去引用一份代码重构指南。所以 --include-pdf 表达的
  是**另一种口径，主口径排除**：它只为对账而存在，用它算出的数不许写进任何以 29 为口径的账。
  同理 data/报销明细表.csv 在主口径里不算出处（--include-csv 得到的仍是 29——「前五/小计/
  变化率/长期未处理/超标率」五个字面串在 CSV 里 0 命中，见 §2.3）。门店 xlsx 加进去也不改变
  结果（§3.10：95txt + 2pdf + xlsx + csv 仍为 27），故不为它设开关。
  依据：docs/handoff/2026-09-19-eval-evidence-audit.md §1、§2.3、§3.10。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_eval_evidence_coverage.py",
        description=(
            "离线复算「评测集 must_contain 在 documents/*.txt 语料里查无出处」的行数与题号清单。"
            "主口径在 9626b7d 上给出 29。零模型、零网络、零连库、零起服务。"
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="仓库根目录（默认取本脚本上两级）。",
    )
    parser.add_argument(
        "--include-pdf",
        action="store_true",
        help="把 documents/*.pdf 也算作出处。**那是另一种口径，主口径排除**（会给出 27 而非 29，"
        "理由见下方「口径分歧」段），只为对账而存在。",
    )
    parser.add_argument(
        "--include-csv",
        action="store_true",
        help="把 data/*.csv 也算作出处。同为备选口径；主口径排除（§1.7），实测结果不变。",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=None,
        help="R401 派生能力：把题源里每个 must_contain 词条在语料里的**现取出处**（篇路径 + "
        "命中的原始行号 + 归一化后 utf-8 字节区间）以 UTF-8 JSON 写到该路径。它只回答"
        "「这个词在语料的哪里」，不改动 §1.4/§1.5/§1.7 任何判据，也不影响出数。",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="把 {题号: [缺的词条]} 以 UTF-8 写到该路径（**件口径那把尺的结果，与 R94 同形**；"
        "默认不落盘、不改动仓库）。",
    )
    parser.add_argument(
        "--caliber-json",
        type=Path,
        default=None,
        help="把**两把尺一起**的账以 UTF-8 写到该路径：件口径读数、语义口径读数、逐枚分歧"
        "（锚词 + 吞掉它的整 token + 文件行号）、以及题源全部锚词条目的 before/after。"
        "件口径一个字节没动，这个开关只添账、不改账。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse 已自行打印用法/帮助，这里只翻译退出码
        return EXIT_USAGE if exc.code else EXIT_OK

    root: Path = args.repo_root.resolve()
    try:
        rows = load_rows(root / FIXTURE_REL)
        # 语料只读一遍：件口径要归一化文本，语义口径要原始文本（词的接缝留在原始文本里现算），
        # R401 的取证件吃的也是同一份原文 —— 一次 IO 喂三处，谁也不许再偷偷开第二次读取。
        entries = _corpus_entries(
            root, include_pdf=args.include_pdf, include_csv=args.include_csv
        )
        corpus = {label: normalize(raw) for label, _path, raw in entries}
        corpus_raw = {label: (path, raw) for label, path, raw in entries}
        missing = find_missing_terms(rows, corpus)
        audit = audit_calibers(rows, missing, corpus, corpus_raw)
        report = render_report(
            missing,
            rows=len(rows),
            term_total=sum(len(row[MUST_CONTAIN_FIELD]) for row in rows),
            corpus_desc=corpus_label(args.include_pdf, args.include_csv),
            audit=audit,
        )
        provenance = None
        if args.provenance is not None:
            provenance = derive_provenance_for_rows(rows, corpus_raw)
    except StructureDrift as exc:
        print("FAIL-CLOSED：拒绝出数（输入与本脚本钉死的主口径不一致）", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return EXIT_STRUCTURE

    print(report)
    if args.json is not None:
        target: Path = args.json
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("已写出 {0}（{1} 条）".format(target, len(missing)))
    if args.caliber_json is not None:
        caliber_target: Path = args.caliber_json
        if caliber_target.parent and not caliber_target.parent.exists():
            caliber_target.parent.mkdir(parents=True, exist_ok=True)
        caliber_target.write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            "已写出双口径账 {0}（件口径 {1} / 语义口径 {2}；{3} 枚锚词条目 before/after 全量在内）".format(
                caliber_target,
                audit["case"]["row_count"],
                audit["semantic"]["row_count"],
                audit["entry_total"],
            )
        )
    if args.provenance is not None:
        provenance_target: Path = args.provenance
        if provenance_target.parent and not provenance_target.parent.exists():
            provenance_target.parent.mkdir(parents=True, exist_ok=True)
        provenance_target.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(
            "已写出派生出处 {0}（{1} 个词条；只读语料现算，判据未动）".format(
                provenance_target, len(provenance)
            )
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
