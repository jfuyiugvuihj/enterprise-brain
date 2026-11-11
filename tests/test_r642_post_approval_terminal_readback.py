# -*- coding: utf-8 -*-
"""R642 判据①：D-3 那半格 —— 批准之后必须**再读一次** ``/queue/status``，两次读数都留档。

病（跟进单 §167 二／§172 二；本席 10-04 在 run21b 那 12 行上现取）：``_poll_queue`` 读到
``awaiting_approval`` 就停表，``queue.terminal`` 从此定格在**挂起那一刻**的快照上；transport 随后
把批准轮走到终答（R447 判据①），却一次都没回头再读那枚载荷 ⇒ 那 8 枚 ``queued_approved`` 的
``terminal.state`` 全是 ``awaiting_approval``、``sources_present`` 全是 false、``sources_n`` 全是 0。
这枚 0 说的是「挂起的时候当然还没有出处」，不是「批准后出处为零」—— D-3 因此只能判「未量到」。

本件把这一格钉成可失败读数，一枚都不落在散文上：

- 开关 ``EVAL_POST_APPROVAL_READBACK`` **默认关**：关着时一枚状态读都不许多打，``queue`` 那一格
  的形状与帧账一行的键集逐字回到今天（旧口径由 ``test_the_switch_defaults_to_off...`` 钉）；
- 开着时批准轮走完之后多打**一发** GET，读回的东西落在 ``queue.post_approval`` 那一格里 ——
  🔴 快照那一格一个字不改，两次读数都在账上，谁也不冒充谁；
- 打不通 / 解不开 / 那一行说不出 ⇒ 记 ``None`` 并点名原因，🔴 不折 0、不拿挂起快照顶替；
- 读数分类 ``post_approval_sources_readback`` 八枚互不冒充，``sources_n`` 只在三枚读数下才是真数；
- 帧账一行的键集一格不多（四枚「键集是**对判**」的在册钉一字不改），且那枚闸真会红 —— 多一列红、
  少一列也红，本件的货没从这道闸里漂过去；
- 钟的纪律：那一发重读一枚表都不许多读；``_poll_queue`` 的停表词表一字未动（AST 现取）。

全部离线：假出口复用 ``tests/_r259_queue_ruler``（不新造第二套桩），零容器零连库零模型零端口。
真机读数不在本件里 —— 由总控在 run22／D 相 2 的窗里取，本件只证明量具**有能力**取到。
"""
import ast
import hashlib
import importlib.util
from pathlib import Path

import pytest

from tests import _r259_queue_ruler as Q

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "eval_transport_ask_v2.py"
IMPORT_SHA = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()

KNOB_ENV = "EVAL_POST_APPROVAL_READBACK"
#: run21b 那 8 枚的形状：kind 已落成 queued_approved，terminal 却还停在挂起快照上。
PARKED_SNAPSHOT = {"shape": "structured", "state": "awaiting_approval",
                   "sources_present": False, "sources_n": 0, "sources_error": ""}


def _load(monkeypatch, knob, name):
    """按开关状态现装一枚干净的量具（开关在 import 期读表，与 R632 那两枚同一族纪律）。"""
    if knob:
        monkeypatch.setenv(KNOB_ENV, "on")
    else:
        monkeypatch.delenv(KNOB_ENV, raising=False)
    spec = importlib.util.spec_from_file_location("r642_d3_" + name, str(SCRIPT_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.RECORD_POST_APPROVAL_TERMINAL is bool(knob)
    return module


def _staged(monkeypatch, tmp_path, knob, name):
    return Q.configure(_load(monkeypatch, knob, name), tmp_path, name="r642-d3-" + name)


def _parked_then_approved(monkeypatch, tmp_path, knob, name, extra=None):
    """完整一题：入队 → 读到挂起（停表）→ 批准到终答 →（开关开着才有的）批准后重读。"""
    module = _staged(monkeypatch, tmp_path, knob, name)
    statuses = [Q.parked_body()] + (list(extra) if extra is not None else [Q.answered_body()])
    return (module,) + Q.drive_queue(module, statuses, row_id="report-r642")


# ==================== 一、开关默认关：旧口径逐字节回到今天 ====================


def test_the_switch_defaults_to_off_and_asks_for_no_extra_read(monkeypatch, tmp_path):
    module, _payload, fake, sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, False, "off")
    assert module.RECORD_POST_APPROVAL_TERMINAL is False
    assert len(fake.queue_reads) == 1, fake.queue_reads
    row = frames[0]
    assert row["kind"] == module.QUEUED_APPROVED_KIND == "queued_approved", row
    assert "post_approval" not in row["queue"], "关着就多长了一格 ⇒ 旧窗口的字节不再可比"
    assert row["queue"]["terminal"]["state"] == "awaiting_approval", row
    assert set(row) == Q.FRAME_ROW_KEYS, set(row) ^ Q.FRAME_ROW_KEYS
    read = module.post_approval_sources_readback(row)
    assert read["cell"] == module.D3_NO_READBACK and read["sources_n"] is None, read
    assert set(sidecar[0]) - set(Q.SIDECAR_BASE_KEYS) == Q.R123_EXTRA_KEYS, set(sidecar[0])


# ==================== 二、开关开着：批准后那一发重读 + 两次读数都留档 ====================


def test_an_approved_queue_turn_reads_the_terminal_once_more(monkeypatch, tmp_path):
    module, payload, fake, _sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "on")
    assert len(fake.queue_reads) == 2, fake.queue_reads
    assert fake.queue_reads[1] == fake.queue_reads[0], "重读必须打在同一个 request_id 上"
    row = frames[0]
    cell = row["queue"]["post_approval"]
    assert set(cell) == set(module.POST_APPROVAL_CELL_KEYS), cell
    assert cell["read"] is True and cell["outcome"] == "read", cell
    assert cell["terminal"]["state"] == "answered", cell
    assert cell["terminal"]["sources_n"] == 3, cell
    # 🔴 快照那一格一字不改：批准后终态是**多存的一格**，不是把旧格子顶掉
    assert row["queue"]["terminal"]["state"] == "awaiting_approval", row
    assert row["queue"]["terminal"]["sources_n"] == 0, row
    assert row["queue"]["final"] == "awaiting_approval", row
    assert payload["answer"] == Q.ANSWER, payload
    read = module.post_approval_sources_readback(row)
    assert read["cell"] == module.D3_READ_SOME and read["sources_n"] == 3, read


