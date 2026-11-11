"""R454 判据②的常驻钉：一窗多判据的计划器只许开一扇窗，批准次数必须算得出来。

病灶原文（跟进单 §128 二节）：五道门的格分扇窗跑——run9 相 1 全量串行 111.2 分钟、
run9c 只跑队列道 20 枚，一扇窗只拿一两格就收工，剩下的格下一班再开窗，
同一批题被反复重放。所以本文件第一件事就是钉"窗数恒为 1"，
第二件事是钉"相"不能变成变相的第二扇（每相一套开关态，且相划分有物理理由）。

为什么必须分相而不是合并成一相（runbook「两相一窗」写死，不是纪律问题）：
`REPORT_LANE_VIA_QUEUE` 一开，报告档的回答整段取回，A② 那 12 枚必然读成
`(text_frames, max_stream_frames) = (1, 1)`——把 D 三格和 A② 放同一轮，
等于用 D 的开关把 A② 洗成假红。所以计划器给的是"一扇窗两相"，不是"一相全拿"。

批准次数这一格正是业主 09-28 授权「评测窗内自动批准」省下来的地方，
所以它必须是**算出来的**：算料＝上一窗 sidecar 逐枚 approval_rounds。
本机反例（现读同一件）：按族猜会算成 0——`approval` 族在 run9 里一枚都没触发批准轮，
真触发的是 report/chart/tool/insight/scope 那 18 枚。

反证钉（第三把）：把"同一批格开第二扇窗"这一约束摘掉，两扇窗的计划就溜过去了；
装回去 ⇒ 当场红，且红的话里点名是哪几枚格。

全程离线：只读仓内文本文件，零模型、零网络、零容器。
"""
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval_window_planner.py"
BANK_PATH = REPO_ROOT / "tests" / "fixtures" / "business_evaluation_100.jsonl"
SUBSET_PATH = REPO_ROOT / "docs" / "testing" / "bank-shape-subset-30.jsonl"
EVIDENCE_PATH = REPO_ROOT / "docs" / "testing" / "sidecar-run9.jsonl"


def _load_planner():
    name = "eval_window_planner"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


planner = _load_planner()

BANK_LINES = [line for line in BANK_PATH.read_bytes().splitlines(keepends=True) if line.strip()]
SUBSET_RAW = SUBSET_PATH.read_bytes()
EVIDENCE = planner.load_approval_evidence(EVIDENCE_PATH)
ALL_SHAPE = list(planner.SHAPE_CELLS)


def _plan(cells=None, profile=None):
    requested = ALL_SHAPE if cells is None else list(cells)
    return planner.plan_window(
        requested,
        bank_lines=BANK_LINES,
        subset_raw=SUBSET_RAW,
        evidence=EVIDENCE,
        profile=profile or planner.MachineProfile(),
    )


def _subset_ids():
    comparison = planner.compare_subset(BANK_LINES, SUBSET_RAW)
    return [row["id"] for row in comparison["rows"] if row["equal"]]


# ==================== 判据②主断言 ====================


def test_the_request_yields_exactly_one_window():
    plan = _plan()
    assert len(plan["windows"]) == 1, plan["windows"]
    window = plan["windows"][0]
    assert window["window_id"] == "shape-window-1"
    # 一扇窗里可以多相，但窗还是那一扇。
    assert len(window["phases"]) == 2, window["phases"]


def test_every_requested_cell_gets_exactly_one_home_and_no_strangers():
    plan = _plan()
    assert sorted(plan["cells"]) == sorted(ALL_SHAPE)
    for cell_id, phases in plan["cell_phases"].items():
        assert phases, cell_id
    for window in plan["windows"]:
        placed = [c for phase in window["phases"] for c in phase["cells"]]
        assert set(placed) == set(ALL_SHAPE), sorted(set(placed) ^ set(ALL_SHAPE))
        for phase in window["phases"]:
            assert len(phase["cells"]) == len(set(phase["cells"])), phase["cells"]
        # 有开关要求的格只能落一相；不变量格（零重试零哨兵）才允许跟着每一相播放。
        for cell_id in set(placed):
            homes = plan["cell_phases"][cell_id]
            if planner.CELLS[cell_id].switches:
                assert len(homes) == 1, (cell_id, homes)
            else:
                assert len(homes) == len(window["phases"]), (cell_id, homes)


