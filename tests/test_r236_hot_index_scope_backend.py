"""R236 T2：热集口径键的首轴改读 `read_backend()`，与读路径同源。

R231 把读路径、版本台账出料、publication 落账三处收成同一个 `read_backend()`，唯独
`hot_index.current_scope_key()` 的首轴还裸读常量 `INDEX_BACKEND`（app/rag/hot_index.py:675、
:678）。env 钩子只长在 `read_backend()` 上 ⇒ `INDEX_BACKEND=pgvector` 合闸那一刻，读路径答
pgvector、热集键仍写 chroma。今天不出错（切读态下热集整层让路，`retriever._hot_hits` 在
app/rag/retriever.py:1129 直接 return None），但它是 R231 明写的种子，本单按交回单反引。

形状表沿用 R231 的 `test_r231_no_half_switch.SHAPES` 风格：env 不设时首轴仍是 chroma，
env 设了 pgvector 时首轴跟着走；两值不一致时 env 赢；非法值回落到 shipped 引擎。
再加一枚 AST 棘轮：`app/rag/hot_index.py` 里不许再有裸读 `INDEX_BACKEND` 的地方，
而 `current_scope_key` 必须**真的在调用** `read_backend()`。

顺带钉住"零语义夹带"：改的只有首轴的取材处，元组的另外三轴（模型 / 维度 / 版本 id）
仍然逐字来自 `configured_embedding_scope()`，热集键的形状一格没变。
"""
import ast
from pathlib import Path

import pytest

from app.rag import hot_index, indexing

REPO_ROOT = Path(__file__).resolve().parents[1]
HOT_INDEX_SOURCE = REPO_ROOT / "app" / "rag" / "hot_index.py"

#: (env 值, 模块常量值, 期望) —— None 表示"这一路没人说话"。与 R231 同表同序。
SHAPES = [
    (None, None, "chroma"),                 # shipped 默认：谁都没翻
    ("pgvector", None, "pgvector"),         # 只有 env —— 最容易一半生效的形状
    (None, "pgvector", "pgvector"),         # 只有常量
    ("pgvector", "chroma", "pgvector"),     # 同时给且不一致：env 赢
    ("chroma", "pgvector", "chroma"),       # 不一致反过来：仍是 env 赢
    (" PGVECTOR ", None, "pgvector"),       # 大小写与空格
    ("", None, "chroma"),                   # 空串＝没说话
    ("", "pgvector", "pgvector"),           # 空串落回常量
    ("pg_vetcor", None, "chroma"),          # 非法：回落 shipped 引擎
    ("pg_vetcor", "pgvector", "chroma"),    # 非法：常量不许救场
    ("pgvector", "pg_vetcor", "pgvector"),  # 常量坏了不影响 env 的答复
]


def _backend_of_scope_key(monkeypatch, env, constant):
    """喂一枚输入形状，交回三个读数：解析器 / 热集首轴 / 热集整键。"""
    if env is None:
        monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    else:
        monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, env)
    monkeypatch.setattr(
        indexing, "INDEX_BACKEND",
        indexing.INDEX_BACKEND_DEFAULT if constant is None else constant)

    return indexing.read_backend(), hot_index.current_scope_key()


@pytest.mark.parametrize("env,constant,expected", SHAPES)
def test_the_hot_index_scope_key_moves_with_the_read_path(monkeypatch, env, constant, expected):
    """判据③的形状钉：任何输入下首轴 == `read_backend()` == 期望值。"""
    switch, scope_key = _backend_of_scope_key(monkeypatch, env, constant)

    assert switch == expected
    assert scope_key[0] == expected, "热集首轴与读路径不同源"


@pytest.mark.parametrize("env,constant,expected", SHAPES)
def test_only_the_first_axis_moved(monkeypatch, env, constant, expected):
    """零语义夹带：另外三轴仍是 R22 口径源的原样，元组长度也没变。"""
    _switch, scope_key = _backend_of_scope_key(monkeypatch, env, constant)
    scope = indexing.configured_embedding_scope()

    assert len(scope_key) == 4
    assert scope_key[1:] == (scope.embedding_model, scope.dimension, "")


def test_the_version_id_axis_is_untouched(monkeypatch):
    """带 index_version_id 进来时仍旧落在第四轴上，首轴改源不该碰它。"""
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)

    assert hot_index.current_scope_key(index_version_id="v9")[3] == "v9"


# ------------------------------------------------------------------------ AST 棘轮

class _BackendReader(ast.NodeVisitor):
    """记下 `app/rag/hot_index.py` 里对裸 `INDEX_BACKEND` 的读，与 `read_backend()` 的调用。"""

    def __init__(self):
        self.stack = []
        self.raw_reads = []
        self.resolver_calls = {}

    def _enter(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _enter
    visit_AsyncFunctionDef = _enter
    visit_ClassDef = _enter

    def visit_Name(self, node):
        if node.id == "INDEX_BACKEND" and isinstance(node.ctx, ast.Load):
            self.raw_reads.append(tuple(self.stack))

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.name == "INDEX_BACKEND":
                self.raw_reads.append((node.lineno, "import"))
        self.generic_visit(node)

    def visit_Call(self, node):
        called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if called == "read_backend":
            self.resolver_calls.setdefault(tuple(self.stack), 0)
            self.resolver_calls[tuple(self.stack)] += 1
        self.generic_visit(node)


def _scan():
    visitor = _BackendReader()
    visitor.visit(ast.parse(HOT_INDEX_SOURCE.read_text(encoding="utf-8")))
    return visitor


def test_hot_index_no_longer_reads_the_bare_constant():
    """这枚文件里不许再有任何一处读 `INDEX_BACKEND` 本体（含 import 位）。

    R231 的棘轮只管 `app/rag/indexing.py`，那一枚的作用域不会覆盖这里 —— 所以反引之后
    要在这一侧另起一枚，否则"首轴改回常量"没有任何东西会红。
    """
    assert _scan().raw_reads == [], _scan().raw_reads


def test_current_scope_key_actually_asks_the_resolver():
    """正向半枚：首轴必须**真的在调用** `read_backend()`，不是被改成字面量蒙过上一条。"""
    holders = {name[-1] for name, count in _scan().resolver_calls.items() if count}

    assert "current_scope_key" in holders, sorted(holders)
