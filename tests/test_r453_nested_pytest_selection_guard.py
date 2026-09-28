"""R453 · 事故 #69 的牙：以 pytest 为子进程的驱动件，空参数不许回落到全量收集。

病怎么发的（09-28 本单现场，总控按事故 #69 入账）：反证矩阵的驱动脚本参数绑定少传一位
⇒ 递给 pytest 的选择路径是空串 ⇒ pytest 就当「没给目标」，照 `pyproject.toml` 的
`testpaths = ["tests"]` 收全仓 ⇒ 约 15 分钟的全量套件在一声「定向测试」里跑起来了。
今天这是第二次踩同一根：第一次＝跟进单 §123 第四节那枚 620 s 假红（嵌套 pytest 的默认参数
不可信）。所以规矩要钉在**读法**上，不是钉在态度上：

R1 每一处「起 pytest 的子进程调用」都必须在 argv 里带至少一枚**选择目标**；
   裸一枚 `pytest -q`（只有开关没有目标）＝全量收集，当场红。
R2 目标来自变量／spread 的站点，同一枚函数里必须对空值**当场拒绝**
   （`if not targets: raise/assert/return ...` 那一类），不许悄悄回落；
   今日现场还欠着几处（别的单的件，本单无权改），逐枚记进 `UNGUARDED_DEBT`，
   名册只许缩短不许加长——补一枚就少一枚，红一次就把那枚从名册里删掉。
R3 argv 看不见形状的起法（先拼 `cmd` 再 `subprocess.run(cmd)`）必须显式豁免，
   豁免的姿势是在所在函数里写 `R453-SANCTION-FULL-COLLECTION` 并同段写明「全量」二字；
   没写豁免的新起法一律红。
R4 「空参数＝全量收集」不许只是修辞：本件现读 `pyproject.toml` 的 `testpaths` 与
   tests/ 的枚数把这条链两端都量出来（不起嵌套 pytest：R449 的名册在别人的件里，
   本单无权进册，硬起就会把那本在册件拿红）。
R5 豁免令牌不许撒着写：仓内令牌枚数必须等于被豁免站点枚数，拿它洗白别的站点当场红。

全部离线：本件只做 AST 读法与文本现读，不起任何子进程、不打模型、不动容器。
合成源落在 tmp_path 的影子根里读，盘上那架子一个字都不动。
"""
from __future__ import annotations

import ast
import re
import sys
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SANCTION = "R453-SANCTION-FULL-COLLECTION"
#: 扫描面：只有驱动件会在这里起 pytest；app/** 与 frontend/** 是禁域且不因子进程起测试。
SCAN_DIRS = ("scripts", "tests")
SCAN_FILES = ("conftest.py",)
SUBPROCESS_METHODS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
#: 带值的开关：它后面那一枚是开关的值，不是选择目标（`-k SEL`／`--basetemp DIR` 都算这类）。
FLAGS_WITH_VALUE = frozenset({
    "-m", "-k", "-p", "-o", "-n", "-c", "-W", "-r", "--basetemp", "--rootdir", "--dist",
    "--override-ini", "--ignore", "--ignore-glob", "--deselect", "-rf", "--runxfail-limit",
})
#「不许回落全量」的两种拒绝形状：对空值 if 一次硬停，或一枚裸 assert。
GUARD_IF_RE = re.compile(
    r"if\s+not\s+(?P<not_name>\w+)\s*:|if\s+len\(\s*(?P<len_name>\w+)\s*\)\s*==\s*0\s*:")
GUARD_ASSERT_RE = re.compile(r"^\s*assert\s+(?P<assert_name>\w+)\s*(?:,[^\n]*)?$", re.M)



def _segment(lines: list[str], node: ast.AST) -> str:
    """按行表切出一枚节点的源码。

    别用 ast.get_source_segment：它每调一次都要把整篇源码重切一遍，本件对扫描面里每一枚
    含 pytest 字样的件都要切（R449 那本件首版就是这么在门里读了 200 s 的）。
    """
    if node.lineno == node.end_lineno:
        return lines[node.lineno - 1][node.col_offset:node.end_col_offset]
    parts = [lines[node.lineno - 1][node.col_offset:]]
    parts.extend(lines[node.lineno:node.end_lineno - 1])
    if node.end_col_offset:
        parts.append(lines[node.end_lineno - 1][:node.end_col_offset])
    return "".join(parts)


