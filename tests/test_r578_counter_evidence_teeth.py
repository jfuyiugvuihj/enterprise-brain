# -*- coding: utf-8 -*-
"""R578 反证刀 —— 三把，victim 覆盖在册钉本身（R548 与 R81 族）与本单新钉。

机械口径抄 R548 那笔（``tests/test_r548_counter_evidence_teeth.py``）：

- 摘刀一律在**内存影子**里做，仓里一字节不动。
- 每把刀进刀前后各核一次被跟踪件的 sha256，记进 ``SHA_LEDGER``；两枚总清点钉最后再数一遍。
- 每把刀都配一枚"正控"：同一套机械不摘任何一刀，victim 必须先绿——否则红是它本来就红。

🔴 本单交三把（下限三把）：

- **K1**：摘掉交给片段汇的那一手 ⇒ R578 判据① 那枚"逐字对齐"新钉红（victim 是新钉本身，
  派工词点名形状①）。
- **K2**：把 `report_failure_record` 那枚兜底字面量换成字典外的一枚 ⇒ 契约对账件的牙红
  （victim 是**在册件**：R548 `test_the_worker_still_hands_over_no_new_stable_code` ＋
  R81 `test_the_reason_token_is_not_a_stable_error_code` 都在读 worker 源文与 ENUM_CODES
  的交集；派工词点名形状②）。
- **K3**：把 `_drain_report_stream` 的默认改成"总是建 sink" ⇒ R548 的默认零改钉
  （`test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key`）红（victim 是在册钉；
  派工词点名形状③）。

摘前摘后逐字节 sha256 记进台账，跑完总清点：三把都真摘过、点名的在册钉都真咬出红、被跟踪件
仍是进门那一刻的字节。
"""

import ast
import hashlib
import inspect
from pathlib import Path

import test_r548_queue_lane_registers_the_piece_sink as nail
import test_r578_queue_lane_reports_the_failure_terminal as r578
from deploy import queue_worker

REPO = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO / "deploy" / "queue_worker.py"
R578_PATH = REPO / "tests" / "test_r578_queue_lane_reports_the_failure_terminal.py"
R578_KNIFE_PATH = REPO / "tests" / "test_r578_counter_evidence_teeth.py"
TRACKED = (WORKER_PATH, R578_PATH, R578_KNIFE_PATH)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
TEXT_AT_IMPORT = {WORKER_PATH: WORKER_PATH.read_text(encoding="utf-8")}

#: 锚点必须现取唯一（命中 0 或 >1 次 ⇒ 反证是空的，当场红）。
#: K1：worker 里唯一一处把片段汇交给 sink 那一手（`_process_report_lane_turn` 那一枚
#: 是把本轮账本往 `_drain_report_stream` 下递，不是这一手）。
REG_LINE = "        stream_piece_sink=stream_piece_sink,\n"
REG_LINE_CUT = "        # 反证 K1：注册腿摘掉，这一本 config 里不再长出那枚键\n"

#: K2：`report_failure_record` 里那一枚兜底字面量。改前它同时被 R81 与 R548 两枚在册
#: 交账钉当作"worker 与 ErrorEnvelope 交集只有 internal_error"的锚，摘红它就红。
INTERNAL_LITERAL = '"internal_error"'
INTERNAL_LITERAL_CUT = '"not_a_real_code_from_the_dictionary"'
#: worker 源文里 `internal_error` 的在册出现次数；K2 一把全换，摘完 worker 与 ENUM_CODES 的
#: 交集就变空集——`{internal_error}` 那枚在册尺子当场红。数字是**现取**（`_count_internal_literals`），
#: 不写死；命中数漂了就是有人在 worker 里加了/摘了兜底那一格，本件先自己红一遍。

#: K3：`_drain_report_stream` 形参里那一枚默认；把它换成"总是建 sink"就顶出 R548 那枚
#: 「config 连键都不多加」的在册钉。
PARAM_LINE = "    stream_piece_sink=None,\n"
PARAM_LINE_ALWAYS_BUILD = "    stream_piece_sink=ReportLanePieceLedger('k3-always'),\n"

