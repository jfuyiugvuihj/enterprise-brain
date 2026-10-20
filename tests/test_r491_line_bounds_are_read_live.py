# -*- coding: utf-8 -*-
"""R491 · 判据②：行号档只许现读磁盘，混换行件不许蒙混。

钉住 `scripts/dispatch_preflight.py` 的 (b) 档三件事：
  ① 行数一律现读：末行 IN_RANGE、多一行 OUT_OF_RANGE，两枚数都从磁盘当场派生 ——
     另有一枚 AST 钉，咬「把某枚真实行数写死进尺子」这种偷懒；
  ② 区间两头都核：`:1-末行` 过、`:1-(末行+1)` 红、`:0` 红；
  ③ CRLF／混换行件（跟进单 §92 记过的那坑）按「三种换行全展开」这个最大口径数，
     并在读数里把 MIXED_EOL 与 LF 口径同时说出口，不悄悄选一个尺子。

外加 `line_counts()` 的内存字节表（零盘上依赖）与「件本身读不到就说无法核，不猜」。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"
CHAT = "app/api/v1/chat.py"
MIXED = "docs/handoff/2026-09-15-backend-followup-requests.md"

#: AST 反查用的活件：这几枚的真实行数一旦在尺子里以字面量出现，就是写死了。
PROBE_FILES = (CHAT, "app/rag/pg_store.py", "scripts/dispatch_preflight.py", MIXED)

LF = chr(10)


@pytest.fixture(scope="module")
def r491():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r491_lines", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ruler(r491):
    return r491.Ruler(REPO_ROOT)


def line_rows(report):
    return {row["raw"]: row for row in report["lines"]}


def live_count(ruler, rel):
    return ruler.count_lines(rel)["text"]


# ---------------------------------------------------------------------------
# ① 现读：末行与多一行
# ---------------------------------------------------------------------------

def test_the_live_line_count_agrees_with_an_independent_reading(ruler):
    counts = ruler.count_lines(CHAT)
    body = (REPO_ROOT / CHAT).read_bytes().decode("utf-8").replace(chr(13) + LF, LF).rstrip(LF)
    independent = len(body.split(LF)) if body else 0
    assert counts["text"] == independent, "现读行数与另算一份不符，两枚里必有一枚在编"


def test_the_last_line_is_in_range_and_one_past_it_is_not(r491, ruler):
    last = live_count(ruler, CHAT)
    report = ruler.check("锚点 {0}:{1} 与 {0}:{2}。".format(CHAT, last, last + 1))
    rows = line_rows(report)
    assert rows["{0}:{1}".format(CHAT, last)]["status"] == r491.IN_RANGE
    assert rows["{0}:{1}".format(CHAT, last + 1)]["status"] == r491.OUT_OF_RANGE
    assert report["red"] == 1


def test_each_file_is_measured_by_its_own_live_count(r491, ruler):
    """两枚件各量各的：拿一枚的行数套另一枚（或全局缓存一个数）立刻红。"""
    chat = live_count(ruler, CHAT)
    store = live_count(ruler, "app/rag/pg_store.py")
    assert store < chat, "活样本的相对关系变了，这把钉要换料"
    report = ruler.check("good app/rag/pg_store.py:{0} bad app/rag/pg_store.py:{1}".format(store, chat))
    rows = line_rows(report)
    assert rows["app/rag/pg_store.py:{0}".format(store)]["status"] == r491.IN_RANGE
    assert rows["app/rag/pg_store.py:{0}".format(chat)]["status"] == r491.OUT_OF_RANGE


def test_no_live_line_count_is_hardcoded_inside_the_ruler(ruler):
    literals = set()
    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            literals.add(node.value)
    for rel in PROBE_FILES:
        count = live_count(ruler, rel)
        assert count not in literals, "{0} 的现读行数 {1} 出现在尺子的字面量里 = 写死了".format(rel, count)


# ---------------------------------------------------------------------------
# ② 区间两头
# ---------------------------------------------------------------------------

def test_a_range_is_checked_at_both_endpoints(r491, ruler):
    last = live_count(ruler, CHAT)
    report = ruler.check("好例 {0}:1-2、坏例 {0}:1-{1}、更坏 {0}:0。".format(CHAT, last + 1))
    rows = line_rows(report)
    assert rows[CHAT + ":1-2"]["status"] == r491.IN_RANGE
    assert rows["{0}:1-{1}".format(CHAT, last + 1)]["status"] == r491.OUT_OF_RANGE
    assert rows[CHAT + ":0"]["status"] == r491.OUT_OF_RANGE


def test_the_line_spec_forms_all_reach_the_same_verdict(r491, ruler):
    last = live_count(ruler, CHAT)
    report = ruler.check("三式：{0}：{1}、{0}#L{1}、{0}:{1}:9（列号忽略）。".format(CHAT, last))
    assert len(report["lines"]) == 3, "全角冒号／#L／带列号都该出行号档"
    assert {row["status"] for row in report["lines"]} == {r491.IN_RANGE}
    assert report["red"] == 0


# ---------------------------------------------------------------------------
# ③ 混换行件
# ---------------------------------------------------------------------------

def test_the_mixed_newline_file_is_named_and_counted_by_the_widest_ruler(r491, ruler):
    counts = ruler.count_lines(MIXED)
    assert counts["mixed"] is True, "{0} 的换行早就纯了，这把钉该换个活样本".format(MIXED)
    assert counts["text"] > counts["lf"], "最大口径必须不小于 LF 口径"
    report = ruler.check("证据 {0}:{1}。".format(MIXED, counts["text"]))
    row = line_rows(report)["{0}:{1}".format(MIXED, counts["text"])]["status"]
    assert row == r491.IN_RANGE, "按最大口径能落下的行号不该被更窄的尺子判死"
    assert "MIXED_EOL" in r491.render(ruler.check("证据 {0}:1。".format(MIXED)))


def test_one_line_past_the_widest_ruler_is_red_even_on_a_mixed_file(r491, ruler):
    counts = ruler.count_lines(MIXED)
    report = ruler.check("证据 {0}:{1}。".format(MIXED, counts["text"] + 1))
    row = [item for item in report["lines"] if item["status"] == r491.OUT_OF_RANGE]
    assert len(row) == 1, "超出最大口径还不出红，这档就是摆设"
    assert "MIXED_EOL" in row[0]["detail"]


@pytest.mark.parametrize("data,expected", [
    (b"", 0),
    (b"one", 1),
    (b"one\n", 1),
    (b"one\ntwo", 2),
    (b"one\r\ntwo\r\n", 2),
    (b"one\rtwo", 2),
    (b"a\r\nb\rc\n", 3),
])
def test_the_line_counting_table_on_in_memory_bytes(r491, data, expected):
    assert r491.line_counts(data)["text"] == expected


def test_a_file_that_cannot_be_read_says_unverifiable_not_a_number(r491, tmp_path):
    ruler = r491.Ruler(tmp_path)
    checked = ruler.line_status({"rel": "scripts/never_was.py", "spec": ":12"})
    assert checked[0] == r491.UNVERIFIABLE
    assert "无法核" in checked[3] and "行数" not in checked[3], "读不到就不许端出一个行数"


def test_a_reference_into_a_missing_name_goes_red_once_not_twice(r491, ruler):
    report = ruler.check("新钉 tests/test_r387_teeth.py:44 一枚。")
    assert report["red"] == 1, "件名缺失已经判死，行号档只许报无法核，不许再补一刀"
    assert [row["status"] for row in report["lines"]] == [r491.UNVERIFIABLE]
