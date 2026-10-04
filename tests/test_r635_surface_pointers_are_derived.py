# -*- coding: utf-8 -*-
"""R635 判据①②③ —— 观测面整本的坐标清零、锚点枚枚真解析、枚数尺铺到每一格。

对判据的哪一条（派工词 R635）：
  ① 现取 `app/api/v1/observability.py` 里形如「文件点 py 冒号数字」的手抄坐标，枚数必须为零；
     派工词那枚正则与更宽的一枚（文件名带数字或短横）同时上，两把都零才算过。
  ② 每一枚 `文件::符号` 锚点都必须真解析得到——符号必须在那枚文件的源码里定义，点号链逐层可
     下钻。牙走 AST 腿而不是 import 腿：`app/api/v1/chat.py` 在模块级就构造 DocumentRetriever()，
     在 pytest 之外 import 它耗时以秒计、还会朝被 git 跟踪的 ./chroma_db 写回（仓库根
     conftest.py 记的正是这一笔），而派工同时禁连库、禁动盘面。AST 腿与在册运行时腿
     （`r630.resolve_symbol`）的同判关系由本件一枚用例钉住，防止「另立一套更松的尺」。
  ③ R630 那把尺（形状约定 + `roster_count_offenders` 那一族）扩覆盖到整本 `SLO_BLOCKERS` 的
     每一格 detail 与 `slo_readout()` 的每一枚字符串叶子；派生源与尺子都在
     `tests/test_r630_first_token_pointer_is_derived.py` 里新增，本件不抄第二份平行实现。

零 IO：只读盘上源码文本与内存对象，不起服务、不连库、不打模型、不动容器。
反证刀在 `tests/test_r635_counter_evidence_teeth.py`，与本件共用同一枚尺。
"""
from __future__ import annotations

import re
import sys

import pytest

import test_r526_slot_caliber_closure as r526
import test_r630_first_token_pointer_is_derived as r630
from app.api.v1 import observability

REPO = r630.REPO
OBSERVABILITY = r630.OBSERVABILITY

#: 派工词判据① 点名那枚正则的原文形状：不放宽，也不收窄。
TICKET_COORDINATE = re.compile(r"[A-Za-z_/]+\.py:[0-9]+")
#: 更宽的一枚：文件名里带数字或短横（`test_r630_…py:` 那一形）同样算手抄坐标。
ANY_COORDINATE = re.compile(r"[A-Za-z0-9_./-]+\.py:[0-9]+")

#: 名册那本书的键前缀（`r630.surface_texts` 交回的落点名）。
BOOK = "SLO_BLOCKERS"


def surface_source() -> str:
    return OBSERVABILITY.read_text(encoding="utf-8")


def texts_on_the_ruler() -> list[tuple[str, str]]:
    """现在这把尺到底扫了哪几格：逐枚点名，coverage 不靠注释维持。"""
    return r630.surface_texts()


def anchor_census() -> set[str]:
    """源文 ∪ 名册 ∪ 回执 里出现过的每一枚锚点，拼成 `文件::符号` 的集合。"""
    found: set[str] = set()
    chunks = [surface_source()] + [prose for _path, prose in texts_on_the_ruler()]
    for text in chunks:
        for rel, dotted in r630.WIDE_ANCHOR.findall(text):
            found.add("%s::%s" % (rel, dotted))
    return found


def unresolvable(anchors) -> list[str]:
    return sorted(row for row in anchors if not r630.anchor_resolves(*row.split("::")))


# ==================== 判据① —— 手抄坐标清零（并且这枚尺不是空的）====================


def test_no_hand_copied_coordinate_survives_anywhere_in_the_module() -> None:
    """判据① 的正面读数：整本源文（含注释与文档串）零枚坐标，两把尺同判。"""
    source = surface_source()
    assert TICKET_COORDINATE.findall(source) == []
    assert ANY_COORDINATE.findall(source) == []
    assert r630.LINE_ANCHOR.findall(source) == []


def test_no_hand_copied_coordinate_survives_in_any_published_leaf() -> None:
    """判据① 的活体面：名册每一格与回执每一枚叶子交回后同样零枚——拼串也躲不过。"""
    offenders = []
    for path, prose in texts_on_the_ruler():
        hits = TICKET_COORDINATE.findall(prose) + ANY_COORDINATE.findall(prose)
        if hits:
            offenders.append("%s %s" % (path, sorted(set(hits))))
    assert offenders == [], offenders


def test_the_coordinate_ruler_would_bite_if_a_number_came_back() -> None:
    """死尺前置：把坐标拆开来现场拼出再喂尺子，它必须咬——否则上面的零什么都量不出。"""
    forged = "app/common/stage_timing.py" + ":" + "7" + "1"
    assert TICKET_COORDINATE.findall(forged) == [forged]
    assert ANY_COORDINATE.findall(forged)
    assert r630.shape_violations("see " + forged) != []


