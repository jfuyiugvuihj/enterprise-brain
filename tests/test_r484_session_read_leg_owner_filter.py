"""R484 · 会话读腿的「谁在拦人」必须钉在 JSON 台账上，不是 `sessions.user_id`（判据①②③④）。

病灶（今天现读，三处锚点由 `scripts/r484_session_read_leg_ledger.py` 现扫现证，行号会漂所以
本件只认函数名与谓词）：

* `app/api/v1/chat.py::_list_sessions` 发的是
  `SELECT s.*, (...) as msg_count FROM sessions s ORDER BY s.updated_at DESC`——
  **外层一个字的 owner/部门谓词都没有**，库里整表进 Python。
* 同一个文件的 `GET /sessions` 在 **Python 侧**逐条过
  `session_registry.is_owned_by(session.get("id", ""), principal)`。
* `app/storage/sessions.py` 自述 `Transitional owner registry` /
  `JSON-backed owner mapping until the canonical Session table is migrated`，
  判定式 `record.owner_id == str(principal.user_id)`。

⇒ 本件钉住的那句话：**拦人的是 JSON 台账；库里那枚 `sessions.user_id` 列在读腿上一根手指都
没碰过**（`test_the_read_leg_has_no_owner_predicate_in_sql` 把这格从注释升级成能跑的牙）。
不许含糊成「有 owner 过滤所以安全」。

判据 → 用例

① 三形逐格四列                  `test_admin_shape_four_columns` / `test_evalbot_shape_four_columns`
                                + `test_no_department_shape_four_columns`
                                （第三形的「只准核对 filters.py」那半在
                                `test_the_department_ruler_never_touches_the_session_leg`）
② 28 行孤儿的归属结论            `test_orphan_rows_are_invisible_to_every_principal_on_the_roster`
③ 逐枚相等不许退化成看总数      `test_the_member_compare_is_what_bites_not_the_total`
                                + `test_counter_evidence_a_totals_only_ruler_lets_the_swap_pass`
④ 判红要带名字                  `test_every_red_names_shape_predicate_and_row_ids`
                                + `test_counter_evidence_a_red_without_a_name_is_not_allowed`

同一把尺：三形的算法不在本件里重写一份，直接 import 取证件那枚纯函数
`scripts/r484_session_read_leg_ledger.py::ledger_view`，所以「纸上判据」与「真库读数」不会分叉。

全程离线：`tests/conftest.py` 已把 `DATABASE_URL` 钉在保留端口 `127.0.0.1:1`，真库一根手指都不碰；
用户表是进程内假表（只换 `auth.get_user` 这一枚现成读点），台账是 `tmp_path` 下**真**
`SessionRegistry`。一发模型都不打、一个端口都不开、一行生产库都不写。
"""

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from app.common import auth
from app.common.auth import create_token

LEDGER = importlib.import_module("scripts.r484_session_read_leg_ledger")

#: 三形的名字。前两形是库里今天真实存在的两枚 admin；第三形是 `departments=None` 那档的成员。
ADMIN = "admin"
EVALBOT = "evalbot"
#: 有部门的 staff：用来证「部门维在会话读腿上零介入」——它看不见任何会话不是因为部门，
#: 是因为台账里没有绑在它名下的行。
STAFF_DEPT = "r484-staff-finance"
#: 无部门的 staff：文档腿该被 `app/rag/filters.py` 硬拒（`authorization_unavailable`），
#: 会话腿照旧 200。这一对不对称就是判据①第三形要核对的东西。
STAFF_NODEPT = "r484-staff-nodept"
#: 孤儿：库里挂着它的 user_id，但 `users` 表里已经没有这个人。
GHOST = "r8-probe-a"

UNRESTRICTED_ROLES = frozenset({"admin"})

# ============================================================================
# harness: 真路由 + 真台账 + 假用户表 + 假库行。四形各占一格，成员逐枚可点名。
# ============================================================================

#: 每档的成员。写死成元组，判据③要「摘掉成员比较就必读红」靠的就是这几枚名字。
ADMIN_ROWS = ("r484-sess-admin-1", "r484-sess-admin-2")
EVALBOT_ROWS = ("r484-sess-eval-1", "r484-sess-eval-2", "r484-sess-eval-3")
ORPHAN_ROWS = ("r484-sess-orphan-1", "r484-sess-orphan-2", "r484-sess-orphan-3")
#: 台账里有绑定、库里已经没有这一行——今天真库那 7 枚幽灵条目的形状。
LEDGER_ONLY_ROWS = ("r484-ghost-binding",)


def _user_row(username, role="staff", department=None):
    """production 形状：`app/common/auth.py::get_user` 只 SELECT username, role, department。

    🔴 一枚多余的键都不许有，尤其不许有 `id`。这格是本件最脆的一处依据：
    `Principal.from_user` 走的是 `user.get("id") or user.get("username")`，
    今天台账 owner_id 与 `sessions.user_id` 同为「用户名 namespace」**完全是因为**那枚 SELECT
    没带 `id`。谁补上 `id`，`str(principal.user_id)` 当场翻成 bigint 字符串，台账零命中，
    `GET /sessions` 对所有人静默回空列表（不报错、不 403）。
    `test_the_owner_namespace_is_the_username_and_it_is_load_bearing` 钉的就是这一格。
    """
    return {"username": username, "role": role, "department": department}


