"""R185 · 文本列名单全树只有一条通路：analyze_data 不再自己比 dtype 字面串。

复验读数（本树 pandas 3.0.3 亲跑，与简报口径有出入，如实记在这里）：
    `app/agents/tools.py` 旧 :1045 那一式 `df.select_dtypes(include=["object"])` 在真机读入的
    `str` 列上**并非恒空** —— pandas 3 还留着一条明写「will be removed in a future version」的
    向后兼容通道替它兜底，代价是每调一次漏一枚 Pandas4Warning。恒空今天只在
    `string` / `category` 两族 dtype 上成立，而那两族一旦是分组列，「哪个部门销售额最高」
    就退化成一句连名字都没有的数据预览。兼容通道一撤，`str` 列跟着一起塌。
    所以这枚修的是「踩在一条声明要撤的通道上」＋「今天已经在漏的两族」，不是修一处全员可见的空。

判据 3 的端到端凭据（同一张合成帧、同一句问法，逐字）：
    category 帧   修前 text_cols=[]        -> ['📊 数据预览 (按销售额降序):\\n  : 销售额=260\\n  : 销售额=140\\n  : 销售额=100']
                  修后 text_cols=['部门']  -> ['🎯 最高(销售额): 华北 — 销售额=260']
    str 帧        修前 text_cols=['部门']  -> ['🎯 最高(销售额): 华北 — 销售额=260']（同一读数，但每次调用漏一枚 Pandas4Warning）
                  修后 text_cols=['部门']  -> ['🎯 最高(销售额): 华北 — 销售额=260']（零枚告警）

本文件钉三条腿：真逻辑（谓词与名单）、真产物（`_analyze_data` 的返回串）、源码形状（唯一通路）。
反证常驻两把：把新出口退回字面 dtype 串 ⇒ 本文件红；名单算对了却不接进 :345 那一支的取数路径 ⇒ 本文件红。
"""

import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS_SOURCE = (ROOT / "app" / "agents" / "tools.py").read_text(encoding="utf-8")

QUERY = "哪个部门销售额最高"
RANKING_LINE = "🎯 最高(销售额): 华北 — 销售额=260"
# 修前那一支的退化产物：分组列名单空着，兜底预览里的名字那格就跟着空。
BLANK_NAME_PREVIEW = "  : 销售额=260"


def _frame(grouping: str = "str") -> pd.DataFrame:
    """一张真机形状的排名表：只有分组列的 dtype 可变，问法与数值列都不动。"""
    return pd.DataFrame(
        {
            "部门": pd.Series(["华东", "华北", "华南"], dtype=grouping),
            "销售额": [100, 260, 140],
        }
    )


def _legacy_text_columns(frame: pd.DataFrame) -> list:
    """修前原式，逐字抄自旧 :1045 —— 留着它，本文件的「修前」才有可比的那一侧。"""
    return frame.select_dtypes(include=["object"]).columns.tolist()


def _config() -> dict:
    return {
        "configurable": {
            "user_id": "7",
            "username": "tester",
            "role": "manager",
            "department": "finance",
        }
    }


def _patch_data_leg(monkeypatch, frame) -> None:
    """绕开数据集准入、Excel 与行级口径，只留「读帧 → 算名单 → 出答案」这一条路。"""
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.agents import tools
    from app.storage import datasets as dataset_storage

    monkeypatch.setattr(tools, "_authorized_dataset_files", lambda config: ([("部门销售.xlsx", "p")], None))
    monkeypatch.setattr(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)
    monkeypatch.setattr(tools, "_record_dataset_evidence", lambda config, filename, df: None)
    monkeypatch.setattr(excel, "load_excel", lambda path: frame)
    monkeypatch.setattr(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (df, {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])}),
    )


# ==================== 1) 真逻辑：出口收整族字符串形态，且只有一条通路 ====================


def test_the_shared_export_covers_the_string_family_the_legacy_selector_drops():
    """判据①：真机字符串帧上 text_cols 必须给得出列 —— 今天已经在漏的是 string / category 两族。"""
    from app.tools.excel import select_text_columns

    frame = pd.DataFrame(
        {
            "部门": ["华东", "华北"],
            "别称": pd.Series(["A", "B"], dtype="string"),
            "类别": pd.Series(["甲", "乙"], dtype="category"),
            "备注": pd.Series(["混装", 1], dtype="object"),
            "计数": [1, 2],
            "单价": [1.5, 2.5],
            "开关": [True, False],
            "开机日": pd.to_datetime(["2026-01-01", "2026-02-01"]),
        }
    )

    assert select_text_columns(frame) == ["部门", "别称", "类别", "备注"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert _legacy_text_columns(frame) == ["部门", "备注"], "旧式漏掉的那两族是这枚单存在的理由"


def test_the_export_lists_labels_in_frame_order_so_the_first_one_is_predictable():
    """名单顺序＝列顺序：`_answer_query` 取 txt_cols[0] 当名字列，不能靠 dtype 通道决定谁在前。"""
    from app.tools.excel import select_text_columns

    frame = pd.DataFrame({"乙文本": ["a", "b"], "数值": [1, 2], "甲文本": ["c", "d"]})

    columns = select_text_columns(frame)

    assert columns == ["乙文本", "甲文本"]
    for column in columns:
        assert len(frame[column]) == 2, "返回的必须是能直接 frame[col] 取数的原始标签"


def test_the_numeric_list_keeps_its_own_selector_and_stays_disjoint_from_the_text_list():
    """判据①后半：`include=["number"]` 那一支一字未动，bool 仍两份名单都不进（改前改后同口径）。"""
    from app.tools.excel import select_text_columns

    frame = pd.DataFrame({"计数": [1, 2], "开关": [True, False], "部门": ["华东", "华北"]})

    numeric = frame.select_dtypes(include=["number"]).columns.tolist()
    text = select_text_columns(frame)

    assert numeric == ["计数"]
    assert text == ["部门"]
    assert set(numeric) & set(text) == set()


def test_the_string_dtype_predicate_lives_in_exactly_one_module_of_app():
    """判据②的常驻守卫：谓词只许有一处实现，第二份＝给 R182 立的口径添一张平行嘴。"""
    hits = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "app").rglob("*.py"))
        if "is_string_dtype" in path.read_text(encoding="utf-8")
        or "is_object_dtype" in path.read_text(encoding="utf-8")
    ]

    assert hits == ["app/tools/excel.py"], f"文本列判定出现了第二处实现：{hits}"


