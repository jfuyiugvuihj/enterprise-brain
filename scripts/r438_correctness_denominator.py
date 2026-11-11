#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""R438 · correctness 两把尺的分母账（读侧派生，零写入）。

一句话：把「进 correctness 可判子集分母的枚数」从题源里的 R401 处置标记现算出来，并跟
R401 那本账（scripts/r401_anchor_provenance.py 的 denominator()）对一遍数。

🔴 本件不起第二套口径：分母的唯一读点是 app.quality.eval.row_disposition()，这里只调它。
   印出来的每一枚数字都是现算读数，本文件没有一个手抄的题数（那枚 AST 钉在
   tests/test_r438_correctness_denominator_is_wired_and_both_calibers_publish.py 里扫这个文件）。

跑法（只读盘：不打模型、不起容器、不动真树，跑分窗内也能跑）：
    python scripts/r438_correctness_denominator.py
    python scripts/r438_correctness_denominator.py --fixture tests/fixtures/business_evaluation_100.jsonl
    python scripts/r438_correctness_denominator.py --json _r438/denominator.json
退出码：0 = 两本账一致；1 = 两本账不一致（差异逐条印出来）；2 = 锚点读不出来或题源缺失。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 唯一派生读点：分母账由判分器自己算，本件只是把它现算的数印出来并对账。
from app.quality.eval import ScorabilityDerivationError, derive_scorability

DEFAULT_FIXTURE_REL = "tests/fixtures/business_evaluation_100.jsonl"
R401_SCRIPT = SCRIPTS_DIR / "r401_anchor_provenance.py"


def read_rows(path: str | Path) -> list[dict]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def load_r401():
    spec = importlib.util.spec_from_file_location("r438_r401_ledger", R401_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cross_check(rows: list[dict]) -> dict:
    """app 那本账 vs R401 那本账：任何一格对不上就是长出了两套口径，逐条点名。"""
    block = derive_scorability(rows)
    ledger = load_r401().denominator(rows)
    pairs = (
        ("全部题数", block["total_rows"], ledger["total_rows"]),
        ("点名扣除数", block["deducted_n"], ledger["unscorable_n"]),
        ("进分母数", block["denominator_rows"], ledger["correctness_denominator"]),
        ("扣除清单", sorted(block["deducted_ids"]), sorted(ledger["unscorable_ids"])),
    )
    mismatches = [
        "{0}：判分器账 {1} vs R401 账 {2}".format(name, mine, theirs)
        for name, mine, theirs in pairs
        if mine != theirs
    ]
    return {"block": block, "r401": ledger, "mismatches": mismatches, "pairs": pairs}


def render(result: dict, fixture: Path) -> str:
    block = result["block"]
    lines = [
        "R438 · correctness 的两把尺分母账（题源现算，非手抄）：{0}".format(fixture),
        "",
        "全部题数     {0}".format(block["total_rows"]),
        "点名扣除数   {0}".format(block["deducted_n"]),
        "进分母数     {0}".format(block["denominator_rows"]),
        "自洽算式     {0} - {1} = {2}".format(
            block["total_rows"], block["deducted_n"], block["denominator_rows"]),
        "",
        block["rule"],
        "口径来源     " + block["basis"],
        "",
        "逐枚被扣题（id · 查无出处的词 · 为什么今天不可考 · 去向）：",
    ]
    for record in block["deducted_rows"]:
        lines.append("  - {0} · 「{1}」 · {2} · {3}".format(
            record["id"], record["missing_term"], record["reason"], record["destination"]))
    lines.append("")
    if result["mismatches"]:
        lines.append("🔴 两本账不一致（本单不许有第二套口径）：")
        lines.extend("  - " + item for item in result["mismatches"])
    else:
        lines.append("两本账一致：判分器 derive_scorability() == R401 denominator()")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="r438_correctness_denominator.py",
        description="correctness 可判子集分母的读侧派生 + 与 R401 账对质（默认零写入）。",
    )
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE_REL, help="题源 jsonl 路径")
    parser.add_argument("--json", default=None, help="把分母账另存一份到这个路径（默认不写盘）")
    args = parser.parse_args(argv)

    fixture = Path(args.fixture)
    if not fixture.is_absolute():
        fixture = REPO_ROOT / fixture
    try:
        rows = read_rows(fixture)
    except (FileNotFoundError, OSError) as error:
        print("题源读不到：{0}（{1}）".format(fixture, error), file=sys.stderr)
        return 2
    try:
        result = cross_check(rows)
    except ScorabilityDerivationError as error:
        print("分母派生不到锚点，这份账不出：{0}".format(error), file=sys.stderr)
        return 2

    print(render(result, fixture))
    if args.json:
        payload = dict(result["block"])
        payload["r401_ledger"] = result["r401"]
        payload["mismatches"] = result["mismatches"]
        out = Path(args.json)
        if not out.is_absolute():
            out = REPO_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已另存：{0}".format(out))
    return 1 if result["mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
