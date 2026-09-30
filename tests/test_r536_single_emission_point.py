# -*- coding: utf-8 -*-
"""R536 判据② —— 发射点唯一：产品道的 ``retrieval.completed`` 只许有一枚发射手、一处调用点。

这枚文件整篇是静态的（AST + 逐行正则），不导入 ``app.**``、不起服务、不打模型：判据② 要的是
「再长出第二枚发射点就当场红」，那是形状问题，不是运行时问题。同一批尺子被
``tests/test_r536_counter_evidence_teeth.py`` 拿去在**影子副本**上跑刀，刀口与牙共用同一份实现，
不存在「刀有牙、钉没牙」。

🔴 字面量正则刻意与在册那把尺同形（``scripts/r483_empty_tables_triage.py::event_emitters``
按 ``event_type="<名字>"`` 找发射点），所以本模块把事件名写成字面量而不是常量：藏进常量等于
把新发射点从在册台账的视野里抹掉，那是洗绿的一种写法。

在册允许的两枚发射点：
  · ``app/rag/retrieval_pipeline.py`` —— 本单落的产品道那一枚（唯一实现 + 唯一调用点）；
  · ``app/rag/debug.py`` —— RAG 调试面那枚遗留发射器，不在本单写域，🔴 也不许被算成产品道读数
    （口径出处 ``docs/testing/r483-empty-tables-2026-09-29.md:104``）。
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PIPELINE = "app/rag/retrieval_pipeline.py"
DEBUG_LEGACY = "app/rag/debug.py"
CHAT = "app/api/v1/chat.py"
CONSUMER = "app/trace/projections.py"

EMITTER = "record_retrieval_completed"
ARM = "arm_retrieval_trace"
RESET = "reset_retrieval_trace"

#: 允许的发射手与其文件：文件名 → 该文件里 ``event_type="retrieval.completed"`` 的行数。
ALLOWED_EMITTERS = {PIPELINE: 1, DEBUG_LEGACY: 1}
#: 消费方那枚文件里 ``retrieval.completed`` 这个字眼的在册处数（文档串 + 字面相等判定）。
CONSUMER_OCCURRENCES = 2
#: 唯一的产品道调用点：(文件, 包着它的函数)。
ALLOWED_CALL_SITES = {(PIPELINE, "search_for_principal")}
#: 问答两腿各挂一枚身份、各交回一枚 token。
EXPECTED_ARMS = 2

EVENT_TYPE_RE = re.compile(r"""event_type\s*=\s*["']retrieval\.completed["']""")
NAME_RE = re.compile(r"\bretrieval\.completed\b")
CALL_RE = re.compile(r"\b(" + EMITTER + r"|" + ARM + r"|" + RESET + r")\s*\(")


def sources(root: Path) -> dict[str, str]:
    """``app/**`` 的每一枚 .py：路径用 POSIX 形状，读文本按盘上字节（CRLF 归一成 LF）。"""
    base = root / "app"
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        for path in sorted(base.rglob("*.py"))
    }


def _enclosing_functions(tree: ast.AST) -> dict[int, list[str]]:
    """每个节点 id → 从外到内的函数名链（模块级 = 空链）。"""
    chain: dict[int, list[str]] = {}

    def walk(node, ancestors):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_chain = ancestors + [child.name]
                chain[id(child)] = child_chain
            else:
                child_chain = ancestors
            chain[id(child)] = child_chain
            walk(child, child_chain)

    walk(tree, [])
    return chain


def _calls(texts: dict[str, str], name: str) -> list[tuple[str, tuple[str, ...]]]:
    """每一处 ``name(...)``：交回 (文件, 函数链)。AST 逐文件解析，解析不动就当场报错。"""
    found = []
    for rel, text in sorted(texts.items()):
        tree = ast.parse(text)
        chains = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name) and function.id == name:
                    found.append((rel, tuple(chains.get(id(function), ()))))
    return found


def emitter_literals(texts: dict[str, str]) -> dict[str, int]:
    return {
        rel: sum(1 for line in text.split("\n") if EVENT_TYPE_RE.search(line))
        for rel, text in sorted(texts.items())
        if any(EVENT_TYPE_RE.search(line) for line in text.split("\n"))
    }