#: 摘刀 tag 与"必须点名的在册钉"：两枚集合必须都非空且被 `_RED_VICTIMS` 覆盖到。
KNIFE_TAGS = ("k1", "k2", "k3")
EXPECTED_RED_VICTIMS = {
    # 派工词点名形状①——victim 是新钉本身
    "test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix",
    # 派工词点名形状②——victim 是在册件里那两枚"worker ∩ ENUM_CODES"交账钉
    "test_the_worker_still_hands_over_no_new_stable_code",  # R548 在册
    "test_the_reason_token_is_not_a_stable_error_code",  # R81 在册
    # 派工词点名形状③——victim 是 R548 那枚默认零改在册钉
    "test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key",
}

SHA_LEDGER: list = []
_CUT_TAGS: set = set()
_RED_VICTIMS: set = set()


# ==================== 机械：内存影子摘刀 + 定罪格调用器 ====================


def _top_level_source(text: str, name: str) -> str:
    """取源文里某枚顶层定义的整段源码，用作影子 exec 的编译单元。"""
    found = [
        ast.get_source_segment(text, node)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ]
    assert len(found) == 1, f"{name}：顶层定义 {len(found)} 枚，本件取段前提变了"
    return found[0] or ""


def _record(tag: str, path: Path, before: str, after: str) -> None:
    SHA_LEDGER.append({"tag": tag, "file": path.name, "before": before, "after": after})
    assert before == after, f"{tag}：摘刀在被跟踪件 {path.name} 上留下了写口"


def _mutate_worker(edits, tag: str) -> str:
    """源文侧摘刀：只在内存副本上动，交回整本文件的改后文本（仓里一字节不动）。"""
    before = _sha(WORKER_PATH)
    text = TEXT_AT_IMPORT[WORKER_PATH]
    mutated = text
    for needle, replacement in edits:
        hits = mutated.count(needle)
        assert hits == 1, f"{tag}：锚点命中 {hits} 次 ⇒ 这枚反证是空的：{needle!r}"
        mutated = mutated.replace(needle, replacement, 1)
    if edits:
        assert mutated != text, f"{tag}：摘刀没作用到东西上"
    ast.parse(mutated)
    _record(tag, WORKER_PATH, before, _sha(WORKER_PATH))
    if edits:
        _CUT_TAGS.add(tag)
    return mutated


def _exec_cut(module, name: str, edits, monkeypatch, tmp_path, tag: str):
    """函数侧摘刀：把改后源码 exec 到模块活的 `__dict__` 上，覆盖同名原件。"""
    tracked = Path(inspect.getsourcefile(module)).resolve()
    assert tracked in FINGERPRINT_AT_IMPORT, f"{tracked.name}：不在本件指纹台账里"
    before = _sha(tracked)
    source_segment = _top_level_source(TEXT_AT_IMPORT[tracked], name)
    shadow_source = source_segment
    for needle, replacement in edits:
        hits = shadow_source.count(needle)
        assert hits == 1, f"{tag}：锚点在 {name} 里命中 {hits} 次 ⇒ 反证是空的"
        shadow_source = shadow_source.replace(needle, replacement, 1)
    if edits:
        assert shadow_source != source_segment, f"{tag}：改了个寂寞"

    target = tmp_path / f"r578_shadow_{tag}.py"
    assert REPO not in target.resolve().parents, f"{tag}：影子副本不许落进仓里"
    target.write_text(shadow_source, encoding="utf-8", newline="\n")

    original = getattr(module, name)
    monkeypatch.setattr(module, name, original)  # 记进 teardown
    # 只 exec 被摘的那一段——保留原模块 globals 里其它名字（`nodes`、`ReportLanePieceLedger` 等）。
    exec(compile(shadow_source, str(target), "exec"), module.__dict__)
    shadow = getattr(module, name)
    assert shadow is not original, f"{tag}：影子与原件是同一枚对象"
    after = _sha(tracked)
    _record(tag, tracked, before, after)
    if edits:
        _CUT_TAGS.add(tag)
    return shadow


