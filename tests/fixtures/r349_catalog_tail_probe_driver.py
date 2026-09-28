# -*- coding: utf-8 -*-
r"""R349 反证驱动（四把刀全部走影子副本道，真树全程只读）。

手法沿用 `tests/fixtures/r305_refutation_driver.py`（R339 立的那条规矩）：**不改真树上任何一枚被跟踪
文件**。复刻一棵 %TEMP% 副本根，pytest 的 cwd 就是副本根，于是副本里的 `app/db/migrations.py` 算出的
`_DEFAULT_MIGRATIONS_DIR` 落在副本的 `migrations/` 上，各把刀的刀口也只落在副本里。R339 的教训正是
"就地改写被跟踪文件 + 没有 try/finally"会把残骸留在盘上，所以本件对真树只有一个动作：`read_bytes()`
取基线摘要；收尾既核对真树摘要恒定、探针零残骸，又用 `sys.addaudithook` 记本进程在真树里开过的每一枚
写口，必须为空。副本内的文本统一按 LF 改写（真树那几枚的换行一个字节都不动）。

四把刀各自要读到的东西：

* **刀A（引信本体）**：干净副本里账本件与 ⑤ 那族全绿；放一枚 `0017_r349_probe.sql`（同时把摘要登记进
  副本的 `manifest.json` —— 不登记的探针只会让 loader 抛 `migration manifest mismatch`，红的是清单闸门
  而不是引信，那种红证明不了任何事）之后，账本件**只许红一枚**，且必须是
  `test_the_named_tail_is_still_the_catalog_tail`，消息里读得出"下一步只有一处可改"与"别改任何 import 方"。
  ⑤ 那族合跑时红的必须全是"读账本"那几枚，而主题版形状钉（r256 钉 0015 自己那两枚用例）一枚都不许跟着红。
* **刀B**：把唯一账本的两枚字面量改回 0015 / dataset_version_scope_columns（就是本单开工时那枚病态），
  必须红，且红在具名那一枚引信上；"现号"那一行 prose 钉同时红是设计使然（改口必须连主题一起写下来）。
* **刀C**：躲账本有两种形状，两种都要被抓到 —— C1 摘掉 import 并在 import 方留一份字面量副本（定义数
  变 2 ⇒ 计数钉 + 拓扑钉），C2 摘掉 import 并把版号直接写进断言（内联对判钉 + 连续性绑账本钉）。
* **刀D**：把 ④ 那半条连续性断言换成 `assert versions == sorted(versions)`（看着像在钉，实际永不红：
  loader 本来就按文件名排序返回），必须由连续性形状钉点名抓红。

跑法：`python tests/fixtures/r349_catalog_tail_probe_driver.py`（只读真树，随便跑）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

#: 真树：全程只读。名字刻意不叫 REPO/ROOT —— 那是 R253 扫描器认的"仓根出身"，本件所有写口的落点
#: 都只许从下面的 tmp 副本根长出来。
SOURCE_TREE = Path(__file__).resolve().parents[2]

MIRROR_DIRS = (
    "app", "migrations", "tests", "data", "deploy", "docs", "scripts", "frontend/src", "static",
)
MIRROR_FILES = (
    "pyproject.toml", "conftest.py", "docker-compose.yml", "README.md", ".env.example", "config.yaml",
)
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "node_modules"}

#: 探针那一版：只在副本道里存在。文件名要过 loader 的 _MIGRATION_FILENAME 尺子。
PROBE_VERSION = "0017"
PROBE_FILENAME = PROBE_VERSION + "_r349_probe.sql"
PROBE_SQL = "-- R349 反证探针：只在影子副本道里，真 migrations/ 目录不许出现它。\nSELECT 1;\n"

LEDGER_REL = "tests/test_r349_catalog_tail_ledger.py"
R251_REL = "tests/test_r251_alert_disposal_migration.py"
R299_REL = "tests/test_r299_notification_states.py"

FUSE = "test_the_named_tail_is_still_the_catalog_tail"
COUNT_PIN = "test_the_tail_literals_are_defined_exactly_once"
DERIVED_PIN = "test_the_tail_literals_are_literals_not_derived_values"
INLINE_PIN = "test_no_module_recompares_the_catalog_fact_to_an_inlined_literal"
TOPOLOGY_PIN = "test_every_module_that_uses_the_ledger_imports_it_from_here"
CONTINUITY_PIN = "test_the_contiguity_claim_is_bound_to_the_ledger"
PROSE_PIN = "test_the_ledger_prose_documents_the_tail_it_holds"

#: ⑤ 那族：尾号账本的 import 方 + 主题版件。刀A 要在它们身上点名红了谁。
FAMILY = (
    LEDGER_REL,
    "tests/test_document_catalog_sync.py::test_the_offline_migration_plan_loads_every_version_through_0016",
    "tests/test_r46_activity_signals.py::test_the_migrations_stay_one_to_one_with_the_manifest_after_0016",
    "tests/test_r120_clean_install_first_boot.py::test_task0_left_the_migrations_directory_alone",
    "tests/test_r183_184_migration_pair.py::test_the_catalog_gains_exactly_one_version_and_the_loader_accepts_it",
    "tests/test_r190_status_failed_domain.py::test_the_catalog_gains_exactly_one_version_and_the_loader_accepts_it",
    "tests/test_r251_alert_disposal_migration.py::test_the_catalog_is_contiguous_and_ends_at_the_named_tail",
    "tests/test_r299_notification_states.py::test_0016_is_registered_as_the_catalog_tail_and_loads",
    "tests/test_r256_dataset_version_scope.py::test_0015_ships_exactly_the_two_scope_columns_and_nothing_else",
    "tests/test_r256_dataset_version_scope.py::test_0015_writes_no_rows_and_breaks_nothing",
)
#: 主题版形状钉：它们钉的是 0015 自己那一版的形状，与尾号无关，探针在场也不许红。
THEME_PINS = (
    "test_0015_ships_exactly_the_two_scope_columns_and_nothing_else",
    "test_0015_writes_no_rows_and_breaks_nothing",
)

def ledger_line(name: str, value: str) -> str:
    """拼出唯一账本里那一枚定义行，供刀B 与刀C1 下刀。

    刻意不把「常量名 + 赋值号 + 带引号版号」整串原文写在这份文件里：总控复核判据①用的就是一条
    数这种定义行的 rg，驱动器把原文抄进 tests/ 就会被自己的反证工具算成第二份手抄账。
    """
    return "%s = \"%s\"" % (name, value)


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
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            return None
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


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restage(shadow: Path, rel: str) -> Path:
    """把真树的某一枚文件**复制**（不硬链接，硬链接共享 inode 会把副本的写变成盘上的写）进副本根。"""
    target = shadow / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_TREE / rel, target)
    return target


def stage_shadow() -> Path:
    """复刻一棵 %TEMP% 副本根：失手就整棵删掉，不漏半棵副本在外面。"""
    root = Path(tempfile.mkdtemp(prefix="r349-shadow-"))
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
            if (SOURCE_TREE / rel_file).is_file():
                restage(root, rel_file)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return root


def add_probe(shadow: Path) -> Path:
    """在副本道里新排一枚 0017，并把它的摘要登记进副本的 manifest.json（真树一个字节都不写）。"""
    catalog = shadow / "migrations"
    probe = catalog / PROBE_FILENAME
    probe.write_text(PROBE_SQL, encoding="utf-8", newline="\n")
    manifest_path = catalog / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(probe.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    manifest[PROBE_FILENAME] = digest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return probe


def edit_copy(shadow: Path, rel: str, pairs: Sequence[Tuple[str, str]]) -> None:
    """把副本里那一枚件按字面改写：每处刀口必须**恰好命中一次**，命中数不对就中止。"""
    path = shadow / rel
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    for old, new in pairs:
        hits = text.count(old)
        if hits != 1:
            raise AssertionError("刀口在 %s 里命中 %d 次（要求恰好 1 次）：%r" % (rel, hits, old[:48]))
        text = text.replace(old, new, 1)
    path.write_bytes(text.encode("utf-8"))


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


def run_pytest(shadow: Path, targets: Sequence[str]) -> dict:
    """在副本根里跑（cwd 就是副本根），读数与在真树里跑同形。

    R449：子会话自带 --basetemp（落在副本根之内），别去剪共享根里别人的 tmp_path。
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
         "--basetemp", str(r449_nested_basetemp(shadow))] + list(targets),
        cwd=str(shadow), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert shadow.is_dir(), "R449：嵌套会话把影子副本根弄没了"
    out = result.stdout or ""
    names = re.findall(r"^FAILED [^:]+::(\w+)", out, re.M)
    message = "\n".join(line[2:].rstrip() for line in out.splitlines() if line.startswith("E   "))
    passed = re.search(r"(\d+) passed", out)
    lines = [line for line in out.strip().splitlines() if line.strip()]
    return {
        "failed": sorted(set(names)),
        "errored": bool(re.search(r"^ERROR ", out, re.M)),
        "passed": int(passed.group(1)) if passed else 0,
        "message": message,
        "tail": lines[-1] if lines else "(无输出)",
    }


