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
 9. R222（09-25）队列道停表：``_poll_queue`` 从前只认 ``done`` / ``expired`` / ``failed``，落进
   ``cancelled`` / ``dead`` 就一路轮到 deadline ⇒ 每题白烧 900 s（R218 实取的病：
   ``adapter_unhandled_final=[cancelled,dead]`` / ``adapter_waste_per_stalled_watch_seconds=900``）。
   今天五枚终态（``done`` / ``cancelled`` / ``dead`` / ``expired`` / ``failed``）逐枚一枚可区分的
   kind，另加三枚「没读到终局」的 kind（``queued_stalled`` / ``queued_deadline`` /
   ``queued_no_status``）；取回那一程的账（几轮询 / 几次瞬断 / 等了多久 / 最后读到什么）落在
   帧账新格 ``queue`` 里。判据② 同装：非 2xx / 连不通 / JSON 解不开**一律不是停表条件**，
   只算一次抖动接着轮（与前端 R198/R202 同一族口径）。白烧上限另开
   ``EVAL_QUEUE_STALL_SECONDS``（默认 300 s，理由写在那一枚常数的注释里）：状态载荷连续
   300 s 没有任何可观测变化就停表 ⇒ 未识别终态那一族从 900 s 降到 300 s，而
   ``cancelled`` / ``dead`` 那一族从今天起读到就停，代价是至多一枚轮询间隔（3 s）。