def test_the_two_phases_split_on_the_switch_that_makes_them_incompatible():
    plan = _plan()
    window = plan["windows"][0]
    stream, queue = window["phases"]
    assert stream["phase"] == planner.STREAM_PHASE
    assert stream["switches"] == {"REPORT_LANE_VIA_QUEUE": "off"}
    assert queue["phase"] == planner.QUEUE_PHASE
    assert queue["switches"] == {"REPORT_LANE_VIA_QUEUE": "on"}
    # A② 只在流式道上判；队列相里绝不出现 A②（否则 D 的开关把它洗成假红）。
    assert "A2-stream-verbatim" in stream["cells"]
    assert "A2-stream-verbatim" not in queue["cells"]
    assert "D-report-retrievable" in queue["cells"]
    assert "D-report-retrievable" not in stream["cells"]


def test_the_stream_phase_runs_the_whole_subset_and_the_queue_phase_only_report():
    subset_ids = _subset_ids()
    plan = _plan()
    stream, queue = plan["windows"][0]["phases"]
    assert stream["question_ids"] == subset_ids
    expected_report = [qid for qid in subset_ids if qid.split("-", 1)[0] == "report"]
    assert queue["question_ids"] == expected_report, queue["question_ids"]
    assert len(expected_report) >= 3, expected_report
    assert plan["windows"][0]["replayed_question_ids"] == sorted(expected_report)
    assert plan["windows"][0]["question_plays"] == len(subset_ids) + len(expected_report)


def test_the_invariant_cell_reads_plays_and_never_expands_the_queue_phase():
    """零重试零哨兵读"每一 play"，但它不许替队列相点整子集的题——那正好复刻本单要治的病。"""
    subset_ids = _subset_ids()
    report_only = [qid for qid in subset_ids if qid.startswith("report-")]
    plan = _plan(["D-report-retrievable", "zero-retry-zero-sentry"])
    (queue,) = plan["windows"][0]["phases"]
    assert queue["phase"] == planner.QUEUE_PHASE
    assert queue["cells"] == ["D-report-retrievable", "zero-retry-zero-sentry"]
    assert queue["question_ids"] == report_only, queue["question_ids"]
    assert plan["cell_phases"]["zero-retry-zero-sentry"] == [planner.QUEUE_PHASE]
    assert len(queue["question_ids"]) < len(subset_ids), "不变量格把队列相撑成整子集了"
    # 两相都在时（整班请求），不变量格跟着每一相播放，去重后仍是整子集。
    both = _plan()
    assert both["cell_phases"]["zero-retry-zero-sentry"] == [
        planner.STREAM_PHASE, planner.QUEUE_PHASE]
    assert len(both["cell_question_ids"]["zero-retry-zero-sentry"]) == len(subset_ids)


def test_approvals_are_computed_from_the_previous_window_sidecar_row_by_row():
    plan = _plan()
    window = plan["windows"][0]
    expected = sum(EVIDENCE.get(qid, 0) for phase in window["phases"]
                   for qid in phase["question_ids"])
    assert window["approvals_planned_total"] == expected, (
        window["approvals_planned_total"], expected)
    assert expected > 0, "算出 0 就说明算料没接上，批准次数那一格变成空话"
    per_phase = {phase["phase"]: sum(EVIDENCE.get(qid, 0) for qid in phase["question_ids"])
                 for phase in window["phases"]}
    assert window["approvals_per_phase"] == per_phase, window["approvals_per_phase"]


def test_guessing_approvals_by_family_would_have_got_this_wrong():
    """按族猜批准腿＝"approval 族会触发批准"——run9 现读把这句推翻，钉在这儿防止改回来。"""
    approval_ids = [qid for qid in _subset_ids() if qid.startswith("approval-")]
    assert approval_ids, "子集里必须留着 approval 族，否则这条反证失去对照物"
    assert sum(EVIDENCE.get(qid, 0) for qid in approval_ids) == 0
    triggered = sorted(qid for qid, rounds in EVIDENCE.items() if rounds)
    assert triggered, EVIDENCE
    assert not any(qid.startswith("approval-") for qid in triggered), triggered


