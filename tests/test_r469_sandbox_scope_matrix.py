# -*- coding: utf-8 -*-
"""R469 常驻账件 · C 门检索侧的逐档期望集合：由在册件现推，读数由产品本体重判（全程离线）。

为什么这本账值得常驻（跟进单 §133 六 / 计划书 §13.一）：生产/演示库 1008 枚向量
`department` 全空、`classification` 全 = 1，于是 `app/rag/filters.py:47-52` 那道 `allows()`
**没有东西可判** ⇒ 「跨部门/跨密级命中 0 条」与阶段 C 那句「越权 0 条」是空集真。
本单把那格从空集换成一次真库读数，而**读数一旦只住在纸上，下一班就会抄**——所以：

- 逐档**期望集合**不在本件里手抄：它由 `scripts/r59c_sandbox_corpus.py` 现造语料 +
  产品自己的 `resolve_document_retrieval_scope()` 现推，再与盘上读数逐枚比。
  r59c 哪天改了取值域，本件红，而不是悄悄跟着抄错。
- 逐档**判定**也不在本件里写死：它由 `scripts/r469_readout_lib.py` 拿产品本体的 `allows()`
  对记录在案的命中重判一遍。
- 生产那格仍按 §13.一 记「未验」：本件钉的是「生产臂逐档空集」这一条事实，
  谁把它写成通过，`test_production_library_is_still_an_empty_set_for_every_department_tier`
  与读数表的 `validate_readout()` 两处一起拦。

零真库、零容器、零模型：只读仓内文件＋跑离线算术。三把反证钉（T1/T2/T3）全在进程内改副本，
不落盘、不连库。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LIB_PATH = REPO_ROOT / "scripts" / "r469_readout_lib.py"
READOUT_PATH = REPO_ROOT / "docs" / "testing" / "r469-sandbox-scope-readout-2026-09-28.md"


def _load(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("r469_readout_lib", LIB_PATH)


def _r59c():
    import scripts.r59c_sandbox_corpus as module

    return module


def _scope_resolver():
    from app.rag.filters import resolve_document_retrieval_scope

    return resolve_document_retrieval_scope


def _principal(spec: dict):
    """主体形状与 r59c 的 load_scope_resolver（:161-174）逐字同形，本件不自立第四种主体。"""
    from app.agents.contracts import Principal

    return Principal(user_id=spec["username"], username=spec["username"],
                     roles=[spec["role"]], permissions=[],
                     department=spec["department"], department_ids=[],
                     clearance=int(spec["clearance"]), status="active")


@pytest.fixture(scope="module")
def evidence() -> dict:
    markdown = READOUT_PATH.read_text(encoding="utf-8")
    return lib.extract_evidence(markdown)


@pytest.fixture(scope="module")
def corpus(evidence: dict):
    """由在册件现造的语料；sha 必须与读数记的那枚对上，否则下面全部期望都建在别的语料上。"""
    record = evidence
    built = _r59c().build_corpus(
        len(_r59c().DEPARTMENTS) * len(_r59c().CLASSIFICATIONS)
        * record["corpus"]["ordinals_per_cell"],
        dimension=record["corpus"]["dimension"])
    assert _r59c().corpus_sha(built) == record["corpus"]["corpus_sha"], (
        "r59c 现在造的语料与读数当时造的不是同一份 ⇒ 本读数表需重跑，不许把期望集合改一改")
    return built


def _tier_by_label(arm: dict, label: str) -> dict:
    return next(tier for tier in arm["tiers"] if tier["label"] == label)


def _expected_admitted(corpus: dict, spec: dict) -> list:
    scope = _scope_resolver()(_principal(spec))
    return sorted(row["vector_id"] for row in corpus["chunks"] if scope.allows(
        {"id": row["vector_id"], "department": row["department"],
         "classification": row["classification"]}))


def _label_of(corpus: dict, vector_id: str) -> tuple:
    row = next(item for item in corpus["chunks"] if item["vector_id"] == vector_id)
    return (row["classification"], row["department"])


# ------------------------------------------------------------------ 账：名册与 scope


def test_the_readout_is_the_shape_this_ticket_promised(evidence: dict) -> None:
    assert evidence["schema"] == lib.EVIDENCE_SCHEMA
    assert evidence["ticket"] == lib.TICKET
    assert evidence["generated_by"] == lib.DRIVER
    assert sorted(evidence["invariants"]["core_six"]["tables"]) == sorted(
        lib.CORE_INVARIANT_TABLES)
    assert set(evidence["arms"]) == set(lib.ARMS)


def test_the_tier_roster_is_r59cs_own_and_nobody_added_a_sixth(evidence: dict) -> None:
    """五档 principal 的名字、角色、部门、密级与期望，逐枚等于在册件自带的那五枚。"""
    recorded = [(tier["label"], tier["role"], tier["department"], tier["clearance"],
                 tier["expect"]) for tier in evidence["arms"]["sandbox"]["tiers"]]
    expected = [(spec["label"], spec["role"], spec["department"], int(spec["clearance"]),
                 spec["expect"]) for spec in _r59c().PRINCIPALS]
    assert recorded == expected, "本单的档位被加/减/改过——那是第二套权限口径的开始"


@pytest.mark.parametrize("spec", _r59c().PRINCIPALS, ids=lambda item: item["label"])
def test_every_tiers_scope_still_comes_out_of_the_product_function(
        evidence: dict, spec: dict) -> None:
    """记录在案的谓词形状今天仍能由产品本体推出：filters / levels / departments / reason。

    这格盯的是「读数当时的 scope 是不是产品自己算的」。今天再算一遍不同 ⇒ 要么真源改了口径，
    要么读数被手改过，两样都不许把这张表继续往下抄。
    """
    tier = _tier_by_label(evidence["arms"]["sandbox"], spec["label"])
    scope = _scope_resolver()(_principal(spec))
    assert dict(scope.filters) == tier["filters"], spec["label"]
    assert sorted(scope.classification_levels) == tier["levels"], spec["label"]
    assert (None if scope.departments is None else sorted(scope.departments)
            ) == tier["departments"], spec["label"]
    assert scope.reason_code == tier["scope_reason"], spec["label"]


@pytest.mark.parametrize("spec", _r59c().PRINCIPALS, ids=lambda item: item["label"])
def test_expected_admitted_set_per_tier_is_derived_not_copied(
        evidence: dict, corpus: dict, spec: dict) -> None:
    """逐档期望集合的正身：现在推一遍 = 读数记的那一枚集合，一字不差。"""
    tier = _tier_by_label(evidence["arms"]["sandbox"], spec["label"])
    assert tier["r59c_admitted_ids"] == _expected_admitted(corpus, spec), spec["label"]


# ------------------------------------------------------------------ 账：命中与判定


def test_no_tier_returns_a_hit_outside_its_own_scope(evidence: dict) -> None:
    verdict = lib.judge(evidence)
    sandbox = verdict["arms"][lib.ARM_SANDBOX]
    assert evidence["arms"][lib.ARM_SANDBOX]["live_breaches"] == 0
    for cell in sandbox["tiers"]:
        assert cell["j2_breaches"] == [], cell["label"]
        assert cell["cell"] == lib.CELL_MEASURED, (cell["label"], cell["cell_why"])


def test_hit_labels_stay_inside_the_grid_each_tier_is_allowed(
        evidence: dict, corpus: dict) -> None:
    """命中项的两维标签必须落在「本部门 × 本人可读数」那格里——跨部门/跨密级一条都不许有。"""
    cells = {cell["label"]: cell for cell in lib.judge(evidence)["arms"][lib.ARM_SANDBOX]["tiers"]}
    by_id = {row["vector_id"]: row for row in corpus["chunks"]}
    checked = 0
    for tier in evidence["arms"][lib.ARM_SANDBOX]["tiers"]:
        cell = cells[tier["label"]]
        allowed_levels = set(tier["levels"])
        allowed_depts = tier["departments"]
        for level, department in cell["hit_labels"]:
            assert level in allowed_levels, (tier["label"], level)
            if allowed_depts is not None:
                assert department in allowed_depts, (tier["label"], department)
        for vector_id in cell["hit_ids"]:
            row = by_id[vector_id]
            pair = (row["classification"], row["department"])
            assert pair in {tuple(item) for item in cell["hit_labels"]}, vector_id
            checked += 1
    assert checked > 0, "一枚命中都没核对，这格等于没判"


def test_every_anchor_row_comes_back_to_the_tier_that_may_read_it(
        evidence: dict, corpus: dict) -> None:
    """自探针的正格：某档能读那一格，锚点行就必须出现在它的命中里（距离 0 都能少给就是漏）。"""
    hit_ids = {cell["label"]: set(cell["hit_ids"]) for cell in
               lib.judge(evidence)["arms"][lib.ARM_SANDBOX]["tiers"]}
    checked = 0
    for spec in _r59c().PRINCIPALS:
        scope = _scope_resolver()(_principal(spec))
        for anchor in evidence["corpus"]["anchors"]:
            row = next(item for item in corpus["chunks"] if item["vector_id"] == anchor)
            hit = {"id": anchor, "department": row["department"],
                   "classification": row["classification"]}
            if scope.allows(hit):
                assert anchor in hit_ids[spec["label"]], (spec["label"], anchor)
                checked += 1
    assert checked > 0, "一枚自探针都没跑起来，这格等于没判"


def test_the_pool_held_material_every_tier_may_not_read(evidence: dict) -> None:
    """把「0 条越权」从空集变成有牙读数的正是这一格：每档池里都有它读不到的料。"""
    verdict = lib.judge(evidence)
    for cell in verdict["arms"][lib.ARM_SANDBOX]["tiers"]:
        assert cell["outside_pool_total"] > 0, cell["label"]
        assert cell["admitted_total"] < cell["pool_total"], cell["label"]
    for cell in verdict["arms"][lib.ARM_SANDBOX]["tiers"]:
        assert cell["control"]["available"] is True, cell["label"]
        assert cell["control"]["rejected_by_allows"] is True, cell["label"]


def test_the_unscoped_arm_reaches_labels_the_scoped_arm_never_shows(evidence: dict) -> None:
    """同一条查询向量，不带谓词时读得到的标签，带谓词后必须一条都不出现——牙在这里。"""
    cells = {cell["label"]: cell for cell in lib.judge(evidence)["arms"][lib.ARM_SANDBOX]["tiers"]}
    for tier in evidence["arms"][lib.ARM_SANDBOX]["tiers"]:
        if tier["departments"] is None:
            continue
        cell = cells[tier["label"]]
        scoped_labels = {tuple(item) for item in cell["hit_labels"]}
        unscoped_labels = {(hit["classification"], str(hit["department"]))
                           for read in tier["reads"] for hit in read["unscoped"]}
        foreign = unscoped_labels - scoped_labels
        assert foreign, tier["label"]
        assert cell["counterfactual_total"] > 0, tier["label"]
        assert scoped_labels.isdisjoint(foreign), (tier["label"], scoped_labels & foreign)


def test_the_semantic_leg_answered_from_the_real_database(evidence: dict) -> None:
    """候选宽度不自带数字：记下来的那档必须等于真源今天的缺省读数。"""
    from app.rag import pg_store

    record = evidence["run"]
    assert record["hnsw_ef_search_source"] == _r59c().TRUE_SOURCE
    assert record["hnsw_ef_search"] == pg_store.configured_hnsw_ef_search({}), (
        "读数站的档与生产缺省档不同 ⇒ 这批复数站在另一个系统上，须重跑")
    assert record["vector_scope"]["dimension"] == evidence["corpus"]["dimension"]
    assert record["vector_scope"]["distance_function"] == _r59c().DISTANCE_FUNCTION


def test_the_selective_filter_did_not_lose_a_hit_at_this_size(evidence: dict) -> None:
    """J-3：沙盒臂逐档逐题的 top-k 与暴力精确解集合全等、槽位全等——只在这一档成立。"""
    summary = lib.judge(evidence)["j3_summary"]
    assert summary["judged"] == 60, summary
    assert summary["sets_equal"] == summary["judged"], summary
    assert summary["slots_equal"] == summary["slots_total"], summary
    first = lib.judge(evidence)["arms"][lib.ARM_SANDBOX]["tiers"][0]
    assert first["j3"]["missing"] == [] and first["j3"]["extra"] == []


# ------------------------------------------------------------------ 账：生产那格仍是空集


def test_production_library_is_still_an_empty_set_for_every_department_tier(
        evidence: dict) -> None:
    """§133 六那条真账的常驻钉：生产库标签全同值 ⇒ 检索侧逐档空集，越权 0 条无从判。

    这格变绿有两种方式，只有一种正当：业主回填真实标签（A1/A3）后重跑本单；
    把期望集合改成现在读得出的样子，就是把「未验」抄成「已验」。
    """
    arm = evidence["arms"]["production"]
    assert arm["writes"] == 0
    assert arm["live_breaches"] == 0
    labels = arm["pool_labels"]
    assert labels["nonempty_department"] == 0, "生产库部门已回填 ⇒ 本读数表需重跑"
    assert labels["dept_empty"] == labels["rows_total"]
    assert labels["distinct_classifications"] == ["1"], "生产库密级已回填 ⇒ 需重跑"
    verdict = lib.judge(evidence)["arms"]["production"]
    for cell in verdict["tiers"]:
        assert cell["cell"] == lib.CELL_VACUOUS, (cell["label"], cell["cell"])
        if cell["departments"] is not None:
            assert cell["admitted_total"] == 0, cell["label"]
        else:
            assert cell["outside_pool_total"] == 0, cell["label"]
    assert verdict["status"] == lib.STATUS_NOT_MEASURED


def test_the_write_never_touched_the_production_tables(evidence: dict) -> None:
    core = evidence["invariants"]["core_six"]
    assert core["before"] == core["after"] and core["match"] is True
    labels = evidence["invariants"]["production_labels"]
    assert labels["before"] == labels["after"] and labels["match"] is True
    identity = evidence["run"]["production_identity_after"]
    assert identity["database"] == evidence["run"]["production_identity"]["database"]
    assert identity["transaction_read_only"] == "on"
    assert evidence["run"]["production_identity"]["server_addr"] == \
        evidence["run"]["sandbox_identity"]["server_addr"], "两臂必须连同一台真库"


def test_the_sandbox_rows_were_named_and_removed(evidence: dict) -> None:
    clean = evidence["cleanup"]
    prefix = evidence["corpus"]["vector_id_prefix"]
    assert clean["inserted"] == clean["deleted"] == evidence["corpus"]["chunks"]
    assert clean["leftover_prefixed_rows"] == 0
    assert prefix and prefix in clean["write_shape"]
    sandbox = evidence["invariants"]["sandbox"]
    assert sandbox["before"] == sandbox["after"] and sandbox["match"] is True


# ------------------------------------------------------------- 反证钉 T1 / T2 / T3


def test_counter_evidence_neutered_allows_turns_the_control_red(evidence: dict) -> None:
    """T1：把产品那道 `allows()` 摘成恒 True ⇒ 每档 control 当场红，整单判红。

    钉的是「本单读数真的依赖那一道判定」。摘掉它还能判出「越权 0 条」，说明那句 0 是空的。
    """
    verdict = lib.judge(evidence, admits=lambda tier, hit: True)
    assert verdict["status"] == lib.STATUS_RED, verdict["why"]
    red = {(cell["arm"], cell["label"]): cell["cell"] for cell in verdict["red_cells"]}
    sandbox_labels = [spec["label"] for spec in _r59c().PRINCIPALS]
    for label in sandbox_labels:
        assert red[(lib.ARM_SANDBOX, label)] == lib.CELL_RED_CONTROL, label
    assert verdict["measured_cells"] == []


def test_counter_evidence_bypassed_predicate_reports_breaches(evidence: dict) -> None:
    """T2：拿「无谓词那一臂」的命中冒充「有谓词那一臂」⇒ 越权条数必须 > 0 且点名到行。"""
    poisoned = copy.deepcopy(evidence)
    for tier in poisoned["arms"][lib.ARM_SANDBOX]["tiers"]:
        for read in tier["reads"]:
            read["scoped"] = copy.deepcopy(read["unscoped"])
    baseline = lib.judge(evidence)
    assert baseline["status"] != lib.STATUS_RED
    verdict = lib.judge(poisoned)
    assert verdict["status"] == lib.STATUS_RED, verdict["why"]
    by_label = {cell["label"]: cell for cell in verdict["arms"][lib.ARM_SANDBOX]["tiers"]}
    for spec in _r59c().PRINCIPALS:
        cell = by_label[spec["label"]]
        if cell["departments"] is None:
            continue
        assert cell["cell"] == lib.CELL_RED_BREACH, (spec["label"], cell["cell"])
        assert cell["j2_breaches"], spec["label"]
        breach = cell["j2_breaches"][0]
        assert breach["department"] not in cell["departments"], breach


def test_counter_evidence_homogeneous_labels_lose_selectivity(evidence: dict) -> None:
    """T3：把沙盒标签抹成生产那种同值 ⇒ 逐档退回空集真，整单 `NOT_MEASURED`。

    这就是「越权 0 条」在今天生产上的真实形状：它不是通过，它是没东西可判。
    """
    flat = copy.deepcopy(evidence)
    for tier in flat["arms"][lib.ARM_SANDBOX]["tiers"]:
        tier["admitted_total"] = 0 if tier["departments"] else tier["pool_total"]
        tier["r59c_admitted_ids"] = []
        tier["outside_sample"] = None if tier["departments"] is None else tier["outside_sample"]
        # 命中本身不动：本档抹的是「标签分布 + 可判面」，动命中＝造出一格真越权，
        # 那是 T2 的形状，不是 §133 六的空集形状。
    pool_labels = flat["arms"][lib.ARM_SANDBOX]["pool_labels"]
    pool_labels["nonempty_department"] = 0
    pool_labels["distinct_departments"] = [""]
    pool_labels["distinct_classifications"] = ["1"]
    pool_labels["distinct_pairs"] = 1
    pool_labels["r59c_distinct_pairs"] = 0

    verdict = lib.judge(flat)
    assert verdict["status"] == lib.STATUS_NOT_MEASURED, verdict["why"]
    assert verdict["measured_cells"] == []
    for cell in verdict["arms"][lib.ARM_SANDBOX]["tiers"]:
        assert cell["cell"] == lib.CELL_VACUOUS, (cell["label"], cell["cell"])
    assert verdict["arms"][lib.ARM_SANDBOX]["criteria"]["d_zero_breach"]["verdict"] == \
        lib.UNVERIFIED
