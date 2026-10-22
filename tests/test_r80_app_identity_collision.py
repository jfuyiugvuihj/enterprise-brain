"""R80 -- 开放平台应用身份撞号：同名注册必须互不覆盖。

缺陷现场（总控 @6d5f5ab 复现，本文件在同一棵树上独立复现过一次）：
``app/common/open_platform.py`` 用 ``sha256(f"{name}:{time.time_ns()}")`` 生成 ``app_id``，
再用 ``sha256(f"{name}:{app_id}:{time.time_ns()}")`` 生成 ``secret``。本机实测（2026-09-18，
@6d5f5ab 一字未改）：内存态下同名连续注册 4 次只得到 **1** 个 app_id、**1** 个 secret，注册表里
只剩 **1** 条记录；带持久化 store 的同样 4 次注册得到 **2** 个 id、**2** 个 secret、**2** 条记录
（总控在 @6d5f5ab 上测到的正是 2/2）。两次实测里，撞号那一对的 secret 完全相同。链条是：
``_APP_REGISTRY[app_id] = record`` 静默覆盖 -> ``store.upsert(_STORE_COLLECTION, app_id, ...)``
以同一主键写穿持久化 -> 先注册那个应用的 actions / departments / clearance / enabled 被后者
整条换掉，而管理员手里的一次性 secret 是同一个。这不是命名美观问题，是密钥复用 +
授权静默改写。

本文件按判据逐条钉：

① 同名连续注册 4 次 => 4 个互不相同 app_id、4 个互不相同 secret、4 条都在（先红后绿）
② 身份与密钥来自 CSPRNG，不再由时钟派生；格式仍是 16/64 位小写十六进制；
   secret 不得由 app_id 派生（app_id 进列表响应与审计，属半公开值，参与派生 == 密钥可推）
③ 撞号不得静默覆盖：撞上已存在者就重生成；重生成用尽则显式失败，绝不改写别人那一行
④ 同名可以注册成不同应用，但互不覆盖、id 必不相同
⑤ 持久化往返逐字节稳定；store 写失败只回滚自己那一条，不顺手清掉别人的
⑥⑦ 错误码词表一字不动，新拒绝沿用 ``ValueError("...")`` 家族

跑测前先看 ``test_the_cases_in_this_file_never_touch_a_real_registry``：本文件的每一条
都只写自己 tmp 目录里的 store，绝不落到宿主/主树的持久化记录上。
"""

import ast
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path

import pytest

from app.common import audit, open_platform
from app.common.monitoring import ProductionReadOnlyProtection
from app.common.open_platform import (
    build_request_signature,
    clear_app_registry,
    configure_app_store,
    list_applications,
    load_app_registry,
    register_application,
    verify_open_request,
)
from app.storage.persistence import JsonPersistenceAdapter, PersistenceWriteError

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "app" / "common" / "open_platform.py"
COLLECTION = "open_platform_apps"

#: The whole point of the ticket: one name, registered over and over.
TWIN = "r80-twin"
DEPARTMENT_A = "rnd"
DEPARTMENT_B = "ops"

APP_ID_RE = re.compile(r"\A[0-9a-f]{16}\Z")
SECRET_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: Names that mean "a cryptographically secure random source was asked".
CSPRNG_NAMES = {"token_hex", "token_bytes", "token_urlsafe", "randbytes", "getrandbits", "urandom"}


