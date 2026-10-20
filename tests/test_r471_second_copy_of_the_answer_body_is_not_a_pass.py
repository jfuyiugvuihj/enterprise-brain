# -*- coding: utf-8 -*-
"""R471 判据①③④：正文在同一轮里出现两遍，判据② 那把尺不许读绿（丙案形态）。

病（本单唯一的对象是**尺子**，不是读数，更不是产品）：``_frame_verdict`` 原来只合取六枚 ——
``text_frames > 1`` / ``max_stream_frames > 1`` / ``uncorrected_breaks == 0`` /
``missing_chars == 0`` / ``extra_chars == 0`` / ``last_frame_covers_answer``。批准腿把挂起轮
已经交上屏的那份正文**又发一遍**时，``_fold_frames`` 的前缀单调只在同一条流内判，那一形常常
连一枚坏形都不长，于是六枚全过、屏上摆着两份答案。R215 那枚豁免对此无从下手：它对的是「坏形」，
而这一形的 ``uncorrected_breaks`` 本来就是 0（台账里「verdict 计算写在 chat.py」那句是过期坐标，
作废 —— 算式全在本件加载的这把尺里）。

今天合取里加第七枚 ``cross_stream_repeat_frames == 0``。**丙案（总控 09-29 裁定一）**：这一枚
证词**不落成帧账的新列** —— 帧账一行的键集是四枚在册钉「对判，不是子集」的闸，不许为一枚派生数
去开列；证词由 ``_record_frames`` 在判定那一刻从**行内既有那一列 R223 逐帧指纹**（``frames``）
现场派生，离线复算那一路（``scripts/r239_stream_gap_offline_audit.py`` 与
``scripts/eval_frame_caliber_readout.py``）同样现场派生。本件因此两头都钉：🔴 尺子有牙，且
🔴 账上多不出格子（见 ``test_the_frame_row_gains_no_column_for_the_new_conjunct``）。

三条边界，都是故意的，不许顺手放宽：
  * 🔴 只算跨流。**总控裁定（2026-09-29，署名总控）原话**：「同一条流内末片帧与收尾帧同文」
    不判成「出现两遍」：R215 那四条例外（末帧／本轮至多一枚／紧邻 arm／逐字等于终答）裁的就是
    这一形，收它等于推翻在册裁定；且 A② 要治的是缺字与断流，跨流重复才是 R464 治的批准腿病形。
    见 ``test_an_identical_closing_frame_in_one_leg_stays_a_pass``：run9 那 105 行里 66 行带这一形、
    其中 64 行在册读绿，一起定罪是误伤。
  * 🔴 不拿 ``text_frames > max_stream_frames`` 当尺：run9 那 18 枚换源形里只有 3 枚真重合，其余
    15 枚交的是新字。见 ``test_the_coincidence_is_the_witness_not_the_frame_counts``。
  * 🔴 老账（run2→run9）递不进这枚证词 ⇒ 在册尺**不重判**当年读数，也不 KeyError。
    见 ``test_the_ruler_does_not_rejudge_a_ledger_that_carries_no_witness``。

全程离线：合成 SSE 字节喂量具**真收端**（``_consume`` / ``_count_text_frame`` / ``_fold_frames`` /
``_cross_stream_repeats`` / ``_frame_readings`` / ``_frame_verdict``）与**真落盘**
（``_record_frames``），importlib 单独加载。不打模型、不起服务、不动容器、不写仓内产物。
"""

import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r471_second_copy_ruler", REPO_ROOT / "scripts" / "eval_transport_ask_v2.py")
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

_AUDIT_SPEC = importlib.util.spec_from_file_location(
    "r471_second_copy_audit", REPO_ROOT / "scripts" / "r239_stream_gap_offline_audit.py")
audit = importlib.util.module_from_spec(_AUDIT_SPEC)
_AUDIT_SPEC.loader.exec_module(audit)

#: 只读原件：09-28 那一窗的帧账与更早的 run7 窗，本件一个字都不写它们。
RUN9_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
RUN7_FRAMES = REPO_ROOT / "docs" / "testing" / "sidecar-run7-frames.jsonl"
EVAL_SET = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
R215_FILE = REPO_ROOT / "tests" / "test_r215_recognizing_a_controlled_correction.py"
RULER_FILE = REPO_ROOT / "scripts" / "eval_transport_ask_v2.py"

