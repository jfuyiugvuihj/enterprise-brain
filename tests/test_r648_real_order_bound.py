# -*- coding: utf-8 -*-
"""R648 判据① 的「真次序腿」—— R153 那根界（最大位移 ≤ 1 名次）在真库读数上成不成立。

## 输入是真库读数，不是假 ``row_reader``

R46 立案到今天，``rank_hits_by_activity`` 的次序只在大模型嘴里绿过：在册 R525 量到的真库那一格
是「0 行 ⇒ 无可读」，所以**真库先验 + 真库名次**这条组合从未被量过。本件把快照钉成机器事实，
默认态（``R648_REAL_PG`` 没设）就复算，一格都不再靠话术：

* 名次 = ``eb_r59_sandbox``（R59 沙盒镜像，``chunk_vectors`` 1008 枚 / 100 篇，标签是那 252 枚
  **合成**标签，不是客户隔离证据）里真 ANN 回来的 top-40；算符 ``l2``、候选宽度由产品自己的
  ``pg_store.search_vectors`` 在同一笔事务里 ``set_config`` 钉到 ``configured_hnsw_ef_search()``；
  查询向量是定种子随机数（seed 20261004，本单不许打模型）。
* 先验 = 真 PG 里 ``document_activity_signals`` 的行，读回走**产品那条 SELECT 原文**，折账走
  产品自己的 ``activity_priors``；命中字典由产品自己的 ``_hit_dicts`` 生成。
* 🔴 唯一不是原文的一格：``filename`` 经**单射**改名成 ``r648_`` 假名（写域只准假名）。名次、
  距离、「同篇占几席」的集中度一个字没动——而那三样才是位移算术的输入。正文换成占位串由
  ``test_the_prior_never_reads_the_chunk_text`` 当场证，不是纸上的承诺。

界与判据②一字未松：``bound`` 取量具里钉死的 ``R153_BOOKED_MAX_SHIFT_RANKS``，**不读被量模块的
常量**（读了就等于让出题人自己答题）；无信号必须交回同一个对象。
"""
from __future__ import annotations

from _r648_gauge_harness import REAL_PG_OPT_IN, load_gauge

#: 快照出处：2026-10-04 真腿读数（``R648_REAL_PG=on`` 亲跑，产物落 %TEMP%，命令原文抄在
#: docs/testing/r648-real-pg-concurrency-2026-10-04.md）。
SNAPSHOT_TAKEN = "2026-10-04"
QUERY_SEED = 20261004
EF_SEARCH_WIDTH = 100
SCOPE = {"embedding_model": "nomic-embed-text", "dimension": 768, "distance_function": "l2",
         "schema_version": 1}
RANKING_STATEMENT_SHA256 = "4d9381427788effe"

