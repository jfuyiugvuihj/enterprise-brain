# -*- coding: utf-8 -*-
"""R540 样本发生器：V2 #13/#14/#15 三条通道的输入侧，全部现场造、一律落仓外 tmp。

为什么手搓而不借 reportlab/FiTz：`pyproject.toml` 不在本单写域，而扫描件要的只是
「一页 = 一张位图 + 零文本层」，40 行 PDF 语法比多引一枚依赖便宜（同
`tests/fixtures/r298_build_fixtures.py` 的取舍，本件不复用那个目录 —— 它是禁域，一字节不动）。

三条通道各要的形状（判据逐格）：
  #13 扫描件：≥4 页**只有像素、零文本层**的 PDF，含中英混排页与故意低质量页；
  #13 对照：**带文本层**的 PDF（每页另挂一张位图），钉「有文本层的页一个字都不许再走 OCR」；
  #14 表格：一份带框线表格的 PDF + 一份带真表格的 DOCX；
  #15 电子表格：一份 .xlsx（中文列名 / 空值 / 日期 / 合并单元格 / 全空列 / 尾随空行）
      与一份 .csv（同形，逗号分隔，utf-8）。

产物是**样本**，不是凭据：凭据在 `scripts/r540_readout.py` 交回的读数里。
"""
from __future__ import annotations

import io
import zlib
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

#: A4 页面几何（pt）与栅格原生分辨率：位图 1240x1754，与 R298 fixture 同档。
PAGE_SIZE_PT = (595, 842)
RASTER_DPI = 150
RASTER_SIZE = (1240, 1754)

_CJK_FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
)

#: #13 扫描页里真的印进像素的句子（判据③ 要认的就是这些字，不是桩话）。
SCAN_PAGES: dict[int, list[str]] = {
    1: [
        "季度回款分析说明",
        "第一条 华东大区三季度回款同比增长百分之七。",
        "第二条 单笔金额超过 5000 元需总经理审批。",
    ],
    2: [
        "Q3 revenue grew 12.5% in East China 华东大区。",
        "Contact 张敏 zhangmin@example.com 13800001234。",
    ],
    3: [
        "库存周转天数 45 天",
        "呆滞物料占比 3.2%",
    ],
}

#: 第 3 页故意造低质量：小字 + 高斯模糊 + 低对比 + 噪点，用来验"降级/空"那一族形状。
LOW_QUALITY_PAGE = 3
LOW_QUALITY_STYLE = {"size": 26, "blur": 6.0, "gray": 0.45, "noise": 26}

#: 第 4 页只画几何框、一个字都没有 —— 判据② 的 ``ocr-empty`` 形状。
NO_TEXT_PAGE = 4

#: #13 对照件：这一页有真文本层，同时还挂一张位图（AND 判定的右半边为真、左半边为假）。
CONTROL_TEXT_LINES = [
    "Quarterly budget review notes for the East China region.",
    "Travel reimbursement policy for engineers, section two.",
    "Server room access requires a badge and a companion.",
]

#: #14 PDF 表格内容（框线由矢量线画出来，pdfplumber 靠它找表）。
PDF_TABLE_HEADER = ("region", "orders", "amount", "owner")
PDF_TABLE_ROWS = (
    ("East", "128", "45600", "zhang"),
    ("South", "77", "23100", "chen"),
    ("North", "15", "8900", "li"),
)

#: #14 DOCX 表格内容（中文表头 + 单元格里的中文，docx 走 python-docx 的表格对象）。
DOCX_TABLE_HEADER = ("大区", "订单数", "回款金额", "负责人")
DOCX_TABLE_ROWS = (
    ("华东", "128", "45600", "张敏"),
    ("华南", "77", "23100", "陈默"),
    ("华北", "15", "8900", "李雷"),
)
DOCX_PROSE = [
    "第三季度经营回顾：华东大区回款领先，华北订单量同比下滑。",
    "下表为三大区回款明细，数据口径与财务系统一致。",
]