def _scope(tree: ast.Module, call: ast.Call):
    """这枚调用所在的最内层函数（模块级则为 None）。"""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= call.lineno <= node.end_lineno:
            if best is None or best.lineno < node.lineno:
                best = node
    return best


def _module_consts(tree: ast.Module) -> dict[str, ast.expr]:
    """模块级常量表：`TEST_REL = "tests/x.py"` 与 `BASE_ARGS = ["-m", "pytest", ...]` 都算。"""
    consts: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            consts[node.targets[0].id] = node.value
    return consts


def _looks_like_target(value: str) -> bool:
    """选择目标的形状：路径／文件名／`tests/test_x.py::test_y`；开关与开关值不算。"""
    return bool(value) and not value.startswith("-") and (
        "/" in value or value.endswith(".py") or "::" in value or value.endswith(".jsonl"))


def _flatten(node: ast.expr | None):
    """`[...] + list(targets)`：交回（最左的列表字面量或 None, 加号右边每一段）。"""
    tails: list[ast.expr] = []
    current = node
    while isinstance(current, ast.BinOp) and isinstance(current.op, ast.Add):
        tails.append(current.right)
        current = current.left
    return (current if isinstance(current, ast.List) else None), list(reversed(tails))


def _local_assignment(scope: ast.AST | None, name: str) -> ast.expr | None:
    if scope is None:
        return None
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value
    return None


