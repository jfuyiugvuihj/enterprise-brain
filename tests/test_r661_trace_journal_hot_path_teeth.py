# -*- coding: utf-8 -*-
"""R661 常驻牙：trace 事件件的体量不许站在 SSE 逐片直发的临界路径上。

对着的病（10-05 总控现取，本席在同一套影子机械里逐档复核）：
``tests/test_r149_sse_text_pieces.py::test_piece_frames_reach_the_wire_while_the_run_is_still_open``
只在主树红、影子树全绿，两边同一个 sha ``8a52c5c``，差别只有 ``data/traces/events.jsonl`` 的体量
（主树 32,038,850 B／影子 24,498 B）。红句「片被攒成一坨同时发出：[0.0, 0.421, 0.5]」，断言形状
是 ``min(gaps) >= 0.4``。

病根具名：**不是**「每片同步重写全件」，是「每一枚事件取号前全量扫件」。
``app/trace/store.py::TraceStore._file_sequence_floor`` 原先把整本 append-only 事件件
``read_text`` + 逐行 ``json.loads`` 读一遍，只为了答一句「这本件替这条 trace 发到过几号」；
而 ``record_event`` 对**每一枚**事件都要问这一句（``_next_sequence``），客户等的第一枚可见 text 帧
正走在 ``app/api/v1/chat.py::_FirstVisibleTextMark.note`` -> ``_record_wire_first_text`` ->
``record_event`` 这条道上。改前现读（同进程四档，原始数在 ``docs/testing/r661-trace-hot-path-2026-10-05.md``）：
0 B 0.108 ms、1 MB 12.503 ms、8 MB 75.356 ms、32 MB 501.842 ms —— 每 MB 约 15.7 ms，线性，
而且落在帧与帧之间，所以症状是「片追上片、一坨同时到」。

修成不随体量长：``_file_sequence_floor`` 改由 ``_fold_journal_floors`` 按**字节游标**增量折叠
（一次 ``stat`` + 自上次折叠以来新增的那几枚字节），新开一本 store 首眼只读件尾常量窗口
``JOURNAL_FLOOR_SEED_BYTES``（1 MiB）。``max(pg, file) + 1`` 这条规则一个字没改，读路径
（``_journal_records`` 的 strict 那一侧）也一个字没改。

十一枚在册牙 + 三道静态闸，十把刀逐枚点名 victim（每把先跑正控 ``edits=()`` 必须先绿）：
  临界路径  A ``test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces``
            B ``test_taking_a_number_costs_the_same_at_one_megabyte_and_at_twenty_four``
            I ``test_the_number_taking_leg_reaches_no_whole_journal_reader``（AST）
  落盘语义  C ``test_a_fresh_store_continues_the_numbers_the_journal_already_handed_out``
            D ``test_the_floor_folds_a_line_another_writer_appended_after_the_first_look``
            E ``test_a_line_still_being_written_is_counted_once_it_is_whole``
            F ``test_a_receipt_line_hands_out_no_number``
            G ``test_a_torn_line_does_not_stop_the_write_path``
            H ``test_the_read_path_still_raises_on_a_torn_line``
  合格线    J ``test_the_shipped_wire_bar_is_still_the_shipped_bar``（``min(gaps) >= 0.4`` 一字未放宽）
            以及 ``test_the_fold_never_touches_the_worktree_journal``（本域一字节都不许落进仓内事件件）

十把刀（逐枚原文锚点；锚点漂了 ``test_every_blade_anchor_hits_exactly_once`` 当场红）：
  K1 把取号那一格改回「读整本再挑最大号」（工单点名的病形本体）
     victim：A —— 24,000 枚事件件在场时片被攒成一坨，红在 ``min(gaps)`` 那道线上
  K2 首眼把种子窗口放大到「整本都读」（一件都不落下的另一种错法）
     victim：B —— 24 MB 的取号价变成 1 MiB 的十几倍，平性当场破
  K3 首眼之后再也不读这本件（只在内存里记自己发过的号）
     victim：D —— 另一个写者追加的行进不了 floor，同一枚号发两次
  K4 游标连半行一起推进（跨两次追加才写完的那枚行被永久跳过）
     victim：E —— 行写完也算没看见
  K5 首眼从 EOF 起算，已落盘的行一概不看
     victim：C —— 新开的一本从 1 重发，撞掉这本件已经发出去的号
  K6 收据行也拿来发号
     victim：F —— 与 ``_journal_records`` 对 receipt 的裁定分家
  K7 坏行在写路径上照抛
     victim：G —— 一件读不懂的行把整轮记账拦死
  K8 把读路径缺省改成 tolerant（R257 那半格被本单摸绿）
     victim：H —— ``replay`` 撞上坏行不抛了：静默少读
  K9 与 K1 同一处改动，但只喂给静态闸的取材口
     victim：I —— 取号那条腿够到了全量读件者
  K10 把 shipped 那一格的合格线改宽（0.4 改成 0.1）
     victim：J —— 线被摸宽这件事本身要红

影子纪律（照 ``tests/test_r545_counter_evidence_teeth.py`` 并树 ``48cc956`` 与
``tests/test_r655_no_stale_fact_teeth.py`` 并树 ``193f65e``）：源文从盘上读进字符串、归一 LF、改、
写进 pytest 的 ``tmp_path`` 留痕、compile 成另一枚模块，仓内那枚 ``app/trace/store.py`` 一个字节都不动；
影子模块的 ``__file__`` 指回真仓那枚源文；``sys.modules["app.trace.store"]`` 一并换成影子，因为
``app/api/v1/chat.py::_record_wire_first_text`` 是**调用期**才 import 那本账的，不换它病形进不了这一轮。
全程离线：不打模型、不开端口、不起服务、不动容器、不连 PG，也不往仓内 ``data/traces/**`` 落一枚字节
（每一枚事件件都造在 ``tmp_path`` 里，``TRACE_STORE_PATH`` 改道，跑完由 pytest 收走）。

跑法：
    .venv/Scripts/python.exe -m pytest -p no:randomly -q tests/test_r661_trace_journal_hot_path_teeth.py
"""
from __future__ import annotations

