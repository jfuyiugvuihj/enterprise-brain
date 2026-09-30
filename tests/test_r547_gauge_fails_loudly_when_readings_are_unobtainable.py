# -*- coding: utf-8 -*-
"""R547 派生钉（一）：量具在**拿不到数**的形状上必须各自 FAIL 并点名，一枚绿都不许长出来。

钉什么（全程零写口：不连库、不起服务、不打模型；变异一律落在进程内的字典上）：

  ① 三形各自红——读不到库（rc=2）／表空（rc=1）／列全空（rc=1），每一形都点名自己的 reason code；
  ② "量不到"永远不许被折成"读到 0 枚"——拿不到数时四件的读数里不得出现条数式读数；
  ③ 生产臂自封绿当场拒：把 (a) 或 (d) 在内存里改成 PASS，`green_audit` 必须点名、rc 必须是"拒"；
  ④ 关门只认生产臂：`--gate sandbox` 当场 rc=3，沙盒臂量到什么都不关这道门；
  ⑤ 连接身份与关系缺失两形各归各码：连错库 = IDENTITY_MISMATCH（拒），缺表 = SCHEMA_RELATIONS_MISSING
     （前置不满足），两者都不许冒"库里 0 枚"；
  ⑥ 只读证明排在任何一条取数语句之前，且经过假连接的语句只有 SET/SHOW/SELECT；
  ⑦ 判定词只有一个家（`scripts/r469_readout_lib.py`），门槛数字只有一个来源（计划书 §13.一 (b) 那一行）；
  ⑧ 生产臂入口只认 `R547_PRODUCTION_DATABASE_URL`，全件不许把 `DATABASE_URL` 当生产库入口。

🔴 摘守卫的门：环境变量 `R547_GAUGE_TOOL` 指到一枚改过的量具副本（配合 `R547_REPO_ROOT` 仍指真树），
   本件就在那份副本上跑——"摘掉哪一把牙、红几枚"因此可以被复跑，不是豁免名单。
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "读不到量具：" + str(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TOOL_PATH = Path(os.getenv("R547_GAUGE_TOOL") or (REPO / "scripts" / "r547_scope_verdict_gauge.py"))
GAUGE = _load(TOOL_PATH, "r547_scope_verdict_gauge")

LIB, DRIVER = GAUGE.load_instruments()
KEYS = list(LIB.CRITERIA_KEYS)
REFUSED = int(getattr(DRIVER, "EXIT_REFUSED", 3))


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row or []


class FakeConnection:
    """只够喂量具那三枚探针的假连接；它把经过的语句全记下来，好让"只读"可被检查。"""

    def __init__(self, database: str = "enterprise_brain", relations=None):
        self.database = database
        self.relations = relations if relations is not None else {}
        self.statements: list = []

    def execute(self, sql, params=None):
        statement = " ".join(str(sql).split())
        self.statements.append(statement)
        if statement.startswith("SET SESSION"):
            return _Result(None)
        if statement.startswith("SHOW transaction_read_only"):
            return _Result(("on",))
        if statement.startswith("SELECT current_database"):
            return _Result((self.database, "baiye", "127.0.0.1", 5432, "PostgreSQL 16 (fixture)"))
        if statement.startswith("SELECT to_regclass"):
            name = str(params[0]).rsplit(".", 1)[-1]
            return _Result((self.relations.get(name),))
        raise AssertionError("量具发了本件没预料到的语句：" + statement[:80])

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def shape_run(shape):
    readings = GAUGE.fixture_readings(shape)
    floors = GAUGE.plan_floors()
    criteria = GAUGE.derive(LIB.ARM_PRODUCTION, readings, floors, LIB)
    gate = GAUGE.gate_roll(LIB.ARM_PRODUCTION, criteria, LIB)
    flags = GAUGE.degenerate_shapes(LIB.ARM_PRODUCTION, readings, LIB)
    defects = GAUGE.green_audit(LIB.ARM_PRODUCTION, criteria, readings, gate, LIB)
    rc = GAUGE.arm_rc(LIB.ARM_PRODUCTION, readings, criteria, gate, flags, defects, LIB, DRIVER)
    return {"readings": readings, "criteria": criteria, "gate": gate, "flags": flags,
            "defects": defects, "rc": rc}


def test_no_database_shape_fails_and_names_the_reason():
    run = shape_run("no-database")
    assert run["rc"] == LIB.EXIT_PRECONDITION, run
    assert run["readings"]["blocked"] == GAUGE.CONNECT_FAILED
    assert run["gate"]["verdict"] == LIB.UNVERIFIED
    assert all(item["verdict"] != LIB.PASS for item in run["criteria"].values())


def test_empty_table_shape_fails_and_names_both_denominators():
    run = shape_run("empty-table")
    assert run["rc"] == LIB.EXIT_RED, run
    assert GAUGE.POOL_TABLE_EMPTY in run["flags"]
    assert GAUGE.ACCOUNTS_TABLE_EMPTY in run["flags"]
    assert run["gate"]["verdict"] == LIB.UNVERIFIED
    assert all(not item["measurable"] for item in run["criteria"].values())


def test_all_empty_column_shape_fails_and_never_greens():
    run = shape_run("all-empty-column")
    assert run["rc"] == LIB.EXIT_RED, run
    assert GAUGE.LABEL_COLUMN_ALL_EMPTY in run["flags"]
    assert run["criteria"][KEYS[1]]["verdict"] == LIB.FAIL
    assert run["criteria"][KEYS[0]]["verdict"] == LIB.UNVERIFIED
    assert run["gate"]["verdict"] == LIB.UNVERIFIED


def test_unmeasurable_is_never_folded_into_a_count():
    """量不到那一族：读数只许说"无现读"，不许长成"非空 0 枚"那种看着像读数的句子。"""
    run = shape_run("no-database")
    for key, item in run["criteria"].items():
        assert not item["measurable"], key
        assert item["reason"] == GAUGE.CONNECT_FAILED, (key, item)
        assert not re.search(r"\d+\s*枚", item["reading"]), (key, item["reading"])
    run = shape_run("empty-table")
    for key, item in run["criteria"].items():
        assert item["verdict"] == LIB.UNVERIFIED, (key, item["verdict"])
        assert "不是读数" in item["reading"] + item["note"], (key, item["reading"])


def test_production_arm_cannot_self_green_a_subject_department():
    readings = GAUGE.fixture_readings("all-empty-column")
    criteria = GAUGE.derive(LIB.ARM_PRODUCTION, readings, GAUGE.plan_floors(), LIB)
    criteria[KEYS[0]] = dict(criteria[KEYS[0]], verdict=LIB.PASS)      # 内存里抹一把绿
    gate = GAUGE.gate_roll(LIB.ARM_PRODUCTION, criteria, LIB)
    defects = GAUGE.green_audit(LIB.ARM_PRODUCTION, criteria, readings, gate, LIB)
    rc = GAUGE.arm_rc(LIB.ARM_PRODUCTION, readings, criteria, gate, [], defects, LIB, DRIVER)
    assert defects and any("(a)" in item for item in defects), defects
    assert rc == REFUSED


def test_production_arm_cannot_self_green_d_zero_breach():
    readings = GAUGE.fixture_readings("all-empty-column")
    criteria = GAUGE.derive(LIB.ARM_PRODUCTION, readings, GAUGE.plan_floors(), LIB)
    criteria[KEYS[3]] = dict(criteria[KEYS[3]], verdict=LIB.PASS)
    gate = GAUGE.gate_roll(LIB.ARM_PRODUCTION, criteria, LIB)
    defects = GAUGE.green_audit(LIB.ARM_PRODUCTION, criteria, readings, gate, LIB)
    assert any("(d)" in item for item in defects), defects
    assert GAUGE.arm_rc(LIB.ARM_PRODUCTION, readings, criteria, gate, [], defects,
                        LIB, DRIVER) == REFUSED


def test_sandbox_arm_closes_nothing_even_with_teeth():
    readings = {"accounts": {"users_total": 9, "users_with_department": 9,
                             "non_admin_accounts_with_department": 8, "rows": []},
                "labels": {"rows_total": 1080, "nonempty_department": 1080,
                           "distinct_departments": ["fin", "hr", "ops", "exec"],
                           "distinct_classifications": ["1", "2", "3", "4"],
                           "distinct_pairs": 16, "r59c_rows": 72},
                "tiers": [{"label": "staff-fin-l1", "role": "staff", "departments": ["fin"],
                           "pool_total": 1080, "admitted_total": 6, "outside_total": 1074}]}
    criteria = GAUGE.derive(LIB.ARM_SANDBOX, readings, GAUGE.plan_floors(), LIB)
    gate = GAUGE.gate_roll(LIB.ARM_SANDBOX, criteria, LIB)
    assert gate["verdict"] == LIB.UNVERIFIED
    assert gate["reason"] == GAUGE.ARM_SUBSTITUTION_REFUSED, gate
    assert GAUGE.SANDBOX_NEVER_CLOSES_GATE in gate["why"]


def test_gate_flag_from_sandbox_is_refused_by_the_cli(capsys):
    rc = GAUGE.main(["--mode", "live", "--arm", "both", "--gate", "sandbox"])
    captured = capsys.readouterr().out
    assert rc == REFUSED, captured
    assert GAUGE.ARM_SUBSTITUTION_REFUSED in captured


def test_live_mode_without_dsn_names_the_exact_variable(capsys, monkeypatch):
    monkeypatch.delenv(GAUGE.PRODUCTION_DSN_ENV, raising=False)
    rc = GAUGE.main(["--mode", "live", "--arm", "production"])
    captured = capsys.readouterr().out
    assert rc == LIB.EXIT_PRECONDITION, captured
    assert GAUGE.PRODUCTION_DSN_ENV in captured
    assert GAUGE.ENV_DSN_UNSET in captured
    assert "野 PG" in captured, "点名句必须把宿主 5432 那枚形状说清楚"


def test_connected_database_that_is_not_the_claimed_arm_is_refused(monkeypatch):
    conn = FakeConnection(database="enterprise_brain_dev")
    monkeypatch.setattr(DRIVER, "open_connection", lambda url: conn)
    readings = GAUGE.collect_live(LIB.ARM_PRODUCTION, "postgresql://x@h:5432/whatever",
                                  GAUGE.PRODUCTION_DSN_ENV, LIB, DRIVER)
    assert readings["blocked"] == GAUGE.IDENTITY_MISMATCH, readings
    assert conn.statements[0].startswith("SET SESSION"), conn.statements


def test_stray_pg_without_the_expected_relations_is_unmeasurable_not_empty(monkeypatch):
    conn = FakeConnection(database="enterprise_brain", relations={})
    monkeypatch.setattr(DRIVER, "open_connection", lambda url: conn)
    readings = GAUGE.collect_live(LIB.ARM_PRODUCTION, "postgresql://x@h:5432/enterprise_brain",
                                  GAUGE.PRODUCTION_DSN_ENV, LIB, DRIVER)
    assert readings["blocked"] == GAUGE.SCHEMA_RELATIONS_MISSING, readings
    assert "chunk_vectors" in readings["detail"] and "vector_scope" in readings["detail"]
    criteria = GAUGE.derive(LIB.ARM_PRODUCTION, readings, GAUGE.plan_floors(), LIB)
    assert all(not item["measurable"] for item in criteria.values()), criteria
    assert all(item["verdict"] == LIB.UNVERIFIED for item in criteria.values()), criteria
    assert all(statement.split()[0] in {"SET", "SHOW", "SELECT"}
               for statement in conn.statements)


def test_read_only_proof_precedes_every_data_statement(monkeypatch):
    relations = {name: name for name in list(DRIVER.CORE_TABLES) + ["vector_scope"]}
    conn = FakeConnection(database="enterprise_brain", relations=relations)
    monkeypatch.setattr(DRIVER, "open_connection", lambda url: conn)
    try:      # 探针之后本件要发取数句，假连接把它挡在预料之外——正是要看头两句的顺序
        GAUGE.collect_live(LIB.ARM_PRODUCTION, "postgresql://x@h:5432/enterprise_brain",
                           GAUGE.PRODUCTION_DSN_ENV, LIB, DRIVER)
    except AssertionError:
        pass
    assert conn.statements[0].startswith("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    assert conn.statements[1].startswith("SELECT current_database"), conn.statements[1:]


def test_decision_words_have_exactly_one_home():
    """判定词只能活在那把在册尺里；量具自己长出一套同义词，就是下一枚漂的开始。"""
    banned = {LIB.PASS, LIB.FAIL, LIB.UNVERIFIED, LIB.PASS_SYNTH_ONLY}
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in {
                "derive", "gate_roll", "green_audit", "arm_rc", "unmeasurable", "degenerate_shapes"}:
            for literal in ast.walk(node):
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                    if literal.value in banned:
                        offenders.append((node.name, literal.value, literal.lineno))
    assert offenders == [], offenders


def test_the_selectivity_floor_is_derived_from_the_criterion_row():
    floors = GAUGE.plan_floors()
    line = GAUGE.read_rows(GAUGE.PLAN_REL)[floors["line"] - 1]
    assert "不同部门 ≥" in line and "不同密级 ≥" in line, line
    assert (floors["min_departments"], floors["min_classifications"]) == (2, 2), floors


def test_derive_carries_no_copied_threshold_number():
    """派生本体里除了 0（空/非空比较）不许出现整数字面量——门槛必须从判据本体现读进来。"""
    tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
    target = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "derive")
    skipped = {id(node.slice) for node in ast.walk(target)
               if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
               and node.value.id == "keys"}
    literals = {node.value for node in ast.walk(target)
                if isinstance(node, ast.Constant) and isinstance(node.value, int)
                and not isinstance(node.value, bool) and id(node) not in skipped}
    assert literals <= {0}, literals


def test_the_gauge_never_takes_the_host_database_url_as_production():
    source = TOOL_PATH.read_text(encoding="utf-8")
    assert '"' + GAUGE.PRODUCTION_DSN_ENV + '"' in source
    assert 'environ.get("DATABASE_URL"' not in source
    assert 'getenv("DATABASE_URL"' not in source
    assert GAUGE.PRODUCTION_DSN_ENV != "DATABASE_URL"
    assert GAUGE.SANDBOX_DSN_ENV != GAUGE.PRODUCTION_DSN_ENV