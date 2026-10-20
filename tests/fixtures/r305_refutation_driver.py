"""R305 反证驱动：逐把摘刀 -> 跑完整本用例 -> 记录红了哪几条 -> 副本按字节还原，真树全程只读。

R339 把这具驱动器搬回影子副本道。口径不是新发明的：
`tests/test_r253_no_test_rewrites_a_tracked_file.py:14` 的规则原文就写着「把被跟踪文件的名字当
**后缀**拼到 tmp 副本根下面」不算点名盘上那枚（R218 那三件今天就这么写），
`tests/_temp_edit_overlay.py` 是同一格在测试进程里的那一半。原形状是把**真树上的**
`app/rag/spreadsheets.py` 就地改坏、跑完再还原，而 `main()` 里没有 try/finally：中途 Ctrl-C、
崩机、机器休眠（09-20 夜四枚 Agent 被冻一整夜那一族）都会把摘了刀的源文件留在盘上，而 git 只在
有人去查的时候才看得见。它同时也是 R253 那枚闭合钉自 R305 并树 `01db964` 起读红的唯一一处。

副本根落在 %TEMP%，复刻 `app/` + `data/` + `tests/` 与两枚配置件，pytest 的 cwd 就是副本根：

  - 被测模块从副本根导入：进门先用一枚同 cwd、同解释器的子进程探针核对
    `app.rag.spreadsheets.__file__` 确实落在副本里，探针不通就直接停，不带着假牙往下跑；
  - 本件那几枚「读源码取证」的用例（`MODULE_SOURCE` / `pyproject.toml`）因此与就地改写那一道
    看见同一份变异字节，七把刀逐把同形（读数见 R339 回执）；
  - 真树那一枚只被 `read_bytes()` 读过：跑前取基线字节与终稿 sha256，跑完再核对一次；
    本进程另装一枚只读账（`sys.addaudithook`），凡在真树里开写口就当场记一笔，收尾必须是空表。

换行照仓库工作树（CRLF）：基线先归一成 \n 再摘刀，写回副本时还原成 CRLF，所以副本与真树同一枚 sha。
重跑：`python tests/fixtures/r305_refutation_driver.py`。
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: 真树：全程只读。名字刻意不叫 ROOT/REPO——那几枚是 R253 扫描器认的「仓根出身」，
#: 而本件所有写口的落点都只许从下面的 tmp 副本根长出来。
SOURCE_TREE = Path(__file__).resolve().parents[2]
MODULE_REL = "app/rag/spreadsheets.py"
TEST_REL = "tests/test_r305_spreadsheets.py"

#: 复刻的目录：app = 被测码 + 三枚禁域对照件，data = 两枚存量真件，tests = 用例与 conftest 链。
MIRROR_DIRS = ("app", "data", "tests")
#: 复刻的单文件：`test_no_new_dependency_is_needed` 要读 pyproject，仓库根 conftest 是 R134 的钉子。
MIRROR_FILES = ("pyproject.toml", "conftest.py")
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache"}

BLADES = [
    ("a 空行不再去掉", "        if not any(line):\n            grid.blank_rows += 1\n            continue\n",
     "        if not any(line):\n            grid.blank_rows += 1\n        if False:\n            continue\n"),
    ("b 合并区域不广播", "    for merge in worksheet.merged_cells.ranges:\n",
     "    for merge in []:\n"),
    ("c 表名里的锚点分隔符不替换", '    cleaned = _cell_text((name or "").replace(ANCHOR_JOIN, " "))\n',
     "    cleaned = _cell_text(name or \"\")\n"),
    ("d 读侧给浮点二次取整", "    return _cell_text(value)\n\n\n@dataclass\nclass _Grid:",
     "    return _cell_text(round(value, 2) if isinstance(value, float) else value)\n\n\n@dataclass\nclass _Grid:"),
    ("e 分隔符不 sniff，硬编逗号", "    chosen = delimiter or sniff_delimiter(text.splitlines())\n",
     "    chosen = delimiter or \",\"\n"),
    ("f 字符顶不裁行（整块照发）", "    if kept >= block.row_count:\n        return block, 0\n",
     "    return block, 0\n"),
    ("g CSV 不走 load_txt，自己按 utf-8 读", "    text = load_txt(str(path))\n",
     "    text = path.read_bytes().decode(\"utf-8\")\n"),
]

#: 本进程里「在真树中开过写口」的每一次现场：与 R253 伴生钉同一手法，收尾必须是空表。
_EVENTS: list = []
_HOOKED = False
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_WRITE_MODES = set("wax+")


def _abs_of(path):
    if isinstance(path, int):                 # 已经是 fd：落点在装钩子之前就定了
        return None
    try:
        text = os.fspath(path)
    except TypeError:
        return None
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return os.path.abspath(text)


def _within(target: str, parent: Path) -> bool:
    head = os.path.normcase(str(parent)) + os.sep
    return os.path.normcase(target).startswith(head)


def install_write_ledger() -> None:
    """装一枚只读的账：谁在真树里开写口就记谁。装第二遍是空操作。"""
    global _HOOKED
    if _HOOKED:
        return

    def ledger(event, args):
        if event != "open" or not args:
            return
        target = _abs_of(args[0])
        if target is None or not _within(target, SOURCE_TREE):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        writing = (isinstance(flags, int) and bool(flags & _WRITE_FLAGS)) \
            or (isinstance(mode, str) and bool(_WRITE_MODES & set(mode)))
        if writing:
            _EVENTS.append((target, mode, flags))

    sys.addaudithook(ledger)
    _HOOKED = True


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restage(root: Path, rel: str) -> Path:
    """副本里的某枚文件回到真树的字，并交回它的位置：每把刀的基线都从这里长出来。"""
    tracked = SOURCE_TREE / rel
    if not tracked.is_file():
        raise AssertionError("真树里没有这枚基线：%s" % tracked)
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    shutil.copyfile(tracked, target)
    return target


def stage_shadow() -> Path:
    """立起副本根：只复制，不硬链接——硬链接共享 inode，穿过它写副本就是写盘上那枚。"""
    root = Path(tempfile.mkdtemp(prefix="r339-shadow-"))
    try:
        for rel_dir in MIRROR_DIRS:
            base = SOURCE_TREE / rel_dir
            if not base.is_dir():
                raise AssertionError("副本根要复刻的目录不在：%s" % base)
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
                here = root / Path(dirpath).relative_to(SOURCE_TREE)
                here.mkdir(parents=True, exist_ok=True)
                for name in sorted(files):
                    shutil.copyfile(Path(dirpath) / name, here / name)
        for rel_file in MIRROR_FILES:
            restage(root, rel_file)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)   # 立到一半失手：不把半棵副本漏在 %TEMP%
    return root


def r449_nested_basetemp(parent_scratch: Path) -> Path:
    """R449：每一枚嵌套 pytest 会话只用自己的 basetemp，落点必须在父件 scratch 之内。

    不传 --basetemp 时子会话落进 `%TEMP%\\pytest-of-<user>` 那枚共享根（跟进单 §123 第四节）：
    每枚会话收尾都要剪该根下的旧编号目录（默认只留最近 3 枚，`.lock` 一过期照剪不误），
    并发时别人正在用的 tmp_path 就有被剪掉的一天 —— 那是门自己造的假红，不是产品缺陷。
    本件的父 scratch 就是影子副本根，所以子会话的残骸跟着副本一起 rmtree，一处都不留在 %TEMP%。
    判据①由 tests/test_r449_nested_pytest_basetemp_contract.py 机检，漏一处当场点名。
    """
    root = Path(parent_scratch) / "r449-nested-basetemp"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="child-", dir=str(root)))


def run_tests(shadow: Path):
    """在副本根里跑完整本用例（cwd 就是副本根），读数与在真树里跑同形。

    R449：子会话自带 --basetemp（落在副本根之内），别去剪共享根里别人的 tmp_path。
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", TEST_REL, "-q", "--no-header", "-p", "no:cacheprovider",
         "--basetemp", str(r449_nested_basetemp(shadow))],
        cwd=str(shadow), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert shadow.is_dir(), "R449：嵌套会话把影子副本根弄没了"
    out = result.stdout
    names = sorted(re.findall(r"^FAILED .*::(\w+)", out, re.M))
    tally = re.search(r"(\d+) failed, (\d+) passed", out)
    error = re.search(r"^ERROR tests/\w+", out, re.M)
    passed = re.search(r"(\d+) passed", out)
    return (int(tally.group(1)) if tally else 0), len(names), names, bool(error), int(passed.group(1)) if passed else 0


