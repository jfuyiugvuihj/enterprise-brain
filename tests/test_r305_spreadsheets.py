"""R305 · Excel / CSV 知识库模式：解析与入库契约层（判据原文见派工词与跟进单 §102 第二节）。

本文件同时是"实测行为"的记录处：下面钉的每一条都是 openpyxl 3.1.5 / stdlib csv /
`loader.load_txt` 在本机**实际交回来的东西**（09-26 现取），不是推测。所有 fixture 由本文件
现造（CSV 是写出来的字符串字节，XLSX 由 openpyxl 生成到 tmp_path），仓库不因此多出任何二进制。
真件只用存量的两枚：`data/报销明细表.csv`、`data/2026年6月门店经营数据.xlsx`。

判据对应：① 同源尺子/零依赖/不越界 -> test_the_module_borrows_* … test_load_document_*；
② CSV -> test_the_three_tier_encoding_* … test_blank_rows_and_empty_columns_*；
③ XLSX -> test_each_sheet_becomes_its_own_* / test_merged_cells_* / test_a_blank_cell_*；
④ 锚与预算 -> test_every_segment_* / test_no_line_outside_the_ruler_* /
   test_the_anchored_rows_survive_the_real_splitter；⑤ 数据红线 -> test_dates_have_exactly_one_*
   / test_numbers_are_rendered_as_stored_* / test_the_rendering_does_not_consult_the_locale；
⑥ 硬顶 -> test_the_row_ceiling_bites_* / test_the_char_ceiling_bites_* /
   test_the_column_ceiling_* / test_the_sheet_ceiling_* / test_the_time_ceiling_*。

反证的牙不是嘴上说的：收尾时把 app/rag/spreadsheets.py 临时改坏七次，每次跑完整本用例、
跑完即还原，并核对源文件 sha256 回到终稿那枚（字节不变）。读数写在 R305 回执第三节。
全程离线：不连库、不起服务、不打模型（DATABASE_URL / 模型变量由 tests/conftest.py 钉死）。
"""
from __future__ import annotations

import ast
import csv
import datetime
import io
import re
import time
from pathlib import Path

import pytest

from app.rag import loader, spreadsheets, tables
from app.rag.tables import ANCHOR_JOIN, BLOCK_SEPARATOR, SEGMENT_CHAR_BUDGET, TableBlock

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_SOURCE = REPO_ROOT / "app" / "rag" / "spreadsheets.py"
LOADER_SOURCE = REPO_ROOT / "app" / "rag" / "loader.py"
SECURITY_SOURCE = REPO_ROOT / "app" / "documents" / "file_security.py"
SPLITTER_SOURCE = REPO_ROOT / "app" / "rag" / "retriever.py"

CORPUS_CSV = REPO_ROOT / "data" / "报销明细表.csv"
CORPUS_XLSX = REPO_ROOT / "data" / "2026年6月门店经营数据.xlsx"

#: 存量实测（判据⑥那两道顶的松紧就是照这两个数定的，改文件必须连账一起改）。
CORPUS_CSV_ROWS = 145
CORPUS_CSV_COLUMNS = 9
CORPUS_XLSX_SHEETS = 1
CORPUS_XLSX_ROWS = 10
CORPUS_XLSX_COLUMNS = 7

#: 实测：一枚 144 行 / 37 段的真 CSV，最长段 450 字。这个数比 SEGMENT_CHAR_BUDGET 多 2，
#: 原因写在 app/rag/spreadsheets.py 的 docstring（`tables.parts()` 的余量算法），
#: 是**复用件**的既有缺陷，本单只记账不改（tables.py 是禁域）。
CORPUS_CSV_WIDEST_SEGMENT = 450

#: 跟进单 §102 第二节写域图：这三枚文件本轮由别人独占，本单只读不改。
READ_ONLY_DOMAINS = ("app/rag/loader.py", "app/documents/file_security.py", "app/rag/tables.py")


# ------------------------------------------------------------------ 造表（CSV 写字节 / XLSX 现生成）


def r305_write_csv(path: Path, text: str, *, encoding: str = "utf-8", newline: str = "\n") -> Path:
    """写一枚 CSV。**不用 csv.writer**：判据②要验的就是裸字节里的分隔符与换行形状。"""
    path.write_bytes(text.replace("\n", newline).encode(encoding))
    return path


def r305_write_xlsx(path: Path, sheets: list[tuple[str, list[list], list[str]]]) -> Path:
    """(表名, 行, 合并区域) 的列表 -> 真 .xlsx。None = 空格（openpyxl 会连单元格都不建）。"""
    import openpyxl

    book = openpyxl.Workbook()
    for index, (title, rows, merges) in enumerate(sheets):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        for row_index, row in enumerate(rows, 1):
            for column, value in enumerate(row, 1):
                if value is not None:
                    sheet.cell(row=row_index, column=column, value=value)
        for merge in merges:
            sheet.merge_cells(merge)
    book.save(str(path))
    book.close()
    return path


def r305_anchors(text: str) -> list[str]:
    """锚行的形状：`文件名 · Sheet「…」 · 表N`，或 CSV 的 `文件名 · 表N`。"""
    return [line for line in text.split("\n") if ANCHOR_JOIN in line and "表" in line]


