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


#: 10-07 12:21 现读（走查环 7，账本 rings[ring=7]）：图腿第一发交回 chart_type="柱状图"
#: 被六个英文键挡掉（validation_error），反思重试那一发写对了 "bar" 却把数值留在
#: datasets 里没进 values（internal_error）。两屏客户看到的都是「没有图」而没有一句原因。
#: 这三枚牙各咬一个屏幕上的坏，不咬实现细节。
def test_chinese_chart_type_draws_the_bar(monkeypatch, tmp_path):
    from app.tools import chart

    _registry(monkeypatch, tmp_path)
    drawn = tmp_path / "bar.png"
    drawn.write_bytes(b"bar")
    seen: dict = {}

    def fake_bar(labels, values, title="x"):
        seen["labels"] = labels
        seen["values"] = values
        return str(drawn)

    monkeypatch.setattr(chart, "bar_chart", fake_bar)
    result = generate_chart.invoke(
        {"chart_type": "柱状图", "labels": ["1月", "2月"], "values": [10, 20], "title": "月度报销"},
        config=_config(),
    )

    assert "图表已生成" in result
    assert seen["values"] == [10, 20]


def test_bar_falls_back_to_the_series_handed_in_datasets(monkeypatch, tmp_path):
    from app.tools import chart

    _registry(monkeypatch, tmp_path)
    drawn = tmp_path / "bar2.png"
    drawn.write_bytes(b"bar2")
    seen: dict = {}

    def fake_bar(labels, values, title="x"):
        seen["values"] = values
        return str(drawn)

    monkeypatch.setattr(chart, "bar_chart", fake_bar)
    result = generate_chart.invoke(
        {
            "chart_type": "bar",
            "labels": ["1月", "2月"],
            "datasets": {"报销金额": ["12,300元", 8700]},
            "title": "月度报销",
        },
        config=_config(),
    )

    assert "图表已生成" in result
    assert seen["values"] == [12300.0, 8700.0]


def test_bar_without_any_numbers_says_the_numbers_are_missing(monkeypatch, tmp_path):
    from app.tools import chart

    _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(chart, "bar_chart", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该被调用")))

    result = generate_chart.invoke(
        {"chart_type": "bar", "labels": ["1月", "2月"], "title": "月度报销"},
        config=_config(),
    )

    assert "error_code=validation_error" in result
    assert "数字" in result
    assert not [p for p in tmp_path.iterdir() if p.suffix in (".png", ".jpg", ".html")]
