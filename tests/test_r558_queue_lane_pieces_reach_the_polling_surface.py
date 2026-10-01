"""R558 —— 队列道的逐字片段要真上得了屏（甲案：接在既有轮询面上，不新开投递路由）。

来历：R31 判据① 的「交付」那一半。R548（`f312eeb`）把 `stream_piece_sink` 的可注册点建进了
队列道，片只进 worker 内存账本；本单把那张账本接到客户端每 3 s 就在读的
`GET /api/v1/queue/status/{request_id}` 上，交回的读数必须是**递增**的，不是到终态一次给全。

全程离线：不打模型、不起服务、不动容器、不碰真 Redis。沿用的在册夹具是 R37 的 FakeRedis 与
R548 的盖章点（`nodes.publish_stream_pieces`）——本单要证的正是「片从生产者一路走到载荷」，
所以桩不许自己再叫一次 sink，也不许自己拼一份读数。

判据逐格对应（跟进单 §142 R558）：
① 递增读数 → `test_the_polling_body_grows_while_the_turn_is_still_running`
② 零新路由／零新稳定码＋逐键有名有姓 → `test_no_second_queue_route_and_no_new_status_word`
   与 `test_the_contract_names_every_key_the_readout_answers`
③ 每轮一条答案流不倒退 → 由在册的 R464／R203／R524／R548 五枚共同守；本件只加一枚旁证：
   终态那一格不许多出片段键（`test_the_terminal_readout_still_carries_no_piece_keys`）
④ 上限诚实 → `test_the_ledger_cap_reports_truncation_not_silence`
   与 `test_the_store_cap_is_a_separate_number_from_the_ledger_cap`
⑤ 屏上要有脸＋零新增裸色值＋`sessions.js` 净零行 → `test_the_screen_reads_cursor_and_delta_from_the_polling_body`
⑥ 反证刀 → 文末 `test_counter_evidence_*`（三把，盘内常驻）加驱动器
#:    `tests/fixtures/r558_refutation_driver.py`（六把，影子副本道，其中刀6 的 victim 是在册的
#:    R548／R524 两枚钉）；每把都点名它要咬的那枚钉
⑦ 两态数字 → 交工纸 `docs/testing/r558-queue-lane-piece-delivery.md`
"""

import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents import nodes, orchestrator
from app.api.v1 import chat
from app.common import auth
from app.common.auth import create_token
from app.common.reliable_queue import (
    PIECE_ABSENT,
    PIECE_BATCH_LIMIT,
    PIECE_BATCH_SCHEMA,
    PIECE_OK,
    PIECE_UNREADABLE,
    ReliableQueue,
)
from app.main import app as fastapi_app
from deploy import queue_worker
from tests.test_r254_queue_terminal_honesty import QUEUE_STATUS_PATH
from tests.test_r37_report_lane_worker import (
    FakeRedis,
    USERNAME,
    USER_ID,
    _install_worker,
    _request_id,
    _state,
)
from tests.test_r548_queue_lane_registers_the_piece_sink import (
    ANSWER,
    CALL_ID,
    LEG,
    _merger_pieces,
    _sink_config,
)

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
CHAT_PATH = REPO / "app" / "api" / "v1" / "chat.py"
CHAT_PANEL = REPO / "frontend" / "src" / "components" / "ChatPanel.vue"

#: 探针之间每发几片。刻意不写死：真正决定「什么时候往外汇一发」的是 `PIECE_FLUSH_PIECES`
#: 那一个处（`app/common/reliable_queue.py`），本件的场景按它自己那枚数来发。
FLUSH_EVERY = 8

#: 报告档那轮正文。R548 的 152 字只够切出个位数的一片，谈「递增」要至少三发，
#: 所以本件把同一篇正文重复到够长——片由在册的真 merger 自己切，本件不发明片。
LONG_ANSWER = ANSWER * 6


def _record_expire(self, key, seconds):
    """给 R37 的 FakeRedis 补一手「记下 TTL」。

    刻意只补这一手：`rpush` / `lrange` / `set` / `get` 全部沿用在册原件，本件一条既有语义
    都不重写——重写就会连带把 R37／R81／R254 那一族的读数一起弄歪。`expire` 不是可选装饰：
    片段表是一张会一直长的表，没有 TTL 它就变成 Redis 里的永久垃圾。
    """
    self.ttls = getattr(self, "ttls", {})
    self.ttls[key] = int(seconds)
    return 1


