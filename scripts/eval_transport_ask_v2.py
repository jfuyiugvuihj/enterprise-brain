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
   自 R259 起再多一枚 ``queued_awaiting_approval``（挂起在等人批准的那一轮）⇒ 共十枚，
   自 R447 起再多一枚 ``queued_approved``（队列道那轮挂起被批准到终答）⇒ 共十一枚；
   🔴 新这一枚只活在停表**之后**的那一层：``_poll_queue`` 交的停表词表与那十枚读数一字未动。
   旧轮次一枚也不可能有
   （本树实取：run6 帧账 kind 只有 ``ok`` / ``approved_ok`` / ``error_event``，run7 只有
   ``ok`` / ``approved_ok``）；(b) 到达时刻与 ``queue`` 那几格自 R223 / R222 起才存在，旧帧账
   原件（``docs/testing/sidecar-run6-frames.jsonl`` 十三格、``sidecar-run7-frames.jsonl``
   十五格）里没有它们 ⇒ 拿旧件重放只会长出**空列**，不许读成「当年零停表」，也不许读成
   「当年无断流」。断流的时刻与首屏的时刻从 run8 起才是量得出来的两件事。

11. R259（09-26）认队列那枚新终态：R254 把挂起在 HITL 的那一轮从 ``done`` 改口成
    ``awaiting_approval``（``result`` 从此是 null，不再拿一句 37 字挂起文案冒充正文），而量具
    不认得这枚字 ⇒ 它落在「未识别状态」那一族里，一路轮到 ``QUEUE_STALL_SECONDS`` 才落
    ``queued_stalled``。09-25 那窗报告档 20 题有 11 题挂在这一枚上 ⇒ 下一扇窗要白烧约 55
    分钟，且 D-1/D-2/D-3 三格读数全被污染。今天读到就停（kind = ``queued_awaiting_approval``，
    与 ``queued_polled`` / ``queued_done_no_bytes`` 三枚互不冒充），并且不喂「零字节超阈值停窗」
    那把闸（产品结局，与 ``_APPROVAL_FAILURES`` 同口径）。同一天把 ``/queue/status`` 多交的那批
    终态读数折进取回账新格 ``queue.terminal``（``_terminal_readout``）：D-2「客户端读没读到
    token」与 D-3「读没读到出处」从此**有字段可算**，不必再事后翻日志。三条诚实口径写在
    那枚函数上：说不出 ⇒ None（不拿 0 或空表冒充「查过，是零」）、载荷在位而解不开 ⇒ 另一枚
    形状、``authoritative: false`` ⇒ 原样进账。🔴 五枚既有终态的 kind 与语义一字未改；sidecar
    那一行的键集、帧账那一行的键集一个字没多（读数只长在 ``queue`` 那一格里）。
12. R447（09-28）队列道终局：批准轮必须走、出处必须随答案交回。R259 让量具**认得**那枚
    ``awaiting_approval`` 就停表（修掉了约 55 min 白烧），但它停在那一格上**一步没走** ——
    run9c 真机实测 20 枚报告档里 11 枚交回 ``queued_awaiting_approval`` + 空正文，而可读面
    ``approval_present=true`` / ``approval_steps=["export"]`` / ``approval_ledger_status="awaiting"``
    / ``approval_notice_chars=37`` 四格全在账上，批准端点一次都没打。今天三件事：
    ① 队列道读到挂起 ⇒ 按同一契约批准到终答（``POST /api/v1/approve``，同一 session_id、同一
      Bearer token，走法复用 ``_resolve_hitl``，不新造第二套）；取不到终答记 ``approval_failed``
      （正文空、出处空、sentinel=true），R123 甲案口径一字不变。legacy 那一路一起治：旧行的
      ``result`` 逐字就是那句 37 字挂起文案，而可读面的 ``answer_is_park_notice`` 是服务端
      现算的真读数（R254 兼容节）⇒ 「取回了一份字」不等于「取回了一份终答」，那一枚也进批准轮。
      🔴 那句挂起文案一个字都不许进交回评分器的正文面（R254 判据① 口径不变）。
    ② 批到终答落新 kind ``queued_approved``：与既有十枚 ``queued_*`` 一枚都不混，不冒充
      ``queued_polled``（那枚说的是「从队列 ``result`` 取回了一份字」），也不冒充同步道的
      ``approved_ok``（那枚说的是「同步流道挂起后被批准」）。
    ③ 出处随答案交回：后台那一轮的 ``sources`` 只活在 ``/queue/status`` 的终态载荷里（前台回执流
      一帧 sources 都没有：run9c 实测「流内 sources 事件 0/20」），而 ``_terminal_readout`` 从前
      只把**枚数**折进取回账 ⇒ 7 枚可读面 ``sources_n>0`` 的题 ``answers.evidence`` 全空。今天把
      那一身行搬进交回评分器的 ``evidence``（行形与同步道那枚 ``sources`` 事件同源同形：
      ``app/api/v1/chat.py::queue_turn_sources`` 用的就是 ``_collect_document_sources`` +
      ``_authorized_source_rows``，不新增放行分支）。出处行**不进帧账**：帧账的口径一直是计数与
      指纹进账、客户正文不进账（R181 的 ``last_frame_sha`` 同办）。
    🔴 同步流道那四枚 kind（``ok`` / ``approved_ok`` / ``hitl`` / ``error_event``）的读数与字段
    逐字节不变：run2..run9 的可比性不许打断。sidecar 那一行的键集、帧账那一行的键集一个字没多。
    队列道 ``first_token_at`` 仍为 null（后台那一程的首字观测不到；批准腿的到达时刻只进帧账的
    ``events`` / ``stream_clock``，不冒充 ``first_token_at`` 那一列的第二种零点）。
