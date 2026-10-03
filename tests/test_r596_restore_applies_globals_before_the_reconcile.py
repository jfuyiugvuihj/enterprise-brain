"""R596 判据②（恢复侧那一半）：施加落在 ``pg_restore`` 之后、任何对账之前，globals 逐枚等值进门控。

R587 交回时把话说白了：恢复库里 ``app.embedding_dimension`` 现读 MISSING，而向量行数、schema、
md5 全对，E 门"备份恢复演练通过"照样绿。本文件用一枚**会记状态**的假库（``_FakeCluster``）把
这一格变成行为判据：``pg_restore`` 在假库里造出来的是"对象都在、setting 一枚没有"的那一面，
所以施加那一步不跑，对账就必须读到 MISSING 并且点名；跑对了两侧才逐枚相等。顺序另外用 AST
钉死一次——桩里的事件序列随写法变，函数体里那几行的先后不会变。

离线钉：不连库、不动容器、不打模型。假库只认名册里的语句，名册外一律当场报错，
"psql 反正会返回点东西"是最容易长成假绿的那一行。
"""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess

from scripts import restore_database as book

SOURCE_URL = "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain"
TARGET_URL = "postgresql://backup_user:secret@127.0.0.1:5433/eb_r596_restore"
SOURCE_DB = "enterprise_brain"
TARGET_DB = "eb_r596_restore"
DIMENSION_GUC = "app.embedding_dimension"
MODEL_GUC = "app.embedding_model"

_DB_LINE = re.compile(
    r"format\('ALTER DATABASE %I SET ([a-z_.0-9]+) = %L', current_database\(\), '([^']*)'\)")
_ROLE_LINE = re.compile(
    r"format\('ALTER ROLE %I IN DATABASE %I SET ([a-z_.0-9]+) = %L', '([^']*)', "
    r"current_database\(\), '([^']*)'\)")


