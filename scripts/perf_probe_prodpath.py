r"""W8 perf probe #4: the endpoint the product actually calls.

The product never touches /api/chat. `ChatOpenAI` / `ModelHandler` both hit Ollama's
OpenAI-compatible /v1/chat/completions, whose response carries `usage`. That is the only
place where "what the product pays" and "what Ollama measured" meet, so this probe calls
/v1 exactly the way the code does (same messages, same tools, temperature=0,
stream=false) and reconciles usage against visible text length.

Purpose: prove or disprove the hidden-reasoning-token hypothesis behind
"230 字的回答花了 50.4 秒" in the 21:58 request.

    cd C:/Users/fengx/PycharmProjects/perf-lab
    cmd /c "docker exec -i enterprise-brain-backend-1 python - < scripts/perf_probe_prodpath.py"
"""
import json
import pathlib
import sys
import time
import urllib.request
import uuid

OLLAMA = "http://ollama:11434"
V1 = OLLAMA + "/v1/chat/completions"
APP_ROOT = pathlib.Path("/app")
MODEL = "qwen3.5:9b"
TIMEOUT = 900
QUESTION = "我们经销商的标准回款周期是多少天？超期多久会停发新货？"
ANSWER_MARK = "【请求校验码 %s】\n"


def emit(row):
    print("JSONL " + json.dumps(row, ensure_ascii=False), flush=True)


