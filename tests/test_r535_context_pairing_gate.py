# -*- coding: utf-8 -*-
r"""R535 判据②③ —— 两枚窗口读数必须被同一枚闸读到，不配套要说得出是哪两枚键。

## 这枚钉在量什么

`MODEL_CONTEXT_TOKENS` 是**本进程按之计算**的窗口；请求真正被服务在多大的窗口里，属于模型
服务端——本仓从不把 `num_ctx` 写进任何请求载荷（原生腿 `app/common/model_handler.py` 只带
`options.num_predict`，兼容腿 `app/agents/nodes.py` 只带 `max_tokens`），所以服务端那一半由
服务端自己决定。两半只有在没人单改一头时才对得上。本件钉三件事：

1. **判据②**：`app/common/model_config.py:check_context_pairing` 同时拿到两读数，env 侧宽于
   运行时侧判「不配套」，反方向判「白留着容量」，结果里逐枚点名**键名与两侧读数**；没读到
   运行时那一侧时如实交回 `runtime_unread`，绝不把缺席洗成 `paired`。
2. **判据③**：撞顶那句话带上「本问需要 X 槽位／当前预算只留 Y／要动的是哪两枚必须配套动的
   键」，且**按构造吃不进客户文档正文**——归因函数只收整数与键名。
3. 形界：`context_limit_exceeded` 的语义一格没动（它照旧是封闭枚举里那一枚，四枚判读词
   **不是**对外码）；闸不新开对外路由；一枚缺省值都没改。

## 通道凭据（全部现取，不在本件里编数字）

- 运行时读数通道：`/api/ps` 的 `context_length`，本机实读在 `docs/perf/raw/rate_all.jsonl`
  （`{"ollama":"0.34.0","loaded":[{"name":"qwen3.5:9b","context_length":4096,"size_vram":0}]}`），
  取法同源 `scripts/perf_probe_rate.py:176`；口径出处
  `docs/handoff/2026-09-15-orchestration-board.md:1013`（写明它是运行时实测值、非仓库配置项）。
- 第二条通道：服务端拒发原文里的数（`docs/perf/raw/rate_prefill.jsonl`，
  `... exceeds the available context size (4096 tokens)`），本件从台账现读，不抄字面。
- 运输全部注入，域名不可解析（`ollama.invalid`），加上 `tests/conftest.py` 的宿主端口闸与
  离线发现桩 ⇒ 本件不存在打真机 Ollama 的路径。
"""
import ast
import inspect
import json
import logging
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes
from app.agents.contracts import (
    CONTEXT_LIMIT_CODE,
    CONTEXT_PAIRING_MARKER,
    CONTEXT_WINDOW_ENV_KEY,
    ErrorEnvelope,
    MIN_ANSWER_ENV_KEY,
    ModelTier,
    PAIRING_ACTIONABLE,
    PAIRING_ENV_ABOVE_RUNTIME,
    PAIRING_PAIRED,
    PAIRING_RUNTIME_ABOVE_ENV,
    PAIRING_RUNTIME_UNREAD,
    RUNTIME_WINDOW_ENV_KEY,
    context_refusal_attribution,
    evaluate_context_pairing,
)
from app.common import model_config
from app.common.model_budget import (
    DEFAULT_CONTEXT_TOKENS,
    MODEL_BUDGET_MARKER,
    ModelContextLimitExceeded,
    context_limit_tokens,
    estimate_prompt_tokens,
    model_tier_budget,
    window_plan,
)

REPO = Path(__file__).resolve().parents[1]
#: 不可解析的域名：这条链上任何一枚用例都不存在打到宿主 Ollama 的路径。
BASE = "http://ollama.invalid/v1"
RUNTIME_LEDGER = REPO / "docs" / "perf" / "raw" / "rate_all.jsonl"
REFUSAL_LEDGER = REPO / "docs" / "perf" / "raw" / "rate_prefill.jsonl"
#: 本单写域三枚产品件：判据② 的「不许新开对外路由」逐枚 AST 扫这三棵。
TOUCHED = (
    REPO / "app" / "common" / "model_config.py",
    REPO / "app" / "agents" / "contracts.py",
    REPO / "app" / "agents" / "nodes.py",
)
#: 2813 枚字 → 2817 枚槽（尺子在 app/common/model_budget.py：一枚 CJK 一字一槽 + 每枚
#: 消息 MESSAGE_OVERHEAD_TOKENS=4 枚，与 test_r255 同一把）。守卫只给资料留 2560 枚，
#: 所以这一串必然撞顶。下面那枚 PROMPT_TOKENS 是**当场现推**的读数，本件末尾的自证格
#: 对它负责——注释里的数只是说明，不当判据（上一班这里写的是一枚过期的数，已订正）。
OVERSIZED_PROMPT = "机密采购价目表" * 381 + "数" * 146
PROMPT_TOKENS = estimate_prompt_tokens([{"role": "user", "content": OVERSIZED_PROMPT}])
#: 一头发得出去的短问：第二条通道要在「预发不拦、服务端自己拒」那一支上量。
FITTING = "住宿费标准是什么"
CANARY = "机密采购价目表"