def _function_return(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and inner.value is not None:
                    return inner.value
    return None


def _resolve_argv(expr, tree: ast.Module, consts, scope, depth: int = 0):
    """把 argv 表达式解到「看得见的列表」：模块常量／函数内赋值／同文件小助手都跟一层。"""
    if expr is None or depth > 4:
        return None
    visible, tails = _flatten(expr)
    if visible is not None:
        return visible, tails
    if isinstance(expr, ast.Name):
        nxt = consts.get(expr.id)
        if nxt is None:
            nxt = _local_assignment(scope, expr.id)
        return _resolve_argv(nxt, tree, consts, scope, depth + 1)
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        return _resolve_argv(_function_return(tree, expr.func.id), tree, consts, scope, depth + 1)
    return None


def _splice(elts: list[ast.expr], consts: dict[str, ast.expr]) -> list[ast.expr]:
    """把 `*BASE_ARGS` 展开成它自己的元素：argv 藏在模块常量里也要看得见形状。"""
    stream: list[ast.expr] = []
    for element in elts:
        inner = element.value if isinstance(element, ast.Starred) else element
        if isinstance(inner, ast.Name) and isinstance(consts.get(inner.id), ast.List):
            stream.extend(consts[inner.id].elts)
        else:
            stream.append(element)
    return stream


def _candidates(stream: list[ast.expr], tails: list[ast.expr], consts: dict[str, ast.expr]):
    """从可见 argv 里挑「选择目标候选」：[(种类, 文本, 变量名)]，种类＝literal／variable。"""
    found: list[tuple[str, str, str | None]] = []
    skip_next = False
    for position, element in enumerate(stream):
        if position == 0:  # argv[0] 是解释器本身，永远不是选择目标
            continue
        if skip_next:
            skip_next = False
            continue
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            if element.value.startswith("-"):
                if element.value in FLAGS_WITH_VALUE:
                    skip_next = True
                continue
            found.append(("literal", element.value, None))
            continue
        name: str | None = None
        if isinstance(element, ast.Starred) and isinstance(element.value, ast.Name):
            name = element.value.id
        elif isinstance(element, ast.Name):
            name = element.id
        elif isinstance(element, ast.Call) and isinstance(element.func, ast.Name) and element.func.id == "list":
            name = element.args[0].id if element.args and isinstance(element.args[0], ast.Name) else None
        resolved = consts.get(name) if name else None
        if isinstance(resolved, ast.Constant) and isinstance(resolved.value, str) and _looks_like_target(
                resolved.value):
            found.append(("literal", resolved.value, name))
        else:
            label = ("starred:" + name) if isinstance(element, ast.Starred) else (name or "expr")
            found.append(("variable", label, name))
    for tail in tails:
        name = None
        if isinstance(tail, ast.Name):
            name = tail.id
        elif isinstance(tail, ast.Call) and isinstance(tail.func, ast.Name) and tail.func.id == "list":
            name = tail.args[0].id if tail.args and isinstance(tail.args[0], ast.Name) else None
        found.append(("variable", "tail:" + (name or "expr"), name))
    return found


def _argv_node(call: ast.Call) -> ast.expr | None:
    target = call.args[0] if call.args else None
    if target is None:
        for keyword in call.keywords:
            if keyword.arg in ("args", "cmd"):
                target = keyword.value
    return target


def _spawned_files(root: Path) -> list[Path]:
    picked: list[Path] = []
    for rel in SCAN_FILES:
        if (root / rel).is_file():
            picked.append(root / rel)
    for name in SCAN_DIRS:
        base = root / name
        if base.is_dir():
            picked.extend(sorted(base.rglob("*.py")))
    return [path for path in picked if "__pycache__" not in path.parts]


_SCAN_CACHE: dict[str, list[dict]] = {}


def scan_spawns(root: Path) -> list[dict]:
    """现读扫描面：每一处「起 pytest 的子进程调用」交回一枚记录。

    记录字段：rel／lineno／func／kind／candidates／func_src／sanctioned。
    kind＝visible（argv 形状解得开）／opaque（解不开：这一处审计不了，R3 要求显式豁免）。
    """
    key = str(root)
    if key in _SCAN_CACHE:
        return _SCAN_CACHE[key]
    records: list[dict] = []
    for path in _spawned_files(root):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "pytest" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        with warnings.catch_warnings():
            #: 读别人的件不许替他们攒 DeprecationWarning（invalid escape sequence 那一类）：
            #: 解析全仓时这些警告会挂到本件名下，把别人的告警断言搅浑。
            warnings.simplefilter("ignore", (SyntaxWarning, DeprecationWarning))
            tree = ast.parse(text, filename=str(path))
        lines = text.splitlines(keepends=True)
        consts = _module_consts(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr = getattr(node.func, "attr", None)
            owner = node.func.value.id if isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name) else None
            is_pytest_main = owner == "pytest" and attr == "main"
            if not is_pytest_main and not (owner == "subprocess" and attr in SUBPROCESS_METHODS):
                continue
            scope = _scope(tree, node)
            func_src = _segment(lines, scope) if scope is not None else text
            resolved = _resolve_argv(_argv_node(node), tree, consts, scope)
            if resolved is None:
                if not re.search(r'-m["\']?\s*,\s*["\']pytest["\']|\bpytest\b', func_src):
                    continue
                records.append({
                    "rel": rel, "lineno": node.lineno, "func": scope.name if scope else "<module>",
                    "kind": "opaque", "candidates": [], "func_src": func_src,
                    "sanctioned": SANCTION in func_src and "全量" in func_src,
                })
                continue
            visible, tails = resolved
            stream = _splice(visible.elts, consts)
            values = [element.value for element in stream
                      if isinstance(element, ast.Constant) and isinstance(element.value, str)]
            paired = any(values[index] == "-m" and index + 1 < len(values) and values[index + 1] == "pytest"
                         for index in range(len(values)))
            if not (is_pytest_main or paired or "pytest" in values):
                continue
            records.append({
                "rel": rel, "lineno": node.lineno, "func": scope.name if scope else "<module>",
                "kind": "visible", "candidates": _candidates(stream, tails, consts),
                "func_src": func_src, "sanctioned": SANCTION in func_src and "全量" in func_src,
            })
    records.sort(key=lambda record: (record["rel"], record["lineno"]))
    _SCAN_CACHE[key] = records
    return records


def _refusal_present(record: dict) -> bool:
    """变量／spread 目标所在函数里，有没有对「空选择」的当场拒绝（raise／assert／return 那一类）。"""
    source = record["func_src"]
    for kind, _label, name in record["candidates"]:
        if kind != "variable" or not name:
            continue
        for match in GUARD_ASSERT_RE.finditer(source):
            if match.group("assert_name") == name:
                return True
        for match in GUARD_IF_RE.finditer(source):
            guarded = match.group("not_name") or match.group("len_name")
            if guarded != name:
                continue
            following = source[match.end():match.end() + 260]
            if re.search(r"\b(?:raise|return)\b|assert |pytest\.fail|sys\.exit", following):
                return True
    return False


def classify(record: dict) -> str:
    """bare＝一枚目标都没有；spread＝目标全来自变量；literal＝至少一枚逐字目标；opaque＝解不开。"""
    if record["kind"] == "opaque":
        return "opaque"
    if not record["candidates"]:
        return "bare"
    if any(kind == "literal" for kind, _label, _name in record["candidates"]):
        return "literal"
    return "spread"


#: 现场欠账（09-28 现扫填）：目标来自变量而那一枚函数里还没有空值拒绝的站点。
#: 都是别人的单的件，本单无权改它们的文件。名册只许缩短不许加长：补掉一处就删一行。
UNGUARDED_DEBT: tuple[tuple[str, str], ...] = (
    ("tests/fixtures/r349_catalog_tail_probe_driver.py", "run_pytest"),
    ("tests/fixtures/r356_r357_refutation_driver.py", "run_pytest"),
    ("tests/fixtures/r364_refutation_driver.py", "run_pytest"),
    ("tests/test_r134_chroma_writeback.py", "_run_child_pytest"),
    ("tests/test_r163_matrix_teeth.py", "_run_nail"),
)

#: 按名豁免的在册全量门：它的工作就是全量收集，且在禁域（只读）。除此之外不设第二枚豁免。
SANCTIONED_MODULES: tuple[str, ...] = ("scripts/run_gate.py",)


def site_key(record: dict) -> tuple[str, str]:
    return (record["rel"], record["func"])


def debt_sites(records: list[dict]) -> list[tuple[str, str]]:
    return sorted({site_key(record) for record in records
                   if classify(record) == "spread" and not _refusal_present(record)
                   and not record["sanctioned"] and record["rel"] not in SANCTIONED_MODULES})


def violations(records: list[dict]) -> list[str]:
    """摘掉事故 #69 之后不许剩下的东西：每一处没牙的起法都点名。"""
    hits = []
    for record in records:
        if record["sanctioned"] or record["rel"] in SANCTIONED_MODULES:
            continue
        kind = classify(record)
        here = "%s:%d %s()" % (record["rel"], record["lineno"], record["func"])
        if kind == "bare":
            hits.append(here + " 起 pytest 却没有一枚选择目标 ⇒ 空参数＝全量收集（R1）")
        elif kind == "opaque":
            hits.append(here + " argv 解不出形状 ⇒ 这一处审计不了，必须写豁免（R3）")
        elif kind == "spread" and not _refusal_present(record) and site_key(record) not in set(UNGUARDED_DEBT):
            hits.append(here + " 目标来自变量／spread 却没有空值拒绝 ⇒ 会回落全量收集（R2）")
    return hits


def spare_sanction_tokens(root: Path) -> int:
    """豁免令牌必须一枚顶一处：只数注释行里的令牌（散文里提到不算）。"""
    total = 0
    for path in _spawned_files(root):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        total += sum(1 for line in text.splitlines() if line.strip().startswith("#") and SANCTION in line)
    return total


# ------------------------------------------------------------------ 现场读数（R1／R2／R3）
def test_the_scanned_surface_actually_contains_pytest_drivers() -> None:
    """扫描面不许是空转：今天至少要有 6 处起 pytest 的调用在册。"""
    records = scan_spawns(REPO)
    assert len(records) >= 6, "只扫到 %d 处起 pytest 的调用，扫描面或读法漂了" % len(records)
    assert all(record["kind"] in ("visible", "opaque") for record in records)
    assert {classify(record) for record in records} <= {"bare", "spread", "literal", "opaque"}


def test_no_pytest_driver_in_the_tree_lacks_an_empty_selection_refusal() -> None:
    """R1＋R2＋R3 的现场读数：仓内每一处以 pytest 为子进程的起法都得有牙。"""
    hits = violations(scan_spawns(REPO))
    assert not hits, "这些起 pytest 的驱动件没牙（空参数就会回落到全量收集）：%s" % hits


def test_the_selection_debt_roster_matches_the_tree_and_may_only_shrink() -> None:
    """欠账名册必须与现场逐枚相等：补掉一处就删一行，多一处本件当场红。"""
    live = debt_sites(scan_spawns(REPO))
    assert live == sorted(UNGUARDED_DEBT), (
        "名册与现场不等（多出＝新病灶；少了＝有人补了牙，把那一行删掉）：现场 %s vs 名册 %s" % (
            live, sorted(UNGUARDED_DEBT)))


def test_the_named_sanction_allow_list_is_alive_and_confined() -> None:
    """按名豁免只许留给 scripts/ 下的在册全量门，而且它今天必须真的还在起 pytest。"""
    records = scan_spawns(REPO)
    for rel in SANCTIONED_MODULES:
        assert rel.startswith("scripts/"), "豁免名单不许收到 scripts/ 之外：%s" % rel
        assert (REPO / rel).is_file(), "豁免名单里那枚文件不在：%s" % rel
        assert any(record["rel"] == rel for record in records), (
            "%s 已经不起 pytest 了，豁免是死的，删掉这一枚" % rel)


def test_sanction_tokens_are_never_spare() -> None:
    """R5：令牌枚数必须等于被豁免站点枚数，拿它洗白别的站点当场红。"""
    records = scan_spawns(REPO)
    sanctioned = [record for record in records if record["sanctioned"]]
    tokens = spare_sanction_tokens(REPO)
    assert tokens == len(sanctioned), (
        "注释里的豁免令牌 %d 枚，真正被豁免的站点只有 %d 处：%s" % (
            tokens, len(sanctioned), [record["rel"] + ":" + str(record["lineno"]) for record in sanctioned]))



# ------------------------------------------------------------------ R4：空参数＝全量收集（现读数，不靠修辞）
def test_an_empty_selection_would_collect_the_whole_tests_tree() -> None:
    """「不给目标」到底收多少：现读 pyproject 的 testpaths 与 tests/ 的枚数。

    事故 #69 的机到这里就是一条链：argv 里的选择路径是空串 → pytest 照
    `[tool.pytest.ini_options] testpaths` 把整棵 tests/ 收走。本钉把这条链的两端都现读：
    一端是 testpaths 确实写着 tests，另一端是 tests/ 下确实挣着上百枚测试件。
    不起嵌套 pytest 的原因：tests/test_r449_nested_pytest_basetemp_contract.py 的名册硬编在
    它自己的文件里（本单禁域），新起一处嵌套会话就要把那本在册件拿红。
    """
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8-sig")
    block = pyproject[pyproject.index("[tool.pytest.ini_options]"):]
    match = re.search(r"^testpaths\s*=\s*\[([^\]]*)\]", block, re.M)
    assert match, "pyproject 里拿不到 testpaths：本钉的前提变了，用法要重写"
    declared = [name.strip().strip(chr(34) + chr(39)) for name in match.group(1).split(",") if name.strip()]
    assert "tests" in declared, "testpaths 不再含 tests（现读 %s）：空参数的后果要重新量" % declared
    collected = sorted((REPO / "tests").glob("test_*.py"))
    assert len(collected) >= 200, (
        "tests/ 下只有 %d 枚测试件，这条链读不出「全量」的分量" % len(collected))
    #: 一枚目标与零枚目标的对比：给一枚只收一枚，不给就是整棵树。
    one_target = [path for path in collected if path.name == "test_r453_cloud_eval_override.py"]
    assert len(one_target) == 1 and len(one_target) < len(collected), (
        "定向与全量的对比拿不到：%s vs %s" % (len(one_target), len(collected)))


# ------------------------------------------------------------------ R5：反证（合成源，逐条摘行为）
def shadow_surface(tmp_path: Path, name: str, source: str) -> Path:
    root = tmp_path / "surface"
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / name).write_text(source.lstrip("\n"), encoding="utf-8")
    return root


