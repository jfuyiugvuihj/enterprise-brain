"""R203 判据③：那枚 R149 注释说的"不会双重下发"，今天仍然是事实——所以它不许被一删了之。

R149 写下"生成腿一旦改走流式，本文件不必再改一个字"时，它背后还压着一条更早的理由：注册
出口就等于双重下发，所以要把它注释掉。本单把腿接上流式，那条理由必须正面处理，处理方式是
**把它变成能被证伪的断言**，而不是把它删掉：

· 屏上——一枚 text 帧到达时前端只有三种可能：与已见过的某一帧逐字相同（丢）、以已见过的某
  一帧为前缀（覆盖整段正文）、否则追加。第三条才是"双份"，而累计语义天然走不到第三条。
  test_the_screen_shows_exactly_one_copy_of_the_answer 把真帧喂进这条规则，看屏上最后留下几个
  字；test_the_frontend_rule_this_claim_rests_on_is_still_on_disk 钉的是这套断言依赖的那条前端
  规则今天还挂在原处——前端改了规则，本文件的断言就该重审，而不是继续绿着说谎。
· 账上——会话历史与答案缓存都只在 done 那一支各写一次：片道一个字节都不落库。两枚用例分别
  数 assistant 行数与 cache_answer 调用数，都必须是一。
· 尺上——末帧就是终答本身（covering 成立，extra_chars == 0），多枚累计帧既不多字也不缺字。

本文件的帧与片全部来自 R203 那两枚真件（真生成腿 + 真 /ask 收端），不是手搓的形状。
"""

from pathlib import Path

import pytest
from app.api.v1 import chat

from tests.test_r203_sse_progressive_frames import (  # noqa: F401  -- 复用同一条链，不造第二份
    DOC_ANSWER,
    _harness,
    _readings,
    _text_payloads,
    ruler,
)

SESSIONS_JS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "sessions.js"


def _fold_like_the_browser(contents):
    """按 sessions.js 的 text 分支（去重 / covering / 追加）折一遍，三种各记一笔。

    这不是把前端逻辑抄进后端求个心安，是把"屏上只有一份正文"这句注释变成能被算出来的数：
    ``doubled`` 非零就是屏上留了两份正文；``started`` 记的是"屏上本来还没有正文时的那一帧追加"
    （第一帧必然走它），它必须恰为一，否则就是收尾帧凭空多了一份。
    """
    segments = []
    content = ""
    ignored = 0
    covered = 0
    started = 0
    doubled = 0
    for chunk in contents:
        if not chunk:
            continue
        if chunk in segments:
            ignored += 1
            continue
        covering = next((seg for seg in segments if seg in chunk and chunk != seg), None)
        if covering is not None:
            content = chunk
            segments = [chunk]
            covered += 1
        else:
            # 前端这条分支就是"追加"：屏上本来没有正文它是第一帧，本来有它就是双份。
            if content:
                doubled += 1
            else:
                started += 1
            content = f"{content}{chunk}"
            segments = [*segments, chunk]
    return {
        "content": content,
        "ignored": ignored,
        "covered": covered,
        "started": started,
        "doubled": doubled,
    }


@pytest.fixture()
def streamed_round(monkeypatch, tmp_path):
    """一真轮：注册了 sink、生成腿真流。返回整条流字面、每一枚 text 帧正文、落库调用。"""
    saves = []
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    monkeypatch.setattr(chat, "_save_message", lambda *_args: saves.append(_args))
    body = ask()
    return body, [payload["content"] for payload in _text_payloads(body)], saves


# ==================== 屏上：只有一份正文 ====================


def test_the_screen_shows_exactly_one_copy_of_the_answer(streamed_round):
    _body, contents, _saves = streamed_round

    assert len(contents) >= 2, "这一轮没流起来，双份无从谈起"
    rendered = _fold_like_the_browser(contents)
    assert rendered["doubled"] == 0, f"屏上被追加成了两份：{rendered}"
    assert rendered["started"] == 1, f"第一帧没落屏：{rendered}"
    assert rendered["content"] == DOC_ANSWER
    assert rendered["content"].count(DOC_ANSWER[:12]) == 1, "同一句话在屏上出现两次"


def test_the_duplicate_frame_is_dropped_not_appended(streamed_round):
    """末片帧与收尾帧逐字同文：那条 includes 分支把它丢掉，屏上不多一个字。"""
    _body, contents, _saves = streamed_round

    assert contents[-1] == DOC_ANSWER
    assert contents[-2] == DOC_ANSWER, "末片帧与收尾帧应当同文（R149 判据③ 的既有形状）"
    assert contents.count(DOC_ANSWER) == 2
    rendered = _fold_like_the_browser(contents)
    assert rendered["ignored"] >= 1
    assert rendered["doubled"] == 0


def test_no_live_frame_is_a_delta_of_the_previous_one(streamed_round):
    """反证靶子的正面：任何一帧都不是上一帧之后多出来的那半截。

    只要有一帧是增量，covering 就找不着北，那一帧就走 append —— 屏上就是两份。
    """
    _body, contents, _saves = streamed_round

    for previous, current in zip(contents, contents[1:]):
        assert current.startswith(previous), f"帧不是累计：{previous[-16:]!r} -> {current[:16]!r}"
        assert current != previous or current == contents[-1]


def test_the_frontend_rule_this_claim_rests_on_is_still_on_disk():
    """承重的那三条前端分支还在原处：它们一动，本文件的"屏上只有一份"就该重审。"""
    source = SESSIONS_JS.read_text(encoding="utf-8")
    backtick = chr(96)
    append_branch = "msg.content = " + backtick + "${msg.content || ''}${chunk}" + backtick

    assert "state.segments.includes(chunk)" in source, "去重分支不见了"
    assert "chunk.includes(seg) && chunk !== seg" in source, "covering 分支不见了"
    assert append_branch in source, "追加分支还在：那就必须保证走不到它"


# ==================== 账上：落库一次、缓存一次 ====================


def test_the_session_history_gets_exactly_one_assistant_row(streamed_round):
    _body, _contents, saves = streamed_round

    assistant_rows = [call for call in saves if len(call) >= 2 and call[1] == "assistant"]
    assert len(assistant_rows) == 1, [call[1:3] for call in assistant_rows]
    assert assistant_rows[0][2] == DOC_ANSWER


def test_the_answer_cache_is_written_once(monkeypatch, tmp_path):
    from app.common import cache

    writes = []
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    monkeypatch.setattr(
        cache, "cache_answer", lambda question, answer, **kwargs: writes.append((question, answer))
    )
    ask()

    assert len(writes) == 1, writes
    assert writes[0][1] == DOC_ANSWER, "进缓存的必须是终答本身，不是任何一枚中间帧"


# ==================== 尺上：末帧 == 终答 ====================


def test_the_last_frame_is_the_answer_and_carries_no_extra_characters(streamed_round):
    body, contents, _saves = streamed_round

    readings = _readings(body)
    assert contents[-1] == DOC_ANSWER
    assert readings["extra_chars"] == 0, readings
    assert readings["missing_chars"] == 0, readings
    assert readings["last_frame_covers_answer"] is True
    assert readings["answer_sha"] == ruler._sha12(DOC_ANSWER)
    # 累计帧的每一枚都以开头那十几个字起头，这是"累计"应有的样子；双份只在屏上判，见上。
    assert all(chunk.startswith(contents[0]) for chunk in contents)
    assert _fold_like_the_browser(contents)["doubled"] == 0
