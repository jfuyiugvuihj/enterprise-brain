# -*- coding: utf-8 -*-
"""R478 常驻闸：已结案的闸门号不许当占位理由用。

病（现读自基点 2ba2bc2）：「app/**」里有一批文字把一件**没人做的事**挂在**一枚已经结案的闸门号**上，
读起来像「有人正拿着」。H13 已于 2026-09-28 裁定＝甲（出处
「docs/handoff/2026-09-17-human-gates.md」最后一节「H13 结案 ＋ A1/A3 裁定」；口径写进契约
「docs/api/contract-v1.md」的「## R467」节），所以「等业主定」这个形状从那天起就是假话。其中最重的两枚
不是注释而是对外可见的串：「MAX_CLEARANCE_NOTE」逐字进注册回执与应用列表的响应体，
「ApplicationRegisterRequest.max_clearance」那枚 description= 逐字进 OpenAPI。

🔴 已结案名单从闸门清单**现读**，本件不抄死表——死表正是本单要治的病。读法：一行里同时出现
「H<数字>」与结案标记（结案 / 裁定＝ / 🟢）即算结案。名单读空就是尺子瞎了，本件当场红。

尺子分两档（判据①明写不许只搜 H13 字样——上一席就是靠窄尺漏掉「没裁的维度」这种不带号的写法）：
  甲档 带闸门号：一枚已结案的号，同一行里跟着「未裁／待业主／undecided／pending the owner／
        open decision」这一族字样，正反两种语序都量；
  乙档 不带闸门号的同族写法：「业主未裁」「没裁的维度」「口径等闸门」「替业主裁」「unratified」
        「pending the owner」这些形状。
另有一格丙：任何一枚已结案的号被写进注释块或字符串字面量，那枚单元必须自己点名它已结案——
光秃秃一枚号挂在理由里，就是假指针的雏形。

豁免白名单（CLOSURE_CELLS）：一枚「单元」里点名了结案，它说到的「未裁」就是历史叙述或否定句，
不算假指针。单元粒度有意分开：注释块与文档串按**整块**豁免（一段话里后面的结案陈述覆盖前面的
历史叙述，「app/common/permissions.py」的 R357 那段正是这个形状），而对外可见的字符串字面量只许
自证——隔壁注释写得再清楚，也不会替响应体里那句话背书。
🔴 有一把反证刀把「结案」这一格从白名单里摘掉（本件里是
test_counter_evidence_dropping_the_closure_cell_is_not_an_empty_ruler）：摘掉之后尺子必须当场多报，
报不出来这枚尺子就是空转的。

写域外的三处同族遗留（OUT_OF_DOMAIN_LEDGER）登记在这儿而不是藏起来，且每一枚都必须**今天仍然
命中**：修好了不摘牌，本件就红——防止白名单长成第二张死表。

判据①要的「同族写法」不是本件新造一把尺：在册钉 tests/test_r472_h13_closed_wording.py 那四枚
正则本件照抄，只把 H13 放宽成任意一枚闸门号，并常驻核对「本件的形状集必须是它的超集」（基线与
盘上各量一遍）——上一席漏掉的正是这一格。

断言格：甲 假指针在 app/** 零命中、名单现读、丙格（提到已结案的号必须自己点名结案）、尺子必须是
r472 那把的超集、基线九格病仍要读得出（事故 #83：刀照基线造）；乙 两枚对外可见的串必须逐字自白
「今天没有任何路径比较这枚字段、注册值不改变任何结果」并点名出处——既不许写回 waiting 形状，也
不许写成「已经生效」（那是 R479 的账）；丙 契约文末那一节的围栏形状。反证四刀各咬一格：刀一
MAX_CLEARANCE_NOTE 回插基点旧句（引文从基点 commit 现抠，零手抄）；刀二 description= 回插基点
旧句；刀三 把两枚串改写成「检索与预览都按这一档过滤」的假实现口吻 ⇒ 判据③要求的那两枚钉当场红；
刀四 摘掉白名单「结案」那一格 ⇒ 尺子必须多报一枚。
"""

from __future__ import annotations

import ast
import re
import subprocess
from contextlib import contextmanager

import pytest
from fastapi import FastAPI

from app.api.v1 import open_platform as open_platform_routes
from app.common import audit, open_platform
from app.common.open_platform import clear_app_registry, configure_app_store
from tests import _temp_edit_overlay as overlay
from tests import test_r467_classification_default_is_ratified as r467
from tests import test_r472_h13_closed_wording as r472
from tests import test_r78_unearned_claims as r78

REPO = overlay.REPO
APP_DIR = REPO / "app"
GATES_DOC_REL = "docs/handoff/2026-09-17-human-gates.md"
R78_REL = "tests/test_r78_unearned_claims.py"
NOTE_REL = "app/common/open_platform.py"
DESCRIPTION_REL = "app/api/v1/open_platform.py"
CONTRACT_REL = "docs/api/contract-v1.md"
SECTION_HEAD = "## R478 "
BASE = "2ba2bc2"
DQ = chr(34)

GATE_ID = re.compile("(?<![0-9])H([0-9]+)")
CLOSE_MARK = re.compile("(结案|裁定[=＝]|🟢)")

