#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R218 跑分窗「开关」离线预演（单号 R218，判据 ② 的三格；09-24，基点 dea3ee4）。

R107 那件（``scripts/rehearse_eval_window.py``）预演的是**窗口形状**：105 题各会被什么卡住。
本件预演的是**窗口要翻的那几个开关**：今晚 run7 一开 2.5-4.7 h，凡是离线能抓的失败，
一律不许留到窗里。三格 = 本单判据 ② 的三格：

  D 格   ``REPORT_LANE_VIA_QUEUE`` 从默认 off 翻 on：报告档入队/轮询/取回里离线判得动的部分，
         加两族轮询停表（前端 ``QUEUE_SETTLED`` / 适配器 ``_poll_queue``）收不收得住
         后端答得出的**每一个**终态。
  C 格   答案缓存「命中腿」在采集器里可不可观测：拿产品自己的帧构造器造命中道字节流，
         喂给真适配器 ``_consume``，读第二遍那一发是不是命中腿。
  A② 格  量具自校准：受控纠正轮与真断流轮各过一遍 R181/R215 那把帧尺，
         证明窗里那把尺子今天有牙，而不是到窗里第一次用。

三条硬规矩继承 R107（那枚文件 8-16 行）：
  1. 只读：零模型调用、零网络、零连库、零起服务、零写盘 —— import 任何业务代码之前先把三条
     出站 socket 路径换成会抛的桩（``_block_network``）。
  2. 不发明口径：开关判定调产品谓词本体（``chat._report_lane_via_queue_enabled`` /
     ``chat._queue_lane``），命中腿与帧形状调适配器函数本体（``_consume`` / ``_frame_readings`` /
     ``_frame_verdict``），帧字节由产品构造器现造（``text_sse_frame`` / ``sse_event``）。
     本件只新增「读法」，不另立第二把尺。
  3. 判据 ③：离线确实测不动的（真 Redis、真容器、真模型、真 worker）一律落成显式
     ``NOT_COVERED_OFFLINE`` + 一句原因，汇进 ``must_judge_in_window``。**严禁为了让预演变绿而
     放宽真实判据** —— 本件任何一格的红色都不许靠改产品代码消掉。

用法（仓库根，项目 venv 解释器）：
    python scripts/r218_switch_rehearsal.py            # 三格读数 + 窗内必须现场判清单
    python scripts/r218_switch_rehearsal.py --json     # 机器可读（仍只走 stdout）
    python scripts/rehearse_eval_window.py --switches  # 从 R107 那件里同一扇门

退出码：0 = 三格无红（红 = 离线判出「翻开关/量具今天就会坏」）；1 = 至少一格红。
🔴 退出码读的是**可测性判定**，不是分数：0 不等于任何一格已翻绿（本单判据 ⑥）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import socket
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CELL_D = "D-报告档翻开关与轮询停表"
CELL_C = "C-缓存命中腿可观测性"
CELL_A2 = "A②-帧账量具自校准"

#: 题数与「窗口形状」同源：R107 那件读的就是这一份夹具（scripts/rehearse_eval_window.py:39）。
#: 🔴 现读不手抄 —— 上一班那句 900 × 105 里的 105 是抄来的，夹具一改就成了假数。
FIXTURE_REL = Path("tests") / "fixtures" / "business_evaluation_100.jsonl"

GREEN = "MEASURED_GREEN"
RED = "RED"
NOT_COVERED = "NOT_COVERED_OFFLINE"

#: --- 以下每个常数都是本树某一行代码的抄本，出处标在后面 -------------------------------
#:
#: ``GET /api/v1/queue/status/{id}`` 可能答出的**终态**（终态 = 产品自己承认「这一轮再也读不
#: 回 done」）。逐枚出处：
#:   done        app/common/reliable_queue.py:201（ack 写 done）
#:   cancelled   同文件 :271（cancel 走已出队那一支）
#:   failed      同文件 :170（reserve 读到坏载荷）
#:   dead        同文件 :250（fail_or_retry 重试用完、或 retryable=False 直接落死信），并且
#:               deploy/queue_worker.py:206 明写 ``terminal_status == "dead"`` —— worker 自己
#:               叫它终态，本件不替它改口。
#:   expired     app/api/v1/chat.py:3836（状态键读不到时 API 现造的那一枚）
#: 在途态（queued :149 / processing :177 / cancel_requested :273）不在上面这张表里，理由是它们
#: 有代码写下的下一步迁移；本件用 ``_CITATIONS`` 逐条复验，抄本一漂就红。
FINAL_QUEUE_STATUSES = ("done", "cancelled", "failed", "dead", "expired")
INFLIGHT_QUEUE_STATUSES = ("queued", "processing", "cancel_requested")