@pytest.fixture(autouse=True)
def _own_the_registry(tmp_path, monkeypatch):
    """Every case gets its own durable store inside its own tmp dir, in both directions.

    A registry leak here would rewrite the host application store, so the store path is
    pinned before the case runs and released after it, exactly like R78 owns the surfaces
    it touches.
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(_store_file(tmp_path)))
    configure_app_store(str(_store_file(tmp_path)))
    clear_app_registry()
    # The clock is part of the defect, not part of the evidence: whether a burst of
    # registrations sees the same ``time_ns()`` twice depends on how fast this machine's
    # system clock ticks, which is why the raw reproduction is sometimes green. Model the
    # documented Windows granularity (about 1/64 s) instead of hoping for it, so every
    # case below rules the same way on any machine.
    _coarsen_clock(monkeypatch)
    audit.reset_audit_storage()
    audit.clear_audit_events()
    yield
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    configure_app_store("")
    clear_app_registry()
    monkeypatch.undo()
    audit.reset_audit_storage()
    audit.clear_audit_events()


def _store_file(tmp_path) -> Path:
    return tmp_path / "apps.json"


def _register(name=TWIN, *, actions=("query",), departments=(), max_clearance=3, description=""):
    return register_application(
        name,
        allowed_actions=list(actions),
        allowed_departments=list(departments),
        max_clearance=max_clearance,
        description=description,
    )


def _registry_rows() -> dict[str, dict]:
    """The live registry as an administrator sees it, keyed by app id."""
    return {row["app_id"]: row for row in list_applications()}


def _stored_rows(tmp_path) -> dict[str, dict]:
    """The durable rows, keyed by app id, read back without going through the cache."""
    rows = JsonPersistenceAdapter(str(_store_file(tmp_path))).list(COLLECTION)
    return {str(row.get("app_id")): row for row in rows}


def _grant(row: dict) -> dict:
    """Everything a registration grants, in the shape both stores and rows agree on."""
    return {
        "app_name": row["app_name"],
        "allowed_actions": list(row["allowed_actions"]),
        "allowed_departments": list(row["allowed_departments"]),
        "max_clearance": int(row["max_clearance"]),
        "enabled": bool(row["enabled"]),
        "description": str(row["description"]),
    }


def _signed(app_id: str, secret: str, body: str, *, department=None, user=None) -> dict:
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_id,
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_id, secret, body, timestamp),
    }
    if department is not None:
        headers["X-Open-Department"] = department
    if user is not None:
        headers["X-Open-User"] = user
    return headers


def _replay_ids(monkeypatch, values):
    """Script the identity mint: hand back ``values`` in order, then repeat the last one.

    This is how a collision is forced without waiting for one. A 64-bit id never collides
    on its own; the guard that has to survive is the code path for when it does.
    """
    queue = list(values)

    def _next_id() -> str:
        return queue.pop(0) if queue else values[-1]

    monkeypatch.setattr(open_platform, "_new_app_id", _next_id)
    return _next_id


#: Windows advances the system clock about 64 times a second, so two adjacent
#: ``time.time_ns()`` calls legitimately return the same value. Measured here: 933 calls
#: in a row before it moved by one tick.
SYSTEM_TICK_NS = 15_625_000


def _coarsen_clock(monkeypatch, step_ns: int = SYSTEM_TICK_NS):
    real_time_ns = open_platform.time.time_ns
    monkeypatch.setattr(open_platform.time, "time_ns", lambda: (real_time_ns() // step_ns) * step_ns)


#: The clock is not allowed to matter, so one case pins it dead instead of ticking.
FROZEN_NS = 1_700_000_000_123_456_789


def _freeze_clock(monkeypatch):
    """The extreme case of the same bug: the clock never moves at all."""
    monkeypatch.setattr(open_platform.time, "time_ns", lambda: FROZEN_NS)


# ------------------------------------------------------------------ source guards ②


#: A wall clock in any spelling: identity must not be a function of when it was minted.
CLOCK_WORDS = {"time_ns", "time", "monotonic", "localtime", "utcnow", "perf_counter", "strftime"}
#: A digest in any spelling: identity must not be a hash of anything.
HASH_CALLS = {"sha256", "sha1", "sha224", "sha384", "sha512", "md5", "blake2b", "blake2s", "new", "hash"}


def _module_tree() -> ast.Module:
    # utf-8-sig: the module under guard is written with a byte-order mark.
    return ast.parse(MODULE.read_text(encoding="utf-8-sig"))


def _local_functions(tree) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _identity_producers() -> dict[str, list[ast.expr]]:
    """Every expression in the module that produces an ``app_id`` or a ``secret``.

    Read paths are included on purpose: what a payload hands back is also an identity, and
    nothing about it may come from the clock, a digest, or the other identifier either.
    """
    producers: dict[str, list[ast.expr]] = {"app_id": [], "secret": []}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
            value = node.value
        elif isinstance(node, ast.keyword) and node.arg in producers:
            producers[node.arg].append(node.value)
            continue
        else:
            continue
        if value is None:
            continue
        for name in names:
            if name in producers:
                producers[name].append(value)
    return producers


def _reachable(expression, functions) -> tuple[set[str], set[str], set[str]]:
    """Identifiers, calls, and the calls reached through one local helper after another.

    A mint that hides behind ``_derive_secret(app_id)`` is still a mint that reads
    ``app_id``, so the guard follows local functions instead of stopping at the call
    boundary. Prose is left out deliberately: docstrings talk about the old derivation,
    and a comment is not a data flow.
    """
    pending = [expression]
    walked: set[str] = set()
    names: set[str] = set()
    calls: set[str] = set()
    while pending:
        node = pending.pop()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            elif isinstance(child, ast.Attribute):
                names.add(child.attr)
            elif isinstance(child, ast.arg):
                names.add(child.arg)
            elif isinstance(child, ast.keyword) and child.arg:
                names.add(child.arg)
            elif isinstance(child, ast.Call):
                called = child.func.id if isinstance(child.func, ast.Name) else getattr(child.func, "attr", "")
                if not called:
                    continue
                calls.add(called)
                helper = functions.get(called)
                if helper is not None and helper.name not in walked:
                    walked.add(helper.name)
                    pending.append(helper)
    return {item.lower() for item in names}, {item.lower() for item in calls}, calls

# --------------------------------------------------------------- ① 复现：四条都要在


def test_four_same_name_registrations_yield_four_distinct_identities(tmp_path):
    """The reproduction. Four registrations of one name must be four applications.

    Red on the mint it was written against, and red the same way on any machine: the
    fixture models the clock granularity the defect depended on (``_coarsen_clock``)
    instead of waiting for a tick to happen to repeat. Measured on the old mint this
    case returned two ids for four registrations -- the same 2-of-4 the controller
    reported -- while a bare process with no store write in the way returned one id for
    all four. The assertion below is the shape of the damage, not a count of luck.
    """
    issued = [
        _register(actions=("query", "dashboard"), departments=(DEPARTMENT_A, DEPARTMENT_B), max_clearance=4, description=f"n{index}")
        for index in range(4)
    ]

    app_ids = [row["app_id"] for row in issued]
    secrets = [row["secret"] for row in issued]

    assert len(set(app_ids)) == 4, app_ids
    assert len(set(secrets)) == 4, secrets
    assert len({(row["app_id"], row["secret"]) for row in issued}) == 4, issued

    rows = _registry_rows()
    assert sorted(rows) == sorted(app_ids), rows
    assert [row["app_name"] for row in list_applications()] == [TWIN] * 4
    assert all("secret" not in row for row in list_applications()), list_applications()

    stored = _stored_rows(tmp_path)
    assert len(stored) == 4, sorted(stored)
    assert {str(row.get("description")) for row in stored.values()} == {"n0", "n1", "n2", "n3"}, stored


# ------------------------------------------------- ④ 同名可注册，但互不覆盖


def test_a_second_same_name_registration_replaces_nothing_of_the_first(tmp_path):
    """The consequence chain: the first application's whole grant has to survive."""
    first = _register(actions=("query",), departments=(DEPARTMENT_A,), max_clearance=4, description="first")
    second = _register(actions=("dashboard",), departments=(DEPARTMENT_B,), max_clearance=2, description="second")

    assert first["app_id"] != second["app_id"], (first, second)
    assert first["secret"] != second["secret"], (first, second)

    rows = _registry_rows()
    assert _grant(rows[first["app_id"]]) == _grant(
        {"app_name": TWIN, "allowed_actions": ["query"], "allowed_departments": [DEPARTMENT_A], "max_clearance": 4, "enabled": True, "description": "first"}
    ), rows[first["app_id"]]
    assert _grant(rows[second["app_id"]]) == _grant(
        {"app_name": TWIN, "allowed_actions": ["dashboard"], "allowed_departments": [DEPARTMENT_B], "max_clearance": 2, "enabled": True, "description": "second"}
    ), rows[second["app_id"]]

    stored = _stored_rows(tmp_path)
    assert len(stored) == 2, sorted(stored)
    assert stored[first["app_id"]]["allowed_actions"] == ["query"], stored[first["app_id"]]
    assert stored[first["app_id"]]["secret"] == first["secret"], "the write-through clobbered the row it landed on"
    assert stored[second["app_id"]]["secret"] == second["secret"], stored[second["app_id"]]


