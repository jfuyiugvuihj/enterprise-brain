# -*- coding: utf-8 -*-
r"""R361 判据 己 · 对外读数格式与基点 00945a9 同形（run6 要拿这份读数跟 run2-run5 比）。

本单把预演器里 30 处手抄换成了现场派生/等值钉，🔴 但**不许**顺手改打印形状：字段名、
字段顺序、单位、表头、列数、行数一枚都不许动。这一格不能靠"我看了一眼没动"自觉，
所以拿历史版本当**素材**跑一遍（R346：冻结的历史只准当素材读，不许出现在与现场比对的
等号两侧——这里等号两侧都是"格式"，不是"事实"）：

  ① 从 ``git show 00945a9:scripts/rehearse_eval_window.py`` 取出基点那份，进程内 exec
     成第二枚模块（它的 REPO_ROOT 由 ``__file__`` 长出来，量的还是这一棵树）；
  ② 两枚模块吃同一批输入（同 105 题、同一份空出处清单——扫 corpus 太慢，格式与它无关）；
  ③ markdown 表头逐字相等、每行列数与题 id 序列相等；CSV 字段名序列逐字相等；
  ④ --summary 的行数、四枚小节横幅、字段名序列（``^key=``）逐字相等；
  ⑤ 每一行的"数字打码骨架"相等：``5``→``#``、``['chat-02', ...]``→``[…]``。
     值随事实漂（本单正是要让它漂），骨架不许漂。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASE = "00945a9"
SCRIPT_REL = "scripts/rehearse_eval_window.py"
HEADERS = ("=== R107 预演汇总（全部由本件当场从源码算出，出处见文件头）===",
           "=== 档位预算静态结论 ===",
           "=== [推算] 用的算式与参数 ===")
KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")

#: corpus 篇数只是摘要里的一句说明文字，两枚模块吃同一个数才比得出格式。
CORPUS_TXT = 95


def load(module_name: str, path: Path, fake_file: Path | None = None):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    if fake_file is not None:
        module.__dict__["__file__"] = str(fake_file)
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    """(基点那份, 现在这份)。基点那份落在 tmp 里，只为 exec，不参与任何比对事实。"""
    text = subprocess.run(["git", "show", f"{BASE}:{SCRIPT_REL}"], cwd=str(REPO),
                          capture_output=True, check=True).stdout.decode("utf-8")
    path = tmp_path_factory.mktemp("r361_base") / "rehearse_eval_window.py"
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="")
    # __file__ 指回仓里那枚路径：基点那份的 REPO_ROOT 必须长在同一棵树上，否则量的不是同一份现场
    old = load("r361_base_rehearsal", path, fake_file=REPO / SCRIPT_REL)
    now = load("r361_now_rehearsal", REPO / SCRIPT_REL)
    return old, now


def skeleton(line: str) -> str:
    """把"值"抹平，只留格式：数字 -> #，方括号里的 id 清单 -> […]。"""
    out = re.sub(r"\[[^\]]*\]", "[…]", line)
    return re.sub(r"\d+(\.\d+)?", "#", out)


def capture(module, mode: str, rows, missing: dict) -> str:
    table = module.build_table(rows, missing)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if mode == "markdown":
            module.markdown(table, "", 40)
        elif mode == "csv":
            keys = list(table[0].keys())
            print(",".join(keys))
            for item in table:
                print(",".join('"' + str(item[key]).replace('"', '""') + '"' for key in keys))
        else:
            from app.common.model_budget import min_answer_tokens
            module.summary(rows, table, missing, 0, CORPUS_TXT,
                           module.budget_table(None), min_answer_tokens(), False)
    return out.getvalue()




def cells_of(line: str) -> list:
    return [cell for cell in line.split("|")]


# ==================== ③ markdown ====================


def test_the_markdown_header_is_byte_identical(pair):
    old, now = pair
    rows = now.load_rows()
    first_old = capture(old, "markdown", rows, {}).splitlines()[0]
    first_now = capture(now, "markdown", rows, {}).splitlines()[0]
    assert first_now == first_old, f"表头变了：{first_old!r} -> {first_now!r}"
    assert first_now.startswith("| 题 id |") and first_now.endswith("窗口建议 |"), first_now


