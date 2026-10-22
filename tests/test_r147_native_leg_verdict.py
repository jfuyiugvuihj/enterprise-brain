"""R147：把「这台服务器没有原生 API」与「它拒了我这一条报文」拆成两枚判定。

工单判据（跟进单 §76 七、计划书 R147 行）只有两格：

1. 喂一枚**人为造错的 400** ⇒ 原生腿**不许退役**，且必须留下**具名读数**；
2. 喂 **404** ⇒ **必须退役**（这才是"这台机器没有 /api/chat"）。

写域只有 ``app/common/model_handler.py`` 与本文件。判定**不许**被复制进
``app/agents/nodes.py`` / ``app/agents/orchestrator.py``——
``test_the_verdict_is_not_copied_into_the_agent_layer`` 用 AST 把它钉住。

🔴 本案不手工构造异常去喂 ``_native_chat``：那只证明"测试造的东西被原样吐出来"，证明不了
``status_code -> 异常种类`` 这一步分对了。所有状态码都从假冒的 ``httpx.Client`` 走**真的**
``_native_chat_request``（R29 E 段的教训：形状冲突在服务端留下的原文就是 400）。
"""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.contracts import ModelTier
from app.common import model_budget, model_handler
from app.common.model_budget import ModelContextLimitExceeded
from app.common.model_handler import (
    NATIVE_PROTOCOL_ABSENT_STATUSES,
    NATIVE_REQUEST_REJECTED_STATUSES,
    NATIVE_VERDICT_ANSWERED,
    NATIVE_VERDICT_NOT_JSON,
    NATIVE_VERDICT_PROTOCOL_ABSENT,
    NATIVE_VERDICT_REQUEST_REJECTED,
    NATIVE_VERDICT_UNTRIED,
    TRANSPORT_COMPAT,
    ModelHandler,
    ModelSource,
)

#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主 Ollama 的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
SAFE_MODEL = "qwen3.5:9b"
#: R29 在宿主 127.0.0.1:11434 上实测到的 400 原文（OpenAI 形状的 tool_calls.arguments 打上
#: 原生腿）。本单把它当"我方报文错"的标准样本，一字不改。
#: 400 原文不是手抄的：下面那枚用例把它和 R29 在宿主上实测抓下的常量逐字对回去，
#: 对不上就红。R29 的原文里同时有单引号和双引号，所以这里用双引号包住、内层转义。
SHAPE_400_BODY = "{\"error\":\"Value looks like object, but can't find closing '}' symbol\"}"
REWRITE_ANSWER = "{\"rewrites\": []}"


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    monkeypatch.delenv("MODEL_ENABLE_THINKING", raising=False)
    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


class _Response:
    """一条 canned HTTP 应答：状态码、正文，以及一个可能撒谎的 json()。"""

    def __init__(self, status_code, text="", body=None):
        self.status_code = status_code
        self.text = text
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP " + str(self.status_code))

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class _Server:
    """假 httpx.Client：按队列逐条应答，并记下每一次真的往返。"""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, **_ignored):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "payload": json})
        assert self._responses, "测试没准备这一次往返：说明这条腿被多问了一次"
        return self._responses.pop(0)


def _handler(monkeypatch):
    """先造 handler 再假冒 httpx：``ModelHandler.__init__`` 自己就要用 ``httpx.Client``
    装 OpenAI 兼容腿，顺序倒了会把这条腿的客户端换成测试替身。
    """
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", SAFE_MODEL)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    return ModelHandler()


def _on_compat(handler, content=REWRITE_ANSWER):
    """把答题腿架起来：原生腿退回时，答案必须一个不少地从这里出来。"""
    handler.ollama_client.chat.completions = SimpleNamespace(
        create=lambda **_kwargs: SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content), finish_reason="stop"
                )
            ],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )
    )
    return handler


def _native_ok():
    return _Response(
        200,
        body={
            "model": SAFE_MODEL,
            "message": {"role": "assistant", "content": "原生腿的答案"},
            "done": True,
            "done_reason": "stop",
        },
    )


def _ask(handler):
    return handler.chat(
        messages=[{"role": "user", "content": "改写这个问题"}],
        source=ModelSource.LOCAL,
        stream=False,
    )


# ==================== 判据①：400 = 我方报文错 ⇒ 本条退回，腿不退役 ====================


def test_a_fabricated_400_falls_back_but_keeps_the_native_leg(monkeypatch):
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(400, text=SHAPE_400_BODY))
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    reply = _ask(handler)

    assert str(reply) == REWRITE_ANSWER, "报文错不能少一个答案"
    assert reply.transport == TRANSPORT_COMPAT
    assert handler._native_supported is True, "400 说的是我的报文，不是这台服务器没有 API"
    assert len(server.calls) == 1


def test_the_readout_names_a_shape_refusal_as_its_own_verdict(monkeypatch):
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(400, text=SHAPE_400_BODY))
    monkeypatch.setattr(model_handler.httpx, "Client", server)
    assert handler.native_leg_readout() == {
        "supported": True,
        "verdict": NATIVE_VERDICT_UNTRIED,
        "request_rejections": 0,
    }

    _ask(handler)

    assert handler.native_leg_readout() == {
        "supported": True,
        "verdict": NATIVE_VERDICT_REQUEST_REJECTED,
        "request_rejections": 1,
    }