def test_the_first_application_keeps_signing_only_its_own_requests():
    """Credentials, not bookkeeping: after the second registration the first secret
    must still authenticate the first application, and only with its own permissions."""
    from fastapi import HTTPException

    first = _register(actions=("query",), departments=(DEPARTMENT_A,))
    second = _register(actions=("dashboard",), departments=(DEPARTMENT_B,))
    body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)

    principal, record = verify_open_request(
        _signed(first["app_id"], first["secret"], body, department=DEPARTMENT_A), body, required_action="query"
    )
    assert record["app_id"] == first["app_id"]
    assert record["app_name"] == TWIN
    assert principal.department == DEPARTMENT_A

    # The second registration must not have handed the first id a dashboard grant.
    with pytest.raises(HTTPException) as forbidden:
        verify_open_request(
            _signed(first["app_id"], first["secret"], body, department=DEPARTMENT_A), body, required_action="dashboard"
        )
    assert forbidden.value.status_code == 403, forbidden.value.detail

    # And the second application's secret must not sign for the first application.
    with pytest.raises(HTTPException) as unsigned:
        verify_open_request(
            _signed(first["app_id"], second["secret"], body, department=DEPARTMENT_B), body, required_action="query"
        )
    assert unsigned.value.status_code == 401, unsigned.value.detail


