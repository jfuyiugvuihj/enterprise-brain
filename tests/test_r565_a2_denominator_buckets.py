# -*- coding: utf-8 -*-
"""R565 常驻钉 —— 钉住「A② 分母拆桶」这把量具的形状，不钉任何一枚数的大小。

三格正判据（指派原文）：
① 四桶互斥且并集恰为整窗（``test_buckets_are_exclusive_and_conserve_the_whole_window``）；
② B3 不许被并进 B0（``test_b3_prefab_rows_are_never_folded_into_b0`` 与其反证
   ``test_counter_evidence_a_blinding_the_prefab_set_folds_the_two_canned_rows_into_b0``）；
③ 拿丙口径宣布 A② 翻绿必须当场红（``test_caliber_c_denies_itself_the_green_claim``）。

钉的都是形状，不是数字：
* 甲口径的绿数**必须等于在册判器自己算出来的那枚**（``test_the_literal_caliber_is_r239s_own_read``），
  所以本件不许另起一把尺，也不许把「94」这类纸上的数抄进断言；
* 尺寸闸与预制串一律现取：把真源换一枚影子件，桶必须跟着动
  （``test_counter_evidence_b_the_size_gate_is_read_live`` /
   ``test_counter_evidence_a_...``）；
* 短指纹口径漂移 ⇒ 拒绝出数，不是少归几枚（``test_counter_evidence_c_fingerprint_drift_is_refused``）。

反证牙清单（在册 ``counter_evidence`` 命名法；一枚都不分层出门）：
  a 预制集合致盲 ⇒ 那两枚占位串被并进 B0；
  b 尺寸闸改档 ⇒ B1 枚数跟着动，真源缺那行 ⇒ 直接抛；
  c 指纹漂移 ⇒ ``FingerprintDriftError``；
  d 同毫秒那一半摘掉 ⇒ 单帧题不再进 B2；
  e ``tool_calls`` 缺键 ⇒ 不许当成 0（不进 B1 且被点名）；
  f 分母对账不上 ⇒ rc=2 并点名，不静默按小窗出数；
  g 本件零降级记号（无 skip / skipif / xfail / only）。
"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r565_a2_denominator_buckets", REPO_ROOT / "scripts" / "r565_a2_denominator_buckets.py")
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

#: 在册两窗：run9（② 的在册读数出处）与 run11c（哨兵串与天然短同时在场的那一窗）。
LEDGERS = {
    "run9": ("docs/testing/sidecar-run9-frames.jsonl",
             "docs/testing/sidecar-run9.jsonl",
             "docs/testing/answers-run9.jsonl"),
    "run11c": ("docs/perf/raw/run11c-2026-10-01/sidecar-run11c-frames.jsonl",
               "docs/perf/raw/run11c-2026-10-01/sidecar-run11c.jsonl",
               "docs/perf/raw/run11c-2026-10-01/answers-run11c.jsonl"),
}
P2_WINDOW = ("docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2-frames.jsonl",
             "docs/perf/raw/run11c-2026-10-01/sidecar-run11c-p2.jsonl",
             "docs/perf/raw/run11c-2026-10-01/answers-run11c-p2.jsonl")

_CACHE = {}


def ledger_paths(run):
    return tuple(REPO_ROOT / name for name in LEDGERS[run])


def read(run="run9", **over):
    """把某一窗的三本账跑一遍（同一次 pytest 内复用；影子件走 over，不动仓内账）。"""
    if not over and run in _CACHE:
        return _CACHE[run]
    frames, sidecar, answers = ledger_paths(run)
    result = mod.read_round(frames=over.get("frames", frames),
                            sidecar=over.get("sidecar", sidecar),
                            answers=over.get("answers", answers),
                            nodes_source=over.get("nodes_source"),
                            chat_source=over.get("chat_source", mod.CHAT_SOURCE),
                            harness_source=over.get("harness_source", mod.HARNESS_SOURCE))
    if not over:
        _CACHE[run] = result
    return result


def bucket_of(result, row_id):
    for item in result["rows"]:
        if item["id"] == row_id:
            return item["bucket"]
    raise AssertionError("账上没有这一题：" + row_id)


def entry_of(result, row_id):
    for item in result["rows"]:
        if item["id"] == row_id:
            return item
    raise AssertionError("账上没有这一题：" + row_id)


def rewrite_jsonl(source, target, mutate):
    """把一本 jsonl 按行改写进影子件（只写 tmp_path，仓内一个字节不动）。"""
    lines = []
    with io.open(str(source), encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            mutated = mutate(row)
            if mutated is not None:
                lines.append(json.dumps(mutated, ensure_ascii=False))
    Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(target)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def run9():
    return read("run9")


@pytest.fixture(scope="session")
def run11c():
    return read("run11c")
# ============================ 一、正控：三格形状 ============================

def test_the_two_in_book_windows_are_the_ones_this_ticket_read():
    for run in LEDGERS:
        for path in ledger_paths(run):
            assert path.is_file(), run + " 的账读不到：" + str(path)
    assert len(read("run9")["rows"]) == mod.DENOMINATOR_IN_BOOK
    assert len(read("run11c")["rows"]) == mod.DENOMINATOR_IN_BOOK


def test_buckets_are_exclusive_and_conserve_the_whole_window(run9):
    """① 每枚题恰落一桶，四桶合计恰为整窗 105 枚，一枚都不许既在又不在。"""
    rows = run9["rows"]
    assert len(rows) == 105
    assert sum(run9["bucket_counts"].values()) == 105
    for item in rows:
        assert item["bucket"] in mod.BUCKET_ORDER, item["id"]
        assert set(item["also_matched"]) <= set([mod.B1, mod.B2, mod.B3]), item["id"]
        assert len(set(item["also_matched"])) == len(item["also_matched"]), item["id"]
        if item["bucket"] == mod.B0:
            assert item["also_matched"] == [], item["id"] + " 落 B0 却还命中着某一格"
        else:
            assert item["bucket"] in item["also_matched"], item["id"] + " 归账没归进命中过的那格"


def test_the_literal_caliber_is_r239s_own_read(run9):
    """甲口径的绿数必须等于在册判器自己算出来的那枚 —— 本件不许另起一把尺，也不许抄纸上的数。"""
    frames, _sidecar, _answers = ledger_paths("run9")
    rows = mod.audit.read_rows(frames)
    literal = mod.audit.summarize([mod.audit.judge_row(row) for row in rows])
    cell = run9["calibers"]["甲"]
    assert cell["green"] == literal["criterion_two_holds_literal"]
    assert cell["red"] == literal["criterion_two_fails_literal"]
    assert cell["denominator"] == literal["rows"] == 105


def test_caliber_c_denies_itself_the_green_claim(run9):
    """③ 拿丙口径宣布 A② 翻绿 ⇒ 当场红（拒绝），且拒绝的话里逐格点名 B1/B2/B3。"""
    cell_a = run9["calibers"]["甲"]
    cell_c = run9["calibers"]["丙"]
    # 只押结构，不押未验的经验预测：②-a = ``text_frames > 1`` ⇒ tf<=1 的每一枚必红；
    # 「换小分母」从甲口径里究竟拿走几枚真红，由 hidden 逐格加出来，两边必须守恒。
    low_frames = [item for item in run9["rows"] if item["text_frames"] <= 1]
    assert low_frames, "run9 读不到 text_frames<=1 的题：②-a 的形状变了，本钉要重写"
    assert all(not item["verdict"] for item in low_frames), (
        "②-a=text_frames>1 应让 tf<=1 全红，如今读不出红 ⇒ 判器与本钉不同代，重新取证")
    assert cell_a["red"] >= len(low_frames) > 0, "甲口径没有可滥用的红：本钉的前提变了"
    hidden = sum(run9["calibers"]["乙"]["excluded_cells"][name]["red"]
                 for name in (mod.B1, mod.B2, mod.B3))
    assert cell_a["red"] == cell_c["red"] + hidden, (
        "甲红 != 丙红 + 三格红 ⇒ 分桶与甲口径读的不是同一批题，守恒破了")
    assert hidden > 0, "三格里一枚红都没有 ⇒ 这一窗不存在「拿小分母洗红」的形状，本钉要重写"
    with pytest.raises(mod.CaliberError) as refused:
        mod.declare(run9, "丙", green=True)
    message = str(refused.value)
    assert "丙口径" in message and "B1=" in message and "B2=" in message and "B3=" in message
    assert "不许据它宣布" in message


def test_caliber_b_is_only_legal_with_the_three_cells_disclosed(run9):
    with pytest.raises(mod.CaliberError) as refused:
        mod.declare(run9, "乙", green=True, disclosed=False)
    assert "乙口径的三格" in str(refused.value)
    # 只报数不报格时，这枚宣布当场拒；报数本身不受影响。
    assert mod.declare(run9, "乙", green=False).startswith("乙")


def test_caliber_c_reports_the_same_numbers_as_b_but_holds_nothing_back(run9):
    """丙与乙的分母/绿数逐枚相等（差别只在披露），🔴 所以「丙更乐观」不是另算出来的。"""
    cell_b = run9["calibers"]["乙"]
    cell_c = run9["calibers"]["丙"]
    assert (cell_b["denominator"], cell_b["green"], cell_b["red"]) == (
        cell_c["denominator"], cell_c["green"], cell_c["red"])
    assert "excluded_cells" not in cell_c
    assert cell_c["discloses_excluded_cells"] is False
    assert set(cell_b["excluded_cells"]) == set([mod.B1, mod.B2, mod.B3])

# ============================ 二、四桶各自的正面形状 ============================

def prefab_texts():
    """现取的预制串全文（逐枚）：``failure_text`` 那一枚 + 采集器两枚哨兵默认字面。"""
    return list(mod.chat_prefab_texts()) + list(mod.harness_sentinel_texts().values())


def test_b3_prefab_rows_are_never_folded_into_b0(run9, run11c):
    """② 终答逐字等于现取预制串的每一枚，必须落 B3；一枚都不许滑进 B0（分母）。"""
    texts = prefab_texts()
    assert texts
    for run, result in (("run9", run9), ("run11c", run11c)):
        _frames, _sidecar, answers = ledger_paths(run)
        book, _collapsed = mod.lane.rows_by_id(answers)
        canned = set()
        for key, row in book.items():
            answer = row.get("answer")
            if isinstance(answer, str) and any(answer == text for text in texts):
                canned.add(key)
        assert canned, run + " 这一窗逐字读不到任何预制句：本钉的前提变了，重新取证，不许默默放行"
        for key in canned:
            assert bucket_of(result, key) == mod.B3, (
                run + "/" + key + " 的预制句被并进了 " + bucket_of(result, key) + "：分母被偷大")
        assert set(item["id"] for item in result["rows"]
                   if item["bucket"] == mod.B3) == canned
        assert result["bucket_counts"][mod.B3] == len(canned)


def test_b3_wins_the_row_yet_b2_stays_written_down(run11c):
    """呈现优先级 B3>B2 只改归账，不改证词：那一枚同时命中两格的题，``also_matched`` 必须两枚都在。"""
    both = [item for item in run11c["rows"] if len(item["also_matched"]) > 1]
    assert both, "run11c 里没有一枚题命中两格：本钉的靶变了（chart-01 那一形），重新取证"
    for item in both:
        assert item["bucket"] == min(item["also_matched"], key=mod.BUCKET_PRIORITY.index)
        assert set(item["also_matched"]) <= set([mod.B1, mod.B2, mod.B3])
    hit = run11c["also_matched_counts"]
    counts = run11c["bucket_counts"]
    assert sum(hit.values()) >= sum(counts[name] for name in (mod.B1, mod.B2, mod.B3))


def test_b2_rows_all_carry_a_single_frame_and_the_same_millisecond(run9):
    """B2 的每一枚都必须同时拿着两件事：恰一枚帧 ∧ 与 request.completed 同毫秒。"""
    picked = [item for item in run9["rows"] if item["bucket"] == mod.B2]
    assert picked, "run9 读不到无逐片腿：这一窗的形状变了，本钉要重写"
    for item in picked:
        assert item["text_frames"] == 1, item["id"]
        assert item["witness"]["within_one_ms"] is True, item["id"]
        assert item["cell_2a"] is False, item["id"] + " 单帧却把②-a 读成 True：尺错了"


def test_b1_rows_are_a_real_zero_and_below_the_live_gate(run11c):
    """B1 的每一枚都得是「真的 0 枚工具调用」加「短过现取的尺寸闸」，两半缺一不成。"""
    gate = run11c["gate"]
    assert gate == mod.lane.piece_size_gate(), "尺寸闸不是现取的那一枚"
    picked = [item for item in run11c["rows"] if item["bucket"] == mod.B1]
    assert picked, "run11c 读不到天然短：本钉的靶变了"
    for item in picked:
        assert item["tool_calls"] == 0, item["id"]
        assert item["answer_chars"] < gate, item["id"]
        assert item["cell_2a"] is True, item["id"] + " 天然短却只有枚帧：与定义不符"


def test_the_two_millisecond_readings_are_both_reported(run9):
    """「差<1ms」与「ms 格相等」两读必须并排交，两读不一致的那一枚要点名（不许挑一处算对）。"""
    single = [item for item in run9["rows"] if item["text_frames"] == 1]
    divided = [item["id"] for item in single
               if item["witness"]["same_ms"] != item["witness"]["within_one_ms"]]
    assert len(divided) == 1, divided
    target = divided[0]
    item = entry_of(run9, target)
    joined = " ".join(item["evidence"])
    assert "差<1ms=True" in joined and "ms 格相等=False" in joined, item["evidence"]
    assert item["bucket"] == mod.B2
    assert run9["diagnostics"]["ms_reading_sensitivity_rows"] == [target]


# ============================ 三、反证牙（在册 counter_evidence 命名法）============================

def test_counter_evidence_a_blinding_the_prefab_set_folds_the_canned_rows_into_b0(tmp_path):
    """牙 a：把预制串真源换一枚影子串 ⇒ 那几枚占位句立刻被并进 B0（分母被偷大）。"""
    frames, sidecar, answers = ledger_paths("run9")
    real = read("run9")
    canned_before = [item["id"] for item in real["rows"] if item["bucket"] == mod.B3]
    assert canned_before
    chat = mod._read_source(mod.CHAT_SOURCE)
    shadow_text = chat.replace(u'本轮未产出任何结论，请重试或补充数据范围。',
                               u'本轮未产出任何结论（影子串，与账上不同）。')
    assert shadow_text != chat, "影子替换没生效：真源那一枚串换了写法"
    shadow = tmp_path / "chat-shadow.py"
    shadow.write_text(shadow_text, encoding="utf-8")
    result = mod.read_round(frames=frames, sidecar=sidecar, answers=answers, chat_source=shadow)
    assert result["bucket_counts"][mod.B3] == 0
    for key in canned_before:
        assert bucket_of(result, key) == mod.B0, key + " 致盲后没并进 B0：那枚格不是真在尺上"


def test_counter_evidence_a2_a_source_without_the_canned_literal_is_refused(tmp_path):
    """牙 a2：预制串真源里认不出那枚字面 ⇒ 当场抛，不许静默按「本窗没有预制句」出数。"""
    empty = tmp_path / "chat-none.py"
    empty.write_text(u"# 影子真源：没有 failure_text 这一枚\n", encoding="utf-8")
    with pytest.raises(mod.PrefabSourceError):
        mod.chat_prefab_texts(empty)
    frames, sidecar, answers = ledger_paths("run9")
    with pytest.raises(mod.PrefabSourceError):
        mod.read_round(frames=frames, sidecar=sidecar, answers=answers, chat_source=empty)


def test_counter_evidence_b_the_size_gate_is_read_live_not_copied(tmp_path, run11c):
    """牙 b：尺寸闸是现取的 —— 换一枚影子真源，B1 的枚数就跟着动；真源缺那行 ⇒ 直接抛。"""
    frames, sidecar, answers = ledger_paths("run11c")
    wide = tmp_path / "nodes-wide.py"
    wide.write_text("STREAM_PIECE_MIN_CHARS = 1000000\n", encoding="utf-8")
    result = mod.read_round(frames=frames, sidecar=sidecar, answers=answers, nodes_source=wide)
    assert result["gate"] == 1000000, "影子闸没吃到：这一格用的是手抄的那枚数"
    zero = set(item["id"] for item in result["rows"] if item["tool_calls"] == 0)
    hit = set(item["id"] for item in result["rows"] if mod.B1 in item["also_matched"])
    assert hit == zero, "闸放开后 B1 的命中集合与 tool_calls==0 的题集不等：那一半不真在尺上"
    assert len(zero) > len([item for item in run11c["rows"] if item["bucket"] == mod.B1])
    absent = tmp_path / "nodes-none.py"
    absent.write_text("SOME_OTHER_GATE = 1\n", encoding="utf-8")
    with pytest.raises(mod.lane.SizeGateError):
        mod.read_round(frames=frames, sidecar=sidecar, answers=answers, nodes_source=absent)


def test_counter_evidence_c_fingerprint_drift_is_refused_not_dropped(tmp_path):
    """牙 c：现算指纹与账上 ``answer_sha`` 对不上 ⇒ 拒绝出数（不是少归两枚算了）。"""
    frames, sidecar, answers = ledger_paths("run9")
    canned = [item["id"] for item in read("run9")["rows"] if item["bucket"] == mod.B3]
    assert canned

    def drift(row):
        if row.get("id") in canned:
            row = dict(row)
            row["answer_sha"] = "0" * 12
        return row

    shadow = rewrite_jsonl(frames, tmp_path / "frames-drift.jsonl", drift)
    with pytest.raises(mod.FingerprintDriftError):
        mod.read_round(frames=shadow, sidecar=sidecar, answers=answers)


def test_counter_evidence_d_the_millisecond_half_of_b2_is_load_bearing(tmp_path):
    """牙 d：把那一枚 ``request.completed`` 推后 50 ms ⇒ 该题不再是 B2；摘掉「同毫秒」那半就抓不住。"""
    frames, sidecar, answers = ledger_paths("run9")
    candidates = [item["id"] for item in read("run9")["rows"] if item["also_matched"] == [mod.B2]]
    assert candidates, "run9 没有一枚只命中 B2 的题：本钉的靶变了"
    target = candidates[0]

    def push(row):
        if row.get("id") != target:
            return row
        row = dict(row)
        row["events"] = [dict(item, arrival_at=str(float(item["arrival_at"]) + 0.05))
                         if item.get("event") == "request.completed" else item
                         for item in row["events"]]
        return row

    shadow = rewrite_jsonl(frames, tmp_path / "frames-pushed.jsonl", push)
    result = mod.read_round(frames=shadow, sidecar=sidecar, answers=answers)
    item = entry_of(result, target)
    assert item["bucket"] == mod.B0, item["also_matched"]
    assert mod.B2 not in item["also_matched"]
    assert "差<1ms=False" in " ".join(item["evidence"])
    assert entry_of(read("run9"), target)["bucket"] == mod.B2, "正控不成立：这一窗本来就没有 B2"


def test_counter_evidence_e_a_missing_tool_calls_is_not_treated_as_zero(tmp_path):
    """牙 e：两本账都 join 不到 ``tool_calls`` ⇒ 不许当成 0 蒙进 B1，必须点名在「不可判」那一格。"""
    frames, sidecar, answers = ledger_paths("run11c")
    picked = [item["id"] for item in read("run11c")["rows"] if item["bucket"] == mod.B1]
    assert picked

    def drop(row):
        if row.get("id") in picked:
            row = dict(row)
            row.pop("tool_calls", None)
        return row

    shadow_sidecar = rewrite_jsonl(sidecar, tmp_path / "sidecar-drop.jsonl", drop)
    shadow_answers = rewrite_jsonl(answers, tmp_path / "answers-drop.jsonl", drop)
    result = mod.read_round(frames=frames, sidecar=shadow_sidecar, answers=shadow_answers)
    assert result["bucket_counts"][mod.B1] == 0
    assert set(result["diagnostics"]["tool_calls_unjoinable"]) >= set(picked)
    for key in picked:
        assert bucket_of(result, key) != mod.B1, key + " 把缺键当成了 0"


def test_counter_evidence_f_a_smaller_window_does_not_slip_past_the_denominator(capsys):
    """牙 f：拿一枚 12 题的半窗来跑 ⇒ 在册分母对账不上要 rc=2 并点名，不许静默按小窗出数。"""
    f, s, a = tuple(REPO_ROOT / name for name in P2_WINDOW)
    code = mod.main(["--frames", str(f), "--sidecar", str(s), "--answers", str(a), "--no-rows"])
    out = capsys.readouterr().out
    assert code == 2, code
    assert u"对账不上" in out, out[-400:]


def test_counter_evidence_g_this_file_carries_no_downgrade_marker():
    """牙 g：本件一枚降级记号都不许有（跳过／放宽／独占）—— 反证钉不分层出门。"""
    text = Path(__file__).read_text(encoding="utf-8")
    for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail", "pytest.mark." + "skipif",
                   "pytest." + "skip(", "pytest." + "xfail(", ".only" + "("):
        assert marker not in text, "本件里出现了降级记号：" + marker


def test_counter_evidence_h_the_instrument_never_writes_its_inputs(monkeypatch, capsys):
    """牙 h：三本账逐字节不许动 —— 跑完之后 sha256 与跑之前逐枚全等，且没有一枚以写模式打开。"""
    paths = ledger_paths("run9")
    before = [sha256_of(path) for path in paths]
    modes = []
    real_open = io.open

    def spy(file, mode="r", *args, **kwargs):
        modes.append(str(mode))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", spy)
    code = mod.main(["--frames", str(paths[0]), "--sidecar", str(paths[1]),
                     "--answers", str(paths[2]), "--no-rows"])
    capsys.readouterr()
    assert code == 0, code
    assert [sha256_of(path) for path in paths] == before
    assert [mode for mode in modes if any(ch in mode for ch in "wax+")] == []
