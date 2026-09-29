# -*- coding: utf-8 -*-
"""R491 · 判据①：四笔真实历史假账必须读出血，真名必须读干净。

病根（09-29 事故 #82/#85/#90）：派工词把不存在的件名、不存在的库外路径当事实写出去，
下一班照着跑就白烧一轮。本件钉 `scripts/dispatch_preflight.py` 那把尺子：
  ① `tests/test_r387_teeth.py`、`tests/test_r400_derived.py`（#90 的账面缩写）⇒ 各一枚 MISSING；
  ② `be-r484\\.venv\\Scripts\\python.exe`（#91 的自造 venv）、`%TEMP%\\evalrun\\r428-driver.md`（#85）
     ⇒ 各一枚 NOT_IN_REPO，只报不判死；
  ③ 同一条里 `app/api/v1/chat.py:999999` ⇒ OUT_OF_RANGE，而 `:1005` ⇒ IN_RANGE；
  ④ 反向：喂真名件 ⇒ 零 MISSING（尺子乱喊和尺子空转一样不合格）；
  ⑤ 四档件名读数不许混：MISSING / UNTRACKED_BUT_ON_DISK / TRACKED_BUT_OFF_DISK / OK 各判各的
     （#82 那族就是「盘上有库里没」和「两样都没」被写成了一句话）。

全程只读盘：临时件一律落在 pytest 的 tmp_path 上，本树一个字节都不写。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "dispatch_preflight.py"

FAKE_R387 = "tests/test_r387_teeth.py"
FAKE_R400 = "tests/test_r400_derived.py"
REAL_R387 = "tests/test_r387_label_ruler_teeth.py"
REAL_R400 = "tests/test_r400_derived_ledger_shift_and_silence_pins.py"
GHOST_VENV = "be-r484\\.venv\\Scripts\\python.exe"
GHOST_TEMP = "%TEMP%\\evalrun\\r428-driver.md"
CHAT = "app/api/v1/chat.py"


@pytest.fixture(scope="module")
def r491():
    spec = importlib.util.spec_from_file_location("dispatch_preflight_r491", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ruler(r491):
    return r491.Ruler(REPO_ROOT)


def rows_named(report):
    return {row["raw"]: row for row in report["names"]}


def rows_linewise(report):
    return {row["raw"]: row for row in report["lines"]}


# ---------------------------------------------------------------------------
# ① #90 那两枚账面缩写
# ---------------------------------------------------------------------------

def test_the_r387_shorthand_name_reads_missing(r491, ruler):
    report = ruler.check("新钉 {0} 一枚。".format(FAKE_R387))
    row = rows_named(report)[FAKE_R387]
    assert row["status"] == r491.MISSING, "不存在的件名没读成 MISSING，这把尺子就是空转"
    assert report["red"] == 1 and report["exit_code"] == 1


def test_the_r400_shorthand_name_reads_missing(r491, ruler):
    report = ruler.check("再钉 {0} 与 {1} 两枚。".format(FAKE_R400, FAKE_R387))
    statuses = {name: row["status"] for name, row in rows_named(report).items()}
    assert statuses[FAKE_R400] == r491.MISSING
    assert statuses[FAKE_R387] == r491.MISSING
    assert report["red"] == 2


# ---------------------------------------------------------------------------
# ② 库外路径：只报不判死（#91 自造 venv、#85 %TEMP% 驱动件）
# ---------------------------------------------------------------------------

def test_the_invented_venv_path_is_reported_as_outside_the_repo(r491, ruler):
    report = ruler.check("解释器用 {0}。".format(GHOST_VENV))
    row = rows_named(report)[GHOST_VENV]
    assert row["status"] == r491.NOT_IN_REPO
    assert "ABSENT" in row["note"], "五棵工作树里这枚 venv 根本不在，得把 ABSENT 说出口"
    assert report["red"] == 0 and report["exit_code"] == 0, "库外路径按判据只报不判死"


def test_the_temp_dispatch_file_is_reported_as_outside_the_repo(r491, ruler):
    report = ruler.check("驱动件在 {0}，先读它。".format(GHOST_TEMP))
    row = rows_named(report)[GHOST_TEMP]
    assert row["status"] == r491.NOT_IN_REPO
    assert "ABSENT" in row["note"]


# ---------------------------------------------------------------------------
# 环境探针：🔴 只许用与 REPO_ROOT 无关的形状
# 「拿兄弟树名拼一枚盘上真在的件」＝派工树绿、合并树必红（本单第一次交回就死在这一格，
# 总控退回令 14:2x）。下面这枚探针取的是系统 Python 的 base_prefix —— 工作树的 venv 在仓里，
# base_prefix 永远在仓外，主树与任意一棵 be-rNNN 皆同。
# ---------------------------------------------------------------------------

def interpreter_outside_any_tree():
    """盘上真在、且对任何一棵树都在库外的一枚件。找不到就红着说话，不许 skip。"""
    base = Path(sys.base_prefix)
    for candidate in (base / "python.exe", base / "python", base / "bin" / "python3",
                      base / "bin" / "python", base / "Scripts" / "python.exe"):
        if candidate.is_file():
            return candidate
    pytest.fail("base_prefix 里没有解释器：" + str(base) + " —— 环境事实变了，本枚钉要换料（不许 skip）")


def test_a_live_path_outside_the_repo_is_reported_as_outside_but_present(r491, ruler):
    """盘上真在的库外件：同样落 NOT_IN_REPO，但附注必须是 EXISTS，且只此一枚。"""
    outside = interpreter_outside_any_tree()
    root = os.path.normcase(str(REPO_ROOT)) + os.sep
    assert not os.path.normcase(str(outside)).startswith(root), (
        "探针自己落进了本树，这格就不是「库外」的形状了：" + str(outside))
    report = ruler.check("解释器用 {0}".format(outside))
    rows = [row for row in report["names"] if row["status"] == r491.NOT_IN_REPO]
    assert len(rows) == 1, "盘上真在的库外件不该被吞掉，也不该多出别的一档：" + repr(report["names"])
    assert "EXISTS" in rows[0]["note"]


# ---------------------------------------------------------------------------
# ③④ 行号两档与反向零 MISSING
# ---------------------------------------------------------------------------

def test_the_dead_line_range_reads_out_of_range_while_the_live_one_reads_in(r491, ruler):
    report = ruler.check("锚点 {0}:999999 与 {0}:1005，逐枚核。".format(CHAT))
    lines = rows_linewise(report)
    assert lines[CHAT + ":999999"]["status"] == r491.OUT_OF_RANGE
    assert lines[CHAT + ":1005"]["status"] == r491.IN_RANGE
    assert report["red"] == 1


def test_the_real_names_read_clean_with_zero_missing(r491, ruler):
    text = "真名另记 {0}、{1}，锚点在 {2}。".format(REAL_R387, REAL_R400, CHAT)
    report = ruler.check(text)
    assert [row for row in report["names"] if row["status"] == r491.MISSING] == []
    assert report["red"] == 0 and report["exit_code"] == 0, "尺子乱喊和尺子空转一样不合格"


def test_a_directory_reference_is_judged_as_a_directory(r491, ruler):
    report = ruler.check("禁入 app/**、docs/handoff/**、frontend/**。")
    for ref in ("app/", "docs/handoff/", "frontend/"):
        assert rows_named(report)[ref]["status"] == r491.DIR_OK, ref + " 该按目录认，不许报缺件"
    assert report["red"] == 0


def test_repeated_reference_reports_once_with_its_own_count(r491, ruler):
    report = ruler.check("先 {0}，再 {0}，最后还 {0}。".format(FAKE_R387))
    assert len(report["names"]) == 1
    assert report["names"][0]["count"] == 3
    assert report["red"] == 1, "重复引用只算一枚红牙，但枚数要说出口"


def test_the_input_line_number_of_each_reference_is_read_live(r491, ruler):
    text = "第一行没有引用。\n第二行才写 {0}。\n第三行还是空的。".format(FAKE_R400)
    report = ruler.check(text)
    assert rows_named(report)[FAKE_R400]["line"] == 2


def test_the_render_is_byte_identical_twice_on_the_same_head(r491, ruler):
    text = "混喂 {0} 与 {1} 以及 R478 R888 {2}:12。".format(FAKE_R387, REAL_R400, CHAT)
    first = r491.render(ruler.check(text, label="t"))
    second = r491.render(ruler.check(text, label="t"))
    assert first == second, "同一棵树上出两遍账不该有抖动"
    assert "HEAD=" in first and "RESULT=" in first


# ---------------------------------------------------------------------------
# ⑤ 四档件名不许混成一档（用 tmp 影子盘 + 手撒在册表，真盘零改动）
# ---------------------------------------------------------------------------

def _shadow_ruler(r491, tmp_path):
    ruler = r491.Ruler(tmp_path)
    ruler._tracked = {"scripts/in_ledger_only.py", "docs/handoff/note.md"}
    return ruler


def test_the_four_name_tiers_stay_apart(r491, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "on_disk_only.py").write_bytes(b"x\n")
    (tmp_path / "docs" / "handoff").mkdir(parents=True)
    ruler = _shadow_ruler(r491, tmp_path)
    judge = lambda rel, kind="repo": ruler.name_status({"kind": kind, "rel": rel})
    assert judge("scripts/on_disk_only.py")[0] == r491.UNTRACKED
    assert judge("scripts/in_ledger_only.py")[0] == r491.OFFDISK
    assert judge("scripts/nowhere.py")[0] == r491.MISSING
    status, why = judge("docs/handoff/", "dir")
    assert status == r491.DIR_OK and "在册件 1 枚" in why


def test_the_untracked_tier_is_not_the_missing_tier(r491, tmp_path):
    """#82 那族病：五枚产物在盘上悬着，库里没有。这必须是一句能读出来的话，不是「不存在」。"""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hanging.py").write_bytes(b"x\n")
    status, why = _shadow_ruler(r491, tmp_path).name_status({"kind": "repo", "rel": "scripts/hanging.py"})
    assert status == r491.UNTRACKED and "库里没" in why
    assert status != r491.MISSING


