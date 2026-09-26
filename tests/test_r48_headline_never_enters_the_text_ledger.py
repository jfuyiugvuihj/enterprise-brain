# -*- coding: utf-8 -*-
r"""R48 路线甲 · 🔴 卡片帧一个字都不许进 ``event: text`` 那本账（派工判据 ② 的行为钉）。

为什么必须有这一枚文件（跟进单 §93 判据 ① 的假绿证明，原文口径）：把首屏卡片做成一枚
``event: text`` 帧，**在评分尺上是可以全绿的** —— 卡片作首帧、而终答又以它为前缀时，
``text_frames > 1``、``max_stream_frames > 1``、``prefix_breaks == 0``、``extra_chars == 0``
四格同时为真，于是「这条流在逐片累计」被一张压根不逐片的卡骗过去：今晚诚实的红洗成假绿。
所以本件钉的不是「卡片像不像正文」，而是**帧账这本账目不因卡片多一枚**。

对照的做法：同一轮跑两遍，一遍发卡、一遍只摘掉那一枚 yield（``_answer_headline_frame``
换成空串），两遍的帧账读数必须逐位相同。🔴 不用「按事件名摘帧」那种假对照——名字一摘就没了
的东西，证不了改名成 ``text`` 之后的形状；只有把发射点整个摘掉再比，才是判据 ② 要的前后对照。

四枚钉，全部在真 ``_consume`` 级别上做（``scripts/eval_transport_ask_v2.py`` 那把尺子原样
import，一个字不改——与 R203 同一分工，「不许改量具」）：

  A 非流式的一轮（一帧收尾）：加卡与摘卡逐位相同，且评分尺那格今天本就是 False。
  B 正文道载荷闭集：每一枚 ``text`` 帧的键必须落在既有六枚之内，卡片那几格不许从侧门混进来。
  C R210 那两条形状（真流片轮 / 半路断流轮）：同样逐位相同。
  D 反证 ①：把发射点整段换成 ``text_sse_frame(第一枚来源文件名)``、终答以它开头 ——
     A 那枚钉必须**当场变红**（红在帧账数字上），而尺子自己那格必须**当场变绿**。
     两件事同时发生才叫假绿，本枚把两份读数与报错原文都留在记录里。

纪律：不打模型（假 orchestrator + 半路断流的假 provider）、不连库、不起服务；帧是真从
``/ask`` 流出来的，收端与尺子都是真码。
"""
import asyncio

import pytest

from app.api.v1 import chat

from tests.test_r48_headline_card_lands_on_the_wire import (  # noqa: F401  -- 同批夹具，不造第二份
    CHAT_PY as _CHAT_PY,
    EVENT,
    FINANCE_DOC,
    _TempEdit,
    _ask,
    _reload,
    cards,
    doc_state,
    drive,
    fake_retriever_hits,
    finance_principal,
    names,
    patch_offline,
    wire,
)

#: 按事件名取卡片帧（与发射面用例同一枚读取，不抄第二份）。
cards_in = cards
from tests.test_r203_sse_progressive_frames import QUESTION, ruler  # noqa: F401
from tests.test_r210_break_replaces_the_screen import (  # noqa: F401
    DIE_AFTER_FRAMES,
    STREAMED_ANSWER,
    _broken_leg,
    _clean_leg,
)

#: 帧账读数里本件关心的那几格：逐位不变才算「卡片没进账」。
LEDGER_FIELDS = ("text_frames", "prefix_breaks", "extra_chars", "missing_chars",
                 "answer_sha", "max_stream_frames", "per_stream", "streams",
                 "last_frame_chars", "last_frame_sha", "last_frame_covers_answer",
                 # 🔴 总控 09-24 随并树补的两格（本件写于 R181-only 尺子上，那时它们还不存在）。
                 # 漏掉这两格就留着一枚真的假绿通道：卡片只要多喂出一枚 answer_correction 的
                 # running step、或把末帧顶成逐字等于终答，真断流就会被 R215 豁免成
                 # uncorrected_breaks == 0 => verdict 由 False 翻 True，而上面十一格一个字都不动。
                 # 「卡片没进账」今天必须连净额两格一起比才算数。
                 "corrective_replacements", "uncorrected_breaks")
