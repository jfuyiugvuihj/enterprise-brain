# -*- coding: utf-8 -*-
r"""R253：反证钉的「影子根」——变异只落在 %TEMP% 里的副本，被跟踪文件全程只读。

来历（跟进单 §100.4 判据 ①）：本仓两枚反证钉会**在测试运行期间就地改写磁盘上的被跟踪文件**
（``app/api/v1/chat.py``、``docs/api/contract-v1.md``），跑完再逐字节还原。单文件串行复跑是绿的，
``-n 8`` 并发下会互相撞：一枚 worker 把 chat.py 改成变异版的那一刻，另一枚 worker 的
``_TempEdit`` 眼里就变成「锚点不唯一（0 处）」，而第三枚在收尾比 ``_tree_sha()`` 的件会因为
自己窗内那枚 sha 变了而红。假红的代价是让「敢不敢并树」变贵、让全量门不可信。

本件只提供一枚性质：**被跟踪文件在测试全程只读**。

  · 变异落到 ``%TEMP%`` 下一份 ``app/**`` 与契约的**副本**（影子根）里；只复制，不硬链接——
    硬链接共享 inode，穿过它 ``write_bytes`` 照样会改掉盘上那枚，那正是本单要根治的形状。
  · 需要「让变异真的被执行」的那几枚件，把影子根的字节 exec 进**同一个**模块对象的
    ``__dict__``（``importlib.reload`` 本来也不换模块身份）；窗尾**不再重跑码体**，而是把命名空间
    倒回进门那一刻的那张快照（R553：重跑会再造顶层类与顶层实例，身份就从此对不上号）。
  · 每扇窗进门都从盘上重取基线，所以崩在半路也不会把变异漏给下一扇窗。

判据 ③ 的分工：这里搬走的只有「变异往哪儿落」，没有「变异是什么」。锚点、替换文本、还原核对、
报错原文的措辞全部留在调用方那些 ``ShadowEdit`` 子类里——摘掉守卫会红的那一格，改完还在同一格红。
🔴 R583：本件不登记「谁开了窗」，也不写枚数——开窗者逐枚点名在派生清单
``tests/test_r583_window_inventory.py``（沿 AST）与名册
``tests/test_r466_mutation_does_not_leak_into_live_module.py::WINDOWS`` 那本账里。
这里的散文若再出现「那两枚／那九枚」这类账面枚数，就是给下一班撒完的假账。
🔴 R589：射程内测试件集合也只在这件里枚举与解析一次——``in_range_test_rels()`` 是唯一的射程口径，
``parse_in_range()`` 是唯一的解析口径。解析不了的文件既不许静默跳过（「射程内集合」会无声少一枚，
它名下的账从此不在射程里），也不许把不带文件名的原文直接端上去（那会把别人的一枚手抖读成一次回归）。
落点 ``tests/test_r589_unparseable_files_cannot_shrink_the_range.py``，凭据见
``docs/testing/r589-unparseable-files-cannot-shrink-the-range-2026-10-03.md``。
"""
from __future__ import annotations

import ast
import atexit
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]

#: 影子根整棵复刻的目录：发射面全在 ``app`` 里，AST 扫描要走整棵才不作弊。
MIRROR_DIRS = ("app",)
#: 影子根按需复刻的单文件：契约。``docs`` 不许整棵进影子，那会连别人的在途改动一起抄进来。
MIRROR_FILES = ("docs/api/contract-v1.md",)
#: 编译产物不进影子根：它会把遍历形状变成第二份。
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}


def rel_of(path) -> str:
    """被跟踪文件 -> 仓内相对路径（posix 分隔）：影子根按这枚键对齐两边。"""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO).as_posix()
    except ValueError:
        raise AssertionError("%s 不在 %s 里面：影子根只管被跟踪文件" % (resolved, REPO))


