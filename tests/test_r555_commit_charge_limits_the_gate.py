# -*- coding: utf-8 -*-
r"""R555：`run_gate.py` 选并发数必须两者取小（物理空闲 **与** 提交电荷），且任何退化都要留痕。

欠的形状（跟进单 §141 第二节）：`fit_workers()` 原来只读 `ullAvailPhys`，而门上真实发生过的失败形状是
**电荷耗尽**——09-30 08:10 那一遍按物理空闲选了 `-n 6`（每枚 worker ≈2 GB），起跑之后被一枚外来 CUDA
训练进程把提交电荷吃掉，xdist worker 死于 `0xe0000008`，88-89% 处一片 `E`，master 最后被 kill
（凭据：看板 §4EE 第一节，`.tmpfix/gate_shift6.log` 199 行现读）。物理空闲那把尺看不见这件事。

本机现取读数（写死在本件 docstring 里的是**当时那一刻**，判据① 要求交回读数而不是要求它永真）：
2026-10-01 23:2x，phys 15.9 GB／commit 26.2 GB ⇒ 受限者是物理空闲，自选 `-n 7`。
09-30 那一遍：phys 够／commit 不够 ⇒ 按本件口径应当只选到 2-3 枚，而不是 6 枚。

口径三条，逐条机检：
① `memory_headroom_gb()` 交回**两个数**，任一问不到就是 -1.0（不许拿 0.0 冒充"还有很多"）。
② `fit_workers()` 交回 `(枚数, 原因串)`：枚数按两者取小、每枚 4 GB 起算、封顶 8；
   电荷不足要明写 limiter 是 commit charge；问不到数不许静默（原因串必须自报家门）。
③ `main()` 必须把那枚原因串打进 `[run_gate]` 那一行——留痕是判据④ 的全部，散文不算。

反证（判据③ 的牙）：本件带一枚影子副本道，把 `headroom = min(free_phys, free_page)` 摘成
`headroom = free_phys`（＝回到本单之前的姿势），同一个 phys=20／commit=5 的案例当场从 2 枚变成 8 枚；
再把"问不到数"那格的原因串摘空，`main()` 的留痕当场红。两把刀都只碰 tmp 里的副本，真树零写口。
"""

from __future__ import annotations

import ctypes
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_gate.py"

_GB_PER_WORKER = 2.0  # what one worker of this suite commits (module docstring: budget ~2 GB)
_SERIAL_FLOOR = 4.0   # below this there is no room for even one worker plus the master


def _load(source_text: str, name: str, tmp_path: Path):
    path = tmp_path / f"{name}.py"
    path.write_text(source_text, encoding="utf-8", newline="\r\n")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gate():
    spec = importlib.util.spec_from_file_location("eb_r555_run_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _R555Stat(ctypes.Structure):
    """A real MEMORYSTATUSEX layout with two known figures baked in.

    The structure type is genuine on purpose: the function under test calls ``ctypes.sizeof`` on
    the class it instantiates, so a duck-typed stand-in makes the call raise and the -1.0 branch
    answer for the wrong reason -- the stub would prove nothing about the two figures.
    """

    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]

    def __init__(self):
        super().__init__()
        self.ullTotalPhys = 32 * 1024 ** 3
        self.ullAvailPhys = int(11.5 * 1024 ** 3)
        self.ullTotalPageFile = 40 * 1024 ** 3
        self.ullAvailPageFile = int(19.3 * 1024 ** 3)


def _stub_kernel32(gate, monkeypatch, answered):
    """Point this loaded copy at the stub structure and a kernel32 that answers as instructed.

    ``monkeypatch`` restores ``ctypes.windll`` at teardown; the copy is re-imported per test, so
    nothing here edits scripts/run_gate.py or leaks a fake binding into another module.
    """
    monkeypatch.setattr(gate.ctypes, "windll", type("W", (), {"kernel32": type(
        "K", (), {"GlobalMemoryStatusEx": staticmethod(lambda _b: answered)})()})(), raising=False)
    monkeypatch.setattr(gate, "MemoryStatusEx", _R555Stat)


def test_headroom_answers_two_numbers_not_one(gate, monkeypatch):
    """判据①：交回 (phys, commit)，两个数各自独立，缺一枚都不许假装另一枚够用。"""
    _stub_kernel32(gate, monkeypatch, answered=True)
    phys, commit = gate.memory_headroom_gb()
    # 19.3 is not binary-exact once it has been through bytes -> GiB division, so the pair is
    # compared with a tolerance; what matters is that both figures come back, independently.
    assert (phys, commit) == pytest.approx((11.5, 19.3), abs=1e-6), (
        "两个读数必须原样交回，不是把电荷当成物理空闲的别名")
    _stub_kernel32(gate, monkeypatch, answered=False)
    assert gate.memory_headroom_gb() == (-1.0, -1.0), "问不到必须报 -1.0，不许报 0.0 或只缺一枚"
    assert gate.free_memory_gb() == -1.0, "旧的单值把手必须跟着一起说问不到"


