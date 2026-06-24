"""
Chat API — Multi-Agent SSE 流式 / 文档上传 / 会话管理 (PostgreSQL 持久化)
"""
import os
import re
import json
import time
import uuid
import queue as qmod
import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, Request as FastAPIRequest
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.rag.loader import load_document
from app.rag.retriever import DocumentRetriever
from app.common.model_handler import ModelHandler, ModelSource
from app.common.logger import logger

router = APIRouter()
retriever = DocumentRetriever()
model_handler = ModelHandler()

DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

_tz = timezone(timedelta(hours=8))

# ==================== PostgreSQL 会话存储 ====================

import psycopg
from psycopg.rows import dict_row

_PG_URL = os.getenv("DATABASE_URL", "postgresql://fengx@localhost:5432/enterprise_brain")


def _sess_conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _ensure_session(session_id: str) -> dict:
    now = datetime.now(_tz).isoformat()
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (%s, '', %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (session_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()
        return dict(row) if row else {"id": session_id, "title": "", "created_at": now, "updated_at": now}


def _save_message(session_id: str, role: str, content: str, steps: list | None = None):
    now = datetime.now(_tz).isoformat()
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content, steps, created_at) VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, json.dumps(steps or [], ensure_ascii=False), now),
        )
        if role == "user":
            title = content[:30]
            conn.execute(
                "UPDATE sessions SET title = %s, updated_at = %s WHERE id = %s AND title = ''",
                (title, now, session_id),
            )
        conn.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (now, session_id))
        conn.commit()