#: 真库 ANN top-40（名次 = 行序）：(假 filename, chunk_index, classification, department, distance)。
REAL_ANN_TOP40 = (
    ('r648_doc01.md', 256, 3, 'finance', 23.859986),
    ('r648_doc01.md', 340, 1, 'sales', 23.955398),
    ('r648_doc02.md', 10, 4, 'hr', 24.230524),
    ('r648_doc01.md', 255, 2, 'engineering', 24.272772),
    ('r648_doc01.md', 341, 2, 'engineering', 24.302175),
    ('r648_doc01.md', 407, 3, 'finance', 24.303423),
    ('r648_doc03.md', 9, 4, 'hr', 24.382706),
    ('r648_doc01.md', 581, 4, 'hr', 24.383353),
    ('r648_doc01.md', 481, 1, 'sales', 24.387569),
    ('r648_doc04.md', 1, 3, 'finance', 24.398759),
    ('r648_doc05.md', 4, 3, 'finance', 24.424784),
    ('r648_doc01.md', 578, 4, 'hr', 24.441105),
    ('r648_doc01.md', 189, 4, 'hr', 24.45055),
    ('r648_doc01.md', 482, 2, 'engineering', 24.481939),
    ('r648_doc06.md', 1, 4, 'hr', 24.484662),
    ('r648_doc01.md', 228, 4, 'hr', 24.500055),
    ('r648_doc01.md', 579, 1, 'sales', 24.529016),
    ('r648_doc04.md', 3, 2, 'engineering', 24.58076),
    ('r648_doc01.md', 568, 1, 'sales', 24.612487),
    ('r648_doc01.md', 352, 2, 'engineering', 24.626065),
    ('r648_doc01.md', 173, 3, 'finance', 24.629749),
    ('r648_doc03.md', 3, 2, 'engineering', 24.64033),
    ('r648_doc04.md', 2, 1, 'sales', 24.640717),
    ('r648_doc01.md', 246, 4, 'hr', 24.651088),
    ('r648_doc05.md', 5, 4, 'hr', 24.66042),
    ('r648_doc05.md', 2, 1, 'sales', 24.662369),
    ('r648_doc01.md', 351, 1, 'sales', 24.669454),
    ('r648_doc07.md', 2, 2, 'engineering', 24.673771),
    ('r648_doc01.md', 274, 3, 'finance', 24.683255),
    ('r648_doc01.md', 269, 1, 'sales', 24.688264),
    ('r648_doc01.md', 383, 4, 'hr', 24.697692),
    ('r648_doc01.md', 570, 4, 'hr', 24.743415),
    ('r648_doc01.md', 566, 3, 'finance', 24.74451),
    ('r648_doc01.md', 572, 2, 'engineering', 24.754045),
    ('r648_doc01.md', 580, 3, 'finance', 24.765499),
    ('r648_doc03.md', 8, 3, 'finance', 24.770816),
    ('r648_doc01.md', 61, 4, 'hr', 24.804911),
    ('r648_doc08.md', 6, 1, 'sales', 24.825315),
    ('r648_doc01.md', 467, 1, 'sales', 24.854927),
    ('r648_doc01.md', 68, 3, 'finance', 24.855852),
)

#: 真库读回的先验（键 = 上面那批假名；净值为负的样本在位，好量界的负侧）。
BOOKED_PRIORS = {
    "r648_doc01.md": {"accepted": 10, "rejected": 7},
    "r648_doc03.md": {"accepted": 1, "rejected": 0},
    "r648_doc04.md": {"accepted": 0, "rejected": 4},
}

#: 三档腿宽在册读数：``max_abs_places_moved`` / ``carriers_shifted`` / ``distinct_filenames``。
BOOKED_WIDTH_READINGS = {
    5: {"max_abs_places_moved": 1, "carriers_shifted": 2, "distinct_filenames": 2},
    12: {"max_abs_places_moved": 1, "carriers_shifted": 6, "distinct_filenames": 5},
    40: {"max_abs_places_moved": 1, "carriers_shifted": 22, "distinct_filenames": 8},
}

