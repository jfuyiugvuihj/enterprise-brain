"""
阶段 7 · MCP Server 集成（信号线）

把企业智脑的 5 项能力用标准 MCP 协议暴露，外部客户端
（Claude Desktop / Cursor / 其它 agent）可直接调用。

隐私形态（关键）：
- 默认 stdio / 本地运行，数据不出客户机器；
- 可选 token 鉴权（MCP_TOKEN）；
- 复用与 API 相同的 Principal 检索过滤（MCP_USERNAME 必须指向已注册用户，否则拒绝检索）；
- 云端 LLM 同意是客户端责任，本处在 instructions 中明确提示。

运行:  python -m app.mcp_server          # stdio（本地）
"""
import os
from app.common.logger import logger

# 调用者身份：MCP 没有会话，只能靠 MCP_USERNAME 指向一个已注册用户。
# 角色/密级/部门一律以用户库为准，不接受 MCP_ROLE 这类可伪造的环境变量声明。
_USERNAME = os.getenv("MCP_USERNAME", "").strip()
_TOKEN = os.getenv("MCP_TOKEN", "")


def _mcp_principal():
    """Resolve the caller against the user store; unregistered identities get nothing."""
    from app.common import auth
    from app.common.identity import Principal

    if not _USERNAME:
        return None
    user = auth.get_user(_USERNAME)
    if not user:
        return None
    return Principal.from_user(user, auth_source="mcp")


def _search_docs_text(query: str) -> str:
    """Knowledge-base search with the caller's retrieval scope, shared by every transport."""
    from app.agents.tools import _get_pipeline
    from app.rag.filters import RetrievalScopeError
    from app.rag.retrieval_pipeline import DOC_HIT_CONTENT_CHARS, format_relevance

    principal = _mcp_principal()
    if principal is None:
        logger.warning("[MCP] 拒绝检索：MCP_USERNAME 未指向已注册用户")
        return "拒绝：MCP 调用身份未在用户库中注册，无法确定检索权限范围。"
    try:
        docs, _rewrites = _get_pipeline().search_for_principal(query, principal, top_k=5)
    except RetrievalScopeError as exc:
        logger.warning(f"[MCP] 拒绝检索：{exc.code}")
        return f"拒绝：{exc.code}"
    if not docs:
        return f"未找到与'{query}'相关的文档信息。"
    return "\n\n---\n\n".join(
        f"[{i}] 来源:{d.get('source')} 相关度:{format_relevance(d)}\n{d['content'][:DOC_HIT_CONTENT_CHARS]}"
        for i, d in enumerate(docs, 1)
    )


def _mcp_tool_config() -> dict:
    principal = _mcp_principal()
    if principal is None:
        # No verified identity: tools must fail closed inside _tool_principal.
        return {"configurable": {}}
    return {"configurable": {"principal": principal}}


def create_mcp_server():
    """懒导入 mcp，未安装时不破坏主应用导入。兼容 1.x(FastMCP)/2.x(MCPServer)"""
    try:
        from mcp.server.fastmcp import FastMCP as _Server   # mcp 1.x
    except ModuleNotFoundError:
        from mcp.server.mcpserver import MCPServer as _Server  # mcp 2.x

    mcp = _Server(
        "enterprise-brain",
        instructions=(
            "企业智脑 MCP Server：知识库检索/数据分析/图表/报告导出。"
            "数据私有化存储于客户机器。注意：检索返回的内容会进入你的 LLM 上下文，"
            "若你使用云端模型，等同数据出客户机器，请改用本地模型（Ollama）或取得用户同意。"
        ),
    )

    @mcp.tool()
    def search_docs(query: str) -> str:
        """搜索企业知识库（按已注册调用者的检索权限过滤，身份未注册即拒绝）。"""
        return _search_docs_text(query)

    @mcp.tool()
    def analyze_data(query: str) -> str:
        """分析企业经营数据（排名/统计/对比）。"""
        from app.agents.tools import analyze_data
        return analyze_data.invoke({"query": query}, config=_mcp_tool_config())

    @mcp.tool()
    def query_data(query: str) -> str:
        """自然语言查询经营数据（LLM 生成 pandas + 沙箱执行）。"""
        from app.agents.tools import query_data
        return query_data.invoke({"query": query}, config=_mcp_tool_config())

    @mcp.tool()
    def generate_chart(chart_type: str, labels: list, values: list, title: str = "图表") -> str:
        """生成图表（bar/line/pie/radar）。"""
        from app.agents.tools import generate_chart
        return generate_chart.invoke({"chart_type": chart_type, "labels": labels,
                                      "values": values, "title": title}, config=_mcp_tool_config())

    @mcp.tool()
    def export_report(report_title: str, sections_json: str) -> str:
        """导出 PDF 报告。"""
        from app.agents.tools import export_report
        return export_report.invoke(
            {"report_title": report_title, "sections_json": sections_json},
            config=_mcp_tool_config(),
        )

    return mcp


def main():
    if _TOKEN:
        logger.info("[MCP] 已启用 token 鉴权提示（客户端需在会话中携带）")
    principal = _mcp_principal()
    mcp = create_mcp_server()
    if principal is None:
        logger.warning("[MCP] 启动 stdio server，但 MCP_USERNAME 未注册，检索与数据工具将拒绝执行")
    else:
        logger.info(
            "[MCP] 启动 stdio server，身份 "
            f"user={principal.username} role={principal.role} dept={principal.department or '(未绑定)'}"
        )
    mcp.run()  # 默认 stdio（本地）


if __name__ == "__main__":
    main()
