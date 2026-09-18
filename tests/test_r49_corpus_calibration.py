"""R49 判据④：排除规则对 documents/ 真实业务语料必须零误伤，余量还要能复算。

这个文件跑的是盘上真实目录、真实解析链路（``app.rag.loader.load_document``，与上传端点走的
同一条），不是夹具。它同时是"命中排除的篇数 = 0"这条交付证据的复跑入口：

    python -m pytest tests/test_r49_corpus_calibration.py -p no:cacheprovider -q --no-header -s

四道阈值都留了至少 1.5 倍余量，且余量本身被断言钉住——新语料一旦贴近某条阈值，这里就会
变红，逼一次重新校准，而不是等到某篇文档在生产上悄悄不入索引才发现。
"""
from pathlib import Path

import pytest

from app.documents import index_policy
from app.documents.index_policy import evaluate_index_eligibility
from app.rag.loader import load_document

# 本单核对的是仓库里这份语料，不是部署实例的 DOCUMENTS_DIR：判据④问的就是这 96 篇。
CORPUS_DIR = Path(__file__).resolve().parents[1] / "documents"

#: 断言余量倍数：语料实测值与阈值之间至少要差这么多倍。
MARGIN = 1.5

KEYWORD_NAMED = ("草稿", "模板", "试行", "临时", "初稿", "告别信")


def _corpus_files():
    return sorted(
        path
        for path in CORPUS_DIR.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )


@pytest.fixture(scope="session")
def measured_corpus():
    rows = []
    for path in _corpus_files():
        text = load_document(str(path))
        eligibility = evaluate_index_eligibility(text, size_bytes=path.stat().st_size)
        rows.append((path.name, eligibility))
    return rows


def _metrics(rows, key):
    return [row[1].metrics.get(key, 0.0) for row in rows]


def test_the_repository_corpus_is_present_and_big_enough_to_mean_something():
    files = _corpus_files()

    assert CORPUS_DIR.is_dir(), f"缺少真实语料目录：{CORPUS_DIR}"
    assert len(files) >= 90, f"语料只有 {len(files)} 篇，这个核对没有意义"


def test_not_one_corpus_document_is_excluded(measured_corpus):
    excluded = [name for name, eligibility in measured_corpus if not eligibility.eligible]

    assert excluded == [], f"排除规则误伤现有语料：{excluded}"
    assert len(measured_corpus) >= 90


def test_the_files_whose_names_say_draft_or_template_are_all_indexed(measured_corpus):
    """文件名写着草稿/模板的几篇必须照常入索引——这正是"按内容判"要保住的样本。"""
    named = [(name, eligibility) for name, eligibility in measured_corpus if any(k in name for k in KEYWORD_NAMED)]

    assert named, "语料里找不到带草稿/模板字样的文件，本用例失去意义"
    wrongly_excluded = [name for name, eligibility in named if not eligibility.eligible]

    assert wrongly_excluded == [], f"按文件名会误伤、按内容也必须放行，却仍被排除：{wrongly_excluded}"


def test_the_corpus_clears_the_content_floor_with_room_to_spares(measured_corpus):
    floor = index_policy.min_content_chars()
    thinnest = min(_metrics(measured_corpus, "content_chars"))

    assert thinnest >= index_policy.MIN_CONTENT_CHARS_CORPUS_FLOOR, (
        f"语料出现比标定值({index_policy.MIN_CONTENT_CHARS_CORPUS_FLOOR})更短的正文：{thinnest}，"
        "需要重新校准阈值"
    )
    assert thinnest >= floor * MARGIN
    # 运维把下限上调到这个数以内都不会碰到语料，"超小文档"这条规则因此是可用的。
    assert thinnest > index_policy.OUTLINE_MAX_CONTENT_CHARS


def test_the_corpus_placeholder_ratio_stays_far_below_the_template_threshold(measured_corpus):
    worst = max(_metrics(measured_corpus, "placeholder_ratio"))

    assert worst <= index_policy.PLACEHOLDER_CHAR_RATIO / MARGIN, (
        f"语料最高占位符比例 {worst} 距阈值 "
        f"{index_policy.PLACEHOLDER_CHAR_RATIO} 余量不足 {MARGIN} 倍"
    )


def test_the_corpus_outline_ratios_stay_far_below_the_skeleton_thresholds(measured_corpus):
    empty = max(_metrics(measured_corpus, "empty_section_ratio"))
    heading = max(_metrics(measured_corpus, "heading_ratio"))

    assert empty <= index_policy.OUTLINE_EMPTY_SECTION_RATIO / MARGIN, empty
    assert heading <= index_policy.OUTLINE_HEADING_CHAR_RATIO / MARGIN, heading


