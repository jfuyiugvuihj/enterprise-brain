# -*- coding: utf-8 -*-
"""R464：批准续跑那一路，一轮跨批准闸只许留下**一枚**终答流。

病历（跟进单 §133 五，09-28 云端形状窗现读）：六枚 ``approved_ok`` 带 ``uncorrected_breaks``
（``tool-04 2``/``report-02 2``/``report-04 1``/``report-09 1``/``report-10 1``/``report-12 1``），
六枚 ``text_frames > max_stream_frames``（``chart-01 2>1``/``report-02 4>2``/``report-04 15>13``/
``report-09 3>2``/``report-10 4>3``/``report-12 95>93``）；本机 run9 同族三枚（``chart-01``/
``report-02``/``tool-04``）⇒ 不是云端特有。

四段，顺序即判据顺序：

A · 取证与**形状账**（零开窗、零模型、零容器）：把 ``docs/testing/sidecar-run9-frames.jsonl`` 的
逐帧记录重新折一遍，复算出量具自己写进册的那几格，再点名"断流格"这一尺量不到病灶在哪（判据③）。
🔴 本格今天只是形状账，**不是**复现凭据：``text_frames > max_stream_frames`` 对任何两腿轮都非零，
``uncorrected_breaks`` 住在挂起轮那一侧的流内前缀关系上 —— 两件都不说"批准腿有没有再发一枚正文"。
件里那两枚反面钉把这件事钉成机器可验的，谁也不许拿本格冒充结案。

B · 打真路由：挂起轮走真 ``/api/v1/ask``、批准轮走真 ``/api/v1/approve``（进程内驱动，不开端口），
五族形状各对一枚 run9 ``approved_ok`` 题号，喂进**在册量具自己**那把尺（``scripts/
eval_transport_ask_v2.py`` 的 ``_blank_observation``/``_consume``/``_fold_frames``/``_frame_readings``，
经 R215 的 ``_readings_of`` 折账，一个字不改它），并把帧喂进 ``frontend/src/lib/sessions.js:520-530``
的三条分支复算屏上此刻的字（只读前端，不改它）。

C · 同源纪律与作用域：闸门只准用既有出口 —— 帧走 ``text_sse_frame``，换源走 R210 那对
``CORRECTION_STEP_*``；``chat.py`` 里不许再长出第二枚 ``event: text`` 字面、不许另造第二套片账；
作用域只许是 ``approve()`` 里那两枚整段正文 yield（AST 数调用点，不拿 ``not in ai_reply`` 冒充）。
交付的正文一个字都不许被改写：摘干净与带守卫两遍跑，交付行与事件面（除 text/step）逐格相同。

D · 反证**两把刀**（判据① 硬要求）：刀A 摘掉「同字不发」那一格 ⇒ 重复正文那两枚形状当场红，红话
点名「同一轮第二枚终答流」；刀B 把「比过字、确实不同才换源」改成一律 skip ⇒ 另外三枚当场红，红的是
「末帧≠收尾帧」。第三枚影子副本是**改前对照**（整枚守卫摘干净）：它不是牙，是复现凭据 —— 五族形状
必须逐格读出在册账那三格症状。变异只造在临时目录的影子副本里，摘刀前后各记一次被跟踪文件的 sha256，
数不相等当场红。

复现账（判据③）：五族形状在离线夹具里全部复现 —— ``insight-07``/``chart-04`` 跨闸重复正文、
``tool-04``/``report-02`` 批准腿两帧且末帧断流零豁免、``chart-01`` 帧账无病而屏上追加一次。
云端六枚 ``uncorrected_breaks`` 的**枚数**复现不到（云端 2/2/1/1/1/1，本机 run9 读 1/1/0/0/0/0），
复现不到的四枚在 A 段点名，不写成已收。

🔴 判据② 的红线：定罪只用在册量具的 structural 读数 + 前端分支复算 —— 帧内重复计数、屏上追加分支、
原始 ``prefix_breaks`` 对换源记账、末帧≠收尾帧；一处都不拿 ``_frame_verdict`` 当定罪证据（R215 的受控
纠正豁免会让「正文出现两遍」仍读 True，总控已另立 R471 收它）。本件也不许拿豁免换绿：断流读数必须与
**我亲眼在丝上数过的那对 ``step(answer_correction)``** 一格一格相等（``raw_prefix_breaks ==
corrective_replacements`` 且 ``uncorrected_breaks == 0``），正常形状另钉武装枚数 == 0。
"""
import ast
import asyncio
import hashlib
import importlib.util
import inspect
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes
from app.api.v1 import chat
from app.storage import pending_approvals as approval_store
from app.storage.sessions import SessionRegistry
from tests.test_approve_canonical_events import _http_request, finance_principal
from tests.test_r210_break_replaces_the_screen import (  # noqa: F401  同一条链，不造第二份
    _correction_steps,
    _text_contents,
    _wire,
)
from tests.test_r215_recognizing_a_controlled_correction import (  # noqa: F401
    _readings_of,
)

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r464_frame_ruler", _ROOT / "scripts" / "eval_transport_ask_v2.py"
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

FRAMES_LEDGER = _ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
ANSWERS_PATH = _ROOT / "docs" / "testing" / "answers-run9.jsonl"

SESSION_ID = "r464-approval-round"
QUESTION = "把上次统计的口径说明一下"
PENDING_CHART = {"pending": ["chart"], "labels": ["📈 生成图表"]}
#: 挂起轮那句状态说明取自现码 ``hitl_park_text``，逐字 37 字 —— run9 ``chart-01`` 挂起轮那唯一
#: 一枚帧的 ``chars`` 正是 37，本件的形状不是编出来的。
PARK_TEXT = chat.hitl_park_text(PENDING_CHART)

#: 云端那两族题号（跟进单 §133 五 原文），A6 拿它们对**本机**账，不由本文件手写结论。
CLOUD_BREAK_IDS = ("tool-04", "report-02", "report-04", "report-09", "report-10", "report-12")
CLOUD_SPLIT_IDS = ("chart-01", "report-02", "report-04", "report-09", "report-10", "report-12")


def _rows(path: Path) -> dict:
    loaded = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            loaded[row["id"]] = row
    return loaded


@pytest.fixture(scope="module")
def ledger() -> dict:
    return _rows(FRAMES_LEDGER)


@pytest.fixture(scope="module")
def answers() -> dict:
    return _rows(ANSWERS_PATH)


def run9_answer(question_id: str) -> str:
    """取 run9 当天**交回评分器**的那份正文（只读，一字不改）。"""
    rows = _rows(ANSWERS_PATH)
    assert question_id in rows, f"{question_id} 不在 answers-run9 里：夹具前提变了"
    return str(rows[question_id]["answer"])


def _approval_rows(ledger: dict) -> dict:
    return {row["id"]: row for row in ledger.values() if row.get("kind") == "approved_ok"}


def _per_stream(row: dict) -> dict:
    """逐帧记录按流分组：``stream`` 0＝挂起轮那次 HTTP，1＝批准轮那次（与量具折账顺序一致）。"""
    grouped = defaultdict(list)
    for frame in row["frames"]:
        grouped[int(frame["stream"])].append(frame)
    return {stream: sorted(items, key=lambda f: int(f["at"])) for stream, items in sorted(grouped.items())}

# ==== A · 在册片账的离线复算与**形状账**（判据③：复现到哪儿、复现不到哪儿）====


