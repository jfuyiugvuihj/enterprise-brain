# -*- coding: utf-8 -*-
"""R659 判据① 的常驻牙 —— 切读态语义腿的配置性拒答：具名抛，不改问遗留目录。

对着的病（本席在基点 96763c4 现读，不是转述）：app/rag/retriever.py::_pgvector_hits 那句
except 把 pg_store.read_topk 按 REASON_VECTOR_READ_WITHOUT_DUAL_WRITE 发出的**配置性拒答**
连同连接类失败一起吞成"这一腿没答"，答复点 search() 于是落到 self.collection.query() ——
在册量具 scripts/r633_dual_write_off_precondition.py 把这一形点名为 read_leg_waits_for_chroma_receipt，
R650 治掉语料腿那一半之后，waiters 只剩这一枚。本单治的就是它。

形状与语料腿那一半（R650）同一条：判定只看"旋钮说这条腿本来就不该问"那一族，族码用在册的
pg_store.CONFIGURAL_READ_REFUSAL_REASONS，本文件所在这一族零枚新造错误码；availability-first
（连不上 / 镜像不可用 / 过滤器翻译不出来）一字未动 —— 那一格还是退回遗留腿并留下绕行账，
把它一并治掉比静默降级更难查（R650 判据③ 反向那枚同一条理由）。

牙分三面，全部可失败，没有一格拿形容词交差：

  1. 行为面：切读开 + 双写关 ⇒ DocumentRetriever.search() 抛具名拒答、reason 是在册码、
     遗留 collection 一次都不许被问到（哨兵一问就抛）、绕行账点名那枚码与"不改问遗留目录"、
     search_shape 不许凭空多记一枚假答复者。
  2. 反向面：切读开 + 双写开 + 连不上 ⇒ 仍由遗留腿答复且形状记 chroma（不许把可用性一并治没）；
     出厂那一档（读侧没切）逐字不变：不发 SQL、不抛、_pgvector_hits 照旧交回 None。
  3. 派生面：在册量具现跑 —— read_topk 必须**仍在拒答腿上**（腿没被拆），waiters 必须归 0，
     read_leg_waits_for_chroma_receipt 这一族必须当场从发现面消失；K1 摘掉那枚具名抛之后
     它必须原样复现，且复现的 subject 逐枚点名就是 read_topk。

两把反证刀（照 tests/test_r545_counter_evidence_teeth.py 48cc956 与
tests/test_r655_no_stale_fact_teeth.py 193f65e 的两形）：
  S1 形状刀 —— 落在本件自己的取材口上：把盘上读回的 retriever 源文里那枚具名抛换成 pass，
     victim = test_the_handler_raises_for_the_registered_family_only（形状闸读的必须是同一枚
     取材口，否则它就是空钉）。
  K1 产品刀 —— 同一刀落在行为面与派生面两端：影子函数（内存 AST，exec 成另一枚方法）里摘掉
     具名抛 ⇒ 遗留 collection 真的又被问了、量具的 waiters 真的又点名 read_topk。
  两把各配一枚正控：同一套机械、edits=()，正控必须先绿，红才算被咬中。
落盘的 app/** 一个字节都不动。牙一律不看盘面状态（无 porcelain / rev-parse / numstat /
ls-files / MERGE_HEAD，在册事故 #96／#107／#113 同族）：形状牙读被测模块自己的源码文本，
行为牙跑真函数，派生牙跑在册量具的派生函数，三者都与 git 状态无关。

全程离线：不连 PostgreSQL、不起服务、不开现役 chroma_db 卷、不打模型、不动容器与镜像、不跑全量门。
跑法：
    .venv/Scripts/python.exe -B -m pytest -p no:randomly -q tests/test_r659_topk_leg_names_its_refusal.py
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys
import types

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt

from test_r59b_pg_read_switch import QUERY, WHERE_ADMIN, _NeverAsked

REPO = pathlib.Path(__file__).resolve().parents[1]
RETRIEVER_REL = "app/rag/retriever.py"
PG_STORE_REL = "app/rag/pg_store.py"
TOOL_REL = "scripts/r633_dual_write_off_precondition.py"
ROSTER_REL = "tests/test_r625_chroma_write_sites_are_named_one_by_one.py"

#: 工单硬规：族码复用 R650 已在册的那一本，本单不新造错误码。
CONFIGURAL = frozenset({pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE,
                        pg_store.REASON_VECTOR_READ_TABLE_UNRECOGNISED})
#: 吞点与答复点的在册名字（本单改的是吞点，答复点的遗留读调用面必须还在，只是这一档走不到它）。
SWALLOWER = "_pgvector_hits"
ANSWERER = "search"
WAITER_CODE = "read_leg_waits_for_chroma_receipt"


def _load(rel: str, name: str):
    """按路径装载在册件（只读）。先进 sys.modules 再 exec：R625 带 dataclass，
    少了这一步会死在 dataclasses 回查模块字典上（R633 与 R650 都记过同一笔）。"""
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


#: 本件唯一的取材口：形状刀换的就是它的返回值（照 R655 的 shape 模式），仓内字节一个都不动。
def _source(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("源码里找不到函数 " + name + " —— 刀先磨不利，别拿去砍钉")


def _configural_guard(func: ast.FunctionDef) -> ast.If:
    """找出那枚"按族分家"的判定。它必须恰好一枚：两枚就是抄了第二份判据，零枚就是牙没了。"""
    hits = [node for node in ast.walk(func)
            if isinstance(node, ast.If)
            and "CONFIGURAL_READ_REFUSAL_REASONS" in ast.unparse(node.test)]
    if len(hits) != 1:
        raise AssertionError("_pgvector_hits 里按族分家的判定不是恰好一枚（命中 %d 枚）" % len(hits))
    return hits[0]


def _strip_the_named_raise(func: ast.FunctionDef) -> None:
    """刀口：把族判定那一支换成 pass（具名抛摘掉，其余一字不动）—— 病形：静默改问遗留库。"""
    guard = _configural_guard(func)
    guard.body = [ast.Pass()]
    ast.fix_missing_locations(func)


def _shadow_hits(mutate=None):
    """把 _pgvector_hits 在内存里改一刀、exec 成影子函数；落盘的 retriever.py 一个字节不动。"""
    tree = ast.parse(_source(RETRIEVER_REL))
    target = _function(tree, SWALLOWER)
    before = ast.unparse(target)
    if mutate is not None:
        mutate(target)
        if ast.unparse(target) == before:
            raise AssertionError("这把刀没磨到东西：" + SWALLOWER)
    namespace = dict(vars(rt))
    exec(compile(ast.Module(body=[target], type_ignores=[]),
                "<r659 shadow " + RETRIEVER_REL + ">", "exec"), namespace)
    return namespace[SWALLOWER]


# ------------------------------------------------------------------------ 档位与假腿


def _gear(monkeypatch, *, reads_on: bool, dual_on: bool) -> None:
    """把两枚旋钮摆到指认的那一档，并清空相关账本。只在进程内，不碰盘也不碰库。"""
    monkeypatch.setattr(indexing, "INDEX_BACKEND",
                        indexing.PGVECTOR_BACKEND if reads_on else indexing.INDEX_BACKEND_DEFAULT)
    monkeypatch.delenv(indexing.INDEX_BACKEND_ENV, raising=False)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on" if dual_on else "off")
    monkeypatch.setenv(rt.ACTIVITY_PRIOR_ENV, "off")
    pg_store.reset_vector_read_diagnostics()
    pg_store.reset_vector_corpus_diagnostics()
    rt.reset_search_shape()


def _no_connection(monkeypatch):
    """这一档一枚连接都不许开：开了就当场红，而不是数一句日志。"""
    def _refuse(url, factory):
        raise AssertionError("这一档不许向 PostgreSQL 开口")

    monkeypatch.setattr(pg_store, "_connect", _refuse)


def _refuse_connection(monkeypatch, reason: str):
    """可用性那一族：真连不上（与 R59b / R650 同形的假件）。"""
    def _refuse(url, factory):
        raise pg_store.VectorReadRejectedError("连不上", reason=reason)

    monkeypatch.setattr(pg_store, "_connect", _refuse)


class _LegacyAnswers:
    """遗留目录的读面：每一次 query() 都记下来，并交回一份可以直接用的命中。"""

    name = "legacy_chroma"

    def __init__(self):
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"ids": [["c.txt_0"]], "documents": [["正文"]],
                "metadatas": [[{"filename": "c.txt", "chunk_index": 0,
                                "classification": 1, "department": "研发中心"}]],
                "distances": [[0.5]]}


def _retriever(tmp_path, monkeypatch, *, reads_on: bool, dual_on: bool):
    """造一台真 DocumentRetriever（假腿、假 embedding），并按在册装配台把 chroma 目录放仓外。"""
    _gear(monkeypatch, reads_on=reads_on, dual_on=dual_on)
    instance = rt.DocumentRetriever(str(tmp_path / "chroma"))
    monkeypatch.setattr(instance.embedding, "embed_query", lambda text: list(QUERY))
    return instance


# ------------------------------------------------------------------ 一 · 行为面：配置性拒答具名抛


def test_a_configural_refusal_names_itself_and_never_asks_the_legacy_leg(tmp_path, monkeypatch):
    """切读开 + 双写关：语义腿当场具名抛，遗留目录一次都不许被问。"""
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=False)
    instance.collection = _NeverAsked()      # 问一次就抛 AssertionError，替"没被问"作证
    _no_connection(monkeypatch)              # 这一档连 PostgreSQL 都不该开口

    with pytest.raises(pg_store.VectorReadRejectedError) as caught:
        instance.search("住宿费标准", k=5, where=WHERE_ADMIN)

    assert caught.value.reason == pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE
    #: 句面上点名的那枚旋钮就是这一档的成因（正文由 pg_store 写，本单不抄第二份措辞）
    assert pg_store.DUAL_WRITE_ENV in str(caught.value), str(caught.value)
    #: 抛出去的是 pg_store 那一族的具名异常，不是 retriever 自己新造的第二套类型
    assert type(caught.value) is pg_store.VectorReadRejectedError


def test_the_ledger_names_the_refusal_and_that_the_caller_did_not_rehome(tmp_path, monkeypatch):
    """绕行账那一格：原因码点名配置矛盾，detail 点名"语义腿不改问遗留目录"。

    这是判据③那一格的行为面：账本里看得见"这一腿拒答"与"调用方没有改问遗留库"两件事，
    用的还是既有那本 vector_read_diagnostics（R330 口径：出口只许投影既有读数，不许新开账）。
    """
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=False)
    instance.collection = _NeverAsked()
    _no_connection(monkeypatch)

    with pytest.raises(pg_store.VectorReadRejectedError):
        instance.search("住宿费标准", k=5, where=WHERE_ADMIN)

    reading = pg_store.vector_read_diagnostics()
    assert reading["bypasses"] == {pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE: 1}, reading
    assert reading["answered"] == 0, reading
    assert reading["last_bypass"]["reason"] == pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE
    assert "不改问遗留目录" in reading["last_bypass"]["detail"], reading["last_bypass"]


def test_the_refused_question_records_no_fake_answerer(tmp_path, monkeypatch):
    """这一问没有答复者，就不许在形状账上凭空记一枚：search_shape 一格都不许多。

    反面写法是把拒答记成 answered_by=chroma 再抛 —— 那正是本单要治的形状换了个地方住。
    """
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=False)
    instance.collection = _NeverAsked()
    _no_connection(monkeypatch)
    before = rt.search_shape_diagnostics()

    with pytest.raises(pg_store.VectorReadRejectedError):
        instance.search("住宿费标准", k=5, where=WHERE_ADMIN)

    assert rt.search_shape_diagnostics() == before, "拒答那一问被记上了一个答复者"


# ---------------------------------------------------------- 二 · 反向面：可用性与出厂档一字未动


def test_an_availability_refusal_still_buys_the_answer_from_the_legacy_leg(tmp_path, monkeypatch):
    """切读开 + 双写开 + 连不上：availability-first 一字未动，仍由遗留腿答复。

    这一格不许顺手治：把连接类一起拒了，等于让一次数据库故障带走整条语义腿，
    比静默降级更难查（与 R650 判据③ 反向那枚同一条理由，语料腿已经钉过一面）。
    """
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=True)
    legacy = _LegacyAnswers()
    instance.collection = legacy
    _refuse_connection(monkeypatch, pg_store.REASON_VECTOR_READ_FAILED)

    hits = instance.search("住宿费标准", k=5, where=WHERE_ADMIN)

    assert [item["source"] for item in hits] == ["c.txt"], hits
    assert len(legacy.queries) == 1, legacy.queries
    assert rt.search_shape_diagnostics()["last"]["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    reading = pg_store.vector_read_diagnostics()
    assert reading["last_bypass"]["reason"] == pg_store.REASON_VECTOR_READ_FAILED
    assert "不改问遗留目录" not in reading["last_bypass"]["detail"], reading["last_bypass"]


def test_the_untranslatable_filter_still_degrades_and_does_not_raise(tmp_path, monkeypatch):
    """族外那一枚码（过滤器翻译不出来）不许被本单顺手划进配置族：照旧退回遗留腿。

    这一格钉的是"按族判"而不是"按名字判"：族里多一枚或少一枚，行为面立刻分叉。
    """
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=True)
    legacy = _LegacyAnswers()
    instance.collection = legacy
    _refuse_connection(monkeypatch, pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE)

    hits = instance.search("住宿费标准", k=5, where=WHERE_ADMIN)

    assert hits and rt.search_shape_diagnostics()["last"]["answered_by"] == (
        rt.RETRIEVAL_SERVER_CHROMA)


def test_the_shipped_gear_still_returns_none_and_opens_nothing(tmp_path, monkeypatch):
    """出厂那一档（读侧没切）逐字不变：不发 SQL、不连库、不抛，_pgvector_hits 照旧交回 None。"""
    instance = _retriever(tmp_path, monkeypatch, reads_on=False, dual_on=False)
    _no_connection(monkeypatch)

    assert indexing.pgvector_reads_enabled() is False
    assert instance._pgvector_hits(list(QUERY), 5, WHERE_ADMIN, query="住宿费") is None
    assert pg_store.vector_read_diagnostics()["bypasses"] == {}, pg_store.vector_read_diagnostics()
    assert rt.search_shape_diagnostics()["totals"] == {}


def test_the_refusal_family_is_the_registered_one_with_no_new_code():
    """判据① 的卫生面：本单零枚新造错误码 —— 族就是 R650 那一本，一枚不多一枚不少。"""
    registry = {value for key, value in vars(pg_store).items()
                if key.startswith("REASON_VECTOR_READ_")}
    assert pg_store.CONFIGURAL_READ_REFUSAL_REASONS == CONFIGURAL, (
        pg_store.CONFIGURAL_READ_REFUSAL_REASONS)
    assert set(pg_store.CONFIGURAL_READ_REFUSAL_REASONS) <= registry, (
        "族里出现了没在 pg_store 登记的码")
    for outside in (pg_store.REASON_VECTOR_READ_FAILED,
                    pg_store.REASON_VECTOR_READ_FILTER_UNTRANSLATABLE,
                    pg_store.REASON_VECTOR_READ_OPERATOR_UNKNOWN):
        assert outside not in pg_store.CONFIGURAL_READ_REFUSAL_REASONS, outside


# ------------------------------------------------------------------ 三 · 形状面（读源码文本）


def test_the_handler_raises_for_the_registered_family_only():
    """形状闸：吞点里那枚族判定必须在位，并且族判定那一支里必须有 raise。

    为什么钉形状而不只钉行为：在册量具的"隐式等 Chroma 回执"整面从 AST 现取（吞掉拒答的那句
    except 里有没有 raise 就是它的判据）。写成永真断言或写死行号，这一格就成了第二枚过期事实。
    """
    func = _function(ast.parse(_source(RETRIEVER_REL)), SWALLOWER)
    guard = _configural_guard(func)
    assert any(isinstance(node, ast.Raise) for node in ast.walk(guard)), (
        "按族分家那一支里没有 raise —— 拒答又被吞成「这一腿没答」")
    body = " ".join(ast.unparse(node) for node in guard.body)
    assert "return None" not in body, "族判定那一支里还留着交回 None：" + body
    answerer = _function(ast.parse(_source(RETRIEVER_REL)), ANSWERER)
    assert ".collection.query(" in ast.unparse(answerer), (
        "答复点的遗留读调用面被摘掉了 —— 可用性那一格从此没人接")
    assert "self._pgvector_hits(" in ast.unparse(answerer), ANSWERER


def test_the_branch_reads_the_family_from_pg_store_not_a_private_copy():
    """本域不许抄第二份族名册：判定读的是 pg_store 那一本，句面上没有码字面量。"""
    func = _function(ast.parse(_source(RETRIEVER_REL)), SWALLOWER)
    test_text = ast.unparse(_configural_guard(func).test)
    assert "pg_store.CONFIGURAL_READ_REFUSAL_REASONS" in test_text, test_text
    #: 族里每一枚码都不许以字面量出现在吞点里（ast.unparse 会把引号换成单引号，
    #: 所以判据只拿 AST 的常量面判，不拿文本子串判 —— 子串判是个永假的钉）
    constants = {item.value for item in ast.walk(func)
                 if isinstance(item, ast.Constant) and isinstance(item.value, str)}
    borrowed = sorted(constants & set(CONFIGURAL))
    assert not borrowed, "吞点里抄了稳定码字面量：" + repr(borrowed)


# ------------------------------------------------------------------ 四 · 派生面（在册量具现跑）


def _reading(tool, roster, *, retriever_text=None, pg_store_text=None):
    """装配静态三面：换掉的源文只进内存，写点从对应副本现取（派生机械全用在册量具自己的函数）。"""
    sources = tool.app_sources()
    mutated = {}
    if retriever_text is not None:
        mutated[RETRIEVER_REL] = retriever_text
    if pg_store_text is not None:
        mutated[PG_STORE_REL] = pg_store_text
    sources.update(mutated)
    if mutated:
        sites = [item for item in roster.app_write_sites() if item.path not in mutated]
        for rel in sorted(mutated):
            sites = list(sites) + list(roster.chroma_write_sites(sources[rel], rel))
        sites = tuple(sites)
    else:
        sites = roster.app_write_sites()
    pg_text = sources[PG_STORE_REL]
    retriever_src = sources[RETRIEVER_REL]
    gated = tool.switch_gated_legs(roster, pg_text)
    legs = [row["leg"] for row in gated["legs"]]
    waiters = tool.legacy_receipt_waiters(sources, gated["legs"])
    findings = tool.off_state_findings(
        tool.predicate_terms(roster, retriever_src),
        tool.write_site_face(roster, sites, retriever_src),
        tool.predicate_dependent_questions(roster, retriever_src, legs),
        waiters, None)
    return {"legs": legs, "waiters": waiters, "findings": findings,
            "codes": {item["code"] for item in findings},
            "swallowers": {item["function"] for item in waiters["swallows"]}}


def _subjects(readings, code):
    return {item["subject"] for item in readings["findings"] if item["code"] == code}


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL_REL, "r633_tool_read_by_r659")


@pytest.fixture(scope="module")
def roster():
    sys.path.insert(0, str(REPO / "tests"))
    return _load(ROSTER_REL, "r625_roster_read_by_r659")


def test_the_registered_gauge_now_reads_no_chroma_waiter(tool, roster):
    """判据① 的归 0：两半都治完 —— waiters 空，而 read_topk 这枚腿必须还在拒答名册上。

    少了后半句，"归 0"就可能是把腿整个拆掉的假绿（R650 §5 同一笔账）。
    """
    reading = _reading(tool, roster)
    assert "read_topk" in reading["legs"], reading["legs"]
    assert reading["waiters"]["waiters"] == [], reading["waiters"]
    assert WAITER_CODE not in reading["codes"], reading["findings"]
    #: 吞点仍在册（switched_corpus 那一枚可用性吞点本单不治，它也不在 waiters 里）
    assert reading["swallowers"] == {"switched_corpus"}, reading["waiters"]["swallows"]


def test_the_other_three_families_are_still_named(tool, roster):
    """归 0 只归了这一族：另外三族一枚都不许跟着消失，否则是量具坏了不是产品落地。"""
    reading = _reading(tool, roster)
    for code in ("chroma_write_gate_reopens", "delete_set_blind_to_pg_only_rows",
                 "question_rehomes_to_legacy_store"):
        assert code in reading["codes"], (code, reading["findings"])
        assert _subjects(reading, code), code


# --------------------------------------------------------------- 五 · 两把刀（各配一枚正控）


def _bite_shape_knife(monkeypatch) -> bool:
    """S1 形状刀：把取材口换成摘掉具名抛的副本，形状闸必须红。"""
    tree = ast.parse(_source(RETRIEVER_REL))
    _strip_the_named_raise(_function(tree, SWALLOWER))
    mutated = ast.unparse(tree)
    assert mutated != _source(RETRIEVER_REL), "刀口没落在源文上"
    monkeypatch.setattr(sys.modules[__name__], "_source",
                        lambda rel: mutated if rel == RETRIEVER_REL else _original_source(rel))
    try:
        test_the_handler_raises_for_the_registered_family_only()
    except BaseException:          # noqa: BLE001 - Failed: DID NOT RAISE 继承的是 BaseException
        return True
    return False


_original_source = _source


def test_s1_shape_control_is_green_before_the_knife():
    """S1 的正控：同一套取材机械、刀口不落，形状闸必须先绿。"""
    test_the_handler_raises_for_the_registered_family_only()
    test_the_branch_reads_the_family_from_pg_store_not_a_private_copy()


def test_s1_shape_knife_redds_the_shape_gate(monkeypatch):
    assert _bite_shape_knife(monkeypatch), (
        "S1 没咬中形状闸：那一格里其实没有牙")


def test_k1_product_control_still_refuses_the_legacy_leg(tmp_path, monkeypatch):
    """K1 的正控：不动刀的影子（同一套 exec 机械）—— 抛、遗留腿零问、waiters 归 0。"""
    shadow = _shadow_hits()
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=False)
    instance.collection = _NeverAsked()
    _no_connection(monkeypatch)
    monkeypatch.setattr(instance, SWALLOWER, types.MethodType(shadow, instance))

    with pytest.raises(pg_store.VectorReadRejectedError):
        instance.search("住宿费标准", k=5, where=WHERE_ADMIN)
    assert pg_store.vector_read_diagnostics()["bypasses"] == {
        pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE: 1}


def test_k1_dropping_the_named_raise_brings_the_silent_receipt_back(tmp_path, monkeypatch,
                                                                    tool, roster):
    """K1 产品刀：摘掉那枚具名抛 ⇒ 病形两端同时复现 —— 遗留腿真的被问了，量具真的又点名它。"""
    shadow = _shadow_hits(_strip_the_named_raise)
    instance = _retriever(tmp_path, monkeypatch, reads_on=True, dual_on=False)
    legacy = _LegacyAnswers()
    instance.collection = legacy
    _no_connection(monkeypatch)
    monkeypatch.setattr(instance, SWALLOWER, types.MethodType(shadow, instance))

    hits = instance.search("住宿费标准", k=5, where=WHERE_ADMIN)
    assert hits and len(legacy.queries) == 1, "摘刀之后遗留腿还是没被问：这枚刀没磨到东西"
    assert pg_store.vector_read_diagnostics()["bypasses"] == {
        pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE: 1}, "静默降级不留账，本单就不是它"

    tree = ast.parse(_source(RETRIEVER_REL))
    _strip_the_named_raise(_function(tree, SWALLOWER))
    reading = _reading(tool, roster, retriever_text=ast.unparse(tree))
    assert WAITER_CODE in reading["codes"], reading["findings"]
    assert _subjects(reading, WAITER_CODE) == {"read_topk"}, reading["findings"]
    triple = {(row["leg"], row["refusal_swallowed_by"], row["answered_by"])
              for row in reading["waiters"]["waiters"]}
    assert ("read_topk", "app/rag/retriever.py::_pgvector_hits",
            "app/rag/retriever.py::search") in triple, triple


def test_the_shadow_machinery_leaves_the_repo_untouched(tmp_path):
    """影子只落内存：跑完之后 retriever.py 与 pg_store.py 的文本与进来时逐字相等。"""
    before = {rel: _source(rel) for rel in (RETRIEVER_REL, PG_STORE_REL)}
    _shadow_hits(_strip_the_named_raise)
    _shadow_hits()
    assert {rel: _source(rel) for rel in (RETRIEVER_REL, PG_STORE_REL)} == before, "影子把仓改了"
    assert not list((REPO / "app" / "rag").glob("*shadow*")), "影子落进仓内"
