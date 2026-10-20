# -*- coding: utf-8 -*-
"""R670 判据①② —— 走一次 ``/chat``，``model_calls`` 里必须有一行，数与夹具自报逐枚相等。

病形写在工单 ``docs/tickets/R670-token-readout-honesty.md`` 的「现取病形」段：``/ask`` 那一腿有行
且非零，``/chat`` 那一腿**打完模型不落 ``model_calls`` 行** —— 端点从不打开 span，也没有任何 trace
身份给它寻址，于是计划书 R38 判据③「抽查一问 ``input_tokens/output_tokens`` 非零且与 Ollama 自报
一致」在这条生产主路径上连一个可查的落点都没有。本件判的就是这个落点，判据逐枚可失败：

* ① 一行 + 两枚数：``input_tokens``／``output_tokens`` 非 NULL 非零，逐枚等于夹具里 Ollama 自己报的
  那两枚 —— 兼容腿拼写（``prompt_tokens``／``completion_tokens``）与原生腿拼写
  （``prompt_eval_count``／``eval_count``）两形都判；
* ② 前一半：``metadata`` 带上原始 usage 的**键名集合**，不许只留 ``worker``；
* ② 后一半：夹具没报 ``cached_tokens`` 时那一格记 NULL，不许记 0（报出来的 0 原样留着）；
* 边界：检索就失败的那轮压根没打模型 ⇒ 一行账都不许有；
* 观测不改正文：交出去的字与「压根不记账」那一版逐字相同，只带计量的末片一个字都不上屏；
* 归属：行要挂在真答的那一轮的 ``agent_runs`` 上，且本单不许为这条道造一枚从没跑过的工作步骤。

🔴 本件**不**宣称 R38③ 在真机上已达。今天这一腿的请求体没开 ``stream_options.include_usage``，
兼容腿流式因此一字节 usage 都不报（R31 现读，落在 ``docs/perf/latency-budget-2026-09-16.md`` 与
跟进单 R31 那一格）；那一格由
:meth:`test_a_round_that_reported_no_usage_block_still_lands_a_row_and_keeps_the_counters_null`
按今天的真形状记成 NULL，凭据纸 ``docs/testing/r670-2026-10-05.md`` 现读。**行必须落，数不许编。**

全程离线：真发射件（``TestClient`` 走真路由与真 span 链）、离线夹具、零真模型、不连库、
不起服务、不开 socket；账落在 ``tmp_path`` 的 TraceStore 上，写链与
``tests/test_r146_cached_token_ledger.py`` 同一套。
"""

import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from app.trace import spans

MODEL_NAME = "qwen3:4b"
#: 夹具自报的数只有一个来源：下面这两份字面量就是夹具本身。判据① 比的是「行上那两格 == 夹具报的
#: 那两格」，一个都不许折算；真机今天报不报得出数，是凭据纸那一格，不在这里冒充。
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
#: 命中形状逐字照 ``tests/test_legacy_chat_retrieval_scope.py``：部门对得上，正文才进得了 prompt。
VISIBLE_HIT = {
    "content": "残值率按十年直线折旧",
    "source": "handbook.txt",
    "chunk_index": 0,
    "classification": 1,
    "department": "dept-a",
}
ANSWER_PIECES = ("残值率", "按十年直线折旧")


class _Chunk:
    """一帧流：要么带正文，要么只带计量 —— 与兼容腿真交回来的形状同形，不是本件想象的形状。"""

    def __init__(self, content=None, usage=None):
        self.choices = (
            [] if content is None else [SimpleNamespace(delta=SimpleNamespace(content=content))]
        )
        self.usage = usage


class _StreamingModel:
    local_model = MODEL_NAME

    def __init__(self, frames):
        self._frames = frames
        self.calls = 0
        self.prompts = []

    def chat(self, messages=None, source=None, stream=True):
        self.calls += 1
        self.prompts.append(messages[0]["content"])
        return iter(self._frames)