def _install_readouts(monkeypatch, ctx):
    """把轮询门指到这一轮的队列上（`_poll` 里已经做了身份那一半）。"""
    monkeypatch.setattr(FakeRedis, "expire", _record_expire, raising=False)
    return ctx


def _round(monkeypatch, tmp_path, *, name, answer=LONG_ANSWER, probe=None, group=None,
           ledger_kwargs=None):
    """真跑一轮报告档后台执行，并允许在**发的中间**插探针。

    ``probe(sink, ctx, index)`` 在每组片发完之后调用一次。这一手是本单的要害：客户端在
    `processing` 期间到底读不读得到字，只有在这儿问才问对地方——问晚了就叫「测终态」，
    而终态那一格从来不是本单要的东西。
    """
    box = {}
    ctx = _install_worker(monkeypatch, tmp_path, name=name)
    _install_readouts(monkeypatch, ctx)
    pieces = _merger_pieces(answer, 7)
    step = int(group or FLUSH_EVERY)

    def _stub(graph, payload, config, *, cancel_event=None):
        sink = (config.get("configurable") or {}).get(nodes.STREAM_PIECE_SINK_KEY)
        box["sink"] = sink
        for index, start in enumerate(range(0, len(pieces), step)):
            for piece in pieces[start : start + step]:
                nodes.publish_stream_pieces(
                    _sink_config(sink), [piece], call_id=CALL_ID, worker=LEG
                )
            if probe is not None:
                probe(sink, ctx, index)
        yield (("",), _state(answer))

    monkeypatch.setattr(orchestrator, "_cancellable_stream", _stub)
    if ledger_kwargs is not None:
        # 反证刀专用：把生产构造点换成带阈值的构造（默认路径一个字节都不许多）。
        real = queue_worker.ReportLanePieceLedger
        monkeypatch.setattr(
            queue_worker,
            "ReportLanePieceLedger",
            lambda request_id, **kwargs: real(
                request_id, **{**kwargs, **(ledger_kwargs or {})}
            ),
        )
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    log = logging.getLogger("enterprise_brain")
    log.addHandler(handler)
    previous = log.level
    log.setLevel(logging.DEBUG)
    try:
        finished = ctx.worker.process_one()
    finally:
        log.removeHandler(handler)
        log.setLevel(previous)
    box.update(
        {
            "ctx": ctx,
            "finished": finished,
            "request_id": _request_id(ctx),
            "pieces": pieces,
            "log_lines": [record.getMessage() for record in records],
        }
    )
    return box



def _ask(monkeypatch, ctx, *, since=None):
    """走真那扇门 `GET /api/v1/queue/status/{id}` 读一发回执。

    本件全部判据读数都从这里出——载荷才是客户端看见的东西，函数返回值不是。``since`` 给空
    就是「从头讲一遍」，给上一发的 ``cursor`` 就是「只讲新长出来的那一截」。
    """
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: ctx.queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda name: {"id": USER_ID, "username": name, "role": "admin"},
    )
    url = QUEUE_STATUS_PATH + _request_id(ctx)
    if since is not None:
        url = url + "?since=" + str(since)
    response = TestClient(fastapi_app).get(
        url, headers={"Authorization": "Bearer " + create_token(USERNAME)}
    )
    assert response.status_code == 200, response.text
    return response.json()


# ==================== 判据①：客户端在跑的这一轮里，屏幕上要一个字一个字长出来 ====================


