from app.agents.tools import generate_chart


def _config() -> dict:
    return {
        "configurable": {
            "id": "finance-manager",
            "username": "finance-manager",
            "role": "manager",
            "department": "finance",
        }
    }


def _registry(monkeypatch, tmp_path):
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    monkeypatch.setattr(
        artifacts,
        "artifact_registry",
        ArtifactRegistry(
            root=tmp_path,
            metadata_path=tmp_path / "artifact-metadata.json",
        ),
    )


def test_generate_gantt_chart_returns_controlled_artifact(monkeypatch, tmp_path):
    from app.tools import visualize

    _registry(monkeypatch, tmp_path)
    generated = tmp_path / "gantt.html"
    generated.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(visualize, "gantt_chart", lambda *args, **kwargs: str(generated))

    result = generate_chart.invoke(
        {
            "chart_type": "gantt",
            "tasks": [
                {"name": "需求", "start": "2026-09-01", "end": "2026-09-03", "label": "A"},
                {"name": "开发", "start": "2026-09-04", "end": "2026-09-06", "label": "B"},
            ],
            "title": "甘特图测试",
        },
        config=_config(),
    )

    assert "图表已生成" in result
    assert "/api/v1/artifacts/" in result
    assert "/content" in result
    assert "/static/" not in result


def test_generate_mindmap_chart_returns_controlled_artifact(monkeypatch, tmp_path):
    from app.tools import visualize

    _registry(monkeypatch, tmp_path)
    generated = tmp_path / "mindmap.png"
    generated.write_bytes(b"mindmap")
    monkeypatch.setattr(visualize, "mindmap", lambda *args, **kwargs: str(generated))

    result = generate_chart.invoke(
        {
            "chart_type": "mindmap",
            "root": "中心主题",
            "branches": {"方向一": ["子项1", "子项2"]},
            "title": "思维导图测试",
        },
        config=_config(),
    )

    assert "图表已生成" in result
    assert "/api/v1/artifacts/" in result
    assert "/content" in result
    assert "/static/" not in result
