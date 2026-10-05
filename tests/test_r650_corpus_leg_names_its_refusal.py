# -*- coding: utf-8 -*-
"""R650 的常驻牙 —— 切读态的语料腿：配置性拒答必须具名，连接类失败仍许退回遗留库。

工单判据③ 逐枚落在这一个文件里，全部走行为与源码形状，一格形容词都不留：

  1. 造「双写关 + 切读开」这一档 ⇒ BM25Searcher.build_index() 不许去问遗留向量库，当场抛
     具名拒答，原因码是在册那枚 vector_read_without_dual_write（本单零枚新造码），且连一次
     PostgreSQL 连接都不许开口。
  2. 反向一枚：造「双写开 + PostgreSQL 连不上」⇒ 仍必须退回遗留库并留下绕行账
     （vector_read_diagnostics() 的 last_bypass.reason 是 vector_read_failed、
     vector_corpus_diagnostics() 的 source 是 legacy_chroma）。不许把可用性一并治没。
  3. 出厂那一档（读侧没切）逐字不变：问遗留库、不发 SQL、不抛。
  4. switched_corpus() 的三答契约与「None 不等于库是空的」那格承诺一字未动 —— 本单治的是
     调用方；这一枚是从本席这一侧替 test_r330 / test_r592 那两族在册牙看住它。
  5. 在册量具 r633 现跑：read_corpus 那半格「隐式等 Chroma 回执」必须不再在册；read_topk
     那半格必须照旧在册 —— 它的吞点与答复点都在 app/rag/retriever.py，本席写域外，不顺手治。

两把反证刀（K1/K2）走内存影子：源文从盘上读成字符串、AST 上改一刀、compile + exec 成影子
函数，落盘的 app/** 一个字节都不动；每把刀都先跑正控（同一套影子机械、不动刀），正控不绿
就不算 victim 被咬中。牙一律不拿「此刻盘面脏不脏／盘上字节==HEAD blob」当判据（事故
#96/#107/#113 同族）：形状牙读的是被测模块自己的源码文本，行为牙跑的是真函数，两样都与
git 状态无关。

全程离线：不连 PostgreSQL、不起服务、不开现役 chroma_db 卷、不打模型、不动容器与镜像。
跑法：
    .venv/Scripts/python.exe -m pytest -p no:randomly -q tests/test_r650_corpus_leg_names_its_refusal.py
"""

import ast
import importlib.util
import pathlib
import sys
import types

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retrieval_pipeline as pipeline_module
from app.rag import retriever as rt
from test_r59_chroma_untouched_on_pg_reads import ROWS, _PgDouble

REPO = pathlib.Path(__file__).resolve().parents[1]
PIPELINE_REL = "app/rag/retrieval_pipeline.py"
PG_STORE_REL = "app/rag/pg_store.py"
TOOL_REL = "scripts/r633_dual_write_off_precondition.py"
ROSTER_REL = "tests/test_r625_chroma_write_sites_are_named_one_by_one.py"

#: 工单点名的那一族稳定码：旋钮说这条腿本来就不该问。连接类那一枚必须在族外。
CONFIGURAL = {pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE,
              pg_store.REASON_VECTOR_READ_TABLE_UNRECOGNISED}


def _load(rel, name):
    """按路径装载在册件（只读，不动它一个字节）。先进 sys.modules 再 exec：R625 带
    @dataclass，少了这一步会死在 dataclasses 回查模块字典上（R633 的牙记过同一笔）。"""
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _source(rel):
    return (REPO / rel).read_text(encoding="utf-8")


class _CorpusHandle:
    """遗留集合的取数面：每一次 get() 都记账。传 where 也记下来——本单的取数面必须仍是不带
    where 的全库扫（那枚形状由 tests/test_classification_fail_closed.py 钉着）。"""

    EMPTY = {"ids": [], "documents": [], "metadatas": []}

    def __init__(self, payload=None):
        self.payload = self.EMPTY if payload is None else payload
        self.gets = []

    def get(self, where=None):
        self.gets.append(where)
        return {key: list(value) for key, value in self.payload.items()}