def test_the_ledger_answer_fingerprint_is_the_registered_sha12(ledger, answers):
    """先证指纹：帧账里的 ``answer_sha`` ＝量具 ``_sha12`` 对交付正文取的值，105/105。

    为什么必须先证它：A4 那枚"同一份正文出现在两条流里"只比指纹。指纹若不是逐字指纹，重合就
    什么也不说。这一枚把"纹相等 ⇒ 逐字相等"钉住（``_sha12`` = sha256 前 12 位，量具自述）。
    """
    checked = 0
    for row in ledger.values():
        answer = str(answers[row["id"]]["answer"])
        assert ruler._sha12(answer) == row["answer_sha"], (row["id"], row["answer_sha"])
        checked += 1
    assert checked == len(ledger) == 105, checked


def _recompute(row: dict) -> dict:
    """按量具 ``_fold_frames`` 的口径，从逐帧记录重新折出这一题的 structural 读数。

    照的正是那几行的语义：逐流求和（:610-:612）、``streams`` 连零帧的流也计（:625）、
    ``max_stream_frames`` 取各流帧数的最大值（:626）、末帧只由**有帧**的流覆盖（:627-:628）。
    """
    streams = _per_stream(row)
    frames_by_stream = {stream: len(items) for stream, items in streams.items()}
    breaks_by_stream = {stream: sum(1 for f in items if f["prefix_break"])
                        for stream, items in streams.items()}
    first_break = {}
    for stream, items in streams.items():
        marks = [int(f["at"]) for f in items if f["prefix_break"]]
        first_break[stream] = marks[0] if marks else 0
    return {"text_frames": sum(frames_by_stream.values()),
            "streams": len(frames_by_stream),
            "max_stream_frames": max(frames_by_stream.values()),
            "prefix_breaks": sum(breaks_by_stream.values()),
            "per_stream": [{"frames": frames_by_stream[s], "breaks": breaks_by_stream[s],
                            "first_break_at": first_break[s]} for s in sorted(frames_by_stream)]}


def test_every_run9_approval_round_splits_its_answer_across_two_streams(ledger):
    """复算钉（形状那一半）：18 枚 ``approved_ok`` 逐题复算与在册列一字不差，且 18/18 读成
    ``text_frames > max_stream_frames`` —— 云端那六枚只是这一族的一个子集。"""
    rows = _approval_rows(ledger)
    assert len(rows) == 18, sorted(rows)
    for row in rows.values():
        one = _recompute(row)
        for cell in ("text_frames", "streams", "max_stream_frames", "prefix_breaks", "per_stream"):
            assert one[cell] == row[cell], (row["id"], cell, one[cell], row[cell])
        assert one["text_frames"] > one["max_stream_frames"], row["id"]
        assert one["streams"] == 2, row["id"]


def test_three_run9_rounds_put_the_same_body_on_both_sides_of_the_gate(ledger):
    """**定罪尺① 帧内重复计数**：三枚题把同一份正文各发在两条流里（一轮交回两枚终答流）。

    云端 ``report-09``/``report-10``/``report-12`` 那一族（批准腿把挂起轮已经交出的字原样再交一遍）
    在本机就落在 ``insight-07``/``chart-04``/``tool-04`` 三枚上。"""
    duplicates = {}
    for row in _approval_rows(ledger).values():
        sides = [set(f["sha"] for f in items) for items in _per_stream(row).values()]
        shared = set.intersection(*sides) if len(sides) > 1 else set()
        if shared:
            duplicates[row["id"]] = len(shared)
    assert duplicates == {"insight-07": 1, "chart-04": 1, "tool-04": 1}, duplicates


def test_two_run9_rounds_break_inside_the_approve_stream_with_no_exemption(ledger):
    """**定罪尺② 原始 ``prefix_breaks``**：批准腿自己那条流里断了一次，而且没拿到任何豁免。

    两枚都 ``first_break_at == 这条流的帧数``（坏形落在末帧）而 ``corrective_replacements == 0``：
    屏上那一刻没有 ``step(answer_correction, running)`` 武装它，R215 四条判据凑不上一条 ⇒
    ``uncorrected_breaks`` 与原始账同数。这一格红得诚实，不是被豁免洗掉的绿。
    """
    broken = {row["id"]: row for row in _approval_rows(ledger).values() if row["prefix_breaks"]}
    assert sorted(broken) == ["report-02", "tool-04"], sorted(broken)
    for row in broken.values():
        approve_stream = _per_stream(row)[1]
        assert row["prefix_breaks"] == row["uncorrected_breaks"] == 1, row["id"]
        assert row["corrective_replacements"] == 0, row["id"]
        assert approve_stream[-1]["prefix_break"] is True, row["id"]
        assert row["per_stream"][1]["first_break_at"] == len(approve_stream), row["id"]
        # 断的那一枚正是收尾帧，而它与交付的正文同纹：坏的是"接不上屏上那份字"，不是少交了字。
        assert approve_stream[-1]["sha"] == row["answer_sha"], row["id"]


def test_the_local_ledger_says_which_cloud_rows_it_cannot_reproduce(ledger):
    """**形状账，不是复现凭据**（判据③ 的诚实交代；总控 09-29 裁定把本格从"复现到缺陷"降下来）。

    本格今天量的是：run9 在册账上「批准腿内部原始断流」这一格，在云端那六枚带
    ``uncorrected_breaks`` 的题号的本机对应体上有没有读数。它按构造读不出「批准腿没有重复
    正文」，两把尺都不行：

    - ``text_frames > max_stream_frames``：对**任何**两腿轮都非零（批准腿哪怕只发一枚收尾帧就
      多 1），它说的是"两条流都发过帧"，不特指第二枚终答流；
    - ``prefix_breaks`` / ``uncorrected_breaks``：住在**流内**前缀关系上，而挂起轮那次 HTTP 的
      断流与"下一枚正文是否与屏上相同"无关。离线夹具里 ``arm_pending`` 使每一枚放行帧都是换源
      起点、``_round_screen_answer`` 读不到时 ``on_screen`` 复位为 "" ⇒ 断流格在守卫后面恒读 0。

    🔴 这一格降级成形状账是正当的（原始断流活在挂起轮那一侧，批准腿本来无从复现），但谁也不许
    拿它冒充结案证据：定罪与复现归 B 组（真端点的帧计数 + 屏上分支复算）与 D 组（两把刀，红话
    ``同一轮第二枚终答流`` / ``末帧≠收尾帧``）。下面两枚**反面钉**把"本格量不到病灶"钉成机器可验。
    """
    rows = _approval_rows(ledger)

    def _shared(row: dict) -> int:
        sides = [set(f["sha"] for f in items) for items in _per_stream(row).values()]
        return len(set.intersection(*sides)) if len(sides) > 1 else 0

    shared = {row_id for row_id, row in rows.items() if _shared(row)}
    # 反面钉①：这两枚题断流格读 0，而正文确实跨闸各交了一遍 ⇒ 断流格替不了重复正文那一格。
    blind = sorted(row_id for row_id in shared if not rows[row_id]["uncorrected_breaks"])
    assert blind == ["chart-04", "insight-07"], blind
    # 反面钉②：病历那一格对 18/18 枚全非零 ⇒ 它是"两腿都发了帧"的计数，不是定罪尺（A2 同读）。
    assert all(row["text_frames"] > row["max_stream_frames"] for row in rows.values())

    # 云端六枚断流题的本机对应体：只有两枚有读数，枚数也对不上（照实报复现不到）。
    locally_broken = sorted(i for i in CLOUD_BREAK_IDS if rows[i]["uncorrected_breaks"])
    assert locally_broken == ["report-02", "tool-04"], locally_broken
    assert {i: rows[i]["uncorrected_breaks"] for i in CLOUD_BREAK_IDS} == {
        "tool-04": 1, "report-02": 1, "report-04": 0, "report-09": 0, "report-10": 0,
        "report-12": 0}, "云端 2/2/1/1/1/1 vs 本机 1/1/0/0/0/0 —— 枚数复现不到"
    # 分帧那一格（tf>mx）六枚全复现：它复现的是"批准腿又发了一枚帧"，不是断流。
    assert all(rows[i]["text_frames"] > rows[i]["max_stream_frames"] for i in CLOUD_SPLIT_IDS)
    # chart-01 本机读成"挂起句 37 字 + 批准腿 16 字"：帧账上既无重合也无断流，病只在屏上（B3）。
    chart = rows["chart-01"]
    assert chart["prefix_breaks"] == 0 and chart["uncorrected_breaks"] == 0, chart
    streams = _per_stream(chart)
    assert [f["chars"] for f in streams[0]] == [37], streams
    assert [f["chars"] for f in streams[1]] == [16], streams
    assert PARK_TEXT and len(PARK_TEXT) == 37, len(PARK_TEXT)


