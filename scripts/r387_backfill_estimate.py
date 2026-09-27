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
    python scripts/r387_backfill_estimate.py --no-db --emit-plan-table   # 渲染 §2.3（数据源用树内快照）
    python scripts/r387_backfill_estimate.py --no-db --verify-plan-table   # 逐字节核对文档那一块
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO_ROOT = Path(__file__).resolve().parents[1]

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


# ---------------------------------------------------------------------------
# R409：批准材料那一节（文档 §2.3）从今往后由命令给数
#
# 病：业主批 A3（按文件名规则回填部门）看的是 §2.3 那张表，而表里那批数是 R387 当时抄下来的
# 一次数。抄一遍就多一本账：同一份数据喂进本件，最重那一格后来读出来是另一枚数（这笔漂移
# 记在文档 §9.5，原文按「读数不追溯改写」留着）。于是批准材料上的数和它自己的量具读数不是
# 同一个数，而这格既没有锚也没有牙 —— 批下去的是一个没人能复跑的东西。
#
# 修法与 ``--unlock-ladder`` 同法同姿势：数只活在现读这一处，文档那一段是它的影子。
#   ``--emit-plan-table``   把渲染结果打到 stdout（纯 markdown，别的一个字节都不出）
#   ``--verify-plan-table`` 逐字节比对文档里那一对标记之间的内容
#   ``--write-plan-table``  用现读渲染重落地那一块（只改文档，不碰数据）
# 三枚都只吃数据源，不发一条 SQL。两本账吃同一枚 ``plan``：这里印的数与梯级账里的数
# 出自同一次分桶，谁也不许另起口径。
#
# 取不到就当场喊，不许静默交出半张表：数据源读不出行、桶没盖住全部、文档里那一对标记不唯一、
# 文档带裸 LF ⇒ 非零退出 + stderr 报名字 + stdout 一个字节都不出。
# ---------------------------------------------------------------------------

#: 渲染落点与数据源。数据源是那批「显示文件名 -> chunk 枚数」的只读导出，必须收在树里：
#: 落在 %TEMP% 上就等于「只有那一台机器能复跑」，而批准材料要的是谁都能重跑一遍。
#: 导法（一条只读 psql）见本文档 §7。
PLAN_TABLE_DOC_REL = "docs/perf/r387-label-lineage-2026-09-27.md"
NAMES_SNAPSHOT_REL = "docs/perf/raw/r387-backfill-names-2026-09-27.tsv"

#: 判定依据的出处：那是标签，不是读数。挪到模块级，渲染函数里就不留任何连号数字。
HINT_RULE_LABEL = "scripts/r387_label_lineage.py::DEPARTMENT_HINTS"

BLOCK_BEGIN = ("<!-- R409:BEGIN 本块由 "
               "`python scripts/r387_backfill_estimate.py --no-db "
               "--names-file <数据源> --emit-plan-table` 渲染，一个字都不许手抄 -->")
BLOCK_END = "<!-- R409:END -->"


class PlanTableAnchorError(Exception):
    """文档里那一对渲染标记不唯一 / 形状不对：这是「取不到」，不是「交一张旧表」。"""


def plan_table_buckets(plan: dict) -> list:
    """三段桶表：每一格的文档数与 chunk 数都从 ``plan`` 现取，桶名是人话、不含数。"""
    ambiguous_chunks = sum(int(item["chunks"]) for item in plan["ambiguous"].values())
    unhinted_chunks = sum(int(value) for value in plan["unhinted"].values())
    return [
        ("文件名只指向**唯一**一枚部门（可规则回填）", plan["automatic_files"], plan["automatic_chunks"]),
        ("文件名指向**多枚**部门（必须人工裁决）", len(plan["ambiguous"]), ambiguous_chunks),
        ("文件名**不给任何**部门线索（必须人工裁决）", len(plan["unhinted"]), unhinted_chunks),
        ("必须人工裁决小计", plan["manual_review_files"], plan["manual_review_chunks"]),
        ("合计（= 数据源行数 / 枚数）", plan["total_files"], plan["total_chunks"]),
    ]


def plan_table_departments(plan: dict) -> list:
    """规则可达部门按 chunk 降序、同数按部门名升序：两枚排序键都确定，并列时也不会偶然换序。"""
    rows = [[dept, int(item["files"]), int(item["chunks"])]
            for dept, item in plan["automatic"].items()]
    return sorted(rows, key=lambda row: (-row[2], -row[1], row[0]))


