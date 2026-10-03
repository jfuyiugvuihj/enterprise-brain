# -*- coding: utf-8 -*-
r"""R589 判据①②：射程内有文件解析不了 ⇒ 直接红并点名文件与行列，且不许与名册钉互相掩盖。

病（跟进单 §157 二，总控 10-03 现场复现）：本族「射程内测试件集合」是按**能否 parse** 长出来的，
两条坏腿都在盘上生活过——

  · **静默缩集**：``tests/test_r516_the_dataset_stubs_stay_on_the_class.py::_all_rows`` 在本单起点
    ``245315b`` 上是 ``except SyntaxError: continue``（盘上确有其码，本件戊格沿 AST 逐枚扫这一形状）。
    一枚解析不了的件被无声摘出集合 ⇒ 它名下的账从此不在射程里，而每一枚在册钉照样全绿；
    ``assert handles`` 那种「集合为空才红」的守卫救不了「集合少一枚」。
  · **红得没法照着改**：``tests/test_r253_no_test_rewrites_a_tracked_file.py::suite_sources`` 交
    ``ast.parse`` 时不收 ``filename``，原文抛出去报的是那条不带文件名的 SyntaxError——不点名是哪枚文件，
    于是别人（或总控自己）的一枚手抖被读成一次回归（10-03 现跑：同一段射程红在三枚与本单无关的钉上）。

治法落在该族唯一的口径（``tests/_temp_edit_overlay.py`` 里 R589 那一段）：射程只由 ``in_range_test_rels()``
枚举一次，解析只由 ``parse_in_range()`` 收口一次，「少一枚」由 ``assert_covers_the_range()`` 逐枚对账。

六格读数（本件的牙，🔴 全部只摘**合成输入面**，被跟踪文件全程只读，与 R572／R583 那两把同形）：
  甲 正控：射程内每一枚都解析得了，且严格口径与 R253 那枚真派生者交回的面**同样覆盖整段射程**；
  乙 刀①：往输入面塞一枚解析不了的件 ⇒ 红，红字点名文件、第几行、第几列、原文那一句、什么错；
  丙 刀①的另一半：把一枚件**静默摘出**输入面 ⇒ 「把手集合非空」那格照样绿（演给你看它为什么不够），
     而逐枚对账红着点名那一枚；
  丁 判据②：两枚钉不许互相掩盖——塞解析不了的件只动本件这枚口径（名册对账本体的回答一字不变），
     名册少一行只动名册那枚（本件的严格口径在盘上仍绿且仍覆盖整段射程）；再演一格结构：两枚判据
     各是各的本体、互不引用、红字词表不相交 ⇒ 不许缝成一枚断言；
  戊 全族扫一遍：射程内派生件里「解析不了就 continue／pass／置 None」的形状一枚不许留（起点只剩 r516
     那一处，本单已改掉）；
  己 判据③第二把刀的常驻形：一枚**合法却不该进集**的件（能解析、开窗、从不往活模块上装变异）⇒
     派生把它落进 no_install，LIVE 枚数与名册对账读数一枚都不许变。

🔴 没治完的那一半（等总控批，见凭据纸 §6）：``tests/test_r253_*.py`` 在本单**禁碰**清单里，它自己那两手
不带 ``filename`` 的 ``ast.parse`` 今天还在。所以盘上真出现一枚坏件时，r253 的三格会与本件①那格**同时**红，
前者仍报那条不带文件名的原文；本件的红字点名文件与行列，接手的人从它读起。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

from tests import _temp_edit_overlay as overlay
from tests import test_r253_no_test_rewrites_a_tracked_file as r253pin
from tests import test_r466_mutation_does_not_leak_into_live_module as r466
from tests import test_r583_window_inventory as r583

HERE_REL = "tests/" + Path(__file__).name
BROKEN_REL = "tests/test_r589_synthetic_piece_that_does_not_parse.py"
#: 弹药那一句里的第二个等号就是要它崩。行列不手抄：本件从 SyntaxError 现取（见 _syntax_error_of）。
BROKEN_TEXT = "# R589 合成件：盘上没有这枚文件，也不许有——反证只摘输入面。\nvalue = = 2\n"
BROKEN_SOURCE_LINE = "value = = 2"

#: 「合法却不该进集」的弹药：能解析、开窗，但一枚活模块都不碰 ⇒ 派生只能把它落进 no_install。
QUIET_REL = "tests/test_r589_synthetic_piece_that_installs_nothing.py"
_QUIET_SOURCE = """# -*- coding: utf-8 -*-
# R589 己格与判据③第二把刀的弹药：只存在于输入面上，盘上没有这枚文件。
from tests import _temp_edit_overlay as overlay


