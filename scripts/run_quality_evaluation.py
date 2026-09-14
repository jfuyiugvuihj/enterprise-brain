import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.quality.runner import run_recorded_evaluation


def main():
    parser = argparse.ArgumentParser(description="Run the enterprise evaluation set.")
    parser.add_argument(
        "--fixture",
        default="tests/fixtures/business_evaluation_30.jsonl",
    )
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output", default="docs/testing/evaluation-report.json")
    args = parser.parse_args()
    report = run_recorded_evaluation(args.fixture, args.answers, args.output)
    print(
        f"evaluated={report['total']} "
        f"correctness={report['answer_correctness']:.4f} "
        f"evidence={report['evidence_coverage']:.4f} "
        f"p95_ms={report['latency_ms']['p95']}"
    )


if __name__ == "__main__":
    main()
