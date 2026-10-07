r"""R715 判据 1＋3 的工具侧 —— 图腿要拿到与导出腿同形的 preflight：登记不下就一条字节都不落。

一手取证（凭据纸 docs/testing/walkthrough-2026-10-06/README.md 缺陷 #2 与 #3，账本
rings[ring=7].readings）：用 admin（users.department 现读为空）问「按月份统计报销金额，并画一张
柱状图」并批准 📈 生成图表，那一轮 chart_artifact.found=false、total=0（等了 151.508 s）、
charts_on_screen=0，而终答正文 6 250 字——屏上零字说清「为什么没有图」。断点在
app/storage/artifacts.py::ArtifactRegistry.register：属主交不出部门 ⇒ 当场拒。而
app/agents/tools.py::_generate_chart 原来把登记那一腿整个裸着（它在 try 之外），拒绝从
_artifact_urls 抛出图外，由 langgraph 的 ToolNode 按 TOOL_CALL_ERROR_TEMPLATE 折成
「Error: …」交给模型：既没有稳定码，又把登记表内部的英文原句卖给了客户。R710 把导出腿拆成
四张脸并把次序反过来（先问登记表收不收），图腿一字未动——这就是本单要还的债。

本件钉改后的形状，每条都可失败：
  1) 属主没有部门 ⇒ 登记必拒：图腿在**写盘之前**叫停，一条字节都不落，台账与盘同时归零；
  2) 人话旁边必须有公开码 department_scope_required，终态 AgentResult 带同一枚码（两路同源）；
  3) 登记表与画图函数自己的英文原句一律不许出现在客户可见正文里；
  4) 拒收真落在写盘之后（race）时，那枚没人登记得上的文件当场收回；
  5) 🔴 反过来那一牙：preflight 不许把有部门的账号也拦下来——登记成功那一支仍是一枚不多。

全程离线：假模型、零容器、假图字节只写 tmp_path，仓库里的 static/charts 一枚都不许多。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.agents import evidence, tools

USERNAME = "r715-nodept"
DEPARTMENT = "r715-报销测试部"
#: 登记表与路径闸各自那句内部原句（走查环 7／环 8 现读到的形状）。
INTERNAL_REGISTRY_SENTENCE = "artifact owner must have a department scope"
INTERNAL_PATH_SENTENCE = "artifact storage path escapes registry root"
CHART_BYTES = b"\x89PNG r715 offline chart"
BAR_ARGS = {"chart_type": "bar", "labels": ["1月", "2月"], "values": [10, 20], "title": "月度报销柱状图"}
GANTT_ARGS = {
    "chart_type": "gantt",
    "labels": None,
    "values": None,
    "tasks": [{"name": "需求", "start": "2026-09-01", "end": "2026-09-03"}],
    "title": "项目甘特图",
}


def _registry(monkeypatch, tmp_path):
    """真 registry 类，根落在 tmp_path：本件一个字都不碰仓库里的 static/。"""
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    instance = ArtifactRegistry(
        root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json"
    )
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


def _fake_charts(monkeypatch, tmp_path, written: list[str]) -> list[str]:
    """假出图：字节写进 registry 根之下（生产里 static/charts 就躺在登记表根之下）。"""
    directory = tmp_path / "charts"
    directory.mkdir(parents=True, exist_ok=True)

    def fake_png(*args, **kwargs) -> str:
        path = directory / f"chart_{uuid4().hex[:10]}.png"
        path.write_bytes(CHART_BYTES)
        written.append(str(path))
        return str(path)

    def fake_html(*args, **kwargs) -> str:
        path = directory / f"chart_{uuid4().hex[:10]}.html"
        path.write_text("<html></html>", encoding="utf-8")
        written.append(str(path))
        return str(path)

    from app.tools import chart as chart_module
    from app.tools import visualize as visualize_module

    for name in ("bar_chart", "line_chart", "pie_chart", "radar_chart"):
        monkeypatch.setattr(chart_module, name, fake_png)
    monkeypatch.setattr(visualize_module, "mindmap", fake_png)
    monkeypatch.setattr(visualize_module, "gantt_chart", fake_html)
    return written


def _config(**overrides) -> dict:
    configurable = {
        "id": USERNAME,
        "username": USERNAME,
        "role": "manager",
        "department": "",
        "thread_id": "sess-r715-" + uuid4().hex[:8],
        "request_id": "req-r715-" + uuid4().hex[:8],
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _ask(config, **arguments) -> str:
    """走一次真出图：工具入口是 @tool 包装过的那一枚，不是手搓的内部函数。"""
    payload = dict(BAR_ARGS)
    payload.update(arguments)
    return tools.generate_chart.invoke(payload, config=config)


def _statuses(config) -> list[dict]:
    return config["configurable"]["evidence_bag"]["tool_statuses"]


def _refusal_rows(config) -> list[dict]:
    """图腿这一条上的终态行：跨度与 _record_denial 各记一枚（出处 app/trace/spans.py）。

    completed 那一枚不是终态——成功那一支跨度写的是 (completed, completed)，把它混进来
    就是「码与话同源」这枚钉自己的假红。本件只钉终态那几行。
    """
    return [
        item
        for item in _statuses(config)
        if item.get("tool") == "generate_chart" and item.get("status") != "completed"
    ]


def _canonical(config, answer: str):
    return evidence.build_agent_result(
        worker="chart", answer=answer, bag=config["configurable"]["evidence_bag"]
    )


# ==================== 1)＋2) 属主没有部门：写盘之前就叫停 ====================


@pytest.mark.parametrize("arguments", [BAR_ARGS, GANTT_ARGS])
def test_a_departmentless_owner_is_refused_before_a_single_byte_is_written(
    monkeypatch, tmp_path, arguments
) -> None:
    """png 与 html 两支都走同一枚 preflight：登记不上的字节根本不该先落盘。"""
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)

    answer = _ask(_config(), **arguments)

    assert written == [], f"登记不上的图根本不该落盘：{written}"
    assert list((tmp_path / "charts").glob("chart_*")) == []
    assert registry.list_active() == [], registry.list_active()
    assert "本轮没有生成图表文件" in answer, answer
    assert "部门" in answer, answer
    assert "图表已生成" not in answer, answer


def test_an_administrator_without_a_department_still_gets_the_chart(monkeypatch, tmp_path) -> None:
    """业主 10-07 裁定改口：管理员不被要求与资源同部门，没部门也该画得出自己的图。

    读那一侧早就是这条口径（``app/common/policy.py`` 的 ``administrator_scope``、
    ``app/common/rbac.py`` 的「空部门行只有 admin 看得到」），写这一侧以前只问部门，
    于是同一个账号读得到别人的图、画不出自己的图：admin 问一句「画张柱状图」，
    preflight 在写盘之前就叫停，屏上静默只剩一张表。现在这一发必须真出图、真登记。
    """
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)

    answer = _ask(_config(role="admin"), **BAR_ARGS)

    assert written, "管理员名下这一轮的图该真落盘"
    assert len(registry.list_active()) == 1, registry.list_active()
    assert "图表已生成" in answer, answer


def test_the_refusal_carries_a_public_code_and_the_ledger_reads_the_same_one(monkeypatch, tmp_path) -> None:
    """码是契约：人话旁边必须有 department_scope_required，终态信封带同一枚（两路同源）。"""
    _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)
    config = _config()

    answer = _ask(config)

    assert "error_code=department_scope_required" in answer, answer
    assert {item["error_code"] for item in _refusal_rows(config)} == {"department_scope_required"}, _statuses(config)
    result = _canonical(config, answer)
    assert result.status == "failed", result.status
    assert result.error is not None and result.error.code == "department_scope_required", result.error
    assert result.artifacts == [], result.artifacts


# ==================== 3) 内部原句一律不外泄 ====================


def test_the_internal_registry_sentence_never_reaches_the_customer(monkeypatch, tmp_path) -> None:
    """无论断在哪一格，客户可见正文里都不许出现登记表自己的英文句子。

    改前那一支根本没有这一层：拒绝从 _artifact_urls 抛出图外，由 ToolNode 折成
    「Error: artifact owner must have a department scope」进模型——本枚用同一条断言钉住改后形状。
    """
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)

    answer = tools._generate_chart("bar", _config(), labels=["1月"], values=[10])

    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer
    assert INTERNAL_PATH_SENTENCE not in answer, answer
    assert "error_code=" in answer, answer
    assert written == [], written
    assert registry.list_active() == [], registry.list_active()


# ==================== 4) 拒收落在写盘之后：那枚孤儿字节当场收回 ====================


def test_a_refusal_after_the_bytes_lands_removes_the_orphan_file(monkeypatch, tmp_path) -> None:
    """preflight 之后登记表仍然可能拒收（同一时刻改的部门、另一枚根因）。

    这一格钉的是「话与账一致」：文件真落了盘，那就既要说清没登记上、也不能留下一枚没人查得回的
    原件——台账归零时盘上那枚 PNG 必须一起归零。
    """
    from app.storage.artifacts import ArtifactOwnerScopeMissing, ArtifactRegistry

    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)

    def refuse(self, storage_path, **values):
        landed = Path(storage_path)
        assert landed.is_file(), landed
        raise ArtifactOwnerScopeMissing(INTERNAL_REGISTRY_SENTENCE)

    monkeypatch.setattr(ArtifactRegistry, "register", refuse)
    config = _config(department="r715-有部门")

    answer = _ask(config)

    assert written and Path(written[0]).exists() is False, written
    assert registry.list_active() == [], registry.list_active()
    assert "本轮的图表文件没能登记进产物台账" in answer, answer
    assert "error_code=department_scope_required" in answer, answer
    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer
    assert {item["error_code"] for item in _refusal_rows(config)} == {"department_scope_required"}, _statuses(config)


# ==================== 5) 画图那一格炸了：异常原句同样不外泄 ====================


def test_a_generation_failure_speaks_in_a_code_instead_of_an_exception_repr(
    monkeypatch, tmp_path
) -> None:
    """改前形状是 return f"图表生成失败: {e}"：异常原句直接进客户可见正文、且不落日志。"""
    from app.tools import chart as chart_module

    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)

    def explode(*args, **kwargs) -> str:
        raise RuntimeError(INTERNAL_REGISTRY_SENTENCE)

    monkeypatch.setattr(chart_module, "bar_chart", explode)
    config = _config(department="r715-有部门")

    answer = _ask(config)

    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer
    assert "图表生成失败" in answer, answer
    assert "error_code=internal_error" in answer, answer
    assert written == [], written
    assert registry.list_active() == [], registry.list_active()
    assert {item["error_code"] for item in _refusal_rows(config)} == {"internal_error"}, _statuses(config)
    result = _canonical(config, answer)
    assert result.error is not None and result.error.code == "internal_error", result.error


# ==================== 6) 🔴 反过来那一牙：preflight 不许误伤有部门的账号 ====================


def test_an_owner_with_a_department_still_lands_exactly_one_chart_row(monkeypatch, tmp_path) -> None:
    """本单新加的闸只拦「登记不上」的那一支：有部门的账号照旧一枚不多、一码不记。"""
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)
    config = _config(id=DEPARTMENT, username="r715-owner", department=DEPARTMENT)

    answer = _ask(config)

    assert answer.startswith("图表已生成"), answer
    assert "error_code=" not in answer, answer
    assert len(written) == 1, written
    rows = registry.list_active()
    assert len(rows) == 1, rows
    assert rows[0].metadata["artifact_type"] == "chart", rows[0].metadata
    assert config["configurable"]["evidence_bag"]["artifacts"], "登记成功却没往证据袋记件"
    assert _refusal_rows(config) == [], _statuses(config)


# ==================== 7) span 上那枚码与这句话同源 ====================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("本轮没有生成图表文件……（error_code=department_scope_required）", "department_scope_required"),
        ("本轮的图表文件没能登记进产物台账……（error_code=department_scope_required）", "department_scope_required"),
        ("图表生成失败：这一轮没有写出图表文件（error_code=internal_error）", "internal_error"),
        ("未找到：当前请求缺少有效授权主体（error_code=authorization_required）", "internal_error"),
        ("不支持的图表类型: sparkline，可选: bar/line/pie/radar/gantt/mindmap", "validation_error"),
        ("", "validation_error"),
        (None, "validation_error"),
    ],
)
def test_the_span_reads_the_code_the_leg_actually_said(text, expected) -> None:
    """没有码的老句子只有「不支持的图表类型」那一枚 ⇒ 沿用 validation_error（改前整条腿都是它）。

    authorization_required 不是枚举成员 ⇒ 折回兜底码：本层不替公开词表扩容（同导出腿口径）。
    """
    assert tools._chart_terminal_error_code(text) == expected, text


# ==================== 8) 写域自证 ====================


def test_the_round_writes_nothing_outside_its_own_tmp_path(monkeypatch, tmp_path) -> None:
    """整轮只往 tmp_path 之下写，仓库里的 static/charts 一枚都不许多出来。"""
    shipped = Path(__file__).resolve().parents[1] / "static" / "charts"
    before = sorted(p.name for p in shipped.glob("chart_*")) if shipped.is_dir() else []

    _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_charts(monkeypatch, tmp_path, written)
    config = _config(id="r715-owner", username="r715-owner", department=DEPARTMENT)

    _ask(config)
    _ask(_config())

    after = sorted(p.name for p in shipped.glob("chart_*")) if shipped.is_dir() else []
    assert after == before, (before, after)
    assert written
    assert all(Path(name).is_relative_to(tmp_path) for name in written), written
