import json
import math
import statistics
from pathlib import Path

#: R123 甲案（跟进单 §57 三选一里业主 09-20 裁定的那一案）：采集器把「批准前那一帧」和
#: 「批准结果」写进侧车（scripts/eval_transport_ask_v2.py 的 _record），评分端据此同时给出
#: 两把尺。下面的键名与采集器逐字对得上，不在这另起一套口径。
APPROVAL_KIND = "approved_ok"
APPROVAL_FAILED_KIND = "approval_failed"
HITL_PRE_KIND = "hitl"


def evaluate_golden_set(path: str | Path, answer_fn) -> dict:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    total = len(rows)
    exact = 0
    relevancy = 0
    for row in rows:
        pred = str(answer_fn(row["question"]))
        gold = str(row["answer"])
        if pred.strip() == gold.strip():
            exact += 1
        if pred and gold and (gold[:4] in pred or pred[:4] in gold or pred.strip() == gold.strip()):
            relevancy += 1
    return {
        "total": total,
        "exact_match": round(exact / total, 2) if total else 0.0,
        "answer_relevancy": round(relevancy / total, 2) if total else 0.0,
    }


def _confidence_label(confidence: float | int | None) -> str:
    value = float(confidence or 0)
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def evaluate_provenance(answer: dict) -> dict:
    evidence = answer.get("evidence") or []
    claims = answer.get("claims") or []
    supported = [claim for claim in claims if claim.get("supported") is True]
    unsupported = [
        str(claim.get("text", "")).strip()
        for claim in claims
        if claim.get("supported") is False and str(claim.get("text", "")).strip()
    ]
    coverage = len(supported) / len(claims) if claims else (1.0 if evidence else 0.0)
    return {
        "has_evidence": bool(evidence),
        "evidence_coverage": round(coverage, 4),
        "confidence_label": answer.get("confidence_label")
        or _confidence_label(answer.get("confidence")),
        "unsupported_claims": unsupported,
    }


def _answer_text(result) -> str:
    if isinstance(result, dict):
        return str(result.get("answer", ""))
    return str(result)


def _is_correct(row: dict, result) -> bool:
    text = _answer_text(result)
    expected = [str(item) for item in row.get("must_contain", [])]
    if expected:
        return all(item in text for item in expected)
    answer = str(row.get("answer", "")).strip()
    return bool(answer) and answer in text


def load_approval_ledger(path: str | Path) -> dict[str, dict]:
    """读采集侧车（append-only 的逐题账），按题号留最后一行。

    显式指定了账本却找不到文件 ⇒ 硬失败：把「没有账本」当成「批准失败 0 题」是静默撒谎。
    半行（跑分中途被 kill 留下的）跳过：它不是一条记录，但也不该炸掉一份能出的报告。
    """
    ledger_path = Path(path)
    if not ledger_path.exists():
        raise FileNotFoundError(
            f"批准账本不存在：{ledger_path}（显式指定过它，就不能当没看见）")
    rows: dict[str, dict] = {}
    for line in ledger_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and str(row.get("id", "")):
            rows[str(row["id"])] = row
    return rows


def summarize_approval_ledger(fixture_rows: list[dict], ledger: dict[str, dict]) -> dict:
    """判据 4 那一行的数据源：本轮经审批取得终答 N 题 / 批准失败 M 题。"""
    fixture_ids = {str(row.get("id", "")) for row in fixture_rows}
    hitl_pre = [row for row in ledger.values() if row.get("pre_kind") == HITL_PRE_KIND]
    approved = [row for row in ledger.values() if row.get("kind") == APPROVAL_KIND]
    failed = [row for row in ledger.values() if row.get("kind") == APPROVAL_FAILED_KIND]
    return {
        "hitl_pre_n": len(hitl_pre),
        "hitl_pre_ids": sorted(str(row.get("id")) for row in hitl_pre),
        "approved_final_n": len(approved),
        "approved_final_ids": sorted(str(row.get("id")) for row in approved),
        "approval_failed_n": len(failed),
        "approval_failed_ids": sorted(str(row.get("id")) for row in failed),
        "ledger_rows": len(ledger),
        "ledger_rows_not_in_fixture": sorted(set(ledger) - fixture_ids),
    }


def pre_approval_ruler(results: list[dict], ledger: dict[str, dict]) -> dict:
    """旧口径重算：分母仍是全部 105 题，但卡在闸上的题拿「批准前那一帧」去计分。

    run2..run5 的 answers 文件里，那 18 枚存的就是「等待确认」park 文本 ⇒ 这个数就是
    它们当时的 correctness（判据 2 要的两个数之一，另一枚是主报告本身）。证据侧只用
    「有没有出处」这个布尔，因为采集器从不交 claims，per 行 evidence_coverage 与它同值。
    """
    total = len(results)
    correct = 0
    evidence_ok = 0
    substituted = 0
    for item in results:
        row = item["row"]
        ledger_row = ledger.get(str(row.get("id", ""))) or {}
        if "pre_answer" in ledger_row:
            substituted += 1
            answer_text = str(ledger_row.get("pre_answer") or "")
            has_evidence = int(ledger_row.get("pre_evidence_n") or 0) > 0
        else:
            answer_text = _answer_text(item["result"])
            has_evidence = item["provenance"]["has_evidence"]
        if _is_correct(row, {"answer": answer_text}):
            correct += 1
        if has_evidence or not row.get("requires_evidence", False):
            evidence_ok += 1
    return {
        "total": total,
        "answer_correctness": round(correct / total, 4) if total else 0.0,
        "evidence_coverage": round(evidence_ok / total, 4) if total else 0.0,
        "substituted_rows": substituted,
        "basis": "卡闸的题按侧车 pre_answer / pre_evidence_n 计分＝run2..run5 口径；分母不变",
    }


