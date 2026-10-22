"""R220 - top-k 里有、进 prompt 没有：逐题损失表与逐格归因（只取证，不改产品代码）.

离线、零模型调用、零容器、对仓内跟踪件零写入。

🔴 本件不 import ``app.rag.retrieval_pipeline``：那个模块在 import 期就构造
``ModelHandler()``，裸跑一次等于对宿主模型端口发一次连接（那件事只有测试里的 R56 端口
闸门接得住）。所以装箱用到的数一律按真源读：

  * 容量      ``app.agents.contracts.ModelBudget.input_budget_tokens``（现场算，不抄 2560）
  * 两枚预留  ``app/rag/retrieval_pipeline.py`` 的模块级字面量（AST 读）
  * top-k     ``app/agents/tools.py`` 里 ``search_docs`` 调用点上的 ``top_k``（AST 读）。R112 起这枚
              值不再是 ``f(top_k=5)`` 的关键字实参，而是先落进 ``retrieval_kwargs`` 字典字面量、再以
              ``**retrieval_kwargs`` 展开进 ``search_for_principal(...)``。两种形状本件都认，读数里
              带出命中的是哪一种。
  * 召回深度  ``RetrievalPipeline.search`` 里 ``ex.submit(self.semantic.search, q, 8, where)``
              的那个 8（AST 按调用点读，不看签名）

输入（全是已并树的只读原件，跑一次记一次 sha256）：
  docs/testing/r59b-recall-comparison-2026-09-24.json  每题向量腿 top-5（Chroma/PG 同一批）
  docs/testing/answers-run6.jsonl                      每题证据袋 = 模型真读到过的那几条
  tests/fixtures/business_evaluation_100.jsonl         题面 / 族 / must_contain
  documents/*                                          按生产 splitter 重切分，补块长

口径边界（别让读数越界）：
  * 这里的 top-k 是「纯向量腿、原题 query、k=5、无 where 下推」的名次，不是产品链路最终
    那 5 条。两个集合的差同时混着名次侧与装箱侧两件事，本件把它拆成互斥的三桶：
    ``lost_by_room``（房不够）/ ``lost_before_packing``（装得进房却没进那一发候选集）/
    ``lost_unattributed``（块长取不到，判不了）。三桶并起来正好等于损失行。
  * 「进 prompt」的凭据是证据袋里的 ``source_id``：R112 复验第 2 条把证据袋收成了「袋里
    只许有真送出去的那几条」（``tests/test_r112_prompt_packing.py`` 钉着），所以它能当进场
    凭据。它不记 query，那正是 ⓪ 那一格量不到的原因。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.agents.contracts import ModelTier  # noqa: E402  纯契约，import 期不开 socket
from app.common.model_budget import (  # noqa: E402  装箱与窗口守卫同一把尺
    estimate_text_tokens,
    model_tier_budget,
)
from app.quality.eval import _is_correct  # noqa: E402  与客户报告同一个判分函数

RECALL = REPO / "docs" / "testing" / "r59b-recall-comparison-2026-09-24.json"
ANSWERS = REPO / "docs" / "testing" / "answers-run6.jsonl"
FIXTURES = REPO / "tests" / "fixtures" / "business_evaluation_100.jsonl"
PIPELINE_SRC = REPO / "app" / "rag" / "retrieval_pipeline.py"
RETRIEVER_SRC = REPO / "app" / "rag" / "retriever.py"
TOOLS_SRC = REPO / "app" / "agents" / "tools.py"
DOCUMENTS = REPO / "documents"
READONLY_INPUTS = (RECALL, ANSWERS, FIXTURES)
FIXTURE_SOURCE = "business_evaluation_100.jsonl"
#: 去重键长度：``_deduplicate`` 与 ``rrf_fusion`` 都按 content[:120] 认人，本件跟着量。
DEDUPE_KEY_CHARS = 120


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_literal(path: Path, name: str):
    """读一枚模块级常量字面量；读不到就地硬失败，不给手抄留口子。"""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise LookupError(f"{name} 不在 {path.name} 的模块级字面量里：真源换了形状，本件要跟着改")


def _function_node(path: Path, func_name: str, class_name: str | None = None):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if class_name:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for inner in ast.walk(node):
                    if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)) and inner.name == func_name:
                        return inner
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    raise LookupError(f"{path.name} 里找不到 {class_name or ''}.{func_name}：调用点换了名字，本件要跟着改")


def _dotted(func_node) -> str:
    parts = []
    node = func_node
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _splatted_names(func_node) -> set:
    """函数体里以 ``**name`` 展开进某枚调用的变量名：用来证明字典值确实够得着调用点。"""
    names = set()
    for call in ast.walk(func_node):
        if isinstance(call, ast.Call):
            for kw in call.keywords:
                if kw.arg is None and isinstance(kw.value, ast.Name):
                    names.add(kw.value.id)
    return names


def call_keyword_int(
    path: Path, func_name: str, keyword: str, class_name: str | None = None
) -> tuple[int, str]:
    """按调用点读一枚整数，返回 ``(值, 命中的形状)``。认两种形状：

      * ``f(query, top_k=5)``              -> ``"call_keyword"``
      * ``d = {"top_k": 5}`` 再 ``f(**d)``  -> ``"dict_splat"``（R112 之后 ``tools.py`` 的形状）

    🔴 字典那一支要求 ``d`` 真的以 ``**d`` 展开进同一函数体里的调用，否则读的是死变量。
    两种形状都不在就硬失败——本件不许退化成手抄一枚 5。
    """
    node = _function_node(path, func_name, class_name)
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            for kw in call.keywords:
                if kw.arg == keyword:
                    return int(ast.literal_eval(kw.value)), "call_keyword"
    spread = _splatted_names(node)
    for assign in ast.walk(node):
        if not isinstance(assign, ast.Assign) or not isinstance(assign.value, ast.Dict):
            continue
        targets = {t.id for t in assign.targets if isinstance(t, ast.Name)}
        if not (targets & spread):
            continue
        for key, value in zip(assign.value.keys, assign.value.values):
            if isinstance(key, ast.Constant) and key.value == keyword:
                return int(ast.literal_eval(value)), "dict_splat"
    raise LookupError(
        f"{func_name} 的调用点里既没有 {keyword}= 关键字实参，也没有展开进调用的 {keyword} 字典键"
        f"（{path.name}）：真源换了形状，本件要跟着改"
    )


def call_positional_int(
    path: Path, func_name: str, callee_tail: str, position: int, class_name: str | None = None
) -> tuple[int, str]:
    """按调用点读一枚位置实参，返回 ``(值, 命中的形状)``。认两种形状：

      * ``self.semantic.search(q, 8, where)``    -> 第 1 号位就是那枚 8（``"direct_call"``）
      * ``ex.submit(self.semantic.search, q, 8, where)``
        被调方降成 0 号实参，深度挪到第 ``position + 1`` 号位（``"submitted_callee"``）

    🔴 ``retrieval_pipeline.py:891`` 用的是后一种：召回是丢进线程池的，被调方以**一等对象**
    的身份出现在 ``ex.submit`` 的实参表里，不是 ``Call.func``。本件原来只认前一种形状，
    于是这一枚数从来没被读到过（``git log -S`` 查过：这一行自 ``88b9430`` 起没换过形状，
    不是漂移，是出生即读不到）。两种都不在就硬失败。
    """
    node = _function_node(path, func_name, class_name)
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if _dotted(call.func).endswith(callee_tail) and len(call.args) > position:
            return int(ast.literal_eval(call.args[position])), "direct_call"
        if call.args and _dotted(call.args[0]).endswith(callee_tail) and len(call.args) > position + 1:
            return int(ast.literal_eval(call.args[position + 1])), "submitted_callee"
    raise LookupError(
        f"{func_name} 里既找不到 {callee_tail} 的直接调用，也找不到把它当一等对象提交的调用"
        f"（{path.name}）：真源换了形状，本件要跟着改"
    )


def splitter_kwargs() -> dict:
    """生产分块参数：从构造点上读，不手抄 500/50。"""
    for node in ast.walk(ast.parse(RETRIEVER_SRC.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "RecursiveCharacterTextSplitter":
            return {kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}
    raise LookupError("app/rag/retriever.py 里找不到 RecursiveCharacterTextSplitter 的构造点")


def pack_numbers() -> dict:
    """装箱那一发的全部数，逐枚按真源取。"""
    budget = model_tier_budget(ModelTier.ANALYSIS)
    shell = int(module_literal(PIPELINE_SRC, "CONTEXT_SHELL_RESERVE_TOKENS"))
    history = int(module_literal(PIPELINE_SRC, "CONTEXT_HISTORY_RESERVE_TOKENS"))
    capacity = int(budget.input_budget_tokens)
    top_k, top_k_shape = call_keyword_int(TOOLS_SRC, "search_docs", "top_k")
    recall_depth, recall_depth_shape = call_positional_int(
        PIPELINE_SRC, "search", "semantic.search", 1, class_name="RetrievalPipeline"
    )
    return {
        "tier": str(module_literal(PIPELINE_SRC, "CONTEXT_PACK_TIER")),
        "context_limit_tokens": int(budget.context_limit_tokens),
        "tier_max_tokens": int(budget.max_tokens),
        "capacity": capacity,
        "shell_reserve": shell,
        "history_reserve": history,
        "reserve_total": shell + history,
        "room": max(0, capacity - shell - history),
        "content_chars": int(module_literal(PIPELINE_SRC, "DOC_HIT_CONTENT_CHARS")),
        "top_k": top_k,
        "top_k_shape": top_k_shape,
        "recall_queries": int(module_literal(PIPELINE_SRC, "MAX_RECALL_QUERIES")),
        "recall_depth": recall_depth,
        "recall_depth_shape": recall_depth_shape,
    }


def pack_prefix(unit_texts, room_tokens, token_of):
    """按名次装箱：``retrieval_pipeline.pack_prefix_by_rank`` 同一算法的本地副本。

    🔴 等价性不是嘴上说的：``tests/test_r220_packing_loss.py`` 拿产品函数在同一批输入上
    逐向量对判，这一副本一漂就红。不直接 import 的理由见模块抬头。
    """
    units = list(unit_texts)
    room = max(0, int(room_tokens))
    kept: list = []
    used = 0
    for unit in units:
        cost = int(token_of(unit))
        if used + cost > room:
            break
        kept.append(unit)
        used += cost
    return kept, units[len(kept):], used


def split_vector_id(vector_id: str) -> tuple[str, int | None]:
    filename, _, index = str(vector_id).rpartition("_")
    return filename, int(index) if index.isdigit() else None


def evidence_ids(row: dict) -> list[str]:
    """证据袋 -> 向量库那套 id：``filename.txt#chunk=N`` -> ``filename.txt_N``。"""
    ids = []
    for item in row.get("evidence") or []:
        source = str(item.get("source") or "")
        index = item.get("chunk_index")
        if source and index is not None:
            ids.append(f"{source}_{index}")
    return ids