P1 = "一线城市住宿费为每晚 500 元"
BODY = "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销"
OTHER_SOURCE = "另一条来源写出来的半截话，和刚才那份正文没有一个字相同"
NEW_BODY = "住宿费上限按城市分档：一线每晚 500 元、二线每晚 400 元，凭发票报销"

#: 第七枚合取那枚证词的名字。🔴 它是**判定视图里的派生读数**，不是帧账的一格。
CELL = "cross_stream_repeat_frames"


def _lines(events):
    """把 ``(事件名, 载荷)`` 编成 SSE 字节行 —— 服务端就是这么写的（与 R215 同一编法）。"""
    lines = []
    for name, payload in events:
        lines.append(("event: " + name).encode("utf-8") + b"\n")
        lines.append(("data: " + json.dumps(payload, ensure_ascii=False)).encode("utf-8") + b"\n")
        lines.append(b"\n")
    return lines


def _text(content):
    return ("text", {"type": "text", "content": content})


def _arm():
    """R210 那枚「武装整段替换」的 step：豁免判据③ 认的就是这一枚脸。"""
    return ("step", {"type": "step", "tool": ruler.CORRECTION_STEP_TOOL,
                     "label": "🔁 换源重发本轮回答", "status": "running"})


def _fold(streams):
    """几条流折成一题的账（走真收端），连同「交回评分器的那份字」一起交回。"""
    ledger = ruler._new_frame_ledger()
    delivered = ""
    for events in streams:
        out = ruler._blank_observation("sess-r471")
        ruler._consume(_lines(list(events)), out)
        if out["answer"]:
            delivered = out["answer"]
        ruler._fold_frames(ledger, out)
    return ledger, delivered


def _clean(row):
    """去掉本件自己加的定位键，交回一份纯帧账行（复算件读的就是这一份）。"""
    return {key: value for key, value in row.items() if key != "_row_id"}


def _row(tmp_path, monkeypatch, streams, row_id="r471-01"):
    """走**真落盘**造一行帧账：``criterion_two_holds`` 由 ``_record_frames`` 当场判出来。

    🔴 本件不自己拼判定视图 —— 丙案的牙就长在落盘那一只手（判定那一刻从行内既有那一列逐帧
    指纹现场派生证词，不落成新列），所以一切红绿都在账上验，不在测试里复算。
    """
    ledger, delivered = _fold(streams)
    assert delivered, "合成流没被真收端读出终答：红色不算判出来的"
    target = tmp_path / (row_id + ".jsonl")
    monkeypatch.setenv("EVAL_FRAME_LEDGER", str(target))
    ruler._record_frames(row_id, "approved_ok", 1, "sess-r471", ledger, delivered, "")
    row = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    row["_row_id"] = row_id
    return row


def _derived(row):
    """从行内既有那一列 R223 逐帧指纹现场派生第七枚证词（尺子与复算件同一条口径）。"""
    return ruler._cross_stream_repeats(row["frames"])


def _old_six_hold(row):
    """R471 之前那六枚合取在这行账上全绿 —— 是的话，否掉它的只可能是新加那一腿。

    🔴 这里只把在册尺**已经在读**的那几格摊开对判，不复制第二把尺：判绿与否仍由
    ``_frame_verdict`` 自己说，这一枚只回答「旧口径看不看得见这一形」。
    """
    return bool(row["text_frames"] > 1
                and row["max_stream_frames"] > 1
                and row["uncorrected_breaks"] == 0
                and row["missing_chars"] == 0
                and row["extra_chars"] == 0
                and row["last_frame_covers_answer"] is True)


def _twins(tail):
    """本件那对孪生夹具：挂起轮逐片把正文铺到屏上，批准腿收尾交 ``tail`` 这一枚字。

    ``tail == BODY`` ⇒ 同一轮里正文出现两遍；``tail == NEW_BODY`` ⇒ 只换字不重发。
    两形其余每一格都造得一样，所以红绿只可能来自重合那一格。
    """
    return [[_text(P1), _text(BODY)], [_text(tail)]]


def _non_empty_shas(row):
    """把在册帧账里那串逐帧指纹摊开计数 —— 证据算术，不是第二把尺（判绿仍由尺子自己说）。"""
    return [str(item.get("sha") or "") for item in (row.get("frames") or [])
            if int(item.get("chars") or 0) > 0]



# ==================== 判据①：疾病形读 False，孪生形读 True ====================