# ==================== B · 打真端点：夹具与尺子 ====================


@pytest.fixture(autouse=True)
def memory_approval_ledger(monkeypatch):
    """待批账本走进程内后端：判据要读账面，但绝不允许碰真库（与 R55 那件同一条纪律）。"""
    monkeypatch.setattr(approval_store, "_MEM_ROWS", {})
    monkeypatch.setattr(approval_store, "_database_available", lambda: False)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """两条腿摘成离线件：假编排 + **真**内存会话历史 + 假缓存；零模型、零端口、零容器。

    🔴 与 ``tests/test_approve_canonical_events._patch_offline`` 的唯一分工：那一枚把
    ``_save_message`` 摘成空函数（它只数事件名），本件必须让挂起轮**真**把正文写进会话历史 ——
    那一份行就是"屏上此刻的字"，闸门读的是它（``_round_screen_answer``）。
    """
    flag = {"pending": PENDING_CHART}
    monkeypatch.delenv("REPORT_LANE_VIA_QUEUE", raising=False)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {})
    monkeypatch.setattr(chat, "_MEM_SESSION_MESSAGES", {})
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda _tid: flag["pending"])

    def set_streams(ask_stream, approve_stream):
        monkeypatch.setattr("app.agents.orchestrator.run_with_stream", ask_stream)
        monkeypatch.setattr("app.agents.orchestrator.run_interrupt_stream", approve_stream)

    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION_ID, finance_principal())
    monkeypatch.setattr(chat, "session_registry", registry)
    return {"set_streams": set_streams, "flag": flag, "principal": finance_principal()}


