"""Route-level contract tests for the read-only management plane.

These tests assert authentication, stable error codes, limit clamping and structural
bounds. They never assert recall quality: this machine has no chromadb / rank_bm25 /
jieba / sentence_transformers, so retrieval honesty is asserted as a *declared*
degradation instead of a score.
"""

import json

import numpy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import observability

DEBUG_PATH = "/api/v1/retrieval/debug"
TRACE_PATH = "/api/v1/traces/{trace_id}"
EVALUATIONS_PATH = "/api/v1/evaluations"
AUDIT_PATH = "/api/v1/audit/events"


class _FakePipeline:
    def __init__(self, document_count=1, rewrite_count=1, scores=None):
        self.calls = []
        self.document_count = document_count
        self.rewrite_count = rewrite_count
        self.scores = scores or []

    def documents(self):
        docs = []
        for index in range(self.document_count):
            score = self.scores[index] if index < len(self.scores) else 0.5 + index / 100
            docs.append(
                {
                    "content": "报销制度 " + ("相" * 4_000),
                    "source": "差旅费报销制度.pdf" + "x" * 5_000,
                    "chunk_index": index,
                    "classification": 2,
                    "department": "研发部",
                    "_score": score,
                }
            )
        return docs

    def search_for_principal(self, query, principal, top_k=5, where=None, pred=None):
        self.calls.append({"query": query, "top_k": top_k, "username": principal.username})
        return self.documents(), [f"改写 {index}" for index in range(self.rewrite_count)]


@pytest.fixture()
def users(monkeypatch):
    """Back the authentication middleware with an in-memory user table."""
    from app.common import auth

    registry = {}

    def add(username, role, **fields):
        registry[username] = {
            "id": f"u-{username}",
            "username": username,
            "role": role,
            "department": "研发部",
            **fields,
        }
        return username

    monkeypatch.setattr(auth, "get_user", lambda username: registry.get(username))
    return add


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def app_client(users):
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def audit_recorder(monkeypatch):
    """Capture audit calls instead of asserting on another slice's storage."""
    from app.common import audit

    recorded = []

    def fake_record(principal, action, outcome, resource="", reason=""):
        recorded.append(
            {
                "username": getattr(principal, "username", "anonymous"),
                "action": action,
                "outcome": outcome,
                "resource": resource,
                "reason": reason,
            }
        )
        return dict(recorded[-1])

    monkeypatch.setattr(audit, "record_audit", fake_record)
    return recorded


@pytest.fixture()
def audit_source(monkeypatch):
    from app.common import audit

    state = {"events": []}
    monkeypatch.setattr(
        audit, "get_audit_events", lambda: [dict(event) for event in state["events"]]
    )
    return state


@pytest.fixture()
def trace_store(tmp_path, monkeypatch):
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "traces" / "events.jsonl")
    monkeypatch.setattr(observability, "_trace_store", lambda: store)
    return store


def _arguments(method):
    return {"json": {"query": "住宿费标准"}} if method == "post" else {}


def _envelope(response):
    detail = response.json()["detail"]
    assert set(detail) == {"code", "message", "retryable", "details"}, detail
    return detail


# ---------------------------------------------------------------- ① mounted paths


def test_the_four_management_paths_are_published_in_the_openapi_document(app_client):
    schema = app_client.get("/openapi.json").json()
    paths = schema["paths"]

    assert paths[DEBUG_PATH]["post"]["operationId"].startswith("retrieval_debug")
    assert "get" in paths[TRACE_PATH]
    assert "get" in paths[EVALUATIONS_PATH]
    assert "get" in paths[AUDIT_PATH]
    assert paths[DEBUG_PATH]["post"]["tags"] == ["observability"]

    error_reference = paths[DEBUG_PATH]["post"]["responses"]["401"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert error_reference.endswith("/ApiError")
    detail_schema = schema["components"]["schemas"]["ApiError"]["properties"]["detail"]
    assert detail_schema["$ref"].endswith("/ErrorEnvelope")


# ------------------------------------------------------------------ ② auth surface


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", DEBUG_PATH),
        ("get", "/api/v1/traces/trace-1"),
        ("get", EVALUATIONS_PATH),
        ("get", AUDIT_PATH),
    ],
)
def test_anonymous_requests_are_rejected_before_the_handler(app_client, method, path):
    response = getattr(app_client, method)(path, **_arguments(method))
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", DEBUG_PATH),
        ("get", "/api/v1/traces/trace-1"),
        ("get", EVALUATIONS_PATH),
        ("get", AUDIT_PATH),
    ],
)
def test_a_request_without_a_principal_fails_closed_as_authentication_required(method, path):
    """The router itself must not infer an identity, and must not fall back to admin."""
    bare = FastAPI()
    bare.include_router(observability.router, prefix="/api/v1")

    response = getattr(TestClient(bare), method)(path, **_arguments(method))

    assert response.status_code == 401
    envelope = _envelope(response)
    assert envelope["code"] == "authentication_required"
    assert envelope["retryable"] is False


