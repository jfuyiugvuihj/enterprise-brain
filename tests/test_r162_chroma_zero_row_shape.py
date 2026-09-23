"""R162 判据①：Chroma「query 交回 0 条 ids，而 get 读得到这一枚向量」的离线形状账。

背景（跟进单 §80 一 / §84 三）：P3 逐题对比 135 题里 24 题 Chroma 交回 0 条、同一枚向量 PG 交回
精确前 5，而语料级完全对齐。生产面 DocumentRetriever.search() 对此返回空列表，用户看到的是
「没有来源」，真相是「图里问不出邻居」。判据① 要求：在临时目录里用固定播种向量 + 真 chromadb
扫 hnsw:search_ef / hnsw:construction_ef / hnsw:M，看这一形状能不能离线复现。

本件把答案钉成两半，因为读数本身就是两半：

- **无过滤那一支复现不出**（前四枚用例）：ef / construction_ef / M 全扫、数值退化向量、
  以及「图还在、行被干净删掉九成」三种打法，交回的行数恒等于请求行数。所以派工要求的那枚
  只读诊断件 scripts/diag_r162_chroma_zero_rows.py 是交付的那一支。
- **过滤那一支复现得出**（test_the_filter_shaped_zero_...）：where 打在库从来没写过的键上，
  query 交回 0 条 ids、get(where=...) 交回 0 行，而 get(ids=[本枚]) 照样读得到那枚向量
  ——同一枚库的两张脸，离线就能造出来。P3 那 24 题走的是**不带 where** 的那一支
  （scripts/compare_vector_recall.py:459 的调用形状），所以这一支不能替它们结案，
  只能说：生产面 DocumentRetriever.search() 的 0 里有这么一类，而且它是可复现、可钉的。

全程不打 Ollama、不连 PostgreSQL、不碰仓内那枚被跟踪的 chroma_db：向量是本地算出来的，
库开在 tmp_path 里。
"""
import importlib.util
import struct
from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb")
from chromadb.config import Settings  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DIAG_PATH = REPO / "scripts" / "diag_r162_chroma_zero_rows.py"
DIMENSION = 8
REQUESTED_ROWS = 5