def test_the_planner_names_score_and_latency_cells_as_out_of_scope():
    plan = _plan()
    assert plan["out_of_scope_statement"] == planner.SCOPE_SENTENCE
    assert planner.SCOPE_SENTENCE in json.dumps(plan, ensure_ascii=False)
    assert sorted(plan["out_of_scope_cells"]) == sorted(planner.OUT_OF_SCOPE_CELLS)
    assert len(planner.OUT_OF_SCOPE_CELLS) >= 3


@pytest.mark.parametrize("cell_id", list(planner.OUT_OF_SCOPE_CELLS))
def test_requesting_a_score_or_latency_cell_is_refused_by_name(cell_id):
    with pytest.raises(planner.ScopeViolation) as caught:
        _plan([cell_id])
    message = str(caught.value)
    assert planner.SCOPE_SENTENCE in message, message
    assert cell_id in message, message


def test_the_machine_names_the_cells_it_cannot_get_and_why():
    plan = _plan()
    blocked = plan["unattainable_here"]
    assert "C-overprivilege" in blocked, blocked
    assert "C-cache-annotation" in blocked, blocked
    for cell_id, reason in blocked.items():
        assert reason.strip(), cell_id
        assert "未验" not in reason  # 原因里不许塞结论，读数列才归读数列
    # 拿不了是能力位决定的，不是态度：把前置装上，同一枚格就从名单里消失。
    capable = _plan(profile=planner.MachineProfile(
        production_labels_backfilled=True, cache_hit_probe_allowed=True))
    assert capable["unattainable_here"] == {}, capable["unattainable_here"]


def test_the_auto_approve_boundary_is_written_into_the_plan():
    plan = _plan()
    assert plan["auto_approve_boundary"] == planner.AUTO_APPROVE_SENTENCE
    assert "生产" in plan["auto_approve_boundary"] and "评测账号" in plan["auto_approve_boundary"]


def test_an_empty_cell_request_refuses_to_open_any_window():
    with pytest.raises(planner.PlannerError):
        _plan([])


# ==================== 反证钉 3：同一批格开两扇窗 ⇒ 红 ====================


def test_counter_evidence_a_second_window_for_the_same_cells_turns_red():
    plan = _plan()
    with pytest.raises(planner.DuplicateWindowError) as caught:
        planner.open_second_window(plan, ["A2-stream-verbatim"])
    message = str(caught.value)
    assert "A2-stream-verbatim" in message, message
    assert "一扇窗" in message or "第二扇" in message, message


def test_counter_evidence_the_window_count_guard_is_the_only_teeth():
    """摘掉 validate_plan 这一层守卫：手工塞进的第二扇窗就无声溜过去了。

    于是"格被两扇窗重复认领"这件事的红，来自这条校验本身，不是来自相划分或渲染顺带。
    把守卫装回原样 ⇒ 当场红，并说清是几扇窗。
    """
    plan = _plan()
    window = plan["windows"][0]
    duplicate = json.loads(json.dumps(window, ensure_ascii=False))
    duplicate["window_id"] = "shape-window-2"
    two_windows = dict(plan)
    two_windows["windows"] = list(plan["windows"]) + [duplicate]

    # 摘掉守卫：没有任何一层会拦。
    original = planner.validate_plan
    planner.validate_plan = lambda item: None
    try:
        planner.validate_plan(two_windows)
        assert len(two_windows["windows"]) == 2
    finally:
        planner.validate_plan = original

    with pytest.raises(planner.DuplicateWindowError) as caught:
        planner.validate_plan(two_windows)
    assert "2" in str(caught.value), str(caught.value)


def test_counter_evidence_double_placing_a_cell_in_one_window_still_red():
    """同一枚格在一扇窗里被两相认领两次＝也是重复开窗的变种，一样红。"""
    plan = _plan()
    stream, queue = plan["windows"][0]["phases"]
    stream["cells"] = stream["cells"] + ["D-usage-nonzero"]
    with pytest.raises(planner.PlannerError):
        planner.validate_plan(plan)


# ==================== 返工令第 1–4 条：与 R453 读数名册的接口 ====================
#
# 这一段的纪律：本文件**一枚名册格名都不许自己写**。名册只能从对面件 import，
# 断言只用 planner 派生出来的 R453_CLOUD_CELLS / r453_cell_names() / resolve()。
# 抄一份云端格清单在这儿，就是又造了第二本账——两单交集＝0 那次事故的正身。


