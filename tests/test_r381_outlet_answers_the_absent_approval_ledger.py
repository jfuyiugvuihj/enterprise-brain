"""R381 · 审批账本缺表时，写侧出口必须说人话：503 storage_unavailable，而不是裸 500。

一手取证（基点 `0d4f5ec`，本件在树上现跑，不是读注释）：从 `POST /notifications/read` 与
`POST /notifications/dismiss` 两枚出口出发，`app/notifications/inbox.py:152` 那一次
`pending_approvals.open_items` 抛出的 `PendingApprovalStoreMissing`（
`app/storage/pending_approvals.py:152` ← `:371` ← `:390`）穿过 `notifications.py:159` 那支只接
生命周期台账错滴 except，一路逃到 ASGI —— 而 `app/**` 零 exception_handler（rg exit 1 已证），
于是客户拿到的是 `500 text/plain "Internal Server Error"`：没有码、没有人话、没有「跑 0008」。
读侧那一格（`GET /notifications`）今天接不到这枚异常：同一枚错早在 `sources.py:130` 就被折成逐腿
缺席，整页仍 200。本单因此**没有**把它接进读出口那一支（判据①：拿不出抛出链的不许进折叠名单），
而且把这条因果也钉住了 —— 摘掉 `sources.py` 那枚逐腿折叠，读出口照旧是裸 500（第
`test_the_read_exit_still_goes_bare_when_the_leg_fold_is_removed` 枚）。反证刀五就是这一格的对照：
往读侧那支也接一次，红的不止本件的形状钉，还有 R376 那枚名单钉与上面这枚裸 500 钉。

R373 的裁定一字不动：`can_address` 那一支仍裸 `raise`（“问不出”不是“不在了”），本件不往
`app/notifications/inbox.py` 里加一个字。改的是出口那一边：让那张脸有正确的出口，而不是让写侧闭嘴。

形状面（判据乙）住在 `tests/test_r381_outlet_shape_pins.py`，那里钉死：名单恰六枚、503 抛出点
恰两枚、两支 except 里不许有 `return`、宽捕获仍恰一枚且仍在 `_ids_from_body`。本件只管行为面：
脸、状态、回执、审计、以及仍归别人治的那三格。
"""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import get_args
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import psycopg.errors as pg_errors

from app.agents.contracts import ErrorEnvelope
from app.api.v1 import alerts as alerts_api
from app.api.v1 import notifications as notifications_api
from app.common.audit import get_audit_events
from app.common.auth import create_token
from app.main import app
from app.notifications import states as state_store
from app.storage import pending_approvals as hitl_store
from tests import _temp_edit_overlay as overlay
from tests import test_r373_the_two_remaining_legs_answer_absence as r373
from tests import test_r381_outlet_shape_pins as shape

REPO = Path(__file__).resolve().parents[1]
OUTLET_PY = REPO / "app" / "api" / "v1" / "notifications.py"

INBOX_PATH = "/api/v1/notifications"
READ_PATH = "/api/v1/notifications/read"
DISMISS_PATH = "/api/v1/notifications/dismiss"
WRITE_PATHS = [READ_PATH, DISMISS_PATH]
WRITE_PATH_IDS = ["mark_as_read", "dismiss"]

#: 仓里已有的那一码：出口那两支 except 本来就在吐它（基点 `:161` / `:191`），本单零新增。
STORAGE_CODE = "storage_unavailable"
NOT_ADDRESSABLE = "notification_not_addressable"

DEPT = "r381-finance"
READER = "r381-reader"
STRANGER = "r381-stranger"
SESSION_ID = "r381-session-1"
STRANGER_SESSION = "r381-session-2"
APPROVAL_ID = f"approval:{SESSION_ID}"
STRANGER_APPROVAL_ID = f"approval:{STRANGER_SESSION}"
ALERT_ID = 8381
ALERT_NOTIFICATION_ID = f"alert:{ALERT_ID}"
ABSENT_ALERT_ID = "alert:98381"
DOCUMENT_NOTIFICATION_ID = "document:r381-plan.pdf#v1"


def _account(username: str, department: str = DEPT, role: str = "manager") -> dict:
    return {"id": username, "username": username, "role": role, "department": department}


#: `r373-finance-manager` 不是本件自己的账号：反证窗里要复跑 R373 那族钉（判据戊三），它们的
#: `_headers` 用的是那一枚名字。不登记进来，那族钉就会红在“鉴权失败”而不是红在“拒答被吞”。
ACCOUNTS = {
    READER: _account(READER),
    STRANGER: _account(STRANGER),
    "r373-finance-manager": _account("r373-finance-manager", "r373-finance"),
}


