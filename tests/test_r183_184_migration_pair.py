"""R183 + R184 共用的那一枚模型：把 migrations 的 DDL 读成一份 schema，离线重放。

来历：跟进单 §89 四（本单判据首次成文）。线上库的 ``alerts`` 只有 0003 建表给出的六枚列、
``pending_approvals`` 只有 0008 给出的那十一枚，而两枚代码侧早已在读的东西没有对应的列：R176
 的行级归属（``alert_row_scope_sql``，生产分支缺列即 fail-closed）与 R172 的挂起档位。
0012 一次送两枚列，本文件钉的是「一次」与「同一笔」这两件事本身：

* 判据 9 —— 两枚列必须出自同一枚迁移文件。拆开就会留出一个部署中间态：一边看到「这枚列在、
  对面那张表还没有」，而 R176 那半是 fail-closed 的。所以这里读的不是「0012 里提到了两枚列」
  这种散文，而是「从 0001 一路重放到最新版，第一枚把这一列建出来的语句落在哪一版」——把 0012
  改窄删掉任何一枚，对应那列就变成「从来没有迁移建过它」，与另一枚所在版不相等，当场红。
* 判据 10 —— ``manifest.json`` 的数字必须等于**落盘字节**的 sha256。本仓库 ``core.autocrlf`` 为
  true，而 loader 取的是 ``read_text()`` 之后的文本：文件带 CRLF 时「字节 hash」与「清单 hash」
  会算成两个不同的数，所以 0012 按 LF 落盘，本文件钉「字节 == 文本 == 清单 == loader 登记」。
* 判据 2 的静态半边 —— 0012 里不许出现任何写数据的语句，也不许出现任何可拿来反推归属的来源。

本文件另外给两枚单提供共用的三件工具：``schema_through``（按版次重放的列清单）、
``added_column_specs``（一枚文件里加列语句的形状）、``replay_added_columns``（把加列落到存量行上，
按 PostgreSQL 的语义只认常量默认值）。全程离线：输入只有 ``migrations/*.sql`` 的文本，不连库、
不起容器、不跑 ``scripts/migrate.py``。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import Path

import pytest

from app.db.migrations import MIGRATIONS, discover_migrations

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"
MANIFEST_PATH = MIGRATIONS_DIR / "manifest.json"

NEW_VERSION = "0012"
NEW_FILENAME = "0012_alert_and_pending_approval_attribution_columns.sql"
NEW_PATH = MIGRATIONS_DIR / NEW_FILENAME

#: 🔴 目录尾号引信（与 tests/test_document_catalog_sync.py、tests/test_r46_activity_signals.py、
#: tests/test_r120_clean_install_first_boot.py、tests/test_r190_status_failed_domain.py 同族）。
#: 本单落 0012 时尾号就是 0012；R190 排了 0013（放开挂起台账 status 的取值域）之后尾号归它，本件
#: 连名带断言一起改口 —— 这是把钉子收紧一版，不是放宽。谁排下一号必须回到这里改这一格。
CATALOG_TAIL_VERSION = "0013"

#: 本单送的两枚列：R184 管告警台账的行级归属，R183 管挂起轮声明的档位。
ALERTS_DEPARTMENT = ("alerts", "department")
PENDING_LANE = ("pending_approvals", "declared_lane")
LANE_TARGETS = (ALERTS_DEPARTMENT, PENDING_LANE)

#: 建表体内不是列定义的行首词（与 tests/test_pending_approvals_migration.py 同一判据）。
_NON_COLUMN_WORDS = ("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "EXCLUDE", "LIKE")
#: 会改动行内容的首词，以及需要两词才认得出的那两枚。对这两张表出现任何一种，
#: 都等于「迁移在写数据」——判据 2 拦的就是它。
_ROW_WRITING_FIRST_WORDS = frozenset(
    {
        "update", "insert", "delete", "merge", "truncate", "copy", "do", "call",
        "set", "reset", "vacuum", "analyze", "refresh", "reindex", "cluster",
    }
)
_ROW_WRITING_TWO_WORDS = frozenset({"create trigger", "create rule", "create policy"})
#: 本单允许出现在 0012 里的语句种类。
_LANDED_HEADS = frozenset({"alter table", "comment on"})

_COMMENT_LINE = re.compile(r"^[ \t]*--.*$", re.MULTILINE)
_HEAD = re.compile(r"^\s*(?P<first>\w+)(?:\s+(?P<second>\w+))?", re.IGNORECASE)
_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+(?P<table_guard>IF\s+EXISTS\s+)?(?P<table>\w+)\s+"
    r"ADD\s+COLUMN\s+(?P<column_guard>IF\s+NOT\s+EXISTS\s+)?(?P<column>\w+)\s+"
    r"(?P<definition>[^;]+)",
    re.IGNORECASE | re.DOTALL,
)
#: 建表语句整体是一枚语句，``.+)`` 贪到行尾最后那枚右括号即表定义本身。
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<table>\w+)\s*\((?P<body>.+)\)\s*\Z",
    re.IGNORECASE | re.DOTALL,
)
_LEDGER_WORD = re.compile(r"\b(?:alerts|pending_approvals)\b", re.IGNORECASE)


def executable_statements(sql: str) -> list[str]:
    """只留能执行的语句：注释是散文，不是 SQL（与 tests/test_document_catalog_sync.py 同一打法）。"""
    body = _COMMENT_LINE.sub("", sql)
    return [" ".join(chunk.split()) for chunk in body.split(";") if chunk.strip()]


def statement_head(statement: str) -> str:
    """语句种类，取前两个词：``alter table`` / ``comment on`` / ``create trigger``。"""
    match = _HEAD.match(statement)
    if match is None:
        return ""
    words = [match.group("first").lower()]
    if match.group("second"):
        words.append(match.group("second").lower())
    return " ".join(words[:2])


def writes_rows(statement: str) -> bool:
    head = statement_head(statement)
    first = head.split()[0] if head else ""
    return first in _ROW_WRITING_FIRST_WORDS or head in _ROW_WRITING_TWO_WORDS


@dataclass(frozen=True)
class AddedColumn:
    """一枚 ``ADD COLUMN`` 的可查形状。"""

    version: str
    table: str
    column: str
    definition: str
    table_guarded: bool
    column_guarded: bool

    @property
    def target(self) -> tuple[str, str]:
        return (self.table, self.column)

    @property
    def data_type(self) -> str:
        return self.definition.split()[0].upper()

    @property
    def not_null(self) -> bool:
        return re.search(r"\bNOT\s+NULL\b", self.definition, re.IGNORECASE) is not None

    @property
    def default_literal(self) -> str | None:
        """常量字符串默认值的**内容**；NOW()/nextval/子查询这类非常量默认一律回 ``None``。

        只认引号包起来的字面量是刻意的：只有它能让存量行在「不发任何写数据语句」的前提下读回
        同一个值。``DEFAULT now()`` 那种每行都不一样的东西在这里当「没有默认值」处理，由用例把
        它判成不合格，而不是悄悄替它想一个值。
        """
        match = re.search(r"DEFAULT\s+('(?:[^']|'')*')", self.definition, re.IGNORECASE)
        return None if match is None else match.group(1)[1:-1].replace("''", "'")


def added_column_specs(sql: str, version: str = "") -> list[AddedColumn]:
    columns = []
    for statement in executable_statements(sql):
        for match in _ADD_COLUMN.finditer(statement):
            columns.append(
                AddedColumn(
                    version=version,
                    table=match.group("table").lower(),
                    column=match.group("column").lower(),
                    definition=" ".join(match.group("definition").split()),
                    table_guarded=bool(match.group("table_guard")),
                    column_guarded=bool(match.group("column_guard")),
                )
            )
    return columns


def split_top_level(body: str) -> list[str]:
    """按**括号深度为 0 的逗号**切列定义。

    必须自己切：``executable_statements`` 把空白折平了，行结构拿不到，而
    ``DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text`` 与
    ``CHECK (jsonb_typeof(parked_steps) = 'array')`` 里都有括号——按逗号裸切会把一列切成两截。
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def created_columns(sql: str) -> dict[str, list[str]]:
    """``CREATE TABLE`` 给出的初始列（按书写次序），表定义之外的 CONSTRAINT 等条目不计为列。"""
    tables: dict[str, list[str]] = {}
    for statement in executable_statements(sql):
        match = _CREATE_TABLE.match(statement)
        if match is None:
            continue
        names = [
            part.split()[0].lower()
            for part in split_top_level(match.group("body"))
            if part.split()[0].upper() not in _NON_COLUMN_WORDS
        ]
        tables.setdefault(match.group("table").lower(), []).extend(names)
    return tables


