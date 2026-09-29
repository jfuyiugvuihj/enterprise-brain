# -*- coding: utf-8 -*-
"""R493 · 常驻钉：血缘纸「受检范围」那两格叙述必须跟得上实物，且不许把历史账顺手清掉。

病灶（工单 R493 账②）：`docs/perf/r387-label-lineage-2026-09-27.md` §8.8 未做 3 与 §9.7 未做 4 都还写着
「受检的只有 §1 表 + §1 表下正文」。可今天的受检面早就扩了——§9.3 最后一列由
`test_r492_s93_column_matches_derived.py` 逐格管，§3 与 §8.7 那两格由 `test_r490_live_reads_match_derived.py`
管，无主区段里每一枚自称现读的坐标由 `test_r492_live_claim_boundary.py` 管，§9.5 那块计划表由
`r387_backfill_estimate.py --no-db --verify-plan-table` 逐字节管。叙述停在旧范围，下一班就会照着它派工。

本件钉两头：往回收不许（过期叙述不许留在纸上）；往外清也不许——§8.7 漂移账、§9.4 派工词对照账、
§9.5 更正那一笔这类**历史账原样留**，三格成对叙述逐枚按字节复认，谁当成"清理"随手改了本件当场红。
另钉一格 R493 没治的账：§3 段末那句用「今天」引出的那枚坐标不在甲类口径里（闸只认「现读」两个字），
本单一字未动它，只把这笔"看见但没治"钉成必须同时挂在纸上的两截——哨与账少一头即红。
全程只读盘上字节：零写口、不连库、不起服务、不打模型。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import test_r490_live_reads_match_derived as r490
import test_r492_live_claim_boundary as boundary

REPO = r490.REPO
DOC = r490.DOCS[0]
COPIED = re.compile(r":\d")
DIGEST = 16
BOM_LEN = 3
CLIP = 72

#: ① 过期叙述的具名形状（旧句里紧贴断言的那两截；新纸把它们放进「」引号并紧跟「已过期」）。
STALE_SHAPES = ("；受检的只有 §1", "），受检范围仍只有 §1")

#: ② 受检面清单必须点到的每一格（逐枚都是今天真在跑的对账口）。
SURFACES = ("teeth 逐跳", "正文闸", "§9.3 最后一列", "R490", "verify-plan-table", "边界闸", "已清零")

#: ④ 已做掉的范围不许再写成待办形状。
UNFINISHED = ("以后要做", "待办", "待补", "留待", "下一步将")

#: ⑤ 三格成对叙述：按内容锚定位，逐枚按 sha256 前 16 位复认（R492 并树时交回的就是这三枚）。
PAIRED = (("同值未改", "f650180e0e9fc769"),
          ("一处区间长度变了", "6e00b0634242d39d"),
          ("文档多出的内层 cite", "a0e2c19d8dc76a29"))

#: ⑥ 必须原样留档的历史账（判据不许顺手清理）。
HISTORY = ("研发 721", "静默过关", "46 枚锚是在", "不改 §2.3 原文", "75 枚锚块唯一命中普查")

#: ⑦ "看见但没治"那一格的哨与账，两截必须同时在场。
UNCURED_CLAIM = "把空值一路放行到"
UNCURED_NOTE = "本席看见但没治"

ITEM3 = "3. §2–§7 正文里那批**不自称现读**"
ITEM4 = "4. 文档 §5–§8 里那批**不自称现读**"


def rows():
    return r490.read_rows(DOC)


def one_line(mark):
    hits = [line for line in rows() if mark in line]
    assert len(hits) == 1, mark + " 命中 " + str(len(hits)) + " 枚，本该恰一枚"
    return hits[0]


def item_block(mark):
    """从那一格起，到下一枚列表项、标题或空行为止（列表续行以空白缩进）。"""
    lines = rows()
    hits = [i for i, line in enumerate(lines) if mark in line]
    assert len(hits) == 1, mark + " 命中 " + str(len(hits)) + " 枚，本该恰一枚"
    out = [lines[hits[0]]]
    for line in lines[hits[0] + 1:]:
        if not line.strip() or re.match(r"^\d+\.\s", line) or line.startswith("#"):
            break
        out.append(line)
    return "\r\n".join(out)


def cited_scripts(text):
    """清单里具名点到的件，逐枚回盘上验存在——把受检面写成不存在的钉，就是新的假话。"""
    return sorted({match.group(1) for match in re.finditer(r"([A-Za-z0-9_./-]+\.py)", text)})


# ---------------------------------------------------------------------------
# ①②③④ 受检范围：叙述必须跟得上实物
# ---------------------------------------------------------------------------

def test_the_two_stale_scope_sentences_are_gone() -> None:
    book = "\r\n".join(rows())
    for shape in STALE_SHAPES:
        assert shape not in book, "过期叙述还挂在纸上：" + shape


def test_the_scope_list_names_every_surface_that_bites() -> None:
    block = item_block(ITEM3)
    missing = [name for name in SURFACES if name not in block]
    assert not missing, "受检面清单漏点了这些真在跑的对账口：" + " / ".join(missing)


def test_every_nail_named_by_the_scope_list_exists() -> None:
    text = item_block(ITEM3) + "\r\n" + item_block(ITEM4)
    named = cited_scripts(text)
    assert named, "清单里一枚具名片都没点名：这格没在写受检面"
    for name in named:
        if "/" in name:
            assert (REPO / name).is_file(), "清单点名了一枚不存在的件：" + name
        else:
            hits = [folder for folder in ("tests", "scripts") if (REPO / folder / name).is_file()]
            assert hits, "清单点名了一枚不存在的件：" + name


def test_the_cured_scope_is_not_written_as_unfinished() -> None:
    for mark in (ITEM3, ITEM4):
        block = item_block(mark)
        said = [word for word in UNFINISHED if word in block]
        assert not said, "已经做掉的范围又写成待办形状：" + " / ".join(said) + " —— " + block[:CLIP]


# ---------------------------------------------------------------------------
# ⑤⑥⑦ 历史账不许被顺手清理，没治的那一笔不许被悄悄抹掉
# ---------------------------------------------------------------------------

def test_the_three_paired_narratives_are_byte_equal() -> None:
    for mark, digest in PAIRED:
        line = one_line(mark)
        got = hashlib.sha256(line.encode("utf-8")).hexdigest()[0:DIGEST]
        assert got == digest, mark + " 那一格已被改写：sha256 前 16 位 " + got + " != 在册 " + digest


def test_the_history_accounts_that_must_stay_are_untouched() -> None:
    book = "\r\n".join(rows())
    for needle in HISTORY:
        assert needle in book, "历史账被清理了一格，读不出：" + needle
    assert boundary.guard_defects(boundary.guard_paragraph(rows())) == [], "§1 表旁那句自守的形状坏了"


def test_the_uncured_clause_is_still_reported_not_erased() -> None:
    book = "\r\n".join(rows())
    assert UNCURED_CLAIM in book, "§3 那一格不见了：要么已被另行治掉（要连本件与 §9.8 第 ⑤ 格一起收），要么是被悄悄删了"
    assert UNCURED_NOTE in book, "§9.8 第 ⑤ 格那笔「看见但没治」的账不在了：不许删账遮住没做到"
    assert book.count(UNCURED_CLAIM) == 1, UNCURED_CLAIM + " 读出多枚：那一格又长出第二处了"


# ---------------------------------------------------------------------------
# ⑧ 纸面形态与本件自证
# ---------------------------------------------------------------------------

def test_the_book_is_still_pure_crlf() -> None:
    blob = (REPO / DOC).read_bytes()
    cr = blob.count(b"\r")
    lf = blob.count(b"\n")
    assert cr == lf == blob.count(b"\r\n"), "换行符不再成对：CR=" + str(cr) + " LF=" + str(lf)
    assert blob[0:BOM_LEN] != b"\xef\xbb\xbf", "本文档长出了 BOM"
    assert blob.decode("utf-8").count(chr(0xfffd)) == 0, "本文档读出了替换字符（编码被动过）"


def test_this_pin_carries_no_copied_coordinates() -> None:
    source = Path(__file__).resolve().read_bytes().decode("utf-8")
    bad = [line.strip()[:CLIP] for line in source.splitlines() if COPIED.search(line)]
    assert not bad, "本件里长出抄来的行号：" + " / ".join(bad)


def test_this_pin_writes_nothing_to_the_deriver() -> None:
    before = r490.tool_bytes()
    test_the_scope_list_names_every_surface_that_bites()
    assert r490.tool_bytes() == before, "本件在取证时动了那支取档脚本"