def format_approval_line(report: dict) -> str:
    """判据 4 要「多印的那一行」。没有账本时返回空串：印一行假的「批准失败 0」比不印更坏。"""
    summary = report.get("approval_ledger")
    if not summary:
        return ""
    ruler = report.get("pre_approval_ruler") or {}
    return (
        f"approval: 本轮经审批取得终答的题数 {summary['approved_final_n']} / 批准失败 "
        f"{summary['approval_failed_n']}"
        f"（批准前卡在闸上 {summary['hitl_pre_n']} 题，账本 {summary['ledger_rows']} 行）"
        f" ｜ correctness 甲案 {report['answer_correctness']:.4f}"
        f" / 旧口径 {ruler.get('answer_correctness', 0.0):.4f}"
        f" ｜ evidence 甲案 {report['evidence_coverage']:.4f}"
        f" / 旧口径 {ruler.get('evidence_coverage', 0.0):.4f}"
    )


# ===== R438：correctness 的两把尺（R401 丙案扣除接线）================================
#
# 跟进单 §115.8 的 R401 判了丙案：那些「锚词在语料里查无出处」的题**保留题面、锚词不动**，
# 只从 correctness 的分母里**点名**出去。裁定当时只落了账与可跑子集夹具，判分器没接线
# （tests/test_r401_unscorable_rows_are_named_not_dropped.py:14-15 自己写明「未接线」）。
# 本段把那根线接上，两把尺同时出，一把都不许藏：
#   尺一 answer_correctness                  分母 = 全部题数，算法与语义一字未动 ⇒ run2..run9 可比
#   尺二 answer_correctness_scorable_subset  分母 = 全部题数 − 丙案点名扣除数
# 🔴 进分母的枚数只能派生，不能手抄：唯一读点是 row_disposition()，读的是题源里 R401 落下的
#    r401.disposition；派生不到锚点就当场 ScorabilityDerivationError。静默退回全题分母＝假绿。
# 🔴 扣除必须逐枚点名：id + 为什么今天不可考 + 缺的那个词 + 去向，文本原样从 R401 的记录里读，
#    本段不另写一套理由（另写一套＝第二本账）。

#: 题源上 R401 处置标记的字段名，与 scripts/r401_anchor_provenance.py:MARKER_FIELD 同一把尺。
SCORABILITY_MARKER_FIELD = "r401"
DISPOSITION_KEY = "disposition"
#: 丙＝题目保留、锚词不动、只从 correctness 分母点名扣除；甲/乙已在 R401 单内处置完，照旧计分。
UNSCORABLE_DISPOSITION = "丙"
#: 认得的处置值全集，与 scripts/r401_anchor_provenance.py:DISPOSITIONS 同一把尺。
KNOWN_DISPOSITIONS = ("甲", "乙", "丙")
#: 第二把尺在报告里的键名：唯一构造点是 evaluate_evaluation_set，唯一读者是判分器与观测出口
#: （app/api/v1/observability.py 与 scripts/run_quality_evaluation.py 都从这里取名字，不抄清单）。
SUBSET_RULER_KEY = "answer_correctness_scorable_subset"
#: 装着两把尺分母账（三数 + 点名清单）那一格的键名，同上。
SCORABLE_SUBSET_REPORT_KEY = "scorable_subset"


class ScorabilityDerivationError(RuntimeError):
    """丙案扣除的锚点读不出来：宁可不出这份报告，也不许静默按全部题数出分母。"""


def _plain_id(row: dict) -> str:
    """题号的宽读法：没有就回空串，要不要因此报错由点名那一腿决定（分子分母闸不猜题号）。"""
    return str(row.get("id", "") or "").strip()


def row_disposition(row: dict) -> str | None:
    """现读这一枚题在题源里带的 R401 处置（甲/乙/丙）；没带标记就是 None。

    🔴 全仓唯一读点：扣除清单、进分母数、可判子集的分子全部从这一格长出来。摘掉它，两把尺
    就塌回一把——tests/test_r438_* 的刀a 钉的正是这一格。
    带着标记却读不出一个认得的处置值 ⇒ 当场报错：把「读不到」当成「不用扣」就是假绿。
    """
    marker = row.get(SCORABILITY_MARKER_FIELD)
    if marker is None:
        return None
    if not isinstance(marker, dict):
        raise ScorabilityDerivationError(
            f"{_plain_id(row)} 行的 {SCORABILITY_MARKER_FIELD} 标记不是对象，读不出处置：{marker!r}")
    disposition = marker.get(DISPOSITION_KEY)
    if disposition is None:
        raise ScorabilityDerivationError(
            f"{_plain_id(row)} 行带着 {SCORABILITY_MARKER_FIELD} 标记却没有 {DISPOSITION_KEY}"
            " ⇒ 丙案账断在题源上，不许按全部题数出分母")
    disposition = str(disposition).strip()
    if disposition not in KNOWN_DISPOSITIONS:
        raise ScorabilityDerivationError(
            f"{_plain_id(row)} 行的处置值 {disposition!r} 不在 {'/'.join(KNOWN_DISPOSITIONS)} 里"
            " ⇒ 分母派生不到锚点")
    return disposition