def test_the_extra_cell_is_the_only_shape_change_in_the_queue_book(monkeypatch, tmp_path):
    """开着与关着两跑对照：``queue`` 那一格只多 ``post_approval`` 一名，其余逐格同数。"""
    off_module, _off_payload, _off_fake, _off_sidecar, off_frames = _parked_then_approved(
        monkeypatch, tmp_path, False, "shape-off")
    on_module, _on_payload, _on_fake, _on_sidecar, on_frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "shape-on")
    off_book = off_frames[0]["queue"]
    on_book = on_frames[0]["queue"]
    assert set(on_book) - set(off_book) == {"post_approval"}, (set(off_book), set(on_book))
    for name in off_book:
        assert on_book[name] == off_book[name], name
    assert off_frames[0]["criterion_two_holds"] == on_frames[0]["criterion_two_holds"]


def test_the_readback_costs_not_a_single_extra_clock_read(monkeypatch, tmp_path):
    """钟的纪律（与 R223／R259 同一族）：那一发 GET 一次表都不许多读。"""
    off = _staged(monkeypatch, tmp_path, False, "clock-off")
    on = _staged(monkeypatch, tmp_path, True, "clock-on")
    for module, statuses in ((off, [Q.parked_body()]),
                             (on, [Q.parked_body(), Q.answered_body()])):
        module._open = Q.Transport(ask_events=Q.QUEUED_STREAM, statuses=statuses,
                                   approvals=[Q.APPROVED_STREAM])
        module.transport({"id": "report-r642", "question": "Q3 营收多少？"})
    assert on.time.reads == off.time.reads, (on.time.reads, off.time.reads)
    assert on.time.reads > 0, on.time.reads


# ==================== 三、拿不到证词就是 None：四枚失败形状逐枚点名 ====================


@pytest.mark.parametrize("injected,expect", [
    ([Q.http_error(503)], "http_503"),
    ([Q.url_error()], "URLError"),
    (["{not-json"], "JSONDecodeError"),
    (['[1, 2, 3]'], "not_object"),
], ids=["http-503", "connection", "undecodable", "not-object"])
def test_a_failed_readback_is_none_never_zero_and_never_the_snapshot(monkeypatch, tmp_path,
                                                                     injected, expect):
    """批准后那一发读不到 ⇒ 槽位全 None、形状 ``not_terminal``、读数记「未量到」。"""
    module, _payload, fake, _sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "fail", extra=injected)
    assert len(fake.queue_reads) == 2, fake.queue_reads
    cell = frames[0]["queue"]["post_approval"]
    assert cell["read"] is False, cell
    assert cell["outcome"] == expect, cell
    terminal = cell["terminal"]
    assert terminal["shape"] == module.TERMINAL_SHAPE_NOT_TERMINAL, terminal
    for slot in module.TERMINAL_SLOTS:
        assert terminal[slot] is None, (slot, terminal[slot])
    read = module.post_approval_sources_readback(frames[0])
    assert read["cell"] == module.D3_READBACK_UNREADABLE and read["sources_n"] is None, read
    # 🔴 快照那一格仍在账上、仍然没被拿来冒充批准后终态（不折 0 的那一半证据）
    assert frames[0]["queue"]["terminal"]["sources_n"] == 0


