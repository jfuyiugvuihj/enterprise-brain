"""P-20 开窗前置闸的牙（R530·总控自修）。

这枚件量的是 scripts/r530_run10_window_preflight.py 的 evaluate() 与退出码契约，全部离线：
不碰 Redis、不碰 docker、不碰 nvidia-smi、不碰模型。

为什么值得钉：本仓已经连续三班把「开窗条件」靠人肉现取，然后取错——09-28 把取不到口令读成
「缓存已清」（两班假零）、09-29 夜沿用快到期的 keep-awake 冻了整夜、09-30 早上拿一枚与项目无关的
外来 CUDA 负载当干净机去量 p95。闸的作用就是把这三件事变成非零退出码。

判据（逐枚对应下面的用例）：
 ① 干净机全绿，七格一枚不少（正控——防止「一律 FAIL」这种假严也算通过）；
 ② K1 外来 GPU 计算进程 -> gpu_apps 红（A(1) 的 p95 读数不可采信）；
 ③ K2 空进程表 -> keep_awake 与 foreign_python 双红（🔴 本班刚抓到的那一形：量不到不等于干净）；
 ④ K3 keep-awake 只剩十分钟 -> 红（不许沿用快到期那枚）；
 ⑤ K4 量具自己 rc=2 -> 该格红而不是绿；
 ⑥ K5 缺 REPORT_LANE_VIA_QUEUE / 跑分树脏 -> 各自红；
 ⑦ K6 反向：Agent 自己的 pytest 子工与 execnet bootstrap 不许报成外来负载（防过严误杀开窗）。
退出码契约：0 全绿 / 1 至少一格 FAIL / 2 量具没跑成——2 永远不是「已通过」。
"""
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r530_run10_window_preflight", ROOT / "scripts" / "r530_run10_window_preflight.py"
)
gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = gate
_SPEC.loader.exec_module(gate)

REPO_PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
FOREIGN_PY = "C:" + chr(92) + "Users" + chr(92) + "fengx" + chr(92) + "anaconda3" + chr(92) + "python.exe"
CHECK_NAMES = {"provenance", "answer_cache", "keep_awake", "gpu_apps", "foreign_python", "eval_tree", "env_flags"}


def _proc(pid, exe, cmd):
    return {"ProcessId": pid, "ExecutablePath": exe, "CommandLine": cmd}


def _clean(now=None):
    """一台确实可以开窗的机器该有的读数。"""
    stamp = now if now is not None else time.time()
    return gate.Snapshot(
        provenance_rc=0,
        provenance_text="verdict       : MATCH",
        cache_rc=0,
        processes=[_proc(11, REPO_PY, REPO_PY + " keep_awake.py window 600")],
        create_times={11: stamp - 60},
        gpu_apps=[{"pid": "11", "exe": REPO_PY}],
        gpu_seen=True,
        eval_tree_dirty=0,
        eval_tree_ahead=0,
        eval_tree_found=True,
        env_flags={"VECTOR_DUAL_WRITE": "on", "REPORT_LANE_VIA_QUEUE": "on"},
        now=stamp,
    )


def _status(snap, need=300.0):
    return {name: state for name, state, _ in gate.evaluate(snap, need)}


def test_a_clean_machine_passes_every_cell():
    rows = gate.evaluate(_clean(), 300.0)
    names = {name for name, _, _ in rows}
    assert names == CHECK_NAMES, names
    bad = [row for row in rows if row[1] != gate.PASS]
    assert bad == [], bad


def test_b_foreign_gpu_app_fails_the_latency_cell():
    snap = _clean()
    snap.gpu_apps = [{"pid": "11", "exe": REPO_PY}, {"pid": "99", "exe": FOREIGN_PY}]
    assert _status(snap)["gpu_apps"] == gate.FAIL
    assert _status(_clean())["gpu_apps"] == gate.PASS


def test_c_an_empty_process_table_is_never_read_as_clean():
    snap = _clean()
    snap.processes = []
    status = _status(snap)
    assert status["keep_awake"] == gate.FAIL
    assert status["foreign_python"] == gate.FAIL


def test_d_an_expiring_keep_awake_does_not_cover_the_window():
    stamp = time.time()
    snap = _clean(stamp)
    snap.processes = [_proc(11, REPO_PY, REPO_PY + " keep_awake.py window 240")]
    snap.create_times = {11: stamp - 235 * 60}
    assert _status(snap, 300.0)["keep_awake"] == gate.FAIL
    assert _status(snap, 3.0)["keep_awake"] == gate.PASS


