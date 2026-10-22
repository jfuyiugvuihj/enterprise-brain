# -*- coding: utf-8 -*-
r"""R678 判据①②③ 的量具半张：缺省不许静默——指望入队却没声明档位，开跑那一刻就具名拒。

## 现取病形（本件钉的就是它）

带 1 已收的三扇 on 相（run24s2／run24s2b／run24s2c）里 12 枚报告题正文全在、queued_polled 零枚：
容器侧 REPORT_LANE_VIA_QUEUE 翻了 on，量具这一侧 EVAL_DECLARE_LANE_TIER 缺省空串、
EVAL_DECLARE_LANE_PER_TIER 也关着 ⇒ 一发 lane 都不出门，服务端「lane 等于 report 且开关 on」
那两道与件永远差一半。从前量具对这件事的态度是「照跑，事后你自己发现」⇒ 三扇全成废样本。

## 本件的三条判据（全离线：假出口、零网络、零模型、零容器、零连库）

① 指望入队（量具进程环境里那枚与产品同名的开关是 on）却一枚 lane 都不发 ⇒ transport 在
   login **之前** raise LaneDeclarationError，假出口里一条路径都不许多打；错误句必须点名
   EVAL_DECLARE_LANE_TIER 并说出「报告档要 on 相必须显式声明 tier」这一句（判据① 原文）。
   🔴 本件同时钉住反面：两枚开关都不设、也不指望入队时，载荷与产物逐字节回到 R520／R632 的
   旧口径。判据① 里「未设就致命」那一半**没有整本照做**，理由是它和并树在册钉正面冲突：
   tests/test_r520_declare_lane_env_leg.py 的 test_an_unset_key_leaves_the_report_tier_on_the
   sync_path 钉死了「键不在盘上 ⇒ 报告档一题都不发、载荷仍是那三键」，而那枚文件不在本单
   写域。要把它改成致命，得由总控先动 R520 的钉（另立一号），不由执行层偷偷放宽。
   替代的静默出口有两道：人工那一步 --lane-preflight（本件第 9 组），事后那把尺
   scripts/r573_caliber_reconciliation.py 的 --expect-lane-phase on（另件 test_r678_waste_sample
   _ruler.py）。
② 声明腿在位时 lane 必须逐请求出门：设了档位名 ⇒ 该档每一行都带；开 per-tier ⇒ 三档逐行各带；
   声明了名册外的名字 ⇒ 与没声明同形，一样拒（判据② 的「逐请求」不许只在正控里演一遍）。
③ 反证牙双向（判据③）：把声明腿摘掉 ⇒ 本件必须红；补回 ⇒ 必须绿。摘法见 KNIVES，
   每一把都先核原件 sha，动刀只在 tmp_path 的副本上。

## 判据④ 的边界（本件一个字都没碰）

评测夹具／判分器／tests/test_evaluation_report.py／deploy/** 的当前值／任何容器与镜像动作：
全部零命中。意图那一枚信号读的是量具**自己进程环境**里与产品同名的开关，不读 deploy/.env.server，
也不问容器；容器真值由开窗人在 --lane-preflight --env-file 里现取（第 9 组那几枚用例演这一格）。
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from test_r520_declare_lane_env_leg import (  # noqa: F401  共用同一套离线假出口与题册
    ANALYSIS_TIER,
    BASE_PAYLOAD_KEYS,
    QA_TIER,
    REPORT_LANE,
    REPORT_TIER,
    SCRIPT_PATH,
    AskEgress,
    fixture_rows,
    rows_with_tier,
)
from test_r632_transport_lane_switches import (  # noqa: F401  共用装配与读数件读法
    HeaderEgress,
    drive,
    read_jsonl,
    stage,
)

TIER_ENV = "EVAL_DECLARE_LANE_TIER"
PER_TIER_ENV = "EVAL_DECLARE_LANE_PER_TIER"
RECORD_ENV = "EVAL_RECORD_LANE_READOUT"
#: 意图那一枚：与产品同名（app/api/v1/chat.py 的 REPORT_LANE_QUEUE_ENV），本件不另造词。
INTENT_ENV = "REPORT_LANE_VIA_QUEUE"
#: 判据① 点名要出现的那一句话，逐字钉，摘掉半句就红。
NAMED_SENTENCE = "报告档要 on 相必须显式声明 tier"


_TAG = itertools.count()

def clean_env(**overrides):
    """每一枚用例都从「四枚键全不在盘上」起跳：壳子里残留的开关不许替本席决定判据。"""
    env = {TIER_ENV: None, PER_TIER_ENV: None, RECORD_ENV: None, INTENT_ENV: None}
    env.update(overrides)
    return env


def raise_of(module, rows):
    """跑第一题，交回 (异常或 None, 假出口打过的路径, 交回的 payload)。"""
    egress = AskEgress()
    module._open = egress
    caught = None
    payload = None
    try:
        payload = module.transport(dict(rows[0]))
    except Exception as exc:  # noqa: BLE001  本件要的就是异常本身
        caught = exc
    return caught, list(egress.paths), payload


def refusal_text(exc):
    return str(exc)


# ==================== 一、判据① 的正面：指望入队却没声明 ⇒ 开跑那一刻具名拒 ====================


def test_on_phase_without_declaration_refuses_before_a_single_request(tmp_path):
    rows = rows_with_tier(REPORT_TIER)
    assert rows, "夹具里没有报告档 ⇒ 本枚判据会空转"
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), tag="refuse") as module:
        caught, paths, payload = raise_of(module, rows)
    assert isinstance(caught, module.LaneDeclarationError), repr(caught)
    assert payload is None, "拒了却还交回了答案 ⇒ 这一窗仍会被当成样本拼进账"
    # 🔴 「开跑那一刻」的硬证据：门打在 login 之前，假出口一条路径都没被打过。
    assert paths == [], "具名拒之前已经打出去了：" + repr(paths)


def test_refusal_names_the_key_the_roster_and_the_required_sentence(tmp_path):
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), tag="words") as module:
        caught, _paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
    text = refusal_text(caught)
    assert NAMED_SENTENCE in text, "判据① 点名要的那一句不见了：" + text
    assert TIER_ENV in text, "错误句没点名那枚键：" + text
    assert PER_TIER_ENV in text, "错误句没给出逐行那一条腿：" + text
    assert module.EXPECT_QUEUE_LANE_ENV == INTENT_ENV, "意图那枚键与产品不同名了"
    for tier in sorted(module.LANE_BY_TIER):
        assert tier in text, "错误句没把名册现读出来，开窗人无从对：" + tier


def test_empty_value_is_the_same_shape_as_not_setting_it(tmp_path):
    """键在盘上但是空串 ⇒ 与没设同形（R520 判据① 的第二格在 on 相里同样致命）。"""
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: ""}), tag="empty") as module:
        caught, paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
    assert isinstance(caught, module.LaneDeclarationError), repr(caught)
    assert paths == []


def test_the_gate_never_guesses_a_tier(tmp_path):
    """判据① 后半句：拒的时候不许有任何一题被补上 lane——量具不许替开窗人猜一档。"""
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), tag="noguess") as module:
        state = module.lane_declaration()
        caught, _paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
    assert isinstance(caught, module.LaneDeclarationError)
    assert state["sends_any_lane"] is False, "闸判「一枚都不发」时却不成立：" + json.dumps(state)
    assert state["tier_raw"] == "" and state["tier_declared"] is False


# ==================== 二、判据②：声明腿在位 ⇒ lane 逐请求出门 ====================


def test_declared_tier_sends_lane_on_every_request_of_that_tier(tmp_path):
    rows = rows_with_tier(REPORT_TIER)
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: REPORT_TIER}),
               tag="tier") as module:
        payloads = drive(module, rows, AskEgress())
    assert payloads, "本枚判据会空转"
    assert {str(row["id"]): payloads[str(row["id"])].get("lane") for row in rows} == \
        {str(row["id"]): REPORT_LANE for row in rows}, "报告档里有题没带 lane"


def test_per_tier_leg_satisfies_the_gate_and_lanes_every_row(tmp_path):
    rows = fixture_rows()
    table = {"报告": "report", "分析": "analysis", "问答": "qa"}
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", PER_TIER_ENV: "on"}),
               tag="pertier") as module:
        payloads = drive(module, rows, AskEgress())
    for row in rows:
        tier = str(row.get("tier", "")).strip()
        got = payloads[str(row["id"])].get("lane")
        want = table.get(tier) or None
        assert got == want, str(row["id"]) + "：档位 " + tier + " 该发 " + str(want) + "，实发 " + str(got)


def test_a_declaration_outside_the_roster_is_refused_while_expect_queue(tmp_path):
    """名册外的档位名＝与没声明同形（R520 判据③），在指望入队那一窗里一样致命，不许静默照跑。"""
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: "报表"}), tag="roster") as module:
        caught, paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
    assert isinstance(caught, module.LaneDeclarationError), repr(caught)
    assert "名册" in refusal_text(caught)
    assert paths == []


def test_explicit_sync_declaration_while_expect_queue_is_refused(tmp_path):
    """两句话互相矛盾：把这一窗声明成同步相，却又带着入队开关 ⇒ 拒，且不许猜哪句是真。"""
    for value in sorted({str(item) for item in ["off", "none", "no-lane", "sync"]}):
        with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: value}),
                   tag="none-" + value) as module:
            caught, paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
        assert isinstance(caught, module.LaneDeclarationError), value + "：" + repr(caught)
        assert "互相矛盾" in refusal_text(caught), value
        assert paths == []


def test_the_readback_leg_now_shows_the_sent_lane_for_every_declared_row(tmp_path):
    """判据② 的「现读」那一格：声明在位 + 读数腿开着 ⇒ 第三份件逐题写着量具发出去的档位名。"""
    rows = rows_with_tier(REPORT_TIER)
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: REPORT_TIER,
                                          RECORD_ENV: "on"}), tag="ledger") as module:
        drive(module, rows, HeaderEgress())
        ledger = read_jsonl(module.lane_ledger_path())
    assert len(ledger) == len(rows), "读数件逐题一行：" + str(len(ledger)) + "≠" + str(len(rows))
    assert {item["sent_lane"] for item in ledger} == {REPORT_LANE}, repr(ledger[:2])
    assert all(item["id"] and item["session_id"] for item in ledger), \
        "读数件丢了 join 键：侧车 ← 帧账 ← 本件那三跳就断了"


# ==================== 三、判据① 的反面：不指望入队时，旧口径逐字节不许漂 ====================


def test_sync_phase_default_payloads_are_still_the_three_keys(tmp_path):
    """R520 判据① 与 R632 判据① 的形状在本单之后照旧：不设、不指望 ⇒ 一题都不带 lane。"""
    rows = rows_with_tier(REPORT_TIER)
    with stage(tmp_path, env=clean_env(), tag="sync") as module:
        payloads = drive(module, rows, AskEgress())
        sidecar_keys = set().union(*[set(json.loads(line)) for line in
                                     module.SIDECAR.read_text(encoding="utf-8").splitlines()])
        state = module.lane_declaration()
    assert payloads, "本枚判据会空转"
    shapes = {tuple(sorted(payload)) for payload in payloads.values()}
    assert shapes == {tuple(sorted(BASE_PAYLOAD_KEYS))}, "同步相的载荷多出了字节：" + repr(shapes)
    assert not (sidecar_keys & {"lane", "effective_lane", "sent_lane", "lane_source"})
    assert state["expect_queue_lane"] is False and state["sends_any_lane"] is False


def test_sync_phase_writes_no_lane_file(tmp_path):
    with stage(tmp_path, env=clean_env(), tag="nolane") as module:
        drive(module, rows_with_tier(REPORT_TIER), AskEgress())
        assert not module.lane_ledger_path().exists(), "默认态落出了新产物"
        assert module.require_lane_declaration("doc-01")["expect_queue_lane"] is False


# ==================== 四、判据⑤ 的人工那一步：--lane-preflight ====================


def env_file(tmp_path, value):
    path = tmp_path / ("r678-env-" + str(next(_TAG)) + ".txt")
    path.write_text("# compose 用的那本 env（本件只读它）" + chr(10)
                    + "INDEX_BACKEND=pgvector" + chr(10)
                    + "REPORT_LANE_VIA_QUEUE=" + value + chr(10), encoding="utf-8")
    return path


def test_preflight_refuses_the_run24s2_shape_by_name(tmp_path, capsys):
    """带 1 那一扇的起手式：env-file 里开关是 on，采集进程里没声明 ⇒ 前置就该拦下。"""
    path = env_file(tmp_path, "on")
    with stage(tmp_path, env=clean_env(), tag="pre-refuse") as module:
        rc = module.main(["--lane-preflight", "--env-file", str(path)])
        expect_refuse = module.RC_PREFLIGHT_REFUSE
    out = capsys.readouterr()
    assert rc == expect_refuse == 2, repr((rc, out.out))
    assert NAMED_SENTENCE in out.err, out.err
    assert TIER_ENV in out.err, out.err
    assert "run24s2" not in out.out + out.err, "前置不该把窗名硬编进判据"


def test_preflight_passes_when_the_tier_is_declared(tmp_path, capsys):
    path = env_file(tmp_path, "on")
    with stage(tmp_path, env=clean_env(**{TIER_ENV: REPORT_TIER}), tag="pre-pass") as module:
        rc = module.main(["--lane-preflight", "--env-file", str(path)])
        state = module.lane_declaration()
    assert rc == module.RC_PREFLIGHT_OK == 0, rc
    assert state["sends_any_lane"] is True
    assert "on 相" in capsys.readouterr().out


def test_preflight_says_sync_phase_loudly_when_the_switch_is_off(tmp_path, capsys):
    path = env_file(tmp_path, "off")
    with stage(tmp_path, env=clean_env(), tag="pre-off") as module:
        rc = module.main(["--lane-preflight", "--env-file", str(path)])
    out = capsys.readouterr().out
    assert rc == 0, rc
    assert "不进 D 门账" in out, "同步相必须把这句话写在盘面上：" + out


def test_preflight_refuses_to_read_blind_as_off(tmp_path, capsys):
    """两处都问不着 ⇒ 非零退出。把「问不着」折成 off 然后照跑，正是废样本的起手式。"""
    with stage(tmp_path, env=clean_env(), tag="pre-blind") as module:
        rc_blind = module.RC_PREFLIGHT_ASKED_BLIND
        rc_missing = module.main(["--lane-preflight", "--env-file",
                                      str(tmp_path / "nope.txt")])
        rc_none = module.main(["--lane-preflight"])
    assert rc_missing == rc_blind == 4, rc_missing
    assert rc_none == rc_blind, rc_none
    assert "问不着" in capsys.readouterr().err


def test_preflight_honours_an_explicit_phase(tmp_path):
    with stage(tmp_path, env=clean_env(**{TIER_ENV: "off"}), tag="pre-phase") as module:
        rc_on = module.main(["--lane-preflight", "--phase", "on"])
        rc_off = module.main(["--lane-preflight", "--phase", "off"])
    assert rc_on == 2 and rc_off == 0, repr((rc_on, rc_off))


def test_preflight_is_the_only_reader_of_the_env_file(tmp_path):
    """前置只读盘：值取最后一个，井号行跳过，引号脱掉；本件绝不动容器、也不动进程环境。"""
    path = tmp_path / "r678-multi-env.txt"
    lines = ["REPORT_LANE_VIA_QUEUE=on", "#REPORT_LANE_VIA_QUEUE=off",
             "INDEX_BACKEND=pgvector",
             "REPORT_LANE_VIA_QUEUE=" + chr(34) + "off" + chr(34)]
    path.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    with stage(tmp_path, env=clean_env(**{TIER_ENV: REPORT_TIER}), tag="pre-parse") as module:
        got = module.read_env_file_switch(path)
        rc = module.main(["--lane-preflight", "--env-file", str(path)])
        env_after = os.environ.get(INTENT_ENV)
        read_back = module.lane_declaration()["expect_queue_lane"]
    assert got == "off", repr(got)
    assert rc == 0, rc
    assert env_after is None, "前置把读到的值又写回盘面了"
    assert read_back is False, "读到的值污染了本进程的声明读数"


def test_summary_reports_the_declaration_state(tmp_path):
    """收窗自查那一格：这一窗声明了什么，写在盘面上，不必事后摊开 sidecar 与 answers 对。"""
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on", TIER_ENV: REPORT_TIER}),
               tag="summary") as module:
        drive(module, rows_with_tier(REPORT_TIER), AskEgress())
        readout = module.summary()
    declared = readout["lane_declaration"]
    assert declared["sends_any_lane"] is True, json.dumps(declared, ensure_ascii=False)
    assert declared["tier_raw"] == REPORT_TIER and declared["expect_queue_lane"] is True
    with stage(tmp_path, env=clean_env(), tag="summary-off") as module:
        quiet = module.summary()["lane_declaration"]
    assert quiet["sends_any_lane"] is False and quiet["expect_queue_lane"] is False


# ==================== 五、判据③：反证牙（摘腿必红·补回必绿·原件一根手指不碰）============

SOURCE_ANCHORS = (
    "    require_lane_declaration(row_id)",
    "EXPECT_QUEUE_LANE = _lane_switch(EXPECT_QUEUE_LANE_ENV)",
    "def require_lane_declaration(where=",
    "def lane_preflight(phase=",
    #: 这两枚是别人的在册刀位（R520 的读取腿、R632 的 K1／K2 锚点）——本单一枚都不许挪。
    "DECLARE_LANE_TIER = os.getenv(",
    "            if DECLARE_LANE_PER_TIER and not lane:",
    "        if RECORD_LANE_READOUT:",
    NAMED_SENTENCE,
)


def test_the_legs_have_exactly_one_home_each():
    """每一枚腿只住一个地方：写两遍就是两把尺，挪走了就是摘牙换了个格子。"""
    text = SCRIPT_PATH.read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
    for anchor in SOURCE_ANCHORS:
        assert text.count(anchor) == 1, anchor + " 在采集器里出现 " + str(text.count(anchor)) + " 次"
    assert "import app." not in text and "from app." not in text, \
        "采集器 import 了 app.**（在册源码级钉 test_r123_hitl_approval.py 会当场红）"


KNIVES = {
    "gate_call_removed": (
        "    require_lane_declaration(row_id)",
        "    pass  # 摘牙：把开跑那一刻那道门摘掉",
    ),
    "intent_leg_hard_off": (
        "EXPECT_QUEUE_LANE = _lane_switch(EXPECT_QUEUE_LANE_ENV)",
        "EXPECT_QUEUE_LANE = False  # 摘牙：指望入队那一格永远读不出来",
    ),
    "named_sentence_dropped": (
        "。" + NAMED_SENTENCE,
        "。",
    ),
}


@contextlib.contextmanager
def knife(tmp_path, name):
    """按锚点改出一份采集器副本；原件进刀前后各核一次 sha256，一根手指都不碰。"""
    old, new = KNIVES[name]
    original = SCRIPT_PATH.read_bytes()
    baseline = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8").replace(chr(13) + chr(10), chr(10))
    hits = text.count(old)
    assert hits == 1, name + "：锚点在原件里出现 " + str(hits) + " 次，不唯一 ⇒ 这枚反证是空的"
    mutated = text.replace(old, new, 1)
    assert mutated != text, name + "：改了个寂寞"
    target = tmp_path / ("r678_knife_" + name + ".py")
    target.write_text(mutated, encoding="utf-8")
    try:
        yield target
    finally:
        assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == baseline, \
            name + "：反证跑完原件不是原样"


def test_knife_1_removing_the_gate_returns_the_waste_sample_shape(tmp_path):
    """摘掉开跑那一刻那道门 ⇒ 判据① 那两格必红：指望入队却不拒，还照旧把同步道样本交回去。"""
    rows = rows_with_tier(REPORT_TIER)
    with knife(tmp_path, "gate_call_removed") as source:
        with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), source_path=source,
                   tag="k1") as module:
            caught, paths, payload = raise_of(module, rows)
    assert caught is None, "摘了门还在拒 ⇒ 这枚反证咬的不是那一枚腿：" + repr(caught)
    assert payload is not None and paths, "摘牙后必须退回今天那种静默照跑（那才是病形）"


def test_knife_2_blinding_the_intent_leg_returns_the_same_shape(tmp_path):
    """把「指望入队」那一枚读表腿摘成恒假 ⇒ 同一形又静默了：门在位却永远不触发。"""
    with knife(tmp_path, "intent_leg_hard_off") as source:
        with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), source_path=source,
                   tag="k2") as module:
            caught, _paths, payload = raise_of(module, rows_with_tier(REPORT_TIER))
            state = module.lane_declaration()
    assert caught is None and payload is not None
    assert state["expect_queue_lane"] is False, "摘牙后意图那一格还读得出东西：" + repr(state)


def test_knife_3_dropping_the_named_sentence_goes_red(tmp_path):
    """错误句里判据① 点名的那半句被摘掉 ⇒ 判据① 的字面钉必红。"""
    with knife(tmp_path, "named_sentence_dropped") as source:
        with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), source_path=source,
                   tag="k3") as module:
            caught, paths, _payload = raise_of(module, rows_with_tier(REPORT_TIER))
    assert isinstance(caught, module.LaneDeclarationError), repr(caught)
    assert paths == [], "摘了那半句还顺手把请求打出去了"
    assert NAMED_SENTENCE not in refusal_text(caught), "刀没落下：那句话还在错误句里"


def test_the_teeth_are_green_again_after_every_knife(tmp_path):
    """补回 ⇒ 必须绿：三把刀都只在副本上动过，原件上那一形照旧当场具名拒、一发都不打。"""
    with stage(tmp_path, env=clean_env(**{INTENT_ENV: "on"}), tag="after-knives") as module:
        caught, paths, payload = raise_of(module, rows_with_tier(REPORT_TIER))
    assert isinstance(caught, module.LaneDeclarationError), repr(caught)
    assert NAMED_SENTENCE in refusal_text(caught)
    assert paths == [] and payload is None