class _QuietEdit(overlay.ShadowEdit):
    execs_module = False

    def mutate(self, text):
        return text.replace("def _authorize_queue_task", "def _authorize_queue_task_quiet", 1)


def _quiet_window():
    path = overlay.REPO / "app" / "api" / "v1" / "chat.py"
    with _QuietEdit(path) as edit:
        yield edit
"""

#: 严格口径的公开把手名：派生「谁在用这枚口径」时按这些尾名认，不抄文件名。
GATE_HANDLES = ("parse_in_range", "in_range_test_rels", "in_range_test_paths",
                "assert_covers_the_range", "describe_parse_failure")
#: 「这枚函数确实在枚举 tests 射程」的形状指纹（戊格用它划界，不伤 app/** 那一族尺子）。
_RANGE_MARK_NAMES = {"TESTS_DIR", "RANGE_DIR"}
_CACHED: dict = {}
#: 传给 ``r583.inventory`` 的面按 ``id()`` 缓存：留一枚强引用，别让地址被回收后撞车。
_KEEP: dict = {}


def scope() -> tuple:
    """射程：盘上现枚举，全族唯一口径（``overlay.in_range_test_rels``）。"""
    if "scope" not in _CACHED:
        _CACHED["scope"] = overlay.in_range_test_rels()
    return _CACHED["scope"]


def surface() -> dict:
    """严格口径交回的那份输入面 ``rel -> (文本, AST)``：本件只在窗外读盘，一枚都不改写。"""
    if "surface" not in _CACHED:
        _CACHED["surface"] = overlay.parse_in_range()
    return _CACHED["surface"]


def disk_token() -> str:
    """整段射程的逐字节指纹：反证只摘输入面，盘上这一面必须一枚不动。"""
    window = hashlib.sha256()
    for rel in scope():
        window.update(rel.encode("utf-8"))
        window.update(b"\0")
        window.update((r253pin.REPO / rel).read_bytes())
        window.update(b"\0")
    return window.hexdigest()[:12]


def _tail(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def gate_users(trees: dict = None) -> tuple:
    """射程内「用了这枚严格口径的件」：沿 AST 现派生，不手抄（R583 立的那条规矩）。"""
    source = surface() if trees is None else trees
    out = []
    for rel, (_text, tree) in sorted(source.items()):
        if any(isinstance(node, ast.Call) and _tail(node.func) in GATE_HANDLES
               for node in ast.walk(tree)):
            out.append(rel)
    return tuple(out)


def _syntax_error_of(text: str):
    try:
        ast.parse(text, filename="synthetic")
    except SyntaxError as exc:
        return exc
    raise AssertionError("合成弹药自己解析得过：这把刀是钝的")


def _enumerates_range(fn) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id in _RANGE_MARK_NAMES:
            return True
        if isinstance(node, ast.Call):
            tail = _tail(node.func)
            if tail in GATE_HANDLES:
                return True
            if tail == "rglob" and any(isinstance(arg, ast.Constant)
                                       and isinstance(arg.value, str) and "tests" in arg.value
                                       for arg in node.args):
                return True
    return False


def _walks_on(handler) -> bool:
    """这枚 handler 收了异常之后**继续走**吗：``continue``／``pass``／把结果置 ``None`` 都算。"""
    if not handler.body:
        return True
    return all(isinstance(statement, (ast.Continue, ast.Pass))
               or (isinstance(statement, ast.Assign)
                   and isinstance(statement.value, ast.Constant)
                   and statement.value.value is None)
               for statement in handler.body)


def _quiet_swallow_shapes(trees: dict) -> list:
    """射程内「解析不了就当它不在射程」的形状清单（枚枚点名：文件::函数:行 handler -> 动作）。"""
    out = []
    for rel, (_text, tree) in sorted(trees.items()):
        for fn in [node for node in ast.walk(tree)
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            if not _enumerates_range(fn):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.Try):
                    continue
                for handler in node.handlers:
                    caught = ast.unparse(handler.type) if handler.type else "BARE"
                    if _walks_on(handler):
                        out.append("%s::%s:L%d %s -> %s" % (
                            rel, fn.name, node.lineno, caught, ast.unparse(handler)))
    return out


# --------------------------------------------------------------------------- 甲 正控


def test_the_range_is_enumerated_once_and_every_piece_parses():
    """甲：射程内每一枚解析得了，且严格口径与 R253 那枚真派生者同样覆盖整段射程。"""
    expected = scope()
    # 下限贴着本单基点现量（实测 640 枚）：射程缩水就等于没扫。
    assert len(expected) >= 600, (
        "射程只枚举到 %d 枚件：口径缩水了，判据①量的就不是它要量的东西" % len(expected))
    parsed = surface()
    assert set(parsed) == set(expected)
    strict = overlay.assert_covers_the_range(parsed.keys(), expected, where="overlay.parse_in_range()")
    derived = overlay.assert_covers_the_range(
        r253pin.suite_sources().keys(), expected,
        where="tests/test_r253_no_test_rewrites_a_tracked_file.py::suite_sources()")
    assert strict["missing"] == derived["missing"] == ()
    assert strict["surface"] == derived["surface"] == len(expected), (strict, derived)
    users = gate_users()
    assert HERE_REL in users and len(users) >= 2, (
        "严格口径在射程内没有第二个使用者（%s）：它就是一枚没人走的装饰件" % (users,))
    print("[r589] 甲 射程 %d 枚全解析 · 严格口径覆盖 extra=%d · R253 派生面覆盖 extra=%d · "
          "口径使用者 %d 枚 · 盘上指纹 %s"
          % (len(expected), len(strict["extra"]), len(derived["extra"]), len(users), disk_token()))


# ------------------------------------------------------------------ 乙·丙 判据 ① 的两把刀


def test_an_unparsable_piece_in_the_range_reds_the_gate_and_names_the_file_line_and_column():
    """乙 刀①（只摘输入面）：解析不了的件 ⇒ 红，且点名文件、第几行、第几列、原文、错误。"""
    before = disk_token()
    injected = {rel: value[0] for rel, value in surface().items()}
    injected[BROKEN_REL] = BROKEN_TEXT
    exc = _syntax_error_of(BROKEN_TEXT)
    with pytest.raises(AssertionError) as caught:
        overlay.parse_in_range(injected)
    message = str(caught.value)
    assert "射程内有 1 枚件解析不了" in message, message[:240]
    assert BROKEN_REL in message, message[:240]
    assert "第 %d 行" % exc.lineno in message, message[:240]
    assert "第 %d 列" % exc.offset in message, message[:240]
    assert BROKEN_SOURCE_LINE in message, message[:240]
    assert exc.msg in message, message[:240]
    assert "SyntaxError" in message, message[:240]
    assert "<unknown>" not in message, "红字里还带着那条不带文件名的原文：那就没法照着改"
    assert disk_token() == before, "刀落到了盘上：反证只许摘输入面"
    print("[r589] 乙 合成弹药 %s -> 红字点名 第 %d 行 第 %d 列（%s）；盘上射程 %s 一枚未动"
          % (BROKEN_REL, exc.lineno, exc.offset, exc.msg, before))


def test_a_quietly_dropped_piece_goes_red_while_the_emptiness_guard_stays_green():
    """丙 刀①的另一半：集合少一枚。空集守卫看不见它，逐枚对账看得见。"""
    expected = scope()
    keep = [rel for rel in sorted(expected)
            if rel not in (r253pin.SOURCE_OF_WINDOW_BASES, r253pin.SOURCE_OF_POSTURE_HANDLES)]
    victim = keep[-1]
    neutered = {rel: value for rel, value in surface().items() if rel != victim}
    assert len(neutered) == len(expected) - 1, (len(neutered), len(expected))
    handles = r253pin.window_handles(neutered)
    assert handles, "演示塌了：摘掉 %s 之后派生把手就空了，旧那格守卫本来就会红" % victim
    with pytest.raises(AssertionError) as caught:
        overlay.assert_covers_the_range(neutered.keys(), expected,
                                        where="合成：一枚件被静默摘出输入面")
    message = str(caught.value)
    assert victim in message, message[:240]
    assert "静默缩集" in message, message[:240]
    assert "少了 1 枚" in message, message[:240]
    print("[r589] 丙 摘掉 %s：输入面 %d -> %d 枚（旧那格只看把手非空，仍绿：%d 枚把手），"
          "逐枚对账红着点名它" % (victim, len(expected), len(neutered), len(handles)))


# ------------------------------------------------------------------------- 丁 判据 ②


def test_a_broken_piece_in_the_range_does_not_move_the_roster_verdict():
    """丁 上半：塞一枚解析不了的件 ⇒ 只红本件这枚口径，名册那枚对账本体的回答一字不变。"""
    sources, roster_text = r583.default_surfaces()
    _KEEP["clean_sources"] = sources
    homes = set(r583.inventory(sources)["live"])
    rows, text_rows = list(r466.WINDOWS), r583.roster_rows_from_text(roster_text)
    before = r583.assert_roster_matches_the_inventory(rows, text_rows, homes)
    token = disk_token()
    injected = {rel: value[0] for rel, value in surface().items()}
    injected[BROKEN_REL] = BROKEN_TEXT
    with pytest.raises(AssertionError) as caught:
        overlay.parse_in_range(injected)
    assert BROKEN_REL in str(caught.value), str(caught.value)[:240]
    after = r583.assert_roster_matches_the_inventory(rows, text_rows, homes)
    assert after == before, "两枚判据被缝到了一枚断言上：①的红动了②的回答（%r vs %r）" % (before, after)
    assert BROKEN_REL not in homes, "合成件被算进了 LIVE：名册那枚也没资格说它没动"
    assert disk_token() == token, "刀落到了盘上：反证只许摘输入面"
    print("[r589] 丁② 塞一枚解析不了的件：①红着点名它，②读数一字不变（名册 %d 行 = 派生 LIVE %d 枚）"
          % (after["rows"], after["derived"]))


def test_a_missing_roster_row_does_not_move_the_range_gate():
    """丁 下半：名册少一行 ⇒ 只红名册那枚，本件的严格口径在盘上仍绿且仍覆盖整段射程。"""
    sources, roster_text = r583.default_surfaces()
    homes = set(r583.inventory(sources)["live"])
    nine = {rel.replace("/", ".").replace(".py", "") for rel in r583.HISTORICAL_NINE}
    rows = list(r466.WINDOWS)
    victim_key = sorted(str(row["key"]) for row in rows if str(row["test_file"]) not in nine)[0]
    cut = [row for row in rows if str(row["key"]) != victim_key]
    assert len(cut) == len(rows) - 1, "名册里没有 key=%s 这一行" % victim_key
    dropped = str(next(row["test_file"] for row in rows if str(row["key"]) == victim_key))
    with pytest.raises(AssertionError) as caught:
        r583.assert_roster_matches_the_inventory(cut, cut, homes)
    message = str(caught.value)
    assert "没进册" in message, message[:240]
    assert dropped.replace(".", "/") + ".py" in message, message[:240]
    assert "射程内有" not in message, "两枚红共用同一句词：那是缝成一枚断言的形状"
    parsed = surface()
    assert set(parsed) == set(scope()), "名册那一刀动了射程口径"
    overlay.assert_covers_the_range(parsed.keys(), scope(), where="丁 下半的正控")
    print("[r589] 丁② 名册剪掉 key=%s：②红在「没进册」并点名 %s；①一枚未动（射程 %d 枚全在面上）"
          % (victim_key, dropped, len(parsed)))


def test_the_two_verdicts_are_two_bodies_that_neither_calls_the_other():
    """丁 结构那一半：两枚判据不许缝成一枚断言——各是各的本体、互不引用、红字词表不相交。"""
    gate_source = (inspect.getsource(overlay.parse_in_range)
                   + inspect.getsource(overlay.assert_covers_the_range))
    roster_source = inspect.getsource(r583.assert_roster_matches_the_inventory)
    assert "assert_roster_matches_the_inventory" not in gate_source
    assert "WINDOWS" not in gate_source
    assert "parse_in_range" not in roster_source
    assert "assert_covers_the_range" not in roster_source
    assert "射程内有" not in roster_source and "没进册" not in gate_source
    assert overlay.parse_in_range is not r583.assert_roster_matches_the_inventory
    print("[r589] 丁·结构 两枚本体互不引用（①%s 行 / ②%s 行源码），词表不相交"
          % (len(inspect.getsource(overlay.parse_in_range).splitlines()),
             len(roster_source.splitlines())))


# ---------------------------------------------------------------------- 戊·己 全族与新钉自己


def test_no_derivation_in_range_catches_a_parse_failure_and_walks_on():
    """戊 全族扫一遍：射程内派生件里「解析不了就 continue／pass／置 None」一枚不许留。

    起点（``245315b``）现量只有 ``tests/test_r516_...::_all_rows`` 那一处 ``except SyntaxError: continue``，
    本单已把它改走 ``overlay.parse_in_range``；这一格是那族病的常驻反证扫——谁再写回原样就红。
    """
    shapes = _quiet_swallow_shapes(surface())
    assert not shapes, ("这些件把「解析不了」当成「不在射程」（静默缩集）：\n  " + "\n  ".join(shapes))
    print("[r589] 戊 射程 %d 枚里「解析失败还继续走」的形状 0 处" % len(scope()))


def test_a_legal_piece_that_installs_nothing_stays_out_of_the_set():
    """己 判据③第二把刀的常驻形：合法却不该进集的件，一枚在册读数都不许被它挪动。

    弹药开窗（``ShadowEdit`` 子类）却从不往被跟踪文件的活模块上装变异 ⇒ 派生只能把它落进 no_install；
    LIVE 枚数、名册对账读数、射程枚数三格都必须一字不变——那才叫「不得被算进集」。
    """
    sources, roster_text = r583.default_surfaces()
    rows, text_rows = list(r466.WINDOWS), r583.roster_rows_from_text(roster_text)
    before = r583.assert_roster_matches_the_inventory(rows, text_rows, set(r583.inventory(sources)["live"]))
    token = disk_token()
    injected = {rel: value[0] for rel, value in surface().items()}
    injected[QUIET_REL] = _QUIET_SOURCE
    parsed = overlay.parse_in_range(injected)
    _KEEP["injected"] = parsed
    assert QUIET_REL in parsed, "合法合成件没能进输入面：这一格量的就不是「该不该进集」"
    assert QUIET_REL not in set(scope()), "弹药落在盘上了：反证只许摘输入面"
    read = r583.inventory(parsed)
    assert QUIET_REL not in read["live"], sorted(read["live"])
    assert QUIET_REL in read["no_install"], sorted(read["no_install"])
    after = r583.assert_roster_matches_the_inventory(rows, text_rows, set(read["live"]))
    assert after == before, "一枚不该进集的件挪动了名册读数：%r vs %r" % (before, after)
    assert HERE_REL in set(scope()) and HERE_REL not in read["live"], (
        "本件自己在射程内却不开窗：今天这格连自己一起量——LIVE=%s" % (sorted(read["live"]),))
    assert disk_token() == token, "刀落到了盘上：反证只许摘输入面"
    print("[r589] 己 合法不开窗的合成件落 no_install（%d 枚）· LIVE 仍 %d 枚 · 名册对账读数不变 · "
          "本件 %s 自己在射程内也不进集" % (len(read["no_install"]), before["derived"], HERE_REL))