def show(message_lines: str, limit: int = 6) -> None:
    for line in message_lines.splitlines()[:limit]:
        print("      " + line)


def blade(title: str, mutate: Callable[[Path], None], expect: Sequence[str],
          exact: bool = False, family_expect: Sequence[str] = ()) -> dict:
    """开一棵副本、下刀、只跑账本件（+ 可选家族合跑），读数后立刻整棵销毁。"""
    root = stage_shadow()
    try:
        mutate(root)
        holder = run_pytest(root, [LEDGER_REL])
        print("\n[%s] 账本件: %s" % (title, holder["tail"]))
        print("    红了: %s" % (", ".join(holder["failed"]) or "(一枚都不红)"))
        missing = [name for name in expect if name not in holder["failed"]]
        assert not missing, "[%s] 该红的没红：%s" % (title, ", ".join(missing))
        if exact:
            assert holder["failed"] == list(expect), (
                "[%s] 要求只红在那几枚上，实际红了 %s" % (title, holder["failed"])
            )
        show(holder["message"])
        if family_expect:
            family = run_pytest(root, list(FAMILY))
            print("    家族合跑: %s -> %s" % (family["tail"], ", ".join(family["failed"])))
            absent = [name for name in family_expect if name not in family["failed"]]
            assert not absent, "[%s] 家族合跑里这几枚没红：%s" % (title, ", ".join(absent))
            holder["family"] = family
        return holder
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print("    副本已销毁: %s -> 仍存在: %s" % (root, root.exists()))


