# -*- coding: utf-8 -*-
"""R400 · 回填账的下牙：那张"照这份计划回填之后"的梯子，判词只能有一本账。

派工词 §三 要的不是又一份工具，是三个读数：A1 / A2 / A3 今天各能落地多少、
哪一格必须业主本人出手、以及"只回填部门不回填密级"那一格 C 为什么仍然未验。
上一班的答案写在文档 §2.3/§3，抄的是量具的输出 —— 抄一遍就多一本账：今天已经
在 §2.3 抓到一枚漂了的数（"研发 721"，现读 713）。所以本班把答案改写成
`scripts/r387_backfill_estimate.py::unlock_ladder` 一张可复跑的梯级表，本件钉它：

① A1 单独做**不移动判词**：补 `users.department` 只影响以后的上传（服务端在上传那一跳
   覆盖），存量那 1008 枚一个字都不动 —— S0 与 S1 的判词必须逐字相同。谁把 A1 写成
   "回填了一步"，这一枚就红。
② 梯级一次只挪开一件可失败判据：判词序列必须是
   空标签 ×3（S0/S1/S2）→ 密级无选择性 ×2（S3/S3b）→ 召回空集（S4）→ 已验（S5）→
   越权优先判「不通过」（S6）。任何一格跳级或自己发明原因码，都说明判序被抄了第二份。
③ 只回填部门那一格为什么仍未验：S3 的原因码必须是 `REASON_NO_CLASSIFICATION_SELECTIVITY`；
   把密级抬到 2 档后堵点前移到 `REASON_EMPTY_RETURN`（要真测召回），而不是变成"通过"。
④ 零召回不许被叫成已验：语料再满、`recalled=0` 就是未验（空集不是证据那一族的另一条腿）。
⑤ 本件与量具都不许有写口：AST 读不出 connect / execute / cursor / INSERT / UPDATE，
   `writes_issued` 恒为 0，`main(--no-db)` 原样交回今天的读数。

计划样本全部是合成名（不往测试里嵌客户文件名）；生产侧那三个数走只读 psql，见回执。
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LINEAGE_REL = "scripts/r387_label_lineage.py"
BACKFILL_REL = "scripts/r387_backfill_estimate.py"


def _load(rel: str, name: str):
    path = REPO / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "无法加载：" + str(path)
    module = importlib.util.module_from_spec(spec)
    #: frozen dataclass 要回查 sys.modules[cls.__module__]；量具也用同名登记，两枚件共用一本账。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: 名字必须与量具自己的模块名一致：回填量具 `from r387_label_lineage import ...` 才会
#: 拿到**同一枚** classify_arm，而不是复制出第二判序（那是 migrations 里 COMMENT 警告的形状）。
TOOL = _load(LINEAGE_REL, "r387_label_lineage")
BF = _load(BACKFILL_REL, "r400_backfill_estimate")

#: 合成样本（两枚单归属、一枚多归属、一枚零线索）：不往测试里嵌客户文件名，
#: 但部门线索必须**跨两枚**，否则第 3 级会先撞"只有一枚部门"那一格，量不到密级那一格。
SAMPLE_NAMES = {"差旅报销细则.txt": 5, "员工手册_2025正式版.txt": 3,
                "客户数据保护政策.txt": 2, "未命名扫描件_0001.pdf": 1}


@pytest.fixture(scope="module")
def plan() -> dict:
    return BF.plan_from_names(SAMPLE_NAMES)


@pytest.fixture(scope="module")
def ladder(plan: dict) -> list:
    return BF.unlock_ladder(plan, 1)


def rung(ladder: list, key: str) -> dict:
    return next(row for row in ladder if row["rung"] == key)


def reasons(ladder: list) -> list:
    return [row["verdict"]["reason"] for row in ladder]


# ------------------------------------------------------------------ ① A1 不治存量

def test_a1_alone_does_not_move_the_verdict(ladder: list) -> None:
    """🔴 业主今天做 A1，验收 C 的判词一个字都不会变：它治的是"以后"，不是存量。

    这一枚是回填账里最容易被读反的一格：把"补账号部门"当成"回填了一步"，
    下一步就会有人拿它去勾验收 C。
    """
    today, after_a1, after_a2 = reasons(ladder)[:3]
    assert today == after_a1 == after_a2, (
        "S0/S1/S2 判词出现分歧：A1、A2 被算成了治存量的动作 " + str([today, after_a1, after_a2]))
    assert today == TOOL.REASON_NO_LABELLED_CHUNK
    assert rung(ladder, "S1")["verdict"]["verdict"] == TOOL.UNVERIFIED


def test_the_untouched_corpus_size_is_carried_by_every_early_rung(ladder: list) -> None:
    """S0–S2 三级的语料账必须都是"0 枚带部门"：这条就是存量一格没动的那本账。"""
    for key in ("S0", "S1", "S2"):
        assert rung(ladder, key)["arm"]["corpus_labelled_chunks"] == 0, key


# ------------------------------------------------------------------ ②③ 梯级一次挪一件

def test_the_ladder_moves_one_gate_at_a_time(ladder: list) -> None:
    """🔴 判词序列：空标签 → 密级无选择性 → 召回空集 → 已验 →（越权优先）不通过。"""
    assert reasons(ladder) == [
        TOOL.REASON_NO_LABELLED_CHUNK, TOOL.REASON_NO_LABELLED_CHUNK, TOOL.REASON_NO_LABELLED_CHUNK,
        TOOL.REASON_NO_CLASSIFICATION_SELECTIVITY, TOOL.REASON_NO_CLASSIFICATION_SELECTIVITY,
        TOOL.REASON_EMPTY_RETURN, "标签非空、两轴都有选择性、召回非空且零越权", TOOL.REASON_BREACH], \
        str(reasons(ladder))


def test_no_rung_invents_a_second_verdict_vocabulary(ladder: list) -> None:
    """每一级的判词与原因码都取自量具那一份词汇表：梯子里不许有自造的第二本账。"""
    allowed = {TOOL.VERIFIED, TOOL.UNVERIFIED, TOOL.FAILED}
    codes = {value for name, value in vars(TOOL).items() if name.startswith("REASON_")}
    codes.add(TOOL.classify_arm(BF._corpus_arm("probe", ("财务", "研发"), labelled=10,
                                               kinds=2, recalled=10))["reason"])
    for row in ladder:
        assert row["verdict"]["verdict"] in allowed, row["rung"]
        assert row["verdict"]["reason"] in codes, row["rung"] + " 的原因码不在册：" + row["verdict"]["reason"]
        assert row["verdict"]["arm"] == row["rung"], row


def test_department_only_backfill_still_leaves_c_unverified(ladder: list) -> None:
    """🔴 派工词那一格的正面回答：只回填部门，C 仍挂在"密级只有一档"；抬上两档就换它堵。

    所以"回填 = 可以勾验收 C"这句在这里不成立，两次都不成立：
    S3 卡密级，S4 卡召回 —— 而召回那一格要真在生产上量，本单不起服务、不打模型。
    """
    assert rung(ladder, "S3")["verdict"]["reason"] == TOOL.REASON_NO_CLASSIFICATION_SELECTIVITY
    assert rung(ladder, "S3b")["verdict"]["reason"] == TOOL.REASON_NO_CLASSIFICATION_SELECTIVITY
    assert rung(ladder, "S4")["verdict"]["reason"] == TOOL.REASON_EMPTY_RETURN
    assert rung(ladder, "S3")["arm"]["corpus_labelled_chunks"] > 0, "第 3 级连部门都没回填，梯子是空的"


# ------------------------------------------------------------------ ④ 空集不是证据

@pytest.mark.parametrize("labelled", [0, 1, 923, 1008])
@pytest.mark.parametrize("kinds", [1, 2, 4])
def test_a_zero_recall_arm_is_never_called_verified(labelled: int, kinds: int) -> None:
    """语料再满、密级再多，`recalled=0` 就不许判"已验"：0 越权与 0 召回是同一个空集。"""
    arm = BF._corpus_arm("probe", ("财务", "研发"), labelled=labelled, kinds=kinds, recalled=0)
    assert TOOL.classify_arm(arm)["verdict"] == TOOL.UNVERIFIED, (labelled, kinds)


def test_a_breach_outranks_every_unverified_reason() -> None:
    """越权优先：哪怕同一格里密级只有一档，量出越权就必须判"不通过"，不能被"未验"盖掉。"""
    arm = BF._corpus_arm("probe", ("财务", "研发"), labelled=1008, kinds=1, recalled=1008, breaches=3)
    verdict = TOOL.classify_arm(arm)
    assert verdict["verdict"] == TOOL.FAILED and verdict["reason"] == TOOL.REASON_BREACH, verdict


# ------------------------------------------------------------------ ⑤ 账的完整性与零写入

def test_a_rule_that_reaches_one_department_stops_one_rung_earlier() -> None:
    """把规则收窄到一枚部门：梯级就必须先卡在"没有跨部门可选"，而不是跳到密级。
    这一枚盯的是"选择性两轴各是各的洞"：只补部门数量、不补分布，照样量不出隔离。
    """
    single = BF.plan_from_names({"差旅报销细则.txt": 5, "员工手册与安全须知.txt": 3})
    assert single["departments_reachable_by_rule"] == ["财务"], single["automatic"]
    rows = {row["rung"]: row for row in BF.unlock_ladder(single, 4)}
    assert rows["S3"]["verdict"]["reason"] == TOOL.REASON_NO_DEPARTMENT_SELECTIVITY
    assert rows["S0"]["verdict"]["reason"] == TOOL.REASON_NO_LABELLED_CHUNK


def test_the_plan_buckets_are_exhaustive_and_disjoint(plan: dict) -> None:
    """三份桶必须不多不少盖住全部：漏一格就是"回填账比语料少"，多一格就是重复计。"""
    assert plan["automatic_files"] + plan["manual_review_files"] == plan["total_files"]
    assert plan["automatic_chunks"] + plan["manual_review_chunks"] == plan["total_chunks"]
    assert set(plan["ambiguous"]) & set(plan["unhinted"]) == set()
    assert plan["automatic_chunks"] == sum(item["chunks"] for item in plan["automatic"].values())
    assert plan["departments_reachable_by_rule"] == sorted(plan["automatic"])


def test_the_reachable_departments_come_from_the_public_rule_only(plan: dict) -> None:
    """规则可达的部门必须是 `DEPARTMENT_HINTS` 的子集：梯子里不许有人手抄一份部门名册。"""
    assert set(plan["departments_reachable_by_rule"]) <= set(TOOL.DEPARTMENT_HINTS)


@pytest.mark.parametrize("word", ["INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE"])
def test_the_backfill_ruler_has_no_write_statement(word: str) -> None:
    """回填量具的可执行字符串里不许出现任何写语句：它只量，写不写由业主批。"""
    tree = ast.parse((REPO / BACKFILL_REL).read_bytes().decode("utf-8"))
    strings = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
               and isinstance(node.value, str)]
    assert not [value for value in strings if word in value.upper()], strings[:3]


def test_the_backfill_ruler_has_no_connection_surface() -> None:
    """本件与量具的连接面只在 `read_postgres` 那一腿；回填量具自己不许另开一条。"""
    tree = ast.parse((REPO / BACKFILL_REL).read_bytes().decode("utf-8"))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)}
    forbidden = {"connect", "execute", "executemany", "cursor", "commit"}
    assert not (called & forbidden), "回填量具自己动库了：" + str(sorted(called & forbidden))


def test_the_cli_reproduces_the_ladder_from_a_names_file(tmp_path: Path,
                                                        capsys: pytest.CaptureFixture) -> None:
    """🔴 交回的不是我抄的一行字：同一份 names 喂进去，命令行就能把这张梯子重打一遍。"""
    names = tmp_path / "names.tsv"
    body = "".join(name + "\t" + str(count) + "\n" for name, count in SAMPLE_NAMES.items())
    names.write_text(body, encoding="utf-8")
    code = BF.main(["--no-db", "--names-file", str(names), "--unlock-ladder"])
    caught = capsys.readouterr()
    assert code == 0, caught.out + caught.err if hasattr(caught, "err") else caught.out
    for row in BF.unlock_ladder(BF.plan_from_names(SAMPLE_NAMES), 1):
        assert any(line.startswith(row["rung"] + " ") for line in caught.out.splitlines()), row["rung"]
    assert "本件写入行数：0" in caught.out, caught.out