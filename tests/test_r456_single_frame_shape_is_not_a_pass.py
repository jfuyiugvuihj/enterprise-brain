"""R456 判据②(a)(b)：把「整轮只发一片 text」这枚形状钉在评分器自己那把尺上。

病灶（`docs/testing/run9-readout-2026-09-28.md` 的 A② 那一格）：缺字那半全绿
（``missing_chars>0``＝0／105），事件数那半不过（``text_frames>1``＝94／105）。九枚单片题号
``doc-07 chat-03 chat-06 chat-09 chat-10 metric-16 approval-06 scope-01 data-09``。

本文件不改一码一屏，只做一件事：把这枚形状**离线复现**（TestClient 打真路由 ＋ 一枚不碰
片段出口的假流驱动器），再用**在册量具自己那把尺**（`scripts/eval_transport_ask_v2.py` 的
``_consume`` / ``_fold_frames`` / ``_frame_readings`` / ``_frame_verdict``，importlib 单独加载，
一个字不改）判它一次，钉住三句话：

1. 整轮只发一片 text 时判据② **必须读成不过**（``_frame_verdict`` 回 False）。收端是逐帧
   计数的（``_count_text_frame`` 每帧 ``+= 1``，既不去重也不折叠），所以「一片」说的是后端
   只 yield 了一次（`app/api/v1/chat.py` 收尾那枚 ``text_sse_frame``），不是读法把帧吞了。
2. 同一枚断言、同一把尺，只把驱动器改成逐片发就转绿 ⇒ 红的是形状，不是运气。
3. 同一枚短答案逐片发读绿、整段发读红 ⇒ 红也不是正文长度逼出来的（run9 边界对照：
   ``chart-01`` 16 字发 2 片、``data-03`` 63 字发 5 片、``doc-07`` 69 字发 1 片）。

离线驱动沿用 `tests/test_approve_canonical_events.py` 那套假编排＋临时会话注册表：
一发模型都不打、一个端口都不开、不碰真实 Chroma。
"""
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

from langchain_core.messages import AIMessage

from app.agents import nodes
from app.storage.sessions import SessionRegistry
from tests.test_approve_canonical_events import _patch_offline

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r456_frame_ruler", _ROOT / "scripts" / "eval_transport_ask_v2.py"
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

SESSION_ID = "r456-single-frame"
QUESTION = "出差补助按自然日还是工作日计发？"  # run9 doc-07 的原题

#: run9 那九枚单片的正文形状：话是模型自己写的（``app/**`` 源码里这几句零命中，见下面那枚
#: 前提钉），图交回的是**一份已经写好的终答**，全程没有一枚片进过本轮注册的片段出口。
SUPERVISOR_PROSE = (
    "根据对话历史，这个问题已经回答过了：\n\n"
    "## 出差补助按自然日计发\n\n"
    "出差期间伙食补助按自然日计算，标准为 100 元每天。"
)
#: 边界对照用的短答案（run9 chart-01 是 16 字那一档）：短，但逐片发就读得出多帧。
SHORT_ANSWER = "柱状图已生成，可以直接下载。"


