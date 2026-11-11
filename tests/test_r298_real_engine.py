r"""R298 判据③ + 判据⑥(b) · 真引擎（rapidocr_onnxruntime / onnxruntime，CPU 无 GPU）跑通。

本文件是全单唯一真的把 onnxruntime 拉起来的地方，也是"客户机没有 GPU 也得跑得完"这句话
唯一能说出口的凭据来源。它**不联网**：模型三枚由 wheel 自带（app/rag/ocr.py 里点名的实测
尺寸），加载走本地文件。判据② 的网络闸门钉在 tests/test_r298_ocr_channel.py。

三枚钉子
③ 栅格化 = pypdfium2，DPI 参数化到"页边像素数随 dpi 线性变化"这一级（逐档精确核对，不是
   跑一下没报错）；单页耗时**现取现打印**（下面的 R298 计时表），门内只留确定性断言 ——
   理由同 R269 收口那一笔：把会浮动的量当回归门，就是把假红买进门里。
⑥(b) 纯图 fixture 有 OCR ⇒ 正文关键句逐句在位，且过 R49 入索引判定（与 ⑥(a) 关掉通道那
   一枚成对：同一份文件、同一个阈值，只差 OCR 这条腿）。

"可检索"在本件的可证口径：正文关键句在位 + `evaluate_index_eligibility` 判 eligible。
真打向量库那一层要动 retriever/pg_store（本单禁域），不在这里越界。
"""
from __future__ import annotations

import contextlib
import io
import logging
import math
import time
from pathlib import Path

import numpy as np
import pytest

from app.documents import index_policy
from app.rag import loader, ocr as ocr_channel

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
SCANNED_PDF = FIXTURES / "r298_scanned_pages.pdf"
MIXED_PDF = FIXTURES / "r298_mixed_pages.pdf"

#: fixture 的页面几何（pt）：A4，见 tests/fixtures/r298_build_fixtures.py
PAGE_PT = (595, 842)

#: 判据③ 要认的正文关键句（渲染进位图的真句子，不是桩话）。
SCANNED_MARKERS = (
    "员工报销制度",
    "第一条差旅费须在出行后三十日内提交财务部",
    "第二条单笔金额超过5000元需总经理审批",
    "信息部运维值班表",
    "紧急联系人林晓13800001234",
    "本制度自2026年3月1日起施行",
)

#: 单页耗时上限（秒）。这不是性能验收，是一枚"炸了就红"的兜底：本机实测单页 2-3 s 量级，
#: 上限放到 60 s（20 倍余量），任何 CPU 机器都能跑得完，也不会盖住真的失控。
PAGE_CEILING_S = 60.0


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


@pytest.fixture(scope="module", autouse=True)
def one_engine_for_the_module():
    """本模块共用一个引擎实例，退出时清零：不把 onnxruntime 会话漏给后面的文件。"""
    started = time.perf_counter()
    ocr_channel.get_engine()
    init_s = time.perf_counter() - started
    print(f"\nR298 引擎初始化（本机 CPU，含读三枚 onnx 模型）：{init_s:.3f} s")
    yield
    ocr_channel.reset_engine_cache()


@pytest.fixture(scope="module")
def real_scan_run():
    with _quiet_parser_warnings():
        return loader.extract_pdf(str(SCANNED_PDF))


@pytest.fixture(scope="module")
def real_mixed_run():
    with _quiet_parser_warnings():
        return loader.extract_pdf(str(MIXED_PDF))


# ------------------------------------------------------------------ 判据③


@pytest.mark.parametrize("dpi", [72, 96, 150, 200, 300])
def test_rasterization_is_pypdfium2_and_scales_exactly_with_dpi(dpi):
    """DPI 参数化钉到像素级：页数 × 每档边长，换库或换算法都会在这里红。"""
    array = ocr_channel.rasterize_page(str(SCANNED_PDF), 1, dpi=dpi)
    expected = (math.ceil(PAGE_PT[0] * dpi / 72), math.ceil(PAGE_PT[1] * dpi / 72))
    assert array.dtype == np.uint8
    assert array.ndim == 3 and array.shape[2] == 3, f"栅格化没交出 RGB：{array.shape}"
    assert (array.shape[1], array.shape[0]) == expected
    assert array.flags["C_CONTIGUOUS"], "rapidocr 拿非连续数组会自己再拷一份"


def test_dpi_bounds_are_enforced_where_pixels_are_allocated():
    """越界 DPI 必须在**申请像素之前**被拒：这是一份上传能把客户机内存吃穿的地方。"""
    for bad in (71, 601, 0, -200):
        with pytest.raises(ValueError):
            ocr_channel.rasterize_page(str(SCANNED_PDF), 1, dpi=bad)
    # 上下限本身是合法的（72 与 600 是实测过的两档边界）
    assert ocr_channel.resolve_dpi(ocr_channel.MIN_OCR_DPI) == 72
    assert ocr_channel.resolve_dpi(ocr_channel.MAX_OCR_DPI) == 600
    assert ocr_channel.resolve_dpi(None) == ocr_channel.DEFAULT_OCR_DPI
    assert ocr_channel.resolve_dpi(300) == 300