#: 甲档：形状里必须带着一枚闸门号，正反两种语序都量（「H13 未定口径」与「业主口径亦未裁（H13）」都得咬住）。
TIER_A_PATTERNS = (
    "(?<![0-9])H[0-9]+.{0,40}(未裁|未定|未决|待裁|待业主|待批|待定|还悬|尚未|没裁|没定|裁完)",
    "(?<![0-9])H[0-9]+.{0,60}(pending|undecided|unratified|awaiting|unruled|still with|"
    "open decision|the owner's ruling|owner's to make|until the owner|once the owner rules)",
    "(pending|undecided|unratified|awaiting|open decision|the owner's ruling|owner's to make|"
    "until the owner).{0,60}(?<![0-9])H[0-9]+",
    "(未裁|未定|未决|待裁|待业主|没裁|尚未裁|口径没裁)[^.。]{0,20}(?<![0-9])H[0-9]+",
    "(等|待)[ ]*(?<![0-9])H[0-9]+",
)
#: 乙档：同族但不带闸门号——上一席漏掉的就是这一格。
TIER_B_PATTERNS = (
    "(业主|口径)(尚未|未|没)(裁|定|拍板)",
    "(未|没)裁的(维度|口径)",
    "口径(没裁|未裁|未定|待定|等闸门)",
    "(待|等)[ ]*业主[ ]*(裁|定|裁定|拍板|一句话)",
    "替业主裁",
    "unratified",
    "undecided",
    "owner-open",
    "open decision",
    "pending[ ]the[ ]owner",
    "the[ ]owner's[ ]ruling",
    "owner's[ ]to[ ]make",
    "awaiting[ ]the[ ]owner",
    "until[ ]the[ ]owner",
    "once[ ]the[ ]owner[ ]rules",
)
#: 白名单：一格里两种语序都算，且**必须点着这枚闸门号**才算——一句关于别的裁定的话，
#: 不许替这一枚号开脱（R478 现读：改前的 rbac 文档串正是靠「R17 裁定＝甲」蒙过宽白名单的）。
CLOSURE_CELLS = (
    ("cell-cn-jiean", ("{gate}[^.。]{0,40}结案", "结案[^.。]{0,40}(?<![0-9]){gate}")),
    ("cell-cn-dinga", ("{gate}[^.。]{0,40}裁定[=＝]甲", "裁定[=＝]甲[^.。]{0,40}(?<![0-9]){gate}")),
    ("cell-en-closed", ("{gate}[^.]{0,40}(?<![A-Za-z-])closed",
                          "(?<![A-Za-z-])closed[^.]{0,40}(?<![0-9]){gate}")),
)
#: 🔴 R478 写域之外的同族遗留：登记给下一班，不藏。台账里的每一枚今天必须仍然命中。
OUT_OF_DOMAIN_LEDGER = (
    ("app/api/v1/data.py", "unratified",
     "写域之外：本单只治 app/** 里点名已结案闸门号的四处；这一维的拒绝今天由 "
     "clearance_insufficient 与 resource_scope_missing 两枚在册码承担，改口口径同契约「## R472」节"),
    ("app/api/v1/chat.py", "awaiting the owner",
     "R464（Ramanujan）在途写域，碰一枚就死；这一句说的是要动 migrations 的另一张单，"
     "不挂在已结案闸门号上"),
    ("app/trace/durability.py", "undecided",
     "写域之外，且说的不是密级：那枚 undecided 讲的是审计事件的文件序号还没有被表确认"
     "（R263），与任何一枚闸门号无关；本单的乙档尺子不带闸门号也会咬到它，故登记在此"),
)
#: 两枚对外可见的串今天必须说的事实（r78 的换锚与本件的同步钉共用这一份清单）。
NOTE_CONFESSION = (
    "ceiling only",
    "open_audit_principal",
    "min(role tier, max(1, registered))",
    "can never raise one",
    "fail closed to level 1",
    "grants no access",
    "contract-v1.md, section r482",
    "closed 2026-09-28",
)
DESCRIPTION_CONFESSION = (
    "ceiling, not a grant",
    "open_audit_principal",
    "min(role tier, max(1, this figure))",
    "can narrow that subject",
    "fail closed to level 1",
    "grants no access",
    "revokes none",
    "contract-v1.md, section r482",
)
WAITING_WORDS = ("pending", "undecided", "unratified", "awaiting", "open decision", "owner-open")


# ==================== 读数把手 ====================

def closed_gates():
    """已结案闸门名单：逐行现读闸门清单，不抄死表。"""
    text = overlay.authoritative_text(GATES_DOC_REL).replace(chr(13), "")
    out = set()
    for line in text.splitlines():
        if CLOSE_MARK.search(line):
            out.update("H" + gid for gid in GATE_ID.findall(line))
    return frozenset(out)


def _app_files():
    found = []
    for candidate in APP_DIR.rglob("*.py"):
        if not candidate.is_file() or "__pycache__" in candidate.parts:
            continue
        found.append(candidate.relative_to(REPO).as_posix())
    return sorted(found)