class Corpus:
    """``documents/`` 的生产重切分：把 ``filename_N`` 翻译回正文，好知道那一块值多少枚。"""

    def __init__(self):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self.splitter = RecursiveCharacterTextSplitter(**splitter_kwargs())
        self._by_file: dict[str, list[str] | None] = {}
        self.missing_files: set[str] = set()

    def chunks(self, filename: str):
        if filename not in self._by_file:
            path = DOCUMENTS / filename
            if path.exists():
                from app.rag.loader import load_document

                self._by_file[filename] = self.splitter.split_text(load_document(str(path)))
            else:
                self.missing_files.add(filename)
                self._by_file[filename] = None
        return self._by_file[filename]

    def text(self, vector_id: str):
        filename, index = split_vector_id(vector_id)
        chunks = self.chunks(filename)
        if chunks is None or index is None or index >= len(chunks):
            return None
        return chunks[index]

    def dedupe_key_hits(self, vector_id: str) -> int:
        """这块的去重键（content[:120]）在全库重切分里与几块相同：1 = 只有它自己。"""
        text = self.text(vector_id)
        if text is None:
            return -1
        key = text[:DEDUPE_KEY_CHARS]
        hits = 0
        for filename in list(self._by_file):
            for chunk in self.chunks(filename) or []:
                if chunk[:DEDUPE_KEY_CHARS] == key:
                    hits += 1
        return hits

    def load_files(self, filenames) -> None:
        for filename in filenames:
            self.chunks(filename)