BARE = """
    import subprocess, sys


    def driver(root):
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"],
                              cwd=str(root))
    """

SPREAD = """
    import subprocess, sys


    def driver(root, targets):
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"]
                              + list(targets), cwd=str(root))
    """

SPREAD_REFUSED = """
    import subprocess, sys


    def driver(root, targets):
        if not targets:
            raise RuntimeError("空选择＝全量收集，本驱动器不收")
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"]
                              + list(targets), cwd=str(root))
    """

SPREAD_ASSERTED = """
    import subprocess, sys


    def driver(root, targets):
        assert targets, "空选择＝全量收集"
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"]
                              + list(targets), cwd=str(root))
    """

LITERAL = """
    import subprocess, sys

    TEST_REL = "tests/test_alpha.py"


    def driver(root):
        return subprocess.run([sys.executable, "-m", "pytest", TEST_REL, "-q", "--basetemp", "bt"],
                              cwd=str(root))
    """

OPAQUE = """
    import subprocess, sys


    def driver(root):
        # argv 由外部注入（起的是 pytest），本件看不见它的形状
        argv = external_builder(root)
        return subprocess.run(argv, cwd=str(root))


    def external_builder(root):
        return split_from_environ()
    """

SANCTIONED_BARE = """
    import subprocess, sys


    def driver(root):
        # @@S@@：这处要的就是全量收集，理由写在同段
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"],
                              cwd=str(root))
    """