def _units(rel, text):
    """把一份源码切成「单元」：连续注释块 + 每一枚字符串字面量（相邻字面量 AST 里折成一枚）。"""
    plain = text.replace(chr(13), "")
    lines = plain.splitlines()
    out, buf = [], []
    for num, line in enumerate(lines, 1):
        if line.strip().startswith("#"):
            buf.append((num, line.strip().lstrip("#").strip()))
        elif buf:
            out.append(("comment", buf))
            buf = []
    if buf:
        out.append(("comment", buf))
    try:
        tree = ast.parse(plain)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                start = node.lineno
                end = getattr(node, "end_lineno", start) or start
                out.append(("literal", [(n, lines[n - 1]) for n in range(start, min(end, len(lines)) + 1)]))
    return out


def _certainly_closed(joined, cells):
    """这枚单元里，哪些闸门号被明明白白说成了已结案。"""
    stated = set()
    for gate in {"H" + gid for gid in GATE_ID.findall(joined)}:
        for _name, templates in cells:
            if any(re.search(template.replace("{gate}", gate), joined) for template in templates):
                stated.add(gate)
                break
    return stated


def _ledgered(hit):
    return any(
        hit["rel"] == rel and token.lower() in hit["matched"].lower()
        for rel, token, _why in OUT_OF_DOMAIN_LEDGER
    )


def scan_text(rel, text, cells=CLOSURE_CELLS, roster=None):
    """一份源码里的假指针读数（已按白名单与台账过滤）。"""
    roster = closed_gates() if roster is None else roster
    hits = []
    for kind, unit in _units(rel, text):
        joined = " ".join(t for _, t in unit)
        stated = _certainly_closed(joined, cells)
        for num, line in unit:
            for index, pattern in enumerate(TIER_A_PATTERNS):
                found = re.search(pattern, line)
                if not found:
                    continue
                ids = {"H" + gid for gid in GATE_ID.findall(found.group(0))} & roster
                if ids and (ids - stated):
                    hits.append({"rel": rel, "line": num, "kind": kind, "tier": "A",
                                 "pattern": index, "matched": found.group(0)})
                break
            else:
                for index, pattern in enumerate(TIER_B_PATTERNS):
                    found = re.search(pattern, line, re.I)
                    if found:
                        mentioned = {"H" + gid for gid in GATE_ID.findall(joined)} & roster
                        if mentioned and not (mentioned - stated):
                            continue
                        hits.append({"rel": rel, "line": num, "kind": kind, "tier": "B",
                                     "pattern": index, "matched": found.group(0)})
                        break
    return hits


def raw_scan_app(cells=CLOSURE_CELLS):
    """全量读数，不过台账：台账那一格必须自己证明它今天仍然命中。"""
    hits = []
    for rel in _app_files():
        hits.extend(scan_text(rel, overlay.authoritative_text(rel), cells=cells))
    return hits


def scan_app(cells=CLOSURE_CELLS):
    return [hit for hit in raw_scan_app(cells=cells) if not _ledgered(hit)]


def bare_gate_mentions(cells=CLOSURE_CELLS):
    """丙格：提到一枚已结案的号，但那枚单元没说一句它结案了。"""
    roster = closed_gates()
    out = []
    for rel in _app_files():
        text = overlay.authoritative_text(rel)
        for kind, unit in _units(rel, text):
            joined = " ".join(t for _, t in unit)
            ids = {"H" + gid for gid in GATE_ID.findall(joined)} & roster
            if not ids:
                continue
            if ids - _certainly_closed(joined, cells):
                out.append({"rel": rel, "line": unit[0][0], "kind": kind, "ids": sorted(ids)})
    return out


def _base_text(rel):
    """基点那份字节：反证刀必须照基线造，不照改后的自己造。"""
    raw = subprocess.run(["git", "show", BASE + ":" + rel], cwd=str(REPO),
                         capture_output=True, check=True).stdout
    return raw.decode("utf-8").replace(chr(13), "")


def _note_text():
    return str(open_platform.MAX_CLEARANCE_NOTE)


def _description_text():
    fields = open_platform_routes.ApplicationRegisterRequest.model_fields
    return str(fields["max_clearance"].description)


def _balanced_span(text, anchor):
    """从 anchor（以左括号收尾）起，回它整个平衡括号表达式的 [start, end)。"""
    start = text.index(anchor)
    depth = 0
    index = start + len(anchor) - 1
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return start, index + 1
        elif char == DQ or char == chr(39):
            index += 1
            while index < len(text) and text[index] != char:
                index += 1
        index += 1
    raise AssertionError("括号不平衡：" + anchor)


class _SpanEdit(overlay.ShadowEdit):
    """一扇反证窗：把一枚对外可见的字面量整段换成假话，变异只落影子根并 exec 回模块。"""

    tag = "r478"
    execs_module = True

    def __init__(self, rel, anchor, body_lines, closer):
        super().__init__(REPO / rel)
        self.anchor = anchor
        self.body = body_lines
        self.closer = closer

    def mutate(self, text):
        if text.count(self.anchor) != 1:
            raise AssertionError("反证刀的锚不唯一：" + self.anchor)
        start, end = _balanced_span(text, self.anchor)
        nl = chr(10)
        mutant = text[:start] + self.anchor + nl + nl.join(self.body) + nl + self.closer + text[end:]
        try:
            compile(mutant, "<r478-counter-evidence>", "exec")
        except SyntaxError as exc:
            raise AssertionError("反证刀产物编译不过（它红的是语法不是判据）：" + str(exc)) from exc
        return mutant


