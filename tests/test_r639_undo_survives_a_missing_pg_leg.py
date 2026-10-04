# -*- coding: utf-8 -*-
"""R639-A 的牙 —— 关掉 VECTOR_DUAL_WRITE 之后，逆序补偿不许再要求一条它拿不到的腿。

判据④要的是可判定的形状：off 态里"撤销遗留目录刚接下的那批新行"这一能力，要么**真存在且被
真调用**，要么在写之前就把这一笔**拒掉**并交出具名错误码。本文件两头都钉住：

  * 矛盾档（``INDEX_BACKEND=pgvector`` ＋ ``VECTOR_DUAL_WRITE=off``）现跑三枚：同名重传中途
    失败 ⇒ 新行被撤、上一版原样放回；旧向量读不出快照 ⇒ 一笔都不许落库，交回**在册**那枚
    ``REASON_VECTOR_MIRROR_UNAVAILABLE``（本单不新造错误码，改名字或删字典行都会红）。
  * 正控三枚：出厂默认档（``chroma`` ＋ off）不许多读一次快照、也不许把文档撤成零行——半截
    回滚比不回滚更糟，本单不许制造；生产现态（on）里 ``rollback()`` 仍是硬要求，缺腿时不许
    谎报"PG 事务状态未知"。
  * 静态牙三枚：两枚补偿调用点的调用路径上不许再出现"这条腿拿得到"那一形（腿的名字从生产者
    赋值现取，``mirror`` 改名成 ``leg`` 判据一字不改）；``rollback()`` 必须回到"有腿才问"之内；
    撤新行那一支仍由"本次真写过"与停写判定共同决定，不许被本单稀释。

全程离线：不连 PostgreSQL、不起服务、不开现役 ``chroma_db`` 卷、不打模型、不发一条写语句。
假腿复用 ``test_r60_write_path_unique_under_pgvector`` 那套装配台——本仓规矩，不为新单再造一套
平行假腿。
"""

from __future__ import annotations

import ast
import logging
import pathlib
import re

import pytest

from app.rag import indexing
from app.rag import retriever as rt
from app.rag.retriever import DocumentRetriever
from test_r60_write_path_unique_under_pgvector import LegacyHandle, _assemble, legacy_row

DOC = "b.txt"
PREVIOUS = "上一版的正文"
#: 腿只有这两枚生产者（与 R633 量具同口径）：闸门里出现"这两枚交回来的东西非 None"，就等于
#: 把补偿挂在那条腿上。名字不写死——本仓为"名字会漂"记过一整族事故。
LEG_PRODUCERS = ("vector_mirror", "_open_vector_mirror")


def _source() -> str:
    """产品码现读。走 ``rt.__file__`` 而不是抄路径，也不 import 端点层（一发 import 就发探针）。"""
    return pathlib.Path(rt.__file__).resolve().read_text(encoding="utf-8")


