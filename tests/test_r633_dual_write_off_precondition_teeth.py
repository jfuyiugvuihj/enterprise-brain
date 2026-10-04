# -*- coding: utf-8 -*-
"""R633 的牙 —— 「关掉双写会掉什么」这把量具自己必须会红，读数才不算空话。

全程离线：不连 PostgreSQL、不起服务、不开现役 `chroma_db` 卷、不打模型、不发一条写语句。
连库那一层用注入的假件走（这正是本单要交的"可注入"），真库那一遍归总控开窗。
所有"改码"都发生在**内存里的源码副本**上，落盘的 app/** 一个字节都不动（照 R625 的口径）。

在册那两枚件各钉过什么，本文件刻意不重复：
  * `test_r60_predicate_terms_and_leg_parity`：三枚条件**还写在判定那一段里**（静态点名）
    + `dual="off"` 那一档的写删行为。它读的是真盘上的 `app/rag/retriever.py`，结构上量不到
    "派生随不随码走"——把条件摘掉之后，一台量具还在不在报这一格，它答不了。
  * `test_r625_chroma_write_sites_are_named_one_by_one`：写点的身份/闸门/id 来源逐枚点名。
    它判的是"停写态里不许有没闸门的写点"，不判"这枚旋钮一关，哪一枚重新接行"。
本文件补的是这两格之外、且只有 R633 这问句才需要的形状：

  1. 判定少一枚条件 ⇒ 量具必须红，并且**点名少的是哪一枚**（三形：摘 `dual_write_enabled`
     那枚合取、摘 `pgvector_writes_are_primary` 那枚合取、摘顶部 `stores_vectors` 早退）。
     刀全砍在源码副本上，真盘不动。
  2. 写点名册与在册名册件对不上 ⇒ 量具按 `roster_cross_check_failed` 收，走退出码 2，
     不当绿；身份撞名（枚数不变那一形）也要红——那是 R625 判据⑥的同族，本量具自己再钉一遍。
  3. "关掉双写仍有代码路径隐式等 Chroma 回执" 这一形**有牙**：
     拒答面与回执面都从 AST 现取，所以两把反向刀都得改读数——
     把 `read_topk` 的开关拒答换成别的码 ⇒ 这条腿与它的回执一起从派生里消失；
     把 `_pgvector_hits` 的 `except` 改成原样上抛 ⇒ 腿还在、回执消失（拒答不再被吞）。
     再加两枚现跑：旋钮关着时语义答复真的由 Chroma 给出（bypass 原因码点名），
     以及切换期写的行在 off 态**删不掉、名单里也没有**，同一形状在 dual=on 那一档删得掉。
  4. 语料面只走注入的连接与快照：非沙盒库名且没给开窗责任人 ⇒ 连一次都不许连就按 2 号收；
     会话不是 READ ONLY ⇒ 按 2 号收；`--chroma-dir` 指现役卷 ⇒ 复用 r626 那枚判据按 2 号收。
  5. 退出码语义：1 号只允许由"检出发现"发出，3 号是"语料面未取数"而不是绿，产物落仓外。
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
import tempfile
import types

import pytest

from app.rag import indexing
from app.rag import pg_store
from app.rag import retriever as rt

#: 在册的读路装配台（`DocumentRetriever(str(tmp_path / "chroma"))` 那一套）与写删装配台。
#: 复用它们，不为 R633 再造一套平行假腿——同族病记过两次。
from test_r59b_pg_read_switch import _build_retriever
from test_r60_write_path_unique_under_pgvector import (
    LegacyHandle,
    PgTable,
    _assemble,
    pg_row,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL_PATH = REPO / "scripts" / "r633_dual_write_off_precondition.py"
ROSTER_PATH = REPO / "tests" / "test_r625_chroma_write_sites_are_named_one_by_one.py"
RECALL_PATH = REPO / "scripts" / "compare_vector_recall.py"
PROBE_PATH = REPO / "scripts" / "r626_legacy_engine_silent_empty_probe.py"
RETRIEVER_PY = REPO / "app" / "rag" / "retriever.py"
PG_STORE_PY = REPO / "app" / "rag" / "pg_store.py"
RETRIEVER_REL = "app/rag/retriever.py"
PG_STORE_REL = "app/rag/pg_store.py"


def _load(path, name):
    """按路径装载在册件。先进 sys.modules 再 exec：带 @dataclass 的件（R625）少了这一步
    会死在 dataclasses 回查模块字典上（本单第一次跑就撞过）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


@pytest.fixture(scope="module")
def tool():
    return _load(TOOL_PATH, "r633_tool_under_test")


@pytest.fixture(scope="module")
def roster():
    sys.path.insert(0, str(REPO / "tests"))
    return _load(ROSTER_PATH, "r633_roster_under_test")


@pytest.fixture(scope="module")
def retriever_source():
    return RETRIEVER_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pg_store_source():
    return PG_STORE_PY.read_text(encoding="utf-8")


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("源码副本里找不到函数 " + name + " —— 刀先磨不利，别拿去砍钉")


