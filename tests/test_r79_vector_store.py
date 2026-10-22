"""R79 判据③：常驻向量下沉成 float32，名次一条都不许变。

改动本体：`HotChunk.vector` 从 `tuple(float, ...)` 换成 `array('f')`。省下的是"每个维度
摊一个 24 字节的 Python float 对象"这笔开销；距离照旧在 float64 上累加，所以本文件要证的
是两件事，缺一不可：

1. **存储真的紧凑了** —— 按 itemsize 与整批常驻字节数钉，改回 tuple 必红；
2. **名次一个都没翻** —— 同一条查询，热集开启态与关闭态（走外部向量库）返回的 top-k
   逐条一致（含顺序，分值给绝对/相对容差），并且覆盖多文档、跨部门 scope、并列分。

并列分为什么单独钉：float32 的下限就在"两个只差 1e-9 的向量会被看成同一个"，而这种坍缩
外部向量库早就做了（落盘即 float32）。下沉之后两边看见的是同一批数，所以并列段里的名次
只可能更一致，不可能更分叉 —— 下面的对照用例把边界处的并列也钉进去了。
"""

import hashlib
import sys
from array import array
from fractions import Fraction

import pytest

from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

DIM = retriever_module.EMBEDDING_DIM
#: score 容差口径与 R44 一致（Chroma 在 float32 里 SIMD 累加，热集在 float64 里累加同一批
#: float32 分量，误差随距离本身线性放大 ⇒ 绝对与相对取大）。
SCORE_ABS_TOL = 1e-5
SCORE_REL_TOL = 1e-5
SCOPE_SMALL = ("chroma", "r79-store", 4, "v1")


def _unit(axis, dim=DIM, scale=1.0):
    vector = [0.0] * dim
    vector[axis] = scale
    return vector


def _hash_vector(text: str, dim: int) -> list:
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    return vector if any(vector) else [1.0] + [0.0] * (dim - 1)


# ==================== 一、存储形态：确凿是 4 字节一份 ====================

def _rows(count, *, dim=4, start=0, department="sales"):
    for ordinal in range(start, start + count):
        chunk_id = f"doc_{ordinal:05d}_0"
        yield (chunk_id, f"正文 {ordinal}",
               {"filename": f"doc_{ordinal:05d}", "chunk_index": 0,
                "classification": 1, "department": department},
               [float(ordinal % 5)] + [1.0] * (dim - 1))


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    hi.reset_hot_index_diagnostics()
    yield monkeypatch
    hi.reset_hot_index_diagnostics()


def test_a_resident_vector_is_a_four_byte_buffer(monkeypatch):
    """常驻向量必须按 float32 存：改回 tuple(float) 这条立刻红。"""
    index = hi.HotSetIndex(max_chunks=10, roster_ttl_seconds=3600.0)
    index.populate(list(_rows(2, dim=8)), scope_key=SCOPE_SMALL)
    entry = index._entries["doc_00000_0"]
    assert isinstance(entry.vector, array), type(entry.vector)
    assert entry.vector.itemsize == 4, entry.vector.itemsize
    assert len(entry.vector) == 8


def _distinct_vector(seed: int, dim: int) -> list:
    """造一条"每个分量都是各自独立的 float 对象"的向量。

    这不是吹毛求疵：向量库读回来的 list(numpy_array) 就是这个形状 —— 768 个互不共享的对象。
    用 [x] * dim 造对照样本会把 24 字节/元素那笔开销整个抹掉，tuple 的账因此少算七成。
    """
    return [float((seed * 7919 + position * 104729) % 1009) / 1009.0 for position in range(dim)]