def _functions(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _leg_names_in(host):
    """宿主函数里"那条腿"可能叫什么：生产者赋值的目标 ∪ 交进来的形参名。

    两样都从 AST 现取，一枚字面名都不写死：写侧的腿是 ``mirror = self._open_vector_mirror()``
    赋值得来的，而 ``_undo_vector_write`` 的腿是**形参**交进来的——只认赋值就会在那一枚函数里
    取到空集合，门就永远量不到（本席第一版就栽在这儿，靠正控现取才露馅）。
    """
    out = set()
    for node in ast.walk(host):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            called = ast.unparse(node.value.func)
            if any(called.endswith(name) for name in LEG_PRODUCERS):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out.add(target.id)
    arguments = host.args
    for group in (arguments.posonlyargs, arguments.args, arguments.kwonlyargs):
        for argument in group:
            if argument.arg != "self":
                out.add(argument.arg)
    return out


def _compensation_call_sites(source_text):
    """每一枚 ``_undo_vector_write(...)`` 调用点：交回宿主函数名与调用路径上的每一枚 if 原文。"""
    tree = ast.parse(source_text)
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "_undo_vector_write":
            continue
        guards, host, host_node = [], "", None
        current = parents.get(id(node))
        while current is not None:
            if isinstance(current, ast.If):
                guards.append(" ".join(ast.unparse(current.test).split()))
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                host, host_node = current.name, current
                break
            current = parents.get(id(current))
        found.append({"host": host, "guards": guards, "leg_names": _leg_names_in(host_node)})
    return found


class _NoSnapshotLegacy(LegacyHandle):
    """会记账、但读不出 embeddings 的遗留目录：在这里"忠实还原"物理上不可能。"""

    def get(self, where=None, ids=None, include=None, limit=None, offset=None):
        result = super().get(where=where, ids=ids, include=include, limit=limit, offset=offset)
        result.pop("embeddings", None)
        return result


class _FlakyLegacy(LegacyHandle):
    """第二批新 chunk 写下去就炸：演的是"旧版已删、新版只写了一半"那一次失败。"""

    def __init__(self, rows=(), fail_on=()):
        super().__init__(rows)
        self.fail_on = [str(item) for item in fail_on]

    def add(self, ids, documents, metadatas, embeddings=None):
        if any(str(item) in self.fail_on for item in ids):
            raise RuntimeError("模拟第二批写入失败")
        return super().add(ids=ids, documents=documents, metadatas=metadatas,
                           embeddings=embeddings)


def _two_batches(monkeypatch):
    """把 2000 一枚的批次切成两枚：两 chunk 的文档也能演"第一批写成、第二批炸"。"""
    monkeypatch.setattr(DocumentRetriever, "_batch_ranges",
                        staticmethod(lambda total, batch_size: [(0, 1), (1, 2)]))


# ------------------------------------------------- 矛盾档：撤销能力必须真在、且真被调用


def test_the_undo_retracts_the_new_rows_and_backfills_the_previous_version(monkeypatch):
    """判据④主形：off 态里补偿被真调用——本次新行被撤、上一版原样放回。

    改动之前这一枚必红：调用点站在 ``if mirror is not None:`` 之内，off 态没有那条腿，整支逆序
    补偿不可达，客户看到的是一份只写了一半的正文。
    """
    legacy = _FlakyLegacy([legacy_row("b.txt_0", document=PREVIOUS)], fail_on=["b.txt_1"])
    instance, connection, table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                            dual="off", legacy=legacy)
    _two_batches(monkeypatch)

    with pytest.raises(RuntimeError):
        instance.add_document(DOC, "新一\n新二")

    assert connection.log == [], "off 态不许发一条 SQL（现取 %s）" % connection.log
    assert len(table.rows) == 0, "PG 那一腿本来没参与这一笔"
    assert legacy.deletes == [["b.txt_0"], ["b.txt_0"]], (
        "删旧一次、撤新一次，两枚都得看得见（现取 %s）" % legacy.deletes)
    assert legacy.adds == [["b.txt_0"], ["b.txt_0"]], legacy.adds
    assert list(legacy.rows) == ["b.txt_0"], (
        "补偿没把文档退回写入之前的形状（现取 %s）" % sorted(legacy.rows))
    assert legacy.rows["b.txt_0"]["document"] == PREVIOUS, (
        "放回的是本次写坏的那一半，不是上一版：现取 %r" % legacy.rows["b.txt_0"]["document"])


def test_the_snapshot_is_read_before_the_legacy_delete_in_the_contradictory_state(monkeypatch):
    """判据④前半：撤得干净的前提是手里有货。矛盾档里这一读必须发生。"""
    legacy = LegacyHandle([legacy_row("b.txt_0", document=PREVIOUS)])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              dual="off", legacy=legacy)

    ok, _message = instance.add_document(DOC, "新一\n新二")

    assert ok is True
    assert {"where": {"filename": DOC}, "ids": None} in legacy.gets, legacy.gets
    assert {"where": None, "ids": ["b.txt_0"]} in legacy.gets, (
        "只问了遗留目录有哪些行，没读旧向量快照——就没有任何撤回的凭据：%s" % legacy.gets)


def test_an_unrestorable_reupload_is_refused_and_lands_nothing(monkeypatch):
    """判据④另一形（写之前拒绝）：读不出快照就一笔都不许动，并交出具名错误码。"""
    legacy = _NoSnapshotLegacy([legacy_row("b.txt_0", document=PREVIOUS)])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              dual="off", legacy=legacy)

    with pytest.raises(rt.VectorWriteRejectedError) as caught:
        instance.add_document(DOC, "新一\n新二")

    assert caught.value.reason == rt.REASON_VECTOR_MIRROR_UNAVAILABLE, caught.value.reason
    assert legacy.deletes == [], "拒收之前一个字节都不许动（现取 %s）" % legacy.deletes
    assert legacy.adds == [], "拒收必须发生在写之前，不是写了一半再报错"
    assert list(legacy.rows) == ["b.txt_0"], "上一版必须仍然完整地在库里"