USERS = (
    _user_row(ADMIN, "admin"),
    _user_row(EVALBOT, "admin"),
    _user_row(STAFF_DEPT, "staff", "财务部"),
    _user_row(STAFF_NODEPT, "staff"),
)


class _UserStore:
    """进程内假用户表：唯一的接管点是「认证查人」，其余全走真实路由与真实台账。"""

    def __init__(self, rows):
        self.rows = {row["username"]: dict(row) for row in rows}

    def get_user(self, username):
        row = self.rows.get(username)
        return dict(row) if row else None


def _db_rows(extra_owner=None):
    """库里 `sessions` 今天的形状：id 是 TEXT，user_id 也是 TEXT（存的是用户名）。"""
    rows = [{"id": sid, "title": sid, "user_id": ADMIN} for sid in ADMIN_ROWS]
    rows += [{"id": sid, "title": sid, "user_id": EVALBOT} for sid in EVALBOT_ROWS]
    rows += [{"id": sid, "title": sid, "user_id": GHOST} for sid in ORPHAN_ROWS]
    if extra_owner:
        rows.append({"id": "r485-misplaced", "title": "r485", "user_id": extra_owner})
    return rows


def _kernel_rows(rows):
    """把库行换成内核认的键名（内核吃 `session_id`，路由吃 `id`）。"""
    return [{"session_id": row["id"], "user_id": row["user_id"]} for row in rows]


@pytest.fixture()
def registry(tmp_path):
    """真 `SessionRegistry`（`app/storage/sessions.py`），只落在 tmp_path，不碰仓里那份台账。"""
    from app.agents.contracts import Principal
    from app.storage.sessions import SessionRegistry

    store = SessionRegistry(tmp_path / "r484-sessions.json")
    owner_of = {}
    for sid in ADMIN_ROWS:
        owner_of[sid] = ADMIN
    for sid in EVALBOT_ROWS:
        owner_of[sid] = EVALBOT
    for sid in ORPHAN_ROWS:
        owner_of[sid] = GHOST
    for sid in LEDGER_ONLY_ROWS:
        owner_of[sid] = ADMIN
    for sid, name in owner_of.items():
        store.bind(sid, Principal.from_user(_user_row(name, "admin")))
    return store


@pytest.fixture()
def ledger_records(registry):
    """台账条目：直读 registry 自己写下的那份 JSON，所以测试与真库读的是同一种字节。"""
    payload = json.loads(registry.metadata_path.read_text(encoding="utf-8"))
    return payload["sessions"]


@pytest.fixture()
def store():
    return _UserStore(USERS)


@pytest.fixture()
def client(store, monkeypatch, registry):
    """真路由：只换「查人」与「库里整表捞」两枚缝，`is_owned_by` 那枚闸门一个字不动。"""
    import app.api.v1.chat as chat

    monkeypatch.setattr(auth, "get_user", store.get_user)
    monkeypatch.setattr(chat, "session_registry", registry)
    return chat


def _exit_ids(username, db_rows, monkeypatch, registry=None):
    """打真 `GET /sessions`，交回 (status_code, 出口成员 id 有序列表)。

    只有两枚缝被接管：「库里整表捞」换成给定库行，「台账」可换成给定的那份。闸门
    `is_owned_by` 与路由本身一个字都不动，所以这里读到的成员集就是产品今天会给的东西。
    """
    import app.api.v1.chat as chat
    from app.main import app

    if registry is not None:
        monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_list_sessions", lambda: [dict(row) for row in db_rows])
    with TestClient(app) as session_client:
        session_client.headers.update({"Authorization": "Bearer " + create_token(username)})
        response = session_client.get("/api/v1/sessions")
    payload = response.json() if response.status_code == 200 else {}
    return response.status_code, [row.get("id", "") for row in payload.get("sessions", [])]


def _view(db_rows, ledger_records, shapes=(ADMIN, EVALBOT)):
    """把同一把尺（取证件的纯函数内核）落到这枚假世界上。"""
    return LEDGER.ledger_view(_kernel_rows(db_rows), ledger_records,
                              [dict(row) for row in USERS], shapes, UNRESTRICTED_ROLES)


def _bound_registry(tmp_path, bindings):
    """按 {session_id: owner_name} 现造一份真台账。"""
    from app.agents.contracts import Principal
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "r484-adhoc.json")
    for session_id, owner in bindings.items():
        registry.bind(session_id, Principal.from_user(_user_row(owner, "admin")))
    return registry

# ============================================================================
# 判据① 三形逐格四列：库里行数 / 台账在册 / 实际可见 / 差在哪几枚（成员，不是数）
# ============================================================================

