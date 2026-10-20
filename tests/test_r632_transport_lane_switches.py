# -*- coding: utf-8 -*-
r"""R632 缺陷三的量具半张 —— 两枚新开关各有牙，而旧口径逐字节不变。

## 为什么这两枚开关必须有反证钉（不是照抄 R520 的格式，是同一件事又缺一块）

账上写「A(2) 的档位名派生 0/105，等 R524 进镜像」。本席现取推翻了那个前提：
`git merge-base --is-ancestor 05bec06 a2bbf13` rc=0（R524 早就在新镜像里），
`git log a2bbf13..HEAD -- app/` 只有一枚 app 改动（f5d75a7＝R616）。所以 0/105 不是产品没码：

- **服务端早就把档位名交出来了**：app/api/v1/chat.py 的 `_lane_readout_headers` 发三枚头
  `x-effective-lane` / `x-declared-lane` / `x-lane-source`，在册钉 tests/test_r141_lane_behavior.py
  与 tests/test_r172_lane_across_hitl.py 一枚枚对着。本席不碰容器也能复核它是产品常量而非手打：
  见下面 `test_the_header_words_and_switch_vocabulary_match_the_product`。
- **量具从来没读过头**：`scripts/eval_transport_ask_v2.py` 全文对 `headers` 零命中（本件钉住
  「现在有了读头那一格，而且它只在开关开着时才落盘」）。侧车与帧账里也没有任何档位名 ——
  10-04 现取 `rg -c lane run20k-sidecar.jsonl / run20k-sidecar-frames.jsonl / run21b-*` 全零命中。
- **声明腿只补一档**：EVAL_DECLARE_LANE_TIER 只替与其同名的那一档补 lane，其余两档一题都不补。

⇒ 「0/105」是量具三面缺码（读头腿没落／声明腿只补一档／契约点名的读数件从来没落），
不是产品那一侧不落 `[R42] lane=`，也不是「等 R524」。定性全文见 docs/testing/r632-instrument-lane-readout.md。

## 三条判据（本件只做离线假出口，零服务／零模型／零容器／零连库）

① 两枚开关都**没设**时：载荷逐字节与旧口径相同（一题都不带 lane），侧车与帧账键集一字不多，
   而且**第三份件一个都不落**（默认口径不受影响 = 盘面上不许多出任何东西）。
② 只开旧那枚（EVAL_DECLARE_LANE_TIER=报告）时：与 R520 钉的行为逐字相同；新那枚再叠加也不许
   改变已经补上了 lane 的那些题（旧口径优先，两枚同设不互相覆盖）。
③ 开新腿时：每一行按**自己的档位**补 lane；读头那一条腿把服务端说的档位名逐题记进第三份件，
   读不到就记「读不到」（假出口没头 ⇒ headers_readable=False 且档位为空），不折算成空档。

反证四把（每把先正控、原件前后各核一次 sha256，全部只在临时根副本上动刀）：
K1 无视 per-tier 开关（`if DECLARE_LANE_PER_TIER and not lane:` 摘成 `if not lane:`）⇒ 判据① 必红；
K2 无视记账开关（`if RECORD_LANE_READOUT:` 摘成 `if True:`）⇒ 「默认不落盘」必红；
K3 读表腿恒真（`_lane_switch` 整个 return 换成 True）⇒ 判据①②③ 全红（本件取① 那一格点名）；
K4 头名漂走（EFFECTIVE_LANE_HEADER 加一枚尾字）⇒ 与产品同源那一枚钉必红。
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import itertools
import json
import os
import re
from unittest import mock

import pytest

from test_r520_declare_lane_env_leg import (  # noqa: F401  共用同一套离线假出口与题册
    ANALYSIS_TIER,
    BASE_PAYLOAD_KEYS,
    BODY,
    QA_TIER,
    REPORT_LANE,
    REPORT_TIER,
    SCRIPT_PATH,
    TOKEN_VALUE,
    FakeResponse,
    fixture_rows,
    sse,
)

REPO_ROOT = SCRIPT_PATH.parents[1]
CHAT_PATH = REPO_ROOT / "app" / "api" / "v1" / "chat.py"

PER_TIER_ENV = "EVAL_DECLARE_LANE_PER_TIER"
RECORD_ENV = "EVAL_RECORD_LANE_READOUT"
LEDGER_PATH_ENV = "EVAL_LANE_LEDGER"
#: 采集器里存放这三枚**键名**的模块常量名（AST 现读用，不靠猜变量名）。
LANE_PER_TIER_CONSTANT = "LANE_PER_TIER_ENV"
LANE_RECORD_CONSTANT = "LANE_RECORD_ENV"
LANE_LEDGER_CONSTANT = "LANE_LEDGER_ENV"
#: 旧那一枚与本单两枚是同一条读取腿上的兄弟：任何一枚漏设，盘面就不是本席判的那张。
ALL_LANE_ENV_KEYS = ("EVAL_DECLARE_LANE_TIER", PER_TIER_ENV, RECORD_ENV, LEDGER_PATH_ENV,
                     "EVAL_SIDECAR", "EVAL_FRAME_LEDGER")

_TAG = itertools.count()


class CaseInsensitiveHeaders:
    """够用的响应头：`http.client.HTTPMessage.get` 就是大小写不敏感，这里照做。"""

    def __init__(self, mapping=None):
        self._values = {str(key).lower(): value for key, value in (mapping or {}).items()}

    def get(self, key, default=None):
        return self._values.get(str(key).lower(), default)


class HeaderResponse(FakeResponse):
    """带头的假出口：与在册那枚 FakeResponse 同规格，只多 `headers` 这一格。"""

    def __init__(self, headers=None, body=b"{}", lines=()):
        FakeResponse.__init__(self, body=body, lines=lines)
        self.headers = CaseInsensitiveHeaders(headers)


class HeaderEgress:
    """假出口，只认 /login 与 /ask；/ask 交回一条带头的流。

    `effective_by_question` 就是「服务端对这一题说出的生效档」：本席喂进去什么就期望账上
    落什么，喂不出来（键不在表里）那一发模拟的是**服务端没给档位读数** —— 产品那一侧的
    纪律是「读数缺格就少发一枚头，不发空值」，所以这里一个头都不发。
    """

    def __init__(self, effective_by_question=None):
        self.paths = []
        self.payloads = []
        self.effective_by_question = dict(effective_by_question or {})

    def __call__(self, path, payload=None, method="POST"):
        self.paths.append(path)
        self.payloads.append(payload)
        if path == "/api/v1/login":
            return FakeResponse(json.dumps({"token": TOKEN_VALUE}).encode("utf-8"))
        if path == "/api/v1/ask":
            payload = payload or {}
            message = str(payload.get("message") or "")
            sent = payload.get("lane") or ""
            headers = {}
            effective = self.effective_by_question.get(message)
            if effective:
                headers["x-effective-lane"] = effective
                headers["x-lane-source"] = "explicit" if sent else "r42_question"
                if sent:
                    headers["x-declared-lane"] = sent
            return HeaderResponse(headers=headers,
                                  lines=sse([("text", {"type": "text", "content": BODY}),
                                             ("done", {"type": "done"})]))
        raise AssertionError("R632 本不该打这一发：" + str(path))

    @property
    def asked(self):
        return [body for path, body in zip(self.paths, self.payloads) if path == "/api/v1/ask"]


@contextlib.contextmanager
def stage(tmp_path, env=None, source_path=SCRIPT_PATH, tag="r632", headerless_ever=False):
    """把采集器按指定环境与指定源码装进一个格子：两份既有产物与第三份件全落 tmp_path。"""
    stamp = tag + "-" + str(next(_TAG))
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in ALL_LANE_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in (env or {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        spec = importlib.util.spec_from_file_location("r632_ruler_" + stamp, str(source_path))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.BASE_URL = "http://r632.test"
        module.SIDECAR = tmp_path / ("sidecar-" + stamp + ".jsonl")
        module.MIN_GAP_SECONDS = 0.0
        module.ATTEMPTS = 1
        module.RETRY_SLEEP = 0.0
        module.MAX_BLANKS = 200
        module.APPROVAL_ROUNDS = 3
        module._TOKEN = TOKEN_VALUE
        module._BLANKS = 0
        module._APPROVAL_FAILURES = 0
        module._QUEUED_APPROVED = 0
        module._PARKED = 0
        module._LAST_CALL = 0.0
        yield module


def drive(module, rows, egress):
    """逐题走 transport，交回 {题号: 真写进 /ask 的那一份载荷}（钉的是发出去的字，不是肚子里的常量）。"""
    module._open = egress
    seen = {}
    for row in rows:
        before = len(egress.asked)
        module.transport(dict(row))
        assert len(egress.asked) == before + 1, str(row.get("id")) + "：这一题没走 /ask ⇒ 读的是假账"
        key = str(row.get("id", ""))
        assert key not in seen, "题号重复，读数会互相盖掉：" + key
        seen[key] = dict(egress.asked[-1])
    return seen


def read_jsonl(path):
    if not os.path.exists(str(path)):
        return []
    with open(str(path), encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def corpus_sample():
    """每一档取一题 + 一枚根本没有 tier 这一格的题（旧口径与本单开关在缺档那一行也必须同形）。"""
    rows = fixture_rows()
    picked = []
    for tier in (QA_TIER, ANALYSIS_TIER, REPORT_TIER):
        picked.append(next(row for row in rows if row.get("tier") == tier))
    picked.append({"id": "r632-no-tier", "question": "R632 造的一题，夹具里没有这个档位", "tier": ""})
    return picked


def expected_per_tier_lane(module, row):
    """独立复写「按每一行自己的档位补」那句判据：不复用模块里的表达式，复写了才有牙。"""
    table = dict(module.LANE_BY_TIER)
    tier = str(row.get("tier") or "").strip()
    return table.get(tier) or None


def lane_cells(payloads):
    return {row_id: payload.get("lane") for row_id, payload in payloads.items()}


def ledger_files(tmp_path):
    return sorted(path.name for path in tmp_path.glob("*-lane.jsonl"))


# ==================== 判据①：两枚开关都不设 ⇒ 盘面一字不多 ====================

def test_both_new_switches_unset_reads_the_default_off_shape(tmp_path):
    """读表腿本体：不设键 ⇒ 两枚常量都是 False（与 R520 对旧那一枚同一格纪律：从环境起跳）。"""
    with stage(tmp_path, tag="defaults") as module:
        assert module.DECLARE_LANE_PER_TIER is False
        assert module.RECORD_LANE_READOUT is False
        assert module._lane_switch(PER_TIER_ENV) is False
        assert module._lane_switch(RECORD_ENV) is False


@pytest.mark.parametrize("value", ["on", "ON", "  on  ", "1", "true", "yes"])
def test_the_switch_read_leg_accepts_the_product_vocabulary_from_the_environment(tmp_path, value):
    """每一枚字面都从 os.environ 起跳读成 True：口径不是本席自造的一套。"""
    with stage(tmp_path, env={PER_TIER_ENV: value, RECORD_ENV: value},
               tag="vocab-" + str(abs(hash(value)))) as module:
        assert module.DECLARE_LANE_PER_TIER is True, repr(value)
        assert module.RECORD_LANE_READOUT is True, repr(value)
        assert module._lane_switch(PER_TIER_ENV) is True, repr(value)


@pytest.mark.parametrize("value", ["", "  ", "off", "0", "报告", "yesss"])
def test_anything_outside_the_vocabulary_keeps_the_old_shape(tmp_path, value):
    with stage(tmp_path, env={PER_TIER_ENV: value, RECORD_ENV: value},
               tag="neg-" + str(abs(hash(value)))) as module:
        assert module._lane_switch(PER_TIER_ENV) is False, repr(value)
        assert module._lane_switch(RECORD_ENV) is False, repr(value)
        assert module.DECLARE_LANE_PER_TIER is False, repr(value)
        assert module.RECORD_LANE_READOUT is False, repr(value)


def test_off_by_default_payloads_are_the_three_keys_and_no_lane_file(tmp_path):
    """判据① 的盘面那一半：载荷只有那三键，侧车/帧账一字不多，第三份件一个都不落。"""
    rows = corpus_sample()
    with stage(tmp_path, tag="off") as module:
        payloads = drive(module, rows, HeaderEgress({row["question"]: "qa" for row in rows}))
        assert lane_cells(payloads) == {str(row["id"]): None for row in rows}, "开关没设却发了 lane"
        assert {tuple(sorted(payload)) for payload in payloads.values()} == \
            {tuple(sorted(BASE_PAYLOAD_KEYS))}, "不设开关的载荷多出了字节"
        assert ledger_files(tmp_path) == [], "默认态落出了第三份件"
        sidecar_keys = set().union(*[set(row) for row in read_jsonl(module.SIDECAR)])
        frames_keys = set().union(*[set(row) for row in
                                    read_jsonl(module.frame_ledger_path())])
        assert not (sidecar_keys & {"lane", "effective_lane", "sent_lane", "lane_source"}), \
            "侧车里长出了档位名那一格（那本件的键集被在册闸钉成对判）"
        assert not (frames_keys & {"lane", "effective_lane", "sent_lane", "lane_source"}), \
            "帧账里长出了档位名那一格"


# ==================== 判据③：per-tier 逐行补 lane ====================

def test_per_tier_declaration_fills_every_row_with_its_own_tier(tmp_path):
    """开关设 on ⇒ 三档逐行各补各的；缺档那一行照旧一枚都不补（不发空串冒充档位）。"""
    rows = corpus_sample()
    with stage(tmp_path, env={PER_TIER_ENV: "on"}, tag="per-tier") as module:
        payloads = drive(module, rows, HeaderEgress())
    want = {str(row["id"]): expected_per_tier_lane(module, row) for row in rows}
    assert lane_cells(payloads) == want, "逐行补 lane 与独立复写对不上"
    assert lane_cells(payloads)["r632-no-tier"] is None, "缺档那一行被补了东西 ⇒ 发了枚猜出来的档"
    assert ledger_files(tmp_path) == [], "只开载荷腿不该落第三份件"


def test_the_full_corpus_declares_its_own_tier_for_every_one_of_the_105_rows(tmp_path):
    """整册 105 题：每一题都发得出自己那一档（这才是「下一窗逐题档位名」的载荷前提）。"""
    rows = fixture_rows()
    assert len(rows) == 105, "实取 " + str(len(rows))
    with stage(tmp_path, env={PER_TIER_ENV: "on"}, tag="corpus") as module:
        payloads = drive(module, rows, HeaderEgress())
    table = dict(module.LANE_BY_TIER)
    missing = [str(row["id"]) for row in rows
               if payloads[str(row["id"])].get("lane") != table.get(str(row["tier"]).strip())]
    assert missing == [], "这些题没按自己的档位补上 lane：" + repr(missing[:12])
    assert {payloads[str(row["id"])]["lane"] for row in rows} == set(table.values()), \
        "三档没一起发出来 ⇒ 又是一窗只读得到一档"


# ==================== 判据②：旧那枚不受影响，两枚同设旧口径优先 ====================

def test_old_single_tier_shape_is_byte_identical_with_the_new_switch_off(tmp_path):
    """设 EVAL_DECLARE_LANE_TIER=报告、新那枚不设 ⇒ 与 R520 钉的行为逐字相同。"""
    rows = [row for row in fixture_rows() if row.get("tier") == REPORT_TIER][:4]
    others = [row for row in fixture_rows() if row.get("tier") == QA_TIER][:4]
    with stage(tmp_path, env={"EVAL_DECLARE_LANE_TIER": REPORT_TIER}, tag="old-only") as module:
        report_cells = lane_cells(drive(module, rows, HeaderEgress()))
        qa_cells = lane_cells(drive(module, others, HeaderEgress()))
    assert set(report_cells.values()) == {REPORT_LANE}, report_cells
    assert set(qa_cells.values()) == {None}, "旧口径被本单改宽了：问答档也跟着发 lane 了"


def test_declaring_per_tier_never_overrides_what_the_old_switch_already_declared(tmp_path):
    """两枚同设：旧那枚补上的题一字不变，新那枚只补旧那枚没补到的题（谁也不许改写谁）。"""
    rows = fixture_rows()
    with stage(tmp_path, env={"EVAL_DECLARE_LANE_TIER": REPORT_TIER}, tag="tier-only") as module:
        old = lane_cells(drive(module, rows, HeaderEgress()))
    with stage(tmp_path, env={"EVAL_DECLARE_LANE_TIER": REPORT_TIER, PER_TIER_ENV: "on"},
               tag="both") as module:
        both = lane_cells(drive(module, rows, HeaderEgress()))
    changed = [row_id for row_id, lane in old.items()
               if lane is not None and both.get(row_id) != lane]
    assert changed == [], "旧口径已经发了 lane 的题被改写：" + repr(changed[:12])
    gained = [row_id for row_id, lane in both.items() if lane is not None and old.get(row_id) is None]
    assert set(gained) == {str(row["id"]) for row in rows if str(row["tier"]).strip() != REPORT_TIER}, \
        "新那枚补的题集不是「旧那枚没补到的那些」"


def test_the_new_leg_costs_exactly_one_key_and_nothing_else(tmp_path):
    """逐 row 对判两态载荷：摘掉随机两键与 lane 之后必须一字不差（票据要求的那份 diff）。"""
    rows = fixture_rows()
    with stage(tmp_path, tag="diff-off") as module:
        off = drive(module, rows, HeaderEgress())
    with stage(tmp_path, env={PER_TIER_ENV: "on"}, tag="diff-on") as module:
        on = drive(module, rows, HeaderEgress())
    random_keys = ("session_id", "idempotency_key")
    for row in rows:
        row_id = str(row["id"])
        assert set(on[row_id]) - set(off[row_id]) <= {"lane"}, row_id + "：多出的不止 lane"
        stripped_on = {k: v for k, v in on[row_id].items()
                       if k not in random_keys and k != "lane"}
        stripped_off = {k: v for k, v in off[row_id].items() if k not in random_keys}
        assert stripped_on == stripped_off == {"message": off[row_id]["message"]}, \
            row_id + "：补 lane 的同时动了别的字节"
        for key in random_keys:
            assert re.fullmatch(r"[0-9a-f]{32}", on[row_id][key]), (row_id, key)
            assert on[row_id][key] != off[row_id][key], row_id + "：" + key + " 两态撞值"


# ==================== 判据③ 的第二腿：把服务端说的档位名记进第三份件 ====================

def test_the_ledger_leg_records_what_the_server_said(tmp_path):
    """开记账腿 ⇒ 第三份件一题一行，档位名就是响应头那一枚，不拿发出去的那一枚冒充。"""
    rows = corpus_sample()
    effective = {row["question"]: ("report" if row.get("tier") == REPORT_TIER else
                                   "analysis" if row.get("tier") == ANALYSIS_TIER else None)
                 for row in rows}
    with stage(tmp_path, env={RECORD_ENV: "on"}, tag="ledger") as module:
        egress = HeaderEgress(effective)
        payloads = drive(module, rows, egress)
        files = ledger_files(tmp_path)
        assert files == [module.SIDECAR.stem + "-lane.jsonl"], files
        rows_out = read_jsonl(tmp_path / files[0])
    assert {row["id"] for row in rows_out} == {str(row["id"]) for row in rows}
    assert len(rows_out) == len(rows), "一题一行的纪律破了"
    by_id = {row["id"]: row for row in rows_out}
    assert all(row["headers_readable"] is True for row in rows_out)
    report_row = by_id[[str(row["id"]) for row in rows if row.get("tier") == REPORT_TIER][0]]
    assert report_row["effective_lane"] == REPORT_LANE, report_row
    assert report_row["sent_lane"] is None, "只开记账腿不许动载荷"
    assert payloads[report_row["id"]].get("lane") is None, "记账腿把 lane 漏进载荷了"
    assert report_row["lane_source"] == "r42_question", report_row
    assert report_row["server_declared_lane"] is None, "服务端没发的头被记成了空值"
    qa_row = by_id[[str(row["id"]) for row in rows if row.get("tier") == QA_TIER][0]]
    assert qa_row["effective_lane"] is None and qa_row["headers_readable"] is True, \
        "服务端少发一枚头时，这一格必须读作取不到（不是空档，也不是零枚）"


def test_the_ledger_leg_with_declaration_stores_both_the_sent_and_the_read_back(tmp_path):
    """两腿同开：发出去的那一枚与读回来的那一枚并排记，谁也不覆盖谁（声明档≠生效档）。"""
    rows = corpus_sample()
    flipped = {row["question"]: ("qa" if row.get("tier") == REPORT_TIER else None) for row in rows}
    with stage(tmp_path, env={RECORD_ENV: "on", PER_TIER_ENV: "on"}, tag="both-legs") as module:
        payloads = drive(module, rows, HeaderEgress(flipped))
        rows_out = read_jsonl(tmp_path / ledger_files(tmp_path)[0])
    by_id = {row["id"]: row for row in rows_out}
    report_id = [str(row["id"]) for row in rows if row.get("tier") == REPORT_TIER][0]
    assert payloads[report_id]["lane"] == REPORT_LANE
    assert by_id[report_id]["sent_lane"] == REPORT_LANE
    assert by_id[report_id]["effective_lane"] == "qa", "生效档被声明档盖掉了 ⇒ 读的是同一枚字两遍"
    assert by_id[report_id]["server_declared_lane"] == REPORT_LANE
    assert by_id[report_id]["lane_source"] == "explicit"


def test_a_response_without_headers_is_recorded_as_cannot_read(tmp_path):
    """假出口根本没 headers 这一格（在册 R520/R181 那些件就是这一形）⇒ 记 False，不折成空档。"""
    rows = corpus_sample()
    with stage(tmp_path, env={RECORD_ENV: "on"}, tag="no-headers") as module:
        from test_r520_declare_lane_env_leg import AskEgress

        drive(module, rows, AskEgress())
        rows_out = read_jsonl(tmp_path / ledger_files(tmp_path)[0])
    assert len(rows_out) == len(rows)
    for row in rows_out:
        assert row["headers_readable"] is False, row
        assert row["effective_lane"] is None and row["lane_source"] is None, row


def test_the_lane_ledger_path_follows_the_env_override(tmp_path):
    """EVAL_LANE_LEDGER 指哪落哪（与 frame_ledger_path 同一条调用期读表纪律）。"""
    target = tmp_path / "elsewhere" / "lane-override.jsonl"
    rows = corpus_sample()[:1]
    with stage(tmp_path, env={RECORD_ENV: "on", LEDGER_PATH_ENV: str(target)},
               tag="override") as module:
        drive(module, rows, HeaderEgress())
        assert ledger_files(tmp_path) == [], "设了覆盖路径还跟着侧车落了一份"
        assert module.lane_ledger_path() == target, "调用期没读覆盖那枚键（键名漂了就是这一格）"
    assert target.exists(), target
    with stage(tmp_path, env={RECORD_ENV: "on"}, tag="derived") as module:
        assert module.lane_ledger_path() == tmp_path / (module.SIDECAR.stem + "-lane.jsonl"), \
            "不设覆盖时它必须跟着侧车走（runbook §8 产物落仓外那条纪律就靠这一格自动覆盖）"


# ==================== 与产品同源（本席不 import app.**，只读源码）====================

def module_level_literals(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    table = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                node.targets[0], ast.Name):
            try:
                table[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue
    return table


def test_the_switch_vocabulary_and_header_words_match_the_product(tmp_path):
    """开关字面与三枚头名都取产品那一侧：量具改一枚字面 = 读了个没人发的头，必须当场红。"""
    with stage(tmp_path, tag="same-source") as module:
        on_values = set(module.LANE_SWITCH_ON_VALUES)
        header_names = (module.EFFECTIVE_LANE_HEADER, module.DECLARED_LANE_HEADER,
                        module.LANE_SOURCE_HEADER)
        env_names = (module.LANE_PER_TIER_ENV, module.LANE_RECORD_ENV, module.LANE_LEDGER_ENV)
    product = module_level_literals(CHAT_PATH)
    assert on_values == set(product["REPORT_LANE_ON_VALUES"]), repr(on_values)
    assert header_names == (product["EFFECTIVE_LANE_HEADER"], product["DECLARED_LANE_HEADER"],
                            product["LANE_SOURCE_HEADER"]), "头名与产品不同源"
    assert module.LANE_PER_TIER_ENV == PER_TIER_ENV and module.LANE_RECORD_ENV == RECORD_ENV
    assert env_names == (PER_TIER_ENV, RECORD_ENV, LEDGER_PATH_ENV)
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "import app." not in source and "from app." not in source, \
        "采集器 import 了 app.**（在册源码级钉 test_r123_hitl_approval.py 会当场红）"


def test_the_two_new_env_names_are_the_ones_the_ruler_reads():
    """读表腿的名字钉子：本件设的键必须就是量具读的键，不然上面全是自说自话。

    量具那三枚键名住在模块级字面里，`os.getenv` 是在 `_lane_switch` 里按名读的（不是逐枚写死，
    与产品那枚 `_report_lane_via_queue_enabled` 同形），所以这一枚从 AST 现读键名再核：
    ① 三枚键名各在源文里出现**恰一次**（写两遍就是两把尺）；② 读表本体确实调 os.getenv 且
    确实拿 LANE_SWITCH_ON_VALUES 判（把 `in LANE_SWITCH_ON_VALUES` 摘掉这枚钉就红）。
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    literals = module_level_literals(SCRIPT_PATH)
    assert literals[LANE_PER_TIER_CONSTANT] == PER_TIER_ENV, literals.get(LANE_PER_TIER_CONSTANT)
    assert literals[LANE_RECORD_CONSTANT] == RECORD_ENV, literals.get(LANE_RECORD_CONSTANT)
    assert literals[LANE_LEDGER_CONSTANT] == LEDGER_PATH_ENV, literals.get(LANE_LEDGER_CONSTANT)
    for name in (PER_TIER_ENV, RECORD_ENV, LEDGER_PATH_ENV):
        assert source.count('"%s"' % name) == 1, name + " 在采集器里出现了不止一枚字面"
    body = source[source.index("def _lane_switch"):]
    body = body[:body.index("\n\n\n")]
    assert "os.getenv(" in body, "读表腿不再从进程环境读：" + repr(body)
    assert "LANE_SWITCH_ON_VALUES" in body, "开关判据不再与那枚字面集对判：" + repr(body)
    assert "os.environ" not in body, "读表腿绕去动盘面了（本单不许写环境）"