def ordered(through: str = NEW_VERSION):
    return [item for item in MIGRATIONS if item.version <= through]


def schema_through(through: str) -> dict[str, list[str]]:
    """把 0001..``through`` 的 DDL 重放成表 -> 列名清单。

    这是对 PG DDL 语义的**最小**模拟（建表给初始列、加列往后缀），不是第二份 schema 事实源：
    输入只有 ``migrations/*.sql`` 的文本，输出只用于和本单判据对照，产品代码不读它。
    """
    schema: dict[str, list[str]] = {}
    for item in ordered(through):
        for table, names in created_columns(item.sql).items():
            columns = schema.setdefault(table, [])
            columns.extend(name for name in names if name not in columns)
        for spec in added_column_specs(item.sql, item.version):
            columns = schema.setdefault(spec.table, [])
            if spec.column not in columns:
                columns.append(spec.column)
    return schema


def first_adding_spec(table: str, column: str) -> AddedColumn | None:
    """第一枚把 ``table.column`` 建出来的加列语句——找不到就是「从来没有迁移建过它」。"""
    for item in ordered():
        for spec in added_column_specs(item.sql, item.version):
            if spec.table == table and spec.column == column:
                return spec
    return None


def rows_at(table: str, count: int, through: str = "0011") -> list[dict]:
    """造 ``count`` 枚「这一版之前就已存在」的行：列集合恰是当时台账的列集合。"""
    columns = schema_through(through).get(table, [])
    return [
        {column: f"{table}-{index}-{column}" for column in columns}
        for index in range(count)
    ]


