# -*- coding: utf-8 -*-
"""R525 判据② —— 位移必须断言**名次与 places_moved**，在 5 / 12 / 40 三种腿宽上各测一次。

在册那枚 ``tests/test_r153_prior_shift_is_bounded.py`` 已经在合成名册（``doc00.txt`` …）上把
界钉死了，本件不重复它的口径：这里的输入是**真库真实 ANN 回来的 40 行名次**（夹具与出处见
``tests/test_r525_real_store_readings.py``），所以本件量的是「先验在真数据形状上买到几名」，
不是「先验的算术对不对」。

两格只有真库形状才答得出的读数，写在这里免得下一班再找：

* 演示语料那篇 586 枚 chunk 的文档在真库 top-40 里独占 **27 席**，top-5 里 **5 席全是它**。
  filename 粒度的先验一次就注记它窗口里的**每一枚**命中：载体全体等强 ⇒ 相邻交换一次都不
  发生 ⇒ **在独大窗口里打在赢家身上买到 0 名**（见 ``…_dominated_window…`` 那枚用例）。
* 同一篇的强度在窗口里唯一能买到的东西是「抢名额时谁赢」，不是「多挪几名」——界是 1 名，
  而且这个 1 不随窗口里有几枚同篇命中放大（见 ``…_when_the_dominant_document_is_adopted``）。

信号值一律明写是合成（键是真库真 filename）：真库那张表今天 0 行，本单只读、不许伪造
「真库有信号」那一格（派工词判据①⑥）。
"""
from __future__ import annotations

import pytest

from test_r525_real_store_readings import (
    LEG_WIDTHS,
    ann_rows,
    product_hit_dicts,
    signal_on,
)


def rank(rows, priors, *, enabled=True, module=None):
    """把真库名次送进产品自己的 ``rank_hits_by_activity``。"""
    if module is None:
        from app.rag import retriever as rt
    else:
        rt = module
    hits = product_hit_dicts(rows, module=module)
    return hits, rt.rank_hits_by_activity(hits, priors, enabled=enabled)


def single_carrier_index(rows):
    """在真库名次里挑一枚**只占一席**的文档，返回它的窗口内下标（0-based，且不是榜首）。

    为什么非要单席位：filename 粒度的先验一次注记该篇在窗口里的**每一枚**命中，而演示语料
    那篇 586 枚 chunk 的文档在 top-12 里占 10 席——打在它身上载体全体等强，一次交换都不会
    发生。要量「买到几名」就得挑一枚只占一席的，让名次账只有一条通路。
    """
    from collections import Counter

    counts = Counter(row["filename"] for row in rows)
    for index, row in enumerate(rows):
        if index and counts[row["filename"]] == 1:
            return index
    raise AssertionError("这份真库名次里没有单席位文档，靶子得换个量法")


def book(ranked):
    """交回 [(source, chunk_index, previous_rank, new_rank, places_moved)]。"""
    return [(hit["source"], hit["chunk_index"],
             (hit.get("activity_prior") or {}).get("previous_rank"),
             (hit.get("activity_prior") or {}).get("new_rank"),
             (hit.get("activity_prior") or {}).get("places_moved", 0)) for hit in ranked]


#: 三档真库名次切片：头两档从榜首取 12 / 40 名；第三档是从真库榜尾裁出来的 5 名宽窗口
#: （top-5 五席全是同一篇，头档那一份量不出「挪一名」，所以 5 名宽那份另切一刀）。
REAL_WINDOWS = {5: ann_rows(40)[35:40], 12: ann_rows(12), 40: ann_rows(40)}


# ==================== 判据②：三种腿宽 × 真库名次 ====================

@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_one_net_adoption_on_real_ranks_buys_exactly_one_place(width):
    """5 / 12 / 40 各测一次：一枚净采纳买到一名，被挤下去的那枚买到负一名。

    🔴 断言全写在名次与 ``places_moved`` 上，没有一处断言「读到了计数」（派工词判据②点名）。
    """
    rows = REAL_WINDOWS[width]
    index = single_carrier_index(rows)
    target = rows[index]
    _, ranked = rank(rows, signal_on(rows, index))
    book_rows = book(ranked)
    promoted = [row for row in book_rows
                if row[0] == target["filename"] and row[1] == target["chunk_index"]][0]
    assert promoted[2] == index + 1, promoted
    assert promoted[3] == index, promoted
    assert promoted[4] == 1, promoted
    displaced = book_rows[index]
    assert displaced[2] == index and displaced[3] == index + 1 and displaced[4] == -1, displaced
    assert sum(1 for row in book_rows if row[4]) == 2, "一名上位只许配一名下沉：" + str(book_rows)
    assert max(abs(row[4]) for row in book_rows) == 1


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_the_bound_holds_on_real_ranks_at_every_shipped_leg_width(width):
    """正负两侧同界：净采纳与净驳回两条输入，位移枚数都不许越过 ``ACTIVITY_PRIOR_MAX_SHIFT_RANKS``。"""
    from app.rag import retriever as rt

    rows = REAL_WINDOWS[width]
    index = single_carrier_index(rows)
    _, up = rank(rows, signal_on(rows, index))
    _, down = rank(rows, signal_on(rows, index, accepted=0, rejected=3))
    moves = [abs(int(hit["activity_prior"]["places_moved"]))
             for hit in up + down if "activity_prior" in hit]
    assert moves, "真库名次里连一枚注记都没有 ⇒ 这一档压根没测到位移"
    assert max(moves) <= int(rt.ACTIVITY_PRIOR_MAX_SHIFT_RANKS), (width, moves)


