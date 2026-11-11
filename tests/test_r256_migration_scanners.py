"""R256 判据⑤第二半 —— ``COMMENT ON`` 的散文里写分号，扫描器不许被裸切骗过。

来历（跟进单 §100.1 与 ``tests/test_r251_alert_disposal_migration.py`` 的文件头）：0014 落地的
第一版在 ``COMMENT ON ... IS '... ; ...'`` 的字面量**内部**有一枚分号，那把按 ``;`` 裸切的工具
把一版迁移切成了两版都不认识的形状——"这一版只发 alter table / comment on 两类语句"这句真话在
机器眼里变假，多出一枚首词是 ``the product`` 的碎片。R251 当时的解法是**把字面量里那枚分号删掉**
（散文同义改写，SQL 语义一字未动），并钉了一格"两把切刀必须切出同一份语句"。那是让迁移绕开工具。

本件换方向：工具配得上迁移。三处扫描器（``test_document_catalog_sync.split_statements``、
``test_r183_184_migration_pair.executable_statements``、``test_r251_alert_disposal_migration.quoted_statements``）
今天都认字面量，所以下一版可以往散文里写分号。🔴 而这枚试验**留在本件**，不烤进生产迁移：
一句会被复制粘贴的 SQL 不是试验田，把 ``;`` 塞进 0015 的列注释，代价是下一班真库读到一个古怪
的注释。判"扫描器不被骗"的正确地方，就是一枚合成输入。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db.migrations import MIGRATIONS
from test_document_catalog_sync import split_statements
from test_r183_184_migration_pair import (
    _COMMENT_LINE,
    executable_statements,
    statement_head,
)
from test_r251_alert_disposal_migration import quoted_statements

REPO = Path(__file__).resolve().parents[1]

#: 合成输入：一版"什么都能长在上面"的迁移，散文里三枚分号，其中一枚在字面量内部，
#: 还带一对 ``''`` 转义——PostgreSQL 读法里那是一枚单引号，不是字面量的结束。
SYNTHETIC = """ALTER TABLE IF EXISTS widget
    ADD COLUMN IF NOT EXISTS color TEXT NOT NULL DEFAULT '';

-- 注释行里的分号不算：先剥注释，再切语句。; 这一枚在注释里。
COMMENT ON COLUMN widget.color IS 'The colour this widget was registered under; an empty string '
    'means nobody recorded one -- that is a denial, not a default. Do not read it as ''public''.';
