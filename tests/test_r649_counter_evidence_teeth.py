# -*- coding: utf-8 -*-
r"""R649 · 判据⑤ 的三把反证刀：刀下去必须红，而且红在**读数**上、点名到那一枚。

派工词 R649 第二节第 5 格点名的三形：

  刀 A 记录点搬到「第一个 token」那一侧（不是屏上那枚可见 text 帧）⇒ 结构面与线上读数两枚都红；
  刀 B 拿离线帧账那一形冒充线上读数（``scripts/eval_transport_ask_v2.py::_first_screen_reading``
       落在 ``*-frames.jsonl`` 里的 ``first_visible_ms``）⇒ 派生一枚数都不给，两形各归各的署名；
  刀 C blocker 摘掉而账里无数 —— 也就是「没有 blocker 也没有读数」那一族空绿 ⇒ 对账格红。

🔴 两枚尺子一律 import 主件（``tests/test_r649_first_screen_ms_is_measurable_on_the_wire.py``）：
``visible_frame_problems`` 与 ``frame_yield_record_points`` 是本单唯一的尺，刀这边不另造一套走法。
每把刀进门先跑正控：正控红了就说明是夹具哑了，不是刀赢了。

姿势（这一格的账要写清，因为它是本单唯一一处绕开在册装变异把手的地方）：变异只落影子副本
（``tests/_temp_edit_overlay.py`` 的在册骨架），活模块上只临时改绑派生点名的那一枚顶层函数、
出门按对象身份装回。本件因此**不**走 ``r466.install_mutation``：
``app/api/v1/chat.py::ask`` 头上挂着 ``@router.post``，整份码体重跑会把端点重复注册到活的 router 上，
而装变异那一腿真往活模块上落的那一族由 ``tests/test_r466_*`` 那本**派生**名册逐枚点名 —— 名册住在
别人的写域里，本单不自扩。按 ``tests/test_r583_window_inventory.py`` 的口径，本件落在
「只开窗、不装变异」那一族（派生读数会逐枚点名它，不会静默失踪）。

纪律同主件：不打模型、不起服务、不连库、不动容器、盘上文件全程只读。
"""
import ast
import copy
from contextlib import contextmanager

from app.api.v1 import chat, observability
from app.common.stage_timing import to_epoch_ms

from tests import test_r466_mutation_does_not_leak_into_live_module as r466
from tests.test_r48_headline_card_lands_on_the_wire import CHAT_PY, _TempEdit
from tests.test_r48_headline_never_enters_the_text_ledger import _crlf, _streamed_round
from tests.test_r649_first_screen_ms_is_measurable_on_the_wire import (
    EVENT_TYPE,
    OPEN_EVENT,
    VISIBLE_LEGS,
    _first_text_metric,
    frame_yield_record_points,
    mirrored_lifecycle,      # noqa: F401  -- 夹具按名借用，不抄第二份
    readback,
    text_frames,
    trace_book,              # noqa: F401
    trace_id_of,
    visible_frame_problems,
)
from tests.test_sse_sources import doc_state, drive, fake_retriever_hits, finance_principal

#: 本单摘掉的那一枚 blocker 的名字。刀 C 判的就是「它摘了、账里却无数」这一族空绿。
BLOCKER_CODE = "wire_first_text_not_recorded"
#: 记账点被搬去的那一侧：它不属于 ``VISIBLE_LEGS``，读回来必须被点名。
TOKEN_LEG = "token"
TRACE = "trace-r649-knife-b"


# ==================== piece 腿原文与「搬到 token 那一侧」的变异 ====================
#
# 锚点逐字取自盘上那一段（十六枚缩进、那两行注释一起抄），``_TempEdit`` 的锚点唯一性会替你盯着：
# 对不上或撞上第二处，窗当场报错而不是悄悄改掉别处。

PIECE_LEG_ANCHOR = "\n".join([
    '                piece_count += 1',
    '                frame_text = piece_stream.frame_for(data, latest_worker_results)',
    '                if frame_text is None:',
    '                    continue',
    '                cumulative_text = frame_text',
    '                # R649：``frame_for`` 交回帧才算「屏上多了一行」；上面那枚 ``continue`` 那一支',
    '                # 一个像素都没变，本单一个字都不记。',
    '                first_text_mark.note(cumulative_text, leg="piece")',
    '                yield text_sse_frame(cumulative_text, live_cache_fields)',
])
#: 病态那一形：片一到手就记账，折帧闸还没判过 —— 交不回帧的那一片也照样被记成「首屏」。
PIECE_LEG_TOKEN_MUTANT = "\n".join([
    '                piece_count += 1',
    '                first_text_mark.note(str(getattr(data, "text", "") or ""), leg="token")',
    '                frame_text = piece_stream.frame_for(data, latest_worker_results)',
    '                if frame_text is None:',
    '                    continue',
    '                cumulative_text = frame_text',
    '                yield text_sse_frame(cumulative_text, live_cache_fields)',
])


