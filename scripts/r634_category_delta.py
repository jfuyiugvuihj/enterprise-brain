# -*- coding: utf-8 -*-
"""R634 —— A 门④「逐类不退化」的归因尺：同类目跨窗 delta，噪声底与退化分开算

===== 本件交什么、不交什么 =====
交三样数：① 逐类目在「基线窗 -> 对照窗」之间的 correctness／evidence_coverage／
unsupported_claim_rate／p95 差值与题号；② 同码两跑之间本来就有多大逐类摆动（噪声底），
它单独成一格，不与退化混在同一张表里；③ 每一枚翻分题逐枚点名（丢了哪枚锚词、答案字数／
evidence_n／tool_calls／kind 怎么变、算「答得不同」还是「没答／哨兵／批准失败」）。
🔴 不交结论：verdict 只有「超底／底内／判不了／样本不足」四档，本件不许出现「A④ 达标」或
「逐类不退化成立」那一句——账上明写这一格欠的是一枚归因单，不是门，判它归业主与总控。

===== 为什么必须先量底 =====
历史那一枚真退化（run4 抓到文档问答 0.6842 -> 0.6316）＝ 19 题里掉 1 题＝ 0.0526；而同码
两跑（run18 -> run19）实测的逐类摆动也在这一档。所以「某类掉了 1 题」今天证不了退化。
代码上的钉：verdict=regression 只可能产生在【跨代次对子】上，且该类目该指标必须先有由
同指纹对子量出来的底；底没量出来时一律写 undecidable_no_floor，不写退化、也不写绿。

===== 窗身份与代次（都不抄第二本账） =====
窗身份五项 = eval_window_shard_driver.FINGERPRINT_KEYS（镜像 revision ∧ 容器 INDEX_BACKEND ∧
fixture sha256 ∧ transport ∧ shard_size），逐字取自开窗那枚 <tag>.window.json。
* 五项全等          = 同码同条件的复跑 ⇒ 差值只可能是摆动，进底、不进退化；
* 代次等其余格不等  = 同代次、条件被换过（run20k 的 index_backend＝空串＝缺省 Chroma 读腿）
                      ⇒ 唯一变量不是代次，本件只列差值不判退化（那一刀归 R580）；
* revision 或 sha 不等 = 跨代次 ⇒ 本件唯一能产出退化判定的那一组，且必须有底；
* 窗记没交           = 代次不可证 ⇒ 只进分代列表，不进任何比较表（docs/testing 从 run5 起全在这档）。
现场重算的 --fixture sha 与窗记里的不等 ⇒ 当场拒（rc=3）：拿今天的锚词去判昨天的窗就是假账。

===== 尺（一枚都不新造；另写一套算不算对就是平行实现） =====
判对错 quality_eval._is_correct；出处与无据断言 quality_eval.evaluate_provenance；
时延格子 quality_eval.aggregate_latency_ms（逐类目＝同一枚函数切子集，不另写排名规则）；
answers 的读法 runner._load_answers；批准账本 quality_eval.load_approval_ledger；
分母账 quality_eval.derive_scorability；jsonl／json 的读法复用 r580.read_jsonl／read_json_object。
🔴 逐类目读数与落盘 report 逐格对账（三数 + 每类目三格 + 时延四格），对不上就 rc=3 明写
「取不到可信读数」，不许挑一把能对上的尺报数。

===== 纪律 =====
只读：三本账、题集、窗记一律只读打开，一个字节都不往输入里写；不打模型、不开容器、
不动 PG、不重跑任何窗。默认产物只落 stdout（仓外），--out 指进仓内直接拒。

退出码（写死）：
  0 干净    —— 取到全部件，且所有可判格都在底内（含无恶化）
  2 检出退化 —— 至少一格跨代次恶化严格超过同码摆动底
  3 取不到  —— 件缺／半行／题数对不上／代次不可证却要重算／与落盘报告对账破（不拿 0 冒充）
  4 判不了  —— 底没量出来、或盘上没有跨代次对子、或全部格样本不足（这不是绿灯）

用法：
  python scripts/r634_category_delta.py --window run18 --window run19 --window run20k
  python scripts/r634_category_delta.py --window run18 --window run19 --format json --out D:/tmp/r634.json
  python scripts/r634_category_delta.py --report docs/testing/evaluation-report-run9.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
for _extra_path in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if _extra_path not in sys.path:
        sys.path.insert(0, _extra_path)

from app.quality import eval as quality_eval  # noqa: E402  在册尺：只经模块属性调用
from app.quality import runner  # noqa: E402  answers 的在册读法（含 utf-8-sig 与后行覆盖前行）
from eval_window_shard_driver import FINGERPRINT_KEYS, fixture_sha256  # noqa: E402  窗身份真源
import r580_per_class_attribution as r580  # noqa: E402  read_jsonl／read_json_object：在册读法

EXIT_CLEAN = 0
EXIT_REGRESSION = 2
EXIT_UNREADABLE = 3
EXIT_NOT_JUDGED = 4

EXIT_MEANING = {
    EXIT_CLEAN: "干净：所有可判格都在同码摆动底内",
    EXIT_REGRESSION: "检出退化：至少一格跨代次恶化严格超过底",
    EXIT_UNREADABLE: "取不到：件缺／读不出／题数对不上／与落盘报告对账破",
    EXIT_NOT_JUDGED: "判不了：底没量出来、或没有跨代次对子、或全部格样本不足（非绿灯）",
}

RATE_METRICS = ("correctness", "evidence_coverage", "unsupported_claim_rate")
LATENCY_METRIC = "p95_ms"
METRICS = RATE_METRICS + (LATENCY_METRIC,)
#: 恶化方向：这些指标越大越坏，其余越小越坏。底与退化都按「恶化量」比，不按带符号的差值比。
WORSE_IS_UP = frozenset({"unsupported_claim_rate", LATENCY_METRIC})

PAIR_SAME_FINGERPRINT = "same_fingerprint"
PAIR_SAME_GEN_OTHER_CELL = "condition_confounded"
PAIR_CROSS_GENERATION = "cross_generation"
PAIR_GENERATION_UNKNOWN = "generation_unprovable"
PAIR_LABELS = {
    PAIR_SAME_FINGERPRINT: "同指纹复跑（这一对子的差值就是底本身）",
    PAIR_SAME_GEN_OTHER_CELL: "同代次·换过条件（唯一变量不是代次，不判退化）",
    PAIR_CROSS_GENERATION: "跨代次（本件唯一能判退化的一组）",
    PAIR_GENERATION_UNKNOWN: "代次不可证（窗记未交，只进分代列表）",
}

VERDICT_REGRESSION = "regression"
VERDICT_WITHIN_FLOOR = "within_noise_floor"
VERDICT_NO_DROP = "no_drop"
VERDICT_INSUFFICIENT = "insufficient_sample"
VERDICT_NO_FLOOR = "undecidable_no_floor"
VERDICT_FLOOR_INPUT = "noise_floor_input"
VERDICT_NOT_CROSS_GEN = "not_a_generation_step"
VERDICT_GEN_UNKNOWN = "generation_unprovable"

#: 代次＝本单判的两枚读数：镜像 revision 与题集 sha256。其余格只算条件，不算代次。
GENERATION_KEYS = ("revision", "fixture_sha256")
MIN_CATEGORY_TOTAL_DEFAULT = 5
DRIVER_ROW_LIMIT = 5

ARTIFACT_PATTERNS = {
    "report": ("{label}-report.json", "evaluation-report-{label}.json", "report-{label}.json"),
    "answers": ("{label}-answers.jsonl", "answers-{label}.jsonl"),
    "sidecar": ("{label}-sidecar.jsonl", "sidecar-{label}.jsonl"),
    "window": ("{label}.window.json",),
    "frames": ("{label}-sidecar-frames.jsonl", "sidecar-{label}-frames.jsonl"),
}
#: 一扇窗要出题级点名，至少得交齐这两枚；缺任何一枚 = 取不到（rc=3），不许拿 0 冒充。
MANDATORY_KINDS = ("report", "answers")


class UnreadableError(RuntimeError):
    """取不到件：件不在／半行／题数对不上 ⇒ rc=3。"""


class ReconcileError(RuntimeError):
    """取不到可信读数：与落盘报告对账破，或代次与现场题集不符 ⇒ rc=3。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _display_width(text) -> int:
    width = 0
    for char in str(text):
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def _padded(text, width: int) -> str:
    text = str(text)
    return text + " " * max(0, width - _display_width(text))


