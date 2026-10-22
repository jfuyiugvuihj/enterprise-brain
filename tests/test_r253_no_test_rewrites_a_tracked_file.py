# -*- coding: utf-8 -*-
r"""R253 判据 ②：闭合钉——全仓扫描「在测试运行期间就地改写被跟踪文件」的形态，必须 0 处。

为什么是静态扫描而不是运行期取证：审计钩子只能看见**装上之后**同进程里的写口，而
``-n 8 --dist loadfile`` 下每枚 worker 各起各的、文件落到哪枚 worker 由分发决定——一枚装在
``test_r253_*`` 里的钩子永远看不见更早跑完的那批件。所以形态级的闭合只能用「读源码」：
它不看负载、不看次序，新长出一处就地改写就当场红。运行期那一半在
``tests/test_r253_shadow_root_holds_the_mutation.py``：它拿审计钩子盯住影子根自己开没开写口。

扫描口径（判据 ① 搬完之后剩下的那枚不变量）：

  · 起点是**被跟踪文件**，而且只认**从仓根长出来**的路径：``REPO / "app" / ...``、
    ``Path(__file__).resolve().parents[1]`` 那一族、以及它们的名字别名。一串相对字面量当**后缀**
    拼到 tmp 副本根下面（R218 那三件今天就这么写：``root / "app/api/v1/chat.py"``）不算点名盘上
    那枚——把它判红就是本单要根治的那类假红，所以另有两枚静默用例守着这一格；
  · 污染源只沿**路径形状**走（``A / "b"``、``Path(A)``、``os.path.join(...)``、直接改名赋值），
    并且**分作用域**：把 ``CHAT_PY`` 交给某枚 helper 的实参，只有那位 helper 自己的形参脏，
    别处同名的局部不许连坐。这一格是实测逼出来的：全仓有 ``_text(CONTRACT)`` 与
    ``write_jsonl(tmp_path / "x.jsonl")`` 两串同名局部，不分作用域就会报出一片假红；
  · helper 里 ``self.path = path`` 之后，``self.path`` 也脏——施工前那枚 ``_TempEdit``
    （构造器收路径、``__enter__`` 里 ``self.path.write_bytes``）正是这副形状，合成源码那格
    把它原样端上来判红；
  · 终点是**写口**：``write_text`` / ``write_bytes`` / ``touch`` / ``truncate`` / ``unlink`` /
    ``mkdir`` / ``rmdir`` / ``Path.open("w|a|x|+")`` / ``open(...)`` / ``os.remove`` 一族 /
    ``shutil.copyfile`` 一族（复制与搬运取落点）；写口的目标是一枚**相对字面量**也算一处，
    因为 pytest 的 cwd 就是仓根。

盲区（明写，不装没有）：移动删除族只认 ``os.`` / ``shutil.`` 前缀——``str.replace`` 与
``Path.replace`` 同名，按接收者判会把全仓的文本替换读成写盘。跨件的路径传递（把被跟踪文件交给
另一枚件里的 helper 去写）也看不见：本件的扫描范围是单文件。运行期那半边由审计钩子补。

R572 改口（跟进单 §151 三·判据③）：本件末尾那枚引用者钉原来把**旧姿势的把手名**写成字面量
（``"_TempEdit(" in source``），等于手抄第二份真源。``c9a782e``（R556）把
``tests/test_r48_headline_never_enters_the_text_ledger.py`` 迁进 ``r466.install_mutation``
之后，那枚在册钉的反证件与变异本体一枚都没少，只是换了把手名，于是引用者钉把它判成红。
今天把手名沿 AST 从两枚真源派生（窗骨架 ＋ 装变异那一腿）：派生不到 ⇒ 红，射程内的件不再调用
任何一枚派生把手 ⇒ 红。扫描口径本身一枚没放宽——它判的是写口，本节判的是把手。"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO / "tests"

#: 仓根的常见写法：件里把这些当基座往上拼路径。
ROOT_TOKENS = {"REPO", "ROOT", "REPO_ROOT", "_REPOSITORY"}
ROOT_PATTERNS = (
    "Path(__file__).resolve().parents[1]",
    "Path(__file__).parents[1]",
    "os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
)

#: 被写的那条路径就是接收者的写口。
RECEIVER_WRITES = {"write_text", "write_bytes", "touch", "truncate", "unlink", "mkdir", "rmdir"}
#: 带模块前缀的删除/移动族：目标分别是第一枚与第二枚实参。
OS_FIRST = {"remove", "unlink", "rmdir", "removedirs", "makedirs", "mkdir"}
OS_SECOND = {"replace", "rename"}
#: 复制与搬运族：目标是最后一枚实参。
COPY_LAST = {"copyfile", "copy", "copy2", "move", "copytree"}
MODULES = {"os", "shutil", "pathlib"}
WRITE_MODES = set("wax+")


def tracked_files() -> frozenset:
    """``git ls-files`` 的全部被跟踪文件（posix 相对路径）：污染源只从这里长出来。"""
    out = subprocess.run(["git", "ls-files"], cwd=str(REPO), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert out.returncode == 0, out.stderr
    return frozenset(line.strip().replace("\\", "/") for line in out.stdout.splitlines()
                     if line.strip())


def _callee_name(node: ast.Call):
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _qualified(node: ast.Call):
    """``os.remove`` 这一族的模块前缀。"""
    fn = node.func
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in MODULES:
        return fn.value.id, fn.attr
    return None


def _write_target(node: ast.Call):
    """这枚调用是写口吗？是就交出「被写到的那条路径」的表达式节点。"""
    fn = node.func
    name = _callee_name(node)
    if name is None:
        return None
    qualified = _qualified(node)
    if qualified:
        module, attr = qualified
        if module == "os" and attr in OS_FIRST and node.args:
            return node.args[0]
        if module == "os" and attr in OS_SECOND and len(node.args) >= 2:
            return node.args[1]
        if module == "shutil" and attr in COPY_LAST and node.args:
            return node.args[-1]
        return None
    if isinstance(fn, ast.Attribute) and fn.attr in RECEIVER_WRITES:
        return fn.value
    if name == "open":
        mode = node.args[1] if len(node.args) > 1 else None
        if mode is None:
            mode = next((k.value for k in node.keywords if k.arg == "mode"), None)
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str) \
                and WRITE_MODES & set(mode.value):
            if node.args:
                return node.args[0]
            return fn.value if isinstance(fn, ast.Attribute) else None
    return None


def _resolve(node, names: dict, rooted: frozenset):
    """把一枚表达式算成 (仓内相对路径, 它是不是从仓根长出来的)；算不动就是 (None, False)。

    「算不动就放过」是故意的：这枚钉红一次就要停一轮并树，误判的代价比漏判高——漏判那一侧
    还有运行期的审计钩子与另两枚件的窗口内 sha 恒等断言顶着。
    """
    text = ast.unparse(node)
    for pattern in ROOT_PATTERNS:
        if text.endswith(pattern):
            return "", True
    if isinstance(node, ast.Name):
        if node.id in ROOT_TOKENS:
            return "", True
        if node.id in names:
            return names[node.id], node.id in rooted
        return None, False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.replace("\\", "/").strip("/"), False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, left_rooted = _resolve(node.left, names, rooted)
        right, _right_rooted = _resolve(node.right, names, rooted)
        if left is None or right is None:
            return None, False
        if not left:
            return right or None, left_rooted
        return (left + "/" + right).strip("/"), left_rooted
    if isinstance(node, ast.Call):
        callee = _callee_name(node)
        if callee == "Path" and node.args:
            return _resolve(node.args[0], names, rooted)
        if callee in ("resolve", "absolute") and isinstance(node.func, ast.Attribute):
            return _resolve(node.func.value, names, rooted)
        if callee == "join" and node.args:
            rows = []
            base_rooted = False
            for index, arg in enumerate(node.args):
                rel, is_rooted = _resolve(arg, names, rooted) if not isinstance(arg, ast.Starred) \
                    else (None, False)
                if rel is None:
                    return None, False
                if index == 0:
                    base_rooted = is_rooted
                rows.append(rel.strip("/"))
            out = ""
            for row in rows:
                out = (out + "/" + row).strip("/") if out else row
            return out or None, base_rooted
    return None, False


def _flat_paths(tree: ast.AST):
    """本文件里能被算成相对路径的名字 -> (路径, 是否仓根出身)：链式定义迭代到定点。"""
    names: dict = {}
    rooted: set = set()
    for _ in range(3):
        grew = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                rel, is_rooted = _resolve(node.value, names, rooted)
                if rel is None:
                    continue
                if names.get(target.id) != rel or (target.id in rooted) != is_rooted:
                    names[target.id] = rel
                    rooted.add(target.id) if is_rooted else rooted.discard(target.id)
                    grew = True
        if not grew:
            break
    return names, frozenset(rooted)


def _operands(node):
    """路径形状的可拼部件：只有这几类写法是「在拼一条路径」。"""
    if isinstance(node, (ast.Name, ast.Attribute, ast.Constant)):
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [node.left, node.right]
    if isinstance(node, ast.Call) and _callee_name(node) in ("Path", "join") and node.args:
        return [a for a in node.args if not isinstance(a, ast.Starred)]
    return None


def _scope_map(tree: ast.AST) -> dict:
    """每枚节点最近的可调用祖先（None = 模块层）。"""
    owner: dict = {}

    def visit(node, current):
        for child in ast.iter_child_nodes(node):
            nxt = id(child) if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                else current
            owner[id(child)] = nxt
            visit(child, nxt)

    visit(tree, None)
    return owner


def _params(node) -> list:
    arglist = list(node.args.posonlyargs) + list(node.args.args)
    if arglist and arglist[0].arg == "self":
        arglist = arglist[1:]
    return [a.arg for a in arglist]


def _callables(tree: ast.AST) -> dict:
    """本文件的函数/方法：类名映射到它自己的 ``__init__``（``_TempEdit(CONTRACT, ...)`` 走这格）。"""
    found: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, []).append(node)
        elif isinstance(node, ast.ClassDef):
            init = next((s for s in node.body
                         if isinstance(s, ast.FunctionDef) and s.name == "__init__"), None)
            if init is not None:
                found.setdefault(node.name, []).append(init)
    return found


def scan_source(source: str, tracked: frozenset, label: str = "<source>") -> list:
    """一件测试的源码 -> 「就地改写被跟踪文件」的站点清单；空表就是判据 ② 要的读数。"""
    tree = ast.parse(source)
    flat, rooted = _flat_paths(tree)
    owner = _scope_map(tree)
    callables = _callables(tree)
    dirty: dict = {}        # (作用域, 名字) -> 来历
    attrs: dict = {}        # self.<attr> 上接住的路径 -> 来历

    def origin(node, scope):
        """这枚表达式此刻是不是一条指着被跟踪文件的路径？是就交出它的来历。"""
        parts = _operands(node)
        if parts is None:                     # 不是路径形状：交出的不会是路径
            return None
        rel, is_rooted = _resolve(node, flat, rooted)
        if is_rooted and rel is not None and rel in tracked:
            return "直接点名被跟踪文件 %s" % rel
        if isinstance(node, ast.Name):
            return dirty.get((scope, node.id)) or dirty.get((None, node.id))
        if isinstance(node, ast.Attribute):
            return attrs.get(node.attr)
        for part in parts:
            if isinstance(part, ast.Constant):
                continue                # 它是拼在别人身上的后缀，不算点名盘上那枚
            found = origin(part, scope)
            if found:
                return found
        return None

    for name, rel in flat.items():
        if rel in tracked and name in rooted:
            dirty[(None, name)] = "%s -> %s" % (name, rel)
    for _ in range(5):                        # 定点：实参进形参，形参再进 self.attr 与局部名
        grew = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _callee_name(node) in callables:
                callee = _callee_name(node)
                here = owner.get(id(node))
                bound: dict = {}
                for index, arg in enumerate(node.args):
                    for fn in callables[callee]:
                        params = _params(fn)
                        if index < len(params):
                            bound.setdefault(params[index], arg)
                for kw in node.keywords:
                    for fn in callables[callee]:
                        if kw.arg in _params(fn):
                            bound.setdefault(kw.arg, kw.value)
                for param, arg in bound.items():
                    found = origin(arg, here)
                    if not found:
                        continue
                    for fn in callables[callee]:
                        if param in _params(fn) and (id(fn), param) not in dirty:
                            dirty[(id(fn), param)] = "%s 的形参（实参里 %s）" % (callee, found)
                            grew = True
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                found = origin(node.value, owner.get(id(node)))
                if not found:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        here = owner.get(id(node))
                        if (here, target.id) not in dirty:
                            dirty[(here, target.id)] = found
                            grew = True
                    elif isinstance(target, ast.Attribute) and target.attr not in attrs:
                        attrs[target.attr] = "%s 接住 %s" % (ast.unparse(target), found)
                        grew = True
        if not grew:
            break
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _write_target(node)
        if target is None:
            continue
        kind = _callee_name(node)
        text = ast.unparse(target)
        found = origin(target, owner.get(id(node)))
        if not found:
            # 相对字面量单独判：pytest 的 cwd 就是仓根，open("app/api/v1/chat.py", "wb") 是真写盘。
            rel, _rooted = _resolve(target, {}, frozenset())
            if isinstance(target, ast.Constant) and rel in tracked:
                found = "写口直接落在相对路径 %s" % rel
        if not found:
            continue
        write = "%s(%s)" % (kind, text) if kind == "open" else "%s.%s()" % (text, kind)
        findings.append({"label": label, "line": node.lineno, "write": write, "source": found})
    return sorted(findings, key=lambda item: item["line"])


def scan_suite(tracked: frozenset) -> list:
    """``tests/**.py`` 全部扫一遍：判据 ② 要的就是这张表空着。"""
    findings = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        findings += scan_source(path.read_text(encoding="utf-8"), tracked,
                                label="tests/" + path.relative_to(TESTS_DIR).as_posix())
    return findings


# ==================== 合成源码：这枚扫描器到底咬不咬 ====================

#: 坏形状一：名字直接落在被跟踪文件上，就地 ``write_text``。
DIRECT_FORM = """
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
CHAT = REPO / "app" / "api" / "v1" / "chat.py"


def mutate():
    CHAT.write_text("x", encoding="utf-8")
"""

#: 坏形状二：施工前 ``_TempEdit`` 的原样——路径从构造器进，``self.path`` 上写盘。
HELPER_FORM = """
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"


class _TempEdit:
    def __init__(self, path, edits):
        self.path = path
        self.edits = edits

    def __enter__(self):
        raw = self.path.read_bytes().decode("utf-8")
        self.path.write_bytes(raw.replace("a", "b").encode("utf-8"))
        return raw


with _TempEdit(CONTRACT, []) as info:
    pass
"""

#: 坏形状三：绕过 ``Path.write_*``，直接开一枚写模式的句柄（相对字面量，cwd 就是仓根）。
OPEN_FORM = """
with open("app/api/v1/chat.py", "wb") as handle:
    pass
"""

#: 坏形状四：路径换个名字接着走——``os.replace`` 的落点是被跟踪文件。
MOVE_FORM = """
import os
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "docs" / "api" / "contract-v1.md"

os.replace(Path("C:/outside/stage.md"), TARGET)
"""

#: 好形状一：判据 ① 搬完之后剩下的样子——路径照样从构造器进，但变异只落副本。
SHADOW_FORM = """
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
OVERLAY = Path("C:/outside/the/repo/contract-v1.md")


class ShadowEdit:
    def __init__(self, path):
        self.rel = str(path)

    def __enter__(self):
        OVERLAY.write_bytes(CONTRACT.read_bytes())
        return OVERLAY


with ShadowEdit(CONTRACT) as info:
    pass
"""

#: 好形状二：R218 那三件的样子——把被跟踪文件的名字当**后缀**拼到 tmp 副本根下面。
OVERLAY_SUFFIX_FORM = """
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
TARGET = "scripts/rehearse_eval_window.py"


def stage(tmp_root):
    root = tmp_root / "overlay"
    copy = root / TARGET
    copy.write_text("mutated", encoding="utf-8")
    return copy
"""


def test_the_scanner_flags_a_direct_write_on_a_tracked_file():
    findings = scan_source(DIRECT_FORM, tracked_files())
    assert len(findings) == 1, findings
    assert findings[0]["write"].startswith("CHAT.write_text"), findings


def test_the_scanner_flags_the_pre_r253_tempedit_shape():
    """反证：把施工前那枚 ``_TempEdit`` 原样端上来——它必须仍然是一处，否则这枚闭合钉是空的。"""
    findings = scan_source(HELPER_FORM, tracked_files())
    assert len(findings) == 1, findings
    assert findings[0]["write"].startswith("self.path.write_bytes"), findings
    assert "docs/api/contract-v1.md" in findings[0]["source"], findings


def test_the_scanner_flags_a_write_mode_handle_on_a_tracked_relative_path():
    findings = scan_source(OPEN_FORM, tracked_files())
    assert len(findings) == 1, findings
    assert findings[0]["write"].startswith("open"), findings
    assert "app/api/v1/chat.py" in findings[0]["source"], findings


def test_the_scanner_flags_a_move_onto_a_tracked_file():
    findings = scan_source(MOVE_FORM, tracked_files())
    assert len(findings) == 1, findings
    assert findings[0]["write"].startswith("TARGET.replace"), findings


def test_the_scanner_stays_silent_on_the_shadow_shape_it_exists_to_allow():
    """同一枚构造器形状，写口落在副本上就是 0 处：这格拦的是「把判据 ② 做成一刀切」。"""
    assert scan_source(SHADOW_FORM, tracked_files()) == []


def test_the_scanner_stays_silent_when_the_tracked_name_is_only_a_suffix():
    """R218 那三件的写法今天就在仓里：后缀同名不等于指着盘上那枚，判红就是新的假红。"""
    assert scan_source(OVERLAY_SUFFIX_FORM, tracked_files()) == []


# ==================== 判据 ②：全仓 0 处 ====================


def test_the_suite_has_enough_write_points_for_the_scanner_to_see():
    """0 处的前提是扫描器真认得写口：全仓 tmp/overlay 里的写口数量本身就是非空转读数。"""
    total = 0
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(1 for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and _write_target(node) is not None)
    # 下限贴着现量（实测 303 枚）：写口认少了一半就说明扫描器瞎了，那 0 处不算数。
    assert total >= 200, "整仓只认到 %d 枚写口：扫描器读不到东西，那 0 处不算数" % total


def test_no_test_rewrites_a_tracked_file_in_place():
    """判据 ②：全仓扫描「在运行期间就地改写被跟踪文件」的形态——今天必须 0 处。"""
    tracked = tracked_files()
    assert tracked, "git ls-files 交回空集：这枚判据没被测到"
    files = [p for p in sorted(TESTS_DIR.rglob("*.py")) if "__pycache__" not in p.parts]
    # 下限贴着现量（实测 346 枚件、984 枚被跟踪文件）：范围缩水就等于没扫。
    assert len(files) >= 300, "只扫到 %d 枚件：扫描范围缩水了，0 处不算数" % len(files)
    assert len(tracked) >= 900, "git ls-files 只报 %d 枚被跟踪文件：口径缩水了" % len(tracked)
    findings = scan_suite(tracked)
    assert not findings, "这些件在运行期间就地改写被跟踪文件（只许改副本或进程内 monkeypatch）：\n  " \
        + "\n  ".join("%(label)s:%(line)d  %(write)s  （%(source)s）" % item for item in findings)


# ==================== 判据 ③（R572 改口）：把手名从真源派生，不抄旧姿势的名字 ====================
#
# 本节替掉的是本件末尾那枚引用者钉的判法。旧写法把**已过时的姿势名**写成字面量
# （``assert "_TempEdit(" in source``）＝手抄第二份真源：``c9a782e``（R556）把
# ``tests/test_r48_headline_never_enters_the_text_ledger.py`` 迁进 ``r466.install_mutation``
# 之后，那枚在册钉的反证件与变异本体一枚都没少，只是换了把手名，于是引用者钉把一枚**有牙的**
# 钉判成红（跟进单 §151 三·症状①）。今天名字沿 AST 从两枚真源派生：派生源被摘空 ⇒ 红，
# 射程内的件不再调用任何一枚派生把手 ⇒ 红。两格都有反证，见
# ``tests/test_r572_window_handles_are_derived_not_transcribed.py``。

#: 派生源一：影子窗骨架。它交回的公开「上下文管理器类」＝一扇窗的样子（``ShadowEdit``）。
SOURCE_OF_WINDOW_BASES = "tests/_temp_edit_overlay.py"
#: 派生源二：R556 的姿势件。它交回的公开 ``@contextmanager`` ＝把变异装进活模块那一腿
#: （``install_mutation``）——旧姿势的 ``execs_module`` 今天不许再当判据。
SOURCE_OF_POSTURE_HANDLES = "tests/test_r466_mutation_does_not_leak_into_live_module.py"

#: 引用者钉的射程：三枚件与各自的反证件名下限。下限一枚都不许随改口蒸发。
COUNTER_PROOF_HOMES = {
    "tests/test_r156_sse_event_surface_sync.py": 5,
    "tests/test_r48_headline_card_lands_on_the_wire.py": 3,
    "tests/test_r48_headline_never_enters_the_text_ledger.py": 1,
}


def _top_level_defs(tree: ast.AST) -> list:
    """一件**顶层**的类与函数：派生把手名只看顶层，局部函数与串里的同名都不算。"""
    return [node for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]


def _callee_tail(node):
    """``_TempEdit(...)`` 与 ``r466.install_mutation(...)`` 共用的那枚尾名。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _has_dunder(node, name: str) -> bool:
    """顶层类体里有没有一枚叫 ``name`` 的方法：骨架的「是不是一扇窗」就按这两格认。"""
    return any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
               for item in getattr(node, "body", []))


def _opens_a_window(node, handles: frozenset) -> bool:
    """这枚顶层函数体内有没有 ``with <已认把手>(...)``：包装把手就是这么认出来的。"""
    for item_node in ast.walk(node):
        if not isinstance(item_node, (ast.With, ast.AsyncWith)):
            continue
        for with_item in item_node.items:
            expr = with_item.context_expr
            if isinstance(expr, ast.Call) and _callee_tail(expr.func) in handles:
                return True
    return False


def parse_sources(texts: dict) -> dict:
    """rel -> 文本 的合成输入面 -> rel -> (文本, 已解析 AST)。

    反证拿它喂**同一枚**派生与**同一枚**判据：盘上一字节不动，摘的只是输入。
    """
    return {rel: (text, ast.parse(text)) for rel, text in texts.items()}


def suite_sources() -> dict:
    """``tests/**.py`` 的 rel -> (文本, AST)：派生把手名的原料，也是反证可整体换掉的输入面。"""
    texts = {}
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        texts["tests/" + path.relative_to(TESTS_DIR).as_posix()] = path.read_text(encoding="utf-8")
    return parse_sources(texts)


def window_handles(sources: dict) -> frozenset:
    """在册反证窗的把手名——沿 AST 从两枚真源闭包派生，不抄名单：

      ① ``SOURCE_OF_WINDOW_BASES`` 交回的公开上下文管理器类（窗骨架）；
      ② ``SOURCE_OF_POSTURE_HANDLES`` 交回的公开 ``@contextmanager``（装变异那一腿）；
      ③ 闭包两路：继承已认骨架的顶层**类**（各件自己那枚 ``_TempEdit``），以及体内 ``with``
         调到已认把手的顶层**函数**（``_chat_window``／``_open_r48`` 这一族包装把手）。
         名叫 ``test_*`` 的顶层函数不进闭包：用例本体开的是窗，它本身不是把手——不收这一口，
         把手集合就会被两百多枚用例名灌满，「派生不到」那格判的就不是它要判的东西。

    🔴 两枚真源都不在场就交回空集：引用者钉拿空集必须红，不许退回手抄一份名字表。
    """
    handles: set = set()
    skeleton = sources.get(SOURCE_OF_WINDOW_BASES)
    if skeleton is not None:
        handles |= {node.name for node in _top_level_defs(skeleton[1])
                    if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
                    and _has_dunder(node, "__enter__") and _has_dunder(node, "__exit__")}
    posture = sources.get(SOURCE_OF_POSTURE_HANDLES)
    if posture is not None:
        handles |= {node.name for node in _top_level_defs(posture[1])
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not node.name.startswith("_")
                    and any(_callee_tail(dec) == "contextmanager" for dec in node.decorator_list)}
    for _ in range(4):                          # 定点：包装把手还能被别的包装把手再套一层
        grew = False
        for _text, tree in sources.values():
            for node in _top_level_defs(tree):
                if node.name in handles or node.name.startswith("test"):
                    continue        # 用例本体不是把手：它开窗，但它不叫「开窗那一手」
                if isinstance(node, ast.ClassDef):
                    hit = any(_callee_tail(base) in handles for base in node.bases)
                else:
                    hit = _opens_a_window(node, frozenset(handles))
                if hit:
                    handles.add(node.name)      # 同名就是同一族把手：集合按名字认，不按文件
                    grew = True
        if not grew:
            break
    return frozenset(handles)


def called_handles(tree: ast.AST, handles: frozenset) -> set:
    """这枚件真**调用**过的把手名：只认调用点，串里出现同名不算。"""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            tail = _callee_tail(node.func)
            if tail in handles:
                found.add(tail)
    return found


def assert_homes_still_ship_their_counter_proofs(sources=None, handles=None) -> dict:
    """引用者钉的本体，拆成普通函数：反证要驱动**同一枚**逻辑，不许另造一套判据。

    交回 ``rel -> (反证件数, 这枚件真调用过的把手名)``——那两份读数同时才是判据 ③：
    用例名不许蒸发，窗也必须还在。
    """
    texts = suite_sources() if sources is None else sources
    names = window_handles(texts) if handles is None else frozenset(handles)
    assert names, (
        "从真源（%s ＋ %s）派生不到任何一枚窗把手名：引用者钉瞎了——旧姿势的骨架名与新姿势的"
        "装变异把手名它一枚都认不出来，这时「反证件数 >= 下限」那几格全是空转"
        % (SOURCE_OF_WINDOW_BASES, SOURCE_OF_POSTURE_HANDLES))
    readings = {}
    for rel, needed in sorted(COUNTER_PROOF_HOMES.items()):
        entry = texts.get(rel)
        assert entry is not None, "射程里的 %s 不在输入面上：这枚判据没被测到" % rel
        _source, tree = entry
        counters = [node.name for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    and (node.name.startswith("test_counter_evidence")
                         or node.name.startswith("test_d1_"))]
        assert len(counters) >= needed, "%s 只剩 %d 枚反证件：%s" % (rel, len(counters), counters)
        used = sorted(called_handles(tree, names))
        assert used, ("%s 里已经没有在册反证窗把手了：从真源派生到 %d 枚名字（%s），这一枚一件"
                      "都没被调用；旧写法在这一格只认字面量 `_TempEdit(`，新姿势它认不出来"
                      % (rel, len(names), ", ".join(sorted(names))))
        readings[rel] = (len(counters), used)
    return readings


def test_the_three_pins_this_ticket_moved_still_ship_their_counter_proofs():
    """判据 ③ 的落点核对：三枚件改的是「变异往哪儿落」，用例名与变异本体一枚都不许一起蒸发。

    R572 改口：把手名不再手抄。今天两格同时成立才算过——反证件名下限照旧，且这枚件真调用过
    一枚**派生自真源**的窗把手（影子窗骨架或装变异那一腿）。
    """
    sources = suite_sources()
    handles = window_handles(sources)
    readings = assert_homes_still_ship_their_counter_proofs(sources, handles)
    assert handles, "派生把手集合为空：上面那格就是空转"
    print("[r253/r572] 派生把手 %d 枚；射程内读数：%s" % (len(handles), readings))