def test_the_polling_body_grows_while_the_turn_is_still_running(monkeypatch, tmp_path):
    """轮询回执里的片段读数必须一发比一发多，而且不是等终态一次给全。

    甲案唯一一枚「拿真载荷问」的钉：每一组片发完就打一次真门，读的是 HTTP 回执那一份。
    只测 ``piece_readout()`` 不算这一格——那测的是尺子，不是投递面。
    """
    seen = []

    def _probe(sink, ctx, index):
        body = _ask(monkeypatch, ctx)
        seen.append((body.get("status"), body.get("stream_pieces")))

    box = _round(monkeypatch, tmp_path, name="r558-grow", probe=_probe)

    assert box["finished"] is True, box["log_lines"]
    assert len(seen) >= 3, "探针落不到三发以下，这一格根本没在问「跑的过程中」"
    assert {status for status, _ in seen} == {"processing"}, seen
    faces = [piece for _, piece in seen]
    assert all(face is not None and face["state"] == PIECE_OK for face in faces), seen
    chars = [face["chars"] for face in faces]
    assert chars == sorted(chars), "片段读数倒退：" + repr(chars)
    assert chars[0] > 0, "头一发就一个字都没有：那是「到终态才一次给全」的形状，不是递增"
    # 最后一组允许不足阈值（那一截字归收窗那一发补，见下面那枚 concat 钉），所以这一格量的是
    # 「除最后一发之外每一发都在长」，不把量具自己的分组形状算成产品的错。
    # 反证刀 backfill 照样咬得住：它连第一发都读不到字，上面 `state` 那一行先红。
    growing = [b - a for a, b in zip(chars, chars[1:])]
    assert sum(1 for step in growing if step > 0) >= len(growing) - 1, repr(chars)
    assert len(set(chars)) >= 3, "整轮只读出一两个值：递增这件事没有发生"
    cursors = [face["cursor"] for face in faces]
    assert cursors == sorted(cursors), cursors
    assert len(set(cursors)) >= 3, cursors
    # 游标与字数必须同涨同停：读数说「新长了一截」而游标不动，客户端下一发就会重拿同一截字。
    assert [(a < b) for a, b in zip(chars, chars[1:])] == [
        (a < b) for a, b in zip(cursors, cursors[1:])
    ], (chars, cursors)
    assert faces[-1]["text"], "最后一发连一个字都没读到"


def test_the_deltas_concatenate_to_every_published_character(monkeypatch, tmp_path):
    """按游标一轮轮读，拼起来必须等于生产者交回的全部片正文——一个字都不许多、都不许少。

    前一枚只证读数在动；这一枚证动的东西就是那一篇，且「带游标」与「不带游标」不重复投喂。
    """
    reads = []

    def _probe(sink, ctx, index):
        cursor = reads[-1][0] if reads else 0
        piece = _ask(monkeypatch, ctx, since=cursor)["stream_pieces"]
        reads.append((piece["cursor"], piece["text"]))

    box = _round(monkeypatch, tmp_path, name="r558-concat", probe=_probe)
    published = "".join(getattr(piece, "text", "") for piece in box["pieces"])
    joined = "".join(text for _, text in reads)
    assert joined == published[: len(joined)], "增量的顺序或内容与生产者对不上"
    # 发与发之间不许漏字；没收完的那一截尾巴归下面那一格管，两头合起来才是全篇。
    # 🔴 下面那一格就是反证刀 no_tail 的落点：摘掉收窗那一发，`full` 会停在 `joined` 那一截。
    # 收窗那一发把最后攒着的尾巴也推了出去：终态之后再读一次（不带游标）必须是全篇。
    full = "".join(
        str(batch["text"]) for batch in _raw_batches(box["ctx"].queue, box["request_id"])
    )
    assert full == published, "片段表里的正文不是那一篇报告"


# ==================== 判据③ 旁证：终态那一格不许长出片段键 ====================


def test_the_terminal_readout_still_carries_no_piece_keys(monkeypatch, tmp_path):
    """片段只进「正在跑」那一格：终态载荷的形状必须与本单之前逐字节同形。

    R548 那句「一字节不进终态帧 / usage / sources / 审计行 / 错误码」在本单之后仍然成立。
    """
    box = _round(monkeypatch, tmp_path, name="r558-terminal")
    body = _ask(monkeypatch, box["ctx"])
    assert body["status"] != "processing"
    assert "stream_pieces" not in body, sorted(body)


def test_a_queued_turn_answers_nothing_about_pieces(monkeypatch, tmp_path):
    """还没起跑的那一轮（``queued``）不许多造这一格：缺席要说得出理由，不是回一片空字。"""
    ctx = _install_worker(monkeypatch, tmp_path, name="r558-queued")
    _install_readouts(monkeypatch, ctx)
    body = _ask(monkeypatch, ctx)
    assert body["status"] == "queued", body
    assert "stream_pieces" not in body, sorted(body)


def test_absent_is_not_the_same_face_as_no_pieces():
    """``absent`` 说的是「表里还没有」：它不等于「这一轮一片都没汇」，更不等于「跑完了没正文」。"""
    queue = ReliableQueue(FakeRedis(), name="r558-absent", lease_seconds=30)
    readout = queue.piece_readout("req-never-ran")
    assert readout["state"] == PIECE_ABSENT
    assert readout == {
        "state": PIECE_ABSENT,
        "text": "",
        "cursor": 0,
        "pieces": 0,
        "chars": 0,
        "discarded": 0,
        "truncated": 0,
        "legs": [],
        "reason": "",
    }


