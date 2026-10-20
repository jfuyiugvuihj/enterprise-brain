"""R623 · 两枚常驻活体钉改按**内容**判：假红必须消失，真越界必须还红。

被治的两枚钉（都在 `tests/test_r453_cloud_eval_override.py` 与 `tests/test_r496_forbidden_pin_scope.py` 里）：
  · `test_forbidden_domain_files_are_unmodified_in_this_worktree`
  · `test_the_real_tree_reads_its_own_construction_fingerprint`
病（总控 10-03 一手实测）：它们拿 `git status --porcelain` 的存在性当罪证。并树窗口里盘面会把受跟踪
条目报成 ` M`，而事后在同一棵树现读，那 17 枚的 HEAD blob、索引 blob、`git hash-object` 现算值三者
一字不差、`git diff` 零报。红的时候指控错了人，绿的时候（总控提交完再跑）又等于没测。

本件只干一件事：把「改对了」钉成两把方向相反的刀，都走影子副本道，真树一个字都不写。
  判据② 反证刀 A（两半）：
    · 物理半——只 touch mtime、内容一字不改 ⇒ 两枚钉必须仍绿。10-03 实测记在案：安静树上纯 mtime 脏
      根本进不了 porcelain（7 组 stat 扰动＋`index.lock`＋`GIT_OPTIONAL_LOCKS=0` 全读空），所以这一形
      在新旧两把尺上都该绿，它是**下限**，不是本单的新牙。
    · 说谎半——把「内容一字未动、盘面却报 ` M`」那几行注进读数口（并树那一刻的形状）：旧尺必须红，
      新尺（三条腿 blob 对账）必须绿。这一半才是本单的新牙。
  判据③ 反证刀 B：真往禁域文件写一个字节 ⇒ 两枚钉必须当场点名文件，一枚都不许溜过去。
  判据① 的另一半：盘面一字不报（最坏的漏报形）时，内容发现面仍要自己抓出真改动——换成内容判据
  不是把尺缩到只看 porcelain，而是两把尺并排放，谁读到不等都算手。
  判据④：本件自己守「只改怎么判、不改判什么」——三张名册逐枚复证，禁语清单照旧咬。

全部离线：只读文件与 git 读数，不 import 产品代码、不起服务、不连库、不动容器、不 commit。
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
R453_SOURCE = REPO / "tests" / "test_r453_cloud_eval_override.py"
R496_SOURCE = REPO / "tests" / "test_r496_forbidden_pin_scope.py"


def _load(name: str, source: Path):
    """按路径载被治的那两枚件：尺一份都不新造，两棵树不许各拿一把。"""
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None, "载不到被治的件：%s" % source
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("r453_under_r623", R453_SOURCE)
r496 = _load("r496_under_r623", R496_SOURCE)

#: 种子与刀全部沿用被治那两枚件里的现成那几把（同一批文件、同一个影子道）。
#: 种子先拿被治那枚件里的现成一批，再补三枚 deploy 覆盖件——12 枚禁域前缀要枚枚都有实体文件可写。
SEED = r496.SEED + (
    "deploy/docker-compose.server.yml",
    "deploy/docker-compose.tls.yml",
    "deploy/.env.server.example",
)
drift = r496.drift
commit_all = r496.commit_all

#: 说谎半的靶子：三枚禁域在册文件，跑之前逐枚复证「三条腿一字不差」，前提不成立就停刀。
LIABLE_VICTIMS = (
    "app/agents/nodes.py",
    "scripts/eval_transport_ask_v2.py",
    "docs/testing/evaluation-30.md",
)

#: 刀 B 的靶子：12 枚禁域前缀逐枚拿一枚盘上真存在的实体文件顶上（deploy/.env.server 未进版本控制，
#: 不在其列——它从来没有一条受跟踪的腿可对账，本单没改这一点）。
BITTEN_VICTIMS = (
    "app/agents/nodes.py",
    "app/common/model_config.py",
    "frontend/.gitignore",
    "docker-compose.yml",
    "deploy/docker-compose.server.yml",
    "deploy/docker-compose.tls.yml",
    "deploy/.env.server.example",
    "scripts/eval_transport_ask_v2.py",
    "scripts/run_gate.py",
    "tests/test_evaluation_report.py",
    "pyproject.toml",
    "docs/testing/evaluation-30.md",
)

DELIVERED_HAND = "deploy/compose.cloud-eval.yaml"


def seeded_worktree(tmp_path: Path, tag: str = "case") -> Path:
    """影子根里造出「本单正在此树施工」那一形，且历史层读得到本单号的挂号提交。

    `real_tree_reading_verdict` 要先过名册那一格，所以拿一枚只碰交付件的 R453 号提交把闸门底下的
    事实种进 HEAD，再往同一枚交付件写第二手**未提交**的改动抬起闸门。没有这一形，两枚钉的「绿」
    只是「不适用」，量不出任何东西。
    """
    root = mod.shadow_repo(tmp_path / ("seeded-" + tag), SEED)
    drift(root, DELIVERED_HAND)
    commit_all(root, "R453 并树（R623 刀：%s：种一棵已并树的施工树）" % tag)
    assert mod.deliverables_tracked_in_head(root), "交付件没进影子 HEAD：这把刀造不出已并树的形"
    assert mod.ticket_landing_commits(root), "影子名册读不到本单号的提交：刀会红在刀身上"
    assert mod.signed_commit_overreach(root) == [], "种树那一笔碰了禁域：刀不干净"
    drift(root, DELIVERED_HAND, b"\n# r623 holds an uncommitted hand on the deliverable\n")
    assert mod.construction_hands(root), (
        "闸门抬不起来：后面所有「红」都是空响，这把刀量不到牙")
    return root


def touch_only(root: Path, victims: tuple[str, ...]) -> None:
    """只改 mtime：字节一枚都不许动（动完逐枚复证，否则刀 A 就变成了刀 B）。"""
    before = {rel: (root / rel).read_bytes() for rel in victims}
    stamps = {rel: os.stat(root / rel) for rel in victims}
    future = time.time() + 3600
    for rel in victims:
        os.utime(root / rel, (future, future))
    for rel in victims:
        assert (root / rel).read_bytes() == before[rel], "touch 手滑改到字节了：%s" % rel
        assert os.stat(root / rel).st_mtime > stamps[rel].st_mtime, "mtime 没动：这一形空响"


# ------------------------------------------------------------------ 判据② 刀 A·物理半
def test_counter_evidence_mtime_touch_only_leaves_both_live_pins_green(tmp_path: Path) -> None:
    """只 touch mtime（内容一字不改）⇒ 两枚活体钉都开口指控就是本单的失败。"""
    victims = ("app/agents/nodes.py", "scripts/run_gate.py", "tests/test_evaluation_report.py",
               "docker-compose.yml", "pyproject.toml", "docs/testing/evaluation-30.md")
    root = seeded_worktree(tmp_path, "touch")
    dirt_before = mod.git_status_porcelain(root)
    touch_only(root, victims)
    for rel in victims:
        changed, why = mod.content_verdict(rel, root)
        assert changed is False, "内容尺把纯 mtime 脏判成了一只手：%s | %s" % (rel, why)
    assert mod.git_status_porcelain(root) == dirt_before, (
        "盘面读数因 touch 变了：%s -> %s（这一形就不再只是 mtime 了，刀要重造）"
        % (dirt_before, mod.git_status_porcelain(root)))
    mod.forbidden_overreach_verdict(root)
    mod.registered_overreach_verdict(root)
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-touch")
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据② 刀 A·说谎半（本单的新牙）
def test_counter_evidence_existence_in_porcelain_is_not_evidence(tmp_path: Path) -> None:
    """把「内容一字未动、盘面却报 ` M`」那几行注进读数口：旧尺必须红，新尺必须绿。

    10-03 在安静树上没能骗过 porcelain（见件头），所以这一形由本件**代 git 打印**它说谎时会给出的
    那几行——判据要钉的是「存在性不算罪证」，不是「git 永远不说谎」。同一份注入读给旧尺（候选层）
    必须处处点名，否则新尺的绿就是空响。
    """
    live = mod.git_status_porcelain(mod.REPO)
    for rel in LIABLE_VICTIMS:
        changed, why = mod.content_verdict(rel)
        assert changed is False, "说谎刀的前提不成立（这枚文件真与 HEAD 不同）：%s | %s" % (rel, why)
        assert not any(mod.hit_path(line) == rel for line in live), (
            "盘面本来就报着 %s 的脏：靶子不干净，换一枚再判" % rel)
    lie = live + [" M " + rel for rel in LIABLE_VICTIMS]
    # 旧尺（候选层）：每一枚都点得名，红句里带着状态——本单没把它改钝，它只是不再是罪证。
    named = {mod.hit_path(hit) for hit in mod.dirty_forbidden_paths(lie)}
    assert set(LIABLE_VICTIMS) <= named, "候选层读空了，新尺的绿就是空响：%s" % named
    assert set(LIABLE_VICTIMS) & set(mod.REGISTERED_FILES) <= {
        mod.hit_path(hit) for hit in mod.registered_modifications(lie)}, "在册候选层也空响了"
    # 新尺：三条腿一字不差 ⇒ 放掉，两枚活体钉都不许开口。
    hands, breaches = mod.forbidden_dirt_reading(mod.REPO, lie)
    assert hands == mod.construction_hands(mod.REPO, lie), "闸门自己都不自洽：%s" % hands
    assert [b for b in breaches if any(rel in b for rel in LIABLE_VICTIMS)] == [], breaches
    _reg_hands, reg_breaches = mod.registered_dirt_reading(mod.REPO, lie)
    assert [b for b in reg_breaches if any(rel in b for rel in LIABLE_VICTIMS)] == [], reg_breaches
    mod.forbidden_overreach_verdict(mod.REPO, lie)
    mod.registered_overreach_verdict(mod.REPO, lie)
    r496.real_tree_reading_verdict(mod.REPO, tmp_path / "ctl-lie", lie)
    r496.real_tree_untouched()


def test_the_merged_in_shape_reads_a_legal_empty_in_the_new_caliber(tmp_path: Path) -> None:
    """事故 #96 那一形在新尺下仍旧不许红：交付件已进 HEAD、盘面只剩 stat 脏 ⇒ 空读必须是合法的空。

    这一枚守的是「别把换内容判据说成换罪名」：并树之后总控一提交，两枚活体钉就该安静地不适用，
    而不是像 09-29 那样把「总控把本单提交了」当成越界。影子根里 mtime 全脏、字节全干净，
    旧尺（候选层）会把闸门抬起来，新尺必须仍旧读空——读不出手是它的本分，不是它的空响。
    """
    root = mod.shadow_repo(tmp_path / "merged", SEED)
    drift(root, DELIVERED_HAND)
    commit_all(root, "R453 并树（R623：形乙正控，交付件进 HEAD）")
    touched = ("app/agents/nodes.py", "scripts/run_gate.py", DELIVERED_HAND, "pyproject.toml")
    touch_only(root, touched)
    assert mod.content_verdict(DELIVERED_HAND, root)[0] is False, "已并树那一腿读不出「字节相同」"
    assert mod.construction_hands(root) == [], (
        "本单已把交付件提交、盘上只剩 mtime 脏，内容尺却还把手举着：%s" % mod.construction_hands(root))
    # 旧尺（候选层）在同一棵树上会把手抬起——新尺的「空」不是没测。
    lie = mod.git_status_porcelain(root) + [" M " + DELIVERED_HAND]
    assert mod.construction_fingerprint(lie), "候选层也读空了：这一形就没东西可放，本反证空响"
    mod.forbidden_overreach_verdict(root, lie)
    mod.registered_overreach_verdict(root, lie)
    r496.real_tree_reading_verdict(root, tmp_path / "ctl-merged", lie)
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据③ 刀 B：真写字节必须红
@pytest.mark.parametrize("victim", BITTEN_VICTIMS)
def test_counter_evidence_a_real_byte_written_into_a_forbidden_path_turns_the_pin_red(
        tmp_path: Path, victim: str) -> None:
    """禁域一枚都不许溜过去：真写一个字节，内容尺与旧尺同向，钉必须点名。"""
    root = seeded_worktree(tmp_path, re.sub(r"\W+", "-", victim))
    assert mod.content_verdict(victim, root)[0] is False, (
        "靶子在种树后就已与 HEAD 不同：这把刀量不出「写一个字节」那一形")
    drift(root, victim)
    changed, why = mod.content_verdict(victim, root)
    assert changed is True, "写了字节内容尺却说没动：%s" % why
    assert "盘上字节与 HEAD blob 不等" in why, "红句没说出是哪条腿漂了：%s" % why
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.forbidden_overreach_verdict(root)
    if victim in mod.REGISTERED_FILES:
        with pytest.raises(AssertionError, match=re.escape(victim)):
            mod.registered_overreach_verdict(root)
    else:
        # 不在册的禁域文件（frontend/.gitignore、deploy/*.yml…）由禁域那一枚守着，
        # 在册那一枚不许顶班——两枚钉各管各的面，这条与 R496 那把刀同形。
        mod.registered_overreach_verdict(root)
    r496.real_tree_untouched()


@pytest.mark.parametrize("victim", ["app/agents/nodes.py", "scripts/run_gate.py",
                                    "docs/testing/evaluation-30.md"])
def test_counter_evidence_the_real_tree_pin_bites_on_a_written_byte(tmp_path: Path,
                                                                    victim: str) -> None:
    """第二枚钉（真树自读那枚）也得在「写了一个字节」这一形下红：两枚都要有牙。"""
    root = seeded_worktree(tmp_path, re.sub(r"\W+", "-", victim))
    drift(root, victim)
    with pytest.raises(AssertionError, match=re.escape(victim)):
        r496.real_tree_reading_verdict(root, tmp_path / "ctl-b")
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 判据① 另一半：盘面漏报也要抓得住
def test_counter_evidence_the_content_face_names_what_the_disk_blindly_misses(tmp_path: Path) -> None:
    """盘面一字不报（`entries=[]`，最坏的漏报形）⇒ 内容尺仍要自己把手读出来。

    换成内容判据不是把尺缩成「只看一把新尺」：这里把候选层整个摘掉眼，看闸门（交付件 sweep）
    与发现面（`git diff HEAD -- <禁域>`、在册件 sweep）能不能各自站住。
    """
    root = seeded_worktree(tmp_path, "blind")
    victim = drift(root, "app/common/model_config.py")
    assert mod.dirty_forbidden_paths([]) == [], "候选层本该读空（眼罩摘不掉就别演），否则这一形空响"
    assert mod.registered_modifications([]) == [], "在册候选层同样该读空"
    hands, breaches = mod.forbidden_dirt_reading(root, entries=[])
    assert hands, "闸门只靠盘面行抬起：交付件 sweep 那一格是空转"
    assert any(victim in hit for hit in breaches), (
        "内容发现面没抓到盘面漏报的真改动：%s" % breaches)
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.forbidden_overreach_verdict(root, [])
    reg_hands, reg_breaches = mod.registered_dirt_reading(root, entries=[])
    assert reg_hands == hands, "两枚活体钉读了两把不同的尺：%s vs %s" % (reg_hands, hands)
    assert any("app/common/model_config.py" in hit for hit in reg_breaches), (
        "在册件 sweep 没自己抓到：%s" % reg_breaches)
    with pytest.raises(AssertionError, match=re.escape(victim)):
        mod.registered_overreach_verdict(root, [])
    r496.real_tree_untouched()


# ------------------------------------------------------------------ 三条腿这把尺自己的形状
def test_the_worktree_leg_is_hashed_through_gits_own_filter() -> None:
    """盘上那一枚字节必须经 git 自己的过滤再算 sha：拿原始字节当尺会把全仓判成脏。"""
    probes = ("app/agents/nodes.py", "scripts/run_gate.py", "docker-compose.yml",
              "docs/testing/evaluation-30.md", "pyproject.toml")
    raw_differs = []
    for rel in probes:
        head = mod.head_leg(rel)
        assert head is not None, "靶子不在 HEAD 里：%s" % rel
        work = mod.worktree_leg(rel)
        assert work == head[1], "过滤后的盘上读数与 HEAD 不等，可这枚文件盘面是干净的：%s" % rel
        assert mod.content_verdict(rel)[0] is False, rel
        raw = hashlib.sha1((mod.REPO / rel).read_bytes()).hexdigest()
        if raw != head[1]:
            raw_differs.append(rel)
    print("\nR623 三条腿读数：probes=%d 枚，原始字节 sha 与 HEAD 不等的=%d 枚 %s"
          % (len(probes), len(raw_differs), raw_differs))
    if not raw_differs:
        print("  这台机盘上字节与库里一字不差（LF 落盘）：过滤这一腿换机时再复证，等值断言照跑。")


def test_the_verdict_paths_are_wired_to_the_content_ruler() -> None:
    """接线钉：内容尺必须真挂在判决线上，挂在外面就等于没改。"""
    for fn in (mod.construction_hands, mod.forbidden_dirt_reading, mod.registered_dirt_reading):
        names = fn.__code__.co_names
        assert "content_hands" in names or "construction_hands" in names, \
            "%s 没走内容尺：判决线还挂在盘面存在性上" % fn.__name__
    assert "content_verdict" in mod.content_hands.__code__.co_names, "content_hands 是空壳"
    assert "forbidden_diff_paths" in mod.forbidden_dirt_reading.__code__.co_names, \
        "禁域只剩一条盘面发现面：漏报那一格没人补"
    assert "content_hands" in r496.real_tree_reading_verdict.__code__.co_names or \
        "construction_hands" in r496.real_tree_reading_verdict.__code__.co_names, \
        "真树那枚钉没换成内容尺"
    for name in ("test_forbidden_domain_files_are_unmodified_in_this_worktree",
                 "test_registered_in_book_files_carry_no_modification_or_deletion",
                 "forbidden_overreach_verdict", "registered_overreach_verdict",
                 "construction_fingerprint", "dirty_forbidden_paths", "registered_modifications"):
        assert callable(getattr(mod, name, None)), "被治的钉换了名字或不见了（改名逃避？）：%s" % name
    assert callable(getattr(r496, "test_the_real_tree_reads_its_own_construction_fingerprint", None))


def test_this_ticket_changed_the_caliber_not_the_scope() -> None:
    """判据④：三张名册与禁语清单逐枚复证「一枚没少」——本单只改怎么判，不改判什么。"""
    forbidden = tuple(mod.FORBIDDEN_PATHS)
    assert forbidden == r496.FORBIDDEN_FLOOR, (
        "禁域名单被重排或删薄：%s vs %s" % (forbidden, r496.FORBIDDEN_FLOOR))
    assert len(forbidden) == 12 and len(set(forbidden)) == 12, forbidden
    assert tuple(mod.REGISTERED_FILES) == r496.REGISTERED_FLOOR, "在册件名册漂了"
    assert len(mod.REGISTERED_FILES) == 12, mod.REGISTERED_FILES
    assert len(mod.DELIVERED_FILES) == 6 and len(mod.WRITE_DOMAIN_FILES) == 2 \
        and mod.WRITE_DOMAIN_PREFIXES == ("tests/test_r453_",), "本单写域漂了"
    # 候选层一枚没缩小：12 枚前缀逐枚仍点得名（含目录前缀与未跟踪不收那一条）
    lines = [" M " + rel for rel in forbidden] + ["?? app/not_tracked_yet.py"]
    named = {mod.hit_path(hit) for hit in mod.dirty_forbidden_paths(lines)}
    assert named == set(forbidden), "候选层被改窄了：%s" % sorted(set(forbidden) - named)
    assert mod.is_forbidden("docs/testing/anything.md") and mod.is_forbidden("frontend/src/main.js")
    assert not mod.is_forbidden("apple/pie.py"), "前缀尺放宽会误伤，禁语清单不许顺手改这个"
    # 禁语清单（密钥形状／公网 URL／注入形态／写域签名）原样咬得住
    assert mod.secret_shaped_literals('key: sk-abc123def456'), "密钥尺钝了"
    assert mod.external_hosts("url: https://api.openai.com/v1"), "公网 URL 尺钝了"
    assert mod.inline_values({"LOCAL_MODEL_NAME": "qwen-local"}), "注入形态尺钝了"
    assert mod.ticket_signed_strays(["?? deploy/compose.cloud-eval.yaml.draft"]) == [
        "deploy/compose.cloud-eval.yaml.draft"], "签名筛钝了"
