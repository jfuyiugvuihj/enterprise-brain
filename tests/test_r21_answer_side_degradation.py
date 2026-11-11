"""跟进单 R21 判据①③④：降级必须看得见，向量不合格不得先删旧数据。

三件事各自钉死：

* 判据④：关键词腿的命中带 retrieval_reason，retrieval_degradation_notice 据此产出
  一句能直接拼进回答的话；语义腿返回空串，绝不给正常结果贴降级标签。
* 判据①②：add_document 先验后删 —— embedding 失败时旧版本必须原样留在库里，
  不许出现"旧的已删、新的写不进"这种把重传变成删除的数据丢失窗口。
* 判据③：/health/details 的 embedding 段能读出最近一次失败原因，读取过程不开 socket。
"""
import pytest

from app.common import monitoring
from app.rag import retriever as r
from app.rag.retriever import (
    EMBEDDING_DIM,
    EmbeddingUnavailableError,
    VectorWriteRejectedError,
    retrieval_degradation_notice,
)


@pytest.fixture(autouse=True)
def _isolate_diagnostics():
    r.reset_embedding_diagnostics()
    yield
    r.reset_embedding_diagnostics()


def _vector(value=0.25):
    vector = [0.0] * EMBEDDING_DIM
    vector[-1] = value
    return vector


def _hit(mode, reason=None):
    hit = {
        "content": "住宿费标准为500元",
        "source": "policy.md",
        "chunk_index": 0,
        "classification": 1,
        "department": "finance",
        "retrieval_mode": mode,
    }
    if reason is not None:
        hit["retrieval_reason"] = reason
    return hit


class _FakeSplitter:
    def __init__(self, chunks=None):
        self.chunks = chunks if chunks is not None else ["住宿费标准为500元"]

    def split_text(self, content):
        return list(self.chunks)


class _RecordingCollection:
    """按顺序记录 add/delete 的替身，用来证明"先验后删"。"""

    def __init__(self, rows=None):
        self.rows = [dict(row) for row in (rows or [])]
        self.events = []

    def get(self, where=None):
        rows = self.rows
        if where:
            rows = [
                row
                for row in rows
                if all(row["metadata"].get(key) == value for key, value in where.items())
            ]
        return {
            "ids": [row["id"] for row in rows],
            "documents": [row["document"] for row in rows],
            "metadatas": [row["metadata"] for row in rows],
        }

    def add(self, ids=None, documents=None, metadatas=None, **kwargs):
        self.events.append("add")
        for position, identifier in enumerate(ids):
            self.rows.append(
                {
                    "id": identifier,
                    "document": documents[position],
                    "metadata": metadatas[position],
                }
            )

    def delete(self, ids=None, **kwargs):
        self.events.append("delete")
        doomed = set(ids or [])
        self.rows = [row for row in self.rows if row["id"] not in doomed]

    def query(self, **kwargs):
        raise AssertionError("本文件只测写入顺序与降级标注，不问向量库")


class _StubEmbeddings:
    """失败时回填全零占位向量，正是写库闸门要挡的那个形状。"""

    def __init__(self, vectors=(), failure_reason=None):
        self.vectors = list(vectors)
        self.last_error = None
        if failure_reason:
            self.last_error = {"reason": failure_reason, "detail": "stub", "at": 0.0}

    def embed_documents(self, texts):
        if self.last_error is not None:
            return [[0.0] * EMBEDDING_DIM for _ in texts]
        return [self.vectors[index % len(self.vectors)] for index in range(len(texts))]

    def embed_query(self, text):
        if self.last_error is not None:
            raise EmbeddingUnavailableError("stub", reason=self.last_error["reason"])
        return _vector()


def _retriever(collection, embedding, splitter=None):
    retriever = r.DocumentRetriever.__new__(r.DocumentRetriever)
    retriever.collection = collection
    retriever.embedding = embedding
    retriever.splitter = splitter or _FakeSplitter()
    retriever.chroma_dir = ""
    return retriever


