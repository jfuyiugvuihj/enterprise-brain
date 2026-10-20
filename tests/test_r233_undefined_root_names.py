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

R236 把本班交回的两枚修掉了（`app/trace/store.py` 的 `logger`、`app/db/migrations.py` 的
`EmbeddingScope`），今天的读数是清单归零；力气挪到"摘掉修复必照样报"的反证钉上，门没变钝。
"""
import ast
import builtins
import hashlib
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

#: 实测读数：范围（app/deploy/scripts）内今天 0 枚。
#: 本班交回的两枚由 R236 修掉 —— `app/trace/store.py` 补上 `from app.common.logger import
#: logger`（那句 `logger.warning` 坐在 `except Exception as exc:` 里，缺它就是拿兜底做二次
#: 替换），`app/db/migrations.py` 补上 `from app.rag.indexing import EmbeddingScope`（注解位
#: 在 future import 之下今天不求值，但 `get_type_hints` 一求就炸）。
#: 清单归零不等于门变钝：`test_a_fixed_survivor_reintroduced_still_gets_caught` 拿工作树外的
#: 副本各演一遍"把那句 import 摘掉"，摘掉必照样报出那枚根名字。多一枚 = 新增一例同类，判红。
EXPECTED_INVENTORY = set()


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


# ------------------------------------------------------------------- 门：清单归零，双向可炸
def test_the_inventory_is_empty(capsys):
    """这类 bug 在 app/deploy/scripts 里今天一枚不剩；冒出任何一枚即判红。

    清单空不等于门钝：这枚只回答"还剩几枚"，"还抓得住"由那族反证钉代劳
    （`test_the_base_version_of_auth_py_would_have_been_caught` 与
    `test_a_fixed_survivor_reintroduced_still_gets_caught`）。两枚合起来才双向可炸 ——
    多一枚红，扫描器失去力气也红。
    """
    rows, files = _inventory()

    print("\n=== R233 同类扫描：范围 %s，py 文件 %d 枚，命中 %d 枚 ===" % (SCOPE, len(files), len(rows)))
    for row in rows:
        print(
            "%s:%d  root=%s  inert_annotation=%s  star_import=%s"
            % (row["file"], row["line"], row["root"], row["inert_annotation"], row["star_import"])
        )

    assert EXPECTED_INVENTORY == set(), "清单已归零：这枚门只判多一枚，不许再登记幸存者"
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


# R236 修掉的两枚幸存者：文件 -> (R236 补上的那一句 import, 摘掉它就该报出的根名字,
# 是否属于"注解位 + future import"那一形)。副本只落在 tmp_path，真文件全程只读。
REINTRODUCED_SHAPES = {
    "app/trace/store.py": (
        "from app.common.logger import logger",
        "logger",
        False,
    ),
    "app/db/migrations.py": (
        "from app.rag.indexing import EmbeddingScope",
        "EmbeddingScope",
        True,
    ),
}


@pytest.mark.parametrize("rel", sorted(REINTRODUCED_SHAPES))
def test_a_fixed_survivor_reintroduced_still_gets_caught(rel, tmp_path):
    """门仍有牙：把 R236 补的那句 import 摘掉，工作树外的副本照旧必须报出那枚根名字。

    这就是"清单归零而门不钝"的另一半凭据，强度照 `auth.py` 那枚反证钉办。收尾再核一次
    真文件的 sha256 与开头一致 —— 本枚不许改工作树取证（与 R233 本体"只报不动"同一条纪律）。
    惰性那一格顺手核 `inert_annotation`：注解位的形状今天照样被打上标记。
    """
    binding, root_name, inert_expected = REINTRODUCED_SHAPES[rel]
    real = ROOT / rel
    digest_before = hashlib.sha256(real.read_bytes()).hexdigest()
    source = real.read_text(encoding="utf-8")
    assert binding in source, "R236 的那句 import 不在位，这枚反证钉要重写"

    stripped = source.replace(binding + "\n", "", 1)
    assert stripped != source, "摘不掉就不是反证"
    tree = ast.parse(stripped)
    copy = tmp_path / rel.replace("/", "__")
    assert not copy.resolve().is_relative_to(ROOT), "副本必须落在工作树之外"
    copy.write_text(stripped, encoding="utf-8")

    findings, _star, inert = _scan_source(
        copy.read_text(encoding="utf-8"), future_flag=_has_future_annotations(tree)
    )
    first_use = min(
        node.lineno for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == root_name
    )

    assert findings == [(first_use, root_name)], findings
    assert (root_name in inert) is inert_expected, inert
    assert hashlib.sha256(real.read_bytes()).hexdigest() == digest_before, "反证钉不许动工作树"


# ------------------------------------------------- 两枚幸存者的修复凭据（R236 改掉之后）
def test_survivor_one_is_fixed_and_still_lives_in_an_exception_handler():
    """`app/trace/store.py` 的 `logger`：形状一格没改，改的是那枚名字今天有 import。

    三半缺一即红：形状还在（文件仍无 future import，`logger.warning` 仍坐在
    `except Exception as exc:` 里面 —— 谁把兜底改成上抛，本枚红，那条语义归总控裁定）；
    修复在位且绑在**模块级**（塞进函数体或 `TYPE_CHECKING` 都救不了兜底）；仍被覆盖
    （本门每次都扫这枚文件，今天交回 0 枚，删掉那句 import 会同时红在这里与反证钉）。
    """
    rel = "app/trace/store.py"
    source = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _has_future_annotations(tree) is False
    assert "from app.common.logger import logger" in source
    assert [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.common.logger"
        and any(alias.name == "logger" for alias in node.names)
    ], "那句 import 必须在模块级，except 兜底才拿得到它"
    handler_lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            for inner in ast.walk(node):
                root = _root_of(inner) if isinstance(inner, ast.Attribute) else None
                if root is not None and root.id == "logger":
                    handler_lines.append(root.lineno)
    assert handler_lines, "`logger` 不在 except 兜底里，本定性要重写"

    assert _scan_source(source)[0] == [], "修后的 store.py 必须扫不出东西"
    rows, _files = _inventory()
    assert [row for row in rows if row["file"] == rel] == []


def test_survivor_two_is_fixed_and_still_the_inert_annotation_shape():
    """`app/db/migrations.py` 的 `EmbeddingScope`：还是"注解位 + future import"那一形，
    变的是类型今天运行期可达 —— 原钉关于注解本身的那一半一个字没动。
    """
    rel = "app/db/migrations.py"
    source = (ROOT / rel).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert _has_future_annotations(tree) is True
    ann = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "declared_embedding_profile"
    ]
    assert isinstance(ann[0].returns, ast.Name) and ann[0].returns.id == "EmbeddingScope"
    assert "EmbeddingScope" in "".join(
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    ), "R236 之后它必须被 import，注解才求值得动"
    assert [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.rag.indexing"
        and any(alias.name == "EmbeddingScope" for alias in node.names)
    ], "那句 import 必须在模块级：塞进函数里，注解照样是哑弹"

    assert _scan_source(source, future_flag=True)[0] == [], "修后的 migrations.py 必须扫不出东西"
    rows, _files = _inventory()
    assert [row for row in rows if row["file"] == rel] == []


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
