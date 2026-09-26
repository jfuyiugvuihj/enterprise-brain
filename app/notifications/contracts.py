"""R299 · 通知中心的资源契约：稳定 ID、生命周期词表与唯一一处推进规则。

跟进单 §102 第三节给本期划的线是「只接审批待办 / 告警 / 文档索引完成三类，且必须复用既有
账本」。所以本模块不描述任何一种业务状态：一条告警开没开、一轮挂起还在不在、一篇文档进没进
索引，全部由 app.notifications.sources 去问那三本账自己。这一份文件只回答两个问题：一枚通知
在这台系统里叫什么名字（稳定 ID），以及读它的人对它做过什么（生命周期）。

生命周期只有两格可写，unread 不在其中 —— 它是「这一格还没有行」，不是第三种写入。理由与
migrations/0016 文件头同一条：把 unread 铺成行，就得在每个事件源上多挂一个写点，那正是本期
禁止的第二本账。唯一一处状态推进规则是 advance_state，读写两条腿都从这里过，所以「重复 dismiss
不改变结论」这句话在机器上只有一个落点可以检查。

ID 的拼法（<source_type>:<source_record_id>）刻意由源那一侧的键派生，而不是由新表生成一枚自增
号：跨进程、跨重启、跨「这条通知还没被人读过」都必须是同一个字符串，否则读者状态无处安放。三枚
源的键各自是 pending_approvals.session_id、alerts.id 与 document_versions 的 (filename, version)
—— 都是账本里已经存在的稳定键，这里不新造第四枚。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 本期允许的三枚源，一条都不许多。第四枚源就意味着第四本账，而跟进单点名禁止平行实现。
SOURCE_APPROVAL = 'approval'
SOURCE_ALERT = 'alert'
SOURCE_DOCUMENT = 'document'
NOTIFICATION_SOURCES: tuple[str, ...] = (SOURCE_APPROVAL, SOURCE_ALERT, SOURCE_DOCUMENT)

#: 读者能做的两件事。第三格 unread 是这两格的补集，不是可写的状态，见文件头。
STATE_READ = 'read'
STATE_DISMISSED = 'dismissed'
NOTIFICATION_STATES: tuple[str, ...] = (STATE_READ, STATE_DISMISSED)

#: 读端点交回给客户端的那一格取值：三枚里恒取其一，unread 由「没有行」算出来。
STATE_UNREAD = 'unread'

#: 单向格：dismissed 是读者这一侧的终态，读过一次的可以再划掉，划掉的不许被「标为已读」
#: 悄悄放回收件箱 —— 否则一次翻页就能替别人重开他已经拒绝看的条目。
_STATE_ORDER: dict[str, int] = {STATE_READ: 1, STATE_DISMISSED: 2}

ID_SEPARATOR = ':'

#: 与 0006 上 length(filename) <= 512 那一族同源的长度护栏：ID 里最长的载荷就是文件名，
#: 上界写在这里，SQL 那一侧再硬一次，两侧都不靠调用方自觉。
MAX_NOTIFICATION_ID_CHARS = 640


class NotificationIdError(ValueError):
    """一枚认不出源、或拼不出稳定 ID 的标识。拒它的理由必须是形状，不能是「存不存在」。"""


@dataclass(frozen=True)
class Notification:
    """一枚候选通知：源那一侧的事实 + 一句人话。没有任何一格是这里新测出来的。

    reference 只装源自己已经交回过的标识（session_id / alert_id / filename+version），前端
    拿它跳转，服务端从不据此再判一次权限：权限的答案永远来自那本账的读路径。
    """

    id: str
    source_type: str
    source_id: str
    title: str
    detail: str
    created_at: str = ''
    reference: dict[str, Any] = field(default_factory=dict)


def make_notification_id(source_type: str, source_id: Any) -> str:
    """把一枚源记录拼成稳定 ID。源类型不认识、源键为空，都当场拒，不退回一个猜。"""
    if source_type not in NOTIFICATION_SOURCES:
        raise NotificationIdError(f'unknown notification source: {source_type}')
    spelled = str(source_id if source_id is not None else '').strip()
    if not spelled:
        raise NotificationIdError('empty notification source id')
    return f'{source_type}{ID_SEPARATOR}{spelled}'


def parse_notification_id(raw: Any) -> tuple[str, str]:
    """拆回 (source_type, source_id)。形状不合就拒，绝不按前缀猜一枚新源。"""
    text = str(raw if raw is not None else '').strip()
    if not text:
        raise NotificationIdError('empty notification id')
    if len(text) > MAX_NOTIFICATION_ID_CHARS:
        raise NotificationIdError('notification id is too long')
    source_type, separator, source_id = text.partition(ID_SEPARATOR)
    if not separator or source_type not in NOTIFICATION_SOURCES or not source_id.strip():
        raise NotificationIdError('malformed notification id')
    return source_type, source_id.strip()


def advance_state(current: str | None, requested: str) -> str:
    """唯一一处生命周期推进：读可以升级成划掉，划掉不回退；重复请求得到同一个结论。

    current 为 None 就是「还没有行」（unread）。三枚入参里只有 requested 需要是可写状态，
    其余一律 NotificationIdError：不许有人把 unread 当成一次写提交进来，那等于让收件箱里凭空
    多出一格永远数不准的状态。
    """
    if requested not in NOTIFICATION_STATES:
        raise NotificationIdError(f'unwritable notification state: {requested}')
    if current is None or current == '':
        return requested
    if current not in _STATE_ORDER:
        # 表里躺着一枚本文件不认识的词：往上是修不好也判不了的，宁可当场报错，也不拿
        # requested 盖掉它 —— 那会把一次数据损坏洗成一次正常操作。
        raise NotificationIdError(f'stored notification state is not understood: {current}')
    if _STATE_ORDER[current] >= _STATE_ORDER[requested]:
        return current
    return requested
