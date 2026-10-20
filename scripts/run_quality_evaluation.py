import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.quality.runner import run_recorded_evaluation
from app.quality.eval import format_correctness_rulers  # R438 判据⑩：第二把尺由判分器自己报，本件不抄键名也不抄数字


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
        f"p95_ms={report['latency_ms']['p95']} {format_correctness_rulers(report)}"
    )


if __name__ == "__main__":
    main()