def replay_added_columns(
    rows: list[dict], table: str, through: str = NEW_VERSION, since: str = "0011"
) -> tuple[list[dict], list[str], list[str]]:
    """把 ``since`` 之后各版给这张表加的列落到存量行上，返回 ``(行, 警告, 跳过)``。

    走 PostgreSQL 自己的语义：带常量默认值的 ``ADD COLUMN`` 由列定义给存量行填值，不需要也不
    允许任何一条写数据的语句；``IF NOT EXISTS`` 命中已存在的列时只发一条 NOTICE（记进
    ``skipped``），不改列、不改行。列是 NOT NULL 而拿不到常量默认值时进 ``warnings``——那正是
    判据 2 要拦的形状：要么它建不出来，要么就得有人回填。
    """
    warnings: list[str] = []
    skipped: list[str] = []
    result = [dict(row) for row in rows]
    #: “这张表现在有哪些列”取自**行自己带的键**与那一版的列清单的并集：第二次重放时这一枚列已在行上，
    #: 才会真的走到 IF NOT EXISTS 那条跳过支路（PG 在那里的判定对象就是目标表的列）。
    existing = set(schema_through(since).get(table, [])) | {key for row in rows for key in row}
    for item in ordered(through):
        if item.version <= since:
            continue
        for spec in added_column_specs(item.sql, item.version):
            if spec.table != table:
                continue
            if spec.column in existing:
                if spec.column_guarded:
                    skipped.append(f"{spec.table}.{spec.column} already exists, skipped")
                    continue
                warnings.append(f"{spec.table}.{spec.column} added twice without a guard")
                continue
            existing.add(spec.column)
            if spec.default_literal is None:
                if spec.not_null:
                    warnings.append(
                        f"{spec.table}.{spec.column} is NOT NULL with no constant default: "
                        "a populated table needs a data-writing statement to fill it"
                    )
                for row in result:
                    row[spec.column] = None
                continue
            for row in result:
                row[spec.column] = spec.default_literal
    return result, warnings, skipped


