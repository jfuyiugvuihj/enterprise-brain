# -*- coding: utf-8 -*-
r"""R599 · V2 #13「一份真扫描件跑通一次并留读数」的常驻钉：合成扫描件在册 + 判定不空转。

钉什么（对应跟进单 §160.6 R599 判据逐格）：
 ① **进仓的那份件就是纸上当时读数的那份件**：sha256 与字节数逐枚钉死。
    理由不是"洁癖"，是 R148 那笔换图事故的直接教训——像素一旦被人换掉，账面读数就成了
    假话，而**换掉的人不需要改任何一行代码**。🔴 这里钉的是「已入库这枚字节的指纹」，
    不是「重跑一遍必然逐字节相同」：后者会随字体/机器浮动，正是 R269 收口那笔点名的假红族。
 ② **无文本层是三把尺各量一次**：``extract_text()`` 空串、页算子里 ``BT``/``Tj`` 零命中、
    每页挂着 ``/Subtype /Image``。前两把读 PDF 语法本身，不借 ``app/`` 的判断。
 ③ **R148 铁规的可执行版**：发生器里那 11 枚源句逐枚过三把禁尺（ASCII 数字 / 中文数字 /
    指标词），命中一枚即红；再加一把「句子折行后仍画不下就拒绝出件」的几何尺——首版件
    就是被它抓到句尾被画布静默裁掉（OCR 读回半句话，样本自己缺字却像识别质量差）。
 ④ **语料零变化**（判据③）：发生器只许写 ``docs/testing/fixtures/``，指到 ``documents/``
    ``data/`` ``chroma_db/`` 之下必须当场拒绝；顺带复查这份件今天确实没被拷进语料。
 ⑤ **扫描页判定不许空转**（判据② 的左半边）：这份件的 4 页必须逐页被判成扫描页；
    **同一枚件里再放一页「有文本层 + 挂位图」的对照页，它必须不被判成扫描页**。
    这一格是反证 K2 的红牙：把 ``loader.py`` 的 AND 摘宽成"只要有图"，对照页立刻被误判，
    本件当场红——判定改宽而账面不变的话，这份钉就是废铁。
    跑这腿用 ``enable_ocr=False``，**不碰引擎、不打模型**（判据⑤ 的"不许靠打 OCR 做常绿"）。
 ⑥ **R301 那格今天确实有消费方**（判据④）：静态复述在册链路的两端——上传回执带
    ``pdf_extraction`` 那一格（四支返回路径一支都不许漏），屏上那句「扫描页 N 页」。
    🔴 本件**不 import** ``app.api.v1.chat``：那枚模块在 import 期就按**相对 CWD** 建
    ``./chroma_db`` 持久客户端（``app/rag/retriever.py:1018`` 的默认值），在仓库里跑一次
    就会把 ``chroma_db/chroma.sqlite3`` 改脏（本班 15:49:56 实测踩到，已按 HEAD blob 还原）。

🔴 非常驻的那半格（如实写在这里，不硬钉成假绿）：**真打 rapidocr 的每一页读数**不在默认腿里
——CPU 单页实测 0.9–4.1 s（首枚含 onnx 首次推理预热），一台正在跑真机评测的机器不该为门
付这笔钱。想真打一次：

    set R599_REAL_OCR=1 && python -m pytest tests/test_r599_synthetic_scan.py -k real_engine -q

读数凭据纸：``docs/perf/r599-synthetic-scan-2026-10-03.md``；跑法 ``scripts/r599_readout.py``。
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.rag import loader  # noqa: E402

REAL_OCR = os.environ.get("R599_REAL_OCR") == "1"

FIXTURE = REPO_ROOT / "docs" / "testing" / "fixtures" / "r599-scan-demo.pdf"

#: ① 已入库件的一手指纹（10-03 本班现取；换件必红，改这枚常数必须由总控连同新读数一起并树）。
PINNED_SHA256 = "1c2aacd751601243605e963ed2b59290611cf1791cba70bba2de6e0660f37053"
PINNED_BYTES = 1154944
PINNED_PAGE_COUNT = 4

#: ⑤ 判定尺的两半边：阈值与栅格档位读自在册模块，不在这里抄第二份常数。
EXPECTED_RASTER_AT_DEFAULT_DPI = (1653, 2339)

CHAT_SOURCE = REPO_ROOT / "app" / "api" / "v1" / "chat.py"
DOC_PANEL_SOURCE = REPO_ROOT / "frontend" / "src" / "components" / "DocPanel.vue"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "r599_synthetic_scan", REPO_ROOT / "scripts" / "r599_synthetic_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


# ==================== ① + ② 件本体：指纹与零文本层 ====================


def test_the_committed_fixture_is_exactly_the_bytes_that_were_measured():
    """判据①：纸上当时的读数属于哪枚字节，今天必须还是那枚字节（R148 换图事故那一刀）。"""
    assert FIXTURE.is_file(), f"缺少扫描件凭据件：{FIXTURE}"
    raw = _fixture_bytes()
    assert len(raw) == PINNED_BYTES, f"件字节数漂移：{len(raw)} != {PINNED_BYTES}"
    assert hashlib.sha256(raw).hexdigest() == PINNED_SHA256, (
        "扫描件 sha256 漂移：像素被换过 = 纸上那份逐页读数作废。"
        "要么恢复原件，要么重跑 scripts/r599_readout.py 并把新读数一并并树。"
    )


def test_no_page_of_the_fixture_carries_a_text_layer():
    """判据①「无文本层」的第一、二把尺：pypdf 抽不出字，页算子里也没有文本绘制算子。"""
    from pypdf import PdfReader

    reader = PdfReader(str(FIXTURE))
    assert len(reader.pages) == PINNED_PAGE_COUNT
    for index, page in enumerate(reader.pages, start=1):
        layer = (page.extract_text() or "").strip()
        assert "".join(layer.split()) == "", f"第{index}页文本层不为空：{layer[:24]!r}"
        operators = builder._raw_page_operators(page)
        assert "BT" not in operators, f"第{index}页算子里出现 BT（文本块）"
        assert "Tj" not in operators, f"第{index}页算子里出现 Tj（绘制文字）"


def test_every_page_of_the_fixture_is_a_bitmap_page():
    """判据① 的另一半边：每页都挂着 ``/Subtype /Image``（AND 的右半边由 PDF 语法自己作证）。"""
    account = builder.account(FIXTURE)
    assert account["image_object_on_every_page"] is True, account["pages"]
    assert account["zero_text_layer_on_every_page"] is True
    assert account["no_text_draw_operator_on_every_page"] is True
    assert account["sha256"] == PINNED_SHA256
    for row in account["pages"]:
        assert row["mediabox"] == [0.0, 0.0, 595.0, 842.0], f"第{row['page']}页不是 A4"


# ==================== ③ R148 铁规：位图里不许有统计数字或假指标 ====================


def test_the_rendered_source_sentences_carry_no_statistics_at_all():
    """三把禁尺逐枚过源句；这里数的是**要印进像素的句子**，不是 PDF 里的字。"""
    lines = builder.page_lines()
    assert len(lines) == 11, f"源句枚数与纸上账不符：{len(lines)}"
    assert builder.statistics_offenders() == []
    for line in lines:
        assert not re.search(r"[0-9]", line), f"像素里出现 ASCII 数字：{line}"
        assert not (set(line) & set(builder.CJK_NUMERAL_CHARS)), f"像素里出现中文数字：{line}"
        assert not re.search(r"[%％]", line), f"像素里出现百分号：{line}"


def test_the_statistics_ruler_is_a_real_ruler():
    """尺自己得会响：把一句假指标喂进去，三把尺必须逐枚点名，不许沉默放行。"""
    caught = builder.statistics_offenders(
        ["回款同比增长百分之七。", "Q3 revenue grew 12.5%.", "呆滞物料占比 3.2%。"]
    )
    # 一把尺各点一枚名，同一句可以中两把尺（"百分之七" 既是中文数字也是指标词）。
    assert len(caught) == 6, caught
    assert any("ASCII 数字" in item for item in caught), caught
    assert any("中文数字" in item for item in caught), caught
    assert any("指标词" in item for item in caught), caught
    with pytest.raises(SystemExit):
        builder.assert_no_statistics_in_the_pixels(["单笔金额超过 5000 元需总经理审批。"])


def test_lines_that_do_not_fit_the_canvas_refuse_to_build():
    """几何尺：句子宽过画布可用宽度时**拒绝出件**，而不是把句尾静默裁掉（本班首版踩过的坑）。"""
    hand = builder.samples()
    # 第一把：一枚拆不开的拉丁长词宽过画布（折行救不了它）——静默裁尾就是一次假读数。
    with pytest.raises(SystemExit) as wide:
        builder.fit_lines(["W" * 80], size=44, hand=hand)
    assert "超出画布可用宽度" in str(wide.value)
    # 第二把：句子都能放下，但折完的行数越过下边距——同样必须拒绝出件。
    with pytest.raises(SystemExit) as tall:
        builder.fit_lines(["巡检记录填写说明。"] * 40, size=44, hand=hand)
    assert "越过下边距" in str(tall.value)
    # 在册句子两把都不踩：逐枚过一遍宽度与底边账。
    geometry = builder.page_geometry(hand)
    assert [row["page"] for row in geometry] == [1, 2, 3, 4]
    for row in geometry:
        if row["no_glyphs"]:
            continue
        assert row["widest_visual_line"] <= row["usable_width"], row
        assert row["lowest_painted_row"] <= int(row["canvas"][1] * 0.92), row


# ==================== ④ 语料零变化：落点把手 ====================


def test_the_builder_refuses_to_land_inside_the_corpus_or_the_data_dirs():
    """判据③：这份件一旦进 ``documents/**`` 就打穿 P-17 哨兵与全部历史窗口可比性。"""
    for relpath in ("documents/r599-scan-demo.pdf", "data/r599/x.pdf", "chroma_db/r599/y.pdf"):
        with pytest.raises(SystemExit) as caught:
            builder.refuse_forbidden_targets(REPO_ROOT / relpath)
        assert "铁规" in str(caught.value)
    builder.refuse_forbidden_targets(FIXTURE)  # 在册落点必须放行（不抛即通过）


def test_the_fixture_never_got_copied_into_the_corpus():
    """同一格的可复查版：今天盘上语料目录里不该有这枚件（也不该有它的任何副本）。"""
    for relpath in ("documents", "data"):
        root = REPO_ROOT / relpath
        if not root.is_dir():
            continue
        strays = sorted(p.name for p in root.rglob("*") if "r599" in p.name.lower())
        assert strays == [], f"{relpath}/ 里出现了 R599 的件：{strays}"


# ==================== ⑤ 扫描页判定：正面 4 页 + 对照 1 页（不碰引擎） ====================


@pytest.fixture(scope="module")
def control_page(tmp_path_factory):
    """一枚「有文本层 + 同时挂着位图」的对照页：判据① 的 AND 左半边必须为假。"""
    hand = builder.samples()
    path = tmp_path_factory.mktemp("r599_control") / "r599-control.pdf"
    hand.build_pdf(path, [{"text_lines": hand.CONTROL_TEXT_LINES, "image": hand.blank_image()}])
    return path


def test_the_registered_judgement_calls_every_fixture_page_scanned(control_page):
    """逐页账的左半边，默认腿就钉：4 页全判扫描页，对照页一枚都不许被误判。

    🔴 ``enable_ocr=False``：这一格要量的是**判定**，不是识别。判定用真件量一次（零 OCR 成本），
    识别质量那一腿留给 ``R599_REAL_OCR=1`` 那枚开关腿——常驻钉不许靠打 OCR 做常绿（判据⑤）。
    """
    report = loader.extract_pdf(str(FIXTURE), enable_ocr=False)
    assert report.page_count == PINNED_PAGE_COUNT
    assert report.scanned_pages == PINNED_PAGE_COUNT
    assert report.scanned_page_numbers == tuple(range(1, PINNED_PAGE_COUNT + 1))
    for page in report.pages:
        assert page.is_scanned is True, f"第{page.page_number}页没被判成扫描页"
        assert page.text_layer_chars == 0
        assert page.has_image_object is True
        assert page.source == loader.PAGE_SOURCE_OCR_DEGRADED
        assert "关闭了 OCR 通道" in page.note
    assert report.ocr_attempted is False
    assert report.ocr_available is True

    control = loader.extract_pdf(str(control_page), enable_ocr=False)
    first = control.pages[0]
    assert first.has_image_object is True, "对照页也得挂位图，否则 AND 没测到右半边"
    assert first.text_layer_chars >= loader.SCANNED_PAGE_TEXT_CHARS, (
        f"对照页文本层只有 {first.text_layer_chars} 字，低于阈值 {loader.SCANNED_PAGE_TEXT_CHARS}，"
        "这枚对照件已经不能证明『有字就不 OCR』"
    )
    assert first.is_scanned is False, "把扫描页判定改宽（只看有没有图）= 本钉当场红"
    assert first.source == loader.PAGE_SOURCE_TEXT_LAYER
    assert control.ocr_attempted is False


# ==================== ⑥ R301 那一格：消费方在不在（静态复述，不 import chat） ====================


def test_the_upload_receipt_still_consumes_the_pdf_extraction_report():
    """判据④ 的取证口径：只复述在册链路，不造第二套上报，所以这里读源码文本而不是调它。"""
    source = CHAT_SOURCE.read_text(encoding="utf-8")
    assert "def _pdf_extraction_cell(" in source, "回执里那格被人删了 = R301 交回的读数退回无人消费"
    assert "pdf_extraction = _pdf_extraction_cell(extraction)" in source
    assert source.count("pdf_extraction=pdf_extraction") == 4, (
        "R301 明写四条返回路径带同一格同一形状，少一支就变成"
        "「客户端靠键不见了去猜」——那是 R49 已否掉的写法"
    )
    assert '"scanned_pages": report.scanned_pages' in source
    assert '"scanned_page_numbers": list(report.scanned_page_numbers)' in source


def test_the_screen_still_draws_the_scanned_page_phrase():
    """客户屏上那句「扫描页 N 页」的另一端：前端确实在读回执里的 ``pdf_extraction``。"""
    source = DOC_PANEL_SOURCE.read_text(encoding="utf-8")
    assert "res.data.pdf_extraction" in source, "回执那一格没人读 = 判据④ 继续挂着"
    assert "扫描页" in source


# ==================== 🔴 非常驻腿：真打在册 OCR 通道 ====================


@pytest.mark.skipif(
    not REAL_OCR,
    reason="真打 rapidocr 不是常驻腿：R599_REAL_OCR=1 才跑（CPU 单页 0.9-4.1 s，见件首）",
)
def test_the_registered_ocr_channel_reads_the_fixture_page_by_page():
    """判据②：走在册 OCR 腿真跑一次，逐页交回「是不是扫描页 / 出没出字 / 哪几页没跑成」。

    形状是量出来的，不是设计出来的：4 页全判扫描页，前 3 页出字（``ocr``），
    第 4 页**有图无字**⇒ 必须是 ``ocr-empty`` 且写明「图像页 OCR 未检出文字」，
    不许混进 ``ocr-degraded``（那两句在检索面是两件事）。耗时只打印不钉（R269 口径）。
    """
    report = loader.extract_pdf(str(FIXTURE))
    assert report.ocr_available is True, "引擎不可用时这一格量不到，必须说出来而不是假绿"
    assert report.ocr_attempted is True
    assert report.ocr_dpi == loader.ocr_channel.DEFAULT_OCR_DPI == 200
    assert report.degradation_notes == () or report.degradation_notes == []
    assert report.degradation_sentence == ""
    assert dict(report.source_counts) == {
        loader.PAGE_SOURCE_OCR: 3,
        loader.PAGE_SOURCE_OCR_EMPTY: 1,
    }, report.source_counts

    by_page = {page.page_number: page for page in report.pages}
    assert all(page.is_scanned for page in by_page.values())
    for number in (1, 2, 3):
        page = by_page[number]
        assert page.source == loader.PAGE_SOURCE_OCR, f"第{number}页没出字：{page.note}"
        assert page.text.strip(), f"第{number}页正文为空"
        assert page.ocr_elapsed_ms > 0
        assert tuple(page.raster_size) == EXPECTED_RASTER_AT_DEFAULT_DPI
    fourth = by_page[4]
    assert fourth.source == loader.PAGE_SOURCE_OCR_EMPTY
    assert fourth.note == "图像页 OCR 未检出文字"
    assert fourth.text == ""
    assert fourth.ocr_elapsed_ms > 0

    # 像素里到底有什么字：整页正文过一遍数字尺（判据① 的第三把尺，只有真打才量得到这一格）。
    assert not re.search(r"[0-9]", report.text), f"OCR 从像素里读出了数字：{report.text[:80]!r}"
    assert not (set(report.text) & set(builder.CJK_NUMERAL_CHARS)), "OCR 读出了中文数字"
    for token in ("内部管理制度宣贯会纪要", "机房出入管理办法", "库房巡检记录填写说明"):
        assert token in report.text, f"源句标题没被读回来：{token}"
    assert "档案管理遵循谁形成" in report.text
    assert "严禁单独作业" in report.text
    assert "不得事后补记或者代签" in report.text


@pytest.mark.skipif(
    not REAL_OCR,
    reason="页数触顶那一形同样要真打引擎才能拿到降级账：R599_REAL_OCR=1 才跑",
)
def test_pages_beyond_the_cap_come_back_degraded_not_empty(control_page):
    """判据②「哪几页没跑成」：``DOCUMENT_OCR_MAX_PAGES=1`` 时第 2-4 页必须是降级并点名原因。"""
    from app.rag import ocr as ocr_channel

    previous = os.environ.get(ocr_channel.OCR_MAX_PAGES_ENV)
    os.environ[ocr_channel.OCR_MAX_PAGES_ENV] = "1"
    try:
        assert ocr_channel.resolve_max_pages(None) == 1
        report = loader.extract_pdf(str(FIXTURE))
    finally:
        if previous is None:
            os.environ.pop(ocr_channel.OCR_MAX_PAGES_ENV, None)
        else:
            os.environ[ocr_channel.OCR_MAX_PAGES_ENV] = previous
    assert by_source(report, loader.PAGE_SOURCE_OCR) == [1]
    assert by_source(report, loader.PAGE_SOURCE_OCR_DEGRADED) == [2, 3, 4]
    for number in (2, 3, 4):
        page = next(item for item in report.pages if item.page_number == number)
        assert "超出单次 OCR 页数上限" in page.note, page.note
        assert page.text == ""
    assert "第2页" in report.degradation_sentence


def by_source(report, source: str) -> list[int]:
    return [page.page_number for page in report.pages if page.source == source]
