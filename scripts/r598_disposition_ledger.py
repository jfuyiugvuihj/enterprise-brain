"""R598 · 逐枚处置台账：19 枚「查无出处」的题怎么判，账从题源与语料**现读**，枚数不写死。

【这件答的三问】
1. 判据①「一枚不落」：今天查无出处的每一枚，归哪一桶、按哪条规则处置、落地形态是什么。
   桶的**归类**是本单新增的人工判断（唯一一处人为分析），其余字段全部现读：
   reason / pool / missing_term 从题源的 R401 标记里读（`app/quality/eval.py:242
   unscorable_records`），缺哪几枚从语料里复算（`scripts/check_eval_evidence_coverage.py`），
   分母从 `derive_scorability` 长出来。🔴 本件不抄任何一枚数进纸面常量。
2. 判据⑥的不变式：「查无出处的行数」== 「丙案枚数」，且「行数 == 词条数」的口径指纹不破。
   这两条按**现读值互比**，不钉具体数字 ⇒ 将来合法改题也不会让本件变旧。
3. CSV 假想账（§3 第三小节的「算给下一班看数」）：如果哪天采纳 `data/*.csv` 为出处，
   能救回哪几枚、分母变几。本件把这问跑成真数，不引用历史注释。

【判据边界】本件只读不改：不动题源、不动语料、不动判分器。改题的落地能力在
`scripts/r598_pending_jia.py`（待授权的那一枚甲）与总控裁定的后续单里。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
COVERAGE_REL = Path("scripts") / "check_eval_evidence_coverage.py"
EVAL_REL = Path("app") / "quality" / "eval.py"

#: 本单基点（`git worktree add --detach` 的来处）：守恒比对拿它当参照，不拿「此刻盘面」当参照。
BASE_REV = "b78ecd8"

#: 归类是本单新增的分析；每桶的处置规则照跟进单 §160.4 判据③。
BUCKET_OF = {
    "doc-15": "A 语料互斥（业主裁定域）",
    "doc-17": "A 语料互斥（业主裁定域）",
    "chat-09": "B 会话内真值（出处天然不在 95 篇）",
    "chat-11": "B 会话内真值（出处天然不在 95 篇）",
    "chat-12": "B 会话内真值（出处天然不在 95 篇）",
    "insight-07": "B 会话内真值（出处天然不在 95 篇）",
    "data-07": "C CSV/数据侧真值（主口径排除 CSV）",
    "data-08": "C CSV/数据侧真值（主口径排除 CSV）",
    "insight-05": "C CSV/数据侧真值（主口径排除 CSV）",
    "insight-06": "C CSV/数据侧真值（主口径排除 CSV）",
    "tool-03": "D 产品行为/输出形状词",
    "report-03": "D 产品行为/输出形状词",
    "report-07": "D 产品行为/输出形状词",
    "report-08": "D 产品行为/输出形状词",
    "report-09": "D 产品行为/输出形状词",
    "unsupported-01": "E 拒答类（考「不编」，判分器形状未接线）",
    "unsupported-02": "E 拒答类（考「不编」，判分器形状未接线）",
    "unsupported-04": "E 拒答类（考「不编」，判分器形状未接线）",
    "chat-02": "F 30 行母集冻结（tests/test_evaluation_report.py 的继承钉）",
}
#: 每桶今天的处置与去向（🔴 全丙：本单没有任何一枚丙→甲落地，理由见 disposition_table 的 note）
BUCKET_DISPOSITION = {
    "A 语料互斥（业主裁定域）": "丙·真互斥（语料内部无仲裁指针，见 §〇.3）；改的是语料不是金标",
    "B 会话内真值（出处天然不在 95 篇）": "丙·会话内真值；除非另寻到语料在位且语义等价的锚词，否则不进甲",
    "C CSV/数据侧真值（主口径排除 CSV）": "丙·主口径不动（§1.7）；实测 CSV 也救不回 ⇒ 归 D 族挂 R600",
    "D 产品行为/输出形状词": "丙·必须改判分器才能救，本单不改判分器 ⇒ 挂 R600",
    "E 拒答类（考「不编」，判分器形状未接线）": "丙·同上，挂 R600",
    "F 30 行母集冻结（tests/test_evaluation_report.py 的继承钉）": "丙·母集改版需业主批准（另单）",
}


_LOADED: dict[tuple[str, str], object] = {}


def _load_module(name: str, path: Path):
    """同一份尺子在一个进程里只 Exec 一次。

    🔴 这不是性能优化：`StructureDrift` 这类异常**按类型身份**判定，重复 Exec 会造出第二个
    同名不同源的类，影子根的刀就再也 raise 不到调用方认得的那一枚（本单 T1/T2 第一跑就是
    这么红的）。缓存之后，量具与被测件用的是同一把尺、同一个异常类。
    """
    key = (name, str(Path(path).resolve()))
    cached = _LOADED.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _LOADED[key] = module
    return module


def load_deps(root: Path = REPO_ROOT, code_root: Path = REPO_ROOT) -> dict:
    """尺子从 code_root（默认仓库）取，数据从 root 量：影子根只需要换数据，不需要复刻代码。

    🔴 这一句是「影子根」能成立的前提：判分宽度与归一化规则永远是被测仓库那一把，
    影子根里改的只有题源与语料副本，所以影子读数与盘面读数可比。
    """
    return {
        "cov": _load_module("r598_cov", code_root / COVERAGE_REL),
        "ev": _load_module("r598_ev", code_root / EVAL_REL),
    }


def read_rows(root: Path = REPO_ROOT, cov=None) -> list[dict]:
    cov = cov or load_deps(root)["cov"]
    return cov.load_rows(root / MASTER_REL)


def base_rows(root: Path = REPO_ROOT, rev: str = BASE_REV) -> list[dict] | None:
    """从 git 现取基点那枚题源 blob；读不出来（浅克隆/历史被改写）返回 None 由调用方点名。"""
    import subprocess

    run = subprocess.run(
        ["git", "-C", str(root), "show", "{0}:{1}".format(rev, MASTER_REL.as_posix())],
        capture_output=True,
    )
    if run.returncode != 0:
        return None
    return [json.loads(line) for line in run.stdout.decode("utf-8-sig").splitlines() if line.strip()]


def coverage_reading(root: Path = REPO_ROOT, *, include_csv: bool = False) -> dict:
    """现读「查无出处的行/词」，并算 行数==词条数 指纹（判据⑥）。"""
    deps = load_deps()
    cov = deps["cov"]
    rows = read_rows(root, cov)
    corpus = cov.load_corpus(root, include_csv=include_csv)
    missing = cov.find_missing_terms(rows, corpus)
    rows_n = len(missing)
    terms_n = sum(len(terms) for terms in missing.values())
    unscorable = deps["ev"].unscorable_row_ids(rows)
    return {
        "caliber": "documents/*.txt + data/*.csv【CSV 备选口径】" if include_csv
        else "documents/*.txt（主口径）",
        "fixture_rows": len(rows),
        "term_total": sum(len(row[cov.MUST_CONTAIN_FIELD]) for row in rows),
        "missing_rows": rows_n,
        "missing_terms": terms_n,
        "fingerprint_rows_equals_terms": rows_n == terms_n,
        "missing_ids": sorted(missing),
        "missing_by_row": {key: [str(t) for t in value] for key, value in sorted(missing.items())},
        "unscorable_ids": sorted(unscorable),
        "unscorable_n": len(unscorable),
        "missing_equals_unscorable": sorted(missing) == sorted(unscorable),
    }


def csv_hypothesis(root: Path = REPO_ROOT) -> dict:
    """§3 第三小节的假想账：采纳 CSV 为出处能救回哪几枚、分母变几（全部现算）。"""
    deps = load_deps()
    cov = deps["cov"]
    rows = read_rows(root, cov)
    main = coverage_reading(root)
    with_csv = coverage_reading(root, include_csv=True)
    rescued = sorted(set(main["missing_ids"]) - set(with_csv["missing_ids"]))
    still_missing = sorted(set(with_csv["missing_ids"]))
    corpus_raw = cov.load_corpus_raw(root, include_csv=True)
    per_term = {}
    for row in rows:
        if str(row["id"]) not in main["missing_ids"]:
            continue
        for term in row[cov.MUST_CONTAIN_FIELD]:
            hits = cov.derive_term_provenance(str(term), corpus_raw)
            per_term.setdefault(str(row["id"]), {})[str(term)] = {
                "hit_labels": [hit["label"] for hit in hits],
                "hit_paths": [hit["path"] for hit in hits],
            }
    csv_only_hits = {
        row_id: {term: info["hit_paths"] for term, info in terms.items()}
        for row_id, terms in per_term.items()
        if any(any("data/" in path for path in info["hit_paths"]) for info in terms.values())
    }
    return {
        "main_missing_rows": main["missing_rows"],
        "csv_caliber_missing_rows": with_csv["missing_rows"],
        "rescued_ids": rescued,
        "rescued_n": len(rescued),
        "denominator_before": main["fixture_rows"] - main["unscorable_n"],
        "denominator_after_hypothesis": with_csv["fixture_rows"] - with_csv["unscorable_n"],
        "still_missing_ids": still_missing,
        "c_bucket_terms_hitting_csv": csv_only_hits,
        "note": (
            "救回 0 枚时这句是结论不是空话：C 桶四枚缺的是「前五/小计/长期未处理/超标率」这类"
            "**输出形状词**，CSV 里有的是数据值而没有这些字面串 ⇒ 采纳 CSV 也一枚救不回，"
            "所以本桶与 D 桶同族，账应挂 R600（改判分器那一族），不该挂着「CSV 口径」这条主口径的账。"
        ),
    }


def conservation(root: Path = REPO_ROOT, rev: str = BASE_REV) -> dict:
    """判据②：题源恒 105 行、id 集合与顺序不变、tier/category 逐档守恒、丙案行一字节未动。

    🔴 参照物是基点 blob，不是「此刻盘面」——常驻钉不许把盘面脏不脏当判据（AGENTS.md 并树纪律）。
    """
    return conservation_between(base_rows(root, rev), read_rows(root), rev)


def conservation_between(base, rows: list[dict], rev: str = BASE_REV) -> dict:
    """同一把尺的纯函数版：给两份行表（参照 / 现在），出守恒账。影子根里没有 git，
    参照必须由调用方从**真仓库**现取 blob 再递进来，所以把比对抽成这一层。
    """
    current_ids = [str(row["id"]) for row in rows]
    tiers = {str(row["id"]): str(row.get("tier")) for row in rows}
    categories = {str(row["id"]): str(row.get("category")) for row in rows}
    out = {
        "base_rev": rev,
        "base_blob_readable": base is not None,
        "rows": len(rows),
        "row_count_matches_base": None if base is None else len(rows) == len(base),
        "id_order_matches_base": None if base is None else current_ids == [str(r["id"]) for r in base],
        "tier_distribution": _counts(tiers.values()),
        "category_distribution": _counts(categories.values()),
        "retitled_ids": [],
        "unscorable_touched_ids": [],
        "violations": [],
    }
    if base is None:
        out["violations"].append("基点 {0} 的题源 blob 读不出来 ⇒ 守恒没法判，指名报错".format(rev))
        return out
    base_by_id = {str(row["id"]): row for row in base}
    for row in rows:
        row_id = str(row["id"])
        old = base_by_id[row_id]
        moved = [
            field for field in ("question", "answer", "must_contain")
            if row.get(field) != old.get(field)
        ]
        if moved:
            out["retitled_ids"].append(row_id)
        marker = row.get("r401")
        if isinstance(marker, dict) and marker.get("disposition") == "丙" and moved:
            out["unscorable_touched_ids"].append(row_id)
        for field in ("tier", "category", "requires_evidence", "conflict_pair", "metric", "department"):
            if row.get(field) != old.get(field):
                out["violations"].append("{0}.{1} 动了：判据②要求桶与 category 守恒".format(row_id, field))
    base_categories = _counts(str(row.get("category")) for row in base)
    base_tiers = _counts(str(row.get("tier")) for row in base)
    if out["category_distribution"] != base_categories:
        out["violations"].append("category 逐档分布与基点不等")
    if out["tier_distribution"] != base_tiers:
        out["violations"].append("tier 逐档分布与基点不等")
    if out["unscorable_touched_ids"]:
        out["violations"].append(
            "丙案铁规破了（题保留、must_contain 一字节不动）：" + "、".join(out["unscorable_touched_ids"]))
    return out


def _counts(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items()))


def disposition_table(root: Path = REPO_ROOT) -> list[dict]:
    """逐枚：现读 missing 词 / reason / pool + 本单归类 + 处置与去向。缺一枚桶就报错。"""
    deps = load_deps()
    cov, ev = deps["cov"], deps["ev"]
    rows = read_rows(root, cov)
    records = {rec["id"]: rec for rec in ev.unscorable_records(rows)}
    missing = cov.find_missing_terms(rows, cov.load_corpus(root))
    table = []
    for row_id in sorted(missing):
        record = records.get(row_id)
        if record is None:
            raise AssertionError(
                "{0} 查无出处却没被丙案点名 ⇒ 判据④缺一枚（unscorable_records 会当场抛）".format(row_id))
        bucket = BUCKET_OF.get(row_id)
        if bucket is None:
            raise AssertionError("{0} 没归桶：判据①要求一枚不落".format(row_id))
        table.append({
            "id": row_id,
            "bucket": bucket,
            "disposition": "丙",
            "missing_term": record["missing_term"],
            "question": record["question"],
            "reason_in_fixture": record["reason"],
            "pool": record["destination"],
            "today_action": BUCKET_DISPOSITION[bucket],
        })
    unmapped = sorted(set(BUCKET_OF) - set(missing))
    if unmapped:
        raise AssertionError(
            "归类账里有 {0} 枚今天已不在「查无出处」名册上（说明题源动过，本账要跟着一枚枚核）：{1}".format(
                "、".join(unmapped), len(unmapped)))
    return table


def chat10_reading(root: Path = REPO_ROOT) -> dict:
    """§3 第一小节要现查的「第三组：住宿超标 需审批 vs 自理」——它在不在 19 枚里。"""
    deps = load_deps()
    cov = deps["cov"]
    rows = read_rows(root, cov)
    by_id = {str(row["id"]): row for row in rows}
    row = by_id["chat-10"]
    corpus_raw = cov.load_corpus_raw(root)
    anchors = [str(term) for term in row[cov.MUST_CONTAIN_FIELD]]
    provenance = {term: cov.derive_term_provenance(term, corpus_raw) for term in anchors}
    missing = cov.find_missing_terms(rows, cov.load_corpus(root))
    return {
        "id": "chat-10",
        "question": str(row["question"]),
        "answer": str(row["answer"]),
        "must_contain": anchors,
        "in_the_unscorable_19": "chat-10" in missing,
        "carries_r401_marker": isinstance(row.get("r401"), dict),
        "anchor_provenance_documents": {
            term: [(hit["path"], hit["raw_line_numbers"]) for hit in records]
            for term, records in provenance.items()
        },
        "conflict_side_line": "documents/差旅费报销细则_2026版.txt:12「超出部分自理」",
        "verdict": (
            "不在 19 枚里：锚词「部门负责人」在 10 篇语料里到处有出处，覆盖度件判它「有出处」，"
            "所以它不进丙案名册、今天照旧进 correctness 分母。但它考的那条命题（住宿超标要审批）"
            "与细则:12「超出部分自理」方向相反 ⇒ 这是**得分侧的假阳性风险行**，不是丙案。"
            "本单不动它：它是得分行，动它会同时改 correctness 的历史可比性，且它也属"
            "「业主裁制度」那一族 ⇒ 记进交付检查项，随 doc-15/doc-17 一起裁。"
        ),
    }


def render(report: dict) -> str:
    out = ["R598 逐枚处置台账（全部现读，枚数不写死）"]
    main = report["main"]
    out.append(
        "  主口径   : 题源 {0} 行 / {1} 个锚词；查无出处 行 {2} == 词 {3}（指纹 {4}）；"
        "丙案点名 {5}；行数==丙案枚数 {6}".format(
            main["fixture_rows"], main["term_total"], main["missing_rows"], main["missing_terms"],
            main["fingerprint_rows_equals_terms"], main["unscorable_n"],
            main["missing_equals_unscorable"]))
    out.append("  分母     : correctness = {0} - {1} = {2}（现算）".format(
        main["fixture_rows"], main["unscorable_n"],
        main["fixture_rows"] - main["unscorable_n"]))
    cons = report["conservation"]
    out.append(
        "  守恒     : 基点 {0} blob 可读={1}；行数等={2}；id 序等={3}；改题落地枚 {4}{5}".format(
            cons["base_rev"], cons["base_blob_readable"], cons["row_count_matches_base"],
            cons["id_order_matches_base"], len(cons["retitled_ids"]),
            "（" + "、".join(cons["retitled_ids"]) + "）" if cons["retitled_ids"] else ""))
    out.append("  违规     : {0}".format(cons["violations"] or "无"))
    csv = report["csv_hypothesis"]
    out.append(
        "  CSV假想  : 主口径缺 {0} 枚 → 采纳 CSV 仍缺 {1} 枚；救回 {2} 枚 {3}；"
        "分母 {4} → {5}".format(
            csv["main_missing_rows"], csv["csv_caliber_missing_rows"], csv["rescued_n"],
            csv["rescued_ids"] or "（一枚没有）", csv["denominator_before"],
            csv["denominator_after_hypothesis"]))
    out.append("             {0}".format(csv["note"]))
    out.append("")
    out.append("  逐枚处置（{0} 枚）：".format(len(report["dispositions"])))
    for item in report["dispositions"]:
        out.append("    {0}  [{1}]  缺词={2}".format(item["id"], item["bucket"], item["missing_term"]))
        out.append("        处置：{0}".format(item["today_action"]))
        out.append("        去向：{0}".format(item["pool"]))
    chat = report["chat10"]
    out.append("")
    out.append("  第三组现查（住宿超标 需审批 vs 自理）：{0} question={1} answer={2} 在 19 枚里={3}".format(
        chat["id"], chat["question"], chat["answer"], chat["in_the_unscorable_19"]))
    out.append("        判词：{0}".format(chat["verdict"]))
    return "\n".join(out)


def build_report(root: Path = REPO_ROOT) -> dict:
    return {
        "repo_root": str(root),
        "main": coverage_reading(root),
        "csv_caliber": coverage_reading(root, include_csv=True),
        "csv_hypothesis": csv_hypothesis(root),
        "conservation": conservation(root),
        "dispositions": disposition_table(root),
        "chat10": chat10_reading(root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R598 逐枚处置台账（只读，零模型零网络零连库）")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--json", dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    report = build_report(root)
    print(render(report))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cons = report["conservation"]
    main_reading = report["main"]
    ok = (
        not cons["violations"]
        and main_reading["fingerprint_rows_equals_terms"]
        and main_reading["missing_equals_unscorable"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())