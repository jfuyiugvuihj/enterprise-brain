"""R90a 判据 ①②③④：应用 0010 之前下发 embedding profile，全部离线可证。

本文件一条真库都不连，也不需要：宿主 5432 已被 tests/conftest.py:41 那颗钉子钉死（测试期
DATABASE_URL 指向 127.0.0.1:1 这个保留端口），所以"自建一次性库"在这里根本连不上，判据 ⑤
走的是它给的另一条路 —— 全部 FakeSession。FakeSession 是按 PostgreSQL 语义写的小假连接：

* 库级设置与会话值分开存：``current_setting()`` 按"本事务 SET LOCAL 的值优先，否则本会话启动
  时读到的库级默认，否则空"回答 —— 这是 PostgreSQL 的真语义，也正是"光发 ALTER DATABASE 不够、
  光发 set_config 也不够"的原因，两条用例分别钉住一边；
* ``format(text, current_database(), value)`` 按 %I / %L 的真规则转义，所以"库名不许在 Python
  里拼字符串"是可证的：实现只能拿到假连接吐回来的整句话并原样执行；
* 同一句 ``format()`` 在拼之前还要过一遍 PostgreSQL 的 Parse 规则：psycopg 默认游标是服务端
  绑定，``%s`` 到了服务端就是没声明类型的 ``$n``，而 ``format(text, "any")`` 只把第一个参数
  强制成 text，其余参数推不出类型 ⇒ 整条语句当场被拒（``IndeterminateDatatype``）。上一棒
  29 条全绿、真机一跑就死，缺的就是这一层：假连接自己把 format() 拼好了，抹掉了服务端唯一
  的拒绝理由。现在摘掉 ::text 必红；
* 0010 的 SQL 可按令牌注入失败，用来模拟它自己那道 RAISE。

契约出自 docs/handoff/2026-09-15-backend-followup-requests.md §34.2；用例名里的 criterion_N 对应
判据编号。R90b（0010 提示串里的 ``%I``）不在本文件范围内，那是 ``migrations/**`` 的业主写域。
"""
from __future__ import annotations

from contextlib import nullcontext
import logging
from pathlib import Path
import re

import pytest
import yaml
from psycopg.errors import IndeterminateDatatype

from app.db import migrations as mig
from app.rag import indexing


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_SERVICES = ("migrate", "backend", "worker", "scheduler")

DIM = 640
MODEL = "bge-m3-r90a"
DATABASE = "brain_r90a"

MIGRATION_0010 = next(migration for migration in mig.MIGRATIONS if migration.version == "0010")
OTHER_MIGRATIONS = tuple(
    migration for migration in mig.MIGRATIONS if migration.version != "0010"
)


class MigrationRanIntoItsOwnRefusal(RuntimeError):
    """替 PostgreSQL 说话：0010 自己那道 RAISE EXCEPTION 的形状。"""


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _pg_format(template: str, *arguments: str) -> str:
    """The slice of PostgreSQL's format() this ticket uses: %I quotes, %L is a literal."""
    result = template
    for argument in arguments:
        if "%I" in result:
            result = result.replace("%I", _quote_identifier(argument), 1)
        elif "%L" in result:
            result = result.replace("%L", _quote_literal(argument), 1)
        else:
            raise AssertionError(f"no %-placeholder left for argument {argument!r}")
    return result


#: 真机那次 rc=1 的原文形状。psycopg 默认游标把 ``%s`` 改写成 ``$1``、``$2`` 交给服务端绑定，
#: 且不声明参数类型；PostgreSQL 只有在函数签名里读得到类型时才会替 ``$n`` 定类型。本单两条
#: 语句正好一正一反：``set_config(text, text, boolean)`` 推得出，``format(text, "any")`` 除了
#: 第一个参数之外推不出 —— 所以 ``_FORMAT_ALTER_DATABASE_SQL`` 的两个占位符必须自带 ::text。
UNTYPED_FORMAT_SQL = "SELECT format(%s, current_database(), %s) AS statement"

