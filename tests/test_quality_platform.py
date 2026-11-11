from app.agents.contracts import AgentResult, Evidence
from app.common.tracing import build_tracing_config, sanitize_trace_event
from app.quality.eval import evaluate_golden_set
from app.quality.provenance import build_answer_provenance
from app.semantics.registry import match_metric_context


def test_golden_set_metrics_are_computed_from_fixture(tmp_path):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(
        '{"question": "Q1", "answer": "A1"}\n{"question": "Q2", "answer": "A2"}\n',
        encoding="utf-8",
    )

    report = evaluate_golden_set(golden, lambda question: "A1" if question == "Q1" else "wrong")

    assert report == {"total": 2, "exact_match": 0.5, "answer_relevancy": 0.5}


def test_trace_sanitizer_redacts_sensitive_fields():
    event = {
        "user": "alice",
        "password": "secret123",
        "jwt": "eyJhbGciOi...",
        "api_key": "abc",
    }

    cleaned = sanitize_trace_event(event)

    assert cleaned["user"] == "alice"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["jwt"] == "[REDACTED]"
    assert cleaned["api_key"] == "[REDACTED]"


def test_tracing_config_uses_environment(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_PROJECT", "enterprise-brain")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://localhost:1984")

    config = build_tracing_config()

    assert config == {
        "enabled": True,
        "project": "enterprise-brain",
        "api_url": "http://localhost:1984",
    }


def test_provenance_builder_collects_worker_evidence_and_metrics():
    result = AgentResult(
        worker="doc",
        status="success",
        answer="住宿费标准为500元/晚。",
        confidence=0.9,
        evidence=[
            Evidence(
                source_type="document",
                source_name="差旅费报销制度.pdf",
                locator="第3页",
                excerpt="住宿费标准为500元/晚。",
                score=0.92,
            )
        ],
    )

    provenance = build_answer_provenance([result])

    assert provenance["workers"] == ["doc"]
    assert provenance["evidence"][0]["locator"] == "第3页"
    assert provenance["confidence"] == 0.9


def test_metric_matching_maps_common_questions_to_context():
    context = match_metric_context("本月住宿费标准是多少？")

    assert context is not None
    assert context.metric_name == "住宿费标准"
    assert context.unit == "元/晚"