def test_the_whole_resident_set_costs_float32_bytes_not_object_headers():
    """按整批常驻字节数钉死：3 000 条 × 768 维只许花 float32 那份钱（加一点点缓冲开销）。"""
    count, dim = 3_000, DIM
    index = hi.HotSetIndex(max_chunks=count, roster_ttl_seconds=3600.0)
    vectors = [_distinct_vector(n, dim) for n in range(count)]
    rows = [(f"wide_{n:05d}_0", f"正文 {n}",
             {"filename": f"wide_{n:05d}", "chunk_index": 0, "classification": 1,
              "department": "sales"}, vectors[n]) for n in range(count)]
    outcome = index.populate(rows, scope_key=SCOPE_SMALL)
    assert outcome["resident"] == count
    resident_bytes = sum(sys.getsizeof(entry.vector) for entry in index._entries.values())
    ideal = count * dim * 4
    #: tuple 的账 = 指针数组本身 + 每个分量一个 PyFloatObject（向量库读回来就是这个形状）。
    as_tuple = sum(sys.getsizeof(tuple(vector)) + sum(map(sys.getsizeof, vector))
                   for vector in vectors)
    print(f"\n[R79 判据③] {count} 条 × {dim} 维常驻向量："
          f"float32 缓冲合计 {resident_bytes / 1e6:.2f} MB（理想 {ideal / 1e6:.2f} MB），"
          f"tuple(float) 合计 {as_tuple / 1e6:.2f} MB，省 {(1 - resident_bytes / as_tuple) * 100:.1f}%")
    assert resident_bytes <= ideal * 1.25, (resident_bytes, ideal)
    assert resident_bytes * 4 < as_tuple, "省不到四分之三就说明没真的下沉成 float32"


def test_the_narrowing_happens_once_at_entry_and_nowhere_else():
    """float64 → float32 只在进热集那一刻发生一次；比对用的仍是同一个已舍值。"""
    value = 0.1                       # 二进制里写不尽的那个 0.1
    index = hi.HotSetIndex(max_chunks=4, roster_ttl_seconds=3600.0)
    index.populate([("t_0", "正文", {"filename": "t", "chunk_index": 0,
                                     "classification": 1, "department": "sales"},
                     [value, 1.0, 0.0, 0.0])], scope_key=SCOPE_SMALL)
    stored = index._entries["t_0"].vector
    assert float(stored[0]) != value, "没下沉就是没下沉"
    assert float(stored[0]) == float(array("f", [value])[0])
    assert abs(float(stored[0]) - value) < 1e-7


def test_distances_are_still_accumulated_in_float64(on):
    """距离必须等于"对已下沉分量做的精确算术"：谁改成 float32 累加，这里当场红。"""
    index = hi.HotSetIndex(max_chunks=8, roster_ttl_seconds=3600.0)
    rows = [(f"e_{n}_0", f"正文 {n}",
             {"filename": f"e_{n}", "chunk_index": 0, "classification": 1,
              "department": "sales"},
             [0.1, 0.2, 0.30000000004, 1.0 / 3.0]) for n in range(4)]
    index.populate(rows, scope_key=SCOPE_SMALL)
    query = [0.7, 1.0 / 7.0, 0.0, 0.9]
    ranked = index.rank(query, 4, scope_key=SCOPE_SMALL)
    assert ranked is not None and len(ranked) == 4
    exact = []
    for row in rows:
        buffer = array("f", row[3])
        total = sum(Fraction(float(a) - float(b)) ** 2 for a, b in zip(buffer, query))
        exact.append((float(total), row[0]))
    assert [item[1] for item in ranked] == [chunk for _, chunk in sorted(exact,
                                                                         key=lambda x: (x[0], x[1]))]
    for got, (want, _chunk) in zip(ranked, sorted(exact, key=lambda x: (x[0], x[1]))):
        assert got[0] == want, (got[1], got[0], want)