def test_dpi_env_override_is_read_at_call_time(monkeypatch):
    monkeypatch.setenv("DOCUMENT_OCR_DPI", "150")
    assert ocr_channel.resolve_dpi(None) == 150
    monkeypatch.setenv("DOCUMENT_OCR_DPI", "abc")
    assert ocr_channel.resolve_dpi(None) == ocr_channel.DEFAULT_OCR_DPI
    monkeypatch.setenv("DOCUMENT_OCR_DPI", "601")  # 越界：退回默认并 WARNING，不炸上传
    assert ocr_channel.resolve_dpi(None) == ocr_channel.DEFAULT_OCR_DPI
    monkeypatch.setenv("DOCUMENT_OCR_DPI", "600")  # 合法上限：照收
    assert ocr_channel.resolve_dpi(None) == 600


def test_r298_timing_table_is_measured_now_not_asserted(real_scan_run, real_mixed_run) -> None:
    """判据③：CPU 单页实测耗时。打印现取值，门内只钉"跑了、>0、没失控"。"""
    rows = []
    for label, report in (("r298_scanned_pages", real_scan_run), ("r298_mixed_pages", real_mixed_run)):
        for page in report.pages:
            if page.source != loader.PAGE_SOURCE_OCR:
                continue
            rows.append((label, page.page_number, page.raster_size, page.ocr_elapsed_ms))
    assert len(rows) == 5, f"该跑出 5 页 OCR，实出 {len(rows)} 页"
    print("\nR298 计时表（本机 CPU / onnxruntime，dpi=200，栅格化+识别整页口径）")
    print(f"{'fixture':22} {'页':>3} {'栅格(宽x高)':>14} {'单页 ms':>9}")
    for label, number, size, ms in rows:
        print(f"{label:22} {number:>3} {size[0]:>6}x{size[1]:<7} {ms:>9.0f}")
    seconds = [ms / 1000.0 for _l, _n, _s, ms in rows]
    print(
        "单页统计：min %.2f s / 中位 %.2f s / max %.2f s；%d 页合计 %.2f s"
        % (
            min(seconds),
            sorted(seconds)[len(seconds) // 2],
            max(seconds),
            len(seconds),
            sum(seconds),
        )
    )
    for label, number, _size, ms in rows:
        assert ms > 0, f"{label} 第{number}页没记到耗时"
        assert ms / 1000.0 < PAGE_CEILING_S, f"{label} 第{number}页 {ms:.0f} ms 失控"


# ------------------------------------------------------------------ 判据⑥(b)


def test_counter_evidence_b_scanned_document_becomes_searchable(real_scan_run, real_mixed_run):
    """⑥(b)：有 OCR ⇒ 关键句在位；同一份文件过 R49 判定 = eligible（与 ⑥(a) 成对）。"""
    text = real_scan_run.text
    assert real_scan_run.scanned_page_numbers == (1, 2, 3)
    for marker in SCANNED_MARKERS:
        assert marker in text, f"识别结果缺关键句：{marker}"
    assert "\x00" not in text
    size = SCANNED_PDF.stat().st_size
    with_ocr = index_policy.evaluate_index_eligibility(text, size_bytes=size)
    without_ocr = index_policy.evaluate_index_eligibility(
        loader.load_pdf(str(SCANNED_PDF), enable_ocr=False), size_bytes=size
    )
    assert with_ocr.eligible is True, with_ocr.reason
    assert without_ocr.eligible is False and without_ocr.reason == index_policy.REASON_NO_TEXT
    # 混合件：文本层页与 OCR 页各归各，正文按页序拼起来
    mixed_text = real_mixed_run.text
    assert mixed_text.index("Policy index 2026") < mixed_text.index("信息部运维值班表")
    assert mixed_text.index("信息部运维值班表") < mixed_text.index("decorative")
    assert mixed_text.index("decorative") < mixed_text.index("本制度自2026年3月1日起施行")
    assert real_mixed_run.summary().count("ocr") >= 1


def test_real_engine_channel_reports_its_own_numbers_per_page(real_scan_run):
    """逐页账要能自证：status=ocr 的页必须有栅格尺寸与耗时，来源不许含糊。"""
    for page in real_scan_run.pages:
        assert page.is_scanned is True
        assert page.source == loader.PAGE_SOURCE_OCR
        assert page.raster_size == (1653, 2339), page.raster_size
        assert page.text_layer_chars == 0
        assert page.ocr_elapsed_ms > 0
        assert page.note == ""