# ---------------------------------------------------------- ② 格式与时钟无关


def test_the_issued_identifiers_keep_the_published_format():
    """16 hex characters for the id, 64 for the secret: rows are persisted as strings."""
    for _ in range(5):
        issued = _register()
        assert APP_ID_RE.match(issued["app_id"]), issued["app_id"]
        assert SECRET_RE.match(issued["secret"]), issued["secret"]
        assert len(issued["app_id"]) == 16, issued["app_id"]
        assert len(issued["secret"]) == 64, issued["secret"]


def test_a_frozen_clock_still_issues_distinct_identities(monkeypatch):
    """The mint may not read the clock at all: freeze it and four ids must still differ."""
    _freeze_clock(monkeypatch)

    issued = [_register() for _ in range(4)]

    assert len({row["app_id"] for row in issued}) == 4, issued
    assert len({row["secret"] for row in issued}) == 4, issued
    assert len(_registry_rows()) == 4, _registry_rows()


def test_the_identity_is_minted_by_a_cryptographic_source_and_never_by_the_clock():
    """Source, not sentiment: nothing that mints an identity reads time or runs a digest."""
    producers = _identity_producers()
    functions = _local_functions(_module_tree())

    assert producers["app_id"], "nothing in this module produces an app id any more"
    assert producers["secret"], "nothing in this module produces a secret any more"

    for kind, expressions in producers.items():
        for expression in expressions:
            names, calls, _raw = _reachable(expression, functions)
            assert not names & CLOCK_WORDS, (kind, ast.dump(expression), sorted(names & CLOCK_WORDS))
            assert not calls & HASH_CALLS, (kind, ast.dump(expression), sorted(calls & HASH_CALLS))

    for kind in ("app_id", "secret"):
        drawn = [node for node in producers[kind] if _reachable(node, functions)[1] & CSPRNG_NAMES]
        assert drawn, f"{kind} is not drawn from a cryptographic random source"


def test_the_secret_is_not_derived_from_the_app_id(monkeypatch):
    """The app id is semi-public, so it may not be an ingredient in the secret.

    It is in the administrator's application list and in every audit row this transport
    writes, because ``open_actor_username`` is built from it. A secret computed from the
    id is one that anybody with read access to the list can recompute offline.
    """
    producers = _identity_producers()
    functions = _local_functions(_module_tree())

    for expression in producers["secret"]:
        names, _calls, _raw = _reachable(expression, functions)
        offenders = sorted(item for item in names if "app_id" in item)
        assert offenders == [], (ast.dump(expression), offenders)

    _freeze_clock(monkeypatch)
    issued = [_register(), _register()]

    for row in issued:
        app_id = row["app_id"]
        guesses = {
            hashlib.sha256(app_id.encode("utf-8")).hexdigest(),
            hashlib.sha256(f"{TWIN}:{app_id}".encode("utf-8")).hexdigest(),
            hashlib.sha256(f"{app_id}:{FROZEN_NS}".encode("utf-8")).hexdigest(),
            hashlib.sha256(f"{TWIN}:{app_id}:{FROZEN_NS}".encode("utf-8")).hexdigest(),
        }
        assert row["secret"] not in guesses, "the secret is a function of the half-public app id"
    assert len({row["app_id"] for row in issued}) == 2, issued
    assert len({row["secret"] for row in issued}) == 2, issued

