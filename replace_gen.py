"""Replace both generate functions with async versions"""
import re

path = r'C:\Users\fengx\PycharmProjects\企业智脑\app\api\v1\chat.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the two generate functions
# 1. Ask endpoint's generate (between @router.post("/ask") and class ApproveRequest)
ask_idx = content.find('async def generate():')
approve_class_idx = content.find('\n\nclass ApproveRequest')

# Find the SECOND async def generate (inside ask)
second_gen = content.find('async def generate():', content.find('@router.post("/ask")'))
# Find where approve endpoint's generate ends
approve_gen_start = content.find('async def generate():', content.find('@router.post("/approve")'))
sessions_start = content.find('# ==================== 会话管理', approve_gen_start)

print(f"Ask generate: {second_gen}")
print(f"Approve class: {approve_class_idx}")
print(f"Approve generate: {approve_gen_start}")
print(f"Sessions: {sessions_start}")

# Ask generate clean version
ask_gen = """    async def generate():
        from app.agents.orchestrator import run_with_stream

        yield f"event: status\\ndata: " + json.dumps({"type": "status", "content": "🔍 正在分析您的问题..."}, ensure_ascii=False) + "\\n\\n"
        await asyncio.sleep(0)

        start_time = time.time()
        steps_log = []
        ai_full_reply = []
        saved = False
        last_workers = []
        last_completed = set()
        emitted_running = set()
        emitted_done = set()
        initial_msg_count = -1
        initial_worker_results = {}

        try:
            async for event in run_with_stream(rewritten_msg, thread_id=thread_id):
                ns = ()
                if isinstance(event, tuple):
                    ns = event[0] if len(event) > 1 else ()
                    data = event[1] if len(event) > 1 else event[0]
                else:
                    data = event

                if not isinstance(data, dict):
                    continue
                if "error" in data:
                    logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {data['error']}")
                    if not saved:
                        _save_message(thread_id, "assistant", f"[错误] {data['error']}")
                    yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": data["error"]}, ensure_ascii=False) + "\\n\\n"
                    await asyncio.sleep(0)
                    break
                if ns and ns != ("",):
                    continue

                msgs = data.get("messages", [])
                worker_results = data.get("worker_results", {})

                dispatched = []
                for msg in msgs:
                    tools = getattr(msg, "tool_calls", None) or []
                    for tc in tools:
                        if tc["name"] == "dispatch":
                            dispatched = tc["args"].get("workers", [])
                            break
                    if dispatched:
                        break

                if dispatched:
                    user_msg = ""
                    for m in reversed(msgs):
                        if type(m).__name__ == "HumanMessage":
                            user_msg = getattr(m, "content", "") or ""
                            break
                    chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
                    export_kw = ["导出", "PDF", "pdf", "报告", "下载"]
                    data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
                    if any(kw in user_msg for kw in chart_kw):
                        dispatched = ["chart"]
                    elif any(kw in user_msg for kw in export_kw) and not any(kw in user_msg for kw in chart_kw):
                        dispatched = ["export"]
                    elif any(kw in user_msg for kw in data_kw) and "chart" not in dispatched:
                        if "data" not in dispatched:
                            dispatched = ["data"]

                if dispatched and dispatched != last_workers:
                    for w in dispatched:
                        if w not in emitted_running:
                            emitted_running.add(w)
                            labels = {"doc": "📄 搜索知识库", "data": "📊 分析数据",
                                      "chart": "📈 生成图表", "export": "📋 导出报告"}
                            label = labels.get(w, f"🔧 {w}")
                            steps_log.append({"tool": w, "label": label, "status": "running", "elapsed": None})
                            yield f"event: step\\ndata: " + json.dumps({"type": "step", "tool": w, "label": label, "status": "running"}, ensure_ascii=False) + "\\n\\n"
                            await asyncio.sleep(0)

                if not initial_worker_results:
                    initial_worker_results = dict(worker_results)
                for w in worker_results:
                    is_new = w not in initial_worker_results
                    is_changed = w in initial_worker_results and worker_results[w] != initial_worker_results[w]
                    if w not in emitted_done and (is_new or is_changed):
                        emitted_done.add(w)
                        elapsed = round(time.time() - start_time, 1)
                        for s in steps_log:
                            if s["tool"] == w and s["status"] == "running":
                                s["status"] = "done"
                                s["elapsed"] = elapsed
                                yield f"event: step\\ndata: " + json.dumps({"type": "step", "tool": w, "label": s["label"], "status": "done", "elapsed": elapsed}, ensure_ascii=False) + "\\n\\n"
                                await asyncio.sleep(0)

                last_workers = dispatched

                if initial_msg_count < 0:
                    initial_msg_count = len(msgs)
                pending = [w for w in last_workers if w not in worker_results]
                if not pending:
                    for idx in range(len(msgs) - 1, initial_msg_count - 1, -1):
                        msg = msgs[idx]
                        msg_type = type(msg).__name__
                        content = getattr(msg, "content", "") or ""
                        has_tools = getattr(msg, "tool_calls", None)
                        if msg_type == "AIMessage" and content and not has_tools:
                            if content.startswith("【") and "Agent 返回】" in content[:50]:
                                continue
                            if content not in ai_full_reply:
                                ai_full_reply.append(content)
                                yield f"event: text\\ndata: " + json.dumps({"type": "text", "content": content}, ensure_ascii=False) + "\\n\\n"
                                await asyncio.sleep(0)
                            break

            elapsed_total = round(time.time() - start_time, 1)
            full_text = "".join(ai_full_reply)
            _save_message(thread_id, "assistant", full_text, steps_log)
            saved = True
            if full_text:
                from app.common.cache import cache_answer
                cache_answer(rewritten_msg, full_text)
            logger.info(f"[ASK] session={thread_id[:8]}... {elapsed_total}s | steps={len(steps_log)}")

            try:
                from app.agents.orchestrator import check_interrupt
                intr = check_interrupt(thread_id)
                if intr:
                    yield f"event: hitl\\ndata: " + json.dumps({"type": "hitl", "pending": intr["pending"], "labels": intr["labels"]}, ensure_ascii=False) + "\\n\\n"
                    await asyncio.sleep(0)
            except Exception:
                pass

            yield f"event: done\\ndata: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {e}")
            if not saved:
                _save_message(thread_id, "assistant", f"[错误] {e}")
            yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

"""