13. R471（09-29）判据② 补上「正文出现两遍」那一腿：六枚合取对**跨流重复送达**全读绿 ——
    批准腿把挂起轮已经交上屏的那份正文又发一遍时，``_fold_frames`` 的前缀单调只在同一条流内判，
    那一枚重发在原始账上常常一枚坏形都不长（run9 在册原件里 ``chart-04`` / ``insight-07`` 两枚
    正是 ``prefix_breaks == 0``），于是六枚合取一枚都不拦：``uncorrected_breaks == 0``、不缺字、
    不多字、末帧覆盖终答、帧数与单流最大帧数都 >1 —— 而客户在屏上把同一轮的答案读两遍
    （成因逐字抄自 ``app/api/v1/chat.py::_ApprovedAnswerStream`` 那页病历）。今天合取里加第七枚
    ``cross_stream_repeat_frames == 0``：口径在 ``_cross_stream_repeats``，沿到达顺序逐枚比 R223
    那一列**逐帧指纹**（帧账里既有的 ``frames``），一枚非空帧的字若在更早的一条流里出现过就记一次
    重复送达。🔴 丙案（总控 09-29 裁定一）：这一格**不落成新列** —— 帧账一行的键集是四枚在册钉
    「对判，不是子集」的闸（``tests/test_r181_text_frame_ruler.py:433`` ／
    ``tests/test_r223_frame_arrival_clock.py:612`` ／
    ``tests/test_r259_awaiting_approval_stops_the_watch.py:162`` ／ ``tests/_r259_queue_ruler.py:54``），
    不许为一枚派生数去开这一列。证词只在判定那一刻由 ``_record_frames`` 从行内指纹现场派生后交给
    尺子；复算那一路（r239 与 caliber readout）同样现场派生，两边都不往账上添一枚字。
    🔴 只算跨流：同一条流里「末片帧与收尾帧同文」是 ``app/api/v1/chat.py`` 自己写明的既有形状
    （一条腿流完再落终答，covering 分支整段替换 ⇒ 屏上始终只有一份正文）；run9 那 105 行里 66 行
    带这一形、其中 64 行在册读绿 ⇒ 把它一起定罪是误伤，不是治尺。
    🔴 本腿不吃 ``prefix_breaks``，R215「豁免只把坏形分家」那枚恒等式一字不动，原始账一格不漂。
    方向是**变严**：R471 之前的帧账不存这格证词，本尺因此**不重判**当年读数（与
    ``scripts/r239_stream_gap_offline_audit.py`` 拿老账退回 ``prefix_breaks`` 同一条纪律）。
    口径、影响面与立案项见 ``docs/testing/r471-verdict-caliber-2026-09-29.md``。

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
#: ===== R632 缺陷三：量具这一侧缺的两条腿（两枚开关，默认都关）===================
#: 上面那一枚只替**与它同名的一档**补 lane，其余两档的题一题都不补 ⇒ 一扇窗里永远只有
#: 一档在账上带得出档位名。EVAL_DECLARE_LANE_PER_TIER 把口径换成「按每一行自己的档位补」：
#: 开 = 三档逐行各补各的，关 = 逐字节回到上面那一句（旧口径由牙钉着，见抬头判据）。
#: 🔴 翻它的代价要写在盘面上：报告档 20 题从此带 lane=report，容器侧 REPORT_LANE_VIA_QUEUE
#: 也开着时它们就改走队列道 —— 时延换了代，这一窗的 A① 读数不许与 run18 / run20k 并表。
#: EVAL_RECORD_LANE_READOUT 是第二条腿，而且它**不改载荷**：只把服务端响应头里的档位读数
#: （app/api/v1/chat.py:1502-1513 发的三枚头）抄进第三份证据件。想在不换代的前提下把 105 题
#: 逐题档位名读出来，下一窗只开这一枚就够；两条腿各自独立，默认都关 = 一件新产物都不落。
LANE_PER_TIER_ENV = "EVAL_DECLARE_LANE_PER_TIER"
LANE_RECORD_ENV = "EVAL_RECORD_LANE_READOUT"
#: 开关取值的字面与产品同源（app/api/v1/chat.py 的 REPORT_LANE_ON_VALUES），本件不另造一套；
#: 同源性由 tests/test_r632_transport_lane_switches.py 现读 chat.py 的 AST 对判，不靠抄。
LANE_SWITCH_ON_VALUES = {"1", "true", "yes", "on"}
#: 服务端档位读数的三枚头名。产品侧真源是 app/api/v1/chat.py 里那三枚常量；按在册纪律本件
#: 不引产品码（tests/test_r123_hitl_approval.py:395 那一枚源码级钉就是这个形状），所以这里是
#: 抄字面 + 钉同源，同源性由 tests/test_r632_transport_lane_switches.py 现读产品源码对判。
EFFECTIVE_LANE_HEADER = "x-effective-lane"
DECLARED_LANE_HEADER = "x-declared-lane"
LANE_SOURCE_HEADER = "x-lane-source"
#: 档位名读数的落点键。读数**不并进 sidecar 也不并进帧账**：那两本件的键集被在册闸钉成
#: 对判（tests/test_r181_text_frame_ruler.py 与 tests/test_r223_frame_arrival_clock.py 各自
#: ``set(row) == JOIN_KEYS | ...``，另加 tests/test_r259_awaiting_approval_stops_the_watch.py
#: 与 tests/_r259_queue_ruler.py），往里加一列当场红 ⇒ 这一格只能长在第三份件上。
LANE_LEDGER_ENV = "EVAL_LANE_LEDGER"


def _lane_switch(name):
    """从进程环境读一枚布尔开关：口径与产品那枚 _report_lane_via_queue_enabled 逐字相同。"""
    return os.getenv(name, "").strip().lower() in LANE_SWITCH_ON_VALUES


#: 与 DECLARE_LANE_TIER 同一枚纪律：import 期读一次表，一窗之内不重读（读表腿由 R632 那件钉）。
DECLARE_LANE_PER_TIER = _lane_switch(LANE_PER_TIER_ENV)
RECORD_LANE_READOUT = _lane_switch(LANE_RECORD_ENV)
#: ===== R642 D-3：批准之后那一次 ``/queue/status`` 重读（口径见抬头第 14 条）=========
#: 🔴 默认关：关着时一枚状态读都不许多打、两份证据件的字节逐字回到今天（旧口径由
#: tests/test_r642_post_approval_terminal_readback.py 钉死）；开着时批准轮走完之后多打**一发**
#: GET。开窗人要读 D-3 那一格就得带上它 —— 不带不是「读到了零枚出处」，是这一格今天没量过。
#: 读表时机与 R632 那两枚同一条纪律：import 期读一次，一窗之内不重读。
POST_APPROVAL_READBACK_ENV = "EVAL_POST_APPROVAL_READBACK"
RECORD_POST_APPROVAL_TERMINAL = _lane_switch(POST_APPROVAL_READBACK_ENV)
APPROVAL_FAILED_SENTINEL = os.getenv(
    "EVAL_APPROVAL_FAILED_SENTINEL", "<approval-failed-no-terminal-answer>")
#: R447 判据②：队列道那一轮挂起被批准到终答之后落的 kind。它与既有十枚 ``queued_*`` 一枚都
#: 不混，也不冒充同步道的 ``approved_ok``（那一枚说的是「同步流道挂起后被批准」）。
#: 写在这里而不写进 ``_poll_queue`` 的停表族里：停表那一层说的还是「一步没走」那句真话。
QUEUED_APPROVED_KIND = "queued_approved"
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


def lane_ledger_path():
    """R632 档位名读数件的落点：``EVAL_LANE_LEDGER`` 优先，否则跟着 SIDECAR（``-lane`` 尾缀）。

    与 ``frame_ledger_path()`` 同一枚纪律：**调用期**读表，钉在 import 期就把 runbook §8
    「产物落仓外」的纪律绕过去了（跟着 SIDECAR 走，开窗只设一个变量就不会把它漏在仓内）。
    """
    override = str(os.getenv(LANE_LEDGER_ENV) or "").strip()
    if override:
        return Path(override)
    return Path(SIDECAR).with_name(Path(SIDECAR).stem + "-lane.jsonl")
# 空 dict = 无视 http_proxy/HTTPS_PROXY，等价 curl --noproxy "*"（runbook §6：Clash 会劫 127.0.0.1）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_TOKEN = ""
_LAST_CALL = 0.0
_BLANKS = 0
_PARKED = 0  # R259：本进程里挂起在等人批准的题数（与 _BLANKS 分账，见 transport）
_APPROVAL_FAILURES = 0
_QUEUED_APPROVED = 0  # R447：队列道那一路批到终答的题数（与上面两枚分账）


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
                # R447：只给 transport 的那一格不落帧账（键集一字不许多，出处行不抄进第二份件）。
                "queue": _ledger_queue_cell(frames.get("queue"))}
    readings.update(_first_screen_reading(events))
    return readings


