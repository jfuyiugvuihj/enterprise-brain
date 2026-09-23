r"""R192 · 排名条数读中文数词，零数值列说事实句 —— 两枚病灶各钉一条真产物腿。

写域：`app/agents/tools.py`。产物断言一律走真产物（`_answer_query` 与整条 `_analyze_data`
工具腿的返回串原文），不钉源码形状了事——R185 那笔教训照抄：只钉源码形状会当场放行一条断路。

枚一（「排名前三」实际给前 10 行）。门店表（3 行：营收 300/200/100）上「营收排名前三」：
    改前 '📊 按 营收 排名前10:\n  建国路: 营收=300, 利润=30\n  人民路: 营收=200, 利润=20\n  中山路: 营收=100, 利润=10'
    改后 '📊 按 营收 排名前3:\n  建国路: 营收=300, 利润=30\n  人民路: 营收=200, 利润=20\n  中山路: 营收=100, 利润=10'
同一张表上「前二/前三/前五/前十名」四种写法改前读数完全相同（全是那枚默认 10）——那正是
"问三答十"印得出来的原因。本文件把它们逐档拆开钉，并在一张 12 行表上量真取了几行。

枚二（异常被吞成"这份文件没结论"，零日志）。零数值列 + 问句含"排名/前"时 `num_cols[0]`
抛 IndexError，被 `_analyze_data` 的 `except Exception: pass` 整个吞掉。改前真 traceback
（唯一一层合成帧是调用方的 spy 壳，异常本身与 tools.py 那一帧全是真打 `_analyze_data` 所得）：

    Traceback (most recent call last):
      File "...\tests\test_r192_probe_tmp.py", line 60, in spy
        return original(*args, **kwargs)
               ^^^^^^^^^^^^^^^^^^^^^^^^^
      File "...\app\agents\tools.py", line 410, in _answer_query
        sort_col = first_num_col or num_cols[0]
                                    ~~~~~~~~^^^
    IndexError: list index out of range

同一次真打交回去的返回串里没有任何一条结论，证据袋 `tool_statuses` 是空表 `[]`：运维侧一个
字都没有，现场不可复现。改后异常不再发生，返回串多出一行事实句；记账那一层落在真异常那条腿
上（`test_an_exception_on_the_analysis_leg_is_recorded`）。两层分开，不共用一条通路。

具名延伸（判据之外的一格，先说在这里）：撞上时间单位的阿拉伯数字，改前交出的是被截出来的
假条数——「前30年的营收排名」改前给 30、「提前3天…」改前给 3（实测逐字见
`test_a_truncated_time_span_stops_printing_a_number_it_never_meant`）。本单把这两形摘回默认
条数，因为它们与"问三答十"是同族的一种假话；零匹配那一头（默认条数本身）一个字没动。

两把反证（本文件负责具名）：
  (a) 把 `_RANKING_COUNT_RE` 整个退回 HEAD 那一枚 `re.search(r"前\s*(\d+)", query)`
      ⇒ 8 枚红（实取，`8 failed, 8 passed`）：
      `test_the_same_count_written_two_ways_returns_the_same_bytes`
      `test_chinese_counts_take_exactly_the_rows_the_title_promises`
      `test_a_composed_chinese_number_is_not_read_as_its_first_character`
      `test_the_reading_on_a_short_table_is_byte_for_byte_the_fixed_count`
      `test_no_count_and_non_ranking_prefixes_all_fall_back_to_the_old_default`
      `test_a_truncated_time_span_stops_printing_a_number_it_never_meant`
      `test_the_count_probe_reads_exactly_what_the_screen_then_prints`
      `test_the_two_layers_do_not_share_one_accounting_path`（那一支的产物本身也要"前三"）；
  (b) 把 `_analyze_data` 那一支重新吞成静默 `pass` ⇒ 恰 1 枚红（`1 failed, 15 passed`），
      且必须是记账那枚：`test_an_exception_on_the_analysis_leg_is_recorded_instead_of_swallowed`。
      那张脸的几枚在 (b) 下全绿——两层各钉各的，正是判据要"别混"的那个形状。
      两把反证跑完都逐字还原，`app/agents/tools.py` 的 sha256 前后同为 8af54b61a680。
"""