@pytest.fixture(autouse=True)
def accounts(monkeypatch):
    """把这几枚账号喂进鉴权中间件真正用的那一次查询；`_db_ready` 钉成假。"""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    monkeypatch.setattr(auth, "_db_ready", False)


@pytest.fixture(autouse=True)
def memory_legs(monkeypatch):
    """三本账全钉在内存形状；本件只把“审批那一本缺表”那一格撑起来。"""
    monkeypatch.setattr(hitl_store, "_MEM_ROWS", {})
    monkeypatch.setattr(hitl_store, "_database_available", lambda: False)
    monkeypatch.setattr(alerts_api, "_MEM_ALERTS", [])
    monkeypatch.setattr(alerts_api, "_database_available", lambda: False)
    monkeypatch.setattr(state_store, "_ROWS", {})
    monkeypatch.setattr(state_store, "_database_available", lambda: False)
    hitl_store.record_awaiting(SESSION_ID, READER, ["chart"], request_id="req-r381-mine")
    hitl_store.record_awaiting(STRANGER_SESSION, STRANGER, ["chart"], request_id="req-r381-theirs")
    alerts_api._MEM_ALERTS.append(
        {
            "id": ALERT_ID,
            "rule_id": 1,
            "message": "R381 营收跌破阈值",
            "read": False,
            "department": DEPT,
            "created_at": "2026-09-27T09:00:00+08:00",
        }
    )


@pytest.fixture()
def client():
    """看得到真实出口的客户端：未处理异常必须作为 500 读进来，而不是改写成 Python 回溯。"""
    return TestClient(app, raise_server_exceptions=False)


def _headers(username: str = READER) -> dict:
    return {"Authorization": f"Bearer {create_token(username)}"}


def _post(client, path: str, ids: list[str], username: str = READER):
    return client.post(path, headers=_headers(username), json={"ids": ids})


def _audit_denials_for(notification_id: str) -> list[dict]:
    return [
        event
        for event in get_audit_events(outcome="denied")
        if str(event.get("resource") or "") == notification_id
    ]


# --------------------------------------------------------------- 三格排查路的替身库


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _AbsentTableConnection:
    """第一格：PG 起着而 `pending_approvals` 那张表不在（0008 没跑）。"""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        return _Result({"table_name": None})

    def close(self):
        pass


class _MissingColumnConnection(_AbsentTableConnection):
    """第二格：表在而列不全（镜像比库新）。`_require_table` 放行，SQL 自己拒。"""

    def execute(self, sql, params=None):
        if "to_regclass" in sql:
            return _Result({"table_name": "pending_approvals"})
        raise pg_errors.UndefinedColumn('column "declared_lane" does not exist')


class _DriverMissingConnection(_AbsentTableConnection):
    """第三格：连驱动都没有。那是裸 RuntimeError，不是那枚具名子类。"""

    def execute(self, sql, params=None):
        raise RuntimeError("PostgreSQL driver is unavailable")


#: 三格各自那枚替身，按名字取：本件只治第一格，后两格钉成看得见的边界。
GRIDS = {
    "absent_table": _AbsentTableConnection,
    "missing_column": _MissingColumnConnection,
    "no_driver": _DriverMissingConnection,
}


def _approval_ledger_grid(monkeypatch, grid: str = "absent_table") -> None:
    """把审批那一本账摆到指定那一格上：库在位，而账本自己问不出。"""
    monkeypatch.setattr(hitl_store, "_database_available", lambda: True)
    monkeypatch.setattr(hitl_store, "_conn", GRIDS[grid])


# --------------------------------------------------------------- 判据①②：第一格要说人话


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_a_missing_approval_ledger_answers_503_on_both_write_exits(client, monkeypatch, path):
    """本单唯一那一格改动：那张脸从 `500 text/plain` 换成全仓已经在说的 503。"""
    _approval_ledger_grid(monkeypatch)

    response = _post(client, path, [APPROVAL_ID])

    assert response.status_code == 503, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": STORAGE_CODE}


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_the_refusal_writes_no_reader_state_and_no_receipt(client, monkeypatch, path):
    """503 不是 200 的另一张脸：这一格一枚状态都不写，也不给逐条结论。"""
    _approval_ledger_grid(monkeypatch)

    response = _post(client, path, [APPROVAL_ID])

    assert response.status_code == 503
    assert "results" not in response.json()
    assert state_store._ROWS == {}
    assert state_store.recipient_states(READER) == {}


def test_a_mixed_batch_refuses_the_whole_call_before_recording_anything(client, monkeypatch):
    """同一批里有一枚可寻址的告警也不许先落半行：问不出的那一格排在写之前。"""
    _approval_ledger_grid(monkeypatch)

    response = _post(client, DISMISS_PATH, [APPROVAL_ID, ALERT_NOTIFICATION_ID])

    assert response.status_code == 503
    assert state_store._ROWS == {}


