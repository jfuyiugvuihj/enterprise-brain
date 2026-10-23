"""
Day 10: Export Agent — PDF 报告 + Excel 导出
优化 #20 导出Excel
"""
import os
import uuid
import re
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import MethodReturnValue
from fpdf.fonts import FontFace
from PIL import Image
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from app.common.logger import logger

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

# ==================== PDF 报告 ====================

class PDFReport(FPDF):
    """中文 PDF 报告：封面、可自动分页的正文与图表。"""

    def __init__(self, title: str = "企业分析报告"):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(16, 25, 16)
        self.alias_nb_pages()
        self.report_title = title
        # 中文字体（运行时检测）
        self._font_name = self._detect_font()
        if self._font_name:
            self.add_font(self._font_name, "", self._font_path)
            self.add_font(self._font_name, "B", self._font_path)

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
        self.set_font(self._font_name or "Helvetica", "B" if bold else "", size=12)

    def _text_height(self, text: str, line_height: float) -> float:
        return self.multi_cell(
            self.epw, line_height, text, dry_run=True, output=MethodReturnValue.HEIGHT,
            new_x="LMARGIN", new_y="NEXT",
        )

    def header(self):
        self._font(bold=True)
        self.set_font_size(9)
        self.set_text_color(20, 62, 94)
        self.set_xy(self.l_margin, 12)
        self.cell(self.epw, 6, "企业智脑  /  经营分析", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(22, 155, 158)
        self.line(self.l_margin, 21, self.w - self.r_margin, 21)
        self.set_y(26)
        self.set_text_color(35, 45, 57)

    def management_summary(self, section: dict):
        self._font(bold=True)
        self.set_font_size(23)
        self.set_text_color(20, 62, 94)
        self.multi_cell(0, 11, self.report_title, new_x="LMARGIN", new_y="NEXT")
        self._font()
        self.set_font_size(10)
        self.set_text_color(95, 111, 129)
        self.multi_cell(0, 6, f"报告期间：{section.get('period') or '以来源数据为准'}\n生成日期：{datetime.now():%Y-%m-%d} · 仅限当前授权范围", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        cards = section.get("cards") or []
        for offset in range(0, len(cards), 3):
            batch = cards[offset:offset + 3]
            width = (self.epw - 8) / 3
            top = self.get_y()
            if top + 32 > self.page_break_trigger:
                self.add_page()
                top = self.get_y()
            for index, card in enumerate(batch):
                x = self.l_margin + index * (width + 4)
                self.set_fill_color(240, 246, 250)
                self.rect(x, top, width, 31, style="F")
                self.set_fill_color(22, 155, 158)
                self.rect(x, top, width, 1.1, style="F")
                self._font()
                self.set_font_size(9)
                self.set_text_color(95, 111, 129)
                self.set_xy(x + 3, top + 4)
                self.cell(width - 6, 5, str(card.get("label") or ""))
                self._font(bold=True)
                self.set_font_size(19)
                value = str(card.get("value") or "—")
                while self.get_string_width(value) > width - 6 and self.font_size_pt > 8:
                    self.set_font_size(self.font_size_pt - 1)
                self.set_text_color(20, 62, 94)
                self.set_xy(x + 3, top + 11)
                self.cell(width - 6, 8, value)
                self._font()
                self.set_font_size(8)
                self.set_text_color(95, 111, 129)
                self.set_xy(x + 3, top + 22)
                self.multi_cell(width - 6, 4, str(card.get("hint") or ""), new_x="LMARGIN", new_y="NEXT")
            self.set_y(top + 35)
        self.set_text_color(35, 45, 57)

    def callout(self, text: str):
        self._font()
        self.set_font_size(10.5)
        height = self.multi_cell(self.epw - 8, 6, text, dry_run=True, output=MethodReturnValue.HEIGHT) + 8
        if self.get_y() + height > self.page_break_trigger:
            self.add_page()
        top = self.get_y()
        self.set_fill_color(240, 246, 250)
        self.rect(self.l_margin, top, self.epw, height, style="F")
        self.set_fill_color(22, 155, 158)
        self.rect(self.l_margin, top, 1, height, style="F")
        self.set_xy(self.l_margin + 4, top + 4)
        self.multi_cell(self.epw - 8, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.set_y(top + height + 3)

    def data_table(self, section: dict):
        headers = section.get("headers") or []
        if not headers:
            return
        self._font()
        self.set_font_size(section.get("font_size", 10))
        self.set_fill_color(255, 255, 255)
        with self.table(line_height=section.get("line_height", 5.5), padding=section.get("padding", 1.2),
                        col_widths=section.get("col_widths"), borders_layout="HORIZONTAL_LINES",
                        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(20, 62, 94)),
                        cell_fill_color=(244, 247, 250), cell_fill_mode="ROWS",
                        text_align=section.get("align") or ["LEFT"] + ["RIGHT"] * (len(headers) - 1)) as table:
            for cells in [headers, *(section.get("rows") or [])]:
                row = table.row()
                for value in cells:
                    row.cell(str(value))
        self.ln(3)

    def cover(self, subtitle: str = "", date: str = ""):
        """封面"""
        self.add_page()
        self.ln(60)
        if self._font_name:
            self.set_font(self._font_name, "B", size=28)
        else:
            self.set_font("Helvetica", "B", size=28)
        self.multi_cell(0, 16, self.report_title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)
        self._font()
        self.set_font_size(14)
        self.multi_cell(0, 10, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font_size(11)
        self.cell(0, 8, date or datetime.now().strftime("%Y-%m-%d"), align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        self.set_font_size(10)
        self.cell(0, 8, "企业智脑 · 私有化 AI 分析平台", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "本报告由 AI 自动生成，仅供参考", align="C", new_x="LMARGIN", new_y="NEXT")

    def heading(self, text: str, level: int = 1):
        """标题"""
        sizes = {1: 18, 2: 14, 3: 12}
        self._font(bold=True)
        self.set_font_size(sizes.get(level, 12))
        self.set_text_color(20, 62, 94)
        # Keep a heading with at least the first body line, rather than stranding it.
        line_height = 7 if level == 3 else 10
        needed = 3 + self._text_height(text, line_height) + 2 + 7
        if self.get_y() + needed > self.page_break_trigger:
            self.add_page()
        self.ln(2 if level == 3 else 3)
        self.multi_cell(0, line_height, text, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self._font()
        self.set_font_size(11)
        self.set_text_color(35, 45, 57)

    def paragraph(self, text: str, size: float = 11, line_height: float = 7):
        """正文段落"""
        text = re.sub(r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)", r"\1", text)
        self._font()
        self.set_font_size(size)
        self.set_x(self.l_margin)
        self.multi_cell(0, line_height, text, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def chart_image(self, path: str, caption: str = "", w: int = 160):
        """插入图表"""
        if os.path.exists(path):
            width, height, caption_height = self._chart_geometry(path, caption, w)
            if self.get_y() + height + caption_height + 6 > self.page_break_trigger:
                self.add_page()
            self._font()
            self.set_font_size(10)
            self.ln(4)
            self.image(path, x=self.l_margin + (self.epw - width) / 2,
                       y=self.get_y(), w=width, h=height)
            self.set_y(self.get_y() + height + 2)
            if caption:
                self.multi_cell(0, 6, caption, align="C", new_x="LMARGIN", new_y="NEXT")
        else:
            raise FileNotFoundError("报告图表文件缺失，无法生成完整报告。")

    def _chart_geometry(self, path: str, caption: str, w: int = 160):
        self._font()
        self.set_font_size(10)
        caption_height = self._text_height(caption, 6) if caption else 0
        with Image.open(path) as image:
            aspect = image.height / image.width
        width = min(float(w), self.epw)
        maximum_height = self.page_break_trigger - max(self.t_margin, 26) - caption_height - 8
        width = min(width, max(10, maximum_height) / aspect)
        return width, width * aspect, caption_height

    def footer(self):
        """页脚"""
        self.set_y(-20)
        self._font()
        self.set_font_size(9)
        label = f"{self.report_title}  |  {self.page_no()} / {{nb}}"
        while self.get_string_width(label) > self.epw - 4:
            label = label[:-4] + "..."
        self.cell(0, 10, label, align="C")


def generate_pdf_report(title: str, sections: list[dict], chart_paths: list[str] = None) -> str:
    """
    生成 PDF 报告

    sections: [{"type":"heading","content":"标题","level":1},
               {"type":"text","content":"段落内容"},
               {"type":"chart","path":"...","caption":"图表说明"}]
    """
    pdf = PDFReport(title)

    if any(section.get("type") == "summary" for section in sections):
        pdf.add_page()
    else:
        pdf.cover(date=datetime.now().strftime("%Y年%m月%d日"))
        pdf.add_page()
    embedded = set()

    def embed_chart(path: str, caption: str = ""):
        key = os.path.normcase(os.path.realpath(path))
        if key in embedded:
            return
        caption = caption.strip() or f"图{len(embedded) + 1}：{title}"
        pdf.chart_image(path, caption=caption)
        embedded.add(key)

    last_section_type = None
    for index, sec in enumerate(sections):
        t = sec.get("type", "text")

        if t == "heading":
            following = sections[index + 1] if index + 1 < len(sections) else {}
            if following.get("type") == "chart" and os.path.exists(following.get("path", "")):
                pdf._font(bold=True)
                level = sec.get("level", 2)
                pdf.set_font_size({1: 18, 2: 14, 3: 12}.get(level, 12))
                line_height = 7 if level == 3 else 10
                heading_height = 3 + pdf._text_height(sec["content"], line_height) + 2
                _, chart_height, caption_height = pdf._chart_geometry(following["path"], following.get("caption", ""))
                if pdf.get_y() + heading_height + chart_height + caption_height + 6 > pdf.page_break_trigger:
                    pdf.add_page()
            pdf.heading(sec["content"], sec.get("level", 2))
        elif t == "text":
            pdf.paragraph(sec["content"], sec.get("font_size", 11), sec.get("line_height", 7))
        elif t == "chart":
            embed_chart(sec["path"], sec.get("caption", ""))
        elif t == "chart_slot":
            # 没有可嵌入图表时也要交代原因，避免模板留下一个空章节；
            # 有图表时 _export_report 会先用真实图件替换该占位项。
            pdf.paragraph(sec.get("content", "本轮未生成图表。"), 10, 5.3)
        elif t == "summary":
            pdf.management_summary(sec)
        elif t == "callout":
            pdf.callout(sec["content"])
        elif t == "table":
            pdf.data_table(sec)
        elif t == "page_break":
            # A no-chart report uses ``chart_slot`` as an explanatory paragraph.
            # Do not preserve the chart template's hard page break in that case;
            # letting the following detail heading flow naturally avoids a mostly
            # empty first page. Real chart sections still keep the deliberate break.
            if last_section_type != "chart_slot":
                pdf.add_page()
        last_section_type = t

    #: 调用方交回的本轮图表件路径：给进来就真嵌（10-07 现读两枚报告 PDF 里 `/Subtype /Image`
    #: 均 0 枚——这一枚参数一直是死的，模型交回的 sections 永远不会有 type=="chart" 那一格，
    #: 因为它不知道图在容器里的路径，工具给它的是 URL）。缺文件的写法沿用 chart_image 那句。
    remaining = [str(item) for item in (chart_paths or []) if str(item).strip()
                 and os.path.normcase(os.path.realpath(str(item))) not in embedded]
    if remaining:
        pdf.heading("本轮生成的图表", level=2)
        for item in remaining:
            embed_chart(item)

    business_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(title)).strip(" .")[:60] or "企业分析报告"
    filename = f"{business_name}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}.pdf"
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
