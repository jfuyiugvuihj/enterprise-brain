# -*- coding: utf-8 -*-
r"""R584·`__defaults__` 那一腿换成结构尺：合法 reload 不再被冤枉，牙还在。

病（改前三枚现取读数，全记录见 `docs/testing/r584-defaults-leg-2026-10-03.md`）：
`tests/conftest.py` 的在册 R563 守卫拿四腿判"同一枚函数"，第四腿原来写的是
`getattr(a, "__defaults__", None) == getattr(b, "__defaults__", None)`。FastAPI 的 `File()`／
`Form()` 继承 pydantic `FieldInfo`，而 `FieldInfo.__eq__ is object.__eq__`（本席现取 True）⇒
`importlib.reload` 把默认值重造一遍之后，码体逐字节相同的**合法还原**也被判成漂移。
最小复现（改前）：`tests/test_r48_headline_card_lands_on_the_wire.py` ＋
`tests/test_phase9_private_deps.py` 合跑 ⇒ `21 passed, 1 error`，红的名字只有
`app.api.v1.chat.upload_document` 一枚；同模块其余 165 枚顶层函数零漂移。

正证钉（甲–子）：
  甲 对症正证：照 phase9 原样 reload chat＋alerts ⇒ 在册守卫不红。
  乙 换值：`Form(1)`→同一枚形只把 `default` 换成 `2`（码体走 reload 那种"同字节不同对象"）⇒ 点名。
  丙 换型：`File(...)`→`Form(...)`，而且**借同一枚码体对象**造人（旧尺在这一支直接免检）⇒ 点名。
  丁 少一位：默认值元组短一枚 ⇒ 点名。
  戊 语义位不是装饰：只翻 `embed` 一位，两枚的 repr 逐字节相同 ⇒ 点名。
  己 病案在进程内复现：把改前那把身份尺装回守卫 ⇒ 同一次合法 reload 必须重新红。
  庚 尺子形状：`_eb_r563_same` 两支都得走 `_eb_r563_defaults_same`，且不许再裸比 `__defaults__`。
  辛 R563 原意没被洗白：reload 之后真留一份假身（名字同、默认值同，只有身体换了）⇒ 仍红在凶手身上。
  壬 函数型默认值（`default_factory` 那一族）按码体判：同体重造算还原，换身体算漂移。
  癸 结构回退不白送：`object()` 那一族的 repr 里带内存地址，两枚不同实例必须仍判不同。
  子 口径钉：值化 repr 又没有 `__eq__` 的类按结构算同一枚值——这是本单选定的口径，写死在此。

反证刀（K1–K4，victim 全为本件在册钉；摘法一律进程内影子，盘上一字节都不动）：
  K1 把 `_eb_r563_defaults_same` 整条换成恒等 ⇒ 乙／丙／丁／戊 四枚钉一起红（尺被锯了）。
  K2 造真漏（`File(...)`→`Form(...)`）⇒ 真尺点名该函数；同一枚漏交给 K1 那把瞎尺 ⇒ 不红。
  K3 摘掉 `co_code` 那一腿 ⇒ 辛 必须红 ⇒ 证辛不空咬，码体腿没被本单迁成摆设。
  K4 把 `FieldInfo` 的语义位清单清空 ⇒ 戊 必须红 ⇒ 证那一层真在判，不是装饰。

靶子为什么一律用 `_twin` 而不是新造一枚 `File()/Form()`：路由注册时 FastAPI 会**就地改写**
默认值实例的 `annotation`（本席现取：`upload_document.__defaults__[0].annotation` 是
`UploadFile`，而现场新造的 `File(...)` 是 `None`），所以新造的那枚会连 `annotation` 一起偏——
刀要只偏点名那一位，否则咬住了也是冤枉。
"""
import ast
import copy
import hashlib
import io
import pathlib
import sys
import types

import pytest

from app.api.v1 import chat

REPO = pathlib.Path(__file__).resolve().parents[1]
CONFTEST = REPO / "tests" / "conftest.py"
CHAT_NAME = "app.api.v1.chat"
#: 病案里唯一被冤枉的那一枚顶层函数（改前漂移名单就只有它）。
TARGET = "upload_document"
GUARD_MESSAGE = "R563"
#: 每把刀都逐字节核这几枚文件的 sha256：摘的只是进程内的名字与活命名空间。
WATCHED = (
    "tests/conftest.py",
    "tests/test_phase9_private_deps.py",
    "tests/test_r563_live_module_callables_do_not_leak.py",
    "tests/test_r466_mutation_does_not_leak_into_live_module.py",
    "app/api/v1/chat.py",
    "tests/test_r584_the_defaults_leg_compares_structure_not_identity.py",
)


