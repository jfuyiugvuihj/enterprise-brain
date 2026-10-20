"""R251 判据 J-4：0014 的首装与升装两条路都要能跑，而且跑第二遍不报错。

🔴 先把这条判据的**形状**说清楚：**全程离线，一枚真 PostgreSQL 都没连过**。
本仓库的测试环境由 tests/conftest.py 把 DATABASE_URL 钉死在 127.0.0.1:1（那上面没有库），
接真库需要业主授权改部署环境，本单不动。这里跑的是 PostgreSQL 的 **DDL 语义模型**：输入只有
``migrations/*.sql`` 的文本，判的是六件可查的事，与 tests/test_r120_clean_install_first_boot.py、
tests/test_r183_184_migration_pair.py、tests/test_r190_status_failed_domain.py 用的是同一台重放机
（加列语义直接借 ``replay_added_columns``，本件另补它没建模的 DROP/ADD CONSTRAINT 与 COMMENT）。

1. **首装**：空库把 0001..0014 依序重放，凡点名 ``alerts`` 的语句都必须被模型认下
   （``unmodeled == []``），一条错误都不许有（``errors == []``）。
2. **次序**：``ADD CONSTRAINT`` 读的 ``status`` 必须已经在那儿。把 0014 里"加列"与"加约束"两段
   调个头，本件当场红（column does not exist）—— 这是"列先于约束"这句主张的可查形状，
   不是靠注释维持。
3. **升装**：0013 时刻的存量行过一遍 0014，只吃常量默认值；不许长出"NOT NULL 无默认值"这种
   必须回填才成立的形状，也不许动任何一枚已存的格子。
4. **重跑**：同一版再跑一次，全部落到 ``IF EXISTS`` / ``IF NOT EXISTS`` 的 NOTICE 支路，列、
   定义、约束、行一字不变。PG 没有 ``ADD CONSTRAINT IF NOT EXISTS`` 这个语法形状，所以那一枚
   的唯一护身符是紧邻在前的带守卫 DROP —— 本件按"必须紧邻"钉死，并顺手钉住全目录不许出现那枚
   不存在的语法（有人拿它"修好"重复执行，就会在这里红）。
5. **词表**：DDL 的 CHECK 取值集合 == ``ALERT_STATUSES``，且 ``status`` 的列默认值落在这个集合里
   —— 否则存量行落地即违约，首装会在 UPDATE 之外以另一种方式停住。
6. **账**：manifest 数字 == 落盘字节 == loader 登记；目录连续到 0014；开发库自建表
   （``app/api/v1/alerts.py::_ensure``）与懒补 DDL 的列集合、默认值，与迁移重放出来的结果逐枚相等。

顺带一枚本件**实测抓到的**坑并当场修掉：0014 的 ``COMMENT ON ... IS '... ;'`` 里原来有一枚位于
字符串字面量**内部**的分号，``executable_statements`` 那种按 ``;`` 裸切的工具会把它切成两半，
于是"这一版只发了 alter table / comment on 两类语句"这句真话在机器眼里变成假话（多出一枚
head 为 ``the product`` 的碎片）。R190 的逐目录扫描也走那把裸切刀，今天是运气没踩着。改法是删
字面量里那枚分号（散文同义改写，SQL 语义一字没动），并把"两把切刀必须切出同一份语句"钉成 T-9
—— 这才是那枚坑的可查形状。

📌 **R256 追记（改的是本件的地基，不改本件的结论）**：那两把裸切刀——
``test_r183_184_migration_pair.executable_statements`` 与 ``test_document_catalog_sync._statements``——
今天已经换成认字面量的切法，所以下一版迁移允许在 ``COMMENT ON`` 的散文里写分号。T-9 那格
随之换义：从「字面量里不许出现分号」变成「两把独立写成的切刀不许分家」。0014 本身一个字没动
（前滚目录），它今天仍然没有字面量内的分号。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from pathlib import Path

import pytest

import app.api.v1.alerts as alerts_module
from app.api.v1.alerts import (
    ALERT_DISPOSAL_DEFAULTS,
    ALERT_STATUSES,
    alert_disposal_target_status,
)
from app.db.migrations import MIGRATIONS, discover_migrations
from test_r183_184_migration_pair import (
    added_column_specs,
    created_columns,
    executable_statements,
    replay_added_columns,
    rows_at,
    schema_through,
    split_top_level,
    statement_head,
    writes_rows,
)
from test_r349_catalog_tail_ledger import CATALOG_TAIL_NAME, CATALOG_TAIL_VERSION

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"
MANIFEST_PATH = MIGRATIONS_DIR / "manifest.json"

#: 本单落的那一版。目录尾号由 T-1 现判，不靠这里抄。
LANDED_VERSION = "0014"
LANDED_FILENAME = "0014_alert_disposal_columns.sql"
LANDED_PATH = MIGRATIONS_DIR / LANDED_FILENAME
PRIOR_VERSION = "0013"

#: 🔴 目录尾号：本件今天红的那一枚就在这两行 —— 0015 / dataset_version_scope_columns 是
#: R256 那份手抄的账，R299 排了 0016（notification_states）之后没人替它改口，门就红了。
#: 数字从此不在这里抄：CATALOG_TAIL_VERSION 与 CATALOG_TAIL_NAME 一律从 tests/test_r349_catalog_tail_ledger.py
#: import（同族：test_document_catalog_sync、test_r46_activity_signals、
#: test_r120_clean_install_first_boot、test_r183_184_migration_pair、
#: test_r190_status_failed_domain）。谁排下一号去那一枚文件连名带主题一起改口，别改本件。
#: 本件的主题是 0014，所以 ``LANDED_VERSION`` 永远写 0014；T-1 那句「目录连续到几号」判的是
#: 目录的事实，跟着账本走 —— 主题版与尾号分成两条钉是收紧（多了一条「主题版必须还在目录
#: 里」），不是把引信拆掉；本件重放的仍然是 0001..0014。

TARGET_TABLE = "alerts"
#: 八枚处置列的名单**取自产品代码**（``ALERT_DISPOSAL_DEFAULTS`` 的键序），本文件一枚都不抄。
DISPOSAL_COLUMNS: tuple[str, ...] = tuple(ALERT_DISPOSAL_DEFAULTS)
CONSTRAINT_NAME = "alerts_status_check"

#: 允许出现在这一版里的语句种类。加约束与删约束都是 ``alter table``，不需要第三种头。
_LANDED_HEADS = frozenset({"alter table", "comment on"})

_COMMENT_LINE = re.compile(r"^[ \t]*--.*$", re.MULTILINE)
_NAMES_TARGET = re.compile(rf"\b{TARGET_TABLE}\b", re.IGNORECASE)
_CREATE_TABLE_HEAD = re.compile(
    r"^CREATE\s+TABLE\s+(?P<guard>IF\s+NOT\s+EXISTS\s+)?(?P<table>\w+)", re.IGNORECASE
)
_CREATE_INDEX_HEAD = re.compile(
    r"^CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<guard>IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>\w+)\s+ON\s+(?P<relation_guard>IF\s+EXISTS\s+)?(?P<table>\w+)"
    r"(?:\s*\((?P<columns>[^)]*)\))?",
    re.IGNORECASE,
)
_DROP_CONSTRAINT = re.compile(
    r"ALTER\s+TABLE\s+(?P<table_guard>IF\s+EXISTS\s+)?(?P<table>\w+)\s+"
    r"DROP\s+CONSTRAINT\s+(?P<name_guard>IF\s+EXISTS\s+)?(?P<name>\w+)",
    re.IGNORECASE,
)
_ADD_CONSTRAINT = re.compile(
    r"ALTER\s+TABLE\s+(?P<table_guard>IF\s+EXISTS\s+)?(?P<table>\w+)\s+"
    r"ADD\s+CONSTRAINT\s+(?P<name>\w+)\s+(?P<body>CHECK\s*\(.+\))",
    re.IGNORECASE | re.DOTALL,
)
_CHECK_IN = re.compile(
    r"^CHECK\s*\(\s*(?P<column>\w+)\s+IN\s*\((?P<words>[^)]*)\)\s*\)$", re.IGNORECASE
)
_ALTER_TABLE = re.compile(
    r"^ALTER\s+TABLE\s+(?P<guard>IF\s+EXISTS\s+)?(?P<table>\w+)", re.IGNORECASE
)
_COMMENT_COLUMN = re.compile(
    r"^COMMENT\s+ON\s+COLUMN\s+(?P<table>\w+)\.(?P<column>\w+)", re.IGNORECASE
)
#: 索引表达式里不是列名的那些词（够用即可：本目录给 alerts 发的索引只有 (id DESC) 一枚）。
_INDEX_KEYWORDS = frozenset({"desc", "asc", "nulls", "first", "last", "collate", "varchar_text_ops"})


def check_words(body: str) -> tuple[str, frozenset[str]] | None:
    """``CHECK (col IN ('a','b'))`` -> ``("col", {"a", "b"})``；形状不合回 ``None``。"""
    match = _CHECK_IN.match(" ".join(body.split()))
    if match is None:
        return None
    words = frozenset(
        part.strip()[1:-1].replace("''", "'").lower()
        for part in split_top_level(match.group("words"))
        if part.strip()
    )
    return match.group("column").lower(), words


@dataclass
class Replay:
    """一份 PostgreSQL DDL 语义的最小模型：只装 ``alerts`` 这条线用得上的四件事。

    ``errors`` 是"PostgreSQL 会在这里停住"的清单，``notices`` 是"带了守卫所以跳过"的清单，
    ``unmodeled`` 是"这句模型不认识，所以本件的结论对它不成立"的清单 —— 三枚都必须为空才算
    这一版跑得通（``notices`` 反过来：重跑时必须**只**长 notices）。
    """

    columns: dict[str, list[str]] = field(default_factory=dict)
    definitions: dict[tuple[str, str], str] = field(default_factory=dict)
    constraints: dict[str, dict[str, str]] = field(default_factory=dict)
    indexes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    unmodeled: list[str] = field(default_factory=list)

    def has_column(self, table: str, column: str) -> bool:
        return column in self.columns.get(table, [])

    def snapshot(self) -> dict:
        """判"重跑没动 schema"用的可比对形状：列、定义、约束、索引，一次全取。"""
        return {
            "columns": {table: list(names) for table, names in self.columns.items()},
            "definitions": dict(self.definitions),
            "constraints": {table: dict(named) for table, named in self.constraints.items()},
            "indexes": dict(self.indexes),
        }


def _apply_alter(state: Replay, statement: str, row_count: int) -> bool:
    """``ALTER TABLE`` 的三种子形状：加列 / 删约束 / 加约束。认下了回 True。"""
    specs = added_column_specs(statement)
    if specs:
        for spec in specs:
            if not spec.table_guarded and spec.table not in state.columns:
                state.errors.append(f"{spec.table}: relation does not exist")
                return True
            if spec.table not in state.columns:
                state.notices.append(f"{spec.table}: relation does not exist, statement skipped")
                return True
            if state.has_column(spec.table, spec.column):
                if spec.column_guarded:
                    state.notices.append(
                        f"{spec.table}.{spec.column}: column already exists, statement skipped"
                    )
                else:
                    state.errors.append(f"{spec.table}.{spec.column}: column already exists")
                continue
            if spec.not_null and spec.default_literal is None and row_count:
                state.errors.append(
                    f"{spec.table}.{spec.column}: column contains null values "
                    "(a NOT NULL column without a constant default cannot be added to a populated table)"
                )
                continue
            state.columns[spec.table].append(spec.column)
            state.definitions[(spec.table, spec.column)] = spec.definition
        return True

    drop = _DROP_CONSTRAINT.search(statement)
    if drop is not None:
        table = drop.group("table").lower()
        name = drop.group("name").lower()
        if table not in state.columns:
            if drop.group("table_guard"):
                state.notices.append(f"{table}: relation does not exist, statement skipped")
            else:
                state.errors.append(f"{table}: relation does not exist")
            return True
        checks = state.constraints.setdefault(table, {})
        if name not in checks:
            if drop.group("name_guard"):
                state.notices.append(f"constraint {name} for relation {table} does not exist, statement skipped")
            else:
                state.errors.append(f"constraint {name} for relation {table} does not exist")
            return True
        del checks[name]
        return True

    add = _ADD_CONSTRAINT.search(statement)
    if add is not None:
        table = add.group("table").lower()
        name = add.group("name").lower()
        body = " ".join(add.group("body").split())
        if table not in state.columns:
            if add.group("table_guard"):
                state.notices.append(f"{table}: relation does not exist, statement skipped")
            else:
                state.errors.append(f"{table}: relation does not exist")
            return True
        checks = state.constraints.setdefault(table, {})
        if name in checks:
            # PostgreSQL 没有 ADD CONSTRAINT IF NOT EXISTS 这个形状：重名只有 DuplicateObject 一条路。
            state.errors.append(f"constraint {name} for relation {table} already exists")
            return True
        read = check_words(body)
        if read is None:
            state.unmodeled.append(statement)
            return True
        column, _words = read
        if not state.has_column(table, column):
            state.errors.append(
                f'{column}: column named in constraint {name} does not exist (order of statements)'
            )
            return True
        checks[name] = body
        return True

    return False


def apply_statement(state: Replay, statement: str, *, row_count: int = 0) -> None:
    """执行一枚语句。与 ``alerts`` 无关的语句直接放过（本件不判它们，也不记 unmodeled）。"""
    if not _NAMES_TARGET.search(statement):
        return
    head = statement_head(statement)

    if head == "create table":
        created = created_columns(statement)
        for table, names in created.items():
            guarded = bool(_CREATE_TABLE_HEAD.match(statement).group("guard"))
            if table in state.columns:
                if guarded:
                    state.notices.append(f"{table}: relation already exists, statement skipped")
                else:
                    state.errors.append(f"{table}: relation already exists")
                continue
            state.columns[table] = []
            for name in names:
                state.columns[table].append(name)
                state.definitions[(table, name)] = "created with the table"
        return

    if head in {"create index", "create unique"}:
        match = _CREATE_INDEX_HEAD.match(statement)
        if match is None:
            state.unmodeled.append(statement)
            return
        table = match.group("table").lower()
        name = match.group("name").lower()
        if table not in state.columns:
            if match.group("relation_guard"):
                state.notices.append(f"{table}: relation does not exist, index skipped")
            else:
                state.errors.append(f"{table}: relation does not exist (index {name})")
            return
        for token in (match.group("columns") or "").split():
            if token.lower().strip(",") in _INDEX_KEYWORDS or not re.fullmatch(r"\w+", token):
                continue
            if not state.has_column(table, token.lower()):
                state.errors.append(f"{token}: column named by index {name} does not exist")
        if name in state.indexes:
            if match.group("guard"):
                state.notices.append(f"index {name} already exists, statement skipped")
            else:
                state.errors.append(f"index {name} already exists")
            return
        state.indexes[name] = table
        return

    if head == "comment on":
        match = _COMMENT_COLUMN.match(statement)
        if match is None:
            state.unmodeled.append(statement)
            return
        table, column = match.group("table").lower(), match.group("column").lower()
        if not state.has_column(table, column):
            state.errors.append(f'{column}: column of relation {table} does not exist')
        return

    if head == "alter table" and _apply_alter(state, statement, row_count):
        return

    state.unmodeled.append(statement)


def replay_versions(through: str, *, since: str = "") -> Replay:
    """把 ``since`` 之后、``through`` 之前（含）各版的语句按版次次序执行一遍。"""
    state = Replay()
    for item in MIGRATIONS:
        if item.version > through or item.version <= since:
            continue
        for statement in executable_statements(item.sql):
            apply_statement(state, statement)
    return state


def quoted_statements(sql: str) -> list[str]:
    """按 PostgreSQL 自己的读法切语句：字面量里的 ``;`` 不是语句结束符。"""
    body = _COMMENT_LINE.sub("", sql)
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0
    while index < len(body):
        char = body[index]
        if char == "'":
            if in_string and body[index + 1 : index + 2] == "'":
                current.append("''")
                index += 2
                continue
            in_string = not in_string
        if char == ";" and not in_string:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    assert not in_string, "字符串字面量没有闭合：本件的切法对它不成立"
    return [" ".join(part.split()) for part in parts if part.strip()]


@pytest.fixture(scope="module")
def landed_sql() -> str:
    return LANDED_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def landed_statements(landed_sql) -> list[str]:
    return executable_statements(landed_sql)


def constraint_statement(statements: list[str]) -> tuple[int, str]:
    """返回 ``(序位, ADD CONSTRAINT 语句)``。"""
    for index, statement in enumerate(statements):
        if _ADD_CONSTRAINT.search(statement):
            return index, statement
    raise AssertionError("这一版没有 ADD CONSTRAINT：判据 J-4 的封闭集去哪了")


# ---------------------------------------------------------------- T-1 目录的账
def test_the_catalog_is_contiguous_and_ends_at_the_named_tail():
    """首装的前提：目录是 0001..尾号 一枚不缺的连续序列，而且 loader 与磁盘说的是同一件事。

    本件落 0014 的那一轮，「连续到 LANDED_VERSION」与「连续到尾号」还是同一句话；R256 排了
    0015 之后它俩不再是同一件事，所以拆成两条分开钉——目录仍然一枚缺口都不许有，而 0014 那五格
    重放判的照旧是 0001..0014。这是收紧（多了一条「主题版必须还在目录里」），不是把引信拆掉。
    """
    versions = [item.version for item in MIGRATIONS]

    assert versions == [
        f"{number:04d}" for number in range(1, int(CATALOG_TAIL_VERSION) + 1)
    ], versions
    assert versions == sorted(versions), "loader 登记的版次序不单调：首装的次序就不是它"
    assert LANDED_VERSION in versions, "本件的主题版被人从目录里摘走了"
    assert versions[-1] == CATALOG_TAIL_VERSION, (
        "尾号账本过期：去改 tests/test_r349_catalog_tail_ledger.py 那两枚字面量，别改本件"
    )
    assert MIGRATIONS[-1].name == CATALOG_TAIL_NAME, (
        "尾号那一版的主题名与账本对不上：同样只在 tests/test_r349_catalog_tail_ledger.py 改，别改本件"
    )
    assert next(item for item in MIGRATIONS if item.version == LANDED_VERSION).name == (
        LANDED_FILENAME[: -len(".sql")].split("_", 1)[1]
    )
    assert discover_migrations() == MIGRATIONS
    assert sorted(json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))) == sorted(
        path.name for path in MIGRATIONS_DIR.glob("*.sql")
    )


# ---------------------------------------------------------------- T-2 首装那条路
def test_a_clean_database_replays_every_version_up_to_the_landed_one():
    """判据 J-4 第一半：空库从 0001 一路跑到 0014，模型不报错、也没有一句它不认识的。

    ``unmodeled == []`` 是这格的前提而不是装饰：只要有一句点名 ``alerts`` 的语句落在模型外，
    "跑得通"这句结论就对它不成立，本件必须红而不是假装通过。
    """
    state = replay_versions(LANDED_VERSION)

    assert state.errors == [], state.errors
    assert state.unmodeled == [], state.unmodeled
    assert TARGET_TABLE in state.columns, "0003 没把 alerts 建出来：首装根本轮不到 0014"
    for column in DISPOSAL_COLUMNS:
        assert state.has_column(TARGET_TABLE, column), column
    assert list(state.constraints[TARGET_TABLE]) == [CONSTRAINT_NAME]


def test_the_landed_columns_are_not_there_before_the_landed_version():
    """0013 那一刻处置列一枚都没有 —— 否则"这一版补齐读路径"这句话就没了对象。"""
    prior = replay_versions(PRIOR_VERSION)

    assert prior.errors == [] and prior.unmodeled == []
    assert [column for column in DISPOSAL_COLUMNS if prior.has_column(TARGET_TABLE, column)] == []
    assert prior.constraints.get(TARGET_TABLE, {}) == {}


# ---------------------------------------------------------------- T-3 次序即语义
def test_the_constraint_is_added_after_the_column_it_reads_not_before():
    """存量库（3 行）按 0014 自己的语句次序执行一遍：必须一枚错误都没有。"""
    state = replay_versions(PRIOR_VERSION)
    statements = executable_statements(LANDED_PATH.read_text(encoding="utf-8"))

    for statement in statements:
        apply_statement(state, statement, row_count=3)

    assert state.errors == [], state.errors
    assert state.unmodeled == [], state.unmodeled
    assert state.has_column(TARGET_TABLE, "status")


def test_reordering_the_landed_file_so_the_constraint_comes_first_goes_red():
    """反证的正向对照：把 ADD CONSTRAINT 挪到最前面，模型必须在这里停住。

    这一格是 T-3 前一格的**牙齿**所在 —— 如果模型对"约束读一枚还不存在的列"无感，前一格就是
    一句空话，挪次序也不会有任何反应。它红的条件与前一格同因，所以它不判产品，只判这台重放机。
    """
    statements = executable_statements(LANDED_PATH.read_text(encoding="utf-8"))
    index, constraint = constraint_statement(statements)
    reordered = [constraint] + statements[:index] + statements[index + 1 :]

    state = replay_versions(PRIOR_VERSION)
    for statement in reordered:
        apply_statement(state, statement, row_count=3)

    assert any("status" in error and "does not exist" in error for error in state.errors), state.errors
    assert state.has_column(TARGET_TABLE, "status") is True


# ---------------------------------------------------------------- T-4 升装那条路
def test_the_upgrade_from_the_prior_version_fills_defaults_and_touches_no_stored_cell():
    """判据 J-4 第二半：0013 时刻的存量行走 0014，只吃常量默认值，已存的格子一枚不变。

    ``warnings`` 那一格是判据 2 的形状（NOT NULL 而拿不到常量默认值 => 必须有人回填）；
    ``skipped`` 那一格在升装这条路上必须是空 —— 非空就意味着这一版在"列已经在了"的库上跑，
    那是重跑（T-5），不是升装。
    """
    before = rows_at(TARGET_TABLE, 3, through=PRIOR_VERSION)
    assert {key for row in before for key in row} == set(schema_through(PRIOR_VERSION)[TARGET_TABLE])

    after, warnings, skipped = replay_added_columns(
        before, TARGET_TABLE, through=LANDED_VERSION, since=PRIOR_VERSION
    )

    assert (warnings, skipped) == ([], [])
    assert len(after) == len(before)
    for index, (row, landed) in enumerate(zip(before, after)):
        for column, value in row.items():
            assert landed[column] == value, f"存量列 {column} 被迁移改了"
        for column in DISPOSAL_COLUMNS:
            assert landed[column] == ALERT_DISPOSAL_DEFAULTS[column], (column, index)
    assert [row["status"] for row in after] == [ALERT_DISPOSAL_DEFAULTS["status"]] * 3


def test_an_empty_ledger_takes_the_same_upgrade_path_as_a_populated_one():
    """零行与三行走同一条路：这一版没有任何一句"只有表里有行才成立"的形状。"""
    after, warnings, skipped = replay_added_columns(
        [], TARGET_TABLE, through=LANDED_VERSION, since=PRIOR_VERSION
    )

    assert (after, warnings, skipped) == ([], [], [])


# ---------------------------------------------------------------- T-5 重跑不报错
def test_applying_the_landed_version_twice_leaves_the_schema_where_it_was():
    """同一版跑两遍：第二遍只剩 NOTICE，列、定义、约束、索引一字不动。"""
    statements = executable_statements(LANDED_PATH.read_text(encoding="utf-8"))
    state = replay_versions(PRIOR_VERSION)
    for statement in statements:
        apply_statement(state, statement, row_count=3)
    first = state.snapshot()
    notices_before, errors_before = list(state.notices), list(state.errors)

    for statement in statements:
        apply_statement(state, statement, row_count=3)

    assert state.errors == errors_before == []
    assert state.snapshot() == first
    assert len(state.notices) == len(notices_before) + len(DISPOSAL_COLUMNS), state.notices
    assert all("already exists, statement skipped" in notice for notice in state.notices[len(notices_before) :])


def test_the_rows_read_the_same_after_a_second_run_as_after_the_first():
    """行这一侧的同一件事：第二次重放全部走守卫跳过支路，没有一句无守卫的重复加列。"""
    once, first_warnings, first_skipped = replay_added_columns(
        rows_at(TARGET_TABLE, 2, through=PRIOR_VERSION), TARGET_TABLE,
        through=LANDED_VERSION, since=PRIOR_VERSION,
    )
    twice, second_warnings, second_skipped = replay_added_columns(
        once, TARGET_TABLE, through=LANDED_VERSION, since=PRIOR_VERSION
    )

    assert (first_warnings, first_skipped) == ([], [])
    assert second_warnings == []
    assert len(second_skipped) == len(DISPOSAL_COLUMNS), second_skipped
    assert twice == once


# ---------------------------------------------------------------- T-6 那枚没有守卫的语法
def test_the_only_guard_on_the_constraint_is_a_drop_of_the_same_name_right_before_it():
    """``ADD CONSTRAINT`` 唯一的重复护身符是紧邻其前的带守卫 DROP，而且两者同名同表。

    中间插进任何一句别的语句都不算（"顺序无关"在这里就是错的：DROP 与 ADD 之间若插进了会
    失败的语句，部署事务整笔回滚，那对组合就再也不会以"删掉了再加"的样子落库）。
    """
    statements = executable_statements(LANDED_PATH.read_text(encoding="utf-8"))
    index, add = constraint_statement(statements)

    assert index > 0, statements
    drop = statements[index - 1]
    match = _DROP_CONSTRAINT.search(drop)
    assert match is not None, drop
    assert match.group("name").lower() == CONSTRAINT_NAME, drop
    assert match.group("table").lower() == TARGET_TABLE, drop
    assert match.group("table_guard"), drop
    assert match.group("name_guard"), drop
    assert "if not exists" not in add.lower(), "PG 没有这个语法形状"


def test_no_version_anywhere_in_the_catalog_uses_the_syntax_postgresql_does_not_have():
    """全目录不许出现 ``ADD CONSTRAINT IF NOT EXISTS`` —— 那不是合法的 PostgreSQL。"""
    offenders = [
        (item.version, statement)
        for item in MIGRATIONS
        for statement in executable_statements(item.sql)
        if re.search(r"ADD\s+CONSTRAINT\s+IF\s+NOT\s+EXISTS", statement, re.IGNORECASE)
    ]

    assert offenders == [], offenders


def test_dropping_the_guarded_drop_would_break_the_second_run():
    """前一格的牙齿：把那句 DROP 删掉再跑两遍，模型必须在第二遍的 ADD CONSTRAINT 上停住。

    也就是说"重跑不报错"这件事确实全靠那枚 DROP 撑着，删掉它这一版就不再幂等 —— 本件不许有人
    以"这句没用"为由把它清理掉。
    """
    statements = executable_statements(LANDED_PATH.read_text(encoding="utf-8"))
    index, _add = constraint_statement(statements)
    narrowed = statements[: index - 1] + statements[index:]

    state = replay_versions(PRIOR_VERSION)
    for round_number in (1, 2):
        for statement in narrowed:
            apply_statement(state, statement, row_count=3)
        if round_number == 1:
            assert state.errors == [], state.errors

    assert state.errors == [f"constraint {CONSTRAINT_NAME} for relation {TARGET_TABLE} already exists"]


# ---------------------------------------------------------------- T-7 这一版只发 DDL
def test_the_landed_file_ships_only_guarded_alters_and_comments(landed_sql, landed_statements):
    """语句种类闭合、零写数据、零删除、只动 ``alerts`` 一张表、加列数与列名册一枚不差。

    ``DROP TABLE`` / ``DROP COLUMN`` 这两枚单独判：``DROP CONSTRAINT`` 是本版唯一的删除形状，
    而且它删的是自己上一轮加的那枚约束。谁哪天"顺手清理一下"旧列，这一格先红。
    """
    assert {statement_head(s) for s in landed_statements} <= _LANDED_HEADS, landed_statements
    assert [s for s in landed_statements if writes_rows(s)] == []
    for statement in landed_statements:
        assert not re.search(r"\bDROP\s+(TABLE|COLUMN)\b", statement, re.IGNORECASE), statement

    altered = {
        match.group("table").lower()
        for match in map(_ALTER_TABLE.match, landed_statements)
        if match
    }
    assert altered == {TARGET_TABLE}, altered
    assert all(_ALTER_TABLE.match(s).group("guard") for s in landed_statements if _ALTER_TABLE.match(s)), (
        "有一枚 ALTER TABLE 不带 IF EXISTS：没建过 alerts 的库会在它上面中断部署事务"
    )

    specs = added_column_specs(landed_sql)
    assert [(spec.table, spec.column) for spec in specs] == [
        (TARGET_TABLE, column) for column in DISPOSAL_COLUMNS
    ], specs
    assert all(spec.column_guarded for spec in specs), specs


# ---------------------------------------------------------------- T-8 词表两边同源
def test_the_landed_check_admits_exactly_the_status_the_product_writes(landed_sql, landed_statements):
    """DDL 的封闭集 == ``ALERT_STATUSES``；``status`` 的默认值落在这个集合里。

    默认值必须在集合内：存量行落地就吃这一枚默认值，它要是被 CHECK 拒了，首装与升装都会以另一种
    方式停住（0010 首装必停那枚历史缺陷的形状 —— 见 R90b）。
    """
    _index, add = constraint_statement(landed_statements)
    read = check_words(_ADD_CONSTRAINT.search(add).group("body"))
    assert read is not None, add
    column, words = read

    assert column == "status"
    assert words == frozenset(ALERT_STATUSES), (words, ALERT_STATUSES)
    status_default = next(
        spec.default_literal
        for spec in added_column_specs(landed_sql)
        if spec.column == "status"
    )
    assert status_default == ALERT_DISPOSAL_DEFAULTS["status"]
    assert status_default in words, (status_default, words)


def test_the_only_states_the_machine_can_write_are_the_states_the_check_admits(landed_statements):
    """把状态机每一枚**会改状态**的出口挨个喂给 DDL 的封闭集：一枚不许落在集合外。

    ``assign`` 有意不改状态（``target is current``），所以它不进"写入集" —— 这一格判的正是
    "代码侧写进 ``status`` 列的每一个值，数据库侧都认"，两边各自数一遍才叫同源。
    """
    _index, add = constraint_statement(landed_statements)
    words = check_words(_ADD_CONSTRAINT.search(add).group("body"))[1]
    written = {
        target
        for action in alerts_module.ALERT_ACTIONS
        for status in ALERT_STATUSES
        if (target := alert_disposal_target_status(action, status)) is not None
        and target != status
    }
    self_routed = {
        status
        for action in alerts_module.ALERT_ACTIONS
        for status in ALERT_STATUSES
        if (target := alert_disposal_target_status(action, status)) == status
    }

    assert written <= words, sorted(written - words)
    assert written == frozenset(ALERT_STATUSES) - frozenset({ALERT_DISPOSAL_DEFAULTS["status"]}), written
    assert self_routed == {"open", "acknowledged"}, self_routed
    assert self_routed <= words


# ---------------------------------------------------------------- T-9 落盘的账
def test_the_landed_digest_is_the_bytes_the_loader_reads_and_the_same_statements(landed_sql):
    """清单数字 == 归一后盘上字节 == loader 文本的 sha256 == loader 登记的那枚校验和。

    外加两枚本单实测补上的形状：

    * ``executable_statements``（按 ``;`` 裸切，R190 的逐目录扫描用的是它）与本文件的
      ``quoted_statements``（认字面量）**必须切出同一份语句**。0014 落盘的第一版在
      ``COMMENT ON ... IS '... ;'`` 的字面量**内部**有一枚分号，两把刀切出 12 与 13 两枚不同的
      结果 —— 那句"这一版只发 alter table / comment on"的真话当场在机器眼里变假。现在字面量里
      没有分号了，这一格就是那条修正的钉子：谁再往字面量里塞分号，这里红，而不是让隔壁某件
      按裸切刀工作的测试莫名其妙地红。
    * 行尾不许影响结论：仓库 ``core.autocrlf`` 为 true 且没有 ``.gitattributes`` 给
      ``migrations/*.sql`` 定行尾，所以钉"归一前后逐枚相同"而不是钉"必须是 LF"（后者钉的是这台
      机器怎么检出的，与 R183/R184 同一口径）。
    """
    raw = LANDED_PATH.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    text = LANDED_PATH.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert len(raw) - len(normalized) == raw.count(b"\r\n"), "不许有裸 CR 之外的 \\r"
    assert raw.count(b"\r") == raw.count(b"\r\n"), "出现裸 CR：归一化会吃掉它并改变行结构"
    assert not raw.startswith(b"\xef\xbb\xbf"), "带 BOM 会让首行注释多出看不见的字符"
    assert normalized.endswith(b"\n") and not normalized.endswith(b"\n\n"), "文件末尾恰好一个换行"
    assert executable_statements(text) == quoted_statements(text), (
        "有分号落在字符串字面量内部：按 ; 裸切的工具会把这一版切成别的形状"
    )
    assert executable_statements(raw.decode("utf-8")) == executable_statements(text)

    from_bytes = sha256(normalized).hexdigest()
    from_text = sha256(text.encode("utf-8")).hexdigest()
    registered = next(item for item in MIGRATIONS if item.version == LANDED_VERSION).checksum

    assert from_bytes == from_text == manifest[LANDED_FILENAME] == registered, {
        "bytes": from_bytes,
        "text": from_text,
        "manifest": manifest[LANDED_FILENAME],
        "loader": registered,
    }
    assert sha256(normalized + b" ").hexdigest() != registered, "正向对照失效：多一枚空格都不改数字"


# ---------------------------------------------------------------- T-10 两条读路不许分家
def _dev_create_table() -> str:
    """从 ``app/api/v1/alerts.py`` 的源码里取自建库那句 ``CREATE TABLE IF NOT EXISTS alerts``。"""
    source = Path(alerts_module.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "CREATE TABLE IF NOT EXISTS alerts" in node.value:
                return node.value
    raise AssertionError("自建库不再自己建 alerts 表：这格的前提变了，请连本文件一起改口")


def test_the_self_built_dev_table_lands_the_same_columns_as_the_migrations():
    """非生产分支那句建表语句，列集合必须等于 ``0001..0014`` 重放出来的列集合。

    开发库与生产库从此读同一份处置数据：一条 ``SELECT`` 写在两边跑，任何一侧少一枚列就是运行时
    500。次序不必相同（自建表把八枚内联在 ``read`` 之后，迁移是逐枚追加），所以这里判集合。
    """
    dev = created_columns(executable_statements(_dev_create_table())[0])[TARGET_TABLE]
    migrated = schema_through(LANDED_VERSION)[TARGET_TABLE]

    assert sorted(dev) == sorted(migrated), {"dev": dev, "migrated": migrated}
    assert len(dev) == len(set(dev)) == len(migrated)


def test_the_lazy_column_defaultss_and_the_migration_defaultss_are_one_table():
    """懒补 DDL 与迁移逐枚同列、同定义，``ALERT_DISPOSAL_DEFAULTS`` 又是这八枚默认值的第三份镜像。

    三处任何一处漂了都会在这里红：产品读回的空串、开发库补出的空串、迁移补出的空串必须是同一个串。
    """
    migrated_specs = added_column_specs(LANDED_PATH.read_text(encoding="utf-8"))
    lazy_specs = [added_column_specs(ddl)[0] for ddl in alerts_module._ALERT_DISPOSAL_LAZY_DDLS]

    assert len(lazy_specs) == len(DISPOSAL_COLUMNS), lazy_specs
    assert [spec.column for spec in lazy_specs] == list(DISPOSAL_COLUMNS), lazy_specs
    assert [spec.column for spec in migrated_specs] == list(DISPOSAL_COLUMNS), migrated_specs
    assert all(spec.column_guarded for spec in lazy_specs), lazy_specs
    assert {spec.column: spec.definition for spec in lazy_specs} == {
        spec.column: spec.definition for spec in migrated_specs
    }
    assert ALERT_DISPOSAL_DEFAULTS == {spec.column: spec.default_literal for spec in migrated_specs}
