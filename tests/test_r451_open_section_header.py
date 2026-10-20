"""R451 · 装箱交出去的那一段不许以「未闭合的小节标题」收尾（跟进单 §127 第一节）。

病（基点 ``7532652`` 现读 ``app/agents/tools.py::_analyze_data``，行号会漂、符号不会）：数据腿
把自己那段报告切成多条 unit 时，``--- 数据样本(前15行) ---`` 这一枚标题与它的 JSON 正文是
**两条**。装箱按整条取舍：前缀填装那一支（``pack_prefix_by_rank`` 撞到装不下的正文就 break）与
R445 的名次救援那一支（正文裁出的桩够不上 ``PACK_MIN_STUB_BODY_TOKENS`` 就跳过）都只交标题、
把正文记进 ``dropped`` ⇒ 员工与模型读到的是"承诺了前 15 行样本"而后面一个字节都没有的话。

修法＝判据 ① 的**甲形**：数据腿构造 units 时就把标题与它的正文并成一枚不可分单元，判定只留在
这一处，``_pack_into_prompt_room`` 与 ``_pack_kept_hits`` 一个字都没动，两条支因此天然同一把尺。
乙形（在装箱处认"开放标题"这一形状）不做。理由钉成读数而不是嘴：
``test_a_split_producer_does_ship_the_shell`` 用同一枚房账跑两遍装箱——喂切成两条的 units，
壳当场又出去；喂并成一枚的 units，出不去的就是整段。也就是说病不在装箱那一步，它在切分；
装箱只看得到一串扁平字符串，它没有任何信息知道第 2 条是第 1 条的正文，要在那里拦就得再写一份
小节语法（而且前缀填装那一支的取舍住在 ``app/rag/retrieval_pipeline.py::pack_prefix_by_rank``，
本单写域之外——在那里改还得同时改 ``test_r220_packing_loss.py:181`` 钉着的那个 ``break`` 语义）。

四把可失败钉（判据 ⑤；每把"摘守卫时的真实红数"见交付回执）：
- a) 摘掉合并这道守卫（标题与正文重新切成两条）⇒ 标题壳又交出去 ⇒ 产品路径那几枚当场红；
- b) 把守卫放宽到连"装得下的有料整条"都不交（拿桩门槛去管整条）⇒ 整条交付那两枚红；
- c) 动 ``[PromptPack]`` 台账字段名/序或多打一行 ⇒ 台账那枚红（另配"检查器不是空响"的反证）；
- d) 证据袋存活判据从名次（``_PackedUnits.source_indexes``）退回前缀长度 ⇒ 存活那枚两头翻。

全离线：不连模型、不起服务、不动数据库、不碰 ``chroma_db/**``。数据腿的桩只顶在准入/读文件/
行级口径三处，切 units 与装箱走的都是生产代码。
"""
import json
import logging
import re

import pytest

from app.agents import tools
from app.agents.contracts import ModelTier
from app.common.model_budget import tier_max_tokens
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
TITLE = "--- 数据样本(前15行) ---"
RESULT_HEAD = "数据分析结果:"

#: 在册字段序（与 ``tests/test_r445_pack_priority.py``、``tests/test_r122_stub_honesty.py`` 同一枚
#: 尺）。本单一名不改、一序不动、一行不加（判据 ③ / R122 判据 ③ 口径）。
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
    yield
    tools._pack_ledger.clear()