class _FakeCluster:
    """假库：源侧交真取的那两枚 setting，恢复侧在 ``pg_restore`` 之后一枚都不带。

    ``tamper`` 用来演"目标库自己已经声明过别的值"那一面（客户改过宽度再恢复，真会出现）。
    """

    def __init__(self, *, source=None, deferred=None, roles="postgres:super",
                 tamper=None, skip_apply=False) -> None:
        #: 源库上声明过的库级 setting（名字→值）；空一本就是"源库本来就没声明"那一面。
        self.source = {DIMENSION_GUC: "768", MODEL_GUC: "nomic-embed-text"} if source is None else dict(source)
        self.source_deferred = [] if deferred is None else deferred
        self.roles = roles
        self.tamper = tamper or {}
        self.skip_apply = skip_apply
        self.rows: list[dict] = []
        #: 恢复库在施加之前的那一面：对象齐全，两枚 setting 读出来都是 MISSING。
        self.session: dict[str, str] = {name: "MISSING" for name in (DIMENSION_GUC, MODEL_GUC)}
        self.events: list[str] = []
        self.statements: list[str] = []

    # -- 源库那一面（备份侧现取） ------------------------------------------------------
    def _source_rows(self) -> list[dict]:
        rows = [{"scope": "database", "setdatabase": "16384", "setrole": "0", "database": SOURCE_DB,
                 "role": "(all)", "name": name, "value": value}
                for name, value in sorted(self.source.items())]
        return rows + list(self.source_deferred)

    def _source_session(self) -> dict:
        return {name: self.source.get(name, "MISSING") for name in (DIMENSION_GUC, MODEL_GUC)}

    # -- 恢复库那一面（施加之后才长出来） ----------------------------------------------
    def _target_rows(self) -> list[dict]:
        return [dict(row, database=TARGET_DB, setdatabase="99999") for row in self.rows]

    def run(self, command, **kwargs) -> subprocess.CompletedProcess:
        tool = command[0]
        if tool == "pg_restore":
            self.events.append("pg_restore")
            # 这一句就是本单的病灶：对象与行都回来了，pg_db_role_setting 的行一枚都不在归档里。
            self.rows = []
            self.session = {name: "MISSING" for name in (DIMENSION_GUC, MODEL_GUC)}
            return subprocess.CompletedProcess(list(command), 0, "", "")
        if tool == "pg_dump":
            self.events.append("pg_dump")
            Path(command[command.index("--file") + 1]).write_bytes(b"custom-format-payload")
            return subprocess.CompletedProcess(list(command), 0, "", "")
        if tool != "psql":
            raise AssertionError("假库不认这件工具：" + str(command))
        database = command[command.index("--dbname") + 1]
        if "--file" in command:
            self.events.append("globals_apply")
            if not self.skip_apply:
                self._apply(kwargs.get("input") or "", database)
            return subprocess.CompletedProcess(list(command), 0, "", "")
        statement = command[command.index("--command") + 1]
        self.statements.append(statement)
        self.events.append("read")
        answer = self._answer(statement, database)
        return subprocess.CompletedProcess(list(command), 0, answer + "\n", "")

    def _answer(self, statement: str, database: str) -> str:
        import json

        if statement.strip() == "SELECT current_database()":
            return json.dumps(database)
        if "pg_db_role_setting" in statement:
            rows = self._source_rows() if database == SOURCE_DB else self._target_rows()
            return json.dumps(rows)
        if "json_object_agg" in statement:
            session = (self._source_session() if database == SOURCE_DB else self.session)
            return json.dumps(session)
        if "FROM pg_roles" in statement:
            return json.dumps(self.roles)
        raise AssertionError("假库没安排这条语句：" + statement[:120])

    def _apply(self, body: str, database: str) -> None:
        for line in (text.strip() for text in (body or "").splitlines()):
            if not line or line.startswith("--") or line in ("BEGIN;", "COMMIT;"):
                continue
            matched = _ROLE_LINE.search(line)
            if matched:
                name, role, value = matched.groups()
                self.rows.append({"scope": "role_in_database", "setdatabase": "99999",
                                  "setrole": "100", "database": database, "role": role,
                                  "name": name, "value": value})
                self.session[name] = value
                continue
            matched = _DB_LINE.search(line)
            if matched:
                name, value = matched.groups()
                value = self.tamper.get(name, value)
                self.rows.append({"scope": "database", "setdatabase": "99999", "setrole": "0",
                                  "database": database, "role": "(all)", "name": name,
                                  "value": value})
                self.session[name] = value
                continue
            raise AssertionError("施加件里出现了假库不认的语句（形状已被判据①拒过）：" + line[:120])


def _patch_cluster(monkeypatch, cluster: _FakeCluster) -> None:
    monkeypatch.setattr(book.subprocess, "run", cluster.run)


def _backup_pair(monkeypatch, tmp_path, cluster: _FakeCluster, name: str = "brain.dump"):
    """先用出厂备份工序那套读数把成对产物落盘，再把事件账清零：只留恢复侧的顺序。"""
    dump = tmp_path / name
    dump.write_bytes(b"custom-format-payload")
    book.write_globals_pair(SOURCE_URL, dump)
    cluster.events.clear()
    cluster.statements.clear()
    return dump


# ---------------------------------------------------------------------------
# 判据①（恢复侧那一半）＋判据②：顺序与逐枚等值
# ---------------------------------------------------------------------------

def test_the_cli_applies_the_pair_after_pg_restore_and_before_any_reconcile(
        monkeypatch, tmp_path, capsys) -> None:
    cluster = _FakeCluster()
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0, captured.out + captured.err
    order = [event for event in cluster.events if event != "read"]
    assert order == ["pg_restore", "globals_apply"], order
    assert cluster.events.index("globals_apply") < cluster.events.index("read"), (
        "对账的第一枚读数赶在施加之前：那比的是没施加过的库")
    assert cluster.session[DIMENSION_GUC] == "768"
    assert {row["database"] for row in cluster.rows} == {TARGET_DB}, (
        "恢复库上的行还带着源库名，对账那把不带库名的钥匙就白造了")
    assert "globals_applied=2" in out, out
    assert "reconcile globals_profile" in out and "reconcile globals_session" in out, out