#: 这枚登记值在源码里的两种存在形状：属性（数据类那一行）与字典键（``asdict`` 摊平之后）。
FIGURE_KEY = "max_clearance"
_LOOKUP_METHODS = frozenset({"get", "pop", "setdefault"})


def _figure_key_read_nodes(tree):
    """把「以字典键的形态读走这枚登记值」的形状挑出来：``row["max_clearance"]`` 与 ``row.get("max_clearance", ...)``。

    R482 加宽了这一格。原来的尺子只认 ``ast.Attribute``（``record.max_clearance``），而执法点
    ``open_audit_principal`` 拿到的是 ``asdict`` 摊平之后的字典，取的是键——不加宽，这格对唯一
    那枚真正按这枚字段行事的路径是瞎的，「读数面」就退化成一张自证的空表。
    字典字面量里那枚同名输出键（``"max_clearance": value``）不算读数：那是发布，不是取用。
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == FIGURE_KEY:
                out.append(node.slice)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _LOOKUP_METHODS and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value == FIGURE_KEY:
                    out.append(first)
    return out


def _function_owners(tree):
    """节点 -> 它站在哪一枚函数里：读数报的是路径与函数名，行号会漂，名字不会。"""
    owners = {}
    for owner in ast.walk(tree):
        if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(owner):
                owners[id(child)] = owner.name
    return owners


def _max_clearance_reads():
    """AST 现读：全树里谁把这枚登记值取出来用——属性取用与字典键取用两种形状都量。"""
    out = []
    for rel in _app_files():
        tree = ast.parse(overlay.authoritative_text(rel))
        owners = _function_owners(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == FIGURE_KEY:
                out.append((rel, owners.get(id(node), "<module>"), node.lineno))
        for node in _figure_key_read_nodes(tree):
            out.append((rel, owners.get(id(node), "<module>"), node.lineno))
    return out


def _max_clearance_comparisons():
    """读数有没有走进判定结构——那是行为，不是文字。

    R482 之后判定这枚字段的写法是一枚 ``min``（封顶只降不升就是这个形状），所以判定面从
    「比较 / if / 断言」加宽到这两枚内建函数：不加宽，「把取小换成取大」那一刀就量不出来，
    而判据⑤要求的正是那一刀。
    """
    verdicts = (ast.Compare, ast.If, ast.IfExp, ast.Assert)
    out = []
    for rel in _app_files():
        tree = ast.parse(overlay.authoritative_text(rel))
        owners = _function_owners(tree)
        held = {id(node) for node in _figure_key_read_nodes(tree)}
        for node in ast.walk(tree):
            weighing = (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in {"min", "max"})
            if not weighing and not isinstance(node, verdicts):
                continue
            for child in ast.walk(node):
                if (isinstance(child, ast.Attribute) and child.attr == FIGURE_KEY) or id(child) in held:
                    label = node.func.id if weighing else type(node).__name__
                    out.append((rel, owners.get(id(node), "<module>"), label))
                    break
    return out



def _base_note():
    """基点那枚 MAX_CLEARANCE_NOTE 的原文：刀一律照基线造，零手抄。"""
    for node in ast.parse(_base_text(NOTE_REL)).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "MAX_CLEARANCE_NOTE"
                for target in node.targets):
            return str(node.value.value)
    raise AssertionError("基点里找不到 MAX_CLEARANCE_NOTE")


def _base_description():
    """基点 OpenAPI 里那枚 description 的原文：同上，零手抄。"""
    for node in ast.walk(ast.parse(_base_text(DESCRIPTION_REL))):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                if "Registered only" in str(keyword.value.value):
                    return str(keyword.value.value)
    raise AssertionError("基点里找不到那枚 description")


def _one_line_literal(value, indent):
    """把一枚字符串摊成源文件里那种字面量行（长度不重要：产物只进影子根）。"""
    assert DQ not in value, "弹药用不了带双引号的原文，得换转义写法"
    return [indent + DQ + value + DQ]


def _own_the_open_platform_surfaces(monkeypatch):
    """与 r78 的 autouse 夹具同一套卫生：注册表与审计都是进程级状态，进出都得清。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    monkeypatch.setenv("AUDIT_PERSISTENCE", "disabled")
    r78.audit.reset_audit_storage()
    configure_app_store("")
    clear_app_registry()
    r78.audit.clear_audit_events()


def _published_description():
    """从「重新 exec 过的路由模块 + 重新生成的对外文档」里取那枚 description。

    description 是在模型类创建时烘进 JSON schema 的，改活对象改不动；这一刀要量的本来就是
    发布出去的那份文档，所以走重建这条路，而不是拿字符串比着看。
    """
    fresh = FastAPI(title="r478-refutation")
    fresh.include_router(open_platform_routes.apps_router, prefix="/api/v1")
    schema = fresh.openapi()
    return schema["components"]["schemas"]["ApplicationRegisterRequest"]["properties"][
        "max_clearance"]["description"]