#: ``_consume`` 观测桶里除到达时间之外的全部读数：动了任何一枚都算卡片上了收端的账。
BUCKET_FIELDS = ("answer", "steps", "hitl", "error_text", "queued", "cancelled", "cached",
                 "session_id", "text_frames", "prefix_breaks", "first_break_at",
                 "last_text_frame", "evidence")


# ==================== 喂尺 ====================


def _as_lines(body):
    """整条 SSE 字面 -> ``iter_events`` 吃的那种行序列（bytes）。不预处理，逐字节进。"""
    return [line.encode("utf-8") for line in body.split("\n")]


def readings_of(body):
    """真字节 -> ``ruler.iter_events`` -> ``ruler._consume`` -> 帧账读数。全程尺子原码。"""
    out = ruler._blank_observation("sess-r48-ledger")
    ruler._consume(_as_lines(body), out)
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return ruler._frame_readings(ledger, out["answer"]), out


def suppress_card(module):
    """只摘掉发卡那一枚 yield（构造器换成空串），别的什么都不动。

    返回一个还原器：``monkeypatch`` 拆不掉 ``importlib.reload`` 之后的模块，所以变异块里
    用得上显式还原。
    """
    original = module._answer_headline_frame
    module._answer_headline_frame = lambda *_a, **_k: ""
    return lambda: setattr(module, "_answer_headline_frame", original)


def assert_the_card_moves_no_ledger_reading(tag, with_card, without_card):
    """本件的钉本体：绿色用例与反证 ① 共用同一枚函数，反证才红得对口。

    🔴 断言的次序是这枚钉的一部分：**先比账，后校验对照本身**。反证 ① 那一轮里卡片是以
    ``event: text`` 出来的，按事件名根本找不到它——若把「这一轮有没有卡」放在最前面，反证就会
    红在那枚守卫上，帧账被污染这件事实质上没被报出来。先比账，红的就是数字本身。
    """
    on, bucket_on = readings_of(with_card)
    off, bucket_off = readings_of(without_card)
    drift = {key: (off[key], on[key]) for key in LEDGER_FIELDS if on.get(key) != off.get(key)}
    assert not drift, "[%s] 卡片帧动了帧账（摘掉它 -> 留着它）：%s" % (tag, drift)
    moved = {key: (bucket_off.get(key), bucket_on.get(key))
             for key in BUCKET_FIELDS if bucket_on.get(key) != bucket_off.get(key)}
    assert not moved, "[%s] 卡片帧动了收端观测桶：%s" % (tag, moved)
    verdict_on = ruler._frame_verdict(on)
    verdict_off = ruler._frame_verdict(off)
    assert verdict_on == verdict_off, (
        "[%s] 卡片翻转了评分尺自己那格 verdict（%s -> %s）：判据 ① 说的那枚假绿就是这个形状" % (
            tag, verdict_off, verdict_on))
    # 账比完了才校验对照本身：两遍都必须按各自的形状成立。
    assert cards_in(with_card), "[%s] 这一轮没发卡，对照无从谈起" % tag
    assert not cards_in(without_card), "[%s] 摘卡那一遍仍然有卡：对照是假的" % tag
    return on


def _round_pair(monkeypatch, tmp_path, *, runner):
    """同一轮跑两遍：发卡的一遍与只摘掉 yield 的一遍。``runner`` 负责这一轮怎么跑。"""
    with_card = runner()
    restore = suppress_card(chat)
    try:
        without_card = runner()
    finally:
        restore()
    return with_card, without_card


# ==================== A：非流式的一轮 ====================


def _plain_round(monkeypatch, tmp_path, answer="财务部差旅上限 2000 元。"):
    return drive(monkeypatch, tmp_path,
                 [doc_state(fake_retriever_hits(), answer=answer)], finance_principal())