def test_staff_is_denied_traces_with_a_stable_code(app_client, users, audit_recorder):
    username = users("s3-staff-denied", "staff")

    response = app_client.get("/api/v1/traces/anything", headers=_headers(username))

    assert response.status_code == 403
    envelope = _envelope(response)
    assert envelope["code"] == "permission_denied"
    assert envelope["details"]["reason_code"] == "permission_denied"
    assert envelope["details"]["action"] == "audit:read"

    audit = app_client.get("/api/v1/audit/events", headers=_headers(username))
    assert audit.status_code == 403
    assert _envelope(audit)["code"] == "permission_denied"
    assert [event["outcome"] for event in audit_recorder] == ["denied", "denied"]


def test_an_auditor_reads_traces_and_audit_but_not_evaluations(app_client, users, trace_store, audit_source):
    auditor = users("s3-auditor", "auditor")
    trace_store.record_event(
        trace_id="trace-audit-1",
        request_id="req-1",
        event_type="retrieval.completed",
        status="completed",
        payload={"api_key": "super-secret", "sources": ["a.pdf"]},
    )
    audit_source["events"] = [
        {"username": "root", "role": "admin", "action": "resource:delete", "outcome": "allowed"},
        {"username": auditor, "role": "auditor", "action": "audit:read", "outcome": "denied"},
    ]

    replayed = app_client.get("/api/v1/traces/trace-audit-1", headers=_headers(auditor))
    assert replayed.status_code == 200
    body = replayed.json()
    assert body["event_count"] == 1
    assert body["events"][0]["payload"]["api_key"] == "[REDACTED]"

    events = app_client.get("/api/v1/audit/events", headers=_headers(auditor))
    assert events.status_code == 200
    assert [event["outcome"] for event in events.json()["events"]] == ["denied", "allowed"]

    evaluations = app_client.get("/api/v1/evaluations", headers=_headers(auditor))
    assert evaluations.status_code == 403
    envelope = _envelope(evaluations)
    assert envelope["code"] == "permission_denied"
    assert envelope["details"]["reason_code"] == "admin_role_required"


def test_a_denied_read_is_recorded_through_the_existing_audit_signature(
    app_client, users, audit_recorder
):
    username = users("s3-staff-record", "staff")

    app_client.get("/api/v1/audit/events", headers=_headers(username))

    assert audit_recorder == [
        {
            "username": username,
            "action": "audit:read",
            "outcome": "denied",
            "resource": "audit/events",
            "reason": "permission_denied",
        }
    ]