def _table(rows) -> str:
    """把若干行等宽格子拼成一张表（中文按双宽度对齐，纯文本，不进仓）。"""
    if not rows:
        return ""
    widths = [max(_display_width(row[column]) for row in rows)
              for column in range(len(rows[0]))]
    lines = []
    for index, row in enumerate(rows):
        lines.append("  ".join(_padded(cell, widths[column]) for column, cell in enumerate(row)).rstrip())
        if index == 0:
            lines.append("-" * min(120, sum(widths) + 2 * (len(widths) - 1)))
    return "\n".join(lines)


def _clean(value):
    """把 -0.0 这种浮点数尾巴归成 0：读数面上不许出现"-0.0000＝没变"。"""
    number = float(value)
    return 0.0 if number == 0 else number


def _format_value(metric: str, value) -> str:
    if value is None:
        return "未量到"
    if metric == LATENCY_METRIC:
        return "%.1f" % _clean(value)
    return "%.4f" % _clean(value)


def _delta_of(metric: str, value) -> str:
    if value is None:
        return "未量到"
    number = _clean(value)
    return ("%+.4f" if metric != LATENCY_METRIC else "%+.1f") % (number if number else 0.0)


# ---------------------------------------------------------------- 读件（只读）

def default_evalrun_dir() -> Path:
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    return (Path(temp) / "evalrun") if temp else (Path.home() / "evalrun")


def discover(root: Path, label: str) -> dict:
    """在一层目录里按在册命名找一扇窗的五枚件（%TEMP%\\evalrun 与 docs/testing 是两层）。"""
    found = {}
    for kind, patterns in ARTIFACT_PATTERNS.items():
        for pattern in patterns:
            candidate = root / pattern.format(label=label)
            if candidate.is_file():
                found[kind] = candidate
                break
    return found


def report_label_of(path: Path) -> str:
    stem = Path(path).name
    for prefix, suffix in (("evaluation-report-", None), ("report-", None),
                           (None, "-report"), (None, ".report")):
        if prefix and stem.startswith(prefix) and stem.endswith(".json"):
            return stem[len(prefix):-len(".json")]
        if suffix and stem.endswith(suffix + ".json"):
            return stem[: -len(suffix + ".json")]
    return Path(stem).stem


def resolve_windows(args) -> list:
    """把 --window／--report 两种给法收成一串窗，逐枚点名件的来处与缺的那一枚。"""
    roots = [Path(item).expanduser().resolve() for item in (args.dir or [default_evalrun_dir()])]
    windows = []
    seen_labels = set()
    for label in args.window:
        hit = None
        for root in roots:
            found = discover(root, label)
            if found:
                hit = (root, found)
                break
        if hit is None:
            raise UnreadableError("取不到窗 " + str(label) + "：在这些层里一枚件都没有——"
                                  + "、".join(str(root) for root in roots)
                                  + "（换 --dir 指层，别在这一层查不到就宣布另一层也没有）")
        root, found = hit
        missing = [kind for kind in MANDATORY_KINDS if kind not in found]
        if missing:
            raise UnreadableError("取不到窗 " + str(label) + " 的必读件：" + "、".join(missing)
                                  + "（层＝" + str(root) + "）⇒ 这一窗不许出数，也不许当零摆动")
        windows.append({"label": label, "root": str(root), "paths": {kind: str(path) for kind, path in found.items()},
                        "order_fallback": _mtime(found["answers"])})
    for raw in args.report:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise UnreadableError("取不到报告件：" + str(path))
        label = report_label_of(path)
        windows.append({"label": label, "root": str(path.resolve().parent),
                        "paths": {"report": str(path)}, "order_fallback": _mtime(path)})
    for index, win in enumerate(windows, 1):
        if win["label"] in seen_labels:
            raise UnreadableError("取不到：窗名重了（" + win["label"] + "）⇒ 基线与对照分不清谁是谁")
        seen_labels.add(win["label"])
        win["index"] = index
    if not windows:
        raise UnreadableError("取不到：一枚窗都没给（--window 或 --report 至少给一枚）")
    return windows


def _mtime(path) -> float:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def load_fixture_rows(path: Path) -> list:
    try:
        rows = r580.read_jsonl(path, "题集（评测集）")
    except r580.RefuseError as error:
        raise UnreadableError(str(error))
    by_id = {}
    for row in rows:
        row_id = str(row.get("id", "") or "").strip()
        if not row_id:
            raise UnreadableError("题集里有一枚没有题号 ⇒ 逐类归因没法点名")
        if row_id in by_id:
            raise UnreadableError("题集里题号重了：" + row_id)
        by_id[row_id] = row
    if not rows:
        raise UnreadableError("取不到题集内容：" + str(path) + " 是空的")
    return rows


def read_identity(win: dict) -> dict | None:
    """窗记（<tag>.window.json）＝这一窗五项指纹的唯一出处；没交就是代次不可证。"""
    path = win["paths"].get("window")
    if not path:
        return None
    payload = r580.read_json_object(path, win["label"] + " 的窗记")
    if not isinstance(payload, dict):
        return None
    return payload


# ---------------------------------------------------------------- 逐窗读数

def _answer_text(result) -> str:
    return quality_eval._answer_text(result)


def _evidence_ok(row: dict, provenance: dict) -> bool:
    """与在册尺同一式子：不要求出处的题一律算过，要求的题看 has_evidence。"""
    return (not row.get("requires_evidence", False)) or bool(provenance["has_evidence"])


