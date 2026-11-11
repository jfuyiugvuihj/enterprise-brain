# -*- coding: utf-8 -*-
r"""R540 · #14 表格通道与 #15 电子表格通道的常驻钉：离线各跑一次，账与正文都读**通道自己交回的那一份**。

钉什么（对应派工词③④）：
 #14 表格：表结构进的是**带来源锚的 markdown**，不是被拍平成一片空格——
   ① 每一枚表行在正文里恰好一次（`| 华东 | 128 | ... |` 全文计数 == 1，散文腿不许再吐一遍）；
   ② 每行的竖线数与列数一致，单元格不是一串空格；
   ③ `table_channel` 真被走到：账里 `source`/`tables`/`rows`/`segments` 非零，
      出口日志逐字含在册前缀（`loader.TABLE_CHANNEL_LOG_PREFIX` 与接线那一句）；
   ④ 表格通道**塌了**与**这份文档没有表**是两句话：`degraded` 点名异常类型，
      正文退回纯散文；页数顶触顶时 `[R304] 表格预算触顶` 必须出声（判据⑤ 不许静默）。
 #15 电子表格：行数/列名/空值三把尺读 `SheetReport` 交回的那一份（🔴 全件没有一处 pandas 重算），
   并把三种空白各自钉在一把尺上：只有表头有值的列**保留**、连表头都空的尾随列**丢掉**、
   整行空的**进网格之前丢掉**；日期一种值只给一种写法；合并单元格覆盖位取左上角。

样本一律件内自造、落 tmp；`app/rag/**` 与 `tests/fixtures/**` 一字节没动。
"""
from __future__ import annotations

import datetime
import importlib.util
import logging
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.rag import loader  # noqa: E402
from app.rag import spreadsheets as spreadsheet_channel  # noqa: E402
from app.rag import tables as table_channel  # noqa: E402


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


samples = _load("r540_samples_r1415", "scripts/r540_samples.py")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """#14/#15 的四件样本：带框线 PDF、带真表格 DOCX、xlsx、csv，外加一枚"空白三形"件。"""
    target = tmp_path_factory.mktemp("r540_r1415")
    samples.build_all(target)
    return {
        "table_pdf": str(target / "r540_table.pdf"),
        "table_docx": str(target / "r540_table.docx"),
        "xlsx": str(target / "r540_sales.xlsx"),
        "csv": str(target / "r540_sales.csv"),
        "pad_csv": str(target / "r540_pad.csv"),
        "scan_pdf": str(target / "r540_scan.pdf"),
        "mixed_pdf": str(target / "r540_mixed.pdf"),
    }


def _pipe_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("|")]


def _anchor_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if table_channel.ANCHOR_JOIN in line and not line.startswith("|")]


# ==================== #14 · 表格通道真被走到，而且交回的是结构 ====================


def test_docx_table_channel_is_attached_and_reports_its_own_numbers(corpus):
    extraction = loader.extract_docx_with_tables(corpus["table_docx"])
    report = extraction.tables
    assert report.source == "docx"
    assert report.tables == 1 and report.rows == len(samples.DOCX_TABLE_ROWS)
    assert report.segments == 1
    assert report.degraded == "" and report.truncated == ""
    assert report.attached is True, report.summary()
    assert report.has_prose is True, "散文在位，has_prose 数的是散文那一半"


@pytest.mark.parametrize(
    "key,header,rows,anchor_tail",
    [
        ("table_docx", samples.DOCX_TABLE_HEADER, samples.DOCX_TABLE_ROWS, "表1"),
        ("table_pdf", samples.PDF_TABLE_HEADER, samples.PDF_TABLE_ROWS, "表1"),
    ],
)
def test_table_reaches_the_body_as_markdown_not_as_a_flattened_string(key, header, rows, anchor_tail, corpus):
    if key == "table_pdf":
        extraction = loader.extract_pdf_with_tables(corpus[key])
    else:
        extraction = loader.extract_docx_with_tables(corpus[key])
    text = extraction.text
    lines = text.splitlines()
    pipes = _pipe_lines(text)
    header_line = "| " + " | ".join(header) + " |"
    separator = "|" + "|".join(["---"] * len(header)) + "|"

    assert header_line in lines, "表头行没进正文"
    assert separator in lines, "markdown 分隔行没进正文 —— 表格被拍平了"
    assert _anchor_lines(text) and any(anchor_tail in line for line in _anchor_lines(text))
    for values in rows:
        row_line = "| " + " | ".join(values) + " |"
        assert lines.count(row_line) == 1, f"表行重复或缺席：{row_line}"
    # 每一行的竖线格数 == 列数：这一条红，就意味着某一格被换成了一片空格
    widths = {len(line.split("|")) - 2 for line in pipes}
    assert widths == {len(header)}, f"行列宽不齐，表格被压扁：{widths}"
    for line in pipes:
        if line == separator:
            continue
        assert not re.search(r"\|\s{2,}\|", line), f"表格里出现空格占位：{line}"
    assert "\x00" not in text


