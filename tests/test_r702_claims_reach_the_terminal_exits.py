# -*- coding: utf-8 -*-
r"""R702 · 把断言（claims）搬到终态出口：问答腿与队列腿各带一枚点得出名字的牙。

病形（工单 `docs/tickets/R702-claims-into-egress.md`）：R699 在工具边界把每一枚断言算完了，
`app/agents/evidence.py::eval_payload_for_answer` 是出货前唯一投影，但 `app/**` 零调用点——
采集侧 `scripts/collect_evaluation_answers.py::build_answer` 对 `claims` 是「响应里有就带走」，
出口不发，C④ 的 `unsupported_claim_rate=0.0` 就永远是一枚没有分母的 0。

判据 → 落点（逐条可失败）：
* 判据 1 出口真带键：`test_the_answered_sync_frame_carries_the_claims_the_turn_already_made`
  （离线驱动真 `/ask`，一条模型都不打）＋队列腿那两枚；牙在
  `test_the_counter_evidence_anchors_name_both_legs`：摘掉任一条出口语句，该钉当场红并点名
  是哪条腿（sync／queue）。摘除实验的红与逐把 sha 记在凭据纸，本件不自带夹具改生产码（同 R585）。
* 判据 2 零分母不许静默：`test_a_laundered_record_...`／`test_an_unreadable_worker_record_...`／
  `test_the_cache_hit_leg_...`——正文有字而一枚断言都交不出时，出口交的是原因码，不是「不带键」。
  空正文与挂起那一轮两枚都不带，那是另一件事：没有正文就没有分母可说。
* 判据 3 契约不破：`test_the_done_frame_only_ever_gains_keys`（只增键、不改键、不删键）＋
  `test_the_contract_names_both_slots_and_every_reason_code_the_code_can_emit`
  （键名与原因码全部从 AST 派生，本文件不抄第二份字面量）。
* 判据 4 热路径不付新税：`test_the_egress_moves_and_never_recomputes`——搬运件的调用面按
  白名单钉死，既不许长出第二份判定，也不许新增任何 IO。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.agents.evidence import Claim, coerce_agent_result, eval_payload_for_answer
from app.common import reliable_queue

from tests.test_approve_canonical_events import (
    ANSWER,
    _drive,
    _patch_offline,
    answer_state,
    doc_agent_result,
    drive_ask,
    empty_stream,
    payload_of,
    retriever_hits,
)
from tests.test_r254_sync_lane_terminal import SHARED_READOUT_KEYS

REPO = Path(__file__).resolve().parents[1]
CHAT_PY = REPO / "app" / "api" / "v1" / "chat.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"

#: 本单加的两枚槽位；键名的真源是构造点自己写的字面量（见 `_slot_keys_written_by`）。
CLAIMS_SLOT = "claims"
ERROR_SLOT = "claims_error"
#: 第三枚在册新键是 R504 的读数格，本单不许顺手改它，只在「只增键」那一格里点名它。
DATA_SLOT = "data_filename"

#: 两条腿的名字：反证牙的红字必须点名腿，不许只报「断言没带」。
LEG_NAMES = ("sync", "queue")

BACKTICK_WORD = re.compile(r"`([a-z_][a-z0-9_]*)`")


# ------------------------------------------------------------------ 驱动把手


def _answered_chunk() -> dict:
    """一轮真答案：证据进过工具边界，记录里本来就带着算好的断言。"""
    return answer_state(hits=retriever_hits())


def _drive_chunk(monkeypatch, tmp_path, chunk, *, endpoint="ask", pending=None) -> dict:
    """真路由、真 chat 代码，只有编排是假的；交回这一轮的 legacy `done` 载荷。"""
    stream = lambda *_a, **_k: iter([chunk])  # noqa: E731 - 一次性编排替身
    chat_module = _patch_offline(monkeypatch, tmp_path, stream, pending)
    return payload_of(_drive(monkeypatch, tmp_path, chat_module, endpoint), "done")


def _drive_scenario(monkeypatch, tmp_path, scenario) -> dict:
    """走在册夹具的场景名册驱动 `/ask`，交回终态帧。"""
    return payload_of(drive_ask(monkeypatch, tmp_path, scenario), "done")


def _boundary_claims() -> list[dict]:
    """边界上算完的那一份：出口若诚实，交回的必须与它逐字相等（不重算）。"""
    record = coerce_agent_result("doc", doc_agent_result(retriever_hits()))
    assert record is not None, "夹具自己就没造出记录，本件的取证没有意义"
    return eval_payload_for_answer(record)["claims"]


def _queue_terminal(**slots) -> dict:
    """走真构造点造队列终态，不在本文件抄第二份载荷。"""
    from app.api.v1 import chat

    return chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True, **slots
    )


def _readout(payload) -> dict:
    from app.api.v1 import chat

    return chat.queue_terminal_readout(_ReadOnlyQueue(payload), "req-r702", {}, "done")


class _ReadOnlyQueue:
    """`queue_terminal_readout` 只问三件事：result／terminal／status，redis 一枚都不碰。"""

    def __init__(self, payload) -> None:
        self._payload = payload

    def result(self, _request_id):
        return "本轮正文。"

    def terminal(self, _request_id):
        return {"state": reliable_queue.TERMINAL_OK, "payload": self._payload}


# ------------------------------------------------------------------- AST 把手


def _chat_text() -> str:
    return CHAT_PY.read_bytes().decode("utf-8")


def _functions(tree: ast.AST) -> list:
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _function(name: str) -> tuple:
    """(节点, 码体原文)。函数没了 = 出口被整枚搬走，本件每一枚牙都该为此而红。"""
    text = _chat_text()
    tree = ast.parse(text, filename=str(CHAT_PY))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(text, node)
            assert segment, "%s 读不到码体" % name
            return node, segment
    raise AssertionError("app/api/v1/chat.py 里没有函数 %s：那一格出口整个不在了" % name)


def _call_names(node: ast.AST) -> set:
    found: set = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        if isinstance(sub.func, ast.Name):
            found.add(sub.func.id)
        elif isinstance(sub.func, ast.Attribute):
            found.add(sub.func.attr)
    return found


def _slot_keys_written_by(function_name: str) -> set:
    """这一枚构造点真写进载荷的字面量键里，属于本单两枚槽位的有哪几枚。"""
    node, _segment = _function(function_name)
    written: set = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub.value in (CLAIMS_SLOT, ERROR_SLOT):
                written.add(sub.value)
    return written


def _claims_error_codes() -> set:
    """`CLAIMS_ERROR_*` 常量取值：唯一真源是 chat.py 顶层那几枚赋值，本文件不抄第二份。"""
    codes: set = set()
    for node in ast.parse(_chat_text(), filename=str(CHAT_PY)).body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if any(name.startswith("CLAIMS_ERROR_") for name in names):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
            codes.add(node.value.value)
    return codes


def _one_code(*tokens: str) -> str:
    codes = {code for code in _claims_error_codes() if all(token in code for token in tokens)}
    assert len(codes) == 1, "按 %r 取原因码取到 %d 枚（要求恰好 1 枚）：现读 %s" % (
        tokens, len(codes), sorted(_claims_error_codes()))
    return codes.pop()


def _chat_top_level_names() -> set:
    """chat.py 顶层名字：契约里带反引号提到它们，不算契约自造的说法。"""
    tree = ast.parse(_chat_text(), filename=str(CHAT_PY))
    names: set = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        for target in getattr(node, "targets", []) or []:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _done_frame_call_sites() -> list:
    """每一处真发终态帧的地方：它在哪个函数里、有没有把本轮记录或原因码交进来。"""
    text = _chat_text()
    tree = ast.parse(text, filename=str(CHAT_PY))
    holders = _functions(tree)
    rows: list = []
    for sub in ast.walk(tree):
        if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)):
            continue
        if sub.func.id != "done_frame_for_turn":
            continue
        owner = None
        for holder in holders:
            if holder.lineno <= sub.lineno <= (holder.end_lineno or holder.lineno):
                if owner is None or holder.lineno > owner.lineno:
                    owner = holder
        keywords = {kw.arg for kw in sub.keywords}
        handed = "agent_results" in keywords or "claims_error" in keywords
        rows.append({
            "holder": owner.name if owner else "<module>",
            "handed": handed,
            "keywords": sorted(k for k in keywords if k in ("agent_results", "claims_error")),
        })
    return rows


# ============ 判据 1 · 问答腿：出口真带键（离线驱动真 /ask，一条模型都不打） ============


def test_the_answered_sync_frame_carries_the_claims_the_turn_already_made(monkeypatch, tmp_path):
    """sync 腿的终态帧必须带 `claims`，且逐枚带着判分器与采集器在读的那几格。"""
    frame = _drive_chunk(monkeypatch, tmp_path, _answered_chunk())
    rows = frame.get(CLAIMS_SLOT)
    assert isinstance(rows, list) and rows, (
        "sync 腿（done_frame_for_turn → done_sse_frame）没带 claims：采集侧 build_answer 是"
        "「有就带走」，这一格缺席就等于 C④ 没有分母。现读键=%s" % sorted(frame))
    fields = set(Claim.model_fields)
    for row in rows:
        assert set(row) == fields, "断言行换了形状，判分器读的就是空气：%s vs %s" % (
            sorted(row), sorted(fields))
        assert isinstance(row["text"], str) and row["text"].strip()
        assert isinstance(row["supported"], bool)
        assert isinstance(row["evidence_refs"], list)
    assert ERROR_SLOT not in frame, (
        "交得出断言那一轮同时发原因码，两枚说法自相矛盾：%r" % frame.get(ERROR_SLOT))


def test_the_egress_moves_the_boundary_readout_verbatim_and_recomputes_nothing(monkeypatch, tmp_path):
    """出口只做搬运：帧里那一份必须与工具边界算完的那一份逐字相等。"""
    frame = _drive_chunk(monkeypatch, tmp_path, _answered_chunk())
    assert frame[CLAIMS_SLOT] == _boundary_claims(), (
        "出口自己算了一遍（或算漏了一部分）：边界那枚唯一投影与交付读数成了两件事")


def test_the_approve_leg_carries_the_same_claims_as_the_ask_leg(monkeypatch, tmp_path):
    """续跑那一支共用同一枚构造点，断言不许只在一条道上出现。"""
    asked = _drive_chunk(monkeypatch, tmp_path, _answered_chunk())
    approved = _drive_chunk(monkeypatch, tmp_path, _answered_chunk(), endpoint="approve")
    assert approved.get(CLAIMS_SLOT) == asked[CLAIMS_SLOT], (
        "approve 腿与 ask 腿交出的断言不一致：approve=%r" % (approved.get(CLAIMS_SLOT),))


# ============ 判据 1 · 队列腿：终态构造点与 /queue/status 读数面同一具形状 ============


def test_the_queue_terminal_constructor_emits_both_slots_under_the_same_names():
    """队列终态与 legacy done 帧同名、同位、同缺席语义：一具解析器盖两条道。"""
    rows = _boundary_claims()
    carried = _queue_terminal(claims=rows)
    assert carried[CLAIMS_SLOT] == rows
    assert ERROR_SLOT not in carried

    refused = _queue_terminal(claims_error=_one_code("zero"))
    assert CLAIMS_SLOT not in refused, (
        "queue 腿交不出断言那一轮不许发一枚空清单冒充「算过了，全都支撑」")
    assert refused[ERROR_SLOT] == _one_code("zero")

    quiet = _queue_terminal()
    assert not {CLAIMS_SLOT, ERROR_SLOT} & set(quiet), sorted(quiet)


def test_the_queue_readout_passes_both_slots_through_and_invents_neither():
    """读数面照旧「载荷里有才说，没有就整格缺席」：搬运不判定，更不替载荷补一格。"""
    rows = _boundary_claims()
    carried = _readout(_queue_terminal(claims=rows))
    assert carried[CLAIMS_SLOT] == rows
    assert ERROR_SLOT not in carried

    silent = _readout(_queue_terminal())
    assert not {CLAIMS_SLOT, ERROR_SLOT} & set(silent), (
        "载荷没交，读数面却替它补了一格：%s" % sorted(silent))

    refused = _readout(_queue_terminal(claims_error=_one_code("record")))
    assert refused[ERROR_SLOT] == _one_code("record")
    assert CLAIMS_SLOT not in refused


# =============== 判据 2 · 零分母不许退化成「不带 claims 键」那枚假绿 ===============


def test_a_laundered_record_surfaces_the_zero_denominator_code_not_a_missing_key(monkeypatch, tmp_path):
    """洗过的记录（正文在、断言空表）正是 R699 拒绝出货的那一枚：今天必须说得出为什么。"""
    chunk = _answered_chunk()
    chunk["agent_results"]["doc"]["claims"] = []
    frame = _drive_chunk(monkeypatch, tmp_path, chunk)
    assert CLAIMS_SLOT not in frame, (
        "零分母交成一枚空清单，判分器就把这一行读成「没有一条不被支撑」——那正是本单要治的假绿")
    assert frame.get(ERROR_SLOT) == _one_code("zero"), (
        "sync 腿对这一轮的说法不对：现读=%r 期望零分母那一枚" % (frame.get(ERROR_SLOT),))


def test_an_unreadable_worker_record_names_the_record_not_a_clean_zero(monkeypatch, tmp_path):
    """记录还原不出 `AgentResult` 与「本轮压根没算出断言」是两件事，码不许混成一格。"""
    chunk = _answered_chunk()
    chunk["agent_results"]["doc"] = {"worker": "doc", "answer": ANSWER, "claims": "不是清单"}
    frame = _drive_chunk(monkeypatch, tmp_path, chunk)
    assert frame.get(ERROR_SLOT) == _one_code("record")
    assert CLAIMS_SLOT not in frame


def test_the_cache_hit_leg_names_the_row_it_could_not_read(monkeypatch, tmp_path):
    """命中那一轮的正文出自另一轮的账：它说不出自己的分母，只能具名说「读不出」。"""
    from app.api.v1 import chat

    chat_module = _patch_offline(monkeypatch, tmp_path, empty_stream, None)
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: ANSWER)
    monkeypatch.setattr("app.common.cache.get_cached_answer_record", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.answer_cache_origin", lambda *_a, **_k: {})
    frame = payload_of(_drive(monkeypatch, tmp_path, chat_module, "ask"), "done")

    assert frame.get(ERROR_SLOT) == _one_code("cache"), (
        "缓存命中那一轮必须交得出「这一格的断言在不在」的说法，不许静默缺席：现读键=%s"
        % sorted(frame))
    assert CLAIMS_SLOT not in frame
    assert frame["sources_error"] == chat.SOURCES_ERROR_NO_MANIFEST, (
        "命中腿在册的出处原因码不许被本单挤掉：两枚槽位说的是两件事")


def test_an_empty_answer_offers_neither_slot(monkeypatch, tmp_path):
    """没有正文就没有「分母」这件事可说：两枚槽位都不发，也不许发一枚空 claims 键。"""
    from app.api.v1 import chat

    frame = _drive_scenario(monkeypatch, tmp_path, "unproductive")
    assert frame["terminal_state"] == chat.TERMINAL_STATE_NO_ANSWER
    assert not {CLAIMS_SLOT, ERROR_SLOT} & set(frame), sorted(frame)


def test_a_parked_turn_hands_back_the_notice_without_a_denominator(monkeypatch, tmp_path):
    """挂起那一轮交回的是那句挂起说明而不是答案：没有正文可判，两枚槽位都不带。"""
    from app.api.v1 import chat

    frame = _drive_scenario(monkeypatch, tmp_path, "hitl_repark")
    assert frame["terminal_state"] == chat.TERMINAL_STATE_AWAITING_APPROVAL
    assert not {CLAIMS_SLOT, ERROR_SLOT} & set(frame), sorted(frame)


def test_the_state_reset_sentinel_is_never_read_as_a_worker(monkeypatch, tmp_path):
    """`{"__reset__": {}}` 是 state 合并协议的控制记法，不是交不出断言的 worker 记录。"""
    chunk = _answered_chunk()
    chunk["agent_results"]["__reset__"] = {}
    frame = _drive_chunk(monkeypatch, tmp_path, chunk)
    assert frame[CLAIMS_SLOT] == _boundary_claims(), (
        "哨兵被当成一枚交不出断言的记录，真读数被原因码顶掉了：%r" % (frame.get(ERROR_SLOT),))
    assert ERROR_SLOT not in frame


# =============== 判据 3 · 响应形状只增键；契约与代码必须同一本账 ===============


def test_the_done_frame_only_ever_gains_keys(monkeypatch, tmp_path):
    """向后兼容：在册键一枚不少，新键最多本单那两枚（前端一字节没改也得照常渲染）。"""
    frame = _drive_chunk(monkeypatch, tmp_path, _answered_chunk())
    baseline = {"type"} | SHARED_READOUT_KEYS
    assert baseline <= set(frame), "少了在册读数键：%s" % sorted(baseline - set(frame))
    gained = set(frame) - baseline
    assert gained <= {DATA_SLOT, CLAIMS_SLOT, ERROR_SLOT}, (
        "终态帧长出了账面之外的新键：%s" % sorted(gained))
    assert CLAIMS_SLOT in gained, "本单的键没出现在真驱动的帧上：%s" % sorted(frame)


def test_the_contract_names_both_slots_and_every_reason_code_the_code_can_emit():
    """契约同步尺同族口径：代码能说的每一枚原因码契约都得说得出，契约也不许多造一枚。"""
    text = CONTRACT.read_bytes().decode("utf-8")
    codes = _claims_error_codes()
    assert codes, "原因码集合空了＝零分母那一格又被洗白了"
    for code in sorted(codes):
        assert "`%s`" % code in text, (
            "代码里那枚原因码 %s 没进契约：前端与采集侧无从解释这一格" % code)
    for slot in (CLAIMS_SLOT, ERROR_SLOT):
        assert "`%s`" % slot in text, "出口真发的槽位 `%s` 没写进契约" % slot

    documented = {word for word in BACKTICK_WORD.findall(text) if word.startswith("claims_")}
    invented = sorted(documented - codes - {ERROR_SLOT} - _chat_top_level_names())
    assert not invented, "契约写了代码交不出的说法：%s" % invented


# ============ 判据 1・4 的牙 · 摘掉出口语句必须红，并且点名是哪条腿 ============


#: 逐枚腿 → 构造点 → 那一句出口语句原文（摘掉任一条，下面的钉当场红并点名腿）。
LEG_ANCHORS = {
    "sync": {
        "done_frame_for_turn": (
            "carried, reason = claims_for_egress(agent_results or {}, full_text)",
            "claims=carried or None,",
            "claims_error=reason,",
        ),
        "done_sse_frame": (
            '**({"claims": carried_claims} if carried_claims else {}),',
            '**({"claims_error": carried_claims_error} if carried_claims_error else {}),',
        ),
    },
    "queue": {
        "build_queue_terminal": (
            '**({"claims": carried_claims} if carried_claims else {}),',
            '**({"claims_error": carried_claims_error} if carried_claims_error else {}),',
        ),
        "queue_terminal_readout": (
            'readout["claims"] = [row for row in carried_claims if isinstance(row, dict)]',
            'readout["claims_error"] = carried_claims_error',
        ),
    },
}


def test_the_counter_evidence_anchors_name_both_legs():
    """反证牙（判据 1）：出口语句是这两条腿各自的那几条，摘一条就红并点名腿。"""
    assert set(LEG_ANCHORS) == set(LEG_NAMES), (
        "反证名册的腿与在册两条腿对不上：%s vs %s" % (sorted(LEG_ANCHORS), sorted(LEG_NAMES)))
    for leg, homes in sorted(LEG_ANCHORS.items()):
        for function_name, anchors in sorted(homes.items()):
            _node, segment = _function(function_name)
            for anchor in anchors:
                hits = segment.count(anchor)
                assert hits == 1, (
                    "%s 腿的出口语句在 %s 里命中 %d 枚（要求恰好 1 枚）——摘掉或改写它，"
                    "这一条腿就不再带 claims：%s" % (leg, function_name, hits, anchor))


def test_both_terminal_constructors_write_the_very_same_slot_names():
    """两条腿共用一具形状：两枚构造点各自真写的槽位必须一模一样。"""
    sync_keys = _slot_keys_written_by("done_sse_frame")
    queue_keys = _slot_keys_written_by("build_queue_terminal")
    assert sync_keys == queue_keys == {CLAIMS_SLOT, ERROR_SLOT}, (
        "两形分叉了：sync=%s queue=%s" % (sorted(sync_keys), sorted(queue_keys)))


def test_every_terminal_site_hands_the_frame_its_records_or_a_reason():
    """每一处发终态帧的地方都得表态：要么交出本轮记录，要么明说自己交不出。"""
    rows = _done_frame_call_sites()
    assert len(rows) == 3, "终态帧出口点数变了（在册三处）：%s" % [row["holder"] for row in rows]
    silent = sorted(row["holder"] for row in rows if not row["handed"])
    assert not silent, (
        "这些出口没把本轮断言交给终态帧，也没有具名原因码：%s" % silent)


def test_the_egress_moves_and_never_recomputes():
    """热路径不付新税（判据 4）：搬运件的调用面按白名单钉死，IO 与第二份判定一枚都不许长出来。"""
    node, segment = _function("claims_for_egress")
    allowed = {
        "str", "isinstance", "strip", "items", "extend",
        "coerce_agent_result", "eval_payload_for_answer",
    }
    extra = sorted(_call_names(node) - allowed)
    assert not extra, "出口多调了没在册的东西（新税或第二份判定）：%s" % extra
    forbidden = (
        "open", "read_text", "read_bytes", "write_text", "Path", "requests", "httpx",
        "redis", "get_client", "sleep", "subprocess",
        "build_answer_claims", "atomize_answer_claims", "claim_support_scan",
        "build_agent_result",
    )
    used = _call_names(node)
    present = sorted(name for name in forbidden if name in used or "%s(" % name in segment)
    assert not present, "搬运件里出现了判定或 IO：%s" % present
    assert "await " not in segment, "出口不许把终态帧挂在新的 await 上"