"""R44 判据②③④⑤：热集与真实 Chroma 的逐条一致性、越权、失效、关闭态回滚面。

这里用真 chromadb（tmp_path 下独立的 PersistentClient），不是自造的第二套向量库：判据②
要证的是"热集给的结果就是外部库会给的那一份"，那只有拿外部库当对照才有意义。

embedding 桩替换的是 OllamaEmbeddings._call_api（唯一出网点），返回确定性的 char-ngram 哈希
向量，维度取 retriever.EMBEDDING_DIM，且保证非全零 —— 所以 embed_documents / 写库闸门
assert_writable_embeddings / search 三条真实路径一个字都没被绕过，只是不再打 Ollama（R56
端口闸门要求全程零连接）。tests/test_r44_vectors_table.py 里可以按文本钉住指定向量。
"""

import hashlib
import re
from pathlib import Path

import pytest

from app.rag import hot_index as hi
from app.rag import indexing as indexing_module
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

#: score 容差的口径见 test_hot_and_chroma_agree_on_ids_scores_and_gaps 的说明。
SCORE_ABS_TOL = 1e-5
SCORE_REL_TOL = 1e-5


def _hash_vector(text: str, dim: int) -> list:
    """确定性哈希向量：同一文本永远同一向量，非全零，维度随 EMBEDDING_DIM。"""
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    if not any(vector):
        vector[0] = 1.0
    return vector


class _CallSpy:
    """把 collection 的每一次调用记下来，用来钉死"关闭态一个新调用都不多发"。"""

    def __init__(self, target):
        self.__dict__["_target"] = target
        self.__dict__["calls"] = []

    def __getattr__(self, name):
        attribute = getattr(self.__dict__["_target"], name)
        if not callable(attribute):
            return attribute

        def wrapper(*args, **kwargs):
            self.calls.append((name, dict(kwargs)))
            return attribute(*args, **kwargs)

        return wrapper

    def __setattr__(self, name, value):
        setattr(self.__dict__["_target"], name, value)


def _hit_key(hit: dict) -> tuple:
    """一条命中的身份：来源文件 + 块序号。向量库的 chunk id 就是这两者的函数。"""
    return (hit["source"], hit["chunk_index"])


def _diff(expected: list, actual: list) -> list:
    """逐条同序比对，返回可读差异；空列表就是完全一致。

    比对的是 id 序列本身（判据②硬要求），不是长度、不是关键词重合度。顺序不同算差异。
    """
    differences = []
    expected_ids = [_hit_key(hit) for hit in expected]
    actual_ids = [_hit_key(hit) for hit in actual]
    if expected_ids != actual_ids:
        differences.append(f"id 序列不同: 外部库={expected_ids} 热集={actual_ids}")
    for position, (want, got) in enumerate(zip(expected, actual)):
        if want["content"] != got["content"]:
            differences.append(f"第 {position} 条正文不同")
        for key in ("classification", "department", "retrieval_mode", "retrieval_reason"):
            if want[key] != got[key]:
                differences.append(f"第 {position} 条 {key} 不同: {want[key]!r} != {got[key]!r}")
    return differences


class _Harness:
    """一个用例一套临时向量库 + 一个全新的热集实例，互不串味。"""

    def __init__(self, tmp_path, monkeypatch, **index_kwargs):
        self.vectors = {}
        self.embedding_calls = []
        harness = self

        def fake_call_api(_self, text):
            harness.embedding_calls.append(str(text))
            if str(text) in harness.vectors:
                return list(harness.vectors[str(text)])
            return _hash_vector(text, retriever_module.EMBEDDING_DIM)

        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api", fake_call_api)
        self.index = hi.HotSetIndex(**{"max_chunks": 10_000, "roster_ttl_seconds": 3600.0,
                                       **index_kwargs})
        monkeypatch.setattr(hi, "_HOT_INDEX", self.index)
        monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
        hi.reset_hot_index_diagnostics()
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.spy = _CallSpy(self.retriever.collection)
        self.retriever.collection = self.spy
        self.monkeypatch = monkeypatch

    # ---- 开关与状态 ----

    def off(self):
        self.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)

    def on(self):
        self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")

    def reset(self):
        self.index.reset(reason="test")

    # ---- 造语料 ----

    def add(self, filename, content, *, classification=1, department="sales", vector=None):
        if vector is not None:
            self.vectors[content] = vector
        ok, message = self.retriever.add_document(
            filename, content, classification=classification, department=department)
        assert ok, message

    # ---- 检索 ----

    def search(self, query, k=3, where=None, pred=None, *, hot=None):
        if hot is True:
            self.on()
        elif hot is False:
            self.off()
        self.spy.calls.clear()
        hits = self.retriever.search(query, k=k, where=where, pred=pred)
        return hits, list(self.spy.calls)

    def stored_ids(self):
        return sorted(str(item) for item in (self.spy.get(include=["metadatas"])["ids"]))