def _cut(text: str, pieces: int) -> list:
    """把整段正文切成 ``pieces`` 枚**增量**片：收端自己累计成帧（判据③ 的两把尺在上游）。"""
    step = max(1, len(text) // pieces)
    return [text[index:index + step] for index in range(0, len(text), step)]


def _marker(worker: str, body: str) -> AIMessage:
    """编排层交给 supervisor 的中转记号：``/ask`` 与 ``/approve`` 的收端都认它、都不发它。"""
    return AIMessage(content=f"【{worker} Agent 返回】{body}")


def _parked_leg(body: str, *, worker: str = "doc", pieces: int = 3):
    """挂起轮：逐片写到底、收尾交整段，然后停在 HITL 节点前 —— run9 第 0 条流的形状。"""

    def stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")
        for index, chunk in enumerate(_cut(body, pieces)):
            sink(nodes.StreamPiece(
                text=chunk, start_at=float(index), end_at=float(index) + 0.4,
                source_fragments=1, emitted_at=float(index),
                call_id="call-park", worker=worker))
        yield _state([HumanMessage(content=QUESTION), _marker(worker, body)], {worker: body},
                     final_answer=body)

    return stream


def _parked_leg_without_body():
    """挂起轮一枚字都没写：屏上只剩那句 37 字状态说明（run9 ``chart-01`` 的 stream 0）。"""

    def stream(*_args, **kwargs):
        yield _state([HumanMessage(content=QUESTION)], {})

    return stream


def _state(messages, worker_results, *, final_answer: str = ""):
    """``graph.stream(..., stream_mode="values")`` 交回的一发状态：整份 state，不是增量。"""
    return {"messages": list(messages), "worker_results": dict(worker_results),
            "final_answer": final_answer}


def _approve_leg(*chunks):
    def stream(*_args, **kwargs):
        for chunk in chunks:
            yield chunk

    return stream


def _drain(response) -> str:
    async def _read():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    return asyncio.run(_read())


def _drive_ask(principal) -> str:
    return _drain(asyncio.run(chat.ask(
        chat.AskRequest(message=QUESTION, session_id=SESSION_ID),
        http_request=_http_request(principal))))


def _drive_approve(principal, *, approved: bool = True) -> str:
    return _drain(asyncio.run(chat.approve(
        chat.ApproveRequest(session_id=SESSION_ID, approved=approved),
        http_request=_http_request(principal))))


def _round(offline, *, ask_stream=None, approve_chunks=None, approved: bool = True) -> dict:
    """跑一整轮跨批准闸（或只跑批准腿），交回两条腿的字面、屏上此刻的字与本轮交付的正文。

    会话历史按**行索引**取：``base`` 之前是上一题留下的行，``base`` 这一行由挂起轮写、
    ``base + 1`` 这一行由批准轮写。这样同一枚夹具里连跑两轮（D 组的对照）也不会串账。
    """
    rows = chat._MEM_SESSION_MESSAGES.setdefault(SESSION_ID, [])
    base = len(rows)
    offline["set_streams"](ask_stream or _parked_leg_without_body(),
                           _approve_leg(*(approve_chunks or [])))
    ask_body = ""
    if ask_stream is not None:
        ask_body = _drive_ask(offline["principal"])
        offline["flag"]["pending"] = None
    approve_body = _drive_approve(offline["principal"], approved=approved)
    # 按**角色**取行而不是按索引：挂起轮那发 /ask 写两行（user 问 + assistant 答），批准轮
    # 只补一行 assistant 答。屏上此刻的字＝本轮之前那一条 assistant 行，交付＝最后一条。
    written = [str(row.get("content") or "") for row in rows[base:]
               if str(row.get("role") or "") == "assistant"]
    expected_rows = 2 if ask_stream is not None else 1
    assert len(written) == expected_rows, (expected_rows, len(written))
    return {"ask": ask_body, "approve": approve_body,
            "on_screen": written[0] if ask_stream is not None else "",
            "delivered": written[-1],
            "rows": [dict(row) for row in rows[base:]]}


def _screen_of_approve_leg(events, on_screen: str) -> dict:
    """批准腿的帧按 ``frontend/src/lib/sessions.js`` 的分支逐帧复算，交回屏上此刻的字。

    分支表与 ``tests/test_r210_break_replaces_the_screen._fold_like_the_browser`` 逐字对齐
    （:520 ``_correcting`` 整段替换 / :524 ``segments.includes`` 丢弃 / :527 covering 替换 /
    :529 追加），唯一差别是**带种子**：``ChatPanel.vue:1076`` 批准时接着写的是挂起轮那条消息
    （``msg.content`` 已经有正文），而 ``sessions.js:442`` 每发 ``consumeSseStream`` 都把
    ``segments`` 从空表起步 —— 挂起轮那份字不在这条流的记账里。这一格正是本单的病根。
    """
    content = on_screen
    segments: list = []
    correcting = False
    doubled = replaced = covered = ignored = 0
    for name, payload in events:
        if name == "step":
            if (payload.get("tool") == chat.CORRECTION_STEP_TOOL
                    and payload.get("status") == "running" and content):
                correcting = True
            continue
        if name != "text":
            continue
        chunk = str(payload.get("content") or "")
        if not chunk:
            ignored += 1
        elif correcting:
            content, correcting, segments = chunk, False, [chunk]
            replaced += 1
        elif chunk in segments:
            ignored += 1
        else:
            covering = next((seg for seg in segments if seg in chunk and chunk != seg), None)
            if covering is not None:
                content, segments = chunk, [chunk]
                covered += 1
            else:
                doubled += 1 if content else 0
                content, segments = f"{content}{chunk}", [*segments, chunk]
    return {"content": content, "doubled": doubled, "replaced": replaced,
            "covered": covered, "ignored": ignored}


def _cells(turn: dict) -> dict:
    """三把定罪尺的读数：全部来自在册量具与前端分支复算，本件不自造口径。"""
    frames_ledger = _readings_of([_wire(turn["ask"]), _wire(turn["approve"])], turn["delivered"])
    ask_bodies, approve_bodies = _text_contents(turn["ask"]), _text_contents(turn["approve"])
    screen = _screen_of_approve_leg(_wire(turn["approve"]), turn["on_screen"])
    per_stream = frames_ledger["per_stream"]
    return {"ledger": frames_ledger, "screen": screen, "delivered": turn["delivered"],
            "on_screen": turn["on_screen"],
            "ask_bodies": ask_bodies, "approve_bodies": approve_bodies,
            "event_names": [name for name, _payload in _wire(turn["approve"])],
            # 定罪尺①：同一份正文出现在两条流里 ⇒ 一轮交回了第二枚终答流。
            "cross_gate_duplicates": len(set(ask_bodies) & set(approve_bodies)),
            # 定罪尺②：原始 prefix_breaks（不读 uncorrected_breaks，不读 corrective_replacements）。
            "raw_prefix_breaks": int(frames_ledger["prefix_breaks"]),
            "approve_leg_breaks": int(per_stream[-1]["breaks"]) if len(per_stream) > 1 else 0,
            "approve_frames": len(approve_bodies),
            # 定罪尺③：末帧≠收尾帧 —— 屏上此刻的字必须就是本轮交付的那一份正文。
            "screen_equals_answer": screen["content"] == turn["delivered"],
            "arms": len(_correction_steps(turn["approve"])),
            "text_frames": int(frames_ledger["text_frames"]),
            "max_stream_frames": int(frames_ledger["max_stream_frames"]),
            "streams": int(frames_ledger["streams"])}


def _assert_one_terminal_stream(cells, *, arms: int) -> None:
    """判据①② 的定罪格：四把尺一起读，红了必须点名「第二枚流」。B 组与 D 组共用这一枚。

    ``arms`` 是这一族形状**应当**出现在丝上的武装 step 枚数（0＝不许换源，2＝一对
    running/done）。🔴 定罪只用在册量具的 structural 读数 + 前端分支复算：帧内重复计数、
    屏上追加分支、原始 ``prefix_breaks``、末帧≠收尾帧 —— 一处都不读 ``_frame_verdict``
    （那是量具，不是被审的那条腿；判据②）。
    """
    assert cells["cross_gate_duplicates"] == 0, (
        f"同一轮第二枚终答流：{cells['cross_gate_duplicates']} 份正文在闸的两条流里各交了一遍"
        "（批准腿又发了一枚终答流，客户把同一轮的答案读两遍）")
    assert cells["screen"]["doubled"] == 0, (
        f"第二枚流：屏上走了 sessions.js:529 的追加分支 {cells['screen']['doubled']} 次")
    assert cells["screen_equals_answer"], (
        f"末帧≠收尾帧：屏上 {len(cells['screen']['content'])} 字 vs 交付 {len(cells['delivered'])} 字"
        "（批准腿该发的那一枚没发出去，或发的不是本轮交付的那份字）")
    assert cells["raw_prefix_breaks"] == cells["ledger"]["corrective_replacements"], (
        f"第二枚流：原始 prefix_breaks={cells['raw_prefix_breaks']} 而真武装记账 "
        f"{cells['ledger']['corrective_replacements']} —— 有断流没被换源记账，或拿豁免洗掉了坏形")
    assert cells["ledger"]["uncorrected_breaks"] == 0, (
        f"第二枚流：未记账断流 {cells['ledger']['uncorrected_breaks']} 枚（病历那一格）")
    assert cells["arms"] == arms, (
        f"武装枚数：丝上 {cells['arms']} 枚 CORRECTION_STEP，本形状预期 {arms} 枚")


def _stand_in(chars: int, seed: str) -> str:
    """按在册账的**字数**造一枚等长替身正文。

    只给"屏上/中途整段"那一侧用：``docs/testing/sidecar-run9-frames.jsonl`` 逐帧只存
    ``sha``/``chars``/``prefix_break``，**不存正文**，挂起轮那一份字的原文拿不到。交付那一侧
    一律用 ``answers-run9.jsonl`` 的原文（A1 已把 ``answer_sha`` 核到逐字指纹）。替身与原文
    的关系（同文 / 异文 / 先后 / 字数）逐格对齐在册账，形状不是编的。
    """
    unit = "〔%s〕企业智脑批准续跑形状复现用的等长替身正文，字数与在册逐帧账对齐。" % seed
    out = ""
    while len(out) < chars:
        out += unit
    return out[:chars]


def _states(approve_bodies: list, delivered: str) -> list:
    """批准腿的假状态序列：第一发定 ``initial_count``，第二发才交出新增的那几行。

    照的是现码 ``approve()`` 里 ``initial_count`` 的读法：它取**第一发**的 ``len(msgs)``，
    所以"中途整段"那一枚必须是新长出来的 AIMessage，否则收端根本走不到发帧那行。
    """
    rows = [{"messages": [HumanMessage(content=QUESTION)], "worker_results": {}, "final_answer": ""}]
    messages = [HumanMessage(content=QUESTION)]
    messages += [AIMessage(content=body) for body in approve_bodies]
    rows.append(_state(messages, {"doc": delivered}, final_answer=delivered))
    return rows


def _shapes() -> dict:
    """五族形状，每族对一枚 run9 ``approved_ok`` 题号，逐格对齐在册逐帧账。"""
    insight = run9_answer("insight-07")          # 590 字：批准腿收尾交回与屏上**同一份**字
    chart04 = run9_answer("chart-04")            # 同族另一枚题、另一份字（不是复制的夹具）
    park239 = _stand_in(239, "tool-04 挂起轮")    # 在册 stream 0 末帧 = 239 字
    tool232 = run9_answer("tool-04")             # 232 字：批准腿收尾那份**不同**的字
    screen852 = _stand_in(852, "report-02 挂起轮")
    head224 = _stand_in(224, "report-02 中途")
    report905 = run9_answer("report-02")          # 905 字
    # run9 ``chart-01`` 交付那一枚 16 字**逐字是内部交接标记** ``【chart Agent 返回】``
    # （与 ``_select_final_answer`` 的 R439 docstring 同读）：R439 并树之后这种正文一律不交付
    # ⇒ 原样喂它会落成具名失败（B6 钉这一格），拿不到"换源一枚正文"的形状。所以本族改用
    # **等长 16 字的真话替身**：帧形状（37 字挂起说明 → 一枚不同的正文）不变。
    chart016 = _stand_in(16, "chart-01 批准腿")
    return {
        "insight-07": {"ask": _parked_leg(insight), "states": _states([], insight),
                       "arms": 0, "frames": 0, "flat": True, "held": 0},
        "chart-04": {"ask": _parked_leg(chart04), "states": _states([], chart04),
                     "arms": 0, "frames": 0, "flat": True, "held": 0},
        "tool-04": {"ask": _parked_leg(park239), "states": _states([park239], tool232),
                    "arms": 2, "frames": 1, "flat": False, "held": 0},
        "report-02": {"ask": _parked_leg(screen852), "states": _states([head224], report905),
                      "arms": 2, "frames": 1, "flat": False, "held": 1},
        "chart-01": {"ask": _parked_leg_without_body(), "states": _states([], chart016),
                     "arms": 2, "frames": 1, "flat": False, "held": 0},
    }


SHAPES = _shapes()
SHAPE_IDS = sorted(SHAPES)          # 在册五族＝病历复现账的口径，别往这枚列表里塞构造形

# 构造形（不是病历复现）：批准腿先把屏上那份**原样重放**，收尾再交一枚**以它开头的更长**正文。
# run9 十八枚 approved_ok 里没有这一形（已现读：重放之后再延长的那枚帧，在册账 0 命中），所以它
# 不进 SHAPE_IDS、不替判据③ 复现任何病例。它钉的是判据① 那一格规则——同字不发**不许把换源的
# 武装用掉**；牙在 D 组刀 C。🔴 谁要把这枚形状当成"病历复现"来报，就是拿构造冒充实测。
CONSTRUCTED_SHAPE_ID = "replay-then-extend"
_screen300 = _stand_in(300, "重放再延长 挂起轮")
_extra = "批准之后补上的一句：差旅报销上限以最新财务制度为准。"
SHAPES[CONSTRUCTED_SHAPE_ID] = {"ask": _parked_leg(_screen300),
                                "states": _states([_screen300], _screen300 + _extra),
                                "arms": 2, "frames": 1, "flat": False, "held": 0}


def _drive(offline, shape: dict) -> dict:
    """跑一整族形状。

    🔴 每次都要把 ``flag["pending"]`` 拨回挂起态：``_round`` 在挂起轮跑完之后会把它置 None
    （批准轮不许再挂起），而同一枚 ``offline`` 夹具里连跑几族（D 组、C3）时，第二族开始
    挂起轮就不挂了 ⇒ 屏上那一份字会从"挂起说明"退化成上一轮的正文，形状对不上在册账。
    """
    offline["flag"]["pending"] = PENDING_CHART
    return _round(offline, ask_stream=shape["ask"], approve_chunks=shape["states"])


# ==================== B · 打真端点：五族形状各复现一枚（判据①②）====================


@pytest.mark.parametrize("question_id", ["insight-07", "chart-04"])
def test_b1_a_round_whose_answer_is_already_on_screen_sends_no_second_stream(offline, question_id):
    """**判据① 主格**：批准腿收尾那份字与屏上逐字相同 ⇒ 一枚帧都不许多发。

    在册对应（run9 ``insight-07``/``chart-04``）：stream 0 末帧与 stream 1 唯一那一枚同纹，
    ``text_frames`` 恰比 ``max_stream_frames`` 多 1 —— 多的就是这枚重复正文（云端
    ``report-09 3>2``/``report-10 4>3``/``report-12 95>93`` 同形）。守卫后面
    ``text_frames == max_stream_frames``（病历格读平）、批准腿交回 0 枚正文帧，而会话历史里
    本轮交付那一行一个字都没少（末帧≠收尾帧那把尺同时读屏上此刻就是交付的那份字）。
    """
    cells = _cells(_drive(offline, SHAPES[question_id]))
    _assert_one_terminal_stream(cells, arms=0)
    assert cells["approve_frames"] == 0, cells
    assert cells["text_frames"] == cells["max_stream_frames"], cells


@pytest.mark.parametrize("question_id", ["tool-04"])
def test_b2_a_replay_of_the_screen_body_drops_and_a_changed_answer_still_arms(offline, question_id):
    """同一轮里两格各咬一次：重放屏上那份 ⇒ 不发；收尾交回不同的字 ⇒ 带 R210 那对 step 换源。

    在册对应（run9 ``tool-04``）：stream 1 = [239 字（与屏上同纹）, 232 字（收尾断流）]，
    ``prefix_breaks == uncorrected_breaks == 1``、``corrective_replacements == 0``。改前那枚
    239 字把屏上拼成两份，232 字又在没有武装的情况下断流。守卫后面批准腿只剩 1 枚帧，且它带
    ``step(answer_correction, running/done)`` 出门，屏上整段替换成本轮交付的那一份。
    """
    cells = _cells(_drive(offline, SHAPES[question_id]))
    _assert_one_terminal_stream(cells, arms=2)
    assert cells["approve_frames"] == 1, cells
    assert cells["screen"]["replaced"] == 1 and cells["screen"]["doubled"] == 0, cells


@pytest.mark.parametrize("question_id", ["chart-01"])
def test_b3_the_park_notice_is_replaced_by_the_answer_not_appended(offline, question_id):
    """``chart-01`` 那族：屏上挂着 37 字挂起说明，批准后的 16 字正文不许接在它后面。

    在册对应（run9 ``chart-01``）：stream 0 = 1 帧 37 字（``hitl_park_text`` 现构造，本件的
    ``PARK_TEXT`` 逐字等于它），stream 1 = 1 帧 16 字 = 交付正文，``prefix_breaks == 0`` 而
    ``text_frames 2 > max_stream_frames 1`` ⇒ 帧账读不出病，病在屏上：16 字走追加分支就成了
    「等待确认…」+「答案」两份字。守卫后面这一枚带武装出门，屏上只剩交付的那 16 字。
    """
    cells = _cells(_drive(offline, SHAPES[question_id]))
    _assert_one_terminal_stream(cells, arms=2)
    assert cells["screen"]["replaced"] == 1, cells
    assert cells["screen"]["content"] == cells["delivered"], cells
    assert len(cells["delivered"]) == 16 and cells["on_screen"] == PARK_TEXT, cells


@pytest.mark.parametrize("question_id", ["report-02"])
def test_b4_a_whole_segment_from_another_stream_is_held_and_said_out_loud(offline, question_id, caplog):
    """中途那枚整段接不上屏上正文 ⇒ 拦下不发，但必须**说得出**拦了谁（静默拦等于没拦）。

    在册对应（run9 ``report-02``）：stream 1 = [224 字, 905 字（收尾断流）]，
    ``uncorrected_breaks == 1``、``corrective_replacements == 0``。守卫后面批准腿只剩收尾那一枚
    （带武装），而 ``[R464]`` 那行 ``logger.error`` 必须当场出现，点名"第二枚流"并报出拦下的字数。
    """
    with caplog.at_level("ERROR", logger=chat.logger.name):
        cells = _cells(_drive(offline, SHAPES[question_id]))
    _assert_one_terminal_stream(cells, arms=2)
    loud = [rec.getMessage() for rec in caplog.records if "[R464]" in rec.getMessage()]
    assert len(loud) == 1, loud
    assert "第二枚流" in loud[0], loud[0]
    assert "224" in loud[0], loud[0]
    assert cells["approve_frames"] == 1, cells


def test_b5_the_unreadable_history_degrades_to_sending_the_body_anyway(offline, monkeypatch):
    """会话历史读不到 ⇒ 屏上按"无正文"处理：本腿照旧把交付的正文发出去，一个字都不许少交。

    🔴 这一格是闸门的退化侧，也照实记下它的代价：屏上无从比对，那一枚同文帧就会回到
    ``sessions.js:529`` 的追加分支 —— 重复正文**回来了**。少交一份交付的正文比让客户重读
    一遍更糟，所以退化方向选"照旧发"，而这一格由会话历史可读性兜着，不由守卫兜着。
    定罪格（``_assert_one_terminal_stream``）在这里**不适用**：它读的是有屏上正文的正常路。
    """
    monkeypatch.setattr(chat, "_get_session_messages",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("会话库不在")))
    insight = run9_answer("insight-07")
    shape = {"ask": _parked_leg(insight), "states": _states([insight], insight)}
    cells = _cells(_drive(offline, shape))
    assert cells["approve_bodies"] == [insight], cells
    assert cells["delivered"] == insight, cells                  # 交付的正文一个字节没少
    assert cells["arms"] == 0, cells                             # 没读到屏上正文 ⇒ 不许凭空武装
    assert cells["screen"]["doubled"] == 1, cells                # 代价：重复正文回到屏上


