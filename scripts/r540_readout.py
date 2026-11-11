# -*- coding: utf-8 -*-
"""R540 读数件：把 V2 #13/#14/#15 三条通道**离线各跑通一次**，交回可复算的读数。

判据射程（纸：docs/testing/r540-v2-channels-e2e.md）：
  ① 扫描件（#13）：`PIL` 现造的**零文本层**多页 PDF 过 `app/rag/loader.py` 的解析入口，
     逐页交回 `source` / OCR 文本前 40 字 / 耗时 / 栅格尺寸；跑之前先用 pypdf 自证零文本层。
     对照件（带文本层 + 带位图）必须走**非 OCR 腿**（判据④）。
  ② 降级形状（#13）：`ocr-empty`（第 4 页有图无字）与 `ocr-degraded`（`DOCUMENT_OCR_MAX_PAGES`
     收到 1，第 2-4 页没跑 ⇒ 必须是降级而不是"没字"）两枚都在同一份样本上复现，可复算。
  ③ 表格（#14）：带框线 PDF 与带真表格 DOCX 过 loader，交回 `table_channel` 那本账
     （tables/rows/segments/attached/degraded）＋正文里表格那几行的**实际形状**。
  ④ 电子表格（#15）：xlsx 与 csv 过 loader，行数列名空值一律读**通道自己交回的那一份**
     （`Spreadsheet.stats()`），不借 pandas 重算。

硬边界：**不打模型、不上传、不写库、不写 chroma、不动容器**。这里唯一被调用的入口是
`app/rag/loader.py` 的解析函数（外加 `app/documents/index_policy.py` 那枚纯函数，
用来把"索引里有字"这半句落到可核对的判定上，它不碰任何存储）。

跑法（工作目录 = 本工作树，解释器 = 主树 .venv）：

    python scripts/r540_samples.py --out %TEMP%\\r540
    python scripts/r540_readout.py --out %TEMP%\\r540 --case all
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 直接 `python scripts/r540_readout.py` 跗时 sys.path[0] 是 scripts/，仓库根不在里面。
#: 本件只**读** app/ 的解析入口，不写它一字节。
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
CASES = (
    "scan",
    "mixed",
    "lowq-only",
    "control",
    "degraded-limit",
    "table-pdf",
    "table-docx",
    "xlsx",
    "csv",
    "csv-pad",
)
HEAD_CHARS = 40
#: 只收这三枚 logger 的记录：降级与接线那几句都出在它们嘴里（loader/ocr/tables）。
LOGGERS = ("enterprise_brain",)


def _load_samples():
    spec = importlib.util.spec_from_file_location("r540_samples", REPO_ROOT / "scripts" / "r540_samples.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def capture_logs() -> Iterator[list[str]]:
    """把 app 侧日志按 `[LEVEL] name: message` 收进一个列表，交回**原文**而不是转述。"""
    collected: list[str] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(f"[{record.levelname}] {record.name}: {record.getMessage()}")

    handler = Collector(level=logging.DEBUG)
    roots = [logging.getLogger(name) for name in LOGGERS]
    previous = []
    for root in roots:
        previous.append((root, root.level, list(root.handlers)))
        root.addHandler(handler)
        root.setLevel(min(root.level or logging.INFO, logging.INFO))
    try:
        yield collected
    finally:
        for root, level, handlers in previous:
            root.handlers = handlers
            root.setLevel(level)


def sha256_head(path: Path, length: int = 12) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:length]


def sample_paths(out: Path) -> dict[str, Path]:
    return {
        "scan_pdf": out / "r540_scan.pdf",
        "control_pdf": out / "r540_control.pdf",
        "table_pdf": out / "r540_table.pdf",
        "table_docx": out / "r540_table.docx",
        "xlsx": out / "r540_sales.xlsx",
        "csv": out / "r540_sales.csv",
        "pad_csv": out / "r540_pad.csv",
        "mixed_pdf": out / "r540_mixed.pdf",
    }


def head(text: str, chars: int = HEAD_CHARS) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    return flat[:chars]


# ==================== ① #13 扫描件：逐页 source + 零文本层自证 ====================


def case_scan(out: Path, *, dpi: int | None) -> dict:
    from pypdf import PdfReader

    from app.rag import loader

    path = sample_paths(out)["scan_pdf"]
    reader = PdfReader(str(path))
    zero_layer = {
        "page_extract_text_chars": {index: len((page.extract_text() or "").strip()) for index, page in enumerate(reader.pages, 1)},
        "page_has_image_object": {
            index: bool(loader.page_has_image_object(page)) for index, page in enumerate(reader.pages, 1)
        },
    }
    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), dpi=dpi)
    pages = [
        {
            "page": page.page_number,
            "source": page.source,
            "is_scanned": page.is_scanned,
            "text_layer_chars": page.text_layer_chars,
            "has_image_object": page.has_image_object,
            "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
            "raster": list(page.raster_size),
            "note": page.note,
            "text_head": head(page.text),
        }
        for page in report.pages
    ]
    from app.documents import index_policy

    size = path.stat().st_size
    eligibility = index_policy.evaluate_index_eligibility(report.text, size_bytes=size)
    without = index_policy.evaluate_index_eligibility(
        loader.load_pdf(str(path), enable_ocr=False), size_bytes=size
    )
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "bytes": size,
        "precondition_zero_text_layer": zero_layer,
        "summary": report.summary(),
        "ocr_engine": report.ocr_engine,
        "ocr_dpi": report.ocr_dpi,
        "ocr_attempted": report.ocr_attempted,
        "ocr_available": report.ocr_available,
        "pages": pages,
        "source_counts": report.source_counts,
        "scanned_pages": list(report.scanned_page_numbers),
        "text_chars": len(report.text),
        "ocr_text_full": {str(page.page_number): page.text for page in report.pages if page.text},
        "degradation_notes": list(report.degradation_notes),
        "degradation_sentence": report.degradation_sentence,
        "index_gate_with_ocr": {"eligible": eligibility.eligible, "reason": eligibility.reason},
        "index_gate_without_ocr": {"eligible": without.eligible, "reason": without.reason},
        "logs": logs,
    }


def case_control(out: Path, *, dpi: int | None) -> dict:
    """判据④：带文本层的页一个字都不许再走 OCR——对照件就是钉这一格的。"""
    from pypdf import PdfReader

    from app.rag import loader

    path = sample_paths(out)["control_pdf"]
    reader = PdfReader(str(path))
    layer = {index: len((page.extract_text() or "").strip()) for index, page in enumerate(reader.pages, 1)}
    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), dpi=dpi)
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "text_layer_chars": layer,
        "has_image_object": {index: bool(loader.page_has_image_object(page)) for index, page in enumerate(reader.pages, 1)},
        "threshold": loader.scanned_page_text_char_threshold(),
        "summary": report.summary(),
        "ocr_attempted": report.ocr_attempted,
        "source_counts": report.source_counts,
        "pages": [
            {
                "page": page.page_number,
                "source": page.source,
                "is_scanned": page.is_scanned,
                "text_layer_chars": page.text_layer_chars,
                "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
                "text_head": head(page.text),
            }
            for page in report.pages
        ],
        "logs": logs,
    }


def case_mixed(out: Path, *, dpi: int | None) -> dict:
    """判据④ 的三面尺：同一份文件里 `ocr` / `text-layer` / `blank` 三形同时成立。

    这一枚**只有一页**会真打 rapidocr（另外两页分别是文本层页与空白页），
    所以它是三条腿里最便宜的端到端形状。
    """
    from pypdf import PdfReader

    from app.rag import loader

    path = sample_paths(out)["mixed_pdf"]
    reader = PdfReader(str(path))
    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), dpi=dpi)
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "text_layer_chars": {str(index): len((page.extract_text() or "").strip()) for index, page in enumerate(reader.pages, 1)},
        "has_image_object": {str(index): bool(loader.page_has_image_object(page)) for index, page in enumerate(reader.pages, 1)},
        "summary": report.summary(),
        "source_counts": report.source_counts,
        "pages": [
            {
                "page": page.page_number,
                "source": page.source,
                "note": page.note,
                "is_scanned": page.is_scanned,
                "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
                "text_head": head(page.text),
            }
            for page in report.pages
        ],
        "logs": logs,
    }


def case_low_quality(out: Path, *, dpi: int | None) -> dict:
    """把 #13 那枚"故意糊"的单独关一页跑：它落到哪一形？下游还剩什么？

    读数结论写进纸：糊页交回的是 `ocr-empty` 而**不是** `ocr-degraded`——通道把它当成
    "这页确实没有字"，与一张真无字底图同形，既没有降级句也没有 WARNING。
    """
    from pypdf import PdfReader

    from app.documents import index_policy
    from app.rag import loader

    samples = _load_samples()
    path = out / "r540_lowq.pdf"
    samples.build_pdf(
        path,
        [{"image": samples.render_text_image(samples.SCAN_PAGES[samples.LOW_QUALITY_PAGE], **samples.LOW_QUALITY_STYLE)}],
    )
    reader = PdfReader(str(path))
    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), dpi=dpi)
    page = report.pages[0]
    gate = index_policy.evaluate_index_eligibility(report.text, size_bytes=path.stat().st_size)
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "printed_lines": list(samples.SCAN_PAGES[samples.LOW_QUALITY_PAGE]),
        "style": dict(samples.LOW_QUALITY_STYLE),
        "text_layer_chars": len((reader.pages[0].extract_text() or "").strip()),
        "has_image_object": bool(loader.page_has_image_object(reader.pages[0])),
        "summary": report.summary(),
        "page_source": page.source,
        "page_note": page.note,
        "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
        "text_chars": len(report.text),
        "degradation_notes": list(report.degradation_notes),
        "index_gate": {"eligible": gate.eligible, "reason": gate.reason},
        "logs": logs,
    }


def case_degraded_limit(out: Path, *, dpi: int | None) -> dict:
    """`ocr-degraded` 的可复算造法：把单次页数顶收到 1，后 3 页**根本没跑** ⇒ 必须是降级。

    为什么不用"糊图"造降级：糊图只会走成 `ocr`（读出残字）或 `ocr-empty`（真的没字），
    那是识别质量，不是通道降级——`ocr_pages` 里 `ocr-degraded` 的三条来源
    （引擎不可用 / 页数触顶 SKIPPED / 栅格化或识别抛错）没有一条是"图不够清楚"。
    """
    from app.rag import loader

    path = sample_paths(out)["scan_pdf"]
    previous = os.environ.get(loader.ocr_channel.OCR_MAX_PAGES_ENV)
    os.environ[loader.ocr_channel.OCR_MAX_PAGES_ENV] = "1"
    try:
        with capture_logs() as logs:
            report = loader.extract_pdf(str(path), dpi=dpi)
    finally:
        if previous is None:
            os.environ.pop(loader.ocr_channel.OCR_MAX_PAGES_ENV, None)
        else:
            os.environ[loader.ocr_channel.OCR_MAX_PAGES_ENV] = previous
    return {
        "file": path.name,
        "env": {loader.ocr_channel.OCR_MAX_PAGES_ENV: "1"},
        "summary": report.summary(),
        "source_counts": report.source_counts,
        "ocr_available": report.ocr_available,
        "degradation_notes": list(report.degradation_notes),
        "degradation_sentence": report.degradation_sentence,
        "pages": [
            {
                "page": page.page_number,
                "source": page.source,
                "note": page.note,
                "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
                "text_head": head(page.text),
            }
            for page in report.pages
        ],
        "logs": logs,
    }


# ==================== ③ #14 表格：账 + 正文里表格那几行的实际形状 ====================


def _table_shape(text: str) -> dict:
    """把正文里"表格那几行"原样切出来，证明结构在位而不是被拍平成空格串。"""
    lines = text.splitlines()
    pipe = [line for line in lines if line.startswith("|")]
    anchors = [line for line in lines if " · " in line and not line.startswith("|")]
    return {
        "line_count": len(lines),
        "anchor_lines": anchors,
        "pipe_line_count": len(pipe),
        "pipe_lines": pipe,
        "pipe_cells_per_line": [len([cell for cell in line.strip().strip("|").split("|")]) for line in pipe],
        "longest_run_of_blank_cells": max(
            (
                len(re.findall(r"(?:\|\s+)", line))
                for line in pipe
                if not re.fullmatch(r"\|(?:---\|)+", line)
            ),
            default=0,
        ),
    }


def _tables_account(report) -> dict:
    tables = report.tables
    return {
        "summary": tables.summary(),
        "source": tables.source,
        "tables": tables.tables,
        "rows": tables.rows,
        "segments": tables.segments,
        "table_chars": tables.table_chars,
        "prose_chars": tables.prose_chars,
        "pages_scanned": tables.pages_scanned,
        "page_count": tables.page_count,
        "truncated": tables.truncated,
        "degraded": tables.degraded,
        "attached": tables.attached,
        "has_prose": tables.has_prose,
    }


def case_table_pdf(out: Path) -> dict:
    from app.rag import loader
    from app.rag import tables as table_channel

    path = sample_paths(out)["table_pdf"]
    with capture_logs() as logs:
        extraction = loader.extract_pdf_with_tables(str(path))
    text = extraction.text
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "log_prefix_constants": {
            "TABLE_TRUNCATION_LOG_PREFIX": loader.TABLE_TRUNCATION_LOG_PREFIX,
            "TABLE_CHANNEL_LOG_PREFIX": loader.TABLE_CHANNEL_LOG_PREFIX,
            "BLOCK_SEPARATOR_repr": repr(table_channel.BLOCK_SEPARATOR),
        },
        "wiring_log_line": next((line for line in logs if "表格接线" in line), ""),
        "tables": _tables_account(extraction),
        "pdf_page_sources": extraction.pdf.source_counts if extraction.pdf else {},
        "shape": _table_shape(text),
        "text_head": head(text, 200),
        "duplicate_cell_check": {
            token: text.count(token) for token in ("region", "East", "45600", "zhang", "North")
        },
        "logs": logs,
    }


def case_table_docx(out: Path) -> dict:
    from app.rag import loader

    path = sample_paths(out)["table_docx"]
    with capture_logs() as logs:
        extraction = loader.extract_docx_with_tables(str(path))
    text = extraction.text
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "wiring_log_line": next((line for line in logs if "表格接线" in line), ""),
        "tables": _tables_account(extraction),
        "shape": _table_shape(text),
        "text_head": head(text, 200),
        "duplicate_cell_check": {token: text.count(token) for token in ("大区", "华东", "45600", "张敏", "华北")},
        "logs": logs,
    }


# ==================== ④ #15 电子表格：只读通道自己交回的那一份账 ====================


def _spreadsheet_account(spreadsheet) -> dict:
    return {
        "summary": spreadsheet.summary(),
        "stats": {key: value for key, value in spreadsheet.stats().items() if key != "sheets_detail"},
        "sheets_detail": [sheet.__dict__ for sheet in spreadsheet.sheets],
        "blocks": [
            {
                "ordinal": block.ordinal,
                "page": block.page,
                "header": list(block.header),
                "width": block.width,
                "row_count": block.row_count,
                "rows": [list(row) for row in block.rows],
                "anchor": block.anchor(),
                "parts": len(block.parts()),
                "char_count": block.char_count,
            }
            for block in spreadsheet.blocks
        ],
        "shape": _table_shape(spreadsheet.text),
        "text_head": head(spreadsheet.text, 200),
    }


def _spreadsheet_case(out: Path, key: str) -> dict:
    from app.rag import loader
    from app.rag import spreadsheets as spreadsheet_channel

    path = sample_paths(out)[key]
    channel_report = spreadsheet_channel.load_spreadsheet(str(path))
    with capture_logs() as logs:
        body = loader.load_document(str(path), display_name=path.name)
        with_reports = loader.extract_document_with_reports(str(path), display_name=path.name)
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "bytes": path.stat().st_size,
        "display_name": path.name,
        "channel": _spreadsheet_account(channel_report),
        "loader_body_chars": len(body),
        "loader_equals_channel_text": body.strip() == channel_report.text.strip(),
        "loader_lines": body.splitlines()[:6],
        "with_reports": {
            "text_equals_load_document": with_reports.text == body,
            "tables_source": with_reports.tables.source,
            "tables_summary": with_reports.tables.summary(),
            "pdf": with_reports.pdf.source_counts if with_reports.pdf else None,
        },
        "nul_in_text": "\x00" in body,
        "logs": logs,
    }


def case_xlsx(out: Path) -> dict:
    return _spreadsheet_case(out, "xlsx")


def case_csv(out: Path) -> dict:
    return _spreadsheet_case(out, "csv")


def run_case(case: str, out: Path, *, dpi: int | None) -> dict:
    if case == "scan":
        return case_scan(out, dpi=dpi)
    if case == "mixed":
        return case_mixed(out, dpi=dpi)
    if case == "lowq-only":
        return case_low_quality(out, dpi=dpi)
    if case == "control":
        return case_control(out, dpi=dpi)
    if case == "degraded-limit":
        return case_degraded_limit(out, dpi=dpi)
    if case == "table-pdf":
        return case_table_pdf(out)
    if case == "table-docx":
        return case_table_docx(out)
    if case == "csv-pad":
        return _spreadsheet_case(out, "pad_csv")
    if case in {"xlsx", "csv"}:
        return _spreadsheet_case(out, case)
    raise KeyError(f"未知 case：{case}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R540 三条通道离线读数")
    parser.add_argument("--out", required=True, help="样本目录（与 r540_samples.py --out 同一个）")
    parser.add_argument("--case", default="all", help="、".join(CASES) + " 或 all")
    parser.add_argument("--dpi", type=int, default=None, help="OCR 栅格 DPI（缺省走产品默认 200）")
    args = parser.parse_args(argv)
    out = Path(args.out).expanduser().resolve()
    if REPO_ROOT == out or REPO_ROOT in out.parents:
        raise SystemExit(f"R540 读数件的样本目录必须在仓外，拒绝 {out}")
    samples = sample_paths(out)
    missing = [str(path) for path in samples.values() if not path.is_file()]
    if missing:
        raise SystemExit("样本不存在，先跑 scripts/r540_samples.py --out " + str(out) + "；缺 " + "、".join(missing))
    chosen = list(CASES) if args.case == "all" else [item.strip() for item in args.case.split(",") if item.strip()]
    unknown = [item for item in chosen if item not in CASES]
    if unknown:
        raise SystemExit(f"未知 case：{'、'.join(unknown)}；可用：{'、'.join(CASES)}")
    result = {
        "tool": "scripts/r540_readout.py",
        "out": str(out),
        "samples": {key: {"sha256_12": sha256_head(path), "bytes": path.stat().st_size} for key, path in samples.items()},
        "cases": {case: run_case(case, out, dpi=args.dpi) for case in chosen},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())