def test_the_order_is_also_pinned_in_the_function_body() -> None:
    """桩会随写法变形，函数体里这几行的先后不会：施加必须在 pg_restore 之后、对账之前。"""
    source = Path(book.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    entry = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name == "restore_backup_with_globals")
    first = {}
    for node in ast.walk(entry):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            first.setdefault(node.func.id, node.lineno)

    for name in ("read_globals_pair", "restore_database", "apply_globals", "reconcile_globals"):
        assert name in first, f"{name} 不在恢复工序里：那一格没人做了"
    assert (first["read_globals_pair"] < first["restore_database"] < first["apply_globals"]
            < first["reconcile_globals"]), first


def test_a_dump_without_its_pair_never_reaches_the_target(monkeypatch, tmp_path, capsys) -> None:
    """判据④第二把反证咬的那一格：成对产物缺失 ⇒ 拒，而且 pg_restore 一次都没发出去。"""
    cluster = _FakeCluster()
    _patch_cluster(monkeypatch, cluster)
    dump = tmp_path / "orphan.dump"
    dump.write_bytes(b"custom-format-payload")

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    err = capsys.readouterr().err

    assert rc == 2, err
    assert cluster.events == [], f"没有成对产物还进了库：{cluster.events}"
    assert "没有成对的 globals 产物" in err, err
    assert "orphan.globals.json" in err and "orphan.globals.sql" in err, err


def test_skipping_the_apply_step_comes_back_as_missing_not_as_a_pass(
        monkeypatch, tmp_path, capsys) -> None:
    """判据④第一把反证的同形件：施加那一步不落地，对账必须点名 MISSING 并把进程判红。"""
    cluster = _FakeCluster(skip_apply=True)
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    err = capsys.readouterr().err

    assert rc == 3, err
    assert "恢复库里它是 MISSING" in err, err
    assert f"globals_session[{DIMENSION_GUC}]: 生产='768' 恢复='MISSING'" in err, err


def test_one_changed_value_is_named_item_by_item_in_plain_language(
        monkeypatch, tmp_path, capsys) -> None:
    """判据②的人话样例：改一枚值要点名是谁，两串不等不算交差。"""
    cluster = _FakeCluster(tamper={DIMENSION_GUC: "1536"})
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    err = capsys.readouterr().err

    assert rc == 3, err
    assert f"globals_session[{DIMENSION_GUC}]: 生产='768' 恢复='1536'" in err, err
    assert f"globals_profile[{DIMENSION_GUC}]" not in err  # 钥匙是 scope|role|name，不是裸名
    assert f"globals_profile[database|(all)|{DIMENSION_GUC}]: 备份='768' 恢复库='1536'" in err, err
    assert err.count(f"globals_session[{MODEL_GUC}]:") == 0, (
        "另一枚等上的 setting 也被逐枚点名了：逐枚判等退化成了整串比对")
    assert err.count(f"globals_profile[database|(all)|{MODEL_GUC}]") == 0, err


# ---------------------------------------------------------------------------
# 门控与上报的分界：deferred 与 cluster_roles 不许当对账项
# ---------------------------------------------------------------------------

def test_deferred_and_cluster_roles_are_reported_and_never_gated(
        monkeypatch, tmp_path, capsys) -> None:
    """恢复单库管不着整台实例的 ALTER ROLE，也管不着角色清单：照实上报，进门控就是越权。"""
    cluster = _FakeCluster(
        deferred=[{"scope": "deferred", "setdatabase": None, "setrole": "16390",
                   "database": SOURCE_DB, "role": "app_user", "name": "work_mem",
                   "value": "4MB"}],
        roles="app_user:nosuper,postgres:super")
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)
    cluster.rows.append({"scope": "deferred", "setdatabase": None, "setrole": "16390",
                         "database": TARGET_DB, "role": "app_user", "name": "work_mem",
                         "value": "8MB"})
    cluster.roles = "someone_else:nosuper"

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0, captured.out + captured.err
    assert set(book.RECON_ITEMS) == {"globals_profile", "globals_session"}, book.RECON_ITEMS
    assert set(book.EXTRA_ITEMS) == {"globals_deferred", "cluster_roles"}, book.EXTRA_ITEMS
    assert not set(book.RECON_ITEMS) & set(book.EXTRA_ITEMS)
    assert "work_mem" not in out.split("reported globals_deferred")[0], out
    assert "reported globals_deferred" in out and "reported cluster_roles" in out, out