import ast
import contextlib
import json
import re
import app.trace.store as store_module
import shutil
import statistics
import sys
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tests.test_r149_sse_text_pieces as r149
import tests.test_r655_no_stale_fact_teeth as stale_gates
from app.trace.store import BACKFILL_RECEIPT_MARKER, FALLBACK_LINE_MARKER

THIS = sys.modules[__name__]
REPO = Path(__file__).resolve().parents[1]
STORE_REL = "app/trace/store.py"
OWN_REL = "tests/test_r661_trace_journal_hot_path_teeth.py"
R149_REL = "tests/test_r149_sse_text_pieces.py"

#: 路径形状的字面：带分隔符、不含空格与散文的一枚相对路径。散文里提一句 data/traces 不算落点。
_PATH_SHAPE = re.compile(r"[\w.\-]+(?:/[\w.\-]+)+")

#: 本牙站的体量。现读到的跨线点在 8,000 枚（病形 min(gaps)=0.390，已经红），24,000 枚时病形
#: 掉到 0.187（合格线的一半）而修复后同一档读到 0.485 —— 牙要咬在「红得没有歧义」的位置，
#: 不是压在跨线点上。原始数在凭据纸。
R661_JOURNAL_EVENTS = 24_000
MEASURED_CROSSING_EVENTS = 8_000
#: B 那把尺的低档：725 B/行（真件实测 32,038,850 B / 44,143 行）下的 1 MiB。
BASELINE_JOURNAL_EVENTS = 1_448
#: 平性判据：高档不许超过低档的这么多倍再外加这一截常数（低档自己就是那枚种子窗口的价）。
FLATNESS_RATIO = 3.0
FLATNESS_SLACK_SECONDS = 0.02
#: 与 shipped 那一格同一道线：这一枚牙不许比它宽，也不许借它之名另开一道尺。
HOLD_SECONDS = 0.5
MIN_GAP_FLOOR = 0.4
MAX_GAP_CEILING = HOLD_SECONDS + 1.0
#: 取号那条腿 = 发一枚事件之前必须走完的那几步。整本扫件的旧病就住在这里；结算清扫
#: （``maybe_backfill_fallback_journal`` 那一腿）今天也还在全量读件，那是另一格账，
#: 本件不把它折成零，也不拿它当这一枚闸的判据——见凭据纸「留给下一格」。
NUMBER_TAKING_LEG = ("_next_sequence",)
WHOLE_JOURNAL_READERS = frozenset({"_read_events", "_journal_records"})
#: 在册格名册：少一枚本件当场红（同族病：牙被悄悄搬走比牙红更难查）。
SHIPPED_CELLS = (
    "test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces",
    "test_taking_a_number_costs_the_same_at_one_megabyte_and_at_twenty_four",
    "test_the_number_taking_leg_reaches_no_whole_journal_reader",
    "test_a_fresh_store_continues_the_numbers_the_journal_already_handed_out",
    "test_the_floor_folds_a_line_another_writer_appended_after_the_first_look",
    "test_a_line_still_being_written_is_counted_once_it_is_whole",
    "test_a_receipt_line_hands_out_no_number",
    "test_a_torn_line_does_not_stop_the_write_path",
    "test_the_read_path_still_raises_on_a_torn_line",
    "test_the_shipped_wire_bar_is_still_the_shipped_bar",
    "test_the_fold_never_touches_the_worktree_journal",
)
#: 没有刀的一枚：它把「自己的前提」写在体内（改道落点 + 全文只有一处拿默认账本），
#: 其余每一枚都有方向明确的 victim，不许出现「两把刀守同一格、另一格没人守」。
UNKNIFED_CELLS = ("test_the_fold_never_touches_the_worktree_journal",)
DOMAIN_FILES = (STORE_REL, "tests/test_r661_trace_journal_hot_path_teeth.py")


# ==================== 取材与影子机械 ====================


