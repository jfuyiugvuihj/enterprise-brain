"""R496 · 禁域自护钉的作用域：两把方向的刀，都走影子副本道。

病根（09-29 主树并 R471 现场，凭据在主树 commit 438d67d 的 subject）：
`tests/test_r453_cloud_eval_override.py` 里那两枚盘面钉拿「工作树此刻相对 HEAD 脏」当「本单越界」的证据。
R471 合法改过在册量具 `scripts/eval_transport_ask_v2.py`，两枚钉替它各红一次（原文
`AssertionError: 在册件被改动：['M scripts/eval_transport_ask_v2.py']`），总控提交后再跑同一枚钉自己转绿。
红的时候指控错了人，绿的时候又等于没测——一枚常驻钉把不属于本单的盘面状态当成了本单的罪证。

本件只干一件事：把「改对了」钉成两个方向都能证伪的形状。
④ 假红必须消失：本单交付件一枚没动、别人家合法改了 `scripts/eval_transport_ask_v2.py` ⇒ 两枚钉必须沉默；
   同一把刀还要证明「不套闸门的旧读数」确实红，否则这枚沉默是空响。
⑤ 真越界必须还红：本单施工指纹为真（动一枚交付件）同时 `app/**` 一枚在册件为 `M` ⇒ 必须红且点名文件；
   `tests/test_evaluation_report.py`、`scripts/run_gate.py`、`docs/testing`、`frontend/**` 同一把刀各来一次。
外加一把补旧钉盲点的刀：越界随交付一起提交（并树那一刻盘面干净、活体钉绿）⇒ 挂号提交名册必须点名。

全部离线：漂移只在 tmp_path 的影子根里造；每把跑完现读真树全集摘要，必须与 import 那一刻逐字相等。
尺一份都不新造：判决本体取自被治的那枚件（`importlib` 按路径载），两棵树不许各拿一把尺。

R706（10-06 返工）· 本件的自读钉 `dropped_must_be_identical` 从此**先分这棵树的状态再取证**：
 静止态（HEAD 之下没有在飞的受跟踪货）一字不松，照旧拿 HEAD blob 对盘上字节；并树中态
 （`git apply` 之后、`git commit` 之前那一段时间）改判索引 blob 对盘上字节，HEAD↔索引／HEAD↔盘上
 那一截差异逐枚点名登记，不作罪证。10-06 主树并 R700 时 state① 唯一那枚红就是这枚钉收的：
 闸门按归因放掉 `app/api/v1/data.py`（R700 的手），复证却拿 HEAD 当底本，于是「放掉了一条真改动」。
 🔴 不是「脏就跳过」：跳过＝摘牙。并树中态当场再拿一枚 `git worktree add --detach <HEAD>` 的干净
 影子树作**正控**（同一枚 `content_verdict`、同一批候选、同一枚 HEAD sha），两态数字记进 `READINGS_LOG`
 供凭据纸取数，影子树用完当场 `git worktree remove` 并自证名册里读不到它。
 刀：`tests/test_r706_state_branch_disk_pins.py`（静止态不松／暂存后又改必须红／未暂存的货不许红／
 无 .git 的检出具名 skip）。
"""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "tests" / "test_r453_cloud_eval_override.py"


def _load_under_test():
    spec = importlib.util.spec_from_file_location("r453_override_under_r496_knife", SOURCE)
    assert spec is not None and spec.loader is not None, "载不到被治的那枚件：%s" % SOURCE
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_under_test()

#: 刀要的种子：本单交付件（施工指纹读它）＋禁域在册件（越界判据读它）＋无关在册件（对照用）。
SEED = (
    "deploy/compose.cloud-eval.yaml",
    "scripts/eval_cloud_window_readout.py",
    "tests/test_r453_cloud_eval_override.py",
    "tests/test_r453_cloud_shape_caliber.py",
    "tests/test_r453_default_env_baseline.py",
    "tests/test_r453_nested_pytest_selection_guard.py",
    "scripts/eval_transport_ask_v2.py",
    "scripts/run_gate.py",
    "tests/test_evaluation_report.py",
    "app/agents/nodes.py",
    "app/common/model_config.py",
    "frontend/.gitignore",
    "docker-compose.yml",
    "pyproject.toml",
    "docs/testing/evaluation-30.md",
)

