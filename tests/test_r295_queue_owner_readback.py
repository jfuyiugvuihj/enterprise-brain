"""R295 · 队列单的归属在读取时刻现取，不再信载荷快照（判据④与反证⑤c）。

病灶：app/api/v1/chat.py 的 /queue/status 与 /queue/{id}/cancel 拿**载荷快照里的
user_id** 当单子归属人（旧 _authorize_queue_task 三行：owner = payload["principal"];
owner_id = owner["user_id"]）。那是入队那一刻冻下的身份，之后没有任何一格回来更新它。
R294（deploy/queue_worker.py::resolve_consumption_principal）已经把「消费时刻现取身份」
立成权威，载荷=权威这最后一个还活着的读点就在本文件，所以一起收掉。

方向与 R294 同一套：现取，或比对后判失效。第二枚读数非空就是归属没确立，调用方一律
判失效，绝不把「读不出」放宽成「放行」。用户库三档口径照抄 R294，不在这儿立第二套：
postgres 现取现比、unavailable 判失效（R230 早就把它定成 default-deny）、memory 是
进程内表、跨进程本来就不同步，这一侧无从现取，按快照交回并明写「未经现取校验」。

判据 → 用例

④ 归属取自用户库，不取自载荷      test_the_owner_is_read_from_the_user_store_at_poll_time
                                  + test_an_account_named_by_the_frozen_snapshot_cannot_read_the_task_body
                                  + test_the_cancel_door_shares_that_one_owner_reading
   跨账号读不到别人的正文          test_a_ticket_whose_claim_matches_the_store_reads_for_its_owner_only
   旧载荷不崩、不提权              test_legacy_payload_shapes_neither_crash_nor_escalation
   与 R294 同源（词表与回退）      test_the_owner_vocabulary_is_the_same_one_the_worker_ships
                                  + test_the_memory_store_keeps_the_documented_fallback
   读数不许带出部门与密级实值      test_no_department_or_clearance_value_leaves_the_queue_leg
   批准台账拿的是现取归属          test_the_approval_ledger_is_asked_with_the_consumption_owner
⑤c 反证常驻                       test_counter_evidence_the_snapshot_rule_lets_another_account_read

全程离线：进程内 TestClient + tests/test_reliable_queue.py 的 FakeRedis + 真
ReliableQueue + 假用户表（只换 auth.get_user 与 auth.user_storage_state 两枚现成读点），
零起服务、零真机 redis、零模型、零库，被跟踪文件零字节落盘。
"""
import ast
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.common import auth

#: 单子载荷里的正文：这一刻它只属于排队的那一个人的那一轮。
TASK_BODY = "R295-TASK 这段载荷只属于排在队列里的那一轮"
#: 单子跑完之后交回的那段正文：判据④说的「别人的正文」在这一格上才是真的正文。
ANSWER_BODY = "R295-ANSWER 这一格答案正文只该交给单子的主人"
#: 载荷快照里冻着的归属 id，与用户库今天那一行的 id 故意不同：不同就是漂移。
FROZEN_ID = "u-r295-frozen-in-payload"
LIVE_ID = "u-r295-live-in-the-store"
PROBER_ID = "u-r295-prober-in-the-store"

OWNER = "r295-owner"
IMPOSTER = "r295-imposter"
PROBER = "r295-prober"

#: 只有这张表能改变可见范围的实值：它们一个字都不许离开这条腿。
SECRET_DEPARTMENT = "r295-secret-finance"
DEPT_SENTINEL = "R295-DEPT-SENTINEL-部门实值"
CLASS_SENTINEL = "R295-CLASS-SENTINEL-密级实值"

#: 这条腿对外说的两枚码（既有出口，一枚都不新造）。
QUEUE_EXIT_CODES = frozenset(
    {
        "authentication_required",
        "resource_not_found",
        "authorization_unavailable",
        "permission_denied",
    }
)

_ROWS = {
    OWNER: {"id": LIVE_ID, "username": OWNER, "role": "manager", "department": DEPT_SENTINEL},
    IMPOSTER: {"id": FROZEN_ID, "username": IMPOSTER, "role": "manager", "department": DEPT_SENTINEL},
    PROBER: {"id": PROBER_ID, "username": PROBER, "role": "manager", "department": DEPT_SENTINEL},
}