class _CountingFetch:
    """注入的假 transport：记录每一次 URL，绝不开 socket。"""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        for suffix, payload in self.routes.items():
            if url.endswith(suffix):
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError("unrouted url: " + url)


def _ps_payload(models):
    """按 Ollama `/api/ps` 的形状交回（app 读的是 models 这一格）。"""
    return {"models": list(models)}


@pytest.fixture(autouse=True)
def _one_pair_at_a_time(monkeypatch):
    """每枚用例从「两枚都没读过、缺省即盘面」出发：环境干净，两枚缓存都归零。"""
    for name in (
        "MODEL_CONTEXT_TOKENS",
        "MODEL_MIN_ANSWER_TOKENS",
        "LOCAL_MODEL_KEEP_ALIVE",
        "OLLAMA_REQUIRE_GPU",
    ):
        monkeypatch.delenv(name, raising=False)
    model_config.reset_runtime_context_window()
    nodes.reset_context_pairing_log()
    yield
    model_config.reset_runtime_context_window()
    nodes.reset_context_pairing_log()


def _recorded_resident_models():
    """台账里那一条运行时读数，换成 app 读的 `models` 形状（数字一格不编）。"""
    for line in RUNTIME_LEDGER.read_text(encoding="utf-8-sig").splitlines():
        payload = line[6:] if line.startswith("JSONL ") else line
        if not payload.startswith("{"):
            continue
        record = json.loads(payload)
        if record.get("case") == "runtime":
            return [
                {
                    "name": entry["name"],
                    "context_length": entry["context_length"],
                    "size_vram": entry.get("size_vram", 0),
                }
                for entry in record["loaded"]
            ]
    raise AssertionError(f"no runtime record in {RUNTIME_LEDGER}")


def _recorded_refusal_parts():
    """服务端拒发原文：与 test_r255 同一本台账、同一把剥法，逐层 json.loads。"""
    for line in REFUSAL_LEDGER.read_text(encoding="utf-8-sig").splitlines():
        payload = line[6:] if line.startswith("JSONL ") else line
        if not payload.startswith("{"):
            continue
        record = json.loads(payload)
        if record.get("case_note") == "http_400":
            inner = json.loads(json.loads(record["detail"])["error"])["error"]
            return inner["message"], inner
    raise AssertionError(f"no http_400 record in {REFUSAL_LEDGER}")


# ==================== 判据②：两个方向都要判得出来，缺席不许当通过 ====================


def test_env_wider_than_the_server_is_judged_not_paired():
    """env 要的 > 运行时给得起的 ⇒ 判「不配套」，键名与两侧读数逐一点名。"""
    pairing = evaluate_context_pairing(
        declared_window_tokens=8192,
        runtime_window_tokens=4096,
        declared_window_source="env",
        runtime_window_source="ps",
        tier="analysis",
        declared_max_tokens=1536,
        min_answer_tokens=1536,
    )

    assert pairing.verdict == PAIRING_ENV_ABOVE_RUNTIME
    assert pairing.actionable is True and pairing.verdict in PAIRING_ACTIONABLE
    assert pairing.delta_tokens == 4096
    for named in (
        CONTEXT_WINDOW_ENV_KEY,
        RUNTIME_WINDOW_ENV_KEY,
        "8192",
        "4096",
        "不配套",
    ):
        assert named in pairing.sentence, pairing.sentence