def digests():
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in WATCHED}


class _Node:
    """conftest 的 R563 守卫只读 `request.nodeid`——手工驱动时的最小替身。"""

    nodeid = "tests/test_r584_the_defaults_leg_compares_structure_not_identity.py"


def _drive(guard):
    """开一版在册守卫：返回 setup 已跑完的生成器，`next` 到底就是"没红"。"""
    gen = guard.body(_Node())
    next(gen)
    return gen


def _close(gen):
    """收守卫的工：红就交回消息，没红交回 None。"""
    try:
        next(gen)
    except StopIteration:
        return None
    except BaseException as caught:      # pytest.fail 抛 Failed，坐在 BaseException 支系上
        return "%s: %s" % (type(caught).__name__, caught)
    return None


def _hand_back(module, snapshot):
    """刀自己的收尾：把活命名空间倒回进门那一刻（在册守卫只还顶层函数，其余自己还）。"""
    live = module.__dict__
    for key in [name for name in list(live) if name not in snapshot]:
        live.pop(key, None)
    live.update(snapshot)


def _namespace(guard):
    """守卫真正在用的那本命名空间（conftest 的模块字典）：反证只许在这里动手。"""
    return guard.body.__globals__


def _ruler(guard):
    """动态取"同一枚函数"那把尺：换了影子尺它必须跟着换，否则反证是空咬。"""
    return _namespace(guard)["_eb_r563_same"]


def _shadow_code(module, name=TARGET):
    """reload 之后的码体形状：逐字节相同，但不是同一枚对象。"""
    code = getattr(module, name).__code__
    shadow = code.replace(co_filename="<r584-shadow>")
    assert shadow is not code and shadow.co_code == code.co_code, "影子码体没造出来"
    return shadow


def _reforge(function):
    """把一枚函数重造成"同一枚身体、另一枚对象"（壬用它演 reload）。"""
    code = function.__code__.replace(co_filename="<r584-shadow>")
    return types.FunctionType(code, function.__globals__, function.__name__,
                              function.__defaults__, function.__closure__)


def _rebase(module, defaults, code=None, name=TARGET):
    """借体造人：同名同身体（或另造一枚同字节码体），只换默认值的那一枚函数。"""
    original = getattr(module, name)
    assert original.__defaults__ is not None, "病案前提：这枚顶层函数得带默认值"
    argdefs = None if defaults is None else tuple(defaults)
    return types.FunctionType(code or original.__code__, module.__dict__, name,
                              argdefs, original.__closure__)


def _defaults(module=chat, name=TARGET):
    return list(getattr(module, name).__defaults__)


def _twin(instance, **overrides):
    """一枚与原件逐位相同的克隆，只改 overrides 点名的那一位。

    新造 `File()/Form()` 会把 `annotation` 也换掉（路由注册就地改写过原件），靶子就不纯了。
    """
    clone = copy.copy(instance)
    assert type(clone) is type(instance), (type(clone), type(instance))
    for key, value in overrides.items():
        setattr(clone, key, value)
    return clone


def _leak_value(module=chat):
    """乙：只把 `Form(1)` 的 `default` 换成 `2`；码体走 reload 那种"同字节不同对象"。"""
    base = _defaults(module)
    assert base[1].default == 1, base[1].default
    poisoned = list(base)
    poisoned[1] = _twin(base[1], default=2)
    return _rebase(module, poisoned, code=_shadow_code(module))


def _leak_type(module=chat):
    """丙／K2：`File(...)`→`Form(...)`，而且**借同一枚码体对象**造人（旧尺在这一支免检）。"""
    from fastapi.params import Form

    base = _defaults(module)
    poisoned = list(base)
    poisoned[0] = Form(...)
    assert type(poisoned[0]) is not type(base[0]), "换型没换成：这一把刀无从落下"
    return _rebase(module, poisoned)


def _leak_length(module=chat):
    """丁：默认值元组少一位（形状变化不许被结构比较吞掉）。"""
    return _rebase(module, _defaults(module)[:-1], code=_shadow_code(module))


