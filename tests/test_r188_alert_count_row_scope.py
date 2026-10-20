"""R188 —— 看板那一格「异常与告警」的计数要跟告警台账同一份判定（改前先红，修完必绿）。

来历：R176 把「一条告警归谁读」做成行级判定，两腿同源
（``app/api/v1/alerts.py:171 alert_row_visible`` / ``:187 alert_row_scope_sql``），
``GET /alerts`` 接上了，看板的告警计数没接：``app/api/v1/dashboard.py:47`` 那条
``_ALERT_COUNT_SQL`` 数全表，``:91-95`` 那条内存腿同样数整个 ``_MEM_ALERTS``。
⇒ A 部门的 manager 打开工作台，「异常与告警」里印的是全公司的总数与未读数，而他点进告警屏
只看到自己那几条。**计数本身就是信息**：别部门今天出没出过事、积了几条没人看，一个数字就漏完
了，不需要任何正文字节出现在响应里。

本件只钉这一格，判定口径全部沿用 R176 已并树的那一份，一字不新增、也不在此处重写：

- 无归属行（``department`` 为 ``''`` 或 ``NULL``，以及归属列出现之前根本没有这一键的行）对已过
  资源级闸门的主体保持可见 —— 这是 ``alert_row_visible`` 的 docstring 立的口径，与
  ``app/common/policy.py`` 对「无主文档」同一条心智；
- 只有 administrator 那一腿不设行级条件（``alert_row_scope_departments`` 返回 ``None``）；
- 计数裁在 SQL 里而不是页外：先 ``LIMIT 100`` 再在 Python 里数长度，会把只有几条告警的部门读成
  一张空表 —— 与 ``alert_row_scope_sql`` 自己 docstring 立的理由同一条。

与 ``tests/test_dashboard_summary.py:297`` 那枚
``test_the_alert_count_counts_the_table_and_not_the_truncated_page`` 的关系要说清，否则后来人容易
把两件事当成互相打脸：那枚钉的是**分母不许来自哪儿**（不许是被 ``LIMIT 100`` 截断的那一页，所以
它故意让 ``total > len(listed)``）；本件钉的是**那个分母是谁的集合**（该主体可见的全集）。两者互相
成全：裁进行内的 ``COUNT(*)`` 既不是页长也不是全表，它正好等于 ``alert_row_visible`` 在同一组行上
判出来的那个全集 —— 本文件那枚 ``..._full_visible_set_and_not_the_delivered_page`` 就拿同一组行把
两件事同时钉住（可见全集 123、页只交 100）。

两条腿都给**真读数**：``_ScopedAlertConnection`` 是一台最小的 PostgreSQL 替身，它把送进来的 WHERE
逐字解析后真的作用在同一组行上，认不出的谓词形状当场抛错。所以「摘掉行级 WHERE」会让本文件的数字
自己变红，「另抄一份判定」要么被那台替身拒掉、要么被最后两枚唯一表守卫钉住 —— 不接受只钉源码文本。
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app

_REPOSITORY = Path(__file__).resolve().parents[1]

SUMMARY_PATH = "/api/v1/dashboard/summary"
ALERTS_PATH = "/api/v1/alerts"

DEPT_OWN = "r188-own"
DEPT_FX = "r188-fx"
#: A 部门刻意铺过一页：台账那条腿永远只交 100 行，跨过它才能把「全集」与「页长」分给两枚不同的
#: 断言去看，也才配得上 :297 那枚钉的口径。
OWN_ROWS = 120
FX_ROWS = 90
UNATTRIBUTED = (
    {"id": 901, "rule_id": 1, "message": "R188T-EMPTY 归属列写了空串", "read": False,
     "department": ""},
    {"id": 902, "rule_id": 1, "message": "R188T-NULL 归属列是 NULL", "read": True,
     "department": None},
    {"id": 903, "rule_id": 1, "message": "R188T-LEGACY 归属列出现之前的历史行", "read": False},
)
#: 两个部门各自的读数在这里写死（120 条里 30 条已读、90 条里 45 条已读、三条无归属里两条未读），
#: 不靠产品代码反推，也不靠本文件的谓词替身反推。
OWN_TOTAL = OWN_ROWS + len(UNATTRIBUTED)               # 123
OWN_UNREAD = 90 + 2                                    # 92
FX_TOTAL = FX_ROWS + len(UNATTRIBUTED)                 # 93
FX_UNREAD = 45 + 2                                     # 47
WHOLE_TOTAL = OWN_ROWS + FX_ROWS + len(UNATTRIBUTED)   # 213
WHOLE_UNREAD = 90 + 45 + 2                             # 137


def _account(username: str, department: str, role: str) -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


OWN_MANAGER = "r188-own-manager"
FX_MANAGER = "r188-fx-manager"
ADMINISTRATOR = "r188-administrator"
STAFF = "r188-own-staff"

ACCOUNTS = {
    OWN_MANAGER: _account(OWN_MANAGER, DEPT_OWN, "manager"),
    FX_MANAGER: _account(FX_MANAGER, DEPT_FX, "manager"),
    ADMINISTRATOR: _account(ADMINISTRATOR, "", "admin"),
    STAFF: _account(STAFF, DEPT_OWN, "staff"),
}


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _seed_rows() -> list[dict]:
    """两个部门各有一批告警，另加三条无归属行：``''`` / ``NULL`` / 根本没有这一键。"""
    rows = [
        {
            "id": index,
            "rule_id": 1,
            "message": f"R188T-OWN-{index} 部门 {DEPT_OWN} 的营收跌破阈值",
            "read": index % 4 == 0,
            "department": DEPT_OWN,
        }
        for index in range(1, OWN_ROWS + 1)
    ]
    rows += [
        {
            "id": 500 + index,
            "rule_id": 2,
            "message": f"R188T-FX-{index} 部门 {DEPT_FX} 的毛利跌破阈值",
            "read": index % 2 == 0,
            "department": DEPT_FX,
        }
        for index in range(1, FX_ROWS + 1)
    ]
    rows += [dict(row) for row in UNATTRIBUTED]
    return rows


def _oracle(rows: list[dict], departments: set[str] | None) -> dict:
    """本文件自己算的期望值：只读原始行的 department 字段，不借产品里那两枚函数。

    刻意不复用 ``alert_row_visible``，否则断言就成了自我论证：判定错了，期望值跟着一起错。
    """
    visible: list[dict] = []
    for row in rows:
        if departments is None:
            visible.append(row)
            continue
        raw = row.get("department")
        if raw is None:
            visible.append(row)
            continue
        claimed = {part.strip() for part in str(raw).split(",") if part.strip()}
        if not claimed or bool(claimed & departments):
            visible.append(row)
    return {
        "total": len(visible),
        "unread": sum(1 for row in visible if not row.get("read")),
    }

# 只有 alert_row_scope_sql 那一支谓词这台替身认得；形状对不上就是有人另抄了一份。
_CANONICAL_DISJUNCTS = (
    re.compile(r"^department IS NULL$"),
    re.compile(r"^department = ''$"),
    re.compile(r"^string_to_array\(department, ','\) && %s::text\[\]$"),
)
_LIMIT_RE = re.compile(r"\bLIMIT (\d+)\b", re.IGNORECASE)


class _ScopedAlertConnection:
    """最小的 PostgreSQL 替身：把送进来的语句真的作用在 rows 上，再返回读数。

    它只够回答本件那两条语句（``SELECT COUNT(*) ... FROM alerts [WHERE ...]`` 与
    ``SELECT * FROM alerts [WHERE ...] ORDER BY id DESC LIMIT 100``），并且**只认
    ``alert_row_scope_sql`` 生成的那三种析取支**。任何人把归属条件换成一枝新写法 —— 包括在
    dashboard 里另抄一份 —— 都会当场撞上 AssertionError，而不是被静默地当成「没裁」。
    """

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.statements: list[tuple[str, tuple | None]] = []
        self._one: dict | None = None
        self._many: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    # ---------------------------------------------------------------- 认谓词那一小段
    def _departments(self, predicate: str, params: tuple | None) -> set[str] | None:
        body = predicate.strip()
        if not body:
            return None
        assert body.upper().startswith("WHERE"), (
            "归属条件没有跟在 FROM alerts 后面，这条计数本替身不认：" + predicate
        )
        body = body[len("WHERE"):].strip()
        assert body.startswith("(") and body.endswith(")"), (
            "行级判定的 SQL 形状只有那一支，出现别的就是第二份定义：" + predicate
        )
        disjuncts = [part.strip() for part in body[1:-1].split(" OR ")]
        recognised = [
            part for part in disjuncts if any(rx.match(part) for rx in _CANONICAL_DISJUNCTS)
        ]
        assert len(recognised) == len(disjuncts) == 3, (
            "看板这条计数用了 alerts.alert_row_scope_sql 之外的归属谓词：" + predicate
        )
        assert params and len(params) == 1, "谓词要求一枚部门数组参数：" + repr(params)
        return {str(value) for value in params[0]}

    @staticmethod
    def _matches(row: dict, departments: set[str] | None) -> bool:
        if departments is None:
            return True
        raw = row.get("department")
        if raw is None:
            return True
        claimed = {part.strip() for part in str(raw).split(",") if part.strip()}
        return not claimed or bool(claimed & departments)

    # ---------------------------------------------------------------- 执行那一小段
    def execute(self, sql: str, params: tuple | None = None):
        self.statements.append((sql, params))
        assert "FROM alerts" in sql, "这台替身只管 alerts 表：" + sql
        tail = sql.split("FROM alerts", 1)[1]
        order_at = tail.upper().find(" ORDER BY")
        predicate = tail if order_at == -1 else tail[:order_at]
        suffix = "" if order_at == -1 else tail[order_at:]
        visible = [
            row for row in self.rows if self._matches(row, self._departments(predicate, params))
        ]

        self._one = None
        self._many = []
        if "COUNT(" in sql.upper():
            self._one = {
                "total": len(visible),
                "unread": sum(1 for row in visible if not row.get("read")),
            }
            return self
        limit = _LIMIT_RE.search(suffix or sql)
        assert limit, "台账那条腿应当带页边界：" + sql
        ordered = sorted(visible, key=lambda row: int(row["id"]), reverse=True)
        self._many = ordered[: int(limit.group(1))]
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return [dict(row) for row in self._many]

    def commit(self):
        return None


def _no_connection():
    raise AssertionError("内存那一腿不该向数据库要连接")


@pytest.fixture()
def ledger(monkeypatch):
    """离线台账 + 只服务本件的其余两格：文档与数据集目录钉成空，本件只钉告警那一格。"""
    from app.api.v1 import alerts, chat, data
    from app.common import auth
    from app.storage import pending_approvals as store

    rows = _seed_rows()
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", rows)
    monkeypatch.setattr(alerts, "_conn", _no_connection)
    monkeypatch.setattr(store, "_database_available", lambda: False)
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))

    async def _no_documents(request):
        return {"documents": []}

    async def _no_files(request=None):
        return {"files": []}

    monkeypatch.setattr(chat, "list_document_catalog", _no_documents)
    monkeypatch.setattr(data, "list_data_files", _no_files)
    return SimpleNamespace(alerts=alerts, rows=rows, client=TestClient(app), mp=monkeypatch)


def _memory_leg(ledger) -> None:
    """显式钉住内存那一腿，并且把连接缝换成会炸的桩：两腿不许互相冒充。"""
    ledger.mp.setattr(ledger.alerts, "_database_available", lambda: False)
    ledger.mp.setattr(ledger.alerts, "_conn", _no_connection)


def _sql_leg(ledger, rows: list[dict] | None = None) -> _ScopedAlertConnection:
    """把告警存储换到 PostgreSQL 那一腿，后端是真会裁行的替身。"""
    connection = _ScopedAlertConnection(ledger.rows if rows is None else rows)
    ledger.mp.setattr(ledger.alerts, "_database_available", lambda: True)
    ledger.mp.setattr(ledger.alerts, "_initialized", True)
    ledger.mp.setattr(ledger.alerts, "_conn", lambda: connection)
    return connection


def _tile(client, username: str) -> dict:
    response = client.get(SUMMARY_PATH, headers=_headers(username))
    assert response.status_code == 200, response.text
    body = response.json()
    assert "alerts" in body, f"已过资源级闸门却整个没有这一格：{sorted(body)}"
    return body["alerts"]


def _count_statements(connection: _ScopedAlertConnection) -> list[tuple[str, tuple | None]]:
    return [
        (sql, params) for sql, params in connection.statements if "COUNT(" in sql.upper()
    ]

# ================== 判据①②：两条腿都要裁，而且裁在 SQL 里而不是页外 ==================


def test_the_manager_tile_counts_his_own_department_and_the_unattributed_rows(ledger):
    """判据①/④③：内存腿数的是「本部门 + 无归属」，不是全表。

    改前的产品证据：``dashboard.py:91-95`` 直接 ``len(_MEM_ALERTS)`` ⇒ 这一格会拿到
    ``{"total": 213, "unread": 137}``，比 A 部门自己的可见全集多出 B 部门那 90 条。
    """
    _memory_leg(ledger)

    tile = _tile(ledger.client, OWN_MANAGER)

    assert tile == _oracle(ledger.rows, {DEPT_OWN})
    assert tile == {"total": OWN_TOTAL, "unread": OWN_UNREAD}
    assert tile != {"total": WHOLE_TOTAL, "unread": WHOLE_UNREAD}, (
        "计数仍是全表口径：别部门的告警条数与积压未读数从这一格漏了出去"
    )


def test_two_managers_do_not_share_one_number_over_the_same_rows(ledger):
    """同一组行、两个部门、两个数字：行级口径真按读者分叉，而不是只把 B 裁给 A。"""
    _memory_leg(ledger)

    own = _tile(ledger.client, OWN_MANAGER)
    other = _tile(ledger.client, FX_MANAGER)

    assert own == {"total": OWN_TOTAL, "unread": OWN_UNREAD}
    assert other == {"total": FX_TOTAL, "unread": FX_UNREAD}
    assert own["total"] > other["total"] and own["unread"] > other["unread"]


def test_the_tile_counts_the_full_visible_set_and_not_the_delivered_page(ledger):
    """判据②：total 是可见全集（123），页只交 100 条 —— 与 :297 那枚钉同一条规矩的两端。

    那枚钉说「分母不许来自被截断的页」，本枚说「那个分母得是该主体可见的全集」。两件事同时为真
    才叫一致：只看那枚，全表口径也能绿；只看本枚，把一页取回来数长度也能绿。
    """
    _memory_leg(ledger)

    tile = _tile(ledger.client, OWN_MANAGER)
    listed = ledger.client.get(ALERTS_PATH, headers=_headers(OWN_MANAGER)).json()["alerts"]

    assert len(listed) == 100, "台账那一腿的页边界是既端口径，本件不许动它"
    assert tile["total"] == OWN_TOTAL > len(listed), (
        "把被截断的页长当成总数，就是看起来是对的的那类错"
    )


def test_the_sql_leg_cuts_the_row_scope_into_the_count(ledger):
    """判据①②：有库那一腿把归属条件裁进 COUNT(*)，并且计数语句里没有页边界。"""
    connection = _sql_leg(ledger)

    tile = _tile(ledger.client, OWN_MANAGER)

    assert tile == {"total": OWN_TOTAL, "unread": OWN_UNREAD}, tile
    counts = _count_statements(connection)
    assert len(counts) == 1, counts
    sql, params = counts[0]
    assert "string_to_array(department" in sql, "计数没裁归属，等于把全表数给他：" + sql
    assert params and list(params[0]) == [DEPT_OWN], f"归属参数没带上调用者的部门：{params!r}"
    assert all("LIMIT" not in item.upper() for item, _ in counts), (
        "计数读了一页回来数长度：" + sql
    )
    assert not [
        item for item, _ in connection.statements if item.lstrip().upper().startswith("SELECT *")
    ], "看板这条腿只该要一个数，不该向台账要行"


def test_the_administrator_tile_is_the_whole_table_and_carries_no_predicate(ledger):
    """判据④②：administrator 仍是全量数，而且那一腿压根不该出现归属条件（豁免不许扩大）。"""
    _memory_leg(ledger)
    offline = _tile(ledger.client, ADMINISTRATOR)

    connection = _sql_leg(ledger)
    online = _tile(ledger.client, ADMINISTRATOR)

    assert offline == online == {"total": WHOLE_TOTAL, "unread": WHOLE_UNREAD}
    counts = _count_statements(connection)
    assert len(counts) == 1, counts
    sql, params = counts[0]
    assert "department" not in sql, "管理员那一腿被加上了行级条件：" + sql
    assert params in (None, ()), f"管理员那一腿不该带归属参数：{params!r}"


@pytest.mark.parametrize(
    "username,expected",
    [
        (OWN_MANAGER, {"total": OWN_TOTAL, "unread": OWN_UNREAD}),
        (FX_MANAGER, {"total": FX_TOTAL, "unread": FX_UNREAD}),
        (ADMINISTRATOR, {"total": WHOLE_TOTAL, "unread": WHOLE_UNREAD}),
    ],
)
def test_both_legs_answer_the_same_number_on_the_same_rows(ledger, username, expected):
    """判据④④：两腿同源 —— 同一组行、同一主体，内存腿与 SQL 腿交出同一个真读数。"""
    _memory_leg(ledger)
    offline = _tile(ledger.client, username)

    connection = _sql_leg(ledger)
    online = _tile(ledger.client, username)

    assert offline == online == expected, (username, offline, online)
    departments = None if username == ADMINISTRATOR else {ACCOUNTS[username]["department"]}
    assert offline == _oracle(ledger.rows, departments)
    assert _count_statements(connection), "SQL 腿没有真的发出计数语句"


def test_the_unattributed_rows_stay_counted_for_a_scoped_reader(ledger):
    """判据④③：无归属行对过了资源级闸门的主体保持可见 —— ``''``、``NULL``、历史行三条都算。

    这是 ``alert_row_visible`` 的 docstring 立的口径（与 ``app/common/policy.py`` 对无主文档同
    一条心智），本件不许自作主张收紧成「只有本部门才看得见」。
    """
    unattributed = [row for row in ledger.rows if not str(row.get("department") or "")]
    assert len(unattributed) == 3
    _memory_leg(ledger)
    ledger.mp.setattr(ledger.alerts, "_MEM_ALERTS", unattributed)

    for username in (OWN_MANAGER, FX_MANAGER):
        tile = _tile(ledger.client, username)
        listed = ledger.client.get(ALERTS_PATH, headers=_headers(username)).json()["alerts"]

        assert tile == {"total": 3, "unread": 2}, (username, tile)
        assert len(listed) == tile["total"], "计数与列表在这一格上必须一字不差"

    connection = _sql_leg(ledger, unattributed)
    assert _tile(ledger.client, OWN_MANAGER) == {"total": 3, "unread": 2}
    assert "department IS NULL" in _count_statements(connection)[0][0]


# ==================== 资源级那道门：加了行级之后口径不许被带偏 ====================


def test_a_staff_caller_still_gets_no_key_after_the_row_scope_landed(ledger):
    """行级这层挂上去之后，staff 那一格照样整个消失，不是变成一个 0（:239-241 的口径）。"""
    response = ledger.client.get(SUMMARY_PATH, headers=_headers(STAFF))

    assert response.status_code == 200
    body = response.json()
    assert "alerts" not in body, "无权限与没有告警混成一个 0 就是假健康"
    assert not [key for key in body if "alert" in key.lower()], "换个键名绕过判定同样是后门"


def test_the_gate_is_still_the_first_call_and_still_sees_the_live_request(ledger):
    """那道门仍然只问一次、仍然拿到活 Request：取 principal 时不许顺手把它挪位或喂 None。"""
    from app.api.v1 import alerts

    seen: list = []
    real = alerts._require_alert_management

    def spy(request):
        seen.append(request)
        return real(request)

    ledger.mp.setattr(alerts, "_require_alert_management", spy)
    _memory_leg(ledger)

    assert _tile(ledger.client, OWN_MANAGER) == {"total": OWN_TOTAL, "unread": OWN_UNREAD}
    assert len(seen) == 1, seen
    assert seen[0] is not None, "行级判定要靠门返回的那个 Principal，不许退回离线那条捷径"


# ======================= 唯一表 / 唯一通路（仓库级硬规矩） =======================


def test_the_alert_row_scope_predicates_are_defined_exactly_once():
    """``alert_row_visible`` / ``alert_row_scope_sql`` 的定义只许有 alerts.py 那一处。

    写法照 ``tests/test_r64_row_scope_error_codes.py`` 那枚唯一表守卫：数命中文件，不数注释里
    提了几次。上一班就有人在自己树上全绿、进主树被这枚规矩当场钉红。
    """
    definitions = {}
    for name in ("def alert_row_visible", "def alert_row_scope_sql"):
        definitions[name] = [
            path.relative_to(_REPOSITORY).as_posix()
            for path in sorted((_REPOSITORY / "app").rglob("*.py"))
            if name in path.read_text(encoding="utf-8")
        ]

    assert definitions == {
        "def alert_row_visible": ["app/api/v1/alerts.py"],
        "def alert_row_scope_sql": ["app/api/v1/alerts.py"],
    }, f"行级判定长出了第二处定义：{definitions}"


def test_the_dashboard_module_carries_no_second_copy_of_the_department_comparison():
    """判据①/反证(b)的常抓手：``dashboard.py`` 里不许长出第二份行级判定，只许 import 那两枚。

    抄一份归属条件绕不开下面这些 token 里的某一个（SQL 侧的形状、Python 侧的部门集合与管理员
    豁免）。正向同时钉住它确实在用那两枚判定 —— 只 import 不用、把返回值丢掉自己数，同样红。
    """
    source = (
        (_REPOSITORY / "app" / "api" / "v1" / "dashboard.py").read_text(encoding="utf-8").lower()
    )

    for token in (
        "string_to_array",
        "department is null",
        "department = ''",
        "alert_department_separator",
        "alert_row_scope_departments",
        "_principal_departments",
        "_split_departments",
        "department_ids",
        "is_administrator",
    ):
        assert token not in source, f"dashboard.py 里出现了行级判定的第二份痕迹：{token}"

    for name in ("alert_row_visible", "alert_row_scope_sql"):
        assert name in source, f"看板这条计数没有复用 alerts 的那两枚判定：{name}"