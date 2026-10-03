"""R596 判据①②（备份侧那一半）：库级 setting 必须与归档成对出厂。

``pg_dump`` 的归档目录里没有 ``pg_db_role_setting``，所以"整库备份成功"这句话在今天这台
机器上是可以全绿而恢复库 ``app.embedding_dimension`` 读成 MISSING 的（R587 现取，两枚
R587 交回都如实写了「生产那一格未修」）。本文件钉的是**出厂 CLI** 那一格：备份工序必须
另交一份与归档同目录同前缀的成对产物，产物必须带归档 sha 以便核对配对，施加件正文一枚
库名都不许带。

离线钉：一根 PG 都不连，psql 与 pg_dump 都由桩顶替。形状与 R587 同一本账，格式常量若
有一侧漂了，本文件与 R587 的钉会同时咬人。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from scripts import backup_database as backup_module
from scripts import restore_database as restore_module

DIMENSION_GUC = "app.embedding_dimension"
MODEL_GUC = "app.embedding_model"
URL = "postgresql://backup_user:secret@127.0.0.1:5433/enterprise_brain_accept_r596"
SOURCE_DB = "enterprise_brain_accept_r596"

#: 恢复库里这两枚 setting 的现读值，桩里的唯一事实源。
DIMENSION = "768"
MODEL = "nomic-embed-text"


def _row(scope: str, *, database: str, role: str, name: str, value: str,
         setdatabase: str | None, setrole: str) -> dict:
    return {"scope": scope, "setdatabase": setdatabase, "setrole": setrole,
            "database": database, "role": role, "name": name, "value": value}


def source_rows(**overrides) -> list[dict]:
    """源库那本账：两枚库级 setting（R587 在生产上现取的就是这一族）加一枚集群级。"""
    session = {"app.embedding_dimension": overrides.get("dimension", DIMENSION),
               "app.embedding_model": overrides.get("model", MODEL)}
    rows = [
        _row("database", database=SOURCE_DB, role="(all)", name="app.embedding_dimension",
             value=session["app.embedding_dimension"], setdatabase="16384", setrole="0"),
        _row("database", database=SOURCE_DB, role="(all)", name="app.embedding_model",
             value=session["app.embedding_model"], setdatabase="16384", setrole="0"),
        _row("deferred", database=SOURCE_DB, role="app_user", name="work_mem", value="4MB",
             setdatabase=None, setrole="16390"),
    ]
    return rows


def fake_psql(*, rows: list[dict] | None = None, session: dict | None = None,
              database: str = SOURCE_DB, roles: str = "app_user:nosuper,postgres:super"):
    """只读那一腿的桩：按语句名册交回 psql 该交回的那一行，名册外的语句当场报错。"""
    rows = source_rows() if rows is None else rows
    session = ({"app.embedding_dimension": DIMENSION, "app.embedding_model": MODEL}
               if session is None else session)
    answers = {
        "SELECT current_database()": json.dumps(database),
        "pg_db_role_setting": json.dumps(rows),
        "json_object_agg": json.dumps(session),
        "FROM pg_roles": json.dumps(roles),
    }

    def _run(command, environment, *, label, stdin_text=None):  # noqa: ARG001 - 桩的签名照原件
        if "--file" in command:
            raise AssertionError("施加不许走 --command 那条只读路径：" + str(command))
        statement = command[command.index("--command") + 1]
        for needle, answer in answers.items():
            if needle in statement:
                return subprocess.CompletedProcess(list(command), 0, answer + "\n", "")
        raise AssertionError(f"没有安排读数的语句（{label}）：{statement[:100]!r}")

    return _run


def archive(tmp_path: Path, name: str = "brain.dump", payload: bytes = b"custom-format-payload") -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


# ---------------------------------------------------------------------------
# 判据①：成对产物与归档同目录同前缀，格式沿用 R587 那一本账
# ---------------------------------------------------------------------------

def test_the_pair_lands_next_to_the_archive_under_the_same_stem(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)

    manifest = restore_module.write_globals_pair(URL, dump)

    paths = restore_module.globals_paths_for(dump)
    assert manifest["json"] == str(paths["json"]) and manifest["sql"] == str(paths["sql"])
    assert Path(manifest["json"]).is_file() and Path(manifest["sql"]).is_file()
    assert paths["json"].name == "brain.globals.json", "后缀不是 R587 那一本账的名字"
    assert paths["sql"].name == "brain.globals.sql"
    payload = json.loads(Path(manifest["json"]).read_text(encoding="utf-8"))
    assert payload["kind"] == restore_module.GLOBALS_KIND == "r587-database-globals"


def test_the_payload_carries_exactly_r587_keys_and_no_seventh(tmp_path, monkeypatch) -> None:
    """成对产物的键集是钉死的：多一枚少一枚都算第三套格式，不许在这里悄悄扩表。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())

    restore_module.write_globals_pair(URL, archive(tmp_path))
    payload = json.loads(restore_module.globals_paths_for(tmp_path / "brain.dump")["json"]
                         .read_text(encoding="utf-8"))

    assert set(payload) == {
        "kind", "source_db", "captured_utc", "archive", "rows", "session", "names",
        "profile", "session_profile", "deferred_profile", "apply_lines",
    }, sorted(payload)
    assert set(payload["archive"]) == {"name", "path", "bytes", "sha256"}
    assert {row["scope"] for row in payload["rows"]} <= set(restore_module.GLOBALS_SCOPES)
    for row in payload["rows"]:
        assert set(row) == set(restore_module.GLOBALS_COLUMNS), sorted(row)


