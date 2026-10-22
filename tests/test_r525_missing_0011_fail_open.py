# -*- coding: utf-8 -*-
"""R525 判据⑤ —— 没跑 0011 的库：跑一问必须 fail-open，且不许把「读不到」冒充成「没有信号」。

真样本是谁
----------

**面 B = 宿主 PG**（``.env`` 里那枚 ``DATABASE_URL``，计划书 §9.3 点名的「5432 上那台野
PostgreSQL」）：它连 ``schema_migrations`` 都没有，0011 的表自然也不存在。产品自己的读取器
打过去拿到的就是下面这枚**真异常与真原文**（``scripts/r525_activity_prior_readout.py``
``--section reader`` 现取）：

    psycopg.errors.UndefinedTable: 关系 "document_activity_signals" 不存在

在册那枚 ``test_r46_activity_signals.py::test_an_unreadable_count_table_leaves_the_order_alone_and_says_why``
用的是自定义 ``RuntimeError``，它验的是「有异常就走 fail-open 这条道」；本件钉的是**这一枚
真异常型与真原文**下的四件事：原序、NULL 语义（命中上压根不出现注记键）、一行日志、不许 500。
两种零（读到零行 / 读不通）在排序上同形、在观测面上必须异形——这一格本件用真库那两枚读数钉。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_r525_real_store_readings import (
    REPO_ROOT,
    REAL_STORE,
    REAL_STORE_OPT_IN,
    ann_rows,
    product_hit_dicts,
)

#: 面 B 现取的异常形状（模块名 / 类名 / 服务端原文首行 / 观测面该落的 reason 码）。
MISSING_0011 = {
    "module": "psycopg.errors",
    "name": "UndefinedTable",
    "first_line": '关系 "document_activity_signals" 不存在',
    "reason": "UndefinedTable",
    "surface": REAL_STORE["surface_b"],
}

LOGGING_PATH = "app.rag.retriever"


def missing_0011_error():
    """用面 B 那枚**真异常型**造一次读失败（不连库也能把这一型的语义钉住）。"""
    import psycopg.errors

    return psycopg.errors.UndefinedTable(
        MISSING_0011["first_line"] + "\nLINE 1: ...ECT filename, accepted_count, "
        "rejected_count FROM document_a...\n" + " " * 60 + "^")


def raiser():
    raise missing_0011_error()


def apply_prior(hits, loader, monkeypatch):
    from app.rag.retriever import DocumentRetriever

    monkeypatch.delenv("RAG_ACTIVITY_PRIOR", raising=False)
    carrier = SimpleNamespace(_activity_prior_loader=loader)
    return DocumentRetriever._apply_activity_prior(carrier, hits)


def snapshot(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def zero_keys(diagnostics: dict) -> dict:
    """只取那四枚参与「两种零」判定的读数（其余三枚是常量，不进对账）。"""
    return {key: diagnostics[key] for key in ("enabled", "source", "reason", "documents")}


# ==================== 判据⑤：fail-open 的四件事 ====================

def test_a_missing_relation_fails_open_instead_of_reaching_the_question(monkeypatch):
    """读不到计数＝不动排序＝空字典，异常不许穿到问答里（不许 500）。"""
    from app.rag import retriever as rt

    monkeypatch.delenv("RAG_ACTIVITY_PRIOR", raising=False)
    rt.reset_activity_priors()
    priors = rt.activity_priors(row_reader=raiser)
    diagnostics = dict(rt.activity_prior_diagnostics())
    rt.reset_activity_priors()

    assert priors == {}, "读不通时必须交回空先验，而不是把异常递给调用方"
    assert diagnostics["source"] == "error"
    assert diagnostics["reason"] == MISSING_0011["reason"], diagnostics
    assert diagnostics["documents"] == 0


def test_the_real_exception_type_and_message_are_the_ones_the_host_server_sends():
    """异常型与原文不许被抄成「任意异常」：型名进观测面，原文进日志。"""
    import psycopg.errors

    error = missing_0011_error()
    assert type(error) is psycopg.errors.UndefinedTable
    assert type(error).__module__ == MISSING_0011["module"]
    assert type(error).__name__ == MISSING_0011["name"]
    assert str(error).splitlines()[0] == MISSING_0011["first_line"]
    #: 它是 ProgrammingError 的子型：任何按 ``Exception`` 兜底的写法都会把它吞成同一个读数，
    #: 所以观测面必须落**型名**而不是落一句通用文案。
    assert issubclass(psycopg.errors.UndefinedTable, psycopg.errors.ProgrammingError)


def test_fail_open_leaves_the_real_ranks_untouched_and_adds_no_annotation(monkeypatch):
    """原序 + NULL 语义：真库 top-40 进去，逐枚原样出来，命中上不出现 ``activity_prior`` 键。"""
    rows = ann_rows(40)
    hits = product_hit_dicts(rows)
    keys_before = [sorted(hit) for hit in hits]
    ranked = apply_prior(hits, raiser, monkeypatch)

    assert ranked is hits, "读不到计数必须交回同一个列表对象"
    assert [hit["source"] for hit in ranked] == [row["filename"] for row in rows]
    assert [hit["chunk_index"] for hit in ranked] == [row["chunk_index"] for row in rows]
    assert [sorted(hit) for hit in ranked] == keys_before, "NULL 语义＝不加注记键，不是补一枚零"
    assert all("activity_prior" not in hit for hit in ranked)


def test_exactly_one_warning_line_is_left_behind(caplog, monkeypatch):
    """一行日志：不许静默，也不许一次问答刷一片。"""
    from app.rag import retriever as rt

    monkeypatch.delenv("RAG_ACTIVITY_PRIOR", raising=False)
    rt.reset_activity_priors()
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        rt.activity_priors(row_reader=raiser)
    rt.reset_activity_priors()

    lines = [record.getMessage() for record in caplog.records
             if "活动信号计数读不到" in record.getMessage()]
    assert len(lines) == 1, caplog.messages
    assert MISSING_0011["first_line"] in lines[0], lines[0]


def test_a_reading_that_returns_zero_rows_is_not_reported_the_same_way():
    """「没有信号」与「读不到信号」两枚读数必须分开（不许冒充成前者）。"""
    from app.rag import retriever as rt

    rt.reset_activity_priors()
    empty_diagnostics = dict((rt.activity_priors(row_reader=lambda: []),
                              dict(rt.activity_prior_diagnostics()))[1])
    rt.reset_activity_priors()
    broken_diagnostics = dict((rt.activity_priors(row_reader=raiser),
                               dict(rt.activity_prior_diagnostics()))[1])
    rt.reset_activity_priors()

    assert empty_diagnostics["source"] == "store" and empty_diagnostics["reason"] == ""
    assert broken_diagnostics["source"] == "error" and broken_diagnostics["reason"] != ""
    assert REAL_STORE["surface_a"]["reader_diagnostics"] == zero_keys(empty_diagnostics), (
        "面 A 的零行读数与本件的零行态必须同形")
    assert REAL_STORE["surface_b"]["reader_diagnostics"] == zero_keys(broken_diagnostics), (
        "面 B 的真读数与本件钉的型名必须是同一枚")


def test_the_backoff_window_does_not_silence_the_next_question_forever(monkeypatch):
    """失败退避只占一个窗口：窗口过后下一问重新真读一次（fail-open 不能变成永久失明）。"""
    from app.rag import retriever as rt

    monkeypatch.delenv("RAG_ACTIVITY_PRIOR", raising=False)
    calls = []

    def counting_reader():
        calls.append(1)
        if len(calls) == 1:
            raise missing_0011_error()
        return [("深度学习入门：基于Python的理论与实现.pdf", 3, 0)]

    rt.reset_activity_priors()
    first = rt.activity_priors(row_reader=counting_reader)
    second = rt.activity_priors(row_reader=counting_reader)
    diagnostics = dict(rt.activity_prior_diagnostics())
    rt.reset_activity_priors()

    assert first == {}, "第一问读不通 ⇒ 空先验，排序不动"
    assert second, "注入 reader 的调用恒真跑（不享退避），第二问必须能读到"
    assert diagnostics["source"] == "store"
    assert len(calls) == 2


def test_a_loader_that_raises_at_the_hub_never_reaches_the_question(monkeypatch, caplog):
    """「不许 500」的另一半：``_apply_activity_prior`` 自己那层兜底。

    读取方（注入的那枚）抛穿时，排序原样交回、异常不上抛、留一行日志——否则一次库故障就会
    决定问答能不能作答，而那正是 R46 裁定 fail-open 时拒绝的形态。
    """
    from app.rag.retriever import DocumentRetriever

    monkeypatch.delenv("RAG_ACTIVITY_PRIOR", raising=False)
    hits = product_hit_dicts(ann_rows(12))

    def exploding_loader():
        raise missing_0011_error()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        ranked = DocumentRetriever._apply_activity_prior(
            SimpleNamespace(_activity_prior_loader=exploding_loader), hits)

    assert ranked is hits, "兜底那一层也必须交回同一个对象"
    assert all("activity_prior" not in hit for hit in ranked)
    lines = [record.getMessage() for record in caplog.records if "先验" in record.getMessage()]
    assert len(lines) == 1, lines


@pytest.mark.skipif(not REAL_STORE_OPT_IN,
                    reason="R525_REAL_STORE=on 才真连面 B（宿主 PG，没跑 0011 的那台）")
def test_the_host_pg_without_0011_really_raises_the_pinned_error(tmp_path):
    """真库复跑：产品自己的读取器打面 B，拿回的必须是本件钉的那枚型与原文。

    驱动器单独一枚子进程（面 B 的 DSN 只走临时文件，不进命令行、不进纸），断言三件事：
    型名、服务端原文首行、观测面落下的 ``reason``。
    """
    dotenv = os.environ.get("R525_DOTENV", "")
    assert dotenv, "R525_REAL_STORE=on 必须同时给 R525_DOTENV"
    from dotenv import dotenv_values

    dsn = str(dotenv_values(dotenv).get("DATABASE_URL", "") or "").strip()
    assert dsn
    #: 产品那枚读取器只在 DSN 没写超时时补 2 s（业主写的数字优先）。这里显式给一枚宽一点的
    #: 数，免得真库复跑被一次偶发的 connect timeout 判成「型名不对」——那是一次量具噪声，
    #: 不是被测行为的读数。
    if "connect_timeout=" not in dsn:
        dsn = dsn + ("&" if "?" in dsn else "?") + "connect_timeout=10"
    import psycopg

    with psycopg.connect(dsn, connect_timeout=3) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.document_activity_signals')").fetchone()[0] is None, (
            "面 B 今天已经跑过 0011 ⇒ 本件的『没跑 0011 的库』样本要换成别的库")

    dsn_file = tmp_path / "dsn.txt"
    dsn_file.write_text(dsn, encoding="utf-8", newline="\n")
    driver = tmp_path / "r525_surface_b_driver.py"
    driver.write_text(
        "import os, sys\n"
        "sys.path.insert(0, %r)\n"
        "os.environ['DATABASE_URL'] = open(%r, encoding='utf-8').read().strip()\n"
        "from app.rag import retriever as rt\n"
        "try:\n"
        "    rt._read_activity_signal_rows()\n"
        "    print('NO-ERROR')\n"
        "except Exception as exc:\n"
        "    print(type(exc).__module__ + '.' + type(exc).__name__)\n"
        "    print(str(exc).splitlines()[0])\n"
        "    priors = rt.activity_priors()\n"
    "    diagnostics = rt.activity_prior_diagnostics()\n"
    "    print(len(priors), diagnostics['source'], diagnostics['reason'],\n"
    "          diagnostics['documents'])\n"
        % (str(REPO_ROOT), str(dsn_file)),
        encoding="utf-8", newline="\n")
    proc = subprocess.run([sys.executable, str(driver)], capture_output=True, text=True,
                          encoding="utf-8", timeout=180,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, proc.stdout + proc.stderr[-500:]
    assert lines[0] == MISSING_0011["module"] + "." + MISSING_0011["name"], lines
    assert lines[1] == MISSING_0011["first_line"], lines
    assert lines[2] == "0 error " + MISSING_0011["reason"] + " 0", lines
    assert proc.returncode == 0, proc.stderr[-500:]
