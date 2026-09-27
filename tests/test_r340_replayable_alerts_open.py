# -*- coding: utf-8 -*-
"""R340 · ``alerts_open`` 改成可回放口径：判据甲 / 乙 / 丙 / 丁 / 戊 / 己 / 庚。

病灶（``app/api/v1/dashboard.py`` 旧 docstring 自己承认的那件事）：这一格数的是「那一档新增的行里，
到**本次请求这一刻** status 还是 open 的」。把一个当下投影画在既往时间轴上，于是这张图不可回放 ——
上周那根柱子本来 3 枚没处置，我今天点一下「确认」，上周的柱子自己矮下去，而屏幕上没有任何一处说
过「这一格会被未来改写」。员工读出来的是「上周还剩 3 件没处理」，这句话当天就是假的了。

本件换口径，七条各钉各的：

- **甲** 新谓词逐字写在 ``_alert_open_at``：「该档新增、且到**该档结束那一刻**仍未处置」。四格边界
  各有具名钉（档内确认 / 档后才确认 / 从未处置 / 已关闭按处置时间）。🔴 转派不算处置。
- **乙** 服务端与契约、前端那一格的口**同一笔**改：列名 ``alerts_open`` 一字不动，不新增并列列，
  屏上不许留着「按这次请求时刻」这种话。
- **丙** 两条腿同一把谓词：PG 腿只是行来源不同，处置时间跟着 ``SELECT`` 一起读回来，比较在
  ``_alert_open_at`` 里做。本件**不引入第二套时间解析**（SQL 里不许长进 ``date_trunc``/``NOW()``），
  也不把 SQL 腿搬回 Python 另算一份 —— 分桶本来就在 Python，两腿共用。
- **丁** 0014 之前的老行仍由 ``alerts.alert_row_status`` 定脸，本模块零第二份 status 判定；
  ``acknowledged_at`` 空串、``NULL``、键整个缺席是同一种形状，两腿都不许为此报错。
- **戊** R342 的守恒式（``sum(各桶) + undated == 同一人可见行数``）一字不放松；新列另给自己钉
  「任何一档不许超过它自己的行数」与「求和被同一个可见行数封顶」。
- **己** ``undated`` 那一格**没有跟着变**：无期间的行没有「该档结束那一刻」可言，仍按当下算，
  契约把这一格为什么只能按今日写明了。
- **庚** 零新增错误码，422/503 三张脸语义不动；处置时钟读不出时退回当下读法，不新开拒答。

世界与夹具直接取自 ``tests/test_r332_dashboard_trend.py``（含三枚 autouse 桩），PG 腿的替身沿用
``tests/test_r188_alert_count_row_scope.py`` 的手法：**只认 ``alert_row_scope_sql`` 生成的那三种析取支**，
并且按 ``SELECT`` 清单逐列投影 —— 少读一列就少一个键，两腿的等号当场红。
"""
from __future__ import annotations

import ast
import re
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.agents.contracts import Principal

import pytest

from tests.test_r332_dashboard_trend import (  # noqa: F401  (夹具是导入进来的，不是复制的)
    SHANGHAI,
    SUMMARY_PATH,
    _headers,
    _month_label,
    _now,
    _series,
    _shanghai_instants,
    _trend,
    _week_label,
    accounts,
    client,
    dataset_store,
    document_store,
    memory_alerts,
    offline_catalog,
    seed_alerts,
)

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "app" / "api" / "v1" / "dashboard.py"
ALERTS_MODULE = REPO / "app" / "api" / "v1" / "alerts.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
LIB = REPO / "frontend" / "src" / "lib" / "dashboard.js"
PANEL = REPO / "frontend" / "src" / "components" / "DashboardPanel.vue"
ALERT_LEDGER_PATH = "/api/v1/alerts"

#: 本件的锚点：口径、守恒式与错误码账全部对着这一版比，不抄今天的读数。
BASE = "e9aac2f"

#: 新列在响应里唯一合法的名字（判据乙：不许改名、不许删、不许加第二枚并列列）。
BUCKET_KEYS = {"bucket", "start", "documents", "documents_ready", "datasets", "alerts",
               "alerts_open"}


# ------------------------------------------------------------------ 日历（测试自己算一遍）


def _prev_month_anchor(hour: int = 9) -> datetime:
    """上一个月里稳当的一天：本档 1 号往回 29 天必然是上一档的最后几天，再钉到 2 号。

    月长 28/30/31 都会落在上一档内，所以这一枚锚点与今天是几号无关。
    """
    cursor = _now().replace(day=1, hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=29)
    return cursor.replace(day=2, hour=hour, minute=0, second=0, microsecond=0)