def v1(messages, tools=None, note="", stream=False, max_tokens=400):
    # max_tokens is NOT what the product sends (it sends nothing, i.e. unbounded), and
    # that is itself a finding: an uncapped non-streaming /v1 call hung for >5 minutes
    # during this measurement, the same shape as the 5 x 60s cascade in the 21:50 log.
    body = {"model": MODEL, "messages": messages, "temperature": 0,
            "max_tokens": max_tokens, "stream": stream}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(V1, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
    wall = time.monotonic() - started
    if stream:
        chunks = 0
        first_at = None
        usage = {}
        for line in raw.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            d = json.loads(payload)
            usage = d.get("usage") or usage
            delta = ((d.get("choices") or [{}])[0].get("delta") or {}).get("content")
            if delta and first_at is None:
                first_at = wall
            chunks += 1
        return {"case_note": "stream", "wall_s": round(wall, 3),
                "first_content_s": round(first_at, 3) if first_at else None,
                "usage": usage}
    d = json.loads(raw)
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    usage = d.get("usage") or {}
    return {"wall_s": round(wall, 3), "usage": usage,
            "content_chars": len(content), "reasoning_chars": len(reasoning),
            "finish": ch.get("finish_reason"),
            "tool_calls": [t.get("function", {}).get("name") for t in (msg.get("tool_calls") or [])],
            "content_head": content[:60].replace("\n", "\\n"),
            "reasoning_head": reasoning[:60].replace("\n", "\\n"), "note": note}


def templates():
    import ast
    tpl = {}
    tree = ast.parse((APP_ROOT / "app/agents/orchestrator.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "DOC_PROMPT":
                tpl["DOC_PROMPT"] = node.value.value
            elif node.targets[0].id == "MAIN_SYSTEM":
                tpl["MAIN_SYSTEM"] = next(kw.value.value for kw in node.value.keywords if kw.arg == "content")
    tree = ast.parse((APP_ROOT / "app/rag/retrieval_pipeline.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "REWRITE_PROMPT":
            tpl["REWRITE_PROMPT"] = node.value.value
    return tpl

def tool(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}


def _load_rounds_probe():
    """Load ``scripts/perf_probe_rounds.py`` for its read-only-ast route to the product's
    content cap. This probe runs either as ``python scripts/perf_probe_prodpath.py`` (repo
    checkout) or piped into the container via ``docker exec ... python -`` (no ``__file__``,
    app source under APP_ROOT), so both layouts are tried before giving up.
    """
    import importlib.util

    candidates = []
    try:
        candidates.append(pathlib.Path(__file__).with_name("perf_probe_rounds.py"))
    except NameError:  # pragma: no cover - stdin mode has no __file__
        pass
    candidates.append(APP_ROOT / "scripts" / "perf_probe_rounds.py")
    candidates.append(pathlib.Path("scripts/perf_probe_rounds.py"))
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("eb_perf_probe_rounds", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise RuntimeError(
        "cannot locate scripts/perf_probe_rounds.py in any of %s" % [str(p) for p in candidates]
    )


def doc_content_cap():
    """Per-hit content cap, taken from ``perf_probe_rounds.doc_content_cap()`` -- the only
    route in this repo that reads DOC_HIT_CONTENT_CHARS off the product source with `ast`.

    R116 (跟进单 §57 追加 1): this file used to hand-copy the per-hit cap as a literal
    five-hundred. A missing or unreadable truth source is a HARD FAIL here -- the probe
    never falls back to a number of its own.
    """
    try:
        rounds = _load_rounds_probe()
        cap = rounds.doc_content_cap(APP_ROOT)
    except Exception as exc:  # noqa: BLE001 - re-raised with the reason, never swallowed
        raise RuntimeError("content cap truth source is unreachable: %r" % (exc,)) from exc
    if not isinstance(cap, int) or cap <= 0:
        raise RuntimeError("doc_content_cap() returned %r, not a positive int" % (cap,))
    return cap


def cn_text(target_chars):
    s = ["经销商逾期超过六十天的，系统自动冻结新货发运，需经区域总监与销售运营双签方可解除。",
         "信用额度依据上一年度实际回款表现核定，最高不超过年度采购额的百分之四十。",
         "季度末最后一笔回款以到账日为准，在途资金不计入当季度考核口径。"]
    out, total, idx = [], 0, 1
    while total < target_chars:
        line = "%04d. " % idx + s[(idx - 1) % len(s)]
        out.append(line)
        total += len(line)
        idx += 1
    return "\n".join(out)[:target_chars]


def main():
    tpl = templates()
    q = QUESTION
    emit({"case": "templates", "ok": True, "chars": {k: len(v) for k, v in tpl.items()}})
    dispatch_tool = tool("dispatch", "派发任务给专业子Agent并行处理。workers可选值: doc 文档搜索; data 数据分析; chart 图表生成; export 报告导出。",
                         {"workers": {"type": "array", "items": {"type": "string"}}}, ["workers"])
    search_tool = tool("search_docs", "搜索公司内部文档知识库。用于查找：公司制度、报销流程、请假规定、产品规格、技术架构、客户案例、定价策略、安全规范、操作手册等所有文档类信息。",
                       {"query": {"type": "string"}}, ["query"])
    cap = doc_content_cap()  # R116: 真源读数，读不到就地硬失败，不再手抄 500
    tool_text = "[1] 来源:demo-policy.md 相关度:未评分\n" + cn_text(cap)
    nonce = ANSWER_MARK % uuid.uuid4().hex[:10]

    r = v1([{"role": "user", "content": nonce + tpl["MAIN_SYSTEM"]}, {"role": "user", "content": q}],
           tools=[dispatch_tool], note="Supervisor 决策，产品真实端点")
    emit(dict(case="v1_supervisor", **r))

    r = v1([{"role": "user", "content": nonce + tpl["REWRITE_PROMPT"].format(question=q)}],
           note="查询改写，产品真实端点 stream=False", max_tokens=300)
    emit(dict(case="v1_query_rewrite", **r))

    msgs = [{"role": "system", "content": nonce + tpl["DOC_PROMPT"]},
            {"role": "user", "content": q},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "search_docs", "arguments": json.dumps({"query": "经销商 回款周期"}, ensure_ascii=False)}}]},
            {"role": "tool", "tool_call_id": "call_1", "name": "search_docs", "content": tool_text}]
    r = v1(msgs, tools=[search_tool], note="doc worker 生成轮（1 条命中），非流式")
    emit(dict(case="v1_doc_react_2", **r))
    r = v1(msgs, tools=[search_tool], stream=True, note="同一 prompt 走流式，量真实首字时间")
    emit(dict(case="v1_doc_react_2_stream", **r))
    return 0


if __name__ == "__main__":
    sys.exit(main())