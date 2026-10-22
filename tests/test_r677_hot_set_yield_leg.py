"""R677 判据①：让路腿在位、可失败、而且承重。

现取符号名（判据只认这些，不认"应有让路机制"那句散文）：
`app/rag/hot_index.py::REASON_INCOMPLETE`、`::HotSetIndex._bypass_locked`、
`::HotSetIndex._could_be_recalled_locked`、`::HotSetIndex.populate`、
`::HotSetIndex.rank`、`::HotSetIndex.bypass_reason`、`::HotSetIndex._evict_locked`，
在册阈值 `::DEFAULT_MAX_CHUNKS` 与环境变量名 `::HOT_INDEX_MAX_CHUNKS_ENV`；非热集腿那一侧
`app/rag/retriever.py::DocumentRetriever._hot_hits` 与 `::DocumentRetriever.search`。

三条形状，全离线（不起窗、不打模型、不动容器、不连库）：

1. 预算装得下语料 ⇒ 热集自己答，一整批题一次都不回穿外部库，且答出来的名次与遗留引擎逐条
   同序同 id。判据 R44② 那半句"与 Chroma 结果一致性有测试"在这一枚里是热集腿对遗留腿的正面对照。
2. 占用打到在册阈值、语料落到冷表 ⇒ 每一问都被判"热集不能答"，`collection.query` 真的多了一枚
   调用（这一问确实走了非热集腿），结果与遗留腿逐条同序同 id。
3. 摘掉那圈冷表扫描 ⇒ 计数器必须动（misses 不再涨、hits 开始涨），而且答出来的结果集比遗留腿
   短——那正是热集模块开头禁止的「少了冷条目的近似结果集」。摘掉而计数不动，本文件当场红。

驱动件是 `scripts/r677_hot_set_yield.py`：本文件顺带钉它交付的坐标、在册阈值现取、承重结论，
以及它不许把离线形状当成重量（weight 一格恒为 NOT_MEASURED）。

embedding 桩在这里再写一遍：tests/ 没有 `__init__.py`，跨用例文件 import 不是本仓的既有写法
（R44 覆盖率那枚给的是同一条理由）。语料用词袋，词频互不相同 ⇒ 名次无并列；并列的名次没法当
判据，chroma 与热集对并列的破序规则不同源。
"""

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

REPO_ROOT = Path(__file__).resolve().parents[1]
GAUGE_PATH = REPO_ROOT / "scripts" / "r677_hot_set_yield.py"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"

#: 语料形状：每篇一段（短于分块窗口，切不到第二刀），词频互不相同。
DOC_COUNT = 4
TOP_K = 3
#: 预算打到一枚：冷表必然有货，这就是"占用达到在册阈值"的可失败形状。
CLIPPED_BUDGET = 1
#: 判据①点名的让路腿符号（现取自检，不许写在散文里）。
LEG_METHODS = ("_bypass_locked", "_could_be_recalled_locked", "populate", "rank",
               "bypass_reason", "_evict_locked")
#: 在册牙：这几枚件必须还在断言同一枚原因码（反假账第 6 条：牙只许增不许摘）。
REGISTERED_TEETH = ("tests/test_r44_hot_index_coverage.py",
                    "tests/test_r44_hot_index_unit.py",
                    "tests/test_r79_hot_index_defaults.py",
                    "tests/test_r79_hot_index_observability.py")


def _token_vector(text: str, dimension: int) -> list:
    """确定性词袋向量：同一枚 token 永远点亮同一维，一次模型都不打。"""
    vector = [0.0] * dimension
    for token in re.findall(r"\w+", str(text), flags=re.UNICODE):
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big")
        vector[digest % dimension] += 1.0
    if not any(vector):
        vector[0] = 1.0
    return vector


def _corpus() -> list:
    return [(f"r677_doc{index}.txt",
             f"probe unique{index} " + "common " * (index + 1))
            for index in range(DOC_COUNT)]


def _questions() -> list:
    return [f"probe unique{index} " + "common " * 6 for index in range(DOC_COUNT)]


def _keys(hits: list) -> list:
    return [(hit["source"], hit["chunk_index"]) for hit in hits]


def _never_recalled(_self, metadata, where, pred) -> bool:
    """摘腿模拟：把"冷条目会不会被召回"永远答成不会，等价于删掉那圈冷表扫描。"""
    return False