def test_the_numpy_free_distance_path_ranks_the_same(on, monkeypatch):
    """numpy 在不在场，名次与距离都必须一字不差：挡"只在其中一条路上算对"。"""
    rows = [(f"p_{n}_0", f"正文 {n}",
             {"filename": f"p_{n}", "chunk_index": 0, "classification": 1,
              "department": "sales" if n % 2 else "hr"},
             [float(n % 3), 0.1, 1.0 / 3.0, 0.25]) for n in range(6)]
    query = [0.2, 0.7, 1.0 / 3.0, 0.0]
    index = hi.HotSetIndex(max_chunks=10, roster_ttl_seconds=3600.0)
    index.populate(rows, scope_key=SCOPE_SMALL)
    with_numpy = index.rank(query, 6, scope_key=SCOPE_SMALL)
    monkeypatch.setattr(hi, "_NP", None)
    index = hi.HotSetIndex(max_chunks=10, roster_ttl_seconds=3600.0)
    index.populate(rows, scope_key=SCOPE_SMALL)
    without_numpy = index.rank(query, 6, scope_key=SCOPE_SMALL)
    assert [item[1] for item in without_numpy] == [item[1] for item in with_numpy]
    for bare, full in zip(without_numpy, with_numpy):
        assert bare[0] == pytest.approx(full[0], rel=1e-12, abs=1e-12), bare


def test_a_query_vector_that_cannot_be_read_fails_closed(on):
    """读不动的查询向量必须走"整体不用"，绝不能安静交回一个空集当作热集答案。

    下沉之前这条只在"有候选可算"时成立（异常在逐候选算距离时抛）；查询向量升位提到循环
    外之后，连"一个候选都没过筛"的那种空集也不再是答案 —— 这是更严，不是更松。
    """
    index = hi.HotSetIndex(max_chunks=4, roster_ttl_seconds=3600.0)
    index.populate(list(_rows(2)), scope_key=SCOPE_SMALL)
    #: rank 抛 ≠ 检索出错：retriever 那一层把它整体当成"不能服务"（R44 的
    #: test_a_broken_hot_layer_cannot_break_retrieval 钉的就是那一层）。本条只钉"绝不
    #: 安静交回空集"，因为空集会被上层当成热集给的答案。
    with pytest.raises(ValueError):
        index.rank(["读不成数的字符串"], 3, scope_key=SCOPE_SMALL,
                   where={"department": "不存在"})
    assert index.bypass_reason(scope_key=SCOPE_SMALL, where={"department": "不存在"},
                               query_vector=None) == hi.REASON_NO_QUERY_VECTOR


# ==================== 二、名次：热集开启态 vs 关闭态逐条对照 ====================
#
# 实测先钉一条事实（本文件 test_a_tie_group_larger_than_k_is_where_the_two_legs_diverge
# 把它钉成用例）：外部向量库是 HNSW，**并列分段的取舍是任意的** —— 一组完全同距的候选
# 多于 k 时，它交回来的既不是 id 序也不是插入序，而是堆序里的某几个。所以下面分两层：
#
# * 无并列（每个候选距离互不相同）：逐条严格同序同 id，分值给容差 —— 判据③要的那句话；
# * 有并列：比距离剖面 + "热集给的每一条都不比外部库差" + 热集自身对并列的裁决确定性。
#
# 两层合起来才是"float32 下沉没改名次"。只比第一层是漏测（漏掉并列），只声称第二层
# 能做严格同序比对是自证。真机 37 483 chunk 上的对照数字在交付回执③里。

#: 六篇 × 三块。两篇共用一支轴向量 ⇒ 跨文档完全并列。
PINNED_CORPUS = (
    ("aa_hot_one.txt", "住宿", "sales", 1, _unit(0)),
    ("ab_hot_two.txt", "住宿", "sales", 1, _unit(0)),
    ("bc_hr.txt", "年假", "hr", 2, _unit(1)),
    ("cd_finance.txt", "预算", "finance", 3, _unit(2)),
    ("de_ops.txt", "动火", "ops", 1, _unit(3)),
    ("ef_hashed.txt", "提成", "sales", 1, None),
)
#: 同样六篇三块，但一支向量都不指定，且六个关键词互不相同：全部走哈希桩 ⇒ 18 条向量互不
#: 相同，才谈得上"无并列"。上面那两篇共用"住宿"是有意的（要的就是并列），这里不能照抄。
OPEN_CORPUS = (
    ("aa_open_one.txt", "住宿", "sales", 1, None),
    ("ab_open_two.txt", "差旅", "sales", 1, None),
    ("bc_open_hr.txt", "年假", "hr", 2, None),
    ("cd_open_fin.txt", "预算", "finance", 3, None),
    ("de_open_ops.txt", "动火", "ops", 1, None),
    ("ef_open_sales.txt", "提成", "sales", 1, None),
)
TIED_QUERIES = ("q-zero", "q-near-aa", "q-two-axes", "q-far-axis", "q-odd-scale")
OPEN_QUERIES = ("住宿费标准是多少", "差旅交通怎么报销", "年假按工龄怎么算",
                "营销费用占比怎么调", "动火作业要找谁报备", "提成比例写在哪里",
                "完全不相关的量子隧穿问题")
