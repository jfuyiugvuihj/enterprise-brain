# -*- coding: utf-8 -*-
"""R222 判据①②③：入队那一道的停表 —— 五枚终态各一枚 kind，而瞬断永远不算终局。

判据原文：施工单 R222 §判据。全程离线：量具的 ``_open`` 换成会记账的假出口，零服务 /
零模型 / 零容器 / 零连库 / 零真跑分（一发都不许打 ``/api/v1/ask``、``/api/v1/login`` 或
Ollama）。两份产物都写 tmp_path，仓内零字节。钟是假钟：只有 ``sleep`` 会让时间走 ⇒
「这一条轮询白烧了多久」= 睡了几次 × 间隔，判据③ 那两枚上限才算得准。

钉住的六件事：
  ① 五枚终态（``done`` / ``cancelled`` / ``dead`` / ``expired`` / ``failed``）逐枚一枚可区分
     的 kind，全部与 ``ok`` 不同名；``cancelled`` / ``dead`` 交回空正文 —— 后端说这一轮不会
     再有正文，量具就不许把它当成模型答完了；``done`` 而 result 不是正文 ⇒ ``queued_done_no_bytes``。
  ② 瞬断不算终态（前端 R198/R202 同一族口径）：非 2xx / 连不通 / JSON 解不开 / 载荷不是
     对象 —— 一律只记一次抖动接着轮；401 换票接着读。读到 done 照常把正文交回。
  ③ 白烧上限降下来了：未识别终态读到就停（不睡一秒）；载荷不再变化的封在
     ``EVAL_QUEUE_STALL_SECONDS``（默认 300 s = 后端自己的 lease_seconds）；只有「状态一直在
     动」才允许等到 ``EVAL_QUEUE_POLL_SECONDS``（900 s）那一枚外圈。
  ④ 在途态（``queued`` / ``processing`` / ``cancel_requested``）不算终局，也不交回正文。
  ⑤ 取回账（polls / blips / relogins / final / wait_ms）落进帧账新格 ``queue``；sidecar 那九键
     与甲案七键一个字没多（``tests/test_r123_hitl_approval.py:243`` 那枚子集钉不塌）。
  ⑥ 三枚反证钉（临时根副本，跟踪里的原件一字不动）：把 cancelled/dead 的停表摘掉、把瞬断
     当终局、把白烧当答完 —— 红都落在本格。

🔴 抬头口径（判据⑤）：**run8 的适配器 ≠ run6 / run7 的适配器。** kind 词汇表自本单起多出
``queued_*`` 这一族，旧轮次一枚也不可能有（本树实取：run6 帧账 kind 只有 ok / approved_ok /
error_event，run7 只有 ok / approved_ok）⇒ 新读数不追溯历史，拿旧件重放只会长出空列。
"""
import importlib.util
import io
import json
import socket
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"

BODY = "据统计，Q3 营收 1200 万元，环比增长 8%。"
TOKEN_VALUE = "eval-bearer-token"
#: 五枚终态 → 各自的 kind。名单在 tests 这一侧独立抄一份，与量具的实跑读数对判
#: （``test_the_five_final_kinds_are_pairwise_distinct_and_not_ok``）：两边谁漂了都红。
FINAL_KINDS = {"done": "queued_polled", "cancelled": "queued_cancelled",
               "dead": "queued_dead", "expired": "queued_expired",
               "failed": "queued_failed"}
#: sidecar 既有九键（顺序也钉）+ 甲案七键：本单一枚都不许多。
SIDECAR_BASE_KEYS = ("id", "kind", "attempt", "sentinel", "evidence_n",
                     "answer_chars", "tool_calls", "wall_ms", "ts")
R123_EXTRA_KEYS = {"pre_kind", "pre_answer_chars", "pre_evidence_n", "approved",
                   "approval_rounds", "approval_http_status", "approval_error"}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    """假钟：``sleep`` 把钟拨过去，``time`` / ``monotonic`` 自己不走。"""

    def __init__(self, start=1790000000.0):
        self.now = start
        self.slept = []

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(float(seconds))
        self.now += float(seconds)

    def strftime(self, fmt):
        return "FIXED-TS"


class FakeResponse:
    """一发假出口：JSON 体走 ``read()``，SSE 流走 ``__iter__()``。"""

    def __init__(self, body=b"{}", lines=()):
        self._body = body
        self._lines = list(lines)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def __iter__(self):
        return iter(self._lines)


