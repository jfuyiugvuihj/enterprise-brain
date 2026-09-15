"""
LangChain Tools — 封装企业智脑全部能力，供 ReAct Agent 自主调用
"""
import os
import json
import re
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.common.logger import logger
from app.common.permissions import ACTION_ANALYZE, ACTION_EXPORT
from app.agents.evidence import (
    bag_from_config,
    record_artifact,
    record_dataset,
    record_document_hits,
    record_tool_status,
)
from app.trace.spans import start_tool_call


def _get_user_context(user: dict | None = None) -> dict:
    """Build tool context from an explicit caller; missing identity is denied."""
    if not user or not user.get("username"):
        raise PermissionError("authorization_required: agent tool identity is missing")
    from app.common.identity import Principal

    principal = Principal.from_user(user, auth_source="agent")
    if principal.status != "active":
        raise PermissionError("permission_denied: agent tool identity is inactive")
    return {
        "username": principal.username,
        "role": principal.role,
        "department": principal.department,
        "permissions": sorted(principal.permissions),
        "clearance": principal.clearance,
    }


def _tool_principal(config):
    """Resolve the canonical Principal carried by the Agent runtime."""
    conf = (config or {}).get("configurable", {}) or {}
    try:
        from app.common.identity import Principal

        provided = conf.get("principal")
        if isinstance(provided, Principal):
            principal = provided
        elif isinstance(provided, dict):
            principal = Principal.model_validate(provided)
        else:
            principal = Principal.from_user(conf, auth_source="agent")
        if not principal.user_id or not principal.username:
            raise PermissionError("authorization_required: agent tool identity is missing")
        if principal.status != "active":
            raise PermissionError("permission_denied: agent tool identity is inactive")
        return principal
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError(
            "authorization_required: agent tool identity is missing"
        ) from exc


def _tool_context(config) -> dict | None:
    try:
        principal = _tool_principal(config)
        return {
            "username": principal.username,
            "role": principal.role,
            "department": principal.department,
            "permissions": sorted(principal.permissions),
            "clearance": principal.clearance,
        }
    except PermissionError as exc:
        logger.warning("[Tool] %s", exc)
        return None


def _authorization_error() -> str:
    return "未找到：当前请求缺少有效授权主体（error_code=authorization_required）"

def _artifact_principal(config, action: str | None = None) -> object | None:
    try:
        principal = _tool_principal(config)
        if action and action not in principal.permissions:
            raise PermissionError("permission_denied")
        return principal
    except Exception as exc:
        logger.warning("[Tool] artifact creation denied: %s", exc)
        return None


def _artifact_urls(path: str, artifact_type: str, config) -> tuple[str, str] | None:
    artifact = _register_artifact(path, artifact_type, config)
    if artifact is None:
        return None
    return artifact.content_url, artifact.download_url


def _register_artifact(path: str, artifact_type: str, config):
    """Register a generated file and record it as evidence for this execution."""
    principal = _artifact_principal(config)
    if principal is None:
        return None
    from app.storage import artifacts as artifact_storage

    artifact = artifact_storage.register_artifact(
        path,
        artifact_type=artifact_type,
        principal=principal,
    )
    record_artifact(
        bag_from_config(config),
        artifact_id=artifact.artifact_id,
        artifact_type=artifact_type,
        owner_id=artifact.owner_id,
        version_id=artifact.source_version_id or "",
        download_url=artifact.download_url,
        expires_at=artifact.expires_at or "",
    )
    return artifact


def _authorized_dataset_files(config) -> tuple[list[tuple[str, str]], str | None]:
    """Resolve registered datasets after applying the same scope policy as API routes."""
    principal = _artifact_principal(config, ACTION_ANALYZE)
    if principal is None:
        return [], _authorization_error()

    from app.common.policy import authorization_decision
    from app.storage import datasets as dataset_storage

    conf = (config or {}).get("configurable", {}) or {}
    selected_filename = os.path.basename(str(conf.get("data_filename") or "").strip())
    if selected_filename:
        record = dataset_storage.dataset_registry.get_active_by_filename(selected_filename)
        if record is None:
            return [], f"未找到选中的数据文件：{selected_filename}（error_code=resource_not_found）"
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_ANALYZE,
            require_resource_scope=True,
        )
        if not decision.allowed:
            return [], f"暂无可访问的数据文件（error_code={decision.reason_code}）"
        return [(record.filename, record.storage_path)], None

    permitted = []
    for record in dataset_storage.dataset_registry.active_records():
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_ANALYZE,
            require_resource_scope=True,
        )
        if decision.allowed:
            permitted.append((record.filename, record.storage_path))
    return permitted, None


