"""R126 · 改写腿的「上一问」必须是真上一轮，追问判据必须认全 12 枚多轮题。

两处缺陷（跟进单 §64 二，总控亲验）：
  (a) `app/api/v1/chat.py` 的 ask 路由原先 `:1116` 先 `_save_message(本轮用户问)`、`:1125`
      才 `_rewrite_followup` 读历史，而取值是 `prev_user[-1]` ⇒ prompt 里
      「上一问: X ／ 当前: X」永远同一句，模型没有上文可用，只能凭空编一段。
  (b) 触发判据只有七枚前缀（那/它/这个/那个/他们/换/改成），对
      `tests/fixtures/business_evaluation_100.jsonl` 里 `多轮对话` 那 12 枚题只命中 4 枚
      （chat-02/06/07/12），另外 8 枚压根没进改写腿。

判据① 要求本文件至少一枚用例走**真存读路由**：`_ensure_sessions_table` / `_save_message` /
`_get_session_messages` 一律真源，不许 monkeypatch 替掉存取 —— 替换掉它们恰恰是本单要修的
"反向奖励"（`tests/test_r109_rewrite_offline_guard.py` 那枚 autouse fixture）。conftest 已把
DATABASE_URL 钉在保留端口 1，`app/common/auth.py` 导入期探针必然失败、`_db_ready` 恒 False，
所以真源自己走内存那条腿：不碰库、不起服务、不打模型，`model_handler.chat` 与编排器两条腿
全程是桩。
"""
import asyncio
import json
import uuid
from pathlib import Path

import pytest

from app.api.v1 import chat
from app.common import cache
from app.common.identity import Principal
from app.common.model_handler import ModelReply
from app.storage.sessions import SessionRegistry

#: 评测题集：105 行，其中 12 行是 `多轮对话`（工单里写作 group，字段名实为 category）
EVAL_FIXTURE = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"
MULTI_TURN_GROUP = "多轮对话"

#: 自己就立得住：本轮之前没有上文时，它一次都不该进改写腿
FIRST_TURN = "住宿费标准是多少？"
#: 句首指代，必须进改写腿；它的上一问只可能是 FIRST_TURN
SECOND_TURN = "那市内交通有单日上限吗？"
#: 桩出来的"改写结果"：用来确认进图的是改写后的句子，也不是被误当上文的本轮自己
REWRITTEN = "市内交通单日报销上限是多少元？"
#: 上一轮的答复文本，形状与真源一致（role/content/steps/created_at 四键）
PREVIOUS_CONTEXT_QUESTION = "差旅住宿标准是多少？"
PREVIOUS_CONTEXT_ANSWER = "住宿费按每人每晚 500 元计发。"
ANSWER_BODY = "市内交通单日不超过 200 元。"


def _rows():
    with EVAL_FIXTURE.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


_ALL_ROWS = _rows()
_MULTI_TURN = [(r["id"], r["question"]) for r in _ALL_ROWS if r["category"] == MULTI_TURN_GROUP]
_OTHER_ROWS = [(r["id"], r["question"]) for r in _ALL_ROWS if r["category"] != MULTI_TURN_GROUP]


def _label_line(prompt: str, label: str) -> str:
    """把改写 prompt 里 `上一问: ` / `当前: ` 两行取出来，取不到就返回空串。"""
    prefix = label + ": "
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return ""


def record_rewriter_prompts(monkeypatch, reply: str = REWRITTEN):
    """只桩改写腿唯一的模型出口，返回它看到的 prompt 列表。"""
    prompts = []

    def fake_chat(**kwargs):
        messages = kwargs.get("messages") or [{}]
        prompts.append(messages[0].get("content", ""))
        return ModelReply(reply, finish_reason="stop")

    monkeypatch.setattr(chat.model_handler, "chat", fake_chat)
    return prompts


def _sessions_live_in_memory():
    """真源存读的前提：本机 PG 在测试里必然探不通，所以走的是内存那条腿。"""
    return chat._session_database_available() is False


def _session_with_one_previous_turn() -> str:
    """用真 `_save_message` 存一段"上一问 + 上一答"，返回会话号。"""
    assert _sessions_live_in_memory(), "会话存读走错分支，本文件的真存读断言就不成立"
    session_id = "r126-" + uuid.uuid4().hex
    chat._save_message(session_id, "user", PREVIOUS_CONTEXT_QUESTION)
    chat._save_message(session_id, "assistant", PREVIOUS_CONTEXT_ANSWER)
    return session_id


