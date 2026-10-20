"""R46 · 活动信号出口：把「采纳 / 驳回」记成文档粒度的计数，供检索排序当先验。

跟进单 §21 给 R46 立的三条判据里有两条半落在这个文件：③「只存计数不存内容」与禁止项
「不得把用户问题原文写进新表」，还有④「未授权者不能给别人的文档打分」。所以本文件的
写路径只有一条 INSERT，参数只有 ``(filename, 1, 0)`` 与 ``(filename, 0, 1)`` 两型——
**没有任何一条路径把请求体里的文本交给 SQL**。判据③靠的因此不是"记得清洗"，而是
"内容进不来"：

- 请求体只认 ``filename`` 与 ``signal`` 两个键，多一个键整条拒（422）；自由文本、备注、
  问题原文、答案摘录全在这一类里。拒的时候只把**字段名**写进日志，值不写——那个值
  很可能就是问题原文，打日志等于换个地方存；
- ``filename`` 上界 512，与 migrations/0011 上 ``length(filename) <= 512`` 那条 CHECK
  同值，两侧都是硬上界，不靠调用方自觉；
- 落库参数由 ``_record_signal`` 一处组装，用例直接抓它收到的东西（不必连真库）。

排序那一侧在 ``app/rag/retriever.py`` 的 ``rank_hits_by_activity``，读的就是这里写的两列
计数。鉴权沿用文档可见性的**唯一**判定 ``app/rag/filters.py::resolve_document_retrieval_scope``
——``app/common/rbac.py`` 的模块注释写着「文档可见性的判定不在这里，也不许回到这里」，
本文件照那句话办，于是"能不能给这篇打分"与"能不能看见这篇"是同一个答案，不多长一套规则。

本文件的 ``signal`` 枚举因此**只有两个值**，不预先收第三种：点击与浏览是**另一族动作**，落在
本文件后半段（R46 差格 a）的 ``/feedback/engagement`` 与 migrations/0019 那张事件表上。两族
不挤进同一枚枚举——「这篇有用」与「这篇被点开过」是两件不同的事，记进同一列就再也分不开是谁
说的，而排序读的恰恰是"谁说的"。
"""
import os
import re
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.logger import logger
from app.common.permissions import ACTION_VIEW
from app.documents.catalog import list_document_versions
from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope

router = APIRouter()

SIGNAL_ACCEPTED = "accepted"
SIGNAL_REJECTED = "rejected"
SIGNALS = (SIGNAL_ACCEPTED, SIGNAL_REJECTED)

#: filename 的硬上界，与 0011 表上那条 CHECK 同值（两处必须相等，用例互相核对）。
MAX_FILENAME_CHARS = 512

#: username 的硬上界，与 0019 表上 `length(username) BETWEEN 1 AND 64` 同值。这一格走的是服务端
#: 主体而不是请求体，出口仍然自己拦一道：账本的形状不该依赖"没人会乱给身份"。
MAX_USERNAME_CHARS = 64

#: 本文件唯一一处写库的语句。列清单与 0011 的列清单同生死：表里没有文本列，
#: 这条语句也就没有能装下文本的位置。
_UPSERT_SQL = """
INSERT INTO document_activity_signals AS s
    (filename, accepted_count, rejected_count, first_signal_at, last_signal_at)
VALUES (%s, %s, %s, NOW(), NOW())
ON CONFLICT (filename) DO UPDATE SET
    accepted_count = s.accepted_count + EXCLUDED.accepted_count,
    rejected_count = s.rejected_count + EXCLUDED.rejected_count,
    last_signal_at = NOW()
"""

#: 测试注入口：置成 callable 后本模块不再真连库（判据③④的用例都从这里进）。
_CONNECTION_FACTORY = None


def _connect():
    if _CONNECTION_FACTORY is not None:
        return _CONNECTION_FACTORY()
    import psycopg

    # DATABASE_URL 的口径只认 app/rag/pg_store.py 那一处，不在这里重抄一遍默认值。
    from app.rag import pg_store

    return psycopg.connect(pg_store.resolve_database_url(), connect_timeout=2)


