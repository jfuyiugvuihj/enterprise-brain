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
    ev_side = [(str(r["id"]), r.get("evidence_n")) for r in frames if int(r.get("evidence_n") or 0) == 0]
    print("- sidecar.evidence_n=0 的题号=%s" % (sorted(i for i, _ in ev_side) or "无"))
    ev_ans = sorted(i for i, r in answers.items() if not (r.get("evidence") or []))
    print("- answers.evidence 为空的题号=%s" % (ev_ans or "无"))
    src_events = sum(1 for r in frames if any(e.get("event") == "sources" for e in (r.get("events") or [])))
    print("- 流内 sources 事件出现过的枚数=%d/%d（🔴 这一格属**流内层**，与可读面那两层不许互抄）" % (src_events, len(frames)))
    print()

    print("### 逐枚一行（判词要能追到题号）")
    print("| id | kind | final | shape | state | ans_present | park | sources_n | total_tokens | model_calls | evidence_n | ans_chars | polls | wait_ms |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(frames, key=lambda x: str(x["id"])):
        q = r.get("queue") or {}
        t = q.get("terminal") or {}
        u = t.get("usage") or {}
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r.get("id"), r.get("kind"), q.get("final"), t.get("shape"), t.get("state"),
            t.get("answer_present"), t.get("answer_is_park_notice"), t.get("sources_n"),
            u.get("total_tokens"), u.get("model_calls"),
            (sidecar.get(str(r["id"])) or {}).get("evidence_n"), r.get("answer_chars"),
            q.get("polls"), q.get("wait_ms")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
