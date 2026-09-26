r"""R298 判据①④ · 扫描页是**判**出来的，且"有文本层的页一个字都不许多 OCR"。

判据全文在 docs/handoff/2026-09-15-backend-followup-requests.md §102 二（本树该份文档只到
§101.15，派工词已把六条抄全）。本文件全程离线：不打真引擎、不连库、不起服务。

四枚钉子
① 扫描页 = "该页文本层实质字符 < 阈值" **AND** "该页存在位图对象"。fixture 备齐四种形
   （有图无字 / 有字无图 / 有字有图 / 无字无图），两半各自单独都不成立。阈值是有注释的
   常量，注释里是 documents/ 36 页的实测分布；``report.summary()`` 直接给"扫描页数/总页数"。
④ 逐页判、逐页记来源，不许整件二选一：混合件 6 页同时出现 4 种来源；把 OCR 通道的入口
   换成"一调就炸"的桩之后，纯文本层件与空白件照常出全文 —— 钉的是"这条路对它们一次都
   没开过"，不是"开了又丢掉"。
⑥(c) 反证一把：把"存在图像对象"改成恒真 ⇒ 空白页立刻被误判成扫描页（假阳性当场可见）；
   把它改成恒假 ⇒ 真扫描页一条都判不出来，退回"上传即失败"那一格。两半都在做事。

fixture 由 tests/fixtures/r298_build_fixtures.py 生成；逐页真值抄在 ``MIXED_PAGE_SHAPES``
（2026-09-26 现取），改了 fixture 这里就会红。
"""
from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path

import numpy as np
import pytest

from app.rag import loader, ocr as ocr_channel

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

SCANNED_PDF = FIXTURES / "r298_scanned_pages.pdf"
TEXT_ONLY_PDF = FIXTURES / "r298_text_only.pdf"
BLANK_PDF = FIXTURES / "r298_blank.pdf"
MIXED_PDF = FIXTURES / "r298_mixed_pages.pdf"

#: 混合件逐页真值（现取 2026-09-26）：页码 -> (文本层实质字符数, 该页有没有位图对象)
MIXED_PAGE_SHAPES = {
    1: (127, False),  # 纯文本层
    2: (0, True),  # 整页位图，无文本层
    3: (107, True),  # 文本层 + 一张插图（数字 PDF 的常见形，不该 OCR）
    4: (1, True),  # 整页位图 + 1 字符垃圾隐形层（扫描件本件）
    5: (0, True),  # 整页位图，图里没有字
    6: (0, False),  # 空白页
}

#: 判据① 的阈值。数值本身在 app/rag/loader.py 里有实测出处，这里钉"它是常量且没改口"。
THRESHOLD = 48


@contextlib.contextmanager
def _quiet_parser_warnings():
    """pypdf 解析真语料会往 stderr 刷坏 CMap 行（R130 同一手法），本单不修它，只在件里静音。"""
    pypdf_logger = logging.getLogger("pypdf")
    previous = pypdf_logger.level
    pypdf_logger.setLevel(logging.ERROR)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            yield
    finally:
        pypdf_logger.setLevel(previous)


class RecordingEngine:
    """假引擎：只负责"被叫到时报一行可辨认的字"，与识图无关。用来数"被叫了几次"。"""

    def __init__(self, prefix: str = "识别行") -> None:
        self.prefix = prefix
        self.calls = 0

    def __call__(self, array):  # noqa: ANN001 - 与 RapidOCR.__call__ 同形
        self.calls += 1
        box = [[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]]
        return ([[box, f"{self.prefix} 第{self.calls}次", 0.99]], [0.0])