_PLACEHOLDER_RE = re.compile(r"%s")
_FORMAT_CALL_RE = re.compile(r"(?<![A-Za-z_0-9])format\s*\(", re.IGNORECASE)
_CAST_RE = re.compile(r"\A\s*::")


def _format_argument_spans(sql: str) -> list[list[tuple[int, int]]]:
    """每个 ``format(...)`` 调用的顶层参数区间。

    只认本文件用到的形状：字面量全在绑定参数里，语句内没有带逗号的字符串常量，format() 也不
    自我嵌套。括号不配对就红，宁可炸在脚手架里，也不放一条读不懂的语句过去。
    """
    calls: list[list[tuple[int, int]]] = []
    for call in _FORMAT_CALL_RE.finditer(sql):
        arguments: list[tuple[int, int]] = []
        depth = 1
        start = call.end()
        position = start
        while position < len(sql):
            char = sql[position]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            elif char == "," and depth == 1:
                arguments.append((start, position))
                start = position + 1
            position += 1
        if depth != 0:
            raise AssertionError(f"unbalanced parentheses in: {sql!r}")
        arguments.append((start, position))
        calls.append(arguments)
    return calls


def _assert_server_can_type_parameters(sql: str) -> None:
    """服务端 Parse 阶段的那道关：定不出类型的绑定参数，整条语句当场被拒。

    参数编号按占位符在语句里出现的次序排（psycopg 就是这么改写成 ``$n`` 的），所以报出来的
    ``$n`` 与真机一字不差。缺类型的是第二个参数：第一个由 ``format()`` 的签名特例强制成 text。
    这条不算"第一个可以少写"的许可证 —— 本单判据 ① 要求两处都带 ::text，另有形状用例钉着。
    """
    placeholders = [match.start() for match in _PLACEHOLDER_RE.finditer(sql)]
    for arguments in _format_argument_spans(sql):
        for slot in arguments[1:]:
            for number, start in enumerate(placeholders, start=1):
                if slot[0] <= start < slot[1] and not _CAST_RE.match(sql[start + len("%s"):]):
                    raise IndeterminateDatatype(
                        f"could not determine data type of parameter ${number}"
                    )


_ALTER_RE = re.compile(
    r"^ALTER DATABASE (?P<database>\"(?:[^\"]|\"\")*\"|[A-Za-z_][A-Za-z0-9_$]*) "
    r"SET (?P<setting>[a-z_][a-z0-9_.]*) = '(?P<value>.*)'\Z"
)


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)