def test_the_refused_id_records_no_denial_in_the_audit_trail(client, monkeypatch):
    """存储拒答不是越权：那一格不许在既有的审计账上长出一条 denied。"""
    _approval_ledger_grid(monkeypatch)

    _post(client, DISMISS_PATH, [APPROVAL_ID])

    assert _audit_denials_for(APPROVAL_ID) == []


def test_the_fold_reuses_a_ratified_code_and_adds_no_face(client, monkeypatch):
    """零新增错误码：吐出去的这一枚本来就在封闭枚举里，也不与入参/权限那两格并脸。"""
    _approval_ledger_grid(monkeypatch)

    detail = _post(client, READ_PATH, [APPROVAL_ID]).json()["detail"]

    assert detail == STORAGE_CODE
    assert detail in set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert shape._http_raises(shape._tree(shape.OUTLET_PY)) == shape.OUTLET_ERROR_FACES


# --------------------------------------------------------------- 判据③：不许反向放宽


def test_the_inbox_still_answers_200_with_the_absent_leg_when_the_ledger_is_missing(
    client, monkeypatch
):
    """读侧那张脸一字不变：缺席仍按逐腿登记，本单没有把账本错接进读出口那一支。

    这一枚与下面那枚直调钉是一对：整页仍 200 是 `sources.py` 那枚逐腿折叠在说话，不是出口在
    替它兜底 —— 出口那一支今天只接生命周期一枚，账本那枚走到它就是裸 500（见直调那枚）。
    """
    _approval_ledger_grid(monkeypatch)

    response = client.get(INBOX_PATH, headers=_headers())

    assert response.status_code == 200, response.text
    assert response.json()["sources"]["approval"] == {
        "included": False,
        "reason_code": STORAGE_CODE,
        "candidates": 0,
        "scanned": 0,
        "truncated": False,
    }


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_an_unaddressable_id_keeps_its_own_receipt_while_the_ledger_is_missing(
    client, monkeypatch, path
):
    """折叠只认那一枚具名类型：问不出的审批与管不着的编号是两张脸，不许同一次黑。"""
    _approval_ledger_grid(monkeypatch)

    before = len(_audit_denials_for(ABSENT_ALERT_ID))
    response = _post(client, path, [ABSENT_ALERT_ID])

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {"id": ABSENT_ALERT_ID, "state": None, "changed": False, "reason": NOT_ADDRESSABLE}
    ]
    # 审计账是进程级的既有台账，逐枚用例只判「这一次多了一条」，不判绝对条数。
    assert len(_audit_denials_for(ABSENT_ALERT_ID)) == before + 1


def test_the_stranger_approval_keeps_its_own_not_addressable_answer(client):
    """别人的编号仍按可寻址性那一格答：本件没把审批腿一律画成存储错。"""
    response = _post(client, READ_PATH, [STRANGER_APPROVAL_ID])

    assert response.status_code == 200
    assert response.json()["results"][0]["reason"] == NOT_ADDRESSABLE


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
def test_a_healthy_ledger_still_answers_with_a_per_item_receipt(client, path):
    """开发态那两枚动作一个字没改：能问出，就照旧逐条回 `applied`。"""
    response = _post(client, path, [APPROVAL_ID])

    assert response.status_code == 200, response.text
    assert response.json()["results"] == [
        {"id": APPROVAL_ID, "state": "read" if path == READ_PATH else "dismissed",
         "changed": True, "reason": "applied"}
    ]


def test_an_anonymous_caller_still_meets_the_401_face_not_the_storage_one(client, monkeypatch):
    """判据④第一道闸：账本缺不缺表，轮不到不认识的人来问。"""
    _approval_ledger_grid(monkeypatch)

    response = client.post(READ_PATH, json={"ids": [APPROVAL_ID]})

    assert response.status_code == 401
    assert response.json() == {"detail": "authentication_required"}


def test_the_anonymous_guard_itself_raises_the_401_face():
    """出口自己那道闸：拿不到 principal 就是 401，与存储那一格无关。

    HTTP 上今天先被中间件挡下（`test_an_anonymous_caller_...` 钉的是那一格），所以这一枚直调
    出口那支守卫本身 —— 反证刀四（把 401 折成 503）必须有行为面的受害者，靠的就是这一枚。
    """
    with pytest.raises(HTTPException) as caught:
        notifications_api._principal_or_401(None)

    assert caught.value.status_code == 401
    assert caught.value.detail == "authentication_required"


