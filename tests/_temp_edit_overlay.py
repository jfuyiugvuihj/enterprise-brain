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
    ``__dict__``（``importlib.reload`` 本来也不换模块身份），退出时再 exec 回盘上的字。
  · 每扇窗进门都从盘上重取基线，所以崩在半路也不会把变异漏给下一扇窗。

判据 ③ 的分工：这里搬走的只有「变异往哪儿落」，没有「变异是什么」。锚点、替换文本、还原核对、
报错原文的措辞全部留在调用方那两枚 ``_TempEdit`` 子类里——摘掉守卫会红的那一格，改完还在同一格红。
"""
from __future__ import annotations

import ast
import atexit
import weakref
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

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


def module_of(rel: str):
    """盘上那枚 ``.py`` 对应的**已导入**模块对象；不是 .py 或还没导入就是 None。"""
    if not rel.endswith(".py"):
        return None
    return sys.modules.get(rel[:-3].replace("/", "."))


def _reuse_class_identities(namespace: dict, before: dict) -> list:
    """把重跑码体时新长出来的顶层类换回**同一枚类对象**：身体换新，身份不换。

    来历（R553 乙腿）：一枚 ``execs_module = True`` 的反证窗重跑整份码体，于是每一枚顶层类都是
    **新对象**，而场上早就存在的单例实例仍指着旧类 —— 盘上那行 ``session_registry = SessionRegistry()``
    只在导入那一刻跑过一次。结果是模块属性上的 ``SessionRegistry`` 与 ``type(chat.session_registry)``
    从此是两枚类，任何按类身份作保的件（``tests/test_r499_..._any_file_order.py`` 三门连红）排在
    别人之后就当场红；窗尾那一次 exec 只会再造第三枚类，救不回来。这里把新身体逐枚装进旧类，
    并把模块属性指回旧类：变异照样被执行（身体是新的），身份不再漂。

    🔴 只在「同一枚类的重跑」上做：元类或基类换了就不是重跑，那种形状一律跳过 —— 宁可留着旧口径
    的换身份，也不伪造一枚挂着旧名的假类。

    交回 ``{新类对象: 旧类对象}``：紧跟着的实例还原要靠它认出「这一枚实例是刚被换掉的那枚类的
    又一个产物」——那一枚新类已经不存在于模块属性上了，`type(new) is type(old)` 结构上不可能成立。
    """
    reused = []
    class_map = {}
    for name, old in list(before.items()):
        if not isinstance(old, type):
            continue
        new = namespace.get(name)
        if not isinstance(new, type) or new is old:
            continue
        if type(new) is not type(old) or new.__bases__ != old.__bases__:
            continue
        dropped = sorted(set(vars(old)) - set(vars(new)))
        for attr, value in list(vars(new).items()):
            if attr in ("__dict__", "__weakref__"):
                continue
            setattr(old, attr, value)
        for attr in dropped:
            if attr in ("__dict__", "__weakref__"):
                continue
            try:
                delattr(old, attr)
            except (AttributeError, TypeError):
                pass
        namespace[name] = old
        reused.append(name)
        class_map[new] = old
    return class_map


def _top_level_assignments(source: str) -> dict:
    """``{名字: 那一行赋值的源码}``——只认顶层 `Name = ...` 与带注解的赋值。"""
    out = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = ast.unparse(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = ast.unparse(node)
    return out


def _reuse_live_instances(namespace: dict, before: dict, previous_text: str, text: str,
                         class_map: dict) -> list:
    """把「赋值那行源码一字没改」的模块级实例换回场上那一枚：重跑同一行初始化换的是身份，不是值。

    来历（R553 乙腿第二格）：反证窗重跑码体时，顶层那行 ``session_registry = SessionRegistry()``
    会再造一枚实例并把模块属性指过去，而 ``chat.py`` 里 ``from app.storage.sessions import
    session_registry`` 的旧绑定仍指着场上那一枚 ⇒ 两处读数从此不是同一个对象
    （门里现取：``registry is session_storage.session_registry`` 红）。这里只在**源码没变**时留旧对象：
    那意味着这一行重跑只是机械地又 new 了一枚同形的东西，身份才是被弄坏的那一格。
    🔴 源码变了就绝不插手——那一行可能正是刀要执行的东西，替它留着旧值就是造一枚假绿。
    """
    if not previous_text:
        return []
    before_assigns = _top_level_assignments(previous_text)
    after_assigns = _top_level_assignments(text)
    reused = []
    for name, old in list(before.items()):
        if isinstance(old, type) or callable(old):
            continue                      # 类由 _reuse_class_identities 管，函数与常量不该动
        if name not in after_assigns or after_assigns.get(name) != before_assigns.get(name):
            continue                      # 赋值行变了（或本就不是赋值来的）：这一格不归本函数插手
        new = namespace.get(name)
        if new is None or new is old or class_map.get(type(new)) is not type(old):
            continue                      # 不是「同一枚类又被 new 了一个」：可能是别人造的，别插手
        namespace[name] = old
        reused.append(name)
    return reused


def previous_source(module) -> str:
    """这枚模块**上一次**跑的字节：窗内 exec 过变异版就取变异版，从没 exec 过就取盘上的字。

    身份还原需要的是「场上那些对象由哪份码造出来」，不是「盘上现在是什么」——
    窗尾那一次重跑，对照文本必须是影子副本的变异版，否则会把「赋值行本来就变了」那一格误判成没变。
    """
    recorded = _INSTALLED.get(module)
    if recorded:
        return recorded
    try:
        path = Path(str(getattr(module, "__file__", "") or ""))
    except OSError:
        return ""
    if not path.is_file():
        return ""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


#: 每枚被本件重跑过码体的模块：它上一次实际执行的是哪一份字节。
_INSTALLED = weakref.WeakKeyDictionary()


def install_source(module, text: str, filename) -> None:
    """把一份字节 exec 进**现有**模块对象的 ``__dict__``。

    ``importlib.reload`` 也不换模块身份（它在同一个 ``__dict__`` 上重跑码体），所以这里与它同形：
    凡是 ``from app.api.v1 import chat`` 的旧绑定一起看到新码，退出时再 exec 回盘上的字。
    ``co_filename`` 沿用被跟踪文件的路径，报错原文里的行列号与今天逐字同形。
    顶层类的身份由 ``_reuse_class_identities`` 保住（R553 乙腿）：重跑码体不许把场上已有的单例
    变成「上一枚类的孤儿实例」。
    """
    before = dict(module.__dict__)
    previous_text = previous_source(module)
    exec(compile(text, str(filename), "exec"), module.__dict__)
    class_map = _reuse_class_identities(module.__dict__, before)
    _reuse_live_instances(module.__dict__, before, previous_text, text, class_map)
    try:
        _INSTALLED[module] = text
    except TypeError:      # 不是可弱引用的模块对象：记不上就只影响下一扇窗的对照文本，不假装成功
        pass


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
            install_source(module, edited, self.path)
        return self.info

    def __exit__(self, *_exc) -> bool:
        module = self._module()
        if module is not None:
            install_source(module, self.path.read_bytes().decode("utf-8"), self.path)
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