class FakeSession:
    """假 psycopg 连接：按语义记两层设置与账本，能注入 0010 的拒绝。"""

    #: True 时探针返回 mapping 行，用来覆盖 _row_value 的另一条分支。
    mappings = False

    def __init__(
        self,
        *,
        database: str = DATABASE,
        database_settings: dict[str, str] | None = None,
        ledger: dict[str, str] | None = None,
        answers_probe: bool = True,
        fail_on: tuple[str, ...] = (),
        stale_read_back: bool = False,
    ) -> None:
        self.database = database
        self.database_settings = dict(database_settings or {})
        #: What *this* session reads when nothing is set locally: the database defaults as they
        #: stood when the session started. A later session picks up the durable declaration;
        #: the session that issued it does not -- that is PostgreSQL, not a convenience.
        self.session_baseline = dict(self.database_settings)
        self.transaction_settings: dict[str, str] = {}
        self.ledger = dict(ledger or {})
        self.answers_probe = answers_probe
        #: True 时第二句探针退回旧值：模拟"下发没真落到这个会话"。
        self.stale_read_back = stale_read_back
        self.probes = 0
        self.fail_on = set(fail_on)
        self.statements: list[tuple[str, object]] = []
        self.applied: list[str] = []
        self.inserted: list[tuple[str, str, str]] = []

    def current_setting(self, setting: str) -> str:
        """Transaction-local value first, else this session's startup default, else unset."""
        return (
            self.transaction_settings.get(setting)
            or self.session_baseline.get(setting)
            or ""
        )

    def reconnect(self) -> "FakeSession":
        """A new session on the same database: it reads the durable declaration only."""
        later = FakeSession(
            database=self.database,
            database_settings=self.database_settings,
            ledger=self.ledger,
            answers_probe=self.answers_probe,
            fail_on=tuple(self.fail_on),
        )
        later.statements = []
        return later

    def transaction(self):
        return nullcontext()

    def execute(self, sql: str, params=None) -> FakeResult:
        self.statements.append((sql, params))
        if params is not None:
            _assert_server_can_type_parameters(sql)

        if "AS database_name" in sql:
            if not self.answers_probe:
                return FakeResult([])
            self.probes += 1
            stale = self.stale_read_back and self.probes > 1
            row = (
                self.database,
                self.session_baseline.get(mig.EMBEDDING_DIMENSION_GUC, "")
                if stale
                else self.current_setting(mig.EMBEDDING_DIMENSION_GUC),
                self.session_baseline.get(mig.EMBEDDING_MODEL_GUC, "")
                if stale
                else self.current_setting(mig.EMBEDDING_MODEL_GUC),
            )
            if self.mappings:
                columns = ("database_name", "embedding_dimension", "embedding_model")
                return FakeResult([dict(zip(columns, row))])
            return FakeResult([row])

        if "AS statement" in sql:
            template, value = params
            return FakeResult([(_pg_format(template, self.database, value),)])

        if sql.startswith("ALTER DATABASE "):
            match = _ALTER_RE.match(sql)
            assert match, f"the server was asked to run a malformed statement: {sql!r}"
            assert match.group("database") == _quote_identifier(self.database), sql
            self.database_settings[match.group("setting")] = match.group("value")
            return FakeResult([])

        if "set_config" in sql:
            dimension_setting, dimension_value, model_setting, model_value = params
            self.transaction_settings[dimension_setting] = dimension_value
            self.transaction_settings[model_setting] = model_value
            return FakeResult([(dimension_value, model_value)])

        if "FROM schema_migrations" in sql:
            return FakeResult(sorted(self.ledger.items()))

        if "INSERT INTO schema_migrations" in sql:
            version, name, checksum = params
            self.inserted.append((version, name, checksum))
            self.ledger[version] = checksum
            return FakeResult([])

        migration = next(
            (item for item in mig.MIGRATIONS if sql == item.sql),
            None,
        )
        if migration is not None:
            if migration.version in self.fail_on:
                raise MigrationRanIntoItsOwnRefusal(
                    "0010 refuses to migrate: app.embedding_dimension = "
                    f"{self.current_setting(mig.EMBEDDING_DIMENSION_GUC)!r} but chunks.embedding "
                    "already holds 12 vectors of width 1024. R22 forbids two dimensions in one "
                    "database; this database is already claimed by width 1024."
                )
            self.applied.append(migration.version)
        return FakeResult([])


