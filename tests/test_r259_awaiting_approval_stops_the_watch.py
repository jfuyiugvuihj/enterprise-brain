# -*- coding: utf-8 -*-
"""R259 判据① + ⑤：队列那枚新终态必须停表，而五枚既有终态一字不许改。

判据原文（派工词 R259 ①）：``_poll_queue`` 读到 ``awaiting_approval`` 必须**立刻停表**，并交回
一枚可区分的 ``kind`` —— 不许并进 ``queued_polled``（那枚说的是「取回了一份字」），不许叫
``ok``，不许与 ``queued_done_no_bytes``（那枚说的是「跑完了但没正文」）混用；这一枚说的是
「一步没走、在等人批准」。停表之后 ``final`` / ``last_status`` 两格要能看出是哪枚状态。
判据⑤：``done`` / ``cancelled`` / ``dead`` / ``expired`` / ``failed`` 各自的 kind 与语义一字
不改，新加一枚不等于可以重排旧的。

不修的后果（现算，``docs/testing/run8-phase2-readout-2026-09-25.md`` §1）：相 2 那 20 题报告档
有 **11 题挂在 HITL**，下一扇窗它们会一路轮到 ``QUEUE_STALL_SECONDS``（300 s）才落
``queued_stalled`` ⇒ 约 55 min 白烧，D-1/D-2/D-3 三格读数全被污染。

🔴 形状铁规（判据① 后半段）：新状态字面必须以 ``if status == "awaiting_approval":`` 留在
``_poll_queue`` 函数体里 —— 总控的 ``scripts/r218_switch_rehearsal.py::adapter_stop_vocabulary``
是按 AST 抠「与名为 ``status`` 的名字比较的**字面量**」。改成集合查表那枚钉当场瞎掉，而停表
行为一模一样：那是「量具有牙」这句主张的一种新形状的假绿。反证甲与反证丁各钉一刀，丁还亲自
复算「行为不变而读数变瞎」这一对。

全程离线：假出口 + 假钟，零服务 / 零模型 / 零容器 / 零连库 / 零真跑分，两份产物落 tmp_path。
"""
import json
import re

import pytest

from tests import _r259_queue_ruler as Q

REPO_ROOT = Q.REPO_ROOT
SCRIPT_PATH = Q.SCRIPT_PATH
PARKED_KIND = Q.PARKED_KIND
#: R447 判据②：队列道那一轮挂起被批准到终答之后落的 kind（与量具常量在用例里逐字对判）。
QUEUED_APPROVED_KIND = "queued_approved"
#: 取回账里那一族读数：五枚既有终态 + 本单新终态 + 三枚没读到终局 = 十枚 kind。
ALL_QUEUE_KINDS = ("queued_polled", "queued_done_no_bytes", PARKED_KIND,
                   "queued_cancelled", "queued_dead", "queued_expired", "queued_failed",
                   "queued_stalled", "queued_deadline", "queued_no_status")
#: 反证甲的锚点：把新终态从停表条件里摘掉（只改那一枚字面，别的一动不动）。
DROP_PARKED_STOP = ('        if status == "awaiting_approval":',
                    '        if status == "awaiting_approval_never_written_by_any_queue":')
#: 反证丁的锚点：把字面量搬进集合 ⇒ 行为不变、AST 钉变瞎（那正是派工词点名的假绿形状）。
LITERAL_INTO_SET = ('        if status == "awaiting_approval":',
                    "        if status in _PARKED_STATUSES:",
                    "\n\n\n_PENDING_STATUSES_UNUSED = 0\n"
                    "_PARKED_STATUSES = {\"awaiting_approval\"}\n")


@pytest.fixture
def adapter(tmp_path):
    return Q.configure(Q.load("r259_stopwatch"), tmp_path, name="r259-a")


def parked_readings(module, rounds=500):
    """把挂起那一枚喂进真 ``_poll_queue``：回 (kind, 正文, 取回账, 假出口)。"""
    statuses = [json.loads(json.dumps(Q.parked_body())) for _ in range(rounds)]
    (kind, answer, book), fake = Q.poll(module, statuses)
    return kind, answer, book, fake


def assert_parked_stops(module):
    """判据① 的点名断言：反证甲摘掉停表条件 ⇒ 红必须落在这里、落在 ``kind`` 那一格。"""
    kind, answer, book, fake = parked_readings(module)
    assert kind == PARKED_KIND, (
        "kind=" + repr(kind) + " ⇒ 挂起在等人批准的那一轮没被认成终态（判据①）")
    assert answer == "", "正文那一格必须是空串：契约里这一枚的 result 恒为 null"
    assert book["final"] == "awaiting_approval", (
        "final=" + repr(book["final"]) + " ⇒ 停表之后看不出挂在哪一枚状态")
    assert book["last_status"] == "awaiting_approval", (
        "last_status=" + repr(book["last_status"]) + " ⇒ 最后一枚读数没记账")
    assert len(fake.queue_reads) == 1, "读到终态还接着轮 ⇒ 白烧没修掉"
    assert module.time.slept == [], "停表之后不许再睡一枚轮询间隔"
    assert book["polls"] == 1 and book["wait_ms"] == 0.0
    return book