def test_a_second_copy_of_the_body_in_the_same_round_is_not_a_pass(tmp_path, monkeypatch):
    """疾病形：批准腿收尾把已经上屏的那份正文又发一遍，且**一枚坏形都不长** ⇒ 落盘读 False。"""
    row = _row(tmp_path, monkeypatch, _twins(BODY))

    assert row["text_frames"] == 3 and row["max_stream_frames"] == 2, row
    assert row["prefix_breaks"] == 0, row          # 重发在原始账上不留痕，豁免根本没出场
    assert _old_six_hold(row) is True, row         # 旧六枚全过 ⇒ 这就是那格洞
    assert _derived(row) == 1, row                 # 第七枚证词：跨流重合一枚
    assert row["criterion_two_holds"] is False, row


def test_the_same_fixture_that_only_switches_source_is_still_a_pass(tmp_path, monkeypatch):
    """判据① 的另一形：只换字不重发 ⇒ 必须仍读绿（把它一起改严就是方向错了）。"""
    row = _row(tmp_path, monkeypatch, _twins(NEW_BODY))

    assert _old_six_hold(row) is True, row
    assert _derived(row) == 0, row
    assert row["criterion_two_holds"] is True, row


# ==================== 病根那一格：豁免被拿去掩护重发 ====================


def test_the_armed_replacement_that_re_sends_the_body_is_not_a_pass(tmp_path, monkeypatch):
    """R215 四条全中的那一形被用来重发正文：``uncorrected_breaks`` 仍是 0，绿却不该给。"""
    row = _row(tmp_path, monkeypatch, [[_text(P1), _text(BODY)],
                                       [_text(OTHER_SOURCE), _arm(), _text(BODY)]])

    assert row["prefix_breaks"] == 1, row
    assert row["corrective_replacements"] == 1, row    # 豁免照旧生效（原始账一字不漂）
    assert row["uncorrected_breaks"] == 0, row
    assert _old_six_hold(row) is True, row
    assert _derived(row) == 1, row
    assert row["criterion_two_holds"] is False, row


def test_an_armed_source_switch_to_new_text_keeps_the_r215_green(tmp_path, monkeypatch):
    """同一副夹具只把收尾那份字换成**新**的：R215 那枚受控纠正一枚不许误伤。"""
    row = _row(tmp_path, monkeypatch, [[_text(P1), _text(BODY)],
                                       [_text(OTHER_SOURCE), _arm(), _text(NEW_BODY)]])

    assert row["prefix_breaks"] == 1, row
    assert row["corrective_replacements"] == 1, row
    assert row["uncorrected_breaks"] == 0, row
    assert _derived(row) == 0, row
    assert row["criterion_two_holds"] is True, row


# ============ 边界（总控裁定二）：只在「跨流」这一侧加腿，同流同文不算两遍 ============


def test_an_identical_closing_frame_in_one_leg_stays_a_pass(tmp_path, monkeypatch):
    """同一条流里末片帧与收尾帧同文 = 既有合法形状（covering ⇒ 屏上始终只有一份正文）。

    🔴 署名总控裁定（2026-09-29）原话：「同一条流内末片帧与收尾帧同文」不判成「出现两遍」：
    R215 那四条例外（末帧／本轮至多一枚／紧邻 arm／逐字等于终答）裁的就是这一形，收它等于
    推翻在册裁定；且 A② 要治的是缺字与断流，跨流重复才是 R464 治的批准腿病形。
    这一枚就是本单选边的凭据：run9 那 105 行里 66 行带这一形、其中 64 行在册读绿 —— 一刀砍
    下去就把阶段 A 判据② 整格判死，那不是治尺。
    """
    row = _row(tmp_path, monkeypatch, [[_text(P1), _text(BODY), _arm(), _text(BODY)]])

    assert row["streams"] == 1, row
    assert _derived(row) == 0, row
    assert row["criterion_two_holds"] is True, row


def test_an_empty_frame_carries_no_body_so_it_cannot_be_a_second_copy(tmp_path, monkeypatch):
    """口径钉：``chars == 0`` 的帧不携带正文，谈不上出现两遍，不参与重合。

    反证落点写在这里：摘掉这道 skip，两枚同文的**空帧**就会被算成一次重复送达 —— 而屏上那
    两枚一个字节都没有多出来。对照同时给出计数的读法：后一条流把同一份正文发几枚就记几枚，
    这一枚是枚数不是布尔，红的时候要说得出重了几遍。
    """
    blanks = _row(tmp_path, monkeypatch, [[_text(P1), _text("")], [_text(""), _text(NEW_BODY)]],
                  row_id="r471-blank")
    copies = _row(tmp_path, monkeypatch, [[_text(P1), _text(BODY)], [_text(BODY), _text(BODY)]],
                  row_id="r471-twice")

    assert _derived(blanks) == 0, blanks        # 空帧同文：屏上没多出正文，不算重复送达
    assert _derived(copies) == 2, copies        # 后一条流发了两枚同文正文 ⇒ 记两枚
    assert copies["criterion_two_holds"] is False, copies


