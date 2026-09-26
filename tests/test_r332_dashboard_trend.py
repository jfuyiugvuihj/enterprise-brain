"""R332 · ``GET /api/v1/dashboard/trend``: the overview page's period series.

The frontend asked for this. ``frontend/src/components/DashboardPanel.vue:12-13`` draws the
「数据趋势」 empty state because no server aggregate returned a period series, and ``:304``
says the card may only grow numbers once one exists. So the three things this file is
actually on trial for are the three ways a chart lies:

1. **Permission (criteria 1).** The series is computed through the same
   ``intelligence._authorized`` analyze call ``/summary`` makes, and a caller without alert
   rights gets no ``alerts`` key in any bucket - not a 0. A 0 is the alert ledger read
   around request R1.
2. **Real time (criteria 2/3).** Every bucket is cut from a stored ``created_at``, in
   ``Asia/Shanghai``, and the month/week edges are pinned from both directions: an instant
   that is September in Shanghai but still August in UTC, and a naive timestamp that is
   August by its own digits and must stay there. File mtime is pinned out as a source by
   giving two datasets the same mtime in a third month.
3. **The two faces of nothing (criteria 4).** A quiet period answers 0. A row whose period
   cannot be read answers 503 for the whole response - never a shorter series, never a
   dropped row, never a 0 - because a series that quietly loses a row totals less than
   ``/summary`` says for the same caller, which is one question answered twice.

Like the R14-A1 file beside it this module imports nothing that reaches a model, and every
store it touches is rooted in ``tmp_path``.
"""

import ast
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.storage import datasets as datasets_module

REPO = Path(__file__).resolve().parents[1]
TREND_PATH = "/api/v1/dashboard/trend"
SUMMARY_PATH = "/api/v1/dashboard/summary"
CATALOG_PATH = "/api/v1/documents/catalog"
DATA_FILES_PATH = "/api/v1/data-files"

#: The zone the route declares and the tests compute their own expectations in. Stated here
#: a second time on purpose: if the route ever answers a different zone, the arithmetic below
#: is what makes the buckets disagree.
SHANGHAI = timezone(timedelta(hours=8))


def _user(username: str, department: str, role: str = "manager") -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


def _headers(username: str) -> dict:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


ACCOUNTS = {
    "finance-staff": _user("finance-staff", "finance", "staff"),
    "finance-manager": _user("finance-manager", "finance"),
    "hr-manager": _user("hr-manager", "hr"),
    "root-admin": _user("root-admin", "", "admin"),
    # 没有 resource:analyze 的角色：trend 与 summary 共用同一道门，它两边都进不来。
    "outside-auditor": _user("outside-auditor", "legal", "auditor"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))


@pytest.fixture(autouse=True)
def offline_catalog(monkeypatch):
    """Pin the document book to its JSON path, the same way the ledger tests do.

    Left unchosen, this file would count a real ``document_versions`` table on a machine
    that happens to have PostgreSQL and pass nowhere else.
    """
    from app.documents import catalog

    monkeypatch.setattr(catalog, "_database_available", lambda: False)


@pytest.fixture(autouse=True)
def memory_alerts(monkeypatch):
    from app.api.v1 import alerts

    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_database_available", lambda: False)


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def document_store(monkeypatch, tmp_path):
    """The real offline catalog, with the period the row reports under as an argument."""
    from app.documents import catalog

    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(
        filename: str,
        *,
        department: str,
        owner: str,
        classification: int = 1,
        parse_status: str = "pending",
        created_at: str | None = None,
    ) -> None:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        catalog.record_local_document_version(
            filename,
            classification,
            department,
            str(stored),
            1,
            owner_id=owner,
            parse_status=parse_status,
        )
        if created_at is not None:
            path = root / catalog.LOCAL_CATALOG_FILENAME
            payload = json.loads(path.read_text(encoding="utf-8"))
            key = catalog._sidecar_key(filename, 1)
            payload["documents"][key]["created_at"] = created_at
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    add.root = root
    return add