def _predicate_conjunction(tree):
    """取判定那一句的合取本体；形状变了这枚刀就不合格，宁可红在刀上。"""
    func = _function(tree, "_writes_go_to_pgvector")
    for node in ast.walk(func):
        if not (isinstance(node, ast.Return) and node.value is not None):
            continue
        value = node.value
        if isinstance(value, ast.Call) and ast.unparse(value.func) == "bool" and value.args:
            value = value.args[0]
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And):
            return value
    raise AssertionError("停写判定不再是『若干枚条件与成』的形状，本文件的刀不适用")


def drop_predicate_term(source, name):
    """形一/形二：从合取里摘掉指定那一枚条件（源码副本，盘上不动）。"""
    tree = ast.parse(source)
    conjunction = _predicate_conjunction(tree)
    keep = [item for item in conjunction.values if name not in ast.unparse(item)]
    if len(keep) == len(conjunction.values):
        raise AssertionError("合取项里本来就没有 %s，这把刀没磨到东西" % name)
    segment = ast.get_source_segment(source, conjunction)
    replacement = keep[0] and ast.unparse(keep[0]) or "True"
    assert segment and source.count(segment) == 1
    return source.replace(segment, replacement, 1)


def drop_stores_vectors_guard(source):
    """形三：摘掉判定顶部那枚『不存向量就早退』（`stores_vectors` 那一枚条件的写法是早退不是合取项）。"""
    tree = ast.parse(source)
    func = _function(tree, "_writes_go_to_pgvector")
    for node in func.body:
        if isinstance(node, ast.If) and "stores_vectors" in ast.unparse(node.test):
            segment = ast.get_source_segment(source, node)
            assert segment and source.count(segment) == 1
            return source.replace(segment, "pass", 1)
    raise AssertionError("顶部那枚早退不在判定里，这把刀没磨到东西")


def add_extra_write_site(source):
    """形四：在 pgvector 主写那一支里多插一枚 Chroma 写点（枚数 +1、名册对不上）。"""
    tree = ast.parse(source)
    func = _function(tree, "_write_batch")
    for node in ast.walk(func):
        if isinstance(node, ast.If) and "_writes_go_to_pgvector" in ast.unparse(node.test):
            extra = ast.parse("self.collection.upsert(ids=ids)").body[0]
            ast.copy_location(extra, node.body[0])
            node.body.insert(0, extra)
            return ast.unparse(tree)
    raise AssertionError("找不到停写判定那一道分支，刀没磨上")


def collide_write_site_identities(source):
    """形五：枚数不变、身份撞车——把主写那枚 add 的 `embeddings` 关键字摘掉，它就与离线那一枚同名。"""
    needle = "embeddings=list(embeddings),"
    if source.count(needle) != 1:
        raise AssertionError("主写那枚 add 的 embeddings 关键字不是恰好一处，这把刀不适用")
    return source.replace(needle, "", 1)

# --------------------------------------------------------------- 静态三面的装配（可换源码副本）


def app_sources(tool, **overrides):
    sources = tool.app_sources()
    sources.update(overrides)
    return sources


def measure_static(tool, roster, *, retriever=None, pg_store_text=None):
    """把静态三面拼起来，语料面按"未取数"交回；换掉的源码副本只进内存，盘上不动。"""
    sources = app_sources(tool, **({RETRIEVER_REL: retriever} if retriever is not None else {}),
                          **({PG_STORE_REL: pg_store_text} if pg_store_text is not None else {}))
    retriever_src = sources[RETRIEVER_REL]
    pg_src = sources[PG_STORE_REL]
    #: 换了 retriever 就从那份副本现取写点，别的文件照旧全扫：一枚都不许少。
    if retriever is None:
        sites = roster.app_write_sites()
    else:
        sites = [item for item in roster.app_write_sites() if item.path != RETRIEVER_REL]
        sites = tuple(sites + list(roster.chroma_write_sites(retriever_src, RETRIEVER_REL)))
    predicate = tool.predicate_terms(roster, retriever_src)
    site_face = tool.write_site_face(roster, sites, retriever_src)
    void = tool.roster_cross_check(roster, site_face)
    gated = tool.switch_gated_legs(roster, pg_src)
    legs = [row["leg"] for row in gated["legs"]]
    questions = tool.predicate_dependent_questions(roster, retriever_src, legs)
    waiters = tool.legacy_receipt_waiters(sources, gated["legs"])
    findings = tool.off_state_findings(predicate, site_face, questions, waiters, None)
    return {
        "predicate": predicate,
        "site_face": site_face,
        "void": void,
        "legs": gated,
        "questions": questions,
        "waiters": waiters,
        "findings": findings,
        "codes": {item["code"] for item in findings},
        "exit": tool.EXIT_PRECONDITION if void
                else tool.classify_exit(findings, corpus_gathered=False),
    }


def _subjects_by_code(findings, code):
    return {item["subject"] for item in findings if item["code"] == code}


# ------------------------------------------------- 面一/面二：今天的读数与"少一枚条件就红"