def _new_frame_ledger():
    """一题的帧账本。一题可能不止一条流：/ask 之外还有 R123 甲案的若干轮 /approve。"""
    return {"text_frames": 0, "prefix_breaks": 0, "last_text_frame": "",
            "streams": 0, "max_stream_frames": 0, "per_stream": [],
            # R215：跨流的坏形证词。它**不进** per_stream —— 那一格的键集被
            # tests/test_r181_text_frame_ruler.py 逐字钉着，一多一少都算改尺。
            "break_frames": [],
            # R642 甲案：每条流**自己交付**的那份字（``_consume`` 末帧覆盖前帧之后的读数）。
            # 🔴 与 break_frames 同一格纪律：只活在内存里、只喂第④条的流级比对，一列都不进账
            # —— per_stream 那一格多带一枚指纹就把 run6 的逐位复算打断（原始账不许漂）。
            "stream_deliveries": [],
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
    # R642 甲案：这条流交付的那份字跟着折进内存账（第④条流级比对的比对对象）。
    # 🔴 只喂判定，不落盘、不计数：原始账那几格与帧账一行的键集一字未动。
    ledger["stream_deliveries"].append(str(out.get("answer") or ""))
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


def _stream_level_correction(frame_text, answer_text, deliveries, stream):
    """R642 甲案：豁免四条件里第④条的**流级**读法（判定层今天唯一的改动点）。

    轮级那一条（``frame_text == answer_text``）一字未动，仍排在最前面 —— 它讲的是「收尾那次
    整段替换，屏上换成的正是交回评分器的那份字」。今天补的是挂起轮内换源那一形：三条
    **同时**成立才算，缺一条就不算 ——
      (a) 断裂住在**非最后一条**流里。末流那一族的坏形照旧只许用轮级那一条判，本条不给它
          开后门（R215 当年在册用例全是「一条 /ask 流」的形状，那一族的读法一字不改）。
      (b) 断裂帧逐字等于**它所在那一条流**自己交付的那份字 —— 同一条流内不许换源。这一条
          真有牙：末帧是一枚空帧时 ``deliveries[stream]`` 仍是该流最后一枚非空帧的字，
          两者不等就豁免不了（``_consume`` 的 ``if content:`` 那一条口径）。
      (c) 本轮终答以它为前缀 —— 批准腿是接着往下写，不是屏上换了第二份字。🔴 这一条是闸：
          放宽它就是把「换源换成了另一份答案」洗成「一次纠正」（R614 §4 的守门用例，
          本单落成常驻牙）。同文重发那一形不归它管，由 R471 的派生格
          ``cross_stream_repeat_frames`` 独立拦，两格不许互抄。
    🔴 ``deliveries`` 缺席（复算入口、调用方没折过任何流、越界流号）⇒ 一律不豁免：
    宁可少豁免一次，不可多豁免一次。本函数只读内存里那一份证词，一列都不往账上添。
    """
    if frame_text == answer_text:
        return True  # 轮级那一条，原样
    if not isinstance(deliveries, list) or stream < 0 or stream >= len(deliveries):
        return False
    if stream >= len(deliveries) - 1:
        return False  # (a) 末流：只认轮级
    if frame_text != deliveries[stream]:
        return False  # (b) 同一条流内换了源
    return bool(frame_text) and answer_text.startswith(frame_text)  # (c) 终答以它为前缀


def _corrective_readings(frames, answer):
    """R215 判据② 的豁免账：本轮几枚坏形是「受控纠正替换」，剩下几枚是真断流。

    四条**同时**成立才豁免一枚，缺一条就不豁免 —— 量具多豁免一次，判据② 就永久假绿一次：
      ① 它是**这一条流的最后一枚** text 帧。中途坏形说明流被截断过，收尾救不回来；
      🔴 R642 甲案只换第④条的**比对对象**（轮级 → 流级），① ② ③ 一字未动，
      ``prefix_breaks`` 与「豁免只把坏形分家」那枚恒等式一字未动，原始账一格不漂。
      ② 本轮至多一枚。一题里出现第二次换源，那已经不是「一次纠正」；
      ③ 它前面紧邻一枚 ``step(tool=answer_correction, status=running)``。光靠字节流的形状
         （短一截、换个头、又变长）蒙不过去 —— 屏上那次整段替换是被这枚 step 武装的；
      ④ 它逐字等于本轮交回评分器的 ``answer``（轮级，原样），**或** R642 甲案的流级三条
         同时成立：(a) 它所在那一条流不是最后一条流、(b) 它逐字等于**它所在那一条流**自己
         交付的那份字、(c) 本轮终答以它为前缀。判法在 ``_stream_level_correction``。
         🔴 跨流不许互相比源：拿批准腿的终答去比挂起轮的末帧，两窗 19/19 恒假（R614 §2），
         这一族的坏形因此从来没有过一次豁免 —— 那是量具失明，不是产品断流。
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
        if not _stream_level_correction(str(record.get("text") or ""), answer_text,
                                        frames.get("stream_deliveries"),
                                        int(record.get("stream") or 0)):
            continue  # ④ 轮级/流级两条比源都不成立：屏上没真替换成交付的那份字
        granted += 1
    total = int(frames.get("prefix_breaks") or 0)
    return {"corrective_replacements": granted, "uncorrected_breaks": total - granted}


def _cross_stream_repeats(frame_records):
    """R471 判据② 的重复送达账：这一轮里有几枚正文是「后一条流把先前发过的那份字又发一遍」。

    🔴 入参是**行内既有那一列** R223 逐帧指纹（``_arrival_readings`` 交回的 ``frames``，落盘之后就是
    帧账的同一格），本函数只从它**现场派生**，自己**不落成新列**（丙案，总控 09-29 裁定一：帧账一行
    的键集是「对判不是子集」的闸，不许为一枚派生数去改那四枚在册钉）。派生不出＝这一格今天没量过，
    调用方按 ``REPEAT_DELIVERY_UNMEASURED`` 读，🔴 不重判当年的读数。

    病根逐字抄自产品自己那页病历（``app/api/v1/chat.py::_ApprovedAnswerStream``）：批准腿把同一条
    生成腿重跑一遍，于是又交出一枚整段正文，而屏上此刻站的已经是挂起轮那一份；
    ``frontend/src/lib/sessions.js::consumeSseStream`` 每次从空 ``segments`` 起步，那枚同文帧落的
    正是**追加**分支 —— 客户把同一轮的答案读两遍。帧账上的形状就是病历点名的那一格：
    ``text_frames > max_stream_frames`` 且**逐帧指纹重合**。🔴 后者在 R471 之前一枚都没人量，
    所以那一形在六枚合取上全读绿：重发常常连一枚坏形都不长（前缀单调只在同一条流内判）。

    口径：沿折进账的到达顺序逐枚走，一枚非空帧的指纹若在**更早的一条流**里出现过，记一次。
    三条边界都是故意的，不许顺手放宽：
      * 🔴 只算跨流。**总控裁定原话（2026-09-29，署名总控）**：「同一条流内末片帧与收尾帧同文」
        不判成「出现两遍」：R215 那四条例外（末帧／本轮至多一枚／紧邻 arm／逐字等于终答）裁的就是
        这一形，收它等于推翻在册裁定；且 A② 要治的是缺字与断流，跨流重复才是 R464 治的批准腿病形。
        （工程侧旁证：``app/api/v1/chat.py`` 那条 covering 注释 —— 一条腿流完再落终答，屏上始终只有
        一份正文，整段替换之后屏上没有第二份；把它一起定罪会误伤 run9 那 64 行在册绿。）
      * 空帧（``chars == 0``）不携带任何正文，谈不上重复，不参与。
      * 指纹只用 R223 逐帧那一列（``frames[].sha``）里的现成读数，本函数**只派生不另数**：
        把 ``_count_text_frame`` 摘瞎，逐帧那一列跟着空，这一枚证词一起归零 —— 与
        ``tests/test_r223_frame_arrival_clock.py`` 那条「派生而非另起一把尺」同一纪律。

    🔴 R507 两形分开（落码向本段承论对齐，不再摇假零）：
    帧在而一枚逐帧指纹都拿不到（量具被摘瞎那一窗）⇒ 回 ``None``：这一格今天**没量过**，不许报 0 冒充量过
    （事故 #73 那一族假零：摘瞎窗口读成「量过了且没重合」）。拿到了指纹且确实没有跨流重合⇒ 才回 0。
    尺子对 ``None`` 与 0 同样不追加定罪也不洗白（``_frame_verdict`` 缺省 ``REPEAT_DELIVERY_UNMEASURED``），但纸面上两形必须分家。
    入参不是帧表或枚数为零（空读那一形）仍照在册现状回 0：那一形钉在
    ``tests/test_r471_second_copy_of_the_answer_body_is_not_a_pass.py:449``，不在本单写域（残余分歧见 ``docs/testing/r507-blind-instrument-returns-none.md``）。
    """
    records = list(frame_records or [])
    if records and not any(str(rec.get("sha") or "") for rec in records):
        return None  # R507 两形分开（一）：帧在而无一枚指纹 ⇒ 未量，不许报 0 冒充量过
    earliest = {}
    repeats = 0
    for record in records:
        if int(record.get("chars") or 0) <= 0:
            continue  # 空帧没有正文，谈不上「出现两遍」
        sha = str(record.get("sha") or "")
        if not sha:
            continue  # 没指纹就没证词：不许拿缺证词当证据（与 R215 判据① 同一条纪律）
        stream = int(record.get("stream") or 0)
        if sha in earliest and stream > earliest[sha]:
            repeats += 1  # 同一份字在更早的一条流里已经上过屏：本轮第二次送达
        earliest[sha] = min(stream, earliest.get(sha, stream))
    return repeats


def _frame_readings(frames, answer):
    """判据② 的四枚读数，外加逐字比对用的两枚指纹。🔴 没有任何一枚进评分。

    R215 起再多两格（``corrective_replacements`` / ``uncorrected_breaks``）：照样一枚都不进
    评分，也不动前面那几格的取值口径。🔴 帧账一行的键集自本单起多这两格，那份键集钉在
    ``tests/test_r181_text_frame_ruler.py`` 的 ``FRAME_READING_KEYS`` —— 那枚文件不在本单
    写域，两个名字由总控补进去（少补一个就是当场红，不会静默漏过）。

    R471 的第七枚合取**不进本函数的返回值**（丙案，总控 09-29 裁定一）：这一枚证词由
    ``_cross_stream_repeats`` 在判定那一刻从行内既有那一列逐帧指纹现场派生，所以帧账一行的键集
    一格不多 —— ``FRAME_READING_KEYS``／``OLD_CELLS``／``_r259_queue_ruler`` 那三份名单与四枚
    「键集是对判」的在册钉全部原样不动，本函数自己的形状也一格未改。新口径在账上的唯一可见处
    是它折出来的 ``criterion_two_holds``；名单只有一处随本单升级 ——
    ``tests/test_r218_ruler_self_calibration.py:81`` 的 ``verdict_key_set`` 从 6 枚升到 7 枚。

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


#: 判定视图里读不到 ``cross_stream_repeat_frames`` 这枚证词时的缺省：0 枚，读作「这一格今天没量过」。
#: 🔴 谁会读不到？(a) R471 之前那四次收窗（run2→run9）落盘的老行 —— 当年的读数一律**不重判**，
#: 既没资格追加定罪，也不许把当年的红字洗白（同 ``scripts/r239_stream_gap_offline_audit.py`` 拿老账
#: 退回 ``prefix_breaks`` 那一条纪律）；(b) 任何只带读数、不带逐帧指纹的复算入口。R471 之后的新账
#: 由 ``_record_frames`` 在判定那一刻从行内那一列逐帧指纹现场派生（丙案：不落成新列）⇒ 每一扇
#: 新窗都吃得到这一腿，而那四份在册原件的读数一格不改。
REPEAT_DELIVERY_UNMEASURED = 0


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

    ⚠️ 口径变更二（R471，方向同样是**变严**）：合取里再加第七枚 ``cross_stream_repeat_frames == 0``
    —— 同一轮里**后一条流把先前已经发过的那份正文又发一遍**，就不算「流式逐字无缺」。这一形
    不吃 R215 那枚豁免，也不靠豁免才拦得住：``_fold_frames`` 的前缀单调只在同一条流内判，跨流重发
    常常一枚坏形都不长（run9 在册原件里 ``chart-04``／``insight-07`` 两枚正是 ``prefix_breaks == 0``、
    ``missing_chars``／``extra_chars`` 同为 0、末帧覆盖终答、``uncorrected_breaks == 0``）—— 六枚合取
    全读绿，而屏上摆着两份答案。🔴 本腿不动 ``prefix_breaks``，也不动「豁免只把坏形分家」那枚
    恒等式。🔴 丙案（总控 09-29 裁定一）：这枚证词**不是帧账的一格** —— 本尺只读调用方在判定那一刻
    递进来的派生值（``_record_frames`` 从行内既有那一列 R223 逐帧指纹派生），所以帧账一行的键集一格
    不多，那四枚「键集是对判，不是子集」的在册钉一个字不改。R471 之前那四扇窗的老行递不进证词
    ⇒ 当年读数一律**不重判**（缺省见 ``REPEAT_DELIVERY_UNMEASURED``；离线复算件
    ``scripts/r239_stream_gap_offline_audit.py`` 同口径：派生不出就照当年的读数交回）。
    实测影响面（09-29 现取 ``docs/testing/sidecar-run9-frames.jsonl`` 那 105 行的逐帧指纹，逐档）：
    问答 50 枚 0 翻｜分析 35 枚翻 2（``chart-04``／``insight-07``）｜报告 20 枚 0 翻
    （``tool-04`` 本来就红）；``text_frames > max_stream_frames`` 那 18 枚换源形里其余 15 枚交的是
    新字，一枚不误伤。逐档表、不重判那句的完整理由与立案项见
    ``docs/testing/r471-verdict-caliber-2026-09-29.md``。
    """
    return bool(readings["text_frames"] > 1
                and readings["max_stream_frames"] > 1
                and readings["uncorrected_breaks"] == 0
                and readings["missing_chars"] == 0
                and readings["extra_chars"] == 0
                and readings["last_frame_covers_answer"]
                # R471：正文在同一轮里出现两遍 ⇒ 不算「流式逐字无缺」。老账缺证词时读默认值。
                and int(readings.get("cross_stream_repeat_frames",
                                     REPEAT_DELIVERY_UNMEASURED) or 0) == 0)


def _record_frames(row_id, kind, attempt, session_id, frames, answer, sentinel):
    """一题一行的帧证据件：与 sidecar 同一次落盘动作里写，join 键 ``id``。

    🔴 侧车一个字都不动：``tests/test_r123_hitl_approval.py:243`` 把 sidecar 除九键之外的
    键集钉成甲案那七键的子集，读数并进那一行即红，而那枚文件不在 R181 写域。
    """
    row = {"id": row_id, "kind": kind, "attempt": attempt, "sentinel": sentinel,
           "session_id": session_id, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    readings = _frame_readings(frames, answer)
    # R223 / R222：到达时刻与取回账作为**新列**并进这一行（上面那枚函数一字未动）。
    arrivals = _arrival_readings(frames)
    row.update(arrivals)
    row.update(readings)
    # R471 丙案（总控 09-29 裁定一）：第七枚合取的证词**不落成新列**，判定这一刻从行内既有那一列
    # R223 逐帧指纹（``arrivals["frames"]``，也就是落盘之后的 ``row["frames"]``）现场派生，只交给尺子。
    # 🔴 顺序是有意的：这一行必须排在 ``row.update(readings)`` **之后** —— 排到前面那枚证词就会被写进
    # 落盘行，撞上 test_r181:433 / test_r223:612 / test_r259_awaiting_approval:162 / _r259_queue_ruler:54
    # 那四枚「键集是对判」的闸，而这一列今天不许开（丙案）。
    readings["cross_stream_repeat_frames"] = _cross_stream_repeats(arrivals["frames"])
    row["criterion_two_holds"] = _frame_verdict(readings)
    target = frame_ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


def _lane_headers_from_response(resp):
    """从 /ask 的响应头抄服务端那一侧的档位读数：只读头，一个字节都不碰流本体。

    🔴 三枚头的纪律与产品同源（app/api/v1/chat.py:1502-1513「读数缺格就少发一枚头，不发假值」）：
    取不到就交 ``None``，不发空串、不折算成零、不拿发出去的那一枚冒充读回来的那一枚。
    ``headers_readable`` 单独说一件事 —— 这一枚假出口/真出口到底有没有头可读。测试里那些
    只带 ``read()`` / ``__iter__()`` 的假件根本没有 ``headers`` 这一格，那种「读不到」既不是
    产品的锅也不是档位为空，把它记成空档就是在制造第三态。
    """
    headers = getattr(resp, "headers", None)
    getter = getattr(headers, "get", None)
    readout = {"headers_readable": callable(getter), "effective_lane": None,
               "declared_lane": None, "lane_source": None}
    if not callable(getter):
        return readout
    for key, header in (("effective_lane", EFFECTIVE_LANE_HEADER),
                        ("declared_lane", DECLARED_LANE_HEADER),
                        ("lane_source", LANE_SOURCE_HEADER)):
        value = getter(header)
        text = str(value).strip() if value is not None else ""
        readout[key] = text or None
    return readout


def _record_lane_readout(row_id, session_id, sent_lane, readout):
    """一题一行落第三份件（R632 缺陷三的量具半张）。开关没开就一个字节都不写。

    join 键是 ``session_id``：每次尝试都现造一枚新会话，重试的那一发不会与终答那一发撞键，
    而帧账那一行本来就带着 ``session_id``（``JOIN_KEYS`` 里的一格）⇒ 侧车 id ← 帧账 ← 本件
    三跳都是精确键，不靠顺序、不靠题面。``id`` 只当方便人眼的旁注，读数以 session 为准。
    """
    row = {"id": row_id, "session_id": session_id,
           "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "sent_lane": sent_lane or None,
           "effective_lane": readout.get("effective_lane"),
           "server_declared_lane": readout.get("declared_lane"),
           "lane_source": readout.get("lane_source"),
           "headers_readable": bool(readout.get("headers_readable"))}
    target = lane_ledger_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        print(json.dumps(row, ensure_ascii=False), file=fh)


def _stream_once(question, session_id, idempotency_key, lane="", request_sent_at=None,
                 row_id=""):
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
        observed = _consume(resp, out)
        # R632 第二腿：档位读数只在这一发真的拿到响应之后才抄（没打通的那一发没有头可读，
        # 也不该有一条读数冒充「服务端说它是某档」）。🔴 默认关：关着时一件新产物都不落。
        if RECORD_LANE_READOUT:
            _record_lane_readout(row_id, session_id, lane, _lane_headers_from_response(resp))
        return observed


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


def _resolve_hitl(row_id, session_id, steps, frames=None, success_kind="approved_ok"):
    """R123 甲案：把挂起轮批准到终答（判据 1），拿不到终答就照实记 approval_failed（判据 3）。

    ``frames`` 是 R181 判据② 那一题的帧账本：恢复流的帧并进同一本账（不传就现造一本，
    单测可以只管这一条流）。评分口径一个字没动。

    ``success_kind``（R447 判据②）只改**批到终答那一枚的名字**：缺省 ``approved_ok`` 就是
    同步流道那一路，逐字节不变；队列道传 ``QUEUED_APPROVED_KIND``，为的是「哪条道批的」在
    ``kind`` 那一列上读得出来 —— 批到终答不等于从队列 ``result`` 取回了一份字，两枚不互冒充。
    失败那一支仍然叫 ``approval_failed``：两条道共用同一枚失败名，R123 甲案的口径不分家。

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
                    "kind": success_kind, "sentinel": False, "approved": approved,
                    "rounds": rounds, "http_status": http_status, "error": ""}
        error = "approve 200 仍无终答：" + (out["error_text"].strip() or "恢复流里没有 text 事件")
        break
    if not error:
        error = "批准 " + str(rounds) + " 轮后仍停在审批闸，没有终答（上限 EVAL_APPROVAL_ROUNDS）"
    return {"answer": APPROVAL_FAILED_SENTINEL, "evidence": [], "first_token_at": None,
            "steps": steps, "kind": "approval_failed", "sentinel": True, "approved": approved,
            "rounds": rounds, "http_status": http_status, "error": error}


