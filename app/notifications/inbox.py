"""R299 · 收件箱读模型：把三条源拼成一份带页与计数的答复，并守住「谁能对哪一枚动手」。

判据④在这一层落地，两条口径写死在这里，契约里也是这么写的：

- returned 是**本页长度**（这一轮交回了几条），total 与 unread_total 是**全集总数**（这位收件
  人在候选窗口内看得见、且没有被自己划掉的条数与其未读数），两者永远各自命名，没有一个裸
  count 可以互相冒充。R278 就是在一个「count 到底是页长还是总数」说不清的格子上把徽标摘掉
  的，本期不再踩第二次。
- 全集是「候选窗口内的全集」，不是整本账的全集。三本账各自有界（告警那一腿自己就只交
  ALERT_LEG_PAGE 行，每枚源再过一道 SOURCE_WINDOW），所以响应带 is_exact：窗口一旦裁掉过任何
  一条，它就是 False。把下界说成精确数才是假话，数得动与否在这里是看得见的字段。

「划掉」(dismissed) 的那一条不进列表、也不进 total 与 unread_total —— 它已经从这个人的收件箱
里出去了。read 反过来：仍然在列表里，只是不再算未读。这两个动作对计数的不同影响是生命周期语
义本身，不是实现细节，所以写进契约并由用例钉住。

谁能对哪一枚通知动手，判法只有一条：那本账自己的读路径认不认这个人和这条记录
（app/notifications/can_address）。收件箱列表**不是**权限来源 —— 它被窗口裁过，拿它当权威会
让「刚刚被第三条源挤出去的一条」变成谁也划不掉的钉子户。
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.api.v1 import alerts as alerts_api
from app.api.v1 import chat as chat_api
from app.documents.index_policy import INDEX_STATUS_INDEXED
from app.notifications import states as state_store
from app.notifications.contracts import (
    NOTIFICATION_SOURCES,
    SOURCE_ALERT,
    SOURCE_APPROVAL,
    SOURCE_DOCUMENT,
    STATE_DISMISSED,
    STATE_READ,
    STATE_UNREAD,
    Notification,
    parse_notification_id,
)
from app.notifications.sources import (
    SourceBundle,
    alert_candidates,
    approval_candidates,
    document_candidates,
)
from app.storage import pending_approvals

#: 读端点默认的每页条数与硬上限。上限的意义与 GET /hitl/pending 同一条：页大小是调用方的
#: 偏好，不许把它读成「服务端愿意一次交回多少本账」。
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: 列表页允许的三格过滤。dismissed 不在其中：已经划掉的条目不在这本账的任何一页里，要查它
#: 得去告警屏或文档屏看那本账自己，收件箱不供第二份历史。
STATE_FILTERS = (STATE_UNREAD, STATE_READ, 'all')


def _project(item: Notification, state: str) -> dict[str, Any]:
    return {
        'id': item.id,
        'source_type': item.source_type,
        'source_id': item.source_id,
        'title': item.title,
        'detail': item.detail,
        'created_at': item.created_at,
        'state': state,
        'reference': dict(item.reference),
    }


def _bundle_for(source_type: str, bundles: list[SourceBundle]) -> SourceBundle:
    for bundle in bundles:
        if bundle.source_type == source_type:
            return bundle
    raise RuntimeError(f'unknown notification source in bundles: {source_type}')


async def collect(principal, request) -> list[SourceBundle]:
    """三枚源各读一次。任何一枚抛错都原样往上走，不在这里降级成空列表。"""
    return [
        await approval_candidates(principal),
        await alert_candidates(request),
        await document_candidates(request),
    ]


async def build_inbox(
    principal,
    request,
    *,
    state_filter: str = 'all',
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """拼出这一页收件箱，并把两条计数口径分开交回。"""
    recipient = str(getattr(principal, 'username', '-') or '-')
    bundles = await collect(principal, request)
    stored = state_store.recipient_states(recipient)

    merged: list[tuple[Notification, str]] = []
    for bundle in bundles:
        for item in bundle.items:
            state = stored.get(item.id) or STATE_UNREAD
            if state == STATE_DISMISSED:
                continue
            merged.append((item, state))
    merged.sort(key=lambda pair: (pair[0].created_at, pair[0].id), reverse=True)

    total = len(merged)
    unread_total = sum(1 for _item, state in merged if state == STATE_UNREAD)
    page_rows = [
        pair for pair in merged if state_filter == 'all' or pair[1] == state_filter
    ]
    start = max(0, int(offset))
    bounded = page_rows[start : start + max(1, int(limit))]
    page = [_project(item, state) for item, state in bounded]
    unread_returned = sum(1 for row in page if row['state'] == STATE_UNREAD)

    return {
        'notifications': page,
        'state': state_filter,
        'limit': int(limit),
        'offset': start,
        # 本页长度。
        'returned': len(page),
        'has_more': start + len(page) < len(page_rows),
        # 全集总数：候选窗口内、该收件人可见、未被自己划掉，不分页。
        'total': total,
        'unread_total': unread_total,
        'unread_returned': unread_returned,
        # 三本账各自有没有被窗口裁过。裁过任何一个，上面两个总数就只是下界。
        'is_exact': not any(bundle.truncated for bundle in bundles),
        'sources': {bundle.source_type: bundle.as_projection() for bundle in bundles},
    }


async def can_address(principal, request, notification_id: str) -> bool:
    """这个人能不能对这一枚通知做动作 —— 全部由那本账的读路径回答，收件箱列表不参与。

    三枚判定与三枚源**同源**：审批看 open_items(owner_user_id=..., session_id=...)，告警看
    GET /alerts/{id} 那个详情端点（它内部就是 _alert_scoped_select，行级归属谓词唯一的一份
    定义），文档看这份调用者自己的文档面板。所以「A 划不掉 B 的待办」「同部门不同密级的人划不
    掉他看不见的文档」这两件事都不是这里新写的规则，而是那三处本来就判出来的答案。
    """
    source_type, source_id = parse_notification_id(notification_id)

    if source_type == SOURCE_APPROVAL:
        owner = str(getattr(principal, 'user_id', '-') or '-')
        return bool(pending_approvals.open_items(owner_user_id=owner, session_id=source_id))

    if source_type == SOURCE_ALERT:
        try:
            alert_id = int(source_id)
        except (TypeError, ValueError):
            return False
        try:
            payload = await alerts_api.get_alert(alert_id, request)
        except HTTPException as exc:
            if exc.status_code == 503:
                # R366：503 与 404 说的是两句不同的话。404 是「这条已经不在了」，回 False 正好
                # 把它从这本账上关掉；503 是「这台机器此刻问不出」，回 False 就等于把一条还开着
                # 的告警画成已解决 —— 一条被静默吞掉的待办。所以原样上抛，由出口答它既有那一码
                # 503 `storage_unavailable`（app/api/v1/notifications.py:161 本来就在吐它），不在这
                # 里替存储拒答换脸。读侧同一条口径见 sources.py::alert_candidates。
                raise
            if exc.status_code in (401, 403, 404):
                # 三种脸在这里同形是刻意的：别人的告警与不存在的告警不许长出两张脸，那是枚举
                # 别人的告警编号用的。理由码在审计里，不在响应里。
                return False
            raise
        row = dict(payload.get('alert') or {})
        return str(row.get('status') or alerts_api.ALERT_STATUS_OPEN) not in (
            alerts_api.ALERT_TERMINAL_STATUSES
        )

    if source_type == SOURCE_DOCUMENT:
        filename, marker, version = str(source_id).rpartition('#v')
        if not marker or not filename or not version:
            return False
        payload = await chat_api.list_document_catalog(request)
        for row in payload.get('documents') or []:
            if str(row.get('filename') or '-') != filename:
                continue
            if str(row.get('version') or '-') != version:
                continue
            return str(row.get('index_status') or '-') == INDEX_STATUS_INDEXED
        return False

    return False  # pragma: no cover - parse_notification_id 已经拦下第四枚源


def writable_state(requested: str) -> str:
    """把动作名读成生命周期状态。只有 read 与 dismissed 两枚，其余一律拒。"""
    if requested == 'read':
        return STATE_READ
    if requested == 'dismiss':
        return STATE_DISMISSED
    raise ValueError(f'unsupported notification action: {requested}')


def source_types_in_order() -> tuple[str, ...]:
    return NOTIFICATION_SOURCES