def test_the_markdown_body_keeps_its_column_count_and_row_order(pair):
    old, now = pair
    rows = now.load_rows()
    body_old = capture(old, "markdown", rows, {}).splitlines()[2:]
    body_now = capture(now, "markdown", rows, {}).splitlines()[2:]
    assert len(body_now) == len(body_old) == len(rows), (len(body_old), len(body_now), len(rows))
    for line_old, line_now in zip(body_old, body_now):
        assert len(cells_of(line_old)) == len(cells_of(line_now)), (line_old, line_now)
        assert cells_of(line_old)[1] == cells_of(line_now)[1], f"题 id 序列漂了：{line_old} / {line_now}"


# ==================== ③ CSV ====================


def test_the_csv_field_names_and_order_are_byte_identical(pair):
    old, now = pair
    rows = now.load_rows()
    head_old = capture(old, "csv", rows, {}).splitlines()[0]
    head_now = capture(now, "csv", rows, {}).splitlines()[0]
    assert head_now == head_old, f"CSV 字段序变了：\n{head_old}\n{head_now}"
    body_old = capture(old, "csv", rows, {}).splitlines()[1:]
    body_now = capture(now, "csv", rows, {}).splitlines()[1:]
    assert len(body_old) == len(body_now) == len(rows)


# ==================== ④⑤ summary ====================


def test_the_summary_field_names_and_order_are_identical(pair):
    old, now = pair
    rows = now.load_rows()
    lines_old = capture(old, "summary", rows, {}).splitlines()
    lines_now = capture(now, "summary", rows, {}).splitlines()
    keys_old = [KEY_LINE.match(line).group(1) for line in lines_old if KEY_LINE.match(line)]
    keys_now = [KEY_LINE.match(line).group(1) for line in lines_now if KEY_LINE.match(line)]
    assert keys_now == keys_old, (
        f"字段名或顺序变了：\n旧 {keys_old}\n新 {keys_now}\n"
        f"多：{sorted(set(keys_now) - set(keys_old))} 少：{sorted(set(keys_old) - set(keys_now))}")
    assert len(keys_old) >= 24, f"字段数少得不像话，这枚钉会空响：{len(keys_old)}"


def test_the_summary_banners_and_line_count_are_identical(pair):
    old, now = pair
    rows = now.load_rows()
    lines_old = capture(old, "summary", rows, {}).splitlines()
    lines_now = capture(now, "summary", rows, {}).splitlines()
    assert len(lines_now) == len(lines_old), (len(lines_old), len(lines_now))
    assert [line for line in lines_now if line.startswith("===")] \
        == [line for line in lines_old if line.startswith("===")] == list(HEADERS)


def test_every_summary_line_keeps_its_digit_masked_skeleton(pair):
    """单位、字段名、句式骨架逐行相等；只有"值"允许随事实漂。"""
    old, now = pair
    rows = now.load_rows()
    lines_old = capture(old, "summary", rows, {}).splitlines()
    lines_now = capture(now, "summary", rows, {}).splitlines()
    drift = [(skeleton(line_old), skeleton(line_now))
             for line_old, line_now in zip(lines_old, lines_now)
             if skeleton(line_old) != skeleton(line_now)]
    assert not drift, "读数骨架漂了（判据 己 停单回报，不许自己拍）：\n" + "\n".join(
        f"  旧 {left}\n  新 {right}" for left, right in drift)


