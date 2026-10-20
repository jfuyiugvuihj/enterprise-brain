r"""R330 · 把 pg_store 那三本向量侧观测账接上 /health/details 这张已有的只读出口。

工单 R330（跟进单 §84 五 / 采纳计划书 P5）。这是 R165 那笔账的**同一类病**的第二次：R158 把
retriever 的检索形状读数交出来时没有生产消费者，R165 才把它接上出口（app/common/monitoring.py:254
那段 search_shape）。今天 app/rag/pg_store.py 里同样只读的三本账——vector_mirror_diagnostics(:141)
/ vector_corpus_diagnostics(:865) / vector_read_diagnostics(:928)——在 app/** 里仍旧零消费者
（217d542 实测只命中定义自身与注释）。切读单在途、退役单排在后面，而运维在客户机上没有任何出口能
回答「这一问读的是哪条腿、绕行过几次、为什么绕」，等于交了出口没接消费。本文件钉接上之后：

- 判据①：三枚节挂在 build_health_snapshot 这张**已有**的只读出口上，走本页所有边界共用的同一枚
  _subsystem_state 入口，不新造包装、不新开第四本账、不新增计数器、不加新错误码。
- 判据②：节名照 search_shape 的取法（函数名去掉 _diagnostics 后缀，不是出口起的别名）；节内键名
  与键序逐字照抄 pg_store 的返回字段，出口不翻译、不改名、不重排——出口里一枚 pg_store 的字段名或
  值码都不许出现，出现一枚就是它在抄第二本账。
- 判据③：探针抛异常只降级成 unavailable，一次健康检查不许被打挂（200 而不是 500），另两枚节照实交出。
- 判据④：三枚节刻意不并进 problems，也不改 status——「这次读的是遗留腿」是配置事实，不是当下故障。
- 判据⑤：零 IO。两把尺：一次冷导入子进程（socket 一开就抛，psycopg / pypdf 不许进 sys.modules）；
  一次出口调用（把 pg_store 里所有会连库的入口换成会抛的桩，出口仍要交出**真数字**，退化成
  unavailable 也算红——那说明它真的去连过一次，只是被 _subsystem_state 吞了）。

反证（判据⑥）在本文件里的常驻钉子：
① 出口上删掉任一枚节 ⇒ test_the_outlet_publishes_the_three_pg_sections 与
   test_the_sections_are_the_ledgers_themselves_in_the_same_order 当场红（缺节、缺键）；
② 任一枚探针抛异常 ⇒ 该节必须等于 _unavailable_state("status_probe_failed: ...")，整页仍 200；
③ 真 switched_corpus() 报 legacy_chroma ⇒ 出口里必须看得见这个值，且三枚 diagnostics 至今仍
   pg_store 的原始对象（本文件一枚 mock 都没打进账本）；
④ 出口写成常数 ⇒ 跑过真代码之后出口仍是空账，test_the_sections_are_the_ledgers_themselves 红。

全程零模型、零 PG、零 Docker、零起服务：账本由真 pg_store 代码驱动（VectorMirror.build_rows 的
R130 具名早拒、switched_corpus 的语料腿拒答），出口是进程内 TestClient 打真路由，三枚宿主探针按
R56 / R79 / R165 既有口径换桩。app/rag/pg_store.py 本单只读，一个字未改。
"""
from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.common import monitoring
from app.rag import indexing, pg_store, retriever

REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_PATH = "/api/v1/health/details"

#: 节名 -> pg_store 里的函数名。节名是**派生**的（函数名去掉 _diagnostics），不是出口起的别名，
#: 那一层关系由 test_the_section_names_are_derived_not_invented 钉住。
SECTIONS = {
    "vector_mirror": "vector_mirror_diagnostics",
    "vector_corpus": "vector_corpus_diagnostics",
    "vector_read": "vector_read_diagnostics",
}

#: 判据②：节内键名与键序，逐字抄自 pg_store 的返回值（:144-149 / :850 / :814-815）。
LEDGER_KEYS = {
    "vector_mirror": ["mirrored_writes", "mirrored_deletes", "rejected_writes", "last_failure"],
    "vector_corpus": ["reads", "rows", "source", "reason"],
    "vector_read": ["attempts", "answered", "rows", "bypasses", "last_bypass"],
}

