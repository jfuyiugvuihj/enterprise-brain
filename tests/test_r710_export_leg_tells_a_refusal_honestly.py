r"""R710 判据 1＋3 的工具侧 —— 登记断掉那一格要说人话、要留码，并且别先在盘上落孤儿字节。

一手取证（凭据纸 docs/testing/r710-2026-10-06.md 甲组读数）：走查环 8 里导出腿自报
``status=failed 结果 51 字``，那 51 字逐字是「报告生成失败: 」+「artifact owner must have a
department scope」，发点在 ``app/agents/tools.py::_export_report`` 的兜底 ``except``——它把
``app/storage/artifacts.py::ArtifactRegistry.register`` 的内部英文原句直接拼进了客户可见正文，
既不给人一个公开码，又已经先往容器盘上落了一枚谁都登记不上的 PDF（``disk_newest_pdf``）。
同一条内部句子早在 run7/run9 评测里就吐进过客户答复（旧账见
docs/current-functionality-2026-09-10-revision-log.md 的 R-新4）。

本件钉的是改后的形状，四条都可失败：
  1) 属主没有部门 ⇒ 登记必拒：导出腿在**写盘之前**就该停下来，一条字节都不落；
  2) 人话旁边必须有公开码（``department_scope_required``，在册枚举成员，出处由
     ``tests/test_error_code_vocabulary.py::RATIFIED`` 钉着），终态 AgentResult 也带同一枚码；
  3) 登记表内部的英文原句一律不许出现在客户可见正文里；
  4) 拒收真发生在写盘之后（race）时，那枚没人登记得上的文件当场收回，台账与盘同时归零。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.agents import evidence, tools

USERNAME = "r710-nodept"
#: 走查环 8 现读的那一句内部原句：admin 没有部门时登记表就是这么说话的。
INTERNAL_REGISTRY_SENTENCE = "artifact owner must have a department scope"
INTERNAL_PATH_SENTENCE = "artifact storage path escapes registry root"
SECTIONS = [{"type": "text", "content": "上半年营收完成年度预算目标的 48.7%。"}]


def _registry(monkeypatch, tmp_path):
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    instance = ArtifactRegistry(
        root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json"
    )
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


def _fake_pdf(monkeypatch, tmp_path, written: list[str]):
    directory = tmp_path / "exports"
    directory.mkdir(parents=True, exist_ok=True)

    def generate(title: str, sections, chart_paths=None) -> str:
        path = directory / f"report_{uuid4().hex[:10]}.pdf"
        path.write_bytes(b"%PDF-1.4 r710 refusal")
        written.append(str(path))
        return str(path)

    from app.tools import export as export_module

    monkeypatch.setattr(export_module, "generate_pdf_report", generate)


def _config(**overrides) -> dict:
    configurable = {
        "id": USERNAME,
        "username": USERNAME,
        "role": "admin",
        "department": "",
        "thread_id": "sess-r710-" + uuid4().hex[:8],
        "request_id": "req-r710-" + uuid4().hex[:8],
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _ask(config) -> str:
    return tools.export_report.invoke(
        {
            "report_title": "2026 年上半年经营情况分析报告",
            "sections_json": json.dumps(SECTIONS, ensure_ascii=False),
        },
        config=config,
    )


def _statuses(config) -> list[dict]:
    return config["configurable"]["evidence_bag"]["tool_statuses"]


def _canonical(config, answer: str):
    return evidence.build_agent_result(
        worker="export", answer=answer, bag=config["configurable"]["evidence_bag"]
    )


# ==================== 1)＋2)＋3) 属主没有部门：写盘之前就叫停 ====================


def test_a_departmentless_owner_is_refused_before_a_single_byte_is_written(
    monkeypatch, tmp_path
) -> None:
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_pdf(monkeypatch, tmp_path, written)

    answer = _ask(_config())

    assert written == [], f"登记不上的文件根本不该落盘：{written}"
    assert list((tmp_path / "exports").glob("report_*.pdf")) == []
    assert registry.list_active() == [], registry.list_active()
    assert "本轮没有导出报告文件" in answer, answer
    assert "部门" in answer, answer
    assert "报告已生成" not in answer, answer


def test_the_refusal_carries_a_public_code_next_to_the_sentence(monkeypatch, tmp_path) -> None:
    """码是契约：人话旁边必须有 ``department_scope_required``，终态信封带同一枚。"""
    _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_pdf(monkeypatch, tmp_path, written)
    config = _config()

    answer = _ask(config)

    assert f"error_code=department_scope_required" in answer, answer
    #: 两条结构化出口本来就该同码：人话那一句走 ``_denial_text``，跨度那一枚走
    #: ``export_report`` 包装的 ``span.finish``。枚数不是判据，"每一条都带同一枚码"才是。
    statuses = [item for item in _statuses(config) if item["tool"] == "export_report"]
    assert statuses, _statuses(config)
    assert {item["error_code"] for item in statuses} == {"department_scope_required"}, statuses
    assert {item["status"] for item in statuses} == {"failed"}, statuses

    result = _canonical(config, answer)
    assert result.status == "failed", result
    assert result.error is not None and result.error.code == "department_scope_required", result.error


@pytest.mark.parametrize(
    "sections_json",
    [
        "not json at all",
        json.dumps(SECTIONS, ensure_ascii=False),
    ],
)
def test_the_internal_registry_sentence_never_reaches_the_customer(
    monkeypatch, tmp_path, sections_json
) -> None:
    """无论断在哪一格，客户可见正文里都不许出现登记表自己的英文句子。"""
    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_pdf(monkeypatch, tmp_path, written)
    config = _config()

    answer = tools._export_report(
        "2026 年上半年经营情况分析报告", sections_json, config
    )

    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer
    assert INTERNAL_PATH_SENTENCE not in answer, answer
    assert "error_code=" in answer, answer
    assert registry.list_active() == [], registry.list_active()


# ==================== 4) 拒收发生在写盘之后：那枚孤儿字节当场收回 ====================


def test_a_refusal_after_the_bytes_lands_removes_the_orphan_file(
    monkeypatch, tmp_path
) -> None:
    """preflight 之后登记表仍然可能拒收（同一时刻改的部门、另一枚根因）。

    这一格钉的是"话与账一致"：文件真落了盘，那就既要说清没登记上、也不能留下一枚没人查得回的
    原件——台账归零时盘上那枚 PDF 必须一起归零。
    """
    from app.storage.artifacts import ArtifactOwnerScopeMissing, ArtifactRegistry

    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_pdf(monkeypatch, tmp_path, written)

    def refuse(self, storage_path, **values):
        written_now = Path(storage_path)
        assert written_now.is_file(), written_now
        raise ArtifactOwnerScopeMissing(INTERNAL_REGISTRY_SENTENCE)

    monkeypatch.setattr(ArtifactRegistry, "register", refuse)
    config = _config(department="r710-有部门")

    answer = _ask(config)

    assert written and Path(written[0]).exists() is False, written
    assert registry.list_active() == [], registry.list_active()
    assert "本轮的报告文件没能登记进产物台账" in answer, answer
    assert "error_code=department_scope_required" in answer, answer
    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer


def test_a_registration_refusal_names_the_type_and_not_the_message(monkeypatch, tmp_path) -> None:
    """登记层的拒收是一枚有名有姓的异常，不靠字符串匹配（那是上一版的病根）。"""
    from app.storage.artifacts import ArtifactOwnerScopeMissing

    assert issubclass(ArtifactOwnerScopeMissing, ValueError), "老 except ValueError 的调用方不能被改坏"


# ==================== 5) 生成那一格炸了：内部异常原句同样不外泄 ====================


def test_a_generation_failure_speaks_in_a_code_instead_of_an_exception_repr(
    monkeypatch, tmp_path
) -> None:
    from app.tools import export as export_module

    registry = _registry(monkeypatch, tmp_path)
    written: list[str] = []
    _fake_pdf(monkeypatch, tmp_path, written)

    def explode(title: str, sections, chart_paths=None) -> str:
        raise RuntimeError(INTERNAL_REGISTRY_SENTENCE)

    monkeypatch.setattr(export_module, "generate_pdf_report", explode)
    config = _config(department="r710-有部门")

    answer = _ask(config)

    assert INTERNAL_REGISTRY_SENTENCE not in answer, answer
    assert "报告生成失败" in answer, answer
    assert "error_code=internal_error" in answer, answer
    assert registry.list_active() == [], registry.list_active()
    statuses = [item for item in _statuses(config) if item["tool"] == "export_report"]
    assert statuses, _statuses(config)
    assert {item["error_code"] for item in statuses} == {"internal_error"}, statuses


# ==================== 6) span 上那枚码与这句话同源 ====================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("本轮没有导出报告文件……（error_code=department_scope_required）", "department_scope_required"),
        ("本轮的报告文件没能登记进产物台账……（error_code=department_scope_required）", "department_scope_required"),
        ("报告生成失败：这一轮没能写出报告文件（error_code=internal_error）", "internal_error"),
        ("未找到：当前请求缺少有效授权主体（error_code=authorization_required）", "internal_error"),
        ("一句话都没有码", "internal_error"),
        ("", "internal_error"),
        (None, "internal_error"),
    ],
)
def test_the_span_reads_the_code_the_leg_actually_said(text, expected) -> None:
    """``authorization_required`` 不是枚举成员 ⇒ 折回兜底码：本层不替公开词表扩容。"""
    assert tools._export_terminal_error_code(text) == expected, text