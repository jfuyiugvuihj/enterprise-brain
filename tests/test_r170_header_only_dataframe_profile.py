"""R170 · 「有列无行」是一张合法的空表画像，不是错误。

复现路径（R169 验收时扫出、总控在主树静态复核确认）：
    app/tools/excel.py::profile_dataframe 里 `if df.empty: return {"error": "数据为空"}`
    -> 只有表头没有数据行的 CSV/Excel，pandas 交回「有列、0 行」，df.empty 恰好为真
    -> app/api/v1/data.py::build_dataframe_preview 把这个错误 dict 原样塞进 profile
    -> frontend/src/components/DataPanel.vue 的 `v-if="profile"` 判真，统计行读
      `profile.column_count || profile.columns.length` -> `undefined.length` 在渲染期抛错
    => 客户上传一张空表，数据面板当场崩。

本文件钉的是后端这一侧的契约，三件事各自一枚：
  1) 空表画像必须形状完整（rows / column_count / columns / 逐列字段一个都不许缺，也不许留 None 冒充算过）；
  2) 真什么都没有（零列）才走错误形状，且错误走既有信封 ErrorEnvelope + 既有稳定码，不新造字段与裸码；
  3) 修完不许把「有数据」那一批的既有形状改坏（numeric/text 汇总按 dtype 派生，与按键存在性派生等价）。

最后两枚是跨层的：前端那处渲染防御一旦被删、或后端被手工改回 `{"error": ...}` 那一支，这里也要响。
"""

from pathlib import Path
from typing import get_args

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _header_only_frame():
    """一张只交了表头的表：一列，零行。pandas 里 df.empty 为真。"""
    return pd.DataFrame({"月份": pd.Series(dtype="object")})


def _mixed_header_only_frame():
    return pd.DataFrame({"金额": pd.Series(dtype="float64"), "部门": pd.Series(dtype="object")})


# ==================== 1) 空表是一张开张空表，不是一条错误 ====================


def test_a_header_only_dataframe_builds_a_shape_complete_profile():
    """只有表头 => 画像必须形状完整，而不是 `{"error": ...}`。

    这一枚就是 R169 扫出来的崩溃源头：改之前它走的就是 `{"error": "数据为空"}` 那一支。
    """
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(_header_only_frame())

    assert "error" not in profile, f"空表被说成了错误：{profile}"
    assert profile["rows"] == 0
    assert profile["column_count"] == 1
    assert isinstance(profile["columns"], list) and len(profile["columns"]) == 1


def test_every_column_of_an_empty_table_reports_missing_and_unique_without_blanks():
    """空列的口径定死：没有单元格 => 一个缺失值都没有（0 / 0.0），没有任何取值 => 唯一值 0 个。

    不许留 None 或干脆不给键：前端 `col.missing_pct > 0` 与 `col.unique_values !== undefined`
    读的就是这两格，留白等于把「算不出来」说成「算出来是空」。
    """
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(_header_only_frame())
    column = profile["columns"][0]

    assert column["name"] == "月份"
    assert column["dtype"] == "object"
    assert column["missing"] == 0
    assert column["missing_pct"] == 0.0
    assert column["unique_values"] == 0
    assert profile["total_missing"] == 0


def test_the_empty_table_is_marked_so_zero_rows_does_not_read_like_a_failed_statistic():
    """一枚诚实的空表标记：让读的人分得清「0 行」与「没统计出来」。"""
    from app.tools.excel import profile_dataframe

    empty_profile = profile_dataframe(_header_only_frame())
    populated_profile = profile_dataframe(pd.DataFrame({"月份": ["1月", "2月"]}))

    assert empty_profile["empty"] is True
    assert populated_profile["empty"] is False


def test_numeric_columns_of_an_empty_table_keep_their_dtype_but_invent_no_aggregates():
    """数值列在空表里仍然是数值列：它进 numeric_columns，但不发 min/max/mean/sum。

    0 行的均值不是一个数，写 0 会把「没有数据」说成「数据是 0」，写 None 会让界面渲染出
    「最小 null」。不发这两组键才是实话，前端本来就是按「键在不在」决定统不统计行的。
    """
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(_mixed_header_only_frame())
    by_name = {column["name"]: column for column in profile["columns"]}

    assert profile["rows"] == 0
    assert profile["column_count"] == 2
    assert profile["numeric_columns"] == ["金额"]
    assert profile["text_columns"] == ["部门"]
    assert by_name["金额"]["dtype"] == "float64"
    assert by_name["金额"]["unique_values"] == 0
    for key in ("min", "max", "mean", "sum"):
        assert key not in by_name["金额"], f"空表编造了统计量 {key}={by_name['金额'][key]}"
    for key in ("min", "max", "mean", "sum"):
        assert key not in by_name["部门"]


def test_preview_endpoint_carries_the_empty_profile_through_unchanged():
    """API 层不再有机会把错误 dict 塞进 profile：走的是同一条画像契约。"""
    from app.api.v1.data import build_dataframe_preview

    preview = build_dataframe_preview(_header_only_frame(), "空表.csv")

    assert preview["columns"] == ["月份"]
    assert preview["rows"] == []
    assert preview["truncated"] is False
    assert preview["profile"]["rows"] == 0
    assert preview["profile"]["column_count"] == 1
    assert "error" not in preview["profile"]


