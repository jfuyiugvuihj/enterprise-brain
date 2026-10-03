"""R283 离线钉：备份隔离恢复演练必须**逐枚点名**两枚向量落点，缺一条就红。

为什么这一枚文件必须离线也跑得动（业主口径：PGVector 是生产向量库；Chroma 是退役中的
遗留件，今天仍在提供读服务）：``scripts/backup_database.py`` 是整库 ``pg_dump``，两张表
按构造都在文件里，所以"整库 dump ⇒ 向量库自然恢复得回来"永远是一句**推理**。推理在离线
回归里既不会被证伪也不会被证实，而真机演练只在 ``EB_PG_BIN_DIR`` +
``EB_PG_ACCEPTANCE_URL`` 都导出时才跑——门里它是 skip，不是 pass。于是这条链上唯一
可能长期拦住"演练退化成只点名 chunks"的，就是本文件。

它钉什么（四件，全部不需要数据库）：

1. **落点清单**：``VECTOR_LANDING_TABLES`` 必须同时是 ``chunks`` 与 ``chunk_vectors``，
   夹具必须真的往这两枚写行，且 ``_counts`` 的台账里也有镜像——摘掉任何一条，本文件红。
2. **归档目录**：``missing_landing_tables`` 只认"关系定义 + 数据"两条目录都齐的表。
   一张被筛掉的表与一张本来就空的表，在 ``pg_restore --list`` 里长得一样，所以这两半
   分开数；而 ``chunks`` 在场绝不意味着 ``chunk_vectors`` 在场（表名不是前缀匹配）。
3. **判据有没有牙齿**：``verify_vector_landings`` 与真机跑的是同一批函数、同一批 SQL，
   这里把它们对准一对假句柄，逐条注入"行数照样相等但向量坏了"的伤——整枚镜像空、单行
   向量错位、列宽被改、行内维度变窄、最近邻换了脸、``chunks`` 那一侧少一行——每一种都必须
   红，且点名是哪一枚表。
4. **反证常驻**（判据③的三把，全部只改内存，一个字节都不落盘）：把 ``chunk_vectors`` 从
   断言清单里摘掉 ⇒ 红；把行数核对折成"两侧都 0 也算过" ⇒ 红；把 top-1 断言折成
   "随便一枚命中" ⇒ 红。再加一枚静态钉：真机件里 ``backup_database`` /
   ``missing_landing_tables`` / ``verify_vector_landings`` 三个调用点必须真的把落点清单交出
   去——真机那一格在本机是 skip，它的形状今天只能由源码结构证明。

盲区（诚实写明，别把本文件当成"演练已验证"）：假句柄只会回答演练真发出的那四条 SQL，
它证明的是**判据的形状**（会不会漏掉镜像），不是 PostgreSQL 的恢复行为。真实恢复链路、
真实相似度算术仍然只有 ``tests/test_postgres_backup_recovery.py`` 那一枚真机件能给，
跑法见 ``tests/test_postgres_backup_recovery.py`` 模块开头「判据④」那一节（命令、env、
落在哪枚端口都写在那里），运维口径见 ``docs/deployment/backup-restore.md``。
本文件绿不代表向量库恢复得回来。
"""
from __future__ import annotations

import ast
import math
from pathlib import Path
import re
import subprocess

import pytest

from scripts import backup_database as backup_module
from scripts import restore_database as restore_module
from scripts.backup_database import backup_database, missing_landing_tables, tables_in_backup
from tests import test_postgres_backup_recovery as drill
from tests.test_r596_globals_pair_leaves_the_dump import fake_psql

TAG = "brp-offline"
_QUERY = drill.DRILL_QUERY_VECTOR
_COUNT_SQL = re.compile(r"^SELECT COUNT\(\*\) FROM (\w+) WHERE (\w+) = %s$")
_ROW_SQL = re.compile(
    r"^SELECT embedding::text, vector_dims\(embedding\), embedding = %s::vector"
    r" FROM (\w+) WHERE (\w+) = %s AND (\w+) = %s$"
)
_COLUMN_SQL = re.compile(
    r"^SELECT format_type\(atttypid, atttypmod\) FROM pg_attribute"
    r" WHERE attrelid = %s::regclass AND attname = 'embedding'"
)
_TOP1_SQL = re.compile(
    r"^SELECT (\w+), round\(\(embedding (<=>|<->) %s::vector\)::numeric, 6\)"
    r" FROM (\w+) WHERE (\w+) = %s ORDER BY embedding (<=>|<->) %s::vector LIMIT 1$"
)


