"""R194 · 队列任务腿五枚拒绝出口落账 + 平铺 GET /documents 的第二张脸。

两格同族，都出自 R179（主树 f51576f）结案时具名上报的两笔同形漏点：

  第 1 格 chat.py:703 _authorize_queue_task —— 这条腿的五枚拒绝出口（401
      authentication_required / 404 resource_not_found / 403
      authorization_unavailable ×2 / 403 permission_denied）一枚都不进审计台账：
      别人排在队列里的任务 id 探一下，屏上给了拒绝、机器上一行痕迹都没有。
  第 2 格 chat.py:3410 GET /documents —— 把 visible ∩ indexed 直接拼成文件名数组，
      于是「这份文件有、但你不能看」与「这台机器上根本没有这份文件」在出口同一张脸
      （R179 已在 chat.py:3423 的 catalog 出口带 restricted 拆掉，同族漏了这一处）。

本格修的是「落不落账」与「说不说得清」，不是「怎么说」：五枚出口的 status_code 与
detail 逐字不动（tests/test_reliable_queue_status_api.py 与前端钉着它），老调用方读
documents 数组的结果也逐字不变（scripts/check_corpus_parity.py 就靠它），只加键。

判定与计数只许仓里那一份（app/rag/filters.py 的 allows / refusal_code，经 chat.py 的
_classify_document_rows 落到既有 record_audit 通路）；记账只走 record_audit 那一条通路，
不另起日志器、不用 logger.warning 了事。

全部离线：进程内 TestClient + tests/test_reliable_queue.py 的 FakeRedis + 真 ReliableQueue，
零起服务、零真机 redis、零模型、零库。
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException as HTTPException_type

DEPT_OWN = "r194-finance"
DEPT_FOREIGN = "r194-hr"

#: 哨兵：这一刻它们确实存在于进程里（别人排队任务的载荷、别人文档的正文）。
TASK_TOKEN = "R194-TASK 这段载荷只属于排在队列里的任务"
BODY_TOKEN = "R194T-BODY 这一段正文只属于别人的文档"
OWN_NAME = "R194-own-report.txt"
OWN_STEM = "R194-own-report"
FOREIGN_NAME = "R194-foreign-report.txt"

#: 「有但不能看」必须说出的因由（与 R179 的 catalog 同一句口径）。
HONEST_MARKER = "可见范围"
#: 文档腿的稳定码词表（沿用 R179 那一份，不扩表）。
STABLE_CODES = frozenset(
    {
        "department_scope_denied",
        "clearance_insufficient",
        "resource_scope_missing",
        "permission_denied",
    }
)
#: 队列腿五枚出口的码：就是它们各自的 HTTP detail，一格都不新造。
QUEUE_CODES = frozenset(
    {
        "authentication_required",
        "resource_not_found",
        "authorization_unavailable",
        "permission_denied",
    }
)

ACCOUNTS = {
    "keeper": {"id": "keeper", "username": "keeper", "role": "manager", "department": DEPT_OWN},
    "xdept": {"id": "xdept", "username": "xdept", "role": "manager", "department": DEPT_FOREIGN},
    "nodept": {"id": "nodept", "username": "nodept", "role": "staff", "department": ""},
    "root": {"id": "root", "username": "root", "role": "admin", "department": ""},
}


@pytest.fixture()
def client(monkeypatch):
    """只接管「认证查人」这一条缝，其余走真实路由。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    return TestClient(app)


def _as(client, username: str) -> None:
    from app.common.auth import create_token

    client.headers.update({"Authorization": "Bearer " + create_token(username)})


def _blob(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@pytest.fixture()
def audit_rows(monkeypatch) -> list[dict]:
    """包一层 chat 模块的 record_audit：原实现照调，顺手取位置参数（沿 R175/R179 的取证件形状）。"""
    import app.api.v1.chat as chat_module
    import app.common.audit as audit_module

    original = audit_module.record_audit
    rows: list[dict] = []

    def _record(principal, action, outcome, resource="", reason="", **kwargs):
        event = original(principal, action, outcome, resource, reason, **kwargs)
        rows.append(
            {
                "username": str(getattr(principal, "username", "") or "anonymous"),
                "action": str(action),
                "outcome": str(outcome),
                "resource": str(resource),
                "reason": str(reason),
                "event": event,
            }
        )
        return event

    monkeypatch.setattr(chat_module, "record_audit", _record)
    return rows


# ================================================== 第 1 格：队列任务腿


@pytest.fixture()
def queue(monkeypatch):
    """真产品队列 ReliableQueue + 进程内 FakeRedis：不碰真机 redis，不起服务。"""
    from app.api.v1 import chat
    from app.common.reliable_queue import ReliableQueue

    from tests.test_reliable_queue import FakeRedis

    instance = ReliableQueue(FakeRedis(), name="r194:test", lease_seconds=30)
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: instance)
    return instance


