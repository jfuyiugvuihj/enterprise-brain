"""R704 · C 门第四格的"分母在不在"量具（派生读数，不是新判据）。

判分器（``app/quality/eval.py::evaluate_provenance``）算的是「带 unsupported 断言的行数 ÷ 行数」，
它不区分两种 0.0：**每一行都带着 claims 且没有一条不被支撑**，与**没有一行带 claims**。
后者是没有分母的 0，不是没有幻觉。本量具只读现成的窗件，把这两形分开交回。

离线：零容器、零模型、零库连接；只读 ``<tmp>/<tag>-answers.jsonl`` 与 ``<tmp>/<tag>-quality.json``。
退出码：0＝分母在位（有行且至少一行的 claims 非空）；3＝没分母（行在、claims 全空或缺键）；
2＝窗件读不到（这一扇窗还没跑／路径不对），不许把它当成"达标"或"不达标"。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

TMP_DEFAULT = os.path.join(os.environ.get("TEMP") or "/tmp", "evalrun")


def read_rows(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def claims_of(row) -> list:
    value = row.get("claims")
    return value if isinstance(value, list) else []


def tally(rows: list) -> dict:
    total = len(rows)
    with_key = sum(1 for row in rows if "claims" in row)
    with_items = sum(1 for row in rows if claims_of(row))
    items = sum(len(claims_of(row)) for row in rows)
    supported = sum(1 for row in rows for claim in claims_of(row) if claim.get("supported"))
    unsupported = items - supported
    rows_with_unsupported = sum(1 for row in rows
                                if any(not claim.get("supported") for claim in claims_of(row)))
    ids_without_key = [str(row.get("id", "?")) for row in rows if "claims" not in row][:12]
    return {
        "rows": total,
        "rows_with_claims_key": with_key,
        "rows_with_claims_items": with_items,
        "claims_total": items,
        "claims_supported": supported,
        "claims_unsupported": unsupported,
        "rows_with_unsupported": rows_with_unsupported,
        "denominator": "MEASURED" if with_items else "NOT_MEASURED",
        "unsupported_claim_rate_derived": (
            round(rows_with_unsupported / with_items, 4) if with_items else None
        ),
        "sample_rows_without_key": ids_without_key,
    }


def quality_rate(path: str):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    for arm in ("arms", "scores", "provenance"):
        node = doc.get(arm)
        if isinstance(node, dict) and "unsupported_claim_rate" in node:
            return node["unsupported_claim_rate"]
    return doc.get("unsupported_claim_rate")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", required=True)
    ap.add_argument("--tmp", default=TMP_DEFAULT)
    args = ap.parse_args()

    answers = os.path.join(args.tmp, args.window + "-answers.jsonl")
    quality = os.path.join(args.tmp, args.window + "-quality.json")
    if not os.path.exists(answers):
        print(json.dumps({"window": args.window, "error": "answers missing", "path": answers},
                         ensure_ascii=False))
        return 2

    table = tally(read_rows(answers))
    table["window"] = args.window
    table["scorer_unsupported_claim_rate"] = quality_rate(quality)
    table["scorer_and_deriver_agree"] = (
        table["scorer_unsupported_claim_rate"] == table["unsupported_claim_rate_derived"]
        if table["scorer_unsupported_claim_rate"] is not None else None
    )
    print(json.dumps(table, ensure_ascii=False, sort_keys=True))
    return 0 if table["denominator"] == "MEASURED" else 3


if __name__ == "__main__":
    sys.exit(main())