def _diag():
    """按路径装载诊断件：它在 scripts/ 下，不是包内模块。"""
    spec = importlib.util.spec_from_file_location("diag_r162_chroma_zero_rows", DIAG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vector(cluster, axis):
    """一枚确定性的「簇心」分量：不引随机数，跑几遍都是同一批向量。"""
    value = ((cluster + 3) * 2654435761 + (axis + 7) * 40503) & 0xFFFF
    return value / 4096.0


def _clustered(count, *, clusters=8, jitter=0.004):
    """count 枚按簇排布的向量：同一簇内彼此很近，簇与簇之间隔得很远。

    「问哪一簇」因此是一个能控的变量——判据② (b) 说「某枚向量在图里没有邻居」，
    只有把邻居密度做成局部量，才谈得上问它。
    """
    vectors = []
    for index in range(count):
        cluster = index % clusters
        spin = index // clusters
        vectors.append([_vector(cluster, axis) + jitter * (spin % 13 - 6)
                        for axis in range(DIMENSION)])
    return vectors


def _open(directory, name="enterprise_docs", hnsw=None):
    client = chromadb.PersistentClient(path=str(directory),
                                       settings=Settings(anonymized_telemetry=False))
    metadata = {"hnsw:space": "l2"}
    for key, value in (hnsw or {}).items():
        metadata["hnsw:" + key.replace("hnsw:", "")] = value
    collection = client.get_or_create_collection(name, metadata=metadata)
    return client, collection


def _add(collection, vectors, *, metadatas=None, start=0):
    for offset in range(0, len(vectors), 200):
        block = vectors[offset:offset + 200]
        collection.add(ids=["c%d" % (start + offset + i) for i in range(len(block))],
                       embeddings=block,
                       metadatas=(metadatas[offset:offset + 200] if metadatas else None))


def _rows(collection, vector, **kwargs):
    got = collection.query(query_embeddings=[list(vector)],
                           n_results=kwargs.pop("k", REQUESTED_ROWS), **kwargs)
    return got, len(((got.get("ids") or [[]])[0] or []))


@pytest.fixture(scope="module")
def diag_module():
    if not DIAG_PATH.exists():
        pytest.fail("判据① 的交付件不存在：" + str(DIAG_PATH))
    return _diag()

# ==================== 判据① 的第一半：无过滤那一支复现不出 ====================

#: 派工点名的三枚参数，加上「什么都不设」的默认档，一次扫完。
HNSW_GRID = [
    {},
    {"search_ef": 100, "M": 16},
    {"search_ef": 10, "M": 4},
    {"search_ef": 1000, "construction_ef": 400, "M": 32},
]


@pytest.mark.parametrize("hnsw", HNSW_GRID,
                         ids=["defaults", "ef100-m16", "ef10-m4", "ef1000-ce400-m32"])
def test_unfiltered_queries_return_every_requested_row_across_the_ef_and_m_grid(tmp_path, hnsw):
    """扫 hnsw:search_ef / construction_ef / M：无过滤的 query 交不回 0 行。

    400 枚播种向量 × 每簇簇心 + 每枚存储向量自身，一共近千次问法，行数恒等于请求数。
    这一枚用例就是「本机真库形状无法离线复现」这句话里**离线那半**的证据。
    """
    _, collection = _open(tmp_path, hnsw=hnsw)
    vectors = _clustered(400)
    _add(collection, vectors)
    assert collection.count() == 400
    probes = list(vectors) + [_clustered(clusters, clusters=clusters)[-1]
                              for clusters in (1, 4, 8)]
    short = []
    for probe in probes:
        _, rows = _rows(collection, probe)
        if rows != REQUESTED_ROWS:
            short.append(rows)
    assert short == [], "这些问法交回的行数不是 %d：%s" % (REQUESTED_ROWS, short)


def test_degenerate_query_vectors_still_get_rows_back(tmp_path):
    """数值退化不是 0 行的理由：全零 / 溢出 / 极小 / 极大四种问法都照样交回前 5。

    判据② (b) 说的是「HNSW 在某 ef / 连通性下返回不足」，而退化向量是最容易把图问空的输入；
    连这些都问得出邻居，(b) 就少了一条自由。
    """
    _, collection = _open(tmp_path, hnsw={"search_ef": 10, "M": 4})
    vectors = _clustered(200)
    _add(collection, vectors)
    degenerate = {
        "all-zero": [0.0] * DIMENSION,
        "overflow-ish": [1e19] * DIMENSION,
        "denormal": [1e-30] * DIMENSION,
        "absurdly-large": [1e150] * DIMENSION,
    }
    for name, probe in degenerate.items():
        _, rows = _rows(collection, probe)
        assert rows == REQUESTED_ROWS, "%s 这一问交回了 %d 行" % (name, rows)


def test_clean_deletion_of_ninety_percent_still_returns_full_rows(tmp_path):
    """「图还在、行被删掉九成」也问不出 0 行：局部损伤交不出**选择性**的 0。

    这一枚是给判据② (c) 用的反证：如果 24/135 的成因是「一部分向量没被索引覆盖」，
    那么删掉一大片之后，问在那一片上应当交回不足 5 行甚至 0 行。真库的删法是走
    collection.delete 的干净删法（图里标删、行拿走），实测仍然交回 5 行
    ——库会自己往外扩候选，把 k 填满。所以「局部缺口」这条因**在形状上就给不出 0**。
    """
    _, collection = _open(tmp_path, hnsw={"search_ef": 100, "M": 16})
    vectors = _clustered(800)
    _add(collection, vectors)
    victims = ["c%d" % index for index in range(0, 800, 2)]
    collection.delete(ids=victims)
    assert collection.count() == 400
    for probe in vectors[:40]:
        _, rows = _rows(collection, probe)
        assert rows == REQUESTED_ROWS, "删掉一半以后这一问只交回 %d 行" % rows
    emptied = ["c%d" % index for index in range(1, 800, 2)]
    collection.delete(ids=emptied)
    assert collection.count() == 0
    _, rows = _rows(collection, vectors[0])
    assert rows == 0, "库被清空以后仍然问得出邻居，那说明读数不是从库里来的"

# ==================== 判据① 的第二半：过滤那一支复现得出 ====================

#: 生产 scope 过滤器真会发出的形状（app/rag/filters.py 把它拼成 classification $in）。
#: 这里按字面重写一份而不是 import：app.rag.filters 一进门就带出 .env 与建库副作用。
PRODUCTION_WHERE = {"classification": {"$in": [1, 2, 3]}}
PRODUCTION_WHERE_AND = {"$and": [{"classification": {"$in": [1]}},
                                 {"department": {"$in": ["研发中心"]}}]}


@pytest.mark.parametrize("where", [PRODUCTION_WHERE, PRODUCTION_WHERE_AND],
                         ids=["classification-$in", "and-classification-department"])
def test_the_filter_shaped_zero_reproduces_both_faces_offline(tmp_path, where):
    """复现得出的那一支：query 交回 0 条 ids，而 get(ids=[本枚]) 照样读得到向量。

    条件是 where 打在库**从来没写过**的那枚键上。这一支把派工要求的「一句话读数」
    钉住了：这一形状的 0 与「图里问不出邻居」的 0 在读数上不同脸——前者 get(where=...)
    也是 0（过滤面本来就空），后者 get(where=...) 有行而 query 交回 0。P3 那 24 题走的是
    不带 where 的调用，所以这一支只能算「同款两脸的一种已知成因」，不能替它们结案。
    """
    _, collection = _open(tmp_path)
    vectors = _clustered(120)
    _add(collection, vectors, metadatas=[{"filename": "doc.txt", "chunk_index": i}
                                         for i in range(len(vectors))])
    probe = vectors[0]
    got, rows = _rows(collection, probe, where=where)
    assert rows == 0, "库里有 120 行却没被这条 where 滤空，用例的前提就变了"
    assert got["ids"] == [[]], "ids 的形状不是「外层一列、列里空」，两脸读数会认错"
    assert len(collection.get(where=where, include=[])["ids"]) == 0
    one = collection.get(ids=["c0"], include=["embeddings", "metadatas"])
    assert one["ids"] == ["c0"]
    assert one["embeddings"] is not None and len(one["embeddings"]) == 1
    back = [float(value) for value in one["embeddings"][0]]
    assert back == pytest.approx([float(value) for value in probe], rel=0, abs=1e-6)


def test_a_nonempty_allow_set_never_drops_below_the_requested_rows(tmp_path):
    """反向对照：where 落在**写得着的**键上时，过滤不会把邻居滤成 0。

    上一枚因此不是「chroma 的 where 一律交回 0」这种废话——它只在允许集为空时两脸分开。
    """
    _, collection = _open(tmp_path)
    vectors = _clustered(120, clusters=6)
    _add(collection, vectors, metadatas=[{"filename": "doc-%d.txt" % (i % 6),
                                          "chunk_index": i} for i in range(len(vectors))])
    for probe in vectors[:20]:
        _, rows = _rows(collection, probe, where={"filename": {"$in": ["doc-1.txt"]}})
        assert rows == REQUESTED_ROWS, "允许集里有 20 行，这一问却只交回 %d 行" % rows


# ==================== 诊断件自身的诚实性 ====================

def test_the_segment_reader_reports_what_the_persisted_index_actually_holds(tmp_path, diag_module):
    """字节解析器在**健康库**上给出的两个数必须与库自报的一致，且正向缺口为 0。

    判据② (c) 的全部账都走这枚解析器，所以它先要能被证伪：图内元素数 == pickle 里的
    total_elements_added，孤儿节点 == 0，正向缺口 == 0。落盘时机本身是 chroma 的事
    （sync_threshold 之前只有一部分进了文件），所以缺口只按「已经落盘的这一份」算，
    并把没落盘的行数照实报成 forward_hole——不猜、不补。
    """
    _, collection = _open(tmp_path)
    vectors = _clustered(1_100)
    _add(collection, vectors)
    assert collection.count() == 1_100
    store = tmp_path
    segment = next((path for path in store.iterdir()
                    if (path / "data_level0.bin").exists()), None)
    assert segment is not None, "chroma 没有把 HNSW 落盘，本件的量法在这台机器上就不成立"
    info = diag_module.read_hnsw_segment(segment, DIMENSION)
    assert info["parse"] == "ok", info
    assert info["entries"] == info["index_pickle"]["total_elements_added"]
    assert len(set(info["labels"])) == info["entries"]
    seq_rows = _seq_map(store)
    account = diag_module.coverage_account(info, seq_rows, lambda _i, _s: "本枚用例不比向量")
    assert account["index_orphans"] == 0, account["index_orphan_runs"]
    assert account["store_rows"] == 1_100
    assert account["forward_hole"] + account["covered"] == account["store_rows"]
    assert account["forward_hole"] == account["store_rows"] - info["entries"]


def test_the_segment_reader_refuses_to_guess_on_garbage(tmp_path, diag_module):
    """算术反证不成立时报 unverified，而不是交出一枚猜出来的元素数。"""
    junk = tmp_path / "segment"
    junk.mkdir()
    (junk / "header.bin").write_bytes(struct.pack("<4I", 1, 2, 3, 4))
    (junk / "data_level0.bin").write_bytes(bytes(4099))
    info = diag_module.read_hnsw_segment(junk, DIMENSION)
    assert info["parse"] == "unverified", info
    assert diag_module.coverage_account(info, {}, None) == {"parse": "unverified"}


def _seq_map(store):
    import sqlite3
    connection = sqlite3.connect("file:" + str(store / "chroma.sqlite3").replace("\\", "/")
                                 + "?mode=ro&immutable=1", uri=True)
    try:
        return {row[0]: row[1] for row in
                connection.execute("SELECT seq_id, embedding_id FROM embeddings")}
    finally:
        connection.close()

def test_the_diag_refuses_a_missing_directory_and_an_in_repo_out_path(tmp_path, diag_module):
    """前置不满足就走退出码 2，且 --out 落在仓内时**立刻**拒绝：诊断输出不许落仓。

    第二条尤其要钉：本件的 --out 是全场唯一一处「往盘上写」的地方，判据写着诊断输出
    不落仓，那就得让它在复制库之前、打开任何句柄之前就拒绝，而不是写完再道歉。
    """
    with pytest.raises(SystemExit) as missing:
        diag_module.main(["--chroma-dir", str(tmp_path / "never-made")])
    assert missing.value.code == diag_module.EXIT_PRECONDITION
    with pytest.raises(SystemExit) as inside:
        diag_module.main(["--chroma-dir", str(tmp_path / "whatever"),
                          "--out", str(REPO / "diag-should-not-land.json")])
    assert inside.value.code == diag_module.EXIT_PRECONDITION
    assert not (REPO / "diag-should-not-land.json").exists()


def test_the_manifest_recompare_catches_a_writable_probe(tmp_path, diag_module):
    """「打开一次就把 sqlite 写脏」是本机实测过的形状，所以收尾复比必须是硬闸。

    这里造一枚最小的脏：先取清单，再往文件里追加一个字节，复比必须抓到它。
    抓不到就等于本件对源目录只读这件事没人守。
    """
    source = tmp_path / "chroma_db"
    source.mkdir()
    victim = source / "chroma.sqlite3"
    victim.write_bytes(b"original bytes, twelve")
    before = diag_module.manifest(source)
    victim.write_bytes(b"original bytes, twelve-plus")
    after = diag_module.manifest(source)
    dirty = {key: value for key, value in after.items() if before.get(key) != value}
    assert list(dirty) == ["chroma.sqlite3"], dirty