def test_the_pair_records_the_archive_sha_so_two_runs_cannot_mix(tmp_path, monkeypatch) -> None:
    """产物与归档不成对就是不成对：换了 dump 内容还照恢复，等于拿别人的账验自己的库。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)
    restore_module.write_globals_pair(URL, dump)

    dump.write_bytes(b"a different, later pg_dump")

    with pytest.raises(restore_module.RefuseError, match="不成对"):
        restore_module.read_globals_pair(dump)


def test_the_apply_body_carries_no_database_name_while_the_comment_keeps_the_ledger(
        tmp_path, monkeypatch) -> None:
    """判据①：库名只进注释作账，语句里一枚都不带，每枚库名由 current_database() 现算。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)
    restore_module.write_globals_pair(URL, dump)

    sql_path = restore_module.globals_paths_for(dump)["sql"]
    text = sql_path.read_text(encoding="utf-8")
    body = restore_module.globals_sql_body(text)

    assert body, "施加件正文一枚语句都没有，那这一步就没东西可施加"
    assert SOURCE_DB in text, "注释里那本账（源库名）要留下，否则无法核对是谁家的 setting"
    for line in body:
        assert "current_database()" in line, line
        assert SOURCE_DB not in line, line
        assert "ALTER DATABASE enterprise_brain " not in line, line
    assert not any(line.upper().startswith("ALTER ") for line in body), (
        "语句必须包在 format(...) + \\gexec 里，裸 ALTER 不带 current_database() 的算法")


def test_a_deferred_setting_is_named_in_the_sql_never_applied(tmp_path, monkeypatch) -> None:
    """集群级 ALTER ROLE ... SET 会改整台实例的所有库：点名，但一枚都不进施加件。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)

    manifest = restore_module.write_globals_pair(URL, dump)
    text = Path(manifest["sql"]).read_text(encoding="utf-8")

    assert manifest["deferred"] == 1 and manifest["applied"] == 2
    assert "deferred role=app_user work_mem=4MB" in text
    assert "work_mem" not in " ".join(restore_module.globals_sql_body(text))
    with pytest.raises(restore_module.RefuseError, match="整台实例"):
        restore_module.globals_apply_line(source_rows()[2])


def test_the_profile_key_drops_the_database_name_that_broke_the_old_caliber(
        tmp_path, monkeypatch) -> None:
    """老口径的死因：钥匙带库名，恢复库叫别的名字，两侧永远不等。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)
    restore_module.write_globals_pair(URL, dump)
    payload = restore_module.read_globals_pair(dump)

    restored = [{"scope": "database", "setdatabase": 99999, "setrole": 0,
                 "database": "eb_r596_restore", "role": "(all)",
                 "name": "app.embedding_dimension", "value": DIMENSION},
                {"scope": "database", "setdatabase": 99999, "setrole": 0,
                 "database": "eb_r596_restore", "role": "(all)",
                 "name": "app.embedding_model", "value": MODEL}]

    assert payload["profile"] == restore_module.globals_profile(restored), (
        "同一枚 setting 换库名就该仍旧相等，否则翻默认那一格永远红")


