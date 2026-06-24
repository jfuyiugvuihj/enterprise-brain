"""
LangChain Tools — 封装企业智脑全部能力，供 ReAct Agent 自主调用
"""
import os
import json
import re
from langchain_core.tools import tool
from app.common.logger import logger


def _answer_query(df, query: str, num_cols: list[str], txt_cols: list[str]) -> list[str]:
    """用 pandas 计算查询结果，返回简洁的分析文本"""
    import pandas as pd
    results = []

    q_lower = query.lower()
    first_txt_col = txt_cols[0] if txt_cols else ""
    first_num_col = num_cols[0] if num_cols else ""

    # "哪个/谁最XX" → 排名第一
    m = re.search(r"(哪个|谁|哪家|哪).*?(最高|最低|最多|最少|最大|最小)", query)
    if m and txt_cols and num_cols:
        col = num_cols[0]
        # 尝试从 query 中找列名
        for nc in num_cols:
            if nc in query:
                col = nc
                break
        direction = m.group(2)
        if "低" in direction or "少" in direction or "小" in direction:
            row = df.loc[df[col].idxmin()]
        else:
            row = df.loc[df[col].idxmax()]
        name_val = str(row[first_txt_col]) if first_txt_col else ""
        results.append(f"🎯 {direction}: {name_val} — {col}={row[col]}")

    # "排名/排序" → top N
    if any(kw in q_lower for kw in ["排名", "排序", "前", "top", "降序", "升序"]):
        sort_col = None
        for nc in num_cols:
            if nc in query:
                sort_col = nc
                break
        if not sort_col and "利润" in query:
            for nc in num_cols:
                if "利润" in nc:
                    sort_col = nc
                    break
        if not sort_col:
            sort_col = first_num_col or num_cols[0]
        top_n = 10
        m = re.search(r"前\s*(\d+)", query)
        if m:
            top_n = int(m.group(1))
        sorted_df = df.sort_values(sort_col, ascending=False).head(top_n)
        lines = [f"📊 按 {sort_col} 排名前{top_n}:"]
        for _, r in sorted_df.iterrows():
            name = str(r[first_txt_col]) if first_txt_col else ""
            vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
            lines.append(f"  {name}: {vals}")
        results.append("\n".join(lines))

    # "统计/汇总/平均/合计" → describe
    if any(kw in q_lower for kw in ["统计", "汇总", "平均", "合计", "总计", "概括", "概览"]):
        if num_cols:
            desc = df[num_cols].describe().to_dict()
            lines = [f"📈 数值统计 ({len(num_cols)}个指标):"]
            for stat in ["mean", "min", "max", "sum"]:
                stat_name = {"mean": "均值", "min": "最小", "max": "最大", "sum": "合计"}
                stat_line = ", ".join(f"{c}: {desc[c][stat]:.1f}" if stat in desc.get(c, {}) else f"{c}: N/A" for c in num_cols[:5])
                lines.append(f"  {stat_name[stat]}: {stat_line}")
            results.append("\n".join(lines))

    # "对比/比较" → groupby
    if any(kw in q_lower for kw in ["对比", "比较", "分组", "按区域", "按类型"]):
        group_col = None
        for tc in txt_cols:
            if tc in query:
                group_col = tc
                break
        if not group_col:
            for tc in txt_cols:
                n_unique = df[tc].nunique()
                if 2 <= n_unique <= 20:
                    group_col = tc
                    break
        if group_col and num_cols:
            agg = df.groupby(group_col)[num_cols[:3]].sum()
            lines = [f"📋 按 {group_col} 分组汇总:"]
            for idx, row in agg.iterrows():
                vals = ", ".join(f"{c}={v:.1f}" for c, v in row.items())
                lines.append(f"  {idx}: {vals}")
            results.append("\n".join(lines))

    # 兜底：返回基本统计
    if not results and num_cols:
        sorted_df = df.sort_values(num_cols[0], ascending=False).head(10)
        lines = [f"📊 数据预览 (按{num_cols[0]}降序):"]
        for _, r in sorted_df.iterrows():
            name = str(r[first_txt_col]) if first_txt_col else ""
            vals = ", ".join(f"{c}={r[c]}" for c in num_cols[:3])
            lines.append(f"  {name}: {vals}")
        results.append("\n".join(lines))

    return results

# ==================== Doc Tool ====================

# 全局单例，避免每次搜索都重建 pipeline（BM25索引/CrossEncoder/Embedding）
_search_pipeline = None


def _get_pipeline():
    global _search_pipeline
    if _search_pipeline is None:
        from app.rag.retrieval_pipeline import RetrievalPipeline
        _search_pipeline = RetrievalPipeline()
    return _search_pipeline


