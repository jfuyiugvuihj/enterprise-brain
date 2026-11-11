#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R401 · 评测集 29 枚「查无出处」逐枚处置 + 甲/乙锚词派生出处 + 丙案分母点名扣除。

【它管什么】
    1. ``--verify``  : 把题源里每一枚 r401 记录拿语料**现算**一遍并对账（派生钉的执行体）。
    2. ``--report``  : 打印 29 枚逐枚处置表、与旧集逐枚 diff 表、correctness 分母账。
    3. ``--apply``   : 按下面的 PLAN/UNSCORABLE 落题源（只此一次；重复跑会拒绝）。

【为什么"出处"必须是派生的而不是手抄的】
    判据②：甲案锚词的 path / 原文行 / 归一化后字节位置必须由脚本从 documents/*.txt 现取。
    本件因此不 import 任何缓存，全部走 scripts/check_eval_evidence_coverage.py 的同一把尺
    （normalize / find_term_positions / load_corpus_raw），派生与校验共用一个实现，
    杜绝"写盘用一把尺、复算用另一把尺"。手抄只允许出现在 PLAN 里的**指针**
    （篇名 + 行号 + 候选锚词），路径/原文/偏移一律本件现算；算不出来就直接失败。

【零写语料】
    本件只写 tests/fixtures/business_evaluation_100.jsonl（且只在 --apply 时）。
    documents/** 一个字节都不碰：判据①「语料零变化」是本单的前提，不是可选项。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent

# 复用 R94 那把尺，不起第二套口径。
_spec = importlib.util.spec_from_file_location(
    "check_eval_evidence_coverage", SCRIPTS_DIR / "check_eval_evidence_coverage.py"
)
cov = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cov
_spec.loader.exec_module(cov)

FIXTURE_REL = cov.FIXTURE_REL
MARKER_FIELD = "r401"
ANCHOR_FIELD = "anchor_provenance"
DISPOSITIONS = ("甲", "乙", "丙")

#: 审计文档 §2.1 / R129 记的那 29 枚（历史抄本，不是"现在还缺"的集合）。


# ---------------------------------------------------------------------------
# 处置计划 —— 甲 / 乙（10 枚）
#   fields  = 要落到题源的新值（question 只有乙案动）
#   sources = 每个新 must_contain 词条的出处指针 (篇名, 原始行号)；原文与字节偏移现算
# ---------------------------------------------------------------------------
DETAILS = {
    # ---- 甲：只换锚词（题面一个字不动）------------------------------------------
    "doc-07": {
        "disposition": "甲",
        "reason": "「计发」95 篇 0 命中；语料同一句作「按自然日计算」——同一命题换字面形，判分宽度不变（仍是 2 词条 AND）。",
        "fields": {"answer": "按自然日计算", "must_contain": ["自然日", "按自然日计算"]},
        "sources": {
            "自然日": ("差旅费报销细则_2026版.txt", 21),
            "按自然日计算": ("差旅费报销细则_2026版.txt", 21),
        },
    },
    "doc-14": {
        "disposition": "甲",
        "reason": "「离职结算」0 命中；手册:39 把离职那一步登记为「财务结算（工资、报销、借款清零）」，两词原本被标点拆在同一行里，同一命题。",
        "fields": {
            "answer": "在离职交接的财务结算环节提交，由原部门负责人审批",
            "must_contain": ["财务结算"],
        },
        "sources": {"财务结算": ("企业管理制度手册.txt", 39)},
    },
    "chat-08": {
        "disposition": "甲",
        "reason": "「不叠加」0 命中；细则:17 的正面写法是「两人同性同住一间标准间的，住宿费按单人标准报销」，锚词取语料在位的「按单人标准」。",
        "fields": {
            "answer": "两人合住一间标准间不叠加，按单人标准报销",
            "must_contain": ["按单人标准"],
        },
        "sources": {"按单人标准": ("差旅费报销细则_2026版.txt", 17)},
    },
    "scope-03": {
        "disposition": "甲",
        "reason": "「超出可见范围」是产品话术、0 命中；手册:151 把薪资信息登记为「机密级」数据。新锚词要求答案说出定级依据，run5 那句走错到数据道的「当前没有工资明细数据文件」不再能命中——这是收紧。",
        "fields": {
            "answer": "拒绝：薪资信息属机密级数据，超出可见范围",
            "must_contain": ["机密级"],
        },
        "sources": {"机密级": ("企业管理制度手册.txt", 151)},
    },
    "scope-04": {
        "disposition": "甲",
        "reason": "「需单独授权」0 命中；IT安全:24「跨部门数据共享需经信息安全委员会审批」是语料里真在位的授权主体，比「需单独授权」更可考。",
        "fields": {
            "answer": "默认不可见，跨部门数据共享需经信息安全委员会审批",
            "must_contain": ["信息安全委员会"],
        },
        "sources": {"信息安全委员会": ("IT安全管理制度V3.1.txt", 24)},
    },
    "scope-06": {
        "disposition": "甲",
        "reason": "「不可以」0 命中（判分尺要原样三字）；手册:141「权限遵循最小权限原则」才是这道题的语料依据，且「最小权限」咬不住「管理员可以绕过」这类错答。",
        "fields": {
            "answer": "不可以，账号权限遵循最小权限原则，不因角色放宽",
            "must_contain": ["最小权限"],
        },
        "sources": {"最小权限": ("企业管理制度手册.txt", 141)},
    },
    "unsupported-03": {
        "disposition": "甲",
        "reason": "🔴 判据变更（收紧，不是放宽）：登记表§〇.4 规定「本表未登记的指标被问到时，必须回答『无口径登记』」，持股比例正属未登记指标 ⇒ 把「像人话的拒答」升级成「必须给出登记表具名码」。",
        "fields": {
            "answer": "无口径登记，本表未登记持股比例口径",
            "must_contain": ["无口径登记"],
        },
        "sources": {"无口径登记": ("制度与口径登记表.txt", 11)},
    },
    # ---- 乙：题面也要动（换成语料真能答的问题），桶与 category 守恒 ---------------
    "data-12": {
        "disposition": "乙",
        "reason": "R129 记题面「本季度」口径未钉 ⇒ 钉成 2026Q2 环比 2026Q1；锚词「变化率」0 命中，语料通篇用「环比」（Q1 报告:17「环比2月增长60%」）。同 tier 同 category 同桶，命题仍是「两季比较」。",
        "fields": {
            "question": "2026年Q2费用总额环比Q1多少？",
            "answer": "给出两季费用总额对比与环比",
            "must_contain": ["环比"],
        },
        "sources": {"环比": ("2026年Q1经营分析报告.txt", 17)},
    },
    "approval-03": {
        "disposition": "乙",
        "reason": "金标在城市维度本来就是错的（480 元在二线/三四线就是超标，题面未限城市）⇒ 钉「北京…480 元一晚」，锚词换成语料在位的「限额内据实报销」。这是修题，不是放水。",
        "fields": {
            "question": "北京住480元一晚超标了吗？",
            "answer": "未超一线城市500元/晚标准，属限额内据实报销",
            "must_contain": ["限额内据实报销"],
        },
        "sources": {"限额内据实报销": ("差旅费报销细则_2026版.txt", 12)},
    },
    "approval-05": {
        "disposition": "乙",
        "reason": "金标「需补开发票」与语料方向相反：「补开」95 篇 0 命中，细则:32 对遗失发票给的是「提供支付记录、行程单等辅助证明…经财务部审批后酌情处理」⇒ 把题面与金标挪到语料真规则上，锚词取「辅助证明」。",
        "fields": {
            "question": "发票遗失只有支付记录能报吗？",
            "answer": "原则上不予报销；确属客观遗失的，提供支付记录、行程单等辅助证明，经财务部审批后酌情处理",
            "must_contain": ["辅助证明"],
        },
        "sources": {"辅助证明": ("差旅费报销细则_2026版.txt", 32)},
    },
}

# ---------------------------------------------------------------------------
# 处置计划 —— 丙（19 枚）：保留题目、逐枚写明"为什么今天不可考"、挂回待派池
#   铁规：不置空 must_contain、不删题、不给覆盖度工具加排除名单。
# ---------------------------------------------------------------------------
UNSCORABLE = {
    "doc-15": (
        "语料互斥未裁：费用报销管理制度V2.1.txt:65「员工无需再打印纸质版提交」与企业管理制度手册.txt:65「电子发票需打印后附在报销单后」方向相反，登记表§〇.3 只说实体标准「以既有制度为准」而没有裁谁赢 ⇒ 换任何一边的锚词都是替业主选边。",
        "待派池：业主裁定电子发票是否需打印（R129 §25.2 同源冲突，需人裁）",
    ),
    "doc-17": (
        "语料互斥未裁：差旅费报销细则_2026版.txt:32「发票抬头须为公司全称」与费用报销管理制度V2.1.txt:51「抬头为公司全称或员工姓名（仅限差旅、通讯、交通类）」相反 ⇒ 金标的「一律」在两篇之间无据；本题三跑虽得分，正文「可以开公司抬头或员工个人抬头」与金标相反，属假阳性，不许用换锚词把它固化。",
        "待派池：业主裁定发票抬头口径（一并处理 doc-15）",
    ),
    "chat-02": (
        "本行在 tests/fixtures/business_evaluation_30.jsonl 母集里，tests/test_evaluation_report.py 的 30 行继承不漂移钉禁止改它任一字段；剩下的唯一出路是补语料，被判据①（语料零变化）否掉 ⇒ 执行层今天无解。词条「之后」95 篇 0 命中，只在备查口径的 refactor_guide.pdf 里有（与经营无关的 PDF，主口径排除）。",
        "待派池：30 行母集改版需业主批准（另单）",
    ),
    "chat-09": (
        "题面「这和你前面说的矛盾吗」的真值取决于上一轮，采集器不重放多轮历史 ⇒ 三跑正文一律「我没有上下文信息」。无论锚词换成什么，本题今天都不可考。",
        "待派池：采集器补多轮历史重放（在途单域）",
    ),
    "chat-11": (
        "锚词「800元」是用户当场注入的假设值，出处天然在会话里不在语料里；换成语料在位的「超出部分」就等于放弃「换值重算」这个考点，属放宽 ⇒ 不采纳。",
        "待派池：覆盖度需区分「语料锚」与「会话锚」（判据变更，请总控/业主裁）",
    ),
    "chat-12": (
        "题问「这个标准去年是多少」要的是历史版本语料，95 篇全是现行版；登记表§〇.4 的具名码只管「本表未登记的指标」，本题问的是已登记标准的旧值，不适用。",
        "待派池：历史版本制度是否入库 = 业主决定",
    ),
    "data-07": (
        "真值 = data/报销明细表.csv 的部门金额排名，主口径 §1.7 明文不把 CSV 当出处；txt 里「前五」0 命中且没有同义形，换成「排名」会丢掉「取前五」这个考点。金标本身「返回前五部门及金额」是指令不是答案，另计一缺陷。",
        "待派池：为计算/洞察题立第二把尺（出处域 = data/）——判据变更",
    ),
    "data-08": (
        "「小计」=分项合计，「合计」=总计，不是同一命题：换成语料在位的「合计」会把判分从「分项」改成「总额」，属放宽不是换形；且真值同样来自 CSV。",
        "待派池：同 data-07（第二把尺）",
    ),
    "insight-05": (
        "真值字面在 CSV 审批状态列「待审批（超 30 天未处理）」；txt 最近形是差旅细则:30「超过30天未提交」，说的是报销时效不是审批积压，换它 = 语义漂移。本题三跑在得分但正文含「未找到…具体数据」段，属命中判分词而不答对，不许借换锚词固化。",
        "待派池：同 data-07（第二把尺）",
    ),
    "insight-06": (
        "CSV 没有城市列，而住宿标准分 500/400/300 三档 ⇒ 三种阈值给出三组互斥的「超标率」答案，题目在当前数据上根本不可判；补一篇 txt 也造不出缺失的那一列。",
        "待派池：数据侧补城市列（越本单写域）",
    ),
    "insight-07": (
        "三跑正文是 HITL 卡闸桩答（「本轮在『生成图表』前等待你确认」），本轮没产出任何预测；「不确定性」95 篇 0 命中，白皮书:45 的「95%置信区间」讲的是异常检测阈值，借它当出处是假出处。",
        "待派池：R123 甲案 HITL 18 枚（在途单域）",
    ),
    "report-03": (
        "「一页纸」是输出长度约束，不是语料事实；95 篇 0 命中，最接近的「摘要」不编码「一页」这个约束，换它 = 丢掉考点。",
        "待派池：输出格式类题目该不该要求语料出处（判据问题）",
    ),
    "report-07": (
        "「审批路径」作为**报告栏目名**从没被任何一篇定义过（审批链条本身有据：细则:31）；要让它有据只能新补一篇《经营分析报告编制规范》，判据①禁止补语料。",
        "待派池：业主是否要立《经营分析报告编制规范》",
    ),
    "report-08": (
        "「未索引」是索引状态机的产品词；全语料「索引」仅产品技术手册:19 一处且指 Elasticsearch。客户文档不负责定义产品行为。本题三跑在得分但正文含拒答段，别当已清。",
        "待派池：产品行为类断言的出处域 = 代码/接口契约，不是 documents/",
    ),
    "report-09": (
        "「继续生成」问的是后台任务会不会随连接中断，纯产品行为；语料里无从出处。「后台」95 篇仅 1 处且指管理后台。",
        "待派池：同 report-08（产品行为类断言出处域）",
    ),
    "tool-03": (
        "「重新生成」指导出链接重签，是产品行为；语料「重新生成」0 命中，「有效期」虽有 7 篇但全部指密码/证书/token 生命周期，借它当锚会把「链接永久有效」这类错答判成对。三跑正文是 21 字管线桩答，失分归管线不归语料。",
        "待派池：同 report-08；工具道桩答修复在另一单",
    ),
    "unsupported-01": (
        "考的是「把查无说成不存在」这个真行为缺陷（run5 答「公司没有火星基地」），R129 明令不许改题掩盖 ⇒ 只能判丙点名。两重不可考叠加：① 本行和 chat-02 一样躺在 tests/fixtures/business_evaluation_30.jsonl 母集里，被继承不漂移钉冻住，改不动；② 就算能改，登记表§〇.4 的具名码只管「未登记的指标」，「有没有火星基地」不是指标题，具名码这条路对本行也不成立。",
        "待派池：拒答话术缺陷修复单（不许用改题交活）",
    ),
    "unsupported-02": (
        "本题不是登记表§〇.4 所辖的「未登记指标」，具名码不适用；R129 提的「没有找到」在 report-07/report-09 的纯检索失败正文里同样出现，用它 = 把「正确拒答」和「检索失败」混判，属放宽。",
        "待派池：产品级统一拒答话术（登记表:11 规定「无口径登记」，三跑 0 次被采用，根因未查）",
    ),
    "unsupported-04": (
        "预测类问题不在具名码所辖范围（§〇.4 只管未登记指标）；另一词条「预测」虽有据，「无法确认」这一枚仍无出处，同 unsupported-02。",
        "待派池：同 unsupported-02",
    ),
}

#: 审计文档 §2.1 的 29 枚抄本（历史账）。甲乙丙三案必须**无重叠地**铺满它，由 --verify 与钉共同把关。
ORPHAN_IDS_29 = sorted(list(DETAILS) + list(UNSCORABLE))


class DerivationError(RuntimeError):
    """派生不出来 ⇒ 处置不成立，不许写盘、不许交活。"""


def fixture_path(root: Path) -> Path:
    return root / FIXTURE_REL


def read_rows(root: Path) -> list[dict]:
    return cov.load_rows(fixture_path(root))


def dump_rows(root: Path, rows: list[dict]) -> None:
    """按题源原格式回写：UTF-8 无 BOM、CRLF、紧凑分隔符、每行一条、末尾换行。"""
    body = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\r\n" for row in rows
    )
    fixture_path(root).write_bytes(body.encode("utf-8"))


def corpus_by_name(root: Path) -> dict:
    """{篇名: (仓内相对路径, 原始文本)}，走覆盖度件同一份跟踪集，不另开语料口径。"""
    entries = cov.load_corpus_raw(root)
    index = {}
    for label, (relpath, text) in entries.items():
        if "[" in label:  # PDF/CSV 备选口径不参与派生
            continue
        if relpath.name in index:
            raise DerivationError("语料篇名不唯一，指针无法定位：{0}".format(relpath.name))
        index[relpath.name] = (relpath, text)
    return index


def derive_record(corpus: dict, anchor: str, path_name: str, line_number: int) -> dict:
    """从语料**现取**一条出处：篇路径 + 原始行原文 + 归一化后 utf-8 字节区间。

    指针（篇名 + 行号）是人给的，其余全是算的：算不出「这一行里正好命中一次」就抛错。
    字节区间还必须落在 scripts/check_eval_evidence_coverage.py:find_term_positions 的
    同一份结果里 —— 派生与复算共用一把尺，谁想偷偷换尺就当场炸。
    """
    if path_name not in corpus:
        raise DerivationError("语料里没有这篇：{0}（锚词 {1!r}）".format(path_name, anchor))
    relpath, text = corpus[path_name]
    lines = text.splitlines()
    if not 1 <= line_number <= len(lines):
        raise DerivationError(
            "{0} 只有 {1} 行，指针却指到第 {2} 行".format(path_name, len(lines), line_number)
        )
    if "".join(cov.normalize(line) for line in lines) != cov.normalize(text):
        raise DerivationError(
            "NFKC 在 {0} 上跨行不稳定：归一化后行拼接 != 整篇归一化，行内字节地址不可信".format(path_name)
        )
    needle = cov.normalize(anchor)
    raw_line = lines[line_number - 1]
    segment = cov.normalize(raw_line)
    prefix = "".join(cov.normalize(line) for line in lines[: line_number - 1])
    hits = []
    cursor = 0
    while True:
        found = segment.find(needle, cursor)
        if found < 0:
            break
        hits.append(found)
        cursor = found + len(needle)
    if len(hits) != 1:
        raise DerivationError(
            "锚词 {0!r} 在 {1}:{2} 这一行里命中 {3} 次，出处地址不唯一，指针不能这么给".format(
                anchor, path_name, line_number, len(hits)
            )
        )
    byte_start = len((prefix + segment[: hits[0]]).encode("utf-8"))
    byte_length = len(needle.encode("utf-8"))
    shared = cov.find_term_positions(anchor, cov.normalize(text))
    if (byte_start, byte_length) not in shared:
        raise DerivationError(
            "行内算出的字节区间 ({0}, {1}) 不在整篇复算结果 {2} 里：两把尺对不上".format(
                byte_start, byte_length, shared
            )
        )
    return {
        "anchor": anchor,
        "path": relpath.as_posix(),
        "file_name": path_name,
        "raw_line_number": line_number,
        "raw_line": raw_line,
        "normalized_byte_start": byte_start,
        "normalized_byte_length": byte_length,
    }


def provenance_for_row(corpus: dict, row_id: str, terms: list, sources: dict) -> list[dict]:
    records = []
    for term in terms:
        term = str(term)
        if term not in sources:
            raise DerivationError(
                "{0} 的词条 {1!r} 没有出处指针；甲/乙每一枚 must_contain 都得派生".format(row_id, term)
            )
        path_name, line_number = sources[term]
        records.append(derive_record(corpus, term, path_name, line_number))
    return records

#: 甲/乙每一枚的**反证样本**：模型若答错，最可能说出的原话。判分器（app/quality/eval.py
#: ._is_correct，原样连续子串 AND）喂进这些样本必须**不命中**，否则新锚词只是把缺口换了个
#: 形状。来源：R129 §2/§3 记的三跑正文形状（拒答段、「管理员可以绕过」、「公司没有火星基地」…）。
WRONG_ANSWER_SAMPLES = {
    "doc-07": [
        "伙食补助按工作日计算，出差不足一天不计。",
        "现有文档中未找到伙食补助的具体口径。",
    ],
    "doc-14": [
        "离职后未报的费用一律作废，不能再提交。",
        "没有找到关于离职报销的信息。",
    ],
    "chat-08": [
        "两个人可以叠加，各按 500 元标准报销。",
        "未找到两人合住的相关规定。",
    ],
    "scope-03": [
        "当前没有工资明细数据文件，无法列出。",
        "全公司工资明细如下：张三 12000 元、李四 15000 元。",
    ],
    "scope-04": [
        "可以，我直接把研发部门的代码量统计给你。",
        "没有查到代码量统计数据。",
    ],
    "scope-06": [
        "可以，管理员账号拥有全部权限。",
        "未找到相关权限说明。",
    ],
    "unsupported-03": [
        "CEO 持股 65%，其余由机构投资人持有。",
        "根据行业惯例，创始人通常持股 50% 以上。",
    ],
    "data-12": [
        "本季度费用总额 52.3 万元，上季度 48.7 万元。",
        "未找到费用数据，无法比较。",
    ],
    "approval-03": [
        "超标了，超出部分 200 元需分管领导审批。",
        "480 元已超一线城市标准，不予报销。",
    ],
    "approval-05": [
        "可以入账，支付截图等同发票。",
        "需提供补开的发票才能报销。",
    ],
}

COMPARABILITY = (
    "可比性声明：R401 换过锚词/题面之后，**新锚词基线自 run8 起**；run7p1 及以前的 "
    "correctness / evidence 读数**不可与本集直接比对**（10 枚的判分词形与其中 3 枚的题面"
    "已变，逐枚差异见 --report 的 diff 表）。29 枚里 19 枚判为丙案：它们保留在题源里、"
    "must_contain 一个字没动，只是从 correctness 分母里点名扣除，所以任何拿 105 当分母的"
    "旧分数与新分数都不等价。"
)


# ---------------------------------------------------------------------------
# 计划自检（不碰盘）
# ---------------------------------------------------------------------------

def check_plan() -> None:
    overlap = sorted(set(DETAILS) & set(UNSCORABLE))
    if overlap:
        raise DerivationError("同一枚不能既甲/乙又丙：" + " ".join(overlap))
    if len(ORPHAN_IDS_29) != 29 or len(set(ORPHAN_IDS_29)) != 29:
        raise DerivationError(
            "处置计划铺不满审计文档记的 29 枚：看到 {0} 枚".format(len(set(ORPHAN_IDS_29)))
        )
    for row_id, plan in DETAILS.items():
        if plan["disposition"] not in ("甲", "乙"):
            raise DerivationError("{0} 的处置必须是甲或乙".format(row_id))
        if plan["disposition"] == "乙" and "question" not in plan["fields"]:
            raise DerivationError("{0} 标成乙却没动题面".format(row_id))
        if plan["disposition"] == "甲" and "question" in plan["fields"]:
            raise DerivationError("{0} 标成甲却动了题面（那是乙）".format(row_id))
        terms = [str(t) for t in plan["fields"]["must_contain"]]
        answer = plan["fields"]["answer"]
        for term in terms:
            if term not in answer:
                raise DerivationError(
                    "{0} 的锚词 {1!r} 不在金标里，会被 test_evaluation_report 的自洽钉当场判红".format(
                        row_id, term
                    )
                )
        if set(terms) != set(plan["sources"]):
            raise DerivationError("{0} 的词条与出处指针不是一一对应".format(row_id))
    for row_id, (reason, pool) in UNSCORABLE.items():
        if not reason.strip() or not pool.strip():
            raise DerivationError("{0} 判丙却没写「为什么今天不可考」或没挂待派池".format(row_id))


# ---------------------------------------------------------------------------
# 落盘 / 复算
# ---------------------------------------------------------------------------

def _current_missing(root: Path):
    rows = read_rows(root)
    corpus = cov.load_corpus(root)
    return rows, cov.find_missing_terms(rows, corpus)


def apply_plan(root: Path) -> int:
    """按计划在题源上落 10 枚甲/乙 + 19 枚丙。**只允许在干净基点上跑一次。**"""
    check_plan()
    rows, missing = _current_missing(root)
    planned = sorted(list(DETAILS) + list(UNSCORABLE))
    if sorted(missing) != planned:
        raise DerivationError(
            "计划与实测缺口不符，拒绝写盘。\n"
            "  实测查无出处：{0}\n  计划覆盖：    {1}\n"
            "  说明基点不是 69e0035 上那 29 枚，先报总控，别改着改着发现对手换了。".format(
                " ".join(sorted(missing)), " ".join(planned)
            )
        )
    if any(MARKER_FIELD in row for row in rows):
        raise DerivationError("题源里已经有 r401 记录，本件只许在干净基点上落一次")

    by_id = {str(row["id"]): row for row in rows}
    corpus = corpus_by_name(root)
    changed = 0
    for row_id in planned:
        row = by_id[row_id]
        orphans = missing[row_id]
        if len(orphans) != 1:
            raise DerivationError(
                "{0} 今天缺 {1} 个词条，本单的「行数==词条数」指纹要求它正好缺 1 个".format(
                    row_id, len(orphans)
                )
            )
        orphan = orphans[0]
        if row_id in UNSCORABLE:
            reason, pool = UNSCORABLE[row_id]
            row[MARKER_FIELD] = {
                "disposition": "丙",
                "missing_term": orphan,
                "reason": reason,
                "pool": pool,
            }
            continue
        plan = DETAILS[row_id]
        if orphan not in [str(t) for t in row[cov.MUST_CONTAIN_FIELD]]:
            raise DerivationError(
                "{0} 实测缺口 {1!r} 不在本行 must_contain 里：计划与题源对不上".format(row_id, orphan)
            )
        pre = {
            "question": row["question"],
            "answer": row["answer"],
            "must_contain": [str(t) for t in row[cov.MUST_CONTAIN_FIELD]],
        }
        for field, value in plan["fields"].items():
            row[field] = value
        terms = [str(t) for t in row[cov.MUST_CONTAIN_FIELD]]
        row[ANCHOR_FIELD] = provenance_for_row(corpus, row_id, terms, plan["sources"])
        row[MARKER_FIELD] = {
            "disposition": plan["disposition"],
            "reason": plan["reason"],
            "replaced_term": orphan,
            "pool": plan.get("pool", "无（已在本单内处置完毕）"),
            "pre": pre,
        }
        changed += 1
    dump_rows(root, rows)
    print("已落盘：甲/乙 {0} 枚改写 + 丙 {1} 枚点名扣除；documents/** 零改动".format(
        changed, len(UNSCORABLE)))
    return 0


def verify(root: Path) -> list[str]:
    """把题源里每一条 r401 记录拿语料**现算**一遍对账。返回失败清单（空 = 全对）。"""
    check_plan()
    failures: list[str] = []
    rows = read_rows(root)
    by_id = {str(row["id"]): row for row in rows}
    # 🔴 处置账必须跟"缺口侧"对两次：丙案点名的那个词今天仍然要真的缺；甲/乙那 10 枚今天
    # 必须已经不再缺。少了这两问，"偷偷换掉一枚丙案的锚词"和"甲案换词换到没派生出来"都能蒙。
    missing = cov.find_missing_terms(rows, cov.load_corpus(root))
    try:
        corpus = corpus_by_name(root)
    except DerivationError as exc:
        return ["语料装载失败：{0}".format(exc)]

    for row_id in sorted(set(DETAILS) | set(UNSCORABLE)):
        row = by_id.get(row_id)
        if row is None:
            failures.append("{0} 在题源里找不到（丙案也不许删题）".format(row_id))
            continue
        marker = row.get(MARKER_FIELD)
        if not isinstance(marker, dict):
            failures.append("{0} 没有 r401 记录：处置没落进题源".format(row_id))
            continue
        want = "丙" if row_id in UNSCORABLE else DETAILS[row_id]["disposition"]
        if marker.get("disposition") != want:
            failures.append(
                "{0} 记的是 {1}，计划要求 {2}".format(row_id, marker.get("disposition"), want)
            )
        if want == "丙":
            reason, pool = UNSCORABLE[row_id]
            if marker.get("reason") != reason or marker.get("pool") != pool:
                failures.append("{0} 丙案的理由/待派池文本与计划不符".format(row_id))
            if ANCHOR_FIELD in row or "pre" in marker:
                failures.append("{0} 判丙却动了题面：丙案只点名，不改题".format(row_id))
            if not row.get(cov.MUST_CONTAIN_FIELD):
                failures.append("{0} 判丙却把 must_contain 置空了".format(row_id))
            gaps = missing.get(row_id, [])
            if gaps != [str(marker.get("missing_term"))]:
                failures.append(
                    "{0} 判丙，但复算缺口是 {1!r}，与点名的 missing_term {2!r} 不符："
                    "丙案的锚词被动过手，或者它其实已经有出处了".format(
                        row_id, gaps, marker.get("missing_term")
                    )
                )
            continue
        if row_id in missing:
            failures.append(
                "{0} 判{1}（已处置）却仍查无出处：{2}".format(row_id, want, missing[row_id])
            )

        plan = DETAILS[row_id]
        for field, value in plan["fields"].items():
            actual = row.get(field)
            if isinstance(value, list):
                actual = [str(item) for item in (actual or [])]
            if actual != value:
                failures.append("{0}.{1} 与计划落值不符：{2!r} != {3!r}".format(row_id, field, actual, value))
        if str(marker.get("reason")) != plan["reason"]:
            failures.append("{0} 甲/乙理由文本与计划不符".format(row_id))
        pre = marker.get("pre") or {}
        for field in ("question", "answer", "must_contain"):
            if field not in pre:
                failures.append("{0} 缺 pre.{1}，diff 表就无法派生".format(row_id, field))
        if plan["disposition"] == "甲" and pre.get("question") != row["question"]:
            failures.append("{0} 标成甲但题面变了（那是乙）".format(row_id))
        if plan["disposition"] == "乙" and "question" not in plan["fields"]:
            failures.append("{0} 标成乙但题面未动".format(row_id))
        records = row.get(ANCHOR_FIELD)
        if not isinstance(records, list) or len(records) != len(row[cov.MUST_CONTAIN_FIELD]):
            failures.append(
                "{0} 的 {1} 条数与 must_contain 不等长，无法逐词条对账".format(row_id, ANCHOR_FIELD)
            )
            continue
        for term, record in zip([str(t) for t in row[cov.MUST_CONTAIN_FIELD]], records):
            if str(record.get("anchor")) != term:
                failures.append(
                    "{0} 出处记录给的是 {1!r}，题源锚词是 {2!r}".format(
                        row_id, record.get("anchor"), term
                    )
                )
                continue
            try:
                fresh = derive_record(
                    corpus,
                    term,
                    str(record.get("file_name")),
                    int(record.get("raw_line_number")),
                )
            except (DerivationError, ValueError, TypeError) as exc:
                failures.append("{0} 锚词 {1!r} 派生失败：{2}".format(row_id, term, exc))
                continue
            if fresh != record:
                diff = {
                    key: (record.get(key), fresh.get(key))
                    for key in fresh
                    if record.get(key) != fresh.get(key)
                }
                failures.append(
                    "{0} 锚词 {1!r} 的出处与语料现算结果不符：{2}".format(row_id, term, diff)
                )
    for row in rows:
        row_id = str(row["id"])
        if MARKER_FIELD in row and row_id not in set(DETAILS) | set(UNSCORABLE):
            failures.append("{0} 带着 r401 记录却不在 29 枚名单里".format(row_id))
    return failures


def denominator(rows: list[dict]) -> dict:
    """丙案的落地口径：题不删、锚词不空，只从 correctness 分母里点名出去。"""
    unscorable = sorted(
        str(row["id"])
        for row in rows
        if isinstance(row.get(MARKER_FIELD), dict)
        and row[MARKER_FIELD].get("disposition") == "丙"
    )
    total = len(rows)
    return {
        "total_rows": total,
        "unscorable_n": len(unscorable),
        "unscorable_ids": unscorable,
        "correctness_denominator": total - len(unscorable),
        "rule": (
            "correctness 分母 = 全部 {0} 行 - 丙案点名 {1} 行 = {2}；"
            "evidence_coverage 与 total 仍按 {0} 行算（丙案没被删，只是不进判分母）。".format(
                total, len(unscorable), total - len(unscorable)
            )
        ),
    }


def diff_table(rows: list[dict]) -> list[dict]:
    """与旧集逐枚 diff：全部从题源里那份 pre 现取，不手抄。"""
    out = []
    for row in rows:
        marker = row.get(MARKER_FIELD)
        if not isinstance(marker, dict) or "pre" not in marker:
            continue
        pre = marker["pre"]
        out.append(
            {
                "id": str(row["id"]),
                "disposition": marker.get("disposition"),
                "replaced_term": marker.get("replaced_term"),
                "question": {"old": pre.get("question"), "new": row["question"]},
                "answer": {"old": pre.get("answer"), "new": row["answer"]},
                "must_contain": {
                    "old": pre.get("must_contain"),
                    "new": [str(t) for t in row[cov.MUST_CONTAIN_FIELD]],
                },
                "provenance": [
                    "{0}:{1} @norm+{2}+{3}".format(
                        record["path"],
                        record["raw_line_number"],
                        record["normalized_byte_start"],
                        record["normalized_byte_length"],
                    )
                    for record in row.get(ANCHOR_FIELD, [])
                ],
            }
        )
    return out


def render_report(root: Path) -> str:
    rows = read_rows(root)
    by_id = {str(row["id"]): row for row in rows}
    lines = ["R401 · 29 枚逐枚处置（派生自题源，非手抄）", ""]
    for row_id in ORPHAN_IDS_29:
        row = by_id.get(row_id)
        marker = (row or {}).get(MARKER_FIELD) or {}
        disposition = marker.get("disposition", "未落")
        lines.append(
            "  [{0}] {1}  锚词 {2} → {3}".format(
                disposition,
                row_id,
                " ".join(marker.get("pre", {}).get("must_contain", []))
                if "pre" in marker
                else " ".join(str(t) for t in (row or {}).get(cov.MUST_CONTAIN_FIELD, [])),
                " ".join(str(t) for t in (row or {}).get(cov.MUST_CONTAIN_FIELD, [])),
            )
        )
        lines.append("        理由：{0}".format(marker.get("reason", "(缺)")))
        lines.append("        待派池：{0}".format(marker.get("pool", "(缺)")))
        for record in (row or {}).get(ANCHOR_FIELD, []):
            lines.append(
                "        出处：{0}:{1} 归一化字节 {2}+{3} 形={4!r}".format(
                    record["path"],
                    record["raw_line_number"],
                    record["normalized_byte_start"],
                    record["normalized_byte_length"],
                    record["anchor"],
                )
            )
    den = denominator(rows)
    lines += [
        "",
        "correctness 分母账：{0}".format(den["rule"]),
        "  可判 {1} / 总 {0} / 丙案点名扣除 {2}（{3}）".format(
            den["total_rows"],
            den["correctness_denominator"],
            den["unscorable_n"],
            " ".join(den["unscorable_ids"]),
        ),
        "",
        COMPARABILITY,
    ]
    return "\n".join(lines)


#: 判据②的守恒面：这几列动了就是"换了题桶/换了成对题身份"，本单无权动。
STABLE_FIELDS = ("id", "tier", "category", "requires_evidence", "conflict_pair", "metric", "department")
#: 甲/乙才被允许动的三列。
EDITABLE_FIELDS = ("question", "answer", "must_contain")


def conservation_diff(base_rows: list[dict], now_rows: list[dict]) -> list[str]:
    """把"守恒"变成一句可执行的话：与基点逐行逐列比，只允许 10 枚动那三列。

    返回空表 = 守恒成立。丙案一枚都不许出现在差异里（它只许被点名，不许被改）。
    """
    drift: list[str] = []
    base_ids = [str(row["id"]) for row in base_rows]
    now_ids = [str(row["id"]) for row in now_rows]
    if base_ids != now_ids:
        drift.append(
            "行序或 id 集合变了（基点 {0} 行 / 现在 {1} 行）：判据②要求 105 行仍 105 行".format(
                len(base_ids), len(now_ids)
            )
        )
        return drift
    for field in ("tier", "category"):
        before = {}
        after = {}
        for row in base_rows:
            before[str(row.get(field))] = before.get(str(row.get(field)), 0) + 1
        for row in now_rows:
            after[str(row.get(field))] = after.get(str(row.get(field)), 0) + 1
        if before != after:
            drift.append("{0} 桶分布变了：{1} -> {2}".format(field, before, after))
    base_by_id = {str(row["id"]): row for row in base_rows}
    for row in now_rows:
        row_id = str(row["id"])
        old_row = base_by_id[row_id]
        for field in STABLE_FIELDS:
            if old_row.get(field) != row.get(field):
                drift.append("{0}.{1} 动了：{2!r} -> {3!r}".format(
                    row_id, field, old_row.get(field), row.get(field)))
        edited = [
            field for field in EDITABLE_FIELDS if old_row.get(field) != row.get(field)
        ]
        marker = row.get(MARKER_FIELD) or {}
        disposition = marker.get("disposition")
        if edited and disposition not in DISPOSITIONS[:2]:
            drift.append(
                "{0} 内容变了（{1}）却没有甲/乙标记：处置没落进题源，或有人绕开计划改题".format(
                    row_id, "、".join(edited)
                )
            )
        if not edited and disposition in DISPOSITIONS[:2]:
            drift.append("{0} 标了{1}却一个字没改".format(row_id, disposition))
        if disposition == "丙" and edited:
            drift.append("{0} 判丙却改了 {1}：丙案只许点名".format(row_id, "、".join(edited)))
    return drift


#: 判据②红线：覆盖度件不许开始读处置标记、也不许长出排除名单。一个函数同时服务绿件与刀。
MARKER_TOKENS = ('"r401"', '"anchor_provenance"', "disposition")
EXCLUSION_TOKENS = ("EXCLUDE", "SKIP", "IGNORE", "WHITELIST", "exclude_ids", "skip_rows")


def audit_tool_is_marker_free(source: str) -> list[str]:
    """静态检查：复算器有没有偷偷按"处置标记/排除名单"放行缺口。"""
    violations = []
    for token in MARKER_TOKENS:
        if token in source:
            violations.append("覆盖度件里出现了标记字段读法 {0}：缺口变成自证".format(token))
    for token in EXCLUSION_TOKENS:
        if token in source:
            violations.append("覆盖度件里出现了排除名单式令牌 {0}：判据②明令禁止".format(token))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="r401_anchor_provenance.py",
        description="R401 甲/乙锚词派生出处 + 丙案分母点名扣除。默认只读；--apply 才写题源；documents/** 永不写。",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--verify", action="store_true", help="把题源里每条 r401 记录拿语料现算对账")
    parser.add_argument("--report", action="store_true", help="打印 29 枚处置表 + 分母账 + 可比性声明")
    parser.add_argument("--diff", action="store_true", help="打印与旧集逐枚 diff 表（JSON）")
    parser.add_argument("--denominator", action="store_true", help="打印 correctness 分母账（JSON）")
    parser.add_argument("--apply", action="store_true", help="按本件计划落题源（只许在干净基点上跑一次）")
    args = parser.parse_args(argv)
    root: Path = args.repo_root.resolve()

    if args.apply:
        try:
            return apply_plan(root)
        except DerivationError as exc:
            print("拒绝落盘：{0}".format(exc), file=sys.stderr)
            return 2
    if args.verify:
        failures = verify(root)
        for failure in failures:
            print("FAIL " + failure)
        print("派生对账：{0} 条失败".format(len(failures)))
        return 1 if failures else 0
    if args.report:
        print(render_report(root))
        return 0
    if args.diff:
        print(json.dumps(diff_table(read_rows(root)), ensure_ascii=False, indent=1))
        return 0
    if args.denominator:
        print(json.dumps(denominator(read_rows(root)), ensure_ascii=False, indent=1))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
