# -*- coding: utf-8 -*-
r"""R572·判据②③④的牙：迁到在册姿势的那扇 r253 窗仍然会咬，且不再把活模块漏给下一枚件。

四把刀，victim 全是 `fd90f30` 上就在册的钉（本件只**驱动**它们，不改它们一个字节）：
  刀一  victim `tests/test_r253_shadow_root_holds_the_mutation.py::
        test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file`
        —— 摘掉变异本体（换成一枚不含 `fabricated_note` 的同形变异）⇒ 红在「影子字节没被执行」。
  刀二  同一枚 victim —— 摘掉 `r466.install_mutation` 那一腿（退回裸 `_TempEdit`：今天它
        `execs_module = False`，只落影子副本）⇒ 红在同一格。这把钉的是「迁姿势不许迁成没牙」。
  刀三  victim `...::test_install_source_swaps_the_bytes_not_the_module_object` ＋ conftest 的在册
        R563 守卫 —— 摘掉窗尾那手**按对象身份倒回** ⇒ 本件自己先红，守卫再把这个模块判成漏。
  刀四  victim `tests/test_phase9_private_deps.py::TestOptionalPsycopgImports::
        test_chat_and_alerts_import_without_psycopg`（症状④）—— 先把活模块漏成旧窗尾那个样子，
        再让那枚在册件照原样 `importlib.reload(app.api.v1.chat)` ⇒ 守卫红在它身上，指名 chat 的顶层函数。

每把刀都逐字节核过六枚相关文件的 sha256：摘的只是进程内的名字与活命名空间，盘上一枚都不许动。
"""
import hashlib

import pytest

import tests._temp_edit_overlay as overlay
import tests.test_r253_shadow_root_holds_the_mutation as window
from app.api.v1 import chat

REPO = window.REPO
CHAT_REL = "app/api/v1/chat.py"
SHADOW_REL = "tests/test_r253_shadow_root_holds_the_mutation.py"
REFERRER_REL = "tests/test_r253_no_test_rewrites_a_tracked_file.py"
PHASE9_REL = "tests/test_phase9_private_deps.py"
WATCHED = (CHAT_REL, SHADOW_REL, REFERRER_REL, PHASE9_REL,
           "tests/_temp_edit_overlay.py",
           "tests/test_r466_mutation_does_not_leak_into_live_module.py")
TEETH_MESSAGE = "影子字节没被执行"
#: 在册守卫红时的自报家门；StopIteration（没红）绝不算数。
GUARD_MESSAGE = "R563"


class _Node:
    """conftest 的 R563 守卫只读 `request.nodeid`——手工驱动时的最小替身。"""

    nodeid = "tests/test_r572_the_migrated_window_still_has_teeth.py"


