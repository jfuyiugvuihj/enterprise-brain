"""R233 判据 4：这类缺陷全仓还有几枚——用标准库 `ast` 自己扫，一枚 ruff/flake8 都不装。

规则（就是 R233 本体的形状）：一枚文件里出现 `名字.属性`（或裸 `名字`）而被读，且这枚根
名字在**本文件内**任何位置都没被绑定过（import / import as / 赋值 / 函数参数 / except as /
walrus / 推导式目标 / global / def / class / match 捕获）又不是内建 ⇒ 它一被走到就是
`NameError: name 'X' is not defined`。R233 就是 `app/common/auth.py` 用了
`secrets.token_urlsafe(24)` 而 import 块里没有 `secrets`。

绑定判定故意宽松（"整文件任一处绑定即算绑定"），所以它宁缺毋滥：
`import x as y`、条件 import、函数参数、内建、`try/except ImportError` 兜底都不会误报。
代价写在下面，不当没看见——
1. 看不见"名字由别的模块在运行期塞进来"（测试 monkeypatch 就属于这一类），所以本门只扫
   `app/**` + `deploy/**` + `scripts/**`，`tests/**` 不在范围内（实测扫了也是 0 枚）；
2. 看不见"import 了但属性名写错"（`secrets.token_urlsaf()` 那一形），那是另一类；
3. `from x import *` 静态判不了 ⇒ 单列标记，实测本范围 0 枚 star import；
4. 注解位置的名字在 `from __future__ import annotations` 之下只是字符串，今天不炸 ⇒ 单列
   `inert_annotation` 标记，本门照样把它报出来（它是延迟引信，不是零风险）。

本门只报不动：写域之外一枚都不改。清单与逐条定性见 `EXPECTED_INVENTORY`，
新增一枚 = 新增一例 R233 同类，判红。
"""
import ast
import builtins
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ("app", "deploy", "scripts")

BUILTIN_NAMES = frozenset(dir(builtins))
#: 模块里合法存在、但不在 `dir(builtins)` 的名字（CPython 注入的运行时符号）。
EXTRA_GLOBALS = {
    "__name__", "__file__", "__doc__", "__spec__", "__package__", "__builtins__",
    "__loader__", "__class__", "__path__", "__debug__", "__dict__", "__all__",
    "__annotations__", "__weakref__", "__module__", "__qualname__",
}

#: 实测读数（基点 ccf8942 + 本单补上 `import secrets` 之后，见下面两枚定性钉）。
#: 这一枚就是"这类 bug 还有几枚"的答案：一枚真炸的、一枚延迟引信，范围外没有第三枚。
EXPECTED_INVENTORY = {
    # 真阳性（活雷）：`app/trace/store.py:123` 在 `except Exception as exc:` 的兜底里用
    # `logger.warning(...)`，而该文件没有 import logger —— 同仓有 40 枚文件写着
    # `from app.common.logger import logger`，它漏了这一句。后果：`_observe_request_window`
    # try 块里任何一次异常都会被这枚 NameError 二次替换并顺着 `record_event`（同一把锁内、
    # 无外层兜底）抛给调用方，函数注释里那句 "a counter is never a request failure" 当场不成立。
    # 本单写域之外（app/trace/**），只报不动。
    ("app/trace/store.py", "logger"),
    # 今天不炸、但是延迟引信：`app/db/migrations.py:283` 的返回注解写了 `EmbeddingScope`，
    # 而这枚名字全文件只出现这一次 —— 它没有 import（类型其实在 `app/rag/indexing.py:238`）。
    # 同文件第 12 行有 `from __future__ import annotations` ⇒ 注解只是字符串，import 期不求值，
    # 所以今天跑不出错；但任何 `typing.get_type_hints()` / `inspect.signature(..., eval_str=True)`
    # 会当场炸，将来谁删掉那枚 future import，模块立刻在 import 期死。
    # 本单写域之外（app/db/**），只报不动。
    ("app/db/migrations.py", "EmbeddingScope"),
}


def _bound_names(tree):
    """本文件内一切"绑定过这枚名字"的位置，宽松收口（见模块 docstring 第 1 条）。"""
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            bound.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            bound.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.add(node.rest)
    return bound


def _root_of(node):
    """`a.b.c()` 的根是 `a`；返回值不是 Name（调用/下标/字面量）时返回 None。"""
    value = node
    while isinstance(value, ast.Attribute):
        value = value.value
    return value if isinstance(value, ast.Name) else None


def _annotation_only_names(tree):
    """只出现在注解位置的名字：有 `from __future__ import annotations` 时它们今天不求值。"""
    targets = set()

    def collect(subtree):
        for node in ast.walk(subtree):
            if isinstance(node, ast.Name):
                targets.add(id(node))

    for node in ast.walk(tree):
        annotation = getattr(node, "annotation", None)
        if annotation is not None:
            collect(annotation)
        returns = getattr(node, "returns", None)
        if returns is not None:
            collect(returns)
    return targets