def _two_months_back_anchor(hour: int = 9) -> datetime:
    cursor = _prev_month_anchor(hour).replace(day=1) - timedelta(days=29)
    return cursor.replace(day=2, hour=hour, minute=0, second=0, microsecond=0)


def _week_anchor(back: int = 1, hour: int = 9) -> datetime:
    """本周起点往前 ``back`` 个整周的那一天 —— 周档的终点就是本档起点（周一 00:00）。"""
    this_week = _now().replace(hour=hour, minute=0, second=0, microsecond=0)
    this_week -= timedelta(days=this_week.weekday())
    return this_week - timedelta(days=7 * back)


def _created(value: datetime) -> str:
    """``alerts.py:825`` 那条腿写进 ``created_at`` 的形状：上海墙上时间，裸的。"""
    return value.replace(tzinfo=None).isoformat(timespec="seconds")


def _stamp(value: datetime) -> str:
    """``alerts._alert_disposal_now()`` 写处置时间的形状：同一枚墙上时间，带 ``+08:00``。"""
    return value.replace(tzinfo=SHANGHAI).isoformat(timespec="seconds")


@pytest.fixture()
def alarm(seed_alerts):
    """在内存台账上落一行，并能把处置三列摆成任意形状（包括整个缺键）。

    行形状取自 ``tests/test_r332_dashboard_trend.py::seed_alerts``，也就是
    ``alerts.py:817-828`` 真实写下的那一套键。
    """
    from app.api.v1 import alerts

    def add(message: str, *, created_at: str, status: str = "open", department: str = "finance",
            acknowledged_at: str | None = "", closed_at: str | None = "",
            assigned_at: str | None = "", assignee: str = "",
            strip: tuple[str, ...] = ()) -> dict:
        seed_alerts(message, created_at=created_at, department=department, status=status)
        row = alerts._MEM_ALERTS[-1]
        # ``None`` 是真的 NULL（PG 交回的形状），``strip=`` 才是「这一列整个不在行上」——
        # 判据丁要求这两件事与空串一起回同一个数。
        row["acknowledged_at"] = acknowledged_at
        row["closed_at"] = closed_at
        row["assigned_at"] = assigned_at
        for column in strip:
            row.pop(column, None)
        if assignee:
            row["assignee"] = assignee
            row["assigned_by"] = "finance-manager"
        return row

    return add


# ------------------------------------------------------------------ PG 腿的替身（判据丙）


#: 只认 ``alerts.alert_row_scope_sql`` 生成的那三种析取支；换一份写法就是第二份归属判定，当场炸。
_CANONICAL_DISJUNCTS = (
    re.compile(r"^department IS NULL$"),
    re.compile(r"^department = ''$"),
    re.compile(r"^string_to_array\(department, ','\) && %s::text\[\]$"),
)


class _AlertTable:
    """最小的 PostgreSQL 替身：认归属谓词、按 ``SELECT`` 清单投影，别的语句一概不认。

    投影这件事是有意为之：这一腿少了哪一列，交回的行就少哪一个键，内存腿却还带着它 ——
    「两条腿同一把谓词」这句话于是不能被 docstring 说，只能被等号钉量出来。
    """

    #: SQL 里一旦长出时间解析，这一腿就与离线腿各拿一把尺（判据丙）。替身先当场拒。
    _FORBIDDEN = ("date_trunc", "at time zone", "now()", "current_date", "current_timestamp",
                  "to_timestamp", "extract(", "::date", "::timestamp", "interval ")

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.statements: list[tuple[str, tuple | None]] = []
        self._many: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def _departments(self, predicate: str, params: tuple | None) -> set[str] | None:
        body = predicate.strip()
        if not body:
            return None
        assert body.upper().startswith("WHERE"), "归属条件没跟在 FROM alerts 后面：" + predicate
        body = body[len("WHERE"):].strip()
        disjuncts = [part.strip() for part in body[1:-1].split(" OR ")]
        recognised = [p for p in disjuncts if any(rx.match(p) for rx in _CANONICAL_DISJUNCTS)]
        assert len(recognised) == len(disjuncts) == 3, (
            "trend 这条腿用了 alert_row_scope_sql 之外的归属谓词：" + predicate)
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

    def execute(self, sql: str, params: tuple | None = None):
        self.statements.append((sql, params))
        assert "FROM alerts" in sql, "这台替身只管 alerts 表：" + sql
        head, tail = sql.split("FROM alerts", 1)
        head = head.strip()
        assert head.upper().startswith("SELECT"), sql
        columns = [part.strip() for part in head[len("SELECT"):].split(",")]
        assert "*" not in columns, "这一腿按列名读行，SELECT * 会把缺席伪装成在场：" + sql
        lowered = sql.lower()
        for banned in self._FORBIDDEN:
            assert banned not in lowered, f"SQL 腿长出了第二套时间解析（{banned}）：" + sql
        visible = [r for r in self.rows if self._matches(r, self._departments(tail, params))]
        self._many = [{column: row.get(column) for column in columns} for row in visible]
        return self

    def fetchall(self):
        return [dict(row) for row in self._many]


