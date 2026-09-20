"""R109 · 追问改写腿的离线罐头句守卫（工单 §48）。

缺陷：provider 挂掉或超时时，model_handler.chat(stream=False) 不抛异常，而是返回一枚带
error_code=model_unavailable 的 ModelReply，内容是本不该出现在题面里的离线罐头句。改写
函数原先只检查 rewritten 非空且长度 > 3，那句话两条都满足，于是它取代用户真正的问题进入
图、进入检索、并参与答案缓存键，而 except 分支在这条路上根本不会触发。判据要求改用类型化
error_code 判别，命中即视同改写失败、回落到原问题。

追加判据 1-b：同一枚 error_code 字段上还挂着第二枚码 —— RATE_LIMITED_CODE 的正文是一句
103 字的英文容量罐头，照样过 len > 3，于是同一个洞换了个马甲。守卫因此是一张恰好两枚的
枚举表：RESPONSE_EMPTY_CODE 与 OUTPUT_TRUNCATED_CODE 是真答案身上带的诊断码（后者是一条
被长度切短的真改写），不收。判据 2-b 的反向钉子就是钉住"非空即失败"那种总线判的。

全程离线：model_handler.chat 一律打成桩，不打模型、不起服务、不连数据库。
"""
import asyncio
import logging

import pytest

from app.api.v1 import chat
from app.common import cache
from app.common.model_handler import (
    MODEL_UNAVAILABLE_CODE,
    MODEL_UNAVAILABLE_REPLY,
    OUTPUT_TRUNCATED_CODE,
    RATE_LIMITED_CODE,
    ModelReply,
    _OfflineStreamChunk,
)

#: 以改写腿 triggers 名单里的词开头 —— 这一类题才会启动改写
TRIGGER_QUESTION = "那个部门的预算是多少？"
#: 不以触发词开头 —— 改写腿本该一声不响
PLAIN_QUESTION = "2024年各部门预算分别是多少？"
PREVIOUS_QUESTION = "2024年财务部门的预算是800万元。"
REWRITTEN_QUESTION = "2024年财务部门的预算占全年的比例是多少？"
#: 抄自真源 app/common/model_handler.py:246-253 的那句容量罐头（103 字）。它只作为桩的输入
#: 出现，守卫一个字都不比对它 —— 判据靠的是 error_code 字段。
RATE_LIMITED_REPLY_SAMPLE = (
    "Local model capacity is exhausted (error_code=rate_limited); "
    "no business conclusion was generated."
)


def offline_reply(**_kwargs):
    """真源形状：provider 不可用时 chat() 交回来的就是这一枚（model_handler._model_failure）。"""
    return ModelReply(MODEL_UNAVAILABLE_REPLY, error_code=MODEL_UNAVAILABLE_CODE)


#: 真源 chat() 非流式那一趟的返回形状（app/common/model_handler.py 的 ModelReply 是 str 子类）。
#: 判据 2-丙 要区分两件事：改写腿"压根没跑"与"跑了但被闸在外层"——两者的 calls 计数不同。
NORMAL_REWRITE_REPLY = ModelReply(REWRITTEN_QUESTION, finish_reason="stop")


def rate_limited_reply(**_kwargs):
    """真源形状：改写预算被容量闸住时 chat() 交回来的是这一枚（model_handler.py:246-253）。"""
    return ModelReply(RATE_LIMITED_REPLY_SAMPLE, error_code=RATE_LIMITED_CODE)


def record_chat_calls(monkeypatch, reply_for):
    """把改写腿唯一的模型出口打成桩，并记下每一趟调用。"""
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return reply_for(**kwargs)

    monkeypatch.setattr(chat.model_handler, "chat", fake_chat)
    return calls


def warning_messages(caplog):
    """本单的账都记在 warning 及以上这一层。"""
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.fixture(autouse=True)
def one_turn_of_history(monkeypatch):
    """改写腿需要一句上文，这里直接给，绕开 session 存储，不碰数据库。"""
    monkeypatch.setattr(
        chat,
        "_get_session_messages",
        lambda _session_id: [{"role": "user", "content": PREVIOUS_QUESTION}],
    )


