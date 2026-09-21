"""R31 判据②③：生成轮流式片段的边界规则（后端合并，前端零改动）。

钉的是 `app/agents/nodes.py` 里的 `StreamPieceMerger` / `StreamPiece` /
`visible_chunk_text` / `publish_stream_pieces` 四枚符号。

为什么合并必须在后端：《计划书》§2.7 实测前端 `sessions.js` 的 `case 'text'` 是逐片追加，
并且用 `state.segments.includes(chunk)` 去重、用 `chunk.includes(seg)` 做"新片整体替换旧片"。
把模型逐 token 的增量原样转成 SSE，标点、空格、短数字会互相撞车而被**静默丢弃**——
表现为答案缺字，不报任何错。所以判据③ 要的是"每片 ≥20 字或按 100 ms 合并、禁单字碎片"，
判据② 要的是"片段时间戳不重叠、逐字比对无缺字"。四门不变量（G1 无损 / G2 不重叠 /
G3 禁单字 / G4 不扣字）逐枚钉在下面。

两把尺的优先级是实测定的：字连续到达时只许尺寸闸说了算，100 ms 只在模型真停手时放行
（理由与真机数字写在 ``test_at_a_realistic_decode_rate_...`` 与 nodes.py 的段落注释里）。

全程离线：时钟是注入的假时钟，没有 socket，也没有模型端口。
"""

import math

import pytest
from langchain_core.messages import AIMessageChunk

from app.agents import nodes

CJK_SENTENCE = (
    "差旅住宿标准按职级分三档，京沪广深一线城市每晚上限五百元，"
    "其余城市每晚上限四百元，超出部分需要事前书面审批。"
)


class _Clock:
    """可控单调时钟：判据② 的时间戳与判据③ 的 100 ms 闸都得能被精确复现。"""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# ==================== 判据③ 的两把尺本身（常量即契约） ====================


def test_the_two_rulers_of_criterion_three_are_the_ratified_numbers():
    """20 字与 100 ms 是裁定值，不是实现细节——把它们改小必须在这里变红。

    反证① 的靶子：把尺寸闸设成 1 字（＝逐 token 直发）时这一枚先红。
    """
    assert nodes.STREAM_PIECE_MIN_CHARS == 20
    assert nodes.STREAM_PIECE_MERGE_SECONDS == pytest.approx(0.1)


def test_the_merge_window_can_never_be_implemented_as_single_character_fragments():
    """"按 100 ms 合并"与"禁单字碎片"同时成立，靠的是这枚地板大于 1。

    反证① 的第二把：地板一旦退化成 1 字，§2.7 陷阱① 就回来了。
    """
    assert nodes.STREAM_PIECE_STALL_FLOOR_CHARS > 1


def test_the_sink_key_is_the_configurable_channel_name():
    assert nodes.STREAM_PIECE_SINK_KEY == "stream_piece_sink"


# ==================== G1 无损（判据② 的"逐字比对无缺字"） ====================


