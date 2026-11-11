# -*- coding: utf-8 -*-
r"""R583 判据 ③④：名册与派生清单同数（枚数钉改口），另交两把反证证明这枚牙有劲。

判据 ③（甲案落地）：``WINDOWS`` 的行数＝派生清单点名的枚数，钉不再写死 9；那句旧解释
「R466 的九扇在册 + R556 的名单清空」今天也从盘上作废——它是一句假话，留着它会教后来者按单号划族。

判据 ④ 的两把刀（🔴 全部只摘**输入面**，被跟踪文件全程只读，与 R572 那把同形）：

  · 刀一：往 ``tests/**`` 的输入面里塞一扇真往活模块上装变异的窗，却不进册 ⇒ 对账必须红，
    且红在「缺哪枚点名哪枚」。这一格证明名册不是靠手抄维持的：后来者不进册，钉当场拦人。
  · 刀二：从名册里**真删掉一行**（两面同删）⇒ 必须红。再演两枚下限：删到 R466 那九枚里的一枚
    红在「名单不许反弹」；只删文本面红在「两面不许只改一面」。

反证驱动的正是 ``test_r583_window_inventory.assert_roster_matches_the_inventory`` 那一枚本体，
不是另抄一套近似判据——那才是「摘掉守卫照样绿」的温床。
"""
from __future__ import annotations

import ast
import hashlib

import pytest

from tests import test_r253_no_test_rewrites_a_tracked_file as r253pin
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466
from tests import test_r583_window_inventory as r583

ROSTER_NAME = "test_r466_mutation_does_not_leak_into_live_module.py"
ROSTER_REL = "tests/" + ROSTER_NAME
INJECTED_REL = "tests/test_r583_injected_second_window.py"
STALE_READING = "九扇在册 + R556 的名单清空"
OLD_PIN_NAME = "test_the_roster_is_nine_windows_and_none_of_them_execs_the_live_module"
NEW_PIN_NAME = "test_the_roster_is_the_windows_that_install_on_a_live_module"

#: 刀一的弹药：一扇只存在于输入面上的窗——它开窗（`ShadowEdit` 子类）也在同一枚函数里把变异
#: 装到被跟踪文件的**活模块**上（`overlay.module_of` 那一腿），所以派生必须点名它是真实开窗者。
_INJECTED_SOURCE = """# -*- coding: utf-8 -*-
# R583 刀一的合成件：只存在于输入面上，盘上没有这枚文件，也永远不会被 import。
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466


class _InjectedEdit(overlay.ShadowEdit):
    execs_module = False

    def mutate(self, text):
        return text.replace("def _authorize_queue_task", "def _authorize_queue_task_mutated", 1)


def _injected_window():
    path = overlay.REPO / "app" / "api" / "v1" / "chat.py"
    module = overlay.module_of("app/api/v1/chat.py")
    with _InjectedEdit(path) as edit:
        r466.install_mutation(module, path, edit.mutate(path.read_text(encoding="utf-8")))
        yield edit
"""


def _surface_digest(sources: dict) -> str:
    """整枚输入面的指纹：摘前/摘后各交一回，证明刀只落在输入面上。"""
    window = hashlib.sha256()
    for rel in sorted(sources):
        window.update(rel.encode("utf-8"))
        window.update(b"\0")
        window.update(sources[rel][0].encode("utf-8"))
        window.update(b"\0")
    return window.hexdigest()[:12]


def _disk_roster_text() -> str:
    return (r253pin.TESTS_DIR / ROSTER_NAME).read_text(encoding="utf-8")


