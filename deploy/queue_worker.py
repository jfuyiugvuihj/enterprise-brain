"""
Layer 5 — 队列后台 Worker
启动后循环从 Redis 队列取请求，调用 Multi-Agent 处理，存储结果。

用法:
  python deploy/queue_worker.py

环境变量:
  REDIS_URL     — Redis 连接地址 (默认 localhost:6379)
  DATABASE_URL  — PostgreSQL 连接地址

R37：载荷自己声明了 report 档的那一轮走**能挂起**的图，跑完把结论补写回会话历史
（见 _process_report_lane_turn）；没声明档位的存量任务与本单之前逐字节相同。

R548：报告腿的逐字片段汇在 worker 进程里有了可注册点（见 ReportLanePieceLedger）。
R558 裁了投递面：账本每汇一批就往片段表推一发，既有轮询面在 processing 态读得到**递增**的
读数；终态那一格的形状与本单之前逐字节相同——片段一字节不进终态帧 / usage / sources /
审计行 / 错误码。
"""

import os
import sys
import time
import signal
from contextlib import nullcontext
from typing import get_args
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.common.reliable_queue import (
    PIECE_BATCH_LIMIT,
    PIECE_BATCH_SCHEMA,
    PIECE_FLUSH_PIECES,
    PIECE_FLUSH_SECONDS,
    LeaseHeartbeat,
    QueueConnectionError,
    QueueMessage,
    ReliableQueue,
    connect_reliable_queue,
)
from app.common.logger import logger, setup_logging
from app.trace.records import record_agent_result

#: R448 判据①②：认码的那一把尺与白名单的两枚锚全部从在册出处 import 进来，本文件
#: 一个面值都不抄、也不写第二把 `in` 匹配。三枚都是轻件（现测 import 共 <0.5 s，
#: 不落 torch 也不落 chromadb），所以不必照本文件对 `app.api.v1.chat` 那笔延后的理由
#: 延后——那一笔延后是因为 17 s 起子链外加一次向量库写，这里两样都没有。
from app.common.model_budget import context_error_code
from app.agents.contracts import CONTEXT_LIMIT_CODE, ErrorEnvelope
#: 反面清单在 evidence 里是私有名。本单只读引用它，因为它是唯一一份在册的"可重试"说法，
#: 而 contracts.py 对 CONTEXT_LIMIT_CODE 的那句注释正是拿它做对照的（不许改它）。
from app.agents.evidence import _RETRIABLE_CODES

setup_logging()

running = True
_queue: ReliableQueue | None = None


def _get_queue() -> ReliableQueue:
    global _queue
    if _queue is None:
        _queue = connect_reliable_queue()
    return _queue


def shutdown(signum, frame):
    global running
    logger.info(f"[QueueWorker] 收到信号 {signum}，正在退出...")
    running = False


def _lease_beat(queue: ReliableQueue, request_id: str):
    """向队列要一枚续租心跳，作用域由调用方用 `with` 划。

    这里的队列对象是鸭子类型的（用例里有只实现 reserve/complete 的替身），所以"这一版
    队列不支持续租"必须退化成"没有心跳"，而不是 AttributeError 把 worker 掀翻。
    """
    factory = getattr(queue, "lease_heartbeat", None)
    if factory is None:
        return nullcontext()
    return factory(request_id)


def _report_lease(heartbeat, request_id: str) -> None:
    """把续租心跳的读数落成日志：正常跑完一律安静，只有提前停表才说话。

    停表原因就是这一格的取证本身——09-25 那句"被取消或租约已丢失"要人拿两枚时间戳反推,
    今天它写在账上。
    """
    readings = getattr(heartbeat, "readings", None)
    if readings is None:
        return
    data = readings()
    if data["stopped_reason"] in (None, LeaseHeartbeat.STOP_MANUAL):
        return
    logger.warning(
        f"[QueueWorker] request_id={request_id} 租约心跳提前停表 "
        f"reason={data['stopped_reason']} renewals={data['renewals']} "
        f"refusals={data['refusals']}（租约就此过期，交给 requeue_expired 回收）"
    )


def _discard_reason(queue: ReliableQueue, request_id: str) -> str:
    """丢弃成因读自队列账本；读不动就明着报 unknown，不许留一枚空的。"""
    try:
        reason = queue.failure(request_id).get("last_error")
    except Exception as exc:
        logger.warning(f"[QueueWorker] request_id={request_id} 读不到丢弃成因: {exc}")
        return "unknown"
    return str(reason or "unknown")


def _log_discard_cause(queue: ReliableQueue, request_id: str) -> None:
    """把"到底是哪一支触发的"单独记一行。

    上面那行丢弃日志被 R81 钉成了逐字文案（`tests/test_r81_queue_terminal_retry.py:132`），
    本单不许放宽那条断言，所以成因另起一行，而不是往那句里塞字。
    """
    logger.info(
        f"[QueueWorker] request_id={request_id} 丢弃成因 "
        f"reason={_discard_reason(queue, request_id)}"
    )


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def _owner_from(payload: dict) -> str:
    principal = payload.get("principal") or {}
    if not isinstance(principal, dict):
        return ""
    return str(principal.get("user_id") or "").strip()

# ==================== R294：消费时刻现取身份（入队快照不是权威） ====================

#: 载荷里那一枚 `principal` 是**入队那一刻**冻下的身份快照：入队侧把整份
#: `Principal.model_dump(mode="json")` 写进队列，之后没有任何一格回来更新它。
#: R290 之后部门是会变的——员工在排队期间被挪了部门，快照里带的还是旧部门，拿它
#: 当身份跑完这一轮，就是“按旧作用域跑完再把结果记成新身份的成果”。本单唯一不许
#: 破的不变量写在这里：**消费时刻的作用域，必须与此刻重新发一个请求逐字相等。**
#: 所以下面把那份快照降级成两件事——定位用户库那一行的引用，以及与现取结果做漂移
#: 比对的证据。权威只有一处：消费时刻从用户库现取的那一份。方向只许收缩或判失效。

#: 队列账本与日志里的成因码。与 `NO_MODEL_CALL_READOUT` 同一档：只进 `last_error`
#: 与日志，不进用户正文（R16 同口径），也不进 `ErrorEnvelope.code` 那枚封闭枚举——
#: `tests/test_error_code_vocabulary.py` 与 `tests/test_r142_error_code_table_sync.py`
#: 的扫描面是 app/**，本文件不在其中，所以这里一枚契约码都不新造。
IDENTITY_SUBJECT_MISSING = "principal_subject_missing"
IDENTITY_SUBJECT_MISMATCH = "principal_subject_mismatch"
IDENTITY_STALE = "principal_stale"
IDENTITY_STORE_UNAVAILABLE = "identity_store_unavailable"
IDENTITY_STORE_NOT_SHARED = "identity_store_not_shared"
IDENTITY_ACCOUNT_INACTIVE = "principal_account_inactive"

#: 判失效不等于宣布终局：用户库连不上是故障，重投有可能救回来；授权判定不会。
#: 与 `is_non_retryable_error` 同一个理由——只有“重试也不会变”的那些才不占名额。
IDENTITY_RETRYABLE_CODES = frozenset({IDENTITY_STORE_UNAVAILABLE})

