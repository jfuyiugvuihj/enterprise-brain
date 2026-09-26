r"""R298 判据②⑤⑥ · OCR 只能在本地、降级必须说明原因、出来的文字过同一把 NUL 尺子。

判据全文在 docs/handoff/2026-09-15-backend-followup-requests.md §102 二。全程离线：
不打真引擎（只读它的安装事实），不连库、不起服务、不开网络。

六枚钉子
② 引擎身份：模块名与类名字面钉死 `rapidocr_onnxruntime` / `RapidOCR`；本模块源码里不许
   出现任何 HTTP/云厂商出口（一把字符串尺子，加了就红）。模型三枚在位是**事实核对**，
   缺失/没装/初始化失败三态各出一句写明原因的降级结论 —— 严禁静默空文本冒充成功。
⑤ OCR 通道出来的文字过的是 loader 里那**同一个** :func:`sanitize_text`（拿 spy 钉"过的是
   这个函数对象"，不是"结果恰好干净"）；整页只有 NUL 的那种净化结果算"没出字"，不算出字。
⑥ 反证三把：(a) 纯图件关掉 OCR ⇒ 空文本 ⇒ `evaluate_index_eligibility` 给 no_text_content
   ⇒ chat.py 那一行把 parse_status 记成 failed（源形状同件核对）；(d) 引擎禁用 ⇒ 出降级句
   而非空文本；(e) OCR 文字带 NUL ⇒ 当场红。
"""
from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path

import numpy as np
import pytest

from app.documents import index_policy
from app.rag import loader, ocr as ocr_channel

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_PDF = REPO_ROOT / "tests" / "fixtures" / "r298_scanned_pages.pdf"
CHAT_SOURCE = (REPO_ROOT / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

NUL = "\x00"
DIRTY_OCR_TEXT = "密级" + NUL + "内部资料" + NUL + " 编号 2026-0926"
CLEAN_OCR_TEXT = "密级内部资料 编号 2026-0926"


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


class ScriptedEngine:
    """假引擎：按调用顺序吐给定行。``rows=None`` 就是"图里没字"。"""

    def __init__(self, *rows) -> None:
        self.rows = list(rows)
        self.calls = 0

    def __call__(self, array):  # noqa: ANN001 - 与 RapidOCR.__call__ 同形
        row = self.rows[min(self.calls, len(self.rows) - 1)] if self.rows else None
        self.calls += 1
        if row is None:
            return (None, [0.0])
        box = [[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]]
        return ([[box, row, 0.98]], [0.0])


class LogRecorder:
    """把模块里的 logger 换成记账桩：降级必须留 WARNING，这条不靠 caplog 的配置。"""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message, *args, **kwargs) -> None:
        self.warnings.append(str(message))

    def info(self, message, *args, **kwargs) -> None:
        self.infos.append(str(message))

    def debug(self, message, *args, **kwargs) -> None:
        return None


@pytest.fixture(autouse=True)
def clean_engine_cache():
    """引擎缓存是进程级的：件与件之间必须清零，否则上一枚的降级会染红下一枚。"""
    ocr_channel.reset_engine_cache()
    yield
    ocr_channel.reset_engine_cache()


@pytest.fixture()
def stub_raster(monkeypatch):
    def _fake(pdf_path: str, page_number: int, *, dpi: int):
        return np.zeros((page_number + 8, page_number + 16, 3), dtype="uint8")

    monkeypatch.setattr(ocr_channel, "rasterize_page", _fake)
    return _fake


# ------------------------------------------------------------------ 判据②


def test_engine_identity_is_pinned_to_the_local_rapidocr():
    assert ocr_channel.OCR_ENGINE_MODULE == "rapidocr_onnxruntime"
    assert ocr_channel.OCR_ENGINE_CLASS == "RapidOCR"
    assert ocr_channel.DEFAULT_OCR_DPI == 200
    # 三枚模型的实测尺寸写进注释（判据②"模型打在 wheel 里"的凭据），不许只写"内置"
    source = Path(ocr_channel.__file__).read_text(encoding="utf-8")
    for needle in ("4,745,517", "10,857,958", "585,532"):
        assert needle in source, f"模型尺寸注释丢了 {needle}"