def _leak_embed(module=chat):
    """戊：只翻 `embed` 一位。两枚的 repr 逐字节相同 ⇒ 只有语义位认得出。"""
    base = _defaults(module)
    poisoned = list(base)
    poisoned[0] = _twin(base[0], embed=True)
    assert repr(poisoned[0]) == repr(base[0]), (repr(poisoned[0]), repr(base[0]))
    assert poisoned[0].embed is True and base[0].embed is not True
    return _rebase(module, poisoned, code=_shadow_code(module))


def _impostor(module=chat, name=TARGET):
    """辛／K3 的靶子：名字与默认值都照真身复刻，只留"身体换了"这一条证据。

    这就是 R563 当年那一族（`record_audit = 一枚假定参数形状的本地函数`）的形状。
    """
    original = getattr(module, name)

    def _fake_body(*args, **kwargs):
        return {"r584": "假身，没人还原"}

    code = _fake_body.__code__.replace(co_name=name, co_qualname=name)
    return types.FunctionType(code, module.__dict__, name, original.__defaults__, None)


def _drift_lines(message):
    return [line for line in (message or "").splitlines() if line.strip().startswith("- ")]


def _leak_and_close(guard, leaked, name=TARGET, module=chat):
    """基线先收（真身还在的时候），再把 leaked 装进活模块收一次工：交回红消息或 None。"""
    live_before = dict(module.__dict__)
    gen = _drive(guard)
    module.__dict__[name] = leaked
    try:
        return _close(gen)
    finally:
        _hand_back(module, live_before)


def _assert_named(message, name=TARGET):
    assert message is not None, (
        "守卫一声不响：这一手没被认出来——尺上少了在判的那一条腿（锯腿＝本单没做完）")
    assert GUARD_MESSAGE in message, message[:200]
    assert "%s.%s" % (CHAT_NAME, name) in message, message[:500]
    drift = _drift_lines(message)
    assert len(drift) == 1, "漂移名单不只有该点名的那一枚：%s" % drift
    return message


def _phase9_run(monkeypatch):
    """照 `tests/test_phase9_private_deps.py` 那枚在册用例原样跑一次：本件不改它一个字节。"""
    import tests.test_phase9_private_deps as phase9

    phase9.TestOptionalPsycopgImports().test_chat_and_alerts_import_without_psycopg(monkeypatch)


def _reload_and_close(guard, setup):
    """基线先收，跑一次合法 reload，再收守卫的工；收尾一律把活模块还回去。"""
    names = (CHAT_NAME, "app.api.v1.alerts")
    watched = [sys.modules[name] for name in names if name in sys.modules]
    snapshots = [dict(module.__dict__) for module in watched]
    gen = _drive(guard)
    try:
        setup()
        return _close(gen)
    finally:
        for module, snapshot in zip(watched, snapshots):
            _hand_back(module, snapshot)


def test_jia_the_phase9_reload_is_restoration_not_drift(eb_r563_guard, monkeypatch):
    """甲（对症正证）：phase9 那枚 reload 收工不再红——全量门今天唯一那枚红就是它。"""
    before = digests()
    original = chat.upload_document
    message = _reload_and_close(eb_r563_guard, lambda: _phase9_run(monkeypatch))
    assert message is None, "合法 reload 仍被判成漏（守卫还在冤枉还原窗）：" + str(message)[:400]
    assert chat.upload_document is original, "收尾没把活模块还回真身：下一枚件要替本件挨打"
    assert digests() == before, "正控写脏了被跟踪文件"
    print("[r584] 甲：phase9 原样 reload ⇒ 在册守卫 0 漂移（改前：红在 %s.%s）"
          % (CHAT_NAME, TARGET))


