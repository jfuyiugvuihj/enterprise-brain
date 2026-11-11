# -*- coding: utf-8 -*-
"""R520 判据 ①②③ —— EVAL_DECLARE_LANE_TIER 从**环境**走到**载荷**的那条读取腿。

## 现场（本单一手现取，树 be-r520 @ 97724c5）

派工词说「在册零钉」。现读要拆成两句话讲，因为它们是两枚不同的东西：

- **环境变量名**在 tests/ 里零命中（rg -l EVAL_DECLARE_LANE_TIER tests 实取为空）
  ⇒ 量具 scripts/eval_transport_ask_v2.py:220 那一行
  DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "").strip() 的**读取腿**
  从没被任何钉盖过。本件补的就是这一枚：每一条判断都从 os.environ 起跳。
- **模块常量**不是零钉：tests/test_r222_queue_terminal_stopwatch.py 里那枚
  test_r226_lane_declaration_still_travels_only_the_declared_tier 走的是
  monkeypatch.setattr(adapter, "DECLARE_LANE_TIER", ...) —— 它绕开读取腿直接改属性。
  后果是硬的：把 :220 整行换成 DECLARE_LANE_TIER = ""（＝环境那一路彻底摘掉），那枚在册钉
  **照旧绿**，因为它设的属性还在原地。这一枚由 tests/test_r520_counter_evidence_teeth.py
  的 K1 一手量到（连「在册那枚对它全盲」一起量），本件不复述数字。

所以本件与那枚在册钉不是重复，而是强度只升：本件从头到尾一枚 setattr 都不许用。

## 全程离线

_open 换成只记账的假出口：零服务 / 零模型 / 零容器 / 零连库 / 零真跑分，sidecar 与帧账
两份产物都写 tmp_path，仓内零字节。🔴 帧账那一份是**调用期**读表的（frame_ledger_path()，
量具 :235-245 自己记过「两个变量都不设时两份都落进 scripts/」这只脚枪），所以整场判断必须
在 _environment 那一格里跑完 —— ruler() 就是这个格子，出窗即不算跑过。
"""
from __future__ import annotations

import contextlib
import importlib.util
import itertools
import json
import os
import re
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"

#: 本单那一枚开关的名字。它既是被钉的对象（见第一条用例），也是本件设环境的键。
ENV_KEY = "EVAL_DECLARE_LANE_TIER"
REPORT_TIER = "报告"
ANALYSIS_TIER = "分析"
QA_TIER = "问答"
#: 相 2 要的那一枚 lane 字面。这里故意独立抄一份字面：它与产品常量的同源关系由
#: tests/test_r520_report_lane_contract.py 钉住，两边谁漂了都红。
REPORT_LANE = "report"
BODY = "据统计，Q3 营收 1200 万元，环比增长 8%。"
TOKEN_VALUE = "r520-bearer-token"
#: 不设键时载荷该有的样子：一个字节都不许多（run6 / run7 相 1 的口径不受影响）。
BASE_PAYLOAD_KEYS = {"message", "session_id", "idempotency_key"}

_NO_ENV = object()
_TAG = itertools.count()


