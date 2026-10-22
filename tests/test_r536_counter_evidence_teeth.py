# -*- coding: utf-8 -*-
"""R536 判据③ —— 反证刀七把：每一把先在影子端跑正控（确认它会咬），再摘刀验在册钉当场红。

🔴 全程只在 ``tmp_path`` 的副本上动手：把在册源文件读进内存、按锚点改一处、写成副本、按副本
单独加载成模块（运行时那五把）或交给静态尺（形状那两把），再在**同一枚加载路径**上跑正控与
刀下两遍同一场判断。真盘面一个字都不动，所以每把刀前后各核一次在册件 sha256，最后一枚总清点
钉逐字节算总账 —— 纸上的那枚 sha 表就出自本文件的 ``BASELINE_SHA``。

刀口与牙共用 ``tests/test_r536_retrieval_completed_on_product_lane.py`` 与
``tests/test_r536_single_emission_point.py`` 里的同一批尺子：不存在「刀有牙、钉没牙」，也不存在
「切空气的刀」——每一把动手之前先断言锚点在真盘面上命中恰好一枚，动手之后先断言字节真的变了。

victim 全部是在册钉本身（文件名与用例名写死在 ``KNIVES`` 里），不是影子。
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

from app.rag import retrieval_pipeline
from app.rag.filters import resolve_document_retrieval_scope
from test_r536_retrieval_completed_on_product_lane import (
    RecordingStore,
    judge_event,
    judge_projection,
    principal,
    run_leg,
)
from test_r536_single_emission_point import (
    ALLOWED_CALL_SITES,
    ARM,
    CHAT,
    CONSUMER,
    DEBUG_LEGACY,
    EMITTER,
    EXPECTED_ARMS,
    PIPELINE,
    _calls,
    judge,
    sources,
)

REPO = Path(__file__).resolve().parents[1]

#: 本单在册件（刀前后的字节账只对着这张表算）。
ROSTER = (
    "app/api/v1/chat.py",
    "app/rag/retrieval_pipeline.py",
    "tests/test_r536_retrieval_completed_on_product_lane.py",
    "tests/test_r536_single_emission_point.py",
    "tests/test_r536_counter_evidence_teeth.py",
)

BASELINE_SHA = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in ROSTER}

KNIVES = {
    "K1_call_site_removed": (
        PIPELINE,
        "tests/test_r536_single_emission_point.py::test_the_product_call_site_is_exactly_one",
        "调用点清单被摘空 ⇒ 判据② 唯一性红",
    ),
    "K2_unarmed_lane_invents_an_identity": (
        PIPELINE,
        "tests/test_r536_retrieval_completed_on_product_lane.py::test_an_unarmed_retrieval_emits_nothing_and_returns_the_same_hits",
        "没挂身份也发 ⇒ /retrieval/debug 那一腿开始冒充产品道（判据① 明令禁止的形状）",
    ),
    "K3_owner_dropped": (
        PIPELINE,
        "tests/test_r536_retrieval_completed_on_product_lane.py::test_the_principal_aware_retrieval_leg_emits_one_event",
        "owner_id 缺格 ⇒ TraceStore 以 REASON_OWNER_MISSING 拒整行，表里还是 0 行",
    ),
    "K4_query_hash_is_plaintext": (
        PIPELINE,
        "tests/test_r536_retrieval_completed_on_product_lane.py::test_the_principal_aware_retrieval_leg_emits_one_event",
        "query_hash 不再是 64 位摘要（表列 CHAR(64) NOT NULL），且把题面抄进了 trace 表",
    ),
    "K5_hits_dropped": (
        PIPELINE,
        "tests/test_r536_retrieval_completed_on_product_lane.py::test_the_event_is_what_the_registered_consumer_reads",
        "hit_count 折成 0，与实际交回的命中打脸",
    ),
    "K6_approval_lane_not_armed": (
        CHAT,
        "tests/test_r536_single_emission_point.py::test_arms_live_inside_the_worker_thread_bodies",
        "续跑腿不挂身份 ⇒ 判据① 点名的那一腿今天又回 0 行",
    ),
    "K7_token_never_returned": (
        CHAT,
        "tests/test_r536_single_emission_point.py::test_chat_py_arms_both_lanes_and_holds_no_emitter",
        "挂与交回不成对 ⇒ 被复用的工作线程把身份漏给下一个请求",
    ),
}

# ------------------------------------------------------------------ 锚点（现取唯一）
#: 摘刀要摘**整枚调用语句**：这枚调用是跨行的，只切第一行会把剩下的实参悬在空中，
#: 影子文件连 `ast.parse` 都过不去（那量到的就不是「调用点没了」，而是「文件坏了」）。
CALL_ANCHOR = (
    "        record_retrieval_completed(\n"
    "            query=query,\n"
    "            hits=found[0],\n"
    "            scope=scope,\n"
    "            principal=principal,\n"
    "            top_k=top_k,\n"
    "            rewrites=found[1],\n"
    "            duration_ms=duration_ms,\n"
    "        )\n"
)
CALL_CUT = "        pass  # 刀下了：调用点摘掉\n"
GATE_ANCHOR = (
    "    context = trace_context if trace_context is not None else current_retrieval_trace_context()\n"
    "    if context is None:\n"
    "        return None\n"
)
GATE_INVENTED = (
    "    context = trace_context if trace_context is not None else current_retrieval_trace_context()\n"
    "    if context is None:\n"
    "        context = RetrievalTraceContext(trace_id='trace:invented', request_id='req:invented')\n"
)
OWNER_ANCHOR = '        "owner_id": str(getattr(principal, "user_id", "") or "").strip(),\n'
HITS_ANCHOR = '        "hits": _retrieval_hit_ledger(hits),\n'
DIGEST_ANCHOR = '    return hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()\n'
DIGEST_CUT = '    return str(query or "")\n'
APPROVE_ARM_ANCHOR = (
    "            trace_token = arm_retrieval_trace(\n"
    "                trace_id=trace_id, request_id=request_id, task_id=task_id\n"
    "            )\n"
    "            try:\n"
    "                for event in run_interrupt_stream(\n"
)
APPROVE_ARM_CUT = (
    "            trace_token = None\n"
    "            try:\n"
    "                for event in run_interrupt_stream(\n"
)
APPROVE_RESET_ANCHOR = (
    '                result_queue.put(("error", str(e)))\n'
    "            finally:\n"
    "                reset_retrieval_trace(trace_token)\n"
)
APPROVE_RESET_CUT = '                result_queue.put(("error", str(e)))\n'


# ------------------------------------------------------------------------ 刀架
def _text(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def _sha_ok(rel: str) -> None:
    """这把刀前后，真盘面那枚在册件必须还是同一串字节。"""
    assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == BASELINE_SHA[rel], rel


def _one_cut(rel: str, anchor: str, replacement: str) -> str:
    text = _text(rel)
    hits = text.count(anchor)
    assert hits == 1, (rel, "锚点命中数不是 1：这把刀切的不是它声称的那一格", hits)
    mutated = text.replace(anchor, replacement, 1)
    assert mutated != text, "改动是恒等：这把刀是死的"
    return mutated


def _pipeline_copy(tmp_path: Path, mutated: str, name: str):
    """把变异体落进影子树并加载成一枚独立模块（真模块一个字不动）。"""
    shadow = tmp_path / "shadow" / "app" / "rag"
    shadow.mkdir(parents=True, exist_ok=True)
    target = shadow / "retrieval_pipeline.py"
    io_target = str(target)
    with open(io_target, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(mutated)
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _shadow_tree(tmp_path: Path, cut) -> Path:
    """静态尺的影子端：四枚相关文件原样搬进去，其中一枚按锚点改一刀。"""
    root = tmp_path / ("shadowtree" if cut is None else f"shadowtree-{cut[0]}")
    for rel in (PIPELINE, DEBUG_LEGACY, CHAT, CONSUMER):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = _text(rel)
        if cut and rel == cut[1]:
            # cut 的形状是 (刀名, 文件, 锚点, 替换) —— 索引错了就是切空气，所以这里点名到格。
            text = _one_cut(cut[1], cut[2], cut[3])
        with open(str(target), "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(text)
    return root


def _call_sites(root: Path):
    return {(rel, chain[-1]) for rel, chain in _calls(sources(root), EMITTER)}


# ==================================================================== 刀下七格
def test_k1_the_call_site_pin_bites_when_the_emission_call_is_removed(tmp_path):
    _sha_ok(PIPELINE)
    assert _call_sites(_shadow_tree(tmp_path, None)) == ALLOWED_CALL_SITES  # 正控

    root = _shadow_tree(tmp_path, ("k1", PIPELINE, CALL_ANCHOR, CALL_CUT))
    assert _call_sites(root) == set(), _call_sites(root)
    problems = [item for item in judge(root) if "调用点" in item]
    assert problems, "K1 没咬：发射调用点这一格是死牙"
    assert KNIVES["K1_call_site_removed"][1].endswith("test_the_product_call_site_is_exactly_one")
    _sha_ok(PIPELINE)


def test_k2_the_unarmed_pin_bites_when_the_gate_invents_an_identity(tmp_path):
    _sha_ok(PIPELINE)
    _docs, baseline, _rewrites = run_leg(module=retrieval_pipeline, armed=False)
    assert baseline == []  # 正控：没挂身份就一个字都不写

    module = _pipeline_copy(tmp_path, _one_cut(PIPELINE, GATE_ANCHOR, GATE_INVENTED), "r536_k2")
    _docs, events, _rewrites = run_leg(module=module, armed=False)
    assert len(events) == 1, events
    assert events[0]["trace_id"] == "trace:invented"
    _sha_ok(PIPELINE)


def test_k3_the_field_pin_bites_when_owner_id_is_dropped(tmp_path):
    who = principal()
    scope = resolve_document_retrieval_scope(who)
    docs, events, _rewrites = run_leg(who=who)
    assert judge_event(events[0], who=who, scope=scope, hits=docs) == []  # 正控

    module = _pipeline_copy(tmp_path, _one_cut(PIPELINE, OWNER_ANCHOR, ""), "r536_k3")
    cut_docs, cut_events, _ = run_leg(module=module, who=who)
    problems = judge_event(cut_events[0], who=who, scope=scope, hits=cut_docs)
    assert any("owner_id" in item for item in problems), problems
    _sha_ok(PIPELINE)


def test_k4_the_digest_pin_bites_when_query_hash_becomes_the_question(tmp_path):
    who = principal()
    scope = resolve_document_retrieval_scope(who)
    ok_docs, ok_events, _ok_rewrites = run_leg(who=who)
    assert judge_event(ok_events[0], who=who, scope=scope, hits=ok_docs) == []  # 正控
    module = _pipeline_copy(tmp_path, _one_cut(PIPELINE, DIGEST_ANCHOR, DIGEST_CUT), "r536_k4")
    docs, events, _ = run_leg(module=module, who=who)
    problems = judge_event(events[0], who=who, scope=scope, hits=docs)
    assert any("query_hash" in item for item in problems), problems
    assert not any("owner_id" in item for item in problems), problems
    _sha_ok(PIPELINE)


def test_k5_the_consumer_pin_bites_when_hits_are_dropped(tmp_path):
    docs, events, _rewrites = run_leg(who=principal())
    assert judge_projection(events[0], docs) == []  # 正控

    module = _pipeline_copy(tmp_path, _one_cut(PIPELINE, HITS_ANCHOR, ""), "r536_k5")
    cut_docs, cut_events, _ = run_leg(module=module, who=principal())
    problems = judge_projection(cut_events[0], cut_docs)
    assert any("hit_count" in item for item in problems), problems
    _sha_ok(PIPELINE)


def test_k6_the_wiring_pin_bites_when_the_approval_lane_stops_arming(tmp_path):
    _sha_ok(CHAT)
    assert judge() == []  # 正控：真盘面上静态那五格全绿

    root = _shadow_tree(tmp_path, ("k6", CHAT, APPROVE_ARM_ANCHOR, APPROVE_ARM_CUT))
    # victim 钉自己那一格：摘掉续跑腿的挂点以后，影子盘面上的挂点数就少一枚（摘的确实是它）
    chains = [chain for _rel, chain in _calls(sources(root), ARM)]
    assert len(chains) == EXPECTED_ARMS - 1, chains
    assert all("_run" in chain for chain in chains), chains
    problems = [item for item in judge(root) if "chat.py" in item]
    assert problems, "K6 没咬：续跑腿挂点这一格是死牙"
    assert any("对数" in item for item in problems), problems
    _sha_ok(CHAT)


def test_k7_the_wiring_pin_bites_when_the_token_is_never_returned(tmp_path):
    _sha_ok(CHAT)
    assert [item for item in judge() if "挂/交回对数" in item] == []  # 正控：真盘面成对
    root = _shadow_tree(tmp_path, ("k7", CHAT, APPROVE_RESET_ANCHOR, APPROVE_RESET_CUT))
    problems = [item for item in judge(root) if "挂/交回对数" in item]
    assert problems, "K7 没咬：token 交回这一格是死牙"
    assert any("2/1" in item for item in problems), problems
    _sha_ok(CHAT)


# ================================================================= 总清点那一枚
def test_the_roster_is_back_at_the_bytes_recorded_before_every_blade():
    """七把刀全在影子端动手 ⇒ 五枚在册件逐字节回到摘刀前。摘刀前的 sha 已抄进读数纸。"""
    now = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in ROSTER}
    assert now == BASELINE_SHA, {
        rel: (BASELINE_SHA[rel], now[rel]) for rel in ROSTER if now[rel] != BASELINE_SHA[rel]
    }
    for rel, digest in sorted(now.items()):
        assert len(digest) == 64, rel