def test_a_malformed_id_still_answers_422_while_the_ledger_is_missing(client, monkeypatch):
    """入参那一格也不并脸：形状不合仍在 `try` 之前就被拒掉。"""
    _approval_ledger_grid(monkeypatch)

    response = _post(client, READ_PATH, ["no-separator-here"])

    assert response.status_code == 422
    assert response.json() == {"detail": "validation_error"}


# --------------------------------------------------------------- 判据④：另两格仍是裸 500（故意）


@pytest.mark.parametrize("path", WRITE_PATHS, ids=WRITE_PATH_IDS)
@pytest.mark.parametrize("grid", ["missing_column", "no_driver"], ids=["no_column", "no_driver"])
def test_the_other_two_grids_still_answer_a_bare_500(client, monkeypatch, grid, path):
    """本单只治第一格：缺列与驱动缺失照旧裸 500。这枚钉钉的是“还没治”，不是“治好了”。

    为什么不在出口用字符串匹配把它们硬折进来：那是第二本账 —— 一枚靠 `type(exc).__name__` 与
    报错文案认出来的“存储不可用”，会把 SQL 层的列错、连接串错、以及未来任何一句带
    “does not exist” 的真 bug 一起洗成 503。三格各自的具名类型才是那三句可执行的诊断。
    """
    _approval_ledger_grid(monkeypatch, grid)

    response = _post(client, path, [APPROVAL_ID])

    assert response.status_code == 500, f"{grid} 被折成了可读的一格：本单的捕获边界不覆盖它"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.strip() == "Internal Server Error"
    assert state_store._ROWS == {}


@pytest.mark.parametrize("grid", ["missing_column", "no_driver"], ids=["no_column", "no_driver"])
def test_those_two_grids_still_take_the_inbox_down_with_them(client, monkeypatch, grid):
    """读侧同两格也还黑：那两格的出口在 `sources.py` 之外，本单一字不碰。"""
    _approval_ledger_grid(monkeypatch, grid)

    response = client.get(INBOX_PATH, headers=_headers())

    assert response.status_code == 500
    assert response.text.strip() == "Internal Server Error"


def test_the_read_exit_leaves_that_ledger_refusal_untranslated(client, monkeypatch):
    """判据①的另一半：读出口今天不接那枚账本错，本件就没往里塞。

    把 `PendingApprovalStoreMissing` 从 `build_inbox` 里直接举出来给客户看：那一支今天仍把它抛到
    ASGI，脸是裸 500 纯文本。今天真实的链走不到这里（`sources.py::approval_candidates` 早在腿里折成
    逐腿缺席），所以「接进来」是一枚没有抛出链的折叠 —— 判据①不许。哪天要接，这枚钉先红，逼着把
    R373 刀一在读出口量到的那个 signature 一起改口，而不是顺手换脸。
    """

    async def _refuse(*_args, **_kwargs):
        raise hitl_store.PendingApprovalStoreMissing("r381: 出口可达性替身")

    monkeypatch.setattr(notifications_api, "build_inbox", _refuse)

    response = client.get(INBOX_PATH, headers=_headers())

    assert response.status_code == 500, f"读出口不知何时接了那枚账本错：{response.status_code}"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.strip() == "Internal Server Error"


def test_the_read_exit_call_itself_lets_that_ledger_refusal_through(monkeypatch):
    """同一格的直调版：反证刀五的受害者必须是这一枚，不是上面那枚 HTTP 读数。

    `app.main` 在导入时就把 `list_notifications` 这枚函数对象登记进了路由，反证窗 exec 的是模块
    `__dict__` 上的新对象，路由手里那枚还是旧的 —— 所以「往读侧多接一枚」这类变异在 HTTP 上读不到
    （写侧那两枚动作经 `_apply` 间接层，才吃得到窗里的改动）。这一枚直调盘上现在那一支，窗里的
    改动立刻可见：多接一枚，它就换成 503，判据①那格就红在这里。
    """
    from app.common.authorization import Principal

    async def _refuse(*_args, **_kwargs):
        raise hitl_store.PendingApprovalStoreMissing("r381: 出口可达性替身")

    monkeypatch.setattr(notifications_api, "build_inbox", _refuse)
    request = SimpleNamespace(state=SimpleNamespace(principal=Principal.from_user(ACCOUNTS[READER])))

    with pytest.raises(hitl_store.PendingApprovalStoreMissing):
        asyncio.run(notifications_api.list_notifications(request))