def statement_literal(module: str, needle: str) -> str:
    """从产品源码里取出装着某条 SQL 的那枚字符串字面量（相邻字面量在 parse 期已折成一枚）。"""
    tree = ast.parse((REPO / module).read_text(encoding="utf-8"))
    found = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and needle in node.value
    ]
    if len(found) != 1:
        raise AssertionError(f"{module} 里含 {needle!r} 的字面量应当恰有一枚，实取 {len(found)} 枚")
    return found[0]


def insert_columns(statement: str) -> tuple[str, list[str]]:
    """``INSERT INTO t (a, b) VALUES (...)`` -> ``("t", ["a", "b"])``。"""
    match = re.search(
        r"INSERT\s+INTO\s+(?P<table>\w+)\s*\((?P<columns>[^)]*)\)", statement, re.IGNORECASE
    )
    assert match is not None, "不是预期的 INSERT 形状：" + statement
    names = [name.strip().lower() for name in match.group("columns").split(",") if name.strip()]
    return match.group("table").lower(), names


def new_migration():
    return next(item for item in MIGRATIONS if item.version == NEW_VERSION)


@pytest.fixture(scope="module")
def landed_sql() -> str:
    return new_migration().sql


# ---------------------------------------------------------------- 判据 9：必须同一笔
def test_the_catalog_gains_exactly_one_version_and_the_loader_accepts_it():
    versions = [item.version for item in MIGRATIONS]
    on_disk = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))

    assert versions == [f"{number:04d}" for number in range(1, len(versions) + 1)], versions
    assert NEW_VERSION in versions, "本单的两枚列必须由已登记的 0012 送出"
    assert versions[-1] == CATALOG_TAIL_VERSION, (
        "目录尾号引信（来历见 CATALOG_TAIL_VERSION）：要加第三枚列请回到 0012 里加"
    )
    assert [version for version in versions if version > NEW_VERSION] == [CATALOG_TAIL_VERSION], (
        "0012 之后只许站着被指名的那一枚前滚迁移，多一枚就得回到这里指名：" + str(versions)
    )
    assert NEW_FILENAME in on_disk
    assert discover_migrations() == MIGRATIONS, "清单校验不过的目录不该被 loader 认下来"


def test_both_columns_ship_in_one_version_and_neither_can_be_split_off(landed_sql):
    """判据 9 的牙齿，也是反证 (b) 的钉子。

    读的是「第一枚把这一列建出来的语句落在哪一版」，不是「0012 的文本里提没提到这一列」。把
    0012 改窄删掉 ``declared_lane``（或 ``department``），对应那一列就退成 ``None``——与另一列所在
    版不相等，这一格当场红；两枚列都还在时，两个版本号必须同为 0012。
    """
    origins = {target: first_adding_spec(*target) for target in LANE_TARGETS}

    for target, spec in origins.items():
        assert spec is not None, (
            f"{target[0]}.{target[1]} 没有任何迁移建过它——两枚列必须同一笔送出（§89 四 判据 9）"
        )
        assert spec.version == NEW_VERSION, (
            f"{target[0]}.{target[1]} 出自 {spec.version}，本单的两枚列必须同在一版"
        )
    specs = added_column_specs(landed_sql, NEW_VERSION)
    assert {(spec.table, spec.column) for spec in specs} == set(LANE_TARGETS), (
        "0012 里的加列语句必须恰是本单这两枚，多一枚少一枚都算走偏："
        + str(sorted((spec.table, spec.column) for spec in specs))
    )


