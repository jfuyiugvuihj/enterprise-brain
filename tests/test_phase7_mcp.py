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

    def test_mcp_does_not_accept_a_declared_identity(self):
        # 旧断言拿 rbac.build_where 证明「默认保守」，而那个函数已随 C-4 删除（零生产调用点）。
        # 这里钉真正要保证的事：MCP 侧不存在「用环境变量声明身份」的入口，
        # 角色/密级/部门一律以用户库为准（app/mcp_server.py 顶部注释就是这条理由）。
        import inspect

        from app import mcp_server

        src = inspect.getsource(mcp_server)
        for injected in (
            'getenv("MCP_ROLE"',
            "getenv('MCP_ROLE'",
            'environ["MCP_ROLE"]',
            'environ.get("MCP_ROLE")',
        ):
            assert injected not in src, injected
