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
7. R181 判据②（09-23）：给 ``event: text`` 装一把尺子 —— 帧数、前缀单调坏形数、末帧与终答的
   缺字/多字，逐题落到 sidecar 之外的第二份证据件（``FRAME_LEDGER``，默认与 sidecar 同目录、
   同名加 ``-frames``）。🔴 这一条**只观测，不改评分**：``answer`` 的取值口径、
   ``APPROVAL_FAILED_SENTINEL``、``cached``、``first_token_at``、``steps`` 五样一个字未动，
   sidecar 那九键与其后的甲案七键也一字未动（把读数并进 sidecar 那一行会被
   ``tests/test_r123_hitl_approval.py:243`` 那条「extras 只许是甲案七键的子集」当场判红，
   而那枚文件不在本单写域）。读数口径与成因见 ``docs/testing/r181-text-frame-readings.md``。
 8. R215 判据② 换读法（09-24，出路 (c) 由总控裁定，本条即那一单）：收尾那枚**受控纠正替换**
   （R210 守卫在断流轮发的那一次整段替换）不再冒充成「流被截断」。帧账新增两格 ——
   ``corrective_replacements``（本轮被判为受控纠正替换的坏形枚数）与 ``uncorrected_breaks``
   （= ``prefix_breaks`` − 被豁免的枚数），判据② 读后者归零。🔴 原始账一个字不漂：
   ``text_frames`` / ``prefix_breaks`` / ``first_break_at`` / ``missing_chars`` / ``extra_chars``
   / ``answer_sha`` 取值口径逐字节不变。可逐位对的老证据只有 run6 那 105 行（仓库里唯一一份
   帧账原件；run2…run5 当年还没有这一格），复算已落成用例：
   ``tests/test_r215_recomputing_run6_frames.py``。豁免四条同时成立才给，缺一条不给：
   末帧 / 本轮至多一枚 / 前面紧邻那枚 step(running, answer_correction) / 末帧与终答逐字相等。

   本文件的行号引用会随 ``app/api/v1/chat.py`` 漂移。09-23 在本树实取：``chat.py:1364`` 今天落在
   ``_complete_pending_steps`` 的收尾里（``return completed`` 在 :1363），「/ask 只发一条整段 text」
   这句旧断言早已失效；``/approve`` 路由在 :2271 而不是 :1719。R181 只订正自己动到的那几处，
   其余留给总控统一校。

