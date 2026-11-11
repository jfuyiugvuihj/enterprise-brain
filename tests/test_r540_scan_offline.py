# -*- coding: utf-8 -*-
r"""R540 · #13 扫描件通道的常驻钉：**离线**把四形各钉一次，真打引擎那一腿不在这枚门里。

钉什么（对应派工词①②⑥）：
 ① 样本自己先作证：`PIL` 现造的多页 PDF 每页 `pypdf.extract_text()` 交回空串，
    而每页 `/Subtype /Image` 在位 ⇒ 判据① 的 AND 两半边都真（不是"看起来像扫描件"）。
 ② 逐页 `source` 只许落在 `ocr` / `ocr-empty` / `ocr-degraded` / `text-layer` / `blank`
    五形之内，且**降级必须点名原因**（页数触顶 / 引擎不在 / 本次调用关掉 / 识别抛错），
    "图里确实没字"与"这页根本没跑成"两句话不许混（`ocr.py` 里 `STATUS_EMPTY` 与
    `STATUS_UNAVAILABLE` 的分界，今天由 loader 侧的 `source` 复述一遍）。
 ④ 🔴 有文本层的页一个字都不许再走 OCR：这一格由 `OcrProbe` 的**页数账**钉——
    对照件（文本层 165 字 + 一张位图）必须交回"OCR 通道被问到 0 页"。
    把 `loader.py` 里那枚 AND 摘成 OR，本件当场红（反证 K2，纸：docs/testing/r540-*.md）。
 ⑤ OCR 出来的字过的是同一把 `sanitize_text`：带 NUL 的那一形必须"字被削掉且不留 NUL"，
    整页只剩 NUL 时不许算"OCR 出来了"（`source` 退成 `ocr-empty` 并写明原因）。

🔴 非常驻的那半格（如实写在这里，不硬钉成假绿）：
  真 `rapidocr_onnxruntime` 的**耗时腿与识别质量腿**不在本件——CPU 单页实测 0.9–5.0 s
  （首枚含引擎初始化），一台正在跑真机评测的机器不该为门付这笔钱，而且绝对毫秒当了门
  就是 R269 收口那笔点名的假红。那一腿由 `scripts/r540_readout.py --case scan,mixed,
  lowq-only,degraded-limit` 现场取数，读数与逐页形状记在 docs/testing/ 的本单纸里。
  想在本件里真打一次：`R540_REAL_OCR=1 python -m pytest tests/test_r540_scan_offline.py -k real_engine`。

样本一律件内自造、落 tmp（`tests/fixtures/**` 一字节没动，仓里也没塞二进制）。
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.rag import loader  # noqa: E402
from app.rag import ocr as ocr_channel  # noqa: E402

REAL_OCR = os.environ.get("R540_REAL_OCR") == "1"


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


samples = _load("r540_samples", "scripts/r540_samples.py")


# ==================== 假引擎：把"哪几页真的走到了 OCR 通道"变成一枚可断言的账 ====================


def _quad(top: float = 8.0, left: float = 8.0):
    return [[left, top], [left + 40.0, top], [left + 40.0, top + 14.0], [left, top + 14.0]]


class OcrProbe:
    """`rasterize_page` 的录单替身 + 一页像素 -> 结论的脚本化假引擎。

    `ocr_pages` 每页先栅格化、再识别，两腿在同一个 probe 上按同一顺序发生，所以
    `recognized` 里能配上真实页码——**"这页有没有被送 OCR"从此是一句可断言的话**，
    而不是"看起来正文里没多出字"。
    """

    def __init__(self, script=None):
        self.rasterized: list[int] = []
        self.recognized: list[tuple[int | None, str]] = []
        self.dpi_seen: list[int] = []
        self.script = list(script or [("text", "季度回款分析说明")])

    def rasterize(self, pdf_path, page_number, *, dpi):
        self.rasterized.append(int(page_number))
        self.dpi_seen.append(int(dpi))
        return np.zeros((40, 60, 3), dtype="uint8")

    def engine(self, array):
        position = len(self.recognized)
        page = self.rasterized[position] if position < len(self.rasterized) else None
        kind, payload = self.script[position] if position < len(self.script) else self.script[-1]
        self.recognized.append((page, kind))
        if kind == "raise":
            raise RuntimeError(payload)
        if kind == "empty":
            return None, 12.0
        return [[_quad(), payload, "0.99"]], 12.0

    @property
    def pages_sent_to_ocr(self) -> list[int]:
        return list(self.rasterized)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """三件样本：扫描件（4 页零文本层）、对照件（文本层 + 位图）、混合件（三种页各一）。"""
    target = tmp_path_factory.mktemp("r540_scan")
    samples.build_scan_pdf(target / "r540_scan.pdf")
    samples.build_control_pdf(target / "r540_control.pdf")
    samples.build_mixed_pdf(target / "r540_mixed.pdf")
    return {
        "scan": str(target / "r540_scan.pdf"),
        "control": str(target / "r540_control.pdf"),
        "mixed": str(target / "r540_mixed.pdf"),
    }


@pytest.fixture()
def probe(monkeypatch):
    """每枚用例一副新 probe：栅格化只记账，识别只交脚本里写好的那一形。"""
    instance = OcrProbe()
    monkeypatch.setattr(ocr_channel, "rasterize_page", instance.rasterize)
    return instance


def _extract(corpus, key, probe, **kwargs):
    return loader.extract_pdf(corpus[key], engine=probe.engine, **kwargs)


# ==================== ① 样本自己作证：零文本层 + 位图在位 ====================


def test_scan_sample_has_a_pixel_layer_on_every_page(corpus):
    from pypdf import PdfReader

    reader = PdfReader(corpus["scan"])
    assert len(reader.pages) >= 3, "派工词① 要 ≥3 页扫描件"
    for index, page in enumerate(reader.pages, 1):
        assert (page.extract_text() or "").strip() == "", f"第{index}页带文本层，扫描件不成立"
        assert loader.page_has_image_object(page), f"第{index}页没有位图对象，判据① 的 AND 右半边缺"


def test_control_sample_wears_a_text_layer_and_a_bitmap_too(corpus):
    from pypdf import PdfReader

    reader = PdfReader(corpus["control"])
    threshold = loader.scanned_page_text_char_threshold()
    for index, page in enumerate(reader.pages, 1):
        chars = len("".join((page.extract_text() or "").split()))
        assert chars >= threshold, f"第{index}页文本层只有 {chars} 字，够不上对照件"
        assert loader.page_has_image_object(page), f"第{index}页没挂位图，AND 的右半边就没被考到过"


def test_real_rasterizer_still_reads_the_sample(corpus):
    """假引擎不许把"这其实是一枚能被 pypdfium2 打开的真 PDF"也一起假掉：dpi=72 现栅格一次。"""
    array = ocr_channel.rasterize_page(corpus["scan"], 1, dpi=72)
    assert array.dtype == np.uint8 and array.ndim == 3 and array.shape[2] == 3
    assert (array.shape[1], array.shape[0]) == (
        math.ceil(samples.PAGE_SIZE_PT[0] * 72 / 72),
        math.ceil(samples.PAGE_SIZE_PT[1] * 72 / 72),
    )


# ==================== ② 四形各自成账，降级必须点名 ====================


def test_every_scanned_page_lands_on_one_of_the_three_ocr_shapes(corpus, probe):
    report = _extract(corpus, "scan", probe)
    allowed = {
        loader.PAGE_SOURCE_OCR,
        loader.PAGE_SOURCE_OCR_EMPTY,
        loader.PAGE_SOURCE_OCR_DEGRADED,
    }
    assert report.pages, "逐页账为空"
    for page in report.pages:
        assert page.source in allowed, f"第{page.page_number}页来源 {page.source} 不在三形之内"
        assert page.is_scanned is True
    assert probe.pages_sent_to_ocr == [1, 2, 3, 4], "扫描件应当四页全送 OCR"
    assert report.source_counts == {loader.PAGE_SOURCE_OCR: 4}
    assert report.ocr_attempted is True and report.ocr_available is True


def test_recognized_page_carries_the_text_and_an_empty_page_names_the_engine(probe, corpus):
    """`ocr` 与 `ocr-empty` 是两句话：前者正文里有字且不留原因，后者一个字都没有但**不是降级**。"""
    probe.script[:] = [("text", "员工报销制度"), ("empty", ""), ("empty", ""), ("text", "信息部运维值班表")]
    report = _extract(corpus, "scan", probe)
    by_page = {page.page_number: page for page in report.pages}
    assert by_page[1].source == loader.PAGE_SOURCE_OCR and by_page[1].note == ""
    assert "员工报销制度" in report.text
    for number in (2, 3):
        assert by_page[number].source == loader.PAGE_SOURCE_OCR_EMPTY
        assert by_page[number].note == "图像页 OCR 未检出文字"
        assert by_page[number].text == ""
    assert report.degradation_notes == (), "empty 不许混进降级账"
    assert report.degradation_sentence == ""
    assert by_page[4].source == loader.PAGE_SOURCE_OCR


def test_page_ceiling_degrades_the_pages_it_never_ran(corpus, probe, monkeypatch):
    """`ocr-degraded` 造法一（可复算）：把单次页数顶收到 2，后两页**根本没跑**，不许说成"没字"。"""
    monkeypatch.setenv(ocr_channel.OCR_MAX_PAGES_ENV, "2")
    report = _extract(corpus, "scan", probe)
    assert report.source_counts == {loader.PAGE_SOURCE_OCR: 2, loader.PAGE_SOURCE_OCR_DEGRADED: 2}
    assert probe.pages_sent_to_ocr == [1, 2], "触顶之后的页不许再栅格化"
    assert len(report.degradation_notes) == 2
    for line in report.degradation_notes:
        assert "超出单次 OCR 页数上限 2" in line, line
    assert report.degradation_sentence.startswith(loader.DEGRADATION_NOTE_PREFIX)
    assert report.ocr_available is True, "引擎在位：触顶不等于引擎不可用"


def test_absent_engine_names_itself_as_unavailable_not_as_blank(corpus, probe, monkeypatch):
    """`ocr-degraded` 造法二（= 反证 K1 的进程内形状）：引擎名指歪 ⇒ 降级腿必须点名。"""
    monkeypatch.setattr(ocr_channel, "OCR_ENGINE_MODULE", "r540_no_such_engine_module")
    report = loader.extract_pdf(corpus["scan"], engine=None, dpi=72)
    assert report.ocr_available is False
    assert set(report.source_counts) == {loader.PAGE_SOURCE_OCR_DEGRADED}
    assert report.degradation_sentence.startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE)
    assert probe.pages_sent_to_ocr == [], "引擎不在就不该去栅格化像素"


def test_disabled_channel_still_reports_the_page_as_degraded(corpus):
    """`ocr-degraded` 造法三：调用方自己关掉通道 ⇒ 账上写"未送 OCR"，不是"这页没字"。"""
    report = loader.extract_pdf(corpus["scan"], enable_ocr=False)
    assert set(report.source_counts) == {loader.PAGE_SOURCE_OCR_DEGRADED}
    for page in report.pages:
        assert "扫描页未送 OCR" in page.note, page.note


def test_one_page_failing_does_not_take_the_run_down(corpus, probe):
    """逐页记的另一半：第 2 页识别抛错只降级第 2 页，其余三页照常出字。"""
    probe.script[:] = [
        ("text", "季度回款分析说明"),
        ("raise", "onnxruntime blew up"),
        ("text", "库存周转天数"),
        ("text", "信息部运维值班表"),
    ]
    report = _extract(corpus, "scan", probe)
    by_page = {page.page_number: page for page in report.pages}
    assert by_page[2].source == loader.PAGE_SOURCE_OCR_DEGRADED
    assert "识别失败" in by_page[2].note, by_page[2].note
    assert [by_page[n].source for n in (1, 3, 4)] == [loader.PAGE_SOURCE_OCR] * 3


# ==================== ④ 有文本层的页一个字都不许再走 OCR（反证 K2 的靶子） ====================


def test_pages_with_a_text_layer_never_reach_the_ocr_channel(corpus, probe):
    report = _extract(corpus, "control", probe)
    assert probe.pages_sent_to_ocr == [], f"文本层页被送进 OCR：{probe.pages_sent_to_ocr}"
    assert report.ocr_attempted is False
    assert set(report.source_counts) == {loader.PAGE_SOURCE_TEXT_LAYER}
    for page in report.pages:
        assert page.source == loader.PAGE_SOURCE_TEXT_LAYER
        assert page.is_scanned is False
        assert page.ocr_elapsed_ms == 0.0
        assert page.text, "对照件的正文应当来自文本层"


def test_a_mixed_document_records_a_source_per_page(corpus, probe):
    """判据④"逐页不逐件"：同一份文件里 `ocr` / `text-layer` / `blank` 三形必须同时成立。"""
    probe.script[:] = [("text", "季度回款分析说明")]
    report = _extract(corpus, "mixed", probe)
    assert [page.source for page in report.pages] == [
        loader.PAGE_SOURCE_OCR,
        loader.PAGE_SOURCE_TEXT_LAYER,
        loader.PAGE_SOURCE_BLANK,
    ]
    assert probe.pages_sent_to_ocr == [1], "只有第 1 页该被送 OCR"
    assert report.scanned_page_numbers == (1,)
    assert report.pages[2].note == "该页既无文本层也无图像对象"
    assert "季度回款分析说明" in report.text
    assert "Quarterly budget review notes" in report.text


def test_blank_page_without_bitmap_or_text_is_named_blank(corpus, tmp_path):
    """`blank` 那一形单独钉一次：既无文本层也无图像对象的页不该被猜成扫描页。"""
    path = tmp_path / "r540_blank.pdf"
    samples.build_pdf(path, [{}])
    report = loader.extract_pdf(str(path), engine=OcrProbe().engine)
    assert report.pages[0].source == loader.PAGE_SOURCE_BLANK
    assert report.pages[0].is_scanned is False
    assert report.text == ""


# ==================== ⑤ OCR 出来的字过同一把 sanitize_text（R130 那一刀） ====================


def test_nul_from_the_ocr_leg_never_reaches_the_body(corpus, probe):
    probe.script[:] = [("text", "第一条\x00差旅费"), ("text", "第二条"), ("text", "第三条"), ("text", "第四条")]
    report = _extract(corpus, "scan", probe)
    assert "\x00" not in report.text
    assert "第一条差旅费" in report.text


def test_a_page_whose_only_glyph_was_nul_is_not_counted_as_recognized(corpus, probe):
    """不变量：`source=ocr` ⇒ 这一页真的往正文里放了字。净化完什么都不剩就得改口。"""
    probe.script[:] = [("text", "\x00"), ("text", "第二条"), ("text", "第三条"), ("text", "第四条")]
    report = _extract(corpus, "scan", probe)
    first = report.pages[0]
    assert first.source == loader.PAGE_SOURCE_OCR_EMPTY
    assert first.note == "OCR 文字经 sanitize_text 后为空"


# ==================== 静态钉：三形常量、降级句前缀、引擎身份（反证 K1 的红牙） ====================


def test_the_three_ocr_shapes_and_their_wording_are_the_inventoried_ones():
    assert loader.PAGE_SOURCE_OCR == "ocr"
    assert loader.PAGE_SOURCE_OCR_EMPTY == "ocr-empty"
    assert loader.PAGE_SOURCE_OCR_DEGRADED == "ocr-degraded"
    assert loader.PAGE_SOURCE_TEXT_LAYER == "text-layer"
    assert loader.PAGE_SOURCE_BLANK == "blank"
    assert loader.DEGRADATION_NOTE_PREFIX == "扫描页 OCR 降级"
    assert ocr_channel.ENGINE_UNAVAILABLE_NOTE == "本地 OCR 引擎不可用，扫描页未识别文字"
    assert loader.SCANNED_PAGE_TEXT_CHARS == 48


def test_the_only_allowed_engine_is_the_local_rapidocr():
    """判据② 的私有化口径：引擎名一旦被换走，本件当场红（反证 K1 的另一枚靶子）。"""
    assert ocr_channel.OCR_ENGINE_MODULE == "rapidocr_onnxruntime"
    assert ocr_channel.OCR_ENGINE_CLASS == "RapidOCR"
    assert loader.ocr_channel is ocr_channel, "loader 的 OCR 腿不指向本模块 = 另有第二套通道"
    assert ocr_channel.DEFAULT_OCR_DPI == 200


def test_ocr_dependency_modules_are_importable_here():
    """这台机上四枚依赖全在位（本单纸 §1 的凭据）：不在位就跑不到真引擎，必须说出来而不是假绿。"""
    import importlib.util

    for name in ("rapidocr_onnxruntime", "pypdfium2", "PIL", "pypdf"):
        assert importlib.util.find_spec(name) is not None, f"依赖缺失：{name}"
    assert ocr_channel.missing_model_files() == (), ocr_channel.missing_model_files()


@pytest.mark.skipif(
    not REAL_OCR,
    reason="真打 rapidocr 不是常驻腿：R540_REAL_OCR=1 才跑（见件首「非常驻的那半格」）",
)
def test_real_engine_reads_the_scanned_pages_end_to_end(corpus):
    """非常驻：真引擎 + 真栅格，逐页必须出字，且关键句子在正文里（耗时只打印不钉）。"""
    report = loader.extract_pdf(corpus["scan"])
    assert report.ocr_available is True
    assert report.source_counts.get(loader.PAGE_SOURCE_OCR, 0) >= 1
    assert "季度回款分析说明" in report.text
    for page in report.pages:
        if page.source == loader.PAGE_SOURCE_OCR:
            assert page.ocr_elapsed_ms > 0
            assert page.raster_size == (1653, 2339)