def _stored_rows(hash_value="oldhash", chunk_index=0):
    return [
        {
            "id": f"policy.md_{chunk_index}",
            "document": "旧版住宿标准",
            "metadata": {
                "filename": "policy.md",
                "chunk_index": chunk_index,
                "hash": hash_value,
                "classification": 1,
                "department": "finance",
            },
        }
    ]


# ------------------------------------------------------- 判据④：答案侧可见降级


def test_a_degraded_hit_carries_the_reason_that_explains_it():
    collection = _RecordingCollection(_stored_rows())
    embedding = _StubEmbeddings(failure_reason="model_missing")
    retriever = _retriever(collection, embedding)

    hits = retriever.search("住宿费标准", k=3)

    assert hits, "降级腿必须还能召回内容，不能悄悄返回空"
    assert all(hit["retrieval_mode"] == retriever.MODE_KEYWORD for hit in hits)
    assert all(hit["retrieval_reason"] == "model_missing" for hit in hits)


def test_the_notice_says_the_vector_leg_was_not_in_the_room():
    notice = retrieval_degradation_notice(
        [_hit(r.DocumentRetriever.MODE_KEYWORD, "model_missing")]
    )

    assert notice, "判据④不许静默：降级必须产出一句话"
    assert "向量检索未参与" in notice
    assert "关键词" in notice
    assert "未安装" in notice, "提示要把原因说给人听，而不是只贴个码"


def test_a_timeout_and_a_missing_model_do_not_share_one_notice():
    missing = retrieval_degradation_notice([_hit(r.DocumentRetriever.MODE_KEYWORD, "model_missing")])
    timeout = retrieval_degradation_notice([_hit(r.DocumentRetriever.MODE_KEYWORD, "timeout")])

    assert missing != timeout
    assert "超时" in timeout


def test_the_semantic_leg_produces_no_notice():
    assert retrieval_degradation_notice([_hit(r.DocumentRetriever.MODE_SEMANTIC, "")]) == ""
    assert retrieval_degradation_notice([]) == ""
    assert retrieval_degradation_notice(None) == ""


def test_a_hit_without_a_recorded_reason_still_produces_a_notice():
    notice = retrieval_degradation_notice([_hit(r.DocumentRetriever.MODE_KEYWORD)])

    assert notice, "缺原因码只能说明文案不精确，不能变成静默"
    assert "未记录原因" in notice


def test_the_reason_labels_cover_every_stable_code():
    codes = [
        value
        for name, value in vars(r).items()
        if name.startswith("REASON_") or name == "RETRIEVAL_REASON_STORE_OFFLINE"
    ]

    assert codes, "稳定码常量必须仍在模块里"
    missing = [code for code in codes if code not in r.EMBEDDING_REASON_LABELS]
    assert missing == [], f"这些原因码没有对应文案，答案侧会退化成未记录原因：{missing}"


# --------------------------------------------- 判据①②：先验后删，失败不留数据缺口


def test_a_failed_reupload_keeps_the_previous_version_indexed():
    """重传同名文档时 embedding 挂了：旧向量必须原地不动。

    这是本单唯一会造成数据丢失的窗口。R21 把写库改成硬失败之后，若仍然先删后写，
    "上传失败"就等于"文档从索引里消失"，比原来的静默零向量更难发现。
    """
    collection = _RecordingCollection(_stored_rows())
    embedding = _StubEmbeddings(failure_reason="model_missing")
    retriever = _retriever(collection, embedding)

    with pytest.raises(VectorWriteRejectedError) as raised:
        retriever.add_document("policy.md", "新版住宿标准", 1, "finance")

    assert raised.value.reason == "all_zero_vector"
    assert collection.events == [], "失败路径既不许写，也不许先删"
    assert [row["document"] for row in collection.rows] == ["旧版住宿标准"]
    assert retriever.list_documents() == ["policy.md"]


def test_the_rejected_write_reports_the_underlying_embedding_reason():
    collection = _RecordingCollection()
    embedding = _StubEmbeddings(failure_reason="model_missing")
    retriever = _retriever(collection, embedding)

    with pytest.raises(VectorWriteRejectedError) as raised:
        retriever.add_document("policy.md", "新版住宿标准", 1, "finance")

    assert "model_missing" in str(raised.value), "拒写要能把「为什么没有向量」一起交出来"


