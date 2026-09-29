# -*- coding: utf-8 -*-
r"""R499 · 会话归属谓词不许被实例影子遮蔽：r397 与 r179 两枚件任意顺序都成立。

## 病灶（09-29 现取，基点 `092fb34`，主树与本树两棵都复现）

    pytest tests/test_r397_read_legs_refuse_a_missing_table.py tests/test_r179_chat_denials.py
      -> 1 failed / 64 passed
         test_the_ownership_predicate_stays_the_single_source_of_truth
         AssertionError: chat.py 没走 is_owned_by：归属判定被就地抄了第二份
         assert [] == ['r179-session-mine']
    pytest tests/test_r179_chat_denials.py tests/test_r397_read_legs_refuse_a_missing_table.py
      -> 65 passed

## 根因（逐枚取证之后才动手，不是绕过去）

| 假设 | 现读（探针件排在 r397 之后） | 结论 |
| --- | --- | --- |
| `sys.modules["app.storage.sessions"]` 被换（`importlib.reload`） | 探针 `id(module)` 与 `sys.modules` 里那枚相同；r397 全文零 `importlib`/`reload` | 否 |
| `SessionRegistry` 类对象被换 | `type(chat.session_registry) is session_storage.SessionRegistry` -> True | 否 |
| 注册表单例被换 | `chat.session_registry is session_storage.session_registry` -> True | 否 |
| r397 装 overlay / 走 R253 影子根 | r397 全文零 `_temp_edit_overlay` 导入 | 否 |
| r397 改了 `DATABASE_URL`/env 未复原（动到 R56、R134 两枚闸门） | r397 只有 `monkeypatch.setenv("APP_ENV", ...)`；跑后探针 `os.environ["APP_ENV"]` -> None，`ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR` 仍在场 | 否 |
| **共享单例上长出一份实例影子** | r397 跑后 `vars(chat.session_registry)` = `['_lock', '_records', 'is_owned_by', 'metadata_path']`，出厂实例只有 `['_lock', '_records', 'metadata_path']`；多出来那枚 = `<bound method SessionRegistry.is_owned_by of ...>` | **是** |

`tests/test_r397_read_legs_refuse_a_missing_table.py:175`（基点原文）把归属谓词打在**实例**上：
`monkeypatch.setattr(chat.session_registry, "is_owned_by", lambda *_a, **_k: True)`。pytest 9.1.1 的
`MonkeyPatch.setattr` 只在 target 是**类**时才用 `target.__dict__.get(name)` 取旧值（源码注释：
"avoid class descriptors like staticmethod/classmethod"），对实例它取 `getattr` 出来的**绑定方法**；
`undo()` 再 `setattr(obj, name, oldval)` 把那份绑定方法**写回实例 `__dict__`**。于是 teardown 之后实例
字典里永久留下一枚 `is_owned_by`，从此遮蔽 `SessionRegistry.is_owned_by` —— 而本件钉的那枚桩
（`tests/test_r179_chat_denials.py:253`）正打在类属性上，`seen` 读不到调用，红成
`assert [] == ['r179-session-mine']`。全量门按字母序 r179 排在 r397 之前，所以门里今天不炸；它是
**潜伏**的：显式点名两枚件、按失败清单 re-run、换分发口径，都会把它炸成假红（事故 #81 那一族）。

## 本件交的三样

1. **根因修在污染方**：r397 改到类上打桩（pytest 对类目标走 `__dict__`，undo 干净），原地再留一枚常驻
   牙；r179 的两枚在册断言一字未动，也没有 skip/xfail/serial。
2. **顺序无关的契约钉**：`_replay_r397_world` 在同一进程里现重放 r397 的读腿世界并让它出场，前后各现跑
   一次 r179 那一格**本体**（不复制断言），两向都验，不依赖 pytest 的文件次序。
3. **对未来又长出一枚跨件全局态也有牙**：契约名集合从 `tests/**` 里「打在 `SessionRegistry` 类上的桩」
   静态**派生**，不是写死名单——① 运行期审计那枚共享单例有没有被契约名影子化（谁先跑都抓得到），
   ② 静态禁止任何件把契约名打在非类目标上（新件一落地就红，并点名文件行号）。

同族在册债（本单写域外，只在纸上点名、不动手）：`bind` 也被三枚件打在实例上，teardown 后同样留下实例
影子（现读 `vars(chat.session_registry)` 多出 `'bind'`）——`tests/test_r384_migrations_first_refuses_at_the_ask_exit.py:266`、
`tests/test_routing_intent_and_terminal_state.py:81`、`tests/test_sse_sources.py:284`。今天没有任何契约
打在类上的 `bind`，所以它不炸；一旦有人那样打，上面第 3 条那两枚牙会当场点名这三枚。

全程离线：进程内 TestClient，零起服务、零模型、零库。反证刀只落 `tests/_temp_edit_overlay.py` 那台影子根，
盘上的被跟踪文件全程只读（沿 R253/R466 姿势：`execs_module = False`，变异只装 `_world` 那一枚顶层绑定）。
"""
from __future__ import annotations