# ==================== 读数渲染与状态卫生 ====================

def _render(hits):
    return "; ".join(h["rel"] + ":" + str(h["line"]) + " " + h["tier"] + "档 " + repr(h["matched"])
                    for h in hits[:8])


def _collapse(value):
    return " ".join(value.split())


@contextmanager
def _r78_state(monkeypatch):
    """借 r78 那套进程级卫生：应用注册表与审计日志都是模块状态，进出都必须清。"""
    _own_the_open_platform_surfaces(monkeypatch)
    try:
        yield
    finally:
        configure_app_store("")
        clear_app_registry()
        audit.clear_audit_events()
        monkeypatch.undo()
        audit.reset_audit_storage()


def _reds(fn, why):
    """反证刀的下法：变异落下去，被指的钉必须当场红——不红就是刀空转（事故 #83）。"""
    try:
        fn()
    except AssertionError:
        return
    pytest.fail(why)


def _stays_green(fn, why):
    """刀的控制格：变异没落下去之前，被指的钉必须是绿的——否则红的是锤子不是钉子。"""
    try:
        fn()
    except AssertionError as exc:
        pytest.fail(why + "（窗外就该绿的，读数：" + str(exc)[:120] + ")")


# ==================== 对外文档的读数把手 ====================

FENCE = chr(96) * 3


def _fresh_app():
    """按「一个新进程今天会发布什么」重建对外文档：模块被 exec 成变异版时，这里的就是变异版。"""
    built = FastAPI(title="r478-counter-evidence")
    built.include_router(open_platform_routes.router, prefix="/api/v1")
    built.include_router(open_platform_routes.apps_router, prefix="/api/v1")
    return built


def _contract_sections(text):
    """契约按「## 」切节，回 [(节名, 节正文), ...]：围栏内外的字都留在正文里。"""
    out, head, buf = [], None, []
    for line in text.split(chr(10)):
        if line.startswith("## "):
            if head is not None:
                out.append((head, chr(10).join(buf)))
            head, buf = line, []
        else:
            buf.append(line)
    if head is not None:
        out.append((head, chr(10).join(buf)))
    return out


def _r478_section():
    """契约文末那一节，按围栏切成「活散文」与「逐字引文」两半（口径同在册钉 r467）。"""
    text = overlay.authoritative_text(CONTRACT_REL).replace(chr(13), "")
    named = [(head, body) for head, body in _contract_sections(text) if head.startswith(SECTION_HEAD)]
    assert len(named) == 1, "契约里「" + SECTION_HEAD.strip() + "」命中 " + str(len(named)) + " 处（要求恰好 1 处）"
    head, body = named[0]
    parts = body.split(FENCE)
    prose = " ".join(parts[index] for index in range(0, len(parts), 2))
    fenced = " ".join(parts[index] for index in range(1, len(parts), 2))
    return head, prose, fenced


def _line_hits(rel, text, patterns):
    """逐行原始读数：不带白名单、不带台账——用来对在册钉那把尺子做超集核对。"""
    out = []
    for number, line in enumerate(text.split(chr(10)), 1):
        for index, pattern in enumerate(patterns):
            found = re.search(pattern, line, re.I)
            if found:
                out.append({"rel": rel, "line": number, "pattern": index, "matched": found.group(0)})
                break
    return out


def _line_hits_app(patterns, reader):
    out = []
    for rel in _app_files():
        out.extend(_line_hits(rel, reader(rel), patterns))
    return out


def _disk_text(rel):
    """盘上（窗外）那份字节：与 _base_text 同一口径，去掉 CR。"""
    return overlay.authoritative_text(rel).replace(chr(13), "")


#: 在册钉 r472 那一族尺子（判据①要求「同族写法」，本件的尺子必须是它的超集）：把 H13 放宽成任意一枚闸门号。
INHERITED_PATTERNS = tuple(pattern.replace("H13", GATE_ID.pattern) for pattern in r472.ALL_OPEN_PATTERNS)
#: 本件实际用来扫 app/** 的全部形状（甲档带号 + 乙档不带号）。
ALL_SHAPES = TIER_A_PATTERNS + TIER_B_PATTERNS
#: 基点 2ba2bc2 上现读登记的病格（rel, 行号, 档位）：这枚表是刀的依据，不是名单的死表。
DISEASE_BASELINE = (
    ("app/agents/contracts.py", 340, "A"),
    ("app/api/v1/open_platform.py", 307, "A"),
    ("app/api/v1/open_platform.py", 320, "A"),
    ("app/common/open_platform.py", 61, "B"),
    ("app/common/open_platform.py", 62, "A"),
    ("app/common/open_platform.py", 66, "B"),
    ("app/common/open_platform.py", 71, "B"),
    ("app/common/rbac.py", 130, "A"),
    ("app/documents/catalog.py", 437, "B"),
)
#: 两枚对外可见的串里绝迹的形状：把「没人拿着」说成「已经生效」是同一枚病的另一面（本单明令不做）。
FORBIDDEN_CLAIMS = (
    "is now enforced", "now enforced", "already enforced", "enforced by the",
    "enforces this", "wired into the principal", "接进 principal", "已经生效", "已生效",
)
#: 判据②的凭据（09-29 现读，AST 重取）：全 app/ 里取用这枚登记值的只有三处，全在报告路径里。
REPORT_ONLY_READS = (
    ("app/api/v1/open_platform.py", "register_open_application"),
    ("app/common/open_platform.py", "list_applications"),
)
#: 报告路径那两处一共三枚读数（``register_open_application`` 两枚、``list_applications`` 一枚），
#: 09-29 现读；枚数变了就是有人新长了报告面或者改了参数名，两种都得让格乙报。
REPORTED_READ_COUNT = 3
#: R482 新登记的两处：一处把存进来就读不出的旧行收到最小档，一处拿它给主体封顶。
#: 判定面（``min``）也只在执法点这一枚，格乙那枚钉直接把这条算式对进去。
CEILING_READS = (
    ("app/common/open_platform.py", "_record_from_payload"),
    ("app/common/open_platform.py", "open_audit_principal"),
)
STORE_REBUILD_READS = 1
CEILING_ENFORCEMENT_READS = 1