#: 出处逐条复验：(相对路径, 必须能在该文件里命中的字面, 这一格担保的读法)。
#: 摘掉任何一条 = 本件的判定依据不再成立，判据跟着红，不许继续报绿。
_CITATIONS: tuple[tuple[str, str, str], ...] = (
    ("app/common/reliable_queue.py",
     'self.redis.set(self._status_key(request_id), "dead")', "dead 是后端真会答出的状态"),
    ("deploy/queue_worker.py", 'terminal_status == "dead"', "产品自己把 dead 叫终态"),
    ("app/api/v1/chat.py", '"status": "expired"', "expired 由 API 现造"),
    ("app/api/v1/chat.py", 'REPORT_LANE_QUEUE_ENV = "REPORT_LANE_VIA_QUEUE"',
     "报告档开关的 env 字面"),
    ("frontend/src/components/ChatPanel.vue", "entry.timer = setInterval(tick, QUEUE_POLL_MS)",
     "前端轮询无截止：只有名单命中才停表"),
    ("scripts/eval_transport_ask_v2.py", "deadline = time.time() + QUEUE_POLL_SECONDS",
     "适配器轮询有截止，漏停的代价是整段 deadline"),
)


def _block_network() -> None:
    """三条出站路径换成会抛的桩，然后才 import 业务代码（R107 同款纪律，同款理由）。"""

    def _boom(*_args, **_kwargs):
        raise AssertionError("R218 预演件禁止任何网络动作")

    socket.create_connection = _boom
    socket.getaddrinfo = _boom
    socket.socket.connect = _boom


#: 闸门装在什么时候：
#: 🔴 09-24 实测教训 —— 在 pytest 收集期无条件把 socket.create_connection / getaddrinfo /
#: socket.socket.connect 换成会抛的桩，会把同会话里 ``tests/test_r37_report_lane_enqueue.py``
#: 的 11 枚用例全打死（那批用例要走回环上的假 redis 与 TestClient）。所以正确的分工是：
#: **作为脚本跑时本件自拦；作为模块被 import 时让位给 conftest** —— tests/conftest.py 的 R56
#: 端口闸门本来就比这枚桩严格（它按目标端口识别、逐用例记 attempt、收尾再判一次红），
#: 本件不该在同一条进程里叠第二把更钝的刀。
def _conftest_gate_loaded() -> bool:
    """pytest 的 R56 端口闸门在不在本进程里：在就让位，不在就必须自己拦。

    判据用「conftest 模块带着 BLOCKED_MODEL_PORT_ATTEMPTS 进没进 sys.modules」，不用
    ``PYTEST_CURRENT_TEST`` 之类环境变量 —— 那只覆盖用例执行期，收集期 import app 同样危险。
    """
    for name in ("tests.conftest", "conftest"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "BLOCKED_MODEL_PORT_ATTEMPTS"):
            return True
    return False


#: 拦没拦要能被读出来（反证钉读这一格）：形状与 scripts/rehearse_eval_window.py 同一份。
EGRESS_GUARDED = False

if not _conftest_gate_loaded():
    # 作为脚本单跑、或被非 pytest 的调用方 import（如 rehearse_eval_window.py --switches），
    # 闸门都由本件装：否则一次 import app.api.v1.chat 就能往宿主 Postgres 探活、
    # 甚至「首次连接时建表」——那是本单禁止的改环境动作。
    _block_network()
    EGRESS_GUARDED = True


def egress_guard_state() -> dict:
    """本件此刻拦没拦、为什么这么选：给反证钉读的出口，不改变任何行为。"""
    return {"guarded": EGRESS_GUARDED,
            "conftest_gate_loaded": _conftest_gate_loaded(),
            "stubbed": getattr(socket.create_connection, "__name__", "") == "_boom"}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: --- Chroma 写回卫生（09-24 16:05 本树亲测的教训）------------------------------------
#: ``app/api/v1/chat.py`` 是模块级 ``DocumentRetriever()``：一 import 就
#: ``chromadb.PersistentClient(path=<仓库根>/chroma_db)``，而那枚文件是**被 git 跟踪的
#: 生产向量库**（1008 枚向量）。R134 的改道钉子（tests/_chroma_sandbox.py）只在 pytest
#: 生命周期内由 conftest 装 —— 脚本侧（``python -c`` / ``scripts/**``）没人装，于是任何
#: 离线预演 import 一次就把 chroma.sqlite3 就地写脏（实测「尺寸一字不变而 mtime 变了」，
#: 与本件 D 格同款形状：一个只在某条生命周期里生效的守卫，出了那条生命周期就是洞）。
#: 所以本件在 import 任何业务代码之前，自己装**依赖级那半**（``pin_retriever_default=
#: False``：仓库根装 app 级那半等于重开 R70「宿主 .env 一个字都不许进进程」的口子）。
#: 🔴 样本一律落在 %TEMP% 空沙箱（0 枚向量），永不碰 1008 枚生产库；装不上钉子就当场抛，
#: 不许静默跳过 —— 静默跳过等于把这条脏写留给下一个跑预演的人。
from tests import _chroma_sandbox as chroma_sandbox_pins  # noqa: E402

_CHROMA_SNAPSHOT_BEFORE = chroma_sandbox_pins._chroma_store_snapshot()
if not chroma_sandbox_pins.PINS_INSTALLED:
    # pytest 里 conftest 已经把两半都装好了；这里再装一次会撞上幂等分支的交叉断言，
    # 所以只在「作为脚本单独跑」这条路上装依赖级那半。
    chroma_sandbox_pins.install_chroma_sandbox_pins(pin_retriever_default=False)