def measure_window(win: dict, fixture_rows: list, fixture_sha: str) -> None:
    """一扇窗的逐类目读数：一律现算，并与它自己那份落盘 report 逐格对账。"""
    paths = win["paths"]
    identity = read_identity(win)
    win["identity"] = identity
    win["generation"] = None
    win["fingerprint"] = None
    win["reconcile"] = {"status": "未做", "checks": [], "notes": []}
    win["measured"] = True
    win["measure_gap"] = ""
    win["ledger_rows"] = None
    win["scorability"] = None
    if identity is not None:
        win["fingerprint"] = [str(identity.get(key, "")) for key in FINGERPRINT_KEYS]
        revision = str(identity.get("revision", "") or "").strip()
        sha = str(identity.get("fixture_sha256", "") or "").strip()
        if revision and sha:
            win["generation"] = [revision, sha]
    report = r580.read_json_object(paths.get("report"), win["label"] + " 的报告") if paths.get("report") else None
    win["report_present"] = isinstance(report, dict)
    win["started_at"] = (identity or {}).get("started_at") or ""

    if win["generation"] is None:
        win["measured"] = False
        win["measure_gap"] = ("窗记未交或窗记里读不出 revision／fixture_sha256 ⇒ 代次不可证："
                              "本件不重算、不对账，只把报告里已有的读数列进分代列表，不进任何比较表")
        win["categories"] = report_categories(report)
        win["global"] = report_global(report)
        win["rows"] = {}
        return
    if win["fingerprint"] is None:
        raise ReconcileError(win["label"] + " 的窗记读不出五项指纹 ⇒ 这窗的身份没法钉")
    recorded_sha = str((identity or {}).get("fixture_sha256", ""))
    if recorded_sha.lower() != fixture_sha.lower():
        raise ReconcileError(win["label"] + " 窗记里的题集 sha 与现场重算的 --fixture 不等（"
                             + (recorded_sha[:12] or "未量到") + " vs " + fixture_sha[:12]
                             + "）⇒ 拿今天的锚词判这一窗就是假账，本件拒绝出数")

    try:
        answers = runner._load_answers(paths["answers"])
    except (ValueError, KeyError, OSError) as error:
        raise UnreadableError("取不到 " + win["label"] + " 的 answers（" + str(paths["answers"])
                              + "）：" + str(error))
    ledger = None
    if paths.get("sidecar"):
        try:
            ledger = quality_eval.load_approval_ledger(paths["sidecar"])
        except FileNotFoundError as error:
            raise UnreadableError("取不到 " + win["label"] + " 的批准账本：" + str(error))
        except (ValueError, OSError) as error:
            raise UnreadableError("取不到 " + win["label"] + " 的批准账本（" + str(paths["sidecar"]) + "）：" + str(error))
    win["ledger_rows"] = len(ledger) if ledger is not None else None
    if ledger is not None:
        win["reconcile"]["notes"].append("批准账本按在册读法折叠（同题取最后一行）；半行按既有纪律跳过")

    # 时延那一格用哪两列读数，由报告自己说：报告带 approval_ledger 那一格 = 尺收过帧账。
    ledger_for_latency = bool(isinstance(report, dict) and "approval_ledger" in report)
    if not ledger_for_latency and report is not None:
        win["reconcile"]["notes"].append("落盘报告没有 approval_ledger 那一格 ⇒ 在册尺只吃了 answers 的实测跨度，"
                                         "本件逐类目时延同此口径（不拿侧车另起一把）")

    rows = {}
    spans = []
    for row in fixture_rows:
        row_id = str(row.get("id"))
        result = answers.get(row_id, {"answer": "", "evidence": [], "latency_ms": None})
        provenance = quality_eval.evaluate_provenance(result if isinstance(result, dict) else {})
        text = _answer_text(result)
        expected = [str(item) for item in row.get("must_contain", [])]
        hits = [item for item in expected if item in text]
        side = (ledger or {}).get(row_id) or {}
        reported = result.get("latency_ms") if isinstance(result, dict) else None
        frame = side.get("wall_ms") if ledger_for_latency else None
        spans.append({"id": row_id, "reported_ms": reported, "frame_ledger_ms": frame})
        verdict = quality_eval.classify_latency_span(row_id, reported, frame,
                                                     envelope_ms=quality_eval.latency_envelope_ms())
        citations = sorted({str(item.get("source_id") or item.get("source") or "")
                            for item in (result.get("evidence") or []) if isinstance(item, dict)})
        rows[row_id] = {
            "category": str(row.get("category", "未分类")),
            "tier": str(row.get("tier", "") or ""),
            "correct": bool(quality_eval._is_correct(row, result)),
            "expected_terms": expected,
            "hit_terms": hits,
            "missed_terms": [item for item in expected if item not in hits],
            "answer_chars": len(text),
            "answer_sha": _sha_of(text),
            "answer_missing_row": row_id not in answers,
            "citations": citations,
            "evidence_coverage": provenance["evidence_coverage"],
            "evidence_ok": _evidence_ok(row, provenance),
            "unsupported": bool(provenance["unsupported_claims"]),
            "claims_carried": bool(result.get("claims")) if isinstance(result, dict) else False,
            "used_ms": verdict["used_ms"],
            "latency_action": verdict["action"],
            "evidence_n": side.get("evidence_n"),
            "tool_calls": (side.get("tool_calls") if "tool_calls" in side
                           else (result.get("tool_calls") if isinstance(result, dict) else None)),
            "kind": side.get("kind"),
            "attempt": side.get("attempt"),
            "sentinel": side.get("sentinel"),
            "approved": side.get("approved"),
            "approval_rounds": side.get("approval_rounds"),
            "approval_error": side.get("approval_error"),
            "pre_kind": side.get("pre_kind"),
            "sidecar_missing": not paths.get("sidecar"),
        }
    win["rows"] = rows
    win["answers_rows"] = len(answers)
    if len(answers) != len(fixture_rows):
        extra = sorted(set(answers) - {str(row.get("id")) for row in fixture_rows})
        missing = sorted({str(row.get("id")) for row in fixture_rows} - set(answers))
        raise UnreadableError("取不到完整件：" + win["label"] + " 的 answers 有 " + str(len(answers))
                              + " 枚，题集有 " + str(len(fixture_rows)) + " 枚；题集缺的＝"
                              + ("、".join(missing) or "无") + "／题集里没有的＝" + ("、".join(extra) or "无")
                              + " ⇒ 不许按缺的行出分母")

    win["categories"] = aggregate_categories(fixture_rows, rows, spans)
    global_latency = quality_eval.aggregate_latency_ms(spans)
    win["global"] = {
        "total": len(fixture_rows),
        "answer_correctness": round(sum(bool(item["correct"]) for item in rows.values()) / len(rows), 4),
        "evidence_coverage": round(sum(1 for item in rows.values() if item["evidence_ok"]) / len(rows), 4),
        "unsupported_claim_rate": round(sum(1 for item in rows.values() if item["unsupported"]) / len(rows), 4),
        "claims_carried_n": sum(1 for item in rows.values() if item["claims_carried"]),
        "latency_ms": global_latency,
        "p95_ms": global_latency["p95"],
    }
    if report is not None:
        reconcile_with_report(win, report, fixture_rows)
    else:
        win["reconcile"]["status"] = "报告未交，无账可对"
        win["reconcile"]["notes"].append("这一窗只有 answers：读数能出，但拿不到在册报告的对照")


def _sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def report_categories(report) -> dict:
    """报告里的逐类目那一格原样搬来（代次不可证的窗只走这条路，不重算）。"""
    out = {}
    for category, cell in ((report or {}).get("category_metrics") or {}).items():
        out[str(category)] = {
            "total": cell.get("total"),
            "correctness": cell.get("correctness"),
            "evidence_coverage": cell.get("evidence_coverage"),
            "unsupported_claim_rate": None,
            "p95_ms": None,
            "rows": [],
            "source": "报告原样（未重算）",
        }
    return out


def report_global(report) -> dict:
    out = {"total": None, "answer_correctness": None, "evidence_coverage": None,
           "unsupported_claim_rate": None, "p95_ms": None, "subset": None, "source": "报告未交"}
    if not isinstance(report, dict):
        return out
    cell = report.get("latency_ms") or {}
    out.update({
        "total": report.get("total"),
        "answer_correctness": report.get("answer_correctness"),
        "evidence_coverage": report.get("evidence_coverage"),
        "unsupported_claim_rate": report.get("unsupported_claim_rate"),
        "p95_ms": cell.get("p95"),
        "subset": report.get("answer_correctness_scorable_subset"),
        "source": "报告原样（未重算）",
    })
    return out


def aggregate_categories(fixture_rows: list, rows: dict, spans: list) -> dict:
    """逐类目四格：correctness／evidence／unsupported_claim_rate 现算，p95 走在册同一枚聚合函数切子集。"""
    order = []
    buckets = {}
    for row in fixture_rows:
        category = rows[str(row.get("id"))]["category"]
        if category not in buckets:
            buckets[category] = []
            order.append(category)
        buckets[category].append(str(row.get("id")))
    span_by_id = {str(item["id"]): item for item in spans}
    out = {}
    for category in order:
        ids = buckets[category]
        total = len(ids)
        correct = sum(1 for row_id in ids if rows[row_id]["correct"])
        evidence = sum(rows[row_id]["evidence_coverage"] for row_id in ids)
        unsupported = sum(1 for row_id in ids if rows[row_id]["unsupported"])
        cell = quality_eval.aggregate_latency_ms([span_by_id[row_id] for row_id in ids])
        out[category] = {
            "total": total,
            "correctness": round(correct / total, 4) if total else 0.0,
            "evidence_coverage": round(evidence / total, 4) if total else 0.0,
            "unsupported_claim_rate": round(unsupported / total, 4) if total else 0.0,
            "p95_ms": cell["p95"],
            "rows": ids,
            "source": "现算（与在册报告逐格对账）",
        }
    return out


