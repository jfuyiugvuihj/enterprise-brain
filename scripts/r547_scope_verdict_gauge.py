# -*- coding: utf-8 -*-
"""R547 量具（只读）：计划书 §13.一 那四件可失败判据，**两条臂各现读派生一遍**。

三条道（全部零写入、零模型；一条 UPDATE/INSERT 都不发）：

    # ① 真库现读——DSN 只由环境给，给不到就 rc=2 并点名是哪一枚变量没给
    $env:R547_PRODUCTION_DATABASE_URL = "..."      # 总控在容器网络里注入
    $env:R547_SANDBOX_DATABASE_URL    = "..."
    python scripts/r547_scope_verdict_gauge.py --mode live --arm both

    # ② 在册尺重跑——用在册 `scripts/r469_readout_lib.py` 那把尺重判在册读数件（沙盒 252 枚那一路）
    python scripts/r547_scope_verdict_gauge.py --mode reread

    # ③ 三形自检——读不到库／表空／列全空 各自 FAIL 并点名（夹具，不是读数）
    python scripts/r547_scope_verdict_gauge.py --mode shapes

🔴 三形自检那一道打印的每一行都带 `DEMONSTRATION_FIXTURE_NOT_A_MEASUREMENT`：它是夹具在过自己的牙，
   rc=0 只说明"三形确实各自红了"，**不说明任何一格量到了东西**。别把它抄进账。

四件硬边界（本件自己拦，不靠人记）
--------------------------------
* **DSN 只从环境来，且两臂两枚变量分开**：`R547_PRODUCTION_DATABASE_URL` / `R547_SANDBOX_DATABASE_URL`。
  刻意不读 `DATABASE_URL`——主树 `.env` 里那一枚指向宿主 5432，而宿主 5432 上是野 PG
  （计划书 §9.4 抓过的那枚假读数形状）。连上的库名与本臂声称的那一枚对不上 ⇒ rc=3 点名，不自愈。
* **只读先于取数**：会话先 `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`，把证明取回来
  才谈读数（复用在册件 `scripts/r469_sandbox_scope_readout.py` 的 `prove_read_only`）。
* **两臂不许互相顶替**：C 门（越权格）只认生产臂的数字；`--gate sandbox` 当场拒。沙盒那批合成标签
  **只证行为、不证客户隔离**（业主在册原话，本件按锚从 `human-gates` 那一行现读派生），
  它量到什么都不关门。
* **量不到不许折成 0 或绿**：拿不到数就交 reason code 加一句"为什么这不是读数"；
  生产臂任何一格想挂 PASS 而现场撑不住 ⇒ rc=3（与在册 `validate_readout` 拒"生产臂声称有牙"同形）。

判定词表、臂名、四件键名一律从 `scripts/r469_readout_lib.py` 导入——本件不长第二套说法；
标签分布／账号存量／池子的取数一律复用在册采集腿——本件不重写一条取数句。
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from pathlib import Path

#: 摘牙守卫：变异检验时把这枚量具的副本放进影子目录，仓库根仍指真树（与 R455 那本同法）
REPO_ROOT = Path(os.environ.get("R547_REPO_ROOT") or Path(__file__).resolve().parents[1])
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TOOL = "scripts/r547_scope_verdict_gauge.py"
LIB_REL = "scripts/r469_readout_lib.py"
DRIVER_REL = "scripts/r469_sandbox_scope_readout.py"
PLAN_REL = "docs/handoff/2026-09-17-pgvector-adoption-plan.md"
GATES_REL = "docs/handoff/2026-09-17-human-gates.md"
READOUT_REL = "docs/testing/r469-sandbox-scope-readout-2026-09-28.md"

PRODUCTION_DSN_ENV = "R547_PRODUCTION_DATABASE_URL"
SANDBOX_DSN_ENV = "R547_SANDBOX_DATABASE_URL"
GATE_NAME = "格③ / C 门（跨部门·跨密级越权命中为 0）"

#: 量不到与退化形状的点名码：每一枚都必须落到交回上，不许被一条通用异常吞掉。
ENV_DSN_UNSET = "ENV_DSN_UNSET"
CONNECT_FAILED = "CONNECT_FAILED"
SESSION_NOT_READ_ONLY = "SESSION_NOT_READ_ONLY"
SCHEMA_RELATIONS_MISSING = "SCHEMA_RELATIONS_MISSING"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
POOL_TABLE_EMPTY = "POOL_TABLE_EMPTY"
ACCOUNTS_TABLE_EMPTY = "ACCOUNTS_TABLE_EMPTY"
ACCOUNT_COLUMN_ALL_EMPTY = "ACCOUNT_COLUMN_ALL_EMPTY"
LABEL_COLUMN_ALL_EMPTY = "LABEL_COLUMN_ALL_EMPTY"
LABELS_NOT_SELECTABLE = "LABELS_NOT_SELECTABLE"
SYNTH_LABELS_ABSENT = "SYNTH_LABELS_ABSENT"
READ_LEG_NOT_EXERCISED = "READ_LEG_NOT_EXERCISED"
ARM_SUBSTITUTION_REFUSED = "ARM_SUBSTITUTION_REFUSED"
PRODUCTION_PASS_WITHOUT_EVIDENCE = "PRODUCTION_PASS_WITHOUT_EVIDENCE"

#: rc 的归属（退出码与在册 r469 同词表：0 过关／1 红／2 前置不满足／3 拒）。
PRECONDITION_REASONS = frozenset({ENV_DSN_UNSET, CONNECT_FAILED,
                                  SESSION_NOT_READ_ONLY, SCHEMA_RELATIONS_MISSING})
REFUSED_REASONS = frozenset({IDENTITY_MISMATCH})
DEGENERATE_REASONS = frozenset({POOL_TABLE_EMPTY, ACCOUNTS_TABLE_EMPTY, ACCOUNT_COLUMN_ALL_EMPTY,
                                LABEL_COLUMN_ALL_EMPTY, SYNTH_LABELS_ABSENT})

#: 🔴 业主在册原话的口径，逐字在账，不许改写、不许删（与 r469 那把尺同一处理）。
SANDBOX_NEVER_CLOSES_GATE = "沙盒合成标签只证行为、不证客户隔离，量到什么都不关门。"
FIXTURE_MARK = "DEMONSTRATION_FIXTURE_NOT_A_MEASUREMENT"

# ------------------------------------------------------------------ 派生锚（行号一律运行时取）

def read_rows(rel):
    """现读盘上那一本：先证明换行符仍成对，再按行切开。行号 = 下标 + 1。"""
    raw = (REPO_ROOT / rel).read_bytes().decode("utf-8")
    assert raw.count("\r") == raw.count("\n"), rel + " 的换行符不再成对"
    return raw.splitlines()


def one_line(rel, anchor, what):
    """锚在那本纸里必须唯一命中；不唯一就当场停——派生错一格的引文比没有引文更坏。"""
    hits = [(no, line) for no, line in enumerate(read_rows(rel), 1) if anchor in line]
    if len(hits) != 1:
        raise SystemExit("[前置不满足] {0} 那一格在 {1} 里现读命中 {2} 枚，定位不唯一："
                         "本件不许猜行号".format(what, rel, len(hits)))
    return hits[0]


RULING_ANCHORS = (
    ("H13", "## H13 结案 ＋ A1/A3 裁定", "H13 结案节"),
    ("auditor", "密级档位 = 3", "auditor 密级档那一裁定"),
    ("A1", "A1（`users.department` 回填）裁定", "A1 那一裁定"),
    ("A3", "A3（生产密级标签回填）裁定", "A3 那一裁定"),
)


def owner_rulings():
    """业主三条裁定的坐标与原文按锚现读派生；交回与纸面只许引用这一枚派生值。"""
    out = {}
    for key, anchor, what in RULING_ANCHORS:
        no, line = one_line(GATES_REL, anchor, what)
        out[key] = {"line": no, "anchor": anchor, "quote": line.strip()}
    return out


#: 纸面括号里那几枚计划书侧坐标：一枚都不许手抄，全部按锚现读派生。
PLAN_CITATION_ANCHORS = (
    ("d_accounting", "只有 (d) 单独成立不记通过", "§13.一 末「记账口径」那一行"),
    ("nine_three_gate", "本格的判据今天改写为四件可失败判据", "§9.3 第 3 格那一行"),
    ("cell2_hotset", "第 **②** 格（热集让路延迟）", "§13.四 第 ② 格那一行"),
)


def plan_citations():
    """本纸引用的计划书侧行号：按锚现读；锚不唯一当场停。漂一格就脱钩。"""
    out = {}
    for key, anchor, what in PLAN_CITATION_ANCHORS:
        no, line = one_line(PLAN_REL, anchor, what)
        out[key] = {"line": no, "anchor": anchor, "what": what, "text": line.strip()}
    return out


def plan_floors():
    """(b) 那两枚门槛（不同部门 ≥N、不同密级 ≥N）从 §13.一 判据本体现读，不落第二份数字。"""
    no, line = one_line(PLAN_REL, "不同部门 ≥", "§13.一 (b) 那一行")
    floors = [int(value) for value in re.findall(r"≥\s*(\d+)", line)]
    if len(floors) != 2:
        raise SystemExit("[前置不满足] §13.一 (b) 那一行读不到两枚门槛（拿到 {0}）："
                         "判据本体改了形，本件要跟着改，不许自带缺省".format(floors))
    return {"line": no, "min_departments": floors[0], "min_classifications": floors[1]}


def load_instruments():
    """在册那两件（判据尺 + 只读采集腿）按需装载；取不到就是前置不满足，本件不降级成自造一套。"""
    try:
        lib = importlib.import_module("scripts.r469_readout_lib")
        driver = importlib.import_module("scripts.r469_sandbox_scope_readout")
    except Exception as exc:
        raise SystemExit("[前置不满足] 取不到在册件 {0} / {1}：{2}: {3}".format(
            LIB_REL, DRIVER_REL, type(exc).__name__, str(exc)[:180]))
    return lib, driver


# ------------------------------------------------------------------ 四件判据的派生本体

def unmeasurable(reason, lib, keys, detail=""):
    """量不到那一族：四件一起挂「未验」，并把 reason 原样带出去。"""
    item = {"verdict": lib.UNVERIFIED, "measurable": False, "reason": reason,
            "reading": "无现读（量不到）" + (("：" + detail) if detail else ""),
            "note": "量不到不等于干净，更不等于通过"}
    return dict((key, dict(item)) for key in keys)


def derive(arm, readings, floors, lib):
    """把 §13.一 那四件从现读派生一遍。

    拿得到数 ⇒ 报数与件级判定（判定词表用在册那四枚，不另立说法）；
    拿不到数 ⇒ `measurable=False` + reason 点名，**绝不把"没读到"折成"读到 0 枚"**。
    """
    keys = list(lib.CRITERIA_KEYS)
    if readings.get("blocked"):
        return unmeasurable(readings["blocked"], lib, keys, readings.get("detail", ""))

    accounts, labels, tiers = readings["accounts"], readings["labels"], readings["tiers"]
    rows_total = int(labels["rows_total"])
    out = {}

    # (a) 主体侧真带部门——管理员那档 `departments=None` 不算（§13.一 原话）。
    users_total = int(accounts["users_total"])
    present = int(accounts["non_admin_accounts_with_department"])
    if users_total == 0:
        out[keys[0]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                        "reason": ACCOUNTS_TABLE_EMPTY,
                        "reading": "users 表 0 行：连分母都没有，说不出『非空几枚』",
                        "note": "空表不是读数"}
    else:
        reason = "" if present > 0 else (
            ACCOUNT_COLUMN_ALL_EMPTY if int(accounts["users_with_department"]) == 0 else
            LABELS_NOT_SELECTABLE)
        out[keys[0]] = {"verdict": lib.PASS if present > 0 else lib.UNVERIFIED,
                        "measurable": True, "reason": reason,
                        "reading": "users 表 {0} 行里 department 非空 {1} 行；去掉管理员档还剩 {2} 行"
                                   .format(users_total, accounts["users_with_department"], present),
                        "note": "" if present > 0 else "主体侧没有可判的真账号"}

    # (b) 语料两维都 selectable。
    if rows_total == 0:
        out[keys[1]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                        "reason": POOL_TABLE_EMPTY,
                        "reading": "池子 0 枚：0/0 不是读数，不许写成『非空 0 枚 ⇒ 干净』",
                        "note": "空表不是读数"}
    else:
        nonempty = int(labels["nonempty_department"])
        depts_all = [str(v) for v in labels["distinct_departments"]]
        depts_nonempty = [v for v in depts_all if v != ""]
        levels = [str(v) for v in labels["distinct_classifications"]]
        ok = (nonempty > 0 and len(depts_nonempty) >= floors["min_departments"]
              and len(levels) >= floors["min_classifications"])
        out[keys[1]] = {
            "verdict": lib.PASS if ok else lib.FAIL, "measurable": True,
            "reason": "" if ok else (LABEL_COLUMN_ALL_EMPTY if nonempty == 0
                                     else LABELS_NOT_SELECTABLE),
            "reading": ("非空 department {0}/{1} 枚；非空部门 {2} 档 [{3}]（在册尺口径含空串时 {4} 档）；"
                        "密级 {5} 档 [{6}]；(部门,密级) 叉乘 {7} 格；门槛 部门≥{8}/密级≥{9}"
                        "（门槛现读自计划书 :{10}）").format(
                            nonempty, rows_total, len(depts_nonempty),
                            "/".join(depts_nonempty) or "<无>", len(depts_all),
                            len(levels), "/".join(levels), labels["distinct_pairs"],
                            floors["min_departments"], floors["min_classifications"],
                            floors["line"]),
            "note": "两档口径并列交回：判 PASS 用非空档，在册尺报档数含空串——不互相顶替",
        }

    # (c) 该臂召回 > 0——本件不跑读腿，只有"谓词恒空集 ⇒ 召回必为 0"这一支能落 FAIL。
    if rows_total == 0:
        out[keys[2]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                        "reason": POOL_TABLE_EMPTY, "reading": "池子 0 枚，谈不到召回",
                        "note": "空表不是读数"}
    else:
        restricted = [t for t in tiers if t["departments"]]
        with_admit = [t for t in restricted if int(t["admitted_total"]) > 0]
        if restricted and not with_admit:
            out[keys[2]] = {"verdict": lib.FAIL, "measurable": True, "reason": "",
                            "reading": "带部门谓词的档 {0}/{1} 枚，逐档可召料 0 枚 ⇒ 召回必为 0"
                                       .format(len(restricted), len(tiers)),
                            "note": "这正是 §13.一 (c) 那天那条空集的形状"}
        else:
            out[keys[2]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                            "reason": READ_LEG_NOT_EXERCISED,
                            "reading": "谓词放行 {0} 枚 ≠ 读腿交回 {0} 枚：本件不跑读腿，"
                                       "不许把它折成召回>0".format(
                                           sum(int(t["admitted_total"]) for t in restricted)),
                            "note": "召回那一件只能由跑过读腿的在册尺（r469 那条道）给绿"}

    # (d) 越权 = 0。条数只有跑了读腿才拿得到；空集形状的 0 一律不记结论。
    if rows_total == 0:
        out[keys[3]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                        "reason": POOL_TABLE_EMPTY, "reading": "池子 0 枚，越权条数无从派生",
                        "note": "空表不是读数"}
    else:
        selective = [t for t in tiers if 0 < int(t["admitted_total"]) < int(t["pool_total"])]
        outside = sum(int(t["outside_total"]) for t in tiers)
        if not selective:
            out[keys[3]] = {"verdict": lib.UNVERIFIED, "measurable": True, "reason": "",
                            "reading": "逐档谓词要么挡光要么全放行（可选档 0/{0} 枚，池外材料 {1} 枚）"
                                       "⇒ 越权 0 条是空集真，无从判".format(len(tiers), outside),
                            "note": "只在空集意义上成立的 0，不记通过（§13.一 记账口径）"}
        else:
            out[keys[3]] = {"verdict": lib.UNVERIFIED, "measurable": False,
                            "reason": READ_LEG_NOT_EXERCISED,
                            "reading": "{0}/{1} 档有可选性、池外共 {2} 枚可漏：没跑读腿就拿不到"
                                       "越权条数，0 条不许当结论".format(
                                           len(selective), len(tiers), outside),
                            "note": "有东西可判 ≠ 已经判过"}

    return {key: out[key] for key in keys}

# ------------------------------------------------------------------ 关门与反绿自检

def gate_roll(arm, criteria, lib):
    """格③ / C 门只认生产臂那四件：任一不满足即记「未验」，只有真出现越权 > 0 才记「不通过」。"""
    keys = list(lib.CRITERIA_KEYS)
    if arm != lib.ARM_PRODUCTION:
        return {"gate": GATE_NAME, "verdict": lib.UNVERIFIED,
                "reason": ARM_SUBSTITUTION_REFUSED, "unmet": keys,
                "why": SANDBOX_NEVER_CLOSES_GATE}
    breach = int(criteria[keys[3]].get("breaches") or 0)
    if breach:
        return {"gate": GATE_NAME, "verdict": lib.FAIL, "reason": "", "unmet": keys,
                "why": "越权 {0} 条：不通过优先于未验（§13.一 记账口径）".format(breach)}
    unmet = [key for key in keys
             if criteria[key]["verdict"] != lib.PASS or not criteria[key]["measurable"]]
    if not unmet:
        return {"gate": GATE_NAME, "verdict": lib.PASS, "reason": "", "unmet": [],
                "why": "四件全部现读可判且都过——这一支今天不可达，写在这儿是为了让它能被证伪"}
    return {"gate": GATE_NAME, "verdict": lib.UNVERIFIED, "reason": "", "unmet": unmet,
            "why": "任一不满足即记未验，不得记通过（计划书 §13.一 判据本体）"}


def green_audit(arm, criteria, readings, gate, lib):
    """🔴 反绿自检：想在生产臂上挂绿，必须有现场撑得住的数；撑不住就点名拒，不商量。"""
    defects = []
    keys = list(lib.CRITERIA_KEYS)
    if readings.get("blocked"):
        if gate["verdict"] != lib.UNVERIFIED:
            defects.append("读不到的那一臂交出了 {0} 而不是未验".format(gate["verdict"]))
        for key in keys:
            if criteria[key]["verdict"] == lib.PASS:
                defects.append("{0}：量不到被折成了 PASS".format(key))
        return defects
    if arm != lib.ARM_PRODUCTION:
        return defects
    accounts, labels = readings["accounts"], readings["labels"]
    if criteria[keys[0]]["verdict"] == lib.PASS and int(
            accounts.get("non_admin_accounts_with_department", 0)) <= 0:
        defects.append("(a) 记 PASS 却没有一行非管理员账号真带部门")
    if criteria[keys[1]]["verdict"] == lib.PASS and int(labels.get("nonempty_department", 0)) <= 0:
        defects.append("(b) 记 PASS 而语料非空 department 为 0 枚")
    if criteria[keys[3]]["verdict"] == lib.PASS:
        defects.append("(d) 本件一条读腿都没跑，生产臂这一件只能由在册尺给，不许自封")
    for item in criteria.values():
        if item["verdict"] == lib.PASS and not item["measurable"]:
            defects.append("PASS 挂在 measurable=False 上")
    return defects


def degenerate_shapes(arm, readings, lib):
    """退化形状逐枚点名（表空／列全空／沙盒没合成标签）：这些一律红，不许当成"量到了 0"。"""
    flags = []
    if readings.get("blocked"):
        blocked = readings["blocked"]
        return [blocked] if blocked in DEGENERATE_REASONS else []
    labels, accounts = readings["labels"], readings["accounts"]
    if int(labels["rows_total"]) == 0:
        flags.append(POOL_TABLE_EMPTY)
    elif int(labels["nonempty_department"]) == 0:
        flags.append(LABEL_COLUMN_ALL_EMPTY)
    if int(accounts["users_total"]) == 0:
        flags.append(ACCOUNTS_TABLE_EMPTY)
    elif int(accounts["users_with_department"]) == 0:
        flags.append(ACCOUNT_COLUMN_ALL_EMPTY)
    if arm == lib.ARM_SANDBOX and int(labels.get("r59c_rows", 0)) == 0:
        flags.append(SYNTH_LABELS_ABSENT)
    return flags


def arm_rc(arm, readings, criteria, gate, shapes, defects, lib, driver):
    """一臂的退出码：拒 > 前置 > 红 > 过关。没有读数时不谈红，但绝不谈绿。"""
    refused = int(getattr(driver, "EXIT_REFUSED", 3))
    if defects:
        return refused
    blocked = readings.get("blocked")
    if blocked in PRECONDITION_REASONS:
        return lib.EXIT_PRECONDITION
    if blocked in REFUSED_REASONS:
        return refused
    if blocked or shapes:
        return lib.EXIT_RED
    if any(item["verdict"] == lib.FAIL for item in criteria.values()):
        return lib.EXIT_RED
    if all(item["verdict"] == lib.PASS for item in criteria.values()):
        return lib.EXIT_OK
    return lib.EXIT_RED


def aggregate_rc(results, lib, driver):
    severities = [int(item["rc"]) for item in results]
    return max(severities) if severities else lib.EXIT_PRECONDITION


# ------------------------------------------------------------------ 现读采集（全部走只读会话）

def probe_relations(connection, tables):
    """本件唯一自己发的 SQL：只问 `to_regclass`，一枚数据行都不读——野 PG 就是在这露形的。"""
    missing = []
    for table in tables:
        row = connection.execute("SELECT to_regclass(%s)", ("public." + table,)).fetchone()
        if row is None or row[0] is None:
            missing.append(table)
    return missing


def scope_tiers(rows, r59c, driver):
    """谓词由产品自己那一层算（`resolve_document_retrieval_scope` + `allows()`），本件不复制规则。"""
    from app.rag.filters import resolve_document_retrieval_scope

    tiers = []
    for spec in r59c.PRINCIPALS:
        scope = resolve_document_retrieval_scope(driver.make_principal(spec))
        admitted = sum(1 for row in rows if scope.allows(row))
        departments = None if scope.departments is None else sorted(scope.departments)
        tiers.append({"label": spec["label"], "role": spec["role"], "departments": departments,
                      "pool_total": len(rows), "admitted_total": admitted,
                      "outside_total": len(rows) - admitted})
    return tiers


def collect_live(arm, url, env_name, lib, driver):
    """一臂的现场读数：DSN 只由环境给；拿不到就带 reason 回来，不自愈、不降级、不改库名乱试。"""
    expected_db = driver.PRODUCTION_DB if arm == lib.ARM_PRODUCTION else driver.SANDBOX_DB
    if not url:
        return {"blocked": ENV_DSN_UNSET,
                "detail": "环境变量 {0} 未设：本件不许自造 DSN，更不许拿宿主 5432 那台野 PG "
                          "当这一臂的库（计划书 §9.4）".format(env_name)}
    try:
        connection = driver.open_connection(url)
    except Exception as exc:
        return {"blocked": CONNECT_FAILED,
                "detail": "{0}: {1}".format(type(exc).__name__, str(exc)[:200])}
    try:
        identity = driver.prove_read_only(connection)      # SET 只读排在任何取数之前
        if identity["transaction_read_only"] != "on":
            return {"blocked": SESSION_NOT_READ_ONLY,
                    "detail": "会话自证为 {0}：只读证明没落地就取数，本件不做".format(
                        identity["transaction_read_only"])}
        if identity["database"] != expected_db:
            return {"blocked": IDENTITY_MISMATCH,
                    "detail": "这一臂声称连 {0}，现场连上的是 {1}（{2}）".format(
                        expected_db, identity["database"], driver.mask_url(url))}
        scope_table = importlib.import_module("scripts.audit_vector_mirror_sets").DEFAULT_SCOPE_TABLE
        missing = probe_relations(connection, list(driver.CORE_TABLES) + [scope_table])
        if missing:
            return {"blocked": SCHEMA_RELATIONS_MISSING,
                    "detail": "库里读不到这些关系：{0} ⇒ 这就是 §9.4 那台野 PG 的形状；"
                              "『读不到关系』不许折成『库里有 0 枚』".format("、".join(missing))}
        r59c = importlib.import_module("scripts.r59c_sandbox_corpus")
        prefix = driver.r59c_provenance(r59c)["prefix"]
        rows = driver.pool_rows(connection)
        readings = {"accounts": driver.accounts_block(connection),
                    "labels": driver.labelled_block(connection, prefix),
                    "tiers": scope_tiers(rows, r59c, driver),
                    "identity": identity, "prefix": prefix, "dsn": driver.mask_url(url)}
        connection.rollback()
        return readings
    finally:
        try:
            connection.close()
        except Exception:
            pass


# ------------------------------------------------------------------ 三形自检（夹具，不是读数）

#: 夹具的行数只是**规模参数**，不是任何库的读数；这一道打印的每一行都带 `FIXTURE_MARK`。
FIXTURE_ROWS = 3
SHAPES = ("no-database", "empty-table", "all-empty-column")
SHAPE_WANTS = {
    "no-database": (ENV_DSN_UNSET, CONNECT_FAILED),
    "empty-table": (POOL_TABLE_EMPTY, ACCOUNTS_TABLE_EMPTY),
    "all-empty-column": (LABEL_COLUMN_ALL_EMPTY, ACCOUNT_COLUMN_ALL_EMPTY),
}


def fixture_readings(shape):
    if shape == "no-database":
        return {"blocked": CONNECT_FAILED, "detail": "夹具：连不上库（真跑这一形看 rc，用 --mode live）"}
    if shape == "empty-table":
        return {"accounts": {"users_total": 0, "users_with_department": 0,
                             "non_admin_accounts_with_department": 0, "rows": []},
                "labels": {"rows_total": 0, "nonempty_department": 0, "distinct_departments": [],
                           "distinct_classifications": [], "distinct_pairs": 0, "r59c_rows": 0},
                "tiers": []}
    if shape == "all-empty-column":
        return {"accounts": {"users_total": FIXTURE_ROWS, "users_with_department": 0,
                             "non_admin_accounts_with_department": 0, "rows": []},
                "labels": {"rows_total": FIXTURE_ROWS, "nonempty_department": 0,
                           "distinct_departments": [""], "distinct_classifications": ["1"],
                           "distinct_pairs": 1, "r59c_rows": 0},
                "tiers": [{"label": "fixture-staff", "role": "staff", "departments": ["fin"],
                           "pool_total": FIXTURE_ROWS, "admitted_total": 0,
                           "outside_total": FIXTURE_ROWS},
                          {"label": "fixture-admin", "role": "admin", "departments": None,
                           "pool_total": FIXTURE_ROWS, "admitted_total": FIXTURE_ROWS,
                           "outside_total": 0}]}
    raise SystemExit("[前置不满足] 不认识的形状：{0}".format(shape))


def run_shapes(lib, driver, floors):
    """把同一派生道按在三种拿不到数的形状上：必须各自红、各自点名、一枚绿都不许出现。"""
    results = []
    for shape in SHAPES:
        readings = fixture_readings(shape)
        arm = lib.ARM_PRODUCTION
        criteria = derive(arm, readings, floors, lib)
        gate = gate_roll(arm, criteria, lib)
        flags = degenerate_shapes(arm, readings, lib)
        defects = green_audit(arm, criteria, readings, gate, lib)
        rc = arm_rc(arm, readings, criteria, gate, flags, defects, lib, driver)
        reasons = sorted({item["reason"] for item in criteria.values() if item["reason"]})
        pool = set(flags) | set(reasons)
        named = [code for code in SHAPE_WANTS[shape] if code in pool]
        greens = [key for key, item in criteria.items() if item["verdict"] == lib.PASS]
        results.append({"shape": shape, "fixture": FIXTURE_MARK, "rc": rc,
                        "named": named, "reasons": reasons, "shapes": flags,
                        "gate_verdict": gate["verdict"], "greens": greens,
                        "criteria": criteria,
                        "teeth_ok": bool(rc != lib.EXIT_OK and named and not greens
                                         and not defects)})
    return results


# ------------------------------------------------------------------ 在册尺重跑（不新读任何库）

def run_reread(readout_rel, lib, driver):
    """用在册 `scripts/r469_readout_lib.py` 那把尺，把在册读数件的两臂四件重判一遍。"""
    markdown = (REPO_ROOT / readout_rel).read_text(encoding="utf-8")
    try:
        report = lib.validate_readout(markdown)
    except lib.ReadoutError as exc:
        return {"status": "REFUSED", "defects": ["在册尺拒收这份读数件：{0}".format(exc)]}
    verdict = lib.judge(lib.extract_evidence(markdown))
    arms = {}
    for arm in lib.ARMS:
        block = verdict["arms"][arm]
        cells = block["tiers"]
        detail = [{"label": c["label"], "scope_reason": c["scope_reason"],
                   "admitted": c["admitted_total"], "outside": c["outside_pool_total"],
                   "returned": c["returned"], "counterfactual": c["counterfactual_total"],
                   "cell": c["cell"]} for c in cells]
        no_dept = [c for c in cells if c["departments"] is None]
        arms[arm] = {
            "cells": detail,
            "no_predicate_outside": int(no_dept[0]["outside_pool_total"]) if no_dept else None,
            "database": block["database"], "pool_total": block["pool_total"],
            "status": block["status"], "criteria": block["criteria"],
            "teeth_cells": sum(1 for c in cells if c["cell"] == lib.CELL_MEASURED),
            "vacuous_cells": sum(1 for c in cells if c["cell"] == lib.CELL_VACUOUS),
            "breaches": sum(len(c["j2_breaches"]) for c in cells),
            "counterfactual_total": sum(int(c["counterfactual_total"]) for c in cells),
            "max_outside_pool_total": max([int(c["outside_pool_total"]) for c in cells] or [0]),
            "synth_rows": int(block.get("writes", 0)),
        }
    ruling = owner_rulings()["A3"]["quote"]
    match = re.search(r"沙盒那\s*(\d+)\s*枚", ruling)
    return {"status": verdict["status"], "arms": arms,
            "unmet_criteria": verdict["unmet_criteria"], "report": report,
            "reread_via": LIB_REL + " validate + judge",
            "ruling_synth_count": int(match.group(1)) if match else None,
            "ruling_quote": ruling,
            "honest_boundary_in_paper": lib.HONEST_BOUNDARY in markdown,
            "cell3_not_green_in_paper": lib.NOT_CELL3_GREEN in markdown,
            "readout": readout_rel}


# ------------------------------------------------------------------ 真库现读

def run_live(arm_list, lib, driver, floors):
    results = []
    for arm in arm_list:
        env_name = PRODUCTION_DSN_ENV if arm == lib.ARM_PRODUCTION else SANDBOX_DSN_ENV
        url = str(os.environ.get(env_name, "") or "").strip()
        readings = collect_live(arm, url, env_name, lib, driver)
        criteria = derive(arm, readings, floors, lib)
        gate = gate_roll(arm, criteria, lib)
        flags = degenerate_shapes(arm, readings, lib)
        defects = green_audit(arm, criteria, readings, gate, lib)
        results.append({"arm": arm, "dsn_env": env_name,
                        "blocked": readings.get("blocked", ""),
                        "detail": readings.get("detail", ""),
                        "identity": readings.get("identity"),
                        "readings": {"accounts": readings.get("accounts"),
                                     "labels": readings.get("labels"),
                                     "tiers": readings.get("tiers")},
                        "criteria": criteria, "gate": gate, "shapes": flags,
                        "defects": defects,
                        "rc": arm_rc(arm, readings, criteria, gate, flags, defects, lib, driver)})
    return results


def arm_line(item, tool_tag):
    criteria = item["criteria"]
    named = "、".join(sorted({value for value in
                              [item.get("blocked", ""), *item.get("shapes", []),
                               *[c["reason"] for c in criteria.values()]] if value}))
    return ("[R547]{0} {1} rc={2} 判定={3} (a){4} (b){5} (c){6} (d){7} 点名={8}".format(
        tool_tag, item.get("arm") or item.get("shape"), item.get("rc"),
        (item.get("gate") or {}).get("verdict", item.get("gate_verdict", "")),
        criteria["a_subject_department"]["verdict"], criteria["b_corpus_labels"]["verdict"],
        criteria["c_recall_positive"]["verdict"], criteria["d_zero_breach"]["verdict"],
        named or "无"))


def emit(results, payload, rc):
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    for item in results:
        print(arm_line(item, ""))
    print("[R547][末行] rc={0}｜关门只认生产臂那四件｜🔴 本件不宣布格③／C 门翻绿".format(rc))
    return rc


def build_parser():
    parser = argparse.ArgumentParser(prog=TOOL, description="R547 越权格四件判据的只读派生量具")
    parser.add_argument("--mode", choices=("live", "reread", "shapes"), default="live")
    parser.add_argument("--arm", choices=("production", "sandbox", "both"), default="both")
    parser.add_argument("--gate", choices=("production", "sandbox", "none"), default="production",
                        help="要拿哪一臂关门；选 sandbox 当场拒（两臂不许互相顶替）")
    parser.add_argument("--readout", default=READOUT_REL, help="reread 那道读的在册读数件")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    lib, driver = load_instruments()
    floors = plan_floors()
    refused = int(getattr(driver, "EXIT_REFUSED", 3))
    if args.mode == "shapes":
        results = run_shapes(lib, driver, floors)
        broken = [item["shape"] for item in results if not item["teeth_ok"]]
        print(json.dumps({"mode": "shapes", "fixture": FIXTURE_MARK, "floors": floors,
                          "teeth_broken": broken, "results": results},
                         ensure_ascii=False, indent=2, sort_keys=True))
        for item in results:
            print(arm_line(item, "[夹具]"))
        rc = lib.EXIT_PRECONDITION if broken else lib.EXIT_OK
        print("[R547][末行] {0}｜三形各自 rc={1}｜本道 rc={2} 只代表三形各自红了且各自点了名，"
              "不代表任何一格量到了东西{3}".format(
                  FIXTURE_MARK, [item["rc"] for item in results], rc,
                  "" if not broken else "｜失守的形状：" + "、".join(broken)))
        return rc
    if args.mode == "reread":
        payload = run_reread(args.readout, lib, driver)
        payload["floors"] = floors
        payload["mode"] = "reread"
        if payload.get("defects"):
            print("[拒绝] {0}".format("；".join(payload["defects"])))
            return refused
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        sand = payload["arms"][lib.ARM_SANDBOX]
        print("[R547][末行] mode=reread 状态={0}｜沙盒臂有牙格 {1} 枚／越权 {2} 条／无谓词对照本可越界 {3} 条／"
              "无部门谓词那档池外 {4} 枚（裁定原文那句沙盒枚数={5}）／本臂写入 {6} 枚｜{7}".format(
                  payload["status"], sand["teeth_cells"], sand["breaches"],
                  sand["counterfactual_total"], sand["no_predicate_outside"],
                  payload["ruling_synth_count"], sand["synth_rows"], SANDBOX_NEVER_CLOSES_GATE))
        return lib.EXIT_OK
    arm_list = list(lib.ARMS) if args.arm == "both" else (args.arm,)
    if args.gate == "sandbox":
        print("[拒绝] {0}：{1}".format(ARM_SUBSTITUTION_REFUSED, SANDBOX_NEVER_CLOSES_GATE))
        return refused
    results = run_live(arm_list, lib, driver, floors)
    gate_arm = next((item for item in results if item["arm"] == args.gate), None)
    if args.gate != "none" and gate_arm is None:
        print("[前置不满足] 要求由 {0} 臂关门，可它不在 --arm 里".format(args.gate))
        return lib.EXIT_PRECONDITION
    payload = {"mode": "live", "arms": list(arm_list), "gate_requested": args.gate,
               "gate": None if gate_arm is None else gate_arm["gate"],
               "floors": floors, "rulings": owner_rulings(), "results": results}
    return emit(results, payload, aggregate_rc(results, lib, driver))


if __name__ == "__main__":
    sys.exit(main())