"""
Day 9: Chart Skill — 图表生成 + 标签防重叠 + 企业配色
优化 #7 图表标签重叠, #8 企业配色, #24 无显示器后端
"""
import os
import math
import uuid
import matplotlib
matplotlib.use("Agg")  # 无 GUI 后端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.ticker import MaxNLocator
from app.common.logger import logger

# ==================== 中文字体配置 ====================

def _setup_chinese_font():
    """自动探测可用的中文字体"""
    preferred = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                 "WenQuanYi Micro Hei", "PingFang SC", "STHeiti"]
    available = {f.name for f in fm.fontManager.ttflist}

    for name in preferred:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            logger.info(f"使用中文字体: {name}")
            break
    else:
        logger.warning("未找到中文字体，图表中文将无法正常显示")

    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 150

_setup_chinese_font()

# ==================== 企业配色 ====================

PRIMARY = "#1a4f8a"       # 深蓝（主色）
ACCENTS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
#: 一组数就是一根色。以前柱状图按「每一根」发配色板，六个月的报销额画成六道彩虹
#: （10-07 现读那张图），客户第一眼以为是六个系列。板子留给多系列与饼图。
ACCENT_SINGLE = ACCENTS[0]
BG_LIGHT = "#f8fafc"

plt.rcParams.update({
    "axes.facecolor": BG_LIGHT,
    "figure.facecolor": "white",
    "axes.edgecolor": "#e2e8f0",
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.color": "#e2e8f0",
})

# ==================== 输出目录 ====================

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "charts")
os.makedirs(STATIC_DIR, exist_ok=True)

def _save_and_return(fig) -> str:
    """保存图表并返回文件路径"""
    filename = f"{uuid.uuid4().hex[:12]}.png"
    path = os.path.join(STATIC_DIR, filename)
    fig.savefig(path, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    logger.info(f"图表已保存: {filename}")
    return path

# ==================== 标签防重叠工具 (优化 #7) ====================

def _smart_labels(ax, labels, chart_type="bar", max_rotate=10, max_suggest=20):
    """
    智能标签处理：
    - ≤10 个标签：正常显示
    - 11~20 个标签：旋转 45° + 调整对齐
    - >20 个标签：建议换图表类型 + 间隔显示
    """
    n = len(labels)

    if n <= max_rotate:
        return  # 正常显示

    elif n <= max_suggest:
        # 旋转标签
        for label in ax.get_xticklabels():
            label.set_rotation(45)
            label.set_ha("right")
            label.set_fontsize(max(7, 11 - n * 0.15))
        logger.info(f"标签已旋转 45°（{n} 个标签）")

    else:
        # 太多标签：间隔显示
        step = max(2, n // 20)
        visible = [i for i in range(n) if i % step == 0]
        for i, label in enumerate(ax.get_xticklabels()):
            if i not in visible:
                label.set_visible(False)
            else:
                label.set_rotation(60)
                label.set_ha("right")
                label.set_fontsize(7)
        logger.warning(f"标签过多 ({n} 个)，已间隔显示 + 旋转 60°。建议改用折线图或横向柱状图。")

    # 减少刻度数量
    if hasattr(ax, "xaxis"):
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=min(15, n)))


def _label_overlap_suggestion(n: int, chart_type: str) -> str | None:
    """标签过多时的建议"""
    if n > 20 and chart_type == "bar":
        return f"当前 {n} 个柱状标签已自动旋转并间隔显示。建议改用横向柱状图(`barh`)或折线图(`line`)以获得更好效果。"
    return None


def _bar_value_label(value: float) -> str:
    display = 0 if value == 0 else value
    return f"{display:,.1f}" if display % 1 else f"{display:,.0f}"

# ==================== 图表函数 ====================

def bar_chart(labels: list[str], values: list[float],
              title: str = "", xlabel: str = "", ylabel: str = "",
              horizontal: bool = False) -> str:
    """
    柱状图（自动处理标签重叠）
    - horizontal=False: 垂直柱状图
    - horizontal=True: 横向柱状图（标签多时推荐）
    """
    if not labels or len(labels) != len(values):
        raise ValueError("柱状图需要非空且数量一致的分类和数值")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("柱状图数值必须有效，缺失值需先说明或处理")

    # Explicit category positions preserve every label, including repeated names.
    # Wrap long names rather than silently dropping categories at a tick locator.
    wrapped = ["\n".join(line[start:start + 10]
                        for line in str(label).split("\n")
                        for start in range(0, max(1, len(line)), 10))
               for label in labels]
    rows = max(label.count("\n") + 1 for label in wrapped)
    dense_labels = not horizontal and len(labels) > 10 and rows > 1
    if dense_labels:
        horizontal = True
        xlabel, ylabel = ylabel, xlabel
        size = (10, max(6, len(labels) * (rows * 14 / 72 * 1.12 + 0.06) + 1.4))
    elif horizontal:
        size = (9, max(5.5, len(labels) * (0.3 + rows * 0.2)))
    else:
        longest = max(len(line) for label in wrapped for line in label.split("\n"))
        size = (max(8, len(labels) * (longest * 10 / 72 + 0.25)),
                5.5 + max(0, rows - 1) * 0.25)
    fig, ax = plt.subplots(figsize=size)
    colors = ACCENT_SINGLE
    positions = range(len(labels))
    lower, upper = min(0, min(values)), max(0, max(values))
    padding = (upper - lower) * 0.15 or 1
    value_limits = (lower - padding if lower < 0 else 0,
                    upper + padding if upper > 0 else (0 if lower < 0 else 1))
    category_limits = (-1.5, 1.5) if len(labels) == 1 else (-0.6, len(labels) - 0.4)

    if horizontal:
        bars = ax.barh(positions, values, color=colors, height=0.7)
        ax.set_yticks(list(positions), wrapped, fontsize=14 if dense_labels else 10)
        if dense_labels:
            ax.tick_params(axis='x', labelsize=12)
        ax.set_ylim(*category_limits)
        ax.set_xlim(*value_limits)
        # 数值标注
        for bar, v in zip(bars, values):
            ax.annotate(_bar_value_label(v),
                        (v, bar.get_y() + bar.get_height() / 2),
                        xytext=(-5 if v < 0 else 5, 0), textcoords="offset points",
                        ha="right" if v < 0 else "left", va="center",
                        fontsize=12 if dense_labels else 9, color="#334155")
    else:
        bars = ax.bar(positions, values, color=colors, width=0.65)
        ax.set_xticks(list(positions), wrapped, fontsize=10)
        ax.set_xlim(*category_limits)
        ax.set_ylim(*value_limits)
        # 数值标注（柱顶）
        for bar, v in zip(bars, values):
            ax.annotate(_bar_value_label(v),
                        (bar.get_x() + bar.get_width() / 2, v),
                        xytext=(0, -5 if v < 0 else 5), textcoords="offset points",
                        ha="center", va="top" if v < 0 else "bottom",
                        fontsize=9, color="#334155", fontweight="500")

    ax.set_title(title, fontsize=15, fontweight="700", color=PRIMARY, pad=16)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout(pad=1.4)
    return _save_and_return(fig)


