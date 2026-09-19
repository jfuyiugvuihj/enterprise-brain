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
SIDECAR = Path(os.getenv("EVAL_SIDECAR") or str(Path(__file__).with_name("collect-sidecar.jsonl")))
# 空 dict = 无视 http_proxy/HTTPS_PROXY，等价 curl --noproxy "*"（runbook §6：Clash 会劫 127.0.0.1）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_TOKEN = ""
_LAST_CALL = 0.0
_BLANKS = 0


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


def _stream_once(question, session_id, idempotency_key):
    out = {"answer": "", "evidence": [], "first_token_at": None, "steps": 0,
           "hitl": False, "error_text": "", "queued": None, "cancelled": False, "cached": False}
    payload = {"message": question, "session_id": session_id, "idempotency_key": idempotency_key}
    with _open("/api/v1/ask", payload) as resp:
        for name, data, arrival in iter_events(resp):
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


def _record(row_id, kind, attempt, started, payload, sentinel):
    """逐题在盘：采集器只有覆盖闸全过才写字节，中途没有任何断点，这行就是废题的证据。"""
    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,
           "evidence_n": len(payload.get("evidence") or []),
           "answer_chars": len(str(payload.get("answer") or "")),
           "tool_calls": payload.get("tool_calls"),
           "wall_ms": round((time.time() - started) * 1000.0, 1),
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    with SIDECAR.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


def transport(row):
    """采集器对每题调一次：入参 fixture row，出参 §3.1 那张表里的 payload。

    除了三种测量环境破了的情况（命中缓存 / 零字节超阈值 / 重试耗尽连不通），一律返回
    产品真正吐出的字节。产品自己的错误文案与 HITL 等待文案都是它的终答，记下来让它扣分。
    """
    global _TOKEN, _BLANKS
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
        payload = {"answer": answer, "evidence": evidence, "first_token_at": first_token_at,
                   "thinking_chars": None,  # HTTP 侧看不见隐藏思维链 ⇒ null，禁止估算
                   "tool_calls": out["steps"]}
        # 故意不自报 latency_ms：交给采集器 perf_counter 实测（collect:192/:146）
        _record(row_id, kind, attempt, started, payload, sentinel)
        return payload
    raise RuntimeError(row_id + ": " + str(ATTEMPTS) + " 次都没打通，最后一次 " + str(last_error))


def summary():
    """收窗自查用：本进程内的 kind 计数不在这里，sidecar 才是账本；这里只回阈值。"""
    return {"sidecar": str(SIDECAR), "blank_threshold": MAX_BLANKS, "attempts": ATTEMPTS}
