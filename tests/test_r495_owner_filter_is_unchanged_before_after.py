# -*- coding: utf-8 -*-
"""R495 判据①：会话归属三档在**改前改后逐枚相等**（admin / evalbot / staff）。

「改前」不是回忆，也不是我自己另写的一份算式：

* 影子根外面那枚基点文件由 `git show HEAD:app/storage/sessions.py` 现取（本单未 commit，
  HEAD 即基点 438d67d），用 `importlib` 单独载成一枚私有模块 ⇒ 今天生产代码用的那把**旧尺**；
* 出口成员集合另取 R484 交回的那枚纯函数内核 `scripts/r484_session_read_leg_ledger.py::
  visible_ids` 算一遍 ⇒ 纸上判据与真闸门用的是同一把尺，不分叉；
* 再把真路由 `GET /api/v1/sessions` 跑一遍 ⇒ 三样读数一枚不差才算「行为不变面」成立。

夹具是**形状副本**，不是生产读数（与 R484 同一口径）：成员全是 `r495-snap-*` 合成 id，
库行 1020 枚 = admin 336 + evalbot 656 + 五枚孤儿名 28，台账 1027 行 = 上述 1020 + 7 枚
只落在台账里的 ghost binding ⇒ admin 台账 343 对库里 336，那 7 枚永不进出口。生产数以
`python scripts/r484_session_read_leg_ledger.py --live` 现读为准。

这条判据为什么在离线夹具上就能成立：会话归属那一句判定今天全部住在
`app/storage/sessions.py` 里，它只吃两样东西——台账自己的字节与 principal 自己的字段。
所以「改前改后逐枚相等」不需要真库、不需要模型、不需要端口：把同一份台账字节交给新旧两把
尺，成员必须一枚不差；把同一批库行交给真路由，出口必须等于内核算出来的那一套。
全程 `DATABASE_URL` 由 `tests/conftest.py` 钉在保留端口 127.0.0.1:1，盘上零写入。
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common import auth
from app.common.auth import create_token
from app.storage import sessions as sessions_module
from tests import _temp_edit_overlay as overlay

REPO = overlay.REPO
SESSIONS_REL = "app/storage/sessions.py"
LEDGER = importlib.import_module("scripts.r484_session_read_leg_ledger")

ADMIN = "admin"
EVALBOT = "evalbot"
STAFF = "r495-staff-finance"
#: 孤儿：库里挂着它的 user_id，但 users 表里已经没有这个人（R484 现取的那五枚名）。
ORPHAN_COUNTS = {"browser-e2e-mgr": 9, "r8-probe-a": 8, "browser-e2e-rv": 6,
                 "r8-probe-b": 3, "browser-e2e-tester": 2}
#: R484 交回的 09-29 那一格形状：库里 336 / 656 / 28，台账再叠 7 枚 ghost binding。
DB_COUNTS = {ADMIN: 336, EVALBOT: 656}
GHOST_BINDINGS = 7
#: 三档：admin 与 evalbot 是有会话的两枚 admin，staff 是有部门却零会话的员工。
SHAPES = (ADMIN, EVALBOT, STAFF)


def _user_row(username: str, role: str = "staff", department: str = "") -> dict:
    """真源今天交给的形状：查人不带 id，所以 principal.user_id 就是用户名。"""
    return {"username": username, "role": role, "department": department}


def _principal(username: str, role: str = "staff", department: str = "") -> Principal:
    return Principal.from_user(_user_row(username, role, department))


def _snapshot() -> tuple:
    """(库行[出口形状], 台账行[R495 之前的字节形状], {档: 成员有序列表})。"""
    members, db_rows, ledger_rows = {}, [], []
    for name, size in DB_COUNTS.items():
        ids = ["r495-snap-%s-%04d" % (name, index) for index in range(size)]
        members[name] = ids
        db_rows += [{"id": sid, "title": sid, "user_id": name} for sid in ids]
        ledger_rows += [_ledger_row(sid, name) for sid in ids]
    for name, size in ORPHAN_COUNTS.items():
        ids = ["r495-snap-orphan-%s-%02d" % (name, index) for index in range(size)]
        members[name] = ids
        db_rows += [{"id": sid, "title": sid, "user_id": name} for sid in ids]
        ledger_rows += [_ledger_row(sid, name) for sid in ids]
    ghost = ["r495-snap-ghost-%02d" % index for index in range(GHOST_BINDINGS)]
    ledger_rows += [_ledger_row(sid, ADMIN) for sid in ghost]
    members[STAFF] = []
    assert len(db_rows) == 1020 and len(ledger_rows) == 1027, (
        "副本形状漂了（库 %d / 台账 %d），本件不再对应 09-29 交回的那一格"
        % (len(db_rows), len(ledger_rows))
    )
    expected = {name: sorted(members[name]) for name in SHAPES}
    return db_rows, ledger_rows, expected


def _ledger_row(session_id: str, owner: str) -> dict:
    return {"session_id": session_id, "owner_id": owner, "status": "active",
            "created_at": "2026-09-29T00:00:00+00:00"}


def _kernel_rows(db_rows: list) -> list:
    """内核吃 `session_id`，路由吃 `id`：同一批行换两枚键名，不是两批数据。"""
    return [{"session_id": row["id"], "user_id": row["user_id"]} for row in db_rows]


def _write_ledger(path, ledger_rows: list):
    """按 R495 之前的字面形状落台账：`{"sessions": [...]}`、`ensure_ascii`、`sort_keys`。"""
    path.write_text(
        json.dumps({"sessions": ledger_rows}, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )


def _pristine_text(rel: str) -> str:
    out = subprocess.run(
        ["git", "show", "HEAD:" + rel],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert out.returncode == 0, "git show HEAD:%s 失败：%s" % (rel, out.stderr)
    return out.stdout


@pytest.fixture(scope="module")
def pristine():
    """基点那份 `app/storage/sessions.py` 单独载成一枚私有模块：今天生产代码用的那把旧尺。"""
    text = _pristine_text(SESSIONS_REL)
    assert "SESSION_OWNER_NAMESPACE" not in text, (
        "git show HEAD:%s 交回的已经不是基点那份字了：本件的「改前」不成立" % SESSIONS_REL
    )
    directory = Path(tempfile.mkdtemp(prefix="r495-pristine-"))
    target = directory / "r495_pristine_sessions_src.py"
    target.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("r495_pristine_sessions", target)
    module = importlib.util.module_from_spec(spec)
    #: 必须先登记再执行：`@dataclass` 在求值注解时要能从 `sys.modules` 找到宿主模块，
    #: 否则 `dataclasses._is_type` 拿到 None 就炸（这是装载姿势的问题，与被测代码无关）。
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


@pytest.fixture()
def snapshot(tmp_path):
    db_rows, ledger_rows, expected = _snapshot()
    path = tmp_path / "r495-snapshot-ledger.json"
    _write_ledger(path, ledger_rows)
    return db_rows, ledger_rows, expected, path


# ============================================================================
# 一、同一份台账字节交给新旧两把尺：成员必须逐枚相等
# ============================================================================


def test_the_same_ledger_bytes_give_the_same_members_before_and_after(snapshot, pristine):
    db_rows, _ledger_rows, expected, path = snapshot
    before = pristine.SessionRegistry(path)
    after = sessions_module.SessionRegistry(path)

    for name in SHAPES:
        principal = _principal(name, "admin" if name in DB_COUNTS else "staff",
                               "财务部" if name == STAFF else "")
        rows = [row["id"] for row in db_rows]
        seen_before = sorted(sid for sid in rows if before.is_owned_by(sid, principal))
        seen_after = sorted(sid for sid in rows if after.is_owned_by(sid, principal))
        diff = LEDGER.member_diff(set(seen_before), set(seen_after))
        assert diff["members_equal"], (
            "档=%s 谓词=改前(record.owner_id==str(principal.user_id)) vs 改后(session_owner_key) | "
            "成员不等: 改前 %d 枚 / 改后 %d 枚, 差=%s"
            % (name, diff["count_a"], diff["count_b"],
               (diff["only_in_a"] + diff["only_in_b"])[:5])
        )
        assert seen_after == expected[name], (
            "档=%s 谓词=改后 | 出口成员不等于 09-29 交回的那一格: 应 %d 枚 / 实 %d 枚, 差=%s"
            % (name, len(expected[name]), len(seen_after),
               sorted(set(seen_after) ^ set(expected[name]))[:5])
        )


def test_the_pinned_kernel_and_the_shipped_gate_agree_member_by_member(snapshot, pristine):
    """三样读数一起对：内核算的、旧尺判的、新尺判的。任何一格单独漂了都要点名。"""
    db_rows, ledger_rows, _expected, path = snapshot
    kernel_rows = _kernel_rows(db_rows)
    before = pristine.SessionRegistry(path)
    after = sessions_module.SessionRegistry(path)
    for name in (ADMIN, EVALBOT, STAFF):
        should = LEDGER.visible_ids(kernel_rows, ledger_rows, name)
        principal = _principal(name, "admin" if name in DB_COUNTS else "staff")
        got_before = {row["id"] for row in db_rows if before.is_owned_by(row["id"], principal)}
        got_after = {row["id"] for row in db_rows if after.is_owned_by(row["id"], principal)}
        for label, got in (("改前", got_before), ("改后", got_after)):
            diff = LEDGER.member_diff(should, got)
            assert diff["members_equal"], (
                "档=%s 谓词=内核 vs %s | 成员不等: 内核 %d 枚 / 闸门 %d 枚, 差=%s"
                % (name, label, diff["count_a"], diff["count_b"],
                   (diff["only_in_a"] + diff["only_in_b"])[:5])
            )


# ============================================================================
# 二、真路由：出口成员等于内核，且 09-29 那几格数字一枚不动
# ============================================================================


class _UserStore:
    """进程内假用户表：唯一的接管点是「认证查人」，路由与台账全走真的。"""

    def __init__(self, rows):
        self.rows = {row["username"]: dict(row) for row in rows}

    def get_user(self, username):
        row = self.rows.get(username)
        return dict(row) if row else None


def _roster():
    #: 在册的就这三档。那五枚孤儿名**不在** users 表里——它们之所以是孤儿，正因为
    #: 库里还挂着它们的 `user_id`，而查人已经查不到这个人。把它们放进名册就等于自己
    #: 把 28 枚孤儿读成了 0 枚，判据①那格就成了自证的空话。
    return [_user_row(ADMIN, "admin"), _user_row(EVALBOT, "admin"),
            _user_row(STAFF, "staff", "财务部")]


def _exit_ids(username: str, db_rows: list, monkeypatch, registry) -> tuple:
    import app.api.v1.chat as chat
    from app.main import app

    monkeypatch.setattr(auth, "get_user", _UserStore(_roster()).get_user)
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_list_sessions", lambda: [dict(row) for row in db_rows])
    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer " + create_token(username)})
        response = client.get("/api/v1/sessions")
    payload = response.json() if response.status_code == 200 else {}
    return response.status_code, [row.get("id", "") for row in payload.get("sessions", [])]


def test_the_real_route_still_returns_the_09_29_member_sets(snapshot, monkeypatch):
    db_rows, ledger_rows, expected, path = snapshot
    registry = sessions_module.SessionRegistry(path)
    view = LEDGER.ledger_view(
        _kernel_rows(db_rows), ledger_rows, _roster(), (ADMIN, EVALBOT), frozenset({"admin"})
    )
    for name in SHAPES:
        status, seen = _exit_ids(name, db_rows, monkeypatch, registry)
        assert status == 200, "档=%s 出口不再是 200（读到 %s）：显式化不该改对外状态码" % (name, status)
        assert sorted(seen) == expected[name], (
            "档=%s 谓词=is_owned_by(台账 owner_id == session_owner_key) | 出口成员不等于 09-29 "
            "那一格: 应 %d 枚 / 实 %d 枚, 差=%s"
            % (name, len(expected[name]), len(seen), sorted(set(seen) ^ set(expected[name]))[:5])
        )
    counts = {name: len(expected[name]) for name in SHAPES}
    assert (counts[ADMIN], counts[EVALBOT], counts[STAFF]) == (336, 656, 0), (
        "三档读数不再是 336 / 656 / 0（读到 %s）：本件的对照面换了，判据①要重画" % counts
    )
    assert view["orphan_rows"] == 28 and view["orphan_seen_by_any_principal"] == 0, (
        "五枚孤儿名那 28 枚今天被谁看见了（孤儿 %d 枚 / 被见 %d 枚）"
        % (view["orphan_rows"], view["orphan_seen_by_any_principal"])
    )
    cells = view["shapes"]
    assert (cells[ADMIN]["db_rows"], cells[ADMIN]["ledger_rows"], cells[ADMIN]["visible"]) \
        == (336, 343, 336), (
        "档=admin 那一格四列不再是 336 / 343 / 336（读到 %s）：台账超集那 7 枚今天放进了出口"
        % dict(cells[ADMIN])
    )
    assert (cells[EVALBOT]["db_rows"], cells[EVALBOT]["ledger_rows"], cells[EVALBOT]["visible"]) \
        == (656, 656, 656), (
        "档=evalbot 那一格四列不再是 656 / 656 / 656（读到 %s）" % dict(cells[EVALBOT])
    )
    assert len(view["ledger_minus_db"]) == GHOST_BINDINGS, (
        "台账超集那 %d 枚应当一枚都不进出口，今天对出 %d 枚" % (GHOST_BINDINGS, len(view["ledger_minus_db"]))
    )


# ============================================================================
# 三、台账字节与两把尺的关系：旧文件读得回来，新写入的字与基点逐字节同形
# ============================================================================


def test_the_pre_r495_ledger_bytes_are_still_readable_and_unchanged(snapshot, pristine):
    _db_rows, _ledger_rows, _expected, path = snapshot
    before = path.read_bytes()
    registry = sessions_module.SessionRegistry(path)
    assert len(registry._records) == 1027, (
        "基点写下的台账今天只读回 %d 枚：R495 把旧文件读坏了" % len(registry._records)
    )
    assert path.read_bytes() == before, "只是读了一遍台账就改了盘上字节：读腿不许写字"
    reopened = pristine.SessionRegistry(path)
    assert {sid for sid, record in reopened._records.items()} == {
        sid for sid, record in registry._records.items()
    }, "新旧两把尺读同一份字节读出两个条目集合"
    assert [record.owner_id for record in registry._records.values()][:1] == [ADMIN], (
        "台账第一枚条目的 owner_id 不再是用户名字符串：形状漂了"
    )


def test_a_fresh_bind_writes_the_same_bytes_as_the_pristine_gate(tmp_path, pristine):
    """改前改后各绑同一枚会话：落盘的键名与形状必须逐字节同形（只有时间戳允许不同）。"""
    old_registry = pristine.SessionRegistry(tmp_path / "r495-before.json")
    new_registry = sessions_module.SessionRegistry(tmp_path / "r495-after.json")
    principal = _principal(ADMIN, "admin")
    old_record = old_registry.bind("r495-byte-check", principal)
    new_record = new_registry.bind("r495-byte-check", principal)
    old_payload = json.loads(old_registry.metadata_path.read_text(encoding="utf-8"))
    new_payload = json.loads(new_registry.metadata_path.read_text(encoding="utf-8"))
    for record in (old_record, new_record):
        record.created_at = "fixed"
    for payload in (old_payload, new_payload):
        for row in payload["sessions"]:
            row["created_at"] = "fixed"
    assert old_payload == new_payload, (
        "台账字节形状改了：改前 %s / 改后 %s——旧文件与新文件从此不同构"
        % (old_payload, new_payload)
    )
    assert set(new_payload["sessions"][0]) == {
        "session_id", "owner_id", "status", "created_at"
    }, "R495 给台账长出了新列"


def test_the_owner_gate_is_identical_in_both_namespaces(tmp_path, pristine):
    """键整套一致时，新旧两把尺在**任一套**命名空间下给出同一个成员集。

    这一格是「算式仍只许一枚」的正面凭据：R495 没有把归属换成用户名那套键（那会改掉
    R484:406 钉住的判定），它只是把那枚键的来源写成声明并只留一处算式。
    """
    for username, user_id in (("r495-plain", None), ("r495-with-id", 7)):
        row = {"username": username, "role": "admin", "department": ""}
        if user_id is not None:
            row["id"] = user_id
        principal = Principal.from_user(row)
        old_registry = pristine.SessionRegistry(tmp_path / ("r495-old-%s.json" % username))
        new_registry = sessions_module.SessionRegistry(tmp_path / ("r495-new-%s.json" % username))
        for index in range(4):
            session_id = "r495-%s-%d" % (username, index)
            old_registry.bind(session_id, principal)
            new_registry.bind(session_id, principal)
        for index in range(4):
            session_id = "r495-%s-%d" % (username, index)
            assert old_registry.is_owned_by(session_id, principal) == (
                new_registry.is_owned_by(session_id, principal)
            ), "档=%s 命名空间=%r 两把尺在 %s 上给出不同答案" % (
                username, sessions_module.session_owner_namespace(principal), session_id
            )
        stranger = _principal(username + "-stranger", "admin")
        assert new_registry.is_owned_by("r495-%s-0" % username, stranger) is False, (
            "档=%s 外来主体读到了别人的会话：闸门被显式化改松了" % username
        )