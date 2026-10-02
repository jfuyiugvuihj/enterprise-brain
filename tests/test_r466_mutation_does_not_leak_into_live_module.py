# -*- coding: utf-8 -*-
r"""R466：反证窗的变异不许漏在活模块上（共用姿势件 + 跨件牙）。

病根（本席 d824b10 现取）：``tests/`` 里有 9 枚反证钉把 ``execs_module = True``——开窗那一刻
``ShadowEdit.__enter__`` 会把**变异后的整份码体** exec 进 ``sys.modules`` 里那枚活模块的
``__dict__``。基类 ``__exit__`` 确实会把盘上的字 exec 回去，但那句「会漏」不是空话：

  · exec 发生在 ``__enter__`` 里、``_WINDOWS.append`` 之后。变异体在顶层就跑炸（装饰器实参、
    模块级表达式），``__enter__`` 抛出 -> ``with`` 的 ``__exit__`` 根本不执行 -> 活模块留下半份
    变异码，而 ``_WINDOWS`` 也记着这扇窗：``overlay.authoritative_text()`` 从此把影子副本的变异
    当成「当前该算数的那份字节」交回给每一枚读源码的钉子。那是假绿，且没有复原路径。
  · 即使一切顺利，``__exit__`` 的「复原」是**再 exec 一遍模块体**：本席现量的读数是活模块里
    chat 134 枚、data 19 枚、notifications 8 枚、sources 9 枚、inbox 7 枚顶层把手**逐枚换成新对象**
    （身份全换），而且每一枚的 ``co_flags`` 都比开窗前多一枚 ``CO_FUTURE_ANNOTATIONS`` bit。
    ``tests/test_r457_audit_retention_execution_leg.py:225-230`` 记的同族：R425 那本在册钉
    ``from app.scheduler.jobs import offpeak_rebuild_window`` 拿的是旧身体，同 worker 里跑在
    本件之后就红 5 枚。今天不炸只是 ``--dist loadfile`` 的侥幸。

正例姿势在 ``tests/test_r457_audit_retention_execution_leg.py:169-242``：变异只落临时目录那份
影子副本（``execs_module = False``），要跑变异就把它装进一枚隔离对象，窗尾逐枚对照活把手没被换过。
本件把那条姿势做成可复用的把手 ``install_mutation``：只把**改动的那几枚顶层绑定**临时装进活模块
的名字空间（其余每一枚函数对象连身份都不动），出门在 ``finally`` 里逐枚装回去；那几枚变异函数体的
``__globals__`` 直接挂在活模块字典上，所以窗内才装的夹具替身照样看得见——这一格比 r457 的
「整份 exec 进隔离字典」更贴本仓这几枚件的跑法（r310/r337 在窗内 ``_rebind`` 装世界）。

判据③ 的牙在下面：顺序跑「A 件开反证窗」->「B 件读同一枚活函数」，B 必须读到原始码；
再故意造一枚会漏变异的形状（``LeakyEdit``：出门不还原）证明这枚牙认得出。

R553 第二版（10-01）改了基类的还原姿势，本件跟着改**一处口径**，没有放松任何一格。
``_temp_edit_overlay.ShadowEdit.__exit__`` 不再把盘上的字重 exec 一遍，而是把命名空间倒回进门那一刻
的快照 ⇒ 唯一还走「进门 exec 整份码体」那条路的 r48，出窗后**不再换身份**了。它原来那格
``len(identity_diff(before, after)) == len(before["objects"])`` 量的正是「码体被重跑过」这件事本身，
10-01 它红了，红的是登记，不是泄漏。于是 r48 的在册姿势改名 ``live_exec_snapshot``，出窗这一侧九枚
同判（码体与身份都倒回开窗前，另加下面那格「点名的那几枚必须回到盘上那份码」——旧口径只有 r48 一支
有这条，八枚影子窗一辈子没被量过），再留两格降级哨：``execs_module`` 仍须为真、窗内「整片换身份」
那格原样不动，谁把这枚窗悄悄降级成影子改绑，本件当场红。

同一版还订正一枚**尺子的编法**（与上面同因：都是拿盘上那份码当尺子时才会撞上）。本件文件头写着
``from __future__ import annotations``，而 ``compiled_view`` 走不带 ``dont_inherit`` 的 plain
``compile()``，那一位 future 会顺着调用帧掺进字节码（3.12+ 的 ``__annotate__`` 子码体跟着变形状）
⇒ 拿它量「导入机器编出来的那份」时，10-01 现取 chat 139/139、data 19/19 枚整片假差；只把
``co_flags`` 摘掉仍剩 4 枚真差（``_authorize_queue_task`` / ``_reap_agent_worker`` / ``approve`` /
``delete_document``）。所以凡「盘上那份码」当尺子的那两格一律 ``dont_inherit=True``；窗内比影子副本
那两格不动（``install_source`` 也是继承帧的编法，两边同形）。

R556（10-01 第十一班）把最后那几扇旧姿势窗也迁进本口径：``execs_module is True`` 的在册名单由
``["r48"]`` 缩到 ``[]``——r472 两扇、r478、r495、r48 从今天起都只装「变了的那几枚顶层绑定」，
落在顶层类上的那一族由本件新加的类支接住。名册钉随之按新事实改口（``only_r48_still_execs`` →
``none_of_them_execs_the_live_module``），并留一枚「名单反弹即红」的牙。
🔴 盘上另有两枚 exec 窗不在本单写域、今天仍登记在案：
``tests/test_r482_registered_ceiling_is_the_ceiling.py::_ClampEdit``（越界不迁，坐标交回）与
``tests/test_r553_counter_evidence_teeth.py::_Probe``（它量的就是 exec 姿势本身，迁了就没牙了）；
逐枚读数见 ``docs/testing/r556-window-posture-migration-2026-10-01.md`` 与新钉
``tests/test_r556_window_posture_is_installed_not_executed.py``。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
from types import CodeType, FunctionType

import pytest

from tests import _temp_edit_overlay as overlay

__all__ = [
    "install_mutation",
    "changed_bindings",
    "live_view",
    "diff_view",
    "SELF_PROOF_SHAPES",
]

_MISSING = object()


# ------------------------------------------------------------------ 姿势件（8 枚 unsafe 件调用这里）


def _top_level_bindings(text: str) -> dict:
    """顶层绑定名 -> 源码（``ast.unparse``）：盘上的字与影子副本逐名一比就知道改了谁。"""
    out: dict[str, str] = {}
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = ast.unparse(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.unparse(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = ast.unparse(node)
    return out


def changed_bindings(disk_text: str, mutant_text: str) -> tuple:
    """(改了哪些顶层绑定名, 只改到非绑定语句时的说明) —— 变异必须有名字可挂。"""
    disk, mutant = _top_level_bindings(disk_text), _top_level_bindings(mutant_text)
    names = sorted(set(disk) | set(mutant))
    changed = [name for name in names if disk.get(name) != mutant.get(name)]
    if changed:
        return changed, ()
    other_disk = [ast.unparse(node) for node in ast.parse(disk_text).body
                  if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                           ast.Assign, ast.AnnAssign))]
    other_mutant = [ast.unparse(node) for node in ast.parse(mutant_text).body
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                             ast.Assign, ast.AnnAssign))]
    return [], tuple(zip(other_disk, other_mutant))


def _rebase(value, live_dict: dict, name: str):
    """把变异函数体挂回**活模块的名字空间**：码体是变异的，命名空间仍是盘上那一枚模块的。"""
    if isinstance(value, FunctionType) and value.__closure__ is None:
        return FunctionType(value.__code__, live_dict, value.__name__, value.__defaults__, None)
    if isinstance(value, type):
        raise AssertionError(
            "R466 的自动改绑只覆盖顶层函数与常量，这枚变异落在类 %s 上：得手工处理" % name)
    return value


def _top_level_class_names(text: str) -> set:
    """那份字节里的顶层**类名**。install_mutation 原本对它们设计性拒绝（``_rebase`` 明写
    「得手工处理」）；R556 把这格补进姿势件——补的是同一族口径（只碰点名的那几枚绑定），
    不是在 test 件里另抄一套第二实现。
    """
    return {node.name for node in ast.parse(text).body if isinstance(node, ast.ClassDef)}


def _top_level_class_statement(text: str, name: str) -> str:
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError("影子副本里没有顶层类 %s 的定义：这一枚绑定不该走类那一支" % name)


@contextlib.contextmanager
def install_mutation(module, path, mutant_text: str) -> dict:
    """把影子副本里改动的那几枚顶层绑定临时装进活模块，出门逐枚还原并核对每一枚把手没被换过。

    🔴 不重跑整份模块体：``overlay.install_source`` 会把码体 exec 进 ``module.__dict__``，于是
    每一枚顶层函数都换成新身体、导入期那层壳也被 plain 编译顶掉。这里只碰变了的那几枚名字。

    R556 补上顶层**类**那一支：变异落在类体里时（r478 的 ``description=`` 在 Pydantic 模型类里、
    r495 的归属判定在 ``SessionRegistry.is_owned_by`` 里），过去 ``_rebase`` 一句「得手工处理」把这格
    推给调用方；今天这一支把那一枚类语句在**活命名空间**里现编一遍——方法体的 ``__globals__`` 仍是
    这一枚模块的字典，窗内 monkeypatch 装的夹具替身照样看得见。出窗仍按进门那一刻的值逐枚装回，
    没点名的绑定一枚都不动。
    """
    disk_text = path.read_bytes().decode("utf-8")
    names, unmatched = changed_bindings(disk_text, mutant_text)
    assert names, (
        "影子副本的变异没落到任何一枚顶层绑定上（改动只出现在非绑定语句里）："
        "这把刀无法被执行，反证就是空的：%r" % (unmatched[:1],)
    )
    before_view = live_view(module)
    live_dict = vars(module)
    #: 🔴 R553 甲腿：`live_view` 只收「带码体的那几枚」（顶层函数与类的方法），**常量与非可调用绑定
    #: 从来不在它的 `objects` 里**。刀落在常量上时（r353 刀3 把 `CAP = 10` 换成 `CAP = 1`），窗尾从
    #: `before_view["objects"]` 取不到 original，于是走 `live_dict.pop(name)`——把盘上本来就有的那枚
    #: 常量整个从活模块上删了；而下一格 `assert live_dict.get(name, _MISSING) is original` 两边都是
    #: `_MISSING`，`is` 成立 ⇒ 自我认证，泄漏检查看不见。还原面因此必须直接看 `live_dict`：
    #: 窗内不在场上的名字才允许 pop，本来在场上的一律装回窗那一枚对象。
    before_values = {name: (live_dict[name] if name in live_dict else _MISSING) for name in names}
    #: R556：落在**顶层类**上的变异走单独一支——类语句必须在活命名空间里现编一遍，否则它每一枚方法
    #: 体的 ``__globals__`` 停在那份一次性字典上，窗内由 monkeypatch 装进去的夹具替身它一枚都看不见。
    #: 没点名的名字照旧一枚都不碰，出窗仍按 before_values 逐枚装回。
    disk_classes = _top_level_class_names(disk_text)
    mutant_classes = _top_level_class_names(mutant_text)
    class_names = [n for n in names if n in mutant_classes or n in disk_classes]
    plain_names = [n for n in names if n not in class_names]
    scratch = dict(live_dict)
    exec(compile(mutant_text, str(path), "exec"), scratch)   # 只进这份一次性字典
    installed = {}
    try:
        for name in plain_names:
            assert name in scratch, "变异里的 %s 没在影子副本里绑上名字" % name
            installed[name] = _rebase(scratch[name], live_dict, name)
            setattr(module, name, installed[name])
        for name in class_names:
            if name not in mutant_classes:
                continue   # 变异把这枚类整个摘掉了：exec 整片码体的旧姿势同样不会删名字，照旧留场上
            exec(compile(_top_level_class_statement(mutant_text, name), str(path), "exec"), live_dict)
            installed[name] = live_dict[name]
        yield installed
    finally:
        for name in names:
            original = before_values[name]
            if original is _MISSING:
                live_dict.pop(name, None)
            else:
                live_dict[name] = original
            assert live_dict.get(name, _MISSING) is original, (
                "窗尾 %s.%s 没装回窗内那一枚对象：变异漏在活模块上了" % (module.__name__, name))
        back = live_view(module)
        leaked = sorted(key for key in names if back["codes"].get(key) != before_view["codes"].get(key))
        assert not leaked, (
            "窗尾 %s 的 %s 还在跑变异码体：反证窗不许把变异留在活模块上"
            % (module.__name__, ", ".join(leaked)))


# ------------------------------------------------------------------------ 跨件牙的尺子


def _digest_code(code: CodeType) -> str:
    h = hashlib.sha256()
    parts = [
        "qualname:" + getattr(code, "co_qualname", code.co_name),
        "lineno:" + str(code.co_firstlineno),
        "flags:" + str(code.co_flags),
        "names:" + repr(code.co_names),
        "varnames:" + repr(code.co_varnames),
        "exceptiontable:" + code.co_exceptiontable.hex(),
        "bytecode:" + code.co_code.hex(),
        "consts:" + "|".join(_const_token(item) for item in code.co_consts),
    ]
    h.update("\n".join(parts).encode("utf-8", "replace"))
    return h.hexdigest()[:12]


def _const_token(value) -> str:
    if isinstance(value, CodeType):
        return "code(" + _digest_code(value) + ")"
    if isinstance(value, (str, bytes, int, float, complex, bool, type(None))):
        return repr(value)
    if isinstance(value, (tuple, frozenset)):
        return "seq[" + ",".join(_const_token(item) for item in value) + "]"
    return "opaque:" + type(value).__name__


def _codes_in(code: CodeType):
    yield code
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _codes_in(const)


def compiled_view(text: str, filename: str, dont_inherit: bool = False) -> dict:
    """把一份字节编成码体树，交回 限定名 -> 指纹：全程不 exec，装饰器掺不进来。

    ``dont_inherit=True`` 是要拿这份字节去量**导入机器编出来的那份**时用（模块 docstring 末段）；
    默认沿旧形继承调用帧的 future flags，窗内比影子副本那两格靠的就是这一份同形。
    """
    out = {}
    for code in _codes_in(compile(text, filename, "exec", 0, dont_inherit)):
        out[getattr(code, "co_qualname", code.co_name)] = _digest_code(code)
    return out


def fn_digest(value) -> str:
    """一枚活函数现在跑的码体指纹：B 件读同一枚活函数就读这个，不读 inspect（它跟着盘走）。"""
    code = getattr(value, "__code__", None)
    assert isinstance(code, CodeType), "要的是一枚函数，实取 %r" % (type(value).__name__,)
    return _digest_code(code)


def live_view(module) -> dict:
    """活模块现在跑的码：顶层函数与顶层类的方法，各自的身份与码体指纹。"""
    codes, objects = {}, {}
    for name, value in list(vars(module).items()):
        candidates = [value]
        if isinstance(value, type):
            candidates = [getattr(vars(value)[m], "__func__", vars(value)[m])
                          for m in sorted(vars(value))]
        for item in candidates:
            code = getattr(item, "__code__", None)
            if not isinstance(code, CodeType):
                continue
            if getattr(item, "__module__", None) != module.__name__:
                continue
            if getattr(item, "__wrapped__", None) is not None:
                continue          # 装饰器换过身体的：不由本尺子作保
            qualname = getattr(item, "__qualname__", name)
            codes[qualname] = _digest_code(code)
            objects[qualname] = item
    return {"codes": codes, "objects": objects}


def diff_view(a: dict, b: dict) -> list:
    """两份 live_view 的差：返回「码体变了」的名字；不含只换身份的那一层。"""
    keys = set(a["codes"]) & set(b["codes"])
    return sorted(name for name in keys if a["codes"][name] != b["codes"][name])


def codes_differ(a: dict, b: dict) -> list:
    # 两份 {限定名: 码体指纹} 的差集：拿盘上那份码当尺子量活模块时用这一枚。
    KEYS = set(a) & set(b)
    return sorted(name for name in KEYS if a[name] != b[name])


def identity_diff(a: dict, b: dict) -> list:
    keys = set(a["objects"]) & set(b["objects"])
    return sorted(name for name in keys if a["objects"][name] is not b["objects"][name])
# ---------------------------------------------------------------------- 在册的 9 扇反证窗

# 每扇窗都用**那一件自己的**开窗把手与它自己登记的锚点：本件不抄第二份变异。


def _open_r303(m):
    return m._mutate(m.NOTIFICATIONS_PY, m._BATCH_GATE_ANCHOR, m._BATCH_GATE_MUTANT), m.NOTIFICATIONS_PY


def _open_r310(m):
    return m._window([(m.OWNER_LINE, m.OWNER_LINE_REMOVED)]), m.DATA_PY


def _open_r337(m):
    return m._window(m.NO_OWNER_ON_EITHER_EXIT), m.DATA_PY


def _open_r353(m):
    return m._window([(m.SLICE_ANCHOR, m.SLICE_REMOVED)]), m.CHAT_PY


def _open_r354(m):
    return m._window([(m.DELIVERED_READ, m.BASE_READ)]), m.DATA_PY


def _open_r373(m):
    return m._mutate(m.SOURCES_PY, m.KNIFE_ONE_OLD, m.KNIFE_ONE_NEW), m.SOURCES_PY


def _open_r381(m):
    return m._mutate(m.OUTLET_PY, m.KNIFE_ONE), m.OUTLET_PY


def _open_r388(m):
    return m._mutate(m.INBOX_PY, m.COUNT_ANCHOR, m.COUNT_MUTANT), m.INBOX_PY


def _open_r48(m):
    """R556：这扇窗在册登记的是「影子改绑 + 只装变了的那几枚绑定」，开窗器必须是件自己
    那枚 `_chat_window`——裸 `_TempEdit` 在今天只落影子根、不碰活模块，拿它当窗会读成空转刀。"""
    return m._chat_window([(m.C1_ANCHOR, m.C1_MUTANT)]), m.CHAT_PY


#: 判据① 那张表的机器可读形态。posture 与 verdict 都是本席 d824b10 现取的读数，不是派工词里的旧账。
WINDOWS = (
    {"key": "r303", "test_file": "tests.test_r303_notification_pins",
     "target": "app.api.v1.notifications", "edit": "_R303Edit", "opener": _open_r303,
     "verdict": "有 finally（只还原 rebind 的消费者把手）·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r310", "test_file": "tests.test_r310_owner_lookup_cost",
     "target": "app.api.v1.data", "edit": "_R310Edit", "opener": _open_r310,
     "verdict": "窗体只有 with ... as info: yield —— 什么都没做·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r337", "test_file": "tests.test_r337_owner_receipt_cost_and_knives",
     "target": "app.api.v1.data", "edit": "_R337Edit", "opener": _open_r337,
     "verdict": "窗体只有 with ... as info: yield —— 什么都没做·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r353", "test_file": "tests.test_r353_degradation_note_caps_reason_classes",
     "target": "app.api.v1.chat", "edit": "_R353Edit", "opener": _open_r353,
     "verdict": "窗体只有 with ... as info: yield —— 什么都没做·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r354", "test_file": "tests.test_r354_delete_audit_shares_the_owner_reader",
     "target": "app.api.v1.data", "edit": "_R354Edit", "opener": _open_r354,
     "verdict": "窗体只有 with ... as info: yield —— 什么都没做·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r373", "test_file": "tests.test_r373_the_two_remaining_legs_answer_absence",
     "target": "app.notifications.sources", "edit": "_R373Edit", "opener": _open_r373,
     "verdict": "有 finally（只还原 rebind 的消费者把手）·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r381", "test_file": "tests.test_r381_outlet_answers_the_absent_approval_ledger",
     "target": "app.api.v1.notifications", "edit": "_R381Edit", "opener": _open_r381,
     "verdict": "窗体只有 with ... as info: yield —— 什么都没做·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r388", "test_file": "tests.test_r388_read_leg_answers_absence",
     "target": "app.notifications.inbox", "edit": "_R388Edit", "opener": _open_r388,
     "verdict": "有 finally（只还原 rebind 的消费者把手）·会漏·本单已改影子改绑",
     "posture": "shadow_swap"},
    {"key": "r48", "test_file": "tests.test_r48_headline_card_lands_on_the_wire",
     "target": "app.api.v1.chat", "edit": "_TempEdit", "opener": _open_r48,
     "verdict": "R556 已迁 install_mutation：进门只把变了的那几枚顶层绑定（`_headline_card_data`）"
                "装进活模块，出窗逐枚装回；它自己那枚 finally 里的 `_reload()` 从此只重载夹具，"
                "不再 exec 盘上的字（判据⑤ 归真）。契约那两把刀改的是 .md，module_of 只可能交 None。",
     "posture": "shadow_swap"},
)


def _row_handles(row):
    """把这扇窗的把手取齐：件、它的 ShadowEdit 子类、开窗器、被改文件、活模块。"""
    module = importlib.import_module(row["test_file"])
    edit_cls = getattr(module, row["edit"])
    assert issubclass(edit_cls, overlay.ShadowEdit), row["edit"] + " 不是影子窗的子类"
    window, path = row["opener"](module)
    target = importlib.import_module(row["target"])
    assert overlay.module_of(overlay.rel_of(path)) is target, (
        "%s 的窗改的不是 %s：本件的把手写错了" % (row["key"], row["target"]))
    return module, edit_cls, window, path, target


#: 判据③ 的第二半：故意造一枚会漏变异的形状，证明这枚牙认得出（不是 not.toMatch 那种空话）。
SELF_PROOF_SHAPES = ("leaky_install_source_no_restore",)


def _leak_install_source_no_restore():
    """造一枚会把变异漏在活模块上的形状：装进去，然后**不还原**。

    这就是 8 枚件旧姿势最坏的那一格——``ShadowEdit.__enter__`` 在 ``_WINDOWS.append`` 之后 exec
    变异码体，那一次 exec 一抛（语法过不了、或顶层副作用炸了），``with`` 的 ``__exit__`` 就轮不到，
    活模块留着半份变异码，``_WINDOWS`` 也还记着这扇窗。这里用真锚点真码体演它的后果。
    """
    sibling = importlib.import_module("tests.test_r373_the_two_remaining_legs_answer_absence")
    path = sibling.SOURCES_PY
    target = importlib.import_module("app.notifications.sources")
    disk_text = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in disk_text else "\n"
    old = newline.join(tuple(sibling.KNIFE_ONE_OLD))
    new = newline.join(tuple(sibling.KNIFE_ONE_NEW))
    assert disk_text.count(old) == 1, "自证的锚点在盘上的字里不唯一：%d 处" % disk_text.count(old)
    mutated = disk_text.replace(old, new, 1)
    compile(mutated, str(path), "exec")
    return {
        "path": path,
        "target": target,
        "disk_text": disk_text,
        "mutated": mutated,
        "leaked": "approval_candidates",
        # ← 故意漏：把变异装进活模块，外面没有配对的还原
        "apply": lambda: overlay.install_source(target, mutated, path),
    }


_SELF_PROOFS = {"leaky_install_source_no_restore": _leak_install_source_no_restore}


# ------------------------------------------------------------------------------- 用例


def test_the_roster_is_nine_windows_and_none_of_them_execs_the_live_module():
    """R466 的九扇在册 + R556 的名单清空：`execs_module is True` 这一族今天必须是空集。

    用例名里那句 ``only_r48_still_execs`` 是 R466 的账面；R556 把最后一扇（r48）也迁进
    ``install_mutation`` 之后它就成了假话——在册钉按新事实改口，名字跟着事实走，不许留一枚
    写着旧账的名字。🔴 这一格同时就是「反弹即红」那枚牙：谁再把任何一扇在册窗开成
    ``execs_module = True``，或把它登记成旧姿势的 posture，``still_execs`` / 那两格立刻非空。
    """
    keys = sorted(row["key"] for row in WINDOWS)
    assert keys == sorted(["r303", "r310", "r337", "r353", "r354", "r373", "r381", "r388", "r48"]), keys
    still_execs = sorted(
        row["key"] for row in WINDOWS if _row_handles(row)[1].execs_module is True)
    assert still_execs == [], (
        "R556 之后九扇一律影子改绑 + install_mutation：名单不许反弹（还开着 execs_module 的：%s）"
        % (still_execs,))
    not_swap = sorted(row["key"] for row in WINDOWS if row["posture"] != "shadow_swap")
    assert not_swap == [], (
        "登记表里又出现旧姿势的行列（%s）：R556 之后 posture 只准写 shadow_swap" % (not_swap,))
    mismatched = sorted(
        row["key"] for row in WINDOWS
        if (row["posture"] == "shadow_swap") is not (_row_handles(row)[1].execs_module is False))
    assert mismatched == [], (
        "在册姿势与 execs_module 读数不一致：有人在名单里登记了旧姿势（%s）" % (mismatched,))


@pytest.mark.parametrize("row", WINDOWS, ids=[row["key"] for row in WINDOWS])
def test_a_refutation_window_leaves_no_mutation_on_the_live_module(row):
    """判据③ 的正脸：A 件开反证窗 -> B 件读同一枚活函数，B 必须读到原始码。

    尺子是码体指纹与对象身份，不是 inspect/linecache —— install_source 把 co_filename 沿用成
    被跟踪文件的路径，窗内用 getsource 去读，读到的一直是盘上的字：那枚「尺」量不到正在跑的码。
    """
    module, edit_cls, window, path, target = _row_handles(row)
    rel = overlay.rel_of(path)
    disk_text = path.read_bytes().decode("utf-8")
    disk_codes = compiled_view(disk_text, str(path))
    before = live_view(target)
    assert before["codes"], "%s 的活模块没有可读的顶层把手：这枚牙是空的" % row["key"]

    with window as info:
        shadow_text = info.read_text()
        shadow_codes = compiled_view(shadow_text, str(path))
        swapped = changed_bindings(disk_text, shadow_text)[0]
        assert swapped, "%s 这扇窗的变异没落到任何顶层绑定上：反证是空的" % row["key"]
        assert any(shadow_codes[name] != disk_codes[name] for name in swapped), (
            "%s 的影子副本码体与盘上逐字相同：锚点空转" % row["key"])
        assert overlay.open_windows() == (rel,), overlay.open_windows()
        inside = live_view(target)
        if row["posture"] == "shadow_swap":
            assert set(diff_view(before, inside)) <= set(swapped), (
                "%s 窗内活模块的码体在没点名的名字上也变了：变异 exec 进了整份码体（%s）"
                % (row["key"], sorted(set(diff_view(before, inside)) - set(swapped))))
            # 判据② 的强度格：影子改绑不是「什么都没装」——窗内必须真在跑影子副本那份码。
            # 只断「没多出别的变化」会把一把空转的刀读成绿，所以这里点名比对每一枚改动的绑定。
            const_comparable = [name for name in swapped
                                if name in inside["codes"] and name in shadow_codes]
            assert const_comparable, (
                "%s 窗内没有一枚改动的顶层绑定的码体可比对：这枚牙量不到变异" % row["key"])
            for name in const_comparable:
                assert inside["codes"][name] == shadow_codes[name], (
                    "%s 窗内 %s 跑的不是影子副本那份码：变异没被执行，反证是空的" % (
                        row["key"], name))
            assert diff_view(before, inside), (
                "%s 窗内活模块的码体一处都没变：影子改绑空转" % row["key"])
        else:
            # 只登记的那一枚：旧姿势在这里确实把整份码体 exec 进活模块——这正是病根的形状。
            assert len(identity_diff(before, inside)) == len(before["objects"]), (
                "%s 登记的形状失效：这扇窗今天不再换掉每一枚顶层把手，本件的口径要改写" % row["key"])
            for name in swapped:
                assert inside["codes"].get(name) == shadow_codes.get(name), (
                    "%s 窗内那枚 %s 不是影子副本的码体：exec 没落到模块字典上" % (row["key"], name))
            assert diff_view(before, inside), row["key"] + " 窗内活模块码体没变"

    after = live_view(target)
    assert overlay.open_windows() == (), "出窗没关干净：%s" % (overlay.open_windows(),)
    assert info["restored"] is True
    # --------------------------------------------------------------- 出窗这一侧：九枚同判
    # R553 之后基类的窗尾是「把命名空间倒回进门那一刻」，两族姿势在这一侧形状相同，
    # 而且都比旧口径严：旧的那一支只拿盘上那份码比，从没查过对象身份。
    assert diff_view(before, after) == [], (
        "%s 出窗后还在跑变异码体：漏在活模块上的名字 %s" % (row["key"], diff_view(before, after)))
    assert identity_diff(before, after) == [], (
        "%s 出窗后顶层把手没回到开窗前那一枚：模块体被重跑过（%s）"
        % (row["key"], identity_diff(before, after)[:4]))
    # 上面两格都是「相对开窗前」的：快照本身若更早地沾了变异，它照样绿。下面这格把尺子换成盘上那份码，
    # 只量本扇窗点名的那几枚绑定——逐枚比整片会把别枚件在导入期合法换过的把手读成假红。
    disk_as_imported = compiled_view(disk_text, str(path), dont_inherit=True)
    shadow_as_imported = compiled_view(shadow_text, str(path), dont_inherit=True)
    visible = [name for name in swapped if name in after["codes"]
               and disk_as_imported.get(name) != shadow_as_imported.get(name)]
    assert visible, (
        "%s 点名的顶层绑定里一枚都没有「盘上 vs 影子」可读的差：这格漏变异检是空的（%s）"
        % (row["key"], swapped[:3]))
    stuck = codes_differ({key: after["codes"][key] for key in visible},
                         {key: disk_as_imported[key] for key in visible})
    assert not stuck, (
        "%s 出窗后点名的这几枚没回到盘上那份码：%s" % (row["key"], stuck[:3]))
    if row["posture"] != "shadow_swap":
        # 降级哨（判据④ 刀一的第二颗牙）：上面三格对影子改绑同样成立，所以谁把这扇窗悄悄改成
        # execs_module = False，三格不会响——响的是这一格，外加窗内「整片换身份」那一格。
        assert edit_cls.execs_module is True, (
            "%s 在册姿势是 %s，可它已经不再往活模块上 exec 整份码体：姿势被降级，本件口径要改写"
            % (row["key"], row["posture"]))

@pytest.mark.parametrize("shape", SELF_PROOF_SHAPES)
def test_the_ruler_reddens_on_a_shape_that_leaves_its_mutation(shape):
    """判据③ 的第二半（自证）：故意造一枚会把变异漏在活模块上的形状，这枚牙必须当场认出。

    这里不写「断言非空」那种空话：认出的名字要能对上变异码体的指纹，且现场收得回来——
    摘掉自证本体（让它不再往活模块上装变异）会让本枚红，摘掉登记会让下面那枚红。
    """
    builder = _SELF_PROOFS.get(shape)
    assert callable(builder), shape + " 的自证把手被摘掉了"
    scene = builder()
    disk_text, path, target = scene["disk_text"], scene["path"], scene["target"]
    leaked_name = scene["leaked"]
    before = live_view(target)
    assert leaked_name in before["codes"], "自证要盯的那枚函数不在活模块上：%s" % (leaked_name,)

    snapshot = dict(vars(target))           # R553：收场按这张快照倒回，见 finally 那段的说明
    scene["apply"]()
    try:
        dirty = live_view(target)
        leaked = diff_view(before, dirty)
        assert leaked_name in leaked, (
            shape + " 把变异漏在活模块上了，这枚牙却没认出来（实取 %s）" % (leaked,))
        shadow_codes = compiled_view(scene["mutated"], str(path))
        assert dirty["codes"][leaked_name] == shadow_codes[leaked_name], (
            shape + " 认出的名字对不上变异那份码体：这枚牙在瞎指")
        assert disk_text != scene["mutated"]
    finally:
        # 收拾现场：本件也不许污染同一枚 worker。🔴 这里原本走的是「把盘上的字再 exec 一遍」，
        # 那一手只救码不救身份——install_source 造出第二枚 sources.alert_candidates，而消费者
        # app.notifications.inbox 手里那枚还是旧的，同 worker 里排在后面的
        # tests/test_r303_notification_pins.py::test_the_counter_evidence_window_touches_no_tracked_file
        # 当场红（10-01 现取：HEAD 上把这两枚件放进同一个进程必红，门里不炸只是 --dist loadfile 的侥幸，
        # 与 R553 乙腿同一族形状）。改成按进门那一刻的命名空间快照倒回。
        overlay.restore_namespace(target, snapshot)
    assert diff_view(before, live_view(target)) == [], "自证收场没把活模块交回去：本件自己也在漏"
    assert identity_diff(before, live_view(target)) == [], (
        "自证收场把活模块的身份换过了：还原只到码、没到身份，消费者手里的旧绑定就此与生产者分家")


def test_the_self_proof_is_registered_and_not_stripped():
    """判据④ 刀二：把 ③ 那枚自证摘掉，这枚登记必须红（登记与实证两格分开放）。"""
    assert len(SELF_PROOF_SHAPES) == 1, SELF_PROOF_SHAPES
    assert set(SELF_PROOF_SHAPES) == set(_SELF_PROOFS), "自证清单与把手对不上：有人摘了一格"
    for shape in SELF_PROOF_SHAPES:
        assert callable(_SELF_PROOFS[shape]), shape + " 的自证把手不是可调用的"
        assert _SELF_PROOFS[shape]().__len__() >= 5, shape + " 的自证场景缺件"


def test_the_swap_refuses_a_mutation_that_moves_nothing():
    """姿势件不许把「空变异」当成还原成功：影子副本与盘上逐字相同时必须硬拒。"""
    row = next(item for item in WINDOWS if item["key"] == "r310")
    module, edit_cls, window, path, target = _row_handles(row)
    disk_text = path.read_bytes().decode("utf-8")
    before = live_view(target)
    with pytest.raises(AssertionError) as caught:
        with install_mutation(target, path, disk_text):
            pass
    assert "顶层绑定" in str(caught.value), str(caught.value)
    assert diff_view(before, live_view(target)) == []
    assert identity_diff(before, live_view(target)) == []