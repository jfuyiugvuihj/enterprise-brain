"""R598 · 把 docs/testing/fixtures/r97-shard-{1,2,3}.jsonl 从主件**逐字节派生**。

【为什么有这件】
runbook `docs/handoff/2026-09-17-eval-real-run-runbook.md:413` 那行登记「冻结三分片拼接
**逐字节等于** tests/fixtures/business_evaluation_100.jsonl，sha256 前缀 2230b2b45be18bfb，
24,346 B ⇒ ✅」，本单 10-03 现读证伪：

    主件   41,941 B / sha256[:16] 686c564ff2985744 / 105 行
    三片拼接 24,346 B / sha256[:16] 2230b2b45be18bfb / 105 行（id 与行序与主件全同，29 行内容不同代）

三片是 09-17 冻结件 `78b8507` 抄的**当时**主件，R401（`baef92e`）改了主件却没回头改三片 ⇒
「手抄账与派生账分叉」那一族（同族先例 R583 `500d88a`）。历史分数没被污染：run13/14/16/17 的
`window.json` 里 `fixture_sha256` 逐枚＝主件，跑分窗吃的一直是主件；欠的只是把三片重派生＋
一枚常驻钉（钉在 `tests/test_r598_r97_shards_are_derived.py`）。

【本件的两条纪律】
1. 派生 = 从主件的字节里切，不是「读盘上现成三片比一下」：见 ``derive_shards``，它对主件做
   ``splitlines(keepends=True)`` 后按 (35, 35, 35) 分块再原样拼接，BOM／行序／CRLF／行尾字节
   一个都不加工。所以主件变了三片必然跟着变，三片被手改必然对不上。
2. 只回答「派生出来该是什么」和「盘上现在是什么」，不改判分器、不动主件、不动语料。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
SHARD_RELS = tuple(
    Path("docs") / "testing" / "fixtures" / "r97-shard-{0}.jsonl".format(index)
    for index in (1, 2, 3)
)
#: 在册分片粒度：35 + 35 + 35 = 105（跟进单 §160.3 判据⑦）。
SHARD_LINE_SIZES = (35, 35, 35)

EXIT_MATCH = 0      # 三片 == 派生：钉可翻绿
EXIT_MISMATCH = 1   # 三片 != 派生：盘上有手抄件，拒绝当绿交


def sha16(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def read_master_bytes(root: Path = REPO_ROOT) -> bytes:
    path = root / MASTER_REL
    if not path.is_file():
        raise FileNotFoundError("主件读不到：{0}".format(path))
    return path.read_bytes()


def master_lines(master: bytes) -> list[bytes]:
    """按**字节行**切主件（keepends=True）：换行符跟着行走，行尾一字节都不加工。"""
    return master.splitlines(keepends=True)


def derive_shards(master: bytes) -> list[bytes]:
    """判据⑦的派生腿：主件字节 → 三片字节，逐字节、保持现有序。

    行数必须等于 sum(SHARD_LINE_SIZES)，否则拒绝派生：分片粒度是账，不是随手能改的量。
    空行不在主件里（load_rows 会过滤），但这里**不过滤**——过滤就等于给三片动了手。
    """
    lines = master_lines(master)
    want = sum(SHARD_LINE_SIZES)
    if len(lines) != want:
        raise ValueError(
            "主件 {0} 有 {1} 行，分片账要的是 {2} 行（{3}）⇒ 拒绝派生，先对齐粒度".format(
                MASTER_REL.as_posix(), len(lines), want, SHARD_LINE_SIZES
            )
        )
    shards: list[bytes] = []
    cursor = 0
    for size in SHARD_LINE_SIZES:
        shards.append(b"".join(lines[cursor:cursor + size]))
        cursor += size
    if b"".join(shards) != master:
        raise AssertionError("派生自检破了：三片拼回去不等于主件（splitlines 不该丢字节）")
    return shards


def read_shards(root: Path = REPO_ROOT) -> list[bytes]:
    return [(root / rel).read_bytes() for rel in SHARD_RELS]


def line_ids(raw: bytes) -> list[str]:
    text = raw.decode("utf-8-sig")
    return [str(json.loads(line)["id"]) for line in text.splitlines() if line.strip()]


def compare(root: Path = REPO_ROOT) -> dict:
    """派生账 vs 盘上账，逐片点名；两边都打印 sha256 前 16（判据⑦要求的读数形态）。"""
    master = read_master_bytes(root)
    expected = derive_shards(master)
    actual = read_shards(root)
    per_shard = []
    for index, (rel, want, got) in enumerate(zip(SHARD_RELS, expected, actual), start=1):
        per_shard.append(
            {
                "shard": index,
                "path": rel.as_posix(),
                "derived_bytes": len(want),
                "ondisk_bytes": len(got),
                "derived_sha256_16": sha16(want),
                "ondisk_sha256_16": sha16(got),
                "byte_equal": want == got,
                "derived_ids": line_ids(want),
                "ondisk_ids": line_ids(got),
            }
        )
    concat = b"".join(actual)
    return {
        "repo_root": str(root),
        "master": {
            "path": MASTER_REL.as_posix(),
            "bytes": len(master),
            "sha256_16": sha16(master),
            "lines": len(master_lines(master)),
            "has_bom": master.startswith(b"\xef\xbb\xbf"),
            "line_ending": "crlf" if b"\r\n" in master else "lf",
        },
        "shards": per_shard,
        "concat": {
            "bytes": len(concat),
            "sha256_16": sha16(concat),
            "byte_equal_master": concat == master,
        },
        "all_shards_match": all(item["byte_equal"] for item in per_shard),
    }


def render(report: dict) -> str:
    master = report["master"]
    out = [
        "R598 三片派生对账（主件 → 分片，逐字节）",
        "  主件   : {0} {1} B / sha256[:16] {2} / {3} 行 / BOM={4} / 行尾={5}".format(
            master["path"], master["bytes"], master["sha256_16"], master["lines"],
            master["has_bom"], master["line_ending"],
        ),
    ]
    for item in report["shards"]:
        out.append(
            "  片 {0}  : 盘上 {1} B / {2}  ⟺  派生 {3} B / {4}  ⇒ {5}".format(
                item["shard"], item["ondisk_bytes"], item["ondisk_sha256_16"],
                item["derived_bytes"], item["derived_sha256_16"],
                "逐字节相等" if item["byte_equal"] else "不等（盘上被手改过或与主件不同代）",
            )
        )
    concat = report["concat"]
    out.append(
        "  三片拼接 : {0} B / sha256[:16] {1}  ⟺  主件 {2} B / sha256[:16] {3} ⇒ {4}".format(
            concat["bytes"], concat["sha256_16"], master["bytes"], master["sha256_16"],
            "逐字节相等" if concat["byte_equal_master"] else "不等",
        )
    )
    out.append(
        "  结论     : {0}".format(
            "三片＝从主件逐字节派生（钉可翻绿）"
            if report["all_shards_match"] and concat["byte_equal_master"]
            else "三片≠从主件派生（钉必红，跑 --write 重派生）"
        )
    )
    return "\n".join(out)


def write_shards(root: Path = REPO_ROOT) -> list[dict]:
    master = read_master_bytes(root)
    rows = []
    for rel, raw in zip(SHARD_RELS, derive_shards(master)):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows.append({"path": rel.as_posix(), "bytes": len(raw), "sha256_16": sha16(raw)})
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="仓库根（默认本脚本上两级）")
    parser.add_argument("--check", action="store_true", help="只对账不出数以外的动作（默认）")
    parser.add_argument("--write", action="store_true", help="把三片从主件重派生落盘（只动三片）")
    parser.add_argument("--json", dest="json_path", help="把对账结果以 UTF-8 JSON 写到该路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.write:
        for row in write_shards(root):
            print("已派生 {0}：{1} B / sha256[:16] {2}".format(
                row["path"], row["bytes"], row["sha256_16"]))
    report = compare(root)
    print(render(report))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return EXIT_MATCH if report["all_shards_match"] else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main())