def test_the_refusal_uses_the_in_register_code_and_not_a_new_invention():
    """本单不许新造错误码：拒收交回的那枚码必须仍在在册字典里占一行。

    把 ``REASON_VECTOR_MIRROR_UNAVAILABLE`` 的名字或值改动一个字 ⇒ 这一枚与
    ``test_r21_answer_side_degradation.py::test_the_reason_labels_cover_every_stable_code``
    一起红：一枚管这条路用不用它，一枚管字典里有没有这一行。
    """
    assert rt.REASON_VECTOR_MIRROR_UNAVAILABLE in rt.EMBEDDING_REASON_LABELS
    source = _source()
    for needle in ("拒绝写入向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]",
                   "拒绝删除向量库 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]",
                   "补偿无法忠实还原 [{REASON_VECTOR_MIRROR_UNAVAILABLE}]"):
        assert source.count(needle) == 1, (needle, source.count(needle))


# ---------------------------------------------------- 正控：别把另一档与生产现态一起改了


def test_the_factory_default_state_neither_reads_a_snapshot_nor_retracts_new_rows(monkeypatch,
                                                                                  caplog):
    """正控（出厂默认档 ``chroma`` ＋ off）：本单只治矛盾档，这一档的读写形状一字不改。

    这一档里遗留目录是唯一持有者，而且它没有向量列、读不出快照，所以撤回必须**不做**：撤了
    新行又放不回旧行，等于把这份文档从库里整个抹掉——那比今天更坏。不做也要说出去。
    """
    legacy = _FlakyLegacy([legacy_row("b.txt_0", document=PREVIOUS)], fail_on=["b.txt_1"])
    instance, _connection, _table = _assemble(monkeypatch, backend=None, dual="off",
                                              legacy=legacy)
    _two_batches(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(RuntimeError):
            instance.add_document(DOC, "新一\n新二")

    assert {"where": None, "ids": ["b.txt_0"]} not in legacy.gets, (
        "出厂默认档多读了一次快照，这一档的行为就不是原样了：%s" % legacy.gets)
    assert legacy.deletes == [["b.txt_0"]], (
        "只许有删旧那一次；撤新会把文档抹干净（现取 %s）" % legacy.deletes)
    assert legacy.rows["b.txt_0"]["document"] != PREVIOUS, "上一版本来就删掉了，这里不假装能还原"
    assert rt.REASON_VECTOR_MIRROR_UNAVAILABLE in caplog.text, (
        "撤回被扣下必须点名原因，不许静默：%s" % caplog.text)


def test_the_leg_is_still_rolled_back_when_the_switch_is_on(monkeypatch):
    """正控（生产现态 on）：有条腿时 ``rollback()`` 仍是硬要求，这一格一字未改。"""
    instance, connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND)
    mirror = instance._open_vector_mirror()
    assert mirror is not None

    instance._undo_vector_write(mirror, [], None, stale_deleted=False)

    assert connection.rollbacks == 1, "把腿的回滚摘掉，就不叫「on 态一字不改」了"


def test_a_missing_leg_is_not_reported_as_an_unknown_pg_transaction(monkeypatch, caplog):
    """没有腿就不许谎报「PG 事务状态未知」：那是把 off 态写成一次根本没发生过的 PG 故障。"""
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              dual="off")

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        instance._undo_vector_write(None, [], None, stale_deleted=False)

    assert "PG 事务状态未知" not in caplog.text, caplog.text


# -------------------------------------------------------- 静态牙：这一形不许再长回来


def test_no_compensation_call_site_is_behind_a_pg_leg_gate():
    """两枚调用点都不许要求「那条腿拿得到」；``mirror`` 改名之后判据必须一字不改。"""
    variants = {"原文": _source(),
                "mirror 改名为 leg": re.sub(r"\bmirror\b", "leg", _source())}
    for label, source_text in variants.items():
        sites = _compensation_call_sites(source_text)
        assert len(sites) == 2, "%s：补偿调用点枚数漂了（现取 %d 枚）" % (label, len(sites))
        assert "= self._open_vector_mirror()" in source_text, label
        for site in sites:
            gated = [guard for guard in site["guards"]
                     if any(re.search(r"\b%s\b is not None" % name, guard)
                            for name in site["leg_names"])]
            assert not gated, "%s：%s 的补偿调用点又站回腿门之内 %s" % (label, site["host"], gated)


def _reindent(block, spaces="    "):
    """把一块源码整体再缩进一级：模拟"重新包进 if"那一形。"""
    return "\n".join(spaces + line if line.strip() else line
                      for line in block.split("\n"))


