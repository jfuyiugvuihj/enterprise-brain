# -*- coding: utf-8 -*-
"""B25 判据：模型不可用时兜底那一发，屏上不许出现整段原始材料。

形状是 10-08 撤下演练真跑出来的：装箱把窗口顶穿 -> 服务端 500 -> ``_ResilientModel``
回退到 :class:`app.agents.nodes._OfflineModel`，它把本轮最后一条 ``ToolMessage`` 原样包成
``AIMessage`` 交出去 -> 屏上落 12,476 字检索原文（读数 ``%TEMP%\evalrun\r7revert`` 环 7）。
客户读到的是料堆：既没有人整理，也不说模型坏了，还被当成这个答案落进缓存。

三格全是屏幕现象：
1. 失败当场说破——那一格的开头一句就点名「本轮模型不可用」。
2. 不许堆料——交出去的字符数有上限，超出部分写明「余下多少字未显示」。
3. 小段原文照常送到屏上（``tests/test_offline_runtime_fallbacks.py`` 钉的「住宿费标准为
   500元」那一格就是这个判据的来源，砍掉它等于把有用的那一半也扔了）。
"""

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import nodes


def _material(chars: int) -> str:
    """与现场同形的料：工具交回来的检索原文，带出处行与正文段。

    尾巴是一枚唯一的句子：样本正文由重复段落拼成，拿「尾 200 字」去判「整段有没有上屏」
    会被中间那段咬住，所以钉一枚只出现在末尾的标记。
    """
    unit = "1.1.2 迟到与早退 每月累计迟到不超过 3 次且每次不超过 15 分钟，不计入考勤异常。\n"
    head = "企业管理制度手册.txt | 第 2 段 | 相关度 0 | 密级 1 级 | 生效 2026-09-22\n"
    tail = "本文件其余段落未纳入本轮装箱。"
    body = (head + unit * (chars // len(unit) + 1))[:chars - len(tail)]
    return body + tail


def _fallback_text(tool_content: str, question: str = "上半年报销情况怎么样") -> str:
    model = nodes._OfflineModel().bind_tools(
        [type("SearchTool", (), {"name": "search_docs"})()]
    )
    return model.invoke([
        HumanMessage(content=question),
        ToolMessage(content=tool_content, tool_call_id="call-b25"),
    ]).content


def test_a_long_tool_output_never_reaches_the_screen_verbatim():
    raw = _material(11716)
    text = _fallback_text(raw)

    assert nodes.is_offline_reply_text(text), (
        "兜底交回的那一格不被认成离线话术：它会被当成答案落进缓存，",
        f"一次模型故障回放半小时（{len(text)} 字）",
    )
    assert len(text) <= nodes.OFFLINE_TOOL_OUTPUT_MAX_CHARS + 200, (
        f"屏上落了 {len(text)} 字：材料没被限住"
    )
    assert "本轮模型不可用" in text.splitlines()[0], (
        "开头第一句没点名模型不可用：客户读到的仍像一份真答案"
    )
    assert "未显示" in text, "没写明还有多少字没上屏"


def test_the_head_of_the_material_is_still_handed_over():
    raw = _material(11716)
    text = _fallback_text(raw)

    assert raw[:40] in text, "限住之后连已经查到的头一小段都不给了"
    assert raw[-200:] not in text, "整段材料还是原样上了屏"


def test_a_short_tool_output_still_reaches_the_screen():
    text = _fallback_text("住宿费标准为500元", question="住宿费标准是多少")

    assert "500" in text, "有用的那一半被砍掉了"
    assert "本轮模型不可用" in text.splitlines()[0], "短句那一格同样要说破"


def test_blank_material_is_not_pasted_as_an_empty_block():
    text = _fallback_text("   ", question="差旅报销要走哪几道审批")

    assert not text.startswith(nodes.OFFLINE_TOOL_OUTPUT_LEAD), (
        "空的工具输出也被包成「已查到的原文」：屏上是一句光杆话"
    )
