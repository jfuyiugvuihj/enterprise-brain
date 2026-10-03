"""R587 常驻牙：库级/角色级 setting 的成对产物必须把 E 门那枚假绿堵住（离线，桩住 _run）。

为什么这枚文件必须存在：缺陷本体是"备份日志全绿、恢复库的 app.embedding_dimension 是 MISSING"。
真机那一轮今天绿，不代表明天那一步施加还在——判据②的顺序、判据③的"取不到即红"、判据④的三把
反证，在全量回归门里只有本文件拦得住。假句柄链复用 ``tests/test_r575_vector_restore_drill.py``
里那枚 ``FakePg``（R587 之后它是有状态的：``ALTER ... SET`` 真会打在 ``self.settings`` 上，
``current_setting`` 跟着现读现答），同一条链，不造第二份。

它钉什么：
1. 名字不写死：必读项来自 ``app/db/migrations.py``，取数那一句里一枚 setting 名都没有；多出来
   的第三枚 setting 照样随行（真库上就有一枚 ``app.r587_probe`` 留着当反例）。
2. 判据①：产物与 dump 同目录同前缀，里面记着归档 sha；成对缺一枚、kind 不对、归档被换过、
   源值缺一枚、``.sql`` 被人手改开——五种不认对，一律 REFUSE，而且在建库之前。
3. 判据②：施加排在恢复工序跑的第一枚校验之前（台账与真发出去的语句两头各证一次）。
4. 判据③：逐枚等；恢复库 MISSING 红，源库改了值红，两侧都 MISSING 也红——最后这一支正是
   老口径"相等即通过"放过去的那枚假绿。
5. 判据④三把反证的常驻版：摘掉施加那一步 / 改掉一枚值 / 把恢复库清空，每一把都点名红在哪。
6. 作用域各归各位：集群级 ``ALTER ROLE ... SET`` 只进注释上报，绝不出现在能跑的语句里；
   ``apply_globals`` 拿到生产库或别人的库名当场拒收。

盲区（诚实写明）：``FakePg`` 是"件让它答什么它答什么"的替身，它证的是判据的形状，不证 PostgreSQL
真会把 ``ALTER DATABASE ... SET`` 落成会话默认值——后者只有真机那一轮能答，读数与摘前/摘后 sha
对在 ``docs/testing/r587-globals-pair-in-the-e-gate-2026-10-03.md``。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.r575_vector_restore_drill as drill
from tests.test_r575_vector_restore_drill import (
    ARCHIVE,
    ARCHIVE_SHA,
    CONTAINER,
    FakePg,
    PROD_SETTINGS,
    _globals_reading,
    _issued_statements,
    _pair,
)

EXTRA_SETTING = "app.r587_probe"
PROBE_VALUE = "7'6;8"


def _wired(monkeypatch, fake, tmp_path, *, pair=True, name="eb_r575_drill.dump"):
    """给假句柄落一枚归档，按需配好成对产物，返回那两枚路径。"""
    monkeypatch.setattr(drill, "_run", fake)
    drill.LEDGER.clear()
    archive = tmp_path / name
    archive.write_bytes(ARCHIVE)
    if pair:
        return archive, _pair(archive)
    return archive, None


def test_the_required_names_come_from_the_migration_file():
    from app.db import migrations

    assert drill.required_global_settings() == (migrations.EMBEDDING_DIMENSION_GUC,
                                               migrations.EMBEDDING_MODEL_GUC)
    # 取数那一句里一枚 setting 名都没有：整本 pg_db_role_setting 摊平回来，件不认识名字表。
    assert "app." not in drill.GLOBALS_SQL
    assert drill.GLOBALS_SQL.count("pg_db_role_setting") == 1
    for column in ("setdatabase", "setrole", "setconfig"):
        assert column in drill.GLOBALS_SQL
    assert drill.session_guc_sql("app.embedding_model").count("app.embedding_model") == 1


def test_the_capture_reads_survive_the_read_only_gate():
    drill.guard_statement(drill.GLOBALS_SQL)
    for name in drill.required_global_settings():
        drill.guard_statement(drill.session_guc_sql(name))
    # "所有角色"那一格用的是 '(all)'：'cluster' 这个词在 guard 的写关键字黑名单里（CLUSTER），
    # 拿它当标签会把自己的只读查询拒在门外。想改回去之前先读这一句。
    assert drill.GLOBALS_ALL_ROLES_LABEL == "(all)"
    assert "cluster" not in drill.GLOBALS_SQL.lower()
    assert "current_database()" in drill.GLOBALS_SQL


def test_the_gate_moved_these_two_readings_from_reported_to_gated():
    """判据⑤点名的那一格：库级 setting 从 EXTRA（上报）升进 RECON（门控）。"""
    assert "globals_profile" in drill.RECON_ITEMS
    assert "globals_session" in drill.RECON_ITEMS
    assert "db_local_settings" not in drill.EXTRA_ITEMS
    assert "local_embedding_gucs" not in drill.EXTRA_ITEMS
    assert "cluster_roles" in drill.EXTRA_ITEMS
    assert "globals_deferred" in drill.EXTRA_ITEMS
    assert not hasattr(drill, "DB_LOCAL_SETTINGS_SQL"), "旧那枚读数只能摘干净，不许留着当第二口径"
    assert not hasattr(drill, "LOCAL_GUC_SQL")


def test_the_pair_lands_next_to_the_dump_under_the_same_stem(tmp_path, monkeypatch):
    fake = FakePg()
    monkeypatch.setattr(drill, "_run", fake)
    report = drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=tmp_path)
    dump = Path(report["path"])
    pair = report["globals"]
    assert Path(pair["json"]) == dump.parent / (dump.stem + drill.GLOBALS_JSON_SUFFIX)
    assert Path(pair["sql"]) == dump.parent / (dump.stem + drill.GLOBALS_SQL_SUFFIX)
    assert Path(pair["json"]).is_file() and Path(pair["sql"]).is_file()
    payload = json.loads(Path(pair["json"]).read_text(encoding="utf-8"))
    assert payload["kind"] == drill.GLOBALS_KIND
    assert payload["archive"]["sha256"] == ARCHIVE_SHA == drill.sha256_file(dump)
    assert sorted(row["name"] for row in payload["rows"]) == sorted(PROD_SETTINGS)
    assert payload["session"] == dict(PROD_SETTINGS)
    assert len(payload["apply_lines"]) == len(PROD_SETTINGS)


def test_a_restore_without_its_pair_refuses_before_it_can_build_a_database(tmp_path, monkeypatch):
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB])
    archive, _ = _wired(monkeypatch, fake, tmp_path, pair=False)
    with pytest.raises(drill.Refuse, match="成对"):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert drill.DRILL_DB not in fake.databases, "缺 globals 的一轮连库都不许建"
    assert not [call for call in fake.calls if call["stdin"] and "CREATE DATABASE" in call["stdin"]]


def test_globals_land_before_the_restored_database_is_checked(tmp_path, monkeypatch):
    """判据②：施加排在恢复工序跑的第一枚校验之前——台账与真发出去的语句两头各证一次。"""
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB], damage={"globals-absent"})
    archive, pair = _wired(monkeypatch, fake, tmp_path)
    reading = drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert reading["globals"]["applied"] == len(PROD_SETTINGS)
    issued = drill.ledger_for(drill.DRILL_DB)
    apply_at = next(index for index, text in enumerate(issued)
                    if text.startswith("psql -f " + Path(pair["sql"]).name))
    checks = [index for index, text in enumerate(issued)
              if text.startswith("SELECT") or text.startswith("ANALYZE")]
    assert checks and min(checks) > apply_at, "恢复库上的第一枚校验必须晚于施加"

    def where(needle):
        return next(index for index, call in enumerate(fake.calls)
                    if call["stdin"] and needle in call["stdin"])

    assert where("ALTER DATABASE") < where("ANALYZE chunk_vectors")
    assert where("ALTER DATABASE") < where("pg_db_role_setting")


def test_taking_the_apply_step_out_turns_the_third_cell_red(tmp_path, monkeypatch):
    """判据④第一把（常驻版）：同一枚假库、同一对产物，只把施加那一步摘掉——第③格必须红。"""
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB], damage={"globals-absent"})
    archive, _ = _wired(monkeypatch, fake, tmp_path)
    monkeypatch.setattr(drill, "apply_globals",
                        lambda *args, **kwargs: {"applied": 0, "skipped": True})
    with pytest.raises(drill.Mismatch, match="MISSING"):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert drill.DRILL_DB not in fake.databases, "红的一轮不许留下半截库"


def test_the_reconcile_gate_names_every_setting_that_did_not_land(tmp_path, monkeypatch):
    """判据④第一把的另一头：就算没人摘那一步，恢复库空着也照样逐枚点名红。"""
    fake = FakePg(damage={"globals-absent"})
    _wired(monkeypatch, fake, tmp_path)
    prod = drill.collect_fingerprint(CONTAINER, drill.SOURCE_DB)
    restored = drill.collect_fingerprint(CONTAINER, drill.DRILL_DB)
    problems = drill.gate_required_globals(prod, restored)
    assert len(problems) == len(drill.required_global_settings())
    assert all("MISSING" in text for text in problems)
    assert drill.compare_fingerprints(prod, restored)["differences"]


def test_one_changed_value_on_the_source_turns_the_third_cell_red(tmp_path, monkeypatch):
    """判据④第二把：源库那一枚改了值（1536）、恢复库还是老值——必须红，且点名是哪一枚。"""
    fake = FakePg(damage={"source-drift"})
    _wired(monkeypatch, fake, tmp_path)
    prod = drill.collect_fingerprint(CONTAINER, drill.SOURCE_DB)
    restored = drill.collect_fingerprint(CONTAINER, drill.DRILL_DB)
    assert prod["globals_session"] != restored["globals_session"]
    problems = drill.gate_required_globals(prod, restored)
    assert len(problems) == 1
    assert "app.embedding_dimension" in problems[0] and "不等" in problems[0]
    named = " ".join(drill.compare_fingerprints(prod, restored)["differences"])
    assert "app.embedding_dimension" in named


def test_both_sides_missing_is_not_a_pass(tmp_path, monkeypatch):
    """判据③那句"不许缺失但看起来能跑"：两侧都 MISSING 时整串相等，旧口径正是此处放行。"""
    fake = FakePg()
    fake.settings[drill.SOURCE_DB] = {}
    fake.settings[drill.DRILL_DB] = {}
    _wired(monkeypatch, fake, tmp_path)
    prod = drill.collect_fingerprint(CONTAINER, drill.SOURCE_DB)
    restored = drill.collect_fingerprint(CONTAINER, drill.DRILL_DB)
    assert prod["globals_session"] == restored["globals_session"], "正控：这就是假绿的形状"
    assert prod["globals_profile"] == restored["globals_profile"] == "EMPTY"
    problems = drill.gate_required_globals(prod, restored)
    assert len(problems) == len(drill.required_global_settings())
    assert all("没声明" in text for text in problems)
    assert drill.compare_fingerprints(prod, restored)["differences"], "整串相等也不算过"
    with pytest.raises(drill.Refuse, match="本来就取不到"):
        drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=tmp_path / "out")


def test_a_third_setting_travels_with_the_pair(tmp_path, monkeypatch):
    """取数不写死两枚名字：真库上就留着一枚 app.r587_probe，值里带单引号、分号和等号。"""
    three = dict(PROD_SETTINGS)
    three[EXTRA_SETTING] = PROBE_VALUE
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB], damage={"globals-absent"})
    fake.settings[drill.SOURCE_DB] = dict(three)
    monkeypatch.setattr(drill, "_run", fake)
    drill.LEDGER.clear()
    report = drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=tmp_path)
    assert report["globals"]["applied"] == 3
    reading = drill.restore(CONTAINER, archive=Path(report["path"]), drill=drill.DRILL_DB,
                            expect_sha256=report["sha256"])
    assert reading["globals"]["applied"] == 3
    assert fake.settings[drill.DRILL_DB] == three
    body = drill.globals_sql_body(Path(report["globals"]["sql"]).read_text(encoding="utf-8"))
    assert len(body) == 3
    assert any(PROBE_VALUE.replace("'", "''") in line for line in body), "单引号要成对写回去"


def test_cluster_wide_settings_are_reported_never_applied(tmp_path, monkeypatch):
    """作用域各归各位：角色级在库内施加，集群级只进注释；库名一枚都不出现在能跑的语句里。"""
    role_row = {"scope": "role_in_database", "setdatabase": "16384", "setrole": "1",
                "database": drill.SOURCE_DB, "role": "analyst", "name": "statement_timeout",
                "value": "30s"}
    deferred = {"scope": "deferred", "setdatabase": None, "setrole": "1", "database": None,
                "role": "analyst", "name": "work_mem", "value": "64MB"}
    reading = _globals_reading(drill.SOURCE_DB, PROD_SETTINGS)
    reading["rows"] = reading["rows"] + [role_row, deferred]
    reading["profile"] = drill.globals_profile(reading["rows"])
    reading["deferred_profile"] = drill.globals_deferred_profile(reading["rows"])
    archive = tmp_path / "eb_r575_drill.dump"
    archive.write_bytes(ARCHIVE)
    pair = drill.write_globals_artifacts(tmp_path, reading, archive=archive)
    assert pair["applied"] == 3 and pair["deferred"] == 1
    text = Path(pair["sql"]).read_text(encoding="utf-8")
    body = drill.globals_sql_body(text)
    assert len(body) == 3
    assert any("ALTER ROLE %I IN DATABASE %I SET statement_timeout" in line for line in body)
    assert "work_mem" in text, "集群级那一枚要逐枚点名上报"
    assert all("work_mem" not in line for line in body), "上报就是上报，不许混进能跑的语句"
    for line in body:
        assert "current_database()" in line and line.endswith("\\gexec")
        assert drill.SOURCE_DB not in line
    with pytest.raises(drill.Refuse, match="整台实例"):
        drill.globals_apply_line(deferred)
    payload = drill.read_globals_artifact(archive)
    quiet = FakePg()
    monkeypatch.setattr(drill, "_run", quiet)
    for forbidden in (drill.SOURCE_DB, "eb_r59_sandbox", drill.MAINT_DB):
        with pytest.raises(drill.Refuse):
            drill.apply_globals(CONTAINER, forbidden, payload)
    assert quiet.calls == [], "拒收必须发生在任何 docker 调用之前"


def test_the_globals_family_adds_no_writing_statement_literal():
    """判据⑥那枚静态预算的续集：新加的施加一族不该被当成写语句收集，也不该改清单。"""
    issued = _issued_statements(Path(drill.__file__))
    assert issued, "这件本来就发 CREATE/DROP DATABASE，清单不该是空的"
    assert all("gexec" not in text for text in issued), "施加模板以 SELECT 开头才不被收集"
    assert drill.DATABASE_APPLY_LINE.startswith("SELECT format(")
    assert drill.ROLE_APPLY_LINE.startswith("SELECT format(")
    assert "cluster" not in drill.DATABASE_APPLY_LINE.lower()
    assert drill.GLOBALS_KIND == "r587-database-globals"


def test_the_pair_must_match_the_archive_it_ships_with(tmp_path, monkeypatch):
    """判据①那句"成对可核对"：五种不认对每一种都得单独拒一次，而且全在建库之前。"""
    fake = FakePg(databases=[drill.MAINT_DB, drill.SOURCE_DB])
    archive, pair = _wired(monkeypatch, fake, tmp_path)
    json_path, sql_path = Path(pair["json"]), Path(pair["sql"])
    pristine_json = json_path.read_text(encoding="utf-8")
    pristine_sql = sql_path.read_text(encoding="utf-8")
    payload = json.loads(pristine_json)

    def reset():
        archive.write_bytes(ARCHIVE)
        json_path.write_text(pristine_json, encoding="utf-8")
        sql_path.write_text(pristine_sql, encoding="utf-8")

    def tampered_json(**changes):
        def apply():
            json_path.write_text(json.dumps({**payload, **changes}, ensure_ascii=False),
                                 encoding="utf-8")
        return apply

    reset()
    drill.read_globals_artifact(archive)  # 正控：配得好好的读得动
    cases = [
        ("归档被换过一枚字节", "不成对", lambda: archive.write_bytes(ARCHIVE + b"x")),
        ("kind 被人改了", "kind", tampered_json(kind="r575-whatever")),
        ("源值少一枚必读项", "必读 setting",
         tampered_json(session={"app.embedding_dimension": "768"})),
        ("json 里的施加语句被加了一句", "不等",
         tampered_json(apply_lines=payload["apply_lines"] + ["SELECT 1"])),
        (".sql 被人手加了一句", "逐字节不等", lambda: sql_path.write_text(
            pristine_sql.replace("COMMIT;", "SELECT 1;\nCOMMIT;"), encoding="utf-8")),
    ]
    for label, pattern, tamper in cases:
        reset()
        tamper()
        with pytest.raises(drill.Refuse, match=pattern):
            drill.read_globals_artifact(archive)
    reset()
    drill.read_globals_artifact(archive)  # 还原之后又读得动：上面五枚红只认那一处篡改
    sql_path.unlink()
    with pytest.raises(drill.Refuse, match="成对"):
        drill.read_globals_artifact(archive)
    with pytest.raises(drill.Refuse, match="成对"):
        drill.restore(CONTAINER, archive=archive, drill=drill.DRILL_DB)
    assert drill.DRILL_DB not in fake.databases, "产物不全的一轮连库都不许建"


def test_the_archive_sha_and_the_pair_are_the_same_reading(tmp_path, monkeypatch):
    """成对凭据不是抄的：备份工序记下的归档 sha 必须等于件自己算出来的那一枚。"""
    fake = FakePg()
    monkeypatch.setattr(drill, "_run", fake)
    report = drill.backup(CONTAINER, source=drill.SOURCE_DB, artifact_dir=tmp_path)
    pair = report["globals"]
    assert pair["archive_sha256"] == report["sha256"] == drill.sha256_file(Path(report["path"]))
    payload = drill.read_globals_artifact(Path(report["path"]))
    assert payload["archive_sha256"] == report["sha256"]
    assert payload["source_db"] == drill.SOURCE_DB
    assert drill.globals_profile(payload["rows"]) == pair["profile"]