def consumer_word_count(texts: dict[str, str]) -> int:
    return sum(1 for line in texts[CONSUMER].split("\n") if NAME_RE.search(line))


def judge(root: Path = REPO) -> list[str]:
    """五格判据合一，交回违规清单（空清单 = 绿）。牙齿与刀共用这一枚函数。"""
    texts = sources(root)
    problems = []

    defined = [
        (rel, node.name)
        for rel, text in sorted(texts.items())
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef) and node.name == EMITTER
    ]
    if len(defined) != 1 or defined[0][0] != PIPELINE:
        problems.append(f"发射实现应当只有一枚、且住在 {PIPELINE}：现扫 {defined}")

    call_sites = {(rel, chain[-1]) for rel, chain in _calls(texts, EMITTER)}
    if call_sites != ALLOWED_CALL_SITES:
        problems.append(
            "发射调用点漂了：允许 " + repr(sorted(ALLOWED_CALL_SITES)) + "，现扫 " + repr(sorted(call_sites))
        )

    literals = emitter_literals(texts)
    if literals != ALLOWED_EMITTERS:
        problems.append(
            "发射手不止在册那两枚（本单那一枚 + 调试面遗留那一枚）："
            + repr(literals) + "；🔴 调试面不许被算成产品道"
        )

    if consumer_word_count(texts) != CONSUMER_OCCURRENCES:
        problems.append(
            f"{CONSUMER} 里 retrieval.completed 的处数不是 {CONSUMER_OCCURRENCES}："
            f"消费方被改动了，本单的入参对照失去参照物"
        )

    chat_texts = {rel: texts[rel] for rel in (CHAT,) if rel in texts}
    arms = _calls(chat_texts, ARM)
    resets = _calls(chat_texts, RESET)
    if len(arms) != EXPECTED_ARMS or len(resets) != EXPECTED_ARMS:
        problems.append(f"chat.py 的挂/交回对数不是 {EXPECTED_ARMS}/{EXPECTED_ARMS}：{len(arms)}/{len(resets)}")
    for site in _calls(chat_texts, EMITTER):
        problems.append(f"chat.py 里长出了第二枚发射调用点：{site}")
    if EVENT_TYPE_RE.search(texts[CHAT]):
        problems.append("chat.py 里长出了第二枚发射实现（event_type=\"retrieval.completed\"）")

    for rel, chain in arms:
        if "_run" not in chain:
            problems.append(
                f"{rel} 的身份挂在了 {chain} 里，不在工作线程那一枚 _run 函数体内 ⇒ "
                "loop.run_in_executor 不复制调用方的 contextvar，这一挂等于没挂"
            )
    return problems


# ==================================================================== 逐格判据
def test_the_emission_implementation_is_a_single_function():
    problems = [item for item in judge() if "发射实现" in item]
    assert problems == [], problems


def test_the_product_call_site_is_exactly_one():
    call_sites = {(rel, chain[-1]) for rel, chain in _calls(sources(REPO), EMITTER)}
    assert call_sites == ALLOWED_CALL_SITES, sorted(call_sites)


def test_only_the_two_known_emitters_remain_in_the_product_tree():
    assert emitter_literals(sources(REPO)) == ALLOWED_EMITTERS


def test_the_consumer_is_not_a_second_emitter():
    """消费方（在册、本单禁入）那两枚字眼一处不多一处不少：它读事件，不发事件。"""
    assert consumer_word_count(sources(REPO)) == CONSUMER_OCCURRENCES


def test_chat_py_arms_both_lanes_and_holds_no_emitter():
    problems = [
        item
        for item in judge()
        if "chat.py" in item or "挂在了" in item
    ]
    assert problems == [], problems


def test_arms_live_inside_the_worker_thread_bodies():
    """两枚挂点必须都在 ``_run`` 函数体内：那是 chat.py 拥有的最深一枚工作线程帧。"""
    chains = [chain for _rel, chain in _calls({CHAT: sources(REPO)[CHAT]}, ARM)]
    assert len(chains) == EXPECTED_ARMS, chains
    for chain in chains:
        assert "_run" in chain, chain
        assert "ask" in chain or "approve" in chain, chain


def test_the_aggregate_judge_is_green_on_the_registered_tree():
    assert judge() == []