def test_the_registered_write_site_roster_is_green_before_any_knife(tool, roster, retriever_source,
                                                                   pg_store_source):
    """刀先要有的砍：真码上在册那枚名册件与本量具的派生必须同时是绿的，否则下面的红没意义。"""
    reading = measure_static(tool, roster, retriever=retriever_source,
                             pg_store_text=pg_store_source)
    assert reading["site_face"]["roster_findings"] == [], reading["site_face"]["roster_findings"]
    assert reading["void"] == [], reading["void"]


def test_the_tool_names_every_write_site_the_registered_roster_knows(tool, roster, retriever_source,
                                                                    pg_store_source):
    """写点身份集合与在册名册**逐枚相等**——不数枚数，因为枚数相等而身份换过正是 R625 判据⑥那一形。"""
    reading = measure_static(tool, roster)
    assert {item["identity"] for item in reading["site_face"]["sites"]} \
        == set(roster.CHROMA_WRITE_ROSTER)


def test_turning_the_switch_off_is_measured_as_a_loss_not_a_green(tool, roster, retriever_source,
                                                                 pg_store_source):
    """本单的核心读数：这一格现在**不能翻**，而且不许由"没发现"冒充"可翻"。"""
    reading = measure_static(tool, roster)
    assert {"chroma_write_gate_reopens",
            "compensation_needs_a_leg_it_wont_have",
            "delete_set_blind_to_pg_only_rows",
            "question_rehomes_to_legacy_store",
            "read_leg_waits_for_chroma_receipt"} <= reading["codes"], reading["codes"]
    assert reading["exit"] == tool.EXIT_CANNOT_FLIP


def test_the_stop_write_predicate_is_still_a_conjunction_of_the_registered_terms(tool, roster,
                                                                               retriever_source):
    """前提钉：判定今天由这几枚条件与成，其中一枚就是这枚旋钮。前提被改掉时本单整问句要重对。"""
    predicate = tool.predicate_terms(roster, retriever_source)
    assert predicate["present"] is True
    assert predicate["conjunction"] is True
    assert predicate["switch_terms"], predicate["terms"]
    assert predicate["backend_terms"], predicate["terms"]
    assert any("stores_vectors" in item["test"] for item in predicate["early_returns"]), \
        predicate["early_returns"]


@pytest.mark.parametrize("term", ["dual_write_enabled", "pgvector_writes_are_primary"])
def test_dropping_a_conjunct_from_the_predicate_is_named_by_name(tool, roster, retriever_source,
                                                                pg_store_source, term):
    """摘掉双写判定中的一枚合取项 ⇒ 必须红，且红句点名的是**被摘掉的那一枚**。

    在册的 parity 件钉的是"三枚条件还写在判定那一段里"（读真盘上的文本）；本枚钉的是**派生随码走**：
    把判定摘一枚之后量具自己的读数改不改口。前者量不到后者（它无从在不改盘的前提下换码）。
    """
    mutated = drop_predicate_term(retriever_source, term)
    assert mutated != retriever_source
    reading = measure_static(tool, roster, retriever=mutated)
    assert term not in " ".join(reading["predicate"]["terms"]), reading["predicate"]["terms"]
    assert term in _subjects_by_code(reading["findings"], "predicate_term_missing"), \
        reading["findings"]
    assert reading["exit"] != tool.EXIT_CAN_FLIP


def test_dropping_the_stores_vectors_early_return_is_named(tool, roster, retriever_source,
                                                          pg_store_source):
    """第三枚条件写成早退而不是合取项：把它摘掉同样必须红，并点名 `stores_vectors`。

    这一形在册 parity 件钉的是"名字还在文本里"；把早退还成 `pass` 之后名字仍在（在合取项里），
    它的静态那格照旧绿——本枚补的就是那一格量不到的形状。
    """
    mutated = drop_stores_vectors_guard(retriever_source)
    assert "stores_vectors" in mutated, "刀要把早退还成 pass，判定里那枚合取项仍该留着"
    reading = measure_static(tool, roster, retriever=mutated)
    assert reading["predicate"]["early_returns"] == []
    assert "stores_vectors" in _subjects_by_code(reading["findings"], "predicate_term_missing"), \
        reading["findings"]


# ---------------------------------------------------------------- 名册不一致：量具不许自说自话


def _named_in(void, findings, needle):
    """在册件交回的是句子，本量具交回的是 dict：两种都按"点名了那一句身份"判。"""
    texts = [str(item) for item in void]
    texts += [item if isinstance(item, str) else item["text"] for item in findings]
    return any(needle in text for text in texts)


def test_an_extra_chroma_write_site_is_reported_as_untrustworthy(tool, roster, retriever_source):
    """名册之外多出一枚变异写点 ⇒ 本量具按 `roster_cross_check_failed` 收，走 2 号，不许当普通发现读。"""
    mutated = add_extra_write_site(retriever_source)
    sites = roster.chroma_write_sites(mutated, RETRIEVER_REL)
    face = tool.write_site_face(roster, sites, mutated)
    void = tool.roster_cross_check(roster, face)
    assert void, "主写路径上多插一枚 Chroma 写点，名册对账没红——那它还是在数枚数"
    extra = "%s::DocumentRetriever._write_batch::upsert(ids)" % RETRIEVER_REL
    assert _named_in(void, face["roster_findings"], extra), (void, face["roster_findings"])