def test_the_reconcile_hands_back_both_gated_items_with_both_sides_of_every_number(
        monkeypatch, tmp_path) -> None:
    """门控那两格必须交回两侧读数：只交一句"过了"就是没法核对的绿。"""
    cluster = _FakeCluster()
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)

    result = book.restore_backup_with_globals(dump, TARGET_URL)
    report = result["reconcile"]

    assert set(report["items"]) == set(book.RECON_ITEMS)
    for name, item in report["items"].items():
        assert item["recorded"] == item["restored"], name
        assert item["recorded"], name
    assert set(report["extras"]) == set(book.EXTRA_ITEMS)
    assert report["gated"] == list(book.RECON_ITEMS)
    assert report["reported"] == list(book.EXTRA_ITEMS)
    assert report["problems"] == []


def test_the_two_shipped_clis_finish_the_job_when_chained(monkeypatch, tmp_path, capsys) -> None:
    """出厂的两枚 CLI 串起来必须真把活儿干完：备份交成对产物，恢复施加并逐枚对上。

    这一枚是判据④第二把反证的落点——把备份侧采集那一行摘掉，这里必须红在
    **成对产物缺失**上，而不是红在别的什么形状上。
    """
    from scripts import backup_database as backup_book

    cluster = _FakeCluster()
    _patch_cluster(monkeypatch, cluster)
    dump = tmp_path / "chained.dump"

    assert backup_book.main(["--output", str(dump), "--database-url", SOURCE_URL]) == 0, (
        capsys.readouterr().err)
    assert [event for event in cluster.events if event != "read"] == ["pg_dump"], cluster.events
    cluster.events.clear()

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0, captured.out + captured.err
    assert dump.with_name("chained.globals.json").is_file()
    assert dump.with_name("chained.globals.sql").is_file()
    assert "globals_applied=2" in out, out
    assert cluster.session == {DIMENSION_GUC: "768", MODEL_GUC: "nomic-embed-text"}

# ---------------------------------------------------------------------------
# 源侧本来就没声明的那一面：R587 的门禁口径，不许这里放宽
# ---------------------------------------------------------------------------

def test_a_source_that_declared_nothing_is_refused_at_the_reconcile(
        monkeypatch, tmp_path, capsys) -> None:
    """源库上 app.embedding_dimension 就是 MISSING ⇒ 这份备份配不出可信施加件，判红。"""
    cluster = _FakeCluster(source={})
    _patch_cluster(monkeypatch, cluster)
    dump = tmp_path / "blind.dump"
    dump.write_bytes(b"custom-format-payload")
    book.write_globals_pair(SOURCE_URL, dump)
    cluster.events.clear()

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    err = capsys.readouterr().err

    assert rc == 3, err
    assert "源库上它本来就没声明" in err, err


def test_the_cli_prints_the_reconciled_items_only_on_a_clean_reconcile(
        monkeypatch, tmp_path, capsys) -> None:
    cluster = _FakeCluster(tamper={MODEL_GUC: "bge-m3"})
    _patch_cluster(monkeypatch, cluster)
    dump = _backup_pair(monkeypatch, tmp_path, cluster)

    rc = book.main([str(dump), "--database-url", TARGET_URL])
    captured = capsys.readouterr()
    out, err = captured.out, captured.err

    assert rc == 3, err
    assert "等=True" not in out, "对账不等还在打印「等=True」：这句假话比不打印更难发现"
    assert f"globals_session[{MODEL_GUC}]: 生产='nomic-embed-text' 恢复='bge-m3'" in err, err