def chroma_hygiene() -> dict:
    """这一趟预演有没有碰被跟踪的生产向量库：调用数 / 改道数 / 写回违例 / 沙箱向量数。"""
    calls = list(chroma_sandbox_pins.CHROMA_PERSISTENT_CLIENT_CALLS)
    # 判据与 tests/conftest:561 同一枚：落点 != 请求路径 才算「改道出工作树」。
    redirected = [c for c in calls if c["target"] != c["requested"]]
    violations = chroma_sandbox_pins._chroma_writeback_violations(
        _CHROMA_SNAPSHOT_BEFORE)
    sandbox = chroma_sandbox_pins.CHROMA_SANDBOX
    vectors: object = 0
    if os.path.isdir(sandbox):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=sandbox)
            names = [c.name if hasattr(c, "name") else str(c)
                     for c in (client.list_collections() or [])]
            vectors = sum(len(client.get_collection(name).peek(0).get("ids") or [])
                          for name in names)
        except Exception as exc:  # 沙箱读不动只影响这一格读数，不勾生产库违例
            vectors = f"unreadable:{type(exc).__name__}"
    return {"persistent_client_calls": len(calls), "redirected_out_of_tree": len(redirected),
            "redirect_ledger": [{k: v for k, v in c.items() if k != "test"} for c in calls],
            "sandbox_root": chroma_sandbox_pins.CHROMA_SANDBOX_ROOT,
            "sandbox_collections_and_vectors": vectors,
            "tracked_store_violations": violations}


def rehearsal_inputs(root: Path = REPO_ROOT) -> list:
    """本件三格会读到的仓内文件清单（反证钉拿它搭临时对照根，抄漏一枚就假红）。

    清单从 _CITATIONS 与三格的读取点长出来，不另抄一份：抄本会和代码漂，漂了就复现成
    "读不到 ⇒ citation_drift ⇒ 本格红"那种与判据无关的假红。
    """
    rels = {rel for rel, _literal, _claim in _CITATIONS}
    rels |= {"app/common/reliable_queue.py", "app/api/v1/chat.py",
             "frontend/src/components/ChatPanel.vue", "scripts/eval_transport_ask_v2.py",
             FIXTURE_REL.as_posix()}
    return sorted(rels)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8-sig")


def _load_adapter(root: Path):
    """按路径单独加载冻结适配器：它自己不 import app（R215 文件头明写这条纪律），照样能用。"""
    spec = importlib.util.spec_from_file_location(
        "r218_eval_transport_ask_v2", root / "scripts" / "eval_transport_ask_v2.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_chat():
    return importlib.import_module("app.api.v1.chat")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ============================== 判据 ② - D 格 ==============================

def backend_status_vocabulary(root: Path) -> dict:
    """从代码里抽出「后端 queue/status 答得出的状态」，不手抄清单。"""
    queue_text = _read(root, "app/common/reliable_queue.py")
    written = set(re.findall(
        r'self\.redis\.set\(self\._status_key\(request_id\),\s*"([a-z_]+)"\)', queue_text))
    api_text = _read(root, "app/api/v1/chat.py")
    synthesized = set(re.findall(r'"status":\s*"([a-z_]+)"', api_text)) & {"expired"}
    return {"written_by_queue": sorted(written), "synthesized_by_api": sorted(synthesized),
            "answers": sorted(written | synthesized)}


#: 「这一族轮询有没有截止表」的检索词：命中任意一枚就说明 watch 自己会到点停表。
#: 🔴 本件不假设答案 —— 09-24 在本树 ``watchQueueTurn`` 函数体里实测这六枚**全为 0 次**，
#: 所以 ``no_deadline`` 读 True；谁哪天给前端加了截止表，这里立刻翻 False，D 格的口径跟着变。
DEADLINE_TOKENS = ("setTimeout", "clearTimeout", "Date.now", "deadline", "Deadline", "elapsed")


def _function_body(text: str, name: str) -> str:
    """按花括号配平切出 ``function <name>(...)`` 的函数体（含头，不含 docstring 猜想）。"""
    at = text.index("function " + name + "(")
    open_at = text.index("{", at)
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[at:index + 1]
    raise AssertionError(f"{name} 的函数体没配平闭合")


def frontend_stop_vocabulary(root: Path) -> dict:
    """前端那族停轮子：``QUEUE_SETTLED``（状态名单）+ ``QUEUE_POLL_STOPPERS``（HTTP 回执）。

    再多交一枚 ``no_deadline``：``watchQueueTurn`` 只有 ``setInterval``（ChatPanel.vue:1013）与
    两枚 ``stop()``（:994 命中名单 / :1001 命中终止回执），**没有第三枚到点自停** —— 这决定了
    它漏停一枚的代价不是一个秒数，而是"永不停"。
    """
    rel = "frontend/src/components/ChatPanel.vue"
    text = _read(root, rel)
    settled = re.search(r"const QUEUE_SETTLED = \[([^\]]*)\]", text)
    stoppers = re.search(r"const QUEUE_POLL_STOPPERS = \[(.*?)\n\]", text, re.S)
    codes = re.findall(r"status:\s*(\d+),\s*code:\s*'([^']+)'", stoppers.group(1)) if stoppers else []
    interval = re.search(r"const QUEUE_POLL_MS = (\d+)", text)
    body = _function_body(text, "watchQueueTurn")
    return {"settled": sorted(x.strip().strip("'\"") for x in
                              (settled.group(1).split(",") if settled else [])),
            "http_stoppers": sorted(f"{a}:{b}" for a, b in codes),
            "poll_ms": int(interval.group(1)) if interval else 0,
            # 停表动作逐枚取证：连**原文**一起交，别只交行号 —— 只钉行号的话，别人在这枚
            # 文件上沿插一行就把本件打成假红（这正是本单第 ② 件要修的这类地雷）。
            "stop_actions": [[n, line.strip()] for n, line in enumerate(text.splitlines(), 1)
                             if "QUEUE_SETTLED.includes" in line or "setInterval(tick" in line],
            "deadline_tokens_seen": {tok: body.count(tok) for tok in DEADLINE_TOKENS},
            "no_deadline": not any(tok in body for tok in DEADLINE_TOKENS)}


def question_count(root: Path) -> int:
    """题数**从夹具现读**，不手抄：上一班那句 ``900 × 105`` 里的 105 是抄来的，钉不住。"""
    return len([line for line in
                _read(root, FIXTURE_REL.as_posix()).splitlines() if line.strip()])


def adapter_stop_vocabulary(root: Path) -> dict:
    """适配器那族停轮子：``_poll_queue`` 函数体里比较过的状态字面 + 它的截止。"""
    text = _read(root, "scripts/eval_transport_ask_v2.py")
    tree = ast.parse(text)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_poll_queue")
    stops: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) \
                and node.left.id == "status":
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    stops.add(comparator.value)
                elif isinstance(comparator, (ast.Tuple, ast.List)):
                    stops.update(e.value for e in comparator.elts if isinstance(e, ast.Constant))
    env = re.search(r'QUEUE_POLL_SECONDS = float\(os\.getenv\("([A-Z_]+)",\s*"(\d+(?:\.\d+)?)"\)\)',
                    text)
    return {"stops": sorted(stops),
            "deadline_env": env.group(1) if env else "",
            "deadline_seconds": float(env.group(2)) if env else 0.0}