class _Retriever:
    def __init__(self, hits=None, failure=None):
        self._hits = list(hits) if hits is not None else [dict(VISIBLE_HIT)]
        self._failure = failure

    def search(self, query, k=5, where=None):
        if self._failure is not None:
            raise self._failure
        return list(self._hits)


def _headers(username):
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _offline_store(tmp_path, monkeypatch):
    """把这一轮的账落到 ``tmp_path`` 的 TraceStore 上，并且**两枚出口都换**：

    ``app/trace/spans.py`` 在模块级绑定了 ``default_trace_store``，而
    ``app/api/v1/chat.py::_record_chat_round_verdict`` 与 ``app/api/v1/chat.py`` 的在册先例
    （``_record_wire_first_text``）一样在调用时从 ``app.trace.store`` 现取。两枚名字是两枚不同的
    绑定，只换一枚就等于让终态那事件走进真账（``./data/traces`` 与在配的库），
    本件判的就不是自己那本账了。
    """
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import store as trace_store
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "r670-events.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "r670-rows.json"),
    )
    def seams():
        return store

    monkeypatch.setattr(spans, "default_trace_store", seams)
    monkeypatch.setattr(trace_store, "default_trace_store", seams)
    return store


def _frames(*, usage=None):
    frames = [_Chunk(piece) for piece in ANSWER_PIECES]
    if usage is not None:
        frames.append(_Chunk(usage=usage))
    return frames


def _drive(monkeypatch, tmp_path, frames, *, retriever=None):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "staff",
            "department": "dept-a",
        },
    )
    model = _StreamingModel(frames)
    monkeypatch.setattr(chat, "retriever", retriever or _Retriever())
    monkeypatch.setattr(chat, "model_handler", model)
    store = _offline_store(tmp_path, monkeypatch)
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "残值率是多少"},
        headers=_headers("staff-r670"),
    )
    return response, store, model


def _rows(store, table):
    return store.persistence.list(table)


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (COMPAT_USAGE, (COMPAT_USAGE["prompt_tokens"], COMPAT_USAGE["completion_tokens"])),
        (NATIVE_USAGE, (NATIVE_USAGE["prompt_eval_count"], NATIVE_USAGE["eval_count"])),
    ],
    ids=["compat-spelling", "native-spelling"],
)
def test_one_round_of_chat_lands_a_row_with_the_servers_own_counts(usage, expected, monkeypatch, tmp_path):
    """判据①：打完模型必须有一行，且两枚数非 NULL 非零、逐枚等于夹具自报。"""
    prompt, completion = expected
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=usage))

    assert response.status_code == 200
    assert model.calls == 1, "夹具这一腿必须真打到模型，否则下面判的是空账"
    rows = _rows(store, "model_calls")
    assert len(rows) == 1, "打完模型不落 model_calls 行就是本单的病形，不许复发"
    row = rows[0]
    assert (row["input_tokens"], row["output_tokens"]) == (prompt, completion)
    assert prompt > 0 and completion > 0
    assert row["cached_tokens"] == 467, "两种拼写读回的必须是同一枚数"
    assert row["provider"] == "local"
    assert row["model_name"] == MODEL_NAME
    assert row["status"] == "completed"
    assert row["error_code"] is None
    assert row["first_token_at"] is not None, "第一枚看得见的字要有时戳：那一列本来就是量这件事的"
    assert row["duration_ms"] is not None


def test_metadata_names_the_usage_keys_instead_of_only_the_worker(monkeypatch, tmp_path):
    """判据② 前一半：``metadata`` 要带原始 usage 的键名集合，不许只留 ``worker``。"""
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=COMPAT_USAGE))
    row = _rows(store, "model_calls")[0]

    metadata = row["metadata"]
    assert set(metadata) > {"worker"}, "只留 worker 就是判据② 点名的那张脸"
    assert metadata["usage_keys"] == sorted(COMPAT_USAGE)