def test_a_corrupt_stored_state_is_not_washed_into_a_storage_answer(client):
    """第四格：表里躺着一枚本仓不认识的词 —— 那是数据损坏，不是存储没就绪。

    `contracts.advance_state` 故意具名拒答（宁可报错也不拿 `requested` 盖掉它），今天它穿过出口
    仍是裸 500。把 `NotificationIdError` 也接进那支 except 就等于替一次损坏发一张“运维去跑迁移”
    的假处方 —— 反证刀三钉的正是这一格。
    """
    state_store._ROWS[(READER, ALERT_NOTIFICATION_ID)] = {
        "state": "banana",
        "recorded_at": "2026-09-27T09:00:00+08:00",
        "updated_at": "2026-09-27T09:00:00+08:00",
    }

    response = _post(client, READ_PATH, [ALERT_NOTIFICATION_ID])

    assert response.status_code == 500
    assert response.text.strip() == "Internal Server Error"
    assert state_store._ROWS[(READER, ALERT_NOTIFICATION_ID)]["state"] == "banana", (
        "损坏那一格被一次正常写盖掉了：那才是本件最不该看见的事"
    )

# --------------------------------------------------------------- 判据⑤：反证刀


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report(knife: str, reds: list, greens: list) -> None:
    """一把刀一屏：红几枚、逐枚具名（红件 + 那枚红的类型），再列全窗里仍绿的格子。

    断言原文里带换行，一行一枚是把它们压平后再打 —— 回执要按这一屏点名，不能只报一个数。
    """
    print("[r381-%s] reds=%d" % (knife, len(reds)))
    for entry in reds:
        print("[r381-%s]   RED %s" % (knife, " ".join(entry.split())))
    print("[r381-%s] stays_green=%d: %s" % (knife, len(greens), ", ".join(greens)))


class _R381Edit(overlay.ShadowEdit):
    """一扇 R381 的反证窗：变异只落影子副本，盘上那枚文件全程只读。

    锚点按**行列表**给，换行由被改文件自己决定（本仓文件体纯 CRLF）；每段锚点的命中数必须等于
    登记的那一枚数，差一处就整体不落盘 —— 那正是 r303 记过的「锚点不唯一 ⇒ 反证空转」。
    """

    tag = "r381"
    execs_module = True

    def __init__(self, path: Path, patches) -> None:
        super().__init__(path)
        self.patches = tuple(patches)

    def mutate(self, text: str) -> str:
        newline = "\r\n" if "\r\n" in text else "\n"
        mutated = text
        for old_lines, new_lines, expected in self.patches:
            old = newline.join(tuple(old_lines))
            found = mutated.count(old)
            if found != expected:
                raise AssertionError(
                    "锚点应恰命中 %d 处，实取 %d 处：%r" % (expected, found, tuple(old_lines)[:1])
                )
            mutated = mutated.replace(old, newline.join(tuple(new_lines)))
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _mutate(path: Path, patches):
    assert overlay.module_of(overlay.rel_of(path)) is not None, "被改模块还没导入，exec 无处可落"
    with _R381Edit(path, patches) as info:
        yield info


def _must_go_red(pin, *args, label: str = "") -> str:
    """反证刀只看「红没红」：任何一类红都算红，全绿就说明这把刀是钝的。

    `label` 只在红件要经一把手（还原替身的 `_with_restored_inbox`、按路径参数化的同一枚钉）时给：
    回执要点名到真正的钉，而不是点名到那把手。
    """
    name = label or getattr(pin, "__name__", str(pin))
    try:
        pin(*args)
    except BaseException as exc:  # noqa: BLE001 - 刀要的是红，AssertionError 与 Failed 一样红
        return "%s<-%s: %s" % (name, type(exc).__name__, str(exc)[:110])
    raise AssertionError(f"{name} 在变异版下全绿：这把刀是钝的")


def _stays_green(label: str, pin, *args) -> str:
    try:
        pin(*args)
    except BaseException as exc:  # noqa: BLE001
        raise AssertionError(f"{label} 不该被这把刀碰到：{type(exc).__name__}: {exc}") from exc
    return label


def _r373_dismiss_writes_nothing(client, monkeypatch) -> None:
    """复算 R373 那族钉：三格判据 `_check_dismiss_survives_the_refusal`（不是 200、不是逐条回执、
    一枚状态都不写）加上它外面那一行 `assert status >= 500`。本件的刀必须红在这族钉上。"""
    status = r373._check_dismiss_survives_the_refusal(client)
    assert status >= 500, f"这一格的出口脸换了，请连同回执一起重读：{status}"


#: 写侧那一支 except 的头部（本单唯一那一格改动）、它的注释首尾，以及两行 503 抛出。
STORAGE_EXCEPT_HEAD = (
    "    except (",
    "        state_store.NotificationStateStoreMissing,",
    "        pending_approvals.PendingApprovalStoreMissing,",
    "    ) as exc:",
)
STORAGE_HEAD_COMMENT = "        # 只接这两枚具名错"
WRITE_TAIL_LAST = "        # 那一枚，于是这张脸在客户机上是裸 500 纯文本 —— 答成 503 才是那句可执行的运维真话。"
STORAGE_RAISE = "        raise HTTPException(status_code=503, detail='storage_unavailable') from exc"
AUTH_RAISE = "        raise HTTPException(status_code=401, detail='authentication_required')"