10. R223（09-25）到达时刻的账：帧账从前只有「这一帧长什么样」，没有「这一帧什么时候到」，
    于是导不出「断流发生在什么时间」与「首屏可见元素何时到位」（B 门首屏 ≤1 s 一直没有尺子；
    run7 那枚 p50 24.3 s / p95 121.4 s 量的是正文首片，不是首屏）。今天帧账多七格：
    ``frames``（逐枚 text 帧：到达时刻 / 距零点毫秒 / 字数 / 短指纹 / 是否坏形）、
    ``events``（逐枚**全部**事件的到达时刻 + 它在前端认领表里的类别）、``first_visible_at`` /
    ``first_visible_event`` / ``first_visible_ms``（首枚非-text 可见事件，含 R48 已并树的
    canonical ``answer.headline``）、``stream_clock``（每条流的零点与第一枚事件）、
    ``queue``（见第 9 条）。🔴 只加读数：``answer`` / ``first_token_at`` / ``steps`` / ``cached`` /
    ``sentinel`` / 甲案七键 / 帧账既有十三格与 R215 两格 取值口径一字未动 ——
    ``tests/test_r215_recomputing_run6_frames.py`` 拿 run6 原件复算照旧逐位相同，
    「关掉新读数再跑同一条流」的反证钉在 ``tests/test_r223_frame_arrival_clock.py``。
    可见事件口径抄自 ``frontend/src/lib/sessions.js`` 的 ``EVENT_CLAIMS``（render 且名字不是
    text），抄本漂移由同一枚件当场红。

   🔴 钟的纪律（本单真踩过一次，所以写进代码）：上面这些读数**一次都不许多读表**。
   /ask 那条流的零点抄 ``_pace()`` 的放行戳（放行与 POST 之间只构造请求体，没有 I/O）；
   批准那条流抄不到表戳就留 null、退到本流第一枚事件；``_poll_queue`` 里 stalled 与
   deadline 两族的等待由「每轮那一枚唯一的表戳」算出来（零点用 deadline 反推）。用的哪
   一侧逐条写在 ``stream_clock.elapsed_base``，读的人不必猜。为什么这么苛刻：量具的假钟
   每读一次就走一格，多读一枚就把 R181 那 105 题重放的时间轴整条推走 ——
   ``PRE_R181_ANSWERS_SHA`` 当场红，而那枚 digest 正是「只加读数」这句话的裁判。
   同一族纪律还管着逐帧那一格：它**跟着 ``_count_text_frame`` 的计数走**（尺子没数的枚次
   这格也不记），所以它不是第二把尺 —— R215 的 ``_note_frame_shape`` 就是这么办的。

   🔴 **判据⑤ 抬头口径（写进代码，供总控抄档）：run8 的适配器 ≠ run6 / run7 的适配器。**
   两件事各自有名：(a) kind 词汇表自 R222 起多出 ``queued_*`` 九枚（``queued_polled`` /
   ``queued_done_no_bytes`` / ``queued_cancelled`` / ``queued_dead`` / ``queued_expired`` /
   ``queued_failed`` / ``queued_stalled`` / ``queued_deadline`` / ``queued_no_status``），
   旧轮次一枚也不可能有
   （本树实取：run6 帧账 kind 只有 ``ok`` / ``approved_ok`` / ``error_event``，run7 只有
   ``ok`` / ``approved_ok``）；(b) 到达时刻与 ``queue`` 那几格自 R223 / R222 起才存在，旧帧账
   原件（``docs/testing/sidecar-run6-frames.jsonl`` 十三格、``sidecar-run7-frames.jsonl``
   十五格）里没有它们 ⇒ 拿旧件重放只会长出**空列**，不许读成「当年零停表」，也不许读成
   「当年无断流」。断流的时刻与首屏的时刻从 run8 起才是量得出来的两件事。

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
#: 五枚终态的逐枚出处（不手抄清单，逐条可对）：done = app/common/reliable_queue.py:201、
#: cancelled = :165/:197/:237/:271、failed = :170、dead = :250（``deploy/queue_worker.py:206``
#: 自己把 ``terminal_status == "dead"`` 叫终态）、expired = app/api/v1/chat.py:3943（状态键
#: 读不到时 API 现造）。在途态 queued :149 / processing :177 / cancel_requested :273 不是终态：
#: 它们有代码写下的下一步迁移，所以「读到它」不构成停表理由（R218 同一份名单）。
#:
#: 外圈截止（改这行的字面或形状会同时打断总控的预演件：``scripts/r218_switch_rehearsal.py``
#: 里那条 ``QUEUE_POLL_SECONDS = float(os.getenv("EVAL_QUEUE_POLL_SECONDS", "N"))`` 正则与
#: ``_CITATIONS`` 的 ``deadline = time.time() + QUEUE_POLL_SECONDS`` 抄本，要改一起改）：
#: 这一枚只管「状态还在动」的轮询最多多等多久，它**不是**白烧的天花板。
QUEUE_POLL_SECONDS = float(os.getenv("EVAL_QUEUE_POLL_SECONDS", "900"))
#: 🔴 R222 判据① 真正降下来的那一枚：白烧上限。状态载荷（status / position /
#: ``failure.attempts`` 三样）连续这么久**没有任何可观测变化**就停表，读成 ``queued_stalled``。
#: 300 s 的两条理由：① 与后端自己的租约同源 —— ``reliable_queue.lease_seconds`` 默认 300
#: （app/common/reliable_queue.py:67），一个租约周期内没人再动这条消息，再等就是白烧；
#: ② 不误伤还在写的轮子 —— run7 报告档实测最慢单轮 159.8 s（本树实取
#: ``docs/testing/sidecar-run7.jsonl`` 的 wall_ms，档位按评测集 join），300 s 是它的 1.9 倍。
#: ⇒ 未识别终态那一族的白烧从 900 s 降到 300 s；``cancelled`` / ``dead`` 那一族读到就停，
#: 代价是至多一枚轮询间隔（3 s），不再是整段 deadline。
QUEUE_STALL_SECONDS = float(os.getenv("EVAL_QUEUE_STALL_SECONDS", "300"))
#: 轮询间隔与前端同源：``frontend/src/components/ChatPanel.vue:839`` 的 ``QUEUE_POLL_MS = 3000``。
#: 两族轮子一把尺，「前端 3 s 一停 vs 适配器 3 s 一停」才读得成同一句话。
QUEUE_POLL_INTERVAL = float(os.getenv("EVAL_QUEUE_POLL_INTERVAL_SECONDS", "3.0"))
BLANK_SENTINEL = os.getenv("EVAL_BLANK_SENTINEL", "<no-bytes-emitted>")
MAX_BLANKS = int(os.getenv("EVAL_MAX_BLANKS", "5"))
#: R123 甲案。路由挂在 `/api/v1` 上（app/main.py:80 `include_router(chat.router, "/api/v1")`），
#: 所以批准端点是 POST /api/v1/approve（app/api/v1/chat.py:1719）—— 不是 /api/v1/chat/approve：
#: 那个路径不存在，真机第一投就是被它打成 404 的（08-21 08:31 探针，容器 openapi 复核）。
APPROVAL_PATH = "/api/v1/approve"
APPROVAL_ROUNDS = max(1, int(os.getenv("EVAL_APPROVAL_ROUNDS", "3")))
#: R226（run7 相 2 前置·总控亲做）：入队要两件事同时成立 —— app/api/v1/chat.py:1955-1956 的
#: `lane == LANE_REPORT and _report_lane_via_queue_enabled()`。本量具从前从不发 lane（全文零命中），
#: 所以历轮跑分里报告档走的一律是同步道：只翻 REPORT_LANE_VIA_QUEUE 也不入队，D-1「入队 → worker
#: 跑完 → /queue/status 取回正文」从来没被量到过（run6 与 run7 相 1 的 12 道报告题 kind 全是 ok，
#: 没有一枚 queued_polled）。
#: 🔴 默认空串 = 载荷一个字节都不多，run6 / run7 相 1 的口径不受影响；把档位名设进来（相 2 用「报告」）
#: 才替该档的题补 lane，取值表与前端同源（frontend/src/router/lane-choice.js，ChatPanel.vue:602
#: 就是照这张表发的）⇒ 这是**量具缺陷，不是产品缺陷**。
DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "").strip()
LANE_BY_TIER = {"报告": "report", "分析": "analysis", "问答": "qa"}
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
    return _LAST_CALL  # R223：把这一枚放行戳交给调用者当零点 —— 量具因此不必再读一次表


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
            "break_frames": [],
            # R223：到达时刻的原始账。🔴 只记时刻，不参与上面与下面任何一格的计数与判据。
            # ``frame_arrivals`` 逐枚 text 帧，``event_arrivals`` 逐枚事件（text 与非 text 都记）。
            "frame_arrivals": [], "event_arrivals": [],
            # 本条流的零点：/ask 那条抄 ``_pace()`` 的放行戳（＝放行这一题、亦即发出 POST
            # 那一刻）。批准那条流没有表戳可抄 —— 量具不许为读数新读一次表 ⇒ 留 null。
            # 🔴 单测直接喂 ``_consume`` 时它是 None ⇒ elapsed 退到「本流第一枚事件到达」，
            # 退到哪一侧随读数一起交（帧账的 ``stream_clock.elapsed_base``），不静默换尺。
            "request_sent_at": None}