def plan_table_manual(plan: dict) -> list:
    """多归属清单按显示文件名升序（``plan`` 里已是 sorted 插入，这里再排一次，不依赖字典序）。"""
    return sorted([[name, int(item["chunks"]), "｜".join(item["departments"])]
                   for name, item in plan["ambiguous"].items()])


def percent(part: int, whole: int) -> str:
    """占比写成百分数：乘一百那一步交给格式化符号，源码里因此不出现任何计数常量。"""
    if not whole:
        return "算不出来（分母为零）"
    return "{:.1%}".format(part / whole)


def source_label(source: str) -> str:
    """块里印的路径必须跨机器可复跑：树内的绝对路径折成仓库相对 POSIX 路径，树外原样。"""
    path = Path(source)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return source
    return path.as_posix()


def render_plan_table(plan: dict, source: str) -> list:
    """把 §2.3 那一节渲染成 markdown 行。🔴 这里不许出现任何一枚计数常量。"""
    buckets = plan_table_buckets(plan)
    departments = plan_table_departments(plan)
    manual = plan_table_manual(plan)
    auto_chunks = int(plan["automatic_chunks"])
    total_chunks = int(plan["total_chunks"])
    lines = [
        "数据源：`%s` —— 只读导出的「显示文件名 → chunk 枚数」，逐行按制表符分列现读，"
        "本件不发一条 SQL、不写一行数据。" % source_label(source),
        "",
        "判定依据：`%s`（公开口径：文件名里出现某枚 "
        "token 就记一枚命中）。命中唯一 = 可规则回填；命中多枚或零枚 = 必须人工裁决。这一口径量的是"
        "「语义上像属于谁」，🔴 **不是权威**，回填前由业主逐格确认；判词一律出自 `classify_arm`，本件不重造判序。" % HINT_RULE_LABEL,
        "",
        "| 量（每一格现读） | 文档 | chunk | 占合计 |",
        "|---|---|---|---|",
    ]
    for name, files, chunks in buckets:
        if name.startswith("合计") or name.startswith("必须人工裁决小计"):
            lines.append("| %s | %s | %s | %s |" % (name, files, chunks, percent(chunks, total_chunks)))
        else:
            lines.append("| %s | **%s** | **%s** | %s |"
                         % (name, files, chunks, percent(chunks, total_chunks)))
    lines += [
        "",
        "规则可达部门 **%s** 枚，按 chunk 降序（同数按部门名升序；同一枚数据源两次渲染逐字节相等）："
        % len(departments),
        "",
    ]
    if departments:
        lines += ["| 部门 | 文档 | chunk | 占可回填 |", "|---|---|---|---|"]
        for dept, files, chunks in departments:
            lines.append("| `%s` | %s | %s | %s |" % (dept, files, chunks, percent(chunks, auto_chunks)))
        heaviest = departments[0]
        second = departments[1] if len(departments) > 1 else None
        tail = "" if second is None else "，次重 `%s` = %s 枚文档 / %s 枚 chunk" % (
            second[0], second[1], second[2])
        lines += [
            "",
            "🔴 回填出来的分布并不均衡：最重一格 `%s` = **%s 枚文档 / %s 枚 chunk**（占可回填的 %s）%s。"
            "**「规则可达 %s 枚部门」不等于「%s 家都覆盖到了」** —— 这句话必须跟着批准材料一起走。"
            % (heaviest[0], heaviest[1], heaviest[2], percent(heaviest[2], auto_chunks),
               tail, len(departments), len(departments)),
        ]
    else:
        lines += ["", "规则一枚部门都没够到：上面那格是 0，不是「量具没跑」。"]
    lines += [
        "",
        "必须人工裁决的多归属清单（按显示文件名升序；「命中部门」就是规则给出的全部线索）：",
        "",
        "| 显示文件名 | chunk | 命中部门 |",
        "|---|---|---|",
    ]
    for name, chunks, departments_hit in manual:
        lines.append("| `%s` | %s | %s |" % (name, chunks, departments_hit))
    unhinted = buckets[2]  # 同一本桶账的第三段：不另算一遍，免得两处口径分家
    lines += [
        "",
        "零线索的那 %s 枚文档 / %s 枚 chunk 不在这里逐枚列（清单在本件 `--json` 输出的 `plan.unhinted` "
        "里，同样是现读）：它们与上面这些一样，规则给不出部门，只能业主点名。" % (unhinted[1], unhinted[2]),
        "",
        "🔴 本块只声明**能回填多少**，不声明回填之后验收 C 判什么：那本账在文档 §9.5 的解锁梯"
        "（`--unlock-ladder` 现跑），两处吃的是同一次分桶。渲染不带时间戳 —— 加了就没有逐字节可复现；"
        "数由数据源决定，数据源由 §7 那条只读命令重导。",
    ]
    return lines