#: 一条腿都没跑过时三本账长这样。出口写成常数就会在这里红（反证④）。
EMPTY_LEDGERS = {
    "vector_mirror": {"mirrored_writes": 0, "mirrored_deletes": 0,
                      "rejected_writes": 0, "last_failure": None},
    "vector_corpus": {"reads": 0, "rows": 0, "source": "", "reason": ""},
    "vector_read": {"attempts": 0, "answered": 0, "rows": 0, "bypasses": {}, "last_bypass": None},
}

#: pg_store 自己写出来的值码。出口侧一枚都不许出现（判据②「不翻译」）。
VALUE_CODES = frozenset({
    pg_store.CORPUS_SOURCE_PGVECTOR,
    pg_store.CORPUS_SOURCE_LEGACY,
    pg_store.CORPUS_SOURCE_NOT_SWITCHED,
    pg_store.REASON_VECTOR_MIRROR_TEXT_UNENCODABLE,
    pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE,
    pg_store.REASON_VECTOR_READ_TABLE_UNRECOGNISED,
    pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE,
    pg_store.REASON_VECTOR_READ_OPERATOR_UNKNOWN,
    pg_store.REASON_VECTOR_READ_FAILED,
})

#: 三本账的字段名。出口里一枚都不许出现——出现一枚就是它抄了第二本账（判据①「不许新开」）。
LEDGER_FIELDS = frozenset(key for keys in LEDGER_KEYS.values() for key in keys)

#: 驱动 vector_mirror 那本账的口径。与真机 768 无关：镜像这条腿只认库口径（R130 同手法）。
DIM = 8
MODEL = "nomic-embed-r330"
VECTOR_ID = "r330.txt_0"
NUL = chr(0)
DIRTY_CHUNK = "第一段" + NUL + "第二段"

#: 本文件绝不许把账本换成桩：先记下三枚原始对象，逐枚验明正身。
_ORIGINALS = {name: getattr(pg_store, name) for name in SECTIONS.values()}


def _reset_pg_ledgers() -> None:
    pg_store.reset_vector_mirror_diagnostics()
    pg_store.reset_vector_corpus_diagnostics()
    pg_store.reset_vector_read_diagnostics()


def _live_ledgers() -> dict:
    return {name: getattr(pg_store, function)() for name, function in SECTIONS.items()}


@pytest.fixture(autouse=True)
def _clean_pg_ledgers(monkeypatch):
    """每枚用例从空账本开始，并把两枚开关按生产默认值钉住（宿主的 .env 不许进进程）。"""
    monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    _reset_pg_ledgers()
    yield
    _reset_pg_ledgers()


@pytest.fixture
def client(monkeypatch):
    """真路由 + 真鉴权 + 进程内 TestClient；三枚宿主探针按 R56 / R79 / R165 既有口径换桩。"""
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


@pytest.fixture
def dirty_mirror(monkeypatch):
    """真代码驱动 vector_mirror 那本账：R130 的具名早拒，不开 cursor、不发 SQL。"""
    monkeypatch.setenv(indexing.EMBEDDING_MODEL_ENV, MODEL)
    monkeypatch.setenv(indexing.EMBEDDING_DIMENSION_ENV, str(DIM))
    monkeypatch.setattr(retriever, "EMBEDDING_DIM", DIM)

    def _drive() -> dict:
        scope = pg_store.VectorScope(embedding_model=MODEL, dimension=DIM,
                                     distance_function="cosine")
        mirror = pg_store.VectorMirror(None, scope=scope, column_type=f"vector({DIM})",
                                       vector_table=pg_store.DEFAULT_VECTOR_TABLE)
        with pytest.raises(retriever.VectorWriteRejectedError) as refused:
            mirror.build_rows([VECTOR_ID], [DIRTY_CHUNK],
                              [{"filename": "r330.txt", "chunk_index": 0}], [[0.25] * DIM])
        assert refused.value.reason == pg_store.REASON_VECTOR_MIRROR_TEXT_UNENCODABLE
        return pg_store.vector_mirror_diagnostics()

    return _drive


@pytest.fixture
def legacy_corpus(monkeypatch):
    """反证③ 的正身：切读开着、双写关着，真 switched_corpus() 退回遗留库并记一笔绕行。"""
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    assert pg_store.switched_corpus() is None, "这一腿没退回遗留库，下面的钉子就全是空转"
    return pg_store.vector_corpus_diagnostics()