def _consume(response, out):
    """把一条 SSE 流从头读到尾，逐事件填进观测桶。/ask 与 /approve 事件形状同构。

    R215：多记一样东西 —— 每一枚帧到达时，它前面紧邻的是不是那枚武装整段替换的 step。
    🔴 「紧邻」只有在**事件流**上才判得出来，帧账本身判不出来：把 text 帧摘出来单独喂给尺
    （单测里那两枚 ``_readings`` 就是这么办的）证词就是空的，豁免永远拿不到，也就撒不了谎。

    R223 在同一个圈里再多抄一样东西：每一枚事件与每一枚 text 帧**到达的时刻**。钟不是新起的
    —— ``iter_events`` 本来就在 ``data:`` 那一行打了 ``time.time()`` 的戳（``first_token_at``
    用的就是它），这里只是把同一个戳抄进账。🔴 只抄不改：返回的还是同一个 ``out``，
    ``answer`` / ``first_token_at`` / ``steps`` / ``cached`` / ``evidence`` 的取值口径与把新读数
    关掉时逐字相同（那一件事由 tests/test_r223_frame_arrival_clock.py 的反证钉着）。
    """
    armed = False  # 上一枚事件是不是 step(tool=answer_correction, status=running)
    for name, data, arrival in iter_events(response):
        preceding_arm = armed
        armed = False
        # R223：先抄到达时刻，再走既有的分派。它认下**全部**事件名（连前端还没认领的也照实
        # 记成 unclaimed），只抄时刻与类别，一个字都不改下面任何一格的判定。
        _note_event_arrival(out, name, arrival)
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
            _note_frame_arrival(out, frame, arrival)  # R223：只补时刻，不动计数
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