#: ==================== R259：把队列终态读数折进取回账 ====================
#: R254 之后 `/api/v1/queue/status/{request_id}` 在 `done` / `awaiting_approval` 两枚状态下多交
#: 一批读数（契约 `docs/api/contract-v1.md` 的 §Structured terminal readout (2026-09-25, R254)）：
#: `terminal_state` / `answer_present` / `sources_present` / `sources` / `sources_error` / `usage`
#: / `approval` / `terminal_schema` / `worker_status` / `scope_reason_code` / `terminal_note`。
#: 量具从前只看 `status` 与 `result` 两格 ⇒ run8 相 2 的 D-2「可读面没有 usage」与 D-3
#: 「`sources` 0/20」两枚是**无从判定**，不是判了红（`docs/testing/run8-phase2-readout-2026-09-25.md`）。
#: 这一族函数把读数折进取回账（由 `transport` 塞进帧账 `queue` 那一格），三条诚实口径一条不省：
#:   ① 键根本不在位（本单之前发布的旧行 / 服务端没交这批键）⇒ 槽位读 None，读作「这一行
#:      说不出」，不拿 0 或空表冒充「查过，是零」；
#:   ② 载荷在位而解不开（`unreadable_terminal`）⇒ 另记一枚形状，与 legacy 分开；
#:   ③ `usage.authoritative` 为 false ⇒ 标志原样进账（那本账只有一台机器看得见），它交回的
#:      null 照 null 记，一枚都不折算成零。
#: 🔴 这一段一次表都不许多读：钟的纪律见文件抬头 R223 那一族（假钟每多读一格，105 题重放的
#: 时间轴整条被推走 ⇒ PRE_R181_ANSWERS_SHA 当场红）。