def _sections(response) -> dict:
    """出口响应体里那三枚节。缺节即红——本单交的就是这三枚节。"""
    body = response.json()
    missing = [name for name in SECTIONS if name not in body]
    assert not missing, f"出口上没有这三枚节：缺 {missing}；实有 {sorted(body)}"
    return {name: body[name] for name in SECTIONS}


# ============================== 判据①② 接的是那张已有的出口，一个字段都没翻译
def test_the_outlet_publishes_the_three_pg_sections(client):
    """运维在一次只读健康请求里就能读到这三本账，不必翻日志、不必跑脚本。"""
    blocks = _sections(client())

    for name, keys in LEDGER_KEYS.items():
        assert list(blocks[name]) == keys, (
            f"{name} 节内的键名/键序与 pg_store 的返回值不再逐字一致：{list(blocks[name])}")
        assert blocks[name] == EMPTY_LEDGERS[name], (
            "一条腿都没跑过的出口必须交出空账，不是任何出口自己发明的默认值")


def test_the_sections_are_the_ledgers_themselves_in_the_same_order(client, legacy_corpus,
                                                                   dirty_mirror):
    """判据①② 的正面验证：跑过真代码之后，出口交的就是账本自己，逐字段同序，一枚不多一枚不少。"""
    dirty_mirror()
    ledgers = _live_ledgers()
    blocks = _sections(client())

    assert blocks == ledgers, "出口读到的与 pg_store 交出的不是同一份数字"
    for name in SECTIONS:
        assert list(blocks[name]) == list(ledgers[name]), f"{name} 节的键被出口重排过"
    assert json.loads(json.dumps(blocks)) == json.loads(json.dumps(ledgers))
    # 反证④：出口不是常数——三本账此刻都真的带着真值，常数出口交不出这些
    assert blocks["vector_mirror"]["rejected_writes"] == 1
    assert blocks["vector_corpus"]["source"] == pg_store.CORPUS_SOURCE_LEGACY
    assert blocks["vector_read"]["bypasses"] == {
        pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE: 1}


def test_the_ledger_functions_were_never_replaced_by_a_stub(client, legacy_corpus, dirty_mirror):
    """本单存在的意义：出口读的是那三枚真函数，不是测试喂给它的假数字。"""
    dirty_mirror()
    client()

    for name, function in SECTIONS.items():
        assert getattr(pg_store, function) is _ORIGINALS[function], (
            f"{function} 被换成了桩：出口读到的不是 pg_store 那本真账")
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_LEGACY


def test_the_section_names_are_derived_not_invented():
    """节名只能是函数名去掉 _diagnostics 后缀——出口不许给账本起别名。"""
    assert all(f"{name}_diagnostics" == function for name, function in SECTIONS.items())


def test_the_legacy_leg_is_visible_on_the_outlet_itself(client, legacy_corpus, dirty_mirror):
    """本单存在的全部意义：运维在一次 GET 里看得见「这一问读的是遗留腿」，以及它为什么绕。

    这一枚不许用 mock 交差——值来自真 switched_corpus() 的真拒答（fixture 里那一次），断言打在
    出口响应体上，所以把出口写成常数、或把节改了名，都会在这里当场红。
    """
    dirty_mirror()
    body = _sections(client())

    assert body["vector_corpus"]["source"] == pg_store.CORPUS_SOURCE_LEGACY, (
        f"出口上没有那一格读数：{body['vector_corpus']}")
    assert body["vector_corpus"]["reads"] == 1 and body["vector_corpus"]["rows"] == 0
    assert "VectorReadRejectedError" in body["vector_corpus"]["reason"], (
        "绕行原因要跟着值一起看得见，不是只报一个码")
    assert body["vector_read"]["bypasses"] == {
        pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE: 1}, "为什么绕行的那一格也得在出口上"


