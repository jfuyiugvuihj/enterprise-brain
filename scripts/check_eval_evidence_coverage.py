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
       --json 路径上落盘。
    2. 口径不商量：判据全在下面「口径常量」区块里，以显式常量 + 注释表达。要换口径请用开关
       （--include-pdf / --include-csv），不要改常量。
    3. fail-closed：输入规模与本口径钉死的期望值不一致时**拒绝给数**，非 0 退出并打印它实际
       看到了什么。这个数字变了必须让人当场知道，不许静默吐出一个新数。

【退出码】
    0 = 正常出数；1 = 命令行用法错误；2 = 结构漂移（题源/语料规模与口径不符）或开关依赖缺失。

【用法】
    python scripts/check_eval_evidence_coverage.py
    python scripts/check_eval_evidence_coverage.py --json _r94/no_provenance_r0.json
    python scripts/check_eval_evidence_coverage.py --include-pdf
"""
from __future__ import annotations

import argparse
import json
import re
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


def decode_text_bytes(raw: bytes) -> str:
    """§1.3：按 CORPUS_DECODINGS 顺序试解码，取第一个成功的；全失败抛 StructureDrift。"""
    for encoding in CORPUS_DECODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StructureDrift(
        "语料解码失败（依次试过 {0}）：本脚本不猜编码，猜了就不可复算。".format(
            " / ".join(CORPUS_DECODINGS)
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
    for page in PdfReader(str(pdf_path)).pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def load_corpus(
    root: Path,
    *,
    include_pdf: bool = False,
    include_csv: bool = False,
) -> dict[str, str]:
    """按口径装载语料，返回 {文件标签: 归一化后的文本}。

    主口径（两个开关都不开）只读 documents/*.txt，且必须正好 EXPECTED_CORPUS_TXT_COUNT 篇。
    """
    corpus_dir = root / CORPUS_DIR_REL
    if not corpus_dir.is_dir():
        raise StructureDrift(
            "语料目录不存在：{0}。本脚本不会退回任何缓存/快照冒充语料——上一轮废跑的根因就是\n"
            "  拿宿主 chroma_db 快照当语料真相源（审计文档 §3.9、runbook P-9）。".format(corpus_dir)
        )
    txt_files = sorted(corpus_dir.glob(CORPUS_TXT_GLOB))
    if len(txt_files) != EXPECTED_CORPUS_TXT_COUNT:
        raise StructureDrift(
            "语料 txt 篇数对不上主口径：看到 {0} 篇，期望 {1} 篇（{2}）。\n{3}".format(
                len(txt_files), EXPECTED_CORPUS_TXT_COUNT, corpus_dir, UPDATE_BOTH_PLACES
            )
        )
    loaded = [(path.name, decode_text_bytes(path.read_bytes())) for path in txt_files]
    if include_pdf:
        for path in sorted(corpus_dir.glob(PDF_GLOB)):
            loaded.append(("{0} [PDF 备选口径]".format(path.name), read_pdf_text(path)))
    if include_csv:
        for path in sorted((root / DATA_DIR_REL).glob(DATA_CSV_GLOB)):
            loaded.append(
                ("{0} [CSV 备选口径]".format(path.name), decode_text_bytes(path.read_bytes()))
            )
    return {label: normalize(text) for label, text in loaded}


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
    out += [
        "",
        "  缺出处的题号（{0} 条）：".format(len(missing)),
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
        "--json",
        type=Path,
        default=None,
        help="把 {题号: [缺的词条]} 以 UTF-8 写到该路径（默认不落盘、不改动仓库）。",
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
        corpus = load_corpus(root, include_pdf=args.include_pdf, include_csv=args.include_csv)
        missing = find_missing_terms(rows, corpus)
    except StructureDrift as exc:
        print("FAIL-CLOSED：拒绝出数（输入与本脚本钉死的主口径不一致）", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return EXIT_STRUCTURE

    print(
        render_report(
            missing,
            rows=len(rows),
            term_total=sum(len(row[MUST_CONTAIN_FIELD]) for row in rows),
            corpus_desc=corpus_label(args.include_pdf, args.include_csv),
        )
    )
    if args.json is not None:
        target: Path = args.json
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print("已写出 {0}（{1} 条）".format(target, len(missing)))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
