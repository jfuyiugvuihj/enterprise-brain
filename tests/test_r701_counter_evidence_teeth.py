"""R701 的反证牙：盘形行尾谓词只准认「整齐」，不准认「某一种盘形」，也不准掩盖手改。

全程离线：零 `app` import、零容器、零模型、零真库；写盘只写 tmp_path。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, "加载不到：" + str(path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


eol = _load("r701_eol_form_teeth", REPO / "scripts" / "r701_eol_form.py")

READOUT = REPO / "docs" / "testing" / "r469-sandbox-scope-readout-2026-09-28.md"
LINEAGE = REPO / "docs" / "perf" / "r387-label-lineage-2026-09-27.md"


def test_two_good_forms_are_both_accepted():
    """纯 LF 与成对 CRLF 都是健康的盘形——两形都必须过，缺一枚就是量 checkout。"""
    good_lf = "第一行\n第二行\n"
    good_crlf = "第一行\r\n第二行\r\n"
    assert eol.is_uniform(good_lf) is True
    assert eol.is_uniform(good_crlf) is True
    assert eol.is_uniform(good_lf.encode("utf-8")) is True
    assert eol.is_uniform(good_crlf.encode("utf-8")) is True
    eol.assert_uniform(good_crlf, "成对 CRLF 那形")


def test_mixed_endings_are_refused_and_named():
    """混行尾（裸 CR 与裸 LF 并存）才是病：必须红，且话里要点名是哪一篇与实测枚数。"""
    sick = "第一行\n第二行\r第三行\r\n"
    assert eol.is_uniform(sick) is False
    with pytest.raises(AssertionError) as caught:
        eol.assert_uniform(sick, "docs/样例.md")
    words = str(caught.value)
    assert "docs/样例.md" in words and "CR=2" in words and "LF=2" in words
    assert "成对 CRLF 只有 1 枚" in words


def test_normalization_never_hides_a_solitary_cr():
    """to_lf 只折成对 CRLF；孤立 CR 必须留在字节里，否则「混行尾」这一族就量不到了。"""
    sick_bytes = "甲\n乙\r丙\r\n".encode("utf-8")
    folded = eol.to_lf(sick_bytes)
    assert b"\r" in folded, "归一把裸 CR 也吃掉了，混行尾从此不可见"
    assert eol.counts(folded) == (1, 2)


@pytest.mark.parametrize("path", [READOUT, LINEAGE], ids=["r469-readout", "r387-lineage"])
def test_the_two_pinned_documents_are_uniform_today(path):
    """被钉的那两本，在当前盘形下必须整齐——本单不许把真病说成「盘形噪声」。"""
    raw = path.read_bytes()
    assert eol.is_uniform(raw), "%s 的行尾本来就是混的，R701 的口径不成立" % path.name


def test_hand_edit_survives_the_line_ending_normalization(tmp_path):
    """判据 1 的正牙：把生成件里的一枚读数改一位，LF 归一之后仍然不等——手改藏不住。

    锚是当场派生的（第一个 `x.y` 形数字），不手抄常量：文档换了内容本牙照样咬。
    """
    import re

    pristine = READOUT.read_bytes()
    lf_copy = eol.to_lf(pristine)
    text = lf_copy.decode("utf-8")
    hit = re.search(r"\d\.\d+", text)
    assert hit is not None, "派生锚没了（本篇里找不到一枚小数读数），本牙得跟着换锚"
    needle = hit.group(0)
    bumped = needle[:-1] + str((int(needle[-1]) + 1) % 10)
    mutated = text.replace(needle, bumped, 1).encode("utf-8")
    assert mutated != lf_copy, "改了一位数字却逐字节相同——相等比较成了摆设"

    crlf = lf_copy.replace(b"\n", b"\r\n")
    assert eol.is_uniform(crlf) is True
    assert eol.to_lf(crlf) == lf_copy, "成对 CRLF 归一后应与纯 LF 相同，否则两态永远对不上"
    assert eol.to_lf(crlf.replace(needle.encode(), bumped.encode(), 1)) != lf_copy
    assert tmp_path is not None