def sha16_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class ShadowRoot:
    """``%TEMP%`` 下的 ``app/**`` 与契约副本：反证窗里只改它，盘上的字一个字都不动。"""

    def __init__(self) -> None:
        self._root = None

    @property
    def root(self) -> Path:
        if self._root is None:
            self._build()
        return self._root

    def _build(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="r253-shadow-"))
        for rel_dir in MIRROR_DIRS:
            source = REPO / rel_dir
            if not source.is_dir():
                raise AssertionError("影子根要复刻的目录不在：%s" % source)
            for dirpath, dirs, files in os.walk(source):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                here = root / Path(dirpath).relative_to(REPO)
                here.mkdir(parents=True, exist_ok=True)
                for name in sorted(files):
                    shutil.copyfile(Path(dirpath) / name, here / name)
        self._root = root
        for rel_file in MIRROR_FILES:
            self.ensure(rel_file)
        atexit.register(self.close)

    def ensure(self, rel: str) -> Path:
        """影子副本回到盘上的字，并交回它的位置：每扇窗的基线都从这里长出来。"""
        tracked = REPO / rel
        if not tracked.is_file():
            raise AssertionError("被跟踪的基线文件不在：%s" % tracked)
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        shutil.copyfile(tracked, target)
        return target

    def write(self, rel: str, data: bytes) -> None:
        target = (self.root / rel).resolve()
        if self.root not in target.parents:
            # 构造性的一格：影子根**写不到**被跟踪文件，所以「忘还原」这类事故伤不到盘上。
            raise AssertionError("影子根越界：%s 不在 %s 下面" % (target, self.root))
        target.write_bytes(data)

    def read_bytes(self, rel: str) -> bytes:
        return (self.root / rel).read_bytes()

    def close(self) -> None:
        if self._root is not None:
            shutil.rmtree(self._root, ignore_errors=True)
            self._root = None


SHADOW = ShadowRoot()

#: 当前开着窗的 rel 列表（进门 append、出门 remove）：两枚用途——视图切换与嵌套告警。
_WINDOWS: list = []


def open_windows() -> tuple:
    return tuple(_WINDOWS)


def view_root() -> Path:
    """窗外读盘上的真身，窗内读影子根：同一份解析代码，两种视图。"""
    return SHADOW.root if _WINDOWS else REPO


def authoritative_text(rel: str) -> str:
    """当前该算数的那份字节：窗内是影子副本的变异版，窗外是盘上的被跟踪文件。"""
    source = SHADOW.root / rel if rel in _WINDOWS else REPO / rel
    return source.read_bytes().decode("utf-8")


# ==================== R589：射程只从这里枚举，解析失败只从这里红 ====================
#
# 病（跟进单 §157 二，10-03 现场复现）：本族「射程内测试件集合」是按**能否 parse** 长出来的，两种坏
# 形状都真在盘上生活过——
#   · 静默跳过：``tests/test_r516_the_dataset_stubs_stay_on_the_class.py::_all_rows`` 原来是
#     ``except SyntaxError: continue``。一枚解析不了的件被无声摘出集合，它名下的账从此不在射程里，
#     而每一枚在册钉照样全绿——``assert handles`` 那种「空集才红」的守卫看不见「少一枚」。
#   · 红得没法照着改：``tests/test_r253_no_test_rewrites_a_tracked_file.py::suite_sources`` 调
#     ``ast.parse(text)`` 不交 ``filename``，原文抛出去报的是 ``File "<unknown>", line 2``，不点名
#     是哪枚文件，于是别人（或总控自己）的一枚手抖被读成一次回归，同时红三枚与本单无关的钉。
# 治法是一枚口径两家用：射程只由 ``in_range_test_rels()`` 枚举一次，解析只由 ``parse_in_range()`` 收口
# 一次；解析不了就红，逐枚点名「文件、第几行、第几列、原文那一句、什么错」；``assert_covers_the_range``
# 再按逐枚差集对账「输入面少了哪一枚」，缺谁点谁。
# 🔴 本节不写枚数：枚数由 ``in_range_test_rels()`` 现量（写死就是给下一班撒的假账，同 R583 那条规矩）。

#: 射程 = ``tests/**.py``。全族唯一的枚举口径：别处再 ``rglob`` 一份就是第二份真源。
RANGE_DIR = "tests"
#: 编译缓存不是源码：混进射程等于把同一枚件数两遍。
RANGE_SKIP_DIR_NAMES = {"__pycache__", ".mypy_cache", ".pytest_cache"}
#: 红字里带上这两枚名字，接手的人不用回跟进单猜该改哪儿、该看哪份凭据。
RANGE_PIN = "tests/test_r589_unparseable_files_cannot_shrink_the_range.py"
RANGE_PAPER = "docs/testing/r589-unparseable-files-cannot-shrink-the-range-2026-10-03.md"


