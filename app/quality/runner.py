import json
from pathlib import Path

from app.quality.eval import evaluate_evaluation_set


def _load_answers(path: str | Path) -> dict[str, dict]:
    answers = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            item = json.loads(line)
            answers[str(item["id"])] = item
    return answers


def run_recorded_evaluation(
    fixture_path: str | Path,
    answers_path: str | Path,
    output_path: str | Path,
) -> dict:
    answers = _load_answers(answers_path)

    def answer_fn(row):
        return answers.get(
            str(row["id"]),
            {"answer": "", "evidence": [], "latency_ms": None},
        )

    report = evaluate_evaluation_set(fixture_path, answer_fn)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
