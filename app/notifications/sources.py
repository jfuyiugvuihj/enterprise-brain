"""R299 · 三条源的适配器：收件箱里的每一枚候选，都来自一本已经存在的账。

这是本期判据②的落点，也是本单最容易写歪的地方。跟进单原文禁止「自造事件源」与「开第二本待办
账」，AGENTS.md 又禁止平行实现，所以本文件只守一条很窄的规矩：一枚候选通知的「有没有」与「归
谁看」，全部由那本账自己的读路径回答，本文件一个字都不参与裁。落到代码上就是三行：

- 审批待办 -> app.storage.pending_approvals.open_items(owner_user_id=...) —— 与
  GET /api/v1/hitl/pending 逐字相同的那一次读，归属谓词在账本层，不在这里；
- 告警 -> app.api.v1.alerts.list_alerts(request) —— 直接调那个端点本身。资源级闸门
  _require_alert_management、行级归属 alert_row_visible / alert_row_scope_sql、行投影
  alert_ledger_row 三件事因此各只有一份定义，本文件不重抄任何一件；
- 文档索引完成 -> app.api.v1.chat.list_document_catalog(request) —— 与看板同一份读，看得见与
  否由 app/common/policy.py 的 authorization_decision 判完才回到这里。

为什么不去问图、也不新开一张事件表：R278 把顶栏那枚「待办」徽标摘掉，理由正是宁可无数也不要一
本没人复核的账。本期把同一句话执行到写侧：没有第四本账，也就不会有第四种说法。

唯一一处本文件自己下的判断是「什么算完成」：三枚各取自己那本账已经写下的那一格（awaiting 且未
过期 / status 不在 ALERT_TERMINAL_STATUSES / index_status 恰为 INDEX_STATUS_INDEXED），用的都是
那侧公开的常量，不新造第二份词表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException

from app.api.v1 import alerts as alerts_api
from app.api.v1 import chat as chat_api
from app.documents.index_policy import INDEX_STATUS_INDEXED
from app.notifications.contracts import (
    SOURCE_ALERT,
    SOURCE_APPROVAL,
    SOURCE_DOCUMENT,
    Notification,
    make_notification_id,
)
from app.storage import pending_approvals

#: 每枚源最多向本次读模型供多少枚候选。这是一个读侧代价上限，不是业务口径：三本账都不保证行数
#: 上界，收件箱也不许把自己变成一次全表扫描。被这一格裁掉的条数由 is_exact 说出去（见
#: app/notifications/inbox.py），所以它是看得见的边界，不是静默的截断。
SOURCE_WINDOW = 50

#: GET /alerts 那一腿自己永远只交 100 行。这一层界比 SOURCE_WINDOW 更早生效，所以本文件把它
#: 写成常量而不是裸数字：撞上了要在 is_exact 上留一笔，而不是让收件箱显得「查过了，只有这些」。
ALERT_LEG_PAGE = 100

#: 排序缺省值：created_at 读不到时沉到最旧，不参与编造一个时间。
_SORT_FALLBACK = '-'


@dataclass
class SourceBundle:
    """一枚源这一轮交回的东西：候选、有没有供数、被什么挡住、有没有被窗口裁过。

    reason_code 恒有一格：供数时是 ok，被拒时是那本账自己给出的稳定码。这里不新造码 —— 告警那
    一格的 403 交回什么就写什么，契约里也照抄那一个词。
    """

    source_type: str
    items: list[Notification] = field(default_factory=list)
    included: bool = True
    reason_code: str = 'ok'
    truncated: bool = False
    scanned: int = 0

    def as_projection(self) -> dict[str, Any]:
        return {
            'included': self.included,
            'reason_code': self.reason_code,
            'candidates': len(self.items),
            'scanned': self.scanned,
            'truncated': self.truncated,
        }


def _omitted(source_type: str, reason_code: str) -> SourceBundle:
    """这一格没有供数，而且说得出为什么：空列表不许伪装成「查过了，确实没有」。"""
    return SourceBundle(source_type=source_type, included=False, reason_code=reason_code)


def _sorted_window(
    items: list[Notification], window: int = SOURCE_WINDOW
) -> tuple[list[Notification], bool]:
    """新在前，截成一页读得动的长度，并如实报告有没有因此丢东西。"""
    ordered = sorted(
        items,
        key=lambda item: (str(item.created_at or _SORT_FALLBACK), item.id),
        reverse=True,
    )
    if len(ordered) <= window:
        return ordered, False
    return ordered[:window], True


def _approval_detail(record: Any) -> tuple[str, str]:
    steps = [str(step) for step in (getattr(record, 'parked_steps', None) or []) if str(step)]
    joined = "、".join(steps) if steps else "未记录";
    detail = f'挂起步骤：{joined}'
    expires = str(getattr(record, 'expires_at', '-') or '-')
    if expires:
        detail += f'；行动窗口至 {expires}'
    return '有一轮回答在等你决定', detail


async def approval_candidates(principal) -> SourceBundle:
    """审批待办：账本层已经按 owner 裁过，所以 A 的挂起不会出现在 B 的收件箱里。

    这一格刻意不向图复核（check_interrupt）。看板早就把这条口径写死并钉了用例：不复核的那本账
    只能高估、不会低估，所以收件箱里多挂一条其实已经办完的待办，与看板上多数一条是同一种偏差。
    要把这一格变精确的是 R289（复核过的聚合数），不在本期里顺手做半截。
    """
    owner = str(getattr(principal, 'user_id', '-') or '-')
    records = pending_approvals.open_items(owner_user_id=owner)
    items: list[Notification] = []
    for record in records:
        session_id = str(getattr(record, 'session_id', '-') or '-')
        if not session_id:
            continue
        title, detail = _approval_detail(record)
        items.append(
            Notification(
                id=make_notification_id(SOURCE_APPROVAL, session_id),
                source_type=SOURCE_APPROVAL,
                source_id=session_id,
                title=title,
                detail=detail,
                created_at=str(getattr(record, 'created_at', '-') or '-'),
                reference={'session_id': session_id},
            )
        )
    windowed, truncated = _sorted_window(items)
    return SourceBundle(
        source_type=SOURCE_APPROVAL,
        items=windowed,
        truncated=truncated,
        scanned=len(items),
    )


async def alert_candidates(request) -> SourceBundle:
    """告警：直接调那个端点本身，于是闸门、行级归属与行投影都只有一份定义。

    staff 走到这里会被 list_alerts 内的资源级闸门拒成 403。处理方式沿用看板那一条：这一格不供
    数并说出原因，而不是回一枚 0 —— 0 会长成「你们部门今天很平安」那张脸。

    R359 之后同一枚端点还会吐出第二张脸：生产环境而 PG 不在位时 `_require_ready_store()` 回
    503 `storage_unavailable`。这一支今天原样上抛，于是整页收件箱跟着黑掉 —— 一条腿问不出，
    其余几格也一并没了。这里把它折成同一枚 `_omitted`，理由码取那本账自己给出的那一枚（读
    `exc.detail`，它不是字符串才兜底写 `storage_unavailable`），零新增错误码、零新增 reason 词。
    「这一格不供数」与「这一类今天没有事」仍然是两张脸；403 那一支一个字都没动，权限的答案
    与存储的答案各自留名，不许被一次顺手统一并进同一格。
    """
    try:
        payload = await alerts_api.list_alerts(request)
    except HTTPException as exc:
        if exc.status_code == 403:
            reason = exc.detail if isinstance(exc.detail, str) else 'permission_denied'
            return _omitted(SOURCE_ALERT, reason)
        if exc.status_code == 503:
            # R366：存储拒答折成「这一格不供数」，不折成「这里真的没有东西」。
            reason = exc.detail if isinstance(exc.detail, str) else 'storage_unavailable'
            return _omitted(SOURCE_ALERT, reason)
        raise
    rows = [dict(row) for row in (payload.get('alerts') or [])]
    items: list[Notification] = []
    for row in rows:
        status = str(row.get('status') or alerts_api.ALERT_STATUS_OPEN)
        if status in alerts_api.ALERT_TERMINAL_STATUSES:
            # 已经关掉的那一条不是待办：告警屏里它还在（处置台账要看），收件箱不该再催一次人。
            continue
        alert_id = row.get('id')
        if alert_id is None:
            continue
        items.append(
            Notification(
                id=make_notification_id(SOURCE_ALERT, alert_id),
                source_type=SOURCE_ALERT,
                source_id=str(alert_id),
                title='有一条告警还没关闭',
                detail=str(row.get('message') or '-'),
                created_at=str(row.get('created_at') or '-'),
                reference={'alert_id': int(alert_id)},
            )
        )
    windowed, truncated = _sorted_window(items)
    return SourceBundle(
        source_type=SOURCE_ALERT,
        items=windowed,
        # 台账那一腿的 LIMIT 100 比 SOURCE_WINDOW 更早生效，两个数都要看：谁先撞上都得留一笔。
        truncated=truncated or len(rows) >= ALERT_LEG_PAGE,
        scanned=len(rows),
    )


async def document_candidates(request) -> SourceBundle:
    """文档索引完成：读的就是这份调用者自己的文档面板，不另起一次目录查询。

    判定链只有一条：list_document_catalog 已经跑过 _classify_document_rows 到
    authorization_decision，所以「同部门不同密级」那一格在这里是结构性做不到的越权 —— 能到得了
    这一行的，本来就是他在文档屏上看得见的文档。这里只再问一句这篇进索引了没有，用的还是
    catalog 自己写下的那一格。
    """
    payload = await chat_api.list_document_catalog(request)
    rows = [dict(row) for row in (payload.get('documents') or [])]
    items: list[Notification] = []
    for row in rows:
        if str(row.get('index_status') or '-') != INDEX_STATUS_INDEXED:
            # 没有这一格是历史行（R49 之前入库），不等于「没进索引」。这一区分来自
            # catalog.public_document_row 的口径，收件箱不许把它读成一条坏消息。
            continue
        filename = str(row.get('filename') or '-')
        version = str(row.get('version') or '-')
        if not filename or not version:
            continue
        source_id = f'{filename}#v{version}'
        items.append(
            Notification(
                id=make_notification_id(SOURCE_DOCUMENT, source_id),
                source_type=SOURCE_DOCUMENT,
                source_id=source_id,
                title='一份文档已经可以检索了',
                detail=filename,
                created_at=str(row.get('created_at') or '-'),
                reference={'filename': filename, 'version': version},
            )
        )
    windowed, truncated = _sorted_window(items)
    return SourceBundle(
        source_type=SOURCE_DOCUMENT,
        items=windowed,
        truncated=truncated,
        scanned=len(items),
    )
