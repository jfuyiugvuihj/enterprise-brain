"""R190 —— 挂起台账的 status 词表放开到六枚：DDL 与代码必须逐枚同音。

来历（总控已用线上库实取坐实，本件不重复主张线上读数）：R175 新了终态 ``failed``，本机文件账
闭合，PG 那一腿写不进去 —— ``migrations/0008_pending_approvals.sql`` 的
``pending_approvals_status_check`` 只认五枚，撞约束的那一轮由 ``_decide_pending_approval`` 记
exception，行永远停在 ``awaiting``：审批人面前一张消不掉的待办，同一会话的
``pending_approvals_open_session_idx`` 也被它占着，下一轮挂起跟着撞 unique。

``migrations/0013_pending_approvals_status_includes_failed.sql`` 是那半条腿的前滚补法。本件钉的是
"补齐之后不许再漂移"，逐枚：

* 判据 2 —— 词表在仓库里只有三处拼写：0013 落盘的 CHECK、``PG_STATUSES``、``ALL_STATUSES``。
  DDL 的 CHECK 是 PostgreSQL 唯一能持有封闭集的形状，所以它天然是第二份；三方取值集合必须逐枚
  相等，任一方多一枚少一枚当场红，而不是到生产环境的审批屏上才红。本件自己不抄词表，最后一条
  用例用 AST 自查这件事。
* 判据 1 —— 纯前滚：0013 只有两枚 ``alter table``，零 UPDATE/零回填/零 DROP TABLE，放开后的域
  必须是 0008 那一域的**真超集**（否则存量行可能被新约束判死），而且守卫齐到能让没建表的库跳过。
* 判据 1 的"可重跑"—— 凭据只有 PostgreSQL 文档原文（引文与 URL 写在 DOCUMENTED_NO_ERROR_FORMS
  上方）：``ALTER TABLE [ IF EXISTS ]`` 与 ``DROP CONSTRAINT [ IF EXISTS ]`` 两形文档明写
"不存在也不报错、改出 notice"，而 ``ADD table_constraint`` 那一形文档没给任何 no-error 写法，
  所以第二遍的安全只许来自"ADD 前面有一枚带 IF EXISTS 的同名 DROP"（``add_drop_pairing``）。
  摘掉 DROP、把 DROP 挪到 ADD 之后、去掉 DROP 的守卫、或拿不存在的 ADD CONSTRAINT IF NOT
  EXISTS 求幂等，本件一律当场红；重放器遇到同名 ADD 抛不抛错**不作凭据**，只钉它一次都不许被触发。
* 判据 4 —— 0008 那两枚 ``WHERE status = 'awaiting'`` 的 partial index 在放开域之后仍然成立，凭据
  是谓词点名的那一格语义没变：它不是终态、``mark_status`` 也拒把它当终态写，而新放开的那一枚是
  终态，所以它天然落在两枚 partial index 之外。

全程离线：输入只有 ``migrations/*.sql`` 的文本，且一律走 ``app.db.migrations`` 的 loader（不是手读
文件），不连库、不起容器、不跑 ``scripts/migrate.py``。重放器与
``tests/test_r183_184_migration_pair.py`` 的 ``schema_through`` 同一强度定位：它只给本单判据当凭据，
产品代码不读它，也不是第二份 schema 事实源。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest

from app.db.migrations import MIGRATIONS, Migration, discover_migrations
from app.storage import pending_approvals as store
from test_r183_184_migration_pair import (  # noqa: T401  共用同一份离线 DDL 模型
    executable_statements,
    statement_head,
    writes_rows,
)

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"
MANIFEST_PATH = MIGRATIONS_DIR / "manifest.json"

TABLE = "pending_approvals"
CONSTRAINT_NAME = "pending_approvals_status_check"

#: 0008：这枚 CHECK 的出生地，也是"存量行过去被什么关着"的基准。
BASE_VERSION = "0008"
#: 🔴 目录尾号引信（与 tests/test_document_catalog_sync.py、tests/test_r46_activity_signals.py、
#: tests/test_r120_clean_install_first_boot.py 同族）：谁排下一号，必须回到这里连名带断言一起改口。
#: 改口是收紧，不是放宽。
CATALOG_TAIL_VERSION = "0013"
NEW_VERSION = CATALOG_TAIL_VERSION
NEW_FILENAME = "0013_pending_approvals_status_includes_failed.sql"
NEW_NAME = "pending_approvals_status_includes_failed"
NEW_PATH = MIGRATIONS_DIR / NEW_FILENAME

_STATUS_IN = r"CHECK\s*\(\s*status\s+IN\s*\((?P<words>[^)]*)\)"
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?P<guarded>IF\s+NOT\s+EXISTS\s+)?(?P<table>\w+)\s*\((?P<body>.+)\)",
    re.IGNORECASE | re.DOTALL,
)
_INLINE_STATUS_CHECK = re.compile(
    r"CONSTRAINT\s+(?P<name>\w+)\s+" + _STATUS_IN, re.IGNORECASE | re.DOTALL
)
_BARE_STATUS_CHECK = re.compile(_STATUS_IN, re.IGNORECASE | re.DOTALL)
_DROP_CONSTRAINT = re.compile(
    r"ALTER\s+TABLE\s+(?P<table_guard>IF\s+EXISTS\s+)?(?P<table>\w+)\s+"
    r"DROP\s+CONSTRAINT\s+(?P<name_guard>IF\s+EXISTS\s+)?(?P<name>\w+)",
    re.IGNORECASE,
)
_ADD_CONSTRAINT = re.compile(
    r"ALTER\s+TABLE\s+(?P<table_guard>IF\s+EXISTS\s+)?(?P<table>\w+)\s+"
    r"ADD\s+CONSTRAINT\s+(?!IF\s+NOT\s+EXISTS\b)(?P<name>\w+)(?P<body>.*)",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_INDEX = re.compile(
    r"CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<guarded>IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>\w+)\s+ON\s+(?P<table>\w+)\s*\((?P<columns>[^)]*)\)"
    r"(?:\s+WHERE\s+(?P<predicate>.+))?",
    re.IGNORECASE | re.DOTALL,
)
_PREDICATE_WORD = re.compile(r"'(?P<word>[^']*)'")


class ReplayError(RuntimeError):
    """重放器自带的保守拒绝：表/约束不在而语句没带守卫，或同名 ADD 撞车。

    🔴 同名 ADD 那一格是**建模**而不是 PG 凭据：文档只写了 ``ADD table_constraint`` 没有
    no-error 形，没写它撞车时报什么。可重跑性一律由 ``add_drop_pairing`` 与文档引文作证，
    这枚拒绝只当防呆，并且由用例钉"真目录重放到任何一版都不许触发它"。
    """


@dataclass(frozen=True)
class IndexInfo:
    """一枚索引在模型里的形状：谓词为空串就是普通索引，非空即 partial。"""

    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool
    predicate: str


@dataclass
class SchemaState:
    """重放到某一版时 ``pending_approvals`` 的可见状态（外加两笔账：没覆盖的语句、撞过名的 ADD）。

    ``collisions`` 只记账重放器自己保守拒绝过哪几枚同名 ADD，它不是 PG 读数，也不给任何判据
    当凭据 —— 有用例钉它恒为空。
    """

    tables: set[str] = field(default_factory=set)
    status_checks: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)
    indexes: dict[str, dict[str, IndexInfo]] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    unmodeled: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)


def words_of(raw: str) -> frozenset[str]:
    return frozenset(
        item.strip().strip("'").strip() for item in raw.split(",") if item.strip()
    )


def inline_status_checks(body: str, table: str) -> list[tuple[str, frozenset[str]]]:
    """``CREATE TABLE`` 体内写死的 status 封闭集：具名的照名字记，没具名的按 PG 的默认名记。"""
    named = [
        (match.group("name").lower(), words_of(match.group("words")))
        for match in _INLINE_STATUS_CHECK.finditer(body)
    ]
    if named:
        return named
    return [
        (f"{table}_status_check", words_of(match.group("words")))
        for match in _BARE_STATUS_CHECK.finditer(body)
    ]


def status_enumerations(sql: str) -> list[tuple[str, str, frozenset[str]]]:
    """一枚迁移文件里所有"把 status 的取值抄成封闭集合"的地方：``(表, 约束名, 取值)``。"""
    found: list[tuple[str, str, frozenset[str]]] = []
    for statement in executable_statements(sql):
        head = statement_head(statement)
        if head == "create table":
            create = _CREATE_TABLE.search(statement)
            if create is None:
                continue
            table = create.group("table").lower()
            for name, words in inline_status_checks(create.group("body"), table):
                found.append((table, name, words))
            continue
        add = _ADD_CONSTRAINT.search(statement)
        if add is None:
            continue
        check = _BARE_STATUS_CHECK.search(add.group("body"))
        if check is not None:
            found.append((add.group("table").lower(), add.group("name").lower(), words_of(check.group("words"))))
    return found


def _skip_or_fail(state: SchemaState, guarded: bool, reason: str) -> None:
    if guarded:
        state.notices.append(reason + ", statement skipped")
        return
    raise ReplayError(f"{reason}, and the statement carries no guard: PostgreSQL aborts here")


def _apply_alter(state: SchemaState, statement: str) -> None:
    drop = _DROP_CONSTRAINT.search(statement)
    if drop is not None:
        table = drop.group("table").lower()
        if table != TABLE:
            state.unmodeled.append(statement)
            return
        if table not in state.tables:
            _skip_or_fail(state, bool(drop.group("table_guard")), f"relation {table} does not exist")
            return
        checks = state.status_checks.setdefault(table, {})
        name = drop.group("name").lower()
        if name not in checks:
            _skip_or_fail(state, bool(drop.group("name_guard")), f"constraint {name} does not exist")
            return
        del checks[name]
        return

    add = _ADD_CONSTRAINT.search(statement)
    if add is not None:
        table = add.group("table").lower()
        if table != TABLE:
            state.unmodeled.append(statement)
            return
        if table not in state.tables:
            _skip_or_fail(state, bool(add.group("table_guard")), f"relation {table} does not exist")
            return
        check = _BARE_STATUS_CHECK.search(add.group("body"))
        if check is None:
            state.unmodeled.append(statement)
            return
        checks = state.status_checks.setdefault(table, {})
        name = add.group("name").lower()
        if name in checks:
            state.collisions.append(f"{table}.{name}")
            raise ReplayError(
                f"constraint {name} already exists on {table}: this replay model refuses "
                "rather than assumes, because the documented grammar for ALTER TABLE gives "
                "ADD table_constraint no no-error form (see DOCUMENTED_NO_ERROR_FORMS)"
            )
        checks[name] = words_of(check.group("words"))
        return

    state.unmodeled.append(statement)


def _apply_index(state: SchemaState, statement: str) -> None:
    match = _CREATE_INDEX.search(statement)
    if match is None:
        state.unmodeled.append(statement)
        return
    table = match.group("table").lower()
    if table != TABLE:
        state.unmodeled.append(statement)
        return
    name = match.group("name").lower()
    state.indexes.setdefault(table, {})[name] = IndexInfo(
        name=name,
        table=table,
        columns=tuple(part.strip() for part in match.group("columns").split(",") if part.strip()),
        unique=bool(match.group("unique")),
        predicate=" ".join((match.group("predicate") or "").split()),
    )


def apply_statement(state: SchemaState, statement: str) -> None:
    """把一枚语句叠到模型上。本模型只覆盖 status 的封闭集与索引谓词两件事，其余记账不猜。"""
    head = statement_head(statement)
    if head == "create table":
        match = _CREATE_TABLE.search(statement)
        if match is None:
            state.unmodeled.append(statement)
            return
        table = match.group("table").lower()
        if table in state.tables:
            _skip_or_fail(state, bool(match.group("guarded")), f"relation {table} already exists")
            return
        state.tables.add(table)
        for name, words in inline_status_checks(match.group("body"), table):
            state.status_checks.setdefault(table, {})[name] = words
        return
    if head == "alter table":
        _apply_alter(state, statement)
        return
    if head in ("create index", "create unique"):
        _apply_index(state, statement)
        return
    state.unmodeled.append(statement)


def ordered(through: str) -> list[Migration]:
    return [item for item in MIGRATIONS if item.version <= through]


def statements_of(version: str) -> list[str]:
    item = next(item for item in MIGRATIONS if item.version == version)
    return executable_statements(item.sql)


def apply_version(state: SchemaState, version: str) -> SchemaState:
    for statement in statements_of(version):
        apply_statement(state, statement)
    return state


def replay_through(through: str) -> SchemaState:
    state = SchemaState()
    for item in ordered(through):
        apply_version(state, item.version)
    return state


def status_checks_through(through: str) -> dict[str, frozenset[str]]:
    return dict(replay_through(through).status_checks.get(TABLE, {}))


def status_domain_through(through: str) -> frozenset[str]:
    """重放 0001..``through`` 之后，``pending_approvals.status`` 被哪一枚 CHECK 关着。

    🔴 本件与 ``tests/test_r175_failed_turn.py`` 共用这一枚函数：取值一律从落盘 DDL 重放出来，
    中间没有任何一处手抄词表。``tests/test_r183_184_migration_pair.py`` 的 ``schema_through``
    数的是列，这一枚数的是取值域，两件事不重叠。
    """
    checks = status_checks_through(through)
    assert list(checks) == [CONSTRAINT_NAME], (
        f"{through} 之后 {TABLE}.status 的封闭集应当恰有一枚 {CONSTRAINT_NAME}，实取 {sorted(checks)}"
    )
    return next(iter(checks.values()))


def indexes_through(through: str) -> dict[str, IndexInfo]:
    return dict(replay_through(through).indexes.get(TABLE, {}))


def predicate_word(predicate: str) -> str:
    match = _PREDICATE_WORD.search(predicate)
    assert match, f"partial index 的谓词读不出被点名的那一格：{predicate!r}"
    return match.group("word")


# ------------------------------ 判据 1"可重跑"的凭据源：PostgreSQL 官方文档原文
#: 这一节是被总控打回之后重写的。上一版把"可重跑"证在重放器自己身上（同名 ADD 会抛
#: ``ReplayError``），那是建模而不是凭据。现在凭据只许来自文档：以下逐条摘自
#: ``https://www.postgresql.org/docs/current/sql-altertable.html`` 与
#: ``https://www.postgresql.org/docs/current/sql-createtable.html``（取回时为 PostgreSQL 18）。
#:
#: Synopsis（sql-altertable.html）::
#:
#:     ALTER TABLE [ IF EXISTS ] [ ONLY ] name [ * ]
#:         action [, ... ]
#:     where action is one of:
#:         ADD [ COLUMN ] [ IF NOT EXISTS ] column_name data_type ...
#:         ADD table_constraint [ NOT VALID ]
#:         DROP CONSTRAINT [ IF EXISTS ]  constraint_name [ RESTRICT | CASCADE ]
#:
#: Parameters（同页）::
#:
#:     IF EXISTS
#:         Do not throw an error if the table does not exist. A notice is issued in this case.
#:
#: Description（同页）::
#:
#:     DROP CONSTRAINT [ IF EXISTS ]
#:         This form drops the specified constraint on a table, along with any index
#:         underlying the constraint. If IF EXISTS is specified and the constraint does not
#:         exist, no error is thrown. In this case a notice is issued instead.
#:     ADD table_constraint [ NOT VALID ]
#:         This form adds a new constraint to a table using the same constraint syntax as
#:         CREATE TABLE, plus the option NOT VALID ... Normally, this form will cause a scan
#:         of the table to verify that all existing rows in the table satisfy the new
#:         constraint.
#:
#: Examples（同页）—— PG 自己"换掉一枚同名约束"的写法就是先 DROP 再 ADD 同名::
#:
#:     ALTER TABLE distributors DROP CONSTRAINT distributors_pkey,
#:     ADD CONSTRAINT distributors_pkey PRIMARY KEY USING INDEX dist_id_temp_idx;
#:
#: Parameters（sql-createtable.html）::
#:
#:     IF NOT EXISTS
#:         Do not throw an error if a relation with the same name already exists. A notice is
#:         issued in this case.
#:
#: 读法：文档为 ``ADD [ COLUMN ]``、``DROP [ COLUMN ]``、``DROP CONSTRAINT``、``CREATE TABLE``
#: 都明写了"不存在/已存在都不报错、改出 notice"的那一形，唯独 ``ADD table_constraint`` 后面只跟
#: ``[ NOT VALID ]``。⇒ 第二次执行的安全只许寄托在"ADD 前面有一枚带 IF EXISTS 的同名 DROP"，
#: 不许寄托在 ADD 宽容，也不许寄托在本件重放器遇到同名 ADD 时抛不抛错。
PG_DOC_ALTER_TABLE = "https://www.postgresql.org/docs/current/sql-altertable.html"
PG_DOC_CREATE_TABLE = "https://www.postgresql.org/docs/current/sql-createtable.html"

#: 文档明写了"不报错、改出 notice"的三形（``create table if not exists`` 本单没用到，写全
#: 是给下一单留路：幂等形只许从这三形里挑，不许自己发明）。
DOCUMENTED_NO_ERROR_FORMS = {
    "alter table if exists": r"alter\s+table\s+if\s+exists\b",
    "drop constraint if exists": r"drop\s+constraint\s+if\s+exists\b",
    "create table if not exists": r"create\s+table\s+if\s+not\s+exists\b",
}
#: 文档里**不存在**的形：谁靠它求幂等，就是拿不存在的语法赌生产环境的部署事务。
UNDOCUMENTED_FORMS = {
    "add constraint if not exists": r"add\s+constraint\s+if\s+not\s+exists\b",
    "add table constraint if not exists": r"add\s+table[_ ]constraint\s+if\s+not\s+exists\b",
}


def collapsed(text: str) -> str:
    return " ".join(text.split()).lower()


def no_error_forms_in(text: str) -> tuple[str, ...]:
    """这枚语句用到了文档明写的哪几形 no-error 守卫（按归一后的文本判，行尾与换行不参与）。"""
    body = collapsed(text)
    return tuple(
        name for name, pattern in DOCUMENTED_NO_ERROR_FORMS.items() if re.search(pattern, body)
    )


def undocumented_forms_in(text: str) -> tuple[str, ...]:
    body = collapsed(text)
    return tuple(name for name, pattern in UNDOCUMENTED_FORMS.items() if re.search(pattern, body))


def add_drop_pairing(statements: list[str]) -> tuple[list[tuple[int, int, str]], list[tuple[int, str]]]:
    """按文档凭据判：每条 ``ADD CONSTRAINT`` 之前有没有一枚**带 ``IF EXISTS``** 的同名 DROP。

    返回 ``(配对, 裸 ADD)``，配对是 ``(add 下标, drop 下标, 约束名)``，裸 ADD 是 ``(下标, 约束名)``。
    只看落盘文本的配对，不碰重放器 —— "第二遍跑不跑得动"这件事的凭据就此只剩文档里那两形。
    """
    paired: list[tuple[int, int, str]] = []
    bare: list[tuple[int, str]] = []
    for index, statement in enumerate(statements):
        add = _ADD_CONSTRAINT.search(statement)
        if add is None:
            continue
        table = add.group("table").lower()
        name = add.group("name").lower()
        dropper = None
        for earlier in range(index):
            drop = _DROP_CONSTRAINT.search(statements[earlier])
            if drop is None:
                continue
            if drop.group("table").lower() != table or drop.group("name").lower() != name:
                continue
            if not drop.group("name_guard"):
                continue
            dropper = earlier
            break
        if dropper is None:
            bare.append((index, name))
        else:
            paired.append((index, dropper, name))
    return paired, bare


def new_sql() -> str:
    return next(item for item in MIGRATIONS if item.version == NEW_VERSION).sql


_NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _record(status: str) -> store.PendingApprovalRecord:
    return store.PendingApprovalRecord(
        session_id="r190-domain",
        owner_user_id="u-r190",
        parked_steps=["chart"],
        status=status,
        expires_at=(_NOW + timedelta(hours=1)).isoformat(),
    )


# ---------------------------------------------------- 判据 1：目录只多一枚新号
def test_the_catalog_gains_exactly_one_version_and_the_loader_accepts_it():
    versions = [item.version for item in MIGRATIONS]
    on_disk = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))

    assert versions == [f"{number:04d}" for number in range(1, len(versions) + 1)], versions
    assert versions[-1] == CATALOG_TAIL_VERSION, (
        "本单只排一枚新号；下一版必须回到这里改口（收紧，不是放宽）：" + str(versions[-1])
    )
    assert NEW_FILENAME in on_disk
    assert next(item for item in MIGRATIONS if item.version == NEW_VERSION).name == NEW_NAME
    assert discover_migrations() == MIGRATIONS, "清单校验不过的目录不该被 loader 认下来"


# ------------------------------------------------- 判据 2：三方对判，词表只此一处
def test_the_landed_check_admits_every_status_the_code_can_write():
    """本单最要紧的一枚：DDL 落盘的取值集合 == ``PG_STATUSES`` == ``ALL_STATUSES``。

    三方任一处多一枚或少一枚都当场红 —— 包括"只改 DDL 不改代码"和"只改代码不改 DDL"两个方向，
    那正是 R175 留欠账的形状：代码侧六枚、DDL 侧五枚，PG 腿于是永远写不进缺的那一格。
    """
    from_ddl = status_domain_through(NEW_VERSION)
    from_pg_statuses = set(store.PG_STATUSES)
    from_all_statuses = set(store.ALL_STATUSES)

    assert from_ddl == from_pg_statuses, (
        "0013 落盘的 CHECK 与 PG_STATUSES 分家："
        f"只在 DDL={sorted(from_ddl - from_pg_statuses)} 只在代码={sorted(from_pg_statuses - from_ddl)}"
    )
    assert from_ddl == from_all_statuses, (
        "0013 落盘的 CHECK 与 ALL_STATUSES 分家："
        f"只在 DDL={sorted(from_ddl - from_all_statuses)} 只在代码={sorted(from_all_statuses - from_ddl)}"
    )
    assert from_pg_statuses == from_all_statuses, (
        "内存腿能写的与 PG 腿能写的不是同一组词，缺的那一枚就是写不进去的那一枚"
    )
    assert store.DECIDED_STATUSES <= from_all_statuses, "终态必须是值域的子集"
    assert len(from_all_statuses) == len(store.ALL_STATUSES), "ALL_STATUSES 里有重名"
    assert store.FAILED in from_ddl, "R175 那一格今天必须能进 PG"


def test_the_widening_admits_exactly_the_status_that_was_missing_and_nothing_else():
    """判据 1 的"纯前滚"与判据 2 的"不许顺手多放一格"合起来读：新域必须是旧域的真超集。

    真超集不只是好看：``ADD CONSTRAINT`` 会校验存量行，放开后的域若是旧域的子集或与之交叉，客户库里
    已存在的那一格就会被新约束判死，迁移当场失败。差集还须恰为 R175 新加的那一枚。
    """
    before = status_domain_through(BASE_VERSION)
    after = status_domain_through(NEW_VERSION)

    assert before < after, f"放开后的域不是 0008 那一域的超集：{sorted(before)} -> {sorted(after)}"
    assert after - before == {store.FAILED}, sorted(after - before)
    assert store.FAILED not in before, (
        "0008 是已发布迁移，它的文本不许被改写：放开只许发生在前滚的那一版里"
    )
    assert after == before | {store.FAILED}


def test_0013_is_forward_only_and_writes_no_rows():
    """判据 1 的字面要求：全文零 UPDATE、零回填、零 DROP TABLE，语句种类只有 ``alter table``。"""
    statements = statements_of(NEW_VERSION)

    assert len(statements) == 2, statements
    assert {statement_head(statement) for statement in statements} == {"alter table"}
    assert not [statement for statement in statements if writes_rows(statement)], statements
    joined = " ".join(statements).lower()
    for forbidden in (
        "update ", "insert into", "delete from", "merge ", "truncate ", "copy ", "select ",
        "drop table", "drop index", "drop column", "add column", "alter column", "create index",
        "set not null", "drop default", "set default", "refresh ", "vacuum ", "analyze ",
    ):
        assert forbidden not in joined, f"0013 里出现了 {forbidden!r}：这一版只放开约束域"
    tables = {
        re.search(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)", statement, re.IGNORECASE).group(1).lower()
        for statement in statements
    }
    assert tables == {TABLE}, tables


def test_the_landed_file_reapplies_to_the_identical_schema():
    """判据 1 的"可重跑"，凭据只有文档原文与落盘文本的配对，重放器只当防呆。

    正向按三件事一起判：① ``0013`` 每条 ``ADD CONSTRAINT`` 之前都有一枚带 ``IF EXISTS`` 的同名
    DROP —— 这是文档里唯一能保证"第二遍不因已存在而中断"的形状（``ADD table_constraint`` 那一形
    文档没给任何 no-error 写法，引文见 ``DOCUMENTED_NO_ERROR_FORMS`` 上方）；② 文件用到的守卫恰好
    是文档明写的两形，一枚不多一枚不少；③ 同一版重放两遍，表集合、status 域、索引逐字段不变。
    ③ 不许靠重放器宽容得来：``collisions`` 必须仍为空，且第二遍的 ``notices`` 里不许出现
    "constraint ... does not exist" —— 出现就说明第一遍根本没建上，那条"不变"是空的。
    """
    statements = statements_of(NEW_VERSION)

    paired, bare = add_drop_pairing(statements)
    assert bare == [], f"有裸 ADD，第二遍执行没有文档凭据可依：{bare}"
    assert paired == [(1, 0, CONSTRAINT_NAME)], paired

    for statement in statements:
        assert undocumented_forms_in(statement) == (), statement
    assert [no_error_forms_in(statement) for statement in statements] == [
        ("alter table if exists", "drop constraint if exists"),
        ("alter table if exists",),
    ], "0013 用到的 no-error 形必须恰好是文档明写的这两形"

    once = apply_version(replay_through(BASE_VERSION), NEW_VERSION)
    twice = apply_version(_clone(once), NEW_VERSION)

    assert once.tables == twice.tables, "第二遍改动了表集合"
    assert once.status_checks == twice.status_checks, "第二遍改动了 CHECK：这一版不幂等"
    assert once.indexes == twice.indexes, "第二遍改动了索引"
    assert twice.collisions == [], "第二遍撞上同名 ADD：可重跑没靠配对，靠的是重放器"
    assert [
        notice for notice in twice.notices if "does not exist" in notice and "constraint" in notice
    ] == [], "第二遍应当找得到那一枚约束：找不到就说明第一遍没真的建上"
    assert status_domain_through(NEW_VERSION) == status_domain_through(BASE_VERSION) | {store.FAILED}


def test_a_mutilated_pairing_leaves_the_add_bare_and_this_file_goes_red():
    """反证（判据 7 的第三把）：可重跑性凭据的哪一角被摘掉，本件都必须当场红。

    文档侧理由：``DROP CONSTRAINT [ IF EXISTS ]`` 是"约束不在也不报错、改出 notice"的唯一凭据，
    而 ``ADD table_constraint`` 没有对应的 no-error 形 —— 所以摘掉 DROP、把 DROP 挪到 ADD 之后、
    或去掉 DROP 的 ``IF EXISTS``，第二遍都不再具资格被叫做可重跑。第四形更糟：拿文档里根本不存在
    的 ``ADD CONSTRAINT IF NOT EXISTS`` 求幂等，重放器连读都不该读懂它。
    """
    statements = statements_of(NEW_VERSION)
    paired, bare = add_drop_pairing(statements)
    assert paired == [(1, 0, CONSTRAINT_NAME)] and bare == []

    unguarded = _DROP_CONSTRAINT.sub(
        lambda m: f"ALTER TABLE IF EXISTS {m.group('table')} DROP CONSTRAINT {m.group('name')}",
        statements[0],
    )
    variants = {
        "摘掉 DROP": statements[1:],
        "DROP 挪到 ADD 之后": [statements[1], statements[0]],
        "DROP 去掉 IF EXISTS": [unguarded, statements[1]],
    }
    for label, variant in variants.items():
        still_paired, still_bare = add_drop_pairing(variant)
        assert still_bare != [], f"{label}：本件必须认得出裸 ADD"
        assert still_paired == [], f"{label}：不该再有配对：{still_paired}"
        assert {name for _index, name in still_bare} == {CONSTRAINT_NAME}, still_bare

    hacked = [
        statements[0],
        re.sub(r"(?i)ADD CONSTRAINT", "ADD CONSTRAINT IF NOT EXISTS", statements[1]),
    ]
    assert undocumented_forms_in(hacked[1]) == ("add constraint if not exists",)
    assert _ADD_CONSTRAINT.search(hacked[1]) is None, (
        "文档里没有的守卫形必须读不成一条可认的 ADD，而不是被假装认识"
    )


def test_the_replay_model_still_refuses_a_bare_re_add_but_that_refusal_is_not_the_warrant():
    """重放器同名 ADD 抛错是建模，不是 PG 凭据：本枚钉它"仍然会拒"，更钉它"一次都不许被用到"。

    上一版这里写的是"PG 必然报 constraint already exists，本件按同一语义拒绝"，等于拿自己的模型
    当证据。凭据现在全在 ``add_drop_pairing`` 与文档引文上；这枚用例只守两件事：模型没变宽（把
    ADD 单独喂进去照旧拒，且留痕），以及真目录重放到任何一版都不曾触发它 —— 也就是说本单的可重跑
    结论里没有一分钱来自模型。
    """
    statements = statements_of(NEW_VERSION)
    add_only = [item for item in statements if "add constraint" in item.lower()]
    assert len(add_only) == 1, add_only

    state = replay_through(BASE_VERSION)
    with pytest.raises(ReplayError, match=CONSTRAINT_NAME):
        apply_statement(state, add_only[0])
    assert state.collisions == [f"{TABLE}.{CONSTRAINT_NAME}"], "模型的拒绝也要留痕，不许静默"

    for item in MIGRATIONS:
        assert replay_through(item.version).collisions == [], (
            f"重放到 {item.version} 靠了同名 ADD 的宽容：这才是真该修的东西"
        )




def test_both_statements_are_guarded_and_a_database_without_the_table_skips_them():
    """守卫式：没建表的库执行这一版必须跳过而不是中断部署事务；两枚都要带 ``IF EXISTS``。"""
    statements = statements_of(NEW_VERSION)
    lowered = [statement.lower() for statement in statements]

    assert all(re.match(r"alter table if exists\b", text) for text in lowered), statements
    assert "drop constraint if exists" in lowered[0] and "add constraint" not in lowered[0]
    assert "add constraint" in lowered[1] and "drop constraint" not in lowered[1]

    fresh = SchemaState()
    for statement in statements:
        apply_statement(fresh, statement)
    assert fresh.tables == set()
    assert fresh.status_checks == {} and fresh.indexes == {}
    assert len(fresh.notices) == 2, fresh.notices


# ------------------------------------------------------ 判据 2 的另一半：不许有第三份
def test_the_vocabulary_is_written_in_sql_exactly_twice_and_both_are_the_same_words_or_supersets():
    """整册目录里 status 的封闭集只许出现在 0008 与 0013 两处。

    0008 那一处是历史（不许改写），0013 这一处是现行域；第三处拼写一旦长出来，就有两份 DDL 与一份
    代码互相指认，而本单的判据 2 只对判三方。
    """
    enumerations = [
        (item.version, table, name, words)
        for item in MIGRATIONS
        for table, name, words in status_enumerations(item.sql)
    ]
    versions = [version for version, _, _, _ in enumerations]

    assert versions == [BASE_VERSION, NEW_VERSION], enumerations
    assert {table for _, table, _, _ in enumerations} == {TABLE}
    assert {name for _, _, name, _ in enumerations} == {CONSTRAINT_NAME}
    by_version = {version: words for version, _, _, words in enumerations}
    assert by_version[NEW_VERSION] == status_domain_through(NEW_VERSION)
    assert by_version[BASE_VERSION] < by_version[NEW_VERSION]


def test_this_file_carries_no_second_copy_of_the_status_vocabulary():
    """判据 2 要求"不许把词表抄第二份进测试"，这一枚就是那句要求的可查形状。

    取值一律现读：DDL 走上面的重放器，代码走 ``app.storage.pending_approvals`` 的常量。AST 自查让
    "顺手写一枚字面量"这件事在本文件里活不下来。
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    vocabulary = set(store.ALL_STATUSES)

    copied = sorted(
        {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in vocabulary
        }
    )
    assert copied == [], f"本文件把 {copied} 抄成了字面量：词表只有三处，这是第四处"