# ==================== 反证四把（只在临时根副本上动刀，原件前后各核一次指纹）====================

KNIVES = {
    "K1_per_tier_switch_ignored": {
        "anchor": "            if DECLARE_LANE_PER_TIER and not lane:",
        "replace": "            if not lane:",
        "victim": "判据①（不设开关时载荷一字不多）",
    },
    "K2_ledger_written_anyway": {
        "anchor": "        if RECORD_LANE_READOUT:",
        "replace": "        if True:",
        "victim": "判据①（默认态第三份件一个都不落）",
    },
    "K3_read_leg_always_on": {
        "anchor": '    return os.getenv(name, "").strip().lower() in LANE_SWITCH_ON_VALUES',
        "replace": "    return True",
        "victim": "判据①②③（两枚开关从环境读的那条腿整个不存在）",
    },
    "K4_effective_header_word_drifts": {
        "anchor": 'EFFECTIVE_LANE_HEADER = "x-effective-lane"',
        "replace": 'EFFECTIVE_LANE_HEADER = "x-effective-lanez"',
        "victim": "与产品同源那一枚钉 + 记账腿那两格读数",
    },
}


@contextlib.contextmanager
def mutant(tmp_path, name):
    """按锚点改出一份采集器副本；原件一根手指都不碰（进刀前后各核一次 sha256）。"""
    knife = KNIVES[name]
    original = SCRIPT_PATH.read_bytes()
    baseline = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8").replace("\r\n", "\n")
    hits = text.count(knife["anchor"])
    assert hits == 1, name + "：锚点在原件里出现 " + str(hits) + " 次，不唯一 ⇒ 这枚反证是空的"
    mutated = text.replace(knife["anchor"], knife["replace"], 1)
    assert mutated != text, name + "：改了个寂寞"
    target = tmp_path / ("r632_" + name + ".py")
    target.write_text(mutated, encoding="utf-8")
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == baseline, name + "：跟踪里的原件被动了"
    yield target
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == baseline, \
        name + "：反证跑完原件不是原样"


