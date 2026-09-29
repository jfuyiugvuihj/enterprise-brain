# -*- coding: utf-8 -*-
r"""R508 · 三枚 `bind` 实例桩改到类目标：注册表上不许留方法影子。

## 这单治什么

R499 查出并治了 `is_owned_by` 那一枚（`tests/test_r397_read_legs_refuse_a_missing_table.py`），并如实
记下一笔同族在册债没治：`bind` 被三枚件打在**实例**上。pytest 9.1.1 的 `MonkeyPatch.setattr` 只在
target 是**类**时才用 `target.__dict__.get(name)` 取旧值，对实例它取 `getattr` 出来的绑定方法，
`undo()` 再把它 `setattr` 回实例 `__dict__` —— teardown 之后那枚单例上永久长出一份影子，从此遮蔽
`SessionRegistry.bind`；哪天有人把 `bind` 打在类上，那份类级桩就读不到调用，跳文件次序假红。今天没有
类级 `bind` 契约所以不炸，但这是同一枚地雷。

| 件 | 改前（`git show 8857a8d:<path>` 原文） | 改后（盘上现在） |
| --- | --- | --- |
| `tests/test_r384_migrations_first_refuses_at_the_ask_exit.py:266` | `monkeypatch.setattr(chat.session_registry, "bind", _spy)` | `monkeypatch.setattr("app.storage.sessions.SessionRegistry", "bind", lambda self, *_a, **_k: _spy())` |
| `tests/test_routing_intent_and_terminal_state.py:81` | `monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)` | `monkeypatch.setattr("app.storage.sessions.SessionRegistry", "bind", lambda self, *_a, **_k: None)` |
| `tests/test_sse_sources.py:284` | `monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)` | `monkeypatch.setattr(SessionRegistry, "bind", lambda self, *_a, **_k: None)` |

三枚都是**只换桩目标**：断言一字未动，枚数未增未减，`_spy` 那枚记录器本体也没碰（类目标多一个
`self`，所以用一行 lambda 转接）。

## 09-29 现取的读数（逐枚单跑，探针在 `pytest_sessionfinish` 读 `vars(session_storage.session_registry)`）

| 件 | 单跑结果 | 共享单例 `vars()` | 结论 |
| --- | --- | --- | --- |
| `test_r384_migrations_first_refuses_at_the_ask_exit.py` | 26 passed | `['_lock', '_records', 'bind', 'metadata_path']` | 漏影子，**有爆炸危**（打在进程级单例上） |
| `test_routing_intent_and_terminal_state.py` | 7 passed | `['_lock', '_records', 'bind', 'metadata_path']` | 漏影子，**有爆炸危**（打在进程级单例上） |
| `test_sse_sources.py` | 14 passed / 4 skipped | `['_lock', '_records', 'metadata_path']` | 干净：`patch_offline` 先把 `chat.session_registry` 换成一枚 tmp 实例（`:136`），影子落在那枚**一次性实例**上，出不了本件 |

所以 R499 纸上把三枚并列成"现读 `vars(chat.session_registry)` 多出 `bind`"这一句，只有前两枚成立；
第三枚形状相同但今天不外溢——本单照样把它改到类上（同族形状不留第二份），并在
`docs/testing/r508-instance-shadow-debt-2026-09-29.md` 把两档危级分开记账。

## 本件交的三样

1. **运行期审计**：在同一枚进程里现重放这三枚件的**本体**（不复制断言），把它们碰过的每一枚注册表都
   抓回来——包括 sse 那枚当场换进来的一次性实例——teardown 之后逐枚读 `vars()`，不许多出任何一枚
   类上就有的方法名。不赌 pytest 的文件次序。
2. **静态禁止**：契约名（=凡打在 app 类上的桩名）与 app 模块级单例名全部从源码**派生**，不写死名单；
   把契约名打在 `chat.session_registry` 这类**模块级单例**上直接红。另有一格冻结账：打在测试局部对象上的
   同族形状今天恰有三枚（r103 两枚 + r106 一枚，写进纸上排队，本单不碰），多第四枚就红。
3. **反证刀**：把三枚里任意一枚退回实例桩 ⇒ 上面的审计与静态格必须当场红，红句原文交回；变异只落
   `tests/_temp_edit_overlay.py` 那台影子根，盘上的被跟踪文件全程只读，出门逐枚核对 sha16 报
   `restored=True`。

全程离线：进程内 TestClient，零起服务、零模型、零库写。
"""
from __future__ import annotations