def test_the_ledger_not_the_column_is_what_gates_the_exit(client, monkeypatch, tmp_path):
    """把「库里说这人所有」与「台账说那人所有」掰开：出口跟着**台账**走。

    这一枚就是「拦人的是 JSON 台账，`sessions.user_id` 一根手指都没碰过」的正证。
    """
    split = "r484-column-says-admin"
    registry = _bound_registry(tmp_path, {split: EVALBOT})
    rows = [{"id": split, "title": split, "user_id": ADMIN}]

    assert ADMIN in [row["user_id"] for row in rows], "前提：库里这行写的是 admin"
    status, seen = _exit_ids(ADMIN, rows, monkeypatch, registry)
    assert status == 200 and seen == [], (
        "档=%s 谓词=is_owned_by(台账 owner_id) | 库里 user_id=%s 的 1 枚=%s 竟从出口出去了"
        % (ADMIN, ADMIN, [row["id"] for row in rows])
    )
    status, seen = _exit_ids(EVALBOT, rows, monkeypatch, registry)
    assert status == 200 and seen == [split], (
        "档=%s 谓词=is_owned_by(台账 owner_id) | 台账绑在该档的 1 枚=%s 没进出口"
        % (EVALBOT, [split])
    )


def test_admin_shape_four_columns(client, monkeypatch, ledger_records):
    """admin 形：库里 2 / 台账 3 / 可见 2 / 差在 1 枚台账独有绑定。"""
    rows = _db_rows()
    view = _view(rows, ledger_records)
    shape = view["shapes"][ADMIN]
    assert shape["db_rows"] == len(ADMIN_ROWS), "库里该档行数漂了"
    assert shape["ledger_rows"] == len(ADMIN_ROWS) + len(LEDGER_ONLY_ROWS), (
        "台账在册数应含 %d 枚库里已无此行的绑定，今天=%d"
        % (len(LEDGER_ONLY_ROWS), shape["ledger_rows"])
    )
    assert shape["visible"] == len(ADMIN_ROWS)
    assert shape["visible_ids"] == sorted(ADMIN_ROWS)
    assert shape["ledger_not_in_db"] == sorted(LEDGER_ONLY_ROWS), (
        "差在哪几枚没点到名：台账独有 %s" % shape["ledger_not_in_db"]
    )
    assert shape["db_not_in_ledger"] == []
    status, seen = _exit_ids(ADMIN, rows, monkeypatch)
    assert status == 200 and sorted(seen) == shape["visible_ids"], (
        "档=%s 谓词=出口遍历库行再交台账 | 真出口 %d 枚 != 内核算出的该见 %d 枚"
        % (ADMIN, len(seen), len(shape["visible_ids"]))
    )


def test_evalbot_shape_four_columns(client, monkeypatch, ledger_records):
    """evalbot 形：库里 3 / 台账 3 / 可见 3 / 四格无差（症状里那 656 的干净一侧）。"""
    rows = _db_rows()
    shape = _view(rows, ledger_records)["shapes"][EVALBOT]
    assert (shape["db_rows"], shape["ledger_rows"], shape["visible"]) == (3, 3, 3)
    assert shape["visible_ids"] == sorted(EVALBOT_ROWS)
    assert shape["db_not_in_ledger"] == [] and shape["ledger_not_in_db"] == []
    status, seen = _exit_ids(EVALBOT, rows, monkeypatch)
    assert status == 200 and sorted(seen) == sorted(EVALBOT_ROWS)


def test_no_department_shape_four_columns(client, monkeypatch, ledger_records):
    """无部门档（`departments=None` 那档不受限）：上界是成员可见并集，**不是整表**。

    尺只核对不重写：`app/rag/filters.py` 给谁 `departments=None` 由 `app/common/policy.py`
    的 `_ADMINISTRATOR_ROLES` 决定，本件从这里取成员，不去 filters.py 加第二把尺。
    """
    rows = _db_rows()
    view = _view(rows, ledger_records)
    assert view["nodept_member"] == sorted([ADMIN, EVALBOT]), (
        "无部门档成员漂了：应取 role 命中 _ADMINISTRATOR_ROLES 的在册账号，今天=%s"
        % view["nodept_member"]
    )
    assert view["nodept_union_visible"] == len(ADMIN_ROWS) + len(EVALBOT_ROWS)
    assert view["nodept_union_ids"] == sorted(ADMIN_ROWS + EVALBOT_ROWS)
    # 🔴 这一格是判据①第三形的要害：不受限那档如果在会话读腿上被读成「整表」，
    # 出口就会是 len(rows)=8；今天它只能到 5，差的那 3 枚全是孤儿行。
    assert view["nodept_union_visible"] < view["db_total"], (
        "档=无部门档 谓词=departments=None 不受限 | 该档并集已膨胀到整表 %d 枚，"
        "会话读腿把文档腿那把尺当成 owner 尺用了" % view["db_total"]
    )
    assert view["nodept_ceiling_if_filters_applied"] == view["db_total"]
    assert view["orphan_rows"] == view["db_total"] - view["nodept_union_visible"]
    for name in (ADMIN, EVALBOT):
        status, seen = _exit_ids(name, rows, monkeypatch)
        assert status == 200 and len(seen) == view["shapes"][name]["visible"]