def load_answers() -> dict[str, dict]:
    rows = {}
    for line in ANSWERS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def load_recall(fixture_source: str = FIXTURE_SOURCE) -> tuple[dict, dict[str, list[str]]]:
    """向量腿 top-k。同一题号在 30 题夹具里还有一份，这里只取 105 题那一份。"""
    doc = json.loads(RECALL.read_text(encoding="utf-8"))
    top5: dict[str, list[str]] = {}
    for question in doc["questions"]:
        if question.get("source") == fixture_source:
            top5[question["id"]] = list(question.get("chroma_ids") or [])
    return doc, top5


def load_fixtures() -> dict[str, dict]:
    rows = {}
    for line in FIXTURES.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def replay(ranked: list[str], room: int, cost_of) -> dict:
    """反事实复算：名次完全照向量腿那几条走、房按真源给，装箱能送到第几名。

    块长取不到就就地停——从那一行往后判不了，硬猜会把「没量到」说成「不是房的问题」。
    """
    kept: list[str] = []
    used = 0
    dropped_room: list[str] = []
    unattributed: list[str] = []
    for index, vector_id in enumerate(ranked):
        cost = cost_of(vector_id)
        if cost is None:
            unattributed.extend(ranked[index:])
            break
        if used + cost > room:
            dropped_room.extend(ranked[index:])
            break
        kept.append(vector_id)
        used += cost
    return {"kept": kept, "dropped_room": dropped_room, "unattributed": unattributed, "used": used}