def _named_id(row: dict) -> str:
    row_id = _plain_id(row)
    if not row_id:
        raise ScorabilityDerivationError("有一枚判丙的题没有题号 ⇒ 扣除没法点名，这份报告不出")
    return row_id


def unscorable_row_ids(rows: list[dict]) -> list[str]:
    """计数腿：今天判丙的题号，逐枚现读，不抄名单。"""
    return [_named_id(row) for row in rows if row_disposition(row) == UNSCORABLE_DISPOSITION]


def unscorable_records(rows: list[dict]) -> list[dict]:
    """点名腿：逐枚被扣题的 id / 为什么今天不可考 / 缺的词 / 去向，文本从 R401 的记录里原样读。

    🔴 这里一行都不许「另写一套理由」：reason / missing_term / pool 就是
    scripts/r401_anchor_provenance.py 的 --apply 落进题源的那份账，读它就是读那本账。
    丙案的铁规是题保留、锚词不动 ⇒ 那个查无出处的词必须还挂在 must_contain 上；谁把锚词置空
    或把理由抹平，这里当场报错（R401 判据②明令禁的那两条捷径）。
    """
    named_rows = []
    for row in rows:
        if row_disposition(row) != UNSCORABLE_DISPOSITION:
            continue
        marker = row[SCORABILITY_MARKER_FIELD]
        row_id = _named_id(row)
        anchors = [str(term) for term in (row.get("must_contain") or [])]
        reason = str(marker.get("reason") or "").strip()
        destination = str(marker.get("pool") or "").strip()
        missing_term = str(marker.get("missing_term") or "").strip()
        if not reason or not destination:
            raise ScorabilityDerivationError(
                f"{row_id} 判丙却没被点名（reason/pool 缺一枚）"
                " ⇒ 报告里会出现「分母扣了却没人知道扣了谁」")
        if not missing_term or missing_term not in anchors:
            raise ScorabilityDerivationError(
                f"{row_id} 判丙但锚词被动过了：「{missing_term}」不在 must_contain {anchors} 里"
                " ⇒ 丙案不换锚词，置空锚词换分母是 R401 判据②禁的那条捷径")
        named_rows.append({
            "id": row_id,
            "disposition": UNSCORABLE_DISPOSITION,
            "missing_term": missing_term,
            "reason": reason,
            "destination": destination,
            "question": str(row.get("question") or ""),
        })
    return named_rows


def derive_scorability(rows: list[dict]) -> dict:
    """两把尺的分母账：全部题数 / 点名扣除数 / 进分母数 + 逐枚点名，三个数全是现算。

    计数腿与点名腿各走一遍再互相对账：任何一枚丙案题只被计数没被点名（或反过来），三数算式
    就破 ⇒ 当场报错，不许出一份「扣了分母但点不出人」的报告。
    """
    deducted_ids = unscorable_row_ids(rows)
    named_rows = unscorable_records(rows)
    if sorted(record["id"] for record in named_rows) != sorted(deducted_ids):
        raise ScorabilityDerivationError(
            f"扣除账对不上：点名 {len(named_rows)} 枚 vs 丙案 {len(deducted_ids)} 枚"
            " ⇒ 有题被扣了分母却没被点名")
    total_rows = len(rows)
    deducted_n = len(deducted_ids)
    denominator_rows = total_rows - deducted_n
    if denominator_rows < 0 or denominator_rows != total_rows - deducted_n:
        raise ScorabilityDerivationError(
            f"进分母数 {denominator_rows} ≠ 全部 {total_rows} − 扣除 {deducted_n} ⇒ 三数算式破了")
    block = {
        "total_rows": total_rows,
        "deducted_n": deducted_n,
        "denominator_rows": denominator_rows,
        "deducted_ids": deducted_ids,
        "deducted_rows": named_rows,
        "rule": (
            "answer_correctness_scorable_subset 的分母 = 全部 {0} 题 − 丙案点名扣除 {1} 题 = {2}；"
            "answer_correctness / evidence_coverage / total 仍按全部 {0} 题（题没删、锚词没动）。"
            .format(total_rows, deducted_n, denominator_rows)
        ),
        "basis": (
            "处置值由 app.quality.eval.row_disposition() 现读题源里的 r401.disposition，"
            "逐枚理由与去向原样取自同一份 R401 记录（scripts/r401_anchor_provenance.py 落的账），"
            "分母账里没有一枚手抄数字"
        ),
    }
    if not denominator_rows:
        block["note"] = (
            f"全部 {total_rows} 题都判丙 ⇒ 可判子集为空，这一把尺报 None 而不是 0.0"
            "（0.0 会被读成「一道题都没答对」，那是假话）")
    return block


