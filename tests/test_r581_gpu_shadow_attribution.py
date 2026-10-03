"""R581 的牙：GPU「Docker vGPU 影子」三分归因（CLEAN／ATTRIBUTED／FOREIGN，问不到落 UNMEASURED）。

量的两件件：新真源 `scripts/r581_gpu_attribution.py`，以及在册闸
`scripts/r530_run10_window_preflight.py` 的 `gpu_apps` 格怎么用它。
全程离线：`classify()` 是纯函数，取数腿拿假 runner 喂，**不碰 docker／nvidia-smi／模型**。

为什么值得钉（判据逐格）：
 ① 三分法必须真三分，且归因链是「影子 → 容器 → 计算 pid 同名同槽」的**可失败断言**——
    逐腿摘一腿都必须红（`test_d`），不是「看起来不像负载」；
 ② 🔴「问不到」一律落 UNMEASURED 且拦窗（`test_e`／`test_d` 的四腿半边／`test_i` 的在册映射）——
    本仓 09-28「两班假零」写过的那条教训，不许在这格复活；
 ③ 默认行为不许放松：真有人在抢 GPU 的形状必须仍 FAIL（`test_c`／`test_f`／`test_g`／`test_l`，
    进程内造一枚非容器所有的计算 pid 交回 FOREIGN）；
 ④ 归因真源只此一处（`test_j` 钉在册件里不许留第二份同形判定，`test_b` 钉取数腿只读）；
 ⑤ `--json` 的键不许消失（`test_k`：check/status/detail 一枚不少，verdict 为新增）。

本机 10-03 现取的真形状（下面几枚读数就是照它造的，逐字）：
  宿主   4, [Insufficient Permissions], GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab, [N/A]
  容器   50983, [Not Found], 同槽 / 51023, [Not Found], 同槽
         readlink /proc/50983/exe -> /usr/lib/ollama/llama-server
  宿主进程表：ProcessId=4 -> Name=System，ExecutablePath 空
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


attr = _load("r581_gpu_attribution", "scripts" + chr(47) + "r581_gpu_attribution.py")
gate = _load("r530_run10_window_preflight", "scripts" + chr(47) + "r530_run10_window_preflight.py")

BS = chr(92)
GPU = "GPU-0e7f33ad-cc4a-7a1a-e9a4-7dd69f9032ab"
OTHER_GPU = "GPU-00000000-1111-2222-3333-444444444444"
HOST_PY = "C:" + BS + "Users" + BS + "fengx" + BS + "anaconda3" + BS + "python.exe"
MAIN_TREE_PY = str(ROOT.parent / "企业智脑" / ".venv" / "Scripts" / "python.exe")
CONTAINER = "enterprise-brain-ollama-1"
LLAMA = "/usr/lib/ollama/llama-server"


def _host(pid="4", exe="[Insufficient Permissions]", gpu=GPU, mem="[N/A]"):
    return attr.ComputeRow(pid=pid, exe=exe, gpu_uuid=gpu, used_memory=mem, source="host")


def _cont(pid="50983", exe="[Not Found]", gpu=GPU):
    return attr.ComputeRow(pid=pid, exe=exe, gpu_uuid=gpu, used_memory="[N/A]", source="container")


def _system_proc(pid="4"):
    return attr.HostProcess(pid=pid, name="System", exe_path="", resolved=True)


def _container_state(rows=None, exe_names=None, docker_ok=True, running=True, query_ok=True):
    return attr.ContainerState(
        requested=CONTAINER, name=CONTAINER, docker_ok=docker_ok, running=running, query_ok=query_ok,
        rows=[_cont()] if rows is None else rows,
        exe_names={"50983": LLAMA} if exe_names is None else exe_names,
        notes=[] if (docker_ok and running and query_ok) else ["rc!=0"])


def _attributed_state():
    """本机此刻的真读数：一枚宿主匿名行 + 容器侧两枚同槽计算进程，名字靠 /proc 补出来。"""
    return attr.GpuState(
        host_rows=[_host()], host_seen=True,
        host_processes={"4": _system_proc()},
        container=_container_state(rows=[_cont(), _cont(pid="51023")]))


# ── ① 取数腿：真读数解析与「问不到」的边界 ────────────────────────────────────

def test_a_live_nvidia_rows_parse_into_pid_name_slot():
    text = ("4, [Insufficient Permissions], " + GPU + ", [N/A]" + chr(13) + chr(10)
            + "13640, " + HOST_PY + ", " + GPU + ", [N/A]" + chr(13) + chr(10))
    rows = attr.parse_rows(text)
    assert [row.pid for row in rows] == ["4", "13640"], rows
    assert rows[0].anonymous is True and rows[1].anonymous is False
    assert rows[0].gpu_uuid == GPU and rows[0].used_memory == "[N/A]"


def test_b_collect_only_asks_read_only_questions_and_skips_docker_when_idle():
    calls = []

    def runner(cmd, timeout=180):
        calls.append([str(part) for part in cmd])
        text = " ".join(calls[-1])
        if calls[-1][0] == "nvidia-smi":
            return 0, ""
        raise AssertionError("干净机上不该再多问一句：" + text)

    idle = attr.collect(run=runner)
    assert len(calls) == 1 and calls[0][0] == "nvidia-smi", calls
    assert attr.classify(idle).status == attr.CLEAN

    calls.clear()

    def runner2(cmd, timeout=180):
        argv = [str(part) for part in cmd]
        calls.append(argv)
        text = " ".join(argv)
        if argv[0] == "nvidia-smi":
            return 0, "4, [Insufficient Permissions], " + GPU + ", [N/A]" + chr(10)
        if argv[:2] == ["docker", "ps"]:
            return 0, CONTAINER + chr(10)
        if argv[:2] == ["docker", "exec"]:
            if "nvidia-smi" in text:
                return 0, "50983, [Not Found], " + GPU + ", [N/A]" + chr(10)
            return 0, LLAMA + chr(10)
        if argv[0] == "powershell":
            return 0, json.dumps({"Name": "System", "ExecutablePath": None})
        raise AssertionError("没料到的命令：" + text)

    state = attr.collect(run=runner2)
    assert attr.classify(state).status == attr.ATTRIBUTED
    for argv in calls:
        joined = " ".join(argv).lower()
        assert argv[0] in ("nvidia-smi", "docker", "powershell"), argv
        if argv[0] == "docker":
            assert argv[1] in ("ps", "exec", "inspect"), argv
            assert not any(flag in argv for flag in ("up", "down", "restart", "kill", "rm", "build", "commit", "push")), argv
            assert "--force-recreate" not in joined, argv
        if argv[0] == "powershell":
            assert "get-ciminstance" in joined and "win32_process" in joined, argv
            assert not any(token in joined for token in ("stop-process", "taskkill", "invoke-webrequest", "curl")), argv
        assert "run_gate.py" not in joined and "-n " not in joined, argv


# ── ② 三分法本体 ─────────────────────────────────────────────────────────────

def test_c_zero_rows_is_clean_and_an_anaconda_row_is_still_foreign():
    idle = attr.GpuState(host_rows=[], host_seen=True)
    verdict = attr.classify(idle)
    assert verdict.status == attr.CLEAN and verdict.blocking is False
    assert "0 枚" in verdict.detail

    grabbed = attr.GpuState(host_rows=[_host(pid="13640", exe=HOST_PY)], host_seen=True)
    verdict = attr.classify(grabbed)
    assert verdict.status == attr.FOREIGN and verdict.blocking is True
    assert "13640" in verdict.detail and "p95" in verdict.detail

    mixed = attr.GpuState(host_rows=[_host(pid="7", exe=MAIN_TREE_PY),
                                     _host(pid="13640", exe=HOST_PY)], host_seen=True)
    assert attr.classify(mixed).status == attr.FOREIGN

    # 名册只认「树」，不认文件名里带 ollama：一枚装在宿主程序目录的原生 ollama.exe 不是自家容器
    native = attr.GpuState(host_rows=[_host(pid="88", exe="C:" + BS + "Program Files" + BS + "ollama" + BS + "ollama.exe")],
                           host_seen=True)
    assert attr.classify(native).status == attr.FOREIGN, "自家名册被放宽到文件名了"
    assert attr.is_repo_path(MAIN_TREE_PY) and not attr.is_repo_path("C:" + BS + "Program Files" + BS + "ollama" + BS + "ollama.exe")


def test_d_attribution_needs_all_four_legs_and_each_leg_can_fail_it():
    """判据 1＋3 的核心：少一腿就红，且红是拦窗的红（FOREIGN／UNMEASURED），绝不掉回 CLEAN。"""
    good = _attributed_state()
    verdict = attr.classify(good)
    assert verdict.status == attr.ATTRIBUTED
    assert [leg.ident for leg in verdict.legs] == ["L1", "L2", "L3", "L4"], verdict.legs
    assert all(leg.ok for leg in verdict.legs)
    assert LLAMA in verdict.detail and GPU in verdict.detail
    assert "不许因此翻绿" in verdict.detail

    broken = {
        "摘掉 L1（宿主进程表问不到这枚影子 pid）": lambda state: state.host_processes.clear(),
        "摘掉 L2（容器侧整枚没取证）": lambda state: setattr(state, "container", None),
        "摘掉 L3（影子换到容器不认领的槽上）": lambda state: state.host_rows[0].__setattr__("gpu_uuid", OTHER_GPU),
        "摘掉 L4（容器侧一枚名字都叫不出）": lambda state: state.container.exe_names.clear(),
    }
    for why, saboteur in broken.items():
        victim = _attributed_state()
        saboteur(victim)
        result = attr.classify(victim)
        assert result.status != attr.ATTRIBUTED, (why, result.status)
        assert result.status != attr.CLEAN, (why, "影子还在，绝不许写 CLEAN")
        assert result.blocking is True, (why, result.status)
        assert result.status in (attr.FOREIGN, attr.UNMEASURED), (why, result.status)


def test_e_unaskable_legs_never_become_clean():
    """判据 2：取不到证据一律 UNMEASURED——「问不到」不许冒充「没有」。"""
    cases = {
        "nvidia-smi 跑不成": attr.GpuState(host_rows=[], host_seen=False, host_note="nvidia-smi rc=2"),
        "影子 pid 点不到名": attr.GpuState(host_rows=[_host()], host_seen=True,
                                    host_processes={"4": attr.HostProcess("4", "", "", False)},
                                    container=_container_state()),
        "影子行没有槽位字段": attr.GpuState(host_rows=[_host(gpu="")], host_seen=True,
                                    host_processes={"4": _system_proc()}, container=_container_state()),
        "容器内 nvidia-smi 非零": attr.GpuState(host_rows=[_host()], host_seen=True,
                                        host_processes={"4": _system_proc()},
                                        container=_container_state(query_ok=False, rows=[], exe_names={})),
        "容器侧叫不出任何名字": attr.GpuState(host_rows=[_host()], host_seen=True,
                                      host_processes={"4": _system_proc()},
                                      container=_container_state(exe_names={})),
        "影子在位但容器侧整枚没查": attr.GpuState(host_rows=[_host()], host_seen=True,
                                        host_processes={"4": _system_proc()}, container=None),
    }
    for why, state in cases.items():
        verdict = attr.classify(state)
        assert verdict.status == attr.UNMEASURED, (why, verdict.status, verdict.detail)
        assert verdict.blocking is True, why
        assert "问不到" in verdict.detail or "没取证" in verdict.detail, (why, verdict.detail)


def test_f_shadow_the_container_does_not_own_is_foreign_not_unmeasured():
    """判据 3 指定的那一形：进程内造一枚**非容器所有**的计算 pid —— 必须 FOREIGN（有人在抢）。"""
    other_slot = attr.GpuState(host_rows=[_host(pid="40400", gpu=OTHER_GPU)], host_seen=True,
                               host_processes={"40400": attr.HostProcess("40400", "System", "", True)},
                               container=_container_state())
    verdict = attr.classify(other_slot)
    assert verdict.status == attr.FOREIGN, verdict.detail
    assert "非容器所有的计算 pid" in verdict.detail and OTHER_GPU in verdict.detail

    nobody_home = attr.GpuState(host_rows=[_host()], host_seen=True,
                                host_processes={"4": _system_proc()},
                                container=_container_state(running=False, rows=[], exe_names={}))
    verdict = attr.classify(nobody_home)
    assert verdict.status == attr.FOREIGN and "无人认领" in verdict.detail, verdict.detail

    silent_container = attr.GpuState(host_rows=[_host()], host_seen=True,
                                     host_processes={"4": _system_proc()},
                                     container=_container_state(rows=[], exe_names={}))
    verdict = attr.classify(silent_container)
    assert verdict.status == attr.FOREIGN and "0 枚" in verdict.detail, verdict.detail


def test_g_shadow_that_resolves_to_a_user_process_is_foreign():
    """影子反解出一枚仓库外可执行文件／名册外的进程名 ⇒ 不是自家 vGPU 影子。"""
    hiding = attr.GpuState(
        host_rows=[_host()], host_seen=True,
        host_processes={"4": attr.HostProcess("4", "python.exe", HOST_PY, True)},
        container=_container_state())
    verdict = attr.classify(hiding)
    assert verdict.status == attr.FOREIGN and "反解出仓库外可执行文件" in verdict.detail, verdict.detail

    odd_name = attr.GpuState(
        host_rows=[_host()], host_seen=True,
        host_processes={"4": attr.HostProcess("4", "nightmare_trainer.exe", "", True)},
        container=_container_state())
    verdict = attr.classify(odd_name)
    assert verdict.status == attr.FOREIGN and "名册" in verdict.detail, verdict.detail


def test_h_attribute_is_the_shared_exit_surface():
    """两元组出口是给别的调用点用的（队列那套以后改调它），别各自再写一份。"""
    status, detail = attr.attribute(_attributed_state())
    assert status == attr.ATTRIBUTED and detail.startswith("ATTRIBUTED")
    assert attr.BLOCKING == (attr.FOREIGN, attr.UNMEASURED)
    assert attr.PASSING == (attr.CLEAN, attr.ATTRIBUTED)
    assert set(attr.BLOCKING) | set(attr.PASSING) == {"CLEAN", "ATTRIBUTED", "FOREIGN", "UNMEASURED"}


# ── ③ 在册闸：只做映射，不留第二套判定 ───────────────────────────────────────

def test_i_preflight_delegates_and_maps_the_three_way():
    def row_status(state):
        snap = gate.Snapshot(provenance_rc=0, provenance_text="", cache_rc=0, processes=[],
                             create_times={}, gpu_apps=[], gpu_seen=True, eval_tree_dirty=0,
                             eval_tree_ahead=0, eval_tree_found=True, env_flags={}, gpu_state=state)
        return {name: (status, detail) for name, status, detail in gate.evaluate(snap, 90.0)}["gpu_apps"]

    status, detail = row_status(_attributed_state())
    assert status == gate.PASS and detail.startswith("ATTRIBUTED"), detail
    status, detail = row_status(attr.GpuState(host_rows=[], host_seen=True))
    assert status == gate.PASS and detail.startswith("CLEAN"), detail
    status, detail = row_status(attr.GpuState(host_rows=[_host(pid="13640", exe=HOST_PY)], host_seen=True))
    assert status == gate.FAIL and detail.startswith("FOREIGN"), detail
    status, detail = row_status(attr.GpuState(host_rows=[_host()], host_seen=True))
    assert status == gate.FAIL and detail.startswith("UNMEASURED"), detail


def test_j_registered_gate_keeps_no_second_gpu_judgement():
    """判据 4：归因真源只写一处。在册件里不许再留一份同形判定（匿名名册、名册、三分支）。"""
    src = (ROOT / "scripts" / "r530_run10_window_preflight.py").read_text(encoding="utf-8")
    assert "import r581_gpu_attribution" in src, "在册件没调真源"
    assert "gpu.classify(" in src, "在册件没有把判定交给真源"
    lowered = src.lower()
    assert "insufficient permissions" not in lowered, "匿名名册回到在册件里了"
    assert "not found" not in lowered, "同上"
    assert "UNREADABLE" not in src and "SHADOW_HOST_OWNERS" not in src
    assert "snap.gpu_apps" in src and src.count("snap.gpu_apps") == 1, src.count("snap.gpu_apps")
    assert 'rows.append(("gpu_apps", PASS' not in src or "verdict.status in gpu.PASSING" in src
    assert "--query-compute-apps" not in src, "在册件自己拼 nvidia-smi 查询＝第二份取数口径"


def test_k_json_surface_keeps_every_key_and_adds_the_verdict(monkeypatch, capsys):
    """判据 5 的 `--json` 半边：check/status/detail 一枚不许少，verdict 是新增。"""
    snap = gate.Snapshot(provenance_rc=0, provenance_text="", cache_rc=0,
                         processes=[{"ProcessId": 11, "ExecutablePath": MAIN_TREE_PY,
                                     "CommandLine": "scripts" + chr(47) + "window_keep_awake.py --loop"}],
                         create_times={}, gpu_apps=[], gpu_seen=True, eval_tree_dirty=0,
                         eval_tree_ahead=0, eval_tree_found=True,
                         env_flags={"VECTOR_DUAL_WRITE": "on", "REPORT_LANE_VIA_QUEUE": "on"},
                         gpu_state=attr.GpuState(host_rows=[], host_seen=True))
    monkeypatch.setattr(gate, "collect", lambda: (snap, False))
    monkeypatch.setattr(gate, "keep_awake_freshness", lambda path, now: (True, "stamp 12 s 前续过"))
    assert gate.main(["--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    names = [row["check"] for row in rows]
    assert names == ["provenance", "answer_cache", "keep_awake", "gpu_apps",
                     "foreign_python", "eval_tree", "env_flags"], names
    for row in rows:
        assert {"check", "status", "detail"} <= set(row), row
        assert {"check", "status", "detail", "verdict"} == set(row), row
    gpu_row = [row for row in rows if row["check"] == "gpu_apps"][0]
    assert gpu_row["verdict"] == attr.CLEAN and gpu_row["status"] == gate.PASS
    assert all(row["verdict"] == row["status"] for row in rows if row["check"] != "gpu_apps")


def test_l_foreign_shape_still_refuses_the_window_end_to_end(monkeypatch):
    """默认行为不许放松：真有人在抢 GPU 时，退出码仍非零、仍点名 pid。"""
    snap = gate.Snapshot(provenance_rc=0, provenance_text="", cache_rc=0, processes=[], create_times={},
                         gpu_apps=[], gpu_seen=True, eval_tree_dirty=0, eval_tree_ahead=0,
                         eval_tree_found=True, env_flags={},
                         gpu_state=attr.GpuState(host_rows=[_host(pid="13640", exe=HOST_PY)], host_seen=True))
    monkeypatch.setattr(gate, "collect", lambda: (snap, False))
    assert gate.main([]) == 1
    assert gate.evaluate(snap, 90.0) and snap.gpu_state.host_rows[0].pid == "13640"


def test_m_shadow_whose_host_path_is_in_a_repo_tree_attributes():
    """L1 的另一条正证：nvidia-smi 读不出名，但宿主进程表把这枚 pid 点到自家树里的可执行文件。"""
    state = attr.GpuState(
        host_rows=[_host(pid="4242")], host_seen=True,
        host_processes={"4242": attr.HostProcess("4242", "python.exe", MAIN_TREE_PY, True)},
        container=_container_state(rows=[_cont(pid="50983", exe="[Not Found]")]));
    verdict = attr.classify(state)
    assert verdict.status == attr.ATTRIBUTED, verdict.detail
    assert MAIN_TREE_PY in verdict.detail and "自家树里" in verdict.detail, verdict.detail