def test_the_reverse_direction_names_idle_capacity():
    """反方向（判据② 第二问）：运行时远宽于声明 ⇒ 报「白留着容量」。"""
    pairing = evaluate_context_pairing(
        declared_window_tokens=4096,
        runtime_window_tokens=8192,
        declared_window_source="code-default",
        runtime_window_source="ps",
        tier="analysis",
        declared_max_tokens=1536,
        min_answer_tokens=1536,
    )

    assert pairing.verdict == PAIRING_RUNTIME_ABOVE_ENV
    assert pairing.idle_capacity is True and pairing.actionable is True
    assert pairing.delta_tokens == 4096
    assert "白留着" in pairing.sentence
    assert CONTEXT_WINDOW_ENV_KEY in pairing.sentence and RUNTIME_WINDOW_ENV_KEY in pairing.sentence


def test_a_narrower_gap_is_the_same_direction_without_the_idle_claim():
    """「远小于」要有据：不足 2 倍那一档只报方向，不冒充白留着容量。"""
    pairing = evaluate_context_pairing(
        declared_window_tokens=4096,
        runtime_window_tokens=6144,
        runtime_window_source="ps",
        declared_max_tokens=1536,
    )

    assert pairing.verdict == PAIRING_RUNTIME_ABOVE_ENV
    # 「没到白留着」要说得出证据：先判句式（那一格的说法是「白留着容量：运行时给到 …」），
    # 再判 idle_capacity 布尔——反过来写会把「还没到『白留着』那一格」这句诚实话当成违规。
    assert not pairing.sentence.startswith("白留着容量"), pairing.sentence
    assert pairing.idle_capacity is False and pairing.delta_tokens == 2048
    assert "还没到" in pairing.sentence, pairing.sentence


def test_equal_windows_are_paired_and_say_nothing_further():
    pairing = evaluate_context_pairing(
        declared_window_tokens=4096,
        runtime_window_tokens=4096,
        declared_window_source="code-default",
        runtime_window_source="ps",
        declared_max_tokens=1536,
    )

    assert pairing.verdict == PAIRING_PAIRED
    assert pairing.actionable is False and pairing.delta_tokens == 0


@pytest.mark.parametrize("unread", [None, 0])
def test_an_unobserved_server_is_never_printed_as_paired(unread):
    """缺席不是绿灯：没读到运行时那一侧就判 `runtime_unread`，且不许洗成 `paired`。"""
    pairing = evaluate_context_pairing(
        declared_window_tokens=4096,
        runtime_window_tokens=unread,
        declared_window_source="code-default",
        declared_max_tokens=1536,
    )

    assert pairing.verdict == PAIRING_RUNTIME_UNREAD
    assert pairing.actionable is False
    assert "配套：" not in pairing.sentence, pairing.sentence
    assert CONTEXT_WINDOW_ENV_KEY in pairing.sentence and RUNTIME_WINDOW_ENV_KEY in pairing.sentence


def test_the_room_subtraction_still_comes_from_the_one_registered_home():
    """判据② 不许再抄一遍减法：room 仍是 contracts.prompt_room 那一枚（R463 口径）。"""
    pairing = evaluate_context_pairing(
        declared_window_tokens=4096,
        runtime_window_tokens=8192,
        declared_max_tokens=1536,
    )

    assert pairing.prompt_room_tokens == 2560
    assert pairing.prompt_room_tokens == window_plan(ModelTier.ANALYSIS).prompt_room_tokens


# ==================== 判据② 的闸本体：一次调用里两枚读数都要真到手 ====================


def test_the_gate_reads_both_halves_and_judges_the_direction(monkeypatch):
    """**K1 的 victim**：把闸里读运行时那一格摘成 ``None``（见反证件 K1）⇒ 本句当场红。

    判据② 要的是「两枚读数被同一枚闸读到」，不是「两枚函数都存在」——所以这一格钉的是
    同一次调用里的**两半**：声明侧跟着环境走、运行时侧跟着台账读数走，判决还得说出键名。
    """
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "8192")
    model_config.record_runtime_context_window(4096, source="api/ps")

    pairing = model_config.check_context_pairing(tier=ModelTier.ANALYSIS)

    assert pairing.verdict == PAIRING_ENV_ABOVE_RUNTIME, pairing.as_dict()
    assert pairing.declared_window_tokens == 8192 and pairing.declared_window_source == "env"
    assert pairing.runtime_window_tokens == 4096 and pairing.runtime_window_source == "api/ps"
    assert "不配套" in pairing.sentence, pairing.sentence
    assert CONTEXT_WINDOW_ENV_KEY in pairing.sentence and RUNTIME_WINDOW_ENV_KEY in pairing.sentence