def reconcile_with_report(win: dict, report: dict, fixture_rows: list) -> None:
    """🔴 与在册尺的落盘读数逐格对账：对不上就拒（rc=3），不许挑一把能对上的尺报数。"""
    problems = []
    checks = win["reconcile"]["checks"]
    global_cell = win["global"]
    rows = win["rows"]
    scorability = quality_eval.derive_scorability(fixture_rows)
    subset = quality_eval.correctness_subset_ruler(
        [{"row": row, "result": {}, "correct": rows[str(row.get("id"))]["correct"]} for row in fixture_rows],
        scorability)
    win["scorability"] = {
        "deducted_ids": [str(item) for item in scorability.get("deducted_ids") or []]
        or [str(item["id"]) for item in scorability.get("deducted_rows") or []],
        "denominator_rows": scorability.get("denominator_rows"),
        "deducted_n": scorability.get("deducted_n"),
        "subset_ruler": subset[quality_eval.SUBSET_RULER_KEY],
    }
    for name, want, got in (
        ("total", report.get("total"), global_cell["total"]),
        ("answer_correctness", report.get("answer_correctness"), global_cell["answer_correctness"]),
        ("evidence_coverage", report.get("evidence_coverage"), global_cell["evidence_coverage"]),
        ("unsupported_claim_rate", report.get("unsupported_claim_rate"),
         global_cell["unsupported_claim_rate"]),
        (quality_eval.SUBSET_RULER_KEY, report.get(quality_eval.SUBSET_RULER_KEY),
         subset[quality_eval.SUBSET_RULER_KEY]),
    ):
        if want is None:
            continue
        if got is None:
            problems.append(name + "：报告有数、本件读不出")
            continue
        checks.append({"cell": name, "report": want, "recomputed": got, "equal": want == got})
        if want != got:
            problems.append(name + " 报告＝" + str(want) + " 本件现算＝" + str(got))

    report_latency = report.get("latency_ms") or {}
    mine_latency = global_cell["latency_ms"]
    for name in ("count", "average", "p95", "max"):
        if name not in report_latency:
            continue
        want, got = report_latency[name], mine_latency.get(name)
        checks.append({"cell": "latency_ms." + name, "report": want, "recomputed": got, "equal": want == got})
        if want != got:
            problems.append("latency_ms." + name + " 报告＝" + str(want) + " 本件现算＝" + str(got))

    report_categories_map = report.get("category_metrics")
    if isinstance(report_categories_map, dict):
        for category, cell in report_categories_map.items():
            mine = win["categories"].get(category)
            if mine is None:
                problems.append("类目「" + category + "」在报告里有、本件算不出来")
                continue
            for name in ("total", "correctness", "evidence_coverage"):
                if name not in cell:
                    continue
                want, got = cell[name], mine[name]
                checks.append({"cell": "category_metrics." + category + "." + name,
                               "report": want, "recomputed": got, "equal": want == got})
                if want != got:
                    problems.append("类目「" + category + "」" + name + " 报告＝" + str(want)
                                    + " 本件现算＝" + str(got))
        for category in win["categories"]:
            if category not in report_categories_map:
                problems.append("类目「" + category + "」本件算出来了、报告里没有 ⇒ 题集与报告不同源")

    if problems:
        raise ReconcileError(win["label"] + " 与落盘报告对账破（共 " + str(len(problems)) + " 格）："
                             + "；".join(problems[:8]) + " ⇒ 取不到可信读数，本件拒绝出数")
    win["reconcile"]["status"] = "全格对上（" + str(len(checks)) + " 格）"


def rows_of(win: dict) -> dict:
    return win["rows"]# ---------------------------------------------------------------- 配对（基线 -> 对照）

def order_value(win: dict) -> str:
    """基线与对照谁先谁后：窗记里的 started_at 优先，没交就退回件本身的 mtime。"""
    started = str(win.get("started_at") or "").strip()
    if started:
        return started
    return datetime.fromtimestamp(float(win.get("order_fallback") or 0.0)).strftime("%Y-%m-%d %H:%M:%S")


def make_pair(a: dict, b: dict) -> dict:
    """两扇窗的对照关系由指纹现读决定，不由功能名称决定（本单的钉全在这一格）。"""
    pair = {"baseline": a["label"], "compare": b["label"], "a": a, "b": b,
            "baseline_order": order_value(a), "compare_order": order_value(b),
            "diff_cells": [], "note": ""}
    if not a["measured"] or not b["measured"]:
        pair["class"] = PAIR_GENERATION_UNKNOWN
        gaps = [win["label"] + "（" + str(win.get("measure_gap", ""))[:60] + "）"
                for win in (a, b) if not win["measured"]]
        pair["note"] = "代次不可证：" + "、".join(gaps) + " ⇒ 只进分代列表，不进比较表"
        return pair
    pair["diff_cells"] = [key for key, left, right in zip(FINGERPRINT_KEYS, a["fingerprint"], b["fingerprint"])
                          if left != right]
    if not pair["diff_cells"]:
        pair["class"] = PAIR_SAME_FINGERPRINT
        pair["note"] = "五项指纹全等：这两扇是同码同条件的复跑，差值只可能是摆动"
    elif a["generation"] == b["generation"]:
        pair["class"] = PAIR_SAME_GEN_OTHER_CELL
        pair["note"] = ("revision 与题集 sha 相同，换掉的是 " + "、".join(pair["diff_cells"])
                        + " ⇒ 唯一变量不是代次，退化与否本件不判（那一刀归 R580）")
    else:
        pair["class"] = PAIR_CROSS_GENERATION
        pair["note"] = ("代次不同：" + "、".join("%s=%s->%s" % (key, left, right) for key, left, right
                                                in zip(GENERATION_KEYS, a["generation"], b["generation"]))
                        + "（其余不等格：" + ("、".join(pair["diff_cells"]) or "无") + "）")
    pair["cells"] = compute_pair_cells(pair)
    return pair


def _category_union(a: dict, b: dict) -> list:
    order = list(a["categories"])
    order += [category for category in b["categories"] if category not in order]
    return order


def driver_rows(a: dict, b: dict, category: str, metric: str) -> list:
    """这一格差值是哪几枚题搬动的：逐枚点名，题数截到上限，但一枚都不许默默消失。"""
    ids = sorted({row_id for row_id, row in a["rows"].items() if row["category"] == category}
                 | {row_id for row_id, row in b["rows"].items() if row["category"] == category})
    picks = []
    for row_id in ids:
        left = a["rows"].get(row_id)
        right = b["rows"].get(row_id)
        if metric == "correctness":
            if not left or not right or left["correct"] == right["correct"]:
                continue
            dropped = bool(left["correct"]) and not bool(right["correct"])
            picks.append({"id": row_id, "a": bool(left["correct"]), "b": bool(right["correct"]),
                          "worsened": dropped, "weight": 1 if dropped else 0})
        elif metric == "evidence_coverage":
            if not left or not right or left["evidence_coverage"] == right["evidence_coverage"]:
                continue
            delta = right["evidence_coverage"] - left["evidence_coverage"]
            picks.append({"id": row_id, "a": left["evidence_coverage"], "b": right["evidence_coverage"],
                          "delta": round(delta, 4), "worsened": delta < 0, "weight": abs(delta)})
        elif metric == "unsupported_claim_rate":
            if not left or not right or left["unsupported"] == right["unsupported"]:
                continue
            newly = (not left["unsupported"]) and bool(right["unsupported"])
            picks.append({"id": row_id, "a": bool(left["unsupported"]), "b": bool(right["unsupported"]),
                          "worsened": newly, "weight": 1 if newly else 0})
        elif metric == LATENCY_METRIC:
            if not left or not right:
                continue
            left_ms, right_ms = left["used_ms"], right["used_ms"]
            if left_ms is None or right_ms is None or abs(right_ms - left_ms) <= 0.05:
                continue
            delta_ms = right_ms - left_ms
            picks.append({"id": row_id, "a": round(left_ms, 1), "b": round(right_ms, 1),
                          "delta_ms": round(delta_ms, 1), "worsened": delta_ms > 0,
                          "weight": abs(delta_ms)})
    picks.sort(key=lambda item: (not item["worsened"], -item.get("weight", 0), item["id"]))
    return {
        "count_changed_rows": len(picks),
        "count_worsened_rows": sum(1 for item in picks if item["worsened"]),
        "limit": DRIVER_ROW_LIMIT,
        "rows": [{key: value for key, value in item.items() if key != "weight"}
                 for item in picks[:DRIVER_ROW_LIMIT]],
    }