def _queued_task(queue, owner: str, idem: str) -> str:
    """把一份「别人排在队列里的任务」放进真队列，返回它的任务 id。"""
    message = queue.enqueue(
        {"message": TASK_TOKEN, "principal": {"user_id": owner, "username": owner}},
        idem,
    )
    return str(message.request_id)


@pytest.mark.parametrize(
    ("door", "action"),
    [("read", "resource:view"), ("cancel", "resource:delete")],
)
def test_a_probe_of_anothers_task_files_a_denial_under_its_own_door(
    client, queue, audit_rows, door, action
):
    """判据①②：越权探测必须落既有通路，而且动词得说得出是哪一扇门。"""
    target = _queued_task(queue, owner="keeper", idem="r194-door")
    _as(client, "xdept")

    if door == "read":
        response = client.get(f"/api/v1/queue/status/{target}")
    else:
        response = client.post(f"/api/v1/queue/{target}/cancel")

    # 判据③：屏上怎么说，一字未动。
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    assert TASK_TOKEN not in response.text, "403 不许把别人任务的载荷带出来"

    denials = [
        row for row in audit_rows if row["outcome"] == "denied" and row["resource"] == target
    ]
    assert denials, f"反证①：{door} 这扇门探测别人的任务 id，在审计台账里查不到一笔"
    row = denials[0]
    assert row["username"] == "xdept", "主体必须是来探测的那个人"
    assert row["reason"] == "permission_denied", "稳定码不许被换成一句人读的话"
    assert row["action"] == action, f"{door} 这扇门要记成 {action}，不许共用一枚笼统动词"
    assert TASK_TOKEN not in _blob(denials), "反证：台账里混进了别人任务的载荷"


@pytest.mark.parametrize(
    ("scenario", "status_code", "reason"),
    [
        ("missing_task", 404, "resource_not_found"),
        ("unreadable_payload", 403, "authorization_unavailable"),
        ("ownerless_payload", 403, "authorization_unavailable"),
        ("foreign_task", 403, "permission_denied"),
    ],
)
def test_every_refusal_exit_on_the_queue_leg_files_its_own_line(
    client, queue, audit_rows, scenario, status_code, reason
):
    """五枚拒绝出口一枚都不能漏：每枚都在既有通路留一笔，码就是它自己那句 detail。"""
    needs_task = scenario in {"foreign_task", "ownerless_payload", "unreadable_payload"}
    target = (
        _queued_task(queue, owner="keeper", idem=f"r194-{scenario}")
        if needs_task
        else "r194-absent-task"
    )
    if scenario == "unreadable_payload":
        queue.redis.set(queue._message_key(target), "{not-json")
    elif scenario == "ownerless_payload":
        queue.redis.set(queue._message_key(target), json.dumps({"payload": {}}))

    _as(client, "xdept")

    response = client.get(f"/api/v1/queue/status/{target}")

    assert response.status_code == status_code, response.text
    assert response.json()["detail"] == reason

    denials = [
        row for row in audit_rows if row["outcome"] == "denied" and row["resource"] == target
    ]
    assert denials, f"反证①：出口 {reason}（HTTP {status_code}）在审计台账里查不到一笔"
    assert len(denials) == 1, "一枚出口记一笔，不许重复记账"
    line = denials[0]
    assert line["reason"] == reason
    assert line["reason"] in QUEUE_CODES, "拒绝码必须是这条腿既有的封闭码，不许新造"
    assert line["username"] == "xdept"
    assert TASK_TOKEN not in _blob(denials), "反证：拒绝账里混进了别人任务的载荷"