def test_pdf_table_cells_are_not_spilled_twice(corpus):
    """判据①：散文腿（pdfplumber 扣掉表框）与表格段不能并存同一枚表 ⇒ 每格全文恰好一次。"""
    extraction = loader.extract_pdf_with_tables(corpus["table_pdf"])
    text = extraction.text
    for value in ("45600", "zhang", "128"):
        assert text.count(value) == 1, f"{value} 出现了 {text.count(value)} 次 = 同一枚表吐了两次"
    assert extraction.pdf is not None
    assert set(extraction.pdf.source_counts) == {loader.PAGE_SOURCE_TEXT_LAYER}


def test_pdf_table_prose_page_still_arrives_first(corpus):
    extraction = loader.extract_pdf_with_tables(corpus["table_pdf"])
    lines = extraction.text.splitlines()
    prose_index = next(index for index, line in enumerate(lines) if line.startswith("Appendix B"))
    table_index = next(index for index, line in enumerate(lines) if line.startswith("| region"))
    assert prose_index < table_index, "表格段是追加的，不该跑到正文前面"
    assert extraction.tables.page_count == 2 and extraction.tables.pages_scanned == 2


def test_table_channel_log_lines_are_the_inventoried_ones(corpus, caplog):
    """点名 `table_channel` 有没有被走到：读**真发出来的那一句**日志原文，不是复述。"""
    assert loader.TABLE_CHANNEL_LOG_PREFIX == "[R304] 表格通道"
    assert loader.TABLE_TRUNCATION_LOG_PREFIX == "[R304] 表格预算触顶"
    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        extraction = loader.extract_docx_with_tables(corpus["table_docx"])
    wiring = [record.getMessage() for record in caplog.records if "表格接线" in record.getMessage()]
    assert wiring, "接线那一句没出声 = 表格通道没被走到，或者账被吞了"
    assert "source=docx" in wiring[0] and "tables=1" in wiring[0]
    assert extraction.tables.summary() in wiring[0]


def test_a_broken_table_channel_never_lies_about_there_being_no_table(corpus, monkeypatch, caplog):
    """表格通道自己塌了：账里 `degraded` 点名异常，正文退回纯散文，`attached` 必须 False。"""
    original = table_channel.extract_document

    def explode(*args, **kwargs):
        raise RuntimeError("R540 反证：pdfplumber 起不来")

    monkeypatch.setattr(table_channel, "extract_document", explode)
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        extraction = loader.extract_pdf_with_tables(corpus["table_pdf"])
    monkeypatch.setattr(table_channel, "extract_document", original)

    assert "RuntimeError" in extraction.tables.degraded, extraction.tables.degraded
    assert extraction.tables.attached is False
    assert "| region" not in extraction.text, "塌了的那一腿不许留下半枚表格段"
    assert "Appendix B" in extraction.text, "退回的必须是完整纯散文"
    assert extraction.pdf is not None and extraction.pdf.page_count == 2
    warns = [record.getMessage() for record in caplog.records if loader.TABLE_CHANNEL_LOG_PREFIX in record.getMessage()]
    assert warns, "表格通道塌了要出声"


def test_page_ceiling_on_the_table_leg_is_reported_not_swallowed(corpus, monkeypatch, caplog):
    """页数顶触顶：正文一页字都不许少（逐页账回补），但 `[R304] 表格预算触顶` 必须点名缺哪几页。"""
    original = table_channel.extract_document

    def one_page_only(path, **kwargs):
        kwargs["max_pages"] = 1
        return original(path, **kwargs)

    monkeypatch.setattr(table_channel, "extract_document", one_page_only)
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        extraction = loader.extract_pdf_with_tables(corpus["table_pdf"])
    monkeypatch.setattr(table_channel, "extract_document", original)

    assert extraction.tables.truncated.startswith("pages:"), extraction.tables.truncated
    notice = extraction.tables.truncated_notice
    assert "页数上限" in notice and "未走到的页为第 2-2 页" in notice, notice
    assert "45600" in extraction.text, "表格腿被切断不该把第 2 页的正文一起吞掉"
    warns = [record.getMessage() for record in caplog.records if loader.TABLE_TRUNCATION_LOG_PREFIX in record.getMessage()]
    assert warns, "触顶必须出声（判据⑤）"