@pytest.fixture()
def client(monkeypatch):
    """只接管「认证查人」与「用户库是哪一档」这两条现成读点，其余走真实路由。"""
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: dict(_ROWS[username]) if username in _ROWS else None)
    monkeypatch.setattr(
        auth, "user_storage_state", lambda: {"storage_mode": "postgres", "shared_across_processes": True}
    )
    return TestClient(app)


@pytest.fixture()
def memory_client(client, monkeypatch):
    """同一套读点，只把用户库换回进程内表那一档（R294 的回退分支）。"""
    monkeypatch.setattr(
        auth, "user_storage_state", lambda: {"storage_mode": "memory", "shared_across_processes": False}
    )
    return client


@pytest.fixture()
def queue(monkeypatch):
    """真产品队列 ReliableQueue + 进程内 FakeRedis：不碰真机 redis，不起服务。"""
    from app.api.v1 import chat
    from app.common.reliable_queue import ReliableQueue

    from tests.test_reliable_queue import FakeRedis

    instance = ReliableQueue(FakeRedis(), name="r295:test", lease_seconds=30)
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: instance)
    return instance


@pytest.fixture()
def audit_rows(monkeypatch):
    """包一层 chat 模块的 record_audit：原实现照调，只取位置参数（沿 R175/R179/R194 的形状）。"""
    import app.api.v1.chat as chat_module
    import app.common.audit as audit_module

    original = audit_module.record_audit
    rows = []

    def _record(principal, action, outcome, resource="", reason="", **kwargs):
        event = original(principal, action, outcome, resource, reason, **kwargs)
        rows.append(
            {
                "username": str(getattr(principal, "username", "") or "anonymous"),
                "action": str(action),
                "outcome": str(outcome),
                "resource": str(resource),
                "reason": str(reason),
            }
        )
        return event

    monkeypatch.setattr(chat_module, "record_audit", _record)
    return rows


def _enqueue(queue, *, subject, claimed_id, include_roles_only=False, drop_principal=False):
    """把一张「归谁」只由载荷自己说的单子放进真队列，返回任务 id。"""
    if drop_principal:
        payload = {
            "task_type": "ask",
            "message": TASK_BODY,
            "session_id": "r295-session",
            "username": subject,
            "user_id": claimed_id,
            "roles": ["manager"],
        }
    else:
        snapshot = {"user_id": claimed_id, "username": subject}
        if include_roles_only:
            snapshot["roles"] = ["manager"]
        payload = {
            "task_type": "ask",
            "message": TASK_BODY,
            "session_id": "r295-session",
            "username": subject,
            "principal": snapshot,
        }
    return str(queue.enqueue(payload, "r295-idem-" + subject + "-" + str(claimed_id)).request_id)


def _as(client, username):
    from app.common.auth import create_token

    client.headers.update({"Authorization": "Bearer " + create_token(username)})


def _blob(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _finish(queue, target):
    """把这张单子跑到 done：那一格正文从此才是越权者真正想拿的东西。"""
    queue.reserve()
    assert queue.complete(target, ANSWER_BODY)


def _status(client, target):
    return client.get("/api/v1/queue/status/" + target)


# ==================== 判据④：归属现取，不读快照 ====================


def test_the_owner_is_read_from_the_user_store_at_poll_time(client, queue):
    """载荷说这张单子是 FROZEN_ID 的，用户库今天说它是 LIVE_ID 的：判失效，不认快照。

    旧规则在这里交出的是 200（owner_id 直接抄载荷，与调用方现取身份一比即合），
    改完归属之后这一格再也不是「谁的名字写在载荷上谁就是归属人」。
    """
    target = _enqueue(queue, subject=OWNER, claimed_id=FROZEN_ID)
    _finish(queue, target)
    _as(client, OWNER)

    response = _status(client, target)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "authorization_unavailable"
    assert ANSWER_BODY not in response.text, "反证：判失效的那张脸仍然把正文交了出去"


def test_an_account_named_by_the_frozen_snapshot_cannot_read_the_task_body(client, queue):
    """判据④的核心那一格：另一个人顶着快照里那枚 user_id 来读，拿不到正文。

    IMPOSTER 在用户库里的 id 就是 FROZEN_ID——旧规则拿载荷当权威，一比即合，这张
    别人的单子就此整份读走。现取之后载荷说不上话。
    """
    target = _enqueue(queue, subject=OWNER, claimed_id=FROZEN_ID)
    _finish(queue, target)
    _as(client, IMPOSTER)

    response = _status(client, target)
    assert response.status_code == 403, "反证：载荷快照又成权威了，顶着旧 id 的人读到了别人的单子"
    assert response.json()["detail"] == "authorization_unavailable"
    assert ANSWER_BODY not in response.text, "反证：别人的答案正文跨账号读回来了"


def test_a_ticket_that_is_not_mine_still_gets_permission_denied(client, queue):
    """归属对上了用户库、来问的人却是别人：仍是那枚 permission_denied，一码都没换。"""
    target = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID)
    _finish(queue, target)
    _as(client, PROBER)

    response = _status(client, target)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    assert ANSWER_BODY not in response.text


