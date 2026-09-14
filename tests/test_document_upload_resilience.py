import asyncio
import io
from concurrent.futures import Future
from pathlib import Path

from fastapi import UploadFile
import pytest


def test_upload_rejects_a_client_path_before_writing_files(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from fastapi import HTTPException

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    upload = UploadFile(filename="nested/policy.txt", file=io.BytesIO(b"policy"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_upload_enforces_size_limit_and_removes_partial_file(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools
    from fastapi import HTTPException

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "MAX_DOCUMENT_UPLOAD_BYTES", 4)
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="policy.txt", file=io.BytesIO(b"12345"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_embedding_failure_skips_remaining_chunks_during_cooldown(monkeypatch):
    from app.rag import retriever

    calls = 0

    def unavailable(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("Ollama unavailable")

    monkeypatch.setattr(retriever.urllib.request, "urlopen", unavailable)

    embeddings = retriever.OllamaEmbeddings()
    result = embeddings.embed_documents(["first chunk", "second chunk"])

    assert calls == 1
    assert len(result) == 2
    assert all(vector == [0.0] * 768 for vector in result)


def test_embedding_uses_a_short_default_timeout(monkeypatch):
    from app.rag.retriever import OllamaEmbeddings

    monkeypatch.delenv("OLLAMA_EMBED_TIMEOUT", raising=False)

    assert OllamaEmbeddings().timeout == 1.0


def test_upload_keeps_document_when_optional_metadata_store_is_down(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path: "document content")
    monkeypatch.setattr(chat, "_upsert_document", lambda *args: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(chat, "record_document_version", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="policy.txt", file=io.BytesIO(b"policy"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert response["stored_name"] != "policy__v1.txt"
    assert (tmp_path / response["stored_name"]).exists()


def test_upload_moves_blocking_parsing_and_indexing_off_the_event_loop():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

    assert "await asyncio.to_thread(load_document, file_path)" in source
    assert "await asyncio.to_thread(" in source


def test_upload_schedules_bm25_rebuild_without_waiting_for_it(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    class FakeExecutor:
        def __init__(self):
            self.submitted = []

        def submit(self, function, *args):
            self.submitted.append((function, args))
            return Future()

    executor = FakeExecutor()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(chat, "_executor", executor)

    upload = UploadFile(filename="async-index.txt", file=io.BytesIO(b"async index"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert executor.submitted == [(tools.rebuild_bm25, ())]


def test_document_version_uses_local_files_when_postgres_is_offline(tmp_path, monkeypatch):
    from app.documents import catalog

    (tmp_path / "policy__v1.txt").write_text("first", encoding="utf-8")
    (tmp_path / "policy__v2.txt").write_text("second", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False, raising=False)
    monkeypatch.setattr(
        catalog,
        "_conn",
        lambda: (_ for _ in ()).throw(AssertionError("offline mode must not connect to PostgreSQL")),
    )

    assert catalog.peek_next_document_version("policy.txt") == 3
    metadata = catalog.record_document_version(
        "policy.txt",
        classification=1,
        department="",
        storage_path=str(tmp_path / "policy__v3.txt"),
        version=3,
    )

    assert metadata["version"] == 3


def test_upload_skips_optional_metadata_sync_when_postgres_is_offline(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    metadata_synced = False

    def unexpected_metadata_sync(*args, **kwargs):
        nonlocal metadata_synced
        metadata_synced = True
        raise AssertionError("offline upload must not attempt metadata sync")

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(chat, "_upsert_document", unexpected_metadata_sync)
    monkeypatch.setattr(chat, "record_document_version", unexpected_metadata_sync)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="offline.txt", file=io.BytesIO(b"offline"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert metadata_synced is False


def test_document_retriever_batches_large_collection_writes():
    from app.rag.retriever import DocumentRetriever

    class FakeCollection:
        def __init__(self):
            self.calls = []

        def get(self, where=None):
            return {"ids": [], "metadatas": []}

        def add(self, **kwargs):
            self.calls.append(kwargs)

    class FakeSplitter:
        def split_text(self, content):
            return [f"chunk-{i}" for i in range(4500)]

    class FakeEmbedding:
        def embed_documents(self, texts):
            return [[0.0] * 3 for _ in texts]

    retriever = DocumentRetriever.__new__(DocumentRetriever)
    retriever.collection = FakeCollection()
    retriever.splitter = FakeSplitter()
    retriever.embedding = FakeEmbedding()

    ok, msg = DocumentRetriever.add_document(retriever, "big.txt", "x" * 10)

    assert ok is True
    assert "4500" in msg
    assert len(retriever.collection.calls) == 3
    assert [len(call["ids"]) for call in retriever.collection.calls] == [2000, 2000, 500]


def test_pdf_loader_uses_local_pypdf_extraction(monkeypatch):
    from app.rag import loader

    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, path):
            self.path = path
            self.pages = [FakePage("第一页"), FakePage("第二页")]

    monkeypatch.setattr(loader, "PdfReader", FakeReader)

    assert loader.load_pdf("demo.pdf") == "第一页\n\n第二页"


def test_upload_returns_clear_error_when_pdf_parse_fails(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from fastapi import HTTPException

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "build_storage_name", lambda filename, version: f"{Path(filename).stem}__v{version}.pdf")
    monkeypatch.setattr(chat, "load_document", lambda path: (_ for _ in ()).throw(ValueError("boom")))

    upload = UploadFile(filename="policy.pdf", file=io.BytesIO(b"%PDF-1.4 test"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 500
    assert "文档解析失败" in exc_info.value.detail