def test_the_reader_rejoins_the_json_that_postgres_wraps_across_lines(tmp_path, monkeypatch) -> None:
    """PostgreSQL 把聚合出来的 JSON 在元素之间换行——本机 16.15 现取的字节形状就是这样的。

    真服务端交回的是 ``[{"a":"x"}, `` + 换行 + ``{"a":"y"}]``（换行落在元素之间，是合法的
    JSON 空白），而 ``json.dumps`` 交回的是单行。按行读会把两枚 setting 判成"psql 交了 2 行"
    当场拒——桩必须复现服务端那一枚形状，不然离线绿、真库红。
    """
    wrapped = (
        '[{"scope": "database", "setdatabase": "16384", "setrole": "0", '
        '"database": "' + SOURCE_DB + '", "role": "(all)", '
        '"name": "app.embedding_dimension", "value": "' + DIMENSION + '"}, ' + "\n"
        + ' {"scope": "database", "setdatabase": "16384", "setrole": "0", '
        '"database": "' + SOURCE_DB + '", "role": "(all)", '
        '"name": "app.embedding_model", "value": "' + MODEL + '"}]'
    )
    honest = fake_psql()

    def run_psql(command, environment, *, label, stdin_text=None):
        statement = command[command.index("--command") + 1]
        if "pg_db_role_setting" in statement:
            return subprocess.CompletedProcess(list(command), 0, wrapped + "\n", "")
        return honest(command, environment, label=label, stdin_text=stdin_text)

    monkeypatch.setattr(restore_module, "_run_psql", run_psql)

    manifest = restore_module.write_globals_pair(URL, archive(tmp_path))

    assert manifest["applied"] == 2, manifest
    assert manifest["profile"] == (f"database|(all)|{DIMENSION_GUC}={DIMENSION} ;; "
                                   f"database|(all)|{MODEL_GUC}={MODEL}"), manifest["profile"]


def test_a_scalar_that_comes_back_as_two_lines_is_still_refused(tmp_path, monkeypatch) -> None:
    """标量那一腿不跟着一并放宽：一枚库名分成两行读就是没读懂，宁可乐死也不猜。"""
    honest = fake_psql()

    def run_psql(command, environment, *, label, stdin_text=None):
        result = honest(command, environment, label=label, stdin_text=stdin_text)
        if "current_database" in command[command.index("--command") + 1]:
            return subprocess.CompletedProcess(list(command), 0, '"enter"\n"prise_brain"\n', "")
        return result

    monkeypatch.setattr(restore_module, "_run_psql", run_psql)

    with pytest.raises(restore_module.RefuseError, match="期望一枚值"):
        restore_module.write_globals_pair(URL, archive(tmp_path))

# ---------------------------------------------------------------------------
# 判据①（CLI 那一格）：出厂备份 CLI 默认就取，少一步就红
# ---------------------------------------------------------------------------

def _stub_pg_dump(monkeypatch, tmp_path):
    """把 pg_dump 顶掉，并记下每一次外进程：判据①要的是 CLI 默认路径真的多写了两枚文件。"""
    seen: list[list[str]] = []

    def fake_run(command, *, env, check, **kwargs):  # noqa: ARG001 - 形状照真件
        seen.append(list(command))
        backup_module.Path(command[command.index("--file") + 1]).write_bytes(b"dump")
        return subprocess.CompletedProcess(list(command), 0, "", "")

    monkeypatch.setattr(backup_module.subprocess, "run", fake_run)
    return seen