#: 判据②要求「一枚不许少」：这枚地板就是 R496 动手前的原样名单，删路径换绿当场红。
FORBIDDEN_FLOOR = (
    "app", "frontend", "docker-compose.yml", "deploy/docker-compose.server.yml",
    "deploy/docker-compose.tls.yml", "deploy/.env.server.example", "deploy/.env.server",
    "scripts/eval_transport_ask_v2.py", "scripts/run_gate.py", "tests/test_evaluation_report.py",
    "pyproject.toml", "docs/testing",
)
REGISTERED_FLOOR = (
    "docker-compose.yml", "deploy/.env.server.example", ".env.example",
    "deploy/docker-compose.server.yml", "scripts/eval_transport_ask_v2.py", "scripts/run_gate.py",
    "tests/test_evaluation_report.py", "app/agents/nodes.py", "app/common/model_config.py",
    "app/common/model_handler.py", "pyproject.toml", "AGENTS.md",
)

FOREIGN_CALIBER_NOTE = b"\n# R471 caliber: derived inline from frames[].sha, no new column.\n"


def drift(root: Path, rel: str, extra: bytes = b"\n# drifted one byte\n") -> str:
    """影子根里把一枚在册件改一格。真树一个字都不动（每把末尾自证）。"""
    path = root / rel
    path.write_bytes(path.read_bytes() + extra)
    return rel


def commit_all(root: Path, subject: str) -> str:
    mod._git(root, "add", "-A")
    mod._git(root, "-c", "user.name=r496-knife", "-c", "user.email=r496@knife.invalid",
             "commit", "-q", "-m", subject)
    return mod._git(root, "rev-parse", "HEAD").strip()


def real_tree_untouched() -> None:
    assert mod.digest_of(mod.tracked_manifest(mod.REPO) or {}) == mod.RUN_START_TREE_SHA, (
        "刀说是在影子根里造漂移，真树却被碰脏了——这正是 09-28 越界那一笔换成的这个形")


# ------------------------------------------------------------------ R706 态分支（先分状态，再取证）
#: 静止态＝HEAD 之下没有在飞的受跟踪货（索引与盘上逐枚等 HEAD）；并树中态＝`git apply` 之后、
#: `git commit` 之前那一段时间——索引或盘上本来就与 HEAD 不同，那是别人那一枚单正在搬的货。
#: 未跟踪条目不算货：主树常年挂着业主的 `?? ...`，把它算进来就等于宣布每棵树都在并树。
STATIC_STATE = "静止态"
MERGING_STATE = "并树中态"
#: 并树中态里被放掉的候选的凭据前缀（判据①：那一截差异逐枚点名登记、不作罪证）。
REGISTERED_PREFIX = "并树中态登记"

#: 供凭据纸取数（判据②要两态数字）：每一枚 `real_tree_reading_verdict` 现读现 append 一条账。
READINGS_LOG: list[dict] = []

#: 影子端正控的路径前缀：带 pid 与序号，同批并发各建各的，只删自己建的那一枚。
SHADOW_WORKTREE_PREFIX = "r706-head-shadow"
SHADOW_SERIAL = [0]


def read_tree_state(root: Path) -> dict:
    """现取这棵树的状态：`git diff --cached --name-only`（HEAD↔索引）＋ `git status --porcelain`（索引↔盘上）。

    两枚读数一律现取（判据①禁手抄、禁引用几分钟前的旧账）；`entries` 那种注入读数不参与分态，
    分态只认这棵树自己此刻的 git 回答——注入的行是「git 若说谎时会打印的那几行」，不是盘面事实。
    """
    staged = set(mod._git_read(root, "diff", "--name-only", "-z", "--no-renames", "--cached", sep="\0"))
    unstaged = set()
    for line in mod.git_status_porcelain(root):
        xy, raw = line[:2], line[3:].strip().replace("\\", "/")
        if xy.strip() == "??":
            continue
        if len(xy) == 2 and xy[1] != " ":
            unstaged.add(raw.split(" -> ")[0].strip())
    delta = sorted(staged | unstaged)
    return {"state": MERGING_STATE if delta else STATIC_STATE,
            "staged": sorted(staged), "unstaged": sorted(unstaged), "delta": delta}