# ==================== 格甲 · 假指针绝迹 ====================

def test_the_roster_is_read_live_from_the_gate_list():
    """已结案名单必须现读自闸门清单：读空＝尺子瞎了，抄进来的号＝本单要治的死表。"""
    roster = closed_gates()
    assert roster, "闸门清单里读不出任何一枚已结案的号：尺子瞎了，本件无从判断"
    assert "H13" in roster, "清单最后一节写明 H13 结案＝甲，名单却没有它：" + str(sorted(roster))
    absent = [gate for gate in roster if gate not in overlay.authoritative_text(GATES_DOC_REL)]
    assert not absent, "名单里的号在清单上找不到出处（那是抄进来的死表）：" + str(absent)


def test_no_closed_gate_is_written_as_something_someone_is_still_holding():
    """判据①主格：改口之后，app/** 里这类形状必须零命中。"""
    hits = scan_app()
    assert not hits, "app/** 里还有把已结案的闸门号写成「有人正拿着」的形状：" + _render(hits)


def test_every_closed_gate_mention_names_its_closure():
    """丙格：光秃秃一枚已结案的号挂在理由里，就是假指针的雏形。"""
    bare = bare_gate_mentions()
    assert not bare, "提到已结案的号却没说自己已结案的单元：" + "; ".join(
        item["rel"] + ":" + str(item["line"]) + " " + item["kind"] + " " + "/".join(item["ids"])
        for item in bare[:8])


def test_the_ruler_is_a_superset_of_the_registered_nail():
    """判据①：尺子必须是 r472 那一族在册正则的超集；基线上有真病可咬，这格才不空转。"""
    for label, reader in (("baseline", _base_text), ("disk", _disk_text)):
        theirs = set((hit["rel"], hit["line"]) for hit in _line_hits_app(INHERITED_PATTERNS, reader))
        mine = set((hit["rel"], hit["line"]) for hit in _line_hits_app(ALL_SHAPES, reader))
        blind = sorted(theirs - mine)
        assert not blind, "r472 的尺子在" + label + "能报而本件报不出来（窄了）：" + repr(blind[:6])
    assert _line_hits_app(INHERITED_PATTERNS, _base_text), "基线上那把在册尺子一枚都不报：无从对账"


def test_the_ruler_reads_the_disease_it_was_built_for():
    """刀照基线造（事故 #83）：这枚尺子必须在基点那份字节上读出本单登记过的每一格病。"""
    seen = set()
    for rel in _app_files():
        for hit in scan_text(rel, _base_text(rel)):
            seen.add((hit["rel"], hit["line"], hit["tier"]))
    missing = [site for site in DISEASE_BASELINE if site not in seen]
    assert not missing, "尺子在基线上读不出这些登记过的病格（它被改窄了？）：" + repr(missing)


# ==================== 格乙 · 两枚对外可见的串必须如实 ====================

def test_the_registration_receipt_note_confesses_the_measured_fact():
    """MAX_CLEARANCE_NOTE 逐字进注册回执与应用列表的响应体：它必须说清今天没人比较这枚字段。"""
    note = _note_text().lower()
    missing = [phrase for phrase in NOTE_CONFESSION if phrase not in note]
    assert not missing, "注册回执里那句话不再自白这枚事实：" + repr(missing) + "；原文：" + note[:200]
    trips = [word for word in WAITING_WORDS if word in note]
    assert not trips, "对外可见的响应体又把这件没人做的事写成有人正拿着：" + repr(trips)
    claims = [word for word in FORBIDDEN_CLAIMS if word in note]
    assert not claims, "响应体把「没接进判定」说成「已生效」（那是 R479 的账）：" + repr(claims)