def citation_drift(root: Path) -> list:
    """逐条复验抄本还在不在代码里。漂一条报一条，别让判定坐在过期抄本上。"""
    drift = []
    for rel, literal, _claim in _CITATIONS:
        try:
            if literal not in _read(root, rel):
                drift.append(f"{rel} 已无字面 {literal!r}")
        except OSError as exc:
            drift.append(f"{rel} 读不到：{exc}")
    return drift


def lane_flip_readings(root: Path) -> dict:
    """翻开关：直接调产品那两枚谓词本体，不吃宿主环境变量残留。"""
    chat = _load_chat()
    saved = os.environ.get("REPORT_LANE_VIA_QUEUE")
    try:
        os.environ.pop("REPORT_LANE_VIA_QUEUE", None)
        unset = bool(chat._report_lane_via_queue_enabled())
        os.environ["REPORT_LANE_VIA_QUEUE"] = "on"
        on = bool(chat._report_lane_via_queue_enabled())
        os.environ["REPORT_LANE_VIA_QUEUE"] = "off"
        off_literal = bool(chat._report_lane_via_queue_enabled())
        lanes = {value: str(chat._queue_lane(types.SimpleNamespace(lane=value)))
                 for value in ("report", "REPORT", "qa", "analysis", "")}
    finally:
        if saved is None:
            os.environ.pop("REPORT_LANE_VIA_QUEUE", None)
        else:
            os.environ["REPORT_LANE_VIA_QUEUE"] = saved
    return {"default_off": not unset, "flip_on": on, "flip_off_literal": not off_literal,
            "lane_predicate": lanes}


def stop_set_gap(frontend_settled, adapter_stops) -> tuple:
    """两族停表各自漏掉的终态。前端漏 = 收窗停不干净的轮子；适配器漏 = 每题白花一段 deadline。"""
    front = [s for s in FINAL_QUEUE_STATUSES if s not in set(frontend_settled)]
    back = [s for s in FINAL_QUEUE_STATUSES if s not in set(adapter_stops)]
    return front, back


