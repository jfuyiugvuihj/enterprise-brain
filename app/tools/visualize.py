
"""
Day 10: 可视化 Skills — 思维导图 + 甘特图
"""
import os
import uuid
import json
import plotly.express as px
import plotly.figure_factory as ff
import plotly.io as pio
from app.common.logger import logger

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== 思维导图 (Graphviz) ====================

def mindmap(root: str, branches: dict[str, list[str]],
            title: str = "思维导图") -> str:
    """
    生成思维导图 PNG。
    root: 中心主题
    branches: {"分支1": ["子节点A", "子节点B"], "分支2": [...]}
    """
    try:
        import graphviz
    except ImportError:
        raise ImportError("请安装 graphviz: pip install graphviz")

    dot = graphviz.Digraph(title, format="png")
    dot.attr(rankdir="LR", bgcolor="white")
    dot.attr("node", shape="box", style="rounded,filled",
             fillcolor="#e8f4fd", fontname="SimHei",
             fontsize="12", color="#1a4f8a")
    dot.attr("edge", color="#c0c4cc")

    # 根节点
    dot.node("root", root, fillcolor="#1a4f8a", fontcolor="white",
             shape="box", style="rounded,filled")

    for i, (branch, children) in enumerate(branches.items()):
        branch_id = f"b{i}"
        dot.node(branch_id, branch, fillcolor="#d4e9ff")

        dot.edge("root", branch_id)

        for j, child in enumerate(children):
            child_id = f"b{i}_c{j}"
            dot.node(child_id, child)
            dot.edge(branch_id, child_id)

    filename = f"mindmap_{uuid.uuid4().hex[:10]}"
    path = os.path.join(OUTPUT_DIR, filename)
    dot.render(path, cleanup=True)
    logger.info(f"思维导图已生成: {filename}.png")
    return f"{path}.png"

# ==================== 甘特图 (Plotly) ====================

def gantt_chart(tasks: list[dict], title: str = "项目甘特图") -> str:
    """
    生成甘特图 HTML。

    tasks: [
        {"name": "需求分析", "start": "2026-01-01", "end": "2026-01-05", "label": "张三"},
        {"name": "开发",     "start": "2026-01-06", "end": "2026-01-20", "label": "李四"},
    ]
    """
    if not tasks:
        raise ValueError("至少需要一个任务")

    df_data = []
    for i, t in enumerate(tasks):
        df_data.append(dict(
            Task=t.get("label", f"任务{i}"),
            Start=t["start"],
            Finish=t["end"],
            Resource=t.get("name", f"任务{i}"),
        ))

    colors = {
        t["name"]: px.colors.qualitative.Plotly[i % len(px.colors.qualitative.Plotly)]
        for i, t in enumerate(tasks)
    }

    fig = ff.create_gantt(
        df_data,
        colors=colors,
        index_col="Resource",
        show_colorbar=True,
        group_tasks=True,
        title=title,
    )

    fig.update_layout(
        xaxis_title="",
        font=dict(family="SimHei, Microsoft YaHei, sans-serif", size=12),
        title_font_size=16,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    filename = f"gantt_{uuid.uuid4().hex[:10]}.html"
    path = os.path.join(OUTPUT_DIR, filename)
    fig.write_html(path)
    logger.info(f"甘特图已生成: {filename}")
    return path

# ==================== 批量生成 ====================

def generate_all_charts(chart_specs: list[dict]) -> list[dict]:
    """
    批量生成图表，返回 [{type, path, title}]。
    供 Orchestrator 调用，串行执行。

    chart_specs: [{"type":"bar","labels":[...],"values":[...]}, ...]
    """
    from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart

    results = []
    for spec in chart_specs:
        try:
            t = spec["type"]
            title = spec.get("title", "")

            if t == "bar":
                path = bar_chart(spec["labels"], spec["values"], title=title,
                                 horizontal=spec.get("horizontal", False))
            elif t == "line":
                path = line_chart(spec["labels"], spec["datasets"], title=title)
            elif t == "pie":
                path = pie_chart(spec["labels"], spec["values"], title=title)
            elif t == "radar":
                path = radar_chart(spec["categories"], spec["datasets"], title=title)
            elif t == "gantt":
                path = gantt_chart(spec["tasks"], title=title)
            elif t == "mindmap":
                path = mindmap(spec["root"], spec["branches"], title=title)
            else:
                results.append({"type": t, "error": f"不支持的图表类型: {t}", "path": None})
                continue

            results.append({"type": t, "title": title, "path": path, "error": None})
        except Exception as e:
            logger.error(f"图表生成失败 [{spec.get('type')}]: {e}")
            results.append({"type": spec.get("type", "?"), "error": str(e), "path": None})

    return results
