# -*- coding: utf-8 -*-
"""R379 格一：`MODEL_MIN_ANSWER_TOKENS 现值=… DEFAULT=…` 那两枚数字必须来自两处现场。

事由（总控 2026-09-27 派工，主树 ``285e265`` 现场复核属实）：``scripts/rehearse_eval_window.py``
的 ``--summary`` 从前把同一个运行期读数往两列上打（``现值={floor_now} DEFAULT={floor_now}``），
"DEFAULT" 半句因此永远不会与"现值"不同，也就永远读不出漂移——这是一句空气读数，
与 R361 根治的那一族同形（自己抄自己的读数）。

本件钉三件事：
  ① 两列不同源：现值 = 这一次跑真正拿来算的地板（含 ``--floor``），DEFAULT = 默认值真身；
  ② 反证刀一（改现值）：给一个与默认值不同的地板 ⇒ 两列必须打出不相同的两个数；
  ③ 反证刀二（改默认值真身）：现场那枚字面量一动，等值门必须**当场红**并说"从几变到几"，
     开机闸门必须拦住读数——不许"DEFAULT 静默跟着真身走"当作什么都没发生。

真身住在 ``app/common/model_budget.py``（模块级 ``DEFAULT_MIN_ANSWER_TOKENS``；派工词写的
contracts.py 经现场复核不是它的出处，已按现场写）。影子副本一律落在 tmp 里，
盘上的被跟踪文件一字节都不动（每格用例亲自比 sha256）。
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/rehearse_eval_window.py"
FLOOR_REL = "app/common/model_budget.py"
FLOOR_SRC = "DEFAULT_MIN_ANSWER_TOKENS = 1536"
LINE_HEAD = "MODEL_MIN_ANSWER_TOKENS 现值="
PAIR = re.compile(r"^MODEL_MIN_ANSWER_TOKENS 现值=(\d+)  DEFAULT=(\d+)$")

#: 影子树要装下的现场：预演件读的全部源码（名单从预演件自己抄，一枚不许漏）。
def read_sources(mod) -> tuple:
    return tuple(sorted(set(mod.REPO_RELS.values())))


def load_script(module_name: str, path: Path):
    """按源码文本现编译加载。🔴 不许换回 ``spec.loader.exec_module``（格四那一族雷）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def mod():
    return load_script("r379_floor_target", SCRIPT)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_shadow(tmp_path: Path, mod, edits) -> Path:
    """原样复制现场清单再按 ``(相对路径, 原文, 新文, 处数)`` 改影子；盘上那枚必须一字不动。"""
    root = tmp_path / "shadow"
    before = {rel: sha256(REPO / rel) for rel in read_sources(mod)}
    for rel in read_sources(mod):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    for rel, old, new, times in edits:
        path = root / rel
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        assert text.count(old) == times, f"影子里锚点数不对：{rel} / {old[:40]!r} 实有 {text.count(old)} 处"
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        assert sha256(REPO / rel) == before[rel], f"{rel} 被就地改写了（判据戊的红线）"
    return root


def summary_line(module, rows, floor_now) -> str:
    """让本件真跑一遍 ``--summary``，只取那一行地板读数。"""
    table = module.build_table(rows, {})
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        module.summary(rows, table, {}, 0, 95, module.budget_table(floor_now),
                       floor_now, False)
    lines = [line for line in out.getvalue().splitlines() if line.startswith(LINE_HEAD)]
    assert len(lines) == 1, f"地板那一行应当恰有一处，实取 {len(lines)}：{lines}"
    return lines[0]


# ==================== ① 两列同源 = 空气 ====================


def test_the_default_column_is_not_a_second_copy_of_the_current_value(mod):
    """AST 抓"同一枚变量打两侧"：那一行 print 里 ``floor_now`` 只准出现一次。"""
    import ast
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8-sig"))
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"):
            continue
        text = ast.unparse(node)
        if LINE_HEAD in text:
            hits.append((node.lineno, text))
    assert len(hits) == 1, hits
    lineno, text = hits[0]
    names = [n.id for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Name)]
    assert names.count("floor_now") == 1, (
        f"那一行又只吃一枚变量了（第 {lineno} 行）：{text}")
    assert "MIN_ANSWER_TOKENS_DEFAULT" in text, (
        f"DEFAULT 那一侧不再从登记表取现场读数：第 {lineno} 行 {text}")


def test_the_default_cell_is_registered_as_a_derived_fact(mod):
    """默认值那一格必须是"现场派生"：登记在读数格里，出处是 path::symbol。"""
    assert "MIN_ANSWER_TOKENS_DEFAULT" in mod.FACT_READERS
    anchor = mod.FACT_ANCHORS["MIN_ANSWER_TOKENS_DEFAULT"]
    assert anchor == f"{FLOOR_REL}::DEFAULT_MIN_ANSWER_TOKENS", anchor
    assert not re.search(r":\d+", anchor), f"出处里混进行了号（那是抄本换个地方放）：{anchor}"


def test_the_default_reading_equals_the_live_literal_and_the_runtime_default(mod):
    """今天这一格读的必须是真身本身：AST 读数 == 现算 == 运行期不吃 env 时的那枚默认。"""
    assert mod.FACTS["MIN_ANSWER_TOKENS_DEFAULT"] == mod.read_min_answer_default()
    # 再读一遍必须读出同一个数（读现场对盘上是零副作用）
    assert mod.read_min_answer_default() == mod.read_min_answer_default()
    import os
    saved = os.environ.pop("MODEL_MIN_ANSWER_TOKENS", None)
    try:
        assert mod.min_answer_tokens() == mod.FACTS["MIN_ANSWER_TOKENS_DEFAULT"]
    finally:
        if saved is not None:
            os.environ["MODEL_MIN_ANSWER_TOKENS"] = saved


