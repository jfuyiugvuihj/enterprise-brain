# -*- coding: utf-8 -*-
"""R506 钉②（2026-09-29，执行层 Feynman）：帧账缺**必读键**必须报错，不许当零。

A② 的翻绿算式全靠帧账那几格读数；一旦「缺格」被读成「零」，②就会朝**绿的方向**漂：``missing_chars=0`` 与「这一格从没量过」在合取里长得一模一样。判器自己把这条纪律写在
``scripts/r239_stream_gap_offline_audit.py:79``（「少任何一枚就不是『没量到』而是『这份账不是一张帧账』，
直接 raise」）与 :138（派生不出 ⇒ 回 ``None``，「不许报 0 冒充量过」）。本钉封的就是这两条不许漂。

夹具全部**当场构造**（``tmp_path`` 落几行 JSON）：🔴 不读 903 KB 的在册全量帧账，零网络、
零容器、零模型，不写任何在册原件。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "r239_stream_gap_offline_audit", REPO_ROOT / "scripts" / "r239_stream_gap_offline_audit.py")
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def full_row(row_id="synthetic-01", **overrides):
    """一张**合法**的帧账行（五枚必读键齐、R471 派生列也可派生），再按需摘格。"""
    row = {
        "id": row_id,
        "kind": "ok",
        "text_frames": 2,
        "max_stream_frames": 2,
        "streams": 1,
        "per_stream": [{"frames": 2, "breaks": 0, "first_break_at": 0}],
        "missing_chars": 0,
        "extra_chars": 0,
        "last_frame_covers_answer": True,
        "uncorrected_breaks": 0,
        "answer_chars": 40,
        "criterion_two_holds": True,
        "frames": [{"stream": 0, "at": 1, "chars": 20, "sha": "aaaaaaaaaaaa"},
                   {"stream": 0, "at": 2, "chars": 40, "sha": "bbbbbbbbbbbb"}],
    }
    row.update(overrides)
    return row


def write_ledger(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("key", sorted(audit.REQUIRED_KEYS))
def test_b1_dropping_any_required_key_rejects_the_whole_ledger(tmp_path, key):
    """五枚必读键任一枚缺席 ⇒ ``LedgerSchemaError``，不许退化成「这一格读作 0」。"""
    row = full_row(**{"%s" % key: None})
    row.pop(key)
    ledger = write_ledger(tmp_path / "frames.jsonl", [json.dumps(row, ensure_ascii=False)])

    with pytest.raises(audit.LedgerSchemaError) as raised:
        audit.read_rows(ledger)

    message = str(raised.value)
    assert key in message, "报错必须点名缺的是哪一枚键：" + message
    assert ":%d" % 1 in message or str(ledger) in message, "报错必须点名是哪本账第几行"


def test_b2_the_three_char_countings_are_on_the_required_list():
    """派工单点名的三枚（``text_frames``/``missing_chars``/``extra_chars``）必须在必读名单上。

    名单一旦缩，缺格就会变成补零 —— 这一枚是把名单本身钉住，改名单要过这枚钉。
    """
    assert {"text_frames", "missing_chars", "extra_chars"} <= set(audit.REQUIRED_KEYS)
    assert {"last_frame_covers_answer", "criterion_two_holds"} <= set(audit.REQUIRED_KEYS)
    assert audit.REQUIRED_KEYS == ("text_frames", "missing_chars", "extra_chars",
                                   "last_frame_covers_answer", "criterion_two_holds")


def test_b3_a_ledger_line_that_is_not_an_object_is_rejected(tmp_path):
    """非 JSON 对象的一行也是「这不是帧账」，不许跳过该行少算一行分母。"""
    ledger = write_ledger(tmp_path / "frames.jsonl", ['["not", "a", "row"]'])

    with pytest.raises(audit.LedgerSchemaError):
        audit.read_rows(ledger)


def test_b4_missing_ledger_file_is_rejected(tmp_path):
    with pytest.raises(audit.LedgerSchemaError):
        audit.read_rows(tmp_path / "there-is-no-such-ledger.jsonl")


@pytest.mark.parametrize("key", sorted(audit.REQUIRED_KEYS))
def test_b5_the_judge_never_invents_a_zero_for_a_missing_required_key(key):
    """判器内部也不许 ``.get(...) or 0``：必读键缺席当场 ``KeyError``，不是静默补零。

    🔴 这一枚管的是判器**读法**而不是入口校验：``read_rows`` 挡在前面，但谁绕过它直接喂
    ``judge_row``（复算入口、别的小工具），也拿不到一枚假绿。
    """
    row = full_row()
    row.pop(key)

    with pytest.raises(KeyError):
        audit.judge_row(row)


def test_b6_no_per_frame_witness_reads_as_none_not_zero():
    """R471 那第七枚派生不出时必须回 ``None``：不许报 0 冒充量过，也不许追加定罪。

    run9 上 ``重合量不出=2`` 就是 ``metric-02``/``scope-02`` 那两枚零帧行（``frames`` 列在、
    是一个空表、一枚指纹都没有）。读数件 §2.D 靠这一格不漂才敢写「复算漂是账与尺不同代」。
    """
    without_column = full_row()
    without_column.pop("frames")
    empty_records = full_row(frames=[])

    assert audit.cross_stream_repeat_frames(without_column) is None
    assert audit.cross_stream_repeat_frames(empty_records) is None

    judged = audit.judge_row(without_column)
    summary = audit.summarize([judged])
    assert judged["cross_stream_repeat_frames"] is None
    assert summary["cross_stream_repeat_ids"] == [], "没量过不进重合名单"
    assert summary["cross_stream_repeat_unmeasurable"] == 1, "没量过必须自己占一格"


def test_b7_an_unmeasurable_seventh_conjunct_cannot_add_a_conviction():
    """派生不出 ⇒ 复算照当年的读数放行（``None`` 算通过）；量到了跨流重发 ⇒ 当场 FALSE。

    两半都要钉住：前半是「不追加定罪」（``scripts/r239_stream_gap_offline_audit.py:188``），
    后半是 R471 第七枚真的在跑 —— 摘掉它，``tool-04`` 那一形就悄悄绿了。
    """
    unmeasurable = full_row()
    unmeasurable.pop("frames")
    assert audit.recomputed_ledger(unmeasurable) is True

    re_send = full_row(frames=[
        {"stream": 0, "at": 1, "chars": 20, "sha": "aaaaaaaaaaaa"},
        {"stream": 0, "at": 2, "chars": 40, "sha": "bbbbbbbbbbbb"},
        {"stream": 1, "at": 1, "chars": 40, "sha": "bbbbbbbbbbbb"},
    ])
    assert audit.cross_stream_repeat_frames(re_send) == 1
    assert audit.recomputed_ledger(re_send) is False


def test_b8_arrival_less_ledger_reports_unmeasurable_not_a_clean_schedule():
    """缺逐帧到达坐标的账（run6/run7 那一形）必须整行 ``unmeasurable``，不许读成「合格」。

    计划书 :87 那条「≥20 字或 100 ms 合并 / 禁单字碎片」需要逐帧 ``chars``/``elapsed_ms``；
    读数件 §3 那三个「量不到」的窗全靠这一格才没被写成已验。
    """
    legacy = full_row()
    legacy.pop("frames")

    check = audit.schedule_check(legacy)

    assert check["status"] == "unmeasurable"
    assert check["frame_count_with_arrival"] == 0
    assert check["single_char_fragments"] is None, "不许报 0 枚碎片冒充量过"
    assert check["min_increment_chars"] is None
    assert check["max_gap_ms"] is None
    assert audit.summarize([audit.judge_row(legacy)])["schedule_measurable_rows"] == 0
def test_b6b_the_blind_instrument_shape_today_reads_zero_not_none():
    """🔴 缺口现状钉（R506 读数件 §5 第 5 条）：``frames`` 列在、逐帧却一枚指纹都不带那一形，
    判器今天读 **0**（读作「量过了，没重合」），而它的 docstring 承诺的是回 ``None``（没量过）。

    承诺写在 ``scripts/r239_stream_gap_offline_audit.py:147-150`` 那段 docstring（「或有这一列却
    一枚逐帧指纹都不带 ⇒ 回 ``None``」），落码在 :153-167：只有「``frames`` 不是列表 / 是空列表」
    才 ``return None``，循环里 ``if not sha: continue`` 把没指纹的帧直接跳过，末尾交回 ``repeats``。
    后果：那一形会**通过**第七枚合取（``recomputed_ledger`` 里 ``in (None, 0)`` 两值都算过），
    与 :149 那句「不许报 0 冒充量过」相反。run9 没吃到它 —— ``metric-02``/``scope-02`` 交回的是
    **空列表**（``None``），所以 ``重合量不出=2`` 今天是对的；但「量具被摘瞎」那一窗会读成一片绿。

    判器是禁改件，所以这里只把**今天真实读回的数字**钉住，并把矛盾摆到明面。谁改了判器让
    它按 docstring 交回 ``None``，这枚钉会当场红 —— 那是它该有的反应：逼着纸与尺一起改。
    """
    blind = full_row(frames=[{"stream": 0, "at": 1, "chars": 20, "elapsed_ms": 12.0},
                             {"stream": 0, "at": 2, "chars": 40, "elapsed_ms": 40.0}])

    assert audit.cross_stream_repeat_frames(blind) == 0, "现状：无指纹那一形读 0，不读 None"
    assert audit.recomputed_ledger(blind) is True, "后果：第七枚合取放它过去了"
    assert audit.summarize([audit.judge_row(blind)])["cross_stream_repeat_unmeasurable"] == 0