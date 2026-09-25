"""R231 判据③：三处读同一份解析 —— 「env 让读路径走 pgvector、版本台账还写着 chroma」这一格堵死。

R59b 把 `INDEX_BACKEND` 从"只是个标签"升成"决定谁答语义检索的开关"，同时留下了两处**裸读**
这枚常量的地方：`PublicationOutcome.as_dict()` 的 `"backend"`（交回给调用方的台账出料）与
`IndexPublisher.publish()` 喂给 `IndexRegistry.create_version()` 的那一枚（落进版本记录的
backend 列）。只给 `read_backend()` 加 env 钩子，就会造出半切换态：读路径已经换引擎，台账
还在盖旧引擎的名字 —— 而那正是召回对照最省事的假读数形状。

所以本件对每一枚输入形状同时读四个数：

1. `read_backend()` —— 读路径的答复；
2. `outcome.as_dict()["backend"]` —— 台账出料（原 `:1076` 那处）；
3. `registry.current(...).backend` —— `create_version` 真正落账的值（原 `:1592` 那处）；
4. 盘上那份 index-versions.json 里的 backend —— 3 的持久化证据，不是内存里的自我确认。

再加一枚 AST 棘轮：`app/rag/indexing.py` 里除了 `read_backend` 自己，谁都不许再裸读那枚常量。

全程不连库、不打模型：发布走 `IndexPublisher(registry, store=None)`，与 R22 那批件同一条路，
镜像那一腿本来就降级为 warning，台账仍然照写。
"""

import ast
import json
from pathlib import Path

import pytest

from app.rag import indexing

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEXING_SOURCE = REPO_ROOT / "app" / "rag" / "indexing.py"

#: (env 值, 模块常量值, 期望) —— None 表示"这一路没人说话"。每一格都要过四个读数。
SHAPES = [
    (None, None, "chroma"),              # shipped 默认：谁都没翻
    ("pgvector", None, "pgvector"),      # 只有 env —— 判据①，也是最容易一半生效的形状
    (None, "pgvector", "pgvector"),      # 只有常量 —— R59b 那批钉的老路
    ("pgvector", "chroma", "pgvector"),  # 同时给且不一致：env 赢
    ("chroma", "pgvector", "chroma"),    # 不一致反过来：仍是 env 赢
    (" PGVECTOR ", None, "pgvector"),    # 大小写与空格
    ("", None, "chroma"),                # 空串＝没说话
    ("", "pgvector", "pgvector"),        # 空串落回常量
    ("pg_vetcor", None, "chroma"),       # 非法：回落 shipped 引擎
    ("pg_vetcor", "pgvector", "chroma"),  # 非法：常量不许救场
    ("pgvector", "pg_vetcor", "pgvector"),  # 常量坏了不影响 env 的答复
]


def _four_readings(monkeypatch, metadata_path, env, constant):
    """喂一枚输入形状，交回四个读数（读路径 / 台账出料 / 落账值 / 盘上那份）。"""
    if env is None:
        monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    else:
        monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, env)
    monkeypatch.setattr(
        indexing, "INDEX_BACKEND",
        indexing.INDEX_BACKEND_DEFAULT if constant is None else constant)

    switch = indexing.read_backend()
    registry = indexing.IndexRegistry(metadata_path)
    outcome = indexing.IndexPublisher(registry, store=None).publish(
        indexing.DocumentIndexPublication(
            filename="policy.txt", version=1, chunks=("一段正文",)))
    record = registry.current(outcome.index_id).backend
    sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))

    return {
        "switch": switch,
        "as_dict": outcome.as_dict()["backend"],
        "create_version": record,
        "sidecar": [row["backend"] for row in sidecar["versions"]],
        "enabled": indexing.pgvector_reads_enabled(),
    }


# ------------------------------------------------------------------ 同值性本体


@pytest.mark.parametrize("env,constant,expected", SHAPES)
def test_the_ledger_and_the_read_path_cannot_be_set_apart(monkeypatch, tmp_path,
                                                          env, constant, expected):
    """判据③的正身：任何输入下四个读数同源，且 `pgvector_reads_enabled()` 跟着一起动。

    把 `as_dict` 或 `create_version` 任一处改回裸常量：带 env 的那几格立刻红（"读路径已
    切、台账仍写旧引擎"就是它要抓的东西）；把优先级反过来：不一致那两格红。
    """
    readings = _four_readings(monkeypatch, tmp_path / "index-versions.json", env, constant)

    assert readings["switch"] == expected
    assert readings["as_dict"] == expected, "台账出料与读路径不同源"
    assert readings["create_version"] == expected, "create_version 落的账与读路径不同源"
    assert readings["sidecar"] == [expected], "写进盘上的版本记录与读路径不同源"
    assert readings["enabled"] is (expected == indexing.PGVECTOR_BACKEND)