def _increments(text_: str, parts: int) -> list[str]:
    """把一整段字切成**非空**增量：拼回去逐字等于原段，一枚空增量都不留。

    第一版这里手抄了四段切片，最后一段是空串，于是"片数"与"帧数"的账差了一枚。
    """
    step = max(1, len(text_) // parts)
    return [chunk for chunk in (text_[i:i + step] for i in range(0, len(text_), step)) if chunk]


#: 同一份字逐片发时的增量：拼回去逐字等于上面那一整段。
INCREMENTS = _increments(SUPERVISOR_PROSE, 4)
SHORT_INCREMENT_TAIL = _increments(SHORT_ANSWER, 3)


# ------------------------------------------------------------------ 假流驱动器


def _piece(text: str):
    """真 ``StreamPiece``：收端 ``_AnswerPieceStream.frame_for`` 认的就是这个形状。"""
    now = time.monotonic()
    return nodes.StreamPiece(
        text=text, start_at=now - 0.01, end_at=now, source_fragments=len(text), emitted_at=now
    )


def one_shot_supervisor_stream(*_args, **_kwargs):
    """整轮只发一片 text 的那条腿：终答是**写好了交回来**的，片段出口一个字都没响。

    复刻的是 run9 九枚里的八枚：``worker_results`` 为空、``final_answer`` 非空。图里交回
    这一发的是 supervisor 自己（``app/agents/orchestrator.py`` 的 ``main_agent_node``：那一发
    ``main_model.invoke([sys_msg, current_user_msg])`` 不带 ``config``），摘不到本轮的片段出口，
    于是 ``chat`` 收尾那枚 ``text_sse_frame`` 成为这一轮唯一的一枚 text 帧。
    """
    yield {
        "messages": [AIMessage(content=SUPERVISOR_PROSE)],
        "worker_results": {},
        "final_answer": SUPERVISOR_PROSE,
    }


def piece_by_piece_stream(*args, **kwargs):
    """同一份字，改成逐片发：先把手里的增量交给本轮注册的片段出口，再交终答。"""
    sink = kwargs.get("stream_piece_sink")
    if sink is not None:
        for part in INCREMENTS:
            sink(_piece(part))
    yield from one_shot_supervisor_stream(*args, **kwargs)


def short_answer_streams_pieces(*_args, **kwargs):
    """边界对照：正文只有 16 字，但它是逐片发出来的。"""
    sink = kwargs.get("stream_piece_sink")
    if sink is not None:
        for part in SHORT_INCREMENT_TAIL:
            sink(_piece(part))
    yield {
        "messages": [AIMessage(content=SHORT_ANSWER)],
        "worker_results": {},
        "final_answer": SHORT_ANSWER,
    }


def short_answer_whole_stream(*_args, **_kwargs):
    """同一枚短答案整段交回、不碰片段出口：与上面那枚只差「有没有逐片发」这一件事。"""
    yield {
        "messages": [AIMessage(content=SHORT_ANSWER)],
        "worker_results": {},
        "final_answer": SHORT_ANSWER,
    }


# ------------------------------------------------------------------ TestClient 真路由


def ask_body(monkeypatch, tmp_path, stream, *, session_id: str = SESSION_ID,
             message: str = QUESTION) -> str:
    """把 /api/v1/ask 挂到假编排上，经 TestClient（进程内 ASGI，不开真端口）取整条 SSE 字面。"""
    from fastapi.testclient import TestClient

    from app.agents.contracts import Principal
    from app.common.auth import create_token, get_user
    from app.main import app

    chat = _patch_offline(monkeypatch, tmp_path, stream, None)
    assert get_user("admin"), "夹具要用的 admin 必须能离线解析出来"
    # _patch_offline 把会话绑给了 r55 那位财务员工，而这里带的是 admin 的 token：归属不一致
    # 会被 /ask 的 bind 判成 403。换一具空的注册表，让路由自己按 token 绑这一轮。
    registry = SessionRegistry(tmp_path / "r456-sessions.json")
    registry.bind(session_id, Principal.from_user(get_user("admin")))
    chat.session_registry = registry

    client = TestClient(app)
    response = client.post(
        "/api/v1/ask",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"message": message, "session_id": session_id},
    )
    assert response.status_code == 200, response.text
    return response.text


# ------------------------------------------------------------------ 读数：只用那一把尺


def _event_names(body: str) -> list[str]:
    return [
        frame.split("\n", 1)[0].removeprefix("event: ")
        for frame in body.split("\n\n")
        if frame
    ]


def _text_payloads(body: str) -> list[dict]:
    return [
        json.loads(frame.split("data: ", 1)[1])
        for frame in body.split("\n\n")
        if frame.startswith("event: text")
    ]


def read_with_registered_ruler(body: str) -> tuple[dict, dict]:
    """把一条 SSE 字面喂给在册量具自己那把尺，交回（观测桶，判据② 的读数）。🔴 不复算第二套。"""
    out = ruler._blank_observation(SESSION_ID)
    lines = iter([chunk.encode("utf-8") for chunk in body.splitlines(keepends=True)])
    ruler._consume(lines, out)
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return out, ruler._frame_readings(ledger, out["answer"])