def test_the_read_leg_has_no_owner_predicate_in_sql():
    """静态形状牙：`_list_sessions` 的外层查询里不许出现 owner/部门谓词，且全仓没人读该列。

    摘掉这枚牙就等于允许「把过滤下推到 SQL」这件事悄悄发生而账面不动——那一改同时会让
    本单其余几枚钉失去意义，所以它必须先在**这里**红一次。
    """
    anchors = LEDGER.check_list_sessions_sql()
    assert anchors["owner_predicate_hits"] == [], (
        "谓词=SELECT ... FROM sessions 之后 | 外层出现 %s | 原文: %s"
        % (anchors["owner_predicate_hits"], anchors["outer_tail"])
    )
    assert anchors["selects_whole_table"] is True, (
        "锚点形状变了：外层不再是从 sessions 整表捞，读数件要重画。原文: %s" % anchors["sql"]
    )
    readers = LEDGER.check_read_leg_uses_no_user_id_column()
    assert readers["count"] == 0, (
        "谓词=sessions.user_id 在读腿上的读者 | 今天有 %d 处在读它：%s"
        % (readers["count"], readers["readers"])
    )


def test_ledger_only_bindings_never_inflate_the_exit(client, monkeypatch, ledger_records):
    """台账独有的绑定不许变成分母：出口遍历的是**库行**（真库那 7 枚幽灵条目这一形）。"""
    rows = _db_rows()
    assert len(rows) < len(ledger_records), "前提：台账条目数必须大于库行数"
    status, seen = _exit_ids(ADMIN, rows, monkeypatch)
    assert status == 200
    assert sorted(seen) == sorted(ADMIN_ROWS), (
        "档=%s 谓词=出口只遍历库行 | 库里无此行的 %d 枚绑定漏进了出口：%s"
        % (ADMIN, len(LEDGER_ONLY_ROWS), sorted(set(seen) - set(ADMIN_ROWS)))
    )
    view = _view(rows, ledger_records)
    assert view["shapes"][ADMIN]["ledger_not_in_db"] == sorted(LEDGER_ONLY_ROWS)
    assert view["ledger_minus_db"] == sorted(LEDGER_ONLY_ROWS)


def test_orphan_rows_are_invisible_to_every_principal_on_the_roster(
    client, monkeypatch, ledger_records
):
    """判据②：28 行孤儿的归属结论——已消失用户的行，任何在册 principal 都不该看见，今天也看不见。

    依据是现读代码，不是推测：
    * `app/main.py` 的中间件先 `get_user(sub)`，查不到就 401 并落匿名探测账，
      所以连「同名的人」都成不了 principal（本件用 `_UserStore` 复现同一枚读点）；
    * `app/storage/sessions.py::is_owned_by` 只认 `record.owner_id == str(principal.user_id)`，
      **不认角色**，所以 admin 在这条口子上不豁免（`app/api/v1/chat.py` 的
      `_authorize_session_request` 文档字符串明写这件事）。
    """
    rows = _db_rows()
    view = _view(rows, ledger_records)
    assert sorted(view["orphans"]) == [GHOST], (
        "孤儿档漂了：应只有已不在 users 表的那一枚名字，今天=%s" % sorted(view["orphans"])
    )
    info = view["orphans"][GHOST]
    assert info["db_rows"] == len(ORPHAN_ROWS) and info["session_ids"] == sorted(ORPHAN_ROWS)
    assert info["ledger_backed"] == sorted(ORPHAN_ROWS), (
        "这 %d 枚孤儿行的台账绑定没被点名：孤儿今天是被台账绑住才不出口，不是被 SQL 挡掉" % len(ORPHAN_ROWS)
    )
    assert info["seen_by_any_principal"] == [] and view["orphan_seen_by_any_principal"] == 0
    for name in (ADMIN, EVALBOT, STAFF_DEPT, STAFF_NODEPT):
        status, seen = _exit_ids(name, rows, monkeypatch)
        assert status == 200, "%s 这档在会话读腿上被拒成了 %d，归属结论要重画" % (name, status)
        leaked = sorted(set(seen) & set(ORPHAN_ROWS))
        assert leaked == [], (
            "档=%s 谓词=is_owned_by(台账) | 孤儿行漏进出口 %d 枚=%s"
            % (name, len(leaked), leaked)
        )
    # 归属结论的另一半：这个名字今天成不了 principal，所以「谁都不该看见」今天是被硬保证的。
    assert auth.get_user(GHOST) is None, "前提破了：孤儿名 %r 竟能在 users 表里查到" % GHOST


def test_orphan_rows_would_become_visible_if_the_name_were_reregistered(
    client, monkeypatch, ledger_records, store
):
    """判据②的后半（未真机验证的风险，纸上一形）：同名重注册即整体继承那 28 行。

    台账键是**用户名字符串**，`delete_user` 只删 `users` 行（不清会话、不清台账），
    `create_user` 又没有保留名名单——所以一旦有人重注册 `r8-probe-a`，
    `str(principal.user_id)` 当场等于台账里那 8 枚的 owner_id。这一枚钉不修任何东西，
    它把「今天安全」与「设计上安全」的差别留在册子上。
    """
    rows = _db_rows()
    before = _exit_ids(GHOST, rows, monkeypatch)[0]
    assert before == 401, "前提破了：孤儿名今天竟能成 principal，风险等级要重画"

    store.rows[GHOST] = _user_row(GHOST, "staff")  # 复现一次同名重注册，只动进程内假表
    status, seen = _exit_ids(GHOST, rows, monkeypatch)
    assert status == 200 and sorted(seen) == sorted(ORPHAN_ROWS), (
        "档=%s 谓词=is_owned_by(台账 owner_id == 用户名) | 同名重注册后继承 %d 枚孤儿行，"
        "实际读到 %d 枚=%s" % (GHOST, len(ORPHAN_ROWS), len(seen), sorted(seen))
    )


