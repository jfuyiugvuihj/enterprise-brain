"""r677_hot_set_yield.py · R677 的让路驱动件（离线，只驱动热集那一层的服务判定）

一句话：同一份代码、同一台机器，把热集那两条腿各跑一遍——预算装得下语料时由热集自己答，
占用打到在册阈值、语料落到冷表时让路给非热集腿——再把让路那一腿摘掉，证明进程内计数器
不可能不动。摘掉而计数不动 = 这枚驱动件自己没牙，本件用退出码把这件事说出去。

三条硬口径
----------
* **在册阈值现取**：预算不抄数字。`DEFAULT_MAX_CHUNKS` 与环境变量名 `HOT_INDEX_MAX_CHUNKS_ENV`
  的真实解析口径、`ROSTER_SCAN_ROW_CEILING` 一并打印；坐标由 inspect 派生成「文件::符号」，
  本件与它的读数里都不出现行号形态的坐标（新规③）。
* **不碰外部世界**：跑之前钉死六枚环境变量——打到端口 1 的 DSN（与 tests/conftest.py 同一口径，
  真要连就连不上，而不是悄悄连上生产 PG）、不可路由的模型 base_url、哨兵模型名、读后端 chroma、
  双写 off、热集开关 on。非热集腿在这里是一枚**计数桩**：它只证明"这一问确实被判定为热集不能答"；
  真腿走没走由 tests/test_r677_hot_set_yield_leg.py 在 `DocumentRetriever.search` 上钉。
* **重量不量**：让路延迟的成本在跨进程往返上，离线量不到，weight 那一格永远输出 NOT_MEASURED。
  真机读数欠一台安静机器，排在夜窗之后（工单 R677 判据 2／窗口单 docs/tickets/WINDOW-2026-10-06.md）。

退出码
------
0 两条腿都跑出来且让路腿承重／2 命令行用法错／3 摘掉让路腿而计数不动（牙死了）／
4 要覆盖率却没从在册量具读到数／5 判据点名的符号现在取不到／6 两条腿没能都跑出来。
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 离线针脚。库打到端口 1（与 tests/conftest.py 钉测试库同一口径：真要连库就连不上，
#: 而不是悄悄连上那台在生产口径上跑着的 PG）；模型端口反过来必须避开 1——那一格被 conftest
#: 认作它自己的 PG 钉子，撞上去 conftest 当场拒绝加载。端口 9 是 discard，本机没人听。
OFFLINE_DATABASE_URL = ("postgresql://postgres:postgres@127.0.0.1:1/"
                        "eb_r677_offline_pinned?connect_timeout=1")
OFFLINE_MODEL_BASE_URL = "http://127.0.0.1:9"
OFFLINE_MODEL_SENTINEL = "__eb_r677_offline_no_model__"

#: 每一遍读数都在这几枚针脚底下跑，读数里把钉住的原值一起吐出来，免得下一班猜环境。
PINNED_ENV = {
    "DATABASE_URL": OFFLINE_DATABASE_URL,
    "OLLAMA_BASE_URL": OFFLINE_MODEL_BASE_URL,
    "LOCAL_MODEL_NAME": OFFLINE_MODEL_SENTINEL,
    "INDEX_BACKEND": "chroma",
    "VECTOR_DUAL_WRITE": "off",
    "HOT_INDEX_ENABLED": "1",
}

#: 夹具自身的向量维度：热集不校验维度（校验在写库那一腿），服务判定与维度无关。
FIXTURE_DIMENSION = 64
#: 预算切到一枚，冷表必然有货——这就是"占用打到在册阈值"的离线形状。
CLIPPED_BUDGET = 1
TOP_K = 3
FILLER_DOCS = 6
COLD_DOCS = 3

RC_OK = 0
RC_USAGE = 2
RC_LEG_NOT_LOAD_BEARING = 3
RC_COVERAGE_UNREADABLE = 4
RC_SYMBOL_MISSING = 5
RC_LEGS_NOT_RUN = 6

#: 判据① 只认现取符号名。取不到本件直接判负，不许退化成"应有让路机制"那句散文。
LEG_SYMBOLS = (
    "REASON_INCOMPLETE",
    "REASON_DISABLED",
    "DEFAULT_MAX_CHUNKS",
    "HOT_INDEX_MAX_CHUNKS_ENV",
    "ROSTER_SCAN_ROW_CEILING",
    "_note_bypass",
    "_squared_l2",
    "HotSetIndex.populate",
    "HotSetIndex.rank",
    "HotSetIndex.bypass_reason",
    "HotSetIndex._bypass_locked",
    "HotSetIndex._could_be_recalled_locked",
    "HotSetIndex._evict_locked",
)

#: 覆盖率不在这里重新发明：当场跑在册量具那一枚，把它打印的读数行取回来。
COVERAGE_GAUGE = "tests/test_r44_hot_index_coverage.py"
COVERAGE_TEST = "covers_the_evaluation_question_set"
COVERAGE_PATTERNS = {
    "served": re.compile(r"热集覆盖率 = (\d+)/(\d+)"),
    "consistency": re.compile(r"与外部向量库逐条同序同 id = (\d+)/(\d+)"),
    "chunks": re.compile(r"向量库 (\d+) 个 chunk"),
    "resident_cold": re.compile(r"其中常驻 (\d+)，冷表 (\d+)"),
}


def pin_offline_env() -> dict:
    """把三条会打到外部世界的腿钉住：库、模型、读后端。交回钉住的那几行。"""
    for name, value in PINNED_ENV.items():
        os.environ[name] = value
    return dict(PINNED_ENV)


def resolve_symbols(module) -> tuple:
    """把 LEG_SYMBOLS 现取成对象；解析不到的名字逐枚点名，不静默少一枚。"""
    found, missing = {}, []
    for name in LEG_SYMBOLS:
        target = module
        for piece in name.split("."):
            target = getattr(target, piece, None)
            if target is None:
                break
        if target is None:
            missing.append(name)
        else:
            found[name] = target
    return found, tuple(missing)


def symbol_coordinates(module, found) -> list:
    """「文件::符号」坐标全部派生：路径来自 inspect，符号名来自活对象。"""
    source = Path(inspect.getsourcefile(module) or str(module.__file__)).resolve()
    relative = source.relative_to(REPO_ROOT).as_posix()
    coordinates = []
    for name in LEG_SYMBOLS:
        obj = found.get(name)
        if obj is None:
            continue
        qualname = getattr(obj, "__qualname__", None)
        symbol = qualname if callable(obj) and qualname else name.rsplit(".", 1)[-1]
        coordinates.append(f"{relative}::{symbol}")
    return coordinates


def token_vector(text, dimension: int = FIXTURE_DIMENSION) -> list:
    """确定性词袋向量：同一枚 token 永远点亮同一维，一次模型都不打。

    词频就是权重（重复 n 次给 n），所以下面那批夹具文档两两距离不相等，名次没有并列——
    并列的名次没法当判据：chroma 与热集对并列的破序规则不同源。
    """
    vector = [0.0] * dimension
    for token in re.findall(r"\w+", str(text), flags=re.UNICODE):
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:4], "big")
        vector[digest % dimension] += 1.0
    if not any(vector):
        vector[0] = 1.0
    return vector


def build_rows(*, filler_docs: int = FILLER_DOCS, cold_docs: int = COLD_DOCS) -> list:
    """可控语料：filler 排在前面（先吃满预算），cold 排在预算之外。

    真实暖机那条是按 id 尾部取预算内的批次（`DocumentRetriever._warm_hot_index`），本件直接喂
    `populate()`，方向相反但判据同一枚：冷表里只要还剩可能被召回的条目，热集就不许答。
    """
    rows = []
    for group, count in (("fill", filler_docs), ("cold", cold_docs)):
        for position in range(count):
            token = f"{group}{position}"
            rows.append((f"{token}_0",
                         f"{token} 段落正文 只有这一篇带着这个词",
                         {"filename": f"{token}.txt", "classification": 1, "department": "ops"},
                         token_vector(token)))
    return rows


class _ExternalLegStandIn:
    """非热集腿的计数桩：只回答"这一问真的回穿了外部检索吗"，不假装自己是真库。"""

    def __init__(self, rows, module) -> None:
        self._rows = rows
        self._module = module
        self.calls = 0

    def exact_ids(self, query_vector, k: int) -> list:
        scored = sorted(((self._module._squared_l2(row[3], query_vector), row[0])
                         for row in self._rows), key=lambda item: (item[0], item[1]))
        return [str(chunk_id) for _distance, chunk_id in scored[:k]]

    def answer(self, query_vector, k: int) -> list:
        self.calls += 1
        return self.exact_ids(query_vector, k)


def _one_leg(module, rows, *, budget: int, query_vector, k: int,
             neuter_yield: bool = False) -> dict:
    """把预算钉在 budget、问同一道题：热集答不答、外部腿被叫了几次、计数器怎么动。"""
    index = module.HotSetIndex(max_chunks=budget, roster_ttl_seconds=3600.0)
    module.reset_hot_index_diagnostics()
    scope_key = module.current_scope_key()
    index.adopt_scope(scope_key)
    admitted = index.populate(rows, scope_key=scope_key)
    stand_in = _ExternalLegStandIn(rows, module)
    if neuter_yield:
        # 摘腿：把"冷条目会不会被召回"永远答成不会，等价于删掉那圈冷表扫描。
        index._could_be_recalled_locked = lambda metadata, where, pred: False
    before = module.hot_index_diagnostics()
    reason_before = index.bypass_reason(scope_key=scope_key, query_vector=query_vector)
    ranked = index.rank(query_vector, k, scope_key=scope_key)
    after = module.hot_index_diagnostics()
    if ranked is None:
        served = False
        answered = stand_in.answer(query_vector, k)
    else:
        served = True
        answered = [str(item[1]) for item in ranked]
    return {
        "budget": budget,
        "resident_chunks": index.resident_chunks,
        "cold_chunks": index.cold_chunks,
        "populate_admitted": admitted["resident"],
        "populate_cold": admitted["cold"],
        "served_by_hot_leg": served,
        "bypass_reason_before": reason_before,
        "bypass_reason_after": after["last_bypass_reason"],
        "external_leg_calls": stand_in.calls,
        "hits_delta": after["hits"] - before["hits"],
        "misses_delta": after["misses"] - before["misses"],
        "answered_ids": answered,
        "answer_matches_exact_oracle": answered == stand_in.exact_ids(query_vector, k),
    }


def verdict_for(legs_block: dict, reason_code: str) -> dict:
    """承重结论只从三遍读数推出来：把这段判定摘掉，驱动件就必须换退出码。

    分成两枚判语是刻意的：`both_legs_ran` 说"两条腿都真的跑出来了"，`yield_leg_load_bearing`
    说"把让路那圈冷表扫描摘掉之后计数器动了、而且答案变短了"。前者红是量具坏了，后者红是
    这条腿不承重——两件事不能让同一个退出码顶。
    """
    hit = legs_block["hot_hit"]
    yield_leg = legs_block["yield"]
    removed = legs_block["yield_leg_removed"]
    both_legs = (hit["served_by_hot_leg"] is True
                 and hit["external_leg_calls"] == 0
                 and yield_leg["served_by_hot_leg"] is False
                 and yield_leg["external_leg_calls"] == 1)
    load_bearing = (yield_leg["misses_delta"] == 1
                    and yield_leg["hits_delta"] == 0
                    and removed["hits_delta"] == 1
                    and removed["misses_delta"] == 0
                    and removed["served_by_hot_leg"] is True
                    and removed["answer_matches_exact_oracle"] is False)
    return {"both_legs_ran": both_legs,
            "yield_leg_load_bearing": load_bearing,
            "reason_code_that_carries_the_leg": reason_code}


def measure(module) -> dict:
    """同一份语料跑三遍：装得下／装不下／装不下但让路腿被摘掉。"""
    rows = build_rows()
    query_vector = token_vector("cold0 段落正文 只有这一篇带着这个词")
    legs_block = {
        "hot_hit": _one_leg(module, rows, budget=len(rows), query_vector=query_vector, k=TOP_K),
        "yield": _one_leg(module, rows, budget=CLIPPED_BUDGET, query_vector=query_vector, k=TOP_K),
        "yield_leg_removed": _one_leg(module, rows, budget=CLIPPED_BUDGET,
                                      query_vector=query_vector, k=TOP_K, neuter_yield=True),
    }
    return {
        "legs": legs_block,
        "corpus": {"chunks": len(rows), "filler_docs": FILLER_DOCS, "cold_docs": COLD_DOCS,
                   "dimension": FIXTURE_DIMENSION, "top_k": TOP_K,
                   "fixture": "synthetic-token-bag（不为覆盖率造数，只跑两条腿的形状）"},
        "verdict": verdict_for(legs_block, module.REASON_INCOMPLETE),
    }


def legs(module) -> dict:
    """判据①那一格：在钉住的离线环境里跑三遍，且不把环境泄漏给调用方的进程。"""
    with mock.patch.dict(os.environ, PINNED_ENV):
        return measure(module)


def registered_threshold(module) -> dict:
    """在册阈值现取：默认值、环境变量名、此刻环境的值、空实例真正在用的那一份。"""
    return {
        "default_max_chunks": module.DEFAULT_MAX_CHUNKS,
        "env_name": module.HOT_INDEX_MAX_CHUNKS_ENV,
        "env_value_now": os.getenv(module.HOT_INDEX_MAX_CHUNKS_ENV, ""),
        "instance_default": module.HotSetIndex().max_chunks,
        "roster_scan_row_ceiling": module.ROSTER_SCAN_ROW_CEILING,
    }


def coverage_denominator() -> dict:
    """分母从 fixture 现读：文件逐枚点名，题数按 id 去重。"""
    fixture_root = REPO_ROOT / "tests" / "fixtures"
    files = sorted(fixture_root.glob("business_evaluation_*.jsonl"))
    per_file, ids = {}, set()
    for path in files:
        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        per_file[path.name] = len(rows)
        for line in rows:
            ids.add(str(json.loads(line)["id"]))
    return {"files": per_file, "distinct_questions": len(ids),
            "source": "tests/fixtures/business_evaluation_*.jsonl"}


def registered_coverage_readout(timeout_seconds: int) -> dict:
    """覆盖率不重造：当场跑在册量具那一枚，把它打印的读数取回来。

    取不到就是取不到——原样交回 NOT_MEASURED 加那枚退出码，不许拿账面旧数顶（工单判据 3）。
    """
    target = REPO_ROOT / COVERAGE_GAUGE
    result = {"status": "NOT_MEASURED", "source": COVERAGE_GAUGE, "test": COVERAGE_TEST,
              "exit_code": None, "readouts": {}, "note": ""}
    if not target.is_file():
        result["note"] = "在册量具不在盘上"
        return result
    command = [sys.executable, "-m", "pytest", COVERAGE_GAUGE, "-q", "-s",
               "-p", "no:cacheprovider", "-k", COVERAGE_TEST]
    try:
        child_env = dict(os.environ, PYTHONUTF8="1")
        proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, env=child_env,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        result["note"] = f"在册量具 {timeout_seconds} 秒内没跑完"
        return result
    output = (proc.stdout or "") + (proc.stderr or "")
    result["exit_code"] = proc.returncode
    for label, pattern in COVERAGE_PATTERNS.items():
        match = pattern.search(output)
        if match:
            result["readouts"][label] = list(match.groups())
    if "served" in result["readouts"]:
        result["status"] = "MEASURED"
        served, total = (int(value) for value in result["readouts"]["served"])
        result["coverage_pct"] = round(served / total * 100, 2) if total else None
    else:
        result["note"] = "在册量具跑完了，但读数行没匹配上（那是口径漂了，不是覆盖率为零）"
    return result


def weight_block() -> dict:
    """重量这一格离线量不到：本件禁模型、禁容器、禁库，只许写未验。"""
    return {"status": "NOT_MEASURED",
            "reason": "让路延迟的成本在跨进程往返上；本件离线，夜窗之内也不许重量",
            "where": "docs/tickets/WINDOW-2026-10-06.md"}


def not_proved() -> list:
    """本件明确不证明的事，逐枚点名（反假账第 7 条：两头都要说）。"""
    return [
        "让路延迟与热集冷启装载的代价：要安静机器真机窗，本件离线量不到",
        "客户尺寸语料能不能装进在册预算：要客户库，本件不读",
        "读后端为 pgvector 时整层让路：那是另一枚原因码（读后端切换），不归本件",
        "覆盖率的分母是评测集，不是真实查询日志：本机没有可现读的客户查询日志",
        "合成词袋语料的排名：只证两条腿的形状与计数承重，不代表检索质量",
    ]


def read_backend_now() -> str:
    try:
        from app.rag import indexing
        return indexing.read_backend()
    except Exception as exc:  # pragma: no cover - 取不到就照实写，不猜
        return f"UNREADABLE:{type(exc).__name__}"


def report(module, *, coverage: bool, timeout_seconds: int) -> dict:
    found, missing = resolve_symbols(module)
    measurement = legs(module)
    if coverage:
        coverage_block = dict(registered_coverage_readout(timeout_seconds))
    else:
        coverage_block = {"status": "NOT_MEASURED", "readouts": {}, "exit_code": None,
                          "note": "没带 --coverage：这一档要现读建库，默认不开",
                          "source": COVERAGE_GAUGE, "test": COVERAGE_TEST}
    coverage_block["denominator"] = coverage_denominator()
    coverage_block["requested"] = coverage
    payload = dict(measurement)
    payload["coordinates"] = symbol_coordinates(module, found)
    payload["threshold"] = registered_threshold(module)
    payload["pinned_env"] = dict(PINNED_ENV)
    payload["read_backend_in_this_process"] = read_backend_now()
    payload["coverage"] = coverage_block
    payload["weight"] = weight_block()
    payload["not_proved"] = not_proved()
    payload["verdict"] = dict(measurement["verdict"], symbols_missing=list(missing))
    return payload


def exit_code_for(payload: dict) -> int:
    verdict = payload["verdict"]
    if verdict.get("symbols_missing"):
        return RC_SYMBOL_MISSING
    if not verdict.get("both_legs_ran"):
        return RC_LEGS_NOT_RUN
    if not verdict.get("yield_leg_load_bearing"):
        return RC_LEG_NOT_LOAD_BEARING
    coverage = payload.get("coverage", {})
    if coverage.get("requested") and coverage.get("status") != "MEASURED":
        return RC_COVERAGE_UNREADABLE
    return RC_OK


def _scalar(value) -> str:
    if isinstance(value, (bool, int, float)) or value is None:
        return json.dumps(value)
    return str(value)


def _flatten(prefix: str, block, lines: list) -> None:
    if isinstance(block, dict):
        for key, value in block.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), value, lines)
    elif isinstance(block, list):
        lines.append(f"{prefix} = {json.dumps(block, ensure_ascii=False)}")
    else:
        lines.append(f"{prefix} = {_scalar(block)}")


def render_lines(payload: dict) -> list:
    lines: list = []
    for section in ("threshold", "corpus", "legs", "verdict", "coverage", "weight",
                    "not_proved", "coordinates"):
        _flatten(section, payload[section], lines)
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R677 让路驱动件：离线跑通热集两条腿，并证明让路那一腿承重")
    parser.add_argument("--json", action="store_true", help="机器可读整块输出")
    parser.add_argument("--coverage", action="store_true",
                        help="当场跑在册覆盖率量具取数（要现读建库，默认不开）")
    parser.add_argument("--timeout-seconds", type=int, default=900,
                        help="--coverage 那一档给在册量具的墙钟上限")
    parser.add_argument("--out", default="",
                        help="把 JSON 另落一枚文件（只写自己点名的那一枚）")
    args = parser.parse_args(argv)

    pin_offline_env()
    from app.rag import hot_index as module

    try:
        payload = report(module, coverage=args.coverage, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        print(f"r677 驱动件读不到热集：{type(exc).__name__}: {exc}", file=sys.stderr)
        return RC_SYMBOL_MISSING
    code = exit_code_for(payload)
    payload["exit_code_planned"] = code
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        print(text)
    else:
        for line in render_lines(payload):
            print(line)
    print(f"exit = {code}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