def test_a_the_frame_ledger_is_identical_with_and_without_the_card(monkeypatch, tmp_path):
    def runner():
        return _plain_round(monkeypatch, tmp_path)

    with_card, without_card = _round_pair(monkeypatch, tmp_path, runner=runner)
    readings = assert_the_card_moves_no_ledger_reading("非流式轮", with_card, without_card)
    # 顺手量一格今天的事实：这一条流只有一枚收尾 text 帧，评分尺那格今天本就是 False。
    assert readings["text_frames"] == 1, readings
    assert ruler._frame_verdict(readings) is False, readings


def test_b_no_card_field_leaks_into_the_text_channel_payload(monkeypatch, tmp_path):
    """正文道载荷闭集：卡片那六格从任何侧门混进来都当场红。"""
    body = _plain_round(monkeypatch, tmp_path)
    card = cards_in(body)[0]["data"]
    allowed = {"type", "content", "cached", "cache_generated_at", "cache_note"}
    frames = [payload for name, payload in wire(body) if name == "text"]
    assert frames, "这一轮一枚正文帧都没有，闭集断言就是空转"
    for payload in frames:
        extra = sorted(set(payload) - allowed)
        assert not extra, "text 帧多出了载荷键 %s：正文道被开了侧门" % extra
        clash = sorted(set(payload) & set(card))
        assert not clash, "text 帧与卡片共用载荷键 %s：两条通道混成一份账" % clash
    # 卡片也不许被别的计数顺手吃掉：step 计数是 R38 用量审计的口径，单独钉一格。
    _readings, bucket = readings_of(body)
    _pair_with, _pair_without = _round_pair(monkeypatch, tmp_path,
                                            runner=lambda: _plain_round(monkeypatch, tmp_path))
    _r2, bucket_off = readings_of(_pair_without)
    assert bucket["steps"] == bucket_off["steps"] == names(body).count("step")


# ==================== C：R210 那两条形状（真流片轮 / 半路断流轮）====================


