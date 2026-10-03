# -*- coding: utf-8 -*-
"""R599 读数件：把 ``docs/testing/fixtures/r599-scan-demo.pdf`` 走在册 OCR 腿**真跑一次**，交回逐页读数。

判据② 要的三句话，逐页各答一次（不整件二选一）：
 「这一页是不是扫描页」→ ``is_scanned`` / ``text_layer_chars`` / ``has_image_object``；
 「OCR 出没出字」    → ``source``（``ocr`` 出字 / ``ocr-empty`` 图里确实没字）+ ``text_head``；
 「哪几页没跑成」    → ``source=ocr-degraded`` + ``note``（原因原文），``degraded-limit`` 与
                       ``ocr-off`` 两案专门把这一形复现一遍（触顶 / 关掉通道），可复算。

🔴 一次性解析（判据③）：本件**只读**那份 PDF，不落库、不建索引、不发向量、不写 ``data/**``、
不碰 ``documents/**``；唯一被调用的入口是 ``app/rag/loader.py``（外加 ``app/api/v1/chat.py``
里那枚在册消费方函数 ``_pdf_extraction_cell``，用于判据④ 的 live 凭据）。不打模型。

🔴 必须先 ``cd`` 到仓库之外再跑（判据④ 的副作用实测，本件现读）：``import app.api.v1.chat``
在 import 期就按 ``./chroma_db``（**相对 CWD**，默认值在 ``app/rag/retriever.py:1018``）建
Chroma 持久客户端，并顺手建出 ``./data``、``./documents`` 两个目录 ⇒ 在工作树里跑它会把
``chroma_db/chroma.sqlite3`` 改脏（本班 15:49:56 实测踩到一次，已按 HEAD blob 逐字节还原）。
``require_cwd_outside_repo`` 就是这一格的把手：CWD 落在仓内直接拒绝，缺什么也不许改 ``app/**``。

跑法（工作目录 = 仓库之外，解释器 = 主树 .venv）：

    cd %TEMP%\\eb103\\r599_cwd
    python C:\\repo\\scripts\\r599_readout.py --case all
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURE = REPO_ROOT / "docs" / "testing" / "fixtures" / "r599-scan-demo.pdf"

CASES = (
    "probe",
    "scan",
    "ocr-off",
    "repeat",
    "degraded-limit",
    "receipt",
)

HEAD_CHARS = 60
LOGGERS = ("enterprise_brain",)

#: 判据② 的三句话按页码收成一行，纸面上直接可贴。
PER_PAGE_KEYS = (
    "page",
    "is_scanned",
    "source",
    "text_layer_chars",
    "has_image_object",
    "ocr_elapsed_ms",
    "raster",
    "note",
    "text_head",
)


def require_cwd_outside_repo() -> None:
    cwd = Path.cwd().resolve()
    if cwd == REPO_ROOT or REPO_ROOT in cwd.parents:
        raise SystemExit(
            "🔴 本件必须在仓库之外运行：import app.api.v1.chat 会按相对 CWD 建 ./chroma_db/"
            "./data/./documents，在工作树里跑会把 chroma_db/chroma.sqlite3 改脏。"
            f" 当前 CWD={cwd}，请先 cd 到仓外（例如 %TEMP%\\eb103\\r599_cwd）再跑。"
        )


@contextlib.contextmanager
def capture_logs() -> Iterator[list[str]]:
    """把 app 侧日志按 ``[LEVEL] name: message`` 收进列表，交回原文而不是转述。"""
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


def head(text: str, chars: int = HEAD_CHARS) -> str:
    flat = re.sub(r"\s+", " ", text or "").strip()
    return flat[:chars]


def sha256_head(path: Path, length: int = 12) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:length]


def precondition(path: Path) -> dict:
    """跑 OCR 之前先自证「无文本层 + 有位图」，两半各量一次（判据① 的 AND）。

    ``text_layer_chars`` 用的是 ``pypdf.extract_text()``；``has_image_object`` 用的是
    loader 在册那把尺（``page_has_image_object``），这样读者能看到判定输入本身，
    而不是只看判定结论。
    """
    from pypdf import PdfReader

    from app.rag import loader

    reader = PdfReader(str(path))
    rows = []
    for index, page in enumerate(reader.pages, start=1):
        layer = (page.extract_text() or "").strip()
        rows.append(
            {
                "page": index,
                "text_layer_chars": len("".join(layer.split())),
                "has_image_object": bool(loader.page_has_image_object(page)),
            }
        )
    return {
        "threshold": loader.scanned_page_text_char_threshold(),
        "pages": rows,
        "all_zero_text_layer": all(row["text_layer_chars"] == 0 for row in rows),
        "all_have_image_object": all(row["has_image_object"] for row in rows),
    }


def page_rows(report) -> list[dict]:
    return [
        {
            "page": page.page_number,
            "is_scanned": page.is_scanned,
            "source": page.source,
            "text_layer_chars": page.text_layer_chars,
            "has_image_object": page.has_image_object,
            "ocr_elapsed_ms": round(page.ocr_elapsed_ms, 1),
            "raster": list(page.raster_size),
            "note": page.note,
            "text_head": head(page.text),
        }
        for page in report.pages
    ]


def ocr_timing_account(report) -> dict:
    """单页耗时只统计**真的跑了识别**的那些页（``ocr`` / ``ocr-empty``）。"""
    from app.rag import loader

    ran = [
        page.ocr_elapsed_ms
        for page in report.pages
        if page.source in {loader.PAGE_SOURCE_OCR, loader.PAGE_SOURCE_OCR_EMPTY}
        and page.ocr_elapsed_ms > 0
    ]
    did_not_run = [
        {"page": page.page_number, "source": page.source, "note": page.note}
        for page in report.pages
        if page.source == loader.PAGE_SOURCE_OCR_DEGRADED
    ]
    return {
        "pages_that_ran_ocr": len(ran),
        "per_page_ms": [round(value, 1) for value in ran],
        "min_s": round(min(ran) / 1000.0, 3) if ran else None,
        "median_s": round(statistics.median(ran) / 1000.0, 3) if ran else None,
        "max_s": round(max(ran) / 1000.0, 3) if ran else None,
        "total_s": round(sum(ran) / 1000.0, 3) if ran else None,
        "pages_that_did_not_run": did_not_run,
    }


def report_account(report) -> dict:
    from app.rag import loader

    return {
        "summary": report.summary(),
        "page_count": report.page_count,
        "scanned_pages": report.scanned_pages,
        "scanned_page_numbers": list(report.scanned_page_numbers),
        "source_counts": dict(report.source_counts),
        "ocr_engine": report.ocr_engine,
        "ocr_dpi": report.ocr_dpi,
        "ocr_attempted": report.ocr_attempted,
        "ocr_available": report.ocr_available,
        "degradation_notes": list(report.degradation_notes),
        "degradation_sentence": report.degradation_sentence,
        "text_chars": len(report.text),
        "nul_in_text": "\x00" in report.text,
        "pages": page_rows(report),
        "ocr_text_full": {
            str(page.page_number): page.text for page in report.pages if page.text
        },
        "per_page_timing": ocr_timing_account(report),
        "blank_page_note": [
            {"page": page.page_number, "note": page.note}
            for page in report.pages
            if page.source == loader.PAGE_SOURCE_BLANK
        ],
    }


# ==================== case ====================


def case_probe(path: Path) -> dict:
    """零 OCR、零引擎：只把「这份件确实无文本层」这一格量出来（可反复跑，不花钱）。"""
    return {"file": path.name, "sha256_12": sha256_head(path), "bytes": path.stat().st_size,
            "precondition": precondition(path)}


def measure_engine_init() -> dict:
    """引擎初始化单独量一次（判据② 先例读数的对照格）：force_new 绕开缓存。"""
    import time

    from app.rag import ocr as ocr_channel

    ocr_channel.reset_engine_cache()
    started = time.perf_counter()
    try:
        ocr_channel.get_engine(force_new=True)
    except Exception as exc:  # noqa: BLE001 - 引擎起不来是一句要如实报的读数，不是栈
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "init_s": None}
    init_s = time.perf_counter() - started
    return {
        "ok": True,
        "module": ocr_channel.OCR_ENGINE_MODULE,
        "init_s": round(init_s, 3),
        "missing_model_files": list(ocr_channel.missing_model_files()),
        "default_dpi": ocr_channel.DEFAULT_OCR_DPI,
        "default_max_pages": ocr_channel.DEFAULT_OCR_MAX_PAGES,
    }


def case_scan(path: Path, *, dpi: int | None) -> dict:
    from app.rag import loader

    engine_init = measure_engine_init()
    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), dpi=dpi)
    return {
        "file": path.name,
        "sha256_12": sha256_head(path),
        "engine_init": engine_init,
        "precondition": precondition(path),
        **report_account(report),
        "logs": logs,
    }


def case_ocr_off(path: Path) -> dict:
    """把「本次调用关掉 OCR 通道」那一形复现一次：不花钱，且证明降级句会说原因。"""
    from app.rag import loader

    with capture_logs() as logs:
        report = loader.extract_pdf(str(path), enable_ocr=False)
    return {"file": path.name, "engine_called": False, **report_account(report), "logs": logs}


def case_degraded_limit(path: Path) -> dict:
    """把「哪几页没跑成」那一形复现一次：``DOCUMENT_OCR_MAX_PAGES=1`` 触顶，只跑第 1 页。"""
    from app.rag import loader
    from app.rag import ocr as ocr_channel

    previous = os.environ.get(ocr_channel.OCR_MAX_PAGES_ENV)
    os.environ[ocr_channel.OCR_MAX_PAGES_ENV] = "1"
    try:
        limit = ocr_channel.resolve_max_pages(None)
        with capture_logs() as logs:
            report = loader.extract_pdf(str(path))
    finally:
        if previous is None:
            os.environ.pop(ocr_channel.OCR_MAX_PAGES_ENV, None)
        else:
            os.environ[ocr_channel.OCR_MAX_PAGES_ENV] = previous
    return {
        "file": path.name,
        "env": {ocr_channel.OCR_MAX_PAGES_ENV: "1"},
        "resolved_limit": limit,
        **report_account(report),
        "logs": logs,
    }


def case_repeat(path: Path) -> dict:
    """预热之后再连跑两遍：把「首枚含 onnx 首次推理预热」与「稳态单页」分开量。

    判据② 的先例读数（min 1.14 / 中位 2.11 / max 2.72 s）拿单页耗时当对照，而单页耗时里
    混着 onnxruntime 首次推理的一次性成本；只报一遍 max 就会把这笔预热说成"这页更慢"。
    本案连跑两遍，第二轮才是客户机上传第二页之后 steady 的那一份账。
    """
    from app.rag import loader

    warm = measure_engine_init()
    rounds: list[dict] = []
    for attempt in (1, 2):
        report = loader.extract_pdf(str(path))
        timing = ocr_timing_account(report)
        rounds.append(
            {
                "attempt": attempt,
                "per_page_ms": timing["per_page_ms"],
                "min_s": timing["min_s"],
                "median_s": timing["median_s"],
                "max_s": timing["max_s"],
                "total_s": timing["total_s"],
                "source_counts": dict(report.source_counts),
                "text_chars": len(report.text),
            }
        )
    return {"file": path.name, "engine_init": warm, "rounds": rounds}


def case_receipt(path: Path) -> dict:
    """判据④ 的 live 凭据：客户上传回执里那一格今天到底长什么样（不新造第二套上报）。

    走的在册链路 = ``loader.extract_document_with_reports`` → ``chat._pdf_extraction_cell``，
    与 ``app/api/v1/chat.py`` 上传那四支返回路径同一个把手。
    """
    from app.api.v1.chat import _pdf_extraction_cell
    from app.rag import loader

    extraction = loader.extract_document_with_reports(str(path))
    cell = _pdf_extraction_cell(extraction)
    return {
        "consumer_function": "app/api/v1/chat.py::_pdf_extraction_cell",
        "extraction_has_pdf_report": extraction.pdf is not None,
        "upload_receipt_cell": cell,
        "visible_phrase_preview": (
            f"本次共 {cell['page_count']} 页 · 扫描页 {cell['scanned_pages']} 页"
            if cell
            else None
        ),
    }


def run_case(case: str, path: Path, *, dpi: int | None) -> dict:
    if case == "probe":
        return case_probe(path)
    if case == "scan":
        return case_scan(path, dpi=dpi)
    if case == "ocr-off":
        return case_ocr_off(path)
    if case == "degraded-limit":
        return case_degraded_limit(path)
    if case == "repeat":
        return case_repeat(path)
    if case == "receipt":
        return case_receipt(path)
    raise KeyError(f"未知 case：{case}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R599 合成扫描件在册 OCR 腿读数（一次性解析，不落库）")
    parser.add_argument("--fixture", default=str(FIXTURE), help="要解析的 PDF（绝对路径）")
    parser.add_argument("--case", default="all", help="、".join(CASES) + " 或 all")
    parser.add_argument("--dpi", type=int, default=None, help="OCR 栅格 DPI（缺省走产品默认 200）")
    args = parser.parse_args(argv)

    require_cwd_outside_repo()
    path = Path(args.fixture).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"扫描件不存在：{path}")
    refuse = REPO_ROOT / "documents"
    if refuse.resolve() in path.parents:
        raise SystemExit(f"判据③ 铁规：本件不解析 documents/** 下的东西，收到 {path}")

    chosen = list(CASES) if args.case == "all" else [item.strip() for item in args.case.split(",") if item.strip()]
    unknown = [item for item in chosen if item not in CASES]
    if unknown:
        raise SystemExit(f"未知 case：{'、'.join(unknown)}；可用：{'、'.join(CASES)}")

    print(
        json.dumps(
            {
                "tool": "scripts/r599_readout.py",
                "cwd": str(Path.cwd()),
                "fixture": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "cases": {case: run_case(case, path, dpi=args.dpi) for case in chosen},
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
