"""R79 判据①：热集观测必须读得到 HTTP 面，而且一个字都不碰那颗钉死形状的钉子。

口径：
* `hot_index_diagnostics()` 的形状被 R44 用例钉成五个键的精确相等
  （tests/test_r44_hot_index_chroma.py 既断言"读一眼前后全等"，又断言全等字典就是那五项），
  所以配置态与实例态一律走本单新增的独立出口 `hot_index_snapshot()`，那颗钉不动。
* 运维在 /api/v1/health/details 上必须一次看全：开关态、hits/misses/invalidations、
  常驻条数、最近一次绕行原因码，以及 HOT_INDEX_* 到底解析成了什么。
* 开关关闭时这一块**必须照样在场**并如实标 enabled=False —— "没装这层"和"装了但关了"
  是两件事，整块消失等于让后者冒充前者。

动手前 grep 出的既存钉子（本单全部按纯加法放行、一条都没改）：
  tests/test_compute_wiring.py:166  路由体必须是 build_health_snapshot(...) 的形状
  tests/test_deployment_guards.py:100,245,335  钉 storage.subsystems / status
  tests/test_r21_health_probe.py:84-154,211  钉 dependencies / embedding / problems
  tests/test_r51_stage_latency.py:665  钉 performance 块
  tests/test_security_operations.py:71  钉 performance 在场
  tests/test_model_discovery_selection.py:108、tests/test_r70_dotenv_isolation.py:57  钉 model 块
"""

import hashlib
import json

import pytest

from app.common import monitoring
from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

#: 判据①点名要看见的字段，逐个钉，不用"差不多"糊过去。
REQUIRED_KEYS = {
    "enabled", "hits", "misses", "invalidations", "resident_chunks",
    "last_bypass_reason", "max_chunks", "roster_ttl_seconds", "cold_chunks",
}

#: 那颗钉的完整形状。往后谁想加键，先在这里撞一下。
PINNED_DIAGNOSTICS_SHAPE = {"hits": 0, "misses": 0, "invalidations": 0,
                            "resident_chunks": 0, "last_bypass_reason": ""}

#: 路由上必须逐字段同源的计数。
COUNTER_KEYS = ("hits", "misses", "invalidations", "resident_chunks", "last_bypass_reason")


def _hash_vector(text: str, dim: int) -> list:
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    return vector if any(vector) else [1.0] + [0.0] * (dim - 1)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
    monkeypatch.delenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, raising=False)
    hi.reset_hot_index_diagnostics()
    yield
    hi.reset_hot_index_diagnostics()


class _Store:
    """一套临时向量库 + 一个顶掉进程内单例的热集：路由读的就是它。"""

    def __init__(self, tmp_path, monkeypatch, *, from_env=False, **index_kwargs):
        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api",
                            lambda _self, text: _hash_vector(
                                str(text), retriever_module.EMBEDDING_DIM))
        kwargs = ({} if from_env else
                  {"max_chunks": 10_000, "roster_ttl_seconds": 3600.0})
        kwargs.update(index_kwargs)
        self.index = hi.HotSetIndex(**kwargs)
        monkeypatch.setattr(hi, "_HOT_INDEX", self.index)
        hi.reset_hot_index_diagnostics()
        self.monkeypatch = monkeypatch
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.calls = []
        collection = self.retriever.collection
        real_get, real_query = collection.get, collection.query

        def get(*args, **kwargs_):
            self.calls.append("get")
            return real_get(*args, **kwargs_)

        def query(*args, **kwargs_):
            self.calls.append("query")
            return real_query(*args, **kwargs_)

        collection.get, collection.query = get, query

    def add(self, filename, content, *, department="sales"):
        ok, message = self.retriever.add_document(filename, content,
                                                  classification=1, department=department)
        assert ok, message

    def on(self):
        self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")

    def search(self, query, k=3):
        del self.calls[:]
        return self.retriever.search(query, k=k)


