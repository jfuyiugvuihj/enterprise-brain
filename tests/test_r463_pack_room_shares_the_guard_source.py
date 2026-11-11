"""R463 · 装箱的 room 与发请求前那道守卫必须同源（跟进单 §133 五）。

病（09-28 22:25:23 云端窗现读）：装箱交出的题面 ``prompt_tokens=14928``，加上该档声明的输出顶
``declared_max_tokens``，推出 ``required_n_ctx=16464 > MODEL_CONTEXT_TOKENS=16384`` ⇒
``context_limit_exceeded``，同段 ``max_coherent_n_ctx=18064 window_coherent=yes``。装箱那一路把
prompt 塞到边界，而"边界"由**另一处**算式给出——``窗口 − 该档输出顶`` 这同一个减法写在
``input_budget_tokens``（装箱读的那格）与 ``context_window_code``（守卫判拒用的那句
``prompt + cap <= window``）里各抄了一遍，于是自己塞完、再由自己下游那道守卫拒发。客户读到的是
「这个问题我处理不了」，不是慢。本单把它收成一处：``app/agents/contracts.py::prompt_room``。

钉的四件事，与判据一一对上：

- ① 同源：全仓只许一处写 ``窗口 − 该档 declared_max_tokens``；装箱账上那枚 ``room_total`` 与守卫
  判拒用的可用量必须由同一处算出，四格读数逐枚相等（``input_budget_tokens`` /
  ``prompt_room_tokens`` / ``WindowPlan.prompt_room_tokens`` / 拒绝对象里的同名格）。
- ② 边界会咬：``analysis`` / ``report`` / ``code`` / ``qa`` 逐档参数化——装箱产物再大一枚 token
  就**当场少塞一片**，并在账上点名丢的是第几名；整条装不下那一支裁出的桩必须带可见截断标记，
  不许静默丢。
- ③ 反向牙：把 ``declared_max_tokens`` 那一格从 room 里摘掉，①② 的新钉逐档必红，红话点名
  「装箱与守卫不同源」这一句病名，并复现"塞完再由守卫拒"的原病形状。
- ④ 不许放宽：``context_limit_exceeded`` 仍然可达，撞顶那一发仍然不走兜底文案（本单修的是别撞顶，
  不是撞了别报）；逐格对照改前那句 ``prompt + cap <= window``，没有一发请求跨过拒绝线。

全离线：不起服务、不连模型（R56 闸门行必须读到 ``blocked connect attempts to host model port: 0``）、
不动数据库、不碰 ``deploy/**``、不碰评测集本体。模型一律替身。
"""
import logging
import re
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents import nodes, tools
from app.agents.contracts import CONTEXT_LIMIT_CODE, ModelBudget, ModelTier, prompt_room
from app.common.model_budget import (
    ModelContextLimitExceeded,
    authorize,
    estimate_prompt_tokens,
    estimate_text_tokens,
    model_tier_budget,
    window_plan,
)
from app.rag.retrieval_pipeline import (
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_SHELL_RESERVE_TOKENS,
    PROMPT_PACK_MARKER,
    context_pack_room,
    text_pack_tokens,
)

RESERVE = CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS
MARK = tools.PACK_TRUNCATION_MARK
FLOOR = tools.PACK_MIN_STUB_BODY_TOKENS
#: 判据② 点名的三档，另加 ``qa``（问答档走 ``ModelTier.CHAT``，输出顶与 analysis 不同，
#: 用来证明 room 扣的是"本档自己的" declared_max_tokens，而不是全仓那一枚缺省）。
PROFILES = ("analysis", "report", "code", "qa")
#: app/api/v1/chat.py 那句内部失败文案：撞顶那一发不许被洗成它（判据④）。
GENERIC_FALLBACK = "本轮未产出任何结论，请重试或补充数据范围。"
OFFLINE_TEXT = "（离线替身）本机模型不可用，已按降级口径回复。"
#: 在册字段序（与 tests/test_r117_ledger_turn_scoped.py / test_r122 / test_r445 同一把尺）。
PACK_FIELDS = (
    "leg", "tier", "room_total", "room_left", "candidates", "fitted", "dropped", "truncated",
    "stub", "packed_tokens", "ledger_packed_tokens", "prompt_estimate_tokens", "ledger",
    "dropped_labels",
)
#: 逐用例都钉死这扇窗，免得环境里那格把算术吹散；病历那一格另设 16384。
CASE_WINDOW = 8192


