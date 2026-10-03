r"""R586 probe: does raising the Ollama context window cost us anything on this box?

Host-side orchestrator. Nothing here is a business write: every model call is
num_predict=1 (prefill only), every container call is a read (`ollama ps`) plus an
`ollama stop` between tiers, which is the only state change and is undone by the last
tier landing back on 4096 (the shipped default).

Why this ticket exists: report-tier questions are refused before the request is sent
(`context_limit_exceeded`, required_n_ctx=4230 > n_ctx=4096), and the two measurements
already in the record disagree about the price of raising the window --
``.env.example:309`` says 4096->8192 took load_s 0.001 -> 5.811, while
``app/agents/contracts.py:329`` says the same 2154-token prompt prefilled in 66.683 s vs
68.849 s (+3.2%). Both numbers cannot be the whole truth, so measure before changing.

Guards baked in:
  * a tier is VOID unless ``ollama ps`` reports PROCESSOR == 100% GPU for it;
  * the corpus is read from scripts/perf_probe_rate.py so the numbers stay comparable
    with the W8 rate curves already on file (same sentences, same prompt shape);
  * the in-container body is generated as pure ASCII, so piping it through stdin cannot
    re-encode the Chinese corpus and silently change the token count being measured.
"""
import ast
import io
import json
import os
import re
import statistics
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTAINER = "enterprise-brain-backend-1"
OLLAMA_CONTAINER = "enterprise-brain-ollama-1"
MODEL = "qwen3.5:9b"
TIERS = (4096, 6144, 8192, 4096)
PROMPT_CHARS = 3950
SAMPLES = 8
DECODE_SAMPLES = 2
DECODE_PREDICT = 300
QUESTIONS = [
    "经销商逾期超过六十天会有什么后果？",
    "银行承兑汇票回款时贴现费用如何处理？",
    "连续两个季度评级为 C 的经销商会被怎样处理？",
    "提前回款的现金折扣按什么口径冲抵？",
    "跨区窜货造成的回款归属争议由谁裁定？",
    "坏账核销需要附哪些材料、超过多少金额要报批？",
]


def corpus():
    src = io.open(os.path.join(REPO, "scripts", "perf_probe_rate.py"), "r", encoding="utf-8").read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_SENTENCES":
            return list(ast.literal_eval(node.value))
    raise SystemExit("[r586] 取不到在册语料 scripts/perf_probe_rate.py:_SENTENCES")


BODY_TMPL = '''
import json, sys, time, urllib.request
OLLAMA = "http://ollama:11434"
MODEL = "qwen3.5:9b"
TIMEOUT = 1800
SENT = json.loads(r"""__SENT__""")
QUES = json.loads(r"""__QUES__""")


def cn_text(target):
    out, total, idx = [], 0, 1
    while total < target:
        line = "%04d. " % idx + SENT[(idx - 1) % len(SENT)]
        out.append(line)
        total += len(line)
        idx += 1
    body = "\\n".join(out)
    if len(body) > target + 40:
        body = body[:target] + "。"
    return body


def api(payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/chat", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(question, context, salt, num_ctx, num_predict=1, case="steady"):
    prompt = ("【请求校验码 %s】\\n参考以下资料回答问题。\\n\\n【资料】\\n%s\\n\\n【问题】%s" % (salt, context, question))
    body = {"model": MODEL, "stream": False,
            "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": num_ctx},
            "messages": [{"role": "user", "content": prompt}]}
    started = time.monotonic()
    try:
        resp = api(body)
    except Exception as exc:
        print("JSONL " + json.dumps({"ok": False, "note": repr(exc)[:200], "wall_s": round(time.monotonic() - started, 3)}), flush=True)
        return
    wall = time.monotonic() - started
    pe = resp.get("prompt_eval_count", 0) or 0
    ped = resp.get("prompt_eval_duration", 0) or 0
    ed = resp.get("eval_duration", 0) or 0
    ec = resp.get("eval_count", 0) or 0
    row = {"ok": True, "case": case, "num_ctx": num_ctx, "prompt_chars": len(prompt), "prompt_tokens": pe,
           "load_s": round((resp.get("load_duration", 0) or 0) / 1e9, 3),
           "prefill_s": round(ped / 1e9, 3), "wall_s": round(wall, 3),
           "decode_s": round(ed / 1e9, 3), "eval_tokens": ec,
           "prefill_tps": round(pe / (ped / 1e9), 2) if ped > 5e6 else None,
           "decode_tps": round(ec / (ed / 1e9), 2) if ed > 5e6 else None}
    print("JSONL " + json.dumps(row), flush=True)


def main():
    import uuid
    num_ctx = int(sys.argv[1])
    samples = int(sys.argv[2])
    chars = int(sys.argv[3])
    decode_samples = int(sys.argv[4])
    context = cn_text(chars)
    chat(QUES[0], context, "r586warm", num_ctx, case="warm_cold_load")
    for i in range(samples):
        chat(QUES[i % len(QUES)], context, "r586" + uuid.uuid4().hex[:8], num_ctx, case="prefill")
    for i in range(decode_samples):
        chat(QUES[(i + 2) % len(QUES)], context, "r586d" + uuid.uuid4().hex[:8], num_ctx,
             num_predict=int(sys.argv[5]), case="decode")


main()
'''


