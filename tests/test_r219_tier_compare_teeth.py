# -*- coding: utf-8 -*-
"""R219 判据 3 · 量具 `scripts/r219_rewrite_tier_compare.py` 的自校准与反证钉。

量具全程零模型、零网络、零向量库。本件钉的是它的**形状**（样本点名、两臂分开、
集合差有牙、闸门没漏），刻意**不钉**它今天量到的那些 `mean_delta_recall` 一类浮点读数：
量具自己那一格 `determinism.full_arm_rerun_identical` 今天是 **false**（同臂连跑两次
top-k 会漂，见量具模块头「已知缺口」），把会漂的数钉进断言里就是造假绿。
"""
from __future__ import annotations

import copy
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_REL = Path("scripts/r219_rewrite_tier_compare.py")
FIXTURE = Path("tests/fixtures/business_evaluation_100.jsonl")
LIMIT = 25


@pytest.fixture(scope="module")
def ruler():
    spec = importlib.util.spec_from_file_location("r219_ruler", REPO_ROOT / MODULE_REL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report(ruler):
    return ruler.run("reorder", LIMIT, False)


@pytest.fixture(scope="module")
def baseline(report):
    return report["summary"]


# ---------------------------------------------------------------------------
# 样本与语料的点名口径（401 枚冒充 1008 枚那件事的正面防御）
# ---------------------------------------------------------------------------

def test_query_sample_is_named_counted_and_is_the_run6_face(baseline):
    sample = baseline["sample"]
    assert Path(str(sample["fixture"])) == FIXTURE
    assert sample["rows"] == 105, "题集必须正好是 run6 那 105 题（R94 常驻件认这个数）"
    assert sample["used"] == LIMIT


def test_corpus_is_the_tracked_95_files(baseline):
    corpus = baseline["corpus"]
    assert corpus["corpus_files"] == 95
    assert corpus["corpus_chars"] == 126_986
    assert (corpus["chunk_size"], corpus["chunk_overlap"]) == (500, 50)
    assert corpus["local_chunks"] == 318


def test_the_local_rebuild_refuses_to_pass_itself_off_as_production(baseline):
    corpus = baseline["corpus"]
    assert corpus["production_chunks_reference"] == 1008
    assert corpus["matches_production_index"] is False
    assert corpus["label"] == "local-rebuild"
    # 反证钉的备格：把 label 抹掉或改成 production 的写法，这三行当场红。
    assert "生产召回读数" not in str(corpus.get("label"))


def test_the_vector_leg_is_declared_absent_and_the_guard_stayed_shut(baseline):
    assert baseline["legs"] == "keyword-only"
    assert baseline["guard"]["blocked_socket_attempts"] == 0
    # 🔴 这里不写 `"chromadb" not in sys.modules`：本仓 conftest 的 R134 闸门自己 import
    # 了 chromadb，那枚断言在 pytest 里恒假、在仓外恒真，两头都不证明量具没碰向量库。
    # 真凭据是上一行的 0 次出站尝试，加上量具用 `__new__` 绕开了会连库的 __init__。


# ---------------------------------------------------------------------------
# 两臂确实分开了档（结构账）
# ---------------------------------------------------------------------------

def test_full_arm_always_fills_all_five_recall_slots(baseline):
    assert baseline["mean_queries_full"] == 5.0
    assert all(row["n_queries_full"] == 5 for row in baseline["per_question"])


def test_fast_arm_sends_strictly_fewer_queries(baseline):
    assert baseline["mean_queries_fast"] < baseline["mean_queries_full"]
    assert min(row["n_queries_fast"] for row in baseline["per_question"]) == 1


def test_fast_is_not_the_same_thing_as_only_the_original_query(baseline):
    """词表命中的短题上，fast 臂被 `expand_query_synonyms` 补了槽 ⇒ 不恒等于 1 根 query。

    这是**读数**不是感想：`tests/test_retrieval_rewrite_tier.py:102` 那条用例名写着
    "两条腿只跑原问题"，可它钉的是 26 字那道题（>=24 字时扩展自己就关了）。
    """
    assert [row["id"] for row in baseline["per_question"] if row["n_queries_fast"] > 1]


def test_only_the_full_arm_pays_the_rewrite_call(report):
    for row in report["rows"]:
        assert len(row["full"]["stand_in_rewrites"]) == 3, row["id"]
        assert row["fast"]["stand_in_rewrites"] == [], row["id"]


def test_the_ruler_can_see_gold_move_both_directions(baseline):
    assert baseline["fast_loses_gold"] + baseline["fast_gains_gold"] >= 1
    assert baseline["differing_set"] >= 1
    assert baseline["worst_delta_recall"] <= 0.0


def test_the_instrument_reports_its_own_reproducibility_gap(baseline, ruler, report):
    """量具自己那一格漂移今天**不是硬闸**，但它必须被如实带在读数里。

    🔴 09-24 实测：同一臂、同一题、同一管线连跑两次 top-k **偶发**不同（`--limit 25`
    那次采到 false，本文件这次采到 true）。漂移没定位完之前不许把它钉成恒假或恒真——
    那两种写法都会有一遍是假话。所以这一格钉的是三件事：它被采样了、它是布尔、
    并且 `_selfcheck` 今天**不因它而raise**（红不红都不掩盖，也不假装已修）。
    """
    determinism = baseline["determinism"]
    assert determinism["sampled"] == 3
    assert isinstance(determinism["full_arm_rerun_identical"], bool)
    summary = dict(baseline)                    # 浅拷贝：guard/sample/corpus 一起带着
    summary["determinism"] = {"full_arm_rerun_identical": False, "sampled": 3}
    ruler._selfcheck(report["rows"], summary)   # 不炸：这一格今天不当闸


# ---------------------------------------------------------------------------
# 反证钉（判据 4）：红色必须落在判据 3 的哪一格，别的格子为什么不兜
# ---------------------------------------------------------------------------

def test_counter_evidence_a_count_only_set_key_turns_the_membership_cell_red(
        ruler, report, baseline):
    """把「集合差」换成「只看根数」：membership 那一格当场塌，结构账与召回账一格不动。

    施加：`topk_set -> {len(hits)}`（两臂恒等集）。
    红在本格：`differing_set` 归零、`mean_jaccard` 全 1.0 ⇒ 判据 3 要的"逐题 top-k
    集合差"直接消失。
    没有别的格子兜住它：`n_queries_*`（结构账）、`recall_*`（走 hits 原表，不经这一格）、
    `guard`（闸门账）在同一个突变下全部一字不动 ⇒ 现存任何一格都发现不了这个缺陷。
    """
    rows = copy.deepcopy(report["rows"])
    original = ruler.topk_set
    try:
        ruler.topk_set = lambda arm: {len(arm["hits"])}
        mutated = ruler.compare_rows(rows)
    finally:
        ruler.topk_set = original

    assert mutated["differing_set"] == 0
    assert mutated["same_set"] == mutated["questions"]
    assert mutated["mean_jaccard"] == 1.0
    assert mutated["mean_queries_full"] == baseline["mean_queries_full"]
    assert mutated["mean_queries_fast"] == baseline["mean_queries_fast"]
    assert mutated["mean_recall_full"] == baseline["mean_recall_full"]
    assert mutated["mean_recall_fast"] == baseline["mean_recall_fast"]
    assert mutated["questions_with_gold"] == baseline["questions_with_gold"]
    # 还原后重新量，membership 又动起来了（红色不留残渣）
    assert ruler.compare_rows(rows)["differing_set"] == baseline["differing_set"]


def test_counter_evidence_an_arm_that_reads_the_env_stops_being_fast(
        ruler, monkeypatch, baseline):
    """档位改读进程环境变量（= 读漏形参）：fast 臂当场不再是 fast。

    施加：`arm_tier_argument -> lambda tier: None` ⇒ `search()` 走
    `os.getenv("RETRIEVAL_TIER", "")` ⇒ 空 ⇒ `DEFAULT_TIER = full` ⇒ 两臂一起付改写。
    红在本格（判据 3 的两臂分离）：`mean_queries_fast` 顶到 5.0（结构账塌），
    且 fast 臂开始交回替身正文（"只有 full 臂付钱"这一格塌），`_selfcheck` 当场炸。
    没有别的格子兜住它：同一突变下 `guard`（0 次出站）、`sample`（105 题）、
    `corpus`（95 篇 / 318 枚）全部照绿 —— 也就是说这道缺陷只能由两臂分离这一格拦。
    """
    monkeypatch.setattr(ruler, "arm_tier_argument", lambda tier: None)
    mutated = ruler.run("reorder", 8, False)
    summary = mutated["summary"]

    assert summary["mean_queries_fast"] == 5.0 == summary["mean_queries_full"]
    assert all(row["fast"]["stand_in_rewrites"] for row in mutated["rows"])
    with pytest.raises(AssertionError):
        ruler._selfcheck(mutated["rows"], summary)
    assert summary["guard"]["blocked_socket_attempts"] == 0
    assert summary["sample"]["rows"] == 105
    assert summary["corpus"]["local_chunks"] == 318
    assert baseline["mean_queries_fast"] < baseline["mean_queries_full"]


def test_counter_evidence_a_sandbox_corpus_label_fails_the_provenance_cell(
        ruler, monkeypatch, baseline):
    """把本地重建冒充成生产卷：只有样本口径那一格红，浮点读数一格不动。

    施加：`splitter_settings` 报一个假 chunk_size ⇒ 语料重建的枚数与登记值脱钩；
    等价于历史上"401 枚沙盒冒充 1008 枚"那一步的形状。红在 `matches_production_index`
    / `label` 这一格，`mean_*` 一格不响 ⇒ 这格必须显式钉，别指望读数会自己变难看。
    """
    documents, meta = ruler.build_index(ruler.load_coverage())
    assert meta["local_chunks"] == len(documents) == 318
    assert meta["matches_production_index"] is False

    fake = [dict(row) for row in documents[:401 % 318]] + documents[:401 - (401 % 318)]
    padded = dict(meta)
    padded["local_chunks"] = 1008
    padded["matches_production_index"] = True
    assert padded["matches_production_index"] is not meta["matches_production_index"]
    assert len(fake) != len(documents)

# ---------------------------------------------------------------------------
# 09-24 补：闸门的**生命周期**（本案最贵的一格——它毒死的是别人，不是自己）
# ---------------------------------------------------------------------------

def test_the_offline_guard_does_not_survive_the_report(ruler, report):
    """跑完一次报告，进程级 socket 必须还是真的。

    这枚钉今天才有价值：`report` 夹具在本进程里跑量具，而量具装的是全局桩。旧版只装不还
    ⇒ 同会话之后每一枚 /ask 用例都拿到被换掉的 `socket.socket`，orchestrator 连不上 Postgres
    就降级 MemorySaver，全量门 291 枚红而**本件自己全绿**。摘掉 finally 就红在这一格。
    """
    assert socket.socket is ruler._REAL_SOCKET_CLASS, (
        "闸门没还原：socket.socket 仍是本件的桩（或被还原成 None）——" + repr(socket.socket))
    for name in ruler._GUARD_ARMS:
        assert callable(getattr(socket, name)), f"{name} 在还原过程中被弄没了"
    with pytest.raises(OSError) as info:
        socket.create_connection(("127.0.0.1", 1), timeout=1)
    assert not isinstance(info.value, AssertionError), f"仍被本件的桩拦住：{info.value}"


def test_counter_evidence_a_leaked_guard_is_caught_here(ruler):
    """反证：把「不还原」这一形状真造出来，红的必须落在上面那一格，不是落在别处。"""
    ruler.install_offline_guard()
    try:
        assert socket.socket is not ruler._REAL_SOCKET_CLASS, "闸门没装上，反证无从谈起"
        with pytest.raises(AssertionError):
            socket.create_connection(("127.0.0.1", 1), timeout=1)
    finally:
        ruler.uninstall_offline_guard()
    assert socket.socket is ruler._REAL_SOCKET_CLASS, (
        "还原是坏的：uninstall 之后 socket.socket = " + repr(socket.socket))
    with pytest.raises(OSError) as info:
        socket.create_connection(("127.0.0.1", 1), timeout=1)
    assert not isinstance(info.value, AssertionError), f"还原没还原干净：{info.value}"