def _record_dataset_evidence(config, filename: str, df) -> None:
    """Attach the real dataset identity behind an analysis result."""
    from app.storage import datasets as dataset_storage

    record = dataset_storage.dataset_registry.get_active_by_filename(filename)
    bag = bag_from_config(config)
    if bag is None:
        return
    record_dataset(
        bag,
        filename=filename,
        dataset_id=getattr(record, "dataset_id", "") if record is not None else "",
        version_id=getattr(record, "version_id", "") if record is not None else "",
        rows=int(getattr(df, "shape", (0, 0))[0]),
        columns=[str(column) for column in getattr(df, "columns", [])],
        department=str(getattr(record, "department", "") or "") if record is not None else "",
    )


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
        # C3: 优先精确匹配列名；多列且无匹配时所有数值列都给出，避免静默选错列
        matched = [nc for nc in num_cols if nc in query]
        if matched:
            cols_use = matched[:1]
        elif len(num_cols) > 1:
            cols_use = num_cols
        else:
            cols_use = [num_cols[0]]
        direction = m.group(2)
        for col in cols_use:
            if "低" in direction or "少" in direction or "小" in direction:
                row = df.loc[df[col].idxmin()]
            else:
                row = df.loc[df[col].idxmax()]
            name_val = str(row[first_txt_col]) if first_txt_col else ""
            results.append(f"🎯 {direction}({col}): {name_val} — {col}={row[col]}")

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
            # describe() has no sum row, so 合计 printed N/A for a frame whose upload
            # profile had already reported that same total correctly.
            totals = {column: float(df[column].sum()) for column in num_cols}
            lines = [f"📈 数值统计 ({len(num_cols)}个指标):"]
            for stat in ["mean", "min", "max", "sum"]:
                stat_name = {"mean": "均值", "min": "最小", "max": "最大", "sum": "合计"}
                parts = []
                for column in num_cols[:5]:
                    value = totals[column] if stat == "sum" else desc.get(column, {}).get(stat)
                    usable = isinstance(value, (int, float)) and value == value
                    parts.append(f"{column}: {value:.1f}" if usable else f"{column}: N/A")
                lines.append(f"  {stat_name[stat]}: " + ", ".join(parts))
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
# threading.Lock 防止并发请求同时初始化（竞态条件导致多个 BM25 索引重复构建）
import threading
_search_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    global _search_pipeline
    if _search_pipeline is None:
        with _pipeline_lock:
            if _search_pipeline is None:  # double-check
                from app.rag.retrieval_pipeline import RetrievalPipeline
                _search_pipeline = RetrievalPipeline()
    return _search_pipeline


def preload_pipeline():
    """启动时预加载 RAG pipeline（BM25索引 + CrossEncoder），避免首个请求等待 10s+"""
    p = _get_pipeline()
    p.preload()


def rebuild_bm25():
    """C1: 文档增删后重建 BM25 索引，新文档免重启即可被关键词检索"""
    if _search_pipeline is not None:
        _search_pipeline.bm25.build_index()
        logger.info("[BM25] 索引已重建")


@tool
def search_docs(query: str, config: RunnableConfig) -> str:
    """
    搜索公司内部文档知识库。用于查找：公司制度、报销流程、请假规定、产品规格、
    技术架构、客户案例、定价策略、安全规范、操作手册等所有文档类信息。
    如果第一次搜索返回不够，可以换个关键词再搜。
    权限：必须从调用上下文取得有效身份，缺少身份时拒绝检索。
    """
    try:
        principal = _tool_principal(config)
    except PermissionError:
        record_tool_status(
            bag_from_config(config), tool="search_docs", status="rejected", error_code="authorization_required"
        )
        return _authorization_error()

    with start_tool_call(config, tool_name="search_docs", arguments={"query": query}) as span:
        pipeline = _get_pipeline()
        try:
            docs, rewrites = pipeline.search_for_principal(
                query,
                principal,
                top_k=5,
            )
        except Exception as exc:
            code = getattr(exc, "code", "retrieval_unavailable")
            logger.warning("[Tool] document retrieval unavailable: %s", exc)
            span.finish("retrieval_unavailable", error_code=code)
            return f"文档检索不可用（error_code={code}）"

        if not docs:
            span.finish("empty", summary={"hit_count": 0, "rewrite_count": len(rewrites or [])})
            return f"未找到与'{query}'相关的文档信息。建议尝试以下改写角度的关键词：{', '.join(rewrites[:3])}"

        record_document_hits(bag_from_config(config), query=query, hits=docs)
        span.finish("completed", summary={"hit_count": len(docs), "rewrite_count": len(rewrites or [])})

    result_parts = []
    for i, d in enumerate(docs, 1):
        source = d.get("source", "unknown")
        raw_score = d.get("_score", "?")
        try:
            score = f"{float(raw_score):.2f}"
        except (TypeError, ValueError):
            score = str(raw_score)
        content = d["content"][:500]
        result_parts.append(f"[{i}] 来源:{source} 相关度:{score}\n{content}")

    return "\n\n---\n\n".join(result_parts)


