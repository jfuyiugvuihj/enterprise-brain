# -*- coding: utf-8 -*-
"""R373 · 另外两条腿也不许把整页收件箱拖黑：审批账本缺表、文档账本拒答。

症状（总控在 `a9762df` 并树的 R366 回执里点名移交，基点 `796540e` 现取）：R366 只把**告警腿**在
「存储问不出」时折成一条可读的缺席，它自己报出另外两条腿是同一种黑。收件箱是三条腿共用一个出口
（`app/notifications/inbox.py::collect` 把三枚源串起来，一枚抛错整页上抛），于是：

- 审批腿：`sources.py::approval_candidates` 与 `inbox.py::can_address` 各有一处直调
  `pending_approvals.open_items`，此前一枚 except 都没有。PG 起着而 `0008` 那张表不在 ⇒ 领域异常
  `PendingApprovalStoreMissing`（定义 `app/storage/pending_approvals.py:140`，抛点 `:152`，经
  `:371 _require_table` 到 `open_items`）一路撞到出口。本仓 `app/**` 零 exception_handler
  （`git grep exception_handler app` exit=1），于是客户机上 `GET /api/v1/notifications` 既不是 503
  也不是 JSON 信封，而是**裸 500 `Internal Server Error`** —— 本班在基点字节上现场量到的。
  对照组：同一枚账本缺表错在 `chat.py::hitl_pending`（`:3034`）与 `dashboard.py::_pending_count`
  （`:149`）各被翻成 503 `storage_unavailable`。同一件事在别的屏说 503，在收件箱说 500。
- 文档腿：两个文件各有一处直调 `chat.list_document_catalog`，同样零 except。本班实测它今天**不会**
  因存储问题抛到收件箱这一层：`app/documents/catalog.py::current_documents`（`:709-724`）把 SQL 层
  的失败整个 `except Exception` 折成一次本地目录扫描，于是缺表/缺列在收件箱里长出的脸是
  `included=True / reason_code=ok / scanned=0` —— 那不是 500，那是「已经扫过而且很干净」这句假话。
  洗的那一层在 catalog 里，不在本单写域（已具名上报）；本单在这一腿接的是**同一道边界**：这一本账
  一旦回 503，这一腿折成缺席，其余两腿逐字照读，401 那一支一字不动。

判据的形状（每条一枚以上的钉，方向写死在断言里）：

- 甲 任一条腿的存储拒答都不许把整页打成 500：折成该腿既有 `_omitted(SOURCE_*, <码>)` 的缺席投影
  （五枚键一枚不多一枚不少），其余两条腿的投影与逐行读数逐字不变；两条腿一起坏也仍然是 200。
- 乙 零新增错误码、零新增 reason 词：折进去的那一枚必须与那本账自己给出的 `storage_unavailable`
  相等，等号右侧从禁域 `dashboard.py::_pending_count` 与 `chat.py::hitl_pending` 的 AST 现取，
  不手抄；三枚源全部可能的 reason 取值都落在 `ErrorEnvelope.code` 那本封闭枚举里；`sources.py`
  里那一枚字面量的出现次数改前改后都是 1（本单把 R366 那处兜底提成一枚常量复用，零新增抄写点）。
- 丙 「这一格不供数」与「这一类今天没有事」必须两张脸：同一世界读两次，缺席投影与安静账本的投影
  必须不等（审批腿与文档腿各一枚，形状照 R366 的两脸钉）。
- 丁 权限那一支一字不动：401 / 403 / 404 的既有语义与既有投影保持；折叠名单各腿自行派生并钉死 ——
  告警腿 {403, 503}（R366 的账，本单一格未动）、文档腿 {503}、审批腿按**类型**接而不是按状态码接。
  把 403 塞进文档腿的名单，本件必红（刀三）。
- 戊 写路径不许静默吞：`can_address` 问的是「这一轮挂起还在不在」，账本缺表时回 False 就等于把一条
  还挂着的审批画成已解决，所以本件钉的是「照旧上抛 + 一枚状态都不写 + 拿不到 200 逐条回执」；文档
  腿那一支钉的是「存储与鉴权拒答都不折成 False」。出口把那枚上抛答成 503 需要改
  `app/api/v1/notifications.py`（本单写域外），已具名上报，见回执。
- 己 反证刀四把，全部走 `tests/_temp_edit_overlay.py` 那台影子根：盘上被跟踪文件全程只读，进出各量
  一次 sha256 并断言相等；同一扇窗里 R366 的告警腿两枚钉照旧为绿。

本件全程离线：不起服务、不连库、不打模型端口、不写 `chroma_db/`。「库拒答」这一件事在审批腿由
`_database_available()` 为真 + 一张不存在的表达成（与 `tests/test_hitl_pending.py:697 _no_table`
同一间屋子），在文档腿由出口自己会吐的那枚 503 达成 —— 本班不用替身假装 catalog 已经会拒答。
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import ErrorEnvelope
from app.api.v1 import alerts as alerts_api
from app.api.v1 import chat as chat_api
from app.common.auth import create_token
from app.common.authorization import principal_from_request
from app.documents import catalog
from app.api.v1 import notifications as notifications_api
from app.main import app
from app.notifications import inbox as inbox_module
from app.notifications import sources as sources_module
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store
from tests import _temp_edit_overlay as overlay

REPO = Path(__file__).resolve().parents[1]
#: 本单的记名锚点：与现场读数比等号的是它，不是「工作树 vs HEAD」那一类会随提交变空的差集。
BASE = "796540e"

SOURCES_PY = REPO / "app" / "notifications" / "sources.py"
INBOX_PY = REPO / "app" / "notifications" / "inbox.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"
DASHBOARD_PY = REPO / "app" / "api" / "v1" / "dashboard.py"
CHAT_PY = REPO / "app" / "api" / "v1" / "chat.py"

INBOX_PATH = "/api/v1/notifications"
DISMISS_PATH = "/api/v1/notifications/dismiss"

#: 仓里已有的那一码。等号右侧由本件从禁域出口的 AST 现取（见 _storage_code_the_approval_ledger_emits），
#: 这一行只是「与那两处出口同源」的第三重对照，不是本件抄下来的期望值。
STORAGE_CODE = "storage_unavailable"
PERMISSION_CODE = "permission_denied"
NOT_ADDRESSABLE = "notification_not_addressable"

DEPT_FINANCE = "r373-finance"
DEPT_HR = "r373-hr"
FINANCE_MANAGER = "r373-finance-manager"
HR_MANAGER = "r373-hr-manager"
FINANCE_STAFF = "r373-finance-staff"

ALERT_ID = 7373
ALERT_NOTIFICATION_ID = f"alert:{ALERT_ID}"
SESSION_ID = "sess-r373-a"
APPROVAL_NOTIFICATION_ID = f"approval:{SESSION_ID}"
DOCUMENT_NAME = "r373-plan.pdf"
DOCUMENT_NOTIFICATION_ID = f"document:{DOCUMENT_NAME}#v1"

#: 既有 `_omitted(SOURCE_*, <码>)` 在投影里长成的样子（键名取自 SourceBundle.as_projection，一件
#: 都不新造）。本单只是让另外两条腿也能走这一扇门，不是另开一扇。
OMITTED_APPROVAL_LEG = {
    "included": False,
    "reason_code": STORAGE_CODE,
    "candidates": 0,
    "scanned": 0,
    "truncated": False,
}
OMITTED_DOCUMENT_LEG = OMITTED_APPROVAL_LEG

#: 契约里本单那一节的标题（只取 marker 尺子认的同一枚名字，不抄全文）。
OWN_SECTION_HEADING = "Either remaining leg may refuse without taking the inbox down"


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
    """文档腿用真的离线 catalog，落点搬到 tmp_path（与 R299/R366 同一间屋子）。"""
    root = tmp_path / "documents"
    root.mkdir()
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root))

    def add(filename: str, *, department: str, owner: str, index_status: str = "indexed") -> str:
        stored = root / catalog.build_storage_name(filename, 1)
        stored.write_text("收入 成本\n100 80\n", encoding="utf-8")
        catalog.record_local_document_version(
            filename, 1, department, str(stored), 1, owner_id=owner, index_status=index_status,
        )
        return filename

    return add


@pytest.fixture()
def world(document_store):
    """一枚三腿各有一条的世界：一轮待批准、一条开着的告警、一篇进了索引的文档。"""
    hitl_store.record_awaiting(SESSION_ID, FINANCE_MANAGER, ["chart"], request_id="req-r373")
    alerts_api._MEM_ALERTS.append(
        {
            "id": ALERT_ID,
            "rule_id": 1,
            "message": "R373 营收跌破阈值",
            "read": False,
            "department": DEPT_FINANCE,
            "created_at": "2026-09-27T09:00:00+08:00",
        }
    )
    document_store(DOCUMENT_NAME, department=DEPT_FINANCE, owner=FINANCE_MANAGER)
    return SimpleNamespace(alert=ALERT_ID, session=SESSION_ID, document=DOCUMENT_NAME)


@pytest.fixture()
def client():
    """看得到真实出口的客户端：未处理的异常必须作为 500 读进来，而不是改写成 Python 回溯。

    本件钉的就是「客户机上看到哪张脸」，所以 5xx 要按状态码断言；`_inbox_body` 那枚把手把状态码
    连同 body 一起写进失败原文，红的时候读得到是哪一格黑了。
    """
    return TestClient(app, raise_server_exceptions=False)


def _inbox_body(client, username: str = FINANCE_MANAGER) -> dict:
    """读一次收件箱并把「整页黑了」钉成一句可读的断言，而不是一枚 ValueError。"""
    response = _inbox(client, username)
    assert response.status_code == 200, (
        f"整页收件箱黑了：status={response.status_code} body={response.text[:160]}"
    )
    return response.json()


def _headers(username: str = FINANCE_MANAGER) -> dict:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _inbox(client, username: str = FINANCE_MANAGER) -> object:
    return client.get(INBOX_PATH, headers=_headers(username))


def _leg(body: dict, source: str) -> dict:
    return body["sources"][source]


def _ids(body: dict) -> list:
    return sorted(row["id"] for row in body["notifications"])


def _rows_of(body: dict, source: str) -> list:
    return [row for row in body["notifications"] if row["source_type"] == source]


def _request(username: str = FINANCE_MANAGER):
    """一枚够用的 Request 投影：授权那一层只读 `state.username`。"""
    return SimpleNamespace(state=SimpleNamespace(principal=None, username=username), headers={})


def _principal(username: str = FINANCE_MANAGER):
    request = _request(username)
    principal = principal_from_request(request)
    assert principal is not None, f"{username} 解析不出 principal，本件的直调没有意义"
    return principal, request


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _AbsentTableConnection:
    """`_require_table` 问 to_regclass，这张表不在 —— 与 test_hitl_pending.py:681 同一间屋子。"""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        return _Result({"table_name": None})

    def close(self):
        pass


class _DriverMissingConnection:
    """另一张脸：驱动都没有。那是裸 RuntimeError，不是那枚具名子类，所以不许被折进缺席。"""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        raise RuntimeError("PostgreSQL driver is unavailable")

    def close(self):
        pass


def _approval_ledger_missing(monkeypatch) -> None:
    """PG 起着而 `pending_approvals` 那张表不在 —— 审批腿今天唯一会撞穿出口的那一格。"""
    monkeypatch.setattr(hitl_store, "_database_available", lambda: True)
    monkeypatch.setattr(hitl_store, "_conn", lambda: _AbsentTableConnection())


def _approval_ledger_has_no_driver(monkeypatch) -> None:
    monkeypatch.setattr(hitl_store, "_database_available", lambda: True)
    monkeypatch.setattr(hitl_store, "_conn", lambda: _DriverMissingConnection())


def _document_ledger_refuses(monkeypatch, status_code: int = 503, detail: str = STORAGE_CODE) -> None:
    """文档腿的拒答由那一本账自己给出：本件把出口会吐的那枚 503 原样递进来，不另装探针。"""

    def refuse(_request):
        raise HTTPException(status_code=status_code, detail=detail)

    monkeypatch.setattr(chat_api, "list_document_catalog", refuse)


# --------------------------------------------------------------------------- AST 取证工具


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


def _http_handlers(tree: ast.Module, function_name: str) -> list:
    return [
        node
        for node in ast.walk(_function(tree, function_name))
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "HTTPException"
    ]


def _fold_roster_text(text: str, function_name: str, source_constant: str) -> dict:
    """某条腿的折叠表：{状态码: 'omitted' | 别的处置}。名单由代码派生，不写死在本件里。

    尺子读的是**文本**，所以它既能量盘上被跟踪的那份字（判据丁的钉），也能量反证窗里的影子副本
    （刀三要的正是后者：影子根从不改盘，读盘的 AST 钉当然不会跟着红）。
    """
    handlers = _http_handlers(ast.parse(text), function_name)
    assert len(handlers) == 1, (
        f"{function_name} 里承接 HTTPException 的地方应有 1 枚，实取 {len(handlers)}："
        "折叠规则换了落点，本件的名单钉就找不到东西了"
    )
    dispositions: dict[int, str] = {}
    for statement in handlers[0].body:
        if not isinstance(statement, ast.If):
            continue
        codes = _status_codes(statement.test)
        if not codes:
            continue
        disposition = (
            "omitted" if f"_omitted({source_constant}," in ast.unparse(statement) else "other"
        )
        for code in codes:
            dispositions[code] = disposition
    return dispositions

def _assert_fold_roster(text: str, function_name: str, source_constant: str, expected: dict) -> None:
    """把「名单恰好是这几枚」那句断言交给文本尺，盘上与窗内共用同一句话。"""
    roster = _fold_roster_text(text, function_name, source_constant)
    assert roster == expected, f"{function_name} 的折叠名单换了：{roster}"


def _approval_fold_type(path: Path = SOURCES_PY) -> str:
    """审批腿读侧承接的那一枚**类型**全名 —— 本件按类型钉，不按「有没有 try」钉。"""
    handlers = [
        node
        for node in ast.walk(_function(_tree(path), "approval_candidates"))
        if isinstance(node, ast.ExceptHandler)
    ]
    assert len(handlers) == 1, (
        f"approval_candidates 的承接应有 1 枚，实取 {len(handlers)}：多一枚就是并了别种的错，"
        "少一枚就是那条腿又裸奔了"
    )
    handler = handlers[0]
    assert handler.name is None, "承接不留别名：别名一旦被读出去，就是给吞错留口子"
    return ast.unparse(handler.type) if handler.type is not None else "BARE"


def _storage_code_the_approval_ledger_emits() -> str:
    """从禁域出口现取那一枚 503 的 detail 字面量：账本缺表在别人那儿怎么答，这里就怎么登记。

    两处各取一次并要求相等 —— 抄来的常量蒙不过这两枚 AST 读数。
    """
    sites = []
    pairs = ((_tree(DASHBOARD_PY), "_pending_count"), (_tree(CHAT_PY), "hitl_pending"))
    for tree, function_name in pairs:
        for node in ast.walk(_function(tree, function_name)):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.exc.keywords}
            status = keywords.get("status_code")
            if isinstance(status, ast.Constant) and status.value == 503:
                sites.append((function_name, keywords.get("detail")))
    assert len(sites) == 2, f"账本缺表那两枚 503 出口应有 2 处，实取 {len(sites)}"
    details = []
    for function_name, detail in sites:
        assert isinstance(detail, ast.Constant) and isinstance(detail.value, str), (
            f"{function_name} 那枚闸的 detail 不再是字面量：判据乙的等号右侧失去了可比对象"
        )
        details.append(detail.value)
    assert details[0] == details[1], f"两处出口对同一件事给了两个码：{details}"
    return details[0]


# ================================================== 判据甲：一条腿问不出，不许整页黑


def test_the_inbox_still_answers_200_when_the_approval_ledger_is_missing(
    client, world, monkeypatch
):
    """判据甲：审批账本缺表 ⇒ 收件箱仍 200。这就是本单收的那一格裸 500。"""
    _approval_ledger_missing(monkeypatch)

    response = _inbox(client)

    assert response.status_code == 200, (
        "一条腿问不出，整页收件箱又黑了 —— 本单收的就是这一格 "
        f"(status={response.status_code} body={response.text})"
    )
    body = response.json()
    assert _leg(body, "approval") == OMITTED_APPROVAL_LEG
    assert APPROVAL_NOTIFICATION_ID not in _ids(body)


def test_the_inbox_still_answers_200_when_the_document_ledger_refuses(
    client, world, monkeypatch
):
    """判据甲：文档账本回 503 ⇒ 同一扇门，缺席登记，整页仍 200。"""
    _document_ledger_refuses(monkeypatch)

    response = _inbox(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert _leg(body, "document") == OMITTED_DOCUMENT_LEG
    assert DOCUMENT_NOTIFICATION_ID not in _ids(body)


def test_two_legs_refusing_at_once_still_leave_a_readable_inbox(client, world, monkeypatch):
    """三条腿共用一个出口，所以两条一起坏也只是两格缺席，不是整页黑。"""
    _approval_ledger_missing(monkeypatch)
    _document_ledger_refuses(monkeypatch)

    body = _inbox_body(client)

    assert _leg(body, "approval") == OMITTED_APPROVAL_LEG
    assert _leg(body, "document") == OMITTED_DOCUMENT_LEG
    assert _leg(body, "alert") == {
        "included": True,
        "reason_code": "ok",
        "candidates": 1,
        "scanned": 1,
        "truncated": False,
    }, "两腿缺席时，还在答话的那一条必须逐字照读"
    assert _ids(body) == [ALERT_NOTIFICATION_ID]


def test_the_absent_approval_leg_uses_the_existing_omitted_projection_shape(
    client, world, monkeypatch
):
    """判据甲：缺席登记用的是既有那枚投影形状，五枚键一枚不多、一枚不少。"""
    _approval_ledger_missing(monkeypatch)

    leg = _leg(_inbox_body(client), "approval")

    assert set(leg) == {"included", "reason_code", "candidates", "scanned", "truncated"}
    assert leg["included"] is False
    assert leg["reason_code"] == STORAGE_CODE
    assert leg["candidates"] == 0 and leg["scanned"] == 0
    assert leg["truncated"] is False, "缺席不是被窗口裁掉，不许冒充 truncated"


def test_the_absent_document_leg_uses_the_existing_omitted_projection_shape(
    client, world, monkeypatch
):
    """判据甲：同一枚形状，文档腿一份，不另开一扇。"""
    _document_ledger_refuses(monkeypatch)

    leg = _leg(_inbox_body(client), "document")

    assert set(leg) == {"included", "reason_code", "candidates", "scanned", "truncated"}
    assert leg["included"] is False
    assert leg["reason_code"] == STORAGE_CODE
    assert leg["truncated"] is False


def test_the_other_two_legs_keep_reading_the_same_words_when_approval_refuses(
    client, world, monkeypatch
):
    """判据甲：审批腿折出去之后，其余两腿的投影与逐行读数一个字都不许变。"""
    healthy = _inbox_body(client)
    _approval_ledger_missing(monkeypatch)
    refused = _inbox_body(client)

    assert _ids(healthy) == sorted(
        [APPROVAL_NOTIFICATION_ID, ALERT_NOTIFICATION_ID, DOCUMENT_NOTIFICATION_ID]
    )
    assert _ids(refused) == [i for i in _ids(healthy) if i != APPROVAL_NOTIFICATION_ID]
    for source in ("alert", "document"):
        assert refused["sources"][source] == healthy["sources"][source], source
        assert _rows_of(refused, source) == _rows_of(healthy, source), source


def test_the_other_two_legs_keep_reading_the_same_words_when_document_refuses(
    client, world, monkeypatch
):
    """判据甲：文档腿折出去之后，其余两腿照旧逐字读数。"""
    healthy = _inbox_body(client)
    _document_ledger_refuses(monkeypatch)
    refused = _inbox_body(client)

    assert _ids(refused) == [i for i in _ids(healthy) if i != DOCUMENT_NOTIFICATION_ID]
    for source in ("approval", "alert"):
        assert refused["sources"][source] == healthy["sources"][source], source
        assert _rows_of(refused, source) == _rows_of(healthy, source), source


def test_the_counts_move_by_exactly_the_rows_the_refusal_took_away(client, world, monkeypatch):
    """判据甲/丙：计数只按被折掉那一腿动；`is_exact` 不许被顺手翻成 False。"""
    healthy = _inbox_body(client)

    _approval_ledger_missing(monkeypatch)
    approval_out = _inbox_body(client)
    assert approval_out["total"] == healthy["total"] - 1
    assert approval_out["is_exact"] is healthy["is_exact"] is True, (
        "缺席不是「被窗口裁过」，把 is_exact 翻成 False 又是一句新的假话"
    )

    _document_ledger_refuses(monkeypatch)
    both_out = _inbox_body(client)
    assert both_out["total"] == healthy["total"] - 2
    assert both_out["is_exact"] is True
    assert (both_out["state"], both_out["limit"], both_out["offset"]) == (
        healthy["state"],
        healthy["limit"],
        healthy["offset"],
    )


def test_a_refused_inbox_writes_no_reader_state(client, world, monkeypatch):
    """判据甲：一次 200 的读不该在生命周期那一层留下一行 —— 缺席不是一次写。"""
    _approval_ledger_missing(monkeypatch)
    _document_ledger_refuses(monkeypatch)

    assert _inbox(client).status_code == 200
    assert state_store._ROWS == {}


# ==================================== 判据丙：缺席不许被洗成「已扫过而且很干净」


def test_an_absent_approval_ledger_and_a_quiet_one_are_two_different_faces(
    client, world, monkeypatch
):
    """判据丙：「账本在答但没有待办」与「账本拒答」必须两张脸（R366 同一形状）。"""
    hitl_store._MEM_ROWS.clear()
    answered = _leg(_inbox_body(client), "approval")
    assert answered == {
        "included": True,
        "reason_code": "ok",
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }, "世界没铺对：库在答而确实没有待办，这一腿本该交这张脸"

    _approval_ledger_missing(monkeypatch)
    refused = _leg(_inbox_body(client), "approval")

    assert refused != answered, "两种情形长成同一张脸，调用方读不出缺席"
    assert refused["included"] is False, (
        "存储拒答被折成了「这一格没有新事项」：R359 要杀的那句假话在收件箱里复活了"
    )
    assert refused["reason_code"] == STORAGE_CODE


def test_an_absent_document_ledger_and_a_quiet_one_are_two_different_faces(
    client, world, monkeypatch
):
    """判据丙：文档腿同一张对照 —— 目录里没有可检索的文档，与目录拒答，不是同一句话。"""
    world_row = _leg(_inbox_body(client), "document")
    assert world_row["candidates"] == 1, "世界没铺对：那篇已入索引的文档本该被读到"

    quiet = _leg(_inbox_body(client, HR_MANAGER), "document")
    assert quiet == {
        "included": True,
        "reason_code": "ok",
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }, f"另一位收件人这一腿本该是「扫过了，没有」：{quiet}"

    _document_ledger_refuses(monkeypatch)
    refused = _leg(_inbox_body(client, HR_MANAGER), "document")

    assert refused != quiet, "两种情形长成同一张脸，调用方读不出缺席"
    assert refused["included"] is False
    assert refused["reason_code"] == STORAGE_CODE


# ======================================= 判据乙：零新增错误码、零新增 reason 词


def test_the_absence_carries_the_very_code_the_approval_gate_itself_emits(
    client, world, monkeypatch
):
    """判据乙：折进来的那一枚 == 那本账在别的屏给出的那一枚 == 仓里已有的那一枚。"""
    _approval_ledger_missing(monkeypatch)

    reason = _leg(_inbox_body(client), "approval")["reason_code"]

    assert reason == _storage_code_the_approval_ledger_emits(), "与出口给出的码不是同一枚"
    assert reason == STORAGE_CODE, "不许新造 ledger_missing 之类的第四本账"


def test_the_document_absence_carries_the_code_the_refusal_itself_named(
    client, world, monkeypatch
):
    """判据乙：文档腿登记的说法就是从那一本账的 detail 上来的，不是本文件另起的。"""
    _document_ledger_refuses(monkeypatch, detail=_storage_code_the_approval_ledger_emits())

    leg = _leg(_inbox_body(client), "document")

    assert leg["reason_code"] == _storage_code_the_approval_ledger_emits()
    assert leg["reason_code"] == STORAGE_CODE


def test_no_reason_code_any_leg_can_carry_is_outside_the_ratified_table(client, world, monkeypatch):
    """判据乙：三枚源全部可能的 reason_code 都落在 ErrorEnvelope 那本封闭枚举里。"""
    ratified = set(get_args(ErrorEnvelope.model_fields["code"].annotation)) | {"ok"}
    assert len(ratified) > 5, f"封闭枚举读空了：{sorted(ratified)}"
    seen: set[str] = set()

    for source in ("approval", "alert", "document"):
        seen.add(_leg(_inbox_body(client), source)["reason_code"])
    _approval_ledger_missing(monkeypatch)
    seen.add(_leg(_inbox_body(client), "approval")["reason_code"])
    _document_ledger_refuses(monkeypatch)
    seen.add(_leg(_inbox_body(client), "document")["reason_code"])
    seen.add(_leg(_inbox_body(client, FINANCE_STAFF), "alert")["reason_code"])

    assert seen == {"ok", PERMISSION_CODE, STORAGE_CODE}, seen
    assert seen <= ratified, f"长出了没进 ErrorEnvelope 的码：{sorted(seen - ratified)}"


def test_the_storage_word_is_written_once_in_sources(world, monkeypatch):
    """判据乙：兜底被提成一枚常量复用，盘上那枚字面量的出现次数改前改后都是 1。

    这条钉的是「没有新增抄写点」：三处折叠都指同一枚常量，下一个人要改说法只能改那一处。
    """
    text = SOURCES_PY.read_text(encoding="utf-8")

    assert text.count("'" + STORAGE_CODE + "'") == 1, "存储那一枚说法在本文件里被抄了第二遍"
    body = ast.unparse(_function(_tree(SOURCES_PY), "approval_candidates"))
    assert STORAGE_CODE not in body, "折叠点自己不许再写一遍字面量"
    assert "STORAGE_UNAVAILABLE" in body, "审批腿折的是那枚共用的常量"


# ================= 判据丁：折叠名单各腿自派生；权限那一支一字不动；捕获按类型


def test_the_document_leg_fold_roster_is_exactly_one_status_code():
    """判据丁：文档腿只折 503。401 没被顺手并进来，403 也没有（它今天根本没有那一支）。"""
    _assert_fold_roster(
        SOURCES_PY.read_text(encoding="utf-8"), "document_candidates", "SOURCE_DOCUMENT",
        {503: "omitted"},
    )


def test_the_alert_leg_fold_roster_is_still_exactly_two_status_codes():
    """判据丁：R366 那两枚一格没动 —— 本单不许把别人的账并进来，也不许改短告警腿的名单。"""
    _assert_fold_roster(
        SOURCES_PY.read_text(encoding="utf-8"), "alert_candidates", "SOURCE_ALERT",
        {403: "omitted", 503: "omitted"},
    )


def test_the_approval_leg_fold_is_typed_and_not_a_broad_catch():
    """判据丁/乙：审批腿按类型接，只接那一枚具名领域异常。

    钉的是全名，不是「有没有 except」：换成 Exception、RuntimeError，或把 HTTPException 也拖进来，
    本枚各红一次 —— 那三种都会顺带吞掉驱动缺失、列错、连接错。
    """
    assert _approval_fold_type() == "pending_approvals.PendingApprovalStoreMissing"


def test_the_named_exception_is_a_runtime_error_subclass_but_not_its_inverse():
    """判据丁的类型边界凭据：捕获这枚子类吞不到父类那一支，也吞不到 psycopg 的错。"""
    assert issubclass(hitl_store.PendingApprovalStoreMissing, RuntimeError)
    assert not isinstance(
        RuntimeError("PostgreSQL driver is unavailable"),
        hitl_store.PendingApprovalStoreMissing,
    )
    import psycopg

    assert not issubclass(psycopg.errors.UndefinedColumn, hitl_store.PendingApprovalStoreMissing)
    assert not issubclass(psycopg.OperationalError, hitl_store.PendingApprovalStoreMissing)


def test_a_driver_that_is_not_there_is_not_folded_into_an_absence(client, world, monkeypatch):
    """判据丁：那本账连驱动都缺 = 另一种错，本文件不接，整页照旧黑。

    这一格是「按类型接」的代价，本件把它钉成看得见的边界，而不是藏在注释里。
    """
    _approval_ledger_has_no_driver(monkeypatch)

    response = _inbox(client)

    assert response.status_code == 500, (
        f"驱动缺失被折成了可读缺席：本单的捕获边界不覆盖这一格 ({response.status_code})"
    )


def test_a_staff_caller_still_gets_the_permission_answer_not_the_storage_answer(
    client, world, monkeypatch
):
    """判据丁：403 与存储错不并支 —— 权限的答案与存储的答案各自留名，即使两条腿同时出问题。"""
    _approval_ledger_missing(monkeypatch)

    body = _inbox_body(client, FINANCE_STAFF)

    assert body["sources"]["alert"] == {
        "included": False,
        "reason_code": PERMISSION_CODE,
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }
    assert body["sources"]["alert"]["reason_code"] != STORAGE_CODE
    assert body["sources"]["approval"] == OMITTED_APPROVAL_LEG


def test_a_403_from_the_document_ledger_is_not_folded_into_an_absence(client, world, monkeypatch):
    """判据丁：把 403 塞进文档腿名单，本枚先红 —— 拒答与无权是两句话。"""
    _document_ledger_refuses(monkeypatch, status_code=403, detail=PERMISSION_CODE)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(sources_module.document_candidates(_request()))

    assert caught.value.status_code == 403
    assert caught.value.detail == PERMISSION_CODE


def test_a_401_from_the_document_ledger_still_keeps_its_own_face(client, world, monkeypatch):
    """判据丁：401 那一字未动 —— 鉴权的答案不许长成「这一格不供数」。"""
    _document_ledger_refuses(monkeypatch, status_code=401, detail="authentication_required")

    with pytest.raises(HTTPException) as caught:
        asyncio.run(sources_module.document_candidates(_request()))

    assert caught.value.status_code == 401
    assert caught.value.detail == "authentication_required"

# ================= 判据戊：写侧不许静默吞 —— 「问不出」不是「这条已经不在了」


def _check_write_side_asks_and_refuses() -> str:
    """账本缺表时 `can_address` 必须把那枚领域异常原样上抛，而不是回一枚 False。"""
    principal, request = _principal()
    try:
        asyncio.run(inbox_module.can_address(principal, request, APPROVAL_NOTIFICATION_ID))
    except hitl_store.PendingApprovalStoreMissing:
        return "raised"
    return "answered"


def test_the_write_side_raises_the_question_the_approval_ledger_cannot_answer(
    monkeypatch, world
):
    """判据戊：这台机器问不出 ⇒ 上抛。回 False 就是把一条还挂着的审批画成已解决。"""
    _approval_ledger_missing(monkeypatch)

    assert _check_write_side_asks_and_refuses() == "raised"


def test_the_approval_write_branch_re_raises_bare():
    """判据戊（代码层）：那一支的语句体只有一枚裸 `raise`，换码或换处置都红。"""
    handlers = [
        node
        for node in ast.walk(_function(_tree(INBOX_PY), "can_address"))
        if isinstance(node, ast.ExceptHandler)
    ]
    typed = [
        node
        for node in handlers
        if ast.unparse(node.type) == "pending_approvals.PendingApprovalStoreMissing"
    ]
    assert len(typed) == 1, f"审批写侧的具名承接应有 1 枚，实取 {len(typed)}"
    assert {ast.unparse(node.type) for node in handlers} == {
        "HTTPException",
        "pending_approvals.PendingApprovalStoreMissing",
        "(TypeError, ValueError)",
    }, f"can_address 的承接名单换了：{[ast.unparse(node.type) for node in handlers]}"
    body = [
        node
        for node in typed[0].body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
    ]
    assert len(body) == 1 and isinstance(body[0], ast.Raise), ast.dump(typed[0])
    assert body[0].exc is None, "上抛的不是原发那枚异常（换了码就是换了一句假话）"


def test_the_document_write_branch_gained_no_fold():
    """判据戊：文档那一腿一个字都不接 —— 接了就等于把拒答画成「这一枚不归你管」。"""
    for node in ast.walk(_function(_tree(INBOX_PY), "can_address")):
        if not isinstance(node, ast.If) or "SOURCE_DOCUMENT" not in ast.unparse(node.test):
            continue
        assert not [n for n in ast.walk(node) if isinstance(n, ast.Try)], (
            "文档写侧长出了 try：那正是本件不许的形状"
        )
        assert "_omitted" not in ast.unparse(node)
        return
    raise AssertionError("can_address 里找不到文档那一腿了")


def test_the_write_side_document_leg_does_not_fold_a_refusal(monkeypatch, world):
    """判据戊：文档账本回 503，写侧照原样上抛；不许折成 not_addressable 那枚回执。"""
    _document_ledger_refuses(monkeypatch)
    principal, request = _principal()

    with pytest.raises(HTTPException) as caught:
        asyncio.run(inbox_module.can_address(principal, request, DOCUMENT_NOTIFICATION_ID))

    assert caught.value.status_code == 503


def _check_dismiss_survives_the_refusal(raw_client) -> int:
    """写侧拒答的三格读数：不是 200、不是逐条回执、没有偷偷写下状态。"""
    response = raw_client.post(
        DISMISS_PATH,
        headers=_headers(FINANCE_MANAGER),
        json={"ids": [APPROVAL_NOTIFICATION_ID]},
    )
    if response.status_code == 200:
        raise AssertionError(f"拒答被折成了 200 回执：{response.text}")
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and "results" in payload:
        raise AssertionError(f"拒答之余还给出了逐条结论：{payload}")
    if state_store.recipient_states(FINANCE_MANAGER):
        raise AssertionError("拒答之余还写了一行读者状态")
    return response.status_code


def test_dismissing_an_approval_while_the_ledger_is_missing_writes_nothing(
    client, monkeypatch, world
):
    """判据戊（端到端）：问不出的那一枚既没收兵，也没落状态。

    今天它撞成裸 500（本仓 app/** 零 exception_handler，见模块文档串）。本枚故意不把 500 写死成
    等号：出口把那枚上抛答成 503 之后（`app/api/v1/notifications.py`，本单写域外），本枚照旧为绿。
    """
    _approval_ledger_missing(monkeypatch)

    status = _check_dismiss_survives_the_refusal(client)

    assert status >= 500, f"这一格的出口脸换了，请连同回执一起重读：{status}"
    assert state_store._ROWS == {}


def test_the_other_two_legs_keep_their_writes_while_the_approval_ledger_is_missing(
    client, world, monkeypatch
):
    """整页不许黑：写侧也只有审批那一腿问不出，另两腿照常落状态。"""
    _approval_ledger_missing(monkeypatch)

    response = client.post(
        DISMISS_PATH,
        headers=_headers(FINANCE_MANAGER),
        json={"ids": [DOCUMENT_NOTIFICATION_ID]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {
            "id": DOCUMENT_NOTIFICATION_ID,
            "state": "dismissed",
            "changed": True,
            "reason": "applied",
        }
    ]
    assert state_store.recipient_states(FINANCE_MANAGER) == {DOCUMENT_NOTIFICATION_ID: "dismissed"}


# ===================================================== 结构钉：不另装探针、不在合并层降级


def test_the_two_files_gained_no_database_driver_dependency():
    """本单不吞列错与连接错，代价是这两格照旧黑；凭据是这两枚文件里没有 pg 驱动可用。

    要把它们接进来只有两条路：宽捕获（判据丁禁）或在收件箱自己再算一遍库在不在（R366 的结构钉
    禁）。两条都通向第二本账，所以那一格归那本账与出口自己（见回执「只报不改」）。
    """
    for path in (SOURCES_PY, INBOX_PY):
        text = path.read_text(encoding="utf-8")
        assert "psycopg" not in text, f"{path.name} 长出了驱动依赖，捕获边界就不再是那一枚具名类型"
        assert "except Exception" not in text, f"{path.name} 里有宽捕获"


def test_collect_still_degrades_nothing_itself():
    """三枚源的合并层不许长出承接：降级只发生在各腿自己那一层，一条一码。"""
    collect = _function(_tree(INBOX_PY), "collect")
    assert not [node for node in ast.walk(collect) if isinstance(node, ast.ExceptHandler)], (
        "collect 里出现了承接：那会把三条腿的答案并成一句话"
    )


def test_every_delivered_file_keeps_the_repository_line_endings():
    """写域内文件的字节形状：每一个 LF 都在 CRLF 里、无 lone CR、无 BOM、严格 UTF-8 可解码。"""
    for path in (SOURCES_PY, INBOX_PY, CONTRACT, Path(__file__).resolve()):
        blob = path.read_bytes()
        assert blob[:3] != b"\xef\xbb\xbf", f"{path.name} 带上了 BOM"
        assert blob.count(b"\n") == blob.count(b"\r\n"), f"{path.name} 里有 lone LF"
        assert blob.replace(b"\r\n", b"").count(b"\r") == 0, f"{path.name} 里有 lone CR"
        blob.decode("utf-8")


# ================================================= 契约：文末追加一节，历史一字不动


def _git_show(revision: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"{revision}:{relative}"],
        capture_output=True,
        check=True,
    ).stdout


def _as_blob_text(raw: bytes) -> str:
    """一律落到 git blob 那一层（LF）比对：本仓 core.autocrlf=true，checkout 与 blob 两个形状。"""
    return raw.decode("utf-8").replace("\r\n", "\n")


#: 契约那一节里必须出现的字样。缺任一枚 = 口径只写在代码注释里，下一个人只能靠猜。
CONTRACT_MARKERS = (
    "storage_unavailable",
    "_omitted",
    "reason_code",
    "can_address",
    "PendingApprovalStoreMissing",
    "401, 403, 404",
    "500",
    "503",
    "Zero new error code",
    "sources.approval",
    "sources.document",
)


def _own_contract_section() -> str:
    text = _as_blob_text(CONTRACT.read_bytes())
    marker = "\n## " + OWN_SECTION_HEADING
    assert text.count(marker) == 1, f"本单那一节应有 1 枚，实得 {text.count(marker)}"
    start = text.index(marker)
    following = text.find("\n## ", start + len(marker))
    return text[start:following if following != -1 else len(text)]


def test_the_contract_appends_one_section_and_deletes_nothing():
    """三笔账都与提交先后无关：① 前缀等式 ② 长度变长 ③ 本单那枚节标题在追加段里恰一枚。"""
    base = _as_blob_text(_git_show(BASE, "docs/api/contract-v1.md"))
    now = _as_blob_text(CONTRACT.read_bytes())

    assert now.startswith(base), "契约不是纯追加：文末之前的每一个字都不许动"
    assert len(now) > len(base), "契约没长东西：本单一格都没写"
    assert now[len(base):].count("\n## " + OWN_SECTION_HEADING) == 1, "本单那一节在追加段里恰一枚"
    assert now.count("\n## ") >= base.count("\n## ") + 1, "一节都没长出来"


def test_the_new_contract_section_says_which_face_lives_where():
    """契约把两张脸写清：读侧折进 `_omitted`，写侧照旧上抛，名单各腿自派生。"""
    section = _own_contract_section()

    for marker in CONTRACT_MARKERS:
        assert marker in section, f"契约那一节没提 {marker}"
    assert "bare 500" in section, "契约没写清今天这一格到底是什么脸"


def test_the_contract_bytes_stay_in_the_repository_shape():
    blob = CONTRACT.read_bytes()
    assert blob[:3] != b"\xef\xbb\xbf", "契约被写成带 BOM"
    assert blob.count(b"\n") == blob.count(b"\r\n"), "追加引入了 lone LF"
    assert blob.decode("utf-8").count("\ufffd") == 0, "契约里出现 U+FFFD：编码被写坏过"

# ================================================= 判据己：反证刀（影子根，盘上只读）


class _R373Edit(overlay.ShadowEdit):
    """一扇 R373 的反证窗：变异只落临时目录里的影子副本，并 exec 进内存那一枚模块字典。

    锚点按**行列表**给，换行由被改文件自己决定（本仓文件体是纯 CRLF）；命中数不是恰好一枚就整个
    不落窗，变异文本还要先过一枚 compile()，语法不过就连窗都不开。盘上那枚被跟踪文件全程只读。
    """

    tag = "r373"
    execs_module = True

    def __init__(self, path: Path, old_lines, new_lines) -> None:
        super().__init__(path)
        self.old_lines = tuple(old_lines)
        self.new_lines = tuple(new_lines)

    def mutate(self, text: str) -> str:
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        old = newline.join(self.old_lines)
        hits = text.count(old)
        assert hits == 1, f"{self.path.name} 里锚点命中 {hits} 处（要求恰好 1 处）：变异整体不落窗"
        mutated = text.replace(old, newline.join(self.new_lines), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _mutate(path: Path, old_lines, new_lines, rebind=()):
    """开一扇反证窗，把「谁 import 了这一格」指到变异版上，出门逐格还原。"""
    mutated_module = overlay.module_of(overlay.rel_of(path))
    assert mutated_module is not None, f"{path.name} 还没被导入，exec 无处可落"
    snapshots = [(target, attr, getattr(target, attr)) for target, attr in rebind]
    with _R373Edit(path, old_lines, new_lines) as info:
        for target, attr, _before in snapshots:
            setattr(target, attr, getattr(mutated_module, attr))
        try:
            yield info
        finally:
            for target, attr, before in snapshots:
                setattr(target, attr, before)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _must_go_red(pin, *args) -> str:
    """反证刀只看「红没红」：任何一类红都算红，全绿就说明这把刀是钝的。"""
    try:
        pin(*args)
    except BaseException as exc:  # noqa: BLE001 - 刀要的是红，AssertionError 与 Failed 一样红
        return type(exc).__name__ + ": " + str(exc)[:200]
    raise AssertionError(f"{pin.__name__} 在变异版下全绿：这把刀是钝的")


#: 刀一：摘掉本单新加的承接（审批腿那一枚具名类型的折叠）。
KNIFE_ONE_OLD = (
    "    try:",
    "        records = pending_approvals.open_items(owner_user_id=owner)",
    "    except pending_approvals.PendingApprovalStoreMissing:",
    "        # R373：账本缺表是「这一格问不出」，不是「这一格没有新事项」，两张脸各自留名。",
    "        return _omitted(SOURCE_APPROVAL, STORAGE_UNAVAILABLE)",
)
KNIFE_ONE_NEW = ("    records = pending_approvals.open_items(owner_user_id=owner)",)

#: 刀二：把拒答折成「空 bundle，不登记缺席」——正是判据丙要杀的那张脸。
KNIFE_TWO_OLD = (
    "        # R373：账本缺表是「这一格问不出」，不是「这一格没有新事项」，两张脸各自留名。",
    "        return _omitted(SOURCE_APPROVAL, STORAGE_UNAVAILABLE)",
)
KNIFE_TWO_NEW = ("        return SourceBundle(source_type=SOURCE_APPROVAL)",)

#: 刀三：把 403 塞进文档腿的折叠名单。
KNIFE_THREE_OLD = (
    "        if exc.status_code == 503:",
    "            # R373：与告警腿同构的折叠，reason 取那本账自己给出的那一枚；其余状态码原样上抛。",
)
KNIFE_THREE_NEW = (
    "        if exc.status_code in (403, 503):",
    "            # 刀三：权限那一支被并进了存储那一支。",
)

#: 刀四：写侧把「问不出」答成「这条已经不在了」。
KNIFE_FOUR_OLD = (
    "            # 的活，不在本文件写域内，已具名上报总控。",
    "            raise",
)
KNIFE_FOUR_NEW = (
    "            # 刀四：把拒答折成 not_addressable。",
    "            return False",
)


def test_knife_one_removing_the_approval_fold_reddens_the_read_pins(
    client, world, monkeypatch
):
    """刀一：摘掉承接 ⇒ 200 那枚、缺席形状那枚、两腿照读那枚、码表那枚各红一次。"""
    _approval_ledger_missing(monkeypatch)
    test_the_inbox_still_answers_200_when_the_approval_ledger_is_missing(client, world, monkeypatch)
    before = _sha(SOURCES_PY)

    with _mutate(
        SOURCES_PY, KNIFE_ONE_OLD, KNIFE_ONE_NEW, rebind=[(inbox_module, "approval_candidates")]
    ) as info:
        assert "500" in _must_go_red(
            test_the_inbox_still_answers_200_when_the_approval_ledger_is_missing,
            client,
            world,
            monkeypatch,
        )
        _must_go_red(
            test_the_absent_approval_leg_uses_the_existing_omitted_projection_shape,
            client, world, monkeypatch,
        )
        _must_go_red(
            test_the_other_two_legs_keep_reading_the_same_words_when_approval_refuses,
            client, world, monkeypatch,
        )
        _must_go_red(
            test_no_reason_code_any_leg_can_carry_is_outside_the_ratified_table,
            client, world, monkeypatch,
        )
        # 本单的刀不许借道改告警腿的账：窗内读影子副本，那一腿的名单仍恰是 {403, 503}。
        # （整页在变异版下就是黑的，权限那枚行为件不可能在这扇窗里还绿 —— 它的零红由
        # test_knife_three 那一扇窗与交付态合跑那一批既有件负责，两格各管各的。）
        _assert_fold_roster(
            info.read_text(), "alert_candidates", "SOURCE_ALERT", {403: "omitted", 503: "omitted"}
        )

    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(SOURCES_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"
    test_the_inbox_still_answers_200_when_the_approval_ledger_is_missing(client, world, monkeypatch)


def test_knife_two_a_quiet_bundle_instead_of_an_absence_reddens_the_two_faces_pin(
    client, world, monkeypatch
):
    """刀二：折成「空 bundle 不登记缺席」⇒ 判据丙那枚必红，另外两枚也跟着红。"""
    before = _sha(SOURCES_PY)

    with _mutate(
        SOURCES_PY, KNIFE_TWO_OLD, KNIFE_TWO_NEW, rebind=[(inbox_module, "approval_candidates")]
    ) as info:
        _must_go_red(
            test_an_absent_approval_ledger_and_a_quiet_one_are_two_different_faces,
            client, world, monkeypatch,
        )
        _must_go_red(
            test_the_absent_approval_leg_uses_the_existing_omitted_projection_shape,
            client, world, monkeypatch,
        )
        _must_go_red(
            test_the_absence_carries_the_very_code_the_approval_gate_itself_emits,
            client, world, monkeypatch,
        )

    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(SOURCES_PY) == before, "盘上被跟踪文件被动过一字节"


def test_knife_three_merging_403_into_the_document_fold_reddens_its_own_pins(
    client, world, monkeypatch
):
    """刀三：把 403 并进文档腿的存储那一支 ⇒ 那张脸那枚必红；告警腿的名单一格没动。"""
    before = _sha(SOURCES_PY)

    with _mutate(
        SOURCES_PY, KNIFE_THREE_OLD, KNIFE_THREE_NEW, rebind=[(inbox_module, "document_candidates")]
    ) as info:
        _must_go_red(
            test_a_403_from_the_document_ledger_is_not_folded_into_an_absence,
            client, world, monkeypatch,
        )
        _must_go_red(
            lambda: _assert_fold_roster(
                info.read_text(), "document_candidates", "SOURCE_DOCUMENT", {503: "omitted"}
            )
        )
        _assert_fold_roster(
            info.read_text(), "alert_candidates", "SOURCE_ALERT", {403: "omitted", 503: "omitted"}
        )
        test_a_staff_caller_still_gets_the_permission_answer_not_the_storage_answer(
            client, world, monkeypatch
        )

    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(SOURCES_PY) == before, "盘上被跟踪文件被动过一字节"


def test_knife_four_answering_false_on_a_missing_ledger_reddens_the_write_pins(
    client, world, monkeypatch
):
    """刀四：写侧把拒答答成 False ⇒ 上抛那枚与端到端那枚各红一次。"""
    before = _sha(INBOX_PY)

    with _mutate(
        INBOX_PY,
        KNIFE_FOUR_OLD,
        KNIFE_FOUR_NEW,
        rebind=[(notifications_api, "can_address")],
    ) as info:
        _must_go_red(
            test_the_write_side_raises_the_question_the_approval_ledger_cannot_answer,
            monkeypatch, world,
        )
        _must_go_red(
            test_dismissing_an_approval_while_the_ledger_is_missing_writes_nothing,
            client, monkeypatch, world,
        )

    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(INBOX_PY) == before, "盘上被跟踪文件被动过一字节"