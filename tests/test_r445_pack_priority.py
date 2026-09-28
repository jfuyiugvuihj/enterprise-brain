"""R445 · 装箱硬顶：整批装不下时不许只看第一名，要按名次装到装满为止（跟进单 §121 第二节）。

全离线：不连模型、不起服务、不动数据库、不碰 ``chroma_db/**``；检索腿与数据腿一律 monkeypatch
到"能拼出返回串"那一层，``LOCAL_MODEL_NAME`` 由 tests/conftest.py 的哨兵挡住。

钉的六件事（判据 ③ 的 a–f，一枚不少）：

- a) 缺省 ctx 态下复现 metric-02 那一发（``room_left=32``／四条候选全装不下）⇒ 仍然空手报
  「本轮检索预算已用尽」那一句人话，账上 ``fitted=0``，模型侧照旧判拒
  ``context_limit_exceeded``——装箱不许把拒绝洗成兜底文案，也不许少装了还报 ok；
- b) 名次优先于长短：第 2 名整条装得下、第 3 名更短，交出去的必须是第 2 名，而且证据袋
  必须认第 2 名那条 hit（``source_indexes`` 断了就会认错人）；
- c) 扫 room 网格：``fitted=0`` 只许发生在「没有任何一条整条装得下」上，``room_left`` 够装
  最短那一条却归零＝今天的病形状，钉成不复发；
- d) 台账 ``[PromptPack]`` 字段名与相对顺序逐字不变，一发不多打一行也不少打一行；
- e) 低于 ``PACK_MIN_STUB_BODY_TOKENS`` 的桩一律不交，裁进行头里（0 枚正文）同样不交；
- f) 同一个账本键上三腿连发，累计值必须往上涨，后发的 ``room_left`` 必须等于 ``room_total``
  减前几发之和（账本不许被绕过）。

每把都配一枚"摘掉守卫当场红"的反证用例：把 ``_rescue_pack_by_rank`` 换回改前的形状（只裁
``units[0]``）、把门槛钉成 0、把账本键钉成空串……对应那把必须当场失效，钉不许是空的。
"""
import importlib.util
import io
import logging
import os
import re

import pytest