@pytest.fixture()
def dataset_store(monkeypatch, tmp_path):
    """The real registry, with the registration clock handed to each call.

    ``register()`` stamps rows through ``datasets._utc_now_text()`` (``datasets.py:911``), so
    the period is set on the write path rather than by editing a stored row afterwards - the
    row that ends up in the table is the row the route reads.
    """
    from app.api.v1 import data
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / "data"
    root.mkdir()
    registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)

    clock = {"now": ""}
    monkeypatch.setattr(datasets_module, "_utc_now_text", lambda: clock["now"])

    def add(
        filename: str,
        *,
        owner: str,
        department: str,
        created_at: str,
        classification: str = "internal",
    ) -> Path:
        path = root / filename
        path.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
        clock["now"] = created_at
        registry.register(
            path, principal=Principal.from_user(_user(owner, department)),
            classification=classification,
        )
        return path

    add.root = root
    return add


@pytest.fixture()
def seed_alerts(monkeypatch):
    """Append rows to the offline ledger in the shape ``alerts.py:817-828`` writes them."""
    from app.api.v1 import alerts

    def add(message: str, *, created_at: str, department: str = "", status: str = "open") -> None:
        alerts._MEM_ALERTS.append(
            {
                "id": len(alerts._MEM_ALERTS) + 1,
                "rule_id": 1,
                "message": message,
                "ai_analysis": "",
                "department": department,
                "read": False,
                "created_at": created_at,
                **alerts.ALERT_DISPOSAL_DEFAULTS,
            }
            | {"status": status}
        )

    return add


# ------------------------------------------------------------------ the calendar, twice


def _now() -> datetime:
    return datetime.now(SHANGHAI)


def _month_label(day: date) -> str:
    return "%04d-%02d" % (day.year, day.month)


def _week_label(day: date) -> str:
    iso = day.isocalendar()
    return "%04d-W%02d" % (iso[0], iso[1])


def _month_window(count: int) -> list[date]:
    """The ``count`` months a viewer expects, oldest first, walked back one month at a time."""
    cursor = date(_now().year, _now().month, 1)
    starts = []
    for _ in range(count):
        starts.append(cursor)
        cursor = cursor - timedelta(days=1)
        cursor = date(cursor.year, cursor.month, 1)
    starts.reverse()
    return starts


def _shanghai_instants():
    """Two moments either side of a month edge, as *Shanghai* wall times.

    ``inside`` is half an hour after the first instant of the current month; ``before`` is
    half an hour before it, i.e. the last day of the previous month at 23:30. Both are
    written out in UTC with an explicit offset, where they read as the *previous* month's
    day - which is the whole point: the digits are wrong for the bucket, the instant is not.
    """
    month_start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inside = month_start + timedelta(minutes=30)
    before = month_start - timedelta(minutes=30)
    return inside, before


def _trend(client, username: str = "finance-manager", **params):
    return client.get(TREND_PATH, headers=_headers(username), params=params)


def _series(body):
    return {point["bucket"]: point for point in body["series"]}


# ------------------------------------------------------------------ the route is published


def test_the_trend_path_is_published_as_a_read_only_route(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][TREND_PATH]["get"]

    assert operation["tags"] == ["dashboard"]
    assert "requestBody" not in operation, "trend 是只读聚合，不接受客户端喂 rows"


def test_the_body_is_not_reusable_across_callers(client):
    response = _trend(client)

    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")
    assert response.headers.get("pragma") == "no-cache"


# ------------------------------------------------------------------ 判据 1: one permission leg


