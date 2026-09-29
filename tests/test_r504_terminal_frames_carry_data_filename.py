# -*- coding: utf-8 -*-
r"""R504 · G03 后端那半格：legacy `done` 帧与队列终态要说得出「这一轮用的哪份数据文件」。

改前现场读数（全部在基点 `405cacb` 上现读，坐标一律按符号名，不抄行号）：

* ``app/api/v1/chat.py::terminal_data_filename`` 与它的上游 ``_collect_dataset_filenames``
  已在册（R414），改前只有 canonical ``request.completed`` 的两枚出口（``/ask`` 正文道、
  ``/approve`` 续跑道）把那一格发出去；
* legacy ``done`` 帧（唯一构造点 ``done_sse_frame``）与队列终态（``build_queue_terminal``）
  的键集里没有 ``data_filename``——那两具键集被在册件
  ``tests/test_r254_sync_lane_terminal.py`` 按名以**相等**钉住；
* ``/queue/status`` 的投影件 ``queue_terminal_readout`` 的口径是「照载荷说，一格都不添」。

本单裁定（沿用在册那一条「宁缺毋造」，不新开判据）：真产出数据文件就必须交
``data_filename``，取值只走在册那枚 ``terminal_data_filename``；真没产出（零枚）与多枚
说不清一律**整格缺席**，不补空串、不拿请求方向的声明值顶它。canonical 那两发的
「键在位、值可为空串」与本单的「整格缺席」是两张脸，不许并。

离线驱动沿用 ``tests/test_approve_canonical_events.py`` 那套件（假编排 + 临时会话注册表），
一发模型都不打、一条真端口都不开、不连库、不起服务、不碰容器。
"""

import ast
import asyncio
import json
import re
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from app.api.v1 import chat
from app.common import reliable_queue
from tests.test_approve_canonical_events import (
    SESSION_ID,
    _consume,
    _http_request,
    _patch_offline,
    finance_principal,
    payload_of,
)
from tests.test_r254_sync_lane_terminal import SHARED_READOUT_KEYS
from tests.test_r414_b_terminal_data_filename import (
    DATASET,
    OTHER_DATASET,
    dataset_agent_result,
)

ANSWER = "金额合计 12 笔。"
DATA_QUESTION = "这份数据的金额合计是多少？"
COMPLETION = "request.completed"
CHAT_PY = "app/api/v1/chat.py"
NO_CELL = object()


def _chunk(*, filenames=(), answer=ANSWER):
    """一枚真形状的状态回报：证据先进工具边界唯一的写入口，正文单独给（可以故意不给）。"""
    return {
        "messages": [AIMessage(content=answer)] if answer else [],
        "worker_results": {"data": answer} if answer else {},
        "final_answer": answer,
        "agent_results": {"data": dataset_agent_result(*filenames)},
    }


def drive(monkeypatch, tmp_path, *, filenames=(), declared=DATASET, endpoint="ask", answer=ANSWER):
    """真路由、真 chat 代码，只有编排是假的；交回这一轮的整条流。"""
    stream = lambda *_a, **_k: iter([_chunk(filenames=filenames, answer=answer)])
    _patch_offline(monkeypatch, tmp_path, stream, None)
    http = _http_request(finance_principal())
    if endpoint == "approve":
        response = asyncio.run(
            chat.approve(chat.ApproveRequest(session_id=SESSION_ID, approved=True), http_request=http)
        )
    else:
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=DATA_QUESTION, session_id=SESSION_ID, data_filename=declared),
                http_request=http,
            )
        )
    return asyncio.run(_consume(response))


def done_frame(body: str) -> dict:
    """流末那枚 legacy ``done`` 的载荷：它仍是本仓唯一认得的「流结束了」信号。"""
    return payload_of(body, "done")


def cell(frame: dict):
    return frame.get("data_filename", NO_CELL)


# ==================== 判据①形一：真产出了数据文件，终态就必须点名 ====================


@pytest.mark.parametrize("endpoint", ["ask", "approve"])
def test_a_turn_that_computed_from_one_file_names_it_in_the_done_frame(monkeypatch, tmp_path, endpoint):
    """反证刀②（摘键）的家：把那一格从构造点摘掉，本枚当场红。"""
    frame = done_frame(drive(monkeypatch, tmp_path, filenames=(DATASET,), endpoint=endpoint))

    assert "data_filename" in frame, (
        "legacy done 又不说用的哪份文件了。键集合：" + repr(sorted(frame))
    )
    assert frame["data_filename"] == DATASET, frame


