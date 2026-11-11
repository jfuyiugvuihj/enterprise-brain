r"""W8 perf probe #1: qwen3.5:9b prefill / decode rate curves via native Ollama /api/chat.

Read-only measurement. No business data is written, no product code is touched, no
container file is modified. Host port 11434 is NOT published on this machine, so the
probe has to run inside the docker network:

    cd C:/Users/fengx/PycharmProjects/perf-lab
    cmd /c "docker exec -i enterprise-brain-backend-1 python - < scripts/perf_probe_rate.py --suite prefill"

The byte-level `cmd /c <` redirect is deliberate: piping through PowerShell alone would
re-encode the Chinese prompt corpus and change the token counts being measured.
Suites: warmup | prefill | decode | think | all
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

OLLAMA = "http://ollama:11434"
MODEL = "qwen3.5:9b"
TIMEOUT = 900

# Enterprise credit-policy corpus. Every line carries a unique numeric prefix so BPE
# cannot compress repeated text into an unrealistically low token count.
_SENTENCES = [
    "经销商年度回款周期按自然季度考核，逾期三十天以内记为轻微违约并书面提示。",
    "逾期超过三十天未满六十天的，暂停新客户授信并缩减下季度返点结算比例。",
    "逾期超过六十天的，系统自动冻结新货发运，需经区域总监与销售运营双签方可解除。",
    "信用额度依据上一年度实际回款表现核定，最高不超过年度采购额的百分之四十。",
    "客户以银行承兑汇票回款的，贴现费用由双方按合同约定比例分担。",
    "季度末最后一笔回款以到账日为准，在途资金不计入当季度考核口径。",
    "连续两个季度评级为 C 的经销商，纳入淘汰观察名单并缩短账期至三十天。",
    "大客户专项备货需单独申请临时额度，审批通过后有效期不超过四十五天。",
    "对账差异应在收到对账单后十个工作日内书面提出，逾期视同认可。",
    "跨区窜货造成的回款归属争议，由渠道管理部按首次报备记录裁定。",
    "提前回款可享受千分之一点五的现金折扣，折扣在下季度返利中冲抵。",
    "坏账核销须附完整催收记录与法务意见，单笔超过二十万元报财务总监审批。",
]

QUESTION = "经销商逾期超过六十天会有什么后果？"
LONG_ASK = "请用条目方式详细说明经销商信用管理应注意的十五个要点。"
PREFILL_SCALES = [90, 520, 1680, 3130, 4300, 6500]
DECODE_SCALES = [200, 400]


def cn_text(target_chars):
    out, total, idx = [], 0, 1
    while total < target_chars:
        line = "%04d. " % idx + _SENTENCES[(idx - 1) % len(_SENTENCES)]
        out.append(line)
        total += len(line)
        idx += 1
    body = "\n".join(out)
    if len(body) > target_chars + 40:
        body = body[:target_chars] + "。"
    return body


def api(path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(OLLAMA + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_prompt(question, context, salt=None):
    marker = "" if salt is None else "【请求校验码 %s】\n" % salt
    return marker + "参考以下资料回答问题。\n\n【资料】\n%s\n\n【问题】%s" % (context, question)


def chat(question, context, num_predict, think=None, salt=None, num_ctx=None):
    """Mirror the product prompt shape: retrieved context first, question last."""
    prompt = build_prompt(question, context, salt)
    body = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0, "num_predict": num_predict},
        "messages": [{"role": "user", "content": prompt}],
    }
    if think is not None:
        body["think"] = think == "on"
    if num_ctx is not None:
        body["options"]["num_ctx"] = num_ctx
    started = time.monotonic()
    try:
        resp = api("/api/chat", body)
    except urllib.error.HTTPError as exc:
        return {"ok": False, "case_note": "http_%s" % exc.code,
                "detail": exc.read().decode("utf-8", "replace")[:240],
                "prompt_chars": len(prompt),
                "wall_s": round(time.monotonic() - started, 3)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "case_note": repr(exc)[:240], "prompt_chars": len(prompt),
                "wall_s": round(time.monotonic() - started, 3)}
    wall = time.monotonic() - started
    pe = resp.get("prompt_eval_count", 0) or 0
    ev = resp.get("eval_count", 0) or 0
    ped = resp.get("prompt_eval_duration", 0) or 0
    evd = resp.get("eval_duration", 0) or 0
    content = (resp.get("message") or {}).get("content") or resp.get("content") or ""
    return {
        "ok": True,
        "prompt_chars": len(prompt),
        "prompt_eval_count": pe,
        "eval_count": ev,
        "load_s": round((resp.get("load_duration", 0) or 0) / 1e9, 3),
        "prefill_s": round(ped / 1e9, 3),
        "decode_s": round(evd / 1e9, 3),
        "total_s": round((resp.get("total_duration", 0) or 0) / 1e9, 3),
        "wall_s": round(wall, 3),
        "prefill_tps": round(pe / (ped / 1e9), 2) if ped > 5e6 else None,
        "decode_tps": round(ev / (evd / 1e9), 2) if evd > 5e6 else None,
        "think": think,
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "answer_chars": len(content),
        "thinking_chars": len((resp.get("message") or {}).get("thinking") or resp.get("thinking") or ""),
        "answer_head": content[:60].replace("\n", "\\n"),
    }


def emit(row):
    print("JSONL " + json.dumps(row, ensure_ascii=False), flush=True)


def suite_warmup():
    row = chat(QUESTION, cn_text(90), 1)
    row["case"] = "warmup_cold_load"
    emit(row)


def suite_prefill():
    """Salted runs. Ollama 0.34 caches prompt prefixes, so a cumulative corpus
    inflates the apparent rate (observed 72 tok/s on a cached prefix). A unique
    leading nonce per call forces the cold prefill a real user request pays for."""
    for chars in PREFILL_SCALES:
        row = chat(QUESTION, cn_text(chars), 1, salt=uuid.uuid4().hex[:12])
        row["case"] = "prefill_chars_%d" % chars
        emit(row)
    for nctx in (4096, 8192):
        row = chat(QUESTION, cn_text(3130), 1, salt=uuid.uuid4().hex[:12], num_ctx=nctx)
        row["case"] = "num_ctx_%d_prefill2136" % nctx
        emit(row)


def suite_decode():
    for n in DECODE_SCALES:
        row = chat(LONG_ASK, cn_text(90), n, salt=uuid.uuid4().hex[:12])
        row["case"] = "decode_predict_%d" % n
        emit(row)


def suite_think():
    for think in ("off", "on"):
        row = chat(QUESTION, cn_text(520), 1, think=think, salt=uuid.uuid4().hex[:12])
        row["case"] = "think_%s_prefill383" % think
        emit(row)
    for think in ("off", "on"):
        row = chat(LONG_ASK, cn_text(90), 300, think=think, salt=uuid.uuid4().hex[:12])
        row["case"] = "think_%s_decode300" % think
        emit(row)


SUITES = {"warmup": suite_warmup, "prefill": suite_prefill, "decode": suite_decode, "think": suite_think}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="prefill", choices=["warmup", "prefill", "decode", "think", "all"])
    args = parser.parse_args()
    print("# probe_start %s model=%s suite=%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), MODEL, args.suite), flush=True)
    try:
        ver = api("/api/version")
        ps = api("/api/ps")
        emit({"case": "runtime", "ollama": ver.get("version"),
              "loaded": [{"name": m["name"], "context_length": m.get("context_length"),
                          "size_vram": m.get("size_vram")} for m in ps.get("models", [])]})
    except Exception as exc:  # noqa: BLE001
        print("# runtime_probe_failed %r" % (exc,), flush=True)
    for name in (list(SUITES) if args.suite == "all" else [args.suite]):
        SUITES[name]()
    print("# probe_end %s" % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())