#: 读侧那一支（基点交付态一字未动）：刀五把它折成写侧那支的形状，用来还「顺手多接一枚」的债。
READ_EXCEPT = ("    except state_store.NotificationStateStoreMissing as exc:", STORAGE_RAISE)

#: 刀一：摘掉那一格改动 —— 写侧那支回到只接生命周期一枚。
KNIFE_ONE = (
    (STORAGE_EXCEPT_HEAD, READ_EXCEPT[:1], 1),
)

#: 刀二：把那枚账本错折成空回执 —— 静默吞，正是 R373 判过的那张脸。
KNIFE_TWO = (
    (
        (WRITE_TAIL_LAST, STORAGE_RAISE),
        (
            WRITE_TAIL_LAST,
            "        return {",
            "            'action': action,",
            "            'requested': len(ids),",
            "            'changed': 0,",
            "            'results': [],",
            "        }",
        ),
        1,
    ),
)

#: 刀三：顺手把入参那一格（`NotificationIdError`）也并进存储那一格。
KNIFE_THREE = (
    (
        ("        pending_approvals.PendingApprovalStoreMissing,", "    ) as exc:"),
        (
            "        pending_approvals.PendingApprovalStoreMissing,",
            "        NotificationIdError,",
            "    ) as exc:",
        ),
        1,
    ),
)

#: 刀四：顺手把权限那一格（401）也折成 503 —— 换成一张真的 503 脸，不带 `from exc`（那一枚
#: 名字在这里根本不在作用域里，带着它红就成了 NameError 的红，证据不纯）。
KNIFE_FOUR = (
    ((AUTH_RAISE,), ("        raise HTTPException(status_code=503, detail='storage_unavailable')",), 1),
)

#: 刀五：往读侧那一支也接一次账本错 —— 判据①说没有抛出链就不许进名单，这把刀就是那句话的对照。
KNIFE_FIVE = ((READ_EXCEPT, STORAGE_EXCEPT_HEAD + (STORAGE_RAISE,), 1),)

def test_the_knife_anchors_are_unique_in_the_delivered_file():
    """刀不钝的前提是锚点还在原位：出口那几行被改过时，本枚先红，而不是让反证悄悄空转。"""
    text = overlay.authoritative_text(overlay.rel_of(OUTLET_PY))
    head = "\r\n".join(STORAGE_EXCEPT_HEAD)

    assert text.count(head) == 1, f"写侧那支具名 except 的头部应恰一枚，实取 {text.count(head)}"
    assert text.count("\r\n".join(READ_EXCEPT)) == 1, "读侧那一支不再是基点交付态：刀五的锚点会打偏"
    assert text.count(STORAGE_HEAD_COMMENT) == 1, "写侧首行注释落点变了"
    assert text.count(WRITE_TAIL_LAST) == 1, "写侧那行尾注释不止一枚：刀二的锚点会打偏"
    assert text.count(STORAGE_RAISE) == 2, "503 那一行的落点数变了"
    assert text.count(AUTH_RAISE) == 1, "401 那一行不止一枚：刀四的锚点会打偏"


def test_knife_one_removing_the_new_type_reddens_the_face_pins(client, monkeypatch):
    """刀一：摘掉写侧那一枚 ⇒ 五枚脸钉 + 三枚形状钉各红一次（含 R376 那枚改过口的名单钉）。"""
    _approval_ledger_grid(monkeypatch)
    before = _sha(OUTLET_PY)
    reds: list = []
    greens: list = []
    with _mutate(OUTLET_PY, KNIFE_ONE) as info:
        reds.append(_must_go_red(
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, READ_PATH))
        reds.append(_must_go_red(
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, DISMISS_PATH))
        reds.append(_must_go_red(
            test_the_refusal_writes_no_reader_state_and_no_receipt, client, monkeypatch, READ_PATH))
        reds.append(_must_go_red(
            test_a_mixed_batch_refuses_the_whole_call_before_recording_anything, client, monkeypatch))
        reds.append(_must_go_red(
            test_the_fold_reuses_a_ratified_code_and_adds_no_face, client, monkeypatch))
        reds.append(_must_go_red(shape.test_the_outlet_roster_is_exactly_the_six_ratified_names))
        reds.append(_must_go_red(shape.test_this_ticket_grew_the_roster_by_exactly_one_named_type))
        reds.append(_must_go_red(shape.test_the_ledger_type_is_folded_at_the_write_exit_only))
        greens.append(_stays_green("r381pins:two_storage_handlers",
            shape.test_the_storage_handlers_are_exactly_two_one_read_one_write))
        greens.append(_stays_green("r381pins:two_503_raises",
            shape.test_the_module_still_emits_exactly_two_503_raises))
        greens.append(_stays_green("r381pins:one_503_each",
            shape.test_each_storage_handler_raises_exactly_one_503_and_chains_the_original))
        greens.append(_stays_green("r381:inbox_200",
            test_the_inbox_still_answers_200_with_the_absent_leg_when_the_ledger_is_missing, client, monkeypatch))
        greens.append(_stays_green("r381:not_addressable",
            test_an_unaddressable_id_keeps_its_own_receipt_while_the_ledger_is_missing, client, monkeypatch, READ_PATH))
        greens.append(_stays_green("r373:write_side_still_asks", r373._check_write_side_asks_and_refuses))
    _report("knife-one", reds, greens)
    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"


