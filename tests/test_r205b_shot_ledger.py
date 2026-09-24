"""R205b · 工具循环的模型发数台账：图表 / 主动洞察两族的重派空往返。

这台量具只做一件事：在**离线** harness 上（假 provider、零 socket、零真模型）逐题数
清一次提问到底花了几发模型往返，并证明本单省掉的那一发满足两件事——

1. 它派不出任何工作（_redo_lap_is_void 的三种 shape 全集探针）；
2. 它的产出对终答没有贡献（worker_results / final_answer 字节不变）。

判据对应：
- 判据 ①（归因）：test_every_shot_is_attributed_to_a_lane_and_a_leg
- 判据 ②（收敛读数）：test_model_shot_count_converges_per_question
- 判据 ③（答案等价）：test_delivered_answer_bytes_are_identical_with_the_guard_on
- 判据 ④（反证钉）：test_counter_evidence_lift_the_void_guard_adds_the_shot_back
  与 test_counter_evidence_lift_the_log_quieting_contaminates_the_anchors
- 判据 ⑤（既往断言零放宽）：本文件不改任何既有用例，只加读数

全程不打真模型：tests/conftest.py 把 LOCAL_MODEL_NAME/OLLAMA_MODEL 清掉、把
OLLAMA_BASE_URL 钉到死端口并上闸，于是 nodes._make_model() 在 import 期就返回
_OfflineModel；本文件把那枚 _OfflineModel.invoke 换成计数器，并在用例开头断言计数器
真的看见了往返（看不见＝桩没生效＝立刻红，绝不静默放水）。
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.agents import nodes, orchestrator, tools as agent_tools
from app.agents.nodes import (
    _DISPATCHABLE_WORKERS,
    _OfflineModel,
    _probe_shapes,
    _redo_lap_is_void,
    route_reflect,
)
from langchain_core.messages import AIMessage, HumanMessage

#: 两族全表（run6 里 chart n=4 / insight n=7），外加四枚 control：
#: metric-05/06/10 与 report-01 是 run6 唯一 tool_calls==4 的那一批（本单立单的表层
#: 理由），doc-01 是问答档单腿对照组。
FAMILY_ROWS = (
    "insight-01",
    "insight-02",
    "insight-03",
    "insight-04",
    "insight-05",
    "insight-06",
    "insight-07",
    "chart-01",
    "chart-02",
    "chart-03",
    "chart-04",
)
CONTROL_ROWS = ("metric-05", "metric-06", "metric-10", "report-01", "doc-01")
LEDGER_ROWS = FAMILY_ROWS + CONTROL_ROWS

#: 逐题期望的模型发数：(摘掉守卫, 装上守卫)。数字来自本文件自己跑出来的台账，
#: 不是从 run6 的 tool_calls 抄的——那枚字段是派发腿数，与模型发数是两回事。
EXPECTED_SHOTS: dict[str, tuple[int, int]] = {
    "insight-01": (4, 4),
    "insight-02": (4, 4),
    "insight-03": (4, 4),
    "insight-04": (4, 4),
    "insight-05": (4, 3),
    "insight-06": (4, 4),
    "insight-07": (6, 5),
    "chart-01": (4, 3),
    "chart-02": (6, 5),
    "chart-03": (6, 5),
    "chart-04": (6, 5),
    "metric-05": (4, 4),
    "metric-06": (4, 4),
    "metric-10": (4, 4),
    "report-01": (4, 4),
    "doc-01": (4, 3),
}

_FIXTURE = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"

#: 工具正文桩：图例只关心发了几发、派了谁，正文换成固定短句，
#: 于是 final_answer 的字节差只可能来自路由，不可能来自检索。
_TOOL_STUBS = {
    "search_docs": "【知识检索】报销需附发票。",
    "analyze_data": "【数据结果】各部门费用合计如下。",
    "query_data": "【取数结果】费用明细如下。",
    "generate_chart": "![chart](/api/v1/artifacts/r205b.png)",
    "export_report": "【报告】已生成，下载地址 /api/v1/artifacts/r205b.docx",
}

_LEG_BY_TOOLS = {
    ("dispatch",): "supervisor",
    ("search_docs",): "doc",
    ("analyze_data", "query_data"): "data",
    ("analyze_data", "generate_chart"): "chart",
    ("analyze_data", "export_report"): "export",
}


def _questions() -> dict[str, str]:
    rows = {}
    for line in _FIXTURE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        rows[item["id"]] = item["question"]
    return rows


def _leg_of(tool_names) -> str:
    return _LEG_BY_TOOLS.get(tuple(sorted(tool_names or ())), ",".join(tool_names or ()) or "unknown")


def _drive(question: str) -> dict:
    """跑一题完整图，返回模型发数台账 + 交付面读数。"""
    shots = _SHOTS
    shots.clear()
    logs = _LOG_LINES
    logs.clear()
    config = {
        "configurable": {
            "thread_id": "r205b-" + question[:8] + "-" + str(len(_RUNS)),
            "username": "r205b",
            "role": "staff",
            "department": "finance",
            "data_filename": "r205b.xlsx",
            "principal": {"user_id": "r205b-u", "username": "r205b", "roles": ["staff"]},
        }
    }
    state = orchestrator.queue_graph.invoke(
        {
            "messages": [HumanMessage(content=question)],
            "worker_results": {"__reset__": {}},
            "agent_results": {"__reset__": {}},
        },
        config=config,
    )
    return {
        "shots": [dict(shot) for shot in shots],
        "count": len(shots),
        "legs": [shot["leg"] for shot in shots],
        "final_answer": str(state.get("final_answer") or ""),
        "worker_results": {k: str(v) for k, v in (state.get("worker_results") or {}).items()},
        "agent_results": sorted((state.get("agent_results") or {}).keys()),
        "reflect_count": state.get("reflect_count"),
        "redo": state.get("redo"),
        "message_count": len(state.get("messages") or []),
        "reflect_passes": _reflect_passes(),
        "supervisor_prompts": [
            shot["prompt"] for shot in shots if shot["leg"] == "supervisor"
        ],
    }


_SHOTS: list[dict] = []
_RUNS: list[str] = []
_LOG_LINES: list[str] = []


def _reflect_passes() -> int:
    """reflect 节点今天到底跑了几轮：直接数它自己那行账，不靠 state 里的计数器。"""
    return sum(1 for line in _LOG_LINES if line.startswith("[Reflect] redo="))


@pytest.fixture(scope="module")
def ledger():
    """离线台账：每一题跑两遍——摘掉守卫 / 装上守卫。跑完即拆桩。"""
    questions = _questions()
    missing = [row for row in LEDGER_ROWS if row not in questions]
    assert not missing, f"评测集缺题，台账无法复现：{missing}"

    import logging

    original_invoke = _OfflineModel.invoke
    original_guard = nodes._redo_lap_is_void

    class _Capture(logging.Handler):
        def emit(self, record):
            try:
                _LOG_LINES.append(record.getMessage())
            except Exception:  # pragma: no cover - 桩本身不许拖垮台账
                pass

    handler = _Capture(level=logging.INFO)
    watched = nodes.logger
    previous_level = watched.level
    watched.addHandler(handler)
    watched.setLevel(logging.INFO)
    patched_tools = {}
    for name, text in _TOOL_STUBS.items():
        tool = getattr(agent_tools, name)
        patched_tools[name] = tool.func
        tool.func = (lambda payload: (lambda query="", *a, **k: payload))(text)

    def counting_invoke(self, messages, config=None, **kwargs):
        out = original_invoke(self, messages, config=config, **kwargs)
        _SHOTS.append(
            {
                "leg": _leg_of(getattr(self, "tool_names", None)),
                "n_messages": len(messages or []),
                "calls": [call["name"] for call in (getattr(out, "tool_calls", None) or [])],
                "chars": len(str(out.content or "")),
                "prompt": "|".join(
                    f"{type(m).__name__}:{str(getattr(m, 'content', '') or '')}"
                    for m in (messages or [])
                ),
            }
        )
        return out

    _OfflineModel.invoke = counting_invoke
    table = {}
    try:
        for mode, guard in (("guard_off", lambda state, config: False), ("guard_on", original_guard)):
            nodes._redo_lap_is_void = guard
            for row in LEDGER_ROWS:
                _RUNS.append(f"{mode}:{row}")
                table.setdefault(row, {})[mode] = _drive(questions[row])
    finally:
        watched.removeHandler(handler)
        watched.setLevel(previous_level)
        _OfflineModel.invoke = original_invoke
        nodes._redo_lap_is_void = original_guard
        for name, func in patched_tools.items():
            getattr(agent_tools, name).func = func
    assert table, "台账一枚都没跑出来"
    return table


def _assert_offline_only(table) -> None:
    total = sum(row["count"] for side in table.values() for row in side.values())
    assert total > 0, "桩没生效：整个台账一个模型往返都没看见"


def test_ledger_is_recorded_offline_and_sees_every_roundtrip(ledger):
    """这台量具自己得先能被证明是离线且咬得住的。"""
    _assert_offline_only(ledger)
    for row, value in ledger.items():
        assert {"guard_off", "guard_on"} <= set(value), row
        assert value["guard_off"]["count"] >= 3, f"{row}: 连一发 supervisor 加一腿都没跑满，台账失真"


def test_every_shot_is_attributed_to_a_lane_and_a_leg(ledger):
    """判据 ①：每一发模型往返都能报出它是谁发的、带着几条消息。

    钉住两族今天的构成：supervisor 的往返数恒等于「派发轮数」，而最后一发 supervisor
    往返带着同样的 2 条消息（sys + 本轮问题）——worker 结果一个字都不进它的 prompt，
    所以那一发能买回来的只有第 1 发已经说过的话。
    """
    for row in FAMILY_ROWS:
        shots = ledger[row]["guard_off"]["shots"]
        sup = [s for s in shots if s["leg"] == "supervisor"]
        assert sup, row
        assert all(s["n_messages"] == 2 for s in sup), f"{row}: supervisor 的 prompt 不再只有两条消息，归因段作废"
        for shot in shots:
            assert shot["leg"] in _LEG_BY_TOOLS.values(), f"{row}: 认不出这一发是谁发的：{shot['leg']}"


def test_supervisor_prompt_is_byte_identical_across_laps(ledger):
    """重派轮那一发的输入与第 1 发逐字节相同——本单省掉它时唯一依赖的事实本身。

    这条不证明模型会复读（探针也不需要它），它证明的是另一句话：reflect 的否决理由
    根本没进 supervisor 的上下文，所以那一发在信息上是空的。
    """
    for row, side in ledger.items():
        prompts = side["guard_off"]["supervisor_prompts"]
        assert len(prompts) >= 1, row
        assert len(set(prompts)) == 1, f"{row}: supervisor 各轮输入不同，归因段需要重写"


def test_model_shot_count_converges_per_question(ledger):
    """判据 ②：逐题读数。降不到 1 就如实写降到几。"""
    _assert_offline_only(ledger)
    for row in LEDGER_ROWS:
        assert set(LEDGER_ROWS) <= set(ledger)
        observed = (ledger[row]["guard_off"]["count"], ledger[row]["guard_on"]["count"])
        assert observed == EXPECTED_SHOTS[row], f"{row}: 收敛读数变了（期望 摘守卫/装守卫 {EXPECTED_SHOTS[row]}，实得 {observed}）"


def test_only_the_supervisor_lane_shrinks(ledger):
    """省掉的一发必然落在 supervisor 头上，worker 腿一发没少。"""
    for row in LEDGER_ROWS:
        off, on = ledger[row]["guard_off"], ledger[row]["guard_on"]
        assert sorted(s for s in off["legs"] if s != "supervisor") == sorted(
            s for s in on["legs"] if s != "supervisor"
        ), f"{row}: 探针改动动到了 worker 腿"
        assert off["legs"][: len(on["legs"])] == on["legs"], f"{row}: 守卫不是截掉尾巴，而是改了路径形状"


def test_delivered_answer_bytes_are_identical_with_the_guard_on(ledger):
    """判据 ③：终答与全部中间产出的字节等价。

    只对守卫**没**发力的行做逐题字节比较是不够的，发力那几行更要比：
    insight-05 / insight-07 / chart-01..04 / doc-01 的 final_answer 与 worker_results
    在两态下必须一模一样，少掉的那一发只在 messages 里多一条空正文 dispatch。
    """
    fired = [row for row in LEDGER_ROWS if EXPECTED_SHOTS[row][0] != EXPECTED_SHOTS[row][1]]
    assert fired == ["insight-05", "insight-07", "chart-01", "chart-02", "chart-03", "chart-04", "doc-01"], fired
    for row in LEDGER_ROWS:
        off, on = ledger[row]["guard_off"], ledger[row]["guard_on"]
        assert on["final_answer"] == off["final_answer"], f"{row}: 终答字节变了"
        assert on["worker_results"] == off["worker_results"], f"{row}: worker 正文变了"
        assert on["agent_results"] == off["agent_results"], f"{row}: 证据面变了"
    for row in fired:
        off, on = ledger[row]["guard_off"], ledger[row]["guard_on"]
        assert on["message_count"] == off["message_count"] - 1, f"{row}: 少的不是一发往返"
        # 少的这一发只可能来自重派轮：reflect 今天在这几行上跑了两轮，装上守卫后只剩一轮。
        assert off["reflect_passes"] == 2 and on["reflect_passes"] == 1, (
            f"{row}: reflect 轮数 {off['reflect_passes']}→{on['reflect_passes']}，少的不是重派轮"
        )
        # 诚实记账：交付面之外唯一真实变了的一格是 state["redo"]。装上守卫后它恒为 True
        # （停在第一枚 redo 裁定上），今天则可能 True 也可能 False，取决于第二轮 reflect
        # 有没有改口——两态都在 synthesize 之前收工，而 app/ 全库只有 route_reflect 与
        # main_agent_node 读它（均已发生），没有任何交付物读它。上面三条字节断言就是这句
        # 话的全部证据面，这一格明写出来，不藏着。
        assert on["redo"] is True, f"{row}: 守卫应当停在第一枚 redo 裁定上"


def test_guard_fires_exactly_where_the_reflect_verdict_is_a_redo(ledger):
    """守卫只在 reflect 判了重派的行上发力，其余行路径一字不动。"""
    for row in LEDGER_ROWS:
        off, on = ledger[row]["guard_off"], ledger[row]["guard_on"]
        fired = off["count"] != on["count"]
        assert fired is (EXPECTED_SHOTS[row][0] != EXPECTED_SHOTS[row][1]), row
        if fired:
            assert off["reflect_passes"] == 2, f"{row}: 发力行今天没有跑满两轮 reflect"
            assert on["reflect_passes"] == 1, f"{row}: 装上守卫后仍然白跑了一轮 reflect"


def test_counter_evidence_lift_the_void_guard_adds_the_shot_back(ledger):
    """反证钉 A：把 _redo_lap_is_void 摘成恒 False，收敛读数当场变红。

    这就是「摘了不红＝没钉」的那一枚：EXPECTED_SHOTS 里任何一行只要守卫被摘掉就必然
    多出一发，台账与判据② 的用例双双失败。
    """
    lifted = {row: value["guard_off"]["count"] for row, value in ledger.items()}
    shipped = {row: value["guard_on"]["count"] for row, value in ledger.items()}
    assert sum(lifted.values()) > sum(shipped.values()), "摘掉守卫后发数没变——这枚短路是死代码"
    assert lifted["chart-01"] == shipped["chart-01"] + 1, lifted
    assert lifted["chart-02"] == shipped["chart-02"] + 1, lifted
    assert lifted["insight-07"] == shipped["insight-07"] + 1, lifted


def test_counter_evidence_probe_shapes_cover_the_whole_dispatch_space():
    """反证钉 B：探针枚举的是那一发的全部输出，少一种 shape 就当场变红。

    32 种派发子集 + 1 种纯正文＝33；名字集必须与 route_main 里的 valid 字面量同源，
    否则将来多出第六枚腿时探针会「探不出可疑」而静默放行。
    """
    shapes = _probe_shapes()
    assert len(shapes) == 2 ** len(_DISPATCHABLE_WORKERS) + 1 == 33, len(shapes)
    assert all(isinstance(s, AIMessage) for s in shapes)
    assert sum(1 for s in shapes if not getattr(s, "tool_calls", None)) == 1

    source = inspect.getsource(orchestrator.route_main)
    literal = re.search(r"valid = \{([^}]*)\}", source)
    assert literal, "route_main 里的 valid 字面量形状变了，探针名字集需要重新对齐"
    named = tuple(sorted(part.strip().strip('"\'') for part in literal.group(1).split(",")))
    assert named == tuple(sorted(_DISPATCHABLE_WORKERS)), (
        f"腿名集漂移：route_main={named} 探针={tuple(sorted(_DISPATCHABLE_WORKERS))}"
    )


def test_counter_evidence_a_dispatchable_leg_blocks_the_short_circuit():
    """反证钉 C：只要模型还可能派出一条未完成的腿，守卫就必须闭嘴。

    拿 insight-01（守卫**没**发力的行）作样：它的 plan 只有一条 doc，data 从未跑过，
    所以「这一发改派 data」是完全合法的输出 ⇒ 探针必须判非无效。把短路条件写松
    （例如只复读本轮那条 dispatch）这枚用例当场红。
    """
    question = _questions()["insight-01"]
    state = {
        "messages": [
            HumanMessage(content=question),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "dispatch", "args": {"workers": ["doc"]}, "id": "s1", "type": "tool_call"}
                ],
            ),
        ],
        "plan": [{"worker": "doc", "objective": "step-doc"}],
        "worker_results": {"doc": "【知识检索】报销需附发票。"},
        "redo": True,
        "reflect_count": 1,
    }
    assert _redo_lap_is_void(state, None) is False, "insight-01 还能派 data，短路它＝拿准确率换时延"
    assert route_reflect(state) == "supervisor"


def test_counter_evidence_a_blank_worker_result_blocks_the_short_circuit():
    """反证钉 D：终答来源为空时那一发散文就是答案本身，不许省。

    worker_results 全空（或全空白）时 synthesize 与 chat.py::_select_final_answer 都会
    退回去读 supervisor 的正文，这时候短路会真的改变交付。
    """
    question = _questions()["chart-01"]
    state = {
        "messages": [
            HumanMessage(content=question),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "dispatch", "args": {"workers": ["chart"]}, "id": "s1", "type": "tool_call"}
                ],
            ),
        ],
        "plan": [{"worker": "chart", "objective": "step-chart"}],
        "worker_results": {"chart": "   "},
        "redo": True,
        "reflect_count": 1,
    }
    assert _redo_lap_is_void(state, None) is False
    assert route_reflect(state) == "supervisor"


def test_the_two_changed_state_channels_have_no_consumer_outside_the_graph():
    """本单只留下两格读数差：「redo」与「reflect_count」，都在 synthesize 之前收工。

    这句不是修辞：全仓 app/ 里提到这两格的文件只有 state.py（声明）与图自己的两枚节点。
    交付路径（chat.py / synthesize / evidence）一个字都不读它们，所以少掉一发往返不会以
    「状态少一格」的形式漏到客户端。哪天有人在图外面读它们，这枚用例先红。
    """
    root = Path(nodes.__file__).parent.parent
    readers = set()
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if '"redo"' in text or "reflect_count" in text:
            readers.add(path.name)
    assert readers <= {"nodes.py", "orchestrator.py", "state.py"}, sorted(readers)

def test_legacy_direct_calls_keep_todays_verdict():
    """既有单参数直调（test_phase1_arch / test_r42_fallback_upgrade 的形状）一字不变。"""
    assert route_reflect({"redo": True, "reflect_count": 1}) == "supervisor"
    assert route_reflect({"redo": False, "reflect_count": 1}) == "synthesize"
    assert route_reflect({"redo": True, "reflect_count": 2}) == "synthesize"
    assert route_reflect({"redo": True, "reflect_count": 1, "messages": [], "worker_results": {}}) == "supervisor"


def test_counter_evidence_lift_the_log_quieting_contaminates_the_anchors():
    """反证钉 E：探针的读数账静音被摘掉时，锚点频次当场被踩脏。

    [R42] 那行的**频次**是 R51 读表口径的一部分（stage_timing.R42_LOG_PATTERN 逐字节
    钉形状），[Route] 那行是派发轮的唯一读数。route_probe_quiet 恒 False 之后，探针
    光是「探」就得多敲几行钟——观测改了被测，这枚用例立刻红。

    样题取 insight-01：它的探针会在第 3 种 shape 上判非无效并停下，但空派发那一种
    shape 已经先把 classify_route 敲过一遍了，所以脏数据是必然会留下的。
    """
    import logging

    question = _questions()["insight-01"]
    state = {
        "messages": [
            HumanMessage(content=question),
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "dispatch", "args": {"workers": ["doc"]}, "id": "s1", "type": "tool_call"}
                ],
            ),
        ],
        "plan": [{"worker": "doc", "objective": "step-doc"}],
        "worker_results": {"doc": "【知识检索】报销需附发票。"},
        "redo": True,
        "reflect_count": 1,
    }
    quiet_nodes = nodes.route_probe_quiet
    quiet_orch = orchestrator.route_probe_quiet
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture(level=logging.INFO)
    watched = [nodes.logger, orchestrator.logger]
    levels = [logger.level for logger in watched]
    for logger in watched:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        assert _redo_lap_is_void(state, None) is False
        quiet_hits = _route_anchor_lines(records)

        records.clear()
        nodes.route_probe_quiet = lambda: False
        orchestrator.route_probe_quiet = lambda: False
        try:
            assert _redo_lap_is_void(state, None) is False
            loud_hits = _route_anchor_lines(records)
        finally:
            nodes.route_probe_quiet = quiet_nodes
            orchestrator.route_probe_quiet = quiet_orch
    finally:
        for logger, level in zip(watched, levels):
            logger.removeHandler(handler)
            logger.setLevel(level)

    assert quiet_hits == [], f"探针在静音窗口内仍然敲了路由账：{quiet_hits}"
    assert loud_hits, "摘掉静音之后探针一行账都不敲，说明它根本没走真 route_main"


def _route_anchor_lines(lines) -> list[str]:
    return [line for line in lines if line.startswith("[R42] '") or line.startswith("[Route] ")]
