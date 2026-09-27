# -*- coding: utf-8 -*-
r"""R349 · 「目录尾号」的唯一账本：一枚字面量 + N 处 import，引信一颗都不许拆。

来历（09-27 全量门第三枚红的现场）：盘上已经有 ``migrations/0016_notification_states.sql``
（R299 通知收件箱的读者生命周期表），而 ``tests/test_r251_alert_disposal_migration.py`` 那份手抄
的账还停在 0015 / dataset_version_scope_columns。同一个数字被抄在好几枚件里，0016 落地时改口了
几份、漏了别份，门就红了 —— 红的不是产品，是账本与现实脱钩。

🔴 方向只有一条（判据③）：真源是本文件下面那**两枚带引号的字面量**，``MIGRATIONS`` 是事实。
新排一版 ⇒ 人回到这里把两枚字面量改口（并补一句这一版的主题）；不是把字面量换成
``MIGRATIONS[-1].version`` 那种派生式。派生式看着"从此不用改口"，实际是把引信拆了：下一枚
0017 会**静默通过**，那是比今天这种手抄更危险的假绿。所以本文件同时是形状钉 ——
派生式、以及别处再抄一份字面量，两件事都由下面的用例抓红。

现号：0016，主题 notification_states（R299 给通知收件箱落的读者生命周期表，不是第二本通知台账）。

改口流程（新排一枚迁移时照着走）：
  1. 只改本文件的 CATALOG_TAIL_VERSION 与 CATALOG_TAIL_NAME 这两枚字面量，再把上面"现号"那一行
     换成本版的主题（一句话：谁排的、给哪张表落了什么）。
  2. import 方（test_document_catalog_sync / test_r175 / test_r183_184 / test_r183_declared_lane /
     test_r190 / test_r251 / test_r299 / test_r46）一个字都不动 —— 它们只读这枚账本。
  3. 各件里那种「把 0010 之后的每一枚点名」的名册（test_r120 的 forward 名单、test_r183_184 里
     ``> NEW_VERSION`` 那几枚、test_r256 / test_r249 / test_r303 各钉自己那一版的形状）是新那一版
     的**登记动作**，回到那里把版本号与主题名一起点上。它们不是尾号账，一枚都不许改成派生式。
  4. 各件的主题版常量（LANDED_VERSION / NEW_VERSION / VERSION 那一族，比如 r251 的 0014、r190 的
     0013、r256 的 0015）说的是"本件重放到哪一版"，一概不跟着尾号改口。

本件零生产写入：只读 ``app/db/migrations.py`` 的 loader 与各件源码文本。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.db.migrations import MIGRATIONS

#: 唯一账本所在地的文件名：形状钉拿它做"只许出现在这里"的自指。
LEDGER_MODULE = Path(__file__).name
TESTS_DIR = Path(__file__).resolve().parent

#: 🔴 目录尾号。整个测试套件只许在这里写死一次，其余件一律 import。
CATALOG_TAIL_VERSION = "0016"
CATALOG_TAIL_NAME = "notification_states"

#: 上面那段 docstring 是"这一版的主题"的落点，判据②的失败消息把人送回这里。
_LEDGER_DOC = __doc__ or ""

#: 定义形状：行首、且 = 右边必须是一枚带引号的字面量。
_LITERAL_DEFINITION = re.compile(
    r"^[ \t]*(?P<name>CATALOG_TAIL_(?:VERSION|NAME))[ \t]*=[ \t]*(?P<value>[\"'][0-9a-z_]+[\"'])[ \t]*$",
    re.MULTILINE,
)
#: 派生式定义（= MIGRATIONS[-1].version 那一族）＝把引信拆掉的形状，抓到就红。
_DERIVED_DEFINITION = re.compile(
    r"^[ \t]*CATALOG_TAIL_(?:VERSION|NAME)[ \t]*=[ \t]*(?=[^\"' \r\n])[^\r\n]*$",
)
#: 内联字面量对判目录事实 ＝ 第二份手抄账（刀C 的第二种躲法）。
_INLINE_FACT_COMPARE = re.compile(
    r"(?:\bversions\[-1\]|\bMIGRATIONS\[-1\]\.[a-z]+|\.split\([\"']_[\"']\)\[0\])"
    r"[ \t]*(?:==|!=|>=|<=|>|<)[ \t]*[\"'][^\"']+[\"']"
)
#: 引用本账本的合法形状：只许 from 本件 import。
_LEDGER_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+(?:tests\.)?test_r349_catalog_tail_ledger[ \t]+import\b", re.MULTILINE
)
_MENTION = re.compile(r"\bCATALOG_TAIL_(?:VERSION|NAME)\b")
#: 「0001..尾号 一枚不缺」这条连续性主张的持有件（判据④）。名册是**文件名**，不是版本号。
_CONTINUITY_OWNERS = (
    "test_document_catalog_sync.py",
    "test_r183_184_migration_pair.py",
    "test_r190_status_failed_domain.py",
    "test_r251_alert_disposal_migration.py",
    "test_r299_notification_states.py",
)
#: 连续性必须拿账本构造期望值：range(1, int(CATALOG_TAIL_VERSION) + 1)。
_LEDGER_BOUND_SEQUENCE = re.compile(r"range\(1,[ \t]*int\(CATALOG_TAIL_VERSION\)[ \t]*\+[ \t]*1\)")
#: 「现号」那一行的形状：改尾号必须连主题一起落在这行上。
_PRESENT_TAIL = re.compile("现号：(?P<version>\\d{4})，主题 (?P<name>[a-z_]+)")


def _test_sources() -> list[tuple[str, str]]:
    """盘上全部 ``test_*.py`` 的源码文本，逐枚带相对名。形状钉读文本，不看运行结果。"""
    return [
        (path.relative_to(TESTS_DIR).as_posix(),
         path.read_text(encoding="utf-8", errors="replace"))
        for path in sorted(TESTS_DIR.rglob("test_*.py"))
        if "__pycache__" not in path.parts
    ]


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _unquote(value: str) -> str:
    return value[1:-1]


def _stale_message(field: str, ledger: str, fact: str) -> str:
    """判据②：失败消息必须读得出下一步做什么，而且只指一处。"""
    return (
        f"目录尾号账本过期：{LEDGER_MODULE} 里的 CATALOG_TAIL_{field} 写的是 {ledger!r}，"
        f"而目录事实 MIGRATIONS[-1] 是 {fact!r}"
        f"（盘上最新一枚 = migrations/{MIGRATIONS[-1].version}_{MIGRATIONS[-1].name}.sql）。"
        f"下一步只有一处可改：打开 tests/{LEDGER_MODULE}，把 CATALOG_TAIL_VERSION 与 "
        "CATALOG_TAIL_NAME 这两枚字面量一起改成最新那一版，并把该文件 docstring 里「现号」"
        "那一行换成本版的主题（谁排的、给哪张表落了什么）。"
        "🔴 别改任何 import 方，更不许把常量改成 MIGRATIONS[-1] 派生式 —— 那样下一版会静默通过，"
        "引信就没了。"
    )


# ---------------------------------------------------------------- 引信本体
def test_the_named_tail_is_still_the_catalog_tail():
    """判据②的引信：常量与目录事实对判，全仓**只有这一处**做这条对判。

    断言方向是「账本 == 事实」（判据③）：事实漂了这格就红，红消息指名去改那两枚字面量。
    把它写成 ``CATALOG_TAIL_VERSION == MIGRATIONS[-1].version`` 的派生定义不叫改口，那叫拆引信，
    由 test_the_tail_literals_are_literals_not_derived_values 抓红。
    """
    assert MIGRATIONS, "目录一枚迁移都没有：MIGRATIONS[-1] 无从对判，先去查 loader"
    assert CATALOG_TAIL_VERSION == MIGRATIONS[-1].version, _stale_message(
        "VERSION", CATALOG_TAIL_VERSION, MIGRATIONS[-1].version
    )
    assert CATALOG_TAIL_NAME == MIGRATIONS[-1].name, _stale_message(
        "NAME", CATALOG_TAIL_NAME, MIGRATIONS[-1].name
    )


# ---------------------------------------------------------------- 形状钉
def test_the_tail_literals_are_defined_exactly_once():
    """判据①的形状钉：字面量定义在全仓只许命中一枚，且就落在本件。

    等价于总控复核判据①用的那条命令——数一遍 tests/ 里「常量名 + 赋值号 + 带引号版号」这种定义
    行：命中数必须为 1。刀C（摘掉某枚 import、在 import 方偷偷留一份字面量副本）让定义数变成 2，
    这一格当场红。
    """
    defs = {"VERSION": [], "NAME": []}
    for rel, text in _test_sources():
        for match in _LITERAL_DEFINITION.finditer(text):
            defs[match.group("name").rsplit("_", 1)[1]].append(
                f"{rel}:{match.group('value')}"
            )
    assert defs["VERSION"] == [f"{LEDGER_MODULE}:\"{CATALOG_TAIL_VERSION}\""], (
        "CATALOG_TAIL_VERSION 的字面量定义必须只有一枚，多出来的那份就是手抄账：" + str(defs["VERSION"])
    )
    assert defs["NAME"] == [f"{LEDGER_MODULE}:\"{CATALOG_TAIL_NAME}\""], (
        "CATALOG_TAIL_NAME 的字面量定义必须只有一枚：" + str(defs["NAME"])
    )


def test_the_tail_literals_are_literals_not_derived_values():
    """判据③的牙：谁把账本改成从 MIGRATIONS 派生，就是新排一版会静默通过的那枚假绿。"""
    offenders = [
        f"{rel}:{_line_of(text, match.start())}"
        for rel, text in _test_sources()
        for match in _DERIVED_DEFINITION.finditer(text)
    ]
    assert offenders == [], (
        "CATALOG_TAIL_VERSION / CATALOG_TAIL_NAME 只能是一枚带引号的字面量，改成派生式等于拆引信："
        + ", ".join(offenders)
    )


def test_no_module_recompares_the_catalog_fact_to_an_inlined_literal():
    """判据①的另一半：账本之外的件不许把 ``versions[-1]`` 之类与内联字面量对判。

    那种写法既是第二份手抄账，又正好落在引信的盲区里（它不定义常量，只把数字抄进断言），
    所以单开一枚钉。刀C 用内联形状躲 #1 时也躲不过这一枚。
    """
    hits = [
        f"{rel}:{_line_of(text, match.start())} {match.group(0)}"
        for rel, text in _test_sources()
        for match in _INLINE_FACT_COMPARE.finditer(text)
    ]
    assert hits == [], (
        "尾号只能从 " + LEDGER_MODULE + " 读；把版号直接写进断言就是又抄一份账：" + " | ".join(hits)
    )


def test_every_module_that_uses_the_ledger_imports_it_from_here():
    """判据①的拓扑钉：提这两枚名字的件，要么是本件，要么 from 本件 import。"""
    offenders = []
    for rel, text in _test_sources():
        if rel == LEDGER_MODULE or not _MENTION.search(text):
            continue
        if not _LEDGER_IMPORT.search(text):
            offenders.append(rel)
    assert offenders == [], (
        "这些件引用了目录尾号却没从唯一账本 import（刀C 摘掉 import 的那一躲就落在这里）："
        + ", ".join(offenders)
    )


def test_the_contiguity_claim_is_bound_to_the_ledger():
    """判据④ + 刀D：「0001..尾号 一枚不缺」必须拿账本构造期望值。

    ``range(1, len(versions) + 1)`` 只钉"没有缺口"，尾号漂了它照旧绿；换成账本以后它同时钉
    "缺口"与"尾号"。谁把它换成 ``versions == sorted(versions)`` 那种永不红的形状（loader 本来就
    按文件名排序返回，见 ``discover_migrations``），这一格会点名抓红。
    """
    missing = []
    for rel in _CONTINUITY_OWNERS:
        text = (TESTS_DIR / rel).read_text(encoding="utf-8", errors="replace")
        if not _LEDGER_BOUND_SEQUENCE.search(text):
            missing.append(rel)
    assert missing == [], (
        "这几枚件持有「0001..尾号 连续」的主张，却没把期望值绑到唯一账本上："
        + ", ".join(missing)
        + "。写成 range(1, int(CATALOG_TAIL_VERSION) + 1) 才算钉住，换成 sorted(versions) 那种"
        "看着像在钉、实际永不红的形状不许。"
    )


def test_the_ledger_prose_documents_the_tail_it_holds():
    """判据②收尾：改口必须连主题一起写下来，不许只换一个数字。

    这条钉的是 docstring 里「现号」那一行的**形状**（现号：<四位版号>，主题 <主题名>），不写
    ``常量 in 散文`` 那种对判 —— 本文件开头那段来历本来就写着 0015 与 dataset_version_scope_
    columns，"数字出现在散文里"永远成立，那种钉是废钉。
    """
    found = _PRESENT_TAIL.search(_LEDGER_DOC)
    assert found is not None, (
        "账本 docstring 里必须有一行「现号：<四位版号>，主题 <那一版的主题名>」，改口时那一行"
        "要跟着改成最新那一版；现在一行都抠不出来。"
    )
    assert found.group("version") == CATALOG_TAIL_VERSION, (
        "「现号」那一行写的版号 " + found.group("version") + " 与账本常量 " + CATALOG_TAIL_VERSION
        + " 不同字：改数字必须连主题一起写下来，不许只换一半。"
    )
    assert found.group("name") == CATALOG_TAIL_NAME, (
        "「现号」那一行写的主题 " + found.group("name") + " 与账本常量 " + CATALOG_TAIL_NAME
        + " 不同字：新排一版要去那一行把这一版的主题写清楚。"
    )