#: 取回账 ``terminal`` 那一格的五种形状，逐枚不同名、互不冒充。
TERMINAL_SHAPE_STRUCTURED = "structured"          # 终态载荷在位且读得出（queue-terminal-v1）
TERMINAL_SHAPE_LEGACY = "legacy"                  # 本单之前发布的行：它说不出自己有没有出处
TERMINAL_SHAPE_UNREADABLE = "unreadable"          # 键在位而载荷解不开：损坏，不是兼容
TERMINAL_SHAPE_NO_KEYS = "no_keys"                # 服务端在这一枚状态下压根没交这批键
TERMINAL_SHAPE_NOT_TERMINAL = "not_terminal"      # 停表时一次终态载荷都没读到
#: 出处三枚（``sources_present`` / ``len(sources)`` / ``sources_error``）只在**载荷真说了话**的
#: 形状下才算读数：契约 §Compatibility note 2026-09-25 明写旧行交回的是占位空表 ``sources: []``，
#: 照抄 len() 就把「这一行说不出」洗成「查过了，零枚」—— R254 刚治过的那枚谎换个格子复发。
SOURCES_READABLE_SHAPES = (TERMINAL_SHAPE_STRUCTURED,)
#: 进账的读数槽，名字与契约同源（一处解析两通道）。缺证词一律 None，不是 0、不是空串。
TERMINAL_SLOTS = ("schema", "state", "answer_present", "answer_is_park_notice",
                  "worker_status", "sources_present", "sources_n", "sources_error",
                  "scope_reason_code", "usage", "approval_steps", "approval_ledger_status",
                  "approval_notice_chars", "terminal_note")
#: ``usage`` 里必须点名的六枚槽（判据②）：四枚数 + 那本账的名分 + 权威不权威。
USAGE_SLOTS = ("prompt_tokens", "completion_tokens", "total_tokens", "model_calls",
               "authoritative", "ledger")


def _text_slot(source, key):
    """只认真读到的字符串；键不在位或不是字符串 ⇒ None（说不出 ≠ 查过是空串）。"""
    value = source.get(key)
    return value if isinstance(value, str) else None


def _flag_slot(source, key):
    """布尔槽位同上。🔴 None 与 False 是两枚不同的读数：前者是这一行说不出。"""
    value = source.get(key)
    return value if isinstance(value, bool) else None


def _terminal_shape(body):
    """这一行属于哪一枚形状（三条诚实口径全靠这一格分家）。"""
    schema = _text_slot(body, "terminal_schema") or ""
    state = _text_slot(body, "terminal_state") or ""
    if schema == "legacy" or state == "legacy_row":
        return TERMINAL_SHAPE_LEGACY
    if schema == "unreadable" or state == "unreadable_terminal":
        return TERMINAL_SHAPE_UNREADABLE
    if not schema and not state:
        return TERMINAL_SHAPE_NO_KEYS
    return TERMINAL_SHAPE_STRUCTURED


def _sources_are_reportable(shape):
    """出处那一族在这一枚形状下到底说没说句话（判据② 第一条口径的开关）。"""
    return shape in SOURCES_READABLE_SHAPES


def _blank_terminal_readout(shape):
    """一枚说不出话的终态格：形状有名，读数槽全 None（不是 0，不是空表，不是空串）。"""
    readout = {"shape": shape, "usage_present": False, "approval_present": False}
    readout.update({slot: None for slot in TERMINAL_SLOTS})
    return readout


def _terminal_readout(body):
    """把一枚 `/queue/status` 载荷折成取回账的 ``terminal`` 那一格（判据②③）。

    非 dict（停在 ``queued_stalled`` / ``queued_deadline`` / ``queued_no_status`` 上：一次终态
    载荷都没读到过）⇒ 形状 ``not_terminal``，其余全 None。``answer_present`` 与
    ``answer_is_park_notice`` 两枚在 legacy / unreadable 形状下仍是**真读数**（路由从 ``result``
    现算，契约兼容节明写），照收不误。
    """
    if not isinstance(body, dict):
        return _blank_terminal_readout(TERMINAL_SHAPE_NOT_TERMINAL)
    shape = _terminal_shape(body)
    readout = _blank_terminal_readout(shape)
    readout["schema"] = _text_slot(body, "terminal_schema")
    readout["state"] = _text_slot(body, "terminal_state")
    readout["answer_present"] = _flag_slot(body, "answer_present")
    readout["answer_is_park_notice"] = _flag_slot(body, "answer_is_park_notice")
    readout["worker_status"] = _text_slot(body, "worker_status")
    readout["scope_reason_code"] = _text_slot(body, "scope_reason_code")
    readout["terminal_note"] = _text_slot(body, "terminal_note")
    if _sources_are_reportable(shape):
        sources = body.get("sources")
        readout["sources_present"] = _flag_slot(body, "sources_present")
        readout["sources_n"] = len(sources) if isinstance(sources, list) else None
        readout["sources_error"] = _text_slot(body, "sources_error")
    usage = body.get("usage")
    if isinstance(usage, dict):
        # 逐键照抄 + 六枚具名槽补位：authoritative 一枚不许洗掉（口径③），null 照 null 记。
        readout["usage"] = {str(key): value for key, value in usage.items()}
        for slot in USAGE_SLOTS:
            readout["usage"].setdefault(slot, None)
        readout["usage_present"] = True
    approval = body.get("approval")
    if isinstance(approval, dict):
        readout["approval_present"] = True
        steps = approval.get("pending_steps")
        readout["approval_steps"] = ([str(step) for step in steps]
                                     if isinstance(steps, list) else None)
        readout["approval_ledger_status"] = _text_slot(approval, "ledger_status")
        notice = _text_slot(approval, "notice")
        readout["approval_notice_chars"] = len(notice) if notice is not None else None
    return readout


