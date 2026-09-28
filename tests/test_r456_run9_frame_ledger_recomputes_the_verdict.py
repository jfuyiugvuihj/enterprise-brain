"""R456 判据① 的读数面：归因表里每一格都做成能跑的复算钉，不落在散文上。

凭据只有三本**在册件**（本树现读，零开窗、零复跑模型）：

- ``docs/testing/sidecar-run9-frames.jsonl``  逐题 events 与帧读数（105 行）
- ``docs/testing/sidecar-run9.jsonl``         逐题 kind / evidence_n / tool_calls / wall_ms
- ``docs/testing/answers-run9.jsonl``         逐题交回评分器的那一份正文

尺只有**在册量具那一把**：``scripts/eval_transport_ask_v2.py`` 的 ``_frame_verdict`` /
``_sha12``，用 importlib 单独加载（与 ``tests/test_r203_sse_progressive_frames.py`` 同一招），
本文件一个字都不改它。为什么必须复算：本项目有一条铁规——「零命中不是判据，除非说清在
哪一层查的」，而归因表里那些「94／105」「0／105」「九枚单片」的读数如果只写在纸上，下一班
就没人知道它是从哪一格的哪个名字算出来的。
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r456_ledger_ruler", _ROOT / "scripts" / "eval_transport_ask_v2.py"
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

FRAMES = _ROOT / "docs" / "testing" / "sidecar-run9-frames.jsonl"
SIDECAR = _ROOT / "docs" / "testing" / "sidecar-run9.jsonl"
ANSWERS = _ROOT / "docs" / "testing" / "answers-run9.jsonl"

#: 九枚整轮只发一片 text 的题号（A② 事件数那一半的红的全部来源）。
SINGLE_FRAME_IDS = {"doc-07", "chat-03", "chat-06", "chat-09", "chat-10", "metric-16",
                    "approval-06", "scope-01", "data-09"}
#: 两枚连一片都没有的空读题号（各 119.6 s／125.2 s 收窗，落在 error＋request.failed）。
EMPTY_READ_IDS = {"metric-02", "scope-02"}
#: ``app/api/v1/chat.py`` 空正文那条具名结局交回的那一句（21 字），逐字取自在册件。
FALLBACK_TEXT = "本轮未产出任何结论，请重试或补充数据范围。"
#: ``RequestBudget`` 超时那条腿的 legacy error 帧文字（10 字）：用来排除它，不是拿来比的。
TIMEOUT_TEXT = "请求超过系统处理时限"


def _rows(path: Path) -> dict:
    loaded = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            loaded[row["id"]] = row
    return loaded


@pytest.fixture(scope="module")
def frames() -> dict:
    return _rows(FRAMES)


@pytest.fixture(scope="module")
def sidecar() -> dict:
    return _rows(SIDECAR)


@pytest.fixture(scope="module")
def answers() -> dict:
    return _rows(ANSWERS)


def _event_names(row: dict) -> list[str]:
    return [event["event"] for event in row["events"]]


# ---------------------------------------------------------------- 全窗三格读数


def test_the_ledger_is_one_row_per_question_and_the_three_registered_counts_hold(frames):
    """105 行、``text_frames>1``＝94、``missing_chars>0``＝0：报告里那三格的出处就是这一枚。"""
    assert len(frames) == 105, len(frames)
    assert sum(1 for row in frames.values() if row["text_frames"] > 1) == 94
    assert sum(1 for row in frames.values() if row["missing_chars"] > 0) == 0
    assert sum(1 for row in frames.values() if row["text_frames"] == 1) == len(SINGLE_FRAME_IDS)
    assert sum(1 for row in frames.values() if row["text_frames"] == 0) == len(EMPTY_READ_IDS)


def test_criterion_two_recomputes_from_the_rows_own_readings(frames):
    """在册件里每一行的 ``criterion_two_holds`` 都能由同一行读数经在册尺复算出来。

    这一枚是本文件的守卫：摘掉 ``_frame_verdict`` 里 ``text_frames > 1`` 与
    ``max_stream_frames > 1`` 那两枚合取项，复算就与在册件对不上，本用例当场红。
    """
    drift = [row["id"] for row in frames.values()
             if ruler._frame_verdict(row) is not row["criterion_two_holds"]]
    assert drift == [], f"复算与在册件漂移 {len(drift)} 枚：{sorted(drift)}"


def test_no_single_frame_or_empty_read_row_is_recorded_as_passing(frames):
    """单帧与空读谁都不许带着「判据② 成立」出门：合格线要的是同一条流里累计出 >1 帧。"""
    offenders = sorted(row["id"] for row in frames.values()
                      if row["text_frames"] <= 1 and row["criterion_two_holds"])
    assert offenders == [], offenders


# ---------------------------------------------------------------- 九枚单片


def test_the_nine_single_frame_rows_are_exactly_these_ids(frames):
    """九枚单片的题号逐枚点名，多一枚少一枚都算红。"""
    assert {i for i, row in frames.items() if row["text_frames"] == 1} == SINGLE_FRAME_IDS


def test_the_nine_are_a_single_frame_with_no_prefix_break_and_no_missing_char(frames):
    """九枚的形状读数：一条流、一枚帧、零坏形、不缺字也不多字、末帧覆盖终答。"""
    for row_id in sorted(SINGLE_FRAME_IDS):
        row = frames[row_id]
        assert row["kind"] == "ok", row_id
        assert row["text_frames"] == 1, row_id
        assert row["max_stream_frames"] == 1, row_id
        assert row["streams"] == 1, row_id
        assert row["prefix_breaks"] == 0 and row["uncorrected_breaks"] == 0, row_id
        assert row["missing_chars"] == 0 and row["extra_chars"] == 0, row_id
        assert row["last_frame_covers_answer"] is True, row_id
        assert row["last_frame_chars"] == row["answer_chars"] > 0, row_id
        assert row["criterion_two_holds"] is False, row_id


def test_the_nine_put_their_only_frame_at_the_very_close_of_the_round(frames):
    """那唯一一枚帧落在收尾：它后面直接是 request.completed——屏上此前只有转圈。"""
    for row_id in sorted(SINGLE_FRAME_IDS):
        names = _event_names(frames[row_id])
        assert names.count("text") == 1, row_id
        assert names.index("text") + 1 == names.index("request.completed"), (row_id, names)


def test_the_nine_are_not_the_cache_hit_leg(frames):
    """排除缓存命中腿：命中那一支先发 status 再发一帧正文，**不发 canonical**（``request.started``）。

    查的是在册帧件里逐题的 ``events`` 序列这一层，不是日志、不是数据库。
    """
    for row_id in sorted(SINGLE_FRAME_IDS):
        names = _event_names(frames[row_id])
        assert "request.started" in names, (row_id, names)
        assert "request.completed" in names, (row_id, names)
        assert names[0] == "status", (row_id, names)


def test_the_nine_answer_bytes_are_what_the_collector_handed_the_scorer(frames, answers):
    """帧账里的 ``answer_sha`` 与 answers 件里那一份正文逐字同源（同一枚尺 ``_sha12``）。"""
    for row_id in sorted(SINGLE_FRAME_IDS):
        text = answers[row_id]["answer"]
        assert frames[row_id]["answer_sha"] == ruler._sha12(text) == _sha256_12(text), row_id
        assert frames[row_id]["answer_chars"] == len(text), row_id


def test_the_frame_count_is_not_explained_by_the_answer_length(frames):
    """边界对照就在册件里：16 字发 2 片、63 字发 5 片，而 69 字只发 1 片。

    ``chart-01`` 那两帧是**两条流各一帧**（挂起轮＋批准轮），``max_stream_frames`` 仍是 1，
    所以对照钉要同时看 ``streams`` 与 ``max_stream_frames``，只看 ``text_frames`` 会读反。
    """
    chart = frames["chart-01"]
    data03 = frames["data-03"]
    doc07 = frames["doc-07"]

    assert chart["answer_chars"] == 16 and chart["text_frames"] == 2, chart
    assert chart["streams"] == 2 and chart["max_stream_frames"] == 1, chart
    assert data03["answer_chars"] == 63 and data03["text_frames"] == 5, data03
    assert data03["streams"] == 1 and data03["max_stream_frames"] == 5, data03
    assert doc07["answer_chars"] == 69 and doc07["text_frames"] == 1, doc07
    # 长短与帧数不同向：三枚里**最长**的那一枚（doc-07 69 字）逐流帧数最少（1），
    # 短它六字的 data-03（63 字）在同一条码流里累计出 5 帧。
    assert chart["answer_chars"] < data03["answer_chars"] < doc07["answer_chars"]
    assert doc07["max_stream_frames"] < data03["max_stream_frames"]
    assert chart["text_frames"] > doc07["text_frames"]


# ---------------------------------------------------------------- 两枚空读


def test_the_two_empty_reads_carry_the_named_fallback_bytes_and_nothing_else(frames):
    """两枚空读的读数：0 帧、末帧是空串的指纹、多字那半正好 21，答案指纹＝那句兜底话。"""
    empty_sha = ruler._sha12("")
    fallback_sha = ruler._sha12(FALLBACK_TEXT)
    matched = sorted(row_id for row_id, row in frames.items() if row["answer_sha"] == fallback_sha)
    assert matched == sorted(EMPTY_READ_IDS), matched

    for row_id in sorted(EMPTY_READ_IDS):
        row = frames[row_id]
        assert row["kind"] == "error_event", row_id
        assert row["text_frames"] == 0 and row["max_stream_frames"] == 0, row_id
        assert row["last_frame_chars"] == 0 and row["last_frame_sha"] == empty_sha, row_id
        assert row["last_frame_covers_answer"] is False, row_id
        assert row["missing_chars"] == 0 and row["extra_chars"] == len(FALLBACK_TEXT), row_id
        assert row["answer_chars"] == len(FALLBACK_TEXT) == 21, row_id
        assert row["criterion_two_holds"] is False, row_id
        assert row["frames"] == [], row_id


def test_the_two_empty_reads_close_on_the_named_outcome_leg_not_the_other_two(frames):
    """事件顺序把三条失败出口分开：``error`` 在 ``request.failed`` **之前**才是空正文那条腿。

    ``internal_error``（编排线程抛错）与 ``task_timeout``（超过处理时限）都先发 canonical
    再发 legacy error，且交回的文字不是那 21 个字；在册两枚是 ``error``→``request.failed``，
    而且这一轮既没有 ``request.completed`` 也没有 ``sources``。
    """
    for row_id in sorted(EMPTY_READ_IDS):
        names = _event_names(frames[row_id])
        assert "text" not in names, (row_id, names)
        assert names.index("error") < names.index("request.failed"), (row_id, names)
        assert "request.completed" not in names and "sources" not in names, (row_id, names)
        assert names[-1] == "done" and names[0] == "status", (row_id, names)
        assert names.count("step") == 2, (row_id, names)


def test_the_two_empty_reads_are_the_only_rows_whose_answer_is_not_a_delivered_text(frames, sidecar):
    """兜底句不是任何一枚 text 帧的字节：末帧指纹是空串，正文取到的是 error 那一帧。"""
    for row_id in sorted(EMPTY_READ_IDS):
        row = frames[row_id]
        assert row["last_frame_sha"] != row["answer_sha"], row_id
        assert row["last_frame_chars"] < row["answer_chars"], row_id
        assert sidecar[row_id]["evidence_n"] == 0, row_id


def test_the_two_windows_closed_well_before_the_request_budget(frames, sidecar):
    """收窗时刻（119.6 s／125.2 s）离 CHAT_REQUEST_TIMEOUT 还远：不是超时那条腿。"""
    assert sidecar["metric-02"]["wall_ms"] == pytest.approx(119577.9, abs=0.1)
    assert sidecar["scope-02"]["wall_ms"] == pytest.approx(125225.2, abs=0.1)
    for row_id in sorted(EMPTY_READ_IDS):
        assert sidecar[row_id]["wall_ms"] < 300000.0, row_id
    assert len(TIMEOUT_TEXT) == 10 and len(FALLBACK_TEXT) == 21


def test_the_eight_of_the_nine_never_touched_a_worker_and_the_ninth_did(frames, sidecar):
    """九枚分家：八枚一发工具都没派（``step`` 事件 0 枚）、出处 0 行；第九枚派过但交回空正文。

    查的是 ``sidecar-run9.jsonl`` 的 ``tool_calls``（＝收端数到的 ``event: step`` 枚数）与
    ``evidence_n``（＝``sources`` 事件里的可见行）——不是数据库里的 trace，也不是模型日志。
    """
    for row_id in sorted(SINGLE_FRAME_IDS):
        assert sidecar[row_id]["evidence_n"] == 0, row_id
        assert sidecar[row_id]["kind"] == "ok", row_id

    untapped = sorted(i for i in SINGLE_FRAME_IDS - {"data-09"} if sidecar[i]["tool_calls"] == 0)
    assert len(untapped) == 8, untapped
    assert sidecar["data-09"]["tool_calls"] == 2
    assert _event_names(frames["data-09"]).count("step") == 2, _event_names(frames["data-09"])


def test_the_registered_fallback_sentence_is_a_real_constant_in_the_tree_not_a_paraphrase():
    """那句 21 字在 ``app/**`` 里逐字存在：在册件里那 21 个字是后端具名结局交回的，不是评分器编的。

    查的是 ``app/api/v1/chat.py`` 源码文本这一层（本单写域只读，不改它一个字）。
    """
    source = (_ROOT / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")
    assert source.count(FALLBACK_TEXT) >= 1
    assert source.count('"no_answer_produced"') >= 1


def _sha256_12(text: str) -> str:
    """独立实现的一枚短指纹：与在册尺 ``_sha12`` 对得上，才说明那格读数不是抄来的。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]