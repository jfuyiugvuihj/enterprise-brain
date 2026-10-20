# -*- coding: utf-8 -*-
"""R469 · C 门检索侧读数的判据本体与读数表生成器（纯离线：零库、零容器、零模型）。

为什么单独一枚件
----------------
跟进单 §133 六第一次量清真账：生产/演示库 `chunk_vectors` 1008/1008 全部 `department=''`、
`classification` 全为整数 `1`。于是 `app/rag/filters.py:47-52` 那道 `allows()` **没有东西可判**
⇒ 计划书 §9.3 那句「跨部门/跨密级命中 0 条」与阶段 C 那句「越权 0 条」在检索侧是**空集真**。
要把它变成有牙的读数，判据不能只住在纸上——每班手写一遍判读，就一定会有一班把空集抄成通过
（09-28 那枚 P-18「假零」是同一族病，跟进单 §133 二）。本件因此只做两件事，且一件都不碰库：

1. `judge(evidence)`：把驱动在容器里取回的原始读数（本文件渲染进 `docs/testing/r469-*.md`
   的那段围栏 JSON）逐档重判一遍。判定词只有五枚（`CELL_*`），越权、空集、失牙各归各的。
   「这一档有没有东西可判」由 `admits()` 现场问——默认问产品本体
   `app.rag.filters.DocumentRetrievalScope.allows`，本件不自建第二条权限规则。
2. `render_readout(evidence)`：读数表由本件生成，`validate_readout()` 拿盘上那份与再生件比字节。

反证的形状（`tests/test_r469_*.py` 逐把钉着；这里说清各咬什么）
------------------------------------------------------------
- 摘掉 `allows()`（恒 True）：每档的 `control` 格当场红——那格从池里点名一枚**已知越界**的行
  喂回判定，判定说「能看」就是红。这把咬的是**判定的牙**，不是召回。
- 旁路下推谓词（拿「无谓词那一臂」的命中冒充「有谓词那一臂」）：`j2_breaches` 立刻 > 0。
  这把咬的是**读数的形状**，且它只有在池里真有池外的料时才点得出名 ⇒ 同时证明本单的池非空集。
- 把标签抹成同值（全 `department=''`、全 `classification=1`）：所有格退回 `VACUOUS_EMPTY_SET`，
  整单 `NOT_MEASURED`——「越权 0 条」重新变成空集真。
- 存量恒量任一枚前后不同：`validate_readout()` 拒绝出表。
- 手改表格里的读数：字节对不上再生件。

边界（照抄计划书 §13.一，本件无权改口）：沙盒合成标签只证「谓词按标签行为」，**不证客户隔离**。
`judge()` 交回的状态词表里根本没有 GREEN 这一枚，就是为了让人抄不成。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: 与 scripts/r59c_sandbox_corpus.py:68-70 同一手法：本件离线跑，但要能 import 产品本体——
#: 判定必须由 app.rag.filters 那一条做，本件不复制第二条权限规则。
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TICKET = "R469"
EVIDENCE_SCHEMA = "r469-scope-readout-1"
DRIVER = "scripts/r469_sandbox_scope_readout.py"
TOOL = "scripts/r469_readout_lib.py"

#: 存量恒量的六枚表名（跟进单 §133 六点名的那六张；跑前跑后逐枚必须相同）。
CORE_INVARIANT_TABLES = (
    "chunk_vectors", "documents", "document_versions",
    "dataset_versions", "resource_versions", "users",
)

#: 逐格判定词表。只这五枚，别在别处造第六个说法。
CELL_MEASURED = "MEASURED_WITH_TEETH"      # 谓词有可选性、有池外材料可漏、实际一条没漏
CELL_VACUOUS = "VACUOUS_EMPTY_SET"         # 空集真：谓词全放行或全挡死，越权 0 条无从判
CELL_ZERO_RECALL = "ZERO_RECALL"           # 有可召的料而读腿一条没交回（选择性预过滤欠给）
CELL_RED_BREACH = "RED_BREACH"             # 真出现越权命中：不通过，且优先于「未验」
CELL_RED_CONTROL = "RED_CONTROL"           # 判定本身失去可判性（allows() 被摘/被旁路的形状）

#: 整单状态词表。没有 GREEN。
STATUS_MEASURED = "SANDBOX_MEASURED_PRODUCTION_UNVERIFIED"
STATUS_RED = "RED"
STATUS_NOT_MEASURED = "NOT_MEASURED"

PASS = "PASS"
PASS_SYNTH_ONLY = "PASS_SYNTH_ONLY"
FAIL = "FAIL"
UNVERIFIED = "未验"

#: 🔴 这句是业主与总控在册的原话，读数表与交回里都必须逐字在位，不许改写、不许删。
HONEST_BOUNDARY = (
    "沙盒标签只证「谓词按标签行为」，不证客户隔离；生产格③ 欠的是业主侧真实密级回填"
    "（A3 已裁「交付阶段按客户真实密级做」）。"
)
#: 交回里的第 7 条要求：这句也必须逐字在位。
NOT_CELL3_GREEN = "🔴 这不等于格③ 已翻绿，也不等于 C 门翻绿：格③ 在生产侧仍记「未验」。"

ARM_PRODUCTION = "production"
ARM_SANDBOX = "sandbox"
ARMS = (ARM_PRODUCTION, ARM_SANDBOX)

#: §13.一 那四件判据的名字，读数表照这四件交回，不另立第五件。
CRITERIA_KEYS = ("a_subject_department", "b_corpus_labels", "c_recall_positive",
                 "d_zero_breach")


class ReadoutError(AssertionError):
    """读数表与证据不一致、或证据自己不过关。和断言一样往外抛，由 CLI 转成退出码。"""


def product_admits(tier: dict, hit: dict) -> bool:
    """把记录在案的 scope 形状还原成产品那个类，再问它本人。

    本件不重写一条权限规则（AGENTS.md：不平行实现）。这里只做形状还原：`filters` /
    `reason_code` / `classification_levels` / `departments` 四枚字段都是驱动现场从
    `resolve_document_retrieval_scope(principal)` 抄下来的，判定仍走 `allows()` 那一条。
    """
    from app.rag.filters import DocumentRetrievalScope

    departments = tier.get("departments")
    scope = DocumentRetrievalScope(
        filters=tier["filters"],
        reason_code=tier["scope_reason"],
        classification_levels=frozenset(tier["levels"]),
        departments=None if departments is None else frozenset(departments),
    )
    return scope.allows(hit)


def pretty(values) -> str:
    """把一列取值拼成可读串；空部门要显式写成 <空串>，否则表里看着像少了一档。"""
    return "/".join("<空串>" if str(value) == "" else str(value) for value in values)


def hit_label(hit: dict) -> tuple:
    return (hit.get("classification"), str(hit.get("department") or ""))


def invariants_match(before: dict, after: dict) -> bool:
    """前后是否逐枚相同——由两本账现场算，不信任何一枚记录下来的 bool。"""
    if sorted(before) != sorted(after):
        return False
    return all(before[key] == after[key] for key in before)


def judge_tier(tier: dict, *, admits=product_admits) -> dict:
    """逐档重判一遍：J-1 可选性 / J-2 不越权 / J-3 与精确解一致 / 反证 control。

    判序（写死，别换顺序）：先看判定本身还有没有牙（control），再看有没有真越权（breaches），
    再看这一档可不可选（J-1），最后才看召回。「不通过」优先于「未验」——计划书 §13.一 那句
    "别让还没验淹掉已经漏了"，在这里就是前两条比后两条先出红。
    """
    pool_total = int(tier["pool_total"])
    admitted = int(tier["admitted_total"])
    outside = pool_total - admitted
    reads = tier["reads"]

    breaches: list = []
    counterfactual: list = []
    returned = 0
    short_reads = 0
    for read in reads:
        scoped = read["scoped"]
        returned += len(scoped)
        if len(scoped) < int(read["k"]):
            short_reads += 1
        for hit in scoped:
            if not admits(tier, hit):
                breaches.append(dict(hit, anchor=read["anchor"],
                                     why="out_of_scope_in_pushed_read"))
        for hit in read["unscoped"]:
            if not admits(tier, hit):
                counterfactual.append(dict(hit, anchor=read["anchor"],
                                           why="reachable_only_without_predicate"))

    sample = tier.get("outside_sample")
    control_available = sample is not None
    control_ok = (not control_available) or (not admits(tier, sample))

    j3 = {"judged": 0, "sets_equal": 0, "slots_equal": 0, "slots_total": 0,
          "missing": [], "extra": []}
    for read in reads:
        exact = read.get("exact")
        if exact is None:
            continue
        got = [hit["id"] for hit in read["scoped"]]
        want = list(exact)
        j3["judged"] += 1
        j3["slots_total"] += len(want)
        j3["slots_equal"] += sum(1 for left, right in zip(got, want) if left == right)
        if set(got) == set(want):
            j3["sets_equal"] += 1
            continue
        j3["missing"].extend({"anchor": read["anchor"], "id": item}
                             for item in want if item not in set(got))
        j3["extra"].extend({"anchor": read["anchor"], "id": item}
                           for item in got if item not in set(want))

    labels = sorted({hit_label(hit) for read in reads for hit in read["scoped"]})
    distinct_ids = sorted({hit["id"] for read in reads for hit in read["scoped"]})

    if control_available and not control_ok:
        cell, cell_why = CELL_RED_CONTROL, (
            "已知越界的一行被判定放行——这道闸门自己不再可判（allows() 被摘或被旁路的形状）")
    elif breaches:
        cell, cell_why = CELL_RED_BREACH, "出现 {0} 条越权命中".format(len(breaches))
    elif admitted == 0:
        cell, cell_why = CELL_VACUOUS, "谓词挡光整库：该臂恒空集，J-2 无从判"
    elif outside == 0:
        cell, cell_why = CELL_VACUOUS, "谓词一件没挡：越权 0 条是空集真，不是隔离正确"
    elif returned == 0:
        cell, cell_why = CELL_ZERO_RECALL, (
            "池里有 {0} 枚可召料而读腿一条没交回（短读数 {1} 次）".format(admitted, short_reads))
    else:
        cell, cell_why = CELL_MEASURED, (
            "越权 0 条，且无谓词对照里有 {0} 条本可越界——这一格的 0 是有牙的 0".format(
                len(counterfactual)))

    return {
        "label": tier["label"], "expect": tier["expect"], "role": tier["role"],
        "department": tier["department"], "clearance": tier["clearance"],
        "scope_reason": tier["scope_reason"], "levels": sorted(tier["levels"]),
        "departments": tier["departments"], "filters": tier["filters"],
        "pool_total": pool_total, "admitted_total": admitted, "outside_pool_total": outside,
        "admitted_share": round(admitted / pool_total, 4) if pool_total else 0.0,
        "queries": len(reads), "returned": returned, "short_reads": short_reads,
        "distinct_hits": len(distinct_ids), "hit_ids": distinct_ids,
        "hit_labels": [[level, department] for (level, department) in labels],
        "j1_selective": 0 < admitted < pool_total,
        "j2_breaches": breaches,
        "counterfactual_candidates": counterfactual,
        "counterfactual_total": len(counterfactual),
        "r59c_admitted_ids": tier.get("r59c_admitted_ids") or [],
        "j3": j3,
        "control": {"available": control_available, "sample": sample,
                    "rejected_by_allows": (None if not control_available else control_ok)},
        "cell": cell, "cell_why": cell_why,
    }


def judge_criteria(arm_name: str, arm: dict, evidence: dict, cells: list) -> dict:
    """§13.一 那四件可失败判据，逐件给读数与判定。判定词表：PASS / PASS_SYNTH_ONLY / FAIL / 未验。

    口径先说死：`production` 那一臂的主体是本单造的**合成 principal**，不是 `users` 表里的人，
    所以它的 (a) 只能引真账号的实测数——真账号那格今天仍然是空的，这一件在生产侧不成立。
    """
    accounts = evidence["invariants"].get("production_accounts") or {}
    restricted = [cell for cell in cells if cell["departments"]]
    with_hits = [cell for cell in cells if cell["returned"] > 0]
    breaches = sum(len(cell["j2_breaches"]) for cell in cells)
    vacuous = sum(1 for cell in cells if cell["cell"] == CELL_VACUOUS)
    labels = arm["pool_labels"]

    if arm_name == ARM_PRODUCTION:
        present = int(accounts.get("users_with_department") or 0)
        a = {
            "verdict": UNVERIFIED if present <= 1 else PASS,
            "reading": ("users 表 {0} 枚里 department 非空 {1} 枚；admin/evalbot 实测为空"
                        .format(accounts.get("users_total"), present)),
            "note": "本单主体是合成 principal，不代替真账号；真账号那一格未回填 ⇒ (a) 不成立",
        }
    else:
        a = {
            "verdict": PASS_SYNTH_ONLY if len(restricted) == len(cells) - 1 else FAIL,
            "reading": "{0}/{1} 档带部门谓词（管理员那档 departments=None 不计，§13.一 原话）"
                       .format(len(restricted), len(cells)),
            "note": "只证「主体带部门时谓词的行为」，不证客户侧真有人被回填了部门",
        }

    b_ok = (int(labels["nonempty_department"]) > 0
            and len(labels["distinct_departments"]) >= 2
            and len(labels["distinct_classifications"]) >= 2)
    b = {
        "verdict": PASS if b_ok else FAIL,
        "reading": ("非空 department {0}/{1} 枚；部门 {2} 档 [{3}]；密级 {4} 档 [{5}]；"
                    "(部门,密级) 叉乘 {6} 格（其中 r59c 合成语料 {7} 格）".format(
                        labels["nonempty_department"], labels["rows_total"],
                        len(labels["distinct_departments"]),
                        pretty(labels["distinct_departments"]),
                        len(labels["distinct_classifications"]),
                        pretty(labels["distinct_classifications"]),
                        labels["distinct_pairs"], labels["r59c_distinct_pairs"])),
        "note": "r59c 补的正是密级那一维：沙盒原有标签是 4 部门 × 各 1 档，同部门内跨密级不可判",
    }

    c = {
        "verdict": PASS if len(with_hits) == len(cells) else FAIL,
        "reading": "召回 > 0 的档 {0}/{1}：{2}".format(
            len(with_hits), len(cells),
            "/".join(cell["label"] for cell in with_hits) or "无"),
        "note": "",
    }

    if breaches:
        d = {"verdict": FAIL, "reading": "越权 {0} 条".format(breaches),
             "note": "不通过优先于未验"}
    elif vacuous == len(cells):
        d = {"verdict": UNVERIFIED, "reading": "逐档全是空集（挡光或全放行），越权 0 条无从判",
             "note": "这正是 §133 六那条真账的形状"}
    else:
        d = {"verdict": PASS if arm_name == ARM_SANDBOX else UNVERIFIED,
             "reading": "越权 0 条；池外可漏材料逐档 {0} 枚，无谓词对照命中里本可越界逐档 {1} 条"
                        "（合计 {2} 条）".format(
                            "/".join(str(cell["outside_pool_total"]) for cell in cells),
                            "/".join(str(cell["counterfactual_total"]) for cell in cells),
                            sum(cell["counterfactual_total"] for cell in cells)),
             "note": "合成标签上的行为读数，不证客户隔离" if arm_name == ARM_SANDBOX else ""}

    return {"a_subject_department": a, "b_corpus_labels": b,
            "c_recall_positive": c, "d_zero_breach": d}

def judge(evidence: dict, *, admits=product_admits) -> dict:
    """整单判定：逐臂逐档 + 四件判据 + 存量恒量复算 + 未过清单。"""
    arms_out: dict = {}
    red_cells: list = []
    for arm_name in ARMS:
        arm = evidence["arms"][arm_name]
        cells = [judge_tier(tier, admits=admits) for tier in arm["tiers"]]
        criteria = judge_criteria(arm_name, arm, evidence, cells)
        for cell in cells:
            if cell["cell"] in (CELL_RED_BREACH, CELL_RED_CONTROL):
                red_cells.append(dict(cell, arm=arm_name))
        if any(cell["cell"] in (CELL_RED_BREACH, CELL_RED_CONTROL) for cell in cells):
            arm_status = STATUS_RED
        elif any(cell["cell"] == CELL_MEASURED for cell in cells):
            arm_status = STATUS_MEASURED
        else:
            arm_status = STATUS_NOT_MEASURED
        arms_out[arm_name] = {
            "database": arm["database"], "pool_total": arm["pool_total"],
            "writes": arm.get("writes", 0), "status": arm_status,
            "tiers": cells, "criteria": criteria,
        }

    inv_report: dict = {}
    inv_ok = True
    for key in ("core_six", "production_labels", "sandbox"):
        block = evidence["invariants"][key]
        derived = invariants_match(block["before"], block["after"])
        recorded = bool(block.get("match"))
        inv_ok = inv_ok and derived and (recorded == derived)
        inv_report[key] = {"before": block["before"], "after": block["after"],
                          "match": derived, "match_recorded": recorded,
                          "recorded_matches_derived": recorded == derived}

    sandbox = arms_out[ARM_SANDBOX]
    measured = [cell for cell in sandbox["tiers"] if cell["cell"] == CELL_MEASURED]
    if red_cells or not inv_ok:
        status = STATUS_RED
    elif measured:
        status = STATUS_MEASURED
    else:
        status = STATUS_NOT_MEASURED

    why = []
    if not inv_ok:
        why.append("存量恒量前后不同，或记录下来的 match 与现场复算不符")
    if red_cells:
        why.append("有 {0} 格判红：{1}".format(
            len(red_cells), ",".join("{0}/{1}".format(cell["arm"], cell["label"])
                                     for cell in red_cells)))
    if status == STATUS_MEASURED:
        why.append("沙盒臂 {0}/{1} 档拿到有牙读数；生产臂仍逐档空集 ⇒ 只把检索侧从「空集」"
                   "变成「有牙读数」，格③ 本身不改口".format(len(measured), len(sandbox["tiers"])))

    unmet = []
    for arm_name in ARMS:
        for key in CRITERIA_KEYS:
            item = arms_out[arm_name]["criteria"][key]
            if item["verdict"] not in (PASS, PASS_SYNTH_ONLY):
                unmet.append(dict(item, arm=arm_name, criterion=key))

    j3 = {"judged": 0, "sets_equal": 0, "slots_equal": 0, "slots_total": 0}
    for cell in sandbox["tiers"]:
        for key in ("judged", "sets_equal", "slots_equal", "slots_total"):
            j3[key] += cell["j3"][key]

    return {
        "schema": EVIDENCE_SCHEMA, "ticket": TICKET, "status": status, "why": "; ".join(why),
        "invariants": inv_report, "invariants_ok": inv_ok, "arms": arms_out,
        "red_cells": red_cells, "measured_cells": [
            "{0}/{1}".format(ARM_SANDBOX, cell["label"]) for cell in measured],
        "unmet_criteria": unmet, "j3_summary": j3,
        "honest_boundary": HONEST_BOUNDARY, "not_cell3_green": NOT_CELL3_GREEN,
    }


def _table(headers: list, rows: list) -> list:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return out


def _criteria_rows(criteria: dict) -> list:
    named = {"a_subject_department": "(a) 主体侧真带部门",
             "b_corpus_labels": "(b) 语料两维都 selectable",
             "c_recall_positive": "(c) 该臂召回 > 0",
             "d_zero_breach": "(d) 越权 = 0"}
    rows = []
    for key in CRITERIA_KEYS:
        item = criteria[key]
        rows.append([named[key], item["verdict"], item["reading"], item["note"] or "—"])
    return rows


def _tier_rows(cells: list) -> list:
    rows = []
    for cell in cells:
        rows.append([
            cell["label"], cell["scope_reason"],
            "{0}/{1}".format(cell["admitted_total"], cell["pool_total"]),
            "{0:.4f}".format(cell["admitted_share"]),
            cell["outside_pool_total"],
            "{0}×{1}".format(cell["queries"], cell["returned"]),
            cell["distinct_hits"], len(cell["j2_breaches"]),
            cell["counterfactual_total"],
            "{0}/{1}".format(cell["j3"]["sets_equal"], cell["j3"]["judged"])
            if cell["j3"]["judged"] else "未判",
            "{0}/{1}".format(cell["j3"]["slots_equal"], cell["j3"]["slots_total"])
            if cell["j3"]["slots_total"] else "未判",
            cell["cell"],
        ])
    return rows


def render_readout(evidence: dict, verdict: dict | None = None) -> str:
    """读数表 = 本件的纯函数。同一份证据再生必须逐字节相同，否则盘上那份是手改的。"""
    verdict = verdict if verdict is not None else judge(evidence)
    run = evidence["run"]
    corpus = evidence["corpus"]
    lines: list = []
    add = lines.append

    add("# R469 · C 门检索侧沙盒读数（{0}）".format(run["started_at"]))
    add("")
    add("单号 **R469**（施工树基点 `{0}`，容器镜像 BUILD_INFO `{1}`）。".format(
        run.get("base_commit", "—"), str(run.get("image_revision", ""))[:12]))
    add("驱动 `{0}`（在 backend 容器里跑，连 compose 网络内的真 PostgreSQL）；"
        "本表由 `{1}` 从文末围栏 JSON 生成——手写即假账，`validate_readout()` 比字节。".format(
            DRIVER, TOOL))
    add("")
    add("> 🔴 口径：PGVector 是生产向量库（业主 09-24 定案，不再变更），Chroma 是退役中的遗留件。")
    add("> 今天真实位置见下面那行「读后端旋钮现读」——本表不抄文档里的开关状态；"
        "全部读数都在 pgvector 读腿上取，遗留引擎一条没问。")
    add("> 🔴 这一格的边界：{0}".format(HONEST_BOUNDARY))
    add("> {0}".format(NOT_CELL3_GREEN))
    add("")
    add("语料：`{0}` 的 {1} 枚合成行（部门 [{2}] × 密级 [{3}] × 每格 {4} 枚），dimension={5}，"
        "来历标签 `{6}`（几何夹具，非嵌入）；锚点 {7} 枚＝每枚 (部门,密级) 格里 id 最小那一枚，"
        "查询向量取该行自己的 embedding（自探针）；每锚点读两臂（带谓词 / 不带谓词），k={8}。".format(
            corpus["corpus_sha"], corpus["chunks"], ", ".join(corpus["departments"]),
            ", ".join(str(item) for item in corpus["classifications"]),
            corpus["ordinals_per_cell"], corpus["dimension"], corpus["embedding_model"],
            len(corpus["anchors"]), corpus["top_k"]))
    add("")
    add("整单状态：**{0}**".format(verdict["status"]))
    add("")
    add("判据本体：{0}。逐档判定词表：`{1}` / `{2}` / `{3}` / `{4}` / `{5}`。".format(
        TOOL, CELL_MEASURED, CELL_VACUOUS, CELL_ZERO_RECALL, CELL_RED_BREACH, CELL_RED_CONTROL))
    add("候选宽度不自带数字：现场向 `{0}` 取，本班读数 = {1}（与生产读腿同一笔调用）。".format(
        run["hnsw_ef_search_source"], run["hnsw_ef_search"]))
    read_backend = run["read_backend"]
    add("读后端旋钮现读：本班进程 `{0}`（env `{1}` 由 docker exec 注入），"
        "摘掉 env 后镜像缺省 `{2}` ⇒ 翻默认仍是业主动作，本表全部读数都在 pgvector 读腿上。".format(
            read_backend["this_process"], read_backend["env_name"],
            read_backend["shipped_default"]))
    add("")

    add("## 一、存量六枚恒量（跑前 / 跑后）")
    add("")
    add("六枚 = {0}。生产库一律只读，写只发生在沙盒库的 `r59c-` 前缀行上。".format(
        " / ".join("`{0}`".format(name) for name in CORE_INVARIANT_TABLES)))
    add("")
    core = verdict["invariants"]["core_six"]
    rows = [[name, core["before"][name], core["after"][name],
             "相同" if core["before"][name] == core["after"][name] else "🔴 不同"]
            for name in CORE_INVARIANT_TABLES]
    lines += _table(["表", "跑前", "跑后", "逐枚"], rows)
    add("")
    labels = verdict["invariants"]["production_labels"]
    lines += _table(["生产库附加恒量", "跑前", "跑后", "逐枚"], [
        ["chunk_vectors 行数", labels["before"]["rows_total"], labels["after"]["rows_total"],
         "相同" if labels["before"]["rows_total"] == labels["after"]["rows_total"] else "🔴 不同"],
        ["department 为空串的枚数", labels["before"]["dept_empty"], labels["after"]["dept_empty"],
         "相同" if labels["before"]["dept_empty"] == labels["after"]["dept_empty"] else "🔴 不同"],
        ["classification 取值分布", labels["before"]["classification_distribution"],
         labels["after"]["classification_distribution"],
         "相同" if labels["before"]["classification_distribution"]
         == labels["after"]["classification_distribution"] else "🔴 不同"],
        ["users 里 department 非空", labels["before"]["users_with_department"],
         labels["after"]["users_with_department"],
         "相同" if labels["before"]["users_with_department"]
         == labels["after"]["users_with_department"] else "🔴 不同"],
    ])
    add("")
    add("六枚复算：`{0}`（记录值与现场复算一致：`{1}`）。"
        "「取值分布」的键是 PostgreSQL 的 `integer`，不是空串——同一枚词在 "
        "`documents`/`document_versions`/`chunk_vectors` 上是 integer、在 "
        "`datasets`/`dataset_versions`/`resource_versions` 上是 text，"
        "拿空串判 integer 那三张表会当场炸（§133 六末尾那条现场教训）。".format(
            core["match"], core["recorded_matches_derived"]))
    add("")

    for arm_name in ARMS:
        arm = verdict["arms"][arm_name]
        add("## {0}、{1}臂（库 `{2}`，池 {3} 枚，本臂写入 {4} 枚）".format(
            "二" if arm_name == ARM_PRODUCTION else "三",
            "生产/演示" if arm_name == ARM_PRODUCTION else "沙盒",
            arm["database"], arm["pool_total"], arm["writes"]))
        add("")
        add("臂状态：**{0}**".format(arm["status"]))
        add("")
        lines += _table(["主体档", "scope", "池内可召/池", "share", "池外材料",
                         "读次×交回", "去重命中", "越权", "无谓词对照可越界",
                         "J-3 集合等", "J-3 槽位等", "判定"], _tier_rows(arm["tiers"]))
        add("")
        lines += _table(["§13.一 四件", "判定", "读数", "边界"],
                        _criteria_rows(arm["criteria"]))
        add("")
    add("## 四、逐档命中集合（沙盒臂）")
    add("")
    sandbox = verdict["arms"][ARM_SANDBOX]
    for cell in sandbox["tiers"]:
        add("- `{0}`（{1} / 部门 {2} / 密级 ≤{3}，谓词 `{4}`）：交回 {5} 条、去重 {6} 枚，"
            "命中项 (密级,部门) 去重清单 {7}，越权 {8} 条 → **{9}**。".format(
                cell["label"], cell["role"], cell["department"] or "—", cell["clearance"],
                cell["scope_reason"], cell["returned"], cell["distinct_hits"],
                " ".join("`({0},{1})`".format(level, department)
                         for (level, department) in cell["hit_labels"]) or "无",
                len(cell["j2_breaches"]), cell["cell"]))
        add("  - 池内该档可召的 r59c 行（{0} 枚）：{1}".format(
            len(cell["r59c_admitted_ids"]),
            " ".join("`{0}`".format(item) for item in cell["r59c_admitted_ids"])))
        add("  - 实际命中的 vector_id（去重 {0} 枚）：{1}".format(
            len(cell["hit_ids"]), " ".join("`{0}`".format(item) for item in cell["hit_ids"])))
    add("")

    add("## 五、沙盒清理账")
    add("")
    clean = evidence["cleanup"]
    lines += _table(["格", "读数"], [
        ["写入方式（唯一写点）", "`{0}`".format(clean["write_shape"])],
        ["造出的行数", clean["inserted"]],
        ["删除语句真源", "`{0}`".format(clean["delete_sql_source"])],
        ["删除点名枚数", clean["deleted"]],
        ["删除后 `vector_id LIKE 'r59c%'` 残留", clean["leftover_prefixed_rows"]],
        ["沙盒库行数（跑前 → 跑后）", "{0} → {1}".format(
            verdict["invariants"]["sandbox"]["before"]["rows_total"],
            verdict["invariants"]["sandbox"]["after"]["rows_total"])],
        ["沙盒库标签分布复现", "{0} → {1}".format(
            verdict["invariants"]["sandbox"]["before"]["classification_distribution"],
            verdict["invariants"]["sandbox"]["after"]["classification_distribution"])],
        ["恒量复现", "相同" if verdict["invariants"]["sandbox"]["match"] else "🔴 不同"],
    ])
    add("")
    add("处置：`r59c-` 行按点名 id 删除（不是 `LIKE` 扫删），删后立即复扫前缀残留必须为 0；"
        "沙盒库不 VACUUM、不 REINDEX——HNSW 页里会留下已删条目的悬挂边，"
        "这是沙盒的代价，不是生产库的，本表不声称清到字节级。")
    add("")

    add("## 六、反证钉（本单交的牙，逐把点名）")
    add("")
    lines += _table(["编号", "咬什么", "落在哪枚测试"],
                    [[item[0], item[1], "`{0}`".format(item[2])] for item in TEETH])
    add("")

    add("## 七、诚实边界（不许删，也不许抄成删过了）")
    add("")
    add("- {0}".format(HONEST_BOUNDARY))
    add("- {0}".format(NOT_CELL3_GREEN))
    add("- 本单**没过**的判据（逐条，含为什么没过）：")
    if verdict["unmet_criteria"]:
        for item in verdict["unmet_criteria"]:
            add("  - `{0}` 臂 (件 {1}) 判定 **{2}**：{3}{4}".format(
                item["arm"], item["criterion"], item["verdict"], item["reading"],
                "；" + item["note"] if item["note"] else ""))
    else:
        add("  - 无。")
    add("- 量到的是**库层读腿**（下推谓词 + 真库索引扫描 + 产品 `allows()` 复核）。"
        "**没量**端到端 `RetrievalPipeline`：那条腿要先 embed 查询句 ⇒ 打模型，本单硬禁；"
        "也没量 `DocumentRetriever._pgvector_hits` 的零行降级分支——它要 `DocumentRetriever`，"
        "而本单一行新 Chroma 依赖都不许加（AGENTS.md 向量库口径）。")
    add("- 合成向量是**几何夹具**不是嵌入（`{0}`）：它只证谓词算术与索引召回，"
        "不许被引成「pgvector 的语义召回比遗留引擎好/差」。".format(corpus["embedding_model"]))
    add("- 沙盒池 {0} 枚 ≪ 客户尺寸：J-3 在这一档全等**不可外推**，"
        "§13.二 那两句禁令（抬宽后索引扫描已≈全库暴力扫量级；自探针量不到近重复吃预算那一族）"
        "原样生效，客户尺寸两档差那一格仍未量。".format(sandbox["pool_total"]))
    add("- 沙盒库 `eb_r59_sandbox` 原有 1008 枚是**生产向量副本 + R59 合成标签**，"
        "标签形状是 4 部门 × 各 1 档；本班加的 72 枚 r59c 行补的正是同部门内跨密级那一维。"
        "两批标签都是合成的，都不证客户隔离。")
    add("")

    add("## 八、机器证据（围栏 JSON＝本表唯一事实源）")
    add("")
    add("本表由 `render_readout(evidence)` 生成；`evidence` 由 `{0}` 在容器里现取，"
        "口令一律 mask，`DATABASE_URL` 原文不入文档不入日志。".format(DRIVER))
    add("钉盯的是「手改表格」，不防「重造一份自洽的假证据」——后者要靠现场六枚恒量与"
        "容器日志对账，本单不宣称防住。")
    add("")
    add("```json")
    add(dump_evidence(evidence))
    add("```")
    add("")
    return "\n".join(lines)


def dump_evidence(evidence: dict) -> str:
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2)


def extract_evidence(markdown: str) -> dict:
    """从读数表里取回那段围栏 JSON；取不到或不唯一就是前置不满足。"""
    blocks = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() == "```json":
            stop = index + 1
            while stop < len(lines) and lines[stop].strip() != "```":
                stop += 1
            blocks.append("\n".join(lines[index + 1:stop]))
            index = stop + 1
            continue
        index += 1
    matched = []
    for block in blocks:
        try:
            parsed = json.loads(block)
        except ValueError:
            continue
        if isinstance(parsed, dict) and parsed.get("schema") == EVIDENCE_SCHEMA:
            matched.append(parsed)
    if not matched:
        raise ReadoutError(
            "读数表里没有 schema={0!r} 的围栏 JSON——表与证据脱开，判不了".format(EVIDENCE_SCHEMA))
    if len(matched) > 1:
        raise ReadoutError("读数表里有 {0} 枚证据块，拿哪一枚判？".format(len(matched)))
    return matched[0]


def validate_readout(markdown: str, evidence: dict | None = None) -> dict:
    """盘上那份必须由证据再生得出来，且证据自己必须过关。"""
    evidence = evidence if evidence is not None else extract_evidence(markdown)
    regenerated = render_readout(evidence)
    if regenerated != markdown:
        first = next((number for number, (left, right) in
                      enumerate(zip(markdown.splitlines(), regenerated.splitlines()), start=1)
                      if left != right), None)
        raise ReadoutError(
            "盘上读数表与再生件第 {0} 行起不同 ⇒ 有人手改过表格（或改过本件却没重生成）".format(
                first if first else "长度"))
    verdict = judge(evidence)
    core = verdict["invariants"]["core_six"]
    if not core["match"]:
        raise ReadoutError("存量六枚恒量前后不同：{0} vs {1}".format(core["before"], core["after"]))
    if not verdict["invariants_ok"]:
        raise ReadoutError("恒量复算不过关：记录值与现场复算不符，或未逐枚相同")
    clean = evidence["cleanup"]
    if int(clean["leftover_prefixed_rows"]) != 0:
        raise ReadoutError("沙盒里还剩 {0} 枚 r59c- 行没清干净".format(
            clean["leftover_prefixed_rows"]))
    production = verdict["arms"][ARM_PRODUCTION]
    if any(cell["cell"] == CELL_MEASURED for cell in production["tiers"]):
        raise ReadoutError("生产臂声称拿到了「有牙读数」——§133 六实测生产标签全同值，"
                           "这条只能是假账")
    if not verdict["measured_cells"]:
        raise ReadoutError("沙盒臂一枚「有牙读数」都没有 ⇒ 这一格仍是空集真，"
                           "本单没有把 C 门检索侧量到，不许抄成量到了")
    for sentence in (HONEST_BOUNDARY, NOT_CELL3_GREEN):
        if sentence not in markdown:
            raise ReadoutError("读数表里缺那句诚实边界：{0}".format(sentence[:40]))
    for key in CRITERIA_KEYS:
        for arm_name in ARMS:
            if key not in verdict["arms"][arm_name]["criteria"]:
                raise ReadoutError("四件判据缺件：{0}/{1}".format(arm_name, key))
    return {"status": verdict["status"], "cells": len(
        verdict["arms"][ARM_SANDBOX]["tiers"]) + len(production["tiers"]),
        "measured_cells": len(verdict["measured_cells"]),
        "unmet_criteria": len(verdict["unmet_criteria"])}

#: 本单交回的反证钉：编号 / 咬什么 / 落在哪枚测试函数。
#: `tests/test_r469_readout_is_generated.py` 机检这三列与盘上测试件逐一对得上——
#: 表里点名一枚不存在的钉，等于把没装上的牙写成装上了。
TEETH = (
    ("T1", "把产品那道 `allows()` 摘成恒 True ⇒ 每档的 control 格当场红（判定失去可判性）",
     "test_counter_evidence_neutered_allows_turns_the_control_red"),
    ("T2", "拿「无谓词那一臂」的命中冒充「有谓词那一臂」（＝下推谓词被旁路）⇒ 越权条数 > 0",
     "test_counter_evidence_bypassed_predicate_reports_breaches"),
    ("T3", "把标签抹成同值（全空部门、全 1 档密级）⇒ 逐档退回空集真、整单 NOT_MEASURED",
     "test_counter_evidence_homogeneous_labels_lose_selectivity"),
    ("T4", "存量六枚恒量任一枚前后不同 ⇒ validate 拒出表",
     "test_counter_evidence_invariant_drift_is_refused"),
    ("T5", "手改表格里的任一枚读数 ⇒ 与再生件字节不符",
     "test_the_in_tree_readout_is_byte_for_byte_what_the_lib_emits"),
    ("T6", "生产臂被写成「有牙读数」（而 §133 六实测标签全同值）⇒ validate 直接拒",
     "test_counter_evidence_a_fabricated_production_cell_is_refused"),
    ("T7", "驱动里长出裸 `psycopg.connect`、或生产连接上读只标志没先落地 ⇒ 纪律钉红",
     "test_the_driver_reaches_the_database_only_through_the_boundary"),
    ("T8", "候选宽度/前缀/模型名等真源量在驱动里被抄成第二份字面量 ⇒ 抄数钉红",
     "test_no_ticket_carries_a_second_copy_of_a_true_source_number"),
    ("T9", "把记录下来的 `match: true` 当数用（现场复算与它不符）⇒ 仍拒：恒量只信现场复算",
     "test_counter_evidence_a_recorded_match_flag_is_not_believed"),
    ("T10", "沙盒里残留一枚 `r59c-` 行没清干净 ⇒ 拒，不许把没扫过的库交给下一班",
     "test_counter_evidence_the_leftover_sandbox_row_is_refused"),
)

EXIT_OK = 0
EXIT_RED = 1
EXIT_PRECONDITION = 2


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def cmd_render(args) -> int:
    evidence = json.loads(_read_text(args.evidence))
    markdown = render_readout(evidence)
    Path(args.out).write_text(markdown, encoding="utf-8", newline="\n")
    verdict = judge(evidence)
    print("[生成] {0} 行 → {1}；状态 {2}".format(
        len(markdown.splitlines()), args.out, verdict["status"]))
    return EXIT_OK if verdict["status"] != STATUS_RED else EXIT_RED


def cmd_validate(args) -> int:
    try:
        report = validate_readout(_read_text(args.readout))
    except ReadoutError as exc:
        print("[不过] {0}".format(exc))
        return EXIT_PRECONDITION
    print("[过关] 状态 {0}｜有牙格 {1} 枚｜未过判据 {2} 条".format(
        report["status"], report["measured_cells"], report["unmet_criteria"]))
    return EXIT_OK if report["status"] == STATUS_MEASURED else EXIT_RED


def cmd_judge(args) -> int:
    evidence = json.loads(_read_text(args.evidence))
    verdict = judge(evidence)
    print(json.dumps({"status": verdict["status"], "why": verdict["why"],
                      "measured_cells": verdict["measured_cells"],
                      "red_cells": [{0: cell[0] for cell in ("arm", "label", "cell")}
                                    for cell in verdict["red_cells"]],
                      "unmet_criteria": verdict["unmet_criteria"],
                      "j3_summary": verdict["j3_summary"]},
                     ensure_ascii=False, indent=2))
    return EXIT_OK if verdict["status"] == STATUS_MEASURED else (
        EXIT_RED if verdict["status"] == STATUS_RED else EXIT_PRECONDITION)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=TOOL, description="R469 判据本体与读数表生成器")
    sub = parser.add_subparsers(dest="command")
    render = sub.add_parser("render", help="由证据 JSON 出读数表（唯一合法出表口）")
    render.add_argument("--evidence", required=True)
    render.add_argument("--out", required=True)
    render.set_defaults(func=cmd_render)
    validate = sub.add_parser("validate", help="盘上那份必须能由证据再生，且证据自己过关")
    validate.add_argument("--readout", required=True)
    validate.set_defaults(func=cmd_validate)
    judge_ = sub.add_parser("judge", help="只判不落盘：逐档判定 + 未过清单")
    judge_.add_argument("--evidence", required=True)
    judge_.set_defaults(func=cmd_judge)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_PRECONDITION
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())