@pytest.fixture
def pack_log(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _fields(line):
    return dict(re.findall(r"([a-z_]+)=(\S+)", line))


def _order(line):
    return tuple(re.findall(r"([a-z_]+)=\S+", line))


def _pack_lines(log, leg):
    """只取装箱那一行账：证据袋那一条也带 ``[PromptPack]``，但它没有 ``room_total=``。"""
    return [
        _fields(record.getMessage())
        for record in log.records
        if PROMPT_PACK_MARKER in record.getMessage()
        and f"leg={leg}" in record.getMessage()
        and "room_total=" in record.getMessage()
    ]


def _config(step_id: str) -> dict:
    from app.agents.evidence import new_evidence_bag

    return {
        "configurable": {
            "user_id": "7",
            "username": "r451",
            "role": "manager",
            "department": "finance",
            "thread_id": "thread-r451",
            "worker": "data",
            "step_id": step_id,
            "evidence_bag": new_evidence_bag(),
        }
    }


def _pin_room(monkeypatch, room_tokens: int) -> int:
    """把 room 钉成想要的数：只动 ``MODEL_CONTEXT_TOKENS``，容量真源不抄第二份。"""
    monkeypatch.setenv(
        "MODEL_CONTEXT_TOKENS",
        str(room_tokens + RESERVE + tier_max_tokens(ModelTier.ANALYSIS)),
    )
    assert context_pack_room() == room_tokens
    return room_tokens


def _patch_data_leg(monkeypatch, frames, recorded=None):
    """数据腿的公共替身：绕开准入、读文件与行级口径，只留"切 units + 装箱"这一条真路。

    ``recorded`` 给一个列表就把它当证据袋的收集口（钉 d 要用），不给就顶成 no-op。
    """
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.storage import datasets as dataset_storage

    by_path = {f"path-{index}": frame for index, (_, frame) in enumerate(frames)}
    files = [(fname, f"path-{index}") for index, (fname, _) in enumerate(frames)]
    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: (files, None))
    monkeypatch.setattr(dataset_storage.DatasetRegistry, "get_active_by_filename", lambda self, filename: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: by_path[path])
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (
            df,
            {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])},
        ),
    )
    if recorded is None:
        monkeypatch.setattr(tools, "_record_dataset_evidence", lambda config, filename, df: None)
    else:
        monkeypatch.setattr(
            tools, "_record_dataset_evidence", lambda config, filename, df: recorded.append(filename)
        )


def _pack_spy(monkeypatch):
    """给装箱那一步留一份输入/输出副本，好对 units 的真实切法与名次账下断言。"""
    seen: list = []
    original = tools._pack_into_prompt_room

    def spy(config, *, leg, units, keep_first_truncated=False):
        units = list(units)
        packed = original(config, leg=leg, units=units, keep_first_truncated=keep_first_truncated)
        seen.append((leg, units, packed))
        return packed

    monkeypatch.setattr(tools, "_pack_into_prompt_room", spy)
    return seen


def _data_call(seen):
    return [call for call in seen if call[0] == "data"][-1]


def _text_frame(rows: int, chars: int):
    """纯文本帧：没有数值列（``_answer_query`` 交回空），样本正文长度还能按字符数算准。"""
    import pandas as pd

    return pd.DataFrame({"备注": ["数" * max(chars, 1) for _ in range(rows)]})


def _wide_frame(rows: int = 20, columns: int = 40):
    """40 枚数值列的宽帧：概览行与样本正文都远超任何一格残料房账，正是 §127 点名的读数形状。"""
    import pandas as pd

    return pd.DataFrame(
        {
            f"金额指标{index}": [float(row * index) for row in range(rows)]
            for index in range(1, columns + 1)
        }
    )


def _assert_no_open_header(text: str) -> None:
    """交回来的文本里：标题要么不出现，要么后面跟着真正文。裸标题收尾＝本单要治的壳。"""
    assert not text.rstrip().endswith(TITLE), "交回的是一段承诺了样本、正文一个字节都没有的壳：" + text
    _head, sep, tail = text.partition(TITLE)
    if sep:
        assert tail.startswith("\n"), "标题后面紧跟的不是正文：" + repr(tail[:24])
        assert tail[1:].lstrip().startswith(("{", "[")), "标题后面不是样本本体：" + repr(tail[:24])


# ==================== 甲/乙之辩的读数：病在切分，不在装箱 ====================