def analyze() -> dict:
    numbers = pack_numbers()
    corpus = Corpus()
    recall_doc, top5 = load_recall()
    answers = load_answers()
    fixtures = load_fixtures()
    limit = numbers["content_chars"]
    room = numbers["room"]
    corpus.load_files({split_vector_id(vid)[0] for vids in top5.values() for vid in vids})

    def body(vector_id):
        return corpus.text(vector_id)

    def body_cost(vector_id):
        text = body(vector_id)
        return None if text is None else estimate_text_tokens(text[:limit])

    def unit_cost(vector_id, rank):
        """工具腿真发给模型的那一段（行头 + 正文），比 ⑤ 那把尺贵，两把都量。"""
        text = body(vector_id)
        if text is None:
            return None
        filename, _ = split_vector_id(vector_id)
        return estimate_text_tokens(f"[{rank}] 来源:{filename} 相关度:未评分\n{text[:limit]}")

    seen_elsewhere: Counter = Counter()
    for line_row in answers.values():
        for vector_id in set(evidence_ids(line_row)):
            seen_elsewhere[vector_id] += 1

    rows = []
    for qid in sorted(answers):
        ranked = top5.get(qid) or []
        present = set(evidence_ids(answers[qid]))
        lost = [vector_id for vector_id in ranked if vector_id not in present]
        fit = replay(ranked, room, body_cost)
        by_room = set(fit["dropped_room"])
        kept_set = set(fit["kept"])
        fixture = fixtures.get(qid) or {}
        answer_text = str(answers[qid].get("answer") or "")
        detail = []
        for rank, vector_id in enumerate(ranked, start=1):
            if vector_id in present:
                bucket = "in_prompt"
            elif vector_id in by_room:
                bucket = "lost_by_room"
            elif vector_id in kept_set:
                bucket = "lost_before_packing"
            else:
                bucket = "lost_unattributed"
            detail.append(
                {
                    "rank": rank,
                    "vector_id": vector_id,
                    "chars": (len(body(vector_id)) if body(vector_id) is not None else None),
                    "body_tokens": body_cost(vector_id),
                    "unit_tokens": unit_cost(vector_id, rank),
                    "bucket": bucket,
                    "seen_in_other_prompts": seen_elsewhere.get(vector_id, 0),
                }
            )
        rows.append(
            {
                "id": qid,
                "category": str(fixture.get("category") or "-"),
                "question": str(fixture.get("question") or ""),
                "correct": (_is_correct(fixture, {"answer": answer_text}) if fixture else None),
                "missing_terms": [term for term in (fixture.get("must_contain") or []) if term not in answer_text],
                "top_k": len(ranked),
                "evidence_n": len(present),
                "lost_n": len(lost),
                "lost_ids": lost,
                "lost_by_room_n": len([vid for vid in lost if vid in by_room]),
                "lost_before_packing_n": len([vid for vid in lost if vid in kept_set]),
                "lost_unattributed_n": len([vid for vid in lost if vid not in by_room and vid not in kept_set]),
                "foreign_n": len([vid for vid in present if vid not in set(ranked)]),
                "attribution_partial": bool(fit["dropped_room"] or fit["unattributed"]),
                "top5_body_tokens": sum(cost for cost in (body_cost(vid) for vid in ranked) if cost),
                "top5_unit_tokens": sum(
                    cost for cost in (unit_cost(vid, rank) for rank, vid in enumerate(ranked, 1)) if cost
                ),
                "replay_kept_n": len(fit["kept"]),
                "room": room,
                "detail": detail,
            }
        )
    return {
        "numbers": numbers,
        "rows": rows,
        "meta": recall_doc.get("meta") or {},
        "corpus_missing_files": sorted(corpus.missing_files),
        "seen_elsewhere": seen_elsewhere,
        "corpus": corpus,
    }