def imported_target(shadow: Path) -> str:
    """探针：同 cwd、同解释器问一句「`app.rag.spreadsheets` 落在哪」——被测那份必须来自副本根。"""
    probe = subprocess.run(
        [sys.executable, "-c", "import app.rag.spreadsheets as m; print(m.__file__)"],
        cwd=str(shadow), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return (probe.stdout or "").strip()


def main() -> int:
    tracked = SOURCE_TREE / MODULE_REL
    original = tracked.read_bytes()                          # 真树唯一一次被读：取基线字节
    base_sha = hashlib.sha256(original).hexdigest()
    print("真树终稿 sha256:", base_sha[:16], "bytes:", len(original), "（只读）")
    install_write_ledger()

    shadow = stage_shadow()
    rows = []
    try:
        copy = restage(shadow, MODULE_REL)
        assert copy.read_bytes() == original, "副本基线与真树逐字节不等：复刻没做对"
        landing = imported_target(shadow)
        assert _within(landing, shadow), "被测模块不是从副本根导入的：%s" % landing
        print("被测模块落点:", landing)

        failed, _count, names, errored, passed = run_tests(shadow)
        print("基线（未摘刀，副本根内）: 红 %d / 通过 %d / collection error: %s" % (failed, passed, errored))
        for item in names[:14]:
            print("    ·", item)
        assert not errored and failed == 0 and passed >= 40, "基线不干净：下面七把的读数不算数"

        for name, old, new in BLADES:
            text = original.decode("utf-8").replace("\r\n", "\n")
            assert old in text, f"{name}: 找不到刀口 {old[:32]!r}"
            copy.write_bytes(text.replace(old, new, 1).replace("\n", "\r\n").encode("utf-8"))
            failed, _count, names, errored, _passed = run_tests(shadow)
            print(f"\n[{name}] -> 影子根红 {failed} 枚" + ("（含 collection error）" if errored else ""))
            for item in names[:14]:
                print("    ·", item)
            assert copy.read_bytes() != original, "刀没摘下去"
            assert failed >= 1, f"[{name}] 摘刀以后一枚都不红：这一把的牙是空的"
            rows.append((name, failed, tuple(names)))
            copy.write_bytes(original)                       # 还原的只有副本
            assert hashlib.sha256(copy.read_bytes()).hexdigest() == base_sha, "副本还原失败"
    finally:
        shutil.rmtree(shadow, ignore_errors=True)
        print("\n副本根已销毁:", shadow, "-> 仍存在:", shadow.exists())

    print("\n逐把读数（摘刀前基线 0 红）:")
    for name, failed, names in rows:
        distinct = ", ".join(sorted(set(names)))
        print("  [%s] 影子根红 %d 枚 :: %s" % (name, failed, distinct))
    after = sha256_of(tracked)
    print("真树写口账:", len(_EVENTS), "枚 ->", _EVENTS[:3])
    print("跑完真树 sha256:", after[:16], "== 终稿 ->", after == base_sha)
    assert not _EVENTS, "本进程在真树里开过写口：%s" % (_EVENTS,)
    assert after == base_sha, "真树里那枚被跟踪文件被改过：影子道失守"
    return 0


if __name__ == "__main__":
    sys.exit(main())