def _has_future_annotations(tree):
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
        ):
            return True
    return False


def _scan_source(source, *, future_flag=False):
    """一枚文件的源码 -> (findings, star_import, inert)。findings 是 (lineno, root) 列表。"""
    tree = ast.parse(source)
    bound = _bound_names(tree)
    annotation_only = _annotation_only_names(tree)
    star = any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(tree)
    )
    found = {}
    live = set()
    seen = set()
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Attribute):
            root = _root_of(node)
            name = root.id if root is not None else None
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
        if name is None or name in bound or name in EXTRA_GLOBALS or name in BUILTIN_NAMES:
            continue
        found[name] = min(found.get(name, node.lineno), node.lineno)
        seen.add(name)
        # 只有"每一处出现都在注解位"才算惰性；一枚名字哪怕有一个真求值点，就照实算活雷。
        if not (future_flag and id(node) in annotation_only):
            live.add(name)
    return sorted((line, name) for name, line in found.items()), star, sorted(seen - live)


def _iter_scope():
    for top in SCOPE:
        for path in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path.relative_to(ROOT).as_posix(), path


def _inventory():
    rows = []
    files = []
    for rel, path in _iter_scope():
        files.append(rel)
        source = path.read_text(encoding="utf-8")
        findings, star, inert = _scan_source(source, future_flag=_has_future_annotations(ast.parse(source)))
        for line, name in findings:
            rows.append(
                {
                    "file": rel,
                    "line": line,
                    "root": name,
                    "star_import": star,
                    "inert_annotation": name in inert,
                }
            )
    return rows, files


# ----------------------------------------------------------------------- 门：清单不许多
def test_the_inventory_is_exactly_the_two_known_survivors(capsys):
    """这类 bug 在 app/deploy/scripts 里一共还剩这两枚，多一枚少一枚都算判红。"""
    rows, files = _inventory()

    print("\n=== R233 同类扫描：范围 %s，py 文件 %d 枚，命中 %d 枚 ===" % (SCOPE, len(files), len(rows)))
    for row in rows:
        print(
            "%s:%d  root=%s  inert_annotation=%s  star_import=%s"
            % (row["file"], row["line"], row["root"], row["inert_annotation"], row["star_import"])
        )

    assert {(row["file"], row["root"]) for row in rows} == EXPECTED_INVENTORY, rows
    assert not any(row["star_import"] for row in rows), "范围里冒出了 star import，静态判定失效"


def test_the_file_that_started_this_ticket_is_clean():
    """本单的回归钉：`app/common/auth.py` 再不许出现"用了没 import"的名字。"""
    rows, _ = _inventory()

    assert [row for row in rows if row["file"] == "app/common/auth.py"] == []
    assert _scan_source(AUTH_FIXED_SOURCE)[0] == [], "修后的 auth.py 必须扫不出东西"


def test_the_base_version_of_auth_py_would_have_been_caught():
    """同一枚扫描器扫修前那段 import 块，必须正好报出 `secrets`——证明门有力气，不是摆设。"""
    base = AUTH_FIXED_SOURCE.replace("import secrets  #", "import not_secrets  #", 1)
    first_use = min(
        number
        for number, line in enumerate(AUTH_FIXED_SOURCE.splitlines(), 1)
        if "secrets.token_urlsafe" in line
    )

    findings, _star, _inert = _scan_source(base)

    assert findings == [(first_use, "secrets")], findings
    assert {number for number, _name in findings} == {first_use}, "命中点必须是那两处铸口令之一"


# ------------------------------------------------------------------- 两条幸存者的定性依据
def test_survivor_one_is_a_live_nameerror_in_an_exception_handler():
    """`app/trace/store.py` 的 `logger`：不在注解里、文件也没有 future import ⇒ 真炸。"""
    rel = "app/trace/store.py"
    source = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _has_future_annotations(tree) is False
    assert "from app.common.logger import logger" not in source
    handler_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            for inner in ast.walk(node):
                root = _root_of(inner) if isinstance(inner, ast.Attribute) else None
                if root is not None and root.id == "logger":
                    handler_lines.append(root.lineno)
    assert handler_lines, "`logger` 不在 except 兜底里，本定性要重写"

    rows, _files = _inventory()
    survivor = next(row for row in rows if row["file"] == rel)
    assert survivor["root"] == "logger" and survivor["inert_annotation"] is False


def test_survivor_two_is_inert_only_because_of_a_future_import():
    """`app/db/migrations.py` 的 `EmbeddingScope`：注解位 + future import ⇒ 今天不求值，延迟引信。"""
    rel = "app/db/migrations.py"
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))

    assert _has_future_annotations(tree) is True
    ann = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "declared_embedding_profile"
    ]
    assert isinstance(ann[0].returns, ast.Name) and ann[0].returns.id == "EmbeddingScope"
    assert "EmbeddingScope" not in "".join(
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    ), "它没有 import；注解指了一枚本模块拿不到的类型"

    rows, _files = _inventory()
    survivor = next(row for row in rows if row["file"] == rel)
    assert survivor["root"] == "EmbeddingScope" and survivor["inert_annotation"] is True


