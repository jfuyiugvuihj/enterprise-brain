"""阶段 0（地基与安全）修复的回归测试

只测不依赖外部服务（Ollama/Redis/真实 LLM）的点，保证 pytest 稳定全绿。
"""
import os
import pytest
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(*rel):
    with open(os.path.join(ROOT, *rel), "r", encoding="utf-8") as f:
        return f.read()


class TestSecretsRemoved:
    """S1/S4: 真实密钥不再出现在配置文件与脚本里"""

    def test_config_yaml_no_real_jwt(self):
        content = _read("config.yaml")
        assert "11a06d21" not in content, "config.yaml 仍含真实 JWT 密钥"
        assert "CHANGE_ME" in content, "config.yaml 应留占位符"

    def test_generate_docs_no_hardcoded_key(self):
        content = _read("generate_docs.py")
        assert "sk-f04ced" not in content, "generate_docs.py 仍硬编码 DeepSeek Key"


class TestMainHardening:
    """S3/D4: main.py 安全加固回归"""

    def test_register_not_public(self):
        content = _read("app", "main.py")
        assert '/api/v1/users" and request.method == "POST"' not in content, \
            "注册接口不应再跳过鉴权"

    def test_cors_credentials_off(self):
        content = _read("app", "main.py")
        assert "allow_credentials=False" in content, "CORS 不应 * + credentials 同用"


class TestColumnDisambiguation:
    """C3: 多数值列时不静默选错列"""

    def _df(self):
        return pd.DataFrame({
            "门店": ["中山路", "建国路", "人民路"],
            "营收": [100, 300, 200],
            "利润": [10, 30, 20],
        })

    def test_ambiguous_query_returns_all_columns(self):
        from app.agents.tools import _answer_query
        df = self._df()
        results = _answer_query(df, "哪个门店最高", ["营收", "利润"], ["门店"])
        hits = [r for r in results if "🎯" in r]
        # 歧义（未点名指标）→ 每个数值列都给一条，避免选错
        assert len(hits) == 2, f"歧义查询应返回多列结果, 实际 {len(hits)}"

    def test_specific_query_single_column(self):
        from app.agents.tools import _answer_query
        df = self._df()
        results = _answer_query(df, "哪个门店利润最高", ["营收", "利润"], ["门店"])
        hits = [r for r in results if "🎯" in r]
        assert len(hits) == 1
        assert "利润" in hits[0]
        assert "建国路" in hits[0], "应选出利润最高的建国路"


class TestBm25Rebuild:
    """C1: rebuild_bm25 存在且 pipeline 未加载时安全无操作"""

    def test_noop_when_pipeline_none(self, monkeypatch):
        import app.agents.tools as tools
        monkeypatch.setattr(tools, "_search_pipeline", None)
        # 不应抛异常
        assert tools.rebuild_bm25() is None

    def test_function_exists(self):
        from app.agents.tools import rebuild_bm25
        assert callable(rebuild_bm25)


class TestQueueGraph:
    """C2: 队列专用图存在且节点齐全（无 interrupt 卡死）"""

    def test_queue_graph_nodes(self):
        from app.agents.orchestrator import queue_graph
        nodes = list(queue_graph.get_graph().nodes.keys())
        for n in ["supervisor", "doc", "data", "chart", "export"]:
            assert n in nodes, f"queue_graph 缺少节点: {n}"

    def test_run_orchestrator_queue_exists(self):
        from app.agents.orchestrator import run_orchestrator_queue
        assert callable(run_orchestrator_queue)