def off_state(source, tmp_path, tag):
    """「两枚开关都不设」那一格在指定源码上的读数：逐题载荷的 lane + 第三份件落没落。

    🔴 落点一律现取 module.lane_ledger_path()，不 glob 整个 tmp_path：同一枚 tmp_path 里
    正控与刀下各跑一遍，glob 会把上一遍的产物算进这一遍的读数（本件第一版就栽在这里）。
    """
    rows = corpus_sample()
    with stage(tmp_path, source_path=source, tag=tag) as module:
        payloads = drive(module, rows, HeaderEgress())
        return lane_cells(payloads), module.lane_ledger_path().exists()


def same_source_state(source, tmp_path, tag):
    """「与产品同源」那一格的读数：量具那三枚头名 vs 产品源码 AST 现读的那三枚。"""
    with stage(tmp_path, source_path=source, tag=tag) as module:
        product = module_level_literals(CHAT_PATH)
        mine = (module.EFFECTIVE_LANE_HEADER, module.DECLARED_LANE_HEADER,
                module.LANE_SOURCE_HEADER)
        theirs = (product["EFFECTIVE_LANE_HEADER"], product["DECLARED_LANE_HEADER"],
                  product["LANE_SOURCE_HEADER"])
        return mine, theirs, module


def read_back_state(source, tmp_path, tag):
    """开记账腿、服务端真发了头的那一格在指定源码上的读数：逐题读回的档位名。"""
    rows = corpus_sample()
    effective = {row["question"]: "qa" for row in rows}
    with stage(tmp_path, source_path=source, env={RECORD_ENV: "on"}, tag=tag) as module:
        drive(module, rows, HeaderEgress(effective))
        return read_jsonl(module.lane_ledger_path())


