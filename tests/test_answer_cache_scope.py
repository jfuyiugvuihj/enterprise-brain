"""R35：答案缓存的作用域门槛与淘汰策略。

判据对应关系：
- 判据①（多轮会话内重复问题命中 + 可区分标记）：
  ``test_repeat_question_inside_a_session_hits_cache_and_is_labelled``
- 判据②（跨部门/跨密级命中 0 条，P0）：
  ``test_same_question_never_hits_across_authorization_inputs`` 七组参数化 +
  ``test_department_change_invalidates_the_owners_own_cache_through_ask``（走 /ask 接线取证）
- 判据③（淘汰策略可测，且内存回退路径生效）：
  ``test_cache_answer_ttl_expires_on_the_memory_fallback`` /
  ``test_capacity_eviction_bounds_the_memory_fallback`` /
  ``test_capacity_eviction_is_least_recently_used`` /
  ``test_expire_is_not_a_noop_on_the_memory_fallback`` / ``test_answer_cache_ttl_is_configurable``
- 判据⑤（无 session_id 的兼容路径行为不变）：
  ``test_no_session_path_still_consults_writes_and_hits_the_cache`` /
  ``test_hit_frames_keep_the_pre_r35_shape``
- 附带（不可信/陈旧记录不回读，限流未回归）：
  ``test_legacy_bare_string_record_is_not_served`` / ``test_rate_limit_still_works_after_the_rewrite``

全程离线：不打模型、不连真 Redis；缓存层用 app/common/cache.py 自己的内存回退实现，
也就是 REDIS_URL 未设时生产上真正会走的那条路径。
"""
import asyncio
import json
import time

import pytest

QUESTION = "差旅费报销的住宿费标准是多少？"
ANSWER = "一线城市住宿费 500 元/晚，按发票实报。"
OTHER_ANSWER = "这一轮真实生成的另一份答案。"


def principal_for(user_id="u1", department="finance", clearance=2, roles=("staff",), **kwargs):
    """只带授权输入维度的构造器：作用域应当完全由这些字段决定。"""
    from app.agents.contracts import Principal

    permissions = list(kwargs.pop("permissions", ["document:read"]))
    department_ids = list(kwargs.pop("department_ids", []))
    status = kwargs.pop("status", "active")
    assert not kwargs, f"未预期的构造参数: {sorted(kwargs)}"
    return Principal(
        user_id=user_id,
        username=user_id,
        roles=list(roles),
        permissions=permissions,
        department=department,
        department_ids=department_ids,
        clearance=clearance,
        clearance_label=f"L{clearance}",
        status=status,
    )


# 每组都是"同一问题文本、同一账号，只换一个授权维度"。刻意共用同一个 user_id：
# 若作用域只到用户号（改动前就是这样），这几组全会互相命中，判据②就是漏权的。
CROSS_SCOPE_CASES = {
    "换部门": ({"department": "finance"}, {"department": "hr"}),
    "换密级": ({"clearance": 2}, {"clearance": 3}),
    "administrator 对 staff": ({"roles": ["staff"]}, {"roles": ["administrator"]}),
    "账号无部门": ({"department": "finance"}, {"department": ""}),
    "换 owner": ({"user_id": "alice"}, {"user_id": "carol"}),
    "兼任部门不同": ({"department_ids": ["finance"]}, {"department_ids": ["hr"]}),
    "权限集合不同": ({"permissions": ["document:read"]}, {"permissions": ["document:read", "data:read"]}),
}


def _memory_cache(monkeypatch, max_entries=None):
    """把缓存层换成内存回退实现：REDIS_URL 未设时生产上跑的就是这一套。"""
    from app.common import cache

    backend = cache._MemoryRedis(max_entries=max_entries) if max_entries else cache._MemoryRedis()
    monkeypatch.setattr(cache, "_redis", backend)
    return backend