def _cut_roster_row(text: str, key: str) -> str:
    """从名册文本面剪掉 ``key`` 那一行 dict 字面量（连同它后面那枚逗号），剩下的仍要能解析。"""
    tree = ast.parse(text)
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "WINDOWS" for t in node.targets)):
            continue
        for element in getattr(node.value, "elts", ()):
            if not isinstance(element, ast.Dict):
                continue
            row = {}
            for name_k, value_k in zip(element.keys, element.values):
                if isinstance(name_k, ast.Constant) and isinstance(value_k, ast.Constant):
                    row[name_k.value] = value_k.value
            if row.get("key") != key:
                continue
            segment = ast.get_source_segment(text, element)
            assert segment, "%s 那一行不是纯字面量，剪不出来" % key
            assert text.count(segment) == 1, "%s 的行面在盘上不唯一" % key
            start = text.index(segment)
            after = text[start + len(segment):]
            head = after[: len(after) - len(after.lstrip(" \t"))]
            assert (head + after[len(head):]).lstrip(" \t").startswith(","), (
                "名册那一行后面没有逗号：形状换了，本件要跟着改写")
            return text[:start] + head + after[len(head) + 1:]
    raise AssertionError("名册文本面里没有 key=%s 这一行" % key)


def _positive() -> tuple:
    sources, roster_text = r583.default_surfaces()
    homes = set(r583.inventory(sources)["live"])
    return sources, roster_text, homes


# ------------------------------------------------------------------------------- 判据 ③


def test_the_roster_count_now_comes_from_the_derived_inventory():
    """判据 ③：名册行数＝派生清单枚数，且钉名/旧解释都改了口。"""
    _sources, roster_text, homes = _positive()
    rows = list(r466.WINDOWS)
    readings = r583.assert_roster_matches_the_inventory(rows, r583.roster_rows_from_text(roster_text), homes)
    assert readings["rows"] == readings["derived"] == len(rows) == len(homes), (
        "枚数不同名册：%r vs 盘上 %d 行 / 派生 %d 枚" % (readings, len(rows), len(homes)))
    assert len(rows) > len(r583.HISTORICAL_NINE), (
        "名册还停在 R466 那九枚的账面枚数（%d 行）：甲案要的补齐没落地" % len(rows))
    assert hasattr(r466, NEW_PIN_NAME), "枚数钉没改口：盘上还找得到 %s" % NEW_PIN_NAME
    assert not hasattr(r466, OLD_PIN_NAME), (
        "旧那枚写死枚数的钉还在盘上：%s——它会继续阻止后来者进册" % OLD_PIN_NAME)
    assert STALE_READING not in roster_text, (
        "旧解释那句还留在名册件的docstring 里（%s）：甲案要求一并改掉" % STALE_READING)
    print("[r583] 判据③ 名册 %d 行 = 派生 LIVE %d 枚（旧账 %d 枚）· 钉名已改口 · 旧解释已作废"
          % (readings["rows"], readings["derived"], len(r583.HISTORICAL_NINE)))


# ------------------------------------------------------------------------------- 判据 ④ 刀一


def test_a_live_window_that_stays_out_of_the_roster_reddens_the_reconcile():
    """刀一：新增一扇真往活模块上装变异的窗、却不进册 ⇒ 对账必须红，红在点名那一枚。

    这格才是甲案真正的牙：名册与真实开窗者一旦再度脱节，钉拦人，而不是继续把账面枚数当事实。
    """
    sources, roster_text, homes_before = _positive()
    disk_before = overlay.sha16_of_bytes(roster_text.encode("utf-8"))
    before = _surface_digest(sources)
    r583.assert_roster_matches_the_inventory(
        list(r466.WINDOWS), r583.roster_rows_from_text(roster_text), homes_before)   # 摘前：绿

    injected = dict(sources)
    injected[INJECTED_REL] = (_INJECTED_SOURCE, ast.parse(_INJECTED_SOURCE))
    read = r583.inventory(injected)
    assert INJECTED_REL in read["live"], (
        "派生认不出这扇合成窗（它开窗也往活模块上装变异）：口径瞎了，反证就成了空话；live=%s"
        % (sorted(read["live"]),))
    after = _surface_digest(injected)
    with pytest.raises(AssertionError) as first:
        r583.assert_roster_matches_the_inventory(
            list(r466.WINDOWS), r583.roster_rows_from_text(roster_text), set(read["live"]))
    message = str(first.value)
    assert INJECTED_REL in message, "红没点名缺的那一枚：%s" % message
    assert "没进册" in message, "红在别的格上，刀一量的不是「不进册必须拦」：%s" % message
    assert _disk_roster_text() == roster_text and overlay.sha16_of_bytes(
        roster_text.encode("utf-8")) == disk_before, "刀一动到了盘上的名册：反证只许摘输入面"
    print("[r583] 刀一 摘前输入面 %s（LIVE %d）-> 摘后 %s（LIVE %d）：红在缺册点名 %s；"
          "盘上名册 %s 未变" % (before, len(homes_before), after, len(read["live"]),
                                   INJECTED_REL, disk_before))