#: 随行签名。图内那一族身份还原（`app/agents/tools.py::_tool_principal`）从此只认
#: 由本文件在消费时刻交出的那一份 dict。它长在 configurable 上而不是 Principal 里：
#: 两条路径的 Principal 字段集必须逐字相等，把出处塞成字段，相等就没有了。
#: 取值必须与 app/agents/tools.py 的同名常量逐字相等，由用例钉（写法照 REPORT_LANE）。
PRINCIPAL_PROVENANCE_KEY = "principal_provenance"
CONSUMPTION_PRINCIPAL_PROVENANCE = "consumption-time"

#: 参与漂移比对的维度：每一维都能改变可见范围。`request_id` 与 `auth_source` 不参与
#: ——前者是本轮读数、后者是出处，两道路径上本来就该不同，比进去只会造出假失效。
PRINCIPAL_SCOPE_FIELDS = (
    "user_id",
    "roles",
    "permissions",
    "department",
    "department_ids",
    "clearance",
    "clearance_label",
    "status",
    "is_system",
)


def _principal_snapshot(payload) -> dict:
    """载荷里那份冻结的快照。只认 dict 形状，其余一律读成“没有快照”。"""
    snapshot = payload.get("principal") if isinstance(payload, dict) else None
    return snapshot if isinstance(snapshot, dict) else {}


def _identity_subject(payload) -> tuple[str, str]:
    """该向用户库问谁：载荷顶层的 username 与快照里的 username，两枚都在场就必须一致。

    不一致直接判失效——这一格说的是“这张单子是谁的”，队列没资格替它挑一个。
    """
    snapshot = _principal_snapshot(payload)
    claimed = str(snapshot.get("username") or "").strip()
    top = str(payload.get("username") or "").strip() if isinstance(payload, dict) else ""
    if claimed and top and claimed != top:
        return "", IDENTITY_SUBJECT_MISMATCH
    return claimed or top, ""


def _scope_shape(field: str, value):
    """把一维身份读成可比的规范形状。形状不对就是不可比，由漂移那一支判失效。"""
    if field in ("roles", "permissions", "department_ids"):
        if not isinstance(value, (list, tuple, set, frozenset)):
            return ("uncomparable", field, None)
        return ("list", None, sorted(str(item) for item in value))
    if field == "clearance":
        try:
            return ("int", None, int(value))
        except (TypeError, ValueError):
            return ("uncomparable", field, None)
    if field == "is_system":
        return ("bool", None, bool(value))
    return ("str", None, str(value or "").strip())


def _principal_drift(snapshot: dict, principal) -> tuple[str, ...]:
    """快照与现取结果逐维对照，只回漂移的**维度名**。

    实际值一个字都不进返回值：把别人的部门实值、密级实值写进日志，正是
    `app/rag/filters.py::_record_refusal` 明令不许落账的那一格。缺键同样算漂移——
    拿默认值替载荷补一格再去比，等于替一份旧快照猜一次身份（“没有新字段的旧载荷”
    恰是这种形状，判据④要的就是它被判失效而不是被猜出来）。
    """
    live = principal.model_dump(mode="json")
    drifted = []
    for field in PRINCIPAL_SCOPE_FIELDS:
        if field not in snapshot:
            drifted.append(field)
            continue
        if _scope_shape(field, snapshot[field]) != _scope_shape(field, live[field]):
            drifted.append(field)
    return tuple(drifted)


def resolve_consumption_principal(payload: dict) -> tuple[dict, str, str]:
    """把一张队列载荷换成“消费时刻”的权威身份。

    回 ``(projection, provenance, refusal)``：``refusal`` 非空即判失效，调用方一个模型
    都不许打、一条结果都不许记；``refusal`` 为空时第一枚就是交给图与出处复核的那一份。

    三种用户库形状，逐字取自 `app.common.auth.user_storage_state()`，不自造第二套口径：

    * ``postgres`` —— 生产那一档，用户表跨进程共享。**现取现比**：取不到人、账号停用、
      任何一维漂移都判失效。跑起来的那一份是现取结果的投影，与“此刻新发一个请求”拿到
      的那一份同源同值——判据②的逐字相等就是这么来的，不是比了 department 一维就算。
    * ``unavailable`` —— 生产形态下 PG 不可达，R230 已经把它定成 default-deny。队列这一
      侧不放宽：判失效，但把它留给重试，绝不退回快照。
    * ``memory`` —— 用户表长在进程内，worker 这一程本来就无从现取（跨进程不同步就是
      这一档的定义，不是本单给它开的例外）。**回退口径**：按快照原样执行，并在日志里
      明写本轮身份未经现取校验；不补默认值、不放宽任何一道闸门——快照里没有部门时检索
      闸门照旧拒（`app/rag/filters.py:135-139`），“静默按无部门跑遍全库”在这条路上不是
      可达的形状。
    """
    # 延迟 import：本文件 0.5 秒起得来的性质不许被打破，理由与文件头不 import chat 同一条。
    from app.common import auth
    from app.agents.contracts import Principal

    subject, refusal = _identity_subject(payload)
    if refusal:
        return {}, "", refusal
    if not subject:
        return {}, "", IDENTITY_SUBJECT_MISSING

    # 先问人、再问库是什么档：`get_user` 在生产侧自带 R230 那枚限频重探，先问一次，
    # 下面读到的 storage_mode 才是重探之后的读数，而不是一小时前那次探针的余温。
    row = auth.get_user(subject)
    mode = str((auth.user_storage_state() or {}).get("storage_mode") or "").strip()
    snapshot = _principal_snapshot(payload)

    if mode == "memory":
        if not snapshot:
            return {}, "", IDENTITY_SUBJECT_MISSING
        logger.warning(
            f"[QueueWorker] 用户库是进程内表（storage_mode=memory），本轮身份无从现取、"
            f"未经现取校验，按载荷快照执行 subject={subject} reason={IDENTITY_STORE_NOT_SHARED}"
        )
        return snapshot, CONSUMPTION_PRINCIPAL_PROVENANCE, ""
    if mode != "postgres":
        logger.error(
            f"[QueueWorker] 用户库不可用（storage_mode={mode or '(读空)'}），本轮判失效不执行 "
            f"subject={subject} reason={IDENTITY_STORE_UNAVAILABLE}"
        )
        return {}, "", IDENTITY_STORE_UNAVAILABLE
    if not row:
        # 账号此刻已经不在这张表里（被删、被改名、从来就没有）。按快照跑完，就是把一份
        # 旧身份的结论记在一个此刻无权存在的人身上——判失效，不退回快照。
        logger.error(
            f"[QueueWorker] 用户库现取不到该主体，本轮判失效 subject={subject} "
            f"reason={IDENTITY_STALE}"
        )
        return {}, "", IDENTITY_STALE
    try:
        principal = Principal.from_user(row)
    except Exception as exc:  # noqa: BLE001 - 这一行读不成身份就是无从授权，不猜
        logger.error(
            f"[QueueWorker] 用户库这一行读不成身份，本轮判失效 subject={subject} "
            f"reason={IDENTITY_STALE}: {type(exc).__name__}: {exc}"
        )
        return {}, "", IDENTITY_STALE
    if principal.status != "active":
        logger.error(
            f"[QueueWorker] 主体在消费时刻已不是 active，本轮判失效 subject={subject} "
            f"reason={IDENTITY_ACCOUNT_INACTIVE}"
        )
        return {}, "", IDENTITY_ACCOUNT_INACTIVE
    drifted = _principal_drift(snapshot, principal)
    if drifted:
        # 这一支就是 R290 那枚成果今天丢掉的地方：入队之后人换了部门，载荷里还是旧部门。
        # 既不许按旧快照跑完，也不许悄悄换成新部门跑完再交差——换部门是一次新的授权
        # 决定，该由用户重发那一轮来做，所以判失效。
        logger.error(
            f"[QueueWorker] 入队快照与消费时刻的身份已漂移，本轮判失效 subject={subject} "
            f"fields={','.join(drifted)} reason={IDENTITY_STALE}"
        )
        return {}, "", IDENTITY_STALE
    return principal.model_dump(mode="json"), CONSUMPTION_PRINCIPAL_PROVENANCE, ""