def test_the_backup_cli_writes_the_pair_by_default(monkeypatch, tmp_path, capsys) -> None:
    seen = _stub_pg_dump(monkeypatch, tmp_path)
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = tmp_path / "cli.dump"

    rc = backup_module.main(["--output", str(dump), "--database-url", URL])
    captured = capsys.readouterr()
    out = captured.out

    assert rc == 0, out + captured.err
    assert [call[0] for call in seen] == ["pg_dump"], "dump 那一腿不该被顺手改掉"
    assert dump.is_file()
    assert Path(f"{dump.with_suffix('')}.globals.json").is_file()
    assert Path(f"{dump.with_suffix('')}.globals.sql").is_file()
    assert "globals=" in out and "globals_sql=" in out, out
    assert "app.embedding_dimension=768" in out, out
    assert "app.embedding_model=nomic-embed-text" in out, out


def test_the_backup_cli_refuses_loudly_when_psql_is_not_in_the_image(
        monkeypatch, tmp_path, capsys) -> None:
    """判据③的另一面：镜像没装 postgresql-client-16 时，这里必须点名拒绝，不是假零。"""
    _stub_pg_dump(monkeypatch, tmp_path)

    def _missing(command, environment, *, label, stdin_text=None):  # noqa: ARG001
        raise restore_module.RefuseError(f"找不到 {command[0]}：镜像里没装 postgresql-client-16")

    monkeypatch.setattr(restore_module, "_run_psql", _missing)

    rc = backup_module.main(["--output", str(tmp_path / "cli.dump"), "--database-url", URL])
    err = capsys.readouterr().err

    assert rc == 2, err
    assert "postgresql-client-16" in err, err


def test_the_backup_cli_refuses_an_unreadable_source_instead_of_shipping_an_empty_pair(
        monkeypatch, tmp_path, capsys) -> None:
    """psql 交回零行、会话读数缺一枚，都算取失败：不许落成"EMPTY 也算备份成功"。"""
    _stub_pg_dump(monkeypatch, tmp_path)
    monkeypatch.setattr(restore_module, "_run_psql",
                        fake_psql(session={"app.embedding_model": MODEL}))

    rc = backup_module.main(["--output", str(tmp_path / "cli.dump"), "--database-url", URL])
    err = capsys.readouterr().err

    assert rc == 2, err
    assert "app.embedding_dimension" in err, err


# ---------------------------------------------------------------------------
# 成对产物的完整性：被人手改开过的那两枚形状
# ---------------------------------------------------------------------------

def test_a_hand_edited_apply_file_is_refused_byte_by_byte(tmp_path, monkeypatch) -> None:
    """施加件被人手改过一枚值：读的时候拒，促进恢复库之前也拒——两道都是逐字节。"""
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)
    restore_module.write_globals_pair(URL, dump)
    paths = restore_module.globals_paths_for(dump)
    payload = restore_module.read_globals_pair(dump)

    paths["sql"].write_text(
        paths["sql"].read_text(encoding="utf-8").replace("current_database(), '768')",
                                                          "current_database(), '1536')"),
        encoding="utf-8", newline="\n")

    with pytest.raises(restore_module.RefuseError, match="逐字节不等"):
        restore_module.read_globals_pair(dump)
    with pytest.raises(restore_module.RefuseError, match="逐字节不等"):
        restore_module.apply_globals(URL, payload)
    assert paths["json"].is_file(), "拒收不该顺手删掉操作者的账"


