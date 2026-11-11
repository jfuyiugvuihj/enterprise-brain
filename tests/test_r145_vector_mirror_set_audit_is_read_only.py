"""R145 的红线本身也要可证伪：只读、零模型、不碰仓库里的 `chroma_db/`。

判据①②③④的读数形状在 `tests/test_r145_vector_mirror_set_audit_reads.py` 里；这枚文件钉的是
工单那三条 🔴 约束，用的是同一份 SQL —— 因为"我只读"这种话在回执里不值钱，值钱的是：

* 每一条要发出去的语句都过不了写关键字闸 ⇒ 直接抛，一个字节都不离开本机（首词白名单 + 关键字表）；
* 走工单指定的那条 docker 路线时，**每个会话**的完整脚本文本只有 BEGIN / SET TRANSACTION READ
  ONLY / SELECT…WITH / ROLLBACK 四种语句，`COMMIT` 一个都不出现，报告里连 transcript 都带上，
  谁都能重数一遍；
* psycopg 那条备用路线坐在一个只读事务里，收尾只有 `rollback()`，`commit()` 一被调用就报红；
* Chroma 侧的 client 永远只拿到 `%TEMP%` 副本的路径，仓库目录一个字节都不写（跑前跑后逐文件哈希）；
* 一整场审计跑完，`tests/conftest.py` 的宿主模型端口闸门上没有新记录 —— 这是"零 Ollama"的运行时
  证据，比 `grep -v ollama` 强，因为它连间接腿（`app/rag/retriever.py` 自己 urlopen 那条）都拦。

脚本刻意不 import `app/**`（`app.rag.pg_store` 会把 `app.rag.retriever` 连带模型的腿拖进来），
代价是表名/前缀/collection 名这类字面量在脚本里自持，所以最后有一组"现读写入侧源码"的对齐用例，
把这几枚字面量钉回唯一真源。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "audit_vector_mirror_sets.py"
RETRIEVER_PATH = ROOT / "app" / "rag" / "retriever.py"
INDEXING_PATH = ROOT / "app" / "rag" / "indexing.py"
PG_STORE_PATH = ROOT / "app" / "rag" / "pg_store.py"
MIGRATION_0010 = ROOT / "migrations" / "0010_pgvector_chunks.sql"


def _load_audit():
    spec = importlib.util.spec_from_file_location("r145_audit_read_only", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass 求值时要回查 sys.modules
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit()


def row_line(*values) -> str:
    cells = [AUDIT.NULL_SENTINEL if value is None else str(value) for value in values]
    return AUDIT.ROW_PREFIX + AUDIT.FIELD_SEP.join(cells)


def psql_stdout(query, rows) -> str:
    """照 psql -tA 的样子产文本：还夹进命令标签，验证解析边界不是"顺手过滤噪声"。"""
    lines = ["BEGIN", "SET"] + [row_line(*row) for row in rows] + ["ROLLBACK"]
    return "\n".join(lines) + "\n"


def full_preconditions() -> list:
    tables = {
        AUDIT.DEFAULT_VECTOR_TABLE: AUDIT.REQUIRED_COLUMNS["chunk_vectors"],
        AUDIT.DEFAULT_CHUNKS_TABLE: AUDIT.REQUIRED_COLUMNS["chunks"],
        "index_versions": AUDIT.REQUIRED_COLUMNS["index_versions"],
        "index_registry": AUDIT.REQUIRED_COLUMNS["index_registry"],
        AUDIT.DEFAULT_SCOPE_TABLE: AUDIT.OPTIONAL_COLUMNS["vector_scope"],
    }
    return [(table, column) for table, columns in tables.items() for column in columns]



# ================================================================== 只读闸本体
@pytest.mark.parametrize("statement", [
    "DELETE FROM chunk_vectors",
    "UPDATE chunk_vectors SET index_version_id = NULL",
    "INSERT INTO chunks (chunk_id) VALUES ('x')",
    "DROP TABLE chunk_vectors",
    "ALTER TABLE chunks ADD COLUMN embedding vector",
    "TRUNCATE chunk_vectors",
    "CREATE TABLE scratch (id int)",
    "GRANT ALL ON chunks TO PUBLIC",
    "VACUUM FULL",
    "COPY chunks TO PROGRAM 'sh -c id'",
    "CALL do_bad_stuff()",
    "REFRESH MATERIALIZED VIEW whatever",
    "SELECT 1; DELETE FROM chunks",
    "WITH x AS (SELECT 1) INSERT INTO chunks SELECT * FROM x",
    "SELECT pg_sleep(1); DROP SEQUENCE whatever",
])
def test_read_only_gate_refuses_every_write_shape_we_came_up_with(statement):
    with pytest.raises(AssertionError) as info:
        AUDIT._assert_read_only(statement)
    assert "R145" in str(info.value)


def test_read_only_gate_accepts_the_queries_the_script_actually_builds():
    for name, query in AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope").items():
        try:
            AUDIT._assert_read_only(query.sql)
        except AssertionError as exc:  # pragma: no cover - 失败时给出可定位信息
            pytest.fail("%s 没过只读闸：%s" % (name, exc))


def test_read_only_gate_is_comment_and_case_proof():
    AUDIT._assert_read_only("select 1 -- delete from chunks")
    AUDIT._assert_read_only("WITH t AS (SELECT 1)\nSELECT * FROM t")
    with pytest.raises(AssertionError):
        AUDIT._assert_read_only("WITH t AS (SELECT 1)\nDELETE FROM chunks")


@pytest.mark.parametrize("bad", [
    "chunks; DROP TABLE chunks", 'chunks"', "chunks --", "public.chunks", "CHUNK S", "", "  ",
])
def test_table_names_from_the_command_line_cannot_bring_a_second_statement(bad):
    with pytest.raises(ValueError):
        AUDIT.safe_table(bad)


def test_a_renamed_table_still_produces_read_only_sql():
    queries = AUDIT.build_queries("mirror_v2", "chunk_log", "scope_v2")
    assert "mirror_v2" in queries["q1_pg_vector_ids"].sql
    for query in queries.values():
        AUDIT._assert_read_only(query.sql)


# ================================================================== 工单指定的 docker 路线
class Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_the_docker_command_is_exactly_the_one_the_ticket_named():
    reader = AUDIT.DockerPsqlReader()
    assert reader.command == [
        "docker", "exec", "-i", "enterprise-brain-postgres-1", "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -q -v ON_ERROR_STOP=1 -f -',
    ]
    assert reader.command == AUDIT.DOCKER_PSQL
    assert "$POSTGRES_USER" in reader.command[-1] and "$POSTGRES_DB" in reader.command[-1]
    assert reader.command[-1].startswith("psql ")  # 库名/用户都留在容器环境里，不进命令行


def test_docker_psql_session_is_begin_read_only_select_rollback_only():
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")
    sent: list = []

    def runner(command, input=None, **kwargs):  # noqa: A002 - 语句本来就从 stdin 进去
        sent.append({"command": list(command), "script": input, "kwargs": kwargs})
        return Completed(stdout="")

    reader = AUDIT.DockerPsqlReader(runner=runner)
    for name in ("preconditions", "q1_pg_vector_ids", "q3_pg_generations"):
        assert reader.rows(queries[name]) == []
    assert len(sent) == 3
    for record in sent:
        script = record["script"]
        #: 会话第一行自己报家门：查询名写进标记，服务端日志与回执看的是同一位。
        head = script.split(chr(10))[0]
        assert head.startswith("-- r145:"), head
        assert head[8:] in queries
        assert record["command"] == reader.command
        assert record["kwargs"]["capture_output"] is True
        body = AUDIT._strip_sql_comments(script)
        statements = [item.strip() for item in body.split(";") if item.strip()]
        assert statements[:2] == ["BEGIN", "SET TRANSACTION READ ONLY"]
        assert statements[-1] == "ROLLBACK"
        middle = statements[2:-1]
        assert middle, "每个会话必须真的带一条查询"
        AUDIT._assert_read_only((chr(59) + chr(10)).join(middle))
        assert "commit" not in script.lower()
        assert script.count("SET TRANSACTION READ ONLY") == 1
    assert [entry["query"] for entry in reader.transcript] == [
        "preconditions", "q1_pg_vector_ids", "q3_pg_generations"]
    assert reader.malformed == []


def test_psql_stderr_comes_back_as_a_named_unavailability_not_an_empty_answer():
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")

    def runner(command, input=None, **kwargs):  # noqa: A002
        return Completed(stdout="", returncode=3,
                         stderr='psql:<stdin>:1: ERROR:  relation "chunk_vectors" does not exist')

    reader = AUDIT.DockerPsqlReader(runner=runner)
    with pytest.raises(AUDIT.MirrorUnavailable) as info:
        reader.rows(queries["q1_pg_vector_ids"])
    assert "does not exist" in str(info.value)
    answer = AUDIT.answer_q1(reader, queries, {"ids": [], "total": 0, "distinct": 0, "widths": {}},
                             AUDIT.parse_args([]))
    assert answer["status"] == AUDIT.CANNOT_ASK
    assert "does not exist" in answer["blocked_reason"]


# ================================================================== psycopg 备用路线
class FakeConnection:
    def __init__(self):
        self.statements: list = []
        self.rolled_back = 0
        self.closed = 0

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        return self

    def fetchall(self):
        return []

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1

    def commit(self):
        raise AssertionError("R145 绝不 COMMIT —— 这一条被调用就是写了库")


def test_psycopg_reader_uses_one_read_only_transaction_and_only_rolls_back():
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")
    connection = FakeConnection()
    reader = AUDIT.PsycopgReader("postgresql://nobody/nowhere", connect=lambda dsn: connection)
    for name in ("preconditions", "q2_null_rows", "self_check_counts"):
        assert reader.rows(queries[name]) == []
    assert connection.statements[:2] == list(AUDIT.TX_BEGIN)
    assert connection.statements[2:] == [queries[n].sql for n in
                                         ("preconditions", "q2_null_rows", "self_check_counts")]
    reader.close()
    assert connection.rolled_back == 1 and connection.closed == 1
    assert reader.rows(queries["q1_pg_vector_ids"]) == []  # close 之后重开一个只读事务，仍然不 COMMIT
    assert connection.statements.count("COMMIT") == 0


class AbortingConnection(FakeConnection):
    """一有一条语句失败，服务端就把整个事务打成 aborted：后续查询只会拿到二级错。

    这正是实测里真发生过的事 —— 修之前 `self_check_counts` 第二次报的是「当前事务被终止」，
    把真因（表不存在）盖掉了。假件把同一件事演出来，好让那条修复有反证。
    """

    def __init__(self, fail_on: str):
        super().__init__()
        self.fail_on = fail_on
        self.aborted = False

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)  # 失败的那一条也要留在账上，反证才有位置可对
        control = sql.strip().upper().split(None, 1)[0] in {"BEGIN", "SET", "ROLLBACK"}
        if self.aborted and not control:
            raise RuntimeError("当前事务被终止, 事务块结束之前的查询被忽略")
        if sql == self.fail_on:
            self.aborted = True
            raise RuntimeError(chr(39) + "chunk_vectors" + chr(39) + " 不存在")
        return self

    def rollback(self):
        super().rollback()
        self.aborted = False


def test_every_question_keeps_its_own_reason_after_a_failed_one():
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")
    connection = AbortingConnection(queries["q1_pg_vector_ids"].sql)
    reader = AUDIT.PsycopgReader("postgresql://nobody/nowhere", connect=lambda dsn: connection)
    with pytest.raises(RuntimeError) as info:
        reader.rows(queries["q1_pg_vector_ids"])
    assert "不存在" in str(info.value)
    #: 修之前：下一问只会拿到「当前事务被终止」，真因被二级错盖掉。修之后：它坐在重开的
    #: 只读事务里，拿到的是自己的答案。
    assert reader.rows(queries["q2_null_rows"]) == []
    position = connection.statements.index(queries["q1_pg_vector_ids"].sql)
    assert connection.statements[position + 1:position + 3] == list(AUDIT.TX_BEGIN)
    assert connection.statements[position + 3] == queries["q2_null_rows"].sql
    reopened = [entry for entry in reader.transcript
                if entry["script"].endswith("reopened after a failed statement")]
    assert len(reopened) == 1 and reopened[0]["query"] == "#transaction"
    assert connection.rolled_back == 1
    reader.close()  # ROLLBACK 走的是连接方法，不是再 execute 一条语句
    assert connection.rolled_back == 2 and connection.closed == 1
    assert reader.transcript[-1] == {"query": "#transaction", "script": AUDIT.TX_END[0]}
    assert connection.rolled_back == 2


def test_psycopg_default_connect_pins_autocommit_off_and_an_application_name(monkeypatch):
    """这三枚 kwarg 就是"没写库"的服务端闩：autocommit 关着 + 只读事务 + 可被 DBA 认出来源。"""
    import psycopg

    captured: dict = {}
    connection = FakeConnection()

    def fake_connect(dsn, **kwargs):
        captured["dsn"] = dsn
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    reader = AUDIT.PsycopgReader("postgresql://someone/somewhere")
    reader.rows(AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")["q1_pg_vector_ids"])
    reader.close()
    assert captured["dsn"] == "postgresql://someone/somewhere"
    assert captured["autocommit"] is False
    assert captured["connect_timeout"] == 5
    assert captured["application_name"] == "r145-audit"
    assert connection.rolled_back == 1


# ================================================================== 文本协议边界
def test_parse_rows_keeps_only_prefixed_lines_and_flags_wrong_arity():
    query = AUDIT.Query("probe", ("a", "b"), "SELECT 1")
    stdout = "\n".join([
        "BEGIN", "SET", "ROLLBACK",
        row_line("x", "y"),
        row_line("only-one-field"),
        "Timing is on.",
        row_line("p", "q"),
    ])
    rows, malformed = AUDIT.parse_rows(query, stdout)
    assert rows == [("x", "y"), ("p", "q")]
    assert malformed == [row_line("only-one-field")]


def test_parse_rows_turns_the_null_sentinel_back_into_none_but_keeps_empty_strings():
    query = AUDIT.Query("probe", ("a", "b", "c"), "SELECT 1")
    rows, malformed = AUDIT.parse_rows(
        query, row_line(AUDIT.NULL_SENTINEL, "", "v"))
    assert rows == [(None, "", "v")] and malformed == []


def test_a_filename_carrying_the_field_separator_is_flagged_not_misread():
    """0x1f 是合法文件名里的字符。这里不猜，直接退回 malformed 让报告点名。"""
    query = AUDIT.Query("probe", ("a", "b"), "SELECT 1")
    rows, malformed = AUDIT.parse_rows(query, row_line("we" + AUDIT.FIELD_SEP + "ird", "x", "y"))
    assert rows == [] and len(malformed) == 1

# ================================================================== 整场 transcript 自证
def test_the_full_session_transcript_has_no_fourth_kind_of_statement():
    """跑一整场（工单指定的 docker 路线 + 空库），再把每句话拆出来数一遍。

    这是对"未写 PG"最直接的一次可复核：报告里带的 transcript 就是实际发出去的字节，
    而这里的断言保证里面除了 BEGIN / SET TRANSACTION READ ONLY / ROLLBACK 之外只有 SELECT。
    """
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")
    pre = full_preconditions()
    payloads = {
        "preconditions": pre,
        "q1_pg_vector_ids": [("a.pdf_0",)],
        "q2_null_rows": [],
        "q2_mirror_totals": [(1, 1)],
        "q2_dangling_bindings": [],
        "q3_pg_generations": [("nomic-embed-text", "768", 1, "2026-09-20 01:00:00+00",
                               "2026-09-20 01:00:00+00")],
        "q3_declared_scope": [("1", "nomic-embed-text", "768", "cosine")],
        "q3_shape_lies": [],
        "q4_vectors_without_chunks": [],
        "q4_chunks_without_vectors": [],
        "q4_chunk_id_shapes": [],
        "q4_vector_id_shapes": [],
        "self_check_counts": [("chunk_vectors", 1), ("chunks", 1)],
    }
    sent: list = []

    def run(command, input=None, **kwargs):  # noqa: A002 - psql 的语句就是从 stdin 进去的
        sent.append(input)
        for name, rows in payloads.items():
            if ("-- r145:" + name + chr(10)) in (input or ""):
                return Completed(
                    stdout=chr(10).join(row_line(*row) for row in rows) + chr(10))
        return Completed(stdout="")

    reader = AUDIT.DockerPsqlReader(runner=run)
    chroma_view = {"ids": ["a.pdf_0"], "total": 1, "distinct": 1, "widths": {"768": 1},
                   "ok": True, "get_calls": 1}
    report = AUDIT.audit(reader, queries, chroma_view, AUDIT.parse_args([]))
    assert report["verdict"] == {key: AUDIT.CLEAN for key in ("q1", "q2", "q3", "q4")}
    transcript = report["self_check"]["statement_transcript"]
    names = [entry["query"] for entry in transcript]
    #: 13 条查询各有名字，self_check_counts 审计前后各数一次 ⇒ 14 个会话，一个不多一个不少。
    assert len(names) == len(sent) == 14
    assert set(names) == set(queries)
    assert names.count("self_check_counts") == 2
    allowed_control = {"BEGIN", "SET TRANSACTION READ ONLY", "ROLLBACK"}
    for entry in transcript:
        #: 每个会话自己报家门：标记里的查询名必须与 transcript 记的那一条一致。
        assert entry["script"].startswith("-- r145:" + entry["query"] + chr(10))
        body = AUDIT._strip_sql_comments(entry["script"])
        statements = [item.strip() for item in body.split(";") if item.strip()]
        assert statements[:2] == ["BEGIN", "SET TRANSACTION READ ONLY"]
        assert statements[-1] == "ROLLBACK"
        assert statements[2:-1], "会话里必须真的带一条查询"
        AUDIT._assert_read_only(";\n".join(statements[2:-1]))
        assert "commit" not in entry["script"].lower()
    assert report["self_check"]["row_counts_stable"] is True
    assert AUDIT.exit_code_for(report) == 0


# ================================================================== 零模型 / 零写真库
def test_script_never_imports_the_application_or_a_model_client():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n"))

    def module_names(nodes):
        found: list = []
        for node in nodes:
            if isinstance(node, ast.Import):
                found.extend(str(alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.append(str(node.module or ""))
        return found

    imported = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert any(node.col_offset for node in imported), "模型库那条腿得是真·惰性 import"
    top = module_names([node for node in tree.body
                        if isinstance(node, (ast.Import, ast.ImportFrom))])
    nested = []
    for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
        nested.extend(module_names([node for node in ast.walk(function)
                                    if isinstance(node, (ast.Import, ast.ImportFrom))]))
    roots = [name.split(".")[0] for name in top + nested]
    assert not [name for name in top + nested if name.startswith("app")], "不许 import 应用层"
    banned = {"ollama", "openai", "requests", "httpx", "langchain", "langchain_ollama"}
    assert not (banned & set(roots)), sorted(banned & set(roots))
    assert {name.split(".")[0] for name in nested} == {"psycopg", "chromadb"}
    assert {name.split(".")[0] for name in top} <= {
        "__future__", "argparse", "datetime", "dataclasses", "hashlib", "json", "os",
        "pathlib", "re", "shutil", "subprocess", "sys", "tempfile"}

def test_a_full_audit_makes_no_host_model_port_attempt(model_endpoint_guard):
    """R56 那道闸的运行时证据：整场审计 + 打开一次假 collection，闸门计数不许动。"""
    start = model_endpoint_guard.blocked_count()
    assert start == 0, "闸门上不该有别的用例留下的记录"
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")

    class Collection:
        def __init__(self):
            self.calls = 0

        def get(self, include=None, limit=None, offset=0):
            self.calls += 1
            return {"ids": ["a.pdf_0"], "embeddings": [[0.1] * 768]}

    collection = Collection()
    client_class = type("C", (), {
        "get_collection": lambda self, name=None: collection})
    client = AUDIT.open_chroma(
        "enterprise_docs", Path("/tmp/does-not-matter"),
        client_factory=lambda path: client_class())
    view = AUDIT.read_chroma(collection)
    def quiet(command, input=None, **kwargs):  # noqa: A002 - 空库：一条也回不来
        return Completed(stdout="")

    reader = AUDIT.DockerPsqlReader(runner=quiet)
    report = AUDIT.audit(reader, queries, dict(view, ok=True), AUDIT.parse_args([]))
    assert collection.calls >= 1
    assert report["self_check"]["model_calls"] == 0
    assert model_endpoint_guard.blocked_count() == start
    assert view["total"] == 1 and report["verdict"]["q1"] == AUDIT.CANNOT_ASK


# ================================================================== 仓库 chroma_db 不被打开
def test_copy_chroma_source_never_opens_or_creates_anything_in_the_source(tmp_path):
    source = tmp_path / "chroma_db"
    (source / "sub").mkdir(parents=True)
    (source / "chroma.sqlite3").write_bytes(b"header")
    (source / "sub" / "data_level0.bin").write_bytes(b"payload")
    before = AUDIT.file_manifest(source)
    destination, back = AUDIT.copy_chroma_source(source, str(tmp_path / "work"))
    try:
        assert back == source
        assert destination.exists() and destination != source
        assert AUDIT.file_manifest(destination) == before
        assert AUDIT.file_manifest(source) == before  # 拷贝这一步没在源目录留任何文件
        assert str(tmp_path / "work") in str(destination)
    finally:
        import shutil

        shutil.rmtree(destination.parent, ignore_errors=True)


def test_a_missing_chroma_directory_is_refused_instead_of_created(tmp_path):
    missing = tmp_path / "nope" / "chroma_db"
    with pytest.raises(AUDIT.MirrorUnavailable) as info:
        AUDIT.copy_chroma_source(missing, None)
    assert "不新建目录" in str(info.value)
    assert not missing.exists()


def test_read_chroma_pages_with_get_only_and_records_what_it_asked_for():
    seen: list = []

    class Collection:
        ids = ["id%d" % index for index in range(5)]

        def get(self, include=None, limit=None, offset=0):
            seen.append((tuple(include or ()), limit, offset))
            window = self.ids[offset:offset + (limit or len(self.ids))]
            payload = {"ids": list(window)}
            if "embeddings" in (include or ()):
                payload["embeddings"] = [[0.0] * 768 for _ in window]
            return payload

        def __getattr__(self, name):
            raise AssertionError("R145 不许调用 collection.%s" % name)

    view = AUDIT.read_chroma(Collection(), page=2)
    assert (view["total"], view["distinct"]) == (5, 5)
    assert view["widths"] == {"768": 5}
    assert view["get_calls"] == 3
    assert all(include == ("metadatas", "embeddings") for include, _l, _o in seen)
    narrow = AUDIT.read_chroma(Collection(), page=2, with_shapes=False)
    assert narrow["widths"] == {} and narrow["ids"] == view["ids"]
    assert all(include == ("metadatas",) for include, _l, _o in seen[-3:])
    # 没有 metadatas 的假句柄退回按最后一个下划线反切，只当标签用，不参与判定
    assert view["documents"] == {item: 1 for item in Collection.ids}


def test_open_chroma_refuses_a_missing_collection_by_name(tmp_path):
    class Client:
        def get_collection(self, name=None):
            raise Exception("Collection %s does not exist." % name)

    with pytest.raises(AUDIT.MirrorUnavailable) as info:
        AUDIT.open_chroma("enterprise_docs", tmp_path, client_factory=lambda path: Client())
    assert "enterprise_docs" in str(info.value)


# ================================================================== 字面量钉回唯一真源
def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _chroma_collection_literals() -> set:
    names: set = set()
    for node in ast.walk(ast.parse(_source(RETRIEVER_PATH))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in ("get_or_create_collection", "get_collection"):
            for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    names.add(argument.value)
    return names


def test_collection_default_is_the_name_the_writer_uses():
    names = _chroma_collection_literals()
    assert AUDIT.DEFAULT_COLLECTION in names, names
    assert AUDIT.parse_args([]).collection == AUDIT.DEFAULT_COLLECTION


def test_index_id_prefix_is_the_resource_type_the_writer_uses():
    tree = ast.parse(_source(INDEXING_PATH))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "RESOURCE_TYPE_DOCUMENT":
                    values[node.lineno] = node.value
    assert values, "indexing.py 里的 RESOURCE_TYPE_DOCUMENT 找不到了"
    literal = next(iter(values.values()))
    assert isinstance(literal, ast.Constant)
    assert AUDIT.INDEX_ID_PREFIX == literal.value + ":"


def test_mirror_table_names_match_the_writer():
    tree = ast.parse(_source(PG_STORE_PATH))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                        "DEFAULT_VECTOR_TABLE", "DEFAULT_CHUNKS_TABLE"}:
                    if isinstance(node.value, ast.Constant):
                        found[target.id] = node.value.value
    assert found["DEFAULT_VECTOR_TABLE"] == AUDIT.DEFAULT_VECTOR_TABLE
    assert AUDIT.DEFAULT_CHUNKS_TABLE == "chunks"
    assert AUDIT.DEFAULT_SCOPE_TABLE == "vector_scope"


def _normalise(expression: str) -> str:
    return re.sub(r"\s+", "", expression.replace("NEW.", ""))


def test_the_derivation_scale_is_the_trigger_scale_verbatim():
    """Q4 那两条孤儿判定用的键，必须与 0010 的 sync_chunk_embedding() 一字不差（去掉 NEW. 前缀）。

    两把尺对不上的话，孤儿数就是编出来的 —— 而这正是本单最容易在绿灯里混过去的一格。"""
    sql = _source(MIGRATION_0010)
    trigger_line = next(line for line in sql.split("\n")
                        if "split_part(NEW.chunk_id" in line)
    queries = AUDIT.build_queries("chunk_vectors", "chunks", "vector_scope")
    q4_sql = queries["q4_vectors_without_chunks"].sql
    assert _normalise("split_part(NEW.chunk_id, '|v', 1) || '_' || "
                      "NULLIF(split_part(NEW.chunk_id, '#', 2), '')") in _normalise(q4_sql)
    assert trigger_line.count("NULLIF") == 1
    # 触发器的第二条规则：metadata 里有显式 vector_id 时它以显式键为准，Q4 也照这个优先级取键
    assert "jsonb_typeof(metadata -> 'vector_id') = 'string'" in q4_sql
    assert "metadata ->> 'vector_id'" in q4_sql
    assert "NEW.metadata ? 'vector_id'" in sql  # 现读一遍触发器原文，确认这两句讲的是同一件事


def test_projection_protocol_is_what_the_parser_expects():
    projection = AUDIT.P("a", "b")
    assert "chr(31)" in projection and "'R' ||" in projection
    assert AUDIT.FIELD_SEP == chr(31) and AUDIT.ROW_PREFIX == "R" + chr(31)
    assert projection.count(AUDIT.NULL_SENTINEL) == 2