@pytest.mark.parametrize("env,constant,expected", SHAPES)
def test_the_published_record_survives_a_reload_with_the_same_backend(
        monkeypatch, tmp_path, env, constant, expected):
    """账要同值得跨进程成立：另开一枚 registry 重读盘上那份，backend 不许在重读时改写。

    这条防的是另一类半切换 —— 落账时写对了，读台账时又按"当前开关"现算一遍，于是历史
    记录会跟着开关一起变色。盘上那一行是当时的事实，`as_dict()` 才是现在的事实。
    """
    metadata = tmp_path / "index-versions.json"
    _four_readings(monkeypatch, metadata, env, constant)

    reopened = indexing.IndexRegistry(metadata)

    assert [row.backend for row in reopened._versions.values()] == [expected]
    assert reopened.current(indexing.document_index_id("policy.txt")).backend == expected


# ------------------------------------------------------------------ AST 棘轮


class _BackendReader(ast.NodeVisitor):
    """记下每个作用域里对裸 `INDEX_BACKEND` 的读，以及对 `read_backend()` 的调用。"""

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

    def visit_Call(self, node):
        called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if called == "read_backend":
            self.resolver_calls.setdefault(tuple(self.stack), 0)
            self.resolver_calls[tuple(self.stack)] += 1
        self.generic_visit(node)


def _scan():
    visitor = _BackendReader()
    visitor.visit(ast.parse(INDEXING_SOURCE.read_text(encoding="utf-8")))
    return visitor


def test_only_the_resolver_reads_the_bare_constant():
    """`app/rag/indexing.py` 里裸读 `INDEX_BACKEND` 的作用域必须只剩 `read_backend` 一枚。

    这是判据③的"永远"那一半：同值性用例证今日，这枚棘轮证明天 —— 谁再往任何地方写
    `INDEX_BACKEND` 当读点，这条当场红，而不是等到某次排窗才发现台账在骗人。
    它也防"钩子被整个摘掉"：钩子一没，`read_backend` 里就没有读了，集合变空照样红。
    """
    scopes = {name[-1] if name else "<module>" for name in _scan().raw_reads}

    assert scopes == {"read_backend"}, sorted(scopes)


def test_the_two_ledger_sites_ask_the_resolver():
    """两处台账读点必须**真的在调用** `read_backend()`，而不是被删成字面量后蒙过上一条。"""
    calls = _scan().resolver_calls
    holders = {name[-1] for name, count in calls.items() if count}

    assert {"as_dict", "publish"} <= holders, sorted(holders)


# ------------------------------------------------------------------ 只报不动的一格


def test_the_hot_index_scope_key_still_names_the_constant_not_the_env(monkeypatch):
    """记录一处本班无权修的分歧（写域禁改 `app/rag/hot_index.py`），钉成"现状"而非"应该"。

    `hot_index.current_scope_key()` 的首轴读的是裸常量（app/rag/hot_index.py:675、:678），
    不是 `read_backend()`。加了 env 钩子之后两者可以不同值：env=pgvector 时读路径答
    pgvector，热集缓存键的首轴仍写 chroma。本窗不出错 —— 切读态下热集整层让路
    （`retriever._hot_hits` 在 app/rag/retriever.py:1129 直接 return None，R59b 有钉），
    所以它只是一枚暂时没人当引擎身份读的首轴。但它是种子：谁哪天让热集在切读态下重新服务，
    或把首轴当"当前引擎"读，这一格必须当场红，然后按 R231 交回单改成 `read_backend()`。
    """
    from app.rag import hot_index

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, "pgvector")
    monkeypatch.setattr(indexing, "INDEX_BACKEND", indexing.INDEX_BACKEND_DEFAULT)

    assert indexing.read_backend() == "pgvector"
    assert hot_index.current_scope_key()[0] == indexing.INDEX_BACKEND_DEFAULT