def _text(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _store_source_text() -> str:
    """静态闸与影子唯一的取材口：刀只落在这枚函数的返回值上，仓内字节一个都不动。"""
    return _text(STORE_REL)


def _shipped_wire_text() -> str:
    """shipped 那一格的取材口：K10 把「合格线被改宽」喂到这里，J 当场红。"""
    return _text(R149_REL)


def _apply(text: str, edits) -> str:
    out = text
    for old, new in edits:
        if out.count(old) != 1:
            raise AssertionError(
                "刀口没落在唯一一处：%r（命中 %d 枚）" % (old[:56], out.count(old))
            )
        out = out.replace(old, new, 1)
    return out


def _shadow_store(source_text: str, where: Path, knife: str) -> types.ModuleType:
    """影子源文落 tmp_path 留痕 → compile → exec 成另一枚模块；``__file__`` 指回真仓。"""
    where.mkdir(parents=True, exist_ok=True)
    path = where / ("r661_shadow_store_%s.py" % knife)
    assert REPO not in path.resolve().parents, "影子不落 tmp_path 就要写回仓了"
    path.write_text(source_text, encoding="utf-8")
    name = "r661_mutant_store_" + knife
    module = types.ModuleType(name)
    module.__file__ = str(REPO / STORE_REL)
    sys.modules[name] = module
    exec(compile(source_text, str(path), "exec"), module.__dict__)
    return module


def _arm(knife: str, tmp_path: Path, monkeypatch, *, bite: bool) -> None:
    """装刀：影子刀换掉在册格看见的那本账，形状刀只换取材口；``bite=False`` 就是正控。"""
    spec = KNIVES[knife]
    edits = spec["edits"] if bite else ()
    mutated = _apply(_text(spec.get("target", STORE_REL)), edits)
    if spec["mode"] == "shape":
        monkeypatch.setattr(THIS, spec["seam"], lambda: mutated)
        return
    shadow = _shadow_store(mutated, tmp_path, knife)
    monkeypatch.setattr(THIS, "store_module", shadow)
    # chat.py 是调用期才 from app.trace.store import default_trace_store：不换 sys.modules
    # 这一格，病形根本进不了那一轮，K1 就会「咬不中」而白绿。
    monkeypatch.setitem(sys.modules, "app.trace.store", shadow)

# ==================== 事件件：形状照真件，落点一律在 tmp_path ====================


def _stamp(index: int) -> str:
    return (
        datetime(2026, 9, 13, 9, 2, 2, tzinfo=timezone.utc) + timedelta(milliseconds=7 * index)
    ).isoformat()


def _journal_line(trace_id: str, sequence: int) -> dict:
    """One journal line in the shape the write side produces.

    行长约 725 B 是真件量出来的（32,038,850 B / 44,143 行），行尾用 CRLF 也与真件一致——
    Windows 上 ``TraceStore._write_fallback`` 走的正是文本模式追加。体量是本单的自变量，
    所以这两格不许省。
    """
    stamp = _stamp(sequence)
    return {
        "trace_id": trace_id,
        "request_id": "req-" + trace_id,
        "task_id": "task-" + trace_id,
        "sequence": sequence,
        "timestamp": stamp,
        "event_type": "agent.result.recorded",
        "status": "completed",
        "payload": {
            "owner_id": "u-r661",
            "session_id": "sess-r661",
            "excerpt": "x" * 420,
        },
        FALLBACK_LINE_MARKER: {
            "is_fallback": True,
            "reason": "backend_not_postgres",
            "recorded_at": stamp,
        },
    }


def _line_text(trace_id: str, sequence: int) -> str:
    return json.dumps(_journal_line(trace_id, sequence), ensure_ascii=False)


def _build_journal(path: Path, events: int) -> int:
    """Write exactly ``events`` whole lines and hand back the bytes on disk.

    行与行按 64 条 trace 轮转，与真件一致地把同一枚 trace 的号摊开：全量扫件那种写法要的正是
    「整本逐行解析」这一笔代价，把件写成单条 trace 会让尺量错东西。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\r\n") as handle:
        for index in range(events):
            trace_id = "trace-r661-%03d" % (index % 64)
            handle.write(_line_text(trace_id, index // 64 + 1) + "\n")
    return path.stat().st_size


def _append_lines(path: Path, text: str) -> None:
    """Simulate another writer mid-append: text mode with CRLF translation, no newline added."""
    with path.open("a", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)


def _path_shaped_call_arguments(source_text: str) -> list:
    """本件递给任何一枚调用的字面参数里，不许出现带分隔符的路径。

    事件件的落点只许由夹具（``tmp_path``）递进来。散文里提到 ``data/traces/`` 不算落点，
    所以这一枚闸看的是调用参数，不是全文字面——把闸做成「谁在文档里写过这个路径谁红」
    就等于没有闸。
    """
    strays = []
    for node in ast.walk(ast.parse(source_text)):
        if not isinstance(node, ast.Call):
            continue
        for argument in list(node.args) + [keyword.value for keyword in node.keywords]:
            if (
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and _PATH_SHAPE.fullmatch(argument.value)
            ):
                strays.append(argument.value)
    return strays


def _store(journal: Path):
    """一枚不连库的账本：``persistence=None`` 时每一枚事件都落进这件文件，正是病形现场。"""
    return THIS.store_module.TraceStore(journal)


def _event(trace_id: str, owner: str = "u-r661") -> dict:
    return {
        "trace_id": trace_id,
        "request_id": "req-" + trace_id,
        "event_type": "request.started",
        "status": "started",
        "payload": {"owner_id": owner},
    }


def _identities(path: Path) -> list:
    """The ``(trace_id, sequence)`` pair of every event line, in the order they were written."""
    out = []
    for raw in path.read_bytes().decode("utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            # 坏行按 R257 的裁定归 unreadable：本尺只数读得懂的行，不替读路径作决定。
            continue
        if isinstance(record.get(BACKFILL_RECEIPT_MARKER), dict):
            continue
        out.append((str(record.get("trace_id")), int(record.get("sequence") or 0)))
    return out


@contextlib.contextmanager
def _point_store_at(monkeypatch, journal: Path):
    """把默认那本账改道到事件件：仓内 ``data/traces/`` 一字节都不许多出来（与 R649 同一招）。"""
    monkeypatch.setenv("TRACE_STORE_PATH", str(journal))
    THIS.store_module.reset_default_trace_store()
    store = THIS.store_module.default_trace_store()
    try:
        yield store
    finally:
        THIS.store_module.reset_default_trace_store()


def _piece_timings(monkeypatch, tmp_path: Path):
    """真收端逐帧到达时刻：与 shipped 那一格同一个激励（片间停 0.5 s），不另开一把尺。"""

    def publish(sink, answer):
        for part in r149.INCREMENTS:
            sink(r149._piece(part))
            time.sleep(HOLD_SECONDS)

    _ask, ask_timed, _remaining, _seen = r149._harness(
        monkeypatch, tmp_path, [r149.ANSWER], publish=publish
    )
    out = ask_timed()
    times = [t for t, frame in out["frames"] if frame.startswith("event: text")]
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    return times, gaps, out["wall"]


def _first_number_price(journal: Path, trace_id: str) -> float:
    """新开一本账、给它的第一枚事件取号，这一笔花多少秒——首眼就住在这条道里。"""
    store = _store(journal)
    started = time.perf_counter()
    store.record_event(**_event(trace_id))
    return time.perf_counter() - started


# ==================== 临界路径：A 逐片直发、B 平性、I 静态 ====================


def test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces(tmp_path, monkeypatch):
    """24,000 枚事件件在场时，逐片直发照旧逐片到：这道牙站的就是 shipped 那一格的合格线。

    判据一字不放宽（``min(gaps) >= 0.4``、``max(gaps) <= hold + 1.0``、first_text 显著早于
    wall），也不借 sleep 糊过去。事件件落在 tmp 里、由 ``TRACE_STORE_PATH`` 改道，改前回读
    行数自证前提在场——一枚量不到病形的牙不许自称咬得住。
    """
    journal = tmp_path / "events.jsonl"
    bytes_on_disk = _build_journal(journal, R661_JOURNAL_EVENTS)
    assert len(_identities(journal)) == R661_JOURNAL_EVENTS, "事件件没造够，这一格量的是空气"
    assert bytes_on_disk > R661_JOURNAL_EVENTS * 600, bytes_on_disk
    with _point_store_at(monkeypatch, journal) as store:
        assert Path(store.path) == journal, "默认那本账没改道，这一格量的是仓里那本"
        times, gaps, wall = _piece_timings(monkeypatch, tmp_path)
        assert len(times) == len(r149.INCREMENTS) + 1, times
        assert times[0] < wall - 0.5, (times[0], wall)
        assert min(gaps) >= MIN_GAP_FLOOR, (
            "片被攒成一坨同时发出（事件件 %d B / %d 枚）：%s"
            % (bytes_on_disk, R661_JOURNAL_EVENTS, [round(gap, 3) for gap in gaps])
        )
        assert max(gaps) <= MAX_GAP_CEILING, [round(gap, 3) for gap in gaps]
        assert len(_identities(journal)) > R661_JOURNAL_EVENTS, (
            "这一轮一枚事件都没往事件件里落：量具没接上临界路径，红绿都不算数"
        )


def test_taking_a_number_costs_the_same_at_one_megabyte_and_at_twenty_four(tmp_path):
    """取号这一步不许随事件件变贵：1 MiB 档与 24,000 枚档必须是同一个价钱。

    这条才是「不随体量长」的直接判据，A 那一格是它对客户的表面。低档取五枚中位（它自己也
    就是那枚种子窗口的价），高档同取五枚中位；比值与常数余量都是现读之后宽配的量出来的：
    改前 1 MB 12.5 ms、24 MB 约 380 ms（比值 30），改后 5.6 ms 与 5.7 ms（比值 1.0）。
    """
    small_book = tmp_path / "one-megabyte.jsonl"
    small_bytes = _build_journal(small_book, BASELINE_JOURNAL_EVENTS)
    big_book = tmp_path / "shipped-size.jsonl"
    big_bytes = _build_journal(big_book, R661_JOURNAL_EVENTS)
    low = statistics.median(
        _first_number_price(small_book, "trace-r661-low-%d" % i) for i in range(5)
    )
    high = statistics.median(
        _first_number_price(big_book, "trace-r661-high-%d" % i) for i in range(5)
    )
    assert high <= FLATNESS_RATIO * low + FLATNESS_SLACK_SECONDS, (
        "事件件从 %d B 涨到 %d B，取号这一步从 %.1f ms 涨到 %.1f ms：它还在随体量长"
        % (small_bytes, big_bytes, low * 1000, high * 1000)
    )


def test_the_number_taking_leg_reaches_no_whole_journal_reader() -> None:
    """静态闸：``_next_sequence`` 那条腿（含它递进的所有 ``self.*``）不许够到整本读件者。

    A 与 B 是时间的尺，机器忙起来总有脾气；这一枚是字面的闸——把修复改回「读整本再挑最大号」
    当场红，把整本读换成另一枚新写的读法也照样红，只要它还在取号那条腿上。结算清扫那一腿
    （``maybe_backfill_fallback_journal``）今天仍在整本读件，本单不替它翻绿也不把它折进这一格：
    那条腿只在「tables 在位且有欠账」时才走，写在凭据纸的「留给下一格」。
    """
    tree = ast.parse(THIS._store_source_text())
    methods = _store_methods(tree)
    leg = _reachable_methods(methods, NUMBER_TAKING_LEG)
    assert "_file_sequence_floor" in leg, (
        "取号那条腿里已经认不出 ``_file_sequence_floor``：本闸的判定对象搬走了，红给人看"
    )
    reached = sorted(name for name in leg if name in WHOLE_JOURNAL_READERS)
    assert not reached, "取号那条腿够到了整本读件者：%s" % reached
    for name in sorted(leg):
        body = methods[name]
        read_backs = [
            node for node in ast.walk(body)
            if isinstance(node, ast.Attribute) and node.attr in {"read_text", "read_bytes"}
        ]
        assert not read_backs, "%s 里直接把整本件读进内存：%s" % (name, ast.unparse(read_backs[0]))


# ==================== 落盘语义：C..H 六枚，逐枚对着折叠那一步 ====================


def test_a_fresh_store_continues_the_numbers_the_journal_already_handed_out(tmp_path):
    """新开一本账（重启的进程、并写的 worker）必须接着这件已经发出去的号，不许从 1 重发。

    这一格钉的是折叠换了手法之后那条不能弯的规则：``max(pg, file) + 1`` 里 file 那一腿
    仍然要说得出这本件替这条 trace 发到过几号（R250 的原话：两本账不许发出同一枚号）。
    """
    journal = tmp_path / "events.jsonl"
    journal.write_text("", encoding="utf-8")
    trace = "trace-r661-fresh"
    first = _store(journal)
    taken = [first.record_event(**_event(trace))["sequence"] for _ in range(3)]
    assert taken == [1, 2, 3], taken
    again = _store(journal).record_event(**_event(trace))["sequence"]
    assert again == 4, "新开的一本把这件已经发过的号又发了一遍：%s" % taken
    identities = _identities(journal)
    assert len(identities) == len(set(identities)) == 4, identities


def test_the_floor_folds_a_line_another_writer_appended_after_the_first_look(tmp_path):
    """首眼之后别人追加的行也必须折进来：只在内存里记自己发过的号就是 K3 那一刀。

    两个进程（这里两枚 store）同一本件同一枚 trace：a→1，b 首眼折到 a 那枚行取 2，
    a 再取时必须折到 b 那枚行 ⇒ 3。少了第三步这一格就退化成上一格的重复。
    """
    journal = tmp_path / "events.jsonl"
    journal.write_text("", encoding="utf-8")
    trace = "trace-r661-two-writers"
    a, b = _store(journal), _store(journal)
    assert a.record_event(**_event(trace))["sequence"] == 1
    assert b.record_event(**_event(trace))["sequence"] == 2
    assert a.record_event(**_event(trace))["sequence"] == 3, (
        "另一本写进去的行没被折叠进来：a 又发了一个 2"
    )
    identities = _identities(journal)
    assert sorted(number for _trace, number in identities) == [1, 2, 3], identities


def test_a_line_still_being_written_is_counted_once_it_is_whole(tmp_path):
    """半行不发号，也不许把游标带过去：行写完的那一刻它必须算进 floor。

    游标只在整行边界上前进，这是「增量折叠」与「读一遍尾巴」的分别所在。写一半就推进游标
    （K4）会让这枚行永远落在游标之前，下一次折叠只读到它的后半截，谁也不认得它。
    """
    journal = tmp_path / "events.jsonl"
    journal.write_text("", encoding="utf-8")
    trace = "trace-r661-half-line"
    a = _store(journal)
    text = _line_text(trace, 77)
    head, tail = text[: len(text) // 2], text[len(text) // 2:]
    _append_lines(journal, head)
    assert a._file_sequence_floor(trace) == 0, "一枚还没写完的行发起了号"
    _append_lines(journal, tail + "\n")
    assert a._file_sequence_floor(trace) == 77, (
        "写完的行没被算进来：游标跨过了半行"
    )


def test_a_receipt_line_hands_out_no_number(tmp_path):
    """收据不是事件，也不发号：折叠对它的裁定必须与 ``_journal_records`` 一字不差。

    真件的收据行故意不带 trace_id（R257：一行重复一枚 id 会让 ``grep -c`` 数两遍）。这里
    偏偏造一枚带了 id 与号数的收据，量的就是「折叠是不是按行种分类」而不是「这行有没有 id」。
    """
    journal = tmp_path / "events.jsonl"
    journal.write_text("", encoding="utf-8")
    trace = "trace-r661-receipt"
    a = _store(journal)
    assert a.record_event(**_event(trace))["sequence"] == 1
    receipt = json.dumps(
        {
            BACKFILL_RECEIPT_MARKER: {"settled_events": 1, "covered_through_line": 1},
            "trace_id": trace,
            "sequence": 99,
        },
        ensure_ascii=False,
    )
    _append_lines(journal, receipt + "\n")
    assert a.record_event(**_event(trace))["sequence"] == 2, (
        "收据行被当成事件发了号：这一本件从此在数自己的收据"
    )


def test_a_torn_line_does_not_stop_the_write_path(tmp_path):
    """读不懂的一行不许拦住记账：写路径问的是「我能取几号」，坏行答不了就让它过去。

    旧写法（全量扫件）里坏行会把 ``record_event`` 一起抛掉，``_record_wire_first_text``
    那一层接住之后只剩一行 warning：于是整轮的首屏读数无声消失。本格把这条钉住——它与
    下一格是同一枚坏行的两面，动哪一面都会红。
    """
    journal = tmp_path / "events.jsonl"
    journal.write_text("", encoding="utf-8")
    trace = "trace-r661-torn-write"
    a = _store(journal)
    assert a.record_event(**_event(trace))["sequence"] == 1
    _append_lines(journal, '{"trace_id": "torn\n')
    event = a.record_event(**_event(trace))
    assert event["sequence"] == 2, event
    assert len(_identities(journal)) == 2, "坏行拦住了这一枚事件落盘"


def test_the_read_path_still_raises_on_a_torn_line(tmp_path):
    """同一枚坏行在读路径上照旧抛：R257 那句「静默少读就是撒谎」不许被本单摸绿。

    折叠只把 tolerance 加在写路径那一侧；``_journal_records`` 的 strict 缺省一个字节都没动，
    ``tests/test_r257_journal_says_it_is_not_the_ledger.py`` 那两枚 ``pytest.raises`` 今天
    仍然由它说话（本格是补的第三面：本域自己也得能被咬住）。
    """
    journal = tmp_path / "events.jsonl"
    trace = "trace-r661-torn-read"
    a = _store(journal)
    a.record_event(**_event(trace))
    _append_lines(journal, '{"trace_id": "torn\n')
    with pytest.raises(ValueError):
        a.replay(trace)


# ==================== 合格线与落点的自证 ====================


def test_the_shipped_wire_bar_is_still_the_shipped_bar() -> None:
    """本单的牙与 shipped 那一格共用同一道线：``min(gaps) >= 0.4`` 一字未改宽，也不另开一把尺。

    工单第一条不许就是这个：合格线不许动、不许加 sleep、不许为了变绿把事件件写到仓外别处。
    这里不读盘面状态，只读两枚源文的字面。
    """
    shipped = THIS._shipped_wire_text()
    assert shipped.count("assert min(gaps) >= 0.4") == 1, "shipped 那道线不在了或被改写了"
    assert "assert max(gaps) <= hold + 1.0" in shipped, "另一头的尺被摘了"
    assert "hold = 0.5" in shipped, "激励变了：那一格不再是每片之间停半秒"
    assert "MIN_GAP_FLOOR = 0.4" in _text(OWN_REL), "本件自己那枚常数已经不是那道线"
    assert "time.sleep(0" not in _text(STORE_REL), "落盘件里长出了 sleep：拿延时糊过去的那种修法"


def test_the_fold_never_touches_the_worktree_journal(tmp_path, monkeypatch) -> None:
    """本域的账一律改道到 tmp：仓里 ``data/traces/`` 不许因为这枚牙多落一枚字节（R656 那一格今天还欠）。

    两半：运行时证明默认那本账真的被 ``TRACE_STORE_PATH`` 带走；字面证明本件只在
    ``_point_store_at`` 一处碰 ``default_trace_store()``，全文没有第二枚指向仓根的落点。
    """
    journal = tmp_path / "events.jsonl"
    _build_journal(journal, 12)
    with _point_store_at(monkeypatch, journal) as store:
        assert tmp_path in Path(store.path).resolve().parents, store.path
    own = _text(OWN_REL)
    strays = _path_shaped_call_arguments(own)
    assert not strays, "本件把事件件的落点写成了字面路径：%s" % strays
    tree = ast.parse(own)
    counts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            counts[node.name] = sum(
                1 for inner in ast.walk(node)
                if isinstance(inner, ast.Attribute) and inner.attr == "default_trace_store"
            )
    homes = sorted(name for name, hit in counts.items() if hit)
    assert homes == ["_point_store_at"], "默认那本账在本件里有第二个拿法：%s" % homes

# ==================== 刀口（逐枚原文锚点；漂了就在锚点闸当场红）====================

CUT_K1 = (
    '        self._fold_journal_floors()\n'
    '        return self._journal_floors.get(str(trace_id or ""), 0)\n',
    '        events = [event for event in self._read_events() if event.get("trace_id") == trace_id]\n'
    '        if not events:\n'
    '            return 0\n'
    '        return max(int(event.get("sequence") or 0) for event in events)\n',
)
CUT_K2 = (
    "JOURNAL_FLOOR_SEED_BYTES = 1 << 20\n",
    "JOURNAL_FLOOR_SEED_BYTES = 1 << 46  # 摘刀：首眼就把整本读进来\n",
)
CUT_K3 = (
    "        size = self._journal_size()\n"
    "        cursor = self._journal_floor_cursor\n",
    "        size = self._journal_size()\n"
    "        cursor = self._journal_floor_cursor\n"
    "        if cursor is not None:\n"
    "            return  # 摘刀：首眼之后再也不读这本件\n",
)
CUT_K4 = (
    '        consumed = chunk.rfind(b"\\n") + 1\n',
    "        consumed = len(chunk)  # 摘刀：半行也把游标推过去\n",
)
CUT_K5 = (
    "            self._journal_floor_cursor = cursor = max(0, size - JOURNAL_FLOOR_SEED_BYTES)\n",
    "            self._journal_floor_cursor = cursor = size  # 摘刀：首眼不看已落盘的行\n",
)
CUT_K6 = (
    "        if isinstance(record.get(BACKFILL_RECEIPT_MARKER), dict):\n",
    "        if False:  # 摘刀：收据也拿来发号\n",
)
CUT_K7 = (
    "        except (UnicodeDecodeError, ValueError):\n            return\n",
    "        except (UnicodeDecodeError, ValueError):\n            raise\n",
)
CUT_K10 = (
    "    assert min(gaps) >= 0.4, f\"片被攒成一坨同时发出：{[round(gap, 3) for gap in gaps]}\"\n",
    "    assert min(gaps) >= 0.1, f\"片被攒成一坨同时发出：{[round(gap, 3) for gap in gaps]}\"\n",
)
CUT_K8 = (
    "    def _journal_records(self, *, tolerant: bool = False) -> list[dict[str, Any]]:\n",
    "    def _journal_records(self, *, tolerant: bool = True) -> list[dict[str, Any]]:\n",
)

#: 逐枚点名 victim。K1 与 K9 是同一处改动的两面：K1 把改过的源文 exec 成影子账本，量的是
#: 客户端真看见的帧间距；K9 只把这处改动喂给静态闸的取材口，量的是字面。两枚都要红，
#: 缺一个方向就是「时间过了、字面还病着」或反之。
KNIVES = {
    "K1": {"mode": "shadow", "edits": (CUT_K1,),
           "victim": "test_twenty_four_thousand_journal_events_do_not_bunch_the_pieces"},
    "K2": {"mode": "shadow", "edits": (CUT_K2,),
           "victim": "test_taking_a_number_costs_the_same_at_one_megabyte_and_at_twenty_four"},
    "K3": {"mode": "shadow", "edits": (CUT_K3,),
           "victim": "test_the_floor_folds_a_line_another_writer_appended_after_the_first_look"},
    "K4": {"mode": "shadow", "edits": (CUT_K4,),
           "victim": "test_a_line_still_being_written_is_counted_once_it_is_whole"},
    "K5": {"mode": "shadow", "edits": (CUT_K5,),
           "victim": "test_a_fresh_store_continues_the_numbers_the_journal_already_handed_out"},
    "K6": {"mode": "shadow", "edits": (CUT_K6,),
           "victim": "test_a_receipt_line_hands_out_no_number"},
    "K7": {"mode": "shadow", "edits": (CUT_K7,),
           "victim": "test_a_torn_line_does_not_stop_the_write_path"},
    "K8": {"mode": "shadow", "edits": (CUT_K8,),
           "victim": "test_the_read_path_still_raises_on_a_torn_line"},
    "K9": {"mode": "shape", "edits": (CUT_K1,), "target": STORE_REL,
           "seam": "_store_source_text",
           "victim": "test_the_number_taking_leg_reaches_no_whole_journal_reader"},
    "K10": {"mode": "shape", "edits": (CUT_K10,), "target": R149_REL,
            "seam": "_shipped_wire_text",
            "victim": "test_the_shipped_wire_bar_is_still_the_shipped_bar"},
}


# ==================== 取号那条腿的 AST 走法 ====================


def _store_methods(tree) -> dict:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TraceStore":
            return {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError("app/trace/store.py 里找不到 TraceStore：取材对象变了")


def _self_names(fn) -> set:
    return {
        node.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    }


def _reachable_methods(methods: dict, starts) -> set:
    """沿 ``self.<method>`` 递推：取号那条腿今天走得到哪些方法。"""
    seen: set = set()
    queue = list(starts)
    while queue:
        name = queue.pop()
        if name in seen or name not in methods:
            continue
        seen.add(name)
        queue.extend(sorted(_self_names(methods[name]) - seen))
    return seen


# ==================== 机械：正控先绿，逐枚点名咬中 ====================


def _victim(knife: str):
    return getattr(THIS, KNIVES[knife]["victim"])


def _run_victim(knife: str, tmp_path: Path, monkeypatch) -> None:
    victim = _victim(knife)
    signature = victim.__code__.co_varnames[: victim.__code__.co_argcount]
    kwargs = {}
    if "tmp_path" in signature:
        kwargs["tmp_path"] = tmp_path
    if "monkeypatch" in signature:
        kwargs["monkeypatch"] = monkeypatch
    victim(**kwargs)


def _bite(knife: str, tmp_path: Path, monkeypatch) -> bool:
    _arm(knife, tmp_path, monkeypatch, bite=True)
    try:
        _run_victim(knife, tmp_path / "bite", monkeypatch)
    except BaseException:  # noqa: BLE001 - Failed: DID NOT RAISE 继承的是 BaseException
        return True
    return False


@pytest.mark.parametrize("knife", sorted(KNIVES))
def test_the_positive_control_stays_green(knife, tmp_path, monkeypatch):
    """同一套影子机械、刀口不落（edits=()）：victim 必须先绿，后面的红才算被咬中。"""
    _arm(knife, tmp_path / "control", monkeypatch, bite=False)
    _run_victim(knife, tmp_path / "control", monkeypatch)


@pytest.mark.parametrize("knife", sorted(KNIVES))
def test_each_knife_reddens_its_named_victim(knife, tmp_path, monkeypatch):
    assert _bite(knife, tmp_path, monkeypatch), (
        "刀 %s 没咬中 %s：那一格判据其实没有牙" % (knife, KNIVES[knife]["victim"])
    )


# ==================== 三道静态闸：在册格、锚点、盘面 ====================


def test_the_shipped_teeth_are_all_still_here() -> None:
    """名册在册：搬走任何一枚牙，本件先红（牙被悄悄摘走比牙红更难查）。"""
    for name in SHIPPED_CELLS:
        assert callable(getattr(THIS, name, None)), "在册牙不在了：%s" % name
    victims = {spec["victim"] for spec in KNIVES.values()}
    assert len(victims) == len(KNIVES), "两把刀指着同一枚 victim：有一格其实没人守"
    assert victims <= set(SHIPPED_CELLS), victims - set(SHIPPED_CELLS)
    assert set(SHIPPED_CELLS) - victims == set(UNKNIFED_CELLS), (
        "在册牙里出现了既没人守又没点名的格子：%s" % sorted(set(SHIPPED_CELLS) - victims)
    )


def test_every_blade_anchor_hits_exactly_once() -> None:
    """锚点在册：每把刀的每一处改动在 shipped 字节里仍旧只命中一枚，漂了不许默默失刀。"""
    for knife, spec in sorted(KNIVES.items()):
        target = spec.get("target", STORE_REL)
        source = _text(target)
        for old, new in spec["edits"]:
            assert source.count(old) == 1, "%s 的刀口在 %s 里命中 %d 枚" % (
                knife, target, source.count(old))
            assert old != new, "%s 的刀口是空改动" % knife
    assert R661_JOURNAL_EVENTS > MEASURED_CROSSING_EVENTS, (
        "牙站的体量必须高于现读到的跨线点，否则这一格量不到病形")
    assert MEASURED_CROSSING_EVENTS * 3 <= R661_JOURNAL_EVENTS, (
        "跨线点三倍之内没有余量：这台机器一忙就白绿")


def test_no_tooth_in_this_domain_gates_on_the_checkout_state() -> None:
    """反同族病（在册事故 #96／#107／#113）：本域的钉一律不看「此刻这棵树干不干净」。

    needles 不在本件重抄一遍，用 R655 那枚在册闸的出处；本件自己也不起子进程去摸盘面。
    """
    needles = stale_gates.STATE_NEEDLES
    assert needles, "在册那枚闸的字面表空了：本闸会退化成永真"
    for rel in DOMAIN_FILES:
        tree = ast.parse(_text(rel))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert "subprocess" not in imported, "%s 起了子进程：盘面状态判据的常见入口" % rel
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for needle in needles:
                    assert needle not in node.value, "%s 里出现盘面探针 %r" % (rel, needle)
    assert "subprocess" not in THIS.__dict__, "本件自己也不许起子进程去摸盘面"