def test_the_owner_namespace_is_the_username_and_it_is_load_bearing(client, monkeypatch, tmp_path):
    """身份 namespace 牙：台账能命中**纯属偶然**——因为 `get_user()` 的 SELECT 里没有 `id`。

    谁给那枚 SELECT 补上 `id`，`Principal.from_user` 就取 `str(user["id"])`，
    与台账里的用户名 owner_id 永不相等 ⇒ `GET /sessions` 对所有人静默回空列表（不报错）。
    这一枚钉不许改宽：它同时是「不许顺手改成 join」那格的凭据。
    """
    session_id = "r484-namespace"
    registry = _bound_registry(tmp_path, {session_id: ADMIN})
    rows = [{"id": session_id, "title": session_id, "user_id": ADMIN}]

    from app.agents.contracts import Principal

    production_shape = _user_row(ADMIN, "admin")
    assert "id" not in production_shape
    assert Principal.from_user(production_shape).user_id == ADMIN, (
        "principal.user_id 已不再等于用户名，台账 owner_id 那格要重画"
    )
    status, seen = _exit_ids(ADMIN, rows, monkeypatch, registry)
    assert status == 200 and seen == [session_id], (
        "档=%s 谓词=is_owned_by 用用户名 namespace | 该见的 1 枚没进出口" % ADMIN
    )

    bigint_shape = dict(production_shape, id=1)  # 假设有人补上了 id
    flipped = Principal.from_user(bigint_shape)
    assert flipped.user_id == "1" and flipped.username == ADMIN
    assert registry.is_owned_by(session_id, flipped) is False, (
        "台账竟然认得 bigint 那套 namespace：本件记的「偶然承重」这格不成立了，结论要重写"
    )

def test_the_department_ruler_never_touches_the_session_leg(client, monkeypatch, ledger_records):
    """判据①第三形的「只准核对」那半：部门那把尺只在文档腿上，会话腿对它零感知。

    🔴 这里叫的是 `app/rag/filters.py` 的**判定本体** `_resolve_document_retrieval_scope`，
    不是对外那枚入口：入口在 raise 之前会 `_record_refusal` → `record_audit`，取证据此落账
    就不再是只读。判定本体与入口的判定一字不差（filters.py 自己写明「判定逻辑…一律不改」）。
    """
    from app.agents.contracts import Principal
    from app.rag.filters import RetrievalScopeError, _resolve_document_retrieval_scope

    admins = (_user_row(ADMIN, "admin"), _user_row(EVALBOT, "admin"))
    for row in admins:
        scope = _resolve_document_retrieval_scope(Principal.from_user(row))
        assert scope.departments is None, (
            "档=%s 谓词=departments=None 不受限 | 文档腿那把尺今天不再是这格，第三形要重画" % row["username"]
        )
    staff_scope = _resolve_document_retrieval_scope(
        Principal.from_user(_user_row(STAFF_DEPT, "staff", "财务部"))
    )
    assert staff_scope.departments == frozenset({"财务部"})
    with pytest.raises(RetrievalScopeError) as refused:
        _resolve_document_retrieval_scope(Principal.from_user(_user_row(STAFF_NODEPT, "staff")))
    assert refused.value.code == "authorization_unavailable"

    # 同一批主体换到会话腿上：部门有没有、不受限不受限，都不改一行的归属。
    rows = _db_rows()
    per_shape = _view(rows, ledger_records)["shapes"]
    for name, expected in ((ADMIN, ADMIN_ROWS), (EVALBOT, EVALBOT_ROWS),
                           (STAFF_DEPT, ()), (STAFF_NODEPT, ())):
        status, seen = _exit_ids(name, rows, monkeypatch)
        assert status == 200 and sorted(seen) == sorted(expected), (
            "档=%s 谓词=is_owned_by 唯一归属尺 | 会话读腿被部门维改动了：%s != %s"
            % (name, sorted(seen), sorted(expected))
        )
    assert set(per_shape[ADMIN]["visible_ids"]).isdisjoint(per_shape[EVALBOT]["visible_ids"]), (
        "两档可见成员竟然相交，读数表要重画"
    )


# ============================================================================
# 判据③ 逐枚相等：不许退化成「只看总数」
# ============================================================================

def _swap_admin_membership(tmp_path, bindings):
    """造一形「admin 仍然看见 2 枚，但那 2 枚换了人」的世界：总数不动，成员全换。"""
    registry = _bound_registry(tmp_path, bindings)
    rows = [{"id": sid, "title": sid, "user_id": ADMIN} for sid in sorted(bindings)]
    return registry, rows