# ==================== R447：出处随答案交回（判据③） ====================

#: 取回账里**只给 transport 用**的那一格。出处行是要交给评分器的那一份正文，不抄进第二份
#: 证据件：帧账的口径一直是「计数与指纹进账、客户正文不进账」（``last_frame_sha`` 同办）。
#: 🔴 它不进 ``TERMINAL_SLOTS`` —— 那一格的键集是 R259 的形状账，一多一少都算改尺；它也不进
#: sidecar 那一行（``tests/test_r123_hitl_approval.py:243`` 把除九键之外的键集钉成甲案七键子集）。
TRANSPORT_ONLY_QUEUE_KEYS = ("sources_rows",)


def _reportable_source_rows(body):
    """把 ``/queue/status`` 载荷里那一身出处行搬出来（判据③ 的搬运，不裁决、不补零）。

    只在**载荷真说了话**的形状下取（``SOURCES_READABLE_SHAPES``）：legacy / no_keys /
    unreadable / not_terminal 四枚形状说不出自己有没有出处 ⇒ 回空表说的是「这一行没交行」，
    它与「查过了，零枚」在 ``terminal.sources_n`` 那一格上仍然是两件事（口径① 一字不省）。
    行本身在服务端已过一遍 ``isinstance(row, dict)``（``chat.py::queue_terminal_readout``），
    所以 ``len(rows)`` 与 ``sources_n`` 逐枚相等 —— 这枚相等由 ``tests/test_r447_*`` 钉住。
    """
    if not _sources_are_reportable(_terminal_shape(body)):
        return []
    rows = body.get("sources")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _queue_evidence(book, stream_evidence=()):
    """出处随答案交回：可读面真交了行就用它那一身行，说不出就退回流内那一份。

    🔴 不拿空表冒充「查过了，零枚」，也绝不从正文反推出处。队列道后台那一轮没有前台
    ``sources`` 事件（run9c 实测「流内 sources 事件 0/20」），所以 ``stream_evidence`` 在那一路
    上恒为空 —— 那正是从前 20 枚 ``answers.evidence`` 全空的来路。
    """
    cell = (book or {}).get("terminal") or {}
    if _sources_are_reportable(cell.get("shape")):
        return list((book or {}).get("sources_rows") or [])
    return list(stream_evidence or [])


def _bytes_are_the_park_notice(book):
    """取回的那一份字**逐字就是**那句挂起文案吗（判据① 后半段那把闸）。

    认的是服务端现算的真读数 ``answer_is_park_notice``（``is_hitl_park_notice`` 按
    ``hitl_park_text`` 现构造再逐字比），不是量具自己猜文案；``None`` 说的是这一行说不出 ⇒
    不算命中。run8 相 2 那 11 枚 legacy 行就是这个形状：``result`` 位置上是那句 37 字文案。
    """
    return bool(((book or {}).get("terminal") or {}).get("answer_is_park_notice"))


def _ledger_queue_cell(book):
    """落帧账的那一份取回账：摘掉只给 transport 用的那一格（帧账键集一字不许多）。"""
    cell = dict(book or {})
    for key in TRANSPORT_ONLY_QUEUE_KEYS:
        cell.pop(key, None)
    return cell


#: R222 判据①：五枚终态各一枚 kind，外加三枚「没读到终局」各一枚。全部与 ``ok`` 不同名，
#: 全部可以在 sidecar / 帧账的 ``kind`` 那一列上直接统计（那一列的名字与顺序未动）。
#: 🔴 ``done`` 沿用 ``queued_polled`` 这个名字：``tests/test_r181_text_frame_ruler.py:322``
#: 钉着它，而它也是「相 2 第一枚真取回正文」那一格的历史对接口，换名就是抹账。
#: ``queued_cancelled`` / ``queued_dead`` 是这一单的病：从前它们不落任何名字，一路轮到
#: deadline，最后和「一帧都没到的空答题」共用同一枚 ``blank`` —— 既看不出白烧，也看不出
#: 后端其实已经明说过这一轮不会再有正文。
#: R259 在这一族之上再多一枚：``awaiting_approval``（挂起在等人批准）→
#: ``queued_awaiting_approval``，正文空串。它从前落在「未识别状态」里 ⇒ 一路白烧到
#: ``QUEUE_STALL_SECONDS``（09-25 那窗 11/20 题，约 55 min）。判据⑤：五枚既有终态一字未改。
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

    R259 起这一族再多一枚终态：``awaiting_approval``（挂起在等人批准的那一轮）读到就停，
    kind = ``queued_awaiting_approval``，正文空串 —— 它与 ``queued_polled``（取回了一份字）、
    ``queued_done_no_bytes``（跑完了没正文）三枚互不冒充。上面五枚终态的 kind 与语义一个字
    没动（判据⑤）：新加一枚不等于可以重排旧的。
    🔴 R447：这一层说的仍然只是**停表读数**（「一步没走」），它不再是这一题的结局 ——
    ``transport`` 读到这一枚就读 ``queue.terminal.approval`` 那枚把手，把批准轮走到终答，
    批到落 ``queued_approved``、批不到落 ``approval_failed``。停表词表与读表次数一字未动。

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
        book.setdefault("terminal", _terminal_readout(None))  # R259：每枚停表都说得出终态格那一格
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
            book["terminal"] = _terminal_readout(body)  # R259 判据②：终态读数进账
            # R447 判据③：出处那一身行只给 transport（落帧账前由 _ledger_queue_cell 摘掉）。
            book["sources_rows"] = _reportable_source_rows(body)
            result = body.get("result")
            if isinstance(result, str) and result.strip():
                return _stop("queued_polled", result, "done", now)
            # done 但 result 不是正文（None / 非 str / 全空白）：取回了个空，另立一枚 kind，
            # 不许与「取回了一份字」共用 queued_polled，也不许冒充 ok。
            return _stop("queued_done_no_bytes", "", "done_no_bytes", now)
        if status == "awaiting_approval":
            # R259 判据①：挂起在等人批准的那一轮**一步没走**，读到就停表。从前这一枚字落在
            # 「未识别状态」那一族里，一路轮到 QUEUE_STALL_SECONDS（09-25 那窗 20 题里 11 题挂
            # HITL ⇒ 每题白烧 300 s、约 55 min，且 D-1/D-2/D-3 三格读数全被污染）。
            # 🔴 三枚 kind 互不冒充：``queued_polled`` =「取回了一份字」，``queued_done_no_bytes``
            # =「跑完了但没正文」，本枚 =「一步没走、在等人批准」——不许并进前两枚的任何一枚。
            # 🔴 正文交空串：契约里这一枚的 ``result`` 恒为 null，那句 37 字挂起文案只从
            # ``queue.terminal.approval_*`` 读数里露脸，一个字都不许当正文交回评分器（R254 判据①）。
            # 批准轮在这一枚停表**之后**由 transport 走（R447 判据①），这一层一枚都不许多打。
            book["terminal"] = _terminal_readout(body)
            return _stop("queued_awaiting_approval", "", "awaiting_approval", now)
        if status in ("cancelled", "dead", "expired", "failed"):
            # 后端自己宣布这一轮不会再有正文：读到就停（从前这两枚要烧到 deadline）。
            book["terminal"] = _terminal_readout(body)  # 这几枚状态下契约不交读数键 ⇒ 形状 no_keys
            return _stop("queued_" + status, "", status, now)
        # queued / processing / cancel_requested / 任何不认得的字面 ⇒ 都不是终态，接着轮
        time.sleep(QUEUE_POLL_INTERVAL)
    # 外圈到点：一次状态都没读到过 = 这一题根本没读通（另立 kind，不并进 stalled）
    return _stop("queued_no_status" if not book["polls"] else "queued_deadline",
                 "", "no_status" if not book["polls"] else "deadline", now)