def assert_criterion_two_matches_the_frame_shape(body: str, expected_holds: bool) -> dict:
    """两枚驱动器共用这一枚断言：判据② 的读法必须与**这一轮的帧形**同进同退。"""
    _out, readings = read_with_registered_ruler(body)
    verdict = ruler._frame_verdict(readings)
    assert verdict is expected_holds, (
        f"判据② 在 text_frames={readings['text_frames']} "
        f"max_stream_frames={readings['max_stream_frames']} 这一枚形状上读成 {verdict}，"
        f"而形状要求的读数是 {expected_holds}"
    )
    if readings["text_frames"] <= 1:
        assert verdict is False, f"单帧／空读被判成了通过：{readings}"
    return readings


# ------------------------------------------------------------------ 判据②(a) 单片形状


def test_the_untapped_round_issues_exactly_one_text_frame(monkeypatch, tmp_path):
    """形状复现：片段出口一个字都没响的那一轮，整条流里只许出现一枚 ``event: text``。"""
    body = ask_body(monkeypatch, tmp_path, one_shot_supervisor_stream)
    names = Counter(_event_names(body))

    assert names["text"] == 1, f"整轮只发一片 text 的形状没复现出来：{dict(names)}"
    assert names["request.started"] == 1, (
        "这一轮没有 request.started——那不是未命中的实时腿：缓存命中腿不发 canonical，"
        "拿它当单片形状的复现就是把另一条腿的账记到这条腿上"
    )
    assert "request.completed" in names and "sources" in names and "done" in names, dict(names)
    assert "error" not in names and "request.failed" not in names, dict(names)
    assert [payload["content"] for payload in _text_payloads(body)] == [SUPERVISOR_PROSE]


def test_the_single_frame_round_is_read_as_a_fail_under_criterion_two(monkeypatch, tmp_path):
    """判据②(a)：这枚钉当场红——单片那一轮的 ``criterion_two_holds`` 必须是 False。"""
    body = ask_body(monkeypatch, tmp_path, one_shot_supervisor_stream)
    _out, readings = read_with_registered_ruler(body)

    assert readings["text_frames"] == 1, readings
    assert readings["max_stream_frames"] == 1, readings
    assert readings["streams"] == 1, readings
    # 缺字那一半全绿：run9 的 105 枚里 missing_chars>0 一枚都没有，这九枚也一样
    assert readings["missing_chars"] == 0, readings
    assert readings["extra_chars"] == 0, readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert readings["prefix_breaks"] == 0, readings
    # 红的是事件数那一半
    assert_criterion_two_matches_the_frame_shape(body, expected_holds=False)


def test_the_text_frame_of_a_single_frame_round_lands_at_the_very_end(monkeypatch, tmp_path):
    """员工看到的是「转圈到最后一次性砸出全文」：唯一的 text 帧紧跟 request.completed。"""
    body = ask_body(monkeypatch, tmp_path, one_shot_supervisor_stream)
    names = _event_names(body)

    assert names.index("text") + 1 == names.index("request.completed"), names
    assert names.count("text") == 1, names


def test_the_driven_shape_carries_the_bytes_the_route_actually_returned(monkeypatch, tmp_path):
    """自证这枚钉喂给尺的是**路由真交回的字节**：末帧逐字等于驱动器里那一段终答。"""
    body = ask_body(monkeypatch, tmp_path, one_shot_supervisor_stream)
    out, readings = read_with_registered_ruler(body)

    assert out["answer"] == SUPERVISOR_PROSE, out["answer"][:40]
    assert readings["answer_sha"] == ruler._sha12(SUPERVISOR_PROSE), readings
    assert readings["last_frame_sha"] == readings["answer_sha"], readings


# ------------------------------------------------------------------ 判据②(b) 反证


def test_the_same_pin_turns_green_when_the_driver_publishes_pieces(monkeypatch, tmp_path):
    """反证：只换驱动器（逐片发），同一枚断言在同一把尺上转绿 ⇒ 咬的是形状不是运气。"""
    body = ask_body(monkeypatch, tmp_path, piece_by_piece_stream)
    readings = assert_criterion_two_matches_the_frame_shape(body, expected_holds=True)

    assert readings["text_frames"] == len(INCREMENTS) + 1, readings
    assert readings["max_stream_frames"] == len(INCREMENTS) + 1, readings
    assert readings["prefix_breaks"] == 0, readings
    assert readings["missing_chars"] == 0, readings
    assert readings["extra_chars"] == 0, readings
    contents = [payload["content"] for payload in _text_payloads(body)]
    assert contents[-1] == SUPERVISOR_PROSE, contents
    assert all(current.startswith(previous)
               for previous, current in zip(contents, contents[1:])), contents


