import json


def test_evaluation_report_tracks_categories_and_latency(tmp_path):
    from app.quality.eval import evaluate_evaluation_set

    fixture = tmp_path / "evaluation.jsonl"
    fixture.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "doc-1",
                        "category": "文档问答",
                        "question": "住宿费标准是多少？",
                        "answer": "500元/晚",
                        "must_contain": ["500元/晚"],
                        "requires_evidence": True,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "id": "scope-1",
                        "category": "无证据问题",
                        "question": "公司有没有火星基地？",
                        "answer": "无法确认",
                        "must_contain": ["无法确认"],
                        "requires_evidence": False,
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    def answer_fn(row):
        return {
            "answer": "住宿费标准是500元/晚。",
            "evidence": [{"source_name": "差旅制度.pdf", "locator": "第3页"}],
            "confidence_label": "high",
            "latency_ms": 120,
        } if row["id"] == "doc-1" else {
            "answer": "无法确认，公司知识库没有相关证据。",
            "evidence": [],
            "confidence_label": "low",
            "latency_ms": 240,
        }

    report = evaluate_evaluation_set(fixture, answer_fn)

    assert report["total"] == 2
    assert report["answer_correctness"] == 1.0
    assert report["evidence_coverage"] == 1.0
    assert report["category_metrics"]["文档问答"]["correctness"] == 1.0
    assert report["category_metrics"]["无证据问题"]["correctness"] == 1.0
    assert report["latency_ms"]["p95"] == 240


def test_evaluate_provenance_flags_unsupported_claims():
    from app.quality.eval import evaluate_provenance

    report = evaluate_provenance(
        {
            "answer": "公司规定住宿费为500元/晚，财务总监审批。",
            "evidence": [{"source_name": "差旅制度.pdf", "locator": "第3页"}],
            "claims": [
                {"text": "住宿费为500元/晚", "supported": True},
                {"text": "财务总监审批", "supported": False},
            ],
            "confidence": 0.42,
        }
    )

    assert report["has_evidence"] is True
    assert report["evidence_coverage"] == 0.5
    assert report["confidence_label"] == "low"
    assert report["unsupported_claims"] == ["财务总监审批"]