def line_chart(x_labels: list[str], datasets: dict[str, list[float]],
               title: str = "", xlabel: str = "", ylabel: str = "") -> str:
    """折线图（支持多系列）"""
    fig, ax = plt.subplots(figsize=(max(8, len(x_labels) * 0.45), 5.5))

    for i, (name, values) in enumerate(datasets.items()):
        color = ACCENTS[i % len(ACCENTS)]
        ax.plot(x_labels, values, marker="o", label=name, color=color,
                linewidth=2.2, markersize=5, markerfacecolor="white",
                markeredgewidth=2, markeredgecolor=color)

    _smart_labels(ax, x_labels, "line")

    ax.set_title(title, fontsize=15, fontweight="700", color=PRIMARY, pad=16)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.legend(frameon=True, fancybox=True, shadow=True, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    return _save_and_return(fig)


def pie_chart(labels: list[str], values: list[float],
              title: str = "") -> str:
    """饼图（标签过多自动转为柱状图）"""
    if not labels or len(labels) != len(values):
        raise ValueError("饼图需要非空且数量一致的分类和数值")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("饼图数值必须为有限数值，请先处理缺失或无穷值")
    if any(value < 0 for value in values):
        raise ValueError("饼图不支持负值；请使用柱状图展示收支")
    total = sum(values)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("饼图数值总和必须是大于零的有限数值")
    if len(labels) > 10:
        logger.warning(f"饼图标签过多 ({len(labels)})，自动转柱状图")
        return bar_chart(labels, values, title=title, horizontal=True)

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = [ACCENTS[i % len(ACCENTS)] for i in range(len(labels))]
    explode = [0.03] * len(labels)

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=colors, explode=explode,
        startangle=90, pctdistance=0.78,
        textprops={"fontsize": 10}
    )

    for at in autotexts:
        at.set_fontweight("600")
        at.set_color("#1e293b")

    ax.set_title(title, fontsize=15, fontweight="700", color=PRIMARY, pad=20)

    return _save_and_return(fig)


def radar_chart(categories: list[str], datasets: dict[str, list[float]],
                title: str = "") -> str:
    """雷达图（最多 10 个维度）"""
    n = len(categories)
    if n < 3:
        raise ValueError("雷达图至少需要 3 个维度")
    if n > 10:
        raise ValueError(f"雷达图最多 10 个维度，当前 {n} 个。请精简指标。")

    angles = [2 * __import__("math").pi * i / n for i in range(n)]
    angles += angles[:1]  # 闭合

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"projection": "polar"})
    ax.set_theta_offset(__import__("math").pi / 2)
    ax.set_theta_direction(-1)

    for i, (name, values) in enumerate(datasets.items()):
        v = values + values[:1]  # 闭合
        color = ACCENTS[i % len(ACCENTS)]
        ax.fill(angles, v, alpha=0.1, color=color)
        ax.plot(angles, v, "o-", label=name, color=color,
                linewidth=2, markersize=5, markerfacecolor="white")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_yticklabels([])
    ax.set_title(title, fontsize=15, fontweight="700", color=PRIMARY, pad=24, y=1.1)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.set_facecolor(BG_LIGHT)

    return _save_and_return(fig)


def wordcloud_image(text: str, max_words: int = 100) -> str:
    """词云图（jieba 分词 + wordcloud）"""
    from wordcloud import WordCloud
    import jieba

    words = " ".join(jieba.cut(text))
    wc = WordCloud(
        font_path=_get_chinese_font_path(),
        width=800, height=500,
        max_words=max_words,
        background_color="white",
        colormap="Blues",
        collocations=False,
    ).generate(words)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")

    return _save_and_return(fig)


def _get_chinese_font_path() -> str | None:
    """获取中文字体文件路径"""
    for f in fm.fontManager.ttflist:
        if "Microsoft YaHei" in f.name or "SimHei" in f.name:
            return f.fname
    return None