@tool
def search_docs(query: str) -> str:
    """
    搜索公司内部文档知识库。用于查找：公司制度、报销流程、请假规定、产品规格、
    技术架构、客户案例、定价策略、安全规范、操作手册等所有文档类信息。
    如果第一次搜索返回不够，可以换个关键词再搜。
    """
    pipeline = _get_pipeline()
    docs, rewrites = pipeline.search(query, top_k=5)

    if not docs:
        return f"未找到与'{query}'相关的文档信息。建议尝试以下改写角度的关键词：{', '.join(rewrites[:3])}"

    result_parts = []
    for i, d in enumerate(docs, 1):
        source = d.get("source", "unknown")
        score = d.get("_score", "?")
        content = d["content"][:500]
        result_parts.append(f"[{i}] 来源:{source} 相关度:{score:.2f}\n{content}")

    return "\n\n---\n\n".join(result_parts)


# ==================== Data Tool ====================

@tool
def analyze_data(query: str) -> str:
    """
    分析企业经营数据。用于所有数据相关问题：统计数字、计算指标、对比业绩、
    排名、增长率、利润、营收等。调用此工具会自动检测已上传的 Excel/CSV 文件并进行分析。
    如果用户提到具体数字指标，优先使用此工具而不是 search_docs。
    """
    import pandas as pd
    from app.tools.excel import load_excel, profile_dataframe

    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    os.makedirs(data_dir, exist_ok=True)

    files = [f for f in os.listdir(data_dir) if f.endswith((".xlsx", ".xls", ".csv"))]
    if not files:
        return "暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。"

    parts = []
    for fname in files:
        try:
            df = load_excel(os.path.join(data_dir, fname))
            profile = profile_dataframe(df)
            cols_info = [f"{c['name']}({c['dtype']})" if isinstance(c, dict) else str(c) for c in profile["columns"]]
            parts.append(f"📁 {fname}: {profile['rows']}行 × {len(cols_info)}列 — 列: {', '.join(cols_info)}")

            # 根据 query 计算具体答案
            numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
            text_cols = df.select_dtypes(include=["object"]).columns.tolist()

            try:
                ai_parts = _answer_query(df, query, numeric_cols, text_cols)
                parts.extend(ai_parts)
            except Exception:
                pass

            # 返回前 15 行数据用于图表
            try:
                sample = df.head(15).to_dict(orient="records")
                parts.append("--- 数据样本(前15行) ---")
                parts.append(json.dumps(sample, ensure_ascii=False, default=str))
            except Exception:
                pass
        except Exception as e:
            parts.append(f"📁 {fname}: 读取失败 - {e}")

    result = "\n".join(parts)
    return f"数据分析结果:\n{result}\n\n用户查询: {query}\n图表生成时直接使用上述数据样本中的字段名和数值。"


# ==================== Chart Tool ====================

@tool
def generate_chart(chart_type: str, labels: list, values: list,
                   title: str = "数据分析图表") -> str:
    """
    生成数据可视化图表。chart_type可选：bar(柱状图)、line(折线图)、pie(饼图)、radar(雷达图)、
    gantt(甘特图)、mindmap(思维导图)。
    labels是X轴标签列表，values是数值列表。
    返回生成的图表文件路径。
    """
    from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
    from app.tools.visualize import gantt_chart, mindmap as _mindmap

    chart_funcs = {
        "bar": lambda: bar_chart(labels, values, title=title),
        "line": lambda: line_chart(labels, {"数据": values}, title=title),
        "pie": lambda: pie_chart(labels, values, title=title),
        "radar": lambda: radar_chart(labels, {"数据": values}, title=title),
    }

    if chart_type in chart_funcs:
        path = chart_funcs[chart_type]()
    else:
        return f"不支持的图表类型: {chart_type}，可选: bar/line/pie/radar/gantt/mindmap"

    url = f"/static/charts/{os.path.basename(path)}"
    return f"图表已生成: ![{title}]({url})"


# ==================== Export Tool ====================

@tool
def export_report(report_title: str, sections_json: str,
                  include_charts: str = "") -> str:
    """
    导出分析报告为 PDF 文件。
    sections_json: JSON 数组，每项 {"type":"heading"|"text","content":"..."}
    include_charts: 图表路径列表（可选）
    """
    from app.tools.export import generate_pdf_report

    try:
        sections = json.loads(sections_json)
        path = generate_pdf_report(title=report_title, sections=sections)

        url = f"/static/exports/{os.path.basename(path)}"
        return f"报告已生成: [📋 下载报告]({url})"
    except Exception as e:
        return f"报告生成失败: {e}"


# ==================== 工具列表 ====================

ALL_TOOLS = [search_docs, analyze_data, generate_chart, export_report]
