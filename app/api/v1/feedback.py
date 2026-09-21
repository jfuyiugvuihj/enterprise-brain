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

点击/浏览这类信号跟进单原文也提了，但那一路要前端埋点（前端半张单等总控另派），
本文件的 ``signal`` 枚举因此**只有两个值**，不预先收第三种。
"""
import os
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

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