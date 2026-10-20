# -*- coding: utf-8 -*-
r"""R645 · 契约历史的「具名差异账」：默认逐字节不许动，账外一字节都不许动，账上逐字登记。

病（10-04 本席现取）：`497ac38`（并树 R630）把 `docs/api/contract-v1.md` 里 blockers 表那一行的两枚手抄
行号换成了运行时符号锚点。那一格改得对 —— 对外契约里烤死过期坐标，正是本仓这两天在治的病 —— 但它同时让
「当前契约必须以 `git show a7ac040` 那一份为逐字节前缀」这一类常驻钉从今天起不可能绿。同一把尺全仓一共八枚
（契约文末那一节自己数过），今天六枚红；本单只治
`tests/test_r354_delete_audit_shares_the_owner_reader.py` 那两枚，其余六枚在写域外，名单与逐枚读数记在
`docs/testing/r645-contract-difference-ledger-2026-10-04.md`，交回总控另立单。

治法不是撤销 R630，也不是把尺的基点前移（那等于把尺子折短来灭红），而是把那条不变式改写成**具名差异账**：

  ① 默认仍然逐字节不许动：账外每一个字节都必须与基点相同，新内容只许长在文末。
  ② 账只收一种形状：旧文含手抄坐标（点 py 冒号紧跟数字）⇒ 新文一枚都不留，且含 `文件::符号` 派生锚。
     增句／删句／改数字／改语义／改标题这些形状不收；收了也要逐枚点名它为什么不收。
  ③ 位置一律派生：起点／终点／行号全由 git 对象与盘上现读拼接出来（内容层的字符位，不是传输层的字节位）。`Difference` 的字段面里根本没有
     位置那一格，那种六位数的字节偏移抄都没地方抄，下一笔正当追加也不会把它撞歪。
  ④ 今天账上恰好一枚：多一枚少一枚都红（`EXPECTED_DIFFERENCES_TODAY`）。
  ⑤ 基点冻在 `a7ac040`：谁前移它，登记在册的旧文就在那一版里找不到 —— 这是结构性挡；另按字面量再挡一枚。

六把反证刀（每把先跑正控；全部只拿内存副本与 `tmp_path` 影子端判，盘上契约一字节不动）：
刀① 账外手改历史区一个标点 ⇒ 两枚钉都红，红句点名派生出来的位置（字符位与行号）；
刀② 往账里塞一枚「把一句结论换掉」的改写 ⇒ 必红，并说清这形状为什么不收；加进真账则枚数一起报；
刀③ 把 `FROZEN_BASE` 换成较新的版本（本刀直接用 HEAD，不抄 sha）⇒ 两枚钉红、基点字面量钉也红；
刀④ 新文里留一枚手抄坐标（半截派生）⇒ 必红，理由就是那一格仍然会过期。
刀A 追加段里来一次没有出处的原地改口 ⇒ 必红，红句说「就地消失」；登记了却拿不出单号与凭据纸 ⇒ 也必红。
刀B 把一次原地改口伪装成纯追加（补一行空行撑长度）⇒ 必红；把「旧文 ＋ 一行空行」登记成改口 ⇒ 形状尺当场拒。

🔴 两枚钉同判据：`test_the_current_contract_is_the_base_plus_an_appendage` 与
`test_the_appendage_deletes_nothing_and_adds_exactly_one_section` 都只走本文件这一把尺，谁也不许留着自家的
前缀等式（那等于给它开后门）—— 这一条沿 AST 现查，见 `test_the_two_r354_nails_read_this_same_book`。

R664（10-05）给这本账扩了第二类：`CONTRACT_REWORDS` 那一本**改口账**。上面的差异账管的是「冻结基点到现盘」
那一段历史里的格子；契约文末长出来的那一截里也有必须**原地**改口的行 —— 见
`tests/test_r526_slot_caliber_closure.py::test_the_contract_row_and_the_module_are_the_same_words`：它把 §4b
那一格与码面那一枚字段逐字对判，只许原地换、不许另起新节回避。R657 依令原地替换 §4b 的 `qa.first_text_p95_ms` 那一行
之后，「现盘是任一在册版本的纯追加」就此不再成立，刀③ 交回的 escape 集当场为空：两枚在册不变式互斥。
裁的是账的形状，不是任何一枚码：改口账只收「派生锚行的原地改口」，三条硬条件 ——
① 逐字点名那一格（旧文新文各一整行，行首格子名两侧必须相等，前后缀逐字等值，一半不许包住另一半）；
② 账面有出处（点名单号 ＋ 凭据纸，纸里点得出这一单与这一格，另由 `derive_reword_pair()` 拿两半回 git 现校）；
③ 账外一字节仍当场红 —— 尺先把现盘按两本账退回原形，再拿「基点 ＋ 差异账」比历史区的前缀、拿**最近那一版
   在册契约的同一原形**比追加段；退回原形比那一版还长了别的东西，就是「就地消失」，补多少行空行都蒙不过。
今天改口账上恰好一枚（R657），`EXPECTED_REWORDS_TODAY` 与那两枚字面量同为尺的一部分。
凭据纸：`docs/testing/r664-inplace-derived-anchor-differences-2026-10-05.md`。
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, get_type_hints

import pytest

REPO = Path(__file__).resolve().parents[1]
CONTRACT_REL = "docs/api/contract-v1.md"
R354_REL = "tests/test_r354_delete_audit_shares_the_owner_reader.py"

#: 读契约的唯一把手：反证刀把它指向 tmp_path 下的影子副本，盘上那一枚全程只读。
CONTRACT_PATH = REPO / "docs" / "api" / "contract-v1.md"

#: 🔴 尺的基点（刀③ 的靶）：只许是 `a7ac040`。前移它 = 把尺子折短来灭红。
FROZEN_BASE = "a7ac040"

#: 今天账上应当有的枚数：多一枚少一枚都红。
EXPECTED_DIFFERENCES_TODAY = 1

#: 今天改口账上应当有的枚数：多一枚少一枚都红（与上面那枚同为尺的字面量，见 `_literal_pin_problems`）。
EXPECTED_REWORDS_TODAY = 1

#: r354 那两枚钉、它们共用的那把尺、以及那把尺必须落到的本文件入口。
R354_NAILS = (
    "test_the_current_contract_is_the_base_plus_an_appendage",
    "test_the_appendage_deletes_nothing_and_adds_exactly_one_section",
)
R354_SHARED_RULER = "_contract_history_account"
SHARED_ENTRY_POINT = "assert_history_matches_ledger"

SELF = sys.modules[__name__]

#: 手抄坐标：点 py 之后冒号紧跟数字。旧文里必须至少一枚，否则这一格不是「过期坐标」。
HAND_COPY_COORD = re.compile(r"[\w./+-]*\.py:\d+")
#: 裸行号：反引号紧跟冒号紧跟数字（旧那一格里没带文件名的那一枚）。新文里一枚不许留。
BARE_LINE_NUMBER = re.compile(r"`:\d")
#: 派生锚：`文件::符号`。新文里必须至少一枚，否则这一格只是改写，不是派生化。
DERIVED_ANCHOR = re.compile(r"[\w./+-]+\.py::\w[\w.]*")
#: 那一格的名字：表格行第一枚反引号里那一串。原地改口不许顺手把被点名的格子换成另一格。
ROW_NODE = re.compile(r"^\|\s*`([^`]+)`")
#: 单号那一形：R 紧跟数字。改口的出处要点得出是谁立的单。
TICKET_SHAPE = re.compile(r"^R\d+$")


class Difference(NamedTuple):
    """账上一枚差异：立案号、逐字旧文、逐字新文、为什么收它。

    🔴 字段面里没有「起点／终点」那种格子：位置一律由 `audit_history()` 现派生。
    """

    ticket: str
    old: str
    new: str
    reason: str


class Reword(NamedTuple):
    """改口账上一枚原地改口：立案号、逐字旧行、逐字新行、为什么收它、出处落在哪张凭据纸。

    🔴 字段面里同样没有位置那一格：字符位与行号一律由 `apply_rewords()` 现派生。
    """

    ticket: str
    old: str
    new: str
    reason: str
    evidence: str
class Record(NamedTuple):
    """派生出来的那一格：登记的逐文字对上了基点与现盘的哪一段。"""

    ticket: str
    base_start: int
    base_end: int
    current_start: int
    current_end: int
    base_line: int
    current_line: int


class RewordMark(NamedTuple):
    """派生出来的那一格改口：登记的逐字两半对上了现盘与历史态的哪一段。"""

    ticket: str
    current_start: int
    current_end: int
    historical_start: int
    historical_end: int
    current_line: int
    head_length: int
    tail_length: int
class Account(NamedTuple):
    """一次对账的全部现场：两侧原文、拼接出来的「历史应当长这样」、逐枚差异、逐条红。"""

    base_text: str
    current_text: str
    expected_prefix: str
    records: tuple
    violations: tuple
    historical_text: str = ""
    reword_marks: tuple = ()

    @property
    def appendage(self) -> str:
        """文末追加那一段：拼接后的历史之后、现盘剩下的全部。"""
        return self.current_text[len(self.expected_prefix):]


#: R630 那一格：blockers 表里 first_token_not_a_stage_sample 那一行，整行逐字（含行尾 LF）。
R630_FIRST_TOKEN_ROW = Difference(
    ticket="R630",
    old='| `first_token_not_a_stage_sample` | `first_token_at` is recorded (`spans.py:174`) and persisted (`store.py:259`) but `stage_timing.samples_from_span_payload` (`:330-345`) never reads it ⇒ 首屏 is computable from a persisted trace, not from the ledger |\n',
    new='| `first_token_not_a_stage_sample` | first_token_at is stamped by ``app/trace/spans.py::ExecutionSpan.mark_first_token`` and emitted on the finished model span by ``app/trace/spans.py::ExecutionSpan.finish``; ``app/trace/projections.py::project_span`` folds it into the model_calls row, whose columns are the roster in ``app/trace/schema.py::TRACE_TABLE_COLUMNS``, and ``app/storage/persistence.py::PostgresPersistenceAdapter.upsert`` writes it, taking the column set from ``app/storage/persistence.py::_TABLES`` -- ``app/trace/store.py`` pushes sealed projections and names no column; ``app/common/stage_timing.py`` folds finished spans into ledger samples yet its ``samples_from_span_payload`` builds a ``StageSample`` with no field for it, so 首屏 is computable per trace and not from the in-process ledger. |\n',
    reason="旧句把手抄行号烤进对外契约，其中一枚落点还写错了；新句改问运行时符号，账外一字节没动",
)

CONTRACT_DIFFERENCES: tuple = (R630_FIRST_TOKEN_ROW,)


#: R657 那一格：§4b 名册里 `qa.first_text_p95_ms` 那一行，整行逐字（含行尾 LF）。
#: 两半都由 `derive_reword_pair()` 拿登记回 git 现校：旧行取自改口落地那一版的上一版，新行取自那一版本身。
R657_FIRST_TEXT_ROW = Reword(
    ticket="R657",
    old="| `qa.first_text_p95_ms` | 采集器帧账 scripts/eval_transport_ask_v2.py 的 `events[]` 逐事件 `elapsed_ms`（基准 `stream_clock.request_sent_at`）；事件面读法件 scripts/eval_frame_caliber_readout.py | docs/testing/sidecar-{window}-frames.jsonl · `events[]` 里第一枚 `event == 'text'` 的 `elapsed_ms`；🔴 不是 `first_visible_ms`——那一格量的是第一个**可见**事件，上一窗帧账多数行的 `first_visible_event` 是 `step` 而不是 `text`，两格不同量，拿它顶首屏就是第二套口径 | n(该生效档里真出现 `text` 事件的流式请求数) >= MIN_SLO_SAMPLES，且分母就是这一格自己那枚分布的样本数；caliber=local-full：数值必本机（R453 裁定（b）），云端形状窗交回这一格即拒；分位只按 app/common/performance.py::PerformanceStats (nearest rank: the value at ceil(n * q), 1-based) 取；仓内任何第二套排名都不算这格的凭据；原始读数件必须落在 docs/perf/raw/ 或 docs/testing/ 之内，读数本里同时记下该件的 sha256；target 只由乙半按这三件写；p50_ms / p95_ms 永远由计算得出，手打的数不进 value 侧；上面缺一件 = 本格仍是「待真机样本」：未实测的秒数 = 不可承诺 | 未在册（不许拿相近枚名走私） | 是 | ①R453 名册要先新增一枚首屏格：`first_visible_ms` 是别的东西，拿它顶这格＝走私；②产品侧 wire 事件仍不落盘（blocker `wire_first_text_not_recorded`），本格的凭据是采集器那一侧的外部观察，读数本必须这么署名；③还没有一枚按 `text` 挑第一枚的在册读数件 |\n",
    new="| `qa.first_text_p95_ms` | 采集器帧账 scripts/eval_transport_ask_v2.py 的 `events[]` 逐事件 `elapsed_ms`（基准 `stream_clock.request_sent_at`）；事件面读法件 scripts/eval_frame_caliber_readout.py | docs/testing/sidecar-{window}-frames.jsonl · `events[]` 里第一枚 `event == 'text'` 的 `elapsed_ms`；🔴 不是 `first_visible_ms`——那一格量的是第一个**可见**事件，上一窗帧账多数行的 `first_visible_event` 是 `step` 而不是 `text`，两格不同量，拿它顶首屏就是第二套口径 | n(该生效档里真出现 `text` 事件的流式请求数) >= MIN_SLO_SAMPLES，且分母就是这一格自己那枚分布的样本数；caliber=local-full：数值必本机（R453 裁定（b）），云端形状窗交回这一格即拒；分位只按 app/common/performance.py::PerformanceStats (nearest rank: the value at ceil(n * q), 1-based) 取；仓内任何第二套排名都不算这格的凭据；原始读数件必须落在 docs/perf/raw/ 或 docs/testing/ 之内，读数本里同时记下该件的 sha256；target 只由乙半按这三件写；p50_ms / p95_ms 永远由计算得出，手打的数不进 value 侧；上面缺一件 = 本格仍是「待真机样本」：未实测的秒数 = 不可承诺 | 未在册（不许拿相近枚名走私） | 是 | ①R453 名册要先新增一枚首屏格：`first_visible_ms` 是别的东西，拿它顶这格＝走私；②wire 首屏今天已落账也可读回（`app/api/v1/chat.py::_record_wire_first_text` 记账＋`app/api/v1/observability.py::wire_first_text_readout` 读回，R649 已并树），blocker `wire_first_text_not_recorded` 已从 §6 那本名册摘掉 ⇒ 本格不再欠「量得到」这一件；③仍欠两件才谈落数：还没有一枚按 `text` 挑第一枚的在册读数件，且样本量没到 `MIN_SLO_SAMPLES` |\n",
    reason="契约 §4b 那一格与 app/api/v1/observability.py::SLO_METRIC_CALIBER 里同一枚 prerequisite 由逐字对判钉在一起，只许原地换；那一行本来就是派生锚行，不是手抄坐标，所以它属于改口账而不是差异账",
    evidence="docs/testing/r657-caliber-prerequisite-2026-10-05.md",
)

CONTRACT_REWORDS: tuple = (R657_FIRST_TEXT_ROW,)


# ------------------------------------------------------------------ 现取的两侧


def normalize_eol(data: bytes) -> bytes:
    """按签出语义归一（git blob 存 LF、工作树是 CRLF）：等式在内容层成立，不在传输层成立。"""
    return data.replace(b"\r\n", b"\n")


def git_show(revision: str, relative: str = CONTRACT_REL) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), "show", "%s:%s" % (revision, relative)],
        capture_output=True,
        check=True,
    ).stdout


def base_contract_text(revision: str = None) -> str:
    """基点那一版契约：读 git 对象而不是工作树副本，否则各 worktree 停在自己的基点上会稳定假绿。"""
    return normalize_eol(git_show(FROZEN_BASE if revision is None else revision)).decode("utf-8")


def current_contract_bytes() -> bytes:
    return Path(CONTRACT_PATH).read_bytes()


def current_contract_text() -> str:
    return normalize_eol(current_contract_bytes()).decode("utf-8")  # 严格解码：坏一个字节就红


def head_contract_text() -> str:
    return normalize_eol(git_show("HEAD")).decode("utf-8")


# ------------------------------------------------------------------ 尺本体


def shape_violations(entry: Difference) -> list:
    """这一格是不是「手抄坐标 → 派生锚」那一形状；交回逐条理由，空表才叫合格。"""
    problems: list[str] = []
    if not HAND_COPY_COORD.search(entry.old):
        problems.append(
            "旧文里一枚手抄坐标都没有：账只收「把过期的手抄坐标换成运行时派生锚」这一种形状，"
            "增句／删句／改数字／改语义／改标题一律不收"
        )
    left = sorted(set(HAND_COPY_COORD.findall(entry.new)))
    if left:
        problems.append("新文里还留着 %d 枚手抄坐标（半截派生，那一格明年照样过期）：%s" % (len(left), left))
    bare = BARE_LINE_NUMBER.findall(entry.new)
    if bare:
        problems.append("新文里还留着 %d 枚裸行号（冒号紧跟数字那一形）：那也是手抄坐标，只是没带文件名" % len(bare))
    if not DERIVED_ANCHOR.search(entry.new):
        problems.append("新文里没有一枚 `文件::符号` 派生锚：这一格就只是改写，不是派生化")
    return problems


def _occurrences(haystack: str, needle: str) -> list:
    """needle 在 haystack 里每一次出现的起点（不重叠扫）：位置从这里派生，不抄进钉。"""
    hits: list[int] = []
    start = haystack.find(needle)
    while start != -1:
        hits.append(start)
        start = haystack.find(needle, start + max(1, len(needle)))
    return hits


def _first_difference(left: str, right: str) -> int:
    """两侧文本第一次不同的位置（分块比，不逐字符走一遍五十万字）。"""
    limit = min(len(left), len(right))
    step = 4096
    for start in range(0, limit, step):
        chunk_left, chunk_right = left[start:start + step], right[start:start + step]
        if chunk_left != chunk_right:
            for offset in range(len(chunk_left)):
                if chunk_left[offset] != chunk_right[offset]:
                    return start + offset
    return limit


def _window(text: str, index: int, span: int = 60) -> str:
    return text[max(0, index - 20):index + span]


def _row_node(row: str) -> str:
    """那一行的格子名：表格行行首第一枚反引号里那一串。"""
    match = ROW_NODE.match(row)
    return match.group(1) if match else ""


def _common_head(left: str, right: str) -> int:
    """两侧逐字相等的前缀长度（分块比，不逐字符走一遍半兆）。"""
    limit = min(len(left), len(right))
    step = 4096
    start = 0
    while start + step <= limit and left[start:start + step] == right[start:start + step]:
        start += step
    while start < limit and left[start] == right[start]:
        start += 1
    return start


def _common_tail(left: str, right: str, head: int) -> int:
    """前缀之外两侧逐字相等的后缀长度（两半不许重叠：中间那一格才是真改了口）。"""
    limit = min(len(left), len(right)) - head
    count = 0
    while count < limit and left[len(left) - 1 - count] == right[len(right) - 1 - count]:
        count += 1
    return count


def reword_shape_violations(entry: Reword) -> list:
    """这一格是不是「派生锚行的原地改口」那一形状；交回逐条理由，空表才叫合格。"""
    problems: list[str] = []
    if not entry.old or not entry.new:
        problems.append("旧文或新文是空串：改口账只收「整行原地换掉」，不收把话删掉或凭空造出来那一形")
        return problems
    for side, row in (("旧文", entry.old), ("新文", entry.new)):
        if row.count("\n") != 1 or not row.endswith("\n") or not row.startswith("| "):
            problems.append("%s不是表格里的一整行（要求恰一枚行尾、以竖线起头）：原地改口只许逐字点名那一行" % side)
    if entry.old == entry.new:
        problems.append("旧文与新文逐字相等：这一格根本没有改口，登记它只是给账添一格空位")
    if entry.new.startswith(entry.old) or entry.old.startswith(entry.new):
        problems.append(
            "一半整串是另一半的开头（补一行空行那一形）：那是文末追加伪装成改口 —— 原地改口两半都不许包住对方"
        )
    if _row_node(entry.old) != _row_node(entry.new):
        problems.append(
            "两半点名的是不同的格子（旧 %r 新 %r）：改口只许改那一格里说的话，不许换被点名的那一格"
            % (_row_node(entry.old), _row_node(entry.new))
        )
    if not DERIVED_ANCHOR.search(entry.old):
        problems.append(
            "旧文里没有一枚 `文件::符号` 派生锚：改口账只收派生锚行；手抄坐标那一格属于差异账（手抄坐标 → 派生锚）"
        )
    if not DERIVED_ANCHOR.search(entry.new):
        problems.append("新文里没有一枚 `文件::符号` 派生锚：这一格只是把话说长说短，不是把口径改回运行时")
    left = sorted(set(HAND_COPY_COORD.findall(entry.new)))
    if left:
        problems.append("新文里还留着 %d 枚手抄坐标（半截派生，那一格明年照样过期）：%s" % (len(left), left))
    bare = BARE_LINE_NUMBER.findall(entry.new)
    if bare:
        problems.append("新文里还留着 %d 枚裸行号（冒号紧跟数字那一形）：那也是手抄坐标，只是没带文件名" % len(bare))
    return problems


def reword_provenance_problems(entry: Reword) -> list:
    """判据⑥②：改口必须在账面有出处 —— 点名单号 ＋ 凭据纸，纸里点得出这一单与这一格。"""
    problems: list[str] = []
    if not TICKET_SHAPE.match(entry.ticket):
        problems.append("立案号 %r 不是单号那一形（要 R 紧跟数字）：原地改口必须在账面点名单号" % entry.ticket)
    if not entry.evidence.startswith("docs/testing/") or not entry.evidence.endswith(".md"):
        problems.append(
            "凭据纸 %r 不在 docs/testing/ 下的 .md 里：改口的出处只能落在取证纸上，不许落在契约本体或口头里" % entry.evidence
        )
        return problems
    paper = REPO.joinpath(*entry.evidence.split("/"))
    if not paper.is_file():
        problems.append("凭据纸不存在：%s" % entry.evidence)
        return problems
    text = normalize_eol(paper.read_bytes()).decode("utf-8")
    if entry.ticket not in text:
        problems.append("凭据纸 %s 里没有立案号 %s：出处要点得出是谁立的单" % (entry.evidence, entry.ticket))
    node = _row_node(entry.old)
    if not node:
        problems.append("旧行行首点不出格子名：凭据纸没法与它对上号")
    elif node not in text:
        problems.append("凭据纸 %s 里没有那一格的格子名 %s：出处要点得出改的是哪一格" % (entry.evidence, node))
    return problems


def unwind_rewords(text: str, rewords: tuple) -> str:
    """把改口账倒着套在任何一份契约文本上（用在册那一版时就用它）：逐枚把登记的新行换回旧行。

    只在那一行「新文恰一枚、旧文零枚」时才换 —— 换不动就原样交回，让尺那一层去报登记与现场不符。
    """
    unwound = text
    for entry in rewords:
        if entry.new and unwound.count(entry.new) == 1 and unwound.count(entry.old) == 0:
            unwound = unwound.replace(entry.new, entry.old, 1)
    return unwound


def committee_revision() -> str:
    """最近那一枚动过契约的提交：追加段那条腿的对照面，版本号一律现取，不抄进账。"""
    revision = _git_output("log", "-1", "--format=%h", "--", CONTRACT_REL).strip()
    if not revision:
        raise AssertionError("取不到任何一枚动过契约的提交：追加段这一条腿没法判，先取证再改尺")
    return revision


def committed_appendage_problems(pristine: str, ledger: tuple, rewords: tuple) -> list:
    """判据⑥③：现盘按两本账退回原形之后，必须仍是「最近那一版在册契约（同样退回原形）＋ 文末追加」。

    追加段那一截不与差异账的前缀尺见面，所以「就地改一句话、再补一行空行装作只长了文末」这种走法
    只能由这一条腿咬。它比「与最近某几版里任意一版同前缀」强：一枚**旧而短**的版本会白让追加段里的
    账外改口过关（新刀 A 第一版就是被这一条抓出来的），所以对照面只认最新那一版。
    """
    revision = committee_revision()
    committed = normalize_eol(git_show(revision)).decode("utf-8")
    baseline = unwind_differences(unwind_rewords(committed, rewords), ledger)
    if pristine.startswith(baseline):
        return []
    index = _first_difference(baseline, pristine)
    line = pristine.count("\n", 0, index) + 1
    return [
        "现盘按两本账退回原形之后，比最近那一版在册契约（commit %s）的同一原形还长了账外的格：从第 %d 字符"
        "（第 %d 行）起就不同，账上应是 %r，退回原形是 %r —— 文末长出来那一截里的原地改口只许登记在改口账上，不许就地消失"
        % (revision, index, line, _window(baseline, index), _window(pristine, index))
    ]

def apply_rewords(current_text: str, frozen_text: str, rewords: tuple) -> tuple:
    """把改口账逐枚按现盘退回历史态：交回 (历史态, 逐枚派生位置, 逐条红)。"""
    problems: list[str] = []
    for position, entry in enumerate(rewords, start=1):
        for reason in reword_shape_violations(entry):
            problems.append("改口账第 %d 枚（立案 %s）这形状不收：%s" % (position, entry.ticket, reason))
        for reason in reword_provenance_problems(entry):
            problems.append("改口账第 %d 枚（立案 %s）没有出处：%s" % (position, entry.ticket, reason))

    placed: list = []
    for position, entry in enumerate(rewords, start=1):
        if not entry.old or not entry.new or entry.old == entry.new:
            continue
        in_base = frozen_text.count(entry.old)
        if in_base:
            problems.append(
                "改口账第 %d 枚（立案 %s）的旧文在冻结基点里命中 %d 处：那一格长在历史区里，它属于差异账"
                "（手抄坐标 → 派生锚），不属于改口账" % (position, entry.ticket, in_base)
            )
            continue
        hits = _occurrences(current_text, entry.new)
        if len(hits) != 1:
            problems.append(
                "改口账第 %d 枚（立案 %s）登记的新文在现盘上命中 %d 处（要求恰 1 处）："
                "那一格的原地改口要么没落地，要么后来又被改过" % (position, entry.ticket, len(hits))
            )
            continue
        if current_text.count(entry.old):
            problems.append(
                "改口账第 %d 枚（立案 %s）登记的旧文在现盘上还命中 1 处：账说它已经原地改口，盘上它还在 —— "
                "把旧行留在盘上再多补一行，也只是追加，不是改口" % (position, entry.ticket)
            )
            continue
        placed.append((hits[0], entry))

    placed.sort(key=lambda item: item[0])
    for (start, entry), (next_start, nxt) in zip(placed, placed[1:]):
        if next_start < start + len(entry.new):
            problems.append(
                "改口账里立案 %s 与立案 %s 两格在现盘第 %d 字符之后重叠：一本账把同一格写了两遍"
                % (entry.ticket, nxt.ticket, start)
            )

    historical = current_text
    marks: list = []
    for start, entry in reversed(placed):
        if start and historical[start - 1] != "\n":
            problems.append(
                "改口账立案 %s 登记的那一格在现盘上不从行首起：原地改口只许整行换，不许从一行中间切开" % entry.ticket
            )
            continue
        unwound = historical[:start] + entry.old + historical[start + len(entry.new):]
        head_length = _common_head(entry.old, entry.new)
        tail_length = _common_tail(entry.old, entry.new, head_length)
        marks.append(
            RewordMark(
                ticket=entry.ticket,
                current_start=start,
                current_end=start + len(entry.new),
                historical_start=start,
                historical_end=start + len(entry.old),
                current_line=current_text.count("\n", 0, start) + 1,
                head_length=head_length,
                tail_length=tail_length,
            )
        )
        historical = unwound
    if historical.count("\n") != current_text.count("\n"):
        problems.append(
            "按改口账退回历史态之后行数变了（现盘 %d 行 -> 历史态 %d 行）：原地改口只许一行换一行，增行删行都算改史"
            % (current_text.count("\n"), historical.count("\n"))
        )
    return historical, tuple(reversed(marks)), problems


def unwind_differences(text: str, ledger: tuple) -> str:
    """把差异账也退回原形：追加段那一条腿要比的是「一本账都没登记过」的那一份契约。"""
    pristine = text
    for entry in ledger:
        if entry.new and pristine.count(entry.new) == 1:
            pristine = pristine.replace(entry.new, entry.old, 1)
    return pristine
def audit_history(base_text: str, current_text: str, ledger: tuple, rewords: tuple = ()) -> Account:
    """把「前缀逐字节相同」这条不变式按两本账走一遍：现盘先退回历史态，再交回逐枚派生位置与逐条红。"""
    violations: list[str] = []

    for position, entry in enumerate(ledger, start=1):
        for reason in shape_violations(entry):
            violations.append("差异账第 %d 枚（立案 %s）这形状不收：%s" % (position, entry.ticket, reason))

    placed: list = []
    for position, entry in enumerate(ledger, start=1):
        if not entry.old or not entry.new:
            violations.append(
                "差异账第 %d 枚（立案 %s）旧文或新文是空串：账只收「换成派生锚」，不收把话删掉那一形" % (position, entry.ticket)
            )
            continue
        hits = _occurrences(base_text, entry.old)
        if len(hits) != 1:
            violations.append(
                "差异账第 %d 枚（立案 %s）的旧文在基点里命中 %d 处（要求恰 1 处）：起点无从派生。"
                "要么这一格根本没在基点上长过，要么尺的基点被前移过 —— 后者是灭红，不是改账" % (position, entry.ticket, len(hits))
            )
            continue
        placed.append((hits[0], entry))

    placed.sort(key=lambda item: item[0])
    for (start, entry), (next_start, nxt) in zip(placed, placed[1:]):
        if next_start < start + len(entry.old):
            violations.append(
                "差异账里立案 %s 与立案 %s 两格在基点第 %d 字符之后重叠：一本账把同一格写了两遍"
                % (entry.ticket, nxt.ticket, start)
            )

    segments: list = []
    anchors: list = []          # (拼接里的起点, 拼接里的长度, 基点里的起点)
    records: list = []
    cursor = 0
    built = 0
    for start, entry in placed:
        if start < cursor:
            continue            # 重叠已经报过，不再拼第二次
        segments.append(base_text[cursor:start])
        anchors.append((built, start - cursor, cursor))
        built += start - cursor
        segments.append(entry.new)
        anchors.append((built, len(entry.new), start))
        current_start = built
        built += len(entry.new)
        records.append(
            Record(
                ticket=entry.ticket,
                base_start=start,
                base_end=start + len(entry.old),
                current_start=current_start,
                current_end=current_start + len(entry.new),
                base_line=base_text.count("\n", 0, start) + 1,
                current_line=current_text.count("\n", 0, min(current_start, len(current_text))) + 1,
            )
        )
        cursor = start + len(entry.old)
    segments.append(base_text[cursor:])
    anchors.append((built, len(base_text) - cursor, cursor))
    expected = "".join(segments)

    for position, entry in enumerate(ledger, start=1):
        got_new = current_text.count(entry.new)
        if got_new != 1:
            violations.append(
                "差异账第 %d 枚（立案 %s）登记的新文在现盘上命中 %d 处（要求恰 1 处）："
                "那一格改写要么没落地，要么后来又被改过" % (position, entry.ticket, got_new)
            )
        got_old = current_text.count(entry.old)
        if got_old:
            violations.append(
                "差异账第 %d 枚（立案 %s）登记的旧文在现盘上还命中 %d 处：账说它已经换掉，盘上它还在"
                % (position, entry.ticket, got_old)
            )

    # 两本账的分工按**冻结基点**划线（`FROZEN_BASE` 的字面量钉就是这一行的依据）：刀③ 把尺的基点
    # 临时挪到较新的一版时，那一版里带着已经改过口的行，不许因此就把在册的改口判成越界。
    historical, marks, reword_problems = apply_rewords(current_text, base_contract_text(), tuple(rewords))
    violations.extend(reword_problems)

    if not historical.startswith(expected):
        index = _first_difference(expected, historical)
        violations.append(
            "契约的历史在差异账之外被动过：现盘第 %d 字符（第 %d 行）起与「基点 ＋ 账上 %d 枚登记」的拼接不同，"
            "对应基点第 %d 字符；账上应是 %r，现盘是 %r"
            % (index, historical.count("\n", 0, index) + 1, len(ledger), _base_anchor(anchors, index),
               _window(expected, index), _window(historical, index))
        )
    if len(historical) <= len(expected):
        violations.append(
            "契约没长东西：现盘 %d 字符 <= 拼接后的历史 %d 字符，本单一格都没往文末追加" % (len(historical), len(expected))
        )
    pristine = unwind_differences(historical, tuple(ledger))
    violations.extend(committed_appendage_problems(pristine, tuple(ledger), tuple(rewords)))

    return Account(base_text, current_text, expected, tuple(records), tuple(violations), historical, marks)


def _base_anchor(anchors: list, index: int) -> int:
    """拼接文本里的某一枚字符位，对应回基点的第几字符位（红句要点名的是「历史上那一格」的位置）。"""
    for start, length, base_start in anchors:
        if start <= index < start + length:
            return base_start + (index - start)
    return index


def assert_history_matches_ledger(base_text: str = None, current_text: str = None,
                                  ledger: tuple = None, expected_count: int = None,
                                  rewords: tuple = None, expected_reword_count: int = None) -> Account:
    """判据⑦ 唯一那把尺（r354 那两枚钉与 r653 那六枚钉共用）：现盘 == 基点 ＋ 具名差异账 ＋ 文末追加，
    而文末那一截里改过口的行只许长在改口账上：先按账退回原形，再逐条腿比（差异账 ＋ 追加段 ＋ 枚数门）。
    """
    base = base_contract_text() if base_text is None else base_text
    current = current_contract_text() if current_text is None else current_text
    book = CONTRACT_DIFFERENCES if ledger is None else tuple(ledger)
    reword_book = CONTRACT_REWORDS if rewords is None else tuple(rewords)
    want = EXPECTED_DIFFERENCES_TODAY if expected_count is None else expected_count
    want_rewords = EXPECTED_REWORDS_TODAY if expected_reword_count is None else expected_reword_count

    account = audit_history(base, current, book, reword_book)
    problems = list(account.violations)
    if len(book) != want:
        problems.append("差异账的枚数不对：账上登记 %d 枚，今天应当恰好 %d 枚（多一枚少一枚都红）" % (len(book), want))
    if len(account.records) != want:
        problems.append(
            "派生出来的差异枚数不对：账上登记 %d 枚、能在基点定位的 %d 枚，今天应当恰好 %d 枚"
            % (len(book), len(account.records), want)
        )
    if len(reword_book) != want_rewords:
        problems.append(
            "改口账的枚数不对：账上登记 %d 枚，今天应当恰好 %d 枚（多一枚少一枚都红）" % (len(reword_book), want_rewords)
        )
    if len(account.reword_marks) != want_rewords:
        problems.append(
            "派生出来的改口枚数不对：账上登记 %d 枚、能在现盘定位的 %d 枚，今天应当恰好 %d 枚"
            % (len(reword_book), len(account.reword_marks), want_rewords)
        )
    if problems:
        raise AssertionError(
            "契约历史与具名账（差异 ＋ 改口）对不上（%d 条）：\n  · %s" % (len(problems), "\n  · ".join(problems))
        )
    return account
def derived_difference_table(account: Account) -> list:
    """逐枚点名：立案、基点起点／终点字符位与行号、现盘起点／终点字符位与行号、旧文新文字数。"""
    rows: list[str] = []
    for record in account.records:
        rows.append(
            "立案 %s：基点第 %d..%d 字符（第 %d 行，旧文 %d 字）-> 现盘第 %d..%d 字符（第 %d 行，新文 %d 字）"
            % (
                record.ticket,
                record.base_start, record.base_end, record.base_line, record.base_end - record.base_start,
                record.current_start, record.current_end, record.current_line,
                record.current_end - record.current_start,
            )
        )
    return rows


def derived_reword_table(account: Account) -> list:
    """逐枚点名改口：立案、现盘起点／终点字符位与行号、退回历史态后的终点、两侧逐字等值的前缀／后缀长度。"""
    rows: list[str] = []
    for mark in account.reword_marks:
        rows.append(
            "立案 %s：现盘第 %d..%d 字符（第 %d 行，新文 %d 字）-> 历史态到第 %d 字符收尾（旧文 %d 字），"
            "两侧逐字相等的前缀 %d 字 / 后缀 %d 字"
            % (
                mark.ticket,
                mark.current_start, mark.current_end, mark.current_line, mark.current_end - mark.current_start,
                mark.historical_end, mark.historical_end - mark.historical_start,
                mark.head_length, mark.tail_length,
            )
        )
    return rows


# ------------------------------------------------------------------ 一本账只许有一份

#: pytest 按顶层名收本文件，r354 却按 `tests.` 点名 import 它。两个名字若落在两个模块对象上，
#: 刀架在自己这一份的把手上、钉读的那一份看不见 —— 反证立刻变成假绿。所以先把名字合流，
#: 再由 `test_the_ledger_module_is_a_single_object_under_both_names` 把它钉成常驻牙。
TOP_NAME = __name__.rpartition(".")[2]
DOTTED_NAME = "tests." + TOP_NAME
for _alias in (TOP_NAME, DOTTED_NAME):
    sys.modules.setdefault(_alias, SELF)
_TESTS_PACKAGE = sys.modules.get("tests")
if _TESTS_PACKAGE is not None:
    setattr(_TESTS_PACKAGE, TOP_NAME, SELF)

R354_STEM = Path(R354_REL).name[: -len(".py")]
#: 影子副本落在 tmp_path 下面，文件名沿用契约那一枚：与 R218/R253 认的好形状同形。
CONTRACT_NAME = "contract-v1.md"

#: 不许被两枚钉自己拿去当地名的「文本」把手：一旦 `startswith` 的两侧是这些名字，
#: 就说明那枚钉在自己做前缀等式，而不是在读账。
TEXT_NAMES = frozenset({
    "base", "base_text", "current", "current_text", "expected", "expected_prefix", "account", "text",
})
#: r354 里那两枚钉的可达面里不许再出现的私有把手：它们一旦留着，就是第二把尺（或第二份 git blob）。
R354_FORBIDDEN_NAMES = frozenset({"BASE", "CONTRACT", "_git", "_normalize_eol", "_first_difference", "subprocess"})
#: 判据⑤ 的硬话：不许 skip、不许 xfail、不许豁免名单。
NO_ESCAPE_CALLS = frozenset({"skip", "xfail", "importorskip"})


def _own_source() -> str:
    return Path(__file__).resolve().read_text(encoding="utf-8")


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO)] + list(args), capture_output=True, check=True
    ).stdout.decode("utf-8")


def _git_ok(*args: str) -> bool:
    return subprocess.run(["git", "-C", str(REPO)] + list(args), capture_output=True).returncode == 0


def _disk_contract_bytes() -> bytes:
    """盘上那一枚禁区文件：刀永远只读它，写出去的是 tmp_path 下的影子。"""
    return (REPO / CONTRACT_REL).read_bytes()


def _disk_sha() -> str:
    return hashlib.sha256(_disk_contract_bytes()).hexdigest()


def _disk_text_and_newline() -> tuple:
    raw = _disk_contract_bytes()
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    newline = "\r\n" if crlf and not lone_lf else "\n"
    return normalize_eol(raw).decode("utf-8"), newline


def _shadow_copy(tmp_path: Path, mutate) -> Path:
    """把盘上契约抄到 tmp_path，抄的过程里做一处改写；行尾从盘上自取，不硬写。"""
    text, newline = _disk_text_and_newline()
    mutated = mutate(text)
    if mutated == text:
        raise AssertionError("影子端的改写没有生效：这一把刀什么都没改，红了也说明不了问题")
    data = mutated.encode("utf-8")
    if newline == "\r\n":
        data = data.replace(b"\n", b"\r\n")
    target = tmp_path / CONTRACT_NAME
    target.write_bytes(data)
    assert str(target).startswith(str(tmp_path)), "影子端写到了 tmp_path 外面：%s" % target
    return target


def _ledger_entry(ticket: str) -> Difference:
    for entry in SELF.CONTRACT_DIFFERENCES:
        if entry.ticket == ticket:
            return entry
    raise AssertionError("差异账里没有立案 %s：今天这本账应当逐枚点名" % ticket)


def _reword_entry(ticket: str) -> Reword:
    for entry in SELF.CONTRACT_REWORDS:
        if entry.ticket == ticket:
            return entry
    raise AssertionError("改口账里没有立案 %s：今天这本账应当逐枚点名" % ticket)


def _r354_module():
    """取 r354 那枚件本身：pytest 已按顶层名导过就复用那一份，否则按 `tests.` 点名导。"""
    for name in (R354_STEM, "tests." + R354_STEM):
        module = sys.modules.get(name)
        if module is not None:
            return module
    return importlib.import_module("tests." + R354_STEM)


def _run_r354_nails() -> dict:
    """逐枚现跑那两枚钉：交回 {钉名: 红句}，绿的那一枚交回空串（不当场 raise，好让两枚都说话）。"""
    module = _r354_module()
    outcome: dict = {}
    for name in R354_NAILS:
        nail = getattr(module, name, None)
        if nail is None:
            raise AssertionError("r354 里找不到钉 %s：本单共用的那两枚被改名或删掉了" % name)
        try:
            nail()
        except AssertionError as error:
            outcome[name] = str(error)
        else:
            outcome[name] = ""
    return outcome


def _red(outcome: dict) -> dict:
    return {name: message for name, message in outcome.items() if message}
# ------------------------------------------------------------------ 现查源码的几把手

def _parse(relative: str) -> ast.Module:
    return ast.parse((REPO / relative).read_text(encoding="utf-8"))


def _function_defs(tree: ast.Module) -> dict:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _calls_of(node: ast.AST) -> set:
    names: set = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                names.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                names.add(sub.func.attr)
    return names


def _shells_out(tree: ast.Module) -> frozenset:
    """自己跑 git / 子进程的那些函数：两枚钉的可达面一枚都不许沾。"""
    return frozenset(
        node.name for node in tree.body
        if isinstance(node, ast.FunctionDef) and {"run", "check_output", "Popen"} & _calls_of(node)
    )


def _reachable(tree: ast.Module, entry: str) -> dict:
    """从一枚钉出发，沿本文件的顶层函数定义走一遍，把可达面上的名字分门别类交回来。"""
    defs = _function_defs(tree)
    found = {"local": set(), "called": set(), "loads": set(), "strings": set(), "prefix_receivers": set()}
    stack = [entry]
    while stack:
        name = stack.pop()
        if name in found["local"]:
            continue
        found["local"].add(name)
        node = defs.get(name)
        if node is None:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Name):
                    found["called"].add(func.id)
                    if func.id in defs and func.id not in found["local"]:
                        stack.append(func.id)
                elif isinstance(func, ast.Attribute):
                    found["called"].add(func.attr)
                    if func.attr == "startswith" and isinstance(func.value, ast.Name):
                        found["prefix_receivers"].add(func.value.id)
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                found["loads"].add(sub.id)
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found["strings"].add(sub.value)
    return found


def _literal_assignments(tree: ast.Module, name: str) -> list:
    """全文件里对某个常量名的赋值（任何作用域），交回值节点。"""
    hits: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    hits.append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            hits.append(node.value)
    return hits


def _literal_pin_problems(source_text: str) -> list:
    """尺的三枚字面量：基点 `a7ac040`、差异枚数门 `1`、改口枚数门 `1`。它们一被挪走，红句就交回来。

    为什么必须有这一枚钉（刀③ 当场演示）：把基点前移 + 把账清空 + 把枚数门归零，
    「历史逐字节不许动」这条不变式在尺那一层是可以整体绕过去的 —— 唯一的封口就是
    源码里那两枚字面量，所以它们得被钉住，而不是被当成可改的缺省值。
    """
    problems: list[str] = []
    tree = ast.parse(source_text)

    bases = _literal_assignments(tree, "FROZEN_BASE")
    if len(bases) != 1:
        problems.append("尺的基点 FROZEN_BASE 在源码里被赋值了 %d 次（要求恰 1 次）：多处赋值就是可挪" % len(bases))
    elif not (isinstance(bases[0], ast.Constant) and bases[0].value == "a7ac040"):
        problems.append(
            "尺的基点被从字面量 a7ac040 挪走了（现在是 %r）：禁止用把基点前移来灭红" % _value_of(bases[0])
        )

    gates = _literal_assignments(tree, "EXPECTED_DIFFERENCES_TODAY")
    if len(gates) != 1:
        problems.append("枚数门 EXPECTED_DIFFERENCES_TODAY 被赋值了 %d 次（要求恰 1 次）" % len(gates))
    elif not (isinstance(gates[0], ast.Constant) and gates[0].value == 1):
        problems.append(
            "枚数门不再是 1（现在是 %r）：正控必须钉在「恰好一枚」上，不许松成阈值" % _value_of(gates[0])
        )
    gates_rewords = _literal_assignments(tree, "EXPECTED_REWORDS_TODAY")
    if len(gates_rewords) != 1:
        problems.append("改口枚数门 EXPECTED_REWORDS_TODAY 被赋值了 %d 次（要求恰 1 次）" % len(gates_rewords))
    elif not (isinstance(gates_rewords[0], ast.Constant) and gates_rewords[0].value == 1):
        problems.append(
            "改口枚数门不再是 1（现在是 %r）：原地改口同样只许恰好一枚，不许松成阈值" % _value_of(gates_rewords[0])
        )
    return problems


def _value_of(node: ast.AST):
    return getattr(node, "value", ast.dump(node))


def _synthetic_second_entry() -> Difference:
    """从基点文本里现找一枚**别处**的手抄坐标，派生成第二格登记：只为撑枚数门，盘上没有这一格。"""
    base = base_contract_text()
    registered = _ledger_entry("R630")
    for line in base.splitlines():
        if not line or line == registered.old.rstrip("\n"):
            continue
        coords = HAND_COPY_COORD.findall(line)
        if not coords:
            continue
        new = line
        for coord in sorted(set(coords), key=len, reverse=True):
            stem, _, _number = coord.partition(":")
            new = new.replace(coord, "%s::derived_symbol_here" % stem)
        return Difference(
            ticket="R645-合成第二枚",
            old=line + "\n",
            new=new + "\n",
            reason="这一格只用来把枚数门撑到两枚：盘上从来没有落地过",
        )
    raise AssertionError("基点里找不到第二枚手抄坐标：那枚数门就没法被合成地撑起来")
def derive_reword_pair(entry: Reword) -> tuple:
    """账本的生成件：拿登记的两半回 git 现取，交回 (改口落地那一版, 那一版上一版里的那一行, 那一版里的那一行)。

    下一班要再登记一枚原地改口时不必手抄整行：按格子名取现盘那一行当新文，再取落地那一版的上一版那一行当旧文。
    两半对不上登记，就是这本账与历史分家了 —— 当场红，不许就地改抄。
    """
    marker = "| `%s` |" % _row_node(entry.old)
    landed = _git_output("log", "--format=%h", "-S", entry.new, "--", CONTRACT_REL).split()
    if len(landed) != 1:
        raise AssertionError(
            "立案 %s 登记的新文在契约历史里改变了 %d 版的发生次数（要求恰 1 版）："
            "那一格要么没原地落地过，要么这本登记不是唯一的一版" % (entry.ticket, len(landed))
        )
    landing = landed[0]
    before = normalize_eol(git_show("%s^" % landing)).decode("utf-8")
    after = normalize_eol(git_show(landing)).decode("utf-8")
    rows_before = [line for line in before.splitlines(True) if line.startswith(marker)]
    rows_after = [line for line in after.splitlines(True) if line.startswith(marker)]
    if len(rows_before) != 1 or len(rows_after) != 1:
        raise AssertionError(
            "版本 %s 与其上一版里以 %r 起头的表格行不是各一枚（得 %d 枚与 %d 枚）：格子名不再唯一"
            % (landing, marker, len(rows_before), len(rows_after))
        )
    if rows_before[0] == rows_after[0]:
        raise AssertionError("版本 %s 里 %r 那一行没有原地变过：这一格不是改口，别拿它入账" % (landing, marker))
    return landing, rows_before[0], rows_after[0]


# ------------------------------------------------------------------ 常驻牙：账本身

def test_the_disk_state_is_green_with_exactly_one_named_difference():
    """正控：现盘在账上是绿的，而且绿在「恰好一枚具名差异」上，不是绿在松掉的阈值上。"""
    account = assert_history_matches_ledger()

    assert account.violations == (), account.violations
    assert len(account.records) == EXPECTED_DIFFERENCES_TODAY == 1, derived_difference_table(account)
    assert [record.ticket for record in account.records] == ["R630"], account.records
    assert len(account.appendage) > 0, "追加段是空的：契约没长东西"
    rows = derived_difference_table(account)
    assert len(rows) == 1, rows


def test_the_derived_positions_match_the_verbatim_ledger_text():
    """账上抄的是字，不是位置：派生出来的那一段必须与登记的逐文字一模一样。"""
    account = assert_history_matches_ledger()
    record = account.records[0]
    entry = _ledger_entry(record.ticket)

    assert account.base_text[record.base_start:record.base_end] == entry.old
    assert account.current_text[record.current_start:record.current_end] == entry.new
    assert record.base_end - record.base_start == len(entry.old)
    assert record.current_end - record.current_start == len(entry.new)
    # 那一格是就地换掉，不是把邻格一起拖走：前后各 200 字符的上下文两侧必须一字不差。
    head_before = account.base_text[max(0, record.base_start - 200):record.base_start]
    assert head_before == account.current_text[max(0, record.current_start - 200):record.current_start]
    tail_after = account.base_text[record.base_end:record.base_end + 200]
    assert tail_after == account.current_text[record.current_end:record.current_end + 200]
    assert entry.old.endswith("\n") and entry.old.count("\n") == 1, "登记的那一格必须恰好是一整行（旧文）"
    assert entry.new.endswith("\n") and entry.new.count("\n") == 1, "登记的那一格必须恰好是一整行（新文）"


def test_the_difference_record_carries_no_position_field():
    """判据③ 的结构防线：`Difference` 的字段面里根本没有位置那一格，手抄偏移量抄都没地方抄。"""
    assert set(Difference._fields) == {"ticket", "old", "new", "reason"}, Difference._fields
    assert set(get_type_hints(Difference).values()) == {str}, get_type_hints(Difference)
    assert {"base_start", "base_end", "current_start", "current_end", "base_line", "current_line"} <= set(
        Record._fields
    ), Record._fields

    for entry in CONTRACT_DIFFERENCES:
        assert entry.ticket and entry.reason, entry
        assert entry.old != entry.new, entry.ticket
        with pytest.raises(AttributeError):
            entry.base_start  # type: ignore[attr-defined]


def test_the_ledger_entries_are_the_accepted_shape():
    """判据② 的正控：账上每一枚都必须是「手抄坐标 → 派生锚」那一形状。"""
    assert CONTRACT_DIFFERENCES, "差异账是空的：现盘明明与基点差着一格（R630），空账就是假绿"

    for entry in CONTRACT_DIFFERENCES:
        problems = shape_violations(entry)
        assert problems == [], (entry.ticket, problems)
        assert HAND_COPY_COORD.findall(entry.old), entry.ticket
        assert HAND_COPY_COORD.findall(entry.new) == [], entry.ticket
        assert BARE_LINE_NUMBER.findall(entry.new) == [], entry.ticket
        assert DERIVED_ANCHOR.findall(entry.new), entry.ticket


def test_the_frozen_base_is_pinned_by_literal_and_lands_in_history():
    """判据③ 的封口：基点与枚数门是字面量，且那一版真的在这条历史线上。"""
    source = _own_source()
    assert _literal_pin_problems(source) == [], _literal_pin_problems(source)
    assert FROZEN_BASE == "a7ac040"
    assert EXPECTED_DIFFERENCES_TODAY == 1

    assert _git_output("cat-file", "-t", FROZEN_BASE).strip() == "commit"
    assert _git_ok("merge-base", "--is-ancestor", FROZEN_BASE, "HEAD"), FROZEN_BASE
    head = _git_output("rev-parse", "--short", "HEAD").strip()
    assert FROZEN_BASE != head, (FROZEN_BASE, head)
    newest = _git_output("log", "-1", "--format=%h", "--", CONTRACT_REL).strip()
    assert newest and _git_ok("merge-base", "--is-ancestor", FROZEN_BASE, newest), newest
    assert _git_ok("merge-base", "--is-ancestor", newest, "HEAD"), newest


def test_the_registered_difference_is_committed_not_a_dirty_fluke():
    """账上那一格必须在提交里：谁也不能拿一枚停在工作树上的手写来平账。

    🔴 这一枚读的是 git 对象，不是「此刻工作树脏不脏」——并树前后同数，不会并树即自毁。
    """
    committed = head_contract_text()

    for entry in CONTRACT_DIFFERENCES:
        assert committed.count(entry.new) == 1, entry.ticket
        assert committed.count(entry.old) == 0, entry.ticket
        coord = HAND_COPY_COORD.search(entry.old).group(0)
        removed_by = _git_output("log", "--format=%h", "-S", coord, "--", CONTRACT_REL).split()
        assert removed_by, coord
        assert _git_ok("merge-base", "--is-ancestor", removed_by[0], "HEAD"), removed_by
        anchor = DERIVED_ANCHOR.search(entry.new).group(0)
        added_by = _git_output("log", "--format=%h", "-S", anchor, "--", CONTRACT_REL).split()
        assert added_by, anchor


def test_the_ledger_holds_exactly_one_difference_today():
    """判据② 的枚数门：少一枚多一枚都红，且红句要说「枚数不对」，不能只说「找不到」。"""
    account = assert_history_matches_ledger()
    assert len(CONTRACT_DIFFERENCES) == len(account.records) == EXPECTED_DIFFERENCES_TODAY == 1
    assert [entry.ticket for entry in CONTRACT_DIFFERENCES] == ["R630"], CONTRACT_DIFFERENCES

    second = _synthetic_second_entry()
    assert shape_violations(second) == [], shape_violations(second)
    with pytest.raises(AssertionError) as more:
        assert_history_matches_ledger(ledger=(tuple(CONTRACT_DIFFERENCES) + (second,)))
    assert "枚数不对" in str(more.value), str(more.value)
    assert "账上登记 2 枚，今天应当恰好 1 枚" in str(more.value), str(more.value)

    with pytest.raises(AssertionError) as fewer:
        assert_history_matches_ledger(ledger=())
    assert "枚数不对" in str(fewer.value), str(fewer.value)
    assert "账上登记 0 枚，今天应当恰好 1 枚" in str(fewer.value), str(fewer.value)
#: r354 手里那枚账本把手的名字：两枚钉共用的是这一个模块对象，不是抄来的第二份尺。
LEDGER_HANDLE = "contract_ledger"
#: 判据⑤ 禁的逃生口这一族（`pytest.raises` 是刀的正解，不算逃生）。
ESCAPE_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})


def test_the_two_r354_nails_read_this_same_book():
    """判据④：两枚钉只读这一本账 —— 谁也不许留着自家的前缀等式或自家的 git 把手。"""
    tree = _parse(R354_REL)
    defs = _function_defs(tree)
    shellers = _shells_out(tree)
    module = _r354_module()

    assert getattr(module, LEDGER_HANDLE, None) is SELF, "r354 拿到的账本不是本文件这一份"
    for name in R354_NAILS:
        assert name in defs, "r354 里那枚钉不见了：%s" % name
        reach = _reachable(tree, name)
        assert R354_SHARED_RULER in reach["local"], (name, sorted(reach["local"]))
        assert SHARED_ENTRY_POINT in reach["called"], (name, sorted(reach["called"]))
        hijacked = (reach["local"] | reach["loads"]) & R354_FORBIDDEN_NAMES
        assert not hijacked, "%s 还留着自家的把手：%s" % (name, sorted(hijacked))
        assert not (reach["local"] & shellers), (name, sorted(reach["local"] & shellers))
        assert "show" not in reach["strings"], name
        assert not [text for text in reach["strings"] if CONTRACT_REL in text], name
        assert not [text for text in reach["strings"] if text == FROZEN_BASE], name
        private_prefix = sorted(reach["prefix_receivers"] & TEXT_NAMES)
        assert not private_prefix, "%s 在自己做前缀等式：%s" % (name, private_prefix)
        nail = getattr(module, name)
        assert list(inspect.signature(nail).parameters) == [], (name, inspect.signature(nail))


def test_the_ledger_module_is_a_single_object_under_both_names():
    """同名两副面孔就是假绿的入口：刀架在这一份上，钉读的那一份看不见。"""
    assert sys.modules[TOP_NAME] is SELF, TOP_NAME
    assert sys.modules[DOTTED_NAME] is SELF, DOTTED_NAME
    assert getattr(_r354_module(), LEDGER_HANDLE, None) is SELF


def test_the_nail_files_copy_no_byte_offsets():
    """判据③：位置只能派生。今天派生出来的那些数字，一枚都不许以字面量的形态活在这两枚件里。"""
    account = assert_history_matches_ledger()
    positions: set = set()
    lines: set = set()
    for record in account.records:
        positions |= {record.base_start, record.base_end, record.current_start, record.current_end}
        lines |= {record.base_line, record.current_line}
    positions |= {len(account.base_text), len(account.current_text), len(account.expected_prefix)}

    for relative in (R354_REL, "tests/" + Path(__file__).name):
        text = (REPO / relative).read_text(encoding="utf-8")
        bare = re.findall(r"(?<![\w.])\d{5,}(?![\w.])", text)
        assert bare == [], "%s 里出现了五位以上的裸数字（手抄偏移量的形状）：%s" % (relative, sorted(set(bare)))
        for position in sorted(positions):
            assert str(position) not in text, "%s 把派生出来的位置 %d 抄成了字面量" % (relative, position)
        for line in sorted(lines):
            assert str(line) not in text, "%s 把派生出来的行号 %d 抄成了字面量" % (relative, line)


def _escape_calls(tree: ast.Module) -> list:
    """`pytest.skip` / `pytest.mark.skipif` / `pytest.xfail` 这一族逃生口。"""
    hits: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        outer = node.func
        inner = outer.value
        if outer.attr not in ESCAPE_ATTRS:
            continue
        if isinstance(inner, (ast.Name, ast.Attribute)):
            base = inner
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id == "pytest":
                hits.append("%s.%s" % (ast.unparse(inner), outer.attr))
    return sorted(set(hits))


def _loose_count_assertions(tree: ast.Module) -> list:
    """枚数那一格只能写等号：`<`／`<=`／`>`／`>=` 套在 records 或账上，正控就松成了阈值。"""
    loose: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left] + list(node.comparators)
        rendered = [ast.unparse(item) for item in operands]
        if not any(("records" in text or "CONTRACT_DIFFERENCES" in text) for text in rendered):
            continue
        if any(isinstance(op, (ast.LtE, ast.GtE, ast.Lt, ast.Gt)) for op in node.ops):
            loose.append(ast.unparse(node)[:160])
    return loose


def test_the_ledger_ships_no_skip_or_exemption_list():
    """判据⑤ 的下限：不许 skip、不许 xfail、不许把枚数门写成阈值，两枚钉也不许留逃生口。"""
    own = ast.parse(_own_source())
    assert _escape_calls(own) == [], _escape_calls(own)
    assert _loose_count_assertions(own) == [], _loose_count_assertions(own)

    tree = _parse(R354_REL)
    defs = _function_defs(tree)
    for name in R354_NAILS:
        reach = _reachable(tree, name)
        trapped = reach["called"] & NO_ESCAPE_CALLS
        assert not trapped, "%s 里有逃生口：%s" % (name, sorted(trapped))
        body = ast.Module(body=[defs[name]], type_ignores=[])
        assert _escape_calls(body) == [], name
        assert _loose_count_assertions(body) == [], name
        decorators = [ast.unparse(item) for item in defs[name].decorator_list]
        assert not [text for text in decorators if "skip" in text or "xfail" in text], (name, decorators)
# ------------------------------------------------------------------ 常驻牙：改口账（R664）


def test_the_reword_book_is_green_with_exactly_one_named_reword():
    """正控：现盘在改口账上同样是绿的，而且绿在「恰好一枚原地改口」上，不是绿在松掉的阈值上。"""
    account = assert_history_matches_ledger()

    assert account.violations == (), account.violations
    assert len(account.reword_marks) == EXPECTED_REWORDS_TODAY == 1, derived_reword_table(account)
    assert [mark.ticket for mark in account.reword_marks] == ["R657"], account.reword_marks
    assert account.historical_text and account.historical_text != account.current_text
    assert len(account.appendage) > 0, "追加段是空的：契约没长东西"
    assert len(derived_reword_table(account)) == 1, derived_reword_table(account)


def test_the_reword_positions_are_derived_and_the_neighbourhood_is_byte_equal():
    """判据⑥①：那一格的位置由现盘派生，前后各 200 字符两侧逐字等值 —— 原地改口不许把邻格一起拖走。"""
    account = assert_history_matches_ledger()
    mark = account.reword_marks[0]
    entry = _reword_entry(mark.ticket)

    assert account.current_text[mark.current_start:mark.current_end] == entry.new
    assert account.historical_text[mark.historical_start:mark.historical_end] == entry.old
    assert account.current_text[:mark.current_start] == account.historical_text[:mark.historical_start]
    assert account.current_text[mark.current_end:] == account.historical_text[mark.historical_end:]
    head_before = account.current_text[max(0, mark.current_start - 200):mark.current_start]
    assert head_before == account.historical_text[max(0, mark.historical_start - 200):mark.historical_start]
    tail_after = account.current_text[mark.current_end:mark.current_end + 200]
    assert tail_after == account.historical_text[mark.historical_end:mark.historical_end + 200]
    assert entry.old.endswith("\n") and entry.old.count("\n") == 1, mark.ticket
    assert entry.new.endswith("\n") and entry.new.count("\n") == 1, mark.ticket
    assert _row_node(entry.old) == _row_node(entry.new), mark.ticket
    assert 0 < mark.head_length < len(entry.old), derived_reword_table(account)
    assert mark.head_length + mark.tail_length < min(len(entry.old), len(entry.new)), "两半叠满了：那其实没改口"


def test_the_reword_entries_are_the_accepted_shape_with_a_named_provenance():
    """判据⑥② 的正控：账上每一枚都先要是「派生锚行的原地改口」，再点得出单号与凭据纸。"""
    assert CONTRACT_REWORDS, "改口账是空的：现盘明明有一格原地改过口（R657），空账就是假绿"

    for entry in CONTRACT_REWORDS:
        problems = reword_shape_violations(entry)
        assert problems == [], (entry.ticket, problems)
        provenance = reword_provenance_problems(entry)
        assert provenance == [], (entry.ticket, provenance)
        assert DERIVED_ANCHOR.findall(entry.old), entry.ticket
        assert DERIVED_ANCHOR.findall(entry.new), entry.ticket
        assert HAND_COPY_COORD.findall(entry.new) == [], entry.ticket
        assert BARE_LINE_NUMBER.findall(entry.new) == [], entry.ticket


def test_the_reword_record_carries_no_position_field():
    """判据③ 对改口账同样成立：`Reword` 的字段面里没有位置那一格，只有单号与凭据纸。"""
    assert set(Reword._fields) == {"ticket", "old", "new", "reason", "evidence"}, Reword._fields
    assert set(get_type_hints(Reword).values()) == {str}, get_type_hints(Reword)
    assert {"current_start", "current_end", "historical_start", "historical_end", "current_line",
            "head_length", "tail_length"} <= set(RewordMark._fields), RewordMark._fields

    for entry in CONTRACT_REWORDS:
        assert entry.ticket and entry.reason and entry.evidence, entry
        assert entry.old != entry.new, entry.ticket
        with pytest.raises(AttributeError):
            entry.current_start  # type: ignore[attr-defined]


def test_the_two_books_do_not_write_the_same_row():
    """两本账各管一段：差异账管冻结基点那一段历史，改口账只管文末长出来那一截里的行。"""
    account = assert_history_matches_ledger()

    for entry in CONTRACT_REWORDS:
        assert account.base_text.count(entry.old) == 0, entry.ticket
        assert account.base_text.count(entry.new) == 0, entry.ticket
        assert entry.ticket not in [record.ticket for record in account.records], entry.ticket
    for registered in CONTRACT_DIFFERENCES:
        for entry in CONTRACT_REWORDS:
            assert registered.old not in entry.new and registered.new not in entry.old, (
                registered.ticket, entry.ticket)


def test_the_registered_reword_lands_in_a_commit_and_derives_from_it():
    """出处的结构腿：那一枚原地改口真的落在某枚提交里，旧行取自那一枚的上一版，两半与登记逐字相等。"""
    committed = head_contract_text()

    for entry in CONTRACT_REWORDS:
        assert committed.count(entry.new) == 1, entry.ticket
        assert committed.count(entry.old) == 0, entry.ticket
        landing, old_row, new_row = derive_reword_pair(entry)
        assert new_row == entry.new, (entry.ticket, landing)
        assert old_row == entry.old, (entry.ticket, landing)
        assert _git_ok("merge-base", "--is-ancestor", "%s^" % landing, "HEAD"), landing
        assert _git_ok("merge-base", "--is-ancestor", landing, "HEAD"), landing


def test_the_reword_book_holds_exactly_one_reword_today():
    """枚数门对改口账同样成立：少一枚多一枚都红，红句要说「改口账的枚数不对」。"""
    account = assert_history_matches_ledger()
    assert len(CONTRACT_REWORDS) == len(account.reword_marks) == EXPECTED_REWORDS_TODAY == 1
    assert [entry.ticket for entry in CONTRACT_REWORDS] == ["R657"], CONTRACT_REWORDS

    entry = _reword_entry("R657")
    with pytest.raises(AssertionError) as fewer:
        assert_history_matches_ledger(rewords=())
    assert "改口账的枚数不对" in str(fewer.value), str(fewer.value)

    with pytest.raises(AssertionError) as more:
        assert_history_matches_ledger(rewords=(entry, _reword_entry(entry.ticket)))
    assert "改口账的枚数不对" in str(more.value), str(more.value)


# ------------------------------------------------------------------ 六把反证刀

def test_counter_evidence_1_a_byte_changed_outside_the_ledger_reddens_both_nails(tmp_path, monkeypatch):
    """刀①：账外手改历史区一个标点 ⇒ 两枚钉都红，红句点名派生出来的位置（不是抄来的数字）。"""
    anchor = "**on the wire**"
    replacement = "**in the wire**"
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿：现盘在账上本来是不红的"

    text, _newline = _disk_text_and_newline()
    assert text.count(anchor) == 1 and text.count(replacement) == 0, anchor
    base_text = base_contract_text()
    assert base_text.find(anchor) != -1, anchor

    shadow = _shadow_copy(tmp_path, lambda body: body.replace(anchor, replacement, 1))
    shadow_text = normalize_eol(shadow.read_bytes()).decode("utf-8")
    #: 要点名的位置由影子端自己招：两侧第一次不同的那一格，不拿锚点起点去猜。
    index = next(k for k, (left, right) in enumerate(zip(text, shadow_text)) if left != right)
    line = text.count("\n", 0, index) + 1
    base_index = base_text.find(anchor) + (index - text.find(anchor))
    monkeypatch.setattr(SELF, "CONTRACT_PATH", shadow)

    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for name, message in red.items():
        assert "在差异账之外被动过" in message, (name, message)
        assert "现盘第 %d 字符" % index in message, (name, message)
        assert "第 %d 行" % line in message, (name, message)
        assert "对应基点第 %d 字符" % base_index in message, (name, message)
    assert len({message for message in red.values()}) == 1, "两枚钉的红句不同：它们读的不是同一本账"
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"


def test_counter_evidence_2_a_difference_of_the_wrong_shape_is_refused(tmp_path, monkeypatch):
    """刀②：往账里塞一枚不是「手抄坐标 → 派生锚」的改写 ⇒ 必红，并说清这形状为什么不收。"""
    old_fragment = "a model-side first token is a proxy"
    new_fragment = "a model-side first token is the answer"
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿"

    text, _newline = _disk_text_and_newline()
    assert text.count(old_fragment) == 1 and text.count(new_fragment) == 0, old_fragment
    wrong = Difference(
        ticket="R645-刀②",
        old=old_fragment,
        new=new_fragment,
        reason="把一句结论换掉了：这不是把过期坐标改成派生锚",
    )
    problems = shape_violations(wrong)
    assert problems, wrong
    assert any("旧文里一枚手抄坐标都没有" in line for line in problems), problems
    assert any("派生锚" in line for line in problems), problems

    shadow = _shadow_copy(tmp_path, lambda body: body.replace(old_fragment, new_fragment, 1))
    monkeypatch.setattr(SELF, "CONTRACT_PATH", shadow)
    with pytest.raises(AssertionError) as info:
        assert_history_matches_ledger(ledger=(_ledger_entry("R630"), wrong), expected_count=2)
    message = str(info.value)
    assert "这形状不收" in message and "R645-刀②" in message, message
    assert "旧文里一枚手抄坐标都没有" in message, message
    assert "在差异账之外被动过" not in message, "账外的格没被动过：这一刀只能由形状尺来红，否则是巧合"
    assert "枚数不对" not in message, message

    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for each in red.values():
        assert "在差异账之外被动过" in each, each
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"


def test_counter_evidence_3_moving_the_frozen_base_forward_reddens(monkeypatch):
    """刀③：把尺的基点从 `a7ac040` 换成较新的一版 ⇒ 必红；前移基点灭红由字面量钉常驻挡着。

    🔴 R664 之后这把刀的判据一字没松，改的是尺：现盘先按改口账退回历史态，再与「基点 ＋ 差异账」比前缀。
    于是那三条腿（前移基点 ＋ 清空差异账 ＋ 差异枚数门归零）重新走得通 —— 交回的候选正是 R657 原地改口
    之前那几版；把改口账也一起清空反而走不通，那一格由尺自己守住，不靠枚数门，见本刀第二条腿。
    """
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿"

    monkeypatch.setattr(SELF, "FROZEN_BASE", "HEAD")
    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for name, message in red.items():
        assert "命中 0 处" in message, (name, message)
        assert "基点被前移过" in message, (name, message)
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"

    # 前移基点这一条腿单独走不通（账与枚数门还盯着）。三条腿一起 —— 前移基点 + 清空账 + 枚数门归零
    # —— 才真能把这条不变式整体绕过去。所以那两枚字面量不是可改的缺省值，是尺的一部分：
    # 本刀先把后门证明是真的走得通，再证明字面量钉咬得动它。
    monkeypatch.setattr(SELF, "CONTRACT_DIFFERENCES", ())
    monkeypatch.setattr(SELF, "EXPECTED_DIFFERENCES_TODAY", 0)
    current = current_contract_text()
    escapes: list = []
    for candidate in _git_output("log", "--format=%h", "-8", "--", CONTRACT_REL).split():
        if candidate == FROZEN_BASE:
            continue
        try:
            assert_history_matches_ledger(
                base_text=base_contract_text(candidate), current_text=current, ledger=(), expected_count=0
            )
        except AssertionError:
            continue
        escapes.append(candidate)
    assert escapes, "三条腿都走不通的话，字面量钉就是空转：这一枚要现交出走得通的那几版"

    # 第二条腿（R664 新增）：两本账一起清还能走得通的话，改口账就只是装饰 —— 走不通才是对的。
    both: list = []
    for candidate in _git_output("log", "--format=%h", "-8", "--", CONTRACT_REL).split():
        if candidate == FROZEN_BASE:
            continue
        try:
            assert_history_matches_ledger(
                base_text=base_contract_text(candidate), current_text=current, ledger=(),
                expected_count=0, rewords=(), expected_reword_count=0
            )
        except AssertionError:
            continue
        both.append(candidate)
    #: 🔴 R719 改形（10-06）：契约是**只往文末追加**的那本，所以「最新版的上一版」天然满足
    #: 「基点＋空账＝它自己」，纯追加的祖先会稳定走进 both。上一班把这一格写成 assert not both，
    #: 于是它随每一笔合法追加变红——那是一条不许有人动笔的账，不是牙。牙在别处：
    #: 走进 both 的候选**必须是现盘的真前缀**（纯追加的祖先），只要有一枚不是前缀，
    #: 就说明「两本账一起清」真能掩盖一次原地改口——那一枚才是本刀要抓的罪证。
    for candidate in both:
        assert current.startswith(base_contract_text(candidate)), (
            "两本账一起清就走得通，而 %s 不是现盘的纯追加祖先（原地改过口的历史区被洗白了）" % candidate)
    #: 第二枚牙：把尺按在册基点与现盘整跑一遍，账与枚数门全清成零 ⇒ 必须当场红，
    #: 而且红句要点名「契约的历史在差异账之外被动过」。这一格不许随追加变绿。
    with pytest.raises(AssertionError) as pinned:
        assert_history_matches_ledger(ledger=(), expected_count=0,
                                      rewords=(), expected_reword_count=0)
    assert "契约历史与具名账（差异 ＋ 改口）对不上" in str(pinned.value), str(pinned.value)

    source = _own_source()
    assert _literal_pin_problems(source) == [], _literal_pin_problems(source)
    moved = source.replace('FROZEN_BASE = "a7ac040"', 'FROZEN_BASE = "HEAD"', 1)
    assert any("把基点前移来灭红" in line for line in _literal_pin_problems(moved)), moved
    zeroed = source.replace("EXPECTED_DIFFERENCES_TODAY = 1", "EXPECTED_DIFFERENCES_TODAY = 0", 1)
    assert any("枚数门" in line for line in _literal_pin_problems(zeroed)), zeroed
    zeroed_rewords = source.replace("EXPECTED_REWORDS_TODAY = 1", "EXPECTED_REWORDS_TODAY = 0", 1)
    assert any("改口枚数门" in line for line in _literal_pin_problems(zeroed_rewords)), zeroed_rewords


def test_counter_evidence_4_a_half_derived_rewrite_reddens(tmp_path, monkeypatch):
    """刀④：新文里还留着「点 py 冒号跟数字」那一形（半截派生）⇒ 必红，那一格明年照样过期。"""
    r630 = _ledger_entry("R630")
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿"

    coord = HAND_COPY_COORD.search(r630.old).group(0)
    number = coord.partition(":")[2]
    stem = "app/common/stage_timing.py"
    anchor = "``%s``" % stem
    assert r630.new.count(anchor) == 1, anchor
    half_new = r630.new.replace(anchor, "``%s:%s``" % (stem, number), 1)
    assert half_new != r630.new and half_new != r630.new.replace(anchor, anchor)

    half = Difference(ticket="R645-刀④", old=r630.old, new=half_new, reason="派生了一半，那一格还带着手抄行号")
    problems = shape_violations(half)
    assert any("半截派生" in line for line in problems), problems
    assert DERIVED_ANCHOR.search(half.new), "派生锚还在：这一刀红的只能是留下的那枚坐标"

    text, _newline = _disk_text_and_newline()
    assert text.count(r630.new) == 1
    shadow = _shadow_copy(tmp_path, lambda body: body.replace(r630.new, half_new, 1))
    monkeypatch.setattr(SELF, "CONTRACT_PATH", shadow)

    with pytest.raises(AssertionError) as info:
        assert_history_matches_ledger(ledger=(half,))
    message = str(info.value)
    assert "半截派生" in message, message
    assert "在差异账之外被动过" not in message, message

    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for name, each in red.items():
        assert "登记的新文在现盘上命中 0 处" in each, (name, each)
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"


def test_counter_evidence_A_an_inplace_reword_without_provenance_reddens(tmp_path, monkeypatch):
    """新刀 A：追加段里来一次没有出处的原地改口 ⇒ 必红；登记了却拿不出单号与凭据纸 ⇒ 也必红。"""
    entry = _reword_entry("R657")
    anchor = "app/api/v1/observability.py::wire_first_text_readout"
    assert entry.new.count(anchor) == 1, anchor
    tampered = entry.new.replace(anchor, "app/api/v1/observability.py::slo_slot_caliber", 1)
    assert tampered != entry.new and tampered.count("\n") == 1, _row_node(tampered)
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿：现盘在账上本来是不红的"

    # 第一条腿：那一格真的在盘上被原地换掉了，改口账却一格没登记。前缀尺管不到追加段，长度腿也照样过，
    # 只有「退回原形必须仍是最近那一版在册契约 ＋ 文末追加」这一条腿咬得住它：红句必须点名「就地消失」。
    unbooked_dir = tmp_path / "unbooked"
    unbooked_dir.mkdir()
    shadow = _shadow_copy(unbooked_dir, lambda body: body.replace(entry.new, tampered, 1))
    shadow_text = normalize_eol(shadow.read_bytes()).decode("utf-8")
    index = shadow_text.find(tampered)
    assert index != -1, _row_node(tampered)
    line = shadow_text.count("\n", 0, index) + 1
    monkeypatch.setattr(SELF, "CONTRACT_PATH", shadow)

    with pytest.raises(AssertionError) as vanished:
        assert_history_matches_ledger()
    message = str(vanished.value)
    assert "不许就地消失" in message, message
    assert "在差异账之外被动过" not in message, "那一格在追加段里：前缀尺本来就管不到它，这一刀只能由追加段那一腿咬"
    assert "第 %d 行" % line in message, (line, message)

    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for each in red.values():
        assert "不许就地消失" in each, each

    # 第二条腿：改口登记在册，出处拿不出来 —— 没有单号，或凭据纸不存在，各自当场红。
    nameless = Reword(ticket="", old=entry.old, new=entry.new, reason=entry.reason, evidence=entry.evidence)
    assert any("必须在账面点名单号" in each for each in reword_provenance_problems(nameless)), nameless
    orphan = Reword(
        ticket=entry.ticket, old=entry.old, new=entry.new, reason=entry.reason,
        evidence="docs/testing/r664-这一张凭据纸不存在-2026-10-05.md",
    )
    assert any("凭据纸不存在" in each for each in reword_provenance_problems(orphan)), orphan
    with pytest.raises(AssertionError) as unattributed:
        assert_history_matches_ledger(rewords=(orphan,))
    got = str(unattributed.value)
    assert "没有出处" in got and "凭据纸不存在" in got, got
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"


def test_counter_evidence_B_a_reword_disguised_as_a_pure_append_reddens(tmp_path, monkeypatch):
    """新刀 B：把一次原地改口伪装成纯追加（补一行空行撑长度）⇒ 必红；把「旧行 ＋ 一行空行」登记成改口 ⇒ 形状尺拒。"""
    entry = _reword_entry("R657")
    assert entry.new.endswith(" |\n"), entry.new[-4:]
    shorter = entry.new[:-120] + " |\n"
    assert len(shorter) < len(entry.new) and shorter.count("\n") == 1, _row_node(shorter)
    assert _row_node(shorter) == _row_node(entry.new), _row_node(shorter)
    before = _disk_sha()
    assert not _red(_run_r354_nails()), "正控先绿"
    text, _newline = _disk_text_and_newline()

    # 第一条腿（账面侧）：拿「旧行 ＋ 一行空行」当改口登记 —— 那一形其实是追加，形状尺当场拒。
    disguised_entry = Reword(
        ticket=entry.ticket, old=entry.old, new=entry.old + "\n", reason=entry.reason, evidence=entry.evidence
    )
    shape = reword_shape_violations(disguised_entry)
    assert any("文末追加伪装成改口" in each for each in shape), shape
    with pytest.raises(AssertionError) as refused:
        assert_history_matches_ledger(rewords=(disguised_entry,))
    refused_message = str(refused.value)
    assert "这形状不收" in refused_message and "文末追加伪装成改口" in refused_message, refused_message

    # 正控：只补一行空行、账一字不动 —— 那是正当的文末追加，尺必须仍是绿的（蒙混骗得过长度腿是预期内的）。
    pad_dir = tmp_path / "only-pad"
    pad_dir.mkdir()
    padded = _shadow_copy(pad_dir, lambda body: body + "\n")
    monkeypatch.setattr(SELF, "CONTRACT_PATH", padded)
    account = assert_history_matches_ledger()
    assert account.violations == (), account.violations
    assert len(account.current_text) > len(text), "补一行空行没能把长度撑起来：这一刀的蒙混前提不成立"

    # 第二条腿（盘上侧）：改口就地做了、账上没登记，文末再补一行空行装作「我只长了文末」。
    both_dir = tmp_path / "pad-and-reword"
    both_dir.mkdir()
    shadow = _shadow_copy(both_dir, lambda body: body.replace(entry.new, shorter, 1) + "\n")
    monkeypatch.setattr(SELF, "CONTRACT_PATH", shadow)
    with pytest.raises(AssertionError) as disguised:
        assert_history_matches_ledger()
    message = str(disguised.value)
    assert "不许就地消失" in message, message
    assert "没长东西" not in message, "长度腿被一行空行蒙混过去是预期内的：救场只有追加段那一条腿"
    assert "在差异账之外被动过" not in message, message

    red = _red(_run_r354_nails())
    assert len(red) == 2, red
    for each in red.values():
        assert "不许就地消失" in each, each
    assert _disk_sha() == before, "刀动到了盘上那枚禁区文件"