#: #15 电子表格的在册形状（列名/空值/日期/合并/全空列/尾随空行）。
SHEET_COLUMNS = ("订单号", "客户名称", "下单日期", "数量", "折扣率", "备注", "附件")
SHEET_ROWS = (
    ("SO-1001", "杭州云栖科技有限公司", "2026-01-05", 120, 0.15, "月结"),
    ("SO-1002", "苏州工业园区某某厂", "2026-01-06", 77, None, ""),
    ("SO-1003", None, "2026-01-07", None, 0.2, "现结"),
    ("SO-1004", "上海临港装备有限公司", "2026-01-08", 15, 0.0, None),
)
CSV_BODY = (
    ["SO-1001", "杭州云栖科技有限公司", "2026-01-05", "120", "0.15", "月结"],
    ["SO-1002", "苏州工业园区某某厂", "2026-01-06", "77", "", ""],
    ["SO-1003", "", "2026-01-07", "", "0.2", "现结"],
    ["SO-1004", "上海临港装备有限公司", "2026-01-08", "15", "0", ""],
)


def _cjk_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _CJK_FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("找不到 CJK 字体，无法造扫描件：" + "、".join(_CJK_FONT_CANDIDATES))


def render_text_image(
    lines: Sequence[str],
    *,
    size: int = 44,
    blur: float = 0.0,
    gray: float | None = None,
    noise: int = 0,
    seed: int = 20260103,
) -> Image.Image:
    """把若干行文字印成一张 A4 比例的**位图**（扫描件的样子：整页一张图，零文本层）。

    ``gray`` / ``blur`` / ``noise`` 三枚旋钮只给低质量页用：模糊越大、灰得越平、噪点越响。
    """
    canvas = Image.new("L", RASTER_SIZE, 255)
    draw = ImageDraw.Draw(canvas)
    font = _cjk_font(size)
    y = int(RASTER_SIZE[1] * 0.12)
    for line in lines:
        draw.text((int(RASTER_SIZE[0] * 0.08), y), line, font=font, fill=10)
        y += int(size * 2.1)
    if blur:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    array = np.asarray(canvas, dtype="float32")
    if gray is not None:
        array = 255.0 - (255.0 - array) * gray
    if noise:
        rng = np.random.default_rng(seed)
        array = array + rng.normal(0.0, float(noise), size=array.shape)
    return Image.fromarray(np.clip(array, 0, 255).astype("uint8"), mode="L")


def blank_image() -> Image.Image:
    """一张「有图无字」的底图：判据② 的 ``ocr-empty`` 靠它，判据① 的 AND 也靠它。"""
    canvas = Image.new("L", RASTER_SIZE, 246)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([160, 520, 1060, 1240], outline=0, width=8)
    draw.line([160, 520, 1060, 1240], fill=0, width=6)
    return canvas


# ==================== 手写最小 PDF（1.4 语法：可选位图 + 可选文本层 + 可选矢量线） ====================


