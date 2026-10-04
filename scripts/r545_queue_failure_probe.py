"""R545 —— 队列道「失败有终态与原因码」缺的那一次真队列失败读数（量具本体，零产品码改动）。

来历（底稿原话 + 本基点现读复核，纸面一律重新量过）：
  09-30 波次五底稿说 #8／#22 那一格「码与牙在（app/common/reliable_queue.py:498 failure()），
  台账自判 PARTIAL，欠真机重量」，并称 deploy/queue_worker.py 里 stream_piece_sink 零命中
  （rc=1，无可注册点）。**两枚前提在本基点 4da0bad 都已过期**：
    * 注册点今天有——R548 交出片段汇那一枚收端、R578 在旁边补第二枚 report_failure_sink。
      现读 git grep -n stream_piece_sink -- deploy/queue_worker.py 交回 **rc=0**
      （:431 类自述 / :603 形参 / :610 判据自述 / :635 转交 / :827 装配点）。
    * 行号也漂了：failure() 现在住在 app/common/reliable_queue.py:647（不是 :498），
      dead_letter_depth() 在 :679（不是 :529），写 last_error 那一行在 :582（不是 :423）。
  所以本件量的仍是那句唯一没被量过的话：**一台真容器里，一枚真失败的队列任务，客户能不能
  从在册出口读出它是谁、为什么、还剩几次名额**。

今天盘面（现读取证，不是抄来的）：
  * 终态词表**不是五枚**。队列往状态键写过 8 枚字（queued / processing / cancel_requested /
    done / cancelled / failed / dead / awaiting_approval），轮询路由在状态键读不到时自己现造
    第 9 枚（expired）。其中停表（终态）的是**六枚**：done / cancelled / failed / dead /
    awaiting_approval / expired —— 第六枚正是 awaiting_approval。本件不抄任何一份手抄名单：
    词表、读数键序、稳定码表、路由路径全部 AST 现派生（与
    tests/test_r232_queue_status_vocabulary_sync.py 同一条纪律）。
  * 入队判定 = lane == report **且** REPORT_LANE_VIA_QUEUE 为 on（app/api/v1/chat.py:2568，
    读 _enqueue_ask_turn 的两个调用点之一），生产那枚开关今天仍为 off（deploy/.env.server，
    gitignore 件、本树无副本）=> 不在窗里翻开，本件一枚失败都造不出来，相关格只落 UNMEASURED。

三条纪律（写在代码里，不在注释里躲）：

1. 不改产品码制造失败，也不改 .env、不起容器、不重建镜像。注入姿势只有四枚，写死成参数
   （--inject）：expired（读一枚没人写过的 request_id，零副作用）、cancel（走在册
   POST /api/v1/queue/{request_id}/cancel）、budget（把请求侧 prompt 撑长，同时要求 worker
   进程把 MODEL_CONTEXT_TOKENS 调小 —— 旋钮不在位这一格就判量不到）、endpoint（要求 worker
   进程的 LOCAL_MODEL_BASE_URL / OLLAMA_BASE_URL 指到一扇没人听的端口）。后两枚的窗与重建由
   总控执行，本件只验旋钮在不在位并交回命令原文（--print-recipe）。
2. 缺证词记 None（判据①）。每一格只有三种说法：read（读到了，值原样在）、
   row_cannot_speak（这一行压根不交这一格，值记 None 并登记进 absent 清单）、以及本件自己
   没跑成（整格 UNMEASURED）。「读不到」折成 0 / [] / 空串就是把「没说」洗成「说了零」——
   R254 与 R585 各治过一次，本件第三次不许犯。
3. 产物落仓外（runbook §8）。默认 tempfile.gettempdir()/r545-<date>；--out 解析到仓库内任何
   路径一律 rc=2 拒绝并说明理由。scripts/ 与 docs/ 里不许漏下一件证据。

读回只走在册出口：GET /api/v1/queue/status/{request_id}（路径由 app/api/v1/chat.py 的装饰器
AST 现取，不抄纸面）、GET /api/v1/queue/stats；Redis 那一腿只经产品自己的
connect_reliable_queue()，且一次都不写（ping / EXISTS / GET / LLEN）。

用法：
    python scripts/r545_queue_failure_probe.py --print-recipe
    python scripts/r545_queue_failure_probe.py --inject expired --inject cancel --expect-rev <HEAD>
    python scripts/r545_queue_failure_probe.py --offline %TEMP%\r545-2026-10-04
容器内那一遍（总控开窗；账号与口令走 env，凭据纸 §4 有整行原文）：
    docker exec -e EVAL_USERNAME -e EVAL_PASSWORD enterprise-brain-worker-1 /app/.venv/bin/python scripts/r545_queue_failure_probe.py --inject budget --expect-rev <HEAD>

退出码（写死，判据②）：
    0 = 九格全 PASS，且这一遍真看到至少一枚失败终态带着可读的原因码；
    1 = 至少一格 FAIL（口径漂了、原因码读不出、或把缺证折成了零）；
    2 = 至少一格 UNMEASURED，或量具自己没跑成（缺凭证、Redis 不通、契约读不到、产物目录落在仓内）。
    2 永远不是「已通过」；开关没翻、窗没开，正确的结果就是 2。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 派生面的源文件。镜像只带前三枚（Dockerfile 只 COPY app / scripts / deploy / migrations，不带 docs/），
#: 所以契约那张脸在容器里读不到 —— 本件把它如实记进 unreadable，并允许 --contract-from 带一份副本进来。
QUEUE_REL = "app/common/reliable_queue.py"
CHAT_REL = "app/api/v1/chat.py"
CONTRACTS_REL = "app/agents/contracts.py"
CONTRACT_REL = "docs/api/contract-v1.md"
GAUGE_REL = "scripts/eval_transport_ask_v2.py"

STATUS_KEY_METHOD = "_status_key"
STATUS_DICT_KEY = "status"
POLL_PATH_FRAGMENT = "/queue/status/"
CANCEL_PATH_TAIL = "/cancel"
TERMINAL_STATE_TO_STATUS_NAME = "TERMINAL_STATE_TO_STATUS"
DEAD_SCHEMA_NAME = "DEAD_TERMINAL_SCHEMA"
DISCARD_CODE_NAME = "RESULT_DISCARDED"
DEAD_STATUS_NAME = "DEAD_STATUS"
AWAITING_NAME = "AWAITING_APPROVAL"
WORD_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CONTRACT_SECTION = "## Long Task Status"
CONTRACT_BULLET_RE = re.compile(
    r"^\* `(?P<value>[a-z][a-z0-9_]*)` "
    r"\((?P<phase>non-terminal|terminal), "
    r"(?P<layer>written by the queue|answered by the route)\): (?P<prose>.+)$",
    re.MULTILINE,
)
CONTRACT_ENUM_RE = re.compile(r"^`status` is one of .+\.$", re.MULTILINE)
PROSE_COUNT_RE = re.compile(r"(?:今天|上面|上面那|共|共计)([一二三四五六七八九十])枚终态"
                          r"|([一二三四五六七八九十])枚终态（")
CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

PASS, FAIL, UNMEASURED = "PASS", "FAIL", "UNMEASURED"
#: 一格的两种诚实说法：读到了 / 这一行说不出（后者值记 None，并登记进 absent 清单）。
SPEAKS_READ = "read"
SPEAKS_CANNOT = "row_cannot_speak"

FAILURE_FIELD = "failure"
LAST_ERROR_KEY = "last_error"
ATTEMPTS_KEY = "attempts"
MAX_ATTEMPTS_KEY = "max_attempts"
REASON_KEY = "reason"
RETRYABLE_KEY = "retryable"
SCHEMA_KEY = "terminal_schema"
STATE_KEY = "terminal_state"
NOTE_KEY = "terminal_note"
POSITION_KEY = "position"
#: 判据②点名的四枚结构化终态键：键名先由 queue_terminal_readout 的 AST 派生，再与这张需求单取交。
REQUIRED_TERMINAL_KEYS = ("terminal_state", "answer_present", "sources_present", "usage")

CELLS = (
    "provenance",
    "vocabulary",
    "failure_reason",
    "dead_keys",
    "retry_budget",
    "dead_letter_depth",
    "idempotency",
    "terminal_keys",
    "none_is_none",
)

#: 失败家族：这一族必须说得出成因。expired 不在内 —— 那一格说的是「账本压根读不到」，
#: 由 vocabulary / terminal_keys 如实记 None，不许拿它冒充「一次真失败读数」。
FAILURE_FAMILY = ("dead", "cancelled", "failed")

#: 注入姿势表。四枚姿势的差别只在「失败从哪一扇门进来」，本件一律不改产品码。
POSTURE_NONE = "none"
POSTURE_EXPIRED = "expired"
POSTURE_CANCEL = "cancel"
POSTURE_BUDGET = "budget"
POSTURE_ENDPOINT = "endpoint"
POSTURES = {
    POSTURE_NONE: {"env_required": (), "side_effects": "零", "note": "不注入，只把盘面读回来"},
    POSTURE_EXPIRED: {"env_required": (), "side_effects": "零（读一枚没人写过的 request_id）",
                      "note": "这一姿势量的是 expired 那格在在册门上读不读得到：本基点现读 "
                              "chat.py::_authorize_queue_task 先要求 message 键在位，否则 404 "
                              "resource_not_found，所以读到 404 就是「expired 经这扇门不可达」，"
                              "整格记 None，不许折算成一次失败读数"},
    POSTURE_CANCEL: {"env_required": (), "side_effects": "一枚真队列任务 + 一扇在册 cancel 门",
                     "note": "走在册 POST /api/v1/queue/{request_id}/cancel"},
    POSTURE_BUDGET: {"env_required": ("MODEL_CONTEXT_TOKENS",),
                     "side_effects": "一枚真队列任务（worker 侧被在册闸拦下）",
                     "note": "让 app/common/model_budget.py 的在册闸在发请求前就拒，产出在册码"},
    POSTURE_ENDPOINT: {"env_required": ("LOCAL_MODEL_BASE_URL", "OLLAMA_BASE_URL"),
                       "side_effects": "一枚真队列任务（provider 连不上）",
                       "note": "把模型端点指到一扇没人听的端口，失败来自产品自己的调用腿"},
}
#: 旋钮的后半句：budget 要「比这一问需要的小」，endpoint 要「这扇端口真不通」。两枚都是现读判定。
BUDGET_ARM_CEILING = 8192

LOGIN_PATH = "/api/v1/login"
ASK_PATH = "/api/v1/ask"
STATS_PATH = "/api/v1/queue/stats"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_QUESTION = "请把上一季度的经营状况写成一份完整报告，并逐条给出出处。"


class SourceUnreadable(RuntimeError):
    """派生读不到源文件或抠不出任何东西：这一格只能量不到，绝不退回一份手抄名单。"""


class GaugeFailure(RuntimeError):
    """量具自己没跑成（缺凭证、产物目录落在仓内、存档读不出）：一律 rc=2。"""

# ==================== 派生面（AST + 契约文本，零手抄） ====================

def normalize_newlines(text: str) -> str:
    """行尾归一：本仓 ``core.autocrlf = true``，检出来的源文是 CRLF。一枚字面 `\r` 躲在 `$`
    前面会让一切「以字面字符收尾」的正则静默失配——契约里那枚 ``status` is one of ...``
    枚举行就是这么被读成「纸面没有」的（本单自纠，见取证纸 §13）。派生面必须与检出口径无关。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_source(rel: str, repo: Path | None = None) -> str:
    path = (repo or ROOT) / rel
    try:
        return normalize_newlines(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceUnreadable(rel + " 读不到：" + type(exc).__name__ + ": " + str(exc)) from exc


def _status_write_sites(tree: ast.AST) -> list:
    """每一处 redis.set(self._status_key(...), 值)：交回 (字面量或空串, 行号)。"""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "set"):
            continue
        target = node.args[0] if node.args else None
        if not (isinstance(target, ast.Call) and isinstance(target.func, ast.Attribute)
                and target.func.attr == STATUS_KEY_METHOD):
            continue
        value = node.args[1] if len(node.args) > 1 else None
        for keyword in node.keywords:
            if keyword.arg == "value":
                value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            hits.append((value.value, node.lineno))
        else:
            hits.append(("", node.lineno))
    return hits


def queue_written_words(source: str, origin: str) -> dict:
    """队列往状态键写过的每一枚字面量，逐枚带出处；写成变量的站点记进 blind_spots。"""
    written: dict = {}
    blind: list = []
    for word, lineno in _status_write_sites(ast.parse(source)):
        if not word:
            blind.append("%s:%d 写进 status 键的不是字面量，本件读不到它的取值" % (origin, lineno))
            continue
        if not WORD_RE.match(word):
            raise SourceUnreadable("%s:%d 抠出的 %r 不合状态词形状" % (origin, lineno, word))
        written.setdefault(word, []).append("%s:%d" % (origin, lineno))
    if not written:
        raise SourceUnreadable(origin + " 里一处 status 写入都没抠到，比对失去对象")
    return {"words": written, "blind_spots": blind}


def _route_function(source: str, fragment: str, tail: str = "", origin: str = ""):
    """按装饰器里的路径找那支路由（找路径不找行号：行号会为别人的一次编辑而漂）。"""
    found = None
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and decorator.args):
                continue
            path = decorator.args[0]
            if not (isinstance(path, ast.Constant) and isinstance(path.value, str)):
                continue
            if fragment in path.value and (not tail or path.value.endswith(tail)):
                if found is not None:
                    raise SourceUnreadable(origin + " 里有多于一支 " + fragment + " 路由")
                found = node
        if found is not None:
            break
    if found is None:
        raise SourceUnreadable("找不到 " + fragment + " 那一支路由，量具没有在册出口可读")
    return found


def route_status_words(source: str, origin: str) -> dict:
    """轮询路由写死的 status 字面量、它转发的读数，以及每一支早退分支交了哪些键。

    那支「状态键读不到就现造 expired」的早退是本单最重要的一格证据：它在不在位、
    交不交 failure，全部从 AST 现取，不抄契约那句「every non-expired status response」。
    """
    route = _route_function(source, POLL_PATH_FRAGMENT, origin=origin)
    literals: list = []
    forwarded = False
    early: list = []
    for node in ast.walk(route):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and key.value == STATUS_DICT_KEY):
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literals.append(value.value)
                else:
                    forwarded = True
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            pairs = [(k.value, v) for k, v in zip(node.value.keys, node.value.values)
                     if isinstance(k, ast.Constant)]
            status_value = dict(pairs).get(STATUS_DICT_KEY)
            if isinstance(status_value, ast.Constant) and isinstance(status_value.value, str):
                early.append({"status": status_value.value,
                              "keys": [str(name) for name, _ in pairs]})
    return {"route_literals": literals, "forwards_queue_status": forwarded,
            "early_returns": early}


def dict_keys_returned(source: str, function_name: str) -> list:
    """某枚读数函数交回的那套键名：`return {..}`、`readout.update({..})`、`readout["k"] = ..` 三形都认。

    `queue_terminal_readout` 交回的是 `readout` 那枚变量而不是字面量，只认 return 就会当场
    判「派生不出来」——那不是产品没键序，是本件的形状认不全。按书写顺序去重交回。
    """
    target = None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target = node
    if target is None:
        raise SourceUnreadable(function_name + " 读不到，读数键无从派生")
    payload: list = []

    def _keep(keys):
        for key in keys:
            if key not in payload:
                payload.append(key)

    def _base(node):
        return node.id if isinstance(node, ast.Name) else getattr(node, "attr", "")

    holders = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            holders.add(node.value.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update":
            holders.add(_base(node.func.value))
    for node in ast.walk(target):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            _keep([str(k.value) for k in node.value.keys if isinstance(k, ast.Constant)])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "update" and _base(node.func.value) in holders \
                and node.args and isinstance(node.args[0], ast.Dict):
            _keep([str(k.value) for k in node.args[0].keys if isinstance(k, ast.Constant)])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for holder in targets:
                if isinstance(holder, ast.Name) and holder.id in holders and isinstance(node.value, ast.Dict):
                    _keep([str(k.value) for k in node.value.keys if isinstance(k, ast.Constant)])
                elif isinstance(holder, ast.Subscript) and _base(holder.value) in holders \
                        and isinstance(holder.slice, ast.Constant):
                    _keep([str(holder.slice.value)])
    if not payload:
        raise SourceUnreadable(function_name + " 交不出任何键名，读数键序派生不出来")
    return payload


def stable_error_codes(source: str) -> list:
    """ErrorEnvelope.code 那枚封闭枚举的运行时投影（唯一真源；本件只消费，不添成员）。"""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.AnnAssign):
            continue
        if not (isinstance(node.target, ast.Name) and node.target.id == "code"):
            continue
        # `code: Literal[...]` 是无默认值的 AnnAssign：类型住在 annotation，不在 value。
        value = node.annotation if node.value is None else node.value
        if not (isinstance(value, ast.Subscript) and getattr(value.value, "id", "") == "Literal"):
            continue
        slice_ = value.slice
        elements = slice_.elts if isinstance(slice_, ast.Tuple) else [slice_]
        codes = [item.value for item in elements if isinstance(item, ast.Constant)]
        if not codes:
            raise SourceUnreadable("ErrorEnvelope.code 抠不出任何稳定码")
        return list(codes)
    raise SourceUnreadable("找不到 ErrorEnvelope.code 那枚 Literal")


def contract_status_table(text: str) -> dict:
    """契约 Long Task Status 一节的逐值分档（终态/非终态 × 队列写的/路由现造的），解析器不硬编码值名。"""
    text = normalize_newlines(text)
    start = text.find(CONTRACT_SECTION)
    if start < 0:
        raise SourceUnreadable("契约里没有 " + CONTRACT_SECTION + " 那一节")
    body = text[start:]
    bullets = [match.groupdict() for match in CONTRACT_BULLET_RE.finditer(body)]
    if not bullets:
        raise SourceUnreadable("契约那一节抠不出任何一行逐值分档，比对失去对象")
    return {
        "terminal": [item["value"] for item in bullets if item["phase"] == "terminal"],
        "non_terminal": [item["value"] for item in bullets if item["phase"] == "non-terminal"],
        "by_route": [item["value"] for item in bullets if item["layer"] == "answered by the route"],
        "layers": {item["value"]: item["layer"] for item in bullets},
        "enum_line_present": bool(CONTRACT_ENUM_RE.search(body)),
    }


def gauge_stop_words(source: str) -> dict:
    """在册量具里与名为 status 的读数比较过的字面量：停表名单的第二张面孔（同一族 AST 纪律）。"""
    words: set = set()
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1):
            continue
        operands = [node.left] + list(node.comparators)
        names = [item for item in operands if isinstance(item, ast.Name) and item.id == "status"]
        if not names:
            continue
        for other in [item for item in operands if item not in names]:
            if isinstance(other, ast.Constant) and isinstance(other.value, str):
                words.add(other.value)
            elif isinstance(other, (ast.Tuple, ast.List)):
                for item in other.elts:
                    if isinstance(item, ast.Constant) and isinstance(item.value, str):
                        words.add(item.value)
    claimed = [CN_DIGITS.get(found, -1) for found in _flatten_prose(PROSE_COUNT_RE.findall(source))]
    return {"stop_words": sorted(words), "prose_counts": [c for c in claimed if c > 0]}


def module_constant(source: str, name: str) -> str:
    """模块级 NAME = "字面量" 的取值（读源文而不是 import：镜像里的 import 面比源码宽）。"""
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return str(node.value.value)
    raise SourceUnreadable("模块级常量 " + name + " 读不到，词表缺一枚锚")


def success_status_words(queue_source: str) -> list:
    """TERMINAL_STATE_TO_STATUS 的值（成功终态那两枚状态词）：AST 派生，不抄字面。"""
    for node in ast.walk(ast.parse(queue_source)):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == TERMINAL_STATE_TO_STATUS_NAME:
                if isinstance(node.value, ast.Dict):
                    return [value.value for value in node.value.values
                            if isinstance(value, ast.Constant) and isinstance(value.value, str)]
    raise SourceUnreadable("TERMINAL_STATE_TO_STATUS 读不到，成功终态那一族没有锚")


def _flatten_prose(found):
    """re.findall 在两枚捕获组下交回元组：把它们摊平成一串枚数用词。"""
    out = []
    for item in found:
        out.extend([part for part in (item if isinstance(item, tuple) else (item,)) if part])
    return out

def derive_vocabulary(repo: Path | None = None, contract_text: str | None = None) -> dict:
    """四张面孔一起派生：队列写的字、路由现造的字、契约的分档、在册量具停的字。

    任何一张读不到就如实记进 unreadable，绝不用另一张冒充它；两张以上说得不一致才叫 drift。
    """
    queue_text = read_source(QUEUE_REL, repo)
    chat_text = read_source(CHAT_REL, repo)
    queue_face = queue_written_words(queue_text, QUEUE_REL)
    route_face = route_status_words(chat_text, CHAT_REL)
    written = set(queue_face["words"])
    route_only = sorted(word for word in route_face["route_literals"] if word not in written)
    awaiting = module_constant(queue_text, AWAITING_NAME)
    dead_status = module_constant(queue_text, DEAD_STATUS_NAME)

    faces = {"queue_written": sorted(written), "route_literal": route_face["route_literals"],
             "early_returns": route_face["early_returns"]}
    unreadable: list = []
    drift: list = []
    terminal: list = []
    non_terminal = sorted(written | set(route_only))
    prose_counts: list = []

    try:
        contract = contract_status_table(contract_text if contract_text is not None
                                         else read_source(CONTRACT_REL, repo))
        faces["contract"] = contract
        terminal = list(contract["terminal"])
        non_terminal = list(contract["non_terminal"])
    except SourceUnreadable as exc:
        unreadable.append("contract: " + str(exc))

    try:
        gauge = gauge_stop_words(read_source(GAUGE_REL, repo))
        faces["gauge"] = gauge
        prose_counts = gauge["prose_counts"]
        if not terminal:
            terminal = [word for word in gauge["stop_words"] if word in written or word in route_only]
            non_terminal = sorted((written | set(route_only)) - set(terminal))
    except SourceUnreadable as exc:
        unreadable.append("gauge: " + str(exc))

    universe = written | set(route_only)
    for word in terminal:
        if word not in universe:
            drift.append("契约说 %r 是终态，可没有任何一处代码写过它" % word)
    for word in sorted(universe - set(terminal) - set(non_terminal)):
        drift.append("代码写过 %r，契约两档里都没有它" % word)
    if faces.get("gauge") and terminal:
        unstopped = sorted(set(terminal) - set(faces["gauge"]["stop_words"]))
        if unstopped:
            drift.append("契约叫终态而量具不停表：" + ", ".join(unstopped))
    stale_prose = sorted({count for count in prose_counts if count != len(terminal)})

    return {
        "terminal": terminal,
        "non_terminal": non_terminal,
        "queue_written": sorted(written),
        "route_only": route_only,
        "by_route": list((faces.get("contract") or {}).get("by_route") or []),
        "sites": queue_face["words"],
        "blind_spots": queue_face["blind_spots"],
        "faces": faces,
        "drift": drift,
        "unreadable": unreadable,
        "prose_counts": prose_counts,
        "stale_prose": stale_prose,
        "sixth_terminal_named": awaiting in set(terminal),
        "awaiting_word": awaiting,
        "dead_status": dead_status,
        "dead_schema": module_constant(queue_text, DEAD_SCHEMA_NAME),
        "discard_prefix": module_constant(queue_text, DISCARD_CODE_NAME) + ":",
        "success_states": sorted(set(success_status_words(queue_text))),
        "poll_path": POLL_PATH_FRAGMENT,
        "terminal_readout_keys": dict_keys_returned(chat_text, "queue_terminal_readout"),
        "dead_readout_keys": dict_keys_returned(chat_text, "queue_dead_readout"),
        "stable_codes": stable_error_codes(read_source(CONTRACTS_REL, repo)),
    }

# ==================== 终态词 -> 可定位证据（判据① 的落笔处） ====================

def _absent(path: str, note: str) -> dict:
    """一枚说不出话的格子：值记 None，并登记进 absent 清单（绝不折成 0 / [] / 空串）。"""
    return {"value": None, "speaks": SPEAKS_CANNOT, "absent_path": path, "note": note}


def _present(path: str, value) -> dict:
    return {"value": value, "speaks": SPEAKS_READ, "absent_path": "", "note": ""}


def _failure_block(row) -> dict:
    """轮询面上那本重试账；不在位或不是 dict 就是读不出，不替它补一枚空 dict。"""
    block = row.get(FAILURE_FIELD) if isinstance(row, dict) else None
    return block if isinstance(block, dict) else {}


def reason_field_for(word: str, row, vocab: dict) -> dict:
    """这一枚终态的「原因码字段名」从哪一格里读：三条路各说各话，一律由派生的键序判定。"""
    if not isinstance(row, dict):
        return _absent("reason_code_field", "这一行压根没读回来")
    block = _failure_block(row)
    if word == vocab["dead_status"]:
        expected = vocab["dead_readout_keys"]
        if REASON_KEY in expected and REASON_KEY in row:
            return _present("reason_code_field", REASON_KEY)
        if REASON_KEY in expected:
            return _absent("reason_code_field",
                           "死终态那格的键序里有 reason，可这一行没交 —— 形状与代码不一致")
        return _absent("reason_code_field", "queue_dead_readout 的键序里没有原因码那一格")
    if word in vocab["success_states"]:
        code = row.get("scope_reason_code")
        if isinstance(code, str) and code:
            return _present("reason_code_field", "scope_reason_code")
        return _absent("reason_code_field",
                       "成功终态不交失败成因（这一行的 scope_reason_code 为空，空串不是原因码）")
    if LAST_ERROR_KEY in block:
        return _present("reason_code_field", FAILURE_FIELD + "." + LAST_ERROR_KEY)
    if not block:
        return _absent("reason_code_field",
                       "这一行不交 " + FAILURE_FIELD + " 那一本账：路由只在状态键读得到时才有它")
    return _absent("reason_code_field", FAILURE_FIELD + " 在位而 last_error 那一格没值")


def last_error_readout(row, vocab: dict) -> dict:
    """last_error 的原样读数 + 它的前缀 + 它认不认得在册稳定码（三件事分三格说）。"""
    block = _failure_block(row)
    raw = block.get(LAST_ERROR_KEY) if block else None
    if raw is None:
        return {"cell": _absent(FAILURE_FIELD + "." + LAST_ERROR_KEY,
                                "这一行没交 last_error（读不到 != 没有错）"),
                "prefix": None, "is_stable_code": None}
    text = str(raw)
    prefix = vocab["discard_prefix"] if text.startswith(vocab["discard_prefix"]) else None
    return {"cell": _present(FAILURE_FIELD + "." + LAST_ERROR_KEY, text),
            "prefix": prefix,
            "is_stable_code": text in set(vocab["stable_codes"])}


def terminal_key_cells(row, vocab: dict, word: str) -> dict:
    """判据②点名的四枚结构化终态键逐枚表态；这一行压根不交这一格时值记 None。"""
    expected = list(vocab["dead_readout_keys"]) if word == vocab["dead_status"] \
        else list(vocab["terminal_readout_keys"])
    # 四枚键每一枚都必须有一句证词：读到（值原样）或说不出（值 None 并登记）。少一句就是漏判。
    cells: dict = {}
    for key in REQUIRED_TERMINAL_KEYS:
        if not isinstance(row, dict):
            cells[key] = _absent(key, "这一行没读回来")
        elif key in row:
            cell = _present(key, row.get(key))
            if row.get(key) is None:
                cell["note"] = ("键在位而值为 null（读到 null != 这一格不交）："
                                + str(row.get(NOTE_KEY) or "")[:160])
            cells[key] = cell
        elif key in expected:
            cells[key] = _absent(key, "%s 这一格该交 %s 却没交" % (word, key))
        else:
            cells[key] = _absent(key, "%s 那一形的在册读数键里压根没有 %s（这一行说不出，不折成零）"
                                 % (word, key))
    return {"asked": list(REQUIRED_TERMINAL_KEYS), "expected_keys": expected, "cells": cells,
            "unreadable_from_code": [key for key in REQUIRED_TERMINAL_KEYS if key not in expected]}


def evidence_from_row(word: str, row, vocab: dict, *, depth=None, idempotency=None) -> dict:
    """一枚终态词的完整可定位证据：原因码字段、last_error 前缀、重试计数、死信深度、幂等键。"""
    block = _failure_block(row)
    reason_cell = reason_field_for(word, row, vocab)
    error = last_error_readout(row, vocab)
    keys = terminal_key_cells(row, vocab, word)
    absent = [cell["absent_path"] for cell in [reason_cell, error["cell"]] + list(keys["cells"].values())
              if cell["speaks"] == SPEAKS_CANNOT]
    return {
        "terminal": word,
        "observed": isinstance(row, dict),
        "reason_code_field": reason_cell["value"],
        "reason_code_field_verdict": reason_cell["speaks"],
        "reason_code": row.get(REASON_KEY) if (word == vocab["dead_status"] and isinstance(row, dict)) else None,
        "retryable": row.get(RETRYABLE_KEY) if isinstance(row, dict) else None,
        "terminal_schema": row.get(SCHEMA_KEY) if isinstance(row, dict) else None,
        "last_error": error["cell"]["value"],
        "last_error_prefix": error["prefix"],
        "last_error_is_stable_code": error["is_stable_code"],
        "attempts": block.get(ATTEMPTS_KEY),
        "max_attempts": block.get(MAX_ATTEMPTS_KEY),
        "dead_letter_depth": depth,
        "idempotency": idempotency,
        "terminal_keys": keys,
        "absent_evidence": absent,
        "note": reason_cell["note"] or error["cell"]["note"],
    }


# ==================== 注入姿势：只验旋钮，不改产品码 ====================

def _tcp_open(value: str, *, connector=None, timeout: float = 1.5) -> bool | None:
    """一扇模型端点在不在听：连得上 True，连不通 False，URL 读不出就 None（说不知道）。"""
    match = re.search(r"^[a-z]+://([^/:]+)(?::(\d+))?", str(value or "").strip())
    if not match:
        return None
    host = match.group(1)
    port = int(match.group(2) or (443 if str(value).startswith("https") else 80))
    probe = connector or _default_tcp_probe
    try:
        return bool(probe(host, port, timeout))
    except Exception:
        return False


def _default_tcp_probe(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def env_witness(names, *, environ=None, container: str = "", runner=None) -> dict:
    """旋钮到底在不在位：能问容器就问容器，问不到就问本进程，两处都问不到就记 absent。"""
    environ = dict(os.environ if environ is None else environ)
    out: dict = {}
    for name in names:
        entry = {"name": name, "source": "", "value": None, "note": ""}
        if container and runner is not None:
            rc, text = runner(container, name)
            if rc == 0:
                entry.update(source="docker exec " + container + " printenv " + name,
                             value=text.strip(), note="")
                out[name] = entry
                continue
            entry["note"] = "容器里问不到（rc=%s），回落本进程 env：%s" % (rc, (text or "").strip()[:120])
        if name in environ:
            entry.update(source="os.environ", value=environ.get(name) or "", note=entry["note"])
        else:
            entry.update(source="absent", value=None,
                         note=entry["note"] or "本进程 env 里没有这一枚旋钮")
        out[name] = entry
    return out


def posture_gate(name: str, env_state: dict, *, environ=None, connector=None,
                 ceiling: int = BUDGET_ARM_CEILING) -> dict:
    """这一枚姿势今天armed不armed：armed 才准问出去，不 armed 就交回命令原文而不是假读数。"""
    posture = POSTURES[name]
    required = list(posture["env_required"])
    environ = dict(os.environ if environ is None else environ)
    if not required:
        return {"posture": name, "armed": True, "reason": posture["note"],
                "witness": {}, "recipe": ""}
    witness = {key: env_state.get(key, {}) for key in required}
    values = {key: str((witness.get(key) or {}).get("value") or "").strip() for key in required}
    present = {key: bool(values.get(key)) for key in required}
    if name == POSTURE_BUDGET:
        raw = values.get("MODEL_CONTEXT_TOKENS") or ""
        try:
            declared = int(raw)
        except ValueError:
            return {"posture": name, "armed": False,
                    "reason": "MODEL_CONTEXT_TOKENS 读不出整数（当前 %r）：这一遍注入不出预算失败" % raw,
                    "witness": witness, "recipe": RECIPE_BUDGET}
        armed = declared < ceiling
        return {"posture": name, "armed": armed,
                "reason": "MODEL_CONTEXT_TOKENS=%d %s 天花板 %d" % (
                    declared, "小于" if armed else "不小于", ceiling),
                "witness": witness, "recipe": "" if armed else RECIPE_BUDGET}
    if not any(present.values()):
        return {"posture": name, "armed": False,
                "reason": "两枚端点旋钮都不在位，指歪无从谈起", "witness": witness,
                "recipe": RECIPE_ENDPOINT}
    if connector is None:
        return {"posture": name, "armed": True,
                "reason": "端点旋钮在位；可达性未验（没给 --probe-tcp，本件不碰 socket）",
                "witness": witness, "recipe": ""}
    reachable = [key for key in required if present[key] and _tcp_open(values[key], connector=connector)]
    if reachable:
        return {"posture": name, "armed": False,
                "reason": "端点仍可达（" + ", ".join(reachable) + "）：这一遍不会注入出连接失败",
                "witness": witness, "recipe": RECIPE_ENDPOINT}
    return {"posture": name, "armed": True,
            "reason": "端点旋钮在位且 tcp 连不通，失败来自产品自己的调用腿", "witness": witness,
            "recipe": ""}


RECIPE_BUDGET = (
    "在 deploy/.env.server 里把 MODEL_CONTEXT_TOKENS 调小（小于 " + str(BUDGET_ARM_CEILING) + "），"
    "然后容器重建（不是镜像重建）："
    "docker compose --env-file deploy/.env.server -f docker-compose.yml "
    "-f deploy/docker-compose.server.yml up -d --force-recreate backend worker scheduler；"
    "跑完记得改回来再 recreate 一次，否则下一班读到的是歪的窗口")
RECIPE_ENDPOINT = (
    "把 worker 进程的 LOCAL_MODEL_BASE_URL 指到一扇没人听的端口（例 http://127.0.0.1:1），"
    "同一条 recreate 命令生效；跑完改回来再 recreate")
WINDOW_RECIPE = (
    "总控开窗那一行（容器内、账号走 env、产物落仓外）："
    "docker exec -e EVAL_USERNAME -e EVAL_PASSWORD enterprise-brain-worker-1 "
    "/app/.venv/bin/python scripts/r545_queue_failure_probe.py "
    "--inject expired --inject cancel --inject budget --expect-rev <主树 HEAD 40 位>")

# ==================== 在册出口：HTTP 会话（读回只走这两扇门） ====================

def no_proxy_opener():
    """空 ProxyHandler = 无视 http_proxy/HTTPS_PROXY（runbook §6：本机代理会劫 127.0.0.1）。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Session:
    """一枚最小 Bearer 会话：与 scripts/eval_transport_ask_v2.py 同一扇门、同一个 token 口径。

    本件不绕鉴权、不伪造 session、不直接调 app.agents.orchestrator —— 「这一枚失败客户读不读得回」
    这句话必须靠真 HTTP 量出来，抄近路就不是这句话了。
    """

    def __init__(self, base_url: str, opener=None, timeout: float = 60.0) -> None:
        self.base = base_url.rstrip("/")
        self.opener = opener or no_proxy_opener()
        self.timeout = float(timeout)
        self.token = ""
        self.polls = 0
        self.blips = 0
        self.relogins = 0

    def login(self, username: str, password: str) -> str:
        body = self._post_json(LOGIN_PATH, {"username": username, "password": password})
        self.token = str(body.get("token") or "")
        if not self.token:
            raise GaugeFailure("login 响应里没有 token 键（缺凭证 != 缺读数，这一遍一枚都不许判绿）")
        return self.token

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    def _request(self, path: str, body=None, method: str = "GET", timeout: float | None = None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data,
                                         headers=self._headers(), method=method)
        return self.opener.open(request, timeout=self.timeout if timeout is None else float(timeout))

    def _post_json(self, path: str, payload: dict) -> dict:
        try:
            with self._request(path, payload, "POST") as resp:
                return json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GaugeFailure("POST " + path + " 没跑成：" + type(exc).__name__ + ": " + str(exc)) from exc

    def poll_status(self, request_id: str, since: int = 0):
        """读一发轮询面：回 (http_status, 原文 bytes, dict 或 None)。非 2xx 是**读不到**，不是**读完了**。"""
        path = self.base + POLL_PATH_FRAGMENT + str(request_id)
        if since:
            path += "?since=" + str(int(since))
        request = urllib.request.Request(path, headers=self._headers(), method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as resp:
                raw = resp.read()
                return int(resp.getcode()), raw, _as_dict(raw)
        except urllib.error.HTTPError as exc:
            self.blips += 1
            return int(exc.code), (exc.read() or b""), None
        except (urllib.error.URLError, OSError) as exc:
            self.blips += 1
            return 0, ("transport: " + type(exc).__name__ + ": " + str(exc)).encode("utf-8"), None

    def ask(self, question: str, session_id: str, idempotency_key: str, lane: str):
        """POST /api/v1/ask 并把那条 SSE 读到关流：回 (事件名清单, queued 载荷或 None, 错误说明)。"""
        payload = {"message": question, "session_id": session_id,
                   "idempotency_key": idempotency_key}
        if lane:
            payload["lane"] = lane
        events: list = []
        queued = None
        try:
            with self._request(ASK_PATH, payload, "POST", timeout=self.timeout) as resp:
                name, data = None, None
                for line in resp:
                    text = line.decode("utf-8", "replace").rstrip("\r\n")
                    if text.startswith("event: "):
                        name = text[7:].strip()
                    elif text.startswith("data: "):
                        try:
                            data = json.loads(text[6:])
                        except json.JSONDecodeError:
                            data = {}
                    elif not text and name:
                        events.append(name)
                        if name == "queued":
                            queued = data if isinstance(data, dict) else {}
                        name, data = None, None
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as exc:
            return events, queued, type(exc).__name__ + ": " + str(exc)
        return events, queued, ""

    def cancel(self, request_id: str, cancel_path: str):
        """走在册那扇 cancel 门（路径由 chat.py 的装饰器派生后拼进来，本件不第二条拼写它）。"""
        try:
            with self._request(cancel_path.format(request_id=request_id), {}, "POST") as resp:
                return int(resp.getcode()), _as_dict(resp.read())
        except urllib.error.HTTPError as exc:
            return int(exc.code), _as_dict(exc.read() or b"")
        except (urllib.error.URLError, OSError) as exc:
            return 0, {"transport": type(exc).__name__ + ": " + str(exc)}

    def stats(self) -> dict:
        try:
            with self._request(STATS_PATH, method="GET") as resp:
                return _as_dict(resp.read()) or {}
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
            return {}


def _as_dict(raw: bytes):
    try:
        body = json.loads((raw or b"").decode("utf-8", "replace") or "null")
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def derived_cancel_path(chat_source: str) -> str:
    """从装饰器现取那扇 cancel 门的路径（找不到就抛：本件不许拼第二套地址）。"""
    route = _route_function(chat_source, "/queue/", tail=CANCEL_PATH_TAIL, origin=CHAT_REL)
    for decorator in route.decorator_list:
        if isinstance(decorator, ast.Call) and decorator.args:
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str):
                return "/api/v1" + path.value
    raise SourceUnreadable("cancel 路由的装饰器读不出路径")


# ==================== Redis 那一腿：只经产品自己的连接，一次都不写 ====================

def queue_handle():
    """产品自己的 connect_reliable_queue()；连不上就交回 (None, 原因)，绝不伪造一本账。"""
    try:
        from app.common.reliable_queue import connect_reliable_queue
    except Exception as exc:
        return None, "产品队列模块 import 不成：" + type(exc).__name__ + ": " + str(exc)
    try:
        return connect_reliable_queue(), ""
    except Exception as exc:
        return None, "队列连不上（REDIS_URL 缺失 / Redis 不通 / 依赖不在）：" + type(exc).__name__ + ": " + str(exc)


def read_failure_ledger(handle, request_id: str) -> dict | None:
    """拿队列自己的 failure() 读那本账：这是判据①点名的落点，本件不复算它。"""
    if handle is None or not request_id:
        return None
    try:
        return handle.failure(request_id)
    except Exception:
        return None


def read_dead_depth(handle) -> int | None:
    if handle is None:
        return None
    try:
        return int(handle.dead_letter_depth())
    except Exception:
        return None


def read_idempotency(handle, key: str, expected_request_id: str) -> dict:
    """幂等键那一格的可定位证据：键名走产品自己的 builder，读不到就说读不到。"""
    if handle is None:
        return {"state": "unavailable", "key": key or None, "maps_to": None,
                "matches_request_id": None, "note": "没有队列连接，幂等账无从可问"}
    builder = getattr(handle, "_idempotency_key", None)
    if not callable(builder):
        return {"state": "unreadable", "key": None, "maps_to": None, "matches_request_id": None,
                "note": "产品侧找不到 _idempotency_key()，本件不抄第二份键形状"}
    if not key:
        return {"state": "absent", "key": None, "maps_to": None, "matches_request_id": None,
                "note": "这一姿势没带幂等键"}
    try:
        redis_key = builder(key)
        mapped = handle.redis.get(redis_key)
    except Exception as exc:
        return {"state": "unreadable", "key": None, "maps_to": None, "matches_request_id": None,
                "note": "幂等键读不成：" + type(exc).__name__ + ": " + str(exc)}
    mapped_text = ""
    if mapped is not None:
        mapped_text = mapped.decode() if isinstance(mapped, bytes) else str(mapped)
    return {"state": "read" if mapped_text else "absent",
            "key": str(redis_key), "maps_to": mapped_text or None,
            "matches_request_id": bool(mapped_text) and mapped_text == expected_request_id,
            "note": "" if mapped_text else "幂等键已过期或压根没写下（TTL 到了就是 absent，不是错）"}

# ==================== 问出去：一次窗（本单不跑它；跑它的权限在总控） ====================

def poll_until_stop(session: Session, request_id: str, stop_words, *, interval: float,
                    deadline: float, stall: float, clock=time.time,
                    sleeper=time.sleep) -> dict:
    """按在册停表词表轮到终态：非 2xx 与解不开都算抖动，绝不算「这一轮结束了」。

    停表词一律用派生出来的那一套（vocab["terminal"]），本文件里没有第二份终态名单。
    """
    started = clock()
    stalled_at = None
    signature = None
    last = {"http_status": 0, "raw": b"", "row": None}
    polls = 0
    blips_before = session.blips
    while True:
        now = clock()
        if now - started >= deadline:
            return {"kind": "deadline", "polls": polls, "final": "", "row": last["row"],
                    "http_status": last["http_status"], "blips": session.blips - blips_before}
        if stalled_at is not None and now >= stalled_at:
            return {"kind": "stalled", "polls": polls, "final": "", "row": last["row"],
                    "http_status": last["http_status"], "blips": session.blips - blips_before}
        status, raw, body = session.poll_status(request_id)
        polls += 1
        last = {"http_status": status, "raw": raw, "row": body}
        if isinstance(body, dict):
            word = str(body.get(STATUS_DICT_KEY) or "")
            block = body.get(FAILURE_FIELD) if isinstance(body.get(FAILURE_FIELD), dict) else {}
            mark = (word, body.get(POSITION_KEY), block.get(ATTEMPTS_KEY))
            if mark != signature:
                signature = mark
                stalled_at = now + stall
            if word in set(stop_words):
                return {"kind": "stopped", "polls": polls, "final": word, "row": body,
                        "http_status": status, "blips": session.blips - blips_before}
        sleeper(interval)


def long_question(base: str, repeat: int) -> str:
    """把请求侧那一问撑长：注入姿势之一，只改**调用方发出去的字**，产品码一字节不动。"""
    filler = "并请逐条列出各部门的毛利率、库存周转、应收账款账龄与现金流变化，"
    return base + filler * max(0, int(repeat))


def run_window(args, vocab: dict, session: Session, handle, *, clock=time.time,
               sleeper=time.sleep) -> dict:
    """按 --inject 的姿势逐枚问出去，每一枚都把**整份回执原文**留下；不 armed 的姿势一字节都不打。"""
    names = sorted({key for posture in POSTURES.values() for key in posture["env_required"]})
    env_state = env_witness(names, container=args.worker_container,
                            runner=(docker_printenv if args.worker_container else None))
    stop_words = list(vocab["terminal"]) or [args.fallback_stop_word]
    cancel_path = args.cancel_path_override or derived_cancel_path(read_source(CHAT_REL, args.repo))
    depth_before = read_dead_depth(handle)
    rows: list = []
    for name in args.inject_list:
        gate = posture_gate(name, env_state, connector=None if not args.probe_tcp else _default_tcp_probe)
        attempt = {"posture": name, "armed": bool(gate["armed"]), "gate_reason": gate["reason"],
                   "recipe": gate["recipe"], "witness": gate["witness"], "note": POSTURES[name]["note"],
                   "side_effects": POSTURES[name]["side_effects"], "idempotency_key": "",
                   "request_id": "", "http_status": 0, "row": None, "raw_sha256": "",
                   "polls": 0, "blips": 0, "stop_kind": "", "ask_error": "", "events": []}
        rows.append(attempt)
        if not gate["armed"]:
            continue
        if name == POSTURE_EXPIRED:
            # 零副作用：问一枚压根没人写过的 request_id，看这扇门到底答什么。
            probe_id = "r545-nonexistent-" + uuid.uuid4().hex[:12]
            status, raw, body = session.poll_status(probe_id)
            attempt.update(request_id=probe_id, http_status=status, row=body,
                           raw_sha256=_sha(raw), stop_kind="single_read", polls=1)
            continue
        idem = "r545-" + name + "-" + uuid.uuid4().hex[:16]
        attempt["idempotency_key"] = idem
        question = args.question or DEFAULT_QUESTION
        if name == POSTURE_BUDGET:
            question = long_question(question, args.budget_repeat)
        events, queued, ask_error = session.ask(question, "r545-" + uuid.uuid4().hex[:8],
                                                idem, args.lane)
        attempt["events"] = events
        attempt["ask_error"] = ask_error
        request_id = str((queued or {}).get("request_id") or "")
        attempt["request_id"] = request_id
        if not request_id:
            attempt["stop_kind"] = "not_queued"
            continue
        if name == POSTURE_CANCEL:
            code, body = session.cancel(request_id, cancel_path)
            attempt["cancel_http_status"] = code
            attempt["cancel_body"] = body
        read = poll_until_stop(session, request_id, stop_words, interval=args.poll_interval,
                               deadline=args.deadline, stall=args.stall, clock=clock, sleeper=sleeper)
        attempt.update(polls=read["polls"], blips=read["blips"], stop_kind=read["kind"],
                       http_status=read["http_status"])
        if read["row"] is not None:
            attempt["row"] = read["row"]
            attempt["raw_sha256"] = _sha(json.dumps(read["row"], ensure_ascii=False).encode("utf-8"))
        attempt["failure_ledger"] = read_failure_ledger(handle, request_id)
        attempt["idempotency"] = read_idempotency(handle, idem, request_id)
    stats_after = session.stats()
    return {
        "asked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "postures": [row["posture"] for row in rows],
        "rows": rows,
        "terminal_words": stop_words,
        "cancel_path": cancel_path,
        "base_url": session.base,
        "lane": args.lane,
        "depth_before": depth_before,
        "depth_after": read_dead_depth(handle),
        "handle_note": args.handle_note,
        "stats_before": args.stats_before,
        "stats_after": stats_after,
        "polls": sum(int(row.get("polls") or 0) for row in rows),
        "blips": session.blips,
        "book": {"polls": sum(int(row.get("polls") or 0) for row in rows),
                 "blips": int(session.blips), "rows": len(rows),
                 "armed": sum(1 for row in rows if row.get("armed"))},
    }


def docker_printenv(container: str, name: str):
    """问容器里那一枚旋钮（只读 printenv）。没有 docker CLI 就交回 rc≠0，由调用方回落。"""
    import subprocess

    try:
        done = subprocess.run(["docker", "exec", container, "printenv", name],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, type(exc).__name__ + ": " + str(exc)
    return int(done.returncode), (done.stdout or done.stderr or "")

# ==================== 判读（九格；纯函数，可离线喂存档） ====================

def _sha(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def _cell(name: str, verdict: str, value, note: str) -> dict:
    return {"cell": name, "verdict": verdict, "value": value, "note": note}


def collect_evidence(head: dict, vocab: dict) -> list:
    """把窗里读回来的每一行，逐枚换算成「这一枚终态的可定位证据」。"""
    out: list = []
    for row in head.get("rows") or []:
        body = row.get("row") if isinstance(row.get("row"), dict) else None
        word = str((body or {}).get(STATUS_DICT_KEY) or "")
        evidence = evidence_from_row(word, body, vocab, depth=head.get("depth_after"),
                                     idempotency=row.get("idempotency"))
        evidence["posture"] = row.get("posture")
        evidence["armed"] = bool(row.get("armed"))
        evidence["gate_reason"] = row.get("gate_reason")
        evidence["status_word"] = word or None
        evidence["stop_kind"] = row.get("stop_kind")
        evidence["request_id"] = row.get("request_id")
        out.append(evidence)
    return out


def build_info_text(path: str) -> str:
    try:
        return Path(path).read_bytes().decode("utf-8", "replace")
    except OSError:
        return ""


def build_info_revision(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip().startswith("revision="):
            return line.split("=", 1)[1].strip()
    return ""


def judge_provenance(head: dict, args) -> dict:
    """容器里那枚 rev 与主树 HEAD 逐字符对上才算开窗条件成立；任何一头读不到就是量不到。"""
    expect = str(args.expect_rev or "").strip()
    stamp = build_info_revision(args.build_info_text)
    if not expect:
        return _cell("provenance", UNMEASURED, {"expect": None, "image": stamp or None},
                     "--expect-rev 没给：本件不许猜镜像是哪一枚")
    if not stamp or not re.fullmatch(r"[0-9a-f]{7,40}", stamp):
        return _cell("provenance", UNMEASURED, {"expect": expect, "image": stamp or None},
                     args.build_info_path + " 读不出 revision=（三条路里这条哑了，既不是落后也不是在位）")
    same = stamp == expect or (len(stamp) >= 7 and expect.startswith(stamp))
    return _cell("provenance", PASS if same else FAIL, {"expect": expect, "image": stamp},
                 "" if same else "镜像里的 rev 与 --expect-rev 不相等：先 "
                 + "docker compose --env-file deploy/.env.server up -d --force-recreate backend worker scheduler，"
                 + "不要 docker compose build backend")


def judge_vocabulary(head: dict, vocab: dict) -> dict:
    """词表这格判的是「派生出来的一致性」，不是「有没有凑够五枚」。"""
    value = {"terminal": vocab["terminal"], "non_terminal": vocab["non_terminal"],
             "queue_written": vocab["queue_written"], "route_only": vocab["route_only"],
             "by_route": vocab["by_route"], "blind_spots": vocab["blind_spots"],
             "sixth_terminal_named": vocab["sixth_terminal_named"],
             "unreadable": vocab["unreadable"], "sites": vocab["sites"],
             "prose_counts": vocab["prose_counts"], "stale_prose": vocab["stale_prose"]}
    if vocab["drift"]:
        return _cell("vocabulary", FAIL, value, "；".join(vocab["drift"]))
    if not vocab["terminal"]:
        return _cell("vocabulary", UNMEASURED, value, "词表一张脸都没读到，本件没有名单可用")
    notes = []
    if vocab["unreadable"]:
        notes.append("分档那张脸是量具停表顶的（" + "; ".join(vocab["unreadable"]) + "）")
    if vocab["stale_prose"]:
        # 散文不是契约：这一处只如实记一笔，改它得走 scripts/ 的写域（不在本单），故不判红。
        notes.append("在册量具纸面还写着「%s 枚终态」，派生出来是 %d 枚——转出项，不在本单写域"
                     % ("/".join(str(count) for count in vocab["stale_prose"]), len(vocab["terminal"])))
    return _cell("vocabulary", PASS, value, "；".join(notes))


def _armed_observed(evidence: list, words=None) -> list:
    picked = []
    for item in evidence:
        if not item["armed"] or not item["observed"]:
            continue
        if words is not None and item["status_word"] not in words:
            continue
        picked.append(item)
    return picked


def judge_failure_reason(head: dict, evidence: list, vocab: dict) -> dict:
    """队列判定的失败（dead / failed）必须带一枚读得出的原因码；调用方自己按的 cancel 单列。"""
    rows = _armed_observed(evidence, FAILURE_FAMILY)
    if not rows:
        return _cell("failure_reason", UNMEASURED,
                     {"observed_failure_rows": 0, "not_armed": [item["posture"] for item in evidence
                                                                 if not item["armed"]]},
                     "这一遍没量到任何队列判定的失败终态：开关没翻、姿势没 armed、或压根没入队。"
                     + "这是量不到，不是干净。")
    silent = [item for item in rows
              if item["terminal"] != "cancelled" and not item["reason_code_field"]
              and not item["last_error"]]
    not_required = [item for item in rows if item["terminal"] == "cancelled"
                    and not item["last_error"]]
    value = {"rows": [{k: item.get(k) for k in ("posture", "terminal", "status_word", "reason_code_field",
                                                "reason_code", "last_error", "last_error_prefix",
                                                "attempts", "max_attempts")} for item in rows],
             "silent": [item["posture"] for item in silent],
             "cancel_without_reason": [item["posture"] for item in not_required],
             "discard_prefix": vocab["discard_prefix"]}
    if silent:
        return _cell("failure_reason", FAIL, value,
                     "这一枚失败终态交不出原因码字段，failure.last_error 也是 None："
                     + ", ".join(item["posture"] for item in silent))
    return _cell("failure_reason", PASS, value,
                 "cancelled 那一族没走丢弃支时按契约就是状态词自己说话（记 None，不折成 0）"
                 if not_required else "")


def judge_dead_keys(head: dict, evidence: list, vocab: dict) -> dict:
    """死终态那一格的六个键逐枚表态（R585 交的可读面，本件只验它今天真吐字了）。"""
    rows = _armed_observed(evidence, (vocab["dead_status"],))
    if not rows:
        return _cell("dead_keys", UNMEASURED, {"dead_rows": 0, "expected_keys": vocab["dead_readout_keys"]},
                     "这一遍没有一枚 dead 可读：死终态的原因码没被量过。")
    problems: list = []
    per_row: list = []
    for item in rows:
        body = item.get("terminal_keys", {}).get("cells", {})
        schema = item.get("terminal_schema")
        state = (body.get(STATE_KEY) or {}).get("value") if STATE_KEY in body else None
        reason = item.get("reason_code")
        entry = {"posture": item["posture"], "terminal_schema": schema, "terminal_state": state,
                 "reason": reason, "retryable": item.get("retryable"),
                 "reason_is_stable_code": reason in set(vocab["stable_codes"]),
                 "keys": {key: cell["speaks"] for key, cell in body.items()}}
        if schema != vocab["dead_schema"]:
            problems.append("terminal_schema=%r 不等于派生自代码的 %r" % (schema, vocab["dead_schema"]))
        if state != vocab["dead_status"]:
            problems.append("terminal_state=%r 没逐字回显状态键上那枚词" % state)
        if not reason:
            problems.append("reason 那一格说不出话（None 就是 None，不折成空串）")
        elif entry["reason_is_stable_code"] is False:
            problems.append("reason=%r 不在 ErrorEnvelope.code 那枚在册枚举里" % reason)
        if entry["retryable"] is None:
            entry["retryable_note"] = "这一行落在 R585 之前或账本读不到：说「读不出」，不拿 False 冒充「不可重试」"
        per_row.append(entry)
    return _cell("dead_keys", FAIL if problems else PASS,
                 {"dead_rows": len(rows), "per_row": per_row, "problems": problems,
                  "stable_code_count": len(vocab["stable_codes"])},
                 "; ".join(problems))


def judge_retry_budget(head: dict, evidence: list, vocab: dict) -> dict:
    """重试计数不许越界；判定不可重试的那一枚不许占名额（R81/R448 那两条语义在这里量真机）。"""
    rows = _armed_observed(evidence)
    counters = [{"posture": item["posture"], "terminal": item["terminal"],
                 "attempts": item.get("attempts"), "max_attempts": item.get("max_attempts"),
                 "retryable": item.get("retryable")} for item in rows]
    if not counters:
        return _cell("retry_budget", UNMEASURED, {"rows": 0}, "没有任何一行带得出 attempts 读数。")
    problems = []
    for entry in counters:
        attempts, ceiling = entry["attempts"], entry["max_attempts"]
        if not isinstance(attempts, int) or not isinstance(ceiling, int):
            problems.append("%s 那一行的 attempts/max_attempts 读不出（None 不折成 0）" % entry["posture"])
        elif attempts > ceiling:
            problems.append("attempts=%d 越过了 max_attempts=%d" % (attempts, ceiling))
    dead = [entry for entry in counters if entry["terminal"] == vocab["dead_status"]]
    if dead:
        verdicts = {entry["retryable"] for entry in dead}
        if False in verdicts and True in verdicts:
            problems.append("同一遍里两枚 dead 的终局判定没分开：dead_verdict 那笔账读不出")
        for entry in dead:
            if entry["retryable"] is False and isinstance(entry["attempts"], int) \
                    and isinstance(entry["max_attempts"], int) and entry["attempts"] >= entry["max_attempts"]:
                entry["note"] = "名额恰好也用完了：这一枚两种成因在数字上长得一样，只有 dead_verdict 分得开"
    return _cell("retry_budget", FAIL if problems else PASS,
                 {"rows": counters, "dead_rows": len(dead), "problems": problems},
                 "; ".join(problems))


def judge_dead_depth(head: dict, evidence: list, vocab: dict) -> dict:
    """死信深度现读服务端 LLEN（走产品自己的 dead_letter_depth()）；差值要和这一遍真落 dead 的行数对得上。"""
    before, after = head.get("depth_before"), head.get("depth_after")
    if before is None or after is None:
        return _cell("dead_letter_depth", UNMEASURED, {"before": before, "after": after},
                     "没有 Redis 那一腿（或 LLEN 读不出）：深度这格量不到。" + str(head.get("handle_note") or ""))
    rows = _armed_observed(evidence, (vocab["dead_status"],))
    if not rows:
        return _cell("dead_letter_depth", UNMEASURED, {"before": before, "after": after},
                     "这一遍没有一枚 dead，深度差无从谈起（盘面值只是 " + str(after) + "）。")
    grew = int(after) - int(before)
    value = {"before": before, "after": after, "delta": grew, "dead_rows_this_run": len(rows),
             "key_source": "ReliableQueue.dead_key + LLEN（产品自己的 dead_letter_depth()）"}
    if grew < len(rows):
        return _cell("dead_letter_depth", FAIL, value,
                     "落了 %d 枚 dead 而死信列表只长了 %d：有一枚没进死信账" % (len(rows), grew))
    return _cell("dead_letter_depth", PASS, value, "")


def judge_idempotency(head: dict, evidence: list) -> dict:
    """幂等键生效 = 那本账上确有这一枚键，且它指向的就是这一枚 request_id。"""
    rows = [item for item in evidence if item["armed"] and item.get("idempotency")]
    if not rows:
        return _cell("idempotency", UNMEASURED, {"rows": 0},
                     "这一遍没带幂等键出去（或没有队列连接可问那本账）。")
    problems, per_row = [], []
    for item in rows:
        block = item["idempotency"]
        per_row.append({"posture": item["posture"], "state": block.get("state"),
                        "key": block.get("key"), "maps_to": block.get("maps_to"),
                        "request_id": item.get("request_id") or "",
                        "matches": block.get("matches_request_id"),
                        "note": block.get("note")})
        if block.get("state") == "read" and not block.get("matches_request_id"):
            problems.append("%s：幂等键指向 %r，不是这一枚 request_id"
                            % (item["posture"], block.get("maps_to")))
        elif block.get("state") == "absent":
            problems.append("%s：在册 enqueue 之后幂等键读不到（absent 不是过期就是没写）" % item["posture"])
        elif block.get("state") in ("unreadable", "unavailable"):
            problems.append("%s：幂等账读不成 —— %s" % (item["posture"], block.get("note")))
    return _cell("idempotency", FAIL if problems else PASS, {"rows": per_row,
                                                             "key_builder": "ReliableQueue._idempotency_key()"},
                 "; ".join(problems))


def judge_terminal_keys(head: dict, evidence: list, vocab: dict) -> dict:
    """判据②那四枚键逐枚说「读到了 / 这一行说不出」；成功终态说不出就是假话。"""
    rows = _armed_observed(evidence)
    if not rows:
        return _cell("terminal_keys", UNMEASURED, {"asked": list(REQUIRED_TERMINAL_KEYS), "rows": 0},
                     "这一遍一行都没读回来：四枚键谁都没被问出口。")
    problems, per_row = [], []
    for item in rows:
        cells = item["terminal_keys"]["cells"]
        verdicts = {key: (cell["speaks"], cell["value"]) for key, cell in cells.items()}
        per_row.append({"posture": item["posture"], "terminal": item["terminal"],
                        "verdicts": {key: value[0] for key, value in verdicts.items()},
                        "values": {key: value[1] for key, value in verdicts.items()},
                        "not_derivable": item["terminal_keys"]["unreadable_from_code"]})
        if item["terminal"] in vocab["success_states"]:
            for key, (speaks, _) in verdicts.items():
                if speaks != SPEAKS_READ:
                    problems.append("%s 是成功终态却交不出 %s：结构化终态那格在骗人" % (item["terminal"], key))
        for key, (speaks, value) in verdicts.items():
            if speaks == SPEAKS_CANNOT and value is not None:
                problems.append("%s 记成说不出话却带着值 %r" % (key, value))
    return _cell("terminal_keys", FAIL if problems else PASS,
                 {"asked": list(REQUIRED_TERMINAL_KEYS), "rows": per_row, "problems": problems,
                  "terminal_readout_keys_from_code": vocab["terminal_readout_keys"]},
                 "; ".join(problems))


def resolve_in_row(row, path: str):
    """按 absent 清单那种类 jsonpath 逐段走一行读数；走不通就是 KeyError（缺格 != 值为零）。"""
    current = row
    for segment in str(path).split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(path)
        current = current[segment]
    return current


def judge_none_is_none(head: dict, evidence: list) -> dict:
    """自证那一格：登记成「说不出」的格子，原文里必须真的没有值；折成 0/[]/空串当场红。"""
    folded, absent_total = [], 0
    for item in evidence:
        if not item["armed"]:
            continue
        body = item.get("raw_row") if isinstance(item.get("raw_row"), dict) else None
        cells = dict(item["terminal_keys"]["cells"])
        cells["reason_code_field"] = {"value": item["reason_code_field"], "speaks": item["reason_code_field_verdict"],
                                      "absent_path": "reason_code_field"}
        for name, cell in cells.items():
            if cell.get("speaks") != SPEAKS_CANNOT:
                continue
            absent_total += 1
            if cell.get("value") is not None:
                folded.append({"posture": item["posture"], "key": name,
                               "value": cell.get("value"), "why": "登记为说不出却带着值"})
                continue
            if body is None:
                continue
            try:
                observed = resolve_in_row(body, cell.get("absent_path") or name)
            except KeyError:
                continue
            if observed in (0, "", [], {}):
                folded.append({"posture": item["posture"], "key": name, "value": observed,
                               "why": "原文里躺着一枚折算出来的零，而本件说这一格说不出"})
    if not evidence:
        return _cell("none_is_none", UNMEASURED, {"absent_cells": 0}, "这一遍什么也没读到，自证无从做起。")
    value = {"absent_cells": absent_total, "folded": folded,
             "sentinel_free": not any(str(item.get("last_error")) == "<no-bytes-emitted>" for item in evidence)}
    return _cell("none_is_none", FAIL if folded else PASS, value,
                 "; ".join("%s/%s" % (row["posture"], row["key"]) for row in folded))


def judge(head: dict, vocab: dict, args=None) -> dict:
    """九格一起判，返回可原样落进 report.json 的那份账。"""
    evidence = collect_evidence(head, vocab)
    for row, item in zip(head.get("rows") or [], evidence):
        item["raw_row"] = row.get("row")
    head["evidence"] = evidence
    cells = [judge_provenance(head, args), judge_vocabulary(head, vocab),
             judge_failure_reason(head, evidence, vocab),
             judge_dead_keys(head, evidence, vocab),
             judge_retry_budget(head, evidence, vocab),
             judge_dead_depth(head, evidence, vocab),
             judge_idempotency(head, evidence),
             judge_terminal_keys(head, evidence, vocab),
             judge_none_is_none(head, evidence)]
    return {"order": list(CELLS), "cells": {cell["cell"]: cell for cell in cells},
            "rc": overall(cells)}


def overall(cells: list) -> int:
    """退出码：先判量不到（2 永远不是通过），再判 FAIL（1），才轮到 0。"""
    verdicts = [cell["verdict"] for cell in cells]
    if UNMEASURED in verdicts:
        return 2
    if FAIL in verdicts:
        return 1
    return 0

# ==================== 落盘（判据③：产物一律在仓外） ====================

def default_out_dir(now=None) -> Path:
    return Path(tempfile.gettempdir()) / ("r545-" + time.strftime("%Y-%m-%d", time.localtime(now)))


def is_inside_repo(path, repo: Path = ROOT) -> bool:
    target = Path(path).resolve()
    try:
        target.relative_to(Path(repo).resolve())
    except ValueError:
        return False
    return True


def resolve_out_dir(raw: str, repo: Path = ROOT) -> Path:
    """--out 落在仓内就当场拒：本件的产物是证据件，不是仓库的格子。"""
    out = Path(raw).expanduser() if str(raw or "").strip() else default_out_dir()
    if is_inside_repo(out, repo):
        raise GaugeFailure("产物目录 " + str(out) + " 落在仓库内："
                           + "这一单的写域只有 scripts/tests/docs 三处，证据件必须落仓外（%TEMP% 或 --out）")
    return out


def write_artifact(out_dir: Path, head: dict, report: dict, vocab: dict) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows_dir = out / "rows"
    rows_dir.mkdir(parents=True, exist_ok=True)
    stored = []
    for index, row in enumerate(head.get("rows") or [], start=1):
        body = row.get("row")
        word = row.get("status_word") or ((body or {}).get(STATUS_DICT_KEY)
                                          if isinstance(body, dict) else "")
        name = "%02d-%s-%s.json" % (index, row.get("posture") or "row", word or "unreadable")
        payload = json.dumps(body, ensure_ascii=False, indent=2) if body is not None else "null\n"
        (rows_dir / name).write_text(payload, encoding="utf-8")
        stored.append({"index": index, "posture": row.get("posture"), "file": name,
                       "sha256": _sha(payload.encode("utf-8")), "bytes": len(payload.encode("utf-8"))})
    snapshot = dict(head)
    snapshot["vocab"] = vocab
    (out / "head.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    (out / "rows.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                            for row in (head.get("rows") or [])), encoding="utf-8")
    (out / "report.txt").write_text("\n".join(render(report)) + "\n", encoding="utf-8")
    return {"out_dir": str(out), "stored_rows": stored}


def load_artifact(raw) -> dict:
    """读回一份存档：读不出就抛，绝不返回一份空账冒充「那一遍很干净」。"""
    path = Path(raw) / "head.json"
    if not path.is_file():
        raise GaugeFailure("存档里没有 head.json：" + str(path))
    try:
        head = json.loads(path.read_bytes().decode("utf-8"))
    except ValueError as exc:
        raise GaugeFailure("head.json 解不开：" + str(exc)) from exc
    if not isinstance(head, dict) or "rows" not in head:
        raise GaugeFailure("存档里的 head.json 不是本件写的那本账（缺 rows）")
    return head


# ==================== 输出 ====================

def render(report: dict) -> list:
    lines = ["[R545] 队列失败终态量具 —— 九格读数（每一格只有 PASS/FAIL/UNMEASURED 三种说法）"]
    for name in report["order"]:
        cell = report["cells"][name]
        lines.append("  %-18s %-10s %s" % (name, cell["verdict"], cell["note"] or ""))
        compact = json.dumps(cell["value"], ensure_ascii=False, default=str)
        if len(compact) > 900:
            compact = compact[:900] + "...(截断，原文在 report.json)"
        lines.append("      value=" + compact)
    lines.append("[R545] rc=%d（0 全 PASS 且真看到失败带原因码 / 1 至少一格 FAIL / 2 至少一格量不到）"
                 % report["rc"])
    return lines


def build_vocab(args) -> dict:
    text = None
    if args.contract_from:
        text = Path(args.contract_from).expanduser().read_bytes().decode("utf-8", "replace")
    return derive_vocabulary(repo=Path(args.repo) if args.repo else None, contract_text=text)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="r545_queue_failure_probe.py",
        description="R545：队列道失败终态与原因码的真机量具（容器内那一遍由总控执行；本件不改产品码）",
        epilog="退出码：0 = 九格全 PASS 且这一遍真读到至少一枚带原因码的失败终态；"
               "1 = 至少一格 FAIL（词表漂了、原因码读不出、或把缺证折成了零）；"
               "2 = 至少一格 UNMEASURED 或量具自己没跑成（缺凭证 / Redis 那一腿不通 / 契约读不到 / "
               "产物目录落在仓内）。2 永远不是通过：REPORT_LANE_VIA_QUEUE 没翻、窗没开，正确的结果就是 2。"
               "注入姿势只四枚（expired/cancel/budget/endpoint），全部经请求侧或 worker 进程的在册旋钮，"
               "一字节都不改 app/**。产物默认落 %TEMP%\\r545-<date>，--out 指到仓内当场拒。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--inject", action="append", default=[], choices=sorted(POSTURES),
                        help="注入姿势，可重复；缺省 expired（零副作用那一枚）")
    parser.add_argument("--base-url", default=os.getenv("EVAL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--username", default=os.getenv("EVAL_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("EVAL_PASSWORD", ""))
    parser.add_argument("--lane", default="report", help="载荷声明的档位；report 加开关才入队")
    parser.add_argument("--question", default="", help="问哪一句（缺省用内置那句报告体问法）")
    parser.add_argument("--budget-repeat", type=int, default=400,
                        help="budget 姿势把 prompt 撑长的重复次数（只改调用方发出去的字）")
    parser.add_argument("--deadline", type=float, default=900.0)
    parser.add_argument("--stall", type=float, default=300.0,
                        help="载荷不再变化多久就停表（与在册量具同一族口径，别拿它当失败）")
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--expect-rev", default="", help="主树 HEAD 的 40 位；不给就没开窗条件")
    parser.add_argument("--build-info", default="", help="缺省先读 /app/BUILD_INFO 再读仓内那份")
    parser.add_argument("--worker-container", default="",
                        help="给了就用 docker exec printenv 问旋钮，不给只问本进程 env")
    parser.add_argument("--probe-tcp", action="store_true",
                        help="budget/endpoint 姿势要不要真去 tcp 连一下端点（默认不连：不 armed 就交回命令原文）")
    parser.add_argument("--contract-from", default="",
                        help="镜像不带 docs/：把契约那一节另带一份副本进来才量得了分档那张脸")
    parser.add_argument("--repo", default="", help="派生面的根（缺省＝本脚本所在仓库）")
    # argparse 会对每一枚 help= 跑 %-插值：字面 % 必须写成 %%，否则 --help 当场炸（本单一手踩过）。
    parser.add_argument("--out", default="", help="产物目录，缺省 %%TEMP%%\\r545-<date>；落仓内当场拒")
    parser.add_argument("--offline", default="", help="只重放已存的那一遍，一次都不问出去")
    parser.add_argument("--print-recipe", action="store_true", help="只交命令原文，不问任何东西、不开容器")
    args = parser.parse_args(argv)
    args.inject_list = list(dict.fromkeys(args.inject or [POSTURE_EXPIRED]))
    args.fallback_stop_word = ""
    args.cancel_path_override = ""
    args.build_info_path = args.build_info or next(
        (str(path) for path in (Path("/app/BUILD_INFO"), ROOT / "BUILD_INFO") if Path(path).is_file()),
        "/app/BUILD_INFO")
    args.build_info_text = build_info_text(args.build_info_path)
    args.handle_note = ""
    args.stats_before = {}
    args.out_dir = None
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.print_recipe:
        print(WINDOW_RECIPE)
        print("budget：" + RECIPE_BUDGET)
        print("endpoint：" + RECIPE_ENDPOINT)
        return 0
    try:
        # 仓外闸放在这里而不是 argparse 里：拒绝要说人话（rc=2 一行），不许抛栈给总控看。
        args.out_dir = resolve_out_dir(args.out, Path(args.repo) if args.repo else ROOT)
    except GaugeFailure as exc:
        print("[R545] rc=2 " + str(exc), flush=True)
        return 2
    try:
        vocab = build_vocab(args)
    except (SourceUnreadable, OSError) as exc:
        print("[R545] rc=2 词表派生不出来：" + str(exc) + "（派生失败就是量不到，绝不退回一份手抄名单）",
              flush=True)
        return 2
    if args.offline:
        try:
            head = load_artifact(args.offline)
        except GaugeFailure as exc:
            print("[R545] rc=2 " + str(exc), flush=True)
            return 2
        stored = head.get("vocab") or vocab
        print("[R545] 离线重放：下面九格读的是那一遍存下的原文与那一遍派生出的词表，"
              "不是此刻容器里的读数——拿它当容器凭据就是把纸面形状当成容器形状", flush=True)
        report = judge(head, stored, args)
        for line in render(report):
            print(line)
        return int(report["rc"])
    if not args.username or not args.password:
        print("[R545] rc=2 量具没跑成：EVAL_USERNAME/EVAL_PASSWORD 没给（缺凭证 != 缺读数，"
              "这一遍一枚都没问，绝不交任何一格的数）", flush=True)
        return 2
    handle, note = queue_handle()
    args.handle_note = note
    try:
        session = Session(args.base_url, timeout=args.timeout)
        session.login(args.username, args.password)
        args.stats_before = session.stats()
        head = run_window(args, vocab, session, handle)
    except (GaugeFailure, SourceUnreadable) as exc:
        print("[R545] rc=2 量具没跑成：" + str(exc), flush=True)
        return 2
    except Exception as exc:  # 量具自己炸了 = 2，绝不是「没报错所以干净」
        print("[R545] rc=2 量具没跑成：" + type(exc).__name__ + ": " + str(exc), flush=True)
        return 2
    report = judge(head, vocab, args)
    try:
        written = write_artifact(args.out_dir, head, report, vocab)
    except OSError as exc:
        print("[R545] rc=2 产物写不成：" + str(exc), flush=True)
        return 2
    print("[R545] 产物目录（仓外）：" + written["out_dir"]
          + "；Redis 那一腿：" + (note or "已连（只读 ping/GET/LLEN）"), flush=True)
    for line in render(report):
        print(line)
    return int(report["rc"])


if __name__ == "__main__":
    sys.exit(main())