跑法与凭据见看板 §4BD：BASE_URL / 账号一律走环境变量，代码里没有硬编凭据。
"""
import hashlib
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
#: R181 判据② 的帧证据件：一题一行，join 键 ``id``（外加 attempt / session_id）。
#: 落点由 frame_ledger_path() 现算 —— 钉在 import 期会绕过"事后重绑 SIDECAR"的仓外纪律
#: （本单第一版就栽在这里：跑兄弟用例时往 scripts/ 里漏了一行，已清）。
FRAME_LEDGER_ENV = "EVAL_FRAME_LEDGER"


def frame_ledger_path():
    """帧证据件落点：``EVAL_FRAME_LEDGER`` 优先，否则跟着 SIDECAR（同目录、``-frames`` 尾缀）。

    跟着 SIDECAR 是为了让 runbook §8「产物落仓外」这一条纪律自动覆盖它：开窗只设一个
    ``EVAL_SIDECAR`` 就不会把第二份证据件漏在仓内。两个变量都不设时两份都落进 ``scripts/``，
    与 sidecar 默认值是同一条既有脚枪（runbook §16 记过）。
    """
    override = str(os.getenv(FRAME_LEDGER_ENV) or "").strip()
    if override:
        return Path(override)
    return Path(SIDECAR).with_name(Path(SIDECAR).stem + "-frames.jsonl")
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
    """一轮流的观测桶：/ask 与 /approve 两个出口共用同一个形状、同一套解析。

    R181 判据② 在桶尾追加四枚帧读数（帧数 / 坏形数 / 首枚坏形序号 / 末帧原文）。
    🔴 只记账：``answer`` 仍然是「后帧覆盖前帧」的末帧取值，一个字节都没改口径。

    R215 再加一枚 ``break_frames``：坏形那一枚帧**到达时**的形状证词（第几帧、前面紧邻的是
    不是那枚武装替换的 step、帧正文）。它只喂豁免判据，不参与上面任何一格的计数。
    """
    return {"answer": "", "evidence": [], "first_token_at": None, "steps": 0,
            "hitl": False, "error_text": "", "queued": None, "cancelled": False,
            "cached": False, "session_id": session_id,
            # R181：这一条流的 text 帧尺（cumulative 语义下的帧数与坏形数）
            "text_frames": 0, "prefix_breaks": 0, "first_break_at": 0,
            "last_text_frame": "",
            # R215：坏形的到达顺序证词。🔴 只有走真 ``_consume`` 的那条路才填得进来。
            "break_frames": []}


def _consume(response, out):
    """把一条 SSE 流从头读到尾，逐事件填进观测桶。/ask 与 /approve 事件形状同构。

    R215：多记一样东西 —— 每一枚帧到达时，它前面紧邻的是不是那枚武装整段替换的 step。
    🔴 「紧邻」只有在**事件流**上才判得出来，帧账本身判不出来：把 text 帧摘出来单独喂给尺
    （单测里那两枚 ``_readings`` 就是这么办的）证词就是空的，豁免永远拿不到，也就撒不了谎。
    """
    armed = False  # 上一枚事件是不是 step(tool=answer_correction, status=running)
    for name, data, arrival in iter_events(response):
        preceding_arm = armed
        armed = False
        if name == "status" and "缓存命中" in str(data.get("content", "")):
            out["cached"] = True
        elif name == "step":
            out["steps"] += 1  # 计数留给 R38 用量审计
            armed = _is_correction_arm(data)
        elif name == "text":
            if data.get("cached"):
                out["cached"] = True  # 命中帧的 cache_fields 在 chat.py:1645-1649，发帧在 :1660
            content = data.get("content")
            # R181 判据②：先给这一帧记账，再按既有口径取末帧覆盖前帧。缺 content 的帧
            # 记成空串帧 —— "空帧"本身就是一种形状，不许不数。计数不参与下面任何一行。
            frame = "" if content is None else str(content)
            _count_text_frame(out, frame)
            _note_frame_shape(out, frame, preceding_arm)  # R215：只补证词，不动计数
            if content:
                if out["first_token_at"] is None:
                    out["first_token_at"] = arrival  # 首字到达＝客户端实测，不用服务端 elapsed 折算
                out["answer"] = str(content)  # 末帧覆盖前帧：片帧 chat.py:1863，收尾整段 :1943
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


# ===== R181 判据②：给 ``event: text`` 装的尺子。以下每一行都只观测，不改评分。 =====

#: R210 收尾那枚「换源纠正」step 的 tool 名，镜像 app/api/v1/chat.py 里的同名常量。
#: 量具不许 import app（它要能被 importlib 单独加载），所以这里抄一份字面，并由
#: tests/test_r215_recognizing_a_controlled_correction.py 逐字钉住两边相等 —— 上游改名而
#: 这里没跟上的后果是豁免拿不到：宁可少豁免一次，不可多豁免一次。
CORRECTION_STEP_TOOL = "answer_correction"


def _sha12(text):
    """帧正文的短指纹。判据② 要「逐字比对」，但不必把客户正文抄进第二份文件。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _common_prefix_len(left, right):
    """两串共有的前缀长度 —— 它就是「缺字 / 多字」的分界线。"""
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _count_text_frame(out, frame):
    """收帧处：数帧 + 查相邻两帧的前缀单调（cumulative 语义），坏形记一次并留首枚序号。

    后端每来一枚片就发一帧「截至这一片的累计全文」——构造器 ``text_sse_frame()`` 在
    ``app/api/v1/chat.py:250-262``，片帧发在 :1863、收尾整段发在 :1943、命中道只有 :1660
    那一帧。所以一条合法流里后帧必须以先帧为前缀；不满足就是坏形（片与终答不同源，或
    流被截断）。后端在 :1888 为同一件事记 error 日志，这里是收端那把对称的尺子。
    """
    if out["text_frames"] and not frame.startswith(out["last_text_frame"]):
        out["prefix_breaks"] += 1
        if not out["first_break_at"]:
            out["first_break_at"] = out["text_frames"] + 1  # 坏形记"后帧"的序号（1 起）
    out["text_frames"] += 1
    out["last_text_frame"] = frame


