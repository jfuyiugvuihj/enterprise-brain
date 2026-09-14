import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.performance import PerformanceStats


def main():
    parser = argparse.ArgumentParser(description="Build a P95 performance report.")
    parser.add_argument("input", help="JSONL with duration_ms and optional error fields")
    parser.add_argument("--output", default="docs/testing/performance-report.json")
    args = parser.parse_args()
    stats = PerformanceStats()
    for line in Path(args.input).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            stats.observe(item["duration_ms"], error=bool(item.get("error")))
    report = stats.report()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
