"""R189 · 名字列按问法选：三处消费不再一律取 txt_cols[0]。

病灶（总控按 30465a1 实取行号，app/agents/tools.py）：
    :342  first_txt_col = txt_cols[0] if txt_cols else ""
    三处消费  :362 排名答案 / :386 前 N 名逐行标签 / :435 兜底预览
同一函数里数值列那一支 :349 早就有"按问法选列"的规矩，注释 C3 的原话是"多列且无匹配时所有数值列
都给出，避免静默选错列"。文本列没有 —— 本单补的就是这枚不对称。

改前 / 改后逐字读数（本文件每一条产物断言都取自这里的实测，不是记忆）：
    帧 {姓名, 部门, 销售额}，问「哪个部门销售额最高」
        修前 ['🎯 最高(销售额): 李四 — 销售额=260']      拿人名回答"哪个部门"
        修后 ['🎯 最高(销售额): 华北 — 销售额=260']
    同一帧，问「哪个销售额最高」（点不出名字列、两列候选）
        修前 ['🎯 最高(销售额): 李四 — 销售额=260']      静默取第 0 列
        修后 ['🎯 最高(销售额): 姓名=李四 — 销售额=260'] 判据 2 形态 (a)：带出按哪一列作答
    帧 {门店, 营收, 利润}（只有一个候选列）
        修前 = 修后 ['🎯 最高(营收): 建国路 — 营收=300'] 判据 3：产物字节不变

腿：真产物（`_answer_query` 与整条 `_analyze_data` 工具腿的返回串原文）、改前字节（三处消费逐字）、
源码形状（选列结论只有一份、不再无条件取第 0 列、前缀那一支仍在）。
反证常驻两把：把选列退回 txt_cols[0] ⇒ 本文件红；把"按哪一列作答"的前缀抹掉 ⇒ 本文件红。
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOLS_SOURCE = (ROOT / "app" / "agents" / "tools.py").read_text(encoding="utf-8")

# R185 钉死的那行排名读数（tests/test_r185_text_columns_single_path.py:30），本单修后逐字相同。
RANKING_LINE = "🎯 最高(销售额): 华北 — 销售额=260"
# 病灶原样：拿人名回答"哪个部门"，也是"把选列退回 txt_cols[0]"那把反证的产物形状。
SILENT_PERSON_LINE = "🎯 最高(销售额): 李四 — 销售额=260"


def _people_frame() -> pd.DataFrame:
    """一张真机形状的销售表：姓名在前、部门在后，两列都是文本候选。"""
    return pd.DataFrame(
        {
            "姓名": ["张三", "李四", "王五"],
            "部门": ["华东", "华北", "华南"],
            "销售额": [100, 260, 140],
        }
    )


def _store_frame() -> pd.DataFrame:
    """只有一个文本候选的门店表 —— 判据 3 的对照组（帧抄自 tests/test_phase0_fixes.py:47）。"""
    return pd.DataFrame(
        {"门店": ["中山路", "建国路", "人民路"], "营收": [100, 300, 200], "利润": [10, 30, 20]}
    )


def _answer(df, query, numeric, text):
    from app.agents.tools import _answer_query

    return _answer_query(df, query, numeric, text)


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
    """绕开数据集准入、Excel 与行级口径，只留「读帧 → 算名单 → 出答案」这一条路（与 R185 同型）。"""
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


# ==================== 判据 1 · 问法点名的维度优先 ====================


def test_a_named_dimension_is_the_dimension_the_answer_carries():
    """逐字反证：把选列退回 txt_cols[0]，这枚当场红 —— 病灶就是这么读出来的。"""
    lines = _answer(_people_frame(), "哪个部门销售额最高", ["销售额"], ["姓名", "部门"])

    assert lines == [RANKING_LINE], lines
    assert SILENT_PERSON_LINE not in lines, "又拿人名回答「哪个部门」"


def test_the_lowest_reading_follows_the_named_dimension_too():
    """同一枚选列管着最高与最低两侧，不是只把最显眼那一格糊过去。"""
    lines = _answer(_people_frame(), "哪个部门销售额最低", ["销售额"], ["姓名", "部门"])

    assert lines == ["🎯 最低(销售额): 华东 — 销售额=100"], lines


def test_analyze_data_hands_the_employee_a_department_for_a_which_department_question(monkeypatch):
    """真产物腿（抄 R185 的交工教训）：只钉源码文本不算修好，员工看的那句答案得自己站得住。"""
    from app.agents.tools import _analyze_data

    _patch_data_leg(monkeypatch, _people_frame())

    answer = _analyze_data("哪个部门销售额最高", _config())

    assert [line for line in answer.splitlines() if line.startswith("🎯")] == [RANKING_LINE], answer
    assert "  李四: " not in answer, "兜底预览那一支还在逐行点名"


# ==================== 判据 2 · 无点名列且多候选：显式带出按哪一列作答 ====================


def test_two_candidates_and_no_name_says_which_column_it_answered_by():
    """判据 2 取形态 (a)：第 0 列仍然是答案，但它把自己报出来了，不再静默选错。"""
    lines = _answer(_people_frame(), "哪个销售额最高", ["销售额"], ["姓名", "部门"])

    assert lines == ["🎯 最高(销售额): 姓名=李四 — 销售额=260"], lines
    assert lines[0] != SILENT_PERSON_LINE, "前缀一抹掉就又回到静默取第 0 列"


def test_the_pick_is_still_deterministic_when_the_question_names_nothing():
    """名单顺序＝列顺序：换一张列序相反的帧，取的是另一枚，并且照样标出来。"""
    frame = pd.DataFrame({"部门": ["华东", "华北"], "姓名": ["张三", "李四"], "销售额": [100, 260]})

    lines = _answer(frame, "哪个销售额最高", ["销售额"], ["部门", "姓名"])

    assert lines == ["🎯 最高(销售额): 部门=华北 — 销售额=260"], lines


def test_the_ranking_list_tags_the_column_it_answered_by_too():
    """`:386` 那一支与排名答案同一个洞：前 N 名的逐行标签同样要点名，且行数不许翻倍。"""
    frame = _people_frame()

    lines = _answer(frame, "销售额排名前2", ["销售额"], ["姓名", "部门"])

    assert lines == ["📊 按 销售额 排名前2:\n  姓名=李四: 销售额=260\n  姓名=王五: 销售额=140"], lines
    assert len(lines[0].splitlines()) == 3, "逐列重播会让行数随候选列数翻倍，装箱预算先撞墙"


# ==================== 判据 3 · 无点名列且单候选：产物字节不变 ====================


def test_one_candidate_and_no_name_is_byte_for_byte_what_it_always_was():
    """三处消费的改前实测字节逐字钉住：单候选时一个字节都不许多。"""
    frame = _store_frame()

    assert _answer(frame, "哪个营收最高", ["营收", "利润"], ["门店"]) == [
        "🎯 最高(营收): 建国路 — 营收=300"
    ]
    assert _answer(frame, "营收排名前三", ["营收", "利润"], ["门店"]) == [
        "📊 按 营收 排名前3:\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20\n"
        "  中山路: 营收=100, 利润=10"
    ]
    assert _answer(frame, "看看营收", ["营收", "利润"], ["门店"]) == [
        "📊 数据预览 (按营收降序):\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20\n"
        "  中山路: 营收=100, 利润=10"
    ]


def test_the_reading_r185_pinned_is_unchanged_on_both_sides_of_the_text_list():
    """点名 + 单候选＝R185 那行逐字；名单空着那一侧的退化产物也不许跟着变。"""
    frame = pd.DataFrame({"部门": ["华东", "华北", "华南"], "销售额": [100, 260, 140]})

    assert _answer(frame, "哪个部门销售额最高", ["销售额"], ["部门"]) == [RANKING_LINE]
    assert _answer(frame, "哪个部门销售额最高", ["销售额"], []) == [
        "📊 数据预览 (按销售额降序):\n  : 销售额=260\n  : 销售额=140\n  : 销售额=100"
    ]


# ==================== 判据 5 第 4 枚 · `:435` 那一支的同类泄漏 ====================


def test_the_fallback_preview_branch_stops_answering_a_person_for_a_department():
    """`:435` 与 `:386` 是同一个洞：问法点部门、走兜底预览时，逐行标签必须是部门。"""
    lines = _answer(_people_frame(), "部门销售额明细", ["销售额"], ["姓名", "部门"])

    assert lines == [
        "📊 数据预览 (按销售额降序):\n  华北: 销售额=260\n  华南: 销售额=140\n  华东: 销售额=100"
    ], lines
    assert "李四" not in "\n".join(lines), "兜底预览还在逐行点名"


def test_the_fallback_preview_tags_the_column_it_picked_when_nothing_is_named():
    lines = _answer(_people_frame(), "看看销售额", ["销售额"], ["姓名", "部门"])

    assert lines == [
        "📊 数据预览 (按销售额降序):\n"
        "  姓名=李四: 销售额=260\n"
        "  姓名=王五: 销售额=140\n"
        "  姓名=张三: 销售额=100"
    ], lines


# ==================== 判据 4 · 三处消费同源（形状守卫） ====================


def test_the_selection_is_computed_once_and_shared_by_the_three_consumers():
    """选列结论只有一份；三处各写一份 if 迟早各自漂移，这里钉住数量。"""
    assert "first_txt_col" not in TOOLS_SOURCE, "无条件取第 0 列的那枚名字列又回来了"
    assert TOOLS_SOURCE.count("[tc for tc in txt_cols if tc in query]") == 1, "出现了第二份文本列匹配"
    assert TOOLS_SOURCE.count("label_value(") == 4, "定义一枚 + 三处消费，对不上就是有人在别处另写一份"
    assert TOOLS_SOURCE.count("name_val = label_value(row)") == 1
    assert TOOLS_SOURCE.count("name = label_value(r)") == 2


def test_the_ambiguity_tag_is_still_wired():
    """反证②：把"按哪一列作答"的前缀抹掉（退回判据 2 的另一条路），本枚与上面几枚产物一起红。"""
    assert 'label_col, label_tag = txt_cols[0], f"{txt_cols[0]}="' in TOOLS_SOURCE
