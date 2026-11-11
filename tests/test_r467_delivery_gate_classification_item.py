# -*- coding: utf-8 -*-
r"""R467 判据③ · 装机文档里那条「首灌前逐库确认密级标注策略」必须是**可执行**的一条。

落点为什么选 `deploy/README.server.md`：本仓唯一一本「客户现场装机 + 离线交付」的操作文档 ——
「启动 / 迁移 / 备份 / 访问 / 离线交付（客户现场通常不放外网）」都在它身上，交付记录（镜像到 digest、
模型打包）也记在它身上；`docs/deployment/` 今天只有 `backup-restore.md`（备份恢复）、
`health-details-frontend-contract.md`（前端接口约束）、`memory-fallback-and-multi-instance-boundaries.md`
（存储边界）三本，都不是客户装机时手里那一份；`docs/handoff/2026-09-26-v1-frontend-gap-list.md` 是
R265/R426 的前端缺口取证，不是交付清单。检查项放进缺口清单 = 装机的人永远不会打开它。

四组判据：

  · 甲 这一节在场，且说的是「未标注 = 1 级 = 全公司可读」这一枚**已裁定**的口径；
  · 乙 它给的是**能复制即跑**的核验（`docker compose ... psql`），点名的表与列在
    `migrations/` 里真存在，判据（`missing_classification` 必须为 0）写在同一段；
  · 丙 签字那一格点名两枚人：客户方数据负责人 + 我方实施工程师，且写明缺签 = 不开首灌；
  · 丁 口径与契约、与后端缺省同源（三处必须是同一枚数字），且这一节不许把「未标注」写成「不可见」。

四把反证刀只落 `tests/_temp_edit_overlay.py` 的影子根（盘上文档全程只读）：刀1 摘整节；刀2 把签字
收成一个人；刀3 把「必须是 0」改成「可以忽略」；刀4 把命令里的表名换成一张不存在的表。
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path

from tests import _temp_edit_overlay as overlay
from tests.test_r467_classification_default_is_ratified import (
    DEFAULT_ANCHOR,
    _contract_text,
    _disk_text,
    _sha,
)

REPO = Path(__file__).resolve().parents[1]
DELIVERY_REL = "deploy/README.server.md"
DELIVERY = REPO / DELIVERY_REL
MIGRATION_DIR = REPO / "migrations"

#: 这一节的标题（改名要连本钉与契约那句「交付闸门 C-1」一起改）。
SECTION_HEAD = "## 首灌前必须过的一道签字闸门：密级标注策略（C-1）"
#: 三条必备表述。
PUBLIC_CLAIM = "未标注密级的上传按 1 级入库"
PERMITTED_TO = "本公司所有账号都读得到"
ZERO_KEY_RULE = "missing_classification"
#: 那条判据的写法：读数旁边必须写着「必须是 0」，不许只剩一句「看一眼」。
RULE_LINE = re.compile(r"必须\s*是\s*0")


def _doc_text() -> str:
    return overlay.authoritative_text(DELIVERY_REL).replace("\r\n", "\n")


def _section(text: str) -> str:
    start = text.find(SECTION_HEAD)
    assert start != -1, "装机文档里没有 %r 这一节：本单那条交付闸门被删了或改了名" % SECTION_HEAD
    tail = text[start + len(SECTION_HEAD):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    return text[start:start + len(SECTION_HEAD) + (end.start() if end else len(tail))]


def _bash_blocks(text: str) -> list:
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


def _migrations_text() -> str:
    return "\n".join(sorted(path.read_bytes().decode("utf-8")
                            for path in MIGRATION_DIR.glob("*.sql")))


# ==================== 甲 · 这一节在场，说的就是裁完的那枚口径 ====================

def test_the_delivery_gate_exists_and_asks_for_per_store_confirmation():
    section = _section(_doc_text())
    assert "首灌前" in section, "这一节不再挂在「首灌前」时点上：它变成了事后说明"
    assert "逐库" in section, "「逐库确认」那一步被删了：一台机器一套库也要逐枚点名落点"
    assert PUBLIC_CLAIM in section, "未标注入库的那枚口径不在这节里了"
    assert PERMITTED_TO in section, "「全员可读」这半句被摘了：客户签的就不是同一件事"


def test_the_gate_names_the_ruling_it_is_based_on():
    """交付文档必须指着契约那一节，客户想复核时有一条走得通的路。"""
    section = _section(_doc_text())
    assert "R467" in section and "contract-v1.md" in section, section[:200]
    assert "H13" in section and "甲" in section, "裁定来源没写：下一班会把它当成新的未决项"


def test_the_gate_does_not_claim_unlabelled_is_invisible():
    """乙案（未标注即不可见）没被采纳：这一节不许反过来把 fail-closed 写成默认行为。"""
    for number, line in enumerate(_section(_doc_text()).split("\n"), 1):
        if "未标注" in line:
            assert "不可见" not in line and "不允许入库" not in line, (number, line)


# ==================== 乙 · 核验命令可执行，点名的表列在 migrations 里真存在 ====================

def test_the_gate_ships_copy_runnable_commands():
    blocks = _bash_blocks(_section(_doc_text()))
    assert len(blocks) >= 1, "这一节没有 fenced bash：只剩一句口号"
    commands = [ln for block in blocks for ln in block.splitlines() if ln.strip()]
    psql = [ln for ln in commands if "docker compose" in ln and "psql" in ln]
    assert len(psql) == 2, psql
    for line in psql:
        assert "deploy/.env.server" in line and "$POSTGRES_USER" in line, (
            "命令缺 --env-file 或缺容器内的库凭据：现场复制即错")
        assert "-Atc" in line and re.search(r"\bselect\b.*\bfrom\b", line), line


def _table_block(migrations: str, table: str) -> str:
    """从 DDL 里抠出建表那一段：列的形状要在**表内**判，拿全文判会捡到别人的列。"""
    match = re.search(r"CREATE TABLE IF NOT EXISTS %s \((.*?)\n\);" % re.escape(table),
                      migrations, re.DOTALL)
    assert match, "migrations 里读不到 CREATE TABLE IF NOT EXISTS %s 的建表段" % table
    return match.group(1)


def test_every_table_and_column_the_gate_queries_exists_in_the_migrations():
    section = _section(_doc_text())
    migrations = _migrations_text()
    tables = re.findall(r"\bfrom ([a-z_]+)", "\n".join(
        ln for ln in section.split("\n") if "psql" in ln))
    assert tables, "没从核验命令里抠出任何一枚表名"
    for table in sorted(set(tables)):
        block = _table_block(migrations, table)
        assert "classification" in block, "%s 建表段里没有密级列：%s" % (table, block[:120])
    assert re.search(r"\bclassification INTEGER\b", _table_block(migrations, "chunk_vectors")), (
        "chunk_vectors.classification 不再是可空的整数：契约「缺键 = NULL = 永不可见」那一条要重读")
    assert re.search(r"\bclassification TEXT NOT NULL\b", _table_block(migrations, "resource_versions"))


def test_the_zero_rule_for_missing_classification_is_stated_next_to_the_command():
    """缺键 = 静默丢料：这一节必须把「必须是 0」写在命令旁边，而不是让人自己猜读数怎么判。"""
    section = _section(_doc_text())
    assert ZERO_KEY_RULE in section, "核验读数那一格没点名 missing_classification：让人自己猜查的是什么"
    assert RULE_LINE.search(section), (
        "「必须是 0」这条判据被放宽或删掉了：缺键行是静默丢料，不是可选检查")
    assert section.index("必须是 0") > section.index("psql"), (
        "判据写在了命令之前：那一格读起来像前言，不像读数之后要打的勾")
    assert "永不可见" in section, "缺键那一维的口径没交代：为什么必须为 0 就成了无来由的规矩"


# ==================== 丙 · 谁来签字 ====================

def test_the_gate_names_two_signatories_and_the_consequence_of_missing_signatures():
    section = _section(_doc_text())
    assert "客户方数据负责人" in section, "策略归属那一格没点名到人：知情同意不能由我们代签"
    assert "实施工程师" in section, "核验读数那一格没点名到人"
    assert "不开首灌" in section, "缺签的后果被删了：那这条闸门就没有牙齿"


def test_the_row_level_blank_cell_claim_matches_rbac_source():
    """文档里那句「行级密级列同样按 1 级兜底」必须对得上真源代码，不是想当然。"""
    section = _section(_doc_text())
    assert "filter_dataframe_rows" in section and "fillna(1)" in section
    assert re.search(r"\[class_col\]\.fillna\(1\)", _disk_text("app/common/rbac.py")), (
        "rbac 的行级密级兜底不再是 fillna(1)：文档那句与契约第 1 条都要重读")


# ==================== 丁 · 与契约、后端同源 ====================

def test_the_level_the_gate_states_is_the_same_number_the_contract_and_backend_state():
    doc_level = int(re.search(r"未标注密级的上传按 (\d+) 级入库", _section(_doc_text())).group(1))
    contract_level = int(DEFAULT_ANCHOR.search(_contract_text()).group(1))
    route = re.search(r"classification:\s*int\s*=\s*Form\((\d+)\)", _disk_text("app/api/v1/chat.py"))
    assert route, "后端签名读不到 Form(n)"
    assert doc_level == contract_level == int(route.group(1)), (
        "交付闸门、契约、后端缺省三处不同源：(%s, %s, %s)" % (doc_level, contract_level, route.group(1)))


# ==================== 反证刀 ====================

class _R467DeliveryEdit(overlay.ShadowEdit):
    """一扇装机文档的反证窗：锚点命中不是恰好一处，变异整片不落影子根。"""

    tag = "r467-delivery"

    def __init__(self, path: Path, edits) -> None:
        super().__init__(path)
        self.edits = list(edits)

    def mutate(self, text: str) -> str:
        newline = "\r\n" if "\r\n" in text else "\n"
        mutated = text
        for old, new in self.edits:
            needle = old.replace("\n", newline)
            hits = mutated.count(needle)
            assert hits == 1, "文档里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落影子" % (
                hits, old[:60])
            mutated = mutated.replace(needle, new.replace("\n", newline), 1)
        return mutated


@contextmanager
def _window(edits):
    with _R467DeliveryEdit(DELIVERY, edits) as info:
        yield info


PINS = (
    test_the_delivery_gate_exists_and_asks_for_per_store_confirmation,
    test_the_gate_names_the_ruling_it_is_based_on,
    test_the_gate_does_not_claim_unlabelled_is_invisible,
    test_the_gate_ships_copy_runnable_commands,
    test_every_table_and_column_the_gate_queries_exists_in_the_migrations,
    test_the_zero_rule_for_missing_classification_is_stated_next_to_the_command,
    test_the_gate_names_two_signatories_and_the_consequence_of_missing_signatures,
    test_the_row_level_blank_cell_claim_matches_rbac_source,
    test_the_level_the_gate_states_is_the_same_number_the_contract_and_backend_state,
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
    print("[r467-delivery] %s 红 %d 枚：%s" % (knife, len(red), sorted(red)))
    print("[r467-delivery] %s 绿 %d 枚：%s" % (knife, len(green), sorted(green)))


def test_counter_evidence_1_deleting_the_whole_gate_goes_red():
    """刀1：摘掉整节 ⇒ 甲乙丙丁四组全红（这节不存在时任何一枚钉都不许空响）。"""
    tracked = _sha(DELIVERY)
    text = _doc_text()
    with _window([(_section(text), "")]) as info:
        red, green = _tally()
        assert len(red) == len(PINS), (red, green)
        assert _sha(DELIVERY) == tracked, "被跟踪的装机文档在反证窗里被改过"
        _print_tally("刀1 摘整节", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_2_single_signatory_goes_red():
    """刀2：把两枚签字收成实施工程师自己 ⇒ 签字钉红。"""
    tracked = _sha(DELIVERY)
    with _window([("**客户方数据负责人**（业务侧，不是 IT 侧）", "**我方实施工程师**（自查）")]) as info:
        red, green = _tally()
        assert "test_the_gate_names_two_signatories_and_the_consequence_of_missing_signatures" in red, red
        assert _sha(DELIVERY) == tracked
        _print_tally("刀2 签字收成一枚", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_3_loosening_the_zero_rule_goes_red():
    """刀3：把「missing_classification 必须是 0」放宽 ⇒ 判据钉红。"""
    tracked = _sha(DELIVERY)
    with _window([("- `%s` **必须是 0**。密级**缺键**" % ZERO_KEY_RULE,
                   "- `%s` 可以忽略。密级**缺键**" % ZERO_KEY_RULE)]) as info:
        red, green = _tally()
        assert "test_the_zero_rule_for_missing_classification_is_stated_next_to_the_command" in red, red
        assert _sha(DELIVERY) == tracked
        _print_tally("刀3 放宽必须为 0", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_counter_evidence_4_querying_a_table_that_does_not_exist_goes_red():
    """刀4：命令里的表名换成一张不存在的表 ⇒ 迁移对账钉红（命令形状仍然像话，红点必须落在表名上）。"""
    tracked = _sha(DELIVERY)
    with _window([("from chunk_vectors\"", "from chunk_vectors_typo\"")]) as info:
        red, green = _tally()
        assert "test_every_table_and_column_the_gate_queries_exists_in_the_migrations" in red, red
        assert "test_the_gate_ships_copy_runnable_commands" not in red, (
            "命令形状没被这刀改，这枚不该红 —— 红了说明两件事混在同一枚断言里")
        assert _sha(DELIVERY) == tracked
        _print_tally("刀4 表名换成不存在的表", red, green)
    assert info["restored"] and info["shadow_clean"], info


def test_the_window_leaves_the_tracked_delivery_doc_untouched():
    print("[r467-delivery] 盘上只读核对 %s sha256=%s" % (DELIVERY_REL, _sha(DELIVERY)[:16]))
    assert re.fullmatch(r"[0-9a-f]{64}", _sha(DELIVERY))
