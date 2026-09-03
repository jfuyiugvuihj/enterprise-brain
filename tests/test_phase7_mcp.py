"""阶段 7 · MCP Server 集成测试"""
import asyncio
import pytest

try:
    import mcp  # noqa: F401
    HAS_MCP = True
except Exception:
    HAS_MCP = False

pytestmark = pytest.mark.skipif(not HAS_MCP, reason="mcp 未安装，跳过 MCP 测试")


class TestMcpServer:
    def test_create_server(self):
        from app.mcp_server import create_mcp_server
        s = create_mcp_server()
        assert s is not None

    def test_five_tools_registered(self):
        from app.mcp_server import create_mcp_server
        s = create_mcp_server()
        tools = asyncio.run(s.list_tools())
        names = {t.name for t in tools}
        assert names == {"search_docs", "analyze_data", "query_data",
                         "generate_chart", "export_report"}

    def test_default_role_conservative(self):
        # 默认 MCP_ROLE=staff，build_where 应返回过滤条件（非 None）
        from app.common import rbac
        assert rbac.build_where("staff", "") is not None
        assert rbac.build_where("admin", "") is None