def test_the_claimed_half_follows_the_environment_and_the_one_reading_home(monkeypatch):
    """**K1b 的 victim**：把闸里声明那一格写死成 4096（反证件 K1b）⇒ 本句当场红。

    另一半同样不许漂：不设环境时必须等于 ``DEFAULT_CONTEXT_TOKENS``，且与 ``context_limit_tokens()``
    同一枚数——本单没有为窗口开第二个读数口。
    """
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")
    raised = model_config.check_context_pairing(tier=ModelTier.ANALYSIS)
    monkeypatch.delenv("MODEL_CONTEXT_TOKENS", raising=False)
    shipped = model_config.check_context_pairing(tier=ModelTier.ANALYSIS)

    assert raised.declared_window_tokens == 16384, raised.as_dict()
    assert raised.declared_window_source == "env"
    assert shipped.declared_window_tokens == DEFAULT_CONTEXT_TOKENS == context_limit_tokens()
    assert shipped.declared_window_source == "code-default"
    assert shipped.declared_window_tokens == window_plan(ModelTier.ANALYSIS).context_limit_tokens


# ==================== 运行时那一半的通道：台账形状 / 缺席 / 节流 / 不抹旧读数 ====================


def test_the_resident_reading_is_taken_from_the_recorded_ps_shape():
    """通道一用的是在册凭据（``docs/perf/raw/rate_all.jsonl`` 那条 runtime 记录），不是编的形状。"""
    resident = _recorded_resident_models()

    assert [entry["context_length"] for entry in resident] == [4096], resident
    assert model_config.runtime_window_from_ps_payload(_ps_payload(resident)) == 4096


def test_the_shipped_pair_is_the_same_number_on_this_machine():
    """判据① 的收口：此刻两半确实是同一枚数——这是「本单不改缺省」的事实根据，不是主张。"""
    served = model_config.runtime_window_from_ps_payload(_ps_payload(_recorded_resident_models()))

    assert served == DEFAULT_CONTEXT_TOKENS == window_plan(ModelTier.ANALYSIS).context_limit_tokens
    assert served == 4096


def test_absence_is_recorded_as_absence_and_never_as_a_zero_window():
    """缺席的四种形状都得交回 ``None``：0、缺键、布尔、非列表——一枚都不许被读成「窗口是 0」。"""
    for shape in (
        None,
        {"models": []},
        {"models": [{"name": "m"}]},
        {"models": [{"context_length": 0}]},
        {"models": [{"context_length": True}]},
        {"models": [None]},
        {"models": "not-a-list"},
        {},
    ):
        assert model_config.runtime_window_from_ps_payload(shape) is None, shape


def test_the_widest_resident_window_wins():
    """两枚模型在场时取最宽：报窄了会造出一枚根本不存在的「不配套」。"""
    payload = _ps_payload(
        [{"name": "small", "context_length": 4096, "size_vram": 0},
         {"name": "wide", "context_length": 8192, "size_vram": 0}]
    )

    assert model_config.runtime_window_from_ps_payload(payload) == 8192


def test_an_unanswerable_probe_leaves_the_pairing_unread_and_raises_nothing(monkeypatch):
    """探针问不到 ⇒ 如实交回 ``runtime_unread``，且这一路一个字都不许冒出来。"""
    dead = _CountingFetch({"/api/ps": ConnectionRefusedError("no registry")})
    with pytest.raises(ConnectionRefusedError):
        dead("http://ollama.invalid/api/ps")  # 对照组：假件真会抛，不是空转的计数器
    fake = _CountingFetch({"/api/ps": ConnectionRefusedError("no registry")})
    monkeypatch.setattr(model_config, "_fetch_registry", fake)

    state = model_config.observe_runtime_context_window(BASE)
    pairing = model_config.check_context_pairing(tier=ModelTier.ANALYSIS)

    assert state["tokens"] is None
    assert state["source"] == "probe_failed:ConnectionRefusedError", state
    assert pairing.verdict == PAIRING_RUNTIME_UNREAD and pairing.actionable is False
    assert fake.calls == ["http://ollama.invalid/api/ps"], fake.calls


