"""R387 回填量具：判据③ 说"回填就是写生产数据，属业主动作，必须先量后批"——本件就是那份"量"。

🔴 本件**一行业务数据都不写**：它只读 catalog 的显示文件名，按 `r387_label_lineage.DEPARTMENT_HINTS`
那套公开口径算出"如果批准按文件名回填，会写成什么样"，并把必须人工裁决的那部分单独列出来。
批准与否、写不写、由谁写，全部留给业主（计划书 §8.3 同一条口径：开关与数据变更属业主动作）。

它回答三格：
① 可自动回填的有多少枚文档 / 多少枚 chunk（文件名只指向唯一部门）；
② 必须人工裁决的有多少（一枚文件名指向多枚部门，或压根不指向任何部门）；
③ 回填之后部门这条腿**够不够格**当验收 C 的语料 —— 判据仍然是 `classify_arm` 那一枚，本件不重造判序。

用法::

    python scripts/r387_backfill_estimate.py --database-url "$DATABASE_URL"
    python scripts/r387_backfill_estimate.py --no-db --names-file names.txt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r387_label_lineage import (  # noqa: E402  —— 同目录取件，判序与口径只此一份
    ArmReading,
    classify_arm,
    hint_departments,
    read_postgres,
)

#: 验收 C 对语料的最低形状要求（判据④）。它写在这里，是为了让"够不够"这件事有个可核对的数，
#: 而不是一句"看起来差不多了"。数值来源：沙盒 `eb_r59_sandbox` 今天实际在位的分布
#: （4 部门 × 4 密级 × 252 枚，`scripts/r59c_sandbox_corpus.py` 的合成口径）。
MIN_DEPARTMENTS = 2
MIN_CLASSIFICATIONS = 2

#: 主体侧为空时顶上用的占位值：它不是部门名，判据只看「非空」那一件（理由见 unlock_ladder）。
_PRINCIPAL_PLACEHOLDER = "(主体侧按 A1 已补的口径给)"


def plan_from_names(name_to_chunks: dict) -> dict:
    """把 (显示文件名 -> chunk 枚数) 折成一份回填计划草案 + 必须人工裁决的清单。"""
    automatic: dict = {}
    ambiguous: dict = {}
    unhinted: dict = {}
    for name, chunks in sorted(name_to_chunks.items()):
        hits = hint_departments(name)
        if not hits:
            unhinted[name] = int(chunks)
        elif len(hits) == 1:
            automatic[hits[0]] = automatic.get(hits[0], {"files": 0, "chunks": 0})
            automatic[hits[0]]["files"] += 1
            automatic[hits[0]]["chunks"] += int(chunks)
        else:
            ambiguous[name] = {"departments": hits, "chunks": int(chunks)}
    total_chunks = sum(int(chunks) for chunks in name_to_chunks.values())
    auto_chunks = sum(item["chunks"] for item in automatic.values())
    manual_chunks = sum(item["chunks"] for item in ambiguous.values()) + sum(unhinted.values())
    return {
        "total_files": len(name_to_chunks),
        "total_chunks": total_chunks,
        "automatic": {key: value for key, value in sorted(automatic.items())},
        "automatic_files": sum(item["files"] for item in automatic.values()),
        "automatic_chunks": auto_chunks,
        "manual_review_files": len(ambiguous) + len(unhinted),
        "manual_review_chunks": manual_chunks,
        "ambiguous": ambiguous,
        "unhinted": unhinted,
        "departments_reachable_by_rule": sorted(automatic),
    }


def feasibility_after(plan: dict, existing_classifications: int) -> dict:
    """回填之后，这条腿能不能被判成"已验"？判序仍归 `classify_arm`。

    🔴 这里刻意 `recalled=0`：回填只解决"谓词不再是空集"，它不证明召回非空。
    所以今天这份计划的必然结论是未验，除非有人另跑一轮真召回测量。
    """
    departments = tuple(plan["departments_reachable_by_rule"])
    arm = ArmReading(
        name="after-backfill-from-filename-rule",
        principal_departments=departments,
        principal_clearance=3,
        corpus_labelled_chunks=plan["automatic_chunks"],
        corpus_departments=departments,
        corpus_classifications=tuple(str(value) for value in range(1, existing_classifications + 1)),
        recalled=0,
        breaches=0,
    )
    return {"arm": arm.as_dict(), "verdict": classify_arm(arm)}


# ---------------------------------------------------------------------------
# 解锁梯：验收 C 那四件可失败判据，一件一件挪开之后，判词会停在哪一格。
#
# 🔴 判序不在这里重造：每一级只是一枚 ``ArmReading``，判词一律由
# ``r387_label_lineage.classify_arm`` 现给。``moved`` 写清这一级挪开了哪一件，
# ``status`` 明写这一行是「现读」还是「推演（待量）」—— 推演行不是测量结果，
# 尤其不证明召回。文档里那张梯级表抄的是这里的判词，不是自己编的因果。
# ---------------------------------------------------------------------------

#: 主体侧口径：全梯统一按「A1 已补」的形状给。量的是**语料侧**那三件；主体侧给空
#: 会把每一级都判成 ``REASON_PRINCIPAL_UNSCOPED``，那张表就读不出"下一级堵在哪"了。
def _corpus_arm(rung: str, departments, *, labelled: int, kinds: int,
                recalled: int = 0, breaches: int = 0) -> ArmReading:
    return ArmReading(
        name=rung,
        principal_departments=tuple(departments) or (_PRINCIPAL_PLACEHOLDER,),
        principal_clearance=3,
        corpus_labelled_chunks=labelled,
        corpus_departments=tuple(departments),
        corpus_classifications=tuple(str(value) for value in range(1, kinds + 1)),
        recalled=recalled,
        breaches=breaches,
    )


def unlock_ladder(plan: dict, classification_kinds: int = 1) -> list:
    """把"回填能把验收 C 推到哪一格"摊成一张可复跑的梯级账（零写入，纯推演）。

    读法：从上往下找**第一行判词变好的**，那就是当前唯一挡路的格子；它前面所有行
    判词相同，说明那些动作对这一格没有推进力（S1/S2 就是这个形状 —— 它们治的是
    "以后别再漏"，不是"存量已经补上"）。
    """
    depts = tuple(plan["departments_reachable_by_rule"])
    kinds = max(int(classification_kinds), 1)
    total = int(plan["total_chunks"])
    auto = int(plan["automatic_chunks"])
    rungs = [
        ("S0", "今天：零动作", "现读",
         {"moved": "无", "labelled": 0, "departments": (), "kinds": kinds}),
        ("S1", "+A1 业主补 users.department", "推演（待量）",
         {"moved": "只影响**以后**的上传：服务端在上传那一跳覆盖，存量一个字都不动",
          "labelled": 0, "departments": (), "kinds": kinds}),
        ("S2", "+A2 上传时拒收空部门", "推演（待量）",
         {"moved": "止住新增漏标；存量仍 0 枚带部门",
          "labelled": 0, "departments": (), "kinds": kinds}),
        ("S3", "+A3 按文件名规则回填部门", "推演（待量）",
         {"moved": "语料侧带部门 0 -> %d 枚、部门 %d 枚" % (auto, len(depts)),
          "labelled": auto, "departments": depts, "kinds": kinds}),
        ("S3b", "+A3 之外再把人工裁决那部分也批了", "推演（待量）",
         {"moved": "带部门 %d -> %d 枚：覆盖率上去了，判词不动" % (auto, total),
          "labelled": total, "departments": depts, "kinds": kinds}),
        ("S4", "+密级也回填（业主逐档定密）", "推演（待量）",
         {"moved": "密级 1 档 -> 2 档：(b) 两件齐了，下一格堵在召回",
          "labelled": total, "departments": depts, "kinds": 2}),
        ("S5", "+在生产真标签上重跑四臂（召回非空、零越权）", "假想（要真测）",
         {"moved": "(c) 第一次由真测量交出读数",
          "labelled": total, "departments": depts, "kinds": 2, "recalled": total}),
        ("S6", "同 S5，但量出越权", "假想（要真测）",
         {"moved": "breaches > 0：判词改「不通过」，优先级压过一切未验理由",
          "labelled": total, "departments": depts, "kinds": 2, "recalled": total,
          "breaches": 1}),
    ]
    ladder = []
    for rung, action, status, spec in rungs:
        arm = _corpus_arm(rung, spec["departments"], labelled=spec["labelled"],
                          kinds=spec["kinds"], recalled=spec.get("recalled", 0),
                          breaches=spec.get("breaches", 0))
        ladder.append({"rung": rung, "action": action, "status": status,
                       "moved": spec["moved"], "arm": arm.as_dict(),
                       "verdict": classify_arm(arm)})
    return ladder


def render_ladder(ladder: list) -> list:
    return ["%-4s %-44s => %s —— %s" % (row["rung"], row["action"],
                                        row["verdict"]["verdict"],
                                        row["verdict"]["reason"])
            for row in ladder]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R387 回填量（只读，零写入）")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--expect-database", default="enterprise_brain")
    parser.add_argument("--names-file", default="", help="每行：文件名<TAB>chunk 枚数")
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--json", dest="out", default="")
    parser.add_argument("--classification-kinds", type=int, default=1,
                        help="密级档数的现读值：--no-db 时按这一格起算（默认 1 = 今天的生产形状）")
    parser.add_argument("--unlock-ladder", action="store_true",
                        help="打印验收 C 的解锁梯：一件一件挪开可失败判据，判词各停在哪一格")
    args = parser.parse_args(argv)

    name_to_chunks: dict = {}
    classifications = max(args.classification_kinds, 1)
    source = ""
    if not args.no_db:
        if not args.database_url:
            print("ABORT: 既没有 --database-url 也没有 --no-db/--names-file。", file=sys.stderr)
            return 2
        readings = read_postgres(args.database_url, args.expect_database)
        for row in readings["vector_catalog"]:
            name_to_chunks[row["filename"]] = int(row["chunks"] or 0)
        classifications = len(readings["chunk_vectors_classifications"])
        source = f"postgres:{readings['attached_database']}"
    elif args.names_file:
        for line in Path(args.names_file).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            name, _, count = line.partition("\t")
            name_to_chunks[name.strip()] = int(count.strip() or 0)
        source = args.names_file
    else:
        print("ABORT: --no-db 必须配 --names-file，否则本件无从量起。", file=sys.stderr)
        return 2

    plan = plan_from_names(name_to_chunks)
    report = {
        "source": source,
        "writes_issued": 0,
        "plan": plan,
        "acceptance_c_after_backfill": feasibility_after(plan, classifications),
        "classification_kinds_read": classifications,
        "unlock_ladder": unlock_ladder(plan, classifications),
        "threshold_note": (
            f"验收 C 至少需要 {MIN_DEPARTMENTS} 枚部门与 {MIN_CLASSIFICATIONS} 档密级，"
            "并且必须另有一轮非空召回的测量；本件只量谓词，不量召回。"),
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(f"可自动回填 {plan['automatic_files']} 枚文档 / {plan['automatic_chunks']} 枚 chunk；"
          f"必须人工裁决 {plan['manual_review_files']} 枚文档 / {plan['manual_review_chunks']} 枚 chunk")
    print(f"规则可达部门：{plan['departments_reachable_by_rule']}")
    verdict = report["acceptance_c_after_backfill"]["verdict"]
    print(f"照这份计划回填之后，验收 C 的部门腿仍是：{verdict['verdict']} —— {verdict['reason']}")
    if args.unlock_ladder:
        print("--- 验收 C 解锁梯（判词一律由 classify_arm 现给；「推演/假想」行不是测量结果）---")
        for line in render_ladder(report["unlock_ladder"]):
            print(line)
    print("本件写入行数：0（回填属业主动作，先量后批）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
