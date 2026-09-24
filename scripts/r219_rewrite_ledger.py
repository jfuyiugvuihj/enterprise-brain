# -*- coding: utf-8 -*-
"""R219 判据 1 · run6 这 105 题一共付了几发「查询改写」——一笔可复核的账。

跑法（仓库根，工作树解释器；**零模型、零网络、零向量库、零写盘**）::

    .venv\\Scripts\\python.exe scripts/r219_rewrite_ledger.py
    .venv\\Scripts\\python.exe scripts/r219_rewrite_ledger.py --json

三条硬规矩（照 `scripts/rehearse_eval_window.py` 的形）：

1. **只读原件**：题面与腿形来自 `docs/testing/rehearse-run6.csv`，引证来自
   `docs/testing/answers-run6.jsonl`，重试次数与墙钟来自 `docs/testing/sidecar-run6.jsonl`。
   三本都是 run6 的仓内原件；本件不 import `chromadb`、不碰 `chroma_db/`。
2. **不发明口径**：档位取值域与判定式用 **ast** 从 `app/rag/retrieval_pipeline.py` 现抠
   （`_tier_facts`），不手抄、不 import 业务件——import 会在模块级建 `ModelHandler()`。
3. **只报代码与原件能担保的东西**：模型说了算的那一格（一条 doc 腿究竟调了几发
   `search_docs`）今天没有任何一张表记着，所以本件给的是**下界**，并写明上界为什么给不出。

发数怎么算出来的（每一格都可复核）
----------------------------------
一「发」= 一次 `RetrievalPipeline.search()` 里 `QueryRewriter.rewrite()` 真的打到模型。
`full` 档 `should_rewrite_query()` 恒真，所以 **发数 = 检索调用数**。生产链路上只有两类调用点
会为一题付改写：

- `search_docs` 工具（`app/agents/tools.py` 的 doc 腿）—— top_k=5；
- `approval_precheck`（`app/agents/orchestrator.py` 的审批腿制度检索）—— top_k=3。

`evidence` 汇流在 `app/api/v1/chat.py` 按 `source_id` **去重**，所以一题的 doc 引证行数 `n`
只能担保「这题至少跑了 ceil(n/5) 发 search_docs」（审批腿同理 ceil(n/3)）。重叠召回会被去重
吃掉，真值只会更大不会更小：**这是下界，不是估计**。

价格：41.581 s 已被现网读数推翻
------------------------------
`tests/test_r51_stage_latency.py:51` 那枚 `("rewrite", "multi-query rewrite", 41.581)` 是
2026-09-16 纯 CPU（decode 8.14 tok/s）、且**改写还打在带隐藏思维链的 `/v1` 腿**上量出来的。
两件事在此之后都变了：

- **R92**（09-19 并树）把非流式改写挪到原生 `/api/chat` + `think:false`
  （`app/common/model_handler.py:7-13` 原话：改前那条腿 "roughly 12 s of GPU per question
  for text nothing can parse"）；
- **R101**（跟进单 36.6，总控主树亲验，非采信自述）认得一行现网日志：
  `21:21:36 [Model] ollama-native 应答: seconds=4.08 load_seconds=0.00 keep_alive=900s
  done_reason=stop eval_count=115`，并逐行证明**那 4.08 s / 115 token 就是一发查询改写**
  （native 腿只在 `if not stream:` 分支可达，非流式调用方只有改写，预算恒为 REWRITE/256）；
- **R214**（09-24 结案）：native 腿 95 发实测 decode 19.7-50.6 tok/s、**中位 29.2**
  ⇒ 4.08 s / 115 token = 28.2 tok/s，与现网同一枚量级。

所以本件定价用 **4.08 s/发**（`REWRITE_SECONDS_PER_CALL`，出处 = 跟进单 36.6 那一行现网日志，
**n=1**），并把它与 41.581 s 的比一起打出来。41.581 只保留为「历史标定，不得用于今天的归因」。
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CSV_REL = Path("docs/testing/rehearse-run6.csv")
ANSWERS_REL = Path("docs/testing/answers-run6.jsonl")
SIDECAR_REL = Path("docs/testing/sidecar-run6.jsonl")
PIPELINE_REL = Path("app/rag/retrieval_pipeline.py")
BUDGET_TEST_REL = Path("tests/test_r51_stage_latency.py")

#: 一发的价格。见模块 docstring「价格」一节。n=1 是这条读数的诚实边界。
REWRITE_SECONDS_PER_CALL = 4.08
REWRITE_PRICE_SOURCE = "跟进单 36.6 现网日志 21:21:36 seconds=4.08 eval_count=115 (n=1)"
#: 被推翻的旧标定，只作对照，不进任何合计。
STALE_SECONDS_PER_CALL = 41.581
STALE_PRICE_SOURCE = ("tests/test_r51_stage_latency.py:51 / "
                      "docs/perf/latency-budget-2026-09-16.md 表一(3)")

#: 两类检索调用点各自的 top_k（现值：tools.py 的 search_docs=5、orchestrator.py 的 precheck=3）。
DOC_LEG_TOP_K = 5
APPROVAL_LEG_TOP_K = 3

#: 与 `_looks_multi_intent` 同一把尺；子句分隔符集合照抄 app/rag/retrieval_pipeline.py 的
#: `_CLAUSE_SEPARATORS`（那枚常量是代码里的字面量，本件按 ast 读它，见 `_tier_facts` 的钉）。
CLAUSE_SEPARATORS = "，,；;、？?"


# ---------------------------------------------------------------------------
# 档位取值域与判定式（ast 取证，零 import）
# ---------------------------------------------------------------------------

def _resolve_names(node: ast.expr, resolved: dict) -> ast.expr:
    """把 `TIER_FULL` 这样的名字换成已解出的字面量，再交给 literal_eval。"""
    if isinstance(node, ast.Name):
        if node.id in resolved:
            return ast.Constant(value=resolved[node.id])
        raise ValueError(f"unresolved name {node.id}")
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        node.elts = [_resolve_names(elt, resolved) for elt in node.elts]
    elif isinstance(node, ast.Dict):
        node.values = [_resolve_names(value, resolved) for value in node.values]
    elif isinstance(node, ast.UnaryOp):
        node.operand = _resolve_names(node.operand, resolved)
    return node


def _tier_facts() -> dict:
    """从 `app/rag/retrieval_pipeline.py` 抠档位常量与两枚判定式的形状。

    第二遍解名字引用：直接 `ast.literal_eval` 会把 `DEFAULT_TIER = TIER_FULL` 读成
    "读不出来"，那是假的缺失。
    """
    tree = ast.parse((REPO_ROOT / PIPELINE_REL).read_bytes().decode("utf-8"))
    raw: dict[str, object] = {}
    pending: dict[str, ast.expr] = {}
    functions: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                pending[target.id] = node.value
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = ast.unparse(node)
    for _round in range(6):
        for name, value in list(pending.items()):
            try:
                raw[name] = ast.literal_eval(_resolve_names(value, raw))
            except ValueError:
                continue
            del pending[name]

    wanted = ("TIER_ENV", "TIER_FAST", "TIER_ADAPTIVE", "TIER_FULL",
              "DEFAULT_TIER", "REWRITE_TIERS", "TIER_ALIASES", "MAX_RECALL_QUERIES",
              "ADAPTIVE_REWRITE_MIN_CHARS", "ADAPTIVE_REWRITE_MIN_CLAUSES",
              "SYNONYM_EXPANSION_MAX_QUERIES", "SYNONYM_EXPANSION_MAX_QUERY_CHARS",
              "SYNONYM_EXPANSION_MIN_TERM_CHARS", "_CLAUSE_SEPARATORS")
    missing = [name for name in wanted if name not in raw]
    if missing:
        raise AssertionError(f"档位常量改名或搬家，账本读法需复核：{missing}")

    resolve = functions["resolve_rewrite_tier"]
    should = functions["should_rewrite_query"]
    return {
        "constants": {name: raw[name] for name in wanted},
        "clause_separators_match": (
            raw["_CLAUSE_SEPARATORS"] == CLAUSE_SEPARATORS),
        # ast.unparse 把常量名留在原地（os.getenv(TIER_ENV, ...)），所以按名字查。
        "resolve_reads_env": "os.getenv(TIER_ENV" in resolve,
        "resolve_falls_back_to_default_twice": resolve.count("return DEFAULT_TIER") >= 2,
        "fast_is_the_only_false": should.count("return False") == 1,
        "adaptive_delegates_to_rule": "return _looks_multi_intent(query)" in should,
        "everything_else_returns_true": should.rstrip().endswith("return True"),
        "resolve_source": resolve,
        "should_source": should,
    }


# ---------------------------------------------------------------------------
# run6 原件
# ---------------------------------------------------------------------------

def load_run6() -> dict:
    plans = {row["id"]: row for row in csv.DictReader(
        (REPO_ROOT / CSV_REL).read_bytes().decode("utf-8-sig").splitlines())}
    answers = {}
    for line in (REPO_ROOT / ANSWERS_REL).read_bytes().decode("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            answers[row["id"]] = row
    sidecar = {}
    for line in (REPO_ROOT / SIDECAR_REL).read_bytes().decode("utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            sidecar[row["id"]] = row
    if not (len(plans) == len(answers) == len(sidecar) == 105):
        raise AssertionError(
            f"run6 三本原件题数不等：csv={len(plans)} answers={len(answers)} "
            f"sidecar={len(sidecar)}")
    if set(plans) != set(answers) or set(plans) != set(sidecar):
        raise AssertionError("三本原件题号不闭合")
    return {"plans": plans, "answers": answers, "sidecar": sidecar}


def _adaptive_would_rewrite(question: str, facts: dict) -> bool:
    """照 `should_rewrite_query` 的 adaptive 分支原式复算，尺子取值全部来自 ast 现抠。"""
    text = str(question or "").strip()
    if not text:
        return False
    constants = facts["constants"]
    if len(text) >= constants["ADAPTIVE_REWRITE_MIN_CHARS"]:
        return True
    return (sum(text.count(ch) for ch in constants["_CLAUSE_SEPARATORS"])
            >= constants["ADAPTIVE_REWRITE_MIN_CLAUSES"])


def build_ledger(run6: dict, facts: dict) -> list[dict]:
    """逐题的改写发数下界（每格都带着它自己的凭据）。"""
    rows: list[dict] = []
    for question_id, plan in run6["plans"].items():
        evidence = run6["answers"][question_id].get("evidence") or []
        side = run6["sidecar"][question_id]
        doc_rows = sum(1 for row in evidence if row.get("worker") == "doc")
        approval_rows = sum(1 for row in evidence if row.get("worker") == "approval")
        distinct_doc = len({(row.get("source"), row.get("chunk_index"))
                            for row in evidence if row.get("worker") == "doc"})
        doc_searches = math.ceil(doc_rows / DOC_LEG_TOP_K) if doc_rows else 0
        approval_searches = (math.ceil(approval_rows / APPROVAL_LEG_TOP_K)
                             if approval_rows else 0)
        attempt = int(side.get("attempt") or 1)
        rows.append({
            "id": question_id,
            "plan": plan.get("plan") or "",
            "route_class": plan.get("route_class") or "",
            "doc_planned": "doc" in (plan.get("plan") or ""),
            "doc_evidence_rows": doc_rows,
            "doc_evidence_distinct": distinct_doc,
            "approval_evidence_rows": approval_rows,
            "rewrite_calls_proven": doc_searches + approval_searches,
            "attempts": attempt,
            "rewrite_calls_all_attempts": (doc_searches + approval_searches) * attempt,
            "wall_ms": side.get("wall_ms"),
            "question_chars": len((plan.get("question") or "").strip()),
            "adaptive_would_rewrite": _adaptive_would_rewrite(
                plan.get("question") or "", facts),
        })
    return rows


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def summarize(rows: list[dict]) -> dict:
    walls = [float(row["wall_ms"]) for row in rows if row.get("wall_ms")]
    doc_wall = [float(r["wall_ms"]) for r in rows if r["doc_planned"] and r.get("wall_ms")]
    other_wall = [float(r["wall_ms"]) for r in rows
                  if not r["doc_planned"] and r.get("wall_ms")]
    lengths = [int(row["question_chars"]) for row in rows]
    total_calls = sum(row["rewrite_calls_all_attempts"] for row in rows)
    single = sum(row["rewrite_calls_proven"] for row in rows)
    return {
        "questions": len(rows),
        "doc_leg_planned": sum(1 for row in rows if row["doc_planned"]),
        "questions_with_proven_rewrite": sum(1 for row in rows if row["rewrite_calls_proven"]),
        "questions_without_any_evidence": sum(
            1 for row in rows
            if not (row["doc_evidence_rows"] or row["approval_evidence_rows"])),
        "rewrite_calls_lower_bound": single,
        "rewrite_calls_with_retries": total_calls,
        "retry_extra_calls": total_calls - single,
        "attempts_total": sum(row["attempts"] for row in rows),
        "adaptive_still_pays": sum(1 for row in rows if row["adaptive_would_rewrite"]),
        "adaptive_would_skip": sum(1 for row in rows if not row["adaptive_would_rewrite"]),
        "seconds_lower_bound": total_calls * REWRITE_SECONDS_PER_CALL,
        "seconds_at_stale_price": total_calls * STALE_SECONDS_PER_CALL,
        "price_ratio_stale_over_now": STALE_SECONDS_PER_CALL / REWRITE_SECONDS_PER_CALL,
        "question_chars_min": min(lengths),
        "question_chars_median": statistics.median(lengths),
        "question_chars_max": max(lengths),
        "question_chars_ge_24": sum(1 for value in lengths if value >= 24),
        "wall_total_ms": sum(walls),
        "wall_median_ms": statistics.median(walls) if walls else None,
        "wall_p95_ms": _p95(walls) if walls else None,
        "doc_wall_median_ms": statistics.median(doc_wall) if doc_wall else None,
        "other_wall_median_ms": statistics.median(other_wall) if other_wall else None,
        "rewrite_share_of_doc_median_pct": (
            100.0 * REWRITE_SECONDS_PER_CALL / (statistics.median(doc_wall) / 1000.0)
            if doc_wall else None),
        "rewrite_share_of_run_pct": (
            100.0 * total_calls * REWRITE_SECONDS_PER_CALL / (sum(walls) / 1000.0)
            if walls else None),
    }


def render(rows: list[dict], summary: dict, facts: dict) -> str:
    out: list[str] = []
    push = out.append
    push("=== R219 判据 1 · run6 查询改写发数账（只读原件，零模型、零向量库）===")
    push(f"凭据原件: {CSV_REL} + {ANSWERS_REL} + {SIDECAR_REL}（各 105 行，题号已核对闭合）")
    push("")
    push(f"[档位取值域 · ast 现抠自 {PIPELINE_REL}]")
    for name in ("TIER_ENV", "REWRITE_TIERS", "DEFAULT_TIER", "TIER_ALIASES",
                 "MAX_RECALL_QUERIES", "ADAPTIVE_REWRITE_MIN_CHARS",
                 "ADAPTIVE_REWRITE_MIN_CLAUSES", "_CLAUSE_SEPARATORS",
                 "SYNONYM_EXPANSION_MAX_QUERY_CHARS", "SYNONYM_EXPANSION_MAX_QUERIES",
                 "SYNONYM_EXPANSION_MIN_TERM_CHARS"):
        push(f"  {name} = {facts['constants'][name]!r}")
    push(f"  本件复算用的子句分隔符与代码逐字相同: {facts['clause_separators_match']}")
    push(f"  resolve_rewrite_tier 读环境变量: {facts['resolve_reads_env']}")
    push(f"  未设/空/拼错一律回默认档（两条 return DEFAULT_TIER）: "
         f"{facts['resolve_falls_back_to_default_twice']}")
    push(f"  should_rewrite_query 里唯一的 return False 属于 fast: "
         f"{facts['fast_is_the_only_false']}")
    push(f"  adaptive 委托给 _looks_multi_intent: {facts['adaptive_delegates_to_rule']}")
    push(f"  其余分支 return True: {facts['everything_else_returns_true']}")
    push("")
    push("[默认档 full 在什么条件下这一发不发生]")
    push("  A. RETRIEVAL_TIER 命中 fast（含别名 off/lean）=> 不发。未设、空、拼错一律回 full")
    push("     => 照发（fail-closed：少做一次改写是检索质量变化，不能被一个打错的配置静默开启）。")
    push("  B. 显式 tier= 实参能越过环境，但生产链路上 5 个 search_for_principal 调用点全不传")
    push("     tier（tools.py / orchestrator.py / approval/assistant.py / mcp_server.py /")
    push("     rag/debug.py）=> 现网档位只由进程环境决定，没有请求级后门。")
    push("  C. 并发槽不排队：model_handler 的 acquire(wait_seconds=0) 抢不到槽就返回")
    push("     RATE_LIMITED 正文，**一发模型都不打**，改写静默回退成原问题（09-16 实测各花 0.06 s）。")
    push("     现网 MODEL_MAX_CONCURRENCY=1 => 这一格在并发下是常态，不是异常。")
    push("  D. 模型不可用/超时：_model_failure 出口。这一格**付了墙钟**、不产出改写；")
    push("     引证不区分这两类，所以不在本账的下界里。")
    push("  E. search() 压根没被调到（腿没派、或派了而模型没调工具）=> 不发。")
    push("     **本账的下界就断在这一格**：run6 没有任何一张表记 search_docs 的调用次数。")
    push("")
    push("[价格 · 引用前先查有没有被后续实测推翻]")
    push(f"  采用: {REWRITE_SECONDS_PER_CALL} s/发   出处: {REWRITE_PRICE_SOURCE}")
    push(f"  作废: {STALE_SECONDS_PER_CALL} s/发  出处: {STALE_PRICE_SOURCE}")
    push(f"  旧数是新数的 {summary['price_ratio_stale_over_now']:.1f} 倍 —— 两代前提都已变"
         "（CPU=>GPU 见 R214；思维链未关=>think:false 见 R92）")
    push(f"  点名订正 {BUDGET_TEST_REL}:51：那一行是历史参考表，不是现网定价。")
    push("")
    push("[逐题：只列付了发的（发数=下界；xattempts 已把重试次数乘进去）]")
    push("  id               plan             doc distinct appr calls xattempts  wall_s  adaptive")
    for row in rows:
        if not row["rewrite_calls_proven"]:
            continue
        push("  {id:<16}{plan:<16}{doc_evidence_rows:>3} {doc_evidence_distinct:>8} "
             "{approval_evidence_rows:>4} {rewrite_calls_proven:>5} "
             "{rewrite_calls_all_attempts:>8} {wall:>7.1f}  {ad}".format(
                 wall=float(row["wall_ms"] or 0) / 1000.0,
                 ad=("付" if row["adaptive_would_rewrite"] else "省"), **row))
    push("")
    push("[题长与 adaptive 的那把尺（>=24 字 或 >=2 枚子句分隔符）]")
    push(f"  题面字数 min/median/max = {summary['question_chars_min']}/"
         f"{summary['question_chars_median']}/{summary['question_chars_max']}"
         f" ；>=24 字的题 = {summary['question_chars_ge_24']}/{summary['questions']}")
    push("")
    push("[合计账]")
    for key, value in summary.items():
        push(f"  {key} = {value:.3f}" if isinstance(value, float) else f"  {key} = {value}")
    push("")
    push("[为什么给不出上界]")
    push("  evidence 汇流按 source_id 去重（app/api/v1/chat.py 那一格）=> 两次检索召回重叠块只")
    push("  留一份，引证行数对发数单调不增。doc 腿的 ReAct 子图没把工具调用次数落进 run6 任何")
    push("  一张表 => 上界只能落到「腿数包络」（csv 的 legs 列：94 题 2-4、5 题 3-5、6 题 3-6），")
    push("  而那是一题全部模型腿的根数，不是检索次数。要钉死它，缺的是一发改写一行的现网台账")
    push("  （R51 的 rewrite 段有尺，run6 没开 STAGE_TIMING_ENABLED => 见交回的缺格清单）。")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R219 判据 1：run6 查询改写发数与墙钟的账（只读原件）")
    parser.add_argument("--json", action="store_true", help="机器可读（仍只走 stdout）")
    args = parser.parse_args(argv)
    facts = _tier_facts()
    rows = build_ledger(load_run6(), facts)
    summary = summarize(rows)
    if args.json:
        print(json.dumps({
            "constants": {k: repr(v) for k, v in facts["constants"].items()},
            "facts": {k: v for k, v in facts.items() if k != "constants"},
            "summary": summary,
            "rows": rows,
        }, ensure_ascii=False, indent=1, default=str))
    else:
        print(render(rows, summary, facts))
    return 0


if __name__ == "__main__":
    sys.exit(main())