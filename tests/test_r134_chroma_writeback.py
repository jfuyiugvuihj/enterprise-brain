"""跟进单 R134：测试进程一次都不许写脏被跟踪的 ./chroma_db。

两个成因，分别钉：套件内的入口（脚本里的 ROOT/chroma_db 常量、--chroma-dir 的
相对默认值、CHROMA_DIR 指回树内、显式传仓库路径），以及「根本不经这套钉子」的起法
（把 tests/ 之外的路径交给 pytest → tests/conftest.py 根本不加载）。后者由仓库根的
conftest.py 兜住，并由本文件末尾那几枚子进程用例与静态钉守。

R53 只钉住了 DocumentRetriever 的 chroma_dir 默认值，而工作树里那枚被 git 跟踪的向量库
还有四条入口绕得开它：

1. scripts/rebuild_index.py:292 的落点常量 ROOT/"chroma_db"（--status 普查走的就是它，
   而 open_census_store 刻意不用 DocumentRetriever）；
2. 同一行前面的 CHROMA_DIR 环境变量分支；
3. scripts/compare_vector_recall.py:76 --chroma-dir 的默认值 "./chroma_db" —— 相对 cwd，
   而 pytest 的 cwd 就是仓库根；
4. 任何把工作树内绝对路径当实参传进来的调用。

本文件钉的是 tests/conftest.py 里的 _pin_chroma_persistent_client：这四条路都汇到
chromadb.PersistentClient 这个唯一收口，落点在工作树里的一律改道进临时沙箱。

一条反直觉的事实，也是本单立单的原因（2026-09-21 实测，本树 @9cdbef2，chromadb 1.5.9）：
一次不带任何参数的 open_census_store() —— 纯只读普查，不碰 embedder、不写一条语料 ——
就把 chroma_db/chroma.sqlite3 原地改写：字节数 6 262 784 一字不变，sha256 由
0b8cb318a0e0ba18 变成 c43c3e8a950a64b1，git status --porcelain -- chroma_db 当场报 M。
所以本文件的快照一律带 mtime_ns：只比字节数会漏掉这种「同尺寸回写」。

全离线：不连模型、不起服务、不调 git、不联网；要开库就开在 tmp_path 或临时沙箱里。
"""
import ast
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import chromadb
from chromadb.config import Settings

from app.rag.retriever import DocumentRetriever  # noqa: E402  -- 沙箱先钉好，这里才敢 import