SANCTION_WITHOUT_REASON = """
    import subprocess, sys


    def driver(root):
        # @@S@@
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"],
                              cwd=str(root))
    """

SANCTION_ONLY_IN_PROSE = """
    import subprocess, sys


    def driver(root):
        \"\"\"这里只是散文里提一句 R453-SANCTION-FULL-COLLECTION，注释里没有。\"\"\"
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", "bt"],
                              cwd=str(root))
    """

NOT_A_SITE = """
    import subprocess, sys


    def driver(root):
        return subprocess.run(["git", "status", "--porcelain"], cwd=str(root))
    """

#: 合成源一律四格缩进写在上面，落盘前要把这层壳脱掉。
def _dedent(source: str) -> str:
    lines = source.lstrip("\n").splitlines()
    body = "".join((line[4:] if line.startswith("    ") else line) + "\n" for line in lines)
    #: 合成源里的令牌用占位符写：这件自己的注释行也要被 R5 数一次，两处勿混。
    return body.replace("@@S@@", SANCTION)


@pytest.mark.parametrize("name,source,expect_named", [
    ("test_bare.py", BARE, True),
    ("test_spread.py", SPREAD, True),
    ("test_spread_refused.py", SPREAD_REFUSED, False),
    ("test_spread_asserted.py", SPREAD_ASSERTED, False),
    ("test_literal.py", LITERAL, False),
    ("test_opaque.py", OPAQUE, True),
    ("test_sanctioned_bare.py", SANCTIONED_BARE, False),
    ("test_sanction_without_reason.py", SANCTION_WITHOUT_REASON, True),
    ("test_sanction_only_in_prose.py", SANCTION_ONLY_IN_PROSE, True),
])
def test_counter_evidence_the_detector_bites_on_each_shape(
        tmp_path: Path, name: str, source: str, expect_named: bool) -> None:
    root = shadow_surface(tmp_path, name, _dedent(source))
    records = scan_spawns(root)
    assert len(records) == 1, "%s 应当只扫到一处起 pytest 的调用，实测 %d" % (name, len(records))
    hits = violations(records)
    if expect_named:
        assert hits, "%s 这种没牙的起法必须点名，检测器却放行了" % name
    else:
        assert not hits, "%s 本该放行却被点名：%s" % (name, hits)


