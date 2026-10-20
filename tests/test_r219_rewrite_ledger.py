# -*- coding: utf-8 -*-
"""R219 判据 1/2 · run6 查询改写发数账的钉子与反证。

全程离线：本件只读 `docs/testing/*run6*` 三本原件 + 用 ast 读 `app/rag/**` 源码文本，
**不 import `app.rag.retrieval_pipeline`**（那会在模块级建 `ModelHandler()`），
不 import `chromadb`，不开任何 socket。
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path("scripts/r219_rewrite_ledger.py")
R51_REL = Path("tests/test_r51_stage_latency.py")
PERF_REL = Path("docs/perf/latency-budget-2026-09-16.md")
FOLLOWUP_REL = Path("docs/handoff/2026-09-15-backend-followup-requests.md")


def load(name: str, relative: Path):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger():
    return load("r219_ledger", LEDGER_REL)


@pytest.fixture(scope="module")
def account(ledger):
    facts = ledger._tier_facts()
    rows = ledger.build_ledger(ledger.load_run6(), facts)
    return {"facts": facts, "rows": rows, "summary": ledger.summarize(rows)}


# ---------------------------------------------------------------------------
# 判据 1：账目本身
# ---------------------------------------------------------------------------

def test_the_three_run6_originals_close_over_the_same_105_ids(ledger):
    run6 = ledger.load_run6()
    assert len(run6["plans"]) == len(run6["answers"]) == len(run6["sidecar"]) == 105
    assert set(run6["plans"]) == set(run6["answers"]) == set(run6["sidecar"])


def test_leg_shape_of_the_face(account):
    """78 题计划里有 doc 腿、63 题留下检索引证、42 题零引证——三格各是各的数。"""
    summary = account["summary"]
    assert summary["doc_leg_planned"] == 78
    assert summary["questions_with_proven_rewrite"] == 63
    assert summary["questions_without_any_evidence"] == 42
    # 计划面 != 现网面：4 题计划无 doc 腿却留了 doc 引证，15 题有计划没留引证。
    assert summary["doc_leg_planned"] != summary["questions_with_proven_rewrite"]


def test_rewrite_call_lower_bound_is_auditable(ledger, account):
    """发数 = Σ ceil(doc 引证行数 / top_k) × 该题 attempt 数，逐题可复算。"""
    rows = account["rows"]
    recomputed = sum(row["rewrite_calls_proven"] for row in rows)
    with_retries = sum(row["rewrite_calls_all_attempts"] for row in rows)
    assert recomputed == account["summary"]["rewrite_calls_lower_bound"] == 79
    assert with_retries == account["summary"]["rewrite_calls_with_retries"] == 83
    assert account["summary"]["retry_extra_calls"] == 4
    assert account["summary"]["attempts_total"] == 109
    for row in rows:
        expected = (row["rewrite_calls_proven"] * row["attempts"])
        assert row["rewrite_calls_all_attempts"] == expected, row["id"]


def test_every_proven_call_carries_its_own_evidence(account):
    """没有引证的题一律记 0 发：账不许靠"计划里该有"来加水。"""
    for row in account["rows"]:
        if row["doc_evidence_rows"] == row["approval_evidence_rows"] == 0:
            assert row["rewrite_calls_proven"] == 0, row["id"]
        else:
            assert row["rewrite_calls_proven"] >= 1, row["id"]


def test_adaptive_ruler_never_fires_on_this_face(account):
    """adaptive 那把尺（>=24 字 或 >=2 枚子句分隔符）在 run6 题面上的实际效果。"""
    summary = account["summary"]
    lengths = [row["question_chars"] for row in account["rows"]]
    assert max(lengths) == summary["question_chars_max"] == 20
    assert summary["question_chars_ge_24"] == 0          # 长度这把尺一题都不碰
    assert summary["adaptive_still_pays"] == 9            # 全靠子句分隔符那一把
    assert summary["adaptive_would_skip"] == 96


# ---------------------------------------------------------------------------
# 判据 1 后半：41.581 s 过期，必须点名订正
# ---------------------------------------------------------------------------

def test_the_stale_price_is_still_written_in_r51_and_we_name_it():
    lines = R51_REL.read_bytes().decode("utf-8").split("\n")
    assert any("41.581" in line for line in lines[:60]), "R51 参考表那一行搬家了，订正要重写"
    perf = PERF_REL.read_bytes().decode("utf-8").split("\n")
    row = next(line for line in perf if "41.581" in line and "多路查询改写" in line)
    assert "116" in row, "09-16 那一行自带 prompt token=116，前提是可查的"


def test_the_correction_cites_a_real_machine_reading(account, ledger):
    """新价 4.08 s 出自身带 token 数的现网 native 日志，且出处文字确实在跟进单里。"""
    assert ledger.REWRITE_SECONDS_PER_CALL == 4.08
    followup = FOLLOWUP_REL.read_bytes().decode("utf-8").split("\n")
    lines = [line for line in followup if "seconds=4.08" in line and "eval_count=115" in line]
    assert lines, "跟进单里那行现网日志不见了，定价出处需重找"
    assert any("就是一发查询改写" in line or "是一发查询改写" in line for line in lines), \
        "R101 的归因文字（那 4.08 s 属于改写而非答题）不在册"


def test_the_account_priced_at_the_current_reading_not_the_stale_one(account, ledger):
    summary = account["summary"]
    calls = summary["rewrite_calls_with_retries"]
    assert summary["seconds_lower_bound"] == pytest.approx(calls * 4.08, abs=1e-6)
    assert summary["seconds_at_stale_price"] == pytest.approx(calls * 41.581, abs=1e-6)
    assert summary["price_ratio_stale_over_now"] == pytest.approx(41.581 / 4.08, rel=1e-9)
    assert summary["rewrite_share_of_run_pct"] < 10.0, "改写占整轮墙钟的比例是量具的结论主体"


# ---------------------------------------------------------------------------
# 判据 2：档位取值域与"默认档在什么条件下不发"
# ---------------------------------------------------------------------------

def test_tier_domain_is_fail_closed_read_straight_off_the_source(account):
    constants = account["facts"]["constants"]
    assert constants["TIER_ENV"] == "RETRIEVAL_TIER"
    assert constants["REWRITE_TIERS"] == ("fast", "adaptive", "full")
    assert constants["DEFAULT_TIER"] == "full"
    assert constants["TIER_ALIASES"] == {
        "off": "fast", "lean": "fast", "on": "full", "standard": "full", "default": "full"}
    facts = account["facts"]
    assert facts["resolve_reads_env"] is True
    assert facts["resolve_falls_back_to_default_twice"] is True   # 未设/空/拼错都回 full
    assert facts["fast_is_the_only_false"] is True                 # 唯一不发的一格是 fast
    assert facts["adaptive_delegates_to_rule"] is True
    assert facts["everything_else_returns_true"] is True
    assert facts["clause_separators_match"] is True


def test_the_recall_slot_cap_is_five_and_the_rewrite_out_grows_past_it(account):
    """结构账：full 一发改写交回 3+2~3 枚，`MAX_RECALL_QUERIES=5` 必定截掉 sub_questions。"""
    constants = account["facts"]["constants"]
    assert constants["MAX_RECALL_QUERIES"] == 5
    # 1 枚原题 + 3 枚 rewrites + 2 枚 sub_questions = 6 > 5 ⇒ 至少 1 枚子问题进不了召回。
    assert 1 + 3 + 2 > constants["MAX_RECALL_QUERIES"]
    assert constants["SYNONYM_EXPANSION_MAX_QUERY_CHARS"] == \
        constants["ADAPTIVE_REWRITE_MIN_CHARS"] == 24


def test_the_ledger_reads_source_text_and_never_imports_the_read_path(account):
    """账本靠 ast 读源码文本，不 import 检索链本体（import 就会在模块级建 ModelHandler）。

    🔴 这里**不**拿 `"chromadb" not in sys.modules` 当钉：本仓 `tests/conftest.py` 的
    R134 写回闸门自己 import 了 chromadb，那枚断言在 pytest 里恒假、在仓外恒真，
    两头都不证明本件没碰向量库。真正的凭据是上面那一行读数：`blocked connect attempts
    to host model port: 0`，加上账本从头到尾只 open 过 4 个仓内文本文件。
    """
    # 🔴 不写 `"app.rag.retrieval_pipeline" not in sys.modules`：同一 pytest 进程里
    # 判据 3 那枚件会 import 检索链本体，这条断言会不会红取决于**同批跑了谁**，
    # 不取决于本件做没做（`--dist loadfile` 下两枚件还可能落到同一个 worker）。
    # 凭据只留能归给本件的那一条：它的源码里没有任何一条通往向量库或模型的路径。
    # 🔴 不许写 `"app.rag.retriever" not in sys.modules`：本仓 conftest 的 R134 闸门自己
    # 把它 import 了，那枚断言与本件无关、恒假（红在别处）。
    assert ledger_sources_are_text_only()


def ledger_sources_are_text_only() -> bool:
    """账本读的四件东西全是文本：三本 run6 原件 + 一枚 ast 读的源码。"""
    text = (REPO_ROOT / LEDGER_REL).read_bytes().decode("utf-8")
    banned = ("import chromadb", "PersistentClient", "chromadb.", "get_collection",
              "httpx", "requests.", "socket.", "app.rag.retrieval_pipeline")
    return "read_bytes()" in text and not any(banned_line in text for banned_line in banned)


# ---------------------------------------------------------------------------
# 反证钉（判据 4）：红色必须落在本格，且证明没有别的格子顺手兜住它
# ---------------------------------------------------------------------------

def test_counter_evidence_quoting_the_stale_price_turns_only_the_money_cell_red(
        ledger, account, monkeypatch):
    """把定价换回 41.581：只有钱那格变红，发数与腿形一格都不动。

    这就是"红在本格"：如果账目里还有第二格能兜住过期定价，它今天就不必靠这一枚钉。
    """
    facts = account["facts"]
    before = ledger.summarize(account["rows"])
    monkeypatch.setattr(ledger, "REWRITE_SECONDS_PER_CALL", 41.581)
    after = ledger.summarize(ledger.build_ledger(ledger.load_run6(), facts))

    # 本格：钱算错了，且错到 10 倍。
    assert after["seconds_lower_bound"] != before["seconds_lower_bound"]
    assert after["seconds_lower_bound"] == pytest.approx(before["seconds_at_stale_price"])
    assert after["rewrite_share_of_run_pct"] > 60.0
    # 别的格子一格没动 ⇒ 没有任何既存判据会顺手把过期定价拦下来。
    for key in ("rewrite_calls_lower_bound", "rewrite_calls_with_retries",
                "doc_leg_planned", "questions_with_proven_rewrite", "attempts_total",
                "adaptive_still_pays", "wall_p95_ms", "wall_median_ms"):
        assert after[key] == before[key], key
    # 而账本自己那枚判据（现价 × 发数）当场不成立 ⇒ 这一格确实是活的判据不是装饰。
    calls = before["rewrite_calls_with_retries"]
    assert after["seconds_lower_bound"] != pytest.approx(calls * 4.08, abs=1e-6)


def test_counter_evidence_ignoring_the_retry_column_loses_four_calls(ledger, account,
                                                                    monkeypatch):
    """把 attempt 乘子摘掉：合计发数从 83 掉回 79，而逐题下界与腿形照旧绿。

    红在「重试也要付钱」这一格；`rewrite_calls_lower_bound`（另一格）不会替它兜。
    """
    rows = copy.deepcopy(account["rows"])
    before = ledger.summarize(copy.deepcopy(account["rows"]))
    for row in rows:
        row["rewrite_calls_all_attempts"] = row["rewrite_calls_proven"]
    after = ledger.summarize(rows)

    assert after["rewrite_calls_with_retries"] == 79 != before["rewrite_calls_with_retries"]
    assert after["retry_extra_calls"] == 0 != before["retry_extra_calls"]
    assert after["seconds_lower_bound"] != before["seconds_lower_bound"]
    # 没被兜住的反面证明：其余格子全部一字不动。
    for key in ("rewrite_calls_lower_bound", "doc_leg_planned",
                "questions_with_proven_rewrite", "adaptive_still_pays", "wall_p95_ms"):
        assert after[key] == before[key], key


def test_counter_evidence_dropping_evidence_rows_to_counts_loses_the_second_leg(
        ledger, account, monkeypatch):
    """把 ceil(n/top_k) 换成"一条腿有引证就算一发"：79 掉到 66，腿形/题面一格不动。

    红在发数下界这一格（审批腿的 ceil(n/3) 与 >5 行的多腿题一起被抹平）；
    `questions_with_proven_rewrite`（"有几题付过钱"那一格）不会替它兜住这 13 发。
    """
    rows = copy.deepcopy(account["rows"])
    before = ledger.summarize(copy.deepcopy(account["rows"]))
    for row in rows:
        one_per_leg = (int(bool(row["doc_evidence_rows"]))
                       + int(bool(row["approval_evidence_rows"])))
        row["rewrite_calls_proven"] = one_per_leg
        row["rewrite_calls_all_attempts"] = one_per_leg * row["attempts"]
    after = ledger.summarize(rows)

    # 63 题有 doc 引证、另 3 题有审批引证 => 抹平 ceil() 之后是 66 发，比真下界少 13 发。
    assert after["rewrite_calls_lower_bound"] == 66
    assert after["rewrite_calls_with_retries"] == 70
    assert after["rewrite_calls_lower_bound"] != before["rewrite_calls_lower_bound"]
    for key in ("doc_leg_planned", "questions_with_proven_rewrite", "question_chars_max",
                "adaptive_still_pays", "wall_p95_ms"):
        assert after[key] == before[key], key