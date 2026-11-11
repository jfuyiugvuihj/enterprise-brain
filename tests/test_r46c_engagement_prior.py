# -*- coding: utf-8 -*-
r"""R46 差格 a · 读侧派生——先验必须从 0019 现读长出来，且冷启动不许把新文档压死。

判据原文（与 tests/test_r46c_engagement_signals.py 同一份摘要，这里只留与本格相关的两行）：

- 计划书 §5.2 R46：① 有信号后排序变化可测；② **无信号时与现状一致**；
  ③ 隐私：只存计数不存内容 | 禁止项：不得把用户问题原文写进新表。
- 派工词判据②：相关度先验必须从那张表现读派生，不许在代码里写死任何一道题的先验，
  也不许把「没人点过」读成「分数为零」从而把新文档永久压死；默认值与样本数下限要交代并钉住。

口径（本单裁定，写在交工纸里同一份）：
- 冷启动默认值 = 0.0 枚名次，含义是**不动名次**，不是"这篇值零分"。这一路**只抬不压**，
  返回值恒在 [0, 界]，所以没人点过的文档与刚入库的新文档拿同一个中性值，排序退回名次分本身。
- 样本数下限 = ENGAGEMENT_MIN_SAMPLES（现值 5）：攒够之前按 support / 下限 往中性收缩，
  第一枚点击替整篇定序这件事不发生；攒够之后 confidence 恒为 1，不再随样本数漂。
- 平滑项 = ENGAGEMENT_PRIOR_SMOOTHING（现值 5）：与 0011 的平滑同一个理由。
- 权重 = click 1.0 / view 0.5：口径而非校准结果，真库强度那一格欠一台安静机器（D 组）。
- 🔴 位移界**不因两路合并而放宽**：合并值夹回同一根 ACTIVITY_PRIOR_MAX_SHIFT_RANKS。

库与模型都不在场：读腿走行注入的 row_reader，检索器走注入的 engagement_prior；
真 PG 与真向量库一枚都不碰。
"""
import inspect
import types
import pytest
from app.rag import retriever as rt
from test_r46c_engagement_signals import (
    ACTION_VIEW,
    BODY_TEXT,
    DOC_ROW,
    GOOD_BODY,
    _EngagementStore,
    _post,
    _staff_client,
)
from test_r153_prior_shift_is_bounded import NOTE_KEYS

CAP = float(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS)


def _hits(*names):
    """命中字典：形状与在册那枚 R46 件一致（source 就是 filename）。"""
    return [
        {
            "content": "body of " + name,
            "source": name,
            "chunk_index": 0,
            "classification": 1,
            "department": "finance",
        }
        for name in names
    ]


def _sources(hits):
    return [str(hit.get("source")) for hit in hits]


def _engagement_priors(rows):
    """把 0019 的聚合读数灌进读腿：rows 是 (filename, clicks, views) 的列表。"""
    rt.reset_engagement_priors()
    return rt.engagement_priors(row_reader=lambda: list(rows))


def _reader_text():
    """活把手那枚函数体里的字面量拼接：install_mutation 换的就是这一枚对象的码体，"""
    """所以本件的列名清单钉量的始终是场上那一条语句，不是盘上的旧抄。"""
    code = rt._read_engagement_rows.__code__
    # co_consts[0] 是文档串：它讲的是"username 连出现的位置都没有"，把这句话算进语句就成了假红。
    return " ".join(constant for constant in code.co_consts[1:] if isinstance(constant, str))


# ===================================================== 判据② 冷启动：没点过＝不动名次
def test_a_source_nobody_clicked_holds_the_neutral_value():
    """🔴 反证 K2 的靶子：把派生改成写死一个常数，本件当场红（写死的 0.4 不是派生出来的）。"""
    for absent in (None, {}, {"clicks": 0, "views": 0}, {"clicks": 0}, {"views": 0}):
        value = rt.engagement_prior_value(absent)
        assert value == 0.0, (absent, value)
    assert rt.engagement_prior_value({"clicks": 0, "views": 0}) == 0.0
    assert rt.engagement_prior_value("finance-q3.txt") == 0.0, "非字典一律中性"