# ===== R223：帧账的到达时刻。以下每一行都只读数，不改判据，也不参与评分。 =====

#: 事件名 → 它在前端那张认领表里的类别，抄自 ``frontend/src/lib/sessions.js`` 的
#: ``EVENT_CLAIMS``（口径原文：``render``＝画进界面；``note``＝只进过程提示条；
#: ``terminal``＝收尾信号；``silent``＝显式选择不画）。🔴 量具不许 import 前端，所以这里抄
#: 一份字面，并由 ``tests/test_r223_frame_arrival_clock.py`` 逐枚比对两边相等：抄本漂了的
#: 后果是「首屏」那一格静默换口径 —— 宁可当场红，不可悄悄量。
EVENT_CLASSES = {
    "status": "note",
    "text": "render",
    "step": "render",
    "hitl": "render",
    "error": "render",
    "cancelled": "render",
    "done": "terminal",
    "heartbeat": "silent",
    "queued": "render",
    "request.started": "silent",
    "request.completed": "terminal",
    "request.failed": "render",
    "request.cancelled": "render",
    "sources": "render",
    # R48 路线甲：首屏那张线索卡（app/api/v1/chat.py::_answer_headline_frame）。它不是一枚
    # text 帧，却是**第一个画到屏上的元素** ⇒ B 门「首屏 ≤1 s」量的就是它，不是正文首片。
    "answer.headline": "render",
}
#: 名字不在表里 = 量具没替它作过证（新事件名先在这儿露脸，是一枚信号，不是一枚错误）。
UNCLAIMED_EVENT_CLASS = "unclaimed"
#: 「首屏可见」只认画进界面那一族（``note`` 只进过程提示条，``silent``/``terminal`` 屏上无物）。
VISIBLE_EVENT_CLASS = "render"


def _event_class(name):
    return EVENT_CLASSES.get(str(name), UNCLAIMED_EVENT_CLASS)


def _is_first_screen_event(name):
    """首屏那一格两条同时成立：类别是 render，且它不是正文 ``text``（那一枚有 first_token_at）。"""
    return _event_class(name) == VISIBLE_EVENT_CLASS and str(name) != "text"


def _note_event_arrival(out, name, arrival):
    """给刚到达的这一枚事件抄一个时刻。🔴 不判形状、不计数，也不动 ``out`` 里任何既有键。"""
    records = out.get("event_arrivals")
    if records is None:
        records = out["event_arrivals"] = []
    records.append({"at": len(records) + 1, "event": str(name),
                    "class": _event_class(name), "arrival_at": arrival})


def _note_frame_arrival(out, frame, arrival):
    """给刚到达的这一枚 text 帧抄时刻 + 形状指纹（钟与事件账同一枚，永远同格）。

    🔴 这一格跟着 ``_count_text_frame`` 的计数走：尺子数了几枚，账上就有几枚到达时刻；
    尺子没数的那一枚不记（下面那道 ``at != len(records) + 1`` 的闸）。所以它不是第二把尺。
    🔴 ``prefix_break`` 只是把 R181 那把尺**已经判过**的坏形抄到这一枚帧上：读
    ``break_frames`` 末枚的序号，既不因此多出一枚坏形，也不少记一枚。
    """
    records = out.get("frame_arrivals")
    if records is None:
        records = out["frame_arrivals"] = []
    at = int(out.get("text_frames") or 0)  # _count_text_frame 已自增 ⇒ 这就是本帧的流内序号
    if at != len(records) + 1:
        # 🔴 R181 那把尺这一枚没数 ⇒ 这一格也不记。与 R215 的 ``_note_frame_shape`` 同一
        # 条纪律（它只跟着 ``prefix_breaks`` 的变化走）：新列必须是**派生**读数，不许
        # 自成第二把尺 —— 否则「把计数摘掉之后三帧与零帧同形」那枚常驻反证会被这格
        # 悄悄救活（tests/test_r181_text_frame_ruler.py:467）。尺子瞎，这格一起瞎。
        return
    breaks = out.get("break_frames") or []
    prefix_break = bool(breaks) and int(breaks[-1].get("at") or 0) == at
    records.append({"at": at, "arrival_at": arrival, "chars": len(frame),
                    "sha": _sha12(frame), "prefix_break": bool(prefix_break)})