@pytest.fixture(autouse=True)
def _clean_ledger(monkeypatch):
    """装箱账是进程内的：逐用例清零，并把窗口钉成 CASE_WINDOW。"""
    tools._pack_ledger.clear()
    tools._retrieval_pack_support.clear()
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", str(CASE_WINDOW))
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


def _tool_config(step_id=None):
    from app.agents.evidence import new_evidence_bag
    from app.common.identity import Principal

    identity = {"username": "r463", "role": "admin", "department": "财务部"}
    conf = dict(identity)
    conf["principal"] = Principal.from_user(identity, auth_source="agent")
    conf["evidence_bag"] = new_evidence_bag()
    conf["thread_id"] = "thread-r463"
    conf["worker"] = "doc"
    conf["step_id"] = step_id or f"trace-r463:{uuid.uuid4().hex[:12]}"
    return {"configurable": conf}, conf["evidence_bag"]


def _header(rank: int) -> str:
    return f"[{rank}] 来源:装箱同源钉.pdf" + chr(10)


def _piece(tokens: int, *, rank: int = 1) -> str:
    """一枚**恰好** ``tokens`` 枚的候选：行头带名次，账上点得出丢的是谁。"""
    header = _header(rank)
    body = tokens - text_pack_tokens(header)
    assert body >= 1, f"{tokens} 枚装不下一片（行头已经吃掉 {text_pack_tokens(header)} 枚）"
    text = header + "房" * body
    assert text_pack_tokens(text) == tokens, (tokens, text_pack_tokens(text))
    return text


def _tile(total: int, pieces: int) -> list:
    """把 ``total`` 枚拆成 ``pieces`` 片（余数落在最后一片），名次逐片唯一。"""
    assert total >= pieces * 12, (total, pieces)
    share = total // pieces
    sizes = [share] * (pieces - 1) + [total - share * (pieces - 1)]
    return [_piece(size, rank=index + 1) for index, size in enumerate(sizes)]


def _pack_lines(pack_log, leg="doc"):
    return [
        _fields(record.getMessage())
        for record in pack_log.records
        if PROMPT_PACK_MARKER in record.getMessage()
        and f"leg={leg}" in record.getMessage()
        and "room_total=" in record.getMessage()
    ]


def _pack(pack_log, units, *, profile=None, leg="doc", keep_first_truncated=False):
    """走**生产**装箱那一路，返回 ``(产物, 这一发的账)``：room 从账上现读，不在本件重算。"""
    before = len(_pack_lines(pack_log, leg))
    config, _ = _tool_config()
    packed = tools._pack_into_prompt_room(
        config, leg=leg, units=units, keep_first_truncated=keep_first_truncated, profile=profile
    )
    lines = _pack_lines(pack_log, leg)
    assert len(lines) == before + 1, f"一发装箱只许打一行账，今天打了 {len(lines) - before} 行"
    return packed, lines[-1]


def _production_room(pack_log, profile, *, leg="doc") -> int:
    """装箱自己账上的 ``room_total``——真源读数，本件不另立第二把尺。"""
    _, line = _pack(pack_log, [], profile=profile, leg=leg)
    return int(line["room_total"])


def _budget(profile):
    return model_tier_budget(tools.pack_profile_tier(profile))