def plan_table_block(plan: dict, source: str) -> list:
    """渲染结果 + 那一对标记：文档里被替换的正是这一整块（含标记本身）。"""
    return [BLOCK_BEGIN] + render_plan_table(plan, source) + [BLOCK_END]


def plan_table_guard(plan: dict) -> str:
    """出账前的自检：交回一句话 = 取不到的原因；空串 = 这份读数成得出账。"""
    if not plan or not int(plan.get("total_files") or 0):
        return "数据源里一枚文档都没有，无从量起"
    if int(plan["automatic_files"]) + int(plan["manual_review_files"]) != int(plan["total_files"]):
        return "三份桶没盖住文档：%s + %s != %s" % (
            plan["automatic_files"], plan["manual_review_files"], plan["total_files"])
    if int(plan["automatic_chunks"]) + int(plan["manual_review_chunks"]) != int(plan["total_chunks"]):
        return "三份桶没盖住 chunk：%s + %s != %s" % (
            plan["automatic_chunks"], plan["manual_review_chunks"], plan["total_chunks"])
    return ""


def replace_plan_block(text: str, block: list) -> str:
    """把渲染块塞回文档里那一对标记之间。标记不唯一就是「取不到」，不当场补投、也不追加第二块。"""
    if "\r\n" not in text:
        raise PlanTableAnchorError("文档不是纯 CRLF 的形状，拒绝就地改写")
    if [char for index, char in enumerate(text) if char == "\n" and text[index - 1] != "\r"]:
        raise PlanTableAnchorError("文档里混着裸 LF（行尾不纯），先修行尾再谈渲染")
    lines = text.split("\r\n")
    begins = [index for index, line in enumerate(lines) if line.strip() == BLOCK_BEGIN]
    ends = [index for index, line in enumerate(lines) if line.strip() == BLOCK_END]
    if len(begins) != 1 or len(ends) != 1 or ends[0] <= begins[0]:
        raise PlanTableAnchorError(
            "文档里找不到唯一的一对渲染标记（标记 BEGIN=%s END=%s，应当各命中一枚且成对）"
            % (len(begins), len(ends)))
    return "\r\n".join(lines[:begins[0]] + block + lines[ends[0] + 1:])


def read_names_file(path: str) -> dict:
    """读「显示文件名<TAB>chunk 枚数」。读不出一行、形状不对、同名两行打架 ⇒ 抛，不静默交空表。"""
    text = Path(path).read_text(encoding="utf-8")
    out: dict = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, sep, count = line.partition("\t")
        if not sep:
            raise ValueError("数据源不是「文件名<TAB>枚数」的形状：" + str(path))
        try:
            chunks = int(count.strip() or 0)
        except ValueError:
            raise ValueError("数据源里那行的枚数不是整数：" + str(path))
        name = name.strip()
        if not name:
            raise ValueError("数据源里有一行为空的文件名：" + str(path))
        if name in out and out[name] != chunks:
            raise ValueError("同一枚文件名在数据源里出现两次且枚数不等：" + name)
        out[name] = chunks
    if not out:
        raise ValueError("数据源里一行都没有：" + str(path))
    return out


