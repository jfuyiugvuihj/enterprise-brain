"""跟进单 R21 判据①②④：embedding 失败不得被当成正常路径，全零向量不得入库。

覆盖四条钉死的口径：

* HTTP 404（模型没装）与超时各自抛带稳定原因码的异常，不返回占位向量；
* 熔断冷却期内不重发请求，但必须抛出原因，而不是批量发全零；
* 任何要进向量库的全零 / 错维度向量在写入闸门就被挡下；
* 查询侧退化到关键词腿时，命中带可区分的降级标注，且不拿占位向量去问向量库。
"""
import io
from urllib.error import HTTPError, URLError

import pytest

from app.rag import retriever as r
from app.rag.retriever import (
    EMBEDDING_DIM,
    EmbeddingError,
    EmbeddingUnavailableError,
    VectorWriteRejectedError,
)


@pytest.fixture(autouse=True)
def _isolate_diagnostics():
    r.reset_embedding_diagnostics()
    yield
    r.reset_embedding_diagnostics()


def _http_error(code: int = 404, body: bytes = b'{"error":"model not found"}'):
    return HTTPError(
        "http://localhost:11434/api/embeddings", code, "Not Found", None, io.BytesIO(body)
    )


def _vector(value: float = 0.1, dim: int = EMBEDDING_DIM) -> list:
    vector = [0.0] * dim
    vector[-1] = value
    return vector


class _FakeSplitter:
    def __init__(self, chunks=None):
        self.chunks = chunks or ["住宿费标准为500元"]

    def split_text(self, content):
        return list(self.chunks)


class _FakeCollection:
    """Chroma collection 替身：记录每一次 add/query/get，越界调用直接炸。"""

    def __init__(self, rows=None, query_error=None):
        self.rows = rows or []
        self.added = []
        self.queried = []
        self.gets = []
        self.query_error = query_error

    def get(self, where=None):
        self.gets.append(where)
        rows = self.rows
        if where:
            rows = [
                row for row in rows
                if all(row["metadata"].get(key) == value for key, value in where.items())
            ]
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["document"] for row in rows],
            "metadatas": [row["metadata"] for row in rows],
        }

    def add(self, **kwargs):
        self.added.append(kwargs)

    def delete(self, ids=None, **kwargs):
        return None

    def query(self, **kwargs):
        self.queried.append(kwargs)
        if self.query_error is not None:
            raise AssertionError("降级路径不得再问向量库")
        page = self.rows[: kwargs["n_results"]]
        return {
            "documents": [[row["document"] for row in page]],
            "metadatas": [[row["metadata"] for row in page]],
        }


class _ScriptedEmbeddings:
    """只换 embedding 这一个零件：写库路径的测试不该依赖网络，也不该依赖 Ollama 在不在。"""

    def __init__(self, vectors=None, failure=None):
        self.vectors = vectors
        self.failure = failure
        self.last_error = None
        self.query_calls = 0
        self.document_calls = 0
        if failure is not None:
            self.last_error = {"reason": failure.reason, "detail": str(failure), "at": 0.0}

    def embed_documents(self, texts):
        self.document_calls += 1
        if self.failure is not None:
            return [[0.0] * EMBEDDING_DIM for _ in texts]
        return list(self.vectors)[: len(texts)]

    def embed_query(self, text):
        self.query_calls += 1
        if self.failure is not None:
            raise self.failure
        return _vector()


def _retriever(collection, embedding, splitter=None):
    """__new__ 构造：不跑 __init__，因此既不建 PersistentClient 也不碰 Ollama。"""
    retriever = r.DocumentRetriever.__new__(r.DocumentRetriever)
    retriever.collection = collection
    retriever.embedding = embedding
    retriever.splitter = splitter or _FakeSplitter()
    retriever.chroma_dir = ""
    return retriever


# ------------------------------------------------------------- 判据①：失败即抛并留原因