@pytest.fixture(autouse=True)
def _declared_profile(monkeypatch):
    """默认跑在"两个变量都声明了"的环境里，且故意不用出厂的 768，免得哪条用例靠猜过关。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, MODEL)


def _pending_0010(**kwargs) -> FakeSession:
    """一个"0001..0009 已记账、0010 待应用"的库：干净首装走到 pgvector 那一步的形状。"""
    return FakeSession(
        ledger={migration.version: migration.checksum for migration in OTHER_MIGRATIONS},
        **kwargs,
    )


def _alter_statements(connection: FakeSession) -> list[str]:
    return [sql for sql, _ in connection.statements if sql.startswith("ALTER DATABASE ")]


def _alter_pairs(connection: FakeSession) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for statement in _alter_statements(connection):
        match = _ALTER_RE.match(statement)
        assert match, f"not a well-formed ALTER DATABASE ... SET ... statement: {statement!r}"
        pairs[match.group("setting")] = match.group("value")
    return pairs


def _statements(connection: FakeSession) -> list[str]:
    return [sql for sql, _ in connection.statements]


def _position_of(sqls: list[str], needle: str) -> int:
    for position, sql in enumerate(sqls):
        if needle in sql:
            return position
    raise AssertionError(f"no statement containing {needle!r} was executed")


# ------------------------------------------------------------- 判据 ①：时机、成对、库名来源


def test_criterion_1_both_settings_are_declared_before_migration_0010():
    connection = _pending_0010()

    applied = mig.apply_migrations(connection, DATABASE)

    assert [migration.version for migration in applied] == ["0010"]
    sqls = _statements(connection)
    alters = [
        position for position, sql in enumerate(sqls) if sql.startswith("ALTER DATABASE ")
    ]
    assert alters, "nothing was declared at the database level"
    assert max(alters) < _position_of(sqls, MIGRATION_0010.sql[:60]), (
        "0010 reads these settings inside its own SQL, so declaring them afterwards is a no-op"
    )
    assert _alter_pairs(connection) == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }, "0010 reads a pair: declaring half of it is the drift R22 exists to stop"
    assert connection.database_settings == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }, "the durable declaration is the one every later session reads"
    assert connection.inserted == [
        (MIGRATION_0010.version, MIGRATION_0010.name, MIGRATION_0010.checksum)
    ]


def test_criterion_1_the_session_that_migrates_can_read_the_pair_it_declared():
    """PostgreSQL 只在会话启动时应用库级默认，所以正在跑 0010 的这一句还得看得见。

    ALTER DATABASE 页原文："Whenever a new session is subsequently started in that database,
    the specified value becomes the session default value." 只发库级那一笔，本会话读到的仍是空
    值，0010 照样 RAISE —— 这条用例钉住"下发完必须复读一次并核对"。
    """
    connection = _pending_0010()

    mig.apply_migrations(connection, DATABASE)

    assert connection.current_setting(mig.EMBEDDING_DIMENSION_GUC) == str(DIM)
    assert connection.current_setting(mig.EMBEDDING_MODEL_GUC) == MODEL
    sqls = _statements(connection)
    probes = [position for position, sql in enumerate(sqls) if "AS database_name" in sql]
    assert len(probes) == 2, "ask what is declared, then read it back: no blind writes"
    assert probes[1] < _position_of(sqls, MIGRATION_0010.sql[:60])


def test_criterion_1_the_durable_half_is_what_a_later_session_reads():
    """另一边的反证：只 SET LOCAL 不算下发 —— 下一个会话必须不靠我们也能读到那对值。

    ``reconnect()`` 开一个只带库级设置的新会话（真库里就是 migrate 跑完之后的 backend）。
    它对 0010 的两句 ``current_setting`` 都答得出来，才说明 ``ALTER DATABASE`` 真的落了地。
    """
    connection = _pending_0010()

    mig.apply_migrations(connection, DATABASE)

    later = connection.reconnect()
    assert later.transaction_settings == {}, "the next session inherits defaults, not our local set"
    assert later.current_setting(mig.EMBEDDING_DIMENSION_GUC) == str(DIM)
    assert later.current_setting(mig.EMBEDDING_MODEL_GUC) == MODEL


def test_criterion_1_a_declaration_the_session_cannot_read_back_stops_before_0010():
    """下发完读不回来就不许往下走：这条是"库级默认对本会话不生效"那枚暗礁的保险。

    假连接第二次答探针时退回旧值，等价于 ``set_config`` 那一笔被谁吞了。实现必须停下来报错，
    而不是把 0010 交出去、让它用一句运维抄不通的 RAISE 收尾。
    """
    connection = _pending_0010(stale_read_back=True)

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    assert "not visible to the session that migrates" in str(caught.value)
    assert connection.applied == [], "0010 must not have been attempted"
    assert connection.inserted == []


def test_criterion_1_the_database_name_is_the_servers_own_not_a_string_join():
    connection = _pending_0010(database=DATABASE)

    mig.apply_migrations(connection, "an_entirely_different_name")

    composed = [(sql, params) for sql, params in connection.statements if "AS statement" in sql]
    assert composed, "the runner must let the server compose ALTER DATABASE"
    for sql, params in composed:
        assert "current_database()" in sql
        assert "%I" in params[0], "the database name has to be quoted by format()'s %I"
        assert "an_entirely_different_name" not in sql
    assert _alter_statements(connection), "nothing was declared at all"
    for statement in _alter_statements(connection):
        assert _quote_identifier(DATABASE) in statement
        assert "an_entirely_different_name" not in statement


def test_criterion_1_a_database_name_that_needs_quoting_cannot_escape_its_own_slot():
    awkward = 'wei"rd db;drop'
    connection = _pending_0010(database=awkward)

    mig.apply_migrations(connection, awkward)

    for statement in _alter_statements(connection):
        match = _ALTER_RE.match(statement)
        assert match, f"quoting produced an unparsable statement: {statement!r}"
        assert match.group("database") == _quote_identifier(awkward)
        assert len(_ALTER_RE.findall(statement)) == 1, statement


# ---------------------- 真机退回：绑定参数的类型（本单判据 ①②，与上面那套 criterion_N 无关）


def test_the_format_statement_types_both_of_its_placeholders():
    """库名与值都由服务端引号化，但两个绑定参数的类型必须写在 SQL 文本里。

    方向没错、缺的是类型：真机 rc=1 就停在 ``could not determine data type of parameter $2``，
    一句 ALTER 都没发出去。所以这里两头都钉 —— 既钉"仍由服务端 format() 组装"，也钉"每个
    占位符都自带 ::text"。
    """
    sql = mig._FORMAT_ALTER_DATABASE_SQL

    assert "format(" in sql, "库名必须由服务端引号化，不许退回 Python 拼字符串"
    assert "current_database()" in sql, "库名是问服务端要的，不是拼给它看的"
    placeholders = list(re.finditer(r"%s", sql))
    assert len(placeholders) == 2, f"一个设置名加一个值，正好两个参数: {sql!r}"
    for match in placeholders:
        assert sql[match.end():].startswith("::text"), (
            f"第 {match.start()} 列的占位符不带类型，真库会在 Parse 阶段拒掉整条语句: {sql!r}"
        )


def test_the_fake_connection_refuses_an_untyped_format_call():
    """假连接自己就是那道 Parse 关 —— 这条钉子是防回归本体，比代码里那两处 ::text 更重要。

    上一棒 29 条全绿而真机一跑就死，差的就是这一步：只要假连接无条件替服务端把 format()
    拼好，摘掉类型也没人会红。现在摘掉必红，而且红的是真机那句原文。
    """
    with pytest.raises(IndeterminateDatatype) as caught:
        _assert_server_can_type_parameters(UNTYPED_FORMAT_SQL)

    assert str(caught.value) == "could not determine data type of parameter $2"
    _assert_server_can_type_parameters(mig._FORMAT_ALTER_DATABASE_SQL)


def test_a_statement_whose_signature_types_its_parameters_needs_no_cast():
    """``set_config(text, text, boolean)`` 那四个占位符照旧裸写：类型写在签名里，服务端推得出。

    钉住这处不对称的原因，免得下一个人把 ::text 当成对所有绑定参数的通用要求，或者怀疑假连接
    漏判了另一边 —— 它拒的只是 format() 那个 variadic "any" 的特例。
    """
    connection = _pending_0010()

    _assert_server_can_type_parameters(mig._DECLARE_PROFILE_FOR_TRANSACTION_SQL)
    connection.execute(
        mig._DECLARE_PROFILE_FOR_TRANSACTION_SQL,
        (mig.EMBEDDING_DIMENSION_GUC, str(DIM), mig.EMBEDDING_MODEL_GUC, MODEL),
    )

    assert connection.transaction_settings == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }


def test_the_untyped_format_statement_stops_the_run_before_0010(monkeypatch):
    """把 ::text 摘掉再走一遍整条路径：离线也要复现真机那次 rc=1 的死法，而不是绿给人看。

    三件事都得对上 —— 异常是 psycopg 自己的那个类（``scripts/migrate.py:39`` 打印的就是它的
    消息）、0010 根本没被交出去、库上一行设置都没落地。这正是"什么都没下发"的形状。
    """
    monkeypatch.setattr(mig, "_FORMAT_ALTER_DATABASE_SQL", UNTYPED_FORMAT_SQL)
    connection = _pending_0010()

    with pytest.raises(IndeterminateDatatype) as caught:
        mig.apply_migrations(connection, DATABASE)

    assert str(caught.value) == "could not determine data type of parameter $2"
    assert connection.applied == [], "0010 没跑到，真机当时就停在这个位置"
    assert connection.inserted == []
    assert connection.database_settings == {}, "什么都没下发"
    assert _alter_statements(connection) == []


# ------------------------------------------------------------------ 判据 ②：缺一即停并点名


def test_criterion_2_a_missing_dimension_stops_and_names_only_it(monkeypatch):
    monkeypatch.delenv(indexing.EMBEDDING_DIMENSION_ENV)
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_DIMENSION_ENV in message
    assert "is not declared" in message
    assert f"{indexing.EMBEDDING_MODEL_ENV} is not declared" not in message
    assert "Declared so far" in message and MODEL in message, "say what is already set"
    assert _alter_statements(connection) == [], "a refusal may not touch the database first"
    assert connection.applied == [], "0010 must not have been attempted"


def test_criterion_2_a_missing_model_stops_and_names_only_it(monkeypatch):
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV)
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_MODEL_ENV in message
    assert f"{indexing.EMBEDDING_DIMENSION_ENV} is not declared" not in message
    assert _alter_statements(connection) == []
    assert connection.applied == []


def test_criterion_2_an_empty_value_counts_as_undeclared(monkeypatch):
    """``EMBEDDING_DIMENSION=`` 这种"占了一行但没值"的写法，正是 compose 空插值会造出来的。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, "   ")
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    assert indexing.EMBEDDING_DIMENSION_ENV in str(caught.value)
    assert _alter_statements(connection) == []