def _parse(text: str) -> list[float]:
    return [float(part) for part in text.strip("[] ").split(",")]


def _distance(operator: str, left: list[float], right: list[float]) -> float:
    if operator == "<->":
        return math.dist(left, right)
    norm = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return 1.0 - (sum(a * b for a, b in zip(left, right)) / norm)


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class _FakePg:
    """只回答 ``verify_vector_landings`` 发出的那四条 SQL。

    解析失败直接抛错，不静默返回空：演练的 SQL 一改，本文件立刻红，而不是变成一枚
    谁也看不出问题的绿灯。``top1="worst"`` 是故障注入——同一批向量、同一发行数，
    但库对最近邻给出了另一个答案。
    """

    def __init__(
        self,
        world: dict[str, dict[str, tuple[str, int]]],
        *,
        top1: str = "best",
        column_width: dict[str, int] | None = None,
    ) -> None:
        self.world = world
        self.top1 = top1
        #: 列的声明宽度。真库里它是 ``format_type(atttypid, atttypmod)`` 的答案，行内那一发是
        #: ``vector_dims()`` 的答案，两回事。上一班从行内宽度集合里 ``pop()`` 一枚当列宽，于是
        #: 「列宽被改」与「单行被截断」两枚注入共用一个随机数，绿灯会飘；分开之后各红各的。
        self.column_width = (
            {table: drill.DRILL_DIMENSION for table in world}
            if column_width is None
            else dict(column_width)
        )
        self.queries: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> _FakeCursor:
        params = tuple(params)
        self.queries.append((sql, params))

        if _COLUMN_SQL.match(sql):
            table = params[0]
            if table not in self.world:
                return _FakeCursor([])
            return _FakeCursor([("vector(" + str(self.column_width[table]) + ")",)])

        count = _COUNT_SQL.match(sql)
        if count:
            table, _scope_column = count.groups()
            return _FakeCursor([(len(self.world.get(table, {})),)])

        row = _ROW_SQL.match(sql)
        if row:
            table, _key_column, _scope_column = row.group(1), row.group(2), row.group(3)
            expected, key, _scope = params
            stored = self.world.get(table, {}).get(key)
            if stored is None:
                return _FakeCursor([])
            text, dims = stored
            return _FakeCursor([(text, dims, text == expected)])

        top = _TOP1_SQL.match(sql)
        if top:
            _key_column, operator, table, _scope_column = (
                top.group(1), top.group(2), top.group(3), top.group(4)
            )
            if top.group(5) != operator:
                raise AssertionError(
                    "the drill must rank by the same operator it reports: " + operator + " vs " + top.group(5)
                )
            if _parse(params[0]) != _parse(_QUERY):
                raise AssertionError("the similarity probe must be the declared vector")
            scored = [
                (round(_distance(operator, _parse(text), _parse(_QUERY)), 6), key)
                for key, (text, _dims) in self.world.get(table, {}).items()
                if len(_parse(text)) == len(_parse(_QUERY))
            ]
            if not scored:
                return _FakeCursor([])
            best = min(scored) if self.top1 == "best" else max(scored)
            return _FakeCursor([(best[1], best[0])])

        raise AssertionError("the drill emitted SQL this offline fake does not model: " + sql)


def _world(tag: str = TAG) -> dict[str, dict[str, tuple[str, int]]]:
    """从演练自己的夹具造出"恢复成功"的样子：主键 -> (向量文本, 宽度)。

    用夹具而不是另写一份期望值，是为了让"判据绿"这件事只能由夹具本身解释。
    """
    return {
        landing.table: {
            key: (expected, drill.DRILL_DIMENSION)
            for key, _content, _written, expected in landing.rows
        }
        for landing in drill._landings(tag)
    }