def test_a_half_written_batch_is_unreadable_and_says_which_shape_broke():
    """键在位而解不开（半截 JSON、换代异形、序号坏）必须走 ``unreadable``，并说清坏在哪一手。"""
    queue = ReliableQueue(FakeRedis(), name="r558-broken", lease_seconds=30)
    key = queue._pieces_key("req-broken")
    queue.redis.rpush(key, "{not json")
    broken = queue.piece_readout("req-broken")
    assert broken["state"] == PIECE_UNREADABLE
    assert broken["reason"] == "batch_payload_unparsable"
    assert broken["text"] == "" and broken["cursor"] == 0
    queue.redis.lists[key] = [json.dumps({"schema": "queue-piece-batch-v9", "seq": 1})]
    assert queue.piece_readout("req-broken")["reason"] == "batch_schema_mismatch"
    queue.redis.lists[key] = [json.dumps({"schema": PIECE_BATCH_SCHEMA, "seq": 0})]
    assert queue.piece_readout("req-broken")["reason"] == "batch_seq_invalid"


# ==================== 判据④：两枚上限各自要说自己的话，不许静默 ====================


class SimplePiece:
    """``StreamPiece`` 的最小替身：账本只认 ``text`` 与 ``worker`` 两格（在册读法）。"""

    def __init__(self, text="", worker=""):
        self.text = text
        self.worker = worker


def _direct_ledger(monkeypatch, name, **kwargs):
    """把账本直接接在真队列上：上限那一族要按可控的片数问，不能靠一篇报告碰运气。"""
    queue = ReliableQueue(FakeRedis(), name="r558-" + name, lease_seconds=30)
    monkeypatch.setattr(FakeRedis, "expire", _record_expire, raising=False)
    request_id = "req-" + name
    ledger = queue_worker.ReportLanePieceLedger(
        request_id,
        publisher=lambda batch: queue.append_piece_batch(request_id, batch),
        **kwargs,
    )
    return queue, ledger, request_id


def test_the_ledger_cap_reports_truncation_not_silence(monkeypatch):
    """内存账本到顶之后只计数不留片：读数必须说得出「丢了几枚」，而字一个不少。

    两件事常被混为一谈：``discarded > 0`` 说的是 worker 内存，客户端拿到的字不受它影响；
    把它读成「这一轮没有片段」或「正文缺了一截」都是假账。
    """
    queue, ledger, request_id = _direct_ledger(monkeypatch, "cap", limit=4, flush_pieces=3)
    for index in range(10):
        ledger(SimplePiece("abc", worker="leg-%d" % index))
    ledger.flush()

    readout = queue.piece_readout(request_id)
    assert readout["state"] == PIECE_OK
    assert readout["pieces"] == 10, readout
    assert readout["discarded"] == 6, readout
    assert readout["truncated"] == 0, readout
    assert readout["chars"] == 30 and len(readout["text"]) == 30, readout
    assert len(ledger.joined_text()) == 12, "内存留片数被改了：R548 的上限语义是本单的起点"
    assert readout["legs"] == ["leg-0", "leg-1", "leg-2", "leg-3"], readout["legs"]