#: 逐枚位移（真库读数原样）：(source, previous_rank, new_rank, places_moved, shift_ranks)。
BOOKED_MOVES_AT_40 = (
    ('r648_doc01.md', 1, 1, 0, 0.3),
    ('r648_doc01.md', 2, 2, 0, 0.3),
    ('r648_doc01.md', 4, 3, 1, 0.3),
    ('r648_doc02.md', 3, 4, -1, 0.0),
    ('r648_doc01.md', 5, 5, 0, 0.3),
    ('r648_doc03.md', 7, 6, 1, 0.5),
    ('r648_doc01.md', 6, 7, -1, 0.3),
    ('r648_doc01.md', 8, 8, 0, 0.3),
    ('r648_doc01.md', 9, 9, 0, 0.3),
    ('r648_doc04.md', 10, 10, 0, -1.0),
    ('r648_doc01.md', 12, 11, 1, 0.3),
    ('r648_doc05.md', 11, 12, -1, 0.0),
    ('r648_doc01.md', 13, 13, 0, 0.3),
    ('r648_doc01.md', 14, 14, 0, 0.3),
    ('r648_doc01.md', 16, 15, 1, 0.3),
    ('r648_doc06.md', 15, 16, -1, 0.0),
    ('r648_doc01.md', 17, 17, 0, 0.3),
    ('r648_doc01.md', 19, 18, 1, 0.3),
    ('r648_doc04.md', 18, 19, -1, -1.0),
    ('r648_doc01.md', 20, 20, 0, 0.3),
    ('r648_doc03.md', 22, 21, 1, 0.5),
    ('r648_doc01.md', 21, 22, -1, 0.3),
    ('r648_doc01.md', 24, 23, 1, 0.3),
    ('r648_doc04.md', 23, 24, -1, -1.0),
    ('r648_doc05.md', 25, 25, 0, 0.0),
    ('r648_doc01.md', 27, 26, 1, 0.3),
    ('r648_doc05.md', 26, 27, -1, 0.0),
    ('r648_doc01.md', 29, 28, 1, 0.3),
    ('r648_doc07.md', 28, 29, -1, 0.0),
    ('r648_doc01.md', 30, 30, 0, 0.3),
    ('r648_doc01.md', 31, 31, 0, 0.3),
    ('r648_doc01.md', 32, 32, 0, 0.3),
    ('r648_doc01.md', 33, 33, 0, 0.3),
    ('r648_doc01.md', 34, 34, 0, 0.3),
    ('r648_doc03.md', 36, 35, 1, 0.5),
    ('r648_doc01.md', 35, 36, -1, 0.3),
    ('r648_doc01.md', 37, 37, 0, 0.3),
    ('r648_doc01.md', 39, 38, 1, 0.3),
    ('r648_doc08.md', 38, 39, -1, 0.0),
    ('r648_doc01.md', 40, 40, 0, 0.3),
)


def ann_rows(limit=None):
    """把在册名次折成量具 ``_hit_dicts`` 吃的那份行（正文是占位串：先验不读它）。"""
    rows = REAL_ANN_TOP40[:limit] if limit else REAL_ANN_TOP40
    return [{"filename": name, "chunk_index": index, "classification": classification,
             "department": department, "distance": distance,
             "content_head": "r648-placeholder-%02d" % position}
            for position, (name, index, classification, department, distance)
            in enumerate(rows, start=1)]
def report_for(tmp_path, *, hits=None, priors=None, widths=(5, 12, 40), content_swap=False):
    """在册快照 → 产品自己的命中字典 → 产品自己的排序 → 量具的位移读数（全程零连库）。"""
    gauge = load_gauge(tmp_path, "order_bound")
    rows = ann_rows()
    if content_swap:
        rows = [dict(row, content_head="swapped-content-%d" % index)
                for index, row in enumerate(rows)]
    built = gauge.product_hit_dicts(rows)
    return gauge.displacement_report(built, priors or BOOKED_PRIORS, widths=widths)


def test_the_snapshot_rows_are_a_real_ann_window_not_invented_ranks():
    """快照自己必须先像一次真 ANN 回来的东西：40 行、距离严格递增、名次唯一。"""
    assert len(REAL_ANN_TOP40) == 40
    distances = [row[4] for row in REAL_ANN_TOP40]
    assert distances == sorted(distances), "真库 l2 名次必须单调不减，否则这份快照不是 ANN 回来的"
    assert len(set(distances)) == 40, "距离出现并列 ⇒ 名次不是从库里读出来的"
    assert len({(row[0], row[1]) for row in REAL_ANN_TOP40}) == 40, "同一枚 (文档, chunk) 占不了两个名次"
    assert {row[2] for row in REAL_ANN_TOP40} == {1, 2, 3, 4}
    assert {row[3] for row in REAL_ANN_TOP40} == {"finance", "hr", "engineering", "sales"}
    assert all(row[0].startswith("r648_") for row in REAL_ANN_TOP40)