#: 本单允许漂的读数格。每一枚都必须是"事实被改对了"的下游，不是顺手改口径：
#:   rewrite_triggered      —— 旧件抄的是 chat.py 早已换掉的 7 枚前缀表（现场是 11 枚 + 指代词扫描）
#:   rows_with_no_failure_mode —— 上面那格修对之后，chat-08 从"没失败模式"变成"改写换题面"
#:   legs_distribution / advice —— 腿数跟着改写次数走，窗口建议跟着腿数走
#: 另有**唯一一句**出处文字（approval 腿那枚行跨度）由派生锚点打印，值账一动它必须动。
#: 本单允许漂的读数格，每一枚都挂在"事实被改对了"的下游：
#:   rewrite_triggered            —— 旧件抄的是 chat.py 早已换掉的 7 枚前缀表，现场口径是 11 枚 + 指代词扫描
#:   rows_with_no_failure_mode    —— 上面修对后 chat-08 从"没失败模式"变成"改写换题面"
#:   legs_distribution / advice / 平均下界腿数 —— 腿数跟着改写次数走，窗口建议跟着腿数走
#: 另有**唯一一句**出处文字（approval 腿那枚行跨度）由派生锚点打印：值账一动它必须跟着动。
ALLOWED_KEY_DRIFT = {"advice", "rewrite_triggered", "legs_distribution",
                     "rows_with_no_failure_mode", "平均下界腿数"}
PROVENANCE_MARK = "approval 腿记 0 次模型调用（"
#: 摘要里那行中文键名不符 KEY_LINE 的 ASCII 形状，单独接住，不许混进 UNDECLARED。
ANY_KEY = re.compile(r"^([^=\s|]{1,40})=")


def classify(line_old: str, line_now: str) -> str:
    if PROVENANCE_MARK in line_old:
        return "provenance"
    matched = KEY_LINE.match(line_old) or ANY_KEY.match(line_old)
    if matched:
        return matched.group(1)
    return "UNDECLARED:" + line_old[:60]


def test_the_only_changed_summary_readings_are_the_declared_ones(pair):
    """值到底改了哪几行——逐行列出来，不允许有人以后拿"顺手改个口径"混过去。"""
    old, now = pair
    rows = now.load_rows()
    lines_old = capture(old, "summary", rows, {}).splitlines()
    lines_now = capture(now, "summary", rows, {}).splitlines()
    assert len(lines_old) == len(lines_now)
    changed = [(line_old, line_now) for line_old, line_now in zip(lines_old, lines_now)
               if line_old != line_now]
    kinds = [classify(line_old, line_now) for line_old, line_now in changed]
    allowed = ALLOWED_KEY_DRIFT | {"provenance"}
    assert set(kinds) <= allowed, (
        f"除了 {sorted(allowed)} 之外又有读数在漂："
        + chr(10).join(f"  {kind}: {before!r} -> {after!r}"
                       for kind, (before, after) in zip(kinds, changed)))
    # 漂移必须全部是"数字/清单"在动：把数字与方括号内容全部打码，剩下的骨架逐字相等
    for (line_old, line_now) in changed:
        assert skeleton(line_old) == skeleton(line_now) or PROVENANCE_MARK in line_old, (
            f"这一行不止是值在动：{line_old!r} -> {line_now!r}")
    provenance = [(before, after) for (before, after), kind in zip(changed, kinds)
                  if kind == "provenance"]
    assert len(provenance) == 1, f"出处那一句只允许有一处可以动：{provenance}"
    before, after = provenance[0]
    assert re.sub(r"\d+", "", before) == re.sub(r"\d+", "", after), (
        f"出处那句话除了行跨度数字之外还别了字：{before!r} -> {after!r}")
    assert re.search(r"app/agents/orchestrator\.py:\d+-\d+", after), after


def test_the_table_only_loses_or_gains_cells_on_the_declared_rows(pair):
    """逐题表：只允许那些被改写判定修对的题目出现格子变化，其余逐字相等。"""
    old, now = pair
    rows = now.load_rows()
    ids = [str(row["id"]) for row in rows]
    heads_old = [tuple(item[key] for key in old.build_table(rows, {})[0])
                 for item in old.build_table(rows, {})]
    heads_now = [tuple(item[key] for key in now.build_table(rows, {})[0])
                 for item in now.build_table(rows, {})]
    assert len(heads_old) == len(heads_now) == len(ids)
    moved = [ids[i] for i in range(len(ids)) if heads_old[i] != heads_now[i]]
    # 这九题 = "现场判定为追问、旧抄本没判定为追问"那批里真改变了格子的题；
    # chat-02/06/07/12 旧件本来也判成追问，所以一格不动；insight-04 反过来了（旧件误判它为追问）。
    assert moved == ["chat-01", "chat-03", "chat-04", "chat-05", "chat-08", "chat-09",
                     "chat-10", "chat-11", "insight-04"], moved
    rows_old = capture(old, "markdown", rows, {}).splitlines()[2:]
    rows_now = capture(now, "markdown", rows, {}).splitlines()[2:]
    for line_old, line_now in zip(rows_old, rows_now):
        assert len(line_old.split("|")) == len(line_now.split("|")), (line_old, line_now)


