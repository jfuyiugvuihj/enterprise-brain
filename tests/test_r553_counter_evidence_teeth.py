# -*- coding: utf-8 -*-
r"""R553·两扇反证窗把活模块的**身份**弄坏了，各配一枚现跑的牙（第二版·治法＝窗尾按快照倒回）。

凭据 `docs/testing/r553-window-identity-leak-2026-10-01.md`。一句话账：
一扇 `execs_module = True` 的反证窗，进门把变异字节 exec 进活模块，窗尾**又 exec 一遍盘上的字**——
那一手救不回任何东西：码体重跑会再造每一枚顶层类与每一行顶层初始化，于是模块属性上的
`SessionRegistry` 与 `type(chat.session_registry)` 分成两枚类、注册表分成两枚实例，
门里三枚红报的是 ``assert X is X`` 却为假（`tests/test_r499_..._any_file_order.py`）。
本件钉的是：**窗尾不再重跑码体，而是把命名空间倒回进门那一刻的快照**。

🔴 另一条本席亲自踩过、写进来当护栏：不许改成「把新身体逐枚装进旧类」——零参 `super()` 读的是码体里
那枚 `__class__` 格，把新类的方法定进旧类，第一次 `super()` 就 `TypeError: super(type, obj):
obj must be an instance or subtype of type`（第一版这么改，把门从 28 枚红跑成 109 枚红，
`test_r253_shadow_root_holds_the_mutation`／`test_r508_the_bind_stub_stays_on_the_class` 当场点名）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.api.v1 import chat
from app.storage import sessions as session_storage
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
SESSIONS_REL = "app/storage/sessions.py"
SESSIONS_SITE = REPO / "app" / "storage" / "sessions.py"
CAP_NAME = "PDF_DEGRADATION_REASON_GROUP_CAP"
NAMESPACE_NAME = "SESSION_OWNER_NAMESPACE"


def _disk(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8")


def _cap_literal(source: str) -> int:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == CAP_NAME for target in node.targets
        ):
            return int(node.value.value)
    raise AssertionError("盘上的 chat.py 读不出常量 " + CAP_NAME)


class _Probe(overlay.ShadowEdit):
    """本件自己的探针窗：变异只落影子副本，窗内真 exec 进活模块。"""

    tag = "r553"
    execs_module = True

    def __init__(self, path, needle: str, replacement: str) -> None:
        super().__init__(path)
        self.needle = needle
        self.replacement = replacement

    def mutate(self, text: str) -> str:
        assert text.count(self.needle) == 1, "锚点在盘上命中不是恰好一枚：这把刀不落"
        edited = text.replace(self.needle, self.replacement, 1)
        compile(edited, str(self.path), "exec")
        return edited


def _live_identities(module) -> dict:
    return {name: value for name, value in vars(module).items()}


# ------------------------------------------------------------------------ 乙腿·身份


def test_a_window_leaves_every_live_identity_intact() -> None:
    """一扇窗开完：活模块上**每一枚名字都得是原来那一枚对象**，值也要回到盘上那份。"""
    module = overlay.module_of(SESSIONS_REL)
    assert module is not None, "app.storage.sessions 还没被导入，探针无处可落"
    pristine = _live_identities(module)
    registry = chat.session_registry
    needle = '%s = "username"' % NAMESPACE_NAME
    with _Probe(SESSIONS_SITE, needle, '%s = "r553-probe"' % NAMESPACE_NAME):
        assert getattr(module, NAMESPACE_NAME) == "r553-probe", "变异没被执行：这扇窗是空转的"
    now = _live_identities(module)
    assert now.get(NAMESPACE_NAME) == "username", "窗尾没把值倒回盘上那份"
    drifted = sorted(name for name, value in pristine.items()
                     if name in now and now[name] is not value)
    assert not drifted, "窗尾之后这些名字换了对象（乙腿复发）：" + ", ".join(drifted)
    assert session_storage.SessionRegistry is pristine["SessionRegistry"], "顶层类被换了"
    assert type(registry) is session_storage.SessionRegistry, (
        "`chat` 手里的注册表与模块属性上的类不是同一枚类")
    assert chat.session_registry is session_storage.session_registry is registry, (
        "注册表单例被换：两处读数不是同一枚对象")


def test_the_window_tail_reexecutes_nothing() -> None:
    """机制钉：整扇窗只许 exec **一次**（进门那次），窗尾一次都不许。"""
    module = overlay.module_of(SESSIONS_REL)
    calls = []
    real = overlay.install_source

    def counting(target, text, filename):
        calls.append(str(filename))
        return real(target, text, filename)

    overlay.install_source = counting
    try:
        with _Probe(SESSIONS_SITE, '%s = "username"' % NAMESPACE_NAME,
                    '%s = "r553-probe"' % NAMESPACE_NAME):
            pass
    finally:
        overlay.install_source = real
    assert len(calls) == 1, (
        "窗尾又 exec 了一遍（旧口径）：那正是再造顶层类与顶层实例的那一手，calls=%r" % (calls,))


def test_names_invented_by_the_mutant_do_not_survive_the_window() -> None:
    """变异码体在顶层新造的名字必须随窗一起没：留在活模块上就是漏给后面那枚件的影子。"""
    module = overlay.module_of(SESSIONS_REL)
    needle = '%s = "username"' % NAMESPACE_NAME
    invented = "%s = \"username\"\nR553_INVENTED = \"shadow leftover\"" % NAMESPACE_NAME
    with _Probe(SESSIONS_SITE, needle, invented):
        assert getattr(module, "R553_INVENTED", None) == "shadow leftover"
    assert not hasattr(module, "R553_INVENTED"), (
        "变异新造的名字活在窗外的活模块上了：旧口径（窗尾 exec 盘上的字）就救不掉这一格")


def test_a_crashed_window_still_hands_the_module_back_untouched() -> None:
    """窗内抛异常也要倒回：`__exit__` 走的是同一张快照，不许把变异留在场上。"""
    module = overlay.module_of(SESSIONS_REL)
    pristine = _live_identities(module)
    with pytest.raises(RuntimeError):
        with _Probe(SESSIONS_SITE, '%s = "username"' % NAMESPACE_NAME,
                    '%s = "r553-probe"' % NAMESPACE_NAME):
            raise RuntimeError("r553 窗内故意炸")
    now = _live_identities(module)
    assert now.get(NAMESPACE_NAME) == "username", "窗内出事，变异漏在了活模块上"
    assert [n for n, v in pristine.items() if now.get(n) is not v] == []


# ------------------------------------------------------------------------ 甲腿·常量


def test_a_constant_knife_leaves_the_constant_on_the_live_module() -> None:
    """`install_mutation` 的还原面不许把常量 pop 掉（受害者：`test_r301_upload_readout` 四枚 `NameError`）。"""
    module = overlay.module_of(CHAT_REL)
    assert module is not None, "chat 还没被导入，改绑无处可落"
    disk_text = _disk(CHAT_REL)
    disk_value = _cap_literal(disk_text)
    mutant = disk_text.replace("%s = %d" % (CAP_NAME, disk_value), "%s = 1" % CAP_NAME, 1)
    assert mutant != disk_text, "变异没落上：这把刀是空的"
    compile(mutant, str(REPO / CHAT_REL), "exec")
    with r466.install_mutation(module, REPO / CHAT_REL, mutant):
        assert getattr(module, CAP_NAME) == 1, "变异没被执行：反证窗空转"
    assert hasattr(module, CAP_NAME), (
        "甲腿复发：窗尾把常量从活模块上删了——后面任何一枚读它的件都会拿到 NameError")
    assert getattr(chat, CAP_NAME) == disk_value, "窗尾没装回盘上的值"


def test_live_view_still_indexes_only_code_bearings() -> None:
    """甲腿的**前提**钉：`live_view.objects` 里没有常量，所以拿它当还原面必 pop。

    哪天有人把 `live_view` 改成也收非可调用绑定，这一格当场红——那是口径变更，
    必须连 `install_mutation` 的注释与本件一起重看，不许只改一处。
    """
    view = r466.live_view(overlay.module_of(CHAT_REL))
    assert CAP_NAME not in view["objects"], "live_view 今天已经收常量了：甲腿的成因账要重记"


# ------------------------------------------------------------------------ 收尾


def test_the_two_victim_modules_still_point_at_their_disk_sources() -> None:
    """本件开过窗之后：两枚受害模块的来源仍是盘上那份，`__file__` 没被带去影子根。"""
    for rel in (CHAT_REL, SESSIONS_REL):
        module = overlay.module_of(rel)
        assert module is not None
        assert Path(str(module.__file__)).resolve() == (REPO / rel).resolve(), (
            "活模块的来源被换到影子根上了：后面的件量的就不是盘上那份码")