def in_range_test_paths(repo=None) -> list:
    """射程内每一枚件的盘上位置（排序、去编译缓存）：唯一的枚举口径，派生件都从这里长出来。"""
    base = Path(repo).resolve() if repo is not None else REPO
    root = base / RANGE_DIR
    if not root.is_dir():
        raise AssertionError("射程目录不在：%s——枚举口径自己缩水了，本族任何「0 处」读数都不算数" % root)
    return [path for path in sorted(root.rglob("*.py"))
            if not RANGE_SKIP_DIR_NAMES & set(path.parts)]


def in_range_test_rels(repo=None) -> tuple:
    """射程内件名的仓内相对路径（posix、排序）：集合对账按这一枚元组走，不按账面枚数。"""
    base = Path(repo).resolve() if repo is not None else REPO
    return tuple(path.relative_to(base).as_posix() for path in in_range_test_paths(base))


def describe_parse_failure(rel: str, exc: BaseException, text: str) -> str:
    """一枚解析失败 -> 人能照着改的读数：文件、第几行、第几列、原文那一句、什么错。"""
    line = getattr(exc, "lineno", None)
    column = getattr(exc, "offset", None)
    source = (getattr(exc, "text", None) or "").strip("\r\n")
    if not source and line:
        lines = text.replace("\r\n", "\n").split("\n")
        source = lines[line - 1] if 0 < line <= len(lines) else ""
    return "%s:第 %s 行 第 %s 列  %s  %s: %s" % (
        rel, line if line else "?", column if column else "?", source,
        type(exc).__name__, getattr(exc, "msg", None) or exc)


def parse_in_range(texts: dict = None, repo=None) -> dict:
    """射程内集合 -> ``rel -> (文本, 已解析 AST)``：该族唯一的严格解析口径（与 ``parse_sources`` 同形）。

    三种用法同一枚判法：
      · ``texts=None`` 读盘上的射程（走 ``authoritative_text``，所以反证窗里读的仍是影子那一份）；
      · 交回 ``texts`` 就是一枚**合成输入面**：反证只摘输入面，被跟踪文件全程只读，与 R572／R583 同形；
      · 无论哪一路，解析不了的文件一枚都不许被跳过：逐枚攒齐失败再一次红全，红字点名文件与行列。
    🔴 收尾那格 ``set(parsed) == set(texts)`` 是给下一班的牙：谁把这里改成「catch 完 continue」，
    这格当场红——静默缩集这一族病不许靠纪律防。
    """
    if texts is None:
        texts = {}
        unreadable: list = []
        for rel in in_range_test_rels(repo):
            try:
                texts[rel] = authoritative_text(rel)
            except (OSError, UnicodeDecodeError) as exc:
                unreadable.append("%s 读不出文本 %s: %s" % (rel, type(exc).__name__, exc))
        if unreadable:
            raise AssertionError(
                "射程内有 %d 枚件读不出文本（R589 判据①）：读不出也按解析不了同一格处置，不许静默少一枚：\n  %s\n"
                "判据落点 %s，凭据 %s" % (len(unreadable), "\n  ".join(unreadable), RANGE_PIN, RANGE_PAPER))
    parsed: dict = {}
    failures: list = []
    for rel in sorted(texts):
        text = texts[rel]
        try:
            parsed[rel] = (text, ast.parse(text, filename=rel))
        except SyntaxError as exc:
            failures.append(describe_parse_failure(rel, exc, text))
    if failures:
        raise AssertionError(
            "射程内有 %d 枚件解析不了（R589 判据①）：这一族的「射程内集合」按能否 parse 长出来，一枚解析不了的"
            "文件被静默跳过，集合就无声少一枚，它名下的账从此不在射程里，每一枚在册钉照样全绿；反过来把原文直接"
            "端上去，报的是那条不带文件名的原文——不点名是哪枚文件，别人的一枚手抖就被读成一次回归。"
            "先修文件再复跑，逐枚点名 文件/行/列/原文/错误：\n  %s\n判据落点 %s，机理与两趟对照读数 %s"
            % (len(failures), "\n  ".join(failures), RANGE_PIN, RANGE_PAPER))
    assert set(parsed) == set(texts), (
        "严格解析口径自己缩集了：输入面 %d 枚、交回 %d 枚，缺 %s"
        % (len(texts), len(parsed), sorted(set(texts) - set(parsed))))
    return parsed