def test_a_split_producer_does_ship_the_shell(monkeypatch):
    """同一枚房账跑两遍装箱：切成两条 ⇒ 裸标题交出去；并成一枚 ⇒ 出不去的就是整段。"""
    overview = "📁 费用明细.xlsx: 15行 × 1列 — 列: 备注(object)"
    body = json.dumps([{"备注": "数" * 80} for _ in range(15)], ensure_ascii=False)
    room = text_pack_tokens(overview) + text_pack_tokens(TITLE) + 1
    assert text_pack_tokens(body) > room, (text_pack_tokens(body), room)

    split = _pack(monkeypatch, room, [overview, TITLE, body], step="r451:fixture:split")
    merged = _pack(monkeypatch, room, [overview, TITLE + "\n" + body], step="r451:fixture:merged")

    assert list(split) == [overview, TITLE], list(split)
    #: 夹具自检：切成两条时这一发交回的正是一枚裸标题壳（改前的真产物）。
    assert "\n".join(split).rstrip().endswith(TITLE), "夹具不成立：切成两条也没交出壳"
    _assert_no_open_header(RESULT_HEAD + "\n" + "\n".join(merged))
    assert list(merged) == [overview], list(merged)
    assert TITLE not in "\n".join(merged), list(merged)


def _pack(monkeypatch, room, units, step):
    _pin_room(monkeypatch, room)
    tools._pack_ledger.clear()
    return tools._pack_into_prompt_room(
        _config(step), leg="data", units=units, keep_first_truncated=True
    )


# ==================== 钉 a：产品路径两条支都不许交出壳 ====================


def test_prefix_fill_never_ships_the_sample_title_without_its_rows(monkeypatch, pack_log):
    """a·前缀填装那一支：房账够标题不够正文时，改前交出 [概览, 裸标题]，改后只能整段不交。"""
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _text_frame(rows=15, chars=80))])
    seen = _pack_spy(monkeypatch)
    room = _pin_room(monkeypatch, 60)

    out = tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:prefix"))

    _leg, units, packed = _data_call(seen)
    assert units[0].startswith("📁 费用明细.xlsx"), units
    overview_cost = text_pack_tokens(units[0])
    #: 夹具成立性：改前那一枚独立标题装得下，改前那一枚独立正文装不下——正是病形状的那一发。
    assert text_pack_tokens(TITLE) <= room - overview_cost, (room, overview_cost)
    assert text_pack_tokens("\n".join(units[1:])) > room - overview_cost, units
    #: 并成一枚以后：正文没装下 ⇒ 标题也没出去；概览那条有料整条照旧交。
    assert TITLE not in out, out
    assert "📁 费用明细.xlsx" in out, out
    _assert_no_open_header(out)
    line = _pack_lines(pack_log, "data")[-1]
    assert (line["candidates"], line["fitted"], line["dropped"]) == ("2", "1", "1"), line
    assert line["truncated"] == "0" and line["stub"] == "none", line


def test_rescue_never_ships_the_sample_title_without_its_rows(monkeypatch, pack_log):
    """a·名次救援那一支：正文裁出的桩够不上门槛就整段不交，不许退化成"只交标题"。

    这一发正是 §127 点名的在册读数（room=40 的 40 列宽帧：改前 ``fitted=1``、
    ``packed_tokens=9``、交回 ``数据分析结果:\n--- 数据样本(前15行) ---``）。
    """
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _wide_frame(rows=20, columns=40))])
    _pin_room(monkeypatch, 40)

    out = tools._analyze_data("按金额指标1排名", _config("r451:worker:data:rescue"))

    assert TITLE not in out, out
    _assert_no_open_header(out)
    assert MARK not in out, out
    assert out.startswith("本轮检索预算已用尽，未取回新料"), out
    line = _pack_lines(pack_log, "data")[-1]
    assert line["fitted"] == "0" and line["truncated"] == "0" and line["stub"] == "refused", line


