from pathlib import Path

import pytest
from PIL import Image

from app.tools import chart


@pytest.fixture
def rendered(monkeypatch, tmp_path):
    monkeypatch.setattr(chart, "STATIC_DIR", str(tmp_path))
    original_save = chart._save_and_return
    captured = {}

    def save(fig):
        fig.canvas.draw()
        captured["figure"] = fig
        captured["axes"] = fig.axes[0]
        captured["renderer"] = fig.canvas.get_renderer()
        path = original_save(fig)
        with Image.open(path) as image:
            assert image.width >= 800 and image.height >= 500
        captured["path"] = Path(path)
        return path

    monkeypatch.setattr(chart, "_save_and_return", save)
    return captured


@pytest.mark.parametrize("horizontal", [False, True])
def test_single_bar_keeps_category_space_in_rendered_axes(rendered, horizontal):
    chart.bar_chart(["试用-财务"], [200], title="部门费用", ylabel="金额（元）",
                    horizontal=horizontal)
    ax, renderer = rendered["axes"], rendered["renderer"]
    bar_box = ax.patches[0].get_window_extent(renderer)
    axis_box = ax.get_window_extent(renderer)
    fraction = (bar_box.height / axis_box.height if horizontal
                else bar_box.width / axis_box.width)
    assert fraction <= 0.35
    assert ax.get_ylabel() == "金额（元）"
    assert ax.texts[0].get_text() == "200"
    assert ax.patches[0].get_width() == 200 if horizontal else ax.patches[0].get_height() == 200


@pytest.mark.parametrize("horizontal", [False, True])
def test_negative_value_labels_stay_outside_bar_ends(rendered, horizontal):
    chart.bar_chart(["退款甲", "退款乙"], [-120, -20], horizontal=horizontal)
    ax, renderer = rendered["axes"], rendered["renderer"]
    for bar, text, value in zip(ax.patches, ax.texts, [-120, -20]):
        box = text.get_window_extent(renderer)
        endpoint = ax.transData.transform((value, 0) if horizontal else (0, value))
        assert box.x1 < endpoint[0] if horizontal else box.y1 < endpoint[1]
        assert text.get_text() == str(value)


@pytest.mark.parametrize("horizontal", [False, True])
def test_zero_value_axis_starts_at_zero(rendered, horizontal):
    chart.bar_chart(["零费用"], [0], horizontal=horizontal)
    ax = rendered["axes"]
    assert (ax.get_xlim() if horizontal else ax.get_ylim())[0] == 0
    assert ax.texts[0].get_text() == "0"


@pytest.mark.parametrize("horizontal", [False, True])
def test_negative_zero_is_displayed_as_zero(rendered, horizontal):
    chart.bar_chart(["未发生费用"], [-0.0], horizontal=horizontal)
    assert rendered["axes"].texts[0].get_text() == "0"


def test_many_long_chinese_labels_remain_visible_without_overlap(rendered):
    labels = [f"跨区域企业费用试用部门第{index:02d}组及其业务支持中心" for index in range(21)]
    chart.bar_chart(labels, list(range(21)), title="完整部门费用", ylabel="元")
    ax, renderer = rendered["axes"], rendered["renderer"]
    assert rendered['figure'].get_size_inches()[0] <= 12, 'A very wide figure becomes unreadable in a PDF'
    ticks = ax.get_yticklabels()
    assert len(ticks) == len(labels)
    assert all(tick.get_visible() for tick in ticks)
    assert [tick.get_text().replace("\n", "") for tick in ticks] == labels
    boxes = [tick.get_window_extent(renderer) for tick in ticks]
    boxes.sort(key=lambda box: box.y0)
    assert all(low.y1 <= high.y0 for low, high in zip(boxes, boxes[1:]))
    assert ax.get_xlabel() == '元'


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")]])
def test_empty_or_nonfinite_values_do_not_write_chart(rendered, values):
    with pytest.raises(ValueError):
        chart.bar_chart(["未知"] if values else [], values)
    assert "path" not in rendered

@pytest.mark.parametrize("labels,values", [
    ([], []), (["甲"], []), (["甲", "乙"], [1]),
    (["甲"], [float("nan")]), (["甲"], [float("inf")]), (["甲"], [float("-inf")]),
    (["甲"], [-1]), (["甲", "乙"], [0, 0]), (["甲", "乙"], [1e308, 1e308]),
    ([f"分类{i}" for i in range(11)], [0] * 10 + [-1]),
])
def test_pie_rejects_invalid_inputs_before_plotting_or_writing(rendered, monkeypatch, labels, values):
    def unexpected_plot(*args, **kwargs):
        raise AssertionError("must validate before plotting")
    monkeypatch.setattr(chart.plt, "subplots", unexpected_plot)
    monkeypatch.setattr(chart, "bar_chart", unexpected_plot)
    with pytest.raises(ValueError, match="饼图") as exc:
        chart.pie_chart(labels, values)
    if any(value < 0 and value != float("-inf") for value in values):
        assert "柱状图" in str(exc.value)
    assert "path" not in rendered


@pytest.mark.parametrize("values", [[1, 2], [0, 3], [2, 0, 4]])
def test_pie_accepts_positive_total_and_preserves_proportions(rendered, values):
    labels = [f"分类{i}" for i in range(len(values))]
    chart.pie_chart(labels, values)
    assert len(rendered["axes"].patches) == len(values)
    percentages = [text.get_text() for text in rendered["axes"].texts if text.get_text().endswith("%")]
    expected = [f"{value / sum(values) * 100:.1f}%" for value in values]
    assert percentages == expected
