"""
阶段 1 · LangGraph 强类型状态定义

把旧版弱类型 `AgentState(dict)` 升级为 TypedDict：
- 每个字段含义明确
- 需要并行合并的字段用 reducer（add_messages / _merge_dicts）
- 普通字段默认"后者覆盖"
"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


def _merge_dicts(a: dict, b: dict) -> dict:
    """并行 worker 写 worker_results 时的合并 reducer"""
    return {**a, **b}


def _last_wins(a, b):
    """普通字段：后写覆盖"""
    return b


class AgentState(TypedDict, total=False):
    # 短期记忆：当前对话（LangGraph 消息流，自动追加）
    messages: Annotated[list, add_messages]

    # classify_intent 输出：chat(闲聊) / task(任务)
    intent: str

    # 当前用户（长期记忆按 user 隔离）
    user_id: str

    # load_memory 注入：{"long": [...], "work": [...]}
    memory: dict

    # plan 节点拆解出的子任务列表（仅复杂问题）
    plan: list

    # 并行 worker 的结果：{worker_name: result_text}，用 _merge_dicts 合并
    worker_results: Annotated[dict, _merge_dicts]

    # reflect 已重派次数（最多 1 次，防死循环）
    reflect_count: int

    # reflect 判定：是否需要重派（True→回 supervisor，False→synthesize）
    redo: bool

    # synthesize 产出的最终回答
    final_answer: str
