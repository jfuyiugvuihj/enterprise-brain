"""R183 -- pending_approvals.declared_lane 进台账：这一格从此可以绑，但本件不绑。

总控 15:5x 更正派工：app/storage/pending_approvals.py 同时在 be-r175 的写域里（那枚文件
今天 15:55 被 R175 改动过），两枚单同改一份文件并树必撞，所以写侧绑值转 R187。本件因此
只证到「列已在、绑它是合法的」，不证「写侧已经绑了」：

- 新增交付项 3：迁移执行后 pending_approvals 的列集合里确有 declared_lane 且缺省空串。
  离线可验，走 app.db.migrations 的 loader 加一枚桩 connection，不连真库。
- 判据 6：存量行落空串。83 枚这个数是总控在线上报的读数，本件不连库、不重复主张它
  为真；它在这里只是一个形状参数，所以 0 行／1 行／83 行三档都跑同一条路。
- 判据 7：那条 INSERT 与迁移自洽——列已在，禁令的性质从「不许绑」变成「绑它合法」，
  而 R172 那枚断言必须仍然绿（实测见交付报告，本件不改它）。
- 判据 8：默认值与仓库级唯一归一化通路 normalize_declared_lane 同源，DDL 里不长出
  第二份档位词表。
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from test_r183_184_migration_pair import (  # noqa: T401  共用同一份离线 DDL 模型
    LANE_TARGETS,
    NEW_VERSION,
    PENDING_LANE,
    added_column_specs,
    executable_statements,
    first_adding_spec,
    insert_columns,
    new_migration,
    replay_added_columns,
    rows_at,
    schema_through,
    statement_literal,
)

REPO = Path(__file__).resolve().parents[1]
PRE = "0011"
#: 总控简报第二节给的线上读数。本件不连库，所以它只当作「有存量行」这一档的样本数使用，
#: 不在这里主张它等于线上真值。
LIVE_ROWS_HINT = 83
TABLE = "pending_approvals"


def pre_columns() -> list[str]:
    return schema_through(PRE)["pending_approvals"]


def post_columns() -> list[str]:
    return schema_through(NEW_VERSION)["pending_approvals"]


def landed_spec():
    return first_adding_spec(*PENDING_LANE)


class _LedgerConnection:
    """只回答两类问句的挂起台账替身：表在不在（to_regclass）、列在不在（information_schema）。

    答案一律从 migrations 重放出来的列目录取，所以「这一枚列有没有真的进 0012」能改变
    本文件的判定：把迁移改窄，桩就照实回「没有这一列」。
    """

    def __init__(self, through: str):
        self.columns = schema_through(through)
        self.executed: list[str] = []
        self._next: object = None

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self.executed.append(text)
        if "to_regclass" in text:
            table = re.search(r"public\.(\w+)", text).group(1)
            self._next = {"table_name": table} if table in self.columns else None
        elif "information_schema" in text:
            present = "declared_lane" in self.columns.get("pending_approvals", [])
            self._next = {"column_name": "declared_lane"} if present else None
        else:
            raise AssertionError("本件只该问表与列两件事：" + text)
        return self

    def fetchone(self):
        return self._next


# ==================================================== 新增交付项 3：列已在、默认空串
def test_the_parking_ledger_gains_exactly_one_column_and_the_0008_shape_survives():
    """迁移前后只差 declared_lane，0008 建的十一枚列一枚不少。"""
    before, after = pre_columns(), post_columns()

    assert [name for name in after if name not in before] == ["declared_lane"]
    assert set(after) == set(before) | {"declared_lane"}
    assert {"session_id", "owner_user_id", "parked_steps", "status"} <= set(before), before
    assert landed_spec().version == NEW_VERSION


def test_the_column_comes_from_the_loader_not_from_a_hand_read_file():
    """离线可验的入口是 app.db.migrations 的 loader：盘上有、loader 不认等于没落。"""
    from app.db.migrations import MIGRATIONS

    versions = [item.version for item in MIGRATIONS]

    assert NEW_VERSION in versions and versions[-1] == NEW_VERSION
    spec = next(
        column
        for item in MIGRATIONS
        for column in added_column_specs(item.sql, item.version)
        if (column.table, column.column) == PENDING_LANE
    )
    assert spec.column_guarded and spec.table_guarded


def test_the_landed_column_is_guarded_not_null_text_with_a_constant_empty_default():
    """列的形状逐字对上判据：TEXT NOT NULL DEFAULT 空串，且 ADD COLUMN 带幂等守卫。"""
    spec = landed_spec()

    assert spec.data_type == "TEXT"
    assert spec.not_null is True
    assert spec.default_literal == ""
    assert spec.column_guarded is True


def test_the_migrated_catalog_answers_a_real_schema_probe_with_the_column():
    """真走一枚桩 connection 的列目录问句：0011 上没有，0012 之后有。

    这就是「离线可验」的那一环——问句形状取自产品代码里已有的 information_schema 探测，
    回答由 migrations 重放给出，不连真库、不跑 scripts/migrate.py。
    """
    before = _LedgerConnection(PRE)
    assert before.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'pending_approvals' AND column_name = 'declared_lane' LIMIT 1"
    ).fetchone() is None

    after = _LedgerConnection(NEW_VERSION)
    assert after.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'pending_approvals' AND column_name = 'declared_lane' LIMIT 1"
    ).fetchone() == {"column_name": "declared_lane"}


def test_the_store_gate_still_passes_on_the_migrated_ledger():
    """本件不许碰 _require_table 的判定，只证它在新列目录上照旧放行。"""
    from app.storage.pending_approvals import PendingApprovalStoreMissing, _require_table

    _require_table(_LedgerConnection(NEW_VERSION))
    with pytest.raises(PendingApprovalStoreMissing):
        _require_table(_LedgerConnection("0007"))


# ==================================================== 判据 6：存量行落空串
def ledger_rows(count: int, through: str = PRE) -> list[dict]:
    """存量行的可读数形状：列集合取当时台账，parked_steps 给真数组。

    共用模型 rows_at 只造字符串占位值，而 _record_from_row 会把字符串当 JSON 解析，
    所以要读回记录的用例必须自己把那一格换成产品代码认的形状。列**集合**仍由模型给出，
    占位值的差别不影响任何一条判据。
    """
    rows = []
    for index, row in enumerate(rows_at(TABLE, count, through=through)):
        filled = dict(row)
        filled["parked_steps"] = [f"step-{index}-a", f"step-{index}-b"]
        filled["status"] = "awaiting"
        filled["decided_at"] = None
        rows.append(filled)
    return rows

@pytest.mark.parametrize("count", [0, 1, LIVE_ROWS_HINT])
def test_existing_rows_land_on_the_empty_string_at_every_row_count(count):
    """0 行／1 行／83 行走的是同一条路：无警告、无跳过、新列取常量默认。

    带常量默认的 ADD COLUMN 由列定义给存量行填值， PostgreSQL 不需要也不可能有一条
    写数据的语句参与；一旦这一档要求别的步骤，回填就有了入口。
    """
    seeds = ledger_rows(count)

    landed, warnings, skipped = replay_added_columns(seeds, "pending_approvals")

    assert (warnings, skipped) == ([], [])
    assert len(landed) == count
    assert [row["declared_lane"] for row in landed] == [""] * count


def test_the_backfill_moves_no_other_column_and_leaves_the_gap_countable():
    """只动这一枚列，其余各格逐字节不动；且「没人声明过」这件事仍然数得出来。

    R172 那句「缺口照旧可数，不遮丑」落到存量上就是：83 行填完仍是 83 枚缺口，
    而不是被哪个默认档位悄悄吃掉。
    """
    seeds = ledger_rows(LIVE_ROWS_HINT)

    landed, _warnings, _skipped = replay_added_columns(seeds, "pending_approvals")

    assert sum(1 for row in landed if not row["declared_lane"]) == LIVE_ROWS_HINT
    for seed, row in zip(seeds, landed):
        assert {key: value for key, value in row.items() if key != "declared_lane"} == seed


def test_replaying_the_landed_file_a_second_time_skips_the_column_and_moves_no_row():
    """二次执行幂等：命中 IF NOT EXISTS 只发一条跳过，列与行都不动。"""
    once, first_warnings, first_skipped = replay_added_columns(
        ledger_rows(3), TABLE
    )
    twice, second_warnings, second_skipped = replay_added_columns(once, "pending_approvals")

    assert (first_warnings, first_skipped) == ([], [])
    assert second_skipped == ["pending_approvals.declared_lane already exists, skipped"]
    assert second_warnings == []
    assert twice == once


# ==================================================== 判据 6 的读数侧：改前改后逐字节相同
def _read_back(row: dict):
    from app.storage.pending_approvals import _record_from_row

    return _record_from_row(row)


def _shape(record) -> str:
    """把一条读回的记录折成可比较的字节形状（字段名加值，按 key 排序）。"""
    return json.dumps(dataclasses.asdict(record), ensure_ascii=False, sort_keys=True)


def test_a_row_that_cannot_answer_the_column_reads_byte_identical_to_one_answering_empty():
    """R172 口径在迁移后仍然成立：那一格读不到与读到空串，逐字节相同。

    迁移给存量行填的是空串，而旧形状的行根本没有这个键；两条路都必须落到同一个
    declared_lane 值，否则「改前改后同一形状」这句话就是假的。
    """
    seed = ledger_rows(1)[0]
    without_key = dict(seed)
    with_empty_key = dict(seed, declared_lane="")

    record_before = _read_back(without_key)
    record_after = _read_back(with_empty_key)

    assert record_before.declared_lane == "" == record_after.declared_lane
    assert _shape(record_before) == _shape(record_after)


def test_a_lane_value_in_the_column_still_reads_through():
    """上一枚断言不是因为这一格死了：有值时必须原样读出来。

    不然「读不到与读到空串相同」可以靠把字段整个忽略来蒙过。
    """
    row = dict(ledger_rows(1)[0], declared_lane="analysis")

    assert _read_back(row).declared_lane == "analysis"


def test_the_empty_string_is_a_real_value_and_null_is_not_the_default_shape():
    """列 NOT NULL，所以三态里根本没有 NULL 那一格：要么有名，要么名为「没有」。"""
    spec = landed_spec()
    row = dict(ledger_rows(1)[0], declared_lane=None)

    assert spec.default_literal == ""
    assert spec.not_null is True
    # 万一哪天真库回一枚 None，读侧仍落空串，不把它读成「声明过」。
    assert _read_back(row).declared_lane == ""


# ==================================================== 判据 7：列已在、绑它合法（不做到已绑）
def test_the_shipped_parking_writer_still_binds_nothing_the_ledger_lacks():
    """那条 INSERT 的九枚列在迁移前后都全在台账里——R172 那枚断言因此继续绿。

    本件没改写侧一个字：它今天绑的列本来就都在，加一列不会让它变红。
    """
    statement = statement_literal("app/storage/pending_approvals.py", "INSERT INTO pending_approvals")
    table, columns = insert_columns(statement)

    assert table == "pending_approvals"
    assert "declared_lane" not in columns, "本件不做写侧绑值，那半条腿转 R187"
    assert set(columns) <= set(pre_columns()), columns
    assert set(columns) <= set(post_columns()), columns
    assert len(columns) == len(set(columns)) == statement.count("%s"), statement


def test_binding_the_lane_column_is_now_legal_whereas_before_it_was_not():
    """判据 7 的新口径本体：同一枚 INSERT 多绑这一格，迁移前非法、迁移后合法。

    这就是「列已在、绑它是合法的」那句话的可执行形状。它也兼任反证 (b) 的引信：
    把 0012 改窄（只补 alerts.department），本枚立刻红。
    """
    statement = statement_literal("app/storage/pending_approvals.py", "INSERT INTO pending_approvals")
    _table, columns = insert_columns(statement)
    would_bind = set(columns) | {"declared_lane"}

    assert not would_bind <= set(pre_columns()), "迁移前这一枚列不在台账里"
    assert would_bind <= set(post_columns()), "0012 之后这一枚列必须在台账里"


def test_the_landed_file_writes_no_row_to_the_parking_ledger():
    """存量行的值只来自列定义：本件里没有一条会改动行内容的语句。"""
    assert executable_statements(new_migration().sql), "落盘的迁移不该是空文件"
    assert not re.search(r"\b(update|insert|delete|merge|truncate)\b",
                        " ".join(executable_statements(new_migration().sql)).lower())


# ==================================================== 判据 8：同源归一化，不长了第二份词表
def test_the_migration_default_is_the_same_string_the_only_normalizer_produces():
    """DDL 的默认值与 normalize_declared_lane 的空串出口是同一枚值。

    仓库级唯一通路在 app/agents/nodes.py，本件不许另起第二份归一化，所以这里只把
    「默认值 == 它给空输入的返回」钉住。
    """
    from app.agents.nodes import normalize_declared_lane

    assert normalize_declared_lane("") == ""
    assert normalize_declared_lane(None) == ""
    assert landed_spec().default_literal == normalize_declared_lane("")


def test_the_ddl_declares_no_second_lane_vocabulary():
    """档位词表只在 LANE_TIERS 一处：带约束的那几句里不许出现 CHECK／ENUM／值清单。

    值集一旦抄进约束，就有两份事实源可以互相漂移；未知拼写在 normalize 那里硬失败，
    本来就不该由库来静默兜住。

    检查范围只取**会建对象的语句**（ALTER／CREATE）。COMMENT ON 后面那段是给运维看的
    散文，它提到 qa / analysis / report 三个名字是解释这一格的含义，不构成任何强制，
    也就不是第二份事实源——把它一并禁掉只会让迁移看不懂自己加了什么。
    """
    from app.agents.nodes import LANE_TIERS

    enforcing = [
        statement
        for statement in executable_statements(new_migration().sql)
        if statement.split()[0].upper() in ("ALTER", "CREATE")
    ]
    assert enforcing, "本件至少要落地两枚 ALTER"
    body = " ".join(enforcing).upper()

    assert "CHECK" not in body
    assert "CREATE TYPE" not in body
    assert "ENUM" not in body
    assert " IN (" not in body
    for tier in LANE_TIERS:
        assert str(tier).upper() not in body


def test_the_comment_prose_points_at_the_one_normalizer_instead_of_restating_a_rule():
    """注释把读者送回唯一通路：它说「由 normalize_declared_lane 归一」，不自带判定。"""
    statements = executable_statements(new_migration().sql)
    lane_comments = [
        statement for statement in statements
        if statement.lower().startswith("comment on") and "declared_lane" in statement.lower()
    ]

    assert len(lane_comments) == 1, lane_comments
    assert "normalize_declared_lane" in lane_comments[0]
    assert "app/agents/nodes.py" in lane_comments[0]

def test_the_pinned_lane_values_survive_a_normalized_round_trip_into_the_column():
    """归一化之后写进去的值，读回来必须还是它：空串默认值不会吞掉真声明。"""
    from app.agents.nodes import normalize_declared_lane

    for tier in sorted(str(value) for value in LANE_TIERS_keys()):
        row = dict(ledger_rows(1)[0],
                   declared_lane=normalize_declared_lane(tier))
        assert _read_back(row).declared_lane == tier


def LANE_TIERS_keys():
    from app.agents.nodes import LANE_TIERS

    return LANE_TIERS.keys()