# ------------------------------------------------------------- ③ 撞号护栏


def test_a_colliding_app_id_is_regenerated_instead_of_overwriting(tmp_path, monkeypatch):
    """Force the collision the 64-bit id will not find on its own."""
    first = _register(actions=("query",), departments=(DEPARTMENT_A,), max_clearance=4, description="first")
    taken_id = first["app_id"]
    fresh_id = "deadbeefdeadbeef"
    _replay_ids(monkeypatch, [taken_id, fresh_id])

    second = _register(actions=("dashboard",), departments=(DEPARTMENT_B,), max_clearance=2, description="second")

    assert second["app_id"] == fresh_id, second
    rows = _registry_rows()
    assert sorted(rows) == sorted([taken_id, fresh_id]), rows
    assert _grant(rows[taken_id])["description"] == "first", rows[taken_id]
    assert _grant(rows[taken_id])["allowed_actions"] == ["query"], rows[taken_id]
    assert _grant(rows[fresh_id])["allowed_actions"] == ["dashboard"], rows[fresh_id]

    stored = _stored_rows(tmp_path)
    assert stored[taken_id]["secret"] == first["secret"], "the guard let a colliding id write through"
    assert len(stored) == 2, sorted(stored)


def test_a_colliding_app_id_held_by_another_worker_is_not_overwritten(tmp_path, monkeypatch):
    """The durable row can exist while this process has never seen it.

    A second worker registered the id and this cache was dropped, so an in-memory check
    alone would let the write-through replace a live application. The store is part of
    the guard for exactly that case.
    """
    first = _register(actions=("query",), departments=(DEPARTMENT_A,), description="owned-elsewhere")
    taken_id = first["app_id"]
    clear_app_registry()
    fresh_id = "cafebabecafebabe"
    _replay_ids(monkeypatch, [taken_id, fresh_id])

    second = _register(actions=("dashboard",), description="mine")

    assert second["app_id"] == fresh_id, second
    stored = _stored_rows(tmp_path)
    assert len(stored) == 2, sorted(stored)
    assert stored[taken_id]["description"] == "owned-elsewhere", stored[taken_id]
    assert stored[taken_id]["secret"] == first["secret"], stored[taken_id]
    assert stored[taken_id]["allowed_actions"] == ["query"], stored[taken_id]


def test_exhausted_id_generation_refuses_instead_of_replacing_a_live_row(tmp_path, monkeypatch):
    """When every draw is taken the registration fails; it does not overwrite.

    The refusal stays in the family the module already uses -- a bare
    ``ValueError("snake_case")`` -- because the ratified error-code vocabulary is closed.
    """
    first = _register(actions=("query",), departments=(DEPARTMENT_A,), description="first")
    _replay_ids(monkeypatch, [first["app_id"]])

    with pytest.raises(ValueError) as refused:
        _register(actions=("dashboard",), description="second")

    message = str(refused.value)
    assert re.fullmatch(r"[a-z0-9_]+", message), message
    assert "app_id" in message, message
    rows = _registry_rows()
    assert list(rows) == [first["app_id"]], rows
    assert _grant(rows[first["app_id"]])["description"] == "first", rows[first["app_id"]]
    stored = _stored_rows(tmp_path)
    assert list(stored) == [first["app_id"]], sorted(stored)
    assert stored[first["app_id"]]["allowed_actions"] == ["query"], stored[first["app_id"]]


