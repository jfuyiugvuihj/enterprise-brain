"""R172 · 声明跨得过 HITL 确认门（后端半）。

来历：R141 让客户端声明的档位第一次真的改派了工作腿，并把四态读数
(r42 / explicit / not_routed / resumed) 上了三处出口。那一年续跑轮读的是"没人定过"：
用户先声明一档、中途弹确认卡、批准之后再跑的那一轮读回 resumed 且 declared_lane 空串。
本单把这句话改回实话 —— 声明随 pending 账本的挂起行存下来，批准后续跑轮把它读回来。

判据① 的现状账（改动前实取于 839c344：同一台机器、同一个解释器、同一套进程内 TestClient
驱动，用例与断言逐字对着这份账）：

    /ask (lane=report)  响应头  x-effective-lane: report / x-declared-lane: report / x-lane-source: explicit
                        帧 data lane="report" lane_source="explicit" declared_lane="report"
                                lane_rule="artifact" rules_lane="analysis" tier="analysis" may_plan=true
                        trace   request.started 载荷同上（那一处出口住在 orchestrator，本单禁碰）
    挂起行              parked_steps=["export"] —— 账本上压根没有档位这一格
    /approve            响应头  x-lane-source: resumed      （另两枚头整枚不发：取不到就不发）
                        帧 data lane="" lane_source="resumed" declared_lane="" rules_lane="" tier=""
                                lane_rule="" allowed_workers=[] required_workers=[] may_plan=false
                        trace   没有 request.started 那一行 —— 续跑轮的第三处出口本来是空的

声明并没有丢，它就是 /ask 那一轮的 report；丢的是"这一轮的档是谁定的"这句话。
本单之后：挂起行带着它，续跑轮三处出口逐字同一份读数，而 lane（生效）那格仍旧空。

取值闭集一律 import，不硬编猜名：档位 qa/analysis/report，来源 r42/explicit/not_routed/resumed。

全程离线：TestClient 是进程内 ASGI，不开真端口；编排、模型、会话库、答案缓存、待批账本、
trace 落盘全换成桩或临时目录，一次模型往返都不许多。
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agents.nodes import (
    LANE_ANALYSIS,
    LANE_EXEMPT_WORKERS,
    LANE_QA,
    LANE_REPORT,
    LANE_SOURCE_EXPLICIT,
    LANE_SOURCE_NOT_ROUTED,
    LANE_SOURCE_R42,
    LANE_SOURCE_RESUMED,
    LANE_WORKERS,
    not_routed_lane,
    resolve_turn_lane,
    resumed_lane,
)
from app.api.v1 import chat
from app.common.auth import create_token
from app.common.identity import Principal
from app.main import app
from app.storage import pending_approvals as store
from app.storage.sessions import SessionRegistry
from app.trace.store import TraceStore

SESSION = "r172-across-the-gate"
#: 一句真会被判别器判重的话：声明与判别不一致时，两格必须同时可读。
QUESTION = "把各季度营收统计出来并且画成柱状图"
ANSWER = "住宿费凭发票据实报销，单晚上限 500 元。"
DEPARTMENT = "finance"
CLASSIFICATION = "机密"
PARK_AT = {"pending": ["export"], "labels": ["导出文件"]}

#: 读数的全部格名（判据② 的隐私面：这张表以外的东西一律不许出现在任何一处出口上）。
READOUT_KEYS = {
    "session_id",
    "lane",
    "lane_source",
    "lane_rule",
    "declared_lane",
    "rules_lane",
    "tier",
    "allowed_workers",
    "required_workers",
    "may_plan",
}
TRACE_KEYS = READOUT_KEYS | {"owner_id"}

#: 续跑轮读数的原文（判据①：改动前除了 declared_lane="" 之外逐格相同，而 trace 那一行不存在）。
#: 这里刻意写死线上字面值而不是 import 常量：常量漂了就该红，不该跟着一起漂。
RESUMED_FRAME = {
    "session_id": SESSION,
    "lane": "",
    "lane_source": "resumed",
    "lane_rule": "",
    "declared_lane": "report",
    "rules_lane": "",
    "tier": "",
    "allowed_workers": [],
    "required_workers": [],
    "may_plan": False,
}


def _user(**overrides) -> dict:
    user = {"id": "u-r172", "username": "alice", "role": "manager", "department": DEPARTMENT}
    user.update(overrides)
    return user


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_token('alice')}"}


def _canonical(body: str, name: str) -> dict | None:
    for block in body.split("\n\n"):
        lines = block.splitlines()
        if len(lines) >= 2 and lines[0] == f"event: {name}":
            return json.loads(lines[1][len("data: "):])
    return None


def _lane_headers(headers) -> dict:
    wanted = {
        chat.EFFECTIVE_LANE_HEADER,
        chat.LANE_SOURCE_HEADER,
        chat.DECLARED_LANE_HEADER,
    }
    return {key.lower(): value for key, value in headers.items() if key.lower() in wanted}


def _parked_row() -> store.PendingApprovalRecord:
    rows = [row for row in store._all_rows() if row.session_id == SESSION]
    assert rows, "挂起没开成账，本文件的取证就没有意义"
    return max(rows, key=lambda row: row.created_at)


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """把每一处会花钱、会留痕、会打网络的东西换成进程内替身。"""
    from app.common import auth

    user = _user()
    monkeypatch.setattr(auth, "get_user", lambda _name: dict(user))
    monkeypatch.setattr(store, "_MEM_ROWS", {})
    monkeypatch.setattr(store, "_database_available", lambda: False)

    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION, Principal.from_user(user))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.answer_cache_origin", lambda *_a, **_k: {})
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.delenv(chat.REPORT_LANE_QUEUE_ENV, raising=False)

    trace = TraceStore(tmp_path / "trace-events.jsonl")
    monkeypatch.setattr("app.trace.store.default_trace_store", lambda: trace)
    monkeypatch.setattr("app.agents.orchestrator._trace_store", trace)

    def _no_model(*_args, **_kwargs):
        raise AssertionError("跨过 HITL 这道门不许多花一发模型往返")

    monkeypatch.setattr(chat.model_handler, "chat", _no_model)

    def _park_stream(*_args, **_kwargs):
        yield {"messages": [], "worker_results": {}, "final_answer": ""}

    def _resume_stream(*_args, **_kwargs):
        yield {
            "messages": [AIMessage(content=ANSWER)],
            "worker_results": {"export": ANSWER},
            "final_answer": ANSWER,
        }

    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", _park_stream)
    monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", _resume_stream)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: PARK_AT)
    return SimpleNamespace(trace=trace, monkeypatch=monkeypatch)


def _ask(lane=None):
    """发问：带一份真实存在的声明档，图停在确认卡上。"""
    body = {"message": QUESTION, "session_id": SESSION}
    if lane is not None:
        body["lane"] = lane
    response = TestClient(app).post("/api/v1/ask", headers=_auth(), json=body)
    assert response.status_code == 200, response.text
    return response


def _approve():
    response = TestClient(app).post(
        "/api/v1/approve", headers=_auth(), json={"session_id": SESSION, "approved": True}
    )
    assert response.status_code == 200, response.text
    return response


def _cross_the_gate(offline, *, lane=LANE_REPORT):
    """整条链：声明发问 -> 弹确认卡 -> 批准 -> 续跑轮，抄回三处出口的原文。"""
    ask = _ask(lane)
    parked = _parked_row()
    resumed = _approve()
    started = _canonical(resumed.text, "request.started")
    assert started is not None, "续跑轮没有 request.started 帧"
    trace_events = [
        event
        for event in offline.trace.replay(started["trace_id"])
        if event["event_type"] == "request.started"
    ]
    return SimpleNamespace(
        ask=ask,
        ask_headers=_lane_headers(ask.headers),
        ask_frame=(_canonical(ask.text, "request.started") or {}).get("data", {}),
        parked=parked,
        resumed=resumed,
        headers=_lane_headers(resumed.headers),
        frame=started["data"],
        trace_events=trace_events,
        trace_payload=trace_events[0]["payload"] if trace_events else None,
    )
# ==================== A 组 · 判据①：端到端把声明送过那道门 ====================


def test_the_parked_row_is_where_the_declaration_now_lives(offline):
    """存腿：挂起那一轮的声明必须写进行账。

    批准之后续跑的那一轮既拿不到原始请求体，也拿不到上一轮 run_with_stream 里的
    configurable —— 账上这一格是"这一轮的档是谁定的"唯一还活着的地方。摘掉这条腿，
    本用例与 test_a_declared_tier_survives_the_confirmation_card 一起红。
    """
    run = _cross_the_gate(offline)

    assert run.parked.parked_steps == ["export"]
    assert run.parked.declared_lane == LANE_REPORT
    # 对照：进门之前那一轮的三处出口本来就把 report 说成 explicit
    assert run.ask_frame["lane"] == LANE_REPORT
    assert run.ask_frame["lane_source"] == LANE_SOURCE_EXPLICIT
    assert run.ask_headers == {
        chat.EFFECTIVE_LANE_HEADER: LANE_REPORT,
        chat.DECLARED_LANE_HEADER: LANE_REPORT,
        chat.LANE_SOURCE_HEADER: LANE_SOURCE_EXPLICIT,
    }


def test_a_declared_tier_survives_the_confirmation_card(offline):
    """读腿 + 三处出口的原文，逐格钉在本文件开头那份账的"改动后"一侧。

    改动前这里的 declared_lane 是空串、trace 那一行压根不存在：同一枚用例，同一套驱动，
    摘掉「存声明」或「读声明」任一腿都必须红（判据③ 第一把）。
    """
    run = _cross_the_gate(offline)

    # ① 响应头：生效那一枚整枚不发 —— 这一轮的腿没按 report 重新派发过
    assert run.headers == {
        chat.LANE_SOURCE_HEADER: LANE_SOURCE_RESUMED,
        chat.DECLARED_LANE_HEADER: LANE_REPORT,
    }
    assert chat.EFFECTIVE_LANE_HEADER not in run.headers
    # ② canonical request.started 帧的 data
    assert run.frame == RESUMED_FRAME
    # ③ trace 的 request.started 载荷：R172 之前这一行不存在，第三处出口是空的
    assert len(run.trace_events) == 1, "续跑轮的 trace 出口要么没有，要么发了两遍"
    assert run.trace_payload == {**RESUMED_FRAME, "owner_id": "u-r172"}


def test_the_three_outlets_quote_one_number_not_three_rewritings(offline):
    """判据②：同一份数字。三处出口逐格等于现算的那一份读数，谁也没另写一套口径。

    把读数与任一处出口脱钩（改了帧、忘了头；或帧补了、trace 仍旧空）都红这一枚。
    """
    run = _cross_the_gate(offline)
    direct = chat._resumed_lane_readout(SESSION)

    assert set(direct) == READOUT_KEYS - {"session_id"}
    assert {key: run.frame[key] for key in direct} == direct
    assert {key: run.trace_payload[key] for key in direct} == direct
    assert run.trace_payload["session_id"] == run.frame["session_id"] == SESSION
    assert run.headers == chat._lane_readout_headers(direct)
    assert _lane_headers(run.ask.headers) == chat._lane_readout_headers(run.ask_frame)


def test_inheriting_a_declaration_still_claims_no_effective_tier(offline):
    """承诺与证据不许并格：沿用的档住在 declared_lane，生效那格与腿边界仍旧空。

    续跑的这条腿没有按这一档重新派发过 —— 把 report 抄进 lane 那格，或把
    LANE_WORKERS[report] 借给这一轮，都是判据② 严禁的那张脸。
    """
    run = _cross_the_gate(offline)
    inherited = resumed_lane(LANE_REPORT)

    assert run.frame["declared_lane"] == LANE_REPORT
    assert run.frame["lane"] == ""
    assert run.frame["allowed_workers"] == []
    assert run.frame["required_workers"] == []
    assert run.frame["may_plan"] is False
    assert inherited.allowed_workers != LANE_WORKERS[LANE_REPORT] + LANE_EXEMPT_WORKERS
    assert not_routed_lane(LANE_REPORT).allowed_workers == inherited.allowed_workers == ()


def test_a_second_confirmation_card_does_not_lose_the_declaration(offline):
    """批准之后图又挂起一次：这一轮沿用的声明必须跟着续到下一行账上。

    第二次挂起若把声明丢了，第三次批准就又只剩"没人定过"——门不止一道时链条不能断。
    """
    first = _cross_the_gate(offline)
    reparked = _parked_row()

    assert reparked is not first.parked, "图第二次挂起没开新行，本用例就成了空的"
    assert reparked.status == store.AWAITING
    assert reparked.declared_lane == LANE_REPORT

    again = _approve()
    assert _lane_headers(again.headers)[chat.DECLARED_LANE_HEADER] == LANE_REPORT
    assert _parked_row().declared_lane == LANE_REPORT


def test_a_turn_that_declared_nothing_parks_with_nothing(offline):
    """没声明的轮次跨门之后仍旧没声明：补成一档就是替调用方编一句他没说的话。"""
    run = _cross_the_gate(offline, lane="")

    assert run.parked.declared_lane == ""
    assert run.frame["declared_lane"] == ""
    assert run.frame["lane_source"] == LANE_SOURCE_RESUMED
    assert chat.DECLARED_LANE_HEADER not in run.headers
    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_RESUMED


# ==================== B 组 · 判据② 的四态、旧记录兼容表与隐私 ====================


def test_the_inherited_state_is_a_different_sentence_from_the_other_three():
    """四态两两不同句，且"沿用别人定的 report"与"没走图的 report"不并格。"""
    from itertools import combinations

    variants = {
        LANE_SOURCE_R42: resolve_turn_lane(QUESTION, "").as_dict(),
        LANE_SOURCE_EXPLICIT: resolve_turn_lane(QUESTION, LANE_REPORT).as_dict(),
        LANE_SOURCE_NOT_ROUTED: not_routed_lane(LANE_REPORT).as_dict(),
        LANE_SOURCE_RESUMED: resumed_lane(LANE_REPORT).as_dict(),
    }

    assert {row["lane_source"] for row in variants.values()} == set(variants)
    for (name_a, row_a), (name_b, row_b) in combinations(variants.items(), 2):
        assert row_a != row_b, (name_a, name_b)
    # 两两不同句不等于两两只有一格不同：resumed 与 not_routed 差的是"图跑没跑"这一件事，
    # 差在 source 那一格，而这一格读的是路径，不是形容词。
    assert resumed_lane(LANE_QA).as_dict()["lane"] == ""
    assert resolve_turn_lane(QUESTION, LANE_QA).as_dict()["lane"] == LANE_QA


def test_a_row_without_the_field_reads_resumed_and_never_a_tier():
    """旧记录兼容表：三行"读不到这一格"全部落 resumed 且 declared 空。

    落成 resumed 而不是 r42 的理由：r42 说的是"没人声明、系统按题面自选"，而续跑这一轮
    既没有题面可判、也没跑判别器；🔴 更不许落 explicit。三行同形 = 一句"这一轮的档不是
    本轮定的"，正是第四态从设计那天起就在说的那句话。
      行一 R172 之前挂起、TTL 未到的旧行（账上没有这一格）
      行二 PG 后端：0008 尚无 declared_lane 列（补它要一枚 migrations 脚本，写域外）
      行三 本轮压根没声明（新行，值为空串）
    行三由 test_a_turn_that_declared_nothing_parks_with_nothing 端到端钉，行一、行二在下面。
    """
    legacy = store.PendingApprovalRecord(
        session_id=SESSION,
        owner_user_id="u-r172",
        parked_steps=["export"],
        status=store.AWAITING,
        request_id="req-legacy",
        trace_id="trace-legacy",
        task_id="task-legacy",
        created_at=store._NOW().isoformat(),
        expires_at=store._NOW().isoformat(),
    )
    # 这枚构造器没有 declared_lane 实参：它就是 R172 之前那台写账的手。
    store._MEM_ROWS[4242] = legacy
    readout = chat._resumed_lane_readout(SESSION)

    assert readout["lane_source"] == LANE_SOURCE_RESUMED
    assert readout["declared_lane"] == ""
    assert readout["lane"] == ""
    assert chat._lane_readout_headers(readout) == {chat.LANE_SOURCE_HEADER: LANE_SOURCE_RESUMED}
    assert store.get_row(SESSION).declared_lane == ""


def test_an_awaiting_row_written_before_this_ticket_still_survives_the_gate(offline):
    """兼容表第一行，端到端：旧行在场的会话批准之后读的是 resumed，不是 explicit。"""
    from datetime import timedelta

    store._MEM_ROWS[4243] = store.PendingApprovalRecord(
        session_id=SESSION,
        owner_user_id="u-r172",
        parked_steps=["export"],
        status=store.AWAITING,
        created_at=store._NOW().isoformat(),
        expires_at=(store._NOW() + timedelta(hours=1)).isoformat(),
    )
    resumed = _approve()

    assert _lane_headers(resumed.headers) == {chat.LANE_SOURCE_HEADER: LANE_SOURCE_RESUMED}
    frame = _canonical(resumed.text, "request.started")["data"]
    assert frame["declared_lane"] == "" and frame["lane_source"] == LANE_SOURCE_RESUMED


def test_a_postgres_row_without_the_column_degrades_to_nothing_not_to_a_guess(monkeypatch, offline):
    """兼容表第二行：PG 后端读不到那一列 ⇒ 空串。这条腿本单没打通，但它必须不撒谎。"""

    class _Row(dict):
        pass

    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

        def fetchall(self):
            return [self._row] if self._row else []

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            if "to_regclass" in sql.lower():
                return _Result(_Row(table_name="pending_approvals"))
            # 0008 的 SELECT 列里今天没有 declared_lane：这一行就是"旧库上的一行账"。
            return _Result(
                _Row(
                    session_id=SESSION,
                    owner_user_id="u-r172",
                    parked_steps='["export"]',
                    status=store.AWAITING,
                    request_id="req-pg",
                    trace_id="trace-pg",
                    task_id="task-pg",
                    created_at="2026-09-23T00:00:00+00:00",
                    expires_at="2026-09-24T00:00:00+00:00",
                    decided_at=None,
                )
            )

    monkeypatch.setattr(store, "_database_available", lambda: True)
    monkeypatch.setattr(store, "_conn", lambda: _Connection())

    assert store.get_row(SESSION).declared_lane == ""
    readout = chat._resumed_lane_readout(SESSION)
    assert readout["lane_source"] == LANE_SOURCE_RESUMED and readout["declared_lane"] == ""
    assert chat._lane_readout_headers(readout) == {chat.LANE_SOURCE_HEADER: LANE_SOURCE_RESUMED}


def test_a_junk_tier_in_the_ledger_is_not_repaired_into_a_real_one(offline):
    """账本里躺着闭集外的值（手改、混版本）：退成"没有记录"，不退成任何一档。

    猜成 report 等于替调用方挑最贵的那条道；猜成 explicit 更是判据② 明令禁的那张脸。
    """
    store.record_awaiting(SESSION, "u-r172", ["export"], declared_lane="REPORT")

    readout = chat._resumed_lane_readout(SESSION)
    assert readout["declared_lane"] == ""
    assert readout["lane_source"] == LANE_SOURCE_RESUMED

    resumed = _approve()
    assert chat.LANE_SOURCE_HEADER in _lane_headers(resumed.headers)
    assert chat.DECLARED_LANE_HEADER not in _lane_headers(resumed.headers)


def test_no_body_department_or_classification_reaches_any_outlet(offline):
    """隐私不变（判据② 的后半）：三处出口只发读数那几格，正文/部门/密级一个字都不进。"""
    run = _cross_the_gate(offline)
    outlets = {
        "headers": run.headers,
        "frame": run.frame,
        "trace": run.trace_payload,
    }

    for name, payload in outlets.items():
        blob = json.dumps(payload, ensure_ascii=False)
        for forbidden in (ANSWER, QUESTION, DEPARTMENT, CLASSIFICATION, "board-minutes"):
            assert forbidden not in blob, (name, forbidden)
        if name == "headers":
            continue  # 头名是另一个命名空间，下面单独钉
        allowed = TRACE_KEYS if name == "trace" else READOUT_KEYS
        assert set(payload) <= allowed, (name, set(payload) - allowed)
    # 头那一处的"格名"命名空间不同：三枚头名是闭集，多一枚就是新开一处出口没被本单钉住。
    assert set(run.headers) <= {
        chat.EFFECTIVE_LANE_HEADER,
        chat.LANE_SOURCE_HEADER,
        chat.DECLARED_LANE_HEADER,
    }
    assert "department" not in json.dumps(outlets) and "classification" not in json.dumps(outlets)


# ==================== C 组 · 判据③：三把反证的常驻落点 ====================
#
#  摘「存声明」 -> test_the_parked_row_is_where_the_declaration_now_lives 与
#                 test_a_declared_tier_survives_the_confirmation_card 同时红
#  摘「读声明」 -> 上面那一枚与 test_the_readout_is_the_ledger_row_not_a_lucky_guess 红
#  硬编 explicit -> test_the_resumed_round_never_wears_the_explicit_face 与
#                 test_the_inherited_state_is_a_different_sentence_from_the_other_three 红
#  与任一出口脱钩 -> test_the_three_outlets_quote_one_number_not_three_rewritings 红
#                 （帧、头、trace 任一处单改都断等式）


def test_the_readout_is_the_ledger_row_not_a_lucky_guess(offline):
    """续跑轮的读数来自那一行账：改掉账上这一格，三处出口跟着一起改。

    读数若是硬编出来的、或是从题面/会话里"猜"回来的，这一枚当场红。
    """
    _ask(LANE_REPORT)
    _parked_row().declared_lane = LANE_ANALYSIS
    resumed = _approve()
    frame = _canonical(resumed.text, "request.started")["data"]

    assert frame["declared_lane"] == LANE_ANALYSIS
    assert _lane_headers(resumed.headers)[chat.DECLARED_LANE_HEADER] == LANE_ANALYSIS
    started = _canonical(resumed.text, "request.started")
    trace_rows = [
        event
        for event in offline.trace.replay(started["trace_id"])
        if event["event_type"] == "request.started"
    ]
    assert trace_rows[0]["payload"]["declared_lane"] == LANE_ANALYSIS


def test_the_resumed_round_never_wears_the_explicit_face(offline):
    """硬编成 explicit 必红：三处出口的来源格都钉是 resumed，而 explicit 另有其人。"""
    run = _cross_the_gate(offline)

    assert run.headers[chat.LANE_SOURCE_HEADER] == LANE_SOURCE_RESUMED
    assert run.frame["lane_source"] == LANE_SOURCE_RESUMED
    assert run.trace_payload["lane_source"] == LANE_SOURCE_RESUMED
    assert resumed_lane(LANE_REPORT).as_dict() != resolve_turn_lane(QUESTION, LANE_REPORT).as_dict()
    assert run.ask_frame["lane_source"] == LANE_SOURCE_EXPLICIT
    assert run.frame["lane_source"] != run.ask_frame["lane_source"]


# ==================== D 组 · 账本本体的形状（钉住"没打通的那半条腿"不越界） ====================


def test_record_awaiting_still_works_for_the_pre_r172_callers():
    """新格必须是可选的：既有调用点一枚都不该因为本单改签名而红。"""
    row = store.record_awaiting(SESSION, "u-r172", ["export"], request_id="req-1")

    assert row.declared_lane == ""
    assert store.get_row(SESSION).declared_lane == ""


def test_the_parking_writer_binds_no_column_the_ledger_does_not_have(monkeypatch):
    """PG 分支一字未动：0008 没有 declared_lane，多绑一格就是 UndefinedColumn。

    那条错会被 _record_pending_approval 吞掉，代价是**审批面板一条待办都不剩**，
    所以这一格不许顺手加：钉住 INSERT 的列集与占位符数一致，也钉住它不含本单的新格。
    """
    statements = []

    class _Result:
        def fetchone(self):
            return {"table_name": "pending_approvals"}

        def fetchall(self):
            return []

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def execute(self, sql, params=None):
            statements.append((sql, params))
            return _Result()

    monkeypatch.setattr(store, "_database_available", lambda: True)
    monkeypatch.setattr(store, "_conn", lambda: _Connection())

    store.record_awaiting(SESSION, "u-r172", ["export"], declared_lane=LANE_REPORT)

    insert = next(sql for sql, _params in statements if "INSERT INTO pending_approvals" in sql)
    params = next(p for _sql, p in statements if "INSERT INTO pending_approvals" in _sql)
    assert "declared_lane" not in insert
    assert insert.count("%s") == len(params) == 9