def test_yi_a_changed_default_value_is_still_named(eb_r563_guard):
    """乙：`default` 换了人是漂移，不是还原 ⇒ 必须点名。"""
    before = digests()
    message = _assert_named(_leak_and_close(eb_r563_guard, _leak_value()))
    print("[r584] 乙 点名原文：%s" % _drift_lines(message)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def test_bing_a_changed_default_type_is_still_named_on_a_shared_code_object(eb_r563_guard):
    """丙：借**同一枚码体对象**造的人（`ca is cb` 那一支）也得把默认值比完——旧尺在这支免检。"""
    before = digests()
    leaked = _leak_type()
    assert leaked.__code__ is chat.upload_document.__code__, "丙的前提：码体必须是同一枚对象"
    message = _assert_named(_leak_and_close(eb_r563_guard, leaked))
    print("[r584] 丙 点名原文：%s" % _drift_lines(message)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def test_ding_a_shorter_defaults_tuple_is_still_named(eb_r563_guard):
    """丁：形状变化（少一位）不许被结构比较吞掉。"""
    before = digests()
    message = _assert_named(_leak_and_close(eb_r563_guard, _leak_length()))
    print("[r584] 丁 点名原文：%s" % _drift_lines(message)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def test_wu_an_embed_bit_is_named_though_the_repr_is_identical(eb_r563_guard):
    """戊：`File(...)` 与 `File(embed=True)` 的 repr 逐字节相同 ⇒ 语义位这一层必须在判。"""
    before = digests()
    message = _assert_named(_leak_and_close(eb_r563_guard, _leak_embed()))
    print("[r584] 戊 点名原文：%s" % _drift_lines(message)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def _old_identity_ruler(a, b):
    """改前第四腿的口径：拿 `==` 直接比两枚 `__defaults__` 实例（本件自造的旧尺，非盘上活物）。

    故意留在本件里，只为件事：己能用它在进程内把病案复现出来。盘上那把真尺不许退回这个口径
    ——退回的那一刻己就不红了，而乙／丙／丁／戊 会集体失配。
    """
    if a is b:
        return True
    ca, cb = getattr(a, "__code__", None), getattr(b, "__code__", None)
    if ca is None or cb is None or ca is cb:
        return ca is cb
    return (
        ca.co_name == cb.co_name
        and ca.co_qualname == cb.co_qualname
        and ca.co_code == cb.co_code
        and getattr(a, "__defaults__", None) == getattr(b, "__defaults__", None)
    )


def test_ji_the_old_identity_ruler_reddens_the_same_reload(eb_r563_guard, monkeypatch):
    """己：把旧身份尺装回守卫 ⇒ 同一次合法 reload 必须重新红在 `upload_document` 上。

    这条钉的是"本单治的就是那一枚口径"：旧尺一回来病症原样复发，新尺在位时病症消失且牙还在。
    """
    before = digests()
    monkeypatch.setitem(_namespace(eb_r563_guard), "_eb_r563_same", _old_identity_ruler)
    message = _reload_and_close(eb_r563_guard, lambda: _phase9_run(monkeypatch))
    assert message is not None, "旧尺咬不动 reload：己复现的不是本单治的那枚病"
    assert GUARD_MESSAGE in message, message[:200]
    assert "%s.%s" % (CHAT_NAME, TARGET) in message, message[:500]
    assert digests() == before, "反证写脏了被跟踪文件"
    print("[r584] 己 病案复现原文：%s" % _drift_lines(message)[0].strip())


def test_geng_the_ruler_wires_the_defaults_leg_into_both_branches():
    """庚：`_eb_r563_same` 两支都得走 `_eb_r563_defaults_same`，且不许再裸比 `__defaults__`。"""
    tree = ast.parse(io.open(CONFTEST, encoding="utf-8").read())
    fn = next(node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "_eb_r563_same")
    callees = [node.func.id for node in ast.walk(fn)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert callees.count("_eb_r563_defaults_same") >= 2, (
        "`__defaults__` 那一腿只剩一支在判：另一支被写成免检就是锯腿 %s" % callees)
    compares = [ast.unparse(node) for node in ast.walk(fn) if isinstance(node, ast.Compare)]
    offenders = [text for text in compares if "__defaults__" in text]
    assert offenders == [], "又拿裸比较直接比两枚 `__defaults__` 实例：%s" % offenders
    assert any("cb.co_code" in text for text in compares), "码体那一腿被摘了：%s" % compares


def test_xin_a_fake_body_behind_a_reload_still_reddens_its_owner(eb_r563_guard, monkeypatch):
    """辛＝判据 3 的 K3：reload 之后真留一份假身（名字同、默认值同，只有身体换了）⇒ 仍红。

    这一条证的正是"R563 的原意没被本单洗白"：结构尺放过的只有同码体的合法还原。
    """
    before = digests()
    live_before = dict(chat.__dict__)
    gen = _drive(eb_r563_guard)                        # 基线＝真身还在的那一刻
    try:
        _phase9_run(monkeypatch)                       # 合法 reload：这一步不该红（甲已钉）
        chat.__dict__[TARGET] = _impostor()            # 摘掉还原：真留假身
        message = _assert_named(_close(gen))
    finally:
        _hand_back(chat, live_before)
    assert chat.upload_document is live_before[TARGET], "收尾没把活模块还回真身"
    print("[r584] 辛 点名原文：%s" % _drift_lines(message)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def test_ren_a_function_valued_default_is_judged_by_its_body(eb_r563_guard):
    """壬：`default_factory` 那一族按码体判——同体重造算还原，换身体算漂移。"""
    before = digests()
    ruler = _ruler(eb_r563_guard)

    def factory():
        return 1

    def other():
        return 2

    base = _defaults()
    code = _shadow_code(chat)
    left = list(base)
    left[0] = factory
    rebuilt = list(base)
    rebuilt[0] = _reforge(factory)                     # 同一枚身体，另一枚对象
    changed = list(base)
    changed[0] = other
    assert factory is not _reforge(factory)
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, rebuilt, code=code)) is True, \
        "同身体的函数型默认值被当成漂移：reload 那一族又会多一枚冤枉"
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, changed, code=code)) is False, \
        "换了身体的函数型默认值被判成同一枚值：壬这一族没了牙"
    assert digests() == before, "正控写脏了被跟踪文件"


def test_gui_an_address_bearing_repr_is_not_a_free_pass(eb_r563_guard):
    """癸：结构回退不许白送——`object()` 那一族的 repr 里带着内存地址。"""
    before = digests()
    ruler = _ruler(eb_r563_guard)
    base = _defaults()
    code = _shadow_code(chat)
    left = list(base)
    left[0] = object()
    right = list(base)
    right[0] = object()
    assert " at 0x" in repr(left[0]) and " at 0x" in repr(right[0])
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, right, code=code)) is False, \
        "两枚不同实例的带地址 repr 被判成同一枚值：结构回退白送了身份"
    identical = list(base)
    identical[0] = left[0]
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, identical, code=code)) is True, \
        "同一枚实例反而判不等：癸的正控失配"
    assert digests() == before, "正控写脏了被跟踪文件"


