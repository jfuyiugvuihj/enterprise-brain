# -*- coding: utf-8 -*-
"""R223 判据③：帧账里必须有「什么时候到的」—— 断流的时刻与首屏的时刻。

判据原文：施工单 R223 §补的读数。全程离线：量具的 ``_open`` 换成会记账的假出口，假钟每读
一次表走 0.25 s ⇒ 「第几枚什么时候到」是可复算的数，不是 wall-clock 噪声。零服务 / 零模型 /
零容器 / 零连库 / 零真跑分（一发都不打 ``/api/v1/ask``、``/api/v1/login`` 或 Ollama），两份
产物都写 tmp_path，仓内零字节。

钉住的九件事：
  ① 每一枚 text 帧带 ``arrival_at`` 且逐枚单调，抄的是 ``first_token_at`` 用的同一枚钟；
  ② 断流那一枚帧（``prefix_break`` 为真）在帧账里同时有「第几条流第几帧」和「几点到的」
     ⇒ 才谈得上导出「断流发生在什么时间」；
  ③ ``events`` 记**全部**事件的到达时刻与前端认领类别；``first_visible_*`` 三格只认 render
     且名字不是 ``text`` 的最早一枚（R48 已并树的 canonical ``answer.headline`` 就是它）；
     ``status``（只进过程提示条）与 ``heartbeat``（显式选择不画）都不许抢首屏，正文也不许；
  ④ 零点写进账（``stream_clock.elapsed_base``）：真跑分路径＝发出 POST 那一刻，单测直连
     ``_consume``＝退到本流第一枚事件。缺一侧一律 null，禁止拿 0 冒充「同一时刻」；
  ⑤ 🔴 只加读数：把两枚 ``_note_*_arrival`` 摘成空函数，同一条流照旧跑一遍，payload /
     sidecar / 帧账既有每一格逐字节相同；并且逐帧那一格**跟着 R181 的计数走**（尺子没数的
     枚次这格也不记），它不是第二把尺 —— 与 R215 的 ``_note_frame_shape`` 同一条纪律。
     而且新列一律开在 ``_arrival_readings`` 这一层、由 ``_record_frames`` 并进落盘行 ——
     ``_frame_readings``（R181 那把尺自己的函数）返回的键集与本单开工前逐字相同，所以
     ``tests/test_r181_text_frame_ruler.py:467`` 那枚「把计数摘瞎之后三帧与零帧同形」的
     整字典对判照旧绿，不需要谁去改。需要总控动的只有 :426 那枚**行级**名单。
  ⑥ 从**落盘的 JSONL** 里直接读出断流时刻与首枚非-text 事件时刻；
  ⑦ 抄本不漂移：``EVENT_CLASSES`` 与 ``frontend/src/lib/sessions.js`` 的 ``EVENT_CLAIMS``
     逐枚相等（量具不许 import 前端 ⇒ 抄一份字面并钉住它，抄本漂了就当场红）；
  ⑧ 两条流（挂起轮 + 批准轮）各有各的钟；``at`` 是流内序号，与 ``per_stream`` /
     ``break_frames`` 同一个坐标系；
  ⑨ 反证钉（判据④b「帧账缺 arrival_at 就红」）：摘掉抄时刻、把 ``arrival_at`` 写成 null、
     把首屏过滤放宽成「任何 render 事件」、把 ``answer.headline`` 从认领表里漏掉 —— 红都落在
     本格。全部在临时根副本上动手，跟踪里的原件一字不改（最后一枚件复核字面）。

🔴 判据⑤ 抬头口径：**run8 的帧账 ≠ run6 / run7 的帧账。** 本树实取的旧件里一列到达时刻都
没有（run6 帧账 19 键、run7 帧账 21 键，都没有 ``frames`` / ``events`` / ``stream_clock`` /
``queue`` / ``first_visible_*``）⇒ 拿旧件重放只会长出空列，既不许读成「当年零停表」，也不许
读成「当年无断流」。断流的时刻与首屏的时刻，从 run8 起才是量得出来的两件事。
"""
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
FRONTEND_SESSIONS = REPO_ROOT / "frontend" / "src" / "lib" / "sessions.js"
RUN6_LEDGER = REPO_ROOT / "docs" / "testing" / "sidecar-run6-frames.jsonl"
RUN7_LEDGER = REPO_ROOT / "docs" / "testing" / "sidecar-run7-frames.jsonl"

FULL = "据统计，Q3 营收 1200 万元，环比增长 8%，毛利率持平。"
PARK_TEXT = "本轮在「生成图表」前等待你确认，确认后才会执行，目前尚未产出回答内容。"
TOKEN_VALUE = "eval-bearer-token"
#: 假钟每读一次表走的秒数。一枚事件只读一次表（``iter_events`` 在 ``data:`` 那一行打戳），
#: 所以「第几枚什么时候到」都是 250 ms 的整数倍，不是噪声。
TICK = 0.25

#: R223 / R222 新开在帧账那一层的读数格。既有格一枚不许动，也不许往 sidecar 里加。
NEW_CELLS = {"frames", "events", "stream_clock", "queue",
             "first_visible_at", "first_visible_event", "first_visible_ms"}
#: 本单开工前就有的读数格（R215 那两格在内）。名单与 tests/test_r181_text_frame_ruler.py
#: 的 ``FRAME_READING_KEYS`` 同口径 —— 那枚文件不在本单写域，七个新名字照旧由总控补进去
#: （R215 当年同样如此）；这里先把「旧的一格都没少、新的一格都没漏」钉住。
OLD_CELLS = {"text_frames", "prefix_breaks", "corrective_replacements", "uncorrected_breaks",
             "missing_chars", "extra_chars", "last_frame_covers_answer", "last_frame_chars",
             "last_frame_sha", "answer_chars", "answer_sha", "streams", "max_stream_frames",
             "per_stream", "criterion_two_holds"}
