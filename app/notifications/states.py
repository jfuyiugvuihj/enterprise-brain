"""R299 · 读者生命周期那一层存储：0016 那张表的唯一写口。

这份文件只管一件事：某个收件人对某枚通知做过什么。它不知道告警是什么、挂起是什么、文档是
什么 —— 那些事实活在三本既有账里，由 app/notifications/sources.py 现读。表里也没有任何正文、
部门、密级列，所以这里不可能长出一本和第二账竞争的影子台账（0016 文件头逐条记了这个理由）。

两条腿的选法与 app/storage/pending_approvals.py 同一条：PG 就绪时读写 notification_states，
否则退到进程内账本，开发态与全量回归因此不需要数据库。差别有两条 —— **只要真在跟 PG 说话，
表就必须在**：缺表抛具名 NotificationStateStoreMissing，由出口翻成 503，而不是往内存悄悄降级。
把「表没迁移」洗成「这个人没有已读记录」，正好是本期判据⑥要防的那类假绿。第二条是 R376 添的，
只管写腿：**生产模式下库没就绪，这一格根本不许写**。进程内那本账在客户机上随进程一起消失，
重启之后屏上那句「已读」会回到「未读」，而当初的回执是 200 加 changed: true —— 落不了库是这台
机器的现状，把落不了库说成落了库才是假话。开发与裸机（APP_ENV 不是生产）那条退路一个字没动，
它今天仍是合法后端。
R376 只管了这一格的下半张脸（不许说「写了」），本文件剩下的那条腿由 R388 治（不许说「没读过」）：
同一格世界里读腿从前交回那本内存空账，于是收件箱把每一条通知都判成未读 —— 员工明明读过、明明
划掉过，徽标还是满的。这与「把问不出说成没有」是同句病，只不过反过来说成「全是新的」。今天两张
脸分开：答上了的交 dict（`{}` 说的是「查过，确实没有行」），答不上的交 `None`，由读模型
app/notifications/inbox.py 登记成「这一格不供数」那一格；列表照读，不跟着整页 503。

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

from app.api.v1 import alerts as alerts_api
from app.common.logger import logger
from app.db.connection import open_connection_with_policy, parse_database_settings
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

    R376 起这一枚类型载两张脸，因为客户读到的是同一句话：``_require_table`` 判「表没迁移」，
    ``_require_writable_store`` 判「生产机器上库整个不在」。刻意不另开第二型 —— 出口只接一种
    错那一格（app/api/v1/notifications.py 的两处 except）因此一个字都不必跟着改。

    具名而不是裸 RuntimeError：出口只接这一种错就翻 503。把任何一次异常都洗成「存储不可用」，
    等于替真正的 bug 打掩护 —— pending_approvals 那一族早就吃过这个亏。
    """


def _database_available() -> bool:
    auth_module = sys.modules.get('app.common.auth')
    return bool(auth_module and getattr(auth_module, '_db_ready', False))


def _conn():
    if psycopg is None:  # pragma: no cover - 无驱动就走不到这条腿
        raise RuntimeError('PostgreSQL driver is unavailable')
    # R299 收口由总控落笔（账本钉 test_r238_bare_connect_ratchet 当场拒了这枚新落点）：
    # 新模块不许自带裸 psycopg.connect——全仓只供出 app/db/connection.py 这一枚边界，
    # 其余落点全按遗留记账、不许多长。这里改走既有缝，与 app/rag/pg_store.py::_connect
    # 同一个入口；row_factory 递下去这件事是 R602（事故 #106）才成真的，见那笔的交工纸。
    settings = parse_database_settings(_PG_URL)
    return open_connection_with_policy(settings, row_factory=dict_row)


def _now() -> str:
    return _NOW().isoformat(timespec='seconds')


def _require_table(conn) -> None:
    row = conn.execute('SELECT to_regclass(%s) AS table_name', (f'public.{TABLE}',)).fetchone()
    if not row or row['table_name'] is None:
        raise NotificationStateStoreMissing(
            f'{TABLE} table is required; run migrations first ('
            'migrations/0016_notification_states.sql)'
        )