#: 本文件被 collect 的时刻（任何用例都还没跑）工作树向量库的 git 态。快照为什么取在导入期：
#: pytest 先 import 测试模块再跑用例，所以这一行的时刻就是「本场会话开始之前」，用它做对照
#: 才能把「这场会话动没动被跟踪的库」单独量出来 —— 树接手时本来就脏（主树现状）也不会误判。
def _git_state(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
    except OSError:  # pragma: no cover - 没装 git 的机器由下面的断言指名
        return "\x00git-unavailable"


GIT_STATUS_AT_COLLECTION = _git_state("status", "--porcelain", "--", "chroma_db")
GIT_NUMSTAT_AT_COLLECTION = _git_state("diff", "--numstat", "--", "chroma_db")

#: 生产侧的出厂默认值，R53/R134 拦的就是它落到工作树里的那一刻。
SHIPPED_RELATIVE_DEFAULT = "./chroma_db"


def _rebuild_cli():
    return importlib.import_module("scripts.rebuild_index")


def _comparator():
    path = Path(chroma_writeback_repo_root()) / "scripts" / "compare_vector_recall.py"
    spec = importlib.util.spec_from_file_location("r134_compare_vector_recall", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chroma_writeback_repo_root() -> str:
    """仓库根：本文件与 conftest 的 CHROMA_REPO_ROOT 必须是同一个。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ledger_mark(guard) -> int:
    return len(guard.calls)


def _new_entries(guard, mark: int) -> list[dict]:
    return guard.calls[mark:]


def _redirect_for(guard, mark: int, expected_requested: str) -> dict:
    """取本次调用里那条「被改道」的台账，取不到就是把漏口留在了原处。"""
    entries = [
        entry
        for entry in _new_entries(guard, mark)
        if entry["redirected"] and entry["requested"] == expected_requested
    ]
    assert entries, (
        f"没有任何一次 PersistentClient 落点被改道：期望 {expected_requested!r}，"
        f"实际新增台账 {_new_entries(guard, mark)}。conftest 的 R134 收口没装上来。"
    )
    return entries[-1]


def test_the_session_baseline_covers_every_tracked_chroma_file(chroma_writeback_guard):
    """前提校验：基线真的量到了那批被跟踪的二进制，否则后面的比对是空的。"""
    baseline = chroma_writeback_guard.baseline

    assert baseline, f"{chroma_writeback_guard.store_dir} 不在，快照无从谈起"
    assert "chroma.sqlite3" in baseline, sorted(baseline)
    assert any(name.endswith("data_level0.bin") for name in baseline), sorted(baseline)
    assert chroma_writeback_guard.diff(baseline) == [], (
        "会话刚开始就有写回告警，说明基线取晚了，本文件的钉子全部失去意义："
        + " | ".join(chroma_writeback_guard.diff(baseline))
    )


def test_the_snapshot_guard_names_the_file_that_was_written(tmp_path, chroma_writeback_guard):
    """反空转：守卫必须能在真被写脏时指名是哪一枚文件，而不是永远返回空表。

    这里刻意不开工作树的库：拿临时目录做假仓库，证的是这段比对逻辑本身有效。
    """
    store = tmp_path / "chroma_db"
    (store / "segment").mkdir(parents=True)
    (store / "chroma.sqlite3").write_bytes(b"x" * 64)
    (store / "segment" / "data_level0.bin").write_bytes(b"y" * 32)
    snapshot = chroma_writeback_guard.snapshot(str(store))

    with open(store / "chroma.sqlite3", "ab") as handle:
        handle.write(b"more")

    problems = chroma_writeback_guard.diff(snapshot, target_dir=str(store))
    assert len(problems) == 1, problems
    assert problems[0].startswith("chroma.sqlite3: "), problems
    assert "data_level0.bin" not in problems[0], "没动过的文件不许被点名"


def test_the_snapshot_guard_spots_a_same_size_writeback(tmp_path, chroma_writeback_guard):
    """主树那种脏法就是「尺寸一字不变、内容被回写」——只比字节数的快照会漏掉它。

    写之前睡 50 ms：本机实测 NTFS 的 mtime 更新粒度粗到同一个 tick 之内两次写入
    mtime_ns 差为 0（同一 tick 的同尺寸回写，任何 stat 快照都看不见，这是守卫公开
    的分辨率下限，也是验收判据还要再读一次 git diff --numstat 的理由）。
    会话里不存在这种撞车：基线取在 conftest 导入期，任何真实写回都落在几个 tick 之后。
    """
    store = tmp_path / "chroma_db"
    store.mkdir()
    target = store / "chroma.sqlite3"
    target.write_bytes(b"A" * 128)
    snapshot = chroma_writeback_guard.snapshot(str(store))

    time.sleep(0.05)
    target.write_bytes(b"B" * 128)

    problems = chroma_writeback_guard.diff(snapshot, target_dir=str(store))
    assert len(problems) == 1, problems
    assert problems[0].startswith("chroma.sqlite3: 尺寸 128 -> 128 B"), problems
    assert "mtime_ns" in problems[0], problems


def test_the_snapshot_guard_names_a_new_file_and_a_deleted_one(tmp_path, chroma_writeback_guard):
    """新建与删除都要指名：offline_collection.json 那类漏网文件就是「本次会话新建」。"""
    store = tmp_path / "chroma_db"
    store.mkdir()
    (store / "keep.bin").write_bytes(b"k")
    (store / "gone.bin").write_bytes(b"g")
    snapshot = chroma_writeback_guard.snapshot(str(store))

    os.remove(store / "gone.bin")
    (store / "offline_collection.json").write_text("{}", encoding="utf-8")

    problems = chroma_writeback_guard.diff(snapshot, target_dir=str(store))
    named = " | ".join(problems)
    assert "offline_collection.json: 本次会话新建" in named, problems
    assert "gone.bin: 本次会话被删除" in named, problems
    assert "keep.bin" not in named, problems


def test_the_census_default_entry_point_is_steered_out_of_the_tree(chroma_writeback_guard):
    """判据②主证：--status 普查不带任何参数，也不许碰到工作树那批被跟踪的文件。"""
    module = _rebuild_cli()
    repo_store = chroma_writeback_guard.store_dir
    mark = _ledger_mark(chroma_writeback_guard)

    store, reason = module.open_census_store()

    entry = _redirect_for(chroma_writeback_guard, mark, repo_store)
    assert entry["redirected"] is True
    assert chroma_writeback_guard.within(chroma_writeback_guard.sandbox_root, entry["target"]), entry
    assert not chroma_writeback_guard.within(chroma_writeback_guard.repo_root, entry["target"]), entry
    assert chroma_writeback_guard.diff(chroma_writeback_guard.baseline) == [], (
        "census 普查把被跟踪的向量库写脏了："
        + " | ".join(chroma_writeback_guard.diff(chroma_writeback_guard.baseline))
    )
    observed = getattr(store, "source", None) or reason
    if store is not None:
        assert not chroma_writeback_guard.within(chroma_writeback_guard.repo_root,
                                                 str(observed).split("#")[0]), observed


def test_an_explicit_in_tree_path_is_steered_out_too(chroma_writeback_guard):
    """显式把仓库绝对路径当实参传进来，同样不许落到工作树（改道不看调用方多诚实）。"""
    module = _rebuild_cli()
    repo_store = chroma_writeback_guard.store_dir
    mark = _ledger_mark(chroma_writeback_guard)

    module.open_census_store(repo_store, "enterprise_docs")

    entry = _redirect_for(chroma_writeback_guard, mark, repo_store)
    assert entry["target"] == chroma_writeback_guard.redirects[repo_store], entry
    assert chroma_writeback_guard.diff(chroma_writeback_guard.baseline) == []


def test_the_chroma_dir_variable_cannot_point_inside_the_tree(chroma_writeback_guard, monkeypatch):
    """CHROMA_DIR 指回工作树：仍然在收口处改道，脚本常量与环境变量共用一道门。"""
    module = _rebuild_cli()
    repo_store = chroma_writeback_guard.store_dir
    monkeypatch.setenv("CHROMA_DIR", repo_store)
    mark = _ledger_mark(chroma_writeback_guard)

    module.open_census_store()

    _redirect_for(chroma_writeback_guard, mark, repo_store)
    assert chroma_writeback_guard.diff(chroma_writeback_guard.baseline) == []


def test_the_recall_comparator_relative_default_cannot_open_the_tracked_store(
    chroma_writeback_guard, monkeypatch
):
    """compare_vector_recall 的 "./chroma_db" 是相对 cwd 的，而 pytest 的 cwd 就是仓库根 ——
    照样改道。这里显式 chdir 到仓库根，钉的是那条默认值真实会解析到的地方。
    """
    module = _comparator()
    repo_store = chroma_writeback_guard.store_dir
    monkeypatch.chdir(chroma_writeback_guard.repo_root)
    assert os.path.abspath(SHIPPED_RELATIVE_DEFAULT) == repo_store, (
        "cwd 不在仓库根，这条用例的前提不成立了"
    )
    mark = _ledger_mark(chroma_writeback_guard)

    with pytest.raises(SystemExit):
        # 改道之后那是一个空沙箱库，取不到 enterprise_docs；这里要的不是它的结论，
        # 而是「这一次 open 一个字节都没写进工作树」。
        module.open_chroma(SHIPPED_RELATIVE_DEFAULT, "enterprise_docs")

    _redirect_for(chroma_writeback_guard, mark, repo_store)
    assert chroma_writeback_guard.diff(chroma_writeback_guard.baseline) == []


def test_a_store_outside_the_tree_is_left_alone(tmp_path, chroma_writeback_guard):
    """反向边界：仓库外的目录必须原样放行，否则本单会把自己的临时库也搞坏。"""
    directory = tmp_path / "chroma_db"
    mark = _ledger_mark(chroma_writeback_guard)

    client = chromadb.PersistentClient(
        path=str(directory), settings=Settings(anonymized_telemetry=False)
    )
    client.heartbeat()

    entries = _new_entries(chroma_writeback_guard, mark)
    assert len(entries) == 1, entries
    assert entries[0]["redirected"] is False, entries[0]
    assert entries[0]["requested"] == os.path.abspath(str(directory)), entries[0]
    assert (directory / "chroma.sqlite3").is_file(), "改道之外的真库应当照常建起来"
    assert str(directory) not in chroma_writeback_guard.redirects


def test_constructing_the_retriever_leaves_the_tracked_store_untouched(chroma_writeback_guard):
    """R53 那条腿在 R134 的逐文件快照下复量一次：无参构造只可能落在沙箱里。"""
    before = chroma_writeback_guard.snapshot()

    retriever = DocumentRetriever()

    assert retriever.chroma_dir == os.environ["ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR"]
    assert chroma_writeback_guard.within(chroma_writeback_guard.sandbox_root, retriever.chroma_dir)
    assert os.listdir(retriever.chroma_dir), "沙箱里应当留下 chroma 生成的文件"
    assert chroma_writeback_guard.snapshot() == before, (
        "工作树的 ./chroma_db 被写动了：" 
        + " | ".join(chroma_writeback_guard.diff(before))
    )


def test_the_redirect_mapping_is_stable_and_injective(chroma_writeback_guard):
    """同一原路径整个会话恒映射同一处；不同路径不许撞进同一个库（Chroma 一目录一写者）。"""
    calls: list[str] = []

    class Fake:
        @staticmethod
        def PersistentClient(path: str = "default", *args, **kwargs):
            calls.append(path)
            return "client"

    fake = Fake()
    parameter, shipped = chroma_writeback_guard.pin(
        chroma_writeback_guard.sandbox_root, chroma_writeback_guard.repo_root, module=fake
    )
    assert parameter == "path", parameter
    assert callable(shipped)

    first = fake.PersistentClient(os.path.join(chroma_writeback_guard.repo_root, "chroma_db"))
    second = fake.PersistentClient(os.path.join(chroma_writeback_guard.repo_root, "chroma_db"))
    other = fake.PersistentClient(chroma_writeback_guard.store_dir + "-elsewhere")
    outside = fake.PersistentClient(os.path.join(os.environ["TEMP"], "r134_outside_store"))

    assert first == second == other == outside == "client"
    assert len(calls) == 4, calls
    assert calls[0] == calls[1] != calls[2], calls
    assert not chroma_writeback_guard.within(chroma_writeback_guard.repo_root, calls[0]), calls
    assert not chroma_writeback_guard.within(chroma_writeback_guard.repo_root, calls[2]), calls
    assert calls[3] == os.path.abspath(os.path.join(os.environ["TEMP"], "r134_outside_store")), (
        "仓库外的路径必须原样放行：" + repr(calls[3])
    )
    assert chroma_writeback_guard.within(chroma_writeback_guard.sandbox_root, calls[0]), calls


def test_the_pin_refuses_a_factory_that_is_not_a_directory_funnel(chroma_writeback_guard):
    """签名对不上时必须抛，而不是静默跳过——静默跳过等于本单白做（R53 同一条纪律）。"""

    class NotCallable:
        PersistentClient = None

    class RenamedFirstArgument:
        @staticmethod
        def PersistentClient(vector_store: str = "x"):
            return vector_store

    class NoParameters:
        @staticmethod
        def PersistentClient():
            return None

    for module in (NotCallable, RenamedFirstArgument, NoParameters):
        with pytest.raises(RuntimeError):
            chroma_writeback_guard.pin(
                chroma_writeback_guard.sandbox_root,
                chroma_writeback_guard.repo_root,
                module=module,
            )


def test_installing_the_redirect_twice_does_not_stack_a_second_shell(chroma_writeback_guard):
    """幂等：conftest 导入期之外再装一次不许叠壳，否则台账会双记、反证也数不清。"""
    calls: list[str] = []

    class Fake:
        @staticmethod
        def PersistentClient(path: str = "default"):
            calls.append(path)
            return "client"

    fake = Fake()
    chroma_writeback_guard.pin(chroma_writeback_guard.sandbox_root,
                               chroma_writeback_guard.repo_root, module=fake)
    shell = fake.PersistentClient
    parameter, shipped = chroma_writeback_guard.pin(
        chroma_writeback_guard.sandbox_root, chroma_writeback_guard.repo_root, module=fake
    )
    assert fake.PersistentClient is shell, "第二次安装换了另一层壳"
    assert shipped is shell and parameter == "path"
    fake.PersistentClient(os.path.join(chroma_writeback_guard.repo_root, "chroma_db"))
    assert len(calls) == 1, calls


# ==================== R134 第二成因：把 tests/ 之外的路径交给 pytest ====================
# 总控补充（09-21）：Hooke（R32）在它树上跑 `pytest app/api/v1/chat.py` 又把
# chroma_db/chroma.sqlite3 写脏了一次。原因不是某枚测试，而是「钉子只在 tests/conftest.py
# 的导入期动手」：conftest 的加载跟着命令行参数的祖先链走，参数落在 tests/ 之外就拿不到
# 那枚文件，而 app/api/v1/chat.py:83 是模块级的 DocumentRetriever()，一 import 就开库。
# 所以下面几枚子进程用例把「起法」本身钉成判据：无论把哪一枚文件交给 pytest，工作树的
# chroma_db 一个字节都不许动。子进程用 sys.executable（= 跑本次会话的那枚解释器），
# 不落任何新文件进仓库（探针住在 tmp_path，缓存 Provider 关掉）。

#: 探针以 pytest 插件的身份加载，在 pytest_sessionstart 里动手 —— 那时 conftest 已经装完。
_CHILD_PROBE = """
import json
import os
import sys


def pytest_sessionstart(session):
    report = {"executable": sys.executable, "cwd": os.getcwd()}
    import chromadb
    from chromadb.config import Settings

    report["redirect_marker"] = bool(
        getattr(chromadb.PersistentClient, "_enterprise_brain_chroma_redirect", False)
    )
    from tests import _chroma_sandbox as pins

    report["pins_installed"] = pins.PINS_INSTALLED
    report["default_pinned"] = pins.CHROMA_DIR_DEFAULT_INDEX is not None
    report["sandbox_root"] = pins.CHROMA_SANDBOX_ROOT
    report["repo_root"] = pins.CHROMA_REPO_ROOT

    from app.rag.retriever import DocumentRetriever

    retriever = DocumentRetriever()
    report["retriever_requested"] = os.path.abspath(str(retriever.chroma_dir))
    chromadb.PersistentClient(
        path=pins.CHROMA_REPO_STORE, settings=Settings(anonymized_telemetry=False)
    )
    report["redirects"] = dict(pins.CHROMA_SANDBOX_REDIRECTS)
    report["calls"] = list(pins.CHROMA_PERSISTENT_CLIENT_CALLS)
    destination = os.environ.get("R134_CHILD_REPORT")
    if destination:
        with open(destination, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False)
            handle.write("\\n")
"""


def _child_environment(tmp_path: Path, repo_root: str, report: Path) -> dict:
    """子进程环境。

    R20/R56/R70 那几枚钉子住在 tests/conftest.py 里，而本单测的起法恰好拿不到它们，
    所以这里手动复述它们的效果：DSN 指向保留端口 1、Ollama 地址指向打不通的回环、
    模型名用同一枚哨兵。少写一行，这枚取证用例就会反过来去打宿主的数据库或模型端口。
    """
    env = dict(os.environ)
    env["DATABASE_URL"] = (
        "postgresql://enterprise_brain_pytest@127.0.0.1:1/enterprise_brain_pytest"
        "?connect_timeout=1"
    )
    # 端口 9（discard）而不是端口 1：tests/conftest.py:295 有一条交叉断言「R20 的 PG 钉子
    # 127.0.0.1:1 不能被 R56 的模型端口闸门当成模型端口」，而那枚闸门的端口集正是从
    # OLLAMA_BASE_URL 推出来的——指到 1 会让任何加载 tests/conftest.py 的子进程当场
    # ImportError（实测 rc=4）。端口 9 同样打不通，但不与那枚钉子抢地址。
    env["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
    env["LOCAL_MODEL_NAME"] = "__eb_test_disabled__"
    env["R134_CHILD_REPORT"] = str(report)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), repo_root])
    env.pop("ENTERPRISE_BRAIN_PYTEST_CHROMA_DIR", None)
    return env


def _run_child_pytest(repo_root: str, args: list[str], env: dict, cwd: str | None = None) -> object:
    """枚 -q 交给调用方：要断言终端抬头（钉子装没装的直接证据）就得留着默认 verbosity。

    缓存 Provider 关掉，免得子进程去写 .pytest_cache；cwd 能换，用来复现「在子目录里拿
    相对路径起 pytest」这一类起法（app/rag/retriever.py:394 的默认值是相对 cwd 的）。
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=cwd or repo_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def _assert_no_in_tree_landing(report: dict, chroma_writeback_guard) -> None:
    """台账里每一次 PersistentClient 调用：落点必须在仓库外。"""
    within = chroma_writeback_guard.within
    repo_root = chroma_writeback_guard.repo_root
    assert report["pins_installed"] is True, "这种起法根本没装上 R134 的钉子"
    assert report["redirect_marker"] is True, "chromadb.PersistentClient 上没有改道壳"
    assert report["calls"], "子进程一次 PersistentClient 都没开，探针白跑了"
    for call in report["calls"]:
        requested, target = call["requested"], call["target"]
        if call["redirected"]:
            assert target and not within(repo_root, target), f"改道落点又回仓库了：{call}"
        else:
            assert not within(repo_root, str(requested)), f"工作树路径没被改道：{call}"
    requested_retriever = str(report["retriever_requested"])
    landing = report["redirects"].get(requested_retriever)
    if landing is None:
        assert not within(repo_root, requested_retriever), (
            f"无参 DocumentRetriever() 落在工作树里却没被改道：{requested_retriever}"
        )
    else:
        assert within(str(report["sandbox_root"]), str(landing)), f"改道落点不在沙箱里：{landing}"


def test_a_path_argument_outside_tests_still_loads_the_pins(
    tmp_path, chroma_writeback_guard
):
    """把 tests/ 之外的一枚产品文件交给 pytest：钉子必须在，工作树必须原样。"""
    probe = tmp_path / "r134_child_probe.py"
    probe.write_text(_CHILD_PROBE, encoding="utf-8")
    report_path = tmp_path / "child-report.json"
    store = chroma_writeback_guard.store_dir
    before = chroma_writeback_guard.snapshot(store)
    completed = _run_child_pytest(
        chroma_writeback_guard.repo_root,
        ["--collect-only", "-p", "r134_child_probe", "app/common/audit.py"],
        _child_environment(tmp_path, chroma_writeback_guard.repo_root, report_path),
    )
    problems = chroma_writeback_guard.diff(before, chroma_writeback_guard.snapshot(store))
    assert completed.returncode in {0, 5}, completed.stdout[-3000:] + completed.stderr[-3000:]
    assert "R134 chroma sandbox:" in completed.stdout, (
        "终端抬头里没有仓库根 conftest 那一行：这种起法根本没加载它。\n" + completed.stdout[-3000:]
    )
    assert problems == [], "工作树的 chroma_db 被子进程写脏：" + "；".join(problems)
    assert report_path.is_file(), "探针没落报告，子进程多半死在导入之前"
    _assert_no_in_tree_landing(json.loads(report_path.read_text(encoding="utf-8")), chroma_writeback_guard)


def test_a_relative_path_from_a_subdirectory_still_loads_the_pins(
    tmp_path, chroma_writeback_guard
):
    """换一种起法：cwd 落在 app/，参数是相对路径 common/audit.py。

    这一形更阴：app/rag/retriever.py:394 的默认值 "./chroma_db" 是相对 cwd 的，cwd 一旦不在
    仓库根，它要开的就不是那六枚被跟踪的文件，而是在 app/ 底下新建一枚没人跟踪的 chroma_db。
    改道闸门按「仓库之内」判定，不看相对还是绝对，所以这条路同样只剩临时沙箱。

    诚实边界：DocumentRetriever.__init__:395 的 os.makedirs(chroma_dir) 在收口之前，所以闸门
    拦得住「开库」、拦不住「留一枚空目录」。git 不跟踪空目录，判据① 那两条命令因此仍然成立；
    本用例断的是「目录里不许落文件」，并顺手把这枚空目录清掉，不给下一班留脏项。
    """
    probe = tmp_path / "r134_child_probe.py"
    probe.write_text(_CHILD_PROBE, encoding="utf-8")
    report_path = tmp_path / "child-report.json"
    store = chroma_writeback_guard.store_dir
    stray = Path(chroma_writeback_guard.repo_root, "app", "chroma_db")
    before = chroma_writeback_guard.snapshot(store)
    completed = _run_child_pytest(
        chroma_writeback_guard.repo_root,
        ["-q", "--collect-only", "-p", "r134_child_probe", "common/audit.py"],
        _child_environment(tmp_path, chroma_writeback_guard.repo_root, report_path),
        cwd=str(Path(chroma_writeback_guard.repo_root) / "app"),
    )
    problems = chroma_writeback_guard.diff(before, chroma_writeback_guard.snapshot(store))
    output = completed.stdout + completed.stderr
    try:
        assert completed.returncode in {0, 5}, output[-3000:]
        assert problems == [], "从子目录起 pytest 也写脏了被跟踪的向量库：" + "；".join(problems)
        leftovers = sorted(p.name for p in stray.iterdir()) if stray.is_dir() else []
        assert not leftovers, (
            f"子进程把 cwd 相对默认值开成了工作树里的新库并落了文件：{stray} -> {leftovers}"
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["cwd"] == str(Path(chroma_writeback_guard.repo_root) / "app"), report["cwd"]
        _assert_no_in_tree_landing(report, chroma_writeback_guard)
        assert str(stray) in report["redirects"], (
            f"cwd 相对的那枚默认值没进改道台账：{sorted(report['redirects'])}"
        )
    finally:
        if stray.is_dir():  # 万一上面红了，也别把新目录留在树里给下一班添脏项
            shutil.rmtree(stray, ignore_errors=True)


def _module_level_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


def test_the_repo_root_conftest_exists_and_stays_out_of_app(chroma_writeback_guard):
    """仓库根那枚装载点本身也得有钉：整枚删掉，本文件上面的子进程用例全会当场红。

    另一条更要紧：它在导入期一个 app.* 都不许 import。app/rag/retriever.py:19 的
    load_dotenv() 会在 R70 的桩装上之前就跑掉 —— 仓库根的 conftest 比 tests/conftest.py
    先加载，在那儿引 app 等于把「宿主的 .env 一个字都不许进测试进程」重新放开。
    """
    root_conftest = Path(chroma_writeback_guard.repo_root) / "conftest.py"
    assert root_conftest.is_file(), "仓库根的 conftest.py 不见了：R134 的越界起法又没人管了"
    tree = ast.parse(root_conftest.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not [name for name in imports if name.split(".")[0] == "app"], (
        f"仓库根 conftest 在导入期引了 app：{sorted(imports)}；R70 的 .env 闸门会因此失效"
    )
    installs = [
        call
        for call in _module_level_calls(tree)
        if call.func.attr == "install_chroma_sandbox_pins"
    ]
    assert len(installs) == 1, "仓库根 conftest 没有且只调一次装载函数"
    keywords = {keyword.arg for keyword in installs[0].keywords}
    assert "pin_retriever_default" in keywords, (
        "仓库根 conftest 不再显式声明装载范围：app 级默认值改写会跟着 import app 回到导入期"
    )
    values = {keyword.arg: keyword.value for keyword in installs[0].keywords}
    assert isinstance(values["pin_retriever_default"], ast.Constant) and (
        values["pin_retriever_default"].value is False
    ), "仓库根这一侧只许装依赖级的那半"


def test_the_tracked_store_leaves_the_git_view_untouched(chroma_writeback_guard):
    """判据①的用例形态：本场会话结束时，`git status --porcelain -- chroma_db` 与
    `git diff --numstat -- chroma_db` 必须和会话开始前逐字相同。

    钉的是「这一场跑动没改变 git 眼里的被跟踪库」，而不是「必须是干净的」——后者在主树那种
    接手即脏的树上永远红，红了就没人再看，等于没钉。树干净时（总控验收判据①的前提）这条
    断言就是字面上的两条空输出；树本来就脏时它退化成「别再加脏」，仍然有意义。

    它也是那枚 (size, mtime_ns) 快照的外部复核：快照有「同 tick 同尺寸回写」的分辨率下限，
    而 git 比的是内容 —— be-r119 那次「尺寸一字不变、sha256 变了」正好落在这个差里。
    """
    assert GIT_STATUS_AT_COLLECTION != "\x00git-unavailable", (
        "本机 git 不可用：这枚钉子判不了，别把它当通过"
    )
    status_now = _git_state("status", "--porcelain", "--", "chroma_db")
    numstat_now = _git_state("diff", "--numstat", "--", "chroma_db")
    assert status_now == GIT_STATUS_AT_COLLECTION, (
        "本场会话改变了被跟踪向量库在 git 眼里的状态：\n"
        f"会话前 {GIT_STATUS_AT_COLLECTION!r}\n现在 {status_now!r}\n"
        f"改道台账 {len(chroma_writeback_guard.redirects)} 条，"
        f"调用 {len(chroma_writeback_guard.calls)} 次"
    )
    assert numstat_now == GIT_NUMSTAT_AT_COLLECTION, (
        "本场会话让被跟踪向量库的内容相对 HEAD 漂了：\n"
        f"会话前 {GIT_NUMSTAT_AT_COLLECTION!r}\n现在 {numstat_now!r}"
    )




def _chroma_funnel_sites(root: Path) -> list[str]:
    """把 app/ 与 scripts/ 里「按目录开 Chroma 库」的调用点抠出来（AST，不是扫文本）。

    只认 chromadb 自己的工厂：先在本文件里找 chromadb 的导入别名，再要求调用点的接收者
    就是那枚别名（或直接 from chromadb import 进来的名字）。少了这一步，httpx.Client(...)
    那类同名调用会被误计成开库收口——实测 app/agents/nodes.py:713 与
    app/common/model_handler.py:258/329 就是这种撞名，误报的红不携带信息。
    """
    factory = {
        "AdminClient",
        "AsyncHttpClient",
        "Client",
        "CloudClient",
        "EphemeralClient",
        "HttpClient",
        "PersistentClient",
        "PostClient",
        "RustClient",
        "SharedSystemClient",
    }

    def outermost(expression):
        while isinstance(expression, ast.Attribute):
            expression = expression.value
        return getattr(expression, "id", "")

    sites = []
    for folder in ("app", "scripts"):
        for current, dirs, names in os.walk(root / folder):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(names):
                if not name.endswith(".py"):
                    continue
                candidate = Path(current, name)
                relative = candidate.relative_to(root).as_posix()
                tree = ast.parse(candidate.read_text(encoding="utf-8"))
                aliases, direct = set(), set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for spec in node.names:
                            if spec.name == "chromadb" or spec.name.startswith("chromadb."):
                                aliases.add(spec.asname or spec.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        if (node.module or "").split(".")[0] == "chromadb":
                            for spec in node.names:
                                if spec.name in factory:
                                    direct.add(spec.asname or spec.name)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Attribute) and func.attr in factory and outermost(func) in aliases:
                            sites.append(f"{relative}:{node.lineno}:{func.attr}")
                        elif isinstance(func, ast.Name) and func.id in direct:
                            sites.append(f"{relative}:{node.lineno}:{func.id}")
                    elif isinstance(node, ast.keyword) and node.arg == "persist_directory":
                        # Settings(persist_directory=...) 是第二条腿：目录不经位置参数，直接进配置。
                        sites.append(f"{relative}:{node.lineno}:persist_directory")
    return sorted(sites)


def test_there_is_still_only_one_directory_funnel_to_guard(chroma_writeback_guard):
    """R134 只钉一枚 chromadb.PersistentClient，依据是「全仓按目录开库的收口只有那三处」。

    这条依据是别人给的（总控 09-21 的 git grep），所以必须自己钉住：app/ 或 scripts/ 里以后
    若长出第二种开库写法（chromadb.Client(...) / Settings(persist_directory=...) /
    SharedSystemClient / EphemeralClient / HttpClient / AdminClient），本用例当场红并指名
    新位置。那时要改的是 tests/_chroma_sandbox.py 的收口清单，而不是再叠一层默认值改写——
    「第 N 层改写」正是本单判据里禁止的表面补丁。
    """
    sites = _chroma_funnel_sites(Path(chroma_writeback_guard.repo_root))
    # 钉的是"收口有哪几处"，不是"那几处今天坐在第几行"：本单原文的依据就是
    # 「全仓按目录开库的收口只有那三处」。带行号的等式会被一次无关的插行打红——
    # R152 在 retriever.py 里加了 251 行，把这枚 PersistentClient 从 480 顶到 731，
    # 收口一个没多、一个没少，却红了一整条全量。所以这里比 (文件, 工厂名) 与**枚数**：
    # 同文件再长第二处会得到 4 枚，照样当场红（行号仍随消息打出来，指位置用）。
    funnels = [site.split(":", 1)[0] + ":" + site.rsplit(":", 1)[1] for site in sites]
    assert funnels == [
        "app/rag/retriever.py:PersistentClient",
        "scripts/compare_vector_recall.py:PersistentClient",
        "scripts/rebuild_index.py:PersistentClient",
    ], "按目录开 Chroma 的收口清单变了，R134 的改道要跟着扩：" + "、".join(sites)


def test_the_tests_conftest_still_installs_the_app_level_half(chroma_writeback_guard):
    """分工的另一半：app 级默认值改写仍由 tests/conftest.py 装，且带着持久化沙箱那枚交叉断言。"""
    source = (Path(chroma_writeback_guard.repo_root) / "tests" / "conftest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    installs = [
        call
        for call in _module_level_calls(tree)
        if call.func.attr == "install_chroma_sandbox_pins"
    ]
    assert len(installs) == 1, "tests/conftest.py 不再装载钉子：R53 的默认值改写就没了"
    assert installs[0].args and installs[0].args[0].id == "_PERSISTENCE_SANDBOX", (
        "持久化沙箱没传进去，install 里那条「两处沙箱必须分开」的交叉断言会被静默跳过"
    )
    from tests import _chroma_sandbox as pins

    assert pins.CHROMA_DIR_DEFAULT_INDEX is not None, "本会话的 chroma_dir 默认值没被改写"
