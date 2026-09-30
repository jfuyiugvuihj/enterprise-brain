# -*- coding: utf-8 -*-
r"""R523 判据①④ —— 0018 给 ``model_calls`` 加 cached 列，两条装机路径都不停，摘要三处同字。

派工词点名的前例是 R90b「迁移 0010 首装必停」，所以本件把**首装**与**既有库**两条路分开跑，
一条都不许只证一半：

* 首装：空库（``schema_migrations`` 一枚都没有）从 0001 一路重放到 0018，``model_calls``
  最后带着 cached 这一列；
* 既有库：账本已经打到 0017，``migration_plan`` 只交回 0018 这一笔，跑完即尾号。

在册夹具一律复用同族件，本件不自建第二套：DDL 重放用 ``tests/test_r183_184_migration_pair.py``
的 ``schema_through`` / ``added_column_specs`` / ``replay_added_columns`` / ``rows_at``，跑迁移器用
``tests/test_r120_clean_install_first_boot.py`` 的 ``FreshSession``，目录尾号只从
``tests/test_r349_catalog_tail_ledger.py`` 那一枚账本 import（第二份手抄账由那件自己抓红）。

全程离线：不连库、不起服务、不动容器、不打模型。输入只有 ``migrations/*.sql`` 的文本。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.db import migrations as mig
from test_r120_clean_install_first_boot import COMPOSE_DEFAULT_DATABASE, FreshSession
from test_r183_184_migration_pair import (
    added_column_specs,
    executable_statements,
    replay_added_columns,
    rows_at,
    schema_through,
)

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"

#: 本单的主题版。按 r349 账本改口流程第 4 步，这一枚说的是「本件重放到哪一版」，
#: 不跟着目录尾号一起改口。
NEW_VERSION = "0018"
NEW_NAME = "prompt_cache_tokens"
NEW_FILENAME = f"{NEW_VERSION}_{NEW_NAME}.sql"
NEW_PATH = MIGRATIONS_DIR / NEW_FILENAME

TABLE = "model_calls"
COLUMN = "cached_tokens"
#: 0002 建出 model_calls 的那一版，也就是既有库路径的起点。
BEFORE_VERSION = "0017"


@pytest.fixture
def profile_declared(monkeypatch):
    """迁移器走到 0010 会要那一对 embedding 声明，这里给的是量具值，不是新的产品事实。

    0018 自己不读任何 GUC —— 那正是它和 R90b 那一族的区别 —— 所以本件只要让**前面的** 0010
    过得去，才能把「首装一路走到 0018」这半句跑成真句而不是嘴上句。
    """
    monkeypatch.setenv("EMBEDDING_MODEL", "r523-offline-model")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "512")


def _ledger(through: str) -> dict[str, str]:
    """已经记进账的那些版次：version -> checksum。"""
    return {item.version: item.checksum for item in mig.MIGRATIONS if item.version <= through}


# ------------------------------------------------------------------- 判据 ①：这一版只加这一列


def test_0018_adds_exactly_one_nullable_column_to_model_calls():
    """加列语句恰一枚，打在 model_calls.cached_tokens 上，表与列都带 IF EXISTS 守卫。"""
    sql = NEW_PATH.read_text(encoding="utf-8")
    specs = added_column_specs(sql, NEW_VERSION)

    assert [(spec.table, spec.column) for spec in specs] == [(TABLE, COLUMN)], specs
    spec = specs[0]
    assert spec.table_guarded, "ALTER TABLE 不带 IF EXISTS，没建过这张表的库会当场停"
    assert spec.column_guarded, "ADD COLUMN 不带 IF EXISTS，重跑会撞 already exists"
    assert spec.data_type == "INTEGER", spec.definition
    assert not spec.not_null, "老行没这个数是事实，NOT NULL 会把它逼成猜测"
    assert spec.default_literal is None, "DEFAULT 会给全部存量行凭空造出一枚读数"


def test_0018_writes_no_data_and_builds_no_index():
    """除了那一枚 ALTER 与那条 COMMENT，本文件不许有第二条语句，更不许有写数据的形状。"""
    statements = executable_statements(NEW_PATH.read_text(encoding="utf-8"))

    kinds = [statement.split()[0].upper() for statement in statements]
    assert kinds == ["ALTER", "COMMENT"], kinds
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "CREATE INDEX"):
        assert not [statement for statement in statements if forbidden in statement], (
            f"本文件不该出现 {forbidden!r}：回填与索引都不在这一单"
        )


def test_the_column_is_declared_in_the_trace_schema():
    """列名同源的两处都点名它：迁移原文重放出来的列集，与 app/trace/schema.py 的声明。"""
    from app.trace.schema import TRACE_TABLE_COLUMNS

    assert TRACE_TABLE_COLUMNS[TABLE][-1] == COLUMN, TRACE_TABLE_COLUMNS[TABLE]
    assert COLUMN in schema_through(NEW_VERSION)[TABLE]


# ------------------------------------------------------------------- 判据 ① 前半：首装那一路


def test_a_first_install_replays_every_version_and_ends_up_with_the_column():
    """空库重放全量：model_calls 由 0002 建出，cached 这一列由 0018 后缀上去。"""
    created = schema_through(BEFORE_VERSION)[TABLE]
    final = schema_through(NEW_VERSION)[TABLE]

    assert COLUMN not in created, "0002 里就有了，本文件就不是『补上承载面』那一格"
    assert final[-1] == COLUMN, f"重放完的列序末位是 {final[-1]}，不是加列后缀的形状"
    assert set(final) - set(created) == {COLUMN}


def test_a_first_install_walks_past_0018_without_stopping(profile_declared):
    """R90b 那一族的判据形状：首装必须一路走到尾号，并把每一版记进账。"""
    session = FreshSession(database=COMPOSE_DEFAULT_DATABASE, ledger={})

    applied = mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert [item.version for item in applied] == [item.version for item in mig.MIGRATIONS]
    assert NEW_VERSION in session.applied, session.applied
    assert session.ledger[NEW_VERSION] == _ledger(NEW_VERSION)[NEW_VERSION]


# ------------------------------------------------------------------- 判据 ① 后半：既有库那一路


def test_a_database_at_0017_has_0018_as_its_only_pending_step():
    """既有库（账本打到 0017）：pending 恰一枚，就是 0018，不带别人。"""
    pending = mig.migration_plan(_ledger(BEFORE_VERSION))

    assert [item.version for item in pending] == [NEW_VERSION], [item.version for item in pending]
    assert pending[0].name == NEW_NAME


def test_the_upgrade_applies_the_column_and_records_it(profile_declared):
    """既有库跑迁移器：只执行 0018 那一笔，账上多出尾号那一行，摘要与登记同字。"""
    session = FreshSession(database=COMPOSE_DEFAULT_DATABASE, ledger=_ledger(BEFORE_VERSION))

    applied = mig.apply_migrations(session, COMPOSE_DEFAULT_DATABASE)

    assert [item.version for item in applied] == [NEW_VERSION]
    assert session.applied == [NEW_VERSION]
    assert sorted(session.ledger) == [item.version for item in mig.MIGRATIONS]
    assert session.ledger[NEW_VERSION] == next(
        item.checksum for item in mig.MIGRATIONS if item.version == NEW_VERSION
    )


def test_old_rows_gain_the_column_as_null_and_a_re_run_changes_nothing():
    """存量行加列后读回 NULL；第二遍走的是 IF NOT EXISTS 那条跳过支路，不改列也不改行。"""
    old_rows = rows_at(TABLE, 3, through=BEFORE_VERSION)

    filled, warnings, skipped = replay_added_columns(
        old_rows, TABLE, through=NEW_VERSION, since=BEFORE_VERSION
    )

    assert warnings == [], f"这条加列在存量表上建不出来：{warnings}"
    assert skipped == []
    assert all(row[COLUMN] is None for row in filled), "没报数就是没报数，不许由迁移补一个值"

    again, warnings_again, skipped_again = replay_added_columns(
        filled, TABLE, through=NEW_VERSION, since=BEFORE_VERSION
    )
    assert warnings_again == []
    assert skipped_again == [f"{TABLE}.{COLUMN} already exists, skipped"], skipped_again
    assert all(row[COLUMN] is None for row in again), "重跑把 NULL 改成了别的读数"


# ------------------------------------------------------------------- 判据 ④：摘要三处同字


def test_the_manifest_digest_is_the_text_digest_the_loader_uses():
    """摘要判的是**文本**：``manifest.json`` 那一行 == ``read_text()`` 的 sha256 == loader 登记值。

    真源口径见 ``app/db/migrations.py:176-181`` —— loader 取的是 ``path.read_text(encoding="utf-8")``
    之后的文本再算 sha256，而 ``read_text`` 做通用换行归一。所以「字节 == 文本」那种判法会把
    **检出形态**当成产品判据：这台机 ``core.autocrlf=true`` 且没有 ``.gitattributes``，同一枚文件
    在谁的树上落成 CRLF 都会让它红，而产品行为一个字没变（总控裁定 2 的原话：真隐患）。
    今天判的是：字节归一到 LF 之后必须与文本同字（即只许 LF 或整枚 CRLF 两种形，不许混排），
    并且带 BOM 不许。
    """
    manifest = json.loads((MIGRATIONS_DIR / "manifest.json").read_text(encoding="utf-8"))
    raw_bytes = NEW_PATH.read_bytes()
    text = NEW_PATH.read_text(encoding="utf-8")
    registered = next(item for item in mig.MIGRATIONS if item.version == NEW_VERSION)

    digest_from_text = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "生成件不带 BOM，盘上那份也不许有"
    assert raw_bytes.replace(b"\r\n", b"\n") == text.encode("utf-8"), (
        "盘上那枚 0018 的行尾不是「全 LF」或「全 CRLF」两种形之一：混排会让摘要随人漂移"
    )
    assert manifest[NEW_FILENAME] == digest_from_text == registered.checksum
    assert mig.discover_migrations() == mig.MIGRATIONS, "清单校验不过的目录不该被 loader 认下来"


def test_the_digest_survives_both_lf_and_crlf_landings(tmp_path):
    """刀（总控裁定 2 点名要补的那把）：同一份内容分别落成 LF 与 CRLF，摘要必须仍然相等。

    正控在最后一行：把同一份 CRLF 字节直接 sha256，那个数**不等于**清单摘要 —— 谁想把这枚钉
    改回「字节 == 清单」，就会在这一格看见自己判的其实是检出形态。全程只写 ``tmp_path``。
    """
    import shutil

    text = NEW_PATH.read_text(encoding="utf-8")
    digest_from_text = hashlib.sha256(text.encode("utf-8")).hexdigest()
    registered = next(item for item in mig.MIGRATIONS if item.version == NEW_VERSION)

    digests = {}
    for shape, newline in (("lf", "\n"), ("crlf", "\r\n")):
        catalog = tmp_path / shape
        shutil.copytree(MIGRATIONS_DIR, catalog, dirs_exist_ok=True)
        (catalog / NEW_FILENAME).write_bytes(text.replace("\n", newline).encode("utf-8"))
        entry = next(item for item in mig.discover_migrations(catalog) if item.version == NEW_VERSION)
        digests[shape] = entry.checksum

    assert digests == {"lf": digest_from_text, "crlf": digest_from_text}, digests
    assert registered.checksum == digest_from_text
    crlf_bytes = text.replace("\n", "\r\n").encode("utf-8")
    assert hashlib.sha256(crlf_bytes).hexdigest() != digest_from_text, (
        "CRLF 字节摘要与文本摘要相等？那这枚刀没内容，改回字节判法也不会红——本件不许这种形状"
    )


def test_0018_is_in_the_catalog_and_is_the_only_builder_of_that_column():
    """目录里有 0018 这一版、且全仓只有它把 model_calls.cached_tokens 建出来。

    本件**不**声明「0018 是目录尾号」：那句话的唯一天职在
    ``tests/test_r349_catalog_tail_ledger.py``（全仓只许在那里写死一枚数字），这里再抄一份
    就是第二本手抄账，会被那件自己的形状钉抓红。
    """
    registered = next(item for item in mig.MIGRATIONS if item.version == NEW_VERSION)

    assert registered.name == NEW_NAME
    assert registered.checksum == hashlib.sha256(NEW_PATH.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    #: 「第一枚把这一列建出来的迁移」= 全目录重放，而不是 r183 那件把默认 through 钉在自己那一版
    #: （0012）上的 helper：抄它的默认值会把 0017/0018 当成不存在，那是假绿。
    builders = [
        (item.version, spec.column)
        for item in mig.MIGRATIONS
        for spec in added_column_specs(item.sql, item.version)
        if spec.table == TABLE and spec.column == COLUMN
    ]

    assert builders == [(NEW_VERSION, COLUMN)], (
        f"cached 这一列的建造者应是 0018 一枚，实取 {builders}"
    )