def _is_correction_arm(data):
    """「武装整段替换」那枚 step 的形状：既有 step 词汇表里的 running + 那个 tool，没别的。

    认的是 R210 守卫在 ``app/api/v1/chat.py`` 收尾处发的那一枚（``sse_event("step",
    {**correction, "status": "running"})``）。前端 ``sessions.js`` 也正是被它置上
    ``_correcting``，屏上随后那枚 text 帧才整段替换 —— 量具认的和屏上做的是同一枚事件。
    """
    return bool(isinstance(data, dict) and data.get("tool") == CORRECTION_STEP_TOOL
                and data.get("status") == "running")


def _note_frame_shape(out, frame, armed):
    """紧跟在 ``_count_text_frame`` 后面，替刚到达的这一枚帧留下到达顺序上的证词。

    🔴 这里不自己判坏形：坏形与否**只读** ``prefix_breaks`` 的变化（判据仍然只有
    ``_count_text_frame`` 那一份），所以它既多不出一枚坏形，也少不出一枚坏形 —— 只能给
    已经发生的坏形补一份「它当时站在流的哪个位置、前面紧邻着什么」。
    """
    records = out.get("break_frames")
    if records is None:
        records = out["break_frames"] = []
    if out["prefix_breaks"] > len(records):
        records.append({"at": out["text_frames"], "armed": bool(armed), "text": frame})


def _new_frame_ledger():
    """一题的帧账本。一题可能不止一条流：/ask 之外还有 R123 甲案的若干轮 /approve。"""
    return {"text_frames": 0, "prefix_breaks": 0, "last_text_frame": "",
            "streams": 0, "max_stream_frames": 0, "per_stream": [],
            # R215：跨流的坏形证词。它**不进** per_stream —— 那一格的键集被
            # tests/test_r181_text_frame_ruler.py 逐字钉着，一多一少都算改尺。
            "break_frames": []}


def _fold_frames(ledger, out):
    """把一条流的帧读数并进这一题的账，原地返回这本账。

    前缀单调只在**同一条流内**判：批准后恢复的那条流从零起累计，拿它去比挂起轮的末帧
    会凭空长出坏形。跨流只留「最后真正到达的那一帧」当末帧（covering 语义下收端显示的
    就是它）。零帧的流照样计入 ``streams``，但不覆盖末帧 —— 没到达的帧不算末帧。
    """
    frames = int(out.get("text_frames") or 0)
    breaks = int(out.get("prefix_breaks") or 0)
    ledger["text_frames"] += frames
    ledger["prefix_breaks"] += breaks
    ledger["per_stream"].append({"frames": frames, "breaks": breaks,
                                 "first_break_at": int(out.get("first_break_at") or 0)})
    # R215：这条流的坏形证词跟着折进账，顺手记下「这条流一共几枚帧」—— 判据① （末帧）
    # 要的就是这两个数相等。零帧的流没有证词可带（上面那格同理不覆盖末帧）。
    stream_index = len(ledger["per_stream"]) - 1
    for record in out.get("break_frames") or []:
        ledger["break_frames"].append(
            {"stream": stream_index, "stream_frames": frames,
             "at": int(record.get("at") or 0), "armed": bool(record.get("armed")),
             "text": str(record.get("text") or "")})
    ledger["streams"] += 1
    ledger["max_stream_frames"] = max(int(ledger["max_stream_frames"]), frames)
    if frames:
        ledger["last_text_frame"] = str(out.get("last_text_frame") or "")
    return ledger