def test_criterion_2_both_undeclared_names_both(monkeypatch):
    monkeypatch.delenv(indexing.EMBEDDING_DIMENSION_ENV)
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV)
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_DIMENSION_ENV in message
    assert indexing.EMBEDDING_MODEL_ENV in message
    assert "are not declared" in message
    assert _alter_statements(connection) == []


def test_criterion_2_an_unusable_width_is_not_quietly_replaced_by_the_shipped_default(monkeypatch):
    """R22 承重：``EMBEDDING_DIMENSION=wide`` 不许退成 768 继续往下走。"""
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, "wide")
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_DIMENSION_ENV in message
    assert "not a positive integer" in message
    assert _alter_statements(connection) == []
    assert connection.applied == []
    assert not any("768" in sql for sql in _statements(connection)), message


def test_criterion_2_zero_is_refused_like_any_other_unusable_width(monkeypatch):
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, "0")
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    assert indexing.EMBEDDING_DIMENSION_ENV in str(caught.value)
    assert _alter_statements(connection) == []


def test_criterion_2_the_values_come_from_configured_embedding_scope(monkeypatch):
    """①② 的交接处：值只能经 ``configured_embedding_scope()`` 这道门出来。"""
    calls: list[int] = []
    real = indexing.configured_embedding_scope

    def spy():
        calls.append(1)
        return real()

    monkeypatch.setattr(indexing, "configured_embedding_scope", spy)
    connection = _pending_0010()

    mig.apply_migrations(connection, DATABASE)

    assert calls, "the profile has to be read through app.rag.indexing"
    assert _alter_pairs(connection) == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }


def test_criterion_2_a_width_that_disagrees_with_the_profile_stops(monkeypatch):
    """声明与 profile 不一致时宁可停，也不许挑一个值下发 —— 反证"另起一套读法"。"""
    monkeypatch.setattr(
        indexing,
        "configured_embedding_scope",
        lambda: indexing.EmbeddingScope(MODEL, 1024),
    )
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_DIMENSION_ENV in message
    assert str(DIM) in message and "1024" in message
    assert _alter_statements(connection) == []
    assert connection.applied == []


def test_criterion_2_a_model_that_disagrees_with_the_profile_stops(monkeypatch):
    monkeypatch.setattr(
        indexing,
        "configured_embedding_scope",
        lambda: indexing.EmbeddingScope("some-other-model", DIM),
    )
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError) as caught:
        mig.apply_migrations(connection, DATABASE)

    message = str(caught.value)
    assert indexing.EMBEDDING_MODEL_ENV in message
    assert "some-other-model" in message
    assert _alter_statements(connection) == []


# --------------------------------------------------------------------- 判据 ③：幂等与不绕过


def test_criterion_3_a_second_run_applies_nothing_and_declares_nothing():
    """连跑第二次：0010 已记账，于是探针、库级 SET、事务级 SET 一句话都不该再发。"""
    declared = {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }
    connection = FakeSession(
        ledger={migration.version: migration.checksum for migration in mig.MIGRATIONS},
        database_settings=declared,
    )

    applied = mig.apply_migrations(connection, DATABASE)

    assert applied == []
    assert _alter_statements(connection) == []
    assert not any("set_config" in sql for sql in _statements(connection))
    assert not any("AS database_name" in sql for sql in _statements(connection))
    assert connection.database_settings == declared, "the values on the database came back changed"