def test_the_gate_is_the_same_analyze_call_the_summary_route_makes(client, monkeypatch):
    """The trend route borrows ``intelligence._authorized``; it does not grow a second chain."""
    from app.api.v1 import intelligence

    seen: list[tuple[str, str]] = []
    real = intelligence._authorized

    def spy(request, action, resource_name):
        seen.append((action, resource_name))
        return real(request, action, resource_name)

    monkeypatch.setattr(intelligence, "_authorized", spy)
    assert _trend(client).status_code == 200

    assert seen == [("resource:analyze", "dashboard_trend")]


def test_an_anonymous_caller_gets_no_buckets(client):
    response = client.get(TREND_PATH)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
    assert "series" not in response.json(), "拒绝出口不许顺手带上任何一格"


def test_a_principal_without_analyze_rights_gets_no_buckets(client):
    response = _trend(client, "outside-auditor")

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


def test_a_staff_caller_without_alert_rights_gets_no_alert_keys_in_any_bucket(client, seed_alerts):
    """反证面之一：无权限是「键消失」，不是「这一期 0 条告警」。

    A real alarm is in the ledger, so a 0 here would be the alert total read through a route
    that is not ``GET /alerts`` - request R1 with one ``ACTION_ANALYZE`` call in front of it.
    """
    seed_alerts("现金流低于阈值", created_at=_now().isoformat(timespec="seconds"), department="finance")

    body = _trend(client, "finance-staff").json()
    summary = client.get(SUMMARY_PATH, headers=_headers("finance-staff")).json()

    assert "alerts" not in summary, "same discipline the summary tile already holds"
    for point in body["series"]:
        assert "alerts" not in point
        assert "alerts_open" not in point
        assert "documents" in point and "datasets" in point, "the rest of the tile stays"


def test_a_manager_counts_only_the_alerts_of_the_departments_they_can_see(client, seed_alerts):
    """Second layer, same as R188: passing the gate is not a licence for the company total."""
    stamp = _now().isoformat(timespec="seconds")
    seed_alerts("finance alarm", created_at=stamp, department="finance")
    seed_alerts("hr alarm", created_at=stamp, department="hr")
    current = _month_label(_now().date())

    mine = _series(_trend(client, "finance-manager").json())[current]
    theirs = _series(_trend(client, "hr-manager").json())[current]
    both = _series(_trend(client, "root-admin").json())[current]

    assert (mine["alerts"], theirs["alerts"], both["alerts"]) == (1, 1, 2)


def test_the_buckets_add_up_to_the_lists_the_panel_already_shows(
    client, document_store, dataset_store
):
    """The series is a partition of the same visible set ``/summary`` counts."""
    inside, before = _shanghai_instants()
    document_store(
        "plan.pdf", department="finance", owner="finance-manager", created_at=inside.isoformat()
    )
    document_store(
        "prior.pdf", department="finance", owner="finance-manager", created_at=before.isoformat()
    )
    document_store(
        "roster.pdf", department="hr", owner="hr-manager", created_at=inside.isoformat()
    )
    dataset_store("finance.csv", owner="finance-manager", department="finance",
                  created_at=inside.astimezone(timezone.utc).isoformat())

    headers = _headers("finance-manager")
    body = _trend(client, "finance-manager").json()
    summary = client.get(SUMMARY_PATH, headers=headers).json()

    assert sum(point["documents"] for point in body["series"]) == summary["documents"]
    assert sum(point["datasets"] for point in body["series"]) == summary["datasets"]
    assert sum(point["documents"] for point in body["series"]) == len(
        client.get(CATALOG_PATH, headers=headers).json()["documents"]
    )
    assert len(client.get(DATA_FILES_PATH, headers=headers).json()["files"]) == summary["datasets"]


# ---------------------------------------------------------- 判据 4: the two faces of nothing


def test_the_window_is_consecutive_and_ends_with_the_current_period(client):
    body = _trend(client, buckets=6).json()

    assert body["period"] == "month"
    assert body["buckets"] == 6
    assert body["time_zone"] == "Asia/Shanghai"
    assert body["generated_for"] == "finance-manager"
    assert [point["start"] for point in body["series"]] == [
        day.isoformat() for day in _month_window(6)
    ]
    assert [point["bucket"] for point in body["series"]] == [
        _month_label(day) for day in _month_window(6)
    ]