def test_a_removed_write_site_is_named_by_identity(tool, roster, retriever_source):
    """把名册在册的某枚写点摘掉（回滚通路被拆）⇒ 报的是那一枚的身份，不是"数量不对"。"""
    needle = "self.collection.add(ids=ids, documents=documents, metadatas=metadatas)"
    assert retriever_source.count(needle) == 1, "摘的就是离线 _JsonCollection 那一枚"
    mutated = retriever_source.replace(needle, "pass", 1)
    sites = roster.chroma_write_sites(mutated, RETRIEVER_REL)
    face = tool.write_site_face(roster, sites, mutated)
    void = tool.roster_cross_check(roster, face)
    missing = "%s::DocumentRetriever._write_batch::add(documents, ids, metadatas)" % RETRIEVER_REL
    assert missing not in {item["identity"] for item in face["sites"]}
    assert _named_in(void, face["roster_findings"], missing), (void, face["roster_findings"])


def test_a_count_preserving_identity_swap_still_bites(tool, roster, retriever_source):
    """判据⑥的同族：枚数一字不变、两枚身份撞成同一句 ⇒ 量具自己那一枚红必须落地（不只借在册件的话）。"""
    mutated = collide_write_site_identities(retriever_source)
    sites = roster.chroma_write_sites(mutated, RETRIEVER_REL)
    identities = [item.identity for item in sites]
    assert len(identities) == len(roster.app_write_sites()), "这一形按定义就该枚数不变"
    face = tool.write_site_face(roster, sites, mutated)
    void = tool.roster_cross_check(roster, face)
    assert any("同一身份" in item for item in void), void
    collided = "%s::DocumentRetriever._write_batch::add(documents, embeddings, ids, metadatas)" \
        % RETRIEVER_REL
    assert _named_in(void, face["roster_findings"], collided), (void, face["roster_findings"])

# -------------------------------------- 面三：拒答面与「隐式等 Chroma 回执」面（两把反向刀）


def leg_names(reading):
    return {row["leg"] for row in reading["legs"]["legs"]}


def waiter_legs(reading):
    return {item["leg"] for item in reading["waiters"]["waiters"]}


def test_the_refusing_legs_and_their_chroma_receipts_are_named_from_the_code(tool, roster,
                                                                            retriever_source,
                                                                            pg_store_source):
    """今天的读数：两枚拒答面与两条"答复改由 Chroma 给"的路径都要点得出名字。

    这一格不许拿数量当判据——`switch_gated_legs()` 与 `legacy_receipt_waiters()` 全从 AST 现取，
    下面两把反向刀各摘一格，派生必须跟着改口；把它们写成 `== 3` / `== 2` 就量不到那一族。
    """
    reading = measure_static(tool, roster)
    assert {"read_topk", "read_corpus", "_document_leg_connection",
            "document_vector_rows", "indexed_document_names"} <= leg_names(reading), leg_names(reading)
    pairs = {(item["leg"], item["refusal_swallowed_by"], item["answered_by"])
             for item in reading["waiters"]["waiters"]}
    assert ("read_topk", "app/rag/retriever.py::_pgvector_hits",
            "app/rag/retriever.py::search") in pairs, pairs
    assert ("read_corpus", "app/rag/pg_store.py::switched_corpus",
            "app/rag/retrieval_pipeline.py::build_index") in pairs, pairs
    assert "read_leg_waits_for_chroma_receipt" in reading["codes"]


def test_a_refusal_on_another_reason_is_not_a_dual_write_leg(tool, roster, retriever_source,
                                                             pg_store_source):
    """反向刀一：把 `read_topk` 那处开关拒答换成别的稳定码 ⇒ 这条腿与它的回执一起从派生里消失。

    另一格（语料腿）一字没动，必须照旧在册——这才叫"点名派生"，不是"整面翻红"。
    """
    needle = "reason=REASON_VECTOR_READ_WITHOUT_DUAL_WRITE)"
    assert pg_store_source.count(needle) >= 3, "三处开关拒答同形，本刀只换第一处（read_topk）"
    mutated = pg_store_source.replace(needle, "reason=REASON_VECTOR_READ_FAILED)", 1)
    reading = measure_static(tool, roster, pg_store_text=mutated)
    assert "read_topk" not in leg_names(reading), leg_names(reading)
    assert "read_topk" not in waiter_legs(reading), waiter_legs(reading)
    assert "read_corpus" in leg_names(reading)
    assert "read_corpus" in waiter_legs(reading)


def _raise_instead_of_swallowing(source):
    """把 `_pgvector_hits` 里那处 except 改成原样上抛（拒答不再被吞成"这一腿没答"）。"""
    tree = ast.parse(source)
    func = _function(tree, "_pgvector_hits")
    for node in ast.walk(func):
        if isinstance(node, ast.Try) and node.handlers:
            node.handlers[0].body.append(ast.parse("raise").body[0])
            return ast.unparse(tree)
    raise AssertionError("_pgvector_hits 里没有 try/except，这把刀没磨到东西")