# ==================== 2) 真逻辑：:345 那一支的取数路径真的接上了 ====================


def test_the_ranking_branch_only_answers_once_the_grouping_column_is_counted():
    """判据③的第一条腿：同一张 category 帧、同一句问法，喂旧名单答不出、喂新名单答得出。"""
    from app.agents.tools import _answer_query
    from app.tools.excel import select_text_columns

    frame = _frame("category")
    numeric = frame.select_dtypes(include=["number"]).columns.tolist()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        starved = _answer_query(frame, QUERY, numeric, _legacy_text_columns(frame))
    fed = _answer_query(frame, QUERY, numeric, select_text_columns(frame))

    assert BLANK_NAME_PREVIEW in "\n".join(starved), starved
    assert not any(line.startswith("🎯") for line in starved), f"旧名单饿不饿这一支要钉住：{starved}"
    assert [line for line in fed] == [RANKING_LINE], fed


def test_the_grouping_branch_groups_by_a_text_column_it_can_now_see():
    """同一份名单还喂给「对比/分组」那一支：饿死的不只排名一支。"""
    from app.agents.tools import _answer_query
    from app.tools.excel import select_text_columns

    frame = pd.DataFrame(
        {"部门": pd.Series(["华东", "华北", "华东"], dtype="category"), "销售额": [100, 200, 300]}
    )

    lines = _answer_query(frame, "按部门分组对比销售额", ["销售额"], select_text_columns(frame))

    assert any(line.startswith("📋 按 部门 分组汇总:") for line in lines), lines


# ==================== 3) 真产物：`_analyze_data` 的返回串 ====================


def test_analyze_data_hands_the_employee_a_named_top_row_for_a_category_grouping_column(monkeypatch):
    """判据③的第二条腿：整条工具腿走通，员工问的那句拿到有名有姓的那一行。"""
    from app.agents.tools import _analyze_data

    _patch_data_leg(monkeypatch, _frame("category"))

    answer = _analyze_data(QUERY, _config())

    assert RANKING_LINE in answer, answer
    assert BLANK_NAME_PREVIEW not in answer, "又退化成连名字都没有的数据预览"


def test_analyze_data_still_answers_for_a_plain_string_frame_without_borrowing_the_deprecated_channel(monkeypatch):
    """str 帧改前改后同一读数，但改后不再踩那条声明要撤的兼容通道 —— 这才是这枚单的未来那条腿。"""
    from app.agents.tools import _analyze_data

    _patch_data_leg(monkeypatch, _frame("str"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        answer = _analyze_data(QUERY, _config())

    assert RANKING_LINE in answer, answer
    kinds = {item.category.__name__ for item in caught}
    assert "Pandas4Warning" not in kinds, f"还在靠将撤的兼容通道捞列，撤那天就是恒空：{kinds}"


def test_the_deprecated_channel_is_what_kept_the_legacy_expression_alive(monkeypatch):
    """环境事实（与 R182 钉 dtype 同一手法）：旧式在 str 帧上今天还给得出列，但是付费换来的。

    这一枚是绊线：pandas 真把那条兼容通道撤掉的那天它红，红的那一刻正好证明简报里
    「恒空」那一格从明天开始才成立 —— 别把它当噪音删掉。
    """
    frame = _frame("str")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        columns = _legacy_text_columns(frame)

    assert columns == ["部门"], f"兼容通道的行为变了，本文件的「修前」侧需要重新取证：{columns}"
    assert "Pandas4Warning" in {item.category.__name__ for item in caught}


# ==================== 4) 源码形状 ====================


def test_analyze_data_takes_its_text_columns_from_the_shared_export():
    """判据②的形状那一腿：改动的两处必须钉在源码上，反证①一退形就红在这里。"""
    assert "from app.tools.excel import load_excel, profile_dataframe, select_text_columns" in TOOLS_SOURCE
    assert "text_cols = select_text_columns(df)" in TOOLS_SOURCE
    assert 'text_cols = df.select_dtypes(include=["object"]).columns.tolist()' not in TOOLS_SOURCE
    assert '"object"' not in TOOLS_SOURCE
    assert "'object'" not in TOOLS_SOURCE
    assert "dtype ==" not in TOOLS_SOURCE


def test_the_numeric_selection_line_is_still_the_untouched_number_selector():
    """:1044 一字未动（判据①后半的形状侧）。"""
    assert 'numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()' in TOOLS_SOURCE


def test_the_export_delegates_to_the_predicate_instead_of_reimplementing_it():
    """出口只许是层薄壳：判定本体留在 `_is_text_series`，不许在两处各写一份 or 式。"""
    excel_source = (ROOT / "app" / "tools" / "excel.py").read_text(encoding="utf-8")
    export = excel_source.split("def select_text_columns", 1)[1].split("def profile_dataframe", 1)[0]

    assert "_is_text_series(" in export
    assert "is_string_dtype" not in export
    assert "is_object_dtype" not in export
    assert excel_source.count("pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)") == 1