def assert_covers_the_range(surface_keys, scope=None, where: str = "") -> dict:
    """「集合少一枚」的守卫：射程内每一枚都必须在这枚输入面上，缺哪枚点名哪枚。

    空集守卫（``assert handles`` 那一族）只在射程塌成零枚时红；从 640 枚缩到 639 枚它一路绿。这里按
    逐枚差集判，缺谁点谁，并把 ``where``（哪一枚派生者交回的面）写进红字，让接手的人知道该修哪条腿。
    """
    expected = set(in_range_test_rels() if scope is None else scope)
    have = set(surface_keys)
    missing = sorted(expected - have)
    extra = sorted(have - expected)
    assert not missing, (
        "%s 交回的射程内输入面少了 %d 枚（R589 判据①：静默缩集）：缺 %s（面 %d 枚 vs 射程 %d 枚）"
        % (where or "输入面", len(missing), ", ".join(missing), len(have), len(expected)))
    return {"surface": len(have), "scope": len(expected), "missing": tuple(missing),
            "extra": tuple(extra)}


def module_of(rel: str):
    """盘上那枚 ``.py`` 对应的**已导入**模块对象；不是 .py 或还没导入就是 None。"""
    if not rel.endswith(".py"):
        return None
    return sys.modules.get(rel[:-3].replace("/", "."))


def isolated_module(module, text: str, filename):
    """把一份字节 exec 进一枚**新造**的模块对象：整份码体照跑，但活模块一个名字都不换。

    来历（R556 判据① 的原证面）：r478 那把刀落在 Pydantic 模型类里，而 ``description`` 是在**类创建
    那一刻**烘进 JSON schema 的——只换那一枚类绑定，活路由上那条端点仍指着旧类，发布的文档就还是旧句，
    刀就迁成了空转（比不迁更坏）。正例姿势在 ``tests/test_r457_audit_retention_execution_leg.py``：
    要跑变异就把它装进一枚隔离对象。这里给同一族姿势一个把手：新模块的 ``__dict__`` 以活模块当前那份
    起头（窗内夹具替身照样看得见），被跟踪文件与活模块都不开口。
    """
    fresh = ModuleType(getattr(module, "__name__", "r556-isolated"))
    fresh.__dict__.update(module.__dict__)
    exec(compile(text, str(filename), "exec"), fresh.__dict__)
    return fresh


def install_source(module, text: str, filename) -> None:
    """把一份字节 exec 进**现有**模块对象的 ``__dict__``。

    ``importlib.reload`` 也不换模块身份（它在同一个 ``__dict__`` 上重跑码体），所以这里与它同形：
    凡是 ``from app.api.v1 import chat`` 的旧绑定一起看到新码，退出时再 exec 回盘上的字。
    ``co_filename`` 沿用被跟踪文件的路径，报错原文里的行列号与今天逐字同形。
    """
    exec(compile(text, str(filename), "exec"), module.__dict__)


def restore_namespace(module, snapshot: dict) -> list:
    """把一扇窗进门那一刻的活模块**按对象身份**装回去：该在的一枚不少，多出来的摘掉。

    来历（R553 乙腿）：旧口径的窗尾是「再 exec 一遍盘上的字」。那一手救不回身份——
    码体重跑会**再造**每一枚顶层类与每一行顶层初始化，于是
      · ``type(chat.session_registry)`` 与模块属性上的 ``SessionRegistry`` 分成两枚类，
      · 模块属性上的注册表与 ``chat`` 手里那一枚分成两枚实例，
    门里三枚红（`tests/test_r499_..._any_file_order.py` 三门连红），报的是
    ``assert X is X`` 却为假——两枚同名同模块的东西。窗尾那次 exec 只会再造第三枚，越救越远。
    🔴 也不许改成「把新身体逐枚装进旧类」：零参 ``super()`` 读的是码体里那个 ``__class__`` 格，
    把新类的方法定进旧类，第一次 ``super()`` 就 ``TypeError: super(type, obj): obj must be...``
    （本席 10-01 第一版就这么把门跑成 109 枚红，两枚在册件当场点名）。
    这里根本不再 exec：窗尾只是把命名空间倒回进门那一刻，身份与值都还是原来那些对象。
    """
    live = module.__dict__
    for name in [k for k in list(live) if k not in snapshot]:
        live.pop(name, None)          # 变异码体新造出来的名字：整片摘掉，不留影子
    diverged = [name for name, value in snapshot.items() if live.get(name) is not value]
    live.update(snapshot)
    return diverged