# --------------------------------------------------------- 判据 4：两枚 partial index
def test_the_partial_indexes_of_0008_still_hold_after_the_domain_widens():
    """放开取值域之后，``WHERE status = 'awaiting'`` 的两枚 partial index 仍然成立。

    成立的理由不是"看着没事"，是三件事合起来：0013 一枚索引语句都没发（索引集合与 0008 之后逐字
    相同）；两枚谓词点名的那一格语义没变（它不是终态，``mark_status`` 也拒把它写成终态，产品自己的
    ``_is_open`` 仍只对这一格为真）；新放开的那一枚是终态，所以它天然落在两枚谓词之外 —— 挂起槽位
    就此让开，同一会话的下一轮挂起不再被那一行永远批不完的账占着。
    """
    before = indexes_through(BASE_VERSION)
    after = indexes_through(NEW_VERSION)

    assert before == after, "0013 一枚索引都没动；动了就必须回到这里指名"
    assert set(after) == {
        "pending_approvals_owner_idx",
        "pending_approvals_open_session_idx",
        "pending_approvals_expiry_idx",
    }, sorted(after)
    partials = {name: info for name, info in after.items() if info.predicate}
    assert set(partials) == {
        "pending_approvals_open_session_idx",
        "pending_approvals_expiry_idx",
    }, sorted(partials)
    domain = status_domain_through(NEW_VERSION)
    for name, info in partials.items():
        assert predicate_word(info.predicate) == store.AWAITING, (name, info.predicate)
        assert info.predicate == f"status = '{store.AWAITING}'", (name, info.predicate)
        assert store.AWAITING in domain
    assert partials["pending_approvals_open_session_idx"].unique is True
    assert partials["pending_approvals_open_session_idx"].columns == ("session_id",)

    assert store.AWAITING not in store.DECIDED_STATUSES
    with pytest.raises(ValueError, match="unsupported pending approval status"):
        store.mark_status("r190-partial-index-semantics", store.AWAITING)
    assert store.FAILED in store.DECIDED_STATUSES
    assert store._is_open(_record(store.FAILED), _NOW) is False
    assert store._is_open(_record(store.AWAITING), _NOW) is True


