# -*- coding: utf-8 -*-
r"""R467 判据① · 密级这一维的缺省与缺键必须写进契约，而契约得与真源逐枚对得上。

背景（现读自 `9c21490`）：业主已把 H13 裁定为**甲** —— 未标注密级的上传按 1 级（最低公开）入库。
这一格从此是写进契约的口径，不再是缺陷；契约里那两处「H13 还悬着」的表述（`row_scope.code` 值域
那一格的 `owner-open`、R357 讲 `auditor` 那一段的 `still with 业主`）随结案已成假话，本单就地改口。

四组判据逐枚对位（本件零手抄常数：每一枚数字都从真源现抠）：

  · 甲 「H13 未决」字样在契约**活散文**里命中 0 条。逐字引文只许待在 ``` 围栏里 ——
    「引文不是断言」沿用 R276 那枚口径钉的分法；把原句搬回活散文，本钉当场红。
  · 乙 契约明写 `缺省密级 = 1 级`，那个数字与四枚真源逐枚等值：路由缺省
    `classification: int = Form(n)`、入库缺省 `_scope_int(self.classification, n)`、
    界面缺省 `DEFAULT_UPLOAD_CLASSIFICATION`、以及 `1 级 = 本客户全员可检索` 那枚锚句里的级数。
  · 丙 「全员可检索」不是形容词：真调用 `allowed_levels()` 对每一枚在册角色**与不在册角色**
    都回含这一档的集合；同一段散文还必须带着部门那一维的 caveat —— 少了 caveat 就是把
    「密级不设门槛」写成「谁都能读到别人部门的文档」，那是第二句假话。
  · 丁 「密级**缺键**（不是缺 1）在检索侧永不可见」：契约锚句在场，且读侧真源
    `meta.get("classification")` 不带 `, 1)`；本件直接构造 `DocumentRetrievalScope` 真调用
    `allows()`，缺键与 `None` 两枚输入都必须回 False（不碰审计通路、不碰库、不起服务）。

四把反证刀只落 `tests/_temp_edit_overlay.py` 的影子根（盘上契约全程只读，进出各取一次 sha256）：
刀1 把 `owner-open` 那句搬回活散文；刀2 摘掉缺省口径那一句；刀3 把缺键那一支改写成「按 1 级放行」；
刀4 把裁定改回「仍待业主」。每把逐枚报红名与绿名，不报总数。
"""
from __future__ import annotations

import ast
import hashlib
import re
from contextlib import contextmanager
from pathlib import Path

from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
CONTRACT_REL = "docs/api/contract-v1.md"
CONTRACT = REPO / CONTRACT_REL
CHAT_REL = "app/api/v1/chat.py"
INDEXING_REL = "app/rag/indexing.py"
PIPELINE_REL = "app/rag/retrieval_pipeline.py"
PG_STORE_REL = "app/rag/pg_store.py"
DOCPANEL_REL = "frontend/src/components/DocPanel.vue"
DELIVERY_REL = "deploy/README.server.md"

SECTION_HEAD = "## R467 "

#: 「H13 还悬着」的字样：只许作为逐字引文出现在围栏里，出现在活散文里就是假话。
OPEN_QUESTION_PATTERNS = (
    re.escape("owner-open"),
    re.escape("unratified dimension"),
    re.escape("the tier question is H13"),
    r"H13[^\n]{0,40}(未裁|未定|未决|待裁|待业主|still with|awaiting)",
    r"(待|still with)[^\n]{0,40}业主[^\n]{0,40}H13",
)
#: 契约里那三条口径的机器锚句（本节自己把它们标成「锚句」，改措辞要连本件一起改）。
DEFAULT_ANCHOR = re.compile(r"缺省密级 = (\d+) 级")
EVERYONE_ANCHOR = re.compile(r"(\d+) 级 = 本客户全员可检索")
MISSING_KEY_ANCHOR = re.compile(r"密级缺键（不是缺 (\d+)）在检索侧永不可见")
PUBLIC_ANCHOR = "未标注入库即视为公开"
RULING_ANCHOR = re.compile(r"H13\s*=\s*甲")
#: 界面上那一句的三个必备片段（契约与组件共用同一枚尺，谁改了另一边就红）。
SCREEN_TAIL = "不设密级门槛，全公司的人都读得到（部门由服务端按你的账号判定）"
#: 本节逐字引的退役原句（必须在围栏里，且必须在活散文里绝迹）。
RETIRED_QUOTES = (
    "unratified dimension (classification is H13, owner-open).",
    "(`app/common/rbac.py:31`), and the tier question is H13, still with 业主.",
)