def test_the_click_leg_only_lifts_and_never_presses():
    """把「没人点过」读成负分，新文档就永久翻不了身——判据②点名要拦的那一种读法。"""
    grid = []
    for clicks in range(0, 30, 3):
        for views in range(0, 30, 7):
            grid.append(rt.engagement_prior_value({"clicks": clicks, "views": views}))
            assert grid[-1] >= 0.0, grid
            assert grid[-1] <= CAP, grid
    # 平滑项让界成为**渐近上界**：一万枚点击也只逼近一名而永不越过它，这比"到顶就等于界"更难做到。
    huge = rt.engagement_prior_value({"clicks": 10_000, "views": 10_000})
    assert huge < CAP and huge == pytest.approx(CAP, abs=1e-3), huge
    assert min(grid) == 0.0 and max(grid) < CAP, (min(grid), max(grid))


def test_malformed_counts_never_become_a_negative_score():
    """脏读数退回中性：负数、非数字、None 一律 0.0，不许长出第三种含义。"""
    for bad in ({"clicks": -5, "views": 2}, {"clicks": "many"}, {"views": None},
              {"clicks": None, "views": None}, {"clicks": -1, "views": -1}):
        assert rt.engagement_prior_value(bad) == 0.0, bad


def test_the_first_click_is_weaker_than_the_fifth():
    """🔴 反证 K5 的靶子：摘掉样本数下限那一手（confidence 恒为 1），本件当场红。"""
    one = rt.engagement_prior_value({"clicks": 1, "views": 0})
    three = rt.engagement_prior_value({"clicks": 3, "views": 0})
    enough = rt.engagement_prior_value({"clicks": rt.ENGAGEMENT_MIN_SAMPLES, "views": 0})
    many = rt.engagement_prior_value({"clicks": 60, "views": 0})
    assert 0 < one < three < enough <= many, (one, three, enough, many)
    support = 1
    expected = CAP * 1.0 / (1.0 + rt.ENGAGEMENT_PRIOR_SMOOTHING) * (
        support / float(rt.ENGAGEMENT_MIN_SAMPLES))
    assert abs(one - expected) < 1e-12, (one, expected)
    assert rt.ENGAGEMENT_MIN_SAMPLES > 1, "下限为 1 就等于没有下限"


def test_a_view_is_weaker_than_a_click_at_the_same_support():
    """口径写死在常量里：点开比展开看了一眼更强，所以一枚 click 记一份、一枚 view 记半份。"""
    assert rt.ENGAGEMENT_CLICK_WEIGHT == 1.0 and rt.ENGAGEMENT_VIEW_WEIGHT == 0.5
    assert rt.engagement_prior_value({"clicks": 3, "views": 0}) > \
        rt.engagement_prior_value({"clicks": 0, "views": 3})
    equal = rt.engagement_prior_value({"clicks": 2, "views": 2})
    assert equal == rt.engagement_prior_value({"clicks": 2, "views": 2})
    assert 0 < equal < rt.engagement_prior_value({"clicks": 4, "views": 0})

# ================================================== 判据② 派生而不是写死（不认题目）
def test_the_prior_depends_on_counts_only_and_not_on_which_document():
    """代码里不许有"哪道题／哪一篇值几分"那本名册：同一份计数换任何文档名都给同一个数。"""
    for first, second in (("finance-q3.txt", "随便一篇.txt"), ("a.txt", "b.txt"), ("", "x")):
        left = _engagement_priors([(first, 4, 2)])[first]
        right = _engagement_priors([(second, 4, 2)])[second]
        assert rt.engagement_prior_value(left) == rt.engagement_prior_value(right)
    values = _engagement_priors([("one.txt", 0, 0), ("two.txt", 1, 0), ("three.txt", 9, 9)])
    assert values == {
        "one.txt": {"clicks": 0, "views": 0},
        "two.txt": {"clicks": 1, "views": 0},
        "three.txt": {"clicks": 9, "views": 9},
    }, values
    assert rt.engagement_prior_diagnostics()["source"] == "store"


