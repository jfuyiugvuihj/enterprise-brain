# -*- coding: utf-8 -*-
"""R116 · 把装箱 room 从"按估算"换成"按实测 prompt_tokens 复算"（跟进单 §54 / §57 / §62 二）。

四件事，全离线：不连模型、不起服务、不动数据、不跑评测采集，也不读仓库外那份 run5 保全日志
（所有真机数都以 ``scripts/perf_probe_run5_ledger.py`` 里烘进仓库的实测表为源）。

1. 判据 2（§62 二第 2 笔）：run5 那 17 枚 ``stub=refused``（全部 ``fitted=0``）按实测
   ``prompt_tokens`` 复算 room 之后有几枚能变成**整条实料**——答案逐枚算出来。
2. 判据 3（§62 二第 3 笔）：装箱自身开销拆账，点名 ``data-10``(177.8 s) 与 ``insight-04``
   (160.3 s、``evidence_n=0`` 却最慢)，并给全量占比。
3. 判据 4（§57 追加 1）：``perf_probe_prodpath.py`` 的 ``cn_text(500)`` 手抄改走
   ``perf_probe_rounds.doc_content_cap()`` 只读 ast 真源，读不到真源就地硬失败。
4. 判据 5（§57 追加 2）：``perf_probe_rounds`` 里"synthetic 500-char chunk overstates ...
   ~4x"那句带日期的历史实测——今天重量对不上，已标注旧口径并钉住新数。
5. 判据 6（§62 二第 1 笔）：``stub=`` 台账在真机上没铺满三条腿——**只取证与定性**，
   要补字段得碰的产品文件不在本单写域内，一行都不动（结论见 ``delivery`` 说明）。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import os
import pathlib
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from app.rag.retrieval_pipeline import (  # noqa: E402
    CONTEXT_HISTORY_RESERVE_TOKENS,
    CONTEXT_SHELL_RESERVE_TOKENS,
    DOC_HIT_CONTENT_CHARS,
    context_pack_capacity,
    context_pack_room,
    text_pack_tokens,
)
from scripts import perf_probe_run5_ledger as run5  # noqa: E402

perf_probe_rounds = importlib.import_module("perf_probe_rounds")

REFUSED_PACKS = run5.records(run5.MEASURED_REFUSED_RUN5, run5.REFUSED_FIELDS)
REFUSED_IDS = ["%s:%s#%d" % (row["row_id"], row["leg"], row["refused_seq"]) for row in REFUSED_PACKS]
#: 🔴 下面三枚全是**历史具名常数**：它们记的是 run5 当时刻被测代码自己的预留与 room，
#: 不是今天的现值。R119（跟进单 §55 反案）把 ``CONTEXT_SHELL_RESERVE_TOKENS`` /
#: ``CONTEXT_HISTORY_RESERVE_TOKENS`` 从 632/322 重排成实测值之后，"现值"与"run5 当时的值"
#: **已经不同源**：台账里的 ``room_left`` 是按 1606 那份房算出来的，拿今天的 room 去反推
#: ``over_reserve`` 会把两笔账混成一笔（今天的房越少，算出来的"估窄"就越大，那是自己的改动
#: 而不是真机的事实）。所以本文件的复算一律锚在 run5 自己的那套数上；要引用今天的口径，
#: 必须先 ``--emit-table`` 重跑一遍采集、把新表烘进来，再另立一单复算。
RUN5_RESERVE = run5.RUN5_RESERVE                      # run5 当时：壳 632 + 历史 322
RUN5_CAPACITY = run5.RUN5_CAPACITY                    # run5 当时 analysis 档容量
RUN5_ESTIMATED_ROOM = RUN5_CAPACITY - RUN5_RESERVE    # =1606，与台账 room_total 逐行同值


def _source(name: str) -> str:
    return io.open(os.path.join(REPO, "scripts", name), encoding="utf-8").read()


def _function(name: str, source: str = None, path: str = "perf_probe_rounds.py"):
    tree = ast.parse(source if source is not None else _source(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("脚本里没有函数 %s：本单取证的前提已经变了" % name)


def _reserve() -> int:
    return CONTEXT_SHELL_RESERVE_TOKENS + CONTEXT_HISTORY_RESERVE_TOKENS


@pytest.fixture
def room_sources():
    """交出**run5 当时**的（容量, 估算 room）：复算真机台账只能用真机那套尺。

    R116 刚立的时候这里现取被测真源（``context_pack_capacity()`` / ``context_pack_room()``），
    因为当时"现值 == run5 值"。R119 把预留按实测重排之后两者不再相等，于是改成显式取历史
    常数——这不是放宽，恰恰是把"复算不许被今天的改动污染"这条钉死：谁再动预留，
    ``test_run5_anchor_is_history_and_today_is_a_different_pair`` 立刻把两副口径摆出来。
    """
    return RUN5_CAPACITY, RUN5_ESTIMATED_ROOM


# ==================== 判据 2：17 枚 refused 按实测 room 复算 ====================


def test_run5_refused_ledger_is_the_seventeen_the_board_named():
    """先把尺子对齐看板：run5 就是 17 枚 refused，且每一枚都 ``fitted=0``、不记账。"""
    assert len(REFUSED_PACKS) == 17, "跟进单 §62 与看板 §4BH.12 都记 17 枚，现表 %d 枚" % len(REFUSED_PACKS)
    assert len(set(REFUSED_IDS)) == 17, "17 枚必须彼此可辨（同腿连拒两发靠 refused_seq 分开）"
    assert all(row["fitted"] == 0 for row in REFUSED_PACKS), "refused 台账里混进了送出料的发"
    assert all(row["stub"] == "refused" for row in REFUSED_PACKS)
    assert all(row["packed_tokens"] == 0 for row in REFUSED_PACKS), "拒发不记账：送出枚数必须为 0"
    assert {row["room_total"] for row in REFUSED_PACKS} == {RUN5_ESTIMATED_ROOM}


def test_refused_ledger_matches_the_pinned_last_pack_rows():
    """两张实测表必须互相咬合：refused 表里的发， room_left 与单价都同源于逐发台账。"""
    pinned = {
        (row["row_id"], row["leg"]): row
        for row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)
    }
    for pack in REFUSED_PACKS:
        mate = pinned.get((pack["row_id"], pack["leg"]))
        assert mate is not None, "%s/%s：refused 表里有它，逐发台账里却没有" % (pack["row_id"], pack["leg"])
        assert pack["unit_price_tokens"] == mate["unit_price_tokens"], (
            "%s/%s：两表同腿单价不一致，反事实用的尺子就成了两套" % (pack["row_id"], pack["leg"])
        )
        assert pack["room_total"] == mate["room_total"]
    refused_last = [key for key, row in pinned.items() if row["stub"] == "refused"]
    assert len(refused_last) == 14, (
        "逐发台账（每题每腿只取最后一发）里 14 枚 refused＝「这一腿到收尾还是空手」；"
        "全量 17 枚里另有 3 枚是同腿后面还送出过料的中间发（靠 refused_seq 分辨）"
        "——两个数各自有用，不许混为一谈"
    )


@pytest.mark.parametrize("pack", REFUSED_PACKS, ids=REFUSED_IDS)
def test_each_refused_pack_becomes_whole_material_under_measured_room(pack, room_sources):
    """逐枚回答"这发拒掉的料，按实测 room 能不能送出去"：只认**整条**，裁尾桩不算。

    口径与探针模块说明同一份：实测壳＝该发之后第一发 ``tier=analysis`` 的 ``prompt_tokens``
    减 ``ledger_packed_tokens``；实测 room＝容量减壳；剩余房＝``room_left`` 加回被多扣的那截。
    候选单价取该题该腿整条送出那几发里最贵的均价，宁可高估料价，不给装箱放水。
    """
    capacity, estimated = room_sources
    assert estimated == pack["room_total"], (
        "今天真源估算 room=%d 与 run5 记的 %d 不等：预留或容量动过，这张表得重测"
        % (estimated, pack["room_total"])
    )
    shell = run5.measured_shell(pack)
    assert shell > 0, "配对配错了：实测壳不是正数"
    extra = run5.over_reserve(pack, capacity, estimated)
    room_b = max(0, pack["room_left"] + extra)
    prices = run5.replay_prices(pack)
    assert len(prices) == pack["candidates"]
    assert min(prices) > pack["room_left"], (
        "拒发的前提是每条候选都比当时的剩余房贵，反推的价表不自洽：%r" % prices
    )
    fitted, dropped, used = run5.fit_prices(prices, room_b)
    assert fitted > 0, (
        "%s/%s 第 %d 发：真机 room_left=%d 拒了 %d 条；实测壳 %d 枚（预留 %d 枚）复算剩余房 %d 枚，"
        "最贵单价 %d 枚——按这个房仍一条装不下，本单结论要重写"
        % (pack["row_id"], pack["leg"], pack["refused_seq"], pack["room_left"], pack["candidates"],
           shell, _reserve(), room_b, max(prices))
    )
    assert fitted + dropped == pack["candidates"]
    assert used <= room_b


def test_answer_to_criterion_two_all_seventeen_refused_packs_turn_into_material(room_sources):
    """§62 二第 2 笔要的那枚**数字**：17 枚全部能变实料，合计 31 条整料（逐枚点名）。"""
    answer = []
    for pack in REFUSED_PACKS:
        capacity, estimated = room_sources
        extra = run5.over_reserve(pack, capacity, estimated)
        fitted, dropped, used = run5.fit_prices(
            run5.replay_prices(pack), max(0, pack["room_left"] + extra)
        )
        answer.append((pack["row_id"], pack["leg"], pack["refused_seq"], fitted, dropped, used))
    assert [row for row in answer if row[3] > 0] == answer, "有拒发按实测房仍然装不出整料，答案不是 17"
    assert len(answer) == 17
    assert sum(row[3] for row in answer) == 31, "整料合计变了（现 %d）：反事实单价或表动过" % sum(r[3] for r in answer)
    assert sum(row[5] for row in answer) == 8961, (
        "送出的枚数合计（现 %d）是判据 2 的账面口径，钉死防漂移" % sum(row[5] for row in answer)
    )


def test_measured_room_recalculation_inputs_come_from_the_pinned_reserve(room_sources):
    """复算只用三枚**历史**真源数：run5 的容量、run5 的估算 room、run5 的预留。

    原来的第二行是 ``assert _reserve() == 954``——那是把"今天的现值"当"run5 当时的事实"用，
    R119 重排预留后这枚断言必然红。立意正确的说法是：run5 当时的壳+历史预留就是 954，
    它与今天的现值无关，所以这里比对历史常数，不再比对 ``_reserve()``。
    """
    capacity, estimated = room_sources
    assert capacity - estimated == RUN5_RESERVE
    assert RUN5_RESERVE == 954, "run5 当时的预留记成 %d 枚，看板 §4BH.11 的账要重对" % RUN5_RESERVE
    assert estimated == RUN5_ESTIMATED_ROOM == 1606
    # 台账每行都记着真机当时的 room_total，它必须等于历史锚点；容量本身另核一枚。
    totals = {row["room_total"] for row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)}
    assert totals == {RUN5_ESTIMATED_ROOM}, f"台账 room_total 不再单一：{sorted(totals)}"
    assert RUN5_CAPACITY == 2560 and RUN5_RESERVE + RUN5_ESTIMATED_ROOM == RUN5_CAPACITY
    shells = [
        run5.measured_shell(row)
        for row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)
    ]
    assert min(shells) == 90 and max(shells) == 1154, "真机壳的量程动了：room 估窄这枚结论的边界要重描"


def test_run5_anchor_is_history_and_today_is_a_different_pair():
    """R119 追加：现值已按实测重排，两副口径不同源——over_reserve 表不重烘就不许引用。"""
    live_reserve = _reserve()
    live_capacity, live_room = context_pack_capacity(), context_pack_room()
    assert live_capacity - live_room == live_reserve, "今天的容量/room/预留本身就对不上"
    assert live_reserve != RUN5_RESERVE, (
        f"现值预留仍是 {RUN5_RESERVE} 枚：R119 的重排没落地，本文件的历史口径写法要退回"
    )
    assert (live_capacity, live_room) != (RUN5_CAPACITY, RUN5_ESTIMATED_ROOM), (
        "今天的 room 与 run5 的 room 还同源：台账锚点白拆了"
    )
    assert RUN5_ESTIMATED_ROOM > live_room, (
        f"今天的估算 room {live_room} 反而比 run5 当时 {RUN5_ESTIMATED_ROOM} 大："
        "over_reserve 的方向变了，判据 2 那句话得整个重写"
    )
    # 引用今天的口径谈 run5 的估窄，必须先重烘台账；这里把差值当场摊开，不许含混。
    drift = RUN5_ESTIMATED_ROOM - live_room
    assert drift == live_reserve - RUN5_RESERVE, (
        f"room 少 {drift} 枚而预留多 {live_reserve - RUN5_RESERVE} 枚，两笔账合不上"
    )


# ==================== 判据 3：打包耗时 vs 生成长度 ====================

COST_ROWS = run5.records(run5.MEASURED_COST_LONG_TAIL_RUN5, run5.COST_FIELDS)


def test_the_two_named_long_tail_questions_pay_for_generation_not_packing():
    """点名 ``data-10``(177.8 s) 与 ``insight-04``(160.3 s)：慢在模型往返，不在装箱。"""
    assert [row["row_id"] for row in COST_ROWS] == ["data-10", "insight-04"]
    for row in COST_ROWS:
        assert row["wall_s"] > 150.0, row["row_id"]
        assert row["model_s"] / row["wall_s"] > 0.90, (
            "%s：模型往返 %s s 只占墙钟 %s s 的 %.1f%%，拆账口径变了"
            % (row["row_id"], row["model_s"], row["wall_s"], 100 * row["model_s"] / row["wall_s"])
        )
        assert row["pack_ready_calls"] == row["pack_calls"] == 2, (
            "%s：装箱 %d 发里严格档（料已就绪→装箱行）只认到 %d 发，上界口径要说清"
            % (row["row_id"], row["pack_calls"], row["pack_ready_calls"])
        )
        assert row["pack_s"] < 0.2 and row["pack_ready_s"] == row["pack_s"], row["row_id"]
        assert row["evidence_n"] == 0, "%s 的 evidence_n 不是 0，「最慢却零证据」这枚问句要重问" % row["row_id"]
        assert row["model_s"] + row["pack_s"] + row["other_s"] + row["unattributed_s"] == pytest.approx(
            row["wall_s"], abs=0.05
        ), "%s：四档拆账合不上墙钟" % row["row_id"]
    data10, insight04 = COST_ROWS
    assert (data10["wall_s"], data10["model_s"], data10["pack_s"], data10["other_s"]) == (
        177.8, 165.63, 0.018, 11.82)
    assert data10["unattributed_s"] == 0.36 and insight04["unattributed_s"] == 1.09
    assert (data10["model_calls"], data10["answer_chars"]) == (20, 393)
    assert (insight04["wall_s"], insight04["model_s"], insight04["pack_s"], insight04["other_s"]) == (
        160.3, 148.7, 0.185, 10.32)
    assert (insight04["model_calls"], insight04["answer_chars"]) == (17, 809)
    assert data10["pack_s"] < insight04["pack_s"], (
        "装箱耗时上界 data-10 %s s / insight-04 %s s：两枚都在 0.2 s 以下，慢的是模型往返"
        % (data10["pack_s"], insight04["pack_s"])
    )
    assert insight04["answer_chars"] > data10["answer_chars"] and insight04["model_calls"] < data10["model_calls"], (
        "insight-04 字多、往返少，data-10 字少、往返多——两枚的慢法不同，但都与装箱无关"
    )


def test_packing_share_of_the_whole_run_is_a_fifth_of_a_percent():
    """全量拆账：282 发装箱占 4378.6 s 墙钟的多少，装箱最慢的那一题是谁。"""
    aggregate = run5.MEASURED_COST_RUN5_AGGREGATE
    assert aggregate["questions"] == 105 and aggregate["pack_lines"] == 282
    share = 100.0 * aggregate["pack_s_total"] / aggregate["wall_s_total"]
    assert round(share, 3) == aggregate["pack_share_of_wall_pct"] == 0.215, (
        "装箱占墙钟 %.3f%%：占比变了这段说明要改写" % share
    )
    assert aggregate["model_s_total"] == 3775.34 and aggregate["other_s_total"] == 546.54
    four = (aggregate["model_s_total"] + aggregate["pack_s_total"]
            + aggregate["other_s_total"] + aggregate["unattributed_s_total"])
    assert four == pytest.approx(aggregate["wall_s_total"], abs=0.6), (
        "四档拆账（含刻意不塞进任何一档的那 %s s）必须合上墙钟" % aggregate["unattributed_s_total"]
    )
    assert aggregate["slowest_pack_question"] == "chat-11"
    assert aggregate["pack_ready_s_total"] == 4.87
    assert aggregate["max_pack_s_one_question"] == 1.38
    assert aggregate["refused_total"] == 17


def test_generated_length_is_reported_as_chars_because_the_endpoint_logs_no_usage():
    """「生成长度」只能给字数：兼容端点 ``/v1`` 不落 usage，全日志 0 枚 ``completion_tokens``。"""
    assert [row["native_tokens"] for row in COST_ROWS] == [0, 0]
    assert [row["native_seconds"] for row in COST_ROWS] == [0.0, 0.0]
    source = _source("perf_probe_run5_ledger.py")
    assert "completion_tokens" in source, "探针说明里那句「只有原生腿落生成 token 数」的前提要重看"


# ==================== 判据 4：prodpath 不再手抄 500 ====================


def test_prodpath_takes_the_content_cap_from_the_ast_route_not_a_hand_copy():
    """那处 ``cn_text(500)`` 必须换成 ``doc_content_cap()``，且读不到真源就地硬失败。"""
    source = _source("perf_probe_prodpath.py")
    assert "cn_text(500)" not in source, "prodpath 里又出现手抄的 500：真源读数被绕过了"
    assert "cn_text(cap)" in source, "合成料没用真源读数"
    body = ast.get_source_segment(source, _function("doc_content_cap", source, "perf_probe_prodpath.py")) or ""
    assert "_load_rounds_probe()" in body, "prodpath 的 doc_content_cap() 不再走 perf_probe_rounds 的路子"
    assert "RuntimeError" in body, "读不到真源不硬失败，就会悄悄退回一个自己编的数"
    assert "cn_text(cap)" in source, "装箱探针的合成料没有用真源读数"
    rounds_body = ast.get_source_segment(_source("perf_probe_rounds.py"), _function("doc_content_cap")) or ""
    assert "DOC_HIT_CONTENT_CHARS" in rounds_body and "RuntimeError" in rounds_body


def test_rounds_probe_and_the_packer_read_the_same_cap(tmp_path):
    """两条路子必须量到同一个数：探针的只读 ast 与被测模块里的真常量。"""
    assert perf_probe_rounds.doc_content_cap(pathlib.Path(REPO)) == DOC_HIT_CONTENT_CHARS
    gone = tmp_path / "app" / "rag"
    gone.mkdir(parents=True)
    (gone / "retrieval_pipeline.py").write_text("OTHER = 1\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        perf_probe_rounds.doc_content_cap(tmp_path)


def _load_prodpath():
    spec = importlib.util.spec_from_file_location(
        "r116_prodpath_under_test", os.path.join(SCRIPTS, "perf_probe_prodpath.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prodpath_hard_fails_when_the_truth_source_is_gone(monkeypatch, tmp_path):
    """§57 追加 1 的原话：读不到真源必须硬失败，不许回退默认值。"""
    module = _load_prodpath()
    monkeypatch.setattr(module, "APP_ROOT", tmp_path / "nowhere")
    with pytest.raises(RuntimeError):
        module.doc_content_cap()

    def missing():
        raise RuntimeError("cannot locate scripts/perf_probe_rounds.py")

    monkeypatch.setattr(module, "_load_rounds_probe", missing)
    with pytest.raises(RuntimeError) as caught:
        module.doc_content_cap()
    assert "cannot locate" in str(caught.value), "硬失败要说清是没找到真源，不是别的原因"

    class _NoRuler:
        pass

    monkeypatch.setattr(module, "_load_rounds_probe", lambda: _NoRuler())
    with pytest.raises(RuntimeError):
        module.doc_content_cap()


def test_prodpath_cap_flows_into_the_synthetic_unit_it_sends(monkeypatch):
    """改了真源读数，合成料就得跟着变：把读数换成 128 就得量到更短的那条料。"""
    module = _load_prodpath()
    monkeypatch.setattr(module, "doc_content_cap", lambda: 128)
    built = "[1] 来源:demo-policy.md 相关度:%s\n" % "未评分" + module.cn_text(module.doc_content_cap())
    assert len(built.split("\n", 1)[1]) == 128
    monkeypatch.setattr(module, "doc_content_cap", lambda: DOC_HIT_CONTENT_CHARS)
    same = "[1] 来源:demo-policy.md 相关度:%s\n" % "未评分" + module.cn_text(module.doc_content_cap())
    assert len(same.split("\n", 1)[1]) == DOC_HIT_CONTENT_CHARS


# ==================== 判据 5：那句 ~4x 的过期实测 ====================


def test_rounds_docstring_keeps_the_dated_history_and_states_todays_ratio():
    """旧实测不许悄悄删：标成 09-19 当晚口径，同时给出今天量到的倍率。"""
    doc = ast.get_docstring(_function("real_chunk_text")) or ""
    assert "4x" in doc, "09-19 那句 ~4x 被删了：本单要的是标注日期，不是抹掉"
    assert "09-19" in doc and "must not" in doc, "旧数没标成当晚口径，读的人还会拿它当今天的尺子"
    assert "09-21" in doc and "1.6x" in doc, "今天量到的倍率没写进去"
    assert "445" in doc and "275" in doc, "分子分母两枚实测数要能被复核"
    assert run5.synthetic_overstatement_ratio() == 1.62


def test_synthetic_unit_token_count_is_measured_not_transcribed():
    """docstring 里那枚 445 必须由被测尺子现量：合成单条命中＝行头 + 正文上限。"""
    unit = "[1] 来源:demo-policy.md 相关度:%s\n" % "未评分" + perf_probe_rounds.cn_text(DOC_HIT_CONTENT_CHARS)
    assert text_pack_tokens(unit) == run5.RUN5_SYNTHETIC_UNIT_TOKENS == 445
    assert run5.RUN5_DOC_HIT_MEDIAN_TOKENS == 275 and run5.RUN5_DOC_HIT_MEDIAN_N == 321
    assert run5.synthetic_overstatement_ratio() == pytest.approx(445 / 275, abs=0.01)


def test_the_kb_still_holds_no_markdown_so_the_116_char_fallback_is_not_corpus():
    """今天复核到的另一半：09-19 那枚 "ONE file of 116 chars" 量的就是兜底串本身。"""
    documents = os.path.join(REPO, "documents")
    names = os.listdir(documents) if os.path.isdir(documents) else []
    assert [name for name in names if name.endswith(".md")] == [], (
        "documents/ 里出现了 .md：那句兜底说明要按真语料重写"
    )
    assert [name for name in names if name.endswith(".txt")], "兜底分支现在还得是唯一的料源"


# ==================== 判据 6：stub 台账三条腿（只取证，不补） ====================


def test_stub_ledger_census_names_every_leg_line():
    """run5 的 282 枚 ``[PromptPack]`` 按腿点名：retrieval 那 29 行压根没有 stub 这套字段。"""
    census = run5.RUN5_PROMPT_PACK_CENSUS
    assert sum(row["lines"] for row in census.values()) == 282
    assert census["doc"]["lines"] == 152 and census["doc"]["stub_lines"] == 152
    assert census["data"]["lines"] == 101 and census["data"]["stub_lines"] == 81
    retrieval = census["retrieval"]
    assert retrieval["lines"] == 29 and retrieval["stub_lines"] == 0 and retrieval["ledger_lines"] == 0
    assert set(retrieval["fields"]) == {
        "candidates", "dropped", "dropped_sources", "fitted", "leg", "packed_tokens", "room", "tier"
    }
    for field in ("room_total", "room_left", "stub", "truncated", "ledger_packed_tokens",
                  "prompt_estimate_tokens"):
        assert field not in retrieval["fields"], "retrieval 腿行里出现了 %s：判据 6 的取证结论要重写" % field


def test_the_unaccounted_twenty_are_the_evidence_bag_line_not_a_missing_stub_field():
    """那 20 枚「装箱未送出，证据袋不记」是另一种行：字段集只有 dataset / leg / recorded。"""
    assert run5.RUN5_EVIDENCE_BAG_RECORD_LINES == 101 - 81
    assert run5.RUN5_EVIDENCE_BAG_FIELDS == ["dataset", "leg", "recorded"]
    assert "stub" not in run5.RUN5_EVIDENCE_BAG_FIELDS


def test_retrieval_leg_has_no_stub_because_it_never_cuts_one():
    """定性取证（只读，不动产品代码）：retrieval 腿只做**整条丢弃**，裁尾与桩档位只活在记账腿里。

    ``pack_hit_list`` 是那条腿的全部装箱动作——它只调 ``pack_prefix_by_rank`` 并把整条后缀丢掉，
    既没有 ``_fit_unit_to_room`` 的裁尾，也没有 R122 的门槛判定，所以那一行日志压根没有桩可记；
    但它同时也交不出 ``room_total`` / ``room_left`` / ``ledger_packed_tokens``，同一口径的房账
    在那条腿上是缺的（缺什么、要补哪个文件，见交付说明）。
    """
    pipeline = io.open(os.path.join(REPO, "app", "rag", "retrieval_pipeline.py"), encoding="utf-8").read()
    hit_list = ast.get_source_segment(pipeline, _function("pack_hit_list", pipeline, "retrieval_pipeline.py")) or ""
    assert "pack_prefix_by_rank" in hit_list
    for primitive in ("_fit_unit_to_room", "stub", "PACK_MIN_STUB_BODY_TOKENS", "ledger"):
        assert primitive not in hit_list, "pack_hit_list 里出现了 %s：判据 6 的定性要重写" % primitive
    tools_source = io.open(os.path.join(REPO, "app", "agents", "tools.py"), encoding="utf-8").read()
    packer = ast.get_source_segment(
        tools_source, _function("_pack_into_prompt_room", tools_source, "tools.py")
    ) or ""
    for primitive in ("_fit_unit_to_room", "PACK_MIN_STUB_BODY_TOKENS", "ledger_packed_tokens"):
        assert primitive in packer, "%s 不在装箱函数里：两条腿的差异不成立了" % primitive
    packed = run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)
    assert {row["leg"] for row in packed} == {"doc", "data"}
    assert {row["stub"] for row in packed} == {"none", "kept", "refused"}


# ==================== 判据 1 的总账：46 枚钉桩逐枚答三个数 ====================


def _window_ids() -> set:
    """从 R112 那族钉桩里读出 46 枚题号（只读源码，不 import 测试模块）。"""
    source = io.open(
        os.path.join(REPO, "tests", "test_r112_prompt_packing.py"), encoding="utf-8"
    ).read()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "WINDOW_IDS":
            return set(ast.literal_eval(node.value))
    raise AssertionError("R112 里读不到 WINDOW_IDS：那族钉桩改了名，本单要重找")


def test_every_window_pin_answers_room_material_and_refusal(room_sources):
    """46 枚钉桩（摊到 47 发装箱账）每一枚都必须同时答得出：room 多少、实得几条、拒几条。

    这里出的是**算式总账**（``pin_account``），被测自己怎么走那两档由
    ``tests/test_r112_prompt_packing.py`` 的同一族用例钉：两边都从同一张实测表出发。
    """
    capacity, estimated = room_sources
    window = _window_ids()
    assert len(window) == 46, "钉桩族变成 %d 枚，本单的账要跟着改" % len(window)
    rows = [
        row for row in run5.records(run5.MEASURED_PACKS_RUN5, run5.TABLE_FIELDS)
        if row["row_id"] in window
    ]
    assert len(rows) == 47, "46 枚钉桩应摊到 47 发装箱账（现 %d 发）" % len(rows)
    accounts = [run5.pin_account(row, capacity, estimated) for row in rows]
    assert {row["row_id"] for row in rows} | set(run5.MEASURED_NOT_PACKED_IDS) == window, (
        "有钉桩既没有实测装箱账也没被点名说明为什么没有"
    )
    for account in accounts:
        for field in ("room_estimated", "room_measured", "whole_material_estimated",
                      "refused_estimated", "whole_material_measured", "refused_measured",
                      "measured_shell", "candidates"):
            assert isinstance(account[field], int), account
        # room 不会为负：被测自己是 max(0, room_total - used)，实测口径同样要允许被夹住。
        assert account["room_measured"] == max(0, account["room_estimated"] + account["room_overestimate"])
        assert account["whole_material_estimated"] + account["refused_estimated"] == account["candidates"]
        assert account["whole_material_measured"] + account["refused_measured"] == account["candidates"]
        assert account["whole_material_measured"] >= account["whole_material_estimated"]
    refused_rows = [account for account in accounts if account["refused_on_machine"]]
    assert len(refused_rows) == 13, "46 枚族里最后一发就拒的是 13 枚（全量 17 枚见 refused 族）"
    assert all(a["whole_material_estimated"] == 0 for a in refused_rows)
    assert all(a["whole_material_measured"] > 0 for a in refused_rows), "有拒发按实测房仍然变不出整料"
    totals = {
        "estimated_material": sum(a["whole_material_estimated"] for a in accounts),
        "measured_material": sum(a["whole_material_measured"] for a in accounts),
        "estimated_refused": sum(a["refused_estimated"] for a in accounts),
        "measured_refused": sum(a["refused_measured"] for a in accounts),
    }
    assert totals == {
        "estimated_material": 37, "measured_material": 119,
        "estimated_refused": 182, "measured_refused": 100,
    }, "按实测 room 复算，46 枚族多送出 82 条整料：这组数变了要连交付说明一起改"


def test_pin_account_agrees_with_the_refused_family(room_sources):
    """总账与逐枚账必须同源：同一枚 refused 发，两处算出来的整料条数一模一样。"""
    capacity, estimated = room_sources
    by_key = {
        (row["row_id"], row["leg"], row["refused_seq"]): row for row in REFUSED_PACKS
    }
    for pack in REFUSED_PACKS:
        account = run5.pin_account(pack, capacity, estimated)
        extra = run5.over_reserve(pack, capacity, estimated)
        fitted, _dropped, used = run5.fit_prices(
            run5.replay_prices(pack), max(0, pack["room_left"] + extra)
        )
        assert (account["whole_material_measured"], account["tokens_measured"]) == (fitted, used)
        assert (account["row_id"], account["leg"], by_key[(pack["row_id"], pack["leg"], pack["refused_seq"])]["refused_seq"]) == (
            pack["row_id"], pack["leg"], pack["refused_seq"]
        )


# ==================== §62 的教训：UTF-16 LE 日志按 utf-8 硬读会全零假阴性 ====================


def test_zero_pack_lines_is_a_hard_failure_not_a_quiet_zero(tmp_path):
    """同一份正文：BOM 探测读得出来，按 utf-8 硬读就是 0 枚装箱账 ⇒ 后者必须炸。"""
    body = "\n".join([
        "[Classify] tier=qa tokens=1 question=演示题",
        "[PromptPack] leg=doc tier=analysis room_total=1606 room_left=1606 candidates=2 "
        "fitted=2 dropped=0 truncated=0 stub=none packed_tokens=200 ledger_packed_tokens=200 "
        "prompt_estimate_tokens=1154 ledger=step dropped_labels=-",
    ])
    utf16 = tmp_path / "mini-utf16.log"
    utf16.write_bytes(b"\xff\xfe" + body.encode("utf-16-le"))
    rows = run5.read_backend_log(str(utf16))
    assert len(run5.pack_lines(rows, 0, len(rows), leg="doc")) == 1

    naive = io.open(str(utf16), encoding="utf-8", errors="replace").read()
    assert run5.PACK_MARKER not in naive, "utf-8 硬读竟然读得到装箱标记：这枚假阴性的教训要重描"
    wrong = tmp_path / "plain.log"
    wrong.write_text("[无关行]\n另一行\n", encoding="utf-8")
    with pytest.raises(run5.LogFormatError):
        run5.read_backend_log(str(wrong))