@pytest.fixture
def harness(tmp_path, monkeypatch):
    return _Harness(tmp_path, monkeypatch)


def _unit(axis, dim, scale=1.0):
    vector = [0.0] * dim
    vector[axis] = scale
    return vector


# ==================== 判据②：与 Chroma 的结果一致性 ====================

def test_hot_and_chroma_agree_on_ids_scores_and_gaps(harness):
    """同一 query、同一权限上下文：热集与外部向量库必须逐条同序同 id。

    score 容差用"绝对 1e-5 或相对 1e-5 取大"，理由：Chroma 默认 l2 空间给出的就是平方欧氏
    距离，热集算的是同一个量，但 Chroma 在 float32 里 SIMD 累加、热集在 float64 里累加同一批
    float32 分量，误差随距离本身的大小线性放大，所以固定绝对容差在大批量高维下不成立。
    顺序不留容差：名次必须一模一样，只有距离数值允许浮点尾差。
    """
    harness.add("sales_a.txt", "住宿费标准是每晚500元。", classification=2, department="sales")
    harness.add("sales_b.txt", "差旅费报销细则：市内交通实报实销。", classification=2,
                department="sales")
    harness.add("hr_a.txt", "考勤与假期管理办法：年假按工龄计算。", classification=3,
                department="hr")
    harness.add("fin_a.txt", "年度预算方案：营销费用占比下调两个点。", classification=4,
                department="finance")
    queries = [
        "住宿费标准是多少",
        "出差交通怎么报销",
        "年假有几天",
        "预算怎么安排",
        "员工报销政策",
        "经营分析报告",
        "完全不相关的量子隧穿问题",
    ]
    differences = []
    max_abs = 0.0
    max_rel = 0.0
    min_gap = float("inf")
    served = 0
    for query in queries:
        for where in (None, {"department": {"$in": ["sales", "hr"]}}):
            external, _ = harness.search(query, k=4, where=where, hot=False)
            harness.reset()
            harness.on()
            before = hi.hot_index_diagnostics()["hits"]
            hot, _ = harness.search(query, k=4, where=where)
            served += int(hi.hot_index_diagnostics()["hits"] > before)
            differences.extend((query, str(where), item) for item in _diff(external, hot))
            embedding = harness.retriever.embedding.embed_query(query)
            raw = harness.retriever.collection.query(
                query_embeddings=[embedding], n_results=4,
                **({"where": where} if where else {})) or {}
            chroma_distances = list((raw.get("distances") or [[]])[0])
            ranked = harness.index.rank(embedding, 4, where=where)
            assert ranked is not None, (query, where, harness.index.bypass_reason(
                query_vector=embedding, where=where))
            hot_distances = [item[0] for item in ranked]
            assert [item[1] for item in ranked] == list(raw["ids"][0]), (query, where)
            for chroma_distance, hot_distance in zip(chroma_distances, hot_distances):
                max_abs = max(max_abs, abs(chroma_distance - hot_distance))
                max_rel = max(max_rel,
                              abs(chroma_distance - hot_distance) / max(chroma_distance, 1e-12))
                assert abs(chroma_distance - hot_distance) <= max(
                    SCORE_ABS_TOL, SCORE_REL_TOL * chroma_distance), (
                    chroma_distance, hot_distance)
            for previous, following in zip(chroma_distances, chroma_distances[1:]):
                min_gap = min(min_gap, following - previous)
    print(f"\n[R44 一致性] 比对 {len(queries) * 2} 次，热集服务 {served} 次")
    print(f"[R44 score] 最大绝对尾差 {max_abs:.3e}，最大相对尾差 {max_rel:.3e}，"
          f"容差 abs {SCORE_ABS_TOL} / rel {SCORE_REL_TOL}")
    print(f"[R44 名次] 相邻名次最小间隔 {min_gap:.3f}（远大于尾差 ⇒ 顺序不是碰巧一致）")
    for item in differences:
        print("[R44 差异]", item)
    assert differences == []
    assert min_gap > 1000 * max_abs, f"名次间隔 {min_gap} 与尾差 {max_abs} 同量级 ⇒ 顺序一致没有说服力"
    assert served == len(queries) * 2, "这批题必须全部由热集服务，否则下面的比对等于没跑"


