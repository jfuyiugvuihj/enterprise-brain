"""R236 T3：`declared_embedding_profile` 的返回注解要能被运行期求值。

那枚注解写的是 `EmbeddingScope`，而类型住在 `app/rag/indexing.py`，本模块从来没 import 它。
同文件 `:12` 有 `from __future__ import annotations` ⇒ 注解不求值，今天跑不出错；但任何
`typing.get_type_hints()` / `inspect.signature(..., eval_str=True)` 当场 `NameError`，
谁哪天删掉那枚 future import 就是 import 期死。R233 的类门把它钉成"延迟引信"。

二选一里选了**补 import**，理由写在交回单，摘要在此：改成字符串注解救不了这一枚 ——
`get_type_hints` 求的就是字符串，`EmbeddingScope` 不在模块名字空间里照样 `NameError`；
只有运行期可达的名字才算"类型可达"。`TYPE_CHECKING` 那半边同理（只求静态，不求这枚钉）。

代价核过：`app/rag/indexing.py` 的模块级 import 只有 stdlib + `app.common.logger`（一枚叶子），
所以新增这条 `app.db.migrations -> app.rag.indexing` 边不成环 —— 本件末尾那枚静态棘轮
把这句话钉成可跑的，而不是留在注释里。
"""
import ast
import inspect
from pathlib import Path
import typing

import pytest

from app.db import migrations
from app.rag import indexing

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_return_annotation_evaluates_for_real():
    """判据③：真求一次 `get_type_hints`，拿到的必须是那枚类型本体，不是字符串匹配。"""
    hints = typing.get_type_hints(migrations.declared_embedding_profile)

    assert hints["return"] is indexing.EmbeddingScope
    assert hints["database_name"] is str


def test_the_signature_evaluates_with_eval_str():
    """另一条真实求值路径：`inspect.signature(..., eval_str=True)` 同样不许炸。"""
    signature = inspect.signature(migrations.declared_embedding_profile, eval_str=True)

    assert signature.return_annotation is indexing.EmbeddingScope


def test_the_whole_module_has_no_unevaluable_annotation_left():
    """一枚文件级清扫：`app/db/migrations.py` 里任何注解都不许再是哑弹。

    只钉 `declared_embedding_profile` 会漏掉同类的下一个：这枚扫全部模块级函数与类的
    方法，逐条真求 `get_type_hints`。谁再把注解指向一枚本模块拿不到的名字，红在这里。
    """
    targets = [
        obj
        for obj in vars(migrations).values()
        if callable(obj) and getattr(obj, "__module__", "") == migrations.__name__
    ]
    for klass in (
        value for value in vars(migrations).values()
        if inspect.isclass(value) and value.__module__ == migrations.__name__
    ):
        targets.extend(
            method for method in vars(klass).values()
            if isinstance(method, (classmethod, staticmethod)) or inspect.isfunction(method)
        )

    assert targets, "扫不到任何目标 = 这枚件在空转"
    broken = []
    for target in targets:
        function = getattr(target, "__func__", target)
        try:
            typing.get_type_hints(function)
        except Exception as exc:  # noqa: BLE001 - 这里要的正是在 NameError 之外的全部失败
            broken.append((target.__qualname__, type(exc).__name__, str(exc)))

    assert broken == [], broken


# ------------------------------------------------- 新增那条 import 的成环棘轮（零运行期代价）

APP_PACKAGE = REPO_ROOT / "app"


def _module_path(dotted: str) -> Path:
    return APP_PACKAGE.joinpath(*dotted.split(".")[1:])


def _top_level_app_imports(path: Path):
    """一枚文件**模块级**会拉进来的 app 内模块（含父包 __init__，它们同样会被执行）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    resolved = []
    for name in names:
        if not name.startswith("app"):
            continue
        parts = name.split(".")
        for depth in range(1, len(parts) + 1):
            prefix = ".".join(parts[:depth])
            candidate = _module_path(prefix)
            if candidate.with_suffix(".py").exists() or (candidate / "__init__.py").exists():
                resolved.append(prefix)
        package = _module_path(".".join(parts[:-1]))
        if package.name and (package / "__init__.py").exists():
            resolved.append(".".join(parts[:-1]))
    return sorted(set(resolved))


def test_the_new_import_edge_stays_a_leaf_and_cannot_reach_app_db():
    """从 `app.rag.indexing` 出发，沿**模块级** app import 走闭包，不许走回 `app.db.*`。

    这是"补 import 会不会造出新循环导入"那句理由的可执行版本：`app/rag/indexing.py` 今天
    只拉 stdlib + `app.common.logger`，所以这枚闭包小得能列出来；哪天有人往 indexing.py
    的模块级塞一枚会回指 `app.db` 的 import，这枚棘轮当场红，而不是等到运维跑 migrate。
    """
    seen = set()
    frontier = ["app.rag.indexing"]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        module_file = _module_path(current)
        candidates = [module_file.with_suffix(".py"), module_file / "__init__.py"]
        path = next((candidate for candidate in candidates if candidate.exists()), None)
        if path is None:
            continue
        frontier.extend(_top_level_app_imports(path))

    assert "app.rag.indexing" in seen
    assert not [name for name in seen if name == "app.db" or name.startswith("app.db.")], \
        f"新增的 import 边把 app.db 拉进了自己的闭包：{sorted(seen)}"