def correctness_subset_ruler(results: list[dict], scorability: dict) -> dict:
    """可判子集那把尺：分子与分母从同一份点名清单里长出来，不许一只脚踩在全集上。

    两道同源闸：① 进分子的题数必须等于分母账上的枚数；② 分子不许大过分母
    （「分子按全部题数、分母按可判子集」这种越界读数比值会大于 1）。
    任何一道不通 ⇒ 当场报错，这份报告不出。
    """
    deducted_ids = {record["id"] for record in scorability["deducted_rows"]}
    scorable = [item for item in results if _plain_id(item["row"]) not in deducted_ids]
    if len(scorable) != scorability["denominator_rows"]:
        raise ScorabilityDerivationError(
            f"可判子集读出 {len(scorable)} 枚，分母账上是 {scorability['denominator_rows']} 枚"
            " ⇒ 分子分母不同源")
    correct_n = sum(bool(item["correct"]) for item in scorable)
    if correct_n > len(scorable):
        raise ScorabilityDerivationError(
            f"可判子集分子 {correct_n} 越出分母 {len(scorable)}"
            " ⇒ 有题没进分母却在算分，两把尺不同源")
    return {
        "correct_n": correct_n,
        SUBSET_RULER_KEY: round(correct_n / len(scorable), 4) if scorable else None,
    }


def scorability_metrics(report: dict, *, list_limit: int | None = None) -> dict:
    """把第二把尺与它的分母账读成「可进出口」的读数面：键名从报告那一格自己长出来。

    🔴 判据⑨：出口不许抄一份键名清单当第二本账（本仓为这病开了 R346/R351/R377/R396/R400 一整族）。
    规则只有一条 —— 逐格读 `scorable_subset`：
      * 数值格（三数与 correct_n）→ `scorable_subset_<该格键名>`；
      * 字符串清单（逐枚点名的题号）→ `scorable_subset_<该格键名>`，逐枚照发；条数超过调用方给的
        上限就当场红——截断出口等于「少报了几枚还照旧报 ok」，正是判据⑨禁的静默少一格；
      * 对象清单（逐枚理由与去向）→ 不搬进出口，只与扣除数对账（长文本留在报告文件里）；
      * 尺本身 → 用 SUBSET_RULER_KEY 原名：判分器怎么写，出口就怎么读。
    🔴 派生不到锚点当场红，不许静默少一格：尺与账只有一半、三数算式破、点名清单与扣除数
       对不上、分母为零却报了数、比值大于 1、格内格外的尺不是同一个数 —— 一律报错。
    旧形状（本单接线之前入库的那批件根本没有第二把尺）返回空面：那是「那一把尺
    今天不存在」，不是「少了一格」，不许把它当分叉炸掉 —— 已入库的报告还得照样看得见。
    """
    block = report.get(SCORABLE_SUBSET_REPORT_KEY)
    has_block = isinstance(block, dict)
    has_ruler = SUBSET_RULER_KEY in report
    if has_ruler != has_block:
        raise ScorabilityDerivationError(
            "第二把尺与它的分母账只有一半（尺{0}／账{1}）⇒ 形状分叉的报告不许进出口".format(
                "在" if has_ruler else "不在", "在" if has_block else "不在"))
    if not has_block:
        return {}

    def _count(name: str) -> int:
        value = block.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ScorabilityDerivationError(f"分母账上「{name}」读不出整数：{value!r}")
        return value

    total_rows = _count("total_rows")
    deducted_n = _count("deducted_n")
    denominator_rows = _count("denominator_rows")
    if denominator_rows < 0 or denominator_rows != total_rows - deducted_n:
        raise ScorabilityDerivationError(
            f"出口重算三数：{total_rows} − {deducted_n} ≠ {denominator_rows} ⇒ 账上的算式是破的")

    roster = block.get("deducted_ids")
    named = block.get("deducted_rows")
    if deducted_n and not isinstance(roster, list):
        raise ScorabilityDerivationError(f"扣了 {deducted_n} 枚却点不出名单 ⇒ 账在尺不在")
    if isinstance(roster, list) and len(roster) != deducted_n:
        raise ScorabilityDerivationError(
            f"点名清单 {len(roster)} 枚 ≠ 扣除数 {deducted_n} ⇒ 有题被扣了分母却没被点名")
    if isinstance(named, list) and len(named) != deducted_n:
        raise ScorabilityDerivationError(
            f"逐枚点名记录 {len(named)} 枚 ≠ 扣除数 {deducted_n} ⇒ 清单与账不同源")

    metrics: dict = {}
    ruler = report.get(SUBSET_RULER_KEY)
    if ruler is not None:
        try:
            number = float(ruler)
        except (TypeError, ValueError) as error:
            raise ScorabilityDerivationError(f"第二把尺读不成数：{ruler!r}") from error
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ScorabilityDerivationError(
                f"第二把尺 {number} 越出 [0, 1] ⇒ 分子踩在了全部题数上")
        metrics[SUBSET_RULER_KEY] = number
    elif denominator_rows:
        raise ScorabilityDerivationError(
            f"分母是 {denominator_rows} 枚却没有读数 ⇒ 静默少一格，这份出口不认")
    if SUBSET_RULER_KEY in block and block[SUBSET_RULER_KEY] != ruler:
        raise ScorabilityDerivationError(
            f"账里那把尺（{block[SUBSET_RULER_KEY]!r}）与报告抬头那把（{ruler!r}）不是同一个数")

    prefix = f"{SCORABLE_SUBSET_REPORT_KEY}_"
    for key, value in block.items():
        if key == SUBSET_RULER_KEY or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value):
            metrics[f"{prefix}{key}"] = value
        elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            if list_limit is not None and len(value) > list_limit:
                raise ScorabilityDerivationError(
                    f"点名清单 {len(value)} 枚超出出口条数上限 {list_limit}"
                    " ⇒ 截断就是少报几枚还报 ok ⇒ 本出口不认，宁可落 unreadable")
            metrics[f"{prefix}{key}"] = list(value)
    return metrics