@pytest.mark.parametrize("label", list(CROSS_SCOPE_CASES))
def test_same_question_never_hits_across_authorization_inputs(monkeypatch, label):
    from app.common import cache

    _memory_cache(monkeypatch)
    writer_attrs, reader_attrs = CROSS_SCOPE_CASES[label]
    writer = principal_for(**writer_attrs)
    reader = principal_for(**reader_attrs)
    assert cache.answer_cache_scope(writer) != cache.answer_cache_scope(reader), label

    cache.cache_answer(QUESTION, ANSWER, scope=cache.answer_cache_scope(writer))

    # 判据②：越权方向 0 命中。
    assert cache.get_cached_answer(QUESTION, scope=cache.answer_cache_scope(reader)) is None
    # 反向对照：本人同作用域必须命中，否则上面那条"0 命中"是靠谁都查不到刷出来的假绿。
    assert cache.get_cached_answer(QUESTION, scope=cache.answer_cache_scope(writer)) == ANSWER


def test_cache_answer_ttl_expires_on_the_memory_fallback(monkeypatch):
    from app.common import cache

    backend = _memory_cache(monkeypatch)
    scope = cache.answer_cache_scope(principal_for())
    cache.cache_answer(QUESTION, ANSWER, scope=scope, ttl=1)
    # 改动前 setex 把 TTL 参数丢掉，这条断言当时必然为假（后端根本没记有效期）。
    assert backend._expires_at, "TTL 没有落到后端：内存回退路径依旧永不过期"
    assert cache.get_cached_answer(QUESTION, scope=scope) == ANSWER
    time.sleep(1.1)
    assert cache.get_cached_answer(QUESTION, scope=scope) is None


def test_answer_cache_ttl_is_configurable(monkeypatch):
    from app.common import cache

    monkeypatch.setenv("ANSWER_CACHE_TTL_SECONDS", "7")
    backend = _memory_cache(monkeypatch)
    cache.cache_answer(QUESTION, ANSWER, scope=cache.answer_cache_scope(principal_for()))
    assert len(backend._expires_at) == 1
    deadline = next(iter(backend._expires_at.values()))
    assert time.time() < deadline <= time.time() + 8


def test_capacity_eviction_bounds_the_memory_fallback(monkeypatch):
    from app.common import cache

    backend = _memory_cache(monkeypatch, max_entries=3)
    scope = cache.answer_cache_scope(principal_for())
    for i in range(6):
        cache.cache_answer(f"{QUESTION}{i}", f"答案{i}", scope=scope)
    assert len(backend._kv) <= 3
    assert cache.get_cached_answer(f"{QUESTION}5", scope=scope) == "答案5"
    assert cache.get_cached_answer(f"{QUESTION}0", scope=scope) is None
    # 淘汰是"少用的先死"，不是"全都死"：最近写过的那几条仍然读得回来。
    assert cache.get_cached_answer(f"{QUESTION}4", scope=scope) == "答案4"


def test_capacity_eviction_is_least_recently_used():
    from app.common import cache

    backend = cache._MemoryRedis(max_entries=2)
    backend.setex("a", 60, "1")
    backend.setex("b", 60, "2")
    assert backend.get("a") == "1"  # 读一次 = 把 a 挪回"最近使用"
    backend.setex("c", 60, "3")
    assert backend.get("a") == "1"
    assert backend.get("b") is None
    assert backend.get("c") == "3"


def test_expire_is_not_a_noop_on_the_memory_fallback():
    from app.common import cache

    backend = cache._MemoryRedis()
    backend.setex("answer:x", 600, "v")
    assert backend.expire("answer:x", 1) is True
    assert backend.get("answer:x") == "v"
    time.sleep(1.1)
    assert backend.get("answer:x") is None


def test_legacy_bare_string_record_is_not_served(monkeypatch):
    """旧版本在同一个键上存过裸字符串：说不清生成时间就无法标注，一律不回读。"""
    from app.common import cache

    backend = _memory_cache(monkeypatch)
    scope = cache.answer_cache_scope(principal_for())
    backend.setex(cache._answer_key(QUESTION, scope), 600, ANSWER)
    assert cache.get_cached_answer(QUESTION, scope=scope) is None
    assert cache.get_cached_answer_record(QUESTION, scope=scope) is None


def test_rate_limit_still_works_after_the_rewrite(monkeypatch):
    from app.common import cache

    _memory_cache(monkeypatch)
    assert cache.check_rate_limit("alice", max_per_minute=2)[0] is True
    assert cache.check_rate_limit("alice", max_per_minute=2)[0] is True
    assert cache.check_rate_limit("alice", max_per_minute=2) == (False, 0)