def _damage(landing_table: str, mutate) -> dict:
    world = _world()
    mutate(world[landing_table])
    return world


def _landings_by_table(tag: str = TAG) -> dict:
    return {landing.table: landing for landing in drill._landings(tag)}


def test_the_drill_names_both_vector_landing_points() -> None:
    """判据①：两枚落点必须一起点名。这一枚就是反证钉的第一半——摘掉镜像，它先红。"""
    assert set(drill.VECTOR_LANDING_TABLES) == {"chunks", "chunk_vectors"}, (
        "演练断言的向量落点是 " + repr(drill.VECTOR_LANDING_TABLES)
        + "，R283 要求 chunks（含 embedding 列）与 chunk_vectors 逐枚点名"
    )


def test_the_fixture_seeds_every_named_landing_point() -> None:
    """断言清单与夹具必须同时覆盖两枚落点：只摘断言、或连夹具一起摘，都会在这里红。"""
    fixtures = _landings_by_table()
    assert set(fixtures) == set(drill.VECTOR_LANDING_TABLES)
    for table, landing in fixtures.items():
        keys = [row[0] for row in landing.rows]
        assert len(keys) == len(set(keys)), table + ": 夹具的主键不唯一"
        assert len(landing.rows) >= 3, table + ": 少于三枚方向不同的向量，top-1 可能靠并列撞对"
        assert landing.nearest_key in keys, table + ": 预定的 top-1 不在夹具里"


def test_the_nearest_neighbour_is_strictly_ahead_of_the_runner_up() -> None:
    """夹具的区分度：两把尺子下 top-1 都必须严格领先第二名，否则"取回原 top-1"是撞对的。"""
    for landing in drill._landings(TAG):
        for operator in drill.DRILL_DISTANCE_OPERATORS:
            ranking = sorted(
                (
                    round(_distance(operator, _parse(expected), _parse(_QUERY)), 6),
                    key,
                )
                for key, _content, _written, expected in landing.rows
            )
            assert ranking[0][1] == landing.nearest_key, (
                landing.table + ": " + operator + " 下第一名不是预定的 " + landing.nearest_key
            )
            assert ranking[1][0] - ranking[0][0] > 1e-6, (
                landing.table + ": " + operator + " 下第一名与第二名并列，top-1 不唯一"
            )


def test_the_blank_embedding_row_follows_the_0010_derivation() -> None:
    """R58 那条回填链的形状：留空的 chunks 行必须按 0010 的推导规则命中一枚镜像行且正文相同。

    这一枚钉的是夹具自己有没有对着生产链路写——``app/rag/indexing.py`` 从不写
    ``chunks.embedding``，那一列今天靠 ``sync_chunk_embedding()`` 从 ``chunk_vectors`` 认领。
    """
    fixtures = _landings_by_table()
    mirror = fixtures["chunk_vectors"]
    derived = [row for row in fixtures["chunks"].rows if row[2] is None]
    assert derived, "夹具里没有一行是留空给触发器回填的：演练就没有钉住 R58 那条链"
    for key, content, _written, expected in derived:
        stem = key.split("|v")[0]
        ordinal = key.rsplit("#", 1)[1]
        vector_id = stem + "_" + ordinal
        matched = [row for row in mirror.rows if row[0] == vector_id]
        assert matched, "推导出的 vector_id " + vector_id + " 在镜像里没有对应行"
        assert matched[0][1] == content, vector_id + ": 正文与镜像不一致，触发器会拒绝认领"
        assert matched[0][3] == expected, vector_id + ": 期望向量与镜像的那一发不同"


def test_the_count_ledger_covers_the_mirror_table() -> None:
    """整库台账比对必须自己数得上镜像，而不是只在落点清单里出现一次。"""
    assert "chunk_vectors" in drill._COUNTED_TABLES
    assert "chunks" in drill._COUNTED_TABLES
    assert drill._COUNTED_TABLES.count("chunk_vectors") == 1