class FakeResponse:
    """一发假出口：JSON 体走 read()，SSE 流走 __iter__()。"""

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
    """服务端每事件三行：event / data / 空行。"""
    lines = []
    for name, data in events:
        lines.append(("event: " + name + "\n").encode("utf-8"))
        lines.append(("data: " + json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        lines.append(b"\n")
    return lines


class AskEgress:
    """假出口，签名与真的 _open(path, payload, method) 逐位相同。

    只认两发：/api/v1/login（本件把 _TOKEN 预先坐实，正常一次都不该来）与 /api/v1/ask
    （交回一条同步道的正文流：一帧 text 加一帧 done）。别的出口一律当场红 —— 一旦有 lane
    发出去，本件读的就是「有没有第二道出口把这一题改走了」这类假象，不许有。
    """

    def __init__(self):
        self.paths = []
        self.payloads = []

    def __call__(self, path, payload=None, method="POST"):
        self.paths.append(path)
        self.payloads.append(payload)
        if path == "/api/v1/login":
            return FakeResponse(json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        if path == "/api/v1/ask":
            return FakeResponse(lines=sse([("text", {"type": "text", "content": BODY}),
                                           ("done", {"type": "done"})]))
        raise AssertionError("本单不该打这一发：" + str(path))

    @property
    def asked(self):
        return [body for path, body in zip(self.paths, self.payloads) if path == "/api/v1/ask"]


@contextlib.contextmanager
def _environment(value):
    """只替本单那一枚键改盘面，其余环境原样继承；两份产物的落点键一律摘掉。"""
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in (ENV_KEY, "EVAL_SIDECAR", "EVAL_FRAME_LEDGER"):
            os.environ.pop(key, None)
        if value is not _NO_ENV:
            os.environ[ENV_KEY] = value
        yield


def _import_ruler(source_path, name):
    spec = importlib.util.spec_from_file_location(name, str(source_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def ruler(tmp_path, *, env=_NO_ENV, source_path=SCRIPT_PATH, tag="run"):
    """交回一枚装配好的采集器：环境按 env 设定，两份产物写 tmp_path，全程不碰网络。

    env 传 _NO_ENV ＝ 这一枚键根本不在盘上（判据① 的那一格）；传 "" ＝ 在盘上但是空串。
    🔴 整个 with 期间环境格子都开着：帧账落点是调用期读表的（见本件抬头），出窗跑题就漏。
    """
    stamp = tag + "-" + str(next(_TAG))
    with _environment(env):
        module = _import_ruler(source_path, "r520_ruler_" + stamp)
        module.BASE_URL = "http://r520.test"
        module.SIDECAR = tmp_path / ("sidecar-" + stamp + ".jsonl")
        module.MIN_GAP_SECONDS = 0.0
        module.ATTEMPTS = 1
        module.RETRY_SLEEP = 0.0
        module.MAX_BLANKS = 200
        module.APPROVAL_ROUNDS = 3
        module._TOKEN = TOKEN_VALUE
        module._BLANKS = 0
        module._APPROVAL_FAILURES = 0
        module._LAST_CALL = 0.0
        yield module


def payloads_sent(module, rows):
    """逐题走一遍 transport，按题号交回采集器真的写进 /ask 载荷的那一份字。"""
    egress = AskEgress()
    module._open = egress
    seen = {}
    for row in rows:
        before = len(egress.asked)
        module.transport(dict(row))
        assert len(egress.asked) == before + 1, str(row.get("id")) + "：这一题没走 /ask ⇒ 读的是假账"
        key = str(row.get("id", ""))
        assert key not in seen, "题号重复，本件的读数会互相盖掉：" + key
        seen[key] = dict(egress.asked[-1])
    return seen


def lanes_sent(module, rows):
    """{题号: 那一发 ask 载荷里的 lane}；None ＝ 载荷里根本没有 lane 这个键。

    钉的是**发没发**，不是「发了一枚空串」：_stream_once 只在 if lane: 时才写这一格，
    所以「键缺席」与「键为空串」是两件事，本件把它们分得很清（载荷里出现空形即红）。
    """
    lanes = {}
    for row_id, payload in payloads_sent(module, rows).items():
        if "lane" not in payload:
            lanes[row_id] = None
            continue
        value = payload["lane"]
        assert isinstance(value, str) and value, row_id + "：载荷里的 lane 是空形 ⇒ 等于没发"
        lanes[row_id] = value
    return lanes


def lane_via_attribute(module, tier):
    """在册 r226 那枚钉的走法：不碰环境，直接把常量 setattr 上去再发一题。

    本件只用它量一件事 —— 那条路对「读取腿被摘掉」全盲（见 teeth 件 K1）。它不是判据。
    """
    module.DECLARE_LANE_TIER = tier
    lanes = lanes_sent(module, [{"id": "attr-01", "question": "Q", "tier": REPORT_TIER}])
    return lanes["attr-01"]


def fixture_rows():
    """105 题名册（形状本身由判据④ 那枚 contract 件钉，这里只取来当输入）。"""
    rows = []
    for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def rows_with_tier(tier):
    return [row for row in fixture_rows() if row.get("tier") == tier]


def expected_lane(row_tier, declared, table):
    """本件对采集器那句判据的独立复写：只有「题的档位 == 声明的档位」才发，发的就是表里那一枚。

    刻意不复用模块里的表达式 —— 复写一遍才有牙：规则被改宽、被改窄、读取腿被摘掉，这里都对不上。
    """
    if declared and row_tier == declared:
        return table.get(row_tier) or None
    return None


# ==================== 读取腿本体 ====================

def test_the_ruler_reads_the_very_env_key_this_order_names():
    """本件设的键必须就是量具读的那一枚：不然下面全是自说自话。"""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    hits = re.findall(r'DECLARE_LANE_TIER\s*=\s*os\.getenv\(\s*"([^"]+)"', source)
    assert hits == [ENV_KEY], "采集器读的环境键不是本件设的那一枚，实取 " + repr(hits)


def test_an_unset_key_leaves_the_report_tier_on_the_sync_path(tmp_path):
    """判据①：盘上没这枚键 ⇒ 报告档一题都不发 lane，载荷仍是那三键。"""
    rows = rows_with_tier(REPORT_TIER)
    assert rows, "夹具里没有报告档 ⇒ 本枚判据① 会空转"
    with ruler(tmp_path, tag="unset") as module:
        assert module.DECLARE_LANE_TIER == "", "不设键却读出了东西 ⇒ 默认值那一半不成立"
        payloads = payloads_sent(module, rows)
    assert {rid: payload.get("lane") for rid, payload in payloads.items()} == \
        {rid: None for rid in payloads}
    key_shapes = {tuple(sorted(payload)) for payload in payloads.values()}
    assert key_shapes == {tuple(sorted(BASE_PAYLOAD_KEYS))}, \
        "不设键的载荷多出了字节：" + repr(key_shapes)


def test_an_empty_value_is_the_same_as_not_setting_it(tmp_path):
    """判据① 的第二格：键在盘上但是空串 ⇒ 同样一题不发（默认口径不受影响）。"""
    with ruler(tmp_path, env="", tag="empty") as module:
        assert module.DECLARE_LANE_TIER == ""
        lanes = lanes_sent(module, rows_with_tier(REPORT_TIER))
    assert set(lanes.values()) == {None}, repr(lanes)


def test_declaring_the_report_tier_sends_a_lane_for_every_report_question(tmp_path):
    """判据②：设成「报告」⇒ 报告档每一题都发，发的就是 report 那一枚字。"""
    rows = rows_with_tier(REPORT_TIER)
    with ruler(tmp_path, env=REPORT_TIER, tag="report") as module:
        assert module.DECLARE_LANE_TIER == REPORT_TIER, "读取腿没把环境落成常量"
        table = dict(module.LANE_BY_TIER)
        lanes = lanes_sent(module, rows)
    assert set(lanes) == {str(row["id"]) for row in rows}
    assert set(lanes.values()) == {REPORT_LANE}, repr(lanes)
    want = {rid: expected_lane(REPORT_TIER, REPORT_TIER, table) for rid in lanes}
    assert lanes == want, "与独立复写对不上：" + repr(lanes)


def test_declaring_a_tier_sends_lanes_for_exactly_that_tier_across_the_corpus(tmp_path):
    """判据② 与 ③ 的合尺：全库 105 题走一遍，发 lane 的那一撮逐枚等于「档位 == 声明值」。

    三档各跑一轮（报告 / 分析 / 问答）⇒ 「把档位名写死在代码里」这种改法在这枚上必红。
    """
    rows = fixture_rows()
    tier_of = {str(row["id"]): str(row.get("tier", "")) for row in rows}
    for declared in (REPORT_TIER, ANALYSIS_TIER, QA_TIER):
        with ruler(tmp_path, env=declared, tag="corpus") as module:
            table = dict(module.LANE_BY_TIER)
            lanes = lanes_sent(module, rows)
        want = {rid: expected_lane(tier_of[rid], declared, table) for rid in lanes}
        assert lanes == want, declared + " 那一轮对不上：" + repr(
            {rid: (tier_of[rid], lanes[rid], want[rid]) for rid in lanes if lanes[rid] != want[rid]})
        sent = {rid for rid, value in lanes.items() if value}
        assert sent == {rid for rid, tier in tier_of.items() if tier == declared}, \
            declared + "：发 lane 的名册不对"


def test_a_value_that_matches_no_tier_sends_nothing(tmp_path):
    """判据③：设一枚名册里没有的档位名 ⇒ 一题都不发（不是「发出去让服务端拒」）。"""
    with ruler(tmp_path, env="报表", tag="unknown") as module:
        lanes = lanes_sent(module, fixture_rows())
    assert set(lanes.values()) == {None}, repr({k: v for k, v in lanes.items() if v})


def test_a_declared_value_that_only_contains_a_tier_name_is_not_a_match(tmp_path):
    """判据③ 加严：报告 是 分析报告 的子串，但那不是同一个档位名。

    这枚专防「把 == 换成 in」：换宽之后报告档会成批入队，而 == 那一版一题都不发。
    """
    rows = rows_with_tier(REPORT_TIER)
    assert rows
    with ruler(tmp_path, env="分析报告", tag="substring") as module:
        lanes = lanes_sent(module, rows)
    assert set(lanes.values()) == {None}, "子串也算配上了 ⇒ 值比较被改宽：" + repr(lanes)


def test_the_env_value_is_stripped_before_it_is_compared(tmp_path):
    """读取腿上那枚 .strip() 是有牙的：.env 里多一个尾空格也算声明了「报告」。

    真机开窗就是把这一枚键写进 deploy/.env.server 那一类文件 ⇒ 手抖多一枚空格，
    相 2 悄悄没开、整轮跑分白做。这一枚防的就是它。
    """
    with ruler(tmp_path, env="  报告  ", tag="strip-env") as module:
        assert module.DECLARE_LANE_TIER == REPORT_TIER, "环境值没被 strip ⇒ 常量还带着空格"
        lanes = lanes_sent(module, rows_with_tier(REPORT_TIER))
    assert set(lanes.values()) == {REPORT_LANE}, repr(lanes)


def test_the_row_tier_is_stripped_before_it_is_compared(tmp_path):
    """题面档位带空格（夹具或派生表手抖）也必须算报告档。"""
    rows = [{"id": "sp-01", "question": "Q1", "tier": " 报告"},
            {"id": "sp-02", "question": "Q2", "tier": "报告 "},
            {"id": "sp-03", "question": "Q3", "tier": "\t报告\t"}]
    with ruler(tmp_path, env=REPORT_TIER, tag="strip-row") as module:
        lanes = lanes_sent(module, rows)
    assert set(lanes.values()) == {REPORT_LANE}, repr(lanes)


def test_a_row_without_a_tier_never_gets_a_lane(tmp_path):
    """没有 tier 这一格、或它是空串 / 非串 / 近亲名 ⇒ 一题都不发（缺省仍走原来的同步道）。"""
    rows = [{"id": "notier-01", "question": "Q1"},
            {"id": "notier-02", "question": "Q2", "tier": ""},
            {"id": "notier-03", "question": "Q3", "tier": None},
            {"id": "notier-04", "question": "Q4", "tier": "报告生成"}]
    with ruler(tmp_path, env=REPORT_TIER, tag="notier") as module:
        lanes = lanes_sent(module, rows)
    assert set(lanes.values()) == {None}, repr(lanes)


def _without_a_random_key(payload):
    """把两枚 uuid4 随机键（与 lane）摘掉，剩下的才是两轮可比的那一份字。"""
    random_keys = ("session_id", "idempotency_key", "lane")
    return {k: v for k, v in payload.items() if k not in random_keys}


def test_declaring_a_lane_costs_exactly_one_key_and_nothing_else(tmp_path):
    """反向钉（防本件把「多发一格」当成免费）：声明档位只许多出 lane 这一格，别的一律不动。

    两轮之间 uuid4 随机键必然不同 —— 每题一枚新会话、一枚新幂等键，那正是量具的口径，
    所以这里不许拿「逐键全等」当判据（那是永假），要比的是题面文本，随机键单独钉形状与互不相同。
    """
    rows = rows_with_tier(REPORT_TIER)[:3]
    with ruler(tmp_path, tag="keys-unset") as module:
        plain = payloads_sent(module, rows)
    with ruler(tmp_path, env=REPORT_TIER, tag="keys-set") as module:
        declared = payloads_sent(module, rows)
    ids = {str(row["id"]) for row in rows}
    assert set(plain) == set(declared) == ids
    for row_id in ids:
        assert set(plain[row_id]) == BASE_PAYLOAD_KEYS
        assert set(declared[row_id]) == BASE_PAYLOAD_KEYS | {"lane"}
        assert _without_a_random_key(plain[row_id]) == _without_a_random_key(declared[row_id]) \
            == {"message": plain[row_id]["message"]}, row_id + "：补 lane 的同时动了别的字节"
        assert declared[row_id]["lane"] == REPORT_LANE
        for key in ("session_id", "idempotency_key"):
            assert re.fullmatch(r"[0-9a-f]{32}", plain[row_id][key]), (row_id, key, plain[row_id][key])
            assert re.fullmatch(r"[0-9a-f]{32}", declared[row_id][key]), (row_id, key)
            assert declared[row_id][key] != plain[row_id][key], row_id + "：" + key + " 两轮撞值"
    sessions = [payload["session_id"] for payload in declared.values()]
    assert len(set(sessions)) == len(ids), "补 lane 之后会话键开始复用 ⇒ 题与题不再是各自一轮"
