"""R165 · 把 R158 那枚检索形状读数接上一处现成的只读出口。

工单 R165（跟进单 §84 五）。背景：并树枚 0e99e85 交出 app/rag/retriever.py 的
search_shape_diagnostics()（四枚结局码 + 三枚答复方 + 逐问累计计数），**没有任何生产
消费者**——这笔欠账写在该枚提交信息的最后一段。于是客户问出一句「索引里查无此物」，运维
今天仍旧只能看见一个空列表，它与「检索根本没跑成」在界面上还是同一张脸。本文件钉接上之后：

- 判据①：读数挂在 app/common/monitoring.py::build_health_snapshot 这张**已有**的只读出口上
  （/api/v1/health/details 就是从它作答的，路由体形状由 tests/test_compute_wiring.py 钉着），
  并且走本页所有边界共用的同一枚 _subsystem_state 入口——不新造第二套聚合口径（R135·S1 原话）。
  节内键名逐字取自 retriever 的返回值（last / totals / answered_by），出口侧不翻译、不改名、
  不重排成另一张表。
- 判据②：跑一次检索 ⇒ 出口读数跟着变；且 leg_returned_zero_rows 与 vector_store_failed 两张
  脸在**响应体**上分得开。这就是本单的全部价值，只把个数挂上去的出口过不了这一节。
- 判据③：两把反证常驻在本文件里。① 出口写成常数 ⇒「同一出口交出三张不同的表」当场红；
  ② 把 _record_search_shape 的调用摘掉 ⇒ 检索照旧跑、出口当场变哑。交工账里另有两把物理反证：
  真把出口改成常量、真把那处记账调用删掉（后者跑完已还原，retriever.py 一字未改）。
- 判据④：隐私钉在**出口响应体**的字节上数，不在读数函数里数——查询原文、命中正文、部门与
  密级的实际值一律不许出现在 GET /api/v1/health/details 上。canary 打法沿用 R158，换了靶面。
- 判据⑤：app/rag/retriever.py 一个字未改（本文件只 import 它），search() 的返回形状不动。

全程零模型、零 PG、零 Docker、零起服务：检索腿是真 DocumentRetriever.search() 配假
collection（应答形状逐字段抄 chromadb，一次 embedding 都不发）；出口是进程内 TestClient 打
真路由，三枚宿主探针换成桩（R56 / R79 既有口径）。
"""
import ast
import inspect
import json

import pytest

from app.common import monitoring
from app.rag import hot_index
from app.rag import retriever as rt

HEALTH_PATH = "/api/v1/health/details"
#: 出口里那一节的节名：必须是 retriever 侧那本账自己的名字，不是出口起的别名。
SECTION = "search_shape"
DIM = rt.EMBEDDING_DIM

#: 判据④ 的四枚记号：查询原文、命中正文、部门实际值、密级实际值。任何一枚出现在出口
#: 响应体的字节里即为红。带 r165 后缀是为了不与其它文件的记号互相撞红。
QUERY_CANARY = "查看其他部门的工资明细-r165-canary"
BODY_CANARY = "salary-body-r165-canary-MUST-NOT-LEAK"
DEPARTMENT_CANARY = "dept-r165-canary-board-secretariat"
CLASSIFICATION_CANARY = "cls-r165-canary-level-five"

#: 判据③ 反证① 的形状：常数出口绝不可能在复位之后交回一张空表。
EMPTY_LEDGER = {"last": None, "totals": {}, "answered_by": {}}

#: retriever 的返回值有哪三枚键、什么顺序，出口就必须照抄，一字不译。
LEDGER_KEYS = ["last", "totals", "answered_by"]

#: 读数里允许出现的字段全集＝retriever 自己记的那十个。多一枚就是出口在另起口径。
READING_KEYS = {
    "collection", "answered_by", "leg", "degradation_reason", "n_results_requested",
    "rows_returned", "hits_built", "rows_lost", "outcome", "store_error",
}