def _refuse_identity(queue, request_id, code, *, session_id, write_back) -> bool:
    """判失效这一支：一个模型都不打、一条结果都不记，只留队列账与（承诺过的）会话交代。

    不重投那半与 R81 同一个理由：载荷里冻着的那一份不会自己变新，重试只会把同一枚
    授权判定再判一次，白烧名额。用户库不可达那一码是故障，不在不重投之列。
    """
    terminal_status = queue.fail_or_retry(
        request_id, code, retryable=code in IDENTITY_RETRYABLE_CODES
    )
    bookkeeping = queue.failure(request_id)
    logger.error(
        f"[QueueWorker] request_id={request_id} 身份判失效，本轮未执行 -> {terminal_status}: {code} "
        f"(attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})"
    )
    if terminal_status == "dead" and write_back:
        # 会话历史里不许留一句没人回答的问话（R37 判据③④那一条口径）。交回的是
        # “未产出结论”那一句，不是“按旧身份跑完了”那一句。
        _save_background_turn(session_id, REPORT_TURN_FAILURE_TEXT)
    return True


NON_RETRYABLE_DEAD_REASON = "non_retryable_terminal"
#: 判据④：真库 `model_calls` 里一枚调用都没有的这一轮，没有资格叫 done。这一枚说的是
#: 「交回了答案却没有任何一次模型调用」，与 `no_answer_produced`（连答案都没有）不是一格。
#: 只进队列账本（`failure()["last_error"]`）与日志，不进用户正文（R16 同口径）。
NO_MODEL_CALL_READOUT = "no_model_call_recorded"


def is_non_retryable_error(record: object) -> bool:
    """True 只在记录自己声明了"重试也不会变"的时候成立。

    判定收成一个不碰 Redis 的纯函数，是为了能被单独钉住（deploy/ 不在包里，
    本文件此前也不在任何用例覆盖内）。它刻意只认 error["retryable"] is False
    这一种形状：状态闸门不在这里，success/partial 由下面那条一字未改的判断挡住，
    所以"partial 带一枚不可重试错误"仍旧照常发布；error 不是 dict、缺 retryable
    字段、字段值不是 False（None/0/"False"/"false" 等异形）一律 False，
    调用方仍旧照改前的路走 fail_or_retry。

    字段缺失为什么默认重试：ErrorEnvelope.retryable 的出厂值是 False，而
    AgentResult.model_dump() 一定带这个字段，所以看不见它只可能是这条记录压根
    没走过契约。队列层没资格替契约宣布终局，更不能把一次形状异常升级成不重投的
    dead —— 那是把"还能救"变成"必然丢"，而盲重试的代价本来有 max_attempts 兜着。
    """
    if not isinstance(record, dict):
        return False
    error = record.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("retryable") is False


# ==================== R37：报告档在后台跑完这一轮 ====================

# 档位名在队列这一侧的声明。取值必须与 app/api/v1/chat.py 的 LANE_REPORT、
# app/agents/nodes.py 的 LANE_REPORT 同为同一个字符串，由
# tests/test_r37_report_lane_worker.py::test_the_lane_name_has_one_source_of_truth 钉住。
# 为什么不干脆 import chat：本文件现在 0.5 秒起得来，而 app.api.v1.chat 一被 import
# 就要把整条 API/RAG 链拉起来（本机实测 17 秒，并且会改写 chroma_db/chroma.sqlite3），
# 用例又在模块层 import 本文件——等于每次全量测试都付这笔钱并顺手写一次向量库。
# 挂起文案与会话回写仍旧用 chat 里那三个与同步路径同源的共用件，只是延后到真跑到
# 报告档时才 import，和下面 run_orchestrator_result 的按需 import 同一个理由。
REPORT_LANE = "report"

# 后台这一轮彻底失败时写给用户看的那一句，措辞与同步路径 app/api/v1/chat.py 里
# "本轮未产出任何结论" 同一句。稳定码只进队列的 last_error 与日志，不进正文（R16）。
REPORT_TURN_FAILURE_TEXT = "本轮未产出任何结论，请重试或补充数据范围。"


def _report_lane_requested(payload) -> bool:
    """判据②：worker 侧定档是载荷的纯读——不调模型、不读会话、不碰队列。

    只认载荷里显式写着的档位字符串，和 chat._queue_lane 同一套苛刻：REPORT 不是任何
    人声明过的档位，而队列这一侧压根没有第二次判别的机会，模糊匹配等于猜心思。
    """
    if not isinstance(payload, dict):
        return False
    lane = payload.get("lane")
    return isinstance(lane, str) and lane.strip() == REPORT_LANE


def _stream_snapshot(event):
    """把流里的一枚事件拆成顶层状态快照；不是快照就返回 None。

    能挂起的在场流产的是 (namespace, state) 元组，编排自己吐的失败事件是一枚裸 dict，
    两种形状都得认，否则一次失败会被读成空快照。子图快照里没有顶层结论，读它等于拿
    半成品冒充最终答案。
    """
    namespace = ()
    data = event
    if isinstance(event, tuple):
        namespace = event[0] if len(event) > 1 else ()
        data = event[1] if len(event) > 1 else event[0]
    if not isinstance(data, dict):
        return None
    if data.get("error") or (namespace and namespace != ("",)):
        return None
    return data


#: R548 判据①：队列道报告腿的逐字片段账本上限。投递面（轮询面增量、或新起一条 tail SSE）
#: 今天还没裁，所以账本只在**本轮**活着——攒够这么多片之后只计数、不再留片，免得一台长跑的
#: worker 被一桩超大报告撑住内存。它不是第二套发布面，也不跨轮积累。
QUEUE_PIECE_LEDGER_LIMIT = 512