def test_the_two_name_spaces_now_intersect():
    """总控现取交集＝0 那一格，现在必须是可断言的非零：绑到的名全在对面的表里。"""
    bound = {name for names in planner.R453_BINDING.values() for name in names}
    roster = set(planner.r453_cell_names())
    assert bound, planner.R453_BINDING
    assert bound <= roster, sorted(bound - roster)
    assert len(roster) == len(planner.R453_ROSTER)


def test_every_shape_cell_carries_a_binding_and_every_binding_is_cloud_readable():
    plan = _plan()
    for cell_id in planner.SHAPE_CELLS:
        assert planner.CELLS[cell_id].r453_cells, cell_id
        assert plan["r453_binding"][cell_id] == list(planner.CELLS[cell_id].r453_cells)
        for name in plan["r453_binding"][cell_id]:
            assert name in planner.R453_CLOUD_CELLS, (cell_id, name)


def test_bindings_resolve_through_the_roster_own_registry():
    """每一枚绑定名都要被对面件的 REGISTRY 精确认出来（不是别名撞巧）。"""
    for cell_id, names in planner.R453_BINDING.items():
        for name in names:
            row = planner.R453.resolve(name)
            assert row is not None and row["cell"] == name, (cell_id, name)


def test_refused_cells_never_bind_a_cloud_readable_reading():
    """被拒的分数/时延格若也绑名，只能绑本机专属那一侧——两单分家必须一致。"""
    for cell_id in planner.OUT_OF_SCOPE_CELLS:
        names = planner.CELLS[cell_id].r453_cells
        assert all(name in planner.R453_LOCAL_ONLY_CELLS for name in names), (cell_id, names)


def test_counter_evidence_a_name_off_the_roster_raises_instead_of_passing():
    """返工令第 2 条：表外一格名 ⇒ 走异常，不许静默通过（臆造一枚"看着像"的名）。"""
    bogus = planner.R453_ROSTER[0] + "_typo"
    assert bogus not in planner.r453_cell_names()
    item = replace(planner.CELLS["A2-stream-verbatim"], r453_cells=(bogus,))
    with pytest.raises(planner.RosterError) as caught:
        planner.r453_binding(item)
    assert bogus in str(caught.value), str(caught.value)


def test_counter_evidence_a_bad_binding_breaks_the_catalog_selfcheck():
    """整本 catalog 的自校对同样拦得住：绑一枚名册外的名，装载口径当场红。"""
    catalog = {cid: item for cid, item in planner.CELLS.items()}
    catalog["D-usage-nonzero"] = replace(catalog["D-usage-nonzero"],
                                         r453_cells=("this_cell_exists_in_no_roster",))
    with pytest.raises(planner.RosterError):
        planner.validate_catalog_binding(list(catalog.values()))


def test_a_shape_cell_the_roster_cannot_prove_lands_in_unattainable_by_name():
    """返工令第 3 条：名册证不了的格只能认缺，不许硬凑映射，且要说清缺哪一处读数。

    今天请求的 7 枚全部能证（`r453_unproven_shape_cells` 现算为空），
    所以这条用一枚临时造的空绑定格走真代码路径，用完立刻摘掉。
    """
    base = planner.CELLS["A2-stream-verbatim"]
    orphan = replace(base, cid="A9-orphan", r453_cells=())
    gaps = planner.roster_gap_reasons([orphan])
    assert list(gaps) == ["A9-orphan"], gaps
    reason = gaps["A9-orphan"]
    assert planner.UNVERIFIED not in reason, reason
    assert orphan.surface in reason, reason
    planner.CELLS["A9-orphan"] = orphan
    try:
        plan = _plan(["A9-orphan", "D-usage-nonzero"])
    finally:
        del planner.CELLS["A9-orphan"]
    assert "A9-orphan" in plan["unattainable_here"], plan["unattainable_here"]
    assert plan["r453_unproven_shape_cells"] == ["A9-orphan"]


def test_counter_evidence_an_unbound_cell_must_be_declared_unattainable():
    """返工令第 1、3 条的接口牙：把一枚格的绑定抹掉又不声明未验
    ＝两单接口又脱开，validate_plan 必须把它点名报错，不许静默通过。
    """
    plan = _plan()
    broken = dict(plan)
    broken["r453_binding"] = {**plan["r453_binding"], "A2-stream-verbatim": []}
    with pytest.raises(planner.RosterError) as caught:
        planner.validate_plan(broken)
    message = str(caught.value)
    assert "A2-stream-verbatim" in message, message
    assert "unattainable_here" in message, message
    # 装回原样：同一个计划必须通过
    planner.validate_plan(plan)