class EditInfo(dict):
    """``with _TempEdit(...) as info`` 交回去的东西：sha 凭据 + 影子副本的读取把手。

    ``before`` / ``after`` / ``restored`` 沿用旧名，调用方的收尾断言一个字不用改；今天这三格
    量的是**被跟踪文件**在全程只读下的 sha 恒定性，比旧口径（我自己改过再还原）更强一格。
    ``read_bytes()`` 是新的：窗内要读变异版，只能读影子副本。
    """

    def __init__(self, tracked: Path) -> None:
        super().__init__()
        self.tracked = tracked
        self.rel = rel_of(tracked)

    @property
    def path(self) -> Path:
        return SHADOW.root / self.rel

    @property
    def name(self) -> str:
        return self.tracked.name

    def read_bytes(self) -> bytes:
        return SHADOW.read_bytes(self.rel)

    def read_text(self) -> str:
        return self.read_bytes().decode("utf-8")


class ShadowEdit:
    """一扇反证窗的公共骨架：读盘上的字 -> 只在影子副本上落变异 -> 退出即还原视图。

    子类只负责讲清「变异是什么」（``mutate``）。锚点唯一性与报错原文留在子类里，那是判据 ③。
    """

    #: 日志前缀：各件沿用自己那枚单号，别把 [r48] 的读数改记成 [r253]。
    tag = "r253"
    #: 窗内要不要把变异字节 exec 进同名模块（只有真会跑码的那几枚反证需要）。
    execs_module = False

    def __init__(self, path) -> None:
        self.path = Path(path)
        self.rel = rel_of(self.path)
        self.info = EditInfo(self.path)
        self._live_snapshot: dict = {}

    def mutate(self, text: str) -> str:
        raise NotImplementedError

    def _module(self):
        return module_of(self.rel) if self.execs_module else None

    def __enter__(self) -> EditInfo:
        if self.rel in _WINDOWS:
            raise AssertionError("%s 上已经有一扇反证窗：影子根不许嵌套" % self.rel)
        raw = self.path.read_bytes().decode("utf-8")             # 只读
        self.info["before"] = sha16_of_bytes(raw.encode("utf-8"))
        edited = self.mutate(raw)
        assert edited != raw
        SHADOW.ensure(self.rel)                                 # 基线取盘上的字
        SHADOW.write(self.rel, edited.encode("utf-8"))          # 变异只落在这里
        _WINDOWS.append(self.rel)
        module = self._module()
        if module is not None:
            self._live_snapshot = dict(module.__dict__)      # R553：窗尾按这一张倒回，不再重跑码体
            install_source(module, edited, self.path)
        return self.info

    def __exit__(self, *_exc) -> bool:
        module = self._module()
        if module is not None:
            diverged = restore_namespace(module, self._live_snapshot)
            self.info["identity_diverged"] = sorted(diverged)
        if self.rel in _WINDOWS:
            _WINDOWS.remove(self.rel)
        SHADOW.ensure(self.rel)
        tracked = self.path.read_bytes()                        # 只读核对
        after = sha16_of_bytes(tracked)
        self.info["after"] = after
        self.info["restored"] = after == self.info["before"]
        self.info["shadow_clean"] = SHADOW.read_bytes(self.rel) == tracked
        assert self.info["shadow_clean"], "影子副本没回到盘上的字：%s" % self.rel
        print("[%s] %s %s -> %s restored=%s tracked-file-untouched" % (
            self.tag, self.path.name, self.info["before"], after, self.info["restored"]))
        return False