"""

#: 裸切对这串会切出几块：三枚语句结束符位置各错一次——字面量内部那枚 ``;`` 也被当成结束符，
#: 于是第二枚语句被劈成两半，尾巴那半的首词是一枚单引号，``statement_head`` 认不出任何语句种类。
#: 注释里那枚分号不算：两把刀都先剥注释。
NAIVE_CUT_COUNT = 3
IMMUNE_CUT_COUNT = 2

_LITERAL = re.compile(r"IS\s+'(?P<text>(?:[^']|'')*)'", re.IGNORECASE | re.DOTALL)
#: 那把坏刀的唯一写法。用字面量匹配而不是找引号：注释里提到 ``.split(";")`` 也算文本，
#: 所以真正的判据是"这一行代码在切"，见上两行。
_BARE_CUT = re.compile(r'\.split\(";"\)|\.split\(.;.\)')
#: 什么叫做"读迁移目录的件"：它引用 loader 登记的那一份目录，或自己去 ``discover_migrations``。
_CATALOG_READER = re.compile(r"\bMIGRATIONS\b|discover_migrations")


def naive_cut(sql: str) -> list[str]:
    """那把**坏**刀，留在本件只为对照：R251 撞上的就是它，判据⑤要防的也是它。"""
    body = _COMMENT_LINE.sub("", sql)
    return [chunk for chunk in body.split(";") if chunk.strip()]


def _heads(statements: list[str]) -> set[str]:
    return {statement_head(item) for item in statements}


# ------------------------------------------------------------------ 1. 陷阱是真的


def test_a_bare_cut_of_the_synthetic_migration_is_wrong_in_a_specific_way():
    """先证明这串确实能骗过裸切，否则后面几格只是"两把好刀互相点头"。"""
    pieces = naive_cut(SYNTHETIC)
    stripped = _COMMENT_LINE.sub("", SYNTHETIC)

    assert len(pieces) == NAIVE_CUT_COUNT, [piece[:60] for piece in pieces]
    assert _heads([" ".join(item.split()) for item in pieces]) - {
        "alter table",
        "comment on",
    }, "字面量里那枚分号没有骗到裸切：本件的输入退化成了一串无意义的语句，判据⑤失去牙齿"


def test_the_quote_aware_cut_returns_two_statements_and_no_fragment():
    pieces = split_statements(_COMMENT_LINE.sub("", SYNTHETIC))

    assert len(pieces) == IMMUNE_CUT_COUNT, [item[:60] for item in pieces]
    assert _heads([" ".join(item.split()) for item in pieces]) == {"alter table", "comment on"}
    joined = " ".join(" ".join(item.split()) for item in pieces).lower()
    assert "means nobody recorded one" in joined, "字面量被切断了：后半句去了另一枚语句"
    assert "''public''" in joined, "两枚单引号的转义被拆开或吃掉了"


# ------------------------------------------------- 2. 三处扫描器必须都免疫（同一串输入）


def test_the_persistence_layer_cutter_is_immune():
    """``test_document_catalog_sync`` 那把刀：本单的 0015 正由它逐句读。"""
    statements = [
        " ".join(item.split()).lower()
        for item in split_statements(_COMMENT_LINE.sub("", SYNTHETIC))
    ]

    assert len(statements) == IMMUNE_CUT_COUNT
    assert _heads(statements) == {"alter table", "comment on"}


def test_the_shared_ddl_model_cutter_is_immune():
    """``test_r183_184_migration_pair`` 那把刀：0012/0013/0014/0015 的离线重放都走它。"""
    statements = executable_statements(SYNTHETIC)

    assert len(statements) == IMMUNE_CUT_COUNT, statements
    assert _heads(statements) == {"alter table", "comment on"}
    assert not [item for item in statements if writes_a_row_or_is_a_shard(item)], statements


def test_the_migration_ledger_cutter_is_immune():
    """``test_r251_alert_disposal_migration`` 那把刀：三处独立写成，切出的必须同一份。"""
    quoted = quoted_statements(SYNTHETIC)
    model = executable_statements(SYNTHETIC)
    catalog = [" ".join(item.split()) for item in split_statements(_COMMENT_LINE.sub("", SYNTHETIC))]

    assert quoted == model == catalog, [item[:60] for item in quoted]


def writes_a_row_or_is_a_shard(statement: str) -> bool:
    """裸切留下的碎片长什么样：首词既不是语句种类，也不是本件允许的两种头。"""
    head = statement_head(statement)
    return head not in {"alter table", "comment on"} or bool(
        re.match(r"^\s*(update|insert|delete|drop|truncate)\b", statement, re.IGNORECASE)
    )


# -------------------------------------------------- 3. 闭包：目录里不许再有第四把裸切刀


#: 允许出现裸切的文件名——只有本件，因为只有本件要**演示**那把刀坏在哪。例外写成名字而不是
#: 把 ``.split(";")`` 藏进变量，是为了让闭包不被绕过：把本件从这枚名单里删掉，闭包立刻红。
ALLOWED_BARE_CUTTERS = frozenset({"test_r256_migration_scanners.py"})


def _migration_scanners() -> list[Path]:
    """会读迁移目录（提到 ``MIGRATIONS`` 或 ``migrations``）、又自己切 SQL 的件。"""
    offenders = []
    for directory in ("tests", "scripts", "app"):
        for path in sorted((REPO / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if not _BARE_CUT.search(text):
                continue
            if not _CATALOG_READER.search(text):
                continue
            offenders.append(path)
    return offenders


def test_no_migration_scanner_cuts_on_a_bare_semicolon():
    """判据⑤的可查形状：整个仓里，读迁移目录的件只剩认字面量的那三把刀（加本件这把坏刀）。"""
    offenders = [path.name for path in _migration_scanners()]

    assert set(offenders) == set(ALLOWED_BARE_CUTTERS), offenders


# ------------------------------------------- 4. 已落的两版今天干净：那是检查，不是运气


@pytest.mark.parametrize(
    "filename",
    [
        "0014_alert_disposal_columns.sql",
        "0015_dataset_version_scope_columns.sql",
    ],
)
def test_these_two_landed_files_hold_no_semicolon_inside_a_literal(filename: str) -> None:
    """这一格说的是**这两枚文件**今天干净，不是"以后也不许在散文里写分号"。

    后者会把判据⑤反着钉死：散文里的分号是合法的 SQL，问题从来只在工具。今天把 0014 与 0015
    现取一遍，是为了让 R251 那句"本班实测 0014 今天没有分号，但那是运气"变成一句有证据的检查。
    """
    path = REPO / "migrations" / filename
    statements = executable_statements(path.read_text(encoding="utf-8"))

    assert statements, filename
    for statement in statements:
        match = _LITERAL.search(statement)
        if match is None or not statement_head(statement).startswith("comment"):
            continue
        assert ";" not in match.group("text"), statement[:120]


def test_the_two_independent_cutters_still_agree_on_every_landed_version():
    """两把独立写成的刀对全部 15 版必须切出同一份语句——这一格与"不许写字面量内的分号"无关。

    下一版若在散文里写分号，这一格**照样绿**（两把刀都认字面量），那正是判据⑤要的：免疫，
    而不是绕路。它红只有一种形状：有人把其中一把刀改坏了。
    """
    for item in MIGRATIONS:
        assert executable_statements(item.sql) == quoted_statements(item.sql), item.version
        assert executable_statements(item.sql) == [
            " ".join(chunk.split())
            for chunk in split_statements(_COMMENT_LINE.sub("", item.sql))
        ], item.version