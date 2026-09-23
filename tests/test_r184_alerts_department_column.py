"""R184 -- alerts.department 进迁移之后，告警面的读侧与生产闸门各自变成什么形状。

判据全文在 docs/handoff/2026-09-15-backend-followup-requests.md 八十九之四。本件只碰
migrations/0012_*.sql 与 manifest.json，产品代码一字未改，所以这里钉的全是「那支迁移落
到台账上之后，已经并树的读侧代码会怎么看待存量行」：

- 判据 1：加列幂等，且在 0 行存量上不产生任何警告路径。
- 判据 2：存量行只留空串，不许从 rule_id / 数据集登记表反推部门。
- 判据 3：语义与 alert_row_visible / alert_row_scope_sql 逐字对齐，双向都钉——加列
  既不能把已有无归属行读成假空，也不能让 A 部门的告警被 B 部门读到。
- 判据 4：迁移之后生产分支从 RuntimeError 变成放行。这一条走真调用 _ensure()，
  桩 connection 的回答由 migrations 重放模型给出，不是硬编码「列在/列不在」。
- 判据 5：scripts/audit_r160_department_columns.py 已核、不需改，并把「不需改」证成
  可执行断言而不是口头结论。

桩的位置与形状在本文件里指名：_CatalogConnection 只回答 to_regclass 与
information_schema 两类问句，其余语句一律 raise，commit 一律 raise。
"""
from __future__ import annotations

import importlib
import hashlib
import sys
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.auth import create_token
from app.main import app

from test_r183_184_migration_pair import (  # noqa: T401  共用同一份离线 DDL 模型
    ALERTS_DEPARTMENT,
    NEW_VERSION,
    added_column_specs,
    executable_statements,
    first_adding_spec,
    insert_columns,
    new_migration,
    replay_added_columns,
    rows_at,
    schema_through,
    statement_head,
    statement_literal,
    writes_rows,
)

REPO = Path(__file__).resolve().parents[1]
PRE = "0011"
AUDIT_SCRIPT = REPO / "scripts" / "audit_r160_department_columns.py"

DEPT_OWN = "r184-own"
DEPT_FOREIGN = "r184-fx"
OWN_MESSAGE = "R184T-ALERT-OWN 本部门营收跌破阈值"
FOREIGN_MESSAGE = "R184T-ALERT-FX 别部门毛利跌破阈值"
LEGACY_MESSAGE = "R184T-ALERT-LEGACY 归属列出现之前写下的巡检告警"


# ============================================================ 离线台账与桩 connection
def pre_columns() -> list[str]:
    return schema_through(PRE)["alerts"]


def post_columns() -> list[str]:
    return schema_through(NEW_VERSION)["alerts"]


class _CatalogConnection:
    """按 migrations 重放出来的列目录回话的生产库替身。

    它不接收「列在不在」这个布尔参数：答案只从 schema_through(through) 取，所以
    「0012 有没有把这一枚列建出来」这件事真的能改变本文件的判定结果——把迁移改窄，
    这里立刻红，而不是仍然绿着说谎。
    """

    def __init__(self, through: str):
        self.columns = schema_through(through)
        self.executed: list[str] = []
        self._next: object = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        self.executed.append(text)
        match = re.search(r"to_regclass\('public\.(\w+)'\)", text)
        if match:
            table = match.group(1)
            self._next = {"table_name": table} if table in self.columns else None
            return self
        if "information_schema" in text:
            present = "department" in self.columns.get("alerts", [])
            self._next = {"column_name": "department"} if present else None
            return self
        raise AssertionError("生产库 schema 检查不该发出别的语句：" + text)

    def fetchone(self):
        return self._next

    def commit(self):
        raise AssertionError("production schema checks must not commit runtime DDL")


def _run_ensure(monkeypatch, through: str) -> _CatalogConnection:
    from app.api.v1 import alerts

    connection = _CatalogConnection(through)
    monkeypatch.setattr(alerts, "_initialized", False)
    monkeypatch.setattr(alerts, "_conn", lambda: connection)
    monkeypatch.setenv("APP_ENV", "production")
    return connection


