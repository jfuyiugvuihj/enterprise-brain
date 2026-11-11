# -*- coding: utf-8 -*-
r"""R572·判据③：引用者钉吃的把手名必须**从真源派生**，两枚派生源被摘掉就得红。

病（跟进单 §151 三·症状①）：`tests/test_r253_no_test_rewrites_a_tracked_file.py` 末尾那枚
引用者钉把旧姿势的把手名写成字面量 `"_TempEdit(" in source`——手抄第二份真源。`c9a782e`（R556）
把 `tests/test_r48_headline_never_enters_the_text_ledger.py` 迁进 `r466.install_mutation`
之后，那枚在册钉的反证件与变异本体一枚都没少，只是换了把手名，于是引用者钉把它判成红。

四格读数（乙、丙是把在册钉本身咬红的刀，victim 逐枚点名在本件函数名与凭据纸里）：
  甲 派生集合两头都认得出：旧姿势的骨架名（`ShadowEdit` 与各件的 `_TempEdit`）与新姿势的
     装变异那一腿（`install_mutation`、包它的 `_chat_window`）。同时它不许把公开面灌成一张
     大网：`ShadowRoot`／`EditInfo`（不是上下文管理器）、`live_view`／`changed_bindings`
     （不是 ``@contextmanager``）、名叫 ``test_*`` 的用例本体，一枚都不该在里面。
  乙 刀：摘掉射程内某一枚件的把手调用（只摘输入面）⇒ 引用者钉必须红并**指名那枚件**。
  丙 刀：两枚派生源一起摘掉 ⇒ 派生集合空 ⇒ 同一枚判据红在「派生不到名字」，
     不许它退回一份手抄名单照样绿。
  丁 合成件正控：换一份名字全是现编的输入面（`ZephyrWindow`／`fit_mutation`／`_zed_window`），
     同一枚派生与同一枚判据照样认得出窗——认得出才叫派生，认不出就是手抄。
"""
import hashlib

import pytest

import tests.test_r253_no_test_rewrites_a_tracked_file as pin

REPO = pin.REPO
SKELETON_REL = pin.SOURCE_OF_WINDOW_BASES
POSTURE_REL = pin.SOURCE_OF_POSTURE_HANDLES
HOMES = tuple(sorted(pin.COUNTER_PROOF_HOMES))
WATCHED = (SKELETON_REL, POSTURE_REL) + HOMES


def sha256_of(rel: str) -> str:
    """盘上那枚文件的逐字节 sha256：反证只动输入面，被跟踪文件一枚都不许脏。"""
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def digests() -> dict:
    return {rel: sha256_of(rel) for rel in WATCHED}


def test_jia_the_derived_set_names_both_postures_and_stops_at_the_window():
    """甲 正控：两头都认得出，非窗的公开面灌不进来。"""
    sources = pin.suite_sources()
    handles = pin.window_handles(sources)
    readings = pin.assert_homes_still_ship_their_counter_proofs(sources, handles)
    assert {"ShadowEdit", "_TempEdit"} <= handles, sorted(handles)
    assert {"install_mutation", "_chat_window"} <= handles, sorted(handles)
    assert not {"ShadowRoot", "EditInfo", "live_view", "changed_bindings"} & handles, \
        sorted(handles)
    assert not [name for name in handles if name.startswith("test")], sorted(handles)
    assert set(readings) == set(HOMES), readings
    for rel, (count, used) in readings.items():
        assert count >= pin.COUNTER_PROOF_HOMES[rel], (rel, count)
        assert used and set(used) <= handles, (rel, used)
    print("[r572] 派生把手 %d 枚，射程读数 %s" % (len(handles), readings))


def test_yi_a_home_that_stops_calling_any_handle_goes_red():
    """乙 刀（victim＝引用者钉本体）：射程内某枚件不再调用任何把手 ⇒ 红并指名它。"""
    before = digests()
    sources = pin.suite_sources()
    victim = "tests/test_r48_headline_never_enters_the_text_ledger.py"
    text, _tree = sources[victim]
    assert "_chat_window(" in text, "victim 的形状变了，这把刀要跟着重写"
    neutered = text.replace("_chat_window(", "_r572_window_gone(")
    stripped = dict(sources)
    stripped.update(pin.parse_sources({victim: neutered}))
    assert sha256_of(victim) == before[victim], "摘的应当只是输入面：盘上那枚已经脏了"
    with pytest.raises(AssertionError) as caught:
        pin.assert_homes_still_ship_their_counter_proofs(stripped)
    message = str(caught.value)
    assert victim in message, message[:200]
    assert "没有在册反证窗把手" in message, message[:200]
    print("[r572] 乙 实际报错原文：", message[:150])
    assert digests() == before, "反证写脏了被跟踪文件"