def _legacy_double(payload=None):
    """DocumentRetriever 的哨兵：构造一次记一次，collection 换成会记账的假面。"""
    handle = _CorpusHandle(payload)
    built = []

    class _Stub:
        def __init__(self, *args, **kwargs):
            built.append(args)
            self.collection = handle

    return _Stub, handle, built


def _gear(monkeypatch, *, reads_on, dual_on):
    """把两枚旋钮摆到指认的那一档，并清空两本账（只在进程内，不碰盘也不碰库）。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND",
                        indexing.PGVECTOR_BACKEND if reads_on else indexing.INDEX_BACKEND_DEFAULT)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    if dual_on:
        monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    else:
        monkeypatch.delenv(pg_store.DUAL_WRITE_ENV, raising=False)
    pg_store.reset_vector_corpus_diagnostics()
    pg_store.reset_vector_read_diagnostics()


def _no_connection(monkeypatch):
    """这一档一枚连接都不许开：开了就当场红，而不是数一句日志。"""
    def _refuse(url, factory):
        raise AssertionError("这一档不许向 PostgreSQL 开口")
    monkeypatch.setattr(pg_store, "_connect", _refuse)


def _unreachable(monkeypatch):
    """连接类失败：真连不上（与工单里 test_r59 那枚同形的假件，不复用它的装配台）。"""
    def _refuse(url, factory):
        raise pg_store.VectorReadRejectedError(
            "连不上", reason=pg_store.REASON_VECTOR_READ_FAILED)
    monkeypatch.setattr(pg_store, "_connect", _refuse)

# ------------------------------------------------------- 判据③ 第一枚：配置性拒答必须具名


def test_a_configural_refusal_names_itself_and_never_asks_the_legacy_leg(monkeypatch):
    """双写关 + 切读开：语料腿不改问遗留库，而是当场把这一枚配置矛盾说出去。"""
    _gear(monkeypatch, reads_on=True, dual_on=False)
    stub, handle, built = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub)
    _no_connection(monkeypatch)

    with pytest.raises(pg_store.VectorReadRejectedError) as caught:
        pipeline_module.BM25Searcher().build_index()

    assert caught.value.reason == pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE
    assert pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE in str(caught.value), str(caught.value)
    assert built == [], "这一档还构造了 DocumentRetriever —— 隐式回执没治掉"
    assert handle.gets == [], "这一档还问了遗留库"
    #: switched_corpus() 那两本账照旧（三答契约不许动，本单治的是调用方）
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_LEGACY
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE)


# --------------------------------------------------- 判据③ 反向那一枚：可用性不许一并治没


def test_a_connection_failure_still_buys_the_corpus_from_the_legacy_leg(monkeypatch):
    """双写开 + PostgreSQL 连不上：仍走 R59b 的 availability-first，且绕行账留在名字上。

    这一格不许顺手治：把两种 None 一起拒了，等于让一次数据库故障带走整条关键词腿，
    那比静默降级更难查。
    """
    _gear(monkeypatch, reads_on=True, dual_on=True)
    stub, handle, built = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub)
    _unreachable(monkeypatch)

    pipeline_module.BM25Searcher().build_index()

    assert handle.gets == [None], handle.gets
    assert len(built) == 1, built
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_LEGACY
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FAILED)


def test_the_shipped_gear_builds_from_the_legacy_leg_and_opens_nothing(monkeypatch):
    """出厂那一档（读侧没切）逐字不变：问遗留库、不发 SQL、不抛。"""
    payload = {"ids": ["a.txt_0", "a.txt_1"],
               "documents": ["住宿费标准是每晚500元。", "差旅报销走 OA 流程。"],
               "metadatas": [{"filename": "a.txt", "chunk_index": 0, "classification": 2,
                              "department": "研发中心"},
                             {"filename": "a.txt", "chunk_index": 1, "classification": 2,
                              "department": "研发中心"}]}
    _gear(monkeypatch, reads_on=False, dual_on=False)
    stub, handle, built = _legacy_double(payload)
    monkeypatch.setattr(rt, "DocumentRetriever", stub)
    _no_connection(monkeypatch)

    searcher = pipeline_module.BM25Searcher()
    searcher.build_index()

    assert handle.gets == [None], handle.gets
    assert len(searcher.documents) == 2, searcher.documents
    assert searcher.bm25 is not None, "出厂那一档连语料都不建，就是本单越界了"
    assert pg_store.vector_corpus_diagnostics()["source"] == (
        pg_store.CORPUS_SOURCE_NOT_SWITCHED)


def test_the_production_gear_with_dual_write_on_takes_no_new_branch(monkeypatch):
    """判据④ 的现跑事实：生产那一档（双写 on + 切读 on）一步都不走本单新加的分支。"""
    _gear(monkeypatch, reads_on=True, dual_on=True)
    double = _PgDouble(rows=ROWS)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    stub, handle, built = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub)

    assert pg_store.dual_write_enabled() is True
    assert pg_store.corpus_configural_refusal_reason() == ""

    searcher = pipeline_module.BM25Searcher()
    searcher.build_index()

    assert built == [] and handle.gets == [], "生产档去问了遗留库"
    assert double.corpus_statements(), "语料腿没发 SQL 就不算从 PG 取的"
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_PGVECTOR
    assert len(searcher.documents) == len(ROWS), searcher.documents


# ---------------------------------------------------------------- 三答契约与只读 accessor


def test_switched_corpus_still_gives_its_three_answers(monkeypatch):
    """没切 / 拒答 / 答出行，三答一字未动 —— 本单只治调用方，这一枚替 r330 与 r592 看门。"""
    _gear(monkeypatch, reads_on=False, dual_on=False)
    _no_connection(monkeypatch)
    assert pg_store.switched_corpus() is None
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_NOT_SWITCHED

    _gear(monkeypatch, reads_on=True, dual_on=False)
    _no_connection(monkeypatch)
    assert pg_store.switched_corpus() is None, "拒答这一格改口就是退货：r330 两枚牙以此为前置"
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_LEGACY

    _gear(monkeypatch, reads_on=True, dual_on=True)
    double = _PgDouble(rows=ROWS)
    monkeypatch.setattr(pg_store, "_connect", lambda url, factory: double)
    payload = pg_store.switched_corpus()
    assert payload is not None, "答出行那一格交回 None，就是把 pgvector 读成了没答"
    assert payload["documents"], payload
    assert pg_store.vector_corpus_diagnostics()["source"] == pg_store.CORPUS_SOURCE_PGVECTOR


def test_the_accessor_reads_the_knobs_and_opens_nothing(monkeypatch):
    """新加的只读 accessor：四档各有答复，全过程不开连接、不发 SQL、不写任何一本账。"""
    _no_connection(monkeypatch)
    for reads_on, dual_on, expected in (
            (False, False, ""),
            (False, True, ""),
            (True, False, pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE),
            (True, True, "")):
        _gear(monkeypatch, reads_on=reads_on, dual_on=dual_on)
        before_read = pg_store.vector_read_diagnostics()
        before_corpus = pg_store.vector_corpus_diagnostics()
        assert pg_store.corpus_configural_refusal_reason() == expected, (reads_on, dual_on)
        assert pg_store.vector_read_diagnostics() == before_read, "accessor 动了绕行账"
        assert pg_store.vector_corpus_diagnostics() == before_corpus, "accessor 动了语料账"


def test_the_refusal_family_is_made_of_registered_read_codes():
    """族里每一枚都必须是 pg_store 自己登记的读码：本单零枚新造码，也不许把连接类混进来。"""
    registry = {value for key, value in vars(pg_store).items()
                if key.startswith("REASON_VECTOR_READ_")}
    assert pg_store.CONFIGURAL_READ_REFUSAL_REASONS == CONFIGURAL, (
        pg_store.CONFIGURAL_READ_REFUSAL_REASONS)
    assert set(pg_store.CONFIGURAL_READ_REFUSAL_REASONS) <= registry, (
        "族里出现了没在 pg_store 登记的码")
    assert pg_store.REASON_VECTOR_READ_FAILED not in pg_store.CONFIGURAL_READ_REFUSAL_REASONS, (
        "连接类混进配置族，就会把一次故障读成配置矛盾 —— 判据③ 反向那枚当场失效")

# --------------------------------------------------------------- 源码形状牙（不看 git 状态）


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("源码里找不到函数 " + name)


def test_build_index_holds_no_legacy_receipt_while_the_caller_still_decides():
    """形状：语料腿的遗留回执必须搬出 build_index，而调用方仍必须问那条腿并按族分家。

    为什么钉形状而不只钉行为：量具 r633 的「隐式等 Chroma 回执」是从 AST 现取的，两跳派生
    （吞点 → 该调用方的遗留读）。回执留在 build_index 里，判据① 就还是红的；把它整段删掉
    而让可用性那一格没人接，判据③ 的反向那枚又红。两头同时成立只有一种形状：调用方只做
    判定，遗留读单独一枚具名方法。
    """
    tree = ast.parse(_source(PIPELINE_REL))
    build = _function(tree, "build_index")
    helper = _function(tree, "_legacy_corpus")
    assert ".collection." not in ast.unparse(build), (
        "build_index 里还留着遗留集合的读调用 —— 量具仍会读到一条等待")
    assert ".collection.get()" in ast.unparse(helper), helper.name
    called = {ast.unparse(node.func) for node in ast.walk(build) if isinstance(node, ast.Call)}
    assert "pg_store.switched_corpus" in called, called
    assert "pg_store.corpus_configural_refusal_reason" in called, called
    assert "self._legacy_corpus" in called, called
    assert any(isinstance(node, ast.Raise) for node in ast.walk(build)), (
        "具名失败不在调用方 —— 判据① 红")


def test_the_shipped_gauge_no_longer_names_the_corpus_leg_as_a_chroma_waiter():
    """判据① 的常驻化：在册量具现跑，read_corpus 那半格必须不在，read_topk 那半格必须在。

    量具与名册本席一字未动（禁区），这里只按在册调用面把派生取回来。
    """
    tool = _load(TOOL_REL, "r633_tool_read_by_r650")
    roster = _load(ROSTER_REL, "r625_roster_read_by_r650")
    gated = tool.switch_gated_legs(roster, _source(PG_STORE_REL))
    legs = {row["leg"] for row in gated["legs"]}
    waiters = tool.legacy_receipt_waiters(tool.app_sources(), gated["legs"])["waiters"]
    pairs = {(row["leg"], row["refusal_swallowed_by"], row["answered_by"]) for row in waiters}

    assert "read_corpus" in legs, (
        "腿必须还在册上：本单治的是吞它那一层的下游，不是把读腿拆了")
    assert not [row for row in waiters if row["leg"] == "read_corpus"], (
        "语料腿还在等遗留库回执：" + repr(pairs))
    assert ("read_topk", "app/rag/retriever.py::_pgvector_hits",
            "app/rag/retriever.py::search") in pairs, (
        "read_topk 那一半的吞点与答复点都在 app/rag/retriever.py，本单写域外，必须照旧被点名")


# --------------------------------------------------------------------- 两把反证刀（内存影子）


def _shadow(module, rel, name, mutate=None):
    """把一枚函数在内存里改一刀、exec 成影子；落盘的 app/** 一个字节都不动。"""
    tree = ast.parse(_source(rel))
    target = _function(tree, name)
    before = ast.unparse(target)
    if mutate is not None:
        mutate(target)
        if ast.unparse(target) == before:
            raise AssertionError("这把刀没磨到东西：" + name)
    ast.fix_missing_locations(tree)
    namespace = dict(vars(module))
    exec(compile(ast.Module(body=[target], type_ignores=[]), "<shadow " + rel + ">", "exec"),
         namespace)
    return namespace[name]


def _cut_the_named_refusal(function):
    """刀一：摘掉调用方那枚具名抛（就地换成 pass，其余一字不动）。"""
    hits = [item for item in ast.walk(function) if isinstance(item, ast.Raise)]
    if len(hits) != 1:
        raise AssertionError("build_index 里的具名抛不是恰好一枚，这把刀不适用：" + str(len(hits)))
    for parent in ast.walk(function):
        for _field, value in ast.iter_fields(parent):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if item is hits[0]:
                        value[index] = ast.Pass()
                        return
    raise AssertionError("那枚抛不在 build_index 的语句表里，刀没磨上")


def _blind_the_accessor(function):
    """刀二：让 accessor 认不出配置那一档（dual_write_enabled 那枚判定改成恒假）。"""
    hits = [node for node in ast.walk(function)
            if isinstance(node, ast.If) and "dual_write_enabled" in ast.unparse(node.test)]
    if len(hits) != 1:
        raise AssertionError("accessor 里那枚旋钮判定不是恰好一枚：" + str(len(hits)))
    hits[0].test = ast.Constant(value=False)


def test_k1_dropping_the_named_refusal_brings_the_silent_receipt_back(monkeypatch):
    """K1 摘掉具名抛 ⇒ 静默回执必须复现；同一套影子机械的正控（不动刀）必须仍绿。"""
    control = _shadow(pipeline_module, PIPELINE_REL, "build_index")
    knifed = _shadow(pipeline_module, PIPELINE_REL, "build_index", _cut_the_named_refusal)

    for label, fn, victim in (("正控", control, False), ("K1 摘刀", knifed, True)):
        _gear(monkeypatch, reads_on=True, dual_on=False)
        stub, handle, _built = _legacy_double()
        monkeypatch.setattr(rt, "DocumentRetriever", stub)
        _no_connection(monkeypatch)
        searcher = pipeline_module.BM25Searcher()
        searcher.build_index = types.MethodType(fn, searcher)
        if victim:
            searcher.build_index()
            assert handle.gets == [None], label + "：摘刀之后旧病复现，遗留回执又被打开了"
        else:
            with pytest.raises(pg_store.VectorReadRejectedError):
                searcher.build_index()
            assert handle.gets == [], label + "：正控就不该去问遗留库"


def test_k2_an_accessor_blind_to_the_gear_redds_only_the_config_family(monkeypatch):
    """K2 让 accessor 认不出配置档 ⇒ 只有配置那一格退回静默，连接那一格必须照旧绿。

    两族分家不是同一根线：这一枚刀砍在判定上，反向那枚判据仍成立，才叫分开治。
    """
    control = _shadow(pg_store, PG_STORE_REL, "corpus_configural_refusal_reason")
    blind = _shadow(pg_store, PG_STORE_REL, "corpus_configural_refusal_reason",
                    _blind_the_accessor)
    #: 正控与刀各自的档位返回值都由下面的行为现取，这里不写永真断言

    monkeypatch.setattr(pg_store, "corpus_configural_refusal_reason", control)
    _gear(monkeypatch, reads_on=True, dual_on=False)
    stub, handle, _built = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub)
    _no_connection(monkeypatch)
    with pytest.raises(pg_store.VectorReadRejectedError):
        pipeline_module.BM25Searcher().build_index()
    assert handle.gets == [], "正控就不该去问遗留库"

    monkeypatch.setattr(pg_store, "corpus_configural_refusal_reason", blind)
    _gear(monkeypatch, reads_on=True, dual_on=False)
    stub2, handle2, _built2 = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub2)
    _no_connection(monkeypatch)
    pipeline_module.BM25Searcher().build_index()
    assert handle2.gets == [None], "K2 之后配置那一档又去问遗留库了（victim 成立）"

    _gear(monkeypatch, reads_on=True, dual_on=True)
    stub3, handle3, _built3 = _legacy_double()
    monkeypatch.setattr(rt, "DocumentRetriever", stub3)
    _unreachable(monkeypatch)
    pipeline_module.BM25Searcher().build_index()
    assert handle3.gets == [None], "连接类那一格被这枚刀误伤"
    assert pg_store.vector_read_diagnostics()["last_bypass"]["reason"] == (
        pg_store.REASON_VECTOR_READ_FAILED)