def test_the_window_is_concentrated_enough_that_one_document_can_move_many_seats():
    """集中度是真库形状（放大率的真读数）：一篇打点会同时注记窗口里的多枚命中。"""
    concentration = {width: len({row[0] for row in REAL_ANN_TOP40[:width]})
                     for width in (5, 12, 40)}
    assert concentration == {5: 2, 12: 5, 40: 8}, concentration
    dominant = max({row[0] for row in REAL_ANN_TOP40},
                   key=lambda name: sum(1 for row in REAL_ANN_TOP40 if row[0] == name))
    seats = sum(1 for row in REAL_ANN_TOP40 if row[0] == dominant)
    assert seats == 27, "那篇独占 40 席中的 " + str(seats) + " 席：放大率漂了就得重取快照"
    assert seats / 40 > 0.5, "一篇过半 ⇒ 一次打点能同时挪动整条腿的大半席位"


def test_the_bound_holds_on_real_readings_at_every_booked_width(tmp_path):
    """判据①：三档腿宽的位移全部夹在那根界里，且界是从量具钉死的那枚数（1 名次）。"""
    report = report_for(tmp_path)
    assert sorted(report) == ["12", "40", "5"]
    for width, readings in report.items():
        booked = BOOKED_WIDTH_READINGS[int(width)]
        assert readings["bound_booked"] == 1, width
        assert readings["bound_constant_in_module"] == 1, width + "：R153 的界被人改了"
        assert readings["max_abs_places_moved"] <= readings["bound_booked"], readings
        assert readings["within_bound"] is True, readings
        assert readings["max_abs_places_moved"] == booked["max_abs_places_moved"], width
        assert readings["carriers_shifted"] == booked["carriers_shifted"], width
        assert readings["distinct_filenames"] == booked["distinct_filenames"], width
        assert readings["carriers_noted"] == int(width), "注记枚数必须等于腿宽：候选一个不许少"


def test_the_displacement_is_not_vacuous_somebody_actually_moved(tmp_path):
    """界成立的前提是**有人被挪过**：一档都没挪的绿是空炮。"""
    report = report_for(tmp_path)
    assert [report[str(width)]["carriers_shifted"] for width in (5, 12, 40)] == [2, 6, 22]


def test_every_single_move_is_exactly_one_place_or_none(tmp_path):
    """逐枚点名：位移只许 0 或 ±1，``new_rank`` 与 ``places_moved`` 必须自洽，候选集一个字不变。"""
    report = report_for(tmp_path)
    for move in report["40"]["moves"]:
        assert abs(move["places_moved"]) <= 1, move
        assert move["new_rank"] == move["previous_rank"] - move["places_moved"], move
    previous = sorted(item["previous_rank"] for item in report["40"]["moves"])
    newer = sorted(item["new_rank"] for item in report["40"]["moves"])
    assert previous == newer == list(range(1, 41)), "候选的进出一个都不许动"


def test_the_negative_side_of_the_bound_is_measured_too(tmp_path):
    """只有驳回那一枚样本：负方向同样夹在一名里（界是正负两侧同一个数）。"""
    report = report_for(tmp_path)
    lows = [item for item in report["40"]["moves"] if item["places_moved"] < 0]
    assert lows, "负方向一次都没量到 ⇒ 这枚界只证了半边"
    assert min(item["places_moved"] for item in lows) == -1
    rejected_only = [item for item in report["40"]["moves"] if item["source"] == "r648_doc04.md"]
    assert {item["shift_ranks"] for item in rejected_only} == {-1.0}, rejected_only
    assert all(item["accepted"] == 0 and item["rejected"] == 4 for item in rejected_only)