# --------------------------------------------------- 判据 1/6：落盘字节与登记的数字
def test_the_landed_file_is_certified_by_the_manifest_and_the_loader():
    """0013 的数字：归一后的盘上字节 == loader 文本 == manifest == schema_migrations 会记的那枚。

    刻意不钉"盘上不许出现 CRLF"：本仓库 ``core.autocrlf`` 为 true，任何新 worktree 检出都会把
    迁移件变成 CRLF，那一条是机器依赖而不是不变量（原判据 10 的教训，见
    ``tests/test_r183_184_migration_pair.py`` 同名改口）。SQL 里 CRLF 对语义无害，真性质是
    "``\\n`` 之外没有裸 ``\\r``"与"归一后字节 == 登记的数字"。本件落盘时按 LF 写，这一版报告里
    另有实测字节数。
    """
    raw = NEW_PATH.read_bytes()
    text = NEW_PATH.read_text(encoding="utf-8")
    normalized = raw.replace(b"\r\n", b"\n")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    registered = next(item for item in MIGRATIONS if item.version == NEW_VERSION).checksum

    assert raw.count(b"\r") == raw.count(b"\r\n"), "出现裸 CR（``\\n`` 之外的单枚 ``\\r``）：归一化会读不出行"
    assert not raw.startswith(b"\xef\xbb\xbf"), "带 BOM 会让首行注释多出看不见的字符"
    assert normalized.endswith(b"\n") and not normalized.endswith(b"\n\n"), "文件末尾恰好一个换行"
    assert sha256(normalized).hexdigest() == sha256(text.encode("utf-8")).hexdigest()
    assert sha256(normalized).hexdigest() == manifest[NEW_FILENAME] == registered, {
        "bytes": sha256(normalized).hexdigest(),
        "manifest": manifest[NEW_FILENAME],
        "loader": registered,
    }


def _clone(state: SchemaState) -> SchemaState:
    return SchemaState(
        tables=set(state.tables),
        status_checks={
            table: dict(checks) for table, checks in state.status_checks.items()
        },
        indexes={table: dict(items) for table, items in state.indexes.items()},
        notices=list(state.notices),
        unmodeled=list(state.unmodeled),
        collisions=list(state.collisions),
    )
