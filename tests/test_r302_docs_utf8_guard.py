"""R302｜文档编码体检：把事故 #17 那一类「共享文档被有损编码写坏」变成会红的钉。

病灶（09-26 第二格实录，跟进单 §102 第一节）：往 ``docs/handoff/*.md`` 追加中文散文时，
整文件走了一遍 latin1 解码-编码。中文码点全部 > ``0xFF``，latin1 编码只保留低字节，
于是「行」变成 ``0x8C`` 这类碎片——文件在磁盘上烂了一截，而**没有任何一枚门变红**。
执行层 ``Arendt`` 是自己读文件才发现的：判据原文读不出来，只能退回派工词。
同一族还有事故 #16：4,588 行看板被赋值成字面量 ``"x"``。两笔的共同点＝共享文档的写入没有下牙。

三格下牙，全部**逐文件记账、等值断言**（不是 ``<=``）：
① 严格 UTF-8 可解码，且 NUL 恒为 0（BOM 允许——看板本来就带 BOM）；
② U+FFFD 计数与账本分毫不许差：净增＝写坏，净减＝有人悄悄改了史，两边都得当场停下；
③ ``\t\n\r`` 之外的控制字符必须与账本同一集合。
账本里那几枚存量（跟进单 7 枚 U+FFFD + ``0x0c``）是事故 #17 之前就
在的旧痕，本班不做考古；要动它们必须连同跟进单 §102 第一节一起改口。
🔴 10-05 第十七班续席改口格：跟进单那一枚历史 ``0x0c``（``C:Users<FF>engx.codexsessions`` 那一形，
是当年 latin1 往返把反斜杠吞成 FF 留下的疤）**已按本件正解路径复原成字面反斜杠**
``C:\\Users\\fengx\\.codex\\sessions``（落盘于并树 ``b5b67b5``，出处＝跟进单 §183.5 末条＋本班 §184），
复原后现取该文件控制字符集合＝**空**、U+FFFD 仍 7 枚未动 ⇒ 账本跟着收紧到 ``(7, ())``，
与上面看板那一格同一路径、同样比旧账更严。7 枚 U+FFFD 一格未动，考古仍不做。
🔴 看板那 4 枚 ``0x07``/``0x08`` 已于 10-05 第十六班按本件的正解路径**修好文档并改口账本**（复原成字面
反斜杠 ``\a``/``\b``，出处＝跟进单 §181 末条），从此看板这一格的控制字符要求是**零**，比旧账更严。
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs" / "handoff"

#: 账本：文件名 -> (U+FFFD 计数, 除 \\t\\n\\r 之外的控制字符码点升序元组)。09-26 现取。
ENCODING_LEDGER: dict[str, tuple[int, tuple[int, ...]]] = {
    "2026-09-15-backend-followup-requests.md": (7, ()),  # 10-05 第十七班续席：历史 0x0c 已复原为字面反斜杠（并树 b5b67b5），账本收紧到零；U+FFFD 7 枚未动
    "2026-09-15-orchestration-board.md": (0, ()),  # 10-05 第十六班：4 枚历史 BEL/BS 已复原为字面反斜杠，账本收紧到零
}

ALLOWED_CONTROL = "\t\n\r"
FOLLOWUP_DOC = "2026-09-15-backend-followup-requests.md"


def _readings(path: pathlib.Path) -> tuple[int, tuple[int, ...], str, int]:
    """现取一枚文档的体检读数：U+FFFD 数 / 越界控制字符 / 严格解码结果 / NUL 数。"""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        strict = "ok"
    except UnicodeDecodeError as exc:
        text = raw.decode("utf-8", errors="replace")
        strict = f"strict-utf8-fail@{exc.start}"
    return (
        text.count("\ufffd"),
        tuple(sorted({ord(ch) for ch in text if ord(ch) < 0x20 and ch not in ALLOWED_CONTROL})),
        strict,
        raw.count(b"\x00"),
    )


def _violations(path: pathlib.Path, expected_fffd: int, expected_controls: tuple[int, ...]) -> list[str]:
    """把一枚文件与它该长的样子对照，返回违规清单（空＝干净）。"""
    replacements, controls, strict, nul = _readings(path)
    found = []
    if strict != "ok":
        found.append(f"{path.name}: {strict}")
    if nul:
        found.append(f"{path.name}: NUL x{nul}")
    if replacements != expected_fffd:
        found.append(f"{path.name}: U+FFFD {replacements} != 记账 {expected_fffd}")
    if controls != expected_controls:
        found.append(f"{path.name}: 控制字符 {controls} != 记账 {expected_controls}")
    return found


def test_every_handoff_doc_is_strict_utf8_and_has_no_nul() -> None:
    """①：谁把文档写成非法 UTF-8 或塞进 NUL，当场红，且点名到文件。"""
    files = sorted(DOCS_DIR.glob("*.md"))
    assert files, f"{DOCS_DIR} 下一枚文档都没扫到——是路径错了，不是文档干净"
    broken = []
    for path in files:
        _replacements, _controls, strict, nul = _readings(path)
        if strict != "ok":
            broken.append((path.name, strict))
        if nul:
            broken.append((path.name, f"NUL x{nul}"))
    assert not broken, f"文档编码已损坏（事故 #17 那一族）：{broken}"


def test_replacement_char_and_control_counts_match_the_ledger_exactly() -> None:
    """②＋③：逐文件等值。红了只有两条路——把文档修好，或连同 §102 第一节一起改口。"""
    offenders = []
    for name, (expected_fffd, expected_controls) in ENCODING_LEDGER.items():
        path = DOCS_DIR / name
        assert path.exists(), f"账本里的文档不见了：{name}（改名或删除要连同本账一起改口）"
        offenders.extend(_violations(path, expected_fffd, expected_controls))
    assert not offenders, (
        f"文档体检读数与账本不符：{offenders}。追加一律用字节拼接"
        "（open(p,'rb').read() + new.encode('utf-8')），禁止整文件 latin1 往返——见跟进单 §102 第一节。"
    )


def test_ledger_names_every_damaged_doc_so_none_can_hide() -> None:
    """账本不许漏文件：任何带损坏读数的文档都必须在账里有名，否则本单等于没下牙。"""
    unlisted = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        if path.name in ENCODING_LEDGER:
            continue
        replacements, controls, strict, nul = _readings(path)
        if replacements or controls or strict != "ok" or nul:
            unlisted.append((path.name, replacements, controls, strict, nul))
    assert not unlisted, f"这些文档读起来是坏的却没进账本，藏得住就查不出：{unlisted}"


def test_the_append_recipe_is_written_down_where_the_next_shift_can_find_it() -> None:
    """纠正条款必须落在跟进单里：字节拼接 + 写前断言前缀 + 写后看减少行数。"""
    text = (DOCS_DIR / FOLLOWUP_DOC).read_bytes().decode("utf-8")
    assert "事故 #17" in text, "跟进单里没有事故 #17 那节——纠正条款不能只活在记忆里"
    assert "字节拼接" in text, "追加的正确写法（字节拼接）必须写进跟进单，供下班照抄"
    assert "减少行数" in text, "写后必须看 git diff --numstat 的减少行数，这条也得落字"


# ------------------------------------------------------------------ 反证钉（摘刀必红）


def test_counter_evidence_a_lossy_codec_appends_that_broke_the_repo_go_red(
    tmp_path: pathlib.Path,
) -> None:
    """反证一：把中文追加过一遍有损编码 ⇒ 尺子必须抓到，两路都要抓到。

    事故 #17 的手法是 Node 的 ``Buffer.from(text, 'latin1')``：码点 > ``0xFF`` 只留低字节，
    中文落成 ``0x8C`` 这类碎片。Python 的 latin-1 编码器对同一批字符直接报错，所以这里
    分两路演示同一种病：一路丢字节（症状与当年同形），一路按 GBK 落盘（另一种错代码页）。
    """
    source = DOCS_DIR / FOLLOWUP_DOC
    expected_fffd, expected_controls = ENCODING_LEDGER[FOLLOWUP_DOC]
    text = source.read_bytes().decode("utf-8")

    dropped = tmp_path / FOLLOWUP_DOC
    dropped.write_bytes(
        (text + "\n新增判据：消费时刻现取身份，漂移即判失效。\n").encode("latin-1", errors="ignore")
    )
    assert _violations(dropped, expected_fffd, expected_controls), (
        "丢字节的追加没被本单抓到——它复现的正是事故 #17"
    )

    wrong_page = tmp_path / ("gbk_" + FOLLOWUP_DOC)
    wrong_page.write_bytes((text + "\n扫描版 PDF 走本地 OCR 通道。\n").encode("gbk", errors="ignore"))
    assert _violations(wrong_page, expected_fffd, expected_controls), (
        "错代码页的追加没被本单抓到"
    )


def test_counter_evidence_b_cleaning_the_ledger_instead_of_the_doc_goes_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """反证二：把账本改成迎合损坏值 ⇒ 等值断言红（堵死「红了就改账本」这条逃生路）。"""
    monkeypatch.setitem(ENCODING_LEDGER, FOLLOWUP_DOC, (1248, (0x08,)))
    with pytest.raises(AssertionError, match="U\\+FFFD"):
        test_replacement_char_and_control_counts_match_the_ledger_exactly()


def test_counter_evidence_c_moving_or_renaming_a_ledgered_doc_goes_red(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反证三：把账本里的文档删掉或改名 ⇒ 红（「删文件」不能变成逃避体检）。"""
    empty = tmp_path / "handoff"
    empty.mkdir(parents=True)
    monkeypatch.setattr(sys.modules[__name__], "DOCS_DIR", empty, raising=True)
    with pytest.raises(AssertionError, match="账本里的文档不见了"):
        test_replacement_char_and_control_counts_match_the_ledger_exactly()


def test_counter_evidence_d_a_quietly_shortened_doc_goes_red(
    tmp_path: pathlib.Path,
) -> None:
    """反证四：只把带 U+FFFD 旧痕的那段悄悄删掉 ⇒ 等值断言红（净减同样是改史）。"""
    source = DOCS_DIR / FOLLOWUP_DOC
    body = source.read_bytes().decode("utf-8")
    assert "\ufffd" in body, "本树跟进单已经没有旧痕，这一把反证失去靶子——连同账本一起改口"
    cleaned = tmp_path / FOLLOWUP_DOC
    cleaned.write_bytes(body.replace("\ufffd", "").encode("utf-8"))
    expected_fffd, expected_controls = ENCODING_LEDGER[FOLLOWUP_DOC]
    assert _violations(cleaned, expected_fffd, expected_controls), (
        "把旧痕悄悄抹掉没被本单抓到——净减也必须停下问一句"
    )