def test_the_two_doors_do_not_share_one_generic_verb(client, queue, audit_rows):
    """判据②：同一份拒绝在两扇门上的动词必须分得开，且只能取自仓里既有词表。"""
    import app.common.permissions as permissions

    target = _queued_task(queue, owner="keeper", idem="r194-verbs")
    _as(client, "xdept")

    assert client.get(f"/api/v1/queue/status/{target}").status_code == 403
    assert client.post(f"/api/v1/queue/{target}/cancel").status_code == 403
    assert queue.status(target) == "queued", "被拒的取消不许真的把别人的任务取消掉"

    actions = sorted(
        {
            row["action"]
            for row in audit_rows
            if row["outcome"] == "denied" and row["resource"] == target
        }
    )
    vocabulary = {value for key, value in vars(permissions).items() if key.startswith("ACTION_")}
    assert actions == sorted(["resource:view", "resource:delete"]), (
        f"两扇门各记各的动词，实际落账 {actions}"
    )
    assert set(actions) <= vocabulary, "动词必须取自 app/common/permissions.py 的既有词表"


@pytest.mark.parametrize("door", ["read", "cancel"])
def test_the_owner_still_walks_both_doors_without_filing_a_denial(
    client, queue, audit_rows, door
):
    """正向对照：绿不是把口子关死刷出来的——本人走自己的门照旧通，也不该长出拒绝账。"""
    target = _queued_task(queue, owner="xdept", idem=f"r194-owner-{door}")
    _as(client, "xdept")

    if door == "read":
        response = client.get(f"/api/v1/queue/status/{target}")
    else:
        response = client.post(f"/api/v1/queue/{target}/cancel")

    assert response.status_code == 200, response.text
    assert [row for row in audit_rows if row["outcome"] == "denied"] == [], (
        "本人轮询自己的任务不许被记成拒绝——前端每 3s 一次，凭空刷账"
    )


def test_falsification_the_queue_denial_accounting_runs_on_that_one_pathway(
    client, queue, audit_rows, monkeypatch
):
    """反证①常驻：摘掉 chat 的审计通路，同一套取证必须一行都查不到。

    如果拒绝记账走了第二条通道（自造事件表、或绑到别的模块名上），这里摘不掉它，
    本枚当场红。同时验一句：摘账不许把「怎么说」那半条也摘掉。
    """
    import app.api.v1.chat as chat

    target = _queued_task(queue, owner="keeper", idem="r194-falsify")
    _as(client, "xdept")
    assert client.get(f"/api/v1/queue/status/{target}").status_code == 403
    assert [row for row in audit_rows if row["outcome"] == "denied"]

    monkeypatch.setattr(chat, "record_audit", lambda *a, **k: {})
    rows_before = len(audit_rows)
    read = client.get(f"/api/v1/queue/status/{target}")
    cancel = client.post(f"/api/v1/queue/{target}/cancel")

    assert len(audit_rows) == rows_before, "摘掉通路还在长账 = 存在第二套审计形状"
    assert read.status_code == 403 and read.json()["detail"] == "permission_denied"
    assert cancel.status_code == 403 and cancel.json()["detail"] == "permission_denied"


# ---- 401 那一枚：出口在本函数手里，但 HTTP 栈上它前面还有一层中间件（见测试内说明）


def test_the_unauthenticated_exit_files_a_denial_and_speaks_the_same_words(
    client, queue, audit_rows
):
    """五枚出口里的 401（authentication_required）那一枚：在函数层落账，口径一字不动。

    取证时撞到的一条事实（照原样交回总控，不改判据）：这条腿经 HTTP 栈走不到那枚
    401 —— app/main.py:96 AuthMiddleware 在进路由之前就替它把无凭证的请求拒了
    app/main.py:124 与 app/main.py:129 两处各回一记 401 authentication_required）。
    所以「匿名探测队列任务 id 不留痕」那半句要拆成两截看：
      - _authorize_queue_task 自己的那枚 401 出口，本枚在真实函数上直接取证；
      - 中间件那层的全站 401 不落账，面覆盖 40 多枚路由，不属这条腿，本单不碰。
    两截都验：真路由上匿名请求的回话形状一字未动。
    """
    from fastapi import Request

    from app.api.v1 import chat

    target = _queued_task(queue, owner="keeper", idem="r194-anonymous")
    path = f"/api/v1/queue/status/{target}"
    anonymous = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "root_path": "",
        }
    )

    with pytest.raises(HTTPException_type) as raised:
        chat._authorize_queue_task(anonymous, queue, target)

    assert raised.value.status_code == 401
    assert raised.value.detail == "authentication_required"

    denials = [
        row for row in audit_rows if row["outcome"] == "denied" and row["resource"] == target
    ]
    assert denials, "反证①：无身份探测这条任务 id 的拒绝在审计台账里查不到一笔"
    assert len(denials) == 1
    assert denials[0]["reason"] == "authentication_required"
    assert denials[0]["username"] == "anonymous", "没有主体时台账要写成匿名，不许凭空造一个人"
    assert TASK_TOKEN not in _blob(denials)

    # 同一枚探测走真路由：回话形状一字未动（那一层由中间件作答）。
    probe = client.get(path)
    assert probe.status_code == 401, probe.text
    assert probe.json()["detail"] == "authentication_required"