def compute_pair_cells(pair: dict) -> dict:
    a, b = pair["a"], pair["b"]
    cells = {}
    for category in _category_union(a, b):
        left_cell = a["categories"].get(category) or {}
        right_cell = b["categories"].get(category) or {}
        total_a = left_cell.get("total")
        total_b = right_cell.get("total")
        per_metric = {}
        for metric in METRICS:
            value_a = left_cell.get(metric)
            value_b = right_cell.get(metric)
            entry = {"baseline": value_a, "compare": value_b, "delta": None,
                     "worsening": None, "improving": None, "total_a": total_a, "total_b": total_b,
                     "quantum": round(1.0 / min(total_a, total_b), 4) if total_a and total_b else None}
            if value_a is not None and value_b is not None:
                delta = round(float(value_b) - float(value_a), 6)
                worsening = delta if metric in WORSE_IS_UP else -delta
                entry["delta"] = _clean(round(delta, 6))
                entry["worsening"] = _clean(round(worsening, 6))
                entry["improving"] = _clean(round(-worsening, 6))
                # 🔴 底按「摆动量」＝差值的绝对值：同码复跑里方向是随机的，
                # 只取恶化那一侧会把「这一类明明摆动了 0.0527（往好摆）」当成底＝0。
                entry["swing"] = round(abs(delta), 6)
                entry["drivers"] = driver_rows(a, b, category, metric)
            per_metric[metric] = entry
        cells[category] = per_metric
    return cells


# ---------------------------------------------------------------- 噪声底

def floor_key(window: dict) -> str:
    return json.dumps(window["generation"], ensure_ascii=False) if window["generation"] else ""


def build_floors(pairs: list) -> dict:
    """🔴 底只从「同指纹复跑对子」长出来：那一组里没有任何代码变化，差值全是摆动。"""
    floors = {}
    for pair in pairs:
        if pair.get("class") != PAIR_SAME_FINGERPRINT:
            continue
        key = floor_key(pair["a"])
        bucket = floors.setdefault(key, {"pairs": [], "cells": {}})
        bucket["pairs"].append(pair["baseline"] + "->" + pair["compare"])
        for category, per_metric in (pair.get("cells") or {}).items():
            target = bucket["cells"].setdefault(category, {})
            for metric, entry in per_metric.items():
                if entry.get("swing") is None:
                    continue
                drivers = entry.get("drivers") or {}
                current = target.get(metric)
                record = {"value": entry["swing"], "pair": pair["baseline"] + "->" + pair["compare"],
                          "worsening": entry["worsening"],
                          "moved_ids": [item["id"] for item in drivers.get("rows", [])],
                          "worsened_ids": [item["id"] for item in drivers.get("rows", []) if item.get("worsened")]}
                if current is None or record["value"] > current["value"]:
                    target[metric] = record
                elif record["value"] == current["value"] and record["value"] > 0:
                    current["tied_pairs"] = (current.get("tied_pairs") or []) + [record["pair"]]
    return floors


def floor_for(floors: dict, pair: dict, category: str, metric: str) -> dict:
    """跨代次那一组用哪一把底：取两代各自复跑底里较大的那把（宁可宽判也不误报退化）。"""
    readouts = []
    best = None
    for side, window in (("baseline", pair["a"]), ("compare", pair["b"])):
        bucket = floors.get(floor_key(window)) or {}
        cell = ((bucket.get("cells") or {}).get(category) or {}).get(metric)
        if cell:
            readouts.append({"side": side, "generation": window["generation"],
                             "pairs": bucket.get("pairs"), "value": cell["value"],
                             "from_pair": cell["pair"], "row_ids": cell.get("row_ids") or []})
            if best is None or cell["value"] > best["value"]:
                best = cell
    if best is None:
        covered = [key for key in (floor_key(pair["a"]), floor_key(pair["b"])) if key in floors]
        reason = ("这一格（" + category + "／" + metric + "）在两窗所属代次的同码复跑里没量到读数"
                  "（那一类缺席或件不齐）⇒ 底缺这一格，不判" if covered else
                  "盘上没有同指纹复跑对子（代次 " + json.dumps(pair["a"]["generation"], ensure_ascii=False)
                  + " 与 " + json.dumps(pair["b"]["generation"], ensure_ascii=False)
                  + " 各只有孤窗）⇒ 同码摆动没量出来，本件不许宣布任何一格退化")
        return {"value": None, "sources": readouts, "reason": reason}
    return {"value": best["value"], "sources": readouts, "reason": ""}

# ---------------------------------------------------------------- 判定（底先于退化）

def judge_pair(pair: dict, floors: dict, min_total: int) -> None:
    """逐格给 verdict：同码摆动底没量出来时，跨代次那一组也只能写 undecidable，不写退化、更不写绿。"""
    for category, per_metric in (pair.get("cells") or {}).items():
        for metric, entry in per_metric.items():
            entry["floor"] = None
            entry["floor_sources"] = []
            if pair["class"] == PAIR_GENERATION_UNKNOWN:
                entry["verdict"] = VERDICT_GEN_UNKNOWN
                entry["verdict_reason"] = pair["note"]
                continue
            totals = [value for value in (entry["total_a"], entry["total_b"]) if value is not None]
            smallest = min(totals) if totals else 0
            if smallest < min_total:
                entry["verdict"] = VERDICT_INSUFFICIENT
                entry["verdict_reason"] = ("这一类在两窗里最少只剩 " + str(smallest) + " 枚（样本闸＝"
                                           + str(min_total) + " 枚）⇒ 样本不足，不许判，也不许当成没退化")
                continue
            if entry["worsening"] is None:
                entry["verdict"] = VERDICT_NO_FLOOR
                entry["verdict_reason"] = "这一格至少一窗没读数（类目在一窗里缺席或报告未交）⇒ 差值量不到，不判"
                continue
            if pair["class"] == PAIR_SAME_FINGERPRINT:
                entry["verdict"] = VERDICT_FLOOR_INPUT
                entry["verdict_reason"] = "同码同条件复跑：这一格的恶化量就是摆动本身，按定义不进退化那一栏"
                continue
            if pair["class"] == PAIR_SAME_GEN_OTHER_CELL:
                entry["verdict"] = VERDICT_NOT_CROSS_GEN
                entry["verdict_reason"] = pair["note"]
                continue
            floor = floor_for(floors, pair, category, metric)
            entry["floor"] = floor["value"]
            entry["floor_sources"] = floor["sources"]
            if floor["value"] is None:
                entry["verdict"] = VERDICT_NO_FLOOR
                entry["verdict_reason"] = floor["reason"]
                continue
            if entry["worsening"] > floor["value"]:
                entry["verdict"] = VERDICT_REGRESSION
                entry["verdict_reason"] = ("跨代次恶化 " + _format_value(metric, entry["worsening"])
                                           + " 严格大于同码摆动底 " + _format_value(metric, floor["value"])
                                           + "（底的来路：" + "、".join(item["from_pair"] for item in floor["sources"])
                                           + "）")
            elif entry["worsening"] > 0:
                entry["verdict"] = VERDICT_WITHIN_FLOOR
                entry["verdict_reason"] = ("恶化 " + _format_value(metric, entry["worsening"]) + " 没超过同码摆动底 "
                                           + _format_value(metric, floor["value"]) + " ⇒ 与抖动分不开")
            else:
                entry["verdict"] = VERDICT_NO_DROP
                entry["verdict_reason"] = ("这一格没有恶化（改好了 " + _format_value(metric, entry["improving"])
                                           + "）" if entry["improving"] else "这一格两窗同数")