# ==================== 丙案：尺子有牙，账上多不出格子 ====================


def test_the_frame_row_gains_no_column_for_the_new_conjunct(tmp_path, monkeypatch):
    """丙案自证（总控 09-29 裁定一）：新口径**不给帧账添一列**，牙照样咬得住疾病形。

    名单不在本件里抄第二份（那四枚在册钉才是名单）：期望键集由**尺子自己交回的两层读数**
    现算 —— ``_frame_readings`` 的形状 + ``_arrival_readings`` 的形状 + join 键 + 判定那一格。
    🔴 这一枚就是「回不到 217 就说明还留着落盘列」那格验收的机读版本。
    """
    ledger, delivered = _fold(_twins(BODY))
    expected = ({"id", "kind", "attempt", "sentinel", "session_id", "ts", "criterion_two_holds"}
                | set(ruler._frame_readings(ledger, delivered))
                | set(ruler._arrival_readings(ledger)))
    row = _row(tmp_path, monkeypatch, _twins(BODY), row_id="r471-keys")

    assert CELL not in row, sorted(row)
    assert set(_clean(row)) == expected, (sorted(set(_clean(row)) - expected),
                                          sorted(expected - set(_clean(row))))
    assert row["criterion_two_holds"] is False, row    # 不添一格，疾病形照样读 False


def test_the_live_ruler_and_the_offline_audit_agree_on_the_new_conjunct(tmp_path, monkeypatch):
    """「账与尺同代」的自证：真尺刚写出来的行，复算件必须一格不漂（疾病行与孪生绿行都算）。

    复算件补的是第七枚合取的**派生复算**（帧账里没有那一格），所以它对同代账的判据是：
    派生出的证词与尺子读到的同值，且 ``recomputed_ledger`` 与账上那枚 ``criterion_two_holds``
    逐行相等 ⇒ ``ledger_drift`` 为空。漂了就是账与尺不同代，当场点名而不是替它改写。
    """
    rows = [_row(tmp_path, monkeypatch, _twins(BODY), row_id="r471-same-disease"),
            _row(tmp_path, monkeypatch, _twins(NEW_BODY), row_id="r471-same-green")]

    judged = [audit.judge_row(_clean(row)) for row in rows]
    for row, item in zip(rows, judged):
        assert item["cross_stream_repeat_frames"] == _derived(row), item
        assert item["recomputed_ledger"] is row["criterion_two_holds"], (item, row)
        assert item["ledger_drift"] is False, item
    assert [item["ledger_criterion_two_holds"] for item in judged] == [False, True], judged
    assert audit.summarize(judged)["cross_stream_repeat_ids"] == ["r471-same-disease"]


def test_the_offline_audit_cannot_rejudge_a_window_without_fingerprints():
    """run7 那扇窗（R223 并树之前）连逐帧指纹都没有 ⇒ 复算件派生不出，当年的读数不重判。

    这一枚同时钉住两件事：派生不出要照实回 ``None``（不许报 0 冒充量过），以及那 105 行
    ``ledger_drift`` 仍为空 —— 补上第七枚合取之后的复算件，对老账**一个字节都没改判**。
    """
    rows = [json.loads(line) for line in
            RUN7_FRAMES.read_text(encoding="utf-8").splitlines() if line.strip()]
    judged = [audit.judge_row(row) for row in rows]
    summary = audit.summarize(judged)

    assert len(rows) == 105, len(rows)
    assert all(item["cross_stream_repeat_frames"] is None for item in judged)
    # 有 ``frames`` 那一列却一枚指纹都不带（量具被摘瞎那一形）同样算量不到，不许读成「量过且为 0」
    assert audit.cross_stream_repeat_frames({"frames": []}) is None
    assert audit.cross_stream_repeat_frames({}) is None
    assert summary["cross_stream_repeat_unmeasurable"] == 105, summary
    assert summary["cross_stream_repeat_ids"] == [], summary
    assert summary["ledger_drift"] == [], summary["ledger_drift"]