def test_a_tableless_document_returns_today_body_byte_for_byte(corpus):
    """0 表的那条岔路：正文逐字等于纯解析输出，表格账写明「参与了、一枚表都没抽到」。"""
    pure = loader.extract_pdf(corpus["mixed_pdf"], enable_ocr=False)
    wired = loader.extract_pdf_with_tables(corpus["mixed_pdf"], enable_ocr=False)
    assert wired.text.strip(), "混合件第 2 页带文本层，纯散文腿就该交出那一段字"
    assert wired.text == pure.text
    assert wired.tables.source == "pdf"
    assert wired.tables.tables == 0 and wired.tables.degraded == ""
    assert wired.tables.attached is False, "attached 认的是「真接上了表」，0 表不算"


# ==================== #15 · 电子表格：行/列/空值三把尺各读通道那一份 ====================


def _sheet(corpus, key):
    return spreadsheet_channel.load_spreadsheet(corpus[key])


def test_xlsx_row_and_column_ledger_matches_the_inventoried_rulers(corpus):
    book = _sheet(corpus, "xlsx")
    first = book.sheets[0]
    assert first.label == "一月销售"
    # rows_total = 这个格式自己声称的行数；rows_read = 清掉空行之后；rows_kept = 交出去的 data 行
    assert first.rows_total == 7, first.rows_total
    assert first.rows_read == len(samples.SHEET_ROWS) + 1, first.rows_read
    assert first.rows_kept == len(samples.SHEET_ROWS), first.rows_kept
    assert first.blank_rows_dropped == 2, first.blank_rows_dropped
    assert first.columns_total == len(samples.SHEET_COLUMNS)
    assert first.columns_kept == len(samples.SHEET_COLUMNS)
    assert first.empty_columns_dropped == 0, "只有表头有值的列不许丢：列名本身就是可检索的事实"
    assert first.spans == 1, "F2:F3 那一枚合并单元格要能在账里数到"
    assert first.state == "visible" and first.emitted is True
    assert book.sheets[1].label == "汇总" and book.sheets[1].rows_kept == 2
    assert book.truncated == "" and book.skipped_sheets == 0
    assert book.summary()["blocks"] == 2 and book.summary()["rows"] == len(samples.SHEET_ROWS) + 2


def test_xlsx_cells_are_rendered_by_the_channels_own_rules(corpus):
    book = _sheet(corpus, "xlsx")
    block = book.blocks[0]
    assert block.header == tuple(samples.SHEET_COLUMNS)
    rows = [list(row) for row in block.rows]
    assert rows[0] == ["SO-1001", "杭州云栖科技有限公司", "2026-01-05", "120", "0.15", "月结", ""]
    assert rows[1] == ["SO-1002", "苏州工业园区某某厂", "2026-01-06", "77", "", "月结", ""], rows[1]
    assert rows[2] == ["SO-1003", "", "2026-01-07", "", "0.2", "现结", ""], rows[2]
    assert rows[3] == ["SO-1004", "上海临港装备有限公司", "2026-01-08", "15", "0", "", ""], rows[3]
    assert "\x00" not in book.text
    assert " · 合并单元格1处" in block.anchor()
    assert "Sheet「一月销售」" in block.anchor()


def test_one_value_gets_one_spelling_in_the_sheet_channel():
    """判据⑤：日期只有一种写法，空值只有一种落法，数字不做第二次取整。"""
    assert spreadsheet_channel.render_value(None) == ""
    assert spreadsheet_channel.render_value(datetime.date(2026, 1, 5)) == "2026-01-05"
    assert spreadsheet_channel.render_value(datetime.datetime(2026, 1, 5, 0, 0)) == "2026-01-05"
    assert spreadsheet_channel.render_value(datetime.datetime(2026, 1, 5, 13, 45, 6)) == "2026-01-05 13:45:06"
    assert spreadsheet_channel.render_value(0.30000000000000004) == "0.30000000000000004"
    # 渲染层不做第二次取整：float 0.0 交回 "0.0"。xlsx 那一格里读到的是 "0"，那是
    # openpyxl **写入侧** safe_string 把 0.0 落盘成 0（读回来就是 int），不是这里改的口；
    # 那一腿端到端另有凭据（test_xlsx_cells_are_rendered_by_the_channels_own_rules）。
    assert spreadsheet_channel.render_value(0.0) == "0.0"
    assert spreadsheet_channel.render_value(0) == "0"
    assert spreadsheet_channel.render_value(True) == "True"


