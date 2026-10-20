r"""R591 · 真打一次：兼容腿带上 ``reasoning_effort:"none"`` 之后必须三格同时成立。

判据④ 要求的三件事，一枚钉同时钉住：**正文非空** 且 **reasoning 为空** 且 **finish=stop**。
默认 **skip**，``EB_OLLAMA_ACCEPTANCE=1`` 且配置里的模型端点真的答得出模型名才跑（门在
``tests/_live_model.py``，与 ``tests/test_orchestrator.py`` 同一枚在册闸；``test_r540_*`` 的
"常驻的那半格离线、真打那半格显式开"就是同一先例）。一台正在跑评测的机器不该为这枚钉付
GPU，所以它不在全量门里。

两臂的分工不是重复，是各证一半：

1. ``..._raw_compat_body_...``：用**产品自己的**字段来源（``thinking_extra_body()``）与
   **产品自己的**档位预算（``model_tier_budget(ANALYSIS).max_tokens``）拼一枚 `/v1` 报文，
   三格全读服务端原始帧。reasoning 那一格**只能**从这里读——实测
   ``langchain_openai`` 1.3.2 把 ``message.reasoning`` 整通道丢掉（离线探针：
   additional_kwargs 只剩 ``{"refusal": null}``），所以任何走 LangChain 对象的钉都"证明不了
   思考为空"，它只是看不见。这一点本身写在这里，不许被当成第二条证据。
2. ``..._answer_leg_...``：真的 ``_make_model`` 一发，钉产品侧收得到正文、且这一发没被记成
   ``empty_answer_rejected``。

凭据（2026-10-03 交机时各跑过一次）：raw 臂 8.48 s / 338 generated tokens / content 572 /
reasoning 0 / finish=stop；同体摘掉 ``reasoning_effort`` 的控制臂 73.49 s / 1536 / 0 / 5554 /
length（``%TEMP%\r591-probe.txt``、``%TEMP%\evalrun\r591-compat-lever.txt``）。控制臂**不在本件
里重跑**：再花 40 s 复现同一枚已被六臂证伪的字段，是打模型，不是取证。
"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import HumanMessage

REPO_ROOT = Path(__file__).resolve().parents[1]
_gate_spec = importlib.util.spec_from_file_location(
    "r591_live_model_gate", REPO_ROOT / "tests" / "_live_model.py"
)
_live_model = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_live_model)

from app.agents.contracts import ModelTier  # noqa: E402
from app.agents.nodes import _make_model, answer_text  # noqa: E402
from app.common.model_budget import (  # noqa: E402
    REASONING_EFFORT_DISABLED_VALUE,
    REASONING_EFFORT_REQUEST_FIELD,
    THINKING_REQUEST_FIELD,
    budget_event_counts,
    model_tier_budget,
    thinking_extra_body,
)
from app.common.model_config import get_local_model_settings  # noqa: E402

pytestmark = _live_model.live_model_required

QUESTION = "员工市内交通费怎么报销？请一句话回答。"


def read_compat_frame(payload: dict) -> dict:
    """Reduce one ``/v1/chat/completions`` frame to the three readings 判据④ asks for.

    Plain field names, no LangChain in the path: the product's own object cannot witness the
    reasoning channel (``langchain_openai`` 1.3.2 drops ``message.reasoning``), so the second of
    the three facts has to be read off the server's frame or not at all.
    """
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = payload.get("usage") or {}
    return {
        "content": str(message.get("content") or ""),
        "reasoning": str(message.get("reasoning") or message.get("reasoning_content") or ""),
        "finish": str(choice.get("finish_reason") or ""),
        "completion_tokens": usage.get("completion_tokens"),
    }


def thinking_off_verdicts(readings: dict) -> list[str]:
    """The three 判据④ facts as one AND, returning the names of whichever ones failed.

    An empty list is the only pass. The verdicts are named rather than merged into one boolean
    because the three failures are three different incidents: text that arrived but was cut at
    the cap is not text that never arrived, and text that arrived *alongside* a thinking chain is
    a field the server ignored. A single ``assert ok`` would let a fix that satisfies one格 and
    loses two read as progress.
    """
    failed = []
    if not readings["content"].strip():
        failed.append("empty_content")
    if readings["reasoning"].strip():
        failed.append("reasoning_not_empty")
    if readings["finish"] != "stop":
        failed.append(f"finish_not_stop({readings['finish'] or 'none'})")
    return failed


def _compat_endpoint() -> str:
    base = (get_local_model_settings().base_url or "").strip().rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def test_the_raw_compat_body_stops_thinking_and_delivers_text():
    """三格 AND：正文非空 ∧ reasoning 为空 ∧ finish=stop。摘掉字段即红（反证 K1 的真机半边）。"""
    settings = get_local_model_settings()
    budget = model_tier_budget(ModelTier.ANALYSIS)
    body = {
        "model": settings.model_name,
        "messages": [{"role": "user", "content": QUESTION}],
        "stream": False,
        "max_tokens": budget.max_tokens,
        **thinking_extra_body(),
    }
    assert body[REASONING_EFFORT_REQUEST_FIELD] == REASONING_EFFORT_DISABLED_VALUE
    assert body[THINKING_REQUEST_FIELD] == {"type": "disabled"}

    with httpx.Client(trust_env=False, timeout=budget.timeout_seconds) as client:
        response = client.post(f"{_compat_endpoint()}/chat/completions", json=body)

    assert response.status_code == 200, response.text[:400]
    readings = read_compat_frame(response.json())
    #: The reading the paper quotes. Seconds and token counts are what make this 取证 and not
    #: an assertion: a fix that only works when nobody measures it is not a fix.
    print(json.dumps({
        "arm": "r591-live-compat-lever",
        "model": settings.model_name,
        "max_tokens": budget.max_tokens,
        "finish": readings["finish"],
        "content_chars": len(readings["content"].strip()),
        "reasoning_chars": len(readings["reasoning"].strip()),
        "completion_tokens": readings["completion_tokens"],
    }, ensure_ascii=False))

    assert thinking_off_verdicts(readings) == [], f"三格 AND 未同时成立：{readings}"


def test_the_product_answer_leg_delivers_visible_text():
    """产品那一发必须真答出字，而且不许被记成一枚空正文——这条腿才是 run16/run17 死掉的那条。"""
    before = budget_event_counts()["empty_answer_rejected"]
    reply = _make_model(ModelTier.ANALYSIS, prompt=QUESTION).invoke(
        [HumanMessage(content=QUESTION)]
    )

    assert answer_text(reply), "产品腿收回零字正文：判据④ 的第一格就不成立"
    assert budget_event_counts()["empty_answer_rejected"] == before, (
        "这一发被边界记成了 no_answer_produced，正文非空的那一格是假话"
    )
    finish = str((getattr(reply, "response_metadata", None) or {}).get("finish_reason") or "")
    assert finish == "stop", f"finish_reason={finish}：第三格（没被预算截断）不成立"
