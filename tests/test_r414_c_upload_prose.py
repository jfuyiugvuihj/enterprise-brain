# -*- coding: utf-8 -*-
r"""R414 (c) · ``chat.py`` 里那枚漏在源码里的字面转义，连着同一句的双写撇号一起改干净。

改前现场读数（现读，符号名锚点）：``app/api/v1/chat.py::upload_document`` 的 docstring 里，
"…publish into somebody else" 后面跟的是**六枚字符** ``\u2019``（不是右单引号 U+2019），
同一行还有 ``uploader''s`` 双写撇号。字节级取证两把，改前⇒改后：

    盘上字节里字面反斜杠-u-2-0-1-9 的枚数  ->  1 => 0
    同一枚字节 decode 以后真 U+2019 的枚数  ->  0 => 0

第二把说的是：源码从来就没写对过。docstring 是普通字符串字面量，Python 在**运行期**把这六枚
字符解释成了一枚右单引号，所以渲染出来的正文是对的、源码是错的 —— 于是只在 ``__doc__`` 上断言
量不到这一格，本件按 ``inspect.getsource`` 读源码文本。同一枚口径见
``docs/handoff/2026-09-27-v2-gap-recheck-2.md`` 的「症状 c」（它给的正是这两把字节尺）。

范围：只改这一处英文散文。全仓同类漏网的枚数与路径列在交回单里（明令「只报不改写域外的」），
本件只在写域内那一枚文件上钉死它不许再长回来。

🔴 本文件自己就是这一族坑的活靶：任何一枚**非 raw** 字符串里裸写反斜杠-u，轻则被运行期解释、
重则直接 SyntaxError（本件第一版就红在 ``\u`` 后面跟了一枚空格，而那枚 raw 前缀写进正文里又把文档串提前收了口）。所有提到它的串一律走 raw 前缀。
"""
import inspect
import pathlib
import re

from app.api.v1 import chat

#: 反斜杠用 chr(92) 现取：本仓文件按 CRLF 检出，字面量里手打反斜杠很容易被编辑器改掉（R142 同口径）。
BS = chr(92)
#: 源码里那枚漏网的六字符转义。
LEAKED_ESCAPE = BS + "u2019"
#: 同一句里的双写撇号。
DOUBLED_APOSTROPHE = "''"
#: 正则里的反斜杠要成对，不与上面那枚混用。
ESCAPE_PATTERN = re.compile(BS + BS + "u[0-9a-fA-F]{4}")
ANCHOR_PHRASE = "somebody else"


def _upload_source() -> str:
    """读 ``upload_document`` 的**源码文本**（不是 ``__doc__``）：要看的正是字节。"""
    return inspect.getsource(chat.upload_document)


def test_that_sentence_carries_neither_the_leaked_escape_nor_a_doubled_apostrophe():
    r"""反证：在影子树上把这一行退回 else + 六字符转义 + uploader 双撇号，本枚当场红。"""
    source = _upload_source()
    lines = [line for line in source.splitlines() if ANCHOR_PHRASE in line]
    assert len(lines) == 1, "锚点句不唯一或不见了（读到的：" + repr(lines) + "）"
    line = lines[0]

    assert LEAKED_ESCAPE not in line, "字面转义又回来了：" + repr(line)
    assert DOUBLED_APOSTROPHE not in line, "双写撇号又回来了：" + repr(line)
    assert "somebody else's results" in line, line
    assert "The uploader's own" in line, line


def test_the_upload_docstring_is_clean_english_prose_end_to_end():
    """两个口径一起钉：源码字节里没有，渲染出来的正文里也没有。"""
    source = _upload_source()
    docstring = chat.upload_document.__doc__ or ""

    assert LEAKED_ESCAPE not in source, "源码字节里还有字面转义"
    assert DOUBLED_APOSTROPHE not in " ".join(source.splitlines()), "源码里还有双写撇号"
    assert LEAKED_ESCAPE not in docstring and DOUBLED_APOSTROPHE not in docstring
    assert "uploader's own department" in " ".join(docstring.split()), docstring


def test_chat_py_carries_no_literal_unicode_escape_anywhere():
    """写域内那枚文件整体钉死：反斜杠-u + 四位十六进制一枚都不许有。

    这一族的合法用法（正则字符类、码位比较、控制符）今天没有一枚落在 ``chat.py`` 里，所以钉成
    零而不是钉成名单——名单就是下一本手抄账。哪天真需要一枚码位比较，改的是这条判据的口径，
    不是往名单里塞一行。
    """
    text = pathlib.Path(chat.__file__).read_text(encoding="utf-8")
    found = ESCAPE_PATTERN.findall(text)

    assert found == [], found[:5]