def _streamed_round(monkeypatch, tmp_path, *, die_after=None, answer=STREAMED_ANSWER):
    """跑一轮**真的在逐片累计**的 /ask，而这一轮手里有可见来源（所以会有卡）。

    生产者是真生成腿（真 ``ChatOpenAI`` + ``httpx.MockTransport`` 走 ``_ResilientModel``）、
    收端折帧与发卡全是真码；假的只有 orchestrator 那一层。``die_after`` 给数字就是 R210 的
    半路断流形状。夹具照借 ``tests/test_r210_break_replaces_the_screen.py``，它一个字没被改。
    """
    from app.common import cache, model_budget
    from app.storage.sessions import SessionRegistry

    from tests.test_sse_sources import doc_agent_result

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    patched = patch_offline(monkeypatch, tmp_path, [])
    hits = fake_retriever_hits()

    def fake_stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")
        if die_after is None:
            message = _clean_leg(answer, sink, "doc")
        else:
            message = _broken_leg(answer, die_after, sink, "doc")
        handed = str(getattr(message, "content", "") or "")
        yield {
            "messages": [],
            "worker_results": {"doc": handed},
            # 🔴 走真证据边界：卡片那几行的出处必须与收尾那枚 sources 同源，否则 C 枚就是在
            # 拿一份假造的来源清单量帧账。
            "agent_results": {"doc": doc_agent_result("doc", hits, handed)},
            "final_answer": handed,
        }

    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(patched, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    return asyncio.run(_ask(patched, finance_principal(), message=QUESTION,
                            session_id="sess-r48-stream"))


def test_c1_a_real_streaming_round_keeps_every_frame_reading_untouched(monkeypatch, tmp_path):
    """判据 ② 的正身：一条**真的在逐片累计**的流，加不加卡片，读数逐位相同。

    这一枚才有牙——A 枚那一轮只有一枚收尾帧，``max_stream_frames`` 与 ``per_stream`` 都只有一
    格可看；这里一条流里十几枚帧，卡片只要混进任何一条腿，账立刻显形。
    """
    def runner():
        return _streamed_round(monkeypatch, tmp_path)

    with_card, without_card = _round_pair(monkeypatch, tmp_path, runner=runner)
    readings = assert_the_card_moves_no_ledger_reading("真流片轮", with_card, without_card)
    assert readings["text_frames"] > 1, readings
    assert readings["max_stream_frames"] > 1, readings
    assert readings["prefix_breaks"] == 0, readings
    assert ruler._frame_verdict(readings) is True, readings


def test_c2_a_half_broken_round_keeps_every_frame_reading_untouched(monkeypatch, tmp_path):
    """R210 的第二条形状：provider 死在半路、离线话术顶上那一轮，卡片同样不进账。

    这一轮的帧序列里有一枚**与后帧不同源**的收尾（R210 立案的就是它），所以它同时也是
    ``prefix_breaks`` 那格的活样本：卡片要能混进正文道，坏形计数第一个动。
    """
    def runner():
        return _streamed_round(monkeypatch, tmp_path, die_after=DIE_AFTER_FRAMES)

    with_card, without_card = _round_pair(monkeypatch, tmp_path, runner=runner)
    readings = assert_the_card_moves_no_ledger_reading("半路断流轮", with_card, without_card)
    assert readings["text_frames"] >= 2, readings
    # 🔴 09-24 订正（总控）：这枚锚原来钉的是「本轮 verdict 今天本就是 False」，那是 **R181-only**
    # 尺子上的事实。R215 并树后尺子读的是六条件，而这一轮（末帧逐字等于终答 + 紧邻一枚
    # answer_correction 的 running step + 每轮至多一枚 + 是本流末帧）恰好就是它豁免的
    # **受控纠正**形状 => verdict 归 True。绿是尺子给的，不是卡片给的：摘掉卡片同一格 verdict
    # 一字不动（由上面那枚共用函数里的 verdict_on == verdict_off 钉住），且原始账没漂——
    # prefix_breaks 照样记着这枚坏形，豁免只体现在净额那一格。真断流那一支仍然读 False，
    # 两形的对偶在同一把尺子上由 tests/test_r218_ruler_self_calibration.py 钉。
    assert readings["prefix_breaks"] == 1, readings
    assert readings["corrective_replacements"] == 1, readings
    assert readings["uncorrected_breaks"] == 0, readings
    assert ruler._frame_verdict(readings) is True, readings


def test_c3_the_card_never_becomes_the_last_text_frame(monkeypatch, tmp_path):
    """末帧就是末帧：卡片载荷里那枚 ``excerpt`` 是正文片段，最容易被当成一帧文字。"""
    body = _streamed_round(monkeypatch, tmp_path)
    readings, bucket = readings_of(body)
    assert bucket["last_text_frame"] == STREAMED_ANSWER, readings
    assert readings["last_frame_sha"] == ruler._sha12(STREAMED_ANSWER), readings
    for payload in cards_in(body):
        for row in payload["data"]["sources"]:
            # 卡片确实带着命中句（它是事实），但那句话不许出现在正文道上——这是「两通道」的正面证据。
            assert row["excerpt"], row
            assert row["excerpt"] not in bucket["last_text_frame"], row["excerpt"][:40]


# ==================== D：反证 ①（本单最重要的一枚）====================


def _crlf(text):
    """本仓 chat.py 是纯 CRLF：锚点按盘上的字面写，不然 ``_TempEdit`` 找不到它。"""
    return text.replace("\n", "\r\n")


#: 发射点整段：改成一枚 ``text`` 帧之后，卡片载荷被扔掉、只把第一枚来源文件名当正文发出去。
#: 终答刻意以同一个文件名开头（见 ``_fake_green_answer``）——那正是 §93 判据 ① 描述的形状。
CALL_ANCHOR = (
    "    return canonical_sse_event(\n"
    '        "answer.headline",\n'
    "        request_id=request_id,\n"
    "        trace_id=trace_id,\n"
    "        task_id=task_id,\n"
    "        sequence=sequence,\n"
    '        status="running",\n'
    "        data=data,\n"
    "    )\n"
)
CALL_MUTANT = (
    "    del data\n"
    '    return text_sse_frame(str(rows[0]["source"]))\n'
)


def _fake_green_answer(body):
    """把终答写成「以卡片第一枚来源文件名开头」：卡片作首帧时它就是终答的前缀。"""
    first = cards_in(body)[0]["data"]
    return str(first["sources"][0]["source"]) + "：一线城市住宿费为每晚 500 元，凭发票据实报销。"


def test_d1_counter_evidence_a_card_sent_as_text_turns_this_pin_red(monkeypatch, tmp_path):
    """反证 ①：发射点改成 ``event: text`` ⇒ 本件的帧账钉**当场变红**，而评分尺当场变绿。

    两件事必须同时发生才叫假绿，所以这里把两份读数与报错原文一起留在记录里：红的这一枚是
    「卡片动了帧账」，绿的那一枚是尺子自己那格 ``criterion_two_holds``。
    """
    answer = FINANCE_DOC + "：一线城市住宿费为每晚 500 元，凭发票据实报销。"
    tracked = _CHAT_PY.read_bytes()                  # 判据①的现场取证：被跟踪文件全程只读
    try:
        with _TempEdit(_CHAT_PY, [(_crlf(CALL_ANCHOR), _crlf(CALL_MUTANT))]) as info:
            sources = _reload()
            with_card = _mutated_round(sources, monkeypatch, tmp_path, answer)
            # 摘卡那一遍摘的就是影子副本那份新码：变异 exec 在同一个模块对象上，身份没换。
            restore = suppress_card(chat)
            try:
                without_card = _mutated_round(sources, monkeypatch, tmp_path, answer)
            finally:
                restore()
            # ① 帧账钉当场红，且红在数字上（不是红在「找不到卡片」那枚守卫上）。
            with pytest.raises(AssertionError) as exc:
                assert_the_card_moves_no_ledger_reading("反证①", with_card, without_card)
            message = str(exc.value)
            print("[r48] 反证① 实际报错原文：", message)
            assert "帧账" in message, "红不在帧账上，这枚反证没打到点上：" + message
            assert "text_frames" in message, "红的不是帧数那一格：" + message
            # ② 同一轮的评分尺自己那格却是绿的：这就是「今晚诚实的红被洗成假绿」的现场。
            readings, _bucket = readings_of(with_card)
            print("[r48] 反证① 假绿读数：text_frames=%s max_stream_frames=%s prefix_breaks=%s "
                  "extra_chars=%s missing_chars=%s verdict=%s" % (
                      readings["text_frames"], readings["max_stream_frames"],
                      readings["prefix_breaks"], readings["extra_chars"],
                      readings["missing_chars"], ruler._frame_verdict(readings)))
            assert ruler._frame_verdict(readings) is True, readings
            assert not cards_in(with_card), "变异后仍按卡片事件名发：那改法没生效"
        assert info["restored"], "被跟踪的 chat.py 没保持原样"
    finally:
        # 🔴 顺序是这枚反证的一半：``_TempEdit.__exit__`` 先把模块 exec 回盘上的字、还原视图，
        # 这里才把夹具再重载一遍。反过来写（在 with 里面 reload）会把变异后的码留在内存里，
        # 同批那十枚用例接着就红在无关格上——这是本班实际踩过的一枚污染，留成注释当路标。
        _reload()
    assert _CHAT_PY.read_bytes() == tracked, "被跟踪的 chat.py 在窗里被改过：影子根没接住变异"
    assert _CHAT_PY.read_bytes().decode("utf-8").count(_crlf(CALL_ANCHOR)) == 1, "发射点没回到原样"


def _mutated_round(sources_module, monkeypatch, tmp_path, answer):
    """变异窗口里跑一轮：用**重新装载过的那份**夹具模块，不然跑的还是内存里的旧码。"""
    return sources_module.drive(monkeypatch, tmp_path,
                                [sources_module.doc_state(fake_retriever_hits(), answer=answer)],
                                sources_module.finance_principal())