def sse(events):
    """服务端每事件三行：event / data / 空行（app/api/v1/chat.py:222-223）。"""
    lines = []
    for name, data in events:
        lines.append(("event: " + name + "\n").encode("utf-8"))
        lines.append(("data: " + json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        lines.append(b"\n")
    return lines


def http_error(code):
    return urllib.error.HTTPError("http://eval.test/api/v1/queue/status/req", code,
                                  str(code), None, io.BytesIO(b"boom"))


def url_error():
    return urllib.error.URLError(socket.error("connection reset"))


class Transport:
    """假出口，签名与真的 ``_open(path, payload, method)`` 逐位相同。

    ``statuses`` 每元素是 dict（状态载荷）/ 非 dict 非 Exception（原文交回，制造半截 JSON）/
    Exception（当场抛出 = 一次瞬断）。读完还不停就抛 ``AssertionError`` ⇒ 判据① 的「停表」
    是真被量到的，不是脚本刚好耗尽。
    """

    def __init__(self, ask_events=(), statuses=()):
        self.ask_events = list(ask_events)
        self.statuses = list(statuses)
        self.paths = []
        self.payloads = []
        self.logins = 0

    def __call__(self, path, payload=None, method="POST"):
        self.paths.append(path)
        self.payloads.append(payload)
        if path == "/api/v1/login":
            self.logins += 1
            return FakeResponse(json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        if path.startswith("/api/v1/queue/status/"):
            if not self.statuses:
                raise AssertionError("状态全读完了还在轮 ⇒ 这一枚终态没停住表")
            item = self.statuses.pop(0)
            if isinstance(item, BaseException):
                raise item
            if not isinstance(item, dict):  # 半截 JSON 那一族：把原文交回去
                return FakeResponse(str(item).encode("utf-8"))
            return FakeResponse(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if path == "/api/v1/ask":
            return FakeResponse(lines=sse(self.ask_events))
        raise AssertionError("本单不该打这一发：" + path)

    @property
    def queue_reads(self):
        return [p for p in self.paths if p.startswith("/api/v1/queue/status/")]

    @property
    def asked(self):
        return [b for p, b in zip(self.paths, self.payloads) if p == "/api/v1/ask"]


@pytest.fixture
def adapter(tmp_path):
    module = _load("r222_transport_under_test")
    module.BASE_URL = "http://eval.test"
    module.SIDECAR = tmp_path / "sidecar-r222.jsonl"
    module.MIN_GAP_SECONDS = 0.0
    module.ATTEMPTS = 1
    module.RETRY_SLEEP = 0.0
    module.MAX_BLANKS = 200
    module.APPROVAL_ROUNDS = 3
    module._TOKEN = TOKEN_VALUE
    module._BLANKS = 0
    module._APPROVAL_FAILURES = 0
    module._LAST_CALL = 0.0
    module.time = Clock()
    return module


def poll(module, statuses, request_id="req-1"):
    fake = Transport(statuses=statuses)
    module._open = fake
    return module._poll_queue(request_id), fake


# ==================== ① 五枚终态各自停表 ====================

@pytest.mark.parametrize("status", sorted(FINAL_KINDS))
def test_every_final_status_stops_the_watch_with_its_own_kind(adapter, status):
    """判据① 主钉：读到终态就停（不睡一秒），kind 逐枚不同，而只有 done 交回正文。"""
    payload = {"status": status}
    if status == "done":
        payload["result"] = BODY
    (kind, answer, book), fake = poll(adapter, [payload] * 5)
    assert kind == FINAL_KINDS[status]
    assert kind != "ok"
    assert book["final"] == ("done" if status == "done" else status)
    assert len(fake.queue_reads) == 1, "读到终态还接着轮 ⇒ 白烧没修掉"
    assert adapter.time.slept == [], "停表之后不许再睡一枚轮询间隔"
    assert book["polls"] == 1 and book["wait_ms"] == 0.0
    assert (answer == BODY) is (status == "done")


def test_cancelled_and_dead_are_never_read_as_a_model_answer(adapter):
    """判据① 那半句：``cancelled`` / ``dead`` 交回的是空正文，不是「模型答完了」。"""
    for status in ("cancelled", "dead"):
        (kind, answer, _book), fake = poll(adapter, [{"status": status}] * 5)
        assert kind == "queued_" + status and kind != "ok"
        assert answer == "", "取不到就是取不到，不许伪造一个字"
        assert len(fake.queue_reads) == 1


def test_done_without_bytes_has_its_own_kind_and_is_not_polled_ok(adapter):
    """done 而 result 不是正文（None / 非 str / 全空白）：另立 kind，不混进 queued_polled。"""
    for result in (None, 12345, "   "):
        (kind, answer, book), _ = poll(adapter, [{"status": "done", "result": result}])
        assert kind == "queued_done_no_bytes", (result, kind)
        assert kind != "queued_polled" and answer == ""
        assert book["final"] == "done_no_bytes"


def test_the_five_final_kinds_are_pairwise_distinct_and_not_ok(adapter):
    """可统计：六枚 kind（五枚终态 + done 无字节）两两不同，且没有一枚叫 ok 或空串。"""
    seen = set()
    for status in sorted(FINAL_KINDS):
        payload = {"status": status}
        if status == "done":
            payload["result"] = BODY
        seen.add(poll(adapter, [payload])[0][0])
    seen.add(poll(adapter, [{"status": "done"}])[0][0])  # done 无字节那一枚
    assert len(seen) == 6, seen
    assert "ok" not in seen and "" not in seen


# ==================== ② 瞬断不算终态 ====================

@pytest.mark.parametrize("blip", [http_error(500), http_error(502), http_error(503),
                                  url_error(), ValueError("not json"),
                                  json.JSONDecodeError("x", "y", 0)])
def test_a_transient_poll_failure_is_not_a_stop_condition(adapter, blip):
    """判据②：一次读不到状态既不是「答完」也不是「失败」，只记一次抖动接着轮。"""
    (kind, answer, book), fake = poll(
        adapter, [blip, blip, {"status": "done", "result": BODY}])
    assert kind == "queued_polled" and answer == BODY, "瞬断把这一题判成了终局"
    assert book["blips"] == 2 and book["final"] == "done"
    assert fake.statuses == []


def test_a_transient_blip_never_stops_earlier_than_a_progressing_watch(adapter):
    """瞬断那一族不许自带小截止：它照旧等到外圈，只是把抖动记在账上。"""
    blips = [url_error()] * 400
    (kind, _answer, book), fake = poll(adapter, blips)
    assert kind == "queued_no_status"
    assert book["polls"] == 0 and book["blips"] == len(fake.queue_reads)
    assert book["wait_ms"] == pytest.approx(adapter.QUEUE_POLL_SECONDS * 1000.0)


def test_a_401_blip_refreshes_the_token_and_keeps_reading(adapter):
    """401 是最常见的一枚可恢复抖动：换票接着读，不记终态，也不静默交空白。"""
    (kind, answer, book), fake = poll(
        adapter, [http_error(401), {"status": "done", "result": BODY}])
    assert kind == "queued_polled" and answer == BODY
    assert book["blips"] == 1 and book["relogins"] == 1
    assert fake.logins >= 1, "401 之后没重登 ⇒ 后面每一发都会继续 401"


def test_a_payload_that_is_not_an_object_is_a_blip_not_a_final(adapter):
    """状态答回来一个数组：读不成对象 ⇒ 算抖动，不算「没答完」。"""
    (kind, answer, book), _ = poll(adapter, [[1, 2, 3], {"status": "done", "result": BODY}])
    assert kind == "queued_polled" and answer == BODY
    assert book["blips"] == 1


def test_a_truncated_json_body_is_a_blip(adapter):
    """半截 JSON（瞬断的常见形状）不许被读成终局。"""
    (kind, answer, book), _ = poll(adapter, ['{"status": ', {"status": "done",
                                                             "result": BODY}])
    assert kind == "queued_polled" and answer == BODY
    assert book["blips"] == 1, "半截 JSON 被读成终局 ⇒ 判据② 破了"


# ==================== ③ 白烧的天花板 ====================

def test_a_silent_status_stops_at_the_stall_ceiling_not_the_deadline(adapter):
    """载荷不再变化 = 真白烧 ⇒ 封在 QUEUE_STALL_SECONDS（默认 300 s），不是从前的 900 s。"""
    (kind, answer, book), fake = poll(adapter, [{"status": "processing"}] * 500)
    assert kind == "queued_stalled" and answer == ""
    assert book["stall_ms"] == int(adapter.QUEUE_STALL_SECONDS * 1000)
    assert book["wait_ms"] == pytest.approx(adapter.QUEUE_STALL_SECONDS * 1000.0)
    assert book["wait_ms"] < book["deadline_ms"], "无进展的轮询烧到了外圈 ⇒ 上限没降下来"
    assert len(fake.queue_reads) < 500


def test_a_moving_status_may_run_the_outer_deadline_without_being_cut(adapter):
    """状态一直在动 = 这一轮还在被推进 ⇒ 不掐（掐一次就是一次假红），走 900 s 外圈。"""
    steps = [{"status": "queued", "position": n + 1} for n in range(400)]
    (kind, answer, book), _ = poll(adapter, steps)
    assert kind == "queued_deadline" and answer == ""
    assert book["wait_ms"] == pytest.approx(adapter.QUEUE_POLL_SECONDS * 1000.0)
    assert book["blips"] == 0


def test_short_progress_bursts_reset_the_stall_ceiling(adapter):
    """每 99 s 动一次（累计早过 300 s）也不该被停：掐的是静止，不是慢。"""
    steps = []
    for position in range(1, 8):
        steps.extend([{"status": "queued", "position": position}] * 50)
    (kind, _answer, book), _ = poll(adapter, steps)
    assert kind == "queued_deadline", (kind, book)
    assert book["polls"] == int(adapter.QUEUE_POLL_SECONDS / adapter.QUEUE_POLL_INTERVAL)


def test_the_stopwatch_vocabulary_is_smaller_than_the_old_burn(adapter):
    """把「白烧从 900 s 降下来」这句话本身钉住：默认值、大小关系、与前端同源的间隔。"""
    module = _load("r222_defaults")
    assert module.QUEUE_STALL_SECONDS == 300.0
    assert module.QUEUE_STALL_SECONDS < module.QUEUE_POLL_SECONDS
    assert module.QUEUE_POLL_SECONDS == 900.0  # 外圈那枚没动：它量的不是白烧
    assert module.QUEUE_POLL_INTERVAL == 3.0   # 与 ChatPanel.vue:839 QUEUE_POLL_MS = 3000 同源


@pytest.mark.parametrize("status", ["queued", "processing", "cancel_requested"])
def test_inflight_statuses_are_never_final(adapter, status):
    """在途态有代码写下的下一步迁移 ⇒ 不算终局，也一个字正文都不交。"""
    (kind, answer, _book), _ = poll(adapter, [{"status": status}] * 500)
    assert kind == "queued_stalled", (status, kind)
    assert answer == ""


# ==================== ⑤ 落盘：kind 与取回账一起进两份证据件 ====================

def read_jsonl(path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


QUEUED_STREAM = [("queued", {"type": "queued", "request_id": "req-9"}),
                 ("done", {"type": "done"})]


@pytest.mark.parametrize("status,expected_kind", [
    ("cancelled", "queued_cancelled"), ("dead", "queued_dead"),
    ("failed", "queued_failed"), ("expired", "queued_expired")])
def test_a_terminal_tail_lands_in_both_artifacts_with_its_kind(
        adapter, status, expected_kind):
    """判据① + ⑤：kind 与取回账一起落盘，而 sidecar 的键集一个字都没多。"""
    adapter._open = Transport(ask_events=QUEUED_STREAM,
                              statuses=[{"status": status}] * 500)
    payload = adapter.transport({"id": "doc-01", "question": "Q3 营收多少？"})
    sidecar = read_jsonl(adapter.SIDECAR)[0]
    frames = read_jsonl(adapter.frame_ledger_path())[0]
    assert payload["answer"] == adapter.BLANK_SENTINEL  # 零字节 ⇒ 哨兵照旧
    assert payload["first_token_at"] is None  # 后台跑的首字观测不到，禁止估算
    assert sidecar["kind"] == expected_kind == frames["kind"]
    assert sidecar["sentinel"] is True and sidecar["pre_kind"] == expected_kind
    assert frames["queue"]["final"] == status
    assert frames["queue"]["polls"] == 1 and frames["queue"]["wait_ms"] == 0.0
    assert frames["queue"]["stall_ms"] == 300000
    assert tuple(list(sidecar)[:9]) == SIDECAR_BASE_KEYS
    assert set(sidecar) - set(SIDECAR_BASE_KEYS) <= (R123_EXTRA_KEYS | {"pre_answer"})


def test_a_polled_answer_still_reads_queued_polled(adapter):
    """正例对照：done + result 那一枚 kind 一个字没改（run6/run7 的历史口径不漂）。"""
    adapter._open = Transport(ask_events=QUEUED_STREAM,
                              statuses=[{"status": "done", "result": BODY}])
    payload = adapter.transport({"id": "doc-02", "question": "Q3 营收多少？"})
    assert payload["answer"] == BODY
    assert read_jsonl(adapter.SIDECAR)[0]["kind"] == "queued_polled"
    row = read_jsonl(adapter.frame_ledger_path())[0]
    assert row["queue"]["blips"] == 0 and row["queue"]["final"] == "done"


def test_blips_are_visible_in_the_ledger_without_changing_the_answer(adapter):
    """判据② 的落盘证据：抖了三次最后取到正文 ⇒ 账上看得见抖，正文不受影响。"""
    adapter._open = Transport(
        ask_events=QUEUED_STREAM,
        statuses=[url_error(), http_error(503), url_error(),
                  {"status": "processing"}, {"status": "done", "result": BODY}])
    payload = adapter.transport({"id": "doc-03", "question": "Q3 营收多少？"})
    assert payload["answer"] == BODY
    book = read_jsonl(adapter.frame_ledger_path())[0]["queue"]
    assert (book["blips"], book["polls"], book["final"]) == (3, 2, "done")


def test_a_question_that_never_touched_the_queue_has_an_empty_book(adapter):
    """没走队列的题：``queue`` 那一格是空字典（读作「这一题没取回过」），不是 None 也不是 0。"""
    adapter._open = Transport(ask_events=[("text", {"type": "text", "content": BODY}),
                                          ("done", {"type": "done"})])
    adapter.transport({"id": "doc-04", "question": "Q3 营收多少？"})
    row = read_jsonl(adapter.frame_ledger_path())[0]
    assert row["queue"] == {} and row["kind"] == "ok"


def test_the_blank_safety_valve_is_untouched_by_the_new_kinds(adapter):
    """白烧修了，但「零字节超阈值就停窗」那一枚安全阀一个字节没动。"""
    adapter.MAX_BLANKS = 0
    adapter._open = Transport(ask_events=QUEUED_STREAM,
                              statuses=[{"status": "dead"}] * 500)
    with pytest.raises(RuntimeError) as exc:
        adapter.transport({"id": "doc-05", "question": "Q"})
    assert "零字节题数已超" in str(exc.value)


def test_a_dead_tail_does_not_get_laundered_by_a_foreground_error(adapter):
    """🔴 走过队列道就不许被前台那枚 error 帧改写结局：dead 是 dead，不是「产品给的一句错话」。"""
    adapter._open = Transport(
        ask_events=[("error", {"type": "error", "content": "前台报错"}),
                    ("queued", {"type": "queued", "request_id": "req-9"}),
                    ("done", {"type": "done"})],
        statuses=[{"status": "dead"}] * 500)
    payload = adapter.transport({"id": "doc-06", "question": "Q"})
    assert payload["answer"] == adapter.BLANK_SENTINEL
    assert read_jsonl(adapter.SIDECAR)[0]["kind"] == "queued_dead"


# ==================== R226 代际：报告档的 lane 声明不许被本单带回退化 =========

def test_r226_lane_declaration_still_travels_only_the_declared_tier(adapter, monkeypatch):
    """判据「代际已变不许回退」：默认载荷一字节不多，设了档位名才补 lane。"""
    monkeypatch.setattr(adapter, "DECLARE_LANE_TIER", "")
    fake = Transport(ask_events=[("text", {"type": "text", "content": BODY})])
    adapter._open = fake
    adapter.transport({"id": "doc-07", "question": "Q", "tier": "报告"})
    assert len(fake.asked) == 1
    sent = fake.asked[0]
    # 默认口径：载荷仍是那三键，一个字节都不多（run6 / run7 相 1 的口径不受影响）
    assert set(sent) == {"message", "session_id", "idempotency_key"}, sent
    assert sent["message"] == "Q" and "lane" not in sent

    monkeypatch.setattr(adapter, "DECLARE_LANE_TIER", "报告")
    fake2 = Transport(ask_events=[("text", {"type": "text", "content": BODY})])
    adapter._open = fake2
    adapter.transport({"id": "doc-08", "question": "Q2", "tier": "报告"})
    assert fake2.asked[0]["lane"] == "report"
    fake3 = Transport(ask_events=[("text", {"type": "text", "content": BODY})])
    adapter._open = fake3
    adapter.transport({"id": "doc-09", "question": "Q3", "tier": "问答"})
    assert "lane" not in fake3.asked[0]


# ==================== ⑥ 反证钉（红必须落在本格） ====================

#: (名字, 锚点, 换成什么) —— 逐枚在临时根副本上动手，跟踪里的原件一字不改。
MUTANTS = {
    "drop_cancelled_and_dead_stop": (
        '        if status in ("cancelled", "dead", "expired", "failed"):',
        '        if status in ("expired", "failed"):'),
    "transient_counts_as_final": (
        "        except urllib.error.HTTPError as exc:\n"
        "            # 判据②：非 2xx 是**读不到**，不是**读完了**。401 换票接着读，其余原样重试。\n",
        "        except urllib.error.HTTPError as exc:\n"
        "            # 反证乙：把一次 5xx 就当终局 —— 判据② 摘掉之后的形状。\n"
        '            return _stop("queued_expired", "", "expired", now)\n'),
    "white_burn_reads_as_answer": (
        '    return _stop("queued_no_status" if not book["polls"] else "queued_deadline",',
        '    return _stop("queued_polled" if not book["polls"] else "queued_deadline",'),
}


def _mutant(tmp_path, name):
    """把量具复制进临时根、只改那一处锚点，再加载那份副本。"""
    import hashlib
    original = SCRIPT_PATH.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    anchor, replacement = MUTANTS[name]
    assert text.count(anchor) == 1, "锚点在原件里不唯一，这枚反证是空的"
    mutated = text.replace(anchor, replacement, 1)
    assert mutated != text, "反证没作用到东西上"
    target = tmp_path / ("mutant_" + name + ".py")
    target.write_text(mutated, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location("r222_" + name, str(target))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SIDECAR = tmp_path / (name + "-sidecar.jsonl")
    module.MIN_GAP_SECONDS = 0.0
    module.MAX_BLANKS = 200
    module._TOKEN = TOKEN_VALUE
    module.time = Clock()
    assert SCRIPT_PATH.read_bytes() == original, "跟踪里的原件被动了"
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == \
        hashlib.sha256(original).hexdigest()
    return module


def test_counter_evidence_dropping_the_cancelled_deadly_stop_goes_red_here(tmp_path):
    """反证甲：把 cancelled/dead 摘回「未处理」（本单要治的那枚病）⇒ 白烧回来了。"""
    module = _mutant(tmp_path, "drop_cancelled_and_dead_stop")
    (kind, answer, book), fake = poll(module, [{"status": "dead"}] * 500)
    assert kind != "queued_dead", "摘掉停表还读到 queued_dead ⇒ 这枚钉是空的"
    assert kind == "queued_stalled" and book["final"] == "stalled"
    assert len(fake.queue_reads) > 1 and module.time.slept, "白烧没回来 ⇒ 钉没打到点上"
    assert book["wait_ms"] == pytest.approx(module.QUEUE_STALL_SECONDS * 1000.0)
    assert answer == ""


def test_counter_evidence_a_blip_read_as_a_final_goes_red_here(tmp_path):
    """反证乙：把一次 503 当成终局（前端 R198/R202 那族误伤）⇒ 后面那发 done 白读。"""
    module = _mutant(tmp_path, "transient_counts_as_final")
    (kind, answer, book), fake = poll(
        module, [http_error(503), {"status": "done", "result": BODY}])
    assert kind == "queued_expired" and answer == "", "瞬断仍被读成终局 ⇒ 判据② 没钉住"
    assert fake.statuses, "被摘错的那发瞬断：后面那发 done 根本没轮到"


def test_counter_evidence_the_white_burn_reading_as_an_answer_goes_red_here(tmp_path):
    """反证丙：一条都没读通却报「取回了」⇒ 那是伪造的结局，kind 当场不同。"""
    module = _mutant(tmp_path, "white_burn_reads_as_answer")
    (kind, answer, _book), _ = poll(module, [url_error()] * 400)
    assert kind == "queued_polled" and answer == ""
    assert kind != "queued_no_status", "摘掉之后本枚该红在未区分上"


def test_the_tracked_ruler_is_byte_identical_after_every_overlay_proof():
    """临时根反证不许漏进真树：原件的字面逐枚还在。"""
    text = SCRIPT_PATH.read_bytes().decode("utf-8")
    assert 'if status in ("cancelled", "dead", "expired", "failed"):' in text
    assert '"queued_stalled"' in text and '"queued_done_no_bytes"' in text
    assert 'return _stop("queued_no_status" if not book["polls"] else "queued_deadline",' in text