# ==================== 反证窗：影子副本落变异，活模块只临时改绑一枚名字 ====================


def _mutant_binding(text: str, name: str):
    """从变异源文里只编那一枚被点名的顶层函数，装饰器摘掉，码体挂回**活命名空间**。

    🔴 三件事都是这枚把手的本体，不是实现细节：
      · 只编被点名的那一枚：整份码体重跑会把 ``@router.post`` 再执行一遍，端点就在活的 router
        上长出第二份（本仓 R553 乙腿点名的正是这一族污染）；
      · 摘装饰器：FastAPI 那一枚路由装饰器交回的就是原函数，用例直接调函数，不需要也不许再注册一次；
      · 用 ``r466._rebase`` 把码体的命名空间挂回 ``vars(chat)``：这样窗内后来由夹具装上去的替身
        （``patch_offline`` 是在开窗**之后**才跑的）逐枚看得见，本件不必先把活模块改脏。
    """
    tree = ast.parse(text)
    target = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    target.decorator_list = []
    scratch: dict = dict(vars(chat))   # 形参标注在 def 那一刻就要求值，空字典会 NameError
    exec(compile(ast.unparse(target), str(CHAT_PY), "exec"), scratch)
    value = scratch[name]
    return r466._rebase(value, vars(chat), name)


@contextmanager
def _mutant_ask_window(edits):
    """开窗：影子副本改 ``ask`` 里那一段 -> 活模块临时改绑这一枚名字 -> 出门按身份装回。"""
    disk_text = CHAT_PY.read_bytes().decode("utf-8")
    original = chat.ask
    routes = len(chat.router.routes)
    with _TempEdit(CHAT_PY, edits) as info:
        shadow_text = info.read_text()
        changed, unmatched = r466.changed_bindings(disk_text, shadow_text)
        assert changed == ["ask"], (
            "这把刀没落在 ``ask`` 这一枚顶层绑定上（点名 %s，非绑定改动 %s）："
            "变异跑不到，刀就是死的" % (changed, unmatched[:1]))
        chat.ask = _mutant_binding(shadow_text, "ask")
        assert chat.ask is not original, "变异没换上活模块：这一轮量的还是原码"
        try:
            yield info
        finally:
            chat.ask = original
            assert chat.ask is original, "窗尾没把 ``ask`` 装回原来那一枚对象"
    assert len(chat.router.routes) == routes, (
        "端点在活的 router 上多长了 %d 枚：变异码体重跑过整份模块体" % (
            len(chat.router.routes) - routes,))
    assert info["restored"], "窗尾核对：被跟踪的 chat.py 没保持原样"
    assert CHAT_PY.read_bytes().decode("utf-8") == disk_text, "盘上的 chat.py 被窗改过"


# ==================== 刀 A：记录点搬到 token 那一侧 ====================


