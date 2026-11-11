"""R298 fixture 发生器：手写最小 PDF，把"有没有文本层""有没有图像对象"两维分开控制。

为什么手搓而不借 reportlab/FiTz：`pyproject.toml` 本单不许动（判据写域），而造 fixture
要的只是"一页 = 文本层 op + /Subtype /Image 位图"，40 行 PDF 语法比多引一枚依赖便宜。
判据① 的 AND 条件必须有"有图无字""有字有图""有字无图""无字无图"四种页才能钉得住，
现成语料里凑不齐这四种。

重跑（只在需要改内容时）：`python tests/fixtures/r298_build_fixtures.py`。
需要一枚 CJK 字体（Windows: msyh.ttc / simhei.ttf）；产物是提交进仓库的 .pdf，
测试运行期不读字体，所以 Linux CI 上没有字体也不会红。
"""
from __future__ import annotations

import io
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

PAGE_SIZE_PT = (595, 842)  # A4
RASTER_DPI = 150  # 位图原生分辨率：595pt x 842pt @150dpi = 1240 x 1754 px

_CJK_FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
)

SCANNED_PAGE_LINES = {
    1: [
        "员工报销制度",
        "第一条 差旅费须在出行后三十日内提交财务部。",
        "第二条 单笔金额超过 5000 元需总经理审批。",
    ],
    2: [
        "信息部运维值班表",
        "夜班时段 22:00 至次日 06:00。",
        "紧急联系人 林晓 138 0000 1234",
    ],
    3: [
        "第三章 附则",
        "本制度自 2026 年 3 月 1 日起施行。",
    ],
}

TEXT_ONLY_LINES = [
    "Quarterly budget review notes",
    "Travel reimbursement policy for engineers, section two.",
    "Server room access requires a badge and a companion.",
]

#: 混合件第 1 页专属：整份文件里只出现一次，判据④ 的"同一句话只该出现一遍"拿它当尺。
COVER_TEXT_LINES = [
    "Policy index 2026: reimbursement windows, badge rules, retention terms.",
    "Section one lists the approval chain for travel and the finance cut-off day.",
]

FIGURE_PAGE_LINES = [
    "Appendix A: measured latency distribution per gateway node.",
    "The figure below is decorative; the text layer above is complete.",
]


def _cjk_font(size: int):
    for candidate in _CJK_FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(
        "找不到 CJK 字体，无法重新生成 R298 fixture（已提交的 .pdf 仍可直接使用）："
        + "、".join(_CJK_FONT_CANDIDATES)
    )


def render_text_image(lines: list[str], *, start_y: int = 140, size: int = 44) -> Image.Image:
    """把若干行中文渲染成一张 A4 比例的灰度位图（扫描件的样子：整页一张图）。"""
    font = _cjk_font(size)
    width = int(PAGE_SIZE_PT[0] * RASTER_DPI / 72)
    height = int(PAGE_SIZE_PT[1] * RASTER_DPI / 72)
    canvas = Image.new("L", (width, height), 255)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)
    y = start_y
    for line in lines:
        draw.text((int(width * 0.08), y), line, font=font, fill=10)
        y += int(size * 1.9)
    return canvas


def _blank_gray_image() -> Image.Image:
    width = int(PAGE_SIZE_PT[0] * RASTER_DPI / 72)
    height = int(PAGE_SIZE_PT[1] * RASTER_DPI / 72)
    return Image.new("L", (width, height), 245)  # 一张没有字的底图（水印/贴图）


