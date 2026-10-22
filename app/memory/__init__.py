"""
企业智脑 · 三层记忆统一接口

- 短期：summarizer.trim_history（确定性历史裁剪，零模型 · R33）
- 长期：long_term.remember / recall（PostgreSQL 持久化）
- 工作：复用 long_term.recall 语义召回历史问答
"""
from app.memory.summarizer import compress_messages, trim_history


def remember(*args, **kwargs):
    from app.memory.long_term import remember as _remember

    return _remember(*args, **kwargs)


def recall(*args, **kwargs):
    from app.memory.long_term import recall as _recall

    return _recall(*args, **kwargs)


__all__ = ["remember", "recall", "compress_messages", "trim_history"]
