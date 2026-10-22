"""R610 · 收割 R605 那 6 条独有牙：递给驱动的 kwargs 每一格都要有人守。

账（跟进单 §161.1，10-03 17:3x 现取订正）：失联执行层 R605 留在检疫区的那枚新钉有 11 格测试，逐名对账（号本身按事故 #62 作废不复用），
随 8d8b85f 并树的只有 4 枚，落在
tests/test_r602_notification_pg_leg.py；剩下 6 枚独有、今天没人守。本件把这 6 枚钉在今天
这枚 driver_kwargs 签名上，不新增任何行为。

六条逐一对回 §161.1 那句清单（test 名字里的 c1…c6 就是它的顺序）：
  c1 写腿（apply_state 那条 INSERT）的 driver kwargs 也到驱动，不许只验读腿；
  c2 四枚 env 一枚都不设时，转发格逐字节等于调用方给的那几枚，一枚不多、不夹带超时；
  c3 DSN 自带的 connect_timeout 压过 env，调用方多给 kwargs 时这一条仍然成立；
  c4 六枚测试缝（policy / environ / connect / transient / sleep / clock）一枚都不许漏进
     递给驱动的那份字典；
  c5 connect_with_policy 与 open_connection_with_policy 两枚边界都收调用方 kwargs，且后者
     真把它转给前者（只查签名接不住「签名有、body 里丢了」那种写法）；
  c6 app/notifications/states.py 的 _conn 仍然向边界要 row_factory=dict_row，并且不自己裸连。

纪律与 r602 同一条：🔴 本文件一枚 _conn 桩都不许有。许碰的缝只有两处 —— 驱动那一层的
psycopg.connect，或 connect_with_policy 自己那枚 connect= 注入缝。被验的转发链
「states._conn → open_connection_with_policy → connect_with_policy → 驱动」一次都不许绕过，
所以这里断言的是**递给真驱动的那份字典**，不是「假连接到本就不转发参数」那种凑绿。

反证（本单一手做过，读数在交工纸里）：把 connect_with_policy 签名末尾那枚 **driver_kwargs
摘掉，c1…c5 五格当场红；把 states.py 里那枚 row_factory=dict_row 摘掉，c6 当场红。

零真库、零服务、零模型、零写入：所有「连接」都停在记录器上，一次 socket 都不发。
本件与 r602 同族，需要 psycopg 在场（那枚件早已在模块顶层 import 它，本机 .venv 实测 3.3.5）；
拿不到驱动的机器上本件在收集期就红，不拿 skip 兜路。
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.db import connection
from app.notifications import states as state_store

REPO_ROOT = Path(__file__).resolve().parents[1]
STATES_PY = REPO_ROOT / 'app' / 'notifications' / 'states.py'

#: 一枚永不落地的 DSN（tests/conftest.py 同一口径，端口是保留端口 1）：本件的「连」全停在记录器上。
URL = 'postgresql://r610_pytest@127.0.0.1:1/r610_pytest'

#: 同一枚 DSN 但库里自己写了超时：c3 量的就是「库上的读数压过 env」。
URL_WITH_DSN_TIMEOUT = URL + '?connect_timeout=1'

TABLE = 'notification_states'

#: 四枚策略开关一枚都不许带残留进本文件：策略读数必须是「关」，转发格才只由调用方决定。
POLICY_ENVS = (
    connection.ENV_CONNECT_TIMEOUT,
    connection.ENV_CONNECT_KEEPALIVES,
    connection.ENV_CONNECT_ATTEMPTS,
    connection.ENV_CONNECT_BUDGET,
)

#: 六枚测试缝的名字（c4 的靶子）：它们只许被 connect_with_policy 自己消费，一枚都不许出门。
SEAM_NAMES = ('policy', 'environ', 'connect', 'transient', 'sleep', 'clock')


class _Recorder:
    """假 psycopg.connect：只记账，绝不握手；需要腿上有连接对象时逐次交回同一枚替身。"""

    def __init__(self, connection_obj=None) -> None:
        self.calls: list[tuple] = []
        self._connection = connection_obj

    def connect(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._connection is not None:
            return self._connection
        return 'conn<%d>' % len(self.calls)


class _Result:
    def __init__(self, store, sql: str) -> None:
        self._store = store
        self._sql = ' '.join(sql.split())

    def fetchone(self):
        if 'to_regclass' in self._sql:
            return {'table_name': self._store.table}
        for row in self._store.rows:
            return dict(row)
        return None

    def fetchall(self):
        if 'to_regclass' in self._sql:
            return [{'table_name': self._store.table}]
        return [dict(row) for row in self._store.rows]


class _FakeStore:
    """只装 states.py 那几条语句用到的形状：建表探测 / 单枚读 / 整份读 / 写。"""

    def __init__(self, table: str = TABLE, rows=()) -> None:
        self.table = table
        self.rows = list(rows)
        self.statements: list[str] = []
        self.params: list = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.statements.append(' '.join(sql.split()))
        self.params.append(params)
        return _Result(self, sql)

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _policy_env_off(monkeypatch) -> None:
    """把四枚策略 env 逐枚擦干净：这一节的默认就是「关着」，判据①那条账按默认读。"""
    for name in POLICY_ENVS:
        monkeypatch.delenv(name, raising=False)


def _database_in_place(monkeypatch) -> None:
    """只把「库在不在」那一格拧成真；_conn 一个字都不桩 —— 桩 _conn 就是本单的病。"""
    monkeypatch.setattr(state_store, '_database_available', lambda: True)


# ------------------------------------------------------------------ c1：写腿
def test_c1_write_leg_forwards_the_caller_kwargs_to_the_driver(monkeypatch):
    """§161.1·c1 写腿的 driver kwargs 也到驱动（在册件只验过读腿那一格）。

    真调 states.apply_state：读那一帧（read_state 的 FOR UPDATE）与写那一帧各开一条连接，
    两帧都必须带着同一枚行工厂出门。摘掉 connect_with_policy 签名末尾那枚 **driver_kwargs，
    这一格当场 TypeError —— 也就是 500 那一帧的写腿版本。
    """
    store = _FakeStore(rows=[])
    driver = _Recorder(store)
    _policy_env_off(monkeypatch)
    monkeypatch.setattr(psycopg, 'connect', driver.connect)
    _database_in_place(monkeypatch)

    outcome = state_store.apply_state('r610', 'alert:9', 'read')

    assert outcome == {'state': 'read', 'changed': True, 'notification_id': 'alert:9'}, outcome
    assert store.commits == 1, store.commits
    inserts = [s for s in store.statements if s.startswith('INSERT INTO notification_states')]
    assert len(inserts) == 1, store.statements
    assert 'ON CONFLICT (notification_id, recipient) DO UPDATE' in inserts[0], inserts[0]
    assert store.params[-1][0] == 'alert:9', store.params
    assert len(driver.calls) == 2, driver.calls
    assert [call[1] for call in driver.calls] == [{'row_factory': dict_row}] * 2, driver.calls
    for args, kwargs in driver.calls:
        assert args == (state_store._PG_URL,), args
        assert kwargs['row_factory'] is dict_row, '写腿递给驱动的行工厂不是 dict_row 本尊'


# ------------------------------------------------------------------ c2：env 全不设
def test_c2_with_no_env_at_all_the_driver_gets_exactly_what_the_caller_gave(monkeypatch):
    """§161.1·c2 四枚 env 一枚都不设 ⇒ 转发给驱动的 kwargs 逐字节等于调用方给的那几枚。

    这一格钉的是「不多不少、不夹带超时」：策略关着时 connect_kwargs 交回空 dict，合并出来
    因此只有调用方那两枚。顺手钉住转发格必须是新建的字典 —— 把调用方那份直接递出去，
    等于让被调方改写调用方的字典。
    """
    driver = _Recorder()
    given = {'row_factory': dict_row, 'application_name': 'r610-pin'}
    _policy_env_off(monkeypatch)
    assert all(name not in os.environ for name in POLICY_ENVS), '这一格要的是真·一个 env 都不设'

    result = connection.connect_with_policy(URL, connect=driver.connect, **given)

    assert result == 'conn<1>', result
    sent = driver.calls[0][1]
    assert driver.calls == [((URL,), given)], driver.calls
    assert sent == {'row_factory': dict_row, 'application_name': 'r610-pin'}, sent
    assert sent is not given, '转发格必须是新表，不许把调用方的字典直接递出去'
    assert 'connect_timeout' not in sent, sent
    assert 'keepalives' not in sent, sent


# ------------------------------------------------------------------ c3：DSN 压过 env
def test_c3_a_dsn_carried_timeout_beats_the_env_with_forwarded_kwargs(monkeypatch):
    """§161.1·c3 DSN 自带的超时压过 env：两边都给时，驱动收到的是 DSN 那份。

    式子与 app/common/auth.py 同源（connect_kwargs 见 DSN 里有 connect_timeout 就闭嘴）。
    正控同在本格：同一枚 env 落在不自带超时的 DSN 上时策略是会注入的 —— 少了这半格，
    「策略闭嘴」可能被读成「策略整个坏了」。
    """
    _policy_env_off(monkeypatch)
    monkeypatch.setenv(connection.ENV_CONNECT_TIMEOUT, '5')

    driver = _Recorder()
    connection.connect_with_policy(
        URL_WITH_DSN_TIMEOUT, connect=driver.connect, row_factory=dict_row
    )

    assert len(driver.calls) == 1, driver.calls
    conninfo, sent = driver.calls[0]
    assert conninfo == (URL_WITH_DSN_TIMEOUT,), conninfo
    assert 'connect_timeout=1' in conninfo[0], conninfo
    assert sent == {'row_factory': dict_row}, 'DSN 自带超时时策略不许再往驱动那份里塞一枚 connect_timeout'

    control = _Recorder()
    connection.connect_with_policy(URL, connect=control.connect, row_factory=dict_row)
    assert control.calls == [
        ((URL,), {'row_factory': dict_row, 'connect_timeout': 5})
    ], control.calls


# ------------------------------------------------------------------ c4：测试缝不外泄
def test_c4_the_six_injection_seams_never_leak_into_the_forwarded_kwargs(monkeypatch):
    """§161.1·c4 六枚测试缝不许漏进转发 kwargs：它们是缝，不是驱动参数。

    六枚逐枚都喂上真值（policy / environ / connect / transient / sleep / clock），再让调用方
    多给两枚驱动参数。断言的是递给驱动那份字典的**全等**：任何一枚缝名混进去，或者合并时
    把 kwargs 之外的东西并进来，这一格当场红。
    """
    _policy_env_off(monkeypatch)
    driver = _Recorder()

    connection.connect_with_policy(
        URL,
        policy=connection.ConnectPolicy(),
        environ={},
        connect=driver.connect,
        transient=(),
        sleep=lambda seconds: None,
        clock=lambda: 0.0,
        row_factory=dict_row,
        application_name='r610-pin',
    )

    assert len(driver.calls) == 1, driver.calls
    sent = driver.calls[0][1]
    assert sent == {'row_factory': dict_row, 'application_name': 'r610-pin'}, sent
    assert [name for name in SEAM_NAMES if name in sent] == [], sent

    params = inspect.signature(connection.connect_with_policy).parameters
    for name in SEAM_NAMES:
        assert name in params, (name, sorted(params))
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, (name, params[name].kind)


# ------------------------------------------------------------------ c5：两枚边界签名
def test_c5_both_boundary_signatures_take_and_forward_caller_kwargs(monkeypatch):
    """§161.1·c5 两枚边界都收调用方 kwargs，且 open_connection_with_policy 真把它转下去。

    修之前那枚签名（全具名、无 **kwargs）就是这枚 500 的落点，所以结构必须守一遍；
    但只查签名接不住「签名里留着 **kwargs、body 却不转」那种写法，因此同一格里再走一遍
    函数：从 open_connection_with_policy 进，驱动必须收到调用方那枚 row_factory。
    """
    _policy_env_off(monkeypatch)

    for name in ('connect_with_policy', 'open_connection_with_policy'):
        function = getattr(connection, name)
        kinds = [p.kind for p in inspect.signature(function).parameters.values()]
        assert inspect.Parameter.VAR_KEYWORD in kinds, (name, inspect.signature(function))

    driver = _Recorder()
    settings = connection.parse_database_settings(URL)
    returned = connection.open_connection_with_policy(
        settings, connect=driver.connect, row_factory=dict_row
    )

    assert returned == 'conn<1>', returned
    assert driver.calls == [((URL,), {'row_factory': dict_row})], driver.calls


# ------------------------------------------------------------------ c6：states 探针
def test_c6_states_probe_still_asks_the_boundary_for_dict_rows():
    """§161.1·c6 states 探针仍然向边界要 dict_rows：行工厂这条口径不许被静默改掉。

    按 AST 判（与 test_r238_bare_connect_ratchet 同族做法，不靠行号）：_conn 里对
    open_connection_with_policy 的调用必须恰好一枚，关键字必须只有 row_factory 那一枚，
    其值必须仍写作 dict_row，并且这一层不许自己裸连。
    """
    tree = ast.parse(STATES_PY.read_text(encoding='utf-8'))
    probe = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == '_conn'
    )
    calls = [
        node for node in ast.walk(probe)
        if isinstance(node, ast.Call)
        and (getattr(node.func, 'id', None) or getattr(node.func, 'attr', None))
        == 'open_connection_with_policy'
    ]

    assert len(calls) == 1, ast.dump(probe)
    keywords = {kw.arg for kw in calls[0].keywords if kw.arg}
    assert keywords == {'row_factory'}, calls[0].keywords
    values = {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords if kw.arg}
    assert values == {'row_factory': 'dict_row'}, values
    assert 'psycopg.connect' not in ast.unparse(probe), '通知中心那一层又自己裸连了'
    assert state_store.dict_row is dict_row, 'states 顶部那枚 dict_row 绑定被换掉了'