def test_a_missing_cached_side_is_recorded_as_null_not_zero(monkeypatch, tmp_path):
    """判据② 后一半：缺 ``cached_tokens`` ⇒ 那一格 NULL。在册规矩：绝不默认成 0。"""
    usage = {"prompt_tokens": 116, "completion_tokens": 7}
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=usage))
    row = _rows(store, "model_calls")[0]

    assert row["cached_tokens"] is None, "记 0 就是把「服务端没说」写成「服务端数过、是 0」"
    assert row["metadata"]["usage_keys"] == ["completion_tokens", "prompt_tokens"]
    assert (row["input_tokens"], row["output_tokens"]) == (116, 7)


def test_a_reported_zero_cached_side_stays_a_reported_zero(monkeypatch, tmp_path):
    """同一枚 NULL 纪律的反面：服务端真报了 0，那一格就必须带着 0，不许被折成缺格。"""
    usage = {
        "prompt_tokens": 116,
        "completion_tokens": 7,
        "prompt_tokens_details": {"cached_tokens": 0},
    }
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=usage))

    assert _rows(store, "model_calls")[0]["cached_tokens"] == 0


def test_a_round_that_reported_no_usage_block_still_lands_a_row_and_keeps_the_counters_null(
    monkeypatch, tmp_path
):
    """今天这条道的真形状：行照样落，两枚数留 NULL，键名集合是空列表。

    🔴 这条钉就是本单不许把 R38③ 硬翻成达的那一格证据：没开 ``include_usage`` 的兼容腿流式
    报不出数，而「报不出」与「没这一行」是两件事 —— 前者是读数，后者是账根本没开门。
    """
    response, store, model = _drive(monkeypatch, tmp_path, _frames())
    row = _rows(store, "model_calls")[0]

    assert model.calls == 1
    assert row["input_tokens"] is None and row["output_tokens"] is None
    assert row["cached_tokens"] is None
    assert row["metadata"]["usage_keys"] == []
    assert row["status"] == "completed"


def test_the_meter_does_not_move_a_single_answer_byte(monkeypatch, tmp_path):
    """观测面不许改正文：交出去的字与不记账那一版逐字相同，只带计量的末片不上屏。"""
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=COMPAT_USAGE))

    assert response.text == "".join(ANSWER_PIECES)
    assert response.status_code == 200
    assert "x-lane-source" in response.headers, "档位读数那枚头是本单写域之外，一个不许动"
    assert MODEL_NAME not in response.text, "计量不能把模型名漏进正文"


def test_a_round_that_never_reached_the_model_lands_no_rows_at_all(monkeypatch, tmp_path):
    """边界：检索就炸的那轮一次模型都没打 —— 那它一行 model_calls 都不该有。"""
    broken = _Retriever(failure=OSError("connection refused 10.0.5.9:11434"))
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=COMPAT_USAGE), retriever=broken)

    assert response.status_code == 200
    assert model.calls == 0
    assert _rows(store, "model_calls") == [], "没打模型就造一行账，那是造证据"
    assert _rows(store, "agent_runs") == [], "连 FK 父行都不该有：这一轮压根没到模型边界"
    assert "本轮检索或模型调用失败" in response.text


def test_the_row_is_addressed_to_the_round_that_answered(monkeypatch, tmp_path):
    """行要挂在真答的那一轮上：FK 父行由同一本账自己造，且本单不替这条道造一枚工作步骤。"""
    response, store, model = _drive(monkeypatch, tmp_path, _frames(usage=COMPAT_USAGE))
    row = _rows(store, "model_calls")[0]
    runs = _rows(store, "agent_runs")

    assert len(runs) == 1, "每一枚 trace 事件都刷新 run 行：这一轮的父行必须由这一轮自己造"
    assert row["agent_run_id"] == runs[0]["agent_run_id"]
    assert runs[0]["trace_id"].startswith("trace-")
    assert runs[0]["owner_id"] == "staff-r670"
    assert row["agent_step_id"] is None, "这条道没跑过工作步骤，不许给它造一行 agent_steps"
    assert _rows(store, "agent_steps") == []
    assert runs[0]["status"] == "completed", "父行不许永远停在 running：那是本单新造的假账"
    assert runs[0]["completed_at"] is not None