def test_the_member_compare_is_what_bites_not_the_total(client, monkeypatch, tmp_path):
    """反证形状在册：总数对得上而成员换了，必须读红。

    两枚世界：`W1 = {keep-1, keep-2}`、`W2 = {swap-1, swap-2}`，admin 都恰好看见 2 枚。
    只看总数的尺量不出差别；逐枚相等量得出，而且要点名差在哪几枚。
    """
    w1, w2 = ("r484-keep-1", "r484-keep-2"), ("r484-swap-1", "r484-swap-2")
    reg1, rows1 = _swap_admin_membership(tmp_path, {sid: ADMIN for sid in w1})
    reg2, rows2 = _swap_admin_membership(tmp_path, {sid: ADMIN for sid in w2})

    _, seen1 = _exit_ids(ADMIN, rows1, monkeypatch, reg1)
    _, seen2 = _exit_ids(ADMIN, rows2, monkeypatch, reg2)
    assert len(seen1) == len(seen2) == 2, (
        "反证形状破了：两形必须总数相等（今天 %d vs %d），否则「成员」这一格没被考验到"
        % (len(seen1), len(seen2))
    )
    diff = LEDGER.member_diff(set(seen1), set(seen2))
    assert diff["count_a"] == diff["count_b"], "只看数的那半格没跑起来，说明用例造形不对"
    assert diff["members_equal"] is False, (
        "谓词=逐枚相等 | 成员已从 %s 换成 %s 却判成相等，这枚钉退化成数数了"
        % (sorted(seen1), sorted(seen2))
    )
    assert diff["only_in_a"] == sorted(w1) and diff["only_in_b"] == sorted(w2), (
        "判红没点名：only_in_a=%s only_in_b=%s" % (diff["only_in_a"], diff["only_in_b"])
    )


def test_a_same_total_different_member_world_is_named(client, monkeypatch, tmp_path):
    """判据③的见证形：admin 仍然看见 2 枚，但那 2 枚**不是库里那 2 枚**，必须读红并点名。

    这一形专门用来堵「把成员比较偷偷写成比总数」。库里 `user_id=admin` 的是 s1/s2，台账却把
    s1 与 s3 绑在 admin 名下（s3 那行的 `user_id` 写的是 evalbot）⇒ 该档可见数 2 == 库里数 2，
    比总数的尺量不出任何异常；逐枚相等则必须报出「少 s2 / 多 s3」。
    """
    rows = [
        {"id": "r484-s1", "title": "s1", "user_id": ADMIN},
        {"id": "r484-s2", "title": "s2", "user_id": ADMIN},
        {"id": "r484-s3", "title": "s3", "user_id": EVALBOT},
    ]
    registry = _bound_registry(tmp_path, {"r484-s1": ADMIN, "r484-s3": ADMIN})
    records = json.loads(registry.metadata_path.read_text(encoding="utf-8"))["sessions"]

    status, seen = _exit_ids(ADMIN, rows, monkeypatch, registry)
    assert status == 200 and sorted(seen) == ["r484-s1", "r484-s3"]
    view = _view(rows, records, shapes=(ADMIN,))
    shape = view["shapes"][ADMIN]
    assert (shape["db_rows"], shape["visible"]) == (2, 2), (
        "见证形要的就是总数相等，今天 %d vs %d —— 数都不等了，这枚钉就没在考验成员比较"
        % (shape["db_rows"], shape["visible"])
    )
    assert shape["members_equal_to_db_owned"] is False, (
        "谓词=逐枚相等 | 成员已从 %s 换成 %s 却判成相等"
        % (sorted(ADMIN_ROWS[:2]), sorted(seen))
    )
    assert shape["db_not_in_ledger"] == ["r484-s2"], "该档少了哪一枚没点名: %s" % shape["db_not_in_ledger"]
    assert shape["extra_visible_ids"] == ["r484-s3"], "该档多了哪一枚没点名: %s" % shape["extra_visible_ids"]
    # 这一形同时踩四条谓词，四条都必须响、都必须点名——少响一条就是那条尺在空转。
    reds = [_require_named_red(item) for item in LEDGER.reconcile(view)]
    assert len(reds) == 4, "该响 4 条谓词，实际 %d 条: %s" % (len(reds), reds)
    member_red = [item for item in reds if "可见成员" in item]
    assert len(member_red) == 1, "成员比较那一枚没单独响: %s" % reds
    assert "r484-s2" in member_red[0] and "r484-s3" in member_red[0], (
        "成员红没点到互换的两枚: " + member_red[0]
    )
    assert "少 1 枚" in member_red[0] and "多 1 枚" in member_red[0], ("成员红没报出少/多各几行: " + member_red[0])