def test_the_snapshot_never_falls_back_to_a_built_in_default_for_a_known_question():
    """派生的反面是"表里读不到就按一套内置先验排"：那种兜底在这条路上一个位置都没有。"""
    priors = _engagement_priors([("only.txt", 2, 1)])
    assert set(priors) == {"only.txt"}
    hits = _hits("only.txt", "brand-new.txt")
    ranked = rt.rank_hits_by_activity(hits, priors)
    assert _sources(ranked) == ["only.txt", "brand-new.txt"], (
        "点过的抬一名、没点过的保持原位：新文档靠的还是相关性本身，没有被永久压死"
    )
    assert ranked[1]["source"] == "brand-new.txt"
    assert ranked[1]["activity_prior"]["shift_ranks"] == 0.0, (
        "表里没有这一篇＝中性＝不动名次：新文档靠的还是相关性本身，不是被历史点击永久压住"
    )


def test_a_clicked_source_beats_an_unclicked_one_by_exactly_one_place():
    """判据①在点击这一路的可测读数：注记里前一格与后一格都看得见，位移恰一名。"""
    priors = _engagement_priors([("b.txt", 7, 3)])
    ranked = rt.rank_hits_by_activity(_hits("a.txt", "b.txt"), priors)
    assert _sources(ranked) == ["b.txt", "a.txt"], ranked
    note = ranked[0]["activity_prior"]
    assert note["previous_rank"] == 2 and note["new_rank"] == 1 and note["places_moved"] == 1
    assert 0 < note["shift_ranks"] <= CAP, note
    assert note["accepted"] == 0 and note["rejected"] == 0, (
        "这一路不改采纳／驳回那两格读数：注记里的计数仍是 0011 那一路的"
    )


def test_no_signal_returns_the_very_same_list_object_in_the_click_leg_too():
    """判据②：零行与"读不通"都退回同一个对象，不是内容恰好相同的另一份拷贝。"""
    hits = _hits("a.txt", "b.txt", "c.txt")
    assert rt.rank_hits_by_activity(hits, _engagement_priors([])) is hits
    assert rt.rank_hits_by_activity(hits, _engagement_priors([("a.txt", 0, 0)])) is hits
    assert rt.rank_hits_by_activity(hits, {"a.txt": {"clicks": 0, "views": 0}}) is hits
    assert "activity_prior" not in hits[0]


def test_the_click_leg_never_adds_or_removes_a_candidate():
    """先验只在已经合法的候选集内部挪名次：判定可见性的仍是 filters 那一处。"""
    priors = _engagement_priors([("x.txt", 40, 40), ("y.txt", 0, 9)])
    hits = _hits("x.txt", "y.txt", "z.txt")
    ranked = rt.rank_hits_by_activity(hits, priors)
    assert sorted(_sources(ranked)) == sorted(_sources(hits))
    assert len(ranked) == len(hits)


# ============================================ 判据② 的隐私边界：身份进不了排序
def test_the_aggregate_statement_carries_no_identity_column():
    """读腿那条聚合语句的列清单只有文档名与两枚 COUNT：username 连出现的位置都没有。"""
    text = _reader_text()
    assert "document_engagement_events" in text, text[:120]
    assert "GROUP BY filename" in text, text[:200]
    assert "username" not in text, (
        "谁点的进不了排序：想按人加权就得改这条字面量，而那一步会先在这里红"
    )
    assert "thread_id" not in text, "题号同理：排序不读它"
    assert "result_rank" not in text, "名次这一路当前不吃它（见交工纸的未验格子）"
    assert BODY_TEXT not in text


def test_the_priors_surface_exposes_two_counters_and_nothing_else():
    """读腿交回的形状：每篇只有 clicks 与 views 两格，没有身份、没有题号、没有内容。"""
    priors = _engagement_priors([("q3-report.txt", 3, 1)])
    assert set(priors) == {"q3-report.txt"}
    assert set(priors["q3-report.txt"]) == {"clicks", "views"}
    dumped = str(priors)
    for forbidden in ("alice", "mallory", "m1", DOC_ROW["department"], BODY_TEXT):
        assert forbidden not in dumped, forbidden


# ================================================== 判据② 的两本账：读不到 ≠ 没信号
def test_zero_rows_and_an_unreadable_table_are_two_different_readings(monkeypatch):
    """观测面必须分得开这两种零：一种说"表是空的"，一种说"我没读到"。"""
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    rt.reset_engagement_priors()
    assert _engagement_priors([]) == {}
    empty = rt.engagement_prior_diagnostics()
    assert empty["source"] == "store" and empty["documents"] == 0 and empty["reason"] == "", empty

    def broken():
        raise RuntimeError("connection refused")
    assert rt.engagement_priors(row_reader=broken) == {}
    failed = rt.engagement_prior_diagnostics()
    assert failed["source"] == "error" and failed["reason"] == "RuntimeError", failed
    hits = _hits("a.txt", "b.txt")
    assert rt.rank_hits_by_activity(hits, rt.engagement_priors(row_reader=broken)) is hits
    rt.reset_engagement_priors()
    assert rt.engagement_prior_diagnostics()["source"] == "never"


