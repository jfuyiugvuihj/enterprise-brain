"""R366 · 一条腿问不出，不许整页黑：告警存储拒答与收件箱的接口面。

症状（总控在 `4382443` 立案、基点 `b291324` 现取）：R359 给 `app/api/v1/alerts.py` 的九枚出口加了
`_require_ready_store()`，生产环境而 PG 不在位时回 503 `storage_unavailable` —— 方向是对的，本件
一个字都不回改它。但 `app/notifications/sources.py::alert_candidates` 只把 **403** 折进
`_omitted(SOURCE_ALERT, reason)`，其余原样 `raise`，于是那枚新码一路撞到出口：客户机上
`GET /api/v1/notifications` 从「200 + 悄悄少一条告警腿」变成**整页 503**。一条腿坏了，三格全黑。

判据的形状（每条一枚以上的钉，方向写死在断言里）：

- 甲 生产 + 库不在 ⇒ 收件箱仍 200，告警腿以**既有**那枚 `_omitted(SOURCE_ALERT, <码>)` 的投影形状
  登记缺席（五枚键一枚不多一枚不少），其余各腿的投影与逐行读数逐字不变。
- 乙 零新增错误码、零新增 reason 词：承接的那一枚必须就是那本账自己吐出的 `storage_unavailable`，
  与 `app/api/v1/dashboard.py` / `app/api/v1/notifications.py` / `ErrorEnvelope.code` 同源。这一格
  不靠「我保证没新造」维持：等号右侧的字面量是从 `alerts.py` 现读的，抄来的常量蒙不过去。
- 丙 不许把 503 折成「这一格没有新事项」：`included=True + candidates=0` 与 `included=False +
  reason_code=storage_unavailable` 是两句话，本件把「缺席必须可被调用方读出来」钉成对同一世界
  两种环境的比较，而不是只看一眼投影。这正是 R359 要杀掉的那句假话，不许在收件箱里复活。
- 丁 401 / 403 / 404 现有的折叠行为逐字不变，也没有被顺手「统一」进新写的那一支：读侧只折 403 与
  503 两枚（AST 现取名单），staff 那一格拿到的仍是权限的答案。
- 戊 `app/notifications/inbox.py::can_address` 那一腿问的是「这条告警还开着吗」。404 是「这条已经不
  在了」，回 False 正好把它从账上关掉；503 是「这台机器此刻问不出」，回 False 就等于把一条还开着
  的告警画成已解决 —— 一条被静默吞掉的待办。所以它原样上抛，由出口答它既有那一码。这一支与 404 那
  一支在代码层各自独立（AST 钉：两枚分支不是同一枚语句、那枚元组仍是 401/403/404），端到端也各自
  有脸（503 回执 vs `notification_not_addressable` 回执）。

本件全程离线：不起服务、不连库、不打模型端口、不写 `chroma_db/`。三本账一律钉在内存形状
（`_database_available()` 为假），"库不在" 这一件事由 `APP_ENV=production` 触发 R359 那道闸来达成，
所以本件测的确实是闸与收件箱之间的那一层，而不是另一份替身。
"""
from __future__ import annotations

import ast
import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.api.v1 import alerts as alerts_api
from app.common.auth import create_token
from app.common.authorization import principal_from_request
from app.documents import catalog
from app.main import app
from app.notifications import inbox as inbox_module
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store

REPO = Path(__file__).resolve().parents[1]
#: 本单的记名锚点：与现场读数比等号的只许是锚点，不许是「工作树 vs HEAD」那一类会随提交变空的差集。
BASE = "b291324"

CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
SOURCES_PY = REPO / "app" / "notifications" / "sources.py"
INBOX_PY = REPO / "app" / "notifications" / "inbox.py"
ALERTS_PY = REPO / "app" / "api" / "v1" / "alerts.py"

INBOX_PATH = "/api/v1/notifications"
DISMISS_PATH = "/api/v1/notifications/dismiss"