import ast
import contextlib
import functools
import importlib.util
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import chat
from app.common import auth
from app.main import app
from app.storage import sessions as session_storage
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO / "tests"
R397_REL = "tests/test_r397_read_legs_refuse_a_missing_table.py"
R397_PY = TESTS_DIR / "test_r397_read_legs_refuse_a_missing_table.py"
R179_PY = TESTS_DIR / "test_r179_chat_denials.py"

#: 反证要退回的那枚基点：`092fb34` 写死，不由 `HEAD~1` 之类现推（事故 #96/#97 那一族），
#: 由 test_the_revert_anchor_is_the_base_line_it_claims_to_be 自证它是 HEAD 的祖先。
BASE_SHA = "092fb34"
BASE_ORIGINAL_LINE = (
    '    monkeypatch.setattr(chat.session_registry, "is_owned_by", '
    "lambda *_a, **_k: True)\n")

REGISTRY_CLASS = "SessionRegistry"
PREDICATE = "is_owned_by"
RED_SENTENCE = "chat.py 没走 is_owned_by"

#: 刀的唯一一枚锚：盘上修好的那四行代码 -> 基点那一行原文。注释留在原位，变异只落影子副本。
REVERT_EDITS = (((
    "    monkeypatch.setattr(",
    '        session_storage.SessionRegistry, "is_owned_by", lambda self, *_a, **_k: True)',
    '    assert "is_owned_by" not in chat.session_registry.__dict__, (',
    '        "单例上长出了一份就地抄的影子：类上的打桩再也够不到它")',
), (
    '    monkeypatch.setattr(chat.session_registry, "is_owned_by", lambda *_a, **_k: True)',
),),)


def _load_view(path: Path, alias: str):
    """按文件路径装载一枚「视图」模块对象：不进 `sys.modules`，也不管原件被 pytest 收集到哪一步。"""
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _instance_shadows(registry) -> list:
    """实例字典里那些「类上本来就有」的名字 = 把类属性就地遮蔽掉的影子。"""
    return sorted(set(vars(registry)) & _class_owned_names(type(registry)))


def _setattr_calls(text: str):
    """`(行号, 目标 AST, 属性名)`：认 `anything.setattr(target, "name", value)` 这一枚形状。"""
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "setattr" or len(node.args) < 3:
            continue
        attr = node.args[1]
        if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
            yield node.lineno, node.args[0], attr.value


def _last_dotted_part(node) -> str:
    return ast.unparse(node).split(".")[-1]


@functools.lru_cache(maxsize=1)
def _setattr_calls_in_tests() -> tuple:
    """全仓 `tests/test_*.py` 的 setattr 形状，一次解析两向共用：(文件, 行号, 目标末段, 目标原文, 属性名)。"""
    out = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        rel = path.relative_to(REPO).as_posix()
        for lineno, target, attr in _setattr_calls(path.read_text(encoding="utf-8")):
            out.append((rel, lineno, _last_dotted_part(target), ast.unparse(target), attr))
    return tuple(out)


@functools.lru_cache(maxsize=1)
def _class_patched_names() -> frozenset:
    """契约名集合 = 凡打桩打在 `SessionRegistry` 这枚**类**上的名字，全从源码派生，不写死名单。"""
    return frozenset(attr for _rel, _line, last, _target, attr in _setattr_calls_in_tests()
                     if last == REGISTRY_CLASS)


def _instance_patches_of(names: frozenset) -> list:
    """把契约名打在非类目标上的每一处：那就是会漏出实例影子的形状。"""
    return ["%s:%s setattr(%s, %r, ...)" % (rel, line, target, attr)
            for rel, line, last, target, attr in _setattr_calls_in_tests()
            if attr in names and last != REGISTRY_CLASS]


def _replay_r397_world() -> None:
    """现跑一遍 r397 的 `_world` 再让它出场：留下的形状就是「门里 r397 先到」那一格留下的形状。"""
    r397 = _load_view(R397_PY, "r499_r397_world_view")
    with pytest.MonkeyPatch.context() as mp:
        client, _ledger, _recorder = r397._world(
            mp, env="production", pg_up=True, tables=r397.BOTH_TABLES)
        response = r397._get(client, r397.DETAIL_PATH)
        assert response.status_code == 200, response.text
    assert PREDICATE not in vars(chat.session_registry), (
        "r397 的 teardown 在共享单例上留下了实例影子，类上的打桩从此够不到它")