def test_consistency_comparator_detects_a_real_divergence(harness):
    """一致性这把尺子本身要能被反证：名次被换序时，_diff 必须报出差异。

    这一条专门挡"把比对换成哈希/关键词/长度近似"的写法 —— 那种尺子在这里就量不出差异，
    判据②会退化成自证。
    """
    harness.add("a.txt", "第一条内容", vector=_unit(0, retriever_module.EMBEDDING_DIM))
    harness.add("b.txt", "第二条内容", vector=_unit(1, retriever_module.EMBEDDING_DIM))
    first, _ = harness.search("随便问一句", k=2, hot=False)
    assert len(first) == 2
    assert _diff(first, first) == []
    assert _diff(first, list(reversed(first))) != [], "换序必须被判定为差异"
    assert _diff(first, first[:1]) != [], "少给一条必须被判定为差异"
    assert _diff(first, [dict(first[0], department="elsewhere"), first[1]]) != [], \
        "权限元数据被改动必须被判定为差异"


# ==================== 判据③：pre-filter 先于热集 ====================

def test_foreign_department_document_lies_in_the_hot_index_and_is_invisible(harness):
    """直接反例：别的部门的文档就躺在热集里，越权用户也一条都看不到。"""
    harness.add("hr_secret.txt", "人力资源薪酬表：高管年薪明细。", classification=5,
                department="hr")
    harness.add("sales_open.txt", "住宿费标准是每晚500元。", classification=1,
                department="sales")
    harness.on()
    harness.search("薪酬", k=3, where={"department": "sales"})  # 暖机
    stored = harness.stored_ids()
    assert harness.index.resident_chunks == len(stored) and harness.index.cold_chunks == 0
    assert "hr_secret.txt_0" in harness.index._entries, "反例前提：越权文档确实常驻热集"

    where = {"$and": [{"classification": {"$in": [1, 2]}},
                      {"department": {"$in": ["sales"]}}]}
    hits, calls = harness.search("薪酬 高管 年薪", k=5, where=where)
    assert hits, hits
    assert [hit["source"] for hit in hits] == ["sales_open.txt"], hits
    assert all(hit["department"] == "sales" for hit in hits), hits
    assert harness.index.bypass_reason(where=where, query_vector=harness.retriever.embedding
                                       .embed_query("薪酬")) == ""
    external, _ = harness.search("薪酬 高管 年薪", k=5, where=where, hot=False)
    assert _diff(external, hits) == []


def test_prefilter_runs_before_truncation_so_limited_users_are_not_starved(harness):
    """名次饥饿反例：全局最近的那条是被禁文档，受限用户仍要拿到次近的合法文档。

    如果 pre-filter 被挪到截断之后（判据③的刀），k=1 会先选中禁文档再丢掉 ⇒ 返回空。
    """
    dim = retriever_module.EMBEDDING_DIM
    harness.vectors["query"] = [0.0] * dim
    harness.add("hr_forbidden.txt", "只有人力能看的薪酬明细", department="hr",
                classification=5, vector=_unit(0, dim, 1.0))
    harness.add("sales_allowed.txt", "销售部门的公开提成说明", department="sales",
                classification=1, vector=_unit(1, dim, 3.0))
    harness.on()
    k = 1
    where = {"department": {"$in": ["sales"]}}
    hits, _ = harness.search("query", k=k, where=where)
    assert [hit["source"] for hit in hits] == ["sales_allowed.txt"], hits
    pred_hits, _ = harness.search("query", k=k, pred=lambda item: item["department"] == "sales")
    assert [hit["source"] for hit in pred_hits] == ["sales_allowed.txt"], pred_hits
    external, _ = harness.search("query", k=k, where=where, hot=False)
    assert [hit["source"] for hit in external] == ["sales_allowed.txt"], external