def test_an_archive_holding_only_the_ledger_side_is_not_a_pass() -> None:
    """判据①（归档那一头）：``chunks`` 在场绝不等于 ``chunk_vectors`` 在场。

    行格式不是想象：``pg_restore --list`` 走 ``PrintTOCSummary()``，PG 12/13/15/16 源码里
    这一枚都是 ``ahprintf(AH, "%d; %u %u %s %s %s %s\n", dumpId, catalogId.tableoid,
    catalogId.oid, desc, schema, name, owner)``，于是 ``231; 1259 57777 TABLE public chunks
    postgres`` 这种形状就是它逐字节印出来的东西，``TABLE DATA`` 那枚只差 ``desc`` 一个词。
    """
    both = [
        "231; 1259 57777 TABLE public chunks postgres",
        "5526; 0 57777 TABLE DATA public chunks postgres",
        "240; 1259 58001 TABLE public chunk_vectors postgres",
        "5540; 0 58001 TABLE DATA public chunk_vectors postgres",
    ]
    assert tables_in_backup(both) == {"chunks", "chunk_vectors"}
    assert tables_in_backup(both, data=True) == {"chunks", "chunk_vectors"}
    assert missing_landing_tables(both, drill.VECTOR_LANDING_TABLES) == set()

    ledger_only = [line for line in both if "chunk_vectors" not in line]
    assert missing_landing_tables(ledger_only, drill.VECTOR_LANDING_TABLES) == {"chunk_vectors"}, (
        "整份目录只剩 chunks 时还判通过，等于把「整库 dump 必然覆盖」当证据"
    )

    definition_without_rows = [line for line in both if line != both[3]]
    assert missing_landing_tables(definition_without_rows, drill.VECTOR_LANDING_TABLES) == {
        "chunk_vectors"
    }, "有表定义、没有数据行的归档必须点名它缺席"

    rows_without_definition = [line for line in both if line != both[2]]
    assert missing_landing_tables(rows_without_definition, drill.VECTOR_LANDING_TABLES) == {
        "chunk_vectors"
    }


def test_backup_database_refuses_an_archive_that_drops_the_mirror(monkeypatch, tmp_path) -> None:
    """脚本级的闸：带 ``required_tables`` 的备份，归档里少了镜像就报错，不许静默成一颗绿文件。"""
    calls: list[list[str]] = []

    def fake_run(command, *, env, check):
        calls.append(list(command))
        backup_module.Path(command[command.index("--file") + 1]).write_bytes(b"dump")

    both = [
        "231; 1259 57777 TABLE public chunks postgres",
        "5526; 0 57777 TABLE DATA public chunks postgres",
        "240; 1259 58001 TABLE public chunk_vectors postgres",
        "5540; 0 58001 TABLE DATA public chunk_vectors postgres",
    ]
    monkeypatch.setattr(backup_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        restore_module,
        "list_backup",
        lambda archive, *, pg_restore_path="pg_restore": list(both),
    )

    complete = backup_database(
        "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r283",
        tmp_path / "full.dump",
        pg_dump_path="pg_dump.exe",
        required_tables=drill.VECTOR_LANDING_TABLES,
    )
    assert complete.is_file()

    monkeypatch.setattr(
        restore_module,
        "list_backup",
        lambda archive, *, pg_restore_path="pg_restore": [
            line for line in both if "chunk_vectors" not in line
        ],
    )
    with pytest.raises(RuntimeError, match="chunk_vectors"):
        backup_database(
            "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r283",
            tmp_path / "half.dump",
            pg_dump_path="pg_dump.exe",
            required_tables=drill.VECTOR_LANDING_TABLES,
        )