class DocumentFeedback(BaseModel):
    """一篇文档 + 一枚信号。除这两个键以外，请求体什么都不接受。"""

    model_config = ConfigDict(extra="forbid")

    filename: str
    signal: Literal["accepted", "rejected"]


ALLOWED_FIELDS = frozenset({"filename", "signal"})


def _json_object(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="validation_error")
    return payload


def _reject_extra_fields(payload: dict) -> None:
    """把任何"计数以外"的字段挡在写路径外面（判据③与禁止项的落点）。

    未知字段是**拒**而不是**忽略**：忽略等于告诉调用方"带上原文也能过"，那半句判据就只剩
    表结构在守。日志里只出现字段名，绝不出现值。
    """
    unexpected = sorted(str(key) for key in set(payload) - ALLOWED_FIELDS)
    if not unexpected:
        return
    logger.warning(
        "[R46] 活动信号出口拒收未登记字段 %d 个（只记字段名，不记值）：%s",
        len(unexpected),
        ", ".join(unexpected),
    )
    raise HTTPException(status_code=422, detail="validation_error")


def _clean_filename(value: Any) -> str:
    filename = str(value or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="validation_error")
    if len(filename) > MAX_FILENAME_CHARS or any(char in filename for char in ("\r", "\n", "\x00")):
        # 上界与"不许带换行"都是隐私与注入的双面护栏：一段问题原文比这个长，塞不进 key 列。
        raise HTTPException(status_code=422, detail="validation_error")
    return filename


def _principal_or_401(request: Request | None):
    if request is None:  # pragma: no cover - 路由总会带 Request，留给付调用方
        raise HTTPException(status_code=401, detail="authentication_required")
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return principal


def _newest_version_or_404(filename: str) -> dict:
    rows = list_document_versions(filename)
    if not rows:
        # 不存在的文档不收信号：否则任何人都能往计数表里写任意 key，那张表就不再只描述
        # 真实文档，排序读到的"先验"也就没了出处。
        raise HTTPException(status_code=404, detail="resource_not_found")
    return rows[0]


def _visibility_decision(principal, filename: str, row: dict):
    """能不能给这篇文档打点＝能不能看见这篇文档，同一个判定，不多一套规则。"""
    try:
        scope = resolve_document_retrieval_scope(principal)
    except RetrievalScopeError as exc:
        return False, exc.code
    if not scope.allows(row):
        return False, "permission_denied"
    return True, "document_visible"