def test_counter_evidence_a_totals_only_ruler_lets_the_swap_pass(client, monkeypatch, tmp_path):
    """反证刀（判据③）：把成员比较换成「比总数」，同一形当场读绿——所以成员比较是承重的。

    这枚用例不改产品码，它摘的是**尺子**：如果哪天有人把逐枚相等写成 `len(a) == len(b)`，
    上面那枚钉就会变绿，本枚钉负责把这件事写成一句可执行的证据。
    """
    w1, w2 = ("r484-keep-1", "r484-keep-2"), ("r484-swap-1", "r484-swap-2")
    reg1, rows1 = _swap_admin_membership(tmp_path, {sid: ADMIN for sid in w1})
    reg2, rows2 = _swap_admin_membership(tmp_path, {sid: ADMIN for sid in w2})
    _, seen1 = _exit_ids(ADMIN, rows1, monkeypatch, reg1)
    _, seen2 = _exit_ids(ADMIN, rows2, monkeypatch, reg2)

    totals_only = len(seen1) == len(seen2)          # ← 摘掉成员比较之后剩下的那半把尺
    members = set(seen1) == set(seen2)              # ← 在册的那把尺
    assert totals_only is True, "反证不成立：两形总数已经不等，判据③这一格白造了"
    assert members is False, (
        "反证不成立：成员比较竟然判它们相等 —— 逐枚相等那格是假的，判据③未达标"
    )


def test_kernel_and_endpoint_agree_member_by_member(client, monkeypatch, ledger_records):
    """纸上判据与真出口同一把尺：内核算出的成员集必须逐枚等于路由吐出的成员集。"""
    rows = _db_rows() + [{"id": "r484-unbound", "title": "r484", "user_id": ADMIN}]
    view = _view(rows, ledger_records)
    for name in (ADMIN, EVALBOT):
        status, seen = _exit_ids(name, rows, monkeypatch)
        expected = view["shapes"][name]["visible_ids"]
        assert status == 200
        assert sorted(seen) == expected, (
            "档=%s 谓词=台账 owner_id | 真出口 %d 枚 != 内核算出 %d 枚 | 差=%s"
            % (name, len(seen), len(expected), sorted(set(seen) ^ set(expected)))
        )
    # 库里冒出一行没绑台账的：内核算它「该档行数 +1 / 可见不变」，出口必须同样不吐它。
    assert view["shapes"][ADMIN]["db_not_in_ledger"] == ["r484-unbound"], (
        "档=%s 谓词=库行未进台账 | 该点名的一枚没点名：%s"
        % (ADMIN, view["shapes"][ADMIN]["db_not_in_ledger"])
    )

# ============================================================================
# 判据④ 判红要有名字
# ============================================================================

_RED_TOKENS = ("档=", "谓词=")


def _require_named_red(text):
    """一枚红必须自带 档名 / 谓词名 / 条数 / 至少一枚 id；缺一样就把它打回。"""
    for token in _RED_TOKENS:
        if token not in text:
            raise AssertionError("判红缺字 %r: %s" % (token, text))
    if not any(char.isdigit() for char in text):
        raise AssertionError("判红没带条数: " + text)
    if "[" not in text and "=" not in text.split("谓词=")[-1]:
        raise AssertionError("判红没点名到行: " + text)
    return text


def test_every_red_names_shape_predicate_and_row_ids(client, monkeypatch, ledger_records, tmp_path):
    """把两处都弄坏，逼出红：①库行没绑台账 ②无部门档并集膨胀到整表。红必须逐枚可点名。"""
    # 一枚「库里有行、台账没绑」的行，会被三条谓词各逮一次：owner 等式、成员相等、总账三格。
    # 三枚都必须点到同一枚 id——只响一条就说明另外两格的尺没在跑。
    rows = _db_rows() + [{"id": "r484-unbound-again", "title": "x", "user_id": ADMIN}]
    reds = [_require_named_red(item) for item in LEDGER.reconcile(_view(rows, ledger_records))]
    assert len(reds) == 3, "该逼出 3 枚红（owner 等式 / 成员相等 / 总账三格），实际 %d 枚：%s" % (len(reds), reds)
    assert all("r484-unbound-again" in item for item in reds), (
        "有红没点到那一枚的 id: %s" % [item for item in reds if "r484-unbound-again" not in item]
    )
    assert all("1 枚" in item for item in reds), "有红没带条数: %s" % reds
    assert any(item.startswith("档=admin") for item in reds), "没有一档被点名: %s" % reds
    assert sum(1 for item in reds if item.startswith("档=整表")) == 1, "整表那格没响: %s" % reds

    # 第二处：干净世界上只伪造一形「孤儿被某档读回了」——归属结论的红同样必须点名。
    forged = _view(_db_rows(), ledger_records)
    assert LEDGER.reconcile(forged) == [], "伪造之前该是绿的，红没被隔离出来"
    forged["orphan_seen_by_any_principal"] = 2
    forged["orphans"][GHOST]["seen_by_any_principal"] = list(ORPHAN_ROWS[:2])
    reds = [_require_named_red(item) for item in LEDGER.reconcile(forged)]
    orphan_red = [item for item in reds if "孤儿" in item]
    assert len(reds) == 1 and len(orphan_red) == 1, "只该逼出孤儿那一枚红，实际: %s" % reds
    assert ORPHAN_ROWS[0] in orphan_red[0] and "2 枚" in orphan_red[0], (
        "孤儿红没点名/没带条数: " + orphan_red[0]
    )


def test_counter_evidence_a_red_without_a_name_is_not_allowed():
    """反证刀（判据④）：把红退化成一句裸失败，本枚钉必须响。"""
    for lazy in ("assertion failed", "对账不闭合", "档= 谓词= 0 枚", "谓词=is_owned_by 0 枚 []"):
        with pytest.raises(AssertionError):
            _require_named_red(lazy)
    assert _require_named_red(
        "档=admin 谓词=is_owned_by: 台账 owner_id == str(principal.user_id)"
        " | 库行未进台账 1 枚=['r484-x'] (这些行对任何 principal 都不出口)"
    )


