"""R38（代码半）· 原生腿把输入侧 token 数报回来了，账上必须拿得到。

开工现场（本树 ``6f3777d``，行号按 ``git grep -n`` 口径，逐枚复核过）：

- ``app/common/model_handler.py:360`` 原生 ``/api/chat`` 腿只读 ``output_tokens = body.get("eval_count")``；
  ``git grep -n prompt_eval_count -- app`` 开工前 **0 命中** ⇒ 服务端报了输入侧，这一腿把它扔了；
- ``ModelReply``（同文件 ``:88``，构造点 ``:155/:252/:371/:408``）只带 ``output_tokens``，没有 input 侧字段；
- ``app/trace/spans.py:269 model_token_counts`` 只认 LangChain 的 ``usage_metadata`` / ``usage`` 两种 dict，
  拿到 ``ModelReply`` 就走 ``:274`` 返回两枚 ``None`` —— 连 ``output_tokens`` 也一并丢掉；
- ``app/trace/store.py:270-272`` 把 summary 里这两枚值写进 ``model_calls`` 的 values（列见 ``migrations/0002:147``）。

本文件钉判据 ①②③：报了就穿到 ``input_tokens``、没报就必须是 ``None``、两枚值都要能落到 ``store`` 那侧。
🔴 跟进单 §21 原话「不得估算冒充实测 token 数」在这里是硬判据：应答里故意留着
``total_duration`` / ``prompt_eval_duration`` / ``eval_duration`` 这些能被"顺手算一下"的数，
``prompt_eval_count`` 缺失时 ``input_tokens`` 仍须为 ``None``，一枚派生数都不许出现。

全程离线：模型地址只出现 ``http://model.internal:11434`` 这种不存在的主机，真 HTTP 由
``_native_chat_request`` 这一个缝注入，一次 socket 都不开；落库用仓里已有的
``JsonPersistenceAdapter`` 读回，不碰数据库。
"""
import json
from types import SimpleNamespace

import pytest

from app.agents.contracts import Principal
from app.common import model_budget
from app.common.model_budget import estimate_prompt_tokens
from app.common.model_handler import (
    TRANSPORT_COMPAT,
    TRANSPORT_NATIVE,
    ModelHandler,
    ModelReply,
    ModelSource,
    compat_reply,
)
from app.trace import spans
from app.trace.spans import model_token_counts

#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，绝不会碰到宿主模型的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
REWRITE_JSON = json.dumps(
    {"rewrites": ["住宿费报销上限是多少"], "sub_questions": []},
    ensure_ascii=False,
)
#: 真机量级取自 docs/perf/raw/rounds.jsonl（supervisor_decide 632 进 / 96 出）。
MEASURED_PROMPT_EVAL_COUNT = 632
MEASURED_EVAL_COUNT = 96
MESSAGES = [{"role": "user", "content": "改写这个问题"}]


@pytest.fixture(autouse=True)
def _fresh_budget():
    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()