def test_neither_column_existed_anywhere_before_this_version():
    """静态复验简报第二节的前两格（仓库侧）：跑到 0011 的库里就是没有这两枚列。

    这一格不查 ``schema_migrations``——那是线上库的事实，总控已取证，我不重复主张。它只看仓库里
    的 DDL：0001..0011 没有任何语句给这两张表加过列，``alerts`` 的全部列就是 0003 建表那六枚。
    """
    before = schema_through("0011")

    assert before["alerts"] == ["id", "rule_id", "message", "ai_analysis", "read", "created_at"], (
        "0003 之外还有别的迁移在动 alerts 的列清单，那本单「从来没有这支迁移」的前提就不成立了"
    )
    assert "department" not in before["alerts"]
    assert "declared_lane" not in before["pending_approvals"]
    assert "session_id" in before["pending_approvals"], "对照：0008 那批列确实在，重放器没读空"

    after = schema_through(NEW_VERSION)
    assert after["alerts"] == before["alerts"] + ["department"]
    assert after["pending_approvals"] == before["pending_approvals"] + ["declared_lane"]


def test_the_landed_file_adds_the_two_columns_and_does_nothing_else(landed_sql):
    """0012 的可执行语句只许是两枚加列加两枚列注释：不建表、不删东西、不顺手改别的列。"""
    statements = executable_statements(landed_sql)

    assert len(statements) == 4, statements
    assert {statement_head(statement) for statement in statements} == _LANDED_HEADS, statements
    assert not [statement for statement in statements if statement.upper().startswith("CREATE TABLE")]
    assert not [statement for statement in statements if "DROP" in statement.upper()]
    assert {spec.table for spec in added_column_specs(landed_sql)} == {
        "alerts",
        "pending_approvals",
    }


# ---------------------------------------------------------------- 判据 2 的静态半边
def test_0012_writes_no_row_data_and_names_no_inference_source(landed_sql):
    """判据 2：文件里根本没有一条写数据的语句，所以「猜一次归属」这条路在物理上不存在。

    按**语句种类**收口而不是按关键词出现与否：注释里会出现 ``rule_id``（正是在解释为什么不猜），
    可执行文本里不许出现它，也不许出现任何函数式取值。
    """
    statements = executable_statements(landed_sql)
    joined = " ".join(statements).lower()

    assert not [statement for statement in statements if writes_rows(statement)], statements
    for forbidden in ("update ", "insert into", "delete from", "merge ", "truncate ", "select "):
        assert forbidden not in joined, f"0012 里出现了 {forbidden!r}：回填推断就是从这一句开始的"
    for inference_source in (
        "rule_id", "datasets", "dataset_", "document_versions", "string_to_array", "substring",
        "coalesce", "case when",
    ):
        assert inference_source not in joined, (
            f"0012 从 {inference_source!r} 反推归属——猜一次就是往客户库里写一条假归属"
        )


def test_no_migration_in_the_catalog_backfills_either_of_these_columns():
    """把判据 2 从「这一支文件」扩到「整册目录」：0001..0012 没有任何语句动过这两张表的行。

    这一格防的是后来人往**别的**已发布版本里塞回填（那样清单的号会跟着变，而读侧不认），也顺手
    钉住本单的交付里没有第二支迁移在改这两张表。
    """
    offenders = []
    for item in ordered():
        for statement in executable_statements(item.sql):
            if _LEDGER_WORD.search(statement) is None:
                continue
            if writes_rows(statement):
                offenders.append(f"{item.version}: {statement[:70]}")
            head = statement_head(statement)
            if head == "alter table" and "add column" not in statement.lower():
                offenders.append(f"{item.version}: {statement[:70]}")

    assert offenders == [], offenders