def _require_writable_store(operation: str) -> None:
    """生产环境 + 库未就绪 ⇒ 这一格生命周期拒写，也不许说写了（R376）。

    判的两件事都是本件既有的读数，一枚都不新造：库在不在取本模块唯一那枚
    ``_database_available()``（``_db_ready`` 的读者数因此一枚没长，test_r246 那本账按 AST 管）；
    是不是生产取 ``alerts_api._is_production_environment()`` —— 与 app/api/v1/dashboard.py（R367）
    借的是同一枚尺，本包 import 那模块已有多处（inbox.py、sources.py 各一枚），零新增定义、
    零新增依赖环。两支同时成立才拒，缺一支就照旧走。

    为什么只管写腿：内存那本账（``_ROWS``）随进程消失。客户点「标记已读」，回执 200 +
    changed: true，进程一重启那条已读就回来了 —— 本单治的就是这两句话对不上。判据是「没落库」
    这件事要么是一个错误，要么是一格显式标注的缺席，不许既 200 又 changed: true。

    抛的是本件既有那一枚具名错：出口 app/api/v1/notifications.py 的两支 except 已经在接它（坐标按树取：
    基点 b498c88 读 :159/:190，R381 并树后的 903765b 读 :169-170/:208），
    翻成 503 ``storage_unavailable`` —— 零新增错误码、零新增 reason 词、出口一字不改。

    调用点排在授权与可寻址性之后（出口 ``_apply`` 先答 401 / 403 / not_addressable），排在
    ``read_state``、``_now()`` 与任何一次 ``_conn`` 之前：先答「你是谁、这一枚你管不管得着」，
    再答「这台机器还记不记得话」，最后才谈写。反过来就把 503 与 401 之差做成一枚探针。

    开发态一字不改（``APP_ENV`` 不是生产即直接 return）：那条内存腿今天仍是合法后端，全量回归
    也靠它跑，把开发支一起打死同样是说假话，只不过反着说。

    读腿 ``recipient_states`` / ``read_state`` 判的是这同一格条件（R388 落的那一刀），但处置
    刻意不一样，而且必须不一样：R366 已经为「生产无库时的收件箱」追认过 200 加逐腿缺席那一格
    （契约 R366 一节），列表那三本账答得出来的照答，把读腿也翻成抛错就是替一格问不出打死整页。
    于是 ``recipient_states`` 交回 ``None`` 这一枚显式的「答不上」，由读模型登记成缺席那一格；
    ``read_state`` 是单枚读，它唯一的调用方 ``apply_state`` 在这一格早就被本闸拒在门外，没有
    照答的页面要保，所以照本闸抛同一枚具名错——零新增错误码，出口 `app/api/v1/notifications.py`
    那两支 except 今天就在接它。
    """
    if _database_available() or not alerts_api._is_production_environment():
        return
    logger.warning(
        f'[R376] 生产环境存储未就绪，生命周期这一格拒写而不是写进内存: operation={operation} '
        'code=storage_unavailable（PG 未起或迁移未跑，写进内存即重启失忆）'
    )
    raise NotificationStateStoreMissing(
        f'{TABLE} cannot be written in production without PostgreSQL ('
        'migrations/0016_notification_states.sql)'
    )


def recipient_states(recipient: str) -> dict[str, str] | None:
    """这个收件人手上的全部生命周期行，notification_id -> 可写状态。

    一次读整份，不在 SQL 里按状态裁：「未读」在这一层根本没有行（0016），所以任何
    'WHERE state = ...' 都数不出未读，只会把结论推到别处去再算一遍。页与计数由读模型裁。

    R388 起这一枚函数交三张脸，一枚都不许多并：
      ``dict`` —— 这本账答上了，逐条给出；空 dict 说的是「查过了，这个人确实没有行」。
      ``None`` —— 这本账**答不上来**：生产机器上 PG 没起（或 0016 没跑）。此刻关于「谁读过什么」
      这台机器没有一句真话可说，而 `{}` 与 `None` 是两句话：并成一枚，收件箱就把每一条都判成
      未读（`inbox.py` 拿 `{}` 逐条比），员工读过的痕迹在屏上一格不剩 —— 那正是本单治的病。
    判的仍是 ``_require_writable_store`` 那两支既有读数（`_database_available()` 与借来的那把
    生产尺 `alerts_api._is_production_environment()`），本文件一枚新尺、一枚新码都没造。
    """
    person = str(recipient or '')
    if not person:
        return {}

    if not _database_available():
        if alerts_api._is_production_environment():
            # 生产而库不在位：那本内存账在客户机上恒为空，交回去就是替这台机器宣布「这个人
            # 什么都没读过」。列表那一格照答，缺席由读模型登记，这里不抛错也不装成空账。
            logger.warning(
                '[R388] 生产环境存储未就绪，生命周期这一格答不上而不是交回内存空账: '
                'code=storage_unavailable（PG 未起或迁移未跑，空账会被读成「全是新的」）'
            )
            return None
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
    """单枚通知在这个收件人手上的状态；没有行就是 None（unread）。

    这一枚 `None` 说的是「有账，而这一枚没有行」，即未读，所以它**不能**兼作「问不出」——
    兼了就是把问不出洗成一次未读，与整页 503 之间没有第三种说法可挑。生产而库不在位那一格
    R388 起抛本件既有那枚具名错（与 ``_require_writable_store`` 同一型、同一族出口，零新增码）；
    唯一的调用方 `apply_state` 在这一格本来就被那道闸拒在门外，所以这一支今天不改任何回执形状。
    """
    if not _database_available():
        if alerts_api._is_production_environment():
            raise NotificationStateStoreMissing(
                f'{TABLE} cannot be read in production without PostgreSQL ('
                'migrations/0016_notification_states.sql)'
            )
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

    还有一句 R376：这一格落不了库就一个字都不写，也不回 changed。生产而库未就绪 ⇒
    _require_writable_store 抛具名错，由出口答它已有的那一码 503 storage_unavailable；
    于是 'changed': True 这句话从今天起只在**真写过了某本账**的世界里出现。
    """
    person = str(recipient or '')
    identifier = str(notification_id or '')
    if not person or not identifier:
        raise ValueError('recipient and notification_id are both required')

    # 排在任何一次读写之前：内存腿与 PG 腿都不许被这次拒答碰过一字节（连 _now 都不读）。
    _require_writable_store('apply_state')
    current = read_state(person, identifier)
    final = advance_state(current, requested)
    changed = final != current
    if not changed:
        return {'state': final, 'changed': False, 'notification_id': identifier}

    moment = _now()
    if not _database_available():
        # 走到这里只剩两种世界：库就绪，或者不是生产 —— 上面那道闸已经把「生产 + 无库」
        # 那一格拒在门外，所以这一支内存腿今天只可能来自开发与裸机。
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