# ==================== 判据 2：坏链路上必须回落到原问题 ====================

def test_offline_canned_reply_does_not_replace_the_users_question(monkeypatch, caplog):
    calls = record_chat_calls(monkeypatch, offline_reply)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        result = chat._rewrite_followup("r109-offline", TRIGGER_QUESTION)

    assert result == TRIGGER_QUESTION, "拿到离线罐头句时必须回退用户原问题，不许拿它当改写结果"
    assert MODEL_UNAVAILABLE_REPLY not in result
    assert type(result) is str, "回退时不许把 ModelReply 对象本身交回调用方"
    assert len(calls) == 1, "守卫应当在真调用之后生效，不许靠压根不调用来假装通过"
    assert calls[0]["stream"] is False, "改写腿走的必须是非流式那一趟"
    # 回落必须由本单的守卫负责，不许是既有 except 分支顺手接住的 —— 那是判据 2 对照②的
    # 领地，两者混在一起就分不清哪一道在起作用，摘掉守卫的反证也会因此空响。
    assert not any("[REWRITE] 失败" in m for m in warning_messages(caplog))


def test_fallback_leaves_a_greppable_warning(monkeypatch, caplog):
    record_chat_calls(monkeypatch, offline_reply)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        chat._rewrite_followup("r109-log", TRIGGER_QUESTION)

    messages = warning_messages(caplog)
    assert any(
        "改写腿拿到离线罐头句" in m and "已回退原问题" in m for m in messages
    ), "判据 1 要求留一条指名这件事的 warning 供运维 grep：" + " / ".join(messages)


# ==================== 追加判据 2-b：第二枚罐头句走同一道守卫 ====================

def test_rate_limited_canned_reply_does_not_replace_the_users_question(monkeypatch, caplog):
    """追加判据 2-b：那句 103 字的英文容量罐头同样不许冒充题面。"""
    calls = record_chat_calls(monkeypatch, rate_limited_reply)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        result = chat._rewrite_followup("r109-rate", TRIGGER_QUESTION)

    assert result == TRIGGER_QUESTION, "拿到容量罐头句时必须回退用户原问题"
    assert RATE_LIMITED_REPLY_SAMPLE not in result
    assert type(result) is str, "回退时不许把 ModelReply 对象本身交回调用方"
    assert len(calls) == 1 and calls[0]["stream"] is False
    assert len(RATE_LIMITED_REPLY_SAMPLE) > 3, "这句话本来就过得了那道尺寸检查"
    assert not any("[REWRITE] 失败" in m for m in warning_messages(caplog))
    # §12.1 那条机器判据扫的是整份 chat.py：码名不许塞进可读文本，改写后的日志因此
    # 用"改写码"这个中文键名挂裸码值。这一行把形态钉住，防止下一个人改回等号写法。
    assert not any("error_code=" in m for m in warning_messages(caplog))
    assert any(
        "改写腿拿到离线罐头句" in m and "改写码 rate_limited" in m
        for m in warning_messages(caplog)
    ), "容量这条回落也得留一行可 grep 的账"