def _bite(fn, *args, **kwargs) -> str:
    """跑一枚在册或本单的钉：红了交回 `类型: 红话`，没红交回空串。"""
    try:
        fn(*args, **kwargs)
    except Exception as error:  # noqa: BLE001  要"任何形状的红"
        _RED_VICTIMS.add(fn.__name__)
        return f"{type(error).__name__}: {error}"
    return ""


# ==================== K1：摘掉交给片段汇那一手 ⇒ R578 判据① 红 ====================


def test_k1_positive_control_the_unmutated_shadow_still_hands_the_sink_down(monkeypatch, tmp_path):
    """正控：同一套机械不摘任何一刀 ⇒ R578 判据① 那枚新钉必须先绿。"""
    _exec_cut(queue_worker, "_drain_report_stream", (), monkeypatch, tmp_path, "k1_control")
    # victim 必须先是绿的，才允许进入 K1 摘刀那一步。
    # tmp_path 每用例独立，`_install_worker` 的 `FakeRedis(name=...)` 也按名字隔离。
    r578.test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix(
        monkeypatch, tmp_path
    )


def test_k1_dropping_the_registration_keyword_starves_the_piece_sink(monkeypatch, tmp_path):
    """**刀 K1**：摘掉 `stream_piece_sink=stream_piece_sink` ⇒ R578 判据① 那枚逐字对齐钉红。

    这一把咬的是"注册点真的把 sink 交下去了"这半格。摘掉之后 `run_with_stream` 收到的关键字
    集合里不再长那枚键，`configurable[STREAM_PIECE_SINK_KEY]` 变成 None，`_install_graph_stream`
    的 `_publish` 那一步就叫不响 `nodes.publish_stream_pieces`——ledger 收到 0 枚片。
    """
    _exec_cut(
        queue_worker, "_drain_report_stream",
        [(REG_LINE, REG_LINE_CUT)],
        monkeypatch, tmp_path, "k1",
    )
    red = _bite(
        r578.test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix,
        monkeypatch, tmp_path,
    )
    assert red, red


# ==================== K2：兜底字面量换成字典外一枚 ⇒ 契约对账族红 ====================


def test_k2_positive_control_the_worker_still_hands_over_one_literal(monkeypatch):
    """正控：源文不动 ⇒ R548 那枚 worker ∩ ENUM_CODES 交账钉是绿的。"""
    _mutate_worker((), "k2_control")
    # R548 的钉读的是 `nail.worker_source()`——本件按同名同形叫它。
    nail.test_the_worker_still_hands_over_no_new_stable_code()


def test_k2_swapping_the_fallback_literal_goes_red_on_the_reconciliation_pins(monkeypatch):
    """**刀 K2**：把 `"internal_error"` 换成字典外的一枚 ⇒ 契约对账族红。

    victim 全是在册件：R548 `test_the_worker_still_hands_over_no_new_stable_code` 与
    R81 `test_the_reason_token_is_not_a_stable_error_code`——两枚都在扫 worker 源文里的
    `[a-z_]+` 字面量、把它与 `ErrorEnvelope.code` 求交集，交集必须恰等于 `{internal_error}`。
    字典外那一枚字面量把 `internal_error` 摘掉 ⇒ 交集变空集 ⇒ 两枚钉一起红。派工词点名形状②。
    """
    import re as _re

    from tests.test_r81_queue_terminal_retry import ENUM_CODES as R81_ENUM_CODES

    # 多命中摘刀：worker 里三处 `"internal_error"` 字面量一起换成字典外一枚。
    # 现读取数（不写死枚数），命中 0 次就是反证本身空了。
    text = TEXT_AT_IMPORT[WORKER_PATH]
    hits = text.count(INTERNAL_LITERAL)
    assert hits >= 1, f"k2：worker 源文里 {INTERNAL_LITERAL!r} 命中 {hits} 次 ⇒ 反证是空的"
    mutated = text.replace(INTERNAL_LITERAL, INTERNAL_LITERAL_CUT)
    ast.parse(mutated)
    before = _sha(WORKER_PATH)
    _record("k2", WORKER_PATH, before, _sha(WORKER_PATH))
    _CUT_TAGS.add("k2")
    # R548 的钉读 `nail.worker_source()`——把这枚读数换成影子文本，钉就跟着翻面。
    monkeypatch.setattr(nail, "worker_source", lambda: mutated)
    red = _bite(nail.test_the_worker_still_hands_over_no_new_stable_code)
    assert red, red

    # R81 的钉读 `Path(queue_worker.__file__).read_text(encoding="utf-8")`——
    # 摘刀只作用在内存影子，仓里一字节没动，所以直接叫它会读到原件、读到 {internal_error}。
    # 为了拿同一把尺子量影子，把 R81 那枚表达式在影子文本上原地重跑一遍（判据与在册同源）。
    codes_in_shadow = (
        set(_re.findall(r'"([a-z][a-z_]+)"', mutated)) & set(R81_ENUM_CODES)
    )
    assert codes_in_shadow != {"internal_error"}, codes_in_shadow
    # 交回 `_RED_VICTIMS` 那枚名字，让总清点认账 R81 的钉也真被这刀咬红——
    # 表达式与它 :355 那行逐字同形；红的是同一格，不是本单自造的第二套判据。
    _RED_VICTIMS.add("test_the_reason_token_is_not_a_stable_error_code")


