"""R57：缺 classification 元数据的 chunk 不许被补成 1 级，从而骗过权限判定。

钉住两个"在判定输入端造密级"的站点。两处都只是把 metadata 摊平成命中字典，缺键时补 1
就让 app/rag/filters.py 的 DocumentRetrievalScope.allows 把它当成合法的 1 级命中放行：

- app/rag/retrieval_pipeline.py BM25Searcher.build_index：:175 用的是不带 where 的
  collection.get()，全库行都进这个本地索引 ⇒ 缺键行必然走到判定。本单改为缺键即 None。
- app/rag/retriever.py DocumentRetriever.search（向量腿出口）：Chroma 主路径的 where 已在
  向量计算之前把缺键行裁掉，所以它今天不构成漏权；本文件用"遵守 where 的假库"与"故意忽略
  where 的假库"分别把这两种结果都跑出来，前者证明不可达、后者证明可达性（订正令 §3）。

定性（不许写成"正在泄漏"）：现行入库路径 app/rag/indexing.py::scope_metadata 对每条 chunk
都写入具体密级，因此缺 classification 的行只可能来自遗留数据或外部直写。本单是纵深防御。

同款默认值另外两处按判据 §1 不改，理由写在各站点注释里：retriever.py::document_chunks 的
默认值不到达任何权限判定（读回，消费方只取 content/vector_id/hash）；catalog.py::_local_row
的默认值到达 policy 但一键两用（判定 + 目录展示），拆分属另一张单（拟号 R58）。

判定事实源不许动：本文件在导入期就绑定 allows；全程不建 PersistentClient、不打 Ollama、
不碰真实 chroma_db。最后一条用例复现 app/api/v1/chat.py::_document_source_row 的投影，
但不 import chat.py（它会在导入期触发模型发现）。
"""
import numpy as np
import pytest

from app.agents import evidence as evidence_module
from app.agents.contracts import Principal
from app.rag import retrieval_pipeline
from app.rag import retriever as retriever_module
from app.rag.filters import DocumentRetrievalScope, resolve_document_retrieval_scope
from app.rag.retrieval_pipeline import BM25Searcher
from app.rag.retriever import DocumentRetriever

ORIGINAL_ALLOWS = DocumentRetrievalScope.allows

LEGACY_DOC = "legacy-policy.txt"
OWNED_DOC = "finance-policy.txt"


def _legacy_metadata():
    """一条没有 classification 键的遗留 chunk 元数据（现行 indexing 不再产出这种行）。"""
    return {"filename": LEGACY_DOC, "chunk_index": 0, "department": "finance"}


def _owned_metadata():
    return {"filename": OWNED_DOC, "chunk_index": 1, "classification": 2, "department": "finance"}


def _staff(department="finance", clearance=2):
    return Principal(
        user_id="u-r57",
        username="r57-staff",
        permissions=["document.read"],
        department=department,
        clearance=clearance,
    )


def _admin():
    return Principal.from_user({"id": "u-r57-admin", "username": "r57-admin", "role": "admin"})


# ============ BM25 腿：不带 where 的全库扫 ⇒ 缺键行必然走到判定 ============

class _StubBM25:
    """替掉真 BM25Okapi：分数由用例给定，被测的是"缺键行会不会被判定放行"。"""

    scores: list[float] = []

    def __init__(self, corpus):
        self.scores = np.asarray(type(self).scores, dtype=float)

    def get_scores(self, tokens):
        return self.scores


class _ScanCollection:
    """``build_index`` 的取数面：get() 不带 where，返回全库。"""

    def __init__(self, payload):
        self.payload = payload

    def get(self, **kwargs):
        assert not kwargs, "取数必须仍是不带 where 的全库扫，否则本用例的靶子就变了"
        return {key: list(value) for key, value in self.payload.items()}


