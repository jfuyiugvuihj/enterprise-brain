def _registry(monkeypatch, tmp_path):
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(
        root=tmp_path,
        metadata_path=tmp_path / "artifact-metadata.json",
    )
    monkeypatch.setattr(artifacts, "artifact_registry", registry)


def _config() -> dict:
    return {
        "configurable": {
            "id": "finance-manager",
            "username": "finance-manager",
            "role": "manager",
            "department": "finance",
        }
    }


def test_chart_tool_requires_an_explicit_principal_before_generating(monkeypatch):
    from app.agents.tools import generate_chart
    from app.tools import chart

    generated = {"called": False}

    def fake_chart(*args, **kwargs):
        generated["called"] = True
        raise AssertionError("chart generation must not run without a principal")

    monkeypatch.setattr(chart, "bar_chart", fake_chart)

    result = generate_chart.invoke(
        {
            "chart_type": "bar",
            "labels": ["A"],
            "values": [1],
            "title": "Revenue",
        }
    )

    assert "authorization_required" in result
    assert not generated["called"]


def test_chart_tool_returns_a_controlled_artifact_url(monkeypatch, tmp_path):
    from app.agents.tools import generate_chart
    from app.tools import chart

    _registry(monkeypatch, tmp_path)
    generated = tmp_path / "chart.png"
    generated.write_bytes(b"chart")
    monkeypatch.setattr(chart, "bar_chart", lambda *args, **kwargs: str(generated))

    result = generate_chart.invoke(
        {
            "chart_type": "bar",
            "labels": ["A"],
            "values": [1],
            "title": "Revenue",
        },
        config=_config(),
    )

    assert "/api/v1/artifacts/" in result
    assert "/content" in result
    assert "/static/" not in result


def test_export_tool_requires_export_permission_before_generating(monkeypatch):
    from app.agents.tools import export_report
    from app.tools import export

    generated = {"called": False}

    def fake_export(*args, **kwargs):
        generated["called"] = True
        raise AssertionError("report generation must not run without export permission")

    monkeypatch.setattr(export, "generate_pdf_report", fake_export)
    config = {
        "configurable": {
            "id": "finance-staff",
            "username": "finance-staff",
            "role": "staff",
            "department": "finance",
        }
    }

    result = export_report.invoke(
        {
            "report_title": "Revenue report",
            "sections_json": '[{"type":"text","content":"Summary"}]',
        },
        config=config,
    )

    assert "authorization_required" in result
    assert not generated["called"]


def test_export_tool_returns_a_controlled_artifact_url(monkeypatch, tmp_path):
    from app.agents.tools import export_report
    from app.tools import export

    _registry(monkeypatch, tmp_path)
    generated = tmp_path / "report.pdf"
    generated.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(export, "generate_pdf_report", lambda *args, **kwargs: str(generated))

    result = export_report.invoke(
        {
            "report_title": "Revenue report",
            "sections_json": '[{"type":"text","content":"Summary"}]',
        },
        config=_config(),
    )

    assert "/api/v1/artifacts/" in result
    assert "/download" in result
    assert "/static/" not in result
