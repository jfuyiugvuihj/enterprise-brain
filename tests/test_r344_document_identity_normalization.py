# -*- coding: utf-8 -*-
r"""R344 判据 ②：文档名归一口径必须与前端的 ``documentIdentityKey`` 逐字同语义。

这道筛法一旦落到服务端，前后端就对「同一篇文档」共用一个词。所以这里的判据不是「差不多
就行」，而是**逐字同语义**：先删掉全部 ECMAScript ``\s`` 匹配的字符，再做小写折叠。两枚
会翻车的细节各由一组钉住死：

① ``.lower()`` 而不是 ``.casefold()``。JS ``toLowerCase()`` 原样留着 ``ß``，casefold 把它
   展开成 ``ss``；服务端要是走了 casefold，就会认出前端认不出的文档对——两套房各有一套口径。
② 空白集合不许照抄 Python。实测（``node -e "String(v).replace(/\s+/g, '').toLowerCase()"``）：
   JS 的 ``\s`` **含** ``U+FEFF``，而 Python 的 ``re.\s`` 与 ``str.isspace()`` 都不含；反过来
   Python 还多吃了 ``U+001C``-``U+001F`` 与 ``U+0085``。两族之差必须由一张显式表闭合，
   ``U+200B`` 两头都不算空白，所以它留在名字里，是身份的一部分而不是可擦掉的排版。

下面这张成对样本表的期望读数是**真 JS 引擎现量**取来的（脚本只喂 ``String(v ?? '').replace(/\s+/g,
'').toLowerCase()`` 这一条式子），不是按 Python 的形状反推出来的——否则这一格就成了自我印证。
表里的 ``\uXXXX`` 全部是显式转义：不可见字符写在源码里就是给下一个读文件的人猜谜。
"""
from __future__ import annotations

import re

import pytest

from app.knowledge_graph import service
from app.knowledge_graph.service import document_identity_key

#: (输入原文, 前端 documentIdentityKey 的读数)。取法见模块 docstring。
PAIRED_SAMPLES = [
    ("员工手册", "员工手册"),
    (" 员工手册 ", "员工手册"),
    ("员工\u0009手册", "员工手册"),
    ("员工\u3000手册", "员工手册"),
    ("员工\u00a0手册", "员工手册"),
    ("员工\u200b手册", "员工\u200b手册"),
    ("\ufeff员工手册", "员工手册"),
    ("员工\u0085手册", "员工\u0085手册"),
    ("员工\u001f手册", "员工\u001f手册"),
    ("员工\u2028手册", "员工手册"),
    ("员工\u2029手册", "员工手册"),
    ("员工\u2009手册", "员工手册"),
    ("员工\u202f手册", "员工手册"),
    ("员工\u205f手册", "员工手册"),
    ("员工\u1680手册", "员工手册"),
    ("员工\u000d\u000a手册", "员工手册"),
    ("员工\u000b手册", "员工手册"),
    ("员工\u000c手册", "员工手册"),
    ("STAFF Handbook", "staffhandbook"),
    ("差旅管理办法.PDF", "差旅管理办法.pdf"),
    ("差旅管理办法.pdf", "差旅管理办法.pdf"),
    ("差旅管理办法\u3000PDF", "差旅管理办法pdf"),
    ("Straße", "straße"),
    ("\u0130", "i\u0307"),
    ("   ", ""),
    ("", ""),
    ("员工Handbook 手册", "员工handbook手册"),
]

#: 前端判「同一篇」的一对名字：归一必须把它们折成同一个键（判据②反证刀B 的正身）。
SAME_DOCUMENT_PAIRS = [
    ("差旅管理办法.PDF", "差旅管理办法.pdf", "大小写不参与身份"),
    ("员工手\u3000册.pdf", "员工手册.pdf", "登记时手打的 U+3000 不参与身份"),
    ("\ufeff员工手册.pdf", "员工手册.pdf", "BOM 在 ECMAScript 的 \\s 里，被擦掉"),
    ("员工\t手册.pdf", "员工手册.pdf", "Tab 同理"),
    (" 员工手册.pdf ", "员工手册.pdf", "首尾空白同理"),
    ("STAFF Handbook", "staff handbook", "英文篇名的大小写与空格同理"),
]