def cell_lane_flip(root: Path) -> dict:
    """D 格：翻开关本身离线判得动；判不动的（真 worker、真 Redis）逐条落成 NOT_COVERED。"""
    vocab = backend_status_vocabulary(root)
    front = frontend_stop_vocabulary(root)
    back = adapter_stop_vocabulary(root)
    flip = lane_flip_readings(root)
    drift = citation_drift(root)
    questions = question_count(root)
    # 前端无截止（抄本：watchQueueTurn 只有 setInterval，命中名单或 HTTP 终止回执才 stop）⇒
    # 每一个终态都必须出现在 QUEUE_SETTLED 里，少一枚就是一枚停不干净的轮子。
    unhandled_front, unhandled_back = stop_set_gap(front["settled"], back["stops"])
    not_covered = [
        f"{NOT_COVERED} 队列 worker 真取回（deploy/queue_worker.py 要真 Redis + 真进程；离线只能判"
        "状态字面，判不了 done 之后 result 真不真）",
        f"{NOT_COVERED} 报告档整轮端到端（入队→worker 跑完→/queue/status 取回正文要真容器）",
    ]
    problems = []
    if drift:
        problems.append("citation_drift:" + " | ".join(drift))
    if not (flip["default_off"] and flip["flip_on"] and flip["flip_off_literal"]):
        problems.append("lane_predicate_flip=" + json.dumps(flip, ensure_ascii=False, sort_keys=True))
    if flip["lane_predicate"].get("report") != "report" or flip["lane_predicate"].get("REPORT") != "":
        problems.append("lane_case_matching=" + json.dumps(flip["lane_predicate"], ensure_ascii=False))
    if not back["stops"]:
        problems.append("adapter_poll_stops_unparsed")
    if not front["settled"]:
        problems.append("frontend_settled_unparsed")
    if unhandled_front:
        problems.append("frontend_never_stops_on=" + ",".join(unhandled_front))
    if not front["no_deadline"]:
        # 前端一旦有了截止表，"漏停 = 永不停"这句代价口径就过期了：本件的读数要跟着改，
        # 不许拿着旧口径继续报数 —— 宁可当场红，让窗前来人重算。
        problems.append("frontend_deadline_appeared_rerun_the_cost_reading")
    return {"cell": CELL_D,
            "verdict": RED if problems else GREEN,
            "readings": {"backend_answers": vocab["answers"],
                         "final_statuses": list(FINAL_QUEUE_STATUSES),
                         "inflight_statuses": list(INFLIGHT_QUEUE_STATUSES),
                         "frontend_settled": front["settled"],
                         "frontend_http_stoppers": front["http_stoppers"],
                         "frontend_poll_ms": front["poll_ms"],
                         "frontend_stop_actions": front["stop_actions"],
                         "frontend_deadline_tokens_seen": front["deadline_tokens_seen"],
                         "frontend_unhandled_final": unhandled_front,
                         "adapter_stops": back["stops"],
                         "adapter_unhandled_final": unhandled_back,
                         "adapter_deadline_env": back["deadline_env"],
                         "adapter_deadline_seconds": back["deadline_seconds"],
                         # 🔴 R218 返工订正（判据 ③「不许把最坏情形写成期望值」）：上一班这里交的是
                         # `adapter_deadline_cost_105q_minutes = 900 × 105 / 60 = 1575`，那枚乘法把
                         # "每一条未终结的轮询都白等一整段 deadline"当成了前提，而 105 是**题数上限**、
                         # 落入 cancelled/dead 只是其中一部分题 ⇒ 1575 分钟是**上界**，不是预计代价。
                         # 现在把两件事分开交，且都不冒充期望值：
                         #   per_stalled_watch_waste_seconds —— 每条未终结轮询各白等多久（=deadline 本身）；
                         #   worst_case_*_if_every_question_stalls —— 只有"105 题全部撞上"才成立的天花板。
                         # 前端那一族另算：它压根没有 deadline，代价是"永不停"，不是一个秒数。
                         "adapter_waste_per_stalled_watch_seconds": back["deadline_seconds"],
                         "adapter_worst_case_minutes_if_every_question_stalls":
                             round(back["deadline_seconds"] * questions / 60.0, 1),
                         "question_count_read_from_fixture": questions,
                         "worst_case_is_upper_bound_not_expectation": True,
                         "frontend_watch_has_no_deadline": front["no_deadline"],
                         "lane_flip": flip,
                         "citation_drift": drift},
            "problems": problems,
            "not_covered_offline": not_covered}


# ============================== 判据 ② - C 格 ==============================

def hit_leg_literals(root: Path) -> dict:
    """命中道在产品代码里的两枚证词：status 帧文案 + text 帧的缓存三字段。"""
    text = _read(root, "app/api/v1/chat.py")
    status_lines = [line for line in text.splitlines()
                    if "event: status" in line and "缓存命中" in line]
    content = ""
    if status_lines:
        found = re.search(r"'content':\s*'([^']*)'", status_lines[0])
        content = found.group(1) if found else ""
    fields = re.search(r"cache_fields = \{(.*?)\n        \}", text, re.S)
    keys = re.findall(r'"([a-z_]+)":', fields.group(1)) if fields else []
    return {"status_content": content, "cache_field_keys": sorted(keys),
            "detects_status_literal": "缓存命中" in content}


def sse_lines(chat, frames: list, status_content: str, *, with_status: bool, frame_flag: bool) -> list:
    """把帧序列拼成 SSE 字节行：构造器用的是产品本体的 ``sse_event`` / ``text_sse_frame``。"""
    lines = []
    if with_status:
        lines.append("event: status\ndata: " + json.dumps(
            {"type": "status", "content": status_content}, ensure_ascii=False) + "\n\n")
    for frame in frames:
        if isinstance(frame, tuple):  # ("step", {...})
            lines.append(chat.sse_event(frame[0], frame[1]))
            continue
        cache_fields = None
        if frame_flag:
            cache_fields = {"cached": True,
                            "cache_generated_at": "2026-09-24T10:00:00+08:00",
                            "cache_note": "缓存结果 · 生成于 2026-09-24 10:00:00"}
        lines.append(chat.text_sse_frame(frame, cache_fields))
    # 🔴 iter_events 是**逐行**解析的（scripts/eval_transport_ask_v2.py:135 的 for raw in
    # response）：一整帧（含结尾空行）当一个元素喂进去，event:/data: 永远匹配不上，
    # 一条事件都解不出来 —— 本件 09-24 首跑就栽在这里，三格命中腿全读 False、A② 三形状
    # 全读 text_frames==0，而判据还照样"绿"。所以这里按产品写盘的换行拆回逐行。
    return [bytes(line, "utf-8") for frame in lines for line in frame.split("\n")[:-1]]