def format_correctness_rulers(report: dict) -> str:
    """把两把尺读成一行（CLI 用）：与出口共用 `scorability_metrics`，谁也不许拼第二遍。

    🔴 这一行只许**追加**：历史那四格（evaluated / correctness / evidence / p95_ms）的写法与顺序
       不动 —— runbook §7-C 认的是「stdout 以 evaluated= 开头」与那串既有 token。第二把尺挂行尾。
       派生不到就当场红：只印一把尺交活，正是判据①禁的那个形状。
    """
    metrics = scorability_metrics(report)
    if not metrics:
        raise ScorabilityDerivationError(
            "这份报告没有可判子集那一格 ⇒ 第二把尺无从可报，只许两把尺同报")
    ruler = metrics.get(SUBSET_RULER_KEY)
    ruler_text = f"{SUBSET_RULER_KEY}=" + ("n/a" if ruler is None else f"{ruler:.4f}")
    prefix = f"{SCORABLE_SUBSET_REPORT_KEY}_"
    ledger = " ".join(
        f"{key[len(prefix):]}={value}"
        for key, value in metrics.items()
        if key.startswith(prefix) and not isinstance(value, list))
    return f"{ruler_text} {SCORABLE_SUBSET_REPORT_KEY}[{ledger}]"


# ===== R205a：时延记账（跟进单 §93.9）=============================================
#
# run6 正式报告里 latency_ms.average = 351 121 ms 比逐题最大值（诚实的 272.2 s）还大。
# 起因在采集器：载荷不自报 latency_ms 时，它拿自己 perf_counter 的**整调用跨度**冒充
# 「这一发的时延」（scripts/collect_evaluation_answers.py 的 _latency_ms），而采集适配器
# 是故意不自报的。整调用跨度里含被打回的重试、重试 sleep，以及 09-23 23:34 → 09-24 07:40
# 那段 8 h 6 min 整机待机 —— 它不是「每发尝试自己的真实跨度」。诚实的那一发在帧账 sidecar
# 的 wall_ms 里（适配器每次尝试开头重取时间、重试不记账），而这份账本评分时本来就要读
# （R123 甲案），所以时延与它同源核对，不再各说各话。
#
# 规则（写在数上，不写在题号上）：
#   ① 有帧账可对：实测值不超过帧账跨度的容忍带 ⇒ 两者本就是同一发，按实测进聚合；
#      越过容忍带 ⇒ 这一发解释不了，改用帧账的逐发跨度（repaired_to_frame_ledger）；
#   ② 没有帧账可对：实测值仍在一发量级之内才允许进聚合；否则该题排除并逐题列出；
#   ③ 这一发压根没有可用实测（载荷没自报，或被采集器按量级拒记 ⇒ answers 行那格记 null）：
#      帧账 wall_ms 在一发量级之内就直接顶上（recovered_from_frame_ledger）；两边都拿不出
#      诚实跨度，才落进 count < total 那个既有出口。读不成毫秒的读数同样不许静默消失。
#   ④ 聚合出的格子必须自洽：average ≤ max，且 average / max 都不许越过帧账给出的诚实
#      上界。任何一条不成立 ⇒ 当场 LatencyAccountingError，这份报告不出。
# 被 ①②③ 处置过的题逐条列在 latency_ms.suspect：谁、原读数多少、帧账多少、最终用了谁。
# 🔴 两把尺各管一件事，不许混用：量级上限问「这还像不像一发尝试」（run6 那发 8 h 待机），
#    帧账容忍带问「这是不是这一发的跨度」（run6 另外三枚 6.5~523 倍的重试虚高）。
#    源头那道守卫（采集器 _latency_ms）只管前者，所以重试虚高那一类仍要靠这里的帧账对账。

#: 实测值与帧账 wall_ms 的容忍带：倍差 1.25 + 固定 2 s，两个数量级的余量，不是题号白名单。
#: 下界依据（前任按 run6 逐题实录归纳，本班**没能复核**：仓内与 %TEMP% 都没有 run6 的 answers/
#: sidecar 原件，只有 §93.0 的汇总数）——无重试题两数差 <0.1%（最大约 4 ms，是采集器在适配器之外
#: 多花的登录/节拍/记账），三枚越界题差 6.5~523 倍。本班能证的那一半在
#: tests/test_r205a_latency_ledger.py：带上沿逐字是 limit，越出去才换帧账。
LATENCY_LEDGER_RATIO_TOLERANCE = 1.25
LATENCY_LEDGER_SLACK_MS = 2000.0