def test_a_missing_0019_leaves_the_order_alone_and_says_why(monkeypatch):
    """没跑 0019 的库：用真异常型 UndefinedTable，排序退回现状，观测面记下型名，不许 500。"""
    import psycopg.errors
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    rt.reset_engagement_priors()

    def raiser():
        raise psycopg.errors.UndefinedTable('关系 "document_engagement_events" 不存在')

    assert rt.engagement_priors(row_reader=raiser) == {}
    diagnostics = rt.engagement_prior_diagnostics()
    assert diagnostics["source"] == "error", diagnostics
    assert diagnostics["reason"] == "UndefinedTable", diagnostics
    hits = _hits("a.txt", "b.txt")
    assert rt.rank_hits_by_activity(hits, {}) is hits, "缺表那一态连注记都不许长出来"
    rt.reset_engagement_priors()

def test_the_snapshot_refills_after_the_window_expires(monkeypatch):
    """TTL 与 0011 同值同理：一次库故障最多拖慢一个窗口，而不是拖慢每一问。"""
    rt.reset_engagement_priors()
    calls = []
    monkeypatch.setattr(
        rt, "_read_engagement_rows", lambda: (calls.append(1), [("a.txt", 2, 0)])[1]
    )
    ttl = rt.ENGAGEMENT_PRIOR_TTL_SECONDS
    first = rt.engagement_priors(now=100.0)
    second = rt.engagement_priors(now=100.0 + ttl - 1)
    assert len(calls) == 1, "窗口内不该二次打库：一次排序读一整张表"
    third = rt.engagement_priors(now=100.0 + ttl + 1)
    assert len(calls) == 2, "窗口一过就得重读：刚点的那一枚不能永远看不见"
    assert first == second == third == {"a.txt": {"clicks": 2, "views": 0}}
    assert ttl == rt.ACTIVITY_PRIOR_TTL_SECONDS, "两路同一把尺，否则没人说得清这次排序听谁的"
    rt.reset_engagement_priors()


def test_an_unreadable_window_backs_off_instead_of_hammering_the_database(monkeypatch):
    """读失败之后退避窗口内不再打库；这与 0011 同一格口径，两路各自记各自的失败。"""
    rt.reset_engagement_priors()
    attempts = []

    def broken():
        attempts.append(1)
        raise RuntimeError("connection refused")
    monkeypatch.setattr(rt, "_read_engagement_rows", broken)
    assert rt.engagement_priors(now=200.0) == {}
    assert rt.engagement_priors(now=200.0 + rt.ENGAGEMENT_PRIOR_RETRY_SECONDS - 1) == {}
    assert len(attempts) == 1, attempts
    assert rt.engagement_priors(now=200.0 + rt.ENGAGEMENT_PRIOR_RETRY_SECONDS + 1) == {}
    assert len(attempts) == 2, attempts
    assert rt.engagement_prior_diagnostics()["source"] == "error"
    rt.reset_engagement_priors()

# ============================================ 判据② 合并那一手：界不因为两路而变宽
def test_the_merge_never_widens_the_shift_cap():
    """🔴 反证 K6 的靶子：把合并值夹到两倍界，本件当场红——两路各自顶满也只买到一名。"""
    both = {"accepted": 99, "rejected": 0, "clicks": 99, "views": 99}
    assert rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS == rt.ENGAGEMENT_PRIOR_MAX_SHIFT_RANKS == 1
    assert rt.activity_prior_value(both) <= CAP and rt.engagement_prior_value(both) <= CAP, (
        "两路各自都不越过那根界"
    )
    assert rt.activity_prior_value(both) + rt.engagement_prior_value(both) > CAP, (
        "两路相加本来是两名——不加这一格，下面那句夹界就是一句空话"
    )
    assert rt.signal_prior_value(both) == CAP, (
        "简单相加会给出两枚名次，而交换轮数仍是一轮：那一轮到顶只换一名"
    )
    opposed = {"accepted": 0, "rejected": 99, "clicks": 99, "views": 99}
    assert -CAP <= rt.signal_prior_value(opposed) <= CAP, rt.signal_prior_value(opposed)
    assert rt.signal_prior_value(None) == 0.0
    assert rt.signal_prior_value({"clicks": 1, "views": 0}) == rt.engagement_prior_value(
        {"clicks": 1, "views": 0}), "只有点击这一路时，合并值就是这一路的值"