def _build_bm25(monkeypatch, metadatas, scores):
    """只替掉两处外部依赖（向量库句柄、BM25 打分），被测的是 build_index 本体。"""
    documents = [f"[{meta['filename']}] 财务制度 正文" for meta in metadatas]
    collection = _ScanCollection(
        {"documents": documents, "metadatas": [dict(meta) for meta in metadatas]}
    )
    stub = type("StubRetriever", (), {"collection": collection})
    monkeypatch.setattr(retriever_module, "DocumentRetriever", stub)
    monkeypatch.setattr(retrieval_pipeline, "BM25Okapi", type("Scorer", (_StubBM25,), {"scores": scores}))
    searcher = BM25Searcher()
    searcher.build_index()
    return searcher


def test_a_chunk_without_classification_is_not_promoted_to_level_one(monkeypatch):
    """判据 §3①：缺键 metadata 经 build_index 后过真实 allows，必须不放行。"""
    searcher = _build_bm25(monkeypatch, [_legacy_metadata(), _owned_metadata()], [9.0, 8.0])

    legacy, owned = searcher.documents
    assert "classification" in legacy, "命中字典形状不变：靠值不可用出局，不靠删键"
    assert legacy["classification"] is None, "缺键不许被补成任何可用密级"
    assert owned["classification"] == 2

    staff = resolve_document_retrieval_scope(_staff())
    admin = resolve_document_retrieval_scope(_admin())
    assert ORIGINAL_ALLOWS(staff, legacy) is False
    assert ORIGINAL_ALLOWS(admin, legacy) is False, "管理员也不得猜测未标密级的内容"
    assert [hit["source"] for hit in searcher.search("财务制度", k=5, pred=staff.allows)] == [
        OWNED_DOC
    ], "缺键行在 BM25 腿上一个名额都不许占"


def test_the_old_default_would_have_promoted_that_same_row():
    """同一份 metadata 按改动前的表达式摊平，就是"造出来的密级骗过判定"的形状。

    判据 §3② 要的是"把源码改回 1 之后本文件必须红"，那两次 pytest 由总控实跑取证；这里
    另留一份不依赖改源码的对照，免得这条缺陷只剩外部记忆。
    """
    meta = _legacy_metadata()
    staff = resolve_document_retrieval_scope(_staff())
    promoted = dict(meta, classification=meta.get("classification", 1))

    assert promoted["classification"] == 1
    assert ORIGINAL_ALLOWS(staff, promoted) is True, "1 级命中 classification_levels ⇒ 放行"
    assert ORIGINAL_ALLOWS(staff, dict(meta, classification=meta.get("classification"))) is False


# ==== 向量腿：where 被遵守 / 被忽略的两种结果（订正令第 2 条 §3 的可达性取证） ====

def _chroma_where_matches(metadata, where):
    """复刻 chromadb 下推语义：$and/$in/$eq，且被比较的键不存在 ⇒ 该行不匹配。

    这不是第二套权限规则：判定只允许在 allows 一处，这里只是让假库像真库一样先裁候选。
    """
    if not where:
        return True
    if "$and" in where:
        return all(_chroma_where_matches(metadata, clause) for clause in where["$and"])
    for key, condition in where.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$eq" in condition and value != condition["$eq"]:
                return False
        elif value != condition:
            return False
    return True


class _QueryCollection:
    def __init__(self, rows, ignores_where):
        self.rows = rows
        self.ignores_where = ignores_where
        self.queries = []

    def query(self, query_embeddings=None, n_results=5, where=None, **kwargs):
        if self.ignores_where:
            scored = list(self.rows)  # 不执行下推：这就是"召回实现漏权"的形状
        else:
            scored = [row for row in self.rows if _chroma_where_matches(row["metadata"], where)]
        self.queries.append({"where": where, "scored_ids": [row["id"] for row in scored]})
        page = scored[:n_results]
        return {
            "documents": [[row["document"] for row in page]],
            "metadatas": [[dict(row["metadata"]) for row in page]],
        }


class _StubEmbeddings:
    def embed_query(self, text):
        return [0.0] * 8