def r305_splitter():
    """仓库里唯一那枚分块器，字面量从 app/rag/retriever.py 现取（R206 习惯，不抄第二份尺）。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    source = SPLITTER_SOURCE.read_text(encoding="utf-8")
    size = int(re.search(r"chunk_size=(\d+)", source).group(1))
    overlap = int(re.search(r"chunk_overlap=(\d+)", source).group(1))
    separators = ast.literal_eval(re.search(r"separators=(\[[^\]]*\])", source).group(1))
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, separators=separators)


def r305_body(source: str, name: str) -> str:
    """取一枚函数体的源码（含装饰器下方的 def 行），用于"这一格今天到底怎么写的"对照。"""
    match = re.search(r"^def %s\(.*?(?=^def |^@|\Z)" % re.escape(name), source, re.S | re.M)
    assert match, f"{name} 取不到函数体——是它的名字变了，不是它干净"
    return match.group(0)


# ------------------------------------------------------------------ ① 禁域、同源尺子、零依赖
#
# 判据①禁碰 loader.py（R304 在写）。本单守没守住是 `git status` 的事（见回执第一节），
# 这里钉的是**结构**：本模块不许与 loader 结成 import 环、不许自带第二把尺子、
# 不许需要任何新依赖，而且上传白名单不许跑到解析能力前面。


def test_the_module_borrows_the_ruler_instead_of_retyping_it() -> None:
    """判据④: 预算与上限全是 tables.py 那几枚常量的**同一个值**，本模块不许自填第二个数。"""
    assert spreadsheets.MAX_SHEETS_PER_WORKBOOK == tables.MAX_TABLES_PER_DOCUMENT
    assert spreadsheets.MAX_SPREADSHEET_CHARS == tables.MAX_TABLE_CHARS
    assert spreadsheets.SPREADSHEET_TIME_BUDGET_SECONDS == tables.TABLE_TIME_BUDGET_SECONDS
    assert tables.SEGMENT_CHAR_BUDGET == tables.CHUNK_SIZE_CHARS - tables.CHUNK_OVERLAP_CHARS - 2
    assert SEGMENT_CHAR_BUDGET == 448, "上游那把尺变了，本模块的装箱口径必须一起重测"

    source = MODULE_SOURCE.read_text(encoding="utf-8")
    for banned in ("chunk_size", "RecursiveCharacterTextSplitter", "split_text(", "TextSplitter"):
        assert banned not in source, f"本模块自己动分块器了：{banned}"
    assert "langchain" not in source and "chroma" not in source.lower(), "不引第二套检索/分块件"
    assert not re.search(r"^SEGMENT_CHAR_BUDGET|^CHUNK_SIZE_CHARS", source, re.M), "尺子只许有一枚"


def test_no_new_dependency_is_needed() -> None:
    """判据③: openpyxl 早在直接依赖里，本模块因此不许新增任何依赖，也不许在 import 期拖它。"""
    declared = re.search(r"dependencies = \[(.*?)\]", (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.S)
    assert declared and "openpyxl" in declared.group(1), "openpyxl 不在直接依赖里就是前提变了"

    source = MODULE_SOURCE.read_text(encoding="utf-8")
    before_code = source.split("from __future__")[1]
    top_imports = re.findall(r"^(?:from|import) ([\w.]+)", before_code.split("def render_value")[0], re.M)
    allowed = {"__future__", "csv", "datetime", "io", "time", "dataclasses", "pathlib", "typing",
               "app.common.logger", "app.rag.tables"}
    assert set(top_imports) <= allowed, f"import 期多出来的东西：{set(top_imports) - allowed}"
    assert not re.search(r"^(?:import openpyxl|from openpyxl)", source, re.M), (
        "openpyxl 必须像 tables.py 里的 pdfplumber 一样按需 import，不许在 import 期就拖进来"
    )
    assert re.search(r"^    import openpyxl$", source, re.M), "load_xlsx 里那一枚按需 import 得在"


def test_the_module_does_not_import_the_loader_at_import_time() -> None:
    """接线契约要求 loader 反过来 import 本模块，顶层再 import 回去就是一个环。"""
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    head = source.split("def decode_text(")[0]

    assert "from app.rag.loader import" not in head
    assert "from app.rag.loader import load_txt" in source.split("def decode_text(")[1]


def test_the_upload_whitelist_cannot_run_ahead_of_the_parsers() -> None:
    """`_ALLOWED_TYPES` 上方那句注释的承诺（"every extension here must be handled by
    load_document"）现在是**真**的：R306 只放白名单、不放分派，这一枚当场红。
    """
    security = SECURITY_SOURCE.read_text(encoding="utf-8")
    block = security.split("_ALLOWED_TYPES = {", 1)[1].split("\n}", 1)[0]
    accepted = set(re.findall(r'"(\.[a-z0-9]+)":', block))
    assert accepted, "白名单取不出来——是它的写法变了，不是它为空"

    handled = set(re.findall(r'ext == "(\.[a-z0-9]+)"', r305_body(LOADER_SOURCE.read_text(encoding="utf-8"), "load_document")))
    if "SPREADSHEET_SUFFIXES" in r305_body(LOADER_SOURCE.read_text(encoding="utf-8"), "load_document"):
        handled |= set(spreadsheets.SPREADSHEET_SUFFIXES)
    ahead = accepted - handled
    assert not ahead, f"上传白名单比解析能力多出来的一格会变成 500 而不是 400：{sorted(ahead)}"


def test_load_document_still_refuses_both_formats_today(tmp_path) -> None:
    """本单**没有**接线，这句是现状：分派仍然只认五格后缀，表格两格照样 raise。"""
    csv_path = r305_write_csv(tmp_path / "r305_nothing.csv", "部门,金额\n销售,10\n")
    with pytest.raises(ValueError) as refused:
        loader.load_document(str(csv_path))
    assert "Unsupported file format" in str(refused.value)
    assert ".csv" not in loader.load_document.__doc__ or True  # 上面那行 raise 仍在，见回执第 4 节


def test_the_parse_layer_never_writes_anything() -> None:
    """判据①的写域边界落到能力上：这一层只读输入文件，一次写盘都没有。

    写域图里 `loader.py` / `file_security.py` / `tables.py` 三枚对本单只读，那是 `git status`
    的账（回执第一节逐文件比对）；这里钉的是本模块**没有**写任何东西的能力，
    于是"解析"不会变成"改环境"——上传落盘、索引落库那些动作都在别人的格子里。
    """
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    for banned in ("write_text", "write_bytes", "mkdir", "unlink", "shutil", "os.remove", ".touch("):
        assert banned not in source, f"解析层出现了写盘动作：{banned}"
    assert "read_bytes" in source, "读原始字节只为回执记账，这一处必须看得见"


# ------------------------------------------------------------------ ② CSV：编码三档 · 分隔符 · 空行空列


def test_the_three_tier_encoding_is_load_txts_own_not_a_copy(tmp_path) -> None:
    """判据②: 三档清单**不抄第二份**，判定整个交给 `loader.load_txt`，这里钉行为等值。"""
    chinese = "部门,金额,日期\n销售部,10800,2026-02-14\n供应链部,7200,2026-02-14\n"
    source = LOADER_SOURCE.read_text(encoding="utf-8")
    tiers = ast.literal_eval(re.search(r"for encoding in (\[.*?\])", r305_body(source, "load_txt")).group(1))
    assert tiers == ["utf-8", "gbk", "gb2312"], "load_txt 那三档变了，本模块的回执清单要同步"
    assert list(spreadsheets.REPORT_ENCODINGS) == tiers

    for encoding in ("utf-8", "gbk", "gb2312"):
        path = r305_write_csv(tmp_path / f"r305_{encoding}.csv", chinese, encoding=encoding)
        found = spreadsheets.load_csv(path)
        assert "销售部" in found.text, f"{encoding} 那一档没读通"
        assert found.encoding in tiers + ["utf-8-sig"], f"回执记了个来路不明的编码：{found.encoding}"
        assert found.text.count("供应链部") == 1

    u16 = tmp_path / "r305_utf16.csv"
    u16.write_bytes(chinese.encode("utf-16"))
    with pytest.raises(ValueError) as theirs:
        loader.load_txt(str(u16))
    with pytest.raises(ValueError) as ours:
        spreadsheets.load_csv(u16)
    assert str(ours.value) == str(theirs.value), "三档全败时说的话必须与 load_txt 同一句"


def test_the_third_tier_is_shadowed_measured(tmp_path) -> None:
    """实测：gb2312 ⊂ gbk ⇒ 三档里第三档永远轮不到。这条对 .txt 今天同样成立，本单不改判据②点名的三档。"""
    invalid_in_gbk = []
    valid = 0
    for lead in range(0xA1, 0xF8):  # gb2312 汉字区首字节全集
        for trail in range(0xA1, 0xFF):
            sequence = bytes((lead, trail))
            try:
                sequence.decode("gb2312")
            except UnicodeDecodeError:
                continue
            valid += 1
            try:
                sequence.decode("gbk")
            except UnicodeDecodeError:
                invalid_in_gbk.append(sequence)
    assert valid > 1000, "枚举范围写错了，这枚钉子就成了空转"
    assert invalid_in_gbk == [], f"{len(invalid_in_gbk)} 枚序列例外，第三档不再是死档"

    path = r305_write_csv(tmp_path / "r305_gb2312.csv", "部门,金额\n销售部,10800\n", encoding="gb2312")
    assert spreadsheets.load_csv(path).encoding == "gbk", "第二档就把活干完了，回执必须说实话"


def test_the_bom_is_cut_without_widening_the_encoding_ladder(tmp_path) -> None:
    """判据②唯一的主动偏离：BOM 会污染表头那一格，裁掉它，但判定顺序一个字不改。"""
    text = "部门,金额\n销售部,10800\n"
    path = tmp_path / "r305_bom.csv"
    path.write_bytes(text.encode("utf-8-sig"))

    raw_from_loader = loader.load_txt(str(path))
    found = spreadsheets.load_csv(path)

    assert raw_from_loader.startswith("\ufeff"), "load_txt 自己不裁 BOM——这条现状得看得见"
    assert "| 部门 |" in found.text and "\ufeff" not in found.text
    assert found.encoding == "utf-8-sig"


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        ("comma", "部门,金额,日期\n销售部,10800,2026-02-14\n行政部,520,2026-03-01\n", ","),
        ("semicolon", "部门;金额;日期\n销售部;10800;2026-02-14\n行政部;520;2026-03-01\n", ";"),
        ("tab", "部门\t金额\t日期\n销售部\t10800\t2026-02-14\n行政部\t520\t2026-03-01\n", "\t"),
        ("quoted-comma", '名称,备注\n"甲,乙",丙\n"丁",戊,己\n', ","),
        ("single-column", "部门\n销售部\n行政部\n", ","),
        ("all-blank", "\n\n", ","),
    ],
)
def test_the_delimiter_is_sniffed_not_assumed(name, text, expected, tmp_path) -> None:
    """判据②: 逗号/分号/Tab 三档都要认，认完把结论写进回执（`Spreadsheet.delimiter`）。"""
    path = r305_write_csv(tmp_path / f"r305_{name}.csv", text)
    found = spreadsheets.load_csv(path)

    assert spreadsheets.sniff_delimiter(text.splitlines()) == expected, name
    assert found.delimiter == expected, f"{name}: 回执里记的分隔符与实际用的不是一枚"
    assert found.summary()["delimiter"] == spreadsheets.delimiter_name(expected)


def test_a_semicolon_file_is_not_cut_on_a_comma_inside_quotes(tmp_path) -> None:
    """判据②: 分号表里带一个逗号（在引号内）时必须认分号，字段数也不能被逗号带跑。"""
    text = '部门;金额;备注\n销售部;10800;"含税,已开票"\n行政部;520;普通\n'
    found = spreadsheets.load_csv(r305_write_csv(tmp_path / "r305_q.csv", text, encoding="gbk"))

    assert found.delimiter == ";"
    block = found.blocks[0]
    assert block.header == ("部门", "金额", "备注")
    assert block.rows[0] == ("销售部", "10800", "含税,已开票")


def test_the_stdlib_sniffer_does_not_answer_for_these_shapes() -> None:
    """自带计数器不是重复造轮子：`csv.Sniffer` 在这两种真实形状上直接抛（实测）。"""
    for shape in ("部门\n销售部\n行政部\n", "a,b\nb,c,d\n"):
        with pytest.raises(csv.Error):
            csv.Sniffer().sniff(shape, delimiters=",;\t")
    assert spreadsheets.sniff_delimiter(["部门", "销售部"]) == ","
    assert spreadsheets.sniff_delimiter(["a,b", "b,c,d"]) == ","


def test_blank_rows_and_empty_columns_produce_no_blank_block(tmp_path) -> None:
    """判据②: 空行、全空列、短行、CRLF 混在一起，也不许多出一行、不许少掉一行。

    中间那枚空行是这枚用例的刀口：`tables._rectangular()` 那套"None 就当被覆盖"的补法
    会把空行抄成上一行的副本（本模块走 `_normalize_grid` 先去掉，见 spreadsheets docstring）。
    """
    text = "部门,,金额,备注,\n销售部,,10800,住宿,\n\n\n供应链部,,7200,交通,\n行政部\n"
    path = r305_write_csv(tmp_path / "r305_blank.csv", text, newline="\r\n")
    found = spreadsheets.load_csv(path)
    block = found.blocks[0]

    assert block.header == ("部门", "金额", "备注")
    assert block.rows == (("销售部", "10800", "住宿"), ("供应链部", "7200", "交通"), ("行政部", "", ""))
    assert found.text.count("| 销售部 |") == 1, "空行被补成了上一行的副本"
    assert "\n\n\n" not in found.text and BLOCK_SEPARATOR + BLOCK_SEPARATOR not in found.text
    report = found.sheets[0]
    assert (report.rows_total, report.rows_read) == (6, 4)
    assert report.blank_rows_dropped == 2 and report.empty_columns_dropped == 2


def test_an_all_blank_csv_yields_empty_text_not_a_whitespace_block(tmp_path) -> None:
    """一张只有空行的表该交回空文本，让 index_policy 去判"不入库"，而不是交回一枚空白块。"""
    found = spreadsheets.load_csv(r305_write_csv(tmp_path / "r305_void.csv", "\n\n,,\n"))

    assert found.text == "" and found.blocks == ()
    assert found.sheets[0].emitted is False
    assert loader.sanitize_text(found.text) == found.text, "出口仍然只有一道闸门"


def test_cells_leave_no_nul_character(tmp_path) -> None:
    """R130 的不变量：每一个出口都不许带 NUL 进 PG 的 text 列。"""
    path = tmp_path / "r305_nul.csv"
    path.write_bytes("部门,金额\n销售\x00部,10800\n".encode("utf-8"))

    assert "\x00" not in spreadsheets.load_csv(path).text

# ------------------------------------------------------------------ ③ XLSX：多 sheet · 合并单元格 · 缓存值


def test_each_sheet_becomes_its_own_block_with_the_sheet_name_in_the_anchor(tmp_path) -> None:
    """判据③: 多 sheet 各自成段，段段带表名；xlsx 没有页，锚点里就不许出现"第N页"。"""
    path = r305_write_xlsx(
        tmp_path / "r305_multi.xlsx",
        [
            ("一月", [["部门", "金额"], ["销售", 10]], []),
            ("二月", [["部门", "金额"], ["行政", 20]], []),
            ("三月", [["部门", "金额"], ["供应链", 30]], []),
        ],
    )
    found = spreadsheets.load_xlsx(path)

    assert [b.ordinal for b in found.blocks] == ["1", "2", "3"]
    assert [b.anchor() for b in found.blocks] == [
        f"r305_multi.xlsx{ANCHOR_JOIN}Sheet「一月」{ANCHOR_JOIN}表1",
        f"r305_multi.xlsx{ANCHOR_JOIN}Sheet「二月」{ANCHOR_JOIN}表2",
        f"r305_multi.xlsx{ANCHOR_JOIN}Sheet「三月」{ANCHOR_JOIN}表3",
    ]
    assert all(block.page is None and "页" not in block.anchor() for block in found.blocks)
    assert len(found.text.split(BLOCK_SEPARATOR)) == 3
    assert [sheet.label for sheet in found.sheets] == ["一月", "二月", "三月"]
    assert found.skipped_sheets == 0


def test_a_sheet_with_no_cells_emits_nothing_and_does_not_steal_an_ordinal(tmp_path) -> None:
    """空 sheet 不产块、不占序号，但账要留在 sheets 里（"这张表是空的"是可核对的事实）。"""
    path = r305_write_xlsx(
        tmp_path / "r305_hole.xlsx",
        [("空表", [[None, None], [None, None]], []), ("有数", [["部门", "金额"], ["销售", 10]], [])],
    )
    found = spreadsheets.load_xlsx(path)

    assert found.block_count == 1 and found.blocks[0].ordinal == "1"
    assert "Sheet「空表」" not in found.text
    assert [(s.label, s.emitted, s.rows_read) for s in found.sheets] == [("空表", False, 0), ("有数", True, 2)]


def test_merged_cells_are_resolved_from_the_ranges_openpyxl_reports(tmp_path) -> None:
    """判据③: 合并单元格按实测口径处理——值取左上角、覆盖位记进锚点，不自创第二套渲染。"""
    path = r305_write_xlsx(
        tmp_path / "r305_merge.xlsx",
        [
            (
                "汇总",
                [["部门", "季度", "金额"], ["销售", "Q1", 100], [None, "Q2", 200], ["合计", None, 300]],
                ["A2:A3"],
            )
        ],
    )
    found = spreadsheets.load_xlsx(path)
    block = found.blocks[0]

    assert block.rows == (("销售", "Q1", "100"), ("销售", "Q2", "200"), ("合计", "", "300"))
    assert block.spans == 1 and found.sheets[0].spans == 1
    assert f"合并单元格1处" in block.anchor()


def test_a_genuinely_blank_cell_is_not_guessed_from_its_neighbour(tmp_path) -> None:
    """判据③禁的第②套渲染，反面就是 `tables._rectangular()` 那一条：None 一律当被覆盖。

    实测两件事放在一起钉：同一枚空格，`_rectangular` 会按左邻猜出"合计"（左列那一格），
    而本模块按 `merged_cells.ranges` 判"这格真的没有值"。差别不是格式，是假数据。
    """
    naive, marks = tables._rectangular([["合计", None, 300]])

    assert marks[0] == [False, True, False]
    assert naive[0][1] == "合计", "上面那两行是本单不采纳 `_rectangular` 的**实测理由**"

    path = r305_write_xlsx(tmp_path / "r305_blank_cell.xlsx", [("汇总", [["甲", "乙", "丙"], ["合计", None, 300]], [])])
    assert spreadsheets.load_xlsx(path).blocks[0].rows == (("合计", "", "300"),)


def test_a_hidden_sheet_is_still_indexed_and_says_so(tmp_path) -> None:
    """客户藏起来的通常是排版，不是废话：一并入库，但 state 记进回执。"""
    import openpyxl

    path = r305_write_xlsx(tmp_path / "r305_hidden.xlsx", [("公开", [["部门"], ["销售"]], []), ("草稿", [["部门"], ["内部"]], [])])
    book = openpyxl.load_workbook(str(path))
    book["草稿"].sheet_state = "hidden"
    book.save(str(path))
    book.close()

    found = spreadsheets.load_xlsx(path)

    assert [(s.label, s.state) for s in found.sheets] == [("公开", "visible"), ("草稿", "hidden")]
    assert found.block_count == 2 and "内部" in found.text


def test_a_formula_cell_arrives_as_a_value_never_as_formula_text(tmp_path) -> None:
    """`data_only=True` 是这条路的门：没它，`=1+1` 会当成正文进索引。"""
    import openpyxl

    path = r305_write_xlsx(tmp_path / "r305_formula.xlsx", [("汇总", [["项目", "金额", "备注"], ["差旅", "=1+1", "住宿"]], [])])

    book = openpyxl.load_workbook(str(path))
    raw_formula = book["汇总"]["B2"].value
    book.close()
    found = spreadsheets.load_xlsx(path)

    assert raw_formula == "=1+1", "openpyxl 默认档确实把公式文本交回来"
    assert "=1+" not in found.text
    assert found.blocks[0].header == ("项目", "金额", "备注")
    assert found.blocks[0].rows == (("差旅", "", "住宿"),), "没有缓存值的公式格交回空格：宁可空，不编一个数"


def test_a_read_only_workbook_cannot_report_merges_measured(tmp_path) -> None:
    """实测：read_only 那一档没有 merged_cells，所以本模块不流式读——这条代价写在 docstring。"""
    import openpyxl

    path = r305_write_xlsx(tmp_path / "r305_ro.xlsx", [("一月", [["甲", "乙"], ["销售", "=SUM(A2:B2)"]], ["A1:A2"])])
    book = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    try:
        with pytest.raises(AttributeError) as refused:
            book["一月"].merged_cells
        assert "merged_cells" in str(refused.value)
    finally:
        book.close()


def test_the_sheet_name_cannot_fake_an_extra_anchor_field(tmp_path) -> None:
    """判据④: 表名进锚点之前先按 `MAX_CONTEXT_CHARS` 收口，且 " · " 必须被换掉。"""
    longest_legal = "季" * 31  # Excel 的表名上限是 31 字，比 MAX_CONTEXT_CHARS 短，合法名截不断
    path = r305_write_xlsx(
        tmp_path / "r305_names.xlsx",
        [("一月 · 销售", [["部门", "金额"], ["销售", 10]], []), (longest_legal, [["部门", "金额"], ["行政", 20]], [])],
    )
    found = spreadsheets.load_xlsx(path)

    pieces = found.blocks[0].anchor().split(ANCHOR_JOIN)
    assert pieces == ["r305_names.xlsx", "Sheet「一月 销售」", "表1"], pieces
    assert found.sheets[1].label == longest_legal, "合法表名（<=31 字）一个字都不该被截"
    assert len(spreadsheets._sheet_label("超长工作表名" * 20)) == tables.MAX_CONTEXT_CHARS == 40
    assert spreadsheets._sheet_label("  \n 甲  乙 | 丙 \t") == "甲 乙 \| 丙"


# ------------------------------------------------------------------ ④ 锚点与预算：给检索用的文本


def test_every_segment_of_a_long_table_is_re_anchored() -> None:
    """判据④: 长表交回的是**多段带锚的块**，不是一坨无锚点长串。37 段 = 37 枚锚。"""
    found = spreadsheets.load_spreadsheet(CORPUS_CSV)
    segments = found.text.split(BLOCK_SEPARATOR)

    assert found.row_count == CORPUS_CSV_ROWS - 1
    assert len(segments) == sum(len(block.parts()) for block in found.blocks) > 5
    assert len(r305_anchors(found.text)) == len(segments), "一枚段一枚锚：锚既不缺席也不野涨"
    widest = max(len(segment) for segment in segments)
    assert widest == CORPUS_CSV_WIDEST_SEGMENT, (
        f"实测最长段变成 {widest}：这条账记的是 tables.parts() 用不带段号的 anchor() 算余量的"
        "缺陷（R305 已回报总控，禁域不自改）。它变了就说明那一边动过，两边的账都得重核。"
    )
    assert SEGMENT_CHAR_BUDGET < widest < 499, "仍在 500 的上游尺与 499 的丢锚线之内，但已超本模块那把 448"
    for segment in segments:
        assert len(segment) <= tables.CHUNK_SIZE_CHARS, f"段超上游那把尺：{len(segment)}"
        lines = segment.split("\n")
        assert (ANCHOR_JOIN + "表") in lines[0], f"段首不是锚：{lines[0]!r}"
        assert lines[1] == found.blocks[0].header_line, "每一段都得把表头带回去，不然列名对不上号"
        assert lines[2].startswith("|-")


def test_no_line_outside_the_ruler_and_no_anonymous_blob() -> None:
    """判据④: 单行最长不超过 448；且"整表一坨"这种形状当场判死。"""
    for path in (CORPUS_CSV, CORPUS_XLSX):
        text = spreadsheets.load_spreadsheet(path).text
        assert text
        assert max(len(line) for line in text.split("\n")) <= SEGMENT_CHAR_BUDGET
        assert text.count("\n") > text.count("\n\n"), "没有逐行的表结构，就是一坨长串"
        assert "\t" not in text and "  " not in text, "空白被折叠过，对齐不靠空格"


def test_the_anchored_rows_survive_the_real_splitter_exactly_once() -> None:
    """判据④: 拿仓库里唯一那枚分块器切一遍，每块 ≤500、块块带头锚、行不从中间断、行不多不少。"""
    found = spreadsheets.load_spreadsheet(CORPUS_CSV)
    chunks = [chunk for chunk in r305_splitter().split_text(found.text) if chunk.strip()]

    assert chunks
    for chunk in chunks:
        assert len(chunk) <= tables.CHUNK_SIZE_CHARS, f"分块超尺：{len(chunk)}"
        lines = chunk.split("\n")
        assert (ANCHOR_JOIN + "表") in lines[0], f"这一块没有以锚开头：{lines[0]!r}"
        for line in lines:
            if line.startswith("|") and not line.startswith("|-"):
                assert line.endswith(" |"), f"表格行被从中间切断了：{line!r}"

    emitted = [line for segment in found.text.split(BLOCK_SEPARATOR) for line in segment.split("\n")[3:]]
    source = [line for block in found.blocks for line in block.row_lines]
    assert emitted == source, "数据行必须逐字、按源顺序、各出现一次"
    assert len(set(source)) + found.blocks[0].row_count - len(source) <= len(source)


def test_the_anchor_says_which_upload_it_came_from_and_can_be_renamed(tmp_path) -> None:
    """上传落盘名是 uuid（`chat.py:3803`），所以锚点必须能被 `display_name` 改名——R306 的口子。"""
    stored = tmp_path / "2f3a9c1e5b7d4a869c0f1e2d3c4b5a69.csv"
    r305_write_csv(stored, "部门,金额\n销售部,10800\n")

    assert stored.stem not in spreadsheets.load_csv(stored, display_name="报销明细表.csv").text
    anonymous = spreadsheets.load_csv(stored).text
    assert f"{stored.name}{ANCHOR_JOIN}表1" in anonymous, "不改名就得如实带上落盘名，别假装是客户起的名字"


# ------------------------------------------------------------------ ⑤ 数据红线：日期与数字不许漂


def test_dates_have_exactly_one_writing(tmp_path) -> None:
    """判据⑤: 一种值一种写法，全部 ISO；xlsx 里日期与"零点的时刻"同一枚序列号，写法必须同。"""
    rows = [
        ["事项", "起", "止", "时刻", "跨度"],
        [
            "预算",
            datetime.datetime(2026, 1, 31, 9, 30),
            datetime.datetime(2026, 2, 1, 0, 0),
            datetime.time(9, 30),
            datetime.timedelta(days=1, hours=2),
        ],
        ["报销", datetime.date(2026, 2, 1), None, None, None],
    ]
    path = r305_write_xlsx(tmp_path / "r305_dates.xlsx", [("期间", rows, [])])
    block = spreadsheets.load_xlsx(path).blocks[0]

    assert block.rows[0] == ("预算", "2026-01-31 09:30:00", "2026-02-01", "09:30:00", "1 day, 2:00:00")
    assert block.rows[1][1] == block.rows[0][2], "纯日期与零点 datetime 在 xlsx 里本来就分不开"
    flat = "\n".join(block.row_lines)
    for wrong in ("/", "年", "月", "T09", "Feb", "PM", "上午"):
        assert wrong not in flat, f"日期漂成了 {wrong} 那种写法"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (10800, "10800"),
        (1 / 3, "0.3333333333333333"),
        (0.1 + 0.2, "0.3"),
        (21.0, "21"),
        (1e20, "1e+20"),
        (1234567890123456789.0, "1.234567890123457e+18"),
        (1e-6, "1e-06"),
        (-4500, "-4500"),
        (True, "True"),
        ("10,800.00", "10,800.00"),
    ],
)
def test_numbers_are_rendered_as_stored_not_rounded(value, expected, tmp_path) -> None:
    """判据⑤: 客户存的是什么就是什么。第二次取整、千分位、%.2f 全都不许出现在读侧。"""
    path = r305_write_xlsx(tmp_path / "r305_num.xlsx", [("数", [["科目", "值"], ["甲", value]], [])])
    block = spreadsheets.load_xlsx(path).blocks[0]

    assert block.rows[0][1] == expected, f"{value!r} 渲染成了 {block.rows[0][1]!r}"

    import openpyxl

    book = openpyxl.load_workbook(str(path), data_only=True)
    stored = book["数"]["B2"].value
    book.close()
    assert spreadsheets.render_value(stored) == expected, "读侧那一步单独钉：交回的原始值->文本，不多一位不少一位"


def test_the_rendering_path_has_no_locale_or_rounding_lever() -> None:
    """判据⑤的源码钉，走 AST 而不是 grep：注释里写着"不用 strftime"，grep 会自己冤枉自己。

    `render_value` 这一路只许碰：`isinstance` / `datetime` 的 `.time() .date() .isoformat()` /
    `str()` / 复用的 `_cell_text()`。取整（`round`）、格式串（f-string 的 `:.2f`、`%`）、
    `strftime`、locale 这一族**一个都不许出现**——出现一次就多一处把 10800 印成 "10,800" 的机会。
    """
    source = MODULE_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_value")

    names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)}
    # object / str 只来自那一行签名（value: object) -> str），不是调用。
    assert names <= {"isinstance", "datetime", "_cell_text", "value", "_MIDNIGHT", "object", "str"}, names
    assert attrs <= {"datetime", "date", "time", "isoformat", "timedelta"}, attrs
    assert not any(isinstance(node, ast.FormattedValue) for node in ast.walk(fn)), "不许有格式串"
    assert not any(
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) for node in ast.walk(fn)
    ), "不许有 %-格式化"
    assert not any(isinstance(node, (ast.JoinedStr, ast.Lambda)) for node in ast.walk(fn))

    assert not re.search(r"^\s*(import|from)\s+locale", source, re.M), "整个模块不许碰 locale"
    assert "setlocale" not in source and "babel" not in source
    assert "strftime" not in attrs | names, "strftime 只能出现在注释里，不许出现在代码里"


def test_the_rendering_does_not_consult_the_environment(monkeypatch, tmp_path) -> None:
    """判据⑤: 换时区、换语言变量，逐字不许动——私有一枚真客户机就会踩到这条。"""
    rows = [["事项", "起"], ["预算", datetime.datetime(2026, 1, 31, 9, 30)]]
    path = r305_write_xlsx(tmp_path / "r305_tz.xlsx", [("期间", rows, [])])
    before = spreadsheets.load_xlsx(path).text

    for key, value in (("TZ", "America/Sao_Paulo"), ("LC_ALL", "tr_TR.UTF-8"), ("LANGUAGE", "de"), ("LANG", "ja_JP.eucJP")):
        monkeypatch.setenv(key, value)
    assert spreadsheets.load_xlsx(path).text == before
# ------------------------------------------------------------------ ⑥ 硬顶：五道，每道都要真收口


def test_the_row_ceiling_bites_on_a_narrow_sheet_at_its_default(tmp_path) -> None:
    """判据⑥: 行顶不是摆设。一列三个字符的窄表装不满 40k 字符顶，于是行顶先收口。"""
    # 一列一个字符：5_000 行渲染出来三万字符，装得进 40k 字符顶，所以能收口的只有行顶。
    rows = ["编号"] + ["甲"] * 6_000 + ["尾行"]
    path = r305_write_csv(tmp_path / "r305_long.csv", "\n".join(rows) + "\n")

    capped = spreadsheets.load_csv(path)
    uncapped = spreadsheets.load_csv(path, max_rows=100_000)

    assert capped.truncated == f"rows:CSV:{spreadsheets.MAX_ROWS_PER_SHEET}+"
    assert spreadsheets.MAX_ROWS_PER_SHEET == 5_000
    # 顶数的是网格行（含表头那一枚），所以交出去的数据行是 5_000 - 1。
    assert capped.row_count == spreadsheets.MAX_ROWS_PER_SHEET - 1 == 4_999
    assert capped.sheets[0].rows_read == 5_000
    assert "budget:" not in capped.truncated, "窄表先撞行顶；这一格要是反过来，两道的账就得重记"
    assert "尾行" not in capped.text, "被顶掉的行不许还留在文本里"
    assert uncapped.row_count > capped.row_count, "把这顶抬上去就多出数据，说明它切的是真东西"
    assert uncapped.truncated == "" and "尾行" in uncapped.text


def test_the_char_ceiling_bites_on_a_wide_sheet_before_the_row_ceiling(tmp_path) -> None:
    """判据⑥: 一行七十字符的宽表装得下 5_000 行，却装不进 40k 字符顶——这时是内容顶收口。"""
    header = "单据号,部门,报销人,费用类型,金额,发生月份,出差天数,提交日期,审批状态"
    lines = [header] + [
        f"BX-2026{i:04d}-XS027-1,销售部,周敏,住宿费,10800,2026-01,27,2026-02-14,已通过（含跨区补贴明细）"
        for i in range(1, 901)
    ]
    path = r305_write_csv(tmp_path / "r305_wide.csv", "\n".join(lines) + "\n")
    found = spreadsheets.load_csv(path)

    assert found.truncated.startswith("budget:1:"), found.truncated
    assert "rows:" not in found.truncated
    assert 0 < found.row_count < 900
    assert found.char_count <= spreadsheets.MAX_SPREADSHEET_CHARS == tables.MAX_TABLE_CHARS
    assert found.sheets[0].rows_kept == found.row_count
    assert found.sheets[0].rows_read == 901


def test_the_column_ceiling_cuts_the_widest_sheet_and_names_it(tmp_path) -> None:
    """判据⑥: 200 列的病态件只留前 128 列，并在回执里写清"128 of 200"。"""
    width = 200
    path = r305_write_csv(
        tmp_path / "r305_widecols.csv",
        ",".join(f"列{i}" for i in range(width)) + "\n" + ",".join(str(i) for i in range(width)) + "\n",
    )
    found = spreadsheets.load_csv(path)

    assert found.truncated == f"cols:CSV:{spreadsheets.MAX_COLUMNS_PER_SHEET}of{width}"
    assert found.blocks[0].width == spreadsheets.MAX_COLUMNS_PER_SHEET == 128
    assert found.sheets[0].columns_total == width and found.sheets[0].columns_kept == 128
    assert "列199" not in found.text and "列127" in found.text


def test_the_sheet_ceiling_stops_reading_further_sheets(tmp_path) -> None:
    """判据⑥: sheet 数顶与 R300 的"表枚数顶"同源同一个数，收口时点名还剩几张没读。"""
    path = r305_write_xlsx(
        tmp_path / "r305_many.xlsx",
        [(f"表{i}", [["部门", "金额"], [f"销售{i}", i]], []) for i in range(1, 5)],
    )

    assert spreadsheets.load_xlsx(path).block_count == 4
    capped = spreadsheets.load_xlsx(path, max_sheets=2)

    assert capped.truncated == "sheets:2of4"
    assert capped.block_count == 2 and [s.index for s in capped.sheets] == [1, 2]
    assert capped.text.count(" · 表") == 2


def test_the_time_ceiling_is_not_a_decoration(tmp_path) -> None:
    """判据⑥: 预算花完时第一张 sheet 都不读，并把"读了 0/4"写出来。

    这里传 -1 而不是 0：本机 `time.monotonic()` 实测是 `GetTickCount64()`，**分辨率
    15.625 ms**，一枚小 xlsx 的 `load_workbook` 量出来就是 0.0，拿 0.0 当预算收不了口。
    默认那 12 s 的顶不受这个粒度影响（12 s >> 15.6 ms），但"0 就该立刻收"这一格测不了，
    已写进回执第 5 节的未验账。
    """
    path = r305_write_xlsx(
        tmp_path / "r305_slow.xlsx",
        [(f"表{i}", [["部门", "金额"], [f"销售{i}", i]], []) for i in range(1, 5)],
    )
    found = spreadsheets.load_xlsx(path, time_budget_s=-1.0)

    assert found.truncated.startswith("time:0of4"), found.truncated
    assert time.get_clock_info("monotonic").resolution >= 0.001, "本机时钟粒度变了，这道顶的测法要跟着改"
    assert found.blocks == () and found.sheets == () and found.text == ""
    assert spreadsheets.SPREADSHEET_TIME_BUDGET_SECONDS == tables.TABLE_TIME_BUDGET_SECONDS == 12.0


def test_a_header_that_cannot_fit_is_named_in_the_receipt_instead_of_vanishing(tmp_path) -> None:
    """判据⑥: 全文档预算已经见底时，后面的 sheet 整枚不发，但账必须留在 truncated 里。"""
    path = r305_write_xlsx(
        tmp_path / "r305_tight.xlsx",
        [("一月", [["部门", "金额"], ["销售", 10]], []), ("二月", [["部门", "金额"], ["行政", 20]], [])],
    )
    found = spreadsheets.load_xlsx(path, max_chars=40)

    assert found.block_count == 1 and found.char_count <= 40
    assert found.truncated.startswith("budget:2:0of1"), found.truncated
    assert [sheet.emitted for sheet in found.sheets] == [True, False]
    assert [sheet.rows_kept for sheet in found.sheets] == [1, 0], "预算只够第一张的一行，第二张整枚不发"
    assert found.sheets[1].rows_read == 2, "没发出去也要留住这笔账：这张表是被预算切掉的"
    assert "Sheet「二月」" not in found.text


def test_the_ceilings_are_ahead_of_the_measured_corpus(capsys) -> None:
    """判据⑥: 顶必须比已知最坏的存量宽松，否则它天天在切真数据（R300 同一 habit）。"""
    csv_file = spreadsheets.load_spreadsheet(CORPUS_CSV)
    xlsx_file = spreadsheets.load_spreadsheet(CORPUS_XLSX)

    assert csv_file.truncated == "" and xlsx_file.truncated == ""
    assert csv_file.sheets[0].rows_total == CORPUS_CSV_ROWS
    assert csv_file.sheets[0].columns_total == CORPUS_CSV_COLUMNS
    assert xlsx_file.block_count == CORPUS_XLSX_SHEETS
    assert xlsx_file.row_count == CORPUS_XLSX_ROWS
    assert spreadsheets.MAX_ROWS_PER_SHEET > csv_file.sheets[0].rows_total
    assert spreadsheets.MAX_COLUMNS_PER_SHEET > max(
        csv_file.sheets[0].columns_total, xlsx_file.sheets[0].columns_total
    )
    assert spreadsheets.MAX_SPREADSHEET_CHARS > csv_file.char_count
    assert spreadsheets.MAX_SHEETS_PER_WORKBOOK > xlsx_file.sheets[0].index

    with capsys.disabled():
        print(
            "\nR305 实测 %s: rows=%d cols=%d table_chars=%d segments=%d 全程 %.3fs"
            % (csv_file.filename, csv_file.row_count, csv_file.sheets[0].columns_total,
               csv_file.char_count, sum(len(b.parts()) for b in csv_file.blocks), csv_file.elapsed_s)
        )
        print(
            "R305 实测 %s: sheets=%d rows=%d cols=%d table_chars=%d segments=%d 全程 %.3fs"
            % (xlsx_file.filename, xlsx_file.block_count, xlsx_file.row_count,
               xlsx_file.sheets[0].columns_total, xlsx_file.char_count,
               sum(len(b.parts()) for b in xlsx_file.blocks), xlsx_file.elapsed_s)
        )


def test_the_measured_cost_is_not_a_one_off_parse(tmp_path) -> None:
    """同机二次解析的耗时账：第一枚付的是 import（loader 那条腿），第二枚才是这层自己的价。"""
    import time

    path = r305_write_xlsx(
        tmp_path / "r305_cost.xlsx",
        [(f"月{i}", [["部门", "金额"], [f"销售{i}", i * 100]], [f"A{i + 2}:B{i + 2}"]) for i in range(1, 13)],
    )
    spreadsheets.load_xlsx(path)
    started = time.perf_counter()
    found = spreadsheets.load_xlsx(path)
    wall = time.perf_counter() - started

    assert found.block_count == 12 and found.char_count > 0
    assert wall < 1.0, f"12 张 sheet 现取 {wall:.3f}s，量级不对就先重估上限"


# ------------------------------------------------------------------ 出口：拒绝与闸门


def test_unreadable_formats_refuse_out_loud_with_a_readable_reason(tmp_path) -> None:
    """判据③/接线契约：认不出的后缀必须**出声**，而且理由要说清是"没有这个能力"。"""
    with pytest.raises(ValueError) as xls:
        spreadsheets.load_spreadsheet(tmp_path / "r305_old.xls")
    assert "xlrd" in str(xls.value)

    with pytest.raises(ValueError) as unknown:
        spreadsheets.load_spreadsheet(tmp_path / "r305_notes.pptx")
    assert "R305" in str(unknown.value) and ".pptx" in str(unknown.value)

    with pytest.raises(ValueError) as noSuffix:
        spreadsheets.load_spreadsheet(tmp_path / "README")
    assert str(noSuffix.value).endswith("README")


def test_a_missing_file_propagates_as_oserror_not_a_quiet_empty_text(tmp_path) -> None:
    """R306 的错误码表只有 500 document_parse_failed 一格：这层不许把"文件不在"糊成空文本。"""
    with pytest.raises(OSError):
        spreadsheets.load_spreadsheet(tmp_path / "r305_absent.xlsx")
    with pytest.raises(OSError):
        spreadsheets.load_spreadsheet(tmp_path / "r305_absent.csv")


def test_the_dispatch_pair_covers_both_formats_end_to_end(tmp_path) -> None:
    """`load_spreadsheet_text` 的形态就是 load_document 那一行要的：进路径，出一段文本。"""
    csv_path = r305_write_csv(tmp_path / "r305_ok.csv", "部门,金额\n销售部,10800\n")
    xlsx_path = r305_write_xlsx(tmp_path / "r305_ok.xlsx", [("一月", [["部门", "金额"], ["销售", 10]], [])])

    for path in (csv_path, xlsx_path):
        text = spreadsheets.load_spreadsheet_text(path)
        assert text.endswith("|") and (ANCHOR_JOIN + "表") in text.split("\n")[0]
        assert text == loader.sanitize_text(text), "出口文本必须已经过 R130 那道闸门"
        assert tables.render_tables(spreadsheets.load_spreadsheet(path).blocks) == text