@pytest.mark.parametrize("endpoint", ["ask", "approve"])
def test_the_done_frame_and_the_canonical_terminal_never_disagree(monkeypatch, tmp_path, endpoint):
    """同源：两枚终态报的是同一格，取值出自同一枚 ``terminal_data_filename``。"""
    body = drive(monkeypatch, tmp_path, filenames=(DATASET,), endpoint=endpoint)

    assert payload_of(body, COMPLETION)["data"]["data_filename"] == done_frame(body)["data_filename"], (
        "同一轮在两枚终态上说出两份文件名：有人在第二处拼名字"
    )


@pytest.mark.parametrize("endpoint", ["ask", "approve"])
def test_the_no_answer_leg_still_names_the_file_it_read(monkeypatch, tmp_path, endpoint):
    """「这一轮没结论」与「这一轮没跑数据」是两件事：失败腿也照说算过哪份。"""
    frame = done_frame(drive(monkeypatch, tmp_path, filenames=(DATASET,), endpoint=endpoint, answer=""))

    assert frame["terminal_state"] == chat.TERMINAL_STATE_NO_ANSWER, frame
    assert frame["answer_present"] is False, frame
    assert frame["data_filename"] == DATASET, (
        "正文失败的那一腿把 dataset 读数一起吞了：那一轮确实算过这份文件"
    )


# ==================== 判据①形二：真没产出就整格缺席（另一枚形） ====================


def test_a_turn_that_computed_from_nothing_leaves_the_cell_absent(monkeypatch, tmp_path):
    """反证刀①③（补造 / 并脸）的家：补空串或塞一句假名字，本枚当场红。"""
    frame = done_frame(drive(monkeypatch, tmp_path, filenames=(), declared=""))

    assert cell(frame) is NO_CELL, (
        "这一轮真没跑数据，那一格必须整枚缺席，实际读到 " + repr(frame.get("data_filename"))
    )
    assert "data_filename" not in json.dumps(frame), "缺席就是键都不许在"


def test_a_multi_dataset_turn_refuses_to_name_one_file(monkeypatch, tmp_path):
    """在册函数说空串的两态（零枚 / 多枚），本单一律整格缺席，不并成第三张脸。"""
    body = drive(monkeypatch, tmp_path, filenames=(DATASET, OTHER_DATASET))
    frame = done_frame(body)

    assert chat.terminal_data_filename([DATASET, OTHER_DATASET]) == "", "在册口径复核"
    assert cell(frame) is NO_CELL, frame
    completed = payload_of(body, COMPLETION)["data"]
    assert completed["data_filename"] == "" and "data_filename" in completed, (
        "canonical 那一发是「键在位、值可为空串」，与本单的缺席不是同一句话"
    )


def test_the_two_shapes_are_not_the_same_face(monkeypatch, tmp_path):
    """键集合逐枚点名：两形只差那一格，其余一字不差。"""
    produced = done_frame(drive(monkeypatch, tmp_path, filenames=(DATASET,)))
    empty = done_frame(drive(monkeypatch, tmp_path, filenames=(), declared=""))

    assert set(produced) - set(empty) == {"data_filename"}, (sorted(produced), sorted(empty))
    assert set(empty) - set(produced) == set()
    assert set(empty) == {"type"} | SHARED_READOUT_KEYS, (
        "缺席那一形必须等于在册件按名钉住的那具键集合——否则改的就是那道钉"
    )
    assert set(produced) == {"type"} | SHARED_READOUT_KEYS | {"data_filename"}


def test_the_declared_field_never_becomes_the_answer(monkeypatch, tmp_path):
    """反手抄刀：声明 A、实际算 B，done 只能说 B；实际没算就一个字都不说。"""
    swapped = done_frame(drive(monkeypatch, tmp_path, filenames=(OTHER_DATASET,), declared=DATASET))
    silent = done_frame(drive(monkeypatch, tmp_path, filenames=(), declared=DATASET))

    assert swapped["data_filename"] == OTHER_DATASET, swapped
    assert cell(silent) is NO_CELL, "把调用方自己点名的那一份抄成服务端读数：请求方向顶了响应方向"