@pytest.fixture
def client(monkeypatch):
    """真路由 + 真鉴权；宿主 Ollama 探针按 R56 既有口径换掉，本文件不关心它。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    test_client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth.create_token('admin')}"}
    return lambda: test_client.get("/api/v1/health/details", headers=headers)


def _block(response) -> dict:
    assert response.status_code == 200, response.status_code
    body = response.json()
    assert "hot_index" in body, sorted(body)
    return body["hot_index"]


# ==================== 钉子本身：没被绕过、也没被塞键 ====================

def test_the_pinned_diagnostics_dictionary_still_has_exactly_five_keys(off):
    """本单的加法没有动那颗钉：五键精确相等仍然成立。"""
    assert hi.hot_index_diagnostics() == PINNED_DIAGNOSTICS_SHAPE
    snapshot = hi.hot_index_snapshot()
    assert set(PINNED_DIAGNOSTICS_SHAPE) < set(snapshot), "新观测必须是另开的出口"


# ==================== 出口层：快照自己说得清 ====================

def test_the_snapshot_carries_every_field_judgement_one_asks_for(off):
    """关闭态也必须一次读全：开关、四个计数、常驻、配置，一个都不许缺。"""
    snapshot = hi.hot_index_snapshot()
    missing = REQUIRED_KEYS - set(snapshot)
    assert not missing, f"缺字段：{sorted(missing)}"
    assert snapshot["enabled"] is False, "开关没设就是关，观测面得照实说"
    assert isinstance(snapshot["max_chunks"], int) and snapshot["max_chunks"] > 0
    assert isinstance(snapshot["roster_ttl_seconds"], float)


def test_reading_the_snapshot_is_side_effect_free(off, tmp_path, monkeypatch):
    """纯读：账不动、库不碰、而且必须能过 JSON —— 它是给 HTTP 面用的。"""
    store = _Store(tmp_path, monkeypatch)
    store.add("a.txt", "住宿费标准是每晚500元。")
    store.search("住宿费标准是多少")
    del store.calls[:]
    ledger_before = hi.hot_index_diagnostics()
    json.dumps(hi.hot_index_snapshot())
    assert hi.hot_index_diagnostics() == ledger_before, "读一眼前后必须全等"
    assert store.calls == [], store.calls
    json.dumps(hi.hot_index_snapshot())


def test_the_snapshot_reports_the_real_switch_states(monkeypatch):
    """开关口径与检索腿共用同一个函数：观测面不许自成一套真值判断。"""
    for raw, expected in (("", False), ("0", False), ("ture", False),
                          ("1", True), ("TRUE", True), ("on", True)):
        monkeypatch.setenv(hi.HOT_INDEX_ENV, raw)
        assert hi.hot_index_snapshot()["enabled"] is expected, raw


# ==================== 判据①本体：真路由上看得见 ====================

def test_the_route_shows_the_block_as_disabled_when_the_switch_is_off(client, off):
    """关了就标 disabled，绝不让整块消失：那会让运维分不清"没装"与"关了"。"""
    block = _block(client())
    assert block["enabled"] is False, block
    assert set(REQUIRED_KEYS) <= set(block), sorted(block)
    ledger = hi.hot_index_diagnostics()
    assert {key: block[key] for key in COUNTER_KEYS} == {key: ledger[key] for key in COUNTER_KEYS}
    assert block["roster_built"] is False or block["enabled"] is False


def test_the_route_numbers_come_from_the_same_ledger_as_the_process(client, tmp_path,
                                                                   monkeypatch):
    """判据①的"同源"：路由上那五个字段与进程内计数器逐字段相等，不是第二次统计。"""
    store = _Store(tmp_path, monkeypatch)
    store.add("a.txt", "住宿费标准是每晚500元。")
    store.add("b.txt", "年假按工龄计算。", department="hr")
    store.on()
    assert store.search("住宿费标准是多少")
    assert store.calls == ["get", "get"], store.calls      # 一次暖机，两笔只读
    assert store.search("住宿费标准是多少")
    assert store.calls == [], "第二问必须一个外部调用都不发"

    ledger = hi.hot_index_diagnostics()
    assert ledger["hits"] == 2, ledger      # 两问都由热集服务，第二问一次外部调用都没发
    block = _block(client())
    assert {key: block[key] for key in COUNTER_KEYS} == {key: ledger[key] for key in COUNTER_KEYS}
    assert block["resident_chunks"] == store.index.resident_chunks > 0
    assert block["enabled"] is True
    assert block["cold_chunks"] == store.index.cold_chunks
    assert block["max_chunks"] == store.index.max_chunks == 10_000
    assert block["roster_ttl_seconds"] == 3600.0


def test_the_last_bypass_reason_reaches_the_operator(client, tmp_path, monkeypatch):
    """绕行原因码是运维唯一看得见的"为什么没走热集"，它必须真能到 HTTP 面。"""
    store = _Store(tmp_path, monkeypatch, max_chunks=1)   # 预算 1 条，语料 2 条 ⇒ 装不下
    store.add("a.txt", "住宿费标准是每晚500元。")
    store.add("b.txt", "年假按工龄计算。", department="hr")
    store.on()
    assert store.search("住宿费标准是多少")
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == hi.REASON_INCOMPLETE
    assert _block(client())["last_bypass_reason"] == hi.REASON_INCOMPLETE


def test_the_configured_values_are_visible_next_to_the_counters(client, tmp_path, monkeypatch):
    """预算/TTL/页大小/冷却窗都要看得见：只有原因码分不出"装不下"与"在冷却"。"""
    monkeypatch.setenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, "7")
    monkeypatch.setenv(hi.HOT_INDEX_MAX_AGE_SECONDS_ENV, "11.5")
    monkeypatch.setenv(hi.HOT_INDEX_ROSTER_PAGE_ENV, "3")
    monkeypatch.setenv(hi.HOT_INDEX_WARM_RETRY_SECONDS_ENV, "4.5")
    store = _Store(tmp_path, monkeypatch, from_env=True)   # 不传 kwargs，走真实解析
    store.add("a.txt", "住宿费标准是每晚500元。")
    store.on()
    store.search("住宿费标准是多少")
    block = _block(client())
    assert block["max_chunks"] == 7
    assert block["roster_ttl_seconds"] == 11.5
    assert block["roster_page"] == 3
    assert block["warm_retry_seconds"] == 4.5
    assert block["roster_built"] is True and block["roster_fresh"] is True
    assert block["warm_retry_blocked"] is False
    assert block["roster_age_seconds"] is not None
    assert block["scope_key"] and block["scope_key"][1]

    #: 进程起来之后改环境变量，单例不会回头改自己。两个口径并列摆出，不许互相冒充。
    monkeypatch.setenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, "9")
    changed = _block(client())
    assert changed["max_chunks"] == 7, "实例生效值不许被此刻的环境变量冒充"
    assert changed["env_config"]["max_chunks"] == 9, "改了没生效这件事必须看得见"


def test_a_warm_failure_shows_as_cooldown_on_the_route(client, tmp_path, monkeypatch):
    """R44b 那颗坑的运维面：冷却中要看得见"在冷却"，而不是只看见它在退库。"""
    store = _Store(tmp_path, monkeypatch)
    store.add("a.txt", "住宿费标准是每晚500元。")
    collection = store.retriever.collection
    real_get = collection.get
    collection.get = lambda *args, **kwargs: (_ for _ in ()).throw(
        RuntimeError("injected: too many SQL variables"))
    store.on()
    assert store.search("住宿费标准是多少")
    collection.get = real_get
    block = _block(client())
    assert block["warm_retry_blocked"] is True, block
    assert block["roster_built"] is False
    assert block["last_bypass_reason"] == hi.REASON_COLD


# ==================== 判据⑤护栏：只加读数，不改脸色 ====================

def test_the_new_block_never_moves_status_or_problems(client, monkeypatch):
    """热集在冷却/在绕行都不该让一次健康巡检变红：这一块刻意不并进 problems。"""
    first = client()
    problems_with, status_with = first.json()["problems"], first.json()["status"]
    assert isinstance(_block(first), dict)
    monkeypatch.setattr(monitoring, "_hot_index_state", lambda: {})
    second = client()
    assert second.json()["problems"] == problems_with
    assert second.json()["status"] == status_with
    assert "hot_index" not in str(problems_with)


def test_a_broken_hot_layer_still_cannot_break_the_health_report(client, monkeypatch):
    """一层可丢弃的缓存读不到时，健康报告宁可说"读不到"，也不替运维猜开关。"""
    def explode():
        raise RuntimeError("injected: hot index is on fire")

    monkeypatch.setattr(hi, "hot_index_snapshot", explode)
    assert _block(client()) == {"enabled": None, "state_error": "unavailable"}