class ReportLanePieceLedger:
    """``stream_piece_sink`` 落在队列道的收端：按到达顺序记账，一个字都不往外发。

    R31 的片段汇在两枚在场跑道（``chat._ask_stream``、``chat._approve_stream``）上各有一条
    活着的流收它；队列道两条都没有——入队那条 SSE 交完 ``queued`` 与 ``done`` 两枚帧就关，
    worker 进程里根本没有一条流可投。所以本类补的是**可注册点**那一半，投递面仍旧欠着
    （凭据与逐字对账：``docs/testing/r548-queue-lane-piece-sink-registration.md``）。

    收端对片本身一律原样存：不合并、不改字、不重排、不"攒齐了拼成一枚"。判据① 要的
    「与一次投喂一整篇可区分」，量的就是 ``pieces`` 的枚数与顺序——拼起来等值、分片数不等值。
    """

    def __init__(
        self,
        request_id: str = "",
        *,
        limit: int = QUEUE_PIECE_LEDGER_LIMIT,
        publisher=None,
        flush_pieces: int = PIECE_FLUSH_PIECES,
        flush_seconds: float = PIECE_FLUSH_SECONDS,
        batch_limit: int = PIECE_BATCH_LIMIT,
        clock=time.monotonic,
    ) -> None:
        self.request_id = request_id
        self.limit = max(1, int(limit))
        self.pieces: list = []
        self.chars = 0
        self.overflow = 0
        # R558 判据①：投递面。``publisher`` 收一批 dict、真把批推进表就交回真值。
        # 它是**可选**的：留 None 时本账本退回 R548 的形状（只记账、一个字都不往外发），
        # 所以在册那几枚「一字节不进终态帧」的钉没有被改口，改口的只有轮询面那一侧。
        self._publisher = publisher
        self._flush_pieces = max(1, int(flush_pieces))
        self._flush_seconds = max(0.0, float(flush_seconds))
        self._batch_limit = max(1, int(batch_limit))
        self._clock = clock
        self._pending: list = []
        self._pending_since = self._clock() if publisher is not None else 0.0
        #: 已经推进表的批数，也就是下一批的序号减一。
        self.batches = 0
        #: 真正落到表里的字数（不含没发出去的那一截），用来和 ``chars`` 对账。
        self.published_chars = 0
        #: 投递失败的批数。失败不静默：攒着的字留着按同一序号重试。
        self.publish_errors = 0
        #: 增量表写满之后停止存正文的批数（与 ``overflow`` 分得很清：后者是内存账本上限）。
        self.truncated = 0

    def __call__(self, piece) -> None:
        """收一片。它不许抛：``nodes.publish_stream_pieces`` 会把抛错记成警告并丢掉余下的片。"""
        text = getattr(piece, "text", "")
        if isinstance(text, str):
            self.chars += len(text)
        if len(self.pieces) < self.limit:
            self.pieces.append(piece)
        else:
            self.overflow += 1
        if self._publisher is None or not isinstance(text, str) or not text:
            return
        self._pending.append(text)
        # 两条阈值任一到就汇一发：枚数那条管「字少而片密」，秒数那条管「片少而字长」——
        # 客户端每 3 s 轮一次，所以任何一条都能在下一发轮询里看见新增的字。
        if len(self._pending) >= self._flush_pieces or (
            self._clock() - self._pending_since >= self._flush_seconds
        ):
            self.flush()

    def flush(self) -> bool:
        """把攒着的那一截字打成一批交出去；交回「这一发真推进表了没有」。

        三个不许：

        * **不许抛**——投递面坏了不能把整轮报告带崩，收端那一发同样不许抛（同一口径）；
        * **不许静默**——失败进 ``publish_errors``，字攒回去、序号不前进，下一发按同一序号
          重试；读数侧按序号去重，因此重试不会让客户端看见重复的字；
        * **不许把「表已经写满」读成「一个片段都没有」**——停止存正文后每发只让 ``truncated``
          加一，账面数（``pieces`` / ``chars`` / ``discarded``）照旧往前滚。
        """
        if self._publisher is None or not self._pending:
            return False
        if self.batches >= self._batch_limit:
            # 正文不再存（客户端到终态从 `result` 那一份拿全篇），但每一发的计数照滚。
            # 刻意不做成「报一次就闭嘴」：表里的数一旦冻在最后一批上，屏侧读到的就是
            # 「停在第 N 批」的旧账面——那跟静默丢字只差一个数字，差就差在没人说得出来。
            # 代价是有界的一行 JSON，换来的是「上限到了」这件事随时看得见。
            self.truncated += 1
            self._pending = []
            self._pending_since = self._clock()
            return self._publish("")
        text = "".join(self._pending)
        published = self._publish(text)
        if published:
            # 🔴 交出去就必须把攒着的一截字清掉：不清就是每一发都从头把已交过的字再交一遍，
            # 客户端按游标拼出来的正文会长成「同一段话重复 N 遍」——那是判据③ 禁止的第二条流，
            # 只是它藏在投递面里。（09-30 现场：本仓第一版就栽在这格，靠 r548 的日志面钉抓出。）
            self._pending = []
            self._pending_since = self._clock()
        return published

    def _publish(self, text: str) -> bool:
        """把 ``text`` 打成一批交给投递面，成功才推进序号。

        失败的那一批**原样留着**（序号不动），下一发带同一序号重试；读数侧按序号去重，
        所以连接抖动不会让客户端看见重复的字。
        """
        batch = {
            "schema": PIECE_BATCH_SCHEMA,
            "seq": self.batches + 1,
            "text": text,
            "pieces": self.count,
            "chars": self.chars,
            "discarded": self.overflow,
            "legs": list(self.legs),
            "truncated": self.truncated,
        }
        try:
            ok = bool(self._publisher(batch))
        except Exception as exc:
            ok = False
            logger.warning(
                f"[QueueWorker][R558] request_id={self.request_id} 片段汇流失败，留着重试: {exc}"
            )
        if ok:
            self.batches += 1
            self.published_chars += len(text)
        else:
            # 失败只记账，不回填：`_pending` 里那几片原样留着，下一发带**同一序号**重交，
            # 读数侧按序号去重，客户端因此既不少字也不重复拿字。
            self.publish_errors += 1
        return ok

    @property
    def count(self) -> int:
        """交回过的片数，含被上限截掉的那几枚：截断也如实计数，不许静默少报。"""
        return len(self.pieces) + self.overflow

    @property
    def legs(self) -> tuple:
        """这些片各自盖在哪条腿上（``StreamPiece.worker``）；没标注的归进空串那一格。"""
        return tuple(sorted({str(getattr(piece, "worker", "") or "") for piece in self.pieces}))

    def joined_text(self) -> str:
        """逐字拼回：判据① 的「拼起来等值」读这里，不读任何一份副本。"""
        parts = []
        for piece in self.pieces:
            text = getattr(piece, "text", "")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)