def _elapsed_ms(arrival, base):
    """毫秒差。缺任何一侧都是 None —— 🔴 禁止估算，也不许拿 0 冒充「同一时刻」。"""
    if arrival is None or base is None:
        return None
    return round((float(arrival) - float(base)) * 1000.0, 1)


def _fold_arrivals(ledger, out, stream_index):
    """把这一条流的到达时刻折进这一题的账（R223）。

    零点按「先 POST，退到本流第一枚事件」的顺序取，用的是哪一侧随读数一起交
    （``stream_clock.elapsed_base``）。``at`` 是**流内**序号，与
    ``per_stream[i]["first_break_at"]``、``break_frames[].at`` 同一个坐标系 —— 断流那一枚帧
    因此在帧账里既是「第 stream 条流的第 at 帧」，又有它自己的到达时刻。
    """
    sent = out.get("request_sent_at")
    event_records = list(out.get("event_arrivals") or [])
    first_event_at = next((item.get("arrival_at") for item in event_records
                           if item.get("arrival_at") is not None), None)
    base = sent if sent is not None else first_event_at
    ledger["clocks"].append({
        "stream": stream_index, "request_sent_at": sent, "first_event_at": first_event_at,
        "elapsed_base": ("request_sent_at" if sent is not None
                         else ("first_event_at" if base is not None else None))})
    for record in event_records:
        ledger["events"].append(
            {"stream": stream_index, "at": int(record.get("at") or 0),
             "event": str(record.get("event") or ""),
             "class": str(record.get("class") or UNCLAIMED_EVENT_CLASS),
             "arrival_at": record.get("arrival_at"),
             "elapsed_ms": _elapsed_ms(record.get("arrival_at"), base)})
    for record in list(out.get("frame_arrivals") or []):
        ledger["frame_arrivals"].append(
            {"stream": stream_index, "at": int(record.get("at") or 0),
             "arrival_at": record.get("arrival_at"),
             "elapsed_ms": _elapsed_ms(record.get("arrival_at"), base),
             "chars": int(record.get("chars") or 0), "sha": str(record.get("sha") or ""),
             "prefix_break": bool(record.get("prefix_break"))})
    return ledger


def _first_screen_reading(events):
    """首枚**非-text 可见事件**：跨流按到达时刻取最早的那一枚。

    没量到时刻的事件一律不参与（没量到的东西不许冒充量到了）；一枚都没有 ⇒ 三格
    null / 空串，读作「这一轮的首屏没量到」，不读作「屏上什么都没有」。
    """
    timed = [item for item in events
             if item.get("arrival_at") is not None and _is_first_screen_event(item.get("event"))]
    if not timed:
        return {"first_visible_at": None, "first_visible_event": "", "first_visible_ms": None}
    first = min(timed, key=lambda item: (float(item["arrival_at"]), int(item.get("at") or 0)))
    return {"first_visible_at": first["arrival_at"],
            "first_visible_event": str(first.get("event") or ""),
            "first_visible_ms": first.get("elapsed_ms")}


def _arrival_readings(frames):
    """R223 / R222 的七格新列：逐帧与逐事件的到达时刻、首屏那一枚、每条流的钟、取回账。

    🔴 与 ``_frame_readings`` 分开写是有原因的，不是风格：那一枚是 R181 的尺，它的**返回形状**
    被 ``tests/test_r181_text_frame_ruler.py:467`` 的整字典对判钉着（把计数摘瞎之后「三帧与
    零帧同形」必须仍然成立）。本单的新列只开在**落盘这一层**（``_record_frames`` 把它们并进
    同一行），既有那枚函数一字未动 ⇒ 旧的反证与新的读数各管各的事。帧账一行的键集仍钉在
    ``FRAME_READING_KEYS``，七个新名字照旧由总控补，少补一个当场红。

    口径：``first_visible_*`` 只认 render 且名字不是 ``text`` 的最早那一枚（``EVENT_CLASSES``
    抄自前端 ``EVENT_CLAIMS``）；没量到时刻的记录一律不参与（禁止估算）。🔴 七格全部不进评分，
    也不参与 ``_frame_verdict``。
    """
    events = list(frames.get("events") or [])
    readings = {"frames": list(frames.get("frame_arrivals") or []),
                "events": events,
                "stream_clock": list(frames.get("clocks") or []),
                "queue": dict(frames.get("queue") or {})}
    readings.update(_first_screen_reading(events))
    return readings