def merge_drop_verdict(rel: str, root: Path, staged: set[str]) -> tuple[bool, str]:
    """并树中态下「被闸门放掉的候选」的复证：三条腿里改判另两条——索引 blob 对盘上字节。

    HEAD↔索引／HEAD↔盘上那一截是这棵树在飞的货，登记，不作罪证；索引里一旦存着一枚与 HEAD 不同的
    暂存内容，它就是这一形的权威底本，盘上字节又不等于它 ⇒ 闸门吞下了「暂存之后又被写了一手」，
    那是真手，必须红（判据③①②）。
    """
    head, index, work = mod.head_leg(rel, root), mod.index_leg(rel, root), mod.worktree_leg(rel, root)
    legs = "HEAD=%s index=%s worktree=%s" % (mod._leg_text(head), mod._leg_text(index),
                                             work[:10] if work else "缺")
    if index == mod.UNMERGED:
        return True, "索引未合并＝闸门吞掉的一手 | " + legs
    if rel in staged:
        if index is None:
            if work is not None:
                return True, "暂存里删掉了、盘上又长出字节＝索引 blob 与盘上不等 | " + legs
            return False, "%s：暂存删除与盘上一致（HEAD↔索引那一截是货）| %s" % (REGISTERED_PREFIX, legs)
        if work is None:
            return True, "暂存内容之外盘上没了＝索引 blob 与盘上不等 | " + legs
        if work != index[1]:
            return True, "暂存之后又被写了一手＝索引 blob 与盘上不等 | " + legs
        return False, "%s：暂存 blob 与盘上一字不差（HEAD↔索引那一截是货）| %s" % (REGISTERED_PREFIX, legs)
    if head is None and index is None and work is None:
        return False, "三条腿都没有这枚路径（不在本单视野）| " + legs
    if head is not None and index is None:
        return True, "索引里没了而 HEAD 与盘上都在＝暂存之外的一手 | " + legs
    if head is not None and work is not None and work == head[1]:
        return False, "字节相同 | " + legs
    return False, "%s：未进索引的那一截差异＝apply 未 commit 的货，不作罪证 | %s" % (
        REGISTERED_PREFIX, legs)


def drop_audit(rel: str, root: Path, state: dict) -> tuple[bool, str]:
    """被闸门放掉的候选的复证判据。静止态一字不松（照旧 `content_verdict` 三条腿全等）；
    并树中态走索引对盘上——换的是坐标系，不换「放掉一条就要拿得出凭据」这条本分。"""
    if state["state"] == STATIC_STATE:
        return mod.content_verdict(rel, root)
    return merge_drop_verdict(rel, root, set(state["staged"]))


def head_shadow_control(root: Path, tmp: Path, rels: list[str]) -> dict:
    """并树中态的正控（判据②）：同一批候选拿到 `git worktree add --detach <HEAD>` 的干净检出里再读一遍。

    正控读到的 HEAD 必须与脏树同一枚 sha，被登记的每一枚在正控里必须一字不差——这就是「并树中态
    不再红」不永真的凭据：把尺换成「脏就跳过」也能骗过脏树，骗不过这里逐枚点名的两态对照。
    影子树只读，用完当场 `git worktree remove`，只删自己建的那一枚，并自证名册里再读不到它。
    """
    SHADOW_SERIAL[0] += 1
    sha = mod._git(root, "rev-parse", "HEAD").strip()
    tree = tmp / ("%s-%d-%d" % (SHADOW_WORKTREE_PREFIX, os.getpid(), SHADOW_SERIAL[0]))
    tree.parent.mkdir(parents=True, exist_ok=True)
    mod._git(root, "worktree", "add", "--detach", str(tree), sha)
    readings: dict[str, list] = {}
    try:
        assert mod._git(tree, "rev-parse", "HEAD").strip() == sha, (
            "影子端正控不是这棵树的 HEAD：%s vs %s" % (sha, tree))
        for rel in rels:
            changed, why = mod.content_verdict(rel, tree)
            readings[rel] = [changed, why]
            assert not changed, "干净 HEAD 检出里同一枚 content_verdict 读出了手：%s | %s" % (rel, why)
    finally:
        mod._git(root, "worktree", "remove", "--force", str(tree))
    listing = mod._git(root, "worktree", "list", "--porcelain").replace("\\", "/").lower()
    assert str(tree).replace("\\", "/").lower() not in listing, "工作树名册里还挂着影子树：%s" % tree
    assert not tree.exists(), "影子树用完没删干净：%s" % tree
    return {"head_sha": sha, "shadow_tree": str(tree), "removed": True,
            "rels": sorted(readings), "readings": readings}