def test_csv_ledger_reads_encoding_and_delimiter_off_the_channel(corpus):
    book = _sheet(corpus, "csv")
    sheet = book.sheets[0]
    assert book.source == "csv" and book.encoding == "utf-8" and book.delimiter == ","
    assert book.summary()["delimiter"] == "comma"
    assert sheet.rows_total == len(samples.CSV_BODY) + 1
    assert sheet.rows_read == len(samples.CSV_BODY) + 1
    assert sheet.rows_kept == len(samples.CSV_BODY)
    assert sheet.columns_kept == len(samples.SHEET_COLUMNS)
    assert book.blocks[0].header == tuple(samples.SHEET_COLUMNS)
    assert book.blocks[0].rows[1] == ("SO-1002", "苏州工业园区某某厂", "2026-01-06", "77", "", "", "")
    assert book.blocks[0].anchor() == "r540_sales.csv · 表1"


def test_the_three_kinds_of_blank_land_on_three_different_rulers(corpus):
    """递宽行 + 中间空行：`columns_total` 10 / `columns_kept` 7 / 空列 3 / 空行 1，各归各的尺。"""
    book = _sheet(corpus, "pad_csv")
    sheet = book.sheets[0]
    assert sheet.rows_total == 4, sheet.rows_total
    assert sheet.rows_read == 3 and sheet.blank_rows_dropped == 1
    assert sheet.columns_total == 10 and sheet.columns_kept == 7
    assert sheet.empty_columns_dropped == 3
    assert book.blocks[0].header == tuple(samples.SHEET_COLUMNS), "砍掉的是没有名字的尾随列，表头一枚不少"
    assert book.blocks[0].rows[0] == ("SO-2001", "杭州云栖科技有限公司", "2026-02-01", "9", "0.1", "月结", "")
    assert "| 附件 |" in book.text


def test_load_document_dispatches_spreadsheets_and_rewrites_the_anchor_name(corpus):
    body = loader.load_document(corpus["csv"])
    assert body.strip() == spreadsheet_channel.load_spreadsheet_text(corpus["csv"]).strip()
    assert body.splitlines()[0] == "r540_sales.csv · 表1"
    renamed = loader.load_document(corpus["csv"], display_name="客户上传的一月明细.csv")
    assert renamed.splitlines()[0] == "客户上传的一月明细.csv · 表1"
    assert renamed != body, "display_name 只改锚点第一段，正文其余逐字不变"
    assert renamed.splitlines()[1:] == body.splitlines()[1:]


def test_spreadsheet_exit_takes_the_same_sanitize_gate_as_every_load_leg(corpus):
    """R130 那句「每一个 load_* 出口都过同一把尺」：电子表格这一支不许例外。"""
    import inspect

    source = inspect.getsource(loader.load_spreadsheet)
    assert "sanitize_text" in source
    assert "spreadsheet_channel.load_spreadsheet_text" in source
    for key in ("xlsx", "csv", "pad_csv"):
        assert "\x00" not in loader.load_document(corpus[key])


def test_legacy_xls_is_still_refused_out_loud(corpus, tmp_path):
    """在册口径：`.xls` 不进这一格（openpyxl 读不了旧二进制，依赖里也没有 xlrd）⇒ 分派出口出声拒绝。"""
    legacy = tmp_path / "r540_legacy.xls"
    legacy.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert ".xls" in spreadsheet_channel.UNSUPPORTED_SUFFIXES
    with pytest.raises(ValueError) as refused:
        loader.load_document(str(legacy))
    assert "Unsupported file format" in str(refused.value)


def test_the_reported_exit_keeps_the_documented_asymmetry_for_spreadsheets(corpus, tmp_path):
    """`extract_document_with_reports` 对电子表格交回的是「表格通道未参与」那一份真账，不是漏账。"""
    extraction = loader.extract_document_with_reports(corpus["csv"], display_name="客户上传的一月明细.csv")
    assert extraction.text == loader.load_document(corpus["csv"], display_name="客户上传的一月明细.csv")
    assert extraction.tables.source == "", "source 空串 = 表格通道没参与，与「参与了没抽到表」是两句话"
    assert extraction.tables.tables == 0 and extraction.tables.degraded == ""
    assert extraction.pdf is None, "非 PDF 没有逐页来源账"
    assert extraction.tables.prose_chars == len(extraction.text.strip())


@pytest.mark.parametrize("key", ["xlsx", "csv", "pad_csv"])
def test_spreadsheet_bodies_reach_the_index_gate(key, corpus):
    """最后一格口径：这三份表格出来的正文要能过 R49 那道入索引判定（不写库，只看纯函数怎么判）。"""
    from app.documents import index_policy

    path = Path(corpus[key])
    body = loader.load_document(str(path), display_name=path.name)
    verdict = index_policy.evaluate_index_eligibility(body, size_bytes=path.stat().st_size)
    assert verdict.eligible is True, f"{key} 被入索引闸门拒了：{verdict.reason}"