def test_a_header_only_csv_from_disk_profiles_as_an_empty_table(tmp_path):
    """端到端：客户那张「只有表头」的 CSV 真从磁盘走一遍 load_excel。"""
    from app.tools.excel import load_excel, profile_dataframe

    source = tmp_path / "全年预算.csv"
    source.write_text("部门,预算\n", encoding="utf-8")

    frame = load_excel(str(source))
    assert frame.empty is True  # df.empty 为真，正是当年走进错误分支的那一刻

    profile = profile_dataframe(frame)
    assert "error" not in profile
    assert profile["rows"] == 0
    assert profile["column_count"] == 2
    assert [column["name"] for column in profile["columns"]] == ["部门", "预算"]


# ==================== 2) 真什么都没有，才走错误形状 ====================


def test_a_frame_with_no_columns_at_all_is_the_error_shape():
    """零列 = 什么都没解析出来，这才是错误；错误走既有信封，不是一句裸中文。"""
    from app.agents.contracts import ErrorEnvelope
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(pd.DataFrame())

    assert set(profile) == {"error"}, "错误形状除信封以外不许长得像画像"
    assert isinstance(profile["error"], dict)
    envelope = ErrorEnvelope(**profile["error"])  # 过不了既有模型的校验就是自造形状
    assert envelope.code in get_args(ErrorEnvelope.model_fields["code"].annotation)
    assert envelope.retryable is False
    assert envelope.message.strip()


def test_the_error_shape_names_a_registered_code_instead_of_bare_text():
    """改之前这里是 `{"error": "数据为空"}`：人读得懂，机器读不懂，前端只能判真再炸。"""
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(pd.DataFrame())

    assert profile["error"]["code"] == "parse_failed"
    assert profile["error"]["message"] != "数据为空"


# ==================== 3) 有数据那一批的形状不许被顺手改坏 ====================


def test_a_populated_frame_profile_is_unchanged_in_shape_and_values():
    # 显式给 dtype：pandas 3 会把字符串列判成 `str` 而非 `object`，那是画像函数早就存在的一格
    # 口径（本次改动前也不发 unique_values），不在本单范围内顺手改，见交工报告。
    from app.tools.excel import profile_dataframe

    frame = pd.DataFrame(
        {
            "部门": pd.Series(["研发", "销售", "研发"], dtype="object"),
            "人数": pd.Series([3, 5, None], dtype="float64"),
        }
    )

    profile = profile_dataframe(frame)

    assert profile["empty"] is False
    assert profile["rows"] == 3
    assert profile["column_count"] == 2
    assert profile["numeric_columns"] == ["人数"]
    assert profile["text_columns"] == ["部门"]
    # 有数据的帧上，按 dtype 派生的汇总名单必须与「按键在不在」派生完全等价 —— 这就是「没改坏旧形状」。
    assert profile["numeric_columns"] == [c["name"] for c in profile["columns"] if "mean" in c]
    assert profile["text_columns"] == [c["name"] for c in profile["columns"] if "unique_values" in c]
    by_name = {column["name"]: column for column in profile["columns"]}
    assert by_name["人数"]["missing"] == 1
    assert by_name["人数"]["missing_pct"] == pytest.approx(33.3)
    assert by_name["人数"]["min"] == 3.0
    assert by_name["人数"]["max"] == 5.0
    assert by_name["人数"]["mean"] == 4.0
    assert by_name["人数"]["sum"] == 8.0
    assert "unique_values" not in by_name["人数"]
    assert by_name["部门"]["unique_values"] == 2
    assert profile["total_missing"] == 1


def test_an_all_nan_numeric_column_still_reports_its_aggregate_slots():
    """有行但整列皆空：这跟「一行都没有」不是一回事，统计槽照发（值为 None）。"""
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(pd.DataFrame({"人数": pd.Series([None, None], dtype="float64")}))

    assert profile["empty"] is False
    assert profile["rows"] == 2
    column = profile["columns"][0]
    assert column["missing"] == 2
    assert column["missing_pct"] == 100.0
    assert "min" in column
    assert column["min"] is None


# ==================== 跨层：两把反证的常驻钉 ====================


def test_datapanel_guard_keeps_a_non_profile_payload_out_of_the_profile_card():
    """画像卡的守卫（`v-if` + 列数表达式）是崩溃的第二道闸：删掉它就等于让客户继续点崩。"""
    source = (ROOT / "frontend" / "src" / "components" / "DataPanel.vue").read_text(encoding="utf-8")

    assert 'v-if="profile && !profile.error"' in source, "画像卡守卫没了：错误形状会被当成画像渲染"
    assert "profile.columns.length" not in source, "未防空的 profile.columns.length 回来了：undefined.length 会抛"
    assert "profile.column_count || profile.columns?.length" in source


def test_the_backend_no_longer_returns_the_bare_error_branch_for_zero_rows():
    """把 excel.py 手工改回 `{"error": "数据为空"}` 那一支，这枚与前端同名钉一起红。"""
    source = (ROOT / "app" / "tools" / "excel.py").read_text(encoding="utf-8")

    assert '"数据为空"' not in source
    assert '"empty": ' in source
