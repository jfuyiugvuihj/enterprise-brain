# -*- coding: utf-8 -*-
"""R445 · 「[PromptPack]」 装箱硬顶的只读取证件（跟进单 §121 判据 ①，沿用 R429 写域）。

🔴 只读：不联网、不起服务、不打模型、不动数据库、不碰 chroma_db/**、不写任何文件。
输入＝仓内源码（AST 现读）＋ run9 真机后端日志快照 ＋ sidecar ＋ 收窗判读件；
输出＝stdout 这一份报告。读不出来的东西逐条打「MISS」并指名「读不到哪一格」，
绝不静默跳过，也绝不拿判读件的汇总数顶替逐行读数。

五格口径（每一格都可失败）：
- ① 源码面：装箱口、调用点、门槛分支、room 算式的行号与原文一律 AST/文本现读。
  判 keep_first_truncated 默认值可不可达只看**调用点实参**，不看签名
  （跟进单 §121 判据 ①：本仓为这病开过一整族单）。
- ② 真机面：run9 窗内「[PromptPack]」逐行读数；fitted=0 的形态按 stub 分档，
  档位边界从日志现读，不抄常数。
- ③ 归因面：装箱行不带题号，只能用 sidecar 的 ts/wall_ms 反推窗口；
  窗口交叠的行并列点名，不许假装归属唯一。
- ④ 单价面：fitted=0 里有多少发「其实装得下一条」——台账不逐条记候选单价，
  所以只给两把下界尺（该腿实测最便宜整条单价／标记＋门槛线），并指名真值量不到。
- ⑤ 对账面：与收窗判读件同一格两个口径各量一遍，不等就点名 DIVERGE，不和稀泥。

用法（路径全部由本文件位置推导，cwd 不敏感）：
    python scripts/r445_pack_forensics.py
    python scripts/r445_pack_forensics.py --log D:run9-backend-full.log --strict-queue
退出码：MISS 为正 ⇒ 1；全格闭合 ⇒ 0。
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOOLS_REL = os.path.join("app", "agents", "tools.py")
PIPELINE_REL = os.path.join("app", "rag", "retrieval_pipeline.py")
CONTRACTS_REL = os.path.join("app", "agents", "contracts.py")
BUDGET_REL = os.path.join("app", "common", "model_budget.py")
ORCHESTRATOR_REL = os.path.join("app", "agents", "orchestrator.py")
READOUT_REL = os.path.join("docs", "testing", "run9-readout-2026-09-28.md")

TEMP_EVALRUN = os.path.join(os.environ.get("TEMP", ""), "evalrun")
DEFAULT_LOG = os.environ.get("R445_PACK_LOG") or os.path.join(TEMP_EVALRUN, "run9-backend-full.log")
DEFAULT_SIDECAR = os.environ.get("R445_PACK_SIDECAR") or os.path.join(TEMP_EVALRUN, "sidecar-run9.jsonl")
DEFAULT_RUN9C = os.environ.get("R445_PACK_RUN9C") or os.path.join(TEMP_EVALRUN, "sidecar-run9c.jsonl")

#: 调用点扫描范围：产品面（app/）单独计数，scripts/ 与 tests/ 里的直调只列不合并。
SCAN_ROOTS = ("app", "scripts", "tests")

PACKER = "_pack_into_prompt_room"
KEY_FUNC = "_pack_ledger_key"
PREFIX_FUNC = "pack_prefix_by_rank"
INT_FIELDS = ("room_total", "room_left", "candidates", "fitted", "dropped", "truncated",
              "packed_tokens", "ledger_packed_tokens", "prompt_estimate_tokens")

#: 在册字段序的解析尺（tests/test_r117_* 与 tests/test_r122_* 各钉一份，本件是第三把）。
TOOL_LINE = re.compile(
    r"leg=(?P<leg>\w+) tier=(?P<tier>\w+) room_total=(?P<room_total>\d+) "
    r"room_left=(?P<room_left>\d+) candidates=(?P<candidates>\d+) fitted=(?P<fitted>\d+) "
    r"dropped=(?P<dropped>\d+) truncated=(?P<truncated>\d+) stub=(?P<stub>\w+) "
    r"packed_tokens=(?P<packed_tokens>\d+) ledger_packed_tokens=(?P<ledger_packed_tokens>\d+) "
    r"prompt_estimate_tokens=(?P<prompt_estimate_tokens>\d+) ledger=(?P<ledger>\w+)"
)
#: 检索腿那一行字段更少（没有 room_total/stub），分开数，不混进上面那把尺。
RETRIEVAL_LINE = re.compile(
    r"leg=retrieval tier=(?P<tier>\w+) room=(?P<room>\d+) candidates=(?P<candidates>\d+) "
    r"fitted=(?P<fitted>\d+) dropped=(?P<dropped>\d+) packed_tokens=(?P<packed_tokens>\d+)"
)
EVIDENCE_BAG_LINE = re.compile(r"leg=\w+ dataset=\S+ recorded=false")
STAMP = re.compile(r"^(?P<date>\d{4}-\d\d-\d\d) (?P<time>\d\d:\d\d:\d\d)")
REFUSAL_WARNING = re.compile(
    r"\[ModelBudget\] tier=(?P<tier>\w+).*?prompt_tokens=(?P<prompt_tokens>\d+).*?"
    r"over_by_tokens=(?P<over_by_tokens>\d+) required_n_ctx=(?P<required_n_ctx>\d+) n_ctx=(?P<n_ctx>\d+)"
)
REFUSAL_ERROR = re.compile(r"error_code=context_limit_exceeded")

#: 装箱「整批归零」那两种形状的源码标记：改前只看 units[0]，改后要按名次往下找。
#: 改前那枚形状的原文（只看第一名）：这一串今天已经从源码里消失，它还在＝守卫被摘回去了。
#: 不取 "if not fitted and units and keep_first_truncated:" 那一行，因为那一行改前改后逐字
#: 相同（它是守卫条件，不是病灶），拿它当标记会让这一格永远读成"病灶还在"。
OLD_SHAPE_MARK = "head = _fit_unit_to_room(str(units[0]), room)"
RESCUE_SHAPE_MARK = "for index, unit in enumerate(units):"


def _read(path):
    """读文本；不存在或读不动就返回 None，由调用方打 MISS，这一步不吞任何东西。"""
    if not path or not os.path.isfile(path):
        return None
    try:
        with io.open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _lines(text):
    return (text or "").splitlines()


def _lines_enum(text):
    return [(index + 1, line.strip()) for index, line in enumerate(_lines(text))]


def _verbatim(text, lineno):
    lines = _lines(text)
    return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else "?"


def _module_literal(text, name):
    """模块级字面量：返回 (值, 行号)；读不到返回 (None, None)，由调用方指名。"""
    if text is None:
        return None, None
    for node in ast.walk(ast.parse(text)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        if not targets or getattr(node, "value", None) is None:
            continue
        if any(t.id == name for t in targets):
            try:
                return ast.literal_eval(node.value), node.lineno
            except (ValueError, TypeError, SyntaxError):
                return None, node.lineno
    return None, None


def _def_span(text, name):
    """def 的行号范围与那一行签名原文；读不到返回 (None, None, None)。"""
    if text is None:
        return None, None, None
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", None) or node.lineno
            return node.lineno, end, _verbatim(text, node.lineno)
    return None, None, None


def _kwonly_defaults(text, name):
    """keyword-only 形参的默认值原文（判默认值只看签名能得到的全部，也就只有这么多）。"""
    if text is None:
        return {}
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return {arg.arg: (ast.unparse(default) if default is not None else "<无默认>")
                    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)}
    return {}


def _call_sites(text, name, origin):
    """这一份源码里对 name(...) 的每一个调用点：行号＋实参原文。"""
    out = []
    if text is None or ("%s(" % name) not in text:
        return out
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        fname = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if fname != name:
            continue
        kwargs = {kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg}
        out.append({
            "origin": origin,
            "line": node.lineno,
            "keep_first_truncated": kwargs.get("keep_first_truncated"),
            "leg": kwargs.get("leg"),
            "verbatim": _verbatim(text, node.lineno),
        })
    return out


def _needle_lines(text, rel, needle, label, miss, span=None):
    """按字面量找行：一行都读不到就 MISS（判据「读不出要指名」）；多行如实全列。"""
    lines = _lines(text)
    low, high = span or (1, len(lines))
    found = [(index, lines[index - 1].strip())
             for index in range(max(1, low), min(high, len(lines)) + 1) if needle in lines[index - 1]]
    if not found:
        miss.append("MISS 源码面 %s：%r 在 %s:%d-%d 一行都读不到" % (label, needle, rel, low, high))
    return found


# ==================== ① 源码面 ====================

def code_face(miss, report):
    """装箱口/调用点/门槛分支/room 算式：行号与原文全部现读，一条都不许手抄。"""
    tools = _read(os.path.join(REPO, TOOLS_REL))
    pipeline = _read(os.path.join(REPO, PIPELINE_REL))
    contracts = _read(os.path.join(REPO, CONTRACTS_REL))
    budget = _read(os.path.join(REPO, BUDGET_REL))
    orchestrator = _read(os.path.join(REPO, ORCHESTRATOR_REL))
    for label, text, rel in (("tools", tools, TOOLS_REL), ("retrieval_pipeline", pipeline, PIPELINE_REL),
                             ("contracts", contracts, CONTRACTS_REL), ("model_budget", budget, BUDGET_REL),
                             ("orchestrator", orchestrator, ORCHESTRATOR_REL)):
        if text is None:
            miss.append("MISS 源码面：%s 读不到（%s）" % (label, rel))
    if tools is None or pipeline is None:
        return None

    start, end, signature = _def_span(tools, PACKER)
    if start is None:
        miss.append("MISS 源码面：装箱口 %s 在 %s 里找不到定义" % (PACKER, TOOLS_REL))
    else:
        report("SRC", "%s:%d-%d def %s" % (TOOLS_REL, start, end, signature))
        defaults = _kwonly_defaults(tools, PACKER)
        report("SRC", "签名默认值 keep_first_truncated=%s（只看签名判不了可达性，看下面 CALL 行）"
               % defaults.get("keep_first_truncated"))

    sites = []
    for root in SCAN_ROOTS:
        base = os.path.join(REPO, root)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, REPO).replace(os.sep, "/")
                sites.extend(_call_sites(_read(path), PACKER, rel))
    if not sites:
        miss.append("MISS 源码面：全仓读不到一处 %s 调用点" % PACKER)
    in_app = [s for s in sites if s["origin"].startswith("app/")]
    product = sorted(in_app, key=lambda s: (s["origin"], s["line"]))
    outside = sorted([s for s in sites if s not in in_app], key=lambda s: (s["origin"], s["line"]))
    for site in product + outside:
        report("CALL", "%s:%s leg=%s keep_first_truncated=%s scope=%s | %s"
               % (site["origin"], site["line"], site["leg"], site["keep_first_truncated"],
                  "产品" if site in in_app else "非产品", site["verbatim"]))
    literal_true = [s for s in product if s["keep_first_truncated"] == "True"]
    reachable = bool(product) and len(literal_true) != len(product)
    report("VERDICT", "产品调用点 %d 处，逐处显式 True %d 处 ⇒ 默认值在产品路径上%s；非产品直调 %d 处不合并计数"
           % (len(product), len(literal_true), "可达" if reachable else "不可达", len(outside)))

    floor_value, floor_line = _module_literal(tools, "PACK_MIN_STUB_BODY_TOKENS")
    if floor_line is None:
        miss.append("MISS 源码面：门槛常量 PACK_MIN_STUB_BODY_TOKENS 读不到值")
    else:
        report("SRC", "%s:%d PACK_MIN_STUB_BODY_TOKENS=%r" % (TOOLS_REL, floor_line, floor_value))
    mark_value, mark_line = _module_literal(tools, "PACK_TRUNCATION_MARK")
    if mark_line is None:
        miss.append("MISS 源码面：PACK_TRUNCATION_MARK 读不到")
    else:
        report("SRC", "%s:%d PACK_TRUNCATION_MARK=%r" % (TOOLS_REL, mark_line, mark_value))
    for const in ("PACK_STUB_NONE", "PACK_STUB_KEPT", "PACK_STUB_REFUSED"):
        value, line = _module_literal(tools, const)
        if line is None:
            miss.append("MISS 源码面：%s 读不到" % const)
        else:
            report("SRC", "%s:%d %s=%r" % (TOOLS_REL, line, const, value))
    for func in (KEY_FUNC, "_fit_unit_to_room", "_stub_body_tokens", "_pack_kept_hits"):
        s, e, sig = _def_span(tools, func)
        if s is None:
            miss.append("MISS 源码面：函数 %s 找不到" % func)
        else:
            report("SRC", "%s:%d-%d def %s" % (TOOLS_REL, s, e, func))

    for label, needle in (("桩被门槛拦下的赋值", "stub = PACK_STUB_REFUSED"),
                          ("桩达标交出的赋值", "stub = PACK_STUB_KEPT"),
                          ("门槛比较式", ">= PACK_MIN_STUB_BODY_TOKENS")):
        for line, verbatim in _needle_lines(tools, TOOLS_REL, needle, label, miss):
            report("BRANCH", "%s:%d [%s] %s" % (TOOLS_REL, line, label, verbatim))

    old_hits = [(i, v) for i, v in _lines_enum(tools) if OLD_SHAPE_MARK in v]
    rescue_hits = [(i, v) for i, v in _lines_enum(tools) if RESCUE_SHAPE_MARK in v]
    report("SHAPE", "改前形状（只看 units[0] 那一发）标记 %d 处；按名次往下找（%s）标记 %d 处"
           % (len(old_hits), RESCUE_SHAPE_MARK, len(rescue_hits)))
    for line, verbatim in old_hits[:2]:
        report("SHAPE", "  %s:%d %s" % (TOOLS_REL, line, verbatim))
    for line, verbatim in rescue_hits[:4]:
        report("SHAPE", "  %s:%d %s" % (TOOLS_REL, line, verbatim))
    if not old_hits and not rescue_hits:
        miss.append("MISS 源码面：两种装箱形状都读不到，本件无法说明今天的病是哪一个")

    s, e, sig = _def_span(pipeline, PREFIX_FUNC)
    if s is None:
        miss.append("MISS 源码面：%s 在 %s 里找不到定义" % (PREFIX_FUNC, PIPELINE_REL))
    else:
        report("SRC", "%s:%d-%d def %s（R220 的桶账按这一份算法复算，语义一枚不许动）"
               % (PIPELINE_REL, s, e, sig))
        for line, verbatim in _needle_lines(pipeline, PIPELINE_REL, "break", "整批退出的那一句", miss, span=(s, e)):
            report("BRANCH", "%s:%d [整批退出] %s" % (PIPELINE_REL, line, verbatim))

    shell, shell_line = _module_literal(pipeline, "CONTEXT_SHELL_RESERVE_TOKENS")
    history, history_line = _module_literal(pipeline, "CONTEXT_HISTORY_RESERVE_TOKENS")
    pack_tier, pack_tier_line = _module_literal(pipeline, "CONTEXT_PACK_TIER")
    for label, value, line in (("CONTEXT_SHELL_RESERVE_TOKENS", shell, shell_line),
                               ("CONTEXT_HISTORY_RESERVE_TOKENS", history, history_line),
                               ("CONTEXT_PACK_TIER", pack_tier, pack_tier_line)):
        if line is None:
            miss.append("MISS 源码面：%s 读不到" % label)
        else:
            report("ROOM", "%s:%d %s=%r" % (PIPELINE_REL, line, label, value))
    for needle, label, rel, source in (
        ("def context_pack_room", "room 算式", PIPELINE_REL, pipeline),
        ("def context_pack_capacity", "容量真源（该档 input_budget_tokens）", PIPELINE_REL, pipeline),
        ("def input_budget_tokens", "contracts 里那枚性质", CONTRACTS_REL, contracts),
        ("CONTEXT_LIMIT_CODE = ", "拒绝码定义（只读引用）", CONTRACTS_REL, contracts),
        ("def context_window_code", "判拒的那一函数", CONTRACTS_REL, contracts),
        ("class ModelContextLimitExceeded", "拒绝对象（prompt_tokens/over_by_tokens 的出处）", BUDGET_REL, budget),
    ):
        for line, verbatim in _needle_lines(source, rel, needle, label, miss):
            report("GUARD", "%s:%d [%s] %s" % (rel, line, label, verbatim))
    #: 账本键的成因：step_id 由装配点造成 {trace_id}:worker:{name}，所以键天然含 worker。
    for line, verbatim in _needle_lines(orchestrator, ORCHESTRATOR_REL, 'step_id = f"{trace_id}:worker:{name}"',
                                         "step_id 的成因行", miss):
        report("LEDGER", "%s:%d [账本键成因] %s" % (ORCHESTRATOR_REL, line, verbatim))
    default_ctx, default_ctx_line = _module_literal(budget, "DEFAULT_CONTEXT_TOKENS")
    default_min, default_min_line = _module_literal(budget, "DEFAULT_MIN_ANSWER_TOKENS")
    for label, value, line in (("DEFAULT_CONTEXT_TOKENS", default_ctx, default_ctx_line),
                               ("DEFAULT_MIN_ANSWER_TOKENS", default_min, default_min_line)):
        if line is None:
            miss.append("MISS 源码面：%s 读不到（本件只读它，不动它）" % label)
        else:
            report("ROOM", "%s:%d %s=%r（缺省值，本单不许动）" % (BUDGET_REL, line, label, value))
    return {"floor": floor_value, "mark": mark_value, "shell": shell, "history": history, "tier": pack_tier,
            "defaults": {"keep_first_truncated": _kwonly_defaults(tools, PACKER).get("keep_first_truncated")}}


def truth_source_room(miss, report, facts):
    """真源读数：现场算 room，与 AST 现读的两枚预留对账（两把尺不等就 MISS）。"""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    try:
        from app.rag.retrieval_pipeline import context_pack_capacity, context_pack_room
    except Exception as exc:
        miss.append("MISS 真源面：import 失败（%s: %s）⇒ room 现场算不出" % (type(exc).__name__, exc))
        return None, None
    capacity, room = int(context_pack_capacity()), int(context_pack_room())
    report("ROOM", "真源现读 context_pack_capacity=%d context_pack_room=%d" % (capacity, room))
    if facts and None not in (facts.get("shell"), facts.get("history")):
        derived = capacity - facts["shell"] - facts["history"]
        report("RECON", "AST 两枚预留推得的 room=%d vs 真源 room=%d %s"
               % (derived, room, "MATCH" if derived == room else "DIVERGE"))
        if derived != room:
            miss.append("MISS 真源面：room 两把尺不等（AST 推 %d / 真源 %d）" % (derived, room))
    return capacity, room


# ==================== ② 真机面 ====================

def log_face(text, miss, report):
    if text is None:
        miss.append("MISS 真机面：run9 后端日志快照读不到（--log 指定；默认 %s）" % DEFAULT_LOG)
        return None
    tool_rows, ret_rows, bag_rows, unparsed = [], [], [], []
    for line in _lines(text):
        if "[PromptPack]" not in line:
            continue
        stamp = STAMP.match(line)
        match = TOOL_LINE.search(line)
        if match:
            row = dict(match.groupdict())
            for key in INT_FIELDS:
                row[key] = int(row[key])
            row["at"] = stamp.group(0) if stamp else "?"
            row["clock"] = (stamp.group("date"), stamp.group("time")) if stamp else None
            tool_rows.append(row)
            continue
        match = RETRIEVAL_LINE.search(line)
        if match:
            row = dict(match.groupdict())
            for key in ("room", "candidates", "fitted", "dropped", "packed_tokens"):
                row[key] = int(row[key])
            row["at"] = stamp.group(0) if stamp else "?"
            ret_rows.append(row)
            continue
        if EVIDENCE_BAG_LINE.search(line):
            bag_rows.append(line)
            continue
        unparsed.append(line)
    if not tool_rows:
        miss.append("MISS 真机面：带 room_total 的装箱行一枚都解析不出（在册形状变了）")
        return None
    if unparsed:
        miss.append("MISS 真机面：%d 行含 [PromptPack] 但按在册形状解析不出，前 3 行：%s"
                    % (len(unparsed), " || ".join(row[:90] for row in unparsed[:3])))
    report("LOG", "装箱行（在册形状）n=%d · 检索腿行 n=%d · 证据袋行 n=%d"
           % (len(tool_rows), len(ret_rows), len(bag_rows)))
    report("LOG", "装箱行 leg 计数=%s · ledger 键计数=%s"
           % (dict(Counter(r["leg"] for r in tool_rows)), dict(Counter(r["ledger"] for r in tool_rows))))
    zero = [r for r in tool_rows if r["fitted"] == 0 and r["dropped"] > 0]
    report("LOG", "fitted=0 且 dropped>0：%d 行；按 leg=%s"
           % (len(zero), dict(Counter(r["leg"] for r in zero))))
    report("LOG", "stub 计数（全体装箱行）=%s" % dict(Counter(r["stub"] for r in tool_rows)))
    report("LOG", "room_total 全体取值=%s（档位边界从日志现读，不抄常数）"
           % sorted({r["room_total"] for r in tool_rows}))
    for value in ("none", "kept", "refused"):
        span = sorted(r["room_left"] for r in zero if r["stub"] == value)
        report("LOG", "fitted=0 且 stub=%s：n=%d room_left 区间=%s"
               % (value, len(span), "[%d, %d]" % (span[0], span[-1]) if span else "无"))
    all_zero = sorted(r["room_left"] for r in zero)
    report("LOG", "fitted=0 全体 room_left 区间=[%d, %d] n=%d" % (all_zero[0], all_zero[-1], len(all_zero)))
    ret_zero = [r for r in ret_rows if r["fitted"] == 0 and r["dropped"] > 0]
    report("LOG", "检索腿 fitted=0 且 dropped>0：%d / %d 行" % (len(ret_zero), len(ret_rows)))
    #: ERROR 与 WARNING 两族分开数：判读件那句「ERROR=2 · WARNING=2 · 合计行=4」用的就是两把尺，
    #: 合在一起数会把同一笔拒绝记成两行（量具自己的口径漂移，R393 那一族同形）。
    refusals = [line for line in _lines(text) if REFUSAL_ERROR.search(line) and "[ERROR]" in line]
    warnings = []
    for line in _lines(text):
        match = REFUSAL_WARNING.search(line)
        if match:
            row = dict(match.groupdict())
            for key in ("prompt_tokens", "over_by_tokens", "required_n_ctx", "n_ctx"):
                row[key] = int(row[key])
            row["at"] = STAMP.match(line).group(0) if STAMP.match(line) else "?"
            warnings.append(row)
    report("LOG", "本窗 context_limit_exceeded：ERROR 行=%d · ModelBudget(WARNING) 行=%d"
           % (len(refusals), len(warnings)))
    for row in warnings:
        report("LOG", "  拒绝读数 %s tier=%s prompt_tokens=%d required_n_ctx=%d n_ctx=%d over_by_tokens=%d"
               % (row["at"], row["tier"], row["prompt_tokens"], row["required_n_ctx"], row["n_ctx"],
                  row["over_by_tokens"]))
    return {"tool_rows": tool_rows, "ret_rows": ret_rows, "zero": zero,
            "warnings": warnings, "refusal_count": len(refusals)}


# ==================== ③ 归因面 ====================

def sidecar_windows(path, miss, report):
    text = _read(path)
    if text is None:
        miss.append("MISS 归因面：sidecar 读不到（%s）⇒ 装箱行的题号归属今天取不到" % path)
        return None
    windows = []
    for line in _lines(text):
        if not line.strip():
            continue
        row = json.loads(line)
        try:
            end = datetime.strptime(row["ts"], "%Y-%m-%d %H:%M:%S").timestamp()
            start = end - float(row["wall_ms"]) / 1000.0
        except (KeyError, TypeError, ValueError):
            miss.append("MISS 归因面：sidecar 里 %s 这行缺 ts/wall_ms，窗口算不出" % row.get("id"))
            continue
        windows.append((start, end, row["id"], row))
    report("ATTR", "sidecar 窗口 n=%d（ts 按终态时刻读：拒绝 ERROR 那一行的时刻与 metric-02 的 ts 同秒，"
                   "两格读数在同一件里对得上，见 LOG 与 ROW）" % len(windows))
    return windows


def owners_of(windows, moment):
    return [qid for start, end, qid, _ in (windows or []) if start - 1.0 <= moment <= end + 1.0]


def _moment(row):
    return datetime.strptime("%s %s" % row["clock"], "%Y-%m-%d %H:%M:%S").timestamp()


def attribution(log, windows, miss, report):
    if log is None:
        return
    #: 判据正文点名要 metric-02 那一族行；metric-07 是 room_left=32 那一发的窗口主人（见 CITED）。
    for qid in ("metric-02", "metric-07"):
        row = next((w for w in (windows or []) if w[2] == qid), None)
        if row is None:
            miss.append("MISS 归因面：sidecar 没有 %s 的行，取不到它的窗口" % qid)
            continue
        start, end, _, side = row
        rows = [r for r in log["tool_rows"] if r["clock"] and start - 1 <= _moment(r) <= end + 1]
        report("ATTR", "%s 窗口=%s→%s wall_ms=%s kind=%s sentinel=%s answer_chars=%s evidence_n=%s"
               % (qid, side["ts"], datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M:%S"),
                  side["wall_ms"], side["kind"], side["sentinel"], side["answer_chars"], side["evidence_n"]))
        report("ATTR", "  窗口内装箱行 n=%d leg 计数=%s fitted=0 行 n=%d stub 计数=%s"
               % (len(rows), dict(Counter(r["leg"] for r in rows)),
                  sum(1 for r in rows if r["fitted"] == 0), dict(Counter(r["stub"] for r in rows))))
        for r in rows:
            report("ROW", "  %s leg=%s room_left=%d candidates=%d fitted=%d dropped=%d truncated=%d "
                   "stub=%s packed_tokens=%d ledger_packed_tokens=%d 窗口归属=%s"
                   % (r["at"], r["leg"], r["room_left"], r["candidates"], r["fitted"], r["dropped"],
                      r["truncated"], r["stub"], r["packed_tokens"], r["ledger_packed_tokens"],
                      owners_of(windows, _moment(r))))
    cited = [r for r in log["tool_rows"] if r["room_left"] == 32]
    if not cited:
        miss.append("MISS 归因面：整窗读不到 room_left=32 的装箱行（跟进单 §121 病灶那句引用的就是它）")
    for r in cited:
        named = owners_of(windows, _moment(r))
        tag = "AMBIGUOUS（多题窗口交叠）" if len(named) > 1 else ("UNOWNED（不在任何窗口）" if not named else "")
        report("CITED", "room_left=32 那一发：时刻=%s leg=%s candidates=%d fitted=%d dropped=%d stub=%s "
               "窗口归属=%s %s" % (r["at"], r["leg"], r["candidates"], r["fitted"], r["dropped"], r["stub"],
                                   named, tag))
    ambiguous = sum(1 for r in log["tool_rows"] if r["clock"] and len(owners_of(windows, _moment(r))) > 1)
    unowned = sum(1 for r in log["tool_rows"] if r["clock"] and not owners_of(windows, _moment(r)))
    report("ATTR", "整窗装箱行：窗口交叠（归属不唯一）%d 行 · 不属任何窗口 %d 行 / 共 %d 行 ⇒ 逐行题号归属只能到窗口这一层"
           % (ambiguous, unowned, len(log["tool_rows"])))


# ==================== ④ 单价尺 ====================

def price_rulers(log, facts, miss, report):
    if log is None:
        return None
    #: 尺一：fitted=1 truncated=0 stub=none 那一发的 packed_tokens 就是一条整料的实价；
    #: 每腿取最小＝该腿实测最便宜整条单价（下界：样本只到「发出去过一条」那些发）。
    singles = [r for r in log["tool_rows"] if r["fitted"] == 1 and r["truncated"] == 0 and r["stub"] == "none"]
    rulers = {}
    if not singles:
        miss.append("MISS 单价面：读不到 fitted=1 truncated=0 的行，尺一算不出来")
    else:
        for leg in sorted({r["leg"] for r in singles}):
            prices = sorted(r["packed_tokens"] for r in singles if r["leg"] == leg)
            rulers[leg] = prices[0]
            report("RULER", "尺一 leg=%s：单发整条实价 n=%d 最小=%d 中位=%d"
                   % (leg, len(prices), prices[0], prices[len(prices) // 2]))
    if facts and facts.get("mark"):
        mark_cost = _token_cost(facts["mark"], miss)
        if mark_cost is not None:
            report("RULER", "尺二：截断标记单价=%d（真源现算）· 门槛 PACK_MIN_STUB_BODY_TOKENS=%s ⇒ "
                   "裁得出桩还要 room 大于标记，桩要够读还要 room 不小于 行头+标记+门槛（行头逐条台账不记）"
                   % (mark_cost, facts.get("floor")))
    rescued = 0
    for leg, cheap in sorted(rulers.items()):
        zeros = [r for r in log["zero"] if r["leg"] == leg]
        fit = [r for r in zeros if r["room_left"] >= cheap]
        rescued += len(fit)
        report("RULER", "leg=%s：fitted=0 行 %d，其中 room_left 不小于 尺一(%d) 的 %d 行，取值=%s"
               % (leg, len(zeros), cheap, len(fit), sorted({r["room_left"] for r in fit})))
    below = [r for r in log["zero"] if r["room_left"] < rulers.get(r["leg"], 0)]
    report("VERDICT", "本单这一格在 run9 真机窗上的可救上界=%d / %d 行 fitted=0；其余 %d 行 room_left 连该腿最便宜整条都不到，"
           "改完也仍空手（那是诚实零手，不是缺陷）" % (rescued, len(log["zero"]), len(below)))
    report("VERDICT", "改装箱不会消灭本窗的 context_limit_exceeded：拒绝读数（LOG 那几行）与 room 装不装得满是两件事，"
           "超限那一半在窗口配置与预留尺上，不在本单写域")
    DECLARED.append("DECLARED 单价面：逐条候选单价台账不记 ⇒ 上面两把都是下界尺，"
                "「这一发到底有没有整料装得下」的逐行真值今天量不到（具名申报，不静默）")
    return rulers


def _token_cost(text, miss):
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    try:
        from app.common.model_budget import estimate_text_tokens
    except Exception as exc:
        miss.append("MISS 单价面：estimate_text_tokens 读不到（%s: %s）" % (type(exc).__name__, exc))
        return None
    return int(estimate_text_tokens(text or ""))


# ==================== ⑤ run9c 队列道 ====================

def queue_face(path, strict_queue, miss, report):
    text = _read(path)
    if text is None:
        miss.append("MISS 队列道：run9c 的 sidecar 读不到（%s）⇒ 队列道结局今天取不到" % path)
        return
    rows = [json.loads(line) for line in _lines(text) if line.strip()]
    report("QUEUE", "run9c sidecar n=%d kind 计数=%s" % (len(rows), dict(Counter(str(r.get("kind")) for r in rows))))
    dead = [row for row in rows if row.get("kind") == "queued_dead"]
    if not dead:
        miss.append("MISS 队列道：run9c 读不到 kind=queued_dead 的行（工单点名 report-04）")
    for row in dead:
        report("QUEUE", "  死题 id=%s sentinel=%s answer_chars=%s evidence_n=%s wall_ms=%s ts=%s attempt=%s"
               % (row.get("id"), row.get("sentinel"), row.get("answer_chars"), row.get("evidence_n"),
                  row.get("wall_ms"), row.get("ts"), row.get("attempt")))
    named = ("MISS 队列道：本机没有 run9c 的后端日志快照（TEMP 那个 evalrun 目录只有 sidecar/answers/frames，"
             "全仓 grep 工单给的 request_id 也只命中跟进单正文自己那一句）⇒ 同一 request_id 连发拒绝的逐行 "
             "prompt_tokens/over_by_tokens 本件量不到，只能引用总控 2026-09-28 14:19 交回的读数，不由本件复核")
    if strict_queue:
        miss.append(named)
    else:
        report("PARTIAL", named[len("MISS "):])


# ==================== 与判读件对账（第二把量具） ====================

#: 「结构上今天量不到」与「该读到却没读到」分家：前者进 DECLARED（逐字点名、不挡退出码），
#: 后者进 MISS（退出码非零）。把量不到混成失败，或者把失败混成量不到，都是假话。
DECLARED = []

READOUT_CELLS = (
    ("parsed", r"PromptPack 解析成功行数=(\d+)", "tool_rows"),
    ("carrier_lines", r"含该字样行数=(\d+)", None),
    ("zero_rows", r"fitted=0 且 dropped>0 计数=(\d+)", "zero"),
    ("stub_none", r"'none': (\d+)", "stub_none"),
    ("stub_kept", r"'kept': (\d+)", "stub_kept"),
    ("stub_refused", r"'refused': (\d+)", "stub_refused"),
)


def _mine(key, log):
    if key == "tool_rows":
        return len(log["tool_rows"])
    if key == "zero":
        return len(log["zero"])
    if key == "stub_none":
        return sum(1 for r in log["tool_rows"] if r["stub"] == "none")
    if key == "stub_kept":
        return sum(1 for r in log["tool_rows"] if r["stub"] == "kept")
    if key == "stub_refused":
        return sum(1 for r in log["tool_rows"] if r["stub"] == "refused")
    return None


def reconcile(readout_text, log, report, miss):
    if readout_text is None:
        miss.append("MISS 对账面：收窗判读件读不到（%s）" % READOUT_REL)
        return
    if log is None:
        return
    for key, pattern, which in READOUT_CELLS:
        match = re.search(pattern, readout_text)
        if not match:
            miss.append("MISS 对账面：判读件里读不到 %s 那一格（pattern %r）" % (key, pattern))
            continue
        want = int(match.group(1))
        mine = _mine(which, log) if which else None
        if mine is None:
            report("RECON", "%s: 判读件=%d（本件无同格读数，只做见证）" % (key, want))
            continue
        verdict = "MATCH" if mine == want else "DIVERGE"
        report("RECON", "%s: 本件=%d 判读件=%d %s" % (key, mine, want, verdict))
        if verdict == "DIVERGE":
            miss.append("MISS 对账面：%s 两把量具不等（本件 %d / 判读件 %d）" % (key, mine, want))


# ==================== 账本面（同腿续账 / 跨腿共享，按题窗判） ====================

def ledger_face(log, windows, report, miss):
    """把「doc/data/query 在同一轮里怎么排队」这件事落到窗口内的累加账上。

    台账每行都有 ledger_packed_tokens（本发之后这一本账的总额）与 packed_tokens
    （本发自己交出去的），相减就是这一发之前的余额。

    换一本新账的可见签名：room_left 回到 room_total。本窗里这一条与「发前余额为 0」
    双向逐行核对（两个方向都计数，任何一个方向破了就报 MISS，不做「大致对得上」）。
    累加账按腿各自跑：账本键含 worker 名，同一题窗里同一腿也可能开第二本（重试/多步），
    所以「发前余额比本腿累加小」不是异常，是又开了一本；这一格由 room_left 签名判定。
    """
    if log is None or not windows:
        miss.append("MISS 账本面：装箱行或 sidecar 窗口缺一头，累加账判不了")
        return
    rows_all = [r for r in log["tool_rows"] if r["clock"]]
    counted = same = restart = restart_ub_nonzero = ub_zero_no_restart = 0
    own_zero_not_restart = cross_unique = cross_ambiguous = unexplained = 0
    restart_legchange = 0
    multi_leg_windows = three_leg_windows = leg_windows = 0
    samples = {"cross_unique": [], "cross_ambiguous": [], "unexplained": [], "broken": []}
    prev_leg = None
    for start, end, qid, _ in windows:
        rows = [r for r in rows_all if start - 1 <= _moment(r) <= end + 1]
        if not rows:
            continue
        legs = {row["leg"] for row in rows}
        leg_windows += 1
        if len(legs) > 1:
            multi_leg_windows += 1
        if {"doc", "data", "query"} <= legs:
            three_leg_windows += 1
        per_leg = {}
        for row in rows:
            counted += 1
            used_before = row["ledger_packed_tokens"] - row["packed_tokens"]
            own = per_leg.get(row["leg"], 0)
            others = sum(value for leg, value in per_leg.items() if leg != row["leg"])
            is_restart = row["room_left"] == row["room_total"]
            if is_restart:
                #: 双向核对第一个方向：换账签名那一发的发前余额必须是 0。
                restart += 1
                if prev_leg is not None and prev_leg != row["leg"]:
                    restart_legchange += 1
                if used_before != 0:
                    restart_ub_nonzero += 1
                    if len(samples["broken"]) < 3:
                        samples["broken"].append((qid, row["at"], row["leg"], used_before))
            else:
                if used_before == 0:
                    ub_zero_no_restart += 1
                    if len(samples["broken"]) < 3:
                        samples["broken"].append((qid, row["at"], row["leg"], used_before))
                if used_before == own:
                    same += 1
                    if own == 0:
                        #: 这一发不是新账（room_left 没回到 room_total），但窗内本腿还没有累加
                        #: ⇒ 这一本的开头在窗口之外（题窗前就发过），窗内累加只能读成续账。
                        own_zero_not_restart += 1
                else:
                    unexplained += 1
                    if len(samples["unexplained"]) < 3:
                        samples["unexplained"].append(
                            (row["at"], qid, row["leg"], used_before, own, others))
                #: 歧义与唯一归因这两格与上面的分派正交：只要别腿累加也等于发前余额，这一发
                #: 对「跨腿共享」就没有判别力（本窗真机里两腿各自填到 room_total=1198 时就会这样），
                #: 所以它单独计数，绝不借分派顺序把自己算成 0。
                if others > 0 and used_before == others:
                    if used_before == own:
                        cross_ambiguous += 1
                        if len(samples["cross_ambiguous"]) < 6:
                            samples["cross_ambiguous"].append(
                                (row["at"], qid, row["leg"], used_before, own, others))
                    else:
                        cross_unique += 1
                        if len(samples["cross_unique"]) < 3:
                            samples["cross_unique"].append(
                                (row["at"], qid, row["leg"], used_before, own, others))
            per_leg[row["leg"]] = row["packed_tokens"] if is_restart else own + row["packed_tokens"]
            prev_leg = row["leg"]
    report("LEDGER", "按题窗判装箱账（n=%d 行 / 有装箱行的题窗=%d）：同腿续账=%d · 换一本新账=%d · "
           "其中与上一发换腿=%d" % (counted, leg_windows, same, restart, restart_legchange))
    report("LEDGER", "  双向核对：room_left 回到 room_total 的行=%d，其中发前余额非 0 的=%d；"
           "发前余额为 0 但 room_left 没回满的行=%d ⇒ 两个方向都零破损才算签名成立"
           % (restart, restart_ub_nonzero, ub_zero_no_restart))
    report("LEDGER", "  跨腿共享：唯一可归因=%d · 歧义（别腿累加也等于发前余额，两腿各自填到同一个数）=%d · "
           "归不了账=%d · 本腿无累加却续账（开头在窗外）=%d"
           % (cross_unique, cross_ambiguous, unexplained, own_zero_not_restart))
    for tag in ("cross_unique", "cross_ambiguous", "unexplained"):
        for at, sample_qid, leg, used_before, own, others in samples[tag][:2 if tag == "cross_ambiguous" else 3]:
            report("LEDGER", "    %s %s 题=%s leg=%s 发前余额=%d（同腿累加=%d 别腿累加=%d）"
                   % (tag, at, sample_qid, leg, used_before, own, others))
    for qid, at, leg, used_before in samples["broken"]:
        report("LEDGER", "    签名破损 %s 题=%s leg=%s 发前余额=%d" % (at, qid, leg, used_before))
    report("LEDGER", "  多腿共窗的题=%d（doc 与 data 同时出现），三腿齐全的题=%d"
           % (multi_leg_windows, three_leg_windows))
    if restart_ub_nonzero or ub_zero_no_restart:
        miss.append("MISS 账本面：换账签名与「发前余额为 0」双向对不上（非满行余额=%d / 满行非零余额=%d），"
                    "窗口归属或账本对不齐，具名不静默" % (ub_zero_no_restart, restart_ub_nonzero))
    if unexplained:
        miss.append("MISS 账本面：%d 行的发前余额既不是本腿累加也不是别腿累加 ⇒ 归不了账，具名不静默"
                    % unexplained)
    if cross_unique:
        report("VERDICT", "日志里出现 %d 枚唯一可归因的跨腿共享格：这与代码面「账本键含 worker」并不冲突——"
               "同一个 worker 步里既发 search_docs 又发 analyze_data 时，两把腿本来就记同一本账"
               % cross_unique)
    else:
        report("VERDICT", "本窗没有一枚唯一可归因的跨腿共享格（%d 枚歧义格对「共享」无判别力）："
               "doc 与 data 各自在自己的 worker 步内续账；三腿齐全的题窗=%d 枚 ⇒ 判据那句"
               "「同一轮里三腿共用一本账」在本窗连可观测的机会都没有" % (cross_ambiguous,
                                                                          three_leg_windows))
    DECLARED.append("DECLARED 账本面：日志不带 step_id/worker 名，窗内累加只是必要条件 ⇒「三腿同轮共用一本账」"
                    "这句要由代码面定：账本键来自 " + KEY_FUNC + "，键里带 worker 名")


# ==================== main ====================

def build_parser():
    parser = argparse.ArgumentParser(description="R445 装箱硬顶只读取证（默认路径由本文件位置与本机 TEMP 推导）")
    parser.add_argument("--log", default=DEFAULT_LOG, help="run9 后端日志快照")
    parser.add_argument("--sidecar", default=DEFAULT_SIDECAR, help="run9 sidecar（题号窗口）")
    parser.add_argument("--run9c", default=DEFAULT_RUN9C, help="run9c sidecar（队列道 kind 计数）")
    parser.add_argument("--readout", default=os.path.join(REPO, READOUT_REL), help="收窗判读件（对账用）")
    parser.add_argument("--strict-queue", action="store_true",
                        help="把队列道那格量不到也计成 MISS（默认打 PARTIAL，仍逐字点名）")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    miss = []
    printed = []
    del DECLARED[:]

    def report(kind, message):
        printed.append("%-8s %s" % (kind, message))

    report("HEAD", "R445 取证件 · 树=%s · 只读零写入" % REPO)
    facts = code_face(miss, report)
    truth_source_room(miss, report, facts)
    log = log_face(_read(args.log), miss, report)
    windows = sidecar_windows(args.sidecar, miss, report)
    if log is not None:
        attribution(log, windows, miss, report)
        price_rulers(log, facts, miss, report)
        ledger_face(log, windows, report, miss)
    queue_face(args.run9c, args.strict_queue, miss, report)
    reconcile(_read(args.readout), log, report, miss)
    for line in printed:
        print(line)
    print("SUMMARY MISS=%d DECLARED=%d" % (len(miss), len(DECLARED)))
    for line in DECLARED:
        print(line)
    for line in miss:
        print(line)
    return 1 if miss else 0


if __name__ == "__main__":
    raise SystemExit(main())