def test_the_guard_checks_the_archive_without_narrowing_the_dump(monkeypatch, tmp_path) -> None:
    """这道闸是"检查"，不是"筛表"：pg_dump 仍然是整库，且不带 required_tables 时一个额外进程都不起。"""
    calls: list[list[str]] = []

    def fake_run(command, *, env, check):
        calls.append(list(command))
        backup_module.Path(command[command.index("--file") + 1]).write_bytes(b"dump")

    monkeypatch.setattr(backup_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        restore_module,
        "list_backup",
        lambda archive, *, pg_restore_path="pg_restore": [
            "231; 1259 57777 TABLE public chunks postgres",
            "5526; 0 57777 TABLE DATA public chunks postgres",
            "240; 1259 58001 TABLE public chunk_vectors postgres",
            "5540; 0 58001 TABLE DATA public chunk_vectors postgres",
        ],
    )

    backup_database(
        "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r283",
        tmp_path / "guarded.dump",
        pg_dump_path="pg_dump.exe",
        required_tables=drill.VECTOR_LANDING_TABLES,
    )
    assert calls[0] == [
        "pg_dump.exe",
        "--format=custom",
        "--file",
        str(tmp_path / "guarded.dump"),
        "enterprise_brain_accept_r283",
    ]
    assert not {"-t", "--table", "-n", "--schema", "--tables-only"} & set(calls[0])

    calls.clear()
    backup_database(
        "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r283",
        tmp_path / "plain.dump",
        pg_dump_path="pg_dump.exe",
    )
    assert len(calls) == 1, "不带 required_tables 时不得多出一次 pg_restore（既有件依赖这个形状）"


def test_verify_landings_passes_and_names_both_points() -> None:
    """判据①＋②的形状：两枚落点各自数得上行、向量逐行相同、两把尺子的 top-1 都取回预定那一枚。"""
    report = drill.verify_vector_landings(_FakePg(_world()), _FakePg(_world()), tag=TAG)
    assert set(report) == set(drill.VECTOR_LANDING_TABLES)
    for table, evidence in report.items():
        assert evidence["rows"] == len(_landings_by_table()[table].rows)
        assert evidence["column"] == "vector(" + str(drill.DRILL_DIMENSION) + ")"
        assert set(evidence["top1"]) == set(drill.DRILL_DISTANCE_OPERATORS)
        for operator, (winner, _reported) in evidence["top1"].items():
            assert winner == _landings_by_table()[table].nearest_key, (
                table + ": " + operator + " 取回的 top-1 不是预先声明的那一枚，而是 " + winner
            )
    mirrored = report["chunk_vectors"]["vectors"]
    assert mirrored[_landings_by_table()["chunk_vectors"].nearest_key][0] == "[1,0]"


def test_verify_landings_is_red_when_the_mirror_table_is_empty() -> None:
    """整枚镜像没回来、行数还"看着对"——这是本单存在的理由，必须红。"""
    broken = _world()
    broken["chunk_vectors"] = {}
    with pytest.raises(AssertionError, match="chunk_vectors"):
        drill.verify_vector_landings(_FakePg(_world()), _FakePg(broken), tag=TAG)


def test_verify_landings_is_red_when_a_mirror_vector_is_shifted() -> None:
    """行数相等但向量错位：doc_1 带上了邻居的那一发。"""
    def shift(rows) -> None:
        rows["brp-offline.doc_1"] = ("[0.2,0.9]", drill.DRILL_DIMENSION)

    broken = _damage("chunk_vectors", shift)
    with pytest.raises(AssertionError, match="不再等于"):
        drill.verify_vector_landings(_FakePg(_world()), _FakePg(broken), tag=TAG)


def test_verify_landings_is_red_when_the_restored_column_is_retyped() -> None:
    """列宽被改（比如按 768 建库后恢复）：行数照样，向量文本也照样，但列不是那一列。"""
    retyped = {table: drill.DRILL_DIMENSION for table in _world()}
    retyped["chunk_vectors"] = 768
    with pytest.raises(AssertionError, match="chunk_vectors.*列宽"):
        drill.verify_vector_landings(
            _FakePg(_world()), _FakePg(_world(), column_width=retyped), tag=TAG
        )


def test_verify_landings_is_red_when_a_stored_vector_is_truncated() -> None:
    """单行维度不对（被截断）：列宽与行数都不诚实，只有 vector_dims() 诚实。"""
    def truncate(rows) -> None:
        rows["brp-offline.doc_2"] = ("[0.2,0.9]", 1)

    broken = _damage("chunk_vectors", truncate)
    with pytest.raises(AssertionError, match="宽度"):
        drill.verify_vector_landings(_FakePg(_world()), _FakePg(broken), tag=TAG)