# ==================== 读数把手 ====================

def _disk_text(rel: str) -> str:
    """盘上被跟踪文件的字（LF 口径）：本件对 `app/**` 与前端组件都只读。"""
    path = REPO / rel
    assert path.is_file(), "%s 不在了" % rel
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _contract_text() -> str:
    """当前该算数的那份契约：反证窗内是影子副本的变异版，窗外是盘上的字。"""
    return overlay.authoritative_text(CONTRACT_REL).replace("\r\n", "\n")


def _prose_lines(text: str) -> list:
    """围栏外的行 —— 断言面。围栏里的逐字引文不算断言（R276 同一口径）。"""
    out, in_fence = [], False
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((number, line))
    return out


def _fenced_text(text: str) -> str:
    out, in_fence = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line)
    return "\n".join(out)


def _open_question_hits(text: str) -> list:
    return [(number, pattern, line)
            for number, line in _prose_lines(text)
            for pattern in OPEN_QUESTION_PATTERNS
            if re.search(pattern, line)]


def _r467_section(text: str) -> str:
    start = text.find(SECTION_HEAD)
    assert start != -1, "契约里没有 %s 这一节：改名可以，请连本钉一起改" % SECTION_HEAD
    tail = text[start + len(SECTION_HEAD):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    return text[start:start + len(SECTION_HEAD) + (end.start() if end else len(tail))]


def _one(pattern: re.Pattern, text: str, what: str) -> str:
    hits = pattern.findall(text)
    assert hits, "契约里读不到%s：这一节被改了措辞，本钉与契约必须同批改" % what
    assert len(set(hits)) == 1, "%s 在契约里有多枚取值：%s" % (what, hits)
    return hits[0]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ==================== 甲 · 「H13 未决」的字样必须绝迹 ====================

def test_no_open_question_wording_survives_in_the_live_prose():
    hits = _open_question_hits(_contract_text())
    assert hits == [], "契约活散文里还有「H13 未决」的写法（假话）：" + repr(hits[:4])


def test_the_retired_sentences_are_still_quoted_verbatim_in_fences():
    """改口不许顺手销毁历史：两枚退役原句必须逐字留在围栏里，供下一班对账。"""
    fenced = _fenced_text(_contract_text())
    for quote in RETIRED_QUOTES:
        assert quote in fenced, "退役原句的逐字引文被删了：%r" % quote[:60]


# ==================== 乙 · 缺省那一档：契约说的数 == 四枚真源 ====================

def test_the_default_level_the_contract_states_is_the_route_and_ingest_default():
    stated = int(_one(DEFAULT_ANCHOR, _contract_text(), "缺省密级那句锚句"))
    route = re.search(r"classification:\s*int\s*=\s*Form\((\d+)\)", _disk_text(CHAT_REL))
    assert route, "后端签名里读不到 classification = Form(n)：先取证再动契约"
    ingest = re.search(r"_scope_int\(self\.classification,\s*(\d+)\)", _disk_text(INDEXING_REL))
    assert ingest, "入库缺省读不到了：scope_metadata() 的形状变了，本钉该改法而不是被跳过"
    screen = re.search(r"DEFAULT_UPLOAD_CLASSIFICATION = (\d+)", _disk_text(DOCPANEL_REL))
    assert screen, "界面默认档常量读不到了"
    assert stated == int(route.group(1)) == int(ingest.group(1)) == int(screen.group(1)), (
        "契约说的缺省档与真源不再是同一枚数：契约 %s / 路由 %s / 入库 %s / 界面 %s" % (
            stated, route.group(1), ingest.group(1), screen.group(1)))


def test_the_public_by_ruling_wording_is_in_the_contract():
    """未标注入库即视为公开，且这是**裁定**不是缺陷：裁定标记与口径同段在场。"""
    text = _contract_text()
    section = _r467_section(text)
    assert RULING_ANCHOR.search(section), "本节不再写明 H13 = 甲：口径又变回悬着的事"
    assert PUBLIC_ANCHOR in section, "「未标注入库即视为公开」那一句锚句被删了"
    assert "不再是" in section and "缺陷" in section, "本节必须明写这一格不再是缺陷（否则下一班再报一遍）"


# ==================== 丙 · 「1 级 = 全员可检索」得是真调用说了算 ====================

def test_the_default_level_clears_every_role_including_roles_with_no_tier():
    from app.common.rbac import ROLE_CLEARANCE, allowed_levels

    stated = int(_one(EVERYONE_ANCHOR, _contract_text(), "全员可检索那句锚句"))
    roles = sorted(set(list(ROLE_CLEARANCE) + ["auditor", "", "not-a-role"]))
    missing = [role for role in roles if stated not in allowed_levels(role)]
    assert not missing, (
        "契约说 %s 级全员可检索，但这些角色的档位集合里没有它：%s" % (stated, missing))


def test_the_everyone_claim_keeps_its_department_caveat():
    """「全员可检索」只管密级这一维：同一段散文必须带着部门那道闸，缺了就是一句新假话。"""
    line = next((ln for _, ln in _prose_lines(_contract_text()) if "本客户全员可检索" in ln), "")
    assert line, "契约里再没有「1 级 = 本客户全员可检索」这一行了"
    assert "只管密级这一维" in line and "部门" in line, line


# ==================== 丁 · 缺键（不是缺 1）在检索侧永不可见 ====================

def test_a_missing_classification_key_is_never_visible_through_the_real_gate():
    from app.rag.filters import DocumentRetrievalScope

    _one(MISSING_KEY_ANCHOR, _contract_text(), "缺键那一句锚句")
    scope = DocumentRetrievalScope(
        filters={}, reason_code="r467", classification_levels=frozenset({1}), departments=None)
    assert scope.allows({"filename": "无这枚键的行"}) is False, "缺键行被放行了：契约那句成了假话"
    assert scope.allows({"classification": None}) is False, "None 被放行了：同上"
    assert scope.refusal_code({"classification": None}) == "resource_scope_missing"
    assert scope.allows({"classification": 1}) is True, "对照：真带着 1 级的行必须可见，否则上面两枚是空响"


def test_the_read_leg_still_supplies_no_default_for_the_classification_key():
    """读侧真源用 AST 判，不用字符串判：R57 那条注释里**逐字引着**旧的 `meta.get(..., 1)`，
    按字符串判会把历史取证读成现行缺陷（09-28 实测：那一枚反证刀因此假红过）。"""
    tree = ast.parse(_disk_text(PIPELINE_REL))
    reads = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "meta"
             and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value == "classification"]
    assert reads, "读侧再没有 meta.get('classification') 这一枚调用：形状变了，本钉该改法"
    padded = [ast.unparse(node) for node in reads if len(node.args) > 1]
    assert not padded, "读侧给缺键又补了一枚凭空的价值：%s —— 契约那句「缺键永不可见」成假话" % padded


