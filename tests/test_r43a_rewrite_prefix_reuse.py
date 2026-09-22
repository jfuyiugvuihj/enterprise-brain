# -*- coding: utf-8 -*-
"""R43a 判据②③ · 改写 prompt 的可复用前缀（固定指令在前、可变内容置于末尾）。

跟进单 §81 三第 2/3 条：``REWRITE_PROMPT`` 今天把 ``{question}`` 夹在两段固定指令**中间**，
两次改写之间字节相同的只剩最前面那一句，服务端能复用的前缀短到没有意义。本件钉三件事：

1. **形状**：问题之后一个字都不许有，前缀之外一个字都不许变；
2. **字节级稳定**：同角色、同档连发两发（乃至八发），前缀 sha256 逐位相同——时间戳、
   随机序、uuid、字典序漏网统统堵在门外；
3. **契约没动**：JSON 那行仍是一字未改的 ``{{ }}`` 转义形状，3 枚 rewrites / 2-3 枚
   sub_questions 的骨架照旧，且本常量仍是一枚单独的字符串字面量
   （``scripts/perf_probe_rounds.py`` / ``scripts/perf_probe_prodpath.py`` 按 AST 取字面量）。

🔴 本件只钉形状，不宣称"前缀缓存已生效"：省了多少要等跑分窗真机读数，本机模型端口
此刻正被三枚在途 Agent 抢。全程离线，不起服务、不连库、不打模型。
"""
import ast
import hashlib
import inspect
import json
import os.path
import re

import pytest

from app.rag import retrieval_pipeline
from app.rag.retrieval_pipeline import REWRITE_PROMPT, QueryRewriter

TIER_ENV = retrieval_pipeline.TIER_ENV
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_SRC = os.path.join(REPO, "app", "rag", "retrieval_pipeline.py")

#: 两枚长度接近、内容互不相干的问题：前缀相同这件事必须与问题内容无关。
Q_A = "员工出差住宿费的报销上限是多少"
Q_B = "今年各门店营收排名前三是谁"

#: 判据②保护的那枚 JSON 契约（含 ``{{ }}`` 转义），一字不许动。
CONTRACT_LINE = (
    '{{"rewrites":["改写1","改写2","改写3"],'
    '"sub_questions":["子问题1","子问题2","子问题3"]}}'
)

#: 前缀里出现即算泄漏的东西：时钟、uuid、unix 时间戳（10-13 位连排数字）。
CLOCK_PATTERNS = (
    r"\d{4}-\d{2}-\d{2}",
    r"\d{2}:\d{2}:\d{2}",
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}",
    r"\b\d{10,13}\b",
)

#: 身份/权限词。判据的硬门：可复用前缀一旦带上身份，跨用户命中就是越权面。
IDENTITY_TOKENS = (
    "principal",
    "department",
    "dept",
    "user_id",
    "userid",
    "owner",
    "tenant",
    "scope_reason",
    "权限",
    "部门",
    "角色",
)

#: 渲染这一次改写的函数体里，这些符号一旦露面就说明前缀开始被运行时的东西污染。
VOLATILE_SYMBOLS = {"datetime", "time", "random", "shuffle", "sample", "uuid", "sorted", "set"}


TIER_FULL_DEFAULT = retrieval_pipeline.TIER_FULL
#: 模板里 ``{question}`` 之前的那一段，就是"除问题之外的全部字节"。
FIXED_HEAD = REWRITE_PROMPT.split("{question}")[0].format(question="")


class _StubModel:
    """记录每一次 chat 报文的桩模型：真实推理一次都不该发生。"""

    def __init__(self):
        self.calls = []

    def chat(self, messages=None, source=None, stream=True, **kwargs):
        self.calls.append({"messages": messages, "source": source, "stream": stream})
        return json.dumps(
            {
                "rewrites": ["改写甲", "改写乙", "改写丙"],
                "sub_questions": ["子问题一", "子问题二"],
            },
            ensure_ascii=False,
        )


