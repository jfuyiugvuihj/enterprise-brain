# -*- coding: utf-8 -*-
"""R717 · 队列那三处终态构造点必须把两格断言分母递进去（R702 交回的欠项：补发布腿）。

钉什么（工单 R717 判据①②③）：
  ① 结构普查：deploy/queue_worker.py 里 chat.build_queue_terminal 的调用点**逐枚**都带
     claims= 与 claims_error=，身份由 (所在函数, terminal_state) 派生，不抄行号；枚数钉死为三，
     第四枚调用点想不递两格就当场红。
  ② 形状：走真构造点＋真读数面，正文腿交回的 claims 与工具边界上算完的那一份**逐字相等**
     （只搬运、零重算），读数面与载荷同名同位同缺席语义。
  ③ 挂起轮：空正文两格都不发——「没有分母」与「一枚不被支撑的断言都没有」两句都不许说。
  ④ 反证刀：摘掉任一处的 claims 投递 ⇒ ① 点名那一处红；把稳定码换成空 claims ⇒ 构造点
     不许发那一格（R699 拒绝的假绿形状，与 R702 判据 2 同一口径）。

🔴 全程离线：零服务／零容器／零模型／零连库。夹具复用 tests/test_approve_canonical_events.py
   与 tests/test_r702_claims_reach_the_terminal_exits.py（R601 立的规矩：不许再抄一份构造）。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.agents.evidence import coerce_agent_result, eval_payload_for_answer
from app.api.v1 import chat
from app.common import reliable_queue

from tests.test_approve_canonical_events import ANSWER, doc_agent_result, retriever_hits

REPO = Path(__file__).resolve().parents[1]
WORKER_PY = REPO / "deploy" / "queue_worker.py"

#: 两格的名字只从构造点自己写的字面量派生（不许在本文件抄第二份键名账）。
CLAIM_SLOTS = ("claims", "claims_error")


def _worker_text() -> str:
    return WORKER_PY.read_text(encoding="utf-8")


def _terminal_sites(text: str) -> dict:
    """现扫 chat.build_queue_terminal 的调用点：键＝(所在函数, terminal_state 字面量)。

    值＝这一处实际递进来的形参名集合。函数名与状态字面量都从 AST 取，本文件不写行号。
    """
    tree = ast.parse(text)
    owners: dict = {};

    def walk(node, path):
        for child in ast.iter_child_nodes(node):
            next_path = path
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                next_path = path + [child.name]
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "build_queue_terminal"):
                owners[id(child)] = next_path[-1] if next_path else "<module>"
            walk(child, next_path)

    walk(tree, [])
    out = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "build_queue_terminal"):
            continue
        state = ""
        for keyword in node.keywords:
            if keyword.arg == "terminal_state" and isinstance(keyword.value, ast.Attribute):
                state = keyword.value.attr
        names = {keyword.arg for keyword in node.keywords if keyword.arg}
        out[(owners.get(id(node), "<module>"), state)] = names
    return out


def test_every_queue_terminal_site_carries_both_claim_slots() -> None:
    """判据①：三处调用逐枚点名递进两格；枚数一枚不许多、一枚不许少。"""
    sites = _terminal_sites(_worker_text())
    assert len(sites) == 3, "队列构造点的枚数变了（在册三处）：" + repr(sorted(sites))
    blind = sorted(name for name, kwargs in sites.items()
                   if not set(CLAIM_SLOTS) <= kwargs)
    assert not blind, ("这些调用点没把断言分母递进构造点（R702 的出口因此永远读不到分母）："
                      + repr(blind))


def test_knife_stripping_one_site_names_that_site() -> None:
    """判据③ 第一把：摘掉正文腿那处 claims 投递 ⇒ 普查必须点名那一处，不许含糊。"""
    text = _worker_text()
    mutated = text.replace("            claims=carried_claims or None,\n", "", 1)
    assert mutated != text, "锚点没命中：本刀的前提（在册写法）已经漂了"
    sites = _terminal_sites(mutated)
    blind = [name for name, kwargs in sites.items() if "claims" not in kwargs]
    assert len(blind) == 1, "这刀没咬住，或一次咬了两处（枚数账漂了）：" + repr(blind)
    assert blind[0][1] == "TERMINAL_STATE_AWAITING_APPROVAL", blind


def test_knife_replacing_the_code_with_empty_claims_still_ships_nothing() -> None:
    """判据③ 第二把：把两格换成空 claims ⇒ 构造点当场把它吞掉，不许发那一格（R699 的假绿）。"""
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        claims=[],
        claims_error="",
    )
    assert "claims" not in terminal, "空清单也发键＝把「没有分母」洗成「没有幻觉」"
    assert "claims_error" not in terminal, terminal


class _FakeQueue:
    """读数面要的那两件把手：只交回载荷，不连 redis、不连库。"""

    def __init__(self, answer, payload):
        self._answer = answer
        self._payload = payload

    def result(self, request_id):
        return self._answer

    def terminal(self, request_id):
        return {"state": reliable_queue.TERMINAL_OK, "payload": self._payload}

    def status(self, request_id):
        return "done"


def _boundary_claims() -> list:
    """工具边界上算完的那一份：出口若诚实，交回的必须与它逐字相等。"""
    record = coerce_agent_result("doc", doc_agent_result(retriever_hits()))
    assert record is not None, "夹具自己就没造出记录，本件的取证没有意义"
    return eval_payload_for_answer(record)["claims"]


def test_answered_leg_carries_the_boundary_claims_verbatim() -> None:
    """判据②：正文腿那一处搬运不改判定；构造点与读数面同名同位。"""
    raw = doc_agent_result(retriever_hits())
    want = _boundary_claims()
    carried, reason = chat.claims_for_egress({"doc": raw}, ANSWER)
    assert carried == want and reason == "", (len(carried), reason)
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        claims=carried or None,
        claims_error=reason,
    )
    assert terminal["claims"] == want, "终态载荷里的分母与边界上算完的那一份不同"
    readout = chat.queue_terminal_readout(
        _FakeQueue(ANSWER, terminal), "req-r717", {}, "done")
    assert readout["claims"] == want, readout
    assert "claims_error" not in readout, readout


def test_parked_round_ships_neither_slot() -> None:
    """判据② 后半＋判据①：挂起轮没有正文，两格都不发（R702 判据 2 同一条口径）。"""
    raw = doc_agent_result(retriever_hits())
    carried, reason = chat.claims_for_egress({"doc": raw}, "")
    assert carried == [] and reason == "", (carried, reason)
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_AWAITING_APPROVAL,
        answer_present=False,
        claims=carried or None,
        claims_error=reason,
    )
    for slot in CLAIM_SLOTS:
        assert slot not in terminal, "挂起轮发出了 " + slot + " 那一格"
    readout = chat.queue_terminal_readout(
        _FakeQueue(None, terminal), "req-r717", {}, "done")
    for slot in CLAIM_SLOTS:
        assert slot not in readout, readout


def test_record_unavailable_ships_the_code_not_an_empty_denominator() -> None:
    """判据② 的反方向：还原不出记录时只发原因码，那一格的分母仍不许被补成空清单。"""
    carried, reason = chat.claims_for_egress({"doc": {"answer": "有正文"}}, "有正文")
    assert carried == [] and reason == chat.CLAIMS_ERROR_NO_RECORD, (carried, reason)
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        claims=carried or None,
        claims_error=reason,
    )
    assert "claims" not in terminal, "拿空清单冒充分母＝把「读不出」说成「没有断言"
    assert terminal["claims_error"] == chat.CLAIMS_ERROR_NO_RECORD, terminal
    readout = chat.queue_terminal_readout(
        _FakeQueue("有正文", terminal), "req-r717", {}, "done")
    assert readout["claims_error"] == chat.CLAIMS_ERROR_NO_RECORD, readout
    assert "claims" not in readout, readout


def test_no_fourth_slot_slips_into_the_terminal_payload() -> None:
    """判据② 的边界：新键只限那两格；第四枚名字不许过。"""
    terminal = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        claims=_boundary_claims(),
    )
    baseline = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
    )
    extra = sorted(set(terminal) - set(baseline))
    assert extra, "两格一枚都没长出来，本单没递东西"
    assert set(extra) <= set(CLAIM_SLOTS), "构造点长出了不在册的第四枚键名：" + repr(extra)
    with pytest.raises(TypeError):
        chat.build_queue_terminal(
            terminal_state=chat.TERMINAL_STATE_ANSWERED,
            answer_present=True,
            claims_denominator=_boundary_claims(),
        )

