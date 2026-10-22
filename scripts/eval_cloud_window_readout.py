"""云端形状窗的口径读出与拒写件（R453 · 跟进单 §128 第一节 判据③）。只读、离线、零网络、零模型、零容器。

为什么要有这件（病根，不是态度问题）：口径标签如果只是一句「我这批数是在云端跑的」，它就永远
是对的，也永远是空的 —— 上一班的账里，同一份 run9 读数既能被读成「形状」也能被读成「分数」，
因为没有任何一件东西**规定**哪一格能上云、哪一格不能，也没有一枚牙咬住「p95 和 cloud-shape
写在同一段」这种写法。而这两类的可比性根本不同：形状类（帧怎么切、事件在不在流里、审批门出没
出现）换条模型腿照样读；时延类与分数类吃的是 MODEL_CONTEXT_TOKENS／num_ctx／显存／量化，云端
数拿去冒充本机数就是造假（AGENTS.md：数据不出客户服务器 —— 顺带，本机时延也不许由云端代答）。

所以本件干三件事，都是机器读的，不写在散文里：
① 一张**格表**：逐格写明 cloud 能不能读、必须挂哪枚口径标签、为什么、凭据锚在哪；
   表的分类口径＝总控 09-28 裁定（b）「**形状可云端、数值必本机**」：同一件事拆成两格，
   在场/归类/桶化（`answer_chars_bucket`、`usage_slots_present`、`citations_present`）准在云端道读，
   取数值大小的（`evidence_n`、`sources_count`、`usage_*_tokens`、`answer_chars`）一律归本机全量道，
   云端段里出现即红；
② 一段**拒写规则**：读数（JSONL，一行＝一段）里凡是 caliber=cloud-shape 的那一段混进了
   时延／分数类格（p95／端到端时延／逐类分数／correctness 一律算），当场报错退出 rc=2；
③ 一枚**开窗预检**：--preflight 逐枚报 deploy/compose.cloud-eval.yaml 那四枚 env 在不在
   进程环境里（只报 present/absent，一个字节都不回显值）。

用法：
    python scripts/eval_cloud_window_readout.py                 # 打格表（markdown）
    python scripts/eval_cloud_window_readout.py --json          # 打格表（机器读）
    python scripts/eval_cloud_window_readout.py --readouts <jsonl>   # 校验一批读数
    python scripts/eval_cloud_window_readout.py --preflight     # 开窗前查进程环境

退出码：0＝干净；2＝有拒绝（混口径／缺口径／未知格／预检缺 env）；3＝取不到读数件（明写取不到，不编数）。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys

CALIBER_CLOUD = "cloud-shape"
CALIBER_LOCAL = "local-full"
CALIBERS = (CALIBER_CLOUD, CALIBER_LOCAL)

#: 格的三种归属。shape＝换腿照样读；latency／score＝只认本机全量那扇窗。
SHAPE = "shape"
LATENCY = "latency"
SCORE = "score"

#: 读数行里不是「格」的键。
RESERVED_KEYS = ("segment", "caliber", "note", "source", "anchor", "attempt", "id", "ts")

#: 开窗必须出现在进程环境里的四枚 env（名字，不是值）。
WINDOW_ENV = (
    "LOCAL_MODEL_BASE_URL",
    "LOCAL_MODEL_NAME",
    "LOCAL_MODEL_API_KEY",
    "MODEL_CONTEXT_TOKENS",
)


def _cell(name, gate, kind, cloud, why, anchor, aliases=()):
    return {
        "cell": name,
        "gate": gate,
        "kind": kind,
        "cloud": cloud,
        "why": why,
        "anchor": anchor,
        "aliases": tuple(aliases),
    }


#: 格表本体。cloud=True 的格在云端形状窗里可读，交回时必须挂 caliber=cloud-shape；
#: cloud=False 的格一律只在关掉 override 的本机全量窗里出，挂 caliber=local-full。
CELLS = (
    _cell("frame_shape", "A② 流式逐字", SHAPE, True,
          "帧怎么切是协议形状，与显存和窗口宽度无关",
          "docs/testing/sidecar-run9-frames.jsonl · scripts/eval_frame_caliber_readout.py",
          ("text_frames", "max_stream_frames", "prefix_breaks", "missing_chars", "extra_chars",
           "uncorrected_breaks", "corrective_replacements", "criterion_two_holds", "last_frame_covers_answer")),
    _cell("event_surface", "D 流内事件面", SHAPE, True,
          "sources／answer.headline／request.completed／hitl／done／request.failed 在不在流里，是事件面的在场与否",
          "scripts/eval_frame_caliber_readout.py::event_tally",
          ("sources_present", "headline_present", "done_present", "hitl_present", "failed_event_present")),
    _cell("queue_readback", "D 可查回", SHAPE, True,
          "GET /queue/{id} 能不能读回、响应体键在不在位，属可查回的形状",
          "scripts/eval_transport_ask_v2.py 队列道",
          ("queue_readable", "queue_keys_present", "queue_status_class")),
    _cell("usage_fields_present", "D usage", SHAPE, True,
          "裁定（b）：六枚 usage 槽只准报**在场与否**；槽里的 token 数是数值，走必须本机那一格",
          "scripts/eval_transport_ask_v2.py:803-831 · docs/testing/run9-readout-2026-09-28.md A2 末段",
          ("usage_slots_present", "usage_keys")),
    _cell("approval_gate_shape", "审批门", SHAPE, True,
          "裁定（b）：轮次枚数与 hitl 触发与否取的是形状，留云端道；带审批轮的墙钟合计属时延类，另立一格",
          "docs/testing/sidecar-run9.jsonl approval_rounds · 跟进单 §128 第三节",
          ("approval_rounds", "approved", "hitl_rounds")),
    _cell("escalation_annotation", "C 越权与缓存标注", SHAPE, True,
          "该拒的拒没拒、缓存来源标没标，是判定与标注的形状",
          "docs/testing/run9-readout-2026-09-28.md 跨部门权限 · 跟进单 §128 第二节判据②",
          ("refused_escalation", "cache_annotation_present", "scope_class")),
    _cell("retry_sentinel_shape", "零重试零哨兵", SHAPE, True,
          "attempt 枚数与哨兵是否触发是形状，不含重试耗时",
          "docs/testing/sidecar-run9.jsonl attempt/sentinel",
          ("attempt", "attempt_max", "sentinel", "retry_count")),
    _cell("answer_shape", "答案形状", SHAPE, True,
          "kind 归类与答案空不空可读；answer_chars 的量级只看形状，不拿来判对错",
          "docs/testing/sidecar-run9.jsonl kind/answer_chars",
          ("kind", "answer_nonempty", "answer_chars_bucket")),
    _cell("citation_shape", "引用形状", SHAPE, True,
          "总控 09-28 裁定（b）：只取「引用在不在、形状对不对」；条数数值另立必须本机的一格",
          "docs/testing/run9-readout-2026-09-28.md A0/A4",
          ("citations_present", "citation_class", "sources_shape")),
    _cell("error_class_shape", "失败归类", SHAPE, True,
          "request.failed 的类别（越权／上下文超限／工具错）是归类形状",
          "docs/testing/sidecar-run9.jsonl approval_error/approval_http_status",
          ("failure_class", "approval_http_status")),
    _cell("wall_ms", "A1 端到端时延", LATENCY, False,
          "端到端耗时吃本机显存、量化与 n_ctx，云端数与本机数不同源",
          "docs/testing/run9-readout-2026-09-28.md A1 · docs/testing/sidecar-run9.jsonl wall_ms"),
    _cell("p50_wall_ms", "A1 时延分位", LATENCY, False,
          "分位数是时延的汇总，判据要样本 ≥100 且必须本机跑",
          "docs/testing/run9-readout-2026-09-28.md A1 整表"),
    _cell("p95_wall_ms", "A1 时延分位", LATENCY, False,
          "p95 只在本机全量窗里可比；与 caliber=cloud-shape 同段出现即拒",
          "docs/testing/run9-readout-2026-09-28.md A1 整表"),
    _cell("max_wall_ms", "A1 时延极值", LATENCY, False,
          "max 那枚撞到的往往是上下文超限，换了窗口宽度就不是同一件事",
          "docs/testing/run9-readout-2026-09-28.md A1（撞 300 s 那枚）"),
    _cell("min_wall_ms", "A1 时延极值", LATENCY, False,
          "同上，极值属时延类",
          "docs/testing/run9-readout-2026-09-28.md A1"),
    _cell("first_visible_ms", "A2 首字时延", LATENCY, False,
          "首片可见耗时是流式时延，不是流式形状",
          "docs/testing/run9-readout-2026-09-28.md A2 first_visible_ms 分布"),
    _cell("latency_ms", "答案腿自报时延", LATENCY, False,
          "R205a 起对越界跨度记 null，本机口径；云端腿没有这台机的账",
          "scripts/r205a_latency_source.py · docs/testing/run9-readout-2026-09-28.md A1 出处行"),
    _cell("throughput_tokens_per_second", "吞吐", LATENCY, False,
          "prefill／decode 速度是硬件读数，与 MODEL_PREFILL_TOKENS_PER_SECOND 那两格同族",
          "deploy/.env.server.example MODEL_PREFILL_TOKENS_PER_SECOND · scripts/bench_model_throughput.py"),
    _cell("rewrite_leg_seconds", "A3 改写腿耗时", LATENCY, False,
          "改写腿秒数（现值 4.08 s/发）是时延，云端窗量不到本机那一腿",
          "docs/testing/run9-readout-2026-09-28.md A3"),
    _cell("correctness", "A4 正确性总分", SCORE, False,
          "分数判据要本机全量每冻结点一次，样本不足或换了腿都不许出数",
          "docs/testing/run9-readout-2026-09-28.md A4 · docs/testing/evaluation-report-run9.json"),
    _cell("evidence_score", "A4 证据分", SCORE, False,
          "与 citation_shape 分家：在场与否可云端，分数不行",
          "docs/testing/run9-readout-2026-09-28.md A4"),
    _cell("per_category_score", "A4 逐类分数", SCORE, False,
          "逐类 correctness／evidence 是分数族，判据③点名拒绝",
          "docs/testing/run9-readout-2026-09-28.md A4 逐类行"),
    _cell("unsupported_claim_rate", "A4 无据断言率", SCORE, False,
          "比率类分数，同上",
          "docs/testing/run9-readout-2026-09-28.md A4 总分行"),
    _cell("total_score", "A4 综合分", SCORE, False,
          "综合分是冻结点之间的对照量，只能本机全量",
          "docs/testing/evaluation-report-run9.json"),
    #: 裁定（b）落地：以下三格取的是**数值大小**，不进形状道。云端段里出现即红。
    _cell("citation_count_value", "引用条数数值", SCORE, False,
          "条数是量出来的数，与本机语料同源；形状读数是上面那格 citation_shape",
          "docs/testing/sidecar-run9.jsonl evidence_n/pre_evidence_n",
          ("evidence_n", "pre_evidence_n", "sources_count", "evidence_count")),
    _cell("usage_token_values", "usage token 数值", SCORE, False,
          "六枚槽里的 token 数随窗口宽度与量化走，云端数不是本机数；在场与否归 usage_fields_present",
          "scripts/eval_transport_ask_v2.py:803-831",
          ("usage_prompt_tokens", "usage_completion_tokens", "usage_total_tokens",
           "usage_cached_tokens", "usage_reasoning_tokens")),
    _cell("answer_char_count", "答案字符数", SCORE, False,
          "字符数是量级，不是形状；桶化后的 answer_chars_bucket 才准在云端段读",
          "docs/testing/sidecar-run9.jsonl answer_chars",
          ("answer_chars", "pre_answer_chars")),
    _cell("context_limit_exceeded_count", "上下文超限计数", SCORE, False,
          "云端窗抬了 MODEL_CONTEXT_TOKENS，这一格在云端窗里必然不可比",
          "docs/testing/run9-readout-2026-09-28.md 抬头 · app/common/model_budget.py"),
)

#: 时延与分数两族在云端段里一律是禁格，即便换成别的拼写也要咬住（改名走私）。
FORBIDDEN_PATTERN = re.compile(
    r"(p50|p95|p99|percentile|wall_ms|latency|duration|_ms\b|first_visible|end_to_end|"
    r"端到端|时延|首字|首屏|correctness|evidence_score|per_category|unsupported_claim_rate|"
    r"total_score|score|accuracy|tokens_per_second|throughput|rewrite_leg|context_limit)",
    re.IGNORECASE,
)

REGISTRY = {}
for _row in CELLS:
    REGISTRY[_row["cell"]] = _row
    for _alias in _row["aliases"]:
        if _alias in REGISTRY and REGISTRY[_alias]["cell"] != _row["cell"]:
            raise SystemExit("格别名冲突：%s 同时属于 %s 与 %s" % (
                _alias, REGISTRY[_alias]["cell"], _row["cell"]))
        REGISTRY[_alias] = _row

CLOUD_CELLS = tuple(sorted(row["cell"] for row in CELLS if row["cloud"]))
LOCAL_ONLY_CELLS = tuple(sorted(row["cell"] for row in CELLS if not row["cloud"]))


def resolve(cell_name):
    """把一格读数落到表里的哪一格：认精确名与别名，认不出来返回 None。"""
    return REGISTRY.get(cell_name)


def row_cells(row):
    """一行读数里的「格」集合：既认 cells 子对象，也认摊平的写法。"""
    nested = row.get("cells")
    if isinstance(nested, dict):
        return dict(nested)
    return {k: v for k, v in row.items() if k not in RESERVED_KEYS}


def check_rows(rows):
    """核心拒写规则，纯函数（测试直接喂坏输入）。返回违规记录列表。

    R1 每行必须有非空 segment —— 没有段，口径就无处可挂；
    R2 每行必须挂上在册口径之一 —— 缺口径与拼错口径都不算「本机全量」；
    R3 同一 segment（按段分组，跨行也算同段）里出现 caliber=cloud-shape，则该段每一格都
       必须是 cloud=True 的形状格；命中时延／分数格＝拒（判据③点名的就是这一条）；
    R4 云端段里出现表外格＝拒：认不出来的格没法替它担保是形状；
    R5 本机段里的表外格只作告警（stderr），不拒 —— 拒写规则只管云端那一侧。
    """
    violations = []
    warnings = []
    groups = {}
    for index, row in enumerate(rows):
        segment = str(row.get("segment") or "").strip()
        if not segment:
            violations.append({"rule": "R1", "segment": "#%d" % index, "caliber": row.get("caliber"),
                               "cell": None, "detail": "读数行没有 segment，口径无处可挂"})
            continue
        groups.setdefault(segment, []).append((index, row))

    for segment, members in groups.items():
        calibers = sorted({str(row.get("caliber") or "") for _, row in members})
        cloud = CALIBER_CLOUD in calibers
        for index, row in members:
            caliber = row.get("caliber")
            if caliber not in CALIBERS:
                violations.append({"rule": "R2", "segment": segment, "caliber": caliber,
                                   "cell": None, "detail": "口径缺失或不在册（在册＝%s）" % "／".join(CALIBERS)})
                continue
            for cell_name in row_cells(row):
                cell = resolve(cell_name)
                if cell is None:
                    if cloud and FORBIDDEN_PATTERN.search(str(cell_name)):
                        violations.append({"rule": "R3", "segment": segment, "caliber": caliber,
                                           "cell": cell_name,
                                           "detail": "云端段里的时延／分数形状格（改名走私），命中拒绝模式"})
                    elif cloud:
                        violations.append({"rule": "R4", "segment": segment, "caliber": caliber,
                                           "cell": cell_name, "detail": "表外格：认不出来的格不许替它担保是形状"})
                    else:
                        warnings.append("segment=%s 表外格=%s（本机段，只告警不拒）" % (segment, cell_name))
                    continue
                if cloud and not cell["cloud"]:
                    violations.append({"rule": "R3", "segment": segment, "caliber": caliber,
                                       "cell": cell_name,
                                       "detail": "caliber=cloud-shape 与 %s 类格同段（%s）" % (cell["kind"], cell["why"])})
    violations.sort(key=lambda v: (v["segment"], v["rule"], str(v["cell"])))
    return violations, warnings


def load_rows(path):
    rows = []
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def render_markdown():
    """格表（markdown 机器表）。竖线枚数逐行相同，便于件口径数一数。"""
    out = ["| 格 | 判据归属 | 种类 | 云端可读 | 必须挂的口径 | 为什么 | 凭据锚 |"]
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in CELLS:
        out.append("| %s | %s | %s | %s | `%s` | %s | %s |" % (
            row["cell"], row["gate"], row["kind"],
            "可" if row["cloud"] else "🔴 必须本机",
            CALIBER_CLOUD if row["cloud"] else CALIBER_LOCAL,
            row["why"], row["anchor"]))
    out.append("")
    out.append("- 合计 %d 格：云端可读 %d，必须本机全量 %d" % (
        len(CELLS), len(CLOUD_CELLS), len(LOCAL_ONLY_CELLS)))
    out.append("- 云端段口径标签唯一合法拼写：`%s`；本机段：`%s`" % (CALIBER_CLOUD, CALIBER_LOCAL))
    out.append("- 别名（读数里的原始键名）也在册，逐格 aliases 见 --json")
    return out


def table_payload():
    return {
        "calibers": {"cloud": CALIBER_CLOUD, "local": CALIBER_LOCAL},
        "cells": [dict(row) for row in CELLS],
        "summary": {
            "total": len(CELLS),
            "cloud_readable": len(CLOUD_CELLS),
            "local_only": len(LOCAL_ONLY_CELLS),
            "cloud_cell_names": list(CLOUD_CELLS),
            "local_only_cell_names": list(LOCAL_ONLY_CELLS),
            "table_sha256": table_sha256(),
        },
    }


def table_sha256():
    """格表自身的指纹：表一改口径，指纹就漂，钉得住「表被悄悄改宽」。"""
    canonical = json.dumps(
        [[row["cell"], row["kind"], row["cloud"], sorted(row["aliases"])] for row in CELLS],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preflight(environ=None):
    """开窗预检：四枚 env 在不在进程环境里。只报在场与否，绝不回显值。"""
    env = environ if environ is not None else os.environ
    readings = []
    for name in WINDOW_ENV:
        value = env.get(name)
        state = "absent" if value is None else ("empty" if str(value) == "" else "present")
        readings.append((name, state))
    return readings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="把格表打成 JSON（机器读）")
    parser.add_argument("--readouts", help="读数 JSONL（一行＝一段），按判据③校验")
    parser.add_argument("--preflight", action="store_true", help="查开窗那四枚 env 在不在进程环境")
    args = parser.parse_args(argv)

    if args.preflight:
        readings = preflight()
        missing = [name for name, state in readings if state != "present"]
        for name, state in readings:
            print("- %s=%s" % (name, state))
        if missing:
            print("🔴 开窗预检未过：%d／4 枚不在进程环境。缺了它们，compose 会静默回落到 "
                  "deploy/.env.server 里的本机值（密钥退回 local＝云端一次 401）。" % len(missing),
                  file=sys.stderr)
            return 2
        print("- 预检通过：四枚都在进程环境里（值未回显）")
        return 0

    if args.readouts:
        if not os.path.exists(args.readouts):
            print("取不到读数件：%s —— 明写取不到，不编数" % args.readouts, file=sys.stderr)
            return 3
        rows = load_rows(args.readouts)
        violations, warnings = check_rows(rows)
        for note in warnings:
            print("- 告警 ｜ %s" % note, file=sys.stderr)
        segments = []
        seen = {}
        for row in rows:
            segment = str(row.get("segment") or "")
            if segment not in seen:
                seen[segment] = True
                segments.append(segment)
        print("## 云端形状窗读数校验（件=%s）" % args.readouts)
        print("- 行数=%d ｜ 段数=%d ｜ 格表指纹=%s" % (len(rows), len(segments), table_sha256()[:16]))
        for segment in segments:
            members = [row for row in rows if str(row.get("segment") or "") == segment]
            calibers = sorted({str(row.get("caliber") or "<缺>") for row in members})
            cells = sorted({name for row in members for name in row_cells(row)})
            bad = [v for v in violations if v["segment"] == segment]
            verdict = "🔴 拒" if bad else ("可" if CALIBER_CLOUD in calibers else "本机")
            print("| %s | %s | %s | %d | %s |" % (segment, "／".join(calibers), ",".join(cells) or "无",
                                                  len(bad), verdict))
        if violations:
            print("### 拒绝明细（判据③）", file=sys.stderr)
            for v in violations:
                print("- 拒绝 ｜ rule=%s segment=%s caliber=%s 格=%s ｜ %s" % (
                    v["rule"], v["segment"], v["caliber"], v["cell"], v["detail"]), file=sys.stderr)
            print("🔴 本批读数不许收：云端口径与时延／分数格不得同段（%d 条）" % len(violations),
                  file=sys.stderr)
            return 2
        print("- 结论：PASS ｜ 云端段全部只含形状格，本机段口径齐备")
        return 0

    if args.json:
        json.dump(table_payload(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        print()
        return 0

    print("# 云端形状窗 · 格表（R453 判据③）")
    for line in render_markdown():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