def _prompts(monkeypatch, questions, tier=TIER_FULL_DEFAULT):
    """从**产品路径**取渲染结果：走真 ``QueryRewriter.rewrite``，不自己拼模板。"""
    monkeypatch.setenv(TIER_ENV, tier)
    stub = _StubModel()
    monkeypatch.setattr(retrieval_pipeline, "model", stub)
    for question in questions:
        QueryRewriter.rewrite(question)
    return [call["messages"][0]["content"] for call in stub.calls]




# ==================== 判据②：可变内容置于末尾 ====================


def test_the_question_is_the_tail_of_the_prompt(monkeypatch):
    """问题之后一个字都不许留：留一个字节，可复用前缀就少一截。"""
    prompt_a, prompt_b = _prompts(monkeypatch, [Q_A, Q_B])

    assert prompt_a.endswith(Q_A), prompt_a[-40:]
    assert prompt_b.endswith(Q_B), prompt_b[-40:]
    #: 问题字面只许出现在末尾一次——夹回指令中间就露馅。
    assert prompt_a.count(Q_A) == 1
    assert Q_A not in prompt_a[: -len(Q_A)]


def test_the_fixed_instructions_come_first_and_the_prefix_is_most_of_the_prompt():
    """固定指令在前：可变部分只占整段的一小截（改前那枚形状远不到这个数）。"""
    head = REWRITE_PROMPT.split("{question}")[0]
    tail = REWRITE_PROMPT.split("{question}")[1]

    assert head.endswith("用户问题: "), "问题必须是最后一段指令的宾语，而不是夹在中间"
    assert tail.strip() == "", "🔴 可变内容之后一个字都不许有"
    prompt = REWRITE_PROMPT.format(question=Q_A)
    share = len(FIXED_HEAD.encode("utf-8")) / len(prompt.encode("utf-8"))
    assert share >= 0.8, f"可复用前缀只占 {share:.2f}：说明还有固定指令掉在后面"


# ==================== 判据③：同角色同档连发两发，前缀字节级相同 ====================


def test_two_rounds_share_a_byte_identical_reusable_prefix(monkeypatch):
    prompt_a, prompt_b = _prompts(monkeypatch, [Q_A, Q_B])

    assert prompt_a != prompt_b, "两发内容相同就不是在比前缀"
    prefix_a = prompt_a[: len(prompt_a) - len(Q_A)]
    prefix_b = prompt_b[: len(prompt_b) - len(Q_B)]

    assert prefix_a.encode("utf-8") == prefix_b.encode("utf-8"), "字节级相同，不是逐字符近似"
    assert hashlib.sha256(prefix_a.encode("utf-8")).hexdigest() == hashlib.sha256(
        prefix_b.encode("utf-8")
    ).hexdigest()
    #: 公共前缀必须一路走到问题的第一枚字节，中途不许先分岔。
    assert os.path.commonprefix([prompt_a, prompt_b]) == prefix_a
    #: 而且它恰好等于模板里 {question} 之前那一段（含 ``{{ }}`` 还原后的 JSON 行）。
    assert prefix_a == FIXED_HEAD
    #: 前缀里不许藏着问题字面。
    assert Q_A not in prefix_a and Q_B not in prefix_a


def test_the_prefix_is_stable_across_repeated_rounds_and_across_tiers(monkeypatch):
    """同档连发八发、以及跨档，都得是同一枚前缀：档位与重复都不许写进前缀。"""
    repeats = _prompts(monkeypatch, [Q_A] * 8)
    assert len(set(repeats)) == 1, "同一个问题连发必须逐字节复现"

    heads = {prompt[: len(prompt) - len(Q_A)] for prompt in repeats}
    assert heads == {FIXED_HEAD}

    other_tier = _prompts(monkeypatch, [Q_A], tier=retrieval_pipeline.TIER_ADAPTIVE)[0]
    assert other_tier[: len(other_tier) - len(Q_A)] == FIXED_HEAD


