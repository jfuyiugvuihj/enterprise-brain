"""R706 · 自读钉的态分支与影子端正控：五枚反证牙，全部离线。

被治的形状有两枚红，都在 `tests/test_r496_forbidden_pin_scope.py::dropped_must_be_identical`：
 红形一（并树态）：它拿「HEAD blob 对盘上字节」复证每一枚被闸门放掉的候选。并树窗口里
   （`git apply` 之后、`git commit` 之前）盘上本来就与 HEAD 不同——那是别人那一枚单正在搬的货，
   闸门按归因放掉它是对的，复证却把「放掉」咬成「吞掉了真改动」。10-06 主树并 R700 时 state①
   唯一那枚红即此（读数 M app/api/v1/data.py），本单代码零参与。
 红形二（无 .git 的检出）：`git archive HEAD` 解出来的树里 `git ls-files` 必非零，import 期那一枚
   assert 把同批件在**收集阶段**一起拖停。
本件的牙按判据①②③④分工，一枚都不许做成永真：
 ① 并树中态·货：往 `app/**` 写一行不 commit ⇒ 钉不许红，登记账逐枚点名这一枚、态写明并树中态；
 ② 并树中态·牙：同一枚文件暂存之后再往盘上写一手（索引 blob ≠ 盘上字节）⇒ 必须红并点名；
 ③ 静止态一字不松：树静止时把一枚「HEAD 里没有、盘上长着」的路径塞进候选 ⇒ 必须红；
 ④ 正控在场：并树中态必须当场跑过 `git worktree add --detach <HEAD>` 的干净影子树，两态数字都在，
    影子树用完当场删除；静止态那一格不许悄悄建影子树（省一次 checkout，也不给「拿正控当挡箭牌」留缝）；
 ⑤ 无 .git 的检出：import 不 ERROR，被跟踪清单读不到，依赖它的钉给具名 skip。

全部离线：漂移只在 tmp_path 的影子根里造，跑完现读真树摘要自证一个字节没被碰
（`tests/test_r253_no_test_rewrites_a_tracked_file.py` 钉的就是「测试不许原地改写被跟踪文件」）。
尺一份都不新造：态分支、正控、判决本体全在被治的那枚件里，本件只把方向相反的刀架在它身上。
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
R453_SOURCE = REPO / "tests" / "test_r453_cloud_eval_override.py"
R496_SOURCE = REPO / "tests" / "test_r496_forbidden_pin_scope.py"


def _load(name: str, source: Path):
    """按路径载被治的件：尺一份都不新造，两棵树不许各拿一把。"""
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None, "载不到被治的件：%s" % source
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("r453_under_r706", R453_SOURCE)
r496 = _load("r496_under_r706", R496_SOURCE)

#: 靶子用 R700 那一笔的真手：本件不碰它，只在影子根里拿它当「别人那一枚单正在搬的货」。
MERGE_VICTIM = "app/api/v1/data.py"
DELIVERED_HAND = "deploy/compose.cloud-eval.yaml"
SEED = r496.SEED + (MERGE_VICTIM,)
#: 静止态那把刀的候选：盘上长着、HEAD 与索引里都没有——三条腿不等，静止态必须开口。
FABRICATED_REL = "docs/testing/r706-fabricated-cite.md"
ARCHIVE_FILES = ("tests/test_r453_cloud_eval_override.py", "tests/test_r496_forbidden_pin_scope.py")
SKIPPED = pytest.skip.Exception


def merged_in_tree(tmp_path: Path, tag: str) -> Path:
    """造一棵「R453 已并树、本件在此树零写入」的影子根：闸门在这一形下必须沉默（形乙）。

    先种一枚只碰交付件的 R453 号提交（历史层读得到名册，判决本体才肯往下判），再把交付件恢复到
    与 HEAD 一字不差——内容尺读不到手，此后这棵树里的脏态都是别人那一枚单的手笔。
    """
    root = mod.shadow_repo(tmp_path / ("merged-" + tag), SEED)
    r496.drift(root, DELIVERED_HAND)
    r496.commit_all(root, "R453 并树（R706 刀：%s：交付件已进 HEAD 那一形）" % tag)
    mod._git(root, "checkout", "--", DELIVERED_HAND)
    assert mod.construction_hands(root) == [], "影子根里 R453 读不出「已并树」：这一形造不出来"
    assert mod.git_status_porcelain(root) == [], "影子根种子不干净：靶子本来就脏"
    return root


def worktree_listing(root: Path) -> str:
    return mod._git(root, "worktree", "list", "--porcelain").replace("\\", "/").lower()


# ------------------------------------------------------------------ 判据③①：并树中态的货，登记，不作罪证
def test_an_uncommitted_hand_from_another_ticket_is_registered_not_accused(tmp_path: Path) -> None:
    """红形一的最小复现：干净影子根里往 `app/**` 追加一行、不 commit ⇒ 钉不许红且点名这一枚。

    R706 之前这一形读成一句「闸门放掉了真改动：app/api/v1/data.py」；之后必须是「并树中态登记」，
    态与账都留在 `READINGS_LOG` 里，判据②的影子端正控也必须已经跑过。
    """
    root = merged_in_tree(tmp_path, "goods")
    r496.drift(root, MERGE_VICTIM)                    # 别人那一枚单的手：盘上 ≠ HEAD，索引仍 = HEAD
    state = r496.read_tree_state(root)
    assert state["state"] == r496.MERGING_STATE, (
        "盘上有未提交的货却仍判静止态：态分支是空响：%s" % state)
    assert MERGE_VICTIM in state["unstaged"] and MERGE_VICTIM not in state["staged"], state
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-goods")   # 不红＝这一格治好了
    entry = r496.READINGS_LOG[-1]
    assert entry["state"] == r496.MERGING_STATE, entry
    assert any(MERGE_VICTIM in row for row in entry["registered"]), (
        "登记账没点名这一枚在飞的货：那不是逐枚点名，是悄悄跳过：%s" % entry["registered"])
    assert entry["hands"] == 0 and entry["breaches"] == 0 and entry["reg_breaches"] == 0, entry
    assert entry["control"]["head_sha"] == mod._git(root, "rev-parse", "HEAD").strip(), entry["control"]
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据③①②：暂存之后又被写一手，仍旧要咬得住
def test_a_staged_file_drifted_after_staging_turns_the_pin_red(tmp_path: Path) -> None:
    """同一枚靶子先暂存、再往盘上写一手（索引 blob ≠ 盘上字节）⇒ 必须红并点名该文件。

    这一枚是「并树中态」不永真的正牙：换坐标系不等于换判据。索引里的暂存内容就是这一形的底本，
    底本与盘上一字不差⇒登记；盘上字节又不等于它⇒闸门吞下了一次真改动。
    """
    root = merged_in_tree(tmp_path, "staged")
    target = root / MERGE_VICTIM
    target.write_bytes(target.read_bytes() + b"\n# R706 staged hand\n")
    mod._git(root, "add", MERGE_VICTIM)
    state = r496.read_tree_state(root)
    assert state["state"] == r496.MERGING_STATE and MERGE_VICTIM in state["staged"], state
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-consistent")   # 暂存与盘上一致 ⇒ 不红
    consistent = r496.READINGS_LOG[-1]
    assert any(MERGE_VICTIM in row and "暂存 blob 与盘上一字不差" in row
               for row in consistent["registered"]), consistent["registered"]
    r496.drift(root, MERGE_VICTIM)                          # 暂存之后盘上又一手 ⇒ 索引 ≠ 盘上
    with pytest.raises(AssertionError, match=re.escape(MERGE_VICTIM)):
        r496.real_tree_reading_verdict(root, tmp_path / "ctl-drift")


def test_the_gate_drops_no_candidate_whose_index_blob_differs_from_disk(tmp_path: Path) -> None:
    """判据③②的尺面版：同一份候选，暂存内容与盘上一致⇒登记，盘上又一手⇒红，两向都要量得动。"""
    root = merged_in_tree(tmp_path, "ruler")
    target = root / MERGE_VICTIM
    target.write_bytes(target.read_bytes() + b"\n# R706 staged hand\n")
    mod._git(root, "add", MERGE_VICTIM)
    state = r496.read_tree_state(root)
    candidate = ["M " + MERGE_VICTIM]
    registered = r496.dropped_must_be_identical(root, candidate, [], state)
    assert any(MERGE_VICTIM in row for row in registered), registered
    r496.drift(root, MERGE_VICTIM)
    with pytest.raises(AssertionError, match=re.escape(MERGE_VICTIM)):
        r496.dropped_must_be_identical(root, candidate, [], state)
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据①：静止态一字不松
def test_a_static_tree_still_holds_the_head_caliber(tmp_path: Path) -> None:
    """树静止（HEAD 之下没有在飞的受跟踪货）⇒ 复证照旧拿 HEAD 当底本，塞一枚真差异就得红。

    未跟踪条目不算货：主树常年挂着业主的 `?? ...`，把它算进来就等于宣布每棵树都在并树，
    态分支从此只剩「永远走松的那一条」——所以这一枚同时钉住两件事。
    """
    root = merged_in_tree(tmp_path, "static")
    planted = root / FABRICATED_REL
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text("HEAD 里没有、盘上长着的一枚新钉\n", encoding="utf-8")
    state = r496.read_tree_state(root)
    assert state["state"] == r496.STATIC_STATE, (
        "只有未跟踪新文件的一棵树被算成并树中态：那态分支等于永远走松的那一条：%s" % state)
    changed, why = r496.drop_audit(FABRICATED_REL, root, state)
    assert changed is True and "HEAD 里没有" in why, (
        "静止态里同一枚候选被放掉了：判据①那一格松了：%s | %s" % (changed, why))
    with pytest.raises(AssertionError, match="闸门放掉了真改动"):
        r496.dropped_must_be_identical(root, ["M " + FABRICATED_REL], [], state)
    assert r496.real_tree_reading_verdict(root, tmp_path / "ctl-static") is None
    assert r496.READINGS_LOG[-1]["state"] == r496.STATIC_STATE
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据②：影子端正控在场、两态数字、用完删干净
def test_the_merging_state_runs_a_clean_head_control_and_removes_it(tmp_path: Path) -> None:
    """并树中态必须当场拿 `git worktree add --detach <HEAD>` 复证同一批候选，并自证影子树已删。"""
    root = merged_in_tree(tmp_path, "control")
    head_sha = mod._git(root, "rev-parse", "HEAD").strip()
    r496.drift(root, MERGE_VICTIM)
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-control")
    control = r496.READINGS_LOG[-1]["control"]
    assert control["head_sha"] == head_sha, (
        "影子端正控读的不是这棵树的 HEAD：两态数字对不上账：%s vs %s" % (control["head_sha"], head_sha))
    assert MERGE_VICTIM in control["rels"], control["rels"]
    assert all(row[0] is False for row in control["readings"].values()), control["readings"]
    tree = Path(control["shadow_tree"])
    assert str(tmp_path) in str(tree), "影子树建在本单视野之外：%s" % tree
    assert control["removed"] is True and not tree.exists(), "影子树用完没删干净：%s" % tree
    assert str(tree).replace("\\", "/").lower() not in worktree_listing(root), (
        "工作树名册里还挂着影子树：%s" % tree)
    r496.real_tree_untouched()


def test_a_static_tree_builds_no_shadow_worktree(tmp_path: Path) -> None:
    """静止态不需要正控：不许每一轮门都白付一次 checkout，也不给「拿正控当挡箭牌」留缝。"""
    root = merged_in_tree(tmp_path, "quiet")
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-quiet")
    control = r496.READINGS_LOG[-1]["control"]
    assert "skipped_reason" in control, control
    assert "r706-head-shadow" not in worktree_listing(root), mod._git(root, "worktree", "list")


# ------------------------------------------------------------------ 判据④：无 .git 的检出不许拖停整批
def archive_tree(tmp_path: Path) -> Path:
    """`git archive HEAD` 解出来的一枚无库目录，再把盘上字节盖进去（要测的是今天这两本件）。"""
    proc = subprocess.run(
        ["git", "-c", "core.quotePath=false", "archive", "--format=tar", "HEAD", "--", *ARCHIVE_FILES],
        cwd=str(REPO), capture_output=True)          # tar 是字节流，不许 text=True
    assert proc.returncode == 0, "取不到导出树：" + proc.stderr[:200].decode("utf-8", "replace")
    dest = tmp_path / "archive-tree"
    dest.mkdir(parents=True, exist_ok=True)
    bundle = tarfile.open(fileobj=BytesIO(proc.stdout), mode="r:")
    try:
        bundle.extractall(dest, filter="data")
    except TypeError:                      # 老运行时没有 filter 这一档
        bundle.extractall(dest)
    for rel in ARCHIVE_FILES:
        (dest / rel).write_bytes((REPO / rel).read_bytes())
    assert not (dest / ".git").exists(), "导出树里长出了 .git：这一形就没测到无库检出"
    return dest


def test_an_archive_checkout_needs_no_git_and_skips_by_name(tmp_path: Path) -> None:
    """红形二：无 .git 的检出里 import 不 ERROR（收集阶段不拖停同批），依赖被跟踪清单的钉给具名 skip。"""
    tree = archive_tree(tmp_path)
    assert mod.checkout_shape(tree) == mod.ARCHIVE_SHAPE
    assert mod.tracked_paths(tree) is None, "无库的检出里清单读成了非 None：第三形没生效"
    assert mod.tracked_manifest(tree) is None
    archive_r453 = _load("r453_under_archive", tree / ARCHIVE_FILES[0])
    assert archive_r453.REPO == tree, "载来的件认错了根：%s" % archive_r453.REPO
    assert archive_r453.CHECKOUT_SHAPE_AT_RUN_START == mod.ARCHIVE_SHAPE
    assert archive_r453.MANIFEST_READABLE_AT_RUN_START is False, (
        "import 那一刻没认出无库检出：跑前读数会把同批件拖停在收集阶段")
    assert archive_r453.RUN_START_TREE_SHA == mod.digest_of({})
    archive_r496 = _load("r496_under_archive", tree / ARCHIVE_FILES[1])
    for name, call in (
        ("真树自读那枚钉", lambda: archive_r496.real_tree_reading_verdict(tree, tmp_path / "ctl-archive")),
        ("禁域活体钉", archive_r453.forbidden_overreach_verdict),
        ("在册件活体钉", archive_r453.registered_overreach_verdict),
        ("挂号提交名册", archive_r453.signed_commit_overreach_verdict),
    ):
        with pytest.raises(SKIPPED, match=re.escape(mod.NO_CHECKOUT_SKIP)):
            call()
        assert name
    assert archive_r496.SEED and archive_r496.STATIC_STATE      # 件在导出树里载得动：收集阶段有牙可跑
    r496.real_tree_untouched()