def test_k1_ignoring_the_per_tier_switch_goes_red_on_criterion_one(tmp_path):
    """K1：把「开关开着才补」摘成「无条件补」⇒ 判据① 那一格必须当场红。"""
    cells, landed = off_state(SCRIPT_PATH, tmp_path, "k1-control")
    assert all(lane is None for lane in cells.values()) and landed is False, "影子端正控不成立"
    with mutant(tmp_path, "K1_per_tier_switch_ignored") as source:
        cells, _landed = off_state(source, tmp_path, "k1")
    assert any(lane is not None for lane in cells.values()), \
        "刀下默认态还是不载荷 lane ⇒ 判据① 看不见这条变异（永真钉）"


def test_k2_writing_the_ledger_anyway_goes_red_on_the_default_disk_shape(tmp_path):
    """K2：把「开关开着才落盘」摘成恒落盘 ⇒ 默认态盘面多出一件，判据① 必须红。"""
    cells, landed = off_state(SCRIPT_PATH, tmp_path, "k2-control")
    assert landed is False, "影子端正控不成立：默认态已经会落了"
    with mutant(tmp_path, "K2_ledger_written_anyway") as source:
        _cells, landed = off_state(source, tmp_path, "k2")
    assert landed is True, "刀下默认态仍不落盘 ⇒ 那条『一字不多』是枚永真钉"