def record_document_signal(*, filename: str, accepted: int, rejected: int) -> tuple[int, int]:
    """把一枚计数写进 0011 那张表，返回写后的 (accepted, rejected)。

    🔴 参数三元组 ``(filename, accepted, rejected)`` 是本文件唯一的写内容，两个计数恒为
    0/1。任何想带文本出去的做法都要新写一条 SQL，而那条 SQL 会先被
    ``tests/test_r46_activity_signals.py`` 的列名清单拦下。
    """
    statement_params = (filename, accepted, rejected)
    try:
        with _connect() as connection:
            connection.execute(_UPSERT_SQL, statement_params)
            row = connection.execute(
                "SELECT accepted_count, rejected_count FROM document_activity_signals WHERE filename = %s",
                (filename,),
            ).fetchone()
            connection.commit()
    except Exception as exc:
        # 表还没建（业主未跑 0011）与库连不上都归到这里：稳定的存储码，不让一次
        # 记账失败冒充"信号已收下"。
        logger.warning(f"[R46] 活动信号写入失败: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    if row is None:  # pragma: no cover - upsert 之后读不到只剩并发删除
        raise HTTPException(status_code=503, detail="storage_unavailable")
    # 刚 commit 就把排序侧那份快照作废，免得同一个人手上出现两本账：这枚回执交回的是库里
    # 刚写的数字，而下一问读的是最长 ACTIVITY_PRIOR_TTL_SECONDS 的整表快照——"回执说 7 次、
    # 排序还按 6 次排"就是这么来的。代价是下一问多读一趟表：一次打点换一趟整表读，划算；
    # 而且写成功本身就证明库连得上，顺带清掉读失败那一侧的退避窗口也是应该的。
    from app.rag.retriever import reset_activity_priors

    reset_activity_priors()

    return int(row[0]), int(row[1])


@router.post("/feedback/document")
async def submit_document_feedback(request: Request) -> dict:
    """收一枚文档粒度的采纳/驳回信号，只落计数。"""
    principal = _principal_or_401(request)
    try:
        payload = _json_object(await request.json())
    except Exception:
        raise HTTPException(status_code=422, detail="validation_error")
    _reject_extra_fields(payload)
    try:
        body = DocumentFeedback.model_validate(payload)
    except ValidationError:
        raise HTTPException(status_code=422, detail="validation_error")

    filename = _clean_filename(body.filename)
    signal = str(body.signal)
    row = _newest_version_or_404(filename)
    allowed, reason_code = _visibility_decision(principal, filename, row)
    if not allowed:
        # 拒绝也要留痕：判据④要能证明越权是 0 条通过，而不只是返回码好看。
        record_audit(principal, ACTION_VIEW, "failure", resource=filename, reason=reason_code)
        raise HTTPException(status_code=403, detail=reason_code)
    record_audit(principal, ACTION_VIEW, "success", resource=filename, reason=reason_code)

    accepted, rejected = record_document_signal(
        filename=filename,
        accepted=1 if signal == SIGNAL_ACCEPTED else 0,
        rejected=1 if signal == SIGNAL_REJECTED else 0,
    )
    logger.info(
        "[R46] 活动信号入账: filename=%s signal=%s accepted=%d rejected=%d",
        filename,
        signal,
        accepted,
        rejected,
    )
    return {
        "status": "ok",
        "filename": filename,
        "signal": signal,
        "accepted_count": accepted,
        "rejected_count": rejected,
    }


@router.get("/feedback/document")
async def read_document_feedback(request: Request, filename: str = "") -> dict:
    """读一篇文档当前的计数，附带"这份先验是从哪来的"——没有它，0 就分不清是没信号还是没读到。"""
    principal = _principal_or_401(request)
    clean = _clean_filename(filename)
    row = _newest_version_or_404(clean)
    allowed, reason_code = _visibility_decision(principal, clean, row)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason_code)

    from app.rag.retriever import activity_prior_diagnostics, activity_priors

    # 读先验走 retriever 那一份快照：两处各写一条 SELECT，早晚会读成两个答案。
    priors = activity_priors()
    counts = priors.get(clean) or {}
    diagnostics = activity_prior_diagnostics()
    return {
        "filename": clean,
        "accepted_count": int(counts.get("accepted") or 0),
        "rejected_count": int(counts.get("rejected") or 0),
        "prior_source": diagnostics.get("source", ""),
        "prior_reason": diagnostics.get("reason", ""),
        "prior_enabled": bool(diagnostics.get("enabled")),
    }


# ==================== R46 差格 a · 点击与浏览（出处被真看过 → 相关度先验）====================

#: 两枚动作的稳定码，与 migrations/0019 上那枚 `event_type IN ('click','view')` 同值同形：
#: 想加第三种动作就得再排一枚迁移改那条 CHECK，而不是往这一列里塞一段自由文本。
ENGAGEMENT_CLICK = "click"
ENGAGEMENT_VIEW = "view"
ENGAGEMENT_EVENTS = (ENGAGEMENT_CLICK, ENGAGEMENT_VIEW)

#: 载荷的四格，一格不多。`username` 不在其中（服务端从鉴权主体取），`occurred_at` 也不在
#: （库里 NOW() 生成）——客户端既不能替别人打点，也不能替自己造时间。
ENGAGEMENT_ALLOWED_FIELDS = frozenset({"filename", "event", "thread_id", "rank"})