def test_zi_a_value_rendered_class_without_eq_is_a_deliberate_pass(eb_r563_guard):
    """子（口径钉）：值化 repr 又没有 `__eq__` 的类按结构算同一枚值——这是本单选定的口径。

    写死在这里：改窄（退回身份比较，phase9 那枚红就会复发）或改宽（连语义位都不看，戊就会失配）
    都必须红在本钉上，不许下一班拿"顺手收紧"把它改掉。
    """
    before = digests()
    ruler = _ruler(eb_r563_guard)
    base = _defaults()
    code = _shadow_code(chat)
    left = list(base)
    left[0] = types.SimpleNamespace(mark="r584")
    right = list(base)
    right[0] = types.SimpleNamespace(mark="r584")
    assert left[0] is not right[0] and repr(left[0]) == repr(right[0])
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, right, code=code)) is True, \
        "值化 repr 且无 __eq__ 的类被改窄成身份比较了：phase9 那一族红会复发"
    worse = list(base)
    worse[0] = types.SimpleNamespace(mark="other")
    assert ruler(_rebase(chat, left, code=code), _rebase(chat, worse, code=code)) is False, \
        "值不同的两枚 SimpleNamespace 被判成同一枚值：结构口径自己失效了"
    assert digests() == before, "正控写脏了被跟踪文件"


def _blind_the_defaults_leg(guard, monkeypatch):
    """K1／K2 的摘法：把 `_eb_r563_defaults_same` 整条换成恒等（进程内；盘上一字节不动）。"""
    namespace = _namespace(guard)
    assert "_eb_r563_defaults_same" in namespace, "找不到那一腿的判据本体：摘法要重配"
    monkeypatch.setitem(namespace, "_eb_r563_defaults_same", lambda da, db: True)


def test_k1_stripping_the_defaults_leg_blinds_all_four_leak_pins(eb_r563_guard, monkeypatch):
    """K1：那一腿整条摘掉 ⇒ 乙／丙／丁／戊 四枚钉一起红（守卫再也认不出换了的默认值）。"""
    before = digests()
    victims = (
        test_yi_a_changed_default_value_is_still_named,
        test_bing_a_changed_default_type_is_still_named_on_a_shared_code_object,
        test_ding_a_shorter_defaults_tuple_is_still_named,
        test_wu_an_embed_bit_is_named_though_the_repr_is_identical,
    )
    _blind_the_defaults_leg(eb_r563_guard, monkeypatch)
    reddened = []
    for victim in victims:
        with pytest.raises(AssertionError) as caught:
            victim(eb_r563_guard)
        reddened.append("%s :: %s" % (victim.__name__, str(caught.value).splitlines()[0][:70]))
    assert len(reddened) == len(victims), reddened
    print("[r584] K1 摘腿后红的 victim：\n  " + "\n  ".join(reddened))
    assert digests() == before, "反证写脏了被跟踪文件"


