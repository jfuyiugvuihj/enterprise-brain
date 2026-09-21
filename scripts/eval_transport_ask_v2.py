"""R97 真机 105 题采集适配器 v2（2026-09-19 总控写，替代 09-18 那份 eval_transport_ask.py）。

与 09-18 那份的差别，以及每一条的依据（跑分窗口内本文件冻结，要改先收窗）：

1. 产品级结果不再当异常抛。09-18 那轮 73 分钟白跑的实证是
   C:\\Users\\fengx\\AppData\\Local\\Temp\\evalrun\\B.err：21 题缺口 -> CoverageError ->
   write_answers 一行都没写。现在这些结果一律记成「产品当时真正吐出的字节」：
   - hitl：app/api/v1/chat.py:1327-1328 已把 hitl_park_text 填进 full_text，:1364 照样发 text，
     所以「等确认」就是产品给这一题的终答；它会在 must_contain 上判错，这正是该得的分。
   - error：:1335-1338 的 failure_text 与 :1429-1439 的异常文本都是产品自己
     _save_message 进会话历史的字符串（:1336、:1428），我们只是抄，不发明一个字。
2. 答案缓存命中仍然 raise。命中不是产品行为，是开窗纪律破了（P-18：开窗前 flush Redis 里的
   answer:* 键；TTL 1800 s，见 app/common/cache.py:17）。宁可停下重跑一个 shard，也不让约 50 ms
   的假时延进 P95（runbook §10 的 I-3 就是拦这个）。识别走双路：text 事件的 cached 字段
   （chat.py:1177）与 status 里的「缓存命中」文案（:1175）。
3. queued 现在会自适应取回正文。入队那条道要求 Idempotency-Key（chat.py:1015-1016 直接抛 400），
   旧适配器不发这个键，撞上就是 HTTPError 白少一题。现在每题都带键；真撞上就轮询
   /api/v1/queue/status/<id> 到 done，取 result（app/common/reliable_queue.py:171 回 str），
   并把 first_token_at 记 null —— 后台跑的首字观测不到，采集器 :124-130 允许 null，禁止估算。
4. 逐题在盘：每题往 EVAL_SIDECAR 追加一行（id / kind / 证据条数 / 字符数 / 实测耗时 / 时刻）。
   采集器只在覆盖闸全过时写字节，中途没有断点；sidecar 就是「这一轮废在哪一题」的证据。
   把这件事做进仓库件是 R96，本文件只负责让今天的窗口不再全有或全无。
6. R123 甲案（09-20 业主从跟进单 §57 的三选一里裁定「甲」）：hitl 挂起不再当终答。采集器对
   requires_approval 挂起的题，用**同一个 session_id、同一个 Bearer token** 调
   POST /api/v1/approve（app/api/v1/chat.py:1719，挂在 /api/v1 下：app/main.py:80）按契约批准，
   再把恢复后的流消费到终答
   为止（批准后图又停在下一个闸就再批，上限 EVAL_APPROVAL_ROUNDS）。批准没被接受（非 2xx）、
   超时、或批准后仍拿不到终答 ⇒ 记 approval_failed：正文用占位串、出处清空、sentinel=true，
   绝不拿批准前的「等待确认」半截文本冒充终答。批准前那一帧原样留在侧车的 pre_* 键里 ⇒
   同一份侧车既能重算「旧口径」（105 分母、park 文本当答案）也能重算「甲案口径」，重算器在
   app/quality/eval.py 的 pre_approval_ruler。🔴 不绕过鉴权、不伪造 session、不直接调
   app.agents.orchestrator.run_interrupt_stream —— 绕过去就不是「跑分账号有权批准自己的挂起轮」
   这句话被实测过了。
5. 零字节的题用哨兵串 EVAL_BLANK_SENTINEL 占位，并把 evidence 强制清空（不许给一条没答的题记
   出处分），sidecar 标 sentinel；超过 EVAL_MAX_BLANKS 题就 raise 停窗：那是系统性故障，
   不该被一份能出数的报告盖住。

跑法与凭据见看板 §4BD：BASE_URL / 账号一律走环境变量，代码里没有硬编凭据。
"""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
TIMEOUT = float(os.getenv("EVAL_HTTP_TIMEOUT", "900"))
ATTEMPTS = max(1, int(os.getenv("EVAL_ATTEMPTS", "3")))
RETRY_SLEEP = float(os.getenv("EVAL_RETRY_SLEEP", "20"))
MIN_GAP_SECONDS = float(os.getenv("EVAL_MIN_GAP_SECONDS", "7"))
QUEUE_POLL_SECONDS = float(os.getenv("EVAL_QUEUE_POLL_SECONDS", "900"))
BLANK_SENTINEL = os.getenv("EVAL_BLANK_SENTINEL", "<no-bytes-emitted>")
MAX_BLANKS = int(os.getenv("EVAL_MAX_BLANKS", "5"))
#: R123 甲案。路由挂在 `/api/v1` 上（app/main.py:80 `include_router(chat.router, "/api/v1")`），
#: 所以批准端点是 POST /api/v1/approve（app/api/v1/chat.py:1719）—— 不是 /api/v1/chat/approve：
#: 那个路径不存在，真机第一投就是被它打成 404 的（08-21 08:31 探针，容器 openapi 复核）。
APPROVAL_PATH = "/api/v1/approve"
APPROVAL_ROUNDS = max(1, int(os.getenv("EVAL_APPROVAL_ROUNDS", "3")))
APPROVAL_FAILED_SENTINEL = os.getenv(
    "EVAL_APPROVAL_FAILED_SENTINEL", "<approval-failed-no-terminal-answer>")