#: thread_id 的硬上界与字符集，与 0019 上那枚 CHECK 同值同形（两处必须相等，用例互相核对）。
#: 这枚正则里没有空格、没有换行、没有中日韩：一段问题原文**结构上**塞不进这一格。
MAX_THREAD_ID_CHARS = 128
_THREAD_ID_SHAPE = re.compile(r"^[A-Za-z0-9_.:#-]{1,128}$")

#: 名次下界 1、上界 100，与 0019 上 `result_rank >= 1 AND result_rank <= 100` 同值。
MIN_RESULT_RANK = 1
MAX_RESULT_RANK = 100

#: 「我自己的点击账」那一页最多取几条。上界给死是为了让这条读腿永远不必全表扫，
#: 不是为了限制谁看历史——真要翻旧账的人有的是办法，而没上界的那条 SQL 早晚变成一次拒绝服务。
MAX_LEDGER_ROWS = 100
DEFAULT_LEDGER_ROWS = 20

#: 本段唯一一条写库语句。五枚参数与 0019 的五枚载荷列一一对应，表里没有文本列，这条语句
#: 也就没有能装下文本的位置。`ON CONFLICT DO NOTHING` 是那枚 UNIQUE 的落点：同一个人、同一道
#: 题、同一条出处、同一种动作只算一次事实，重复打点刷不出分数（它**不是**按人限额）。
_INSERT_ENGAGEMENT_SQL = """
INSERT INTO document_engagement_events
    (username, thread_id, filename, result_rank, event_type, occurred_at)
VALUES (%s, %s, %s, %s, %s, NOW())
ON CONFLICT (username, thread_id, filename, event_type) DO NOTHING
RETURNING event_id
"""

#: `RETURNING event_id` 只为买到一个读数：这一笔是真落下了，还是被那枚 UNIQUE 当成重复打点
#: 挡在门外（交回的 `deduplicated` 就是它）。它不参与任何判定，也不带内容。
#: 写后读回的那两枚计数：按 filename 聚合，与 app/rag/retriever.py 排序侧那条聚合语句同形。
#: 🔴 两枚都不带 username——回执说的是"这篇被看过多少次"，不是"你被记录成什么样"。
_READ_ENGAGEMENT_COUNTS_SQL = """
SELECT COUNT(*) FILTER (WHERE event_type = 'click') AS clicks,
       COUNT(*) FILTER (WHERE event_type = 'view') AS views
FROM document_engagement_events
WHERE filename = %s
"""

#: 那一页「我自己点过什么」的读腿：WHERE 里那格 username 是本段的隐私边界本身——点了别人
#: 看不见的东西不该出现在别人的账上，反之也一样。
_READ_ENGAGEMENT_LEDGER_SQL = """
SELECT username, thread_id, filename, result_rank, event_type, occurred_at
FROM document_engagement_events
WHERE username = %s
ORDER BY occurred_at DESC, event_id DESC
LIMIT %s
"""


class DocumentEngagement(BaseModel):
    """一条出处 + 一次动作 + 一道题 + 一个名次。除这四格以外，请求体什么都不接受。"""

    model_config = ConfigDict(extra="forbid")

    filename: str
    event: Literal["click", "view"]
    thread_id: str
    # rank 走 StrictInt 而不是 int：这格是键，不是数字文本。pydantic 的宽松模式会把 True 折成 1、
    # 把 "3" 折成 3、把 3.0 折成 3（本机 pydantic 2.13.4 实测）。名次写错的人该收到一次拒绝，
    # 而不是拿到一条他压根没打过的第 1 名记账——与 _clean_thread_id 拒绝清洗同一个理由。
    rank: StrictInt