def _predicate_contract_verdict(tmp_path):
    """现跑 r179 那一格**本体**（同一份码，不复制断言）：绿交回 None，红交回那枚 AssertionError。"""
    r179 = _load_view(R179_PY, "r499_r179_view")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(auth, "get_user", lambda username: r179.ACCOUNTS.get(username))
        try:
            r179.test_the_ownership_predicate_stays_the_single_source_of_truth(
                TestClient(app), mp, tmp_path)
        except AssertionError as caught:   # 取证把手，不是放行：调用方必须点名它
            return caught
    return None


class _R499Edit(overlay.ShadowEdit):
    """一扇 R499 的反证窗：锚点命中不是恰好一处就整片不落；变异文本先过 `compile()`。

    🔴 沿 R466：`execs_module = False`。变异由 `install_mutation` 只装进 `_world` 那一枚顶层绑定，
    不重跑整份模块体；窗尾逐枚核对活把手没被换过。
    """

    tag = "r499"
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
def _revert_window(module, edits):
    """视图先装载（装载失败就不开窗），再开影子根那扇窗，窗内只把变异的 `_world` 装进那枚视图对象。"""
    assert callable(getattr(module, "_world", None)), "_world 不在这枚视图模块上"
    with _R499Edit(R397_PY, edits) as info, \
            r466.install_mutation(module, R397_PY, info.read_text()):
        yield info


def _restore_instance_dict(registry, snapshot: dict) -> None:
    """把刀口造出来的那份实例影子抹回开窗前的形状：真树上的单例不许带伤出门。"""
    for name in [key for key in vars(registry) if key not in snapshot]:
        del vars(registry)[name]
    for name, value in snapshot.items():
        vars(registry)[name] = value


# =========================================== 判据①：两形都绿（进程内，不赌次序）


def test_the_predicate_contract_holds_on_both_sides_of_the_replay(tmp_path):
    """r179 那一格在 r397 的世界之前、之后各现跑一次，两向都必须绿。

    这一格就是「这两枚件任意顺序都成立」本身：它不赌 pytest 在盘上收集到的次序，而是在同一枚进程里
    把污染方重放一遍，再看契约还成不成立。将来任何件用别的次序、别的分发方式都验不到它。
    """
    before = _predicate_contract_verdict(tmp_path)
    assert before is None, f"r397 还没重放就已经红，这枚牙是空的：{before}"

    _replay_r397_world()

    after = _predicate_contract_verdict(tmp_path)
    assert after is None, f"r397 的 teardown 弄哑了类上的桩：{after}"


def test_the_shared_singleton_carries_no_shadow_of_a_class_patched_predicate():
    """运行期的跨件牙：不管前面跑了哪枚件，共享单例都不许被任何一枚契约名影子化。

    契约名从源码派生（今天 = {`is_owned_by`}），所以这格对「未来又长出一枚跨件全局态」同样有牙：新件
    只要往 `SessionRegistry` 类上打桩就自动进入这格的尺子；而任何件把那枚名字打在实例上，只要它排在
    本件之前跑完，这里就当场点名。两枚身份断言把取证那三条结论（模块/类/单例都没被换）也钉在场上。
    """
    registry = chat.session_registry
    assert type(registry) is session_storage.SessionRegistry, (
        f"类身份被换了（{type(registry)!r}）：本件的尺子量错了对象")
    assert registry is session_storage.session_registry, (
        "单例身份被换了：`app.storage.sessions` 那枚注册表不是模块上这一枚")

    names = _class_patched_names()
    assert names, f"tests/ 里没有任何一处把桩打在 {REGISTRY_CLASS} 类上：这格口径空转了"
    shadows = sorted(names & set(_instance_shadows(registry)))
    assert not shadows, (
        f"单例 {registry!r} 上留着实例影子 {shadows}：类属性被就地遮蔽，凡打在它上面的桩都会被弄哑"
        "——变异方请改到类上打桩，参照 _replay_r397_world 那一格")


def test_no_test_file_patches_a_class_patched_predicate_onto_an_instance():
    """静态那半枚牙：契约名只许打在类上；打在别的目标上就点名文件行号（新件一落地就红，不看次序）。"""
    names = _class_patched_names()
    assert names, f"tests/ 里没有任何一处把桩打在 {REGISTRY_CLASS} 类上：这格口径空转了"
    hits = _instance_patches_of(names)
    assert not hits, (
        "以下位置把类级契约打在非类目标上，teardown 会留下实例影子：\n" + "\n".join(hits))