# ============================================================ 台账形状（判据 1 的前半）
def test_the_alert_ledger_gains_exactly_one_column_and_the_six_survive():
    """迁移前后只差这一枚列，且原有六枚一枚没丢。

    那六枚的名字与总控在线上报的读数按**集合**判等（information_schema 给的是字母序，
    这里给的是 DDL 序，顺序不同不是缺陷）。这是对「线上 alerts 只有六列、没有
    department」那句读数的静态复验：仓内 DDL 重放出来的形状若多出第七枚，就说明
    有一支迁移在总控的读数之外。
    """
    before, after = pre_columns(), post_columns()

    assert [name for name in after if name not in before] == ["department"]
    assert set(before) == {
        "id",
        "rule_id",
        "message",
        "ai_analysis",
        "read",
        "created_at",
    }, before
    assert set(after) == set(before) | {"department"}
    assert first_adding_spec(*ALERTS_DEPARTMENT).version == NEW_VERSION


def test_the_column_is_appended_by_the_migration_not_rewritten_by_product_code():
    """生产分支只查不建：alerts.py 里不许出现给这张表加列的语句。

    迁移是部署件，runtime imports must not create tables —— 放行读侧的办法只能是
    「列已在」，不能是「应用顺手 ALTER」。
    """
    source = (REPO / "app" / "api" / "v1" / "alerts.py").read_text(encoding="utf-8")
    altered = [
        statement
        for statement in re.findall(r'"([^"]*ALTER\s+TABLE[^"]*)"', source, re.IGNORECASE)
        if "alerts" in statement
    ]

    assert altered == [
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT ''"
    ], altered
    assert "CREATE TABLE IF NOT EXISTS alerts" in source, "开发库懒建表那一腿仍要在"
    assert "run migrations first" in source, "生产缺列必须指名去找迁移，而不是自行补建"


# ============================================================ 判据 1：幂等、0 行无警告
def test_the_column_lands_on_an_empty_ledger_without_any_warning_path():
    """alerts 存量 0 行：加列既无警告也无跳过，行集合仍是空的。"""
    rows: list[dict] = []

    landed, warnings, skipped = replay_added_columns(rows, "alerts")

    assert (warnings, skipped) == ([], [])
    assert landed == []
    assert all(row["department"] == "" for row in landed)


def test_the_column_lands_on_a_populated_ledger_with_the_same_outcome_as_on_an_empty_one():
    """有存量行时走同一条路：警告为零，每行新列取常量默认，原有各格逐字节不动。

    0 行与有行的差别只该是「行数」，不该是「有没有额外的回填步骤」——只要有行的
    路径需要多做什么，判据 2 的假归属就有了入口。
    """
    empty, empty_warnings, _ = replay_added_columns([], "alerts")
    seeds = rows_at("alerts", 3, through=PRE)
    landed, warnings, skipped = replay_added_columns(seeds, "alerts")

    assert (warnings, skipped) == ([], [])
    assert len(landed) == len(seeds) == 3
    assert [row["department"] for row in landed] == ["", "", ""]
    for seed, row in zip(seeds, landed):
        assert {key: value for key, value in row.items() if key != "department"} == seed
    assert [row for row in empty] == []


def test_replaying_the_landed_file_a_second_time_skips_the_column_and_moves_no_row():
    """二次执行：IF NOT EXISTS 命中已存在的列，只发一条 NOTICE 级的跳过，不动列也不动行。"""
    once, first_warnings, first_skipped = replay_added_columns(
        rows_at("alerts", 2, through=PRE), "alerts"
    )
    twice, second_warnings, second_skipped = replay_added_columns(once, "alerts")

    assert (first_warnings, first_skipped) == ([], [])
    assert (second_warnings, second_skipped) == (
        [],
        ["alerts.department already exists, skipped"],
    )
    assert twice == once


# ============================================================ 判据 2：不许回填、不许猜
def test_no_statement_in_the_landed_file_writes_a_row_to_either_ledger():
    """本件里没有一条会改动行内容的语句：UPDATE / INSERT / DELETE / 触发器 / 规则全无。

    判据 2 的正面钉子。加列本身在 PostgreSQL 里由列定义给存量行填值，不需要任何一条
    写数据的语句；出现任何一条，都等于有人在替存量行编造归属。
    """
    statements = executable_statements(new_migration().sql)

    assert statements, "落盘的迁移不该是空文件"
    assert not [statement for statement in statements if writes_rows(statement)]
    assert {statement_head(statement) for statement in statements} == {
        "alter table",
        "comment on",
    }


def test_the_landed_file_names_no_source_it_could_infer_a_department_from():
    """迁移文本里不出现任何可被当作推断来源的名字：rule_id、登记表、拆串函数都不在。

    「从 rule_id 反推」「去 datasets 查」这两种写法一旦被塞进迁移，读侧那道行闸门就会
    把编出来的部门当证据守住；所以这里连**词**都不许出现在可执行语句里。
    """
    body = " ".join(executable_statements(new_migration().sql)).lower()

    for needle in (
        "rule_id",
        "datasets",
        "dataset_",
        "string_to_array",
        "split_part",
        "regexp_split",
        "coalesce",
        "case when",
        "select",
        "join",
    ):
        assert needle not in body, "迁移文本里出现了不该有的推断来源：" + needle