def test_criterion_3_declaring_the_same_profile_again_writes_the_same_values():
    declared = {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }
    connection = _pending_0010(database_settings=declared)

    mig.apply_migrations(connection, DATABASE)

    assert connection.database_settings == declared
    assert len(_alter_statements(connection)) == 2, "the pair, once, with nothing extra"


def test_criterion_3_a_database_claimed_by_another_width_is_left_to_migrations_own_refusal():
    """③ 后半：宽度已被别的 profile 占了，说话的是 0010 那道 RAISE，不是我们的补救。"""
    connection = _pending_0010(fail_on=("0010",))

    with pytest.raises(MigrationRanIntoItsOwnRefusal) as caught:
        mig.apply_migrations(connection, DATABASE)

    assert "already claimed by width 1024" in str(caught.value)
    assert connection.applied == [] and connection.inserted == []
    assert len(_alter_statements(connection)) == 2, "declare the pair, then get out of the way"
    assert not any("RESET" in sql.upper() for sql in _statements(connection)), _statements(
        connection
    )


def test_criterion_3_the_success_path_never_resets_a_database_declaration():
    connection = _pending_0010()

    mig.apply_migrations(connection, DATABASE)

    assert not any("RESET" in sql.upper() for sql in _statements(connection))
    assert connection.transaction_settings == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }


def test_criterion_3_replacing_a_stale_declaration_says_so_instead_of_going_quiet(caplog):
    """库上挂着别的宽度而运行时声明了新值：改声明 + 留话，已有的向量由 0010 去守。"""
    connection = _pending_0010(database_settings={mig.EMBEDDING_DIMENSION_GUC: "1024"})

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        mig.apply_migrations(connection, DATABASE)

    assert connection.database_settings[mig.EMBEDDING_DIMENSION_GUC] == str(DIM)
    assert any("was '1024'" in message for message in caplog.messages), caplog.messages
    assert any("not relabelled" in message for message in caplog.messages)


def test_criterion_3_a_refusal_from_configured_embedding_scope_is_not_visible_as_a_success(
    monkeypatch,
):
    """探针答得出、profile 却缺声明：这一条走的是真库路径，必须停。"""
    monkeypatch.delenv(indexing.EMBEDDING_MODEL_ENV)
    connection = _pending_0010()

    with pytest.raises(mig.EmbeddingProfileError):
        mig.provision_embedding_scope(connection)

    assert connection.database_settings == {}


# --------------------------------------------------------- 离线假连接的边界形状（判据 ⑤ 的另一半）


def test_a_connection_that_cannot_answer_current_database_is_not_provisioned(caplog):
    """唯一的例外形状：答不出 current_database() 的不是 PostgreSQL 会话。

    tests/test_storage_contract.py:120 用的就是这种假连接（任何查询都只给 fetchall() -> []）。
    这里如实钉住两件事：一条 ALTER 都不发，并且留一条 warning。真库永远答得出这句查询，所以
    判据 ② 的"缺一即停"在部署路径上躲不掉 —— 这条用例就是那道口子的形状。
    """
    connection = _pending_0010(answers_probe=False)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        applied = mig.apply_migrations(connection, DATABASE)

    assert [migration.version for migration in applied] == ["0010"]
    assert _alter_statements(connection) == []
    assert not any("set_config" in sql for sql in _statements(connection))
    assert any("did not answer current_database" in message for message in caplog.messages)