def _log_report_lane_pieces(request_id: str, ledger) -> None:
    """队列道逐片汇的唯一外部读数：一枚片都没收到就**一行都不留**。

    这一行是 R548 留给真机窗的读点（本单不许跑端到端，见交工纸 §5）。既有日志面因此逐字
    不变——只有真流到字的轮次多这一行；终态帧、``usage``、``sources``、审计行与错误码一字节
    都不许多，那几样由本单的零外溢钉与 R37/R254/R514/R81/R448 的在册件共同守着。
    """
    if not ledger.count:
        return
    logger.info(
        "[QueueWorker][R548] request_id={rid} 报告档逐片汇 {pieces} 枚 / {chars} 字 / "
        "腿 {legs}{tail}".format(
            rid=request_id,
            pieces=ledger.count,
            chars=ledger.chars,
            legs="、".join(name or "未标注" for name in ledger.legs),
            tail=" / 超上限丢弃 %d 枚" % ledger.overflow if ledger.overflow else "",
        )
    )


def _drain_report_stream(
    user_message, *, thread_id, principal, provenance, request_id, trace_id, task_id,
    stream_piece_sink=None,
):
    """跑完这一轮，收回顶层结论、契约记录，以及编排自己报的那句错。

    读法与同步路径一致：只认顶层命名空间的快照，final_answer 取最后一次非空值。

    R548 只多交一枚**可注册点**：``stream_piece_sink`` 非 None 时把它交给编排入口的
    同名形参，由 ``run_with_stream`` 塞进 ``configurable``——这一交就是 R31 差格 b 缺的
    那半格（队列道今天有地方收片了）。传 None 时（全部既有直调）这一发的关键字与
    改前逐字相同，config 里连键都不多加。
    """
    from app.agents.orchestrator import run_with_stream

    final_answer = ""
    agent_results: dict = {}
    stream_error = ""
    for event in run_with_stream(
        user_message,
        thread_id=thread_id,
        user={"principal": principal, PRINCIPAL_PROVENANCE_KEY: provenance},
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        # R548：队列道唯一一枚片段汇注册点（交给编排入口；第二处一起就是第二套口径）。
        stream_piece_sink=stream_piece_sink,
    ):
        if isinstance(event, dict) and event.get("error"):
            # 编排把异常收成一枚 error 事件而不是抛出来：这一轮到此为止。
            stream_error = str(event["error"])
            continue
        state = _stream_snapshot(event)
        if state is None:
            continue
        if state.get("final_answer"):
            final_answer = str(state["final_answer"])
        if isinstance(state.get("agent_results"), dict):
            agent_results = dict(state["agent_results"])
    return final_answer, agent_results, stream_error


def _save_background_turn(session_id: str, content: str) -> None:
    """把后台这一轮补写进会话历史（判据⑤）。写不成就明着留话，不许假装写了。

    共用件返回 False 就是真没写成：纯内存会话的部署里，worker 往自己进程的内存补一行
    等于没写，用户在 API 进程的历史里一个字也看不见。
    """
    from app.api.v1 import chat

    if not session_id:
        logger.warning("[QueueWorker] 后台轮次缺少 session_id，历史回写跳过")
        return
    try:
        written = chat.save_session_turn(session_id, content)
    except Exception as exc:
        # 答案已经发布，回写失败绝不能把这一轮升级成"再跑一次"——那会变成两个答案。
        logger.error(f"[QueueWorker] 后台轮次写回会话历史失败 session={session_id}: {exc}")
        return
    if not written:
        logger.warning(
            f"[QueueWorker] 后台轮次没能写回会话历史 session={session_id}：会话库不可用"
        )


# ==================== R448：确定性拒绝不该重试三发 ====================


def _derive_deterministic_refusal_codes() -> frozenset[str]:
    """现读"再发一次也必然同因"的那一组码；锚读不通就报错停手，不静默退档。

    两枚锚的语义都在别人手里，本文件只是把它们对齐（判据②）：

      正面 —— ``app/agents/contracts.py:102`` 的 ``CONTEXT_LIMIT_CODE``，它的在册注释
      ``app/agents/contracts.py:247-250`` 明写「它不是可重试的错（同一个提示词永远装
      不下），所以不进 evidence._RETRIABLE_CODES」。这一族今天只此一枚，面值由常量带来。
      反面 —— ``app/agents/evidence.py:18`` 的 ``_RETRIABLE_CODES``，在册的"可重试"清单，
      这里用作否决：同一枚码同时出现在正反两处，就是锚漂了，队列没资格替契约挑一个。

    还有一条下限：锚必须在 ``ErrorEnvelope.code`` 那枚封闭词表里，否则它压根不是公开稳定码，
    拿它判终态等于往台账里写野词（枚面值在 ``app/agents/contracts.py:252`` 的封闭枚举里，
    返回它的那一句在 ``app/agents/contracts.py:204``）。

    三条里任何一条读不成都抛。退成"全部可重试"就是本单要治的那枚缺陷本身（run9c 实测
    同一枚拒绝连吃三发，373.7 s 里约 248 s 是纯白烧）；退成"全部不可重试"则把还能救的
    轮次必然判死。两样都不许发生，所以两样都不给路。
    """
    enum_codes = frozenset(get_args(ErrorEnvelope.model_fields["code"].annotation))
    retriable_codes = frozenset(_RETRIABLE_CODES)
    anchors = tuple(
        code.strip()
        for code in (CONTEXT_LIMIT_CODE,)
        if isinstance(code, str) and code.strip()
    )
    if not anchors:
        raise RuntimeError(
            "[R448] 确定性拒绝白名单的锚读不出来（CONTEXT_LIMIT_CODE 为空或非字符串），"
            "本 worker 拒绝启动：静默退成'全部可重试'或'全部不可重试'都是假话"
        )
    for code in anchors:
        if code not in enum_codes:
            raise RuntimeError(
                f"[R448] 锚 {code!r} 不在 ErrorEnvelope.code 的封闭词表里，"
                "它不是公开稳定码，无权拿它判终态"
            )
        if code in retriable_codes:
            raise RuntimeError(
                f"[R448] 锚 {code!r} 同时出现在 evidence._RETRIABLE_CODES 里，"
                "正面锚与反面清单已互相矛盾，本单无权替它们裁定"
            )
    return frozenset(anchors)


#: import 期就把账立住：锚漂了就是 worker 起不来，而不是跑到某一轮才悄悄少判一枚。
DETERMINISTIC_REFUSAL_CODES = _derive_deterministic_refusal_codes()