def test_reverse_coverage_names_every_cloud_cell_this_window_never_reads():
    """返工令第 4 条：没被任何 r453_cells 引用的云端可读格必须报得出来，而且是现算的。"""
    plan = _plan()
    used = {name for item in planner.CELLS.values() for name in item.r453_cells}
    expected = [name for name in planner.R453_CLOUD_CELLS if name not in used]
    assert plan["r453_cloud_unreferenced"] == expected, (
        plan["r453_cloud_unreferenced"], expected)
    with pytest.raises(planner.RosterError):
        planner.validate_plan({**plan, "r453_cloud_unreferenced": []})


def test_the_planner_uses_only_the_imported_roster_no_second_copy_in_code():
    """本件与测试都不许落第二份名册：格名总量、云端数全部现读对面件。"""
    snapshot = _plan()["r453_roster_snapshot"]
    assert snapshot["path"] == planner.R453_ROSTER_REL
    assert snapshot["cells_total"] == len(planner.r453_cell_names())
    assert snapshot["cloud_readable"] == len(planner.R453_CLOUD_CELLS)
    assert snapshot["local_only"] == len(planner.R453_LOCAL_ONLY_CELLS)
    assert snapshot["cloud_readable"] + snapshot["local_only"] == snapshot["cells_total"]


def test_the_approval_ledger_field_is_claimed_by_a_roster_cell():
    """批准台账的算料位必须能在名册里找到东家，不能当野数据用。"""
    plan = _plan()
    owner = plan["r453_ledger_binding"][planner.LEDGER_FIELD]
    assert owner is not None, plan["r453_ledger_binding"]
    assert owner in planner.R453_CLOUD_CELLS, owner
    assert planner.LEDGER_FIELD in planner.r453_reading_fields(owner)


def test_the_window_reads_every_report_question_once_per_phase():
    """返工令第 5 条落在窗计划里：report 族配额抬到 12 之后，队列相要吃满报告档那 12 枚。"""
    subset_ids = _subset_ids()
    report_ids = [qid for qid in subset_ids if qid.startswith("report-")]
    assert len(report_ids) == planner.FAMILY_FLOOR_OVERRIDES["report"] == 12, report_ids
    plan = _plan()
    stream, queue = plan["windows"][0]["phases"]
    assert queue["question_ids"] == report_ids
    assert plan["windows"][0]["question_plays"] == len(subset_ids) + len(report_ids)


# ==================== 返工补令：D sources 那枚格的「在场≠非空」 ====================
#
# 总控裁定：帧账的 event_tally 只存事件名不存载荷，`sources_present` 的真义是「出现过一枚
# sources 事件」，一条 `sources: []` 空列表照样过；D 判据要的是「引用可查回」。所以这一枚
# 判据格必须同时覆盖「事件在场」与「引用载荷形状」两枚读数位，且这两枚不许由同一枚名册格
# 一手包办。下面的断言一枚名册格名都不写死：供给格全部由 planner 现读对面件算出来。


def _payload_shape_supplier(cell_id="D-sources-in-stream"):
    item = planner.CELLS[cell_id]
    assert item.r453_payload_fields, item
    shape_field = item.r453_payload_fields[-1]
    suppliers = [name for name in item.r453_cells
                 if shape_field in planner.r453_reading_fields(name)]
    return item, shape_field, suppliers


def test_the_retrievable_cell_declares_presence_and_payload_fields():
    """判据格自己声明必须读到哪两枚读数位，两枚各有东家，东家全在名册的云端可读侧。"""
    item, _shape_field, _suppliers = _payload_shape_supplier()
    coverage = planner.r453_field_coverage(item)
    assert coverage["fields"] == list(item.r453_payload_fields), coverage
    assert coverage["missing"] == [], coverage
    assert coverage["closable"] is True, coverage
    assert coverage["owner_count"] >= planner.REQUIRED_FIELD_SUPPLIERS_MIN, coverage
    for field, names in coverage["suppliers"].items():
        assert names, (field, coverage)
        for name in names:
            assert name in planner.R453_CLOUD_CELLS, (field, name)
            assert name in item.r453_cells, (field, name)