def _corrective_readings(frames, answer):
    """R215 判据② 的豁免账：本轮几枚坏形是「受控纠正替换」，剩下几枚是真断流。

    四条**同时**成立才豁免一枚，缺一条就不豁免 —— 量具多豁免一次，判据② 就永久假绿一次：
      ① 它是**这一条流的最后一枚** text 帧。中途坏形说明流被截断过，收尾救不回来；
      ② 本轮至多一枚。一题里出现第二次换源，那已经不是「一次纠正」；
      ③ 它前面紧邻一枚 ``step(tool=answer_correction, status=running)``。光靠字节流的形状
         （短一截、换个头、又变长）蒙不过去 —— 屏上那次整段替换是被这枚 step 武装的；
      ④ 它的正文与最终交付的 ``answer`` **逐字相等**。换源之后屏上没换成这份字，就不算纠正。
    🔴 原始账一格不动：``prefix_breaks`` 照旧，豁免只体现在 ``uncorrected_breaks``。
    """
    granted = 0
    answer_text = str(answer or "")
    for record in frames.get("break_frames") or []:
        if granted:  # ② 本轮至多一枚：第一枚拿到豁免之后，后面的候选一律不给
            break
        at = int(record.get("at") or 0)
        if at < 1:  # 帧序号从 1 起，0 是「没有这么一枚帧」——不许拿缺证词当证据
            continue
        if at != int(record.get("stream_frames") or 0):
            continue  # ① 不是这一条流的末帧
        if not record.get("armed"):
            continue  # ③ 前面没有那枚武装替换的 step
        if str(record.get("text") or "") != answer_text:
            continue  # ④ 屏上没真替换成交付的那份字
        granted += 1
    total = int(frames.get("prefix_breaks") or 0)
    return {"corrective_replacements": granted, "uncorrected_breaks": total - granted}


def _frame_readings(frames, answer):
    """判据② 的四枚读数，外加逐字比对用的两枚指纹。🔴 没有任何一枚进评分。

    R215 起再多两格（``corrective_replacements`` / ``uncorrected_breaks``）：照样一枚都不进
    评分，也不动前面那几格的取值口径。🔴 帧账一行的键集自本单起多这两格，那份键集钉在
    ``tests/test_r181_text_frame_ruler.py`` 的 ``FRAME_READING_KEYS`` —— 那枚文件不在本单
    写域，两个名字由总控补进去（少补一个就是当场红，不会静默漏过）。

    ``missing_chars`` / ``extra_chars`` 都是「终答相对末帧」：前者＝末帧里终答没写到的字，
    后者＝终答里末帧没带出来的字，共同前缀是分界，所以两侧分叉时两枚各记自己那半。
    一致性按 **covering 语义**判：末帧把终答所缺的部分盖住（``末帧.startswith(终答)``）
    即算一致 —— **不是严格相等**，收端 ``frontend/src/lib/sessions.js`` 的 covering 分支
    拿新帧整段替换，前端最终显示的就是末帧。``text_frames == 0`` 是**空读**（一帧都没到）：
    这一枚只在终答也是空串时才"空真"为 true，别读成通过 —— 合格线要求 ``text_frames > 1``，
    空读永远读不出成立。
    """
    last = str(frames.get("last_text_frame") or "")
    answer = str(answer or "")
    shared = _common_prefix_len(last, answer)
    corrective = _corrective_readings(frames, answer)
    return {"text_frames": int(frames["text_frames"]),
            "prefix_breaks": int(frames["prefix_breaks"]),
            # R215：坏形分家 —— 哪几枚是收尾那次受控纠正替换，哪几枚是没被救回来的真断流。
            "corrective_replacements": corrective["corrective_replacements"],
            "uncorrected_breaks": corrective["uncorrected_breaks"],
            "missing_chars": len(last) - shared,
            "extra_chars": len(answer) - shared,
            "last_frame_covers_answer": last.startswith(answer),
            "last_frame_chars": len(last),
            "last_frame_sha": _sha12(last),
            "answer_chars": len(answer),
            "answer_sha": _sha12(answer),
            "streams": int(frames["streams"]),
            # 这一枚单独给，是为了把"两条单帧流凑出 2 帧"与"一条流真在逐片累计"分开读：
            # 判据② 要的是后者。挂起轮 + 批准轮各一帧时 text_frames=2 而 max_stream_frames=1。
            "max_stream_frames": int(frames["max_stream_frames"]),
            "per_stream": list(frames["per_stream"])}