def _escape_literal(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(page: dict) -> bytes:
    width, height = PAGE_SIZE_PT
    ops: list[str] = []
    if page.get("image") is not None:
        ops.append(f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q")
    y = height - 90
    for line in page.get("text_lines", []):
        ops.append(f"BT /F1 11 Tf 1 0 0 1 56 {y} Tm ({_escape_literal(line)}) Tj ET")
        y -= 18
    return "\n".join(ops).encode("latin-1")


def build_pdf(path: Path, pages: list[dict]) -> None:
    """写一份只用到 1.4 语法的 PDF：每页可选一张位图 + 若干行 Helvetica 文本层。"""
    catalog_id, pages_id, font_id = 1, 2, 3
    next_id = 4
    plan: list[tuple[int, int, int | None]] = []
    for page in pages:
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        image_id = None
        if page.get("image") is not None:
            image_id = next_id
            next_id += 1
        plan.append((page_id, content_id, image_id))
    last_id = next_id - 1

    body = io.BytesIO()
    offsets: dict[int, int] = {}

    def emit(text: str) -> None:
        body.write(text.encode("latin-1"))

    def start(object_id: int) -> None:
        offsets[object_id] = len(body.getvalue())
        emit(f"{object_id} 0 obj\n")

    def finish() -> None:
        emit("endobj\n")

    emit("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    start(catalog_id)
    emit(f"<< /Type /Catalog /Pages {pages_id} 0 R >>\n")
    finish()

    kids = " ".join(f"{page_id} 0 R" for page_id, _c, _i in plan)
    start(pages_id)
    emit(f"<< /Type /Pages /Kids [{kids}] /Count {len(plan)} >>\n")
    finish()

    start(font_id)
    emit("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\n")
    finish()

    for index, ((page_id, content_id, image_id), page) in enumerate(zip(plan, pages)):
        start(page_id)
        resources = f"<< /Font << /F1 {font_id} 0 R >>"
        if image_id is not None:
            resources += " /XObject << /Im0 " + str(image_id) + " 0 R >>"
        resources += " >>"
        emit(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_SIZE_PT[0]} {PAGE_SIZE_PT[1]}] "
            f"/Resources {resources} /Contents {content_id} 0 R >>\n"
        )
        finish()

        payload = _content_stream(page)
        start(content_id)
        emit(f"<< /Length {len(payload)} >>\nstream\n")
        emit(payload.decode("latin-1"))
        emit("\nendstream\n")
        finish()

        if image_id is not None:
            image: Image.Image = page["image"]
            raw = image.tobytes()
            packed = zlib.compress(raw, 9)
            start(image_id)
            emit(
                f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height} "
                f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(packed)} >>\nstream\n"
            )
            body.write(packed)
            emit("\nendstream\n")
            finish()

    xref_offset = len(body.getvalue())
    emit(f"xref\n0 {last_id + 1}\n")
    emit("0000000000 65535 f \n")
    for object_id in range(1, last_id + 1):
        emit(f"{offsets[object_id]:010d} 00000 n \n")
    emit(f"trailer\n<< /Size {last_id + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n")

    path.write_bytes(body.getvalue())


def figure_only_image() -> Image.Image:
    """一张"有图无字"的底图：用来钉判据① 的 AND —— 有图像对象但文本层够长，不该 OCR。"""
    from PIL import ImageDraw

    canvas = _blank_gray_image()
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([120, 400, 900, 1000], outline=0, width=6)
    draw.line([120, 400, 900, 1000], fill=0, width=4)
    return canvas


def build_all(target_dir: Path) -> list[Path]:
    written: list[Path] = []

    scanned = target_dir / "r298_scanned_pages.pdf"
    build_pdf(
        scanned,
        [
            {"image": render_text_image(SCANNED_PAGE_LINES[number])}
            for number in sorted(SCANNED_PAGE_LINES)
        ],
    )
    written.append(scanned)

    text_only = target_dir / "r298_text_only.pdf"
    build_pdf(text_only, [{"text_lines": TEXT_ONLY_LINES}] * 2)
    written.append(text_only)

    blank = target_dir / "r298_blank.pdf"
    build_pdf(blank, [{}])
    written.append(blank)

    # 混合件：一页一形，判据①④ 全在这一份上验。
    mixed = target_dir / "r298_mixed_pages.pdf"
    build_pdf(
        mixed,
        [
            {"text_lines": COVER_TEXT_LINES},                              # 1 纯文本层
            {"image": render_text_image(SCANNED_PAGE_LINES[2])},           # 2 纯图（扫描页）
            {"text_lines": FIGURE_PAGE_LINES, "image": figure_only_image()},  # 3 文本层 + 插图
            {                                                              # 4 扫描页 + 垃圾隐形层
                "image": render_text_image(SCANNED_PAGE_LINES[3]),
                "text_lines": ["3"],
            },
            {"image": _blank_gray_image()},                                # 5 有图无字（OCR 空）
            {},                                                            # 6 空白页
        ],
    )
    written.append(mixed)
    return written


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for item in build_all(here):
        print(item.name, item.stat().st_size, "bytes")