# ==================== Data Tool ====================

def _analyze_data(query: str, config: RunnableConfig) -> str:
    from app.common.rbac import filter_dataframe_rows
    from app.tools.excel import load_excel, profile_dataframe
    context = _tool_context(config)
    if context is None:
        record_tool_status(
            bag_from_config(config), tool="analyze_data", status="rejected", error_code="authorization_required"
        )
        return "暂无数据：当前请求缺少有效授权主体（error_code=authorization_required）"
    conf = (config or {}).get("configurable", {}) or {}
    role = context["role"]
    dept = context["department"]
    files, dataset_error = _authorized_dataset_files(config)
    if dataset_error:
        return dataset_error
    if not files:
        return "暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。"

    parts = []
    for fname, file_path in files:
        try:
            df = load_excel(file_path)
            df = filter_dataframe_rows(df, role=role, department=dept)
            if df.empty:
                parts.append(f"📧 {fname}: 当前账号没有可见数据行")
                continue
            _record_dataset_evidence(config, fname, df)
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
    # The answer a caller sees is built from this string when the model is unavailable,
    # so it carries data only: an echoed 用户查询 and an instruction addressed to the
    # model both leaked into the reply.
    return f"数据分析结果:\n{result}"


# ==================== 真·自然语言数据查询（阶段 3 · P0） ====================

def _llm_pandas_code(df, query: str) -> str:
    """让 LLM 根据列结构生成一段只用 df/pd 的 pandas 表达式"""
    from app.agents.nodes import _make_model
    from langchain_core.messages import HumanMessage
    cols = ", ".join(f"{c}({df[c].dtype})" for c in df.columns)
    prompt = (
        "你是 pandas 专家。已有 DataFrame 变量 df，列如下：\n" + cols + "\n\n"
        "用【一个 Python 表达式】回答用户问题，只能使用 df 和 pd，"
        "返回值即答案（数字/字符串/列表/Series/DataFrame 均可）。\n"
        "只输出代码本身，不要解释、不要 markdown、不要 ```。\n\n"
        "用户问题：" + query
    )
    resp = _make_model(timeout=30).invoke([HumanMessage(content=prompt)])
    code = str(resp.content).strip()
    if code.startswith("```"):
        code = code.strip("`")
        if code.lower().startswith("python"):
            code = code[6:]
    return code.strip()


def _query_data(query: str, config: RunnableConfig) -> str:
    from app.common.rbac import filter_dataframe_rows
    from app.tools.excel import load_excel, safe_query
    context = _tool_context(config)
    if context is None:
        record_tool_status(
            bag_from_config(config), tool="query_data", status="rejected", error_code="authorization_required"
        )
        return _authorization_error()
    conf = (config or {}).get("configurable", {}) or {}
    role = context["role"]
    dept = context["department"]
    files, dataset_error = _authorized_dataset_files(config)
    if dataset_error:
        return dataset_error
    if not files:
        return "暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。"

    for fname, file_path in files:
        try:
            df = load_excel(file_path)
            df = filter_dataframe_rows(df, role=role, department=dept)
            if df.empty:
                continue
        except Exception:
            continue
        _record_dataset_evidence(config, fname, df)
        code = _llm_pandas_code(df, query)
        res = safe_query(df, code)
        if res.get("error") is None:
            result = res["result"]
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)
            return f"📊 {fname} 查询结果:\n{result}"
    return "查询失败：LLM 生成的代码在沙箱中多次执行未通过，请换个问法。"


# ==================== Chart Tool v2 ====================