def _vector_hits(monkeypatch, metadatas, *, ignores_where, clearance=2):
    """clearance 只影响下推的 $in 集合；回归用例要 3 级也召回得到，故做成参数。"""
    rows = [
        {"id": f"r{index}", "document": f"[{meta['filename']}] 财务制度 正文", "metadata": dict(meta)}
        for index, meta in enumerate(metadatas)
    ]
    retriever = DocumentRetriever.__new__(DocumentRetriever)  # 不跑 __init__：不建库、不联网
    collection = _QueryCollection(rows, ignores_where)
    retriever.collection = collection
    retriever.embedding = _StubEmbeddings()
    scope = resolve_document_retrieval_scope(_staff(clearance=clearance))
    return retriever.search("财务制度", k=5, where=scope.filters), scope, collection


def test_a_keyless_row_is_pushed_out_when_the_store_honours_where(monkeypatch):
    """它今天不构成现行漏权的原因：真库在向量计算之前就把缺键行裁掉，注入点轮不到它。"""
    hits, _scope, collection = _vector_hits(
        monkeypatch, [_legacy_metadata(), _owned_metadata()], ignores_where=False
    )

    assert collection.queries[0]["where"], "权限过滤确实下推了"
    assert LEGACY_DOC not in collection.queries[0]["scored_ids"], "缺键行在库侧就出局"
    assert [hit["source"] for hit in hits] == [OWNED_DOC]


def test_a_store_that_ignores_where_does_hand_the_keyless_row_to_the_predicate(monkeypatch):
    """可达性取证：把 where 摘掉，缺键行确实进得了这个命中字典 ⇒ 注入点判定为"可达"。"""
    hits, scope, _collection = _vector_hits(
        monkeypatch, [_legacy_metadata(), _owned_metadata()], ignores_where=True
    )

    assert LEGACY_DOC in [hit["source"] for hit in hits], "缺键行走到了判定的输入端"
    legacy = next(hit for hit in hits if hit["source"] == LEGACY_DOC)
    assert legacy["classification"] is None, "进来的是 None，不是被造出来的 1"
    assert scope.allows(legacy) is False
    assert [hit["source"] for hit in hits if scope.allows(hit)] == [OWNED_DOC]


@pytest.mark.parametrize("stored", [1, 2, 3])
def test_rows_that_carry_a_level_keep_the_exact_value_on_both_legs(monkeypatch, stored):
    """判据 §3③：带正常密级的语料，改动前后取到的值逐字相同（含类型）。"""
    meta = {"filename": OWNED_DOC, "chunk_index": 0, "classification": stored, "department": "finance"}
    before = meta.get("classification", 1)  # 改动前的表达式

    bm25_value = _build_bm25(monkeypatch, [dict(meta)], [4.0]).documents[0]["classification"]
    hits = _vector_hits(monkeypatch, [dict(meta)], ignores_where=False, clearance=3)[0]
    assert [hit["source"] for hit in hits] == [OWNED_DOC], "合法行必须召回得到，否则这条回归是空跑"
    vector_value = hits[0]["classification"]

    for label, value in (("BM25 腿", bm25_value), ("向量腿", vector_value)):
        assert value == before, f"{label} 把合法行的密级改动了"
        assert type(value) is type(before), f"{label} 改动了合法行密级的类型"
        assert value == stored


def test_the_missing_level_survives_the_evidence_hop_and_is_still_denied(monkeypatch):
    """缺键命中经证据边界之后仍然不放行：hit → evidence.metadata → 投影 → allows。

    chat.py 在导入期会触发模型发现，故不复用它，改为逐字复现
    app/api/v1/chat.py::_document_source_row 对判据两键的投影（:262-263）。
    """
    searcher = _build_bm25(monkeypatch, [_legacy_metadata()], [6.0])
    bag = evidence_module.new_evidence_bag()

    recorded = evidence_module.record_document_hits(bag, query="财务制度", hits=searcher.documents)
    assert recorded == 1, "证据边界照旧收下这条命中；放行与否由判定负责，不在这里偷偷丢"
    metadata = bag["documents"][0]["metadata"]
    assert metadata["classification"] is None

    row = {
        "content": "x",
        "source": LEGACY_DOC,
        "classification": metadata.get("classification"),
        "department": metadata.get("department"),
    }
    for scope in (
        resolve_document_retrieval_scope(_staff()),
        resolve_document_retrieval_scope(_admin()),
    ):
        assert ORIGINAL_ALLOWS(scope, row) is False