def test_b6_the_run9_chart_01_body_is_a_marker_and_today_ends_in_a_named_failure(offline):
    """照实报一格复现不到：run9 ``chart-01`` 交付的那 16 字逐字是内部交接标记。

    ``answers-run9.jsonl`` 里那一枚正文是 ``【chart Agent 返回】`` —— R439（已在树上）规定只剩
    标记的正文不许当终答交给客户，所以这一轮今天复现成 ``request.failed``
    （``error_code=no_answer_produced``）+ ``terminal_state=no_answer``，**不是**复现成"批准腿又
    交一枚正文"。本单不改这个结局也不替它兜底：闸门在零枚放行帧之外一个字都不动，屏上仍是挂起
    轮那句 37 字状态说明。这一格归 R439 那条线，不归本单。
    """
    marker = run9_answer("chart-01")
    assert marker == "【chart Agent 返回】", repr(marker)
    shape = {"ask": _parked_leg_without_body(), "states": _states([], marker)}
    turn = _drive(offline, shape)
    cells = _cells(turn)
    assert cells["approve_bodies"] == [], cells                    # 一枚正文都不曾发出
    names = cells["event_names"]
    assert "request.failed" in names and "error" not in names, names
    failed = [payload for name, payload in _wire(turn["approve"]) if name == "request.failed"]
    assert failed[0]["data"]["error_code"] == "no_answer_produced", failed[0]
    assert cells["on_screen"] == PARK_TEXT and cells["delivered"] == "", cells
    assert cells["screen"]["content"] == PARK_TEXT, cells           # 屏上没被改写
    assert cells["arms"] == 0, cells                                # 也没有凭空武装


