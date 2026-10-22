r"""R347 判据①-⑨ · 上传回执里的降级句不再逐页复述同一句话。

病灶（总控 2026-09-27 现取，app/rag/loader.py:212-225）：``degradation_notes`` 对**每一枚**
``ocr-degraded`` 的页产出一句 ``第{n}页：{reason}``，``degradation_sentence`` 再把它们全量
``；`` join —— 一份 400 页、降级原因同一条的 PDF 就得到一枚把同一句话逐页复述 400 遍的巨型
句子（R338 结案实测过 4853 chars truncated 那种形状）。

合并只能在 ``app/api/v1/chat.py::_pdf_extraction_cell`` 这一层做：

- 界面那一格（``frontend/src/components/DocPanel.vue``，R338 已并树 ``e0168b7``）钉
  ``degradation_note`` 只抄不改口；
- ``loader.py`` 的逐页账是 R298 / R301 钉着的真源，一行都不许动。

本格今天的样子：按 ``page.note`` **字面相等**归堆，一堆一句；页码枚举到
``chat.PDF_DEGRADATION_PAGE_LIST_CAP`` 收口，超限那句「另有 N 页未列出」的 N 只出自真计数；
reason 原文一个字不改；两档句头按 ``ocr_available`` 各走各的；没有同因复述时尺子那句原样搬
（R301 那条「尺改口，回执跟着改口」的等式继续成立）。
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import logging
import re
from pathlib import Path

import numpy as np
import pytest

from app.api.v1 import chat
from app.rag import loader
from app.rag import ocr as ocr_channel
from app.rag.loader import (
    PAGE_SOURCE_BLANK,
    PAGE_SOURCE_OCR,
    PAGE_SOURCE_OCR_DEGRADED,
    PAGE_SOURCE_OCR_EMPTY,
    PAGE_SOURCE_TEXT_LAYER,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MIXED_PDF = REPO_ROOT / "tests" / "fixtures" / "r298_mixed_pages.pdf"
LOADER_SOURCE = (REPO_ROOT / "app" / "rag" / "loader.py").read_text(encoding="utf-8")
CELL_KEY = "pdf_extraction"

#: 本单那枚上限（判据①）—— 从被测模块读，不在测试里再抄一份数，改了常量本件立刻知道。
CAP = chat.PDF_DEGRADATION_PAGE_LIST_CAP

#: 三把 reason（全是 loader 真会产出的那三句原文，不做修辞）。
SAME_REASON = "超出单次 OCR 页数上限 60"
OTHER_REASON = "栅格化失败 RuntimeError"
NEAR_REASON = "识别失败 RuntimeError"
ENGINE_REASON = f"{ocr_channel.OCR_ENGINE_MODULE} 模型文件缺失：models/absent.onnx"

#: 判据① 的形状尺：300 页同因合并后整句的字符上限。
#: 基数：句头 8 + 「：」 + 「第」 + 10 枚页码（含顿号）19 + 「页」 + 「，另有 290 页未列出」 15
#: + 「：」 + 一枚 reason 15 ≈ 60；余量给更长的 reason，取 200。
BOUND_CHARS = 200

#: 基点 c5c3c41 上 ``_pdf_extraction_cell`` 的键集合（判据⑦：只许收紧内部文本）。
BASE_CELL_KEYS = {
    "page_count",
    "scanned_pages",
    "scanned_page_numbers",
    "ocr_attempted",
    "ocr_available",
    "ocr_engine",
    "ocr_dpi",
    "source_counts",
    "ocr_degraded_page_numbers",
    "degradation_note",
}

_OMITTED = re.compile(r"，另有 (\d+) 页未列出")


# ------------------------------------------------------------------ 造账与取样


def _page(number: int, source: str, note: str = ""):
    return loader.PdfPageExtraction(
        page_number=number,
        source=source,
        text="",
        text_layer_chars=0,
        has_image_object=source != PAGE_SOURCE_TEXT_LAYER,
        is_scanned=source
        in (PAGE_SOURCE_OCR, PAGE_SOURCE_OCR_EMPTY, PAGE_SOURCE_OCR_DEGRADED),
        note=note,
    )


def _degraded(number: int, note: str = SAME_REASON):
    return _page(number, PAGE_SOURCE_OCR_DEGRADED, note)


def _report(pages, *, ocr_available: bool = True, page_count: int | None = None):
    return loader.PdfExtractionReport(
        file_path="scan.pdf",
        page_count=len(pages) if page_count is None else page_count,
        pages=tuple(pages),
        text="",
        ocr_dpi=200,
        ocr_engine=ocr_channel.OCR_ENGINE_MODULE,
        ocr_attempted=True,
        ocr_available=ocr_available,
    )


def _cell(report) -> dict:
    extraction = loader.DocumentExtraction(
        file_path=report.file_path,
        text="",
        tables=loader.TableExtractionReport(),
        pdf=report,
    )
    return chat._pdf_extraction_cell(extraction)


def _note(report) -> str:
    return _cell(report)["degradation_note"]


def _head(report) -> str:
    """这一档该用的句头（判据③：两档是两句话，取样器按 ``ocr_available`` 分）。"""
    if report.ocr_available:
        return loader.DEGRADATION_NOTE_PREFIX
    return ocr_channel.ENGINE_UNAVAILABLE_NOTE


def _segments(note: str, head: str) -> list[tuple[str, str]]:
    """把回执那句拆回 ``(页码标签, reason 原文)``（判据④ 的取样器）。

    分界只用**段内的第一枚** ``：`` —— 页码标签里没有冒号，所以 reason 自带冒号
    （``模型文件缺失：models/...``）也不会被切错。
    """
    assert note.startswith(f"{head}："), f"句头不是这一档的：{note[:40]}"
    out = []
    for segment in note[len(head) + 1 :].split("；"):
        label, sep, reason = segment.partition("：")
        assert sep, f"这一段没有「页：原因」的分界：{segment}"
        out.append((label, reason))
    return out


def _shown_pages(label: str) -> list[int]:
    body = label.split("，")[0]
    assert body.startswith("第") and body.endswith("页"), f"页码标签形状不对：{label}"
    return [int(piece) for piece in body[1:-1].split("、")]


def _omitted(label: str) -> int:
    match = _OMITTED.search(label)
    return int(match.group(1)) if match else 0


# ------------------------------------------------------------------ 判据①：同因归堆，一堆一句


def test_same_reason_on_three_pages_becomes_one_sentence():
    """判据①：同一枚 ``page.note`` 的所有页码归成一堆，只产出一句。"""
    report = _report([_degraded(2), _degraded(4), _degraded(5)])

    note = _note(report)

    assert note.count(SAME_REASON) == 1, f"同一句话被复述了 {note.count(SAME_REASON)} 遍：{note}"
    assert _shown_pages(_segments(note, _head(report))[0][0]) == [2, 4, 5]
    assert len(_segments(note, _head(report))) == 1


def test_different_reasons_still_get_one_sentence_each():
    """判据① 的下半句：不同 reason 各出一句，不因为挨着页就捏成一坨。"""
    report = _report([_degraded(2, SAME_REASON), _degraded(3, OTHER_REASON), _degraded(7, SAME_REASON)])

    segments = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)

    assert [reason for _label, reason in segments] == [SAME_REASON, OTHER_REASON]
    assert _shown_pages(segments[0][0]) == [2, 7], "同因跨页要并回来，且保持页序"
    assert _shown_pages(segments[1][0]) == [3]


def test_near_identical_reasons_are_not_merged():
    """判据①「逐字相同」是字面的：``栅格化失败 RuntimeError`` 与 ``识别失败 RuntimeError`` 是两句话。"""
    report = _report([_degraded(1, OTHER_REASON), _degraded(2, NEAR_REASON)])

    note = _note(report)

    assert [reason for _label, reason in _segments(note, loader.DEGRADATION_NOTE_PREFIX)] == [
        OTHER_REASON,
        NEAR_REASON,
    ]


def test_groups_keep_first_appearance_order_and_pages_stay_ascending():
    """判据①：堆序 = reason 首次出现的页序，堆内页码沿用 ``report.pages`` 的升序（不重排真源账）。"""
    report = _report(
        [_degraded(1, OTHER_REASON), _degraded(3, SAME_REASON), _degraded(4, SAME_REASON), _degraded(9, OTHER_REASON)]
    )

    segments = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)

    assert [reason for _label, reason in segments] == [OTHER_REASON, SAME_REASON]
    assert [_shown_pages(label) for label, _reason in segments] == [[1, 9], [3, 4]]


# ------------------------------------------------------------------ 判据①：页码上限与真剩余数


def test_pages_over_the_cap_are_cut_and_the_rest_is_counted_for_real():
    """判据①：超限必须说「另有 N 页未列出」，且 N = 这一堆的真枚数 - 画下来的枚数。"""
    total = CAP + 290
    report = _report([_degraded(number) for number in range(1, total + 1)])

    label = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)[0][0]

    assert _shown_pages(label) == list(range(1, CAP + 1)), "画下来的就该是前 CAP 枚"
    assert _omitted(label) == total - CAP, "N 必须是真剩余数"
    assert "未列出" in label


def test_omitted_count_is_never_the_length_of_the_truncated_list():
    """判据① 的反面：N 拿 ``shown`` 的长度冒充（= CAP）当场红。"""
    total = CAP * 3
    report = _report([_degraded(number) for number in range(1, total + 1)])

    label = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)[0][0]

    assert _omitted(label) == total - CAP
    assert _omitted(label) != len(_shown_pages(label)), "「另有 N 页」说的是没列出的那些，不是列出的这些"


def test_at_exactly_the_cap_no_omitted_clause_is_invented():
    """边界：刚好 CAP 枚 ⇒ 一枚不漏，也不许造「另有 0 页未列出」。"""
    report = _report([_degraded(number) for number in range(1, CAP + 1)])

    label = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)[0][0]

    assert _shown_pages(label) == list(range(1, CAP + 1))
    assert _omitted(label) == 0
    assert "另有" not in label


def test_three_hundred_pages_same_reason_stays_bounded():
    """判据① 的长度尺：300 页同因（``ocr_available=True``）合完仍然有界，reason 只出现一次。"""
    report = _report([_degraded(number) for number in range(1, 301)])

    note = _note(report)

    assert note.count(SAME_REASON) == 1
    assert len(note) <= BOUND_CHARS, f"合并后仍没界：{len(note)} chars -> {note[:120]}"
    assert _omitted(_segments(note, loader.DEGRADATION_NOTE_PREFIX)[0][0]) == 300 - CAP


def test_the_base_per_page_join_would_blow_that_bound():
    """这一枚钉住「本单没做空气」：同一份账退回基点那道（逐页 join）必然炸掉长度尺。"""
    report = _report([_degraded(number) for number in range(1, 301)])

    sentence = report.degradation_sentence

    assert sentence.count(SAME_REASON) == 300, "逐页真源账就该是 300 遍（本单没去动它）"
    assert len(sentence) > BOUND_CHARS * 10, f"旧道今天还是不炸：{len(sentence)} chars"


# ------------------------------------------------------------------ 判据④：reason 只抄不改


def test_reason_is_copied_word_for_word_from_the_page_note():
    """判据④：合并那一路里，句中出现的那段 reason 与 ``page.note`` **全等**，不是「包含」。

    三枚堆（其中一枚两页同因）才会走合并，这一枚才对「改写 reason」敏感 —— 单页那种
    恒等路径另有 ``test_a_note_without_repetition_ships_the_ruler_word_for_word`` 钉。
    """
    pages = [_degraded(2, ENGINE_REASON), _degraded(5, ENGINE_REASON), _degraded(7, SAME_REASON), _degraded(9, OTHER_REASON)]
    report = _report(pages, ocr_available=False)

    segments = _segments(_note(report), _head(report))

    assert [reason for _label, reason in segments] == [ENGINE_REASON, SAME_REASON, OTHER_REASON]
    assert segments[0][1] == pages[0].note == pages[1].note
    assert _shown_pages(segments[0][0]) == [2, 5]


def test_punctuation_and_a_colon_inside_the_reason_survive():
    """判据④：reason 自带全角冒号也不剥标点 —— 拆出来的那段还是整句原文。"""
    raw = "rapidocr_onnxruntime 无法定位：RuntimeError: bad onnx"
    report = _report([_degraded(1, raw), _degraded(2, raw)])

    label, reason = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)[0]

    assert reason == raw
    assert _shown_pages(label) == [1, 2]


def test_no_apology_and_no_polish_is_added():
    """判据④：回执不往 reason 前面添「很抱歉」这类自己造的话。"""
    report = _report([_degraded(2), _degraded(3)])

    note = _note(report)

    for invented in ("很抱歉", "抱歉", "亲", "建议您", "已为您", "文档已完整识别"):
        assert invented not in note, f"回执自己造了话：{invented}"


# ------------------------------------------------------------------ 判据③：两档句头不合并


def test_engine_unavailable_tier_keeps_its_own_head_when_pages_merge():
    """判据③：``ocr_available=False`` 且发生合并时，句头还是「引擎不可用」那一档。"""
    report = _report([_degraded(2, ENGINE_REASON), _degraded(4, ENGINE_REASON)], ocr_available=False)

    note = _note(report)

    assert note.startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE)
    assert loader.DEGRADATION_NOTE_PREFIX not in note


def test_engine_available_tier_keeps_its_own_head_when_pages_merge():
    """判据③：``ocr_available=True`` 时句头是「扫描页 OCR 降级」，不许蹭引擎不可用那一档。"""
    report = _report([_degraded(2), _degraded(3)], ocr_available=True)

    note = _note(report)

    assert note.startswith(loader.DEGRADATION_NOTE_PREFIX)
    assert ocr_channel.ENGINE_UNAVAILABLE_NOTE not in note


def test_the_two_tiers_never_collapse_into_one_sentence():
    """判据③：同一堆页码在两档下是两句话（R338 刀1 实测过：捏成一句当场红）。"""
    pages = [_degraded(2), _degraded(3), _degraded(4)]
    available = _report(pages, ocr_available=True)
    unavailable = _report(pages, ocr_available=False)

    assert ocr_channel.ENGINE_UNAVAILABLE_NOTE != loader.DEGRADATION_NOTE_PREFIX
    assert _note(available) != _note(unavailable)
    assert _note(available).startswith(loader.DEGRADATION_NOTE_PREFIX)
    assert _note(unavailable).startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE)


# ------------------------------------------------------------------ 判据②：尺子还是那把尺子


def test_loader_per_page_book_is_still_per_page():
    """判据②：逐页真源账一行没动 —— 它今天仍然逐页复述，这本账不是回执层能改的。"""
    report = _report([_degraded(1), _degraded(2), _degraded(3)])

    assert report.degradation_notes == tuple(f"第{n}页：{SAME_REASON}" for n in (1, 2, 3))
    assert report.degradation_sentence.count(SAME_REASON) == 3
    assert 'f"第{page.page_number}页：{page.note}"' in LOADER_SOURCE
    assert "return f\"{head}：{'；'.join(notes)}\"" in LOADER_SOURCE


def test_the_cell_reads_the_book_without_rewriting_it():
    """判据②：回执只读账本，不就地改账本。"""
    report = _report([_degraded(1), _degraded(2), _page(3, PAGE_SOURCE_OCR)])
    before_notes = report.degradation_notes
    before_sentence = report.degradation_sentence

    _cell(report)

    assert report.degradation_notes == before_notes
    assert report.degradation_sentence == before_sentence
    assert len(before_notes) == 2


def test_a_note_without_repetition_ships_the_ruler_word_for_word():
    """判据② 的另一半：没有同因复述 ⇒ 回执逐字等于 ``degradation_sentence``（R301 那条等式）。"""
    report = _report([_degraded(2, OTHER_REASON), _page(4, PAGE_SOURCE_OCR)])

    assert _note(report) == report.degradation_sentence


# ------------------------------------------------------------------ 判据⑤：合并不丢信息


def test_degraded_page_numbers_stay_the_full_list_after_merging():
    """判据⑤：「哪几页降级了」由 ``ocr_degraded_page_numbers`` 全量回答，句子里截的页在这儿一枚不少。"""
    total = CAP + 25
    report = _report([_degraded(number) for number in range(1, total + 1)] + [_page(999, PAGE_SOURCE_BLANK)])

    cell = _cell(report)

    assert cell["ocr_degraded_page_numbers"] == list(range(1, total + 1))
    assert len(cell["ocr_degraded_page_numbers"]) == total
    assert cell["degradation_note"].count(SAME_REASON) == 1


def test_source_counts_are_untouched_and_blank_and_ocr_empty_stay_separate():
    """判据⑤：``source_counts`` 一字不改；``blank`` 与 ``ocr-empty`` 不合并（R338 判据点过名）。"""
    report = _report(
        [
            _page(1, PAGE_SOURCE_TEXT_LAYER),
            _page(2, PAGE_SOURCE_OCR_EMPTY),
            _page(3, PAGE_SOURCE_BLANK),
            _degraded(4),
            _degraded(5),
        ]
    )

    cell = _cell(report)

    assert cell["source_counts"] == report.source_counts
    assert cell["source_counts"] == {
        PAGE_SOURCE_TEXT_LAYER: 1,
        PAGE_SOURCE_OCR_EMPTY: 1,
        PAGE_SOURCE_BLANK: 1,
        PAGE_SOURCE_OCR_DEGRADED: 2,
    }


# ------------------------------------------------------------------ 判据⑥：没有降级就是空串


def test_no_degraded_page_answers_an_empty_string():
    """判据⑥：无降级 ⇒ ``""``，不是 ``None``，也不是新造的客气话。"""
    report = _report([_page(1, PAGE_SOURCE_TEXT_LAYER), _page(2, PAGE_SOURCE_OCR)])

    note = _note(report)

    assert note == ""
    assert isinstance(note, str)
    assert note is not None


def test_zero_pages_and_pages_without_degradation_are_two_readings():
    """判据⑥：``page_count == 0`` 与「有页但无降级页」各说各的，降级句两边都是空串。"""
    empty_book = _report([], page_count=0)
    clean_book = _report([_page(1, PAGE_SOURCE_TEXT_LAYER), _page(2, PAGE_SOURCE_TEXT_LAYER)])

    assert _note(empty_book) == "" and _note(clean_book) == ""
    assert _cell(empty_book)["page_count"] == 0
    assert _cell(clean_book)["page_count"] == 2
    assert _cell(empty_book)["ocr_degraded_page_numbers"] == []
    assert _cell(clean_book)["ocr_degraded_page_numbers"] == []


# ------------------------------------------------------------------ 判据⑦：响应形状只收紧内部文本


def test_the_cell_key_set_is_word_for_word_the_base_one():
    """判据⑦：键集合与基点 ``c5c3c41`` 逐字相同 —— 不增、不删、不改名。"""
    report = _report([_degraded(2), _degraded(3), _page(4, PAGE_SOURCE_BLANK)])

    assert set(_cell(report)) == BASE_CELL_KEYS


def test_every_other_reading_is_the_same_object_as_before():
    """判据⑦：这一格只准动 ``degradation_note`` 的文本，其余读数照旧。"""
    report = _report([_degraded(2), _degraded(3)], page_count=6)

    cell = _cell(report)

    assert cell["page_count"] == 6
    assert cell["ocr_attempted"] is report.ocr_attempted
    assert cell["ocr_available"] is report.ocr_available
    assert cell["ocr_engine"] == report.ocr_engine
    assert cell["ocr_dpi"] == report.ocr_dpi
    assert cell["scanned_pages"] == report.scanned_pages
    assert cell["scanned_page_numbers"] == list(report.scanned_page_numbers)


def test_the_cap_is_a_named_constant_not_a_magic_number():
    """判据①：上限是服务端自己立的**具名模块级常量**，不是抄前端那枚 12 的数字。"""
    tree = ast.parse(Path(chat.__file__).read_text(encoding="utf-8"))
    module_targets = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    assert "PDF_DEGRADATION_PAGE_LIST_CAP" in module_targets
    assert CAP == chat.PDF_DEGRADATION_PAGE_LIST_CAP
    assert 0 < CAP < 20


# ------------------------------------------------------------------ 真语料：整条上传链路


@contextlib.contextmanager
def _quiet_parser_warnings():
    pypdf_logger = logging.getLogger("pypdf")
    previous = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        pypdf_logger.setLevel(previous)


class PageAwareEngine:
    """按页给答案的假引擎（与 tests/test_r301_upload_readout.py 同一手法）。"""

    def __init__(self, no_text_pages=(), fail_pages=()) -> None:
        self.no_text_pages = set(no_text_pages)
        self.fail_pages = set(fail_pages)

    def __call__(self, array):  # noqa: ANN001
        page_number = int(array.shape[0]) - 8
        if page_number in self.fail_pages:
            raise RuntimeError("假引擎在这一页炸了")
        if page_number in self.no_text_pages:
            return (None, [0.0])
        box = [[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]]
        return ([[box, f"扫描页正文 第{page_number}页", 0.99]], [0.0])


@pytest.fixture(autouse=True)
def stub_raster(monkeypatch):
    def _fake(pdf_path: str, page_number: int, *, dpi: int):
        return np.zeros((page_number + 8, page_number + 16, 3), dtype="uint8")

    monkeypatch.setattr(ocr_channel, "rasterize_page", _fake)


class RecordingRetriever:
    def __init__(self) -> None:
        self.add_calls: list[str] = []

    def add_document(self, filename, content, classification, department):
        self.add_calls.append(filename)
        return (True, "已添加 2 个文本块")

    def list_documents(self):
        return list(self.add_calls)


def _wire(monkeypatch, tmp_path):
    from app.documents import catalog

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False, raising=False)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(chat, "retriever", RecordingRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    return chat


def _upload(chat_module, path: Path):
    from fastapi import UploadFile

    body = path.read_bytes()
    with _quiet_parser_warnings():
        return asyncio.run(
            chat_module.upload_document(
                UploadFile(filename=path.name, file=io.BytesIO(body)),
                classification=1,
                department="",
            )
        )


def _book_without_engine(monkeypatch):
    """独立对照（引擎不可用那一档）：直接叫 loader，不注 engine —— 与上传路径走同一支。"""
    monkeypatch.setattr(ocr_channel, "_MODEL_FILE_NAMES", ("models/absent.onnx",))
    with _quiet_parser_warnings():
        return loader.extract_pdf(str(MIXED_PDF))


def _book_with_engine(monkeypatch, engine):
    """独立对照（引擎在、按页给答案那一档）：桩与上传路径同一套（都经 ``get_engine``）。"""
    monkeypatch.setattr(ocr_channel, "unavailable_reason", lambda: None)
    monkeypatch.setattr(ocr_channel, "get_engine", lambda **kwargs: engine)
    with _quiet_parser_warnings():
        return loader.extract_pdf(str(MIXED_PDF))


def test_real_upload_merges_the_three_engine_unavailable_pages(monkeypatch, tmp_path):
    """真上传（6 页混合件 + 模型缺失）：三页同因 ⇒ 一句，句头仍是「引擎不可用」那一档。"""
    chat_module = _wire(monkeypatch, tmp_path)
    book = _book_without_engine(monkeypatch)

    cell = _upload(chat_module, MIXED_PDF)[CELL_KEY]

    reason = next(page.note for page in book.pages if page.source == PAGE_SOURCE_OCR_DEGRADED)
    assert book.ocr_available is False and reason, "对照账本身不成立，这一枚就是空转"
    assert cell["ocr_available"] is False
    assert cell["ocr_degraded_page_numbers"] == [2, 4, 5], "页号那一把仍是一枚不少（判据⑤）"
    assert cell["degradation_note"].startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE)
    assert cell["degradation_note"].count(reason) == 1, cell["degradation_note"]
    assert "第2、4、5页：" in cell["degradation_note"]
    assert book.degradation_sentence.count(reason) == 3, "逐页真源账照旧复述三遍（判据②）"


def test_real_upload_with_a_single_failed_page_is_the_ruler_itself(monkeypatch, tmp_path):
    """真上传（只有第 2 页没跑成）⇒ 没有同因复述可合 ⇒ 逐字等于尺子那句（R301 判据②）。"""
    chat_module = _wire(monkeypatch, tmp_path)
    book = _book_with_engine(monkeypatch, PageAwareEngine(no_text_pages={5}, fail_pages={2}))

    cell = _upload(chat_module, MIXED_PDF)[CELL_KEY]

    assert cell["degradation_note"] == book.degradation_sentence
    assert set(cell) == BASE_CELL_KEYS





# ------------------------------------------------------------------ 判据⑧：契约那一节


CONTRACT = REPO_ROOT / "docs" / "api" / "contract-v1.md"


def test_contract_names_the_cap_and_the_source_of_truth():
    """判据⑧：契约写清这一格今天的形状、上限值、超限表达，以及逐页真源账没变。"""
    text = CONTRACT.read_text(encoding="utf-8")

    assert "PDF_DEGRADATION_PAGE_LIST_CAP" in text
    assert f"= {CAP}" in text
    assert "另有" in text and "页未列出" in text
    assert "degradation_notes" in text and "degradation_sentence" in text


def test_contract_is_strict_utf8_crlf_and_the_previous_tail_survives():
    """判据⑧：纯 append —— 字节层严格 UTF-8、无 U+FFFD、零 lone LF，旧尾一行不少。"""
    raw = CONTRACT.read_bytes()
    text = raw.decode("utf-8")  # 严格解码：坏一个字节就红

    assert "\ufffd" not in text
    assert text.count("\n") - text.count("\r\n") == 0, "追加不能引入 lone LF"
    assert "Physical lines: `app/api/v1/alerts.py` 1012 -> 1055" in text
    assert "R347" in text


# ------------------------------------------------------------------ 反证钉（本件自带的两把）


def test_counter_evidence_a_the_per_page_join_is_not_a_free_win(monkeypatch):
    """刀A（件内一把）：把回执退回基点那道（只搬 ``degradation_sentence``）⇒ 长度尺与「只说一遍」双双红。"""
    report = _report([_degraded(number) for number in range(1, 301)])

    shipped = _note(report)
    assert shipped.count(SAME_REASON) == 1 and len(shipped) <= BOUND_CHARS

    monkeypatch.setattr(chat, "_receipt_degradation_note", lambda book: book.degradation_sentence)
    reverted = _note(report)
    with pytest.raises(AssertionError):
        assert reverted.count(SAME_REASON) == 1
    with pytest.raises(AssertionError):
        assert len(reverted) <= BOUND_CHARS


def test_counter_evidence_e_a_forged_remainder_is_caught():
    """刀E（件内一把）：把 N 写成「画下来的枚数」这种冒充值，本件的取样器判红。"""
    report = _report([_degraded(number) for number in range(1, CAP + 2)])
    shipped_label = _segments(_note(report), loader.DEGRADATION_NOTE_PREFIX)[0][0]

    assert _omitted(shipped_label) == 1
    forged = f"第{CAP}页，另有 {CAP} 页未列出：{SAME_REASON}"
    with pytest.raises(AssertionError):
        assert _omitted(_segments(forged, loader.DEGRADATION_NOTE_PREFIX)[0][0]) == 1