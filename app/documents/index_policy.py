"""R49 索引瘦身：草稿骨架 / 填空模板 / 超小正文不入知识库索引。

上传路径过去只问"能不能解析"，不问"值不值得入索引"：一份全是待填占位符的模板、一份
只有标题的草稿骨架，都会照常走完 embedding 写进向量库，再以低信息块的身份在检索里挤掉
真正的制度文本。另一头，解析结果为空的上传会被删掉文件、连目录行都不留，调用方只拿到
一句 ``skipped`` —— 用户上传的东西就此消失。

本模块把"要不要入索引"变成一条有名字、可回答、可复算的判定，并且只按**内容特征**下结论：
文件名或标题里写着"草稿""模板"不构成排除理由（``documents/客户数据保护政策_草稿.txt``
是一篇正文完整的政策文件，必须照常入索引），只有正文本身说明它承载不了信息时才排除。

四条规则的阈值全部钉在 2026-09-18 对 ``documents/`` 96 篇业务语料实测分布的安全侧：语料
最小正文 173 个实质字符（下限 4）、占位符字符占比最高 4.92%（阈值 35%）、空正文小节比例最高
50.0%（阈值 90%）、标题字符占比最高 16.0%（阈值 60%）。余量由
``tests/test_r49_corpus_calibration.py`` 在每次复跑时按真实目录重新核对，不许靠记忆维护。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.common.logger import logger

# ==================== 索引状态 ====================

INDEX_STATUS_INDEXED = "indexed"
INDEX_STATUS_EXCLUDED = "excluded"
INDEX_STATUS_UNKNOWN = "unknown"

#: ``document_versions.parse_status`` 只有 pending/parsing/ready/failed 四个合法值，而且
#: 那是数据库层的 CHECK 约束（``migrations/0006_document_ownership.sql``），不是应用约定；
#: 它表达的是"解析这一步走到哪了"，装不下"解析成功但按策略不入索引"这个事实。索引状态
#: 因此是一个与之正交的字段，而不是第五个 parse_status 取值。
INDEX_STATUSES = (INDEX_STATUS_INDEXED, INDEX_STATUS_EXCLUDED, INDEX_STATUS_UNKNOWN)

# ==================== 排除原因稳定码 ====================

REASON_NO_TEXT = "no_text_content"
REASON_TOO_SMALL = "below_minimum_size"
REASON_PLACEHOLDER_SKELETON = "placeholder_skeleton"
REASON_OUTLINE_SHELL = "outline_only_shell"
REASON_UNCHANGED_CONTENT = "unchanged_content"
REASON_INDEX_REFUSED = "index_refused"

#: 由本模块的内容判定得出的排除原因。
POLICY_REASONS = (
    REASON_NO_TEXT,
    REASON_TOO_SMALL,
    REASON_PLACEHOLDER_SKELETON,
    REASON_OUTLINE_SHELL,
)
#: 必须留下可查痕迹的全部原因（判据③的口径）：政策排除之外，还包括索引层自己拒绝的两种。
TRACEABLE_REASONS = POLICY_REASONS + (REASON_UNCHANGED_CONTENT, REASON_INDEX_REFUSED)

# ==================== 阈值 ====================

MIN_CONTENT_CHARS_ENV = "DOCUMENT_INDEX_MIN_CHARS"

#: 低于这个实质字符数就没有任何可检索的信息可言。默认值刻意停在 4：现存上传契约里最短的
#: "应当被索引"正文是 4 个字符（tests/test_document_index_publication.py 以 ``body`` 断言
#: status==ok），而语料侧最短正文是 173 个字符，所以运维把 ``DOCUMENT_INDEX_MIN_CHARS``
#: 调到 173 以下都不会误伤现有语料。
MIN_CONTENT_CHARS_DEFAULT = 4

#: 2026-09-18 实测的 ``documents/`` 语料最小正文长度，供调参时对照，不参与判定。
MIN_CONTENT_CHARS_CORPUS_FLOOR = 173

#: 占位符骨架：至少这么多处填空，且占位符吃掉正文实质字符的这么多比例。
#: 分母是"非空白字符"，理由见 placeholder_profile 上方的口径说明。
PLACEHOLDER_MIN_TOKENS = 3
PLACEHOLDER_CHAR_RATIO = 0.35

#: "只有标题的草稿骨架"判据。四个条件必须同时成立才排除：小节数、空正文小节比例、标题吃掉
#: 的正文字符比例、正文总长上限。用比例而不是绝对长度做主判据，是为了免疫"小节正文很短但
#: 确实有内容"这一类合法文档。
OUTLINE_MIN_HEADINGS = 2
OUTLINE_EMPTY_SECTION_CHARS = 8
OUTLINE_EMPTY_SECTION_RATIO = 0.9
OUTLINE_HEADING_CHAR_RATIO = 0.6
#: 一行标题最多这么多实质字符，超了就按正文处理：标题不写成一句话。
OUTLINE_MAX_HEADING_CHARS = 24
#: 骨架的正文总长上限。语料最短正文是 173 个实质字符，60 以下才可能是"只有标题没有正文"，
#: 这条上限让草稿骨架判据对长文档完全失效——宁可漏排除，不可误伤。
OUTLINE_MAX_CONTENT_CHARS = 60

# ==================== 特征提取 ====================

_SUBSTANTIVE_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_NON_WHITESPACE_RE = re.compile(r"\s+")

# 只认"没填的空"，不认括号本身：（）【】里的普通业务措辞不算占位符，HTML/URL 的尖括号也
# 不算（语料里 MYO_API 接口文档一类会大面积命中，必须排除在判据之外）。
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{[^{}\n]{0,60}\}\}"),
    re.compile(r"\$\{[^{}\n]{0,60}\}"),
    re.compile(r"_{3,}|[＿]{2,}"),
    re.compile(
        r"【[^】\n]{0,30}(?:请填写|请输入|待补充|待定|占位|此处填写|X{2,}|x{2,}|TBD|TODO)"
        r"[^】\n]{0,30}】"
    ),
    re.compile(
        r"\[[^\]\n]{0,30}(?:请填写|请输入|待补充|待定|占位|此处填写|你的名字|姓名|日期"
        r"|部门|金额|X{2,}|x{2,}|TBD|TODO)[^\]\n]{0,30}\]"
    ),
    re.compile(r"\b(?:TBD|TODO|FIXME)\b"),
    re.compile(r"[Xx]{3,}"),
)

# 只有 markdown ATX 算"结构即标题"。其余形状必须同时满足：不含冒号与句末标点、实质字符不
# 超上限、整行无空白。少了这三道闸，"1. 营业收入：不含税已确认收入" 和 "1. 差旅费 2200 元"
# 这类登记表/明细表的数据行就会被当成"有题无文的小节标题"，把《指标口径登记表》《报销明细
# 表》整篇误判成草稿骨架 —— 而它们正是本轮另有执行体要往 documents/ 里加的两篇评测语料。
_ATX_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_TITLE_HEADING_PATTERNS = (
    re.compile(r"^\*\*[^*\n]{1,40}\*\*\s*$"),
    re.compile(r"^[0-9]{1,2}(?:\.[0-9]{1,2})*[、.．)]\s*\S{1,40}$"),
    re.compile(r"^[一二三四五六七八九十百]+[、.．)]\s*\S{1,40}$"),
    re.compile(r"^第[0-9一二三四五六七八九十百]+[章节条款部分篇]\s*\S{0,40}$"),
)
_TITLE_PUNCTUATION_RE = re.compile(r"[：:。；;]")


def substantive_chars(text: str) -> int:
    """正文里真正带信息的字符数：汉字、字母、数字，标点与空白不计。"""
    return len(_SUBSTANTIVE_RE.findall(text or ""))


#: 两种度量各回答一个问题。"实质字符"判断一份正文有没有话说（只数汉字/字母/数字）；
#: "非空白字符"判断一份正文里有多少根本不是内容、只是留给人的空（下划线、方括号、花括号
#: 一并算进来）。拿前者当占位符比例的分母会朝错误方向算偏：一张 ``__________`` 的空白申请
#: 单，下划线一个实质字符都不贡献，反而显得"并不全是占位符"。
def non_whitespace_chars(text: str) -> int:
    """去掉所有空白之后的字符数，占位符比例的分母。"""
    return len(_NON_WHITESPACE_RE.sub("", text or ""))


def _is_heading_line(line: str) -> bool:
    """这一行是小节标题，还是小节正文里的一行。"""
    if _ATX_HEADING_RE.match(line):
        return True
    if _TITLE_PUNCTUATION_RE.search(line):
        return False
    if substantive_chars(line) > OUTLINE_MAX_HEADING_CHARS:
        return False
    return any(pattern.match(line) for pattern in _TITLE_HEADING_PATTERNS)


def placeholder_profile(text: str) -> dict[str, Any]:
    """数出填空处的个数，以及它们吃掉的非空白字符与占比。"""
    body = text or ""
    total = non_whitespace_chars(body)
    tokens = 0
    chars = 0
    for pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(body):
            tokens += 1
            chars += len(match.group(0))
    return {
        "placeholder_tokens": tokens,
        "placeholder_chars": chars,
        "non_whitespace_chars": total,
        "placeholder_ratio": round(chars / total, 4) if total else 0.0,
    }


def outline_profile(text: str) -> dict[str, Any]:
    """按标题切小节，数出"有题无文"的小节比例与标题占正文字符的比例。"""
    lines = (text or "").splitlines()
    heading_at = [
        index
        for index, line in enumerate(lines)
        if line.strip() and _is_heading_line(line.strip())
    ]
    total = substantive_chars(text)
    heading_chars = sum(substantive_chars(lines[index].strip()) for index in heading_at)
    empty_sections = 0
    for position, index in enumerate(heading_at):
        stop = heading_at[position + 1] if position + 1 < len(heading_at) else len(lines)
        body_chars = substantive_chars("".join(lines[index + 1:stop]))
        if body_chars < OUTLINE_EMPTY_SECTION_CHARS:
            empty_sections += 1
    headings = len(heading_at)
    return {
        "headings": headings,
        "empty_sections": empty_sections,
        "empty_section_ratio": round(empty_sections / headings, 4) if headings else 0.0,
        "heading_ratio": round(heading_chars / total, 4) if total else 0.0,
    }


def min_content_chars() -> int:
    """实质字符下限，运维可用 ``DOCUMENT_INDEX_MIN_CHARS`` 上调；0 表示关掉这条规则。"""
    raw = os.getenv(MIN_CONTENT_CHARS_ENV, "")
    if not str(raw).strip():
        return MIN_CONTENT_CHARS_DEFAULT
    try:
        value = int(str(raw).strip())
    except ValueError:
        logger.warning(
            "[Docs] {}={!r} is not an integer; using the default {} chars".format(
                MIN_CONTENT_CHARS_ENV, raw, MIN_CONTENT_CHARS_DEFAULT
            )
        )
        return MIN_CONTENT_CHARS_DEFAULT
    return value if value >= 0 else MIN_CONTENT_CHARS_DEFAULT


# ==================== 判定 ====================


@dataclass(frozen=True)
class IndexEligibility:
    """一份正文的索引资格：能不能入索引；不能的话是哪个稳定码、凭什么。"""

    eligible: bool
    reason: str = ""
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def excluded(self) -> bool:
        return not self.eligible


def index_notice(reason: str, metrics: dict[str, Any] | None = None) -> str:
    """把一个稳定码展开成给人看的一句话（同一份文字也会进目录与日志）。"""
    measured = metrics or {}
    if reason == REASON_NO_TEXT:
        return "正文去掉标点与空白后没有任何可用字符，无法切块检索；文件与目录记录均已保留。"
    if reason == REASON_TOO_SMALL:
        return (
            "正文实质字符仅 {} 个，低于索引下限 {}；文件与目录记录均已保留。".format(
                measured.get("content_chars", 0),
                measured.get("min_content_chars", MIN_CONTENT_CHARS_DEFAULT),
            )
        )
    if reason == REASON_PLACEHOLDER_SKELETON:
        return (
            "正文有 {} 处未填写的占位符，占非空白字符的 {}，判定为模板骨架，不入索引；"
            "文件与目录记录均已保留。".format(
                measured.get("placeholder_tokens", 0),
                measured.get("placeholder_ratio", 0),
            )
        )
    if reason == REASON_OUTLINE_SHELL:
        return (
            "正文 {} 个小节里 {} 个没有内容，判定为草稿骨架，不入索引；"
            "文件与目录记录均已保留。".format(
                measured.get("headings", 0),
                measured.get("empty_sections", 0),
            )
        )
    if reason == REASON_UNCHANGED_CONTENT:
        return "同名文档内容未发生变化，索引沿用已存在的版本，本次上传不再复制一份向量。"
    if reason == REASON_INDEX_REFUSED:
        return "索引层拒绝了这份正文，文件与目录记录均已保留，可在文档列表中看到未索引状态。"
    return "该文档未进入知识库索引，文件与目录记录均已保留。"


def evaluate_index_eligibility(
    content: str,
    *,
    min_chars: int | None = None,
    size_bytes: int | None = None,
) -> IndexEligibility:
    """按内容特征判定一份正文是否值得入索引。

    只看正文，不看文件名：文件名对"草稿""模板"的表达与正文是否真的有信息没有关系，拿它
    做排除判据就会误伤 ``客户数据保护政策_草稿.txt`` 这一类正文完整的制度文件。
    """
    text = content or ""
    floor = min_content_chars() if min_chars is None else int(min_chars)
    content_chars = substantive_chars(text)
    metrics: dict[str, Any] = {
        "raw_chars": len(text),
        "content_chars": content_chars,
        "non_whitespace_chars": non_whitespace_chars(text),
        "min_content_chars": floor,
    }
    if size_bytes is not None:
        metrics["size_bytes"] = int(size_bytes)

    if content_chars == 0:
        return IndexEligibility(
            False, REASON_NO_TEXT, index_notice(REASON_NO_TEXT, metrics), metrics
        )

    if floor > 0 and content_chars < floor:
        metrics.update(placeholder_profile(text))
        return IndexEligibility(
            False, REASON_TOO_SMALL, index_notice(REASON_TOO_SMALL, metrics), metrics
        )

    placeholders = placeholder_profile(text)
    outline = outline_profile(text)
    metrics.update(placeholders)
    metrics.update(outline)

    if (
        placeholders["placeholder_tokens"] >= PLACEHOLDER_MIN_TOKENS
        and placeholders["placeholder_ratio"] >= PLACEHOLDER_CHAR_RATIO
    ):
        return IndexEligibility(
            False,
            REASON_PLACEHOLDER_SKELETON,
            index_notice(REASON_PLACEHOLDER_SKELETON, metrics),
            metrics,
        )

    if (
        outline["headings"] >= OUTLINE_MIN_HEADINGS
        and outline["empty_section_ratio"] >= OUTLINE_EMPTY_SECTION_RATIO
        and outline["heading_ratio"] >= OUTLINE_HEADING_CHAR_RATIO
        and content_chars < OUTLINE_MAX_CONTENT_CHARS
    ):
        return IndexEligibility(
            False,
            REASON_OUTLINE_SHELL,
            index_notice(REASON_OUTLINE_SHELL, metrics),
            metrics,
        )

    return IndexEligibility(True, "", "", metrics)


# ==================== 索引层的拒绝话术归类 ====================

_REFUSAL_MARKERS = (
    ("未变化", REASON_UNCHANGED_CONTENT),
    ("内容为空", REASON_NO_TEXT),
)


def classify_index_refusal(message: str) -> str:
    """把 ``retriever.add_document`` 返回的那句人话归成稳定码。

    向量库的返回值只有一句中文，本函数不修改它、也不依赖它逐字不变：认得出的落回对应稳定
    码，认不出一律落 ``index_refused``，而 ``index_refused`` 走的是"保留文件与目录行"的分
    支——将来新出现的拒绝理由不可能再把用户上传静默删掉。
    """
    text = str(message or "")
    for marker, reason in _REFUSAL_MARKERS:
        if marker in text:
            return reason
    return REASON_INDEX_REFUSED


def droppable_upload(reason: str) -> bool:
    """这次未入索引是否可以不留物理文件：只有"内容重复"这一种。

    重复上传的正文已经躺在索引里，再留一份同哈希的物理副本只会多出没人能删的文件；除此
    之外的任何未入索引都必须保留文件与目录行。
    """
    return reason == REASON_UNCHANGED_CONTENT