def assert_packing_and_guard_share_the_boundary(profile, room: int) -> None:
    """判据①② 的核心断言：装箱能交出的最大一发，恰好是守卫肯收的最大一发。

    这一枚就是反向牙（判据③）的靶子：把 ``declared_max_tokens`` 从 room 里摘掉，红话必须由这里
    说出病名，不许只报一枚数值不等。
    """
    budget = _budget(profile)
    if room + RESERVE != budget.prompt_room_tokens:
        raise AssertionError(
            f"装箱与守卫不同源：档位 {profile} 的装箱上限 room={room} 枚，加上装箱看不见的那半截 "
            f"prompt（两枚实测预留共 {RESERVE} 枚）推得题面 {room + RESERVE} 枚，而发请求前那道"
            f"守卫认的可用量是 prompt_room_tokens={budget.prompt_room_tokens} 枚（窗口 "
            f"{budget.context_limit_tokens} − 本档声明的输出顶 {budget.max_tokens}），"
            f"两笔算式各算了一遍，差 {room + RESERVE - budget.prompt_room_tokens} 枚——"
            "跟进单 §133 五 那发题面就是这么撞出来的。"
        )
    #: 边界重合：装箱的满格守卫肯收，再多一枚守卫就拒——所以"再大一枚"必须由装箱先咬。
    assert budget.context_window_code(room + RESERVE) is None, profile
    assert budget.context_window_code(room + RESERVE + 1) == CONTEXT_LIMIT_CODE, profile
    authorize(budget, room + RESERVE)
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(budget, room + RESERVE + 1)
    assert refused.value.code == CONTEXT_LIMIT_CODE


def _pad_to_total(messages, target: int) -> list:
    """把 system 段垫到"整串消息恰好 ``target`` 枚"，用守卫自己那把尺现量（一枚 CJK ＝ 一枚）。"""
    padded = list(messages)
    deficit = target - estimate_prompt_tokens(padded)
    assert deficit >= 0, (estimate_prompt_tokens(padded), target)
    padded[0] = SystemMessage(content=padded[0].content + "房" * deficit)
    assert estimate_prompt_tokens(padded) == target, estimate_prompt_tokens(padded)
    return padded


# ==================== 判据①：那一枚减法只许写一处 ====================


def test_the_window_minus_cap_is_computed_in_one_place():
    """四格读数全等：装箱读的、守卫读的、拒绝对象引的、window_plan 报的是同一笔减法。"""
    for profile in PROFILES:
        budget = _budget(profile)
        window, cap = int(budget.context_limit_tokens), int(budget.max_tokens)
        assert window - cap > 0, (profile, window, cap)
        assert budget.prompt_room_tokens == prompt_room(window, cap) == window - cap, profile
        assert budget.input_budget_tokens == max(1, prompt_room(window, cap)), profile

    analysis = model_tier_budget(ModelTier.ANALYSIS)
    assert window_plan(ModelTier.ANALYSIS).prompt_room_tokens == analysis.prompt_room_tokens
    refused = ModelContextLimitExceeded(analysis, analysis.prompt_room_tokens + 1)
    assert refused.prompt_room_tokens == analysis.prompt_room_tokens


def test_the_packer_no_longer_retypes_the_room_formula():
    """装箱那一支不许再去另算一遍 room，也不许自己碰窗口（它只问守卫那一处要可用量）。"""
    import io
    import os

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with io.open(os.path.join(repo, "app", "agents", "tools.py"), encoding="utf-8") as handle:
        packer = handle.read().split("def _pack_into_prompt_room")[1].split("def _get_pipeline")[0]
    assert "context_pack_room(" not in packer, "装箱又去 retrieval 那一侧重算 room，同源就断了"
    assert "pack_room_tokens(" in packer, "装箱不再问守卫那一处要可用量？"
    assert "context_limit_tokens" not in packer, "装箱自己碰窗口，等于又开一处算式"


# ==================== 判据②：逐档参数化，边界会咬 ====================