# ==================== 判据①：队列终态同一枚裁定（构造点 + /queue/status 投影） ====================


def test_the_queue_terminal_names_the_file_only_when_it_knows_one():
    produced = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True, dataset_files=[DATASET]
    )
    silent = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True
    )
    many = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED,
        answer_present=True,
        dataset_files=[DATASET, OTHER_DATASET],
    )

    assert produced["data_filename"] == DATASET, produced
    assert "data_filename" not in silent, sorted(silent)
    assert "data_filename" not in many, "说不清就不说：不许交一枚空串冒充某一枚"
    assert set(produced) - set(silent) == {"data_filename"}
    assert set(silent) == set(many), "零枚与多枚在载荷上是同一张「没这一格」的脸"


def test_the_pinned_queue_key_set_is_untouched_when_nothing_was_read():
    """在册钉复跑（本单未改那枚件）：没有读数时载荷仍等于钉着的那几格。"""
    payload = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True
    )

    assert SHARED_READOUT_KEYS <= set(payload)
    assert set(payload) - SHARED_READOUT_KEYS == {"schema", "worker_status", "scope_reason_code"}


def test_the_done_frame_without_a_readout_keeps_the_registered_key_set():
    """在册钉复跑（`test_r254_sync_lane_terminal:151` 的相等式）：本单一格都没往里塞空。"""
    frame = json.loads(chat.done_sse_frame(
        terminal_state=chat.TERMINAL_STATE_QUEUED,
        answer_present=False,
        sources_present=False,
    ).split("data: ", 1)[1].strip())

    assert set(frame) == {"type"} | SHARED_READOUT_KEYS, sorted(frame)
    assert "data_filename" not in frame


class _ReadOnlyQueue:
    """只喂 ``queue_terminal_readout`` 的两枚读法：result 与 terminal，别的一概不问。"""

    def __init__(self, terminal: dict):
        self._terminal = terminal

    def result(self, request_id):
        return ANSWER

    def terminal(self, request_id):
        return self._terminal


def _readout(payload, state=reliable_queue.TERMINAL_OK) -> dict:
    return chat.queue_terminal_readout(
        _ReadOnlyQueue({"state": state, "payload": payload}), "req-r504", {}, "done"
    )


def test_the_queue_readout_carries_the_cell_the_payload_actually_hands_over():
    payload = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True, dataset_files=[DATASET]
    )

    assert _readout(payload)["data_filename"] == DATASET, sorted(_readout(payload))


def test_the_queue_readout_stays_silent_when_the_payload_has_no_such_cell():
    """旧行（发布于本单之前）与真没跑数据的那一轮，都不许被补一枚空串洗成「说了空话」。"""
    without = chat.build_queue_terminal(
        terminal_state=chat.TERMINAL_STATE_ANSWERED, answer_present=True
    )

    assert "data_filename" not in _readout(without), sorted(_readout(without))
    assert "data_filename" not in _readout(None, state=reliable_queue.TERMINAL_ABSENT)
    assert "data_filename" not in _readout({"schema": "x"}, state=reliable_queue.TERMINAL_UNREADABLE)


# ==================== 判据③：AST 面证明没有第二处拼名字 ====================


def _tree() -> ast.Module:
    return ast.parse(Path(CHAT_PY).read_text(encoding="utf-8"))


def _walk(node, stack):
    yield node, stack
    for child in ast.iter_child_nodes(node):
        yield from _walk(child, stack + [node])


def _enclosing_name(stack) -> str:
    for item in reversed(stack):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return item.name
    return "<module>"