def _frame_verdict(readings):
    """把读数折成一格「判据② 这条流今天成不成立」，供收窗直接读。

    口径写死在 ``docs/testing/r181-text-frame-readings.md``：同一条流里累计出 >1 帧、
    终答相对末帧不缺字也不多字（covering ⇒ ``extra_chars == 0``）、末帧覆盖终答。
    R215 只换「坏形」那一格的读法：``prefix_breaks == 0`` → **``uncorrected_breaks == 0``**，
    读作「剩下的坏形里没有任何一次真断流」——收尾那次受控纠正替换（四条判据见
    ``_corrective_readings``）不再冒充成断流。🔴 与流式无关的条件一枚没加、一枚没减；
    原始 ``prefix_breaks`` 继续写进帧账，红了也看得见红在哪。

    ⚠️ 口径变更（R215 判据④ 明文要求，方向是**变严**）：``missing_chars == 0`` 与
    ``last_frame_covers_answer`` 自本单起进入合取。R181 那张纸
    （``docs/testing/r181-text-frame-readings.md`` §判据② 读法）当时只合取 ``extra_chars == 0``，
    并写着「``missing_chars > 0`` 在这一格算一致」—— 纸由总控改。实测影响面：run6 那 105 行
    的 ``criterion_two_holds`` 逐行不变（``tests/test_r215_recomputing_run6_frames.py`` 复算 0 漂），
    R181 那件重放的绿行数也不变；末帧比终答多字的形状从今天起读 False。
    """
    return bool(readings["text_frames"] > 1
                and readings["max_stream_frames"] > 1
                and readings["uncorrected_breaks"] == 0
                and readings["missing_chars"] == 0
                and readings["extra_chars"] == 0
                and readings["last_frame_covers_answer"])


def _record_frames(row_id, kind, attempt, session_id, frames, answer, sentinel):
    """一题一行的帧证据件：与 sidecar 同一次落盘动作里写，join 键 ``id``。

    🔴 侧车一个字都不动：``tests/test_r123_hitl_approval.py:243`` 把 sidecar 除九键之外的
    键集钉成甲案那七键的子集，读数并进那一行即红，而那枚文件不在 R181 写域。
    """
    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,
           "session_id": session_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    readings = _frame_readings(frames, answer)
    row.update(readings)
    row["criterion_two_holds"] = _frame_verdict(readings)
    target = frame_ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


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


def _resolve_hitl(row_id, session_id, steps, frames=None):
    """R123 甲案：把挂起轮批准到终答（判据 1），拿不到终答就照实记 approval_failed（判据 3）。

    ``frames`` 是 R181 判据② 那一题的帧账本：恢复流的帧并进同一本账（不传就现造一本，
    单测可以只管这一条流）。评分口径一个字没动。

    返回 dict：交回采集器的 answer/evidence/first_token_at/steps/kind/sentinel，加侧车用的
    approved/rounds/http_status/error。🔴 每一条失败分支都不返回批准前的 park 文本 ——
    正文换成占位串、出处清空、sentinel=true，评分器永远看不到「半截文本冒充终答」。

    批准失败**不占用** EVAL_ATTEMPTS 的重试预算：attempt 记的是「这道题的 /ask 打到第几次」
    （判据 5），整题重来会把已花掉的生成时间重复计一次，量出来的就不是模型而是排队。
    """
    frames = _new_frame_ledger() if frames is None else frames
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
        _fold_frames(frames, out)  # R181 判据②：恢复流的帧也算进这一题的账
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
        # R181 判据②：这一题的帧账从这条流起记。被打回重试的那一次整题重来，
        # 它没交回采集器，也就不替它记账 —— 记的是"这一题最终交回的那一路字节"。
        frames = _fold_frames(_new_frame_ledger(), out)
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
            resolved = _resolve_hitl(row_id, out["session_id"], steps, frames)
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
        # R181 判据②：sidecar 那九键 + 甲案七键原样不动，帧读数落在第二份证据件里。
        # 取的是交回采集器的那个 answer（含哨兵替换之后），所以"终答"就是评分真正看到的字。
        _record_frames(row_id, kind, attempt, out["session_id"], frames, answer, sentinel)
        return payload
    raise RuntimeError(row_id + ": " + str(ATTEMPTS) + " 次都没打通，最后一次 " + str(last_error))


def summary():
    """收窗自查用：本进程内的 kind 计数不在这里，sidecar 才是账本；这里只回阈值。"""
    return {"sidecar": str(SIDECAR), "blank_threshold": MAX_BLANKS, "attempts": ATTEMPTS,
            "approval_rounds": APPROVAL_ROUNDS,
            "approval_failed_sentinel": APPROVAL_FAILED_SENTINEL,
            "approval_failures_this_process": _APPROVAL_FAILURES,
            "frame_ledger": str(frame_ledger_path())}  # R181 判据② 的证据件落点（收窗自查用）
