"""The legacy text endpoint must not become an unscoped retrieval path."""

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str, department: str, role: str = "staff") -> dict[str, str]:
    return {"id": username, "username": username, "role": role, "department": department}


class _AnsweringModel:
    def __init__(self):
        self.prompts = []

    def chat(self, messages=None, source=None, stream=True):
        self.prompts.append(messages[0]["content"])
        delta = SimpleNamespace(content="回答完成")
        return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]


def test_legacy_chat_is_not_anonymous():
    from app.main import app

    response = TestClient(app).post("/api/v1/chat", json={"message": "残值率是多少"})

    assert response.status_code == 401


def test_legacy_chat_refuses_retrieval_without_a_department_scope(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user("nodept", ""))

    class _ForbiddenRetriever:
        def search(self, *args, **kwargs):
            raise AssertionError("unscoped principals must not reach the vector store")

    monkeypatch.setattr(chat, "retriever", _ForbiddenRetriever())

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "残值率是多少"},
        headers=_headers("nodept"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "authorization_unavailable"


def test_legacy_chat_scopes_retrieval_and_drops_unlisted_hits(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user("staff-a", "dept-a"))
    captured: dict[str, object] = {}
    hits = [
        {"content": "公开制度", "source": "handbook.txt", "chunk_index": 0,
         "classification": 1, "department": "dept-a"},
        {"content": "E2E-SECRET", "source": "other-dept.txt", "chunk_index": 0,
         "classification": 1, "department": "dept-b"},
        {"content": "E2E-CONFIDENTIAL", "source": "confidential.txt", "chunk_index": 0,
         "classification": 3, "department": "dept-a"},
        {"content": "E2E-NO-METADATA", "source": "legacy.txt", "chunk_index": 0},
    ]

    class _CapturingRetriever:
        def search(self, query, k=5, where=None):
            captured["query"] = query
            captured["where"] = where
            return hits

    model = _AnsweringModel()
    monkeypatch.setattr(chat, "retriever", _CapturingRetriever())
    monkeypatch.setattr(chat, "model_handler", model)

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "残值率是多少"},
        headers=_headers("staff-a"),
    )

    assert response.status_code == 200
    assert response.text == "回答完成"
    where = captured["where"]
    assert where["$and"][0]["classification"]["$in"] == [1]
    assert where["$and"][1]["department"]["$in"] == ["dept-a"]
    assert len(model.prompts) == 1
    prompt = model.prompts[0]
    assert "公开制度" in prompt
    for forbidden in ("E2E-SECRET", "E2E-CONFIDENTIAL", "E2E-NO-METADATA"):
        assert forbidden not in prompt


def test_legacy_chat_keeps_internal_failure_details_off_the_wire(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user("staff-b", "dept-b"))

    class _FailingRetriever:
        def search(self, query, k=5, where=None):
            raise OSError("connection refused 10.0.5.9:11434 /api/embeddings")

    monkeypatch.setattr(chat, "retriever", _FailingRetriever())

    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "残值率是多少"},
        headers=_headers("staff-b"),
    )

    assert response.status_code == 200
    assert "[错误]" in response.text
    for leak in ("10.0.5.9", "11434", "connection refused"):
        assert leak not in response.text