def _new_frame_ledger():
    """一题的帧账本。一题可能不止一条流：/ask 之外还有 R123 甲案的若干轮 /approve。"""
    return {"text_frames": 0, "prefix_breaks": 0, "last_text_frame": "",
            "streams": 0, "max_stream_frames": 0, "per_stream": [],
            # R215：跨流的坏形证词。它**不进** per_stream —— 那一格的键集被
            # tests/test_r181_text_frame_ruler.py 逐字钉着，一多一少都算改尺。
            "break_frames": [],
            # R223：到达时刻的账（跨流，同样**不进** per_stream）。
            "frame_arrivals": [], "events": [], "clocks": [],
            # R222：队列道取回那一程的停表账。没走队列就是空字典，读作「这一题没取回过」。
            "queue": {}}


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
    # R223：这条流的到达时刻跟着折进账（只抄时刻，不参与上面任何一格的计数）。
    _fold_arrivals(ledger, out, stream_index)
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
    # R223 / R222：到达时刻与取回账作为**新列**并进这一行（上面那枚函数一字未动）。
    row.update(_arrival_readings(frames))
    row.update(readings)
    row["criterion_two_holds"] = _frame_verdict(readings)
    target = frame_ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


def _stream_once(question, session_id, idempotency_key, lane="", request_sent_at=None):
    out = _blank_observation(session_id)
    payload = {"message": question, "session_id": session_id, "idempotency_key": idempotency_key}
    if lane:
        payload["lane"] = lane
    # R223 时标的零点：``_pace()`` 放行这一题的那一刻（放行与 POST 之间只有构造请求体，
    # 没有任何 I/O）。🔴 这里**不另读一次表**：量具的假钟每读一次就走一格，多读一枚就把
    # R181 那 105 题重放的整条时间轴推走（PRE_R181_ANSWERS_SHA 当场红）—— 只加读数的东西
    # 必须复用已有的表戳，或在账上老实写明退到了哪一侧（stream_clock.elapsed_base）。
    out["request_sent_at"] = request_sent_at
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
    # R223：批准这一条流**没有**零点表可抄 —— ``_resolve_hitl`` 的循环里从前一次都不读表，
    # 今天也不许为了一枚读数新读一次（同上：会把 105 题重放的时间轴推走）。所以这一条流
    # 的账老实退到「本流第一枚事件」，并把它退到了哪一侧写进 stream_clock.elapsed_base。
    # 读法：批准轮的毫秒数都是「相对本流第一枚事件」，不是相对 POST。
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