def _reject_extra_engagement_fields(payload: dict) -> None:
    """把载荷四格以外的字段挡在点击账外面（判据①与禁止项在**这一路**的落点）。

    与前半张 `_reject_extra_fields` 同一个口径，不复用那一枚：`ALLOWED_FIELDS` 与
    `DocumentFeedback` 的字段清单被在册钉子判等，两路共用一套清单就会有一路说谎。
    日志里只出现字段名，绝不出现值。
    """
    unexpected = sorted(str(key) for key in set(payload) - ENGAGEMENT_ALLOWED_FIELDS)
    if not unexpected:
        return
    logger.warning(
        "[R46a] 点击账出口拒收未登记字段 %d 个（只记字段名，不记值）：%s",
        len(unexpected),
        ", ".join(unexpected),
    )
    raise HTTPException(status_code=422, detail="validation_error")


def _clean_thread_id(value: Any) -> str:
    """题号：与 0019 那枚 CHECK 两侧同值同形，出口先拦一道，不等库里报错。

    为什么不"清洗"成合法值：这格是键，不是文本。改一个字符它就指别的题了，那种"修好"比拒了
    更坏——所以只有整条拒绝这一支。
    """
    thread_id = str(value or "")
    if len(thread_id) > MAX_THREAD_ID_CHARS or not _THREAD_ID_SHAPE.match(thread_id):
        raise HTTPException(status_code=422, detail="validation_error")
    return thread_id


