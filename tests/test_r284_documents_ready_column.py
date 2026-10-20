"""R284: ``documents_ready`` on ``GET /api/v1/dashboard/summary``.

The overview document tile has two jobs: say how many documents this caller can see, and
say how many of *those* finished parsing. R274 gave the frontend the second line and
refused to invent it - it reads ``payload.documents_ready`` and treats absence as null,
never as 0 and never as 「all of them」, because counting a list length client-side is the
silent shrink R14-A1 exists to remove. The missing half is server-side, so this file pins
what the new column means:

1. **One read, two columns.** Both numbers come out of the single
   ``chat.list_document_catalog`` call ``_document_counts`` makes, so "the two columns
   disagree about scope" is not a rule somebody has to remember - there is no second query
   to drift. The call count is asserted below, not only the values.
2. **Ready means parsed, not retrievable.** ``parse_status`` answers 「解析这一步走到哪了」;
   ``index_status`` answers 「助理能不能检索到这篇」 and is orthogonal
   (``app/documents/index_policy.py:32-36``). A ready document the index policy excluded
   still counts here; an indexed document still being parsed does not.
3. **A row that never recorded a parse status counts as not ready.**
   ``catalog._normalise_parse_status`` folds NULL/empty/unrecognised into ``"pending"``, so
   every document stored before the column landed reads as unparsed until something
   re-parses it. That understates 「已解析」 and is pinned as-is rather than widened: the
   tile may look pessimistic, it may never look finished when it is not. The same bias is
   written into ``docs/api/contract-v1.md`` for the employee reading the number.
4. **The column never disappears.** ``alerts`` is conditional on purpose; this one is not.
   Absence and ``0`` are two different faces on the frontend, so omitting the key on a
   quiet day would be exactly the false health this endpoint was built to avoid.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import chat, dashboard
from app.documents import catalog
from app.documents.index_policy import INDEX_STATUS_EXCLUDED, INDEX_STATUS_INDEXED, REASON_TOO_SMALL

SUMMARY_PATH = "/api/v1/dashboard/summary"
CATALOG_PATH = "/api/v1/documents/catalog"


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

#: ``(documents, documents_ready)`` per caller for the ``corpus`` below. The ready half is
#: never the tenant's number: the hr document is ready but invisible to finance, and the
#: whole tenant only has two parsed rows out of five.
VISIBLE = {
    "finance-staff": (3, 1),   # 2 级那篇 parsing 仍然看不见：部门内还要再过密级
    "finance-manager": (4, 1),
    "hr-manager": (1, 1),
    "root-admin": (5, 2),      # 管理员看见全部 5 篇，其中真的解析完的只有 2 篇
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """Serve the fixture accounts through the lookup the auth middleware uses."""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))


@pytest.fixture(autouse=True)
def offline_stores(monkeypatch):
    """Pin every store this route touches to its offline path, whatever this machine runs.

    Same reasoning as test_dashboard_summary.py:70-82 - without these pins a host with a
    reachable PostgreSQL would count the real tables while the seed went into the sidecar,
    and the two would answer for different corpora. The numbers below are about counting,
    not about which persistence path stored the row.
    """
    from app.api.v1 import alerts
    from app.storage import pending_approvals as store

    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False)


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def document_store(monkeypatch, tmp_path):
    """The real offline catalog, rooted in tmp_path, with a controllable parse status.

    Rows are written through ``record_local_document_version`` so the authorization
    judgment under test reads the same shape a deployed catalog row carries.
    """
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))

    def add(
        filename: str,
        *,
        department: str,
        owner: str,
        classification: int = 1,
        parse_status: str = "pending",
        index_status: str | None = None,
        index_reason: str = "",
    ) -> None:
        stored = tmp_path / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        # version=1 pins the sidecar key to the physical ``__v1`` name above, the same
        # reason test_dashboard_summary.py:106-108 gives for it.
        catalog.record_local_document_version(
            filename,
            classification,
            department,
            str(stored),
            1,
            owner_id=owner,
            parse_status=parse_status,
            **({} if index_status is None else {"index_status": index_status}),
            index_reason=index_reason,
        )

    def add_before_the_column_existed(filename: str, *, department: str, owner: str) -> None:
        """One row that never recorded a parse status - a pre-0006 document, offline shape.

        There is no other way to say it: ``record_local_document_version`` normalises the
        argument it is handed and cannot store a NULL, so the record is written and the key
        is then removed. The read path is the thing under test, so the sidecar has to be
        put back into the state a historical row is actually in.
        """
        add(filename, department=department, owner=owner)
        path = tmp_path / catalog.LOCAL_CATALOG_FILENAME
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload["documents"][f"{filename}|v1"]
        assert "parse_status" in record, "先确认写进去了，再删：否则这枚钉数的是空气"
        del record["parse_status"]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )

    return SimpleNamespace(add=add, add_before_the_column_existed=add_before_the_column_existed)
@pytest.fixture()
def corpus(document_store):
    """Five documents over two departments, in four different parse states.

    One of each: parsed, failed, still parsing, and one that predates the column. Only the
    first is ready, and it is a finance document - so a caller who cannot see finance can
    never read a ready count out of it.
    """
    document_store.add(
        "finance-plan.pdf", department="finance", owner="finance-manager", parse_status="ready"
    )
    document_store.add(
        "finance-draft.pdf", department="finance", owner="finance-manager", parse_status="failed"
    )
    document_store.add(
        "finance-budget.pdf",
        department="finance",
        owner="finance-manager",
        classification=2,
        parse_status="parsing",
    )
    document_store.add_before_the_column_existed(
        "finance-legacy.pdf", department="finance", owner="finance-manager"
    )
    document_store.add("hr-roster.pdf", department="hr", owner="hr-manager", parse_status="ready")


def _ready_of(rows) -> int:
    return len([row for row in rows if row.get("parse_status") == "ready"])


# ============================================ 判据①②：两列同一趟读，同一个可见范围


@pytest.mark.parametrize("username", sorted(VISIBLE))
def test_the_ready_count_is_scoped_to_what_this_caller_may_list(client, corpus, username):
    """The number is the caller's own catalog page, not the tenant's table.

    ``documents`` is compared against ``GET /documents/catalog`` because that call *is* the
    implementation; ``documents_ready`` is then counted on those same rows. A count taken
    from the whole table reads 2 for a caller who may only list three rows of their own.
    """
    headers = _headers(username)

    body = client.get(SUMMARY_PATH, headers=headers).json()
    rows = client.get(CATALOG_PATH, headers=headers).json()["documents"]

    assert (body["documents"], body["documents_ready"]) == VISIBLE[username]
    assert body["documents"] == len(rows)
    assert body["documents_ready"] == _ready_of(rows)
    assert body["documents_ready"] <= body["documents"]


@pytest.mark.parametrize("username", ["finance-manager", "hr-manager"])
def test_the_two_columns_are_both_explained_by_one_catalog_call(
    client, corpus, monkeypatch, username
):
    """Structural, not arithmetical: one read, and both numbers have to come from it.

    The call is counted *and* its return value is kept, so the assertion is "this response
    is explainable by the single catalog read the route made" - which a second query cannot
    satisfy even when it happens to agree today. A finance caller has 4 of the 5 rows and 1
    of the 2 ready documents, so a global count is visible from here too.
    """
    reads = []
    real = chat.list_document_catalog

    async def spy(request):
        result = await real(request)
        reads.append((request, result))
        return result

    monkeypatch.setattr(chat, "list_document_catalog", spy)

    body = client.get(SUMMARY_PATH, headers=_headers(username)).json()

    assert len(reads) == 1, f"两列各查一次目录，就是各说各话的起点（实测 {len(reads)} 次）"
    request, rows = reads[0][0], reads[0][1]["documents"]
    assert request is not None, "复用别处的判定要拿到活的 Request，喂 None 是内部旁路"
    assert body["documents"] == len(rows)
    assert body["documents_ready"] == _ready_of(rows)
    assert (body["documents"], body["documents_ready"]) == VISIBLE[username]


@pytest.mark.parametrize(
    ("statuses", "expected_ready"),
    [
        (("ready", "pending"), 1),
        (("ready", "ready"), 2),
        (("parsing", "failed"), 0),
    ],
    ids=["one-of-two", "both", "neither"],
)
def test_the_count_reads_a_field_and_not_a_list_length(
    client, document_store, statuses, expected_ready
):
    """Three catalogs of the same size, three different answers.

    ``documents`` is a list length and always was (R14-A1 counts what the panel lists);
    this column is a count of a value on those rows, so it has to move while the total
    stands still.
    """
    for filename, status in zip(("alpha.pdf", "beta.pdf"), statuses):
        document_store.add(
            filename,
            department="finance",
            owner="finance-manager",
            parse_status=status,
        )

    body = client.get(SUMMARY_PATH, headers=_headers("finance-manager")).json()

    assert body["documents"] == 2
    assert body["documents_ready"] == expected_ready


# =========================================== 判据③第一处：ready 只认解析状态那一个值


@pytest.mark.parametrize("status", ["pending", "parsing", "failed"])
def test_no_other_parse_status_counts_as_ready(client, document_store, status):
    """``PARSE_STATUSES`` holds four values and exactly one of them is done.

    A half-parsed document and one that produced no text are both 「还没解析完」 to the
    employee reading the tile; folding either in would be the good-news sentence R274
    refused to keep writing by hand.
    """
    document_store.add(
        "only.pdf", department="finance", owner="finance-manager", parse_status=status
    )

    body = client.get(SUMMARY_PATH, headers=_headers("finance-manager")).json()

    assert (body["documents"], body["documents_ready"]) == (1, 0)


def test_the_value_dashboard_counts_is_a_member_of_the_catalog_domain():
    """A rename inside ``PARSE_STATUSES`` has to be caught by a test, not by a tile.

    test_r49_upload_contract.py:402 pins the domain against the database CHECK; this pin
    ties the literal copy in ``app/api/v1/dashboard.py`` to it, so the two cannot drift.
    """
    assert dashboard._PARSE_STATUS_READY in catalog.PARSE_STATUSES
    assert catalog.PARSE_STATUSES == ("pending", "parsing", "ready", "failed")


# ============================= 判据③第二处：本列落地之前的历史行怎么算（如实钉，不放宽）


def test_a_row_that_recorded_no_parse_status_counts_as_not_ready(client, document_store):
    """The documented understatement: NULL normalises to ``pending``, so it is not ready.

    Pinned as-is on purpose. ``catalog._normalise_parse_status`` has already folded the
    difference away by the time this endpoint sees the row, so the response cannot offer a
    legacy split without a second read - and widening the count to make the number look
    better is the wrong direction: a tile that says 全部已解析 has to be able to mean it.
    """
    document_store.add_before_the_column_existed(
        "old-plan.pdf", department="finance", owner="finance-manager"
    )
    document_store.add(
        "new-plan.pdf", department="finance", owner="finance-manager", parse_status="ready"
    )
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    rows = client.get(CATALOG_PATH, headers=headers).json()["documents"]
    legacy = [row for row in rows if row["filename"] == "old-plan.pdf"]

    assert len(legacy) == 1, "历史行仍然看得见、仍然计入总数，这一列才需要说明它偏小"
    assert legacy[0]["parse_status"] == "pending", "NULL 归一成 pending 是本列语义的前提"
    assert (body["documents"], body["documents_ready"]) == (2, 1)


# ============================= 判据③第三处：解析完成 ≠ 可检索（index_status 是另一列）


def test_ready_counts_parsing_not_indexing_in_both_directions(client, document_store):
    """An excluded-but-parsed document is ready; an indexed-but-parsing one is not.

    The two columns answer different questions and the tile is written against the parse
    one (「N 篇还没解析完」). Reading this column as 「能被问到的篇数」 would quietly be a
    second contract, and the index policy is orthogonal by design.
    """
    document_store.add(
        "parsed-but-excluded.pdf",
        department="finance",
        owner="finance-manager",
        parse_status="ready",
        index_status=INDEX_STATUS_EXCLUDED,
        index_reason=REASON_TOO_SMALL,
    )
    document_store.add(
        "indexed-but-parsing.pdf",
        department="finance",
        owner="finance-manager",
        parse_status="parsing",
        index_status=INDEX_STATUS_INDEXED,
    )
    headers = _headers("finance-manager")

    body = client.get(SUMMARY_PATH, headers=headers).json()
    rows = client.get(CATALOG_PATH, headers=headers).json()["documents"]
    by_name = {row["filename"]: row for row in rows}

    assert by_name["parsed-but-excluded.pdf"]["parse_status"] == "ready"
    assert by_name["parsed-but-excluded.pdf"]["index_status"] == INDEX_STATUS_EXCLUDED
    assert by_name["indexed-but-parsing.pdf"]["index_status"] == INDEX_STATUS_INDEXED
    assert by_name["indexed-but-parsing.pdf"]["parse_status"] == "parsing"
    # 数进 ready 的那一篇，正是索引策略不要的那一篇；没被数的那一篇，恰恰是已经可检索的。
    # 两列在这里都是 1 是巧合，所以断言点名到文件，不比大小。
    assert _ready_of(rows) == 1
    assert (body["documents"], body["documents_ready"]) == (2, 1)


# ================================= 判据⑥：这一列恒在；没过那道门则一个字都不给


@pytest.mark.parametrize("username", sorted(VISIBLE))
def test_the_column_is_present_and_an_integer_for_every_signed_in_caller(
    client, corpus, username
):
    """Not conditional, not nullable, never a string.

    The frontend folds absence into 「已解析篇数未记录」 and reads only a number as an
    answer, so the backend owns the guarantee that the key is always there.
    """
    body = client.get(SUMMARY_PATH, headers=_headers(username)).json()

    assert "documents_ready" in body, "省掉这一格就是让前端永远说没记录"
    assert isinstance(body["documents_ready"], int)
    assert not isinstance(body["documents_ready"], bool)


def test_the_column_survives_the_day_there_are_no_documents_at_all(client, document_store):
    """An empty tenant answers 0/0 - a real count, not an omitted key.

    Here absence and zero would look the same, so the callers with rows above are what
    pins the difference; this case only proves the empty day does not drop the column.
    """
    body = client.get(SUMMARY_PATH, headers=_headers("root-admin")).json()

    assert body["documents"] == 0
    assert body["documents_ready"] == 0


def test_the_column_is_not_traded_away_when_the_alerts_key_is_omitted(client, corpus):
    """``alerts`` disappears for a caller without alert rights; the counts do not.

    One omitted key is a permission answer (R14-A1); two is a payload the overview cannot
    render. The two omissions must not be confused.
    """
    response = client.get(SUMMARY_PATH, headers=_headers("finance-staff"))

    assert response.status_code == 200
    body = response.json()
    assert "alerts" not in body
    assert (body["documents"], body["documents_ready"]) == VISIBLE["finance-staff"]


@pytest.mark.parametrize(
    ("username", "code"),
    [(None, 401), ("outside-auditor", 403)],
    ids=["anonymous", "no-analyze-grant"],
)
def test_the_new_column_leaks_nothing_before_the_analyze_gate(client, corpus, username, code):
    """The gate is unchanged: a caller who cannot ask cannot read either count.

    Checked against the whole body text rather than the parsed keys - a number smuggled
    into an error message is still a number.
    """
    headers = None if username is None else _headers(username)

    response = client.get(SUMMARY_PATH, headers=headers)

    assert response.status_code == code
    assert "documents_ready" not in response.text
    assert "documents" not in response.text


def test_the_measured_readout_for_two_identities_on_one_corpus(client, corpus):
    """One corpus, two scopes, printed - the numbers a manager and a clerk get.

    The wider scope sees both more documents and more parsed ones, and neither
    column is the tenant total for the other caller. Measured 2026-09-26 on the
    offline catalog above: five rows, two of them parsed.
    """
    admin = client.get(SUMMARY_PATH, headers=_headers("root-admin")).json()
    staff = client.get(SUMMARY_PATH, headers=_headers("finance-staff")).json()

    print(
        "R284 readout  "
        f"root-admin: documents={admin['documents']} documents_ready={admin['documents_ready']}  |  "
        f"finance-staff: documents={staff['documents']} documents_ready={staff['documents_ready']}"
    )

    assert (admin["documents"], admin["documents_ready"]) == VISIBLE["root-admin"]
    assert (staff["documents"], staff["documents_ready"]) == VISIBLE["finance-staff"]
    assert admin["documents_ready"] > staff["documents_ready"]
