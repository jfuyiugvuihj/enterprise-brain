# -*- coding: utf-8 -*-
r"""R632 缺陷一 —— 读数件自己的 `--help` 必须站得起来，而且要有牙咬住这件事。

## 现场（本席 10-04 一手复现，命令原文 → 实取读数）

    python scripts/eval_lane_readout.py --help
    → ValueError: unsupported format character 'T' (0x54) at index 10   （rc=1）

病根：argparse 的 `HelpFormatter._expand_help` 会对每一枚 help 串做 `%` 展开
（`C:\\Users\\fengx\\anaconda3\\Lib\\argparse.py:640`），而 :134 那行 help 写了
`件所在目录，缺省 %TEMP%\\evalrun`。`--help` 是**唯一**会走到这一格展开的动作，
正常运行时一次都不碰 ⇒ 这类「量具自己站不起来」的病靠人眼与「跑过一遍判据」都看不见。
本仓记过不止一次（R443 抬头就写着「本席补 Windows GBK 控制台下 stdout 强 UTF-8，
否则判读件自己先炸」——同一族：量具自身的可用性没人量）。

## 本件的三格

① 真跑子进程判 rc=0（不是 import 进来调 main：只有子进程才走 argparse 打印那一条路）。
② 转义没把文本吃掉：help 里必须还能看见 `%TEMP%\evalrun` 那一枚原样串。
③ 反证一把：临时根上把 `%%` 退回 `%`，同一枚 `--help` 必须当场再炸一次（正控＝真树 rc=0）。
   🔴 原件前后各核一次 sha256，反证只在副本上动刀。

顺带一格结构钉（不替代①）：AST 扫两枚件的 `add_argument(..., help=...)` 字面串与
模块 docstring，任何一枚留着**没转义**的 `%` 就红 —— 人往后往里加一句路径说明时拦在前面。
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)

#: 本单写域里的两枚读数件（R632 新落的那枚不许复发同一条病）。
READERS = ("scripts/eval_lane_readout.py", "scripts/eval_slo_lane_readout.py")


def run_help(path):
    return subprocess.run([str(PYTHON), str(path), "--help"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def help_string_literals(path):
    """交回 [(件名, 行号, help 字面串)]：只收 add_argument 里写成字面量的 help。"""
    source = Path(path).read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "help" and isinstance(keyword.value, ast.Constant) \
                    and isinstance(keyword.value.value, str):
                found.append((str(path), keyword.value.lineno, keyword.value.value))
    return found


@pytest.mark.parametrize("rel", READERS)
def test_every_named_reader_stands_up_on_help(rel):
    """判据①：两枚件各跑一次真 `--help`，退出码必须是 0（缺陷一那一窗实取是 1）。"""
    result = run_help(REPO_ROOT / rel)
    assert result.returncode == 0, (
        rel + " --help rc=" + str(result.returncode) + " stderr 尾部="
        + result.stderr.strip()[-400:])
    assert "usage:" in result.stdout.lower(), rel + " --help 没打出用法：" + result.stdout[:200]


def test_the_temp_placeholder_is_still_readable_in_help():
    r"""判据②：转义成 %%TEMP%% 之后，--help 交回的那一句里必须还是 %TEMP%\evalrun。"""
    out = run_help(REPO_ROOT / "scripts/eval_lane_readout.py").stdout
    assert "%TEMP%\\evalrun" in out, "--help 里那一枚缺省路径读不回原样：" + out[-600:]
    assert "%%TEMP%%" not in out, "argparse 没展开（多半是双重转义）：" + out[-600:]


def test_no_help_string_carries_an_unescaped_percent():
    """结构钉（拦在前面用）：help 串里不许留没转义的 `%`；docstring 里不许留 `%(prog)`。"""
    offenders = []
    for rel in READERS:
        path = REPO_ROOT / rel
        for item_path, line, text in help_string_literals(path):
            if text.replace("%%", "").count("%"):
                offenders.append("%s:%d argparse 会展开的裸 %%：%r" % (item_path, line, text))
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        if "%(prog)" in doc:
            offenders.append(rel + " 的 docstring 里留着 %%(prog) 形态")
    assert offenders == [], "；".join(offenders)


def test_the_knife_reverting_the_escape_breaks_the_help_again(tmp_path):
    """反证一把：临时根上把 %% 退回 % ⇒ 同一枚 --help 必须当场再炸；真树那一份先是绿的。"""
    original = REPO_ROOT / "scripts/eval_lane_readout.py"
    baseline = hashlib.sha256(original.read_bytes()).hexdigest()
    text = original.read_text(encoding="utf-8")
    needle = r'help="件所在目录，缺省 %%TEMP%%\\evalrun"'
    assert text.count(needle) == 1, "转义那一行不唯一，这枚反证是空的"
    assert run_help(original).returncode == 0, "正控不成立：真树那一份自己就站不起来"

    mutant = text.replace(needle, needle.replace("%%TEMP%%", "%TEMP%"), 1)
    assert mutant != text, "改了个寂寞"
    target = tmp_path / "r632_help_knife.py"
    target.write_text(mutant, encoding="utf-8")
    assert hashlib.sha256(original.read_bytes()).hexdigest() == baseline, "原件被动了"

    result = run_help(target)
    assert result.returncode != 0, "刀下 --help 居然还是绿的 ⇒ 判据① 是枚永真钉"
    assert "unsupported format character" in result.stderr, result.stderr[-500:]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == baseline, "反证跑完原件不是原样"


def test_the_readers_still_refuse_to_invent_numbers_when_run_for_real(tmp_path):
    """顺手一格（同一族病）：`--help` 站得住之后，真跑缺件时必须 rc!=0 且明写取不到。

    量具不能只会打用法：读不到件的那一条路也得走得通（缺陷二那一格的口径就在这）。
    """
    missing = tmp_path / "no-such-window"
    missing.mkdir()
    for rel, flag in (("scripts/eval_lane_readout.py", "--label"),
                      ("scripts/eval_slo_lane_readout.py", "--window")):
        result = subprocess.run([str(PYTHON), str(REPO_ROOT / rel), flag, "r632-none",
                                 "--dir", str(missing)], cwd=str(REPO_ROOT),
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        assert result.returncode != 0, rel + " 缺件还交了 0 ⇒ 把「取不到」读成了过"
        assert "取不到" in result.stdout, rel + " 缺件没明写取不到：" + result.stdout[:300]
        assert "不编数" in result.stdout, rel + " 少了那句不编数"
