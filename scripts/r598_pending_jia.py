"""R598 · 待授权的那一枚甲（doc-17）：凭据全套备好，🔴 本单**没有**让它落地。

【为什么备而不落】
跟进单 §160.4 判据⑤把守卫重录限定在两枚件上（`tests/test_evaluation_report.py`、
`tests/test_r94_eval_evidence_coverage.py`）。而丙→甲在任何一枚题上落地，都会打爆**写域外**的
`tests/test_r401_unscorable_rows_are_named_not_dropped.py`——那枚件把「丙案 19 枚 / 分母 86」硬编码
在 8 个断言里（:95 :96 :140 :150 :151 :154 :165 :184 :299 :306），且 :107/:110-113 正是「丙案铁规」钉，
封死了「丙案行偷偷带出处」这条捷径。执行层不许越界改它，也不许为了绕开它而半落半不落地改题源
（半落地会让 R401 件自己的对账 `verify()` 红），所以本单交的是：
  1. 判据结论（真互斥 ⇒ 按判据③的逃生口保持丙，并把「改语料不是改金标」写进交付检查项）；
  2. 一份**可复跑**的甲案凭据（本件）：锚词派生、反证样本、临时副本上的全套绿数——
     总控若要采纳甲，跑 `--apply-to` 指到副本先看数，再由总控授权重录那枚域外件。

【判据结论的凭据（本件现读，不抄纸面）】
A 桶两枚的冲突双方与「语料内部有没有仲裁指针」全部由 `conflict_evidence()` 从 documents/ 现读：
登记表§〇.3 明写「涉及金额标准、**票据要求**、审批权限的，一律以既有制度为准」——即登记表**放弃**
对票据要求作仲裁；t-04 那条虽点名《差旅费报销细则（2026 版）》，其事项是「发票抬头**开错**」（退回
重开），不是「住宿发票该开谁的抬头」。⇒ 两篇制度之间没有第三方指针 ⇒ 真互斥成立。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path("scripts") / "r598_disposition_ledger.py"
R401_REL = Path("scripts") / "r401_anchor_provenance.py"
MASTER_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"
CORPUS_REL = Path("documents")


_LOADED: dict[tuple[str, str], object] = {}


def _load(name: str, path: Path):
    """同 `_load_module`：一份尺子只 Exec 一次，异常类型身份必须与量具同源（见台账件注释）。"""
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


def default_workdir() -> Path:
    """影子根的默认落点：系统临时目录里的一枚专属文件夹（带 pid 防同机互踩）。"""
    return Path(tempfile.gettempdir()) / "r598-probe-{0}".format(os.getpid())


def deps(root: Path = REPO_ROOT) -> dict:
    ledger = _load("r598_ledger_for_pending", root / LEDGER_REL)
    r401 = _load("r401_for_pending", root / R401_REL)
    dd = ledger.load_deps(root)
    return {"ledger": ledger, "r401": r401, "cov": dd["cov"], "ev": dd["ev"]}


#: 待授权的甲案账（照 r401 DETAILS 的形状；sources 里只给「篇名 + 行号」这一枚人给的指针，
#: 其余字节区间与原文一律由 r401.derive_record 现算——判据③「禁手抄」的执行体是它，不是我）。
PENDING_JIA = {
    "doc-17": {
        "disposition": "甲",
        "fields": {
            "answer": "住宿发票抬头须为公司全称",
            "must_contain": ["须为公司全称"],
        },
        "sources": {"须为公司全称": ("差旅费报销细则_2026版.txt", 32)},
        "replaced_term": "公司抬头",
        "note": (
            "锚词取 6 字「须为公司全称」而不是 4 字「公司全称」＝**收紧**：R401 丙案理由记的三跑正文"
            "「可以开公司抬头或员工个人抬头」只要「公司全称」就会命中（把假阳性固化），要「须为公司全称」"
            "咬不住。判分器是裸子串 AND（app/quality/eval.py:_is_correct），本件的反证样本直接喂它。"
        ),
    },
}
PENDING_WRONG_ANSWERS = {
    "doc-17": [
        "住宿发票可以开公司抬头，也可以开员工个人抬头。",
        "未找到关于住宿发票抬头类型的规定。",
        "发票抬头一律为员工姓名，差旅类除外。",
    ],
}


def check_replaced_terms(root: Path = REPO_ROOT) -> dict:
    """判据③「replaced_term 从**现算缺口**取，禁手抄」的执行体。

    账里写的「被替换词」必须正好是今天覆盖度件为这一枚算出来的那一枚缺词：对不上就拒绝出数。
    🔴 这一把刀防的正是本单抓到的那个病（runbook:413 那句 ✅）——纸面抄的词与派生出来的词分叉。
    """
    ledger = deps(root)["ledger"]
    missing = ledger.coverage_reading(root)["missing_by_row"]
    out = {}
    for row_id, plan in PENDING_JIA.items():
        terms = missing.get(row_id)
        if terms is None:
            raise AssertionError(
                "{0} 在待授权账里等着被替换，可覆盖度件今天判它**有**出处 ⇒ 这本账过期了，"
                "要么它已被别人落地，要么名册已变，本件拒绝继续出数".format(row_id))
        claimed = str(plan["replaced_term"])
        if claimed not in terms:
            raise AssertionError(
                "{0} 的 replaced_term 记的是 {1!r}，今天现算缺的是 {2} ⇒ 手抄账与派生账分叉".format(
                    row_id, claimed, terms))
        out[row_id] = {"claimed": claimed, "derived_missing_terms": terms}
    return out


def conflict_evidence(root: Path = REPO_ROOT) -> dict:
    """A 桶逐字对账的凭据：两处冲突原文 + 登记表放弃仲裁的原文 + t-04 原文，全现读。"""
    lines = {}

    def grab(rel: str, number: int) -> str:
        text = (root / CORPUS_REL / rel).read_text(encoding="utf-8")
        return text.splitlines()[number - 1].strip()

    lines["差旅费报销细则_2026版.txt:32"] = grab("差旅费报销细则_2026版.txt", 32)
    lines["费用报销管理制度V2.1.txt:51"] = grab("费用报销管理制度V2.1.txt", 51)
    lines["费用报销管理制度V2.1.txt:65"] = grab("费用报销管理制度V2.1.txt", 65)
    lines["费用报销管理制度V2.1.txt:68"] = grab("费用报销管理制度V2.1.txt", 68)
    lines["企业管理制度手册.txt:65"] = grab("企业管理制度手册.txt", 65)
    lines["制度与口径登记表.txt:10"] = grab("制度与口径登记表.txt", 10)
    lines["制度与口径登记表.txt:42"] = grab("制度与口径登记表.txt", 42)
    lines["差旅费报销细则_2026版.txt:12"] = grab("差旅费报销细则_2026版.txt", 12)
    return {
        "doc-15": {
            "side_a": "费用报销管理制度V2.1.txt:65",
            "side_b": "企业管理制度手册.txt:65",
            "verdict": "真互斥·保持丙",
            "why": "两枚同为制度级条款（《费用报销管理制度》/《企业管理制度手册》），裁定规则「制度/细则条款 > "
                   "会议纪要/FAQ/过渡期安排」在两位同档对手之间无法仲裁；登记表§〇.3（:10）又把「票据要求」"
                   "整族推回既有制度，不做仲裁。总控提示的「过渡期（V2.1:68）与无需打印（V2.1:65）是两条不同"
                   "命题」为真（:68 讲的是 2025-06-30 前**纸质**发票仍可报销），但它不构成对 :65 vs 手册:65 "
                   "的仲裁 ⇒ 换任一边锚词都是替业主选边。",
        },
        "doc-17": {
            "side_a": "差旅费报销细则_2026版.txt:32",
            "side_b": "费用报销管理制度V2.1.txt:51",
            "verdict": "真互斥·保持丙（甲案凭据已备好，见 PENDING_JIA）",
            "why": "细则:32「发票抬头须为公司全称」与 V2.1:51「抬头为公司全称或员工姓名（仅限差旅、通讯、交通类）」"
                   "对「住宿发票」方向相反；两枚同为制度/细则级 ⇒ 裁定规则同档无法仲裁。登记表 t-04（:42）虽然把"
                   "「发票抬头」的依据点名给细则，但其事项是**抬头开错的处置**（一律退回重开），不是抬头**类型口径**；"
                   "而§〇.3（:10）明写本表不裁票据要求 ⇒ 不构成对本题的仲裁指针。金标「一律开具公司抬头」在两篇之间"
                   "无据，且三跑正文「可以开公司抬头或员工个人抬头」正是 V2.1:51 的合法读数 ⇒ 判丙，不许二选一硬翻绿。",
        },
        "chat-10": {
            "side_a": "差旅费报销细则_2026版.txt:12",
            "side_b": "（金标「需部门负责人审批」侧在 95 篇里无据：细则:30 那句「经部门负责人及分管领导审批」讲的是"
                      "**超 30 天延期**审批，不是住宿超标）",
            "verdict": "不在丙案名册·得分侧假阳性风险行·本单不动",
            "why": "锚词「部门负责人」到处有出处，覆盖度件判它有出处 ⇒ 它不进 19 枚、今天照旧进 correctness 分母；"
                   "但它考的命题与细则:12「超出部分自理」相反。动它会同时改 correctness 的历史可比性，且同属"
                   "「业主裁制度」那一族 ⇒ 与 doc-15/doc-17 一起裁，本单只点名不落地。",
        },
        "lines": lines,
    }


def planned_rows(root: Path, rows: list[dict], cov, r401) -> tuple[list[dict], dict]:
    """把待授权的甲落到**内存里的一副本**：出处由 r401.derive_record 现算，一个字节都不手抄。"""
    corpus = r401.corpus_by_name(root)
    out = []
    proofs = {}
    by_id = {str(row["id"]): row for row in rows}
    for row in rows:
        row_id = str(row["id"])
        plan = PENDING_JIA.get(row_id)
        if plan is None:
            out.append(row)
            continue
        current = by_id[row_id]
        records = r401.provenance_for_row(
            corpus, row_id, list(plan["fields"]["must_contain"]), plan["sources"])
        new_row = dict(current)
        new_row["answer"] = plan["fields"]["answer"]
        new_row["must_contain"] = list(plan["fields"]["must_contain"])
        new_row["anchor_provenance"] = records
        marker = dict(current.get("r401") or {})
        marker.update({
            "disposition": "甲",
            "reason": plan["note"],
            "replaced_term": plan["replaced_term"],
            "pool": "无（R598 待授权账：真互斥已裁丙 ⇒ 本条只备凭据）",
            "pre": {
                "question": current["question"],
                "answer": current["answer"],
                "must_contain": list(current["must_contain"]),
            },
        })
        marker.pop("missing_term", None)
        new_row["r401"] = marker
        proofs[row_id] = {
            "derived_records": records,
            "claimed_sources": {k: list(v) for k, v in plan["sources"].items()},
        }
        out.append(new_row)
    return out, proofs


def judge_proof(root: Path, rows: list[dict], ev, r401) -> dict:
    """反证腿：金标自己得过；错答样本喂**真判分器**必须不命中。"""
    by_id = {str(row["id"]): row for row in rows}
    out = {}
    for row_id, plan in PENDING_JIA.items():
        row = by_id[row_id]
        samples = PENDING_WRONG_ANSWERS[row_id]
        out[row_id] = {
            "gold_passes": ev._is_correct(row, {"answer": str(row["answer"])}),
            "samples": [
                {"sample": sample, "hit": bool(ev._is_correct(row, {"answer": sample}))}
                for sample in samples
            ],
        }
        if not out[row_id]["gold_passes"]:
            raise AssertionError("{0} 连自己的金标都判不过：锚词把题目判死了".format(row_id))
        hits = [item["sample"] for item in out[row_id]["samples"] if item["hit"]]
        if hits:
            raise AssertionError(
                "{0} 的新锚词被错答命中（{1}）：这一枚只是把缺口换了个形状".format(row_id, "；".join(hits)))
    return out


def make_probe_root(root: Path, workdir: Path, rows: list[dict]) -> Path:
    """最小影子根：documents/ + 改过的题源。🔴 仓库盘面一个字节不动，甲只活在影子里。"""
    probe = workdir / "probe"
    if probe.exists():
        shutil.rmtree(probe)
    (probe / MASTER_REL.parent).mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / CORPUS_REL, probe / CORPUS_REL)
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\r\n" for row in rows
    )
    (probe / MASTER_REL).write_bytes(body.encode("utf-8"))
    return probe


def proof(root: Path = REPO_ROOT, workdir: Path | None = None) -> dict:
    """把待授权的甲放进影子根跑一遍全套数：改前 19 → 改后 18；指纹不破；守恒不违规；判分器反证过。"""
    dd = deps(root)
    ledger, r401 = dd["ledger"], dd["r401"]
    replaced = check_replaced_terms(root)
    rows = ledger.read_rows(root)
    base = ledger.base_rows(root)
    before = ledger.coverage_reading(root)
    planned, proofs = planned_rows(root, rows, dd["cov"], r401)
    #: 影子根永远落系统临时目录：仓库盘面（含未跟踪清单）不允许因这把试跑多出目录。
    workdir = Path(workdir) if workdir else default_workdir()
    workdir.mkdir(parents=True, exist_ok=True)
    probe = make_probe_root(root, workdir, planned)
    after = ledger.coverage_reading(probe)
    judge = judge_proof(probe, planned, dd["ev"], r401)
    drift_report = (
        ledger.conservation_between(base, planned)
        if base is not None
        else {"violations": ["基点 {0} 的题源 blob 读不出来".format(ledger.BASE_REV)],
              "retitled_ids": []}
    )
    drift = drift_report["violations"]
    touched = [row_id for row_id in proofs]
    out = {
        "replaced_term_ledger": replaced,
        "before": {k: before[k] for k in ("missing_rows", "missing_terms", "unscorable_n",
                                          "fingerprint_rows_equals_terms", "missing_equals_unscorable")},
        "after": {k: after[k] for k in ("missing_rows", "missing_terms", "unscorable_n",
                                        "fingerprint_rows_equals_terms", "missing_equals_unscorable")},
        "denominator": {"before": before["fixture_rows"] - before["unscorable_n"],
                        "after": after["fixture_rows"] - after["unscorable_n"]},
        "retitled_ids": touched,
        "conservation_now_vs_base": drift_report,
        "conservation_drift": drift,
        "derived_provenance": proofs,
        "judge_counter_evidence": judge,
        "probe_root": str(probe),
        "domain_note": (
            "影子根上的数：甲落地会把「查无出处」从 {0} 枚降到 {1} 枚、分母从 {2} 抬到 {3}；"
            "本单没有把它落到仓库题源，域外件 test_r401_unscorable_rows_are_named_not_dropped.py "
            "的 19/86 硬编码还钉着，动它要总控授权。"
        ).format(before["missing_rows"], after["missing_rows"],
                 before["fixture_rows"] - before["unscorable_n"],
                 after["fixture_rows"] - after["unscorable_n"]),
    }
    shutil.rmtree(probe, ignore_errors=True)
    return out


def apply_to_copy(root: Path, dst: Path, *, hold_authorization: bool = False) -> dict:
    """把带甲的整套 105 行写到 **dst**；🔴 dst 默认不许是仓库题源（判据⑤）。

    要往盘面落这一枚，必须显式带 `--i-hold-authorization`，也就是总控已经把 §4 点名的
    那 6＋5 处域外硬编码重录完毕。没有那枚旗标，本函数只往副本写，一次盘面写入都不发。
    """
    shipped = (root / MASTER_REL).resolve()
    if dst.resolve() == shipped and not hold_authorization:
        raise SystemExit(
            "拒绝写仓库题源：判据⑤要求先由总控授权重录域外件（见交工纸 §4 那 6 枚函数），再谈落地。"
            "要落这一枚，先跑 --proof 看影子根的数。")
    dd = deps(root)
    planned, proofs = planned_rows(root, dd["ledger"].read_rows(root), dd["cov"], dd["r401"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\r\n" for row in planned
    )
    dst.write_bytes(body.encode("utf-8"))
    return {"dst": str(dst), "rows": len(planned), "retitled_ids": sorted(proofs)}


def render(report: dict) -> str:
    before, after = report["before"], report["after"]
    out = ["R598 待授权甲案·影子根试跑（仓库盘面零写入）"]
    for label, key in (("改前（盘面）", before), ("改后（影子）", after)):
        out.append(
            "  {0} : 查无出处 行 {1} / 词 {2}（指纹 {3}）；丙案点名 {4}；行==丙 {5}".format(
                label, key["missing_rows"], key["missing_terms"],
                key["fingerprint_rows_equals_terms"], key["unscorable_n"],
                key["missing_equals_unscorable"]))
    out.append("  correctness 分母 : {0} → {1}".format(
        report["denominator"]["before"], report["denominator"]["after"]))
    out.append("  落地枚 : {0}".format(report["retitled_ids"] or "（无）"))
    cons = report["conservation_now_vs_base"]
    out.append(
        "  守恒漂移 : {0}（改题枚 {1}；丙案被动枚 {2}；行数等 {3}；id 序等 {4}）".format(
            report["conservation_drift"] or "无（tier/category/丙案铁规全守住）",
            cons["retitled_ids"] or "无", cons["unscorable_touched_ids"] or "无",
            cons["row_count_matches_base"], cons["id_order_matches_base"]))
    for row_id, info in report["derived_provenance"].items():
        for record in info["derived_records"]:
            out.append("  派生出处 {0} : {1}:{2} 字节({3},{4}) 命中1次".format(
                row_id, record["path"], record["raw_line_number"],
                record["normalized_byte_start"], record["normalized_byte_length"]))
            out.append("    原文 : {0}".format(record["raw_line"]))
    for row_id, judge in report["judge_counter_evidence"].items():
        out.append("  判分器反证 {0} : 金标过={1}".format(row_id, judge["gold_passes"]))
        for item in judge["samples"]:
            out.append("    错答 {0!r} → 命中={1}（须 False）".format(item["sample"], item["hit"]))
    out.append("  {0}".format(report["domain_note"]))
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R598 待授权甲案（默认只出凭据，不落地）")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--proof", action="store_true", help="影子根试跑全套数（默认动作）")
    parser.add_argument("--conflict", action="store_true", help="只出 A 桶逐字对账凭据")
    parser.add_argument("--replaced", action="store_true", help="只出现算缺口对账（禁手抄那把刀的执行体）")
    parser.add_argument("--apply-to", help="把带甲的 105 行写到该路径（默认拒绝仓库题源）")
    parser.add_argument("--i-hold-authorization", dest="hold_authorization", action="store_true",
                        help="声明总控已重录 §4 那批域外硬编码；只有带着它才允许写仓库题源")
    parser.add_argument("--workdir", help="影子根落点（默认 %TEMP%）")
    parser.add_argument("--json", dest="json_path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    workdir = Path(args.workdir) if args.workdir else default_workdir()
    if args.replaced:
        print(json.dumps(check_replaced_terms(root), ensure_ascii=False, indent=2))
        return 0
    if args.conflict:
        print(json.dumps(conflict_evidence(root), ensure_ascii=False, indent=2))
        return 0
    if args.apply_to:
        info = apply_to_copy(root, Path(args.apply_to), hold_authorization=args.hold_authorization)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    report = proof(root, workdir)
    print(render(report))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = (
        report["after"]["missing_rows"] == report["before"]["missing_rows"] - len(PENDING_JIA)
        and report["after"]["missing_terms"] == report["after"]["missing_rows"]
        and not report["conservation_drift"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
