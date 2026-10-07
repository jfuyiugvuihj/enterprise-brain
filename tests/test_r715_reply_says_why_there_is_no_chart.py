r"""R715 判据 2＋3 的答复侧 —— 图腿登记不下时，屏上必须写清「为什么没有图」。

与在册两枚针的分工（动手前 rg 过名册，三格互不认领）：
  * ``tests/test_r703_reply_never_fakes_a_chart.py`` 钉的是「文字冒充屏上已有图」那一格，
    ``app/agents/nodes.py::_carry_chart_truth`` 的句子按措辞红线**不许**说因由，而且对
    「无法生成柱状图」那类答复刻意闭嘴；
  * ``tests/test_r710_reply_never_fakes_an_exported_report.py`` 钉的是导出腿冒充报告那一格，
    日志点名 leg=export；
  * 本件钉走查环 7 的另一半：图腿一路走到 ``app/storage/artifacts.py::ArtifactRegistry.register``
    被拒，那一轮 ``chart_artifact.found=false``、``total=0``、``charts_on_screen=0``，而终答正文
    6 250 字里没有一个字交代原因（凭据
    ``docs/testing/walkthrough-2026-10-06/README.md`` 缺陷 #2 与账本 rings[ring=7].readings）。
    守卫是 ``app/agents/nodes.py::_carry_chart_leg_truth``：只追加不改写、判据只读物证，
    日志点名 leg=chart。

四条都可失败：
  1) 🔴 反证牙·置空台账：本轮真登记过一枚图、而读账那一枚函数被摘掉 ⇒ 本腿必须开口说人话；
  2) 🔴 反证牙·放一枚真件：台账里躺着本轮真出的图 ⇒ 本腿必须闭嘴，一个字都不许多；
  3) 屏上那句的具名格与读数面同源：正文里的 error_code=… 必须等于图腿那一行交回的码；
  4) 表外的码、别的腿的码、屏上已经写过这枚码、屏上连一个字都没有 ⇒ 一律闭嘴。

全程离线：不产文件、不打模型、不起容器。
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.agents import evidence, nodes, tools

QUESTION = "按月份统计报销金额，并画一张柱状图"
REFUSAL_CODE = "department_scope_required"

#: 模型冒充屏上有图的那一份正文（环 7 那一轮的真形状：图一个都没有，字却写了 6 250 枚）。
IMPERSONATED_ANSWER = "已按月份汇总报销金额，并生成柱状图如下：\n![月度报销柱状图](/static/chart-715.png)"

#: 环 7 终答里真出现过的句子（R703 的针要求它对「声称」闭嘴，本针要求它替因由开口）。
REFUSAL_ANSWER = (
    "无法直接生成按月份统计的报销金额柱状图，因为：\n"
    "1. 文档中未包含实际报销数据：所有文档均为制度、流程、规范类文件。"
)

#: 工具腿改后自己那句诚实话（app/agents/tools.py::_CHART_NO_DEPARTMENT_HEAD 的形状）。
HONEST_REFUSAL = (
    "本轮没有生成图表文件：产物台账要求发起这一轮的账号有部门归属，而这个账号的部门是空的。"
    "（error_code=department_scope_required）"
)


def _sentence(code: str = REFUSAL_CODE) -> str:
    """屏上应当长出的那一句：模板与码名都从 app 侧读，本件不抄第二份。"""
    return nodes.CHART_LEG_TRUTH_SENTENCE.format(
        reason=nodes._CHART_LEG_REFUSAL_HEADS[code], code=code
    )


def _chart_row() -> dict:
    return {
        "artifact_id": "art-" + uuid4().hex[:8],
        "artifact_type": "chart",
        "download_url": "/api/v1/artifacts/art-715/download",
    }


def _state(
    legs: dict,
    artifacts: list | None,
    refusal_code: str = REFUSAL_CODE,
    worker: str = "chart",
) -> dict:
    """一轮的终态：legs = 各条腿交回的正文，artifacts = 登记下来的件，refusal_code = 读数面那枚码。"""
    row = {
        "worker": worker,
        "status": "success" if artifacts else "failed",
        "answer": next(iter(legs.values()), ""),
        "artifacts": list(artifacts or []),
        "evidence": [],
    }
    if refusal_code:
        row["error"] = {
            "code": refusal_code,
            "message": f"{worker} worker finished with status={row['status']}",
            "retryable": False,
            "details": {"worker": worker, "status": row["status"]},
        }
    return {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": dict(legs),
        "agent_results": {worker: row},
    }


# ==================== 1) 图腿拒了、台账零枚 ⇒ 钉一句因由 ====================


@pytest.mark.parametrize("answer", [IMPERSONATED_ANSWER, REFUSAL_ANSWER, "本月报销合计 17 100 元。"])
def test_a_refused_chart_leg_with_an_empty_ledger_gets_the_reason_sentence(answer) -> None:
    """三条都可失败：声称有图的、明说生不成的、通篇没提图的——因由都还没上屏，都得补一句。"""
    result = nodes.synthesize(_state({"chart": answer}, []))

    final = result["final_answer"]
    expected = _sentence()
    assert expected in final, final[-300:]
    assert final.endswith(expected), "补写必须落在末尾，不许插进模型已经写的字"
    assert final.startswith(answer), "只许追加，不许改写"
    assert "部门" in final, final[-300:]
    assert list(result["worker_results"]) == ["chart"], result["worker_results"]


def test_the_reason_line_names_the_leg_and_the_code_it_read(caplog) -> None:
    """判据 2 要日志点名 leg=chart：光说 artifacts=0 不够，得写清这一句是替图腿还的债。"""
    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        final = nodes.synthesize(_state({"chart": IMPERSONATED_ANSWER}, []))["final_answer"]

    marked = [
        record.message
        for record in caplog.records
        if nodes.CHART_LEG_TRUTH_MARKER in record.message
    ]
    assert marked, caplog.messages
    assert "leg=chart" in marked[0], marked[0]
    assert f"refusal_code={REFUSAL_CODE}" in marked[0], marked[0]
    assert "artifacts=0" in marked[0], marked[0]
    assert _sentence() in final, final[-300:]


# ==================== 3) 具名格与读数面同源（离线真跑一趟工具腿） ====================


def test_the_named_slot_in_the_answer_is_the_code_the_ledger_actually_holds(
    monkeypatch, tmp_path
) -> None:
    """一手链条：假模型 + 真工具腿 + 真装配 + 真 synthesize，屏上那枚码必须就是账上那枚。

    写域自证：假图字节只写 tmp_path，登记表根也落在 tmp_path——仓库里的 static/ 一个字都不动。
    """
    from app.storage import artifacts as artifacts_module
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(
        root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json"
    )
    monkeypatch.setattr(artifacts_module, "artifact_registry", registry)
    directory = tmp_path / "charts"
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def fake_png(*args, **kwargs) -> str:
        path = directory / f"chart_{uuid4().hex[:10]}.png"
        path.write_bytes(b"\x89PNG r715")
        written.append(str(path))
        return str(path)

    from app.tools import chart as chart_module

    monkeypatch.setattr(chart_module, "bar_chart", fake_png)

    bag = evidence.new_evidence_bag()
    config = {
        "configurable": {
            "id": "r715-nodept",
            "username": "r715-nodept",
            "role": "admin",
            "department": "",
            "thread_id": "sess-r715-" + uuid4().hex[:8],
            "request_id": "req-r715-" + uuid4().hex[:8],
            "evidence_bag": bag,
        }
    }
    leg_answer = tools.generate_chart.invoke(
        {"chart_type": "bar", "labels": ["1月"], "values": [10], "title": "月度报销柱状图"},
        config=config,
    )
    agent_result = evidence.build_agent_result(
        worker="chart", answer=IMPERSONATED_ANSWER, bag=bag
    )
    state = {
        "messages": [HumanMessage(content=QUESTION)],
        "plan": [],
        "worker_results": {"chart": IMPERSONATED_ANSWER},
        "agent_results": {"chart": agent_result.model_dump(mode="json")},
    }

    final = nodes.synthesize(state)["final_answer"]

    assert written == [], written
    assert registry.list_active() == [], registry.list_active()
    assert "error_code=" in leg_answer, leg_answer
    assert agent_result.error is not None
    assert agent_result.error.code == REFUSAL_CODE, agent_result.error
    assert f"error_code={agent_result.error.code}" in final, final[-300:]
    assert _sentence(agent_result.error.code) in final, final[-300:]
    assert nodes.CHART_TRUTH_SENTENCE in final, "R703 那一格仍然要开口：两句各还各的债"


# ==================== 2) 🔴 反证牙：放一枚真件 ⇒ 必须闭嘴 ====================


def test_one_registered_chart_artifact_keeps_the_leg_silent(caplog) -> None:
    artifacts = [_chart_row()]
    state = _state({"chart": IMPERSONATED_ANSWER}, artifacts)
    assert nodes._chart_artifacts_in_state(state) == artifacts

    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        result = nodes.synthesize(state)

    # R725 之后「一个字都不动」不再由本腿独享：本轮有图而正文里没有那行 embed，贴图那一腿
    # 会在末尾补一行地址。本腿要钉的仍是同一格——它自己那句因由不许上屏、模型已经写的字一个字
    # 都不许改；这格是不是本腿做的，交给下面那行台账标记说话。
    assert result["final_answer"].startswith(IMPERSONATED_ANSWER), result
    assert not [
        record.message
        for record in caplog.records
        if nodes.CHART_LEG_TRUTH_MARKER in record.message
    ], caplog.messages


def test_the_guard_reads_the_ledger_and_not_a_hardcoded_zero(monkeypatch) -> None:
    """把读账那一枚摘掉 ⇒ 本腿当场开口：这条断言证明判定真由台账决定（置空台账必须红）。"""
    artifacts = [_chart_row()]
    state = _state({"chart": IMPERSONATED_ANSWER}, artifacts)

    monkeypatch.setattr(nodes, "_chart_artifacts_in_state", lambda _state: [])

    assert _sentence() in nodes.synthesize(state)["final_answer"]


# ==================== 4) 闭嘴的四张脸 ====================


@pytest.mark.parametrize("code", ["internal_error", "permission_denied", "chart_generation_failed", ""])
def test_a_code_outside_the_table_keeps_the_leg_silent(code) -> None:
    """表外的码＝本层说不出因由 ⇒ 一句都不许编（宁可少说一句，措辞红线抄在册正例）。"""
    state = _state({"chart": IMPERSONATED_ANSWER}, [], refusal_code=code or None)

    assert nodes._chart_leg_refusal_code_in_state(state) == "", code
    result = nodes.synthesize(state)
    assert _sentence() not in result["final_answer"], result["final_answer"][-300:]
    assert nodes.CHART_TRUTH_SENTENCE in result["final_answer"], "R703 那一格照旧开口"


def test_another_legs_refusal_is_not_the_charts_reason() -> None:
    """码躺在导出腿那一行 ⇒ 图腿无权替它说话：本腿只认 worker=chart 那一行。"""
    state = _state({"export": "报告没能导出。"}, [], worker="export")

    assert nodes._chart_leg_refusal_code_in_state(state) == ""
    assert _sentence() not in nodes.synthesize(state)["final_answer"]


def test_a_screen_that_already_carries_the_code_is_not_speakened_twice() -> None:
    """工具腿那句诚实话已经上屏 ⇒ 再钉一句就是两句打脸。"""
    state = _state({"chart": HONEST_REFUSAL}, [])

    final = nodes.synthesize(state)["final_answer"]
    assert _sentence() not in final, final[-300:]
    assert final.count(f"error_code={REFUSAL_CODE}") == 1, final


def test_an_empty_screen_gets_no_invented_sentence() -> None:
    """本轮连一个字都没交付 ⇒ 本腿不许凭空长出一句话（空正文的账归 R439，不归本单）。"""
    state = _state({"chart": ""}, [])
    state["final_answer"] = ""

    result = nodes.synthesize(state)

    assert _sentence() not in str(result.get("final_answer") or ""), result
    assert "worker_results" not in result


# ==================== 判定口自己：怎么从读数面取码 ====================


def test_the_reader_accepts_a_pydantic_agent_result_row() -> None:
    """state 里躺的是 AgentResult 对象（contracts 那一型）时同样读得出码，不认字典一种形状。"""
    agent_result = evidence.build_agent_result(
        worker="chart",
        answer=IMPERSONATED_ANSWER,
        bag={
            "documents": [],
            "datasets": [],
            "artifacts": [],
            "metrics": [],
            "tool_statuses": [
                {"tool": "generate_chart", "status": "failed", "error_code": REFUSAL_CODE}
            ],
            "model_statuses": [],
        },
    )
    state = _state({"chart": IMPERSONATED_ANSWER}, [])
    state["agent_results"]["chart"] = agent_result

    assert nodes._chart_leg_refusal_code_in_state(state) == REFUSAL_CODE
    assert _sentence() in nodes.synthesize(state)["final_answer"]


@pytest.mark.parametrize(
    ("text", "code", "expected"),
    [
        (HONEST_REFUSAL, REFUSAL_CODE, True),
        (_sentence(), REFUSAL_CODE, True),
        ("本轮没有生成图表文件。", REFUSAL_CODE, False),
        ("（error_code=internal_error）", REFUSAL_CODE, False),
        ("", REFUSAL_CODE, False),
        (None, REFUSAL_CODE, False),
    ],
)
def test_says_why_there_is_no_chart_only_reads_the_same_code(text, code, expected) -> None:
    assert nodes._says_why_there_is_no_chart(text, code) is expected, text


def test_multi_leg_round_keeps_every_leg_and_writes_the_whole_table_back() -> None:
    """收端整张覆盖 worker_results：回写只带一条腿会把别的腿洗掉，追加只落最后那条有字的腿。"""
    legs = {"data": "月度合计 17 100 元。", "chart": IMPERSONATED_ANSWER}
    before = "\n\n".join(legs.values())
    state = _state(legs, [])
    state["agent_results"] = {
        "data": {"worker": "data", "status": "success", "answer": legs["data"], "artifacts": [], "evidence": []},
        "chart": state["agent_results"]["chart"],
    }

    result = nodes.synthesize(state)

    assert list(result["worker_results"]) == ["data", "chart"], result["worker_results"]
    assert result["worker_results"]["data"] == legs["data"], "别的腿被改了字"
    assert result["final_answer"].startswith(before), "已发帧必须是终答前缀"
    assert result["final_answer"] == "\n\n".join(
        [result["worker_results"][key] for key in ("data", "chart")]
    ), "终答与 worker_results 折出来的文字不一致"
    assert _sentence() in result["worker_results"]["chart"], result["worker_results"]["chart"]