def install_ask_route(monkeypatch, tmp_path):
    """装好 /ask 的离线外壳，返回 (问一次, 改写腿 prompt 列表, 进图的题面列表)。

    桩只盖外部件：Redis、限流、答案缓存、编排器、模型出口、会话注册表落盘路径。
    **会话存读一个都不桩** —— `_ensure_sessions_table`、`_save_message`、
    `_get_session_messages`、`_ensure_session` 全走 `app/api/v1/chat.py` 真源（判据①）。
    """
    assert _sessions_live_in_memory(), "不许连真库：真存读用例只在内存腿上成立"
    prompts = []
    graph_messages = []

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())

    def fake_model_chat(**kwargs):
        messages = kwargs.get("messages") or [{}]
        prompts.append(messages[0].get("content", ""))
        return ModelReply(REWRITTEN, finish_reason="stop")

    def fake_stream(message, *_args, **_kwargs):
        graph_messages.append(message)
        yield {
            "messages": [],
            "worker_results": {"doc": ANSWER_BODY},
            "final_answer": ANSWER_BODY,
        }

    monkeypatch.setattr(chat.model_handler, "chat", fake_model_chat)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.answer_cache_origin", lambda *_a, **_k: {})
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "staff", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    def ask_once(message, session_id):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=http_request,
            )
        )
        chunks = []

        async def consume():
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)

        asyncio.run(consume())
        return "".join(chunks)

    return ask_once, prompts, graph_messages


# ==================== 判据① 存-读顺序：走真存读路由 ====================

def test_the_second_turn_gets_the_first_question_as_its_context(monkeypatch, tmp_path):
    """连问两轮：改写器看到的「上一问」== 第一轮原文，且绝不等于本轮自己。"""
    ask_once, prompts, graph_messages = install_ask_route(monkeypatch, tmp_path)
    session_id = "r126-order-" + uuid.uuid4().hex

    ask_once(FIRST_TURN, session_id)
    assert prompts == [], "本轮之前没有上一问，改写腿一次都不许跑"
    assert graph_messages == [FIRST_TURN]

    ask_once(SECOND_TURN, session_id)

    assert len(prompts) == 1, "带指代的第二轮必须真进改写腿"
    assert _label_line(prompts[0], "上一问") == FIRST_TURN
    assert _label_line(prompts[0], "当前") == SECOND_TURN
    assert _label_line(prompts[0], "上一问") != _label_line(prompts[0], "当前"), (
        "「上一问」又取成本轮自己了：这正是 R126 修掉的缺陷 (a)"
    )
    assert ("上一问: " + SECOND_TURN) not in prompts[0]
    assert graph_messages == [FIRST_TURN, REWRITTEN], "改写结果照旧进图，本单不动下游"


def test_the_route_reads_history_before_it_writes_this_turn(monkeypatch, tmp_path):
    """直接把顺序钉住：改写腿被调用的那一刻，库里的用户问还不许含本轮自己。

    上面那枚用例钉的是结果（「上一问」== 第一轮），这一枚钉的是顺序本身 —— 只挪顺序、
    不修取值（或反过来）都红。这里只给 `_rewrite_followup` 套一层**读数**的壳：它原样
    委托真源，存读三件套一个字都没替掉。
    """
    ask_once, _prompts, _graph = install_ask_route(monkeypatch, tmp_path)
    session_id = "r126-order-peek-" + uuid.uuid4().hex
    real_rewrite = chat._rewrite_followup
    user_rows_at_rewrite = []

    def spy_rewrite(session_id_seen, user_msg):
        user_rows_at_rewrite.append(
            [m["content"] for m in chat._get_session_messages(session_id_seen) if m["role"] == "user"]
        )
        return real_rewrite(session_id_seen, user_msg)

    monkeypatch.setattr(chat, "_rewrite_followup", spy_rewrite)

    ask_once(FIRST_TURN, session_id)
    ask_once(SECOND_TURN, session_id)

    # 第一轮那一刻库里连本轮都还没有（内存腿是空的），第二轮只剩第一轮那句：
    # 落库挪到改写之后，两个数字同时钉住顺序与"历史不缺行"。
    assert user_rows_at_rewrite == [[], [FIRST_TURN]], (
        "改写腿被调用时不许已经看见本轮自己 —— 又先存后读了"
    )