# ==================== 判据② —— 锚点枚枚真解析 ====================


def test_the_surface_names_anchors_and_not_line_numbers() -> None:
    """尺子有的可量：锚点清单非空，且源文里点名过的每一枚 `app/**` 文件都配得上锚点。"""
    assert anchor_census(), "整本观测面一枚锚点都没有：判据② 成了空转"


def test_every_anchor_on_the_surface_resolves_from_source() -> None:
    """判据② 正文：每一枚锚点的目标符号都现读得到，解析不到的逐枚点名。"""
    assert unresolvable(anchor_census()) == []


def test_a_fabricated_symbol_dies_on_both_legs_of_the_ruler() -> None:
    """判据② 的正控：把一枚在册锚点的符号名换成一枚不存在的，AST 腿与运行时腿同判红。"""
    rows = [pair.split("::") for pair in sorted(anchor_census())]
    assert rows, "锚点清单为空：本例前提变了"
    rel, dotted = rows[0]
    ghost = "%s_ghost_symbol" % dotted.split(".")[0]
    assert r630.anchor_resolves(rel, dotted) is True
    assert r630.anchor_resolves(rel, ghost) is False
    if sys.modules.get(rel[: -len(".py")].replace("/", ".")) is not None:
        with pytest.raises(AttributeError):
            r630.resolve_symbol(rel, ghost)


def test_the_ast_leg_and_the_runtime_leg_agree_on_every_module_in_memory() -> None:
    """AST 腿不许比在册运行时腿松：模块已在内存的每一枚锚点，两枚尺必须同判绿。"""
    checked: list[str] = []
    for row in sorted(anchor_census()):
        rel, dotted = row.split("::")
        module = sys.modules.get(rel[: -len(".py")].replace("/", "."))
        if module is None:
            continue
        runtime = True
        try:
            r630.resolve_symbol(rel, dotted)
        except (ImportError, AttributeError, ValueError):
            runtime = False
        assert r630.anchor_resolves(rel, dotted) is runtime, row
        checked.append(row)
    assert checked, "两枚腿一枚都没对上：这枚同判用例是空的"


# ==================== 判据③ —— 尺子覆盖整本名册与回执叶子 ====================


def test_the_ruler_feeds_every_cell_of_the_blocker_book() -> None:
    """`SLO_BLOCKERS` 的每一格都在尺上，键名逐枚对账，不靠「应该都扫到了」。"""
    seen = {path.split("/", 1)[1] for path, _prose in texts_on_the_ruler() if path.startswith(BOOK + "/")}
    assert seen == set(getattr(observability, BOOK)), sorted(
        set(getattr(observability, BOOK)) ^ seen
    )


def test_the_ruler_feeds_every_string_leaf_of_the_receipt() -> None:
    """回执那一侧同样逐枚点名：叶子数现取，且非零枚散文真的在尺上。"""
    payload = observability.slo_readout()
    leaves = list(r630.string_leaves(payload))
    on_ruler = [path for path, _prose in texts_on_the_ruler() if path.startswith("readout")]
    assert len(on_ruler) == len(leaves), (len(on_ruler), len(leaves))
    assert on_ruler, "回执一枚字符串叶子都没进尺"


def test_the_widened_surface_reports_nothing_on_the_live_disk() -> None:
    """判据①②③ 的总正控：真盘面上这把放宽的尺零违规（反证刀共用同一枚函数）。"""
    assert r630.surface_shape_violations() == []
    assert r630.surface_roster_offenders() == []


def test_no_published_or_registry_prose_types_a_roster_count() -> None:
    """枚数那一族同样铺满：名册整本 ＋ 回执，任何一格手写名册枚数都当场点名。"""
    offenders = r630.surface_roster_offenders()
    assert offenders == [], offenders


# ==================== 本件自己先过一遍尺 ====================


def test_this_file_itself_copies_no_coordinate_and_no_magnitude() -> None:
    """钉自己不许抄坐标，也不许把量级或手写枚数写进散文（R526／R630 那两把尺复用）。"""
    from pathlib import Path

    source = Path(__file__).resolve().read_text(encoding="utf-8")
    assert TICKET_COORDINATE.findall(source) == []
    assert ANY_COORDINATE.findall(source) == []
    assert r630.LINE_ANCHOR.findall(source) == []
    assert r526.find_magnitudes(source) == []
    assert re.search(r"\b\w+\s+of\s+the\s+\w+\s+budget\s+tiers\b", source, re.IGNORECASE) is None
    for rel, dotted in r630.WIDE_ANCHOR.findall(source):
        assert r630.anchor_resolves(rel, dotted), "%s::%s" % (rel, dotted)