def observe(adapter, lines: list) -> dict:
    """走真适配器的那条解析路（``_consume``），不抄它自己的分支。"""
    out = adapter._blank_observation("r218-offline-session")
    adapter._consume(iter(lines), out)
    return out


def answer_record_keys(root: Path) -> dict:
    """采集器交回 answers/sidecar 的那些键里，到底有没有「这一发是命中腿」那一格。"""
    tree = ast.parse(_read(root, "scripts/eval_transport_ask_v2.py"))
    payload_keys: list = []
    sidecar_keys: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "answer" in keys and "evidence" in keys and "first_token_at" in keys:
                payload_keys = keys
            if "id" in keys and "kind" in keys and "wall_ms" in keys:
                sidecar_keys = keys
    return {"payload_keys": payload_keys, "sidecar_keys": sidecar_keys,
            "hit_marker_in_payload": any("cache" in str(k).lower() for k in payload_keys),
            "hit_marker_in_sidecar": any("cache" in str(k).lower() for k in sidecar_keys)}


def cache_leg_observations(adapter, chat, literal) -> dict:
    """同一题打两遍的第二遍：四种腿，采集器读出的 cached 各是什么。"""
    answer = "差旅费报销单须在费用发生后 30 日内提交。"
    legs = {
        "both_markers": sse_lines(chat, [answer], literal["status_content"],
                                  with_status=True, frame_flag=True),
        "frame_only": sse_lines(chat, [answer], "", with_status=False, frame_flag=True),
        "status_only": sse_lines(chat, [answer], literal["status_content"],
                                 with_status=True, frame_flag=False),
        "cold_leg": sse_lines(chat, [answer], "", with_status=False, frame_flag=False),
    }
    return {name: bool(observe(adapter, lines)["cached"]) for name, lines in legs.items()}


def cell_cache_hit(root: Path) -> dict:
    """C 格：第二遍那一发，采集器读不读得出「这是命中腿」。读不出就明写不可测，不假装绿。"""
    adapter = _load_adapter(root)
    chat = _load_chat()
    literal = hit_leg_literals(root)
    observed = cache_leg_observations(adapter, chat, literal)
    expected = {"both_markers": True, "frame_only": True, "status_only": True, "cold_leg": False}
    mismatched = sorted(k for k, want in expected.items() if observed.get(k) != want)
    markers = answer_record_keys(root)

    problems = []
    if not literal["detects_status_literal"] or not literal["cache_field_keys"]:
        problems.append("hit_leg_literals_drift=" + json.dumps(literal, ensure_ascii=False))
    if mismatched:
        problems.append("hit_leg_not_observable=" + ",".join(mismatched))
    not_covered = [
        f"{NOT_COVERED} 真 Redis 命中本身（app/common/cache.py:216 走 get_redis()，离线无 Redis；"
        "本件判的是「采集器读不读得出来」，不是「会不会命中」）",
        f"{NOT_COVERED} 命中答案的出处清单（R154 那三格 cached/cached-unknown 要 Redis 里真有记录）",
    ]
    if not markers["hit_marker_in_payload"] and not markers["hit_marker_in_sidecar"]:
        not_covered.append(
            f"{NOT_COVERED} 「报告里逐题显式标注命中」：命中腿在 transport 里是**硬抛**"
            "（scripts/eval_transport_ask_v2.py:467 直接 RuntimeError 停整 shard），命中永远进不了 "
            "answers ⇒ 窗内这一格只能按「P-18 开窗前 answer:* = 0 + 一旦命中即停窗」判，"
            "不许去报告里找那一列")
    return {"cell": CELL_C,
            "verdict": RED if problems else GREEN,
            "readings": {"status_content": literal["status_content"],
                         "cache_field_keys": literal["cache_field_keys"],
                         "collector_reads_hit_leg": observed,
                         "expected": expected,
                         "mismatched_legs": mismatched,
                         "answer_record_keys": markers},
            "problems": problems,
            "not_covered_offline": not_covered}


# ============================== 判据 ② - A② 格 ==============================

R215_KEYS = ("corrective_replacements", "uncorrected_breaks")
R181_KEYS = ("text_frames", "prefix_breaks", "missing_chars", "extra_chars")
HEAD = "差旅报销要"
TAIL = "差旅报销要在 30 日内提交"
REWRITTEN = "出差住宿标准每人每晚 450 元"



def ruler_generation(adapter) -> dict:
    """这把尺子是 R181 那一代还是 R181+R215 那一代：只读返回值键集，不猜。"""
    ledger = adapter._fold_frames(adapter._new_frame_ledger(),
                                  adapter._blank_observation("r218-probe"))
    keys = set(adapter._frame_readings(ledger, "探针"))
    return {"keys": sorted(keys),
            "has_r181": all(k in keys for k in R181_KEYS),
            "has_r215": all(k in keys for k in R215_KEYS)}


