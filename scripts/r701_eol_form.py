"""R701 · 盘形行尾谓词的单一真源。

病根：仓库没有 .gitattributes、本机 core.autocrlf=true，于是同一枚 blob 在
「干净检出／git archive」里是成对 CRLF，在「Linux 克隆／autocrlf=input」里是纯 LF。
在册那些钉原先把其中一种盘形当成了产品事实来钉（要求 CR 枚数必须等于 LF 枚数，
或反过来要求一个 CR 都不许有），结果每一笔并树都要重新误红一次、重新归因一次。

本模块只回答一个问题：**这一篇文本的行尾整不整齐**。两种形状都合格——
纯 LF（CR 枚数＝0）与成对 CRLF（CR 枚数＝LF 枚数）；不合格只有一种：混着来
（既有裸 CR 又有裸 LF）。文本内容该不该相等，仍由各钉自己判，本模块不放松任何比较。
"""

from __future__ import annotations


def counts(raw):
    """交回 (CR 枚数, LF 枚数)。字节与文本都吃，因为在册钉两形都在用。"""
    if isinstance(raw, bytes):
        return raw.count(b"\r"), raw.count(b"\n")
    return raw.count("\r"), raw.count("\n")


def pairs(raw) -> int:
    """CRLF 成对的枚数（bytes 与 str 都吃）。"""
    return raw.count(b"\r\n") if isinstance(raw, bytes) else raw.count("\r\n")


def is_uniform(raw) -> bool:
    """纯 LF，或每一枚 CR 都紧跟一枚 LF 且两数相等，才算合格。

    光看「CR 枚数 == LF 枚数」会放过 `甲\n乙\r丙\r\n`（CR=2、LF=2 却混着来），
    所以成对枚数必须一起数：只有 pair == cr == lf 才是真·成对 CRLF。
    """
    cr, lf = counts(raw)
    if cr == 0:
        return True
    return cr == lf and pairs(raw) == cr


def to_lf(data: bytes) -> bytes:
    """把成对 CRLF 折回 LF，用于跨盘形的逐字节比较；孤立 CR 不动（那是病，得留着）。"""
    return data.replace(b"\r\n", b"\n")


def assert_uniform(raw, label: str = "") -> None:
    """不合格就抛 AssertionError，并把两种合格形状与实测枚数一起写进话里。"""
    if is_uniform(raw):
        return
    cr, lf = counts(raw)
    raise AssertionError(
        (label or "本篇")
        + " 的行尾混了：CR=" + str(cr) + " 而 LF=" + str(lf)
        + "，成对 CRLF 只有 " + str(pairs(raw)) + " 枚。"
        + " 盘形由 core.autocrlf/.gitattributes 决定，钉不许拿它当产品事实。"
    )


def check_bytes(data: bytes, label: str = "") -> bytes:
    """逐字节读进来的东西：先证行尾整齐，再交回按 LF 归一后的同一份字节。"""
    assert_uniform(data, label)
    return to_lf(data)


__all__ = ["counts", "pairs", "is_uniform", "to_lf", "assert_uniform", "check_bytes"]