def classify_drop(left: dict, right: dict) -> tuple:
    """翻分那一枚到底变了什么：答得不同／没答／哨兵／批准失败，四选一，选不出就写量不到。"""
    if right.get("answer_missing_row"):
        return ("no_answer", "对照窗的 answers 里没有这一枚的终答行＝没答")
    if right.get("sentinel") is True:
        return ("sentinel", "侧车 sentinel=True：这一发被哨兵顶回来，没落成终答")
    if right.get("kind") == quality_eval.APPROVAL_FAILED_KIND or right.get("approval_error"):
        return ("approval_failed", "批准失败（kind＝" + str(right.get("kind")) + "，error＝"
                + str(right.get("approval_error") or "")[:80] + "）")
    if not right.get("answer_chars"):
        return ("no_answer", "答案空文本＝没答")
    if right.get("kind") not in (None, "ok", quality_eval.APPROVAL_KIND):
        return ("not_answered", "kind＝" + str(right.get("kind")) + " 未答完（在册那一族翻的是分母，不是答案质量）")
    if left.get("answer_sha") == right.get("answer_sha"):
        return ("same_text", "答案逐字节没变却掉了锚词 ⇒ 变的是锚词/题源那一代，不是这一发回答")
    lost = [term for term in left.get("hit_terms", []) if term not in right.get("hit_terms", [])]
    return ("answered_differently", "答得不同：这一窗丢了锚词 " + ("、".join(lost) or "（无逐枚丢项，全含判定被别的条件拦住）"))


def classify_gain(left: dict, right: dict) -> tuple:
    gained = [term for term in right.get("hit_terms", []) if term not in left.get("hit_terms", [])]
    if left.get("answer_sha") == right.get("answer_sha"):
        return ("same_text", "答案逐字节没变却收了分 ⇒ 锚词/题源变了，不是这一发回答变好")
    return ("answered_differently", "答得不同：这一窗新含住锚词 " + ("、".join(gained) or "（无）"))


def flip_signals(left: dict, right: dict) -> dict:
    """归类之外那三枚形状信号：归类答「算不算答了」，这三格答「答案变成了什么形状」。"""
    def moved(key, worse):
        first, second = left.get(key), right.get(key)
        if first is None or second is None:
            return None
        return bool(worse(first, second))

    return {
        "evidence_zeroed": moved("evidence_n", lambda first, second: first > 0 and second == 0),
        "tool_calls_zeroed": moved("tool_calls", lambda first, second: first > 0 and second == 0),
        "answer_shrank_over_half": moved("answer_chars", lambda first, second: first > 0 and second * 2 < first),
        "answer_chars_delta": right.get("answer_chars", 0) - left.get("answer_chars", 0),
        "short_answer_no_evidence": bool(right.get("answer_chars", 0) < 200
                                         and (right.get("evidence_n") or 0) == 0),
    }


def attribute_flips(pair: dict) -> None:
    """逐枚点名翻分题：锚词命中、答案字数／evidence_n／tool_calls／kind 的变化，全部两窗并排。"""
    flips = []
    a, b = pair["a"], pair["b"]
    for row_id in [row_id for row_id in a["rows"] if row_id in b["rows"]]:
        left, right = a["rows"][row_id], b["rows"][row_id]
        if left["category"] != right["category"]:
            flips.append({"id": row_id, "class": "category_moved", "direction": "n/a",
                          "class_reason": "同一枚题在两窗的类目不一样（" + str(left["category"]) + " vs "
                                          + str(right["category"]) + "）⇒ 题集不同代，这一枚不许进任何一类的账"})
            continue
        if left["correct"] == right["correct"]:
            continue
        direction = "drop" if (left["correct"] and not right["correct"]) else "gain"
        klass, reason = (classify_drop(left, right) if direction == "drop" else classify_gain(left, right))
        flips.append({
            "id": row_id,
            "category": left["category"],
            "tier": left["tier"],
            "direction": direction,
            "class": klass,
            "class_reason": reason,
            "expected_terms": left["expected_terms"],
            "hits_baseline": left["hit_terms"],
            "hits_compare": right["hit_terms"],
            "missed_baseline": left["missed_terms"],
            "missed_compare": right["missed_terms"],
            "answer_chars": {"baseline": left["answer_chars"], "compare": right["answer_chars"]},
            "answer_sha": {"baseline": left["answer_sha"], "compare": right["answer_sha"]},
            "answer_same_bytes": left["answer_sha"] == right["answer_sha"],
            "evidence_n": {"baseline": left["evidence_n"], "compare": right["evidence_n"]},
            "evidence_coverage": {"baseline": left["evidence_coverage"], "compare": right["evidence_coverage"]},
            "citations_changed": sorted(left["citations"]) != sorted(right["citations"]),
            "citations_only_baseline": sorted(set(left["citations"]) - set(right["citations"])),
            "citations_only_compare": sorted(set(right["citations"]) - set(left["citations"])),
            "tool_calls": {"baseline": left["tool_calls"], "compare": right["tool_calls"]},
            "kind": {"baseline": left["kind"], "compare": right["kind"]},
            "attempt": {"baseline": left["attempt"], "compare": right["attempt"]},
            "sentinel": {"baseline": left["sentinel"], "compare": right["sentinel"]},
            "approved": {"baseline": left["approved"], "compare": right["approved"]},
            "pre_kind": {"baseline": left["pre_kind"], "compare": right["pre_kind"]},
            "used_ms": {"baseline": left["used_ms"], "compare": right["used_ms"]},
            "in_deducted_ids": {"baseline": row_id in set((a.get("scorability") or {}).get("deducted_ids") or []),
                                "compare": row_id in set((b.get("scorability") or {}).get("deducted_ids") or [])},
            "sidecar_missing": bool(left.get("sidecar_missing") or right.get("sidecar_missing")),
            "signals": flip_signals(left, right),
        })
    pair["flips"] = flips


# ---------------------------------------------------------------- 汇总与退出码

def summarize(windows: list, pairs: list, floors: dict, min_total: int) -> dict:
    tally = {}
    regressions = []
    judged = 0
    for pair in pairs:
        for category, per_metric in (pair.get("cells") or {}).items():
            for metric, entry in per_metric.items():
                verdict = entry.get("verdict", "未判")
                tally[verdict] = tally.get(verdict, 0) + 1
                if verdict == VERDICT_REGRESSION:
                    regressions.append({"pair": pair["baseline"] + "->" + pair["compare"],
                                        "category": category, "metric": metric,
                                        "baseline": entry["baseline"], "compare": entry["compare"],
                                        "worsening": entry["worsening"], "floor": entry["floor"],
                                        "floor_sources": entry["floor_sources"],
                                        "reason": entry["verdict_reason"],
                                        "worsened_ids": [item["id"]
                                                         for item in (entry.get("drivers") or {}).get("rows", [])
                                                         if item.get("worsened")]})
                if pair["class"] == PAIR_CROSS_GENERATION and verdict in (
                        VERDICT_REGRESSION, VERDICT_WITHIN_FLOOR, VERDICT_NO_DROP):
                    judged += 1
    floor_generations = {key: value["pairs"] for key, value in floors.items()}
    cross = [pair for pair in pairs if pair["class"] == PAIR_CROSS_GENERATION]
    if regressions:
        code = EXIT_REGRESSION
        why = "检出 " + str(len(regressions)) + " 格跨代次恶化严格超过同码摆动底"
    elif judged:
        code = EXIT_CLEAN
        why = str(judged) + " 格可判，全部落在摆动底内或没有恶化"
    else:
        code = EXIT_NOT_JUDGED
        if not cross:
            why = ("盘上没有跨代次对子：所有可测对子的 revision 与题集 sha 全等（同码复跑或换了条件）"
                   " ⇒ 逐类不退化这件事今天量不到，不是没退化")
        elif not floors:
            why = "同码摆动底没量出来（没有同指纹复跑对子）⇒ 本件不许宣布退化，也不许判绿"
        else:
            why = "跨代次对子存在，但每一格都落在样本不足/读数缺失里 ⇒ 判不了"
    return {
        "verdict_tally": tally,
        "regressions": regressions,
        "cross_generation_pairs": len(cross),
        "judged_cross_generation_cells": judged,
        "noise_floor": {
            "measured": bool(floors),
            "per_generation_pairs": floor_generations,
            "cells": {key: value["cells"] for key, value in floors.items()},
            "note": ("底只由同指纹复跑对子量出；对子枚数＝"
                     + str(sum(len(items) for items in floor_generations.values()))
                     + " 枚。枚数为一时它是单样本，只是摆动的下界观测，不是分布——这条不许忘。"),
        },
        "min_category_total": min_total,
        "exit_code": code,
        "exit_meaning": EXIT_MEANING[code],
        "why": why,
    }