def test_counter_evidence_a_moving_the_record_point_to_the_token_side_goes_red(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    r"""结构面与线上读数**两枚都得红**，并且都点名到那一枚搬走的记账点。

    🔴 只红在守卫上不算数：这一把要的是「账里躺着的那一枚首屏读数确实不再是屏上第一枚正文帧」。
    """
    control = _streamed_round(monkeypatch, tmp_path)
    assert visible_frame_problems(trace_book, control) == [], visible_frame_problems(trace_book, control)
    found_control, problems_control = frame_yield_record_points(
        CHAT_PY.read_bytes().decode("utf-8"))
    assert problems_control == [], problems_control
    assert sorted({leg for _line, leg in found_control}) == list(VISIBLE_LEGS), found_control

    with _mutant_ask_window(
        [(_crlf(PIECE_LEG_ANCHOR), _crlf(PIECE_LEG_TOKEN_MUTANT))]
    ) as info:
        shadow_text = info.read_text()

        # —— 静态面：同一枚尺子读变异源文，问题清单必须非空且点名那一枚。
        found_mutant, problems_mutant = frame_yield_record_points(shadow_text)
        assert problems_mutant, "记账点搬到 token 那一侧，结构钉却还绿着：它量不到位置"
        assert any(TOKEN_LEG in problem for problem in problems_mutant), problems_mutant
        assert TOKEN_LEG in {leg for _line, leg in found_mutant}, found_mutant
        assert sorted({leg for _line, leg in found_mutant}) != list(VISIBLE_LEGS), found_mutant

        # —— 行为面：变异真跑一轮，账里那一枚首屏必须是 token 形，读回来红。
        body = _streamed_round(monkeypatch, tmp_path)
        assert text_frames(body), "变异把这一轮发帧都弄没了：量的不是记账点"
        trace = trace_id_of(body)
        rows = observability.wire_first_text_from_events(trace_book.replay(trace))
        assert rows, "变异没落账：这把刀没被执行，红是空的"
        assert rows[trace]["leg"] == TOKEN_LEG, rows[trace]

        problems_reading = visible_frame_problems(trace_book, body)
        assert problems_reading, "账里那枚 token 形读数被判成了合格的首屏：读尺哑了"
        assert any("腿" in problem for problem in problems_reading), problems_reading
        print("[r649 刀A] 变异读数=%r 红点=%s 结构面=%s" % (
            rows[trace], problems_reading, problems_mutant[:1]))


# ==================== 刀 B：离线帧账那一形不许冒充线上读数 ====================

#: ``*-frames.jsonl`` 里每一行都带着采集器自己的墙钟：``first_visible_ms`` 由
#: ``scripts/eval_transport_ask_v2.py::_first_screen_reading`` 从**帧账**里第一枚可见事件算出来。
#: 🔴 它既不是 ``app/trace/store.py::TraceStore.record_event`` 落下的那两枚戳，也不是本单那一枚
#: ``wire.first_text`` 事件 —— 派生认不出来就该一枚数都不给，而不是「看起来像个首屏数」。
OFFLINE_FRAME_ROW = {
    "question": "差旅报销上限是多少？",
    "elapsed_ms": 812.5,
    "first_visible_at": "2026-10-04T13:20:00.000+08:00",
    "first_visible_event": "render",
    "first_visible_ms": 260.0,
    "frames": [{"event": "text", "elapsed_ms": 260.0, "arrival_at": 0.26}],
}


def _open_and_wire_events(opened: str, landed: str) -> list[dict]:
    """线上那一形的两枚事件：起点与第一枚可见 text 帧，时刻都由账盖，纸上不填数。"""
    return [
        {"trace_id": TRACE, "event_type": OPEN_EVENT, "timestamp": opened, "sequence": 1,
         "payload": {}},
        {"trace_id": TRACE, "event_type": EVENT_TYPE, "timestamp": landed, "sequence": 2,
         "payload": {"leg": "piece", "visible_chars": 24}},
    ]


def test_counter_evidence_b_an_offline_frame_reading_cannot_pass_as_the_wire_number() -> None:
    r"""正控先立住（真戳对能算出数），再看离线形与洗过的离线形全部拿不到数。

    🔴 线上与离线两形分开署名：``measured_from`` 只可能写账本那一名，离线那本（
    ``app/api/v1/observability.py::SLO_SOURCE_LEDGER`` 那一族）永远顶不上这一格。
    """
    opened, landed = "2026-10-04T05:00:00.000000+00:00", "2026-10-04T05:00:00.420000+00:00"
    real = _open_and_wire_events(opened, landed)
    control = observability.wire_first_text_from_events(real)
    expected = to_epoch_ms(landed) - to_epoch_ms(opened)
    assert control and control[TRACE]["first_text_ms"] == expected, control
    assert observability.SLO_SOURCE_TRACE != observability.SLO_SOURCE_LEDGER

    # ① 离线帧账那一行直接喂进来：派生不到任何一枚样本，读回是具名的那一个原因。
    assert observability.wire_first_text_from_events([dict(OFFLINE_FRAME_ROW)]) == {}
    laundered = observability.wire_first_text_row([dict(OFFLINE_FRAME_ROW)], TRACE)
    assert laundered["status"] == observability.WIRE_FIRST_TEXT_NO_EVENT, laundered
    assert laundered["first_text_ms"] is None, "离线那一枚数被当成线上读数发了出去"
    assert laundered["measured_from"] == observability.SLO_SOURCE_TRACE, laundered
    assert laundered["leg"] == "" and laundered["visible_chars"] is None, laundered

    # ② 给它贴上 ``trace_id``、换上事件名，但时刻仍是采集器那枚墙钟：一样算不出数。
    pasted = dict(OFFLINE_FRAME_ROW)
    pasted["trace_id"] = TRACE
    pasted["event_type"] = EVENT_TYPE
    pasted["timestamp"] = pasted.pop("first_visible_ms")
    assert observability.wire_first_text_from_events(
        [dict(pasted, trace_id=TRACE, event_type=OPEN_EVENT, timestamp="2026-10-04T05:00:00+00:00"),
         pasted]) == {}, "把离线毫秒贴到事件名上就能冒领线上读数：派生没在认戳"

    # ③ 往真事件上塞一枚假 ``first_text_ms`` / ``elapsed_ms``：读数只随那两枚戳动。
    tampered = copy.deepcopy(real)
    tampered[1]["first_text_ms"] = 9_999_999.0
    tampered[1]["payload"]["elapsed_ms"] = 9_999_999.0
    assert observability.wire_first_text_from_events(tampered) == control, (
        "账里多写一枚数就能顶掉由戳派生的那一枚：同一件事有了第二本账")

    # ④ 模型侧那本账（第一个 token）不是首屏：``first_token_not_a_stage_sample`` 说的就是它。
    model_side = [
        {"trace_id": TRACE, "event_type": OPEN_EVENT, "timestamp": opened, "sequence": 1,
         "payload": {}},
        {"trace_id": TRACE, "event_type": "model.finished", "timestamp": landed, "sequence": 2,
         "payload": {"first_token_at": landed}},
    ]
    assert observability.wire_first_text_from_events(model_side) == {}, (
        "模型侧的第一个 token 被认成了屏上第一行")
    print("[r649 刀B] 线上=%r 离线读回=%s" % (control[TRACE], laundered["status"]))


# ==================== 刀 C：blocker 摘了而账里无数（空绿那一族）====================


def first_text_bookkeeping_problems(*, blockers, events) -> list[str]:
    r"""blocker 的账与账里的数必须同日兑现：两种分家都点名。

    摘 ``wire_first_text_not_recorded`` 的凭据是「真发帧形状读得到非 None」，不是「有人写了这一格」。
    🔴 反过来更危险：blocker 摸掉了、账里一枚读数都没有 —— 那就是本仓记过一整族的空绿。
    """
    rows = observability.wire_first_text_from_events(events)
    blocking = BLOCKER_CODE in set(blockers)
    problems: list[str] = []
    if blocking and rows:
        problems.append("过期账：%s 还挂着，账里却已经有 %d 枚读数" % (
            BLOCKER_CODE, len(rows)))
    if not blocking and not rows:
        problems.append("空绿：%s 摘了，账里一枚读数都没有（没有 blocker 也没有读数）" % (
            BLOCKER_CODE,))
    return problems


def test_the_blocker_book_and_the_book_stay_in_step_together(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """刀 C 的正控：活码上 blocker 已摘、账里有数，对账格交回空清单。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    events = trace_book.replay(trace_id_of(body))
    blockers = list(_first_text_metric().blockers)
    assert BLOCKER_CODE not in blockers, blockers
    assert first_text_bookkeeping_problems(blockers=blockers, events=events) == [], events
    assert readback(trace_book, body)["first_text_ms"] is not None


def test_counter_evidence_c_dropping_the_blocker_without_a_number_goes_red(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """刀 C：把记账出口掐掉（记录点没落地）而 blocker 已摘 ⇒ 对账格红，并且点名空绿。"""
    monkeypatch.setattr(chat, "_record_wire_first_text", lambda **_kwargs: None)
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    block = readback(trace_book, body)
    assert block["status"] == observability.WIRE_FIRST_TEXT_NO_EVENT, block
    assert block["first_text_ms"] is None, "账里明明无数，读回却敢交一枚数"
    problems = first_text_bookkeeping_problems(
        blockers=list(_first_text_metric().blockers),
        events=trace_book.replay(trace_id_of(body)),
    )
    assert problems, "掐掉记账出口以后 blocker 摘了也没人喊：这一格就是空绿"
    assert any("空绿" in problem for problem in problems), problems
    print("[r649 刀C] 红点=%s" % (problems,))


def test_counter_evidence_c2_a_number_under_a_still_hanging_blocker_is_a_stale_book(
    trace_book, mirrored_lifecycle, monkeypatch, tmp_path
):
    """刀 C 的另一半：账里有数、blocker 却还挂着 ⇒ 同一枚对账格红，点名「过期账」。"""
    body = drive(monkeypatch, tmp_path, [doc_state(fake_retriever_hits())], finance_principal())
    events = trace_book.replay(trace_id_of(body))
    assert observability.wire_first_text_from_events(events), events
    problems = first_text_bookkeeping_problems(
        blockers=[BLOCKER_CODE] + list(_first_text_metric().blockers), events=events)
    assert problems and any("过期账" in problem for problem in problems), problems