def test_a_quiet_period_answers_with_a_real_zero(client, document_store):
    """空桶 = 真的 0：这一期确实没有新增，这句话由服务端来说，不让前端猜被省略的期。"""
    inside, _ = _shanghai_instants()
    document_store(
        "plan.pdf", department="finance", owner="finance-manager", created_at=inside.isoformat()
    )

    series = _series(_trend(client, buckets=12).json())

    assert len(series) == 12
    assert series[_month_label(inside.date())]["documents"] == 1
    quiet = [label for label, point in series.items() if point["documents"] == 0]
    assert len(quiet) == 11, "the other periods are stated empty, not omitted"


def test_a_dataset_row_with_no_recorded_time_refuses_the_whole_series(client, dataset_store):
    """反证面之二：账读不出来不许折成 0，也不许悄悄少一格。

    ``created_at`` empty is what a legacy sidecar import leaves behind
    (``datasets.py:763``), so this is a real row shape on a real upgraded install.
    """
    dataset_store("legacy.csv", owner="finance-manager", department="finance", created_at="")

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"
    assert "series" not in response.json()


def test_a_document_row_with_an_unparseable_time_refuses_the_whole_series(client, document_store):
    document_store("odd.pdf", department="finance", owner="finance-manager", created_at="昨天上午")

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"


def test_an_alert_row_with_no_time_refuses_the_whole_series(client, seed_alerts):
    """A ledger row nobody stamped is not a month with nothing in it."""
    from app.api.v1 import alerts

    seed_alerts("undated alarm", created_at=_now().isoformat(timespec="seconds"))
    alerts._MEM_ALERTS[0].pop("created_at")

    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"


def test_a_book_that_raises_is_not_folded_into_zero(client, monkeypatch):
    """No ``try/except`` on the reads: a failing dependency keeps failing the response."""
    from app.api.v1 import chat

    def boom(request):
        raise RuntimeError("catalog is down")

    monkeypatch.setattr(chat, "list_document_catalog", boom)

    with pytest.raises(RuntimeError, match="catalog is down"):
        client.get(TREND_PATH, headers=_headers("finance-manager"))


# ---------------------------------------------------------- 判据 2/3: real time, one zone