AXIS_VECTORS = {
    "q-zero": [0.0] * DIM,
    "q-near-aa": _unit(0),
    "q-two-axes": [1.0, 1.0] + [0.0] * (DIM - 2),
    "q-far-axis": _unit(7),
    "q-odd-scale": [1.0 / 3.0, 2.0 / 7.0] + [0.0] * (DIM - 2),
}
SCOPES = (
    ("不过滤", None, None),
    ("跨部门", {"department": {"$in": ["sales", "hr"]}}, None),
    ("部门加密级", {"$and": [{"classification": {"$in": [1, 2]}},
                             {"department": {"$in": ["sales"]}}]}, None),
    ("谓词与下推同口径", {"department": {"$in": ["sales", "hr"]}},
     lambda item: item["department"] in ("sales", "hr")),
)


class _Mirror:
    """真临时向量库 + 按内容定点的 embedding 桩：同一批向量，两条腿各问一次。"""

    def __init__(self, tmp_path, monkeypatch, corpus):
        mirror = self
        keyword_to_vector = {row[1]: row[4] for row in corpus if row[4] is not None}

        def fake_call_api(_self, text):
            text = str(text)
            if text in AXIS_VECTORS:
                return list(AXIS_VECTORS[text])
            for keyword, vector in keyword_to_vector.items():
                if keyword in text:
                    return list(vector)
            return _hash_vector(text, DIM)

        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api", fake_call_api)
        self.index = hi.HotSetIndex(max_chunks=10_000, roster_ttl_seconds=3600.0)
        monkeypatch.setattr(hi, "_HOT_INDEX", self.index)
        hi.reset_hot_index_diagnostics()
        self.monkeypatch = monkeypatch
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        for filename, keyword, department, classification, vector in corpus:
            #: 每段的正文都随 part 变，块与块之间才拉得开距离；关键词仍然在每段里，
            #: 定点向量（并列那两篇）照样命中。
            body = "\n\n".join(
                f"第 {part} 段 关于{keyword}的口径说明 " + (f"{keyword}{part}号细则补充文字" * 40)
                for part in range(3))
            ok, message = self.retriever.add_document(filename, body,
                                                      classification=classification,
                                                      department=department)
            assert ok, message
        loaded = self.retriever.collection.get(include=["metadatas"])
        self.chunk_ids = sorted(str(item) for item in loaded["ids"])
        assert len(self.chunk_ids) >= 15, self.chunk_ids

    def search(self, question, k, where=None, pred=None, *, hot):
        if hot:
            self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
            self.index.reset(reason="mirror pass")
        else:
            self.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
        return self.retriever.search(question, k=k, where=where, pred=pred)

    def keys(self, hits):
        return [(hit["source"], hit["chunk_index"]) for hit in hits]

    def store_query(self, embedding, n_results, where=None):
        raw = self.retriever.collection.query(
            query_embeddings=[embedding], n_results=n_results,
            **({"where": where} if where else {})) or {}
        return ([str(item) for item in (raw["ids"][0] or [])],
                [float(item) for item in (raw["distances"][0] or [])])


def _exact_distances(vectors, embedding):
    """进程内精确扫描（与热集同一套算术，float32 分量 + float64 累加）。"""
    query = hi._float64_view(embedding)
    return {chunk_id: hi._squared_l2(vector, query) for chunk_id, vector in vectors.items()}