def test_a_historical_alert_keeps_reading_as_unattributed_instead_of_inheriting_a_department():
    """行为侧的判据 2：有部门数据的登记表摆在那儿，迁移后的存量行仍读成无归属。

    真回填的诱惑长这样：alerts.rule_id 指得回一条规则、规则又来自某份登了部门的
    数据，于是「顺手」把那个部门写进历史行。这里把上游摆满，再证明落下来的值是空串。
    """
    from app.api.v1.alerts import alert_owner_department

    dataset_departments = {"finance-q3.csv": "finance"}
    landed = replay_added_columns(rows_at("alerts", 1, through=PRE), "alerts")[0][0]

    assert landed["department"] == ""
    # 同一条判定在写侧会给新行盖章，但那是**新行**：它盖的是数据自己登记的部门。
    assert alert_owner_department(None, "finance-q3.csv", dataset_departments) == "finance"
    assert alert_owner_department(None, "unregistered.csv", dataset_departments) == ""


# ============================================================ 判据 3：双向语义
@pytest.fixture()
def ledger(monkeypatch):
    """离线告警台账：两条有归属、一条是迁移后形状（department == 空串）的历史行。"""
    from app.api.v1 import alerts
    from app.common import auth

    accounts: dict[str, dict] = {}

    def serve(kind: str) -> str:
        username = f"r184-{kind}"
        accounts[username] = {
            "id": "u-" + username,
            "username": username,
            "role": "manager" if kind != "admin" else "admin",
            "department": DEPT_FOREIGN if kind == "fx" else (DEPT_OWN if kind == "own" else ""),
        }
        return username

    rows = [
        {"id": 1, "rule_id": 1, "message": OWN_MESSAGE, "read": False, "department": DEPT_OWN},
        {"id": 2, "rule_id": 1, "message": FOREIGN_MESSAGE, "read": False,
         "department": DEPT_FOREIGN},
        # 迁移落下来之后，归属列出现之前的历史行就是这个形状：列在，值是空串。
        {"id": 3, "rule_id": 1, "message": LEGACY_MESSAGE, "read": False, "department": ""},
    ]
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", rows)
    monkeypatch.setattr(
        alerts, "_MEM_RULES",
        [{"id": 1, "name": "r184-rule", "metric": "revenue", "op": "lt", "threshold": 1.0,
          "enabled": True}],
    )
    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    return SimpleNamespace(
        alerts=alerts, rows=rows, accounts=accounts, serve=serve, client=TestClient(app)
    )


def _messages(body: dict) -> list[str]:
    return [str(alert.get("message") or "") for alert in body["alerts"]]


def test_the_migrated_empty_string_is_not_read_as_a_false_empty_ledger(ledger):
    """判据 3 正向：加列不会把已有无归属告警读成假空。

    这正是 alerts.py:193 那段注释点名的事故形状——先在页外裁一刀，一个只有一条
    历史告警的 manager 就会看见一张空表。列一进台账，存量行拿到了值 ''，而 '' 在
    alert_row_visible 与 alert_row_scope_sql 两处都算无归属，所以他仍看得见它。
    """
    from app.api.v1.alerts import alert_row_visible, alert_row_scope_sql

    own = Principal.from_user(ledger.accounts[ledger.serve("own")])
    predicate, _params = alert_row_scope_sql(own)

    assert alert_row_visible(own, ledger.rows[2]) is True
    assert "department IS NULL OR department = ''" in " ".join(predicate.split())
    assert LEGACY_MESSAGE in _messages(ledger.client.get(
        "/api/v1/alerts", headers=_headers(ledger.serve("own"))).json())


def test_an_attributed_alert_stays_invisible_to_another_department(ledger):
    """判据 3 反向：A 部门的告警不因加列而漏给 B 部门。

    加列改变的只有「无归属行如何被表示」，有归属那两行的判定不许因此松动。
    """
    from app.api.v1.alerts import alert_row_visible

    foreign = Principal.from_user({"id": "x", "username": "x", "role": "manager",
                                   "department": DEPT_FOREIGN})

    assert alert_row_visible(foreign, ledger.rows[0]) is False
    body = ledger.client.get(
        "/api/v1/alerts", headers=_headers(ledger.serve("fx"))
    ).json()
    assert OWN_MESSAGE not in _messages(body)
    assert FOREIGN_MESSAGE in _messages(body)
    assert LEGACY_MESSAGE in _messages(body)