def test_a_shape_refusal_is_asked_again_on_the_next_call(monkeypatch):
    """反证判据①：旧行为在这里只往返一次（整条腿退役了），所以这枚用例改前必红。"""
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(400, text=SHAPE_400_BODY), _native_ok())
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    first = _ask(handler)
    second = _ask(handler)

    assert str(first) == REWRITE_ANSWER
    assert str(second) == "原生腿的答案", "第二问必须重新问原生腿：一次错不等于永久退役"
    assert len(server.calls) == 2
    assert handler.native_leg_readout()["request_rejections"] == 1


def test_a_shape_400_log_says_the_leg_survived(monkeypatch, logs):
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(400, text=SHAPE_400_BODY))
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    _ask(handler)

    messages = [record.getMessage() for record in logs.records]
    named = "verdict=" + NATIVE_VERDICT_REQUEST_REJECTED
    assert any(named in m and "不退役" in m for m in messages), messages
    assert not any("服务端不支持原生" in m for m in messages), "400 不许被说成「没有这个 API」"


# ==================== 判据②：404/405/410 = 协议不存在 ⇒ 必须退役 ====================


@pytest.mark.parametrize("status", sorted(NATIVE_PROTOCOL_ABSENT_STATUSES))
def test_a_protocol_absent_status_retires_the_leg_for_the_process(monkeypatch, status):
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(status, text="no such endpoint"), _native_ok())
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    first = _ask(handler)
    second = _ask(handler)

    assert str(first) == REWRITE_ANSWER and str(second) == REWRITE_ANSWER
    assert handler._native_supported is False, "404 之后还追问就是白付一次往返"
    assert len(server.calls) == 1
    assert handler.native_leg_readout() == {
        "supported": False,
        "verdict": NATIVE_VERDICT_PROTOCOL_ABSENT,
        "request_rejections": 0,
    }


# ==================== 拆分的边界 ====================


def test_the_two_halves_partition_the_old_refusal_set():
    assert NATIVE_PROTOCOL_ABSENT_STATUSES & NATIVE_REQUEST_REJECTED_STATUSES == frozenset()
    assert (
        NATIVE_PROTOCOL_ABSENT_STATUSES | NATIVE_REQUEST_REJECTED_STATUSES
        == model_handler.NATIVE_REFUSED_STATUSES
    )
    assert model_handler.NATIVE_REFUSED_STATUSES == frozenset({400, 404, 405, 410})
    assert NATIVE_REQUEST_REJECTED_STATUSES == frozenset({400})


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_temporary_status_retires_nothing(status, monkeypatch):
    """过载不是"没有 API"：一枚都不许让整条腿退役（R92 就是为此把 429/5xx 挡在外面）。"""
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(status, text="overloaded"))
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    reply = _ask(handler)

    assert handler._native_supported is True
    assert reply.error_code == "model_unavailable", status
    assert len(server.calls) == 1


def test_a_context_limit_400_still_raises_the_typed_error_without_retiring(monkeypatch):
    """400 里那枚「真的嫌太长」的样本：旧语义（抛类型化错）不许丢，新语义（不退役）同样成立。"""
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(400, text="this model context length is 4096 tokens"))
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    with pytest.raises(ModelContextLimitExceeded):
        _ask(handler)

    assert handler._native_supported is True
    assert handler.native_leg_readout()["request_rejections"] == 1


def test_a_non_json_answer_still_retires_and_says_why(monkeypatch):
    """URL 被别的东西应答（代理、登录页）：改报文修不好，所以留在退役那一侧，但名字不同。"""
    handler = _on_compat(_handler(monkeypatch))
    server = _Server(_Response(200, text="<html>login</html>"))
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    _ask(handler)

    assert handler._native_supported is False
    assert handler.native_leg_readout()["verdict"] == NATIVE_VERDICT_NOT_JSON


def test_a_successful_native_answer_moves_the_reading_off_untried(monkeypatch):
    handler = _handler(monkeypatch)
    server = _Server(_native_ok())
    monkeypatch.setattr(model_handler.httpx, "Client", server)

    reply = _ask(handler)

    assert str(reply) == "原生腿的答案"
    assert handler.native_leg_readout()["verdict"] == NATIVE_VERDICT_ANSWERED


# ==================== 判定只此一份：不许复制进 Agent 层 ====================


def test_the_verdict_is_not_copied_into_the_agent_layer():
    root = Path(model_handler.__file__).resolve().parents[2]
    offenders = []
    for rel in ("app/agents/nodes.py", "app/agents/orchestrator.py"):
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            named = getattr(node, "id", None) or getattr(node, "attr", None) or ""
            if "NATIVE_" in named or "native_supported" in named:
                offenders.append((rel, named))
    assert offenders == []


def test_the_shape_400_sample_is_the_one_r29_measured_on_the_host():
    """本单不许自己编一枚"看起来像 400"的样本：它必须逐字等于 R29 抓下的原文。"""
    root = Path(model_handler.__file__).resolve().parents[2]
    tree = ast.parse((root / "tests" / "test_r29_thinking_tax.py").read_text(encoding="utf-8"))
    captured = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == "NATIVE_400_ON_STRING_ARGS" for target in node.targets
        ):
            captured = node.value.value
    assert captured == "HTTP 400: " + SHAPE_400_BODY


def test_the_retirement_assignment_lives_in_exactly_one_branch():
    source = Path(model_handler.__file__).read_text(encoding="utf-8")
    assert source.count("self._native_supported = False") == 1
