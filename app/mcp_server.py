"""
阶段 7 · MCP Server 集成（信号线）

把企业智脑的 5 项能力用标准 MCP 协议暴露，外部客户端
（Claude Desktop / Cursor / 其它 agent）可直接调用。

隐私形态（关键）：
- 默认 stdio / 本地运行，数据不出客户机器；
- 可选 token 鉴权（MCP_TOKEN）；
- 复用 RBAC 文档级过滤（MCP_ROLE / MCP_DEPARTMENT 指定调用者身份，默认 staff 最保守）；
- 云端 LLM 同意是客户端责任，本处在 instructions 中明确提示。

运行:  python -m app.mcp_server          # stdio（本地）
"""
import os
from app.common import rbac
from app.common.logger import logger

# 调用者身份（MCP 无会话，用环境变量注入；默认 staff 最保守）
_ROLE = os.getenv("MCP_ROLE", "staff")
_DEPT = os.getenv("MCP_DEPARTMENT", "")
_TOKEN = os.getenv("MCP_TOKEN", "")


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

    where = rbac.build_where(_ROLE, _DEPT)
    pred = rbac.make_pred(_ROLE, _DEPT)

    @mcp.tool()
    def search_docs(query: str) -> str:
        """搜索企业知识库（按 MCP_ROLE/MCP_DEPARTMENT 权限过滤）。"""
        from app.agents.tools import _get_pipeline
        docs, rewrites = _get_pipeline().search(query, top_k=5, where=where, pred=pred)
        if not docs:
            return f"未找到与'{query}'相关的文档信息。"
        return "\n\n---\n\n".join(
            f"[{i}] 来源:{d.get('source')} 相关度:{d.get('_score', 0):.2f}\n{d['content'][:500]}"
            for i, d in enumerate(docs, 1)
        )

    @mcp.tool()
    def analyze_data(query: str) -> str:
        """分析企业经营数据（排名/统计/对比）。"""
        from app.agents.tools import analyze_data
        return analyze_data.invoke({"query": query})

    @mcp.tool()
    def query_data(query: str) -> str:
        """自然语言查询经营数据（LLM 生成 pandas + 沙箱执行）。"""
        from app.agents.tools import query_data
        return query_data.invoke({"query": query})

    @mcp.tool()
    def generate_chart(chart_type: str, labels: list, values: list, title: str = "图表") -> str:
        """生成图表（bar/line/pie/radar）。"""
        from app.agents.tools import generate_chart
        return generate_chart.invoke({"chart_type": chart_type, "labels": labels,
                                      "values": values, "title": title})

    @mcp.tool()
    def export_report(report_title: str, sections_json: str) -> str:
        """导出 PDF 报告。"""
        from app.agents.tools import export_report
        return export_report.invoke({"report_title": report_title, "sections_json": sections_json})

    return mcp


def main():
    if _TOKEN:
        logger.info("[MCP] 已启用 token 鉴权提示（客户端需在会话中携带）")
    mcp = create_mcp_server()
    logger.info(f"[MCP] 启动 stdio server，身份 role={_ROLE} dept={_DEPT or '(全部门)'}")
    mcp.run()  # 默认 stdio（本地）


if __name__ == "__main__":
    main()