def _function(name: str):
    matches = [
        node for node in ast.walk(_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(matches) == 1, name + " 不见了或长出第二枚：" + repr([m.name for m in matches])
    return matches[0]


def _producers() -> list[dict]:
    """把每一处「把值交给 data_filename 这一格」的地方点名：字面键与下标赋值都算。"""
    found: list[dict] = []
    for node, stack in _walk(_tree(), []):
        func = _enclosing_name(stack)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "data_filename":
                    found.append({"func": func, "kind": "dict", "target": "", "value": value})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "data_filename"
                ):
                    found.append({
                        "func": func,
                        "kind": "subscript",
                        "target": ast.unparse(target.value),
                        "value": node.value,
                    })
    return found


def _from_registered(value) -> bool:
    return isinstance(value, ast.Call) and getattr(value.func, "id", "") == "terminal_data_filename"


def test_the_registered_function_is_defined_exactly_once_and_still_assembles_nothing():
    registered = ast.unparse(_function("terminal_data_filename"))

    assert "basename" not in registered and ".join(" not in registered, (
        "在册函数今天不拼名字，本单也不许让它开始拼"
    )
    assert "return dataset_files[0] if len(dataset_files) == 1 else" in registered, registered
    assert "else " + repr("") in registered or "else \"\"" in registered, registered


def test_every_terminal_value_for_the_cell_comes_from_the_one_registered_function():
    """在册的账一共五处：两枚 canonical 出口 + 挂载件 + 搬运件 + 喂图那一处（既有、请求方向）。"""
    producers = _producers()
    dicts = [p for p in producers if p["kind"] == "dict"]
    stores = [p for p in producers if p["kind"] == "subscript"]

    assert len(producers) == 5, (
        "把值交给 data_filename 的地方漂了：" + repr([(p["func"], p["kind"], p["target"]) for p in producers])
    )
    assert len(dicts) == 2 and all(_from_registered(p["value"]) for p in dicts), (
        "两枚 canonical 出口的取值必须直接走在册函数：" + repr([(p["func"], p["kind"]) for p in dicts])
    )
    assert sorted(p["func"] for p in dicts) == ["_approve_stream", "_ask_stream"], (
        "交这一格值的 canonical 出口换人了：" + repr(sorted(p["func"] for p in dicts))
    )
    assert sorted(p["target"] for p in stores) == ["payload", "readout", "user_ctx"], (
        "下标交值的地方只剩这三处：挂载件的 payload、/queue/status 的 readout、喂图的 user_ctx"
    )
    assert {p["func"] for p in stores} == {"attach_terminal_data_filename", "queue_terminal_readout", "ask"}, (
        "交值函数换人了：" + repr(sorted((p["func"], p["target"]) for p in stores))
    )
    for producer in producers:
        value = producer["value"]
        assert not isinstance(value, (ast.JoinedStr, ast.FormattedValue)), producer["func"] + " 用 f-string 造文件名"
        assert not isinstance(value, ast.BinOp), producer["func"] + " 用字符串拼接造文件名"


def test_the_request_direction_cell_stays_where_it_was():
    """``user_ctx["data_filename"] = request.data_filename`` 是既有那一处（请求方向，喂图用）。

    它今天仍然在场、仍然只交给图，本单没把它挪进任何一枚终态帧；若有人开始拿它填终态，
    本枚与 `test_the_declared_field_never_becomes_the_answer` 一起红。
    """
    request_side = [p for p in _producers() if "request.data_filename" in ast.unparse(p["value"])]

    assert len(request_side) == 1, [(p["func"], p["target"]) for p in request_side]
    assert request_side[0]["target"] == "user_ctx", request_side[0]["target"]
    assert request_side[0]["func"] == "ask", request_side[0]["func"]


def test_the_mount_helper_delegates_and_never_assembles():
    mount = _function("attach_terminal_data_filename")
    binds = [
        node.value for node in ast.walk(mount)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "data_filename" for t in node.targets)
    ]

    assert len(binds) == 1, binds
    assert isinstance(binds[0], ast.Call) and getattr(binds[0].func, "id", "") == "terminal_data_filename"
    dumped = ast.unparse(mount)
    assert "payload[" + chr(39) + "data_filename" + chr(39) + "] = data_filename" in dumped, dumped
    for banned in ("basename", ".join(", ".format("):
        assert banned not in dumped, "挂载件里出现了拼名字的手法：" + banned


def test_the_readout_projection_only_copies_the_payload_cell():
    projection = _function("queue_terminal_readout")
    binds = [
        node.value for node in ast.walk(projection)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "data_filename" for t in node.targets)
    ]

    assert len(binds) == 1, binds
    call = binds[0]
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "get"
    assert isinstance(call.func.value, ast.Name) and call.func.value.id == "data", "搬运件不许从载荷之外取这一格"
    assert call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == "data_filename"


