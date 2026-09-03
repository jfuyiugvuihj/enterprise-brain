"""阶段 4（P0 主动智能 · 告警/日报）测试"""
import pandas as pd


def _df():
    return pd.DataFrame({
        "门店": ["中山路", "建国路"],
        "营收": [100, 300],
        "毛利率": [40, 60],
    })


class TestHit:
    def test_ops(self):
        from app.api.v1.alerts import hit
        assert hit(40, "lt", 50) is True
        assert hit(60, "lt", 50) is False
        assert hit(60, "gt", 50) is True
        assert hit(50, "gte", 50) is True
        assert hit(50, "lte", 50) is True
        assert hit(1, "bad", 2) is False  # 非法操作符不触发


class TestMetricValue:
    def test_sum(self):
        from app.api.v1.alerts import _metric_value
        assert _metric_value(_df(), "营收") == 400

    def test_missing_column(self):
        from app.api.v1.alerts import _metric_value
        assert _metric_value(_df(), "不存在") is None

    def test_text_column(self):
        from app.api.v1.alerts import _metric_value
        assert _metric_value(_df(), "门店") is None


class TestEvaluateGraceful:
    def test_returns_list_without_pg(self):
        # Postgres 停时 evaluate_all 应优雅返回 []（不抛异常）
        from app.api.v1.alerts import evaluate_all
        result = evaluate_all()
        assert isinstance(result, list)


class TestDailyReport:
    def test_returns_string(self):
        from app.api.v1.alerts import daily_report
        text = daily_report()
        assert isinstance(text, str)
        assert "日报" in text