def by_category(rows) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    table = []
    for category, group in sorted(groups.items()):
        topk_rows = sum(item["top_k"] for item in group)
        lost_rows = sum(item["lost_n"] for item in group)
        judged = [item["correct"] for item in group if item["correct"] is not None]
        table.append(
            {
                "category": category,
                "questions": len(group),
                "topk_rows": topk_rows,
                "lost_rows": lost_rows,
                "loss_pct": round(100.0 * lost_rows / topk_rows, 1) if topk_rows else 0.0,
                "lost_by_room": sum(item["lost_by_room_n"] for item in group),
                "lost_before_packing": sum(item["lost_before_packing_n"] for item in group),
                "lost_unattributed": sum(item["lost_unattributed_n"] for item in group),
                "foreign_rows": sum(item["foreign_n"] for item in group),
                "partial_questions": sum(1 for item in group if item["attribution_partial"]),
                "correct_pct": (
                    round(100.0 * sum(1 for flag in judged if flag) / len(judged), 1) if judged else None
                ),
            }
        )
    return sorted(table, key=lambda item: (-item["lost_rows"], item["category"]))


def render(result: dict) -> str:
    numbers = result["numbers"]
    rows = result["rows"]
    categories = by_category(rows)
    out: list[str] = ["# R220 · top-k 里有、进 prompt 没有：逐题损失表", ""]
    out += ["## 0. 读数用的数（现场按真源取，一枚都不是抄的）", "", "| 项 | 值 | 真源 |", "|---|---|---|"]
    out += [
        f"| 装箱档 | `{numbers['tier']}` | `CONTEXT_PACK_TIER` |",
        f"| n_ctx | {numbers['context_limit_tokens']} | `MODEL_CONTEXT_TOKENS` -> `context_limit_tokens` |",
        f"| 该档输出上限 | {numbers['tier_max_tokens']} | `TIER_MAX_TOKEN_DEFAULTS[ANALYSIS]` |",
        f"| 容量 input_budget | {numbers['capacity']} | `ModelBudget.input_budget_tokens` |",
        f"| 预留 = 壳 + 历史 | {numbers['shell_reserve']} + {numbers['history_reserve']} = {numbers['reserve_total']} | 两枚实测常数 |",
        f"| **本轮房 room** | **{numbers['room']}** | 与 `context_pack_room()` 同一算式 |",
        f"| 单条正文上限 | {numbers['content_chars']} 字 | `DOC_HIT_CONTENT_CHARS` |",
        f"| 最终 top-k | {numbers['top_k']} | `search_docs` 调用点上的 `top_k`（命中形状 `{numbers['top_k_shape']}`） |",
        f"| 多路 query 槽位 | {numbers['recall_queries']} | `MAX_RECALL_QUERIES` |",
        f"| 单路召回深度 | {numbers['recall_depth']} | `RetrievalPipeline.search` 里 `semantic.search(q, 8, where)`（命中形状 `{numbers['recall_depth_shape']}`） |",
        "",
        "只读原件指纹：",
        "",
    ]
    out += [f"- `{path.name}` = `{sha256(path)[:16]}`" for path in READONLY_INPUTS]
    out += [
        "",
        f"本机 `documents/` 取不到正文的文件（run6 证据袋引用过、本机没有）：{len(result['corpus_missing_files'])} 份"
        f" -> {result['corpus_missing_files'] or '无'}。这些块只进 `lost_unattributed` 桶，"
        "不许被算进「房不够」或「名次侧」任何一边。",
        "",
        "## 1. 族表（这张表决定下一刀的优先级）",
        "",
        "| 族 | 题 | top-k 行 | 损失行 | 损失率 | 房不够 | 名次侧 | 判不了 | 袋中外来行 | 复算不干净题 | run6 判对率 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in categories:
        out.append(
            "| {category} | {questions} | {topk_rows} | {lost_rows} | {loss_pct}% | {lost_by_room} | "
            "{lost_before_packing} | {lost_unattributed} | {foreign_rows} | {partial_questions} | {correct} |".format(
                correct="-" if item["correct_pct"] is None else f"{item['correct_pct']}%", **item
            )
        )
    topk_rows = sum(item["topk_rows"] for item in categories)
    lost_rows = sum(item["lost_rows"] for item in categories)
    out += [
        "",
        f"全表：{len(rows)} 题 / {topk_rows} 行 top-k / {lost_rows} 行损失 = "
        f"{round(100.0 * lost_rows / topk_rows, 1) if topk_rows else 0}%。",
        "三桶互斥：`房不够` = 名次照向量腿走、房按真源给，仍然装不进；`名次侧` = 它装得进房却压根没进"
        "那一发的候选集；`判不了` = 块长取不到。",
        "",
        "## 2. 逐题表（只列有损失的题，按损失行数倒序）",
        "",
        "| 题号 | 族 | run6 判分 | top-k | 进场 | 损失 | 房不够 | 名次侧 | 判不了 | 外来行 | top-5 枚数 / 房 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda item: (-item["lost_n"], item["id"])):
        if not row["lost_n"]:
            continue
        out.append(
            "| `{id}` | {category} | {verdict} | {top_k} | {evidence_n} | {lost_n} | {room_lost} | "
            "{rank_lost} | {unknown} | {foreign_n} | {tokens} / {room} |".format(
                id=row["id"],
                category=row["category"],
                verdict="对" if row["correct"] else ("错" if row["correct"] is not None else "?"),
                top_k=row["top_k"],
                evidence_n=row["evidence_n"],
                lost_n=row["lost_n"],
                room_lost=row["lost_by_room_n"],
                rank_lost=row["lost_before_packing_n"],
                unknown=row["lost_unattributed_n"],
                foreign_n=row["foreign_n"],
                tokens=row["top5_body_tokens"],
                room=row["room"],
            )
        )
    out += ["", f"零损失题：{sum(1 for row in rows if not row['lost_n'])} / {len(rows)}。", ""]
    return "\n".join(out)


def probe(result: dict, qid: str) -> str:
    """单题逐格排除：把「怎么丢的」讲到能复算。"""
    numbers = result["numbers"]
    corpus = result["corpus"]
    row = next((item for item in result["rows"] if item["id"] == qid), None)
    if row is None:
        raise SystemExit(f"题号 {qid} 不在 run6 那 105 题里")
    answers = load_answers()
    evidence_keys = sorted({key for item in answers[qid].get("evidence") or [] for key in item})
    doc_rows = [
        item
        for line_row in answers.values()
        for item in line_row.get("evidence") or []
        if str(item.get("worker")) == "doc"
    ]
    unscored = sum(1 for item in doc_rows if item.get("score") is None)
    target_file = split_vector_id(row["detail"][0]["vector_id"])[0] if row["detail"] else ""
    same_file_prompts = sorted(
        {
            question
            for question, line_row in answers.items()
            if any(vid.startswith(f"{target_file}_") for vid in evidence_ids(line_row))
        }
    )
    lost_rank_side = [item for item in row["detail"] if item["bucket"] == "lost_before_packing"]
    lines = [
        f"## R220 探针 · {qid} 逐格归因",
        "",
        f"- 题面：{row['question']}",
        f"- 族：{row['category']}　run6 判分：{'对' if row['correct'] else '错'}　缺的 must_contain：{row['missing_terms'] or '—'}",
        f"- 向量腿 top-{row['top_k']}：{[item['vector_id'] for item in row['detail']]}",
        f"- 证据袋 {row['evidence_n']} 行；其中不在 top-k 里的外来行 {row['foreign_n']} 行",
        "",
        "| 名次 | 块 | 字数 | 枚（正文 / 含行头） | 落点 | 这块在别的题上进过几次袋 |",
        "|---|---|---|---|---|---|",
    ]
    for item in row["detail"]:
        lines.append(
            f"| {item['rank']} | `{item['vector_id']}` | {item['chars'] if item['chars'] is not None else '未取到'} "
            f"| {item['body_tokens'] if item['body_tokens'] is not None else '-'} / "
            f"{item['unit_tokens'] if item['unit_tokens'] is not None else '-'} | {item['bucket']} "
            f"| {item['seen_in_other_prompts']} |"
        )
    collisions = {item["vector_id"]: corpus.dedupe_key_hits(item["vector_id"]) for item in lost_rank_side}
    lines += [
        "",
        "### 逐格：损失那几行到底是在哪一格被挤掉的",
        "",
        "| 格 | 这一格会不会吃掉它 | 结论 | 凭据（现场算的，不是引述） |",
        "|---|---|---|---|",
        f"| ⓪ 工具 query | doc 腿那一发的 query 是模型自己填的串，不是题面 | 🔴 **未量到，不能排除** | "
        f"`answers-run6.jsonl` 证据行的字段是 {evidence_keys}，里面没有 `query` |",
        f"| ①/①' 改写与词表扩展 | 只改候选构成，不改原题那一发 | 🟡 成立（它把别的块塞到前面） | "
        f"`all_queries = [原题] + rewrites + sub_questions + 扩展`，槽位上限 {numbers['recall_queries']}，原题恒在 0 号位 |",
        f"| ② 单路召回深度 | 每路只取前 {numbers['recall_depth']} 条 | 🟢 排除 | 目标块在向量腿 top-{row['top_k']} 里，"
        f"{numbers['top_k']} ⊆ {numbers['recall_depth']} |",
        f"| 权限 / 部门过滤 | `_retain_permitted` 与 where 下推 | 🟢 排除（本题这份文件） | "
        f"同一份 `{target_file}` 在 {len(same_file_prompts)} 道题的证据袋里进过场 |",
        f"| 去重 `_deduplicate` | 按 content[:{DEDUPE_KEY_CHARS}] 认人 | 🟢 排除 | "
        f"这几块的去重键在全库重切分里命中枚数 = {collisions}（1 = 只有它自己） |",
        f"| ③ RRF 融合名次 | 融合前先去重，名次 = 拼接表里的首次出现位 | 🔴 成立 | "
        f"`retrieval_pipeline.py` 的 `search()`：`_deduplicate` 在 `rrf_fusion` 之前，而拼接顺序取自 `as_completed`（线程完成顺序，非确定） |",
        f"| ④ 名次截断 | `top_k={numbers['top_k']}` 只留 5 条 | 🔴 **成立，且在装箱之前** | run6 全部 {len(doc_rows)} 枚 doc 证据里 "
        f"`score=null` 有 {unscored} 枚 => Cross-Encoder 未打分，`rerank()` 走 `docs[:top_k]` 兜底 |",
        f"| ⑤ 装箱房 | room={numbers['room']} 枚 | {'🔴 参与本题损失' if row['lost_by_room_n'] else '🟢 不构成约束'} | "
        f"top-{row['top_k']} 正文合计 {row['top5_body_tokens']} 枚（含行头 {row['top5_unit_tokens']} 枚），"
        f"装箱复算能送 {row['replay_kept_n']} 条、剩 {numbers['room'] - row['top5_body_tokens']} 枚空房，房吃掉 {row['lost_by_room_n']} 行 |",
        "",
        f"合桶读数：损失 {row['lost_n']} 行 = 名次侧 {row['lost_before_packing_n']} 行 + 房不够 "
        f"{row['lost_by_room_n']} 行 + 判不了 {row['lost_unattributed_n']} 行。",
        "",
        "名次侧那一桶里，逐块点名："
        + "；".join(f"`{item['vector_id']}`（第 {item['rank']} 名，{item['body_tokens']} 枚，"
                    f"在别的题上进过 {item['seen_in_other_prompts']} 次袋）" for item in lost_rank_side),
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R220 装箱损失取证（离线 / 零模型 / 零容器 / 零写入）")
    parser.add_argument("--question-id", help="额外交付这一题的逐格归因")
    parser.add_argument("--json", action="store_true", help="输出机器可读的全量结果")
    parser.add_argument("--out", help="写到这个路径（默认只打 stdout，不碰仓内跟踪件）")
    args = parser.parse_args(argv)
    result = analyze()
    if args.json:
        payload = {key: result[key] for key in ("numbers", "rows", "corpus_missing_files")}
        for row in payload["rows"]:
            row.pop("detail", None)
        text = json.dumps(payload, ensure_ascii=False, indent=1)
    else:
        text = render(result)
        if args.question_id:
            text += "\n\n" + probe(result, args.question_id)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