class PageAwareEngine(RecordingEngine):
    """按页给答案的假引擎：只有 ``no_text_pages`` 之外的页能认出字。

    页码从桩栅格的形状里解回来（见下面的 ``raster_pages`` fixture —— 桩按"高 = 页码 + 8"
    造图），于是不用真 OCR 也能钉住"这页确实没字"与"这页没跑成"是两件事。
    """

    def __init__(self, no_text_pages: set[int] | None = None) -> None:
        super().__init__(prefix="扫描页正文")
        self.no_text_pages = no_text_pages or set()
        self.seen_pages: list[int] = []

    def __call__(self, array):  # noqa: ANN001
        page_number = int(array.shape[0]) - 8
        self.seen_pages.append(page_number)
        self.calls += 1
        if page_number in self.no_text_pages:
            return (None, [0.0])
        box = [[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]]
        return ([[box, f"{self.prefix} 第{page_number}页", 0.99]], [0.0])


@pytest.fixture(autouse=True)
def stub_raster(monkeypatch):
    """栅格化桩（本文件 autouse）：记下"哪些页被交给了 OCR"，并回一张形状里编着页码的
    小图 —— 于是假引擎也能按页给不同答案，全程不读真像素、不打真引擎。
    """
    seen: list[int] = []

    def _fake(pdf_path: str, page_number: int, *, dpi: int):
        seen.append(page_number)
        return np.zeros((page_number + 8, page_number + 16, 3), dtype="uint8")

    monkeypatch.setattr(ocr_channel, "rasterize_page", _fake)
    return seen


def _extract(path: Path, engine=None) -> loader.PdfExtractionReport:
    """走一遍提取，默认用"只有第 2、4 页能认出字"的假引擎。"""
    engine = engine or PageAwareEngine(no_text_pages={5})
    with _quiet_parser_warnings():
        return loader.extract_pdf(str(path), engine=engine)


# ------------------------------------------------------------------ 判据①


def test_threshold_is_a_documented_constant_with_a_measured_floor():
    assert loader.SCANNED_PAGE_TEXT_CHARS == THRESHOLD
    assert loader.SCANNED_PAGE_TEXT_CHARS_ENV == "PDF_SCANNED_PAGE_TEXT_CHARS"
    assert loader.scanned_page_text_char_threshold() == THRESHOLD
    lines = Path(loader.__file__).read_text(encoding="utf-8").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("SCANNED_PAGE_TEXT_CHARS ="))
    block: list[str] = []
    for line in reversed(lines[:index]):
        if not line.startswith("#:"):
            break
        block.append(line)
    comment = "\n".join(reversed(block))
    # 判据① 要的是"判出来的不是猜的"：紧贴常量的那段注释里必须留着实测出处，
    # 不许只剩一句"经验值"。
    assert len(block) >= 8, "阈值注释缩成 %d 行了" % len(block)
    for needle in ("实测", "refactor_guide.pdf", "79", "AI-Agent"):
        assert needle in comment, "阈值注释丢了实测出处：" + needle


def test_env_override_moves_the_threshold(monkeypatch):
    monkeypatch.setenv("PDF_SCANNED_PAGE_TEXT_CHARS", "200")
    assert loader.scanned_page_text_char_threshold() == 200
    report = _extract(MIXED_PDF)
    # 抬到 200 之后第 3 页（107 字 + 有图）才会被判成扫描页；第 1 页 127 字但无图，仍不判
    assert report.scanned_page_numbers == (2, 3, 4, 5)
    assert report.pages[0].is_scanned is False
    monkeypatch.setenv("PDF_SCANNED_PAGE_TEXT_CHARS", "0")
    assert _extract(MIXED_PDF).scanned_pages == 0
    monkeypatch.setenv("PDF_SCANNED_PAGE_TEXT_CHARS", "not-a-number")
    assert loader.scanned_page_text_char_threshold() == THRESHOLD  # 非法值退回常量，不炸


def test_scanned_page_needs_both_halves_of_the_conjunction():
    report = _extract(MIXED_PDF)
    assert report.page_count == 6
    assert report.scanned_pages == 3
    assert report.scanned_page_numbers == (2, 4, 5)
    for number, (chars, has_image) in MIXED_PAGE_SHAPES.items():
        page = report.pages[number - 1]
        assert page.text_layer_chars == chars, f"第{number}页文本层字符数变了"
        assert page.has_image_object is has_image, f"第{number}页位图对象判定变了"
    # 第 3 页：有图，但文本层 107 字 >= 阈值 ⇒ 不是扫描页（右半边单独不成立）
    assert report.pages[2].is_scanned is False
    # 第 6 页：0 字，可没有图 ⇒ 空白页，不是扫描页（左半边单独不成立）
    assert report.pages[5].is_scanned is False
    # 第 4 页：1 个字符的垃圾隐形层 + 整页位图 ⇒ 扫描页（扫描件最常见的那一形）
    assert report.pages[3].is_scanned is True