def _readings_keys(func) -> set:
    """``func`` 的**代码**里对 ``readings["..."]`` 的取用名集合（AST，剥掉 docstring 与注释）。

    🔴 这里绝不用 ``inspect.getsource`` + 子串匹配：那等于拿散文当证据。R215 把判绿那一格从
    ``prefix_breaks == 0`` 换成 ``uncorrected_breaks == 0``，可它的 docstring 里两个名字都还在
    （"``prefix_breaks == 0`` → **``uncorrected_breaks == 0``**"），子串匹配会永远读到双 True，
    于是"把尺子整代退回 R181"也打不红它 —— 反证钉乙 09-24 实测就是这枚假牙。改读 AST 之后，
    摘掉真读数才真的掉牙，"量具有牙"这句主张才算被钉住。
    """
    tree = ast.parse(inspect.getsource(func).lstrip())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "readings" and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            keys.add(node.slice.value)
    return keys


def verdict_reads(adapter) -> dict:
    """``_frame_verdict`` 今天判绿读的是哪一枚坏形计数：原始账还是 R215 那枚净额。

    只读代码（见 ``_readings_keys``）。两枚读数**互斥地**各钉一件事：R215 之后判绿腿读净额，
    所以 ``reads_prefix_breaks`` 必须 False —— 原始账并没有消失，它仍在 ``_frame_readings``
    的返回值键集里，那一格由 ``ruler_generation`` 的 ``has_r181`` 单独钉着（变严：两枚分开钉，
    任何一枚漂了就红，不再靠一句散文同时喂两格）。
    """
    keys = _readings_keys(adapter._frame_verdict)
    return {"reads_prefix_breaks": "prefix_breaks" in keys,
            "reads_uncorrected_breaks": "uncorrected_breaks" in keys,
            "verdict_key_set": sorted(keys)}


def correction_step(chat) -> tuple:
    """R210 那枚「武装整段替换」的 step 帧：字段逐字取自 app/api/v1/chat.py:2245-2248。"""
    return ("step", {"type": "step", "tool": chat.CORRECTION_STEP_TOOL,
                     "label": chat.CORRECTION_STEP_LABEL, "status": "running"})


def frame_shape(adapter, chat, *, armed: bool, break_at_tail: bool) -> dict:
    """两种形状：受控纠正轮（坏形在尾巴且被 step 武装）/ 真断流轮（没武装，或坏形在腰上）。

    ``HEAD -> TAIL`` 是合法累计对（TAIL 以 HEAD 为前缀），``REWRITTEN`` 与两者都不同源，
    所以它进流的那一枚就是坏形；它落在尾巴还是腰上、前面有没有那枚 step，就是两种形状的分界。
    """
    frames = [HEAD, TAIL, REWRITTEN] if break_at_tail else [HEAD, REWRITTEN, TAIL]
    bad_index = 2 if break_at_tail else 1
    stream = list(frames)
    if armed:
        stream.insert(bad_index, correction_step(chat))
    out = observe(adapter, sse_lines(chat, stream, "", with_status=False, frame_flag=False))
    ledger = adapter._fold_frames(adapter._new_frame_ledger(), out)
    answer = frames[-1]
    readings = adapter._frame_readings(ledger, answer)
    # 🔴 防「空转的牙」：一条什么都没解析出来的流也会让 _frame_verdict 回 False，那不等于尺子
    # 有牙，只等于量具没读到东西。合成流必须先自证「帧真进去了」，红色才算判出来的。
    return {"answer": answer, "readings": readings,
            "stream_parsed": int(readings["text_frames"]) == len(frames),
            "frames_sent": len(frames),
            "verdict": bool(adapter._frame_verdict(readings))}


def unparsed_shapes(shapes: dict) -> list:
    """合成流有没有真被适配器解析：帧数对得上，这一格的红色才算「判出来的」。

    🔴 一条什么都没解析出来的流同样会让 ``_frame_verdict`` 回 False —— 那不是尺子有牙，那是
    量具根本没读到东西。本件 09-24 首跑就栽在这里（整帧当一行喂进 ``iter_events``）：
    三种形状全读 ``text_frames == 0``、三条命中腿全读 ``cached == False``，而判据照样报绿。
    所以形状必须先自证「帧真进去了、枚数对得上」，才许它说话。
    """
    return sorted(name for name, shape in shapes.items() if not shape.get("stream_parsed"))


