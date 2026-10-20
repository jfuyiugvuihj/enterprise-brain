"""R299 · 收件箱读模型：把三条源拼成一份带页与计数的答复，并守住「谁能对哪一枚动手」。

判据④在这一层落地，两条口径写死在这里，契约里也是这么写的：

- returned 是**本页长度**（这一轮交回了几条），total 与 unread_total 是**全集总数**（这位收件
  人在候选窗口内看得见、且没有被自己划掉的条数与其未读数），两者永远各自命名，没有一个裸
  count 可以互相冒充。R278 就是在一个「count 到底是页长还是总数」说不清的格子上把徽标摘掉
  的，本期不再踩第二次。未读那一枚数的是**有依据说它没读过**的条数：状态这本账答不上来时它数
  的是 0，而那件事由下面 state_ledger 那一格说出去 —— 0 在这儿说的是「数不清」，不是「都没有」。
- 全集是「候选窗口内的全集」，不是整本账的全集。三本账各自有界（告警那一腿自己就只交
  ALERT_LEG_PAGE 行，每枚源再过一道 SOURCE_WINDOW），所以响应带 is_exact：窗口一旦裁掉过任何
  一条，它就是 False。把下界说成精确数才是假话，数得动与否在这里是看得见的字段。

「划掉」(dismissed) 的那一条不进列表、也不进 total 与 unread_total —— 它已经从这个人的收件箱
里出去了。read 反过来：仍然在列表里，只是不再算未读。这两个动作对计数的不同影响是生命周期语
义本身，不是实现细节，所以写进契约并由用例钉住。

第三张脸自 R388 起不许再被折进上面两枚里的任意一枚：生命周期**这本账本身**可以答不上来（客户
机上 PG 没起或 0016 没跑，见 app/notifications/states.py::recipient_states 交回的 None）。基点上
那一格交回的是空 dict，于是 `stored.get(item.id) or STATE_UNREAD` 把每一条都判成未读，
unread_total 跟着虚高 —— 与「把问不出说成没有」是同句病，只不过反过来说成「全是新的」。今天的
处置抄 R373 那一刀（那一格不供数、别的一格照答）：列表照读，那三本源账答得出多少就答多少；状态
这一格逐条交回 `null`，两枚未读计数一枚都不把未知算进去；缺席这件事登记在本文件新添的
`state_ledger` 那一格里，形状与 `sources` 同族（`included` / `reason_code` / 两枚 unknown 计数）。
整页 503 是第三种做法，也是本单明确不要的那一种：它替一格问不出把照答的腿一起打死。

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
    STATE_UNKNOWN,
    STATE_UNREAD,
    Notification,
    parse_notification_id,
)
from app.notifications.sources import (
    STORAGE_UNAVAILABLE,
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

#: 生命周期那一本账「答上了」时 `state_ledger.reason_code` 取的取值。它不是新词：与
#: sources.py::SourceBundle 的 reason_code 缺省逐字同（`'ok'`），由 tests/test_r388_* 现读那枚
#: dataclass 对账；答不上的那一枚也不新造，取的就是三枚源今天已经在用的 STORAGE_UNAVAILABLE。
STATE_LEDGER_ANSWERED = 'ok'


def _project(item: Notification, state: str | None) -> dict[str, Any]:
    """一行通知 -> 契约里那一格。state 为 None 就是「这一枚的状态答不上来」（R388），
    交回的是 JSON `null`，不是 `unread` —— 未读要有未读的依据，问不出不许冒充它。"""
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
    """拼出这一页收件箱：两条计数口径分开交回，第三张脸（状态这本账没答）另占一格。"""
    recipient = str(getattr(principal, 'username', '-') or '-')
    bundles = await collect(principal, request)
    # 两枚脸在这儿一枚都不许并（R388）：``None`` = 生命周期那本账这一格答不上来（生产而库不在位，
    # 见 states.recipient_states），``{}`` = 它答上了、而且确实没有行。基点上这两枚是同一枚，于是
    # 客户机上每一条通知都被判成未读 —— 徽标虚高，员工读过的痕迹一格不剩。
    read_back = state_store.recipient_states(recipient)
    ledger_answered = read_back is not None
    stored = read_back or {}

    merged: list[tuple[Notification, str | None]] = []
    for bundle in bundles:
        for item in bundle.items:
            state = (stored.get(item.id) or STATE_UNREAD) if ledger_answered else STATE_UNKNOWN
            if state == STATE_DISMISSED:
                # 划掉的那一条从这个人的收件箱里出去了；状态答不上来时无所谓这一步，因为它既
                # 不是 read 也不是 dismissed，只能留在列表里等那本账回来。
                continue
            merged.append((item, state))
    merged.sort(key=lambda pair: (pair[0].created_at, pair[0].id), reverse=True)

    total = len(merged)
    # 未读只数**有依据说它是未读**的那几条：状态答不上来的条目一枚都不进这两枚计数（判据①），
    # 它们各自占 unknown_total / unknown_returned 那一格，与上面 total 同源同分母。
    unread_total = sum(1 for _item, state in merged if state == STATE_UNREAD)
    unknown_total = sum(1 for _item, state in merged if state is STATE_UNKNOWN)
    # 按 unread / read 过滤时，状态答不上来的那些条目一枚都不进这一页：`unread` 那一档问的是
    # 「有依据说它没读过」，把 unknown 放进来就是替它答一次未读，与上面两枚计数同一把尺。
    page_rows = [
        pair for pair in merged if state_filter == 'all' or pair[1] == state_filter
    ]
    start = max(0, int(offset))
    bounded = page_rows[start : start + max(1, int(limit))]
    page = [_project(item, state) for item, state in bounded]
    unread_returned = sum(1 for row in page if row['state'] == STATE_UNREAD)
    unknown_returned = sum(1 for row in page if row['state'] is STATE_UNKNOWN)

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
        # 生命周期那一本账自己的读数（R388），形状与上面那台 sources 同族：`included` 说这一格
        # 答没答，`reason_code` 说为什么（只取在册那两枚：'ok' / STORAGE_UNAVAILABLE），
        # 两枚 unknown_* 数的是「这一格里有几条数不清」。它不参与上面任何一枚计数，正如
        # 缺席格的 candidates 不进 sources 的合计；`total` / `returned` 仍由那三本源账说话。
        'state_ledger': {
            'included': ledger_answered,
            'reason_code': STATE_LEDGER_ANSWERED if ledger_answered else STORAGE_UNAVAILABLE,
            'unknown_total': unknown_total,
            'unknown_returned': unknown_returned,
        },
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
        try:
            rows = pending_approvals.open_items(owner_user_id=owner, session_id=source_id)
        except pending_approvals.PendingApprovalStoreMissing:
            # R373：写侧与告警腿那枚 503 同一条口径 —— 「问不出」不是「这条已经不在了」。这里回
            # False 会把一轮还挂着的审批画成已解决，那条待办就被静默吞掉，所以原样上抛，不在这
            # 里替存储拒答换脸。出口今天只翻译生命周期台账那一枚缺表错（见 notifications.py 的
            # NotificationStateStoreMissing 那两支），把这枚账本缺表错一起答成 503 是出口那一格
            # 的活，不在本文件写域内，已具名上报总控。
            raise
        return bool(rows)

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
                # 503 `storage_unavailable`（app/api/v1/notifications.py 本来就在吐它；坐标按树取：基点
                # b498c88 读 :161/:191，R381 并树后的 903765b 读 :177/:209），不在这
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
        # R373：这一腿一字不接 —— 存储拒答（503）与鉴权拒答（401）本来就该按各自那张脸上抛到
        # 出口，把它折成 False 就是替一条还看得见的事项画成「它不在了」。
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