def test_the_registry_question_is_throttled(monkeypatch):
    """60 s 的 TTL 是常数不是旋钮（本单不许开旋钮）：健康轮询不许把模型服务端问穿。"""
    fetch = _CountingFetch({"/api/ps": _ps_payload([{"name": "m", "context_length": 4096, "size_vram": 0}])})
    monkeypatch.setattr(model_config, "_fetch_registry", fetch)

    first = model_config.observe_runtime_context_window(BASE, now=1_000.0)
    cached = model_config.observe_runtime_context_window(BASE, now=1_030.0)
    later = model_config.observe_runtime_context_window(BASE, now=1_061.0)

    assert first["tokens"] == cached["tokens"] == later["tokens"] == 4096
    assert len(fetch.calls) == 2, fetch.calls
    assert fetch.calls == ["http://ollama.invalid/api/ps"] * 2, "问的必须是原生登记表,不是 /v1 那条"


def test_an_empty_answer_does_not_forget_a_window_already_seen(monkeypatch):
    """keep_alive 到点以后 `/api/ps` 会交回空表；那时操作员正在读日志，不许当场失忆。"""
    routes = {"/api/ps": _ps_payload([{"name": "m", "context_length": 4096, "size_vram": 0}])}
    monkeypatch.setattr(model_config, "_fetch_registry", _CountingFetch(routes))

    model_config.observe_runtime_context_window(BASE, force=True)
    routes["/api/ps"] = _ps_payload([])
    state = model_config.observe_runtime_context_window(BASE, force=True)

    assert state["tokens"] == 4096 and state["source"] == "api/ps", state


def test_the_reading_state_opens_no_socket_and_names_its_own_absence():
    """读这一格永远不开 socket：没探测过就说没探测过，不借两端的数填空。"""
    state = model_config.runtime_context_window_state()

    assert state["tokens"] is None and state["detail"] == "not_probed", state
    assert state["source"] == "" and state["age_seconds"] is None


# ==================== 通道二：服务端拒发原文里的那一枚数（零额外请求） ====================


def test_the_servers_own_number_is_harvested_from_a_provider_refusal():
    """台账里那句真话 → 4096：原文形状与剥出的数都现读，不抄字面。"""
    message, inner = _recorded_refusal_parts()

    assert "available context size" in message, message
    assert model_config.runtime_window_from_refusal(message) == 4096
    assert model_config.runtime_window_from_refusal(json.dumps(inner)) == 4096


def test_the_servers_json_n_ctx_is_read_but_our_own_claim_is_never_read_back():
    """反自毒：服务端的 ``"n_ctx": 4096`` 收，自家那句 ``n_ctx=4314`` 不收。

    把引起撞顶的那枚数读回来，等于用被告的话给原告作证——配套判读会当场洗绿。
    这一格就是 ``_RUNTIME_WINDOW_PATTERNS`` 里故意不收 ``n_ctx=`` 写法的原因。
    """
    assert model_config.runtime_window_from_refusal('{"error":{"n_ctx":4096}}') == 4096
    refused = ModelContextLimitExceeded(model_tier_budget(ModelTier.ANALYSIS), 2778)

    assert "needs n_ctx=4314" in str(refused), str(refused)
    assert model_config.runtime_window_from_refusal(str(refused)) is None
    for empty in ("", None):
        assert model_config.runtime_window_from_refusal(empty) is None