def _handler(monkeypatch, *, base_url=SAFE_BASE_URL, model_name="qwen3.5:9b"):
    """一个装着真 OpenAI 客户端的 handler：建客户端不开 socket，真 HTTP 由用例注入。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.setenv("LOCAL_MODEL_NAME", model_name)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    return ModelHandler()


def _native_body(*, report_input=True, **overrides):
    """Ollama 原生 ``/api/chat`` 的应答形状：正文在 ``message.content``，计数在顶层。

    三枚 duration 故意留着：想反推输入侧的实现有得偷，才钉得住"不许估算"。
    """
    body = {
        "model": "qwen3.5:9b",
        "message": {"role": "assistant", "content": REWRITE_JSON},
        "done_reason": "stop",
        "done": True,
        "load_duration": 6_100_000_000,
        "prompt_eval_duration": 3_733_000_000,
        "eval_duration": 45_883_000_000,
        "total_duration": 55_716_000_000,
        "eval_count": MEASURED_EVAL_COUNT,
    }
    if report_input:
        body["prompt_eval_count"] = MEASURED_PROMPT_EVAL_COUNT
    body.update(overrides)
    return body


class _NativeRecorder:
    """原生腿的缝：记账请求并回放预置响应，一次真实 HTTP 都不发生。"""

    def __init__(self, body):
        self.calls = []
        self.body = body

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        return self.body


def _native_reply(monkeypatch, body, *, messages=None):
    """只经过真 ``ModelHandler.chat`` 这一道出口，拿到服务端应答的落地对象。"""
    handler = _handler(monkeypatch)
    native = _NativeRecorder(body)
    monkeypatch.setattr(handler, "_native_chat_request", native)
    reply = handler.chat(
        messages=messages or MESSAGES,
        source=ModelSource.LOCAL,
        stream=False,
    )
    assert len(native.calls) == 1, "一次调用只许付一次推理"
    assert reply.transport == TRANSPORT_NATIVE
    return reply


class _NeverUsedOffline:
    """写链的三枚用例都只走正常腿：谁把离线腿叫起来，谁就是在替模型说话。"""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None, **kwargs):
        raise AssertionError("离线模型不该被调用")


def _model_calls_row(tmp_path, monkeypatch, reply):
    """把一枚应答喂进真那条写链：``model_token_counts`` → span payload → store values → 行。"""
    from app.agents.nodes import _ResilientModel
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "spans.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "spans.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": Principal(user_id="u-38", username="staff38", roles=["staff"]),
            "request_id": "req-38",
            "trace_id": "trace-38",
            "task_id": "task-38",
            "worker": "doc",
            "step_id": "trace-38:worker:doc",
        }
    }

    class _Primary:
        model_name = "qwen3.5:9b"

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            return reply

    _ResilientModel(_Primary(), _NeverUsedOffline()).invoke([], config=config)
    rows = store.persistence.list("model_calls")
    assert len(rows) == 1, rows
    return rows[0]


# ==================== 判据 ①②：报了就得穿出来，没报就必须是 NULL ====================


def test_native_leg_reports_prompt_eval_count_and_stays_null_when_absent(monkeypatch):
    """同一道出口，服务端报与不报必须落成两种值：真数与 ``None``，中间不许有第三种。"""
    reported = _native_reply(monkeypatch, _native_body())
    assert reported.output_tokens == MEASURED_EVAL_COUNT
    assert getattr(reported, "input_tokens", None) == MEASURED_PROMPT_EVAL_COUNT

    unreported = _native_reply(monkeypatch, _native_body(report_input=False))
    assert unreported.output_tokens == MEASURED_EVAL_COUNT
    assert getattr(unreported, "input_tokens", None) is None


def test_model_token_counts_reads_the_native_reply_attributes(monkeypatch):
    """``model_token_counts`` 得认得原生腿带出来的那两枚属性，而不是只认 LangChain 形状。"""
    counts = model_token_counts(_native_reply(monkeypatch, _native_body()))
    assert counts == {
        "input_tokens": MEASURED_PROMPT_EVAL_COUNT,
        "output_tokens": MEASURED_EVAL_COUNT,
    }


def test_model_token_counts_still_prefers_the_langchain_shape():
    """LangChain 那条形状一字不改：本单是加法，不是换尺子。"""
    langchain = SimpleNamespace(usage_metadata={"input_tokens": 11, "output_tokens": 7})
    assert model_token_counts(langchain) == {"input_tokens": 11, "output_tokens": 7}
    openai_style = SimpleNamespace(usage={"input_tokens": 21, "output_tokens": 3})
    assert model_token_counts(openai_style) == {"input_tokens": 21, "output_tokens": 3}


def test_a_reply_built_the_old_way_carries_no_input_but_keeps_its_output():
    """改动前的构造点（``:252``/``:408`` 那类）不带 input 侧关键字 ⇒ 读出来必须是 ``None``。

    这枚同时钉住改动前的第二个事实：``ModelReply.output_tokens`` 此前根本穿不过
    ``model_token_counts``（``:274`` 直接两枚 ``None``），改动后它穿得过去，而 input 侧照旧诚实。
    """
    old_style = ModelReply("x", finish_reason="stop", output_tokens=7)
    assert model_token_counts(old_style) == {"input_tokens": None, "output_tokens": 7}


def test_nothing_is_derived_when_the_server_reported_no_input(monkeypatch):
    """🔴 反估算：缺 ``prompt_eval_count`` 就是缺，时长、正文长度、``total - output`` 都不许顶包。"""
    reply = _native_reply(monkeypatch, _native_body(report_input=False))
    counts = model_token_counts(reply)
    assert counts["input_tokens"] is None, counts
    assert counts["output_tokens"] == MEASURED_EVAL_COUNT


def test_the_estimation_ruler_never_becomes_a_metered_number(monkeypatch):
    """估算尺（``estimate_prompt_tokens``）量得出数，也不许顶进计量字段——两把尺不是一个东西。"""
    estimated = estimate_prompt_tokens(MESSAGES)
    assert estimated > 0, "前提：估算尺此刻是有数的，顶包有动机"
    reply = _native_reply(monkeypatch, _native_body(report_input=False))
    counts = model_token_counts(reply)
    assert counts["input_tokens"] is None, (counts, estimated)


# ==================== 判据 ③：两枚值都要进 store 那侧的 values ====================


def test_both_native_counts_reach_the_model_calls_row(tmp_path, monkeypatch):
    row = _model_calls_row(tmp_path, monkeypatch, _native_reply(monkeypatch, _native_body()))
    assert row["input_tokens"] == MEASURED_PROMPT_EVAL_COUNT
    assert row["output_tokens"] == MEASURED_EVAL_COUNT
    assert row["provider"] == "local"


def test_an_unreported_input_lands_as_null_rather_than_zero(tmp_path, monkeypatch):
    """``None`` 写成 ``None``：0 会被读成"命中 0 枚"，那是另一件事（判据 ④ 同一条根）。"""
    row = _model_calls_row(
        tmp_path, monkeypatch, _native_reply(monkeypatch, _native_body(report_input=False))
    )
    assert "input_tokens" in row, "键要在，值才是 NULL —— 缺键与报不出数是两种账"
    assert row["input_tokens"] is None
    assert row["output_tokens"] == MEASURED_EVAL_COUNT


# ==================== 兼容腿：同一条缺陷的第二条腿 ====================


def test_compat_reply_carries_the_prompt_side_of_usage():
    """``compat_reply`` 此前只取 ``completion_tokens``，把 ``prompt_tokens`` 原样扔了。"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(completion_tokens=13, prompt_tokens=4_100),
    )
    reply = compat_reply(response)
    assert reply.transport == TRANSPORT_COMPAT
    assert (reply.output_tokens, getattr(reply, "input_tokens", None)) == (13, 4_100)
    assert model_token_counts(reply) == {"input_tokens": 4_100, "output_tokens": 13}


