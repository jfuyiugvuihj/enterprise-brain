from pathlib import Path


class TestGoldenEvaluation:
    def test_scores_exact_matches(self, tmp_path):
        from app.quality.eval import evaluate_golden_set

        golden = tmp_path / "golden.jsonl"
        golden.write_text(
            "\n".join(
                [
                    '{"question": "公司报销流程是什么", "answer": "提交申请后审批"}',
                    '{"question": "哪个门店利润最高", "answer": "建国路门店"}',
                ]
            ),
            encoding="utf-8",
        )

        def stub_answer(question: str) -> str:
            return "提交申请后审批" if "报销" in question else "建国路门店"

        report = evaluate_golden_set(golden, stub_answer)

        assert report["total"] == 2
        assert report["exact_match"] == 1.0
        assert report["answer_relevancy"] == 1.0


class TestTracingConfig:
    def test_tracing_toggle(self, monkeypatch):
        from app.common.tracing import build_tracing_config

        monkeypatch.setenv("LANGSMITH_TRACING", "true")
        monkeypatch.setenv("LANGSMITH_PROJECT", "enterprise-brain")

        enabled = build_tracing_config()

        assert enabled["enabled"] is True
        assert enabled["project"] == "enterprise-brain"


class TestSemanticCache:
    def test_hits_similar_question(self, monkeypatch):
        from app.common import cache

        monkeypatch.delenv("REDIS_URL", raising=False)
        cache.clear_semantic_cache()
        cache.cache_semantic_answer("公司报销流程是什么", "提交申请后审批")

        hit = cache.get_semantic_cached_answer("报销流程怎么走")

        assert hit == "提交申请后审批"