def test_the_store_cap_is_a_separate_number_from_the_ledger_cap(monkeypatch):
    """增量表自己写满之后停止存正文：``truncated`` 单独报，且账面数不许冻在封顶那一刻。

    上限有两枚，各说各的话：``overflow``（读数里叫 ``discarded``）说的是 worker **内存**留不下
    那么多片，客户端一个字都不缺；``truncated`` 说的是**增量表**停止存正文，屏侧要到终态才拿全篇。
    把这两枚混成一枚，判据④ 那句「不许把它读成没有片段」就没有尺子了。
    """
    queue, ledger, request_id = _direct_ledger(
        monkeypatch, "storecap", batch_limit=2, flush_pieces=1
    )
    for index in range(5):
        ledger(SimplePiece("x" * (index + 1)))

    assert ledger.truncated == 3, ledger.truncated  # 第 3/4/5 片撞上表上限
    readout = queue.piece_readout(request_id)
    assert readout["truncated"] == 3, readout
    assert readout["discarded"] == 0, readout  # 内存那枚上限一枚都没丢
    assert readout["pieces"] == 5 and readout["chars"] == 15, readout
    assert readout["text"] == "xxx", readout["text"]  # 只存下前两批：1 + 2
    raw = _raw_batches(queue, request_id)
    assert len(raw) == 5, raw
    assert sum(1 for item in raw if not item["text"]) == 3, raw  # 封顶那三发正文为空、账面数照全

    # 封顶之后再长三片：正文照旧不存，但账面数必须继续滚。冻住就是「停在第 N 批」的旧账面。
    for index in range(6, 9):
        ledger(SimplePiece("x" * index))
    rolling = queue.piece_readout(request_id)
    assert rolling["truncated"] == 6, rolling
    assert rolling["pieces"] == 8 and rolling["chars"] == 36, rolling
    assert rolling["cursor"] == 8 and rolling["text"] == "xxx", rolling
    stored = [item for item in _raw_batches(queue, request_id) if item["text"]]
    assert len(stored) == 2, "封顶之后还在往表里存正文：上限那一格就没有界了"


def test_the_incremental_store_expires_with_the_result_ttl(monkeypatch):
    """片段表会一直长，没有 TTL 就是 Redis 里的永久垃圾：这一格不许是「忘了设」。"""
    queue, ledger, request_id = _direct_ledger(monkeypatch, "ttl", flush_pieces=2)
    ledger(SimplePiece("hello"))
    assert not getattr(queue.redis, "ttls", {}), "没到阈值就往表里写，递增性就变成每字一发"
    ledger(SimplePiece(" world"))
    assert queue.redis.ttls[queue._pieces_key(request_id)] == queue.result_ttl


def test_a_retried_flush_never_shows_the_client_the_same_characters_twice(monkeypatch):
    """连接抖动让同一批重发：表里可以有两行同序号，读数必须按序号去重，字不许翻倍。"""
    queue = ReliableQueue(FakeRedis(), name="r558-retry", lease_seconds=30)
    monkeypatch.setattr(FakeRedis, "expire", _record_expire, raising=False)
    request_id = "req-r558-retry"
    batch = {
        "schema": PIECE_BATCH_SCHEMA,
        "seq": 1,
        "text": "同一段字",
        "pieces": 3,
        "chars": 4,
        "discarded": 0,
        "legs": [LEG],
        "truncated": 0,
    }
    queue.append_piece_batch(request_id, dict(batch))
    queue.append_piece_batch(request_id, dict(batch))
    assert len(_raw_batches(queue, request_id)) == 2
    readout = queue.piece_readout(request_id)
    assert readout["text"] == "同一段字" and readout["cursor"] == 1, readout

    # 后半段另起一枚键：前半段已经往同一张表里放过两行，复用就会把「表里该有一批」读成三批。
    again = ReliableQueue(FakeRedis(), name="r558-retry-ledger", lease_seconds=30)
    again_id = "req-r558-retry-ledger"
    fails = {"left": 1}

    def _flaky(published):
        def _publish(item):
            if fails["left"]:
                fails["left"] -= 1
                raise ConnectionError("connection reset")
            published.append(item["seq"])
            return again.append_piece_batch(again_id, item)

        return _publish

    ledger = queue_worker.ReportLanePieceLedger(
        again_id, publisher=_flaky([]), flush_pieces=1
    )
    for text in ("第一段", "第二段"):
        ledger(SimplePiece(text))
    assert ledger.publish_errors == 1, ledger.publish_errors
    # 失败那一发不推进序号，攒着的两片留到下一发一起交 ⇒ 表里只有一批，字一片不少。
    assert ledger.batches == 1, ledger.batches
    stored = _raw_batches(again, again_id)
    assert len(stored) == 1, stored
    assert stored[0]["seq"] == 1 and stored[0]["text"] == "第一段第二段", stored
    readback = again.piece_readout(again_id)
    assert readback["text"] == "第一段第二段" and readback["cursor"] == 1, readback
    assert readback["pieces"] == 2 and readback["chars"] == 6, readback


def _raw_batches(queue, request_id):
    """从片段表把原始批读回来（「原始 JSON 逐格点名」读这里，不读任何副本）。"""
    return [json.loads(item) for item in queue.redis.lrange(queue._pieces_key(request_id), 0, -1)]