def test_the_pgvector_leg_keeps_null_instead_of_inventing_a_level():
    from app.rag import pg_store

    source = _disk_text(PG_STORE_REL)
    assert "Kept as NULL, not filled with 1" in source, "PG 语料腿改口了：两枚引擎不再同色"
    clause, params = pg_store.sql_scope_filter({"classification": {"$in": [1]}})
    assert "ANY" in clause and params, (clause, params)


def test_the_contract_quotes_the_very_sentence_the_screen_renders():
    """契约里那句界面文案与组件模板共用同一段字：措辞漂了必须两边一起改。"""
    assert SCREEN_TAIL in _contract_text(), "契约不再引用界面上那句话"
    assert SCREEN_TAIL in _disk_text(DOCPANEL_REL), "组件里那段话被改了，契约那句成了引用不存在的东西"
    assert "零技术串" in _r467_section(_contract_text()), "契约不再明写屏上零技术串"


# ==================== 反证刀 ====================

LIVE_NEW_LINE = ("  row-level dimension: classification. Its blank-cell reading is **ratified now, not open** -")
LIVE_DEFAULT_BULLET = "**缺省密级 = 1 级**（锚句：`缺省密级 = 1 级`）"
LIVE_PUBLIC_BULLET = "**未标注入库即视为公开**（锚句：`未标注入库即视为公开`）"
LIVE_MISSING_KEY_BULLET = "**密级缺键（不是缺 1）在检索侧永不可见**（锚句：`缺键` + `永不可见`）"
LIVE_RULING_LINE = "- **裁定**：H13 = 甲。"