def test_the_row_scope_decision_is_one_function_not_two(ledger):
    """两条腿（内存谓词 / SQL 文本）取的是同一份部门集合，迁移不许催生第二份判定。"""
    from app.api.v1.alerts import alert_row_scope_departments, alert_row_scope_sql

    manager = Principal.from_user({"id": "m", "username": "m", "role": "manager",
                                   "department": DEPT_OWN})
    administrator = Principal.from_user({"id": "a", "username": "a", "role": "admin",
                                         "department": ""})

    assert alert_row_scope_departments(manager) == {DEPT_OWN}
    assert alert_row_scope_sql(manager)[0].startswith("WHERE")
    assert alert_row_scope_departments(administrator) is None
    assert alert_row_scope_sql(administrator) == ("", ())


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


# ============================================================ 判据 4：真调用 _ensure()
def test_production_ensure_raises_on_the_pre_migration_catalog(monkeypatch):
    """0011 的台账上真调一次 _ensure()：生产分支照旧 RuntimeError，指向 migrations。

    桩的回答来自 migrations 重放，不是硬编码：把 0012 改窄或删掉，本枚与下一枚
    会各自朝反方向红。
    """
    from app.api.v1 import alerts

    connection = _run_ensure(monkeypatch, PRE)

    with pytest.raises(RuntimeError, match="alerts.department column is required in production"):
        alerts._ensure()

    assert any("to_regclass" in sql for sql in connection.executed), connection.executed
    assert any("information_schema" in sql for sql in connection.executed), connection.executed


def test_production_ensure_passes_on_the_migrated_catalog(monkeypatch):
    """判据 4 本体：0012 落进台账之后，同一处检查从抛异常变成放行。

    这一枚就是「迁移是生产分支唯一的满足办法」的可执行证据：本件没改 alerts.py
    一个字，改变的只有列目录。
    """
    from app.api.v1 import alerts

    connection = _run_ensure(monkeypatch, NEW_VERSION)

    alerts._ensure()  # 不抛就是放行；桩对任何多余语句与 commit 一律 raise

    assert [sql for sql in connection.executed if sql.upper().startswith(("CREATE", "ALTER"))] == []
    assert alerts._initialized is True


def test_the_gate_opens_only_because_the_migration_landed(monkeypatch):
    """两版对照合起来看：同一份产品代码，差别恰在 0012 有没有那一枚列。"""
    from app.api.v1 import alerts

    assert "department" not in pre_columns()
    assert "department" in post_columns()

    _run_ensure(monkeypatch, PRE)
    with pytest.raises(RuntimeError):
        alerts._ensure()

    monkeypatch.setattr(alerts, "_initialized", False)
    _run_ensure(monkeypatch, NEW_VERSION)
    alerts._ensure()


# ============================================================ 写侧与台账对得上（判据 9 的另一半）
def test_the_alert_writer_binds_only_columns_the_migrated_ledger_has():
    """写侧那条 INSERT 的四枚列，迁移后全在台账里；迁移前 department 不在。

    这正是整条栈卡住的那枚原因：镜像里的 INSERT 要 bind 一列，而台账没有。
    本枚断言在「把 0012 改窄」时必红，所以判据 9 的两半在这里各有一枚钉子。
    """
    statement = statement_literal("app/api/v1/alerts.py", "INSERT INTO alerts")
    table, columns = insert_columns(statement)

    assert table == "alerts"
    assert set(columns) <= set(post_columns()), columns
    assert "department" not in pre_columns()
    assert set(columns) & set(pre_columns()) == set(columns) - {"department"}