# ==================== R642 D-3：批准之后必须再读一次终态载荷 ====================
#
# 病根（跟进单 §167 二／§172 二；本席 10-04 在 run21b 那 12 行上现取）：``_poll_queue`` 读到
# ``awaiting_approval`` 就停表，``queue.terminal`` 从此定格在**挂起那一刻**的快照上，而 transport
# 随后把批准轮走到终答（R447 判据①）却一次都没回头再读那枚载荷 ⇒ 那 8 枚 ``queued_approved``
# 的 ``terminal.state`` 全是 ``awaiting_approval``、``sources_present`` 全是 false、
# ``sources_n`` 全是 0。这枚 0 说的是「挂起的时候当然还没有出处」，不是「批准后出处为零」
# —— D-3 只能判「未量到」：拿它判红是假红，拿它判绿是假绿。
# 今天补的是**那一次读**，不是那格结论：批准后多打一发 GET，读回的东西另存一格，
# 快照那一格一个字不改（两次读数都在账上）。拿不到证词就记 None 并点名原因，🔴 不折 0、
# 不拿快照冒充、不改一字节产品码。真机读数由总控在 run22／D 相 2 的窗里取。

#: 批准后终态那一格长在取回账的哪一处：``queue.post_approval``。
#: 🔴 它长在 ``queue`` 那一格**里面**：帧账一行的键集是四枚「对判，不是子集」的在册钉
#: （``tests/test_r181_text_frame_ruler.py``／``test_r223_frame_arrival_clock.py``／
#: ``test_r259_awaiting_approval_stops_the_watch.py``／``tests/_r259_queue_ruler.py``），
#: 顶层一列都不许多 —— 与 R259 那条「读数只许长在 queue 那一格里」同一族纪律。
POST_APPROVAL_CELL_KEY = "post_approval"
#: 这一格该有几枚读数（本单的自证钉：缺一枚就是量具没交回它承诺的东西）。
POST_APPROVAL_CELL_KEYS = ("read", "outcome", "terminal")


def _read_queue_terminal(request_id):
    """批准之后**再读一次** ``/queue/status/{request_id}``，把那一枚读回折成一格账。

    只一发 GET：不循环、不睡表、一枚 ``time.time()`` 都不多读（钟的纪律见抬头第 10 条那族），
    也不复用 ``_poll_queue`` 那把轮子 ⇒ 停表词表与读表次数一字未动（判据⑤ 同族口径）。
    三条诚实口径照抄 ``_terminal_readout`` 那一族，一枚不省：
      ① 打不通 / 载荷解不成对象 ⇒ ``read`` 假、``terminal`` 那一身槽位全 ``None``
        （形状 ``not_terminal``）：这一格今天**没量到**，🔴 不折成 0、不拿挂起快照顶替；
      ② 读到了而服务端在这枚状态下没交读数键 ⇒ 形状 ``no_keys``／``legacy``，照样说不出；
      ③ 读到真终态 ⇒ 槽位逐枚照收，含 ``sources_error`` 那一枚「出处压根没算成」。
    """
    cell = {"read": False, "outcome": "", "terminal": _terminal_readout(None)}
    try:
        with _open("/api/v1/queue/status/" + str(request_id), None, "GET") as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        if not isinstance(body, dict):
            cell["outcome"] = "not_object"
            return cell
        cell["read"] = True
        cell["outcome"] = "read"
        cell["terminal"] = _terminal_readout(body)
    except urllib.error.HTTPError as exc:
        cell["outcome"] = "http_" + str(exc.code)
    except (urllib.error.URLError, OSError, UnicodeDecodeError,
            json.JSONDecodeError, ValueError) as exc:
        cell["outcome"] = type(exc).__name__
    return cell


#: D-3「批准之后出处随没随答案」的八枚可判读数，逐枚不同名、互不冒充。
#: 🔴 这一族治的就是那枚假零：从前账上只有挂起快照可算，``sources_n`` 读出来是 0，
#: 于是「批准之后没重读」被折成「批准后出处为零」—— 与 ``tests/_r259_queue_ruler.py``
#: 那枚 ``sources_cell`` 把 ``row_cannot_say`` 与 ``read_zero`` 分家同一件事，同一方向。
D3_READ_SOME = "read_some"
D3_READ_ZERO = "read_zero"
D3_NOT_COMPUTABLE = "not_computable"
D3_ROW_CANNOT_SAY = "row_cannot_say"
#: 批准后那一发读回的还是挂起态：批准没有落到这一行的终态上 ⇒ 那一枚载荷说的仍然是
#: 「挂起的时候还没有出处」。🔴 这一枚 guard 治的就是 D-3 的病根本身 —— 不拦它，
#: 「批准后仍挂起」会被折成 ``read_zero``，与拿挂起快照冒充是同一枚假零。状态词与
#: ``_poll_queue`` 停表那一条同源（``awaiting_approval``），本单不另起第二把尺。
D3_STILL_PARKED = "still_parked"
PARKED_TERMINAL_STATE = "awaiting_approval"
D3_READBACK_UNREADABLE = "readback_unreadable"
D3_NO_READBACK = "no_readback"
D3_NOT_APPLICABLE = "not_applicable"
#: 欠「批准后重读」这一格的 kind 两枚：批到终答与批不到 —— 两条都真打了批准轮。
#: 🔴 同步道那一族（``approved_ok``）不在名单里：它没有队列终态载荷可重读，``queue`` 那一格
#: 本来就是个空字典，D-3 在它身上读的是流内 ``sources`` 事件，另一条腿，不许互抄。
APPROVAL_ROUND_KINDS = (QUEUED_APPROVED_KIND, "approval_failed")


def _readback_cell(name, sources_n, note):
    """D-3 那一格的返回形状：读数有名、枚数可 None、原因随行交回（禁止只印一格）。"""
    return {"cell": name, "sources_n": sources_n, "note": note}