def test_a_refusal_that_is_not_swallowed_stops_being_a_receipt(tool, roster, retriever_source,
                                                               pg_store_source):
    """反向刀二：吞掉拒答那一支改成上抛 ⇒ 腿还在、回执消失。

    这一枚钉的是"隐式等 Chroma 回执"这句话里**唯一可证的那一半**：拒答被谁吞、答复由谁给。
    它不许把 fail-closed 的拒答（`_document_rows_by_leg` 那一支原样上抛）读成静默降级——
    同一份码里两种形状并存，只有这一种进 waiters。
    """
    mutated = _raise_instead_of_swallowing(retriever_source)
    reading = measure_static(tool, roster, retriever=mutated)
    assert "read_topk" in leg_names(reading), "拒答面一字没动，腿必须还在册上"
    assert "read_topk" not in waiter_legs(reading), waiter_legs(reading)
    assert "read_corpus" in waiter_legs(reading), "另一条不该被误伤"


def test_the_questions_that_move_back_to_the_legacy_directory_are_named(tool, roster,
                                                                       retriever_source,
                                                                       pg_store_source):
    """名单与按文档读回这两句在 off 态改问遗留目录；早退那一支（PG 那一格恒空）另是一形。"""
    reading = measure_static(tool, roster)
    by_question = {row["question"]: row for row in reading["questions"]["questions"]}
    assert by_question["DocumentRetriever._document_rows_by_leg"]["negated_early_return"]
    assert by_question["DocumentRetriever.list_documents"]["positive_branch"]
    assert by_question["DocumentRetriever.document_chunks"]["positive_branch"]
    subjects = {item["subject"] for item in reading["findings"]
                if item["code"] == "question_rehomes_to_legacy_store"}
    assert {"DocumentRetriever.list_documents", "DocumentRetriever.document_chunks",
            "DocumentRetriever._document_rows_by_leg"} <= subjects, subjects


def test_the_compensation_family_is_reported_as_needing_a_leg_it_wont_have(tool, roster,
                                                                          retriever_source,
                                                                          pg_store_source):
    """补偿那一族的闸门文字从赋值现取：写侧那条腿改名（`mirror`→`leg`），判据一字不改。

    这一枚钉的是量具自己：谁把"腿"的名字写死成字面量，改名那一刀就会让它闭嘴——那正是
    本仓记过一整族的"名字会漂"病。
    """
    baseline = measure_static(tool, roster)
    codes = {item["code"] for item in baseline["findings"]}
    assert "compensation_needs_a_leg_it_wont_have" in codes, baseline["findings"]
    renamed = re.sub(r"\bmirror\b", "leg", retriever_source)
    assert "leg = self._open_vector_mirror()" in renamed, "刀要改的是名字，不是生产者函数"
    reading = measure_static(tool, roster, retriever=renamed)
    assert "compensation_needs_a_leg_it_wont_have" in reading["codes"], reading["findings"]


def test_the_tool_carries_no_second_list_of_write_sites(tool):
    """本单硬规：写点清单只有一份。量具里不许出现第二份身份、函数名或 `collection.add` 的字面抄本。"""
    source = TOOL_PATH.read_text(encoding="utf-8")
    for needle in (".collection.add(", "::DocumentRetriever.", "_undo_vector_write",
                   "CHROMA_WRITE_ROSTER = "):
        assert needle not in source, "量具里出现了第二份抄本：" + needle
    assert "CHROMA_WRITE_ROSTER" in source, "名册要从在册件读回来，不是自己造一份"

# --------------------------------------------------------------- 现跑：off 态掉的是哪一格


def test_answers_move_back_to_the_legacy_engine_while_the_switch_is_off(tmp_path, monkeypatch):
    """把开关从 on 拨到 off：语义答复真的改由 Chroma 给出，bypass 原因码点名那一枚稳定码。

    这一枚是「隐式等 Chroma 回执」的现跑凭据：`read_topk()` 连一条 SQL 都不发（拿不到腿就拒开），
    上一层把拒答吞成"这一腿没答"，`search()` 于是落到 `collection.query()`。在册的
    `test_r59b_pg_read_switch` 钉的是"连不上"那一枚原因（`vector_mirror` 抛异常），
    这一枚钉的是"旋钮关着"那一枚原因——同一族里两格，红的不是同一件事。
    """
    instance = _build_retriever(tmp_path, monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "off")

    hits = instance.search("住宿费标准", k=5)

    assert isinstance(hits, list)
    reading = rt.search_shape_diagnostics()["last"]
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA, reading
    assert reading["leg"] == "semantic"
    bypass = pg_store.vector_read_diagnostics()["last_bypass"]
    assert bypass["reason"] == pg_store.REASON_VECTOR_READ_WITHOUT_DUAL_WRITE, bypass
    assert pg_store.vector_read_diagnostics()["answered"] == 0


