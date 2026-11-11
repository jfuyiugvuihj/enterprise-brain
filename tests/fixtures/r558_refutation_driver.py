# -*- coding: utf-8 -*-
r"""R558 反证驱动：甲案投递面的六把刀，全部走**影子副本道**（真树全程只读）。

手法沿用 `tests/fixtures/r364_refutation_driver.py`（它又沿用 R356/R357 从 R253 抄回来的那条规矩）：
**一枚被跟踪文件都不就地改写**。复刻一棵 %TEMP% 副本根，pytest 的 cwd 就是副本根，于是 `import app`
解析到副本里的 `app/**`，刀口也只落在副本里。对真树只有两类动作：`read_bytes()` 取基线摘要、
只读地跑几条 git 查询。收尾既逐枚核对真树摘要恒定，又用 `sys.addaudithook` 记账本进程在真树里
开过的每一枚写口，必须为空。

🔴 本驱动器不许在主树里跑（主树的 `.git` 是目录，`stage_shadow()` 当场拦）。

六把刀各自要咬的东西（判据⑥ 要求 ≥5 把，且 victim 必须是在册钉本身）：

* **刀1 backfill** 把 `app/common/reliable_queue.py` 里那两枚汇流阈值抬到跑完都不会自己汇
  （`PIECE_FLUSH_PIECES = 8` → `10 ** 6`、`PIECE_FLUSH_SECONDS = 1.0` → `10 ** 9`）⇒ 片段只在收窗
  那一发整批落表，判据① 那格必须红：`test_the_polling_body_grows_while_the_turn_is_still_running`。
  这一把就是判据⑥ 点名的「把片段增量做成一次性全量回填」——它红了，「递增」这个词才不是散文。
* **刀2 drop_tail** 摘掉 `deploy/queue_worker.py` 里收窗前那一发 `piece_ledger.flush()`
  ⇒ 表里永远缺最后一截字，`test_the_deltas_concatenate_to_every_published_character` 必须红。
* **刀3 silent_discarded** 把 `piece_readout()` 的 `discarded` 钉死成 0
  ⇒ 判据④ 那格「超上限丢弃 N 枚」变成一句好看的 0，`test_the_ledger_cap_reports_truncation_not_silence` 必须红。
* **刀4 silent_store_cap** 把增量表写满之后的 `self.truncated += 1` 摘掉
  ⇒ 「停止存正文」这件事没人说，`test_the_store_cap_is_a_separate_number_from_the_ledger_cap` 必须红。
* **刀5 terminal_leak** 把 `chat.py` 里 `if status == "processing"` 那枚守卫换成无条件
  ⇒ 片段键漏进终态读数，`test_the_terminal_readout_still_carries_no_piece_keys` 必须红。
  🔴 在册那两族（R232 状态词表 / R254 终态诚实）盯的是**值**与**usage**，看不见多出来一枚键——
  这一格的牙是本单新长的，纸上必须写清「victim 是本单钉，不是在册钉」，不许含混成「在册有牙」。
* **刀6 unregister_sink** 把 `deploy/queue_worker.py` 的注册实参换成 `stream_piece_sink=None`
  ⇒ 两枚**在册钉**必须同时红：`test_r548_*::test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call`
  与 `test_r524_*::test_the_real_hook_for_the_queue_lane_is_now_registered__r548`。这一把证明本单
  没有把 R548 那半张纸偷偷改口，也证明 R558 的红不是只有自己的钉认得。

跑法（从执行层工作树根，只读真树，随便跑）：

    .venv\Scripts\python.exe tests\fixtures\r558_refutation_driver.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Sequence

#: 真树：全程只读。名字刻意不叫 REPO/ROOT —— 那是 R253 扫描器认的「仓根出身」。
SOURCE_TREE = Path(__file__).resolve().parents[2]

MIRROR_DIRS = (
    "app", "tests", "deploy", "scripts", "data", "documents", "migrations", "static",
    #: docs/api 是本单契约那一格的落点；docs/testing 是在册 R524／R548 那四枚「纸上判定词与树上
    #: 读数同判」的钉要读的凭据纸——不镜像它就会在干净副本里红四枚，把量具的缺件误报成钉的缺牙。
    "docs/api", "docs/testing",
)
MIRROR_FILES = (
    "pyproject.toml", "conftest.py", "config.yaml", ".env.example",
    "frontend/src/components/ChatPanel.vue", "frontend/package.json",
)
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "node_modules"}
# ------------------------------------------------------------------------ 具名件与具名钉
R558_REL = "tests/test_r558_queue_lane_pieces_reach_the_polling_surface.py"
R548_REL = "tests/test_r548_queue_lane_registers_the_piece_sink.py"
R524_REL = "tests/test_r524_queue_lane_sends_no_second_character.py"
QUEUE_REL = "app/common/reliable_queue.py"
WORKER_REL = "deploy/queue_worker.py"
CHAT_REL = "app/api/v1/chat.py"

PIN_GROW = "test_the_polling_body_grows_while_the_turn_is_still_running"
PIN_CONCAT = "test_the_deltas_concatenate_to_every_published_character"
PIN_LEDGER_CAP = "test_the_ledger_cap_reports_truncation_not_silence"
PIN_STORE_CAP = "test_the_store_cap_is_a_separate_number_from_the_ledger_cap"
PIN_TERMINAL_SHAPE = "test_the_terminal_readout_still_carries_no_piece_keys"
PIN_R548_ONE_SINK = "test_the_queue_lane_registers_exactly_one_sink_at_the_orchestrator_call"
PIN_R524_HOOK = "test_the_real_hook_for_the_queue_lane_is_now_registered__r548"

#: 本驱动器读过、判过、可能被刀口涉及的每一枚件：收尾逐枚复对摘要，证明六把刀都只落在副本里。
BASELINED = (QUEUE_REL, WORKER_REL, CHAT_REL, R558_REL, R548_REL, R524_REL)

#: 刀口落点：以下每一串都是从盘上现读的**唯一**形状，命中数不为 1 就中止（不猜行号）。
A_FLUSH_PIECES = "PIECE_FLUSH_PIECES = 8"
A_FLUSH_SECONDS = "PIECE_FLUSH_SECONDS = 1.0"
A_DISCARDED_LINE = '            "discarded": int(latest.get("discarded", 0) or 0),'
A_TAIL_FLUSH = "    piece_ledger.flush()\n\n    _log_report_lane_pieces(request_id, piece_ledger)"
A_CAP_COUNT = "            self.truncated += 1"
A_PROCESSING_GUARD = '    if status == "processing":\n        # R558 判据'
A_SINK_KWARG = "stream_piece_sink=stream_piece_sink,"

# ------------------------------------------------------------------------ 真树写口记账
_EVENTS: list = []
_HOOKED = False
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_WRITE_MODES = set("wax+")


def _abs_of(path):
    if isinstance(path, int):
        return None
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return os.path.abspath(text)


def _within(target: str, parent: Path) -> bool:
    head = os.path.normcase(str(parent)) + os.sep
    return os.path.normcase(target).startswith(head)


def _hook(event, args):
    global _HOOKED
    if event != "open" or len(args) < 2:
        return
    target = _abs_of(args[0])
    if target is None or not _within(target, SOURCE_TREE):
        return
    mode = args[1] if isinstance(args[1], str) else ""
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    if any(char in mode for char in _WRITE_MODES) or bool(flags & _WRITE_FLAGS):
        _EVENTS.append(os.path.relpath(target, str(SOURCE_TREE)).replace("\\", "/"))


def install_write_ledger() -> None:
    global _HOOKED
    if not _HOOKED:
        sys.addaudithook(_hook)
        _HOOKED = True


# ------------------------------------------------------------------------ 副本道
def _copy_into(root: Path, rel: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_TREE / rel, target)
    return target


def stage_shadow() -> Path:
    """复刻一棵 %TEMP% 副本根：失手就整棵删掉，不漏半棵副本在外面。"""
    git_marker = SOURCE_TREE / ".git"
    if not git_marker.is_file():
        raise AssertionError(
            "%s 的 .git 不是一枚 worktree 指针文件 —— 本驱动器只许在执行层工作树里跑，"
            "不许在主树里跑（那会去镜像整棵对象库）。" % SOURCE_TREE
        )
    root = Path(tempfile.mkdtemp(prefix="r558-shadow-"))
    try:
        for rel_dir in MIRROR_DIRS:
            base = SOURCE_TREE / rel_dir
            if not base.is_dir():
                continue
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                here = root / Path(dirpath).relative_to(SOURCE_TREE)
                here.mkdir(parents=True, exist_ok=True)
                for name in sorted(files):
                    shutil.copyfile(Path(dirpath) / name, here / name)
        for rel_file in MIRROR_FILES:
            if (SOURCE_TREE / rel_file).is_file():
                _copy_into(root, rel_file)
        shutil.copyfile(git_marker, root / ".git")
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def edit_copy(shadow: Path, rel: str, pairs: Sequence[tuple]) -> None:
    """把副本里那一枚件按字面改写：每处刀口必须**恰好命中一次**，命中数不对就中止（不猜行号）。"""
    path = shadow / rel
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        hits = text.count(old)
        if hits != 1:
            raise AssertionError(
                "刀口在 %s 里命中 %d 次（要求恰好 1 次）：%r" % (rel, hits, old[:72])
            )
        text = text.replace(old, new, 1)
    path.write_bytes(text.encode("utf-8"))

# ------------------------------------------------------------------------ 嵌套跑
def r449_nested_basetemp(parent_scratch: Path) -> Path:
    """R449：每一枚嵌套 pytest 会话只用自己的 basetemp，落点必须在父件 scratch 之内。

    不传 `--basetemp` 时子会话落进 `%TEMP%\pytest-of-<user>` 那枚共享根，收尾会剪别人正在用的
    tmp_path —— 那是门自己造的假红。本件父 scratch 就是影子副本根，残骸跟着副本一起 rmtree。
    判据由 `tests/test_r449_nested_pytest_basetemp_contract.py` 机检。
    """
    root = Path(parent_scratch) / "r449-nested-basetemp"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="child-", dir=str(root)))


def run_pytest(shadow: Path, targets: Sequence[str]) -> dict:
    import re

    if not targets:
        # R453：一枚目标都没有时必须当场拒——pytest 拿到空参数会回落成全量收集，
        # 在影子副本里那就是把整仓跑一遍，既慢又造出与本页无关的假红。
        raise AssertionError("R453：run_pytest 收到空选择，拒绝回落到全量收集")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
         "--basetemp", str(r449_nested_basetemp(shadow))] + list(targets),
        cwd=str(shadow),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert shadow.is_dir(), "R449：嵌套会话把影子副本根弄没了"
    out = result.stdout or ""
    names = re.findall(r"^FAILED [^:]+::(\w+)", out, re.M)
    passed = re.search(r"(\d+) passed", out)
    failed = re.search(r"(\d+) failed", out)
    lines = [line for line in out.strip().splitlines() if line.strip()]
    return {
        "failed": sorted(set(names)),
        "n_failed": int(failed.group(1)) if failed else 0,
        "n_passed": int(passed.group(1)) if passed else 0,
        "errored": bool(re.search(r"^ERROR ", out, re.M)),
        "tail": lines[-1] if lines else "(无输出)",
        "rc": result.returncode,
    }


# ------------------------------------------------------------------------ 六把刀
def knife_backfill_threshold(root: Path) -> None:
    """判据⑥ 点名那一把：把递增汇流改成「跑完才一次给全」。"""
    edit_copy(
        root,
        QUEUE_REL,
        ((A_FLUSH_PIECES, "PIECE_FLUSH_PIECES = 10 ** 6"),
         (A_FLUSH_SECONDS, "PIECE_FLUSH_SECONDS = 10 ** 9")),
    )


def knife_drop_tail_flush(root: Path) -> None:
    edit_copy(
        root,
        WORKER_REL,
        ((A_TAIL_FLUSH, "    _log_report_lane_pieces(request_id, piece_ledger)"),),
    )


def knife_silent_discarded(root: Path) -> None:
    edit_copy(
        root,
        QUEUE_REL,
        ((A_DISCARDED_LINE, '            "discarded": 0,'),),
    )


def knife_silent_store_cap(root: Path) -> None:
    edit_copy(
        root,
        WORKER_REL,
        ((A_CAP_COUNT, "            pass  # knife: 上限不计数"),),
    )


def knife_terminal_leak(root: Path) -> None:
    edit_copy(
        root,
        CHAT_REL,
        ((A_PROCESSING_GUARD,
          '    if True:  # knife: 片段键漏进终态读数\n        # R558 判据'),),
    )


def knife_unregister_sink(root: Path) -> None:
    edit_copy(
        root,
        WORKER_REL,
        ((A_SINK_KWARG, "stream_piece_sink=None,"),),
    )


# ------------------------------------------------------------------------ 逐把跑
def blade(title: str, mutate: Callable[[Path], None], expect: Sequence[str],
          files: Sequence[str], must_stay_green: Sequence[str] = ()) -> dict:
    root = stage_shadow()
    try:
        mutate(root)
        reading = run_pytest(root, list(files))
        print("\n[%s]\n    %s" % (title, reading["tail"]))
        print("    红了 %d 枚: %s" % (reading["n_failed"], ", ".join(reading["failed"]) or "(一枚都不红)"))
        missing = [name for name in expect if name not in reading["failed"]]
        assert not missing, "[%s] 该红的没红：%s" % (title, ", ".join(missing))
        moved = [name for name in must_stay_green if name in reading["failed"]]
        assert not moved, "[%s] 这几枚本来不该红却红了：%s" % (title, ", ".join(moved))
        print("    该红的红着: %s" % ", ".join(expect))
        if must_stay_green:
            print("    该绿的绿着: %s" % ", ".join(must_stay_green))
        print("    同场通过: %d passed" % reading["n_passed"])
        return reading
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    baseline = {rel: hashlib.sha256((SOURCE_TREE / rel).read_bytes()).hexdigest()
                for rel in BASELINED}
    print("真树基线（只读）:")
    for rel in BASELINED:
        print("    %-64s %s" % (rel, baseline[rel][:16]))
    install_write_ledger()

    clean = stage_shadow()
    try:
        reading = run_pytest(clean, [R558_REL, R548_REL, R524_REL])
        print("\n[干净副本] %s" % reading["tail"])
        assert not reading["errored"], "副本里连收集都没跑起来，后面的读数全都不可信"
        assert reading["failed"] == [], reading["failed"]
        clean_passed = reading["n_passed"]
        print("    三枚件在副本里全绿：%d passed / 0 failed" % clean_passed)
    finally:
        shutil.rmtree(clean, ignore_errors=True)

    blade("刀1 backfill 阈值抬到跑完都不汇（判据⑥ 点名的全量回填）", knife_backfill_threshold,
          (PIN_GROW,), (R558_REL,))
    blade("刀2 drop_tail 摘掉收窗前那一发 flush", knife_drop_tail_flush,
          (PIN_CONCAT,), (R558_REL,))
    blade("刀3 silent_discarded 把内存上限丢弃数钉成 0", knife_silent_discarded,
          (PIN_LEDGER_CAP,), (R558_REL,))
    blade("刀4 silent_store_cap 把增量表上限不计数", knife_silent_store_cap,
          (PIN_STORE_CAP,), (R558_REL,))
    blade("刀5 terminal_leak 片段键漏进终态读数", knife_terminal_leak,
          (PIN_TERMINAL_SHAPE,), (R558_REL,))
    blade("刀6 unregister_sink 摘掉 R548 的注册实参（victim 是在册钉）", knife_unregister_sink,
          (PIN_R548_ONE_SINK, PIN_R524_HOOK), (R548_REL, R524_REL, R558_REL))

    print("\n================= 收尾：真树有没有被动过 =================")
    restored = True
    for rel in BASELINED:
        now = hashlib.sha256((SOURCE_TREE / rel).read_bytes()).hexdigest()
        same = now == baseline[rel]
        restored = restored and same
        print("    RESTORED=%s sha=%s  %s" % (same, now[:16], rel))
    print("    真树写口记账（必须为空）: %s" % (_EVENTS or "0 枚"))
    print("    干净副本读数: %d passed" % clean_passed)
    return 0 if restored and not _EVENTS else 1


if __name__ == "__main__":
    sys.exit(main())