SIDECAR = Path(os.getenv("EVAL_SIDECAR") or str(Path(__file__).with_name("collect-sidecar.jsonl")))
# 空 dict = 无视 http_proxy/HTTPS_PROXY，等价 curl --noproxy "*"（runbook §6：Clash 会劫 127.0.0.1）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_TOKEN = ""
_LAST_CALL = 0.0
_BLANKS = 0
_APPROVAL_FAILURES = 0


def _open(path, payload=None, method="POST"):
    headers = {"Content-Type": "application/json"}
    if _TOKEN:
        headers["Authorization"] = "Bearer " + _TOKEN  # app/common/auth.py:298-302
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE_URL + path, data=body, headers=headers, method=method)
    return _OPENER.open(request, timeout=TIMEOUT)


def login():
    """/api/v1/login 免鉴权（app/common/auth.py:36 PUBLIC_PATHS），响应体取 token 键。"""
    global _TOKEN
    if _TOKEN:
        return _TOKEN
    body = json.loads(_open("/api/v1/login", {
        "username": os.getenv("EVAL_USERNAME", ""),
        "password": os.getenv("EVAL_PASSWORD", ""),
    }).read().decode("utf-8", "replace"))
    _TOKEN = body.get("token") or ""  # app/api/v1/auth.py:60-66
    if not _TOKEN:
        raise RuntimeError("login 响应里没有 token 键")
    return _TOKEN


def iter_events(response):
    """逐行解 SSE：yield (事件名, payload, 到达墙钟)。

    服务端每事件写成 event: <name> + data: <单行 JSON> + 空行（app/api/v1/chat.py:218-219），
    canonical 事件外面还有一层信封（:222-243），所以 sources 在 data["data"]["sources"]。
    """
    name, data, arrival = None, None, None
    for raw in response:
        line = raw.decode("utf-8", "replace").rstrip()
        if line.startswith("event: "):
            name = line[7:].strip()
        elif line.startswith("data: "):
            data, arrival = json.loads(line[6:]), time.time()
        elif not line and name:
            yield name, (data or {}), arrival
            name, data, arrival = None, None, None