def test_bing_stripping_the_derivation_sources_goes_red():
    """丙 刀（victim＝引用者钉本体）：两枚真源摘掉 ⇒ 派生空 ⇒ 红在「派生不到名字」。"""
    before = digests()
    sources = pin.suite_sources()
    stripped = dict(sources)
    stripped.pop(SKELETON_REL)
    stripped.pop(POSTURE_REL)
    assert pin.window_handles(stripped) == frozenset(), "派生源摘不掉：闭包在别处认出了把手"
    with pytest.raises(AssertionError) as caught:
        pin.assert_homes_still_ship_their_counter_proofs(stripped)
    message = str(caught.value)
    assert "派生不到任何一枚窗把手名" in message, message[:200]
    assert SKELETON_REL in message and POSTURE_REL in message, message[:200]
    print("[r572] 丙 实际报错原文：", message[:150])
    assert digests() == before, "反证写脏了被跟踪文件"


def test_ding_a_synthetic_corpus_with_invented_names_is_still_recognised():
    """丁 合成件正控：名字全是现编的一份输入面，同一枚派生与判据照样认得出窗。

    这一格拦的是最省事的假修法——把字面量 `_TempEdit(` 换成另一串手抄名字。现编的名字
    没有任何一份手抄名单能提前含有它：认得出就是真派生。
    """
    before = digests()
    skeleton = (
        "class ZephyrWindow:\n"
        "    def __enter__(self):\n        return {}\n\n"
        "    def __exit__(self, *exc):\n        return False\n\n"
        "class ZephyrNotes:\n    pass\n"
    )
    posture = (
        "import contextlib\n\n\n"
        "@contextlib.contextmanager\n"
        "def fit_mutation(module, path, text):\n    yield {}\n\n\n"
        "def not_a_handle(view):\n    return view\n"
    )
    home = {rel: "" for rel in HOMES}

    def opener(index):
        return (
            "def _zed_window_%d(edits):\n"
            "    with ZephyrWindow(1, edits) as info:\n"
            "        with fit_mutation(None, None, '') as mutant:\n"
            "            info['bindings'] = sorted(mutant)\n"
            "            yield info\n\n\n" % index)

    for rel, needed in pin.COUNTER_PROOF_HOMES.items():
        body = "".join(opener(index) for index in range(needed))
        calls = "".join(
            "def test_counter_evidence_%d_with_a_window():\n"
            "    with _zed_window_0([]) as info:\n        assert info\n\n\n" % index
            for index in range(needed))
        home[rel] = body + calls
    corpus = dict(home)
    corpus[SKELETON_REL] = skeleton
    corpus[POSTURE_REL] = posture
    sources = pin.parse_sources(corpus)
    handles = pin.window_handles(sources)
    assert {"ZephyrWindow", "fit_mutation"} <= handles, sorted(handles)
    assert not {"ZephyrNotes", "not_a_handle"} & handles, sorted(handles)
    readings = pin.assert_homes_still_ship_their_counter_proofs(sources)
    for rel, (count, used) in readings.items():
        assert count >= pin.COUNTER_PROOF_HOMES[rel], (rel, count)
        assert used == ["_zed_window_0"] or "_zed_window_0" in used, (rel, used)
    # 同一份合成件里把三枚射程件的开窗**全摘掉**（反证件名下限照留）：判据必须红，而且红在
    # 「这枚件没有把手」那一格，不是红在「派生不到」——两格分得开，才是两把分开的刀。
    blinded = dict(corpus)
    for rel in HOMES:
        blinded[rel] = "".join(
            "def test_counter_evidence_%d_without_a_window():\n    assert True\n\n\n" % index
            for index in range(pin.COUNTER_PROOF_HOMES[rel]))
    blind = pin.parse_sources(blinded)
    assert pin.window_handles(blind), "派生集合也一起空了：这一把没咬在分格上"
    with pytest.raises(AssertionError) as caught:
        pin.assert_homes_still_ship_their_counter_proofs(blind)
    message = str(caught.value)
    assert "没有在册反证窗把手" in message, message[:200]
    assert any(rel in message for rel in HOMES), message[:200]
    print("[r572] 丁 摘掉合成件的开窗后报错原文：", message[:150])
    assert digests() == before, "反证写脏了被跟踪文件"