import ast
import contextlib
import functools
import inspect
import subprocess
import types
from pathlib import Path

import pytest

from app.api.v1 import chat
from app.common import cache
from app.storage import sessions as session_storage
from app.storage.sessions import SessionRegistry
from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO / "tests"
APP_DIR = REPO / "app"
THIS_FILE = TESTS_DIR / "test_r508_the_bind_stub_stays_on_the_class.py"

#: 改前一律从这枚基点取，不许拿 `HEAD` 当改前（事故 #97 同族）；由下面那格自证它是 HEAD 的祖先。
BASE_SHA = "8857a8d"

REGISTRY_CLASS = "SessionRegistry"
RED_SENTENCE = "跑完这三枚件之后注册表上不许留任何一枚方法影子"
STATIC_RED = "以下位置把类级契约打在模块级单例上，teardown 会留下实例影子"
LEDGER_RED = "打在测试局部对象上的同族形状多了新账"

#: 本单治的三枚点：(仓内相对路径, 用来重放的那枚顶层测试名, 基点那一行, 盘上现在那几行)
SITES = (
    ("tests/test_r384_migrations_first_refuses_at_the_ask_exit.py",
     "test_the_refusal_precedes_every_side_effect",
     ('    monkeypatch.setattr(chat.session_registry, "bind", _spy)',),
     ('    monkeypatch.setattr(',
      '        "app.storage.sessions.SessionRegistry.bind", lambda self, *_a, **_k: _spy())')),
    ("tests/test_routing_intent_and_terminal_state.py",
     "test_unproductive_turn_fails_instead_of_completing",
     ('    monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)',),
     ('    monkeypatch.setattr(',
      '        "app.storage.sessions.SessionRegistry.bind", lambda self, *_a, **_k: None)')),
    ("tests/test_sse_sources.py",
     "test_sources_event_reaches_a_real_http_client_over_asgi_transport",
     ('    monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)',),
     ('    monkeypatch.setattr(SessionRegistry, "bind", lambda self, *_a, **_k: None)',)),
)

#: 同族在册债的冻结账（本单写域外，只在纸上点名）：(文件, 属性名)。第四枚进来就红。
KNOWN_LOCAL_DEBTS = frozenset({
    ("tests/test_r103_graph_unconfigured_exit.py", "upsert"),
    ("tests/test_r106_open_platform_unconfigured_exit.py", "upsert"),
})


# ----------------------------------------------------------- 把手：源码形状与影子形状


def _module_from_text(text: str, path: Path, alias: str):
    """把一份字节装成一枚一次性模块对象：`__file__` 指向真身，报错行列号与盘上同形。"""
    module = types.ModuleType(alias)
    module.__file__ = str(path)
    module.__dict__["__name__"] = alias
    exec(compile(text, str(path), "exec"), module.__dict__)
    return module


def _site_view(rel: str, alias: str):
    """按当前该算数的那份字节装载那枚件：窗内是影子副本的变异版，窗外是盘上的字。"""
    return _module_from_text(overlay.authoritative_text(rel), REPO / rel, alias)


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0, "git %s rc=%s：%s" % (" ".join(args), out.returncode, out.stderr)
    return out.stdout


def _class_owned_names(cls) -> set:
    names: set = set()
    for base in cls.__mro__:
        names.update(vars(base))
    return names


def _instance_shadows(obj) -> list:
    """实例字典里那些「类上本来就有」的名字 = 把类属性就地遮蔽掉的影子。"""
    return sorted(set(vars(obj)) & _class_owned_names(type(obj)))


def _setattr_rows(text: str):
    """`(行号, 目标原文, 属性名)`：认 `anything.setattr(target, "name", value)` 这一枚形状。"""
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "setattr" or not node.args:
            continue
        target = node.args[0]
        if len(node.args) == 2 and isinstance(target, ast.Constant) and isinstance(target.value, str):
            dotted = target.value.strip()
            if "." in dotted:
                head, name = dotted.rsplit(".", 1)
                yield node.lineno, head, name
        elif len(node.args) >= 3:
            attr = node.args[1]
            if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                text_target = (target.value.strip()
                               if isinstance(target, ast.Constant) and isinstance(target.value, str)
                               else ast.unparse(target))
                yield node.lineno, text_target, attr.value