def _all_vectors(mirror):
    loaded = mirror.retriever.collection.get(ids=mirror.chunk_ids, include=["embeddings"])
    return {str(chunk_id): array("f", vector)
            for chunk_id, vector in zip(loaded["ids"], loaded["embeddings"])}


#: 相邻名次至少隔这么多，才配得上"严格同序"这条判据：间距与浮点尾差同量级时，顺序一致
#: 没有信息量。R44 用的是"间隔 > 1000 × 尾差"，那支尺子在它的样例距离（~1）下成立；这里
#: 的哈希桩距离能上千，float32 SIMD 的绝对尾差随距离线性放大到 1e-3 量级，所以把倍数降到
#: 100 并把地板抬到 1e-2 —— 两个数都比最大观测尾差大两个数量级，判据强度没有实质让步。
GAP_FLOOR = 1e-2
GAP_MULTIPLIER = 100.0


def _separated(distances, floor=GAP_FLOOR):
    """这批距离彼此分得够开吗？分不开就说明出现了并列，该走并列那层判据。"""
    values = sorted(distances)
    return all(following - previous >= floor
               for previous, following in zip(values, values[1:]))


@pytest.fixture
def open_mirror(tmp_path, monkeypatch):
    return _Mirror(tmp_path, monkeypatch, OPEN_CORPUS)


@pytest.fixture
def tied_mirror(tmp_path, monkeypatch):
    return _Mirror(tmp_path, monkeypatch, PINNED_CORPUS)


def test_the_open_corpus_really_has_no_identical_vectors(open_mirror):
    """反例前提：这一层的向量互不相同，才有资格谈"严格同序"。"""
    vectors = _all_vectors(open_mirror)
    assert len(vectors) >= 15, len(vectors)
    distinct = {tuple(vector) for vector in vectors.values()}
    assert len(distinct) == len(vectors), "语料里出现了完全相同的向量，换关键词重来"