# ==================== ① 新终态停表 ====================

def test_awaiting_approval_stops_the_watch_with_its_own_kind(adapter):
    """读到 ``awaiting_approval`` 就停：一枚轮询间隔都不许多睡，kind 自成一枚。"""
    assert_parked_stops(adapter)


def test_a_parked_turn_reads_the_clock_exactly_like_an_existing_terminal(tmp_path):
    """钟的纪律：新终态的读表次数与一枚既有终态逐格相同（多读一格就推走 105 题重放的时间轴）。"""
    parked = Q.configure(Q.load("r259_clock_parked"), tmp_path / "parked")
    dead = Q.configure(Q.load("r259_clock_dead"), tmp_path / "dead")
    parked_readings(parked, rounds=1)
    Q.poll(dead, [json.loads(json.dumps(Q.bare_done_body(status="dead")))])
    assert parked.time.reads == dead.time.reads == 2, (
        "读表次数 " + str(parked.time.reads) + " vs " + str(dead.time.reads)
        + "：外圈一枚 + 本轮一枚，本单一枚都不许多")


def test_the_parked_kind_is_distinct_from_every_other_queue_reading(adapter):
    """可统计：十枚取回读数两两不同，且没有一枚叫 ``ok``；三枚「没正文」各说各的事。"""
    seen = {}
    for status, expected in sorted(Q.FINAL_KINDS.items()):
        body = {"status": status}
        if status == "done":
            body["result"] = Q.ANSWER
        seen[status] = Q.poll(adapter, [body])[0][0]
    seen["done_no_bytes"] = Q.poll(adapter, [{"status": "done"}])[0][0]
    seen["parked"] = Q.poll(adapter, [Q.parked_body()])[0][0]
    seen["stalled"] = Q.poll(adapter, [{"status": "processing"}] * 500)[0][0]
    seen["deadline"] = Q.poll(
        adapter, [{"status": "queued", "position": n + 1} for n in range(400)])[0][0]
    seen["no_status"] = Q.poll(adapter, [Q.url_error()] * 400)[0][0]
    assert sorted(seen.values()) == sorted(ALL_QUEUE_KINDS), seen
    assert len(set(seen.values())) == 10
    assert "ok" not in seen.values()
    assert seen["parked"] not in ("queued_polled", "queued_done_no_bytes")


@pytest.mark.parametrize("status", sorted(Q.FINAL_KINDS))
def test_the_five_existing_terminal_kinds_are_unchanged(adapter, status):
    """判据⑤：五枚既有终态逐枚不许多不许少，kind、正文与停表语义一字不改。"""
    body = {"status": status}
    if status == "done":
        body["result"] = Q.ANSWER
    (kind, answer, book), fake = Q.poll(adapter, [body] * 5)
    assert kind == Q.FINAL_KINDS[status]
    assert kind != "ok" and kind != PARKED_KIND
    assert book["final"] == ("done" if status == "done" else status)
    assert len(fake.queue_reads) == 1 and adapter.time.slept == []
    assert (answer == Q.ANSWER) is (status == "done")


# ==================== ① + 落盘：kind 与取回账一起进两份证据件 ====================

def test_a_parked_turn_lands_in_both_artifacts_without_laundering_the_notice(adapter):
    """挂起的一轮：两份证据件都认得它，而那句 37 字挂起文案一个字都不进正文面。

    🔴 自 R447 判据① 起这一枚的**结局**换了：量具读到 ``awaiting_approval`` 就真打一发
    ``/api/v1/approve``，批到终答 ⇒ ``kind`` 落 ``queued_approved``；而**停表读数**照旧留在
    ``pre_kind`` 与帧账 ``queue.final`` 两格里 ——「一步没走」那句话今天还是真话，只是不再
    等于结局。本件其余用例（键集账、白烧闸账）判的都是这一腿走完之后的账，一字未改口。
    """
    payload, fake, sidecar, frames = Q.drive_queue(adapter, [Q.parked_body()] * 5)
    record, row = sidecar[0], frames[0]
    assert payload["answer"] == Q.ANSWER  # R447：交回评分器的是恢复流的终答，不再是零字节哨兵
    assert payload["evidence"] == [] and payload["first_token_at"] is None
    assert record["kind"] == row["kind"] == adapter.QUEUED_APPROVED_KIND == QUEUED_APPROVED_KIND
    assert record["sentinel"] is False and record["pre_kind"] == PARKED_KIND
    assert len(fake.approve_reads) == 1, "批准轮没走 ⇒ R447 判据① 在这一枚用例上脱钩了"
    assert row["queue"]["final"] == "awaiting_approval"
    assert row["queue"]["terminal"]["state"] == "awaiting_approval"
    assert len(fake.queue_reads) == 1
    written = (adapter.SIDECAR.read_text(encoding="utf-8")
               + adapter.frame_ledger_path().read_text(encoding="utf-8"))
    assert Q.PARK_NOTICE not in written, "挂起文案又冒充正文了（R254 判据① 拆的那枚谎）"
    assert Q.PARK_NOTICE not in json.dumps(payload, ensure_ascii=False, default=str)