@functools.lru_cache(maxsize=1)
def _app_shape():
    """app/ 的两张派生表：类名 -> 方法名集合；模块级单例属性名 -> 类名。全从源码读，零导入。"""
    classes: dict = {}
    singletons: dict = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        own = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = {x.name for x in node.body
                           if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))}
                classes.setdefault(node.name, set()).update(methods)
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                cname = (func.id if isinstance(func, ast.Name)
                         else (func.attr if isinstance(func, ast.Attribute) else ""))
                if cname in own:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            singletons[target.id] = cname
    return classes, singletons


def _rows_in_tests() -> tuple:
    """全仓 `tests/**.py` 的 setattr 形状 + 分类：`(文件, 行号, 目标原文, 属性名, 目标种类)`。

    读的是「当前该算数的那份字节」：反证窗开着时那枚件走影子副本，所以静态格量的就是窗里那一版码。
    解析按文件内容缓存，窗外整棵树只解析一次。
    """
    rows = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        rows.extend(_rows_in_one_file(rel, overlay.authoritative_text(rel)))
    return tuple(rows)


@functools.lru_cache(maxsize=None)
def _rows_in_one_file(rel: str, text: str) -> tuple:
    classes, singletons = _app_shape()
    tree = ast.parse(text)
    aliases: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases.add(a.asname or a.name.split(".")[0])
                aliases.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                aliases.add(a.asname or a.name)
    out = []
    for lineno, target, attr in _setattr_rows(text):
        parts = target.split(".")
        last = parts[-1]
        if last in classes:
            kind = "class"
        elif len(parts) > 1 and last in singletons and parts[0] in aliases:
            kind = "singleton"
        elif len(parts) == 1 and target in aliases:
            kind = "module"
        else:
            kind = "local"
        out.append((rel, lineno, target, attr, kind))
    return tuple(out)


def _class_patched_names(rows=None) -> frozenset:
    """契约名集合 = 凡把桩打在 app **类**上的名字，全从源码派生，不写死名单。"""
    rows = _rows_in_tests() if rows is None else rows
    return frozenset(attr for _rel, _line, _target, attr, kind in rows if kind == "class")


def _singleton_patches(names: frozenset, rows=None) -> list:
    rows = _rows_in_tests() if rows is None else rows
    return ["%s:%s setattr(%s, %r, ...)" % (rel, line, target, attr)
            for rel, line, target, attr, kind in rows
            if attr in names and kind == "singleton"]


def _local_patches(names: frozenset, rows=None) -> frozenset:
    rows = _rows_in_tests() if rows is None else rows
    return frozenset((rel, attr) for rel, _line, _target, attr, kind in rows
                     if attr in names and kind == "local")


# ------------------------------------------------------ 判据①的运行期把手：重放三枚件本体


def _quarantine_cache_state(mp) -> None:
    """把重放期间的 redis 流量改道到一次性实例：本件不许溅脏进程级那一枚。

    `check_rate_limit` 用的是 `ratelimit:{username}` 那一枚 60 秒窗口的 sorted set，答案缓存同一条
    路径。本件一枚测试里要把那三枚件重放若干遍，如果不改道，`admin` 的分钟额度会被重放吃掉，排在
    本件之后的 `tests/test_routing_intent_and_terminal_state.py` 就会撞上「超限」道，`/ask` 改走入队
    分支回 400 `idempotency_key_required`——那正是本单在治的同族病（跨件进程级全局态），只是 lever
    不一样，见纸上 §5。改道走的是模块目标（`cache.get_redis`），undo 干净，出厂那一枚对象一个字节不动。
    """
    live = cache.get_redis()
    if type(live).__module__.split(".")[0] not in ("fakeredis", "app"):
        return                      # 真接了外部 Redis 的环境不在测试口径里，不冒充能隔离
    spare = type(live)()
    mp.setattr(cache, "get_redis", lambda: spare)


def _replay_site(rel: str, fn_name: str, mp, tmp_path) -> list:
    """现跑那枚件的本体，把它碰过的每一枚注册表实例都交回来（含它当场换进来的那一枚）。

    影子是 `undo()` 写回去的，所以调用方必须等 `mp` 那层上下文退出之后再读 `vars()`。
    """
    view = _site_view(rel, "r508_%s_view" % Path(rel).stem)
    fn = getattr(view, fn_name)
    shared = chat.session_registry
    params = list(inspect.signature(fn).parameters)
    _quarantine_cache_state(mp)
    try:
        fn(mp, tmp_path) if "tmp_path" in params else fn(mp)
    except AssertionError as exc:
        # 那一枚件自己的断言红不属于本件判据：影子是 teardown 写回去的，形状在这里照样量得准。
        # 门里若它自己红，由它自己那一格红；本件不替它顶罪，也不许被它的次序病拖成假红。
        print("[r508] 重放 %s 时它自己红了（本件只量形状）：%r" % (rel, str(exc)[:140]))
    touched = [shared]
    if chat.session_registry is not shared:
        touched.append(chat.session_registry)          # sse 那枚一次性实例
    return touched


