"""A failure has to answer with a status, and an unscored hit must not claim a score."""

import pytest
from fastapi.testclient import TestClient

from app.rag.retrieval_pipeline import format_relevance


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username, department):
    return {"id": username, "username": username, "role": "manager", "department": department}


@pytest.mark.parametrize(
    "hit,expected",
    [
        ({"_score": 0.873}, "0.87"),
        ({"_score": "0.5"}, "0.50"),
        ({}, "未评分"),
        ({"_score": None}, "未评分"),
        ({"_score": "?"}, "未评分"),
    ],
)
def test_relevance_text_only_claims_a_number_when_there_is_one(hit, expected):
    assert format_relevance(hit) == expected


def test_an_unsupported_chart_type_is_refused_with_a_status(monkeypatch):
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))

    response = TestClient(app).post(
        "/api/v1/chart",
        headers=_headers("finance-manager"),
        json={"type": "sankey", "labels": ["a"], "values": [1]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported_chart_type"


def test_a_chart_a_departmentless_owner_could_not_keep_is_refused_before_it_runs(monkeypatch):
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, ""))

    response = TestClient(app).post(
        "/api/v1/chart",
        headers=_headers("no-department"),
        json={"type": "bar", "labels": ["a"], "values": [1]},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "department_scope_required"


def test_an_unsupported_export_format_is_refused_with_a_status(monkeypatch):
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))

    response = TestClient(app).post(
        "/api/v1/export",
        headers=_headers("finance-manager"),
        json={"format": "docx", "title": "t", "sections": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported_export_format"