# ---------------------------------------------------------------------------
# CLI 出口：退出码契约（0 全绿 / 1 咬到 / 2 环境错）—— 进程内跑 main()，不另起子进程
# ---------------------------------------------------------------------------

def test_the_cli_exits_one_when_it_bites(r491, capsys):
    rc = r491.main(["--text", "新钉 {0} 一枚。".format(FAKE_R387)])
    printed = capsys.readouterr().out
    assert rc == 1 and "RESULT=FAIL" in printed and "红 1 枚" in printed


def test_the_cli_exits_zero_on_a_clean_dispatch(r491, capsys):
    rc = r491.main(["--text", "真名 {0} 一枚。".format(REAL_R387)])
    printed = capsys.readouterr().out
    assert rc == 0 and "RESULT=CLEAN" in printed, "账面干净就该零退出，否则下一班永远看见红"


def test_the_cli_reports_a_broken_environment_as_two_not_one(r491, capsys, tmp_path):
    bogus = str(tmp_path / "no-such-tree")  # 与 REPO_ROOT 无关：任何一棵树上都不存在
    rc = r491.main(["--text", "随便一句", "--repo", bogus])
    err = capsys.readouterr().err
    assert rc == 2 and "不是账错" in err, "读不到 git 是环境错，不许冒充红牙"