def test_only_the_two_terminal_constructors_mount_the_cell():
    users = sorted(
        _enclosing_name(stack) for node, stack in _walk(_tree(), [])
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "attach_terminal_data_filename"
    )

    assert users == ["build_queue_terminal", "done_sse_frame"], users


def test_the_three_constructors_all_take_the_collector_sink():
    """签名面：三枚构造点都收同一枚 sink，而且都不许收一枚现成的名字。"""
    for name in ("done_sse_frame", "done_frame_for_turn", "build_queue_terminal"):
        arguments = _function(name).args
        given = [a.arg for a in list(arguments.kwonlyargs) + list(arguments.args)]
        assert "dataset_files" in given, name + " 的读数入口不见了：" + repr(given)
        assert "data_filename" not in given, name + " 不许收一枚现成的名字（那正是第二处拼名字的起点）"


def test_the_collector_is_still_the_only_dataset_sink_feeder():
    text = Path(CHAT_PY).read_text(encoding="utf-8")

    assert text.count("def _collect_dataset_filenames(") == 1
    assert text.count("_collect_dataset_filenames(agent_results, dataset_files)") == 2, (
        "dataset 取证点仍是 /ask 与 /approve 两枚，一枚不多一枚不少"
    )


# ==================== 判据④：零新错误码、零新增外部请求、零 Chroma ====================


#: 基点 `405cacb` 现取的 chat.py 错误码字面集（同一把尺量改前改后，不是抄派工词）。
ERROR_CODES_AT_BASELINE = frozenset({"internal_error", "no_answer_produced", "task_timeout"})


def test_the_change_added_no_error_code_no_chroma_and_no_new_exit():
    text = Path(CHAT_PY).read_text(encoding="utf-8")
    live = frozenset(re.findall(r'"error_code": "([a-z0-9_]+)"', text))

    assert live == ERROR_CODES_AT_BASELINE, (
        "错误码集合漂了，多出的：" + repr(sorted(live - ERROR_CODES_AT_BASELINE))
        + " 少掉的：" + repr(sorted(ERROR_CODES_AT_BASELINE - live))
    )
    assert "classification_blocked" not in text
    assert "chroma" not in text.lower(), "新代码不许新增 Chroma 依赖或写点"
    assert text.count("yield done_sse_frame(") == 3, "done 出口一枚都不许多，也一枚都不许少"
    assert text.count("yield done_frame_for_turn(") == 3
    assert text.count('"type": "done"') == 1, "done 载荷的键仍只许在唯一构造点里写一遍"


# ==================== 腿 3 取证：缓存命中那一腿今天到底交回什么（🔴 本单未治） ====================


def test_the_cache_hit_leg_hands_back_no_terminal_frame_at_all(monkeypatch, tmp_path):
    """钉现状用：命中道一条 canonical 终态都没有，屏上那一格因此无从接——本单不动它。"""
    from app.common import cache

    _patch_offline(monkeypatch, tmp_path, lambda *_a, **_k: iter([]), None)
    monkeypatch.setattr(cache, "get_cached_answer", lambda *_a, **_k: ANSWER)
    monkeypatch.setattr(cache, "answer_cache_origin", lambda *_a, **_k: {})
    monkeypatch.setattr(cache, "get_cached_answer_record", lambda *_a, **_k: None)

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message=DATA_QUESTION, session_id=SESSION_ID, data_filename=DATASET),
            http_request=_http_request(finance_principal()),
        )
    )
    body = asyncio.run(_consume(response))
    names = [line.removeprefix("event: ").strip() for line in body.splitlines() if line.startswith("event: ")]
    frame = done_frame(body)

    assert COMPLETION not in names, names
    assert names == ["status", "text", "done"], (
        "命中道今天只发 legacy 三帧；若它开始发 canonical，本枚取证钉要跟着改口并另案"
    )
    assert cell(frame) is NO_CELL, "命中轮的用表读数当年没有落账：本单不许在这一帧上补造"
    assert frame["sources_error"] == chat.SOURCES_ERROR_NO_MANIFEST, frame
    assert frame["terminal_state"] == chat.TERMINAL_STATE_ANSWERED, frame
