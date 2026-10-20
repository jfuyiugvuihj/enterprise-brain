"""R299 · 通知中心出口：一份收件箱，两个动作。

三条路由，形状与全仓既有出口同族（状态码与 detail 只取 ErrorEnvelope 已经追认过的那几枚，
裸码不新增，由 tests/test_r142_error_code_table_sync.py 那把扫描器看着）：

- @router.get("/notifications")            —— 分页读，未读数按全集总数交回（口径见
  app/notifications/inbox.py 文件头与 docs/api/contract-v1.md 的 R299 一节）
- @router.post("/notifications/read")     —— 标已读
- @router.post("/notifications/dismiss")  —— 划掉

写侧只有这两枚动作，且都幂等：同一枚 id 再点一次，结论不变，changed 从 True 变 False。幂等不是
"多打几次不报错"就算完，判据④要的是**回执也能分辨第一次与第 N 次**，所以 results 逐条带回
state 与 changed 两格。

收件人不从请求体里读。三枚路由的主体一律取 app.common.authorization.principal_from_request
（会话那一侧的权威投影），body 里出现 recipient / username / department 都算未登记字段整条拒
（extra=forbid）—— 否则任何人都能把状态写到别人名下，而这张表的全部意义就是「谁看过什么」。

对不上号的 id 不写、不建、也不解释：回执只说 not_addressable。别人的通知与根本不存在的通知是
同一张脸，这一格不给枚举编号留缝。判定本身在 app/notifications/inbox.py::can_address，它把问题
原样转给那三本账自己的读路径，本文件不参与裁权限。

写侧那两枚动作（POST /notifications/read 与 /dismiss，同走 _apply）翻译两类具名错：生命周期
台账（NotificationStateStoreMissing）与审批账本（PendingApprovalStoreMissing），两张脸同一句
503 storage_unavailable。R381 之前那一支只接前一枚，后一枚由 inbox.can_address 具名上抛、穿过
出口就撞上裸 500 纯文本 —— 那本账缺表与这本账缺表说的是同一句运维真话（去跑 migrations/0008）。
读侧那一支仍只接生命周期一枚：审批那本账的缺表早在 sources.approval_candidates 里折成逐腿缺席，
今天没有任何抛出链走到读出口，把一枚问不出的腿再折成整页 503 只是替那张脸多留一条后门。缺列与
驱动缺失那两格也仍原样上抛：靠报错文案把它们认出来再折进 503，就是替真 bug 打掩护，那是另一本
账（三格排查路与本单边界见 docs/api/contract-v1.md 的 R381 一节）。
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.logger import logger
from app.common.permissions import ACTION_VIEW
from app.notifications import states as state_store
from app.notifications.contracts import (
    MAX_NOTIFICATION_ID_CHARS,
    NotificationIdError,
    parse_notification_id,
)
from app.notifications.inbox import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    STATE_FILTERS,
    build_inbox,
    can_address,
    writable_state,
)
from app.storage import pending_approvals

router = APIRouter()

#: 一次写最多带多少枚 id。上界的意义是别让一次点击就能把三本账各扫一遍：读一次收件箱已经是
#: 三次账本读，逐条复核可寻址性又是 N 次，没有上界就是一条可以自肥的放大路径。
MAX_IDS_PER_CALL = 50

#: 回执里那一格「这一枚我管不着」的稳定码。它同时覆盖"不存在"与"不是你的"两种情形，两种
#: 情形不许长出不同的脸。
NOT_ADDRESSABLE = 'notification_not_addressable'

REASON_APPLIED = 'applied'


class NotificationActionBody(BaseModel):
    """只有 ids 一个键。收件人、部门、状态目标一律不接受客户端代填。"""

    model_config = ConfigDict(extra='forbid')

    ids: list[str]


def _principal_or_401(request: Request | None):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail='authentication_required')
    return principal


def _clean_state_filter(value: str) -> str:
    state = str(value or 'all').strip().lower()
    if state not in STATE_FILTERS:
        raise HTTPException(status_code=422, detail='validation_error')
    return state


def _clean_page(limit: int, offset: int) -> tuple[int, int]:
    if limit < 1 or limit > MAX_LIMIT:
        raise HTTPException(status_code=422, detail='validation_error')
    if offset < 0:
        raise HTTPException(status_code=422, detail='validation_error')
    return int(limit), int(offset)


async def _ids_from_body(request: Request) -> list[str]:
    """解析并校验一次写的 ids。形状不合整条 422，不做「能收几条算几条」的半收。"""
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 - 非法 JSON 与超限同脸，都是 422
        logger.warning(f'[R299] 通知写入口拒收一次请求体解析失败: {type(exc).__name__}')
        raise HTTPException(status_code=422, detail='validation_error') from exc
    try:
        body = NotificationActionBody.model_validate(payload)
    except ValidationError as exc:
        # 只记字段名，不记值：值里可能就是别人的通知编号，一次 422 不该往日志里抄一份台账。
        unwanted = sorted({str(item.get('loc', ('-',))[0]) for item in exc.errors() if isinstance(item, dict)})
        logger.warning(f'[R299] 通知写入口拒收未登记字段 {len(unwanted)} 个（只记字段名）: {", ".join(unwanted)}')
        raise HTTPException(status_code=422, detail='validation_error') from exc

    raw = list(body.ids)
    if not raw or len(raw) > MAX_IDS_PER_CALL:
        raise HTTPException(status_code=422, detail='validation_error')
    ids: list[str] = []
    for value in raw:
        text = str(value or '-').strip()
        if not text or len(text) > MAX_NOTIFICATION_ID_CHARS:
            raise HTTPException(status_code=422, detail='validation_error')
        try:
            parse_notification_id(text)
        except NotificationIdError as exc:
            # 形状不合（认不出源、拼不出键）是客户端的错，当场拒；但拒的理由只能是形状，
            # 不能是"这一枚存不存在"，否则 422 就成了枚举工具。
            raise HTTPException(status_code=422, detail='validation_error') from exc
        if text not in ids:
            ids.append(text)
    return ids


async def _apply(request: Request, action: Literal['read', 'dismiss']) -> dict[str, Any]:
    principal = _principal_or_401(request)
    recipient = str(getattr(principal, 'username', '-') or '-')
    ids = await _ids_from_body(request)
    requested_state = writable_state(action)

    results: list[dict[str, Any]] = []
    changed_count = 0
    try:
        for notification_id in ids:
            if not await can_address(principal, request, notification_id):
                # 一次越权写都过不去，而且每一笔都在既有那本审计账里留痕（不新造台账）。
                record_audit(principal, ACTION_VIEW, 'denied', notification_id, NOT_ADDRESSABLE)
                results.append(
                    {
                        'id': notification_id,
                        'state': None,
                        'changed': False,
                        'reason': NOT_ADDRESSABLE,
                    }
                )
                continue
            outcome = state_store.apply_state(recipient, notification_id, requested_state)
            if outcome['changed']:
                changed_count += 1
            results.append(
                {
                    'id': notification_id,
                    'state': outcome['state'],
                    'changed': bool(outcome['changed']),
                    'reason': REASON_APPLIED,
                }
            )
    except (
        state_store.NotificationStateStoreMissing,
        pending_approvals.PendingApprovalStoreMissing,
    ) as exc:
        # 只接这两枚具名错：生命周期那一本与审批那一本，各自都缺表。把任何一次异常都
        # 翻成 503，等于替真正的 bug 打掩护（与看板同一条纪律）。审批那一枚由 inbox.can_address
        # 具名上抛（R373 的裁定是「不许静默吞」，不是「不许有正确出口」），出口此前只接生命周期
        # 那一枚，于是这张脸在客户机上是裸 500 纯文本 —— 答成 503 才是那句可执行的运维真话。
        raise HTTPException(status_code=503, detail='storage_unavailable') from exc

    return {
        'action': action,
        'requested': len(ids),
        'changed': changed_count,
        'results': results,
    }


@router.get('/notifications')
async def list_notifications(
    request: Request,
    state: str = 'all',
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """读这一位收件人的通知：三本既有账的投影，加上他自己的生命周期。"""
    principal = _principal_or_401(request)
    cleaned_state = _clean_state_filter(state)
    cleaned_limit, cleaned_offset = _clean_page(limit, offset)
    try:
        return await build_inbox(
            principal,
            request,
            state_filter=cleaned_state,
            limit=cleaned_limit,
            offset=cleaned_offset,
        )
    # 只接生命周期那一枚：审批那本账缺表在 sources.approval_candidates 已折成逐腿缺席，今天走不到
    # 这一支；把它接进来等于给「整页黑」多留一条后门（tests/test_r381_* 与 R373 的刀一共钉这一格）。
    except state_store.NotificationStateStoreMissing as exc:
        raise HTTPException(status_code=503, detail='storage_unavailable') from exc


@router.post('/notifications/read')
async def mark_notifications_read(request: Request) -> dict[str, Any]:
    """把若干枚通知标成已读。重复调用不改变结论，回执里 changed 会说清这一次动没动。"""
    return await _apply(request, 'read')


@router.post('/notifications/dismiss')
async def dismiss_notifications(request: Request) -> dict[str, Any]:
    """把若干枚通知从这个人的收件箱里划掉。已划掉的再划一次仍然是已划掉。"""
    return await _apply(request, 'dismiss')