def test_hot_and_external_store_return_the_same_top_k_in_the_same_order(open_mirror, capsys):
    """判据③硬约束：同一条查询，开启态与关闭态 top-k 逐条同序同 id（分值给容差）。

    覆盖面：7 条查询 × 4 种权限口径（含跨部门 $in 与"部门 + 密级"$and）× k∈{3,5}。
    每一组都先确认"这一刀切下去两边没有并列"（前 k+1 名的距离彼此相距 >= GAP_FLOOR）；
    切口上出现并列的那些组交给下面的并列用例量 —— 拿并列组做严格同序断言，量到的是
    HNSW 的堆序，不是名次。距离剖面整体还要与一次精确扫描对得上，挡的是"近似图漏人"。
    """
    vectors = _all_vectors(open_mirror)
    total = len(open_mirror.chunk_ids)
    differences = []
    served = comparisons = skipped = 0
    max_abs = max_rel = 0.0
    min_ratio = float("inf")
    for question in OPEN_QUERIES:
        embedding = open_mirror.retriever.embedding.embed_query(question)
        for label, where, pred in SCOPES:
            full_ids, full_distances = open_mirror.store_query(embedding, total, where)
            assert len(full_ids) == len(full_distances) >= 6, (question, label)
            scope_vectors = {chunk: vectors[chunk] for chunk in full_ids}
            exact = _exact_distances(scope_vectors, embedding)
            #: 先量"外部库有没有漏人"：距离剖面必须与进程内精确扫描逐位对得上。
            for store_distance, exact_distance in zip(sorted(full_distances),
                                                      sorted(exact.values())):
                assert abs(store_distance - exact_distance) <= max(
                    SCORE_ABS_TOL, SCORE_REL_TOL * store_distance), (question, label)
            for k in (3, 5):
                head = full_distances[:k + 1]
                if len(head) < k + 1 or not _separated(head):
                    skipped += 1
                    continue
                comparisons += 1
                #: 切口无并列 ⇒ 前 k+1 名的次序是唯一的，谁排前面没有第二种答案。
                assert full_ids[:k + 1] == [chunk for chunk, _distance in sorted(
                    exact.items(), key=lambda pair: (pair[1], pair[0]))][:k + 1], \
                    (question, label, k, "外部库这一趟排不出唯一名次")
                external = open_mirror.search(question, k, where, pred, hot=False)
                external_keys = open_mirror.keys(external)
                assert external_keys, (question, label, k)
                before = hi.hot_index_diagnostics()["hits"]
                hot = open_mirror.search(question, k, where, pred, hot=True)
                served += int(hi.hot_index_diagnostics()["hits"] > before)
                if open_mirror.keys(hot) != external_keys:
                    differences.append((question, label, k, "路由层不同序",
                                        external_keys, open_mirror.keys(hot)))
                #: 多取一名：名次间隔要和"它两边各自的尾差"比，不是和全局最大尾差比。
                ranked = open_mirror.index.rank(embedding, k + 1, where=where)
                assert ranked is not None, open_mirror.index.bypass_reason(
                    scope_key=open_mirror.index.scope_key, where=where,
                    query_vector=embedding)
                hot_ids = [item[1] for item in ranked]
                hot_distances = [item[0] for item in ranked]
                if hot_ids[:k] != full_ids[:k]:
                    differences.append((question, label, k, "rank 与库不同序",
                                        full_ids[:k], hot_ids[:k]))
                deltas = []
                for store_distance, hot_distance in zip(full_distances, hot_distances):
                    delta = abs(store_distance - hot_distance)
                    deltas.append(delta)
                    max_abs = max(max_abs, delta)
                    max_rel = max(max_rel, delta / max(store_distance, 1e-12))
                    assert delta <= max(SCORE_ABS_TOL, SCORE_REL_TOL * store_distance), \
                        (question, label, k, store_distance, hot_distance, delta)
                for position in range(len(deltas) - 1):
                    gap = full_distances[position + 1] - full_distances[position]
                    margin = GAP_MULTIPLIER * max(deltas[position], deltas[position + 1])
                    assert gap > margin, (question, label, k, position, gap, margin)
                    min_ratio = min(min_ratio, gap / margin)
    with capsys.disabled():
        print(f"\n[R79 判据③一致性] 严格同序对照 {comparisons} 组（{len(OPEN_QUERIES)} 查询 × "
              f"{len(SCOPES)} 口径 × k∈{{3,5}}，切口上有并列而剔除 {skipped} 组），"
              f"热集实际服务 {served}/{comparisons}")
        print(f"[R79 判据③一致性] 分值最大绝对尾差 {max_abs:.3e}、最大相对尾差 "
              f"{max_rel:.3e}（容差 abs {SCORE_ABS_TOL} / rel {SCORE_REL_TOL}）")
        print(f"[R79 判据③一致性] 最紧的一处名次间隔 = 该处容差上限的 {min_ratio:.1f} 倍"
              f"（要求 > 1，且逐对都过 ⇒ 同序不是碰出来的）")
    for item in differences:
        print("[R79 差异]", item)
    assert differences == []
    assert comparisons >= 30, f"分得开的对照面只剩 {comparisons} 组，这条判据量不到东西"
    assert served == comparisons, "有一组没由热集服务，上面的比对就是自证"
    assert min_ratio > 1.0, min_ratio


def test_the_pinned_corpus_actually_contains_cross_document_exact_ties(tied_mirror):
    """反例前提：并列必须真的跨文档存在，同文档内的并列量不到跨文档名次。"""
    vectors = _all_vectors(tied_mirror)
    by_vector = {}
    for chunk_id, vector in vectors.items():
        by_vector.setdefault(tuple(vector), []).append(chunk_id)
    ties = {key: ids for key, ids in by_vector.items() if len(ids) > 1}
    documents = {chunk_id.rsplit("_", 1)[0] for ids in ties.values() for chunk_id in ids}
    assert len(ties) >= 2 and len(documents) >= 2, (len(ties), sorted(documents))