#: 出口那一节里绝不该出现的键（正文与权限面的字段）。判据④ 的结构面钉子。
FORBIDDEN_KEYS = frozenset({
    "content", "query", "question", "document", "documents", "metadata", "metadatas",
    "source", "filename", "department", "classification", "chunk_index", "ids",
    "embeddings", "distances", "principal", "user", "username",
})

#: R158 那四枚结局码——"这一问到底成了什么"。出口侧一个字都不许写它们（判据①「不许翻译」）。
OUTCOME_CODES = (
    rt.RETRIEVAL_OUTCOME_ANSWERED,
    rt.RETRIEVAL_OUTCOME_ZERO_ROWS,
    rt.RETRIEVAL_OUTCOME_ROWS_DROPPED,
    rt.RETRIEVAL_OUTCOME_STORE_FAILED,
)
assert len(set(OUTCOME_CODES)) == 4, "R158 的四枚结局码不再互不相同：本单的钉子要重读"


# ==================================================== 假向量库：应答形状抄 chromadb
class _StubCollection:
    """只认 query() 的假 collection：交回什么、抛什么全由用例摆好。

    刻意不引 chromadb：本文件钉的是「账本里的数怎么走到出口」，后端给的回答是输入而不是
    结论。name 会被记进 last.collection，那是 retriever 自己的字段，不是出口的发明。
    """

    name = "r165_stub_collection"

    def __init__(self, columns=None, *, raises=None, flat=None):
        self.columns = columns if columns is not None else _columns([])
        self.raises = raises
        self.flat = flat if flat is not None else {"ids": [], "documents": [], "metadatas": []}
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return dict(self.columns)

    def get(self, where=None):
        return dict(self.flat)


class _VectorEmbedder:
    """固定向量当查询：不发 socket、不打模型。"""

    def __init__(self, vector=None):
        self.vector = list(vector) if vector is not None else [0.0] * DIM

    def embed_query(self, text):
        return list(self.vector)


class _RaisingEmbedder:
    """embedding 挂掉的形状：带稳定原因码的 EmbeddingError，走关键词降级腿。"""

    def __init__(self, reason="model_unavailable"):
        self.reason = reason

    def embed_query(self, text):
        raise rt.EmbeddingError("model down", reason=self.reason)


class _FakeHotIndex:
    """热集那一腿的假索引：rank() 交回摆好的名次，populated 恒真（免整库回读）。"""

    def __init__(self, ranked):
        self.ranked = list(ranked)
        self.populated = True

    def adopt_scope(self, scope_key):
        return None

    def warm_retry_blocked(self):
        return False

    def rank(self, query_vector, k, *, where=None, pred=None, scope_key=None,
             stores_vectors=True):
        return list(self.ranked)


def _metadata(filename, chunk_index):
    """部门与密级放**记号值**：判据④ 要验的是实际值不上出口，不是键名不存在。"""
    return {"filename": filename, "chunk_index": chunk_index,
            "classification": CLASSIFICATION_CANARY, "department": DEPARTMENT_CANARY}


def _columns(names, *, bodies=None, metadatas="auto"):
    """chromadb 的二维应答：一次请求一行、行内是候选。

    metadatas="none" 交回空列，那是「库给了行、我们配不出命中」的靶子形状。
    """
    names = list(names)
    if bodies is None:
        bodies = [f"body of {name}" for name in names]
    columns = {
        "ids": [[f"cid-{name}-{position}" for position, name in enumerate(names)]],
        "documents": [list(bodies)],
        "distances": [[0.1 * (position + 1) for position in range(len(names))]],
    }
    if metadatas == "auto":
        columns["metadatas"] = [[_metadata(name, position)
                                 for position, name in enumerate(names)]]
    else:
        columns["metadatas"] = [[]]
    return columns


def _flat(names):
    return {
        "ids": [f"cid-{name}" for name in names],
        "documents": [f"部门工资明细 {name}" for name in names],
        "metadatas": [_metadata(name, 0) for name in names],
    }