# ==================== 判据④：失效正确性 ====================

def test_delete_document_invalidates_its_hot_entries(harness):
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.add("b.txt", "年假按工龄计算。", department="hr")
    harness.on()
    harness.search("住宿费", k=3)
    assert harness.index.resident_chunks == 2
    harness.retriever.delete_document("a.txt")
    assert harness.index.resident_chunks == 1
    assert "a.txt_0" not in harness.index._entries
    hits, _ = harness.search("住宿费标准是每晚500元", k=3)
    assert [hit["source"] for hit in hits] == ["b.txt"], hits
    assert hi.hot_index_diagnostics()["invalidations"] >= 1


def test_reupload_same_name_replaces_the_resident_vector(harness):
    """同名重传：旧向量条目必须作废，热集不能继续按旧内容排名。"""
    dim = retriever_module.EMBEDDING_DIM
    harness.vectors["query"] = [0.0] * dim
    harness.add("policy.txt", "旧版本：住宿费上限300元", vector=_unit(0, dim, 1.0))
    harness.on()
    harness.search("query", k=1)
    #: R79 判据③把常驻向量下沉成 float32 缓冲（array('f')）。这两行原来比的是容器本身，
    #: 用例意图钉的是"驻的是哪一份向量"，所以按元素比，意图一字未改。
    assert list(harness.index._entries["policy.txt_0"].vector) == [1.0] + [0.0] * (dim - 1)
    harness.add("policy.txt", "新版本：住宿费上限900元", vector=_unit(1, dim, 1.0))
    assert list(harness.index._entries["policy.txt_0"].vector) == [0.0, 1.0] + [0.0] * (dim - 2)
    hits, _ = harness.search("query", k=1)
    assert "900" in hits[0]["content"], hits
    external, _ = harness.search("query", k=1, hot=False)
    assert _diff(external, hits) == []


def test_reupload_with_new_classification_is_not_served_under_the_old_level(harness):
    """权限口径变化（本仓唯一的改法就是重传）：旧密级的那份不能再被低权限用户命中。"""
    harness.add("policy.txt", "客户数据保护政策的公开摘要", classification=1,
                department="sales")
    harness.on()
    warm = harness.search("客户数据保护", k=3)[0]
    assert [hit["source"] for hit in warm] == ["policy.txt"], warm
    harness.add("policy.txt", "客户数据保护政策已升为机密：含全量客户名单", classification=5,
                department="sales")
    restricted = {"classification": {"$in": [1, 2]}}
    hits, _ = harness.search("客户数据保护名单", k=3, where=restricted)
    assert hits == [], hits
    assert harness.index._entries["policy.txt_0"].metadata["classification"] == 5


def test_embedding_model_switch_discards_every_hot_entry(harness, monkeypatch):
    """R22 的缓存版：换 embedding 模型 = 口径变了，旧条目一条都不许复用。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.add("b.txt", "年假按工龄计算。", department="hr")
    harness.on()
    harness.search("住宿费", k=3)
    assert harness.index.resident_chunks == 2
    before = hi.hot_index_diagnostics()["invalidations"]
    monkeypatch.setenv(indexing_module.EMBEDDING_MODEL_ENV, "another-model")
    hits, _ = harness.search("住宿费", k=3)
    assert harness.index.last_reset_reason == hi.REASON_SCOPE_MISMATCH
    assert hi.hot_index_diagnostics()["invalidations"] > before
    external, _ = harness.search("住宿费", k=3, hot=False)
    assert _diff(external, hits) == []


def test_entries_carry_their_scope_and_cannot_be_queried_from_another_version(harness):
    """条目自带口径标识：拿另一个版本的 scope 来问，热集整体不服务，而不是给旧向量的结果。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.on()
    harness.search("住宿费", k=3)
    entry = harness.index._entries["a.txt_0"]
    assert entry.scope_key == harness.index.scope_key
    foreign = tuple(list(harness.index.scope_key[:1]) + ["other-model"] +
                    list(harness.index.scope_key[2:]))
    embedding = harness.retriever.embedding.embed_query("住宿费")
    assert harness.index.rank(embedding, 3, scope_key=foreign) is None
    assert harness.index.bypass_reason(scope_key=foreign, query_vector=embedding) == \
        hi.REASON_SCOPE_MISMATCH
    assert entry.scope_key != foreign


