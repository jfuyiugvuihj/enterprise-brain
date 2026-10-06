# -*- coding: utf-8 -*-
"""R676 判据 ①②③ · 同义词族 top-5 变化率量具的牙。

打桩边界（每处都写清楚，免得被读成「测试自己造了个改进」）：

- 两臂跑的是**生产** ``RetrievalPipeline.search()`` 本体（量具只做顺序钉与替身腿），
  族成员与扩展词全部由产品自己的 ``expand_query_synonyms`` 现定，本件不手写题号。
- 语义腿需要 embedding 模型调用 ⇒ 用在册替身恒回 0 行，本件所有 top-5 读数都是
  **词腿单腿口径**；真机两腿那一格归凭据纸的「待窗」清单，不在这里冒充已验。
- 模型面放两枚绊线（``retrieval_pipeline.model`` 计数器 + 顶在 ``QueryRewriter`` 位置上的
  rewrite 绊线）：任何一发往返都当场炸。判据 ②「改写仍走规则不新增模型往返」因此
  既有运行时的数、也有 ast 的静态形状。
- 术语目录在测量期内钉成仓内出厂词表（``registry._database_available`` → False），
  本机有没有 PostgreSQL、客户库里有没有目录行，都不许改这张表里的族成员。
全程零网络、零写盘；闸门的**生命周期**由下面那枚钉管（在册教训：装了不还毒死整个会话）。
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GAUGE_REL = Path("scripts/r676_synonym_top5_delta.py")
FIXTURE_REL = Path("tests/fixtures/business_evaluation_100.jsonl")
PIPELINE_REL = Path("app/rag/retrieval_pipeline.py")

#: 族成员＝量具在本基点上现读的 15 枚（凭据纸逐枚点名；顺序＝题集顺序）。
FAMILY_IDS = ["doc-01", "doc-03", "doc-07", "doc-08", "doc-09", "doc-16", "doc-17",
              "chat-04", "chat-07", "metric-03", "data-04", "data-08", "data-10",
              "approval-01", "report-01"]


def load_by_path(rel: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gauge():
    return load_by_path(GAUGE_REL, "r676_gauge")


@pytest.fixture(scope="module")
def r219(gauge):
    return gauge.load_r219()


@pytest.fixture(scope="module")
def report(gauge, r219):
    """整族一次全量测量：全套牙共用同一份读数，不重复付重量。"""
    before = hashlib.sha256((REPO_ROOT / FIXTURE_REL).read_bytes()).hexdigest()
    result = gauge.measure(r219)
    after = hashlib.sha256((REPO_ROOT / FIXTURE_REL).read_bytes()).hexdigest()
    assert before == after, "量具跑过之后 105 题夹具的字节变了——乙案第一格就是不许动它"
    gauge.validate_report(result)
    return result


@pytest.fixture(scope="module")
def summary(report):
    return report["summary"]


@pytest.fixture(scope="module")
def rows(report):
    return report["rows"]


# ---------------------------------------------------------------------------
# 判据 ① · 族成员由产品规则现定，逐题 top-5 变化率表交得出来
# ---------------------------------------------------------------------------

def test_family_membership_is_the_products_own_rule(summary, rows):
    assert [row["id"] for row in rows] == FAMILY_IDS
    assert summary["family_questions"] == 15
    assert summary["fixture_rows"] == 105
    for row in rows:
        assert 1 <= row["n_expansions"] <= summary["synonym_max_queries"], row["id"]
        assert row["expansions"], row["id"]


def test_the_table_carries_a_per_question_rate(rows):
    for row in rows:
        for key in ("rate_primary", "rate_reverse", "entered_top5", "top5_off",
                    "top5_on", "rate_denominator"):
            assert key in row, f"{row['id']} 少了 {key} 这一格"
        assert len(row["top5_on"]) <= row["rate_denominator"], row["id"]


def test_the_one_moving_question_is_named_by_reading(rows):
    """词腿单腿口径下只有 metric-03 动了 top-5——它是唯一一枚原题召回短于 top_k 的族题。"""
    assert [row["id"] for row in rows if row["entered_top5"]] == ["metric-03"]
    moving = [row for row in rows if row["id"] == "metric-03"][0]
    assert moving["literal_recall_short"] is True
    assert moving["entered_top5"] == 1
    assert moving["rate_primary"] == pytest.approx(0.2)


def test_candidate_face_moves_even_where_top5_does_not(summary, rows):
    """候选面与 top-5 面是两个数：族题合计补回 137 枚新候选，而 top-5 只动 1 枚。

    这一格是判据 ① 的结构因由读数（生产 RRF 的名次取拼接后腿内的到达位置，
    词腿单腿时扩展腿只能排在原题之后），不是感想。
    """
    assert summary["total_new_candidates"] == 137
    assert summary["total_entered_top5"] == 1
    assert sum(row["new_candidates"] for row in rows) == 137
    assert summary["total_new_candidates_with_term"] == 41
    assert sum(row["new_candidates_with_term"] for row in rows) == 41


def test_the_noncriterion_direction_cell_reads_zero(summary, rows):
    """方向参考那一列读到 **0**：新进入 top-5 的块里没有整段答案的字面。

    🔴 这一格不许被读成「没改进」，也不许被读成「有改进」——它不是判据（乙案明令），
    它只把「命中改进的绝对量」钉成**未验**：本件连方向都没给出一枚正面证据。
    """
    assert summary["questions_with_answer_in_new_block"] == 0
    for row in rows:
        assert row["direction_hint_new_block_has_answer"] is False, row["id"]
        assert "must_contain" in row["direction_note"], row["id"]


def test_primary_is_the_lower_bound_and_reverse_the_upper_bound(rows, summary):
    for row in rows:
        assert row["entered_top5"] <= row["entered_top5_reverse"], row["id"]
        assert row["rate_primary"] <= row["rate_reverse"], row["id"]
    assert summary["mean_rate_primary"] <= summary["mean_rate_reverse"]
    assert summary["questions_with_nonzero_primary"] == 1
    assert summary["questions_with_nonzero_reverse"] == 15


def test_pinned_readings_on_this_base(summary):
    assert summary["mean_rate_primary"] == pytest.approx(0.2 / 15)
    assert summary["max_rate_primary"] == pytest.approx(0.2)
    assert summary["literal_recall_short"] == 1
    assert summary["blocked_in_full_tier"] == 15
    assert summary["recall_slots"] == 5


# ---------------------------------------------------------------------------
# 判据 ② 的前半 · 变化率的算术（分子＝新进入块数，分母＝top_k 枚）
# ---------------------------------------------------------------------------

def test_change_rate_is_new_blocks_over_top_k(gauge):
    assert gauge.top5_change_rate(0, 5) == 0.0
    assert gauge.top5_change_rate(1, 5) == pytest.approx(0.2)
    assert gauge.top5_change_rate(2, 5) == pytest.approx(0.4)
    assert gauge.top5_change_rate(5, 5) == 1.0
    with pytest.raises(AssertionError):
        gauge.top5_change_rate(1, 0)
    with pytest.raises(AssertionError):
        gauge.top5_change_rate(1, -5)


def test_every_row_reports_its_own_denominator(gauge, rows, summary):
    provenance = summary["top_k"]
    top_k = provenance["value"]
    assert top_k == provenance["pipeline_search_default"] == provenance["doc_leg_tool_value"]
    assert provenance["two_reads_agree"] is True
    for row in rows:
        assert row["rate_denominator"] == top_k, row["id"]
        assert row["rate_primary"] == gauge.top5_change_rate(row["entered_top5"], top_k)
        assert 0.0 <= row["rate_primary"] <= 1.0, row["id"]


def test_top_k_is_derived_from_two_places_not_hand_copied(gauge):
    read = gauge.read_top_k()
    assert read["doc_leg_carriers"] == ["search_docs"]
    assert read["two_reads_agree"] is True
    for entry in read["provenance"]:
        assert "::" in entry, entry
        assert not re.search(r"\.(py|md|jsonl|txt)\d", entry), entry


def test_expanded_queries_reach_the_recall_legs(rows, summary):
    """扩展词不是只进了账面：臂 B 真把它们送进召回腿，臂 A 只有原题那一条。"""
    for row in rows:
        assert row["queries_off"] == [row["question"]], row["id"]
        assert row["queries_on"][0] == row["question"], row["id"]
        assert set(row["expansions"]) <= set(row["queries_on"]), row["id"]
        assert 2 <= len(row["queries_on"]) <= summary["recall_slots"], row["id"]


# ---------------------------------------------------------------------------
# 判据 ③ · 改写仍走规则：不新增模型往返（运行时一枚 + 静态形状一枚）
# ---------------------------------------------------------------------------

def test_no_arm_of_the_measurement_returns_rewrite_text(rows, summary):
    """臂 B 交回的 rewrites 恒为空：fast 档不发改写，宽化全部来自规则腿。"""
    assert summary["model_roundtrips"] == 0
    for row in rows:
        assert row["returned_rewrites"] == [], row["id"]


def test_the_whole_measurement_pays_zero_model_roundtrips(summary):
    assert summary["model_roundtrips"] == 0
    assert summary["rewrite_tripwire_hits"] == 0
    assert summary["guard"]["blocked_socket_attempts"] == 0
    assert summary["catalog_pinned"] is True


def test_rule_leg_body_is_clean_of_model_and_network_calls():
    """``expand_query_synonyms`` 与它取词表的那枚 helper：函数体里不许出现模型面。"""
    tree = ast.parse((REPO_ROOT / PIPELINE_REL).read_bytes().decode("utf-8"))
    wanted = {"expand_query_synonyms", "_matched_definition"}
    bodies = [node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in bodies} == wanted, "产品把那两枚函数改名或摘掉了"
    banned = {"chat", "complete", "invoke", "requests", "urlopen", "ollama", "stream"}
    for node in bodies:
        attributes = {getattr(item, "attr", None) for item in ast.walk(node)
                      if isinstance(item, ast.Attribute)}
        called = {item.func.id for item in ast.walk(node)
                  if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)}
        assert "model" not in attributes, f"{node.name} 摸到了 model 面"
        assert not (attributes & banned), f"{node.name} 出现模型/网络出口：{attributes & banned}"
        assert not (called & banned), f"{node.name} 调了出站出口：{called & banned}"


def test_full_tier_blocks_the_rule_leg_so_it_cannot_add_any_roundtrip(rows, summary):
    """默认档（full）里模型改写正常返回时槽位排满 ⇒ 规则腿被挡在门外：15/15。

    这一格同时是判据 ②「不新增模型往返」的结构证明：规则腿只填模型**没花掉**的槽位，
    它自己一次往返都不发（运行时读数在 ``model_roundtrips`` 那格）。
    """
    assert summary["blocked_in_full_tier"] == len(rows) == 15
    for row in rows:
        assert row["blocked_in_full_tier"] is True, row["id"]


# ---------------------------------------------------------------------------
# 口径自证：乙案的裁决形状 + 离线承诺 + 落盘纪律
# ---------------------------------------------------------------------------

def test_caliber_is_top5_rate_and_not_must_contain(summary, rows):
    assert summary["criterion"] == "top5_change_rate"
    assert summary["must_contain_used"] is False
    assert "乙案" in summary["ruling"]
    assert summary["legs"] == "keyword-only"
    for row in rows:
        assert "非判据" in row["direction_note"], row["id"]
    assert summary["assembly"].startswith("生产 RetrievalPipeline.search 本体")


def test_offline_promises_are_carried_as_numbers(summary):
    assert summary["determinism"]["primary_rerun_identical"] is True
    assert summary["determinism"]["sampled"] == 15
    corpus = summary["corpus"]
    assert corpus["label"] == "local-rebuild"
    assert corpus["matches_production_index"] is False
    assert corpus["corpus_files"] == 95
    assert corpus["local_chunks"] == 318
    assert summary["sample"]["fixture"] == FIXTURE_REL.as_posix()


def test_the_evaluation_fixture_is_untouched_against_head():
    """乙案第一格：105 题夹具一字节不许动——对 HEAD 现读一次工作树差异。

    口径按行尾安全的那把尺走（本机 ``core.autocrlf=true``，直接与 blob 比字节会把
    LF→CRLF 的换行差异读成「夹具被改」，那是假红）：``git diff --quiet`` 认 eol 规范化。
    """
    diff = subprocess.run(["git", "-C", str(REPO_ROOT), "diff", "--quiet", "HEAD", "--",
                           FIXTURE_REL.as_posix()], capture_output=True, text=True)
    assert diff.returncode == 0, diff.stdout + diff.stderr
    status = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--",
                             FIXTURE_REL.as_posix()], capture_output=True, text=True)
    assert status.stdout.strip() == "", status.stdout


def test_gauge_refuses_to_write_its_readout_inside_the_repo(gauge, tmp_path):
    inside = REPO_ROOT / "docs" / "testing" / "r676-should-not-exist.json"
    with pytest.raises(AssertionError):
        gauge.reject_inside_repo(inside)
    assert not inside.exists()
    outside = gauge.reject_inside_repo(tmp_path / "r676.json")
    assert str(outside).startswith(str(tmp_path))


def test_the_offline_guard_does_not_survive_the_gauge(r219, report):
    """量具换的是进程级 socket：跑完必须还原，否则同会话邻居集体假红（在册教训）。"""
    assert report["summary"]["guard"]["blocked_socket_attempts"] == 0
    assert socket.socket is r219._REAL_SOCKET_CLASS, repr(socket.socket)
    for name in r219._GUARD_ARMS:
        assert callable(getattr(socket, name)), f"{name} 在还原过程中被弄没了"
    with pytest.raises(OSError) as info:
        socket.create_connection(("127.0.0.1", 1), timeout=1)
    assert not isinstance(info.value, AssertionError), f"仍被闸门拦住：{info.value}"


def test_the_catalog_pin_is_restored_after_the_gauge(report):
    """出厂词表那一钉也只许活在测量期内：跑完 registry 必须回到产品自己的那枚函数。

    量具换的是 ``app.semantics.registry._database_available``（模块属性）。桩留在这儿，
    同会话之后每一枚读术语目录的用例都会拿到「永远没有库」的答复——那是把别人的
    现场改成自己的口径（与 R219 那枚闸门泄漏同族）。
    """
    from app.semantics import registry

    assert report["summary"]["catalog_pinned"] is True
    assert getattr(registry._database_available, "__name__", "") == "_database_available", (
        "目录可用性这一钉没还原：现读 " + repr(registry._database_available))
    assert registry._database_available() in (True, False)


# ---------------------------------------------------------------------------
# 反证牙（判据 ② 点名的两枚形：分子分母对调 / 摘掉同义词腿）
# ---------------------------------------------------------------------------

def test_counter_evidence_swapping_numerator_and_denominator_goes_red(
        gauge, r219, monkeypatch, report):
    """把变化率的分子分母对调 ⇒ 红的必须是变化率那一格。

    施加＝``top5_change_rate`` 换成量具自带的 ``swapped_change_rate``（等价于命令行的
    ``--mutate swap-rate``）。metric-03 从 0.2 变成 5.0，越出 [0, 1]，``validate_report``
    当场点名那一行并炸；未施加的同一份报告退 None（正控）。同一突变下族成员、候选补回、
    闸门枚数全部照绿 —— 也就是说这道缺陷只能由变化率这一格拦，别格兜不住它。
    """
    gauge.validate_report(report)
    monkeypatch.setattr(gauge, "top5_change_rate", gauge.swapped_change_rate)
    mutated = gauge.measure(r219)
    moving = [row for row in mutated["rows"] if row["entered_top5"]][0]
    assert moving["rate_primary"] == pytest.approx(5.0)
    assert mutated["summary"]["max_rate_primary"] != report["summary"]["max_rate_primary"]
    with pytest.raises(AssertionError) as info:
        gauge.validate_report(mutated)
    assert "越出" in str(info.value)
    assert moving["id"] in str(info.value)
    assert mutated["summary"]["family_questions"] == 15
    assert mutated["summary"]["total_new_candidates"] == 137
    assert mutated["summary"]["guard"]["blocked_socket_attempts"] == 0


def test_counter_evidence_dropping_the_synonym_leg_goes_red(gauge, r219, report):
    """摘掉同义词腿 ⇒ 族为空：判据 ① 那张表当场一行都交不出来，量具自己判红。

    施加＝``mutate="drop-leg"``（把 ``expand_query_synonyms`` 换成恒回空，臂与账面一起断）。
    红在族数与「至少一枚题动了 top-5」这两格；未施加的正控仍读到 15 枚与 1 枚。
    """
    mutated = gauge.measure(r219, mutate="drop-leg")
    assert mutated["rows"] == []
    assert mutated["summary"]["family_questions"] == 0
    assert mutated["summary"]["total_entered_top5"] == 0
    assert mutated["summary"]["total_new_candidates"] == 0
    with pytest.raises(AssertionError) as info:
        gauge.validate_report(mutated)
    assert "族为空" in str(info.value)
    assert report["summary"]["family_questions"] == 15
    assert report["summary"]["questions_with_nonzero_primary"] == 1


def test_counter_evidence_a_tampered_row_is_caught_by_the_ruler(gauge, report):
    """账面自证不是装饰：把某行的新进入数抬过 top_k，validate 点名那一行并炸。"""
    tampered = {"summary": dict(report["summary"]),
                "rows": [dict(row) for row in report["rows"]]}
    tampered["rows"][0]["entered_top5"] = 9
    with pytest.raises(AssertionError) as info:
        gauge.validate_report(tampered)
    assert tampered["rows"][0]["id"] in str(info.value)



# ---------------------------------------------------------------------------
# CLI 的落盘分支（--out）：这条分支曾经是死枝，旧的牙只测 reject_inside_repo 没走它
# ---------------------------------------------------------------------------


def test_resolve_out_path_expands_env_and_home_forms(gauge):
    """`--out` 的参数字符串先展环境变元与 `~`，否则 %TEMP% 会落成一枚相对的怪路径。"""
    expanded = gauge.resolve_out_path("%TEMP%/evalrun/r676/r676.json")
    assert "%" not in str(expanded), f"环境变元没展开：{expanded}"
    assert expanded.is_absolute(), expanded
    temp_root = str(Path(os.environ["TEMP"]))
    assert str(expanded).lower().startswith(temp_root.lower()), (expanded, temp_root)
    home = gauge.resolve_out_path("~/r676.json")
    assert home.is_absolute() and str(home.parent) == str(Path.home()), home


def test_the_out_branch_writes_the_readout_outside_the_repo(gauge, report, tmp_path, monkeypatch):
    """走 CLI 本体：`--out` 真落盘且 JSON 可回读，仓内那一格仍被拒（判据 ① 的交付面）。"""
    monkeypatch.setattr(gauge, "measure", lambda *a, **k: report)
    out = tmp_path / "evalrun" / "r676.json"
    assert gauge.main(["--out", str(out), "--json", "--selfcheck"]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["family_questions"] == 15
    assert len(data["rows"]) == 15
    inside = REPO_ROOT / "docs" / "testing" / "r676-should-not-exist.json"
    with pytest.raises(AssertionError) as info:
        gauge.main(["--out", str(inside), "--json"])
    assert "仓内" in str(info.value)
    assert not inside.exists()