class _RecordingModel:
    """只记账的 primary：与 test_r30 / test_r255 同一形状，本件不复用它们的假件。"""

    def __init__(self, error: Exception | None = None):
        self.calls: list[dict] = []
        self.error = error

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        from langchain_core.messages import AIMessage

        return AIMessage(content="答案", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        from langchain_core.messages import AIMessage

        yield AIMessage(content="答案", response_metadata={"finish_reason": "stop"})

    def bind_tools(self, tools):
        return self


def _boundary(primary):
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="r535-test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )


def _bagged_config():
    from app.agents.evidence import new_evidence_bag

    bag = new_evidence_bag()
    return {
        "configurable": {
            "evidence_bag": bag,
            "trace_id": "trace-r535",
            "request_id": "01a0af5c-e4ce-7830-a9b9-5e83d27bc4ff",
        }
    }, bag


def test_a_provider_refusal_teaches_the_gate_the_servers_window():
    """经 `nodes` 走一发真撞顶的请求：服务端那一半被摘进台账，判决与码一个字没动。"""
    message, _ = _recorded_refusal_parts()
    primary = _RecordingModel(error=RuntimeError(message))

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _boundary(primary).invoke([HumanMessage(content=FITTING)])

    assert refused.value.code == CONTEXT_LIMIT_CODE
    state = model_config.runtime_context_window_state()
    assert state["tokens"] == 4096 and state["source"] == "provider_refusal", state
    pairing = model_config.check_context_pairing(tier=ModelTier.ANALYSIS)
    assert pairing.verdict == PAIRING_PAIRED and pairing.runtime_window_source == "provider_refusal"


# ==================== 判据② 的启动把手：一次说一句，缺席也照说，坏了不塌建图 ====================


def _start_up_analysis_model(monkeypatch, context_length=4096):
    """把 `nodes._make_model` 摆到「本机 base_url + 一台答话的登记表」上，不碰任何 socket。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", BASE)
    monkeypatch.setenv("LOCAL_MODEL_NAME", "r535-test-model")
    fetch = _CountingFetch(
        {"/api/ps": _ps_payload([{"name": "r535-test-model", "context_length": context_length, "size_vram": 0}])}
    )
    monkeypatch.setattr(model_config, "_fetch_registry", fetch)
    return fetch


def _pairing_records(caplog):
    return [r for r in caplog.records if CONTEXT_PAIRING_MARKER in r.getMessage()]


def test_the_startup_handle_announces_the_pairing_once_per_verdict(monkeypatch, caplog):
    """判据② 要的「启动一行」：连建两枚图只说一句，读数变了才再说一句，级别跟着判决走。"""
    fetch = _start_up_analysis_model(monkeypatch)

    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        model = nodes._make_model(ModelTier.ANALYSIS)
        first = _pairing_records(caplog)
        assert len(first) == 1, [r.getMessage() for r in first]
        assert first[0].levelno == logging.INFO, first[0].getMessage()
        assert "verdict=paired" in first[0].getMessage(), first[0].getMessage()

        nodes._make_model(ModelTier.ANALYSIS)
        assert len(_pairing_records(caplog)) == 1, "同一枚判决说了两遍：一行一句话的规矩没守住"

        caplog.clear()
        fetch.routes["/api/ps"] = _ps_payload([{"name": "r535-test-model", "context_length": 8192, "size_vram": 0}])
        model_config.record_runtime_context_window(8192, source="api/ps")
        nodes._make_model(ModelTier.ANALYSIS)
        second = _pairing_records(caplog)

    assert isinstance(model, nodes._ResilientModel)
    assert len(second) == 1, [r.getMessage() for r in second]
    assert second[0].levelno == logging.WARNING, second[0].getMessage()
    assert PAIRING_RUNTIME_ABOVE_ENV in second[0].getMessage()
    assert CONTEXT_WINDOW_ENV_KEY in second[0].getMessage() and "白留着" in second[0].getMessage()


def test_the_handle_says_the_absent_half_out_loud_instead_of_going_quiet(monkeypatch, caplog):
    """服务端还没被问到 ⇒ 启动那一行必须存在并说清「只读到一侧」，不许静默当绿灯。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", BASE)
    monkeypatch.setenv("LOCAL_MODEL_NAME", "r535-test-model")
    monkeypatch.setattr(model_config, "_fetch_registry", _CountingFetch({"/api/ps": ConnectionRefusedError("no registry")}))

    with caplog.at_level(logging.INFO, logger="enterprise_brain"):
        nodes._make_model(ModelTier.ANALYSIS)

    lines = [r.getMessage() for r in _pairing_records(caplog)]
    assert len(lines) == 1, lines
    assert PAIRING_RUNTIME_UNREAD in lines[0], lines[0]
    assert CONTEXT_WINDOW_ENV_KEY in lines[0] and RUNTIME_WINDOW_ENV_KEY in lines[0]


def test_a_broken_probe_never_takes_the_graph_down(monkeypatch, caplog):
    """自检只是看一眼：它炸了也只留一行告警，建图照旧成功。

    一台服务因为自己的自检读不到模型服务端而起不来，那才是本单真正该修的第二个 bug。
    """
    _start_up_analysis_model(monkeypatch)
    monkeypatch.setattr(nodes, "observe_runtime_context_window", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("probe exploded")))

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        model = nodes._make_model(ModelTier.ANALYSIS)

    assert isinstance(model, nodes._ResilientModel)
    lines = [r.getMessage() for r in _pairing_records(caplog)]
    assert len(lines) == 1 and "配套自检未运行" in lines[0], lines