def docker(args, stdin_bytes=None, timeout=3600):
    cmd = ["docker", "exec"] + (["-i"] if stdin_bytes is not None else []) + [CONTAINER] + args
    proc = subprocess.run(cmd, input=stdin_bytes, capture_output=True, timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def ollama_ps():
    proc = subprocess.run(["docker", "exec", OLLAMA_CONTAINER, "ollama", "ps"], capture_output=True, timeout=180)
    return proc.stdout.decode("utf-8", "replace").strip()


def vram():
    q = "memory.used,memory.total"
    out = subprocess.run(["nvidia-smi", "--query-gpu=" + q, "--format=csv,noheader,nounits"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace")
    parts = [p.strip() for p in out.strip().split(",")]
    return {"used_mib": int(parts[0]), "total_mib": int(parts[1])} if len(parts) >= 2 else {"raw": out.strip()}


def gpu_pct(ps_text):
    # ``ollama ps`` prints e.g. "qwen3.5:9b 5653... 5.3 GB 100% GPU 4096 8 minutes
    # from now". A whitespace column split turns "100%" and "GPU" into two tokens, so
    # read PROCESSOR with a regex. A tier that spills onto CPU is void, per this ticket.
    for line in ps_text.splitlines()[1:]:
        if not line.strip():
            continue
        gpu = re.search(r"(\d+(?:\.\d+)?)%\s+GPU", line)
        cpu = re.search(r"(\d+(?:\.\d+)?)%\s+CPU", line)
        if gpu and cpu:
            return "%s%% GPU / %s%% CPU" % (gpu.group(1), cpu.group(1))
        if gpu:
            return "%s%% GPU" % gpu.group(1)
        if re.search(r"\bCPU\b", line):
            return "100% CPU"
        return line.strip()[:40]
    return "unloaded"


def rows_from(stdout_text):
    out = []
    for line in stdout_text.splitlines():
        if line.startswith("JSONL "):
            out.append(json.loads(line[6:]))
    return out


def median(rows, key):
    vals = [r[key] for r in rows if r.get("ok") and isinstance(r.get(key), (int, float))]
    return round(statistics.median(vals), 3) if vals else None


def main():
    sent = corpus()
    body = BODY_TMPL.replace("__SENT__", json.dumps(sent, ensure_ascii=True)).replace("__QUES__", json.dumps(QUESTIONS, ensure_ascii=True))
    body_bytes = ("# -*- coding: utf-8 -*-\n" + body).encode("utf-8")
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    outdir = os.path.join(os.environ.get("TEMP", "/tmp"), "r586")
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    jsonl = os.path.join(outdir, "r586-probe-%s.jsonl" % stamp)
    handle = io.open(jsonl, "w", encoding="utf-8", newline="\n")
    results = []
    print("# r586_context_window_probe start %s tiers=%s chars=%d samples=%d" % (stamp, TIERS, PROMPT_CHARS, SAMPLES), flush=True)
    for tier in TIERS:
        subprocess.run(["docker", "exec", OLLAMA_CONTAINER, "ollama", "stop", MODEL], capture_output=True, timeout=180)
        pre_ps = ollama_ps()
        pre_vram = vram()
        t0 = time.monotonic()
        rc, out, err = docker(["python", "-", str(tier), str(SAMPLES), str(PROMPT_CHARS),
                                  str(DECODE_SAMPLES), str(DECODE_PREDICT)], stdin_bytes=body_bytes)
        elapsed = round(time.monotonic() - t0, 1)
        rows = rows_from(out)
        if not rows:
            print("[r586] tier %d 零读数 rc=%d err=%s" % (tier, rc, err[:300]), flush=True)
            handle.write(json.dumps({"event": "tier_failed", "tier": tier, "rc": rc, "err": err[:500]}) + "\n")
            continue
        warm = rows[0]
        prefill = [r for r in rows if r.get("case") == "prefill"]
        decode = [r for r in rows if r.get("case") == "decode"]
        steady = prefill
        ps = ollama_ps()
        post_vram = vram()
        processor = gpu_pct(ps)
        summary = {
            "event": "tier", "tier": tier, "rc": rc, "elapsed_s": elapsed,
            "prompt_tokens": [r.get("prompt_tokens") for r in steady],
            "warm_load_s": warm.get("load_s"), "warm_prefill_s": warm.get("prefill_s"), "warm_wall_s": warm.get("wall_s"),
            "steady_load_s_max": max([r.get("load_s") or 0 for r in steady] or [None]) if steady else None,
            "median_prefill_s": median(steady, "prefill_s"), "median_wall_s": median(steady, "wall_s"),
            "median_prefill_tps": median(steady, "prefill_tps"),
            "median_decode_s": median(decode, "decode_s"), "median_decode_tps": median(decode, "decode_tps"),
            "eval_tokens": [r.get("eval_tokens") for r in decode],
            "vram_before": pre_vram, "vram_after": post_vram,
            "ps": ps.replace("\n", " | "), "processor": processor, "pre_ps": pre_ps.replace("\n", " | "),
            "tier_ok": processor in ("GPU", "100% GPU"),
        }
        results.append(summary)
        for r in rows:
            handle.write(json.dumps({"tier": tier, **r}) + "\n")
        handle.write(json.dumps(summary) + "\n")
        handle.flush()
        print("JSONL " + json.dumps(summary, ensure_ascii=False), flush=True)
    handle.close()
    print("# jsonl=%s" % jsonl, flush=True)
    print("# 台账（中位 prefill / 冷加载 / GPU 归属）", flush=True)
    for s in results:
        print("  n_ctx=%-5d median_prefill_s=%-8s warm_load_s=%-8s median_wall_s=%-8s processor=%-10s tier_ok=%s vram_after=%s" % (
            s["tier"], s["median_prefill_s"], s["warm_load_s"], s["median_wall_s"], s["processor"], s["tier_ok"], s["vram_after"]["used_mib"] if "used_mib" in s["vram_after"] else s["vram_after"]), flush=True)
    return 0 if results else 2


if __name__ == "__main__":
    sys.exit(main())