def report_failure_record(error: object) -> dict:
    """把报告档那一发失败拆成交回队列的记录：原码留着，确定性拒绝补一枚显式终局判定。

    改前这里有两枚缺陷，都在同一枚记录上（本文件改前 :527 与 :540 两处同形字面量）：

      ① 码无条件写成兜底值 —— 真机 run9c 的台账因此读成「未产生业务结论: internal_error」，
      而同一条 request_id 的 ``[ModelBudget]`` 那行明明说着 prompt_tokens=2695 装不进 4096；
      业主运维读到的是一枚兜底码，不是那三个数字。
      ② 缺 ``error["retryable"]`` —— 本文件的 ``is_non_retryable_error`` 只认末句那枚显式
      ``False``，缺这一键就是"还能救"，于是同一枚发请求前就干净拒绝的错被打了三发。

    认码只许用 ``app/common/model_budget.py:1021-1023`` 的 ``context_error_code`` 这一把尺
    （键于 :357-366 ``CONTEXT_ERROR_FRAGMENTS``），本文件不写第二把 ``in`` 匹配。尺认不出来
    就仍旧交回兜底值，且**不写** ``retryable`` 这一键 —— 其余一切码的重试次数、退避、终态与
    日志文案逐字节与改前相等（判据⑤ 的下半句）。
    """
    recognised = context_error_code(
        error if isinstance(error, BaseException) else Exception(str(error))
    )
    record = {
        "status": "failed",
        "error": {"code": recognised or "internal_error", "message": str(error)},
    }
    if recognised in DETERMINISTIC_REFUSAL_CODES:
        # 契约自己的语义就是"重试也不会变"，这里把它显式写出来交回 R81 那条闸门：
        # 首发落 dead，一个名额不占，原码留在台账与日志里。
        record["error"]["retryable"] = False
    return record


def _fail_report_turn(queue, request_id, record, *, session_id, write_back) -> bool:
    """这一轮没产出业务结论：终态与原因码仍旧走队列原有的那套，历史只在真终态补一行。"""
    code = str((record.get("error") or {}).get("code") or record.get("status") or "internal_error")
    if is_non_retryable_error(record):
        # 与 R81 同一条闸门：契约判定"重试也不会变"的直接落 dead，一个名额不占。
        terminal_status = queue.fail_or_retry(request_id, code, retryable=False)
        bookkeeping = queue.failure(request_id)
        logger.error(
            f"[QueueWorker] request_id={request_id} 报告档终态不可重试，不再重投 -> {terminal_status}: {code} "
            f"(reason={NON_RETRYABLE_DEAD_REASON} "
            f"attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})"
        )
    else:
        logger.error(f"[QueueWorker] request_id={request_id} 报告档未产生业务结论: {code}")
        terminal_status = queue.fail_or_retry(request_id, code)

    if terminal_status == "dead" and write_back:
        # 还要重试的这一轮不是终态，一个字都不许写；落到 dead 才补一句，否则会话里
        # 永远留着半句没人回答的问话（判据③加④）。
        _save_background_turn(session_id, REPORT_TURN_FAILURE_TEXT)
    return True


