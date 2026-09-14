import json


def test_quality_runner_writes_timestamped_report(tmp_path):
    from app.quality.runner import run_recorded_evaluation

    fixture = tmp_path / "fixture.jsonl"
    fixture.write_text(
        json.dumps(
            {
                "id": "q1",
                "category": "文档问答",
                "question": "标准？",
                "answer": "500元",
                "must_contain": ["500元"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    answers = tmp_path / "answers.jsonl"
    answers.write_text(
        json.dumps(
            {
                "id": "q1",
                "answer": "标准是500元",
                "evidence": [{"source_name": "制度.pdf", "locator": "第1页"}],
                "latency_ms": 80,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    report = run_recorded_evaluation(fixture, answers, output)

    assert report["total"] == 1
    assert report["answer_correctness"] == 1.0
    assert output.exists()
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["latency_ms"]["p95"] == 80