# ==================== 泄漏面：时钟 / uuid / 随机序 / 身份 ====================


def test_the_prefix_carries_no_clock_no_uuid_no_epoch_digits(monkeypatch):
    prompt = _prompts(monkeypatch, [Q_A])[0]
    prefix = prompt[: len(FIXED_HEAD)]

    assert prefix == FIXED_HEAD
    for pattern in CLOCK_PATTERNS:
        assert not re.search(pattern, prefix), f"前缀里出现了 {pattern}：可复用性当场作废"


def test_the_rendering_function_reaches_for_no_clock_or_shuffle():
    """渲染这一步不许去摸时钟、随机与无序容器——那是"看起来稳定"的四条后门。"""
    names = set(QueryRewriter.rewrite.__code__.co_names)
    assert not (names & VOLATILE_SYMBOLS), f"改写渲染碰到了 {sorted(names & VOLATILE_SYMBOLS)}"


def test_no_identity_can_reach_the_reusable_prefix(monkeypatch):
    """硬门：前缀带上身份，跨用户命中就是越权面。

    两枚尺：结构上这一发改写请求根本收不到身份（``rewrite(question)`` 只有一枚入参），
    字面上前缀里没有一个身份词。
    """
    parameters = list(inspect.signature(QueryRewriter.rewrite).parameters)
    assert parameters == ["question"], f"改写入口多收了一枚参数：{parameters}"

    prompt = _prompts(monkeypatch, [Q_A])[0]
    lowered = FIXED_HEAD.lower()
    for token in IDENTITY_TOKENS:
        assert token not in lowered, f"前缀里出现了身份词 {token!r}"
    assert prompt.lower().count("scope") == 0, "检索范围属于召回腿，不属于可复用前缀"


def test_the_rewrite_request_is_one_user_message_and_nothing_else(monkeypatch):
    """报文形状也是前缀可复用性的一部分：多一枚 system 消息就多一个可能变的面。"""
    monkeypatch.setenv(TIER_ENV, TIER_FULL_DEFAULT)
    stub = _StubModel()
    monkeypatch.setattr(retrieval_pipeline, "model", stub)

    QueryRewriter.rewrite(Q_A)

    messages = stub.calls[0]["messages"]
    assert messages == [{"role": "user", "content": REWRITE_PROMPT.format(question=Q_A)}]


# ==================== 判据②的护栏：JSON 契约一字未动 ====================


def test_the_json_contract_line_is_verbatim_in_the_template():
    assert CONTRACT_LINE in REWRITE_PROMPT, "3 rewrites / 2-3 sub_questions 那行被改过了"
    assert REWRITE_PROMPT.count(CONTRACT_LINE) == 1


def test_the_template_has_exactly_one_live_placeholder():
    """``{{ }}`` 转义若被改掉，这两句里至少有一句会当场炸。"""
    with pytest.raises(KeyError):
        REWRITE_PROMPT.format()
    assert REWRITE_PROMPT.format(question=Q_A).endswith(Q_A)


def test_the_rendered_contract_still_parses_as_the_promised_shape():
    prompt = REWRITE_PROMPT.format(question=Q_A)
    block = prompt[prompt.index("{") : prompt.index("}") + 1]
    payload = json.loads(block)

    assert list(payload) == ["rewrites", "sub_questions"], payload
    assert len(payload["rewrites"]) == 3, payload
    assert 2 <= len(payload["sub_questions"]) <= 3, payload


def test_the_template_is_still_a_single_string_literal():
    """两枚 perf 探针按 AST 取字面量；拆成运行时拼接就会把探针读成空缺。"""
    with open(PIPELINE_SRC, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(target, "id", "") == "REWRITE_PROMPT" for target in node.targets)
    ]

    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Constant) and isinstance(value.value, str), "必须是一枚字面量"
    assert value.value == REWRITE_PROMPT