@pytest.mark.parametrize(
    "name,fragments",
    [
        ("per-character", list(CJK_SENTENCE)),
        ("twenty-char-slices", [CJK_SENTENCE[i:i + 20] for i in range(0, len(CJK_SENTENCE), 20)]),
        ("ragged-slices", [CJK_SENTENCE[i:i + 7] for i in range(0, len(CJK_SENTENCE), 7)]),
        ("whitespace-matters", ["第一段。\n", "  ", "第二段。", " ", "第三段。\n"]),
        ("repeated-punctuation", ["。"] * 30),
        ("empty-chunks-in-between", ["", "前半段", "", "后半段", "", "尾巴"]),
        ("non BMP codepoints", ["\U0001F600" * 3, "\U0001F600"]),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_pieces_reassemble_byte_for_byte(name, fragments):
    """把片按到达顺序拼回去，必须与原文逐字节相等：一个字不许丢，一个字不许多。"""
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for fragment in fragments:
        pieces.extend(merger.feed(fragment))
    pieces.extend(merger.finish())
    assert "".join(piece.text for piece in pieces) == "".join(fragments), name


def test_pieces_cover_the_source_in_order_without_gaps_or_repeats():
    """按区间覆盖检查同一件事：相邻两片之间既没有空洞也没有重叠。"""
    fragments = [CJK_SENTENCE[i:i + 9] for i in range(0, len(CJK_SENTENCE), 9)]
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for fragment in fragments:
        pieces.extend(merger.feed(fragment))
    pieces.extend(merger.finish())
    assert pieces, "一段答案一片都没发出去"
    consumed = 0
    for piece in pieces:
        assert piece.text == CJK_SENTENCE[consumed:consumed + len(piece.text)]
        consumed += len(piece.text)
    assert consumed == len(CJK_SENTENCE)


def test_visible_chunk_text_keeps_what_answer_text_strips():
    """片边界必须用不 strip 的取字函数。

    这是本单最容易被"顺手复用现成 helper"做错的一处：`answer_text()` 对整段答案剥一次
    首尾空白是对的，逐片剥就会把每个片界的空格与换行吃掉——拼回去缺字，正是判据② 的靶。
    """
    chunk = AIMessageChunk(content="  第二段开头\n")
    assert nodes.visible_chunk_text(chunk) == "  第二段开头\n"
    assert nodes.answer_text(chunk) == "第二段开头"


def test_visible_chunk_text_reads_the_shapes_a_stream_actually_hands_back():
    assert nodes.visible_chunk_text(AIMessageChunk(content="甲")) == "甲"
    assert nodes.visible_chunk_text({"content": "乙"}) == "乙"
    assert nodes.visible_chunk_text(AIMessageChunk(content=[{"type": "text", "text": "丙"}, "丁"])) == "丙丁"
    assert nodes.visible_chunk_text(AIMessageChunk(content="", tool_call_chunks=[])) == ""


# ==================== G2 时间戳不重叠（判据② 的前半） ====================


def test_piece_intervals_are_monotonic_and_never_overlap():
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    pieces = []
    for index in range(0, len(CJK_SENTENCE), 3):
        pieces.extend(merger.feed(CJK_SENTENCE[index:index + 3]))
        clock.advance(0.02)
    pieces.extend(merger.finish())
    assert len(pieces) > 1
    for previous, current in zip(pieces, pieces[1:]):
        assert previous.end_at <= current.start_at, "两片的时间戳重叠了"
        assert current.end_at >= current.start_at


def test_a_clock_running_backwards_still_cannot_produce_overlapping_pieces():
    """守卫不许依赖"时钟总是好的"：时间源倒着走也只能把区间改窄，不许改重叠。"""
    ticks = iter([500.0, 400.0, 300.0, 200.0, 100.0, 50.0, 10.0])
    merger = nodes.StreamPieceMerger(clock=lambda: next(ticks))
    pieces = []
    for index in range(0, 30, 5):
        pieces.extend(merger.feed("字" * 5))
    pieces.extend(merger.finish())
    assert pieces
    for previous, current in zip(pieces, pieces[1:]):
        assert previous.end_at <= current.start_at


# ==================== G3 禁单字碎片 + 每片 ≥20 字（判据③ 后半） ====================


def test_fast_per_character_output_is_never_emitted_as_single_character_pieces():
    """模型逐 token 吐字（真实节拍：<100 ms/字）时，除末片外每片都必须满 20 字。"""
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    pieces = []
    for char in CJK_SENTENCE:
        pieces.extend(merger.feed(char))
        clock.advance(0.005)  # 5 ms/字：时延闸永远不该触发
    pieces.extend(merger.finish())
    assert len(pieces) == math.ceil(len(CJK_SENTENCE) / 20)
    for piece in pieces[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS
    assert all(len(piece.text) > 1 for piece in pieces), "出现了单字碎片"


def test_the_source_fragment_count_is_recorded_for_each_piece():
    """一片由几个模型增量攒成，是"合并真的在做事"最直接的读数。"""
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for char in CJK_SENTENCE[:25]:
        pieces.extend(merger.feed(char))
    assert [piece.source_fragments for piece in pieces] == [20]
    assert merger.buffered_chars == 5


def test_only_the_last_piece_may_be_shorter_than_the_size_gate():
    """末片允许短：无损优先于整齐，答案末尾没有下一个字来补足。"""
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for char in CJK_SENTENCE[:21]:
        pieces.extend(merger.feed(char))
    assert [len(piece.text) for piece in pieces] == [20]
    tail = merger.finish()
    assert [len(piece.text) for piece in tail] == [1]


def test_an_answer_that_fills_exactly_one_piece_publishes_no_empty_tail():
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for char in CJK_SENTENCE[:20]:
        pieces.extend(merger.feed(char))
    assert merger.finish() == []
    assert "".join(piece.text for piece in pieces) == CJK_SENTENCE[:20]


# ==================== G4 空档闸：隔满 100 ms 就结清，不许扣字 ====================


def test_a_stall_releases_the_buffered_text_instead_of_hoarding_it():
    """G4 不扣字：隔满 100 ms 才来的那一次到达，必须先把已攒的字结清成一片。"""
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    assert merger.feed("第一句") == []              # 3 字，低于地板：继续等
    clock.advance(0.12)
    assert merger.feed("第二句") == []              # 空档到了，但缓冲只有 3 字 < 地板
    clock.advance(0.12)
    pieces = merger.feed("第三句")                   # 此刻缓冲 6 字 ≥ 地板 ⇒ 空档闸放行
    assert [piece.text for piece in pieces] == ["第一句第二句"]
    piece = pieces[0]
    assert piece.start_at == pytest.approx(1000.0)   # 首字到达
    assert piece.end_at == pytest.approx(1000.12)    # 末字到达（不是交出时刻）
    assert piece.emitted_at == pytest.approx(1000.24)
    assert piece.source_fragments == 2


def test_the_idle_gate_does_not_fire_below_the_stall_floor():
    """最坏节拍（一个字停半秒）也不许产出 1–3 字的碎片。

    这一枚就是"禁单字碎片"的具名守卫，反证① 的靶子：地板一旦退化成 1 字，第一次到达
    就发一片单字，立刻红。
    """
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    emitted = []
    for _ in range(4):
        emitted.extend(merger.feed("字"))
        clock.advance(0.5)
    assert emitted == [], "缓冲不足地板就发片，等于把答案打成单字碎片"
    pieces = merger.feed("字")                     # 第 5 次到达：缓冲已满 4 字地板
    assert [piece.text for piece in pieces] == ["字字字字"]
    assert all(piece.chars >= nodes.STREAM_PIECE_STALL_FLOOR_CHARS for piece in pieces)


def test_at_a_realistic_decode_rate_every_non_final_piece_reaches_the_size_gate():
    """真机节拍下的判据③ ：字连续到达时，"每片 ≥20 字"必须一个字都不打折。

    宿主 qwen2.5:3b-instruct 实测约 90 字/s（R31 真机 9 发，见交付说明），合 11 ms/字。
    本单第一版把"按 100 ms 合并"实现成"缓冲起算满 100 ms 即成片"，在这个节拍下真机
    136 片里 127 片不足 20 字（p50=11）——OR 的字面意思过了，判据的目的没做到。这一枚
    就是那种写法不能再回来的钉子。
    """
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    pieces = []
    for char in (CJK_SENTENCE * 4)[:220]:
        pieces.extend(merger.feed(char))
        clock.advance(0.011)
    pieces.extend(merger.finish())
    assert len(pieces) >= math.ceil(220 / nodes.STREAM_PIECE_MIN_CHARS)
    for piece in pieces[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS, (
            f"连续到达的字被时延闸提前放走了：{piece.text!r}"
        )
    assert "".join(piece.text for piece in pieces) == (CJK_SENTENCE * 4)[:220]


def test_an_empty_chunk_never_opens_a_buffer():
    """空增量（tool call 帧、只有 reasoning 的帧）不许产生片，也不许开启时延闸。"""
    clock = _Clock()
    merger = nodes.StreamPieceMerger(clock=clock)
    assert merger.feed("") == []
    clock.advance(60.0)
    assert merger.feed("") == []
    assert merger.finish() == []


def test_the_stall_floor_can_never_be_larger_than_the_size_gate():
    """地板高于尺寸闸会把空档闸变成死代码——构造期就夹住。"""
    merger = nodes.StreamPieceMerger(min_chars=10, stall_floor_chars=99, clock=_Clock())
    assert merger.stall_floor_chars == 10


# ==================== sink：默认关、抛错不许打断答案 ====================


def test_publishing_is_inert_when_nobody_registered_a_sink():
    """判据④ 的一半：没有出口时这条路什么都不做，legacy 形状无从被影响。"""
    pieces = nodes.StreamPieceMerger(clock=_Clock()).feed(CJK_SENTENCE)
    pieces.extend(nodes.StreamPieceMerger(clock=_Clock()).feed(CJK_SENTENCE))
    assert nodes.publish_stream_pieces(None, pieces) is None
    assert nodes.publish_stream_pieces({}, pieces) is None
    assert nodes.publish_stream_pieces({"configurable": {}}, pieces) is None
    assert nodes.publish_stream_pieces({"configurable": "not-a-dict"}, pieces) is None
    assert nodes.publish_stream_pieces({"configurable": {}}, []) is None


def test_a_registered_sink_receives_every_piece_in_order():
    seen = []
    config = {"configurable": {nodes.STREAM_PIECE_SINK_KEY: seen.append}}
    merger = nodes.StreamPieceMerger(clock=_Clock())
    pieces = []
    for char in CJK_SENTENCE:
        emitted = merger.feed(char)
        pieces.extend(emitted)
        nodes.publish_stream_pieces(config, emitted)
    tail = merger.finish()
    pieces.extend(tail)
    nodes.publish_stream_pieces(config, tail)
    assert "".join(piece.text for piece in seen) == CJK_SENTENCE
    assert seen == pieces
    assert len(pieces) > 1


def test_a_broken_sink_cannot_break_the_answer():
    """sink 是一根观测通道，它抛错不许把用户的回答打断，也不许吞掉正文。"""

    def _explode(piece):
        raise RuntimeError("sink died")

    config = {"configurable": {nodes.STREAM_PIECE_SINK_KEY: _explode}}
    pieces = nodes.StreamPieceMerger(clock=_Clock()).feed(CJK_SENTENCE)
    assert nodes.publish_stream_pieces(config, pieces) is None