def _process_report_lane_turn(
    queue,
    request_id,
    payload,
    *,
    user_message,
    session_id,
    owner_id,
    thread_id,
    principal,
    principal_provenance,
) -> bool:
    """报告档的后台执行：结果查得回、挂起留待办、历史不留空洞。

    挂起文案、待办记账、会话回写三件都用 app/api/v1/chat.py 里与同步路径同源的那三个
    共用件，两条道说的是同一句话。判据⑧：本函数不带任何开关，也不默认开启任何路径——
    进不进来看的是载荷自己有没有声明档位，而那由入队侧的 REPORT_LANE_VIA_QUEUE 决定。
    """
    from app.agents.evidence import aggregate_agent_result
    from app.agents.orchestrator import check_interrupt
    from app.api.v1 import chat

    write_back = bool(payload.get("write_back_session"))
    trace_id = f"trace-{uuid4().hex}"
    task_id = f"task-{uuid4().hex}"
    started = time.monotonic()

    # R548：本轮的逐字片段账本，就是队列道那枚可注册点的收端。
    # R558 补的是投递面：账本每汇出一批就往片段表推一发，于是既有轮询面读得到**递增**的
    # 读数。🔴 片段只进这一张表，一字节不进终态帧 / usage / sources / 审计行 / 错误码——
    # R548 那条零外溢的钉在本单之后仍旧成立，改口的只有 processing 态那一格读数。
    piece_ledger = ReportLanePieceLedger(
        request_id,
        publisher=lambda batch: queue.append_piece_batch(request_id, batch),
    )
    try:
        final_answer, agent_results, stream_error = _drain_report_stream(
            user_message,
            thread_id=thread_id,
            # R294：这里交下去的是消费时刻现取的那一份，不是载荷里冻着的快照。
            principal=principal,
            provenance=principal_provenance,
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
            stream_piece_sink=piece_ledger,
        )
    except Exception as exc:
        logger.error(f"[QueueWorker] request_id={request_id} 报告档后台执行异常: {exc}")
        return _fail_report_turn(
            queue,
            request_id,
            # R448：这一支与下面 stream_error 那一支是同一枚洗码形状（兜底码写死在
            # 字面量里、同样不带 retryable、同一个消费者 _fail_report_turn），所以
            # 一并交回认码那一个处。
            report_failure_record(exc),
            session_id=session_id,
            write_back=write_back,
        )

    # R558 判据①：收窗之前把最后攒着的那一截字推出去。少了这一发，「最后不足 8 片」的那
    # 一截永远进不了表——递增会演变成「屏幕少了一尾」。
    piece_ledger.flush()

    _log_report_lane_pieces(request_id, piece_ledger)

    duration_ms = int((time.monotonic() - started) * 1000)
    if stream_error:
        # R448：编排那枚 error 事件只带句子不带码（app/agents/orchestrator.py:1464
        # yield {"error": str(e)}），改前这里因此无条件写兜底码且不写 retryable，于是
        # "发请求前就干净拒绝"的那一发被当成可重试打了三回。现在交回 report_failure_record：
        # 用在册那把尺认回原码，命中白名单的一族就按契约自己的语义补一枚显式 retryable=False，
        # 首发走 R81 那条闸门落 dead；其余码仍旧不带这个键，仍旧交回 fail_or_retry 按名额判，
        # 重试用完才 dead（与 R81 同一口径）——那一支的记录形状与本单改前逐字节相等。
        logger.error(f"[QueueWorker] request_id={request_id} 报告档后台报错: {stream_error}")
        return _fail_report_turn(
            queue,
            request_id,
            report_failure_record(stream_error),
            session_id=session_id,
            write_back=write_back,
        )

    # 先查挂起再判成败：图停在 interrupt_before 之前时这一轮既没有答案也不是失败，它是
    # 在等人。顺序反了就把"等你确认"记成队列失败，审批面板还少一条待办。
    try:
        parked = check_interrupt(thread_id)
    except Exception as exc:
        logger.warning(
            f"[QueueWorker] request_id={request_id} 挂起节点查不到，按未挂起处理: {exc}"
        )
        parked = None

    answer = chat.hitl_park_text(parked) if parked else final_answer
    record = aggregate_agent_result(
        agent_results,
        answer=answer,
        request_id=request_id,
        trace_id=trace_id,
        task_id=task_id,
        session_id=session_id,
        duration_ms=duration_ms,
    ).model_dump()
    record_agent_result(record, owner_id=owner_id, session_id=session_id, entry_point="queue")

    # R254 判据③：token 读数在这一轮交出去之前就取好，两条发布的腿共用同一份。读的是真库
    # `model_calls`（同源，不现编）。出处要到交正文那一支才取——挂起这一轮没有正文，取一遍
    # 出处只是白打一次索引台账，那一格交空清单并说清「这一轮没有正文可带出处」。
    usage = chat.read_model_call_usage(request_id)
    visible_sources: list = []
    scope_reason = ""
    sources_error = ""
    # R514：这一轮真算过哪份数据文件，与上面那枚 usage 同一格——在两腿分叉之前一次取好，
    # 挂起腿与正文腿共用同一份读数。取数只走 `chat` 在册的那一枚唯一收集器
    # `_collect_dataset_filenames`（R504 §9 判据①登记的改法：一处一线、不新增第二份收集器），
    # 读的是 `_drain_report_stream` 已经收回来的那只证据袋：纯内存搬运，一次索引台账都不打，
    # 所以它与上面那句「挂起这一轮不取出处」不冲突——那句话说的是 `queue_turn_sources` 要走
    # `_authorized_source_rows` 现取检索范围，不是这里。
    dataset_files: list[str] = []
    chat._collect_dataset_filenames(agent_results, dataset_files)

    if parked:
        # 挂起记三笔账：审批面板一行待办、队列一个**非 done** 终态、会话历史一句话，缺一笔
        # 用户就找不到这一轮。归属人只认载荷里解析出的 user_id——上面没有 owner 就已经拒
        # 执行，这里更不许退回共享身份。
        if not chat.record_hitl_awaiting(
            session_id or thread_id,
            owner_id,
            parked,
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
        ):
            logger.error(
                f"[QueueWorker] request_id={request_id} 待办没能开成 session={session_id}："
                "审批面板看不见这一轮后台挂起"
            )
        # 判据①：这一轮没有正文。从前它把那句 37 字挂起文案当 `result` 交回、状态还报
        # `done`，客户端读到的是「跑完了」——那既不是正文也不是答案，是谎报终态。今天答案键
        # 干脆不写（`result=None`），挂起文案只留在 `approval.notice` 那一格里，并随它交出
        # 一件可寻址的批准把手（客户端不必重发本轮）。会话历史那一笔照旧写这句（R37 判据③⑤）。
        terminal = chat.build_queue_terminal(
            terminal_state=chat.TERMINAL_STATE_AWAITING_APPROVAL,
            answer_present=False,
            worker_status=str(record.get("status") or ""),
            sources=[],
            scope_reason_code="",
            sources_error="",
            usage=usage,
            dataset_files=dataset_files,
            approval=chat.hitl_approval_handle(
                session_id=session_id or thread_id, parked=parked
            ),
        )
        published = queue.complete(request_id, None, terminal=terminal)
    else:
        if record.get("status") not in {"success", "partial"}:
            return _fail_report_turn(
                queue, request_id, record, session_id=session_id, write_back=write_back
            )
        if chat.usage_proves_zero_model_calls(usage):
            # 判据④：一次模型都没打的这一轮没有资格叫 done。真库台账说 0，就是 0；台账读不出
            # （authoritative=False）时这一格不执法，那是「无从证明」，usage 里原样带着。
            # 不宣布"重试也不会变"（retryable 走默认 True）：队列层没资格替契约宣布终局，
            # 与 is_non_retryable_error 那段同一个理由，重试用完才 dead。
            logger.error(
                f"[QueueWorker] request_id={request_id} 报告档零枚模型调用却想交答案，"
                "不落 done（reason=no_model_call_recorded）"
            )
            return _fail_report_turn(
                queue,
                request_id,
                {
                    "status": "failed",
                    "error": {
                        "code": NO_MODEL_CALL_READOUT,
                        "message": "model_calls 台账里这一轮一枚模型调用都没有",
                    },
                },
                session_id=session_id,
                write_back=write_back,
            )
        # 判据②：出处走的是同步道那两只现成的件（`_collect_document_sources` 取证、
        # `_authorized_source_rows` 复核），判定仍是 `scope.allows`，一行都不许多。
        visible_sources, scope_reason, sources_error = chat.queue_turn_sources(
            agent_results, principal
        )
        terminal = chat.build_queue_terminal(
            terminal_state=chat.TERMINAL_STATE_ANSWERED,
            answer_present=bool(answer),
            worker_status=str(record.get("status") or ""),
            sources=visible_sources,
            scope_reason_code=scope_reason,
            sources_error=sources_error,
            usage=usage,
            dataset_files=dataset_files,
        )
        published = queue.complete(request_id, answer, terminal=terminal)

    if not published:
        logger.info(
            "request_id={rid} 报告档结果已丢弃：运行途中被取消或租约已丢失 terminal_status={state}".format(
                rid=request_id,
                state=queue.status(request_id),
            )
        )
        _log_discard_cause(queue, request_id)
        return True
    if write_back:
        _save_background_turn(session_id, answer)
    logger.info(
        "request_id={rid} 报告档跑完 status={status} awaiting_hitl={awaiting} "
        "sources={sources} model_calls={calls}".format(
            rid=request_id,
            status=record.get("status"),
            awaiting=bool(parked),
            sources=len(visible_sources),
            calls=usage.get("model_calls"),
        )
    )
    return True


def process_one():
    """领一个队列请求，在续租心跳的护持下跑完它"""
    queue = _get_queue()
    message = queue.reserve(timeout=10)
    if message is None:
        return False  # 队列为空

    # R227：从领走到发布答案为止，租约每 lease_seconds/3 续一次格。09-25 实测一档报告题
    # 跑完 311 s > lease_seconds=300，而从前只有 reserve() 写过一次租约 ⇒ 任务还在正常跑
    # 就被自己的持有者判成租约丢失，1519 字正文当场丢弃。心跳不许比这一轮活得更久:
    # complete() 一出口就停表，之后进程再卡死也不该替这条消息报活。
    heartbeat = _lease_beat(queue, message.request_id)
    with heartbeat:
        outcome = _process_reserved(queue, message)
    _report_lease(heartbeat, message.request_id)
    return outcome


