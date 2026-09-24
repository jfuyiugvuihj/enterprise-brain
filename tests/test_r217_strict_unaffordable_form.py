"""R217：预演件里 `always_unaffordable` 必须是「连本档地板都付不起」。

判据出处：跟进单 §93.15 / 看板 §4BX 二。这枚口径松钉不伤客户（`analysis` 之外六档的
`declared` 都低于 `affordable_max`，两式同值），但旧式在 `declared > affordable_max >= floor`
那一段会**同时**印出 `clamp_possible=true`（能夹）与 `always_unaffordable=true`（永远付不起），
下一班照着预演表读就会拿到两枚互相打脸的旗。

标定数（decode 8.0 / prefill 35.0）的出处早就写在 `app/common/model_budget.py:195-222`
（09-16 纯 CPU 读数 + "re-measure before citing"），而改这两个数会当场撞
`test_r99_budget_selfconsistency` / `test_r204_budget_refusal` / `test_r204_single_call_ceiling`
三族既有钉 ⇒ 本件**不重复钉数**，只钉三件事：今天的七档读数不许因这一改而变、两旗永不同时为真、
以及本件自己的牙在不在。
"""

from scripts.rehearse_eval_window import budget_table

FLOORS = (1, 64, 128, 200, 255, 256, 257, 511, 512, 833, 834, 835, 1000, 1536, 2000, 4096)


def _row(rows, tier):
    for row in rows:
        if row["tier"] == tier:
            return row
    raise AssertionError("预演表里没有档位 %r，档位名单变了" % tier)


def test_two_flags_are_never_both_true_under_any_floor():
    """严格式的整个目的：一枚档不能既"能夹到地板"又"连地板都付不起"。"""
    for floor in FLOORS:
        for row in budget_table(floor):
            assert not (row["clamp_possible"] and row["always_unaffordable"]), (
                "floor=%d 档 %s 同时举起两旗：clamp_possible 说能把 max_tokens 夹到地板，"
                "always_unaffordable 说连地板都付不起 —— %r" % (floor, row["tier"], row))


def test_the_discriminating_shape_reports_clampable_not_impossible():
    """两式唯一分歧的那一段（旧式在此假阳）。

    `floor_override=200` 是拿来造形状的，不是任何现网配置：`analysis` 声明 1536、
    钟最多付 834，把地板压到 200 之后 200 <= 834 < 1536 ⇒ 这一档**能夹**，
    旧式 `affordable_max < declared` 会把它一并报成"永远付不起"。
    """
    row = _row(budget_table(200), "analysis")
    assert row["clamp_possible"] is True, row
    assert row["always_unaffordable"] is False, row
    assert row["affordable_max"] < row["declared"], "这一格仍是「写不满声明的帽」，只是付得起地板"


def test_this_pieces_has_teeth_the_old_formula_would_have_let_that_row_through():
    """自证本件不是空转：把旧式复算一遍，必须存在被新式纠正的行。"""
    corrected = []
    for floor in FLOORS:
        for row in budget_table(floor):
            old = row["affordable_max"] < row["declared"]
            if old != row["always_unaffordable"]:
                corrected.append((floor, row["tier"], old, row["always_unaffordable"]))
    assert corrected, "旧式与新式逐格同值 ⇒ 这一改没有对象，本件该删"
    assert (200, "analysis", True, False) in corrected, corrected[:8]


def test_today_seven_tiers_read_exactly_the_same_as_before_the_fix():
    """防"顺手翻表"：现网口径（地板取代码现值）下七档读数一格都不许动。"""
    rows = budget_table(None)
    assert [r["tier"] for r in rows] == [
        "chat", "plan", "compress", "rewrite", "code", "alert", "analysis"], [r["tier"] for r in rows]
    assert [(r["tier"], r["declared"], r["clamp_possible"], r["always_unaffordable"]) for r in rows] == [
        ("chat", 256, False, False),
        ("plan", 256, False, False),
        ("compress", 512, False, False),
        ("rewrite", 256, False, False),
        ("code", 512, False, False),
        ("alert", 384, False, False),
        ("analysis", 1536, False, True),
    ], rows
    assert all(r["affordable_max"] == 834 for r in rows), [r["affordable_max"] for r in rows]
    assert all(r["floor"] == 1536 for r in rows), [r["floor"] for r in rows]


def test_analysis_is_still_the_only_zero_margin_tier_and_stays_named_honestly():
    """`analysis` 的 `always_unaffordable` 必须仍为真：预演件逐题那枚 mode 文案
    （"②analysis档预算自相矛盾(恒budget_unaffordable,永不clamped)"）靠它成立。"""
    rows = budget_table(None)
    impossible = [r["tier"] for r in rows if r["always_unaffordable"]]
    assert impossible == ["analysis"], impossible
    analysis = _row(rows, "analysis")
    assert analysis["declared"] == analysis["floor"] == 1536, analysis
    assert [r["tier"] for r in rows if r["declared"] > r["affordable_max"]] == ["analysis"], rows
