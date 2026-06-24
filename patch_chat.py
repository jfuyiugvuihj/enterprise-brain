"""Replace generate functions in chat.py with async versions"""
path = r'C:\Users\fengx\PycharmProjects\企业智脑\app\api\v1\chat.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ====== Replace /ask generate ======
old_ask = """    async def generate():
        from app.agents.orchestrator import run_with_stream

        result_queue: qmod.Queue = qmod.Queue()

        def _run():
            try:
                for event in run_with_stream(rewritten_msg, thread_id=thread_id):
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _run)"""

new_ask = """    async def generate():
        from app.agents.orchestrator import run_with_stream"""

# Replace thread pool with async for start
if old_ask in content:
    content = content.replace(old_ask, new_ask)
    print("Replaced ask generate start")
else:
    print("WARNING: ask generate start not found!")

# Replace while+queue loop with async for
old_loop = """        while True:
            try:
                kind, data = result_queue.get_nowait()
            except qmod.Empty:
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
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
                        yield f"event: hitl\\ndata: {json.dumps({'type': 'hitl', 'pending': intr['pending'], 'labels': intr['labels']}, ensure_ascii=False)}\\n\\n"
                        await asyncio.sleep(0)
                except Exception:
                    pass

                yield f"event: done\\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {data}")
                if not saved:
                    _save_message(thread_id, "assistant", f"[错误] {data}")
                yield f"event: error\\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
                break

            ns = ()"""

new_loop = """        try:
            async for event in run_with_stream(rewritten_msg, thread_id=thread_id):
                ns = ()"""

if old_loop in content:
    content = content.replace(old_loop, new_loop)
    print("Replaced while loop with async for")
else:
    print("WARNING: while loop not found!")

# Replace tuple unwrapping
old_tuple = """            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue"""

new_tuple = """            if isinstance(event, tuple):
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
                yield f"event: error\\ndata: {json.dumps({'type': 'error', 'content': data['error']}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
                break
            if ns and ns != ("",):
                continue"""

if old_tuple in content:
    content = content.replace(old_tuple, new_tuple)
    print("Replaced tuple unwrapping")
else:
    print("WARNING: tuple unwrap not found!")

# Replace end of generate (before ApproveRequest)
old_end = """                        break

    return StreamingResponse(generate(), media_type="text/event-stream")


class ApproveRequest"""

new_end = """                        break

        # async for completed
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
                yield f"event: hitl\\ndata: {json.dumps({'type': 'hitl', 'pending': intr['pending'], 'labels': intr['labels']}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
        except Exception:
            pass

        yield f"event: done\\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\\n\\n"
        await asyncio.sleep(0)

    except Exception as e:
        logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {e}")
        if not saved:
            _save_message(thread_id, "assistant", f"[错误] {e}")
        yield f"event: error\\ndata: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\\n\\n"
        await asyncio.sleep(0)

    return StreamingResponse(generate(), media_type="text/event-stream")


class ApproveRequest"""

if old_end in content:
    content = content.replace(old_end, new_end)
    print("Replaced generate end")
else:
    print("WARNING: generate end not found!")

# ====== Replace /approve generate ======
old_app = """    async def generate():
        from app.agents.orchestrator import run_interrupt_stream

        result_queue: qmod.Queue = qmod.Queue()

        def _run():
            try:
                for event in run_interrupt_stream(request.session_id, approved=request.approved):
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _run)"""

new_app = """    async def generate():
        from app.agents.orchestrator import run_interrupt_stream"""

if old_app in content:
    content = content.replace(old_app, new_app)
    print("Replaced approve generate start")
else:
    print("WARNING: approve generate start not found!")

# Replace approve while loop
old_app_loop = """        while True:
            try:
                kind, data = result_queue.get_nowait()
            except qmod.Empty:
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
                full_text = "".join(ai_reply)
                _save_message(request.session_id, "assistant", full_text)
                yield f"event: done\\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                yield f"event: error\\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\\n\\n"
                await asyncio.sleep(0)
                break

            ns = ()"""

new_app_loop = """        try:
            async for event in run_interrupt_stream(request.session_id, approved=request.approved):
                ns = ()"""

if old_app_loop in content:
    content = content.replace(old_app_loop, new_app_loop)
    print("Replaced approve while loop")
else:
    print("WARNING: approve while loop not found!")

# Replace approve tuple unwrap
old_app_tuple = """            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue

            msgs"""

new_app_tuple = """            if isinstance(event, tuple):
                ns = event[0] if len(event) > 1 else ()
                data = event[1] if len(event) > 1 else event[0]
            else:
                data = event
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue

            msgs"""

if old_app_tuple in content:
    content = content.replace(old_app_tuple, new_app_tuple)
    print("Replaced approve tuple unwrap")
else:
    print("WARNING: approve tuple not found!")

# Replace approve end
old_app_end = """                    break

    return StreamingResponse(generate(), media_type="text/event-stream")


# ==================== 会话管理 API ===================="""

new_app_end = """                    break

            full_text = "".join(ai_reply)
            _save_message(request.session_id, "assistant", full_text)
            yield f"event: done\\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\\n\\n"
            await asyncio.sleep(0)

        except Exception as e:
            yield f"event: error\\ndata: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\\n\\n"
            await asyncio.sleep(0)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ==================== 会话管理 API ===================="""

if old_app_end in content:
    content = content.replace(old_app_end, new_app_end)
    print("Replaced approve end")
else:
    print("WARNING: approve end not found!")

# Remove unused qmod import
content = content.replace('import queue as qmod\n', '')
content = content.replace('import queue as qmod\r\n', '')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("\nDone - chat.py patched for async")
