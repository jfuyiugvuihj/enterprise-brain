"""
短期记忆 —— 上下文自动压缩（补计划优化 #1）

长对话超过阈值时，把旧历史压成一条摘要 SystemMessage，
只保留 摘要 + 最近 N 条，避免 token 爆炸。
"""
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.common.logger import logger

THRESHOLD = 20   # 超过 20 条触发压缩
KEEP = 8         # 保留最近 8 条


def _to_text(m) -> str:
    role = "用户" if isinstance(m, HumanMessage) else "AI"
    content = getattr(m, "content", "") or ""
    return f"{role}: {content[:200]}"


def summarize(messages: list, model) -> str:
    """把一组消息压缩成摘要文本"""
    lines = "\n".join(_to_text(m) for m in messages if getattr(m, "content", None))
    if not lines:
        return ""
    prompt = (
        "把下面的对话压缩成一段简洁摘要，保留关键事实（用户问过什么、得到什么结论、"
        "涉及哪些数据/文档）。只输出摘要，不要其他内容。\n\n" + lines
    )
    try:
        resp = model.invoke([HumanMessage(content=prompt)])
        return resp.content or ""
    except Exception as e:
        logger.warning(f"[Summarizer] 摘要失败: {e}")
        return ""


def compress_messages(messages: list, model) -> list:
    """超阈值时压缩旧历史，返回 [摘要SystemMessage] + 最近 KEEP 条"""
    if len(messages) <= THRESHOLD:
        return messages

    older = messages[:-KEEP]
    recent = messages[-KEEP:]
    summary = summarize(older, model)
    if not summary:
        return messages  # 摘要失败不压缩，保底

    logger.info(f"[Summarizer] 压缩 {len(older)} 条历史 → 摘要")
    return [SystemMessage(content=f"【历史摘要】{summary}")] + recent