def test_the_announcement_is_wired_once_at_the_model_factory():
    """接线形状：只有 `_make_model` 说这一句，别处再挂一枚就会把「启动一行」变成 N 行。"""
    source = (REPO / "app" / "agents" / "nodes.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    factory = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_make_model"]
    assert len(factory) == 1, "本件的取段前提变了"

    inside = [n for n in ast.walk(factory[0]) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_log_context_pairing"]
    everywhere = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_log_context_pairing"]
    assert len(inside) == 1, inside
    assert len(everywhere) == 1, "启动把手被挂到了第二处：一次建图会打两行"


# ==================== 判据③：撞顶那一发旁边多一行归因，正文一个字都不跟着走 ====================


def test_a_refused_customer_question_names_the_numbers_and_never_the_document(caplog):
    """端到端形状：本问需要多少槽位、当前只留多少、要动的是哪两枚键——而客户正文不在任何一行里。"""
    config, bag = _bagged_config()
    primary = _RecordingModel()
    budget = model_tier_budget(ModelTier.ANALYSIS)
    required = budget.required_context_tokens(PROMPT_TOKENS)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(ModelContextLimitExceeded) as refused:
            _boundary(primary).invoke([HumanMessage(content=OVERSIZED_PROMPT)], config=config)

    lines = [r.getMessage() for r in _pairing_records(caplog)]
    assert len(lines) == 1, lines
    line = lines[0]
    for named in (
        f"本问需要 {required} 枚",
        f"还差 {refused.value.over_by_tokens} 枚",
        f"{CONTEXT_WINDOW_ENV_KEY}={budget.context_limit_tokens}",
        RUNTIME_WINDOW_ENV_KEY,
        MIN_ANSWER_ENV_KEY,
        "recreate",
    ):
        assert named in line, (named, line)
    assert "配套自检" not in line, "运行时那一侧没有读数，不许编一段配对话出来"
    # 归因用的是数不是文：客户文档一个字都不许进日志、异常或证据袋。
    for record in caplog.records:
        assert CANARY not in record.getMessage(), record.getMessage()
    assert CANARY not in str(refused.value)
    assert CANARY not in json.dumps(bag, ensure_ascii=False, default=str)
    # 判决一格没动：照旧没发出去、照旧那一枚码、照旧不走兜底文案。
    assert primary.calls == [], "请求发出去了：守卫不再排在前面"
    statuses = [(item["status"], item["error_code"]) for item in bag["model_statuses"]]
    assert ("failed", CONTEXT_LIMIT_CODE) in statuses, statuses
    assert not any("model_unavailable" in code for _, code in statuses), statuses
    budget_lines = [r.getMessage() for r in caplog.records if MODEL_BUDGET_MARKER in r.getMessage()]
    assert len(budget_lines) == 1, budget_lines


def test_the_refusal_line_carries_the_pairing_once_the_gate_has_a_reading(caplog, monkeypatch):
    """两枚读数都到手时，同一行归因里就带上配对话；缺席时不带——这一格是「归因不许编」的另一半。"""
    monkeypatch.setattr(
        model_config,
        "_fetch_registry",
        _CountingFetch({"/api/ps": _ps_payload([{"name": "m", "context_length": 16384, "size_vram": 0}])}),
    )
    model_config.observe_runtime_context_window(BASE)
    config, bag = _bagged_config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(ModelContextLimitExceeded):
            _boundary(_RecordingModel()).invoke([HumanMessage(content=OVERSIZED_PROMPT)], config=config)

    lines = [r.getMessage() for r in _pairing_records(caplog)]
    assert len(lines) == 1, lines
    assert "配套自检" in lines[0], lines[0]
    assert "白留着容量" in lines[0], lines[0]  # 归因行走的是散文,判决字面量只在启动那一行里
    assert CANARY not in lines[0]


def test_the_attribution_takes_nothing_but_counts_and_names():
    """构造性排除：归因函数的参数只有 budget、一枚整数与可选的配对话对象——没有通道装正文。"""
    params = list(inspect.signature(context_refusal_attribution).parameters)
    budget = model_tier_budget(ModelTier.ANALYSIS)

    assert set(params) <= {"budget", "prompt_tokens", "pairing"}, params
    assert context_refusal_attribution(None, PROMPT_TOKENS) == ""
    assert context_refusal_attribution(budget, None) != ""
    unread = evaluate_context_pairing(declared_window_tokens=4096, runtime_window_tokens=None, declared_max_tokens=1536)
    actionable = evaluate_context_pairing(declared_window_tokens=4096, runtime_window_tokens=8192, declared_max_tokens=1536)
    assert actionable.actionable and not unread.actionable
    assert "配套自检" not in context_refusal_attribution(budget, PROMPT_TOKENS, unread)
    assert "配套自检" in context_refusal_attribution(budget, PROMPT_TOKENS, actionable)


# ==================== 形界：不新开对外出口、不碰码表、不开旋钮、不动缺省 ====================


def _decorator_texts(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (getattr(node, "name", "?"), ast.unparse(dec))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for dec in node.decorator_list
    ]


def _imported_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


def test_the_gate_opens_no_new_public_route():
    """判据④：闸只读数与说话，一条对外路由都不新开——对外出口归在册那几枚，本单不加。"""
    for path in TOUCHED:
        offenders = [
            (name, text)
            for name, text in _decorator_texts(path)
            if text.startswith("app.") or text.startswith("router.") or "APIRouter" in text
        ]
        assert not offenders, f"{path.name}: 闸开了一枚对外路由 {offenders}"
    for path in (REPO / "app" / "common" / "model_config.py", REPO / "app" / "agents" / "contracts.py"):
        assert not any("fastapi" in name for name in _imported_names(path)), path


def test_the_verdicts_are_not_public_error_codes():
    """四枚判读词不是对外码：`context_limit_exceeded` 的语义原样留着，本单一格没动。"""
    from typing import get_args

    codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    verdicts = {PAIRING_PAIRED, PAIRING_ENV_ABOVE_RUNTIME, PAIRING_RUNTIME_ABOVE_ENV, PAIRING_RUNTIME_UNREAD}

    assert CONTEXT_LIMIT_CODE in codes
    assert not (verdicts & codes), "判读词被写进对外码表：那要走契约与词表另立单,不在本单写域"
    for verdict in sorted(verdicts):
        with pytest.raises(Exception):
            ErrorEnvelope(code=verdict, message="not a public code")
    assert ErrorEnvelope(code=CONTEXT_LIMIT_CODE, message="too large").code == CONTEXT_LIMIT_CODE


def test_the_gate_mints_no_new_knob():
    """本单不许开旋钮：R535 那几枚函数里一次 ``getenv`` 都不许出现，TTL 也是常数。"""
    for fn in (
        model_config.check_context_pairing,
        model_config.observe_runtime_context_window,
        model_config.runtime_context_window_state,
        model_config.record_runtime_context_window,
        model_config.runtime_window_from_ps_payload,
        model_config.runtime_window_from_refusal,
    ):
        source = inspect.getsource(fn)
        assert "getenv" not in source, f"{fn.__name__}: 新开了一枚旋钮"
    assert isinstance(model_config.RUNTIME_WINDOW_TTL_SECONDS, float)
    assert model_config.RUNTIME_WINDOW_PROBE_SUFFIX == "/api/ps"
    assert model_config.RUNTIME_WINDOW_TTL_SECONDS > 0


def test_the_shipped_defaults_are_untouched():
    """一枚缺省值都没改（调参数属业主侧）：三枚在册赋值行原样在 `.env.example` 上。"""
    from app.common.model_budget import DEFAULT_MIN_ANSWER_TOKENS

    env = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in (
        "MODEL_CONTEXT_TOKENS=4096",
        "MODEL_MIN_ANSWER_TOKENS=1536",
        "MODEL_TIER_ANALYSIS_MAX_TOKENS=1536",
    ):
        assert line in env, line
    assert DEFAULT_CONTEXT_TOKENS == 4096 and DEFAULT_MIN_ANSWER_TOKENS == 1536
    plan = window_plan(ModelTier.ANALYSIS)
    assert (plan.context_limit_tokens, plan.declared_max_tokens, plan.min_answer_tokens) == (4096, 1536, 1536)


def test_the_prompt_ruler_is_measured_here_and_actually_overflows():
    """本件的尺子当场量：2813 枚字 + 每枚消息 4 枚 = 2817 槽，而守卫只留 2560。"""
    plan = window_plan(ModelTier.ANALYSIS)

    assert PROMPT_TOKENS == len(OVERSIZED_PROMPT) + 4, PROMPT_TOKENS
    assert PROMPT_TOKENS == estimate_prompt_tokens([HumanMessage(content=OVERSIZED_PROMPT)])
    assert plan.prompt_room_tokens == 2560
    assert PROMPT_TOKENS > plan.prompt_room_tokens > 0
    assert model_tier_budget(ModelTier.ANALYSIS).required_context_tokens(PROMPT_TOKENS) > plan.context_limit_tokens