@pytest.fixture(scope="module")
def retriever():
    """一把真 DocumentRetriever，后端与 embedding 由各用例现换（与 R158 同法）。

    全模块共用一枚：构造函数会冷起一个 chromadb 客户端（R134 已把它改道进沙箱）。
    """
    instance = rt.DocumentRetriever(activity_prior=lambda: {})
    instance.embedding = _VectorEmbedder()
    return instance


@pytest.fixture(autouse=True)
def _clean_ledger_and_default_legs(monkeypatch):
    """每枚用例从空账本开始，并默认关掉热集，否则「这一问是谁答的」混成一团。"""
    rt.reset_search_shape()
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    yield
    rt.reset_search_shape()


@pytest.fixture
def client(monkeypatch):
    """真路由 + 真鉴权 + 进程内 TestClient；三枚宿主探针按 R56 / R79 既有口径换桩。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})
    test_client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth.create_token('admin')}"}

    def _get():
        response = test_client.get(HEALTH_PATH, headers=headers)
        assert response.status_code == 200, response.text
        return response

    return _get


def _wire(instance, collection, embedder=None):
    instance.collection = collection
    instance.embedding = embedder or _VectorEmbedder()
    return instance


def _block(response) -> dict:
    """出口响应体里那一节。缺节即红——本单交的就是这一节。"""
    body = response.json()
    assert SECTION in body, f"出口上没有 {SECTION} 这一节：{sorted(body)}"
    return body[SECTION]


# ======================================= 判据① 接的是那张已有的出口，且一个字段都没翻译
def test_the_outlet_publishes_a_search_shape_section(client):
    """运维在一次只读健康请求里就能读到这本账，不必另找出口。"""
    block = _block(client())

    assert list(block) == LEDGER_KEYS, (
        f"出口节内的键名/键序与 retriever 的返回值不再逐字一致：{list(block)}")
    assert block == EMPTY_LEDGER, "没跑过检索的出口必须是空表，不是任何默认值"


def test_the_section_is_the_ledger_itself_in_the_same_order(client, retriever):
    """判据①「不许改名、不许重排」做成正面验证：出口交的就是账本自己，逐字段同序。"""
    _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资明细", k=2)

    ledger = rt.search_shape_diagnostics()
    block = _block(client())

    assert block == ledger
    assert list(block) == list(ledger), "节内的键被出口重排过"
    assert list(block["last"]) == list(ledger["last"]), "读数里的字段被出口重排过"
    assert json.loads(json.dumps(block)) == json.loads(json.dumps(ledger))


def test_the_outlet_writes_no_stable_code_of_its_own():
    """判据①「不许翻译」：出口那一侧的源码里没有一枚 retriever 结局码的字面量。

    出口一旦把 vector_store_failed 写成 error 或一句人话，它就成了第二套口径，运维拿这份与
    拿那份对不上。这里按 AST 精确匹配字符串常量，不按子串：四枚结局码里 answered 与三枚答复
    方里 hot_index / chroma 这些词本来就是本页既有的节名（R44 / R79 先于本单），拿子串比会
    假红。答复方那三枚由上一枚用例的逐字段相等管住，不需要在这儿重复钉。
    """
    constants = {
        node.value for node in ast.walk(ast.parse(inspect.getsource(monitoring)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    leaked = sorted(constants & set(OUTCOME_CODES))
    assert not leaked, f"出口自己写出了 retriever 的结局码字面量：{leaked}"


def test_the_section_rides_the_existing_accessor_not_a_bespoke_wrapper():
    """判据①「不新造第二套聚合口径」：与 model_budget 走同一枚 _subsystem_state 入口。"""
    source = inspect.getsource(monitoring.build_health_snapshot)

    assert '"search_shape": _subsystem_state(' in source, source
    assert '"app.rag.retriever", "search_shape_diagnostics"' in source, source
    # 出口没有另立一枚读函数：这本账在监控侧只有一个来源，就是 retriever 自己。
    published = monitoring._subsystem_state(
        "app.rag.retriever", "search_shape_diagnostics")
    assert published == rt.search_shape_diagnostics(), (
        "健康页读到的与 retriever 交出的不是同一份数字")
    assert not hasattr(monitoring, "_search_shape_state"), (
        "出口自己包了一层，就有了第二套口径的苗头")


# =========================================== 判据② 跑一次检索 ⇒ 出口读数跟着变
def test_one_search_moves_the_outlet(client, retriever):
    """「活表」的定义：同一枚出口，检索前后读到两张不同的表。"""
    before = _block(client())
    assert before["last"] is None and before["totals"] == {}

    hits = _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt", "c.txt"]))).search(
        "工资明细", k=3)

    after = _block(client())
    assert hits and after != before, "跑了一次检索而出口没动：接的是一根空线"
    assert after["last"]["outcome"] == rt.RETRIEVAL_OUTCOME_ANSWERED
    assert after["last"]["rows_returned"] == 3 and after["last"]["hits_built"] == 3
    assert after["last"]["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    assert after["totals"] == {rt.RETRIEVAL_OUTCOME_ANSWERED: 1}
    assert after["answered_by"] == {rt.RETRIEVAL_SERVER_CHROMA: 1}


def test_a_question_with_no_neighbour_reads_as_zero_rows_on_the_outlet(client, retriever):
    """P3 那 24/135 题的脸：那条腿正常答复、就是没给行。这不是故障。"""
    hits = _wire(retriever, _StubCollection(_columns([]))).search("查看其他部门的工资明细", k=5)

    last = _block(client())["last"]

    assert hits == [], "search() 的返回形状不许动：这里仍然是一个空列表"
    assert last["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert last["rows_returned"] == 0 and last["hits_built"] == 0
    assert last["store_error"] == ""


def test_a_store_that_throws_reads_as_vector_store_failure_on_the_outlet(client, retriever):
    """另一张脸：库抛异常。异常照旧上抛（R158 判据②(d)），但出口上留下了它的名字。"""
    boom = ValueError("Expected where operator to have non-empty list")

    with pytest.raises(ValueError) as caught:
        _wire(retriever, _StubCollection(raises=boom)).search("工资明细", k=5)

    assert caught.value is boom, "出口这一单不碰异常语义"
    last = _block(client())["last"]
    assert last["outcome"] == rt.RETRIEVAL_OUTCOME_STORE_FAILED
    assert last["store_error"] == "ValueError"


def test_the_two_faces_are_apart_on_the_outlet_body(client, retriever):
    """本单的全部价值落在这一枚：调用方两次都拿到 []，出口两次给出两枚码。

    只把计数挂上去的用例过不了这一节——这里比的是两次阅读里 outcome 字段本身，并钉住
    「故障那一格绝不会被读成查无此物」。
    """
    _wire(retriever, _StubCollection(_columns([]))).search("工资明细", k=5)
    no_neighbour = _block(client())

    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资明细", k=5)
    store_failed = _block(client())

    assert no_neighbour["last"]["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert rt.RETRIEVAL_OUTCOME_STORE_FAILED not in no_neighbour["totals"]
    assert store_failed["last"]["outcome"] == rt.RETRIEVAL_OUTCOME_STORE_FAILED
    assert store_failed["last"]["store_error"] == "ValueError"
    assert no_neighbour["last"]["outcome"] != store_failed["last"]["outcome"]
    # 两次阅读在出口字节上就是两张不同的表，不是「同一个数大了点」
    assert json.dumps(no_neighbour, sort_keys=True) != json.dumps(store_failed, sort_keys=True)
    assert store_failed["totals"] == {
        rt.RETRIEVAL_OUTCOME_ZERO_ROWS: 1, rt.RETRIEVAL_OUTCOME_STORE_FAILED: 1}


def test_the_rows_dropped_face_is_a_third_cell_on_the_outlet(client, retriever):
    """库给了 2 行、命中建成 0 条：这一格既不是「库里没邻居」也不是「库挂了」。"""
    _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"], metadatas="none"))).search(
        "工资明细", k=2)

    last = _block(client())["last"]

    assert last["outcome"] == rt.RETRIEVAL_OUTCOME_ROWS_DROPPED
    assert last["rows_returned"] == 2 and last["hits_built"] == 0 and last["rows_lost"] == 2


def test_the_outlet_answers_how_many_questions_wore_each_face(client, retriever):
    """判据②「别做成只挂个数」的另一半：数要能对上逐问算术。"""
    for _ in range(3):
        _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资", k=2)
    for _ in range(2):
        _wire(retriever, _StubCollection(_columns([]))).search("工资", k=2)
    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资", k=2)

    block = _block(client())

    assert block["totals"] == {
        rt.RETRIEVAL_OUTCOME_ANSWERED: 3,
        rt.RETRIEVAL_OUTCOME_ZERO_ROWS: 2,
        rt.RETRIEVAL_OUTCOME_STORE_FAILED: 1,
    }
    assert block["answered_by"] == {rt.RETRIEVAL_SERVER_CHROMA: 6}
    assert sum(block["totals"].values()) == 6 == sum(block["answered_by"].values())


def test_the_keyword_degradation_leg_names_its_answerer_on_the_outlet(client, retriever):
    """embedding 挂了、这一轮是词法兜底答的：出口上要说清是谁答的、为什么退。"""
    store = _StubCollection(_columns([]), flat=_flat(["payroll.txt"]))
    _wire(retriever, store, _RaisingEmbedder()).search("部门工资明细", k=3)

    last = _block(client())["last"]

    assert last["answered_by"] == rt.RETRIEVAL_SERVER_KEYWORD_STORE
    assert last["leg"] == rt.RETRIEVAL_MODE_KEYWORD
    assert last["degradation_reason"] == "model_unavailable"


def test_a_zero_from_the_hot_leg_is_not_blamed_on_the_vector_store(client, retriever,
                                                                   monkeypatch):
    """热集交回 0 行时外部向量库压根没被问过：出口上那一格的答复方必须是 hot_index。"""
    store = _StubCollection(_columns(["never-asked.txt"]))
    _wire(retriever, store)
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: True)
    monkeypatch.setattr(hot_index, "get_hot_index", lambda: _FakeHotIndex([]))

    hits = retriever.search("工资明细", k=5)

    assert hits == [] and store.query_calls == []
    block = _block(client())
    assert block["last"]["answered_by"] == rt.RETRIEVAL_SERVER_HOT_INDEX
    assert block["last"]["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert block["answered_by"] == {rt.RETRIEVAL_SERVER_HOT_INDEX: 1}


# ================================================== 判据③ 两把反证必须咬
def test_the_outlet_is_not_a_constant_table(client, retriever):
    """反证①：把出口写成常数，这枚用例当场红。

    同一枚出口要能交出三张互不相同的表：复位之后的空表、正常命中那张、库挂了那张。任何
    「抄一份快照挂在这儿」的常量出口都会在第一次比较上就撞红。
    """
    empty = _block(client())

    _wire(retriever, _StubCollection(_columns(["a.txt"]))).search("工资", k=1)
    answered = _block(client())

    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资", k=1)
    failed = _block(client())

    assert empty == EMPTY_LEDGER, "常数表交不出「复位之后是空的」这一事实"
    readings = [json.dumps(block, sort_keys=True) for block in (empty, answered, failed)]
    assert len(set(readings)) == 3, f"出口在三种真实下交回了同一张表：{readings}"


def test_unplugging_the_recording_call_blanks_the_outlet(client, retriever, monkeypatch):
    """反证②：把 _record_search_shape 的调用摘掉 ⇒ 出口必须变哑。

    这里用 monkeypatch 把那枚记账函数换成空实现，等价于删掉 search() 里那些调用：检索照旧
    交出命中（同时证明出口不是从命中列表现算的），而读数必须当场归零。
    """
    _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资", k=2)
    assert _block(client())["last"] is not None, "接线本身要先成立，否则下面的红是假红"

    rt.reset_search_shape()
    monkeypatch.setattr(rt, "_record_search_shape", lambda **kwargs: None)
    hits = _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资", k=2)

    block = _block(client())
    assert hits, "摘掉记账之后检索仍然正常交回命中：出口读的不是命中列表"
    assert block == EMPTY_LEDGER, (
        f"调用被摘掉而出口还能交出检索的读数，说明它另有一套数：{block}")


# =============================================== 判据④ 隐私钉在出口响应体上数
def _walk_keys(node, seen=None):
    seen = set() if seen is None else seen
    if isinstance(node, dict):
        for key, value in node.items():
            seen.add(str(key))
            _walk_keys(value, seen)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _walk_keys(value, seen)
    return seen


def test_the_query_text_never_reaches_the_outlet_body(client, retriever):
    """判据④：出口响应体的字节里没有查询原文——R158 那两枚 canary 的打法，换到出口面数。"""
    _wire(retriever, _StubCollection(_columns([]))).search(QUERY_CANARY, k=5)

    response = client()

    assert QUERY_CANARY not in response.text, "客户问的那句话上了健康出口"
    assert _block(response)["last"]["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS, (
        "这条钉不许靠「出口什么都没说」蒙绿：这一问确实被记下来了")


def test_the_hit_content_never_reaches_the_outlet_body(client, retriever):
    """命中正文不许上出口：出口记的是「这一问成了几行」，不是那几行写了什么。"""
    store = _StubCollection(_columns(["payroll.txt"], bodies=[BODY_CANARY]))

    hits = _wire(retriever, store).search("工资明细", k=5)

    response = client()
    assert hits[0]["content"] == BODY_CANARY, "正文得真的进了命中，否则这条钉是空转"
    assert BODY_CANARY not in response.text, "命中的正文上了健康出口"


def test_no_department_or_classification_value_reaches_the_outlet_body(client, retriever):
    """权限面的实际值（部门、密级）不许上出口——私有化部署里这是最贵的一类泄漏。"""
    _wire(retriever, _StubCollection(_columns(["payroll.txt"]))).search("工资明细", k=5)

    response = client()
    block = _block(response)
    assert block["last"] is not None, (
        "这一问得真的被记进出口，否则下面三条钉子全是空转")

    assert DEPARTMENT_CANARY not in response.text, "部门实际值上了健康出口"
    assert CLASSIFICATION_CANARY not in response.text, "密级实际值上了健康出口"
    # 结构面：这一节里没有一处键名容得下正文或权限字段（密级若是整数，光数文本数不出来）
    keys = _walk_keys(block)
    assert not (keys & FORBIDDEN_KEYS), (
        f"出口那一节里出现了正文/权限字段：{sorted(keys & FORBIDDEN_KEYS)}")
    assert set(block["last"]) <= READING_KEYS, (
        f"出口给读数加了 retriever 没给的字段：{sorted(set(block['last']) - READING_KEYS)}")


# ================================================ 观测不许改变被观测的东西
def test_reading_the_outlet_asks_the_vector_store_nothing(client, retriever):
    """健康轮询每隔几秒一次：它绝不允许顺手再问一次检索，否则观测改变被观测量。"""
    store = _StubCollection(_columns(["a.txt"]))
    _wire(retriever, store).search("工资", k=1)

    del store.query_calls[:]
    for _ in range(5):
        client()

    assert store.query_calls == [], "读一次出口把向量库又问了一遍"
    assert _block(client())["totals"] == {rt.RETRIEVAL_OUTCOME_ANSWERED: 1}, (
        "反复读出口把计数读涨了")


def test_the_shape_section_never_becomes_a_health_verdict(client, retriever):
    """与 embedding / hot_index 同一纪律：这本账不并进 problems，也不改 status。

    「索引里查无此物」不是当下故障；出口只负责把它说清楚，不负责替运维判红绿——判红绿就是
    在出口侧另起一套口径，判据① 不许。
    """
    clean = client().json()

    _wire(retriever, _StubCollection(_columns([]))).search("工资", k=5)
    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资", k=5)
    dirty = client().json()

    assert dirty["status"] == clean["status"], "形状读数把一个健康判定改色了"
    assert dirty["problems"] == clean["problems"], "形状读数往 problems 里塞了新东西"
    assert dirty[SECTION] != clean[SECTION], "上面两条若永不成立，它们是空钉"