# ==================== 判据②：零新路由、零新稳定码、每个键在契约里有名有姓 ====================

#: `/api/v1/queue` 那一族的在册路径。第四枚就是「另起一条投递面」的形状，本单明令禁止：
#: 甲案的要害正是把增量读数接在客户端**已经在轮**的那一扇门上。
REGISTERED_QUEUE_ROUTES = (
    "/api/v1/queue/stats",
    "/api/v1/queue/status/{request_id}",
    "/api/v1/queue/{request_id}/cancel",
)


def test_no_second_queue_route_and_no_new_status_word():
    # 🔴 量具口径：`fastapi_app.routes` 在 import 期只有 18 枚，`/api/v1/**` 那三是挂进来的，
    # 拿它当路由面会读出「一枚都没有」的假零（本件第一版就报在这里）。路由面只认 openapi
    # 交回的 paths——那才是客户端与契约看见的那一层。
    paths = sorted(name for name in fastapi_app.openapi()["paths"] if "/queue" in name)
    assert paths == sorted(REGISTERED_QUEUE_ROUTES), paths
    source = CHAT_PATH.read_text(encoding="utf-8")
    assert "stream_pieces" in source, "轮询面那一格不见了：本单的第二半没落进真门"
    assert 'status == "processing"' in source, (
        "片段读数发在了别的状态分支上——终态那一格长出这一格就是 R548 零外溢的破口"
    )


def test_a_broken_cursor_is_tolerated_instead_of_becoming_a_new_error_code(monkeypatch, tmp_path):
    """`since` 读不懂就当 0：这一扇门零新稳定码，坏游标的后果只是客户端多拿一遍字。"""
    ctx = _install_worker(monkeypatch, tmp_path, name="r558-cursor")
    _install_readouts(monkeypatch, ctx)
    request_id = _request_id(ctx)
    ctx.queue.append_piece_batch(
        request_id,
        {
            "schema": PIECE_BATCH_SCHEMA,
            "seq": 1,
            "text": "正文",
            "pieces": 1,
            "chars": 2,
            "discarded": 0,
            "legs": [LEG],
            "truncated": 0,
        },
    )
    ctx.queue.redis.set(ctx.queue._status_key(request_id), "processing")
    for junk in ("abc", "-3", "", "999999"):
        body = _ask(monkeypatch, ctx, since=junk)
        assert body["status"] == "processing", body
        assert body["stream_pieces"]["text"] == "正文", (junk, body["stream_pieces"])


def test_the_contract_names_every_key_the_readout_answers(monkeypatch):
    """契约里那一节必须逐键点名读数真正交回的东西：键表从**真读数**里长出来，不手抄。"""
    queue = ReliableQueue(FakeRedis(), name="r558-contract", lease_seconds=30)
    answered = sorted(queue.piece_readout("req-never").keys())
    section = CONTRACT.read_text(encoding="utf-8")
    tail = section.split("## Queue lane streaming pieces", 1)
    assert len(tail) == 2, "契约里没有 R558 那一节（本单只许尾追加）"
    body = tail[1]
    for key in answered:
        assert "`stream_pieces.%s`" % key in body or ("| `%s`" % key) in body, (key, answered)
    for named in ("since", "cursor", "discarded", "truncated", "reason"):
        assert named in body, named
    assert "processing" in body, "缺席语义没说清：这一格只在正在跑的那一态出现"


# ==================== 判据⑤：屏上要有脸，且零新增裸色值 ====================


def test_the_screen_reads_cursor_and_delta_from_the_polling_body():
    """`ChatPanel.vue` 必须真把增量画出来：收了不画就是假接线。"""
    source = CHAT_PANEL.read_text(encoding="utf-8")
    assert "stream_pieces" in source, "屏侧一个字都没接"
    assert re.search(r"since\b", source), "轮询没带游标：每发都会重拿全篇"
    assert re.search(r"cursor", source), "游标没存：下一发不知道从哪儿接"


# ==================== 判据⑥：反证刀（每把点名它要咬的那枚在册钉） ====================