def post_approval_sources_readback(row):
    """把一题的帧账行折成 D-3「批准后终态」那一格的诚实读数（只读，一枚都不现编）。

    ``sources_n`` 只在 ``read_some``／``read_zero``／``not_computable`` 三枚读数下才是**真读数**，
    其余五枚一律 ``None`` ——「那一行说不出」与「查过了，零枚」是两件事（口径① 的延续）。
    🔴 批准后那一发若仍送回挂起态，读数是 ``still_parked`` 而不是 ``read_zero``：这一格
    拦的就是本单要治的那枚假零，方向只会变严，不会多豁免。
    题号与逐枚点名由调用方拿着：读数件与本单的离线对照表都按这一枚函数走，不另起第二把尺。
    """
    record = row or {}
    book = record.get("queue") or {}
    kind = str(record.get("kind") or "")
    if not book or kind not in APPROVAL_ROUND_KINDS:
        return _readback_cell(D3_NOT_APPLICABLE, None,
                              "这一题没走队列道或没打批准轮 ⇒ D-3 不欠批准后重读")
    cell = book.get(POST_APPROVAL_CELL_KEY)
    if not isinstance(cell, dict):
        return _readback_cell(D3_NO_READBACK, None,
                              "打了批准轮而账上没有批准后终态 ⇒ 未量到，不许读成零枚出处")
    if not cell.get("read"):
        return _readback_cell(D3_READBACK_UNREADABLE, None,
                              "批准后那一发重读没读到载荷：" + str(cell.get("outcome") or "未说明"))
    terminal = cell.get("terminal") or {}
    shape = terminal.get("shape")
    if shape == TERMINAL_SHAPE_NOT_TERMINAL:
        return _readback_cell(D3_READBACK_UNREADABLE, None,
                              "重读那一发送回的不是终态载荷（形状 not_terminal）")
    if terminal.get("state") == PARKED_TERMINAL_STATE:
        return _readback_cell(D3_STILL_PARKED, None,
                              "批准后那一发读回的还是挂起态 ⇒ 批准没落到终态，不许读成零枚出处")
    count = terminal.get("sources_n")
    if not _sources_are_reportable(shape) or count is None:
        return _readback_cell(D3_ROW_CANNOT_SAY, None,
                              "那一行说不出自己有没有出处（形状 " + str(shape) + "）")
    if terminal.get("sources_error"):
        return _readback_cell(D3_NOT_COMPUTABLE, count,
                              "服务端明说出处没算成：" + str(terminal.get("sources_error")))
    return _readback_cell(D3_READ_ZERO if count == 0 else D3_READ_SOME, count,
                          "批准后终态真交回 " + str(count) + " 枚出处")


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
    global _TOKEN, _BLANKS, _APPROVAL_FAILURES, _PARKED, _QUEUED_APPROVED
    row_id = str(row.get("id", ""))
    last_error = None
    for attempt in range(1, ATTEMPTS + 1):
        started = time.time()
        login()
        pacing = _pace()  # R223：这一枚就是「发出 POST 的一刻」（不另读表）
        try:
            tier = str(row.get("tier", "")).strip()
            lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier == DECLARE_LANE_TIER else ""
            # R632 第一腿：按**每一行自己的档位**补 lane。默认关 ⇒ 上面那一句就是全部口径；
            # 只在旧那一枚没补出任何东西时才补，两枚同设时旧口径优先，旧读数一字节不改。
            # 真机后果（开窗人必须先读这一句）：报告档 20 题从此带 lane=report，容器侧
            # REPORT_LANE_VIA_QUEUE 开着时它们走队列道 ⇒ 这一窗的时延与 run18 / run20k 不同代。
            if DECLARE_LANE_PER_TIER and not lane:
                lane = LANE_BY_TIER.get(tier, "")
            out = _stream_once(str(row["question"]), uuid.uuid4().hex, uuid.uuid4().hex,
                               lane, request_sent_at=pacing, row_id=row_id)
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
            if kind == "queued_polled":
                # R447 判据③：出处随答案交回。后台那一轮的 sources 只活在 `/queue/status` 的
                # 终态载荷里（前台回执流一帧 sources 都没有），从前没人把它搬到交回评分器的
                # 那一份 evidence 上 ⇒ run9c 实测 7 枚可读面 sources_n>0 的题 evidence 全空。
                evidence = _queue_evidence(frames["queue"], out["evidence"])
        # 🔴 走过队列道就不许再被前台那枚 error 帧或那枚 cancelled 帧换掉 kind：后端已经
        # 明说过这一轮的结局，拿一条没送达的旁证去改写它，量的就不是同一件事了。
        if not answer.strip() and out["error_text"].strip() and not from_queue:
            answer, kind, evidence = out["error_text"], "error_event", []
        # ===== R447 判据①：队列道读到 awaiting_approval ⇒ 批准轮必须走 =====
        # 停表那一层说的还是真话（``queued_awaiting_approval`` 与它的十枚同族一字不改，见
        # ``_poll_queue``），但「一步没走」从今天起不等于结局：契约把那一轮的批准把手交在
        # ``queue.terminal.approval`` 里，而 POST /api/v1/approve 要的 session_id 就是本题 /ask
        # 用的那一枚（归属谓词与同步道同一枚），走法复用 ``_resolve_hitl``，不新造第二套。
        # 第二枚要进批准轮的是 legacy 那一路：旧行的 ``result`` 逐字就是那句 37 字挂起文案，
        # 而可读面的 ``answer_is_park_notice`` 是服务端现算的真读数（R254 兼容节）⇒
        # 「取回了一份字」不等于「取回了一份终答」。🔴 那句文案一个字都不许进评分器。
        pending_approval = kind == "queued_awaiting_approval" or (
            kind == "queued_polled" and _bytes_are_the_park_notice(frames["queue"]))
        if pending_approval:
            # R259 的白烧闸口径不动：挂起的一轮是**产品结局**，一枚都不喂 ``_BLANKS``
            # （算进去的后果是 09-25 那窗 11/20 挂 HITL 在第 6 枚就停窗、整轮不出报告）。
            _PARKED += 1
        if not answer.strip() and not pending_approval:
            if not from_queue:
                kind = "cancelled" if out["cancelled"] else "blank"
            _BLANKS += 1
            if _BLANKS > MAX_BLANKS:
                raise RuntimeError(
                    row_id + ": 零字节题数已超 " + str(MAX_BLANKS) + " 题 ⇒ 系统性故障，停窗，"
                    "不出报告。差因看 sidecar 与 docker logs。")
            # 哨兵照旧：空正文 + 出处清空 + sentinel=true（这一轮真的一字节都没吐出来）。
            answer, evidence, sentinel = BLANK_SENTINEL, [], True
        elif out["hitl"]:
            kind = "hitl"
        # ===== R123 甲案：kind==hitl 就是「批准前停在闸上」，pre_* 键把旧形态留在侧车 =====
        extra = {"pre_kind": kind, "pre_answer_chars": len(str(answer)),
                 "pre_evidence_n": len(evidence), "approved": False, "approval_rounds": 0,
                 "approval_http_status": None, "approval_error": ""}
        steps = out["steps"]
        if kind == "hitl" or pending_approval:
            if kind == "hitl":
                extra["pre_answer"] = str(answer)  # 旧口径重算要的那一帧原文（判据 2）
            # 🔴 队列道一枚都不写 ``pre_answer``：挂起的那一轮交回的是零字节，legacy 那一路
            # 交回的是那句挂起文案 —— 两者都没有「批准前那一帧原文」要留，把文案抄进侧车就是
            # R254 刚拆掉的那枚谎换个格子复发。旧口径那一列在队列道上读 ``kind`` 与 ``pre_kind``。
            resolved = _resolve_hitl(row_id, out["session_id"], steps, frames,
                                     success_kind=(QUEUED_APPROVED_KIND if pending_approval
                                                   else "approved_ok"))
            answer = resolved["answer"]
            evidence = resolved["evidence"]
            steps = resolved["steps"]
            kind = resolved["kind"]
            sentinel = resolved["sentinel"]
            if not pending_approval:
                # 同步道：批准那条流的首字就是本题的首字。队列道那一格留 null —— 后台那一程的
                # 首字观测不到（本文件抬头第 3 条），批准腿的到达时刻只进帧账的 ``events`` /
                # ``stream_clock``，不冒充 ``first_token_at``（那会把两种零点混进同一列）。
                first_token_at = resolved["first_token_at"]
            extra.update({"approved": resolved["approved"],
                          "approval_rounds": resolved["rounds"],
                          "approval_http_status": resolved["http_status"],
                          "approval_error": resolved["error"]})
            if kind == "approval_failed":
                _APPROVAL_FAILURES += 1  # 不进 _BLANKS：批准失败是产品结局，不是零字节系统性故障
            elif kind == QUEUED_APPROVED_KIND:
                _QUEUED_APPROVED += 1  # R447：队列道批到终答的题数（收窗自查那一格）
            # ===== R642 D-3：批准之后必须再读一次终态载荷（抬头第 14 条）=====
            # 快照那一格（``queue.terminal``）说的还是「挂起那一刻」那句话，一个字不改；今天多存
            # 的是批准**之后**那一发读回的东西 —— 两次读数都留档，谁也不冒充谁。
            # 🔴 拿不到就记 None：不折 0、不拿快照顶替、不动产品码。开关关着时这一发压根不打，
            # 落盘字节逐字回到今天（假出口按发数说话，多打一发当场红）。
            if from_queue and RECORD_POST_APPROVAL_TERMINAL:
                queue_book = frames.get("queue")
                if isinstance(queue_book, dict):
                    queue_book[POST_APPROVAL_CELL_KEY] = _read_queue_terminal(
                        (out.get("queued") or {}).get("request_id"))
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
            "awaiting_approval_turns": _PARKED,  # R259：挂起题数（不喂白烧闸）
            "queued_approved_turns": _QUEUED_APPROVED,  # R447：其中批到终答的题数
            # R642：D-3 那半格的开关状态随自查交回 —— 关着就是这一格今天没量，写在盘面上。
            "post_approval_readback": ("on" if RECORD_POST_APPROVAL_TERMINAL else "off"),
            "frame_ledger": str(frame_ledger_path())}  # R181 判据② 的证据件落点（收窗自查用）