def test_a_row_written_after_the_flip_is_undeletable_and_off_the_list_when_the_switch_is_off(monkeypatch):
    """🔴 这一格是 S1 停双写最贵的形状：切换之后只落在 PG 的行，off 态**删不掉、名单里也没有**。

    `delete_document()` 先问 `_document_rows_by_leg()`；那句在 off 态走早退、PG 那一格恒交回空列表，
    于是删除集合为空——它不报错、原样 return，端点报删除成功，而那一行还在 `chunk_vectors` 里。
    这正是 R60 判据③在切换态治过的病，被这枚旋钮关回去。
    """
    table = PgTable([pg_row("late.txt_0", "late.txt", 0, "切换之后写的正文", "sha-new")])
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                            dual="off", table=table, legacy=LegacyHandle())

    assert instance.list_documents() == [], "名单退回遗留腿：这篇文档从名单上消失"
    assert instance.delete_document("late.txt") is None
    assert sorted(table.rows) == ["late.txt_0"], "关掉双写之后这一行一枚都删不掉"
    assert connection.log == [], "这一档连 PG 腿都没有，一条 SQL 都不该发出去"


def test_the_same_delete_works_while_the_switch_is_on(monkeypatch):
    """正控：同一份码、同一批存量行，双写开着时删除真的落到 PG。

    上一枚的红因此只可能来自那枚旋钮，不可能来自本文件的假腿。
    """
    table = PgTable([pg_row("late.txt_0", "late.txt", 0, "切换之后写的正文", "sha-new")])
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                            dual="on", table=table, legacy=LegacyHandle())

    assert instance.delete_document("late.txt") is None
    assert table.rows == {}
    assert "delete" in connection.log


def test_a_reupload_while_the_switch_is_off_leaves_the_previous_version_behind(monkeypatch):
    """同名重传在 off 态只改遗留腿那一版；重开双写之后，PG 交回的是**上一版**的正文。

    这一形给"回滚姿势"下定义：缺口不是零，回滚点也不是免费的——重开开关那一刻，客户看到的
    是上一版，而端点报的是这一次的上传成功。
    """
    table = PgTable([pg_row("v.txt_0", "v.txt", 0, "上一版的正文", "sha-old"),
                     pg_row("v.txt_1", "v.txt", 1, "上一版的下半", "sha-old")])
    legacy = LegacyHandle()
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                            dual="off", table=table, legacy=legacy)

    ok, _message = instance.add_document("v.txt", "新一\n的新二")

    assert ok is True
    assert legacy.count() == 2, "写闸门开了：新行这次全进遗留腿"
    assert sorted(table.rows) == ["v.txt_0", "v.txt_1"], "PG 那一侧一字未动"
    assert "delete" not in connection.log

    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "on")
    assert [row["content"] for row in instance.document_chunks("v.txt")] == [
        "上一版的正文", "上一版的下半"], "重开双写活回来的是上一版"


# --------------------------------------------------- 语料面：只走注入的连接与快照（本席一枚库都没连）


class _OneRow:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return (self.value,)

    def fetchall(self):
        return []


class _FakeConnection:
    def __init__(self, read_only="on"):
        self.read_only = read_only
        self.sent = []
        self.closes = 0

    def execute(self, sql, params=None):
        self.sent.append(str(sql))
        return _OneRow(self.read_only)

    def close(self):
        self.closes += 1


class _FakeCollection:
    def __init__(self, ids):
        self.ids = sorted(str(item) for item in ids)

    def count(self):
        return len(self.ids)


DRIFT = {"pg_vectors": 3, "chroma_vectors": 2, "only_in_pg": ["new.txt_0"],
         "only_in_chroma": ["gone.txt_7"], "wrong_width": [], "all_zero_rows": 0,
         "index_version_id_null": 2, "chunks_rows": 3, "chunks_with_backfilled_embedding": 0}


class FakeRecallTool:
    """scripts/compare_vector_recall.py 的接缝：只记"被叫过几次、拿的什么串"。"""

    def __init__(self, connection=None, ids=("a.txt_0", "gone.txt_7")):
        self.connection = connection or _FakeConnection()
        self.ids = list(ids)
        self.connects = []
        self.drift_calls = 0

    def open_chroma(self, chroma_dir, collection_name):
        return _FakeCollection(self.ids)

    def connect_read_only(self, url):
        self.connects.append(str(url))
        return self.connection

    def read_scope(self, connection, vector_table):
        return {"embedding_model": "nomic-embed-text", "dimension": 8,
                "distance_function": "cosine", "column_type": "vector(8)"}

    def corpus_drift(self, connection, collection, *, vector_table, scope):
        self.drift_calls += 1
        return dict(DRIFT)

    def chroma_all_ids(self, collection):
        return sorted(collection.ids)


class FakeSnapshotProbe:
    """r626 的快照接缝：本文件不去开任何一枚真卷。"""

    def __init__(self, snapshot="C:/tmp/r633-snapshot"):
        self.snapshot = pathlib.Path(snapshot)
        self.removed = []

    def chroma_dir_for_run(self, args, staging):
        return self.snapshot, True

    def volume_inventory(self, directory):
        return {"files": 1, "bytes": 8, "digest": "a" * 16}

    def inventories_match(self, before, after):
        return before["digest"] == after["digest"]

    def remove_snapshot(self, snapshot):
        self.removed.append(str(snapshot))