def test_dead_islands_are_gone():
    """四座孤岛按判据②删除，不留半套实现。"""
    from app.common import cache

    for name in (
        "cache_dispatch",
        "get_cached_dispatch",
        "cache_semantic_answer",
        "get_semantic_cached_answer",
        "clear_semantic_cache",
    ):
        assert not hasattr(cache, name), name
    assert not hasattr(cache, "_SEMANTIC_CACHE")


# --------------------------------------------------------------------------
# /ask 接线取证：判据①（会话内命中 + 标记）与判据⑤（无会话路径不变）。
# --------------------------------------------------------------------------

def _ask_harness(monkeypatch, tmp_path, answers):
    """把 /ask 挂到一个假 orchestrator 上：answers 每被取走一次就等于打了一次模型。"""
    from app.api.v1 import chat
    from app.storage.sessions import SessionRegistry

    _memory_cache(monkeypatch)
    remaining = list(answers)

    def fake_stream(*_args, **_kwargs):
        answer = remaining.pop(0)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    async def consume(response):
        chunks = [chunk async for chunk in response.body_iterator]
        return "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
        )

    def ask(principal, message=QUESTION, session_id=""):
        http_request = type(
            "Request",
            (),
            {"state": type("State", (), {"principal": principal, "username": principal.username})()},
        )()
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=http_request,
            )
        )
        return asyncio.run(consume(response))

    return ask, remaining


def _final_text_payload(body):
    payloads = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in body.split("\n\n")
        if frame.startswith("event: text")
    ]
    assert payloads, f"响应里没有 text 事件：{body!r}"
    return payloads[-1]


def _event_names(body):
    return [frame.split("\n", 1)[0].removeprefix("event: ") for frame in body.split("\n\n") if frame]


def test_repeat_question_inside_a_session_hits_cache_and_is_labelled(monkeypatch, tmp_path):
    """判据①：带 session_id 的多轮对话里重复提问必须命中，且响应体标得出它是缓存。"""
    ask, remaining = _ask_harness(monkeypatch, tmp_path, [ANSWER, OTHER_ANSWER])
    caller = principal_for(user_id="alice", department="finance")

    first = ask(caller, session_id="sess-1")
    assert ANSWER in first and OTHER_ANSWER not in first
    assert remaining == [OTHER_ANSWER], "第一轮应当且只应当生成一次"
    assert "cached" not in _final_text_payload(first), "未命中的那一轮不许带缓存标记"

    second = ask(caller, session_id="sess-1")
    assert remaining == [OTHER_ANSWER], "会话内重复问题必须命中缓存，不许再生成一次"
    assert OTHER_ANSWER not in second
    payload = _final_text_payload(second)
    assert payload["content"] == ANSWER
    assert payload["cached"] is True
    assert payload["cache_note"].startswith("缓存结果 · 生成于")
    assert time.strftime("%Y-%m-%d", time.localtime()) in payload["cache_note"]
    generated_at = payload["cache_generated_at"]
    assert generated_at[:4].isdigit() and "T" in generated_at


def test_interleaved_turns_in_one_session_still_hit_their_own_question(monkeypatch, tmp_path):
    """判据①的多轮形态：Q1、Q2、再问 Q1 —— 第二次 Q1 命中自己的那条，不串到 Q2。"""
    first_answer = "一线城市住宿费 500 元/晚。"
    second_answer = "培训费走年度预算，不需单笔审批。"
    ask, remaining = _ask_harness(
        monkeypatch, tmp_path, [first_answer, second_answer, "多轮里绝不该被用到的答案"]
    )
    caller = principal_for(user_id="alice", department="finance")
    session = "sess-multi"
    q1 = "住宿费标准是多少？"
    q2 = "培训费怎么审批？"
    assert first_answer in ask(caller, message=q1, session_id=session)
    assert second_answer in ask(caller, message=q2, session_id=session)

    body = ask(caller, message=q1, session_id=session)
    assert remaining == ["多轮里绝不该被用到的答案"], "第三轮应当命中缓存，不打模型"
    assert first_answer in body and second_answer not in body
    payload = _final_text_payload(body)
    assert payload["cached"] is True
    assert payload["content"] == first_answer