def test_b7_the_replayed_body_does_not_spend_the_right_to_replace(offline):
    """**判据① 的后半格**：同字不发那一格**不许把换源的武装用掉**（构造形，不是病历复现）。

    形状：屏上站着挂起轮那 300 字 ⇒ 批准腿先原样重放这一枚（该 skip），收尾再交一枚
    **以它开头的更长**正文（300+一句）。规则 1 只许"不发、不武装"，不许顺带 ``arm_pending=False``：
    一旦吃掉，后面那枚延长的正文就变成"同一条流的延续"走普通帧出口，而 ``sessions.js:442``
    每发都从空 ``segments`` 起步 ⇒ 落进 :529 追加分支，屏上成「S + S+尾巴」两份字。
    🔴 这一形在册账 0 命中（见 SHAPES 旁边那句现读），它补的是规则钉，不充病历复现。
    """
    cells = _cells(_drive(offline, SHAPES[CONSTRUCTED_SHAPE_ID]))
    _assert_one_terminal_stream(cells, arms=2)
    assert cells["approve_frames"] == 1, cells                     # 重放那一枚没多发
    assert cells["screen"]["replaced"] == 1 and cells["screen"]["doubled"] == 0, cells
    assert cells["screen"]["content"] == cells["delivered"], cells  # 屏上＝本轮交付那份字

# ==================== C · 同源纪律：只用既有出口，不另造第二套片账 ====================


def _non_frame_events(names) -> dict:
    """除正文帧与武装 step 之外的事件名计数：这一层守卫一票都不许动。"""
    return {name: count for name, count in Counter(names).items() if name not in ("text", "step")}


def _legacy_text_frame(content: str, cache_fields: dict | None = None) -> str:
    """改前那行 f-string 的字面：本单守卫放行时发的帧与它逐字节相同 ⇒ 拿它当旧形状尺。"""
    payload: dict = {"type": "text", "content": content}
    if cache_fields:
        payload.update(cache_fields)
    return f"event: text\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _text_frames(body: str) -> list:
    """逐枚**带帧尾**的 text 帧：``\n\n`` 是 SSE 帧的一部分，比字面时不许把它丢掉。"""
    return [frame + "\n\n" for frame in body.split("\n\n") if frame.startswith("event: text\n")]


def test_the_registered_legs_are_frame_identical_after_the_guard(offline, monkeypatch):
    """未改动的三条腿（挂起轮逐片道 / 挂起轮收尾道 / 命中道）每一枚 text 帧逐字节等于旧字面。

    🔴 判据口径（总控 09-29 订正派工词）：本单守卫的作用域**只是** ``approve()`` 里那两枚
    整段正文 yield，不是 ``full_text not in ai_reply`` 那格全仓收口。所以这一枚钉的是"没被
    触及的腿一个字节都没变"，作用域另有下面那枚 AST 钉数调用点，不拿 ``not in ai_reply`` 冒充。
    """
    insight = run9_answer("insight-07")
    offline["set_streams"](_parked_leg(insight), _approve_leg())
    ask_body = _drive_ask(offline["principal"])
    frames = _text_frames(ask_body)
    pieces = _cut(insight, 3)
    assert len(frames) == len(pieces) + 1, (len(frames), len(pieces))   # 逐片累计 + 收尾一枚
    for frame in frames:
        content = json.loads(frame.split("data: ", 1)[1].rstrip("\n"))["content"]
        assert frame == _legacy_text_frame(content), repr(frame[:48])
    assert _correction_steps(ask_body) == [], "挂起轮那两条腿多发/少发了武装 step ⇒ 逐片道被动了"

    cached = "缓存命中的答案：差旅报销上限 2000 元。"
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: cached)
    monkeypatch.setattr("app.common.cache.answer_cache_origin",
                        lambda *_a, **_k: {"generated_at_iso": "2026-09-29T00:00:00+08:00",
                                           "generated_at_text": "2026-09-29 00:00"})
    monkeypatch.setattr(chat, "_cached_source_manifest", lambda *_a, **_k: None)
    hit_body = _drive_ask_with(chat, offline["principal"], "缓存腿专用问句")
    hit_frames = _text_frames(hit_body)
    assert len(hit_frames) == 1, hit_frames
    payload = json.loads(hit_frames[0].split("data: ", 1)[1].rstrip("\n"))
    assert payload["content"] == cached and payload["cached"] is True, payload
    fields = {key: value for key, value in payload.items() if key != "content"}
    assert hit_frames[0] == _legacy_text_frame(cached, fields), hit_frames[0]
    assert _correction_steps(hit_body) == [], "命中道被守卫越界了"


def _drive_ask_with(module, principal, message: str) -> str:
    return _drain(asyncio.run(module.ask(
        module.AskRequest(message=message, session_id=SESSION_ID),
        http_request=_http_request(principal))))


def test_this_file_never_borrows_the_rulers_verdict_as_evidence():
    """判据② 写进件里：本件一次都不拿量具的 ``_frame_verdict`` 当定罪证据（它是尺子，不是腿）。

    比的是 AST 里的**属性访问**，不是散文 —— 散文里出现过那个词（判据原文与红线说明），
    字符串扫描会假红。量具内部本件只碰这四枚 structural 把手与折账那三枚。
    """
    tree = ast.parse(Path(__file__).resolve().read_text(encoding="utf-8"))
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "frame_verdict" not in {name.lstrip("_") for name in attrs}, sorted(attrs)
    borrowed = sorted(name for name in attrs if name in {
        "_blank_observation", "_consume", "_count_text_frame", "_fold_frames",
        "_frame_readings", "_new_frame_ledger", "_sha12", "_is_correction_arm"})
    assert borrowed, "一把量具都没借用 ⇒ 定罪就成了自造口径"
    assert "_is_correction_arm" not in borrowed, "认脸那格归量具自己，本件不替它判豁免"