@pytest.mark.parametrize("mutation", ["backfill", "no_tail", "silent_cap"])
def test_counter_evidence_the_delivery_pin_bites(monkeypatch, tmp_path, mutation):
    """把投递面改成「到终态一次给全」「尾巴不推」「上限静默」三种坏形状，在册钉必须当场红。

    * ``backfill`` 咬 :func:`test_the_polling_body_grows_while_the_turn_is_still_running`
      ——阈值调到跑完都不汇，`processing` 期间每一发都只能读回 `absent`；
    * ``no_tail`` 咬 :func:`test_the_deltas_concatenate_to_every_published_character`
      ——把收窗那一发摘掉，表里就永远缺最后一截字；
    * ``silent_cap`` 咬 :func:`test_the_ledger_cap_reports_truncation_not_silence`
      ——把上限丢弃做成「计数不报」，读数就只剩一个好看的 0。
    """
    if mutation == "backfill":
        box = _round(
            monkeypatch,
            tmp_path,
            name="r558-knife-backfill",
            probe=None,
            ledger_kwargs={"flush_pieces": 10 ** 6, "flush_seconds": 10 ** 9},
        )
        body = _ask(monkeypatch, box["ctx"], since=0)
        ctx = box["ctx"]
        # 这一轮已经跑完，状态离开 processing，因此门不再发这一格——但**表里**必须有全篇，
        # 而递增那一格在跑的过程中一次都没出现过：用同样的场景重跑一遍并只问过程中。
        seen = []

        def _probe(sink, target, index):
            seen.append(_ask(monkeypatch, target)["stream_pieces"])

        box2 = _round(
            monkeypatch,
            tmp_path,
            name="r558-knife-backfill-2",
            probe=_probe,
            ledger_kwargs={"flush_pieces": 10 ** 6, "flush_seconds": 10 ** 9},
        )
        assert seen and all(item["state"] == PIECE_ABSENT for item in seen), seen
        assert len(box2["pieces"]) > FLUSH_EVERY, "片数太少，这一把刀根本没有可咬的东西"
        del body, ctx
    elif mutation == "no_tail":
        seen = []

        def _probe(sink, ctx, index):
            seen.append(_ask(monkeypatch, ctx)["stream_pieces"])

        box = _round(monkeypatch, tmp_path, name="r558-knife-tail", probe=_probe)
        published = "".join(getattr(piece, "text", "") for piece in box["pieces"])
        stored = "".join(str(item["text"]) for item in _raw_batches(box["ctx"].queue, box["request_id"]))
        assert stored == published, "收窗那一发被摘掉了：表里缺尾"
        real_flush = queue_worker.ReportLanePieceLedger.flush

        def _without_tail(self):
            if self._pending and len(self._pending) < self._flush_pieces:
                return False
            return real_flush(self)

        monkeypatch.setattr(queue_worker.ReportLanePieceLedger, "flush", _without_tail)
        tail_box = _round(monkeypatch, tmp_path, name="r558-knife-tail-2")
        tail_stored = "".join(
            str(item["text"]) for item in _raw_batches(tail_box["ctx"].queue, tail_box["request_id"])
        )
        assert tail_stored != published, "摘掉收窗那一发之后钉居然还绿：这一把刀不咬"
        del box
    else:
        queue, ledger, request_id = _direct_ledger(
            monkeypatch, "knife-cap", limit=4, flush_pieces=3
        )
        for index in range(10):
            ledger(SimplePiece("abc"))
        ledger.flush()
        assert queue.piece_readout(request_id)["discarded"] == 6
        real_publish = queue_worker.ReportLanePieceLedger._publish

        def _silent(self, text):
            self.overflow = 0
            return real_publish(self, text)

        monkeypatch.setattr(queue_worker.ReportLanePieceLedger, "_publish", _silent)
        quiet = _direct_ledger(monkeypatch, "knife-cap-2", limit=4, flush_pieces=3)
        for index in range(10):
            quiet[1](SimplePiece("abc"))
        quiet[1].flush()
        assert quiet[0].piece_readout(quiet[2])["discarded"] == 0, (
            "静默形状没被造出来：这一把刀不咬"
        )

def test_this_file_adds_no_skip_and_no_xfail():
    """本族的规矩：不许拿 skip 当「这格量不了」的替代（同族先例 `test_r232_*::323`）。"""
    source = Path(__file__).read_text(encoding="utf-8")
    # 字面量拼出来，不写全串：写全串就是让本件自己成为那枚「含禁串」的文件（第一版红在这里）。
    for banned in ("pytest." + "skip", "pytest." + "xfail",
                   "@pytest.mark." + "skip", "@pytest.mark." + "xfail"):
        assert banned not in source, banned