# ---------------------------------------------------------------- 交付面

def window_public(win: dict) -> dict:
    return {
        "label": win["label"],
        "dir": win["root"],
        "artifacts": win["paths"],
        "artifact_gaps": [kind for kind in ("report", "answers", "sidecar", "window", "frames")
                          if kind not in win["paths"]],
        "started_at": win.get("started_at") or "",
        "order_value": order_value(win),
        "fingerprint": dict(zip(FINGERPRINT_KEYS, win["fingerprint"])) if win.get("fingerprint") else None,
        "generation": win["generation"],
        "measured": win["measured"],
        "global": win["global"],
        "categories": {category: {key: value for key, value in cell.items() if key != "rows"}
                       for category, cell in win["categories"].items()},
        "reconcile": win["reconcile"],
        "scorability": win.get("scorability"),
        "ledger_rows": win.get("ledger_rows"),
    }


def pair_public(pair: dict) -> dict:
    return {
        "baseline": pair["baseline"],
        "compare": pair["compare"],
        "order": pair["baseline_order"] + " -> " + pair["compare_order"],
        "class": pair["class"],
        "class_label": PAIR_LABELS[pair["class"]],
        "note": pair["note"],
        "diff_cells": pair["diff_cells"],
        "cells": pair.get("cells", {}),
        "flips": pair.get("flips", []),
    }


def build_payload(result: dict) -> dict:
    return {
        "tool": "scripts/r634_category_delta.py",
        "ticket": "R634",
        "generated_at": result["generated_at"],
        "fixture": result["fixture"],
        "exit_code": result["summary"]["exit_code"],
        "exit_meaning": result["summary"]["exit_meaning"],
        "why": result["summary"]["why"],
        "windows": [window_public(win) for win in result["windows"]],
        "pairs": [pair_public(pair) for pair in result["pairs"]],
        "summary": result["summary"],
        "disclaimer": ("本件只交数与判据对照：verdict 只有超底/底内/判不了/样本不足四档。"
                       "A 门④ 达不达标不归本件判，那一句归业主与总控。"),
    }


def signal_brief(signals: dict) -> str:
    """形状那一列：哪一格塌了就说哪一格，塌不出来说「形状未变」。"""
    brief = []
    if signals.get("evidence_zeroed"):
        brief.append("证据清零")
    if signals.get("tool_calls_zeroed"):
        brief.append("工具调用清零")
    if signals.get("answer_shrank_over_half"):
        brief.append("答案缩过半")
    if signals.get("short_answer_no_evidence"):
        brief.append("短答无出处")
    return "、".join(brief) or "形状未变"


#: 翻分归类的中文面：本单要的「答得不同」还是「没答／哨兵／批准失败」就在这一格。
CLASS_SHORT = {
    "answered_differently": "答得不同",
    "no_answer": "没答",
    "sentinel": "哨兵顶回",
    "approval_failed": "批准失败",
    "not_answered": "未答完（分母口径）",
    "same_text": "答案没变·锚词变了",
    "category_moved": "同一枚题类目挪了",
}

VERDICT_SHORT = {
    VERDICT_REGRESSION: "超底＝退化",
    VERDICT_WITHIN_FLOOR: "底内",
    VERDICT_NO_DROP: "无恶化",
    VERDICT_INSUFFICIENT: "样本不足·不判",
    VERDICT_NO_FLOOR: "底没量出来·不判",
    VERDICT_FLOOR_INPUT: "此对子即底",
    VERDICT_NOT_CROSS_GEN: "非代次步·不判",
    VERDICT_GEN_UNKNOWN: "代次不可证",
}


