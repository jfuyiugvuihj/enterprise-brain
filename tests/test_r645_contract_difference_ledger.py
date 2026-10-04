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

四把刀（每把先跑正控；全部只拿内存副本与 `tmp_path` 影子端判，盘上契约一字节不动）：
刀① 账外手改历史区一个标点 ⇒ 两枚钉都红，红句点名派生出来的位置（字符位与行号）；
刀② 往账里塞一枚「把一句结论换掉」的改写 ⇒ 必红，并说清这形状为什么不收；加进真账则枚数一起报；
刀③ 把 `FROZEN_BASE` 换成较新的版本（本刀直接用 HEAD，不抄 sha）⇒ 两枚钉红、基点字面量钉也红；
刀④ 新文里留一枚手抄坐标（半截派生）⇒ 必红，理由就是那一格仍然会过期。

🔴 两枚钉同判据：`test_the_current_contract_is_the_base_plus_an_appendage` 与
`test_the_appendage_deletes_nothing_and_adds_exactly_one_section` 都只走本文件这一把尺，谁也不许留着自家的
前缀等式（那等于给它开后门）—— 这一条沿 AST 现查，见 `test_the_two_r354_nails_read_this_same_book`。
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


class Difference(NamedTuple):
    """账上一枚差异：立案号、逐字旧文、逐字新文、为什么收它。

    🔴 字段面里没有「起点／终点」那种格子：位置一律由 `audit_history()` 现派生。
    """

    ticket: str
    old: str
    new: str
    reason: str


class Record(NamedTuple):
    """派生出来的那一格：登记的逐文字对上了基点与现盘的哪一段。"""

    ticket: str
    base_start: int
    base_end: int
    current_start: int
    current_end: int
    base_line: int
    current_line: int


class Account(NamedTuple):
    """一次对账的全部现场：两侧原文、拼接出来的「历史应当长这样」、逐枚差异、逐条红。"""

    base_text: str
    current_text: str
    expected_prefix: str
    records: tuple
    violations: tuple

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


def audit_history(base_text: str, current_text: str, ledger: tuple) -> Account:
    """把「前缀逐字节相同」这条不变式按差异账走一遍，交回逐枚派生位置与逐条红。"""
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

    if not current_text.startswith(expected):
        index = _first_difference(expected, current_text)
        violations.append(
            "契约的历史在差异账之外被动过：现盘第 %d 字符（第 %d 行）起与「基点 ＋ 账上 %d 枚登记」的拼接不同，"
            "对应基点第 %d 字符；账上应是 %r，现盘是 %r"
            % (index, current_text.count("\n", 0, index) + 1, len(ledger), _base_anchor(anchors, index),
               _window(expected, index), _window(current_text, index))
        )
    if len(current_text) <= len(expected):
        violations.append(
            "契约没长东西：现盘 %d 字符 <= 拼接后的历史 %d 字符，本单一格都没往文末追加" % (len(current_text), len(expected))
        )

    return Account(base_text, current_text, expected, tuple(records), tuple(violations))


def _base_anchor(anchors: list, index: int) -> int:
    """拼接文本里的某一枚字符位，对应回基点的第几字符位（红句要点名的是「历史上那一格」的位置）。"""
    for start, length, base_start in anchors:
        if start <= index < start + length:
            return base_start + (index - start)
    return index


def assert_history_matches_ledger(base_text: str = None, current_text: str = None,
                                  ledger: tuple = None, expected_count: int = None) -> Account:
    """判据⑦ 唯一那把尺（r354 两枚钉共用）：现盘 == 基点 ＋ 具名差异账，且枚数恰好今天那一本。"""
    base = base_contract_text() if base_text is None else base_text
    current = current_contract_text() if current_text is None else current_text
    book = CONTRACT_DIFFERENCES if ledger is None else tuple(ledger)
    want = EXPECTED_DIFFERENCES_TODAY if expected_count is None else expected_count

    account = audit_history(base, current, book)
    problems = list(account.violations)
    if len(book) != want:
        problems.append("差异账的枚数不对：账上登记 %d 枚，今天应当恰好 %d 枚（多一枚少一枚都红）" % (len(book), want))
    if len(account.records) != want:
        problems.append(
            "派生出来的差异枚数不对：账上登记 %d 枚、能在基点定位的 %d 枚，今天应当恰好 %d 枚"
            % (len(book), len(account.records), want)
        )
    if problems:
        raise AssertionError(
            "契约历史与具名差异账对不上（%d 条）：\n  · %s" % (len(problems), "\n  · ".join(problems))
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
    return rows# ------------------------------------------------------------------ 一本账只许有一份

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
    """尺的两枚字面量：基点 `a7ac040` 与枚数门 `1`。它们一被挪走，红句就交回来。

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
# ------------------------------------------------------------------ 四把反证刀

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
    """刀③：把尺的基点从 `a7ac040` 换成较新的一版 ⇒ 必红；前移基点灭红由字面量钉常驻挡着。"""
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

    source = _own_source()
    assert _literal_pin_problems(source) == [], _literal_pin_problems(source)
    moved = source.replace('FROZEN_BASE = "a7ac040"', 'FROZEN_BASE = "HEAD"', 1)
    assert any("把基点前移来灭红" in line for line in _literal_pin_problems(moved)), moved
    zeroed = source.replace("EXPECTED_DIFFERENCES_TODAY = 1", "EXPECTED_DIFFERENCES_TODAY = 0", 1)
    assert any("枚数门" in line for line in _literal_pin_problems(zeroed)), zeroed


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