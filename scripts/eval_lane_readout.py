"""队列道（报告档）三格读出：D-1 可查回 / D-2 usage 非零 / D-3 出处随答案。只读、离线、零模型。

为什么这件必须落仓（R443 那条教训的延续）：run8 相 2 的判读是临时手搭的，
于是「可读面没有 usage」与「sources 0/20」被报成**判了红**，而 R259 之后真相是
**当时那把尺根本没读这批键**（`scripts/eval_transport_ask_v2.py:800-833` 把队列终态读数
折进帧账 `queue.terminal` 那一格）。尺换了形状，判词就得重算，且必须能一键复跑。

三条诚实口径（照抄 R259 的纪律，一条不省）：
① 只有 `terminal.shape == "structured"` 的行才算「读数」；`legacy` / `no_keys` / `not_terminal`
   读作「这一行说不出自己有没有出处」，**不拿 0 或空表冒充「查过，是零」**。
② `usage` 里 null 照 null 记，一枚都不折算成零；`authoritative=false` 原样进账。
③ 判据阈值全部现场派生，期望数一个都不手抄。

R447 在本件上多开两格（同一套诚实口径，一条不省）：
· 批准轮走没走（判据①）：``queued_approved`` / ``approval_failed`` / 仍停在
  ``queued_awaiting_approval`` 三枚分开数，逐枚点名差在哪。第三枚非空就是「批准轮没走」。
· 出处随答案交回（判据③）：可读面 ``sources_n>0`` 的题逐枚与 ``answers.evidence`` 的枚数对判。
  🔴 这一格只认**交出去的那一份**：可读面说了三枚而 answers 交了零枚 ⇒ 不达标，不拿可读面的
  读数冒充「已交回」，也不静默补零。answers 里压根没这一行 ⇒ 明写「取不到，不编数」。

R592 收口一枚取数把手（同一件事只留一处）：`evidence_n` 只住在 sidecar 行里，帧账行不带它。
  上一版「侧车 evidence_n ↔ answers.evidence 枚数不等」那一行直接去**帧账行**上取这一格 ⇒
  恒为 None ⇒ 报出一枚根本不存在的「sidecar 与 answers 不齐」，而表格那一列（取 sidecar）
  又明明打着 14/6/9。现在三处读数一律走 `sidecar_evidence_n()`：真缺那一格就如实报「取不到」，
  既不冒充零枚，也不冒充不齐，更不冒充齐。

用法：
    python scripts/eval_lane_readout.py --label run9c
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台默认 GBK，中文与箭头会当场炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

USAGE_SLOTS = ("prompt_tokens", "completion_tokens", "total_tokens", "model_calls",
               "authoritative", "ledger")
#: R447 判据①/② 的三枚读数名（与量具同源，本件只数不裁决之外的东西）。
KIND_PARKED = "queued_awaiting_approval"      # 停表读数：一步没走（R447 之后应当读作零枚）
KIND_APPROVED = "queued_approved"             # 队列道挂起 → 批准到终答
KIND_APPROVAL_FAILED = "approval_failed"      # 批准轮走了而没取到终答
SHAPES = ("structured", "legacy", "unreadable", "no_keys", "not_terminal")


def load_jsonl(path: str) -> list[dict]:
    rows: dict[str, dict] = {}
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row.get("id"))
            previous = rows.get(key)
            if previous is None or int(row.get("attempt") or 0) >= int(previous.get("attempt") or 0):
                rows[key] = row
    return list(rows.values())

#: R592：`evidence_n` 这一格住在 **sidecar 行**里（采集器落盘的那本账），帧账行
#: （``*-frames.jsonl``）从来不带它 —— 在册 run9 样本实测：sidecar 105/105 有，帧账 0/105 有。
#: 所以全件只许用下面这一枚把手取它，逐枚表的 evidence_n 列与「两本账不等」那一行必须同源。
#: 上一版是两处各自把手：表格列取 sidecar（对），那行「不等」直接去帧账行上取（错，恒为 None），
#: 于是 run16 把 12 枚齐全的账打印成 11 枚不齐，run9 把 105 枚里 72 枚打印成不齐，
#: 同一件程序两处答案互相打脸，下一班照那行打印还会去立案「两本账口径不齐」。
SIDECAR_EVIDENCE_KEY = "evidence_n"
#: 取不到数时的状态名。取不到 ≠ 零枚，也 ≠ 「两本账不齐」，一律如实点名，一枚都不许就近折算。
EV_OK = "读数"
EV_NO_ROW = "sidecar 没这一行"
EV_NO_KEY = "sidecar 缺 evidence_n 格"
EV_NULL = "evidence_n 值=null"
EV_NOT_INT = "evidence_n 值不是整数"


def sidecar_evidence_n(sidecar_rows, row_id):
    """唯一一枚 evidence_n 取数把手：交回 ``(枚数, 状态)``。

    枚数是 int 当且仅当状态是 ``EV_OK``；枚数是 None 时状态点名缺在哪一格。
    缺行 / 缺键 / 值为 null / 值不是整数一律交 None —— 本件抬头口径①：
    说不出这一枚有几枚，不等于这一枚是零枚。
    """
    row = sidecar_rows.get(str(row_id))
    if row is None:
        return None, EV_NO_ROW
    if SIDECAR_EVIDENCE_KEY not in row:
        return None, EV_NO_KEY
    value = row[SIDECAR_EVIDENCE_KEY]
    if value is None:
        return None, EV_NULL
    if isinstance(value, bool) or not isinstance(value, int):
        return None, EV_NOT_INT
    return value, EV_OK


def rank(values: list[float], q: float):
    if not values:
        return None
    v = sorted(values)
    if len(v) == 1:
        return round(v[0], 1)
    pos = (len(v) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return round(v[lo] + (v[hi] - v[lo]) * (pos - lo), 1)


def nearest_rank_p95(values: list[float]):
    if not values:
        return None
    v = sorted(values)
    idx = max(0, math.ceil(0.95 * len(v)) - 1)
    return round(v[idx], 1)


def stat_line(name: str, values) -> str:
    nums = [float(x) for x in values if isinstance(x, (int, float))]
    if not nums:
        return "- %s：无量可算（该格全空）" % name
    return "- %s：n=%d p50=%s p95(nearest-rank)=%s p95(linear)=%s max=%s min=%s" % (
        name, len(nums), rank(nums, 0.5), nearest_rank_p95(nums), rank(nums, 0.95),
        round(max(nums), 1), round(min(nums), 1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", default="run9c")
    ap.add_argument("--dir", default="", help="件所在目录，缺省 %TEMP%\\evalrun")
    ap.add_argument("--frames", default="")
    ap.add_argument("--sidecar", default="")
    ap.add_argument("--answers", default="")
    args = ap.parse_args(argv)

    base = args.dir or os.path.join(os.environ.get("TEMP", "/tmp"), "evalrun")
    frames_path = args.frames or os.path.join(base, "sidecar-%s-frames.jsonl" % args.label)
    sidecar_path = args.sidecar or os.path.join(base, "sidecar-%s.jsonl" % args.label)
    answers_path = args.answers or os.path.join(base, "answers-%s.jsonl" % args.label)

    missing = [p for p in (frames_path, sidecar_path, answers_path) if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("🔴 取不到件：%s —— 明写取不到，不编数" % p)
        return 2

    frames = load_jsonl(frames_path)
    sidecar = {str(r["id"]): r for r in load_jsonl(sidecar_path)}
    answers = {str(r["id"]): r for r in load_jsonl(answers_path)}
    by_id = {str(r["id"]): r for r in frames}

    # 🔴 R592：evidence_n 全件只在这一处取一次，后面四处读数（=0 名册 / 取不到名册 /
    # 两本账对判 / 逐枚表那一列）一律从 ev_readings 里拿，不许再各自把手。
    ev_readings = {rid: sidecar_evidence_n(sidecar, rid)
                   for rid in sorted(set(sidecar) | set(answers) | set(by_id))}

    print("## 队列道三格读出（label=%s，件=%s）" % (args.label, os.path.basename(frames_path)))
    print("- 帧账行数=%d ｜ sidecar 行数=%d ｜ answers 行数=%d" % (len(frames), len(sidecar), len(answers)))
    print("- join 不等长 ⇒ 帧账有而 sidecar 无=%s ｜ sidecar 有而帧账无=%s" % (
        sorted(set(by_id) - set(sidecar)) or "无", sorted(set(sidecar) - set(by_id)) or "无"))
    print()

    kinds = collections.Counter(str(r.get("kind")) for r in frames)
    print("### D-1 队列终态（可查回）")
    print("- kind 直方图=%s" % dict(kinds))
    finals = collections.Counter(str(((r.get("queue") or {}).get("final"))) for r in frames)
    print("- queue.final 直方图=%s" % dict(finals))
    shapes = collections.Counter(str(((r.get("queue") or {}).get("terminal") or {}).get("shape")) for r in frames)
    print("- terminal.shape 直方图=%s（只有 structured 算读数）" % dict(shapes))
    states = collections.Counter(str(((r.get("queue") or {}).get("terminal") or {}).get("state")) for r in frames)
    print("- terminal.state 直方图=%s" % dict(states))
    structured = [r for r in frames if ((r.get("queue") or {}).get("terminal") or {}).get("shape") == "structured"]
    present = sum(1 for r in structured if ((r["queue"]["terminal"]).get("answer_present")) is True)
    parked = [str(r["id"]) for r in structured if ((r["queue"]["terminal"]).get("answer_is_park_notice")) is True]
    absent = [str(r["id"]) for r in structured if ((r["queue"]["terminal"]).get("answer_present")) is not True]
    print("- structured 行数=%d/%d ｜ 其中 answer_present=true=%d ｜ 挂起文案枚数=%d 题号=%s ｜ answer_present 不为 true=%s" % (
        len(structured), len(frames), present, len(parked), parked or "无", absent or "无"))
    print("- 送出去的答案里被判空/哨兵=%s" % (sorted(str(r["id"]) for r in frames if r.get("sentinel")) or "无"))
    # R447 判据①：挂起读数之后那三件事是三件事，一枚都不许并。
    approved_ids = sorted(str(r["id"]) for r in frames if str(r.get("kind")) == KIND_APPROVED)
    failed_ids = sorted(str(r["id"]) for r in frames if str(r.get("kind")) == KIND_APPROVAL_FAILED)
    still_parked = sorted(str(r["id"]) for r in frames if str(r.get("kind")) == KIND_PARKED)
    print("- 批准轮（R447）：批到终答=%d 题号=%s ｜ 批准失败=%d 题号=%s ｜ 仍停在挂起读数（批准轮没走）=%d 题号=%s" % (
        len(approved_ids), approved_ids or "无", len(failed_ids), failed_ids or "无",
        len(still_parked), still_parked or "无"))
    if still_parked:
        print("🔴 判据①：上面这些题读到 awaiting_approval 就交了空正文 —— 批准轮一步没走。")
    for rid in failed_ids:
        record = sidecar.get(rid) or {}
        print("  - %s 批准失败：rounds=%s http=%s error=%s" % (
            rid, record.get("approval_rounds"), record.get("approval_http_status"),
            str(record.get("approval_error") or "")[:120] or "（侧车没这一格，取不到，不编数）"))
    print(stat_line("polls", [(r.get("queue") or {}).get("polls") for r in frames]))
    print(stat_line("wait_ms", [(r.get("queue") or {}).get("wait_ms") for r in frames]))
    blips = [(str(r["id"]), (r.get("queue") or {}).get("blips")) for r in frames if (r.get("queue") or {}).get("blips")]
    relogins = [(str(r["id"]), (r.get("queue") or {}).get("relogins")) for r in frames if (r.get("queue") or {}).get("relogins")]
    print("- blips 非零=%s ｜ relogins 非零=%s" % (blips or "无", relogins or "无"))
    answer_chars = [int(r.get("answer_chars") or 0) for r in frames]
    print("- 终答字数 p50=%s min=%s max=%s ｜ <40 字的枚数=%d 题号=%s" % (
        rank(answer_chars, 0.5), min(answer_chars) if answer_chars else None,
        max(answer_chars) if answer_chars else None,
        sum(1 for x in answer_chars if x < 40),
        sorted(str(r["id"]) for r in frames if int(r.get("answer_chars") or 0) < 40) or "无"))
    print()

    print("### D-2 usage 可读（队列可读面）")
    up_true = [str(r["id"]) for r in structured if ((r["queue"]["terminal"]).get("usage_present")) is True]
    up_other = [(str(r["id"]), ((r["queue"]["terminal"]).get("usage_present"))) for r in structured
                if ((r["queue"]["terminal"]).get("usage_present")) is not True]
    print("- structured 行里 usage_present=true=%d/%d" % (len(up_true), len(structured)))
    print("- usage_present 不为 true=%s" % (up_other or "无"))
    for slot in USAGE_SLOTS:
        vals = []
        nulls = []
        for r in structured:
            usage = ((r["queue"]["terminal"]).get("usage") or {})
            if slot not in usage:
                nulls.append(str(r["id"]) + ":缺键")
                continue
            value = usage.get(slot)
            if value is None:
                nulls.append(str(r["id"]))
            else:
                vals.append(value)
        print("- usage.%s：有值=%d 枚（值样本=%s）｜ null/缺键=%d %s" % (
            slot, len(vals), [vals[i] for i in range(min(3, len(vals)))], len(nulls), nulls[:8] or ""))
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        nums = [((r["queue"]["terminal"]).get("usage") or {}).get(key) or 0 for r in structured]
        zero = [str(r["id"]) for r in structured if not (((r["queue"]["terminal"]).get("usage") or {}).get(key) or 0)]
        print("- Σ%s=%d ｜ 该格为 0 的题号=%s" % (key, sum(int(x) for x in nums), zero or "无"))
    print()

    print("### D-3 出处随答案（队列可读面 + 送出去的那一份）")
    sp_true = [str(r["id"]) for r in structured if ((r["queue"]["terminal"]).get("sources_present")) is True]
    n_zero = [(str(r["id"]), ((r["queue"]["terminal"]).get("sources_n"))) for r in structured
              if ((r["queue"]["terminal"]).get("sources_n")) in (0, None)]
    print("- structured 行里 sources_present=true=%d/%d" % (len(sp_true), len(structured)))
    print("- sources_n 为 0 或 None 的题号=%s" % (n_zero or "无"))
    serr = [(str(r["id"]), ((r["queue"]["terminal"]).get("sources_error"))) for r in structured
            if ((r["queue"]["terminal"]).get("sources_error"))]
    print("- sources_error 非空=%s" % (serr or "无"))
    ev_zero = sorted(rid for rid, (n, _) in ev_readings.items() if n == 0)
    ev_unknown = sorted((rid, state) for rid, (_, state) in ev_readings.items() if state != EV_OK)
    print("- sidecar.evidence_n=0 的题号=%s（真读到 0 枚才算零，共 %d 枚）" % (ev_zero or "无", len(ev_zero)))
    print("- sidecar.evidence_n 取不到的题号=%s（取不到≠零枚，也≠两本账不齐，共 %d 枚）" % (
        ev_unknown or "无", len(ev_unknown)))
    ev_ans = sorted(i for i, r in answers.items() if not (r.get("evidence") or []))
    print("- answers.evidence 为空的题号=%s" % (ev_ans or "无"))
    src_events = sum(1 for r in frames if any(e.get("event") == "sources" for e in (r.get("events") or [])))
    print("- 流内 sources 事件出现过的枚数=%d/%d（🔴 这一格属**流内层**，与可读面那两层不许互抄）" % (src_events, len(frames)))
    # R447 判据③：出处要**随答案**交回。可读面说 N 枚的题，交出去的那一份必须正好 N 枚。
    gaps = []
    for r in structured:
        count = ((r["queue"]["terminal"]).get("sources_n"))
        if not isinstance(count, int) or count <= 0:
            continue  # 读数为零或说不出：这一枚不构成「该交回几枚」的义务（说不出 ≠ 零枚）
        rid = str(r["id"])
        if rid not in answers:
            gaps.append((rid, count, "answers 里没这一行（取不到，不编数）"))
            continue
        got = len(answers[rid].get("evidence") or [])
        if got != count:
            gaps.append((rid, count, got))
    print("- 出处交回对判（可读面 sources_n>0 ↔ answers.evidence 枚数）：对不上=%d 逐枚=%s" % (
        len(gaps), gaps or "无"))
    print("- 判词：%s" % ("🔴 判据③ 不达标 —— 可读面交了出处而评分器没拿到" if gaps
                        else "达标 —— 可读面说了几枚，交出去的就是几枚"))
    side_vs_ans = []
    for rid in sorted(set(sidecar) & set(answers)):
        n_side, _state = ev_readings[rid]
        n_ans = len(answers[rid].get("evidence") or [])
        if n_side is None:
            continue  # 取不到的已由上一行点名：既不冒充「不齐」，也不冒充「齐」
        if n_side != n_ans:
            side_vs_ans.append((rid, n_side, n_ans))
    print("- 侧车 evidence_n ↔ answers.evidence 枚数不等=%s（两本账说的必须同一件事）" % (side_vs_ans or "无"))
    approved_evidence = [(str(r["id"]), len((answers.get(str(r["id"])) or {}).get("evidence") or []))
                         for r in frames if str(r.get("kind")) == KIND_APPROVED]
    print("- 批准腿交回的出处枚数（可读面在挂起那一枚上说 0，两格不许互抄）=%s" % (approved_evidence or "无"))
    print()

    print("### 逐枚一行（判词要能追到题号）")
    print("| id | kind | final | shape | state | ans_present | park | sources_n | total_tokens | model_calls | evidence_n | ans_chars | polls | wait_ms | ans_ev | appr_rounds |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(frames, key=lambda x: str(x["id"])):
        q = r.get("queue") or {}
        t = q.get("terminal") or {}
        u = t.get("usage") or {}
        n_ev, ev_state = ev_readings[str(r["id"])]
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("id"), r.get("kind"), q.get("final"), t.get("shape"), t.get("state"),
            t.get("answer_present"), t.get("answer_is_park_notice"), t.get("sources_n"),
            u.get("total_tokens"), u.get("model_calls"),
            n_ev if ev_state == EV_OK else ev_state, r.get("answer_chars"),
            q.get("polls"), q.get("wait_ms"),
            len((answers.get(str(r["id"])) or {}).get("evidence") or []) if str(r["id"]) in answers else None,
            (sidecar.get(str(r["id"])) or {}).get("approval_rounds")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