def test_the_shift_stays_one_place_at_leg_widths_5_12_and_40():
    """位移界与腿宽解耦：三种宽度各量一次，最大位移恒是一名。"""
    for width in (5, 12, 40):
        names = ["doc-%02d.txt" % index for index in range(width)]
        priors = {name: {"clicks": 0, "views": 0} for name in names}
        priors[names[-1]] = {"accepted": 60, "rejected": 0, "clicks": 60, "views": 60}
        ranked = rt.rank_hits_by_activity(_hits(*names), priors)
        moved = [note["activity_prior"]["places_moved"] for note in ranked if "activity_prior" in note]
        assert moved and max(moved) == 1, (width, moved)
        assert all(abs(note["activity_prior"]["shift_ranks"]) <= CAP for note in ranked
                       if "activity_prior" in note), width
        assert _sources(ranked)[width - 2] == names[-1], (
            "末位那一条只许爬一名：宽度 5 爬到第 4 名，宽度 40 爬到第 39 名"
        )


def test_the_merged_prior_carries_both_counters_from_the_two_tables():
    """两本账并成一枚读数：一路缺席不抹掉另一路挣来的证据。"""
    merged = rt.merge_signal_priors(
        {"a.txt": {"accepted": 3, "rejected": 1}}, {"a.txt": {"clicks": 5, "views": 2}, "b.txt": {"clicks": 1, "views": 0}}
    )
    assert merged["a.txt"] == {"accepted": 3, "rejected": 1, "clicks": 5, "views": 2}
    assert merged["b.txt"] == {"clicks": 1, "views": 0}
    assert rt.signal_prior_value(merged["a.txt"]) > 0
    assert rt.merge_signal_priors({}, {}) == {}
    assert rt.merge_signal_priors(None, None) == {}


# ==================================== 两路各自兜底：一路读不通不抹掉另一路的证据
def test_an_unreadable_click_leg_does_not_erase_the_activity_leg(monkeypatch):
    """载体带着两枚读取方，其中一枚炸：排序照旧吃另一枚，而不是整手关掉先验。"""
    from app.rag.retriever import DocumentRetriever
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    hits = _hits("a.txt", "b.txt")
    carrier = types.SimpleNamespace(
        _activity_prior_loader=lambda: {"b.txt": {"accepted": 9, "rejected": 0}},
        _engagement_prior_loader=lambda: (_ for _ in ()).throw(RuntimeError("click leg down")),
    )
    ranked = DocumentRetriever._apply_activity_prior(carrier, hits)
    assert _sources(ranked) == ["b.txt", "a.txt"], ranked
    assert ranked[0]["activity_prior"]["accepted"] == 9


def test_a_carrier_that_only_knows_the_activity_leg_still_works(monkeypatch):
    """在册那几枚件用 SimpleNamespace(_activity_prior_loader=...) 直呼本方法："""
    """新读腿缺席时一个字节都不许多改——那是 09-30 那批反证刀的载荷形状。"""
    from app.rag.retriever import DocumentRetriever
    monkeypatch.delenv(rt.ACTIVITY_PRIOR_ENV, raising=False)
    hits = _hits("a.txt", "b.txt")
    carrier = types.SimpleNamespace(_activity_prior_loader=lambda: {"b.txt": {"clicks": 40, "views": 40}})
    ranked = DocumentRetriever._apply_activity_prior(carrier, hits)
    assert _sources(ranked) == ["b.txt", "a.txt"], "只有点击那一路时也照样生效"
    bare = types.SimpleNamespace()
    assert DocumentRetriever._apply_activity_prior(bare, hits) is hits, "两枚读取方都没有＝原序交回"