#: 前端判「不是一篇」的一对名字：差一个字、多一个零宽字符都不许折成同一个键。
DIFFERENT_DOCUMENT_PAIRS = [
    ("员工手册", "员工手册.pdf", "差一个扩展名就是另一篇"),
    ("员工手册", "员工手册补充规定", "多四个字就是另一篇"),
    ("员工手册", "员工\u200b手册", "U+200B 两头都不算空白，它是名字的一部分"),
    ("员工手册", "员工\u0085手册", "U+0085 不在 ECMAScript 的 \\s 里，它也不算空白"),
    ("Straße.pdf", "Strasse.pdf", "casefold 才会把这俩折成一篇，前端不折"),
    ("İ", "i", "İ 折成 i+U+0307，比裸 i 长一枚组合字符"),
]


@pytest.mark.parametrize(("raw_name", "expected_key"), PAIRED_SAMPLES)
def test_paired_samples_match_the_javascript_reading(raw_name: str, expected_key: str) -> None:
    """同一枚输入喂给 Python 与前端式子，读数必须一字不差。"""
    assert document_identity_key(raw_name) == expected_key


@pytest.mark.parametrize(("left", "right", "why"), SAME_DOCUMENT_PAIRS)
def test_the_pairs_the_browser_calls_one_document_are_one_document(left: str, right: str, why: str) -> None:
    assert document_identity_key(left) == document_identity_key(right), why


@pytest.mark.parametrize(("left", "right", "why"), DIFFERENT_DOCUMENT_PAIRS)
def test_the_pairs_the_browser_keeps_apart_stay_apart(left: str, right: str, why: str) -> None:
    assert document_identity_key(left) != document_identity_key(right), why


def test_the_whitespace_set_is_the_ecmascript_one_and_not_python_s() -> None:
    """显式表必须正好是 ECMA-262 的 WhiteSpace ∪ LineTerminator，并与 Python 的 ``\s`` 有牙。

    这一格堵的是「顺手换成 ``re.sub(r\"\\s+\", \"\", ...)`` 或 ``.split()``」那一路：那两套
    集合在这里各有出入，抄过来当天就多出第二套口径，而且红得毫无道理——所以两头之差逐码点写死。
    """
    ecmascript = frozenset(
        {
            0x0009,  # TAB
            0x000A,  # LF
            0x000B,  # VT
            0x000C,  # FF
            0x000D,  # CR
            0x0020,  # SP
            0x00A0,  # NBSP
            0x1680,  # OGHAM SPACE MARK
            *range(0x2000, 0x200B),  # EN QUAD .. HAIR SPACE
            0x2028,  # LINE SEPARATOR
            0x2029,  # PARAGRAPH SEPARATOR
            0x202F,  # NARROW NO-BREAK SPACE
            0x205F,  # MEDIUM MATHEMATICAL SPACE
            0x3000,  # IDEOGRAPHIC SPACE
            0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
        }
    )
    assert frozenset(service._JS_WHITESPACE_CODE_POINTS) == ecmascript

    python_s = frozenset(cp for cp in range(0x110000) if re.match(r"\s", chr(cp)))
    # Python 多吃的：JS 认它是正文的一部分，所以归一不许擦。
    assert python_s - ecmascript == frozenset({0x001C, 0x001D, 0x001E, 0x001F, 0x0085})
    # Python 少吃的一枚：JS 认它是空白，所以归一必须擦。
    assert ecmascript - python_s == frozenset({0xFEFF})
    # ``str.split()`` 走的是 ``str.isspace()``，与 ``re.\s`` 同族，同样缺 U+FEFF。
    assert "\ufeff员工手册".split() == ["\ufeff员工手册"]


def test_lower_is_used_and_not_casefold() -> None:
    """``ß`` 不许展开成 ``ss``，``İ`` 不许折成裸 ``i``：这两格是 casefold 的签名。"""
    assert document_identity_key("Straße") == "straße"
    assert document_identity_key("Straße") != "Straße".casefold()
    assert document_identity_key("\u0130") == "i\u0307"
    assert len(document_identity_key("\u0130")) == 2


def test_a_name_with_no_identity_is_the_empty_key() -> None:
    """空名与纯空白名都折成空串——调用方拿它当「没填」，不许它匹配任何一篇。"""
    assert document_identity_key(None) == ""
    assert document_identity_key("") == ""
    assert document_identity_key(" \u3000\u00a0\ufeff\t") == ""


def test_the_key_is_idempotent() -> None:
    """归一两次与归一一次同读数：键值可安全重复计算，不给缓存留第二套形状。"""
    for raw_name, _ in PAIRED_SAMPLES:
        once = document_identity_key(raw_name)
        assert document_identity_key(once) == once
