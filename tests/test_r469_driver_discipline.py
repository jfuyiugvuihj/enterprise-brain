# -*- coding: utf-8 -*-
"""R469 常驻钉：驱动件只走那一枚边界、只落那一枚写点，且不许把真源量抄成第二份。

两本在册纪律在这里落地（AGENTS.md + R393「数抄进第二处就一定会漂」）：
* 连库只能经 `app.db.connection`（R238 的棘轮，本件不重写扫描器，直接复用
  `tests/test_r238_bare_connect_ratchet.py` 的 `readings()`）；生产会话的只读标志必须先于
  第一条取数语句落地；写句在整个文件里只许出现一枚，且只可能落在沙盒库的在册前缀行上。
* 候选宽度（`hnsw.ef_search`）、语料前缀、来历标签、距离算符、维度、池子规模——这些量的
  真源分别是 `app.rag.pg_store` 与 `scripts/r59c_sandbox_corpus.py`，本单两件里一枚字面量都不许有。

为什么值得常驻：本单的读数一旦漂（连到宿主那台野 PG、或前缀/标签抄错），交回去的就是
一枚假绿；而这两样都只能靠静态钉住姿势，量一次数看不出来。

零真库、零容器、零模型：只读源码文本与 AST，跑两枚纯函数（`mask_url` / `swap_database`）。
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
for _entry in (str(REPO_ROOT), str(TESTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import test_r238_bare_connect_ratchet as r238   # 在册扫描器，本件不重写一遍

SCRIPTS_DIR = REPO_ROOT / "scripts"
DRIVER_PATH = SCRIPTS_DIR / "r469_sandbox_scope_readout.py"
LIB_PATH = SCRIPTS_DIR / "r469_readout_lib.py"
READOUT_PATH = REPO_ROOT / "docs" / "testing" / "r469-sandbox-scope-readout-2026-09-28.md"
TICKET_SCRIPTS = (DRIVER_PATH, LIB_PATH)
WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE")
FAKE_SECRET = "r469-pytest-not-a-real-password"
FAKE_URL = "postgresql://r469_user:" + FAKE_SECRET + "@127.0.0.1:1/r469_db?connect_timeout=1"


def _load(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


driver = _load("r469_sandbox_scope_readout", DRIVER_PATH)
lib = _load("r469_readout_lib", LIB_PATH)


def _r59c():
    import scripts.r59c_sandbox_corpus as module

    return module


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.AST, name: str):
    found = next((node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == name), None)
    assert found is not None, "源码里找不到 " + name + "()，本钉的口径已过期"
    return found


def _call_name(node) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _call_lines(scope: ast.AST, name: str) -> list:
    """`scope` 里所有对该裸名函数的调用行号，按出现顺序。"""
    return sorted(node.lineno for node in ast.walk(scope)
                  if isinstance(node, ast.Call) and _call_name(node) == name)


def _stmt_line(scope: ast.AST, pattern: str) -> int:
    """`scope` 里第一条 unparse 后匹配 pattern 的语句行号（AST 取，不用文本 index 猜）。"""
    needle = re.compile(pattern, re.S)
    for node in getattr(scope, "body", []):
        if needle.search(ast.unparse(node)):
            return int(node.lineno)
    raise AssertionError("驱动里找不到这条语句：" + pattern)


def _literal_text(node) -> str:
    """把拼接出来的语句还原成人读的那句 SQL；非字面量（符号、变量）交回空串。"""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else ""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_text(node.left) + _literal_text(node.right)
    if isinstance(node, ast.JoinedStr):
        return "".join(_literal_text(part) for part in node.values)
    if isinstance(node, ast.FormattedValue):
        return "%s"
    return ""


def _executed_statements(path: Path) -> list:
    """这个文件真正发出去的每一条语句：``.execute(...)`` / ``.executemany(...)`` 的第一枚实参。"""
    out = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("execute", "executemany") or not node.args:
            continue
        first = node.args[0]
        pure = isinstance(first, (ast.Constant, ast.BinOp, ast.JoinedStr))
        out.append({"line": int(node.lineno), "text": _literal_text(first),
                    "symbol": "" if pure else ast.unparse(first)})
    return out


def _string_constants(path: Path) -> set:
    return {node.value for node in ast.walk(_tree(path))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def _int_constants(path: Path) -> set:
    return {node.value for node in ast.walk(_tree(path))
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
            and not isinstance(node.value, bool)}


# ================================================= T7：只走那一枚边界


def test_the_driver_reaches_the_database_only_through_the_boundary() -> None:
    """T7：本单两件在 R238 棘轮上的读数＝空集；连接只从 `app.db.connection` 来。"""
    sources = {path.relative_to(REPO_ROOT).as_posix(): path.read_text(encoding="utf-8")
               for path in TICKET_SCRIPTS}
    assert r238.readings(sources) == set(), "本单长出了裸 connect：" + str(sorted(sources))
    imports = []
    for path in TICKET_SCRIPTS:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(str(node.module))
    assert not [name for name in imports if name.split(".")[0] in
                ("psycopg", "psycopg2", "psycopg_binary", "psycopg_pool")], imports

    opener = _func(_tree(DRIVER_PATH), "open_connection")
    fetched = {str(node.module): {alias.name for alias in node.names}
               for node in ast.walk(opener) if isinstance(node, ast.ImportFrom)}
    assert fetched.get("app.db.connection", set()) >= {"open_connection",
                                                      "parse_database_settings"}, fetched
    calls = [node for node in ast.walk(opener)
             if isinstance(node, ast.Call) and _call_name(node) == "boundary_open"]
    assert len(calls) == 1, "唯一连接入口不该分叉"
    assert len(calls[0].args) == 1 and not calls[0].keywords, (
        "边界函数只吃 settings 一枚位置参数；多带参数＝在边界外面自造连法")


def test_the_read_only_flag_lands_before_the_first_production_read() -> None:
    """生产会话：`SET ... READ ONLY` 由 `prove_read_only()` 发，且它排在任何一条取数之前。"""
    tree = _tree(DRIVER_PATH)
    prover = _func(tree, "prove_read_only")
    statements = _executed_statements(DRIVER_PATH)
    set_lines = [row["line"] for row in statements
                 if "READ ONLY" in row["text"].upper()]
    assert len(set_lines) == 1, set_lines
    assert prover.lineno <= set_lines[0] < prover.end_lineno, (
        "只读标志不在 prove_read_only() 里——它可能被挪到取数之后")
    main = _func(tree, "main")
    proven = _call_lines(main, "prove_read_only")
    assert len(proven) == 1, proven
    reads = [min(_call_lines(main, name)) for name in
             ("counts", "production_snapshot", "accounts_block")]
    assert proven[0] < min(reads), (proven, reads)
    assert _stmt_line(main, r"transaction_read_only.\]\s*!=\s*.on.") < min(reads), (
        "只读自证没拦在取数之前：连到能写的库也照样读数")
    assert _call_lines(main, "open_connection")[0] < proven[0]


def test_the_sandbox_guards_fire_before_the_only_write() -> None:
    """三条守卫（库名逐字相等 / 在册前缀零残留 / preflight 早退）都必须排在写点之前。"""
    tree = _tree(DRIVER_PATH)
    main = _func(tree, "main")
    writes = _call_lines(main, "write_sandbox_rows")
    assert len(writes) == 1, writes
    guard_db = _stmt_line(main, r"sandbox_identity\[.database.\]\s*!=\s*SANDBOX_DB")
    guard_leftover = _stmt_line(
        main, r"int\(sandbox_before\[.prefixed_rows.\]\)\s*!=\s*0")
    guard_preflight = _stmt_line(main, r"args\.mode\s*==\s*.preflight.")
    assert max(guard_db, guard_leftover, guard_preflight) < writes[0], (
        guard_db, guard_leftover, guard_preflight, writes)
    call = next(node for node in ast.walk(main)
                if isinstance(node, ast.Call) and _call_name(node) == "write_sandbox_rows")
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "sandbox", (
        "唯一写点的第一枚参数必须是沙盒会话；这里是 production 就等于改真数据")
    for name in ("delete_sandbox_rows", "refuse"):
        _func(tree, name)


def test_the_write_statement_is_the_only_one_and_the_delete_comes_from_the_product() -> None:
    """执行口径里只许有一枚写句；删除语句必须用产品那条 `_DELETE_VECTOR_SQL`，不手抄。"""
    statements = _executed_statements(DRIVER_PATH)
    assert statements, "驱动里一条语句都没扫到，这钉空咬"
    written = [row for row in statements if tuple(row["text"].lstrip().upper().split())
               and row["text"].lstrip().upper().split()[0] in WRITE_VERBS]
    assert len(written) == 1, written
    assert written[0]["text"].upper().startswith("INSERT"), written[0]
    writer = _func(_tree(DRIVER_PATH), "write_sandbox_rows")
    assert writer.lineno <= written[0]["line"] < writer.end_lineno, written[0]
    others = [row for row in statements if row is not written[0]]
    for row in others:
        head = row["text"].lstrip().upper().split()[0] if row["text"] else ""
        assert head in ("SELECT", "SET", "SHOW", ""), (row, head)
    delete = _func(_tree(DRIVER_PATH), "delete_sandbox_rows")
    assert "pg_store._DELETE_VECTOR_SQL" in ast.unparse(delete), ast.unparse(delete)
    assert not [row for row in statements if row["text"].upper().startswith("DELETE")]


def test_the_driver_takes_its_dsn_from_the_house_and_not_from_itself() -> None:
    """DSN 只从 `DATABASE_URL` 取，两件里不许出现一枚自造连接串（野 PG 就是这么连上的）。"""
    main = _func(_tree(DRIVER_PATH), "main")
    assert _stmt_line(main, r"getenv..DATABASE_URL") > 0
    for path in TICKET_SCRIPTS:
        assert not [text for text in _string_constants(path)
                    if text.startswith("postgresql://") or text.startswith("postgres://")], path
    swapped = _call_lines(main, "swap_database")
    assert len(swapped) == 1, "库名只许就地换一次，落点＝沙盒库"
    assert _stmt_line(main, r"open_connection.url.") < _stmt_line(main, r"open_connection.sandbox_url.")


def test_the_ticket_opens_no_model_and_adds_no_new_chroma_dependency() -> None:
    """本单两件零模型、零新 Chroma 依赖（AGENTS.md 向量库口径 + 派工单硬禁）。"""
    banned_roots = {"chromadb", "ollama", "requests", "httpx", "openai"}
    banned_modules = {"app.rag.retriever", "app.models", "app.data"}
    for path in TICKET_SCRIPTS:
        for node in ast.walk(_tree(path)):
            names = ([alias.name for alias in node.names]
                     if isinstance(node, ast.Import) else
                     [str(node.module)] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name.split(".")[0] not in banned_roots, (path, name)
                assert name not in banned_modules, (path, name)
    for path in TICKET_SCRIPTS:
        used = {_call_name(node) for node in ast.walk(_tree(path)) if isinstance(node, ast.Call)}
        assert used.isdisjoint({"DocumentRetriever", "RetrievalPipeline", "PersistentClient",
                                "embed", "embeddings"}), (path, sorted(used))


# =========================================== T8：真源量不许在两件里被抄成第二份


def test_no_ticket_carries_a_second_copy_of_a_true_source_number() -> None:
    """T8：候选宽度、前缀、来历标签、距离算符、seed 算式、池子规模——一律现读，不落字面量。"""
    r59c = _r59c()
    prefix = os.path.commonprefix([row["vector_id"] for row in
                                   r59c.build_corpus(len(r59c.DEPARTMENTS) *
                                                     len(r59c.CLASSIFICATIONS) * 2,
                                                     dimension=r59c.VECTOR_DIMENSION
                                                     )["chunks"]])
    assert prefix.endswith("-"), prefix
    forbidden = {r59c.EMBEDDING_MODEL_LABEL, r59c.DISTANCE_FUNCTION, r59c.SCHEMA, prefix}
    r59c_big = {value for value in _int_constants(Path(r59c.__file__)) if value >= 1000}
    assert len(r59c_big) >= 2, r59c_big
    for path in TICKET_SCRIPTS:
        hit = sorted(forbidden & _string_constants(path))
        assert hit == [], (path, hit)
        big = sorted(_int_constants(path) & r59c_big)
        assert big == [], (path, "seed 算式里的数被抄进了本单：" + str(big))
        sized = sorted(value for value in _int_constants(path) if value >= 1000)
        assert sized == [], (path, "系统量级的数字不该出现在本单两件里：" + str(sized))

    tree = _tree(DRIVER_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if "ef_search" in ast.unparse(target).lower():
                    assert isinstance(node.value, ast.Call), (
                        "候选宽度被写成字面量：" + ast.unparse(node))
    calls = {_call_name(node.func) for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "configured_hnsw_ef_search" in calls, (
        "本单没向真源取候选宽度——那批复数就站在另一个系统上")


def test_the_two_in_register_ledgers_have_to_agree_on_the_vector_table() -> None:
    """表名/库名这类量，驱动现场把两本在册账对一遍，而不是各抄一份再各跑各的。"""
    main = _func(_tree(DRIVER_PATH), "main")
    assert _stmt_line(main, r"r59c.TABLE != pg_store.DEFAULT_VECTOR_TABLE") > 0
    assert _stmt_line(main, r"PRODUCTION_DB not in r59c.PRODUCTION_DB_NAMES") > 0
    assert "SANDBOX_DB" in ast.unparse(main)
    lib_names = {target.id for node in ast.walk(_tree(LIB_PATH)) if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name)}
    assert "CORE_INVARIANT_TABLES" in lib_names


# ================================================ 口令一律 mask，账上只见形状


def test_mask_url_hides_the_credential_and_keeps_the_route() -> None:
    masked = driver.mask_url(FAKE_URL)
    assert FAKE_SECRET not in masked, masked
    assert "***" in masked and "r469_user" in masked and "127.0.0.1:1" in masked, masked
    assert masked.endswith("/r469_db?connect_timeout=1"), masked
    assert driver.mask_url("") == "<unset>"
    assert driver.mask_url("plain-word") == "<unset>"


def test_swap_database_moves_only_the_name_and_refuses_a_shape_it_does_not_know() -> None:
    moved = driver.swap_database(FAKE_URL, driver.SANDBOX_DB)
    assert moved.endswith("/" + driver.SANDBOX_DB + "?connect_timeout=1"), moved
    assert "r469_db" not in moved
    assert driver.swap_database(FAKE_URL, driver.PRODUCTION_DB).endswith(
        "/" + driver.PRODUCTION_DB + "?connect_timeout=1")
    with pytest.raises(SystemExit) as caught:
        driver.swap_database("nonsense-without-slash", driver.SANDBOX_DB)
    text = " ".join(str(item) for item in caught.value.args)
    assert FAKE_SECRET not in text and "<unset>" in text, text


def test_the_in_tree_readout_carries_no_credential_and_no_bare_dsn() -> None:
    """盘上那份读数表：只许出现 masked 过的 URL，一条裸 DSN 都不许有。"""
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    secrets = [match.group(2) for match in
               re.finditer(r"://([^/\s:@]+):([^/\s@]+)@", markdown)]
    assert secrets, "表里没有一枚记了主的 DSN——口令没 mask，是真没连"
    assert set(secrets) == {"***"}, "表里出现了不是 *** 的口令段：" + str(sorted(set(secrets)))
    evidence = lib.extract_evidence(markdown)
    urls = evidence["run"]["database_url_masked"]
    assert set(urls) == set(lib.ARMS)
    for url in urls.values():
        assert "***" in url, url
        assert FAKE_SECRET not in url
    assert driver.PRODUCTION_DB in urls[lib.ARM_PRODUCTION]
    assert driver.SANDBOX_DB in urls[lib.ARM_SANDBOX]