def test_dimension_switch_changes_the_scope_key(harness, monkeypatch):
    """换维度同样换口径（R22：换维度 = 新索引版本 + 全量重建）。"""
    harness.on()
    here = hi.current_scope_key()
    monkeypatch.setenv(indexing_module.EMBEDDING_DIMENSION_ENV,
                       str(retriever_module.EMBEDDING_DIM + 8))
    there = hi.current_scope_key()
    assert here != there and there[2] == retriever_module.EMBEDDING_DIM + 8


def test_no_in_place_metadata_mutation_bypasses_the_write_hooks():
    """守卫：本仓不得出现绕过热集钩子的就地改（update/upsert）。

    热集缓存了 chunk 的权限元数据，它的前提是"元数据变了必然跟着一次重写入"。今天这个前提
    成立（全库只有 add / delete，两者都在钩子里）；哪天有人加一条 collection.update()，
    这个前提就断了，必须同时补一条失效通知 —— 所以把它钉成用例，而不是写在注释里。
    """
    pattern = re.compile(r"collection\.(update|upsert)\s*\(")
    offenders = []
    for path in Path("app").rglob("*.py"):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    assert offenders == [], f"新增就地改向量库的写路径，请同时接热集失效: {offenders}"


# ==================== 判据⑤：不装也能跑（回滚保证） ====================

def test_switch_off_emits_exactly_the_pre_r44_store_calls(harness):
    """关闭态：一次 query、零次 get、零次多余 embedding、热集计数一个都不动。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.add("b.txt", "年假按工龄计算。", department="hr")
    embedded_before = len(harness.embedding_calls)
    diagnostics_before = hi.hot_index_diagnostics()

    hits, calls = harness.search("住宿费标准是多少", k=3, hot=False)
    assert [name for name, _ in calls] == ["query"], calls
    assert len(harness.embedding_calls) - embedded_before == 1, harness.embedding_calls
    assert hi.hot_index_diagnostics() == diagnostics_before
    assert diagnostics_before == {"hits": 0, "misses": 0, "invalidations": 0,
                                 "resident_chunks": 0, "last_bypass_reason": ""}
    assert hits and harness.retriever.last_search_mode == DocumentRetriever.MODE_SEMANTIC
    assert harness.retriever.last_search_reason == ""
    assert harness.index.resident_chunks == 0, "关闭时热集一个字节状态都不该留"


def test_open_index_reads_the_store_once_then_not_at_all(harness):
    """开启态：花名册过期才读库；命中之后同一批查询一次外部调用都不发 —— 这就是本单省下的那几毫秒。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.add("b.txt", "年假按工龄计算。", department="hr")
    harness.reset()
    _, warm_calls = harness.search("住宿费标准是多少", k=3, hot=True)
    # 冷启动那一次付两笔只读 get（花名册 + 预算内的向量），但没有 query：结果已由热集给出
    assert [name for name, _ in warm_calls] == ["get", "get"], warm_calls
    first = harness.search("住宿费标准是多少", k=3)[1]
    assert first == [], first
    for query in ("差旅报销", "年假几天", "预算方案"):
        calls = harness.search(query, k=3)[1]
        assert calls == [], calls
    assert harness.index.resident_chunks == 2 and harness.index.cold_chunks == 0
    embedded = len(harness.embedding_calls)
    harness.search("住宿费标准是多少", k=3)
    assert len(harness.embedding_calls) - embedded == 1, "热集命中不得多发 embedding"