def test_the_frame_count_is_not_bought_with_the_answer_length(monkeypatch, tmp_path):
    """长度解耦：同一枚 16 字短答案，逐片发读绿、整段发读红——单片不是答案短逼出来的。

    run9 的边界对照正是这两端：``chart-01`` 16 字发 2 片、``data-03`` 63 字发 5 片、
    ``doc-07`` 69 字发 1 片。正文长短与判据② 的读数之间没有因果关系，帧数才有。
    """
    assert len(SHORT_ANSWER) <= 16, "对照用的答案就得短，否则这条钉在自说自话"
    streamed = ask_body(monkeypatch, tmp_path, short_answer_streams_pieces,
                        session_id=SESSION_ID + "-short")
    assert_criterion_two_matches_the_frame_shape(streamed, expected_holds=True)

    whole = ask_body(monkeypatch, tmp_path, short_answer_whole_stream,
                     session_id=SESSION_ID + "-whole")
    readings = assert_criterion_two_matches_the_frame_shape(whole, expected_holds=False)
    assert readings["text_frames"] == 1, readings


# ------------------------------------------------------------------ 这枚钉咬的是哪一层


def test_the_increment_fixtures_reassemble_without_a_stray_char():
    """这枚钉的前提：增量拼回去逐字等于终答，且每一枚非空——否则帧数账就不成立。"""
    for answer, chunks in ((SUPERVISOR_PROSE, INCREMENTS), (SHORT_ANSWER, SHORT_INCREMENT_TAIL)):
        assert chunks, chunks
        assert all(chunk for chunk in chunks), chunks
        assert "".join(chunks) == answer
        assert len(chunks) >= 3, chunks


def test_the_ruler_counts_every_frame_it_receives_and_collapses_nothing():
    """收端读法不是这九枚单片的成因：尺对帧字面是**逐枚计数**的。

    同一把尺喂两枚累计帧与喂一枚累计帧，读数必须是 2 与 1——它不折叠、不去重，
    所以 ``text_frames=1`` 只能来自后端只 yield 了一次。
    """
    def count(frames: list[str]) -> int:
        out = ruler._blank_observation("unit")
        body = "".join(
            "event: text\ndata: "
            + json.dumps({"type": "text", "content": frame}, ensure_ascii=False)
            + "\n\n"
            for frame in frames
        )
        lines = iter([chunk.encode("utf-8") for chunk in body.splitlines(keepends=True)])
        ruler._consume(lines, out)
        return int(out["text_frames"])

    assert count([INCREMENTS[0], SUPERVISOR_PROSE]) == 2
    assert count([SUPERVISOR_PROSE]) == 1
    assert count([]) == 0, "一帧都没有时读的是空读，不许读成 1"


def test_the_prose_this_pin_drives_is_not_a_short_circuit_baked_in_the_code():
    """「根据对话历史……已经回答过了」不在 ``app/**`` 源码里：话是模型自己写的。

    这是本单归因的前提——若它是代码里的一枚短路腿，就不该按生成腿归因。零命中不是判据，
    所以这里把**查的是哪一层**写进断言，并同时交一枚**正向自证**：同一把尺在
    ``docs/testing/answers-run9.jsonl``（在册产物，模型交回的那一份字）里必须捞出这句话。
    那边捞得到、而 ``app/**`` 捞不到，「不是代码写的」这句才站得住。
    """
    corpus = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((_ROOT / "app").rglob("*.py"))
    )
    answers = (_ROOT / "docs" / "testing" / "answers-run9.jsonl").read_text(
        encoding="utf-8", errors="replace"
    )
    phrases = ("根据对话历史", "已经回答过了", "根据历史对话记录")

    for phrase in phrases:
        assert phrase not in corpus, f"{phrase} 出现在 app/** 源码里，本单归因前提要重查"
    assert [phrase for phrase in phrases if phrase in answers], (
        "正向自证落空：这句话在 answers-run9 里也找不到，那上面那条 app/** 零命中就没资格当判据"
    )