def sha256_of(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def digests() -> dict:
    return {rel: sha256_of(rel) for rel in WATCHED}


def _drive(guard):
    """开一版在册守卫：返回 setup 已跑完的生成器，`next` 到底就是「没红」。"""
    gen = guard.body(_Node())
    next(gen)
    return gen


def _hand_back(module, snapshot: dict) -> None:
    """刀自己的收尾：把活命名空间倒回进门那一刻。

    在册守卫只还原顶层**函数**，常量与类得自己还——刀三刀四造的正是「没人还」那一刻，
    还完必须连值一起还，否则下一枚件替本件挨打（R563 点名的同一族污染）。
    """
    live = module.__dict__
    for name in [key for key in list(live) if key not in snapshot]:
        live.pop(name, None)
    live.update(snapshot)


def _assert_guard_went_red(caught):
    message = str(caught.value)
    assert not isinstance(caught.value, StopIteration), (
        "守卫一声不响：这一把刀是空咬，红没落到在册钉身上")
    assert GUARD_MESSAGE in message, message[:200]
    assert "app.api.v1.chat" in message, message[:200]
    return message


def test_a_the_migrated_window_passes_before_any_knife(monkeypatch, tmp_path):
    """正控：一字节都不摘的时候，迁完姿势的那枚在册钉是绿的——刀才谈得上「摘了就红」。"""
    before = digests()
    window.test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file(
        monkeypatch, tmp_path)
    assert overlay.open_windows() == (), overlay.open_windows()
    assert digests() == before, "正控写脏了被跟踪文件"
    print("[r572] 刀摘前摘后同一枚 sha256（六枚相关文件）：",
          ", ".join("%s=%s" % (rel.split("/")[-1], digest[:16])
                    for rel, digest in sorted(before.items())))


def test_knife_one_neutralising_the_mutation_body_reddens_the_pin(monkeypatch, tmp_path):
    """刀一：把变异本体换成不含 `fabricated_note` 的同形变异 ⇒ 在册钉红在「影子字节没被执行」。"""
    before = digests()
    anchor = window.C1_ANCHOR
    neutral = (anchor + "\n" + chr(34) + "r572_placeholder_note" + chr(34) + ": "
               + chr(34) + "占位" + chr(34) + ",")
    assert "fabricated_note" not in neutral and neutral != anchor, neutral
    monkeypatch.setattr(window, "C1_MUTANT", neutral)
    with pytest.raises(AssertionError) as caught:
        window.test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file(
            monkeypatch, tmp_path)
    assert TEETH_MESSAGE in str(caught.value), str(caught.value)
    print("[r572] 刀一 实际报错原文：", str(caught.value)[:120])
    assert overlay.open_windows() == (), overlay.open_windows()
    assert digests() == before, "反证写脏了被跟踪文件"


def test_knife_two_dropping_the_install_leg_reddens_the_pin(monkeypatch, tmp_path):
    """刀二：摘掉 `install_mutation` 那一腿 ⇒ 同一枚在册钉红在同一格——迁姿势不许迁成没牙。"""
    before = digests()
    monkeypatch.setattr(window, "_chat_window",
                        lambda edits: window._TempEdit(window.CHAT_PY, edits))
    with pytest.raises(AssertionError) as caught:
        window.test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file(
            monkeypatch, tmp_path)
    assert TEETH_MESSAGE in str(caught.value), str(caught.value)
    print("[r572] 刀二 实际报错原文：", str(caught.value)[:120])
    assert overlay.open_windows() == (), overlay.open_windows()
    assert digests() == before, "反证写脏了被跟踪文件"


def test_knife_three_dropping_the_identity_restore_leaks_the_live_module(eb_r563_guard):
    """刀三：摘掉窗尾的按身份倒回 ⇒ 本件自己先红，在册 R563 守卫再把这个模块判成漏。"""
    before = digests()
    live_before = dict(chat.__dict__)
    original_restore = overlay.restore_namespace
    gen = _drive(eb_r563_guard)                         # 基线＝还原在场时的那一份真身
    try:
        overlay.restore_namespace = lambda module, snapshot: []
        with pytest.raises(AssertionError) as pin_caught:
            window.test_install_source_swaps_the_bytes_not_the_module_object()
        assert "窗尾没把活模块的顶层值装回进门那一刻" in str(pin_caught.value), \
            str(pin_caught.value)
        with pytest.raises(BaseException) as caught:
            next(gen)                                   # teardown：在册守卫比对
        print("[r572] 刀三 实际报错原文：", _assert_guard_went_red(caught)[:150].replace("\n", " / "))
    finally:
        overlay.restore_namespace = original_restore
        _hand_back(chat, live_before)
    assert chat.ask is live_before["ask"], "收尾没把活模块还回真身：下一枚件要替本件挨打"
    assert digests() == before, "反证写脏了被跟踪文件"


def test_the_pinned_install_source_case_leaves_no_drift_behind(eb_r563_guard):
    """正控：还原在场时，同一枚在册守卫驱动那枚在册钉必须不红——刀三才不是空咬。"""
    before = digests()
    live_before = dict(chat.__dict__)
    gen = _drive(eb_r563_guard)
    window.test_install_source_swaps_the_bytes_not_the_module_object()
    done = False
    try:
        next(gen)
    except StopIteration:
        done = True
    _hand_back(chat, live_before)
    assert done, "在册守卫仍把本件的还原判成漏：窗尾那一手没真按对象身份倒回"
    assert chat.ask is live_before["ask"]
    assert digests() == before, "正控写脏了被跟踪文件"


def test_knife_four_a_leaked_live_module_reddens_the_next_module(monkeypatch, eb_r563_guard):
    """刀四（症状④的机理）：活模块被漏成旧窗尾那个样子 ⇒ 下一枚 reload chat 的在册件跟着红。

    victim 是 `tests/test_phase9_private_deps.py` 那枚在册件，本件不改它一个字：先照「旧窗尾」
    造一次漏（把盘上的字再 exec 一遍——新对象加 `CO_FUTURE_ANNOTATIONS` 的新码体），再让它按
    原样 reload。它的基线已经是漏脏的那一份，reload 回来的真身反而被判成漂移——这正是 10-03
    门里那枚「单跑绿、合跑红」的 ERROR 的形状。
    """
    import tests.test_phase9_private_deps as phase9

    before = digests()
    live_before = dict(chat.__dict__)
    disk_text = (REPO / CHAT_REL).read_bytes().decode("utf-8")
    overlay.install_source(chat, disk_text, REPO / CHAT_REL)      # 造漏：只 exec，不还身份
    gen = _drive(eb_r563_guard)                                   # 基线＝漏脏的那一份
    try:
        phase9.TestOptionalPsycopgImports().test_chat_and_alerts_import_without_psycopg(
            monkeypatch)                                          # 在册件照原样 reload
        with pytest.raises(BaseException) as caught:
            next(gen)
        print("[r572] 刀四 实际报错原文：", _assert_guard_went_red(caught)[:150].replace("\n", " / "))
    finally:
        _hand_back(chat, live_before)
    assert chat.ask is live_before["ask"]
    assert digests() == before, "反证写脏了被跟踪文件"