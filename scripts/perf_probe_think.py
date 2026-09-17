r"""W8 perf probe #5: can the product turn the hidden reasoning off, and what does it save?

Probe #4 proved the product's own endpoint (/v1/chat/completions) returns
`reasoning` text that the UI never shows, while `usage.completion_tokens` charges the
request for it. This probe finds a working "no thinking" switch on the OpenAI-compatible
endpoint and measures the saving, because that is a one-request-option change rather
than a model swap.

It also reads `usage.prompt_tokens_details.cached_tokens`, which is the only honest way
to tell whether a prefill number was inflated by Ollama's prefix cache.

    cd C:/Users/fengx/PycharmProjects/perf-lab
    cmd /c "docker exec -i enterprise-brain-backend-1 python - < scripts/perf_probe_think.py"
"""
import json
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid

V1 = "http://ollama:11434/v1/chat/completions"
MODEL = "qwen3.5:9b"
Q = "我们经销商的标准回款周期是多少天？超期多久会停发新货？"
DOC_PROMPT = "你是文档搜索专家。搜公司知识库回答问题。一次想好几个搜索方向，同时搜多个关键词，避免来回。返回完整准确结果并引用来源文件名。"
CHUNK = "# 2026 年华东区渠道政策要点\n\n## 回款周期\n2026 年华东区经销商的标准回款周期为 47 天,超期 15 天起停发新货。\n\n## 折扣上限\n单笔订单折扣不得超过成交价 12%,超出需渠道总监书面审批。"
SEARCH_TOOL = {"type": "function", "function": {
    "name": "search_docs",
    "description": "搜索公司内部文档知识库。用于查找：公司制度、报销流程、请假规定、产品规格、技术架构、客户案例、定价策略、安全规范、操作手册等所有文档类信息。",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}


def emit(row):
    print("JSONL " + json.dumps(row, ensure_ascii=False), flush=True)


def post(extra, messages, tools=None, timeout=600):
    body = {"model": MODEL, "messages": messages, "temperature": 0,
            "max_tokens": 400, "stream": False}
    body.update(extra)
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(V1, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http": exc.code,
                "detail": exc.read().decode("utf-8", "replace")[:160],
                "wall_s": round(time.monotonic() - started, 3)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "case_note": repr(exc)[:160],
                "wall_s": round(time.monotonic() - started, 3)}
    wall = time.monotonic() - started
    msg = (d.get("choices") or [{}])[0].get("message") or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    u = d.get("usage") or {}
    pt = u.get("prompt_tokens") or 0
    ct = u.get("completion_tokens") or 0
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    return {"ok": True, "wall_s": round(wall, 3), "prompt_tokens": pt, "completion_tokens": ct,
            "cached_tokens": cached, "content_chars": len(content), "reasoning_chars": len(reasoning),
            "finish": (d.get("choices") or [{}])[0].get("finish_reason"),
            "tool_calls": [t.get("function", {}).get("name") for t in (msg.get("tool_calls") or [])],
            "tps_incl_thinking": round(ct / wall, 2) if wall else None,
            "content_head": content[:50].replace("\n", "\\n")}


def gen_messages(nonce):
    """The generation round trip as the doc worker really sees it tonight:
    1 chunk of 116 chars from the single demo policy doc."""
    return [{"role": "system", "content": "【请求校验码 %s】\n" % nonce + DOC_PROMPT},
            {"role": "user", "content": Q},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {
                    "name": "search_docs",
                    "arguments": json.dumps({"query": "经销商 回款周期 停发新货"}, ensure_ascii=False)}}]},
            {"role": "tool", "tool_call_id": "call_1", "name": "search_docs",
             "content": "[1] 来源:demo-policy.md 相关度:未评分\n" + CHUNK}]


VARIANTS = [
    ("as_product_no_option", {}, "产品现状：不带任何 think 参数"),
    ("top_level_think_false", {"think": False}, "顶层 think:false（Ollama 扩展）"),
    ("openai_thinking_disabled", {"thinking": {"type": "disabled"}}, "OpenAI 风格 thinking:{type:disabled}"),
    ("options_think_false", {"options": {"think": False}}, "options.think:false"),
    ("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}}, "chat_template_kwargs"),
]


def main():
    print("# probe_start %s" % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    for name, extra, note in VARIANTS:
        row = post(extra, gen_messages(uuid.uuid4().hex[:10]), tools=[SEARCH_TOOL])
        row["case"] = "variant_%s" % name
        row["note"] = note
        emit(row)
    # repeat the accepted winner twice: reasoning-off changes total time, so take 2 samples
    for i in range(2):
        for name, extra, note in VARIANTS[:2]:
            row = post(extra, gen_messages(uuid.uuid4().hex[:10]), tools=[SEARCH_TOOL])
            row["case"] = "repeat%d_%s" % (i, name)
            row["note"] = note
            emit(row)
    print("# probe_end %s" % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())