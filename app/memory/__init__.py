"""
企业智脑 · 三层记忆统一接口

- 短期：summarizer.compress_messages（上下文压缩）
- 长期：long_term.remember / recall（PostgreSQL 持久化）
- 工作：复用 long_term.recall 语义召回历史问答
"""
from app.memory.long_term import remember, recall
from app.memory.summarizer import compress_messages

__all__ = ["remember", "recall", "compress_messages"]
