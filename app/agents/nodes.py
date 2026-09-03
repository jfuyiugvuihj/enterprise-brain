"""
阶段 1 · 新图各节点逻辑

节点：classify_intent / respond / load_memory / plan / reflect / synthesize
共享模型工厂 _make_model 也放这里，避免 orchestrator 循环依赖。
"""
import os
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import Runnable

from app.common.logger import logger
from app.memory import recall, remember
from app.memory.profile import compose_profile_context, get_profile


class _OfflineModel(Runnable):
    def bind_tools(self, tools):
        return self

    def invoke(self, messages, **kwargs):
        text = ""
        for msg in reversed(messages or []):
            content = getattr(msg, "content", None)
            if content is None and isinstance(msg, dict):
                content = msg.get("content", "")
            if content:
                text = str(content)
                break
        if "报销" in text or "流程" in text:
            content = "公司报销流程一般包括提交申请、部门审批、财务复核和付款归档。离线模式下我先给你这个通用版本。"
        elif "利润" in text or "门店" in text or "分析" in text:
            content = "离线模式下可先按门店利润、营收和成本三项做排序，再进一步看利润率和同比环比变化。"
        else:
            content = "离线模式已启用，但我仍可以继续帮你梳理问题、拆解任务，并给出可执行的下一步建议。"
        return AIMessage(content=content)

    def stream(self, *args, **kwargs):
        yield type("Chunk", (), {"choices": [type("Choice", (), {"delta": type("Delta", (), {"content": "离线模式已启用"})()})()]})()


def _make_model(timeout: int = 60):
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return _OfflineModel()
    try:
        return ChatOpenAI(
            base_url="https://api.deepseek.com",
            api_key=api_key,
            model="deepseek-chat",
            temperature=0,
            max_retries=2,
            request_timeout=timeout,
        )
    except Exception as exc:
        logger.warning(f"[Model] 回退到离线模式: {exc}")
        return _OfflineModel()


def _last_user(state) -> str:
    for m in reversed(state.get("messages", [])):
        if type(m).__name__ == "HumanMessage":
            return getattr(m, "content", "") or ""
    return ""


# ==================== 意图分类（确定性，不调 LLM） ====================

_SMALLTALK = ["你好", "您好", "在吗", "谢谢", "感谢", "再见", "拜拜",
              "你是谁", "你叫什么", "hello", "hi", "早上好", "晚上好"]


def classify_intent(state) -> dict:
    """规则分类：chat(闲聊) / task(任务)。快、稳、可解释。"""
    q = _last_user(state).strip()
    ql = q.lower()
    if any(k in ql for k in _SMALLTALK) and len(q) <= 12:
        intent = "chat"
    else:
        intent = "task"
    logger.info(f"[Classify] '{q[:30]}' → {intent}")
    return {"intent": intent}


def respond(state) -> dict:
    """闲聊直接回答，不走 worker"""
    q = _last_user(state)
    try:
        resp = _make_model(timeout=30).invoke([HumanMessage(content=q)])
        text = resp.content or "你好，我是企业智脑，可以帮你查文档、分析数据、画图、导出报告。"
    except Exception:
        text = "你好，我是企业智脑，可以帮你查文档、分析数据、画图、导出报告。"
    return {"final_answer": text, "messages": [AIMessage(content=text)]}


# ==================== 记忆加载 ====================

def load_memory(state) -> dict:
    """召回长期记忆注入 state"""
    user_id = state.get("user_id") or "default"
    q = _last_user(state)
    long_mem = recall(user_id, q, k=3) if q else []
    profile = get_profile(
        user_id,
        fallback={
            "department": state.get("department") or "",
            "role": state.get("role") or "",
        },
    )
    profile_context = compose_profile_context(profile)
    logger.info(f"[LoadMemory] user={user_id} 召回 {len(long_mem)} 条")
    return {"memory": {"long": long_mem, "work": [], "profile": profile, "profile_context": profile_context}}


# ==================== 任务规划（仅复杂问题） ====================

_COMPLEX = ["和", "并且", "同时", "另外", "还有", "以及", "然后"]


def plan(state) -> dict:
    """复杂问题拆子任务；简单问题返回空列表"""
    q = _last_user(state)
    if not any(k in q for k in _COMPLEX):
        return {"plan": []}
    prompt = (
        "把下面的复合问题拆成 2-4 个独立子任务，返回 JSON 数组（只输出数组）：\n"
        f"{q}"
    )
    try:
        import json
        resp = _make_model(timeout=30).invoke([HumanMessage(content=prompt)])
        arr = json.loads(str(resp.content).strip().removeprefix("```json").removesuffix("```"))
        plan_list = arr if isinstance(arr, list) else []
    except Exception as e:
        logger.warning(f"[Plan] 拆解失败: {e}")
        plan_list = []
    logger.info(f"[Plan] {len(plan_list)} 个子任务")
    return {"plan": plan_list}


# ==================== 反思 ====================

def reflect_node(state) -> dict:
    """检查最终回答质量，决定重派(redo)或放行"""
    q = _last_user(state)
    final = ""
    for m in reversed(state.get("messages", [])):
        if type(m).__name__ == "AIMessage" and getattr(m, "content", "") and not getattr(m, "tool_calls", None):
            final = m.content
            break

    redo = False
    if not final or len(final) < 5:
        redo = True
    elif any(bad in final for bad in ["失败", "错误", "无法", "抱歉"]):
        redo = True
    elif any(k in q for k in ["图", "图表", "柱状", "折线", "饼图"]) and "![" not in final:
        redo = True   # 要图却没图
    elif any(k in q for k in ["导出", "报告", "PDF", "pdf"]) and "下载" not in final:
        redo = True   # 要导出却没下载链接

    count = state.get("reflect_count", 0) + (1 if redo else 0)
    logger.info(f"[Reflect] redo={redo} count={count}")
    return {"redo": redo, "reflect_count": count}


def route_reflect(state) -> str:
    """redo 且未超重派上限 → 回 supervisor；否则 → synthesize"""
    if state.get("redo") and state.get("reflect_count", 0) <= 1:
        return "supervisor"
    return "synthesize"


# ==================== 汇总 + 沉淀 ====================

def synthesize(state) -> dict:
    """把最终回答写入 state，并把值得记的沉淀进长期记忆"""
    q = _last_user(state)
    final = state.get("final_answer") or ""
    if not final:
        for m in reversed(state.get("messages", [])):
            if type(m).__name__ == "AIMessage" and getattr(m, "content", "") and not getattr(m, "tool_calls", None):
                final = m.content
                break

    if state.get("intent") == "task" and q and final:
        user_id = state.get("user_id") or "default"
        remember(user_id, f"问: {q[:60]} → 答: {final[:80]}")

    return {"final_answer": final}