# ------------------------------------------------------------------------------- 判据 ④ 刀二


@pytest.mark.parametrize("key,expect", [("r472", "没进册"), ("r310", "名单不许反弹")],
                         ids=["drop-a-newly-registered-row", "drop-a-historical-nine-row"])
def test_a_row_really_deleted_from_the_roster_reddens_the_reconcile(key, expect):
    """刀二：把名册里一枚真删掉 ⇒ 必须红。两枚下限各演一遍。

    ``r472`` 不在 R466 那九枚里，红在「缺哪枚点名哪枚」；``r310`` 在那九枚里，红在「名单不许反弹」。
    🔴 两面同删（文本面与活对象）才有意义：只删一面红的是另一格，下面单独演它。
    """
    _sources, roster_text, homes = _positive()
    disk_before = overlay.sha16_of_bytes(roster_text.encode("utf-8"))
    rows = [row for row in r466.WINDOWS if row["key"] != key]
    assert len(rows) == len(r466.WINDOWS) - 1, "名册里没有 key=%s 这一行" % key
    cut_text = _cut_roster_row(roster_text, key)
    text_rows = r583.roster_rows_from_text(cut_text)
    assert len(text_rows) == len(rows), "剪完还剩 %d 行，不是 %d 行：刀没落在名册那一格" % (
        len(text_rows), len(rows))
    with pytest.raises(AssertionError) as second:
        r583.assert_roster_matches_the_inventory(rows, text_rows, homes)
    message = str(second.value)
    assert expect in message, "删行没红在那一格（%s）：%s" % (expect, message)
    assert _disk_roster_text() == roster_text and overlay.sha16_of_bytes(
        roster_text.encode("utf-8")) == disk_before, "刀一动到了盘上的名册：反证只许摘输入面"
    print("[r583] 刀二 删 %s：名册文本 %s -> %s（%d 行）· 派生仍 %d 枚 · 红在「%s」· 盘上名册 %s 未变"
          % (key, r583.sha12(roster_text), r583.sha12(cut_text), len(text_rows), len(homes),
             expect, disk_before))


def test_the_roster_reddens_when_only_one_of_its_two_faces_moves():
    """刀二的另一面：只剪文本面、活对象不动 ⇒ 红在「不许只改一面」。

    这一格挡的是「名册改了文本却没改活对象（或反之）」——那正是账面与实际再度分叉的形状。
    """
    _sources, roster_text, homes = _positive()
    cut_text = _cut_roster_row(roster_text, "r472")
    text_rows = r583.roster_rows_from_text(cut_text)
    assert len(text_rows) == len(r466.WINDOWS) - 1
    with pytest.raises(AssertionError) as third:
        r583.assert_roster_matches_the_inventory(list(r466.WINDOWS), text_rows, homes)
    message = str(third.value)
    assert "只改了其中一面" in message, "单面改动没被认出：%s" % message
    print("[r583] 刀二·单面 名册文本 %s -> %s：红在「只改一面」"
          % (r583.sha12(roster_text), r583.sha12(cut_text)))