def test_the_plan_carries_the_payload_coverage_for_every_declaring_cell():
    """计划里这一位是现算的：每枚声明了必读读数位的形状格都要有一条覆盖，且都够闭格。"""
    plan = _plan()
    declaring = [cid for cid in plan["cells"] if planner.CELLS[cid].r453_payload_fields]
    assert sorted(plan["r453_payload_coverage"]) == sorted(declaring), plan["r453_payload_coverage"]
    for coverage in plan["r453_payload_coverage"].values():
        assert coverage["missing"] == [] and coverage["closable"], coverage


def test_counter_evidence_dropping_any_payload_supplier_turns_red():
    """把「形状」那一侧的绑定摘掉（摘的是名册现算出来的那一枚供给格）⇒ 当场红，不许静默通过。

    这里不写死格名：对每一枚声明的读数位，现算它的供给格，挨个摘掉再回表——
    两枚供给格少哪一枚都凑不齐，所以两形都必须红，且红的话语里点名缺的那枚读数位。
    """
    item, _shape_field, _suppliers = _payload_shape_supplier()
    planner.validate_catalog_binding([item])  # 原样：不抛
    for field in item.r453_payload_fields:
        suppliers = [name for name in item.r453_cells
                     if field in planner.r453_reading_fields(name)]
        assert suppliers, (field, item.r453_cells)
        thinner = replace(item, r453_cells=tuple(n for n in item.r453_cells if n not in suppliers))
        with pytest.raises(planner.RosterError) as caught:
            planner.validate_catalog_binding([thinner])
        message = str(caught.value)
        assert item.cid in message, message
        assert field in message, message


def test_counter_evidence_a_bare_sources_event_is_not_allowed_to_read_as_a_pass():
    """只喂一条 sources 事件、引用为空：这一枚格不许当过判——planner 走真路拒绝。"""
    item, shape_field, _suppliers = _payload_shape_supplier()
    presence_only = tuple(name for name in item.r453_cells
                          if shape_field not in planner.r453_reading_fields(name))
    assert presence_only and len(presence_only) < len(item.r453_cells), item.r453_cells
    thinner = replace(item, r453_cells=presence_only)
    coverage = planner.r453_field_coverage(thinner)
    assert coverage["missing"] == [shape_field], coverage
    assert coverage["closable"] is False, coverage
    planner.CELLS[item.cid] = thinner
    try:
        with pytest.raises(planner.RosterError) as caught:
            _plan()
    finally:
        planner.CELLS[item.cid] = item
    message = str(caught.value)
    assert shape_field in message, message
    assert "unattainable_here" in message, message


def test_counter_evidence_one_roster_cell_doing_both_is_refused():
    """同一枚名册格一手包办「在场」与「形状」⇒ 分不出空载荷，装载期自校对当场红。"""
    item, _shape_field, _suppliers = _payload_shape_supplier()
    solo = next(name for name in planner.R453_CLOUD_CELLS
                if len(planner.r453_reading_fields(name)) >= 2)
    fields = tuple(planner.r453_reading_fields(solo)[:2])
    forced = replace(item, cid="X-solo-supplier", r453_cells=(solo, ),
                     r453_payload_fields=fields)
    coverage = planner.r453_field_coverage(forced)
    assert coverage["missing"] == [] and coverage["owner_count"] == 1, coverage
    assert coverage["closable"] is False, coverage
    with pytest.raises(planner.RosterError) as caught:
        planner.validate_catalog_binding([forced])
    assert "一手包办" in str(caught.value), str(caught.value)


def test_counter_evidence_a_copied_payload_coverage_turns_red():
    """计划里这一位被手抄/改过一个字符 ⇒ validate_plan 与现算对不上，当场红。"""
    plan = _plan()
    tampered = json.loads(json.dumps(plan, ensure_ascii=False))
    declaring = sorted(tampered["r453_payload_coverage"])
    assert declaring, tampered
    coverage = tampered["r453_payload_coverage"][declaring[0]]
    coverage["owner_count"] = coverage["owner_count"] + 1
    with pytest.raises(planner.RosterError) as caught:
        planner.validate_plan(tampered)
    assert "抄本" in str(caught.value), str(caught.value)
