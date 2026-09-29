# -*- coding: utf-8 -*-
"""R498 · 判据①：库内被 ignore 且盘上真在的产物走第四档，只报不判红；真假账照样红。

病根：R491 把「盘上有 · 库里没」一律判红，而本仓每一枚派工词都必须写明「用主树解释器
`.venv/Scripts/python.exe`」（工作树里没有 .venv＝事故 #93 的正解），于是 `.venv/**`、
`__pycache__/**`、`static/charts/**` 这些正当引用天天被这把尺喊成 #82 那一族假账。

治得两头都不软：
  ① 「被 ignore 且盘上真在」→ IGNORED_IN_REPO，附 `git check-ignore -v` 的出处，只报不判红；
  ② 「盘上无 · 库里无」仍 MISSING 红，「盘上有 · 库里没 · 也没被 ignore」仍 UNTRACKED_BUT_ON_DISK 红；
  ③ 拿不到 check-ignore 的答案（不是一棵 git 树／git 读错）就**不降噪**，照旧红——
     降噪必须有凭据，不许为了安静把整档变宽；
  ④ 在册件永不送进 check-ignore（凭据只在「未跟踪且盘上真在」这一支才需要），
     盘上根本没有的件也不送（那样的引用本来就是一条假话）。

全程只读盘：影子树落在 pytest 的 tmp_path 里（只 `git init` 建空仓，一次 commit 都不做），
真仓工作区与本树工作区都不写第二个字节。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"

#: 影子树的 .gitignore 三行（行号就是附注里的坐标，改一行就得跟着改判据）。
SHADOW_IGNORE = "__pycache__/" + chr(10) + ".venv/" + chr(10) + "static/*" + chr(10)

#: check() 的抽取词表只吃 SCOPE_DIRS 打头的 repo-relative 写法（见 SCOPE_DIRS），
#: 所以「盘上被 ignore 的产物」要走进 A 档，得写成 `tests/__pycache__/…`／`static/…` 这一形；
#: 裸 `.venv/…` 相对写法它今天看不见——下面有一枚钉把这条边界钉在纸面上。
IGNORED_PRODUCT = "tests/__pycache__/deadbeef.cpython-311.pyc"
VENV_PRODUCT = ".venv/Scripts/python.exe"
STATIC_PRODUCT = "static/charts/seed.png"
HANGING = "scripts/hanging.py"
NOWHERE = "scripts/nowhere.py"
IN_LEDGER = "scripts/in_ledger_only.py"
NOTE = "docs/handoff/note.md"

TRACKED_LEDGER = {IN_LEDGER, NOTE}


def git(root, *args, stdin=None):
    run = subprocess.run(("git", "-C", str(root)) + tuple(args), capture_output=True, input=stdin)
    assert run.returncode == 0, "影子树准备失败：git {0} rc={1} {2}".format(
        " ".join(args), run.returncode, run.stderr.decode("utf-8", "replace").strip())
    return run.stdout


def touch(root, rel, payload=b"x" + bytes((10,))):
    path = Path(root) / Path(*rel.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture(scope="module")
def r498():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r498_ignored", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def shadow(r498, tmp_path):
    """真 git 仓（无 commit）+ 三条 ignore 规则 + 四枚盘上件；在册表与 HEAD 用手撒的影子账。"""
    git(tmp_path, "init", "-q")
    touch(tmp_path, ".gitignore", SHADOW_IGNORE.encode("utf-8"))
    for rel in (IGNORED_PRODUCT, VENV_PRODUCT, STATIC_PRODUCT, HANGING, IN_LEDGER):
        touch(tmp_path, rel)
    touch(tmp_path, NOTE)
    ruler = r498.Ruler(tmp_path)
    ruler._tracked = set(TRACKED_LEDGER)
    ruler._head = "0" * 40          # 空仓没有 commit，落地门牌号在这里必须是撒出来的影子账
    return ruler


def judge(ruler, rel, kind="repo"):
    return ruler.name_status({"kind": kind, "rel": rel})


def rows_named(report):
    return {row["raw"]: row for row in report["names"]}


# ---------------------------------------------------------------------------
# ① 第四档：只报不判红，且附注要说出处
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel,rule", [
    (IGNORED_PRODUCT, ".gitignore:1:__pycache__/"),
    (VENV_PRODUCT, ".gitignore:2:.venv/"),
    (STATIC_PRODUCT, ".gitignore:3:static/*"),
])
def test_an_ignored_product_on_disk_reads_the_fourth_tier_with_its_rule(r498, shadow, rel, rule):
    status, note = judge(shadow, rel)
    assert status == r498.IGNORED, rel + " 读成了 " + str(status)
    assert status not in r498.RED_STATUSES and status in r498.WARN_STATUSES
    assert rule in note, "附注要报出 git check-ignore 给的出处，got " + note


def test_the_cli_stays_green_when_a_dispatch_only_names_products_that_are_there(r498, shadow):
    report = shadow.check("编译产物在 {0}，图表在 {1}，解释器用绝对路径 {2}，另读在册件 {3}。".format(
        IGNORED_PRODUCT, STATIC_PRODUCT, (shadow.repo / VENV_PRODUCT).as_posix(), IN_LEDGER))
    statuses = sorted(row["status"] for row in report["names"])
    assert statuses.count(r498.IGNORED) == 3, statuses
    assert r498.OK in statuses, "在册件在影子树里盘上真在，该读 OK：" + repr(report["names"])
    assert report["red"] == 0 and report["exit_code"] == 0, "正当引用不该把派工词判死"


def test_the_ignore_tier_never_shares_a_word_with_the_fake_account_tier(r498):
    assert r498.IGNORED != r498.UNTRACKED
    assert r498.UNTRACKED in r498.RED_STATUSES, "第四档不许顺手把 #82 那一族降级"
    assert r498.MISSING in r498.RED_STATUSES


def test_a_repeated_reading_of_the_same_shadow_tree_is_byte_identical(r498, shadow):
    text = "产物 {0} 与在册件 {1}。".format(IGNORED_PRODUCT, IN_LEDGER)
    assert r498.render(shadow.check(text, label="t")) == r498.render(shadow.check(text, label="t"))


# ---------------------------------------------------------------------------
# ② 真假账两档一格没宽
# ---------------------------------------------------------------------------

def test_an_untracked_file_that_no_rule_ignores_still_reads_red(r498, shadow):
    status, note = judge(shadow, HANGING)
    assert status == r498.UNTRACKED, "盘上有库里没且没被 ignore，仍必须是 #82 那一族的红：" + status
    assert shadow.check("新钉 {0} 一枚。".format(HANGING))["exit_code"] == 1


def test_a_file_that_is_nowhere_still_reads_missing_red(r498, shadow):
    status, _ = judge(shadow, NOWHERE)
    assert status == r498.MISSING
    report = shadow.check("引用 {0} 与 {1} 两枚。".format(NOWHERE, STATIC_PRODUCT))
    assert report["red"] == 1, "红牙只许咬在那枚不存在的件上"
    assert rows_named(report)[NOWHERE]["red"] is True
    assert rows_named(report)[STATIC_PRODUCT]["red"] is False


# ---------------------------------------------------------------------------
# ③ 拿不到凭据就不降噪
# ---------------------------------------------------------------------------

def test_a_tree_that_is_not_a_git_repo_keeps_the_fake_account_red(r498, tmp_path):
    """不是 git 树 ⇒ check-ignore 读不到 ⇒ 宁可不降噪，也照旧红。"""
    touch(tmp_path, HANGING)
    ruler = r498.Ruler(tmp_path)
    ruler._tracked = set()
    status, note = judge(ruler, HANGING)
    assert status == r498.UNTRACKED, "没有 git 凭据就不许凭空造出一档降噪：" + status + " / " + note
    assert ruler.ignore_evidence(HANGING) is None


# ---------------------------------------------------------------------------
# ④ 谁会被送进 check-ignore：只有「未跟踪 + 盘上真在」
# ---------------------------------------------------------------------------

def test_only_untracked_files_on_disk_are_asked_about_ignore_status(r498, shadow, monkeypatch):
    asked = []
    real = shadow.ignore_evidence
    monkeypatch.setattr(shadow, "ignore_evidence",
                        lambda rel: (asked.append(rel), real(rel))[1])
    shadow.check("在册 {0}、悬着 {1}、不存在 {2}、产物 {3}、图表 {4}。".format(
        IN_LEDGER, HANGING, NOWHERE, IGNORED_PRODUCT, VENV_PRODUCT))
    assert sorted(asked) == sorted([HANGING, IGNORED_PRODUCT]), (
        "在册件与盘上根本没有的件都不该送进 check-ignore，实送 " + repr(asked))


def test_the_vocabulary_boundary_is_said_out_loud(r498, shadow):
    """尺子的抽取词表只认 SCOPE_DIRS 打头：裸 `.venv/…` 它今天看不见，写全路径才看得见。

    这不是把边界藏起来——派工词写的是主树解释器的**绝对路径**，那一形走 inside_repo 归一，
    正是第四档要吃的那一枚；相对裸写这一形留在词表外，本枚钉把「沉默」与「看得见」同时钉住。
    """
    bare = shadow.check("解释器用 {0} 跑测试。".format(VENV_PRODUCT))
    assert [row for row in bare["names"] if row["raw"].startswith(".venv/")] == [], (
        "词表若已经吃下裸 .venv/ 写法，本枚钉要跟着改口径：" + repr(bare["names"]))
    full = shadow.check("解释器用 {0} 跑测试。".format((shadow.repo / VENV_PRODUCT).as_posix()))
    row = [one for one in full["names"] if one["status"] == r498.IGNORED]
    assert len(row) == 1 and ".gitignore:2:.venv/" in row[0]["note"], repr(full["names"])
    assert full["red"] == 0


# ---------------------------------------------------------------------------
# 活账（与仓库位置无关的取法）：真仓 .gitignore 确实收着这三族
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel,rule", [
    ("__pycache__/whatever.cpython-311.pyc", "__pycache__/"),
    ("tests/__pycache__/whatever.cpython-311.pyc", "__pycache__/"),
    (".venv/Scripts/python.exe", ".venv/"),
    ("static/charts/whatever.png", "static/"),
])
def test_the_real_repo_actually_ignores_these_product_families(r498, rel, rule):
    evidence = r498.Ruler(REPO_ROOT).ignore_evidence(rel)
    assert evidence and rule in evidence, rel + " 在真仓里没被 ignore？出处读回 " + repr(evidence)


def test_the_real_repo_ledger_is_not_the_place_where_products_live(r498):
    """在册表里一枚 .pyc 都不该有；被 ignore 的产物族与在册族是两批东西。"""
    tracked = r498.Ruler(REPO_ROOT).tracked()
    assert [one for one in tracked if one.endswith(".pyc") or one.startswith(".venv/")] == []
    assert not any(tracked_match.startswith(".venv/") for tracked_match in tracked)


# ---------------------------------------------------------------------------
# 静态闸：本单两枚新钉也不许烤进树名（R491 那枚闸的形状，覆盖面加宽一格）
# ---------------------------------------------------------------------------

def test_no_r498_pin_bakes_a_tree_name_into_its_probe():
    banned = ("REPO_ROOT" + ".parent", "".join(map(chr, (0x4F01, 0x4E1A, 0x667A, 0x8111))))
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("test_r49[18]_*.py")):
        body = path.read_text(encoding="utf-8")
        for token in banned:
            if token in body:
                offenders.append(path.name + " 含 " + token)
    assert offenders == [], "钉里烤进了树名或仓库上层拼接，合并树上必红：" + " | ".join(offenders)