#: 执行层自报的真库读数：把独大那篇打满负分，各档窗口里下沉几枚载体。
#: 5 名宽（top-5 五席同篇）＝ **0 枚**；12 名宽＝ 1 枚；40 名宽＝ 10 枚。
NEGATIVE_SINKS_ON_THE_DOMINANT_DOCUMENT = {5: 0, 12: 1, 40: 10}


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_a_rejected_head_sinks_one_place_and_no_further_on_real_ranks(width):
    """负侧的真库读数：驳回一篇独大的文档，**它的榜首席位一枚都动不了**。

    只有当它某一枚载体的**下邻是别篇**时，那一枚才下沉一名（交换条件是「下邻强度严格大于
    上位」，同篇相邻永远等强）。独大窗口（top-5 五席同篇）里连一个这样的边界都没有 ⇒ 负分
    买到 0 名。每一枚下沉仍然是 1 名，与窗口里有几枚同篇命中无关——界是结构给的。
    """
    rows = ann_rows(width)
    head = rows[0]["filename"]
    _, ranked = rank(rows, {head: {"accepted": 0, "rejected": 5}})
    book_rows = book(ranked)
    head_rows = [row for row in book_rows if row[0] == head]
    moves = [row[4] for row in head_rows]
    assert max(moves) == 0, "被驳回的那篇不许同时往上走：" + str(book_rows)
    assert min(moves) >= -1, "负侧越界：" + str(book_rows)
    assert head_rows[0][4] == 0, "榜首那枚载体在任何档上都不该动：" + str(head_rows[0])
    sinks = sum(1 for move in moves if move)
    assert sinks == NEGATIVE_SINKS_ON_THE_DOMINANT_DOCUMENT[width], (width, moves)
    promoted = [row for row in book_rows if row[0] != head and row[4]]
    assert len(promoted) == sinks, "一名下沉只许配一名上位：" + str(book_rows)


def test_places_moved_is_always_previous_rank_minus_new_rank_on_real_ranks():
    """账目自洽：真库 top-40 上每一枚注记的 ``places_moved`` 都等于 ``previous_rank - new_rank``。"""
    rows = ann_rows(40)
    _, ranked = rank(rows, {row["filename"]: {"accepted": 3, "rejected": 0} for row in rows[::3]})
    for position, row in enumerate(book(ranked), start=1):
        source, chunk_index, previous, new, moved = row
        assert new == position, (source, chunk_index, new, position)
        assert moved == previous - new, (source, chunk_index, previous, new, moved)


def test_the_prior_never_adds_or_drops_a_real_candidate():
    """候选的进出一个都不动（判据②的边界）：40 行真库名次进去，40 行出来，逐枚可配对。"""
    rows = ann_rows(40)
    _, ranked = rank(rows, {name: {"accepted": 3, "rejected": 0}
                            for name in {row["filename"] for row in rows}})
    before = sorted((row["filename"], row["chunk_index"]) for row in rows)
    after = sorted((hit["source"], hit["chunk_index"]) for hit in ranked)
    assert len(ranked) == len(rows) == 40
    assert before == after


def test_a_head_signal_on_a_dominated_real_window_buys_zero_places():
    """真库 top-5 五席同篇 ⇒ 打在任何一枚上都是全体等强，相邻交换一次都不发生。

    这一格是真库形状给的、合成名册给不出的读数：先验粒度是 filename，而独大窗口里 filename
    一个都不许多，所以**一次打点买到 0 名**；``any(strengths)`` 成立 ⇒ 仍会复制注记，但次序
    一个字不动。
    """
    rows = ann_rows(5)
    assert len({row["filename"] for row in rows}) == 1, "top-5 应当全是同一篇"
    hits, ranked = rank(rows, signal_on(rows, -1))
    assert [hit["source"] for hit in ranked] == [hit["source"] for hit in hits]
    assert [hit["chunk_index"] for hit in ranked] == [hit["chunk_index"] for hit in hits]
    assert all(int(hit["activity_prior"]["places_moved"]) == 0 for hit in ranked)
    assert all(int(hit["activity_prior"]["new_rank"]) == int(hit["activity_prior"]["previous_rank"])
               for hit in ranked)


def the_dominant_document_reading():
    """独大那篇在真库 top-40 上把强度兑换成多少枚位移（读数，判据在下一枚用例里）。"""
    rows = ann_rows(40)
    _, ranked = rank(rows, signal_on(rows, 0))
    return [row[4] for row in book(ranked)]


def test_the_real_reading_of_travel_when_the_dominant_document_is_adopted():
    """执行层自报的读数钉：赢家被打点时，真库 top-40 上 20 枚载体各挪 ±1、共 10 次交换。

    这一枚把「强度兑换成位移」钉在真库名次上：位移枚数**没有**因为窗口里有 27 枚同篇命中而
    放大——界是结构给的（一轮内一条命中至多参与一次相邻交换，轮数＝界）。
    """
    moves = the_dominant_document_reading()
    nonzero = [move for move in moves if move]
    assert len(nonzero) == 20, nonzero
    assert sorted(set(nonzero)) == [-1, 1], set(nonzero)
    assert max(abs(move) for move in moves) == 1


@pytest.mark.parametrize("width", LEG_WIDTHS)
def test_equal_evidence_across_the_real_window_moves_nothing(width):
    """全体等强（窗口里每篇都被打成同分）⇒ 并列永远保持原序，不靠排序算法的运气。"""
    rows = REAL_WINDOWS[width]
    priors = {name: {"accepted": 2, "rejected": 0}
              for name in {row["filename"] for row in rows}}
    hits, ranked = rank(rows, priors)
    assert [hit["source"] for hit in ranked] == [hit["source"] for hit in hits]
    assert [hit["chunk_index"] for hit in ranked] == [hit["chunk_index"] for hit in hits]