# ------------------------------------------------------------------ 判据②：名单一枚不许少
def test_the_forbidden_and_registered_lists_lost_no_path_to_get_green() -> None:
    """「不许删路径变绿」今天由这枚钉守着，不靠纸面承诺。"""
    missing = [rel for rel in FORBIDDEN_FLOOR if rel not in set(mod.FORBIDDEN_PATHS)]
    assert missing == [], "R496 拿删禁域路径换绿，少了：%s" % missing
    assert len(mod.FORBIDDEN_PATHS) == len(FORBIDDEN_FLOOR), (
        "禁域名单枚数漂了（现 %d，R496 动手前 %d）：加一枚要在纸上单独说理由"
        % (len(mod.FORBIDDEN_PATHS), len(FORBIDDEN_FLOOR)))
    assert len(set(mod.FORBIDDEN_PATHS)) == len(mod.FORBIDDEN_PATHS), "名单里有重复条目"
    gone = [rel for rel in REGISTERED_FLOOR if rel not in set(mod.REGISTERED_FILES)]
    assert gone == [], "在册件名册被删薄，少了：%s" % gone
    assert len(mod.REGISTERED_FILES) == len(REGISTERED_FLOOR), (
        "在册件名册枚数漂了（现 %d，R496 动手前 %d）" % (len(mod.REGISTERED_FILES), len(REGISTERED_FLOOR)))


# ------------------------------------------------------------------ 判据④（甲形）：假红必须消失
def test_a_foreign_legal_edit_of_the_instrument_leaves_both_pins_silent(tmp_path: Path) -> None:
    """R471 那一形的最小复现：别人家合法改在册量具，本单交付件干净 ⇒ 两枚盘面钉必须沉默。"""
    root = mod.shadow_repo(tmp_path, SEED)
    victim = drift(root, "scripts/eval_transport_ask_v2.py", FOREIGN_CALIBER_NOTE)
    entries = mod.git_status_porcelain(root)
    assert mod.construction_fingerprint(entries) == [], (
        "本单一枚交付件都没动，施工指纹却非空：闸门关不上，09-29 那两次假红还会再来")
    # 旧形状（不套闸门）必须红——否则下面那枚「沉默」是空响。
    assert mod.dirty_forbidden_paths(entries) == ["M " + victim], (
        "不套闸门的禁域读数本该把这枚别人家的改动判红，实测 %s" % mod.dirty_forbidden_paths(entries))
    assert mod.registered_modifications(entries) == ["M " + victim], (
        "不套闸门的在册件读数本该把它判红，实测 %s" % mod.registered_modifications(entries))
    # 套上闸门：读数沉默，判决不 raise。
    assert mod.forbidden_dirt_reading(root) == ([], []), mod.forbidden_dirt_reading(root)
    assert mod.registered_dirt_reading(root) == ([], []), mod.registered_dirt_reading(root)
    mod.forbidden_overreach_verdict(root)
    mod.registered_overreach_verdict(root)
    # 历史层也不替别人喊狼：名册为空，落点里读不到这枚在册量具。
    assert mod.ticket_landing_commits(root) == []
    assert mod.signed_commit_overreach(root) == []
    real_tree_untouched()