# ------------------------------------------------------------- 扫描器自己的假阳对拍（判据 4 的凭据）
AUTH_FIXED_SOURCE = (ROOT / "app" / "common" / "auth.py").read_text(encoding="utf-8")

CONTROL_SOURCES = {
    # 形 = (源码, 期望命中, 说明)
    "missing_import": ("import os\n\n\ndef f():\n    return secrets.token_urlsafe(24)\n", ["secrets"], "R233 本体形状"),
    "imported": ("import secrets\n\n\ndef f():\n    return secrets.token_urlsafe(24)\n", [], "import 了就没事"),
    "aliased_import": ("import secrets as s\n\n\ndef f():\n    return s.token_urlsafe(24)\n", [], "import x as y 的根算绑定"),
    "from_import": ("from secrets import token_urlsafe\n\n\ndef f():\n    return token_urlsafe(24)\n", [], "from x import y"),
    "function_argument": ("def f(logger):\n    return logger.warning('x')\n", [], "函数参数就是绑定"),
    "keyword_argument_body": ("def f(*, table):\n    return table.rows\n", [], "kwonly 参数"),
    "lambda_argument": ("f = lambda store: store.rows\n", [], "lambda 参数"),
    "class_attribute": ("class A:\n    def m(self):\n        return self.x\n", [], "self 是参数"),
    "builtin": ("print(type('x').__name__)\n", [], "内建不报"),
    "exception_class": ("try:\n    pass\nexcept ValueError as exc:\n    raise exc.args\n", [], "except as 绑定了 exc"),
    "conditional_import": (
        "try:\n    import ujson as json\nexcept ModuleNotFoundError:\n    import json\n\n\ndef f():\n    return json.dumps({})\n",
        [],
        "条件 import 两支都算绑定",
    ),
    "global_then_use": ("_x = None\n\n\ndef f():\n    return _x.attr\n", [], "模块级赋值"),
    "inner_scope": ("def outer():\n    store = 1\n\n    def inner():\n        return store.attr\n    return inner\n", [], "闭包变量在文件内绑定"),
    "attribute_chain_root": ("def f():\n    return missing.a.b.c()\n", ["missing"], "链式属性取根名字"),
    "annotation_without_future": ("def f() -> Missing:\n    return 1\n", ["Missing"], "无 future 时注解在 def 期求值 = 真炸"),
    "walrus_and_comprehension": (
        "items = [y.attr for y in range(3)]\nif (cfg := None) is None:\n    pass\nprint(cfg.x, items[0].y)\n",
        [],
        "推导式目标与 walrus 也算绑定",
    ),
    "star_import_still_reported": (
        "from os.path import *\n\n\ndef f():\n    return mystery.join('a')\n",
        ["mystery"],
        "star import 不豁免未知根，但要打上 star 标记",
    ),
}


@pytest.mark.parametrize("case", sorted(CONTROL_SOURCES))
def test_the_scanner_separates_true_positives_from_the_usual_false_ones(case):
    source, expected, _why = CONTROL_SOURCES[case]

    findings, star, _inert = _scan_source(source, future_flag=_has_future_annotations(ast.parse(source)))

    assert sorted(name for _line, name in findings) == expected, case
    assert star is (case == "star_import_still_reported"), case


def test_the_inert_annotation_rule_needs_both_halves():
    """`inert_annotation` 只在"注解位 + 有 future import"同时成立时才成立，缺一枚就照报。"""
    source = "from __future__ import annotations\n\n\ndef f() -> Missing:\n    return 1\n"
    future = ast.parse(source)
    assert _has_future_annotations(future) is True
    assert _scan_source(source, future_flag=True) == ([(4, "Missing")], False, ["Missing"])
    assert _scan_source(source, future_flag=False) == ([(4, "Missing")], False, [])


def test_the_scope_actually_covers_the_tree(capsys):
    """防空转：走错目录会让上面所有判定"绿得没有内容"，所以范围本身也要有读数。"""
    rows, files = _inventory()

    print("\n=== 范围读数 ===")
    for top in SCOPE:
        print("%s/** = %d 枚 .py" % (top, sum(1 for rel in files if rel.startswith(top + "/"))))
    print("合计 %d 枚，命中 %d 枚" % (len(files), len(rows)))

    assert len(files) >= 120, len(files)
    for known in ("app/common/auth.py", "app/trace/store.py", "app/db/migrations.py"):
        assert known in files, known
    assert any(rel.startswith("deploy/") for rel in files), "deploy 没进范围"
    assert any(rel.startswith("scripts/") for rel in files), "scripts 没进范围"