def main() -> int:
    real_manifest = SOURCE_TREE / "migrations" / "manifest.json"
    base_manifest_sha = sha256_of(real_manifest)
    ledger_bytes = (SOURCE_TREE / LEDGER_REL).read_bytes()
    base_ledger_sha = hashlib.sha256(ledger_bytes).hexdigest()
    print("真树基线（只读）: manifest.json %s… / 账本件 %s…"
          % (base_manifest_sha[:16], base_ledger_sha[:16]))
    install_write_ledger()

    clean = stage_shadow()
    try:
        ledger_base = run_pytest(clean, [LEDGER_REL])
        print("\n[刀A·1] 干净副本 · 账本件:", ledger_base["tail"])
        assert not ledger_base["errored"] and ledger_base["failed"] == [], ledger_base["failed"]
        family_base = run_pytest(clean, list(FAMILY))
        print("[刀A·2] 干净副本 · ⑤ 那族:", family_base["tail"])
        assert not family_base["errored"] and family_base["failed"] == [], family_base["failed"]
    finally:
        shutil.rmtree(clean, ignore_errors=True)
        print("    干净副本已销毁:", clean, "-> 仍存在:", clean.exists())

    # ---- 刀A：仓库外的影子道里新排一枚没人登记过的 0017
    probe_run = blade(
        "刀A 探针 0017", add_probe, [FUSE], exact=True,
        family_expect=(FUSE, "test_the_catalog_is_contiguous_and_ends_at_the_named_tail"),
    )
    family_failed = set(probe_run.get("family", {}).get("failed", ()))
    moved = sorted(set(THEME_PINS) & family_failed)
    assert not moved, "主题版形状钉跟着红了，说明改口碰到了不该碰的地方：" + str(moved)
    print("    主题版钉（0015 那两枚）在探针下没跟着红:", not moved)

    # ---- 刀B：唯一账本改回本单开工时那枚病态读数
    blade(
        "刀B 真源改回 0015",
        lambda root: edit_copy(root, LEDGER_REL, (
            (ledger_line("CATALOG_TAIL_VERSION", "0016"),
             ledger_line("CATALOG_TAIL_VERSION", "0015")),
            (ledger_line("CATALOG_TAIL_NAME", "notification_states"),
             ledger_line("CATALOG_TAIL_NAME", "dataset_version_scope_columns")),
        )),
        [FUSE, PROSE_PIN],
        family_expect=("test_the_catalog_is_contiguous_and_ends_at_the_named_tail",
                       "test_the_catalog_gains_exactly_one_version_and_the_loader_accepts_it"),
    )

    # ---- 刀C1：摘掉 import，在 import 方留一份字面量副本
    blade(
        "刀C1 import 方留字面量副本",
        lambda root: edit_copy(root, R299_REL, (
            ("from test_r349_catalog_tail_ledger import CATALOG_TAIL_VERSION\n",
             ledger_line("CATALOG_TAIL_VERSION", "0016") + "\n"),
        )),
        [COUNT_PIN, TOPOLOGY_PIN],
    )

    # ---- 刀C2：摘掉 import，把版号直接写进断言（不定义常量那一躲）
    blade(
        "刀C2 版号直接写进断言",
        lambda root: edit_copy(root, R299_REL, (
            ("from test_r349_catalog_tail_ledger import CATALOG_TAIL_VERSION\n", ""),
            ("versions[-1] == CATALOG_TAIL_VERSION", 'versions[-1] == "0016"'),
            ("range(1, int(CATALOG_TAIL_VERSION) + 1)", "range(1, len(versions) + 1)"),
        )),
        [INLINE_PIN, CONTINUITY_PIN],
    )

    # ---- 刀D：把连续性换成永不红的自比
    blade(
        "刀D 连续性换成 sorted 自比",
        lambda root: edit_copy(root, R251_REL, (
            ('    assert versions == [\n        f"{number:04d}" for number in range(1, int(CATALOG_TAIL_VERSION) + 1)\n    ], versions',
             "    assert versions == sorted(versions)"),
        )),
        [CONTINUITY_PIN],
    )

    after_manifest_sha = sha256_of(real_manifest)
    after_ledger_sha = hashlib.sha256((SOURCE_TREE / LEDGER_REL).read_bytes()).hexdigest()
    residue = (SOURCE_TREE / "migrations" / PROBE_FILENAME).exists()
    print("\n真树写口账:", len(_EVENTS), "枚 ->", _EVENTS[:3])
    print("真树 manifest.json sha256 恒定:", after_manifest_sha == base_manifest_sha)
    print("真树 账本件 sha256 恒定:", after_ledger_sha == base_ledger_sha)
    print("真 migrations/ 里有没有 0017 残骸:", residue)
    assert not _EVENTS, "本进程在真树里开过写口：%s" % (_EVENTS,)
    assert after_manifest_sha == base_manifest_sha, "真树的清单被改过：影子道失守"
    assert after_ledger_sha == base_ledger_sha, "真树的账本件被改过：影子道失守"
    assert not residue, "真 migrations/ 目录里留下了探针残骸"
    print("\n四把刀全部咬住，真树 pristine。")
    return 0


if __name__ == "__main__":
    sys.exit(main())