def test_the_two_canned_replies_fall_back_with_distinguishable_words(monkeypatch, caplog):
    """追加判据 2-b：两枚码的账要分得开 —— 一个是"预算太小"，一个是"模型坏了"。"""
    logged = {}

    for label, reply_for, cause in (
        ("unavailable", offline_reply, "模型不可用，provider 未生成业务结论"),
        ("rate_limited", rate_limited_reply, "改写预算闸住，本机模型容量已满"),
    ):
        record_chat_calls(monkeypatch, reply_for)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
            fallback = chat._rewrite_followup("r109-" + label, TRIGGER_QUESTION)
        assert fallback == TRIGGER_QUESTION
        hits = [m for m in warning_messages(caplog) if "已回退原问题" in m]
        assert len(hits) == 1, f"{label} 这条回落只该留一行账，实际 {len(hits)} 行"
        assert cause in hits[0], f"{label} 的 warning 要指名原因：{hits[0]}"
        logged[label] = hits[0]

    assert logged["unavailable"] != logged["rate_limited"]
    assert "改写码 model_unavailable" in logged["unavailable"]
    assert "改写码 rate_limited" in logged["rate_limited"]
    assert not any("error_code=" in m for m in logged.values()), "§12.1：码名不许塞进可读文本"
    assert "本机模型容量已满" not in logged["unavailable"]
    assert "模型不可用" not in logged["rate_limited"]


# ==================== 判据 2 的三条对照 ====================

def test_a_real_rewrite_still_comes_back_rewritten(monkeypatch):
    """对照①：好链路的改写结果一个字都不许受影响。"""
    calls = record_chat_calls(
        monkeypatch, lambda **_kwargs: ModelReply(REWRITTEN_QUESTION, finish_reason="stop")
    )

    assert chat._rewrite_followup("r109-good", TRIGGER_QUESTION) == REWRITTEN_QUESTION
    assert len(calls) == 1


def test_a_plain_string_reply_still_comes_back_rewritten(monkeypatch):
    """对照①的补角：ModelReply 是 str 子类，但普通 str 也是改写腿的既有契约。"""
    calls = record_chat_calls(monkeypatch, lambda **_kwargs: REWRITTEN_QUESTION)

    assert chat._rewrite_followup("r109-plain", TRIGGER_QUESTION) == REWRITTEN_QUESTION
    assert len(calls) == 1


def test_a_truncated_but_real_rewrite_is_still_adopted(monkeypatch, caplog):
    """追加判据 2-b 的反向钉子：output_truncated 是被长度切短的真改写，不许顺手丢掉。

    这枚钉子钉的是"error_code 非空即视同失败"那种总线判 —— 它会连能用的改写一起扔，
    等于用一个洞换另一个洞。守卫日后被改成总线判，这里就是第一个红的。
    """
    truncated = ModelReply(
        REWRITTEN_QUESTION, finish_reason="length", error_code=OUTPUT_TRUNCATED_CODE
    )
    calls = record_chat_calls(monkeypatch, lambda **_kwargs: truncated)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        result = chat._rewrite_followup("r109-truncated", TRIGGER_QUESTION)

    assert result == REWRITTEN_QUESTION, "真改写被切短时仍应采用改写结果，不许回退"
    assert len(calls) == 1
    assert not any("已回退原问题" in m for m in warning_messages(caplog))


def test_provider_exception_still_falls_back_through_the_except_branch(monkeypatch):
    """对照②：抛异常那条既有回落路径，守卫不许动它一根手指。"""

    def boom(**_kwargs):
        raise RuntimeError("connection refused")

    calls = record_chat_calls(monkeypatch, boom)

    assert chat._rewrite_followup("r109-exc", TRIGGER_QUESTION) == TRIGGER_QUESTION
    assert len(calls) == 1


def test_non_trigger_question_never_reaches_the_model(monkeypatch):
    """对照③：不以触发词开头的题，改写腿一次都不许调模型。"""
    calls = record_chat_calls(monkeypatch, offline_reply)

    assert chat._rewrite_followup("r109-silent", PLAIN_QUESTION) == PLAIN_QUESTION
    assert calls == [], "坏链路被放大成整场问答的代价，是从这里开始算的"


def test_trigger_question_without_history_never_reaches_the_model(monkeypatch):
    """对照③的另一半：没有上文时改写腿同样必须沉默。"""
    monkeypatch.setattr(chat, "_get_session_messages", lambda _session_id: [])
    calls = record_chat_calls(monkeypatch, offline_reply)

    assert chat._rewrite_followup("r109-nohist", TRIGGER_QUESTION) == TRIGGER_QUESTION
    assert calls == []