def test_e_a_broken_ruler_never_reports_pass():
    snap = _clean()
    snap.cache_rc = 2
    snap.provenance_rc = 2
    status = _status(snap)
    assert status["answer_cache"] == gate.FAIL
    assert status["provenance"] == gate.FAIL


def test_f_missing_switch_and_dirty_eval_tree_each_fail():
    snap = _clean()
    snap.env_flags = {"VECTOR_DUAL_WRITE": "on"}
    assert _status(snap)["env_flags"] == gate.FAIL

    other = _clean()
    other.eval_tree_dirty = 3
    assert _status(other)["eval_tree"] == gate.FAIL

    third = _clean()
    third.eval_tree_ahead = 2
    assert _status(third)["eval_tree"] == gate.FAIL


def test_g_agents_own_test_children_are_not_foreign_load():
    snap = _clean()
    snap.processes = [
        _proc(11, REPO_PY, REPO_PY + " keep_awake.py window 600"),
        _proc(21, FOREIGN_PY, FOREIGN_PY + " -m pytest tests/test_r523_migration_pair.py -q"),
        _proc(22, FOREIGN_PY, FOREIGN_PY + ' -u -c "import sys;exec(eval(sys.stdin.readline()))"'),
        _proc(23, FOREIGN_PY, FOREIGN_PY + ' "-c" "from multiprocessing.spawn import spawn_main"'),
    ]
    assert _status(snap)["foreign_python"] == gate.PASS
    assert _status(snap)["keep_awake"] == gate.PASS


def test_h_one_fail_cell_flips_the_exit_code(monkeypatch):
    monkeypatch.setattr(gate, "collect", lambda: (_clean(), False))
    assert gate.main([]) == 0
    broken = _clean()
    broken.cache_rc = 1
    monkeypatch.setattr(gate, "collect", lambda: (broken, False))
    assert gate.main([]) == 1


def test_i_tool_breakage_without_a_fail_cell_is_two_not_zero(monkeypatch):
    snap = _clean()
    snap.eval_tree_found = False
    monkeypatch.setattr(gate, "collect", lambda: (snap, False))
    assert gate.main([]) == 1

    monkeypatch.setattr(gate, "collect", lambda: (_clean(), True))
    assert gate.main(["--json"]) == 2
    quiet = _clean()
    quiet.processes = []
    monkeypatch.setattr(gate, "collect", lambda: (quiet, False))
    assert gate.main([]) == 1


def test_k_a_keep_awake_past_its_own_deadline_is_not_coverage():
    """正是本班现取的那枚形状：07:50 起的 420 分钟档，到 14:50 就没了，别看它 nominal 还很长。"""
    stamp = time.time()
    snap = _clean(stamp)
    snap.processes = [_proc(11, REPO_PY, REPO_PY + " keep_awake.py window 420")]
    snap.create_times = {11: stamp - 430 * 60}
    assert _status(snap, 300.0)["keep_awake"] == gate.FAIL
    fresh = _clean(stamp)
    fresh.processes = [_proc(11, REPO_PY, REPO_PY + " keep_awake.py window 420")]
    fresh.create_times = {11: stamp - 10 * 60}
    assert _status(fresh, 300.0)["keep_awake"] == gate.PASS


def test_j_in_repo_is_case_insensitive_on_the_root():
    assert gate.in_repo(REPO_PY) is True
    assert gate.in_repo(REPO_PY.upper()) is True
    assert gate.in_repo(FOREIGN_PY) is False
    assert gate.in_repo("") is False

def test_r530_create_time_collects_with_one_clock_not_the_dotnet_epoch(monkeypatch):
    """采集腿的牙（R549·总控自修）：本机时区_once_把 keep-awake 剩余时长虚报了 480 min。

    两道：形状钉不许 `.Ticks` 与 .NET epoch 常数回到这件里；行为钉喂一枚「已经跑了 3600 s」
    的假 PS 读数，要求换回的 epoch 落在 `now - 3600` 两秒之内——时区若回来，差值是 8 小时级。
    """
    import inspect

    src = inspect.getsource(gate.read_create_time)
    assert ".Ticks" not in src, "采集腿又拿本地 Ticks 当 UTC 换了"
    assert "621355968000000000" not in src, ".NET epoch 常数回来了，keep-awake 又要虚报 8 小时"

    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return 0, "3600\r\n"

    monkeypatch.setattr(gate, "run", fake_run)
    monkeypatch.setattr(gate.time, "time", lambda: 1800000000.0)
    started = gate.read_create_time(4242)
    assert abs(started - (1800000000.0 - 3600.0)) <= 2.0, started
    assert calls, "采集腿没走 PS 量具——读不到不等于零"