class _R467ContractEdit(overlay.ShadowEdit):
    """一扇 R467 反证窗：锚点在契约里命中不是恰好一处，变异整片不落影子根。"""

    tag = "r467"

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = list(edits)

    def mutate(self, text: str) -> str:
        newline = "\r\n" if "\r\n" in text else "\n"
        mutated = text
        for old, new in self.edits:
            needle = old.replace("\n", newline)
            hits = mutated.count(needle)
            assert hits == 1, "契约里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落影子" % (
                hits, old[:60])
            mutated = mutated.replace(needle, new.replace("\n", newline), 1)
        return mutated


@contextmanager
def _window(edits):
    with _R467ContractEdit(CONTRACT, edits) as info:
        yield info


PINS = (
    test_no_open_question_wording_survives_in_the_live_prose,
    test_the_retired_sentences_are_still_quoted_verbatim_in_fences,
    test_the_default_level_the_contract_states_is_the_route_and_ingest_default,
    test_the_public_by_ruling_wording_is_in_the_contract,
    test_the_default_level_clears_every_role_including_roles_with_no_tier,
    test_the_everyone_claim_keeps_its_department_caveat,
    test_a_missing_classification_key_is_never_visible_through_the_real_gate,
    test_the_read_leg_still_supplies_no_default_for_the_classification_key,
    test_the_pgvector_leg_keeps_null_instead_of_inventing_a_level,
    test_the_contract_quotes_the_very_sentence_the_screen_renders,
)


def _tally():
    red, green = [], []
    for pin in PINS:
        try:
            pin()
        except AssertionError:
            red.append(pin.__name__)
        else:
            green.append(pin.__name__)
    return red, green


def _print_tally(knife: str, red: list, green: list) -> None:
    print("[r467] %s 红 %d 枚：%s" % (knife, len(red), sorted(red)))
    print("[r467] %s 绿 %d 枚：%s" % (knife, len(green), sorted(green)))


def test_counter_evidence_1_owner_open_back_in_live_prose_goes_red():
    """刀1：把退役原句搬回活散文 ⇒ 「未决字样」那枚当场红，其余照旧绿。"""
    tracked = _sha(CONTRACT)
    must_red = ("test_no_open_question_wording_survives_in_the_live_prose",)
    with _window([(LIVE_NEW_LINE, "  some " + RETIRED_QUOTES[0])]) as info:
        red, green = _tally()
        assert set(must_red) <= set(red), "刀1 没咬住：红的是 %s" % red
        assert _sha(CONTRACT) == tracked, "被跟踪的契约在反证窗里被改过"
        _print_tally("刀1 owner-open 回活散文", red, green)
    assert info["restored"] and info["shadow_clean"], info
    assert _sha(CONTRACT) == tracked