# ============================================ 第 2 格：平铺 GET /documents


def _doc_row(name: str, department: str, tmp_path, owner_id: str) -> dict:
    stored = tmp_path / name
    stored.write_text(BODY_TOKEN, encoding="utf-8")
    return {
        "filename": name,
        "storage_path": str(stored),
        "department": department,
        "classification": 1,
        "owner_id": owner_id,
        "version": 1,
    }


def _shelf(monkeypatch, chat, tmp_path, rows: list[dict], indexed: list[str]) -> None:
    """钉住「盘上有哪几份」与「索引里有哪几份」两条名单。"""
    monkeypatch.setattr(chat, "current_documents", lambda *a, **k: [dict(row) for row in rows])
    monkeypatch.setattr(chat.retriever, "list_documents", lambda: list(indexed))


def _two_document_shelf(monkeypatch, chat, tmp_path) -> None:
    _shelf(
        monkeypatch,
        chat,
        tmp_path,
        [
            _doc_row(OWN_NAME, DEPT_OWN, tmp_path, "u-r194-keeper"),
            _doc_row(FOREIGN_NAME, DEPT_FOREIGN, tmp_path, "u-r194-xdept"),
        ],
        indexed=[OWN_NAME, FOREIGN_NAME],
    )


def test_the_flat_list_says_documents_exist_but_are_not_visible(client, monkeypatch, tmp_path):
    """两张脸拆开：数组一字不动，另外补「被挡了几份」的诚实字段，且不点名是哪一份。"""
    import app.api.v1.chat as chat

    _two_document_shelf(monkeypatch, chat, tmp_path)
    _as(client, "xdept")

    body = client.get("/api/v1/documents").json()

    assert body["documents"] == [FOREIGN_NAME], (
        "反证：老调用方读的数组变了——scripts/check_corpus_parity.py 就靠这一枚"
    )
    restricted = body.get("restricted")
    assert restricted, "反证②：平铺出口把「有但你不能看」退回了空数组假话"
    assert restricted["count"] == 1
    assert restricted["reason_codes"], "只报数量不报因由 = 第二张假话"
    assert set(restricted["reason_codes"]) <= STABLE_CODES, "因由必须是稳定码"
    assert HONEST_MARKER in restricted["message"]
    assert set(body) == {"documents", "restricted"}
    leak = _blob(restricted)
    for secret in (BODY_TOKEN, OWN_NAME, OWN_STEM):
        assert secret not in leak, f"反证：成功体点名了被挡的文档（{secret}）"


def test_the_absent_shelf_and_the_locked_shelf_are_not_the_same_answer(
    client, monkeypatch, tmp_path
):
    """反证②常驻：把假脸改回「只给空数组」，这两次响应会逐字相同，本枚当场红。"""
    import app.api.v1.chat as chat

    _shelf(
        monkeypatch,
        chat,
        tmp_path,
        [_doc_row(OWN_NAME, DEPT_OWN, tmp_path, "u-r194-keeper")],
        indexed=[OWN_NAME],
    )
    _as(client, "nodept")
    locked = client.get("/api/v1/documents").json()

    assert locked["documents"] == []
    assert locked.get("restricted"), "「有但你不能看」必须说出来"

    monkeypatch.setattr(chat, "current_documents", lambda *a, **k: [])
    monkeypatch.setattr(chat.retriever, "list_documents", lambda: [])
    absent = client.get("/api/v1/documents").json()

    assert absent["documents"] == []
    assert "restricted" not in absent, "盘上真的一份都没有时，不许凭空造一笔拒绝"
    assert locked != absent, "「这里没有文档」与「有文档，只是你没权看」又长成同一张脸了"


