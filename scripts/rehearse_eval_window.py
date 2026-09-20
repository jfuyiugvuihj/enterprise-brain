#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R107 跑分窗口离线预演器（只读审计件，2026-09-20，基线见 --baseline 输出）。

它回答的唯一问题：D14甲 那个 3-4 小时窗口一开，105 题里每一题会被什么卡住。
产物 = 每题一行的预演表 + 四类失败模式的命中清单，全部从**本树源码**算出来。

三条硬规矩（照 scripts/check_eval_evidence_coverage.py 的形）：
  1. 只读：零模型调用、零网络、零连库、零起服务、零写盘（结果只走 stdout）。
     离线不是一句主张：本件在 import 任何业务代码之前把三条出站 socket 路径换成
     会抛的桩，任何一次真连接都会当场炸给看的人。`app/agents/orchestrator` 不 import
     ——它模块级就 `_make_model(...)`，会去发现本机模型。
  2. 不发明口径：must_contain 的「有没有出处」直接调 R94 常驻件
     scripts/check_eval_evidence_coverage.py 的函数；判分调 app/quality/eval.py 的
     `_is_correct` 本体；路由调 app/agents/planner.py 与 app/agents/nodes.py 的纯规则函数。
  3. 只报代码能担保的东西：模型说了算的部分一律标「静态不可确定」，不猜。
     表里的腿数/秒数是 [推算]，算式写在 --summary 里，参数取跟进单 §42 八变体的实测行。

用法（仓库根，项目 venv 解释器）：
    python scripts/rehearse_eval_window.py                 # 每题一行 markdown 表
    python scripts/rehearse_eval_window.py --only doc      # 按题号前缀筛
    python scripts/rehearse_eval_window.py --csv           # 机器可读（仍只走 stdout）
    python scripts/rehearse_eval_window.py --floor 1536    # 复算 R100 落地后的那一半
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FIXTURE_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"

# --- 以下每个常数都是本树某一行代码的抄本，出处标在后面 -----------------------------
HITL_PARKED = ("chart", "export")  # app/agents/orchestrator.py:419
WORKER_GRAPHS = ("doc", "data", "chart", "export", "approval")  # app/agents/orchestrator.py:876-888
#: 只有这两条腿会往证据袋里写 source_type="document"（sources 事件只认这一类，
#: app/api/v1/chat.py:254 明写 dataset / rule 不进 sources）。
DOC_BEARING = ("doc", "approval")  # app/agents/tools.py:441 + app/agents/orchestrator.py:801
#: 这几条腿不产生生成调用（approval 是纯规则 worker），算腿数时要区分。
ZERO_MODEL_WORKERS = ("approval",)  # app/agents/orchestrator.py:729-841
PLANNER_WORKERS = ("data", "doc", "chart", "approval")  # app/agents/planner.py:72-81
REQUEST_BUDGET_SECONDS = 300.0  # app/api/v1/chat.py:1203 CHAT_REQUEST_TIMEOUT 默认
RATE_LIMIT_PER_MINUTE = 10  # app/api/v1/chat.py:1101 check_rate_limit(..., max_per_minute=10)
ADAPTER_MIN_GAP_SECONDS = 7.0  # scripts/eval_transport_ask_v2.py:41 EVAL_MIN_GAP_SECONDS 默认
CACHE_TTL_SECONDS = 1800  # app/common/cache.py:17 DEFAULT_ANSWER_CACHE_TTL_SECONDS
#: 跟进单 §42 八变体里与现网链路同形的那一行（compat + thinking disabled + 1536）
#: = 37.3 s / 发（1328 计费 token，93 字正文）。表里所有秒数都按这一行线性外推。
MEASURED_SECONDS_PER_CALL = 37.3

#: 追问改写触发词，与 app/api/v1/chat.py:688 的 triggers 逐字同集合。
REWRITE_TRIGGERS = ("那", "它", "这个", "那个", "他们", "换", "改成")

