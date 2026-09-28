# -*- coding: utf-8 -*-
"""R259 两份量具件共用的替身：一台会数表的假钟、一具会记账的假出口、五枚真实形状的终态载荷。

来历：R254（主树 ``8f89def``）把队列道的终态改了口 —— 挂在等人批准（HITL）的那一轮不再报
``done``，改报 ``awaiting_approval``，且 ``result`` 交回 null；同一天 ``/queue/status`` 在两枚
published 状态下多交一批终态读数（契约 ``docs/api/contract-v1.md`` §Structured terminal
readout (2026-09-25, R254)）。我们的评测量具从前不认得那枚新状态词，也不采那些读数。

全程离线：量具的 ``_open`` 换成会记账的假出口，零服务 / 零模型 / 零容器 / 零连库 / 零真跑分
（一发都不许打 ``/api/v1/ask``、``/api/v1/login`` 或 Ollama）。两份产物写 tmp_path，仓内零字节。
钟是假钟，而且**会数自己被打读了几次** —— 量具的假钟每多读一次就走一格（多读一枚就把 105 题
重放的时间轴整条推走 ⇒ ``tests/test_r181_text_frame_ruler.py`` 的 ``PRE_R181_ANSWERS_SHA``
当场红），所以「新终态不许多读表」这句话只能靠数表钉住，不能靠自觉。
"""
import importlib.util
import io
import json
import socket
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"

ANSWER = "上季度毛利率 38.2%，环比 +1.4 个百分点。"
#: run8 相 2 里被当成正文交回的那一句（37 字挂起文案）：今天它只许出现在 approval.notice 里。
PARK_NOTICE = "本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。"
TOKEN_VALUE = "eval-bearer-token"
#: R259 新终态的 kind（派工词判据①：与 ``queued_polled`` / ``queued_done_no_bytes`` 都不许混）。
PARKED_KIND = "queued_awaiting_approval"
#: R222 那五枚终态 → 各自的 kind。名单在 tests 这一侧独立抄一份，与量具实跑读数对判：
#: 谁漂了都红（``tests/test_r222_queue_terminal_stopwatch.py:45`` 同一族做法）。
FINAL_KINDS = {"done": "queued_polled", "cancelled": "queued_cancelled",
               "dead": "queued_dead", "expired": "queued_expired",
               "failed": "queued_failed"}
#: 三枚「没读到终局」的 kind，判据⑤ 里它们也一个字不许动。
UNFINISHED_KINDS = ("queued_stalled", "queued_deadline", "queued_no_status")
#: sidecar 既有九键（顺序也钉）+ 甲案七键：本单一枚都不许多（判据⑥）。
SIDECAR_BASE_KEYS = ("id", "kind", "attempt", "sentinel", "evidence_n",
                     "answer_chars", "tool_calls", "wall_ms", "ts")
R123_EXTRA_KEYS = {"pre_kind", "pre_answer_chars", "pre_evidence_n", "approved",
                   "approval_rounds", "approval_http_status", "approval_error"}
#: 帧账一行的键集（抄自 ``tests/test_r181_text_frame_ruler.py:43-55`` 那三枚名单，逐枚对判）。
#: run8 相 2 实测「28 键/行」就是这一枚并集 ⇒ 本单新增的读数只许长在 ``queue`` 那一格里，
#: 顶层一列都不许多（判据⑥）。
JOIN_KEYS = {"id", "kind", "attempt", "sentinel", "session_id", "ts"}
FRAME_READING_KEYS = {"text_frames", "prefix_breaks", "corrective_replacements",
                      "uncorrected_breaks", "missing_chars", "extra_chars",
                      "last_frame_covers_answer", "last_frame_chars", "last_frame_sha",
                      "answer_chars", "answer_sha", "streams", "max_stream_frames",
                      "per_stream", "criterion_two_holds"}
ARRIVAL_READING_KEYS = {"frames", "events", "stream_clock", "queue",
                        "first_visible_at", "first_visible_event", "first_visible_ms"}
FRAME_ROW_KEYS = JOIN_KEYS | FRAME_READING_KEYS | ARRIVAL_READING_KEYS
#: 入队那一题的前台回执流：一条 queued + 一条收尾 done（run8 相 2 的 events 直方图形状）。
QUEUED_STREAM = [("queued", {"type": "queued", "request_id": "req-1"}),
                 ("done", {"type": "done"})]

