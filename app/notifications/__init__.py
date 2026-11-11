"""R299 · 通知中心：一枚收件箱，三本既有账，零本新账。

跟进单 §102 第三节给本期的范围是「审批待办 / 告警 / 文档索引完成」三类，判据②同时划了两条
红线：不许自造事件源，不许开第二本待办账。这个包因此按「投影 + 覆盖层」两件事组织，没有第三
种状态：

- app/notifications/sources.py —— 投影。每一枚候选通知都由那三本账**现有的读路径**现答
  （pending_approvals.open_items / alerts.list_alerts / chat.list_document_catalog），本包不
  查询、不缓存、也不复刻任何一本账的内容。
- app/notifications/states.py —— 覆盖层。migrations/0016 那张表只存「这个人对这条记录读过还
  是划掉了」，正文、部门、密级一格都没有。业务状态变了（告警关闭、挂起决定、文档下架），收件
  箱下一读就跟着变，因为这里从来没有抄过一份。
- app/notifications/inbox.py —— 读模型与可寻址性判定。分页、两条计数口径（本页长度与全集总数
  分开命名）、以及「谁能对哪一枚动手」都只在这一处；权限那一问全部转交给那三本账自己回答。
- app/notifications/contracts.py —— 稳定 ID 的拼法与生命周期词表，advance_state 是唯一的推进
  规则。

出口在 app/api/v1/notifications.py，契约见 docs/api/contract-v1.md 的 R299 一节。
"""
from app.notifications.contracts import (
    NOTIFICATION_SOURCES,
    NOTIFICATION_STATES,
    STATE_DISMISSED,
    STATE_READ,
    STATE_UNREAD,
    parse_notification_id,
)

__all__ = [
    'NOTIFICATION_SOURCES',
    'NOTIFICATION_STATES',
    'STATE_DISMISSED',
    'STATE_READ',
    'STATE_UNREAD',
    'parse_notification_id',
]