def test_tied_candidates_keep_the_same_distance_profile_and_a_stable_order(tied_mirror, capsys):
    """并列段：名次序列不许因为下沉而变，且热集自己的裁决是确定的。

    这里刻意不写"与外部库逐条同序"—— 一组完全同距的候选比 k 多时，HNSW 交回的是堆序里
    的任意几个（见下一条用例）。把那种任意性当成"热集该复现的正确答案"是错的口径。
    """
    vectors = _all_vectors(tied_mirror)
    total = len(tied_mirror.chunk_ids)
    profiles = checked = 0
    for question in TIED_QUERIES:
        embedding = tied_mirror.retriever.embedding.embed_query(question)
        for label, where, pred in SCOPES:
            for k in (3, 5):
                checked += 1
                external = tied_mirror.search(question, k, where, pred, hot=False)
                external_keys = tied_mirror.keys(external)
                assert external_keys, (question, label, k)
                before = hi.hot_index_diagnostics()["hits"]
                hot = tied_mirror.search(question, k, where, pred, hot=True)
                assert hi.hot_index_diagnostics()["hits"] > before, (
                    question, label, k, tied_mirror.index.bypass_reason(
                        where=where, query_vector=embedding))
                ranked = tied_mirror.index.rank(embedding, k, where=where,
                                                scope_key=tied_mirror.index.scope_key)
                hot_keys = [(chunk_id.rsplit("_", 1)[0], int(chunk_id.rsplit("_", 1)[1]))
                            for _d, chunk_id, _doc, _meta in ranked]
                assert hot_keys == tied_mirror.keys(hot), (hot_keys, tied_mirror.keys(hot))
                rerun = tied_mirror.index.rank(embedding, k, where=where,
                                               scope_key=tied_mirror.index.scope_key)
                assert [item[1] for item in rerun] == [item[1] for item in ranked], "并列裁决不稳定"
                _ids, full_distances = tied_mirror.store_query(embedding, total, where)
                hot_all = [item[0] for item in tied_mirror.index.rank(
                    embedding, total, where=where, scope_key=tied_mirror.index.scope_key)]
                assert len(hot_all) == len(full_distances), (question, label, k)
                for hot_distance, store_distance in zip(sorted(hot_all),
                                                        sorted(full_distances)):
                    assert abs(hot_distance - store_distance) <= max(
                        SCORE_ABS_TOL, SCORE_REL_TOL * store_distance)
                profiles += 1
                #: 前 k 名的距离也必须逐位对得上（用容差，不用 round 相等：两边一个
                #: float64 累加、一个 float32 SIMD，第 8 位小数本来就不该拿来当判据）。
                for hot_distance, store_distance in zip(hot_all[:k], full_distances[:k]):
                    assert abs(hot_distance - store_distance) <= max(
                        SCORE_ABS_TOL, SCORE_REL_TOL * store_distance)
    with capsys.disabled():
        print(f"\n[R79 判据③并列] 含并列对照 {checked} 组，距离剖面一致 {profiles} 组")
    assert checked == len(TIED_QUERIES) * len(SCOPES) * 2
    assert profiles == checked


def test_a_tie_group_larger_than_k_is_where_the_two_legs_diverge_by_design(tied_mirror, capsys):
    """把那条实测事实钉成用例：并列组比 k 大时，外部库交回的是任意几个，不是"更对"的几个。

    这是 R44 之前就存在的性质（R44 的对照用例用"相邻名次间隔 >> 浮点尾差"绕开了并列），
    本单没改它，也不许后人把它当成"热集排名错了"的证据：热集给的是精确扫描 + (距离, id)
    的稳定裁决，外部库给的是近似图里的堆序。这里钉的是"差异只可能出现在并列段内"。
    """
    tied_mirror.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    tied_mirror.search("q-near-aa", 3, hot=True)      # 先把热集暖起来，下面才轮到裸 rank
    embedding = tied_mirror.retriever.embedding.embed_query("q-zero")
    vectors = _all_vectors(tied_mirror)
    exact = _exact_distances(vectors, embedding)
    k = 3
    store_ids, store_distances = tied_mirror.store_query(embedding, k)
    ranked = tied_mirror.index.rank(embedding, k, scope_key=tied_mirror.index.scope_key)
    assert ranked is not None, tied_mirror.index.bypass_reason(
        scope_key=tied_mirror.index.scope_key, query_vector=embedding)
    hot_ids = [item[1] for item in ranked]
    hot_distances = [item[0] for item in ranked]
    assert [round(item, 9) for item in sorted(hot_distances)] == \
        [round(item, 9) for item in sorted(store_distances)], (hot_ids, store_ids)
    worst_store = max(store_distances)
    for chunk_id in set(hot_ids) - set(store_ids):
        assert exact[chunk_id] <= worst_store + SCORE_ABS_TOL, (
            chunk_id, exact[chunk_id], worst_store, "差异跑到了并列段之外")
    with capsys.disabled():
        print(f"\n[R79 判据③并列] q-zero k={k}：外部库={store_ids} 热集={hot_ids}"
              f"（同一批距离 {sorted(round(item, 6) for item in store_distances)}）")


