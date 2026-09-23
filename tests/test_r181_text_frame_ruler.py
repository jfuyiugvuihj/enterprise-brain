"""R181 判据②：给跑分窗的 ``event: text`` 装一把尺子 —— 只观测，不改评分。

判据原文：施工单 R181 §2。全程离线：urllib 的 opener 被换成记账的假传输（真 ``_open`` 仍
负责拼 URL 与请求体），零服务 / 零模型 / 零容器 / 零连库；两份产物都写 tmp_path，仓内零字节
（``test_the_frame_ledger_path_is_resolved_at_write_time`` 就是钉这一条的）。

钉住的五件事：
  1. 一题的 ``text`` 帧计数真的在数：三帧读 3、一帧读 1、零帧读 0；
  2. 前缀单调坏形计数：相邻两帧，后帧必须以先帧为前缀（cumulative 语义），不满足记一次；
  3. 末帧与终答的一致性按 **covering** 判（末帧把终答所缺的部分盖住即算一致），
     ``missing_chars`` / ``extra_chars`` 两枚各自成立 —— 不许退化成严格相等；
  4. 🔴 只观测不改评分：``answer`` / ``APPROVAL_FAILED_SENTINEL`` / ``cached`` /
     ``first_token_at`` / ``steps`` 五枚取值口径没动；105 题重放的 answers 与 sidecar 九键
     逐题等于开工前（``8e1136d``）那份摘要 —— 见 ``PRE_R181_ANSWERS_SHA`` 两枚常数；
  5. 两把常驻反证：把计数改回「不计数」、把前缀缩短吞成静默，各自都让本文件的具名用例变红
     （真实文件动手改的红色回显与还原 sha 见交付说明）。

期望读数一律 09-23 在本树实取（``python`` 直连 ``_consume`` 跑一遍合成流），不是手推的。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
COLLECTOR_PATH = REPO_ROOT / "scripts" / "collect_evaluation_answers.py"
FIXTURE_105 = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 侧车既有九键 + 甲案七键（R181 一个字都没往里加）。
SIDECAR_BASE_KEYS = ("id", "kind", "attempt", "sentinel", "evidence_n",
                     "answer_chars", "tool_calls", "wall_ms", "ts")
R123_EXTRA_KEYS = {"pre_kind", "pre_answer_chars", "pre_evidence_n", "approved",
                   "approval_rounds", "approval_http_status", "approval_error"}
PAYLOAD_KEYS = {"answer", "evidence", "first_token_at", "thinking_chars", "tool_calls"}
#: 帧证据件的一行里，除 join 键之外该有的读数（判据② 的四枚 + covering 布尔 + 取证辅助）。
FRAME_READING_KEYS = {"text_frames", "prefix_breaks", "missing_chars", "extra_chars",
                      "last_frame_covers_answer", "last_frame_chars", "last_frame_sha",
                      "answer_chars", "answer_sha", "streams", "max_stream_frames",
                      "per_stream", "criterion_two_holds"}
JOIN_KEYS = {"id", "kind", "attempt", "sentinel", "session_id", "ts"}

FULL = "据统计，Q3 营收 1200 万元，环比增长 8%，毛利率持平。"
PARK_TEXT = "本轮在「生成图表」前等待你确认，确认后才会执行，目前尚未产出回答内容。"
TOKEN_VALUE = "eval-bearer-token"

# ===== 七类合成 SSE 流（判据② 要求覆盖的用例）=====
MULTI_FRAME = [("text", {"type": "text", "content": FULL[:8]}),
               ("text", {"type": "text", "content": FULL[:17]}),
               ("text", {"type": "text", "content": FULL}),
               ("done", {"type": "done"})]
SINGLE_FRAME = [("text", {"type": "text", "content": FULL}), ("done", {"type": "done"})]
NO_FRAME = [("step", {"type": "step", "name": "doc"}), ("done", {"type": "done"})]
SHORTENED = [("text", {"type": "text", "content": FULL}),
             ("text", {"type": "text", "content": FULL[:5]}),        # 前缀缩短
             ("text", {"type": "text", "content": FULL[:5] + "尾巴"}),
             ("done", {"type": "done"})]
OFF_SOURCE = [("text", {"type": "text", "content": "据统计"}),
              ("text", {"type": "text", "content": "另一条来源的答案"}),   # 非前缀坏形
              ("text", {"type": "text", "content": "另一条来源的答案的后半"}),
              ("done", {"type": "done"})]
NO_TAIL = [("text", {"type": "text", "content": FULL[:8]}),
           ("text", {"type": "text", "content": FULL[:17]}),
           ("done", {"type": "done"})]                     # 收尾帧没到（末帧短于终答）
CACHE_HIT = [("status", {"type": "status", "content": "📋 缓存命中，直接返回"}),
             ("text", {"type": "text", "content": FULL, "cached": True}),
             ("done", {"type": "done"})]
#: 末帧长于终答的形状：终答只到末帧的中段（今天真机路径不可达，见用例名）
POLLED_PREFIX = FULL[:12]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLLECTOR = _load("r181_collector", COLLECTOR_PATH)


def sse(events):
    """服务端每事件三行：event / data / 空行（app/api/v1/chat.py:222-223）。"""
    lines = []
    for name, data in events:
        lines.append(("event: " + name + "\n").encode("utf-8"))
        lines.append(("data: " + json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        lines.append(b"\n")
    return lines


class FakeResponse:
    def __init__(self, lines=None, body=b"{}"):
        self._lines = lines or []
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)

    def read(self):
        return self._body


class FakeTime:
    """确定性假钟：改前改后跑同一条时间轴，墙钟字段才允许逐题比对。"""

    def __init__(self):
        self.now = 1790000000.0

    def time(self):
        self.now += 0.001
        return self.now

    def monotonic(self):
        self.now += 0.001
        return self.now

    def sleep(self, seconds):
        return None

    def strftime(self, fmt):
        return "FIXED-TS"


class ScriptedOpener:
    """只挡网络：按 path 交回事先写好的事件流；入队那道交回 JSON 体。"""

    def __init__(self, script, queue_result=""):
        self.script = script
        self.queue_result = queue_result
        self.calls = []

    def open(self, request, timeout=None):
        path = urlparse(request.full_url).path
        self.calls.append(path)
        if path == "/api/v1/login":
            return FakeResponse(body=json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        if path.startswith("/api/v1/queue/status/"):
            return FakeResponse(body=json.dumps(
                {"status": "done", "result": self.queue_result}).encode("utf-8"))
        return FakeResponse(lines=sse(self.script.get(path) or []))


@pytest.fixture
def adapter(tmp_path):
    module = _load("r181_transport_under_test", SCRIPT_PATH)
    module.BASE_URL = "http://eval.test"
    module.SIDECAR = tmp_path / "sidecar-run6.jsonl"
    module.MIN_GAP_SECONDS = 0.0
    module.ATTEMPTS = 1
    module.RETRY_SLEEP = 0.0
    module.MAX_BLANKS = 200
    module.APPROVAL_ROUNDS = 3
    module._TOKEN = TOKEN_VALUE
    module._BLANKS = 0
    module._APPROVAL_FAILURES = 0
    module._LAST_CALL = 0.0
    module.time = FakeTime()
    return module


def consume(module, events):
    """把合成 SSE 字节喂**真的** ``_consume()``，回观测桶。"""
    out = module._blank_observation("session-under-test")
    module._consume(FakeResponse(sse(events)), out)
    return out


def rollup(module, *streams):
    """几条流折成"一题"的帧账本（与 transport 里的 fold 路径同一组函数）。"""
    ledger = module._new_frame_ledger()
    for events in streams:
        module._fold_frames(ledger, consume(module, events))
    return ledger


def readings(module, streams, answer):
    return module._frame_readings(rollup(module, *streams), answer)


def drive(module, script, row, queue_result=""):
    opener = ScriptedOpener(script, queue_result)
    module._OPENER = opener
    payload = module.transport(row)
    return payload, opener, read_jsonl(module.SIDECAR), read_jsonl(module.frame_ledger_path())


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fixture_row(row_id):
    for line in FIXTURE_105.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            if str(row.get("id")) == row_id:
                return row
    raise AssertionError(row_id + " 不在 " + FIXTURE_105.name + " 里")


# ===== 一、判据② 要求的七类合成流：一律喂**真的** ``_consume()`` =====

def test_case_1_a_multi_frame_stream_is_counted_frame_by_frame(adapter):
    """多帧正常：三帧 cumulative 一路长到终答，帧数读 3、坏形读 0、判据② 成立。"""
    out = consume(adapter, MULTI_FRAME)
    assert (out["text_frames"], out["prefix_breaks"], out["first_break_at"]) == (3, 0, 0)
    assert out["last_text_frame"] == FULL
    assert out["answer"] == FULL  # 🔴 取值口径没动：末帧覆盖前帧
    got = readings(adapter, [MULTI_FRAME], FULL)
    assert (got["missing_chars"], got["extra_chars"]) == (0, 0)
    assert got["last_frame_covers_answer"] is True
    assert got["max_stream_frames"] == 3 and got["streams"] == 1
    assert adapter._frame_verdict(got) is True


def test_case_2_a_single_frame_stream_reads_one_and_fails_the_count(adapter):
    """单帧：整段一帧（今天实时腿的主形态）——帧数达标不了 ">1"，但一致性是成立的。"""
    out = consume(adapter, SINGLE_FRAME)
    assert (out["text_frames"], out["prefix_breaks"]) == (1, 0)
    got = readings(adapter, [SINGLE_FRAME], FULL)
    assert (got["missing_chars"], got["extra_chars"]) == (0, 0)
    assert got["last_frame_covers_answer"] is True
    assert adapter._frame_verdict(got) is False  # 判据② 的 ">1" 不成立，且是被量出来的


def test_case_3_an_empty_stream_reads_zero_frames(adapter):
    """空流：一帧都没有 ⇒ 空读。covering 布尔在这里是空真的，靠 ``text_frames`` 拆穿。"""
    out = consume(adapter, NO_FRAME)
    assert (out["text_frames"], out["last_text_frame"], out["answer"]) == (0, "", "")
    got = readings(adapter, [NO_FRAME], "")
    assert got["text_frames"] == 0 and got["max_stream_frames"] == 0
    assert got["streams"] == 1  # 量过了：这条流确实到了收端，只是没带正文
    assert adapter._frame_verdict(got) is False


def test_case_4_a_non_prefix_frame_is_counted_as_one_break(adapter):
    """非前缀坏形：第二帧换了来源，记一次坏形并留下首枚序号。"""
    out = consume(adapter, OFF_SOURCE)
    assert (out["text_frames"], out["prefix_breaks"], out["first_break_at"]) == (3, 1, 2)
    last = "另一条来源的答案的后半"
    got = readings(adapter, [OFF_SOURCE], last)
    assert (got["missing_chars"], got["extra_chars"]) == (0, 0)  # 末帧自己就是终答
    assert adapter._frame_verdict(got) is False       # 坏形一票否决


def test_case_4b_a_shortened_prefix_is_a_break_not_a_silence(adapter):
    """前缀缩短（后帧比先帧短）：坏形必须报出来，不许被"末帧覆盖前帧"吞掉。"""
    out = consume(adapter, SHORTENED)
    assert (out["text_frames"], out["prefix_breaks"], out["first_break_at"]) == (3, 1, 2)
    assert out["last_text_frame"] == FULL[:5] + "尾巴"
    assert out["answer"] == FULL[:5] + "尾巴"          # 取值口径仍是末帧，没替产品改字
    got = readings(adapter, [SHORTENED], FULL)
    assert (got["missing_chars"], got["extra_chars"]) == (2, 27)
    assert got["last_frame_covers_answer"] is False


def test_case_5_the_last_frame_being_shorter_than_the_answer_is_a_gap(adapter):
    """末帧短于终答：终答里有 15 枚字是末帧没带出来的 ⇒ covering 判不一致。"""
    out = consume(adapter, NO_TAIL)
    assert (out["text_frames"], out["prefix_breaks"]) == (2, 0)
    assert out["answer"] == FULL[:17]                  # 收端只见末帧
    got = readings(adapter, [NO_TAIL], FULL)
    assert (got["missing_chars"], got["extra_chars"]) == (0, 15)
    assert got["last_frame_covers_answer"] is False
    assert (got["last_frame_chars"], got["answer_chars"]) == (17, 32)


def test_case_6_the_last_frame_being_longer_than_the_answer_still_counts_as_consistent(adapter):
    """末帧长于终答：covering 语义**算一致**（判据写死：不许改成严格相等）。

    今天真机路径上这形状不可达 —— 终答恒等于最后一条流的末帧（``chat.py:1943`` 实时收尾、
    ``:2415`` 批准恢复），所以这一格钉的是尺子的口径，不是产品行为。
    """
    got = readings(adapter, [SINGLE_FRAME], POLLED_PREFIX)
    assert (got["missing_chars"], got["extra_chars"]) == (20, 0)
    assert got["last_frame_covers_answer"] is True
    assert got["last_frame_sha"] != got["answer_sha"]  # 两枚指纹不同 ⇒ 没退化成"相等才算"


def test_case_7_a_cache_hit_is_a_single_covering_frame(adapter):
    """缓存命中单帧：一帧、零坏形、末帧＝终答。命中道（``chat.py:1660``）本来就只有这一帧。"""
    out = consume(adapter, CACHE_HIT)
    assert out["cached"] is True
    assert (out["text_frames"], out["prefix_breaks"]) == (1, 0)
    got = readings(adapter, [CACHE_HIT], FULL)
    assert (got["missing_chars"], got["extra_chars"]) == (0, 0)
    assert got["last_frame_covers_answer"] is True
    assert got["last_frame_sha"] == got["answer_sha"]
    assert adapter._frame_verdict(got) is False        # ">1" 不成立：命中不等于"没流式"的失败


# ===== 二、逐题落盘：读数走 transport() 的真实路径 =====

def test_a_polled_tail_is_measured_against_the_last_frame(adapter):
    """入队取回的正文不是帧：末帧短于终答时，``extra_chars`` 就是那段尾巴。"""
    row = fixture_row("doc-01")
    script = {"/api/v1/ask": [("queued", {"type": "queued", "request_id": "req-1"}),
                              ("text", {"type": "text", "content": FULL[:17]}),
                              ("done", {"type": "done"})]}
    payload, _, _, frames = drive(adapter, script, row, queue_result=FULL)
    assert payload["answer"] == FULL
    assert len(frames) == 1
    got = frames[0]
    assert got["kind"] == "queued_polled"
    assert (got["text_frames"], got["missing_chars"]) == (1, 0)
    assert got["extra_chars"] == len(FULL) - 17
    assert got["last_frame_covers_answer"] is False


def test_a_blank_question_is_an_empty_reading_not_a_pass(adapter):
    """零字节题：帧数 0，哨兵串是采集器补的不是线上来的 ⇒ 两枚数都照实记。"""
    row = fixture_row("doc-02")
    payload, _, sidecar, frames = drive(adapter, {"/api/v1/ask": NO_FRAME}, row)
    assert payload["answer"] == adapter.BLANK_SENTINEL and payload["evidence"] == []
    assert sidecar[0]["kind"] == "blank" and sidecar[0]["sentinel"] is True
    got = frames[0]
    assert (got["text_frames"], got["last_frame_chars"], got["missing_chars"]) == (0, 0, 0)
    assert got["extra_chars"] == len(adapter.BLANK_SENTINEL)
    assert got["last_frame_covers_answer"] is False
    assert got["criterion_two_holds"] is False


def test_hitl_frames_from_two_streams_fold_into_one_question(adapter):
    """挂起轮 + 批准轮：帧数与坏形按"这一题"合计，末帧取真正最后到达的那一条流。"""
    row = fixture_row("approval-05")
    script = {"/api/v1/ask": [("text", {"type": "text", "content": PARK_TEXT}),
                              ("hitl", {"type": "hitl", "pending": ["chart"]}),
                              ("done", {"type": "done"})],
              "/api/v1/approve": MULTI_FRAME}
    payload, opener, sidecar, frames = drive(adapter, script, row)
    assert opener.calls.count("/api/v1/approve") == 1
    assert payload["answer"] == FULL and sidecar[0]["kind"] == "approved_ok"
    got = frames[0]
    assert got["text_frames"] == 4 and got["streams"] == 2
    assert got["per_stream"] == [{"frames": 1, "breaks": 0, "first_break_at": 0},
                                 {"frames": 3, "breaks": 0, "first_break_at": 0}]
    assert (got["missing_chars"], got["extra_chars"]) == (0, 0)
    # 跨流不比对前缀：批准流从零起累计，拿它比挂起轮末帧会凭空长出坏形
    assert got["prefix_breaks"] == 0
    assert got["max_stream_frames"] == 3 and got["criterion_two_holds"] is True


def test_an_approval_failure_keeps_the_sentinel_and_reports_the_divergence(adapter):
    """批准失败：占位串口径一个字不许动，读数目击分叉（两枚数同时为正）。"""
    row = fixture_row("chart-01")
    script = {"/api/v1/ask": [("text", {"type": "text", "content": PARK_TEXT}),
                              ("hitl", {"type": "hitl", "pending": ["chart"]}),
                              ("done", {"type": "done"})],
              "/api/v1/approve": NO_FRAME}
    payload, _, sidecar, frames = drive(adapter, script, row)
    assert payload["answer"] == adapter.APPROVAL_FAILED_SENTINEL
    assert sidecar[0]["kind"] == "approval_failed" and sidecar[0]["sentinel"] is True
    got = frames[0]
    assert got["text_frames"] == 1 and got["last_frame_chars"] == len(PARK_TEXT)
    assert got["missing_chars"] == len(PARK_TEXT) and got["extra_chars"] > 0
    assert got["last_frame_covers_answer"] is False


def test_a_cache_hit_stops_the_window_before_anything_lands(adapter):
    """命中在真机轮里到不了落盘：``transport`` 当场 raise，两份证据件都不许出现。"""
    row = fixture_row("doc-03")
    with pytest.raises(RuntimeError, match="命中答案缓存"):
        drive(adapter, {"/api/v1/ask": CACHE_HIT}, row)
    assert not adapter.SIDECAR.exists()
    assert not adapter.frame_ledger_path().exists()


def test_first_token_at_still_marks_the_first_non_blank_frame(adapter, monkeypatch):
    """空帧也数，但 ``first_token_at`` 仍然认第一枚**有正文**的帧 —— 口径没被计数带着走。

    到达时刻用同一次消费记下来（另跑一趟假钟就会错格），spy 只抄不改。
    """
    stream = [("text", {"type": "text"}), ("text", {"type": "text", "content": FULL}),
              ("done", {"type": "done"})]
    seen = []
    real_iter_events = adapter.iter_events

    def spy(response):
        for item in real_iter_events(response):
            seen.append(item)
            yield item

    monkeypatch.setattr(adapter, "iter_events", spy)
    out = consume(adapter, stream)
    assert out["text_frames"] == 2 and out["prefix_breaks"] == 0  # "" 是任何串的前缀
    text_arrivals = [arrival for name, _, arrival in seen if name == "text"]
    assert len(text_arrivals) == 2
    assert out["first_token_at"] == text_arrivals[1]  # 第一枚是空帧，不记首字
    assert out["answer"] == FULL


# ===== 三、🔴 只观测：评分面与两份既有契约一个字没动 =====

def test_the_payload_and_sidecar_contracts_are_untouched(adapter):
    row = fixture_row("approval-05")
    script = {"/api/v1/ask": [("text", {"type": "text", "content": PARK_TEXT}),
                              ("hitl", {"type": "hitl", "pending": ["chart"]}),
                              ("done", {"type": "done"})],
              "/api/v1/approve": MULTI_FRAME}
    payload, _, sidecar, frames = drive(adapter, script, row)
    assert set(payload) == PAYLOAD_KEYS                    # 交回采集器的仍是那五键
    record = sidecar[0]
    assert tuple(list(record)[:9]) == SIDECAR_BASE_KEYS     # 九键的名字与顺序
    assert set(record) - set(SIDECAR_BASE_KEYS) <= (R123_EXTRA_KEYS | {"pre_answer"})
    assert record["answer_chars"] == len(FULL)
    assert record["tool_calls"] == 0                        # steps 没被帧计数污染
    got = frames[0]
    assert set(got) == JOIN_KEYS | FRAME_READING_KEYS
    assert got["id"] == record["id"] and got["kind"] == record["kind"]
    assert got["answer_chars"] == record["answer_chars"]     # 同一份终答，两把尺各记一次


def test_the_frame_ledger_path_is_resolved_at_write_time(adapter, tmp_path, monkeypatch):
    """落点必须现算：窗口事后重绑 ``SIDECAR`` 时，钉在 import 期就会把产物漏进仓内。"""
    monkeypatch.delenv("EVAL_FRAME_LEDGER", raising=False)
    assert adapter.frame_ledger_path() == tmp_path / "sidecar-run6-frames.jsonl"
    adapter.SIDECAR = tmp_path / "sub" / "sidecar-run7.jsonl"
    assert adapter.frame_ledger_path() == tmp_path / "sub" / "sidecar-run7-frames.jsonl"
    monkeypatch.setenv("EVAL_FRAME_LEDGER", str(tmp_path / "explicit-frames.jsonl"))
    assert adapter.frame_ledger_path() == tmp_path / "explicit-frames.jsonl"
    # 仓内零写入：默认跟 sidecar 走 ⇒ 永远落在 repo 之外
    assert REPO_ROOT not in adapter.frame_ledger_path().resolve().parents


def test_summary_names_the_frame_ledger(adapter):
    assert adapter.summary()["frame_ledger"] == str(adapter.frame_ledger_path())



# ===== 四、两把常驻反证（留在仓库里，不是手工一次）=====

def test_counter_evidence_a_ruler_that_stops_counting_turns_the_reading_red(adapter, monkeypatch):
    """反证①：把计数逻辑改回「不计数」⇒ 红。

    这里在进程内复刻那一次回退；真改文件的那把（``_count_text_frame`` 里去掉自增）红色回显与
    还原 sha 见交付说明。红要有名字：三帧与零帧读成同一格，判据② 从此再也读不出 ">1"。
    """
    green = readings(adapter, [MULTI_FRAME], FULL)
    assert green["text_frames"] == 3
    assert adapter._frame_verdict(green) is True

    def blind(out, frame):        # 「不计数」：只留末帧，帧数与坏形一律不记
        out["last_text_frame"] = frame

    monkeypatch.setattr(adapter, "_count_text_frame", blind)
    red = readings(adapter, [MULTI_FRAME], FULL)
    empty = readings(adapter, [NO_FRAME], FULL)
    assert red["text_frames"] == 0                         # 尺子瞎了
    assert red == empty                                    # 三帧与零帧同形 ⇒ 量具已不存在
    assert adapter._frame_verdict(red) is False            # ⇒ 判据② 红
    assert red != green                                    # 与真尺子的读数不再相同
    assert red["answer_sha"] == green["answer_sha"]        # 评分面没受影响：只有尺子变了


def test_counter_evidence_a_swallowed_prefix_break_turns_the_reading_red(adapter, monkeypatch):
    """反证②：把前缀缩短吞成静默（帧照数、坏形不报）⇒ 红。

    红在具名断言 ``prefix_breaks == 1`` 上：吞掉之后同一批字节读 0，而帧数仍然读 3 —— 说明丢的
    恰好是坏形这一格，不是整把尺子。
    """
    green = readings(adapter, [SHORTENED], FULL)
    assert (green["text_frames"], green["prefix_breaks"]) == (3, 1)
    assert green["last_frame_covers_answer"] is False

    def swallow(out, frame):     # 「吞成静默」：只数帧，前缀缩短不再报
        out["text_frames"] += 1
        out["last_text_frame"] = frame

    monkeypatch.setattr(adapter, "_count_text_frame", swallow)
    red = readings(adapter, [SHORTENED], FULL)
    assert red["prefix_breaks"] == 0                       # ⇒ 坏形读不出来了（红）
    assert red["text_frames"] == green["text_frames"]      # 帧数还在 ⇒ 丢的就是坏形那一格
    assert adapter._frame_verdict(red) is False            # 坏形不报 ⇒ 判据② 也永远读不出成立
    assert red != green


# ===== 五、🔴 run2..run5 形状逐题对齐：105 题重放的摘要必须与开工前相同 =====

#: 跟进单具名的那 18 枚挂起题（run3 起两把报告都是这批；看板 §4BH.11 复算照旧 18 枚）。
HITL18 = ("insight-07 chart-01 chart-02 chart-03 chart-04 approval-05 scope-02 scope-05 "
          "tool-01 tool-02 tool-04 report-02 report-05 report-07 report-09 report-10 "
          "report-11 report-12").split()
#: 开工前（``8e1136d``，没有尺子的版本）在同一批合成流上重放 105 题取到的摘要。
#: 取法：``git show 8e1136d:scripts/eval_transport_ask_v2.py`` 落到仓外，与改后版跑同一批
#: 输入、同一条假钟，两份产物逐题比（脚本与回显见交付说明）。
PRE_R181_ANSWERS_SHA = "f50024895fe64778a7cd9cee28a21c6d46bed77e4d045858d2e07bb26a97ac8e"
PRE_R181_SIDECAR_NINE_SHA = "4b58bb839f080c12cfb29b4567982ee97edadc9aed3480dd6864e4bc9c6facf2"


def _corpus(rows):
    """给 105 题各配一条确定性形状：18 枚挂起、5 枚零字节、3 枚 error、3 枚入队、
    10 枚单帧，其余三帧 cumulative。形状写在题号上，两侧跑的必须是同一批。"""
    ids = [str(row["id"]) for row in rows]
    gold = {str(row["id"]): str(row.get("answer", "")) for row in rows}

    def terminal(row_id):
        return "%s：%s（依口径登记表）" % (row_id, gold[row_id])

    def cumulative(text):
        low, high = len(text) // 3, 2 * len(text) // 3
        return [("text", {"type": "text", "content": text[:low]}),
                ("text", {"type": "text", "content": text[:high]}),
                ("text", {"type": "text", "content": text}),
                ("done", {"type": "done"})]

    scripts = {}
    for row_id in ids:
        text = terminal(row_id)
        if row_id in HITL18:
            scripts[row_id] = ({"/api/v1/ask": [("text", {"type": "text", "content": PARK_TEXT}),
                                                ("hitl", {"type": "hitl", "pending": ["chart"]}),
                                                ("done", {"type": "done"})],
                                "/api/v1/approve": cumulative(text)}, text)
        elif row_id in ids[3:8]:
            scripts[row_id] = ({"/api/v1/ask": NO_FRAME}, text)
        elif row_id in ids[11:14]:
            scripts[row_id] = ({"/api/v1/ask": [
                ("error", {"type": "error", "content": "本轮未产出任何结论，请重试。"}),
                ("done", {"type": "done"})]}, text)
        elif row_id in ids[21:24]:
            scripts[row_id] = ({"/api/v1/ask": [
                ("queued", {"type": "queued", "request_id": "req:" + row_id}),
                ("done", {"type": "done"})]}, text)
        elif row_id in set(ids[31:41]):
            scripts[row_id] = ({"/api/v1/ask": [
                ("text", {"type": "text", "content": text}), ("done", {"type": "done"})]}, text)
        else:
            scripts[row_id] = ({"/api/v1/ask": cumulative(text)}, text)
    return scripts


def _replay(module, tmp_path):
    """把 105 题喂给真 ``transport`` + 真采集器，产出两份可比的东西。"""
    import hashlib

    rows = [json.loads(line) for line in
            FIXTURE_105.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    assert len(rows) == 105
    scripts = _corpus(rows)
    opener = ScriptedOpener({}, "")
    module._OPENER = opener

    def transport(row):
        script, terminal_text = scripts[str(row["id"])]
        opener.script = script
        opener.queue_result = terminal_text
        return module.transport(row)

    answers, failures = COLLECTOR.collect_answers(
        rows, transport, answer_source="r181_replay", clock=_ticker())
    assert failures == [], "重放里不该有失败题：%s" % failures[:3]
    body = "".join(json.dumps(answer, ensure_ascii=False) + "\n" for answer in answers)
    (tmp_path / "answers-replay.jsonl").write_text(body, encoding="utf-8")
    sidecar = read_jsonl(module.SIDECAR)
    nine = [[row[key] for key in SIDECAR_BASE_KEYS] for row in sidecar]
    return (hashlib.sha256(body.encode("utf-8")).hexdigest(),
            hashlib.sha256(json.dumps(nine, ensure_ascii=False).encode("utf-8")).hexdigest(),
            len(answers), len(sidecar), read_jsonl(module.frame_ledger_path()))


def _ticker():
    state = {"t": 1000.0}

    def clock():
        state["t"] += 1.0
        return state["t"]
    return clock


def test_the_105_question_replay_still_hashes_to_the_pre_r181_digests(adapter, tmp_path):
    """判据② 的红线：装了尺子之后，105 题的 answers 与 sidecar 九键必须逐题等于开工前那份。"""
    answers_sha, sidecar_sha, collected, sidecar_rows, frames = _replay(adapter, tmp_path)
    assert collected == 105 and sidecar_rows == 105
    assert answers_sha == PRE_R181_ANSWERS_SHA
    assert sidecar_sha == PRE_R181_SIDECAR_NINE_SHA
    # 同一批输入上尺子有读数：105 行逐题落盘、零坏形、11 行有缺/多字（5 零字节 + 3 error + 3 入队）
    assert len(frames) == 105
    assert sum(1 for row in frames if row["prefix_breaks"]) == 0
    assert sum(1 for row in frames if row["extra_chars"]) == 11
    assert sum(1 for row in frames if row["criterion_two_holds"]) == 84   # 判据② 成立的题数
    assert sum(1 for row in frames if row["max_stream_frames"] == 1) == 10  # 整段一帧的题
    assert sum(1 for row in frames if row["streams"] == 2) == 18           # 走了批准轮的 18 枚


def test_the_replay_produces_no_bytes_inside_the_repo(adapter, tmp_path):
    """窗口重放全程仓内零写入（两份产物都跟着 tmp_path 的 sidecar 走）。"""
    _replay(adapter, tmp_path)
    stray = [path for path in REPO_ROOT.glob("scripts/*frames*.jsonl")]
    assert stray == []