def test_knife_two_a_silent_empty_receipt_reddens_the_r373_family(client, monkeypatch):
    """刀二：折成空回执（静默吞）⇒ 必须红在 R373 那族钉上，不只是红在本件新件上。"""
    _approval_ledger_grid(monkeypatch)
    before = _sha(OUTLET_PY)
    reds: list = []
    greens: list = []
    with _mutate(OUTLET_PY, KNIFE_TWO) as info:
        reds.append(_must_go_red(_r373_dismiss_writes_nothing, client, monkeypatch))
        reds.append(_must_go_red(r373._check_dismiss_survives_the_refusal, client))
        reds.append(_must_go_red(
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, READ_PATH))
        reds.append(_must_go_red(
            test_the_refusal_writes_no_reader_state_and_no_receipt, client, monkeypatch, DISMISS_PATH))
        reds.append(_must_go_red(
            test_a_mixed_batch_refuses_the_whole_call_before_recording_anything, client, monkeypatch))
        reds.append(_must_go_red(shape.test_neither_storage_handler_returns_a_receipt))
        reds.append(_must_go_red(
            shape.test_each_storage_handler_raises_exactly_one_503_and_chains_the_original))
        reds.append(_must_go_red(shape.test_the_module_still_emits_exactly_two_503_raises))
        greens.append(_stays_green("r373:write_side_still_asks", r373._check_write_side_asks_and_refuses))
        greens.append(_stays_green("r381:inbox_200",
            test_the_inbox_still_answers_200_with_the_absent_leg_when_the_ledger_is_missing, client, monkeypatch))
    _report("knife-two", reds, greens)
    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"


def test_knife_three_merging_the_id_error_reddens_the_roster_and_the_data_grid(client, monkeypatch):
    """刀三：把入参那一格并进 503 ⇒ 两枚名单钉 + 折叠位置钉 + 数据损坏那一格各红一次。

    503 那一格自身、401 与 not_addressable 那两格都不许被这把刀带歪 —— 并脸的红必须只出现在
    「名单多了一枚」与「那枚损坏的行被发了一张迁移处方」这两处。
    """
    _approval_ledger_grid(monkeypatch)
    before = _sha(OUTLET_PY)
    reds: list = []
    greens: list = []
    with _mutate(OUTLET_PY, KNIFE_THREE) as info:
        reds.append(_must_go_red(shape.test_the_outlet_roster_is_exactly_the_six_ratified_names))
        reds.append(_must_go_red(shape.test_this_ticket_grew_the_roster_by_exactly_one_named_type))
        reds.append(_must_go_red(shape.test_the_ledger_type_is_folded_at_the_write_exit_only))
        reds.append(_must_go_red(test_a_corrupt_stored_state_is_not_washed_into_a_storage_answer, client))
        greens.append(_stays_green("r381pins:two_storage_handlers",
            shape.test_the_storage_handlers_are_exactly_two_one_read_one_write))
        greens.append(_stays_green("r381:401_guard", test_the_anonymous_guard_itself_raises_the_401_face))
        greens.append(_stays_green("r381:not_addressable",
            test_an_unaddressable_id_keeps_its_own_receipt_while_the_ledger_is_missing, client, monkeypatch, READ_PATH))
        greens.append(_stays_green("r381:503_face",
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, READ_PATH))
    _report("knife-three", reds, greens)
    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"


