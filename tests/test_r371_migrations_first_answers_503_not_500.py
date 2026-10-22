"""R371 · 「表/列还没迁移出来」在生产出口不许再交裸 500（同族三句里漏钉的那一句）。

现场读数（基点 `b291324`，`git show HEAD:app/api/v1/alerts.py` 现取，不是工作树）：本模块有三句
`RuntimeError(... "run migrations first")`——`:120` 缺表、`:131` 缺 `alerts.department`、`:573` 缺
`alerts.status`。而 `git grep exception_handler -- app` 零命中，所以任何一句逃到 HTTP 出口，
FastAPI 交出去的是**裸 500**：客户在「处置一条告警」这个动作上看到一个没有码、没有人话的 500，
运维也拿不到「该跑哪一枚迁移」这句真话。三句里前两格有钉（`:120` 有松钉
`tests/test_memory_production_schema.py:83`；`:131` 有紧钉 `tests/test_r184_alerts_department_column.py:420`
与松钉 `tests/test_r176_alert_row_scope.py:469`），第三格 `:573`（`_require_alert_disposal_schema`，
唯一调用点 `:635`）交工前**全仓零钉**——`alerts.py:410` 那行注释写着「像缺归属列一样」，可这一格
既没有紧钉也没有 HTTP 脸。R359 结案时把这一格登记为「立案待派」，本单就是那一案。

本件钉的形状（判据 ↔ 用例名见回执第 4 格）：

- 判据 1/6：转换后的出口答 503 `storage_unavailable`——仓里已有的那一枚码（`dashboard.py:150`、
  `notifications.py:161`、`chat.py:3037`、R359 的 `alerts.py`），🔴 零新增错误码、零新增第二道 503 门。
- 判据 2：转换只做在 **HTTP 出口那一层**。`_ensure()` 与 `_require_alert_disposal_schema()` 继续抛
  `RuntimeError`（既有钉打的就是那一层），把它们改成 `HTTPException` 就是改别人的账。
- 判据 4：捕获做窄。别的 `RuntimeError`（本模块 `:662` 那句「写成了却读不回来」）照旧是裸的
  运行时错——把任何 RuntimeError 都翻成 503，等于替真正的 bug 打掩护。
- 判据 5：开发态一个字都不改。自建库缺列时 `_ensure()` 就地补 DDL 那一支仍然自愈；分开的是两张脸。
- 判据 6③：三格两两可分辨。响应侧三格共用同一枚码是硬规矩，能把三条排查路分开的只有出口那行
  日志（跑 0003 / 跑 0012 / 跑 0014），本件按日志钉。

🔴 效力边界：没有 PG 可用（也不许碰真库/容器），全部用例跑在替身库 `_Catalog` 上——它认的是
「`to_regclass` 与 `information_schema.columns` 这两次现查怎么答」，不是真目录。它证明的是
「出口在这一格读到缺表/缺列时答什么」，不证明 migrations 真能把那三格补出来（那一腿归
`tests/test_r251_alert_disposal_migration.py` 与 `tests/test_r184_alerts_department_column.py`
对迁移目录的重放账）。
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.common.auth import create_token
from app.main import app

ADMIN = "r371-admin"
STAFF = "r371-staff"
STORAGE_CODE = "storage_unavailable"
FIXED_TS = "2026-09-27T09:00:00+08:00"

LEDGER = "/api/v1/alerts"
DETAIL = f"{LEDGER}/1"
RULES = f"{LEDGER}/rules"
RULE_ONE = f"{RULES}/1"
CHECK = f"{LEDGER}/check"

RULE_BODY = {"name": "r371-profit", "metric": "profit", "op": "lt", "threshold": 10}
RULE_ROW = {"id": 1, "name": "r371-profit", "metric": "profit", "op": "lt",
            "threshold": 10.0, "enabled": True}
ALERT_ROW = {"id": 1, "rule_id": 1, "message": "r371 营收跌破阈值", "department": "",
             "ai_analysis": "", "read": False, "created_at": "2026-09-26T09:00:00",
             "status": "open", "acknowledged_by": "", "acknowledged_at": "",
             "closed_by": "", "closed_at": "", "assignee": "", "assigned_by": "",
             "assigned_at": ""}

#: 三句（加缺表那一格的两种写法）消息文本逐字抄在这里（判据 3）：产品代码改一个字就红。
SENTENCES = {
    "missing_alert_rules_table": "alert_rules table is required in production; run migrations first",
    "missing_alerts_table": "alerts table is required in production; run migrations first",
    "missing_department": "alerts.department column is required in production; run migrations first",
    "missing_status": "alerts.status column is required in production; run migrations first",
}

#: 每格缺口对应的迁移（判据 6③：三条排查路不同，不许塌成同一句人话）。
#: 🔴 归属列在 0012，不在 0013——0013 是 pending_approvals 的状态词表；派工词那句「跑 0013」
#: 按 `git grep ... -- migrations` 现读改口，已登记回执「只报不改」。
EXPECTED_MIGRATION = {
    "missing_alert_rules_table": "migrations/0003_legacy_runtime_tables.sql",
    "missing_alerts_table": "migrations/0003_legacy_runtime_tables.sql",
    "missing_department": "migrations/0012_alert_and_pending_approval_attribution_columns.sql",
    "missing_status": "migrations/0014_alert_disposal_columns.sql",
}

BOTH_TABLES = {"alert_rules", "alerts"}
BOTH_COLUMNS = {"department", "status"}

#: 替身库的台账：谁在、谁缺，一格一份读数（`_ensure()` 先查 alert_rules 再查 alerts 再查
#: department；`_require_alert_disposal_schema` 单独查 status）。
CATALOGS: dict[str, tuple[set[str], set[str]]] = {
    "migrated": (set(BOTH_TABLES), set(BOTH_COLUMNS)),
    "missing_alert_rules_table": (set(), set()),
    "missing_alerts_table": ({"alert_rules"}, set()),
    "missing_department": (set(BOTH_TABLES), {"status"}),
    "missing_status": (set(BOTH_TABLES), {"department"}),
}
CELLS = tuple(CATALOGS)
BROKEN_CELLS = tuple(cell for cell in CELLS if cell != "migrated")

DISPOSAL_EXITS = ("write_alert_ack", "write_alert_close", "write_alert_assign")
SCHEMA_CHECK_EXITS = ("write_rule_create", "read_rule_list", "write_rule_delete",
                      "read_ledger_list", "read_alert_detail") + DISPOSAL_EXITS

#: 取证表的可执行版：每枚出口 × 每格缺口 => 该拒答的集合。`read_manual_sweep` 一枚都不在，
#: 因为它那一腿的 `_ensure()` 被 `alerts.py:820` 的宽捕获吃掉（R345 钉它「永不上抛」）。
REFUSED: dict[str, frozenset[str]] = {
    "migrated": frozenset(),
    "missing_alert_rules_table": frozenset(SCHEMA_CHECK_EXITS),
    "missing_alerts_table": frozenset(SCHEMA_CHECK_EXITS),
    "missing_department": frozenset(SCHEMA_CHECK_EXITS),
    "missing_status": frozenset(DISPOSAL_EXITS),
}

EXITS: list[tuple[str, str, str, dict | None]] = [
    ("read_ledger_list", "get", LEDGER, None),
    ("read_alert_detail", "get", DETAIL, None),
    ("read_rule_list", "get", RULES, None),
    ("read_manual_sweep", "post", CHECK, None),
    ("write_rule_create", "post", RULES, RULE_BODY),
    ("write_rule_delete", "delete", RULE_ONE, None),
    ("write_alert_ack", "post", f"{DETAIL}/ack", None),
    ("write_alert_close", "post", f"{DETAIL}/close", None),
    ("write_alert_assign", "post", f"{DETAIL}/assign", {"assignee": ADMIN}),
]
EXIT_IDS = [exit[0] for exit in EXITS]
ACK_EXIT = EXITS[EXIT_IDS.index("write_alert_ack")]

_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)
_ADD_COLUMN = re.compile(r"ADD COLUMN IF NOT EXISTS (\w+)", re.IGNORECASE)
_WANTED_COLUMN = re.compile(r"column_name = '(\w+)'", re.IGNORECASE)


class _Recorder:
    """把出口那两行日志留下来：三格能不能分辨、门有没有复用，今天只有这一处证据。"""

    def __init__(self):
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message, *args, **kwargs):
        self.warnings.append(str(message))

    def info(self, message, *args, **kwargs):
        self.infos.append(str(message))

    def debug(self, message, *args, **kwargs):
        self.infos.append(str(message))

    @property
    def exit_lines(self) -> list[str]:
        """转换那一行：只有出口层会说 `migration=`。"""
        return [line for line in self.warnings if "migration=" in line]

    @property
    def gate_lines(self) -> list[str]:
        """既有那道门那一行：证明转换走的是它，不是新开的第二道门。"""
        return [line for line in self.warnings if "code=" + STORAGE_CODE in line
                and "migration=" not in line]


class _Catalog:
    """只认「目录里有没有这一枚」的替身库：就地补的 DDL 真会把台账改厚（开发态自愈那一腿要它）。

    它不求值行级归属谓词（admin 那一档谓词为空），也不真执行任何 SQL。产品代码不读它。
    """

    def __init__(self, *, tables, columns, rules, rows, unreadable_after_write=False):
        self.tables = set(tables)
        self.columns = set(columns)
        self.rules = [dict(rule) for rule in rules]
        self.rows = [dict(row) for row in rows]
        self.unreadable_after_write = unreadable_after_write
        self.executed: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0
        self._result: list[dict] = []
        self._rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        arguments = tuple(params)
        self.executed.append((text, arguments))
        upper = text.upper()
        self._result = []
        self._rowcount = -1

        regclass = _REGCLASS.search(text)
        created = _CREATE_TABLE.search(text)
        added = _ADD_COLUMN.search(text)
        if regclass:
            name = regclass.group(1)
            self._result = [{"table_name": name}] if name in self.tables else []
        elif "INFORMATION_SCHEMA.COLUMNS" in upper:
            wanted = self._wanted_column(text, arguments)
            self._result = [{"column_name": wanted}] if wanted in self.columns else []
        elif upper.startswith("CREATE") and created:
            self.tables.add(created.group(1))
        elif upper.startswith("ALTER") and added:
            self.columns.add(added.group(1))
        elif upper.startswith("SELECT * FROM ALERT_RULES"):
            self._result = [dict(rule) for rule in self.rules]
        elif upper.startswith("INSERT INTO ALERT_RULES"):
            new_id = max([int(rule["id"]) for rule in self.rules], default=0) + 1
            self.rules.append({"id": new_id, "name": arguments[0], "metric": arguments[1],
                               "op": arguments[2], "threshold": arguments[3], "enabled": True})
            self._result = [{"id": new_id}]
        elif upper.startswith("DELETE FROM ALERT_RULES"):
            wanted = int(arguments[0])
            before = len(self.rules)
            self.rules = [rule for rule in self.rules if int(rule["id"]) != wanted]
            self._rowcount = before - len(self.rules)
        elif upper.startswith("SELECT * FROM ALERTS WHERE ID = %S"):
            wanted = int(arguments[0])
            rows = [dict(row) for row in self.rows if int(row["id"]) == wanted]
            if self.unreadable_after_write and "FOR UPDATE" not in upper:
                rows = []
            self._result = rows
        elif upper.startswith("SELECT * FROM ALERTS"):
            self._result = [dict(row) for row in self.rows]
        elif upper.startswith("UPDATE ALERTS"):
            self._rowcount = self._apply_update(text, arguments)
        else:
            raise AssertionError(f"替身库收到了本件预期之外的语句: {text}")
        return self

    @staticmethod
    def _wanted_column(text: str, arguments: tuple) -> str:
        literal = _WANTED_COLUMN.search(text)
        if literal:
            return literal.group(1)
        assert arguments, f"查列语句既没有字面量也没有参数: {text}"
        return str(arguments[0])

    def _apply_update(self, text: str, arguments: tuple) -> int:
        set_clause = text.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
        columns = re.findall(r"(\w+) = %s", set_clause)
        target = next((row for row in self.rows if int(row["id"]) == int(arguments[-1])), None)
        if target is None:
            return 0
        target.update(dict(zip(columns, arguments[:-1])))
        return 1

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)

    @property
    def rowcount(self):
        return self._rowcount

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    @property
    def statements(self) -> list[str]:
        return [text for text, _ in self.executed]


def _accounts() -> dict[str, dict]:
    return {
        ADMIN: {"id": "u-r371-admin", "username": ADMIN, "role": "admin", "department": ""},
        STAFF: {"id": "u-r371-staff", "username": STAFF, "role": "staff", "department": "r371"},
    }


def _headers(username: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _call(client: TestClient, exit: tuple, username: str | None = ADMIN):
    _label, method, path, body = exit
    kwargs = {} if username is None else {"headers": _headers(username)}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


def _wire(monkeypatch, cell: str, *, environment: str = "production",
          unreadable_after_write: bool = False):
    """把「库在、旗标 True、迁移没跑」这一格接成读数：R359 那道门开着，缺的是它下面那一层。"""
    from app.api.v1 import alerts
    from app.common import auth

    tables, columns = CATALOGS[cell]
    catalog = _Catalog(tables=tables, columns=columns, rules=[dict(RULE_ROW)],
                       rows=[dict(ALERT_ROW)], unreadable_after_write=unreadable_after_write)
    accounts = _accounts()
    recorder = _Recorder()

    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_initialized", False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_MEM_RULES", [])
    monkeypatch.setattr(alerts, "_conn", lambda: catalog)
    monkeypatch.setattr(alerts, "_alert_disposal_now", lambda: FIXED_TS)
    monkeypatch.setattr(alerts, "logger", recorder)
    # 巡检那一腿只借它「读本机数据」的两格：本件不判扫描口径（那是 R345）。
    monkeypatch.setattr(
        alerts, "_scan_data_files",
        lambda principal: ([], {"data_dir_configured": False,
                                "scoped_to_principal": principal is not None,
                                "evaluated_files": [], "reason": "no_data_files"}))
    monkeypatch.setattr(alerts, "_dataset_department_index", lambda: {})
    monkeypatch.setenv("APP_ENV", environment)
    return SimpleNamespace(alerts=alerts, catalog=catalog, logs=recorder,
                           client=TestClient(app))


# ============================================== 判据 1 + 6①：那张「每句 × 每出口」可达性表
@pytest.mark.parametrize("cell", CELLS, ids=CELLS)
@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_the_grid_answers_what_the_evidence_says(monkeypatch, cell, exit):
    """每枚出口 × 每格缺口逐一点名：该拒的一律 503 且不裸 500，不该拒的一律照常答话。

    🔴 不许笼统说「三句 RuntimeError 都会裸 500」：`read_manual_sweep` 那一格的 `_ensure()` 被
    `alerts.py:820` 的宽捕获吃掉（R345 钉它「永不上抛」），缺 `status` 那一格也只咬得住三条处置
    写口——前五枚读腿压根不查 `status`。这张表就是取证的落盘形状。
    """
    wired = _wire(monkeypatch, cell)
    response = _call(wired.client, exit)

    if exit[0] in REFUSED[cell]:
        assert response.status_code == 503, f"{cell} × {exit[0]} 还在交裸 500: {response.text}"
        assert response.json() == {"detail": STORAGE_CODE}, exit[0]
        assert len(wired.logs.exit_lines) == 1, wired.logs.warnings
    else:
        assert response.status_code == 200, f"{cell} × {exit[0]} 被误拒: {response.text}"
        assert not wired.logs.exit_lines, f"{cell} × {exit[0]} 不该说存储拒答: {wired.logs.warnings}"


@pytest.mark.parametrize("cell", BROKEN_CELLS, ids=BROKEN_CELLS)
def test_the_refusal_borrows_the_door_that_is_already_there(monkeypatch, cell):
    """零新增第二道门：转换把结论交给 R359 那枚闸，所以闸那行日志照旧在，码也照旧是它那一枚。"""
    wired = _wire(monkeypatch, cell)
    response = _call(wired.client, ACK_EXIT)

    assert response.status_code == 503, response.text
    assert len(wired.logs.gate_lines) == 1, wired.logs.warnings
    assert len(wired.logs.exit_lines) == 1, wired.logs.warnings
    assert STORAGE_CODE in wired.logs.gate_lines[0]


def test_the_refusal_code_is_the_one_the_repo_already_ships(monkeypatch):
    """判据 6②：断言 detail 字面值，且这枚码必须在 `ErrorEnvelope` 的封闭枚举里——不许只断状态码。"""
    wired = _wire(monkeypatch, "missing_status")
    response = _call(wired.client, ACK_EXIT)
    enum_codes = set(ErrorEnvelope.model_fields["code"].annotation.__args__)

    assert response.json()["detail"] == STORAGE_CODE
    assert STORAGE_CODE in enum_codes, "有人换了词：这枚码不在封闭枚举里"


# ============================================================ 判据 2：转换只做在出口那一层
@pytest.mark.parametrize("cell", BROKEN_CELLS, ids=BROKEN_CELLS)
def test_the_schema_layer_still_raises_runtime_error(monkeypatch, cell):
    """`_ensure()` 与 `_require_alert_disposal_schema()` 本身继续抛 RuntimeError（既有钉的家）。"""
    from fastapi import HTTPException

    wired = _wire(monkeypatch, cell)
    module = wired.alerts

    with pytest.raises(RuntimeError) as caught:
        if cell == "missing_status":
            module._require_alert_disposal_schema(wired.catalog)
        else:
            module._ensure()

    assert not isinstance(caught.value, HTTPException), "出口层的活干到了 schema 层：改别人的账"
    assert str(caught.value) == SENTENCES[cell]


def test_the_family_is_a_runtime_error_subclass_not_a_replacement():
    """判据 3 的后半：只加一层具名，不动基类语义（同 `pending_approvals.py:140` 那条裁定）。"""
    from app.api.v1 import alerts

    family = alerts.AlertSchemaNotMigratedError

    assert issubclass(family, RuntimeError)
    assert RuntimeError in family.__mro__
    assert family.__mro__.count(RuntimeError) == 1
    assert issubclass(family, Exception)


@pytest.mark.parametrize("cell", BROKEN_CELLS, ids=BROKEN_CELLS)
def test_each_cell_answers_the_named_sentence_verbatim(monkeypatch, cell):
    """判据 3：三句消息文本一个字不许改——既有紧钉 match 全文本，逐枚按 `str(exc)` 判等。"""
    wired = _wire(monkeypatch, cell)
    module = wired.alerts

    with pytest.raises(RuntimeError) as caught:
        if cell == "missing_status":
            module._require_alert_disposal_schema(wired.catalog)
        else:
            module._ensure()

    assert str(caught.value) == SENTENCES[cell], "同族那一句话被改口了"


# ==================================================== 判据 6③：三格两两可分辨，不许塌成一句话
@pytest.mark.parametrize("cell", BROKEN_CELLS, ids=BROKEN_CELLS)
def test_the_exit_log_names_the_migration_to_run(monkeypatch, cell):
    """503 的响应体三格共用（零新增错误码），能分辨三条排查路的只有出口那行日志。"""
    wired = _wire(monkeypatch, cell)
    _call(wired.client, ACK_EXIT)
    line = wired.logs.exit_lines[0]

    assert f"migration={EXPECTED_MIGRATION[cell]}" in line, line
    assert SENTENCES[cell] in line, f"出口日志没有原样带上那一句人话: {line}"


def test_the_three_cells_do_not_collapse_into_one_remedy(monkeypatch):
    """缺表 / 缺归属列 / 缺处置列 ⇒ 三枚迁移文件名两两不同；四格缺口 ⇒ 四句话两两不同。"""
    migrations = set()
    sentences = set()
    for cell in BROKEN_CELLS:
        wired = _wire(monkeypatch, cell)
        _call(wired.client, ACK_EXIT)
        line = wired.logs.exit_lines[0]
        migrations.add(re.search(r"migration=(\S+)", line).group(1))
        sentences.add(SENTENCES[cell])

    assert sentences == set(SENTENCES.values()), "四句话塌成了同一句"
    assert migrations == {
        "migrations/0003_legacy_runtime_tables.sql",
        "migrations/0012_alert_and_pending_approval_attribution_columns.sql",
        "migrations/0014_alert_disposal_columns.sql",
    }, f"三条排查路没有各自指名: {sorted(migrations)}"


# ================================================== 判据 1 的落点：拒在写之前，不留下半笔处置
def test_missing_status_refuses_before_anything_is_written(monkeypatch):
    """缺 `alerts.status` 时三条处置写口一枚都不许写：台账上不能留下谁都无法复核的处置。"""
    wired = _wire(monkeypatch, "missing_status")

    for path in (f"{DETAIL}/ack", f"{DETAIL}/close"):
        response = wired.client.post(path, headers=_headers(ADMIN))
        assert response.status_code == 503, f"{path}: {response.text}"

    assert wired.catalog.rows[0]["status"] == "open", "处置写到了没有 status 列的库上"
    assert not [sql for sql in wired.catalog.statements if sql.upper().startswith("UPDATE")], (
        wired.catalog.statements)
    assert wired.catalog.commits == 0


# ====================================================== 判据 4：窄捕获——别的 RuntimeError 不许洗白
def test_a_different_runtime_error_is_not_washed_into_the_storage_face(monkeypatch):
    """`_dispose_alert:662` 那句「写成了却读不回来」不是部署缺口：它必须照旧是裸的运行时错。

    这一枚就是宽捕获的反向钉：谁把出口改成 `except Exception` / `except RuntimeError`，
    这里当场从「逃逸」变成「503」，本枚必红（`tests/test_r371_the_conversion_is_narrow_and_stays_at_the_exit.py`
    另有同一条判据的源文形状钉）。
    """
    from app.api.v1 import alerts

    wired = _wire(monkeypatch, "migrated", unreadable_after_write=True)

    with pytest.raises(RuntimeError) as caught:
        _call(wired.client, ACK_EXIT)

    assert type(caught.value) is RuntimeError, "真 bug 被翻译成了 503：捕获写宽了"
    assert not isinstance(caught.value, alerts.AlertSchemaNotMigratedError)
    assert not wired.logs.exit_lines, wired.logs.warnings


# ============================================================ 判据 5：开发态一格都不许跟着改
def test_the_development_catalog_self_heals_instead_of_refusing(monkeypatch):
    """非生产 + 同一格「缺表缺列」：`_ensure()` 就地补 DDL 自愈，不答 503（分开的是两张脸）。"""
    wired = _wire(monkeypatch, "missing_alerts_table", environment="development")

    assert wired.alerts._ensure() is None
    assert wired.catalog.tables == BOTH_TABLES, wired.catalog.statements
    assert BOTH_COLUMNS <= wired.catalog.columns, wired.catalog.statements
    assert any(sql.upper().startswith("CREATE TABLE") for sql in wired.catalog.statements)
    assert any("ADD COLUMN IF NOT EXISTS department" in sql for sql in wired.catalog.statements)
    assert any("ADD COLUMN IF NOT EXISTS status" in sql for sql in wired.catalog.statements)
    assert wired.catalog.commits == 1
    assert not wired.logs.exit_lines


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_the_development_legs_still_answer_when_the_catalog_is_thin(monkeypatch, exit):
    """开发态九枚出口逐枚照常 200：本单只管生产那一支，没顺手把裸机打死。"""
    wired = _wire(monkeypatch, "missing_alert_rules_table", environment="development")
    response = _call(wired.client, exit)

    assert response.status_code == 200, f"{exit[0]} 在开发态被拒了: {response.text}"
    assert not wired.logs.exit_lines, wired.logs.warnings


# ================================== 可达性表里那一格「被宽捕获吃掉」的证据（不许当逃逸报）
def test_the_sweep_swallows_the_same_sentences_before_they_reach_the_exit(monkeypatch):
    """`check_now` 那一腿的 `_ensure()` 由 `alerts.py:820` 吃掉并退回内存规则（R345 的口径）。

    所以本单不在 `check_now` 上加转换：加了是假账。同一台机器在巡检这一格仍然会撞
    `alerts.py:857` 的驱动错——那不是这三句里的任何一句，已登记「只报不改」。
    """
    wired = _wire(monkeypatch, "missing_alert_rules_table")

    assert wired.alerts.evaluate_all(scan_summary={}) == []
    assert any("切换内存规则" in line for line in wired.logs.warnings), wired.logs.warnings
    assert not wired.logs.exit_lines, "巡检那一腿不该长出本单的转换"
    assert any("to_regclass" in sql for sql in wired.catalog.statements)


# ================================================ 先后不许反：401 / 403 永远在 503 之前
@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_an_anonymous_caller_never_meets_the_new_face(monkeypatch, exit):
    wired = _wire(monkeypatch, "missing_department")
    response = _call(wired.client, exit, username=None)

    assert response.status_code == 401, f"{exit[0]}: {response.text}"
    assert response.json()["detail"] == "authentication_required"
    assert not wired.logs.exit_lines


@pytest.mark.parametrize("exit", EXITS, ids=EXIT_IDS)
def test_a_staff_caller_gets_the_permission_answer_not_the_storage_answer(monkeypatch, exit):
    wired = _wire(monkeypatch, "missing_department")
    response = _call(wired.client, exit, username=STAFF)

    assert response.status_code == 403, f"{exit[0]}: {response.text}"
    assert response.json()["detail"] == "permission_denied"
    assert not wired.logs.exit_lines


# ============================================================ 正常那一格不许被本单一起打死
def test_the_migrated_catalog_still_disposes_normally(monkeypatch):
    """库在、迁移也跑过：确认照旧落库并读回 `acknowledged`——转换不是「生产一律 503」。"""
    wired = _wire(monkeypatch, "migrated")
    response = _call(wired.client, ACK_EXIT)

    assert response.status_code == 200, response.text
    assert response.json()["alert"]["status"] == "acknowledged"
    assert response.json()["alert"]["acknowledged_by"] == ADMIN
    assert wired.catalog.rows[0]["status"] == "acknowledged"
    assert wired.catalog.commits == 1
    assert not wired.logs.exit_lines