def cell_ruler(root: Path, claimed_generation: str | None = None) -> dict:
    """A② 格：先在离线合成流上把三种形状过一遍，再报这把尺子今天有没有牙。"""
    adapter = _load_adapter(root)
    chat = _load_chat()
    generation = ruler_generation(adapter)
    actual = "R181+R215" if generation["has_r215"] else "R181-only"
    claimed = claimed_generation or actual
    shapes = {"controlled_correction_round": frame_shape(adapter, chat, armed=True,
                                                         break_at_tail=True),
              "true_break_round": frame_shape(adapter, chat, armed=False, break_at_tail=True),
              "midstream_break_round": frame_shape(adapter, chat, armed=True,
                                                   break_at_tail=False)}
    controlled = shapes["controlled_correction_round"]
    broken = shapes["true_break_round"]
    midbreak = shapes["midstream_break_round"]
    unparsed = unparsed_shapes(shapes)

    problems = []
    if unparsed:
        problems.append("synthetic_stream_unparsed=" + ",".join(unparsed))
    if not generation["has_r181"]:
        problems.append("r181_readings_missing=" + ",".join(R181_KEYS))
    if claimed != actual:
        # 反证钉的落点：拿着「量具已有 R215 两格」的假口供来报绿，必须当场红，不许静默变绿。
        problems.append(f"generation_claim_mismatch claim={claimed} actual={actual}")
    # 牙：真断流轮必须读红。这一条在两代尺子上都成立 ⇒ 今天就能验，不用等窗。
    if broken["verdict"]:
        problems.append("broken_stream_reads_green")
    if midbreak["verdict"]:
        problems.append("midstream_break_reads_green")
    if controlled["verdict"] and not generation["has_r215"]:
        problems.append("controlled_round_reads_green_without_r215")
    # 🔴 牙的第二层（R218 返工新增）：账上有 R215 两格 **且** 判绿腿真读净额，两件事分开钉。
    # 上一班这里只比 `prefix_breaks` 子串，而 `inspect.getsource` 连 docstring 一起返回 —— R215
    # 的 docstring 里两个名字都在，于是"把尺子整代退回 R181"打不红它（反证钉乙实测假牙）。
    # 现在改成读 AST 里的 `readings[...]` 取用集：摘掉真读数才掉牙。
    reads = verdict_reads(adapter)
    if generation["has_r215"] and not reads["reads_uncorrected_breaks"]:
        problems.append("r215_ledger_keys_present_but_verdict_still_reads_prefix_breaks")
    if generation["has_r215"] and reads["reads_prefix_breaks"]:
        # 原始账重新进判据 => 豁免白给，"多豁免一次就永久假绿一次"那句话说反了方向
        problems.append("verdict_double_counts_raw_breaks")
    not_covered = []
    if not generation["has_r215"]:
        not_covered.append(
            f"{NOT_COVERED} 受控纠正轮读绿：本基点 scripts/eval_transport_ask_v2.py 还没有 "
            "corrective_replacements / uncorrected_breaks 两格（R215 仍是主树未提交工作副本），"
            "这把尺子今天只会把受控纠正轮读成 prefix_breaks>0 ⇒ 判据② 读红。窗内必须在最终 HEAD "
            "上复跑本件，两种形状同时成立才算数")
    elif not controlled["verdict"]:
        problems.append("controlled_round_reads_red_with_r215")
    return {"cell": CELL_A2,
            "verdict": RED if problems else GREEN,
            "readings": {"ruler_generation_actual": actual,
                         "ruler_generation_claimed": claimed,
                         "reading_keys": generation["keys"],
                         "verdict_reads": verdict_reads(adapter),
                         "unparsed_shapes": unparsed,
                         # 两形是否仍可分。前任态（dea3ee4）上两形原始账**逐格相同**
                         # （prefix_breaks=1 / first_break_at=3 / verdict=False）⇒ 那把尺子只判得出
                         # "断流读红"半边；R215 并树后本班态实测 corrective 1 vs 0、uncorrected
                         # 0 vs 1、verdict True vs False ⇒ 已可分，故本枚现在读 False。它留在账上是
                         # 因为钉的是"不可分"这个**历史形状**会不会回来：谁退掉豁免它立刻翻 True。
                        "shape_pair_indistinguishable_at_base":
                             controlled["readings"] == broken["readings"],
                         "shapes": shapes},
            "problems": problems,
            "not_covered_offline": not_covered}


# ============================== 汇总与 CLI ==============================

def run(root=None) -> list:
    root = Path(root) if root is not None else REPO_ROOT
    return [cell_lane_flip(root), cell_cache_hit(root), cell_ruler(root)]


def must_judge_in_window(cells: list) -> list:
    out = []
    for cell in cells:
        out.extend(cell.get("not_covered_offline") or [])
    return out


def report(cells: list) -> int:
    red = [c for c in cells if c["verdict"] == RED]
    for cell in cells:
        print(f"=== {cell['cell']} → {cell['verdict']}")
        print("    readings: " + json.dumps(cell["readings"], ensure_ascii=False,
                                           sort_keys=True, default=str))
        for problem in cell["problems"]:
            print(f"    PROBLEM {problem}")
        for item in cell["not_covered_offline"]:
            print(f"    {item}")
    print()
    hygiene = chroma_hygiene()
    print("chroma_hygiene=" + json.dumps(hygiene, ensure_ascii=False, sort_keys=True))
    if hygiene["tracked_store_violations"]:
        # 生产向量库被写过就是本单级失败：判据③ 不许为了变绿把它咽下去。
        red.append({"cell": "chroma-写回卫生", "problems": hygiene["tracked_store_violations"]})
    print(f"cells={len(cells)} red={len(red)} "
          + json.dumps([c["cell"] for c in red], ensure_ascii=False))
    print("must_judge_in_window=" + json.dumps(must_judge_in_window(cells), ensure_ascii=False))
    return 1 if red else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R218 run7 窗口开关离线预演（只读）")
    parser.add_argument("--json", action="store_true", help="三格读数一次成 JSON（仍只走 stdout）")
    args = parser.parse_args(argv)
    cells = run()
    if args.json:
        print(json.dumps(cells, ensure_ascii=False, sort_keys=True, default=str))
        return 1 if any(c["verdict"] == RED for c in cells) else 0
    return report(cells)


if __name__ == "__main__":
    sys.exit(main())