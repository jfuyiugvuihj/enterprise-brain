# -*- coding: utf-8 -*-
r"""R356 / R357 反证驱动（五把刀全部走影子副本道，真树全程只读）。

手法沿用 `tests/fixtures/r349_catalog_tail_probe_driver.py`（它又沿用 R339 从 R253 抄回来的
那条规矩）：**一枚被跟踪文件都不就地改写**。复刻一棵 %TEMP% 副本根，pytest 的 cwd 就是副本根，
于是 `import app` 解析到副本里的 `app/**`，刀口也只落在副本里。对真树只有一个动作：
`read_bytes()` 取基线摘要；收尾既逐枚核对真树摘要恒定，又用 `sys.addaudithook` 记账本进程在
真树里开过的每一枚写口，必须为空。

文件名不带 `test_` 前缀 ⇒ pytest 不收（副本道驱动器不进收集面，同 R349 那枚）。

五把刀各自要读到的东西（判据⑩：三把正刀 + 两把反例刀）：

* **刀1（⑧ 的差集钉有没有牙）**：往 `ROLE_PERMISSIONS` 加一枚新角色 `ghost`，可创建集合一个字
  不动 ⇒ 两枚「差集恰好 auditor 一枚」钉必须红。顺手看那条同一性钉（有档位才可创建）也跟着红，
  这说明"补了档位没人回答准入"这条道今天也咬得住。
* **刀2（⑦ 的真源尺子有没有牙）**：把 `app/common/auth.py:552`（这枚行号是基点 87cc617 的现场）那格改回开工时那枚手抄三元组 ⇒
  "生产代码里不许长出第二份角色名单"与"auth.py 判两次 CREATABLE_ROLES"两枚必须同时红。
* **刀3（①③ 那张 503 脸有没有牙）**：让 `_memory_store_denied` 为真时仍然回空名册（把
  `raise UserStoreUnavailable` 换成 `return []`）⇒ 503 那族钉必须红，而且红在读不到 503 的那些格上。
* **刀4（反例刀，证明原尺子更强）**：把两枚差集钉从 `== {"auditor"}` 钝化成 `>= {"auditor"}`，
  再下同一把刀1 ⇒ 这两枚钝化的钉**不红**（绿），而没被钝化的那枚同一性钉照样红。这就是
  "把四处都改成对的值"那种收法为什么不算修好：钝刀下漂移是看不见的。
* **刀4b（同一件事的另一种钝化写法）**：差集钉换成 `not wider.isdisjoint({"auditor"})`，再下刀1
  ⇒ 照样一枚都不红。`>=` 与 `isdisjoint` 两枚样本都在，钝刀不是只挑中了一枚巧合。

跑法：`.venv\Scripts\python.exe tests/fixtures/r356_r357_refutation_driver.py`（只读真树，随便跑）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Sequence

#: 真树：全程只读。名字刻意不叫 REPO/ROOT——那是 R253 扫描器认的"仓根出身"，本件所有写口的
#: 落点都只许从下面的 tmp 副本根长出来。
SOURCE_TREE = Path(__file__).resolve().parents[2]

#: `migrations/` 必须在副本里：`app/main.py:61` 导入期就要 `_verify_migration_catalog()`，
#: 而 `app/db/migrations.py:148` 对不存在的目录直接 raise——少镜像它，七枚用例全报 ERROR，
#: 那种红证明不了任何事（本单实测踩过一次，写在这里给下一个人省一轮）。
MIRROR_DIRS = ("app", "tests", "data", "migrations", "scripts", "deploy")
MIRROR_FILES = ("pyproject.toml", "conftest.py", "config.yaml", ".env.example")
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".pytest_cache", ".venv", "node_modules"}

R356_REL = "tests/test_r356_users_refusal_face.py"
R357_REL = "tests/test_r357_single_role_roster.py"
PERMISSIONS_REL = "app/common/permissions.py"
AUTH_REL = "app/common/auth.py"

#: 本单动过与判过的每一枚文件：收尾逐枚复对摘要，证明四把刀都只落在副本里。
BASELINED = (
    PERMISSIONS_REL,
    AUTH_REL,
    "app/common/sso.py",
    "app/common/rbac.py",
    "app/api/v1/auth.py",
    R356_REL,
    R357_REL,
)

# 具名钉（字符串只出现在这里一次，刀口期望值也从这里取，避免驱动器自己变成第二本手抄账）。
PIN_WIDER_ADMISSION = "test_the_permission_ledger_is_exactly_one_role_wider_than_the_admission_ledger"
PIN_WIDER_CLEARANCE = "test_the_permission_ledger_is_exactly_one_role_wider_than_the_clearance_ledger"
PIN_SAME_TIER_RULE = "test_the_gap_has_one_reason_and_it_is_the_missing_clearance_tier"
PIN_NO_SECOND_ROSTER = "test_no_module_in_production_code_carries_a_second_role_roster"
PIN_AUTH_TWO_CHECKS = "test_auth_asks_the_true_source_twice_and_keeps_no_copied_tuple"
PIN_503_FACE = "test_the_route_answers_503_when_the_user_store_refuses_the_roster"
PIN_NEVER_EMPTY_ROSTER = "test_a_refusal_is_never_rendered_as_an_empty_roster"
PIN_HELPER_RAISES = "test_the_helper_raises_a_typed_refusal_when_asked_for_the_truthful_shape"
PIN_THREE_FACES = "test_the_three_faces_share_no_words"

AUDITOR_ONLY = 'assert wider == {"auditor"}, f"权限面比准入宽出的不是恰好 auditor 一枚：{sorted(wider)}"'
AUDITOR_ONLY_CLEARANCE = 'assert wider == {"auditor"}, f"权限面比密级面宽出的不是恰好 auditor 一枚：{sorted(wider)}"'
AUDITOR_ENTRY = '    "auditor": frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT}),'
COPY_BACK = "    if role not in CREATABLE_ROLES:  # R357：真源在 app/common/permissions.py，本处只 import"
RAISE_SITE = '            raise UserStoreUnavailable("user listing")'


def sha256_of(rel: str) -> str:
    import hashlib

    return hashlib.sha256((SOURCE_TREE / rel).read_bytes()).hexdigest()


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


def _copy_into(root: Path, rel: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_TREE / rel, target)
    return target


def stage_shadow() -> Path:
    """复刻一棵 %TEMP% 副本根：失手就整棵删掉，不漏半棵副本在外面。"""
    root = Path(tempfile.mkdtemp(prefix="r356r357-shadow-"))
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
    }


# ---------------------------------------------------------------------- 四把刀的刀口


def knife_new_role_in_permission_ledger(root: Path) -> None:
    edit_copy(root, PERMISSIONS_REL, ((AUDITOR_ENTRY, AUDITOR_ENTRY + '\n    "ghost": frozenset({ACTION_VIEW}),'),))


def knife_hand_copied_tuple(root: Path) -> None:
    edit_copy(root, AUTH_REL, ((COPY_BACK, '    if role not in ("staff", "manager", "admin"):'),))


def knife_refusal_poses_as_empty_roster(root: Path) -> None:
    edit_copy(root, AUTH_REL, ((RAISE_SITE, "            return []"),))


def knife_blunt_difference_pins(root: Path) -> None:
    """反例刀：把两枚差集钉钝化成 `>=`，再下同一把刀1。"""
    edit_copy(root, R357_REL, (
        (AUDITOR_ONLY, AUDITOR_ONLY.replace("== {", ">= {")),
        (AUDITOR_ONLY_CLEARANCE, AUDITOR_ONLY_CLEARANCE.replace("== {", ">= {")),
    ))
    knife_new_role_in_permission_ledger(root)


def knife_blunt_difference_pins_isdisjoint(root: Path) -> None:
    """反例刀 4b：把两枚差集钉钝化成 `not wider.isdisjoint({"auditor"})`，再下同一把刀1。

    判据⑩给的是「`>=` 或 `isdisjoint`」，两枚都试一遍，钝刀的形状就不只剩一枚样本。
    """
    blunt = "not wider.isdisjoint({\"auditor\"})"
    edit_copy(root, R357_REL, (
        (AUDITOR_ONLY, AUDITOR_ONLY.replace('wider == {"auditor"}', blunt)),
        (AUDITOR_ONLY_CLEARANCE, AUDITOR_ONLY_CLEARANCE.replace('wider == {"auditor"}', blunt)),
    ))
    knife_new_role_in_permission_ledger(root)


def blade(title: str, mutate: Callable[[Path], None], expect: Sequence[str],
          must_stay_green: Sequence[str] = (), files: Sequence[str] = (R356_REL, R357_REL),
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
        return reading
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print("    副本已销毁: %s -> 仍存在: %s" % (root, root.exists()))


def main() -> int:
    import hashlib

    baseline = {rel: hashlib.sha256((SOURCE_TREE / rel).read_bytes()).hexdigest() for rel in BASELINED}
    print("真树基线（只读）:")
    for rel in BASELINED:
        print("    %-52s %s" % (rel, baseline[rel][:16]))
    install_write_ledger()

    clean = stage_shadow()
    try:
        reading = run_pytest(clean, [R356_REL, R357_REL])
        print("\n[干净副本] %s" % reading["tail"])
        assert not reading["errored"], "副本里连收集都没跑起来，后面的读数全都不可信"
        assert reading["failed"] == [], reading["failed"]
        print("    两枚新件在副本里全绿：%d passed / 0 failed" % reading["n_passed"])
        clean_passed = reading["n_passed"]
    finally:
        shutil.rmtree(clean, ignore_errors=True)
        print("    干净副本已销毁:", clean, "-> 仍存在:", clean.exists())

    blade("刀1 ROLE_PERMISSIONS 加一枚 ghost（可创建集合不动）", knife_new_role_in_permission_ledger,
          [PIN_WIDER_ADMISSION, PIN_WIDER_CLEARANCE], must_stay_green=(PIN_SAME_TIER_RULE,))
    blade("刀2 auth.py 改回手抄三元组", knife_hand_copied_tuple, [PIN_NO_SECOND_ROSTER, PIN_AUTH_TWO_CHECKS])
    blade("刀3 拒答仍伪装成空名册", knife_refusal_poses_as_empty_roster,
          [PIN_503_FACE, PIN_NEVER_EMPTY_ROSTER, PIN_HELPER_RAISES, PIN_THREE_FACES],
          files=(R356_REL,))
    blade("刀4（反例刀）差集钉钝化成 >= 后，刀1 当场不红", knife_blunt_difference_pins,
          [], must_stay_green=(PIN_WIDER_ADMISSION, PIN_WIDER_CLEARANCE, PIN_SAME_TIER_RULE),
          files=(R357_REL,), expect_zero=True)
    blade("刀4b（反例刀·另一种钝化写法）差集钉钝化成 isdisjoint 后，同一把刀1 同样不红",
          knife_blunt_difference_pins_isdisjoint, [],
          must_stay_green=(PIN_WIDER_ADMISSION, PIN_WIDER_CLEARANCE, PIN_SAME_TIER_RULE),
          files=(R357_REL,), expect_zero=True)

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