def test_the_note_carries_both_columns_not_a_single_net_value(tmp_path):
    """答案侧注记必须把 accepted / rejected 分列带着走：净值 0 的两种来历不许被抹平。"""
    from app.rag.retriever import activity_prior_value, signal_prior_value

    report = report_for(tmp_path)
    notes = {item["source"]: item for item in report["40"]["moves"]}
    assert notes["r648_doc01.md"]["accepted"] == 10
    assert notes["r648_doc01.md"]["rejected"] == 7
    net_zero = {"accepted": 5, "rejected": 5}
    assert activity_prior_value(net_zero) == 0.0
    assert activity_prior_value({"accepted": 0, "rejected": 0}) == 0.0
    assert activity_prior_value(None) == 0.0
    assert signal_prior_value(net_zero) == 0.0
    assert notes["r648_doc02.md"]["accepted"] == 0 and notes["r648_doc02.md"]["rejected"] == 0


def test_no_signal_returns_the_same_object_on_the_real_window(tmp_path):
    """判据②在真窗上同样成立：没有任何先验时交回的是**同一个对象**。"""
    report = report_for(tmp_path)
    for width in ("5", "12", "40"):
        assert report[width]["no_signal_returns_same_object"] is True, width


def test_the_prior_never_reads_the_chunk_text(tmp_path):
    """正文换成一整批占位串之后，位移读数逐枚不变：先验真的只读计数。"""
    plain = report_for(tmp_path)
    swapped = report_for(tmp_path, content_swap=True)
    assert plain == swapped
def test_the_live_real_store_still_reproduces_the_booked_order_readings(tmp_path):
    """真腿开着就复算并逐格对账；关着就交回显式「未量到」＋原因码（这里没有 skip 可用）。"""
    gauge = load_gauge(tmp_path, "order_live")
    if not REAL_PG_OPT_IN:
        leg = gauge.run_report(env={}, legs=("order",))["legs"]["order"]
        assert leg["status"] == "unmeasured"
        assert leg["reason_code"] == gauge.REASON_GATE_OFF
        assert gauge.walk_measurement_keys([leg]) == []
        assert leg["note"], "未量到那一格必须说清量的是什么"
        return
    report = gauge.run_report(legs=("order", "cleanup"))
    leg = report["legs"]["order"]
    assert leg["status"] == "measured", leg
    live_rows = [(item["fake_filename"], int(item["chunk_index"]), float(item["distance"]))
                 for item in leg["ann_rows"]]
    assert live_rows == [(row[0], row[1], row[4]) for row in REAL_ANN_TOP40], (
        "真库名次漂了（沙盒被重建或被别人打过点）：本单的位移读数要重取")
    assert leg["provenance"]["ef_search_width"] == EF_SEARCH_WIDTH
    assert leg["provenance"]["ranking_statement_sha256"] == RANKING_STATEMENT_SHA256
    assert leg["provenance"]["query_seed"] == QUERY_SEED
    assert leg["provenance"]["scope"] == SCOPE
    assert leg["relabeled_concentration"] == {"5": 2, "12": 5, "40": 8}
    assert len(live_rows) == 40 and len({item[2] for item in live_rows}) == 40
    assert len({item[0] for item in live_rows}) == leg["distinct_real_filenames"] == 8
    for width, readings in leg["displacement"].items():
        booked = BOOKED_WIDTH_READINGS[int(width)]
        assert readings["max_abs_places_moved"] == booked["max_abs_places_moved"], width
        assert readings["carriers_shifted"] == booked["carriers_shifted"], width
        assert readings["within_bound"] is True, width
    live_moves = [(item["source"], item["previous_rank"], item["new_rank"],
                  item["places_moved"], item["shift_ranks"])
                  for item in leg["displacement"]["40"]["moves"]]
    assert live_moves == list(BOOKED_MOVES_AT_40)
    cleanup = report["legs"]["cleanup"]
    assert cleanup["rows_returned_to_original"] is True, cleanup