def test_a_legacy_terminal_row_says_it_cannot_say(monkeypatch, tmp_path):
    """读到了载荷而那一行说不出出处（形状非 structured）⇒ row_cannot_say，枚数照样 None。"""
    legacy = Q.answered_body(terminal_schema="legacy", terminal_state="legacy_row", sources=[])
    module, _payload, _fake, _sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "legacy", extra=[legacy])
    cell = frames[0]["queue"]["post_approval"]
    assert cell["read"] is True, cell
    assert cell["terminal"]["shape"] == module.TERMINAL_SHAPE_LEGACY, cell
    assert cell["terminal"]["sources_n"] is None, cell
    read = module.post_approval_sources_readback(frames[0])
    assert read["cell"] == module.D3_ROW_CANNOT_SAY and read["sources_n"] is None, read


def test_a_zero_source_terminal_is_read_zero_and_not_unmeasured(monkeypatch, tmp_path):
    """真读到「成功后出处为零」那一枚（report-11 的形状）：这才是 D-3 有权判红的一格。"""
    empty = Q.answered_body(sources=[], sources_present=False)
    module, _payload, _fake, _sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "zero", extra=[empty])
    read = module.post_approval_sources_readback(frames[0])
    assert read["cell"] == module.D3_READ_ZERO and read["sources_n"] == 0, read


# ==================== 四、八枚读数互不冒充：分类器逐枚点名 ====================


def _row(kind, queue):
    return {"id": "report-x", "kind": kind, "queue": queue}


def _readback(**over):
    cell = {"read": True, "outcome": "read",
            "terminal": {"shape": "structured", "sources_n": 2, "sources_error": ""}}
    cell.update(over)
    return cell


@pytest.mark.parametrize("row,expect_cell,expect_count", [
    (_row("approved_ok", {}), "not_applicable", None),
    (_row("queued_polled", {"terminal": PARKED_SNAPSHOT}), "not_applicable", None),
    (_row("queued_approved", {"terminal": PARKED_SNAPSHOT}), "no_readback", None),
    (_row("approval_failed", {"terminal": PARKED_SNAPSHOT}), "no_readback", None),
    (_row("queued_approved", {"post_approval": _readback(read=False, outcome="http_503")}),
     "readback_unreadable", None),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "not_terminal", "sources_n": None})}), "readback_unreadable", None),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "legacy", "sources_n": None})}), "row_cannot_say", None),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "structured", "sources_n": None})}), "row_cannot_say", None),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "structured", "state": "awaiting_approval",
                  "sources_n": 0, "sources_error": ""})}), "still_parked", None),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "structured", "sources_n": 0,
                  "sources_error": "sources_unavailable"})}), "not_computable", 0),
    (_row("queued_approved", {"post_approval": _readback(
        terminal={"shape": "structured", "sources_n": 0, "sources_error": ""})}),
     "read_zero", 0),
    (_row("queued_approved", {"post_approval": _readback()}), "read_some", 2),
], ids=["sync-lane", "polled-no-approval", "approved-no-readback", "approval-failed",
        "readback-http-503", "readback-not-terminal", "readback-legacy",
        "readback-without-keys", "readback-still-parked", "sources-error",
    "read-zero", "read-some"])
def test_the_d3_readout_names_every_shape_apart(monkeypatch, row, expect_cell, expect_count):
    module = _load(monkeypatch, False, "classifier")
    read = module.post_approval_sources_readback(row)
    assert read["cell"] == expect_cell, (row, read)
    assert read["sources_n"] == expect_count, (row, read)
    assert read["note"], read


def test_an_old_row_says_unmeasured_instead_of_zero(monkeypatch):
    """run21b 那 8 枚的形状（盘上原件的读数抄在这里）：未量到 ≠ 零枚出处。"""
    module = _load(monkeypatch, False, "old-row")
    row = {"id": "report-02", "kind": "queued_approved",
           "queue": {"final": "awaiting_approval", "terminal": dict(PARKED_SNAPSHOT)}}
    assert row["queue"]["terminal"]["sources_n"] == 0, "快照交回过 0，但它说的是挂起那一刻"
    read = module.post_approval_sources_readback(row)
    assert read["cell"] == module.D3_NO_READBACK, read
    assert read["sources_n"] is None, read
    assert "零枚" in read["note"] or "不许" in read["note"], read