def test_the_warm_read_path_narrows_nothing_at_all(open_mirror, monkeypatch):
    """把判据③从"实测没翻"升成"按构造就不会翻"。

    向量库读回来的分量本来就是 float32（`list(numpy_row)` 交出的是这些 float32 的精确
    十进制像），所以 `array('f')` 相对 `tuple(float, ...)` 是**零信息损失**的换壳；距离
    又统一在 float64 上累加。于是常驻形态换了、数值一位都没动 —— 这条直接把"排名不得
    改变"钉成等式，而不是靠"跑了很多次没翻"。
    """
    loaded = open_mirror.retriever.collection.get(
        ids=open_mirror.chunk_ids, include=["documents", "metadatas", "embeddings"])
    monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    rows = [(str(chunk_id), document, metadata, list(vector)) for chunk_id, document,
            metadata, vector in zip(loaded["ids"], loaded["documents"],
                                    loaded["metadatas"], loaded["embeddings"])]
    narrow = hi.HotSetIndex(max_chunks=10_000, roster_ttl_seconds=3600.0)
    narrow.populate(rows, scope_key=SCOPE_SMALL)
    monkeypatch.setattr(hi, "_compact_vector", tuple)     # 逐字退回 R79 之前的常驻形态
    wide = hi.HotSetIndex(max_chunks=10_000, roster_ttl_seconds=3600.0)
    wide.populate(rows, scope_key=SCOPE_SMALL)
    assert narrow.resident_chunks == wide.resident_chunks == len(rows)
    for chunk_id, _document, _metadata, vector in rows:
        assert list(narrow._entries[chunk_id].vector) == list(wide._entries[chunk_id].vector)
        assert list(narrow._entries[chunk_id].vector) == [float(item) for item in vector]
    def deep_size(entry_vector) -> int:
        """tuple 侧的真实代价 = 指针数组本身 + 每个分量各自还是一个对象。

        向量库读回来的是 numpy float32 标量（各 28 字节），array('f') 侧则是把数值直接
        排在缓冲里，一个对象都不额外占 —— 这笔差额才是判据③要省的东西。
        """
        size = sys.getsizeof(entry_vector)
        if isinstance(entry_vector, tuple):
            size += sum(map(sys.getsizeof, entry_vector))
        return size

    narrow_bytes = sum(map(deep_size, (entry.vector for entry in narrow._entries.values())))
    wide_bytes = sum(map(deep_size, (entry.vector for entry in wide._entries.values())))
    print(f"\n[R79 判据③] {len(rows)} 条常驻向量：float32 {narrow_bytes / 1e3:.0f} KB vs "
          f"tuple {wide_bytes / 1e3:.0f} KB")
    assert narrow_bytes * 4 < wide_bytes
    for question in OPEN_QUERIES:
        embedding = open_mirror.retriever.embedding.embed_query(question)
        first = narrow.rank(embedding, len(rows), scope_key=SCOPE_SMALL)
        second = wide.rank(embedding, len(rows), scope_key=SCOPE_SMALL)
        assert first is not None and second is not None
        assert [item[1] for item in first] == [item[1] for item in second], question
        assert [item[0] for item in first] == [item[0] for item in second], (question,
            "距离值不等：不只是名次没变，连分数都没变")