def test_no_network_egress_anywhere_in_the_ocr_channel():
    """判据②：不许任何云 API、不许联网取模型。字符串尺子，加一行出口就红。"""
    forbidden = (
        "urllib",
        "http.client",
        "httpx",
        "requests",
        "socket",
        "aiohttp",
        "boto3",
        "oss2",
        "aliyun",
        "tencent",
        "azure",
        "openai",
        "PaddleOCRServer",
        "use_gpu=True",
    )
    for name in ("ocr.py", "loader.py"):
        source = (REPO_ROOT / "app" / "rag" / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"app/rag/{name} 出现了网络/云出口：{token}"


def test_model_files_are_present_offline_and_named():
    models = ocr_channel.model_files()
    assert len(models) == 3
    assert ocr_channel.missing_model_files() == ()
    assert ocr_channel.unavailable_reason() is None
    for path in models:
        assert path.is_file(), f"模型不在位（离线交付的前提破了）：{path}"
        assert path.stat().st_size > 0


def test_missing_model_degrades_with_the_file_name(monkeypatch):
    monkeypatch.setattr(ocr_channel, "_MODEL_FILE_NAMES", ("models/ch_PP-OCRv4_det_infer.onnx", "models/nope.onnx"))
    reason = ocr_channel.unavailable_reason()
    assert reason is not None and "模型文件缺失" in reason and "nope.onnx" in reason

    logs = LogRecorder()
    monkeypatch.setattr(ocr_channel, "logger", logs)
    run = ocr_channel.ocr_pages(str(SCANNED_PDF), [1, 2])
    assert run.available is False
    assert run.degradation_note  # 判据②：一句写明原因的降级，不是空
    assert "模型文件缺失" in run.degradation_note
    assert [outcome.text for outcome in run.outcomes] == ["", ""]
    assert all(outcome.status == ocr_channel.STATUS_UNAVAILABLE for outcome in run.outcomes)
    assert any("引擎降级" in line for line in logs.warnings), logs.warnings


def test_uninstalled_engine_says_so_and_still_does_not_raise(monkeypatch):
    monkeypatch.setattr(ocr_channel, "OCR_ENGINE_MODULE", "rapidocr_onnxruntime_absent_here")
    reason = ocr_channel.unavailable_reason()
    assert reason is not None and "未安装" in reason
    run = ocr_channel.ocr_pages(str(SCANNED_PDF), [1])
    assert run.available is False and "未安装" in run.degradation_note
    with pytest.raises(ocr_channel.OcrEngineUnavailable, match="未安装"):
        ocr_channel.get_engine()


def test_engine_that_fails_to_initialize_is_reported_as_such(monkeypatch):
    """初始化炸了（不是没装、也不是缺模型）：降级句要说是初始化失败。"""
    monkeypatch.setattr(ocr_channel, "OCR_ENGINE_MODULE", "json")  # 装得上，但没有 RapidOCR
    monkeypatch.setattr(ocr_channel, "_MODEL_FILE_NAMES", ())
    with pytest.raises(ocr_channel.OcrEngineUnavailable, match="初始化失败"):
        ocr_channel.get_engine()


# ------------------------------------------------------------------ 判据⑤


def test_ocr_text_passes_through_the_same_sanitize_text(monkeypatch, stub_raster):
    seen: list[str] = []
    original = loader.sanitize_text

    def spy(text):
        seen.append(text)
        return original(text)

    monkeypatch.setattr(loader, "sanitize_text", spy)
    engine = ScriptedEngine(DIRTY_OCR_TEXT)
    with _quiet_parser_warnings():
        text = loader.load_pdf(str(SCANNED_PDF), engine=engine)
    assert NUL not in text
    assert CLEAN_OCR_TEXT in text
    # 钉的是"过的是这个函数对象、且吃的就是引擎吐回来的那串脏字"，不是"结果恰好干净"
    assert DIRTY_OCR_TEXT in seen, "OCR 通道的文字没走 sanitize_text"


def test_a_page_whose_ocr_text_is_only_nul_counts_as_no_text(monkeypatch, stub_raster):
    engine = ScriptedEngine(NUL, NUL + NUL, "第三条 附则")
    with _quiet_parser_warnings():
        report = loader.extract_pdf(str(SCANNED_PDF), engine=engine)
    assert report.pages[0].source == loader.PAGE_SOURCE_OCR_EMPTY
    assert report.pages[1].source == loader.PAGE_SOURCE_OCR_EMPTY
    assert report.pages[2].source == loader.PAGE_SOURCE_OCR
    assert NUL not in report.text
    # source=ocr 的不变量：这一页真的往正文里放了字
    assert all(page.text or page.source != loader.PAGE_SOURCE_OCR for page in report.pages)


def test_sanitizing_ocr_text_is_not_optional_shape(monkeypatch, stub_raster):
    """把 sanitize_text 换成恒等 ⇒ 件里当场可见脏字进了正文（反证⑤的"红"）。

    不真改文件，只在件里换桩：等价于"谁把判据⑤ 那一刀摘了"。
    """
    monkeypatch.setattr(loader, "sanitize_text", lambda text: text)
    engine = ScriptedEngine(DIRTY_OCR_TEXT)
    with _quiet_parser_warnings():
        report = loader.extract_pdf(str(SCANNED_PDF), engine=engine)
    assert NUL in report.text  # 少了那一刀，PG 腿 executemany 必拒（R130）


# ------------------------------------------------------------------ 判据⑥ 反证


def test_counter_evidence_a_pure_image_pdf_without_ocr_is_a_failed_parse():
    """⑥(a)：纯图件 + 关掉 OCR ⇒ 一个字都没有 ⇒ 目录侧就是 failed。

    这一枚钉的是本单要修的那一格：客户上传扫描件的当前结局是"上传即失败"，不是"能传但
    搜不到"。关掉通道之后必须精确回到那一格，改动才算落在同一位置。
    """
    with _quiet_parser_warnings():
        text = loader.load_pdf(str(SCANNED_PDF), enable_ocr=False)
    assert text == ""
    eligibility = index_policy.evaluate_index_eligibility(text, size_bytes=SCANNED_PDF.stat().st_size)
    assert eligibility.eligible is False
    assert eligibility.reason == index_policy.REASON_NO_TEXT
    # 落库那一行的映射（禁域只读核对：这行改口了，上面这半截结论就不成立）
    assert 'parse_status="failed" if eligibility.reason == REASON_NO_TEXT else "ready",' in CHAT_SOURCE
    assert "content = await asyncio.to_thread(load_document, file_path)" in CHAT_SOURCE


def test_counter_evidence_d_disabled_engine_yields_a_sentence_not_silence(monkeypatch):
    """⑥(d)：引擎禁用 ⇒ 出降级句而非空文本（判据⑥原文）。"""
    monkeypatch.setattr(ocr_channel, "_MODEL_FILE_NAMES", ("models/absent.onnx",))
    with _quiet_parser_warnings():
        silent = loader.load_pdf(str(SCANNED_PDF))  # 默认：不把说明塞进正文
        spoken = loader.load_pdf(str(SCANNED_PDF), include_degradation_note=True)
        report = loader.extract_pdf(str(SCANNED_PDF))
    assert silent == ""  # 正文干净：那句"没识别出来"不该被 embedding 成一块墓碑
    assert report.ocr_available is False
    assert report.degradation_notes and "模型文件缺失" in report.degradation_sentence
    for line in report.degradation_notes:
        assert "第" in line and "页" in line, line  # 降级要能报到页
    assert spoken.strip() and spoken != silent
    # 引擎级降级用 ENGINE_UNAVAILABLE_NOTE 这一档措辞，和"引擎在、这页没跑成"区分开
    assert spoken.startswith(ocr_channel.ENGINE_UNAVAILABLE_NOTE), spoken
    assert "模型文件缺失" in spoken


def test_counter_evidence_pages_beyond_the_cap_are_named(monkeypatch, stub_raster):
    """超上限那一档：少了几页要能说是哪几页，不许和"图里没字"混成一色。"""
    monkeypatch.setenv("DOCUMENT_OCR_MAX_PAGES", "1")
    engine = ScriptedEngine("第一页识别内容", "第二页识别内容", "第三页识别内容")
    with _quiet_parser_warnings():
        report = loader.extract_pdf(str(SCANNED_PDF), engine=engine)
    assert report.pages[0].source == loader.PAGE_SOURCE_OCR
    assert report.pages[2].source == loader.PAGE_SOURCE_OCR_DEGRADED
    assert "页数上限" in report.degradation_sentence
    # 引擎是好的，只是这一轮没排上：措辞走"扫描页 OCR 降级"那一档，不冒充引擎故障
    assert report.ocr_available is True
    assert report.degradation_sentence.startswith(loader.DEGRADATION_NOTE_PREFIX), report.degradation_sentence
    assert ocr_channel.resolve_max_pages() == 1


def test_empty_recognition_is_not_reported_as_a_failure(stub_raster):
    """图里真没字 ⇒ ok=True + status=empty，不许冒充降级；也不能反过来把降级当空页。"""
    run = ocr_channel.ocr_pages(str(SCANNED_PDF), [1], engine=ScriptedEngine(None))
    assert run.available is True
    assert run.outcomes[0].ok is True
    assert run.outcomes[0].status == ocr_channel.STATUS_EMPTY
    assert run.degradation_note == ""