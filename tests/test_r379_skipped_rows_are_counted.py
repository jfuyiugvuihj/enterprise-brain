# -*- coding: utf-8 -*-
"""R379 格二：``--summary`` 那句 ``跳过=0`` 必须是从行集合算出来的读数，不是一句写死的主张。

事由（总控 2026-09-27 派工，主树 ``285e265`` 现场复核属实）：从前那一行是
``json.dumps(...) + " 跳过=0（见 note:coverage）"``——那个 0 是打上去的字面量，不参与任何计算。
今天的真值确实也是 0（105 行全落在 照跑/人工盯 两档里），所以**等值测不出它是不是活的**：
把它换回硬编，今天照样绿。本件因此不吃"等于 0"，吃"造一枚非零 ⇒ 打印跟着变"这一把刀。

钉四件事：
  ① 现场那一行不再含 ``跳过=0`` 那枚字面量（换回硬编时静态先红）；
  ② 打印出来的数与"行数 - 两档之和"逐次一致（它是算出来的，且算的是同一枚行集合）；
  ③ 反证刀：把若干行的窗口建议挪到两档之外 ⇒ 打印的跳过数一格一格跟着涨；
  ④ 今天真值为 0 这一事实照旧成立（但它是被算出来的 0，不是被抄上去的 0）。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
ADVICE_LINE = re.compile(r"^advice=(\{.*\}) 跳过=(\d+)（见 note:coverage）$")
HARD = '" 跳过=0'


def load_script(module_name: str, path: Path):
    """按源码文本现编译加载（格四那一族的自律）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def mod():
    return load_script("r379_skip_target", SCRIPT)


def advice_line(module, table, rows) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        module.summary(rows, table, {}, 0, 95, module.budget_table(None),
                       module.min_answer_tokens(), False)
    lines = [line for line in out.getvalue().splitlines() if line.startswith("advice=")]
    assert len(lines) == 1, f"advice 那一行应当恰有一处，实取 {len(lines)}：{lines}"
    return lines[0]


def parsed(line: str):
    match = ADVICE_LINE.match(line)
    assert match, f"那一行的形状变了（字段名/单位/尾巴那句 note:coverage 一枚不许动）：{line!r}"
    return json.loads(match.group(1)), int(match.group(2))


def real_table(mod):
    rows = mod.load_rows()
    return rows, mod.build_table(rows, {})


# ==================== ① 静态：字面量那口井填了 ====================


def test_the_printed_line_no_longer_carries_a_literal_zero():
    text = SCRIPT.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    assert HARD not in text, "摘要里又出现了硬编的 " + HARD + " 半句：那一格不再是读数，是一句主张"
    assert "跳过=" in text, "跳过那一格整个没了：这是删判据不是修判据"


def test_the_count_is_computed_from_the_same_row_set(mod):
    """算式必须吃这一批行：跳过 = len(table) - 两档之和（现场源码里就得看得见这两个名字）。"""
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8-sig"))
    host = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == "summary")
    assigns = [node for node in ast.walk(host)
               if isinstance(node, ast.Assign)
               and any(getattr(t, "id", "") == "skipped" for t in node.targets)]
    assert len(assigns) == 1, f"跳过那一格应当只有一处算法，实取 {len(assigns)} 处"
    text = ast.unparse(assigns[0])
    assert "advice_counts" in text and "len(table)" in text, text


# ==================== ② 打印的数与行集合自相一致 ====================


def test_the_printed_count_is_the_row_set_minus_the_two_buckets(mod):
    rows, table = real_table(mod)
    buckets, skipped = parsed(advice_line(mod, table, rows))
    assert sum(buckets.values()) + skipped == len(table), (buckets, skipped, len(table))
    assert set(buckets) == {"照跑", "人工盯"}, buckets
    assert skipped == len([item for item in table
                           if item["advice"] not in ("照跑", "人工盯")]), skipped


def test_the_real_value_still_reads_zero_today(mod):
    """今天确实没有第三档（这是算出来的 0，不是抄上去的 0）。"""
    rows, table = real_table(mod)
    buckets, skipped = parsed(advice_line(mod, table, rows))
    assert skipped == 0, (buckets, skipped)
    assert sum(buckets.values()) == len(rows) == 105, (buckets, len(rows), len(table))


# ==================== ③ 反证刀：造非零 ⇒ 打印跟着变 ====================


@pytest.mark.parametrize("moved", [1, 2, 7])
def test_rows_outside_the_two_buckets_move_the_printed_count(mod, moved):
    """把若干行的窗口建议挪到两档之外：跳过数必须一格一格跟着涨，不许仍是 0。"""
    rows, table = real_table(mod)
    table = [dict(item) for item in table]
    for index in range(moved):
        table[index]["advice"] = "跳过"
    buckets, skipped = parsed(advice_line(mod, table, rows))
    assert skipped == moved, f"挪走 {moved} 行，打印的跳过仍是 {skipped}"
    assert sum(buckets.values()) == len(table) - moved, buckets


def test_dropping_a_bucketed_row_leaves_the_difference_at_zero(mod):
    """它算的是"行集合与两档之差"，不是行集合本身：两本账一起少一行 ⇒ 跳过仍是 0。

    这一枚是上面那把刀的另一半：少了它，"造非零就涨"可以靠一枚只数行数缺口的哑刀冒充。
    """
    rows, table = real_table(mod)
    buckets, before = parsed(advice_line(mod, table, rows))
    assert before == 0
    kept = [dict(item) for item in table][:-1]
    gone = table[-1]["advice"]
    buckets_after, after = parsed(advice_line(mod, kept, rows))
    assert buckets_after == {k: v - (1 if k == gone else 0) for k, v in buckets.items()}, \
        (buckets, buckets_after, gone)
    assert after == 0, f"两档与行集合同步少一行，跳过却报了 {after}"


def test_the_count_still_says_zero_when_everything_really_is_bucketed(mod):
    """把全部行改写成同一档：跳过必须回 0（这把刀不是一律报非零的哑刀）。"""
    rows, table = real_table(mod)
    table = [dict(item, advice="照跑") for item in table]
    buckets, skipped = parsed(advice_line(mod, table, rows))
    assert skipped == 0 and buckets["照跑"] == len(table), (buckets, skipped)