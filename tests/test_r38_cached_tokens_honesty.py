"""R38 判据 ④ · ``cached_tokens`` 归真：本机 Ollama 不报它，账上就不许出现它。

跟进单 §21 那行写着「现 ``cached_tokens=0``」。实测事实（两把尺都摆在这）：

- 原生 ``/api/chat`` 腿的应答里根本没有 cached 计数字段 —— 本文件的假应答照真机
  ``docs/perf/raw/rounds.jsonl`` 的形状造，一个 ``cached_tokens`` 都没有；
- OpenAI 兼容 ``/v1`` 腿确实在 ``usage.prompt_tokens_details.cached_tokens`` 上报数
  （``docs/perf/raw/prodpath.jsonl`` 实测 supervisor 292、rewrite 0），而产品里每轮前缀都在变，
  所以那枚 0 是**实测出来的 0**，不是"没读到"的 0。

⇒ 本单选「明写事实」而不是「接上真值来源」：``model_calls`` 至今没有 ``cached_tokens`` 列
（``migrations/0002:147`` 起那几列里没有它），凭空写一枚 0 只会让台账把「没报」读成「命中 0 枚」。
这几枚用例钉的就是：这条链的任何一环都不许造出 ``cached_tokens``。

全程离线，不连模型、不起服务、不碰数据库。
"""
import json
from pathlib import Path

import pytest

from app.common import model_budget
from app.common.model_handler import TRANSPORT_NATIVE, ModelHandler, ModelSource
from app.trace.spans import model_token_counts

REPO = Path(__file__).resolve().parent.parent
SPANS_SRC = REPO / "app" / "trace" / "spans.py"
CONTRACT_DOC = REPO / "docs" / "api" / "contract-v1.md"

#: 判据 ④ 要求「明写」的两处落点：代码注释一处、契约一处。用例把它钉成契约，
#: 否则下一个人把它当缺口补掉，又会写回一枚没有出处的 0。
CACHED_FACT_CODE = "native_leg_reports_no_cached_tokens"
#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主模型端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"


@pytest.fixture
def native_reply(monkeypatch):
    """一枚照真机形状造的原生应答：它没有 cached 字段，所以也不该长出 cached 字段。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3.5:9b")
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    body = {
        "model": "qwen3.5:9b",
        "message": {"role": "assistant", "content": json.dumps({"rewrites": []})},
        "done_reason": "stop",
        "done": True,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 116,
        "prompt_eval_duration": 3_733_000_000,
        "eval_count": 400,
        "eval_duration": 45_883_000_000,
        "total_duration": 49_716_000_000,
    }
    handler = ModelHandler()
    monkeypatch.setattr(handler, "_native_chat_request", lambda url, payload, *, timeout: body)
    reply = handler.chat(
        messages=[{"role": "user", "content": "改写这个问题"}],
        source=ModelSource.LOCAL,
        stream=False,
    )
    assert reply.transport == TRANSPORT_NATIVE
    return reply


def test_the_metering_summary_carries_exactly_two_keys(native_reply):
    """这条链只报服务端报了的两枚；第三枚既不是 0 也不是 ``None``，而是根本不存在。"""
    counts = model_token_counts(native_reply)
    assert set(counts) == {"input_tokens", "output_tokens"}
    assert "cached_tokens" not in counts


def test_the_reply_object_grows_no_cached_token_field(native_reply):
    assert not hasattr(native_reply, "cached_tokens"), "ModelReply 只带服务端报过的数"


def test_the_honesty_note_is_written_at_the_boundary_that_would_have_invented_it():
    """``model_token_counts`` 是唯一有权把 token 数变成账的地方，事实必须写在它身上。"""
    source = SPANS_SRC.read_text(encoding="utf-8")
    assert CACHED_FACT_CODE in source, "spans.py 里那枚「本机不报 cached_tokens」的注释不能丢"


def test_the_contract_registers_the_same_fact():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert CACHED_FACT_CODE in text, "契约里那行登记不能丢，否则 0 又会被当成实测命中"
