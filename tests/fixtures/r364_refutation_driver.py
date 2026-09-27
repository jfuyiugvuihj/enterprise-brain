# -*- coding: utf-8 -*-
r"""R364 反证驱动：两枚"手抄账"现场的盘上真刀，全部走影子副本道（真树全程只读）。

手法沿用 `tests/fixtures/r356_r357_refutation_driver.py`（它又沿用 R339 从 R253 抄回来的那条规矩）：
**一枚被跟踪文件都不就地改写**。复刻一棵 %TEMP% 副本根，pytest 的 cwd 就是副本根，于是 `import app`
解析到副本里的 `app/**`，刀口也只落在副本里。对真树只有两类动作：`read_bytes()` 取基线摘要、
只读地跑几条 git 查询。收尾既逐枚核对真树摘要恒定，又用 `sys.addaudithook` 记账本进程在真树里
开过的每一枚写口，必须为空。

副本根里额外镜像一枚 `.git`（它是 worktree 的**指针文件**，75 字节，不是对象库）：现场 B 的期望值
是从提交里现算的，副本里没有 git 就等于把派生腿劈掉，那种红证明不了任何事。🔴 本驱动器不许在主树
里跑（主树的 `.git` 是目录，下面那条断言会当场拦）。

九把刀各自要读到的东西：

* **刀A1** 把上传腿那行的 `asyncio.to_thread(` 摘掉（退回在事件循环里同步解析）⇒ 现场 A 那枚钉
  必须红。
* **刀A2** 被调符号换成 loader 以外的东西（chat.py 真从 app.documents.preview 引进的符号）⇒ 必须红。
* **刀A3 / 刀A3s** 给那一行加一枚新 kwarg ⇒ 判据①的"参数表允许演进"。两枚读数分开看：A3s（只跑静态
  那枚钉）一枚都不许红；A3（整件跑）里那几枚 runtime 用例照样会红 —— 它们红在 monkeypatch 的假
  `load_document` 不认新 kwarg，那是**合法的签名耦合**（R306 当年就是连桩件一起改的），不是抄写病。
  这一格写清楚，是因为把它当成"钉又红了"就是本族病最容易找错的靶子。
* **刀A4** 换掉持有落盘路径的变量名（连同 `str(...)` 绑定一起换）⇒ 同样一枚都不许多红。
* **刀A5** 多长一枚第二处 `await asyncio.to_thread(load_document, ...)` ⇒ "恰好一枚"那格必须红。
* **刀A6（反例刀）** 把现场 A 的钉放宽成 `assert "load_document" in CHAT_SOURCE`，再下同一把刀A1
  ⇒ 那枚钉**不红**（只跑它自己）。这就是判据③为什么明令不许放宽成裸子串：`load_document` 在 chat.py
  的模块级 import 里就出现一次，钝刀连"解析还在不在事件循环上"都看不见 —— 漂移是隐形的。
* **刀B1** 把副本里的 `app/rag/tables.py` 改坏且不还原 ⇒ 现场 B 的派生钉与 R304 那枚同族钉必须同时红。
* **刀B2** 把锚点换成一枚「与锚点逐字节相同、而自己没改过这枚文件」的提交（现算，不写死）⇒ 三枚
  自校钉必须红，而**字节比对那枚照旧绿** —— 这正是自校钉存在的全部理由。
* **刀B3（反例刀）** 把派生钉钝化成同义反复（拿盘上那份跟自己比），再下同一把刀B1 ⇒ 现场 B 那枚件
  一枚都不红。这一把只跑 `test_r300_tables.py`：R304 那把真尺子还留在原地，把它一起跑只会 red 出
  别人早就咬住的东西，量不到"钝化的这枚钉看不看得见"。

跑法（从树根，只读真树，随便跑）：

    .venv\Scripts\python.exe tests\fixtures\r364_refutation_driver.py
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Sequence

#: 真树：全程只读。名字刻意不叫 REPO/ROOT —— 那是 R253 扫描器认的"仓根出身"，本件所有写口的
#: 落点都只许从下面的 tmp 副本根长出来。
SOURCE_TREE = Path(__file__).resolve().parents[2]

MIRROR_DIRS = ("app", "tests", "data", "migrations", "scripts", "deploy", "documents")
MIRROR_FILES = ("pyproject.toml", "conftest.py", "config.yaml", ".env.example")
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "node_modules"}

UPLOAD_REL = "tests/test_document_upload_resilience.py"
R300_REL = "tests/test_r300_tables.py"
R304_REL = "tests/test_r304_table_wiring.py"
R364_REL = "tests/test_r364_shape_ruler_teeth.py"
CHAT_REL = "app/api/v1/chat.py"
TABLES_REL = "app/rag/tables.py"

#: 本单读过、判过、可能被刀口涉及的每一枚文件：收尾逐枚复对摘要，证明九把刀都只落在副本里。
BASELINED = (
    CHAT_REL,
    TABLES_REL,
    UPLOAD_REL,
    R300_REL,
    R304_REL,
    R364_REL,
    "tests/test_r351_stale_ledger_teeth.py",
    "tests/test_r298_ocr_channel.py",
)

#: 具名钉：名字只在这里出现一次，刀口期望值也从这里取，免得驱动器自己变成第二本手抄账。
PIN_UPLOAD_SHAPE = "test_upload_moves_blocking_parsing_and_indexing_off_the_event_loop"
PIN_R300_BYTES = "test_the_restored_bytes_are_the_ones_the_named_anchor_shipped"
PIN_R300_SELF_CHECK = "test_the_anchor_of_the_restoration_claim_passes_its_three_self_check_nails"
PIN_R300_IMPOSTOR = "test_a_commit_with_identical_bytes_does_not_qualify_as_the_anchor"
PIN_R304_BYTES = "test_the_tables_module_is_still_the_bytes_the_anchor_shipped"
PIN_R304_LAYER = "test_the_ruler_measures_the_git_blob_layer_not_the_checkout"
PIN_R304_CHANGED = "test_the_anchor_commit_really_is_the_one_that_changed_the_file"

#: 刀口的落点：以下每一串都是从盘上现读的**唯一**形状，命中数不为 1 就中止（不猜行号）。
CHAT_LEG = (
    "            content = await asyncio.to_thread(load_document, file_path, "
    "display_name=inspection.display_filename)"
)
BLUNT_PIN = "    assert_upload_leg_parses_off_the_event_loop(CHAT_SOURCE)"
ANCHOR_DECL = 'TABLES_ANCHOR_SHA = "58111c9"'
DERIVED_COMPARE = "    assert r304_tables_digest_on_disk() == r304_tables_digest_at(TABLES_ANCHOR_SHA), ("


# ------------------------------------------------------------------------ 真树写口记账

_EVENTS: List[str] = []
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

def _copy_tree_file(root: Path, rel: str) -> Path:
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
    root = Path(tempfile.mkdtemp(prefix="r364-shadow-"))
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
                _copy_tree_file(root, rel_file)
        shutil.copyfile(git_marker, root / ".git")  # 派生腿要读提交，副本里得认得 git
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def edit_copy(shadow: Path, rel: str, pairs: Sequence[tuple]) -> None:
    """把副本里那一枚件按字面改写：每处刀口必须**恰好命中一次**，命中数不对就中止。"""
    path = shadow / rel
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        hits = text.count(old)
        if hits != 1:
            raise AssertionError("刀口在 %s 里命中 %d 次（要求恰好 1 次）：%r" % (rel, hits, old[:56]))
        text = text.replace(old, new, 1)
    path.write_bytes(text.encode("utf-8"))


def append_copy(shadow: Path, rel: str, extra: str) -> None:
    path = shadow / rel
    raw = path.read_bytes()
    path.write_bytes(raw + extra.encode("utf-8"))


def run_pytest(shadow: Path, targets: Sequence[str]) -> dict:
    """在副本根里跑（cwd 就是副本根），读数与在真树里跑同形。"""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"] + list(targets),
        cwd=str(shadow),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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
    }


# ------------------------------------------------------------------------ 现算的账（不写死）

def git_show(rev: str, rel: str) -> bytes:
    out = subprocess.run(
        ["git", "-C", str(SOURCE_TREE), "show", "%s:%s" % (rev, rel)],
        capture_output=True,
        cwd=str(SOURCE_TREE),
    )
    assert out.returncode == 0, "git show %s:%s 读不到：%s" % (rev, rel, out.stderr.decode("utf-8", "replace")[-160:])
    return out.stdout


def git_text(*args) -> str:
    out = subprocess.run(["git", "-C", str(SOURCE_TREE), *args], capture_output=True, cwd=str(SOURCE_TREE))
    assert out.returncode == 0, "git %s 失败" % (" ".join(args))
    return out.stdout.decode("utf-8", "replace")


def anchor_rev() -> str:
    """从 r304 的具名常量里现读锚点，驱动器不抄第二份。"""
    text = (SOURCE_TREE / R304_REL).read_bytes().decode("utf-8")
    found = re.search(r'^TABLES_ANCHOR_SHA = "([0-9a-f]{7,40})"', text, re.M)
    assert found, "r304 里读不到 TABLES_ANCHOR_SHA：派生腿没源头，本驱动器拒绝继续"
    return found.group(1)


def touches_tables(rev: str) -> bool:
    listed = {
        line.strip().replace("\\", "/")
        for line in git_text("show", "--pretty=format:", "--name-only", rev).splitlines()
        if line.strip()
    }
    return TABLES_REL in listed


def identical_impostor() -> str:
    """现算一枚冒充者：与锚点逐字节相同、在祖先链上、自己没改过 tables.py。"""
    digest = hashlib.sha256(git_show(anchor_rev(), TABLES_REL)).hexdigest()
    for rev in git_text("rev-list", "--max-count=40", "HEAD").split():
        if hashlib.sha256(git_show(rev, TABLES_REL)).hexdigest() == digest and not touches_tables(rev):
            return rev
    raise AssertionError("沿 HEAD 往上 40 枚里没有一枚「与锚点同字节而没动过 tables.py」的提交：先重读现场")


# ------------------------------------------------------------------------ 刀口

def knife_synchronous_parse(root: Path) -> None:
    edit_copy(root, CHAT_REL, ((CHAT_LEG, CHAT_LEG.replace("asyncio.to_thread(load_document", "load_document"),),))


def knife_callee_outside_loader(root: Path) -> None:
    swapped = CHAT_LEG.replace("load_document,", "build_document_preview,")
    edit_copy(root, CHAT_REL, ((CHAT_LEG, swapped),))


def knife_extra_keyword(root: Path) -> None:
    edit_copy(root, CHAT_REL, ((CHAT_LEG, CHAT_LEG[:-1] + ", ocr=False)"),))


def knife_renamed_path_variable(root: Path) -> None:
    moved = (
        "            parse_target = str(storage_path)\n"
        "            content = await asyncio.to_thread(load_document, parse_target, "
        "display_name=inspection.display_filename)"
    )
    edit_copy(root, CHAT_REL, ((CHAT_LEG, moved),))


def knife_second_handoff(root: Path) -> None:
    edit_copy(root, CHAT_REL, ((CHAT_LEG, CHAT_LEG + "\n" + CHAT_LEG.replace("content = ", "content_again = ")),))


def knife_blunt_upload_pin(root: Path) -> None:
    """反例刀：把现场 A 的钉放宽成裸子串（判据③明令禁的收法），再下刀A1。"""
    edit_copy(root, UPLOAD_REL, ((BLUNT_PIN, '    assert "load_document" in CHAT_SOURCE'),))
    knife_synchronous_parse(root)


def knife_dirty_tables(root: Path) -> None:
    append_copy(root, TABLES_REL, "\n# R364 knife: an un-restored change (lives in the shadow copy only)\n")


def knife_impostor_anchor(root: Path) -> None:
    edit_copy(root, R304_REL, ((ANCHOR_DECL, 'TABLES_ANCHOR_SHA = "%s"' % identical_impostor()),))


def knife_blunt_derived_pin(root: Path) -> None:
    """反例刀：把现场 B 的派生钉写成同义反复（盘上那份跟自己比），再下刀B1。"""
    edit_copy(
        root,
        R300_REL,
        ((DERIVED_COMPARE, DERIVED_COMPARE.replace("r304_tables_digest_at(TABLES_ANCHOR_SHA)", "r304_tables_digest_on_disk()")),),
    )
    knife_dirty_tables(root)


# ------------------------------------------------------------------------ 逐把跑

def blade(title: str, mutate: Callable[[Path], None], expect: Sequence[str],
          must_stay_green: Sequence[str] = (), files: Sequence[str] = (UPLOAD_REL,),
          expect_zero: bool = False) -> dict:
    root = stage_shadow()
    try:
        mutate(root)
        reading = run_pytest(root, list(files))
        print("\n[%s] %s" % (title, reading["tail"]))
        print("    红了 %d 枚: %s" % (reading["n_failed"], ", ".join(reading["failed"]) or "(一枚都不红)"))
        if expect_zero:
            assert reading["failed"] == [], (
                "[%s] 钝化以后本来应当一枚都不红（这正是反例刀要证明的事），实际红了 %s"
                % (title, reading["failed"])
            )
        missing = [name for name in expect if name not in reading["failed"]]
        assert not missing, "[%s] 该红的没红：%s" % (title, ", ".join(missing))
        moved = [name for name in must_stay_green if name in reading["failed"]]
        assert not moved, "[%s] 这几枚本来不该红却红了：%s" % (title, ", ".join(moved))
        if must_stay_green:
            print("    该绿的绿着: %s" % ", ".join(must_stay_green))
        print("    同场通过: %d passed" % reading["n_passed"])
        return reading
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print("    副本已销毁: %s -> 仍存在: %s" % (root, root.exists()))


def main() -> int:
    baseline = {rel: hashlib.sha256((SOURCE_TREE / rel).read_bytes()).hexdigest() for rel in BASELINED}
    print("真树基线（只读）:")
    for rel in BASELINED:
        print("    %-56s %s" % (rel, baseline[rel][:16]))
    install_write_ledger()

    clean = stage_shadow()
    try:
        reading = run_pytest(clean, [UPLOAD_REL, R300_REL, R304_REL, R364_REL])
        print("\n[干净副本] %s" % reading["tail"])
        assert not reading["errored"], "副本里连收集都没跑起来，后面的读数全都不可信"
        assert reading["failed"] == [], reading["failed"]
        print("    四枚件在副本里全绿：%d passed / 0 failed" % reading["n_passed"])
        clean_passed = reading["n_passed"]
    finally:
        shutil.rmtree(clean, ignore_errors=True)
        print("    干净副本已销毁: %s -> 仍存在: %s" % (clean, clean.exists()))

    blade("刀A1 上传腿摘掉 asyncio.to_thread（退回同步解析）", knife_synchronous_parse, [PIN_UPLOAD_SHAPE])
    blade("刀A2 被调符号换成 loader 以外的东西", knife_callee_outside_loader, [PIN_UPLOAD_SHAPE])
    blade("刀A3 给那一行加一枚新 kwarg（合法演进·整件跑）", knife_extra_keyword, [],
          must_stay_green=(PIN_UPLOAD_SHAPE,), files=(UPLOAD_REL, R364_REL))
    blade("刀A3s 同一把合法刀，只跑静态那枚钉：一枚都不许红", knife_extra_keyword, [], expect_zero=True,
          files=("%s::%s" % (UPLOAD_REL, PIN_UPLOAD_SHAPE),))
    blade("刀A4 换掉持有落盘路径的变量名（合法演进）", knife_renamed_path_variable, [],
          must_stay_green=(PIN_UPLOAD_SHAPE,), files=(UPLOAD_REL, R364_REL))
    blade("刀A5 多长一枚第二处线程解析（「恰好一枚」失效）", knife_second_handoff, [PIN_UPLOAD_SHAPE])
    # 只跑那枚静态钉：runtime 那几枚在刀A1 下本来就红（桩件不认同步 await），它们红不红与"钉有没有牙"无关
    blade("刀A6（反例刀）钉放宽成裸子串以后，同一把刀A1 当场不红", knife_blunt_upload_pin, [],
          expect_zero=True, files=("%s::%s" % (UPLOAD_REL, PIN_UPLOAD_SHAPE),))

    blade("刀B1 副本里 tables.py 改坏且不还原", knife_dirty_tables, [PIN_R300_BYTES],
          must_stay_green=(PIN_R300_SELF_CHECK,), files=(R300_REL, R304_REL))
    blade("刀B2 锚点换成「逐字节相同而没改过这枚文件」的提交", knife_impostor_anchor,
          [PIN_R300_SELF_CHECK, PIN_R304_CHANGED], must_stay_green=(PIN_R300_BYTES,),
          files=(R300_REL, R304_REL))
    blade("刀B3（反例刀）派生钉钝化成同义反复后，同一把刀B1 当场不红", knife_blunt_derived_pin, [],
          must_stay_green=(PIN_R300_BYTES,), files=(R300_REL,), expect_zero=True)

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