def test_a_successful_reupload_deletes_the_old_version_then_writes():
    collection = _RecordingCollection(_stored_rows())
    embedding = _StubEmbeddings(vectors=[_vector(0.5), _vector(0.75)])
    retriever = _retriever(collection, embedding, _FakeSplitter(["新版住宿标准", "差旅补贴"]))

    ok, message = retriever.add_document("policy.md", "新版住宿标准", 1, "finance")

    assert ok is True
    assert collection.events == ["delete", "add"], "删旧与写新都要发生，且删在写之前"
    assert sorted(row["id"] for row in collection.rows) == ["policy.md_0", "policy.md_1"]


def test_an_empty_document_wipes_nothing():
    collection = _RecordingCollection(_stored_rows())
    embedding = _StubEmbeddings(vectors=[_vector()])
    retriever = _retriever(collection, embedding, _FakeSplitter([]))

    ok, message = retriever.add_document("policy.md", "新版住宿标准", 1, "finance")

    assert ok is False
    assert collection.events == []
    assert len(collection.rows) == 1, "内容为空是拒绝，不是删除"


def test_an_unchanged_document_never_touches_the_store():
    collection = _RecordingCollection(_stored_rows(hash_value="x"))
    embedding = _StubEmbeddings(failure_reason="model_missing")
    retriever = _retriever(collection, embedding)
    content = "新版住宿标准"
    collection.rows[0]["metadata"]["hash"] = retriever._file_hash(content)

    ok, message = retriever.add_document("policy.md", content, 1, "finance")

    assert ok is False
    assert collection.events == []


def test_the_write_gate_is_still_the_only_way_in():
    """预检只是提前挡住，真正的闸门不能被绕开：直接调 _write_batch 仍然抛。"""
    collection = _RecordingCollection()
    retriever = _retriever(collection, _StubEmbeddings(vectors=[_vector()]))

    with pytest.raises(VectorWriteRejectedError):
        retriever._write_batch(
            ids=["policy.md_0"],
            documents=["住宿费标准为500元"],
            metadatas=[{"filename": "policy.md", "chunk_index": 0, "classification": 1}],
            embeddings=[[0.0] * EMBEDDING_DIM],
        )

    assert collection.events == []


# ------------------------------------------- 判据③：健康报告里的原因可观测且不联网


def test_the_snapshot_names_the_last_embedding_failure(monkeypatch):
    def refuse(url, timeout=None):
        raise TimeoutError("cold model load took longer than the budget")

    monkeypatch.setattr(r.urllib.request, "urlopen", refuse)
    embeddings = r.OllamaEmbeddings(model="nomic-embed-text", base_url="http://localhost:11434")

    with pytest.raises(EmbeddingUnavailableError):
        embeddings.embed_query("住宿费标准")

    state = monitoring._embedding_state()

    assert state["last_failure"]["reason"] == "timeout"
    assert state["last_failure"]["model"] == "nomic-embed-text"


def test_the_embedding_state_opens_no_socket(monkeypatch):
    """健康检查不得为"上次失败原因"发起任何请求：这个值已经在进程里。"""

    def explode(*args, **kwargs):
        raise AssertionError("_embedding_state 不得联网")

    monkeypatch.setattr(monitoring, "urlopen", explode)
    monkeypatch.setattr(r.urllib.request, "urlopen", explode)

    assert monitoring._embedding_state() == {
        "last_failure": None,
        "degraded_searches": 0,
        "rejected_writes": 0,
    }


def test_failure_counters_never_become_problem_codes(monkeypatch):
    """rejected_writes 是历史计数，不是当前故障；把它变成 problems 会让健康页永远红。"""
    collection = _RecordingCollection()
    retriever = _retriever(collection, _StubEmbeddings(failure_reason="model_missing"))
    with pytest.raises(VectorWriteRejectedError):
        retriever.add_document("policy.md", "新版住宿标准", 1, "finance")

    state = monitoring._embedding_state()

    assert state["rejected_writes"] == 1
    assert state["last_failure"] is None, "拒写本身不是一次 embedding 调用失败"