def test_roster_expiry_rereads_the_store_instead_of_trusting_memory(harness):
    """TTL 到期 ⇒ 强制重读向量库。跨进程写入最多只被信任一个 TTL，不会永久错下去。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.on()
    harness.search("住宿费", k=3)
    assert harness.search("住宿费", k=3)[1] == []
    harness.index._built_at -= harness.index._roster_ttl + 1.0
    assert harness.index.bypass_reason(query_vector=[0.0] * 768) == hi.REASON_STALE_ROSTER
    _, calls = harness.search("住宿费", k=3)
    assert [name for name, _ in calls] == ["get", "get"], calls


def test_corpus_beyond_the_memory_budget_is_not_used_at_all(tmp_path, monkeypatch):
    """语料超预算 ⇒ 整体不用（不是部分命中），结果与关闭时逐条一致。"""
    tight = _Harness(tmp_path, monkeypatch, max_chunks=1)
    tight.add("a.txt", "住宿费标准是每晚500元。")
    tight.add("b.txt", "年假按工龄计算。", department="hr")
    tight.add("c.txt", "营销费用占比下调两个点。", department="finance")
    assert tight.index.resident_chunks <= 1
    tight.search("住宿费", k=3, hot=True)  # 先付掉冷启动那两笔只读 get
    external, external_calls = tight.search("住宿费", k=3, hot=False)
    hot, hot_calls = tight.search("住宿费", k=3, hot=True)
    assert _diff(external, hot) == []
    assert hot_calls == external_calls == [("query", hot_calls[0][1])], (hot_calls, external_calls)
    assert tight.index.bypass_reason(
        query_vector=tight.retriever.embedding.embed_query("住宿费")) == hi.REASON_INCOMPLETE


def test_offline_backend_without_vectors_behaves_exactly_as_before(tmp_path, monkeypatch):
    """_JsonCollection 降级态（后端不存向量）：热集不得多发一次 get，也不得多问一次 embedding。"""
    monkeypatch.setattr(retriever_module, "chromadb", None, raising=False)
    offline = _Harness(tmp_path, monkeypatch)
    assert offline.retriever.stores_vectors is False
    offline.add("a.txt", "住宿费标准是每晚500元。")
    offline.add("b.txt", "年假按工龄计算。", department="hr")
    embedded_before = len(offline.embedding_calls)
    _, calls_off = offline.search("住宿费", k=3, hot=False)
    _, calls_on = offline.search("住宿费", k=3, hot=True)
    hits_off, _ = offline.search("住宿费标准", k=3, hot=False)
    hits_on, _ = offline.search("住宿费标准", k=3, hot=True)
    assert calls_off == calls_on, (calls_off, calls_on)
    assert [name for name, _ in calls_off] == ["get"], calls_off
    assert _diff(hits_off, hits_on) == []
    assert offline.retriever.last_search_reason == DocumentRetriever.REASON_STORE_OFFLINE
    assert len(offline.embedding_calls) - embedded_before == 0, "离线态一次 embedding 都不该问"
    # 后端不存向量时，search 在 stores_vectors 那一关就分叉了，热集连门都进不去：
    # 开启态与关闭态一样，一次读、一次 embedding、一笔计数都不多发。
    ledger = hi.hot_index_diagnostics()
    assert ledger["hits"] == 0 and ledger["misses"] == 0, ledger
    assert offline.index.bypass_reason(query_vector=[0.0] * 768,
                                       stores_vectors=False) == hi.REASON_NO_VECTORS


def test_a_broken_hot_layer_cannot_break_retrieval(harness, monkeypatch):
    """热集自己出异常 ⇒ 退回外部向量库，结果照旧，只多一个稳定原因码。"""
    harness.add("a.txt", "住宿费标准是每晚500元。")
    external, _ = harness.search("住宿费", k=3, hot=False)
    harness.search("住宿费", k=3, hot=True)  # 先把热集喂热，下面炸的就只有排名那一步

    def boom(*args, **kwargs):
        raise RuntimeError("热集炸了")

    monkeypatch.setattr(harness.index, "rank", boom)
    hits, calls = harness.search("住宿费", k=3, hot=True)
    assert _diff(external, hits) == []
    assert [name for name, _ in calls] == ["query"], calls
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == hi.REASON_ERROR


# ==================== 判据⑥：观测只记账 ====================

def test_diagnostics_are_a_read_only_ledger(harness):
    harness.add("a.txt", "住宿费标准是每晚500元。")
    harness.on()
    harness.search("住宿费", k=3)
    snapshot = hi.hot_index_diagnostics()
    assert snapshot["hits"] == 1 and snapshot["resident_chunks"] == 1
    snapshot["hits"] = 999
    assert hi.hot_index_diagnostics()["hits"] == 1, "交出去的必须是副本，不能是内部字典"
    harness.off()
    before = hi.hot_index_diagnostics()
    harness.search("住宿费", k=3)
    assert hi.hot_index_diagnostics() == before
    hi.reset_hot_index_diagnostics()
    assert hi.hot_index_diagnostics() == {"hits": 0, "misses": 0, "invalidations": 0,
                                         "resident_chunks": 0, "last_bypass_reason": ""}