#: route_main 的四张关键词兜底表，逐字抄自 app/agents/orchestrator.py:468-474。
KW_CHART = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]  # :468
KW_DATA = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]  # :469
KW_EXPORT = ["导出", "PDF", "pdf", "报告", "下载"]  # :470
KW_DOC = [  # :471-474
    "制度", "流程", "报销", "审批", "住宿费", "差旅", "员工手册",
    "入职", "安全", "规定", "标准", "谁审批", "审批人",
]
#: _intent_text 先剥离《…》与文件名再匹配（orchestrator.py:425-433）。
DOC_REFERENCE = re.compile(
    r"《[^》]*》|\S+\.(?:pdf|docx?|xlsx?|csv|md|pptx?|txt)\b",
    re.IGNORECASE,
)


def _block_network() -> None:
    """三条出站路径换成会抛的桩，然后才 import 业务代码。

    只换 connect 类入口、不换 socket.socket 本身：R94 的测试用整类替换会打断导入期
    的 zipimport（本件亲测），那是一条假绿的反面——炸在 import 上而不是炸在连接上。
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("R107 预演件禁止任何网络动作")

    socket.create_connection = _boom
    socket.getaddrinfo = _boom
    socket.socket.connect = _boom


_block_network()

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agents.contracts import ModelTier  # noqa: E402
from app.agents.nodes import (  # noqa: E402
    OFFLINE_ANALYSIS_ANSWER,
    OFFLINE_GENERIC_ANSWER,
    OFFLINE_REIMBURSEMENT_ANSWER,
    OFFLINE_STREAM_CHUNK,
    build_task_plan,
    classify_route,
)
from app.common.model_budget import (  # noqa: E402
    clock_affordable_tokens,
    min_answer_tokens,
    model_tier_budget,
)
from app.quality.eval import _is_correct  # noqa: E402

#: 产品在这一行可能吐出的"非模型正文"，逐条带出处。判分器只认子串（
#: app/quality/eval.py:60-66），所以"这句罐头能不能让这一行变成对"是静态可算的。
CANNED_TEXTS = {
    "park_chart": ("本轮在「📈 生成图表」前等待你确认，确认后才会执行，目前尚未产出回答内容。",
                   "app/api/v1/chat.py:942-945 + orchestrator.py:421"),
    "park_export": ("本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。",
                    "app/api/v1/chat.py:942-945 + orchestrator.py:421"),
    "park_both": ("本轮在「📈 生成图表、📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。",
                  "app/api/v1/chat.py:942-945 + orchestrator.py:421"),
    "no_answer": ("本轮未产出任何结论，请重试或补充数据范围。", "app/api/v1/chat.py:1335"),
    "request_expired": ("请求超过系统处理时限", "app/api/v1/chat.py:1297"),
    "offline_reimburse": (OFFLINE_REIMBURSEMENT_ANSWER, "app/agents/nodes.py:52"),
    "offline_analysis": (OFFLINE_ANALYSIS_ANSWER, "app/agents/nodes.py:53"),
    "offline_generic": (OFFLINE_GENERIC_ANSWER, "app/agents/nodes.py:54"),
    "offline_stream": (OFFLINE_STREAM_CHUNK, "app/agents/nodes.py:57"),
    "blank_sentinel": ("<no-bytes-emitted>", "scripts/eval_transport_ask_v2.py:43"),
    "model_unavailable": (
        "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论",
        "app/common/model_handler.py:63（改写腿会把它当问题文本回填，见 :408-412 + chat.py:704-712）"),
    "approval_missing_both": (
        "无法给出审批预审结论：缺少申请金额、可核对的制度标准（error_code=validation_error），本轮未生成业务结论。",
        "app/agents/orchestrator.py:810-822"),
    "approval_missing_standard": (
        "无法给出审批预审结论：缺少可核对的制度标准（error_code=validation_error），本轮未生成业务结论。",
        "app/agents/orchestrator.py:810-822"),
    "approval_missing_amount": (
        "无法给出审批预审结论：缺少申请金额（error_code=validation_error），本轮未生成业务结论。",
        "app/agents/orchestrator.py:810-822"),
}


def load_rows() -> list:
    text = (REPO_ROOT / FIXTURE_REL).read_text(encoding="utf-8-sig")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_eval_evidence_coverage", REPO_ROOT / "scripts" / "check_eval_evidence_coverage.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def provenance(pdf_caliber: bool = False):
    """主口径（documents/*.txt）的缺出处清单；备选口径（含 PDF）只在显式开关下才算。

    默认关：pypdf 一被 import 就往 stdout 刷几千行 "Skipping broken line"（本件 09-20
    在 --include-pdf 上实测），预演表要能直接贴进文档，不能被那种噪声埋掉。
    """
    checker = load_checker()
    rows = checker.load_rows(REPO_ROOT / checker.FIXTURE_REL)
    main = checker.find_missing_terms(rows, checker.load_corpus(REPO_ROOT))
    pdf_rows = 0
    if pdf_caliber:
        pdf_rows = len(checker.find_missing_terms(
            rows, checker.load_corpus(REPO_ROOT, include_pdf=True)))
    return ({str(key): [str(term) for term in value] for key, value in main.items()},
            pdf_rows, checker.EXPECTED_CORPUS_TXT_COUNT)


def offline_sentence_for(question: str) -> str:
    """_OfflineModel 会挑哪句罐头：app/agents/nodes.py:144-149 的分支顺序。"""
    if "报销" in question or "流程" in question:
        return OFFLINE_REIMBURSEMENT_ANSWER
    if "利润" in question or "门店" in question or "分析" in question:
        return OFFLINE_ANALYSIS_ANSWER
    return OFFLINE_GENERIC_ANSWER


def route_class(workers: list) -> str:
    """把计划折成判据 1 要的三分类：doc / data / mixed（外加两类副作用腿）。"""
    docish = "doc" in workers
    dataish = any(w in ("data", "chart") for w in workers)
    if docish and dataish:
        return "mixed"
    if docish:
        return "doc"
    if dataish:
        return "data"
    if "export" in workers:
        return "export-only"
    return "none"


def plan_workers(question: str) -> list:
    return [task["worker"] for task in build_task_plan(question)]


def _intent(question: str) -> str:
    # route_main 用的其实是剥离文档引用后的文本（orchestrator.py:431-433）。
    return DOC_REFERENCE.sub(" ", question or "")


def kw_path_workers(question: str, planned: list) -> list:
    # route_main 的 :489-509 "else" 分支：计划只有一步、且 supervisor 给出了正文时，
    # 关键词能整组取代它派发的腿。真窗口最终派腿由 supervisor 模型说了算
    # （orchestrator.py:443-453 读它的 tool_calls），本函数算的是"派错了也会被关键词
    # 扳回来"的那一路，用来和确定性计划那一路做对照：两路一致 = 路由稳；
    # 不一致 = 这一题走哪条腿静态不可担保。分支顺序照抄 :491-509，不做等价重写。
    intent = _intent(question)
    workers = []
    if any(kw in intent for kw in KW_CHART):
        if workers != ["chart"]:
            workers = ["chart"]
    elif any(kw in intent for kw in KW_EXPORT) and not any(kw in intent for kw in KW_CHART):
        if workers != ["export"]:
            workers = ["export"]
    elif any(kw in intent for kw in KW_DOC) and not any(kw in intent for kw in KW_DATA):
        if workers != ["doc"]:
            workers = ["doc"]
    elif any(kw in intent for kw in KW_DATA) and "chart" not in workers:
        if "data" not in workers:
            workers = ["data"]
    if workers and all(worker in ("chart", "export") for worker in workers):
        for worker in planned:
            if worker not in workers and worker not in ("chart", "export"):
                workers.insert(0, worker)
    return workers


def plan_path_workers(planned: list, question: str) -> list:
    # route_main 的 :481-488 "计划优先"分支（planned>1 或 supervisor 弃权时生效）。
    intent = _intent(question)
    workers = list(planned)
    if "chart" not in workers and any(kw in intent for kw in KW_CHART):
        workers.append("chart")
    elif "export" not in workers and any(kw in intent for kw in KW_EXPORT):
        workers.append("export")
    return workers


def legs_range(workers: list, rewritten: bool) -> tuple:
    """每题模型发数的 [推算] 区间，算式在 --summary 里印出来。

    下界 = 链路坏（正文 0 字）时：supervisor 1 发 + 每个 worker 1 发（react agent
    拿不到正文也拿不到 tool_calls 就收摊，app/agents/orchestrator.py:607-613 找不到
    final 就交空），加改写腿则 +1。
    上界 = 链路正常时：每个 worker 至少"要工具 1 发 + 出正文 1 发"，supervisor 若
    reflect 判 redo 再来 1 发（nodes.py:873-884），故 +1。
    """
    model_legs = [w for w in workers if w not in ZERO_MODEL_WORKERS]
    low = 1 + len(model_legs) + (1 if rewritten else 0)
    high = 1 + 2 * len(model_legs) + 1 + (1 if rewritten else 0)
    return low, high


def budget_table(floor_override: int | None) -> list:
    """每个档在当前代码值（或 R100 的地板现值替身）下的静态结论。"""
    out = []
    for tier in ModelTier:
        budget = model_tier_budget(tier)
        declared = int(budget.max_tokens)
        rate = max(0.1, float(budget.decode_tokens_per_second))
        prefill_rate = max(0.1, float(budget.prefill_tokens_per_second))
        ceiling = float(budget.timeout_ceiling_seconds)
        margin = max(1.0, float(budget.timeout_margin))
        floor = min_answer_tokens() if floor_override is None else floor_override
        affordable_max = clock_affordable_tokens(budget, 0, stream=False)
        # affordable(p) = (ceiling/margin - p/prefill_rate) * rate 在 p=0 处取最大
        # clamped 需要 floor <= affordable < declared；上限都够不到 floor 就不存在这样的 p
        clamp_possible = floor <= affordable_max and affordable_max < declared
        always_unaffordable = affordable_max < declared
        break_even = (ceiling / margin - declared / rate) * prefill_rate
        out.append({
            "tier": tier.value,
            "declared": declared,
            "floor": floor,
            "ceiling": ceiling,
            "affordable_max": affordable_max,
            "self_decode_seconds": round(declared / rate, 1),
            "needed_worst_seconds": round(
                (budget.prefill_seconds(None) + declared / rate) * margin, 1),
            "read_timeout_worst_seconds": round(budget.read_timeout_seconds(None, stream=False), 1),
            "clamp_possible": clamp_possible,
            "always_unaffordable": always_unaffordable,
            "unaffordable_above_prompt_tokens": round(break_even, 1),
        })
    return out


def build_table(rows: list, missing: dict) -> list:
    table = []
    for row in rows:
        question = str(row["question"])
        row_id = str(row["id"])
        workers = plan_workers(question)
        decision = classify_route(question)
        terms = [str(term) for term in (row.get("must_contain") or [])]
        rewrite = any(question.startswith(t) for t in REWRITE_TRIGGERS)
        parked = [worker for worker in workers if worker in HITL_PARKED]
        upstream = [worker for worker in workers if worker not in HITL_PARKED]
        miss = missing.get(row_id) or []
        kw_path = kw_path_workers(question, workers)
        plan_path = plan_path_workers(workers, question)
        divergent = set(kw_path) != set(plan_path)
        canned_hits = sorted(name for name, (text, _) in CANNED_TEXTS.items()
                             if _is_correct(row, text))
        low, high = legs_range(workers, rewrite)

        modes = []
        if not kw_path:
            # supervisor 只要敢直接作答（不派发），route_main 收尾 workers=[] → return "reflect"
            # （orchestrator.py:536-537），reflect 判 redo 再烧一发 supervisor（:514 作者自注）。
            modes.append("①若supervisor直接作答(不派发)→本轮0腿→reflect空转一轮")
        if parked and not upstream:
            modes.append("①挂起无上游→交付必为park文案")
        elif parked:
            modes.append("①chart/export腿挂起(前面有doc/data真结果)")
        if not [w for w in upstream if w in DOC_BEARING]:
            modes.append("①本轮无写document证据的腿→sources必为0条")
        if row.get("requires_evidence") and not [w for w in upstream if w in DOC_BEARING]:
            modes.append("①evidence闸必失(requires_evidence=true且0来源)")
        if rewrite:
            modes.append("①追问改写会换题面→金标可能对不上改写后的问题")
        if decision.tier is ModelTier.ANALYSIS:
            modes.append("②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped)")
        if high * MEASURED_SECONDS_PER_CALL > REQUEST_BUDGET_SECONDS:
            modes.append("③上界腿数会撞CHAT_REQUEST_TIMEOUT=300s")
        if miss:
            modes.append("②金标无出处:" + "|".join(miss))
        if canned_hits:
            modes.append("④假绿通道:" + "/".join(canned_hits))

        watch = bool(parked and not upstream) or bool(canned_hits) or rewrite \
            or (row.get("requires_evidence") and not [w for w in upstream if w in DOC_BEARING])
        table.append({
            "id": row_id,
            "tier": row.get("tier"),
            "category": row.get("category"),
            "question": question,
            "requires_evidence": bool(row.get("requires_evidence")),
            "must_contain": "、".join(terms),
            "tool_legs": ",".join(leg for leg in ("data", "chart", "export", "approval")
                                  if leg in workers) or "无",
            "plan": "+".join(workers),
            "route_class": route_class(workers),
            "plan_path": "+".join(plan_path) or "-",
            "kw_path": "+".join(kw_path) or "-",
            "route_stability": ("模型决定" if divergent else "两路一致"),
            "route": f'{decision.lane}/{decision.tier.value}',
            "route_rule": f'{decision.rule}:{"/".join(decision.matched) or "-"}',
            "provenance": ("缺:" + "|".join(miss)) if miss else "有",
            "failure_modes": "; ".join(modes) or "-",
            "false_green_via": ",".join(canned_hits) or "-",
            "legs": f"{low}-{high}",
            "advice": "人工盯" if watch else "照跑",
        })
    return table


def markdown(table: list, only: str, width: int) -> None:
    header = ("题 id", "档位/类别/题面", "工具腿", "预期路由", "计划", "车道/模型档",
              "must_contain 出处", "命中失败模式", "窗口建议")
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for item in table:
        if only and not item["id"].startswith(only):
            continue
        question = item["question"]
        if len(question) > width:
            question = question[:width] + "…"
        modes = item["failure_modes"].replace("|", "∣")
        plan_cell = item["plan"]
        if item["plan_path"] != item["plan"] and item["plan_path"]:
            plan_cell += f"<br>计划优先→{item['plan_path']}"
        if item["route_stability"] == "模型决定":
            plan_cell += "<br>⚠关键词路→" + ("空" if item["kw_path"] == "-" else item["kw_path"])
        print("| `{id}` | {tier}·{category}<br>{q} | {legs} | **{cls}** | {plan} | {route} "
              "| {prov} | {modes} | {advice} |".format(
                  id=item["id"], tier=item["tier"], category=item["category"], q=question,
                  legs=item["tool_legs"], cls=item["route_class"], plan=plan_cell,
                  route=item["route"], prov=item["provenance"], modes=modes,
                  advice=item["advice"]))


def summary(rows: list, table: list, missing: dict, pdf_rows: int, corpus_txt: int,
            budgets: list, floor_now: int, pdf_caliber_ran: bool = False) -> None:
    def count(predicate) -> int:
        return sum(1 for item in table if predicate(item))

    parked_only = [i["id"] for i in table if "①挂起无上游→交付必为park文案" in i["failure_modes"]]
    parked_any = [i["id"] for i in table if "①挂起无上游→交付必为park文案" in i["failure_modes"]
                  or "①chart/export腿挂起(前面有doc/data真结果)" in i["failure_modes"]]
    no_doc = [i["id"] for i in table if "①本轮无写document证据的腿→sources必为0条" in i["failure_modes"]]
    ev_fail = [i["id"] for i in table if "①evidence闸必失(requires_evidence=true且0来源)" in i["failure_modes"]]
    rewrite = [i["id"] for i in table if any(m.startswith("①追问改写") for m in i["failure_modes"].split("; "))]
    false_green = {i["id"]: i["false_green_via"] for i in table if i["false_green_via"] != "-"}
    analysis = [i["id"] for i in table if i["route"].endswith("/analysis")]
    timeout_risk = [i["id"] for i in table if "③上界腿数会撞CHAT_REQUEST_TIMEOUT=300s" in i["failure_modes"]]
    approval = [i["id"] for i in table if "+approval" in i["plan"] or i["plan"] == "approval"]
    plans = {}
    for item in table:
        plans[item["plan"]] = plans.get(item["plan"], 0) + 1

    print("=== R107 预演汇总（全部由本件当场从源码算出，出处见文件头）===")
    subprocess_out = ""
    try:
        subprocess_out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                        capture_output=True, cwd=str(REPO_ROOT), timeout=10
                                        ).stdout.decode().strip()
    except Exception:
        subprocess_out = "unknown"
    print(f"baseline={subprocess_out} rows={len(table)}")
    print(f"MODEL_MIN_ANSWER_TOKENS 现值={floor_now}  DEFAULT={floor_now}")
    # 上一行的三元表达式会整条吞掉 no_provenance_rows（本件 09-20 实跑所见），拆成两行。
    print(f"no_provenance_rows={len(missing)}（主口径 corpus=documents/*.txt {corpus_txt} 篇）")
    print("no_provenance_rows_pdf_caliber="
          + (str(pdf_rows) if pdf_caliber_ran else "未算（加 --pdf-caliber 才算）")
          + "；口径差异见 provenance() docstring")
    print("no_provenance_ids=" + " ".join(sorted(missing)))
    print(f"tier_counts=" + json.dumps({t: count(lambda i, t=t: i['tier'] == t)
                                        for t in ('问答', '分析', '报告')}, ensure_ascii=False))
    print(f"advice=" + json.dumps({t: count(lambda i, t=t: i['advice'] == t)
                                   for t in ('照跑', '人工盯')}, ensure_ascii=False) + " 跳过=0（见 note:coverage）")
    print(f"parked_any={len(parked_any)} {parked_any}")
    print(f"parked_only={len(parked_only)} {parked_only}")
    print(f"no_doc_leg={len(no_doc)} {no_doc}")
    print(f"evidence_gate_expected_fail={len(ev_fail)} {ev_fail}")
    print(f"rewrite_triggered={len(rewrite)} {rewrite}")
    print(f"approval_leg_zero_model_call={len(approval)} {approval}")
    print(f"analysis_tier={len(analysis)}")
    print(f"request_budget_at_risk={len(timeout_risk)} {timeout_risk}")
    print(f"max_high_legs={max(int(i['legs'].split('-')[1]) for i in table)} "
          f"⇒ 高界秒数={max(int(i['legs'].split('-')[1]) for i in table) * MEASURED_SECONDS_PER_CALL:.1f}s "
          f"vs 请求预算 {REQUEST_BUDGET_SECONDS}s")
    print("legs_distribution=" + json.dumps(
        {i["legs"]: sum(1 for t in table if t["legs"] == i["legs"]) for i in table}, ensure_ascii=False))
    print(f"false_green_rows={len(false_green)}")
    for row_id in sorted(false_green):
        print(f"   FALSEGREEN {row_id}: {false_green[row_id]}")
    print(f"plan_shapes={json.dumps(dict(sorted(plans.items(), key=lambda kv: -kv[1])), ensure_ascii=False)}")
    route = {}
    lanes = {}
    for item in table:
        route[item["route_class"]] = route.get(item["route_class"], 0) + 1
        lanes[item["route"]] = lanes.get(item["route"], 0) + 1
    print("route_class=" + json.dumps(dict(sorted(route.items(), key=lambda kv: -kv[1])), ensure_ascii=False))
    print("lane_tier=" + json.dumps(dict(sorted(lanes.items(), key=lambda kv: -kv[1])), ensure_ascii=False))
    stable = [i["id"] for i in table if i["route_stability"] == "模型决定"]
    kw_empty = [i["id"] for i in table if i["kw_path"] == "-"]
    print(f"route_divergent={len(stable)} {stable}")
    print(f"route_kw_fallback_empty={len(kw_empty)} {kw_empty}")
    export_rows = [i["id"] for i in table if "export" in i["plan_path"] or "export" in i["kw_path"]]
    print(f"export_leg_any_path={len(export_rows)} {export_rows}")
    # 挂起风险要按"任一路"算：计划里没排 export，但 route_main 的关键词分支 :487-488 / :494-496
    # 会把 export 追加或整组改派进来，而 export 和 chart 一样带 interrupt_before（:907）。
    park_path = [i["id"] for i in table
                 if set(i["plan_path"].split("+")) & set(HITL_PARKED)
                 or set(i["kw_path"].split("+")) & set(HITL_PARKED)]
    print(f"parked_any_path={len(park_path)} {park_path}")
    data_rows = [i["id"] for i in table
                 if "data" in i["plan_path"].split("+") or "data" in i["kw_path"].split("+")]
    print(f"data_leg_any_path={len(data_rows)} {data_rows}")
    print(f"requires_evidence_true={count(lambda i: i['requires_evidence'])}")
    print(f"evidence_coverage_ceiling={105 - len(ev_fail)}/105 "
          f"={round((105 - len(ev_fail)) / 105, 4)}（[算术] 23 行结构上不可能有 document 来源）")
    clean = [i["id"] for i in table if i["failure_modes"] == "-"]
    print(f"rows_with_no_failure_mode={len(clean)} {clean}")
    prov_free = [i["id"] for i in table if i["provenance"] != "有"]
    print(f"no_provenance_in_table={len(prov_free)}")
    print()
    print("=== 档位预算静态结论 ===")
    for row in budgets:
        print(json.dumps(row, ensure_ascii=False))
    print()
    print("=== [推算] 用的算式与参数 ===")
    print(f"legs_min = 1 + len(计划中会产生模型调用的腿) (+1 若追问改写)；"
          f"legs_max = 2 + 2*len(同类腿) (+1 改写)；approval 腿记 0 次模型调用"
          f"（app/agents/orchestrator.py:729-841 是纯规则 worker）")
    print(f"每题秒数 ≈ legs × {MEASURED_SECONDS_PER_CALL}s（跟进单§42 表#6：compat+thinking off+1536 = 37.3s/发）")
    print(f"整窗 [秒] ≈ Σ(legs_min) × {MEASURED_SECONDS_PER_CALL} + 105 × {ADAPTER_MIN_GAP_SECONDS} 间隔"
          f"（上界同理换 Σ(legs_max)）")
    avg_low = sum(int(i["legs"].split("-")[0]) for i in table) / len(table)
    print(f"平均下界腿数={avg_low:.2f} ⇒ 整窗≈{105 * (avg_low * MEASURED_SECONDS_PER_CALL + ADAPTER_MIN_GAP_SECONDS) / 3600:.2f} h"
          f"；上界={105 * ((sum(int(i['legs'].split('-')[1]) for i in table) / len(table)) * MEASURED_SECONDS_PER_CALL + ADAPTER_MIN_GAP_SECONDS) / 3600:.2f} h")
    print(f"限流：{RATE_LIMIT_PER_MINUTE} 次/分钟/用户，适配器最小间隔 {ADAPTER_MIN_GAP_SECONDS}s ⇒ "
          f"任意 60s 窗内最多 {int(60 // ADAPTER_MIN_GAP_SECONDS) + 1} 发 < {RATE_LIMIT_PER_MINUTE} ⇒ 不入队道")
    print(f"答案缓存：键=md5(scope)[:12]+md5(问题.strip())[:12]（app/common/cache.py:194-195），"
          f"TTL={CACHE_TTL_SECONDS}s；105 题题面互不重复⇒单趟自相捂热=0")


def check_against_registered(missing: dict) -> int:
    # 判据 1 那句「核对是否正好那一批，多出来的要单独点名」的机器答复。
    # 登记抄本有两份：tests/test_r94_eval_evidence_coverage.py 的 MISSING_IDS_29（审计
    # 文档 §2.1 的抄本）与 TERM_BY_ID（附录 A 的抄本）。本函数只读 AST 取值，不 import
    # 测试件（那会拉起 pytest 依赖），也不下「谁对谁错」的结论。
    import ast

    test_path = REPO_ROOT / "tests" / "test_r94_eval_evidence_coverage.py"
    tree = ast.parse(test_path.read_text(encoding="utf-8"))
    def resolve(node):
        # 登记件把常量写成 ("a b c").split() 与 {"k": "a b".split()}，literal_eval 不认
        # Call；这里只还原这两种形状，不 eval 整个文件。
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "split":
            return str(resolve(node.func.value)).split()
        if isinstance(node, ast.Dict):
            return {resolve(k): resolve(v) for k, v in zip(node.keys, node.values)}
        return ast.literal_eval(node)

    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = getattr(target, "id", "")
                if name in ("MISSING_IDS_29", "TERM_BY_ID", "BUCKET_COUNTS"):
                    consts[name] = resolve(node.value)
    recorded_ids = [str(i) for i in consts["MISSING_IDS_29"]]
    term_by_id = {str(k): ([str(t) for t in v] if isinstance(v, (list, tuple))
                           else [str(v)]) for k, v in consts["TERM_BY_ID"].items()}
    got_ids = sorted(missing)
    terms = sum(len(v) for v in missing.values())
    extra = sorted(set(got_ids) - set(recorded_ids))
    gone = sorted(set(recorded_ids) - set(got_ids))
    mismatches = sorted(i for i in set(got_ids) & set(term_by_id)
                        if sorted(missing[i]) != sorted(term_by_id[i]))
    print(f"check29 rows_flagged={len(got_ids)} terms={terms}")
    print(f"check29 recorded_ids={len(recorded_ids)} extra={extra} missing={gone}")
    print(f"check29 term_mismatches={mismatches}")
    print(f"check29 row_level_equals_term_level={len(got_ids) == terms}（口径指纹，审计文档 §2.2）")
    buckets = consts.get("BUCKET_COUNTS")
    print(f"check29 bucket_counts={buckets} sum={sum(buckets.values()) if isinstance(buckets, dict) else 'n/a'}")
    return 0 if (not extra and not gone and not mismatches) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R107 跑分窗口离线预演（只读）")
    parser.add_argument("--only", default="")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--width", type=int, default=40)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--pdf-caliber", action="store_true",
                        help="另算含 PDF 的备选口径行数（R94 记 27；默认关，理由见 provenance docstring）")
    parser.add_argument("--check-29", action="store_true",
                        help="实取的无出处清单 vs 登记抄本，逐条点名（判据 1 最后一条）")
    parser.add_argument("--floor", type=int, default=None,
                        help="把 MODEL_MIN_ANSWER_TOKENS 当这个值复算（R100 会把它从 1537 改到 1536）")
    args = parser.parse_args(argv)

    from app.common.model_budget import min_answer_tokens

    os.environ.pop("MODEL_MIN_ANSWER_TOKENS", None)  # 只算代码现值，不吃宿主环境变量
    rows = load_rows()
    missing, pdf_rows, corpus_txt = provenance(args.pdf_caliber)
    table = build_table(rows, missing)
    budgets = budget_table(args.floor)
    floor_now = min_answer_tokens()

    if args.csv:
        keys = list(table[0].keys())
        print(",".join(keys))
        for item in table:
            print(",".join('"' + str(item[key]).replace('"', '""') + '"' for key in keys))
    elif args.check_29:
        return check_against_registered(missing)
    elif args.summary:
        summary(rows, table, missing, pdf_rows, corpus_txt, budgets, floor_now, args.pdf_caliber)
    else:
        markdown(table, args.only, args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())