# -*- coding: utf-8 -*-
r"""R449 判据①③⑤：先用一台关在笼子里的量具复现「嵌套会话共用 %TEMP%\pytest-of-<user> 会吃掉父件 tmp」，
再证明在册件的真起法已经不往那枚根里落任何东西。

复现口径（全部现场派生，不猜用户名也不猜编号）：

 1. 一枚不带 --basetemp 的嵌套会话收尾时，会在共享根里执行 `cleanup_numbered_dir(keep=3)`：
    编号比 `最大编号 - 3` 旧的目录，只要 `.lock` 已经过期（`_pytest.pathlib.LOCK_TIMEOUT` = 3 天），
    就连目录一起改名成 garbage-* 删掉 —— 父会话正在用的 tmp_path 正好长在某一枚编号目录里。
 2. 等不了三天，所以量具把 `.lock` 的 mtime 倒拨到 4 天之前（`ensure_deletable` 读的就是这枚 mtime）。
    这是复现，不是掩盖：它证的正是「共享根里别人的编号目录会被剪」这一条通道。
 3. 复现一律关在 `PYTEST_DEBUG_TEMPROOT` 笼子里（pytest 官方环境变量，只改默认 basetemp 的根），
    所以本件从不碰真树上的 `%TEMP%\pytest-of-fengx`，也不碰别的会话的 tmp。

判据③要的「摘掉 --basetemp 就得能复现红」，本件用两枚在册件的**真函数**回答：
`tests/test_r163_matrix_teeth.py::_run_nail` 与 `tests/test_r134_chroma_writeback.py::_run_child_pytest`
按源码原样取出来 exec（不 import，因此不碰 app/torch），同一枚笼子里跑两遍：
带 --basetemp 的那一遍共享根一枚新目录都不长、倒拨过的旧目录一枚不少；
把 --basetemp 摘掉的那一遍，被当作父会话 tmp 的目录当场被剪走。

判据②禁止「打串行标记 / 从门里摘出去」：本件不动任何件的调度属性，只读源码 + 起子进程。
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 一枚会用到 tmp_path 的子会话样本：不写文件的话 pytest 根本不会去建编号目录，量具就白站岗。
CHILD_TEST = (
    "def test_r449_probe_child(tmp_path):\n"
    '    (tmp_path / "alive.txt").write_text("x", encoding="utf-8")\n'
)
PROBE_SELECTOR = "test_r449_probe_child"
#: 比 _pytest.pathlib.LOCK_TIMEOUT(3 天) 更老：剪枝就会把这枚锁当成上一场会话的死锁。
BACKDATE_SECONDS = 4 * 24 * 3600
#: tmp_path_retention_count 的默认值：留最近 3 枚，更早的照剪。
KEEP_NEWEST = 3


def r449_nested_basetemp(parent_scratch: Path) -> Path:
    """R449：每一枚嵌套 pytest 会话只用自己的 basetemp，落点必须在父件 scratch 之内。

    与六枚在册件里那台同名同形（形状与落点由 tests/test_r449_nested_pytest_basetemp_contract.py 机检）；
    本件自己也起嵌套会话，所以自己也必须在判据①的形状之内。
    """
    root = Path(parent_scratch) / "r449-nested-basetemp"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="child-", dir=str(root)))


def _quarantined_env(temproot: Path) -> dict:
    """把默认 basetemp 的根关进笼子：复现病只在自己 tmp 里复现。"""
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTEST_DEBUG_TEMPROOT"] = str(temproot)
    return env


def _spawn_shared_root_probe(work_dir: Path, temproot: Path) -> subprocess.CompletedProcess[str]:
    """判据③豁免的那一类：故意不带 --basetemp，因此笼子必须写在这枚函数自己肚子里。

    tests/test_r449_nested_pytest_basetemp_contract.py 认这条豁免的前提是：同一枚函数里
    读得到 PYTEST_DEBUG_TEMPROOT —— 复现病不许真去碰 %TEMP% 里别人那枚共享根。
    """
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTEST_DEBUG_TEMPROOT"] = str(temproot)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "child.py", "-q", "--no-header",
         "-p", "no:randomly", "-p", "no:cacheprovider"],
        cwd=str(work_dir), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=300,
    )


def _spawn_isolated_probe(work_dir: Path, temproot: Path, parent_scratch: Path) -> subprocess.CompletedProcess[str]:
    """判据①要求的形状：子会话 basetemp 收进父 scratch，另加一枚 temproot 笼子做双保险。"""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "child.py", "-q", "--no-header",
         "-p", "no:randomly", "-p", "no:cacheprovider",
         "--basetemp", str(r449_nested_basetemp(parent_scratch))],
        cwd=str(work_dir), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=_quarantined_env(temproot), timeout=300,
    )


def _cage(base: Path) -> Path:
    """PYTEST_DEBUG_TEMPROOT 必须指向一枚**已存在**的目录：pytest 只 mkdir(exist_ok) 不建父级。"""
    temproot = base / "temproot"
    temproot.mkdir(parents=True, exist_ok=True)
    return temproot


def _shared_root(temproot: Path) -> Path:
    """笼子里那枚 pytest-of-<user> 共享根：名字现场读，不猜。"""
    roots = sorted(p for p in temproot.iterdir() if p.is_dir()) if temproot.is_dir() else []
    assert len(roots) == 1, "笼子根里应当恰好长出一枚 pytest-of-*：" + str(roots)
    return roots[0]


def _numbered(root: Path) -> list[int]:
    return sorted(int(p.name[len("pytest-"):]) for p in root.iterdir()
                  if p.name.startswith("pytest-") and p.name[len("pytest-"):].isdigit())


def _stage_stale_sessions(root: Path, base: int, count: int = 5) -> list[Path]:
    """造 count 枚「上一场会话留下的」编号目录，锁全部倒拨到 4 天之前。"""
    staged = []
    for offset in range(1, count + 1):
        session = root / f"pytest-{base + offset}"
        session.mkdir(parents=True)
        lock = session / ".lock"
        lock.write_text(str(os.getpid()), encoding="utf-8")
        stale = time.time() - BACKDATE_SECONDS
        os.utime(lock, (stale, stale))
        staged.append(session)
    return staged


def _site_function(rel: str, names: list[str], inject: dict):
    """把在册件里的函数按源码原样取出来 exec：不 import 那枚件，因此不碰 app/torch。"""
    path = REPO_ROOT / rel
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    namespace: dict = {"os": os, "sys": sys, "subprocess": subprocess, "tempfile": tempfile,
                       "Path": Path, "re": re, "json": json, "shutil": shutil, "time": time,
                       "Sequence": __import__("typing").Sequence,
                       "Callable": __import__("typing").Callable,
                       "List": __import__("typing").List,
                       "Tuple": __import__("typing").Tuple}
    namespace.update(inject)
    picked = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            segment = ast.get_source_segment(text, node)
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
            picked.append((node.name, segment))
    assert sorted(name for name, _ in picked) == sorted(names), f"{rel} 里没取到 {names}"
    return namespace, picked


def _site_constant(rel: str, name: str):
    """读某一枚在册件自己的模块级常量：不手抄它的值，改了口径就跟着改。"""
    path = REPO_ROOT / rel
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{rel} 里没有模块级常量 {name}")


def _strip_basetemp(source: str) -> str:
    stripped, hits = re.subn(r'"--basetemp",\s*str\(r449_nested_basetemp\([^)]*\)\)[,\s]*', "", source)
    if hits != 1:
        raise AssertionError(f"摘刀命中 {hits} 次（要求恰好 1 次）：这枚反证造不出红")
    assert stripped != source
    return stripped


# ============================================================================= 病的复现


def test_r449_nested_session_in_the_shared_root_prunes_a_stale_parent_dir(tmp_path):
    """不带 --basetemp 的嵌套会话收尾会剪共享根里的旧编号目录：父件 tmp 就睡在那里面。"""
    temproot = _cage(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "child.py").write_text(CHILD_TEST, encoding="utf-8")

    calibration = _spawn_shared_root_probe(work, temproot)
    assert calibration.returncode == 0 and "1 passed" in calibration.stdout, (
        "校准会话没跑起来，这台量具读不到任何东西：" + (calibration.stdout + calibration.stderr)[-1500:]
    )
    root = _shared_root(temproot)
    first = _numbered(root)
    assert first, "校准会话没在共享根里留下编号目录：" + str(root)

    staged = _stage_stale_sessions(root, base=max(first))
    parent_tmp = staged[0] / "test_the_parent0"
    parent_tmp.mkdir()
    (parent_tmp / "sentinel.txt").write_text("父会话正在用的 tmp_path", encoding="utf-8")

    eaten = _spawn_shared_root_probe(work, temproot)
    assert eaten.returncode == 0, (eaten.stdout + eaten.stderr)[-1500:]
    assert not staged[0].exists(), "复现失败：嵌套会话收尾没剪掉共享根里的旧编号目录 ⇒ §123 那格病是假的"
    assert not parent_tmp.exists(), "父件式的编号目录被剪了，可里面的 tmp_path 却还在？读数不自洽"
    survivors = _numbered(root)
    newest = max(survivors)
    assert survivors == [newest - KEEP_NEWEST + 1, newest - KEEP_NEWEST + 2, newest], (
        "剪枝口径读不出「只留最近 " + str(KEEP_NEWEST) + " 枚」：" + str(survivors)
    )
    assert all(session.exists() for session in staged[-2:]), (
        "keep 之外那批该剪，最近两枚不该一起被剪：" + str(survivors)
    )


def test_r449_child_basetemp_keeps_the_shared_root_untouched(tmp_path):
    """同一枚笼子、同一批倒拨过的锁，只是子会话自带 --basetemp：共享根里一枚新目录都不长。"""
    temproot = tmp_path / "temproot"
    work = tmp_path / "work"
    scratch = tmp_path / "parent-scratch"
    work.mkdir()
    scratch.mkdir()
    (work / "child.py").write_text(CHILD_TEST, encoding="utf-8")

    calibration = _spawn_isolated_probe(work, temproot, scratch)
    assert calibration.returncode == 0 and "1 passed" in calibration.stdout, (
        (calibration.stdout + calibration.stderr)[-1500:])
    assert not temproot.exists() or not list(temproot.iterdir()), (
        "自带 --basetemp 的会话还是去共享根里报了到：" + str(list(temproot.iterdir())))
    child_home = scratch / "r449-nested-basetemp"
    landed = sorted(p.name for p in child_home.iterdir())
    assert landed, "子会话没落在父 scratch 里，判据①那条路没走通：" + str(child_home)
    inside = list((child_home / landed[0]).glob("test_r449_probe_child*"))
    assert inside, "子会话的 tmp_path 不在它自己的 basetemp 之下：" + str(list((child_home / landed[0]).iterdir()))


# ============================================================ 在册件真起法的端到端取证


def test_r449_r163_run_nail_keeps_the_parent_dir_out_of_the_pruning_queue(tmp_path, monkeypatch):
    """判据③：把 tests/test_r163_matrix_teeth.py 里那台 _run_nail 原样取出来跑 ——
    带 --basetemp 时共享根纹丝不动；摘掉 --basetemp 时它真的会吃掉父件式目录。"""
    temproot = _cage(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "child.py").write_text(CHILD_TEST, encoding="utf-8")
    # 校准用一枚「不带 --basetemp」的会话：只有它会在笼子里长出 pytest-of-<user>，
    # 名字现场读（不猜用户名），后面几枚倒拨过锁的编号目录就拼在这根下面。
    calibration = _spawn_shared_root_probe(work, temproot)
    assert calibration.returncode == 0, (calibration.stdout + calibration.stderr)[-1500:]
    root = _shared_root(temproot)
    staged = _stage_stale_sessions(root, base=max(_numbered(root)))

    namespace, _ = _site_function(
        "tests/test_r163_matrix_teeth.py",
        ["_run_nail", "r449_nested_basetemp"],
        {"NAIL_SELECTOR": PROBE_SELECTOR},
    )
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    run_nail = namespace["_run_nail"]
    numbered_before = _numbered(root)
    green = run_nail(work, "child.py", tmp_path)
    assert green.returncode == 0 and "1 passed" in green.stdout, (
        "摘留 --basetemp 都不该改变子会话的结果：" + (green.stdout + green.stderr)[-1500:])
    assert _numbered(root) == numbered_before, (
        "带 --basetemp 的 _run_nail 仍然在共享根里落了编号目录：" + str(set(_numbered(root)) - set(numbered_before)))
    assert all(session.exists() for session in staged), "父件式目录被剪走了"

    stripped_ns, stripped = _site_function(
        "tests/test_r163_matrix_teeth.py",
        ["_run_nail", "r449_nested_basetemp"],
        {"NAIL_SELECTOR": PROBE_SELECTOR},
    )
    stripped_by_name = dict(stripped)
    exec(compile(_strip_basetemp(stripped_by_name["_run_nail"]), "<r163 _run_nail 摘刀>", "exec"), stripped_ns)
    red = stripped_ns["_run_nail"](work, "child.py", tmp_path)
    assert red.returncode == 0 and "1 passed" in red.stdout, (
        "摘刀只该让子会话改用共享根，不该改变测试结果：" + (red.stdout + red.stderr)[-1500:])
    assert not staged[0].exists(), (
        "反证失败：摘掉 --basetemp 之后那枚会话并没有去剪共享根 ⇒ 本单判据③不成立"
    )


def test_r449_r134_run_child_pytest_keeps_the_parent_dir_out_of_the_pruning_queue(tmp_path, monkeypatch):
    """同一把尺量 tests/test_r134_chroma_writeback.py 的 _run_child_pytest：形状一致才许结案。"""
    temproot = _cage(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    (work / "child.py").write_text(CHILD_TEST, encoding="utf-8")
    # 校准用一枚「不带 --basetemp」的会话：只有它会在笼子里长出 pytest-of-<user>，
    # 名字现场读（不猜用户名），后面几枚倒拨过锁的编号目录就拼在这根下面。
    calibration = _spawn_shared_root_probe(work, temproot)
    assert calibration.returncode == 0, (calibration.stdout + calibration.stderr)[-1500:]
    root = _shared_root(temproot)
    staged = _stage_stale_sessions(root, base=max(_numbered(root)))

    namespace, _ = _site_function(
        "tests/test_r134_chroma_writeback.py", ["_run_child_pytest", "r449_nested_basetemp"], {}
    )
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    numbered_before = _numbered(root)
    green = namespace["_run_child_pytest"](str(work), ["child.py"], _quarantined_env(temproot), tmp_path)
    assert green.returncode == 0 and "1 passed" in green.stdout, (
        (green.stdout + green.stderr)[-1500:])
    assert _numbered(root) == numbered_before, (
        "带 --basetemp 的 _run_child_pytest 仍在共享根里落目录：" + str(set(_numbered(root)) - set(numbered_before)))
    assert all(session.exists() for session in staged), "父件式目录被剪走了"

    stripped_ns, stripped = _site_function(
        "tests/test_r134_chroma_writeback.py", ["_run_child_pytest", "r449_nested_basetemp"], {}
    )
    stripped_by_name = dict(stripped)
    exec(
        compile(_strip_basetemp(stripped_by_name["_run_child_pytest"]), "<r134 _run_child_pytest 摘刀>", "exec"),
        stripped_ns,
    )
    red = stripped_ns["_run_child_pytest"](str(work), ["child.py"], _quarantined_env(temproot), tmp_path)
    assert red.returncode == 0, (red.stdout + red.stderr)[-1500:]
    assert not staged[0].exists(), "反证失败：摘掉 --basetemp 之后那枚会话并没有去剪共享根"


# ==================================================== 四枚影子驱动器的同一格（判据①的「每一处」）


def test_r449_shadow_drivers_keep_their_nested_sessions_inside_the_copy_root(tmp_path, monkeypatch):
    """r349 / r356 / r364 的 run_pytest 与 r305 的 run_tests：原样取出来各跑一枚子会话。

    读数形状不许变（判据③），落点必须在副本根之内（判据①），笼子里一枚编号目录都不许长出来
    —— 这四枚是盘上真刀，平时不在门里跑，所以这里只验它们起子会话那一小段管子。
    """
    temproot = _cage(tmp_path)
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))

    for rel, func_name, targets in (
        ("tests/fixtures/r349_catalog_tail_probe_driver.py", "run_pytest", ["child.py"]),
        ("tests/fixtures/r356_r357_refutation_driver.py", "run_pytest", ["child.py"]),
        ("tests/fixtures/r364_refutation_driver.py", "run_pytest", ["child.py"]),
    ):
        namespace, _ = _site_function(rel, [func_name, "r449_nested_basetemp"], {})
        shadow = tmp_path / rel.split("/")[-1].replace(".py", "") / "shadow"
        (shadow / "child.py").parent.mkdir(parents=True, exist_ok=True)
        (shadow / "child.py").write_text(CHILD_TEST, encoding="utf-8")
        reading = namespace[func_name](shadow, targets)
        # 读数键名逐枚不同（r349 记 passed，r356/r364 记 n_passed）：本件按各自的原样读，不改它们
        passed = reading.get("passed", reading.get("n_passed"))
        assert passed == 1, f"{rel} 的读数形状变了：{reading}"
        assert reading["failed"] == [] and not reading["errored"], f"{rel} 的对照跑红了：{reading}"
        assert (shadow / "r449-nested-basetemp").is_dir(), f"{rel} 没把子会话落在副本根之内"

    namespace, _ = _site_function(
        "tests/fixtures/r305_refutation_driver.py",
        ["run_tests", "r449_nested_basetemp"],
        {"TEST_REL": _site_constant("tests/fixtures/r305_refutation_driver.py", "TEST_REL")},
    )
    shadow = tmp_path / "r305" / "shadow"
    (shadow / "tests").mkdir(parents=True)
    (shadow / "tests" / "test_r305_spreadsheets.py").write_text(CHILD_TEST, encoding="utf-8")
    n_failed, n_names, names, errored, passed = namespace["run_tests"](shadow)
    assert (n_failed, n_names, names, errored, passed) == (0, 0, [], False, 1), (
        "r305 驱动器的读数形状变了：" + str((n_failed, n_names, names, errored, passed)))
    assert (shadow / "r449-nested-basetemp").is_dir(), "r305 没把子会话落在副本根之内"
    assert not list(temproot.iterdir()), (
        "以上任何一枚子会话都该自带 basetemp：笼子里不该长出东西 " + str(list(temproot.iterdir()))
    )