def _pace():
    """严格串行 + 每题最小间隔：/ask 有每用户 10 次/分钟的限制，撞限会被塞进入队道，
    量到的就不是这一轮的生成时延（runbook §9：限速不算失败重试）。"""
    global _LAST_CALL
    wait = MIN_GAP_SECONDS - (time.time() - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.time()


def _blank_observation(session_id):
    """一轮流的观测桶：/ask 与 /approve 两个出口共用同一个形状、同一套解析。"""
    return {"answer": "", "evidence": [], "first_token_at": None, "steps": 0,
            "hitl": False, "error_text": "", "queued": None, "cancelled": False,
            "cached": False, "session_id": session_id}


def _consume(response, out):
    """把一条 SSE 流从头读到尾，逐事件填进观测桶。/ask 与 /approve 事件形状同构。"""
    for name, data, arrival in iter_events(response):
        if name == "status" and "缓存命中" in str(data.get("content", "")):
            out["cached"] = True
        elif name == "step":
            out["steps"] += 1  # 计数留给 R38 用量审计
        elif name == "text":
            if data.get("cached"):
                out["cached"] = True  # chat.py:1177
            content = data.get("content")
            if content:
                if out["first_token_at"] is None:
                    out["first_token_at"] = arrival  # 首字到达＝客户端实测，不用服务端 elapsed 折算
                out["answer"] = str(content)  # /ask 只发一条整段 text（chat.py:1364）
        elif name == "sources":
            out["evidence"] = list((data.get("data") or {}).get("sources", []))  # chat.py:1403-1418
        elif name == "hitl":
            out["hitl"] = True  # chat.py:1379 —— 不抛：正文在 :1359-1365 已经发过了
        elif name == "error":
            text = str(data.get("content") or "")
            if text:
                out["error_text"] = text  # chat.py:1338 / :1439
        elif name == "queued":
            out["queued"] = dict(data)  # chat.py:1039-1051
        elif name == "cancelled":
            out["cancelled"] = True  # chat.py:1283
    return out


def _stream_once(question, session_id, idempotency_key):
    out = _blank_observation(session_id)
    payload = {"message": question, "session_id": session_id, "idempotency_key": idempotency_key}
    with _open("/api/v1/ask", payload) as resp:
        return _consume(resp, out)


def _approve_once(session_id):
    """R123 甲案：按契约批准这一题挂起的那一轮 —— 同一个 session_id、同一个 Bearer token。

    /approve 的归属判定与「读这条会话」用的是同一个谓词（app/api/v1/chat.py:1722 -> :377
    session_registry.is_owned_by），而 /ask 在 :1112 已经把这一题的 session 绑给了登录主体
    ⇒ 跑分账号 evalbot 能批自己挂起的那一轮。这句话要靠真机探针实测（判据 6），所以这里
    只走 HTTP：不绕过鉴权、不伪造 session、不直接调 run_interrupt_stream。
    """
    out = _blank_observation(session_id)
    with _open(APPROVAL_PATH, {"session_id": session_id, "approved": True}) as resp:
        return _consume(resp, out)


def _resolve_hitl(row_id, session_id, steps):
    """R123 甲案：把挂起轮批准到终答（判据 1），拿不到终答就照实记 approval_failed（判据 3）。

    返回 dict：交回采集器的 answer/evidence/first_token_at/steps/kind/sentinel，加侧车用的
    approved/rounds/http_status/error。🔴 每一条失败分支都不返回批准前的 park 文本 ——
    正文换成占位串、出处清空、sentinel=true，评分器永远看不到「半截文本冒充终答」。

    批准失败**不占用** EVAL_ATTEMPTS 的重试预算：attempt 记的是「这道题的 /ask 打到第几次」
    （判据 5），整题重来会把已花掉的生成时间重复计一次，量出来的就不是模型而是排队。
    """
    approved = False
    rounds = 0
    http_status = None
    error = ""
    for _ in range(APPROVAL_ROUNDS):
        rounds += 1
        try:
            out = _approve_once(session_id)
        except urllib.error.HTTPError as exc:  # 非 2xx = 批准没被接受，不许静默当答完
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                detail = ""
            http_status = exc.code
            error = "approve HTTP " + str(exc.code) + " " + detail
            break
        except (urllib.error.URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            error = "approve " + type(exc).__name__ + ": " + str(exc)  # 超时/连不通同算失败
            break
        http_status = 200
        approved = True
        if out["cached"]:
            raise RuntimeError(
                row_id + ": /approve 之后出现缓存命中 ⇒ 开窗纪律破了（P-18），停下重跑，不许估算")
        steps += out["steps"]  # tool_calls = 这一题全部 step（挂起轮 + 批准后的恢复轮）
        if out["hitl"]:
            continue  # 批准后图又停在下一个闸（chat.py:1891-1905）⇒ 再批一轮，有上限
        text = str(out["answer"] or "")
        if text.strip():
            return {"answer": text, "evidence": list(out["evidence"]),
                    "first_token_at": out["first_token_at"], "steps": steps,
                    "kind": "approved_ok", "sentinel": False, "approved": approved,
                    "rounds": rounds, "http_status": http_status, "error": ""}
        error = "approve 200 仍无终答：" + (out["error_text"].strip() or "恢复流里没有 text 事件")
        break
    if not error:
        error = "批准 " + str(rounds) + " 轮后仍停在审批闸，没有终答（上限 EVAL_APPROVAL_ROUNDS）"
    return {"answer": APPROVAL_FAILED_SENTINEL, "evidence": [], "first_token_at": None,
            "steps": steps, "kind": "approval_failed", "sentinel": True, "approved": approved,
            "rounds": rounds, "http_status": http_status, "error": error}


def _poll_queue(request_id):
    """入队那道的正文只能事后取：轮询到 done 取 result（reliable_queue.py:171 回 str）。
    expired / failed 取不到就是取不到，返回空串交给上层判 kind，不伪造。"""
    deadline = time.time() + QUEUE_POLL_SECONDS
    while time.time() < deadline:
        with _open("/api/v1/queue/status/" + str(request_id), None, "GET") as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        status = str(body.get("status", ""))
        if status == "done":
            result = body.get("result")
            return result if isinstance(result, str) else ""
        if status in ("expired", "failed"):
            return ""
        time.sleep(3.0)
    return ""


def _record(row_id, kind, attempt, started, payload, sentinel, extra=None):
    """逐题在盘：采集器只有覆盖闸全过才写字节，中途没有任何断点，这行就是废题的证据。

    🔴 R123 判据 2：既有九键（id/kind/attempt/sentinel/evidence_n/answer_chars/tool_calls/
    wall_ms/ts）的名字、顺序与语义一字不改，`kind` 仍是「这一题最终交回采集器的是什么形态」；
    甲案新增的 pre_*/approval_* 追加在后面，且只有真挂起过的题才带 pre_answer。旧口径就从
    这些键重算（app/quality/eval.py 的 pre_approval_ruler），不另写第二把尺。
    """
    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,
           "evidence_n": len(payload.get("evidence") or []),
           "answer_chars": len(str(payload.get("answer") or "")),
           "tool_calls": payload.get("tool_calls"),
           "wall_ms": round((time.time() - started) * 1000.0, 1),
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    row.update(extra or {})
    SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    with SIDECAR.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


def transport(row):
    """采集器对每题调一次：入参 fixture row，出参 §3.1 那张表里的 payload。

    除了三种测量环境破了的情况（命中缓存 / 零字节超阈值 / 重试耗尽连不通），一律返回产品真正
    吐出的字节。R123 甲案之后 HITL 等待文案不再是这一题的终答：先按契约批准，拿真终答回来；
    批准失败记 approval_failed，不拿挂起那一帧的半截文本冒充答案。
    """
    global _TOKEN, _BLANKS, _APPROVAL_FAILURES
    row_id = str(row.get("id", ""))
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        started = time.time()
        login()
        _pace()
        try:
            out = _stream_once(str(row["question"]), uuid.uuid4().hex, uuid.uuid4().hex)
        except urllib.error.HTTPError as exc:  # HTTPError 先于 URLError 捕获，401 强制重登
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            last_error = "HTTP " + str(exc.code) + " " + detail
            if exc.code == 401:
                _TOKEN = ""
            time.sleep(RETRY_SLEEP)
            continue
        except (urllib.error.URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__ + ": " + str(exc)
            time.sleep(RETRY_SLEEP)
            continue
        if out["cached"]:
            raise RuntimeError(
                row_id + ": 命中答案缓存 ⇒ 开窗纪律破了（P-18 要求开窗前 flush Redis 的 answer:*）。"
                "整 shard 停下重跑，不许让假时延进 P95（runbook §10 I-3）。")
        answer = out["answer"]
        evidence = out["evidence"]
        first_token_at = out["first_token_at"]
        sentinel = False
        kind = "ok"
        if out["queued"] is not None:
            kind = "queued_polled"
            answer = _poll_queue(out["queued"].get("request_id"))
            first_token_at = None  # 后台跑的首字观测不到 ⇒ null（采集器允许 null，禁止估算）
        if not answer.strip() and out["error_text"].strip():
            answer, kind, evidence = out["error_text"], "error_event", []
        if not answer.strip():
            kind = "cancelled" if out["cancelled"] else "blank"
            _BLANKS += 1
            if _BLANKS > MAX_BLANKS:
                raise RuntimeError(
                    row_id + ": 零字节题数已超 " + str(MAX_BLANKS) + " 题 ⇒ 系统性故障，停窗，"
                    "不出报告。差因看 sidecar 与 docker logs。")
            answer, evidence, sentinel = BLANK_SENTINEL, [], True
        elif out["hitl"]:
            kind = "hitl"
        # ===== R123 甲案：kind==hitl 就是「批准前停在闸上」，pre_* 键把旧形态留在侧车 =====
        extra = {"pre_kind": kind, "pre_answer_chars": len(str(answer)),
                 "pre_evidence_n": len(evidence), "approved": False, "approval_rounds": 0,
                 "approval_http_status": None, "approval_error": ""}
        steps = out["steps"]
        if kind == "hitl":
            extra["pre_answer"] = str(answer)  # 旧口径重算要的那一帧原文（判据 2）
            resolved = _resolve_hitl(row_id, out["session_id"], steps)
            answer = resolved["answer"]
            evidence = resolved["evidence"]
            first_token_at = resolved["first_token_at"]
            steps = resolved["steps"]
            kind = resolved["kind"]
            sentinel = resolved["sentinel"]
            extra.update({"approved": resolved["approved"],
                          "approval_rounds": resolved["rounds"],
                          "approval_http_status": resolved["http_status"],
                          "approval_error": resolved["error"]})
            if kind == "approval_failed":
                _APPROVAL_FAILURES += 1  # 不进 _BLANKS：批准失败是产品结局，不是零字节系统性故障
        payload = {"answer": answer, "evidence": evidence, "first_token_at": first_token_at,
                   "thinking_chars": None,  # HTTP 侧看不见隐藏思维链 ⇒ null，禁止估算
                   "tool_calls": steps}
        # 故意不自报 latency_ms：交给采集器 perf_counter 实测（collect:192/:146）
        _record(row_id, kind, attempt, started, payload, sentinel, extra)
        return payload
    raise RuntimeError(row_id + ": " + str(ATTEMPTS) + " 次都没打通，最后一次 " + str(last_error))


def summary():
    """收窗自查用：本进程内的 kind 计数不在这里，sidecar 才是账本；这里只回阈值。"""
    return {"sidecar": str(SIDECAR), "blank_threshold": MAX_BLANKS, "attempts": ATTEMPTS,
            "approval_rounds": APPROVAL_ROUNDS,
            "approval_failed_sentinel": APPROVAL_FAILED_SENTINEL,
            "approval_failures_this_process": _APPROVAL_FAILURES}