def render_table(result: dict) -> str:
    windows = result["windows"]
    lines = ["[r634] 同类目跨窗 delta（口径＝在册尺 app/quality/eval.py 现算，并逐格与落盘报告对账）",
             "题集：" + result["fixture"]["path"] + " sha256=" + result["fixture"]["sha256"][:16]
             + " 行数=" + str(result["fixture"]["rows"]),
             ""]
    lines.append("一、窗与代次（指纹现读；代次不可证的窗只出现在这张表）")
    rows = [["窗", "started_at", "revision", "index_backend", "fixture_sha", "transport", "shard",
             "对账", "总correctness", "evidence", "ucr", "p95"]]
    for win in windows:
        finger = dict(zip(FINGERPRINT_KEYS, win["fingerprint"])) if win.get("fingerprint") else {}
        glob = win.get("global") or {}
        rows.append([
            win["label"], (win.get("started_at") or (order_value(win) + "（件 mtime，非开窗时刻）")),
            str(finger.get("revision") or "不可证")[:7],
            json.dumps(finger.get("index_backend"), ensure_ascii=False) if "index_backend" in finger else "不可证",
            str(finger.get("fixture_sha256") or "-")[:8],
            str(finger.get("transport") or "-").split(":")[0],
            str(finger.get("shard_size", "-")),
            (win["reconcile"] or {}).get("status", "-"),
            _format_value("correctness", glob.get("answer_correctness")),
            _format_value("evidence_coverage", glob.get("evidence_coverage")),
            _format_value("unsupported_claim_rate", glob.get("unsupported_claim_rate")),
            _format_value(LATENCY_METRIC, glob.get("p95_ms")),
        ])
    lines.append(_table(rows))
    lines.append("")
    for gap in [win for win in windows if not win["measured"]]:
        lines.append("  代次不可证：" + gap["label"] + " —— " + str(gap.get("measure_gap", "")))
    lines.append("")

    lines.append("二、逐类目读数（列＝窗；类目题数后的括号＝一枚题的粒度）")
    categories = []
    for win in windows:
        for category in win["categories"]:
            if category not in categories:
                categories.append(category)
    for metric in METRICS:
        lines.append("  指标 " + metric)
        table = [["类目", "题数"] + [win["label"] for win in windows]]
        for category in categories:
            totals = [win["categories"].get(category, {}).get("total") for win in windows]
            table.append([category, str(max((value or 0) for value in totals))]
                         + [_format_value(metric, win["categories"].get(category, {}).get(metric))
                            if win["categories"].get(category) else "缺类" for win in windows])
        lines.append("    " + _table(table).replace("\n", "\n    "))
        lines.append("")

    lines.append("三、对子判定（基线 -> 对照；底＝同码复跑量出来的逐类摆动）")
    for pair in result["pairs"]:
        lines.append("  " + pair["baseline"] + " -> " + pair["compare"] + "［" + pair["class"] + "："
                     + PAIR_LABELS[pair["class"]] + "］")
        if pair["note"]:
            lines.append("    " + pair["note"])
        if not pair.get("cells"):
            lines.append("    无可比读数（件不齐）")
            continue
        table = [["类目(题数)", "指标", "基线", "对照", "差值", "恶化量(负=改善)", "底(同码摆动)", "判定"]]
        for category, per_metric in pair["cells"].items():
            for metric in METRICS:
                entry = per_metric[metric]
                if entry.get("verdict") == VERDICT_GEN_UNKNOWN and metric != METRICS[0]:
                    continue
                table.append([
                    category + "(" + str(entry["total_b"] if entry["total_b"] is not None else "?") + ")",
                    metric,
                    _format_value(metric, entry["baseline"]), _format_value(metric, entry["compare"]),
                    _delta_of(metric, entry["delta"]), _format_value(metric, entry["worsening"]),
                    "—（此对子即底）" if entry.get("verdict") == VERDICT_FLOOR_INPUT
                    else _format_value(metric, entry.get("floor")),
                    VERDICT_SHORT.get(entry.get("verdict"), entry.get("verdict", "未判"))])
        lines.append("    " + _table(table).replace("\n", "\n    "))
        names = sorted({item["id"] for item in pair.get("flips", [])})
        lines.append("    翻分题：" + ("、".join(names) or "零枚（两窗逐题同判）"))
        lines.append("")

    lines.append("四、翻分题逐枚点名（谁掉了锚词、是答得不同还是没答/哨兵/批准失败）")
    any_flip = False
    for pair in result["pairs"]:
        if not pair.get("flips"):
            continue
        any_flip = True
        lines.append("  " + pair["baseline"] + " -> " + pair["compare"])
        table = [["题号", "类目", "方向", "归类", "形状", "丢的锚词", "字数", "evidence_n", "tool_calls",
                  "kind", "引证变", "在册扣除(丙案)"]]
        for item in pair["flips"]:
            lost = [term for term in item.get("hits_baseline", []) if term not in item.get("hits_compare", [])] \
                if item["direction"] == "drop" else item.get("missed_compare", [])
            table.append([
                item["id"], item.get("category", "-"),
                "掉分" if item["direction"] == "drop" else ("收分" if item["direction"] == "gain" else item["direction"]),
                CLASS_SHORT.get(item["class"], item["class"]) + "（" + item["class"] + "）",
                signal_brief(item.get("signals") or {}),
                "、".join(lost) or "-",
                "%s->%s" % (item["answer_chars"]["baseline"], item["answer_chars"]["compare"]),
                "%s->%s" % (item["evidence_n"]["baseline"], item["evidence_n"]["compare"]),
                "%s->%s" % (item["tool_calls"]["baseline"], item["tool_calls"]["compare"]),
                "%s->%s" % (item["kind"]["baseline"], item["kind"]["compare"]),
                "是" if item.get("citations_changed") else "否",
                ("是" if (item["in_deducted_ids"]["baseline"] or item["in_deducted_ids"]["compare"]) else "否"),
            ])
        lines.append("    " + _table(table).replace("\n", "\n    "))
        for item in pair["flips"]:
            lines.append("      " + item["id"] + "：" + item["class_reason"])
    if not any_flip:
        lines.append("  零枚翻分（两窗逐题同判）")
    lines.append("")

    summary = result["summary"]
    lines.append("五、噪声底与退化是否分开算出来了")
    floor_block = summary["noise_floor"]
    lines.append("  底量出来了吗：" + ("是" if floor_block["measured"] else "否")
                 + "｜来路对子：" + json.dumps(floor_block["per_generation_pairs"], ensure_ascii=False))
    lines.append("  " + floor_block["note"])
    worst = []
    for generation, cells in floor_block["cells"].items():
        for category, per_metric in cells.items():
            for metric, cell in per_metric.items():
                if cell["value"]:
                    worst.append((cell["value"], category, metric, cell["pair"],
                                  cell.get("moved_ids") or cell.get("worsened_ids")))
    worst.sort(reverse=True)
    rates = [item for item in worst if item[2] != LATENCY_METRIC]
    spans = [item for item in worst if item[2] == LATENCY_METRIC]
    if rates or spans:
        lines.append("  同码两跑之间最大的几格摆动（这就是判退化要跨过的门槛；按量纲分两拨看）：")
        for value, category, metric, pair_label, row_ids in (rates[:8] + spans[:4]):
            lines.append("    " + category + " " + metric + " 摆动 " + _format_value(metric, value)
                         + "（" + pair_label + "；搬动的题：" + ("、".join(row_ids) or "未点名") + "）")
    else:
        lines.append("  同码两跑之间逐类摆动全为零（这本身是枚读数，不代表摆动不存在）")
    lines.append("  跨代次对子枚数：" + str(summary["cross_generation_pairs"])
                 + "｜可判格：" + str(summary["judged_cross_generation_cells"]))
    lines.append("  判定分布：" + json.dumps(summary["verdict_tally"], ensure_ascii=False))
    lines.append("  退化格：" + ("零格" if not summary["regressions"]
                                else json.dumps(summary["regressions"], ensure_ascii=False)))
    lines.append("")
    lines.append("六、退出码")
    lines.append("  rc=" + str(summary["exit_code"]) + " —— " + summary["exit_meaning"])
    lines.append("  为什么是这个码：" + summary["why"])
    lines.append("  🔴 本件不交结论：A④ 达标与否归业主与总控判；上面每一档都只说量到了什么、量不到什么。")
    return "\n".join(lines)

# ---------------------------------------------------------------- 装配与入口

def build_result(args) -> dict:
    fixture_path = Path(args.fixture).expanduser()
    if not fixture_path.is_file():
        raise UnreadableError("取不到题集（尺子读的件之一）：" + str(fixture_path))
    fixture_rows = load_fixture_rows(fixture_path)
    fixture_sha = fixture_sha256(fixture_path)
    windows = resolve_windows(args)
    for win in windows:
        measure_window(win, fixture_rows, fixture_sha)
    ordered = sorted(windows, key=order_value)
    pairs = []
    for index, baseline in enumerate(ordered):
        for compare in ordered[index + 1:]:
            pairs.append(make_pair(baseline, compare))
    floors = build_floors(pairs)
    for pair in pairs:
        judge_pair(pair, floors, args.min_category_total)
        attribute_flips(pair)
    return {
        "generated_at": _now_iso(),
        "fixture": {"path": str(fixture_path), "sha256": fixture_sha, "rows": len(fixture_rows)},
        "windows": ordered,
        "pairs": pairs,
        "summary": summarize(ordered, pairs, floors, args.min_category_total),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="R634：同类目跨窗 delta，噪声底与退化分开算（只读数，不改数，不判 A 门④）")
    parser.add_argument("--window", action="append", default=[],
                        help="窗名（在 --dir 层里按在册命名收件），可重复")
    parser.add_argument("--report", action="append", default=[],
                        help="只给落盘报告一件：代次不可证，只进分代列表，不进比较表")
    parser.add_argument("--dir", action="append", default=[],
                        help="件所在的层，可重复；缺省＝%%TEMP%%\\evalrun（docs/testing 是另一层，要显式指）")
    parser.add_argument("--fixture", default=str(REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"),
                        help="题集（锚词与类目的真源，只读）")
    parser.add_argument("--min-category-total", type=int, default=MIN_CATEGORY_TOTAL_DEFAULT,
                        help="类目样本闸：两窗里最小那一窗不足这个枚数就不许判（含不许判绿）")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--out", default="", help="产物落盘路径（指进仓内直接拒）")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out_path = None
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        if _is_within(out_path, REPO_ROOT):
            sys.stderr.write("[r634] 取不到：--out 指进仓内（" + str(REPO_ROOT) + "）⇒ 本单产物只许落仓外\n")
            return EXIT_UNREADABLE
    try:
        result = build_result(args)
    except ReconcileError as error:
        sys.stderr.write("[r634] 取不到可信读数（与落盘报告对账破，rc=" + str(EXIT_UNREADABLE) + "）："
                         + str(error) + "\n")
        return EXIT_UNREADABLE
    except UnreadableError as error:
        sys.stderr.write("[r634] 取不到件（rc=" + str(EXIT_UNREADABLE) + "）：" + str(error) + "\n")
        return EXIT_UNREADABLE
    except (r580.RefuseError, FileNotFoundError, OSError, ValueError, RuntimeError) as error:
        sys.stderr.write("[r634] 取不到件（读不出或断账，rc=" + str(EXIT_UNREADABLE) + "）："
                         + type(error).__name__ + "：" + str(error) + "\n")
        return EXIT_UNREADABLE
    payload = build_payload(result)
    text = (json.dumps(payload, ensure_ascii=False, indent=2) if args.format == "json"
            else render_table(result))
    code = payload["exit_code"]
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print("[r634] 产物落盘（仓外）：" + str(out_path))
        print("[r634] rc=" + str(code) + "——" + payload["exit_meaning"] + "｜" + payload["why"])
    else:
        print(text)
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