def test_the_cli_refuses_an_empty_dispatch(r491, capsys):
    assert r491.main(["--text", "   "]) == 2
    assert "空输入" in capsys.readouterr().err


def test_a_placeholder_reference_goes_red_and_says_why(r491, ruler):
    """派工词里的占位符（`tests/test_r491_<自定>.py`）会截断成前缀：该红，但要把原因说出口。"""
    report = ruler.check("新钉 tests/test_r491_<自定>.py 一枚。")
    row = report["names"][0]
    assert row["status"] == r491.MISSING and "占位符" in row["note"]


def test_no_r491_pin_bakes_a_tree_name_into_its_probe():
    """落地即自毁那一族的静态闸：本单五枚钉里不许出现「拿仓库位置往上拼兄弟树」这个形状。

    仓库位置往上那一格在派工树与主树指的是两个不同目录（前者是工作树的公共父目录，后者是别处），
    拿它拼一枚盘上真在的件，就必然只在一棵树上绿 —— 总控退回令 14:2x 就是这一格。
    两枚禁字用拼接/码位写，免得本枚钉自己咬自己。
    """
    banned = ("REPO_ROOT" + ".parent", "".join(map(chr, (0x4F01, 0x4E1A, 0x667A, 0x8111))))
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("test_r491_*.py")):
        body = path.read_text(encoding="utf-8")
        for token in banned:
            if token in body:
                offenders.append(path.name + " 含 " + token)
    assert offenders == [], "钉里烤进了树名或仓库上层拼接，合并树上必红：" + " | ".join(offenders)