def _sql_leg(alerts_module, rows: list[dict], monkeypatch) -> _AlertTable:
    """把告警存储搬到 PostgreSQL 那一腿，后端是真会裁行、真会投影的替身。"""
    table = _AlertTable(rows)
    monkeypatch.setattr(alerts_module, "_database_available", lambda: True)
    monkeypatch.setattr(alerts_module, "_initialized", True)
    monkeypatch.setattr(alerts_module, "_conn", lambda: table)
    return table


def _memory_leg(alerts_module, monkeypatch) -> None:
    """显式钉住内存那一腿，并把连接缝换成会炸的桩：两腿不许互相冒充。"""
    def _boom():
        raise AssertionError("内存那一腿不该向数据库要连接")

    monkeypatch.setattr(alerts_module, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_module, "_conn", _boom)


def _body(client, username: str = "finance-manager", **params) -> dict:
    response = _trend(client, username, **params)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------- 判据甲 · 四格边界，各一枚具名钉


def test_edge_one_acknowledged_inside_the_bucket_drops_out(client, alarm):
    """① 在该档内被确认 ⇒ 这一档不算它。"""
    from app.api.v1 import alerts

    created = _prev_month_anchor(9)
    alarm("上月内就确认了", created_at=_created(created), status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(_prev_month_anchor(15)))

    bucket = _series(_body(client))[_month_label(created.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (1, 0)


def test_edge_two_acknowledged_after_the_bucket_still_counts(client, alarm):
    """② 在该档之后才被确认 ⇒ 该档仍算它 —— 今天丢掉的那一件事。"""
    from app.api.v1 import alerts

    created = _prev_month_anchor(9)
    row = alarm("上月那件今天才确认", created_at=_created(created),
                status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=_stamp(_now()))

    bucket = _series(_body(client))[_month_label(created.date())]

    # 当下读法会答 0（那一行今天的状态已经不是 open），可回放读法答 1。
    assert alerts.alert_row_status(row) == alerts.ALERT_STATUS_ACKNOWLEDGED
    assert (bucket["alerts"], bucket["alerts_open"]) == (1, 1)


def test_edge_three_never_disposed_counts(client, alarm):
    """③ 从未被处置 ⇒ 算它。"""
    created = _prev_month_anchor(9)
    alarm("上月那件到今天没人碰", created_at=_created(created))

    bucket = _series(_body(client))[_month_label(created.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (1, 1)


def test_edge_four_closed_is_read_from_closed_at(client, alarm):
    """④ 已关闭 ⇒ 与 ①/② 同判，只是看 ``closed_at``。"""
    from app.api.v1 import alerts

    created = _prev_month_anchor(9)
    alarm("上月内就关掉了", created_at=_created(created), status=alerts.ALERT_STATUS_CLOSED,
          closed_at=_stamp(_prev_month_anchor(15)))
    alarm("上月那件今天才关", created_at=_created(created), status=alerts.ALERT_STATUS_CLOSED,
          closed_at=_stamp(_now()))

    bucket = _series(_body(client))[_month_label(created.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (2, 1)


def test_a_row_acknowledged_then_closed_replays_from_the_earlier_stamp(client, alarm):
    """处置时钟取两枚里**更早**的那一枚：先确认后关闭的行不该在确认之前还被算成未处置。

    拿「与当前 status 相配的那一列」当答案会数错：这一行今天 status 是 ``closed``，只看
    ``closed_at`` 会让两月前那一格一直把它画成未处置，而它两月前当天就有人应过了。
    """
    from app.api.v1 import alerts

    edge = _two_months_back_anchor(9)
    alarm("两月前当天就确认", created_at=_created(edge), status=alerts.ALERT_STATUS_CLOSED,
          acknowledged_at=_stamp(edge.replace(hour=18)), closed_at=_stamp(_now()))
    alarm("两月前挂着，上月才确认", created_at=_created(edge), status=alerts.ALERT_STATUS_CLOSED,
          acknowledged_at=_stamp(_prev_month_anchor(9)), closed_at=_stamp(_now()))

    bucket = _series(_body(client))[_month_label(edge.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (2, 1)


def test_a_reassignment_is_not_a_disposal(client, alarm):
    """🔴 转派不算处置：派出去说的是「现在归他」，不是「有人决定了」。"""
    created = _prev_month_anchor(9)
    alarm("上月派出去了，没人处理", created_at=_created(created),
          assigned_at=_stamp(_prev_month_anchor(15)), assignee="finance-staff")

    bucket = _series(_body(client))[_month_label(created.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (1, 1)


def test_the_disposal_clock_excludes_the_assignment_column():
    """本模块用哪两列当时钟，是从 ``alerts.py`` 的写集派生的，不是抄的。"""
    from app.api.v1 import alerts, dashboard

    columns = set(dashboard._ALERT_DISPOSAL_MOMENT_COLUMNS)
    assignment = set(alerts.ALERT_DISPOSAL_WRITE_COLUMNS[alerts.ALERT_ACTION_ASSIGN])
    stamps = {column for action, written in alerts.ALERT_DISPOSAL_WRITE_COLUMNS.items()
              for column in written if column in alerts.ALERT_DISPOSAL_DEFAULTS
              and alerts.ALERT_DISPOSAL_DEFAULTS[column] == ""}

    assert columns <= stamps, f"时钟列不在处置写集里：{sorted(columns - stamps)}"
    assert not columns & assignment, f"转派列被当成了处置：{sorted(columns & assignment)}"
    assert columns == {"acknowledged_at", "closed_at"}


# ------------------------------------------------------------- 症状本身：图不许改写自己


def test_acknowledging_today_does_not_rewrite_any_closed_bucket(client, alarm):
    """判据甲要的那件事：今天点一枚「确认」，既往每一档的每一格逐字不变。

    旧口径下这一条必红：被确认的那一行住在两月前那一档，那一档的 ``alerts_open`` 会跟着矮 1。
    """
    from app.api.v1 import alerts

    oldest = _two_months_back_anchor(9)
    for day in (oldest, _prev_month_anchor(9), _now().replace(hour=8)):
        alarm("未处置的告警", created_at=_created(day))
    before = _body(client)

    target = alerts._MEM_ALERTS[0]
    target["status"] = alerts.ALERT_STATUS_ACKNOWLEDGED
    target["acknowledged_by"] = "finance-manager"
    target["acknowledged_at"] = _stamp(_now())

    after = _body(client)

    def shape(body):
        return [(point["bucket"], point["alerts"], point["alerts_open"]) for point in
                body["series"]]

    assert shape(after) == shape(before), "点「确认」改写了既往那几格"
    assert alerts.alert_row_status(target) == alerts.ALERT_STATUS_ACKNOWLEDGED
    assert _series(after)[_month_label(oldest.date())]["alerts_open"] == 1, "回放把未处置数丢了"


def test_the_current_bucket_is_still_the_present_open_count(client, alarm):
    """最新那一档还没结束，它的端点是当下：这一格与总览那枚「仍未处置」必须同数。"""
    from app.api.v1 import alerts

    inside, before_edge = _shanghai_instants()
    current = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    alarm("本月新告警甲", created_at=_created(inside))
    alarm("本月新告警乙", created_at=_created(inside))
    alarm("本月内就确认了", created_at=_created(inside), status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(inside + timedelta(hours=1)))
    alarm("上月那件今天确认", created_at=_created(before_edge),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=_stamp(_now()))

    bucket = _series(_body(client))[_month_label(current.date())]
    label = _month_label(current.date())
    present_open = sum(
        1 for row in alerts._MEM_ALERTS
        if alerts.alert_row_status(row) == alerts.ALERT_STATUS_OPEN
        and _month_label(datetime.fromisoformat(row["created_at"]).date()) == label
    )

    assert bucket["alerts_open"] == present_open == 2


def test_the_week_buckets_replay_from_their_own_monday_edge(client, alarm):
    """周档的端点是下周一 00:00，半开区间：正好落在边上的处置属于下一档。"""
    from app.api.v1 import alerts

    edge = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    edge -= timedelta(days=edge.weekday())
    sunday = edge - timedelta(days=1)
    alarm("周日里就确认了", created_at=_created(sunday.replace(hour=10)),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(sunday.replace(hour=18)))
    alarm("周日挂到周一整点才确认", created_at=_created(sunday.replace(hour=10)),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=_stamp(edge))

    series = _series(_body(client, period="week"))

    assert series[_week_label(sunday.date())]["alerts"] == 2
    assert series[_week_label(sunday.date())]["alerts_open"] == 1, "处置落在档边上就不算跨过去了"


# --------------------------------------------------------------- 判据丙 · 两条腿一把谓词


def _world_all_open(alarm, alerts):
    oldest, previous, current = _two_months_back_anchor(), _prev_month_anchor(), _now()
    alarm("两月前", created_at=_created(oldest))
    alarm("上月", created_at=_created(previous))
    alarm("本月", created_at=_created(current.replace(hour=8)))


def _world_mixed_disposal(alarm, alerts):
    oldest, previous = _two_months_back_anchor(), _prev_month_anchor()
    alarm("两月前当天就确认", created_at=_created(oldest),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(oldest.replace(hour=18)))
    alarm("两月前挂到今天", created_at=_created(oldest),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=_stamp(_now()))
    alarm("上月关闭", created_at=_created(previous), status=alerts.ALERT_STATUS_CLOSED,
          closed_at=_stamp(previous.replace(hour=20)))
    alarm("上月转派没处理", created_at=_created(previous),
          assigned_at=_stamp(previous.replace(hour=21)), assignee="finance-staff")
    alarm("本月", created_at=_created(_now().replace(hour=8)))


def _world_legacy_shapes(alarm, alerts):
    """0014 之前的行、空串、``NULL``、整个缺键——四种形状同时在场（判据丁）。"""
    previous = _prev_month_anchor()
    alarm("老行没有处置列", created_at=_created(previous),
          strip=("status", "acknowledged_at", "closed_at", "assigned_at"))
    alarm("确认列是空串", created_at=_created(previous),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at="")
    alarm("确认列是 NULL", created_at=_created(previous),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=None)
    alarm("确认列读不出", created_at=_created(previous),
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at="昨天上午")
    alarm("时间整个缺席", created_at=_created(previous),
          status=alerts.ALERT_STATUS_CLOSED, closed_at=None, acknowledged_at=None)


_WORLDS = (_world_all_open, _world_mixed_disposal, _world_legacy_shapes)
_WORLD_IDS = ("all-open", "mixed-disposal", "legacy-shapes")


@pytest.mark.parametrize("world", _WORLDS, ids=_WORLD_IDS)
@pytest.mark.parametrize("username", ["finance-manager", "root-admin"])
@pytest.mark.parametrize("period", ["month", "week"])
def test_both_legs_answer_the_same_series_on_the_same_seed(client, alarm, monkeypatch, world,
                                                           username, period):
    """判据丙：同一份种子，PG 腿与内存腿必须回同一个数——一格不差。

    比的是整份响应，不是本件挑的两列：分桶、``undated``、缺席规则跟着一起对，两腿任何一处
    各算一套都会在这里红。替身只认 ``alert_row_scope_sql`` 那三种析取支并按 ``SELECT`` 清单
    投影，所以「SQL 腿少读一列」与「SQL 腿自己算日期」都不是静默偏差，是当场炸。
    """
    from app.api.v1 import alerts

    world(alarm, alerts)

    _memory_leg(alerts, monkeypatch)
    memory = _body(client, username, period=period)

    _sql_leg(alerts, list(alerts._MEM_ALERTS), monkeypatch)
    postgres = _body(client, username, period=period)

    assert postgres["series"] == memory["series"]
    assert postgres["undated"] == memory["undated"]
    assert memory["series"], "空序列会让这条等号变成恒真"


@pytest.mark.parametrize("world", _WORLDS, ids=_WORLD_IDS)
def test_the_sql_leg_reads_the_columns_the_predicate_needs(client, alarm, monkeypatch, world):
    """时钟列必须在 ``SELECT`` 清单里：缺席不报错，只会静默把两腿劈成两个数。"""
    from app.api.v1 import alerts

    world(alarm, alerts)
    table = _sql_leg(alerts, list(alerts._MEM_ALERTS), monkeypatch)

    _body(client)

    from app.api.v1 import dashboard

    projections = [sql for sql, _ in table.statements if "FROM alerts" in sql]
    assert projections, "SQL 腿根本没向 alerts 表读过行"
    needed = ("created_at", "status") + tuple(dashboard._ALERT_DISPOSAL_MOMENT_COLUMNS)
    for sql in projections:
        head = sql.split("FROM alerts", 1)[0]
        for column in needed:
            assert column in head, f"这一腿没把 {column} 读回来：" + head


def test_the_replay_uses_no_second_time_parser():
    """本模块只许有一枚时间解析器（``_trend_period``），也不许把解析搬进 SQL。"""
    source = MODULE.read_text(encoding="utf-8")

    assert source.count("fromisoformat") == 1, "dashboard 里长出了第二套时间解析"

    statements = [node.value for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and ("SELECT " in node.value or "FROM alerts" in node.value)]
    assert statements, "本模块没有一条 SQL 可读，这条钉就成了恒真"
    for statement in statements:
        lowered = statement.lower()
        for banned in ("date_trunc", "at time zone", "now()", "current_date", "to_timestamp",
                       "extract(", "::date", "::timestamp", "interval "):
            assert banned not in lowered, f"SQL 里长出了时间解析（{banned}）：" + statement
    tree = ast.parse(source)
    parser = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_trend_period")
    assert any("fromisoformat" in ast.dump(node) for node in ast.walk(parser)), (
        "唯一那枚解析器不在 _trend_period 里，两腿就没有共用的那一把尺")


# --------------------------------------------------------------------- 判据丁 · 老行一张脸


def test_a_pre_0014_row_shows_the_same_face_as_the_alert_panel(client, alarm, monkeypatch):
    """迁移之前写下的行（没 status、没处置时间）：告警屏说什么脸，这一格就数它成什么。"""
    from app.api.v1 import alerts

    previous = _prev_month_anchor()
    row = alarm("归属列之前的老行", created_at=_created(previous),
                strip=("status", "acknowledged_at", "closed_at"))

    ledger = client.get(ALERT_LEDGER_PATH, headers=_headers("finance-manager"))
    assert ledger.status_code == 200, ledger.text
    shown = [item for item in ledger.json()["alerts"] if item["id"] == row["id"]]
    assert shown and shown[0]["status"] == alerts.ALERT_STATUS_OPEN

    bucket = _series(_body(client))[_month_label(previous.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (1, 1)


def test_dashboard_defines_no_second_status_rule():
    """🔴 本模块不许新写一份 status 判定：状态脸只有 ``alerts.alert_row_status`` 那一枚。"""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    for status in ("open", "acknowledged", "closed"):
        assert status not in literals, f"dashboard 里出现了裸状态字面量 {status!r}"
    assert "status" not in literals, "dashboard 里自己读起了 status 键"

    used = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute)
            and node.attr == "alert_row_status"]
    assert used, "本模块一次都不再问 alerts 那枚判定，就是在别处另算一份状态脸"


@pytest.mark.parametrize("world", [_world_legacy_shapes], ids=["legacy-shapes"])
def test_blank_null_and_absent_stamps_are_one_face_on_both_legs(client, alarm, monkeypatch,
                                                                world):
    """空串、``NULL``、键整个缺席是同一种形状，两腿都不许拿它当错。"""
    from app.api.v1 import alerts

    world(alarm, alerts)

    _memory_leg(alerts, monkeypatch)
    memory = _body(client)
    _sql_leg(alerts, list(alerts._MEM_ALERTS), monkeypatch)
    postgres = _body(client)

    assert postgres["series"] == memory["series"]
    previous = _month_label(_prev_month_anchor().date())
    # 五枚行同一档：只有「老行没有处置列」那枚会被算成未处置（它的 status 脸就是 open，与
    # 告警屏同一张脸）；四枚「处置过但时钟为空/NULL/缺席/读不出」的都按当下读法不算。
    for body in (memory, postgres):
        assert _series(body)[previous]["alerts"] == 5
        assert _series(body)[previous]["alerts_open"] == 1, (
            "空串/NULL/缺席/坏掉这四枚形状里有一枚没跟内存腿回同一个数")


def test_an_unreadable_disposal_clock_falls_back_without_a_new_refusal(client, alarm):
    """处置时间记了但不是时间：不开新脸，不 503，只退回当下读法。"""
    from app.api.v1 import alerts

    previous = _prev_month_anchor()
    alarm("时钟坏了", created_at=_created(previous), status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at="昨天上午")
    alarm("时钟好的", created_at=_created(previous), status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(_now()))

    response = _trend(client)
    assert response.status_code == 200, response.text

    bucket = _series(response.json())[_month_label(previous.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (2, 1)


# ------------------------------------------------------------------- 判据戊 · 新列的守恒式


@pytest.mark.parametrize("world", _WORLDS, ids=_WORLD_IDS)
def test_no_bucket_reports_more_open_rows_than_it_has(client, alarm, world):
    """戊：🔴 任何一档都不许出现 ``alerts_open > alerts``——两列同一本账，一个子集。"""
    from app.api.v1 import alerts

    world(alarm, alerts)

    buckets = [(point["alerts"], point["alerts_open"])
               for point in _body(client)["series"] if point["alerts"]]

    assert buckets, "没有一档有行，这条界就变成恒真"
    for total, open_total in buckets:
        assert 0 <= open_total <= total, f"该档未处置数越界：{open_total} > {total}"


def test_the_upper_bound_is_reachable(client, alarm):
    """上界不是摆设：全都没人处置的那一档，两列必须相等。"""
    previous = _prev_month_anchor()
    alarm("上月甲", created_at=_created(previous))
    alarm("上月乙", created_at=_created(previous))

    bucket = _series(_body(client))[_month_label(previous.date())]

    assert (bucket["alerts"], bucket["alerts_open"]) == (2, 2)


def test_the_open_column_is_bounded_by_the_same_visible_total(client, alarm):
    """R342 的守恒式一字不放松，新列在它里面被同一个可见行数封顶。

    ``sum(各桶 alerts) + undated.alerts == /summary 对同一人报的 total`` 原样复算一遍，
    再量 ``sum(各桶 alerts_open) + undated.alerts_open <= 同一个 total``：新口径可以给既往
    档加回行数（那是它存在的理由），但不许凭空造行。
    """
    from app.api.v1 import alerts

    _world_mixed_disposal(alarm, alerts)
    alarm("无期间未处置", created_at="")
    alarm("无期间已处置", created_at="   ", status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(_prev_month_anchor()))

    body = _body(client, buckets=60)
    summary = client.get(SUMMARY_PATH, headers=_headers("finance-manager")).json()
    undated = body["undated"]

    assert sum(point["alerts"] for point in body["series"]) + undated["alerts"] == (
        summary["alerts"]["total"])
    assert sum(point["alerts_open"] for point in body["series"]) + undated["alerts_open"] <= (
        summary["alerts"]["total"])
    assert undated["alerts_open"] <= undated["alerts"]
    assert all(point["alerts_open"] <= point["alerts"] for point in body["series"])


# ------------------------------------------------------------- 判据己 · 无期间那一格不许动


def test_the_undated_open_cell_keeps_the_present_reading(client, alarm):
    """🔴 己：``undated.alerts_open`` 本单不许跟着变——那些行没有「该档结束那一刻」。

    把新谓词「顺手」套到无期间行上（拿当下当端点）也会红：这一枚行的处置时间写在当下之后，
    回放会说它当时还没被处置，而当下读法按 status 说不算。今天这一格答的是后者。
    """
    from app.api.v1 import alerts

    alarm("无期间、处置时间写在明天", created_at="",
          status=alerts.ALERT_STATUS_ACKNOWLEDGED, acknowledged_at=_stamp(_now() + timedelta(1)))
    alarm("无期间、上月就确认了", created_at="   ", status=alerts.ALERT_STATUS_ACKNOWLEDGED,
          acknowledged_at=_stamp(_prev_month_anchor()))
    alarm("无期间、今天还开着", created_at="")

    body = _body(client)

    assert (body["undated"]["alerts"], body["undated"]["alerts_open"]) == (3, 1)
    assert sum(point["alerts_open"] for point in body["series"]) == 0


# ------------------------------------------------------------------- 判据乙 · 同一笔改口


def _base_file(relative: str) -> str:
    """锚点版本的原文（``git show``）：纯追加与零新增错误码都跟它比，不抄今天的读数。"""
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE}:{relative}"],
        capture_output=True, check=False)
    assert result.returncode == 0, f"取不到 {BASE}:{relative}：{result.stderr.decode(errors='replace')}"
    return result.stdout.decode("utf-8")


def _section(text: str, marker: str) -> str:
    headings = [match.start() for match in re.finditer(r"(?m)^## ", text)]
    matched = [start for start in headings if marker in text[start:text.find("\n", start)]]
    assert len(matched) == 1, f"契约里带 {marker} 的二级节应有 1 枚，实得 {len(matched)}"
    start = matched[0]
    following = [position for position in headings if position > start]
    return text[start:following[0]] if following else text[start:]


#: 本单那一节的标题前缀（不是手抄全文：只取 marker 尺子认的同一枚名字，取自本节自己的第一行）。
OWN_SECTION_HEADING = "「其中当时未闭环」"


def test_the_contract_appends_one_section_and_deletes_nothing():
    """乙：契约文末纯追加一节，🔴 删除行为 0；节数只许**增长**，不许与冻结基点比等号。

    原判据写的是「``## `` 计数 == 基点计数 + 1」，总控并入时改口（理由入档，别当成放宽）：
    那枚等号把**冻结的历史**放在了与现场读数的等号一侧——本单开工到并树之间，只要有任何一枚
    兄弟单在文末追加工过一节（今天就是 R356 那枚 ``GET /api/v1/users`` 三面契约），这条钉就会以
    「二级节多了不止一枚」红掉，而它红的那件事根本不是本单做的。同一条病本仓已裁过两次：
    R346（``test_r238`` 行号账改派生）与 R351（手抄字面/手抄 sha 改记名锚点），口径都是
    「历史只准当素材读，不许出现在与现场比对的等号两侧」。
    现在这三条各自咬得住：① ``startswith`` 咬"回改前文"（任何人在本节之前动过一个字都红）；
    ② 只增不减咬"有人删了别人的节"；③ 本单自己那一枚标题恰一枚由 ``_section`` 的 marker 尺子咬，
    "一单长出两节"照样红——只是它红的是**本单那一枚**，不是全仓节数。
    """
    base = _base_file("docs/api/contract-v1.md")
    now = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert now.startswith(base), "契约不是纯追加：文末之前的每一个字都不许动"
    assert now.count("\n## ") >= base.count("\n## ") + 1, "一节都没长出来：本单没往契约里写口径"
    assert now[len(base):].count("\n## " + OWN_SECTION_HEADING) == 1, "本单那一节在追加段里恰一枚"


def test_the_new_contract_section_states_the_predicate_and_retires_the_old_sentence():
    """乙：新口径写清楚，旧那句「截至今日仍未处置」在本节里被点名作废。"""
    section = _section(CONTRACT.read_text(encoding="utf-8"), "R340")

    for marker in ("alerts_open", "acknowledged_at", "closed_at", "assigned_at", "undated",
                   "_alert_open_at"):
        assert marker in section, f"契约那一节没提 {marker}"
    assert "截至今日仍未处置" in section, "旧措辞没被点名作废"
    assert "as of this request" in section, "R332 那一行英文原话没被点名作废"
    assert "not a disposal" in section, "契约没写明转派不算处置"


def test_the_screen_and_the_server_changed_their_mouths_in_the_same_breath():
    """乙：🔴 服务端改算了，屏上标签与口径句必须同一笔改；留着当下投影那句话就是新造的假话。"""
    lib = LIB.read_text(encoding="utf-8")
    panel = PANEL.read_text(encoding="utf-8")
    module = MODULE.read_text(encoding="utf-8")

    note = re.search(r"TREND_ALERTS_OPEN_NOTE = '([^']*)'", lib)
    assert note, "找不到那一格的口径句子"
    assert "每一档自己结束的那一刻" in note.group(1), note.group(1)
    assert "最新那一档还没结束" in note.group(1), "当下那一档没被承认"
    for lie in ("事后回看", "这次请求时刻的处置状态计算"):
        assert lie not in lib, f"前端还留着当下投影那句话：{lie}"
    assert "其中当时未闭环（条）" in panel, "列头还写着旧口径"
    assert ">其中未闭环（条）<" not in panel
    assert "截至今日仍未处置" not in module, "服务端 docstring 还在承认旧口径"


def test_the_column_names_are_unchanged_and_no_second_column_was_added(client, alarm):
    """乙：列名 ``alerts_open`` 不许改、不许删、不许再加一枚并列列来「两个都要」。"""
    alarm("本月", created_at=_created(_now().replace(hour=8)))

    body = _body(client)

    assert [set(point) for point in body["series"]] and all(
        set(point) == BUCKET_KEYS for point in body["series"]), sorted(body["series"][0])
    assert {key for key in body["undated"] if "open" in key} == {"alerts_open"}
    assert not [key for point in body["series"] for key in point
                if key != "alerts_open" and "open" in key]


# --------------------------------------------------------------------- 判据庚 · 零新增错误码


@pytest.mark.parametrize("name", ["_bucket_end", "_alert_disposal_moment", "_alert_open_at"])
def test_the_new_predicate_opens_no_refusal(name):
    """新写的那三支只做判定，不拒答：读不出的处置时钟退回当下，不开第二张脸。"""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == name)

    assert not [node for node in ast.walk(function) if isinstance(node, ast.Raise)], (
        f"{name} 里长出了新的拒答")


def test_the_module_opens_no_error_code_beyond_the_base_version():
    """庚：``detail`` 字面量集合与锚点版本逐字相等，两张错误码钉一个字都不搬。"""
    def codes(source: str) -> set[str]:
        found = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException":
                for keyword in node.keywords:
                    if keyword.arg == "detail" and isinstance(keyword.value, ast.Constant):
                        found.add(str(keyword.value.value))
        return found

    assert codes(_base_file("app/api/v1/dashboard.py")) == codes(MODULE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("params", [{"period": "day"}, {"buckets": 0}, {"buckets": 61}])
def test_the_two_refusals_still_wear_their_old_faces(client, alarm, params):
    """422 那张脸不动：坏参数依旧 ``validation_error``，与本单的口径变更无关。"""
    alarm("本月", created_at=_created(_now().replace(hour=8)))

    response = _trend(client, **params)

    assert response.status_code == 422
    assert response.json()["detail"] == "validation_error"