class _LegHarness:
    """真 chromadb + 词袋桩 + 两条腿各自的调用计数器。"""

    def __init__(self, tmp_path, monkeypatch):
        self.monkeypatch = monkeypatch
        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api",
                            lambda _self, text: _token_vector(
                                str(text), retriever_module.EMBEDDING_DIM))
        monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.external_queries = 0
        self.external_reads = 0
        target = self.retriever.collection
        real_get, real_query = target.get, target.query
        harness = self

        def get(*args, **kwargs):
            harness.external_reads += 1
            return real_get(*args, **kwargs)

        def query(*args, **kwargs):
            harness.external_queries += 1
            return real_query(*args, **kwargs)

        target.get, target.query = get, query

    def add(self, filename: str, content: str) -> None:
        self.retriever.add_document(filename, content, classification=1, department="")

    def use_budget(self, max_chunks: int) -> hi.HotSetIndex:
        """换一枚热集实例挂上进程单例：等价于"把常驻预算钉在这一格"。"""
        index = hi.HotSetIndex(max_chunks=max_chunks, roster_ttl_seconds=3600.0)
        self.monkeypatch.setattr(hi, "_HOT_INDEX", index)
        hi.reset_hot_index_diagnostics()
        return index

    def enable_hot(self) -> None:
        self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")

    def disable_hot(self) -> None:
        self.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)

    def ask(self, question: str, *, k: int = TOP_K) -> list:
        return self.retriever.search(question, k=k)

    def legacy_answers(self, questions: list, *, k: int = TOP_K) -> dict:
        """关热集问一遍：遗留引擎那一腿给的名次就是对照面。"""
        self.disable_hot()
        before = self.external_queries
        answers = {question: self.ask(question, k=k) for question in questions}
        assert self.external_queries - before == len(questions), "对照面本身没走外部库"
        return answers


@pytest.fixture(scope="module")
def harness(tmp_path_factory):
    monkeypatch = pytest.MonkeyPatch()
    probe = _LegHarness(tmp_path_factory.mktemp("r677yield"), monkeypatch)
    for name, content in _corpus():
        probe.add(name, content)
    yield probe
    monkeypatch.undo()


def _load_gauge():
    spec = importlib.util.spec_from_file_location("r677_hot_set_yield", GAUGE_PATH)
    assert spec and spec.loader, f"驱动件读不进来：{GAUGE_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- 在册阈值现取

def test_the_registered_threshold_is_a_live_number_not_a_copied_one(monkeypatch):
    """判据① 说的"在册阈值"必须现在就能取到：默认值、环境变量名、实例真正在用的那一份。"""
    monkeypatch.delenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, raising=False)
    assert hi.HotSetIndex().max_chunks == hi.DEFAULT_MAX_CHUNKS

    monkeypatch.setenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, str(CLIPPED_BUDGET))
    assert hi.HotSetIndex().max_chunks == CLIPPED_BUDGET

    monkeypatch.setenv(hi.HOT_INDEX_MAX_CHUNKS_ENV, "0")
    assert hi.HotSetIndex().max_chunks == hi.DEFAULT_MAX_CHUNKS, "非正数该回落在册默认值"


def test_the_leg_is_named_by_current_symbol_names_not_prose():
    """"让路腿"必须落在活的符号上：取不到就是没有，散文不算。"""
    for name in LEG_METHODS:
        assert callable(getattr(hi.HotSetIndex, name)), name
    assert isinstance(hi.REASON_INCOMPLETE, str) and hi.REASON_INCOMPLETE
    assert hi.HotSetIndex.__module__ == "app.rag.hot_index"


# ------------------------------------------------------- 形状 1：热集腿自己答

def test_the_hot_leg_answers_without_reading_the_external_library(harness):
    """预算装得下语料 ⇒ 一整批题一次都不回穿外部库；名次与遗留引擎逐条同序同 id。

    这一枚同时是判据 R44②"与 Chroma 结果一致性有测试"的那半句：对照面是 chroma 自己的
    l2 腿，不是本文件里的第二个实现。
    """
    questions = _questions()
    baseline = harness.legacy_answers(questions)
    index = harness.use_budget(hi.DEFAULT_MAX_CHUNKS)
    harness.enable_hot()
    before = hi.hot_index_diagnostics()
    external_before = harness.external_queries

    served = 0
    mismatches = []
    for question in questions:
        hits = harness.ask(question)
        if _keys(hits) != _keys(baseline[question]):
            mismatches.append((question, _keys(baseline[question]), _keys(hits)))
        served += 1

    after = hi.hot_index_diagnostics()
    assert index.cold_chunks == 0, "预算装得下却还有冷条目 ⇒ 这一枚测的不是热集答的形状"
    assert harness.external_queries == external_before, "热集答完一整批题，一次都不该回穿外部库"
    assert after["hits"] - before["hits"] == served
    assert after["misses"] == before["misses"]
    assert served == len(questions)
    assert mismatches == [], mismatches