def test_the_owner_reads_its_own_ticket_and_the_cancel_door_agrees(client, queue):
    """正向对照：绿不是把口子关死刷出来的——归属现取之后本人两条门照旧走。"""
    target = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID)
    _finish(queue, target)
    _as(client, OWNER)

    own = _status(client, target)
    assert own.status_code == 200, own.text
    assert own.json()["result"] == ANSWER_BODY, "本人读自己的单子，那一格正文照旧交得回来"
    cancelled = client.post("/api/v1/queue/" + target + "/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert queue.is_cancelled(target), "本人这一扇门要真的把取消落下，只回一张脸不算"


def test_the_cancel_door_shares_that_one_owner_reading(client, queue):
    """同一族另一扇门：cancel 用的是同一枚现取归属，不许留第二份读法。"""
    target = _enqueue(queue, subject=OWNER, claimed_id=FROZEN_ID)
    _as(client, IMPOSTER)

    response = client.post("/api/v1/queue/" + target + "/cancel")
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "authorization_unavailable"
    assert queue.status(target) == "queued", "被拒的取消不许真的把别人的任务取消掉"


def test_legacy_payload_shapes_neither_crash_nor_escalate(client, queue):
    """旧载荷那两只形状都不崩、都不提权：只带三键的快照，以及压根没有归属读数。"""
    _as(client, OWNER)

    roles_only = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID, include_roles_only=True)
    assert _status(client, roles_only).status_code == 200

    top_level = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID, drop_principal=True)
    assert _status(client, top_level).status_code == 200

    idless = _enqueue(queue, subject=OWNER, claimed_id="", drop_principal=True)
    idless_read = _status(client, idless)
    assert idless_read.status_code == 403, idless_read.text
    assert idless_read.json()["detail"] == "authorization_unavailable", "读不出归属人就是失效，不猜默认值"

    _as(client, PROBER)
    assert _status(client, top_level).status_code == 403
    assert _status(client, idless).status_code == 403


def test_an_unreadable_or_empty_payload_still_speaks_the_old_words(client, queue):
    """坏载荷那两枚出口一字未改：解不开与压根没载荷都判失效，而不是 500。"""
    target = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID)
    queue.redis.set(queue._message_key(target), "{not-json")
    _as(client, OWNER)
    assert _status(client, target).status_code == 403

    queue.redis.set(queue._message_key(target), json.dumps({"payload": {}}))
    response = _status(client, target)
    assert response.status_code == 403
    assert response.json()["detail"] == "authorization_unavailable"


def test_the_memory_store_keeps_the_documented_fallback(memory_client, queue, caplog):
    """用户库是进程内表那一档：按快照交回并明写未经现取校验——那是 R294 既有的限制。

    回退不等于放宽：来问的人仍由认证中间件那份现取身份说了算，别人的账号照样吃 403；
    这一行日志只记成因，不记主体。
    """
    caplog.set_level(logging.WARNING)
    target = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID)

    _as(memory_client, OWNER)
    assert _status(memory_client, target).status_code == 200

    _as(memory_client, PROBER)
    probe = _status(memory_client, target)
    assert probe.status_code == 403
    assert probe.json()["detail"] == "permission_denied"

    lines = [r.getMessage() for r in caplog.records if "R295" in r.getMessage()]
    assert any("identity_store_not_shared" in line for line in lines), "回退那一支必须自报未经现取校验"
    joined = " | ".join(lines)
    for value in (OWNER, LIVE_ID, DEPT_SENTINEL):
        assert value not in joined, "反证：回退那行日志里漏出了 " + value