#: 仓里已有的那一码。本件不新造第四本账：alerts / dashboard / notifications / auth 四枚出口都在吐它。
STORAGE_CODE = "storage_unavailable"
PERMISSION_CODE = "permission_denied"
NOT_ADDRESSABLE = "notification_not_addressable"

DEPT_FINANCE = "r366-finance"
DEPT_HR = "r366-hr"
FINANCE_MANAGER = "r366-finance-manager"
HR_MANAGER = "r366-hr-manager"
FINANCE_STAFF = "r366-finance-staff"

ALERT_ID = 7366
ALERT_NOTIFICATION_ID = f"alert:{ALERT_ID}"
GONE_ALERT_ID = "alert:999999"
SESSION_ID = "sess-r366-a"
APPROVAL_NOTIFICATION_ID = f"approval:{SESSION_ID}"
DOCUMENT_NAME = "r366-plan.pdf"
DOCUMENT_NOTIFICATION_ID = f"document:{DOCUMENT_NAME}#v1"

#: 既有 `_omitted(SOURCE_ALERT, <码>)` 在投影里长成的样子（键名取自 SourceBundle.as_projection，
#: 一件都不新造）。本单只是让第二枚码也走这一扇门，不是另开一扇。
OMITTED_ALERT_LEG = {
    "included": False,
    "reason_code": STORAGE_CODE,
    "candidates": 0,
    "scanned": 0,
    "truncated": False,
}

#: 契约里本单那一节的标题（只取 marker 尺子认的同一枚名字，不抄全文）。
OWN_SECTION_HEADING = "The alert leg may refuse without taking the inbox down with it"


def _account(username: str, department: str, role: str) -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


