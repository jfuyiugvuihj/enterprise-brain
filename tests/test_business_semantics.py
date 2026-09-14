from app.semantics.registry import match_metric_context


def test_metric_matching_handles_different_business_phrases():
    context = match_metric_context("分析差旅费用并判断是否超标")
    assert context is not None
    assert context.metric_name in {"住宿费标准", "差旅费"}


def test_metric_matching_returns_none_for_unrelated_questions():
    assert match_metric_context("今天天气怎么样？") is None