# --------------------------------------------------- 形状 2：占用到阈值就让路

def test_occupancy_at_the_threshold_yields_cold_queries_to_the_external_leg(harness):
    """占用打到在册阈值、语料落到冷表 ⇒ 每问都判"热集不能答"，且真的多了一次外部库调用。"""
    questions = _questions()
    baseline = harness.legacy_answers(questions)
    index = harness.use_budget(CLIPPED_BUDGET)
    harness.enable_hot()
    before = hi.hot_index_diagnostics()
    external_before = harness.external_queries

    for question in questions:
        hits = harness.ask(question)
        assert _keys(hits) == _keys(baseline[question]), question

    after = hi.hot_index_diagnostics()
    assert index.resident_chunks == CLIPPED_BUDGET
    assert index.cold_chunks >= 1, "冷表空着就没有让路可言，这一枚测的是别的形状"
    assert harness.external_queries - external_before == len(questions), \
        "让路之后每一问都必须真的回穿非热集腿"
    assert after["misses"] - before["misses"] == len(questions)
    assert after["hits"] == before["hits"]
    assert after["last_bypass_reason"] == hi.REASON_INCOMPLETE


# ------------------------------------------------------- 形状 3：摘腿的反证

def test_removing_the_yield_leg_moves_the_counters_and_shortens_the_answer(harness, monkeypatch):
    """反证牙：把冷表扫描那圈摘掉，计数器必须动，而且给出来的结果集会比遗留腿短。

    计数不动 ⇒ 这条腿不承重（那才是真该红的形状）；结果集不短 ⇒ 让路腿 protecting 的东西
    没有测试钉着。两条都在这一枚里，缺一枚就退化成"看起来有牙"。
    """
    question = _questions()[0]
    baseline = harness.legacy_answers([question])
    index = harness.use_budget(CLIPPED_BUDGET)
    harness.enable_hot()

    before = hi.hot_index_diagnostics()
    with_leg = harness.ask(question)
    middle = hi.hot_index_diagnostics()
    assert middle["misses"] - before["misses"] == 1
    assert middle["hits"] == before["hits"]
    assert _keys(with_leg) == _keys(baseline[question])

    monkeypatch.setattr(hi.HotSetIndex, "_could_be_recalled_locked", _never_recalled)
    neutered = harness.ask(question)
    after = hi.hot_index_diagnostics()

    assert after["hits"] - middle["hits"] == 1, "摘掉让路腿而 hits 不动 ⇒ 这条腿不承重"
    assert after["misses"] == middle["misses"], "摘腿之后 misses 不该继续涨"
    assert after["last_bypass_reason"] == ""
    assert index.cold_chunks >= 1
    assert len(neutered) < len(baseline[question]), \
        "摘腿给出的就是「少了冷条目的近似结果集」，让路腿正是为它存在"


# ---------------------------------------------------------------- 驱动件那一枚

def test_the_gauge_drives_both_legs_offline_and_refuses_to_claim_weight():
    """让路驱动件在位：两条腿都能离线跑出来，承重结论由计数推出，重量一格恒为未验。"""
    gauge = _load_gauge()
    env_before = os.environ.get(hi.HOT_INDEX_ENV, "")
    payload = gauge.legs(hi)
    assert os.environ.get(hi.HOT_INDEX_ENV, "") == env_before, "驱动件不许把环境漏给进程"

    verdict = payload["verdict"]
    assert verdict["both_legs_ran"] is True
    assert verdict["yield_leg_load_bearing"] is True
    assert verdict["reason_code_that_carries_the_leg"] == hi.REASON_INCOMPLETE

    legs_block = payload["legs"]
    assert legs_block["hot_hit"]["served_by_hot_leg"] is True
    assert legs_block["hot_hit"]["external_leg_calls"] == 0
    assert legs_block["yield"]["served_by_hot_leg"] is False
    assert legs_block["yield"]["external_leg_calls"] == 1
    assert legs_block["yield"]["bypass_reason_after"] == hi.REASON_INCOMPLETE
    assert legs_block["yield_leg_removed"]["hits_delta"] == 1
    assert legs_block["yield_leg_removed"]["answer_matches_exact_oracle"] is False

    assert gauge.weight_block()["status"] == "NOT_MEASURED"
    assert gauge.not_proved(), "不说明本件不证明什么，读数就会被当成达"