def test_the_registration_route_reports_the_refusal_as_a_400(monkeypatch, tmp_path):
    """The admin surface already turns the ValueError family into a 400; the new refusal
    must ride that path instead of reaching the caller as an unhandled 500."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.agents.contracts import Principal
    from app.api.v1 import open_platform as routes

    first = _register(actions=("query",))
    _replay_ids(monkeypatch, [first["app_id"]])
    principal = Principal.from_user({"id": "root", "username": "root", "role": "admin", "department": "it"})
    request = SimpleNamespace(state=SimpleNamespace(username=principal.username, principal=principal), headers={})

    with pytest.raises(HTTPException) as refused:
        asyncio.run(
            routes.register_open_application(
                routes.ApplicationRegisterRequest(app_name=TWIN, allowed_actions=["dashboard"]), request
            )
        )

    assert refused.value.status_code == 400, refused.value.detail
    assert _grant(_registry_rows()[first["app_id"]])["allowed_actions"] == ["query"], _registry_rows()


# ----------------------------------------------------------- ⑤ 持久化往返


def test_a_registration_round_trips_through_the_store_byte_for_byte(tmp_path):
    """Restart must not move a single byte of an identity or a grant."""
    issued = [
        _register(actions=("query",), departments=(DEPARTMENT_A,), max_clearance=4, description="first"),
        _register(actions=("query", "dashboard"), departments=(DEPARTMENT_B,), max_clearance=2, description="second"),
    ]
    grants_before = {row["app_id"]: _grant(_registry_rows()[row["app_id"]]) for row in issued}
    stored_before = _stored_rows(tmp_path)
    assert len(stored_before) == 2, sorted(stored_before)

    clear_app_registry()
    assert load_app_registry() == 2
    rows = _registry_rows()
    assert sorted(rows) == sorted(row["app_id"] for row in issued), rows
    for row in issued:
        assert _grant(rows[row["app_id"]]) == grants_before[row["app_id"]], rows[row["app_id"]]

    # A real restart: the cache is dropped with the store handle and rebuilt from disk.
    configure_app_store(str(_store_file(tmp_path)))
    clear_app_registry()
    assert load_app_registry() == 2
    assert _stored_rows(tmp_path) == stored_before, "the round trip rewrote a row"
    for row in issued:
        assert _grant(_registry_rows()[row["app_id"]]) == grants_before[row["app_id"]]

    # Every credential is still the one that was handed out, after a restart and through
    # the durable round trip: an id or secret that moved would authenticate as nothing.
    body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)
    for row in issued:
        _principal, record = verify_open_request(
            _signed(row["app_id"], row["secret"], body, department=_single_department(row["app_id"], tmp_path)),
            body,
            required_action="query",
        )
        assert record["app_id"] == row["app_id"], record
        assert record["secret"] == row["secret"], "the secret survived the wire but not the store"


def _single_department(app_id: str, tmp_path) -> str:
    departments = [str(item) for item in (_stored_rows(tmp_path)[app_id].get("allowed_departments") or [])]
    assert len(departments) == 1, departments
    return departments[0]


def test_the_cases_in_this_file_never_touch_a_real_registry(tmp_path):
    """Tripwire for this file: the store it writes must live inside this case's tmp dir."""
    resolved = Path(str(open_platform._STORE["path"])).resolve()
    assert resolved == _store_file(tmp_path).resolve(), resolved
    assert os.path.normcase(str(resolved)).startswith(os.path.normcase(str(tmp_path.resolve()))), resolved

    monkey_env = os.environ.get("OPEN_PLATFORM_APP_STORE_PATH")
    assert monkey_env and os.path.normcase(str(Path(monkey_env).resolve())) == os.path.normcase(str(resolved)), monkey_env


@pytest.mark.parametrize(
    "failure",
    [
        PersistenceWriteError("cannot write persistence file"),
        OSError("read-only file system"),
        ValueError("collection, record_id and record are required"),
    ],
    ids=["persistence-write-error", "os-error", "value-error"],
)
def test_a_failed_store_write_rolls_back_only_its_own_record(tmp_path, monkeypatch, failure):
    """Memory must not keep an application the durable store refused -- and must keep
    every other application, which a rollback by name or a clear() would drop."""
    first = _register(actions=("query",), departments=(DEPARTMENT_A,), description="first")
    rows_before = _registry_rows()
    raw_before = _store_file(tmp_path).read_text(encoding="utf-8")

    def _explode(self, *args, **kwargs):
        raise failure

    monkeypatch.setattr(JsonPersistenceAdapter, "upsert", _explode)

    with pytest.raises(ProductionReadOnlyProtection):
        _register(actions=("dashboard",), departments=(DEPARTMENT_B,), description="second")

    rows = _registry_rows()
    assert list(rows) == list(rows_before), (rows, rows_before)
    assert _grant(rows[first["app_id"]]) == _grant(rows_before[first["app_id"]]), rows
    assert _store_file(tmp_path).read_text(encoding="utf-8") == raw_before, "a failed write still touched disk"
