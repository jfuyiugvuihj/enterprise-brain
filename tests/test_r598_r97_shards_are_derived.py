"""R598⑦ · 常驻钉：`r97-shard-{1,2,3}.jsonl` 必须**等于从主件逐字节派生出来的那三片**。

【钉的三件事】
1. 三片逐字节 == 从 `tests/fixtures/business_evaluation_100.jsonl` 现派生的三片（BOM／行序／
   换行符／行尾一字节都不加工），两边 sha256 前 16 逐枚打印。
2. 三片按序拼接逐字节 == 主件（runbook `docs/handoff/2026-09-17-eval-real-run-runbook.md:413`
   那句「✅ 与登记一致，题源没被碰过」今天被证伪，本钉把它换成可复跑的判据）。
3. 🔴 这不是「读盘上现成三片互相比一下」的永真式：判据来自**派生腿读主件**，所以只改主件
   不动三片也必红（`test_reverse_knife_only_the_master_moved`）；而把主件与三片按同规则一起
   派生则照绿（`test_legitimate_rederivation_still_passes`）——一把反向刀证明它跟着事实走，
   一把正刀证明它没把某一天的字节冻成牢。

【在册先例】同族病「手抄账与派生账分叉」由 R583（并树 `500d88a`）先治过一枚，本钉是第二枚。

【摘哪一把 → 哪枚红】见文件末 ``KNIVES``，每条都由一枚真断言守着，不是文档里的口头账。
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "r598_shard_sync.py"

#: 在册分片粒度（跟进单 §160.3 判据⑦）：35 + 35 + 35 = 105。
EXPECTED_SHARD_ROWS = (35, 35, 35)


@pytest.fixture(scope="module")
def sync():
    spec = importlib.util.spec_from_file_location("r598_shard_sync_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _live_root(sync, tmp_path: Path) -> Path:
    """把主件与三片原样搬进一枚临时根：反证只在临时根动手，仓库盘面一个字节不碰。"""
    root = tmp_path / "repo"
    for rel in list(sync.SHARD_RELS) + [sync.MASTER_REL]:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, dst)
    return root


def _failures(report: dict) -> list[int]:
    return [item["shard"] for item in report["shards"] if not item["byte_equal"]]


def _master_ids(master: bytes) -> list[str]:
    return [
        str(json.loads(line)["id"])
        for line in master.decode("utf-8-sig").splitlines()
        if line.strip()
    ]
# ---------------------------------------------------------------------------
# ① 绿态：盘上三片 == 从主件现派生的三片（逐字节），并把两边 sha256 前 16 打出来
# ---------------------------------------------------------------------------

def test_shards_are_byte_equal_to_the_derived_three_pieces(sync, capsys):
    report = sync.compare(REPO_ROOT)
    master = report["master"]
    lines = ["主件 {0} {1} B / sha256[:16] {2} / {3} 行 / BOM={4} / 行尾={5}".format(
        master["path"], master["bytes"], master["sha256_16"], master["lines"],
        master["has_bom"], master["line_ending"])]
    for item in report["shards"]:
        lines.append(
            "片{0} 盘上 {1} B / {2}  ⟺  派生 {3} B / {4}  ⇒ {5}".format(
                item["shard"], item["ondisk_bytes"], item["ondisk_sha256_16"],
                item["derived_bytes"], item["derived_sha256_16"],
                "逐字节相等" if item["byte_equal"] else "不等",
            )
        )
    lines.append("三片拼接 {0} B / {1}  ⟺  主件 {2} B / {3} ⇒ {4}".format(
        report["concat"]["bytes"], report["concat"]["sha256_16"],
        master["bytes"], master["sha256_16"],
        "逐字节相等" if report["concat"]["byte_equal_master"] else "不等"))
    print("\n".join(lines))

    assert len(master["sha256_16"]) == 16, "主件 sha256 前 16 没打全"
    for item in report["shards"]:
        assert len(item["ondisk_sha256_16"]) == 16 and len(item["derived_sha256_16"]) == 16, (
            "判据⑦要的两边 sha256 前 16 没打全：{0}".format(item["shard"]))
    assert _failures(report) == [], (
        "三片不是从主件逐字节派生的（红的是片 "
        + "、".join(str(n) for n in _failures(report)) + "）；跑 "
        "python scripts/r598_shard_sync.py --write 重派生，别手抄\n" + "\n".join(lines))
    assert report["concat"]["byte_equal_master"] is True, (
        "三片按序拼接不等于主件字节：runbook:413 那句 ✅ 又是手抄账\n" + "\n".join(lines))
    on_disk_rows = [len(sync.line_ids((REPO_ROOT / rel).read_bytes())) for rel in sync.SHARD_RELS]
    assert on_disk_rows == list(EXPECTED_SHARD_ROWS), (
        "分片行数漂了：判据⑦要的是 35/35/35，看到 {0}".format(on_disk_rows))


def test_id_order_is_preserved_across_the_three_pieces(sync):
    master = sync.read_master_bytes(REPO_ROOT)
    want = _master_ids(master)
    got: list[str] = []
    for rel in sync.SHARD_RELS:
        got.extend(sync.line_ids((REPO_ROOT / rel).read_bytes()))
    assert len(want) == 105 and len(got) == 105, "id 行数不是 105"
    assert got == want, "三片里的 id 顺序与主件不同：分片只许切字节，不许重排"


# ---------------------------------------------------------------------------
# ② 反证刀：每一把都必须在临时根上咬出红，仓库盘面一个字节不动
# ---------------------------------------------------------------------------

def _tamper_word(sync, tmp_path, shard_index=2):
    """刀a 的执行体：把盘上第 shard_index 片里**第一个汉字**换成另一枚汉字（同 3 字节，
    长度不漂），模拟「有人手抄时改了一个词」。咬不到肉的刀自己先报错。
    """
    root = _live_root(sync, tmp_path)
    path = root / sync.SHARD_RELS[shard_index - 1]
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    hit = re.search("[\u4e00-\u9fff]", text)
    assert hit, "刀a 自己没咬到肉：片{0} 里连一枚汉字都抠不到，这把反证是空转".format(shard_index)
    sub = "测" if hit.group(0) != "测" else "试"
    tampered = (text[:hit.start()] + sub + text[hit.start() + 1:]).encode("utf-8")
    assert tampered != raw and len(tampered) == len(raw), (
        "刀a 把「改一个词」改成了长度漂移，那它量的就不是本钉")
    path.write_bytes(tampered)
    return root, shard_index


def test_knife_a_one_word_tamper_in_a_shard_goes_red(sync, tmp_path):
    root, shard_index = _tamper_word(sync, tmp_path, shard_index=2)
    report = sync.compare(root)
    assert _failures(report) == [shard_index], (
        "手改片{0} 里一个词，钉却没指名它：{1}".format(shard_index, _failures(report)))
    assert report["concat"]["byte_equal_master"] is False, "偷改一个词后拼接仍算等于主件＝假绿"


def test_knife_b_missing_shard_refuses_rather_than_passing(sync, tmp_path):
    root = _live_root(sync, tmp_path)
    (root / sync.SHARD_RELS[2]).unlink()
    with pytest.raises(FileNotFoundError):
        sync.compare(root)


def test_knife_c_shard_order_drift_goes_red(sync, tmp_path):
    root = _live_root(sync, tmp_path)
    first = (root / sync.SHARD_RELS[0]).read_bytes()
    second = (root / sync.SHARD_RELS[1]).read_bytes()
    (root / sync.SHARD_RELS[0]).write_bytes(second)
    (root / sync.SHARD_RELS[1]).write_bytes(first)
    report = sync.compare(root)
    assert _failures(report) == [1, 2], "片序漂移没被指名：{0}".format(_failures(report))
    assert report["concat"]["byte_equal_master"] is False


def test_knife_d_added_bom_goes_red(sync, tmp_path):
    root = _live_root(sync, tmp_path)
    path = root / sync.SHARD_RELS[0]
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    report = sync.compare(root)
    assert _failures(report) == [1], "给片1 加 BOM 没被指名：{0}".format(_failures(report))
    assert report["concat"]["bytes"] == report["master"]["bytes"] + 3, (
        "拼接比主件多 3 字节却没人算账")


def test_knife_e_line_ending_conversion_goes_red(sync, tmp_path):
    root = _live_root(sync, tmp_path)
    path = root / sync.SHARD_RELS[2]
    raw = path.read_bytes()
    assert b"\r\n" in raw, "刀e 前提不成立：片3 不是 CRLF，换行符这把刀会空转"
    path.write_bytes(raw.replace(b"\r\n", b"\n"))
    report = sync.compare(root)
    assert _failures(report) == [3], "行尾改 LF 没被指名：{0}".format(_failures(report))


def test_knife_f_dropped_line_goes_red(sync, tmp_path):
    root = _live_root(sync, tmp_path)
    path = root / sync.SHARD_RELS[2]
    raw = path.read_bytes()
    path.write_bytes(raw[: raw.rfind(b"\r\n")])
    report = sync.compare(root)
    assert _failures(report) == [3], "少一行没被指名：{0}".format(_failures(report))


# ---------------------------------------------------------------------------
# ③ 反向刀（本钉不是永真式的凭据）与合法派生流
# ---------------------------------------------------------------------------

def test_reverse_knife_only_the_master_moved(sync, tmp_path):
    """只改主件一个词、三片原样不动 ⇒ 钉必须红。

    🔴 这一枚才是「派生腿真在读主件」的凭据：如果本件写成「读盘上现成三片互相比一下」，
    改主件不会让它红，那它就是永真式，也正是 runbook:413 犯的病。
    """
    root = _live_root(sync, tmp_path)
    master_path = root / sync.MASTER_REL
    raw = master_path.read_bytes()
    tampered = raw.replace("住宿".encode("utf-8"), "住店".encode("utf-8"), 1)
    assert tampered != raw, "反向刀自己没咬到肉：主件里抠不到「住宿」"
    master_path.write_bytes(tampered)
    report = sync.compare(root)
    assert _failures(report), "改了主件却没让任何一片红 ⇒ 派生腿没读主件，本钉是永真式"
    assert report["concat"]["byte_equal_master"] is False, (
        "主件变了而拼接仍等于主件 ⇒ 拼接读的不是真主件")


def test_legitimate_rederivation_still_passes(sync, tmp_path):
    """主件与三片按同规则一起派生 ⇒ 照绿：本钉跟着事实走，没把某一天的字节冻成牢。"""
    root = _live_root(sync, tmp_path)
    master_path = root / sync.MASTER_REL
    raw = master_path.read_bytes()
    tampered = raw.replace("住宿".encode("utf-8"), "住店".encode("utf-8"), 1)
    assert tampered != raw
    master_path.write_bytes(tampered)
    assert sync.compare(root)["all_shards_match"] is False
    sync.write_shards(root)
    report = sync.compare(root)
    assert report["all_shards_match"] is True and report["concat"]["byte_equal_master"] is True


# ---------------------------------------------------------------------------
# ③' CLI 出口：``main()`` 的 return 那一行也必须被真跑过
# ---------------------------------------------------------------------------

def test_cli_exit_code_tracks_the_byte_verdict(sync, tmp_path, capsys):
    """绿态 CLI 必须返 ``EXIT_MATCH``，手改一片后必须返 ``EXIT_MISMATCH``，sha16 必须真打出来。

    🔴 这一枚是给「量具有病但读数一片绿」补的牙：本件前面每一枚断言都直接调 ``compare()``／
    ``write_shards()``，**从没走过 CLI 的 return**，所以本单第一版把 ``EXIT_MATCH`` 写成不存在的
    ``EXIT_OK`` 时，13 枚照样全绿、``--check`` 却当场 ``NameError``（收工自证才抓到）。
    摘掉这一枚 => 出口再写错名字／返错码，没有任何人会报警。
    """
    green_root = _live_root(sync, tmp_path / "cli-green")
    assert sync.main(["--repo-root", str(green_root), "--check"]) == sync.EXIT_MATCH, (
        "三片等于派生时 CLI 没返绿码")
    out = capsys.readouterr().out
    assert re.search(r"[0-9a-f]{16}", out), "CLI 没把 sha256 前 16 打出来（判据⑦要两侧都打）"

    red_root, shard_index = _tamper_word(sync, tmp_path / "cli-red", shard_index=1)
    assert sync.main(["--repo-root", str(red_root), "--check"]) == sync.EXIT_MISMATCH, (
        "手改片{0} 一个词，CLI 出口却没翻红".format(shard_index))
    assert _failures(sync.compare(red_root)) == [shard_index], "红态对账没指名片1"



# ---------------------------------------------------------------------------
# ④ 派生器自身的两条拒绝对账（缺凭据就不许落盘）
# ---------------------------------------------------------------------------

def test_derive_refuses_when_the_master_line_count_is_not_105(sync):
    master = sync.read_master_bytes(REPO_ROOT)
    lines = master.splitlines(keepends=True)
    short = b"".join(lines[:-1])
    with pytest.raises(ValueError):
        sync.derive_shards(short)


def test_derivation_preserves_bom_and_bare_lf(sync):
    """合成一枚「带 BOM + 纯 LF」的 105 行主件：派生必须原样保留，不得加工。"""
    synthetic = b"\xef\xbb\xbf" + b"".join(
        ('{{"id": "x{0:03d}", "must_contain": ["甲"]}}\n'.format(n).encode("utf-8"))
        for n in range(1, 106)
    )
    shards = sync.derive_shards(synthetic)
    assert b"".join(shards) == synthetic, "派生把 BOM 或 LF 加工掉了"
    assert shards[0].startswith(b"\xef\xbb\xbf"), "首片必须带走主件的 BOM"
    assert all(b"\r" not in raw for raw in shards), "派生不许把 LF 改成 CRLF"


def test_the_knife_ledger_names_only_real_tests():
    """把「摘哪一把 → 哪枚红」这张纸面账升成可执行的牙。

    纸上的刀谱最容易烂：改了测试名、删了一枚刀，纸还在说「它守着这一格」。所以 KNIVES 里点到的
    每一枚测试名都必须真在本件里存在，且必须是会红的断言函数（不是注释）。交工纸 §6 抄的就是这张账。
    """
    import re as _re

    names = set(globals())
    cited = set()
    for entry in KNIVES:
        cited.update(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", entry))
    missing = sorted(name for name in cited if name.startswith("test_") and name not in names)
    assert missing == [], "刀谱里点了本件不存在的测试（纸面账已烂）：" + "、".join(missing)
    for entry in KNIVES:
        assert any(token in entry for token in globals() if token.startswith("test_")), (
            "这一行没点到任何一枚真测试：" + entry)
    declared = [name for name in sorted(names) if name.startswith("test_")]
    covered = {name for entry in KNIVES for name in declared if name in entry}
    unguarded = sorted(set(declared) - covered - {"test_the_knife_ledger_names_only_real_tests"})
    assert unguarded == [], "这些测试没进刀谱，交工纸 §6 就少点名了：" + "、".join(unguarded)


#: 摘哪一把 → 哪枚红（交工纸同款账；上一条测试逐枚验它，防止纸面账先烂）。
KNIVES = (
    "刀a 手改片2 一个词 → test_knife_a_one_word_tamper_in_a_shard_goes_red 红（片2 指名）",
    "刀b 少一片 → test_knife_b_missing_shard_refuses_rather_than_passing 红（拒绝出数）",
    "刀c 片序漂移 → test_knife_c_shard_order_drift_goes_red 红（片1+片2 指名）",
    "刀d 给片1 加 BOM → test_knife_d_added_bom_goes_red 红（拼接多 3 字节同场记账）",
    "刀e 行尾改 LF → test_knife_e_line_ending_conversion_goes_red 红（片3 指名）",
    "刀f 少一行 → test_knife_f_dropped_line_goes_red 红（片3 指名）",
    "反向刀 只改主件不动三片 → test_reverse_knife_only_the_master_moved 红（永真式凭据）",
    "派生器拒收 104 行 → test_derive_refuses_when_the_master_line_count_is_not_105 红",
    "绿态主判 三片不等于从主件现派的三片 → test_shards_are_byte_equal_to_the_derived_three_pieces 红（两边 sha256 前 16 逐枚打印）",
    "分片里重排 id → test_id_order_is_preserved_across_the_three_pieces 红",
    "派生器把主件的 BOM/行尾加工掉 → test_derivation_preserves_bom_and_bare_lf 红",
    "正刀（不是刀）主件与三片同规则一起重派生 → test_legitimate_rederivation_still_passes 照绿：钉跟着事实走",
    "刀g CLI 出口写错名字或返错码 → test_cli_exit_code_tracks_the_byte_verdict 红（绿态必须 EXIT_MATCH、手改片1 必须 EXIT_MISMATCH，两侧 sha256 前 16 必须真打出来）",
)