def test_the_flat_list_invents_no_refusal_for_someone_who_sees_everything(
    client, monkeypatch, tmp_path
):
    """正向对照：看得到全部的人不许被凭空造一笔拒绝。"""
    import app.api.v1.chat as chat

    _two_document_shelf(monkeypatch, chat, tmp_path)
    _as(client, "root")

    body = client.get("/api/v1/documents").json()

    assert body["documents"] == [OWN_NAME, FOREIGN_NAME]
    assert "restricted" not in body, "看得见全部的人不许被凭空记一笔拒绝"
    assert set(body) == {"documents"}


def test_the_flat_list_array_keeps_its_own_intersection_rule(client, monkeypatch, tmp_path):
    """没入索引的可见文档仍只由数组负责，不许被冒充成一次权限拒绝。"""
    import app.api.v1.chat as chat

    _shelf(
        monkeypatch,
        chat,
        tmp_path,
        [
            _doc_row(OWN_NAME, DEPT_OWN, tmp_path, "u-r194-keeper"),
            _doc_row(FOREIGN_NAME, DEPT_FOREIGN, tmp_path, "u-r194-xdept"),
        ],
        indexed=[FOREIGN_NAME],
    )
    _as(client, "root")

    body = client.get("/api/v1/documents").json()

    assert body["documents"] == [FOREIGN_NAME], "数组口径未动：可见 ∩ 已索引"
    assert "restricted" not in body, "「能看但没入索引」不是权限拒绝，不许记成被挡"


def test_the_flat_list_counts_with_that_one_verdict_and_not_a_second_pass(
    client, monkeypatch, tmp_path
):
    """判据②：判定与计数一律复用 _classify_document_rows 那一份，不许自己再数一遍。

    把分类器换成「多造两笔假拒绝」的哨兵：出口照单全收才算复用；出口若自己重算，
    这里就会数回 1 而不是 3。同时只许过一遍（第二遍就是第二套判序）。
    """
    import app.api.v1.chat as chat

    _two_document_shelf(monkeypatch, chat, tmp_path)
    real = chat._classify_document_rows
    seen: list[int] = []

    def _spy(*args, **kwargs):
        rows_arg = args[1] if len(args) > 1 else kwargs.get("rows")
        seen.append(len(rows_arg) if rows_arg is not None else -1)
        visible, withheld = real(*args, **kwargs)
        return visible, list(withheld) + [("ghost.txt", "department_scope_denied")] * 2

    monkeypatch.setattr(chat, "_classify_document_rows", _spy)
    _as(client, "xdept")

    body = client.get("/api/v1/documents").json()

    assert seen == [2], f"平铺出口必须只过一遍那份判定，实际每遍的行数是 {seen}"
    assert body["restricted"]["count"] == 3, "计数照分类器的结论，不许就地重算"


def test_the_flat_list_denials_still_reach_the_audit_journal(
    client, monkeypatch, tmp_path, audit_rows
):
    """复用性取证（改前即绿）：平铺出口的文件级拒绝走的就是既有 record_audit 通路。"""
    import app.api.v1.chat as chat
    from app.common.permissions import ACTION_VIEW

    _two_document_shelf(monkeypatch, chat, tmp_path)
    _as(client, "xdept")
    client.get("/api/v1/documents")

    denials = [
        row for row in audit_rows if row["outcome"] == "denied" and row["resource"] == OWN_NAME
    ]
    assert denials, "反证①：平铺出口的文件级拒绝没走既有审计通路"
    assert len(denials) == 1, "一枚拒绝记一笔，不许因为改了出口就重复记账"
    assert denials[0]["action"] == ACTION_VIEW
    assert denials[0]["username"] == "xdept"
    assert BODY_TOKEN not in _blob(denials), "反证：审计里混进了文档正文"


def test_falsification_flat_list_accounting_shares_the_one_pathway(
    client, monkeypatch, tmp_path, audit_rows
):
    """反证①常驻（平铺出口侧）：摘掉通路，拒绝一行也长不出来，而诚实字段必须在。"""
    import app.api.v1.chat as chat

    _two_document_shelf(monkeypatch, chat, tmp_path)
    _as(client, "xdept")
    assert client.get("/api/v1/documents").json()["restricted"]
    assert [row for row in audit_rows if row["outcome"] == "denied"]

    monkeypatch.setattr(chat, "record_audit", lambda *a, **k: {})
    rows_before = len(audit_rows)
    body = client.get("/api/v1/documents").json()

    assert len(audit_rows) == rows_before, "摘掉通路还在长账 = 存在第二套审计形状"
    assert body["restricted"], "说话那半条与留账那半条是两层，摘账不许把话也摘掉"