def _generate_chart(
    chart_type: str,
    config: RunnableConfig,
    labels: list | None = None,
    values: list | None = None,
    datasets: dict | None = None,
    categories: list | None = None,
    tasks: list[dict] | None = None,
    root: str | None = None,
    branches: dict[str, list[str]] | None = None,
    title: str = "数据分析图表",
) -> str:
    from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
    from app.tools.visualize import gantt_chart, mindmap as _mindmap

    chart_funcs = {
        "bar": lambda: bar_chart(labels or [], values or [], title=title),
        "line": lambda: line_chart(labels or [], datasets or {"数据": values or []}, title=title),
        "pie": lambda: pie_chart(labels or [], values or [], title=title),
        "radar": lambda: radar_chart(categories or labels or [], datasets or {"数据": values or []}, title=title),
        "gantt": lambda: gantt_chart(tasks or [], title=title),
        "mindmap": lambda: _mindmap(root or title, branches or {}, title=title),
    }

    if chart_type not in chart_funcs:
        return f"不支持的图表类型: {chart_type}，可选: bar/line/pie/radar/gantt/mindmap"

    try:
        if _artifact_principal(config, ACTION_ANALYZE) is None:
            record_tool_status(
                bag_from_config(config), tool="generate_chart", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        path = chart_funcs[chart_type]()
    except Exception as e:
        return f"图表生成失败: {e}"

    urls = _artifact_urls(path, "chart", config)
    if urls is None:
        return _authorization_error()
    url, _ = urls
    if path.lower().endswith(".html"):
        return f"图表已生成: [{title}]({url})"
    return f"图表已生成: ![{title}]({url})"



# ==================== Export Tool ====================

def _export_report(report_title: str, sections_json: str,
                    config: RunnableConfig, include_charts: str = "") -> str:
    from app.tools.export import generate_pdf_report

    try:
        if _artifact_principal(config, ACTION_EXPORT) is None:
            record_tool_status(
                bag_from_config(config), tool="export_report", status="rejected", error_code="authorization_required"
            )
            return _authorization_error()
        sections = json.loads(sections_json)
        path = generate_pdf_report(title=report_title, sections=sections)

        urls = _artifact_urls(path, "report", config)
        if urls is None:
            return _authorization_error()
        _, url = urls
        return f"报告已生成: [📋 下载报告]({url})"
    except Exception as e:
        return f"报告生成失败: {e}"


@tool
def analyze_data(query: str, config: RunnableConfig) -> str:
    """
    分析企业经营数据。用于所有数据相关问题：统计数字、计算指标、对比业绩、
    排名、增长率、利润、营收等。调用此工具会自动检测已上传的 Excel/CSV 文件并进行分析。
    如果用户提到具体数字指标，优先使用此工具而不是 search_docs。
    """
    with start_tool_call(config, tool_name="analyze_data", arguments={"query": query}):
        return _analyze_data(query, config)


@tool
def query_data(query: str, config: RunnableConfig) -> str:
    """
    用自然语言查询经营数据（阶段3 P0）。LLM 生成 pandas 代码 → 沙箱执行 → 报错自动纠错。
    适合 analyze_data 固定模板答不了的组合条件问题，如
    "利润率超过20%且营收环比增长的门店有哪些"。
    """
    with start_tool_call(config, tool_name="query_data", arguments={"query": query}):
        return _query_data(query, config)


@tool("generate_chart")
def generate_chart_v2(
    chart_type: str,
    config: RunnableConfig,
    labels: list | None = None,
    values: list | None = None,
    datasets: dict | None = None,
    categories: list | None = None,
    tasks: list[dict] | None = None,
    root: str | None = None,
    branches: dict[str, list[str]] | None = None,
    title: str = "数据分析图表",
) -> str:
    """生成柱状图、折线图、饼图、雷达图、甘特图或思维导图。"""
    with start_tool_call(
        config,
        tool_name="generate_chart",
        arguments={
            "chart_type": chart_type,
            "title": title,
            "label_count": len(labels or []),
            "value_count": len(values or []),
        },
    ) as span:
        result = _generate_chart(
            chart_type,
            config,
            labels=labels,
            values=values,
            datasets=datasets,
            categories=categories,
            tasks=tasks,
            root=root,
            branches=branches,
            title=title,
        )
        if not str(result).startswith("图表已生成"):
            span.finish("failed", error_code="validation_error")
        return result


generate_chart = generate_chart_v2


@tool
def export_report(report_title: str, sections_json: str,
                  config: RunnableConfig, include_charts: str = "") -> str:
    """
    导出分析报告为 PDF 文件。
    sections_json: JSON 数组，每项 {"type":"heading"|"text","content":"..."}
    include_charts: 图表路径列表（可选）
    """
    with start_tool_call(
        config,
        tool_name="export_report",
        arguments={"report_title": report_title, "sections_json_length": len(sections_json or "")},
    ) as span:
        result = _export_report(report_title, sections_json, config, include_charts)
        if "报告已生成" not in str(result):
            span.finish("failed", error_code="internal_error")
        return result


# ==================== 工具列表 ====================

ALL_TOOLS = [search_docs, analyze_data, query_data, generate_chart, export_report]