def corpus_args(tool, **overrides):
    values = {"database_url": "postgresql://u@127.0.0.1:5432/eb_r59_sandbox",
              "window_owner": "", "chroma_dir": None, "snapshot_from": None,
              "collection": "enterprise_docs", "vector_table": "chunk_vectors"}
    values.update(overrides)
    return types.SimpleNamespace(**values)

def test_the_corpus_face_names_the_gap_that_defines_the_rollback(tool):
    """给了库与卷之后，语料面交回"关掉双写会整篇消失的文档"，并把它写成一条 corpus_gap 发现。

    缺口区间就是这一格：`only_in_pg` 里那些 id 是切换之后写的、遗留腿一枚都没有；重开双写时
    回滚点不是"拨回去就完"，而是"这批行了不得要补重建"。数字来自注入的假件，本席没连任何库。
    """
    fake_tool, fake_probe = FakeRecallTool(), FakeSnapshotProbe()
    corpus = tool.corpus_face(corpus_args(tool), fake_probe, fake_tool, pathlib.Path("C:/tmp/staging"))

    assert corpus["gathered"] is True
    assert corpus["drift"]["only_in_pg"] == 1
    assert corpus["drift"]["index_version_id_null"] == 2
    assert corpus["documents"]["vanish_if_off"] == ["new.txt"], corpus["documents"]
    assert corpus["database"]["sandbox"] is True
    #: 判定面摆成"今天真码那一形"，这样语料面那两条红句之外不该有任何别的发现混进来。
    predicate = {"present": True, "conjunction": True,
                 "terms": ["pg_store.dual_write_enabled()",
                           "indexing_module.pgvector_writes_are_primary()"],
                 "switch_terms": ["pg_store.dual_write_enabled()"],
                 "backend_terms": ["indexing_module.pgvector_writes_are_primary()"],
                 "early_returns": [{"test": "not self.stores_vectors", "returns": "False"}]}
    findings = tool.off_state_findings(predicate, {"sites": []}, {"questions": []},
                                       {"waiters": []}, corpus)
    assert [item["code"] for item in findings] == ["corpus_gap", "corpus_gap"], findings
    assert {item["subject"] for item in findings} == {"only_in_pg", "only_in_chroma"}
    assert "new.txt" in findings[0]["text"], findings[0]
    assert fake_probe.removed == [str(fake_probe.snapshot)], "本量具造的快照要自己收走"


def test_a_non_sandbox_database_is_refused_before_anything_is_connected(tool):
    """🔴 本单硬规：不许真连生产库。库名不在沙盒那一族又没给开窗责任人 ⇒ 一次连接都不许发生。"""
    fake_tool, fake_probe = FakeRecallTool(), FakeSnapshotProbe()
    with pytest.raises(SystemExit) as refused:
        tool.corpus_face(corpus_args(fake_tool, database_url="postgresql://u@h:5432/enterprise_brain"),
                         fake_probe, fake_tool, pathlib.Path("C:/tmp/staging"))
    assert refused.value.code == tool.EXIT_PRECONDITION
    assert fake_tool.connects == [], "拒在连接之前，不是拒在连接之后"
    assert fake_tool.drift_calls == 0


def test_the_window_owner_token_is_what_opens_the_production_pass(tool):
    """同一枚库名，给了开窗责任人就读得下去：这一格是"生产那一遍由总控开窗跑"的形状。"""
    fake_tool, fake_probe = FakeRecallTool(), FakeSnapshotProbe()
    corpus = tool.corpus_face(corpus_args(fake_tool, database_url="postgresql://u@h:5432/enterprise_brain",
                                          window_owner="总控·10-04 测量窗"),
                              fake_probe, fake_tool, pathlib.Path("C:/tmp/staging"))
    assert corpus["database"]["name"] == "enterprise_brain"
    assert corpus["database"]["sandbox"] is False
    assert corpus["database"]["window_owner"] == "总控·10-04 测量窗"
    assert fake_tool.connects == ["postgresql://u@h:5432/enterprise_brain"]


def test_a_session_that_is_not_read_only_is_refused(tool):
    """`connect_read_only()` 设不上 READ ONLY 只 print 一句 warn；本量具不接受 warn，直接按 2 号收。"""
    fake_tool = FakeRecallTool(connection=_FakeConnection(read_only="off"))
    with pytest.raises(SystemExit) as refused:
        tool.corpus_face(corpus_args(fake_tool), FakeSnapshotProbe(), fake_tool,
                         pathlib.Path("C:/tmp/staging"))
    assert refused.value.code == tool.EXIT_PRECONDITION
    assert fake_tool.drift_calls == 0
    assert "SHOW transaction_read_only" in fake_tool.connection.sent


