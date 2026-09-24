# -*- coding: utf-8 -*-
"""R218 判据 ②-A②（三格之三）+ 判据 ④ 反证钉：A② 的量具自校准。

对判据的哪一条：单号 R218 判据 ② 第三格 —— 预演件必须能在离线合成流上复现
「受控纠正轮 → ``uncorrected_breaks == 0`` → 判据② 读绿」与「真断流轮 → 读红」两种形状，
证明窗里那把尺子今天有牙，而不是到窗里第一次用。

🔴 本班态（总控 09-24 裁定 R215 先并树之后重钉，方向只许变严）：
  - 量具代际断成 ``R181+R215``；``_frame_verdict`` 的**判绿腿只读净额** ``uncorrected_breaks``
    （``reads_prefix_breaks`` 必须 False），原始账那一格改由 ``_frame_readings`` 的返回值键集
    单独钉着（``reading_keys`` 含 ``prefix_breaks`` + ``has_r181``）。
    🔴 这一条与派工词的字面口供不同，且是**变严不是变松**：派工词要求断成"两枚都读 True"，
    那枚读数来自 ``inspect.getsource`` + 子串匹配，而 R215 的 docstring 里两个名字都在
    （"``prefix_breaks == 0`` → **``uncorrected_breaks == 0``**"）—— 拿散文当证据 ⇒ 把尺子整代
    退回 R181 也打不红它。反证钉乙实测到这一枚假牙，故改读 AST；见
    ``test_verdict_reads_ignores_prose_and_follows_the_code``。
  - 原来那枚「两形状在本基点不可分」的读数换成**真断言**：受控纠正轮读绿、
    真断流轮与腰上坏形轮读红 —— 也就是「尺子两形状今天**同时**有牙」；
  - 原始账不许漂：``prefix_breaks`` 照样在账上，豁免只体现在 ``uncorrected_breaks``；
  - 那条 ``NOT_COVERED_OFFLINE: 受控纠正轮读绿`` 现在必须为空 —— 它已可测，
    留着就是过期口供。
  - run6 那一格由 ``tests/test_r215_recomputing_run6_frames.py`` 钉（105 行 × 13 格逐位
    相同、``criterion_two_holds`` 逐行不变），本件**只读它的数，不另立第二把尺**。
🔴 反证只加不减：既有断言一枚不删、不放宽。
"""
import hashlib
import inspect
import importlib.util
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _rehearsal():
    spec = importlib.util.spec_from_file_location(
        "r218_switch_rehearsal_mod", REPO / "scripts" / "r218_switch_rehearsal.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _rehearsal()

PIN_FILES = R.rehearsal_inputs()  # 由 _CITATIONS 与三格读取点长出，不手抄


def _tree_sha() -> dict:
    return {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in PIN_FILES}


def _overlay(tmp_path: Path) -> Path:
    root = tmp_path / "overlay"
    for rel in PIN_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    return root


def test_synthetic_streams_actually_parse_before_any_verdict():
    """防「空转的牙」：帧没进尺子就没资格谈红绿（本件 09-24 首跑栽在这里）。"""
    adapter = R._load_adapter(REPO)
    chat = R._load_chat()
    for armed, at_tail in ((True, True), (False, True), (True, False)):
        shape = R.frame_shape(adapter, chat, armed=armed, break_at_tail=at_tail)
        assert shape["stream_parsed"] is True, shape
        assert shape["readings"]["text_frames"] == shape["frames_sent"] == 3


def test_the_ruler_now_has_teeth_on_both_shapes_at_once():
    """判据 ②-A② 的正例：两形状**同时**成立 —— 这才是「窗里那把尺子今天有牙」。"""
    cell = R.cell_ruler(REPO)
    shapes = cell["readings"]["shapes"]

    controlled = shapes["controlled_correction_round"]["readings"]
    assert cell["readings"]["ruler_generation_actual"] == "R181+R215"
    assert cell["readings"]["verdict_reads"] == {
        "reads_prefix_breaks": False,          # 判绿腿已从原始账移走（R215 的那一次换读法）
        "reads_uncorrected_breaks": True,
        "verdict_key_set": ["extra_chars", "last_frame_covers_answer", "max_stream_frames",
                            "missing_chars", "text_frames", "uncorrected_breaks"]}
    # 原始账那一格仍在账上，别丢 —— 但它现在由键集钉，不再由一句散文同时喂两格
    assert "prefix_breaks" in cell["readings"]["reading_keys"]
    # 受控纠正轮：坏形照样记在原始账上，豁免只体现在 uncorrected 那一格
    assert controlled["prefix_breaks"] == 1, "原始账漂了：豁免不该把 prefix_breaks 抹平"
    assert controlled["corrective_replacements"] == 1
    assert controlled["uncorrected_breaks"] == 0
    assert shapes["controlled_correction_round"]["verdict"] is True

    # 真断流轮（同一枚末帧坏形，只是前面没有那枚武装 step）：不许跟着一起绿
    broken = shapes["true_break_round"]["readings"]
    assert broken["prefix_breaks"] == 1
    assert broken["per_stream"][0]["first_break_at"] == 3
    assert broken["corrective_replacements"] == 0
    assert broken["uncorrected_breaks"] == 1
    assert shapes["true_break_round"]["verdict"] is False

    # 腰上坏形轮（有武装 step、但坏形不在末帧）：条件 ① 必须咬住
    midbreak = shapes["midstream_break_round"]["readings"]
    assert midbreak["prefix_breaks"] == 2
    assert midbreak["uncorrected_breaks"] == 2
    assert shapes["midstream_break_round"]["verdict"] is False

    assert cell["verdict"] == R.GREEN, cell["problems"]


def test_verdict_reads_ignores_prose_and_follows_the_code():
    """钉住"读代码不读散文"这件事本身（上一班这枚是假牙，乙实测到的）。

    期望的形状很刁：``_frame_verdict`` 的 **docstring 里必须仍然写着** ``prefix_breaks``
    （它讲的是"从哪一格换到哪一格"这件事，换读法的历史当然得留在纸上），而
    ``verdict_reads`` 必须报 ``reads_prefix_breaks False``。两枚同时成立，才证明这枚读数
    是从 ``readings[...]`` 的 AST 取用集长出来的，不是从文件里搜字符串搜出来的。
    谁哪天把它改回 ``"prefix_breaks" in inspect.getsource(...)``，这一条立刻红。
    """
    adapter = R._load_adapter(REPO)
    doc = adapter._frame_verdict.__doc__ or ""
    source = inspect.getsource(adapter._frame_verdict)
    reads = R.verdict_reads(adapter)
    assert "prefix_breaks" in doc, "docstring 里那枚旧读法没了：这枚对照失效，换更强的锚"
    assert "prefix_breaks" in source
    assert reads["reads_prefix_breaks"] is False, "散文里有这个名字就把判绿腿算成读原始账 = 假牙"
    assert "prefix_breaks" not in reads["verdict_key_set"]


def test_the_two_shapes_are_now_distinguishable_and_nothing_is_left_uncovered():
    """本班态：两形状分开（旧读数的反面），且那条 NOT_COVERED 必须已经消失。"""
    cell = R.cell_ruler(REPO)
    readings = cell["readings"]
    shapes = readings["shapes"]
    assert readings["shape_pair_indistinguishable_at_base"] is False
    assert (shapes["controlled_correction_round"]["readings"]
            != shapes["true_break_round"]["readings"])
    # 🔴 已可测 ⇒ 不许再留过期口供
    assert cell["not_covered_offline"] == []
    assert readings["unparsed_shapes"] == []


def test_run6_recompute_is_read_not_rederived():
    """run6 那一格归 R215 的件钉，本件只读它给的数（两枚件不许多立一把尺）。"""
    piece = REPO / "tests" / "test_r215_recomputing_run6_frames.py"
    text = piece.read_text(encoding="utf-8")
    import ast

    tree = ast.parse(text)
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", "") in ("RUN6_ROWS", "FRAMES_ORIGINAL_SHA256"):
                    consts[target.id] = ast.literal_eval(node.value)
    assert consts["RUN6_ROWS"] == 105
    frames = REPO / "docs" / "testing" / "sidecar-run6-frames.jsonl"
    assert hashlib.sha256(frames.read_bytes()).hexdigest() == consts["FRAMES_ORIGINAL_SHA256"], (
        "run6 帧账原件被改动过：R215 的复算读数即作废，本件的引用也随之作废")
    import json

    rows = [json.loads(line) for line in frames.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == consts["RUN6_ROWS"] == 105
    # run6 全窗零坏形 ⇒ 豁免无对象可免 ⇒ verdict 逐行仍是 False（与 R215 的复算同向）
    assert all(row["prefix_breaks"] == 0 for row in rows)
    assert all(row["criterion_two_holds"] is False for row in rows)


def test_counter_proof_a_lying_generation_claim_goes_red_here():
    """反证钉 甲：量具已是 R181+R215，却拿「仍只 R181」的假口供报绿 ⇒ 必须当场红。"""
    before = _tree_sha()
    cell = R.cell_ruler(REPO, claimed_generation="R181-only")
    assert cell["verdict"] == R.RED
    assert any(p.startswith("generation_claim_mismatch") for p in cell["problems"])
    assert "claim=R181-only actual=R181+R215" in " ".join(cell["problems"])
    # 红只能落在本格：另两格对同一棵真树照旧
    assert R.cell_cache_hit(REPO)["verdict"] == R.GREEN
    assert R.cell_lane_flip(REPO)["readings"]["frontend_unhandled_final"] == ["dead"]
    assert _tree_sha() == before


def test_counter_proof_the_other_direction_still_bites(tmp_path):
    """反证钉 乙（甲的对偶）：量具被整代退回 R181，却拿「已有 R215 两格」报绿 ⇒ 当场红。

    两向都要咬：甲是「尺子已升级、口供说没升级」，乙是「尺子没升级、口供说升级了」——
    后者正是判据⑥ 禁的那次「假装绿」。退代必须退得**成套**（读数两格 + verdict 那一格
    一起退），只退一半会在 ``_frame_verdict`` 里 KeyError，那测的就不是「尺子旧」而是
    「尺子坏」，钉的落点会歪。
    """
    overlay = _overlay(tmp_path)
    adapter_py = overlay / "scripts/eval_transport_ask_v2.py"
    original = adapter_py.read_text(encoding="utf-8")
    step_one = original.replace(
        '            "corrective_replacements": corrective["corrective_replacements"],\n'
        '            "uncorrected_breaks": corrective["uncorrected_breaks"],\n', '')
    downgraded = step_one.replace('and readings["uncorrected_breaks"] == 0',
                                  'and readings["prefix_breaks"] == 0')
    assert downgraded != original and step_one != original, "反证没作用到东西上，这枚钉是空的"
    assert 'and readings["prefix_breaks"] == 0' in downgraded
    adapter_py.write_text(downgraded, encoding="utf-8")

    before = _tree_sha()
    honest = R.cell_ruler(overlay)
    assert honest["readings"]["ruler_generation_actual"] == "R181-only"
    assert honest["readings"]["verdict_reads"]["reads_uncorrected_breaks"] is False
    # 退代之尺判不出受控纠正轮的绿：本格必须明写不可测，不许闷声报绿
    assert honest["readings"]["shapes"]["controlled_correction_round"]["verdict"] is False
    assert any(item.startswith("NOT_COVERED_OFFLINE") for item in honest["not_covered_offline"])
    # 但拿着假口供来报绿，必须当场红
    lying = R.cell_ruler(overlay, claimed_generation="R181+R215")
    assert lying["verdict"] == R.RED
    assert any(p.startswith("generation_claim_mismatch") for p in lying["problems"])
    assert "claim=R181+R215 actual=R181-only" in " ".join(lying["problems"])

    # 红只能落在本格：D 格与 C 格对着同一枚退代临时根判，必须维持原判
    assert R.cell_lane_flip(overlay)["readings"]["frontend_unhandled_final"] == ["dead"]
    assert R.cell_cache_hit(overlay)["readings"]["mismatched_legs"] == []

    shutil.rmtree(tmp_path)
    assert _tree_sha() == before
    assert (REPO / "scripts/eval_transport_ask_v2.py").read_text(encoding="utf-8") == original


def test_counter_proof_removing_the_prefix_guard_goes_red_here(tmp_path):
    """反证钉 丙（原「甲」保留）：摘掉 ``_count_text_frame`` 的前缀守卫 ⇒ 掉牙 ⇒ 本格红。

    摘掉守卫后的期望不是「更松」而是「必须被抓住」：真断流轮会读成 verdict=True，
    本格要指着 ``broken_stream_reads_green`` 报红，而不是跟着一起绿。
    """
    overlay = _overlay(tmp_path)
    adapter_py = overlay / "scripts/eval_transport_ask_v2.py"
    original = adapter_py.read_text(encoding="utf-8")
    mutated = original.replace(
        '    if out["text_frames"] and not frame.startswith(out["last_text_frame"]):',
        '    if False and out["text_frames"] and not frame.startswith(out["last_text_frame"]):')
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    adapter_py.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    cell = R.cell_ruler(overlay)
    assert cell["verdict"] == R.RED
    assert "broken_stream_reads_green" in cell["problems"]
    assert cell["readings"]["shapes"]["true_break_round"]["readings"]["prefix_breaks"] == 0
    assert cell["readings"]["shapes"]["true_break_round"]["verdict"] is True

    # 红只能落在本格：D 格读的是 _poll_queue 与停表名单，C 格读的是 cached 证词，都不该动
    assert R.cell_lane_flip(overlay)["readings"]["frontend_unhandled_final"] == ["dead"]
    assert R.cell_cache_hit(overlay)["readings"]["mismatched_legs"] == []

    shutil.rmtree(tmp_path)
    assert _tree_sha() == before
    assert (REPO / "scripts/eval_transport_ask_v2.py").read_text(encoding="utf-8") == original


def test_counter_proof_the_exemption_guard_is_load_bearing(tmp_path):
    """反证钉 丁（新尺子的新牙）：把「四条同时成立才豁免」里的 ③（武装 step）摘掉 ⇒ 红。

    豁免判据少一条，真断流轮就会冒充成受控纠正轮 ⇒ 判据② 永久假绿。本格必须在
    ``true_break_round`` 读绿的那一刻抓住它。
    """
    overlay = _overlay(tmp_path)
    adapter_py = overlay / "scripts/eval_transport_ask_v2.py"
    original = adapter_py.read_text(encoding="utf-8")
    mutated = original.replace('        if not record.get("armed"):\n            continue  # ③',
                               '        if False and not record.get("armed"):\n            continue  # ③')
    assert mutated != original, "反证没作用到东西上，这枚钉是空的"
    adapter_py.write_text(mutated, encoding="utf-8")

    before = _tree_sha()
    cell = R.cell_ruler(overlay)
    assert cell["verdict"] == R.RED
    assert "broken_stream_reads_green" in cell["problems"]
    assert (cell["readings"]["shapes"]["true_break_round"]["readings"]
            ["corrective_replacements"] == 1)
    assert R.cell_lane_flip(overlay)["verdict"] == R.RED  # 且红的原因不是它
    assert R.cell_cache_hit(overlay)["readings"]["mismatched_legs"] == []

    shutil.rmtree(tmp_path)
    assert _tree_sha() == before