def test_no_shell_survives_across_the_room_grid(monkeypatch):
    """a·两条支同一把尺的网格版：逐档扫 room，任何一档都不许交出壳，也不许多杀装得下的概览。"""
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _text_frame(rows=15, chars=80))])
    seen = _pack_spy(monkeypatch)

    violations = []
    for room in range(0, 130, 6):
        tools._pack_ledger.clear()
        _pin_room(monkeypatch, room)
        out = tools._analyze_data("这份表里都有哪些人", _config(f"r451:worker:data:grid:{room}"))
        _leg, units, _packed = _data_call(seen)
        try:
            _assert_no_open_header(out)
            assert TITLE not in out, (room, out)
            #: 概览是一条有料整条：装得下就必须交，装不下才允许整批发空（判据 ② 的那口径）。
            if text_pack_tokens(units[0]) <= room:
                assert RESULT_HEAD in out and "📁 费用明细.xlsx" in out, (room, out)
            else:
                assert "📁 费用明细.xlsx" not in out, (room, out)
        except AssertionError as failure:
            violations.append((room, str(failure)))
    assert not violations, violations


# ==================== 钉 b：装得下的有料整条一枚都不许多杀 ====================


def test_a_cheap_whole_section_still_goes_out_with_its_rows(monkeypatch, pack_log):
    """b·门槛只管桩不管整条：样本正文比 ``PACK_MIN_STUB_BODY_TOKENS`` 还短，装得下就得交。

    这一枚是"过度收紧"的靶子：把桩门槛那把尺挪去量整条，或凡是带标题的小节一律不交，本枚
    当场红——那正是跟进单 §121③c 刚治好的病形状换个格子复发（``test_r445_pack_priority.py``
    的钉 b/c 在同一件事上盯着另一条支）。
    """
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _text_frame(rows=2, chars=1))])
    _pin_room(monkeypatch, 400)

    out = tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:whole"))

    assert TITLE in out, out
    assert '"备注": "数"' in out, out
    _assert_no_open_header(out)
    assert MARK not in out, out
    body = out.partition(TITLE + "\n")[2]
    assert text_pack_tokens(body) < FLOOR, (text_pack_tokens(body), body)
    line = _pack_lines(pack_log, "data")[-1]
    assert line["dropped"] == "0" and line["stub"] == "none", line
    assert int(line["fitted"]) == int(line["candidates"]) == 2, line


def test_rescue_still_delivers_a_later_files_whole_section(monkeypatch, pack_log):
    """b·救援那一支同尺：前面几名整批装不下时，后面那家的整段（标题+正文）必须照样交得出。"""
    _patch_data_leg(
        monkeypatch,
        [("甲表.xlsx", _wide_frame(rows=20, columns=40)), ("乙表.xlsx", _text_frame(rows=2, chars=1))],
    )
    seen = _pack_spy(monkeypatch)
    _pin_room(monkeypatch, 60)

    out = tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:two-files"))

    _leg, units, packed = _data_call(seen)
    assert len(units) == 5, units
    assert "📁 甲表.xlsx" not in out, out
    assert "📁 乙表.xlsx" in out, out
    assert TITLE in out and '"备注": "数"' in out, out
    _assert_no_open_header(out)
    assert packed.source_indexes == [3, 4], packed.source_indexes
    line = _pack_lines(pack_log, "data")[-1]
    assert line["fitted"] == "2" and line["dropped"] == "3" and line["stub"] == "none", line


def test_the_sample_section_is_one_unit_at_the_source(monkeypatch):
    """甲形自身的形状钉：units 里标题与正文同在一枚，而整批装得下时返回串逐字节不变。"""
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _text_frame(rows=3, chars=4))])
    seen = _pack_spy(monkeypatch)
    _pin_room(monkeypatch, 4000)

    out = tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:shape"))

    _leg, units, _packed = _data_call(seen)
    sections = [unit for unit in units if TITLE in unit]
    assert len(sections) == 1, units
    assert sections[0].startswith(TITLE + "\n"), sections
    assert json.loads(sections[0].split("\n", 1)[1]), sections[0]
    #: 装得下那一发与改前逐字节相同：并成一枚只是不再在标题与正文之间多切一刀。
    assert out == RESULT_HEAD + "\n" + "\n".join(units), out