JOIN_KEYS = {"id", "kind", "attempt", "sentinel", "session_id", "ts"}
SIDECAR_BASE_KEYS = ("id", "kind", "attempt", "sentinel", "evidence_n",
                     "answer_chars", "tool_calls", "wall_ms", "ts")
R123_EXTRA_KEYS = {"pre_kind", "pre_answer_chars", "pre_evidence_n", "approved",
                   "approval_rounds", "approval_http_status", "approval_error"}

# ===== 合成 SSE 流（全部离线造，一发都不打真机）=====

#: 首屏那张线索卡在正文之前到达：R48 路线甲的 canonical 事件名，B 门量的就是它。
HEADLINE_FIRST = [
    ("request.started", {"type": "request.started"}),
    ("status", {"type": "status", "content": "正在检索知识库"}),
    ("answer.headline", {"type": "answer.headline",
                         "data": {"headline": "Q3 营收 1200 万元", "basis": "营收表"}}),
    ("heartbeat", {"type": "heartbeat"}),
    ("text", {"type": "text", "content": FULL[:8]}),
    ("step", {"type": "step", "tool": "chart", "status": "running"}),
    ("text", {"type": "text", "content": FULL}),
    ("sources", {"type": "sources", "data": {"sources": [{"file": "营收表.xlsx"}]}}),
    ("done", {"type": "done"}),
]
MULTI_FRAME = [("text", {"type": "text", "content": FULL[:8]}),
               ("text", {"type": "text", "content": FULL[:17]}),
               ("text", {"type": "text", "content": FULL}),
               ("done", {"type": "done"})]
#: 第二枚帧换了来源 ⇒ 前缀单调破了。这一枚就是「断流」，R223 要的就是它到达的时刻。
BROKEN = [("text", {"type": "text", "content": FULL[:8]}),
          ("text", {"type": "text", "content": "另一条来源的答案"}),
          ("text", {"type": "text", "content": "另一条来源的答案的后半"}),
          ("done", {"type": "done"})]
#: 首屏线索卡之后才断流：一份同时给出「首屏几点到」与「断流几点到」的样本。
HEADLINE_THEN_BREAK = [
    ("status", {"type": "status", "content": "正在检索知识库"}),
    ("answer.headline", {"type": "answer.headline", "data": {"headline": "Q3 营收"}}),
    ("text", {"type": "text", "content": FULL[:8]}),
    ("text", {"type": "text", "content": "另一条来源的答案"}),
    ("text", {"type": "text", "content": "另一条来源的答案的后半"}),
    ("done", {"type": "done"}),
]
#: 只有 note / silent / terminal 三类事件：屏上什么都没画出来 ⇒ 首屏读「没量到」。
SILENT_ONLY = [("request.started", {"type": "request.started"}),
               ("status", {"type": "status", "content": "正在检索知识库"}),
               ("heartbeat", {"type": "heartbeat"}),
               ("done", {"type": "done"})]
#: 没有线索卡，但 step 是 render 且不是正文 ⇒ 首屏就是它。
STEP_FIRST_VISIBLE = [("status", {"type": "status", "content": "正在检索"}),
                      ("heartbeat", {"type": "heartbeat"}),
                      ("step", {"type": "step", "tool": "chart", "status": "running"}),
                      ("text", {"type": "text", "content": FULL}),
                      ("done", {"type": "done"})]
#: 出处卡比线索卡先到：首屏认**最早**那一枚可见事件，不认名字。
SOURCES_BEFORE_HEADLINE = [
    ("status", {"type": "status", "content": "正在检索"}),
    ("sources", {"type": "sources", "data": {"sources": [{"file": "营收表.xlsx"}]}}),
    ("answer.headline", {"type": "answer.headline", "data": {"headline": "Q3 营收"}}),
    ("text", {"type": "text", "content": FULL}),
    ("done", {"type": "done"}),
]
#: 前端还没认领的事件名：照实记账，但不许冒充首屏（类别不是 render）。
UNCLAIMED_EARLY = [("answer.tail", {"type": "answer.tail", "content": "没人画它"}),
                   ("text", {"type": "text", "content": FULL}),
                   ("done", {"type": "done"})]
BLANK_FRAMES = [("text", {"type": "text"}),
                ("text", {"type": "text", "content": FULL}),
                ("done", {"type": "done"})]
#: 一帧 text 都没有的流（与 r181 的 NO_FRAME 同形）：给「尺子被摘瞎」那两枚对判件用。
NO_FRAME = [("step", {"type": "step", "name": "doc"}), ("done", {"type": "done"})]
ASK_HITL = [("text", {"type": "text", "content": PARK_TEXT}),
            ("hitl", {"type": "hitl", "pending": ["chart"]}),
            ("done", {"type": "done"})]
APPROVE_STREAM = [("status", {"type": "status", "content": "已批准，继续执行"}),
                  ("answer.headline", {"type": "answer.headline",
                                       "data": {"headline": "毛利率持平"}}),
                  ("text", {"type": "text", "content": FULL[:10]}),
                  ("text", {"type": "text", "content": FULL}),
                  ("done", {"type": "done"})]


def _load(name, path=SCRIPT_PATH):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TickingClock:
    """假钟：读一次表走 ``TICK`` 秒；``sleep`` 照实把钟拨过去。"""

    def __init__(self, start=1790000000.0, step=TICK):
        self.now = float(start)
        self.step = float(step)
        self.slept = []

    def time(self):
        self.now += self.step
        return self.now

    def monotonic(self):
        self.now += self.step
        return self.now

    def sleep(self, seconds):
        self.slept.append(float(seconds))
        self.now += float(seconds)

    def strftime(self, fmt):
        return "FIXED-TS"