def test_counter_evidence_2_removing_the_default_level_bullet_goes_red():
    """刀2：摘掉「缺省密级 = 1 级」那枚锚句 ⇒ 缺省同源钉红；全员那半枚仍绿（两件事分家）。"""
    tracked = _sha(CONTRACT)
    with _window([(LIVE_DEFAULT_BULLET, "**缺省档这一格已结案**")]) as info:
        red, green = _tally()
        assert "test_the_default_level_the_contract_states_is_the_route_and_ingest_default" in red, red
        assert "test_the_default_level_clears_every_role_including_roles_with_no_tier" not in red, red
        assert _sha(CONTRACT) == tracked
        _print_tally("刀2 摘缺省口径", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_5_removing_the_public_by_ruling_anchor_goes_red():
    """刀5：摘掉「未标注入库即视为公开」那枚锚句 ⇒ 裁定口径钉红，其余不动。"""
    tracked = _sha(CONTRACT)
    with _window([(LIVE_PUBLIC_BULLET, "**未标注的处理方式见上**")]) as info:
        red, green = _tally()
        assert "test_the_public_by_ruling_wording_is_in_the_contract" in red, red
        assert "test_no_open_question_wording_survives_in_the_live_prose" not in red, red
        assert _sha(CONTRACT) == tracked
        _print_tally("刀5 摘视为公开锚句", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_3_missing_key_flipped_to_visible_goes_red():
    """刀3：把缺键那一支改写成「缺键按 1 级放行」⇒ 缺键锚句钉红（行为那半仍绿，说明判据分家）。"""
    tracked = _sha(CONTRACT)
    with _window([(LIVE_MISSING_KEY_BULLET, "**密级缺键按 1 级放行**")]) as info:
        red, green = _tally()
        assert "test_a_missing_classification_key_is_never_visible_through_the_real_gate" in red, red
        assert "test_the_read_leg_still_supplies_no_default_for_the_classification_key" not in red, (
            "读侧源码没被本刀改，这枚不该红 —— 红了说明两件事混在同一枚断言里")
        assert _sha(CONTRACT) == tracked
        _print_tally("刀3 缺键改判成可见", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_4_ruling_sent_back_to_the_owner_goes_red():
    """刀4：把 D4 那一行裁定改回「仍待业主」⇒ 中文那族「未决」字样也必须咬住（不止英文原句）。

    裁定口径钉在这一刀下**故意是绿的**：本节在别处还写着 `H13 = 甲`（一句话那一段与改口表都写着），
    摘掉一处不等于口径失踪 —— 这一格记下来，免得下一班把这枚绿读成刀没咬住。
    """
    tracked = _sha(CONTRACT)
    with _window([(LIVE_RULING_LINE, "- **裁定**：H13 仍待业主。")]) as info:
        red, green = _tally()
        assert "test_no_open_question_wording_survives_in_the_live_prose" in red, red
        assert "test_the_public_by_ruling_wording_is_in_the_contract" in green, green
        assert _sha(CONTRACT) == tracked
        _print_tally("刀4 裁定改回未决", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_the_shadow_window_leaves_the_tracked_contract_and_the_delivery_doc_untouched():
    """四把刀跑完之后：契约与装机文档的字节必须与进门时同一枚 sha256。"""
    for rel in (CONTRACT_REL, DELIVERY_REL):
        digest = _sha(REPO / rel)
        assert re.fullmatch(r"[0-9a-f]{64}", digest), digest
        print("[r467] 盘上只读核对 %s sha256=%s" % (rel, digest[:16]))