ACCOUNTS = {
    FINANCE_MANAGER: _account(FINANCE_MANAGER, DEPT_FINANCE, "manager"),
    HR_MANAGER: _account(HR_MANAGER, DEPT_HR, "manager"),
    FINANCE_STAFF: _account(FINANCE_STAFF, DEPT_FINANCE, "staff"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """把这三枚账号喂进鉴权中间件真正用的那一次查询。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def offline_legs(monkeypatch):
    """三本账全钉在内存形状：宿主真起 PG，本件的读数不能分成两半。"""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)


@pytest.fixture(autouse=True)
def document_store(monkeypatch, tmp_path):
    """文档腿用真的离线 catalog，落点搬到 tmp_path（与 R299 同一间屋子）。"""
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(filename: str, *, department: str, owner: str, index_status: str = "indexed") -> str:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        catalog.record_local_document_version(
            filename,
            1,
            department,
            str(stored),
            1,
            owner_id=owner,
            index_status=index_status,
        )
        return filename

    return add


@pytest.fixture()
def world(document_store):
    """一枚三腿各有一条的世界：一轮待批准、一条开着的告警、一篇进了索引的文档。"""
    hitl_store.record_awaiting(SESSION_ID, FINANCE_MANAGER, ["chart"], request_id="req-r366")
    alerts_api._MEM_ALERTS.append(
        {
            "id": ALERT_ID,
            "rule_id": 1,
            "message": "R366 营收跌破阈值",
            "read": False,
            "department": DEPT_FINANCE,
            "created_at": "2026-09-26T09:00:00+08:00",
        }
    )
    document_store(DOCUMENT_NAME, department=DEPT_FINANCE, owner=FINANCE_MANAGER)
    return SimpleNamespace(alert=ALERT_ID, session=SESSION_ID, document=DOCUMENT_NAME)


@pytest.fixture()
def client():
    return TestClient(app)


def _headers(username: str) -> dict:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _produce(monkeypatch) -> None:
    """客户机那一格：`APP_ENV=production` 而库不在位（`_db_ready` 已由 autouse 钉成 False）。"""
    monkeypatch.setenv("APP_ENV", "production")


def _develop(monkeypatch) -> None:
    """裸机那一格：同一枚「库不在」，环境不是生产 —— R359 那支闸在这里不该咬。"""
    monkeypatch.setenv("APP_ENV", "development")


def _inbox(client, username: str = FINANCE_MANAGER):
    return client.get(INBOX_PATH, headers=_headers(username))


def _leg(body: dict, source: str) -> dict:
    return body["sources"][source]


def _ids(body: dict) -> list:
    return sorted(row["id"] for row in body["notifications"])


def _rows_of(body: dict, source: str) -> list:
    return [row for row in body["notifications"] if row["source_type"] == source]


def _request(username: str):
    """一枚够用的 Request 投影：授权那一层只读 `state.username`（app/common/authorization.py:34-47）。"""
    return SimpleNamespace(state=SimpleNamespace(principal=None, username=username), headers={})


def _principal(username: str):
    request = _request(username)
    principal = principal_from_request(request)
    assert principal is not None, f"{username} 解析不出 principal，本件的直调没有意义"
    return principal, request


# --------------------------------------------------------------------------- AST 取证工具
#
# 这一节读的是**本单自己写域内那两枚被改过的文件**与被禁域的 `alerts.py`，用途是结构钉（哪一枚
# 状态码折进哪一支）。期望值不来自被测代码自己：它来自 HTTP 现场读数、`ErrorEnvelope` 那本封闭
# 枚举，或禁域闸口的字面量 —— 三者都不是本件写域内的东西，所以推不出「永远绿」。


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 不在了")


def _status_codes(test_node) -> list:
    """`exc.status_code == 503` -> [503]；`exc.status_code in (401, 403, 404)` -> [401,403,404]。"""
    if not isinstance(test_node, ast.Compare) or not isinstance(test_node.left, ast.Attribute):
        return []
    if test_node.left.attr != "status_code":
        return []
    codes: list[int] = []
    for comparator in test_node.comparators:
        if isinstance(comparator, ast.Tuple):
            for element in comparator.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, int):
                    codes.append(element.value)
        elif isinstance(comparator, ast.Constant) and isinstance(comparator.value, int):
            codes.append(comparator.value)
    return codes


def _first_http_handler(tree: ast.Module, function_name: str):
    handlers = [
        node
        for node in ast.walk(_function(tree, function_name))
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name) and node.type.id == "HTTPException"
    ]
    assert len(handlers) == 1, (
        f"{function_name} 里复核 HTTPException 的地方应有 1 枚，实取 {len(handlers)}："
        "折叠规则换了落点，本件的名单钉就找不到东西了"
    )
    return handlers[0]


def _alert_leg_dispositions() -> dict:
    """`alert_candidates` 的折叠表：{状态码: 'omitted' | 别的处置}。"""
    handler = _first_http_handler(_tree(SOURCES_PY), "alert_candidates")
    dispositions: dict[int, str] = {}
    for statement in handler.body:
        if not isinstance(statement, ast.If):
            continue
        codes = _status_codes(statement.test)
        if not codes:
            continue
        disposition = "omitted" if "_omitted(SOURCE_ALERT," in ast.unparse(statement) else "other"
        for code in codes:
            dispositions[code] = disposition
    return dispositions


def _address_leg_branches() -> dict:
    """`can_address` 告警那一腿的分支表：{状态码: 那枚 If 语句节点}。"""
    handler = _first_http_handler(_tree(INBOX_PY), "can_address")
    branches: dict[int, ast.If] = {}
    for statement in handler.body:
        if not isinstance(statement, ast.If):
            continue
        for code in _status_codes(statement.test):
            branches[code] = statement
    return branches


def _gate_refusal_code() -> str:
    """从禁域 `alerts.py::_require_ready_store` 现场取那一枚 503 的 detail 字面量（它一字未改）。"""
    sites = []
    for node in ast.walk(_function(_tree(ALERTS_PY), "_require_ready_store")):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.exc.keywords}
        status = keywords.get("status_code")
        if isinstance(status, ast.Constant) and status.value == 503:
            sites.append(keywords.get("detail"))
    assert len(sites) == 1, f"存储闸的 503 出口应有 1 枚，实取 {len(sites)}"
    detail = sites[0]
    assert isinstance(detail, ast.Constant) and isinstance(detail.value, str), (
        "闸的 detail 不再是字面量：判据乙的等号右侧失去了可比对象"
    )
    return detail.value


# ====================================================== 判据甲：收件箱不再被一条腿拖整页黑


def test_the_inbox_still_answers_200_when_the_alert_store_refuses(client, world, monkeypatch):
    """判据甲：生产 + 库不在 ⇒ 200。一条腿问不出，不许三格全黑。"""
    _produce(monkeypatch)

    response = _inbox(client)

    assert response.status_code == 200, (
        "一条腿问不出，整页收件箱又黑了 —— 本单收的就是这一格 "
        f"(status={response.status_code} body={response.text})"
    )
    body = response.json()
    assert _leg(body, "alert") == OMITTED_ALERT_LEG
    assert ALERT_NOTIFICATION_ID not in _ids(body)


def test_the_absence_is_registered_in_the_existing_omitted_shape(client, world, monkeypatch):
    """判据甲：登记缺席用的是既有那一枚投影形状，五枚键一枚不多、一枚不少。"""
    _produce(monkeypatch)

    leg = _leg(_inbox(client).json(), "alert")

    assert set(leg) == {"included", "reason_code", "candidates", "scanned", "truncated"}
    assert leg["included"] is False
    assert leg["reason_code"] == STORAGE_CODE
    assert leg["candidates"] == 0 and leg["scanned"] == 0
    assert leg["truncated"] is False, "缺席不是被窗口裁掉，不许冒充 truncated"


def test_an_absence_and_a_quiet_ledger_are_two_different_faces(client, world, monkeypatch):
    """判据丙：「这一格不供数」与「这里真的没有东西」必须各自有脸（前者不许折成后者）。"""
    _develop(monkeypatch)
    supplied = _leg(_inbox(client).json(), "alert")
    assert supplied == {
        "included": True,
        "reason_code": "ok",
        "candidates": 1,
        "scanned": 1,
        "truncated": False,
    }, "世界没铺对：开发态这一腿本该读得到那枚行"

    alerts_api._MEM_ALERTS[0]["status"] = "closed"
    answered = _leg(_inbox(client).json(), "alert")
    _produce(monkeypatch)
    refused = _leg(_inbox(client).json(), "alert")

    # 「查过了，确实没有」这一张脸长这样：included 仍是 True，reason 仍是 ok。
    assert answered == {
        "included": True,
        "reason_code": "ok",
        "candidates": 0,
        "scanned": 1,
        "truncated": False,
    }
    assert refused["included"] is False, (
        "存储拒答被折成了「这一格没有新事项」：R359 要杀的那句假话在收件箱里复活了"
    )
    assert refused != answered, "两种情形长成同一张脸，调用方读不出缺席"
    assert refused["reason_code"] == STORAGE_CODE


def test_the_other_two_legs_keep_reading_the_same_words(client, world, monkeypatch):
    """判据甲：告警腿折出去之后，其余各腿的投影与逐行读数一个字都不许变。"""
    _develop(monkeypatch)
    dev = _inbox(client).json()
    _produce(monkeypatch)
    prod = _inbox(client).json()

    assert _ids(dev) == sorted(
        [APPROVAL_NOTIFICATION_ID, ALERT_NOTIFICATION_ID, DOCUMENT_NOTIFICATION_ID]
    )
    assert _ids(prod) == [
        identifier for identifier in _ids(dev) if identifier != ALERT_NOTIFICATION_ID
    ]
    assert sorted(prod["sources"]) == sorted(dev["sources"]) == ["alert", "approval", "document"]
    for source in ("approval", "document"):
        assert prod["sources"][source] == dev["sources"][source], source
        assert _rows_of(prod, source) == _rows_of(dev, source), source


def test_the_counts_move_by_exactly_the_rows_the_refusal_took_away(client, world, monkeypatch):
    """判据甲/丙：计数只按告警那几枚动；`is_exact` 不许被顺手翻成 False（那是一句新的假话）。"""
    _develop(monkeypatch)
    dev = _inbox(client).json()
    _produce(monkeypatch)
    prod = _inbox(client).json()
    taken = len(_rows_of(dev, "alert"))

    assert taken == 1
    for key in ("total", "unread_total", "returned", "unread_returned"):
        assert prod[key] == dev[key] - taken, key
    assert prod["is_exact"] is dev["is_exact"] is True
    assert (prod["state"], prod["limit"], prod["offset"]) == (
        dev["state"],
        dev["limit"],
        dev["offset"],
    )


def test_the_refused_leg_does_not_launder_the_process_memory_ledger(client, world, monkeypatch):
    """判据甲/丙：拒答那一格连「顺手回内存台账」都不许发生（那正是 R359 要消灭的脸）。"""
    _produce(monkeypatch)

    body = _inbox(client).json()

    assert _leg(body, "alert")["reason_code"] == STORAGE_CODE
    assert not _rows_of(body, "alert")
    _develop(monkeypatch)
    assert ALERT_NOTIFICATION_ID in _ids(_inbox(client).json()), (
        "同一枚行在开发态读不到：本件测的就不是闸，而是世界铺错了"
    )


def test_a_refused_inbox_writes_no_reader_state(client, world, monkeypatch):
    """判据甲：一次 200 的读，不该在生命周期那一层留下一行 —— 缺席不是一次写。"""
    _produce(monkeypatch)

    assert _inbox(client).status_code == 200
    assert state_store._ROWS == {}


def test_the_refusal_is_not_a_permission_artifact_for_a_manager_who_may_read(client, world, monkeypatch):
    """判据甲/丁：有权而库不在 ⇒ 存储的答案；有权而库在（开发态）而部门没行 ⇒ 空台账的答案。

    另部门那位 manager 是反面对照：他这一腿本来就该是 `included=True, candidates=0`。生产态把两位
    都变成 storage 那一格，理由同样只能是「库不在」，不是归属 —— 归属的对照是下面那枚 staff 钉。
    """
    _produce(monkeypatch)
    refused_own = _leg(_inbox(client).json(), "alert")
    refused_other = _leg(_inbox(client, HR_MANAGER).json(), "alert")
    _develop(monkeypatch)
    empty_other = _leg(_inbox(client, HR_MANAGER).json(), "alert")

    assert refused_own == refused_other == OMITTED_ALERT_LEG, (
        "生产无库时两位的脸必须相同：这里挡路的是存储，不是归属"
    )
    assert empty_other == {
        "included": True,
        "reason_code": "ok",
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }


# ============================== 判据丁：401 / 403 / 404 那几张脸一个字没动，也没被顺手统一


def test_a_staff_caller_still_gets_the_permission_answer_not_the_storage_answer(client, world, monkeypatch):
    """判据丁：授权在前、库在不在在后 —— R359 那枚先后顺序在收件箱这一层同样成立。"""
    _produce(monkeypatch)

    body = _inbox(client, FINANCE_STAFF).json()

    assert body["sources"]["alert"] == {
        "included": False,
        "reason_code": PERMISSION_CODE,
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }
    assert body["sources"]["alert"]["reason_code"] != STORAGE_CODE
    assert body["sources"]["approval"]["included"] is True


def test_exactly_two_status_codes_are_folded_into_an_absence_on_the_alert_leg():
    """判据丁：读侧只折 403 与 503 两枚，两枚都折进同一扇 `_omitted`；其余一律原样上抛。

    钉的是名单而不是「有没有新代码」：把 401 / 404 也拖进来（多一枚）、把 503 摘掉（少一枚）、
    把 503 折成别的东西（换处置），三种各红一次。
    """
    assert _alert_leg_dispositions() == {403: "omitted", 503: "omitted"}, (
        f"告警腿的折叠名单换了：{_alert_leg_dispositions()}"
    )


# ============================================ 判据乙：零新增错误码、零新增 reason 字符串


def test_the_absence_carries_the_very_code_the_alert_gate_itself_emits(client, world, monkeypatch):
    """判据乙：承接的那一枚 == 那本账自己吐出的那一枚 == 仓里已有的那一枚。三重等号。"""
    _produce(monkeypatch)

    reason = _leg(_inbox(client).json(), "alert")["reason_code"]

    assert reason == _gate_refusal_code(), "折进来的码与闸口吐出的码不是同一枚"
    assert reason == STORAGE_CODE, "不许新造 alerts_unavailable 之类的第四本账"


def test_no_reason_code_the_alert_leg_can_carry_is_outside_the_ratified_table(client, world, monkeypatch):
    """判据乙：这一腿三张脸（供数 / 权限 / 存储）的 reason_code 全落在封闭枚举里。"""
    annotation = ErrorEnvelope.model_fields["code"].annotation
    ratified = set(get_args(annotation)) | {"ok"}
    assert len(ratified) > 5, f"封闭枚举读空了：{sorted(ratified)}"
    seen: set[str] = set()

    _develop(monkeypatch)
    seen.add(_leg(_inbox(client).json(), "alert")["reason_code"])
    _produce(monkeypatch)
    seen.add(_leg(_inbox(client).json(), "alert")["reason_code"])
    seen.add(_leg(_inbox(client, FINANCE_STAFF).json(), "alert")["reason_code"])

    assert seen == {"ok", PERMISSION_CODE, STORAGE_CODE}, seen
    assert seen <= ratified, f"长出了没进 ErrorEnvelope 的码：{sorted(seen - ratified)}"


# ================== 判据戊：`can_address` 那一腿，「问不出」不许画成「这条已经不在了」


def test_the_inbox_refuses_to_answer_a_question_the_store_cannot_answer(client, world, monkeypatch):
    """判据戊：这台机器问不出 ⇒ 原样上抛 503，绝不回 False。

    回 False 的那张脸叫「这条已经不在你的账上了」，写侧会把它回执成 `notification_not_addressable`
    并就地收兵 —— 一条还开着的告警被静默吞掉。本枚钉的是这条单最容易被「顺手简化」掉的一格。
    """
    _produce(monkeypatch)
    principal, request = _principal(FINANCE_MANAGER)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(inbox_module.can_address(principal, request, ALERT_NOTIFICATION_ID))

    assert caught.value.status_code == 503, (
        f"存储拒答被折成了 {caught.value.status_code}：问不出不是答案"
    )
    assert caught.value.detail == _gate_refusal_code() == STORAGE_CODE


def test_a_row_that_is_genuinely_gone_still_answers_false(client, world, monkeypatch):
    """判据戊的另一半：404 那一支一个字没动 —— 「这条已经不在了」照旧回 False。"""
    _develop(monkeypatch)
    principal, request = _principal(FINANCE_MANAGER)

    assert asyncio.run(inbox_module.can_address(principal, request, GONE_ALERT_ID)) is False
    assert asyncio.run(inbox_module.can_address(principal, request, ALERT_NOTIFICATION_ID)) is True


def test_the_storage_refusal_is_not_wired_into_the_missing_row_branch():
    """判据戊（代码层）：503 与 401/403/404 各自独立成支，且那枚元组仍是三枚原样。

    - 503 那一支的语句体只有一枚裸 `raise`；
    - 404 那一支的语句体是 `return False`，其守卫仍是 `(401, 403, 404)`；
    - 两枚不是同一枚语句（并支即红），名单也少一枚或多一枚都红。
    """
    branches = _address_leg_branches()

    assert sorted(branches) == [401, 403, 404, 503], f"这一腿的状态码名单换了：{sorted(branches)}"
    refusal = branches[503]
    gone = branches[404]
    assert refusal is not gone, "503 被并进了 404 那一支：那正是本单要分开的两张脸"
    assert _status_codes(refusal.test) == [503]
    assert len(refusal.body) == 1 and isinstance(refusal.body[0], ast.Raise)
    assert refusal.body[0].exc is None, "上抛的不是原发那枚异常（换了码就是换了一句假话）"
    assert _status_codes(gone.test) == [401, 403, 404], "那枚元组被顺手改了"
    assert isinstance(gone.body[-1], ast.Return) and gone.body[-1].value.value is False
    assert branches[401] is gone and branches[403] is gone


def test_dismissing_an_alert_while_the_store_refuses_answers_503_and_writes_nothing(client, world, monkeypatch):
    """判据戊（端到端）：写侧把「问不出」照原样说出去，不偷偷收下这枚 dismiss。"""
    _produce(monkeypatch)

    response = client.post(
        DISMISS_PATH, headers=_headers(FINANCE_MANAGER), json={"ids": [ALERT_NOTIFICATION_ID]}
    )

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert state_store.recipient_states(FINANCE_MANAGER) == {}, "拒答之余还偷偷写下一行"


def test_dismissing_a_row_that_is_genuinely_gone_answers_the_not_addressable_receipt(client, world, monkeypatch):
    """判据戊（端到端另一半）：404 那一支的回执仍是逐条给结论的那张脸，一字未动。"""
    _develop(monkeypatch)

    response = client.post(
        DISMISS_PATH, headers=_headers(FINANCE_MANAGER), json={"ids": [GONE_ALERT_ID]}
    )

    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["id"] == GONE_ALERT_ID
    assert result["reason"] == NOT_ADDRESSABLE
    assert result["changed"] is False and result["state"] is None


def test_the_other_legs_keep_their_writes_while_the_alert_leg_refuses(client, world, monkeypatch):
    """整页不许黑：写侧同样只有告警那一腿吃 503，另两腿照常落状态。"""
    _produce(monkeypatch)

    response = client.post(
        DISMISS_PATH, headers=_headers(FINANCE_MANAGER), json={"ids": [APPROVAL_NOTIFICATION_ID]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {"id": APPROVAL_NOTIFICATION_ID, "state": "dismissed", "changed": True, "reason": "applied"}
    ]
    assert state_store.recipient_states(FINANCE_MANAGER) == {APPROVAL_NOTIFICATION_ID: "dismissed"}


# ================================================ 结构钉：不新造探针、不新增码的出口、不换依赖


def test_the_two_files_gained_no_second_storage_probe():
    """修这一格靠的是那本账给出的答案，不是在收件箱里自己再问一次「库在不在」。

    第二份探针正是 AGENTS.md 禁止的平行实现：`_db_ready` 的读者数由 `test_r246` 按 AST 管，
    这里再钉一层本件写域内的形状 —— 也不许长出新的 Chroma 依赖（向量库口径已定 PGVector）。
    """
    for path in (SOURCES_PY, INBOX_PY):
        text = path.read_text(encoding="utf-8")
        assert "_db_ready" not in text, f"{path.name} 直接读了 auth 的就绪旗标"
        assert "_database_available" not in text, f"{path.name} 自己算了一遍库在不在"
        assert "chromadb" not in text.lower(), f"{path.name} 长出了新的 Chroma 依赖"


def test_the_two_files_emit_no_httpexception_of_their_own():
    """判据乙：这两枚文件只承接别人给出的码，不自己吐码（自己吐就是第四本账的入口）。"""
    for path in (SOURCES_PY, INBOX_PY):
        assert "HTTPException(" not in path.read_text(encoding="utf-8"), (
            f"{path.name} 里出现了新的 HTTPException 出口"
        )


# ============================================================== 契约：文末追加一节，历史一字不动


def _git_show(revision: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"{revision}:{relative}"],
        capture_output=True,
        check=True,
    ).stdout


def _as_blob_text(raw: bytes) -> str:
    """一律落到 git blob 那一层（LF）比对：本仓 `core.autocrlf=true`，checkout 层与 blob 层两个形状。"""
    return raw.decode("utf-8").replace("\r\n", "\n")


#: 契约那一节里必须出现的字样。缺任一枚 = 口径只写在代码注释里，下一个人只能靠猜。
CONTRACT_MARKERS = (
    "storage_unavailable",
    "_omitted",
    "reason_code",
    "can_address",
    "404",
    "503",
    "Zero new error code",
    "return `False`",
    "sources.alert",
)


def _own_contract_section() -> str:
    text = _as_blob_text(CONTRACT.read_bytes())
    marker = "\n## " + OWN_SECTION_HEADING
    assert text.count(marker) == 1, f"本单那一节应有 1 枚，实得 {text.count(marker)}"
    start = text.index(marker)
    following = text.find("\n## ", start + len(marker))
    return text[start:following if following != -1 else len(text)]


def test_the_contract_appends_one_section_and_deletes_nothing():
    """三笔账都与提交先后无关：① 前缀等式（历史一字不动）② 长度变长（真写了东西）③ 本单那枚节标题恰一枚。

    🔴 不写「`git diff --numstat` 删除列为 0」那一类拿工作树与 HEAD 比的断言（总控一提交就成空 diff
    假红），也不写「全仓 `## ` 节数 == 基点 + 1」（本单开工到交工之间兄弟单也在追加）。同一条病本仓
    已裁过 R346 / R351 / R340 / R354 四回，不许有第五回。
    """
    base = _as_blob_text(_git_show(BASE, "docs/api/contract-v1.md"))
    now = _as_blob_text(CONTRACT.read_bytes())

    assert now.startswith(base), "契约不是纯追加：文末之前的每一个字都不许动"
    assert len(now) > len(base), "契约没长东西：本单一格都没写"
    assert now[len(base):].count("\n## " + OWN_SECTION_HEADING) == 1, "本单那一节在追加段里恰一枚"
    assert now.count("\n## ") >= base.count("\n## ") + 1, "一节都没长出来"


def test_the_new_contract_section_says_which_face_lives_where():
    """契约把两张脸写清：读侧折进 `_omitted`，写侧那一腿对 503 上抛而不是回 False。"""
    section = _own_contract_section()

    for marker in CONTRACT_MARKERS:
        assert marker in section, f"契约那一节没提 {marker}"
    assert "401, 403, 404" in section, "契约没写明那枚元组仍是原样三枚"


def test_the_contract_bytes_stay_in_the_repository_shape():
    blob = CONTRACT.read_bytes()
    assert blob[:3] != b"\xef\xbb\xbf", "契约被写成带 BOM"
    assert blob.count(b"\n") == blob.count(b"\r\n"), "追加引入了 lone LF"
    assert blob.decode("utf-8").count("\ufffd") == 0, "契约里出现 U+FFFD：编码被写坏过"


def test_every_delivered_file_keeps_the_repository_line_endings():
    """本件写域内三枚文件的字节形状：每一个 LF 都在 CRLF 里、无 BOM、严格 UTF-8 可解码。"""
    for path in (SOURCES_PY, INBOX_PY, CONTRACT):
        blob = path.read_bytes()
        assert blob[:3] != b"\xef\xbb\xbf", f"{path.name} 带上了 BOM"
        assert blob.count(b"\n") == blob.count(b"\r\n"), (
            f"{path.name} 里有 lone LF"
        )
        blob.decode("utf-8")