def test_no_corpus_document_is_read_as_a_placeholder_or_skeleton_at_all(measured_corpus):
    """逐篇点名：任何一条规则在语料上都不该"差一点就命中"。"""
    near = [
        (
            name,
            eligibility.reason,
            eligibility.metrics,
        )
        for name, eligibility in measured_corpus
        if eligibility.metrics.get("placeholder_tokens", 0) >= index_policy.PLACEHOLDER_MIN_TOKENS
        and eligibility.metrics.get("placeholder_ratio", 0)
        >= index_policy.PLACEHOLDER_CHAR_RATIO / MARGIN
    ]

    assert near == [], f"多篇语料的占位符密度已接近判据：{[row[0] for row in near]}"


def test_the_two_evaluation_documents_this_round_is_adding_would_clear_the_rules():
    """本轮另有一线要往 documents/ 加《指标口径登记表》《报销明细表》。

    它们还没落盘，所以这里按它们必然的形状（表头 + 一行一条口径/明细）复算一遍：判据要按
    内容特征判，就不能等它们进来之后才发现被挡在门外。
    """
    registry = (
        "指标口径登记表\n\n"
        "| 指标名称 | 计算口径 | 数据来源 | 责任人 |\n"
        "|---|---|---|---|\n"
        "| 营业收入 | 不含税已确认收入，确认时点为发货签收 | ERP-应收单 | 财务部 |\n"
        "| 毛利率 | 毛利除以营业收入，按季度累计 | 财务凭证 | 财务部 |\n"
        "| 回款率 | 实收金额除以当期开票金额 | 银行流水 | 财务部 |\n"
    )
    expenses = (
        "报销明细表\n\n"
        "| 日期 | 报销人 | 部门 | 事由 | 金额 | 凭证号 |\n"
        "|---|---|---|---|---|---|\n"
        "| 2026-03-02 | 张三 | 销售部 | 客户拜访差旅 | 1280.00 | BX-2026-0311 |\n"
        "| 2026-03-05 | 李四 | 市场部 | 展会物料制作 | 460.00 | BX-2026-0312 |\n"
        "| 2026-03-11 | 王五 | 研发部 | 客户端软件许可 | 3600.00 | BX-2026-0313 |\n"
    )

    assert evaluate_index_eligibility(registry).eligible is True
    assert evaluate_index_eligibility(expenses).eligible is True


def test_the_policy_never_opens_a_corpus_file_for_reading_its_name():
    """判据④的制度保障：整条判定只吃正文，语料文件名连进都不进判定。"""
    source = Path(index_policy.__file__).read_text(encoding="utf-8")

    assert "documents/" in source  # 文档里写着语料路径，是注释不是代码
    assert ".stem" not in source
    assert "os.path.splitext" not in source
    assert "startswith(" not in source


def test_report_the_calibration_numbers_of_the_real_corpus(measured_corpus):
    """交付证据的复跑出口：命中排除的篇数，加上每条判据在语料上的最贴近值。

    带 ``-s`` 跑就能拿到下面这段原文：

        python -m pytest tests/test_r49_corpus_calibration.py -p no:cacheprovider -q --no-header -s
    """
    excluded = [name for name, eligibility in measured_corpus if not eligibility.eligible]
    content = _metrics(measured_corpus, "content_chars")
    placeholder = _metrics(measured_corpus, "placeholder_ratio")
    empty = _metrics(measured_corpus, "empty_section_ratio")
    heading = _metrics(measured_corpus, "heading_ratio")

    print("")
    print(f"[R49] 语料篇数 = {len(measured_corpus)}；命中排除的篇数 = {len(excluded)}；{excluded}")
    print(f"[R49] 正文实质字符：最短 {min(content)} / 中位 {sorted(content)[len(content) // 2]} / 最长 {max(content)}"
          f"（排除下限 {index_policy.min_content_chars()}，草稿骨架长度上限 "
          f"{index_policy.OUTLINE_MAX_CONTENT_CHARS}）")
    print(f"[R49] 占位符占非空白字符比例：最高 {max(placeholder)}"
          f"（排除阈值 {index_policy.PLACEHOLDER_CHAR_RATIO}）")
    print(f"[R49] 空正文小节比例：最高 {max(empty)}（阈值 {index_policy.OUTLINE_EMPTY_SECTION_RATIO}）；"
          f"标题字符占比：最高 {max(heading)}（阈值 {index_policy.OUTLINE_HEADING_CHAR_RATIO}）")

    assert excluded == []
    assert all(row[1].metrics for row in measured_corpus), "每篇都要留下判定依据的特征值"