# Approve generate clean version
app_gen = """    async def generate():
        from app.agents.orchestrator import run_interrupt_stream

        ai_reply = []
        initial_count = -1

        try:
            async for event in run_interrupt_stream(request.session_id, approved=request.approved):
                ns = ()
                if isinstance(event, tuple):
                    ns = event[0] if len(event) > 1 else ()
                    data = event[1] if len(event) > 1 else event[0]
                else:
                    data = event

                if not isinstance(data, dict):
                    continue
                if ns and ns != ("",):
                    continue

                msgs = data.get("messages", [])
                if initial_count < 0:
                    initial_count = len(msgs)

                for idx in range(len(msgs) - 1, initial_count - 1, -1):
                    msg = msgs[idx]
                    msg_type = type(msg).__name__
                    content = getattr(msg, "content", "") or ""
                    has_tools = getattr(msg, "tool_calls", None)
                    if msg_type == "AIMessage" and content and not has_tools:
                        if content.startswith("【") and "Agent 返回】" in content[:50]:
                            continue
                        if content not in ai_reply:
                            ai_reply.append(content)
                            yield f"event: text\\ndata: " + json.dumps({"type": "text", "content": content}, ensure_ascii=False) + "\\n\\n"
                            await asyncio.sleep(0)
                        break

            full_text = "".join(ai_reply)
            _save_message(request.session_id, "assistant", full_text)
            yield f"event: done\\ndata: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

        except Exception as e:
            yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

"""

# Replace ask generate (from second_gen to approve_class_idx)
before = content[:second_gen]
after_ask = content[approve_class_idx:]
content = before + ask_gen + '\n' + after_ask

# Now replace approve generate
# Find new positions after first replacement
approve_gen_start2 = content.find('async def generate():', content.find('@router.post("/approve")'))
sessions_start2 = content.find('# ==================== 会话管理', approve_gen_start2)

before_app = content[:approve_gen_start2]
after_app = content[sessions_start2:]
content = before_app + app_gen + '\n' + after_app

# Remove unused qmod import
content = content.replace('import queue as qmod\n', '')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Both generate functions replaced with async versions")
