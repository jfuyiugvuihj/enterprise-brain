# -*- coding: utf-8 -*-
"""R670 · 流式那一发的计量尺：报了的必须落账，没报的必须留 NULL，两头都不许造数。

计划书 R38 判据③ 说「抽查一问，``input_tokens/output_tokens`` 非零且与 Ollama 自报一致」。
``app/trace/spans.py::stream_usage_counts`` 是本单为**流式形状**开的那道口子：一条流把计数
塞在末片里，而不是塞在一枚 reply 对象上，``app/trace/spans.py::model_token_counts`` 那两种
形状都接不住它（R38 当年断的就是这一格）。

本件只判四件事，每件都可失败：

1. 一枚报了数的 usage block ⇒ 两枚列等于**服务端自己报的那两枚数**，逐枚相等；
2. 同一枚事实的两种拼写（兼容腿 ``prompt_tokens`` / 原生腿 ``prompt_eval_count``）读回同一个数，
   尺子只挑拼写，不做换算 —— 没有减法、没有 prompt 减 cached、没有估算；
3. ``cached_tokens`` 只在报了的形状上出现；缺它时那一格是键缺席（列就是 NULL），**绝不是 0**
   （``app/common/model_handler.py`` 的在册规矩：绝不默认成 0）；一枚**报出来的 0** 原样留着；
4. 压根没有 usage block（今天兼容腿流式的真实形状：没开 ``stream_options.include_usage``）
   ⇒ 两枚列 NULL、``usage_keys`` 交回空列表 ——「这一轮没说」与「这一轮数是 0」是两张脸。

全程离线：不连模型、不起服务、不开 socket、不碰数据库。
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.trace.spans import (
    USAGE_CACHED_KEYS,
    USAGE_INPUT_KEYS,
    USAGE_OUTPUT_KEYS,
    model_token_counts,
    stream_usage_counts,
)

#: 夹具里那枚「Ollama 自己报的数」只有一个来源：下面这两份字面量就是夹具本身。判据「与 Ollama
#: 自报一致」量的是尺子搬不搬运得动，不是这台机今天报不报得出数 —— 真机那一格由凭据纸
#: ``docs/testing/r670-2026-10-05.md`` 现读，不在这里冒充。
@pytest.fixture(scope="module")
def root() -> Path:
    return Path(__file__).resolve().parents[1]


COMPAT_USAGE = {
    "prompt_tokens": 3955,
    "completion_tokens": 245,
    "total_tokens": 4200,
    "prompt_tokens_details": {"cached_tokens": 467},
}
NATIVE_USAGE = {
    "prompt_eval_count": 3955,
    "eval_count": 245,
    "prompt_eval_cached_count": 467,
}


def test_the_compat_shape_lands_both_numbers_the_server_reported():
    counts = stream_usage_counts(COMPAT_USAGE)

    assert counts["input_tokens"] == COMPAT_USAGE["prompt_tokens"]
    assert counts["output_tokens"] == COMPAT_USAGE["completion_tokens"]
    assert counts["cached_tokens"] == COMPAT_USAGE["prompt_tokens_details"]["cached_tokens"]
    assert counts["usage_keys"] == sorted(COMPAT_USAGE)


def test_the_native_shape_meters_the_same_fact_under_its_own_names():
    """同一台服务器、两种拼写：读回的数必须逐枚相等，拼写不是丢数的理由。"""
    compat = stream_usage_counts(COMPAT_USAGE)
    native = stream_usage_counts(NATIVE_USAGE)

    assert native["input_tokens"] == compat["input_tokens"] == 3955
    assert native["output_tokens"] == compat["output_tokens"] == 245
    assert native["cached_tokens"] == compat["cached_tokens"] == 467


def test_a_usage_object_from_the_client_is_the_same_fact_as_a_dict():
    """``openai`` 交回的是模型不是 dict：只认 dict 就是把一枚报了数的轮次读成没报。"""

    class _Usage:
        def model_dump(self):
            return dict(COMPAT_USAGE)

    counts = stream_usage_counts(_Usage())

    assert counts["input_tokens"] == 3955
    assert counts["usage_keys"] == sorted(COMPAT_USAGE)


def test_no_usage_block_is_a_reading_not_a_zero():
    """今天兼容腿流式没开 ``include_usage`` 就是这个形状：两枚 NULL、键名集合为空。"""
    counts = stream_usage_counts(None)

    assert counts == {"input_tokens": None, "output_tokens": None, "usage_keys": []}
    assert "cached_tokens" not in counts
    assert json.dumps(counts)


def test_a_missing_cached_side_stays_absent_and_a_reported_zero_stays_zero():
    """判据 2 的那半枚牙：缺 cached ⇒ 键缺席（列就是 NULL），报 0 ⇒ 原样是 0。"""

    silent = stream_usage_counts({"prompt_tokens": 116, "completion_tokens": 7})
    assert "cached_tokens" not in silent, "默认成 0 就是把「没说」写成「数过是 0」"

    reported_zero = stream_usage_counts(
        {
            "prompt_tokens": 116,
            "completion_tokens": 7,
            "prompt_tokens_details": {"cached_tokens": 0},
        }
    )
    assert reported_zero["cached_tokens"] == 0, "服务端报的 0 是读数，不许被当成缺格丢掉"


def test_the_meter_never_invents_the_side_it_did_not_get():
    """单边报数就只落单边：尺子里没有任何一条算术路径能造出另一边。"""
    one_sided = stream_usage_counts({"prompt_eval_count": 900})

    assert one_sided["input_tokens"] == 900
    assert one_sided["output_tokens"] is None
    assert one_sided["usage_keys"] == ["prompt_eval_count"]


def test_a_non_integer_count_is_not_a_number():
    """字符串与小数都不算「服务端报了一枚数」：宁可留 NULL，不许尺子现编类型。

    🔴 布尔不在这一列里：``app/trace/spans.py::_reported_count`` 的在册口径是
    ``isinstance(value, int)``，而 ``bool`` 是 ``int`` 的子类 —— ``True`` 今天会被当成一枚数搬走。
    那是那枚在册尺的形状，本单不偷偷改它（改它要连着 ``tests/test_r38_native_input_tokens.py``
    与 ``tests/test_r146_cached_token_ledger.py`` 一起判，属另一枚单），本件也不把它钉成正确。
    """
    for junk in ("3955", 39.0, None, ["3955"], {}):
        counts = stream_usage_counts({"prompt_tokens": junk, "completion_tokens": 3})
        assert counts["input_tokens"] is None, junk
    assert stream_usage_counts({"prompt_tokens": 0, "completion_tokens": 3})["input_tokens"] == 0


def test_the_key_names_come_from_the_block_itself():
    """``usage_keys`` 是那块东西自己的键名，不是尺子挑中的那几枚：多一格就多半格账。"""
    block = dict(COMPAT_USAGE)
    block["reasoning_tokens"] = 22

    assert "reasoning_tokens" in stream_usage_counts(block)["usage_keys"]
    assert stream_usage_counts(block)["usage_keys"] == sorted(block)


def _product_leg_text(root: Path, path: Path) -> str:
    """一枚源文件的正文，但把本单新写的三张拼写表本身摘掉。

    不摘就是自证：拼写表里写了什么，尺子就在盘上"读"到什么。摘掉之后还在的，才是**别人**
    早就在读的名字 —— ``app/common/model_handler.py::_native_chat`` 读原生腿那两枚，
    ``app/common/model_handler.py::compat_reply`` 读兼容腿那两枚，
    ``app/trace/spans.py::_cached_token_count`` 读 LangChain 改名的那一枚。
    """
    text = path.read_text(encoding="utf-8")
    if path.name == "spans.py":
        text = re.sub(r"^USAGE_\w+ = \(.*?\)$\n", "", text, flags=re.MULTILINE | re.DOTALL)
    return text


@pytest.mark.parametrize(
    "name",
    sorted(set(USAGE_INPUT_KEYS) | set(USAGE_OUTPUT_KEYS) | set(USAGE_CACHED_KEYS)),
)
def test_every_spelling_is_a_name_the_product_already_reads(name, root):
    """拼写表逐枚对账：每一枚都必须已被在册某条腿读过。本单不新造服务端字段名。"""
    read_it = any(
        name in _product_leg_text(root, path) for path in (root / "app").rglob("*.py")
    )
    assert read_it, "%s 没有任何一条在册腿读过：尺子在认一枚机器从没说有过的字段" % name


def test_model_token_counts_keeps_its_two_shapes_untouched():
    """本单是加法：``model_token_counts`` 那两种形状一个字节不改（R29 与 R38 各自钉着它）。"""
    reply = SimpleNamespace(input_tokens=11, output_tokens=7)

    assert model_token_counts(reply) == {"input_tokens": 11, "output_tokens": 7}
    assert "usage_keys" not in model_token_counts(reply), (
        "旧尺子的输出形状不许变：变了就把 tests/test_r29_thinking_tax.py 那枚 set(...) 判据顶掉了"
    )