def test_sidecar_and_frame_rows_gained_no_column(adapter):
    """判据⑥：sidecar 九键 + 甲案七键、帧账那一行的键集一个字没多（读数只长在 queue 那一格里）。"""
    Q.drive_queue(adapter, [Q.parked_body()] * 5)
    record = Q.read_jsonl(adapter.SIDECAR)[0]
    row = Q.read_jsonl(adapter.frame_ledger_path())[0]
    assert tuple(list(record)[:9]) == Q.SIDECAR_BASE_KEYS
    assert set(record) - set(Q.SIDECAR_BASE_KEYS) <= (Q.R123_EXTRA_KEYS | {"pre_answer"})
    assert set(row) == Q.FRAME_ROW_KEYS, set(row) ^ Q.FRAME_ROW_KEYS
    assert "terminal" not in row and "terminal" in row["queue"]


def test_parked_turns_do_not_burn_the_window_down(adapter):
    """挂起是产品结局，不喂「零字节超阈值停窗」那把闸：11/20 挂起的窗不许在第 6 题停摆。"""
    adapter.MAX_BLANKS = 0
    for index in range(1, 3):
        Q.drive_queue(adapter, [Q.parked_body()] * 5, row_id="doc-%02d" % index)
    assert adapter._PARKED == 2 and adapter._BLANKS == 0
    assert adapter.summary()["awaiting_approval_turns"] == 2


def test_the_blank_safety_valve_still_bites_the_existing_kinds(adapter):
    """对照：那一把闸对既有终态一族一个字没松（``dead`` 交回零字节照样停窗）。"""
    adapter.MAX_BLANKS = 0
    with pytest.raises(RuntimeError) as exc:
        Q.drive_queue(adapter, [Q.bare_done_body(status="dead")] * 5)
    assert "零字节题数已超" in str(exc.value)
    assert adapter._PARKED == 0 and adapter._BLANKS == 1


# ==================== 🔴 形状铁规：字面量必须在 status 那一侧 ====================

def test_the_master_nail_still_reads_the_new_stop_word():
    """``adapter_stop_vocabulary`` 抠得到新终态，也照旧抠得到那五枚（一盲就是假绿）。"""
    stops = Q.stop_vocabulary(REPO_ROOT)
    assert "awaiting_approval" in stops, stops
    assert set(Q.FINAL_KINDS) <= set(stops), stops
    assert stops == sorted(set(stops))


def test_the_parked_stop_is_a_literal_compared_with_status():
    """字面形状：``status == "..."``，不是常量名、不是集合、不是查表。"""
    text = SCRIPT_PATH.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert '        if status == "awaiting_approval":\n' in text
    assert 'status in {"awaiting_approval"' not in text
    assert not re.search(r"status\s+(?:==|in|!=)\s*[A-Z_][A-Z0-9_]{2,}", text), \
        "与 status 比的是常量名 ⇒ 那枚 AST 钉看不见这一格"


# ==================== ④ 反证（红必须落在本格，原件一字不动） ====================

def test_counter_evidence_dropping_the_parked_stop_goes_red_here(tmp_path):
    """反证甲：把新终态从停表条件里摘掉 ⇒ 白烧回来，红点名落在 ``kind`` 那一格。"""
    module, _ = Q.mutant(tmp_path, "drop_parked_stop", *DROP_PARKED_STOP)
    with pytest.raises(AssertionError) as exc:
        assert_parked_stops(module)
    assert "没被认成终态（判据①）" in str(exc.value), str(exc.value)
    kind, _answer, book, fake = parked_readings(module)
    assert kind == "queued_stalled" and book["final"] == "stalled"
    assert len(fake.queue_reads) > 1 and module.time.slept, "白烧没回来 ⇒ 这枚钉是空的"
    assert book["wait_ms"] == pytest.approx(module.QUEUE_STALL_SECONDS * 1000.0)


def test_counter_evidence_moving_the_literal_into_a_set_blinds_the_master_nail(tmp_path):
    """反证丁：改成集合查表 ⇒ 停表行为一模一样，而总控那枚 AST 钉从此读不到这一格。"""
    module, target = Q.mutant(tmp_path, "parked_literal_into_a_set", *LITERAL_INTO_SET)
    kind, answer, book, _fake = parked_readings(module)
    assert (kind, answer, book["final"]) == (PARKED_KIND, "", "awaiting_approval"), \
        "行为若跟着变，红的就是别的东西，证不了「读表钉会瞎」这一格"
    overlay = tmp_path / "overlay"
    script = overlay / "scripts" / "eval_transport_ask_v2.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(target.read_bytes())
    assert "awaiting_approval" not in Q.stop_vocabulary(overlay), \
        "钉还看得见 ⇒ 集合查表并非假绿，那条形状铁规就没有依据"
    assert "awaiting_approval" in Q.stop_vocabulary(REPO_ROOT)