#: R222 判据①：五枚终态各一枚 kind，外加三枚「没读到终局」各一枚。全部与 ``ok`` 不同名，
#: 全部可以在 sidecar / 帧账的 ``kind`` 那一列上直接统计（那一列的名字与顺序未动）。
#: 🔴 ``done`` 沿用 ``queued_polled`` 这个名字：``tests/test_r181_text_frame_ruler.py:322``
#: 钉着它，而它也是「相 2 第一枚真取回正文」那一格的历史对接口，换名就是抹账。
#: ``queued_cancelled`` / ``queued_dead`` 是这一单的病：从前它们不落任何名字，一路轮到
#: deadline，最后和「一帧都没到的空答题」共用同一枚 ``blank`` —— 既看不出白烧，也看不出
#: 后端其实已经明说过这一轮不会再有正文。
#: 写法纪律：这些字面必须以 ``status == "..."`` / ``status in ("...", ...)`` 留在
#: ``_poll_queue`` 的函数体里 —— 总控的量具量具（``scripts/r218_switch_rehearsal.py`` 的
#: ``adapter_stop_vocabulary``）就是按 AST 抠「与名为 ``status`` 的名字比较的字面」。改成查表
#: 或集合常量那一格读数当场瞎掉：那是「量具有牙」这句主张的一种新形状的假绿。
def _poll_queue(request_id):
    """把一条已入队的轮次读到**任何一枚终态**为止，回 ``(kind, answer, 取回账)``。

    三条口径，逐条对着判据写：

    ① 五枚终态全部停表（``done`` / ``cancelled`` / ``dead`` / ``expired`` / ``failed``），
       且逐枚一枚可区分的 kind；``cancelled`` / ``dead`` 的正文是空串 —— 🔴 后端说这一轮
       不会再有正文，量具就不许把它当成模型答完了（``kind`` 也不叫 ``ok``，见上表）。
    ② 瞬断不等于终态（与前端 R198/R202 同一族口径）：非 2xx / 连不通 / JSON 解不开
       **一律不是停表条件**，只记一次抖动接着轮。401 那一枚是可恢复的（令牌过期，
       ``login()`` 幂等，重登接着读），记成 ``relogins`` 单独一格，不与终态混读。
       载荷读不成对象（``body`` 不是 dict）同算抖动。
    ③ 白烧的天花板从 900 s 降下来，但**不是**把外圈一刀砍短：还在动的轮询不该被
       掐死（误伤一次就是一次假红），该掐的是「载荷不再变化」的那一族。所以两枚分开：
       ``QUEUE_STALL_SECONDS``（默认 300 s，理由在该常数的注释里）封顶无进展的等待，
       ``QUEUE_POLL_SECONDS``（900 s，未动）只封顶「状态一直在动」的外圈。
       代价读数：``cancelled`` / ``dead`` 一族 = 至多一枚轮询间隔（3 s）；
       无进展一族 = 300 s；两族都不再是 900 s。

    ``取回账`` 是那一段观测的账（轮了几次 / 抖了几次 / 重登几次 / 等了多久 / 最后读到什么），
    由 ``transport`` 折进帧账的 ``queue`` 那一格。🔴 它不进 sidecar（那一行的键集被
    ``tests/test_r123_hitl_approval.py:243`` 钉成甲案七键的子集），也不改 ``kind`` 之外
    任何一格的口径。取不到就是取不到：正文一律空串，不伪造、不估算。
    """
    book = {"polls": 0, "blips": 0, "relogins": 0, "final": "", "last_status": "",
            "wait_ms": 0.0, "stall_ms": int(QUEUE_STALL_SECONDS * 1000),
            "deadline_ms": int(QUEUE_POLL_SECONDS * 1000),
            "interval_ms": int(QUEUE_POLL_INTERVAL * 1000)}

    def _stop(kind, answer, final, now):
        """停表：结局 + 正文 + 这一段观测的账。``now`` 是本轮那一枚唯一的表戳。"""
        book["final"] = final
        book["wait_ms"] = round((now - zero) * 1000.0, 1)
        return kind, answer, book

    # 🔴 钟的纪律（与 R223 同一件事）：这一段一次都不许多读表。原件是「deadline 一枚 +
    # 每轮 while 一枚」，今天还是这个数：零点由 deadline 反推，无进展截止用本轮那枚 now
    # 起算，于是 stalled / deadline 两族各烧了多久都算得出来，而不必引入第二枚钟 ——
    # 量具的假钟每多读一次就走一格，多读会把 105 题重放的时间轴整条推走。
    # 抄本行（总控的预演件按原文钉它）：外圈截止只管「还在动」的那一族。
    deadline = time.time() + QUEUE_POLL_SECONDS
    zero = deadline - QUEUE_POLL_SECONDS
    stalled_at = None  # 无进展截止：第一次读到状态之后才起算
    signature = None   # 可观测进展：status / position / attempts 三样的快照
    now = zero
    while True:
        now = time.time()  # 每轮唯一一枚：与原件的 while 判定同一枚读数
        if now >= deadline:
            break
        if stalled_at is not None and now >= stalled_at:
            # 读到了状态，但载荷再也不动 ⇒ 这一族才是真白烧（300 s 封顶，不是 900 s）
            return _stop("queued_stalled", "", "stalled", now)
        try:
            with _open("/api/v1/queue/status/" + str(request_id), None, "GET") as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            if not isinstance(body, dict):
                raise ValueError("queue/status 答的不是对象")
        except urllib.error.HTTPError as exc:
            # 判据②：非 2xx 是**读不到**，不是**读完了**。401 换票接着读，其余原样重试。
            book["blips"] += 1
            if exc.code == 401:
                # 令牌过期是最常见的一枚可恢复抖动：换票接着读（login() 幂等，见 :132）。
                global _TOKEN
                _TOKEN = ""
                book["relogins"] += 1
                try:
                    login()
                except Exception:  # 登不回去也照样不停表：下一轮再试，另记一笔
                    book["relogin_failures"] = book.get("relogin_failures", 0) + 1
            time.sleep(QUEUE_POLL_INTERVAL)
            continue
        except (urllib.error.URLError, OSError, UnicodeDecodeError,
                json.JSONDecodeError, ValueError) as exc:
            book["blips"] += 1
            book["last_blip"] = type(exc).__name__
            time.sleep(QUEUE_POLL_INTERVAL)
            continue
        book["polls"] += 1
        status = str(body.get("status", ""))
        book["last_status"] = status
        failure = body.get("failure") if isinstance(body.get("failure"), dict) else {}
        mark = (status, body.get("position"), failure.get("attempts"))
        if mark != signature:  # 有任何一格在动 ⇒ 这不是白烧，重新起算无进展截止
            signature = mark
            stalled_at = now + QUEUE_STALL_SECONDS  # 用本轮那枚表戳起算，不再读一次
        if status == "done":
            result = body.get("result")
            if isinstance(result, str) and result.strip():
                return _stop("queued_polled", result, "done", now)
            # done 但 result 不是正文（None / 非 str / 全空白）：取回了个空，另立一枚 kind，
            # 不许与「取回了一份字」共用 queued_polled，也不许冒充 ok。
            return _stop("queued_done_no_bytes", "", "done_no_bytes", now)
        if status in ("cancelled", "dead", "expired", "failed"):
            # 后端自己宣布这一轮不会再有正文：读到就停（从前这两枚要烧到 deadline）。
            return _stop("queued_" + status, "", status, now)
        # queued / processing / cancel_requested / 任何不认得的字面 ⇒ 都不是终态，接着轮
        time.sleep(QUEUE_POLL_INTERVAL)
    # 外圈到点：一次状态都没读到过 = 这一题根本没读通（另立 kind，不并进 stalled）
    return _stop("queued_no_status" if not book["polls"] else "queued_deadline",
                 "", "no_status" if not book["polls"] else "deadline", now)


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
        pacing = _pace()  # R223：这一枚就是「发出 POST 的一刻」（不另读表）
        try:
            tier = str(row.get("tier", "")).strip()
            lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier == DECLARE_LANE_TIER else ""
            out = _stream_once(str(row["question"]), uuid.uuid4().hex, uuid.uuid4().hex,
                               lane, request_sent_at=pacing)
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
        from_queue = out["queued"] is not None
        if from_queue:
            # R222：kind 由停表那一层给（五枚终态 + 三枚没读到终局，逐枚可区分），
            # 取回那一程的账折进帧账的 queue 那一格。
            kind, answer, frames["queue"] = _poll_queue(out["queued"].get("request_id"))
            first_token_at = None  # 后台跑的首字观测不到 ⇒ null（采集器允许 null，禁止估算）
        # 🔴 走过队列道就不许再被前台那枚 error 帧或那枚 cancelled 帧换掉 kind：后端已经
        # 明说过这一轮的结局，拿一条没送达的旁证去改写它，量的就不是同一件事了。
        if not answer.strip() and out["error_text"].strip() and not from_queue:
            answer, kind, evidence = out["error_text"], "error_event", []
        if not answer.strip():
            if not from_queue:
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
