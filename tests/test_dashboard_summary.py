"""R14-A1: ``GET /api/v1/dashboard/summary`` - the overview page's server-side counts.

Two hard constraints from the follow-up request drive this file:

1. **alerts** - the count is readable only through the gate ``app/api/v1/alerts.py``
   already applies (``_require_alert_management``, :96-108). A caller who cannot read
   ``GET /alerts`` gets **no ``alerts`` key at all**: not ``0``, not ``null``. A ``0``
   renders as "no alarms" and is indistinguishable from health, which is the false
   green light this request exists to remove.
2. **pending approvals** - the number is the same ledger read, under the same ownership
   predicate, that ``GET /hitl/pending`` performs (R13). No second visibility rule is
   introduced here. A missing ledger keeps R13's semantics, and the branch chosen for
   the aggregate is the stricter one: **the whole summary answers
   ``503 storage_unavailable``** rather than returning the numbers that did work. That
   choice is pinned below, so a future edit has to change the contract deliberately.

Everything else is anti-drift: the document and dataset counts are compared against the
two list endpoints the overview panel already calls (``/documents/catalog`` and
``/data-files``), because those calls *are* the implementation the numbers come from -
an aggregate with its own filter is how a second permission chain starts.
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.storage import pending_approvals as store

SUMMARY_PATH = "/api/v1/dashboard/summary"
PENDING_PATH = "/api/v1/hitl/pending"
ALERTS_PATH = "/api/v1/alerts"
CATALOG_PATH = "/api/v1/documents/catalog"
DATA_FILES_PATH = "/api/v1/data-files"


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
    "outside-auditor": _user("outside-auditor", "legal", "auditor"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """Serve the fixture accounts through the lookup the auth middleware uses."""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))


@pytest.fixture(autouse=True)
def memory_ledger(monkeypatch):
    """The HITL ledger runs offline for every case unless a test opts into PostgreSQL."""
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)


@pytest.fixture(autouse=True)
def memory_alerts(monkeypatch):
    """Pin the alert store to its offline list unless a case opts into PostgreSQL.

    The branch is otherwise chosen by ``app.common.auth._db_ready``, so this file passes
    on a machine with no reachable PostgreSQL and fails on one that has it: the summary
    would count the real ``alerts`` table while the seed went into ``_MEM_ALERTS``. The
    one case that exercises the SQL branch re-enables it inside its own body.
    """
    from app.api.v1 import alerts

    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_database_available", lambda: False)


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def document_store(monkeypatch, tmp_path):
    """The real offline catalog, rooted in tmp_path.

    Rows are written through ``record_local_document_version`` so the authorization
    judgment under test reads the same shape a deployed catalog row carries.
    """
    from app.documents import catalog

    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))

    def add(filename: str, *, department: str, owner: str, classification: int = 1) -> None:
        stored = tmp_path / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        # version=1 pins the sidecar key to the physical ``__v1`` name above:
        # the offline catalog dedupes per logical file, so a version that does not
        # match the scanned file would leave the unowned row as the current one.
        catalog.record_local_document_version(
            filename, classification, department, str(stored), 1, owner_id=owner
        )

    return add


@pytest.fixture()
def dataset_store(monkeypatch, tmp_path):
    """The real dataset registry, rooted in tmp_path."""
    from app.api.v1 import data
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    root = tmp_path / "data"
    root.mkdir()
    registry = DatasetRegistry(root=root, metadata_path=root / ".dataset-metadata.json")
    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)

    def add(
        filename: str, *, owner: str, department: str, classification: str = "internal"
    ) -> None:
        path = root / filename
        path.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
        registry.register(
            path, principal=Principal.from_user(_user(owner, department)), classification=classification
        )

    return add


@pytest.fixture()
def corpus(document_store, dataset_store):
    """Three documents and three datasets spread over two departments and two levels."""
    document_store("finance-plan.pdf", department="finance", owner="finance-manager")
    document_store("finance-budget.pdf", department="finance", owner="finance-manager", classification=2)
    document_store("hr-roster.pdf", department="hr", owner="hr-manager")
    # The registry default is ``internal`` = level 2, which a clearance-1 staff account
    # cannot read, so one of the two finance tables is published one level lower.
    dataset_store("finance.csv", owner="finance-manager", department="finance", classification="public")
    dataset_store("finance-q2.csv", owner="finance-manager", department="finance")
    dataset_store("hr.csv", owner="hr-manager", department="hr", classification="public")


def _park(session_id: str, owner: str, steps=("chart",)):
    return store.record_awaiting(session_id, owner, list(steps), request_id="req-1")


def _summary(client, username: str):
    return client.get(SUMMARY_PATH, headers=_headers(username))


# ------------------------------------------------------------- the route is published


def test_the_summary_path_is_published_as_a_read_only_route(client, corpus):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][SUMMARY_PATH]["get"]

    assert operation["tags"] == ["dashboard"]
    assert "requestBody" not in operation, "R14-A1 是只读聚合，不接受客户端喂 rows（那是 POST /dashboard 的老路）"


def test_the_summary_body_is_not_reusable_across_callers(client, corpus):
    """Per-Principal counts behind a cache are one stale tile away from another tenant."""
    response = _summary(client, "finance-manager")

    assert response.status_code == 200
    assert "no-store" in response.headers.get("cache-control", "")


# --------------------------------------------------- counts come from the panel's sources


def test_the_counts_equal_the_lists_the_overview_panel_already_calls(client, corpus):
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    catalog_rows = client.get(CATALOG_PATH, headers=headers).json()["documents"]
    data_files = client.get(DATA_FILES_PATH, headers=headers).json()["files"]

    assert body["documents"] == len(catalog_rows)
    assert body["datasets"] == len(data_files)
    assert (body["documents"], body["datasets"]) == (2, 2)


@pytest.mark.parametrize(
    "username,documents,datasets",
    [
        ("finance-staff", 1, 1),  # 部门内也要再过密级：2 级的那份文档/表都看不见
        ("finance-manager", 2, 2),
        ("hr-manager", 1, 1),
        ("root-admin", 3, 3),  # 管理员不受部门限制
    ],
)
def test_every_count_is_computed_through_the_callers_own_scope(
    client, corpus, username, documents, datasets
):
    body = _summary(client, username).json()

    assert (body["documents"], body["datasets"]) == (documents, datasets)


def test_the_response_names_the_principal_the_counts_were_scoped_to(client, corpus):
    body = _summary(client, "finance-manager").json()

    assert body["generated_for"] == "finance-manager"


# ============================================================ 硬约束一：告警计数要过判定


def test_a_staff_caller_without_alert_rights_gets_no_alerts_key_at_all(client, corpus, monkeypatch):
    """The red-bottom case: a real alert exists, staff still must not see a number."""
    from app.api.v1 import alerts

    monkeypatch.setattr(
        alerts,
        "_MEM_ALERTS",
        [{"id": 1, "read": False, "message": "现金流低于阈值"}, {"id": 2, "read": True}],
    )
    # Prove the store is not empty, so an absent key cannot be mistaken for "no alarms".
    assert client.get(ALERTS_PATH, headers=_headers("finance-manager")).json()["alerts"]

    response = _summary(client, "finance-staff")

    assert response.status_code == 200
    body = response.json()
    assert "alerts" not in body, "无权限与没有告警混成一个 0 就是假健康"
    assert not [key for key in body if "alert" in key.lower()], "换个键名绕过判定同样是后门"
    assert body["documents"] == 1, "省一个字段不该把其它真实计数一起弄没"


def test_a_manager_gets_alert_counts_read_from_the_same_store_the_panel_lists(
    client, corpus, monkeypatch
):
    from app.api.v1 import alerts

    monkeypatch.setattr(
        alerts,
        "_MEM_ALERTS",
        [
            {"id": 1, "read": False},
            {"id": 2, "read": False},
            {"id": 3, "read": True},
        ],
    )
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    listed = client.get(ALERTS_PATH, headers=headers).json()["alerts"]

    assert body["alerts"] == {"total": 3, "unread": 2}
    assert body["alerts"]["total"] == len(listed)


def test_an_administrator_gets_the_alert_counts_too(client, corpus, monkeypatch):
    from app.api.v1 import alerts

    monkeypatch.setattr(alerts, "_MEM_ALERTS", [{"id": 1, "read": False}])

    assert _summary(client, "root-admin").json()["alerts"] == {"total": 1, "unread": 1}


def test_the_alert_gate_never_sees_the_offline_bypass(client, corpus, monkeypatch):
    """``_require_alert_management(None)`` returns early (alerts.py:99-100).

    The aggregate must hand it the live Request, or it reads the count through a door
    the HTTP routes are not allowed to open.
    """
    from app.api.v1 import alerts

    seen = []
    real = alerts._require_alert_management

    def spy(request):
        seen.append(request)
        return real(request)

    monkeypatch.setattr(alerts, "_require_alert_management", spy)

    assert _summary(client, "finance-staff").status_code == 200
    assert seen, "告警计数必须先问那道判定，而不是自己猜权限"
    assert all(item is not None for item in seen)


def test_the_alert_count_counts_the_table_and_not_the_truncated_page(client, corpus, monkeypatch):
    """``GET /alerts`` is ``LIMIT 100`` (alerts.py:402); a total read off it is silently small."""

    class _Result:
        def __init__(self, row=None, rows=None):
            self._row = row
            self._rows = rows if rows is not None else []

        def fetchone(self):
            return self._row

        def fetchall(self):
            return self._rows

    class FakeAlertsConnection:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            self.statements.append(sql)
            if "COUNT(" in sql.upper():
                return _Result({"total": 137, "unread": 40})
            return _Result(rows=[{"id": index, "read": False} for index in range(100)])

        def commit(self):
            return None

    from app.api.v1 import alerts

    conn = FakeAlertsConnection()
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_initialized", True)
    monkeypatch.setattr(alerts, "_conn", lambda: conn)
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    listed = client.get(ALERTS_PATH, headers=headers).json()["alerts"]

    assert body["alerts"] == {"total": 137, "unread": 40}
    assert len(listed) == 100
    assert body["alerts"]["total"] > len(listed), "把被截断的页长当成总数，就是看起来是对的的那类错"
    counts = [item for item in conn.statements if "COUNT(" in item.upper()]
    assert counts and all("LIMIT" not in item.upper() for item in counts)


# ================================================== 硬约束二：待审批数沿用 R13 的账本口径


def test_the_pending_count_is_the_callers_own_open_ledger_rows(client, corpus, monkeypatch):
    _park("mine-1", "finance-manager")
    _park("mine-2", "finance-manager", steps=("export",))
    _park("theirs", "hr-manager")

    body = _summary(client, "finance-manager").json()

    assert body["pending_approvals"] == 2
    assert body["pending_approvals"] == len(store.open_items(owner_user_id="finance-manager"))


def test_a_closed_or_expired_ledger_row_is_not_counted_as_work(client, corpus):
    _park("s-1", "finance-manager")
    _park("s-2", "finance-manager")
    store.mark_status("s-1", "resumed")

    assert _summary(client, "finance-manager").json()["pending_approvals"] == 1


def test_the_pending_count_agrees_with_the_panel_when_the_graph_confirms_every_row(
    client, corpus, monkeypatch
):
    monkeypatch.setattr(
        "app.agents.orchestrator.check_interrupt",
        lambda thread_id: {"pending": ["chart", "export"], "labels": ["图表", "导出"]},
    )
    _park("s-1", "finance-manager")
    _park("s-2", "finance-manager", steps=("export",))
    headers = _headers("finance-manager")

    panel = client.get(PENDING_PATH, headers=headers).json()
    body = client.get(SUMMARY_PATH, headers=headers).json()

    assert panel["count"] == 2
    assert body["pending_approvals"] == panel["count"]


def test_the_pending_count_never_hides_a_todo_the_panel_would_still_show(client, corpus, monkeypatch):
    """The ledger is not revalidated per row here, and that direction is the safe one.

    A row the graph no longer holds is dropped from the panel but still counted by the
    summary: the overview can overstate open work, it can never report a cleaner queue
    than the approval page found.
    """
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda thread_id: None)
    _park("s-1", "finance-manager")
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    panel = client.get(PENDING_PATH, headers=headers).json()

    assert body["pending_approvals"] == 1
    assert panel["count"] == 0
    assert body["pending_approvals"] >= panel["count"]
    # Reading the panel closes the row it judged stale, so the next overview load
    # converges on it - the gap is one reload wide, never a hidden todo.
    assert client.get(SUMMARY_PATH, headers=headers).json()["pending_approvals"] == 0


def test_the_summary_reads_the_ledger_and_never_walks_the_graph(client, corpus, monkeypatch):
    """Cost, not correctness: an overview tile must not pay one checkpoint read per row."""
    from app.agents import orchestrator

    def forbidden(thread_id):
        raise AssertionError("总览聚合不该逐行复核图")

    monkeypatch.setattr(orchestrator, "check_interrupt", forbidden)
    _park("s-1", "finance-manager")
    _park("s-2", "finance-manager", steps=("export",))

    assert _summary(client, "finance-manager").json()["pending_approvals"] == 2


# ------------------------------------------- 缺表：选定「整体 503」，不选「省略该字段」


class _AbsentTableConnection:
    """``to_regclass`` answering NULL is the only thing this fake is allowed to say."""

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append(sql)
        return type("Result", (), {"fetchone": lambda self: {"table_name": None}})()

    def close(self):
        pass


def _no_ledger_table(monkeypatch):
    monkeypatch.setattr(store, "_database_available", lambda: True)
    conn = _AbsentTableConnection()
    monkeypatch.setattr(store, "_conn", lambda: conn)
    return conn


def test_a_missing_ledger_refuses_the_whole_summary_with_the_r13_code(client, corpus, monkeypatch):
    """Chosen branch: 503 for the entire response.

    Omitting ``pending_approvals`` would leave a 200 body reading "12 documents, nothing
    to approve" - the same false health the alerts rule above exists to prevent, and a
    new semantic R13 never had.
    """
    _park("s-1", "finance-manager")
    _no_ledger_table(monkeypatch)

    response = _summary(client, "finance-manager")

    assert response.status_code == 503
    assert response.json() == {"detail": "storage_unavailable"}
    assert response.json()["detail"] != "internal_error", "把缺表洗成通用内部错就没人知道去跑迁移"


def test_a_missing_ledger_refuses_callers_without_alert_rights_the_same_way(
    client, corpus, monkeypatch
):
    """The storage failure is not gated by the alert judgment and must not half-answer."""
    _no_ledger_table(monkeypatch)

    response = _summary(client, "finance-staff")

    assert response.status_code == 503
    assert response.json()["detail"] == "storage_unavailable"


def test_only_the_missing_ledger_table_refuses_the_summary(client, corpus, monkeypatch):
    """R13 catches exactly one exception type; a bare RuntimeError stays a bug.

    Swallowing every error as 503 would cover for a real defect, so this asserts the
    503 is specific: a store that fails for another reason must not report the
    operator-readable code.
    """
    _no_ledger_table(monkeypatch)

    def broken(*_args, **_kwargs):
        raise RuntimeError("connection pool exhausted")

    monkeypatch.setattr(store, "open_items", broken)

    with pytest.raises(RuntimeError, match="connection pool exhausted"):
        client.get(SUMMARY_PATH, headers=_headers("finance-manager"))


# ------------------------------------------------------------------- the auth gate itself


def test_an_anonymous_caller_is_refused_the_stable_code(client, corpus):
    response = client.get(SUMMARY_PATH)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
    assert response.text.strip(), "401 也要有可判读的 body"


def test_the_summary_reuses_the_analyze_tier_and_invents_no_new_permission(client, corpus):
    """``auditor`` may read the audit journal but holds no analyze grant.

    The gate is ``permissions_for_role``, so the refusal below is the role table's
    own answer rather than a second rule written for this endpoint.
    """
    from app.common.permissions import ACTION_ANALYZE, permissions_for_role

    assert ACTION_ANALYZE not in permissions_for_role("auditor")
    response = _summary(client, "outside-auditor")

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"


def test_a_forged_token_never_reaches_the_aggregate(client, corpus):
    response = client.get(SUMMARY_PATH, headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"
