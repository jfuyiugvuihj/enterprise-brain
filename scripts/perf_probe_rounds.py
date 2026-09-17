r"""W8 perf probe #2: per-step prompt size of the real /ask chain.

No instrumentation is added to product code. This probe re-derives each step's message
body the same way the code builds it, then sends it to Ollama's NATIVE /api/chat, which
is the only endpoint that reports prompt_eval_count / eval_count (the product itself
calls the OpenAI-compatible /v1 endpoint, whose response carries no token stats).

Templates are extracted from the product source with `ast` (read-only) so nothing is
transcribed by hand and the probe cannot silently drift from the code under test.

    cd C:/Users/fengx/PycharmProjects/perf-lab
    cmd /c "docker exec -i enterprise-brain-backend-1 python - < scripts/perf_probe_rounds.py"

Steps reproduced (mapped onto the 160.6s request in docs/perf/latency-budget-2026-09-16.md):
  supervisor_decide  orchestrator.main_agent_node  -> invoke([MAIN_SYSTEM+mem, user])
  doc_react_1        create_react_agent(doc_graph) -> tool-selection round trip
  query_rewrite      retrieval_pipeline.QueryRewriter.rewrite
  doc_react_2        second round trip, retrieved chunks inside the tool message
  supervisor_report  main_agent_node again, same 2 messages -> duplicate round trip
"""
import argparse
import ast
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid

OLLAMA = "http://ollama:11434"
MODEL = "qwen3.5:9b"
TIMEOUT = 900
APP_ROOT = pathlib.Path("/app")
QUESTION = "我们经销商的标准回款周期是多少天？超期多久会停发新货？"
SENTENCES = [
    "经销商年度回款周期按自然季度考核，逾期三十天以内记为轻微违约并书面提示。",
    "逾期超过三十天未满六十天的，暂停新客户授信并缩减下季度返点结算比例。",
    "逾期超过六十天的，系统自动冻结新货发运，需经区域总监与销售运营双签方可解除。",
    "信用额度依据上一年度实际回款表现核定，最高不超过年度采购额的百分之四十。",
    "客户以银行承兑汇票回款的，贴现费用由双方按合同约定比例分担。",
    "季度末最后一笔回款以到账日为准，在途资金不计入当季度考核口径。",
    "连续两个季度评级为 C 的经销商，纳入淘汰观察名单并缩短账期至三十天。",
    "大客户专项备货需单独申请临时额度，审批通过后有效期不超过四十五天。",
    "对账差异应在收到对账单后十个工作日内书面提出，逾期视同认可。",
]


def cn_text(target_chars):
    out, total, idx = [], 0, 1
    while total < target_chars:
        line = "%04d. " % idx + SENTENCES[(idx - 1) % len(SENTENCES)]
        out.append(line)
        total += len(line)
        idx += 1
    body = "\n".join(out)
    return body[:target_chars] if len(body) > target_chars else body


def _literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _arg_of(call, kwname):
    """The product calls HumanMessage(content=...) with a KEYWORD arg, so
    node.value.args is empty and a positional read silently misses the template."""
    if isinstance(call, ast.Call):
        if call.args:
            return call.args[0]
        for kw in call.keywords:
            if kw.arg == kwname:
                return kw.value
    return call