from app.agents import tools
from app.agents.contracts import CONTEXT_LIMIT_CODE, ModelTier
from app.common.model_budget import model_tier_budget, tier_max_tokens
from app.rag.retrieval_pipeline import (
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_SHELL_RESERVE_TOKENS,
    PROMPT_PACK_MARKER,
    context_pack_room,
    text_pack_tokens,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESERVE = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS
MARK = tools.PACK_TRUNCATION_MARK
FLOOR = tools.PACK_MIN_STUB_BODY_TOKENS
#: app/api/v1/chat.py:2762 那句 21 字内部失败文案：判据不许把装箱空手洗成它（本文件只引用
#: 字面做分色对照，不改那一处，也不 import api 层——起 FastAPI 不是本单该付的代价）。
GENERIC_FALLBACK = "本轮未产出任何结论，请重试或补充数据范围。"

#: 在册字段序（与 tests/test_r122_stub_honesty.py 同一枚尺，一枚不改名、不改相对位置）。
PACK_FIELDS = (
    "leg",
    "tier",
    "room_total",
    "room_left",
    "candidates",
    "fitted",
    "dropped",
    "truncated",
    "stub",
    "packed_tokens",
    "ledger_packed_tokens",
    "prompt_estimate_tokens",
    "ledger",
    "dropped_labels",
)


@pytest.fixture(autouse=True)
def _clean_pack_ledger():
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()
    yield
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()


@pytest.fixture
def pack_log(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _fields(line):
    return dict(re.findall(r"([a-z_]+)=(\S+)", line))


def _order(line):
    return tuple(re.findall(r"([a-z_]+)=\S+", line))


def _pack_lines(log, leg):
    return [
        _fields(record.getMessage())
        for record in log.records
        if PROMPT_PACK_MARKER in record.getMessage()
        and f"leg={leg}" in record.getMessage()
        and "room_total=" in record.getMessage()
    ]


def _tool_config(step_id="trace-r445:worker:doc"):
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r445", "role": "admin", "department": "财务部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf["thread_id"] = "thread-r445"
    conf["worker"] = "doc"
    if step_id:
        conf["step_id"] = step_id
    return {"configurable": conf}


def _pin_room(monkeypatch, room_tokens):
    """把 room 钉成想要的数：只动 ``MODEL_CONTEXT_TOKENS``，容量真源不抄第二份。"""
    monkeypatch.setenv(
        "MODEL_CONTEXT_TOKENS",
        str(room_tokens + RESERVE + tier_max_tokens(ModelTier.ANALYSIS)),
    )
    assert context_pack_room() == room_tokens
    return room_tokens


def _unit(index, body_chars):
    """``search_docs`` 拼返回串的那一公式：行头一行 + 正文（正文字数＝枚数，可算准）。"""
    return f"[{index}] 来源:差旅费报销制度.pdf 相关度:0.93\n" + ("住宿费限额按职级分档执行。" * 80)[:body_chars]


def _pack(monkeypatch, room, units, leg="doc", config=None):
    _pin_room(monkeypatch, room)
    return tools._pack_into_prompt_room(
        config or _tool_config(), leg=leg, units=units, keep_first_truncated=True
    )


#: 改前那段救援的原文（基点 ``227949e`` 的 ``app/agents/tools.py:881-891``，逐字抄回来）。
#: 反证用例不靠 monkeypatch：救援今天inline在装箱函数里没有可替换的钩子，所以反证一律走
#: 「改前的可达集合」——那一支只许动 ``units[0]``，把它单独喂进同一个夹具就能量出病形状。
PRE_FIX_RESCUE_SOURCE = """            head = _fit_unit_to_room(str(units[0]), room)
            if head:
                if _stub_body_tokens(head, str(units[0])) >= PACK_MIN_STUB_BODY_TOKENS:
                    fitted, dropped, truncated = [head], units[1:], 1"""

_PRE_FIX_HEADLINE = "head = _fit_unit_to_room(str(units[0]), room)"


# ==================== a) 空手那一发照旧要说人话、照旧判拒 ====================

def test_metric02_shape_still_refuses_and_still_says_why(monkeypatch, pack_log):
    """判据 ③a：缺省 ctx 态下 ``room_left=32`` 四条候选装不下 ⇒ 仍拒、仍说预算用尽。

    形状照抄 run9 的 metric-02：``room_total=1198``，本轮此前已装 1166，剩 32 枚。
    """
    units = [_unit(i, 300) for i in (1, 2, 3, 4)]
    _pin_room(monkeypatch, 1198)
    config = _tool_config()
    key = tools._pack_ledger_key(config)
    assert key and text_pack_tokens(units[0]) > 32 and text_pack_tokens(units[-1]) > 32
    tools._pack_ledger[key] = 1198 - 32

    packed = tools._pack_into_prompt_room(
        config, leg="doc", units=units, keep_first_truncated=True
    )
    out = tools._empty_pack_text("doc", len(units), packed)

    assert len(packed) == 0 and packed.packed_tokens == 0
    assert out.startswith("本轮检索预算已用尽，未取回新料"), out
    assert GENERIC_FALLBACK not in out and out != GENERIC_FALLBACK
    assert "1166" in out and "32" in out, out
    #: 空手不记账：这一发没送出去，账上的余额不许被伪造的消耗推高。
    assert tools._pack_ledger[key] == 1198 - 32
    #: 模型侧照旧判拒：装箱没把 context_limit_exceeded 洗掉（metric-02 实测 2687 枚）。
    budget = model_tier_budget(ModelTier.ANALYSIS)
    assert budget.context_window_code(2687) == CONTEXT_LIMIT_CODE

    line = _pack_lines(pack_log, "doc")[-1]
    assert line["fitted"] == "0" and line["stub"] == "refused" and line["packed_tokens"] == "0"


def test_metric02_pin_bites_without_the_plain_language_guard(monkeypatch):
    """反证 a)：把「说人话」那一格换成 21 字兜底文案，同一把判据必须当场红。"""
    monkeypatch.setattr(tools, "_budget_exhausted_text", lambda used, left: GENERIC_FALLBACK)
    _pin_room(monkeypatch, 40)
    units = [_unit(i, 300) for i in (1, 2, 3)]
    packed = tools._pack_into_prompt_room(
        _tool_config(), leg="doc", units=units, keep_first_truncated=True
    )
    out = tools._empty_pack_text("doc", len(units), packed)
    assert not out.startswith("本轮检索预算已用尽，未取回新料")
    assert out == GENERIC_FALLBACK


# ==================== b) 名次优先于长短，证据袋不许认错人 ====================

def test_rescue_takes_the_highest_rank_that_can_be_delivered(monkeypatch):
    """判据 ③b：第 1 名裁出来的桩不够读，第 2 名整条装得下 ⇒ 必须交第 2 名。

    第 3 名更短，但它排在第 2 名之后、且第 2 名交出去之后剩下的 room 装不下它——本单不许
    为了"多装一条"把名次重排（排序归检索腿）。
    """
    rank1, rank2, rank3 = _unit(1, 300), _unit(2, 12), _unit(3, 4)
    room = 40
    assert text_pack_tokens(rank1) > room
    assert tools._stub_body_tokens(tools._fit_unit_to_room(rank1, room), rank1) < FLOOR
    assert text_pack_tokens(rank2) <= room
    assert text_pack_tokens(rank2) + text_pack_tokens(rank3) > room

    packed = _pack(monkeypatch, room, [rank1, rank2, rank3])

    assert list(packed) == [rank2], packed
    assert packed.source_indexes == [1], packed.source_indexes
    assert packed.truncated_count == 0 and packed.stub == "none"
    assert packed.dropped_count == 2
    assert packed.packed_tokens == text_pack_tokens(rank2)


def test_kept_hits_translate_by_rank_not_by_position(monkeypatch):
    """判据 ③b 的另一半：救回来的是第 2 名，证据袋必须记第 2 名那条 hit。"""
    rank1, rank2 = _unit(1, 300), _unit(2, 12)
    packed = _pack(monkeypatch, 40, [rank1, rank2])
    hits = [{"chunk_index": 1}, {"chunk_index": 2}]

    kept = tools._pack_kept_hits(hits, [rank1, rank2], packed)

    #: 整条送出去那一发不改正文，交回的必须是第 2 名那条 hit 本身（不是 hits[0]）。
    assert kept == [hits[1]], kept
    assert all("content" not in hit for hit in kept), kept

    #: 裁过的桩才需要按实际送出的正文重写 content：名次与正文两件事都得对。
    stub_packed = _pack_stub = tools._pack_into_prompt_room(
        _tool_config(), leg="doc", units=[_unit(1, 400), _unit(2, 300)], keep_first_truncated=True
    )
    if len(stub_packed) == 1 and stub_packed[0].endswith(MARK):
        stub_hits = tools._pack_kept_hits(
            [{"chunk_index": 1}, {"chunk_index": 2}],
            [_unit(1, 400), _unit(2, 300)],
            stub_packed,
        )
        assert len(stub_hits) == 1 and stub_hits[0]["chunk_index"] == stub_packed.source_indexes[0] + 1
        assert stub_hits[0]["content"] == stub_packed[0][
            len(str(stub_packed[0]).split("\n", 1)[0]) + 1 : -len(MARK)
        ]


def test_rank_priority_pin_bites_when_rescue_only_looks_at_first(monkeypatch):
    """反证 b)：同一夹具只喂改前那支够得着的候选（只有第一名），病形状当场回来。"""
    rank1, rank2, rank3 = _unit(1, 300), _unit(2, 12), _unit(3, 4)
    first_only = _pack(monkeypatch, 40, [rank1])
    whole_batch = _pack(monkeypatch, 40, [rank1, rank2, rank3])

    #: 改前的救援只看 units[0]：第一名裁出的桩不够读 ⇒ fitted=0，尽管 room 里还装得下第 2 名。
    assert len(first_only) == 0 and first_only.stub == "refused", first_only
    #: 同一发房账、同一枚门槛，只因为后面那名被看见了，才交得出料——b) 靠的就是这一格差别。
    assert len(whole_batch) == 1 and whole_batch.source_indexes == [1], whole_batch


# ==================== c) fitted=0 只许发生在真装不下上 ====================

def test_empty_handed_only_when_nothing_whole_fits(monkeypatch):
    """判据 ③c：扫 room 网格，``room_left`` 足以装进最短那一条就不许 ``fitted=0``。"""
    units = [_unit(1, 300), _unit(2, 100), _unit(3, 20), _unit(4, 6)]
    prices = [text_pack_tokens(u) for u in units]
    cheapest = min(prices)
    violations = []
    for room in range(0, 160, 5):
        tools._pack_ledger.clear()
        packed = _pack(monkeypatch, room, list(units))
        if len(packed) == 0 and room >= cheapest:
            violations.append((room, cheapest, packed.stub))
        if len(packed):
            #: 交出去的每一段要么整条装得下，要么是够读的桩——不留暗账也不留空壳。
            for piece, index in zip(packed, packed.source_indexes):
                if piece == units[index]:
                    assert text_pack_tokens(piece) <= room
                else:
                    assert piece.endswith(MARK)
                    assert tools._stub_body_tokens(piece, str(units[index])) >= FLOOR
    assert not violations, violations


def test_grid_pin_bites_when_the_first_unit_gates_everything(monkeypatch):
    """反证 c)：按「改前只够得着第一名」那一支扫同一张网格，``fitted=0`` 的病行必须成批回来。"""
    units = [_unit(1, 300), _unit(2, 100), _unit(3, 20), _unit(4, 6)]
    cheapest = min(text_pack_tokens(u) for u in units)
    old_sick = []
    for room in range(0, 160, 5):
        tools._pack_ledger.clear()
        first_only = _pack(monkeypatch, room, units[:1])
        tools._pack_ledger.clear()
        full = _pack(monkeypatch, room, list(units))
        if len(first_only) == 0 and room >= cheapest:
            old_sick.append(room)
            #: 病行那一格，今天的代码必须交得出东西，否则 c) 自己就是空的。
            assert len(full) > 0, room
    assert old_sick, "反证不成立：改前那支也不归零，这把钉是空的，退回"


# ==================== d) 台账字段一枚不改名、一发不多打一行 ====================

def test_ledger_line_keeps_the_registered_field_order(monkeypatch, pack_log):
    """判据 ③d：救援那一发的 ``[PromptPack]`` 行与在册字段序逐字一致，且一发一行。"""
    packed = _pack(monkeypatch, 40, [_unit(1, 300), _unit(2, 12)])
    lines = _pack_lines(pack_log, "doc")
    assert len(lines) == 1, lines
    assert _order(pack_log.records[-1].getMessage()) == PACK_FIELDS
    assert packed.source_indexes == [1]


def test_no_room_line_keeps_the_registered_field_order_too(monkeypatch, pack_log):
    """判据 ③d 的另一头：空手那一发的字段序同样一个字不许动（真机口径要连续）。"""
    _pack(monkeypatch, 4, [_unit(1, 300), _unit(2, 300)])
    lines = [r.getMessage() for r in pack_log.records if PROMPT_PACK_MARKER in r.getMessage()]
    assert len(lines) == 1
    assert _order(lines[0]) == PACK_FIELDS


def test_field_order_check_bites_on_a_renamed_or_extra_field(pack_log):
    """反证 d)：改一枚名或多加一枚字段，这道逐字比对必须当场不成立。"""
    honest = " ".join(f"{name}=1" for name in PACK_FIELDS)
    assert _order(honest) == PACK_FIELDS
    renamed = honest.replace("dropped=1", "drop=1", 1)
    extra = honest + " source_rank=1"
    assert _order(renamed) != PACK_FIELDS
    assert _order(extra) != PACK_FIELDS


# ==================== e) 不够读的桩一律不交 ====================

def test_stub_below_the_floor_is_never_delivered(monkeypatch):
    """判据 ③e：room 太小裁出的桩正文低于门槛就不交，裁进行头里（0 枚正文）也不交。"""
    long_unit = _unit(1, 300)
    for room in (0, 4, 10, 11, 20, 40, 60, 87):
        tools._pack_ledger.clear()
        packed = _pack(monkeypatch, room, [long_unit])
        if len(packed):
            assert tools._stub_body_tokens(packed[0], long_unit) >= FLOOR, (room, packed[0])
        else:
            assert packed.stub in ("refused", "none"), (room, packed.stub)
    #: 87 枚＝标记 10 + 行头 + 门槛 60 的下边界之上仍裁不出够读的桩：真路径是 refused/none。
    tools._pack_ledger.clear()
    refused = _pack(monkeypatch, 40, [long_unit])
    assert len(refused) == 0 and refused.stub == "refused"
    tools._pack_ledger.clear()
    none_stub = _pack(monkeypatch, 5, [long_unit])
    assert len(none_stub) == 0 and none_stub.stub == "none"


def test_stub_floor_pin_bites_when_the_threshold_is_zeroed(monkeypatch):
    """反证 e)：把门槛钉成 0（等于摘掉 R122 那把尺），空壳桩当场又交出去了。"""
    monkeypatch.setattr(tools, "PACK_MIN_STUB_BODY_TOKENS", 0)
    packed = _pack(monkeypatch, 40, [_unit(1, 300)])
    assert len(packed) == 1 and packed[0].endswith(MARK)
    assert tools._stub_body_tokens(packed[0], _unit(1, 300)) < FLOOR
    assert packed.stub == "kept"


def test_blank_candidate_is_never_a_delivery(monkeypatch):
    """判据 ②：全空白的一条不算可用料，不许为了不归零把它当证据交出去。

    前缀填装那一支不归本单管（那里整批装得下，本来就该交），这一枚只看救援那一支：
    room 小到最后一名候选都交不出去时，空白的第二名不许顶上来。
    """
    blank, blank2 = "   \n  ", "\n \t "
    packed = _pack(monkeypatch, 0, [blank, blank2])
    assert len(packed) == 0 and packed.packed_tokens == 0
    assert packed.stub == "none", packed.stub

    tools._pack_ledger.clear()
    long_unit = _unit(1, 300)
    packed = _pack(monkeypatch, 40, [long_unit, blank, blank2])
    assert len(packed) == 0, list(packed)
    assert packed.stub == "refused" and packed.source_indexes == []


# ==================== f) 同一本账不许被绕过 ====================

def test_three_legs_on_one_key_accumulate(monkeypatch, pack_log):
    """判据 ③f：同一账本键上连发三腿，累计值只许涨，后发的 room_left 等于前几发之和扣完。"""
    _pin_room(monkeypatch, 400)
    config = _tool_config(step_id="trace-r445:worker:doc")  # 三腿记在同一本账上（同一 step 键）
    seen = []
    for leg, units in (
        ("doc", [_unit(1, 60), _unit(2, 40)]),
        ("data", [_unit(3, 50)]),
        ("query", [_unit(4, 30)]),
    ):
        packed = tools._pack_into_prompt_room(
            config, leg=leg, units=units, keep_first_truncated=True
        )
        seen.append(packed)
    for previous, current in zip(seen, seen[1:]):
        assert current.ledger_used == previous.ledger_used + previous.packed_tokens
        assert current.room_left == 400 - current.ledger_used
        assert current.room_left < previous.room_left
    assert seen[0].ledger_used == 0
    total = sum(p.packed_tokens for p in seen)
    assert tools._pack_ledger[tools._pack_ledger_key(config)] == total
    assert [len(_pack_lines(pack_log, leg)) for leg in ("doc", "data", "query")] == [1, 1, 1]


def test_accumulation_pin_bites_when_the_key_is_blanked(monkeypatch):
    """反证 f)：把轮身份钉成空串（账本被绕过），第二发照样吃满 room，累计值不涨。"""
    _pin_room(monkeypatch, 400)
    monkeypatch.setattr(tools, "_pack_ledger_key", lambda config: "")
    first = tools._pack_into_prompt_room(
        _tool_config(), leg="doc", units=[_unit(1, 60)], keep_first_truncated=True
    )
    second = tools._pack_into_prompt_room(
        _tool_config(), leg="doc", units=[_unit(2, 40)], keep_first_truncated=True
    )
    assert second.ledger_used == 0 and second.room_left == first.room_left
    assert second.room_left != 400 - first.packed_tokens


# ==================== 取证件自证：读不出要指名，形状变了要红 ====================

def _forensics():
    path = os.path.join(REPO, "scripts", "r445_pack_forensics.py")
    spec = importlib.util.spec_from_file_location("r445_pack_forensics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forensics_names_every_input_it_cannot_read(tmp_path, capsys):
    """判据 ①：取证件读不出必须指名 MISS、退码非 0，不许静默跳过后交一份"全绿"。"""
    fx = _forensics()
    missing = str(tmp_path / "nope.log")
    rc = fx.main(
        [
            "--log", missing,
            "--sidecar", str(tmp_path / "nope.jsonl"),
            "--run9c", str(tmp_path / "nope.jsonl"),
            "--readout", str(tmp_path / "nope.md"),
        ]
    )
    printed = capsys.readouterr().out
    assert rc == 1, printed
    assert "MISS" in printed
    assert os.path.basename(missing) in printed or "日志" in printed, printed


def test_forensics_shape_face_tracks_the_pinned_rescue_source():
    """判据 ① 的自证面：取证件认的「改前形状」与「改后形状」必须与源码现状一致。"""
    fx = _forensics()
    src = io.open(os.path.join(REPO, "app", "agents", "tools.py"), encoding="utf-8").read()
    assert fx.RESCUE_SHAPE_MARK in src, "改后形状读不到：取证件的 SHAPE 面会 MISS"
    assert fx.OLD_SHAPE_MARK not in src, "改前形状又回来了（守卫被摘掉）"
    #: 两枚标记都必须命中真文本：旧的那枚命中基点上抄回来的那段救援原文，
    #: 新的那枚命中今天的按名次扫描——任何一枚悬空，这一格就退化成永真。
    assert fx.OLD_SHAPE_MARK in PRE_FIX_RESCUE_SOURCE
    assert fx.OLD_SHAPE_MARK in _PRE_FIX_HEADLINE
    assert fx.RESCUE_SHAPE_MARK in src.split("def _pack_into_prompt_room", 1)[1]