def test_the_guard_touches_exactly_two_yield_sites_in_the_approve_leg():
    """作用域钉：守卫只吃 ``approve()`` 里那两枚整段正文 yield，别的一处都不碰。

    数的是 AST 里的实际调用点（不是行数、也不是注释）：``terminal=False`` 一枚（中途整段）
    加 ``terminal=True`` 一枚（收尾）；``ask()`` 里零枚 ⇒ 挂起轮/命中道/逐片道不在写域内。
    """
    tree = ast.parse(inspect.getsource(chat))
    funcs = {node.name: node for node in tree.body
             if isinstance(node, ast.AsyncFunctionDef)}
    approve_fn, ask_fn = funcs["approve"], funcs["ask"]

    def _guard_calls(node):
        return [call for call in ast.walk(node)
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_emit_answer"]

    def _terminal_of(call):
        return next(ast.literal_eval(kw.value) for kw in call.keywords if kw.arg == "terminal")

    inside = _guard_calls(approve_fn)
    assert len(inside) == 2, "批准腿的守卫调用点不是两枚"
    assert sorted(_terminal_of(call) for call in inside) == [False, True]
    assert _guard_calls(ask_fn) == [], "守卫越界进了 ask() ⇒ 越出本单写域"


def test_the_guard_invents_no_new_frame_shape_and_no_second_ledger():
    """同源纪律：帧只走 :func:`text_sse_frame`、武装只走既有那对 step、片账不许有第二套。"""
    tree = ast.parse(inspect.getsource(chat))
    guard = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.ClassDef) and node.name == "_ApprovedAnswerStream")
    approve_fn = next(node for node in tree.body
                      if isinstance(node, ast.AsyncFunctionDef) and node.name == "approve")

    def _strings(node):
        return [value.value for value in ast.walk(node)
                if isinstance(value, ast.Constant) and isinstance(value.value, str)]

    for node, label in ((guard, "_ApprovedAnswerStream"), (approve_fn, "approve()")):
        assert not any("event: text" in value for value in _strings(node)), label
        assert not any("answer_correction" in value for value in _strings(node)), label
    names = {call.func.id for call in ast.walk(approve_fn)
             if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)}
    assert "text_sse_frame" in names, "放行帧没走既有构造器"
    assert not any(isinstance(node, ast.Yield) for node in ast.walk(guard)), "闸门自己发帧"
    used = {node.attr for node in ast.walk(guard)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "self"}
    assert used <= {"on_screen", "arm_pending", "held", "suppressed", "replacements",
                    "emitted", "_same_as_screen"}, sorted(used)


def test_the_guard_does_not_rewrite_the_answer_being_delivered(offline, monkeypatch, tmp_path):
    """正面牙：闸门只改"这一枚帧发不发"，不改**交回客户的任何一个字**。

    同一批形状各跑两遍：一遍带守卫，一遍把守卫摘干净（改前副本）。两遍的会话历史行（屏上/
    交付）、``sources``/``done`` 事件名清单必须相同；带守卫那遍发出去的每一枚帧正文必须逐字
    等于改前那遍也发过的那一枚 —— 少发可以，改写不行。
    """
    guarded = {qid: (_cells(_drive(offline, SHAPES[qid])),
                     _wire(_drive(offline, SHAPES[qid])["approve"])) for qid in SHAPE_IDS}
    _install_mutant_guard(monkeypatch, tmp_path, "pre_change_replica")
    legacy = {qid: _cells(_drive(offline, SHAPES[qid])) for qid in SHAPE_IDS}
    for qid in SHAPE_IDS:
        cells, other_cells = guarded[qid][0], legacy[qid]
        assert cells["delivered"] == other_cells["delivered"], qid      # 交付正文一字不变
        assert cells["on_screen"] == other_cells["on_screen"], qid      # 挂起轮那行也一字不变
        assert set(cells["event_names"]) - set(other_cells["event_names"]) <= {"step"}, qid
        assert set(other_cells["event_names"]) - set(cells["event_names"]) <= {"text"}, qid
        assert _non_frame_events(cells["event_names"]) == _non_frame_events(
            other_cells["event_names"]), (qid, cells["event_names"], other_cells["event_names"])
        for content in cells["approve_bodies"]:
            assert content in other_cells["approve_bodies"], (qid, len(content))
        assert len(cells["approve_bodies"]) <= len(other_cells["approve_bodies"]), qid


# ==================== D · 反证：两把刀 + 一枚改前对照（判据①③）====================

#: 闸门原件的字节指纹：反证全在临时目录的影子副本上做，跑完必须还是这一枚。
CHAT_PATH = Path(inspect.getsourcefile(chat))
CHAT_SHA_AT_IMPORT = hashlib.sha256(CHAT_PATH.read_bytes()).hexdigest()

#: 闸门的源文在 **import 那一刻**取走：摘过一刀之后 ``chat._ApprovedAnswerStream`` 已经是
#: exec 出来的替身，``inspect.getsource`` 对它只会报 "is a built-in class"。
GUARD_SOURCE_AT_IMPORT = inspect.getsource(chat._ApprovedAnswerStream)

#: (锚点, 换成什么)。锚点必须逐字命中闸门源码，命中不了或命中多处 ⇒ 这枚反证是空的。
GUARD_MUTANTS = {
    # 刀 A：摘掉「同字不发」那一格（规则 1 的比字格）。
    "knife_a_drop_the_same_text_cell": (
        '''        # 规则 1（刀 A 摘这一格）：先比字。逐字同屏 ⇒ 不发、不武装、不吃 arm_pending。
        if self._same_as_screen(body):
            self.suppressed += 1  # 本轮已经有这一份字在屏上，不发第二枚流
            return "skip"
''', ""),
    # 刀 B：把「比过字、确实不同才换源」那一格改成一律 skip。
    "knife_b_never_arm": (
        '''        self.arm_pending = False
        self.replacements += 1
        self.on_screen = body
        self.emitted += 1
        return "replace"
''', '''        return "skip"
'''),
    # 刀 C：①的"写钝"退化——同字那一格照发不出帧，却把 arm_pending 吃掉了。
    "knife_c_replay_spends_the_arming": (
        '''        if self._same_as_screen(body):
            self.suppressed += 1  # 本轮已经有这一份字在屏上，不发第二枚流
            return "skip"
''', '''        if self._same_as_screen(body):
            self.suppressed += 1
            self.arm_pending = False  # 写钝：重放那一格把"换源的资格"花掉了
            return "skip"
'''),
    # 改前对照（不是牙）：整枚守卫摘干净 ⇒ 在册病历那一格必须真复现出来。
    "pre_change_replica": (
        '''        if not body:
            return "skip"
''', '''        if body:
            self.emitted += 1
            return "emit"
        if not body:
            return "skip"
'''),
}