def test_the_route_never_strips_a_reply_or_flattens_a_stream_on_a_plain_turn(
    monkeypatch, tmp_path
):
    """判据 2-乙 / 2-丙：路由级钉"非触发词这一轮改写腿压根没跑"，用痕迹，不只数调用。

    两道痕迹（计数为 0 可能只是桩没接上，所以两样都留）：
      ① stream=False 那一趟交回一枚 .strip() 会记账的 ModelReply 子类 —— 改写腿一旦真的
         跑起来，就会就地把它压成字符串（app/api/v1/chat.py:719），账上必留痕；
      ② stream=True 那一趟交回真源那条 iter([_OfflineStreamChunk(整句)])，桩原样收走。
         它不是 str，谁想 .strip()/.join() 压平它都会当场炸出属性错误。
    对照组换成触发词题面跑同一套桩：那时 ① 必须记一次账，否则上面那枚"零痕迹"是空响。
    """
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    answer = "各部门 2024 年预算合计 6400 万元。"
    graph_messages = []
    cache_lookups = []
    strip_trace = []
    stream_calls = []
    handed_back_streams = []

    class StripSpyReply(ModelReply):
        """改写腿对返回值只做一件事：.strip()。那就让它自己报账。"""

        def strip(self, chars=None):
            strip_trace.append(str(self))
            return super().strip(chars)

    def fake_chat(**kwargs):
        if kwargs.get("stream"):
            stream_calls.append(kwargs)
            stream = iter([_OfflineStreamChunk(MODEL_UNAVAILABLE_REPLY)])
            handed_back_streams.append(stream)
            return stream
        return StripSpyReply(REWRITTEN_QUESTION, finish_reason="stop")

    monkeypatch.setattr(chat.model_handler, "chat", fake_chat)

    def fake_stream(message, *_args, **_kwargs):
        graph_messages.append(message)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    def fake_get_cached_answer(question, scope=""):
        cache_lookups.append((question, scope))
        return None

    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "staff", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat,
        "auth",
        type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}),
    )
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9)
    )
    monkeypatch.setattr("app.common.cache.get_cached_answer", fake_get_cached_answer)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    async def consume(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    def ask_once(message):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id="r109-turn"),
                http_request=http_request,
            )
        )
        return asyncio.run(consume(response))

    body = ask_once(PLAIN_QUESTION)

    assert strip_trace == [], "非触发词这一轮不许出现任何 .strip() 痕迹"
    assert stream_calls == [], "/ask 的答复腿走编排器，不该向 chat() 要一条流"
    assert handed_back_streams == []
    assert graph_messages == [PLAIN_QUESTION]
    assert cache_lookups and cache_lookups[0][0] == PLAIN_QUESTION
    assert answer in body
    assert MODEL_UNAVAILABLE_REPLY not in body

    # 对照组：同一套桩换成触发词，.strip() 必须记一次账 —— 上面那枚零痕迹才不是空响。
    del strip_trace[:]
    del graph_messages[:]
    del cache_lookups[:]
    ask_once(TRIGGER_QUESTION)
    assert strip_trace == [REWRITTEN_QUESTION], "触发词这一轮改写腿要真跑，痕迹必须落在账上"
    assert graph_messages == [REWRITTEN_QUESTION]
    assert cache_lookups[0][0] == REWRITTEN_QUESTION

    # 真源那条流的形状：被交回时它是迭代器，逐个元素消费后首元素是 chunk 对象而不是整句
    # str，正文要从 delta.content 里读 —— 这正是 app/api/v1/chat.py:911-916 答复腿消费它的
    # 方式。摘掉本单守卫也改不了这条：罐头句从来没有一条流可压，它是被原样交回的一整个对象。
    offline_stream = fake_chat(
        messages=[{"role": "user", "content": PLAIN_QUESTION}], stream=True
    )
    assert not isinstance(offline_stream, str), "流式返回值不许是字符串"
    elements = list(offline_stream)
    assert len(elements) == 1
    assert not isinstance(elements[0], str), "首元素必须是 chunk 对象，不是被压平的整句"
    assert elements[0].choices[0].delta.content == MODEL_UNAVAILABLE_REPLY
    assembled = "".join(
        (getattr(getattr(chunk, "choices", None)[0], "delta", None).content or "")
        for chunk in elements
    )
    assert assembled == MODEL_UNAVAILABLE_REPLY