def _shadow_verdict(tmp_path) -> list:
    """三枚件逐枚重放，teardown 之后逐枚读形状：交回所有多出来的方法影子（空 = 干净）。"""
    verdict: list = []
    for rel, fn_name, _base, _now in SITES:
        with pytest.MonkeyPatch.context() as mp:
            touched = _replay_site(rel, fn_name, mp, tmp_path)
        for registry in touched:
            for name in _instance_shadows(registry):
                verdict.append("%s 跑完 %s 之后 %s(%s) 上留着方法影子 %r（遮蔽 %s.%s）" % (
                    rel, fn_name, getattr(registry, "metadata_path", registry),
                    type(registry).__name__, name, type(registry).__name__, name))
    return verdict


class _R508Edit(overlay.ShadowEdit):
    """一扇 R508 的反证窗：锚点命中不是恰好一处就整片不落；变异文本先过 `compile()`。"""

    tag = "r508"
    execs_module = False

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = [(tuple(old), tuple(new)) for old, new in edits]

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = newline.join(old)
            hits = mutated.count(needle)
            assert hits == 1, ("%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落"
                               % (self.path.name, hits, old[0]))
            mutated = mutated.replace(needle, newline.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextlib.contextmanager
def _revert_window(rel: str, site):
    """把那一处退回实例桩：变异只落影子根，盘上的字全程只读。"""
    _base_lines, now_lines = site[2], site[3]
    with _R508Edit(REPO / rel, ((now_lines, _base_lines),)) as info:
        yield info


def _audit_verdict_via_registered_test(tmp_path):
    """现跑本件那格在册审计**本体**（不复制断言）：绿交回 None，红交回那枚 AssertionError。"""
    view = _module_from_text(THIS_FILE.read_text(encoding="utf-8"), THIS_FILE, "r508_audit_view")
    try:
        view.test_the_three_sites_leave_no_method_shadow_on_any_registry(tmp_path)
    except AssertionError as caught:      # 取证把手，不是放行：调用方必须点名它
        return caught
    return None


# ----------------------------------------------------- 判据①：跑完不许留方法影子（不赌次序）


def test_the_registry_class_and_singletons_are_what_the_audit_measures(tmp_path):
    """尺子的身份先自证：类没被换、共享单例就是模块上那一枚、出厂形状里没有方法影子。"""
    registry = chat.session_registry
    assert type(registry) is SessionRegistry, f"类身份被换了（{type(registry)!r}）"
    assert registry is session_storage.session_registry, "共享单例被换了：量错了对象"
    fresh = SessionRegistry(tmp_path / "r508-factory-shape.json")
    assert _instance_shadows(fresh) == [], "出厂实例就带着方法影子：这把尺子是空的"
    assert _instance_shadows(registry) == [], "开窗前单例就带着方法影子：上一枚刀没收干净"
    assert callable(SessionRegistry.bind) and "bind" not in vars(registry), (
        "`bind` 出厂就长在实例字典上：本单治的不是这一枚病")


def test_the_three_sites_leave_no_method_shadow_on_any_registry(tmp_path):
    """三枚件逐枚现重放，出场之后注册表上不许多出任何一枚类级方法名。

    抓的是两枚对象：进程级共享单例（r384 与 routing 打在它身上）和 sse 那枚当场换进来的一次性实例。
    打在类上的桩走 `__dict__` 取旧值，undo 干净，所以两枚都必须是空的。本件只量形状：重放里那枚件自己
    的断言红（今天门里有一条跳文件次序的报表档入队病，见纸上 §5）不改写本件判据，也不许把它拖成假红。
    """
    verdict = _shadow_verdict(tmp_path)
    assert not verdict, RED_SENTENCE + "：\n" + "\n".join(verdict)


def test_the_class_level_bind_survives_every_replay(tmp_path):
    """类级桩的对面一半：三枚件跑完，真正在跑的必须是 app 出厂那一枚 `bind`。"""
    registry = chat.session_registry
    original = SessionRegistry.__dict__["bind"]
    for rel, fn_name, _base, _now in SITES:
        with pytest.MonkeyPatch.context() as mp:
            _replay_site(rel, fn_name, mp, tmp_path)
        assert SessionRegistry.__dict__["bind"] is original, (
            "%s 的 teardown 没把类上的 bind 装回出厂那一枚：桩漏在类上了" % rel)
    assert "bind" not in vars(registry), "共享单例被实例影子接管了"


# -------------------------------------------------------- 判据②：同一枚形状不许多第二份


def test_the_base_lines_are_the_ones_the_ticket_names():
    """基点自证：改前一律 `git show 8857a8d:<path>`；那三行确实长在基点上，且已不在盘上。"""
    _git("merge-base", "--is-ancestor", BASE_SHA, "HEAD")
    for rel, _fn, base_lines, now_lines in SITES:
        base_text = _git("show", "%s:%s" % (BASE_SHA, rel))
        for line in base_lines:
            assert line + "\n" in base_text.replace("\r\n", "\n"), (
                "改前原文与基点对不上：%s -> %r" % (rel, line))
        disk = (REPO / rel).read_text(encoding="utf-8")
        for line in base_lines:
            assert line not in disk, "%s 盘上还留着实例桩那一行：%r" % (rel, line)
        for line in now_lines:
            assert line in disk, "%s 盘上没有声称的改后原文：%r" % (rel, line)


def test_no_test_file_patches_a_class_patched_contract_onto_a_module_singleton():
    """静态那半枚牙：契约名（打在 app 类上的桩名）不许打在 app 模块级单例上；新件一落地就红，不看次序。"""
    names = _class_patched_names()
    assert "bind" in names and "is_owned_by" in names, (
        f"契约名集合里没有 bind/is_owned_by：{sorted(names)}——本单的尺子空转了")
    hits = _singleton_patches(names)
    assert not hits, STATIC_RED + "：\n" + "\n".join(sorted(hits))


def test_the_local_instance_stub_ledger_has_no_second_entry():
    """冻结账：打在测试局部对象上的同族形状今天恰是 r103/r106 那三枚（纸上排队），多一枚就红。"""
    names = _class_patched_names()
    seen = _local_patches(names)
    fresh = sorted(seen - KNOWN_LOCAL_DEBTS)
    assert not fresh, LEDGER_RED + "：" + repr(fresh) + "（治法：改到类目标，参照 SITES 那三行）"
    assert seen == KNOWN_LOCAL_DEBTS, (
        "冻结账对不上，纸上的名册过期了：现读 %r / 在册 %r" % (sorted(seen), sorted(KNOWN_LOCAL_DEBTS)))


# ------------------------------------------------------ 判据③：反证刀不许空转


@pytest.mark.parametrize("site", SITES, ids=[site[0].split("/")[-1] for site in SITES])
def test_reverting_a_site_to_an_instance_stub_goes_red(site, tmp_path):
    """把其中任意一枚退回实例桩 ⇒ 在册审计必须当场红，红句原文交回；盘上文件一字不动。"""
    rel, fn_name = site[0], site[1]
    registry = chat.session_registry
    snapshot = dict(vars(registry))
    tracked_before = overlay.sha16_of_bytes((REPO / rel).read_bytes())

    with _revert_window(rel, site) as info:
        caught = _audit_verdict_via_registered_test(tmp_path)
        assert isinstance(caught, AssertionError), (
            "退回实例桩之后在册审计还绿：这把刀在空转（%s）" % rel)
        assert RED_SENTENCE in str(caught), str(caught)
        print("[r508] 反证红句原文（%s）：%r" % (Path(rel).name, str(caught)))
        static_hits = _singleton_patches(_class_patched_names())
        assert any(hit.startswith(rel + ":") for hit in static_hits), (
            "退回实例桩之后静态格没点名这一枚：%r" % sorted(static_hits))

    assert overlay.sha16_of_bytes((REPO / rel).read_bytes()) == tracked_before, (
        "反证窗碰到了真树上的 %s" % rel)
    for name in [key for key in vars(registry) if key not in snapshot]:
        del vars(registry)[name]
    for name, value in snapshot.items():
        vars(registry)[name] = value
    print("[r508] %s sha16 %s -> %s same=%s shadow_clean=%s" % (
        Path(rel).name, tracked_before, info["after"], info["restored"], info["shadow_clean"]))
    assert info["restored"] is True, "盘上那枚件的字节在窗内被动过"
    assert info["shadow_clean"] is True, "影子副本没回到盘上的字"
    assert _instance_shadows(registry) == [], "刀口出门时共享单例还带着影子"
    assert _audit_verdict_via_registered_test(tmp_path) is None, "刀收干净之后在册审计还红"