def test_http_404_raises_a_model_missing_reason_instead_of_a_normal_path(monkeypatch):
    calls = []

    def refuse(request, timeout=None):
        calls.append((request.full_url, timeout))
        raise _http_error(404)

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "model_missing"
    assert "nomic-embed-text" in str(failure.value)
    # 服务端原文要留在异常里，否则运维分不清"模型没装"和"服务没起"
    assert "not found" in str(failure.value)
    assert len(calls) == 1


def test_the_default_timeout_is_no_longer_one_second(monkeypatch):
    monkeypatch.delenv("OLLAMA_EMBED_TIMEOUT", raising=False)

    embeddings = r.OllamaEmbeddings()

    assert embeddings.timeout >= 10, "冷加载模型时 1 秒必然不够，超时不得再被当成常态"
    assert r.EMBED_TIMEOUT_DEFAULT_SECONDS == embeddings.timeout


def test_a_timeout_raises_a_timeout_reason_and_is_not_a_normal_path(monkeypatch):
    def hang(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(r.urllib.request, "urlopen", hang)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "timeout"
    assert failure.value.reason != "model_missing", "超时与模型没装必须是两个原因码"


def test_a_refused_connection_is_labelled_as_refused_and_not_as_a_timeout(monkeypatch):
    def refuse(request, timeout=None):
        raise URLError(ConnectionRefusedError("connection refused"))

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "connection_refused"


def test_a_5xx_is_labelled_as_a_server_error(monkeypatch):
    def boom(request, timeout=None):
        raise _http_error(502, b'{"error":"ollama is busy"}')

    monkeypatch.setattr(r.urllib.request, "urlopen", boom)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "server_error"


def test_cooldown_stops_calling_the_api_but_never_emits_placeholder_vectors(monkeypatch):
    calls = []

    def refuse(request, timeout=None):
        calls.append(request.full_url)
        raise _http_error(404)

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError):
        embeddings.embed_query("first")
    with pytest.raises(EmbeddingUnavailableError) as second:
        embeddings.embed_query("second")

    assert len(calls) == 1, "熔断期内不得重发请求"
    assert second.value.reason == "cooldown"
    # 冷却不是免罪理由：异常里要能看出它冷却的根因是模型没装
    assert "model_missing" in str(second.value)


def test_a_response_without_a_usable_vector_is_rejected(monkeypatch):
    class _Response:
        status = 200

        def read(self):
            return b'{"embedding": []}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(r.urllib.request, "urlopen", lambda request, timeout=None: _Response())
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "empty_vector"


def test_a_wrong_width_response_is_rejected(monkeypatch):
    class _Response:
        status = 200

        def read(self):
            return b'{"embedding": [0.1, 0.2]}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(r.urllib.request, "urlopen", lambda request, timeout=None: _Response())
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingUnavailableError) as failure:
        embeddings.embed_query("住宿费标准")

    assert failure.value.reason == "dimension_mismatch"


def test_the_last_failure_reason_is_readable_without_opening_a_socket(monkeypatch):
    def refuse(request, timeout=None):
        raise _http_error(404)

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    embeddings = r.OllamaEmbeddings()

    with pytest.raises(EmbeddingError):
        embeddings.embed_query("住宿费标准")

    state = r.embedding_diagnostics()
    assert state["last_failure"]["reason"] == "model_missing"
    assert state["last_failure"]["model"] == embeddings.model
    assert embeddings.last_error["reason"] == "model_missing"


# ---------------------------------------------------------- 判据②：全零向量不得入库


def test_the_write_gate_refuses_an_all_zero_vector():
    with pytest.raises(VectorWriteRejectedError) as failure:
        r.assert_writable_embeddings([[0.0] * EMBEDDING_DIM], 1, cause="model_missing")

    assert failure.value.reason == "all_zero_vector"
    assert "model_missing" in str(failure.value), "拒写要能看出向量是哪一步烂掉的"
    assert r.embedding_diagnostics()["rejected_writes"] == 1