#: R447 判据① 之后队列道读到挂起会真打一发 ``/api/v1/approve``。缺省那枚恢复流只交正文、
#: 不交 ``sources`` 事件：R259 的两枚形状账（``evidence`` 为空、sidecar 键集不许多）判的就是
#: 「批准腿没交出处」这一枚形状，出处长在批准流里什么样由 R447 自己带夹具。
APPROVAL_PATH = "/api/v1/approve"
APPROVED_STREAM = [("text", {"content": ANSWER}), ("done", {"type": "done"})]


def load(name):
    """按文件名单独加载量具（与 R222 / R181 同一族做法：一次一份，互不串进程态）。"""
    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(module, tmp_path, name="r259"):
    """把量具装进"零等待、产物落 tmp_path、钟会数表"的观测态。"""
    module.BASE_URL = "http://eval.test"
    module.SIDECAR = tmp_path / ("sidecar-" + name + ".jsonl")
    module.MIN_GAP_SECONDS = 0.0
    module.ATTEMPTS = 1
    module.RETRY_SLEEP = 0.0
    module.MAX_BLANKS = 200
    module.APPROVAL_ROUNDS = 3
    module._TOKEN = TOKEN_VALUE
    module._BLANKS = 0
    module._PARKED = 0
    module._APPROVAL_FAILURES = 0
    module._LAST_CALL = 0.0
    module.time = Clock()
    return module