def test_verify_landings_is_red_when_the_restored_top1_moves() -> None:
    """判据②：同一批行、同一批向量，恢复库对最近邻给出另一个答案就必须红——光比行数看不见这一格。"""
    with pytest.raises(AssertionError, match="最近邻"):
        drill.verify_vector_landings(
            _FakePg(_world()), _FakePg(_world(), top1="worst"), tag=TAG
        )


def test_verify_landings_is_red_when_the_ledger_side_loses_a_row() -> None:
    """另一侧也必须单独成立：chunks 少一行同样是红，不许只盯镜像。"""
    broken = _world()
    broken["chunks"].pop(TAG + ":mid")
    with pytest.raises(AssertionError, match="chunks"):
        drill.verify_vector_landings(_FakePg(_world()), _FakePg(broken), tag=TAG)


def test_taking_the_mirror_out_of_the_assertion_list_turns_the_drill_red(monkeypatch) -> None:
    """判据③就地取证：把 ``chunk_vectors`` 从演练断言里摘掉，同一批函数必须拒绝通过。

    这一枚把"反证"从一次性手工操作变成常驻用例——以后谁把镜像从清单里摘下去，
    不需要谁记得去手动摘一遍，门自己就会红。
    """
    monkeypatch.setattr(drill, "VECTOR_LANDING_TABLES", ("chunks",))
    with pytest.raises(AssertionError, match="chunk_vectors"):
        drill.verify_vector_landings(_FakePg(_world()), _FakePg(_world()), tag=TAG)
    monkeypatch.undo()
    assert drill.verify_vector_landings(_FakePg(_world()), _FakePg(_world()), tag=TAG)


def _call_nodes(tree: ast.AST, function_name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function_name
    ]


def test_the_live_drill_hands_both_landing_points_to_the_guard() -> None:
    """真机件必须把落点清单亲手交给那道闸——它在本机门里是 skip，形状只有源码可查。

    ``tests/test_postgres_backup_recovery.py`` 一旦丢掉 ``required_tables=``，两枚落点就又只剩
    「整库 dump 必然覆盖」这句推理，而真机演练照样绿；本机连不上验收库，就没有任何东西会红。
    所以归档这一头的**调用形状**必须由本文件钉住。用 AST 找调用点而不是文本匹配：改格式
    不算改语义，删掉参数才算。
    """
    source = Path(drill.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(drill.__file__))

    dumps = _call_nodes(tree, "backup_database")
    assert dumps, "演练里没有 backup_database 的调用点：把它删了等于把归档核对一起删了"
    guarded = [
        call
        for call in dumps
        if any(
            keyword.arg == "required_tables"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "VECTOR_LANDING_TABLES"
            for keyword in call.keywords
        )
    ]
    assert guarded, (
        "backup_database 的调用没有把 VECTOR_LANDING_TABLES 交出去：归档目录无人核对，"
        "镜像整枚不在文件里，演练照样绿——这正是要反证的假通过"
    )

    listings = _call_nodes(tree, "missing_landing_tables")
    assert listings, "演练没有核对归档目录：missing_landing_tables 一次都没调用"
    assert any(
        isinstance(node, ast.Name) and node.id == "VECTOR_LANDING_TABLES"
        for call in listings
        for node in ast.walk(call)
    ), "missing_landing_tables 没有拿 VECTOR_LANDING_TABLES 这枚唯一事实源，而是自己另写了一份表名"

    checks = _call_nodes(tree, "verify_vector_landings")
    assert checks, "演练没有调用 verify_vector_landings：行数与 top-1 这两把尺子就没人在真库上跑过"