def test_commit_charge_is_the_binding_limit(gate, monkeypatch):
    """判据②：电荷比物理空闲小时，枚数由电荷决定，且原因串要点名 commit charge。"""
    monkeypatch.setattr(gate, "memory_headroom_gb", lambda: (20.0, 5.0))
    workers, why = gate.fit_workers()
    assert workers == int(5.0 // _GB_PER_WORKER), (
        f"phys 20 GB 会选出 8 枚、commit 5 GB 只养得起 2 枚；现在选了 {workers} 枚——电荷那一格没吃进去")
    assert "commit charge" in why and "headroom 5.0" in why and "20.0 GB" in why, why


def test_free_physical_is_the_binding_limit(gate, monkeypatch):
    """判据② 反向：物理空闲小时由它决定，原因串点名 free physical，不许一口咬定电荷。"""
    monkeypatch.setattr(gate, "memory_headroom_gb", lambda: (7.0, 30.0))
    workers, why = gate.fit_workers()
    assert workers == int(7.0 // _GB_PER_WORKER), workers
    assert "free physical" in why and "7.0" in why and "30.0" in why, why


def test_narrow_headroom_goes_serial_but_leaves_a_trace(gate, monkeypatch):
    """判据④：电荷不足一枚 worker 时退到串行，但原因串必须自报为什么退，不许静默。"""
    monkeypatch.setattr(gate, "memory_headroom_gb", lambda: (30.0, 3.0))
    workers, why = gate.fit_workers()
    assert workers == 1, workers
    assert "serial" in why and "commit charge" in why and "headroom 3.0" in why, why


def test_unanswerable_question_is_not_silent(gate, monkeypatch):
    """判据④：问不到数时不许退成 -n 1 而不留痕，原因串必须写明是问不到的那格。"""
    monkeypatch.setattr(gate, "memory_headroom_gb", lambda: (-1.0, -1.0))
    workers, why = gate.fit_workers()
    assert workers == 4, workers
    assert "no answer" in why, why


def test_main_prints_the_reason_on_the_run_gate_line(gate, monkeypatch, capsys):
    """判据③：留痕在 `main()` 那一行里，不是在注释或 docstring 里。"""
    seen = {}

    def fake_call(cmd, cwd=None):
        seen["cmd"] = list(cmd)
        return 0

    monkeypatch.setattr(gate.sys, "argv", ["run_gate.py"])
    monkeypatch.setattr(gate, "subprocess", type("S", (), {"call": staticmethod(fake_call)})())
    monkeypatch.setattr(gate, "memory_headroom_gb", lambda: (20.0, 5.0))
    assert gate.main() == 0
    out = capsys.readouterr().out
    assert "[run_gate] xdist -n 2 --dist loadfile [" in out, out
    assert "commit charge" in out, "选了 2 枚的理由必须跟着那一行出去，不然事后无从归因"


@pytest.mark.parametrize("needle,replacement,expect_workers", [
    ("headroom = min(free_phys, free_page)", "headroom = free_phys", 8),
])
def test_knife_removing_the_commit_term_goes_red(tmp_path, needle, replacement, expect_workers):
    """反证刀一（判据③）：把两者取小摘回"只看物理空闲"，同一案例当场从 2 枚变 8 枚。"""
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count(needle) == 1, "刀口必须先证明它切得动：真源里这句必须恰一枚"
    mutated = src.replace(needle, replacement)
    assert mutated != src, "摘除没生效，这把刀是空转刀"
    gate = _load(mutated, "eb_r555_shadow_phys_only", tmp_path)
    gate.memory_headroom_gb = lambda: (20.0, 5.0)
    workers, why = gate.fit_workers()
    assert workers == expect_workers, (
        f"摘掉电荷之后本该选出 {expect_workers} 枚（这才是 09-30 那遍的病），实取 {workers}")
    assert "headroom 20.0" in why, (
        f"摘掉电荷的副本应把物理空闲当 headroom 报出来，实取：{why}")
    live = _load(src, "eb_r555_shadow_control", tmp_path)
    live.memory_headroom_gb = lambda: (20.0, 5.0)
    assert "headroom 5.0" in live.fit_workers()[1], "对照组：真源同案例必须报电荷那枚数"


def test_knife_silencing_the_no_answer_reason_goes_red(tmp_path):
    """反证刀二（判据③/④）：把"问不到数"那格的原因串摘空，留痕那一格必须红。"""
    src = SCRIPT.read_text(encoding="utf-8")
    needle = '"GlobalMemoryStatusEx gave no answer "'
    assert src.count(needle) == 1, "刀口必须先证明它切得动"
    mutated = src.replace(needle, '"" ')
    assert mutated != src
    gate = _load(mutated, "eb_r555_shadow_silent", tmp_path)
    gate.memory_headroom_gb = lambda: (-1.0, -1.0)
    workers, why = gate.fit_workers()
    assert workers == 4
    assert "no answer" not in why
    # 真源必须仍带着那句话，否则本单第④格当场红：这里比的是盘上那一版，不是副本。
    assert "no answer" in src, "真源把留痕摘了就是一枚假刀"