def test_a_visible_file_whose_registry_row_vanished_refuses_the_series(
    client, monkeypatch, dataset_store
):
    """The two reads disagreeing is an unreadable book, not a month with nothing in it.

    ``list_data_files`` said the file is registered and visible; the registry pass this route
    consults for the clock no longer carries the name. Dropping it would quietly lower the
    series total below ``/summary``, which is the defect this whole file is pinned against.
    """
    from app.api.v1 import data

    inside, _ = _shanghai_instants()
    dataset_store(
        "finance.csv", owner="finance-manager", department="finance",
        created_at=inside.astimezone(timezone.utc).isoformat(),
    )

    async def listing_with_a_ghost(request=None):
        return {"files": [{"filename": "vanished.csv", "modified_at": inside.isoformat()}]}

    monkeypatch.setattr(data, "list_data_files", listing_with_a_ghost)
    response = _trend(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"
    assert "series" not in response.json()


def test_a_month_edge_moment_is_bucketed_by_shanghai_wall_time(client, dataset_store):
    """反证面之三：跨月的真实数据必须落在正确的月。

    Both rows are written as UTC instants whose *digits* say the previous month. Read as
    Shanghai they are one in the current month (00:30 on the 1st) and one in the previous
    month (23:30 on its last day). A route that ignored the offset, or one that assumed UTC
    for everything, puts both in the same bucket and reddens this test.
    """
    inside, before = _shanghai_instants()
    dataset_store(
        "first.csv", owner="finance-manager", department="finance",
        created_at=inside.astimezone(timezone.utc).isoformat(),
    )
    dataset_store(
        "last.csv", owner="finance-manager", department="finance",
        created_at=before.astimezone(timezone.utc).isoformat(),
    )

    series = _series(_trend(client, buckets=12).json())

    assert series[_month_label(inside.date())]["datasets"] == 1
    assert series[_month_label(before.date())]["datasets"] == 1
    assert series[_month_label(inside.date())]["start"] == date(
        inside.year, inside.month, 1
    ).isoformat()


def test_a_naive_alert_timestamp_stays_on_the_day_its_column_stored(client, seed_alerts):
    """``alerts.created_at`` holds Shanghai wall time with no offset (``alerts.py:122``).

    The naive family must be read as Shanghai, not as UTC: this row is 23:30 on the last day
    of the previous month, and shifting it eight hours forward would invent an alarm in the
    current month.
    """
    _, before = _shanghai_instants()
    seed_alerts(
        "last-day alarm", created_at=before.strftime("%Y-%m-%dT%H:%M:%S"), department="finance"
    )

    series = _series(_trend(client, buckets=12).json())

    assert series[_month_label(before.date())]["alerts"] == 1
    assert series[_month_label(_now().date())]["alerts"] == 0


def test_week_buckets_start_on_monday(client, seed_alerts):
    today = _now().date()
    monday = today - timedelta(days=today.weekday())
    this_week = datetime.combine(
        monday, datetime.min.time(), tzinfo=SHANGHAI
    ) + timedelta(minutes=15)
    last_week = this_week - timedelta(minutes=30)

    seed_alerts("this week", created_at=this_week.isoformat(), department="finance")
    seed_alerts("sunday night", created_at=last_week.isoformat(), department="finance")

    body = _trend(client, period="week", buckets=8).json()
    series = _series(body)

    assert body["period"] == "week"
    assert series[_week_label(monday)]["alerts"] == 1
    assert series[_week_label(last_week.date())]["alerts"] == 1
    starts = [date.fromisoformat(point["start"]) for point in body["series"]]
    assert all(day.weekday() == 0 for day in starts), "周桶起点必须是同一个星期一"


def test_the_period_is_not_read_from_the_filesystem_mtime(client, dataset_store):
    """判据 2 的正面钉法：同一枚 mtime、相隔两个月的登记时间，桶必须分开。

    ``data.list_data_files`` answers ``modified_at`` off ``path.stat()``, so a route that took
    its period from the listing would put both datasets in one bucket. The shared mtime is
    deliberately set to a month neither dataset belongs to: if it ever becomes the source,
    that bucket stops being empty.
    """
    inside, before = _shanghai_instants()
    newest = dataset_store(
        "new.csv", owner="finance-manager", department="finance",
        created_at=inside.astimezone(timezone.utc).isoformat(),
    )
    oldest = dataset_store(
        "old.csv", owner="finance-manager", department="finance",
        created_at=before.astimezone(timezone.utc).isoformat(),
    )
    eleven_months_ago = _now() - timedelta(days=330)
    os.utime(newest, (eleven_months_ago.timestamp(), eleven_months_ago.timestamp()))
    os.utime(oldest, (eleven_months_ago.timestamp(), eleven_months_ago.timestamp()))

    series = _series(_trend(client, buckets=12).json())

    assert series[_month_label(inside.date())]["datasets"] == 1
    assert series[_month_label(before.date())]["datasets"] == 1
    assert series[_month_label(eleven_months_ago.date())]["datasets"] == 0


# ------------------------------------------------------------- 判据 5: parse bias travels


def test_documents_ready_follows_the_tile_it_shares_a_read_with(client, document_store):
    """A legacy row defaulted to ``pending`` is 「还没解析完」 here exactly as it is on the tile."""
    inside, _ = _shanghai_instants()
    document_store(
        "legacy.pdf", department="finance", owner="finance-manager", created_at=inside.isoformat()
    )
    document_store("parsed.pdf", department="finance", owner="finance-manager",
                   parse_status="ready", created_at=inside.isoformat())
    document_store("half.pdf", department="finance", owner="finance-manager",
                   parse_status="parsing", created_at=inside.isoformat())

    body = _trend(client, buckets=12).json()
    summary = client.get(SUMMARY_PATH, headers=_headers("finance-manager")).json()
    point = _series(body)[_month_label(inside.date())]

    assert (point["documents"], point["documents_ready"]) == (3, 1)
    assert sum(p["documents_ready"] for p in body["series"]) == summary["documents_ready"]
    assert all(p["documents_ready"] <= p["documents"] for p in body["series"])


# --------------------------------------------------------------------- parameter refusals


@pytest.mark.parametrize("params", [{"period": "quarter"}, {"buckets": 0}, {"buckets": 61}])
def test_an_illegal_parameter_answers_with_the_existing_code(client, params):
    """422 ``validation_error`` is ``app/api/v1/notifications.py`` 的既有口径，本单零新增。"""
    response = _trend(client, **params)

    assert response.status_code == 422
    assert response.json()["detail"] == "validation_error"


def test_the_refusal_comes_after_the_gate_not_before_it(client):
    """An anonymous caller must not be able to probe which parameter values are legal."""
    response = client.get(TREND_PATH, params={"period": "decade"})

    assert response.status_code == 401


def test_the_route_opens_no_error_code_outside_the_ratified_enum():
    """Every ``detail`` literal in the module is an enum member, so the code table stays untouched.

    A new bare code would have to be added to the contract's table *and* to
    ``tests/test_error_code_vocabulary.py``; this pin is what makes opening one expensive.
    """
    source = (REPO / "app" / "api" / "v1" / "dashboard.py").read_text(encoding="utf-8")
    enum_source = (REPO / "app" / "agents" / "contracts.py").read_text(encoding="utf-8")

    codes: set[str] = set()
    for node in ast.walk(ast.parse(enum_source)):
        if isinstance(node, ast.ClassDef) and node.name == "ErrorEnvelope":
            for stmt in node.body:
                annotation = getattr(stmt, "annotation", None)
                if isinstance(annotation, ast.Subscript) and annotation.value.id == "Literal":
                    codes |= {e.value for e in annotation.slice.elts if isinstance(e, ast.Constant)}
    assert codes, "枚举解析不出码名时对账不能降级成恒真"

    used = {
        keyword.arg == "detail" and isinstance(keyword.value, ast.Constant) and keyword.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HTTPException"
        for keyword in node.keywords
    }
    used = {value for value in used if isinstance(value, str)}

    assert used <= codes, f"本模块出现了枚举之外的裸码：{sorted(used - codes)}"
    assert re.search(r"detail=f", source) is None, "detail 不许插值，否则这道钉就读不到了"


def test_the_summary_route_still_answers_its_own_shape(client, document_store, dataset_store):
    """R332 adds a route; it does not move a key on the four tiles it had to leave alone."""
    inside, _ = _shanghai_instants()
    document_store(
        "plan.pdf", department="finance", owner="finance-manager", created_at=inside.isoformat()
    )
    dataset_store(
        "finance.csv", owner="finance-manager", department="finance",
        created_at=inside.astimezone(timezone.utc).isoformat(),
    )

    manager = client.get(SUMMARY_PATH, headers=_headers("finance-manager")).json()
    staff = client.get(SUMMARY_PATH, headers=_headers("finance-staff")).json()

    assert set(manager) == {
        "generated_for", "pending_approvals", "documents", "documents_ready", "datasets", "alerts"
    }
    assert set(staff) == {
        "generated_for", "pending_approvals", "documents", "documents_ready", "datasets"
    }