def test_the_published_description_confesses_the_measured_fact():
    """description= 逐字进 OpenAPI：客户端读到的必须是同一句自白，而不是一个待裁的闸门。"""
    published = _published_description().lower()
    assert _collapse(published) == _collapse(_description_text().lower()), (
        "发布出去的文档与模型里的原文不是同一句：钉的断言面已经不在对外那一份上")
    missing = [phrase for phrase in DESCRIPTION_CONFESSION if phrase not in published]
    assert not missing, "OpenAPI 里那句话不再自白这枚事实：" + repr(missing) + "；原文：" + published[:200]
    trips = [word for word in WAITING_WORDS if word in published]
    assert not trips, "OpenAPI 又把这件没人做的事写成有人正拿着：" + repr(trips)
    claims = [word for word in FORBIDDEN_CLAIMS if word in published]
    assert not claims, "OpenAPI 把「没接进判定」说成「已生效」（那是 R479 的账）：" + repr(claims)


def test_the_stored_figure_is_still_read_only_for_reporting():
    """判据②的凭据常驻化：读数面与判定面都必须在册，且与常量、两句对外串同一口径。

    名字里的 ``read_only_for_reporting`` 是 R478 的口径（那时全 ``app/`` 只有报告路径取用这枚
    登记值，判定结构零枚），R482 起作废，本钉改量今天的三格：报告读数仍是原来那两处、判定这枚
    字段的表达式恰好一枚且写作 ``min``、常量与 effect 与对外两句同源。尺子在钉之上一起加宽
    （字典键取用与 ``min``/``max`` 现在都算），所以「摘掉执法那一格」与「取小换成取大」两刀都
    有地方落。断言一枚没少，只是从「零枚判定」换成「恰好这一枚判定」。
    """
    reads = _max_clearance_reads()
    sites = sorted(set((rel, owner) for rel, owner, _line in reads))
    assert sites == sorted(REPORT_ONLY_READS + CEILING_READS), (
        "取用这枚登记值的路径变了（现读 " + str(sites) + "）——对外那句话与注释都得跟着改，不许只改一边")
    assert len(reads) == REPORTED_READ_COUNT + STORE_REBUILD_READS + CEILING_ENFORCEMENT_READS, (
        "读数枚数变了：" + repr(reads))
    weighed = _max_clearance_comparisons()
    assert weighed == [("app/common/open_platform.py", "open_audit_principal", "min")], (
        "判定这枚登记值的表达式不再是执法点那一枚 min：" + repr(weighed) + "——封顶的算法长出第二处了")
    assert open_platform.MAX_CLEARANCE_ENFORCED is True, (
        "执法点在拿这枚字段给主体封顶，常量还说自己没在执行：口径分裂")
    assert open_platform.MAX_CLEARANCE_EFFECT == "ceiling_only", "对外那句 effect 变了"


def test_the_ledger_entries_still_bite():
    """台账不许长成第二张死表：每一枚登记都必须在今天的盘上仍然命中，也不许伸进本单写域。"""
    raw = raw_scan_app()
    for rel, token, _why in OUT_OF_DOMAIN_LEDGER:
        assert any(hit["rel"] == rel and token.lower() in hit["matched"].lower() for hit in raw), (
            "台账里这枚登记已经不再命中（改好了就摘牌，别留成死表）：" + rel + " / " + token)
    inside = [rel for rel, _token, _why in OUT_OF_DOMAIN_LEDGER if rel in REWORDED_FILES]
    assert not inside, "台账伸进了本单的写域（那些文件里的同族形状只能改口，不能登记）：" + repr(inside)


# ==================== 格丙 · 契约那一节的形状 ====================

def test_the_contract_section_publishes_both_retired_sentences_in_a_fence():
    """两枚退役原串必须逐字留在契约的围栏里，供下一班对账（改口不销毁历史）。"""
    _head, _prose, fenced = _r478_section()
    for quote in (_base_note(), _base_description()):
        assert _collapse(quote) in _collapse(fenced), "退役原句的逐字引文不在围栏里：" + repr(quote[:60])


def test_the_contract_section_holds_the_registered_wording_ruler():
    """判据⑤：围栏外一行都不许出现那几种形状——用的就是在册钉 r467 那把尺子。"""
    _head, prose, _fenced = _r478_section()
    trips = [pattern for pattern in r467.OPEN_QUESTION_PATTERNS if re.search(pattern, prose)]
    assert not trips, "契约 R478 节的活散文里冒出把已结案闸门写成待裁的形状：" + repr(trips)
    assert "作废" in prose and "逐字引" in prose, (
        "本节丢了作废声明与逐字引的口径，下一班会把这两句当成新发现再报一遍")


# ==================== 反证刀（每刀各咬一格；变异只落影子根） ====================

#: 本单改口的五枚文件（台账不许伸进这里，见 test_the_ledger_entries_still_bite）。
REWORDED_FILES = (
    "app/common/rbac.py",
    "app/agents/contracts.py",
    "app/documents/catalog.py",
    NOTE_REL,
    DESCRIPTION_REL,
)
#: 假实现口吻（判据③要求的反证）：把「没人比较」说成「检索与预览都按这一档过滤」。
FAKE_ENFORCEMENT_NOTE = (
    '    "retrieval and preview both filter on this tier: a level 3 application also "',
    '    "reads level 4 chunks, because the Principal carries it."',
)
FAKE_ENFORCEMENT_DESCRIPTION = (
    '            "Enforced today: retrieval and preview both narrow to this tier, so "',
    '            "registering a 5 grants level 5 reads."',
)