def test_the_write_gate_refuses_a_wrong_dimension_vector():
    with pytest.raises(VectorWriteRejectedError) as failure:
        r.assert_writable_embeddings([[0.1] * 384], 1)

    assert failure.value.reason == "dimension_mismatch"


def test_the_write_gate_refuses_a_missing_vector_row():
    with pytest.raises(VectorWriteRejectedError) as failure:
        r.assert_writable_embeddings([_vector(), None], 2)

    assert failure.value.reason == "not_a_vector"


def test_the_write_gate_refuses_a_shorter_vector_list_than_the_chunks():
    with pytest.raises(VectorWriteRejectedError) as failure:
        r.assert_writable_embeddings([_vector()], 3)

    assert failure.value.reason == "vector_count_mismatch"


def test_the_write_gate_lets_a_real_vector_through():
    assert r.assert_writable_embeddings([_vector(), _vector(0.5)], 2) is None


def test_add_document_never_hands_a_zero_vector_to_the_collection():
    collection = _FakeCollection()
    failure = EmbeddingUnavailableError("model not found", reason="model_missing")
    retriever = _retriever(collection, _ScriptedEmbeddings(failure=failure))

    with pytest.raises(VectorWriteRejectedError) as raised:
        retriever.add_document("policy.txt", "住宿费标准为500元", 1, "finance")

    assert raised.value.reason == "all_zero_vector"
    assert collection.added == [], "拒收必须是挡下，而不是换个值继续写"


def test_add_document_writes_a_real_vector_through_the_gate():
    collection = _FakeCollection()
    embedding = _ScriptedEmbeddings(vectors=[_vector(), _vector(0.25)])
    retriever = _retriever(collection, embedding, _FakeSplitter(["a", "b"]))

    ok, message = retriever.add_document("policy.txt", "住宿费标准为500元", 1, "finance")

    assert ok is True
    assert len(collection.added) == 1
    assert [len(row) for row in collection.added[0]["embeddings"]] == [EMBEDDING_DIM] * 2
    assert all(any(row) for row in collection.added[0]["embeddings"])


def test_a_real_indexing_run_fails_loudly_when_the_model_is_not_installed(monkeypatch, tmp_path):
    """端到端：真 DocumentRetriever + 真 Chroma，只有 Ollama 换成 404。"""

    def refuse(request, timeout=None):
        raise _http_error(404)

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    retriever = r.DocumentRetriever(str(tmp_path))

    with pytest.raises(EmbeddingError):
        retriever.add_document("policy.txt", "住宿费标准为500元", 1, "finance")

    assert retriever.list_documents() == [], "失败了就不许留下任何索引痕迹"


# ------------------------------------------------- 判据（查询侧）：可见降级，不静默


def _rows():
    return [
        {
            "id": "a_0",
            "document": "住宿费标准为500元",
            "metadata": {
                "filename": "a.md", "chunk_index": 0,
                "classification": 1, "department": "finance",
            },
        },
        {
            "id": "b_0",
            "document": "员工培训费用的报销范围",
            "metadata": {
                "filename": "b.md", "chunk_index": 0,
                "classification": 2, "department": "hr",
            },
        },
    ]


def test_the_query_leg_degrades_to_keywords_and_marks_every_hit():
    collection = _FakeCollection(rows=_rows(), query_error=True)
    failure = EmbeddingUnavailableError("model not found", reason="model_missing")
    retriever = _retriever(collection, _ScriptedEmbeddings(failure=failure))

    hits = retriever.search("住宿费标准", k=3)

    assert hits, "降级腿必须还能召回内容，不能悄悄返回空"
    # 词法交集按重合字数排序：整句同词的排第一，只撞见一个"费"字的排后面
    assert hits[0]["content"] == "住宿费标准为500元"
    assert all(hit["retrieval_mode"] == retriever.MODE_KEYWORD for hit in hits)
    assert retriever.last_search_mode == retriever.MODE_KEYWORD
    assert retriever.last_search_reason == "model_missing"
    assert collection.queried == [], "embedding 挂了就不许再拿占位向量去问向量库"
    assert r.embedding_diagnostics()["degraded_searches"] == 1