def _escape_literal(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _page_ops(page: dict) -> bytes:
    width, height = PAGE_SIZE_PT
    ops: list[str] = []
    if page.get("image") is not None:
        ops.append(f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q")
    ops.extend(page.get("vector_ops", []))
    y = height - 90
    for line in page.get("text_lines", []):
        size = int(page.get("font_size", 11))
        ops.append(f"BT /F1 {size} Tf 1 0 0 1 56 {y} Tm ({_escape_literal(line)}) Tj ET")
        y -= 18
    for place in page.get("text_at", []):
        x, ty, text, size = place
        ops.append(f"BT /F1 {int(size)} Tf 1 0 0 1 {x} {ty} Tm ({_escape_literal(text)}) Tj ET")
    return "\n".join(ops).encode("latin-1")


def build_pdf(path: Path, pages: Sequence[dict]) -> dict:
    """写一份只用到 1.4 语法的 PDF；每页可选一张位图、若干行文本层、若干条矢量线。"""
    catalog_id, pages_id, font_id = 1, 2, 3
    next_id = 4
    plan: list[tuple[int, int, int | None]] = []
    for page in pages:
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        image_id = next_id if page.get("image") is not None else None
        if image_id is not None:
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

    for (page_id, content_id, image_id), page in zip(plan, pages):
        start(page_id)
        resources = f"<< /Font << /F1 {font_id} 0 R >>"
        if image_id is not None:
            resources += f" /XObject << /Im0 {image_id} 0 R >>"
        resources += " >>"
        emit(
            f"<< /Type /Page /Parent {pages_id} 0 R "
            f"/MediaBox [0 0 {PAGE_SIZE_PT[0]} {PAGE_SIZE_PT[1]}] "
            f"/Resources {resources} /Contents {content_id} 0 R >>\n"
        )
        finish()
        payload = _page_ops(page)
        start(content_id)
        emit(f"<< /Length {len(payload)} >>\nstream\n")
        emit(payload.decode("latin-1"))
        emit("\nendstream\n")
        finish()
        if image_id is not None:
            image: Image.Image = page["image"]
            packed = zlib.compress(image.tobytes(), 9)
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
    return {"path": str(path), "pages": len(plan), "bytes": len(body.getvalue())}


def build_scan_pdf(path: Path) -> dict:
    """#13 主样本：4 页只有像素、零文本层；第 3 页故意低质量，第 4 页有图无字。"""
    pages: list[dict] = []
    for number in range(1, NO_TEXT_PAGE + 1):
        if number == NO_TEXT_PAGE:
            pages.append({"image": blank_image()})
            continue
        style = LOW_QUALITY_STYLE if number == LOW_QUALITY_PAGE else {"size": 44}
        pages.append({"image": render_text_image(SCAN_PAGES[number], **style)})
    return build_pdf(path, pages)


def build_mixed_pdf(path: Path) -> dict:
    """#13 混合件：第 1 页纯像素、第 2 页文本层 + 位图、第 3 页既无文本层也无图像对象。

    判据④ 说「来源逐页记，不许整件二选一」，这一枚就是它的三面尺：同一份文件里
    `ocr` / `text-layer` / `blank` 三形必须同时成立，且只有第 1 页允许走到 OCR 通道。
    """
    return build_pdf(
        path,
        [
            {"image": render_text_image(SCAN_PAGES[1])},
            {"image": render_text_image(["decorative backing strip"]), "text_lines": CONTROL_TEXT_LINES},
            {},
        ],
    )


def build_control_pdf(path: Path) -> dict:
    """#13 对照样本：两页**带文本层**，每页同时挂一张位图。

    这是判据④ 那半句的凭据面：文本层字符数远过阈值 ⇒ AND 的左半边不成立 ⇒ 有图也不许 OCR。
    """
    image = render_text_image(["decorative scan-like backing strip"])
    return build_pdf(path, [{"image": image, "text_lines": CONTROL_TEXT_LINES}] * 2)


def _grid_ops(xs: Sequence[int], ys: Sequence[int]) -> list[str]:
    ops = ["0.6 w"]
    for y in ys:
        ops.append(f"{xs[0]} {y} m {xs[-1]} {y} l S")
    for x in xs:
        ops.append(f"{x} {ys[-1]} m {x} {ys[0]} l S")
    return ops


def build_table_pdf(path: Path) -> dict:
    """#14 PDF 样本：一页正文 + 一页 4 列 4 行带框线表格（矢量线 + 单元格文字）。"""
    xs = [56, 176, 296, 416, 536]
    ys = [720, 692, 664, 636, 608]
    ops = _grid_ops(xs, ys)
    cells: list[tuple[float, float, str, int]] = []
    for column, text in enumerate(PDF_TABLE_HEADER):
        cells.append((xs[column] + 6, ys[0] - 16, text, 10))
    for row, values in enumerate(PDF_TABLE_ROWS, start=1):
        for column, text in enumerate(values):
            cells.append((xs[column] + 6, ys[row] - 16, text, 10))
    table_page = {"vector_ops": ops, "text_at": cells}
    prose_page = {"text_lines": ["Appendix B: regional collection detail below.", *CONTROL_TEXT_LINES]}
    report = build_pdf(path, [prose_page, table_page])
    report["table_bbox"] = [xs[0], ys[-1], xs[-1], ys[0]]
    return report


def build_table_docx(path: Path) -> dict:
    """#14 DOCX 样本：两段正文 + 一枚真 Word 表格（python-docx 的 table 对象）。"""
    from docx import Document

    document = Document()
    for line in DOCX_PROSE:
        document.add_paragraph(line)
    table = document.add_table(rows=len(DOCX_TABLE_ROWS) + 1, cols=len(DOCX_TABLE_HEADER))
    table.style = "Table Grid"
    for column, text in enumerate(DOCX_TABLE_HEADER):
        table.cell(0, column).text = text
    for row, values in enumerate(DOCX_TABLE_ROWS, start=1):
        for column, text in enumerate(values):
            table.cell(row, column).text = text
    document.add_paragraph("以上数据用于本季度经营回顾。")
    document.save(str(path))
    return {"path": str(path), "pages": 0, "bytes": path.stat().st_size}


def build_xlsx(path: Path) -> dict:
    """#15 xlsx 样本：中文列名 + 空值 + 真日期 + 合并单元格 + 全空列 + 尾随空行。"""
    import datetime

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "一月销售"
    sheet.append(list(SHEET_COLUMNS))
    for values in SHEET_ROWS:
        row = list(values)
        if row[2]:
            year, month, day = (int(part) for part in row[2].split("-"))
            row[2] = datetime.date(year, month, day)
        sheet.append(row)
    sheet.merge_cells("F2:F3")  # 备注列覆盖两行：左上角有值，被覆盖那格不是"本来就是空"
    sheet.append([None] * len(SHEET_COLUMNS))  # 尾随全 None 行：openpyxl 的维度根本不数它
    sheet.append([""] * len(SHEET_COLUMNS))  # 尾随全空串行：这一枚才在网格里占一行，必须被丢掉
    second = workbook.create_sheet("汇总")
    second.append(["大区", "回款"])
    second.append(["华东", 45600])
    second.append(["华南", 23100])
    workbook.save(str(path))
    return {"path": str(path), "sheets": [sheet.title, second.title], "bytes": path.stat().st_size}


#: 空白那两把尺的专用件：递宽的数据行（尾随空列）+ 中间一枚空行。
#: 中文写法不在这里——本件的价值就在于「空白到底怎么算」，所以故意留三种空白。
PAD_CSV_TEXT = (
    "订单号,客户名称,下单日期,数量,折扣率,备注,附件\n"
    "SO-2001,杭州云栖科技有限公司,2026-02-01,9,0.1,月结,,,,\n"
    "\n"
    "SO-2002,苏州工业园区某某厂,2026-02-02,3,,\n"
)


def build_pad_csv(path: Path) -> dict:
    """#15 空白件：表头 7 列、第一枚数据行递宽到 10 列、中间一枚空行。

    三种空白各管一把尺：只有表头有字的那一列**不该被丢**（列名本身就是可检索的事实），
    连表头都没有值的尾随列**该丢**，整行空的**该在进网格之前丢掉**——三把尺在
    `SheetReport` 里是三枚不同的计数，混了就是一句假话。
    """
    path.write_bytes(PAD_CSV_TEXT.encode("utf-8"))
    return {"path": str(path), "bytes": path.stat().st_size}


def build_csv(path: Path) -> dict:
    """#15 csv 样本：utf-8 逗号分隔，中文列名、空值、日期以字符串在位。"""
    import csv as csv_module

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv_module.writer(handle)
        writer.writerow(list(SHEET_COLUMNS))
        for row in CSV_BODY:
            writer.writerow(row)
    return {"path": str(path), "bytes": path.stat().st_size}


def build_all(target_dir: Path) -> dict:
    """一次造齐三条通道要的六种样本，返回路径账（键名与读数件的 ``--case`` 同名）。"""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    return {
        "scan_pdf": build_scan_pdf(target_dir / "r540_scan.pdf"),
        "control_pdf": build_control_pdf(target_dir / "r540_control.pdf"),
        "table_pdf": build_table_pdf(target_dir / "r540_table.pdf"),
        "table_docx": build_table_docx(target_dir / "r540_table.docx"),
        "xlsx": build_xlsx(target_dir / "r540_sales.xlsx"),
        "csv": build_csv(target_dir / "r540_sales.csv"),
        "pad_csv": build_pad_csv(target_dir / "r540_pad.csv"),
        "mixed_pdf": build_mixed_pdf(target_dir / "r540_mixed.pdf"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="R540 样本发生器（只写仓外目录）")
    parser.add_argument("--out", required=True, help="样本落盘目录（必须在仓库之外）")
    args = parser.parse_args(argv)
    out = Path(args.out).expanduser().resolve()
    repo = Path(__file__).resolve().parents[1]
    if repo == out or repo in out.parents:
        raise SystemExit(f"R540 样本一律落仓外，拒绝写入 {out}")
    print(json.dumps(build_all(out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())