def test_department_change_invalidates_the_owners_own_cache_through_ask(monkeypatch, tmp_path):
    """判据②接线证据：同一账号换了部门，问题文本一字不变，也不能读回旧部门那一条。"""
    ask, remaining = _ask_harness(monkeypatch, tmp_path, [ANSWER, OTHER_ANSWER])
    finance_alice = principal_for(user_id="alice", department="finance")
    hr_alice = principal_for(user_id="alice", department="hr")

    assert ANSWER in ask(finance_alice, session_id="sess-finance")
    body = ask(hr_alice, session_id="sess-hr")
    assert remaining == [], "换部门必须重新生成一次"
    assert ANSWER not in body, "换部门后读回了旧部门权限下的答案"
    assert OTHER_ANSWER in body
    assert _final_text_payload(body).get("cached") is not True


def test_no_session_path_still_consults_writes_and_hits_the_cache(monkeypatch, tmp_path):
    """判据⑤：session_id 为空的兼容路径，查/写/命中三件事与改动前一致。"""
    ask, remaining = _ask_harness(monkeypatch, tmp_path, [ANSWER, OTHER_ANSWER])
    caller = principal_for(user_id="alice", department="finance")

    assert ANSWER in ask(caller, session_id="")
    assert remaining == [OTHER_ANSWER]

    body = ask(caller, session_id="")
    assert remaining == [OTHER_ANSWER], "无会话路径第二次调用应当仍然命中缓存"
    assert ANSWER in body and OTHER_ANSWER not in body
    assert _final_text_payload(body)["cached"] is True


def test_hit_frames_keep_the_pre_r35_shape(monkeypatch, tmp_path):
    """判据⑤：命中时的三个事件、顺序与原有文案逐字不变，标记只是附加字段。"""
    ask, _remaining = _ask_harness(monkeypatch, tmp_path, [ANSWER, ANSWER])
    caller = principal_for(user_id="alice", department="finance")
    ask(caller, session_id="")  # 先写进缓存
    body = ask(caller, session_id="")

    assert _event_names(body) == ["status", "text", "done"]
    status_frame = next(frame for frame in body.split("\n\n") if frame.startswith("event: status"))
    assert json.loads(status_frame.split("data: ", 1)[1]) == {
        "type": "status",
        "content": "📋 缓存命中，直接返回",
    }
    payload = _final_text_payload(body)
    assert payload["type"] == "text"
    assert payload["content"] == ANSWER

# ==================== 总控收口补充（09-18）：唯一可达的危险面 ====================
OTHER_QUESTION = "加班餐补的标准是多少？"


def test_the_bare_global_key_serves_nobody_who_carries_a_scope(monkeypatch):
    """`scope=""` 落的是历史全局键 `answer:<hash>`：它不属于任何授权输入，谁都不许回读。

    今天 `/ask` 的两个调用点（`chat.py` 读缓存、写缓存）都显式传 `scope=answer_scope`，
    这条键只可能来自将来漏传 scope 的新调用方。本用例钉的就是那唯一可达的危险面：
    漏传的后果必须是「那条条目谁也查不到」，而不是「所有带授权输入的人共用一份答案」。
    """
    from app.common import cache

    _memory_cache(monkeypatch)
    cache.cache_answer(QUESTION, ANSWER, scope="")
    # 先确认它真的落在了「无作用域」那个形状上，否则下面三条断言都在空转。
    assert cache._answer_key(QUESTION, "") == f"answer:{cache._hash(QUESTION)}"

    for kwargs in ({}, {"department": "hr"}, {"user_id": "carol"}, {"clearance": 3}):
        scope = cache.answer_cache_scope(principal_for(**kwargs))
        assert cache.get_cached_answer(QUESTION, scope=scope) is None, kwargs

    # 匿名兜底也不算空作用域：它的键里带 user:anonymous 摘要，同样读不到全局键。
    assert cache.get_cached_answer(QUESTION, scope=cache.answer_cache_scope(None)) is None

    # 反向：带作用域写入的条目，漏传 scope 的调用方也一条都不许读到。
    scoped = cache.answer_cache_scope(principal_for())
    cache.cache_answer(OTHER_QUESTION, ANSWER, scope=scoped)
    assert cache.get_cached_answer(OTHER_QUESTION, scope="") is None
    assert cache.get_cached_answer(OTHER_QUESTION, scope=scoped) is not None