def test_a_hand_edited_json_is_refused_because_the_apply_lines_recompute(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(restore_module, "_run_psql", fake_psql())
    dump = archive(tmp_path)
    restore_module.write_globals_pair(URL, dump)
    json_path = restore_module.globals_paths_for(dump)["json"]
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["rows"][0]["value"] = "1536"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")

    with pytest.raises(restore_module.RefuseError, match="与按 rows 现算的不等"):
        restore_module.read_globals_pair(dump)


# ---------------------------------------------------------------------------
# 两处口径必须是一本账（R393/R592 那一族病：一枚读数两处取）
# ---------------------------------------------------------------------------

def test_only_one_query_reads_pg_db_role_setting_across_the_two_clis() -> None:
    """成对格式只准有一处定义：备份侧不得自己再写一份查询（散文里提它不算）。

    枚数这一族的老病是一枚口径两处取（R393 的两枚量具、R592 的 evidence_n），所以这里用
    AST 收字符串字面量而不是全文匹配：只有真发出去的语句算一份，注释与说明文字不算。
    """
    def catalog_queries(path: Path) -> list[str]:
        """只收"发出去的语句"那一类字面量：docstring 与报错文案里提它不算第二份口径。"""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value.lstrip().upper().startswith(("SELECT", "WITH"))
                and "pg_db_role_setting" in node.value]

    at_home = catalog_queries(Path(restore_module.__file__))
    in_backup = catalog_queries(Path(backup_module.__file__))

    assert len(at_home) == 1, f"库级 setting 那枚查询在恢复侧出现了 {len(at_home)} 份"
    assert "FROM pg_db_role_setting st" in at_home[0]
    assert in_backup == [], f"备份侧自己另写了一份查询：{[text[:60] for text in in_backup]}"


def test_the_reconcile_reads_with_the_same_collector_as_the_backup() -> None:
    """对账不许另起一枚读数把手：两侧都走 collect_globals，才有同一本账可谈等不等。

    点名那两腿也只能是共享的 builder（globals_profile_problems / globals_session_problems），
    在对账里再手写一次拼接就是第二份口径——R393 与 R592 都是这么分家的。
    """
    tree = ast.parse(Path(restore_module.__file__).read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    calls = {node.func.id for node in ast.walk(functions["reconcile_globals"])
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert {"collect_globals", "globals_profile_problems",
            "globals_session_problems"} <= calls, sorted(calls)
    body = ast.get_source_segment(Path(restore_module.__file__).read_text(encoding="utf-8"),
                                 functions["reconcile_globals"])
    assert ";; " not in body, "对账里自己拼了一遍 profile 串：那是第二份口径"
    assert "pg_db_role_setting" not in body, "对账里自己发了一遍目录查询"


def test_the_pair_readers_do_not_reformat_the_seven_columns() -> None:
    """七列名册与不带库名的钥匙只有一枚实现：别在对账那一步再拼一次字符串。"""
    tree = ast.parse(Path(restore_module.__file__).read_text(encoding="utf-8"))
    builders = {node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name.endswith("profile")}

    assert {"globals_profile", "globals_deferred_profile",
            "globals_session_profile"} <= builders
    assert not {"profile_for_reconcile", "reconcile_profile"} & builders, (
        "对账另起了一枚 profile builder，两侧口径就分家了")


def test_the_cli_can_import_the_book_when_run_as_a_file(tmp_path) -> None:
    """操作者那条路是 ``python scripts/backup_database.py``：这时 sys.path 里没有仓根。

    成对产物那本账住在恢复侧文件里，包内导入失败就必须退回同目录导入，否则 CLI 在自己的
    文档跑法上直接 ModuleNotFoundError——只在 pytest 里绿的那一枚不算交付。
    """
    scripts_dir = Path(backup_module.__file__).resolve().parent
    probe = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, sys.argv[1])
        import backup_database as b
        print(b._globals_book().GLOBALS_KIND)
        """
    )
    runner = tmp_path / "probe.py"
    runner.write_text(probe, encoding="utf-8", newline="\n")

    result = subprocess.run([sys.executable, "-X", "utf8", str(runner), str(scripts_dir)],
                            capture_output=True, text=True, encoding="utf-8", check=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "r587-database-globals", result.stdout