def _process_reserved(queue: ReliableQueue, message: QueueMessage) -> bool:
    """领到任务之后那一段：判身份、定线程、跑图、发布结果。

    从 `process_one` 拆出来只为划清心跳的作用域——`complete()` 必须落在心跳里面,
    判据与语义一条没改。
    """
    request_id = message.request_id
    payload = message.payload or {}
    user_message = str(payload.get("message") or "")
    session_id = str(payload.get("session_id") or "")
    owner_id = _owner_from(payload)

    logger.info(f"[QueueWorker] 处理中 request_id={request_id}: {user_message[:60]}")

    if not owner_id:
        # A queued task without an owning Principal must not run under a shared identity.
        logger.error(f"[QueueWorker] 拒绝执行 request_id={request_id}: 缺少授权主体")
        queue.fail_or_retry(request_id, "authorization_required")
        return True

    # R294：这一行之前，载荷里那份冻结的快照就是本轮身份——R290 挪完部门，后台
    # 那一轮还按旧部门跑。从此它在两条腿上都只作两件事用：定位用户库那一行的引用、
    # 以及漂移比对的证据。现取不到、账号停用、任何一维漂移 ⇒ 判失效，一个模型都不打。
    principal_payload, principal_provenance, identity_refusal = resolve_consumption_principal(
        payload
    )
    if identity_refusal:
        logger.error(
            f"[QueueWorker] request_id={request_id} 消费时刻身份不过闸 reason={identity_refusal}"
        )
        return _refuse_identity(
            queue,
            request_id,
            identity_refusal,
            session_id=session_id,
            write_back=bool(payload.get("write_back_session")),
        )

    # 缺少 session_id 时使用请求级线程，避免不同用户共享同一个 checkpointer 线程
    thread_id = session_id or f"queue:{request_id}"

    if _report_lane_requested(payload):
        # R37：报告档走**能挂起**的那张图，跑完再补写会话历史。判据⑦的护栏就在这两行：
        # 只有载荷自己声明了档位才进这个分支，没声明的一律走下面那条一字未动的老路。
        return _process_report_lane_turn(
            queue,
            request_id,
            payload,
            user_message=user_message,
            session_id=session_id,
            owner_id=owner_id,
            thread_id=thread_id,
            principal=principal_payload,
            principal_provenance=principal_provenance,
        )

    try:
        # C2: 队列走无 interrupt 的图，chart/export 自动执行不卡审批
        from app.agents.orchestrator import run_orchestrator_result
        from app.api.v1 import chat

        agent_result = run_orchestrator_result(
            user_message,
            thread_id=thread_id,
            # R294：同上——图里拿到的是消费时刻的投影，随行的签名由
            # app/agents/tools.py::_tool_principal 认账，缺它就不许当身份用。
            user={"principal": principal_payload, PRINCIPAL_PROVENANCE_KEY: principal_provenance},
        )
        record = agent_result.model_dump() if hasattr(agent_result, "model_dump") else dict(agent_result or {})
        record_agent_result(record, owner_id=owner_id, session_id=session_id, entry_point="queue")

        if record.get("status") not in {"success", "partial"}:
            code = str((record.get("error") or {}).get("code") or record.get("status") or "internal_error")
            if is_non_retryable_error(record):
                # R81：契约已经判定"重试也不会变"的终态（R64/R65 的两枚授权拒绝码）
                # 不再占用重试名额，直接落 dead。原因码单独进日志：前者是授权设计的正常
                # 后果，后者是故障，混在一行里运维会查错地方。
                terminal_status = queue.fail_or_retry(request_id, code, retryable=False)
                bookkeeping = queue.failure(request_id)
                logger.error(
                    f"[QueueWorker] request_id={request_id} 终态不可重试，不再重投 -> {terminal_status}: {code} "
                    f"(reason={NON_RETRYABLE_DEAD_REASON} "
                    f"attempts={bookkeeping.get('attempts')} max_attempts={bookkeeping.get('max_attempts')})"
                )
                return True
            logger.error(f"[QueueWorker] request_id={request_id} 未产生业务结论: {code}")
            queue.fail_or_retry(request_id, code)
            return True

        # R254 判据②③④：这条老腿同样要交结构化终态。它走的是无 interrupt 的图，永远不会
        # 挂起，所以只有两枚读数要补：出处与 token。principal 从载荷里还原，放行判定仍是
        # `scope.allows`——本单不新增也不放宽任何一道权限。
        usage = chat.read_model_call_usage(request_id)
        if chat.usage_proves_zero_model_calls(usage):
            logger.error(
                f"[QueueWorker] request_id={request_id} 零枚模型调用却想交答案，不落 done"
                f"（reason={NO_MODEL_CALL_READOUT}）"
            )
            queue.fail_or_retry(request_id, NO_MODEL_CALL_READOUT)
            return True
        visible_sources, scope_reason, sources_error = chat.queue_turn_sources(
            {"orchestrator": record}, principal_payload
        )
        answer = str(record.get("answer") or "")
        # R514：这条老腿的证据袋就是上面那只 `record`——`run_orchestrator_queue` 已经把各
        # worker 的 evidence 合进同一枚 canonical 记录，所以这里交的是与出处同一只袋子、
        # 同一个键名形状 {"orchestrator": record}（R254 判据②早已拿它喂 `queue_turn_sources`）。
        # 取数同样只走那枚在册收集器，本文件不拼第二份名字；零枚与多枚一律不传，整格缺席。
        dataset_files: list[str] = []
        chat._collect_dataset_filenames({"orchestrator": record}, dataset_files)
        terminal = chat.build_queue_terminal(
            terminal_state=chat.TERMINAL_STATE_ANSWERED,
            answer_present=bool(answer),
            worker_status=str(record.get("status") or ""),
            sources=visible_sources,
            scope_reason_code=scope_reason,
            sources_error=sources_error,
            usage=usage,
            dataset_files=dataset_files,
        )
        if not queue.complete(request_id, answer, terminal=terminal):
            logger.info(
                "request_id={rid} 结果已丢弃：运行途中被取消或租约已丢失 terminal_status={state}".format(
                    rid=request_id,
                    state=queue.status(request_id),
                )
            )
            _log_discard_cause(queue, request_id)
            return True
        logger.info(
            "request_id={rid} 完成 status={status} evidence={ev}".format(
                rid=request_id,
                status=record.get("status"),
                ev=len(record.get("evidence") or []),
            )
        )
        # R254 的读数另起一行：上面那句被 R81 钉成逐字文案
        #（`tests/test_r81_queue_terminal_retry.py::test_a_success_conclusion_still_completes_with_the_unchanged_log_line`），
        # 与本文件 `_log_discard_cause` 对同一族钉的处置一模一样——不往被钉的那句里塞字。
        logger.info(
            "request_id={rid} 终态读数 sources={sources} model_calls={calls} "
            "prompt_tokens={prompt} completion_tokens={completion}".format(
                rid=request_id,
                sources=len(visible_sources),
                calls=usage.get("model_calls"),
                prompt=(usage.get("prompt_tokens")),
                completion=(usage.get("completion_tokens")),
            )
        )

    except Exception as e:
        logger.error(f"[QueueWorker] 失败 request_id={request_id}: {e}")
        terminal_status = queue.fail_or_retry(request_id, str(e))
        logger.info(f"[QueueWorker] request_id={request_id} -> {terminal_status}")

    return True


def main():
    logger.info("[QueueWorker] 启动 — 等待队列请求...")
    try:
        queue = _get_queue()
    except QueueConnectionError as exc:
        logger.error(f"[QueueWorker] 可靠队列不可用: {exc}")
        return
    idle_count = 0

    while running:
        try:
            queue.requeue_expired()
            has_work = process_one()
            if has_work:
                idle_count = 0
            else:
                idle_count += 1
                if idle_count % 30 == 0:  # 每 5 分钟报告一次
                    pending = queue.redis.lrange(queue.pending_key, 0, -1)
                    processing = queue.redis.lrange(queue.processing_key, 0, -1)
                    logger.debug(
                        f"[QueueWorker] 空闲中... 队列={len(pending)} 处理中={len(processing)}"
                    )
        except Exception as e:
            logger.error(f"[QueueWorker] 异常: {e}")
            time.sleep(5)

    logger.info("[QueueWorker] 已停止")


if __name__ == "__main__":
    main()
