r"""R710 判据 2 —— 导出腿真在册：一次导出＝台账里一枚可查回的件，一枚不多一枚不少。

病形（走查环 8 一手读数，docs/testing/walkthrough-2026-10-06/ledger.json 的 rings[ring=8]）：
``report_artifact.total=0``、``artifact_rows_after=[]``、``/api/v1/artifacts`` 零枚在册，
而盘上躺着一枚 ``report_a8e1bc3666.pdf``（57 322 字节，可读）。登记那一腿断了，答复却继续
往前报"文件已导出"。本件钉的是正面对盘：离线跑一次真导出（假 PDF 字节、零容器、写盘只写
tmp_path），本轮交回的件数与 ``GET /api/v1/artifacts`` 的账目**同一枚数**，且件型／文件名／
交付 URL／属主与部门／生成本轮的血缘逐枚可指认。

每一格都是可失败读数（数字与字段名对盘），不是"字符串里好像有"。
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents import evidence, tools

LIST_PATH = "/api/v1/artifacts"
USERNAME = "r710-owner"
DEPARTMENT = "r710-报销测试部"
REPORT_BYTES = b"%PDF-1.4 r710 offline report"
SECTIONS = [
    {"type": "heading", "content": "2026 年上半年经营情况分析报告"},
    {"type": "text", "content": "上半年营收完成年度预算目标的 48.7%。"},
]


def _registry(monkeypatch, tmp_path):
    """真 registry 类，根落在 tmp_path：本件一个字都不碰仓库里的 static/。"""
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    instance = ArtifactRegistry(
        root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json"
    )
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


@pytest.fixture()
def account(monkeypatch):
    """一张内存里的用户表，替掉 ``app.common.auth.get_user``。"""
    from app.common import auth

    users: dict[str, dict] = {}

    def add(username: str = USERNAME, department: str = DEPARTMENT, role: str = "admin") -> str:
        users[username] = {
            "id": username,
            "username": username,
            "role": role,
            "department": department,
        }
        monkeypatch.setattr(auth, "get_user", lambda name: users.get(name))
        return username

    return add


@pytest.fixture()
def fake_pdf(monkeypatch, tmp_path):
    """假导出：字节写进 registry 根目录之下（生产里 EXPORT_DIR 就躺在 static/ 之下）。"""
    written: list[str] = []
    directory = tmp_path / "exports"
    directory.mkdir(parents=True, exist_ok=True)

    def generate(title: str, sections, chart_paths=None) -> str:
        path = directory / f"report_{uuid4().hex[:10]}.pdf"
        path.write_bytes(REPORT_BYTES)
        written.append(str(path))
        return str(path)

    from app.tools import export as export_module

    monkeypatch.setattr(export_module, "generate_pdf_report", generate)
    return written


def _config(**overrides) -> dict:
    configurable = {
        "id": USERNAME,
        "username": USERNAME,
        "role": "admin",
        "department": DEPARTMENT,
        "thread_id": "sess-r710-" + uuid4().hex[:8],
        "request_id": "req-r710-" + uuid4().hex[:8],
        "trace_id": "trace-r710-" + uuid4().hex[:8],
        "evidence_bag": evidence.new_evidence_bag(),
    }
    configurable.update(overrides)
    return {"configurable": configurable}


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def _ask(client, config) -> str:
    """走一次真导出：工具入口是 @tool 包装过的那一枚，不是手搓的内部函数。"""
    return tools.export_report.invoke(
        {
            "report_title": "2026 年上半年经营情况分析报告",
            "sections_json": json.dumps(SECTIONS, ensure_ascii=False),
        },
        config=config,
    )


# ==================== 判据 2：一次导出＝一枚在册件 ====================


def test_one_export_lands_exactly_one_report_row_in_the_ledger(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    registry = _registry(monkeypatch, tmp_path)
    account()
    config = _config()

    answer = _ask(client, config)

    bag_rows = config["configurable"]["evidence_bag"]["artifacts"]
    listed = client.get(LIST_PATH, headers=_headers(USERNAME)).json()

    assert "报告已生成" in answer, answer
    assert len(fake_pdf) == 1, fake_pdf
    assert len(bag_rows) == 1, bag_rows
    assert listed["total"] == 1, listed
    assert len(listed["artifacts"]) == 1, listed
    assert len(registry.list_active()) == 1, registry.list_active()
    assert [row["artifact_id"] for row in listed["artifacts"]] == [bag_rows[0]["artifact_id"]]


def test_the_listed_row_names_the_type_the_filename_and_the_turn(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """件型／文件名／交付 URL／属主与部门／本轮血缘都是可指认的字段，不是"好像有"。"""
    _registry(monkeypatch, tmp_path)
    account()
    config = _config()

    answer = _ask(client, config)

    row = client.get(LIST_PATH, headers=_headers(USERNAME)).json()["artifacts"][0]
    assert row["artifact_type"] == "report", row
    assert row["filename"] == Path(fake_pdf[0]).name, row
    assert row["owner_id"] == USERNAME, row
    assert row["department_ids"] == [DEPARTMENT], row
    #: 导出腿交回客户的是下载口（``app/agents/tools.py::_export_report`` 取的是那一条），
    #: 内容口留在台账行里供机器查回 —— 两枚都要指认得出，但不许要求正文同时躺着两句。
    assert row["download_url"] in answer, (row, answer)
    assert row["content_url"] == f"/api/v1/artifacts/{row['artifact_id']}/content", row
    assert row["session_id"] == config["configurable"]["thread_id"], row
    assert row["request_id"] == config["configurable"]["request_id"], row
    assert row["expires_at"] is None, row


def test_the_reported_urls_serve_the_very_bytes_that_were_written(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """台账说在册，两条交付口就得真打得开，且打开的就是那一枚字节。"""
    _registry(monkeypatch, tmp_path)
    account()
    _ask(client, _config())

    row = client.get(LIST_PATH, headers=_headers(USERNAME)).json()["artifacts"][0]
    content = client.get(row["content_url"], headers=_headers(USERNAME))
    download = client.get(row["download_url"], headers=_headers(USERNAME))

    assert content.status_code == 200, content.text
    assert content.content == REPORT_BYTES, content.content[:64]
    assert download.status_code == 200, download.text
    assert download.content == REPORT_BYTES, download.content[:64]


def test_two_exports_land_two_rows_and_no_more(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """枚数随导出次数线性长：一次导出不留两枚，也不许吞掉一枚。"""
    _registry(monkeypatch, tmp_path)
    account()

    _ask(client, _config())
    _ask(client, _config())

    listed = client.get(LIST_PATH, headers=_headers(USERNAME)).json()
    assert len(fake_pdf) == 2, fake_pdf
    assert listed["total"] == 2, listed
    assert len({row["artifact_id"] for row in listed["artifacts"]}) == 2, listed


def test_the_type_filter_answers_for_the_report_and_for_nothing_else(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """同一张台账里图与报告各归各的件型：按 report 查不到图，按 chart 查不到报告。"""
    from app.agents.contracts import Principal

    registry = _registry(monkeypatch, tmp_path)
    account()
    _ask(client, _config())

    chart_path = registry.root / "chart.png"
    chart_path.write_bytes(b"png-bytes")
    registry.register(
        chart_path,
        artifact_type="chart",
        principal=Principal.from_user(
            {"id": USERNAME, "username": USERNAME, "role": "admin", "department": DEPARTMENT}
        ),
    )

    reports = client.get(
        LIST_PATH, params={"artifact_type": "report"}, headers=_headers(USERNAME)
    ).json()
    charts = client.get(
        LIST_PATH, params={"artifact_type": "chart"}, headers=_headers(USERNAME)
    ).json()

    assert reports["total"] == 1, reports
    assert [row["artifact_type"] for row in reports["artifacts"]] == ["report"], reports
    assert [row["artifact_type"] for row in charts["artifacts"]] == ["chart"], charts


def test_an_anonymous_caller_is_refused_what_the_ledger_still_holds(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """登记在册不等于人人可查回：件是 private 的，匿名一律 401，本单不放宽任何一维。"""
    _registry(monkeypatch, tmp_path)
    account()
    _ask(client, _config())

    anonymous = client.get(LIST_PATH)

    assert anonymous.status_code == 401, anonymous.text
    assert anonymous.json()["detail"] == "authentication_required", anonymous.text
    assert client.get(LIST_PATH, headers=_headers(USERNAME)).json()["total"] == 1


def test_the_round_writes_nothing_outside_its_own_tmp_path(
    monkeypatch, tmp_path, account, fake_pdf, client
) -> None:
    """写域自证：整轮只往 tmp_path 之下写，仓库里的 static/exports 一枚都不许多出来。"""
    shipped = Path(__file__).resolve().parents[1] / "static" / "exports"
    before = sorted(p.name for p in shipped.glob("report_*.pdf")) if shipped.is_dir() else []

    _registry(monkeypatch, tmp_path)
    account()
    _ask(client, _config())

    after = sorted(p.name for p in shipped.glob("report_*.pdf")) if shipped.is_dir() else []
    assert after == before, (before, after)
    assert fake_pdf, fake_pdf
    assert all(Path(name).is_relative_to(tmp_path) for name in fake_pdf), fake_pdf