def test_k2_a_real_defaults_leak_is_named_only_when_the_leg_is_in_place(eb_r563_guard, monkeypatch):
    """K2：同一枚真漏（`File(...)`→`Form(...)`）交给真尺与瞎尺 ⇒ 真尺点名，瞎尺漏判。"""
    before = digests()
    first = _assert_named(_leak_and_close(eb_r563_guard, _leak_type()))
    _blind_the_defaults_leg(eb_r563_guard, monkeypatch)
    slipped = _leak_and_close(eb_r563_guard, _leak_type())
    assert slipped is None, (
        "摘掉那一腿之后仍然咬得住：K2 的瞎尺没瞎，本单的牙没长在 defaults 这一腿上")
    print("[r584] K2 真尺点名：%s ｜ 瞎尺读数：0 漂移（该枚漏不再红）"
          % _drift_lines(first)[0].strip())
    assert digests() == before, "反证写脏了被跟踪文件"


def _blind_the_code_leg(guard, monkeypatch):
    """K3 的摘法：把 `_eb_r563_same` 里 `co_code` 那一腿换成恒真（进程内文本影子，不落盘）。"""
    namespace = _namespace(guard)
    text = io.open(CONFTEST, encoding="utf-8").read()
    tree = ast.parse(text)
    fn = next(node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "_eb_r563_same")
    source = ast.get_source_segment(text, fn)
    assert source and "ca.co_code == cb.co_code" in source, "码体那一腿的字形变了：摘法要重配"
    shadow = source.replace("ca.co_code == cb.co_code", "True")
    scope = dict(namespace)
    exec(compile(shadow, "<r584-k3-shadow>", "exec"), scope)  # noqa: S102 - 进程内影子
    monkeypatch.setitem(namespace, "_eb_r563_same", scope["_eb_r563_same"])


def test_k3_stripping_the_code_leg_blinds_the_fake_body_pin(eb_r563_guard, monkeypatch):
    """K3：摘掉 `co_code` 那一腿 ⇒ 辛 必须红 ⇒ 证辛不空咬，码体腿没被本单迁成摆设。"""
    before = digests()
    _blind_the_code_leg(eb_r563_guard, monkeypatch)
    with pytest.raises(AssertionError) as caught:
        test_xin_a_fake_body_behind_a_reload_still_reddens_its_owner(eb_r563_guard, monkeypatch)
    assert "守卫一声不响" in str(caught.value), str(caught.value)[:200]
    print("[r584] K3 红的 victim：test_xin_a_fake_body_behind_a_reload_still_reddens_its_owner :: %s"
          % str(caught.value).splitlines()[0][:70])
    assert digests() == before, "反证写脏了被跟踪文件"


def _blind_the_semantic_slots(guard, monkeypatch):
    """K4 的摘法：把 `FieldInfo` 的语义位清单清空 ⇒ 尺子只剩 repr 可依。"""
    namespace = _namespace(guard)
    assert "_EB_R563_FIELDINFO_SLOTS" in namespace, "找不到语义位清单：摘法要重配"
    monkeypatch.setitem(namespace, "_EB_R563_FIELDINFO_SLOTS", ())


def test_k4_stripping_the_semantic_slots_blinds_the_embed_pin(eb_r563_guard, monkeypatch):
    """K4：语义位摘掉 ⇒ 戊 必须红 ⇒ 证那一层不是装饰（repr 相同的一族只有它认得出）。"""
    before = digests()
    _blind_the_semantic_slots(eb_r563_guard, monkeypatch)
    with pytest.raises(AssertionError) as caught:
        test_wu_an_embed_bit_is_named_though_the_repr_is_identical(eb_r563_guard)
    assert "守卫一声不响" in str(caught.value), str(caught.value)[:200]
    print("[r584] K4 红的 victim：test_wu_an_embed_bit_is_named_though_the_repr_is_identical :: %s"
          % str(caught.value).splitlines()[0][:70])
    assert digests() == before, "反证写脏了被跟踪文件"