def test_counter_evidence_reinserting_the_old_note_goes_red(monkeypatch):
    """刀一：把 MAX_CLEARANCE_NOTE 回插基点那句假话（引文从 2ba2bc2 现抠，零手抄）——咬的是对外响应体那一格。"""
    with _r78_state(monkeypatch):
        _stays_green(r78.test_the_registration_response_labels_the_clearance_it_stores,
                     "刀一的控制格：窗外那枚钉就该是绿的")
        assert not scan_app(), "窗外已经有假指针了，刀一的读数无从归因：" + _render(scan_app())
        with _SpanEdit(NOTE_REL, "MAX_CLEARANCE_NOTE = (",
                       _one_line_literal(_base_note(), "    "), ")"):
            reported = [hit for hit in scan_app() if hit["rel"] == NOTE_REL]
            assert reported, "刀一落下去尺子不报（旧句明明带着 open decision 与闸门号）：尺子是空转的"
            assert any(word in _note_text().lower() for word in WAITING_WORDS), "旧句的 waiting 形状没被量到"
            _reds(r78.test_the_registration_response_labels_the_clearance_it_stores,
                  "刀一落下去 r78 换锚后的钉还是绿的：那枚钉没咬住对外串")
        _stays_green(r78.test_the_registration_response_labels_the_clearance_it_stores,
                     "刀一退出后字节没还原")


def test_counter_evidence_reinserting_the_old_description_goes_red(monkeypatch):
    """刀二：description= 回插基点那句——咬的是发布出去的 OpenAPI 那一格（不是模型里的字）。"""
    with _r78_state(monkeypatch):
        assert not scan_app(), "窗外已经有假指针了，刀二的读数无从归因：" + _render(scan_app())
        with _SpanEdit(DESCRIPTION_REL, "description=(",
                       _one_line_literal(_base_description(), "            "), ")"):
            reported = [hit for hit in scan_app() if hit["rel"] == DESCRIPTION_REL]
            assert reported, "刀二落下去尺子不报：尺子是空转的"
            published = _published_description().lower()
            assert any(word in published for word in WAITING_WORDS), "发布出去的文档没变成旧句：刀没落到对外面"
            assert _base_description().lower() in published, "发布的不是基点那句原文，红就红得没有依据"
            monkeypatch.setattr(r78, "app", _fresh_app())
            _reds(r78.test_the_api_documentation_says_the_same_thing_to_the_client_that_reads_it,
                  "刀二落下去 OpenAPI 换锚后的钉还是绿的：那枚钉没咬住发布面")


def test_counter_evidence_claiming_the_field_is_enforced_goes_red(monkeypatch):
    """判据③：把两枚对外串改写成「检索与预览都按这一档过滤」的假实现口吻 ⇒ 那两枚钉当场红。"""
    with _r78_state(monkeypatch):
        _stays_green(r78.test_the_registration_response_labels_the_clearance_it_stores, "控制格（回执）")
        _stays_green(r78.test_the_api_documentation_says_the_same_thing_to_the_client_that_reads_it,
                     "控制格（发布面）")
        with _SpanEdit(NOTE_REL, "MAX_CLEARANCE_NOTE = (", FAKE_ENFORCEMENT_NOTE, ")"):
            with _SpanEdit(DESCRIPTION_REL, "description=(", FAKE_ENFORCEMENT_DESCRIPTION, ")"):
                monkeypatch.setattr(r78, "app", _fresh_app())
                _reds(r78.test_the_registration_response_labels_the_clearance_it_stores,
                      "假实现口吻落进响应体，r78 的第一枚钉却还绿：强度没升上去")
                _reds(r78.test_the_api_documentation_says_the_same_thing_to_the_client_that_reads_it,
                      "假实现口吻落进 OpenAPI，r78 的第二枚钉却还绿：强度没升上去")
                missing = [phrase for phrase in NOTE_CONFESSION if phrase not in _note_text().lower()]
                assert missing, "假实现口吻仍然满足自白清单：NOTE_CONFESSION 这格是空的"


def test_counter_evidence_dropping_the_closure_cell_is_not_an_empty_ruler():
    """判据④的刀二：把「已结案」那一格从白名单里摘掉——摘掉之后尺子必须当场报，不报就是空转。"""
    kept = tuple(cell for cell in CLOSURE_CELLS if cell[0] != "cell-cn-jiean")
    assert len(kept) == len(CLOSURE_CELLS) - 1, "白名单里找不到「结案」那一格：刀二无处下，格子已经名存实亡"
    assert not scan_app(), "摘刀之前 app/** 已经不清：这格读数无从归因"
    reported = scan_app(cells=kept)
    assert reported, "把「已结案」从白名单摘掉，尺子仍然一枚都不报：白名单是装饰，尺子是空转的"
    exempt = set((hit["rel"], hit["line"]) for hit in scan_app())
    gained = sorted(set((hit["rel"], hit["line"]) for hit in reported) - exempt)
    assert gained, "摘掉那一格没有多报任何一枚：这枚白名单格不承重：" + _render(reported)