@pytest.mark.parametrize("profile", PROFILES)
def test_the_room_is_the_guard_number_for_this_profile(profile, pack_log):
    """每档的 room ＝ 窗口 − **本档自己声明的**输出顶 − 那半截 prompt，且与检索侧同值。"""
    budget = _budget(profile)
    tier = tools.pack_profile_tier(profile)
    room = _production_room(pack_log, profile)

    assert budget.tier == tier and budget.max_tokens == model_tier_budget(tier).max_tokens
    assert room == context_pack_room(tier.value) == budget.prompt_room_tokens - RESERVE, profile
    assert room > 0, profile
    assert_packing_and_guard_share_the_boundary(profile, room)


@pytest.mark.parametrize("profile", PROFILES)
def test_one_token_more_drops_a_whole_piece_at_packing(profile, pack_log):
    """装箱产物再大一枚 token 就当场少塞一片：少的是谁，账上点得出，不静默。"""
    budget = _budget(profile)
    room = _production_room(pack_log, profile)

    exact, exact_line = _pack(pack_log, _tile(room, 4), profile=profile)
    assert len(exact) == 4 and exact.packed_tokens == room, exact.packed_tokens
    assert exact.dropped_count == 0 and exact.source_indexes == [0, 1, 2, 3]
    assert exact_line["fitted"] == "4" and exact_line["dropped"] == "0"
    assert exact_line["dropped_labels"] == "-"
    assert_packing_and_guard_share_the_boundary(profile, room)

    units = _tile(room + 1, 4)
    bumped, bumped_line = _pack(pack_log, units, profile=profile)
    assert len(bumped) == 3, "边界不咬：装箱把超出一枚的那一发整发交了出去"
    assert bumped.dropped_count == 1 and bumped.source_indexes == [0, 1, 2]
    #: 少塞的那一片恰好是最后一名，且剩下的房确实装不下它——边界咬在装箱这一侧。
    assert bumped.packed_tokens == text_pack_tokens(units[0]) + text_pack_tokens(units[1]) + (
        text_pack_tokens(units[2])
    )
    assert room - bumped.packed_tokens < text_pack_tokens(units[-1])
    assert budget.context_window_code(RESERVE + bumped.packed_tokens) is None, (
        "少塞之后仍被守卫拒：装箱与守卫不是同一枚边界"
    )

    assert bumped_line["room_total"] == str(room) and bumped_line["fitted"] == "3"
    assert bumped_line["dropped"] == "1" and bumped_line["tier"] == profile
    assert bumped_line["prompt_estimate_tokens"] == str(RESERVE + bumped.packed_tokens)
    assert "[4]" in bumped_line["dropped_labels"], f"丢的那一片没点名：{bumped_line['dropped_labels']}"


@pytest.mark.parametrize("profile", PROFILES)
def test_the_trimmed_piece_carries_a_visible_mark(profile, pack_log):
    """整条装不下那一支：裁出来的桩必须带可见截断标记，落在边界内侧，且正文够读。"""
    budget = _budget(profile)
    room = _production_room(pack_log, profile)
    assert room > FLOOR + text_pack_tokens(MARK) + text_pack_tokens(_header(1)), room

    over = _piece(room + 1, rank=1)
    packed, line = _pack(pack_log, [over], profile=profile, keep_first_truncated=True)

    assert len(packed) == 1, "装不下的整条既没裁也没丢，等于静默丢"
    assert packed[0] != over and text_pack_tokens(over) == room + 1
    assert packed.truncated_count == 1 and packed.stub == tools.PACK_STUB_KEPT
    assert packed.packed_tokens <= room and text_pack_tokens(packed[0]) == packed.packed_tokens
    assert packed[0].endswith(MARK), "少塞的那一片没有可见截断标记"
    assert tools._stub_body_tokens(packed[0], over) >= FLOOR
    assert budget.context_window_code(RESERVE + packed.packed_tokens) is None
    assert line["truncated"] == "1" and line["stub"] == "kept" and line["dropped"] == "0"
    assert line["prompt_estimate_tokens"] == str(RESERVE + packed.packed_tokens)