# ==================== 反证两把刀（各咬一格，照改后终态重挥）====================


def test_knife_one_blinding_the_new_reading_leaves_the_disease_green(tmp_path, monkeypatch):
    """刀一：摘掉新加那一格的**读数**（不是摘断言），疾病形必须立刻读回绿。

    同一副夹具、同一条落盘路、同一组断言，只把派生器归零就翻绿 ⇒ 定罪确实来自这一格；
    本件没有靠删断言制造红绿（事故 #83 那一族空转的牙就是这么造出来的）。
    """
    row = _row(tmp_path, monkeypatch, _twins(BODY), row_id="r471-knife1")
    assert row["criterion_two_holds"] is False, row

    monkeypatch.setattr(ruler, "_cross_stream_repeats", lambda records: 0)
    blinded = _row(tmp_path, monkeypatch, _twins(BODY), row_id="r471-knife1-blind")
    assert _derived(blinded) == 0, blinded
    assert blinded["criterion_two_holds"] is True, blinded      # 摘掉牙 ⇒ 洞回来了


def test_knife_two_degrades_the_fixture_without_touching_any_assertion(tmp_path, monkeypatch):
    """刀二：疾病形退化成「只换字不重发」，同一组断言原样跑 ⇒ 必须绿。

    🔴 两形之间只许差一枚事实。这里逐格对判：帧数、流数、坏形、豁免、缺字、多字、末帧覆盖
    全同，只有重合那一枚证词与落盘判定该变 —— 谁想让它绿，除了重发之外没有第二条路。
    """
    disease = _row(tmp_path, monkeypatch, _twins(BODY), row_id="r471-disease")
    healthy = _row(tmp_path, monkeypatch, _twins(NEW_BODY), row_id="r471-healthy")
    same_cells = ("text_frames", "max_stream_frames", "streams", "prefix_breaks",
                  "corrective_replacements", "uncorrected_breaks", "missing_chars",
                  "extra_chars", "last_frame_covers_answer")
    for cell in same_cells:
        assert disease[cell] == healthy[cell], (cell, disease[cell], healthy[cell])
    assert (_derived(disease), _derived(healthy)) == (1, 0), (disease, healthy)
    assert disease["criterion_two_holds"] is False
    assert healthy["criterion_two_holds"] is True


# ==================== 判据④：影响面与「不重判」都要有数 ====================


def _rows(path):
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_the_ruler_does_not_rejudge_a_ledger_that_carries_no_witness():
    """R471 之前的帧账递不进这枚证词：复算不许 KeyError，也不许事后追加定罪。

    纪律与 ``scripts/r239_stream_gap_offline_audit.py`` 拿老账退回 ``prefix_breaks`` 同一条：
    读不到证词就照当年的读数交回，既不洗白当年的红字，也不替当年的绿字补一枚新罪 —— 否则
    阶段 A 判据② 那格「从没宣布验过」会被本单偷偷验成两副样子。🔴 递进证词才定罪：本枚同时
    给出「把同一份行内指纹派生成证词递进去」的对照，读回 False，证明不重判是**缺证词**、
    不是尺子在看别处。
    """
    rows = {row["id"]: row for row in _rows(RUN9_FRAMES)}

    for row_id in ("chart-04", "insight-07", "tool-04", "doc-01"):
        row = rows[row_id]
        assert CELL not in row, row_id                       # 丙案：这一格从来不在账上
        assert ruler._frame_verdict(row) is row["criterion_two_holds"], row_id
        # 递进证词 ⇒ 同一行立刻换脸：不重判是因为**缺证词**，不是尺子在看别处
        assert ruler._frame_verdict(dict(row, **{CELL: 1})) is False, row_id