def load_templates():
    """Pull the real prompt strings out of the product source without importing it."""
    tpl = {}
    tree = ast.parse((APP_ROOT / "app/agents/orchestrator.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else ""
            if name == "DOC_PROMPT":
                tpl["DOC_PROMPT"] = _literal(node.value)
            elif name == "MAIN_SYSTEM":
                tpl["MAIN_SYSTEM"] = _literal(_arg_of(node.value, "content"))
        if isinstance(node, ast.FunctionDef) and node.name == "dispatch":
            tpl["DISPATCH_DOC"] = ast.get_docstring(node) or ""
    tree = ast.parse((APP_ROOT / "app/rag/retrieval_pipeline.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == "REWRITE_PROMPT":
                tpl["REWRITE_PROMPT"] = _literal(node.value)
    tree = ast.parse((APP_ROOT / "app/agents/tools.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "search_docs":
            tpl["SEARCH_DOCS_DOC"] = ast.get_docstring(node) or ""
    return tpl


def tool_schema(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


def api(payload):
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def emit(row):
    print("JSONL " + json.dumps(row, ensure_ascii=False), flush=True)
    return row

def measure(case, messages, tools=None, num_predict=400, note="", nonce=True):
    """One faithful round trip. nonce defeats Ollama's prompt-prefix cache, which
    otherwise reports an impossible rate for corpora sharing a leading prefix."""
    msgs = [dict(m) for m in messages]
    if nonce and msgs:
        tag = "【请求校验码 %s】\n" % uuid.uuid4().hex[:12]
        first = msgs[0]
        first["content"] = tag + (first.get("content") or "")
    body = {"model": MODEL, "stream": False,
            "options": {"temperature": 0, "num_predict": num_predict}, "messages": msgs}
    if tools:
        body["tools"] = tools
    started = time.monotonic()
    try:
        resp = api(body)
    except urllib.error.HTTPError as exc:
        return emit({"case": case, "ok": False, "note": note, "case_note": "http_%s" % exc.code,
                     "detail": exc.read().decode("utf-8", "replace")[:200]})
    except Exception as exc:  # noqa: BLE001
        return emit({"case": case, "ok": False, "note": note, "case_note": repr(exc)[:200]})
    ped = (resp.get("prompt_eval_duration", 0) or 0) / 1e9
    evd = (resp.get("eval_duration", 0) or 0) / 1e9
    pe = resp.get("prompt_eval_count", 0) or 0
    ev = resp.get("eval_count", 0) or 0
    msg = resp.get("message") or {}
    content = msg.get("content") or resp.get("content") or ""
    thinking = msg.get("thinking") or resp.get("thinking") or ""
    tcs = msg.get("tool_calls") or resp.get("tool_calls") or []
    return emit({"case": case, "ok": True, "note": note,
                 "prompt_chars": sum(len(m.get("content") or "") for m in msgs),
                 "prompt_eval_count": pe, "eval_count": ev,
                 "prefill_s": round(ped, 3), "decode_s": round(evd, 3),
                 "total_s": round((resp.get("total_duration", 0) or 0) / 1e9, 3),
                 "wall_s": round(time.monotonic() - started, 3),
                 "prefill_tps": round(pe / ped, 2) if ped > 0.05 else None,
                 "decode_tps": round(ev / evd, 2) if evd > 0.05 else None,
                 "answer_chars": len(content), "thinking_chars": len(thinking),
                 "tool_calls": [t.get("function", {}).get("name") for t in tcs],
                 "answer_head": (content or json.dumps(tcs, ensure_ascii=False))[:70].replace("\n", "\\n")})


def tool_result_text(hits):
    """Reproduce tools.search_docs' return shape: each chunk capped at 500 chars."""
    parts = []
    for i, (source, content) in enumerate(hits, 1):
        parts.append("[%d] 来源:%s 相关度:%s\n%s" % (i, source, "未评分", content[:500]))
    return "\n\n---\n\n".join(parts)


def real_chunk_text(max_chars=500):
    """Read the chunk text tonight KB actually holds, straight off the read-only
    documents dir. Tonight that is ONE file of 116 chars, which is why a synthetic
    500-char chunk overstates the real generation prompt by ~4x."""
    parts = []
    for path in sorted((APP_ROOT / "documents").glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        parts.append((path.name, text[:max_chars]))
    return parts or [("demo-policy.md", cn_text(116))]


def memory_ctx(mem_lines=3):
    """main_agent_node appends 【用户历史记忆】/【用户画像】 to MAIN_SYSTEM. synthesize
    writes each remembered line as 问: q[:60] -> 答: final[:80], so ~145 chars each."""
    lines = ["问: %s → 答: %s" % (cn_text(60), cn_text(80)) for _ in range(mem_lines)]
    return "\n\n【用户历史记忆】\n" + "\n".join("- " + m for m in lines) + "\n\n【用户画像】\n部门: 销售运营\n岗位: 渠道经理"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    q = args.question
    only = set(x.strip() for x in args.only.split(",") if x.strip())

    def want(name):
        return not only or name in only

    tpl = load_templates()
    emit({"case": "templates", "ok": True, "chars": {k: len(v or "") for k, v in tpl.items()}})
    try:
        emit({"case": "runtime", "ok": True,
              "loaded": [{"name": m["name"], "context_length": m.get("context_length")}
                         for m in api("/api/ps").get("models", [])]})
    except Exception as exc:  # noqa: BLE001
        emit({"case": "runtime", "ok": False, "case_note": repr(exc)[:200]})

    dispatch_tool = tool_schema(
        "dispatch", tpl["DISPATCH_DOC"],
        {"workers": {"type": "array", "items": {"type": "string"},
                     "description": "子Agent名称列表，可选 doc / data / chart / export"}},
        ["workers"])
    search_tool = tool_schema(
        "search_docs", tpl["SEARCH_DOCS_DOC"],
        {"query": {"type": "string", "description": "检索关键词或问题"}}, ["query"])

    if want("supervisor_decide"):
        measure("supervisor_decide", [{"role": "user", "content": tpl["MAIN_SYSTEM"]},
                                      {"role": "user", "content": q}],
                tools=[dispatch_tool], note="调度决策第1发，无记忆注入（最短形态）")
        measure("supervisor_decide_mem", [{"role": "user", "content": tpl["MAIN_SYSTEM"] + memory_ctx()},
                                          {"role": "user", "content": q}],
                tools=[dispatch_tool], note="调度决策第1发，注入 3 条长期记忆+画像（今晚 admin 账号的真实形态）")
    if want("doc_react_1"):
        measure("doc_react_1", [{"role": "system", "content": tpl["DOC_PROMPT"]},
                               {"role": "user", "content": q}],
                tools=[search_tool], note="doc worker 决定调用 search_docs 的第 1 个往返")
    if want("query_rewrite"):
        measure("query_rewrite", [{"role": "user", "content": tpl["REWRITE_PROMPT"].format(question=q)}],
                num_predict=400, note="多路查询改写，产品用 stream=False 但同样占 1 个并发槽")
    tonight = tool_result_text([("经销商信用政策.pdf", cn_text(500))])
    customer = tool_result_text([("经销商信用政策.pdf", cn_text(500)) for _ in range(5)])
    if want("doc_react_2_kbreal"):
        real = real_chunk_text()
        measure("doc_react_2_kbreal", [
            {"role": "system", "content": tpl["DOC_PROMPT"]},
            {"role": "user", "content": q},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "search_docs", "arguments": {"query": "经销商 回款周期 停发新货"}}}]},
            {"role": "tool", "content": tool_result_text(real)},
        ], tools=[search_tool], num_predict=800,
           note="今晚真实口径：直接读 /app/documents 里的 %d 个 md（%d 字），search_docs 截 500 字"
                % (len(real), sum(len(c) for _, c in real)))
    if want("doc_react_2"):
        for label, payload, note in (
            ("doc_react_2_kb1", tonight, "今晚口径：知识库 1 篇 1 块，检索返回 1 条"),
            ("doc_react_2_kb5", customer, "客户规模口径：top_k=5 全部命中，每条 500 字上限"),
        ):
            if not want(label):
                continue
            measure(label, [
                {"role": "system", "content": tpl["DOC_PROMPT"]},
                {"role": "user", "content": q},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "search_docs", "arguments": {"query": "经销商 回款周期 停发新货"}}}]},
                {"role": "tool", "content": payload},
            ], tools=[search_tool], num_predict=800, note=note + "；assistant+tool 轮按 ReAct 真实结构重建")
    if want("supervisor_report"):
        measure("supervisor_report", [{"role": "user", "content": tpl["MAIN_SYSTEM"] + memory_ctx()},
                                      {"role": "user", "content": q}],
                tools=[dispatch_tool], note="worker 回来后 main_agent_node 再次执行；代码只传 [sys, current_user]，与第 1 发同形")
    if want("plan_llm"):
        measure("plan_llm", [{"role": "user", "content":
                              "把下面的复合问题拆成 2-4 个独立子任务，返回 JSON 数组（只输出数组）：\n" + q}],
                num_predict=400, note="nodes.plan 的非确定性分支；今晚走确定性计划未触发，仅作上限参考")
    return 0


if __name__ == "__main__":
    sys.exit(main())