def test_a_trimmed_sample_section_still_carries_real_rows(monkeypatch):
    """补强 a：桩形态下交出去的也是"标题 + 真样本前缀"，桩门槛本身一个字没动。"""
    body = json.dumps([{"备注": "数" * 40} for _ in range(15)], ensure_ascii=False)
    unit = TITLE + "\n" + body
    assert text_pack_tokens(unit) > 200, text_pack_tokens(unit)

    packed = _pack(monkeypatch, 200, [unit], step="r451:worker:data:stub")

    assert len(packed) == 1, list(packed)
    assert packed[0].endswith(MARK), packed[0]
    assert tools._stub_body_tokens(packed[0], unit) >= FLOOR, packed[0]
    assert packed[0].startswith(TITLE + "\n["), packed[0]
    _assert_no_open_header("\n".join(packed))


# ==================== 钉 c：台账字段一枚不改名、不改序、不加行 ====================


def test_the_data_leg_still_writes_exactly_one_registered_pack_line(monkeypatch, pack_log):
    """c·这一发装箱只许留下一行账，字段名与相对顺序逐字不动（判据 ③）。"""
    _patch_data_leg(monkeypatch, [("费用明细.xlsx", _text_frame(rows=2, chars=1))])
    _pin_room(monkeypatch, 400)

    tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:ledger"))

    lines = [
        record.getMessage() for record in pack_log.records if PROMPT_PACK_MARKER in record.getMessage()
    ]
    assert len(lines) == 1, lines
    assert _order(lines[0]) == PACK_FIELDS, lines[0]
    fields = _fields(lines[0])
    assert fields["leg"] == "data", fields
    assert int(fields["fitted"]) + int(fields["dropped"]) == int(fields["candidates"]), fields
    assert fields["stub"] in ("none", "kept", "refused"), fields


def test_the_field_order_check_bites_on_a_renamed_or_added_field():
    """c 的反证：这道逐字比对不是空响——改名、多加字段、改序都当场不成立。"""
    honest = " ".join(f"{name}=1" for name in PACK_FIELDS)
    assert _order(honest) == PACK_FIELDS
    assert _order(honest.replace("dropped=1", "drop=1", 1)) != PACK_FIELDS
    assert _order(honest + " open_header=1") != PACK_FIELDS
    assert _order(" ".join(f"{name}=1" for name in reversed(PACK_FIELDS))) != PACK_FIELDS


# ==================== 钉 d：证据袋存活线继续按名次判 ====================


def test_the_dataset_survives_by_rank_not_by_prefix_length(monkeypatch):
    """d·存活判据（R112 复验第 2 条）：交出去的是名次 [3,4]，前缀长度那一读法会认错文件。

    把 ``_ds_index in set(fitted.source_indexes)`` 退回 ``_ds_index < len(fitted)``，本枚两头都翻：
    甲表一名都没出去却被记成"模型读过它"，乙表整段真出去了反而不记。
    """
    recorded: list = []
    _patch_data_leg(
        monkeypatch,
        [("甲表.xlsx", _wide_frame(rows=20, columns=40)), ("乙表.xlsx", _text_frame(rows=2, chars=1))],
        recorded=recorded,
    )
    seen = _pack_spy(monkeypatch)
    _pin_room(monkeypatch, 60)

    out = tools._analyze_data("这份表里都有哪些人", _config("r451:worker:data:survival"))

    _leg, units, packed = _data_call(seen)
    heads = [index for index, unit in enumerate(units) if unit.startswith("📁")]
    assert heads == [0, 3], units
    assert packed.source_indexes == [3, 4], packed.source_indexes
    assert recorded == ["乙表.xlsx"], recorded
    #: 夹具真的能分辨两种读法：前缀长度那一读法在这发里记的是没送出去那一家。
    assert [index for index in heads if index < len(packed)] == [0], heads
    assert "📁 甲表.xlsx" not in out, out