def test_the_owner_vocabulary_is_the_same_one_the_worker_ships():
    """判据④「同源」那半条的机检：两侧模块级成因码逐字相等，不许漂成两套词。"""
    import io

    def _constants(path, prefix):
        tree = ast.parse(io.open(path, "r", encoding="utf-8").read())
        found = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                name = getattr(node.targets[0], "id", "")
                if name.startswith(prefix) and isinstance(node.value, ast.Constant):
                    found[name] = node.value.value
        return found

    worker = _constants("deploy/queue_worker.py", "IDENTITY_")
    api = _constants("app/api/v1/chat.py", "QUEUE_OWNER_")
    assert len(api) == 6, "归属成因码应当正好六枚，多一枚少一枚都是漂了：" + _blob(sorted(api))
    missing = {key: value for key, value in api.items() if value not in set(worker.values())}
    assert not missing, "反证：这几枚码与消费侧不同源 " + _blob(missing)


def test_the_approval_ledger_is_asked_with_the_consumption_owner(client, queue, monkeypatch):
    """出口最后一格也不回头抄载荷：批准台账收到的是现取并比对过的那一枚归属。"""
    import app.api.v1.chat as chat
    from app.common import reliable_queue

    target = _enqueue(queue, subject=OWNER, claimed_id=LIVE_ID)
    queue.reserve()
    queue.complete(
        target,
        None,
        terminal=chat.build_queue_terminal(
            terminal_state=chat.TERMINAL_STATE_AWAITING_APPROVAL,
            answer_present=False,
            approval=chat.hitl_approval_handle(
                session_id="r295-session",
                parked={"pending": ["export"], "labels": ["R295 导出报告"]},
            ),
        ),
    )

    asked = []

    def _spy(session_id, owner_user_id):
        asked.append((session_id, owner_user_id))
        return "absent"

    monkeypatch.setattr(chat, "approval_ledger_state", _spy)
    _as(client, OWNER)
    response = _status(client, target)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == reliable_queue.AWAITING_APPROVAL
    assert asked == [("r295-session", LIVE_ID)], "台账那一格拿的必须是现取归属：" + _blob(asked)


def test_no_department_or_clearance_value_leaves_the_queue_leg(client, queue, audit_rows, caplog):
    """判据②同族的纪律：部门与密级实值一个字都不进返回值、台账与日志。"""
    caplog.set_level(logging.WARNING)
    target = _enqueue(queue, subject=OWNER, claimed_id=FROZEN_ID)
    _as(client, IMPOSTER)

    response = _status(client, target)
    assert response.status_code == 403
    denials = [row for row in audit_rows if row["resource"] == target]
    assert len(denials) == 1, "一枚出口一笔账，不许重复记账"
    assert denials[0]["reason"] in QUEUE_EXIT_CODES, denials[0]["reason"]

    surfaces = [response.text, _blob(denials)] + [r.getMessage() for r in caplog.records]
    for surface in surfaces:
        for value in (DEPT_SENTINEL, CLASS_SENTINEL, SECRET_DEPARTMENT):
            assert value not in surface, "反证：" + value + " 离开了用户库那一行"


# ==================== 判据⑤c：反证常驻 ====================


def test_counter_evidence_the_snapshot_rule_lets_another_account_read(client, queue, monkeypatch):
    """反证③（判据④）：把归属判定退回载荷快照，跨账号当场就读到别人的正文。

    这枚钉拿 R294 之前的那三行原文当反证：owner = payload["principal"];
    owner_id = owner.get("user_id")。换上它，IMPOSTER 顶着一枚冻在载荷里的旧 id 就能
    整份读走 OWNER 的单子——如果本单的改动其实没生效，摘掉它也该没差别，本枚当场红。
    """
    import app.api.v1.chat as chat

    target = _enqueue(queue, subject=OWNER, claimed_id=FROZEN_ID)
    _finish(queue, target)
    _as(client, IMPOSTER)
    denied = _status(client, target)
    assert denied.status_code == 403, "出货代码这一格必须是 403"
    assert ANSWER_BODY not in denied.text

    def _old_rule(payload):
        owner = payload.get("principal") or {}
        return str(owner.get("user_id") or ""), ""

    monkeypatch.setattr(chat, "queue_task_owner_user_id", _old_rule)
    leaked = _status(client, target)
    assert leaked.status_code == 200, "反证失效：退回载荷快照之后跨账号仍然读不到，说明挡它的不是归属现取"
    assert leaked.json()["result"] == ANSWER_BODY, "反证失效：退回载荷快照却没把别人的正文交出来"