class FakeResponse:
    """一发假响应：SSE 流走 ``__iter__()``，JSON 体走 ``read()``。"""

    def __init__(self, lines=(), body=b"{}"):
        self._lines = list(lines)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return self._body


def sse(events):
    """服务端每事件三行：event / data / 空行（app/api/v1/chat.py:222-223）。"""
    lines = []
    for name, data in events:
        lines.append(("event: " + name + "\n").encode("utf-8"))
        lines.append(("data: " + json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        lines.append(b"\n")
    return lines


class Transport:
    """假出口，签名与真的 ``_open(path, payload, method)`` 逐位相同；按 path 交回剧本。"""

    def __init__(self, script):
        self.script = {key: list(value) for key, value in script.items()}
        self.calls = []

    def __call__(self, path, payload=None, method="POST"):
        self.calls.append(path)
        if path == "/api/v1/login":
            return FakeResponse(body=json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        if path not in self.script:
            raise AssertionError("本单不该打这一发：" + path)
        return FakeResponse(lines=sse(self.script[path]))


def _tune(module, sidecar):
    """把量具切到离线假环境：假 URL、假产物落点、假钟，节奏阀全部松开。"""
    module.BASE_URL = "http://eval.test"
    module.SIDECAR = sidecar
    module.MIN_GAP_SECONDS = 0.0
    module.ATTEMPTS = 1
    module.RETRY_SLEEP = 0.0
    module.MAX_BLANKS = 200
    module.APPROVAL_ROUNDS = 3
    module._TOKEN = TOKEN_VALUE
    module._BLANKS = 0
    module._APPROVAL_FAILURES = 0
    module._LAST_CALL = 0.0
    module.time = TickingClock()
    return module


def _harness(tmp_path, name):
    return _tune(_load(name), tmp_path / (name + "-sidecar.jsonl"))


@pytest.fixture
def adapter(tmp_path):
    return _harness(tmp_path, "r223_transport_under_test")


def consume(module, events):
    """把合成 SSE 字节喂**真的** ``_consume()``，回观测桶。"""
    out = module._blank_observation("session-under-test")
    module._consume(FakeResponse(sse(events)), out)
    return out


def fold(module, answer, *streams):
    """一次消费到底：交回每条流的观测桶 + 这一题的读数与账（同一枚钟才允许逐位比对）。

    读数分两枚函数：``_frame_readings`` 是 R181 的尺（本单未动一格），``_arrival_readings``
    是本单新开的列；``_record_frames`` 把两者并进同一行，这里照同一口径合成。
    """
    ledger = module._new_frame_ledger()
    outs = []
    for events in streams:
        out = consume(module, events)
        outs.append(out)
        module._fold_frames(ledger, out)
    got = module._frame_readings(ledger, answer)
    got.update(module._arrival_readings(ledger))
    return outs, got, ledger


def reading_pair(module, answer, *streams):
    """几条流折成一题的账，只交读数（走 transport 里同一组函数）。"""
    _outs, got, ledger = fold(module, answer, *streams)
    return got, ledger

def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def drive(module, script, row=None):
    """走真的 ``transport()``：交回 payload 与**落盘之后重读**的两份证据件。"""
    module._open = Transport(script)
    payload = module.transport(row or {"id": "doc-31", "question": "Q3 营收多少？"})
    return payload, read_jsonl(module.SIDECAR), read_jsonl(module.frame_ledger_path())


def timed_frames(frames):
    """「每一枚帧都有到达时刻」这一句话的取证面。缺格或没时刻都当场红（判据④b）。"""
    assert frames, "帧账里没有逐帧时刻 ⇒ R223 补的读数没落地"
    for record in frames:
        assert "arrival_at" in record, "帧账记录缺 arrival_at 这一格"
        assert record["arrival_at"] is not None, "帧到了却没记时刻"
        assert isinstance(record["arrival_at"], float), "到达时刻必须是量出来的数"
    arrivals = [record["arrival_at"] for record in frames]
    assert arrivals == sorted(arrivals) and len(set(arrivals)) == len(arrivals), \
        "逐帧到达时刻必须严格单调：" + repr(arrivals)
    return frames


def break_moments(row):
    """判据③ 要的导出：断流发生在什么时间 —— (第几条流, 流内第几帧, 到达时刻)。"""
    return [(record["stream"], record["at"], record["arrival_at"])
            for record in row["frames"] if record["prefix_break"]]


# ==================== ① 逐帧到达时刻 ====================

def test_every_text_frame_carries_a_monotone_arrival(adapter):
    """帧账的 ``frames`` 与 ``text_frames`` 同数，逐枚带 arrival_at 且严格单调。"""
    (out, ), got, _ledger = fold(adapter, FULL, MULTI_FRAME)
    assert len(got["frames"]) == out["text_frames"] == 3
    assert [record["at"] for record in got["frames"]] == [1, 2, 3]
    assert [record["stream"] for record in got["frames"]] == [0, 0, 0]
    assert [record["chars"] for record in got["frames"]] == [8, 17, len(FULL)]
    assert [record["sha"] for record in got["frames"]] == [
        adapter._sha12(FULL[:8]), adapter._sha12(FULL[:17]), adapter._sha12(FULL)]
    timed_frames(got["frames"])


def test_the_frame_clock_is_the_same_one_that_stamps_first_token(adapter):
    """🔴 不是第二枚钟：首帧的到达时刻与 ``first_token_at`` 是同一个读数。"""
    (out, ), got, _ledger = fold(adapter, FULL, MULTI_FRAME)
    assert got["frames"][0]["arrival_at"] == out["first_token_at"]
    text_events = [item for item in got["events"] if item["event"] == "text"]
    assert [item["arrival_at"] for item in text_events] == \
        [item["arrival_at"] for item in got["frames"]]


def test_blank_frames_still_get_a_moment(adapter):
    """空帧也数（R181 口径），所以也必须有时刻 —— 否则断流会藏在没记账的那一枚上。"""
    (out, ), got, _ledger = fold(adapter, FULL, BLANK_FRAMES)
    assert out["text_frames"] == 2
    assert [record["chars"] for record in got["frames"]] == [0, len(FULL)]
    timed_frames(got["frames"])
    assert got["frames"][1]["arrival_at"] == out["first_token_at"]  # 首字仍认有正文那一枚


def test_the_elapsed_reading_is_arithmetic_on_the_recorded_clock(adapter):
    """``elapsed_ms`` 只能由同一格里那两枚数算出来：另起钟或拿 0 冒充都当场对不上。"""
    got, _ledger = reading_pair(adapter, FULL, HEADLINE_THEN_BREAK)
    clock = got["stream_clock"][0]
    base = clock["request_sent_at"] if clock["elapsed_base"] == "request_sent_at" \
        else clock["first_event_at"]
    for record in got["frames"] + got["events"]:
        assert record["elapsed_ms"] == pytest.approx(
            round((record["arrival_at"] - base) * 1000.0, 1), abs=0.001)


# ==================== ② 断流发生在什么时间 ====================

def test_the_break_frame_is_locatable_by_time(adapter):
    """坏形那一枚帧同时带着「第几条流第几帧」和「几点到的」——坐标系与 R181/R215 同一套。"""
    got, ledger = reading_pair(adapter, "另一条来源的答案的后半", BROKEN)
    assert got["prefix_breaks"] == 1
    assert got["per_stream"][0]["first_break_at"] == 2
    assert [record["prefix_break"] for record in got["frames"]] == [False, True, False]
    broken = [record for record in got["frames"] if record["prefix_break"]]
    assert len(broken) == 1 and broken[0]["at"] == 2 and broken[0]["stream"] == 0
    assert ledger["break_frames"][0]["at"] == broken[0]["at"] == 2
    assert ledger["break_frames"][0]["text"] == "另一条来源的答案"
    timed_frames(got["frames"])
    assert broken[0]["arrival_at"] > got["frames"][0]["arrival_at"]


def test_a_stream_that_never_breaks_reports_no_break_moment(adapter):
    """没断流时那一枚导出是空表 —— 读作「没断」，不是「没量」。"""
    got, _ledger = reading_pair(adapter, FULL, MULTI_FRAME)
    assert [record["prefix_break"] for record in got["frames"]] == [False, False, False]
    assert break_moments(dict(frames=got["frames"])) == []


# ==================== ③ 全部事件的时刻与首屏 ====================

def test_events_record_every_arrival_with_its_claimed_class(adapter):
    """``events`` 记**全部**事件（连前端还没认领的也照实记），逐枚带类别与时刻。"""
    got, _ledger = reading_pair(adapter, FULL, HEADLINE_FIRST)
    assert [(item["at"], item["event"], item["class"]) for item in got["events"]] == [
        (1, "request.started", "silent"), (2, "status", "note"),
        (3, "answer.headline", "render"), (4, "heartbeat", "silent"),
        (5, "text", "render"), (6, "step", "render"), (7, "text", "render"),
        (8, "sources", "render"), (9, "done", "terminal")]
    assert len({item["arrival_at"] for item in got["events"]}) == 9


def test_the_first_screen_reading_is_the_headline_not_the_body(adapter):
    """B 门那把尺：首屏＝首枚非-text 可见事件。run7 那枚 p50 24.3 s 量的不是这件事。"""
    got, _ledger = reading_pair(adapter, FULL, HEADLINE_FIRST)
    assert got["first_visible_event"] == "answer.headline"
    headline = [item for item in got["events"] if item["event"] == "answer.headline"][0]
    assert got["first_visible_at"] == headline["arrival_at"]
    assert got["first_visible_ms"] == headline["elapsed_ms"] == 500.0  # 零点退到第一枚事件
    assert got["first_visible_ms"] < 1000.0            # B 门口径：首屏 ≤1 s
    assert got["first_visible_ms"] < got["frames"][0]["elapsed_ms"]  # 首屏在正文之前


def test_the_body_frame_never_wins_the_first_screen(adapter):
    """只有正文的流：首屏读「没量到」，不许拿 ``first_token_at`` 顶上。"""
    got, _ledger = reading_pair(adapter, FULL, MULTI_FRAME)
    assert got["first_visible_event"] == ""
    assert got["first_visible_at"] is None and got["first_visible_ms"] is None
    assert got["frames"][0]["arrival_at"] is not None


def test_a_step_event_wins_the_first_screen_when_there_is_no_headline(adapter):
    """口径是「render 且不是 text」，不是「只有线索卡才算」：step 同样画在屏上。"""
    got, _ledger = reading_pair(adapter, FULL, STEP_FIRST_VISIBLE)
    assert got["first_visible_event"] == "step"
    assert got["first_visible_ms"] == 500.0


def test_note_and_silent_events_never_win_the_first_screen(adapter):
    """``status`` 只进过程提示条、``heartbeat`` 显式不画 ⇒ 屏上无物就是没量到。"""
    out = consume(adapter, SILENT_ONLY)
    got, _ledger = reading_pair(adapter, "", SILENT_ONLY)
    assert out["cached"] is False and out["text_frames"] == 0
    assert [item["event"] for item in got["events"]] == [
        "request.started", "status", "heartbeat", "done"]
    assert got["first_visible_event"] == ""
    assert got["first_visible_at"] is None and got["first_visible_ms"] is None


def test_the_earliest_visible_event_wins_not_the_pretty_name(adapter):
    """出处卡比线索卡先到 ⇒ 首屏读出处卡。这一格量的是「什么时候有东西上了屏」。"""
    got, _ledger = reading_pair(adapter, FULL, SOURCES_BEFORE_HEADLINE)
    assert got["first_visible_event"] == "sources"
    assert got["first_visible_ms"] == 250.0


def test_an_unclaimed_event_is_recorded_but_does_not_win_the_first_screen(adapter):
    """前端没认领的名字：照实记账并标 unclaimed（新事件名先露脸），但不许冒充首屏。"""
    got, _ledger = reading_pair(adapter, FULL, UNCLAIMED_EARLY)
    assert got["events"][0]["event"] == "answer.tail"
    assert got["events"][0]["class"] == adapter.UNCLAIMED_EVENT_CLASS == "unclaimed"
    assert got["first_visible_event"] == ""


def _frontend_claims():
    """读前端那张认领表的字面（只读，不改 ``frontend/**``）。"""
    text = FRONTEND_SESSIONS.read_text(encoding="utf-8")
    block = re.search(r"export const EVENT_CLAIMS = \{(.*?)\n\}", text, re.S)
    assert block is not None, "前端那张认领表读不到 ⇒ 抄本没有对证"
    entry = re.compile(
        r"""^(?:'([^']+)'|"([^"]+)"|([A-Za-z][A-Za-z0-9_.]*))\s*:\s*'([a-zA-Z.]+)',?$""")
    table = {}
    for raw in block.group(1).splitlines():
        line = raw.strip()
        if not line or line.startswith(("*", "//", "/*")):
            continue
        match = entry.match(line)
        assert match is not None, "前端认领表有一行读不懂：" + line
        name = next(group for group in match.groups()[:3] if group)
        table[name] = match.group(4)
    assert table, "前端认领表解析成空 ⇒ 这枚钉是空的"
    return table


def test_the_claim_table_copy_matches_the_frontend(adapter):
    """判据「抄本不许漂」：``EVENT_CLASSES`` 与 ``EVENT_CLAIMS`` 逐枚相等。"""
    claims = _frontend_claims()
    assert adapter.EVENT_CLASSES == claims
    for name in ("answer.headline", "sources", "step", "text", "status", "heartbeat"):
        assert name in claims, name


# ==================== ④ 零点：用的是哪一侧，写进账 ====================

def test_the_unit_path_falls_back_to_the_first_event_and_says_so(adapter):
    """直连 ``_consume`` 没有 POST 时刻 ⇒ 退到本流第一枚事件，且把用的是哪一侧写进账。"""
    got, _ledger = reading_pair(adapter, FULL, HEADLINE_FIRST)
    assert got["stream_clock"] == [{
        "stream": 0, "request_sent_at": None,
        "first_event_at": got["events"][0]["arrival_at"], "elapsed_base": "first_event_at"}]
    assert got["events"][0]["elapsed_ms"] == 0.0


def test_the_real_run_zeroes_at_the_post(adapter):
    """真跑分路径：零点＝发出 POST 那一刻 ⇒ 首屏毫秒里含首字节之前那一段等待。"""
    _payload, _sidecar, frames = drive(adapter, {"/api/v1/ask": HEADLINE_FIRST})
    row = frames[0]
    clock = row["stream_clock"][0]
    assert clock["elapsed_base"] == "request_sent_at"
    assert clock["request_sent_at"] is not None
    assert clock["request_sent_at"] < clock["first_event_at"] == row["events"][0]["arrival_at"]
    assert row["events"][0]["elapsed_ms"] > 0.0
    assert row["first_visible_event"] == "answer.headline"
    assert row["first_visible_ms"] == pytest.approx(
        (row["first_visible_at"] - clock["request_sent_at"]) * 1000.0, abs=0.05)
    assert 0.0 < row["first_visible_ms"] < 1000.0     # B 门那一格今天才有尺子


def test_a_missing_side_reads_null_and_not_zero(adapter):
    """🔴 禁止估算：缺一侧就是 null，不许拿 0 冒充「同一时刻」，也不许让没量到的抢首屏。"""
    assert adapter._elapsed_ms(None, 1000.0) is None
    assert adapter._elapsed_ms(1000.0, None) is None
    out = adapter._blank_observation("session-under-test")
    out["event_arrivals"] = [{"at": 1, "event": "answer.headline",
                              "class": "render", "arrival_at": None}]
    ledger = adapter._new_frame_ledger()
    adapter._fold_arrivals(ledger, out, 0)
    assert ledger["clocks"][0]["elapsed_base"] is None
    assert ledger["clocks"][0]["first_event_at"] is None
    assert ledger["events"][0]["elapsed_ms"] is None
    got = adapter._arrival_readings(ledger)
    assert (got["first_visible_event"], got["first_visible_at"], got["first_visible_ms"]) == \
        ("", None, None)
    assert adapter._frame_readings(ledger, "").get("first_visible_event") is None  # 不在旧层


# ==================== ⑧ 两条流各有各的钟 ====================

def test_two_streams_keep_their_own_clocks_and_coordinates(adapter):
    """挂起轮 + 批准轮：``at`` 是**流内**序号，每条流各有一本钟，首屏跨流取最早。"""
    # 🔴 两本钟不混读：每一条记录的 ``elapsed_ms`` 都对**自己那条流**的零点，用的是
    # 哪一侧写在 ``stream_clock[i].elapsed_base`` 里（读的人不必猜）。
    _payload, sidecar, frames = drive(
        adapter, {"/api/v1/ask": ASK_HITL, "/api/v1/approve": APPROVE_STREAM})
    row = frames[0]
    assert sidecar[0]["kind"] == row["kind"] == "approved_ok"
    assert [clock["stream"] for clock in row["stream_clock"]] == [0, 1]
    # 零点一侧一侧写清楚：/ask 那条流抄得到 _pace 的放行戳；批准那条流量具不另读表 ⇒
    # 老实退到本流第一枚事件（「禁止估算」的另一半：抄不到就写抄不到）。
    assert [clock["elapsed_base"] for clock in row["stream_clock"]] == [
        "request_sent_at", "first_event_at"]
    assert row["stream_clock"][1]["request_sent_at"] is None
    assert row["stream_clock"][0]["request_sent_at"] < row["stream_clock"][1]["first_event_at"]
    assert [(item["stream"], item["at"]) for item in row["frames"]] == [(0, 1), (1, 1), (1, 2)]
    assert [(item["stream"], item["at"]) for item in row["events"]][:3] == [(0, 1), (0, 2),
                                                                            (0, 3)]
    assert [(item["stream"], item["at"]) for item in row["events"]][-2:] == [(1, 4), (1, 5)]
    assert row["per_stream"] == [{"frames": 1, "breaks": 0, "first_break_at": 0},
                                 {"frames": 2, "breaks": 0, "first_break_at": 0}]
    headline = [item for item in row["events"] if item["event"] == "answer.headline"]
    assert len(headline) == 1 and headline[0]["stream"] == 1
    # 跨流取**最早**那一枚可见事件：挂起轮那张 HITL 卡（render 且非正文）先上了屏，批准轮的
    # 线索卡在后 —— 这一格量的是「什么时候有东西上了屏」，不是卡片的名字。
    hitl = [item for item in row["events"] if item["event"] == "hitl"]
    assert row["first_visible_event"] == "hitl" and hitl[0]["stream"] == 0
    assert row["first_visible_at"] == hitl[0]["arrival_at"]
    first = row["stream_clock"][0]
    assert row["first_visible_ms"] == pytest.approx(
        (hitl[0]["arrival_at"] - first["request_sent_at"]) * 1000.0, abs=0.05)
    # 批准轮那一枚线索卡的毫秒是「相对本流第一枚事件」——两本钟不混读
    assert headline[0]["elapsed_ms"] == 250.0
    assert row["first_visible_at"] < headline[0]["arrival_at"]  # 跨流比时刻，不比各自的毫秒


# ==================== ⑥ 落盘：从 JSONL 里直接读出来 ====================

def test_the_moments_survive_the_round_trip_through_disk(adapter):
    """判据③：断流时刻与首枚非-text 事件时刻都从**落盘的那份 JSONL** 里读得到。"""
    _payload, _sidecar, frames = drive(adapter, {"/api/v1/ask": HEADLINE_THEN_BREAK})
    assert adapter.frame_ledger_path().exists()
    row = frames[0]
    assert break_moments(row) == [(0, 2, row["frames"][1]["arrival_at"])]
    assert isinstance(break_moments(row)[0][2], float)
    assert row["first_visible_event"] == "answer.headline"
    assert isinstance(row["first_visible_at"], float) and isinstance(row["first_visible_ms"],
                                                                  float)
    assert break_moments(row)[0][2] > row["first_visible_at"]     # 断在首屏之后
    timed_frames(row["frames"])
    # 逐帧指纹与既有那把尺对得上：新列不是第二把尺，只是给同一枚帧补了时刻
    assert [record["sha"] for record in row["frames"]] == [
        adapter._sha12(FULL[:8]), adapter._sha12("另一条来源的答案"),
        adapter._sha12("另一条来源的答案的后半")]


# ==================== ⑤ 🔴 只加读数 ====================

def test_turning_the_two_recorders_off_leaves_every_old_cell_identical(tmp_path):
    """正证：把两枚抄表员摘成空函数，payload / sidecar / 帧账既有每一格逐字节相同。"""
    with_watch = _harness(tmp_path, "r223_with_arrivals")
    blind = _harness(tmp_path, "r223_without_arrivals")
    blind._note_event_arrival = lambda out, name, arrival: None
    blind._note_frame_arrival = lambda out, frame, arrival: None
    script = {"/api/v1/ask": HEADLINE_THEN_BREAK}
    payload_a, sidecar_a, frames_a = drive(with_watch, script)
    payload_b, sidecar_b, frames_b = drive(blind, script)
    assert payload_a == payload_b                        # 交回采集器的五键一字未动
    assert sidecar_a == sidecar_b                        # 九键 + 甲案七键一字未动
    row_a, row_b = frames_a[0], frames_b[0]
    for key in sorted((JOIN_KEYS | OLD_CELLS) - {"session_id"}):
        assert json.dumps(row_a[key], sort_keys=True, ensure_ascii=False) == \
            json.dumps(row_b[key], sort_keys=True, ensure_ascii=False), key
    # session_id 是每题一枚 uuid4，两次跑必然不同 —— 它不是读数，这里只比格式
    assert re.fullmatch(r"[0-9a-f]{32}", row_a["session_id"])
    assert re.fullmatch(r"[0-9a-f]{32}", row_b["session_id"])
    for key in ("frames", "events"):
        assert row_b[key] == [] and row_a[key], key
    # 钟那一格本来就不是抄表员写的：POST 时刻照记，只是没枚事件可对表
    assert [clock["first_event_at"] for clock in row_b["stream_clock"]] == [None]
    assert [clock["first_event_at"] for clock in row_a["stream_clock"]] != [None]
    assert row_a["queue"] == {} and row_b["queue"] == {}     # 这一题没走队列道
    assert (row_b["first_visible_event"], row_b["first_visible_at"]) == ("", None)
    assert row_b["first_visible_ms"] is None
    assert row_a["first_visible_event"] == "answer.headline"
    assert break_moments(row_a) and break_moments(row_b) == []


def test_the_frame_row_gains_exactly_the_new_cells_and_the_sidecar_none(adapter):
    """新键只开在帧账那一层：帧账多且仅多这七格，sidecar 一格都不许多。"""
    _payload, sidecar, frames = drive(adapter, {"/api/v1/ask": HEADLINE_FIRST})
    row = frames[0]
    assert set(row) - (JOIN_KEYS | OLD_CELLS) == NEW_CELLS
    assert JOIN_KEYS <= set(row) and OLD_CELLS <= set(row)
    record = sidecar[0]
    assert tuple(list(record)[:9]) == SIDECAR_BASE_KEYS
    assert set(record) - set(SIDECAR_BASE_KEYS) <= (R123_EXTRA_KEYS | {"pre_answer"})
    assert not (set(record) & NEW_CELLS)


def test_r181_own_ruler_function_returns_exactly_the_old_cells(adapter):
    """分层证据（判据「只加读数」最硬的一枚）：``_frame_readings`` 的返回形状没动。

    键集与本单开工前逐字相同，取值也逐格相同 —— 新列全在 ``_arrival_readings`` 那一层，
    由 ``_record_frames`` 并进落盘行。R181 及其反证件因此一个都不用改。
    """
    ledger = adapter._new_frame_ledger()
    adapter._fold_frames(ledger, consume(adapter, HEADLINE_FIRST))
    ruler = adapter._frame_readings(ledger, FULL)
    assert set(ruler) == OLD_CELLS - {"criterion_two_holds"}
    assert ruler["text_frames"] == 2 and ruler["prefix_breaks"] == 0
    new = adapter._arrival_readings(ledger)
    assert set(new) == NEW_CELLS
    assert not (set(ruler) & set(new))
    row = dict(ruler, **new)
    # 两层各交自己那几格；criterion_two_holds 由 _record_frames 折进落盘行（上面那枚
    # 落盘件已经连它一起钉过），这一枚只管两枚函数自己的形状。
    assert set(row) - JOIN_KEYS == (OLD_CELLS | NEW_CELLS) - {"criterion_two_holds"}

def test_blinding_the_ruler_also_blanks_the_arrival_ledger(adapter, monkeypatch):
    """派生而非另起一把尺：把 ``_count_text_frame`` 摘瞎，逐帧那一格必须一起空（R215 同族）。

    这一格是 ``tests/test_r181_text_frame_ruler.py:467`` 那枚常驻反证还站得住的前提 —— 帧账
    里不许有第二份「几枚帧」的计数，否则把尺子摘掉之后它会被新列悄悄救活。
    """
    def blind(out, frame):        # 「不计数」：只留末帧，帧数与坏形一律不记
        out["last_text_frame"] = frame

    monkeypatch.setattr(adapter, "_count_text_frame", blind)
    got, _ledger = reading_pair(adapter, FULL, MULTI_FRAME)
    assert got["text_frames"] == 0                           # 尺子瞎了
    assert got["frames"] == []                               # 🔴 新列跟着瞎
    assert len(got["events"]) == 4                           # 事件账记的是事件，不是帧


def test_the_old_layer_stays_blind_with_the_ruler_while_the_row_tells_the_two_apart(
        adapter, monkeypatch):
    """分层落地后的对判：R181 那枚整字典反证照旧成立，新列只在**行级**分得开两条流。

    ``test_r181_text_frame_ruler.py:467`` 说「把计数摘瞎之后，三帧流与零帧流必须同形」——
    它比的是 ``_frame_readings`` 的返回，本单没动那一层，所以那枚件不需要改；而落盘的那一行
    多带了到达时刻，两条流在**行级**仍然分得开（哪些事件到过、几点到的，本来就不是帧计数
    那把尺该说的话）。需要总控补的只有 :426 那枚行级名单。
    """
    def blind(out, frame):
        out["last_text_frame"] = frame

    monkeypatch.setattr(adapter, "_count_text_frame", blind)
    ledger_a = adapter._new_frame_ledger()
    adapter._fold_frames(ledger_a, consume(adapter, MULTI_FRAME))
    ledger_b = adapter._new_frame_ledger()
    adapter._fold_frames(ledger_b, consume(adapter, NO_FRAME))
    ruler_a = adapter._frame_readings(ledger_a, FULL)
    ruler_b = adapter._frame_readings(ledger_b, FULL)
    assert ruler_a == ruler_b                                  # ⇒ R181 的反证仍绿
    row_a = dict(ruler_a, **adapter._arrival_readings(ledger_a))
    row_b = dict(ruler_b, **adapter._arrival_readings(ledger_b))
    assert row_a["events"] != row_b["events"]                  # 分开的只有新列
    assert (row_a["first_visible_event"], row_b["first_visible_event"]) == ("", "step")
    assert row_a["frames"] == row_b["frames"] == []            # 派生列跟着尺子一起瞎
    assert row_a != row_b


# ==================== ⑨ 反证钉：红必须落在本格（判据④） ====================

#: 原件在本枚件 import 那一刻的字面。反证全在临时根副本上做，跑完必须还是这一枚 sha。
RULER_SHA_AT_IMPORT = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()

#: (名字, 锚点, 换成什么) —— 逐枚在临时根副本上动手，跟踪里的原件一字不改。
MUTANTS = {
    "drop_the_frame_arrival_recorder": (
        "            _note_frame_arrival(out, frame, arrival)  # R223：只补时刻，不动计数\n",
        ""),
    "stamp_no_arrival": (
        '    records.append({"at": at, "arrival_at": arrival, "chars": len(frame),',
        '    records.append({"at": at, "arrival_at": None, "chars": len(frame),'),
    "loosen_the_first_screen_filter": (
        '    return _event_class(name) == VISIBLE_EVENT_CLASS and str(name) != "text"',
        '    return _event_class(name) == VISIBLE_EVENT_CLASS'),
    "lose_the_headline_from_the_table": (
        '    "answer.headline": "render",\n',
        ""),
}


def _mutant(tmp_path, name):
    original = SCRIPT_PATH.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    anchor, replacement = MUTANTS[name]
    assert text.count(anchor) == 1, "锚点在原件里不唯一，这枚反证是空的"
    mutated = text.replace(anchor, replacement, 1)
    assert mutated != text, "反证没作用到东西上"
    target = tmp_path / ("mutant_r223_" + name + ".py")
    target.write_text(mutated, encoding="utf-8", newline="\n")
    module = _tune(_load("r223_" + name, target), tmp_path / (name + "-sidecar.jsonl"))
    assert SCRIPT_PATH.read_bytes() == original, "跟踪里的原件被动了"
    return module


def test_counter_evidence_dropping_the_recorder_goes_red_here(tmp_path):
    """反证甲：帧账缺 ``arrival_at`` ⇒ 断流时刻导不出来，本格的取证面当场红。"""
    module = _mutant(tmp_path, "drop_the_frame_arrival_recorder")
    _payload, _sidecar, frames = drive(module, {"/api/v1/ask": HEADLINE_THEN_BREAK})
    row = frames[0]
    assert row["frames"] == [] and row["events"], "摘错地方了：连事件账都没了"
    with pytest.raises(AssertionError, match="逐帧时刻"):
        timed_frames(row["frames"])
    assert break_moments(row) == []      # 尺子还在响，但「几点断的」导不出来了
    assert row["prefix_breaks"] == 1


def test_counter_evidence_an_unstamped_frame_goes_red_here(tmp_path):
    """反证乙：帧记上了却没时刻（写成 null）⇒ 「逐枚单调」那一枚钉当场红。"""
    module = _mutant(tmp_path, "stamp_no_arrival")
    got, _ledger = reading_pair(module, FULL, MULTI_FRAME)
    assert len(got["frames"]) == 3, "摘错地方了：帧账整格都没了"
    assert [record["arrival_at"] for record in got["frames"]] == [None, None, None]
    with pytest.raises(AssertionError):
        timed_frames(got["frames"])


def test_counter_evidence_loosening_the_filter_goes_red_here(tmp_path, adapter):
    """反证丙：首屏放宽成「任何 render 事件」⇒ 正文冒充首屏，B 门那把尺就成了假话。"""
    module = _mutant(tmp_path, "loosen_the_first_screen_filter")
    got, _ledger = reading_pair(module, FULL, MULTI_FRAME)
    assert got["first_visible_event"] == "text", "摘掉过滤仍读不到 text ⇒ 这枚钉是空的"
    assert got["first_visible_at"] == got["frames"][0]["arrival_at"] == \
        got["stream_clock"][0]["first_event_at"]
    real, _ = reading_pair(adapter, FULL, MULTI_FRAME)   # 对照组：原件口径正文不算首屏
    assert real["first_visible_event"] == ""


def test_counter_evidence_losing_the_headline_goes_red_here(tmp_path):
    """反证丁：认领表里漏掉 ``answer.headline`` ⇒ 首屏退到 step，抄本漂移不再静默。"""
    module = _mutant(tmp_path, "lose_the_headline_from_the_table")
    assert module._event_class("answer.headline") == module.UNCLAIMED_EVENT_CLASS
    got, _ledger = reading_pair(module, FULL, HEADLINE_FIRST)
    assert got["first_visible_event"] == "step", "摘掉线索卡还读到它 ⇒ 这枚钉是空的"
    assert _frontend_claims()["answer.headline"] == "render"   # 对证还在，红得有名有据


def test_the_tracked_ruler_is_byte_identical_after_every_overlay_proof():
    """临时根反证不许漏进真树：量具从 import 到现在还是同一枚字面。"""
    text = SCRIPT_PATH.read_bytes().decode("utf-8")
    assert "_note_frame_arrival(out, frame, arrival)" in text
    assert '"answer.headline": "render",' in text
    assert 'and str(name) != "text"' in text
    assert '"arrival_at": arrival' in text
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == RULER_SHA_AT_IMPORT


# ==================== 判据⑤：新读数不追溯历史 ====================

def test_the_history_ledgers_have_no_arrival_columns():
    """run6 / run7 的帧账原件里没有这些列 ⇒ 旧轮次不许被读成「零停表 / 无断流」。"""
    for path in (RUN6_LEDGER, RUN7_LEDGER):
        assert path.exists(), path.name + " 不在树里，这枚口径件是空的"
        rows = read_jsonl(path)
        assert len(rows) == 105, path.name
        keys = set().union(*[set(row) for row in rows])
        assert not (keys & NEW_CELLS), path.name + " 里出现了新列：" + repr(keys & NEW_CELLS)
        assert "prefix_breaks" in keys and "per_stream" in keys
    assert {row["kind"] for row in read_jsonl(RUN6_LEDGER)} == {
        "ok", "approved_ok", "error_event"}
    assert {row["kind"] for row in read_jsonl(RUN7_LEDGER)} == {"ok", "approved_ok"}