def test_the_live_volume_guard_is_the_registered_one_not_a_second_copy(tool):
    """开库前的那枚"现役卷"判据复用 r626：`--chroma-dir` 指到仓根的 chroma_db 必须按 2 号收。"""
    probe = _load(PROBE_PATH, "r633_probe_under_test")
    args = corpus_args(tool, snapshot_from=None, chroma_dir=str(REPO / "chroma_db"))
    with pytest.raises(SystemExit) as refused:
        probe.chroma_dir_for_run(args, pathlib.Path(tempfile.mkdtemp()))
    assert refused.value.code == tool.EXIT_PRECONDITION

    def _silent(*_args, **_kwargs):
        raise AssertionError("现役卷不该被复制")

    with pytest.raises(SystemExit):
        probe.snapshot_volume(str(REPO / "no-such-dir"), str(tempfile.mkdtemp()), copier=_silent)


def test_no_default_volume_and_no_default_connection_string(tool):
    """本量具没有"打开默认卷"与"连出厂那串库"这两档：缺省全是 None，语料面就报未取数。"""
    args = tool.parse_args([])
    assert args.chroma_dir is None and args.snapshot_from is None
    assert args.database_url is None
    assert args.window_owner is None


def test_the_switch_face_reads_both_knobs_without_opening_anything(tool, monkeypatch):
    """旋钮面一不发 SQL、二不开连接：两把旋钮的现读答复与出厂缺省都要读得到。"""
    monkeypatch.setenv(pg_store.DUAL_WRITE_ENV, "off")
    monkeypatch.setenv(indexing.INDEX_BACKEND_ENV, indexing.PGVECTOR_BACKEND)
    face = tool.switch_face()
    assert face["knobs"][pg_store.DUAL_WRITE_ENV]["resolved_by_dual_write_enabled"] is False
    backend = face["knobs"][indexing.INDEX_BACKEND_ENV]
    assert backend["reads_enabled"] is True
    assert backend["writes_primary"] is True
    assert backend["factory_default"] == indexing.INDEX_BACKEND_DEFAULT == "chroma"
    assert face["deployment_declaration"]["declared"] == {}


def test_the_deployment_declaration_is_read_as_text_not_as_credentials(tool):
    """`--env-file` 只取那两把旋钮的原文与行号；库串一类凭据一个字都不进出产。"""
    path = pathlib.Path(tempfile.mkdtemp()) / "env.snapshot"
    path.write_text("INDEX_BACKEND=pgvector\nVECTOR_DUAL_WRITE=on\nDATABASE_URL=postgresql://u:p@h/db\n",
                    encoding="utf-8")
    declared = tool.deployment_declaration(str(path))["declared"]
    assert declared["INDEX_BACKEND"]["value"] == "pgvector"
    assert declared["VECTOR_DUAL_WRITE"]["value"] == "on"
    assert "DATABASE_URL" not in declared, "凭据不进读数（私有化：一台机器一套口令）"


@pytest.mark.parametrize("findings,gathered,want", [
    ([], True, 0),
    ([{"code": "corpus_gap", "subject": "x", "text": "y"}], True, 1),
    ([{"code": "chroma_write_gate_reopens", "subject": "x", "text": "y"}], False, 1),
    ([], False, 3),
])
def test_the_exit_code_meaning_is_fixed(tool, findings, gathered, want):
    """1 号只允许由"检出发现"发出，3 号是"语料面未取数"而不是绿（与 R269 同一口径）。"""
    assert tool.classify_exit(findings, corpus_gathered=gathered) == want


def test_products_may_not_land_in_the_repo(tool):
    """产物落仓外：指进工作树当场按 2 号收；写出来的两枚文件也必须全在仓外。"""
    with pytest.raises(SystemExit) as refused:
        tool.guard_out_dir(str(tool.ROOT / "tmp-r633"))
    assert refused.value.code == tool.EXIT_PRECONDITION
    outside = tool.guard_out_dir(str(pathlib.Path(tempfile.mkdtemp()) / "r633"))
    assert not str(outside).startswith(str(tool.ROOT))

    report = {"revision": "x", "run_stamp": "T", "exit_code": 1, "exit_meaning": "…",
              "predicate": {"terms": []}, "write_sites": {"sites": []}, "findings": [],
              "corpus": {"gathered": False}}
    for key, value in tool.write_outputs(report, outside).items():
        assert not str(value).startswith(str(tool.ROOT)), key


def test_the_precondition_prefix_is_the_registered_one(tool):
    """stderr 首行那串前缀与在册两枚件同值，谁改一边就红（照 r626 立的规矩再钉一遍）。"""
    recall = _load(RECALL_PATH, "r633_recall_under_test")
    probe = _load(PROBE_PATH, "r633_probe_prefix_under_test")
    assert tool.PRECONDITION_PREFIX == recall.PRECONDITION_PREFIX
    assert tool.PRECONDITION_PREFIX == probe.PRECONDITION_PREFIX


def test_the_epilog_states_every_exit_code(tool):
    """退出码语义写死在 epilog：0/1/2/3 各一句话，外加"哪一枚代码名对应哪一格"。"""
    epilog = tool.EPILOG
    for line in ("  0 ", "  1 ", "  2 ", "  3 "):
        assert line in epilog, line
    for code in tool.CODES:
        assert code in epilog, code + " 没写进 epilog"