# ==================== ② 反证刀一：改现值 ⇒ 两列必须不同 ====================


@pytest.mark.parametrize("floor", [2048, 96])
def test_a_different_current_value_prints_two_different_numbers(mod, floor):
    """把这一跑的地板换成别的值：现值跟着动，DEFAULT 不许跟着动。"""
    rows = mod.load_rows()
    line = summary_line(mod, rows, floor)
    match = PAIR.match(line)
    assert match, line
    current, default = int(match.group(1)), int(match.group(2))
    assert current == floor, line
    assert default == mod.FACTS["MIN_ANSWER_TOKENS_DEFAULT"], line
    assert current != default, f"两列还是同一枚数，这半句仍是空气：{line}"


def test_the_env_value_and_the_source_default_are_two_separate_numbers(mod, monkeypatch):
    """宿主 env 改了地板（跑分窗口的真实形状）：摘要必须把"env 的现值"和"代码的默认"并排读出来。"""
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", "2048")
    rows = mod.load_rows()
    line = summary_line(mod, rows, mod.min_answer_tokens())
    assert line == f"{LINE_HEAD}2048  DEFAULT={mod.FACTS['MIN_ANSWER_TOKENS_DEFAULT']}", line


def test_the_shipped_readings_still_print_one_number_twice_because_they_agree(mod):
    """反向取证：不吃 env、不给 --floor 时两列今天确实相等（1536），而且那是**两个读数巧合相等**。"""
    rows = mod.load_rows()
    line = summary_line(mod, rows, mod.min_answer_tokens())
    match = PAIR.match(line)
    assert match and match.group(1) == match.group(2) == "1536", line
    assert line == f"{LINE_HEAD}1536  DEFAULT=1536"


# ==================== ③ 反证刀二：改默认值真身 ⇒ 当场红 ====================


def test_moving_the_default_itself_names_the_cell_and_both_numbers(tmp_path, mod):
    root = build_shadow(tmp_path, mod, [(FLOOR_REL, FLOOR_SRC,
                                        "DEFAULT_MIN_ANSWER_TOKENS = 1200", 1)])
    lines = mod.copy_drift(root)
    assert any("CALIBRATED_FLOOR_TOKENS" in line for line in lines), lines
    assert any("从 1536 变到 1200" in line for line in lines), lines
    gate = mod.guard_facts(mod.load_rows(), root)
    assert any("CALIBRATED_FLOOR_TOKENS" in line for line in gate), \
        f"开机闸门没拦下这一格：{gate}"


def test_the_two_ledgers_split_the_moved_default_between_them(tmp_path, mod):
    """两本账各说一半：漂移账点名"现场的真身从 1536 变到 1200"，等值门点名"标定条件不再成立"。

    抄本自己不会出现在漂移账里——它不读现场，读的是本件身上那枚字面量；它唯一的发声口就是
    ``copy_drift()``。这一枚钉把分工钉死：谁跟着现场动、谁负责拦住不动的人。
    """
    root = build_shadow(tmp_path, mod, [(FLOOR_REL, FLOOR_SRC,
                                        "DEFAULT_MIN_ANSWER_TOKENS = 1200", 1)])
    report = mod.drift_between(REPO, root)
    named = [line.split(" ", 1)[0] for line in report]
    assert named == ["MIN_ANSWER_TOKENS_DEFAULT"], report
    line = report[0]
    assert "[derived]" in line and " -> " in line, line
    assert line.split(": ", 1)[1] == "1536 -> 1200", line
    assert "CALIBRATED_FLOOR_TOKENS" not in line, line
    assert any("CALIBRATED_FLOOR_TOKENS" in item for item in mod.copy_drift(root))


def test_a_moved_default_refuses_to_print_readings(monkeypatch, capsys):
    """量不过尺子就不出读数（判据丁下半场）：这一格漂了就停，不许带病出一份看着正常的摘要。"""
    gate = load_script("r379_floor_gate_target", SCRIPT)
    drift = ("CALIBRATED_FLOOR_TOKENS 抄本与现场 app/common/model_budget.py::"
             "DEFAULT_MIN_ANSWER_TOKENS 不等：从 1536 变到 1200")
    monkeypatch.setattr(gate, "copy_drift", lambda root=None: [drift])
    code = gate.main(["--summary"])
    printed = capsys.readouterr()
    assert code == 2, f"退出码 {code}：报了漂移还继续出读数"
    assert LINE_HEAD not in printed.out, "报了漂移还照样打印地板那一行"
    assert "CALIBRATED_FLOOR_TOKENS" in printed.err and "变到" in printed.err, printed.err


def test_the_calibration_copy_is_registered_on_both_ledgers(mod):
    """这枚抄本必须同时登记在两本账上（判据丁）：只写一处就是没挂号的手抄。"""
    assert "CALIBRATED_FLOOR_TOKENS" in mod.COPY_CELLS
    assert mod.COPIES["CALIBRATED_FLOOR_TOKENS"] == mod.CALIBRATED_FLOOR_TOKENS
    assert mod.COPIES["CALIBRATED_FLOOR_TOKENS"] == mod.read_min_answer_default(), (
        "标定抄本今天已经与现场不等（判据丁该红在闸门里，不是红在这枚钉）")


def test_the_egress_counts_stay_out_of_the_printed_default(mod):
    """这一格不许顺手变成"环境读数"：打印的两枚数都来自本树源码，与宿主有没有 .env 无关。"""
    rows = mod.load_rows()
    line = summary_line(mod, rows, mod.min_answer_tokens())
    assert "1536" in line, f"今天现场的真身不是 1536 了，这枚钉要改读法而不是改数：{line}"