def test_the_revert_anchor_is_the_base_line_it_claims_to_be():
    """基点自证：`092fb34` 必须是 HEAD 的祖先，且刀要用那一行确实长在基点那份文件里。"""
    _git("merge-base", "--is-ancestor", BASE_SHA, "HEAD")
    base = _git("show", f"{BASE_SHA}:{R397_REL}")
    assert BASE_ORIGINAL_LINE in base, "刀锚与基点原文对不上：反证退回去的不是那一枚病"


# ================================================ 判据②：反向证明不许空转


def test_reverting_the_r397_line_goes_red_in_the_shadow_root(tmp_path):
    """把修好的那一处退回基点原状 ⇒ 同一进程里必须当场红，红句原文交回；盘上文件一字不动。

    窗内三步都是真的：变异版 `_world` 现跑一次（造出实例影子）→ 单例确实被契约名影子化 → r179 那一格
    本体现跑，必须抛出在册那句红。出门逐枚还原，并证明影子没漏在真树上、那一格又回绿。
    """
    registry = chat.session_registry
    snapshot = dict(vars(registry))
    tracked_before = overlay.sha16_of_bytes(R397_PY.read_bytes())
    module = _load_view(R397_PY, "r499_r397_knife_view")

    try:
        with _revert_window(module, REVERT_EDITS) as info:
            with pytest.MonkeyPatch.context() as mp:
                # 🔴 `r466._rebase` 重建函数时只带 `__defaults__`，关键字专用默认值（`__kwdefaults__`）
                # 会丢，所以变异版的 `_world` 必须把每一枚 kw-only 参数都点名传全。
                client, _ledger, _recorder = module._world(
                    mp, env="production", pg_up=True, tables=module.BOTH_TABLES,
                    driver_missing=False)
                assert module._get(client, module.DETAIL_PATH).status_code == 200

            shadowed = sorted(_class_patched_names() & set(_instance_shadows(registry)))
            assert shadowed == [PREDICATE], f"退回原状没有造出实例影子，刀在空转：{shadowed}"

            caught = _predicate_contract_verdict(tmp_path)
            assert isinstance(caught, AssertionError), "退回原状没有当场红 —— 反证在空转"
            assert RED_SENTENCE in str(caught), str(caught)
            print("[r499] 反证红句原文：%r" % (str(caught),))
    finally:
        _restore_instance_dict(registry, snapshot)

    assert overlay.sha16_of_bytes(R397_PY.read_bytes()) == tracked_before, (
        "反证窗碰到了真树上的 r397")
    print("[r499] 盘上 r397 sha16：%s -> %s restored=%s shadow_clean=%s" % (
        tracked_before, info["after"], info["restored"], info["shadow_clean"]))
    expected = sorted(set(snapshot) & _class_owned_names(type(registry)))
    assert _instance_shadows(registry) == expected, (
        "刀口出门时单例形状变了，影子漏在真树上：%r != %r" % (
            _instance_shadows(registry), expected))
    verdict = _predicate_contract_verdict(tmp_path)
    assert verdict is None, f"刀收干净之后那一格还红：{verdict}"

def test_the_r397_in_place_catch_bites_on_an_already_shadowed_singleton():
    """第二把刀：别处先漏出一枚实例影子时，r397 原地那枚常驻牙必须当场开口，而不是放行到下一枚件。

    这里不碰盘上文件，直接伪造 K1 已经证明会漏出的那一枚形状（`vars(registry)[PREDICATE] = 绑定方法`），
    再叫 r397 的 `_world` 自己判它。牙摘掉的话这一格会一路绿到 r179，正是本单根治前门里的样子。
    """
    registry = chat.session_registry
    assert PREDICATE not in vars(registry), "开窗前单例就带着影子：上一枚刀没收干净"
    snapshot = dict(vars(registry))
    r397 = _load_view(R397_PY, "r499_r397_bite_view")

    vars(registry)[PREDICATE] = getattr(registry, PREDICATE)   # K1 证明会漏的那种形状，这里手工造一枚
    try:
        with pytest.MonkeyPatch.context() as mp:
            with pytest.raises(AssertionError) as caught:
                r397._world(mp, env="production", pg_up=True, tables=r397.BOTH_TABLES)
    finally:
        _restore_instance_dict(registry, snapshot)

    assert "就地抄的影子" in str(caught.value), str(caught.value)
    assert _instance_shadows(registry) == sorted(set(snapshot) & _class_owned_names(type(registry))), (
        "伪造的影子没收回")