# ==================== 判据 3：回落之后的缓存题面 ====================

def test_fallback_reads_back_the_cache_key_of_the_unrewritten_turn(monkeypatch):
    """回落到原问题之后，缓存题面与"这轮压根没改写"时逐字一致。

    走 cache.cache_answer / cache.get_cached_answer 真源，不碰 cache.py：命中与否只由
    answer:{scope_part}{question_hash} 决定，所以这条断言测的就是题面本身。
    """
    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    scope = cache.answer_cache_scope(None, "r109-user")
    cached_answer = "财务部门那一年预算占全年 12%。"
    # 这一条是"那轮压根没改写"时写下去的缓存：题面就是用户原话
    cache.cache_answer(TRIGGER_QUESTION, cached_answer, scope=scope)

    record_chat_calls(monkeypatch, offline_reply)
    question_used = chat._rewrite_followup("r109-cache", TRIGGER_QUESTION)

    assert question_used.encode("utf-8") == TRIGGER_QUESTION.encode("utf-8")
    assert cache.get_cached_answer(question_used, scope=scope) == cached_answer
    # 坏链路的爆炸半径：罐头句会打到另一个键上，同一句话在坏链路上裂成两条缓存
    assert cache.get_cached_answer(MODEL_UNAVAILABLE_REPLY, scope=scope) is None
    assert cache.answer_cache_scope(None, "r109-user") == scope, "作用域口径与本单无关，不许漂"


def test_ask_route_puts_the_original_question_into_graph_and_cache(
    monkeypatch, tmp_path, caplog
):
    """接线证据：/ask 这一趟带着守卫跑完，进图与查缓存用的是同一句用户原话。

    这里故意不桩 _rewrite_followup —— 要的就是路由真走一遍改写腿，否则判据 2 的回落
    只停在函数内部，而工单记的是它下游三处消费点（图、检索、缓存键）。
    """
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    answer = "财务部门 2024 年预算 800 万元。"
    graph_messages = []
    cache_lookups = []

    def fake_stream(message, *_args, **_kwargs):
        graph_messages.append(message)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    def fake_get_cached_answer(question, scope=""):
        cache_lookups.append((question, scope))
        return None

    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "staff", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat,
        "auth",
        type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}),
    )
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9)
    )
    monkeypatch.setattr("app.common.cache.get_cached_answer", fake_get_cached_answer)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    chat_calls = record_chat_calls(monkeypatch, offline_reply)

    async def consume(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=TRIGGER_QUESTION, session_id="r109-route"),
                http_request=http_request,
            )
        )
        body = asyncio.run(consume(response))

    assert graph_messages == [TRIGGER_QUESTION], "进图的题面必须是用户原话，不许是罐头句"
    assert cache_lookups and cache_lookups[0][0] == TRIGGER_QUESTION
    assert all(MODEL_UNAVAILABLE_REPLY != q for q, _ in cache_lookups)
    assert MODEL_UNAVAILABLE_REPLY not in body
    assert answer in body
    # 三枚计数把话说死：守卫确实是在 /ask 这一趟里起效的，不是别的分支顺手凑出来的。
    assert len(chat_calls) == 1, "/ask 这一趟要真走改写腿，否则测不到守卫"
    assert any("改写腿拿到离线罐头句" in m for m in warning_messages(caplog))
    assert not any("[REWRITE] 失败" in m for m in warning_messages(caplog))


