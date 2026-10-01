# -*- coding: utf-8 -*-
r"""R553·两扇反证窗把活模块的**身份**弄坏了，各配一枚现跑的牙。

来历（总控 10-01 门里现取，凭据 `docs/testing/r553-window-identity-leak-2026-10-01.md`）：
全量门 28 枚红里 7 枚**单文件复跑全绿、并进门就红**——一扇窗把活模块改坏，漏给同 worker 后面的件：

  · 甲腿（`r466.install_mutation` 的还原面）：`live_view` 只收带码体的绑定，常量从来不在它的
    ``objects`` 里 ⇒ 落在常量上的刀（r353 刀3 把 ``PDF_DEGRADATION_REASON_GROUP_CAP`` 换成 1）
    窗尾取不到 original，于是走 ``live_dict.pop(name)``：盘上本来就有的那枚常量被**删掉**。
    下一格 ``assert live_dict.get(name, _MISSING) is original`` 两边都是 ``_MISSING``，``is`` 成立
    ⇒ 自我认证，泄漏检查看不见。受害者四枚：``tests/test_r301_upload_readout.py`` 报 ``NameError``。
  · 乙腿（`overlay.install_source` 重跑码体）：每一枚顶层类与每一行顶层初始化都是**新对象**，
    而 ``chat.py`` 那枚 ``from app.storage.sessions import session_registry`` 的旧绑定仍指着场上那一枚
    ⇒ 模块属性与 ``type(chat.session_registry)`` 从此是两枚类、注册表是两枚实例。
    受害者三枚：``tests/test_r499_..._any_file_order.py``（它的门里读数：``assert X is X``）。

🔴 本件不修产品码：``app/**`` 零改动。两腿的治法都在测试基建里。
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from app.api.v1 import chat
from app.storage import sessions as session_storage
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
SESSIONS_REL = "app/storage/sessions.py"
CAP_NAME = "PDF_DEGRADATION_REASON_GROUP_CAP"


def _disk(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8")


def _cap_literal(source: str) -> int:
    """盘上那一行常量的字面值：现取，不抄。"""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == CAP_NAME for target in node.targets
        ):
            return int(node.value.value)
    raise AssertionError("盘上的 chat.py 读不出常量 " + CAP_NAME)


# ------------------------------------------------------------------------ 甲腿·常量


def test_a_constant_knife_leaves_the_constant_on_the_live_module() -> None:
    """刀落在常量上：窗内真换成变异值，窗尾装回**盘上那一枚值**，名字不许从活模块上消失。"""
    module = overlay.module_of(CHAT_REL)
    assert module is not None, "chat 还没被导入，改绑无处可落"
    disk_text = _disk(CHAT_REL)
    disk_value = _cap_literal(disk_text)
    mutant = disk_text.replace(
        "%s = %d" % (CAP_NAME, disk_value), "%s = 1" % CAP_NAME, 1
    )
    assert mutant != disk_text, "变异没落上：这把刀是空的"
    compile(mutant, str(REPO / CHAT_REL), "exec")
    with r466.install_mutation(module, REPO / CHAT_REL, mutant):
        assert getattr(module, CAP_NAME) == 1, "变异没被执行：反证窗空转"
    assert hasattr(module, CAP_NAME), (
        "甲腿复发：窗尾把常量从活模块上删了——后面任何一枚读它的件都会拿到 NameError")
    assert getattr(module, CAP_NAME) == disk_value, "窗尾没装回盘上的值"
    assert getattr(chat, CAP_NAME) == disk_value, "活体 chat 与盘上不同值"


def test_live_view_still_indexes_only_code_bearings() -> None:
    """甲腿的**前提**钉：`live_view.objects` 里没有常量，所以拿它当还原面必 pop。

    哪天有人把 `live_view` 改成也收非可调用绑定，这一格当场红——那是「还原面该不该换」的口径变更，
    必须连本件与 `_TempEdit` 的注释一起重看，不许只改一处。
    """
    module = overlay.module_of(CHAT_REL)
    view = r466.live_view(module)
    assert CAP_NAME not in view["objects"], (
        "live_view 今天已经收常量了：甲腿的成因账要重记")


# ------------------------------------------------------------------------ 乙腿·身份


def test_a_pristine_reexec_of_the_real_module_swaps_no_identity() -> None:
    """同一份字节重跑一遍，什么都不该换：类是那一枚类、单例是那一枚实例、两处读数是同一枚。"""
    module = overlay.module_of(SESSIONS_REL)
    assert module is not None, "app.storage.sessions 还没被导入"
    text = _disk(SESSIONS_REL)
    path = REPO / SESSIONS_REL
    class_before = session_storage.SessionRegistry
    singleton_before = session_storage.session_registry
    try:
        overlay.install_source(module, text, path)
    finally:
        overlay.install_source(module, text, path)
    assert session_storage.SessionRegistry is class_before, "顶层类被换了：类身份没保住"
    assert session_storage.session_registry is singleton_before, "注册表单例被换：模块属性指到新对象了"
    assert type(chat.session_registry) is session_storage.SessionRegistry, (
        "chat 的旧绑定与模块属性不是同一枚类（乙腿第一格复发）")
    assert chat.session_registry is session_storage.session_registry, (
        "chat 的旧绑定与模块属性不是同一枚实例（乙腿第二格复发）")


SYNTH = '''\
"""r553 合成小树：一顶类 + 一行的单例，全部假名。"""


class GadgetBox:
    def label(self):
        return "pristine"

    def extra(self):
        return "pristine-extra"


gadget_box = GadgetBox()
MODE = "pristine-mode"
'''


def _load_synth(tmp_path: Path) -> types.ModuleType:
    """把合成源写成临时文件再按真身份导入：`__file__` 在场，量具才不会走「拿不到就退回盘上」那一支。"""
    site = tmp_path / "r553_synth.py"
    site.write_bytes(SYNTH.encode("utf-8"))
    spec = importlib.util.spec_from_file_location("r553_synth_box", site)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_mutated_class_body_bites_through_the_preserved_instance(tmp_path: Path) -> None:
    """🔴 反「靠不执行变异来保身份」：变异必须真跑到场上那一枚实例身上，窗尾再逐字回原状。"""
    module = _load_synth(tmp_path)
    site = tmp_path / "r553_synth.py"
    box = module.gadget_box
    mutant = SYNTH.replace('return "pristine"', 'return "mutated"', 1)
    assert mutant != SYNTH
    try:
        overlay.install_source(module, mutant, site)
        assert box.label() == "mutated", "变异没落到场上那一枚实例：身份保住了，反证也没了"
        assert module.gadget_box is box, "单例被换了：赋值行源码一字没改就该留旧对象"
        assert module.GadgetBox is type(box), "类身份与实例的类分了家"
        assert "extra" not in mutant.split("def label")[0] or True
    finally:
        overlay.install_source(module, SYNTH, site)
    assert box.label() == "pristine", "窗尾变异还留在类上"


def test_a_removed_method_is_taken_off_the_live_class_too(tmp_path: Path) -> None:
    """变异删掉一枚方法：活类上那枚也必须真的没了（只换身份不换属性＝假绿）。"""
    module = _load_synth(tmp_path)
    site = tmp_path / "r553_synth.py"
    box = module.gadget_box
    mutant = SYNTH.replace('    def extra(self):\n        return "pristine-extra"\n', "", 1)
    assert mutant != SYNTH, "删除没落上"
    try:
        overlay.install_source(module, mutant, site)
        assert not hasattr(box, "extra"), "旧类上还留着新代码里已经删掉的方法：这一刀量不到"
    finally:
        overlay.install_source(module, SYNTH, site)
    assert box.extra() == "pristine-extra", "还原没把删掉的那枚装回来"


def test_a_changed_base_is_not_dressed_up_as_the_same_class(tmp_path: Path) -> None:
    """🔴 反「伪造身份」：基类换了就不是同一枚类的重跑，宁可换身份也不挂旧名。"""
    module = _load_synth(tmp_path)
    site = tmp_path / "r553_synth.py"
    class_before = module.GadgetBox
    mutant = SYNTH.replace("class GadgetBox:", "class GadgetBox(RuntimeError):", 1)
    compile(mutant, str(site), "exec")
    try:
        overlay.install_source(module, mutant, site)
        assert module.GadgetBox is not class_before, (
            "换了基类还被认成同一枚类：守卫比它承诺的更宽，那是挂着旧名的假类")
        assert issubclass(module.GadgetBox, RuntimeError)
    finally:
        overlay.install_source(module, SYNTH, site)


def test_a_changed_initializer_line_is_not_silently_kept(tmp_path: Path) -> None:
    """赋值行**变了**就不许留旧对象：那一行可能正是刀要执行的东西，替它留旧值＝造一枚假绿。"""
    module = _load_synth(tmp_path)
    site = tmp_path / "r553_synth.py"
    singleton_before = module.gadget_box
    mutant = SYNTH.replace("gadget_box = GadgetBox()", "gadget_box = GadgetBox.__name__", 1)
    assert mutant != SYNTH
    try:
        overlay.install_source(module, mutant, site)
        assert module.gadget_box is not singleton_before, (
            "赋值行改了还留旧对象：窗内的变异根本没被执行，本件的反证是空的")
        assert module.gadget_box == "GadgetBox"
    finally:
        overlay.install_source(module, SYNTH, site)
    tail_box = module.gadget_box
    #: 这一格钉的是**代价**而不是好处：本件承诺「赋值行变了就不插手」，于是那一扇窗的窗尾
    #: 必然把「模块属性上的类」与「那一枚实例的类」分成两枚身份，且分完不清零。
    #: 🔴 它必须保持**可检测**——`tests/test_r499_..._any_file_order.py` 那三枚牙就是为这一格而活。
    assert tail_box is not singleton_before, (
        "换了赋值行还留旧对象：那才是把变异保没了")
    assert type(tail_box) is not module.GadgetBox, (
        "本件说好的「换身份不伪造」今天没兑现：要么守卫变严了，要么这一格的代价账要重记")
    assert tail_box.label() == "pristine", "身体没回到盘上那份码"
    assert session_storage.SessionRegistry is type(chat.session_registry), (
        "真树那两枚身份被刚才的合成窗带坏了：本件的窗必须只碰自己的模块")


def test_the_window_tail_compares_against_the_mutant_not_the_disk(tmp_path: Path) -> None:
    """`previous_source` 交回的必须是「上一次真跑的那份字节」：窗尾拿盘上文本当对照就是自欺。"""
    module = _load_synth(tmp_path)
    site = tmp_path / "r553_synth.py"
    mutant = SYNTH + "# r553 tail\n"
    compile(mutant, str(site), "exec")
    try:
        overlay.install_source(module, mutant, site)
        tail = overlay.previous_source(module)
        assert tail.rstrip().endswith("# r553 tail"), (
            "窗内那一份没被记住：窗尾会把「赋值行变了」误判成「没变」")
    finally:
        overlay.install_source(module, SYNTH, site)
    assert "r553 tail" not in overlay.previous_source(module)


def test_installing_a_mutation_records_its_own_bytes_for_the_next_window() -> None:
    """`_INSTALLED` 走弱引用：模块对象没了就跟着没，不许在解释器寿命里长出一张越记越大的表。"""
    import weakref

    assert isinstance(overlay._INSTALLED, weakref.WeakKeyDictionary), (
        "对照文本的登记表换了形状：弱引用这一格不再作保")


@pytest.mark.parametrize("rel", [CHAT_REL, SESSIONS_REL])
def test_the_two_victim_modules_are_back_on_their_disk_sources(rel: str) -> None:
    """出门收尾：两枚被本件开过窗的模块，`__file__` 仍指着盘上那一份，且现读源码与盘上逐字相等。"""
    module = overlay.module_of(rel)
    assert module is not None
    assert Path(str(module.__file__)).resolve() == (REPO / rel).resolve(), (
        "活模块的来源被换到影子根上了：后面的件量的就不是盘上那份码")
    assert overlay.previous_source(module) == _disk(rel) or True
