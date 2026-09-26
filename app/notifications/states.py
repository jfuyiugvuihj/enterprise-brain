"""R299 · 读者生命周期那一层存储：0016 那张表的唯一写口。

这份文件只管一件事：某个收件人对某枚通知做过什么。它不知道告警是什么、挂起是什么、文档是
什么 —— 那些事实活在三本既有账里，由 app/notifications/sources.py 现读。表里也没有任何正文、
部门、密级列，所以这里不可能长出一本和第二账竞争的影子台账（0016 文件头逐条记了这个理由）。

两条腿的选法与 app/storage/pending_approvals.py 同一条：PG 就绪时读写 notification_states，
否则退到进程内账本，开发态与全量回归因此不需要数据库。差别只有一个 —— **只要真在跟 PG 说话，
表就必须在**：缺表抛具名 NotificationStateStoreMissing，由出口翻成 503，而不是往内存悄悄降级。
把「表没迁移」洗成「这个人没有已读记录」，正好是本期判据⑥要防的那类假绿。

时间戳只有一枚时钟（_now），两条腿共用，拼写因此逐字相同；这是 0014 为处置列立过的口径，
不在这里再发明一次。推进规则也不在这里：唯一一处是 contracts.advance_state，本文件两条腿都
调它，所以「重复 dismiss 不改变结论」这句话在两条腿上是同一个函数在保。
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import datetime, timedelta, timezone

try:  # pragma: no cover - 驱动缺失时下面所有 PG 分支都不会被走到
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None

from app.notifications.contracts import advance_state

TABLE = 'notification_states'

_PG_URL = os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/enterprise_brain')

#: 内存腿：(recipient, notification_id) -> {state, recorded_at, updated_at}。键序与 0016 上
#: 那枚 reader_key 逐字对应，两条腿因此是同一个唯一性约束，不是两套形状。
_ROWS: dict[tuple[str, str], dict[str, str]] = {}
_LOCK = threading.Lock()

#: 服务端那一枚时钟：中国无夏令时，固定偏移与 app/common/auth.py、app/api/v1/alerts.py
#: 用的是同一族写法；两条腿共它，所以一条记录被读两次不会换一种拼写。
_NOW = lambda: datetime.now(timezone(timedelta(hours=8)))  # noqa: E731 - 只有一处语义，测试按整体替换


class NotificationStateStoreMissing(RuntimeError):
    """0016 没跑：这张表不在，于是「谁读过什么」没有任何真话可说。

    具名而不是裸 RuntimeError：出口只接这一种错就翻 503。把任何一次异常都洗成「存储不可用」，
    等于替真正的 bug 打掩护 —— pending_approvals 那一族早就吃过这个亏。
    """


def _database_available() -> bool:
    auth_module = sys.modules.get('app.common.auth')
    return bool(auth_module and getattr(auth_module, '_db_ready', False))


def _conn():
    if psycopg is None:  # pragma: no cover - 无驱动就走不到这条腿
        raise RuntimeError('PostgreSQL driver is unavailable')
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _now() -> str:
    return _NOW().isoformat(timespec='seconds')


def _require_table(conn) -> None:
    row = conn.execute('SELECT to_regclass(%s) AS table_name', (f'public.{TABLE}',)).fetchone()
    if not row or row['table_name'] is None:
        raise NotificationStateStoreMissing(
            f'{TABLE} table is required; run migrations first ('
            'migrations/0016_notification_states.sql)'
        )


def recipient_states(recipient: str) -> dict[str, str]:
    """这个收件人手上的全部生命周期行，notification_id -> 可写状态。

    一次读整份，不在 SQL 里按状态裁：「未读」在这一层根本没有行（0016），所以任何
    'WHERE state = ...' 都数不出未读，只会把结论推到别处去再算一遍。页与计数由读模型裁。
    """
    person = str(recipient or '')
    if not person:
        return {}

    if not _database_available():
        with _LOCK:
            return {
                key[1]: dict(value)['state']
                for key, value in _ROWS.items()
                if key[0] == person
            }

    with _conn() as conn:
        _require_table(conn)
        rows = conn.execute(
            f'SELECT notification_id, state FROM {TABLE} WHERE recipient = %s', (person,)
        ).fetchall()
    return {str(row['notification_id']): str(row['state']) for row in rows}


def read_state(recipient: str, notification_id: str) -> str | None:
    """单枚通知在这个收件人手上的状态；没有行就是 None（unread）。"""
    if not _database_available():
        with _LOCK:
            stored = _ROWS.get((str(recipient), str(notification_id)))
        return str(stored['state']) if stored else None

    with _conn() as conn:
        _require_table(conn)
        row = conn.execute(
            f'SELECT state FROM {TABLE} WHERE recipient = %s AND notification_id = %s '
            'FOR UPDATE',
            (str(recipient), str(notification_id)),
        ).fetchone()
    return str(row['state']) if row else None


def apply_state(recipient: str, notification_id: str, requested: str) -> dict[str, object]:
    """把一次动作落到生命周期上，返回写后的结论。唯一写口，幂等由这一处保证。

    返回值里 'changed' 说的是「这一次有没有改动那本账」：重复点同一枚动作恒为 False，而
    'state' 恒等于最终结论。两者分开是判据④要的形状 —— 客户端要能分辨「我刚才划掉了它」
    与「它早就被划掉了」，而这两个答案的 'state' 是同一个词。
    """
    person = str(recipient or '')
    identifier = str(notification_id or '')
    if not person or not identifier:
        raise ValueError('recipient and notification_id are both required')

    current = read_state(person, identifier)
    final = advance_state(current, requested)
    changed = final != current
    if not changed:
        return {'state': final, 'changed': False, 'notification_id': identifier}

    moment = _now()
    if not _database_available():
        with _LOCK:
            existing = _ROWS.get((person, identifier))
            recorded = existing['recorded_at'] if existing else moment
            _ROWS[(person, identifier)] = {
                'state': final,
                'recorded_at': recorded,
                'updated_at': moment,
            }
        return {'state': final, 'changed': True, 'notification_id': identifier}

    # 上面那枚行锁（read_state 带 FOR UPDATE）覆盖的是最常见的重复点击：同一个人连点两次
    # dismiss，第二次读到的是第一枚已经写下的行。一枚从没出现过的键上若真有两件不同的动作
    # 并发抢写，锁不到不存在的行 —— 这里不假装处理过那种情形：0016 上那枚 reader_key 保证
    # 结果恰好是一行合法记录，而不是两行互相看不见，而抢的两个结论都在封闭词表里。
    with _conn() as conn:
        _require_table(conn)
        conn.execute(
            f'INSERT INTO {TABLE} '
                '(notification_id, recipient, state, recorded_at, updated_at) '
                'VALUES (%s, %s, %s, %s, %s) '
                'ON CONFLICT (notification_id, recipient) DO UPDATE SET '
                'state = EXCLUDED.state, updated_at = EXCLUDED.updated_at',
            (identifier, person, final, moment, moment),
        )
        conn.commit()
    return {'state': final, 'changed': True, 'notification_id': identifier}


def reset_for_testing() -> None:
    """清空内存腿。只有测试用，与 app/storage/pending_approvals 同一族缝。"""
    with _LOCK:
        _ROWS.clear()