def test_knife_rewrapping_a_call_site_into_a_leg_gate_is_caught():
    """反证刀①：谁把调用点重新包进 ``if mirror is not None:`` ⇒ 静态牙必须抓到。

    变异只发生在内存里的源码副本上，落盘的 ``app/**`` 一个字节都不动（照 R625/R633 的口径）。
    """
    source = _source()
    needle = """            self._undo_vector_write(mirror, written_ids, snapshot,
                                    stale_deleted=stale_deleted)"""
    assert source.count(needle) == 1, source.count(needle)
    rewired = source.replace(needle,
                            "            if mirror is not None:\n" + _reindent(needle), 1)
    sites = _compensation_call_sites(rewired)
    caught = [site for site in sites
              if any(re.search(r"\b%s\b is not None" % name, guard)
                     for guard in site["guards"] for name in site["leg_names"])]
    assert len(caught) == 1, (
        "刀砍下去读数没变，那枚静态牙是空的：%s" % [(site["host"], site["guards"]) for site in sites])
    assert caught[0]["host"] == "add_document", caught[0]


def test_knife_unwrapping_the_pg_rollback_is_caught():
    """反证刀②：把 ``rollback()`` 从腿门里摘出来 ⇒ 腿不在时 ``None.rollback()`` 会被 except 吞
    成一句"PG 事务状态未知"的假故障，静态牙必须抓到这一形。"""
    source = _source()
    needle = """        if mirror is not None:
            try:
                mirror.rollback()"""
    assert source.count(needle) == 1, source.count(needle)
    # 门不是删掉而是**中和**（照 R625 那枚"摘一项判定就当场红"的姿势）：语义上等于"有没有腿都
    # 去 rollback"，而 AST 仍然合法——直接把 if 摘掉会留下一段悬空 except，量不到任何东西。
    mutated = source.replace(needle, """        if True:
            try:
                mirror.rollback()""", 1)
    tree = ast.parse(mutated)
    host = next(node for node in _functions(tree) if node.name == "_undo_vector_write")
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    call = next(node for node in ast.walk(host)
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "rollback")
    guards, current = [], parents.get(id(call))
    while current is not None and current is not host:
        if isinstance(current, ast.If):
            guards.append(" ".join(ast.unparse(current.test).split()))
        current = parents.get(id(current))
    leg_names = _leg_names_in(host)
    assert not any(re.search(r"\b%s\b is not None" % name, guard)
                   for guard in guards for name in leg_names), (
        "变异没生效：rollback() 仍被腿门包着 %s" % guards)


def test_knife_switching_the_contradictory_state_off_hides_the_snapshot_again(monkeypatch):
    """反证刀③：运行时把矛盾档判定摘成恒假 ⇒ 那一读旧向量快照立刻消失，正控当场改读数。

    这一枚证明"off 态真在读快照"挂在判定上，不是挂在别处的偶然形状上。
    """
    legacy = LegacyHandle([legacy_row("b.txt_0", document=PREVIOUS)])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              dual="off", legacy=legacy)
    assert instance._legacy_rows_may_be_shadowed_by_pg() is True

    monkeypatch.setattr(DocumentRetriever, "_legacy_rows_may_be_shadowed_by_pg",
                        lambda self: False)
    emptied = LegacyHandle([legacy_row("b.txt_0", document=PREVIOUS)])
    instance, _connection, _table = _assemble(monkeypatch, backend=indexing.PGVECTOR_BACKEND,
                                              dual="off", legacy=emptied)
    ok, _message = instance.add_document(DOC, "新一\n新二")

    assert ok is True
    assert {"where": None, "ids": ["b.txt_0"]} not in emptied.gets, emptied.gets


def test_the_pg_rollback_is_asked_only_of_a_leg_that_exists():
    """``rollback()`` 必须包在「这条腿非 None」之内：``None.rollback()`` 会被 except 吞成假故障。"""
    tree = ast.parse(_source())
    host = next(node for node in _functions(tree) if node.name == "_undo_vector_write")
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    calls = [node for node in ast.walk(host)
             if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "rollback"]
    assert len(calls) == 1, calls
    leg_names = _leg_names_in(host)
    guards, current = [], parents.get(id(calls[0]))
    while current is not None and current is not host:
        if isinstance(current, ast.If):
            guards.append(" ".join(ast.unparse(current.test).split()))
        current = parents.get(id(current))
    assert any(any(re.search(r"\b%s\b is not None" % name, guard) for name in leg_names)
               for guard in guards), (
        "rollback() 不再被腿门保护：off 态会把 None 的方法调用记成 PG 事务故障（现取 %s）" % guards)


def test_the_chroma_side_compensation_still_only_undoes_a_write_that_happened():
    """在册口径不许被本单稀释：撤新行那一支仍由「本次真写过」与停写判定共同决定。"""
    tree = ast.parse(_source())
    host = next(node for node in _functions(tree) if node.name == "_undo_vector_write")
    tests = [" ".join(ast.unparse(node.test).split()) for node in ast.walk(host)
             if isinstance(node, ast.If)]
    assert any("written_ids" in item and "_writes_go_to_pgvector" in item for item in tests), tests
