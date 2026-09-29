# -*- coding: utf-8 -*-
"""R498 · 第四档要动用 `git check-ignore`：加档之后，「只读」那条闸不许被顺手放宽。

这枚钉不重复 `tests/test_r491_ruler_reads_only_git.py` 那 27 枚参数化拒止，它管另一件事：
**证明那 27 枚是有牙的**。做法=在内存里把白名单真的放宽一枚写动词，用间谍 `subprocess.run`
顶掉真进程，看读数怎么变：

  · 真件（白名单只有三枚查询）：写动词递进去 ⇒ `SourceError` 当场拒，且一枚子进程都不起；
  · 放宽件（白名单里多了一枚写动词）：同一枚动词 ⇒ 不再抛，间谍收到 argv ⇒ 那 27 枚钉必红。

两头各跑一次才叫判据：只跑第一头，永远不知道它是「闸在咬」还是「探针空转」。
全程零真子进程、零写盘（变异只活在内存的影子副本里）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")

WHITELIST_LINE = 'ALLOWED_GIT = ("check-ignore", "log", "ls-files")'
WRITE_VERBS = ("commit", "checkout", "restore", "add", "clean", "reset", "gc", "apply", "worktree")


def load(source, name):
    namespace = {"__file__": str(SCRIPT), "__name__": name}
    exec(compile(source, str(SCRIPT), "exec"), namespace)
    return namespace


@pytest.fixture(scope="module")
def r498():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r498_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeRun:
    """间谍替身：`Ruler.git()` 拿到返回值之后要读 `returncode`/`stdout`，只记 argv 会撕。"""

    def __init__(self):
        self.returncode = 0
        self.stdout = b""
        self.stderr = b""


def _subprocess_slot(module_under_test):
    """真件是 module，放宽件是 `exec` 出来的 namespace dict：两形都得取到那个 `subprocess`。"""
    if isinstance(module_under_test, dict):
        return module_under_test["subprocess"]
    return module_under_test.subprocess


def spy(module_under_test, monkeypatch):
    """把子进程口换成间谍：只记 argv，绝不起真进程。"""
    seen = []

    def fake_run(argv, *a, **k):
        seen.append([str(one) for one in argv])
        return _FakeRun()

    monkeypatch.setattr(_subprocess_slot(module_under_test), "run", fake_run)
    return seen


def test_the_shipped_whitelist_is_three_queries(r498):
    assert r498.ALLOWED_GIT == ("check-ignore", "log", "ls-files")
    assert SOURCE.count(WHITELIST_LINE) == 1, WHITELIST_LINE


@pytest.mark.parametrize("verb", WRITE_VERBS)
def test_the_shipped_gate_refuses_a_write_verb_and_never_spawns(r498, monkeypatch, verb):
    seen = spy(r498, monkeypatch)
    ruler = r498.Ruler(REPO_ROOT)
    with pytest.raises(r498.SourceError) as caught:
        ruler.git(verb, "--help")
    assert "越界子命令" in str(caught.value)
    assert seen == [], "写动词走到子进程了：" + repr(seen)


@pytest.mark.parametrize("verb", WRITE_VERBS)
def test_widening_the_whitelist_would_make_those_pins_red(r498, monkeypatch, verb):
    """同一枚动词，白名单一放宽就**不再抛**并且真的起进程 ⇒ 上面那枚拒止不是空转。"""
    widened = SOURCE.replace(WHITELIST_LINE, WHITELIST_LINE[:-1] + ', "%s")' % verb)
    assert widened != SOURCE, verb + " 没塞进白名单"
    namespace = load(widened, "widened_" + verb)
    seen = spy(namespace, monkeypatch)
    ruler = namespace["Ruler"](REPO_ROOT)
    ruler.git(verb, "--help")                     # 不抛＝放宽件放行了
    assert len(seen) == 1, "放宽件也没起子进程 ⇒ 这枚对照空转"
    assert seen[0][0] == "git" and verb in seen[0], seen[0]


def test_check_ignore_is_the_only_new_verb_and_it_is_a_query(r498):
    """本单往白名单里只加了这一枚，且它不改工作区：`check-ignore -v --stdin` 是纯问话。"""
    assert "check-ignore" not in ("log", "ls-files")
    assert "check-ignore" in SOURCE
    assert "--stdin" in SOURCE, "路径要走 stdin 送，不许拼进 argv（argv 里能藏 --no-index 那一族岔口）"