def test_the_row_count_check_still_refuses_when_both_sides_are_zero() -> None:
    """反证 (b)：把行数核对折成「两侧都 0 也算过」⇒ 红。

    注入的就是那次折叠本身：来源库与恢复库在这枚落点上数到**同一个 0 行**，于是
    ``恢复库 == 来源库`` 这条相等断言完全通过，先红的是「恢复库数到的行数 == 演练写下的
    行数」那一条（实测红字：``chunk_vectors: 演练写入 3 行，恢复库里数到 0 行``）。
    牙齿在 ``match=`` 上，这句话说全：本班把整条 seeded 断言删掉重跑同一枚注入，演练**仍然**
    红——红在下游那枚逐行向量核对上（``brp-offline.doc_0 在来源库里数不到行``），所以真库
    这一头是双保险；而这一枚用例会因 ``match`` 吃不到那句红字当场红（实测报
    「Regex pattern did not match」）。也就是说它钉的是**由谁去拦**，不只是拦没拦住。
    """
    empty = _world()
    empty["chunk_vectors"] = {}
    mirror = _landings_by_table()["chunk_vectors"]
    source, copy = _FakePg(empty), _FakePg(empty)
    assert drill._landing_count(source, mirror) == 0, "注入没做成：来源库数不到 0 行"
    assert drill._landing_count(copy, mirror) == 0, "注入没做成：恢复库数不到 0 行"
    with pytest.raises(AssertionError, match="chunk_vectors: 演练写入"):
        drill.verify_vector_landings(source, copy, tag=TAG)


def test_the_top1_check_still_refuses_when_a_row_just_happens_to_hit() -> None:
    """反证 (c)：把 top-1 断言折成「随便一枚命中」⇒ 红。

    两侧给同一个错答案，这是「随便命中」最容易放过的形状：两库逐行向量一致、行数一致、
    列宽一致，只有最近邻换了脸。「只换恢复库」那一枚钉看不见这一格（两库一致就过去了），
    看得见的只有先于任何数据库声明的 ``nearest_key``。实测：把 top-1 两条断言折成
    ``copy_top[0] in {每一枚主键}`` 重跑同一枚注入，演练直接**绿灯通过**，这一枚用例随之报
    「DID NOT RAISE」——它就是判据② 在这一格上的证人。
    """
    with pytest.raises(AssertionError, match="预先声明"):
        drill.verify_vector_landings(
            _FakePg(_world(), top1="worst"), _FakePg(_world(), top1="worst"), tag=TAG
        )


def test_the_two_rulers_report_different_numbers_on_the_same_vector() -> None:
    """两把尺子必须真的量出两个数，否则「两把都过」只是一把过了两遍。

    ``<=>`` 是余弦距离、``<->`` 是 L2（``migrations/0010_pgvector_chunks.sql`` 把 L2 记进
    ``vector_scope.distance_function``）。同一批向量下两把读数不同，所以恢复回来的向量只在
    一把尺子下对、在另一把下错位时，必定有一把会红。
    """
    handle = _FakePg(_world())
    for landing in drill._landings(TAG):
        readings = {
            operator: drill._similarity_top1(handle, landing, operator=operator)
            for operator in drill.DRILL_DISTANCE_OPERATORS
        }
        assert {operator: reading[0] for operator, reading in readings.items()} == {
            operator: landing.nearest_key for operator in drill.DRILL_DISTANCE_OPERATORS
        }, landing.table + ": 换一把尺子 top-1 就换脸，预声明的那枚 key 没有区分度"
        assert readings["<=>"][1] != readings["<->"][1], (
            landing.table + ": 两把尺子读数相同，等于只跑了一把"
        )


