"""R199 · 匿名探测必须在审计台账里留一笔（``app/main.py`` 的 AuthMiddleware）。

病灶（R194 取证结论，本件用真实 ASGI 栈复述一遍）：``app/main.py:96`` 的 AuthMiddleware 在
**进路由之前**就回 401（``:124`` 无凭证或验不过 / ``:129`` 有凭证但查无此人），所以 R179 与
R194 补在路由层的落账点对所有未登录探测一个都不响 —— 客户的安全台账看不见有人在扫自己。
第 1 组用例钉的就是这件事：同一枚队列出口，匿名走真栈 ⇒ 台账零笔；换上凭据再走同一枚真栈
⇒ 台账一笔。差别只在中间件那一层，不在记账点坏没坏。

本单加的是**账**，不是行为：401 的状态码、正文、响应头逐字不动（第 5 组用例拿改前实测字节做
基线 —— 那组字节是在 4dcbd30 上用真栈打一发行请求取来的，不是推出来的）。

口径：

- 一笔账 = R179 那一个出口 ``app.common.audit.record_audit``，同一组键（用例拿一次直调
  record_audit 的键集合与它互判），不新造 logger、不新造第二张事件表；
- 主体取不到就走它自己的退化投影 ``anonymous`` / ``unknown``（``app/common/audit.py:541-542``），
  码沿用出口自己那句 detail ``authentication_required``。那个「token 有效但查无此人」的名字
  一个字都不进台账：验不出主体的名字写进账本，就是 R78 那一类没有凭据支撑的断言。
- 刷账面（判据④）：来源取 socket 对端地址，**不**取 X-Forwarded-For —— deploy/nginx.conf:58
  用的是 ``$proxy_add_x_forwarded_for``，客户端可以自己塞第一跳，拿可伪造的头当去重键等于把
  闸门交给攻击者。同一来源同一出口在窗口内第一笔必记，其后按 2 的幂补记，每一行都带窗口内
  累计笔数 ⇒ 折叠可见、一笔不静默丢。为什么非折叠不可：中间件是全站的，而每一笔账都是一次带
  fsync 的整档重写（``app/storage/persistence.py:247``），一万个 401 就是一万次磁盘同步。
- 403 ``account_unavailable``（``app/main.py:133``）本单**不碰**：它有主体，不是匿名探测，
  判据②管不着它。它的响应字节由本件钉住不变；「要不要给它也留一笔」留给总控另立单号。

全程离线：真 ASGI 栈 + 内存台账桩 + tests/test_reliable_queue.py 的 FakeRedis，零起服务、
零真机 redis、零模型、零库。
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

#: 被探测的真实出口（R194 那枚路由层落账点就在这条腿上）。
QUEUE_PATH = "/api/v1/queue/status"
#: 别人排队任务的载荷标记：它进台账就是泄漏，进 resource 说明路由真的被执行过。
TASK_MARKER = "R199-TASK-PAYLOAD 这段载荷只属于排在队列里的任务"

#: ---- 改前（4dcbd30）真栈实测的线形，逐字节钉住，判据⑤ ----
BASELINE_401_STATUS = 401
BASELINE_401_HEADERS = [("content-length", "36"), ("content-type", "application/json")]
BASELINE_401_BODY = b'{"detail":"authentication_required"}'
BASELINE_403_STATUS = 403
BASELINE_403_HEADERS = [("content-length", "32"), ("content-type", "application/json")]
BASELINE_403_BODY = b'{"detail":"account_unavailable"}'
BASELINE_HEALTH_BODY = b'{"status":"ok"}'

#: 匿名行的动作名与稳定码（reason 必须就是出口那句 detail，不新造）。
ANON_ACTION = "auth:unauthenticated"
ANON_REASON = "authentication_required"

ACCOUNTS = {
    "root": {"id": "root", "username": "root", "role": "admin", "department": "finance"},
    "keeper": {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"},
    "xdept": {"id": "xdept", "username": "xdept", "role": "manager", "department": "hr"},
}
DISABLED_GHOST = {
    "id": "ghost",
    "username": "ghost",
    "role": "staff",
    "department": "finance",
    "status": "disabled",
}


# ---------------------------------------------------------------- 真 ASGI 栈


async def _one(app, spec):
    path, headers, host, port, method, query = spec
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "root_path": "",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": (host, port),
        "server": ("testserver", 80),
    }
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    wire = [(key.decode(), value.decode()) for key, value in start["headers"]]
    return start["status"], wire, body


def _drive(app, specs):
    """一个事件循环里连打若干发 —— 刷账面用例要真的打出去，不能靠推演。"""

    async def main():
        return [await _one(app, spec) for spec in specs]

    return asyncio.run(main())


def _spec(path, headers=(), host="10.9.8.7", port=54321, method="GET", query=b""):
    return (path, list(headers), host, port, method, query)


def _call(app, path, headers=(), host="10.9.8.7", **kwargs):
    return _drive(app, [_spec(path, headers, host, **kwargs)])[0]


def _calls(app, path, times, headers=(), host="10.9.8.7", **kwargs):
    return _drive(app, [_spec(path, headers, host, **kwargs) for _ in range(times)])


class _MemoryJournal:
    """``app.storage.persistence`` 适配器的最小形状：只认 upsert/list，外加数写入次数。

    数写入次数是给判据④用的：被折叠掉的探测必须**一次磁盘写都不发生**，否则「限流」只是
    少写几行账，DoS 还在。
    """

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict]] = {}
        self.upserts = 0

    def upsert(self, collection, record_id, record):
        self.upserts += 1
        self.rows.setdefault(str(collection), {})[str(record_id)] = dict(record)
        return record

    def list(self, collection):
        return [dict(row) for row in self.rows.get(str(collection), {}).values()]


@pytest.fixture()
def journal():
    """把台账接到内存桩上：与别的用例的行隔离，并且每枚用例从空账开始。"""
    from app.common.audit import configure_audit_storage, reset_audit_storage

    store = _MemoryJournal()
    configure_audit_storage(persistence=store)
    try:
        yield store
    finally:
        reset_audit_storage()


@pytest.fixture(autouse=True)
def probe_windows():
    """清掉刷账面窗口，用例之间互不遮蔽。"""
    import app.main as main

    main.clear_anonymous_probe_windows()
    yield
    main.clear_anonymous_probe_windows()


@pytest.fixture()
def accounts(monkeypatch):
    """给中间件一张本件控制的内存用户表（中间件在调用时才 import，这颗钉子打得动）。"""
    from app.common import auth

    table = dict(ACCOUNTS)
    monkeypatch.setattr(auth, "get_user", lambda username: table.get(username))
    return table


@pytest.fixture()
def app():
    from app.main import app

    return app


def _bearer(username: str) -> list[tuple[str, str]]:
    from app.common.auth import create_token

    return [("Authorization", "Bearer " + create_token(username))]


def _lines(action: str = ANON_ACTION) -> list[dict]:
    from app.common.audit import get_audit_events

    return get_audit_events(action=action)


def _blob(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# =========================================== 第 1 组：判据① 取证（改前改后都必须绿）


def test_the_gate_answers_before_the_route_so_the_route_ledger_point_never_runs(
    app, accounts, journal, monkeypatch
):
    """真栈取证：匿名打一枚队列状态出口，路由层那枚落账点一次都没被执行到。

    不许只看签名下结论。判据也不是「响应是 401」（那只说明有人拒了），而是「路由层的账一笔
    都没有」：R194 补在 ``chat.py:745`` 的落账点写出来的行，resource 恰好等于被探的任务 id。
    """
    from app.api.v1 import chat
    from app.common.reliable_queue import ReliableQueue

    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="r199:forensics", lease_seconds=30)
    message = queue.enqueue(
        {"message": TASK_MARKER, "principal": {"user_id": "keeper", "username": "keeper"}},
        "r199-forensics",
    )
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    probed = str(message.request_id)
    assert queue.redis.get(queue._message_key(probed)) is not None, "被探的任务确实在队列里"

    status, wire, body = _call(app, f"{QUEUE_PATH}/{probed}")

    assert status == BASELINE_401_STATUS, "改前事实：这一发由中间件作答 401"
    assert body == BASELINE_401_BODY
    route_lines = [row for row in _lines("resource:view") if row["resource"] == probed]
    assert route_lines == [], "取证失效：路由层的落账点被执行到了，本件就证不了「帮忙在中间件层」"
    # 中间件这一层的账是 R199 新加的（改前它为零笔），所以本枚只钉取证的那一半：
    # 路由层的落账点仍然一笔都没写，而写出来的那一笔的 resource 是被探的**路径**、
    # 不是任务 id —— 记账发生在门禁，不在路由。
    gate_lines = _lines()
    assert [row["resource"] for row in gate_lines] == [f"{QUEUE_PATH}/{probed}"], _blob(gate_lines)
    assert all(row["action"] == ANON_ACTION for row in gate_lines), _blob(gate_lines)
    assert TASK_MARKER not in _blob(journal.rows), "被拒探测的账里不该有别人的任务载荷"


def test_the_same_route_files_a_line_once_the_gate_lets_the_request_through(
    app, accounts, journal, monkeypatch
):
    """对照组：同一枚路由、同一套真栈，带上凭据就打得到那个落账点。

    缺这一枚，上一枚等于什么都没说 —— 它证明记账点是活的：匿名查无此账是因为请求根本没进门。
    """
    from app.api.v1 import chat
    from app.common.reliable_queue import ReliableQueue

    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="r199:contrast", lease_seconds=30)
    message = queue.enqueue(
        {"message": TASK_MARKER, "principal": {"user_id": "keeper", "username": "keeper"}},
        "r199-contrast",
    )
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    path = f"{QUEUE_PATH}/{message.request_id}"

    status, wire, body = _call(app, path, headers=_bearer("xdept"))

    assert status == 403, "跨部门探别人的任务：屏上还是那句拒绝"
    assert body == b'{"detail":"permission_denied"}'
    lines = [row for row in _lines("resource:view") if row["resource"] == str(message.request_id)]
    assert len(lines) == 1, "对照失败：带凭据时路由层的账也没了，说明取证用错了量具"
    assert TASK_MARKER not in _blob(lines), "账里只该有被探的任务 id，不该有任务载荷"


# ================================================= 第 2 组：判据② 匿名拒绝要落一笔


def test_an_anonymous_probe_files_one_denial_shaped_like_the_route_leg_ones(
    app, accounts, journal
):
    """判据②：一笔与 R179 同形的账 —— 同一个出口、同一组键，不是复制一份断言。

    同形用两件事钉住：行的键集合与一次直调 ``record_audit`` 的键集合逐位相同；退化主体走
    ``anonymous`` / ``unknown``，码沿用 detail 那句 ``authentication_required``。
    """
    from app.common.audit import record_audit

    status, wire, body = _call(app, "/api/v1/users")

    assert (status, body) == (BASELINE_401_STATUS, BASELINE_401_BODY)
    lines = _lines()
    assert len(lines) == 1, f"匿名探测必须留下一笔账，实测 {len(lines)} 笔：{_blob(lines)}"
    row = lines[0]
    assert row["username"] == "anonymous", row
    assert row["role"] == "unknown", row
    assert row["outcome"] == "denied", row
    assert row["reason"] == ANON_REASON, row
    assert row["resource"] == "/api/v1/users", "台账要看得出被扫的是哪一枚出口"
    assert str(row["event_id"]).startswith("aud-"), row
    assert row["created_at"] and row["expires_at"] and row["policy_version"], row
    assert row["persisted"] is True, "没落进持久台账的账不算账"
    assert row["request_id"] == "", "中间件没有相关 id 就不要造一个（audit.py:263 的规矩）"
    assert journal.upserts == 1, "一笔探测写两次盘 = 另有第二张脸"

    direct = record_audit(None, "resource:view", "denied", "shape-reference", ANON_REASON)
    assert set(row) == set(direct), (
        "不同形：匿名行与既有出口的键集合对不上 "
        f"多={sorted(set(row) - set(direct))} 少={sorted(set(direct) - set(row))}"
    )


def test_every_way_of_being_anonymous_is_filed_and_none_of_them_invents_a_subject(
    app, accounts, journal
):
    """``:124``（无凭证或验不过）与 ``:129``（有凭证查无此人）两枚出口都得落账。

    三种匿名形状在 ``after_summary.credential`` 上分得开，但主体那两栏一个字都不变：都是
    ``anonymous`` / ``unknown``，不新造第三种字面量；查无此人的 token 里那个名字也不许进台账。
    """
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.common import auth

    forged = "R199NOTAJWT"
    expired = jwt.encode(
        {"sub": "someone", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        auth._jwt_secret(),
        algorithm="HS256",
    )
    cases = [
        ("/api/v1/users", [], "absent"),
        ("/api/v1/alerts", [("Authorization", "Basic Zm86YmFy")], "absent"),
        ("/api/v1/documents", [("Authorization", "Bearer " + forged)], "invalid"),
        ("/api/v1/dashboard", [("Authorization", "Bearer " + expired)], "invalid"),
        ("/api/v1/artifacts", _bearer("nobody-here-anymore"), "unknown_account"),
    ]

    for index, (path, headers, _credential) in enumerate(cases):
        status, wire, body = _call(app, path, headers=headers, host=f"10.20.{index}.7")
        assert (status, body) == (BASELINE_401_STATUS, BASELINE_401_BODY), path

    lines = {row["resource"]: row for row in _lines()}
    assert sorted(lines) == sorted(entry[0] for entry in cases), (
        f"五枚匿名形状要各留一笔：{_blob(sorted(lines))}"
    )
    for path, _headers, credential in cases:
        row = lines[path]
        assert row["username"] == "anonymous" and row["role"] == "unknown", row
        assert row["reason"] == ANON_REASON, row
        assert row["after_summary"]["credential"] == credential, row
    blob = _blob([lines[entry[0]] for entry in cases])
    for secret in ("nobody-here-anymore", forged, "someone"):
        assert secret not in blob, f"台账里出现了没有凭据支撑的名字或整枚 token：{secret}"


# ============================================ 第 3 组：判据③ 只许走既有那一本账


def test_the_anonymous_line_reads_back_through_the_operations_audit_api(
    app, accounts, journal
):
    """判据③：从运维读口（``GET /api/v1/audit/events``）读得回来，才算进了同一本账。"""
    _call(app, "/api/v1/users")
    row = _lines()[0]

    status, wire, body = _call(app, "/api/v1/audit/events", headers=_bearer("root"))

    assert status == 200, body
    payload = json.loads(body)
    assert payload["source"] == "app.common.audit.get_audit_events", payload["source"]
    ids = [str(event.get("event_id")) for event in payload["events"]]
    assert str(row["event_id"]) in ids, f"另有一本账的嫌疑：读口里查不到这笔 {ids[:5]}"


def test_falsification_the_anonymous_line_only_comes_from_that_one_pathway(
    app, accounts, journal, monkeypatch
):
    """反证：摘掉 ``app/main`` 里那一条 record_audit 通路，账必须一行都不长、回话一字不变。

    如果落账还走了第二条通道（自造事件表 / 另一只 logger），这里摘不掉它，本枚当场红。
    """
    import app.main as main

    monkeypatch.setattr(main, "record_audit", lambda *args, **kwargs: {})

    status, wire, body = _call(app, "/api/v1/users")

    assert (status, wire, body) == (
        BASELINE_401_STATUS,
        BASELINE_401_HEADERS,
        BASELINE_401_BODY,
    ), "摘账不许把「怎么说」那半条也摘掉"
    assert _lines() == [], "摘掉通路还在长账 = 存在第二套审计形状"
    assert journal.upserts == 0, _blob(journal.rows)


# ================================================ 第 4 组：判据④ 刷账面要有牙


def test_a_flood_from_one_source_grows_the_ledger_logarithmically_not_one_for_one(
    app, accounts, journal
):
    """判据④：同一来源把一发行请求打 400 次，账必须按对数长，不是 400 笔。

    钉三件事：行数远小于探测数（不淹）；最后一行报出的累计笔数不小于探测数的一半（折叠可见、
    不静默丢）；写入次数等于行数（被折叠的那些一次磁盘写都不发生 —— 否则限流是假的）。
    """
    probes = 400

    responses = _calls(app, "/api/v1/queue/status/R199-flood", probes, host="10.30.0.9")

    expected = (BASELINE_401_STATUS, BASELINE_401_HEADERS, BASELINE_401_BODY)
    assert responses.count(expected) == probes, "刷账面期间回话变过形状"
    lines = _lines()
    assert len(lines) >= 2, f"一屏重复探测只留一笔 = 窗口后段彻底失声：{len(lines)}"
    bound = 2 + math.ceil(math.log2(probes))
    assert len(lines) <= bound, f"刷账面没牙：{probes} 次探测写了 {len(lines)} 笔账（上限 {bound}）"
    assert len(lines) < probes // 10, "行数与探测数还是一个量级 = 根本没有去重"
    assert journal.upserts == len(lines), (
        f"被折叠的探测还在写盘：{journal.upserts} 次写 / {len(lines)} 笔账"
    )
    counts = [row["after_summary"]["refusals"] for row in lines]
    assert counts == sorted(set(counts)), f"累计笔数必须单调可读：{counts}"
    assert counts[-1] * 2 >= probes, f"最后一笔只报了 {counts[-1]}/{probes}，丢得看不见"
    assert all(row["username"] == "anonymous" for row in lines)


def test_a_path_spray_from_one_source_is_capped_and_says_so(app, accounts, journal):
    """判据④第二格：换路径扫（每个目标只打一枪）也不许把台账刷爆。

    路径不重复 ⇒ 只按（来源, 路径）去重挡不住它，所以还有一层「同一来源在窗口内愿意为多少枚
    不同出口各起一行」的预算；超预算的合并进该来源那一行，并且明写 paths_capped。
    """
    sprayed = 200

    _drive(app, [_spec(f"/api/v1/scan-{index:04d}", host="10.31.0.9") for index in range(sprayed)])

    lines = _lines()
    bound = 10 + math.ceil(math.log2(sprayed))
    assert len(lines) <= bound, f"扫路径就能刷账：{sprayed} 枚出口写了 {len(lines)} 笔"
    assert len(lines) < sprayed // 4
    assert journal.upserts == len(lines)
    assert any(row["after_summary"].get("paths_capped") is True for row in lines), (
        "超预算必须说得出自己合并了：没有任何一行写着 paths_capped"
    )
    refusals = max(row["after_summary"]["refusals"] for row in lines)
    assert refusals * 2 >= sprayed, f"只报了 {refusals}/{sprayed}"


def test_a_second_source_is_not_swallowed_by_the_first(app, accounts, journal):
    """去重按来源分钉：一个来源的窗口不许把另一个来源的探测一起盖掉。"""
    path = "/api/v1/users"

    _call(app, path, host="10.32.0.1")
    _call(app, path, host="10.32.0.2")

    lines = _lines()
    sources = sorted(str(row["after_summary"]["source"]) for row in lines)
    assert sources == ["10.32.0.1", "10.32.0.2"], f"两个来源各该留一行：{_blob(sources)}"
    assert [row["resource"] for row in lines] == [path, path]


def test_the_window_expires_so_a_later_probe_files_again(app, accounts, journal, monkeypatch):
    """判据④的另一半：折叠只在有限窗口内成立，过期之后同一枚探测重新长账。

    不会过期的「去重」等于「一段时间只记一次」，那对慢扫是失声的。这里走时钟桩，不睡觉。
    """
    import app.main as main

    clock = {"now": 1000.0}
    monkeypatch.setattr(main, "_anonymous_probe_clock", lambda: clock["now"])
    window = main._ANONYMOUS_PROBE_WINDOW_SECONDS
    path = "/api/v1/users"

    _call(app, path, host="10.33.0.1")
    assert len(_lines()) == 1, "第一笔必记"
    clock["now"] += 5
    _call(app, path, host="10.33.0.1")
    assert len(_lines()) == 2, "按 2 的幂补记：第 2 笔要看得见"
    clock["now"] += 5
    _call(app, path, host="10.33.0.1")
    assert len(_lines()) == 2, "第 3 笔该被折叠进同一行的计数里，不是再长一行"

    clock["now"] += window
    _call(app, path, host="10.33.0.1")

    lines = _lines()
    assert len(lines) == 3, "窗口过期后必须重新起一行，否则慢扫只留一天的账"
    assert lines[-1]["after_summary"]["refusals"] == 1, _blob(lines)
    assert lines[-1]["after_summary"]["occurrences"] == 1


# ================================================ 第 5 组：判据⑤ 响应零变化


@pytest.mark.parametrize(
    "case",
    ["no-credential", "non-bearer", "forged-token", "unknown-account-token"],
)
def test_the_anonymous_401_is_byte_for_byte_the_pre_change_baseline(
    app, accounts, journal, case
):
    headers = {
        "no-credential": [],
        "non-bearer": [("Authorization", "Basic Zm86YmFy")],
        "forged-token": [("Authorization", "Bearer R199NOTAJWT")],
    }.get(case)
    """判据⑤：401 的状态码 / 正文 / 响应头逐字不动 —— 本单加的是账，不是行为。

    基线字节取自改前（4dcbd30）真栈实测；四枚形状共用同一发线形，逐枚都钉。
    """
    if headers is None:  # unknown-account-token：一枚签得好、查无此人的凭证
        headers = _bearer("nobody-here-anymore")

    status, wire, body = _call(app, "/api/v1/users", headers=headers)

    assert status == BASELINE_401_STATUS, case
    assert wire == BASELINE_401_HEADERS, f"响应头不许多一枚：{wire}"
    assert body == BASELINE_401_BODY, case
    assert "www-authenticate" not in [name.lower() for name, _ in wire], "401 不许顺手加认证提示头"
    assert len(_lines()) == 1, f"{case}：每枚被拒的探测一行账"


def test_a_query_string_never_reaches_the_ledger(app, accounts, journal):
    """落账顺手不许扩大泄漏面：查询串（常带 token / id）一个字都不进台账。"""
    _call(app, "/api/v1/users", query=b"token=R199-IN-QUERY&password=R199-IN-QUERY")

    blob = _blob(_lines())
    assert "R199-IN-QUERY" not in blob, blob
    assert "/api/v1/users" in blob


def test_a_journal_that_cannot_be_written_cannot_change_the_answer(
    app, accounts, journal, monkeypatch
):
    """判据⑤的牙：记账本身炸了，也不许把 401 变成 500。"""
    import app.main as main

    def _boom(*args, **kwargs):
        raise RuntimeError("R199 台账写不进去")

    monkeypatch.setattr(main, "record_audit", _boom)

    status, wire, body = _call(app, "/api/v1/users")

    assert (status, wire, body) == (
        BASELINE_401_STATUS,
        BASELINE_401_HEADERS,
        BASELINE_401_BODY,
    ), "账写坏了就改回话 = 本单把可观测性改动做成了行为改动"


def test_open_paths_and_granted_requests_file_no_anonymous_line(app, accounts, journal):
    """开门路径与放行路径都不许长出匿名账；它们的线形也一字未动。"""
    health = _call(app, "/api/v1/health")
    granted = _call(app, "/api/v1/audit/events", headers=_bearer("root"))

    assert health == (200, [("content-length", "15"), ("content-type", "application/json")],
                      BASELINE_HEALTH_BODY)
    assert granted[0] == 200
    assert _lines() == [], "只有被拒的未登录探测才该长这一笔"
    assert journal.upserts == 0, _blob(journal.rows)


def test_the_403_disabled_account_exit_is_left_alone_and_still_speaks_the_same_words(
    app, accounts, journal
):
    """``app/main.py:133`` 那枚 403 本单不碰：线形一字不动，也不长匿名账（它有主体）。"""
    accounts["ghost"] = DISABLED_GHOST

    status, wire, body = _call(app, "/api/v1/users", headers=_bearer("ghost"))

    assert (status, wire, body) == (
        BASELINE_403_STATUS,
        BASELINE_403_HEADERS,
        BASELINE_403_BODY,
    )
    assert _lines() == []