def plan_table_cli(args, plan: dict, source: str) -> int:
    """``--emit-plan-table`` / ``--verify-plan-table`` / ``--write-plan-table`` 三条出口。"""
    problem = plan_table_guard(plan)
    if problem:
        print("ABORT: 批准材料取不到 —— " + problem, file=sys.stderr)
        print("本件写入行数：0（取不到就不出账）", file=sys.stderr)
        return 3
    block = plan_table_block(plan, source)
    if args.emit_plan_table:
        #: 交出去的就是文档里那一块的字节：行尾统一按 CRLF 直写，不让控制台编码与换行翻译插手
        #:（中文文件名经控制台编码换一遍，量具就会把同一枚文档读成两枚名字，见文档 §7 那条注释）。
        payload = ("\r\n".join(block) + "\r\n").encode("utf-8")
        stream = getattr(sys.stdout, "buffer", None)
        if stream is None:
            print(payload.decode("utf-8"), end="")
        else:
            stream.write(payload)
            stream.flush()
        print("本件写入行数：0（渲染只给文档那一节供数）", file=sys.stderr)
        return 0
    doc = Path(args.doc)
    if not doc.is_absolute():
        doc = REPO_ROOT / args.doc
    try:
        text = doc.read_bytes().decode("utf-8")
    except OSError as error:
        print("ABORT: 批准材料取不到 —— 文档读不出来 %s（%s）" % (doc, error), file=sys.stderr)
        return 3
    try:
        updated = replace_plan_block(text, block)
    except PlanTableAnchorError as error:
        print("ABORT: 批准材料取不到 —— " + str(error), file=sys.stderr)
        return 3
    if args.verify_plan_table:
        if updated == text:
            print("MATCH: %s 里那一块与现读渲染逐字节相等（渲染 %s 行）" % (args.doc, len(block)))
            return 0
        print("MISMATCH: %s 里那一块已经不是渲染产物（行数 %s -> %s）—— 要么重落地，要么承认它是手抄的"
              % (args.doc, len(text.split("\r\n")), len(updated.split("\r\n"))), file=sys.stderr)
        return 4
    if updated == text:
        print("NOCHANGE: %s 里那一块已经是现读渲染" % args.doc)
    else:
        doc.write_bytes(updated.encode("utf-8"))
        print("WROTE: %s 里那一块已按现读重落地（数据源 %s 一行未动）" % (args.doc, source_label(source)))
    print("本件写入行数：0（文档不是业务数据；库里的标签一格都没改）", file=sys.stderr)
    return 0

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
    parser.add_argument("--names-snapshot", default=NAMES_SNAPSHOT_REL,
                        help="批准材料渲染时用的数据源默认落点（只读导出，收在树里才谈得上复跑）")
    parser.add_argument("--emit-plan-table", action="store_true",
                        help="只把文档 §2.3 那一节的 markdown 打到 stdout（纯派生，别的一个字节都不出）")
    parser.add_argument("--verify-plan-table", action="store_true",
                        help="逐字节比对 --doc 里那一对标记之间的内容与现读渲染，不等就非零退出")
    parser.add_argument("--write-plan-table", action="store_true",
                        help="用现读渲染重落地 --doc 里那一块（只改文档，不碰数据、不碰库）")
    parser.add_argument("--doc", default=PLAN_TABLE_DOC_REL, help="批准材料所在的文档（仓库相对或绝对路径）")
    args = parser.parse_args(argv)

    plan_table_mode = args.emit_plan_table or args.verify_plan_table or args.write_plan_table
    if plan_table_mode and args.no_db and not args.names_file:
        #: 三条出口默认吃树内那枚只读导出快照（不是手抄，是数据）；换数据源就显式带 --names-file。
        args.names_file = str(REPO_ROOT / args.names_snapshot)
        print("NOTE: 没带 --names-file，改用树内快照 " + args.names_snapshot, file=sys.stderr)

    if plan_table_mode:
        if not args.no_db or not args.names_file:
            print("ABORT: 渲染批准材料必须走 --no-db --names-file/--names-snapshot，本件拒绝为了一张表去连库。",
                  file=sys.stderr)
            return 2
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
        try:
            name_to_chunks = read_names_file(args.names_file)
        except (OSError, ValueError) as error:
            #: 🔴 读不出就是读不出：非零退出 + 报名字 + 一张表都不交。静默交空表 = 假绿。
            print("ABORT: 批准材料取不到 —— 数据源 %s 读不出来（%s）" % (args.names_file, error),
                  file=sys.stderr)
            print("本件写入行数：0（取不到就不出账）", file=sys.stderr)
            return 3
        source = args.names_file
    else:
        print("ABORT: --no-db 必须配 --names-file，否则本件无从量起。", file=sys.stderr)
        return 2

    plan = plan_from_names(name_to_chunks)
    if args.emit_plan_table or args.verify_plan_table or args.write_plan_table:
        return plan_table_cli(args, plan, source)
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