def test_a_degraded_search_still_pushes_the_permission_filter_before_truncating():
    collection = _FakeCollection(rows=_rows(), query_error=True)
    failure = EmbeddingUnavailableError("timed out", reason="timeout")
    retriever = _retriever(collection, _ScriptedEmbeddings(failure=failure))

    hits = retriever.search("住宿费标准", k=3, where={"department": "hr"})

    assert collection.gets == [{"department": "hr"}], "降级腿也必须先按 where 筛再截断"
    assert [hit["source"] for hit in hits] == ["b.md"], "finance 的 chunk 不得因降级而绕过过滤"


def test_degraded_hits_keep_the_fail_closed_classification():
    rows = [
        {
            "id": "c_0",
            "document": "住宿费标准",
            "metadata": {"filename": "c.md", "chunk_index": 0},
        }
    ]
    collection = _FakeCollection(rows=rows, query_error=True)
    failure = EmbeddingUnavailableError("refused", reason="connection_refused")
    retriever = _retriever(collection, _ScriptedEmbeddings(failure=failure))

    hits = retriever.search("住宿费标准", k=3)

    assert len(hits) == 1
    assert hits[0]["classification"] is None, "缺密级的行不得在降级腿上被补成 1 级"
    assert hits[0]["retrieval_mode"] == retriever.MODE_KEYWORD


def test_a_working_embedding_keeps_the_semantic_marker():
    collection = _FakeCollection(rows=_rows())
    retriever = _retriever(collection, _ScriptedEmbeddings())

    hits = retriever.search("住宿费标准", k=3)

    assert hits
    assert all(hit["retrieval_mode"] == retriever.MODE_SEMANTIC for hit in hits)
    assert retriever.last_search_mode == retriever.MODE_SEMANTIC
    assert retriever.last_search_reason == ""
    assert len(collection.queried) == 1
    assert collection.queried[0]["query_embeddings"] == [_vector()]
    assert r.embedding_diagnostics()["degraded_searches"] == 0


def test_a_backend_that_stores_no_vectors_asks_the_embedding_model_nothing(tmp_path, monkeypatch):
    """不存向量的后端：写库路径一个 embedding 请求都不该发（R21 收口的漏网之处）。"""
    monkeypatch.setattr(r, "chromadb", None)
    retriever = r.DocumentRetriever(str(tmp_path))
    asked: list[int] = []

    def refuse(texts):
        asked.append(len(texts))
        raise AssertionError("不存向量的后端不该为写库去问 embedding")

    retriever.embedding.embed_documents = refuse

    added, _ = retriever.add_document("policy.txt", "住宿费标准为500元")

    assert added is True
    assert asked == []


def test_the_keyword_only_backend_never_claims_to_hold_vectors(tmp_path, monkeypatch):
    """离线 _JsonCollection 没有向量列：写它就不该带 embeddings，检索按降级标注。"""
    monkeypatch.setattr(r, "chromadb", None)
    retriever = r.DocumentRetriever(str(tmp_path))
    written = []
    original_add = retriever.collection.add

    def record(**kwargs):
        written.append(kwargs)
        return original_add(**kwargs)

    retriever.collection.add = record

    added, _ = retriever.add_document("policy.txt", "住宿费标准为500元")

    assert added is True
    assert retriever.stores_vectors is False
    assert written and "embeddings" not in written[0], "不存向量的后端不得假装写进了向量"

    hits = retriever.search("住宿费标准")

    assert hits and hits[0]["retrieval_mode"] == retriever.MODE_KEYWORD
    assert retriever.last_search_reason == retriever.REASON_STORE_OFFLINE