def _list_sessions() -> list[dict]:
    with _sess_conn() as conn:
        rows = conn.execute(
            """SELECT s.*,
               (SELECT COUNT(*) FROM session_messages WHERE session_id = s.id AND role = 'user') as msg_count
               FROM sessions s ORDER BY s.updated_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def _get_session_messages(session_id: str) -> list[dict]:
    with _sess_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, steps, created_at FROM session_messages WHERE session_id = %s ORDER BY id",
            (session_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["steps"] = json.loads(d["steps"])
        except (json.JSONDecodeError, TypeError):
            d["steps"] = []
        result.append(d)
    return result


def _delete_session(session_id: str):
    with _sess_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()


# ==================== 追问改写 ====================

def _rewrite_followup(session_id: str, user_msg: str) -> str:
    triggers = ["那", "它", "这个", "那个", "他们", "换", "改成"]
    if not any(user_msg.startswith(t) for t in triggers):
        return user_msg

    msgs = _get_session_messages(session_id)
    prev_user = [m["content"] for m in msgs if m["role"] == "user"]
    if not prev_user:
        return user_msg

    try:
        prompt = f"""把追问改写为完整独立问题。结合上文语境。

上一问: {prev_user[-1]}
当前: {user_msg}

只输出改写后的问题:"""
        result = model_handler.chat(
            messages=[{"role": "user", "content": prompt}],
            source=ModelSource.DEEPSEEK,
            stream=False,
        )
        rewritten = result.strip() if isinstance(result, str) else result.choices[0].message.content.strip()
        if rewritten and len(rewritten) > 3:
            logger.info(f"[REWRITE] '{user_msg}' → '{rewritten[:60]}'")
            return rewritten
    except Exception as e:
        logger.warning(f"[REWRITE] 失败: {e}")

    return user_msg


# ==================== Pydantic ====================

class ChatRequest(BaseModel):
    message: str
    model_source: str = "deepseek"


class AskRequest(BaseModel):
    message: str
    session_id: str = ""


# ==================== 旧版 Chat（保留兼容） ====================

@router.post("/chat")
async def chat(request: ChatRequest):
    async def generate():
        try:
            sources = retriever.search(request.message, k=5)
            context = "\n\n".join(
                f"[来源: {s['source']}]\n{s['content']}" for s in sources
            ) if sources else "暂无相关文档"

            prompt = f"""你是一个企业智能助手。参考以下文档内容回答用户问题。

## 参考文档
{context}

## 用户问题
{request.message}

## 要求
- 如果文档包含相关信息，明确引用来源
- 如果文档不包含相关信息，如实告知并给出建议"""

            source_enum = ModelSource.DEEPSEEK if request.model_source == "deepseek" else ModelSource.OLLAMA
            stream = model_handler.chat(
                messages=[{"role": "user", "content": prompt}],
                source=source_enum,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"\n[错误] {str(e)}"

    return StreamingResponse(generate(), media_type="text/plain")


# ==================== Multi-Agent Ask (SSE) ====================

@router.post("/ask")
async def ask(request: AskRequest, http_request: FastAPIRequest = None):
    thread_id = request.session_id or uuid.uuid4().hex
    _ensure_session(thread_id)
    _save_message(thread_id, "user", request.message)

    original_msg = request.message
    rewritten_msg = _rewrite_followup(thread_id, original_msg)

    # ——— 限流检查 ———
    from app.common.cache import check_rate_limit
    username = getattr(http_request.state if http_request else None, "username", None) or "anonymous"
    allowed, remaining = check_rate_limit(username, max_per_minute=10)
    if not allowed:
        async def rate_limited():
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'content': '请求太频繁，请稍后再试（每分钟最多10次）'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        return StreamingResponse(rate_limited(), media_type="text/event-stream")

    # ——— 答案缓存 ———
    from app.common.cache import get_cached_answer
    cached = get_cached_answer(rewritten_msg)
    if cached:
        _save_message(thread_id, "assistant", cached)
        async def cached_response():
            yield f"event: status\ndata: {json.dumps({'type': 'status', 'content': '📋 缓存命中，直接返回'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': cached}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        return StreamingResponse(cached_response(), media_type="text/event-stream")

    async def generate():
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
        loop.run_in_executor(None, _run)

        yield f"event: status\ndata: {json.dumps({'type': 'status', 'content': '🔍 正在分析您的问题...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)

        start_time = time.time()
        steps_log: list[dict] = []
        ai_full_reply: list[str] = []
        saved = False
        last_workers: list[str] = []
        last_completed: set[str] = set()
        emitted_running: set[str] = set()
        emitted_done: set[str] = set()
        initial_msg_count = -1
        initial_worker_results: dict = {}

        while True:
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
                        yield f"event: hitl\ndata: {json.dumps({'type': 'hitl', 'pending': intr['pending'], 'labels': intr['labels']}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                except Exception:
                    pass

                yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {data}")
                if not saved:
                    _save_message(thread_id, "assistant", f"[错误] {data}")
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            ns = ()
            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue

            msgs = data.get("messages", [])
            worker_results = data.get("worker_results", {})

            dispatched: list[str] = []
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
                        yield f"event: step\ndata: {json.dumps({'type': 'step', 'tool': w, 'label': label, 'status': 'running'}, ensure_ascii=False)}\n\n"
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
                            yield f"event: step\ndata: {json.dumps({'type': 'step', 'tool': w, 'label': s['label'], 'status': 'done', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
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
                            yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0)
                        break

    return StreamingResponse(generate(), media_type="text/event-stream")


class ApproveRequest(BaseModel):
    session_id: str
    approved: bool = True


@router.post("/approve")
async def approve(request: ApproveRequest):
    async def generate():
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
        loop.run_in_executor(None, _run)

        ai_reply: list[str] = []
        initial_count = -1

        while True:
            try:
                kind, data = result_queue.get_nowait()
            except qmod.Empty:
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
                full_text = "".join(ai_reply)
                _save_message(request.session_id, "assistant", full_text)
                yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            ns = ()
            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
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
                        yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                    break

    return StreamingResponse(generate(), media_type="text/event-stream")


# ==================== 会话管理 API ====================

@router.get("/sessions")
async def list_sessions():
    return {"sessions": _list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    msgs = _get_session_messages(session_id)
    with _sess_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()
    return {
        "session": dict(row) if row else None,
        "messages": msgs,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    _delete_session(session_id)
    try:
        from app.agents.orchestrator import clear_session
        clear_session(session_id)
    except Exception:
        pass
    return {"status": "ok"}


# ==================== 文档管理 ====================

@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    file_path = os.path.join(DOCUMENTS_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    content = load_document(file_path)
    ok, msg = retriever.add_document(file.filename, content)
    return {"filename": file.filename, "status": "ok" if ok else "skipped", "message": msg}


@router.get("/documents")
async def list_documents():
    docs = retriever.list_documents()
    return {"documents": docs}


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    retriever.delete_document(filename)
    file_path = os.path.join(DOCUMENTS_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    return {"status": "ok", "filename": filename}