def test_the_max_emit_fits_a_real_message_shape_and_one_more_does_not():
    """把装箱的满格产物真装进 ReAct 那一串消息：守卫按 ``estimate_prompt_tokens`` 现量，满格肯收，
    再多一枚判拒——装箱与守卫在同一格上分手，不在两格上各说各话。"""
    profile = "analysis"
    budget = _budget(profile)
    room = budget.pack_room_tokens(RESERVE)
    payload = _piece(room, rank=1)
    prefix = [
        SystemMessage(content="你是文档分析腿。"),
        HumanMessage(content="住宿费打款时限是几天？"),
        AIMessage(content="", additional_kwargs={"tool_calls": []}),
    ]
    messages = _pad_to_total(
        prefix + [ToolMessage(content=payload, tool_call_id="call-1")], room + RESERVE
    )

    assert estimate_prompt_tokens(messages) == room + RESERVE == budget.prompt_room_tokens
    assert budget.context_window_code(estimate_prompt_tokens(messages)) is None

    one_more = list(messages)
    one_more[-1] = ToolMessage(content=payload + "房", tool_call_id="call-1")
    assert budget.context_window_code(estimate_prompt_tokens(one_more)) == CONTEXT_LIMIT_CODE


def test_the_case_window_reproduces_the_recorded_shape(monkeypatch):
    """§133 五 那一格重现：满格装箱与满格守卫同值，病历那 80 枚只能来自预留没量到的那半截。"""
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")
    budget = _budget("analysis")
    room = budget.pack_room_tokens(RESERVE)

    assert budget.max_tokens == 1536 and budget.context_limit_tokens == 16384
    assert room == 16384 - 1536 - RESERVE
    assert budget.context_window_code(room + RESERVE) is None
    assert budget.context_window_code(room + RESERVE + 80) == CONTEXT_LIMIT_CODE
    #: 病历读数落在"满格 + 80"那一格上：那 80 枚是预留没量到的题面，不是漏扣的输出顶。
    assert room + RESERVE + 80 - (room + RESERVE) == 80


# ==================== 判据③：反向牙——把 declared_max_tokens 从 room 里摘掉 ====================


def _cap_less_pack_room(self, prefix_tokens: int) -> int:
    """病版本：room 只扣预留，不扣本档声明的输出顶（§133 五 立案时写的那一句病）。"""
    return max(0, int(self.context_limit_tokens) - max(0, int(prefix_tokens)))


@pytest.mark.parametrize("profile", PROFILES)
def test_dropping_the_declared_cap_from_room_breaks_the_pin(profile, pack_log, monkeypatch):
    """摘掉 ``declared_max_tokens`` 那一格：新钉逐档必红，红话点名「装箱与守卫不同源」。"""
    honest_room = _production_room(pack_log, profile)
    cap = _budget(profile).max_tokens

    monkeypatch.setattr(ModelBudget, "pack_room_tokens", _cap_less_pack_room)
    sick_room = _production_room(pack_log, profile)
    assert sick_room == honest_room + cap, "反证不成立：这格变异压根没改变 room"

    with pytest.raises(AssertionError) as caught:
        assert_packing_and_guard_share_the_boundary(profile, sick_room)
    message = str(caught.value)
    assert "装箱与守卫不同源" in message, message
    assert f"差 {cap} 枚" in message, message

    units = _tile(honest_room + 1, 4)
    sick, sick_line = _pack(pack_log, units, profile=profile)
    assert len(sick) == 4, "摘掉输出顶之后装箱仍少塞一片——边界根本没咬在守卫那一格上"
    assert sick.packed_tokens == honest_room + 1
    assert int(sick_line["prompt_estimate_tokens"]) == honest_room + 1 + RESERVE
    #: 原病复现：装箱自认为塞得下（账上没丢一片），守卫在发请求前把整发拒掉。
    assert _budget(profile).context_window_code(RESERVE + sick.packed_tokens) == CONTEXT_LIMIT_CODE


