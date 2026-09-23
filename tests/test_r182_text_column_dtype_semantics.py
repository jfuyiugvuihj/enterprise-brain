"""R182 · 文本列判语义，不判 dtype 的字符串写法。

复现（总控 2026-09-23 主树亲跑，本树同读数）：
    pandas 3.0.3 把字符串列判成 `str`，而 app/tools/excel.py::profile_dataframe 那一支
    比的是字面 dtype 串 -> 真机数据上基本进不去 -> text_columns 常年为空、每列
    「多少个不同取值」永远不发 -> 数据面板对客户的真实文档说「这里没有文本列」。
    这不是性能问题，是界面在装瞎：员工看得见的假干净。

本文件钉四件事：
  1) 真字符串帧上，文本列名单与 unique_values 一起回来（判据①）；
  2) 两份汇总名单互斥、且与逐列统计键严格等价 —— 双计＝对同一列说两次谎，漏计＝假干净（判据③）；
  3) 从 `object` 到 `str` / `string` / 混装 / 类别的整族字符串形态都收进文本列，修判定不许收窄旧口径；
  4) R170 刚钉死的空表口径一处不许动（判据②）：0 行仍交完整画像 + empty 标记，
     空列 missing 0 / missing_pct 0.0 / unique_values 0，数值列在 0 行不发 min/max/mean/sum，
     只有零列才走 ErrorEnvelope(code="parse_failed")。

末尾两把反证常驻：把判定退回字面 dtype 串 ⇒ 红；只改判定不发 unique_values ⇒ 红。
"""

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _real_world_frame() -> pd.DataFrame:
    """一张真机形状的表：只交文件名，不手写 dtype —— pandas 3 会把「月份」判成 `str`。"""
    return pd.DataFrame({"月份": ["1月", "2月", "3月"], "额": [10, 20, 30]})


def _column(profile, name):
    return {column["name"]: column for column in profile["columns"]}[name]


# ==================== 1) 真字符串帧：判定与取值数一起回来 ====================


def test_a_real_string_column_is_named_as_text_and_reports_its_distinct_values():
    """判据①的那段驱动：改前 text_columns=[] 且列上没有 unique_values。"""
    from app.tools.excel import profile_dataframe

    frame = _real_world_frame()
    # 先钉住环境事实：这一列在 pandas 3 里就是 `str`，不是 `object` —— 旧判定正是死在这格上。
    assert str(frame["月份"].dtype) != "object"
    assert pd.api.types.is_string_dtype(frame["月份"])

    profile = profile_dataframe(frame)

    assert profile["text_columns"] == ["月份"]
    assert profile["numeric_columns"] == ["额"]
    column = profile["columns"][0]
    assert set(column) >= {"dtype", "missing", "missing_pct", "name", "unique_values"}
    assert column["unique_values"] == 3


@pytest.mark.parametrize(
    "series",
    [
        pd.Series(["甲", "乙", "甲"], dtype="str"),
        pd.Series(["甲", "乙", "甲"], dtype="string"),
        pd.Series(["甲", "乙", "甲"], dtype="object"),
        pd.Series(["甲", 1, None], dtype="object"),
        pd.Series(["甲", "乙", "甲"], dtype="category"),
        pd.Series([None, None], dtype="object"),
    ],
    ids=["str", "string", "object", "mixed-object", "category", "all-none-object"],
)
def test_every_string_flavoured_column_is_text_and_carries_its_own_count(series):
    """收编整族字符串形态：判据不许挑 dtype 的写法，也不许把旧口径认得的列不收。"""
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(pd.DataFrame({"列": series}))

    assert profile["text_columns"] == ["列"]
    assert profile["numeric_columns"] == []
    assert _column(profile, "列")["unique_values"] == int(series.nunique())


# ==================== 2) 两份名单的账要连上：不双计、不漏计 ====================