def test_a_readback_that_is_still_parked_is_not_read_zero(monkeypatch, tmp_path):
    """批准后那一发若仍送回挂起态：自成一枚 ``still_parked``，🔴 不许折成 ``read_zero``。

    这一形是本单病根的最近邻：挂起态下 ``sources_n`` 天然就是 0，分类器只看枚数就会把
    「批准还没落到终态」读成「批准后出处为零」——与 run21b 那 8 枚拿挂起快照冒充终态
    是同一枚假零。方向只变严：这一格多拦一枚，永不豁免任何东西。
    """
    module, _payload, fake, _sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "still-parked", extra=[Q.parked_body()])
    assert len(fake.queue_reads) == 2, fake.queue_reads
    cell = frames[0]["queue"]["post_approval"]
    assert cell["read"] is True and cell["outcome"] == "read", cell
    assert cell["terminal"]["state"] == module.PARKED_TERMINAL_STATE, cell
    assert cell["terminal"]["sources_n"] == 0, cell  # 载荷交回的正是那枚诱饵零
    read = module.post_approval_sources_readback(frames[0])
    assert read["cell"] == module.D3_STILL_PARKED and read["sources_n"] is None, read
    assert "挂起" in read["note"], read
    # 快照那一格与批准前一样，仍然没被顶掉，也没被冒充成批准后终态
    assert frames[0]["queue"]["terminal"]["state"] == "awaiting_approval"


# ==================== 五、键集一格不多 + 那枚闸真的会红（判据③） ====================


def test_the_readback_lands_inside_the_queue_cell_not_a_new_column(monkeypatch, tmp_path):
    """🔴 新读数只许长在 ``queue`` 那一格里：帧账一行的键集与在册名单逐字对判。"""
    module, _payload, _fake, sidecar, frames = _parked_then_approved(
        monkeypatch, tmp_path, True, "keyset")
    row = frames[0]
    assert set(row) == Q.FRAME_ROW_KEYS, set(row) ^ Q.FRAME_ROW_KEYS
    assert "sources_rows" not in row["queue"], "出处行是正文，不许抄进第二份证据件"
    assert "sources_rows" not in row["queue"]["post_approval"], "同上：批准后那一格也一样"
    assert set(sidecar[0]) - set(Q.SIDECAR_BASE_KEYS) == Q.R123_EXTRA_KEYS, set(sidecar[0])
    promoted = dict(row)
    promoted["post_approval_terminal"] = {}
    assert set(promoted) != Q.FRAME_ROW_KEYS, "键集闸松了：顶层多一列它都不响"
    demoted = dict(row)
    demoted.pop("uncorrected_breaks")
    assert set(demoted) != Q.FRAME_ROW_KEYS, "键集闸松了：少一列它也不响"


def test_the_stop_vocabulary_did_not_move():
    """判据⑤ 同族：停表词表一字未动 —— AST 现取 ``_poll_queue`` 里与 ``status`` 比的字面。"""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert set(functions) >= {"_poll_queue", "_read_queue_terminal"}
    stops = set()
    for node in ast.walk(functions["_poll_queue"]):
        if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                and node.left.id == "status"):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    stops.add(comparator.value)
                elif isinstance(comparator, ast.Tuple):
                    stops.update(element.value for element in comparator.elts
                                 if isinstance(element, ast.Constant))
    assert stops == {"done", "awaiting_approval", "cancelled", "dead", "expired",
                     "failed"}, stops
    for node in ast.walk(functions["_read_queue_terminal"]):
        assert not (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                    and node.left.id == "status"), "新的读表腿里长出了第二套停表判据"


def test_the_ruler_keeps_one_measuring_leg_per_job(monkeypatch):
    """一把尺：分类器不调 HTTP、不改账，量具里这类名字各只有一处定义。"""
    module = _load(monkeypatch, False, "single-leg")
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for definition in ("def post_approval_sources_readback(", "def _read_queue_terminal(",
                       'D3_READ_SOME = "read_some"'):
        assert source.count(definition) == 1, definition
    body = ast.dump(ast.parse(source))
    classifier = next(node for node in ast.parse(source).body
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "post_approval_sources_readback")
    assert "_open" not in ast.dump(classifier), "读数分类器自己去打出口了 ⇒ 两把尺"
    assert module.POST_APPROVAL_CELL_KEYS == ("read", "outcome", "terminal")


def test_the_summary_publishes_the_knob(monkeypatch, tmp_path):
    """收窗自查得能看见这一格今天量没量：开关状态随 summary 一起交回。"""
    on = _staged(monkeypatch, tmp_path, True, "sum-on")
    off = _staged(monkeypatch, tmp_path, False, "sum-off")
    assert on.summary()["post_approval_readback"] == "on", on.summary()
    assert off.summary()["post_approval_readback"] == "off", off.summary()


def test_the_tracked_ruler_is_byte_identical_after_every_run():
    """本件全程只走假出口、零写入被跟踪文件：跑完原件必须与 import 那一刻逐字节相同。"""
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == IMPORT_SHA