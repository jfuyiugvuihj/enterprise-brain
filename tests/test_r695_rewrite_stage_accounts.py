# -*- coding: utf-8 -*-
"""R695 常驻牙：rewrite 段第一次有**能指认、有主、不双记**的生产发点。

病形原文在 ``docs/tickets/R695-rewrite-stage-production-leg.md``：R688 落了 classify／generate／
reflect 三段的发点，rewrite 今天既无跨度也无身份 —— 两枚改写腿都拿不到本轮 config，而非流式的
``app/common/model_handler.py`` 一枚跨度都不发，直接给它发 ``stage_account`` 会撞「无主不记」
（写零字节＝静默失效，比没有更坏）。本件钉四格，每一格都可失败：

① 身份真送进去：两枚腿各自拿得到本轮的 owner＋trace；拿不到就一个字节都不落。
② 发点可指认：段名 → ``文件::符号`` 由 ``scripts/r636_stage_coverage.py::call_sites_of`` 与
   R688 自己那把 AST 尺各读一遍；retrieve 仍然不许被我顺手"做出"一枚发点。
③ 同区间只一把尺：非流式那一发今天没有任何跨度（AST 现读）；检索腿那一发落在
   ``app/agents/tools.py::search_docs`` 的工具跨度**之内**，在册算术按严格包含把它剔出加总，
   剔出去是「不多算第二次」而不是「没量到」—— p50／p95 那一面仍然看得见它。
④ 计时纪律：记账只读两枚时钟、append 一枚事件，答案字节一个都不许变。

🔴 「调用形状不破」是这条腿的前提：全档现读 31 枚测试替身（27 个文件）按 ``(session_id, message)`` 两枚元数替换
``app/api/v1/chat.py::_rewrite_followup``，把 config 加成第三枚实参就红
``tests/test_r149_sse_text_pieces.py``（判据④点名不许红的那枚）。所以 chat 腿的身份走
``app/trace/spans.py::arm_turn_identity`` 挂进执行上下文 —— 形状与 R536 在册的
``arm_retrieval_trace`` 同一款；形参照样加了，显式交 config 的调用方一律收。

🔴 而 ``QueryRewriter.rewrite`` 的签名本件**不动**，并把它钉死：R43a 的硬门
（``tests/test_r43a_rewrite_prefix_reuse.py::test_no_identity_can_reach_the_reusable_prefix``）
要求它只剩一枚 ``question``，那是「可复用前缀收不到身份」的结构证据。身份因此从调用侧进来，
跨度开在 ``RetrievalPipeline.search`` 那一发外面 —— 判据① 里"形参加在 rewrite 上"落成这样，
是这枚在册钉决定的，不是执行层省事；交回口径见 ``docs/testing/r695-2026-10-06.md``。
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1 import chat
from app.common import stage_timing
from app.common.model_handler import ModelHandler, ModelReply
from app.rag import retrieval_pipeline
from app.trace import spans

from test_r688_stage_accounts_are_landed import (
    _config,
    _principal,
    _redirected_journal,
    journal_lines,
    stage_accounts,
    stage_emit_points,
)
from test_r126_rewrite_prev_turn import FIRST_TURN, SECOND_TURN, install_ask_route

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"
STAGE_EVENT = "stage.finished"
REWRITE = "rewrite"

#: 两枚改写腿的宿主符号名：判据② 要能逐枚点名它们。
CHAT_LEG = "_rewrite_followup"
PIPELINE_LEG = "RetrievalPipeline.search"
CHAT_FILE = "app/api/v1/chat.py"
PIPELINE_FILE = "app/rag/retrieval_pipeline.py"

PREVIOUS_QUESTION = "2024年财务部门的预算是800万元。"
TRIGGER_QUESTION = "那个部门的预算占全年比例是多少？"
REWRITTEN_QUESTION = "2024年财务部门预算占全年预算的比例是多少？"

#: 跨度／记账的写入符号：判据③ 用它证「这条腿上今天没有第二把尺」。
METERS = ("start_model_call", "start_tool_call", "stage_account", "record_stage_event", "stage_window")

# ==================== 读数工具 ====================


def load_coverage_ruler():
    """按在册路子加载 R636 覆盖面尺（判据② 点名的就是它那枚 ``call_sites_of``）。"""
    path = REPO_ROOT / "scripts" / "r636_stage_coverage.py"
    spec = importlib.util.spec_from_file_location("r695_r636_ruler", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 需要能在 sys.modules 里找到本件，否则 exec 当场炸
    spec.loader.exec_module(module)
    return module


def rewrite_emit_sites(root: Path = APP_ROOT) -> list[str]:
    """派生的发点表里 rewrite 段的 ``文件::符号``；读不到两枚就点名「段 rewrite 缺发点」。"""
    sites = stage_emit_points(root).get(REWRITE) or []
    assert len(sites) >= 2, (
        "段 rewrite 的可指认发点=%d（应>=2），现读=%s ⇒ 这一段的账又没人发了"
        % (len(sites), sites))
    return sites


def rewrite_rows(journal: Path) -> list[dict]:
    """事件件里 rewrite 段的件；段名逐字对在册字面，不许由本件另认。"""
    return stage_accounts(journal_lines(journal)).get(REWRITE, [])


def rewrite_samples() -> list[stage_timing.StageSample]:
    return [sample for sample in stage_timing.default_stage_ledger().samples() if sample.stage == REWRITE]


def assert_rewrite_account_landed(journal: Path, *, expect: int = 1) -> list[dict]:
    """判据② 的可失败版本：没落地就点名「rewrite 段没主」，不许报一句整体失败。"""
    rows = rewrite_rows(journal)
    assert len(rows) == expect, (
        "段 rewrite 落进事件件的件数=%d（应=%d）：这一段没主 —— "
        "调用点把身份摘掉了（app/trace/spans.py::arm_turn_identity）" % (len(rows), expect))
    return rows


def _function(tree: ast.AST, name: str):
    return next((node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name), None)


def call_sites_inside(source: str, host: str, called: str) -> list[ast.Call]:
    """某枚函数体内对 ``called(...)`` 的调用点（判据① 的接线账走这条路）。"""
    target = _function(ast.parse(source), host)
    assert target is not None, "%s 读不到，接线判据就成了空气" % host
    hits = []
    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name == called:
            hits.append(node)
    return hits


def keyword_hands_over(call: ast.Call, keyword: str, *names: str) -> bool:
    """这枚调用的 ``keyword=`` 是否把那枚符号交了出去（含 ``符号(...)`` 的形状）。"""
    for item in call.keywords:
        if item.arg != keyword:
            continue
        node = item.value
        if isinstance(node, ast.Call):
            func = node.func
            root = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if root in names:
                return True
        while isinstance(node, ast.Attribute):
            node = node.value
        if isinstance(node, ast.Name) and node.id in names:
            return True
    return False


def chat_route_arms_the_leg(root: Path = REPO_ROOT) -> bool:
    """``chat.ask`` 是否在调用改写腿之前挂了本轮身份（判据① 的接线；摘掉就红）。"""
    source = (root / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")
    route = _function(ast.parse(source), "ask")
    assert route is not None, "读不到 ask 路由，接线判据就成了空气"
    arms = [node for node in ast.walk(route) if isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", "")) == "arm_turn_identity"]
    legs = [node for node in ast.walk(route) if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == CHAT_LEG]
    assert legs, "%s 不再由 ask 路由调用" % CHAT_LEG
    return bool(arms) and all(arm.lineno < leg.lineno for arm in arms for leg in legs)


def pipeline_call_site_hands_identity_down(root: Path = REPO_ROOT) -> bool:
    """``RetrievalPipeline.search_for_principal`` 是否把本轮 config 交给 ``search``。"""
    source = (root / "app" / "rag" / "retrieval_pipeline.py").read_text(encoding="utf-8")
    calls = call_sites_inside(source, "search_for_principal", "search")
    assert calls, "search_for_principal 不再调用 search"
    return any(keyword_hands_over(call, "config", "retrieval_turn_config") for call in calls)


def symbols_called_in(source: str, host: str) -> set:
    """某枚函数碰过的符号名（判据③ 用它证这条腿上没别的尺）。"""
    target = _function(ast.parse(source), host)
    assert target is not None, "%s 读不到" % host
    found = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            func = node.func
            found.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return {name for name in found if name}


# ==================== 桩：只盖外部件 ====================


@pytest.fixture
def stored_previous_turn(monkeypatch):
    """给改写腿一段真形状历史：上一问＋上一答，末尾不含本轮自己。"""
    monkeypatch.setattr(chat, "_get_session_messages", lambda _session_id: [
        {"role": "user", "content": PREVIOUS_QUESTION},
        {"role": "assistant", "content": "财务部门预算占全年 12%。"},
    ])


def stub_rewrite_model(monkeypatch) -> list[dict]:
    """把改写腿唯一的模型出口打成桩，并记下每一趟调用。"""
    seen: list[dict] = []

    def fake_chat(*args, **kwargs):  # 类目标桩：绑定的 self 与实参一律由位置吸收
        seen.append(kwargs)
        return ModelReply(REWRITTEN_QUESTION, finish_reason="stop")

    #: 桩打在**类目标**上（r516 的在册治法：进程级单例不许落方法桩，那枚账全仓量出来）。
    monkeypatch.setattr(ModelHandler, "chat", fake_chat)
    return seen


class RecordingRewriter:
    """检索腿的改写替身：只收一枚 ``question``，元数一枚都不许多（R43a 那枚门的形状）。"""

    def __init__(self):
        self.calls: list[str] = []

    def rewrite(self, question):
        self.calls.append(question)
        return {"rewrites": [question + "（改写）"], "sub_questions": []}


def bare_pipeline(rewriter) -> retrieval_pipeline.RetrievalPipeline:
    """绕开 ``__init__``（它会连 Chroma），保住真 ``search`` 的组装。"""
    pipeline = retrieval_pipeline.RetrievalPipeline.__new__(retrieval_pipeline.RetrievalPipeline)
    pipeline.semantic = SimpleNamespace(search=lambda query, k=8, where=None: [])
    pipeline.bm25 = SimpleNamespace(search=lambda query, k=8, pred=None: [])
    pipeline.reranker = SimpleNamespace(rerank=lambda query, docs, top_k=5: [])
    pipeline.rewriter = rewriter
    return pipeline

# ==================== 判据②：发点可指认 ====================


def test_the_rewrite_stage_has_two_named_production_emit_points():
    """段名 → ``文件::符号``：R688 那把尺与 R636 点名的 ``call_sites_of`` 各读一遍，两把都要有点。"""
    sites = rewrite_emit_sites()
    hosts = set()
    for site in sites:
        relative, sep, symbol = site.partition("::")
        assert sep and relative and symbol and not symbol.isdigit(), site
        assert (REPO_ROOT / relative).is_file(), site
        hosts.add(symbol)
    assert {CHAT_LEG, PIPELINE_LEG} <= hosts, hosts
    # 判据② 点名的那把尺（R636 的 call_sites_of）也要真读出这两枚发点。它给方法符号不带类前缀
    # （交回 retrieval_pipeline.py::search，而 R688 那把交回 RetrievalPipeline.search），所以这里
    # 比的是「同一枚文件里确有这枚调用点」；两把尺的符号拼法分叉记进交付纸，不由本件抹平。
    ruler_sites = load_coverage_ruler().call_sites_of("stage_account", APP_ROOT)
    ruler_files = {site.partition("::")[0] for site in ruler_sites}
    assert {CHAT_FILE, PIPELINE_FILE} <= ruler_files, ruler_sites
    assert len(ruler_sites) >= 3, ruler_sites


def test_the_retrieve_stage_still_has_no_emit_point_of_its_own():
    """本单不许顺手"做出"retrieve：那是 R696 甲案的格子，越界就是双记的起点。"""
    assert REWRITE in stage_emit_points()
    assert not (stage_emit_points().get("retrieve") or []), stage_emit_points().get("retrieve")


# ==================== 判据①：身份真送进去（接线） ====================


def test_the_chat_route_arms_the_identity_before_it_calls_the_leg():
    assert chat_route_arms_the_leg(), (
        "ask 路由不再把本轮身份交给改写腿：段 rewrite 会退回「没主」，"
        "发点落不了一枚字节（app/trace/spans.py::arm_turn_identity）")


def test_the_rewrite_call_keeps_todays_two_argument_shape():
    """判据① 的后半句「缺省值必须保持今天的调用形状不破」：调用点仍是两枚实参、零关键词。"""
    source = (REPO_ROOT / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")
    calls = call_sites_inside(source, "ask", CHAT_LEG)
    assert len(calls) == 1, calls
    call = calls[0]
    assert len(call.args) == 2 and not call.keywords, ast.dump(call)


def test_the_query_rewriter_still_takes_no_identity():
    """R43a 的结构证据不许被我拆掉：``QueryRewriter.rewrite`` 仍然只收一枚 ``question``。"""
    parameters = list(inspect.signature(retrieval_pipeline.QueryRewriter.rewrite).parameters)
    assert parameters == ["question"], parameters


def test_the_followup_takes_an_optional_config():
    """形参加了且可选：默认值不破今天的调用形状（判据① 的字面半边）。"""
    signature = inspect.signature(chat._rewrite_followup)
    parameters = signature.parameters
    assert list(parameters) == ["session_id", "user_msg", "config"], list(parameters)
    assert parameters["config"].default is None, parameters["config"]


# ==================== 判据①＋④：chat 腿的两条落件路 ====================


def test_the_followup_leg_lands_one_rewrite_account_from_an_explicit_config(
        tmp_path, monkeypatch, stored_previous_turn):
    seen = stub_rewrite_model(monkeypatch)
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        answer = chat._rewrite_followup("r695-explicit", TRIGGER_QUESTION, config=_config())
        rows = assert_rewrite_account_landed(journal)
        samples = rewrite_samples()
    assert answer == REWRITTEN_QUESTION
    assert len(seen) == 1, seen
    payload = rows[0]["payload"]
    assert payload["stage"] == REWRITE
    assert payload["model_tier"] == REWRITE
    assert payload["record_kind"] == "stage_windows"
    assert payload["status"] == "completed"
    assert payload["owner_id"], payload
    assert payload["started_at"] and payload["completed_at"]
    assert isinstance(payload["duration_ms"], int) and payload["duration_ms"] >= 0
    assert [sample.tier for sample in samples] == [REWRITE], samples


def test_the_followup_leg_reads_the_identity_the_route_armed(tmp_path, monkeypatch, stored_previous_turn):
    """生产形状：调用点两枚实参都不多，身份由 ``arm_turn_identity`` 挂在执行上下文里。"""
    stub_rewrite_model(monkeypatch)
    token = spans.arm_turn_identity(_config())
    assert token is not None, "带主带 trace 的 config 应当挂得进去"
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        try:
            answer = chat._rewrite_followup("r695-armed", TRIGGER_QUESTION)
        finally:
            spans.reset_turn_identity(token)
        rows = assert_rewrite_account_landed(journal)
    assert answer == REWRITTEN_QUESTION
    assert rows[0]["payload"]["owner_id"]


def test_an_unarmed_followup_leg_lands_no_bytes(tmp_path, monkeypatch, stored_previous_turn):
    """「无主不记」不许被本单放宽：没身份 ⇒ 事件与样本双零，宁缺毋假。"""
    seen = stub_rewrite_model(monkeypatch)
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        answer = chat._rewrite_followup("r695-anon", TRIGGER_QUESTION)
        assert rewrite_rows(journal) == []
        assert rewrite_samples() == []
    assert answer == REWRITTEN_QUESTION and len(seen) == 1


def test_the_real_ask_route_lands_a_rewrite_account_for_the_round(tmp_path, monkeypatch):
    """走真路由（真存读＋真改写腿，模型是桩）：第一轮没上一问⇒零枚，第二轮⇒一枚。"""
    ask_once, prompts, _graph = install_ask_route(monkeypatch, tmp_path)
    session_id = "r695-route-" + uuid4().hex
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        ask_once(FIRST_TURN, session_id)
        assert prompts == [] and rewrite_rows(journal) == []
        ask_once(SECOND_TURN, session_id)
        rows = assert_rewrite_account_landed(journal)
    assert len(prompts) == 1, prompts
    assert rows[0]["payload"]["stage"] == REWRITE
    assert rows[0]["payload"]["owner_id"], rows[0]["payload"]


# ==================== 判据①＋②：检索腿 ====================


def test_the_retrieval_leg_lands_a_rewrite_account_for_the_round(tmp_path, monkeypatch):
    rewriter = RecordingRewriter()
    pipeline = bare_pipeline(rewriter)
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        _docs, rewrites = pipeline.search(REWRITTEN_QUESTION, top_k=2,
                                          tier=retrieval_pipeline.TIER_FULL, config=_config())
        rows = assert_rewrite_account_landed(journal)
    assert rewrites and len(rewriter.calls) == 1, rewriter.calls
    assert rows[0]["payload"]["model_tier"] == REWRITE
    assert rows[0]["payload"]["record_kind"] == "stage_windows"


def test_the_retrieval_leg_is_silent_when_no_round_is_known(tmp_path, monkeypatch):
    rewriter = RecordingRewriter()
    pipeline = bare_pipeline(rewriter)
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        pipeline.search(REWRITTEN_QUESTION, top_k=2, tier=retrieval_pipeline.TIER_FULL)
        assert rewrite_rows(journal) == []
    assert len(rewriter.calls) == 1, "改写照跑：本单只观察，不改召回"


def test_search_for_principal_hands_the_round_identity_down(tmp_path, monkeypatch):
    """判据① 的调用点：``search_for_principal`` 把 principal＋在册那三个 id 一起交下去。"""
    captured: dict = {}
    pipeline = retrieval_pipeline.RetrievalPipeline.__new__(retrieval_pipeline.RetrievalPipeline)

    def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return [], []

    pipeline.search = fake_search
    token = retrieval_pipeline.arm_retrieval_trace(
        trace_id="trace-r695-wire", request_id="req-r695-wire", task_id="task-r695-wire")
    assert token is not None
    with _redirected_journal(tmp_path, monkeypatch):
        try:
            pipeline.search_for_principal(REWRITTEN_QUESTION, _principal(), top_k=3)
        finally:
            retrieval_pipeline.reset_retrieval_trace(token)
    config = captured["config"]
    assert config["configurable"]["trace_id"] == "trace-r695-wire", config
    assert config["configurable"]["request_id"] == "req-r695-wire", config
    assert config["configurable"]["principal"].user_id, config


def test_retrieval_turn_config_refuses_an_anonymous_round():
    """没挂问答身份、或没有主体，都交回 ``None``：这一段宁可不发，也不许挂到编出来的主上。"""
    assert retrieval_pipeline.retrieval_turn_config(_principal()) is None
    token = retrieval_pipeline.arm_retrieval_trace(trace_id="trace-r695-refuse", request_id="req-r695-refuse")
    try:
        assert retrieval_pipeline.retrieval_turn_config(None) is None
        config = retrieval_pipeline.retrieval_turn_config(_principal())
        assert config["configurable"]["trace_id"] == "trace-r695-refuse", config
    finally:
        retrieval_pipeline.reset_retrieval_trace(token)


# ==================== 判据③：同区间只一把尺 ====================


def test_the_non_streaming_model_leg_carries_no_other_meter():
    """非流式那一发今天没有任何跨度：rewrite 的发点不构成双记（病形那一句的现读凭据）。"""
    usage = load_coverage_ruler().module_uses_symbols(
        "app/common/model_handler.py", METERS, repo=REPO_ROOT)
    assert not any(usage.values()), usage
    source = (REPO_ROOT / "app" / "common" / "model_handler.py").read_text(encoding="utf-8")
    called = symbols_called_in(source, "chat")
    assert not (called & set(METERS)), sorted(called & set(METERS))


def test_a_nested_rewrite_sample_is_excluded_from_the_sum_not_billed_twice():
    """检索腿那一发嵌在 search_docs 工具跨度里：在册算术剔它出加总，但 p50/p95 仍量得到它。"""
    origin = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

    def stamp(ms: float) -> str:
        return (origin + timedelta(milliseconds=ms)).isoformat()

    retrieve = stage_timing.StageSample(stage="retrieve", duration_ms=1000.0, trace_id="trace-r695",
                                        source="tool_span", started_at=stamp(0), completed_at=stamp(1000))
    rewrite = stage_timing.StageSample(stage=REWRITE, duration_ms=400.0, trace_id="trace-r695", tier=REWRITE,
                                       source="stage_windows", started_at=stamp(100), completed_at=stamp(500))
    generate = stage_timing.StageSample(stage="generate", duration_ms=600.0, trace_id="trace-r695",
                                        source="model_span", started_at=stamp(1000), completed_at=stamp(1600))
    report = stage_timing.aggregate_stage_latency([retrieve, rewrite, generate], end_to_end_ms=1600.0)

    cell = report["stages"][REWRITE]
    assert cell["count"] == 1, cell
    assert cell["ledger_count"] == 0 and cell["excluded_count"] == 1, cell
    assert REWRITE in report["overlap"]["excluded_from_ledger"], report["overlap"]
    assert report["overlap"]["unresolved_pairs"] == 0, report["overlap"]
    assert report["attributed_total_ms"] == 1600.0, report["attributed_total_ms"]
    assert report["coverage_error_pct"] == 0.0, report["coverage_error_pct"]
    assert report["within_one_percent"] is True, report["within_one_percent"]
    assert REWRITE not in report["missing_stages"], report["missing_stages"]


# ==================== 判据④：观察不改正文 ====================


def test_the_account_does_not_change_what_the_leg_returns(tmp_path, monkeypatch, stored_previous_turn):
    stub_rewrite_model(monkeypatch)
    with _redirected_journal(tmp_path, monkeypatch) as journal:
        with_identity = chat._rewrite_followup("r695-on", TRIGGER_QUESTION, config=_config())
        without_identity = chat._rewrite_followup("r695-off", TRIGGER_QUESTION)
        monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")
        with_switch_off = chat._rewrite_followup("r695-off2", TRIGGER_QUESTION, config=_config())
    assert with_identity == without_identity == with_switch_off == REWRITTEN_QUESTION
    assert len(rewrite_rows(journal)) == 2, rewrite_rows(journal)