def test_the_coincidence_is_the_witness_not_the_frame_counts():
    """逐档影响面（拿行内逐帧指纹复算 run9 那 105 行）+ 一枚反证：不许拿枚数当尺。

    翻脸的只有指纹重合那几枚；如果改用 ``text_frames > max_stream_frames`` 当尺，同一份账上
    要多定罪 15 枚正常换源（后一条流交的是新字）—— 这就是本单选「重合」不选「枚数」的理由。
    """
    tiers = {row["id"]: row["tier"] for row in _rows(EVAL_SET)}
    coincidence, source_switch_only = [], []
    for row in _rows(RUN9_FRAMES):
        records = row.get("frames") or []
        if not records:
            continue                                  # 空读那一行没有逐帧指纹可量
        repeats = ruler._cross_stream_repeats(records)
        if repeats:
            coincidence.append((row["id"], tiers[row["id"]], row["criterion_two_holds"]))
        elif row["text_frames"] > row["max_stream_frames"]:
            source_switch_only.append(row["id"])

    assert sorted(item[0] for item in coincidence) == [
        "chart-04", "insight-07", "tool-04"], coincidence
    assert len(source_switch_only) == 15, sorted(source_switch_only)
    # 三枚里只有两枚当年读绿（tool-04 本来就因真断流读红）⇒ 若重判：问答 0／分析 2／报告 0
    flips = {tier: sum(1 for _i, t, held in coincidence if t == tier and held is True)
             for tier in ("问答", "分析", "报告")}
    assert flips == {"问答": 0, "分析": 2, "报告": 0}, (flips, coincidence)
    assert sorted(i for i, _t, held in coincidence if held is True) == ["chart-04", "insight-07"]


def test_the_boundary_is_pinned_against_the_recorded_window():
    """这一枚把「只算跨流」钉在真证据上：同流同文是普遍形状，跨流重合只有三枚。

    一刀把同一条流里的同文帧一起定罪，run9 这 105 行要多死 64 枚在册绿 —— 那不是治尺，是把
    阶段 A 判据② 整格判死。本单选的是病历点名的那一格（**逐帧指纹重合**），不是枚数。
    """
    rows = [row for row in _rows(RUN9_FRAMES) if (row.get("frames") or [])]
    same_leg = [row for row in rows
                if len(_non_empty_shas(row)) > len(set(_non_empty_shas(row)))]
    cross = [row for row in rows if ruler._cross_stream_repeats(row["frames"]) > 0]

    assert len(same_leg) == 66, len(same_leg)
    assert sum(1 for row in same_leg if row["criterion_two_holds"] is True) == 64
    assert sorted(row["id"] for row in cross) == ["chart-04", "insight-07", "tool-04"]
    assert sum(1 for row in cross if row["criterion_two_holds"] is True) == 2


# ============ 判据②：R215 那三枚在册钉一枚没被磨钝（且落盘调用式没挪窝）============


def test_the_three_registered_r215_green_pins_are_still_there():
    """R215 件里那三枚「判绿」断言原样在盘上，本单一枚没改宽。

    凭据两枚：这一枚数表达式（磁盘上的 R215 源文），加上交回里那条形如
    ``git diff d8fca78 -- tests`` 的取证 —— 本单只动过
    ``tests/test_r218_ruler_self_calibration.py`` 的 ``verdict_key_set`` 名单一处（返工令第 2 项）。
    """
    source = R215_FILE.read_text(encoding="utf-8")
    greens = re.findall(r"assert ruler\._frame_verdict\([^)]*\) is True", source)

    assert len(greens) == 3, greens
    assert "def test_" in source and "uncorrected_breaks" in source


def test_the_exemption_four_criteria_and_the_verdict_call_site_are_untouched():
    """R215 那四条豁免判据与 ``_record_frames`` 里那行调用式都还在原位。

    🔴 丙案不许为了翻绿去动别人的牙，也不许把判定那一只手挪到别处藏起来：豁免四条原样在
    ``_corrective_readings`` 的口径纸上，落盘那一行仍写着 ``_frame_verdict(readings)``；
    新口径只多它上面那一行派生。
    """
    doc = ruler._corrective_readings.__doc__ or ""
    for marker in ("①", "②", "③", "④"):
        assert marker in doc, marker
    ruler_source = RULER_FILE.read_text(encoding="utf-8")
    needle = 'row["criterion_two_holds"] = _frame_verdict(readings)'
    assert needle in ruler_source, "判定那一行的调用式被挪走了：丙案不改这一行"
    # 🔴 丙案的牙长在哪一只手：落盘那一层把行内逐帧指纹派生成证词，判定视图里才有这一格。
    injection = ("readings[" + chr(34) + CELL + chr(34) + "] = "                 "_cross_stream_repeats(arrivals[" + chr(34) + "frames" + chr(34) + "])")
    assert injection in ruler_source, "落盘那一只手没把证词派生给尺子：丙案的牙就在这一行"
    assert "row.update(arrivals)" in ruler_source and "row.update(readings)" in ruler_source
    # 账上不许出现这一格（四枚「键集是对判」的在册钉之外的第二枚闸）
    assert ruler.REPEAT_DELIVERY_UNMEASURED == 0
    assert ruler._cross_stream_repeats([]) == 0
