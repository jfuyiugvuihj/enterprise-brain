"""Migrate chat.py from thread pool to async for"""
path = r'C:\Users\fengx\PycharmProjects\企业智脑\app\api\v1\chat.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
in_ask_gen = False
in_approve_gen = False
gen_count = 0
skip_until_done = False

i = 0
while i < len(lines):
    line = lines[i]

    # Detect generate functions
    if 'async def generate():' in line:
        gen_count += 1
        if gen_count == 2:  # ask endpoint
            new_lines.append(line)  # keep async def generate():
            new_lines.append('        from app.agents.orchestrator import run_with_stream\n')
            new_lines.append('\n')
            new_lines.append('        yield f"event: status\\ndata: " + json.dumps({"type": "status", "content": "\\U0001f50d 正在分析您的问题..."}, ensure_ascii=False) + "\\n\\n"\n')
            new_lines.append('        await asyncio.sleep(0)\n')
            new_lines.append('\n')
            # Skip old thread pool setup, jump to state vars
            in_ask_gen = True
            # Find the next occurrence of start_time
            while i < len(lines) and 'start_time = time.time()' not in lines[i]:
                i += 1
            continue
        elif gen_count == 3:  # approve endpoint
            new_lines.append(line)
            new_lines.append('        from app.agents.orchestrator import run_interrupt_stream\n')
            new_lines.append('\n')
            new_lines.append('        ai_reply = []\n')
            new_lines.append('        initial_count = -1\n')
            new_lines.append('\n')
            in_approve_gen = True
            # Find start of try block
            while i < len(lines) and ('ai_reply' not in lines[i] and 'initial_count' not in lines[i]):
                i += 1
            i += 3  # skip past ai_reply and initial_count and empty line
            # Add try + async for
            new_lines.append('        try:\n')
            new_lines.append('            async for event in run_interrupt_stream(request.session_id, approved=request.approved):\n')
            continue

    if in_ask_gen:
        # Skip old thread pool + while loop, until we hit the first 'ns = ()'
        if 'start_time = time.time()' in line:
            new_lines.append(line)
            i += 1
            continue
        # Keep state variable declarations
        if any(kw in line for kw in ['steps_log', 'ai_full_reply', 'saved =', 'last_workers', 'last_completed',
                'emitted_running', 'emitted_done', 'initial_msg_count', 'initial_worker']):
            new_lines.append(line)
            i += 1
            continue
        # When we hit the try: block, replace with async for
        if line.strip() == 'try:' and 'while True' in lines[i+1] if i+1 < len(lines) else False:
            new_lines.append('        try:\n')
            new_lines.append('            async for event in run_with_stream(rewritten_msg, thread_id=thread_id):\n')
            # Skip ahead to the 'ns = ()' line
            while i < len(lines) and 'ns = ()' not in lines[i]:
                i += 1
            # Add event unwrapping
            new_lines.append('                ns = ()\n')
            new_lines.append('                if isinstance(event, tuple):\n')
            new_lines.append('                    ns = event[0] if len(event) > 1 else ()\n')
            new_lines.append('                    data = event[1] if len(event) > 1 else event[0]\n')
            new_lines.append('                else:\n')
            new_lines.append('                    data = event\n')
            new_lines.append('\n')
            # Skip old tuple unwrapping + dict check
            i += 1
            while i < len(lines) and 'not isinstance(data, dict)' not in lines[i]:
                i += 1
            i += 1  # skip dict check
            while i < len(lines) and lines[i].strip().startswith('continue'):
                i += 1
            i += 1  # skip 'if ns and ns !='
            while i < len(lines) and lines[i].strip().startswith('continue'):
                i += 1
            # Add error check + ns filter
            new_lines.append('                if not isinstance(data, dict):\n')
            new_lines.append('                    continue\n')
            new_lines.append('                if "error" in data:\n')
            new_lines.append('                    logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {data[\'error\']}")\n')
            new_lines.append('                    if not saved:\n')
            new_lines.append('                        _save_message(thread_id, "assistant", f"[\\u9519\\u8bef] {data[\'error\']}")\n')
            new_lines.append('                    yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": data["error"]}, ensure_ascii=False) + "\\n\\n"\n')
            new_lines.append('                    await asyncio.sleep(0)\n')
            new_lines.append('                    break\n')
            new_lines.append('                if ns and ns != ("",):\n')
            new_lines.append('                    continue\n')
            new_lines.append('\n')
            continue
        # When we hit the done handler inside while, skip until we see 'msgs = data.get'
        if 'kind == "done"' in line:
            while i < len(lines) and 'msgs = data.get("messages"' not in lines[i]:
                i += 1
            new_lines.append(lines[i])  # msgs line
            i += 1
            new_lines.append(lines[i])  # worker_results line
            i += 1
            continue
        if 'kind == "error"' in line:
            while i < len(lines) and 'msgs = data.get("messages"' not in lines[i]:
                i += 1
            continue
        # Copy remaining event processing lines unchanged
        if 'msgs = data.get' not in line and 'worker_results = data.get' not in line:
            new_lines.append(line)
        i += 1
        # Check if we've reached end of generate
        if 'return StreamingResponse' in line and 'generate()' in line:
            # Add done handling before return
            done_handler = '''        # async for done
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
            _save_message(thread_id, "assistant", f"[\\u9519\\u8bef] {e}")
        yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False) + "\\n\\n"
        await asyncio.sleep(0)

'''
            new_lines.append(done_handler)
            in_ask_gen = False
        continue

    if in_approve_gen:
        # Similar handling for approve
        if 'try:' in line.strip() and any('async for' in l for l in new_lines[-3:]):
            i += 1
            continue
        # Copy until we see old while loop pattern
        if 'while True:' in line:
            i += 5  # skip while, try, except, await, continue patterns
            continue
        if 'kind == "done"' in line or 'kind == "error"' in line:
            while i < len(lines) and 'msgs' not in lines[i]:
                i += 1
            continue
        new_lines.append(line)
        i += 1
        if 'return StreamingResponse' in line:
            # Add async done handling
            approve_done = '''            full_text = "".join(ai_reply)
            _save_message(request.session_id, "assistant", full_text)
            yield f"event: done\\ndata: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

        except Exception as e:
            yield f"event: error\\ndata: " + json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False) + "\\n\\n"
            await asyncio.sleep(0)

'''
            new_lines.append(approve_done)
            in_approve_gen = False
        continue

    new_lines.append(line)
    i += 1

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('done')