#: 一发尝试的量级上限 = 模型单发请求超时（全仓唯一读点在 app/common/model_budget.py）× 本倍数：采集器整调用最多含 EVAL_ATTEMPTS
#: （默认 3）发模型请求 + 两枚 EVAL_RETRY_SLEEP（默认 20 s）+ 排队轮询观测窗，再往上一个
#: 数量级就不可能是「一发的真实跨度」。上限走唯一读者 latency_envelope_ms()，这里不另存
#: 那个超时常量（app/common/model_budget.py 是它全仓唯一的读点）。
LATENCY_ENVELOPE_TIMEOUT_MULTIPLES = 8.0

#: 同一个数四舍五入两次之内的差，不算「平均值大于逐题最大值」。
LATENCY_ROUNDING_TOLERANCE_MS = 0.01

LATENCY_ACTION_KEPT = "kept"
LATENCY_ACTION_REPAIRED = "repaired_to_frame_ledger"
#: 没有可用实测、但帧账那一发的跨度可用 ⇒ 用帧账顶上（逐题列出，不静默补数）。
LATENCY_ACTION_RECOVERED = "recovered_from_frame_ledger"
LATENCY_ACTION_EXCLUDED = "excluded_without_honest_span"
LATENCY_ACTION_ABSENT = "not_measured"

LATENCY_BASIS = (
    "latency_ms 只由每发尝试自己的真实跨度构成：与帧账 wall_ms 相符者按实测进聚合，"
    "越界者按帧账逐发跨度替换，无实测而帧账可用者按帧账顶上，"
    "拿不出诚实跨度的题排除并逐题列在 suspect"
)


class LatencyAccountingError(RuntimeError):
    """报告的 latency_ms 出现了「平均值大于逐题最大值」这类不可能形状。"""


def latency_envelope_ms() -> float:
    """一发尝试的量级上限：读 app.common.model_budget 里那个唯一的超时上限。"""
    from app.common.model_budget import request_timeout_ceiling_seconds

    return request_timeout_ceiling_seconds() * 1000.0 * LATENCY_ENVELOPE_TIMEOUT_MULTIPLES