# ---------------------------------------------------------------- 判据 1/6 的列形状
def test_both_columns_are_guarded_not_null_text_with_a_constant_empty_default(landed_sql):
    """判据 1（幂等）与判据 6（存量行落空串）在 DDL 这一侧的同一份凭据。"""
    specs = {(spec.table, spec.column): spec for spec in added_column_specs(landed_sql, NEW_VERSION)}

    assert set(specs) == set(LANE_TARGETS)
    for target, spec in specs.items():
        assert spec.column_guarded, f"{target} 没有 IF NOT EXISTS，重跑不是 no-op 而是报错"
        assert spec.table_guarded, f"{target} 的表名没加 IF EXISTS，缺表的库上重跑会中断"
        assert spec.data_type == "TEXT", f"{target} 的类型不是 TEXT：{spec.definition}"
        assert spec.not_null, f"{target} 少了 NOT NULL：读侧就要多判一种 NULL 形状"
        assert spec.default_literal == "", (
            f"{target} 的常量默认值必须是空串，实取 {spec.default_literal!r}"
        )


def test_replaying_the_landed_file_twice_moves_no_column_and_no_row(landed_sql):
    """幂等的可执行定义：第二次重放既不改列清单、也不改任何一行的读数。

    第一次执行零警告零跳过；第二次那一枚列必须走 ``IF NOT EXISTS`` 那条跳过支路——PG 在那里只发
    一条 NOTICE，不动列也不动行。这条断言读的是「有跳过、无警告」，不是「什么都没发生」：后者
    会把「根本没重放」也判成绿。
    """
    rows = rows_at("alerts", 3)
    once, first_warnings, first_skips = replay_added_columns(rows, "alerts")
    twice, second_warnings, second_skips = replay_added_columns(once, "alerts")
    columns_once = schema_through(NEW_VERSION)["alerts"]

    assert first_warnings == [], "首次执行就有警告路径：" + str(first_warnings)
    assert first_skips == [], "首次执行不该有任何「已存在所以跳过」的分支：" + str(first_skips)
    assert second_warnings == []
    assert len(second_skips) == len(first_skips) + 1, (
        "重跑时这一枚列必须被 IF NOT EXISTS 挡下来：" + str(second_skips)
    )
    assert all(row["department"] == "" for row in once), once
    assert set(once[0]) == set(columns_once)
    assert twice == once, "重跑改动了行读数：这支迁移不幂等"


def test_a_zero_row_ledger_takes_the_same_path_as_a_populated_one():
    """判据 1 的字面要求：0 行存量执行完不产生任何警告路径。

    0 行与有行走的是同一份列定义。这一格把「只因为有行才安全」那条路堵掉：哪天有人把默认值改成
    非常量、或把 NOT NULL 摘掉，有行那格会先红，而空表那格可能一直绿着骗过部署。
    """
    empty, warnings, skips = replay_added_columns([], "alerts")
    populated, populated_warnings, _ = replay_added_columns(rows_at("alerts", 5), "alerts")

    assert empty == [] and warnings == [] and skips == []
    assert populated_warnings == []
    assert [row["department"] for row in populated] == [""] * 5


