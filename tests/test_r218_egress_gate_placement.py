# -*- coding: utf-8 -*-
"""R218 判据 ②「门内地雷」的形状钉 + 判据 ④ 反证钉：拦网装在哪儿。

事由（总控 09-24 裁定，第 ② 件归本单修）：
``scripts/rehearse_eval_window.py`` 原来在**模块 import 期**无条件执行 ``_block_network()``
（``dea3ee4`` 第 90 行），把「import 业务代码之前先拦住三条出站路径」这条安全主张实现成了
import 副作用。于是 ``tests/test_r217_strict_unaffordable_form.py:15`` 一句进程内
``from scripts.rehearse_eval_window import budget_table`` 就把桩留给了**同 worker 的别的事**：
``tests/test_r37_report_lane_enqueue.py`` 当场 ``AssertionError: R107 预演件禁止任何网络动作``。

修法（主张一个字不删，只改装载条件）：进程里没有更严的闸门时才拦；conftest 的 R56 端口闸门
已在时让位。本件钉的是三条：
  1. pytest 里 import 预演件 => 桩**不留**（这就是 r37 + r217 同会话能跑绿的机制）；
  2. 脚本模式（``__main__``／非 pytest 的 import）=> 三条出站路径**照样拦得住**；
  3. 反证：把挪位后的守卫摘掉 => 必须有一枚用例红，且红在「脚本模式下没拦网」这一格。
红色不许落在别的事上：副本必须报「没拦」而真件仍报「拦得住」，另两格（D/C）维持原判。
🔴 不许改 test_r217 / conftest / test_r37：那是改断言迁就实现。
"""
import hashlib
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = "scripts/rehearse_eval_window.py"
THREE = ("create_connection", "getaddrinfo", "socket.connect")

#: 探针：在**子进程**（没有 conftest 的世界）里 import 预演件，问它拦没拦，再真试三条出站
#: 路径。三条各试一次，漏一条就报一条，不许用"总之拦住了"糊过去。
#: REPO_HERE / TARGET_HERE 由 _probe 用 repr() 直接替换成字符串字面量（不走 format，
#: 所以子进程不需要 pathlib，也不会有 WindowsPath 泄漏进命名空间）。
PROBE = '''
import json, socket, sys, tempfile
sys.path.insert(0, REPO_HERE)
_tmp = tempfile.gettempdir()
sys.path[:] = [x for x in sys.path if x and x != _tmp]   # %TEMP% 里有别人的 attr.py
sys.argv = ["rehearse_eval_window.py"]
import importlib.util as _u
_spec = _u.spec_from_file_location("probe_target", TARGET_HERE)
m = _u.module_from_spec(_spec)
_spec.loader.exec_module(m)
state = m.egress_guard_state()
tried = {}
for kind, call in (
        ("create_connection", lambda: socket.create_connection(("127.0.0.1", 1), timeout=1)),
        ("getaddrinfo", lambda: socket.getaddrinfo("localhost", 1)),
        ("socket.connect", lambda: socket.socket().connect(("127.0.0.1", 1)))):
    try:
        call()
        tried[kind] = "opened"
    except AssertionError as exc:
        tried[kind] = "blocked:" + str(exc)
    except Exception as exc:
        tried[kind] = "leaked:" + type(exc).__name__
print(json.dumps({"state": state, "tried": tried}, ensure_ascii=False))
'''


def _rehearsal():
    spec = importlib.util.spec_from_file_location(
        "r218_switch_rehearsal_mod", REPO / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _rehearsal()
PIN_FILES = list(R.rehearsal_inputs()) + [TARGET]


def _tree_sha() -> dict:
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in PIN_FILES}


def _probe(script_path: Path) -> dict:
    """跑子进程探针：``script_path`` 是被探的那份预演件（真件或反证副本）。"""
    code = (PROBE.replace("REPO_HERE", repr(str(REPO)))
                  .replace("TARGET_HERE", repr(str(script_path))))
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, timeout=180, cwd=str(REPO))
    line = [l for l in out.stdout.splitlines() if l.startswith("{")]
    assert line, f"探针没出读数：stdout={out.stdout[-400:]} stderr={out.stderr[-800:]}"
    return json.loads(line[-1])


def test_importing_the_rehearsal_under_pytest_leaves_sockets_real():
    """机制本身：pytest 里 import 预演件之后，三条出站路径必须是**真**的（不是桩）。

    这一条就是「r37 + r217 同会话跑绿」的因由 —— 桩不该由 import 这个动作留给别人。
    """
    spec = importlib.util.spec_from_file_location("r218_gate_target", REPO / TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = module.egress_guard_state()
    assert state["conftest_gate_loaded"] is True
    assert state["guarded"] is False, "本件又在 import 期下刀了：同会话的别的事会被打死"
    assert state["stubbed"] is False
    for name in THREE:
        fn = socket.socket.connect if name == "socket.connect" else getattr(socket, name)
        assert fn.__name__ != "_boom", f"{name} 仍是桩：同 worker 的 r37 会被打死"


def test_script_mode_still_blocks_all_three_egress_paths():
    """安全主张不许删：非 pytest 的脚本模式下，三条路径必须一条条被拦。"""
    report = _probe(REPO / TARGET)
    assert report["state"]["conftest_gate_loaded"] is False
    assert report["state"]["guarded"] is True, f"脚本模式下没拦网：{report['state']}"
    for kind in THREE:
        assert report["tried"][kind].startswith("blocked:"), (
            f"脚本模式下 {kind} 没被拦住（实际 {report['tried'][kind]!r}）—— 挪位置挪掉了主张")
    assert "R107 预演件禁止任何网络动作" in report["tried"]["create_connection"]


def test_the_r218_module_shares_one_shape():
    """同一枚修法只留一份口径：r218 预演件与 R107 那件的状态读数同形。"""
    report = _probe(REPO / "scripts" / "r218_switch_rehearsal.py")
    assert set(report["state"]) == {"guarded", "conftest_gate_loaded", "stubbed"}
    assert report["state"]["guarded"] is True
    assert all(report["tried"][k].startswith("blocked:") for k in report["tried"]), report["tried"]


def test_counter_proof_removing_the_moved_guard_goes_red_on_the_blocking_cell(tmp_path):
    """反证钉（判据 ④）：摘掉挪位后的守卫 => 必须红在「脚本模式下没拦网」这一格。"""
    root = tmp_path / "overlay"
    for rel in PIN_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    copy = root / TARGET
    original = copy.read_text(encoding="utf-8")
    mutated = original.replace("if not _conftest_gate_loaded():\n    _block_network()\n"
                               "    EGRESS_GUARDED = True",
                               "if False:\n    _block_network()\n    EGRESS_GUARDED = True")
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    copy.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    report = _probe(copy)
    assert report["state"]["guarded"] is False
    unblocked = [k for k, v in report["tried"].items() if not v.startswith("blocked:")]
    assert unblocked == list(THREE), report["tried"]

    # 同会话里真件必须仍然拦得住：证明红是因"摘掉守卫"，不是探针自己坏了
    assert _probe(REPO / TARGET)["state"]["guarded"] is True
    # 红只落这一格：D 格与 C 格对着同一枚临时根维持原判
    assert R.cell_lane_flip(root)["readings"]["frontend_unhandled_final"] == ["dead"]
    assert R.cell_cache_hit(root)["readings"]["mismatched_legs"] == []

    assert _tree_sha() == before