def test_a_foreign_edit_of_app_leaves_the_live_pins_silent_and_costs_nothing(tmp_path: Path) -> None:
    """诚实的一格：别人在这棵树动了 `app/**` 而本单在此树零写入 ⇒ 本单两枚活体钉沉默。

    本单没在这棵树写过一个字，它拿盘面指控谁都是假话。`app/**` 的保护不靠这一枚常驻钉：
    挂号提交名册（历史层）盯本单自己的手，实质层盯评测集／门／override 够着的面，
    而 `app/**` 自己的那族件另有主人。这一形必须显式钉住，不然下一个人又会拿闸门当免检。
    """
    root = mod.shadow_repo(tmp_path, SEED)
    victim = drift(root, "app/agents/nodes.py")
    entries = mod.git_status_porcelain(root)
    assert mod.construction_fingerprint(entries) == []
    assert mod.dirty_forbidden_paths(entries) == ["M " + victim], "旧读数本该红，否则本反证空响"
    mod.forbidden_overreach_verdict(root)
    mod.registered_overreach_verdict(root)
    assert mod.signed_commit_overreach(root) == [], "本单没提交过这一笔，历史层也不许把它记到本单头上"
    real_tree_untouched()


# ------------------------------------------------------------------ 判据⑤（乙形）：真越界必须还红
@pytest.mark.parametrize("victim", [
    "app/agents/nodes.py",
    "app/common/model_config.py",
    "frontend/.gitignore",
    "scripts/eval_transport_ask_v2.py",
    "scripts/run_gate.py",
    "tests/test_evaluation_report.py",
    "pyproject.toml",
    "docker-compose.yml",
    "docs/testing/evaluation-30.md",
])
def test_the_pins_still_bite_when_this_ticket_is_holding_the_pen(tmp_path: Path, victim: str) -> None:
    """本单正在施工（动了一枚交付件）⇒ 九枚禁域路径逐枚点名，一枚都不许溜过去。"""
    root = mod.shadow_repo(tmp_path / "scoped", SEED)
    assert mod.deliverables_tracked_in_head(root), "交付件没进影子 HEAD：这把刀造不出施工指纹"
    drift(root, "deploy/compose.cloud-eval.yaml")          # 本单的手：施工指纹为真
    drift(root, victim)                                     # 越界的那一手
    fingerprint, breaches = mod.forbidden_dirt_reading(root)
    assert fingerprint, "动了本单的交付件却读不出施工指纹：这道闸门把本单自己的手也放过了"
    assert breaches and any(victim in hit for hit in breaches), (
        "禁域钉在真越界这一形下读空了：%s" % breaches)
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.forbidden_overreach_verdict(root)
    if victim in mod.REGISTERED_FILES:
        with pytest.raises(AssertionError, match=re.escape(victim)):
            mod.registered_overreach_verdict(root)
    else:
        mod.registered_overreach_verdict(root)              # 两枚钉各管各的面，不互相顶班
    real_tree_untouched()


def test_a_first_day_worktree_still_bites(tmp_path: Path) -> None:
    """并树之前第一天的形状：交付件全是未跟踪新钉 ⇒ 那也是本单的手，越界照样红。"""
    root = mod.shadow_repo(tmp_path, SEED)
    mod._git(root, "rm", "-q", "--cached", "tests/test_r453_cloud_eval_override.py")
    mod._git(root, "-c", "user.name=r496-knife", "-c", "user.email=r496@knife.invalid",
             "commit", "-q", "--amend", "--no-edit")
    (root / "tests" / "test_r453_first_day_nail.py").write_text(
        "def test_a_new_nail():\n    assert True\n", encoding="utf-8")
    victim = drift(root, "app/common/model_config.py")
    entries = mod.git_status_porcelain(root)
    assert mod.construction_fingerprint(entries), (
        "写域前缀下的新未跟踪钉没算施工：闸门会把本单第一天的手当成别人家的")
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.forbidden_overreach_verdict(root)
    real_tree_untouched()