def test_the_route_gives_the_offline_turn_and_the_silent_turn_one_cache_key(
    monkeypatch, tmp_path
):
    """判据 3-乙：路由级键对拍 —— 同一个人、同一句原话，坏链路不许打出第二个键。

    两轮都从 /ask 进，题面都是 TRIGGER_QUESTION，缓存里预先摆好两条：一条挂在原话题面上，
    一条挂在罐头句题面上当诱饵，命中哪条就说明这一轮真拿去算键的题面是哪句。
      第一轮 有上文 ⇒ 改写腿真跑 ⇒ 拿到离线罐头句 ⇒ 守卫回落成原话；
      第二轮 抽掉上文 ⇒ 改写腿沉默 ⇒ 这一轮压根没改写。
    键一律由 cache.py 真源算：桩只把 (题面, 作用域) 记下来再原样委托给
    cache.get_cached_answer，测试自己一个 md5 都不碰。
    """
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    answer_under_original = "原话题面那条缓存的答案。"
    answer_under_canned = "只有题面被换成罐头句才读得到的诱饵。"
    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "staff", "department": "finance"}
    )
    scope = cache.answer_cache_scope(principal, username="alice")
    cache.cache_answer(TRIGGER_QUESTION, answer_under_original, scope=scope)
    cache.cache_answer(MODEL_UNAVAILABLE_REPLY, answer_under_canned, scope=scope)
    assert cache._answer_key(TRIGGER_QUESTION, scope) != cache._answer_key(
        MODEL_UNAVAILABLE_REPLY, scope
    ), "两条题面本就是两个键，否则这枚对拍是空响"

    looked_up = []
    graph_messages = []
    real_get_cached_answer = cache.get_cached_answer

    def spy_get_cached_answer(question, scope=""):
        # 关键字名沿用调用方原话（chat.py:1191 用 scope= 传），这里只做记录再原样委托真源
        looked_up.append((question, scope))
        return real_get_cached_answer(question, scope=scope)

    def fake_stream(message, *_args, **_kwargs):
        graph_messages.append(message)
        yield {
            "messages": [],
            "worker_results": {"doc": "这一轮压根不该进图"},
            "final_answer": "这一轮压根不该进图",
        }

    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat,
        "auth",
        type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}),
    )
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9)
    )
    monkeypatch.setattr("app.common.cache.get_cached_answer", spy_get_cached_answer)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(
        chat, "session_registry", SessionRegistry(tmp_path / "sessions.json")
    )
    chat_calls = record_chat_calls(monkeypatch, offline_reply)

    async def consume(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    def ask_once():
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=TRIGGER_QUESTION, session_id="r109-key"),
                http_request=http_request,
            )
        )
        return asyncio.run(consume(response))

    offline_body = ask_once()

    assert len(chat_calls) == 1, "第一轮要真跑改写腿，否则测的是沉默而不是回落"
    assert looked_up == [(TRIGGER_QUESTION, scope)]
    assert answer_under_original in offline_body
    assert answer_under_canned not in offline_body
    assert graph_messages == [], "命中的是缓存条目，这一轮不该进图"

    # 第二轮：抽掉上文 ⇒ 改写腿沉默 ⇒ 这一轮压根没改写，题面与作用域都不许多出一个键
    monkeypatch.setattr(chat, "_get_session_messages", lambda _session_id: [])
    del looked_up[:]
    silent_body = ask_once()

    assert len(chat_calls) == 1, "没有上文的这一轮，改写腿一次都不许再跑"
    assert looked_up == [(TRIGGER_QUESTION, scope)]
    assert silent_body == offline_body
    assert answer_under_original in silent_body
    keys = {cache._answer_key(q, s) for q, s in looked_up}
    assert keys == {cache._answer_key(TRIGGER_QUESTION, scope)}
    assert cache._answer_key(MODEL_UNAVAILABLE_REPLY, scope) not in keys
    assert cache.answer_cache_scope(principal, username="alice") == scope, "口径不许漂"