def test_report_states_scanned_over_total_pages():
    report = _extract(MIXED_PDF)
    summary = report.summary()
    assert summary == report.summary()  # summary 不藏状态
    assert "pages=6" in summary
    assert "scanned=3/6" in summary  # 判据① 点名要的那个口径
    assert "scanned_pages=[2, 4, 5]" in summary
    for expected in ("text-layer=2", "ocr=2", "ocr-empty=1", "blank=1"):
        assert expected in summary, summary


def test_pure_image_document_is_all_scanned_and_blank_is_none():
    scanned = _extract(SCANNED_PDF)
    assert scanned.page_count == 3
    assert scanned.scanned_page_numbers == (1, 2, 3)
    blank = _extract(BLANK_PDF)
    assert blank.scanned_pages == 0
    assert blank.pages[0].source == loader.PAGE_SOURCE_BLANK
    # "无字"不等于"扫描页"：没有图像对象的页一律走原路（今天的结局，本单不改）
    assert blank.text == ""


# ------------------------------------------------------------------ 判据④


def test_every_page_records_its_own_source():
    report = _extract(MIXED_PDF)
    sources = {page.page_number: page.source for page in report.pages}
    assert sources == {
        1: loader.PAGE_SOURCE_TEXT_LAYER,
        2: loader.PAGE_SOURCE_OCR,
        3: loader.PAGE_SOURCE_TEXT_LAYER,
        4: loader.PAGE_SOURCE_OCR,
        5: loader.PAGE_SOURCE_OCR_EMPTY,
        6: loader.PAGE_SOURCE_BLANK,
    }
    # 混合件不是"整件二选一"：同一份文件里两条通道同时在场
    assert len({sources[1], sources[2], sources[5]}) == 3, sources
    assert report.pages[4].note == "图像页 OCR 未检出文字"
    assert report.pages[4].text == ""  # 判成扫描页、跑了、图里没字 ⇒ 不编内容


def test_only_scanned_pages_reach_the_rasterizer(stub_raster):
    engine = PageAwareEngine(no_text_pages=set())
    loader.extract_pdf(str(MIXED_PDF), engine=engine)
    assert stub_raster == [2, 4, 5]  # 交出去的页 == 判出来的扫描页
    assert engine.seen_pages == [2, 4, 5]
    assert engine.calls == 3


def test_text_layer_pages_survive_a_rasterizer_that_bites(monkeypatch):
    """把 OCR 通道的入口换成"一调就抛"，纯文本层件与空白件必须照常出全文。

    这一枚钉的是"整件二选一"那条路：谁要是把 load_pdf 改回"要么全走文本层、要么整件
    OCR"，这里当场红，而不是绿得看不出区别。
    """

    def _bites(*args, **kwargs):
        raise AssertionError("有文本层的文件不该打开 OCR 通道（判据④）")

    monkeypatch.setattr(ocr_channel, "rasterize_page", _bites)
    with _quiet_parser_warnings():
        text = loader.load_pdf(str(TEXT_ONLY_PDF))
        blank_text = loader.load_pdf(str(BLANK_PDF))
    assert text == _legacy_pdf_text(TEXT_ONLY_PDF)
    assert text.count("Quarterly budget review notes") == 2  # 两页各一次，没被整件丢掉
    assert blank_text == ""