def test_the_cli_forwards_both_landing_points_and_the_restore_tool(monkeypatch, tmp_path, capsys) -> None:
    """操作者那道口子的闸：``--require-table`` 必须真的走到归档核对，并能把 pg_restore 指过去。

    参数收下却没人用是最难发现的一类假绿——CLI 返回 0、dump 文件也在，只有「落点其实不在目录
    里」这一件事被静默吞掉。所以这里从 ``main()`` 的 argv 一路看到 ``list_backup`` 收到的实参，
    再验一次缺表时进程真的返回 1 并把表名报出来。
    """
    seen: dict[str, str] = {}
    both = [
        "231; 1259 57777 TABLE public chunks postgres",
        "5526; 0 57777 TABLE DATA public chunks postgres",
        "240; 1259 58001 TABLE public chunk_vectors postgres",
        "5540; 0 58001 TABLE DATA public chunk_vectors postgres",
    ]

    read_globals = fake_psql()

    def fake_run(command, *, env, check, **kwargs):  # noqa: ARG001 - 真件还带 capture_output/text/input
        """桩按工具分派：R596 起备份 CLI 不只发一发 `pg_dump`。

        `capture_output` 是 stdlib 的合法参数，桩不吃它（桩过窄）就等于把 R596 多发的那一发
        psql 判成参数错误。名册外的工具当场报错，所以「少发一条命令」仍然会红，不会被宽签名
        静默放过；读数只引用 R596 自己的名册，这里不重写一套。
        """
        tool = Path(str(command[0])).name
        if tool.startswith("pg_dump"):
            backup_module.Path(command[command.index("--file") + 1]).write_bytes(b"dump")
            return subprocess.CompletedProcess(list(command), 0, "", "")
        if tool.startswith("psql"):
            return read_globals(list(command), env, label="cli", stdin_text=kwargs.get("input"))
        raise AssertionError(f"备份 CLI 发出了名册外的工具：{command[0]!r}")

    def fake_list_backup(archive, *, pg_restore_path="pg_restore"):
        seen["pg_restore_path"] = pg_restore_path
        seen["archive"] = str(archive)
        return list(both)

    def fake_list_backup_without_mirror(archive, *, pg_restore_path="pg_restore"):
        return [line for line in fake_list_backup(archive, pg_restore_path=pg_restore_path)
                if "chunk_vectors" not in line]

    argv = [
        "--output", str(tmp_path / "cli.dump"),
        "--database-url",
        "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r283",
        "--require-table", "chunks",
        "--require-table", "chunk_vectors",
        "--pg-restore", "pg_restore.exe",
    ]
    monkeypatch.setattr(backup_module.subprocess, "run", fake_run)
    monkeypatch.setattr(restore_module, "list_backup", fake_list_backup)

    assert backup_module.main(argv) == 0, capsys.readouterr().err
    assert seen["pg_restore_path"] == "pg_restore.exe", (
        "CLI 的 --pg-restore 没有传到归档核对那一步：那道闸在换不了 pg_restore 的机器上会哑"
    )
    assert seen["archive"].endswith("cli.dump"), "归档核对看的不是刚写出来的那个文件"

    monkeypatch.setattr(restore_module, "list_backup", fake_list_backup_without_mirror)
    assert backup_module.main(argv) == 1, "目录里没有镜像时 CLI 必须拒绝，而不是照样报成功"
    err = capsys.readouterr().err
    assert "chunk_vectors" in err, err
    assert "whole-database dump is not evidence" in err, err


def test_both_similarity_operators_are_actually_queried() -> None:
    """两把尺子必须是**两把**：清单被窄成一枚、或演练只发一条查询，这里都要红。

    ``DRILL_DISTANCE_OPERATORS`` 只剩一枚时，本族所有"逐把比对"的断言都会自动成立（它们
    全部对着这枚常量迭代），连真机件里那句 ``all(operator in evidence["top1"] ...)`` 也照样
    绿——所以牙齿不能长在常量自己上。这里改看假句柄记下的真实查询：``<=>`` 与 ``<->`` 两条
    最近邻查询必须都发出来过，一条都不许少。
    """
    assert set(drill.DRILL_DISTANCE_OPERATORS) == {"<=>", "<->"}, (
        "校验清单里不是两把尺子了：" + repr(drill.DRILL_DISTANCE_OPERATORS)
        + "；cosine(<=>) 与 L2(<->) 必须同时在场，否则「两把都过」只是一把过了两遍"
    )
    handle = _FakePg(_world())
    drill.verify_vector_landings(handle, _FakePg(_world()), tag=TAG)
    queried = {
        match.group(2) for sql, _params in handle.queries if (match := _TOP1_SQL.match(sql))
    }
    assert {"<=>", "<->"} <= queried, "演练实际只发出过这些最近邻查询：" + repr(sorted(queried))