# ==================================== 判据②的观测面：这一路到底读没读到
def test_the_diagnostics_surface_states_the_two_legs_independently():
    """两路各自记 source 与 reason；合成一个"读不到"就丢了可核对性。"""
    rt.reset_signal_priors()
    activity = rt.activity_prior_diagnostics()
    engagement = rt.engagement_prior_diagnostics()
    assert activity["source"] == "never" and engagement["source"] == "never"
    assert engagement["max_shift_ranks"] == rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS
    assert engagement["min_samples"] == rt.ENGAGEMENT_MIN_SAMPLES
    assert engagement["smoothing"] == rt.ENGAGEMENT_PRIOR_SMOOTHING
    assert engagement["click_weight"] == rt.ENGAGEMENT_CLICK_WEIGHT
    assert engagement["view_weight"] == rt.ENGAGEMENT_VIEW_WEIGHT
    _engagement_priors([("a.txt", 2, 1)])
    assert rt.engagement_prior_diagnostics()["documents"] == 1
    assert rt.activity_prior_diagnostics()["source"] == "never", "两本账不许互相顶包"
    rt.reset_signal_priors()


def test_reset_signal_priors_clears_both_snapshots():
    """写成功之后两路一起作废：只清一路等于让另一路带着旧账参加下一次比较。"""
    _engagement_priors([("a.txt", 2, 1)])
    rt.activity_priors(row_reader=lambda: [("a.txt", 1, 0)])
    assert rt.engagement_prior_diagnostics()["source"] == "store"
    assert rt.activity_prior_diagnostics()["source"] == "store"
    rt.reset_signal_priors()
    assert rt.engagement_prior_diagnostics()["source"] == "never"
    assert rt.activity_prior_diagnostics()["source"] == "never"

# ============================ 判据⑤：这一路不许动既有口径（注记键是答案侧契约）
def test_the_click_leg_adds_not_a_single_note_key():
    """注记的键清单是答案侧契约（在册 R153 那枚判等钉）：本单一个字都不加长。"""
    ranked = rt.rank_hits_by_activity(
        _hits("a.txt", "b.txt"), {"b.txt": {"clicks": 6, "views": 3, "accepted": 1, "rejected": 0}}
    )
    note = ranked[0]["activity_prior"]
    assert set(note) == NOTE_KEYS, (sorted(set(note)), sorted(NOTE_KEYS))
    assert "clicks" not in note and "views" not in note, (
        "点击证据由 GET /api/v1/feedback/engagement 现读，不塞进这枚注记——加长它得先改判据"
    )
    assert note["shift_ranks"] == rt.signal_prior_value({"clicks": 6, "views": 3, "accepted": 1, "rejected": 0})


def test_the_click_leg_leaves_the_r46_activity_nails_green():
    """只吃采纳／驳回那两格计数的旧读数：本单一个字节都没改它的语义。"""
    rows = [("finance-q3.txt", 12, 0), ("hr-leave.txt", 0, 9), ("neutral.txt", 3, 3)]
    priors = {name: {"accepted": a, "rejected": r} for name, a, r in rows}
    ranked = rt.rank_hits_by_activity(_hits("neutral.txt", "finance-q3.txt", "hr-leave.txt"), priors)
    assert _sources(ranked) == ["finance-q3.txt", "neutral.txt", "hr-leave.txt"], ranked
    assert ranked[0]["activity_prior"]["places_moved"] == 1


# ================================================== 判据② 现读派生：写完立刻算数，不吃旧快照
def test_a_fresh_click_invalidates_the_sort_side_snapshot(monkeypatch):
    """回执说"这篇被点过一次"，下一问却还按没点过排——那种两本账比先验不准更难查。"""
    rt.reset_signal_priors()
    reads = []
    monkeypatch.setattr(rt, "_read_engagement_rows", lambda: (reads.append(1), [])[1])
    rt.engagement_priors()
    assert len(reads) == 1 and rt.engagement_prior_diagnostics()["source"] == "store"
    store = _EngagementStore()
    client = _staff_client(monkeypatch, store)
    response = _post(client, dict(GOOD_BODY, filename=DOC_ROW["filename"]))
    assert response.status_code == 200, response.text
    assert rt.engagement_prior_diagnostics()["source"] == "never", (
        "写成功之后两路快照一起作废；这里只许留下作废的痕迹，不许留下旧账"
    )
    rt.engagement_priors(row_reader=lambda: store.aggregate())
    assert rt.engagement_prior_diagnostics()["documents"] == 1
    rt.reset_signal_priors()


