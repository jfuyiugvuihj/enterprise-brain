"""
Day 10: Export Agent — PDF 报告 + Excel 导出
优化 #20 导出Excel
"""
import os
import uuid
from datetime import datetime
from fpdf import FPDF
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from app.common.logger import logger

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

# ==================== PDF 报告 ====================

class PDFReport(FPDF):
    """中文 PDF 报告：封面 → 正文 → 图表 → 建议 → 尾页"""

    def __init__(self, title: str = "企业分析报告"):
        super().__init__()
        self.report_title = title
        # 中文字体（运行时检测）
        self._font_name = self._detect_font()
        if self._font_name:
            self.add_font(self._font_name, "", self._font_path, uni=True)
            self.add_font(self._font_name, "B", self._font_path, uni=True)

    def _detect_font(self) -> str | None:
        """探测系统上的中文字体"""
        candidates = [
            ("C:/Windows/Fonts/msyh.ttc", "SimSun"),
            ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
            ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
            ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WenQuanYi"),
            ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ]
        for path, name in candidates:
            if os.path.exists(path):
                self._font_path = path
                return name
        self._font_path = None
        return None

    def _font(self, bold: bool = False):
        """切换字体"""
        if self._font_name:
            style = "B" if bold else ""
            self.set_font(self._font_name, style, size=12)

    def cover(self, subtitle: str = "", date: str = ""):
        """封面"""
        self.add_page()
        self.ln(60)
        if self._font_name:
            self.set_font(self._font_name, "B", size=28)
        else:
            self.set_font("Helvetica", "B", size=28)
        self.cell(0, 16, self.report_title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self._font()
        self.set_font_size(14)
        self.cell(0, 10, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font_size(11)
        self.cell(0, 8, date or datetime.now().strftime("%Y-%m-%d"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        self.set_font_size(10)
        self.cell(0, 8, "企业智脑 · 私有化 AI 分析平台", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "本报告由 AI 自动生成，仅供参考", align="C", new_x="LMARGIN", new_y="NEXT")

    def heading(self, text: str, level: int = 1):
        """标题"""
        self.ln(4)
        sizes = {1: 18, 2: 14, 3: 12}
        self._font(bold=True)
        self.set_font_size(sizes.get(level, 12))
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self._font()
        self.set_font_size(11)

    def paragraph(self, text: str):
        """正文段落"""
        self._font()
        self.set_font_size(11)
        self.multi_cell(0, 7, text)
        self.ln(2)

    def chart_image(self, path: str, caption: str = "", w: int = 160):
        """插入图表"""
        if os.path.exists(path):
            self.ln(4)
            self.image(path, x=None, w=w)
            self.ln(2)
            self._font()
            self.set_font_size(10)
            self.cell(0, 6, caption, align="C", new_x="LMARGIN", new_y="NEXT")
        else:
            self.paragraph(f"[图表缺失: {path}]")

    def footer(self):
        """页脚"""
        self.set_y(-20)
        self._font()
        self.set_font_size(9)
        self.cell(0, 10, f'第 {self.page_no()} 页 — {self.report_title}', align="C")


def generate_pdf_report(title: str, sections: list[dict], chart_paths: list[str] = None) -> str:
    """
    生成 PDF 报告

    sections: [{"type":"heading","content":"标题","level":1},
               {"type":"text","content":"段落内容"},
               {"type":"chart","path":"...","caption":"图表说明"}]
    """
    pdf = PDFReport(title)

    pdf.cover(date=datetime.now().strftime("%Y年%m月%d日"))

    for sec in sections:
        t = sec.get("type", "text")

        if t == "heading":
            pdf.heading(sec["content"], sec.get("level", 2))
        elif t == "text":
            pdf.paragraph(sec["content"])
        elif t == "chart":
            pdf.chart_image(sec["path"], sec.get("caption", ""))

    # 尾页
    pdf.add_page()
    pdf.ln(80)
    pdf.heading("— 报告结束 —", level=1)
    pdf.paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.paragraph("本报告由企业智脑 AI 自动生成，数据来源为企业已上传的经营数据。")

    filename = f"report_{uuid.uuid4().hex[:10]}.pdf"
    path = os.path.join(EXPORT_DIR, filename)
    pdf.output(path)
    logger.info(f"PDF 报告已生成: {filename}")
    return path

# ==================== Excel 导出 (#20) ====================

THIN_BORDER = Border(
    left=Side(style="thin", color="d0d5dd"),
    right=Side(style="thin", color="d0d5dd"),
    top=Side(style="thin", color="d0d5dd"),
    bottom=Side(style="thin", color="d0d5dd"),
)

HEADER_FILL = PatternFill(start_color="1a4f8a", end_color="1a4f8a", fill_type="solid")
HEADER_FONT = Font(name="Microsoft YaHei", size=11, bold=True, color="ffffff")
BODY_FONT = Font(name="Microsoft YaHei", size=10)
TITLE_FONT = Font(name="Microsoft YaHei", size=14, bold=True, color="1a4f8a")


def export_to_excel(sheets: dict[str, list[dict]], title: str = "数据分析结果") -> str:
    """
    多 Sheet 导出 Excel
    sheets: {"Sheet名": [{"列1": 值, "列2": 值}, ...]}
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # 删除默认 sheet

    for sheet_name, rows in sheets.items():
        if not rows:
            continue

        ws = wb.create_sheet(title=sheet_name[:31])  # Excel sheet 名最长 31 字符

        # 标题行
        columns = list(rows[0].keys())
        ws.append([sheet_name])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns))
        title_cell = ws.cell(row=1, column=1)
        title_cell.font = TITLE_FONT
        title_cell.alignment = Alignment(horizontal="center")
        ws.row_dimensions[1].height = 30

        # 表头
        ws.append(columns)
        for ci, col_name in enumerate(columns, 1):
            cell = ws.cell(row=2, column=ci)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER
        ws.row_dimensions[2].height = 24

        # 数据行
        for ri, row in enumerate(rows, 3):
            for ci, col_name in enumerate(columns, 1):
                cell = ws.cell(row=ri, column=ci)
                cell.value = row.get(col_name, "")
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
                cell.alignment = Alignment(horizontal="center" if _is_numeric(row.get(col_name)) else "left")

        # 自动列宽
        for ci, col_name in enumerate(columns, 1):
            max_len = max(len(str(col_name)), 8)
            for row in rows[:100]:  # 前 100 行采样
                val_len = len(str(row.get(col_name, "")))
                max_len = max(max_len, val_len)
            ws.column_dimensions[get_column_letter(ci)].width = min(max_len + 4, 40)

    filename = f"export_{uuid.uuid4().hex[:10]}.xlsx"
    path = os.path.join(EXPORT_DIR, filename)
    wb.save(path)
    logger.info(f"Excel 已导出: {filename}")
    return path


def _is_numeric(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)