def test_counter_evidence_a_non_pytest_subprocess_call_is_not_a_site(tmp_path: Path) -> None:
    root = shadow_surface(tmp_path, "test_quiet.py", _dedent(NOT_A_SITE))
    assert scan_spawns(root) == [], "git 调用被当成起 pytest 的站点，扫描面会越咬越宽"


def test_counter_evidence_the_sanction_word_alone_does_not_pass_a_site(tmp_path: Path) -> None:
    """令牌不许撒着写：写了令牌却没写「全量」的站点仍要红，且豁免令牌一枚只许顶一处。"""
    root = shadow_surface(tmp_path, "test_launder.py", _dedent(SANCTION_WITHOUT_REASON))
    records = scan_spawns(root)
    assert records[0]["sanctioned"] is False, "只有令牌的函数被判成了豁免"
    assert len(records) == 1 and spare_sanction_tokens(root) == 1, "令牌枚数与被扫站点不配"
    assert violations(records), "没写理由的豁免把 R1 洗白了"


def test_counter_evidence_dropping_the_refusal_makes_the_spread_site_red(tmp_path: Path) -> None:
    """摘掉「当场拒绝」这道行为：同一枚 spread 站点，有拒绝绿、没拒绝红——牙咬的是行为不是字。"""
    kept = scan_spawns(shadow_surface(tmp_path / "kept", "test_d.py", _dedent(SPREAD_REFUSED)))
    removed = scan_spawns(shadow_surface(tmp_path / "removed", "test_d.py", _dedent(SPREAD)))
    assert classify(kept[0]) == "spread" and classify(removed[0]) == "spread"
    assert _refusal_present(kept[0]) and not _refusal_present(removed[0])
    assert violations(kept) == [] and len(violations(removed)) == 1