# ---------------------------------------------------------------- 判据 10：字节与号
def test_the_manifest_digest_is_the_sha256_of_the_landed_bytes_not_of_a_string():
    """清单数字 == **归一后**盘上字节的 sha256 == loader 文本的 sha256 == loader 登记的校验和。

    原口径（R183/R184 判据 10）另有一格 ``assert b"\r\n" not in raw``，也就是"0012 必须按 LF
    落盘"。🔴 那一格是**机器依赖**而不是不变量，本单实测坐实：仓库 ``core.autocrlf`` 为 true，
    仓库里又没有 ``.gitattributes`` 给 ``migrations/*.sql`` 定行尾 ⇒ 任何一次全新 worktree/clone
    检出都会把 0012 变成 CRLF，于是"盘上字节 == manifest 数字"在兄弟树里当场红（R187 的施工方就
    在兄弟树撞着它并具名申报）；主树看不出来，只因为主树那份是施工时按 LF 直接写下去的、没经过
    一次检出。把行尾习惯钉进测试，等于把"这台机器怎么检出的"当成产品性质。

    真不变量是这条链，而且它逐字节判、不许退化成比长度：``read_text()`` 的通用换行归一（loader
    就是这么算数字的）== 把盘上字节按 ``CRLF -> LF`` 归一 == manifest 登记的数字 == loader 会写进
    ``schema_migrations`` 的那枚。仍然守住的三枚真性质：``\n`` 之外不许有裸 ``\r``（裸 CR 会被
    归一化吃掉而改变行结构）、不许带 BOM、末尾恰好一个换行；再加两枚正向对照：改一个字节数字就得
    变，以及归一前后的可执行语句必须逐枚相同——后者才是"CRLF 对 SQL 语义无害、所以可重跑这件事与
    检出方式无关"这句主张的可查形状。
    🔴 本件不改 0012 一个字节，也不为"迁就"检出把它转成 CRLF：已发布迁移的字节就是它的身份。
    """
    raw = NEW_PATH.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    text = NEW_PATH.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    # 归一化只许吃掉 CRLF 里的那一枚 \r：两种字节数之差恰好等于 CRLF 枚数，才算"比的是同一份内容"。
    assert len(raw) - len(normalized) == raw.count(b"\r\n"), {
        "raw": len(raw),
        "normalized": len(normalized),
        "crlf": raw.count(b"\r\n"),
    }
    assert raw.count(b"\r") == raw.count(b"\r\n"), "出现裸 CR（``\\n`` 之外的单枚 ``\\r``）：归一化会把它吃掉而改变行结构"
    assert not raw.startswith(b"\xef\xbb\xbf"), "带 BOM 会让首行注释多出看不见的字符"
    assert normalized.endswith(b"\n") and not normalized.endswith(b"\n\n"), "文件末尾恰好一个换行"
    assert executable_statements(raw.decode("utf-8")) == executable_statements(text), (
        "行尾差异改动了可执行语句：这支迁移的语义开始依赖检出方式"
    )

    from_bytes = sha256(normalized).hexdigest()
    from_text = sha256(text.encode("utf-8")).hexdigest()
    registered = next(item for item in MIGRATIONS if item.version == NEW_VERSION).checksum

    assert from_bytes == from_text == manifest[NEW_FILENAME] == registered, {
        "bytes": from_bytes,
        "text": from_text,
        "manifest": manifest[NEW_FILENAME],
        "loader": registered,
    }
    assert sha256(normalized + b" ").hexdigest() != registered, (
        "正向对照失效：多一枚空格都不改数字，说明这格退化成了比长度"
    )


def test_the_manifest_still_maps_one_entry_per_sql_file():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert sorted(manifest) == sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
    assert len(manifest) == len(MIGRATIONS)
    assert NEW_FILENAME in manifest


# ---------------------------------------------------------------- 不建第二份事实源
def test_the_landed_file_declares_no_constraint_and_no_lane_vocabulary(landed_sql):
    """两枚列都不带 CHECK，也不把档位枚举抄进 DDL。

    档位的闭集归 ``app/agents/nodes.py`` 的 ``LANE_TIERS`` / ``normalize_declared_lane``，部门的
    写法归 ``alerts.py`` 的 ``ALERT_DEPARTMENT_SEPARATOR``。在 DDL 里再抄一份就是第二份事实源，
    而它一定会在某一天和第一份分家——这一格不许后来人以「加个 CHECK 更保险」的名义塞回来。
    """
    joined = " ".join(executable_statements(landed_sql)).lower()

    assert "check" not in joined and "constraint" not in joined, joined
    for lane in ("qa", "analysis", "report"):
        assert f"'{lane}'" not in joined, f"档位 {lane} 被抄进了 DDL：闭集的第二份事实源"
    for spec in added_column_specs(landed_sql):
        assert "default" in spec.definition.lower(), spec.target
        assert spec.default_literal == "", spec.target