from pathlib import Path

import pandas as pd

from app.agents import evidence, tools

ROOT = Path(__file__).resolve().parents[1]
TOOLS_SOURCE = (ROOT / "app" / "agents" / "tools.py").read_text(encoding="utf-8")

#: 那张脸的本尊：产物断言与"与既有几张脸两两不同句"共用这一枚引用，不在用例里另抄一份。
FACE = tools._NO_SORTABLE_NUMERIC_COLUMN_TEXT

NUM = ["营收", "利润"]
TXT = ["门店"]

#: 准入桩替身：真台账不在本件写域内，桩只顶掉「哪个文件、怎么读、行级口径」三处。
PROBE_FILE = "r192-部门销售.xlsx"


def _store_frame() -> pd.DataFrame:
    """三行门店表，与 tests/test_r189_label_column_from_query.py:38 同形（"既有产物字节不变"的对照面）。"""
    return pd.DataFrame(
        {"门店": ["中山路", "建国路", "人民路"], "营收": [100, 300, 200], "利润": [10, 30, 20]}
    )


def _twelve_frame() -> pd.DataFrame:
    """十二行门店表：行数够，"前 N"才量得出真取了 N 行，而不是标题写着 N、底下一级取满即止。"""
    revenue = [1200, 300, 1100, 400, 1000, 500, 900, 600, 800, 700, 200, 100]
    return pd.DataFrame(
        {
            "门店": [f"门店{i:02d}" for i in range(12)],
            "营收": revenue,
            "利润": [value // 10 for value in revenue],
        }
    )


def _text_only_frame() -> pd.DataFrame:
    """枚二的现场：一枚数值列都没有的花名册（列全是文本）。"""
    return pd.DataFrame({"姓名": ["张三", "李四"], "部门": ["华东", "华北"]})


def _answer(frame, query, numeric, text):
    return tools._answer_query(frame, query, numeric, text)


def _rank_block(frame, query) -> str:
    """排名那一支的产物块原文。本文件这些问法都只命中这一支，块数必须恒为 1。"""
    lines = _answer(frame, query, NUM, TXT)
    assert len(lines) == 1, lines
    return lines[0]


def _rows(block: str):
    return [line for line in block.splitlines()[1:] if line.strip()]


# ==================== 枚一 · 中文数词与阿拉伯数字同解（真产物腿） ====================

CHINESE_CASES = [
    ("营收排名前一", 1),
    ("营收排名前二", 2),
    ("营收排名前三", 3),
    ("营收排名前五", 5),
    ("营收排名前十", 10),
    ("营收排名前十名", 10),
]

ARABIC_CASES = [
    ("营收排名前2", 2),
    ("营收排名前 10", 10),
    ("营收排名前10", 10),
]


def test_the_same_count_written_two_ways_returns_the_same_bytes():
    """判据"同解"的本体：同一张表上「前 2」与「前二」必须交出逐字相同的块。"""
    frame = _twelve_frame()

    assert _rank_block(frame, "营收排名前2") == _rank_block(frame, "营收排名前二"), (
        "同解破了一边：阿拉伯数字与中文数词交回了不同的东西"
    )


def test_chinese_counts_take_exactly_the_rows_the_title_promises():
    """标题里的数与底下真给的行数一起量：只量标题会放行"改了标题没改 head"那种断路。"""
    frame = _twelve_frame()

    for query, expected in CHINESE_CASES + ARABIC_CASES:
        block = _rank_block(frame, query)
        assert block.splitlines()[0] == f"📊 按 营收 排名前{expected}:", (query, block)
        assert len(_rows(block)) == expected, (query, block)
        assert _rows(block)[0].startswith("  门店00: 营收=1200"), (query, block)


def test_a_composed_chinese_number_is_not_read_as_its_first_character():
    """「前十二十三」这类拼法不许被截成"前十"；「前十二」必须是 12 行。"""
    frame = _twelve_frame()

    block = _rank_block(frame, "营收排名前十二十三")
    assert block.splitlines()[0] == "📊 按 营收 排名前10:", block
    assert len(_rows(block)) == 10, block

    twelve = _rank_block(frame, "营收排名前十二")
    assert twelve.splitlines()[0] == "📊 按 营收 排名前12:", twelve
    assert len(_rows(twelve)) == 12, twelve


def test_the_reading_on_a_short_table_is_byte_for_byte_the_fixed_count():
    """三行表上两档的全块逐字（改后读数）：与改前只差标题里那一枚数字，行数本来就取满。"""
    frame = _store_frame()

    assert _rank_block(frame, "营收排名前三") == (
        "📊 按 营收 排名前3:\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20\n"
        "  中山路: 营收=100, 利润=10"
    )
    assert _rank_block(frame, "营收排名前二") == (
        "📊 按 营收 排名前2:\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20"
    )


# ==================== 枚一 · 零匹配与非排名语义的"前"不许误触发 ====================

NOT_A_RANKING_COUNT = [
    "营收排名",                    # 零匹配：问法里根本没给条数
    "以前的销售额怎么算",            # "前"是"以前"的一部分
    "提前一天提交的报销要什么材料",   # "前一"是"提前一天"的一部分
    "最近前五个月的营收怎么看",       # "前五个月"是时间段
    "营收排名前一百名",              # 数量级组合：认成"前一"就是一枚新假话
    "前30年的营收排名",              # 数字没吃完就截一刀，那是"前3"那类假话
]


def test_no_count_and_non_ranking_prefixes_all_fall_back_to_the_old_default():
    """六形改后一律落回默认 10（＝改前那枚默认条数）。

    其中「前一百名」与「前30年」「提前3天」三形的改前读数并不都是 10：中文那两形改前落 10，
    而撞上时间单位的阿拉伯形改前交出过被截出来的假条数——那一格单列一枚用例逐字钉住，
    不混在这句里说。
    """
    frame = _twelve_frame()

    for query in NOT_A_RANKING_COUNT:
        block = _rank_block(frame, query)
        assert block.splitlines()[0] == "📊 按 营收 排名前10:", query
        assert len(_rows(block)) == 10, (query, block)
        assert tools._ranking_count(query) is None, query


def test_a_truncated_time_span_stops_printing_a_number_it_never_meant():
    """判据之外的一格，具名申报：数字撞上时间单位时，改前交出的是被截出来的假条数。

    改前读数（把 `_RANKING_COUNT_RE` 整个退回 HEAD 那一枚 `re.search(r"前\\s*(\\d+)", query)`
    之后实测，12 行表，走 `_answer_query` 真产物腿）：
        「前30年的营收排名」            标题 '📊 按 营收 排名前30:'，底下 12 行（表不足 30，取满即止）
        「提前3天提交的报销要什么材料」  标题 '📊 按 营收 排名前3:'，底下 3 行
    改后：两形都落回默认 10，标题与行数同为 10。为什么动它：屏上写"前3"而问的是"提前3天"，
    与"问三答十"是同族的一种假话——只不过这回是数字那一头先错。零匹配那一头本单一个字没动。
    """
    frame = _twelve_frame()

    for query in ("前30年的营收排名", "提前3天提交的报销要什么材料"):
        block = _rank_block(frame, query)
        assert block.splitlines()[0] == "📊 按 营收 排名前10:", query
        assert len(_rows(block)) == 10, (query, block)
        assert tools._ranking_count(query) is None, query


def test_the_count_probe_reads_exactly_what_the_screen_then_prints():
    """取值口自身的读数：屏上标题印的就是它，两者不可能各说各话。"""
    assert tools._ranking_count("营收排名前三") == 3
    assert tools._ranking_count("营收排名前十名") == 10
    assert tools._ranking_count("营收排名前 10") == 10
    assert tools._ranking_count("营收排名前三十") == 30
    assert tools._ranking_count("营收排名前2") == 2


# ==================== 枚二 · 第 2 层：用户可见那张脸 ====================

def test_a_text_only_file_says_it_has_no_sortable_numeric_column():
    """改前这里抛 IndexError（docstring 那段真 traceback），改后交回来的是句事实。"""
    lines = _answer(_text_only_frame(), "销售额排名前三", [], ["姓名", "部门"])

    assert lines == [FACE], lines
    assert "可排序的数值列" in FACE, FACE
    for lie in ("没结论", "无结论", "暂无数据", "没数据", "无数据", "没有数据文件"):
        assert lie not in FACE, "那张脸又说成了甩锅话：" + lie
    for guess in ("权限", "部门", "账号", "无权", "可见范围"):
        assert guess not in FACE, "因由不归这里猜，不许出现：" + guess


def test_the_fact_sentence_reaches_the_employee_through_the_real_tool_leg():
    """真打 `_analyze_data`：事实句必须出现在工具返回串原文里，而且数据本体一个不少。"""
    out = _run_analyze(_text_only_frame(), "这两个人排名前三是谁")

    assert FACE in out, out
    assert "2行 × 2列" in out, "文件读到了、行也在，就不许说成没读到：" + out
    assert "数据样本(前15行)" in out, out
    assert "张三" in out, out
    for lie in ("没结论", "暂无数据文件", "本轮没有绑定任何数据文件"):
        assert lie not in out, "把算不出来说成了另一种事：" + lie


def test_the_fact_is_not_said_when_the_question_never_asked_for_a_ranking():
    """同一张零数值列的表，问法里没有排名/前/排序时产物与改前逐字相同：空表，一个字节都不许多。"""
    assert _answer(_text_only_frame(), "这份表里都有哪些人", [], ["姓名", "部门"]) == []
    assert _answer(_text_only_frame(), "统计一下", [], ["姓名", "部门"]) == []


def test_a_prefix_word_that_is_not_a_ranking_still_gets_the_truth():
    """「以前的销售额」会命中既有的"前"关键词（本单不动那张关键词表）：这一支改前是崩了被吞，
    改后交回的是同一句事实——对这张表而言它本来就说得起。
    """
    assert _answer(_text_only_frame(), "以前的销售额怎么算", [], ["姓名", "部门"]) == [FACE]


def test_the_new_face_is_not_any_existing_face_in_this_file():
    """与同文件既有那几张脸两两不同句：并格就是又造出一张"看得见却读不懂"的脸。"""
    others = [
        tools._NO_BOUND_DATASET_TEXT,
        tools._HIDDEN_DATASETS_HEAD,
        tools._NO_VISIBLE_ROWS,
        "文件里没有数据行",
    ]

    for other in others:
        assert FACE != other, "与既有某张脸并成了同一句：" + other
        assert FACE[:8] not in other, FACE


# ==================== 枚二 · 第 1 层：这条腿不再静默（记账真的发生） ====================

def test_an_exception_on_the_analysis_leg_is_recorded_instead_of_swallowed():
    """反证 (b) 的靶子：把那一支退回裸 `pass`，这枚当场红——它要的是账，不是猜。"""
    config = _config()

    def explode(*args, **kwargs):
        raise IndexError("list index out of range")

    out = _run_analyze(_store_frame(), "营收排名前三", config=config, answer=explode)

    statuses = config["configurable"]["evidence_bag"]["tool_statuses"]
    assert statuses == [
        {"tool": "analyze_data", "status": "failed", "error_code": "internal_error"}
    ], statuses
    assert PROBE_FILE in out, "记了账就不许顺手把这文件已经交出去的东西吞掉：" + out
    assert "数据样本(前15行)" in out, out
    assert evidence._terminal_status(
        config["configurable"]["evidence_bag"], out
    ) == ("failed", "internal_error"), "落进袋里就必须读得出来：inert 的一条状态等于没记"


def test_the_two_layers_do_not_share_one_accounting_path():
    """那张脸（数据形状）与那枚账（真异常）分属两层：脸这条腿不记账，正常一轮更不记。"""
    face_leg = _config()
    out = _run_analyze(_text_only_frame(), "这两个人排名前三是谁", config=face_leg)
    assert FACE in out, out
    assert face_leg["configurable"]["evidence_bag"]["tool_statuses"] == [], (
        "零数值列是数据形状，不是执行失败：这一支不该往袋里落一条 failed"
    )

    clean = _config()
    assert "排名前3" in _run_analyze(_store_frame(), "营收排名前三", config=clean)
    assert clean["configurable"]["evidence_bag"]["tool_statuses"] == [], "正常一轮凭什么落失败状态"


# ==================== 判据 1 的对照面：有数值列时既有产物字节不变 ====================

def test_the_pre_existing_products_on_a_numeric_table_are_byte_for_byte_unchanged():
    """三处消费的改前字节逐字重钉（与 R189 同源的那批读数，本单一颗字节都没挪）。"""
    frame = _store_frame()

    assert _answer(frame, "哪个营收最高", NUM, TXT) == [
        "🎯 最高(营收): 建国路 — 营收=300"
    ]
    assert _answer(frame, "看看营收", NUM, TXT) == [
        "📊 数据预览 (按营收降序):\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20\n"
        "  中山路: 营收=100, 利润=10"
    ]
    assert _rank_block(frame, "销售额排名前2") == (
        "📊 按 营收 排名前2:\n"
        "  建国路: 营收=300, 利润=30\n"
        "  人民路: 营收=200, 利润=20"
    )


# ==================== 形状守卫：这条归一只许有一处 ====================

def test_the_ranking_count_has_exactly_one_probe_and_one_consumer():
    """不许长出第二套"前 N"取数：老正则必须消失，取值口必须只有一个消费者。"""
    assert 're.search(r"前\\s*(\\d+)", query)' not in TOOLS_SOURCE, (
        "只认阿拉伯数字的那枚老正则又回来了"
    )
    assert TOOLS_SOURCE.count("= _ranking_count(") == 1, "「前 N」的取数出现了第二处"
    assert TOOLS_SOURCE.count("_RANKING_COUNT_RE") == 2, "一枚定义一处使用，多出来的就是第二套解析器"
    assert TOOLS_SOURCE.count("_NO_SORTABLE_NUMERIC_COLUMN_TEXT") == 2, (
        "那张脸只有一个出处：定义 + 排名那一支"
    )


# ==================== 夹具：真打工具腿，只绕开准入、读文件与行级口径 ====================


def _config() -> dict:
    return {
        "configurable": {
            "user_id": "7",
            "username": "r192",
            "role": "manager",
            "department": "finance",
            "evidence_bag": evidence.new_evidence_bag(),
        }
    }


def _run_analyze(frame, query: str, config=None, answer=None) -> str:
    """真打 `_analyze_data`：桩只顶在准入/读文件/行级口径三处，算名单与出答案全是生产代码。

    执行层不许在模块导入期改全局，所以这里是"用例内装桩 + 交回时逐条还原"，与 R189 的
    monkeypatch 同效而不越它的写域（本件不 import 那个文件，避免把别人的桩借来当自己的证据）。
    """
    import app.common.rbac as rbac
    import app.tools.excel as excel
    from app.storage import datasets as dataset_storage

    config = config if config is not None else _config()
    previous = []

    def install(owner, name, value):
        previous.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    install(tools, "_authorized_dataset_files", lambda cfg: ([(PROBE_FILE, "p")], None))
    install(dataset_storage.dataset_registry, "get_active_by_filename", lambda filename: None)
    install(tools, "_record_dataset_evidence", lambda cfg, filename, df: None)
    install(excel, "load_excel", lambda path: frame)
    install(
        rbac,
        "filter_dataframe_rows_with_scope",
        lambda df, role=None, department=None: (
            df,
            {"rows_in": int(df.shape[0]), "rows_out": int(df.shape[0])},
        ),
    )
    if answer is not None:
        install(tools, "_answer_query", answer)
    try:
        return tools._analyze_data(query, config)
    finally:
        for owner, name, value in previous:
            setattr(owner, name, value)
