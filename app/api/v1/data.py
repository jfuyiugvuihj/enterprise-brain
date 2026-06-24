"""
Day 11: Data API — Excel 画像 / 图表生成 / 报表导出
"""
import os
from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from app.tools.excel import load_excel, profile_dataframe
from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
from app.tools.visualize import gantt_chart, mindmap
from app.tools.export import generate_pdf_report, export_to_excel
from app.common.logger import logger

router = APIRouter()
DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== Excel 上传 + 画像 ====================

@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    """上传 Excel/CSV → 解析 → 返回数据画像"""
    file_path = os.path.join(DATA_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    df = load_excel(file_path)
    profile = profile_dataframe(df)

    return {
        "filename": file.filename,
        "profile": profile
    }

# ==================== 图表生成 ====================

class ChartRequest(BaseModel):
    type: str                          # bar / line / pie / radar / gantt / mindmap
    title: str = ""
    labels: list[str] | None = None    # bar/pie/line x轴
    values: list[float] | None = None  # bar/pie 值
    datasets: dict[str, list[float]] | None = None  # line/radar 多系列
    categories: list[str] | None = None   # radar 维度
    tasks: list[dict] | None = None       # gantt 任务
    root: str | None = None               # mindmap 中心
    branches: dict[str, list[str]] | None = None  # mindmap 分支


@router.post("/chart")
async def generate_chart(req: ChartRequest):
    """根据参数生成图表，返回图片路径"""
    try:
        if req.type == "bar":
            path = bar_chart(req.labels, req.values, title=req.title)
        elif req.type == "line":
            path = line_chart(req.labels, req.datasets, title=req.title)
        elif req.type == "pie":
            path = pie_chart(req.labels, req.values, title=req.title)
        elif req.type == "radar":
            path = radar_chart(req.categories, req.datasets, title=req.title)
        elif req.type == "gantt":
            path = gantt_chart(req.tasks, title=req.title)
        elif req.type == "mindmap":
            path = mindmap(req.root, req.branches, title=req.title)
        else:
            return {"error": f"不支持的图表类型: {req.type}", "path": None}

        # 转成相对 URL
        url = f"/static/charts/{os.path.basename(path)}" if path else None
        return {"path": url, "error": None}
    except Exception as e:
        logger.error(f"图表生成失败: {e}")
        return {"error": str(e), "path": None}

# ==================== 报告导出 ====================

class ExportRequest(BaseModel):
    format: str = "pdf"                # pdf / excel
    title: str = ""
    sections: list[dict] | None = None  # pdf: [{type, content}]
    sheets: dict[str, list[dict]] | None = None  # excel: {"Sheet1": [{col:val}]}


@router.post("/export")
async def export_report(req: ExportRequest):
    """生成 PDF 或 Excel 报告，返回下载链接"""
    try:
        if req.format == "pdf":
            path = generate_pdf_report(
                title=req.title,
                sections=req.sections or []
            )
            url = f"/static/exports/{os.path.basename(path)}"
        elif req.format == "excel":
            path = export_to_excel(
                title=req.title,
                sheets=req.sheets or {}
            )
            url = f"/static/exports/{os.path.basename(path)}"
        else:
            return {"error": f"不支持格式: {req.format}", "path": None}

        return {"path": url, "error": None}
    except Exception as e:
        logger.error(f"导出失败: {e}")
        return {"error": str(e), "path": None}
