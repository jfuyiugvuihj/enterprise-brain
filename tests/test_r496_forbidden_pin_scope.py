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
"""
from __future__ import annotations

import importlib.util
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
    assert mod.digest_of(mod.tracked_manifest(mod.REPO)) == mod.RUN_START_TREE_SHA, (
        "刀说是在影子根里造漂移，真树却被碰脏了——这正是 09-28 越界那一笔换成的这个形")


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
def test_the_real_tree_reads_its_own_construction_fingerprint(tmp_path: Path) -> None:
    """真树读数改形：先判态再取证，施工态与已并树态都不许空响（事故 #96 的返工）。

    病（09-29 本单自己并树现场 `ec5dfef`，凭据＝总控干净树现跑 `1 failed / 15 passed`，
    原文 `AssertionError: R496 正在改这枚件，施工指纹却读空`，件内 :238）：这一枚原来无条件
    `assert fingerprint`，把「本单此刻正在施工」当永真判据。施工期被治件是 `M` ⇒ 绿；总控一提交，
    交付件进 HEAD、盘面干净 ⇒ 指纹合法读空，这枚钉当场翻红并**永久红**——它指控的正是「总控把本单
    提交了」这一件合法的事，与本单要治的那两枚冒名判红是同一种病（同族 #77／R491 探针）。
    返工时又量出第二格：原那两枚**无闸门裸读数**断言（禁域零脏／在册零改）挂在真树上同样会咬假红——
    `docs/testing` 本身就在禁域里，而总控每一次并树都要往那儿写凭据；`frontend/**` 更不必说。
    盘面脏是别人的手，不是本单的罪证，这正是 R496 立单的论题，本枚钉自己不能违背它。

    今天改形（三条永真 + 两形各一刀）：
      永真·实质层：评测集／回归门／override 三面与盘面无关，任何树同一读数；历史层名册非空且零越界。
      永真·闸门形状：两枚活体钉在这棵树上读的指纹必须等于 `construction_fingerprint`，不许各读一把。
      形甲·本单此刻有手 ⇒ 归因只认本单自己的名字（在册交付件或写域前缀下的新未跟踪钉），
            且裸读数必须与闸门读数一致，禁域／在册裸读数一枚都不许落在本单名下。
      形乙·此刻无人施工 ⇒ 空读必须是「合法的空」：交付件已在 HEAD、盘上齐件，并且同一把尺在影子根里
            对着一只真手必须当场读得出指纹——读不出就是尺漂了，不许拿「已并树」当遮羞布。
    原「被治件必在指纹里」那一句不是被删，是**换了层**：它讲的是历史事实，由
    `test_counter_evidence_the_landing_roster_is_two_way_and_not_vacuous` 那枚
    「名册落点并集 ⊇ DELIVERED_FILES」的常驻钉守着，与盘面脏态无关、任何树同一读数。
    """
    entries = mod.git_status_porcelain(mod.REPO)
    fingerprint = mod.construction_fingerprint(entries)
    raw_forbidden = mod.dirty_forbidden_paths(entries)
    raw_registered = mod.registered_modifications(entries)
    gated, breaches = mod.forbidden_dirt_reading(mod.REPO)
    reg_gated, reg_breaches = mod.registered_dirt_reading(mod.REPO)
    roster = mod.ticket_landing_commits()
    assert len(roster) >= 1, "真树读不到本单号的挂号提交"
    assert mod.signed_commit_overreach() == [], mod.signed_commit_overreach()
    assert mod.evaluation_set_breaches(mod.read(mod.EVAL_GUARD_FILE),
                                       mod.jsonl_rows(mod.EVAL_100_REL),
                                       mod.jsonl_rows(mod.EVAL_30_REL)) == []
    assert mod.regression_gate_breaches(mod.read(mod.RUN_GATE_FILE), mod.read(mod.PYPROJECT_FILE)) == []
    assert mod.foreign_surface_reaches(mod.read(mod.OVERRIDE), mod.override_document()) == []
    assert gated == fingerprint, "禁域那枚活体钉换了尺：%s vs %s" % (gated, fingerprint)
    assert reg_gated == fingerprint, "在册那枚活体钉换了尺：%s vs %s" % (reg_gated, fingerprint)
    if fingerprint:
        joined = ",".join(fingerprint)
        named = [rel for rel in mod.DELIVERED_FILES if rel in joined]
        prefix_nails = [hit for hit in fingerprint if hit.startswith("?? tests/test_r453_")]
        assert named or prefix_nails, (
            "形甲：指纹非空却没一枚落在本单名下（既不是在册交付件也不是写域新钉）："
            "归因把别人家的手记给了本单：%s" % fingerprint)
        assert breaches == raw_forbidden, (
            "形甲：本单在施工，闸门却把禁域裸读数改掉了——闸门只该管归因，不该藏脏：%s vs %s"
            % (breaches, raw_forbidden))
        assert reg_breaches == raw_registered, (
            "形甲：在册裸读数被闸门改掉：%s vs %s" % (reg_breaches, raw_registered))
        assert raw_forbidden == [], (
            "形甲：本单在这棵树施工，禁域却读出脏态——本单名下越界：%s" % raw_forbidden)
        assert raw_registered == [], (
            "形甲：本单在这棵树施工，在册件却读出改动——本单名下越界：%s" % raw_registered)
    else:
        assert breaches == [] and reg_breaches == [], (
            "形乙：本单在这棵树零写入，两枚活体钉却还在指控：%s / %s" % (breaches, reg_breaches))
        assert mod.deliverables_tracked_in_head(mod.REPO), (
            "施工指纹读空而交付件又不在 HEAD：这枚钉答不出「本单在不在这棵树施工」——"
            "形乙只允许在「本单已并树」这一态成立")
        missing = [rel for rel in mod.DELIVERED_FILES if not (mod.REPO / rel).is_file()]
        assert missing == [], "形乙：指纹读空且盘上缺交付件：%s" % missing
        control = mod.shadow_repo(tmp_path / "live-hand", SEED)
        drift(control, "deploy/compose.cloud-eval.yaml")
        hand = mod.construction_fingerprint(mod.git_status_porcelain(control))
        assert any("deploy/compose.cloud-eval.yaml" in hit for hit in hand), (
            "真树指纹读空却自称「本单已并树」，可同一把尺在影子根里对着一只真手也读空："
            "这枚钉是空响，施工态与并树态它根本分不开")
        assert mod.deliverables_tracked_in_head(control), (
            "影子端正控里交付件不在 HEAD：那把尺读到的指纹证明不了形乙的空读是合法的空")
    real_tree_untouched()
