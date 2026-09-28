# -*- coding: utf-8 -*-
r"""R414 (b) · 终态那一帧必须说得出「这一轮的数字是从哪份数据文件算的」。

改前现场读数（动手之前现读，坐标一律按符号名，不抄行号）：

* ``app/api/v1/chat.py::_document_source_row`` 第二句就是
  ``evidence.get("source_type") != "document"`` -> return None。dataset 那一批证据
  一个字都不往上传，所以「本轮实际拿去算的那份文件」在 HTTP 出口根本不存在。
* 终态帧有两枚唯一构造点，键集合里都没有 ``data_filename``：
  - canonical 终态 ``request.completed`` 的 data：现读为 session_id / worker_count /
    elapsed / answer_length / awaiting_hitl / awaiting_steps 六格（``/ask`` 与
    ``/approve`` 两条腿同形），本单在它旁边补上 ``data_filename`` 一格；
  - legacy ``done`` 与队列终态：那两份的键集合被在册件
    ``tests/test_r254_sync_lane_terminal.py`` 钉成 ``{"type"} | SHARED_READOUT_KEYS``
    （按名点的那枚 ``test_the_done_frame_never_leaves_a_key_off`` 用的是**相等**而不是包含）。
    🔴 本单一个字都没动那枚在册件：它在写域外，动它就是越界。这一格的裁定记在交回单。

动作的边界：只加一格读数，既有键的名字与语义一个字都不改；不新增第二道放行分支
（``_collect_dataset_filenames`` 只搬运，可见性判定仍只有 ``_authorized_source_rows`` 那一处）。

离线驱动沿用 ``tests/test_approve_canonical_events.py`` 那套件（假编排 + 临时会话注册表），
一发模型都不打、一条真端口都不开。
"""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from app.agents import evidence as evidence_module
from app.api.v1 import chat
from tests.test_approve_canonical_events import (
    SESSION_ID,
    _consume,
    _http_request,
    _patch_offline,
    finance_principal,
    payload_of,
)

DATASET = "报销明细表.csv"
OTHER_DATASET = "库存周转表.csv"
ANSWER_TEXT = "金额合计 12 笔。"
DATA_QUESTION = "这份数据的金额合计是多少？"
COMPLETION = "request.completed"


def dataset_agent_result(*filenames: str, worker: str = "data") -> dict:
    """证据先进工具边界唯一的写入口，再落成 canonical AgentResult——不从正文反推。"""
    bag = evidence_module.new_evidence_bag()
    for name in filenames:
        evidence_module.record_dataset(
            bag,
            filename=name,
            dataset_id="ds-" + name,
            version_id="v-1",
            rows=12,
            columns=["金额", "部门"],
            department="财务部",
        )
    result = evidence_module.build_agent_result(
        worker=worker,
        answer=ANSWER_TEXT,
        bag=bag,
        request_id="req-r414",
        trace_id="trace-r414",
        task_id="task-r414",
        session_id=SESSION_ID,
    )
    return result.model_dump(mode="json")


def _stream_of(*filenames: str):
    chunk = {
        "messages": [AIMessage(content=ANSWER_TEXT)],
        "worker_results": {"data": ANSWER_TEXT},
        "final_answer": ANSWER_TEXT,
        "agent_results": {"data": dataset_agent_result(*filenames)},
    }
    return iter([chunk])


def drive_ask(monkeypatch, tmp_path, *, filenames=(), declared: str = DATASET) -> dict:
    """真路由、真 chat 代码，只有编排是假的；交回 canonical 终态那一帧的载荷。"""
    stream = lambda *_a, **_k: _stream_of(*filenames)
    _patch_offline(monkeypatch, tmp_path, stream, None)
    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message=DATA_QUESTION, session_id=SESSION_ID, data_filename=declared),
            http_request=_http_request(finance_principal()),
        )
    )
    body = asyncio.run(_consume(response))
    return payload_of(body, COMPLETION)


def drive_approve(monkeypatch, tmp_path, *, filenames=()) -> dict:
    stream = lambda *_a, **_k: _stream_of(*filenames)
    _patch_offline(monkeypatch, tmp_path, stream, None)
    response = asyncio.run(
        chat.approve(
            chat.ApproveRequest(session_id=SESSION_ID, approved=True),
            http_request=_http_request(finance_principal()),
        )
    )
    body = asyncio.run(_consume(response))
    return payload_of(body, COMPLETION)


# ==================== 判据①：终态那一帧的键集合里必须有 data_filename ====================


def test_the_terminal_frame_carries_data_filename(monkeypatch, tmp_path):
    """反证：把 ``chat.py`` 出口里那一行摘掉（R414 反证刀·副本驱动器道，见契约同节），本枚当场红。"""
    completed = drive_ask(monkeypatch, tmp_path, filenames=(DATASET,))

    assert "data_filename" in completed["data"], (
        "终态那一帧又不说用的哪份文件了。键集合：" + repr(sorted(completed["data"]))
    )


def test_the_terminal_frame_names_the_file_this_turn_actually_used(monkeypatch, tmp_path):
    """值必须是**本轮实际使用**的那枚文件名，逐字相等。"""
    completed = drive_ask(monkeypatch, tmp_path, filenames=(DATASET,))

    assert completed["data"]["data_filename"] == DATASET, completed["data"]