def _profile_blind_pack_room(self, prefix_tokens: int) -> int:
    """病版本二：装箱无视档位，替所有档认下 analysis 那一枚输出顶（缺省被写死回原样）。"""
    from app.common.model_budget import tier_max_tokens

    return max(0, prompt_room(self.context_limit_tokens, tier_max_tokens(ModelTier.ANALYSIS)) - max(0, int(prefix_tokens)))


@pytest.mark.parametrize("profile", ("code", "qa"))
def test_a_profile_blind_room_bills_the_wrong_tier_and_goes_red(profile, pack_log, monkeypatch):
    """反证：room 若不再按"买单那一档自己声明的输出顶"扣，本件的逐档钉必须红，且红话说出病名。"""
    honest = _production_room(pack_log, profile)
    analysis_room = _production_room(pack_log, "analysis")

    monkeypatch.setattr(ModelBudget, "pack_room_tokens", _profile_blind_pack_room)
    sick = _production_room(pack_log, profile)
    assert sick == analysis_room != honest, "反证不成立：这格变异没把档位吃掉"

    with pytest.raises(AssertionError) as caught:
        assert_packing_and_guard_share_the_boundary(profile, sick)
    assert "装箱与守卫不同源" in str(caught.value), str(caught.value)


def test_the_registered_legs_still_bill_at_the_pack_tier(pack_log):
    """三条在册腿今天仍由 analysis 买单：缺省档位没改口，行为与并树前逐字相同。"""
    from app.rag.retrieval_pipeline import CONTEXT_PACK_TIER

    assert tools.pack_profile_tier(None) is ModelTier.ANALYSIS
    assert tools.pack_profile_tier(CONTEXT_PACK_TIER) is ModelTier.ANALYSIS
    for leg in ("doc", "data", "query"):
        room = _production_room(pack_log, None, leg=leg)
        assert room == context_pack_room() == _budget("analysis").pack_room_tokens(RESERVE), leg


def test_the_reverse_pin_is_not_vacuous(pack_log):
    """对照：同源版本在同一份料上既少塞一片、也不被判拒——两把才有差别。"""
    room = _production_room(pack_log, "analysis")
    packed, line = _pack(pack_log, _tile(room + 1, 4), profile="analysis")

    assert len(packed) == 3 and line["dropped"] == "1"
    assert _budget("analysis").context_window_code(RESERVE + packed.packed_tokens) is None


# ==================== 判据④：不许放宽——撞顶仍判拒，且不产兜底文案 ====================


class _RecordingModel:
    def __init__(self, response=None):
        self.calls = []
        self.response = response

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(list(messages))
        return self.response

    def stream(self, *args, **kwargs):  # 判拒走不到这里，留着让形状完整
        self.calls.append("stream")
        yield self.response

    def bind_tools(self, bound):
        return self


def _resilient(tier, primary, fallback):
    return nodes._ResilientModel(
        primary,
        fallback,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )


def test_the_refusal_is_still_reachable_and_still_not_a_canned_reply():
    """撞顶那一发：判拒、不发请求、不调离线回复、不把 21 字兜底文案洗成答案。"""
    config, bag = _tool_config()
    budget = model_tier_budget(ModelTier.ANALYSIS)
    oversized = "数" * (budget.prompt_room_tokens + 1)
    primary, offline = _RecordingModel(), _RecordingModel(AIMessage(content=OFFLINE_TEXT))

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _resilient(ModelTier.ANALYSIS, primary, offline).invoke(
            [HumanMessage(content=oversized)], config=config
        )

    assert refused.value.code == CONTEXT_LIMIT_CODE
    assert primary.calls == [], "题面已判拒还把请求发了出去"
    assert offline.calls == [], "撞顶那一发不许由离线回复接走"
    assert OFFLINE_TEXT not in str(refused.value) and GENERIC_FALLBACK not in str(refused.value)
    statuses = [(item["status"], item["error_code"]) for item in bag["model_statuses"]]
    assert ("failed", CONTEXT_LIMIT_CODE) in statuses, statuses
    assert "model_unavailable" not in " ".join(status for status, _ in statuses), statuses


