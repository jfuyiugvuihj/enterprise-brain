# -*- coding: utf-8 -*-
"""R491 · 硬约束钉：这把尺子只许读，不许起白名单外的进程、不许写一个字。

派工词写「除 `git log` / `git ls-files` / `rg` 之外不许起别的子进程；零网络；零写库」。
本件把这句话从自觉变成钉：
  ① 静态（AST）：import 只许在 stdlib 白名单里，网络/HTTP/DB/文件复制那一族一枚都不许出现；
     `subprocess` 只许 `run`，且 argv 首元素必须是字面量 "git"；不许出现 `open(` 与任何写盘 API；
  ② 动态：把 `subprocess.run` 换成留痕的假手，跑一遍完整读数，逐条核它只调过 git log / git ls-files；
  ③ 白名单本身：尺子内部那道 `ALLOWED_GIT` 闸要真咬人 —— 递一枚 `git status` 进去必须当场拒。

另附一枚口径钉：docs 证据窗只吃 docs/**，不许顺手把 tests/ 的自述当账面证据。
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ALLOWED_IMPORTS = {"__future__", "argparse", "io", "json", "os", "re", "subprocess", "sys", "pathlib"}
BANNED_WORDS = (
    "socket", "urllib", "http", "requests", "shutil", "sqlite3", "psycopg", "redis",
    "chromadb", "Popen", "os.system", "os.popen", "os.exec", "os.spawn", "os.remove",
    "os.rename", "os.replace", "os.unlink", "mkdir", "write_text", "write_bytes",
    "touch", "truncate", "eval(", "exec(",
)


@pytest.fixture(scope="module")
def r491():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r491_ro", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


# ---------------------------------------------------------------------------
# ① 静态
# ---------------------------------------------------------------------------

def test_the_import_list_is_bounded(r491):
    assert imported_names(TREE) <= ALLOWED_IMPORTS, "多出来的 import 得先证明它不写盘不联网"
    assert r491.ALLOWED_GIT == ("log", "ls-files")


def test_no_write_or_network_api_appears_in_the_source():
    haystack = SOURCE
    for word in BANNED_WORDS:
        assert word not in haystack, "尺子里出现了越界字样：" + word


def test_the_only_spawn_is_git_run_with_a_literal_argv():
    calls = [node for node in ast.walk(TREE)
             if isinstance(node, ast.Call) and dotted(node.func).startswith("subprocess.")]
    assert calls, "一把只读尺子居然一次进程都没起？那在册表从哪来"
    for call in calls:
        assert dotted(call.func) == "subprocess.run", "越界的 spawn：" + dotted(call.func)
        first = call.args[0]
        while isinstance(first, ast.BinOp):
            first = first.left
        assert isinstance(first, ast.Tuple) and isinstance(first.elts[0], ast.Constant)
        assert first.elts[0].value == "git", "argv 首元素必须是字面量 git"


def test_the_ruler_never_opens_a_file_handle():
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call):
            assert dotted(node.func) != "open", "读盘只许 read_bytes，不许开句柄"


# ---------------------------------------------------------------------------
# ② 动态留痕
# ---------------------------------------------------------------------------

def test_every_process_the_ruler_starts_is_a_read_only_git_call(r491, monkeypatch):
    seen = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append(tuple(str(one) for one in argv))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(r491.subprocess, "run", spy)
    report = r491.Ruler(REPO_ROOT).check("核 tests/test_r387_label_ruler_teeth.py 与 R478 R888 两枚号。")
    assert report["numbers"], "读数没跑出来，这枚钉就成了空转"
    assert seen, "一把吃 git 的尺子一枚进程都没起，说明它在撒谎"
    for argv in seen:
        assert argv[0] == "git", "越界进程：" + " ".join(argv)
        sub = argv[argv.index("-C") + 2] if "-C" in argv else argv[1]
        assert sub in r491.ALLOWED_GIT, "越界子命令：" + " ".join(argv)


# ---------------------------------------------------------------------------
# ③ 白名单闸真咬人
# ---------------------------------------------------------------------------

def test_a_disallowed_git_subcommand_is_refused(r491):
    ruler = r491.Ruler(REPO_ROOT)
    with pytest.raises(r491.SourceError) as caught:
        ruler.git("status", "--porcelain")
    assert "越界子命令" in str(caught.value)


def test_the_ledger_layer_is_git_and_it_is_not_a_disk_listing(r491):
    """双层核验的第一层必须真是 git 的账：在册件在里面，编译产物不许混进来。"""
    tracked = r491.Ruler(REPO_ROOT).tracked()
    assert "conftest.py" in tracked and "pyproject.toml" in tracked
    assert not [one for one in tracked if one.startswith("__pycache__/") or one.endswith(".pyc")]
    assert "docs/handoff/2026-09-15-backend-followup-requests.md" in tracked


def test_the_docs_window_does_not_borrow_tests_as_paper_evidence(r491):
    ruler = r491.Ruler(REPO_ROOT)
    index = ruler.paper_index()
    files = {rel for group in index.values() for rel in group}
    assert files, "docs/** 一枚号都没读到？"
    assert all(rel.startswith("docs/") for rel in files)
    assert not [rel for rel in files if rel.startswith("tests/") or rel.startswith("scripts/")]