def _span_ms(value) -> float | None:
    """把一格时延读数读成非负毫秒；读不出来就是 None —— 不猜、不补、不当 0 用。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _latency_verdict(action, used_ms, *, corroborated, row) -> dict:
    """分类结论的统一形状：row 为 None 表示这一题不需要被逐题列出。"""
    return {"action": action, "used_ms": used_ms, "corroborated": corroborated, "row": row}


def classify_latency_span(row_id, reported_ms, frame_ledger_ms, *, envelope_ms: float) -> dict:
    """这一发的实测读数能不能算「每发尝试自己的真实跨度」，以及最终用哪个数。

    返回 {"action", "used_ms", "corroborated", "row"}：row 只在该题需要被逐题列出时非空。
    两把尺各问一件事：envelope_ms 问「这还像不像一发尝试」，帧账容忍带问「这是不是这一发」。
    """
    reported = _span_ms(reported_ms)
    ledger = _span_ms(frame_ledger_ms)
    # 帧账自己也得先过量级这一关：越出一发量级的 wall_ms 不是诚实跨度，不能拿去替换别人。
    ledger_span = ledger if ledger is not None and ledger <= envelope_ms else None

    if reported is not None:
        row = {"id": str(row_id), "reported_ms": reported, "frame_ledger_ms": ledger}
        if ledger is None:
            # 规则②：没有帧账可对，只剩量级这一把尺。
            if reported <= envelope_ms:
                return _latency_verdict(LATENCY_ACTION_KEPT, reported,
                                        corroborated=False, row=None)
            row["reason"] = (
                f"实测 {reported} ms 越出一发量级上限 {envelope_ms} ms，且这一题没有帧账可对"
                " ⇒ 没有可信的逐发跨度可替换")
            return _latency_verdict(LATENCY_ACTION_EXCLUDED, None,
                                    corroborated=False, row=row)
        # 规则①：有帧账可对，两数同带就说明它们本就是同一发。
        limit = round(ledger * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS, 2)
        if reported <= limit:
            return _latency_verdict(LATENCY_ACTION_KEPT, reported,
                                    corroborated=True, row=None)
        if ledger_span is not None:
            row["reason"] = (
                f"实测 {reported} ms 超过帧账逐发跨度 {ledger} ms 的容忍带 {limit} ms"
                "（被打回的重试或被冻的整机待机被算了进来）⇒ 改用帧账那一发的跨度")
            return _latency_verdict(LATENCY_ACTION_REPAIRED, ledger_span,
                                    corroborated=True, row=row)
        row["reason"] = (
            f"实测 {reported} ms 越出容忍带 {limit} ms，帧账 {ledger} ms 自己也越出一发量级上限"
            f" {envelope_ms} ms ⇒ 两边都不可信")
        return _latency_verdict(LATENCY_ACTION_EXCLUDED, None,
                                corroborated=False, row=row)

    # 规则③：这一发没有可用实测——载荷没自报、被采集器按量级拒记（latency_ms 记 null），
    # 或者字面上读不成毫秒。帧账能用就直接顶上并逐题列出，两条都不通才不计入聚合。
    if ledger_span is not None:
        reason = ("这一发没有可用的实测读数（载荷未自报或被采集器拒记 ⇒ 看该题 answers 行的"
                  " latency_suspect）⇒ 用帧账 wall_ms 那一发的真实跨度")
        if reported_ms is not None:
            reason = f"实测读数 {reported_ms!r} 读不成毫秒 ⇒ 改用帧账 wall_ms 那一发的真实跨度"
        return _latency_verdict(
            LATENCY_ACTION_RECOVERED, ledger_span, corroborated=True,
            row={"id": str(row_id), "reported_ms": None, "frame_ledger_ms": ledger,
                 "reason": reason})
    if reported_ms is None and ledger is None:
        # 没测到不等于测得假：count 小于 total 就是这一格的既有出口，不另造形状。
        return _latency_verdict(LATENCY_ACTION_ABSENT, None, corroborated=False, row=None)
    row = {"id": str(row_id), "reported_ms": reported, "frame_ledger_ms": ledger}
    row["reason"] = (
        "这一发既没有可用的实测读数"
        + ("（未自报）" if reported_ms is None else f"（实测读数 {reported_ms!r} 读不成毫秒）")
        + "，帧账那一发也不可用"
        + (f"（wall_ms {ledger} ms 越出一发量级上限 {envelope_ms} ms）"
           if ledger is not None else "（帧账没有这一题）")
        + " ⇒ 不计入聚合")
    return _latency_verdict(LATENCY_ACTION_EXCLUDED, None, corroborated=False, row=row)


def guard_latency_cell(cell: dict, *, honest_max_ms: float | None = None) -> None:
    """时延格子的自洽闸：不可能形状在这里炸，不许变成一份能看的报告。"""
    if not cell.get("count"):
        return
    average = cell["average"]
    highest = cell["max"]
    if average > highest + LATENCY_ROUNDING_TOLERANCE_MS:
        raise LatencyAccountingError(
            f"latency_ms 平均值 {average} 大于逐题最大值 {highest}"
            " ⇒ 聚合里混进了不同源的数（run6 那一格就是这么来的）")
    if honest_max_ms is None:
        return
    ceiling = honest_max_ms * LATENCY_LEDGER_RATIO_TOLERANCE + LATENCY_LEDGER_SLACK_MS
    if highest > ceiling or average > ceiling:
        raise LatencyAccountingError(
            f"latency_ms 越出帧账的诚实上界 {round(ceiling, 2)} ms（逐题帧账最大跨度 "
            f"{honest_max_ms} ms）：max={highest} average={average}"
            " ⇒ 平均值里仍有不是「一发尝试」的跨度")


def build_latency_cell(values, *, honest_max_ms: float | None = None) -> dict:
    """把「已经可信的逐发跨度」汇成报告那一格，并当场自证自洽。

    p95 的排名规则沿用既有那一把（与 app/common/performance.py::PerformanceStats 对齐，
    由 tests/test_r105_slo_contract.py 钉住），这里只补上逐题最大值 max 那一格。
    """
    latencies = sorted(item for item in (_span_ms(value) for value in values)
                       if item is not None)
    if not latencies:
        cell = {"count": 0, "average": 0, "p95": 0, "max": 0}
    else:
        rank = max(1, math.ceil(len(latencies) * 0.95))
        cell = {
            "count": len(latencies),
            "average": round(statistics.mean(latencies), 2),
            "p95": latencies[min(len(latencies) - 1, rank - 1)],
            "max": latencies[-1],
        }
    guard_latency_cell(cell, honest_max_ms=honest_max_ms)
    return cell


def aggregate_latency_ms(spans, *, envelope_ms: float | None = None) -> dict:
    """逐题「实测 + 帧账」两列读数 → 报告里那一格时延。

    spans 每项形如 {"id", "reported_ms", "frame_ledger_ms"}；被替换、被顶上、被排除的题按传入
    顺序逐条落进 cell["suspect"]，一条都不许默默消失。
    """
    ceiling_one = _span_ms(envelope_ms)
    if ceiling_one is None:
        ceiling_one = latency_envelope_ms()
    values: list[float] = []
    honest_spans: list[float] = []
    suspect: list[dict] = []
    corroborated = 0
    for span in spans:
        ledger = _span_ms(span.get("frame_ledger_ms"))
        verdict = classify_latency_span(span.get("id"), span.get("reported_ms"), ledger,
                                        envelope_ms=ceiling_one)
        if ledger is not None and ledger <= ceiling_one:
            # 诚实上界取全部可用的逐发帧账跨度，不以「这次有没有用上它」为条件。
            honest_spans.append(ledger)
        if verdict["row"] is not None:
            verdict["row"]["action"] = verdict["action"]
            verdict["row"]["used_ms"] = verdict["used_ms"]
            suspect.append(verdict["row"])
        if verdict["used_ms"] is None:
            continue
        values.append(verdict["used_ms"])
        if verdict["corroborated"]:
            corroborated += 1
    cell = build_latency_cell(
        values, honest_max_ms=max(honest_spans) if honest_spans else None)
    cell["frame_ledger_rows"] = corroborated
    cell["one_attempt_envelope_ms"] = ceiling_one
    cell["suspect_n"] = len(suspect)
    cell["suspect"] = suspect
    cell["basis"] = LATENCY_BASIS
    return cell


def evaluate_evaluation_set(path: str | Path, answer_fn, *, approval_ledger: str | Path | None = None) -> dict:
    """给一套夹具与一个取答案的函数，产出报告；给了批准账本就在同一份报告里加两把尺。

    🔴 分母不因为甲案而变（判据 4）：`total` 与 `answer_correctness` 恒按全部题数算，
    卡闸的题现在拿真终答进分母，旧口径要的那个数在 `pre_approval_ruler` 里。

    R205a：`latency_ms` 那一格不再由「载荷里有什么就算什么」决定，改由
    `aggregate_latency_ms` 对着帧账逐发记账（跟进单 §93.9 ①）；账本读不出来就当场
    `LatencyAccountingError`，这份报告不出。

    R438：correctness 同时出两把尺（判据①）。`answer_correctness` 的分母与算法一字未动 ⇒
    历史报告可比；`answer_correctness_scorable_subset` 按可判子集出，分母由题源里的 R401
    处置标记现算（`derive_scorability`），逐枚被扣题在 `scorable_subset.deducted_rows` 里
    点名。派生不到锚点同样当场 `ScorabilityDerivationError`，这份报告不出。
    """
    rows = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    # 同一份侧车既是批准账本，也是「每发尝试自己的跨度」的帧账（R123 甲案读的就是它）。
    # 🔴 先读账本再取答案：账本缺失要在打模型之前炸，不许跑完 105 题才发现没法对账。
    ledger: dict[str, dict] = {}
    if approval_ledger is not None:
        ledger = load_approval_ledger(approval_ledger)
    # 🔴 分母账先派再取答案：扣除账断在题源上也要在打模型之前炸（与时延记账同一纪律）。
    scorability = derive_scorability(rows)
    results = []
    for row in rows:
        result = answer_fn(row)
        provenance = evaluate_provenance(result if isinstance(result, dict) else {})
        latency = result.get("latency_ms") if isinstance(result, dict) else None
        results.append(
            {
                "row": row,
                "result": result,
                "correct": _is_correct(row, result),
                "provenance": provenance,
                "evidence_ok": (
                    not row.get("requires_evidence", False)
                    or provenance["has_evidence"]
                ),
                "latency_ms": float(latency) if latency is not None else None,
            }
        )

    def ratio(values):
        return round(sum(bool(value) for value in values) / len(values), 4) if values else 0.0

    # 两列读数一起交给记账闸：answers 行的实测（载荷自报，或采集器当时的整调用跨度）与
    # 帧账 sidecar 的逐发 wall_ms。谁配进聚合由 aggregate_latency_ms 判，不由这里猜。
    latency_spans = [
        {
            "id": item["row"].get("id"),
            "reported_ms": item["latency_ms"],
            "frame_ledger_ms": (ledger.get(str(item["row"].get("id", ""))) or {}).get("wall_ms"),
        }
        for item in results
    ]
    category_metrics = {}
    for item in results:
        category = item["row"].get("category", "未分类")
        bucket = category_metrics.setdefault(
            category, {"total": 0, "correct": 0, "evidence": 0.0}
        )
        bucket["total"] += 1
        bucket["correct"] += int(item["correct"])
        bucket["evidence"] += item["provenance"]["evidence_coverage"]
    for bucket in category_metrics.values():
        total = bucket.pop("total")
        correct = bucket.pop("correct")
        evidence = bucket.pop("evidence")
        bucket["correctness"] = round(correct / total, 4) if total else 0.0
        bucket["evidence_coverage"] = round(evidence / total, 4) if total else 0.0
        bucket["total"] = total

    # 两把尺同出一源：全题那把按既有算法，可判子集那把在同一批 results 上派生。
    subset = correctness_subset_ruler(results, scorability)
    report = {
        "total": len(rows),
        "answer_correctness": ratio([item["correct"] for item in results]),
        SUBSET_RULER_KEY: subset[SUBSET_RULER_KEY],
        "evidence_coverage": ratio([item["evidence_ok"] for item in results]),
        "unsupported_claim_rate": round(
            sum(bool(item["provenance"]["unsupported_claims"]) for item in results)
            / len(results),
            4,
        )
        if results
        else 0.0,
        "category_metrics": category_metrics,
        SCORABLE_SUBSET_REPORT_KEY: {**scorability, **subset},
        "latency_ms": aggregate_latency_ms(latency_spans),
    }
    if approval_ledger is not None:
        report["approval_ledger"] = summarize_approval_ledger(rows, ledger)
        report["pre_approval_ruler"] = pre_approval_ruler(results, ledger)
        report["approval_line"] = format_approval_line(report)
    return report
