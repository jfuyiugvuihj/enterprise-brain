# -*- coding: utf-8 -*-
r"""R253：影子根自己得先有牙——判据 ①② 的运行期那一半。

静态那一半在 ``tests/test_r253_no_test_rewrites_a_tracked_file.py``；这一半盯的是「改造之后
那扇门本身」：真开一扇窗、真跑一枚变异的时候，盘上到底有没有被开过写口。

手法：``sys.addaudithook`` 记每一枚 ``open`` 事件的目标与写标志，凡落在 ``git ls-files``
报过的路径上、又带着写标志的，一律算一次事故。审计钩子是进程级、装上不摘，而
``-n 8 --dist loadfile`` 下每枚 worker 各起各的——装在 ``test_r253_*`` 里的钩子看不见更早
跑完的那批件，所以「新长出一处就地改写」必须靠静态扫描闭合，本件只对自己的窗口取证。

五格读数，全部是现量的：
  ① 真反证窗 + 真变异装进 ``app.api.v1.chat``（R572 迁到在册姿势：影子副本落变异 ＋
     ``r466.install_mutation`` 只装变了的那一枚顶层绑定；变异字面仍借 R48 反证③ 前半那一枚）：
     盘上零写口、被跟踪文件 sha 逐字节恒定、影子副本与被跟踪那份确实不同、卡片真带着那格假字段。
     🔴 这一格的牙长在 ``install_mutation`` 那一腿上：``_TempEdit`` 今天 ``execs_module = False``，
     只落影子副本不装活模块，卡片就交不出那格假字段——本件 10-02 起正是红在这一格
     （跟进单 §151 三·症状②，摘掉那一腿的反证见 ``tests/test_r572_the_migrated_window_still_has_teeth.py``）。
  ② 影子根越界就硬拒：``..`` 拼不回仓里，所以「忘还原」这类事故在构造上伤不到盘上。
  ③ 换码不换模块对象：``install_source`` 与 ``importlib.reload`` 同形，旧绑定一起看到新码；
     窗尾按**对象身份**倒回（R572 补）。旧写法窗尾再 exec 一遍盘上的字，而 ``compile`` 会继承
     ``overlay`` 那枚模块的 ``from __future__ import annotations`` ⇒ 装回去的是新对象＋新码体
     （多一枚 CO_FUTURE_ANNOTATIONS），conftest 的在册 R563 守卫比的就是码体，于是同名集全跑里
     本模块收工 ERROR、下一枚撞上 ``app.api.v1.chat`` 的件跟着报同一句话。
  ④ 只给解析器看的那类变异（契约）：盘上恒定，窗内的影子文本确实换了字。
  ⑤ 同一枚被跟踪文件上要开第二扇窗：当场拒。窗内 ``info`` 只有 ``before``，
     ``restored``/``after``/``shadow_clean`` 都是退出时才有的读数。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

import pytest

from app.api.v1 import chat

from tests import _temp_edit_overlay as overlay
from tests.test_r156_sse_event_surface_sync import CONTRACT_PATH, _TempEdit as _R156Edit
from tests.test_r48_headline_card_lands_on_the_wire import (  # noqa: F401  -- 同一条链，不抄第二份
    C1_ANCHOR,
    C1_MUTANT,
    CHAT_PY,
    _chat_window,
    _one_card,
    _reload,
    _TempEdit,
)

REPO = overlay.REPO
CHAT_REL = overlay.rel_of(CHAT_PY)
CONTRACT_REL = overlay.rel_of(CONTRACT_PATH)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
WRITE_MODES = set("wax+")

_events: list = []            # 本进程里「对被跟踪文件开了写口」的每一次现场
_hooked = False


def _tracked() -> frozenset:
    out = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    return frozenset(line.strip().replace("\\", "/") for line in out.stdout.splitlines()
                     if line.strip())


def _as_rel(path):
    if isinstance(path, int):                   # 已经是个 fd，落点早定了
        return None
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return None
    try:
        return os.path.relpath(os.path.abspath(text), str(REPO)).replace("\\", "/")
    except ValueError:                          # Windows 上跨盘符没有相对路径可言
        return None


def install_write_ledger() -> None:
    """装一枚只读的账：谁在被跟踪文件上开写口，就记谁。装第二遍是空操作。"""
    global _hooked
    if _hooked:
        return
    tracked = _tracked()

    def ledger(event, args):
        if event != "open" or not args:
            return
        rel = _as_rel(args[0])
        if rel is None or rel not in tracked:
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        writing = (isinstance(flags, int) and bool(flags & WRITE_FLAGS)) \
            or (isinstance(mode, str) and bool(WRITE_MODES & set(mode)))
        if writing:
            _events.append((rel, mode, flags))

    sys.addaudithook(ledger)
    _hooked = True


def sha256_of(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_live_counter_evidence_window_opens_no_write_on_the_tracked_file(monkeypatch, tmp_path):
    """判据 ①② 的现场：真变异真跑码，而盘上那枚 ``chat.py`` 连一个写口都没挨到。

    R572：窗走 ``_chat_window``（在册姿势，本件不抄第二份开窗器）——影子副本落变异 ＋
    ``r466.install_mutation`` 只把变了的那一枚 ``_headline_card_data`` 装进活模块。下面那格
    ``installed_bindings`` 钉的就是「装的是那一枚绑定，不是整片码体」；少了这一腿，
    ``fabricated_note`` 出不来，本件红在下一格。
    """
    install_write_ledger()
    baseline = len(_events)
    tracked = sha256_of(CHAT_PY)
    with _chat_window([(C1_ANCHOR, C1_MUTANT)]) as info:
        assert sha256_of(CHAT_PY)[:16] == info["before"], "窗里盘上那枚被改过"
        assert sha256_of(CHAT_PY) == tracked, "被跟踪的 chat.py 在窗里被改过"
        assert info.read_bytes() != CHAT_PY.read_bytes(), "影子副本没落下变异：这枚窗口是空的"
        assert overlay.open_windows() == (CHAT_REL,), overlay.open_windows()
        sources = _reload()
        body = sources.drive(monkeypatch, tmp_path,
                             [sources.doc_state(sources.fake_retriever_hits())],
                             sources.finance_principal())
        assert "fabricated_note" in _one_card(body)["data"], "影子字节没被执行：判据 ③ 掉了"
        assert info.get("installed_bindings") == ["_headline_card_data"], (
            "这把刀没只装 `_headline_card_data`（实取 %r）：姿势回退成了整片 exec"
            % (info.get("installed_bindings"),))
        assert _events == _events[:baseline], "对被跟踪文件开过写口：%s" % _events[baseline:]
    assert overlay.open_windows() == (), "窗关了但影子根还记着它"
    assert sha256_of(CHAT_PY) == tracked
    assert info["shadow_clean"], "影子副本没回到盘上的字"
    assert _events == _events[:baseline], _events[baseline:]


def test_the_shadow_root_cannot_reach_a_tracked_file_even_by_hand():
    """判据 ① 的构造性那一格：影子根写不到仓里，所以它连「出事」都出不了。"""
    install_write_ledger()
    baseline = len(_events)
    with pytest.raises(AssertionError) as exc:
        overlay.SHADOW.write("../../r253-escaped.txt", b"x")
    assert "越界" in str(exc.value), str(exc.value)
    assert not (REPO / "r253-escaped.txt").exists()
    assert _events == _events[:baseline], _events[baseline:]


def test_install_source_swaps_the_bytes_not_the_module_object():
    """``importlib.reload`` 也不换模块身份：旧绑定一起看到新码，退出按**对象身份**回原样。

    R572 补的就是窗尾那一手。旧写法是「再 exec 一遍盘上的字」，看着平等、其实不平等：
    ``overlay.install_source`` 里的 ``compile`` 继承调用者（``overlay`` 自己 ``from __future__
    import annotations``）的未来标志，重 exec 回来的顶层函数是新对象**加新码体**——conftest 的
    在册 R563 守卫比的是码体，于是它把这一手判成跨模块的漏：同名集全跑里本模块收工 ERROR，
    下一枚 ``importlib.reload(app.api.v1.chat)`` 的件（``tests/test_phase9_private_deps.py``）
    也报同一句话（跟进单 §151 三·症状③④）。今天窗尾用骨架自己交回的 ``restore_namespace``：
    倒回进门那一刻的那一枚枚对象，不再重跑码体（R553 乙腿同一口径，本件不另造第二套还原）。
    """
    import sys as _sys

    assert chat is _sys.modules["app.api.v1.chat"]
    live_before = dict(chat.__dict__)          # 进门那一刻的活命名空间：窗尾按身份倒回
    original = chat.HEADLINE_SOURCE_LIMIT
    ask_before = chat.ask
    raw = CHAT_PY.read_bytes().decode("utf-8")
    anchor = "HEADLINE_SOURCE_LIMIT = %d" % original
    assert raw.count(anchor) == 1, "锚点不唯一，这格换码是空的：%d 处" % raw.count(anchor)
    overlay.install_source(chat, raw.replace(anchor, anchor + "  # noqa", 1), CHAT_PY)
    assert chat.HEADLINE_SOURCE_LIMIT == original
    assert chat is _sys.modules["app.api.v1.chat"], "换码换掉了模块对象：旧绑定会跑旧码"
    assert getattr(chat, "__r253_probe__", None) is None
    overlay.install_source(chat, raw.replace(anchor, "HEADLINE_SOURCE_LIMIT = 99", 1), CHAT_PY)
    try:
        assert chat.HEADLINE_SOURCE_LIMIT == 99, "exec 没落到模块字典上"
    finally:
        diverged = overlay.restore_namespace(chat, live_before)
    assert chat.HEADLINE_SOURCE_LIMIT == original, (
        "窗尾没把活模块的顶层值装回进门那一刻：R563 会把这一手判成跨模块的漏")
    assert chat.ask is ask_before, (
        "窗尾重 exec 出来的同名函数顶掉了原来那一枚（新对象＋未来标志的新码体）："
        "R563 在册守卫比的是码体，本模块与下一枚撞上 chat 的模块会连着报同一句漏")
    assert "ask" in diverged, "restore_namespace 一声不响：这一手没真在倒回：%s" % (diverged,)
    assert sha256_of(CHAT_PY) == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_a_contract_window_moves_only_the_shadow_text():
    """只给解析器看的那类变异（R156 反证 b）：盘上恒定，窗内的影子副本确实换了字。"""
    install_write_ledger()
    baseline = len(_events)
    tracked = sha256_of(CONTRACT_PATH)
    fake = "zephyr" + ".handoff"
    with _R156Edit(CONTRACT_PATH, "canonical event names are:",
                   "canonical event names are: `%s`," % fake) as info:
        assert fake in info.read_text(), "变异没落到影子副本上"
        assert overlay.open_windows() == (CONTRACT_REL,), overlay.open_windows()
        assert (REPO / "docs" / "api" / "contract-v1.md").read_bytes() == CONTRACT_PATH.read_bytes()
        assert fake not in CONTRACT_PATH.read_bytes().decode("utf-8"), "盘上被写花了"
        assert sha256_of(CONTRACT_PATH) == tracked
        assert _events == _events[:baseline], _events[baseline:]
    assert info["restored"] and info["shadow_clean"], info
    assert sha256_of(CONTRACT_PATH) == tracked


def test_a_stale_line_anchor_reports_the_cell_it_names_not_a_type_error():
    """搬这具骨架时抓到的一枚真缺陷：那行 ``"{} 第 {} 行里有待改的锚" % (...)`` 会炸成 TypeError。

    ``mutate`` 是纯函数，所以这一格零写入：报错原文必须指得到那一格，否则反证挂掉时读者看见的
    是量具异常（``not all arguments converted``）而不是「锚没了」——判据 ③ 要的就是原文能指路。
    """
    edit = _R156Edit(CHAT_PY, "zephyr-anchor-is-not-here", "x", line=3)
    with pytest.raises(AssertionError) as exc:
        edit.mutate("line one\nline two\nline three\n")
    message = str(exc.value)
    assert "第 3 行里没有待改的锚" in message, message
    assert "zephyr-anchor-is-not-here" in message, message


def test_two_windows_on_one_tracked_file_are_refused_before_they_can_collide():
    """影子根每扇窗都从盘上重取基线，所以同文件嵌套在语义上无意义——当场拒，别漏给下一扇。"""
    with _TempEdit(CHAT_PY, [(C1_ANCHOR, C1_MUTANT)]) as first:
        with pytest.raises(AssertionError) as exc:
            with _TempEdit(CHAT_PY, [(C1_ANCHOR, C1_MUTANT)]):
                pass
        assert "不许嵌套" in str(exc.value), str(exc.value)
        assert overlay.open_windows() == (CHAT_REL,), overlay.open_windows()
    assert overlay.open_windows() == ()
    assert first["restored"], first