def test_ocr_output_lands_in_page_order_without_duplicating_body():
    engine = PageAwareEngine(no_text_pages={5})
    report = _extract(MIXED_PDF, engine=engine)
    assert report.pages[1].text == "扫描页正文 第2页"
    assert report.pages[3].text == "扫描页正文 第4页"
    # 垃圾隐形层那 1 个字符不该和 OCR 正文并存（双份正文 = 双份墓碑 + 双份近重复命中）
    assert "3" not in report.pages[3].text
    assert report.text.split("\n\n") == [
        report.pages[0].text,
        "扫描页正文 第2页",
        report.pages[2].text,
        "扫描页正文 第4页",
    ]
    # 第 1 页那句只在正文里出现一次：OCR 没有把文本层再认一遍
    assert report.text.count("Policy index 2026") == 1
    assert report.text.count("decorative") == 1


def test_guessing_images_inverts_the_ruling(monkeypatch):
    """判据⑥(c) 反证：把"存在图像对象"改成恒真 ⇒ 假阳性当场可见。

    空白页第 6 页立刻被当成扫描页送进 OCR（假阳性），而第 1 / 3 页仍由字符阈值守住 ——
    两半都在做事，摘掉任何一半都会红一片。
    """
    monkeypatch.setattr(loader, "page_has_image_object", lambda page: True)
    report = _extract(MIXED_PDF, engine=PageAwareEngine(no_text_pages={5, 6}))
    assert report.scanned_page_numbers == (2, 4, 5, 6)
    assert report.pages[5].source == loader.PAGE_SOURCE_OCR_EMPTY
    assert report.pages[0].is_scanned is False  # 127 字 > 阈值，这一半还守着
    assert report.pages[2].is_scanned is False


def test_dropping_the_image_half_loses_real_scans(monkeypatch):
    """另一半反证：不看图像 ⇒ 扫描页一条都判不出来，回到"上传即失败"那一格。"""
    monkeypatch.setattr(loader, "page_has_image_object", lambda page: False)
    report = _extract(MIXED_PDF)
    assert report.scanned_pages == 0
    assert {page.source for page in report.pages} == {loader.PAGE_SOURCE_TEXT_LAYER, loader.PAGE_SOURCE_BLANK}
    with _quiet_parser_warnings():
        assert loader.load_pdf(str(SCANNED_PDF)) == ""  # 判出的扫描页为 0 ⇒ 一个字都拿不到


# ------------------------------------------------------------------ 与旧行为对齐


def _legacy_pdf_text(path: Path) -> str:
    """把 R298 之前的 load_pdf 逐字重做一遍（pypdf + 同样的 strip / join）。"""
    from pypdf import PdfReader

    with _quiet_parser_warnings():
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                parts.append(page_text.strip())
    # R298 之前的出口就有 sanitize_text（R130），所以对照的这份也得过，否则比的是两把尺。
    return loader.sanitize_text("\n\n".join(parts).strip())


@pytest.mark.parametrize("path", [TEXT_ONLY_PDF, BLANK_PDF, MIXED_PDF, SCANNED_PDF])
def test_enable_ocr_false_reproduces_the_pre_r298_bytes(path):
    """判据④ 的存量面：关掉 OCR 通道 = 本单之前的行为，一个字都不许多、都不许少。"""
    with _quiet_parser_warnings():
        legacy = _legacy_pdf_text(path)
        current = loader.load_pdf(str(path), enable_ocr=False)
    assert current == legacy


def test_the_two_real_corpus_pdfs_have_no_scanned_pages_and_do_not_change():
    """现网语料面：documents/ 两本 36 页今天一页都不该判成扫描页，新旧输出逐字相等。

    这枚是"已入库的 1008 枚向量不会被本单改写"的最硬说法：改一个字符就会红。
    """
    for name in ("AI-Agent学习路线图.pdf", "refactor_guide.pdf"):
        path = REPO_ROOT / "documents" / name
        assert path.is_file(), f"语料不在位：{path}（存量对齐这枚判据失去前提）"
        with _quiet_parser_warnings():
            report = loader.extract_pdf(str(path))
            legacy = _legacy_pdf_text(path)
        assert report.scanned_pages == 0, f"{name} 被判出扫描页：{report.summary()}"
        assert min(page.text_layer_chars for page in report.pages) >= 79
        assert report.text == legacy