def test_compat_reply_without_a_usage_object_still_reports_nothing():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=None,
    )
    reply = compat_reply(response)
    assert model_token_counts(reply) == {"input_tokens": None, "output_tokens": None}


def test_both_counts_reach_the_postgres_insert_parameters(tmp_path, monkeypatch):
    """判据 ③ 的落库半边：``model_calls`` 那条 INSERT 的参数里就得有这两枚数。

    用仓里已有的那套假连接（``tests/test_persistence_adapter.py`` 的形状）捕获 ``execute`` 的
    参数，按 INSERT 的列名回读——一次数据库连接都不建立。
    """
    from app.agents.nodes import _ResilientModel
    from app.storage.persistence import PostgresPersistenceAdapter
    from app.trace.store import TraceStore

    observed = []

    class _Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class _Connection:
        def execute(self, sql, params=None):
            observed.append((sql, params))
            return _Result()

        def commit(self):
            return None

        def close(self):
            return None

    store = TraceStore(
        tmp_path / "spans.jsonl",
        persistence=PostgresPersistenceAdapter(lambda: _Connection()),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    config = {
        "configurable": {
            "principal": Principal(user_id="u-38", username="staff38", roles=["staff"]),
            "request_id": "req-38",
            "trace_id": "trace-38",
            "task_id": "task-38",
        }
    }
    reply = _native_reply(monkeypatch, _native_body())

    class _Primary:
        model_name = "qwen3.5:9b"

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            return reply

    _ResilientModel(_Primary(), _NeverUsedOffline()).invoke([], config=config)

    inserts = [
        (statement, bound)
        for statement, bound in observed
        if statement.startswith("INSERT INTO model_calls")
    ]
    # 一次调用两张行：``start_model_call`` 先开一行，``span.finish`` 再合一次，带数的是后者。
    assert len(inserts) == 2, inserts
    sql, params = inserts[-1]
    columns = [column.strip() for column in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
    bound = dict(zip(columns, params))
    assert bound["input_tokens"] == MEASURED_PROMPT_EVAL_COUNT, bound
    assert bound["output_tokens"] == MEASURED_EVAL_COUNT, bound