# ------------------------------------------------------------------ 补旧钉盲点：提交级归因
def test_a_committed_overreach_greens_the_live_pin_and_is_named_by_the_roster(tmp_path: Path) -> None:
    """旧钉唯一看不见的形状：越界随交付一起提交。并树那一刻盘面干净，活体钉绿——名册必须红。"""
    root = mod.shadow_repo(tmp_path, SEED)
    victim = drift(root, "scripts/run_gate.py", FOREIGN_CALIBER_NOTE)
    sha = commit_all(root, "R453 并树（影子刀：越界随交付一起提交的那一笔）")
    assert mod.git_status_porcelain(root) == [], "影子树提交后盘面没干净，这把刀证不了旧钉的盲点"
    assert mod.forbidden_dirt_reading(root) == ([], []), "活体钉在这一形下还读数：那它不是绿的来源"
    mod.forbidden_overreach_verdict(root)                   # 旧形状的「绿」，正是不可信的那一枚
    mod.registered_overreach_verdict(root)
    hits = mod.signed_commit_overreach(root)
    assert hits == ["%s %s" % (sha[:8], victim)], hits
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.signed_commit_overreach_verdict(root)
    real_tree_untouched()


def test_a_foreign_signed_commit_never_enters_the_roster(tmp_path: Path) -> None:
    """名册的归因只认 subject 开头那枚号：R471 那笔动了同一枚在册量具，也不记进本单名下。"""
    root = mod.shadow_repo(tmp_path, SEED)
    drift(root, "scripts/eval_transport_ask_v2.py", FOREIGN_CALIBER_NOTE)
    commit_all(root, "并树 R471 丙案（判据口径返工，在册量具随口径跟改）")
    assert mod.ticket_landing_commits(root) == [], "别人家的挂号提交被认成本单的名册"
    assert mod.signed_commit_overreach(root) == []
    # 交付件已在 HEAD 而名册读空 ⇒ 这枚钉不许静默通过，它必须喊「尺漂了」。
    assert mod.deliverables_tracked_in_head(root)
    with pytest.raises(AssertionError, match="空响"):
        mod.signed_commit_overreach_verdict(root)
    real_tree_untouched()


# ------------------------------------------------------------------ 真树自身的读数（现取，两形都要有牙）
def dropped_must_be_identical(root: Path, candidates: list[str], hands: list[str],
                              state: dict | None = None) -> list[str]:
    """闸门只许放掉「这一形的底本与盘上一字不差」的候选，放掉的每一枚当场复证，回登记账。

    R623 那道保险原样留着：不复证就分不清「字节相同所以放」与「尺漂了所以看不见」。
    R706 换的是坐标系。静止态一字不松——照旧拿 HEAD blob 对盘上字节，今天该红的还得红；
    并树中态里 HEAD 之上有在飞的货（`git apply` 未 commit），拿 HEAD 当底本就是把别人那一枚单
    的合法施工判成本单吞掉的罪证（10-06 主树并 R700 时 state① 唯一那枚红即此）。这一形改判
    索引 blob 对盘上字节，HEAD↔索引／HEAD↔盘上那一截逐枚点名登记、不作罪证，由调用方拿影子端
    正控再读一遍。🔴 不是「脏就跳过」：跳过＝摘牙；登记的每一枚都得留下名字。
    """
    state = read_tree_state(root) if state is None else state
    kept = {mod.hit_path(hit) for hit in hands}
    dropped = [hit for hit in candidates if mod.hit_path(hit) not in kept]
    registered: list[str] = []
    for hit in dropped:
        rel = mod.hit_path(hit)
        changed, why = drop_audit(rel, root, state)
        assert not changed, "闸门放掉了真改动：%s（读数 %s｜态=%s｜%s）" % (rel, hit, state["state"], why)
        assert why.startswith("字节相同") or why.startswith(REGISTERED_PREFIX) or \
            why.startswith("三条腿都没有"), \
            "放掉一条却拿不出『底本一字不差』的凭据：%s | %s | 态=%s" % (hit, why, state["state"])
        if why.startswith(REGISTERED_PREFIX):
            registered.append("%s | %s" % (rel, why))
    return registered