def test_a_mapping_cursor_reads_the_same_probe_row():
    connection = _pending_0010()
    connection.mappings = True

    mig.apply_migrations(connection, DATABASE)

    assert _alter_pairs(connection) == {
        mig.EMBEDDING_DIMENSION_GUC: str(DIM),
        mig.EMBEDDING_MODEL_GUC: MODEL,
    }


# ---------------------------------------------------------------------- 判据 ④：交付面成对


def _compose() -> dict:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
    assert isinstance(document, dict), "docker-compose.yml must stay a mapping"
    return document


def test_criterion_4_compose_passes_the_pair_to_the_four_processes():
    services = _compose()["services"]

    for name in COMPOSE_SERVICES:
        environment = services[name]["environment"]
        assert indexing.EMBEDDING_DIMENSION_ENV in environment, name
        assert indexing.EMBEDDING_MODEL_ENV in environment, name


def test_criterion_4_compose_passes_operator_values_and_invents_none():
    """四处写法必须一模一样，而且都是透传：compose 不许自己写死宽度或模型名。"""
    services = _compose()["services"]
    expected = {
        indexing.EMBEDDING_DIMENSION_ENV: "${" + indexing.EMBEDDING_DIMENSION_ENV + "}",
        indexing.EMBEDDING_MODEL_ENV: "${" + indexing.EMBEDDING_MODEL_ENV + "}",
    }

    for name in COMPOSE_SERVICES:
        environment = services[name]["environment"]
        assert {key: environment[key] for key in expected} == expected, name


def _env_example() -> tuple[list[str], dict[str, str]]:
    lines = ENV_EXAMPLE.read_text(encoding="utf-8-sig").splitlines()
    declared = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in lines
        if "=" in line and not line.strip().startswith("#")
    }
    return lines, declared


def test_criterion_4_the_env_sample_declares_the_pair_at_the_numbers_the_code_ships():
    """R30 的口径：写在纸上的数必须等于代码里的数，否则又是一台机器一个行为。"""
    _, declared = _env_example()

    assert declared[indexing.EMBEDDING_DIMENSION_ENV] == str(indexing.DEFAULT_EMBEDDING_DIMENSION)
    assert declared[indexing.EMBEDDING_MODEL_ENV] == indexing.DEFAULT_EMBEDDING_MODEL


def test_criterion_4_the_env_sample_says_a_new_model_must_change_the_width_too():
    """判据 ④ 要的那句注明：换 embedding 模型必须同时改宽度。"""
    lines, _ = _env_example()
    section: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("# --- embedding profile"):
            inside = True
        elif inside and line.startswith("# --- "):
            break
        elif inside:
            section.append(line)

    assert inside, ".env.example needs an embedding profile section"
    assert any(line.startswith("EMBEDDING_") for line in lines)
    body = "\n".join(section).lower()
    assert "changing the embedding model" in body
    assert "width" in body and "same edit" in body
    assert "rebuild" in body, "a different width means a rebuilt index, not a relabel"


def test_criterion_4_the_pair_is_written_four_times_and_never_one_sided():
    text = COMPOSE.read_text(encoding="utf-8")

    dimension = text.count(f"{indexing.EMBEDDING_DIMENSION_ENV}: ${{")
    model = text.count(f"{indexing.EMBEDDING_MODEL_ENV}: ${{")
    assert dimension == 4, f"expected one pair per process, found {dimension}"
    assert model == 4, f"the pair must appear as often as its partner, found {model}"


def test_criterion_4_no_other_service_is_told_a_model_it_cannot_use():
    """成对只加在真正读 profile 的四个进程上：postgres/redis/ollama 不该被塞进应用变量。"""
    services = _compose()["services"]
    keys = {indexing.EMBEDDING_DIMENSION_ENV, indexing.EMBEDDING_MODEL_ENV}

    for name in ("postgres", "redis", "ollama", "frontend"):
        environment = services[name].get("environment") or {}
        assert not keys & set(environment), name