def test_the_gauge_coordinates_are_symbol_shaped_and_resolve_now():
    """坐标全部现取派生：文件::符号，取不到符号就点名，且不出现行号形态。"""
    gauge = _load_gauge()
    found, missing = gauge.resolve_symbols(hi)
    assert missing == (), f"判据点名的符号取不到：{missing}"
    coordinates = gauge.symbol_coordinates(hi, found)
    assert len(coordinates) == len(gauge.LEG_SYMBOLS)
    for coordinate in coordinates:
        assert coordinate.startswith("app/rag/hot_index.py::"), coordinate
        assert not re.search(r"\.py:[0-9]", coordinate), coordinate


def test_the_gauge_fails_loudly_when_the_leg_stops_bearing_load():
    """驱动件自己的退出码可失败：承重结论没了就必须换码，不许一路返回 0。"""
    gauge = _load_gauge()
    legs_block = gauge.legs(hi)["legs"]
    reason = hi.REASON_INCOMPLETE

    assert gauge.verdict_for(legs_block, reason)["yield_leg_load_bearing"] is True
    assert gauge.exit_code_for(_payload(gauge, legs_block, reason)) == gauge.RC_OK

    dead = json.loads(json.dumps(legs_block))
    dead["yield_leg_removed"]["hits_delta"] = 0
    assert gauge.verdict_for(dead, reason)["yield_leg_load_bearing"] is False
    assert gauge.exit_code_for(_payload(gauge, dead, reason)) == gauge.RC_LEG_NOT_LOAD_BEARING

    silent = json.loads(json.dumps(legs_block))
    silent["yield"]["external_leg_calls"] = 0
    assert gauge.verdict_for(silent, reason)["both_legs_ran"] is False
    assert gauge.exit_code_for(_payload(gauge, silent, reason)) == gauge.RC_LEGS_NOT_RUN

    missing = _payload(gauge, legs_block, reason)
    missing["verdict"]["symbols_missing"] = ["HotSetIndex.rank"]
    assert gauge.exit_code_for(missing) == gauge.RC_SYMBOL_MISSING

    unread = _payload(gauge, legs_block, reason)
    unread["coverage"] = {"requested": True, "status": "NOT_MEASURED"}
    assert gauge.exit_code_for(unread) == gauge.RC_COVERAGE_UNREADABLE


def _payload(gauge, legs_block, reason) -> dict:
    return {"legs": legs_block, "verdict": gauge.verdict_for(legs_block, reason),
            "coverage": {"requested": False, "status": "NOT_MEASURED"}}


# ------------------------------------------------------------- 分母与在册牙

def test_the_coverage_denominator_is_the_registered_eval_set():
    """覆盖率那一格的分母必须是有名字的在册评测集，逐枚文件现读，不许拿账面旧数顶。"""
    gauge = _load_gauge()
    denominator = gauge.coverage_denominator()
    files = denominator["files"]
    assert files, "分母取不到就别谈覆盖率——这一枚必须红"
    total_rows = 0
    for name, rows in files.items():
        path = FIXTURE_ROOT / name
        assert path.is_file(), name
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert rows == len(lines), name
        total_rows += rows
    distinct = denominator["distinct_questions"]
    assert 0 < distinct <= total_rows
    assert distinct == len(_distinct_question_ids()), "去重口径与在册评测集不同源"


def _distinct_question_ids() -> set:
    ids = set()
    for path in sorted(FIXTURE_ROOT.glob("business_evaluation_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(str(json.loads(line)["id"]))
    return ids


def test_the_registered_teeth_still_read_the_yield_reason():
    """在册牙不许消失：这几枚件必须还在断言同一枚让路原因码（反假账第 6 条）。"""
    pattern = re.compile(r"assert[^\n]*REASON_INCOMPLETE")
    for relative in REGISTERED_TEETH:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert pattern.search(text), f"{relative} 里再没有断言让路原因码的行"
    coverage = (REPO_ROOT / "tests/test_r44_hot_index_coverage.py").read_text(encoding="utf-8")
    assert ("def test_coverage_drops_to_zero_when_the_budget_cannot_hold_the_corpus"
            in coverage), "那枚钉着「预算装不下就整体让路」的在册牙不见了"