def real_tree_reading_verdict(root: Path, tmp: Path,
                              entries: list[str] | None = None) -> None:
    """真树那枚钉的判决本体（R623 改形成：两形都按**内容**判，盘面行只当候选）。

    病两层，一层都不许留：
      · 09-29 本单自己并树现场 `ec5dfef`（事故 #96）：原来无条件 `assert fingerprint`，把「本单此刻
        正在施工」当永真判据 ⇒ 总控一提交、盘面一干净就当场翻红并永久红。今天仍旧先判态再取证。
      · 10-03 R623：形甲里那三句拿 `git status` 存在性当罪证的裸读数（`raw_forbidden == []` 那一族）
        在同一形下照样咬假红——并树窗口里 porcelain 能把内容一字未动的受跟踪条目报成 ` M`，事后
        现读三条腿全等（总控 17 枚）。今天：候选一律过内容尺，被放掉的每一枚都要能复证字节相同。
    `entries` 只给反证注入「git 若说谎时会打印的那几行」用；真跑一律现取，不采信自述。

    R706 判据①②：先 `read_tree_state(root)` 分态，再取证。并树中态里被登记的每一枚当场拿
    `git worktree add --detach <HEAD>` 的干净影子树复证一次，两态数字进 `READINGS_LOG` 供凭据纸取数。
    R706 判据④：无 .git 的检出（`git archive` 解出来的树）具名 skip，不许在收集阶段 ERROR。
    """
    mod.require_git_checkout(root)
    entries = mod.git_status_porcelain(root) if entries is None else list(entries)
    state = read_tree_state(root)
    cand_fingerprint = mod.construction_fingerprint(entries)      # 候选层：盘面把本单点名的手
    raw_forbidden = mod.dirty_forbidden_paths(entries)            # 候选层：盘面把禁域点名的手
    raw_registered = mod.registered_modifications(entries)        # 候选层：盘面将在册件点名的手
    gated, breaches = mod.forbidden_dirt_reading(root, entries)   # 内容层：禁域罪证
    reg_gated, reg_breaches = mod.registered_dirt_reading(root, entries)
    roster = mod.ticket_landing_commits(root)
    assert len(roster) >= 1, "真树读不到本单号的挂号提交"
    assert mod.signed_commit_overreach(root) == [], mod.signed_commit_overreach(root)
    # 永真·实质层：评测集／回归门／override 三面与盘面无关，任何树同一读数。
    assert mod.evaluation_set_breaches(mod.read(mod.EVAL_GUARD_FILE),
                                       mod.jsonl_rows(mod.EVAL_100_REL),
                                       mod.jsonl_rows(mod.EVAL_30_REL)) == []
    assert mod.regression_gate_breaches(mod.read(mod.RUN_GATE_FILE),
                                        mod.read(mod.PYPROJECT_FILE)) == []
    assert mod.foreign_surface_reaches(mod.read(mod.OVERRIDE), mod.override_document()) == []
    # 永真·闸门形状：两枚活体钉读的是同一把内容尺，不许各写一把。
    hands = mod.construction_hands(root, entries)
    assert gated == hands, "禁域那枚活体钉换了尺：%s vs %s" % (gated, hands)
    assert reg_gated == hands, "在册那枚活体钉换了尺：%s vs %s" % (reg_gated, hands)
    assert {mod.hit_path(hit) for hit in hands} <= \
        {mod.hit_path(hit) for hit in cand_fingerprint} | set(mod.DELIVERED_FILES), \
        "内容级指纹点到了本单名册之外的路径：闸门凭空指控"
    registered: list[str] = []
    registered += dropped_must_be_identical(root, cand_fingerprint, hands, state)
    registered += dropped_must_be_identical(root, raw_forbidden, breaches, state)
    registered += dropped_must_be_identical(root, raw_registered, reg_breaches, state)
    # 判据②：并树中态必须当场再跑一次「同一枚 content_verdict 在干净影子树里的读数」作对照。
    shadow_control = {"skipped_reason": "%s：本钉拿的就是 HEAD 那一截底本，无需影子端正控" % state["state"]}
    if state["state"] == MERGING_STATE:
        rels = sorted({row.split(" | ", 1)[0] for row in registered}) or list(mod.DELIVERED_FILES)
        shadow_control = head_shadow_control(root, tmp, rels)
    READINGS_LOG.append({
        "root": str(root),
        "state": state["state"],
        "staged": len(state["staged"]),
        "unstaged": len(state["unstaged"]),
        "hands": len(hands),
        "breaches": len(breaches),
        "reg_breaches": len(reg_breaches),
        "dropped_candidates": len({mod.hit_path(hit) for hit in
                                   cand_fingerprint + raw_forbidden + raw_registered} -
                                  {mod.hit_path(hit) for hit in hands + breaches + reg_breaches}),
        "registered": registered,
        "control": shadow_control,
    })
    if hands:
        # 形甲·本单此刻有手（内容尺量出来的手）⇒ 归因只认本单自己的名字，且名下零越界。
        joined = ",".join(hands)
        named = [rel for rel in mod.DELIVERED_FILES if rel in joined]
        prefix_nails = [hit for hit in hands if hit.startswith("?? tests/test_r453_")]
        assert named or prefix_nails, (
            "形甲：指纹非空却没一枚落在本单名下（既不是在册交付件也不是写域新钉）："
            "归因把别人家的手记给了本单：%s" % hands)
        assert breaches == [], (
            "形甲：本单在这棵树施工，内容尺却读出禁域越界——本单名下真越界：%s（态=%s）"
            % (breaches, state["state"]))
        assert reg_breaches == [], (
            "形甲：本单在这棵树施工，内容尺却读出在册件动过字节：%s（态=%s）"
            % (reg_breaches, state["state"]))
    else:
        # 形乙·此刻无人施工（盘面说有手的，全被三条腿对账放掉）⇒ 空读必须是合法的空。
        assert breaches == [] and reg_breaches == [], (
            "形乙：本单在这棵树零写入，两枚活体钉却还在指控：%s / %s" % (breaches, reg_breaches))
        assert mod.deliverables_tracked_in_head(root), (
            "施工指纹读空而交付件又不在 HEAD：这枚钉答不出「本单在不在这棵树施工」——"
            "形乙只允许在「本单已并树」这一态成立")
        missing = [rel for rel in mod.DELIVERED_FILES if not (root / rel).is_file()]
        assert missing == [], "形乙：指纹读空且盘上缺交付件：%s" % missing
        control = mod.shadow_repo(tmp / "live-hand", SEED)
        drift(control, "deploy/compose.cloud-eval.yaml")
        hand = mod.construction_hands(control)
        assert any("deploy/compose.cloud-eval.yaml" in hit for hit in hand), (
            "真树指纹读空却自称「本单已并树」，可同一把尺在影子根里对着一只真手也读空："
            "这枚钉是空响，施工态与并树态它根本分不开")
        assert mod.deliverables_tracked_in_head(control), (
            "影子端正控里交付件不在 HEAD：那把尺读到的指纹证明不了形乙的空读是合法的空")


def test_the_real_tree_reads_its_own_construction_fingerprint(tmp_path: Path) -> None:
    """真树自读（R623 形＋R706 态分支）：判决本体抽出成 `real_tree_reading_verdict`，与本单的刀共用一把尺。

    读数改形三条永真 + 两形各一刀，与 09-29 那版同形，只是把「盘面存在性当罪证」那三句换成了
    「三条腿 blob 对账」：只 touch mtime 不再能让这两枚钉开口，真写一个字节仍旧当场点名（判据②③
    的实测在 `tests/test_r623_content_caliber_disk_pins.py`）。
    R706 再加一层：先分这棵树在静止态还是并树中态。并树窗口里 `git apply` 未 commit 的那一截
    差异是在飞的货，逐枚登记并去干净影子树复证，不再当成「闸门吞了真改动」——主树并每一枚单
    都要付一次「先红 vs 我造成」的归因税，今晚还要并三笔，这一格到此为止。
    """
    real_tree_reading_verdict(mod.REPO, tmp_path)