# ============================================================================
# 只读闸与总账算式
# ============================================================================

def test_the_readout_gate_refuses_every_write():
    """取证件的出口闸不许能被自己的常量绕过：三枚在册 SQL 必须过闸，写语句必须被拒。"""
    for sql in (LEDGER.SESSIONS_SQL, LEDGER.USERS_SQL, LEDGER.AUDIT_COUNT_SQL):
        assert LEDGER.assert_select_only(sql) == sql.strip().rstrip(";").strip()
    for write in (
        "INSERT INTO sessions (id, user_id) VALUES ('x', 'y')",
        "UPDATE sessions SET user_id = 'admin'",
        "DELETE FROM sessions WHERE id = 'x'",
        "DROP TABLE sessions",
        "TRUNCATE sessions",
        "CREATE TABLE r484 (id text)",
    ):
        with pytest.raises(ValueError):
            LEDGER.assert_select_only(write)
    with pytest.raises(ValueError):
        LEDGER.assert_select_only("SELECT 1; DELETE FROM sessions")


def test_the_reconciliation_identity_closes(client, ledger_records):
    """总账算式：库里每行必须恰好落进「在册可见 / 孤儿 / 未落账」三格之一。"""
    rows = _db_rows()
    view = _view(rows, ledger_records)
    assert view["nodept_union_visible"] + view["orphan_rows"] + len(view["unaccounted_rows"]) \
        == view["db_total"], (
        "档=整表 谓词=在册可见+孤儿+未落账==库行数 | %d+%d+%d != %d"
        % (view["nodept_union_visible"], view["orphan_rows"],
           len(view["unaccounted_rows"]), view["db_total"])
    )
    assert LEDGER.reconcile(view) == [], (
        "干净世界上不该有红，有就说明尺子偏了: %s" % LEDGER.reconcile(view)
    )


def test_today_reported_shape_replays_member_by_member(client, tmp_path, monkeypatch):
    """把 09-29 那格形状按**合成副本**重放一遍，逼尺子在 1020 枚的量上仍逐枚相等。

    🔴 这是形状副本，不是生产读数：成员全是 `r484-snap-*` 合成 id。生产数以
    `python scripts/r484_session_read_leg_ledger.py --live` 现读为准；这里证的只有一件事——
    「336 / 656 / 28」这一格在真闸门 `is_owned_by` 上重放时，成员一枚不差、孤儿一枚不漏、
    台账那 7 枚超集绑定一枚都不进出口。
    """
    from app.storage.sessions import SessionRegistry

    counts = {ADMIN: 336, EVALBOT: 656}
    orphan_counts = {"browser-e2e-mgr": 9, "r8-probe-a": 8, "browser-e2e-rv": 6,
                     "r8-probe-b": 3, "browser-e2e-tester": 2}
    members = {}
    rows = []
    for name, size in counts.items():
        ids = ["r484-snap-%s-%04d" % (name, index) for index in range(size)]
        members[name] = ids
        rows += [{"id": sid, "title": sid, "user_id": name} for sid in ids]
    orphan_members = {}
    for name, size in orphan_counts.items():
        ids = ["r484-snap-orphan-%s-%02d" % (name, index) for index in range(size)]
        orphan_members[name] = ids
        rows += [{"id": sid, "title": sid, "user_id": name} for sid in ids]
    ghost_bindings = ["r484-snap-ghost-%02d" % index for index in range(7)]

    records = [{"session_id": sid, "owner_id": name, "status": "active", "created_at": "t"}
               for name, ids in list(members.items()) + list(orphan_members.items())
               for sid in ids]
    records += [{"session_id": sid, "owner_id": ADMIN, "status": "active", "created_at": "t"}
                for sid in ghost_bindings]
    assert len(rows) == 1020 and len(records) == 1027, "副本形状漂了，本件不再对应 09-29 那格"
    path = tmp_path / "r484-snapshot.json"
    path.write_text(json.dumps({"sessions": records}), encoding="utf-8")
    registry = SessionRegistry(path)

    view = _view(rows, records)
    for name in (ADMIN, EVALBOT):
        status, seen = _exit_ids(name, rows, monkeypatch, registry)
        assert status == 200
        assert sorted(seen) == sorted(members[name]), (
            "档=%s 谓词=is_owned_by(台账) | 重放成员不等: 出口 %d 枚 / 应为 %d 枚, 差=%s"
            % (name, len(seen), len(members[name]), sorted(set(seen) ^ set(members[name]))[:5])
        )
    assert view["nodept_union_visible"] == 992 and view["orphan_rows"] == 28
    assert view["orphan_seen_by_any_principal"] == 0
    assert sorted(view["ledger_minus_db"]) == sorted(ghost_bindings), (
        "台账超集那 7 枚没被点名，判据①第四格不算交回: %s" % view["ledger_minus_db"][:8]
    )
    assert LEDGER.reconcile(view) == []