@pytest.mark.parametrize(
    "window,cap",
    [(4096, 1536), (4096, 512), (8192, 256), (16384, 1536), (1000, 1536), (512, 512)],
)
def test_no_prompt_moves_across_the_refusal_line(window, cap):
    """逐格对照改前那句 ``prompt + cap <= window``：同一条线，一枚都不许多收或少收。"""
    budget = ModelBudget(tier=ModelTier.ANALYSIS, max_tokens=cap, context_limit_tokens=window)
    for prompt_tokens in range(0, window + cap + 12, 7):
        before = None if prompt_tokens + cap <= window else CONTEXT_LIMIT_CODE
        assert budget.context_window_code(prompt_tokens) == before, (window, cap, prompt_tokens)


def test_a_refusal_still_carries_the_same_three_numbers():
    """拒绝对象那三格读数一格没动：本单修的是别撞顶，不是撞了别报。"""
    budget = ModelBudget(tier=ModelTier.ANALYSIS, max_tokens=1536, context_limit_tokens=4096)
    refused = ModelContextLimitExceeded(budget, 2691)

    assert refused.code == CONTEXT_LIMIT_CODE
    assert (refused.prompt_tokens, refused.required_context_tokens, refused.over_by_tokens) == (
        2691, 4227, 131,
    )
    assert refused.prompt_room_tokens == 4096 - 1536


# ==================== 邻域保护：台账字段、档位桥、跨档形状 ====================


@pytest.mark.parametrize("profile", PROFILES)
def test_the_ledger_line_keeps_the_registered_fields_for_every_profile(profile, pack_log):
    """在册字段名与相对顺序一枚不动，一发不多打一行；``tier=`` 交的是买单那一档的名字。"""
    room = _production_room(pack_log, profile)
    packed, line = _pack(pack_log, _tile(room + 1, 3), profile=profile)
    message = [r.getMessage() for r in pack_log.records if PROMPT_PACK_MARKER in r.getMessage()][-1]

    assert _order(message) == PACK_FIELDS, message
    assert sorted(line) == sorted(PACK_FIELDS)
    assert line["tier"] == profile and line["fitted"] == str(len(packed))


def test_the_report_profile_is_read_off_the_lane_bridge_not_copied():
    """``report`` 走 nodes.LANE_TIERS 那座既有的桥；桥改了这里跟着改，本件不抄第二份。"""
    from app.agents.nodes import LANE_REPORT, LANE_TIERS

    assert tools.pack_profile_tier("report") is LANE_TIERS[LANE_REPORT]
    assert tools.pack_profile_tier(None) is LANE_TIERS["analysis"]
    assert tools.pack_profile_tier("code") is ModelTier.CODE


def test_an_unknown_profile_is_refused_not_silently_defaulted():
    with pytest.raises(ValueError) as caught:
        tools.pack_profile_tier("no-such-profile")
    assert "unknown pack profile" in str(caught.value)


def test_the_packed_payload_never_outruns_its_own_tier(pack_log):
    """同一份料换档买单：room 跟着本档输出顶走，输出顶小的一档能多装——这才叫按"该档"扣。"""
    analysis_room = _production_room(pack_log, "analysis", leg="doc")
    pack_log.records.clear()
    code_room = _production_room(pack_log, "code", leg="data")
    analysis, code = _budget("analysis"), _budget("code")

    assert code.max_tokens < analysis.max_tokens
    assert code_room - analysis_room == analysis.max_tokens - code.max_tokens