def run_mode(module, argv, capsys):
    """把某枚命令行模式的对外读数按行收回来（这两种模式本来就是 stdout-only）。

    ``--switches`` 在现场要 import 同目录的 ``r218_switch_rehearsal``：脚本直跑时 sys.path[0]
    就是 scripts/，被当模块 exec 时不是，所以这里补上那枚目录——量的是同一种跑法，不改脚本。
    """
    scripts = str(REPO / "scripts")
    added = scripts not in sys.path
    if added:
        sys.path.append(scripts)
    try:
        module.main(list(argv))
        return capsys.readouterr().out.splitlines()
    finally:
        if added:
            sys.path.remove(scripts)


def diff_report(old_lines, now_lines):
    rows = []
    for index in range(max(len(old_lines), len(now_lines))):
        before = old_lines[index] if index < len(old_lines) else "<基点没这行>"
        after = now_lines[index] if index < len(now_lines) else "<交付版多出的行>"
        if before != after:
            rows.append(f"L{index + 1} 旧={before!r} 新={after!r}")
    return rows


# ==================== ⑤ 另两种模式也常驻冻结（判据 己）====================


def key_sequence(lines):
    """把每行的"字段名"抠出来：``name=`` 左侧、markdown 的 ``|`` 列位、其余整行前缀。"""
    return [line.split("=", 1)[0] if "=" in line else line[:24] for line in lines]


def test_the_check_29_mode_is_byte_identical_to_the_base(pair, capsys):
    """``--check-29`` 那 5 行 run6 也要跟历史窗口并排看：一枚字节都不许多、不许少。"""
    old, now = pair
    old_lines = run_mode(old, ["--check-29"], capsys)
    capsys.readouterr()
    now_lines = run_mode(now, ["--check-29"], capsys)
    assert old_lines and now_lines, "check-29 模式没打出任何行，比不了格式"
    assert now_lines == old_lines, "\n".join(diff_report(old_lines, now_lines))


def test_the_switches_mode_keeps_its_fields_and_skeleton(pair, capsys):
    """``--switches`` 冻的是**格式**（字段名 + 顺序 + 掩掉数字后的骨架），不是字节。

    为什么这枚只能退一格：第 13 行 ``chroma_hygiene=`` 打的是**进程内累计自观计数**
    （persistent_client_calls / redirect_ledger 长度）。基点那份与交付版在同一进程里跑，
    后跑的那份必然多一枚——实测旧=1、新=2，与格式无关。🔴 这本身是预演件的一处雷：
    同一次窗口里重复调用它，读数会自己漂，见工单"只报不改"清单。
    """
    old, now = pair
    old_lines = run_mode(old, ["--switches"], capsys)
    capsys.readouterr()
    now_lines = run_mode(now, ["--switches"], capsys)
    assert len(old_lines) == len(now_lines), f"switches 行数漂了：{len(old_lines)} -> {len(now_lines)}"
    assert key_sequence(now_lines) == key_sequence(old_lines), (
        "switches 字段名或顺序漂了：\n" + "\n".join(diff_report(key_sequence(old_lines), key_sequence(now_lines))))
    drift = [f"L{i + 1} 旧={skeleton(a)} 新={skeleton(b)}"
             for i, (a, b) in enumerate(zip(old_lines, now_lines))
             if skeleton(a) != skeleton(b) and not a.startswith("chroma_hygiene=")]
    assert not drift, "switches 格式漂了（判据 己：字段/顺序/单位一枚不许动）：\n" + "\n".join(drift)