def test_the_two_summary_lists_stay_disjoint_and_match_the_per_column_keys():
    """同一列进两份名单＝说两次谎；两份都不进＝假干净。这里把两种都钉住。"""
    from app.tools.excel import profile_dataframe

    frame = pd.DataFrame(
        {
            "部门": ["研发", "销售", "研发", "行政"],
            "备注": pd.Series(["通过", "驳回", None, "通过"], dtype="object"),
            "人数": [3, 5, 8, 1],
            "单价": pd.Series([1.5, 2.5, None, 4.0], dtype="float64"),
            "达标": [True, False, True, True],
            "开机日": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]),
        }
    )

    profile = profile_dataframe(frame)
    numeric = profile["numeric_columns"]
    text = profile["text_columns"]
    names = [column["name"] for column in profile["columns"]]

    assert set(numeric) & set(text) == set(), f"同一列被两份名单各说一次：{set(numeric) & set(text)}"
    # 名单与逐列统计键严格等价：这是 R170 定的等价式，换成语义谓词后必须照样成立。
    assert numeric == [column["name"] for column in profile["columns"] if "mean" in column]
    assert text == [column["name"] for column in profile["columns"] if "unique_values" in column]
    assert numeric == ["人数", "单价", "达标"]
    assert text == ["部门", "备注"]
    # 唯一不进任何一份名单的是日期列：它既不是文本也不是数值，改前改后同口径，不是漏计。
    assert [name for name in names if name not in numeric and name not in text] == ["开机日"]


def test_numeric_and_bool_columns_never_slip_into_the_text_list():
    """bool 在 pandas 里算数值：它必须留在 numeric 那份名单里，一份都不许多说。"""
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(
        pd.DataFrame({"计数": [1, 2], "均值": [1.5, 2.5], "开关": [True, False]})
    )

    assert profile["numeric_columns"] == ["计数", "均值", "开关"]
    assert profile["text_columns"] == []
    for name in profile["numeric_columns"]:
        assert "unique_values" not in _column(profile, name)


# ==================== 3) R170 的空表口径：一处不许动 ====================


def test_a_header_only_string_frame_still_gets_the_complete_empty_profile():
    """R170 的钉用的是显式 dtype=object；这一枚补的是 pandas 3 默认那格：0 行的 str 列。"""
    from app.tools.excel import profile_dataframe

    frame = pd.DataFrame({"月份": pd.Series(dtype="str"), "额": pd.Series(dtype="float64")})
    assert frame.empty
    assert str(frame["月份"].dtype) != "object"

    profile = profile_dataframe(frame)

    assert "error" not in profile
    assert profile["empty"] is True
    assert profile["rows"] == 0
    assert profile["text_columns"] == ["月份"]
    assert profile["numeric_columns"] == ["额"]
    assert _column(profile, "月份")["missing"] == 0
    assert _column(profile, "月份")["missing_pct"] == 0.0
    assert _column(profile, "月份")["unique_values"] == 0
    assert _column(profile, "额")["unique_values"] == 0
    for key in ("min", "max", "mean", "sum"):
        assert key not in _column(profile, "额"), f"空表编造了统计量 {key}"


def test_only_a_frame_with_no_columns_at_all_still_takes_the_error_envelope():
    """零列才是「什么都没解析出来」：语义谓词放宽了文本判定，也不许把这格顺手改掉。"""
    from app.agents.contracts import ErrorEnvelope
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(pd.DataFrame())

    assert set(profile) == {"error"}
    envelope = ErrorEnvelope(**profile["error"])
    assert envelope.code == "parse_failed"


# ==================== 4) 反证常驻 ====================


def test_the_predicate_is_semantic_so_reverting_to_a_literal_dtype_string_goes_red():
    """反证①：把判定改回比 dtype 的字面串，这枚立刻红 —— 界面上「没有文本列」就是这么来的。"""
    source = (ROOT / "app" / "tools" / "excel.py").read_text(encoding="utf-8")

    assert '"object"' not in source
    assert "'object'" not in source
    assert "dtype ==" not in source
    assert "pd.api.types.is_string_dtype" in source
    assert "pd.api.types.is_object_dtype" in source


def test_naming_a_text_column_without_its_count_goes_red():
    """反证②：只改判定、不发 unique_values ⇒ 本枚红。名单对了而屏上那格照旧空着，等于没修。"""
    from app.tools.excel import profile_dataframe

    profile = profile_dataframe(_real_world_frame())

    named = set(profile["text_columns"])
    assert named, "文本列名单又空了"
    with_count = {column["name"] for column in profile["columns"] if "unique_values" in column}
    assert named == with_count, f"名单说它是文本列、统计键却没发：{named - with_count}"
    for column in profile["columns"]:
        if column["name"] in named and profile["empty"] is False:
            assert isinstance(column["unique_values"], int)
            assert column["unique_values"] > 0, "有行的文本列报出 0 个取值，等于没数"