def test_this_turn_is_still_persisted_after_the_rewrite(monkeypatch, tmp_path):
    """落库挪到改写之后，本轮那句仍要进历史，且仍在助手答复之前。"""
    ask_once, _prompts, _graph = install_ask_route(monkeypatch, tmp_path)
    session_id = "r126-persist-" + uuid.uuid4().hex

    ask_once(FIRST_TURN, session_id)
    ask_once(SECOND_TURN, session_id)

    stored = chat._get_session_messages(session_id)  # 真读，不桩
    assert [m["role"] for m in stored] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in stored if m["role"] == "user"] == [FIRST_TURN, SECOND_TURN]
    assert stored[2]["steps"] == []
    assert chat._ensure_session(session_id)["title"], "会话标题仍由第一枚用户问落库时写入"


def test_a_history_that_already_holds_this_turn_is_not_its_own_context(monkeypatch):
    """第二道闸：调用方先把本轮落了库（旧顺序）时，改写腿也得把本轮自己剔掉。"""
    prompts = record_rewriter_prompts(monkeypatch)
    session_id = _session_with_one_previous_turn()
    chat._save_message(session_id, "user", SECOND_TURN)

    assert chat._rewrite_followup(session_id, SECOND_TURN) == REWRITTEN
    assert len(prompts) == 1
    assert _label_line(prompts[0], "上一问") == PREVIOUS_CONTEXT_QUESTION
    assert _label_line(prompts[0], "当前") == SECOND_TURN


def test_a_trigger_question_without_a_previous_turn_stays_out_of_the_model(monkeypatch):
    """有指代但没有上一轮：不许白烧一次模型往返。"""
    prompts = record_rewriter_prompts(monkeypatch)

    assert chat._rewrite_followup("r126-empty-" + uuid.uuid4().hex, SECOND_TURN) == SECOND_TURN
    assert prompts == []


# ==================== 判据③ 触发判据：12 枚一枚不丢、93 枚一个字不许多 ====================

def test_the_fixture_still_splits_into_twelve_and_ninety_three():
    """题集一漂，下面两枚对拍就失去意义 —— 先把 12/93 这个前提钉住。"""
    assert len(_ALL_ROWS) == 105
    assert len(_MULTI_TURN) == 12
    assert len(_OTHER_ROWS) == 93


@pytest.mark.parametrize(
    "question", [q for _id, q in _MULTI_TURN], ids=[i for i, _q in _MULTI_TURN]
)
def test_every_multi_turn_fixture_question_reaches_the_rewriter(monkeypatch, question):
    """判据③ 的正向半边：12 枚 `多轮对话` 题现算必须一枚不丢。"""
    prompts = record_rewriter_prompts(monkeypatch)
    session_id = _session_with_one_previous_turn()

    assert chat._rewrite_followup(session_id, question) == REWRITTEN
    assert len(prompts) == 1, "这一枚多轮题没进改写腿：" + question
    assert _label_line(prompts[0], "上一问") == PREVIOUS_CONTEXT_QUESTION
    assert _label_line(prompts[0], "当前") == question


def test_the_other_ninety_three_fixture_questions_never_enter_the_rewriter(monkeypatch):
    """判据③ 的反向半边：其余 93 枚题一个字都不许多进改写，prompt 也就一个字都不许变。"""
    prompts = record_rewriter_prompts(monkeypatch)
    offenders = []

    for row_id, question in _OTHER_ROWS:
        before = len(prompts)
        result = chat._rewrite_followup(_session_with_one_previous_turn(), question)
        if len(prompts) != before or result != question:
            offenders.append(f"{row_id}: {question}")

    assert offenders == [], "这些单轮题被拖进了改写腿：" + " | ".join(offenders)


def test_an_explicitly_standalone_question_is_not_rewritten_even_with_history(monkeypatch):
    """判据③ 点名的负向用例：一句自带主语、对象、口径的单轮问题，有上文也不许改写。"""
    prompts = record_rewriter_prompts(monkeypatch)
    standalone = "2024年各部门报销金额分别是多少？"

    assert chat._rewrite_followup(_session_with_one_previous_turn(), standalone) == standalone
    assert prompts == [], "独立成句的单轮问题不该占用改写预算"