def test_knife_four_merging_401_reddens_the_permission_grid(client, monkeypatch):
    """刀四：把权限那一格折成 503 ⇒ 401 行为钉与面集合钉各红一次；本单的折叠自身不许被带歪。"""
    _approval_ledger_grid(monkeypatch)
    before = _sha(OUTLET_PY)
    reds: list = []
    greens: list = []
    with _mutate(OUTLET_PY, KNIFE_FOUR) as info:
        reds.append(_must_go_red(test_the_anonymous_guard_itself_raises_the_401_face))
        reds.append(_must_go_red(shape.test_the_fold_added_no_error_face_and_reuses_a_ratified_code))
        reds.append(_must_go_red(shape.test_the_module_still_emits_exactly_two_503_raises))
        greens.append(_stays_green("r381:503_face",
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, READ_PATH))
        greens.append(_stays_green("r381:422_face",
            test_a_malformed_id_still_answers_422_while_the_ledger_is_missing, client, monkeypatch))
    _report("knife-four", reds, greens)
    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"


def test_knife_five_widening_the_read_exit_reddens_the_reachability_pins(client, monkeypatch):
    """刀五：往读出口也接一次那枚账本错 ⇒ 可达性那四枚钉各红一次；本单写侧那一格不许被带歪。

    判据①说「拿不出抛出链的不许进折叠名单」，这把刀就是那句话的对照面：往读出口多接一枚，红的既有
    三枚形状钉（名单枚数、只长那一枚、折叠只在写侧），也有「读出口今天不接它」那枚行为钉 —— 也就是
    R373 刀一在读出口量到的那张裸 500 脸，被悄悄洗成了 503。R376 那枚名单钉不在受害者名单里：它的
    `_tree` 直读盘上字节（不是 overlay 的当前视图），窗里的变异对它不可见 —— 那一枚按交付态读数交回。
    """
    _approval_ledger_grid(monkeypatch)
    before = _sha(OUTLET_PY)
    reds: list = []
    greens: list = []
    def _with_restored_inbox(pin, *args):
        """两枚替身钉会把 `build_inbox` 桩在模块字典里；逐枚还原，别把后面那枚绿判成串台。"""
        saved = notifications_api.build_inbox
        try:
            return pin(*args)
        finally:
            notifications_api.build_inbox = saved

    with _mutate(OUTLET_PY, KNIFE_FIVE) as info:
        reds.append(_must_go_red(shape.test_the_outlet_roster_is_exactly_the_six_ratified_names))
        reds.append(_must_go_red(shape.test_this_ticket_grew_the_roster_by_exactly_one_named_type))
        reds.append(_must_go_red(shape.test_the_ledger_type_is_folded_at_the_write_exit_only))
        greens.append(_stays_green("r381:503_face",
            test_a_missing_approval_ledger_answers_503_on_both_write_exits, client, monkeypatch, READ_PATH))
        greens.append(_stays_green("r381:inbox_200",
            test_the_inbox_still_answers_200_with_the_absent_leg_when_the_ledger_is_missing, client, monkeypatch))
        greens.append(_stays_green("r381pins:two_503_raises",
            shape.test_the_module_still_emits_exactly_two_503_raises))
        reds.append(_must_go_red(_with_restored_inbox,
            test_the_read_exit_call_itself_lets_that_ledger_refusal_through, monkeypatch,
            label="test_the_read_exit_call_itself_lets_that_ledger_refusal_through"))
        greens.append(_stays_green(
            "r381:http_read_bare(路由持旧函数对象：窗里改读出口，HTTP 读不到，故用直调那枚)",
            _with_restored_inbox, test_the_read_exit_leaves_that_ledger_refusal_untranslated, client, monkeypatch))
    _report("knife-five", reds, greens)
    assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == before, "反证窗碰过盘上的文件：字节凭据不对"


def test_the_counter_evidence_windows_leave_the_disk_alone(client, monkeypatch):
    """五把刀共同的字节凭据：窗内只有影子副本被改，盘上那枚出口与 R373 那一族全程一字不动。"""
    outlet_before = _sha(OUTLET_PY)
    inbox_before = _sha(r373.INBOX_PY)
    sources_before = _sha(r373.SOURCES_PY)

    for knife in (KNIFE_ONE, KNIFE_TWO, KNIFE_THREE, KNIFE_FOUR, KNIFE_FIVE):
        with _mutate(OUTLET_PY, knife) as info:
            assert overlay.open_windows() == (overlay.rel_of(OUTLET_PY),), "开着的窗不止本件那一扇"
            assert _sha(OUTLET_PY) == outlet_before, "窗内盘上那枚文件就被碰了"
        assert overlay.open_windows() == (), "出窗没关干净"
        assert info["restored"] is True and info["after"] == info["before"]
    assert _sha(OUTLET_PY) == outlet_before, "盘上的出口文件被反证窗碰过"
    assert _sha(r373.INBOX_PY) == inbox_before, "本件的窗不许碰 R373 那一族的文件"
    assert _sha(r373.SOURCES_PY) == sources_before, "本件的窗不许碰 sources.py"