class Clock:
    """假钟：``sleep`` 把钟拨过去；``time()`` 每被打读一次记一格（钟的纪律靠这一格取证）。"""

    def __init__(self, start=1790000000.0):
        self.now = start
        self.slept = []
        self.reads = 0

    def time(self):
        self.reads += 1
        return self.now

    def monotonic(self):
        self.reads += 1
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
    """服务端每事件三行：event / data / 空行（``app/api/v1/chat.py`` 的 SSE 形状）。"""
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

    ``statuses`` 逐发交回状态载荷；读完还不停就抛 ``AssertionError`` ⇒ 「这一枚终态停住表」
    是真被量到的，不是脚本刚好耗尽。``approvals`` 同办（R447 判据①）：批准流逐发交回，
    空表时打过来就抛「这一枚结局不该打批准轮」—— 少打与多打都红，不会漂到别的断言上。
    """

    def __init__(self, ask_events=(), statuses=(), approvals=()):
        self.ask_events = list(ask_events)
        self.statuses = list(statuses)
        self.approvals = list(approvals)
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
            if not isinstance(item, dict):
                return FakeResponse(str(item).encode("utf-8"))
            return FakeResponse(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if path == APPROVAL_PATH:
            if not self.approvals:
                raise AssertionError("这一枚结局不该打批准轮：" + path)
            item = self.approvals.pop(0)
            if isinstance(item, BaseException):
                raise item
            return FakeResponse(lines=sse(item))
        if path == "/api/v1/ask":
            return FakeResponse(lines=sse(self.ask_events))
        raise AssertionError("本单不该打这一发：" + path)

    @property
    def queue_reads(self):
        return [p for p in self.paths if p.startswith("/api/v1/queue/status/")]

    @property
    def asked(self):
        return [b for p, b in zip(self.paths, self.payloads) if p == "/api/v1/ask"]

    def only(self, path):
        """按路径数发数：R447 之后「批准轮打了几发」必须看得见，不能只数状态读。

        读数从 ``paths`` 现算，一次表都不读 ⇒ 假钟的格数不受这一枚影响。
        """
        return [p for p in self.paths if p == path]

    @property
    def approve_reads(self):
        return self.only(APPROVAL_PATH)


def poll(module, statuses, request_id="req-1"):
    """只跑取回那一段：回 ``(_poll_queue 的三元组, 假出口)``。"""
    fake = Transport(statuses=list(statuses))
    module._open = fake
    return module._poll_queue(request_id), fake


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def drive_queue(module, statuses, row_id="doc-01", ask_events=None, approvals=None):
    """走真 ``transport`` 的完整一题：前台回执入队 → 轮询取回 →（挂起就批准）→ 两份证据件落盘。

    ``approvals`` 自 R447 起有缺省值：量具读到 ``awaiting_approval`` 会真打一发
    ``/api/v1/approve``，所以喂挂起载荷的用例必须有一枚恢复流可拿 —— 给空表等于判「这一枚
    结局不该打批准轮」，那是判据本身，不该由夹具替它说话。要判「不该打」的用例自己传 ``()``。
    """
    events = QUEUED_STREAM if ask_events is None else ask_events
    streams = [APPROVED_STREAM] if approvals is None else list(approvals)
    fake = Transport(ask_events=events, statuses=list(statuses), approvals=streams)
    module._open = fake
    payload = module.transport({"id": row_id, "question": "Q3 营收多少？"})
    return payload, fake, read_jsonl(module.SIDECAR), read_jsonl(module.frame_ledger_path())


# ==================== 五枚真实形状的 `/queue/status` 载荷（逐字对着契约抄） ====================

def usage_readout(**over):
    """``usage`` 那一格：run8 相 2 §1 D-2 的服务端补尺读数（70 行 / Σ91,271 / Σ18,859）。"""
    row = {"prompt_tokens": 91271, "completion_tokens": 18859, "total_tokens": 110130,
           "model_calls": 70, "calls_with_token_readout": 68,
           "calls_missing_token_readout": 2, "token_readout_complete": False,
           "authoritative": True, "ledger": "postgres_model_calls"}
    row.update(over)
    return row


def answered_body(**over):
    """一枚真跑完、真交回正文的队列行（契约 §Structured terminal readout 的样例形状）。"""
    row = {"status": "done", "request_id": "req-1", "result": ANSWER,
           "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
           "terminal_schema": "queue-terminal-v1", "terminal_state": "answered",
           "answer_present": True, "answer_is_park_notice": False,
           "worker_status": "success", "sources_present": True,
           "sources": [{"worker": "doc", "source": "经营月报.pdf"},
                       {"worker": "doc", "source": "口径登记表.xlsx"},
                       {"worker": "data", "source": "sales.csv"}],
           "scope_reason_code": "department_and_classification", "sources_error": "",
           "usage": usage_readout(), "approval": None, "terminal_note": ""}
    row.update(over)
    return row


def parked_body(**over):
    """R254 之后挂起在 HITL 闸前的那一轮：``result`` 是 null，可批准的东西在 ``approval`` 里。"""
    row = {"status": "awaiting_approval", "request_id": "req-1", "result": None,
           "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
           "terminal_schema": "queue-terminal-v1", "terminal_state": "awaiting_approval",
           "answer_present": False, "answer_is_park_notice": False,
           "worker_status": "partial", "sources_present": False, "sources": [],
           "scope_reason_code": "", "sources_error": "",
           "usage": usage_readout(prompt_tokens=412, completion_tokens=0, total_tokens=412,
                                  model_calls=1, calls_with_token_readout=1,
                                  calls_missing_token_readout=0,
                                  token_readout_complete=True),
           "approval": {"session_id": "sess-1", "pending_steps": ["export"],
                        "labels": ["📋 导出报告"], "notice": PARK_NOTICE,
                        "decide_method": "POST", "decide_path": "/api/v1/approve",
                        "decide_body": {"session_id": "sess-1", "approved": True},
                        "decide_note": "批准这一轮才会继续跑", "ledger_status": "awaiting"},
           "terminal_note": ""}
    row.update(over)
    return row


def legacy_row_body(park_notice=False, **over):
    """本单之前发布的旧行（契约 §Compatibility note 2026-09-25）：它说不出自己有没有出处。

    ``park_notice=True`` 就是 run8 相 2 那 11 枚的形状 —— 正文位置上是那句 37 字挂起文案，
    而旧行只会说「这一格有句字」，说不出更多。出处/token/批准把手三枚槽位当年没有落账。
    """
    row = {"status": "done", "request_id": "req-1",
           "result": PARK_NOTICE if park_notice else "旧行正文",
           "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
           "terminal_schema": "legacy", "terminal_state": "legacy_row",
           "answer_present": True, "answer_is_park_notice": bool(park_notice),
           "worker_status": "", "sources_present": False, "sources": [],
           "scope_reason_code": "", "sources_error": "", "usage": None, "approval": None,
           "terminal_note": "这一行发布于结构化终态之前：出处、token 与批准把手三格当年没有落账。"}
    row.update(over)
    return row


def unreadable_row_body(**over):
    """终态键在位而载荷解不开：那是损坏，与兼容是两枚诊断（契约同一节最后两句）。"""
    row = {"status": "done", "request_id": "req-1", "result": "正文还在",
           "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
           "terminal_schema": "unreadable", "terminal_state": "unreadable_terminal",
           "answer_present": True, "answer_is_park_notice": False,
           "worker_status": "", "sources_present": False, "sources": [],
           "scope_reason_code": "", "sources_error": "", "usage": None, "approval": None,
           "terminal_note": "终态键在位而载荷解不开，那一格宁缺毋造。"}
    row.update(over)
    return row


def bare_done_body(status="done", **over):
    """更老的读路 / 契约没规定的状态：只有 status + result（R222 那扇窗看见的就是这一枚形状）。"""
    row = {"status": status, "request_id": "req-1", "failure": {"attempts": 1,
                                                                "last_error": None,
                                                                "max_attempts": 3}}
    if status == "done":
        row["result"] = ANSWER
    row.update(over)
    return row


# ==================== 判据③：D-2 / D-3 两格的读法（从取回账现算，不翻日志） ====================

#: D-2「这一轮的客户端读没读到 token 读数」的四种可判读数。
USAGE_CELLS = ("read_authoritative", "read_local_ledger", "read_ledger_silent",
               "row_cannot_say", "no_terminal_read")
#: D-3「这一轮的客户端读没读到出处」的四种可判读数。
SOURCES_CELLS = ("read_some", "read_zero", "not_computable", "row_cannot_say",
                 "no_terminal_read")


def usage_cell(queue_book):
    """D-2 那一格：读数只从 ``queue.terminal`` 取，一枚都不现编。

    🔴 五枚读数各说一件事，谁也不许冒充谁：
      - ``read_authoritative`` / ``read_local_ledger``：读到了数，区别只在那本账权不权威；
      - ``read_ledger_silent``：``usage`` 格在位，但它自己交回的是 null（台账读不到）——
        「没读到数」，与「读到零」是两件事；
      - ``row_cannot_say``：这一行（旧行 / 损坏行 / 服务端没交这批键）压根说不出；
      - ``no_terminal_read``：连一枚终态载荷都没读到过（stalled / deadline / no_status）。
    """
    terminal = (queue_book or {}).get("terminal") or {}
    if terminal.get("shape") == "not_terminal":
        return "no_terminal_read"
    if not terminal.get("usage_present"):
        return "row_cannot_say"
    usage = terminal.get("usage") or {}
    if usage.get("total_tokens") is None and usage.get("model_calls") is None:
        return "read_ledger_silent"
    return "read_authoritative" if usage.get("authoritative") else "read_local_ledger"


def sources_cell(queue_book):
    """D-3 那一格：``row_cannot_say`` 与 ``read_zero`` 必须是两枚读数（判据② 第一条口径）。

    ``not_computable`` 是第三件事：``sources_error`` 非空（``principal_unavailable`` /
    ``sources_unavailable`` / ``answer_cache_without_manifest``）⇒ 出处压根没算成。
    """
    terminal = (queue_book or {}).get("terminal") or {}
    if terminal.get("shape") == "not_terminal":
        return "no_terminal_read"
    count = terminal.get("sources_n")
    if count is None:
        return "row_cannot_say"
    if terminal.get("sources_error"):
        return "not_computable"
    return "read_zero" if count == 0 else "read_some"


# ==================== 反证机械（R253 纪律：变异只落影子副本） ====================

def mutant(tmp_path, name, anchor, replacement, extra=""):
    """按锚点摘掉量具里的某一处，加载那份临时根副本；原件 sha 当场复验。

    🔴 就地改写被跟踪文件是 R253 明令禁止的形态（跟进单 §100.4 第一枚），所以这里只往
    ``tmp_path`` 写，回来再验一次 sha256 与读进来时逐字节相同。
    """
    import hashlib
    import importlib.util
    original = SCRIPT_PATH.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    assert text.count(anchor) == 1, "锚点在原件里不唯一，这枚反证是空的：" + anchor
    mutated = text.replace(anchor, replacement, 1) + extra
    assert mutated != text, "反证没作用到东西上"
    target = tmp_path / ("mutant_" + name + ".py")
    target.write_text(mutated, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location("r259_mutant_" + name, str(target))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    configure(module, tmp_path, name="mut-" + name)
    assert SCRIPT_PATH.read_bytes() == original, "跟踪里的原件被动了"
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == \
        hashlib.sha256(original).hexdigest()
    return module, target


def stop_vocabulary(root, module_name="r218_rehearsal_for_r259"):
    """现读总控那枚 AST 钉（``scripts/r218_switch_rehearsal.py``）对某一棵根的停表词表。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.adapter_stop_vocabulary(root)["stops"]