def test_k3_always_on_read_leg_goes_red_on_both_legs_at_once(tmp_path):
    """K3：读表腿恒真（环境这一路彻底不存在）⇒ 载荷腿与记账腿两格一起红。"""
    with mutant(tmp_path, "K3_read_leg_always_on") as source:
        cells, landed = off_state(source, tmp_path, "k3")
    assert any(lane is not None for lane in cells.values()), "载荷腿这一格对这条变异全盲"
    assert landed is True, "记账腿这一格对这条变异全盲"


def test_k4_a_drifted_header_word_goes_red_on_the_same_source_nail(tmp_path):
    """K4：头名漂一枚尾字 ⇒ 同源钉红，且记账腿读回的档位名整列变空（这才是真代价）。

    这一把是本单最要命的一族：**没读到头**与**服务端没给读数**在账上长得一模一样。
    同源钉先把字面钉住，read_back 那一格再证明「漂了之后读数确实整列空」——
    少了后一半，改头名只会让下一窗安静地交出 0/105，与今天这格的病同形。
    """
    mine, theirs, _module = same_source_state(SCRIPT_PATH, tmp_path, "k4-control")
    assert mine == theirs, "影子端正控不成立：真树上头名就已经不同源"
    rows = read_back_state(SCRIPT_PATH, tmp_path, "k4-green")
    assert [row["effective_lane"] for row in rows] == ["qa"] * len(rows), rows
    with mutant(tmp_path, "K4_effective_header_word_drifts") as source:
        mine, theirs, _module = same_source_state(source, tmp_path, "k4-mutant")
        assert mine != theirs, "头名与产品不同源却钉不住 ⇒ 同源钉是枚空钉"
        rows = read_back_state(source, tmp_path, "k4-mutant-ledger")
    assert all(row["effective_lane"] is None for row in rows), \
        "刀下居然还读得到档位名 ⇒ read_back 那一格没牙"
    assert all(row["headers_readable"] is True for row in rows), \
        "头名漂走时 headers_readable 必须仍是 True：这是「我们认错了头」不是「没头可读」"