def _install_mutant_guard(monkeypatch, tmp_path, name):
    """把摘了刀的闸门装回真路由：影子副本落在 ``tmp_path``，被跟踪文件一个字节都不动。"""
    original = CHAT_PATH.read_bytes()
    assert hashlib.sha256(original).hexdigest() == CHAT_SHA_AT_IMPORT, "闸门原件已被改动"
    source = GUARD_SOURCE_AT_IMPORT
    anchor, replacement = GUARD_MUTANTS[name]
    assert source.count(anchor) == 1, f"锚点在闸门里不唯一（{source.count(anchor)} 处）⇒ 反证是空的"
    mutated = source.replace(anchor, replacement, 1)
    assert mutated != source, "反证没作用到东西上"
    target = tmp_path / ("r464_guard_" + name + ".py")
    target.write_text(mutated, encoding="utf-8", newline="\n")
    namespace = {"__name__": "r464_guard_" + name}
    exec(compile(target.read_text(encoding="utf-8"), str(target), "exec"), namespace)
    assert CHAT_PATH.read_bytes() == original, "被跟踪的 chat.py 被动了"
    monkeypatch.setattr(chat, "_ApprovedAnswerStream", namespace["_ApprovedAnswerStream"])
    return namespace["_ApprovedAnswerStream"]


def _reds_with_guard(tmp_path, monkeypatch, offline, name, shape_ids=None) -> dict:
    """逐枚形状过定罪格，交回 ``{题号: 红话}``；没红的不在表里。

    ``shape_ids`` 默认在册五族（病历复现账）；刀 C 那一把只在构造形上咬得住，另传。
    """
    _install_mutant_guard(monkeypatch, tmp_path, name)
    reds = {}
    for question_id in shape_ids or SHAPE_IDS:
        cells = _cells(_drive(offline, SHAPES[question_id]))
        try:
            _assert_one_terminal_stream(cells, arms=SHAPES[question_id]["arms"])
        except AssertionError as error:
            reds[question_id] = str(error)
    return reds


def test_d1_knife_a_dropping_the_same_text_cell_goes_red_naming_the_second_stream(tmp_path, monkeypatch, offline):
    """**反证 · 刀A**：摘掉「同字不发」那一格 ⇒ 重复正文那两枚形状当场红，红话点名「同一轮第二枚终答流」。

    同时这也是"改前形状"的复现凭据：红的那两枚在摘刀后各多发一枚与屏上逐字相同的正文帧，
    ``text_frames`` 又回到比 ``max_stream_frames`` 多 1 的那一格（云端 6>5、95>93 同一形）。
    """
    reds = _reds_with_guard(tmp_path, monkeypatch, offline, "knife_a_drop_the_same_text_cell")
    assert sorted(reds) == ["chart-04", "insight-07"], f"刀A 红在 {sorted(reds)}"
    for question_id, message in reds.items():
        assert "同一轮第二枚终答流" in message, (question_id, message)
    kept = {qid: _cells(_drive(offline, SHAPES[qid])) for qid in ["tool-04", "report-02", "chart-01"]}
    for qid, cells in kept.items():
        assert cells["cross_gate_duplicates"] == 0, (qid, cells)   # 刀A 咬不到"不同正文"那一族


def test_d2_knife_b_never_arming_goes_red_on_the_last_frame(tmp_path, monkeypatch, offline):
    """**反证 · 刀B**：把「不同正文仍换源」改成一律 skip ⇒ 三枚形状红，红话是「末帧≠收尾帧」。

    这一把挡的是另一种退化：守卫写钝成"批准腿一概不发"。听着也像"只有一枚终答流"，实际是把
    本轮交付的正文扣下来不发 —— 屏上留在挂起轮那份字，客户永远看不到批完之后的答案。
    """
    reds = _reds_with_guard(tmp_path, monkeypatch, offline, "knife_b_never_arm")
    assert sorted(reds) == ["chart-01", "report-02", "tool-04"], f"刀B 红在 {sorted(reds)}"
    for question_id, message in reds.items():
        assert "末帧≠收尾帧" in message, (question_id, message)


def test_d3_the_pre_change_replica_reproduces_the_registered_symptoms(tmp_path, monkeypatch, offline):
    """改前对照：把整枚守卫摘干净，五族形状必须逐格读出在册账那三格症状 —— 复现不到就不许说修了。

    逐格对账（run9 ``approved_ok`` 的 structural 读数，A 组已复算过一字不差）：
    ``insight-07``/``chart-04`` 重复正文 1 份；``tool-04``/``report-02`` 批准腿两帧、末帧断流
    且没有任何豁免；``chart-01`` 帧数 2>1 而断流 0（病只在屏上，追加一次）。
    """
    reds = _reds_with_guard(tmp_path, monkeypatch, offline, "pre_change_replica")
    assert sorted(reds) == SHAPE_IDS, f"摘干净还不全红：{sorted(reds)}"
    cells = {qid: _cells(_drive(offline, SHAPES[qid])) for qid in SHAPE_IDS}
    for qid in ("insight-07", "chart-04"):
        assert cells[qid]["cross_gate_duplicates"] == 1, qid
        assert cells[qid]["text_frames"] == cells[qid]["max_stream_frames"] + 1, qid
    for qid in ("tool-04", "report-02"):
        assert cells[qid]["approve_frames"] == 2, qid
        assert cells[qid]["raw_prefix_breaks"] == 1 == cells[qid]["approve_leg_breaks"], qid
        assert cells[qid]["ledger"]["corrective_replacements"] == 0, qid
        assert cells[qid]["ledger"]["uncorrected_breaks"] == 1, qid
    chart = cells["chart-01"]
    assert (chart["text_frames"], chart["max_stream_frames"]) == (2, 1), chart
    assert chart["raw_prefix_breaks"] == 0 and chart["screen"]["doubled"] == 1, chart
    assert chart["screen"]["content"] == PARK_TEXT + chart["approve_bodies"][0], chart
    assert chart["screen"]["content"].startswith(PARK_TEXT), chart   # 两份字拼在一起，病在屏上


def test_d4_the_mutations_never_touch_the_tracked_gate(tmp_path, monkeypatch, offline):
    """摘刀纪律：影子副本在临时目录，被跟踪的 ``chat.py`` 跑前跑后同一枚 sha256。"""
    for name in GUARD_MUTANTS:
        _install_mutant_guard(monkeypatch, tmp_path, name)
        assert hashlib.sha256(CHAT_PATH.read_bytes()).hexdigest() == CHAT_SHA_AT_IMPORT, name
    assert len(list(tmp_path.glob("r464_guard_*.py"))) == len(GUARD_MUTANTS)

def test_d5_knife_c_spending_the_arming_on_a_replay_goes_red(tmp_path, monkeypatch, offline):
    """**反证 · 刀C**：把「同字不发」写成"顺手吃掉武装" ⇒ 构造形当场红，红话点名追加那一格。

    刀 A 摘的是"发不发"，刀 B 摘的是"换不换源"，两把都咬不到这一格：守卫看着还在"同字不发"，
    实际把本轮**唯一该换源的那一枚**降级成了追加。判据① 要求 skip 不发、不武装、**也不吃**
    ``arm_pending``，这一把就是那一格的牙（正向读数是 B7）。
    """
    reds = _reds_with_guard(tmp_path, monkeypatch, offline, "knife_c_replay_spends_the_arming",
                            shape_ids=[CONSTRUCTED_SHAPE_ID])
    assert sorted(reds) == [CONSTRUCTED_SHAPE_ID], f"刀C 红在 {sorted(reds)}"
    message = reds[CONSTRUCTED_SHAPE_ID]
    assert "追加分支" in message, message                      # 屏上成两份字，正是第二枚流的脸
    assert "第二枚流" in message, message
    # 反向对照：在册五族在这把刀下全绿 ⇒ 刀C 只补①的后半格，不冒充病历复现的牙
    kept = _reds_with_guard(tmp_path, monkeypatch, offline, "knife_c_replay_spends_the_arming")
    assert kept == {}, sorted(kept)