def test_an_administrator_without_a_department_is_admitted_by_retrieval(
    app_client, users, monkeypatch, trace_store, audit_recorder
):
    """e2: an administrator loses the department clause, not the right to ask.
    This case asserted 403 authorization_unavailable until the 2026-09-15 ruling in
    docs/handoff/2026-09-15-backend-followup-requests.md 6.2 replaced that behavior, so
    what it now pins is the shape of the widened scope: classification kept, the override
    named in the report and the trace, and a department-less manager still refused.
    """
    username = users("s3-orphan-admin", "admin", department="")
    pipeline = _FakePipeline(document_count=2)
    monkeypatch.setattr(observability, "_pipeline", lambda: pipeline)

    response = app_client.post(
        DEBUG_PATH, json={"query": "住宿费标准"}, headers=_headers(username)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["permission_filter"] == {"classification": {"$in": [1, 2, 3]}}
    assert "department" not in str(body["permission_filter"])
    assert body["scope_reason"] == "administrator_scope"
    replayed = trace_store.replay(body["trace_id"])
    assert replayed[0]["payload"]["scope_reason"] == "administrator_scope"
    assert replayed[0]["payload"]["permission_filter"] == {
        "classification": {"$in": [1, 2, 3]}
    }

    manager = users("s3-orphan-manager", "manager", department="")
    refused = app_client.post(
        DEBUG_PATH, json={"query": "住宿费标准"}, headers=_headers(manager)
    )

    assert refused.status_code == 403
    envelope = _envelope(refused)
    assert envelope["code"] == "authorization_unavailable"
    assert envelope["details"]["stage"] == "retrieval_scope"

# ------------------------------------------------------------------ ③ bounds


def test_top_k_above_the_ceiling_is_clamped_and_the_report_stays_bounded(
    app_client, users, monkeypatch, trace_store, audit_recorder
):
    username = users("s3-admin", "admin")
    pipeline = _FakePipeline(document_count=25, rewrite_count=30)
    monkeypatch.setattr(observability, "_pipeline", lambda: pipeline)

    response = app_client.post(
        DEBUG_PATH,
        json={"query": "住宿费标准", "top_k": 1000},
        headers=_headers(username),
    )

    assert response.status_code == 200
    body = response.json()
    assert pipeline.calls == [{"query": "住宿费标准", "top_k": 20, "username": username}]
    assert body["limits"] == {
        "default_top_k": 5,
        "max_top_k": 20,
        "requested_top_k": 1000,
        "applied_top_k": 20,
        "clamped": True,
    }
    assert len(body["results"]) == 20 == observability.MAX_TOP_K
    assert len(body["rewrites"]) == observability.MAX_REWRITES
    assert body["bounds"] == {
        "rewrites_total": 30,
        "rewrites_returned": 5,
        "results_total": 25,
        "results_returned": 20,
        "excerpt_max_chars": 240,
        "string_max_chars": 2_000,
        "truncated": True,
    }
    assert len(body["results"][0]["excerpt"]) <= observability.MAX_EXCERPT_CHARS
    assert body["requested_by"]["username"] == username
    assert body["scope_versions"]["server_verified"] is False
    assert [event["outcome"] for event in audit_recorder] == ["allowed"]


def test_a_missing_top_k_uses_the_default_and_a_non_positive_one_floors_at_one(
    app_client, users, monkeypatch, trace_store, audit_recorder
):
    username = users("s3-admin-default", "admin")
    pipeline = _FakePipeline()
    monkeypatch.setattr(observability, "_pipeline", lambda: pipeline)

    default_response = app_client.post(DEBUG_PATH, json={"query": "p"}, headers=_headers(username))
    floored_response = app_client.post(
        DEBUG_PATH, json={"query": "p", "top_k": 0}, headers=_headers(username)
    )

    assert default_response.json()["limits"]["applied_top_k"] == observability.DEFAULT_TOP_K
    assert default_response.json()["limits"]["clamped"] is False
    assert floored_response.json()["limits"]["applied_top_k"] == 1
    assert floored_response.json()["limits"]["clamped"] is True
    assert [call["top_k"] for call in pipeline.calls] == [5, 1]


def test_scores_are_normalised_to_json_scalars(
    app_client, users, monkeypatch, trace_store, audit_recorder
):
    username = users("s3-admin-scores", "admin")
    monkeypatch.setattr(
        observability,
        "_pipeline",
        lambda: _FakePipeline(
            document_count=3, scores=[numpy.float32(0.75), float("nan"), "not-a-score"]
        ),
    )

    body = app_client.post(
        DEBUG_PATH, json={"query": "p", "top_k": 3}, headers=_headers(username)
    ).json()

    assert [result["score"] for result in body["results"]] == [0.75, None, None]


def test_an_empty_or_oversized_query_is_a_validation_error(
    app_client, users, monkeypatch, trace_store, audit_recorder
):
    username = users("s3-admin-query", "admin")
    pipeline = _FakePipeline()
    monkeypatch.setattr(observability, "_pipeline", lambda: pipeline)

    empty = app_client.post(DEBUG_PATH, json={"query": "   "}, headers=_headers(username))
    oversized = app_client.post(
        DEBUG_PATH,
        json={"query": "a" * (observability.MAX_QUERY_CHARS + 1)},
        headers=_headers(username),
    )

    assert empty.status_code == 400
    assert _envelope(empty)["code"] == "validation_error"
    assert oversized.status_code == 400
    assert _envelope(oversized)["details"]["max_chars"] == observability.MAX_QUERY_CHARS
    assert pipeline.calls == []


def test_a_degraded_retrieval_stack_is_reported_as_degraded(app_client, users, monkeypatch, trace_store):
    import importlib.util

    username = users("s3-admin-env", "admin")
    monkeypatch.setattr(observability, "_pipeline", lambda: _FakePipeline())

    body = app_client.post(DEBUG_PATH, json={"query": "p"}, headers=_headers(username)).json()
    environment = body["retrieval_environment"]

    expected_missing = [
        name
        for name, _capability, _installed, _fallback in observability._RETRIEVAL_CAPABILITIES
        if importlib.util.find_spec(name) is None
    ]
    assert environment["missing_dependencies"] == expected_missing
    assert environment["degraded"] is bool(expected_missing)
    if not environment["optional_dependencies"]["chromadb"]:
        assert environment["engines"]["vector_store"] == "offline_json_collection"
    if not environment["optional_dependencies"]["jieba"]:
        assert environment["engines"]["tokenizer"] == "naive_char_or_whitespace"
    assert body["stages"][-1]["name"] == "reranked"


def test_trace_replay_is_paged_and_an_unknown_trace_is_not_found(app_client, users, trace_store):
    auditor = users("s3-auditor-paging", "auditor")
    for index in range(5):
        trace_store.record_event(
            trace_id="trace-page",
            request_id="req-1",
            event_type=f"step.{index}",
            status="completed",
            payload={"index": index},
        )

    page = app_client.get(
        "/api/v1/traces/trace-page", headers=_headers(auditor), params={"limit": 2}
    ).json()
    assert page["events_total"] == 5
    assert page["event_count"] == 2
    assert page["truncated"] is True
    assert [event["event_type"] for event in page["events"]] == ["step.0", "step.1"]

    over_ceiling = app_client.get(
        "/api/v1/traces/trace-page", headers=_headers(auditor), params={"limit": 10_000}
    ).json()
    assert over_ceiling["limits"]["applied_limit"] == observability.MAX_TRACE_EVENTS
    assert over_ceiling["limits"]["clamped"] is True
    assert over_ceiling["truncated"] is False

    missing = app_client.get("/api/v1/traces/never-recorded", headers=_headers(auditor))
    assert missing.status_code == 404
    assert _envelope(missing)["code"] == "resource_not_found"


def test_a_debug_run_can_be_replayed_through_the_trace_route(app_client, users, monkeypatch, trace_store):
    admin = users("s3-admin-replay", "admin")
    monkeypatch.setattr(observability, "_pipeline", lambda: _FakePipeline(document_count=2))

    report = app_client.post(
        DEBUG_PATH,
        json={"query": "住宿费标准", "index_version_id": "idx-1", "strategy_version": "hybrid-v1"},
        headers=_headers(admin),
    ).json()

    replay = app_client.get(
        report["replay_path"], headers=_headers(users("s3-auditor-replay", "auditor"))
    )

    assert replay.status_code == 200
    events = replay.json()["events"]
    assert events[0]["event_type"] == "retrieval.completed"
    assert events[0]["payload"]["index_version_id"] == "idx-1"
    assert events[0]["payload"]["candidate_count"] == 2


def test_audit_events_are_newest_first_filterable_and_limited(app_client, users, audit_source):
    auditor = users("s3-auditor-list", "auditor")
    audit_source["events"] = [
        {"username": "root", "role": "admin", "action": "resource:delete", "outcome": "allowed"},
        {"username": auditor, "role": "auditor", "action": "audit:read", "outcome": "denied"},
        {"username": "root", "role": "admin", "action": "resource:delete", "outcome": "allowed"},
    ]

    everything = app_client.get("/api/v1/audit/events", headers=_headers(auditor)).json()
    assert everything["order"] == "newest_first"
    assert [event["action"] for event in everything["events"]] == [
        "resource:delete",
        "audit:read",
        "resource:delete",
    ]
    assert everything["events_total"] == 3
    assert everything["recorded_total"] == 3

    filtered = app_client.get(
        "/api/v1/audit/events",
        headers=_headers(auditor),
        params={"outcome": "denied", "username": auditor},
    ).json()
    assert filtered["filters"] == {"outcome": "denied", "username": auditor}
    assert filtered["events_total"] == 1
    assert filtered["events"][0]["action"] == "audit:read"

    capped = app_client.get(
        "/api/v1/audit/events", headers=_headers(auditor), params={"limit": 9_999}
    ).json()
    assert capped["limits"]["applied_limit"] == observability.MAX_AUDIT_EVENTS
    assert capped["event_count"] == 3

    small = app_client.get(
        "/api/v1/audit/events", headers=_headers(auditor), params={"limit": 1}
    ).json()
    assert small["event_count"] == 1
    assert small["truncated"] is True


# ---------------------------------------------------------------- evaluations


def test_evaluations_lists_stored_reports_without_running_the_stack(
    tmp_path, app_client, users, monkeypatch, audit_recorder
):
    admin = users("s3-admin-eval", "admin")
    report = {
        "total": 30,
        "answer_correctness": 0.87,
        "evidence_coverage": 1.0,
        "unsupported_claim_rate": 0.03,
        "category_metrics": {"文档问答": {"correctness": 0.9, "total": 10}},
        "latency_ms": {"count": 30, "average": 812.5, "p95": 1400},
    }
    directory = tmp_path / "reports"
    directory.mkdir()
    (directory / "run-2026-09-14.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        "\n".join(
            json.dumps({"id": f"case-{index}", "category": "文档问答"}, ensure_ascii=False)
            for index in range(4)
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVALUATION_REPORT_DIRS", str(directory))
    monkeypatch.setenv("EVALUATION_SET_PATHS", str(suite))

    body = app_client.get("/api/v1/evaluations", headers=_headers(admin)).json()

    assert body["status"] == "reports_available"
    assert body["reports"][0]["id"] == "run-2026-09-14"
    assert body["reports"][0]["status"] == "ok"
    assert body["reports"][0]["metrics"] == {
        "total": 30,
        "answer_correctness": 0.87,
        "evidence_coverage": 1.0,
        "unsupported_claim_rate": 0.03,
        "latency_count": 30.0,
        "latency_average": 812.5,
        "latency_p95": 1400.0,
    }
    assert body["reports"][0]["category_count"] == 1
    assert body["evaluation_sets"][0]["case_count"] == 4
    assert body["evaluation_sets"][0]["categories"] == ["文档问答"]
    assert body["execution"]["runs_on_request"] is False
    assert audit_recorder == []


def test_evaluations_reports_an_absent_suite_and_no_reports(app_client, users, monkeypatch):
    admin = users("s3-admin-empty-eval", "admin")
    monkeypatch.setenv("EVALUATION_REPORT_DIRS", "tmp/_s3-no-such-reports")
    monkeypatch.setenv("EVALUATION_SET_PATHS", "tmp/_s3-no-such-suite.jsonl")

    body = app_client.get("/api/v1/evaluations", headers=_headers(admin)).json()

    assert body["status"] == "no_reports"
    assert body["reports"] == []
    assert body["evaluation_sets"] == [
        {
            "id": "_s3-no-such-suite",
            "path": "tmp/_s3-no-such-suite.jsonl",
            "exists": False,
            "case_count": 0,
            "categories": [],
            "truncated": False,
        }
    ]


def test_the_shipped_evaluation_set_is_discoverable_by_default(app_client, users, monkeypatch):
    admin = users("s3-admin-default-eval", "admin")
    monkeypatch.delenv("EVALUATION_SET_PATHS", raising=False)

    body = app_client.get("/api/v1/evaluations", headers=_headers(admin)).json()

    suites = {suite["path"] for suite in body["evaluation_sets"]}
    assert "tests/fixtures/business_evaluation_30.jsonl" in suites