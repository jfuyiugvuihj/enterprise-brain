# -*- coding: utf-8 -*-
r"""R389 · 那 13 枚裸 connect 是被**迁走**的，不是被**记账**的。

病灶（主树 @5f19e3f 实测，事故 #56）：R382 那批切读取证脚本并树时只跑了它自己的 16 枚钉
加文档守卫，没跑 ratchet 这一族，于是 ``scripts/r382_*.py`` 里长出 13 枚裸
``psycopg.connect``，把 ``tests/test_r238_bare_connect_ratchet.py``（14 红）与
``tests/test_r346_line_ledger_is_derived_not_copied.py``（23 红）两枚常驻钉一起染红。
政策白纸黑字在 ``app/notifications/states.py`` 那句"新模块不许自带裸 psycopg.connect——
全仓只供出 app/db/connection.py 这一枚边界"。

本件守的是**修法**而不是**结果**，因为把两枚钉改绿有两条路，而其中一条是假的：

  ① 现场扫描对 ``scripts/r382_*.py`` 全树零命中（真迁走的直接证据）；
  ② 每枚文件的边界调用枚数与形状对得上那 13 格，且 ``open_connection`` 只吃一枚位置参数
     ——脚本不许再把 ``options=`` / ``row_factory=`` 这类 kwargs 塞进驱动，也不许自己
     ``import psycopg`` 再连（那是第二套连接法，正是 R238 立边界时要拆掉的东西）；
  ③ 边界符号只能来自 ``app.db.connection``；驱动模块里搬出来的 ``connect`` 一枚都不许有；
  ④ 反"重录基线"：``BASELINE`` 仍是 15 格、**一枚 ``r382`` 都不许进册**，现场读数必须与
     账本全等，逐根计数仍是 app 14 + scripts 1。抬上限这条路在这里没有落脚点；
  ⑤⑥ 两处**行为**看守：``read_pg`` 的只读证明仍排在第一条语句之前（报告里
     ``transaction_read_only`` 那一格靠它才读得出 "on"），``r382_probe`` 的
     ``row_factory`` 仍排在第一条语句之前（它决定 JSON 里是对象还是数组）。
     这两枚是"改怎么连、不改连上之后干什么"的唯一危险点，所以钉顺序，不钉行号；
  ⑦ 运行时自证：把驱动 ``connect`` 换成记录器，真调三枚纯 DB 助手
     （``read_pg`` / ``database_identity`` / ``pg_label_map``），必须看见驱动只被边界调用
     一次、参数只有 conninfo、只读标志先于任何语句、且发出去的全是只读语句。

零真库、零写入：⑦ 用 monkeypatch 换掉驱动入口，一次 socket 都不发；其余只读源码文本与 AST。
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import psycopg
import pytest

import test_r238_bare_connect_ratchet as r238

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BOUNDARY = "app.db.connection"

#: 迁走之前那 13 枚落点在七枚文件里的分布。记的是**枚数**，不是行号（R346 的教训）。
MIGRATED_SITES = {
    "r382_index_scope.py": 1,
    "r382_leg_compare.py": 2,
    "r382_matched_corpus.py": 2,
    "r382_metric_attribute.py": 2,
    "r382_probe.py": 3,
    "r382_readpath_measure.py": 1,
    "r382_vector_parity.py": 2,
}
TOTAL_MIGRATED = 13

#: ⑦ 用的假 DSN：主机 127.0.0.1、端口 1（conftest 同一口径，落不到任何真库），
#: 而且驱动入口已被换掉，这一格连 socket 都不会发。
FAKE_URL = "postgresql://r389_pytest@127.0.0.1:1/r389_fake_db?connect_timeout=1"


# ------------------------------------------------------------------ 取证助手
def _paths() -> list[Path]:
    paths = sorted(SCRIPTS_DIR.glob("r382_*.py"))
    assert paths, f"{SCRIPTS_DIR} 下一枚 r382 脚本都没扫到，本件无从判定"
    return paths


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _source(name: str) -> str:
    return (SCRIPTS_DIR / name).read_text(encoding="utf-8")


def _rel_paths() -> list[str]:
    return [_rel(path) for path in _paths()]


def _func(tree: ast.AST, name: str):
    found = next((node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == name), None)
    assert found is not None, f"源码里找不到函数 {name}()，本钉的口径已经过期"
    return found


def _call_name(node) -> str:
    """``open_connection(...)`` 与 ``psycopg.connect(...)`` 都先剥成裸名字。"""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _boundary_blocks(source: str, func_name: str) -> list[ast.With]:
    """``func_name`` 里那些以 ``open_connection(...)`` 当上下文的 ``with`` 块，按行号排。"""
    tree = ast.parse(source)
    target = _func(tree, func_name)
    blocks = [
        node for node in ast.walk(target)
        if isinstance(node, ast.With) and node.items
        and _call_name(node.items[0].context_expr) == "open_connection"
    ]
    return sorted(blocks, key=lambda node: node.lineno)


def _assigned_attribute(stmt):
    """``conn.read_only = True`` 这种单目标赋值，交回 (属性名, 值的名字)。"""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = stmt.targets[0]
    if not isinstance(target, ast.Attribute):
        return None
    value = stmt.value
    value_name = value.id if isinstance(value, ast.Name) else repr(getattr(value, "value", value))
    return target.attr, value_name


def _imported_from(tree: ast.AST, module: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _loaded(name: str):
    """按文件路径装载一枚脚本（模块级只读 import，不跑 main）。"""
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location("r389_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ ① 现场扫描
@pytest.mark.parametrize("path", _paths(), ids=lambda path: path.name)
def test_the_r382_family_has_no_bare_connect_left(path: Path) -> None:
    """判据①：这七枚脚本里一枚边界之外的连接都不许剩下（扫的是 AST，不是文本）。"""
    rel = _rel(path)
    hits = r238.scan_source(rel, path.read_text(encoding="utf-8"))

    assert not hits, "仍不走边界：" + r238._located(hits, hits)


# ------------------------------------------------------ ②③ 边界形状与符号来源
@pytest.mark.parametrize("name,expected", sorted(MIGRATED_SITES.items()))
def test_every_migrated_site_asks_the_boundary_in_the_same_shape(name: str, expected: int) -> None:
    """13 枚落点逐枚点名：走的是 ``open_connection``，而且只吃一枚位置参数。"""
    source = _source(name)
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and _call_name(node.func) == "open_connection"]

    assert len(calls) == expected, f"{name}: 边界调用 {len(calls)} 枚，应为 {expected} 枚"
    for call in calls:
        assert len(call.args) == 1, f"{name}: 边界调用参数形状变了 {ast.dump(call)}"
        assert not call.keywords, f"{name}: 不许再往连接入口塞关键字参数 {call.keywords}"


@pytest.mark.parametrize("name", sorted(MIGRATED_SITES))
def test_the_scripts_import_the_boundary_and_never_the_driver_connect(name: str) -> None:
    """判据①的正面：符号来自 ``app.db.connection``；从驱动搬 ``connect`` 出来一枚都不许有。"""
    source = _source(name)
    tree = ast.parse(source)
    imported = _imported_from(tree, BOUNDARY)

    assert "open_connection" in imported, f"{name} 没有 import 边界的 open_connection"
    assert "parse_database_settings" in imported, f"{name} 没有 import 边界的 parse_database_settings"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in r238.DRIVER_ROOTS:
            assert all(alias.name != "connect" for alias in node.names), f"{name}: 从驱动搬 connect"
    assert not any(isinstance(node, ast.Import)
                   and any(alias.name == "psycopg" for alias in node.names)
                   for node in ast.walk(tree)), f"{name}: 还自己 import psycopg 干什么"


def test_the_migrated_count_is_the_one_the_gate_lost() -> None:
    """13 这个数字也要有出处：它就是棘轮当场报的"未入册"枚数之和。"""
    assert sum(MIGRATED_SITES.values()) == TOTAL_MIGRATED == 13, MIGRATED_SITES
    total = sum(len([node for node in ast.walk(ast.parse(_source(name)))
                     if isinstance(node, ast.Call) and _call_name(node.func) == "open_connection"])
                for name in MIGRATED_SITES)

    assert total == TOTAL_MIGRATED, total


# ------------------------------------------------------------- ④ 反"重录基线"
def test_the_ledger_did_not_grow_to_accommodate_the_r382_family() -> None:
    """判据①的硬禁：清单只许因真迁走而变小，不许因新长而变大，更不许把 r382 收进册。"""
    outside, _boundary = r238.scan_sources(r238.repo_sources())
    identities = {hit.identity for hit in outside}

    assert len(r238.BASELINE) == 15, len(r238.BASELINE)
    assert not [entry for entry in r238.BASELINE if "r382" in entry], r238.BASELINE
    assert identities == set(r238.BASELINE), (
        "现场读数与账本不再全等：要么长出了新的裸 connect，要么有人靠改数字把钉按绿")
    per_root: dict[str, int] = {}
    for hit in outside:
        root = hit.rel.split("/")[0]
        per_root[root] = per_root.get(root, 0) + 1
    assert per_root == {"app": 14, "scripts": 1}, per_root


# --------------------------------------------------------- ⑤⑥ 两处行为看守
def test_the_read_only_proof_still_precedes_the_first_statement() -> None:
    """``read_pg`` 的只读仍必须在第一条语句之前落下，报告里那一格才有读数。"""
    source = _source("r382_index_scope.py")
    blocks = _boundary_blocks(source, "read_pg")

    assert len(blocks) == 1, len(blocks)
    first = blocks[0].body[0]
    assert _assigned_attribute(first) == ("read_only", "True"), ast.dump(first)
    assert "transaction_read_only" in source, "证明只读的那一列不见了"
    assert "default_transaction_read_only" not in source, "connect 期注入 GUC 的旧写法回来了"


def test_the_probe_still_asks_for_dict_rows_before_the_first_statement() -> None:
    """``row_factory`` 决定 JSON 里是对象还是数组：它必须仍排在第一条语句之前。"""
    source = _source("r382_probe.py")
    blocks = _boundary_blocks(source, "main")

    assert len(blocks) == 3, len(blocks)
    assert _assigned_attribute(blocks[0].body[0]) == ("row_factory", "dict_row"), ast.dump(
        blocks[0].body[0])
    assert "from psycopg.rows import dict_row" in _source("r382_probe.py")
    for block in blocks[1:]:
        assert _assigned_attribute(block.body[0]) is None, "后两枚连接不该再改行工厂"


# ------------------------------------------------------------- ⑦ 运行时自证
class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def fetchone(self):
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


def _rows_for(sql: str):
    text = " ".join(sql.split())
    if "current_setting" in text:
        return [("eb_r59_sandbox", "r389_user", "on", "16.4")]
    if "department" in text:
        return [("chunk-1", "sales", 1)]
    if "indexdef" in text:
        return [("CREATE INDEX chunk_vectors_embedding_hnsw ON chunk_vectors "
                 "USING hnsw (embedding vector_l2_ops) WITH (m = 16, ef_construction = 64)",)]
    if "embedding_model" in text:
        return [("nomic-embed-text", 768, "l2")]
    return [(1008, "16.4")]


class _FakeConnection:
    """只装得下这三枚助手用到的那几样：execute / trace / read_only / row_factory。"""

    def __init__(self) -> None:
        self.trace: list[tuple] = []
        self.statements: list[str] = []
        self.row_factory = None
        self._read_only = None

    @property
    def read_only(self):
        return self._read_only

    @read_only.setter
    def read_only(self, value) -> None:
        self._read_only = value
        self.trace.append(("read_only", value))

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        self.trace.append(("exit", exc[0]))
        return False

    def execute(self, sql, params=None):
        head = " ".join(sql.split()).split()[0].upper()
        self.trace.append(("statement", head))
        self.statements.append(sql)
        return _FakeResult(_rows_for(sql))


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.connections: list[_FakeConnection] = []

    def connect(self, conninfo, **kwargs):
        self.calls.append((conninfo, kwargs))
        connection = _FakeConnection()
        self.connections.append(connection)
        return connection


@pytest.mark.parametrize(
    "module_name,func_name,expected_statements",
    [
        ("r382_index_scope", "read_pg", 6),  # ident / vectors / scope / indexes / ef_search / extversion
        ("r382_readpath_measure", "database_identity", 2),
        ("r382_matched_corpus", "pg_label_map", 1),
    ],
)
def test_the_driver_is_only_reached_through_the_boundary(module_name, func_name,
                                                         expected_statements, monkeypatch) -> None:
    """真调一次：驱动只被边界叫一次、参数只有 conninfo、发出去的全是只读语句。"""
    recorder = _Recorder()
    monkeypatch.setattr(psycopg, "connect", recorder.connect)
    module = _loaded(module_name)
    function = getattr(module, func_name)

    result = function(FAKE_URL, "label") if func_name == "read_pg" else function(FAKE_URL)

    assert len(recorder.calls) == 1, recorder.calls
    conninfo, kwargs = recorder.calls[0]
    assert conninfo == FAKE_URL, conninfo
    assert kwargs == {}, f"关键字参数从脚本 smuggle 进了驱动：{kwargs}"
    connection = recorder.connections[0]
    assert len(connection.statements) == expected_statements, connection.statements
    heads = [value for event, value in connection.trace if event == "statement"]
    assert set(heads) <= {"SELECT", "SHOW"}, heads
    assert result, f"{module_name}.{func_name}() 交回空读数"
    if func_name == "read_pg":
        assert connection.read_only is True, "只读没落在连接上"
        assert connection.trace[0] == ("read_only", True), connection.trace
        assert result["database"] == "eb_r59_sandbox", result