def test_the_sections_ride_the_existing_accessor_not_a_bespoke_wrapper():
    """判据①：三枚节都走 _subsystem_state 这同一枚入口，监控侧一个字的聚合口径都没另开。"""
    source = inspect.getsource(monitoring.build_health_snapshot)

    for name, function in SECTIONS.items():
        assert f'"{name}": _subsystem_state(' in source, (name, source)
        assert f'"app.rag.pg_store", "{function}"' in source, (name, function)
    # 恰有三处：多一处就是本单禁止的「第四本账」，少一处就是三枚键里被摘了哪一枚
    assert source.count('"app.rag.pg_store"') == 3, source
    assert _subsystem_readout("vector_read_diagnostics") == pg_store.vector_read_diagnostics(), (
        "健康页读到的与 pg_store 交出的不是同一份数字")

    bespoke = [name for name in vars(monitoring)
               if "vector" in name.lower() or "pg_store" in name.lower()]
    assert not bespoke, f"监控侧另开了读向量账的私有件，就是第二套口径的苗头：{bespoke}"


def _subsystem_readout(function: str) -> dict:
    return monitoring._subsystem_state("app.rag.pg_store", function)


def test_the_outlet_writes_no_pg_code_or_field_of_its_own():
    """判据①「不许新开会计」+ 判据②「不许翻译」：出口那几行里既没有值码字面量，也没有字段名。"""
    snapshot = ast.parse(inspect.getsource(monitoring.build_health_snapshot))
    constants = {
        node.value for node in ast.walk(snapshot)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    translated = sorted(constants & VALUE_CODES)
    assert not translated, f"出口自己写出了 pg_store 的值码字面量：{translated}"
    copied = sorted(constants & LEDGER_FIELDS)
    assert not copied, f"出口在抄第二本账，它自己写出了这些字段名：{copied}"


def test_the_copied_field_names_are_pg_stores_own():
    """LEDGER_KEYS 不是本文件发明的：它与 pg_store 此刻交出的键逐字同序。"""
    for name, function in SECTIONS.items():
        assert LEDGER_KEYS[name] == list(getattr(pg_store, function)()), name


# ================================================== 判据③ 探针抛异常只降级，不打挂整页
@pytest.mark.parametrize("section", sorted(SECTIONS))
def test_a_raising_ledger_degrades_to_unavailable_not_a_500(client, monkeypatch, section):
    """三枚探针逐个打挂：这一节的账读不到，不等于这台机器不健康。"""
    clean = client().json()
    function = SECTIONS[section]

    def _boom():
        raise RuntimeError("ledger probe is down")

    monkeypatch.setattr(pg_store, function, _boom)
    body = client().json()          # client() 里那枚 assert 就是「不许 500」

    assert body[section] == monitoring._unavailable_state("status_probe_failed: RuntimeError"), (
        f"{function} 抛异常时出口没有降级成 unavailable：{body[section]}")
    for other in SECTIONS:
        if other != section:
            assert list(body[other]) == LEDGER_KEYS[other], (
                f"{function} 挂了，连带把 {other} 那一节也问坏了")
    assert body["status"] == clean["status"], "一枚探针抛异常改色了整页判定"
    assert body["problems"] == clean["problems"], "一枚探针抛异常往 problems 里塞了东西"


# ============================================== 判据④ 三枚节不并进 problems，也不改颜色
def test_the_three_sections_never_become_a_health_verdict(client, monkeypatch, dirty_mirror):
    """与 embedding / hot_index / search_shape / model_budget 同一条纪律：读数不是判决。

    空账快照先取，再让两条腿真跑一次（语料腿退回遗留库 + 镜像具名拒写），最后比出口颜色。
    """
    clean = client().json()
    assert clean["vector_corpus"]["source"] == "", "空账快照没取到，下面的对比全是空转"

    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    assert pg_store.switched_corpus() is None, "语料腿得真的退回遗留库，这枚钉子才有对象"
    dirty_mirror()
    dirty = client().json()

    assert dirty["vector_corpus"]["source"] == pg_store.CORPUS_SOURCE_LEGACY
    assert dirty["vector_read"] != clean["vector_read"], "上面几条若永不成立，它们是空钉"
    assert dirty["vector_mirror"] != clean["vector_mirror"], "镜像那本账同样得真的动过"
    assert dirty["status"] == clean["status"], "向量侧的账把一个健康判定改色了"
    assert dirty["problems"] == clean["problems"], "向量侧的账往 problems 里塞了新东西"
    problems = {str(item) for item in dirty["problems"]}
    assert not (problems & VALUE_CODES), (
        f"向量侧的值码被并进了 problems：{sorted(problems & VALUE_CODES)}")


# ================================================= 判据⑤ 零 IO：健康检查不许连任何人
def test_reading_the_outlet_opens_no_connection_and_issues_no_sql(client, monkeypatch,
                                                                  legacy_corpus, dirty_mirror):
    """把 pg_store 里所有会连库的入口换成会抛的桩，出口仍要交出**真数字**。

    退化成 unavailable 同样算红：那说明 _subsystem_state 里真发生了一次连线尝试，只是被它吞了——
    健康轮询于是每隔几秒问一次 PostgreSQL，正是 pg_store.py:121-126 那段注释在防的事。
    """
    dirty_mirror()
    ledgers = _live_ledgers()
    assert any(ledgers[name] != EMPTY_LEDGERS[name] for name in SECTIONS), (
        "空账会让这枚钉子变成空转")

    def _forbidden(name: str):
        def _stub(*args, **kwargs):
            raise AssertionError(f"健康出口不许调用会连库的 {name}")
        return _stub

    for name in ("_connect", "vector_mirror", "read_topk", "read_corpus", "switched_corpus",
                 "search_vectors", "note_read_bypass", "note_read_answered", "_note_corpus"):
        monkeypatch.setattr(pg_store, name, _forbidden(name))
    from app.db import connection as db_connection

    monkeypatch.setattr(db_connection, "open_connection", _forbidden("open_connection"))

    assert _sections(client()) == ledgers, (
        "出口在投影这三本账时动了连线相关的东西，或因此被降级成 unavailable")


def test_reading_the_outlet_five_times_does_not_move_the_books(client, legacy_corpus,
                                                               dirty_mirror):
    """观测不许改变被观测的东西：健康巡检每几秒一次，账不能越读越涨。"""
    dirty_mirror()
    before = _live_ledgers()

    for _ in range(5):
        _sections(client())

    assert _live_ledgers() == before, "反复读出口把向量侧的账读涨了"


_SOCKET_GUARD = textwrap.dedent("""
    import json, socket, sys

    class _NoSockets:
        def __init__(self, *args, **kwargs):
            raise AssertionError("socket opened while reading the pgvector ledgers")

    socket.socket = _NoSockets
    socket.create_connection = _NoSockets
    socket.getaddrinfo = _NoSockets

    from app.rag import pg_store

    functions = ("vector_mirror_diagnostics", "vector_corpus_diagnostics",
                 "vector_read_diagnostics")
    ledgers = {name: getattr(pg_store, name)() for name in functions}
    print(json.dumps({
        "keys": {name[:-len("_diagnostics")]: list(value) for name, value in ledgers.items()},
        "psycopg": "psycopg" in sys.modules,
        "pypdf": "pypdf" in sys.modules,
    }, ensure_ascii=False))
""")


def test_a_cold_process_reads_the_three_ledgers_over_a_dead_socket():
    """判据⑤ 的正身：一台开不了任何 socket 的机器，凭冷导入的进程也能交出这三本账。

    子进程里一个字都不 mock。chromadb 会随 app.rag.retriever 进来——那枚重量先于本单存在
    （出口上的 search_shape 早就 import 同一个 retriever），本单不改它，只钉住 psycopg 与 pypdf
    都不进：pg_store.py:121-126 立的规矩是「只读观测进程不许被拖进解析层」。同一个
    retriever 在 import 期调 load_dotenv 也是既有行为（宿主 .env 进的是这枚子进程自己，
    而 R70 那把闸门管的是 pytest 进程），本单不越界改它——上面的 socket 闸门已经证明这条
    读路径一次连线都没有发生，.env 里的地址也就无处可去。
    """
    result = subprocess.run([sys.executable, "-c", _SOCKET_GUARD], cwd=str(REPO_ROOT),
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"冷导入的只读观测失败了：{result.stderr[-2000:]}"

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["keys"] == {name: LEDGER_KEYS[name] for name in SECTIONS}, (
        f"三本账的字段名在冷进程里与出口钉的不是同一张表：{payload['keys']}")
    assert payload["psycopg"] is False, "只读观测进程被拖进了 psycopg"
    assert payload["pypdf"] is False, "只读观测进程被拖进了 pypdf"