def test_end_to_end_one_click_moves_the_next_ranking_and_a_control_does_not(monkeypatch):
    """R527 判据 1：从端点打进去、从先读腿出来，点一次与不点一次必须量得出差。"""
    b_row = dict(DOC_ROW, filename="b.txt")
    catalog = {"b.txt": b_row}
    untouched_hits = _hits("a.txt", "b.txt")

    # 对照：不点一次——空表派生出的先验一个名次都不动，交回的还是同一个对象。
    untouched = rt.rank_hits_by_activity(untouched_hits, _engagement_priors([]))
    assert untouched is untouched_hits, "不点一次：同一个对象，不是相等的一份拷贝"
    assert _sources(untouched) == ["a.txt", "b.txt"]
    assert "activity_prior" not in untouched[1], "没点过的两条连注记都不该长出来"

    store = _EngagementStore()
    client = _staff_client(monkeypatch, store, rows=catalog)
    posted = _post(client, dict(GOOD_BODY, filename="b.txt", rank=2))
    assert posted.status_code == 200, posted.text
    assert posted.json()["clicks"] == 1
    ranked = rt.rank_hits_by_activity(_hits("a.txt", "b.txt"), _engagement_priors(store.aggregate()))
    assert _sources(ranked) == ["b.txt", "a.txt"], (
        "端点里那一枚 click 走完 0019 → 聚合 → 派生 → 名次整条腿；这里量的是名次真的变了"
    )
    assert ranked[0]["activity_prior"]["places_moved"] == 1


# ==================================================== 真接线：摘掉这一路就会红的靶子
def test_the_search_call_itself_reorders_when_a_source_was_clicked(monkeypatch):
    """🔴 先验必须长在 search() 上，不是只长在工具函数里：摘掉合并那一手，本件红。"""
    from app.rag import hot_index
    from app.rag.retriever import DocumentRetriever
    from test_r46_activity_signals import _FakeCollection, _StubEmbedder
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    instance = DocumentRetriever(
        activity_prior=lambda: {},
        engagement_prior=lambda: {"b.txt": {"clicks": 6, "views": 0}},
    )
    instance.collection = _FakeCollection(["a.txt", "b.txt", "c.txt"])
    instance.embedding = _StubEmbedder()
    found = instance.search("随便问一句", k=3)
    assert [hit["source"] for hit in found] == ["b.txt", "a.txt", "c.txt"], found
    assert found[0]["activity_prior"]["shift_ranks"] > 0


def test_the_retriever_reads_the_default_click_loader_when_nothing_is_injected(monkeypatch):
    """不注入读取方时它也得得住：读不到＝不动排序，而不是抛穿到问答里。"""
    from app.rag import hot_index
    from app.rag.retriever import DocumentRetriever
    from test_r46_activity_signals import _FakeCollection, _StubEmbedder
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    monkeypatch.setattr(rt, "_read_engagement_rows", lambda: (_ for _ in ()).throw(RuntimeError("no db")))
    monkeypatch.setattr(rt, "_read_activity_signal_rows", lambda: (_ for _ in ()).throw(RuntimeError("no db")))
    rt.reset_signal_priors()
    instance = DocumentRetriever()
    instance.collection = _FakeCollection(["a.txt", "b.txt"])
    instance.embedding = _StubEmbedder()
    found = instance.search("随便", k=2)
    assert [hit["source"] for hit in found] == ["a.txt", "b.txt"], "读不到时名次必须一动不动"
    assert rt.engagement_prior_diagnostics()["source"] == "error"
    assert rt.activity_prior_diagnostics()["source"] == "error"
    rt.reset_signal_priors()


def test_the_click_leg_is_not_a_new_dependency_on_the_vector_store():
    """派工词判据④与 AGENTS.md 那条：新代码不得新增 Chroma 依赖或写点。"""
    text = inspect.getsource(rt._read_engagement_rows)
    for banned in ("chroma", "chromadb", "collection.query", "PersistentClient"):
        assert banned not in text, "读腿上长出了遗留引擎的依赖：" + banned
    assert "psycopg" in text or "pg_store" in text, "这一路只许长在 PG 腿上"