def test_it_is_not_an_echo_of_the_declared_field(monkeypatch, tmp_path):
    """反手抄刀：声明的是 A，工具实际算的是 B，终态只能说 B。

    把那一格写成 request.data_filename 的回声，这一枚当场红——回声证明不了「这个数是从
    哪份文件算的」，它只证明用户自己这么说过。
    """
    completed = drive_ask(monkeypatch, tmp_path, filenames=(OTHER_DATASET,), declared=DATASET)

    assert completed["data"]["data_filename"] == OTHER_DATASET, completed["data"]


def test_the_approve_lane_reports_the_same_cell(monkeypatch, tmp_path):
    """批准续跑那条腿与 /ask 同一格读数：两道不能只有一道说得出。"""
    completed = drive_approve(monkeypatch, tmp_path, filenames=(DATASET,))

    assert completed["data"]["data_filename"] == DATASET, completed["data"]


# ==================== 判据①的另一半：说不清就别说 ====================


def test_a_turn_that_analyzed_nothing_says_nothing(monkeypatch, tmp_path):
    """零枚 dataset 证据 -> 空串。不许把「没跑数据」画成「用了一份空文件」。"""
    completed = drive_ask(monkeypatch, tmp_path, filenames=(), declared="")

    assert completed["data"]["data_filename"] == "", completed["data"]


def test_the_collector_only_reads_dataset_rows():
    """收集器的口径：document 证据一枚都不许混进 dataset 那本账。"""

    bag = evidence_module.new_evidence_bag()
    evidence_module.record_document_hits(
        bag,
        query="差旅报销上限",
        hits=[{"content": "上限 2000 元。", "source": "travel-policy.pdf",
               "chunk_index": 0, "classification": 2, "department": "finance"}],
    )
    evidence_module.record_dataset(bag, filename=DATASET, dataset_id="ds", rows=3)
    result = evidence_module.build_agent_result(
        worker="data", answer="x", bag=bag, request_id="r", trace_id="t", task_id="k",
        session_id=SESSION_ID,
    )
    agent_results = {"data": result.model_dump(mode="json")}

    sink: list[str] = []
    chat._collect_dataset_filenames(agent_results, sink)
    assert sink == [DATASET], sink


def test_terminal_data_filename_is_a_scalar_only_when_it_can_be_one():
    """一枚标量只能承载一个答案：零枚与多枚都必须交空串，不许挑一枚冒充。"""

    assert chat.terminal_data_filename([]) == ""
    assert chat.terminal_data_filename([DATASET]) == DATASET
    assert chat.terminal_data_filename([DATASET, OTHER_DATASET]) == ""


def test_a_multi_dataset_turn_refuses_to_name_one_file(monkeypatch, tmp_path):
    """整轮现测：两份都算过，终态就说不出「是哪一份」——那是诚实，不是漏。"""
    completed = drive_ask(monkeypatch, tmp_path, filenames=(DATASET, OTHER_DATASET))

    assert completed["data"]["data_filename"] == "", completed["data"]
    assert "data_filename" in completed["data"], "键必须在，只是那一格说不清"



def _contract() -> str:
    """尾部追加那一节的原文：按标题现取，不抄行号（本仓连续几班栽在手抄坐标上）。"""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs" / "api" / "contract-v1.md").read_text(
        encoding="utf-8").replace("\r\n", "\n")
    heads = [line for line in text.splitlines() if line.startswith("## R414 ")]
    assert len(heads) == 1, heads
    return text[text.index(heads[0]):]


# ==================== 边界：不许顺手改别人钉过的形状 ====================


def test_the_legacy_done_frame_key_set_is_untouched(monkeypatch, tmp_path):
    """R254 把 done 的键集合钉成七格 + type。本单一格都没往里塞（那枚在册件在写域外）。"""

    frame = chat.done_sse_frame(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        sources_present=False,
    )
    payload = frame.split("data: ", 1)[1].strip()
    assert set(json.loads(payload)) == {
        "type", "terminal_state", "answer_present", "sources_present",
        "sources", "sources_error", "usage", "approval",
    }, "done 的键集合漂了：在册件 test_r254_sync_lane_terminal 会当场红"
    assert "data_filename" not in payload

# ==================== 判据②：那枚公开名在契约里有名字，且三态写得清 ====================


def test_the_contract_names_the_public_cell_and_its_three_states():
    """契约里那一格必须把三态写全，并明写「空串不是空文件」。"""
    section = _contract()

    assert "terminal_data_filename" in section, "公开名没进契约：它就是契约那一格的本名"
    assert "正好一枚" in section and "零枚" in section and "两枚及以上" in section, section[:400]
    assert "不是「用了一份空文件」" in section, (
        "空串那两态没在契约里说清：读的人会把「说不清」当成「用了个空文件」")


def test_the_contract_says_the_screen_does_not_change_today():
    """🔴 本单不许冒充像素验收：契约里必须写明前端今天不读这一格。"""
    section = _contract()

    assert "屏上今天不会变" in section, section[:400]
    assert "前端今天**不读**终态这一格" in section, "「界面什么时候说那句话」没交回前端那一单"


def test_the_registration_is_a_tail_append_over_the_base():
    """契约是**跨栈共享面**：本单对它只做尾部追加，基点那份必须是交回字节的前缀。"""
    import re
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    base = subprocess.run(["git", "show", "c0c4bcd:docs/api/contract-v1.md"], cwd=str(repo),
                          capture_output=True, check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    shipped = (repo / "docs" / "api" / "contract-v1.md").read_text(encoding="utf-8").replace("\r\n", "\n")

    assert shipped.startswith(base), "契约中段被动过字：本单只许往文末追加"
    assert len(re.findall("(?m)^## ", shipped)) == len(re.findall("(?m)^## ", base)) + 1