# ============================================================ 判据 5：普查脚本已核、不需改
def _audit_module():
    """按标准办法把普查脚本装进来：先登记进 sys.modules，再 exec。

    它顶层有 @dataclass，而 dataclasses 解析字符串注解时要按 cls.__module__ 回查
    sys.modules；不登记就会在 import 阶段炸掉。这条与脚本本身无关，是加载器的规矩。
    """
    name = "audit_r160_under_test"
    spec = importlib.util.spec_from_file_location(name, AUDIT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def test_the_census_script_takes_its_department_vocabulary_from_rbac_not_from_itself():
    """普查口径的唯一来源是 app/common/rbac.py::ROW_DEPARTMENT_COLUMNS。

    本件不许放宽它的判定，所以先证它没有把候选列名硬编码在自己身上：候选名取自
    rbac 的解析结果，要改口径只能去改 rbac。
    """
    audit = _audit_module()
    dept_candidates, class_candidates, meta = audit.parse_rbac_candidates(REPO)

    assert "department" in dept_candidates, dept_candidates
    assert Path(meta["file"]).name == "rbac.py", meta
    assert class_candidates


def test_the_census_verdict_for_alerts_flips_from_missing_to_present_on_the_new_catalog():
    """迁移落到线上库之后，普查对 alerts 的读数自动从缺列变成有列：本件无需改动它。

    这是对判据 5 的正面回答——总控给的普查读数把 alerts 记成缺列，是因为**活库**今天
    确实只有六列。0012 落库之后它自己会读对，不需要谁去改它的判定。
    """
    audit = _audit_module()
    dept_candidates, _class_candidates, _meta = audit.parse_rbac_candidates(REPO)

    assert audit.match_columns(pre_columns(), dept_candidates) is None
    assert audit.match_columns(post_columns(), dept_candidates) == "department"


def test_the_census_script_does_not_depend_on_the_migration_catalog():
    """它读的是活库的列目录，不是 migrations/*.sql 的文本，也不钉任何版本号。

    「migrations」这串字在脚本里只出现在一个地方：那张真表的名字 schema_migrations——
    那是**线上对象名**，与仓内的迁移文件目录无关。所以这支迁移既不会让它变绿，也不会
    因为它而失效；本件动它一个字都是多余的放宽。
    """
    text = AUDIT_SCRIPT.read_text(encoding="utf-8")

    assert re.findall(r"\b00\d\d\b", text) == [], "它不该钉任何迁移版本号"
    assert set(re.findall(r"\w*migrations\w*", text)) <= {"schema_migrations"}, "只许提表名"
    assert "information_schema" in text, "PG 列目录来自活库"
    assert "PRAGMA table_info" in text, "SQLite 列目录来自活库"


def test_the_landed_bytes_still_match_the_manifest_digest():
    """判据 4 的落盘前提：取 hash 的对象是盘上那枚文件，不是内存里的字符串。

    R190 改口（判据 6 的同一病灶，本枚是它的孪生件，``tests/test_r183_184_migration_pair.py``
    同名改口的口径照搬）：仓库 ``core.autocrlf`` 为 true 而仓库没有 ``.gitattributes`` 给
    ``migrations/*.sql`` 定行尾 ⇒ 任何一次全新检出都会把 0012 变成 CRLF，于是"盘上字节 hash ==
    manifest 数字"与"盘上不许出现 ``\r\n``"在兄弟树里必红（R187 施工方当场撞着，本单 45 枚
    迁移相关件复跑也撞着）。原口径钉的是"这台机器怎么检出的"，不是不变量。

    仍然逐字节判，不比长度：取 hash 的对象是**归一后的盘上字节**（``CRLF -> LF``），且它必须等于
    ``read_text()`` 的通用换行归一结果 —— loader 登记进 ``schema_migrations`` 的正是这一枚。三枚
    真性质一枚不丢：``\n`` 之外不许有裸 ``\r``、不许带 BOM、末尾恰好一个换行。0012 的字节不改，
    也不为"迁就"检出把它转成 CRLF。
    """
    import json

    filename = "0012_alert_and_pending_approval_attribution_columns.sql"
    manifest = json.loads((REPO / "migrations" / "manifest.json").read_text(encoding="utf-8"))
    path = REPO / "migrations" / filename
    raw = path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    text = path.read_text(encoding="utf-8")

    assert len(raw) - len(normalized) == raw.count(b"\r\n"), "归一化吃掉的字节数与 CRLF 枚数不等：比的不是同一份内容"
    assert raw.count(b"\r") == raw.count(b"\r\n"), "出现裸 CR（``\\n`` 之外的单枚 ``\\r``）：归一化会把它吃掉而改变行结构"
    assert not raw.startswith(b"\xef\xbb\xbf"), "带 BOM 会让首行注释多出看不见的字符"
    assert normalized.endswith(b"\n") and not normalized.endswith(b"\n\n"), "文件末尾恰好一个换行"
    from_bytes = hashlib.sha256(normalized).hexdigest()
    from_text = hashlib.sha256(text.encode("utf-8")).hexdigest()

    assert from_bytes == from_text == manifest[filename], {
        "bytes": from_bytes,
        "text": from_text,
        "manifest": manifest[filename],
    }
    assert hashlib.sha256(normalized + b" ").hexdigest() != manifest[filename], (
        "正向对照失效：多一枚空格都不改数字，说明这格退化成了比长度"
    )