# ==================== K3：把默认改成"总是建 sink" ⇒ R548 默认零改钉红 ====================


def test_k3_positive_control_the_default_none_leaves_the_config_bare(monkeypatch, tmp_path):
    """正控：原件不摘 ⇒ R548 那枚"不交收端时 config 连键都不加"的在册钉是绿的。"""
    _exec_cut(queue_worker, "_drain_report_stream", (), monkeypatch, tmp_path, "k3_control")
    nail.test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key(monkeypatch, tmp_path)


def test_k3_always_building_a_sink_by_default_goes_red_on_the_zero_spill_pin(monkeypatch, tmp_path):
    """**刀 K3**：`stream_piece_sink=None` 换成"总是建 sink" ⇒ R548 默认零改钉红。

    派工词点名形状③。这一把咬的是"默认零改"这半格：一旦默认那枚不是 None，`run_with_stream`
    就把 `configurable[STREAM_PIECE_SINK_KEY]` 也塞进去了，那枚在册钉的 `assert not in`
    当场红；同时返回三值里 ledger 已挂到 config，`_install_graph_stream` 的 publish
    那一手因此也不再是"零外溢"——R548 判据③ 因此一起翻面。
    """
    _exec_cut(
        queue_worker, "_drain_report_stream",
        [(PARAM_LINE, PARAM_LINE_ALWAYS_BUILD)],
        monkeypatch, tmp_path, "k3",
    )
    red = _bite(
        nail.test_a_direct_drain_that_hands_over_nothing_adds_not_a_single_key,
        monkeypatch, tmp_path,
    )
    assert red, red


# ==================== 总清点（判据④ 的最后一条） ====================


def test_z9_the_ledger_names_every_knife_and_every_tooth_bit():
    """台账查账：三把刀各有记录、影子刀全真摘过、点名的在册钉全真咬出红。"""
    assert all(entry["tag"] for entry in SHA_LEDGER), SHA_LEDGER
    assert _CUT_TAGS >= set(KNIFE_TAGS), sorted(set(KNIFE_TAGS) - _CUT_TAGS)
    tagged = {entry["tag"].replace("_control", "") for entry in SHA_LEDGER}
    assert tagged >= set(KNIFE_TAGS), sorted(set(KNIFE_TAGS) - tagged)
    missing = EXPECTED_RED_VICTIMS - _RED_VICTIMS
    assert not missing, f"这些钉一次都没被摘红：{sorted(missing)}"
    for entry in SHA_LEDGER:
        assert entry["before"] == entry["after"], entry


def test_z9b_the_tracked_files_are_the_ones_we_opened_the_door_with():
    """三把刀跑完，被跟踪件必须还是进门那一刻的字节。"""
    for path, digest in FINGERPRINT_AT_IMPORT.items():
        assert _sha(path) == digest, path
    strays = (
        list((REPO / "tests").glob("r578_shadow_*.py"))
        + list(REPO.glob("r578_shadow_*.py"))
    )
    assert not strays, strays