def _clean_rank(value: Any) -> int:
    """名次：只认整数，且落在 1..100（越界＝这一条压根不该被记账，而不是夹到边界上）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=422, detail="validation_error")
    if value < MIN_RESULT_RANK or value > MAX_RESULT_RANK:
        raise HTTPException(status_code=422, detail="validation_error")
    return int(value)


def _clean_event(value: Any) -> str:
    event = str(value or "").strip().lower()
    if event not in ENGAGEMENT_EVENTS:
        raise HTTPException(status_code=422, detail="validation_error")
    return event


def _principal_username(principal) -> str:
    """身份只从鉴权主体取，且必须过与 0019 同一形的上界：过不了就是这枚主体不该记账。"""
    username = str(getattr(principal, "username", "") or "").strip()
    if not username or len(username) > MAX_USERNAME_CHARS:
        raise HTTPException(status_code=401, detail="authentication_required")
    return username


def record_document_engagement(
    *, username: str, thread_id: str, filename: str, rank: int, event: str
) -> dict:
    """写一枚点击/浏览事件，返回这篇文档当前的两枚聚合计数。

    🔴 递给 SQL 的参数五枚：身份、题号、文档名、名次、动作码。没有一枚的位置能放正文，而
    返回值那两格是 `COUNT(*) FILTER`，不含任何人读过什么内容。
    """
    statement_params = (username, thread_id, filename, rank, event)
    try:
        with _connect() as connection:
            inserted = connection.execute(_INSERT_ENGAGEMENT_SQL, statement_params).fetchone()
            counts = connection.execute(_READ_ENGAGEMENT_COUNTS_SQL, (filename,)).fetchone()
            connection.commit()
    except Exception as exc:
        # 0019 没跑、库连不上、约束炸了，都归到同一枚稳定的存储码：一次记账失败不许冒充
        # "已看过"。缺表那一支尤其要响——静默吞掉它，排序侧就永远读不到这半张先验。
        logger.warning(f"[R46a] 点击账写入失败: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    if counts is None:  # pragma: no cover - 聚合语句恒有一行，走到这里只剩连接异常
        raise HTTPException(status_code=503, detail="storage_unavailable")
    # 刚 commit 就把排序侧那两份快照一起作废：回执说"这篇被点过 4 次"而下一问还按没点过排，
    # 那种两本账的读数比先验不准更难查。清两路而不是只清一路——一次写改变的是"信号"这件事。
    from app.rag.retriever import reset_signal_priors

    reset_signal_priors()
    return {
        "clicks": int(counts[0] or 0),
        "views": int(counts[1] or 0),
        "deduplicated": inserted is None,
    }


def read_engagement_ledger(*, username: str, limit: int) -> list[dict]:
    """取「这个人点过哪些出处」那一页：列清单固定六枚，没有一格装得下内容。"""
    try:
        with _connect() as connection:
            rows = connection.execute(_READ_ENGAGEMENT_LEDGER_SQL, (username, limit)).fetchall()
    except Exception as exc:
        logger.warning(f"[R46a] 点击账读回失败: {type(exc).__name__}")
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    ledger = [
        {
            "username": str(row[0]),
            "thread_id": str(row[1]),
            "filename": str(row[2]),
            "rank": int(row[3]),
            "event": str(row[4]),
            "occurred_at": str(row[5]),
        }
        for row in rows or []
    ]
    # 🔴 判据③的结构落点：SQL 里那格 username 是唯一过滤条件，所以**读到别人的行**本身
    # 就说明这条读腿被改坏了。宁可在这里当场关账（403 + 拒绝账），也不把别人的阅读史递出去。
    if any(item["username"] != username for item in ledger):
        raise HTTPException(status_code=403, detail="permission_denied")
    return ledger


@router.post("/feedback/engagement")
async def submit_document_engagement(request: Request) -> dict:
    """收一枚出处级的点击/浏览动作，只落"谁在哪道题里看了第几名的哪一篇"。"""
    principal = _principal_or_401(request)
    try:
        payload = _json_object(await request.json())
    except Exception:
        raise HTTPException(status_code=422, detail="validation_error")
    _reject_extra_engagement_fields(payload)
    try:
        body = DocumentEngagement.model_validate(payload)
    except ValidationError:
        raise HTTPException(status_code=422, detail="validation_error")

    username = _principal_username(principal)
    filename = _clean_filename(body.filename)
    thread_id = _clean_thread_id(body.thread_id)
    rank = _clean_rank(body.rank)
    event = _clean_event(body.event)

    row = _newest_version_or_404(filename)
    allowed, reason_code = _visibility_decision(principal, filename, row)
    if not allowed:
        # 点的是读不到的出处 ⇒ 拒，且留一行拒绝账（判据③）。这一族动作在权限上等价于
        # 一次查看，所以复用 ACTION_VIEW 与文档侧同一枚码，不开第二本账。
        record_audit(principal, ACTION_VIEW, "failure", resource=filename, reason=reason_code)
        raise HTTPException(status_code=403, detail=reason_code)
    record_audit(principal, ACTION_VIEW, "success", resource=filename, reason=reason_code)

    counts = record_document_engagement(
        username=username, thread_id=thread_id, filename=filename, rank=rank, event=event
    )
    logger.info(
        "[R46a] 点击账入账: username=%s filename=%s event=%s clicks=%d views=%d",
        username,
        filename,
        event,
        counts["clicks"],
        counts["views"],
    )
    return {
        "status": "ok",
        "username": username,
        "filename": filename,
        "thread_id": thread_id,
        "rank": rank,
        "event": event,
        "clicks": counts["clicks"],
        "views": counts["views"],
        "deduplicated": counts["deduplicated"],
    }


@router.get("/feedback/engagement")
async def read_document_engagement(request: Request, limit: int = DEFAULT_LEDGER_ROWS) -> dict:
    """读回**自己的**点击账，附带"这份先验是从哪来的"——没它，0 分不清是没点过还是没读到。

    🔴 没有 `username` 查询参数，也没有按别人身份读的那一支：这半张账回答的是"我看过哪几条
    出处"，一旦能按别人的身份读，它就长成一份没人授权过的员工阅读画像。管理员也不例外。
    """
    principal = _principal_or_401(request)
    username = _principal_username(principal)
    if limit < MIN_RESULT_RANK or limit > MAX_LEDGER_ROWS:
        raise HTTPException(status_code=422, detail="validation_error")

    ledger = read_engagement_ledger(username=username, limit=limit)
    from app.rag.retriever import engagement_prior_diagnostics

    diagnostics = engagement_prior_diagnostics()
    return {
        "username": username,
        "rows": ledger,
        "returned": len(ledger),
        "limit": int(limit),
        "prior_source": diagnostics.get("source", ""),
        "prior_reason": diagnostics.get("reason", ""),
        "prior_enabled": bool(diagnostics.get("enabled")),
    }
