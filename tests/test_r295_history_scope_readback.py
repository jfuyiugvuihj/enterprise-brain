"""R295 · 会话历史回读必须重过一遍作用域闸门（判据①②③⑤）。

病灶（docs/api/contract-v1.md「Registered, not fixed」第 2 条登记的读路）：
app/api/v1/chat.py 的 GET /sessions/{session_id} 只过 app/storage/sessions.py 的
is_owned_by 一枚归属谓词，于是员工在旧部门期间那一轮的答案正文——里面就写着旧部门
文档的引用——在被挪走部门、或者那份文档改完归属之后，仍然能整段读回来。

方向是总控裁的那一条：回读时重过 app/rag/filters.py 的 scope.allows，**不给
SessionRecord 加部门维，不写新 migration**——作用域不在会话上，在文档上，读数取
目录里当前那一行，所以挪部门与改版重标都当场生效。判据①要的两件事同时成立：旧作用域
那一轮的正文与引用读不回来；屏上给的是「这一轮不在你当前可见范围」这一张脸，而不是
把整条会话变成空列表冒充「没有历史」。

判据 → 用例

① 挪完部门再读同一条会话        test_the_move_takes_the_old_department_turn_off_the_screen 等三枚
② 判定只许用仓里那枚闸门        test_the_readback_partition_is_the_same_scope_allows（矩阵逐行对拍）
                                + test_the_face_carries_no_department_or_classification_value
③ owner 对自己文件照旧读写      test_the_owner_still_reads_their_own_file_after_the_move
                                + test_counter_evidence_tightening_owner_match_...（反证④）
⑤ 反证常驻                      test_counter_evidence_... 三枚（摘闸门 / 换恒真 / 收紧 owner_match）

全程离线：进程内 TestClient + 假用户表（只换 auth.get_user 这一枚现成读点）+ 假目录行，
一发模型都不打、一个端口都不开、一行生产库都不写、被跟踪文件零字节落盘。
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.common import auth
from app.common.auth import create_token

SESSION = "r295-session-history"
OUTSIDE_SESSION = "r295-session-outsider"

DEPT_FIN = "r295-finance"
DEPT_RES = "r295-research"

KEEPER = "r295-keeper"
KEEPER_ID = "u-r295-keeper"
OUTSIDER = "r295-outsider"
OUTSIDER_ID = "u-r295-outsider"

#: 三份文件名就是三份哨兵：回读把那一轮换脸之后，它们一个都不许再出现在屏上。
FIN_DOC = "R295-FIN-薪酬明细表.txt"
RES_DOC = "R295-RES-研发方案书.txt"
OWN_DOC = "R295-OWN-我自己的报销单.txt"

OLD_TURN_BODY = "R295-TURN-OLD 这一段是旧部门期间那一轮的答案正文"
OWN_TURN_BODY = "R295-TURN-OWN 这一段引用的是一份自己上传的文档"
NEW_TURN_BODY = "R295-TURN-NEW 这一段是挪过来之后那一轮的答案正文"
PLAIN_TURN_BODY = "R295-TURN-PLAIN 这一轮没有点名任何文档"
FOREIGN_BODY = "R295-FOREIGN-BODY 这一段正文只属于别人的会话"

#: 屏幕换脸之后仍不许动的东西：本轮仍在，问句仍在，列表不缩短。
TURN_COUNT = 4

#: 拒绝码只许取自闸门自己那一份词表（与 R179 / R194 同口径，本单一枚都不新造）。
STABLE_CODES = frozenset(
    {
        "department_scope_denied",
        "clearance_insufficient",
        "resource_scope_missing",
        "permission_denied",
        "authorization_unavailable",
    }
)

_ROWS = [
    {"role": "user", "content": "r295q1 报销上限按职级是怎么定的", "steps": []},
    {"role": "assistant", "content": OLD_TURN_BODY + "。来源：" + FIN_DOC + " chunk=0",
     "steps": [{"tool": "doc", "label": "📄 搜索知识库", "status": "done", "elapsed": 2.4}]},
    {"role": "user", "content": "r295q2 我的报销单提交到哪一步了", "steps": []},
    {"role": "assistant", "content": OWN_TURN_BODY + "。来源：" + OWN_DOC + " chunk=1", "steps": []},
    {"role": "user", "content": "r295q3 研发方案归档了吗", "steps": []},
    {"role": "assistant", "content": NEW_TURN_BODY + "。来源：" + RES_DOC + " chunk=0", "steps": []},
    {"role": "user", "content": "r295q4 今天有什么安排", "steps": []},
    {"role": "assistant", "content": PLAIN_TURN_BODY, "steps": []},
]


# ==================== 夹具与驱动器 ====================


class _UserStore:
    """进程内假用户表：唯一的手是「挪部门」，改的就是 Principal 读到的那一行。"""

    def __init__(self, rows):
        self.rows = {row["username"]: dict(row) for row in rows}

    def get_user(self, username):
        row = self.rows.get(username)
        return dict(row) if row else None

    def move(self, username, department):
        """R290 那枚端点在产品侧做的事，这里就是那一格。"""
        self.rows[username]["department"] = department


def _keeper_row(**overrides):
    row = {
        "id": KEEPER_ID,
        "username": KEEPER,
        "role": "manager",
        "department": DEPT_FIN,
    }
    row.update(overrides)
    return row


def _outsider_row(**overrides):
    row = {
        "id": OUTSIDER_ID,
        "username": OUTSIDER,
        "role": "manager",
        "department": DEPT_RES,
    }
    row.update(overrides)
    return row


def _doc(filename, department, classification, owner_id):
    """一份「目录里当前那一行」：回读判的就是这三格今天的值。"""
    return {
        "filename": filename,
        "storage_path": filename,
        "department": department,
        "classification": classification,
        "owner_id": owner_id,
        "version": 1,
    }


def _catalog():
    return [
        _doc(FIN_DOC, DEPT_FIN, 1, "u-r295-someone-else"),
        _doc(RES_DOC, DEPT_RES, 1, "u-r295-someone-else"),
        _doc(OWN_DOC, DEPT_FIN, 1, KEEPER_ID),
    ]


@pytest.fixture()
def store():
    return _UserStore([_keeper_row(), _outsider_row()])


@pytest.fixture()
def client(store, monkeypatch):
    """只接管「认证查人」这一条缝，其余走真实路由（与 R179 / R194 同一姿势）。"""
    from app.main import app

    monkeypatch.setattr(auth, "get_user", store.get_user)
    return TestClient(app)


@pytest.fixture()
def audit_rows(monkeypatch):
    """包一层 chat 模块的 record_audit：原实现照调，只取位置参数（沿 R175/R179 的形状）。"""
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


@pytest.fixture()
def history(client, monkeypatch, tmp_path, store):
    """真会话归属 + 真回读闸门，只有「消息从哪读」与「目录长什么样」两枚被接管。"""
    import app.api.v1.chat as chat
    from app.agents.contracts import Principal
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "r295-sessions.json")
    registry.bind(SESSION, Principal.from_user(store.get_user(KEEPER)))
    registry.bind(OUTSIDE_SESSION, Principal.from_user(store.get_user(OUTSIDER)))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_get_session_messages", lambda *_a, **_k: [dict(m) for m in _ROWS])
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {SESSION: {"id": SESSION, "title": "r295q1"}})
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "current_documents", lambda *a, **k: _catalog())
    return chat


def _read(client, session_id=SESSION, as_user=KEEPER):
    client.headers.update({"Authorization": "Bearer " + create_token(as_user)})
    return client.get("/api/v1/sessions/" + session_id)


def _bodies(payload):
    return [row.get("content", "") for row in payload.get("messages", [])]


def _masked(payload):
    return [row for row in payload.get("messages", []) if row.get("answer_withheld")]


def _blob(value):
    return json.dumps(value, ensure_ascii=False, default=str)


# ==================== 判据①：回读那一格真的换了脸 ====================


def test_the_baseline_partition_before_the_move(history, client):
    """挪之前只裁旧部门之外那一轮：绿不是靠全裁刷出来的。"""
    payload = _read(client).json()
    assert payload["withheld_turns"] == 1, _blob(payload)
    assert len(payload["messages"]) == TURN_COUNT * 2
    blob = _blob(payload)
    assert OLD_TURN_BODY in blob, "反证：本部门那份文档引用的那一轮也被一起抹了"
    assert OWN_TURN_BODY in blob
    assert PLAIN_TURN_BODY in blob
    assert NEW_TURN_BODY not in blob


def test_the_move_takes_the_old_department_turn_off_the_screen(history, client, store):
    """判据①：挪完部门再读同一条会话，旧作用域那两轮的正文与文件名都不许再出现。"""
    store.move(KEEPER, DEPT_RES)
    response = _read(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    blob = _blob(payload)
    for token in (OLD_TURN_BODY, OWN_TURN_BODY, FIN_DOC, OWN_DOC):
        assert token not in blob, "反证：" + token + " 在挪完部门之后仍然读得回来"
    for token in (DEPT_FIN, DEPT_RES):
        assert token not in blob, "反证：返回值里漏出了部门实值 " + token
    assert NEW_TURN_BODY in blob, "反证：可见范围内的轮次也被一起抹了"
    assert PLAIN_TURN_BODY in blob
    assert payload["withheld_turns"] == 2


def test_the_face_says_authority_and_never_blames_execution(history, client, store):
    """判据①那半条「一张脸」：说的是可见范围，不是「没有数据」，也不是「代码没跑通」。"""
    store.move(KEEPER, DEPT_RES)
    masked = _masked(_read(client).json())
    assert masked
    for row in masked:
        text = row["content"]
        assert "可见范围" in text, "被裁那一轮必须说得出是因权限而不展示：" + text
        for blame in ("没有数据", "暂无", "代码", "执行未通过", "运行失败", "调用失败", "报错"):
            assert blame not in text, "反证：把权限拒绝甩锅成了「" + blame + "」"


def test_the_session_is_never_faked_as_having_no_history(history, client, store):
    """判据①后半条：换的是那一轮的脸，不是整条会话——列表不缩短、问句不缺、顺序不乱。"""
    store.move(KEEPER, DEPT_RES)
    payload = _read(client).json()
    messages = payload["messages"]
    assert len(messages) == TURN_COUNT * 2, "反证：把整条会话变成空列表冒充「没有历史」"
    assert [row["role"] for row in messages] == [row["role"] for row in _ROWS]
    asks = [row["content"] for row in messages if row["role"] == "user"]
    assert asks == [row["content"] for row in _ROWS if row["role"] == "user"]
    masked = _masked(payload)
    assert len(masked) == 2
    for row in masked:
        assert {"role", "created_at", "steps"} <= set(row), "被换脸那一轮仍要说得出它是哪一轮"
    assert masked[0]["steps"], "那一轮的工具轨迹不许跟着正文一起消失"


# ==================== 判据②：判定只许用仓里那枚闸门 ====================

#: 五档身份：两档部门、一档空部门、一档低密级、一档管理员，逐档与出口那枚对拍。
_MATRIX = [
    ("finance_manager", {"role": "manager", "department": DEPT_FIN}),
    ("research_manager", {"role": "manager", "department": DEPT_RES}),
    ("no_department", {"role": "manager", "department": ""}),
    ("staff_clearance", {"role": "staff", "department": DEPT_FIN}),
    ("administrator", {"role": "admin", "department": ""}),
]


@pytest.mark.parametrize("case, overrides", _MATRIX)
def test_the_readback_partition_is_the_same_scope_allows(history, case, overrides):
    """判据②：回读的可见集与出口那枚 _authorized_source_rows 的可见集逐档相等。

    两集合只要有一天长出不一样，就说明回读这一侧另起了第二套口径，本枚当场红。
    """
    import app.api.v1.chat as chat
    from app.agents.contracts import Principal

    catalog = _catalog()
    rows_dict = {row["filename"]: row for row in catalog}
    principal = Principal.from_user(_keeper_row(**overrides))
    visible_through_exit = {
        row["filename"] for row in chat._authorized_source_rows(rows_dict, principal)[0]
    }
    probe = [
        {
            "role": "assistant",
            "content": "r295 对拍正文。来源：" + name + " chunk=0",
            "steps": [],
        }
        for name in rows_dict
    ]
    readout, withheld = chat._history_scope_face(probe, principal, "r295-matrix")
    visible_through_readback = {
        row["content"].split("来源：")[1].split(" ")[0]
        for row in readout
        if not row.get("answer_withheld")
    }
    assert visible_through_readback == visible_through_exit, (
        "档位 " + case + "：回读与出口判出了两套口径"
    )
    assert withheld == len(catalog) - len(visible_through_exit)


def test_the_readback_never_derives_a_scope_rule_of_its_own(history):
    """判据②反面钉：回读这一段只许问闸门，不许自己认部门、密级与档位。"""
    import inspect

    source = inspect.getsource(history._history_scope_face)
    for token in ("department", "classification", "clearance"):
        assert token not in source, "反证：回读里出现了自算的 " + token + " 判定，闸门被绕过了"
    assert "scope.allows" in source, "判定必须出自闸门那一枚 allows"


def test_the_face_carries_no_department_or_classification_value(
    history, client, store, audit_rows, caplog
):
    """判据②：部门实值、密级实值、被裁掉的文件名，一律不进返回值、台账与日志。"""
    import logging

    caplog.set_level(logging.WARNING)
    store.move(KEEPER, DEPT_RES)
    payload = _read(client).json()
    masked = _masked(payload)
    assert len(masked) == 2
    for row in masked:
        assert set(row) <= {
            "role", "created_at", "steps", "content",
            "answer_withheld", "withheld_reason",
        }, "换脸那一行多带了键：" + _blob(sorted(set(row)))
        assert row["withheld_reason"] in STABLE_CODES, row["withheld_reason"]
    blob = _blob(masked)
    for value in (DEPT_FIN, DEPT_RES, FIN_DOC, OWN_DOC, '"classification"', '"department"'):
        assert value not in blob, "反证：返回值里漏出了 " + value
    whole = _blob(payload)
    for value in (DEPT_FIN, DEPT_RES):
        assert value not in whole, "反证：整条回读响应里漏出了部门实值 " + value
    denials = [
        row for row in audit_rows
        if row["outcome"] == "denied" and row["resource"] == SESSION
    ]
    assert len(denials) == 2, "被裁的两轮各留一笔，一枚都不许漏"
    for row in denials:
        assert row["reason"] in STABLE_CODES
        assert row["username"] == KEEPER
        assert row["action"] == "resource:view"
    audit_blob = _blob(denials)
    for value in (DEPT_FIN, DEPT_RES, FIN_DOC, OWN_DOC, OLD_TURN_BODY):
        assert value not in audit_blob, "反证：台账里漏出了 " + value
    for record in caplog.records:
        text = record.getMessage()
        for value in (DEPT_FIN, DEPT_RES, FIN_DOC, OWN_DOC):
            assert value not in text, "反证：日志里漏出了 " + value


def test_an_account_without_a_department_gets_a_face_not_a_crash(history, client, store):
    """闸门自己都给不出作用域那一支：fail-closed 换脸，而不是 500，也不是放行。"""
    store.move(KEEPER, "")
    response = _read(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["withheld_turns"] == 3
    assert len(payload["messages"]) == TURN_COUNT * 2
    for row in _masked(payload):
        assert row["withheld_reason"] == "authorization_unavailable"
    assert PLAIN_TURN_BODY in _blob(payload), "没引用任何文档的那一轮无从裁，不许顺手一起抹掉"


def test_a_document_moved_or_reclassified_is_judged_from_the_current_row(
    history, client, store, monkeypatch
):
    """改完归属那一支：调用方一字不动，只改目录里当前那一行，回读当场跟着变。"""
    assert _read(client).json()["withheld_turns"] == 1

    moved = [dict(row) for row in _catalog()]
    for row in moved:
        if row["filename"] == FIN_DOC:
            row["department"] = DEPT_RES
    monkeypatch.setattr(history, "current_documents", lambda *a, **k: moved)
    payload = _read(client).json()
    assert OLD_TURN_BODY not in _blob(payload)
    assert _masked(payload)[0]["withheld_reason"] == "department_scope_denied"

    raised = [dict(row) for row in _catalog()]
    for row in raised:
        if row["filename"] == FIN_DOC:
            row["classification"] = 4
    monkeypatch.setattr(history, "current_documents", lambda *a, **k: raised)
    payload = _read(client).json()
    assert OLD_TURN_BODY not in _blob(payload)
    assert _masked(payload)[0]["withheld_reason"] == "clearance_insufficient"


def test_a_non_owner_still_gets_404_and_the_face_never_runs(history, client, store, audit_rows):
    """归属那道门一寸没动：别人的会话仍然像不存在，作用域闸门也不替它说话。"""
    response = _read(client, SESSION, OUTSIDER)
    assert response.status_code == 404
    assert response.json()["detail"] == "resource_not_found"
    assert OLD_TURN_BODY not in response.text
    denied = [row["reason"] for row in audit_rows if row["outcome"] == "denied"]
    assert denied == ["permission_denied"], (
        "别人的会话只记归属那一枚码，不许长出作用域码：" + _blob(denied)
    )


# ==================== 判据③：owner 对自己文件的读写是另一件事 ====================

#: 这枚钉钉的是既有设计（app/common/policy.py:150-155 的 owner_match），本单一格都不许顺手改。
OWN_FILE_BYTES = b"R295-OWN-BYTES the bytes of a file KEEPER uploaded personally"


@pytest.fixture()
def own_document_on_disk(history, monkeypatch, tmp_path):
    """把「自己上传的那份文件」接上真资源链：目录行 + 磁盘上真存在的一个版本。"""
    path = tmp_path / "r295-own-file.txt"
    path.write_bytes(OWN_FILE_BYTES)
    version = dict(_doc(OWN_DOC, DEPT_FIN, 1, KEEPER_ID))
    version["storage_path"] = str(path)
    monkeypatch.setattr(
        history,
        "list_document_versions",
        lambda name, *a, **k: [dict(version)] if name == OWN_DOC else [],
    )
    return version


def _open_own_file(client, username):
    client.headers.update({"Authorization": "Bearer " + create_token(username)})
    return client.get("/api/v1/documents/" + OWN_DOC + "/file")


def test_the_owner_still_reads_their_own_file_after_the_move(history, client, store, own_document_on_disk):
    """判据③：部门挪走了，本人对自己那份文件的下载照旧通——这一格一格都不许动。

    同一个人、同一时刻、同一份文档：历史里引用它的那一轮换了脸，文件本身仍然打得开。
    两格出自两枚不同的闸门（检索闸门没有 owner 这个概念，资源闸门有），这正是本条钉
    要钉住的分界——不许有人把「回读收紧」顺手做成「owner 对自己文件也读不到」。
    """
    store.move(KEEPER, DEPT_RES)
    response = _open_own_file(client, KEEPER)
    assert response.status_code == 200, response.text
    assert response.content == OWN_FILE_BYTES

    payload = _read(client).json()
    assert OWN_TURN_BODY not in _blob(payload), "反证：历史那一格没裁住"
    assert _masked(payload), "历史那一轮必须仍然带着那张脸"


def test_a_foreign_account_still_cannot_open_that_file(history, client, store, own_document_on_disk):
    """正向钉的另一半：owner_match 只认本人，别的人按部门不匹配照样吃 403。"""
    response = _open_own_file(client, OUTSIDER)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "department_scope_denied"
    assert OWN_FILE_BYTES.decode("utf-8") not in response.text


# ==================== 判据⑤：三枚常驻反证 ====================


def test_counter_evidence_dropping_the_readback_gate_reads_the_old_answer_back(
    history, client, store, monkeypatch
):
    """反证①（判据①②）：把回读这道闸门摘掉，旧部门那一轮的正文与引用就都读回来了。

    如果这条绿是靠别的东西撑着的（回读根本没读消息、或换脸写死在别处），摘掉闸门不会
    有任何变化，本枚当场红。
    """
    store.move(KEEPER, DEPT_RES)
    assert OLD_TURN_BODY not in _blob(_read(client).json())

    monkeypatch.setattr(
        history, "_history_scope_face", lambda msgs, principal, sid: ([dict(m) for m in msgs], 0)
    )
    payload = _read(client).json()
    blob = _blob(payload)
    assert OLD_TURN_BODY in blob, "反证失效：摘掉闸门旧正文仍然读不回来，说明挡它的不是这枚判定"
    assert FIN_DOC in blob, "反证失效：摘掉闸门旧部门的文档引用仍然没露出来"
    assert OWN_TURN_BODY in blob
    assert payload["withheld_turns"] == 0


def test_counter_evidence_an_always_true_gate_widens_the_visible_surface(
    history, client, store, monkeypatch
):
    """反证②（判据②）：把闸门换成恒真，可见面立刻变宽——越权面确实由这枚谓词界定。

    恒真的形状就是「departments=None + 全密级」，也就是管理员那一档的谓词：换上它之后
    旧部门与跨密级两轮都读得回来。若判定其实另有一套（本单新造的口径），换谓词不会动，
    本枚当场红。
    """
    from app.rag.filters import DocumentRetrievalScope

    store.move(KEEPER, DEPT_RES)
    baseline = _read(client).json()
    assert baseline["withheld_turns"] == 2

    always_true = DocumentRetrievalScope(
        filters={},
        reason_code="administrator_scope",
        classification_levels=frozenset({1, 2, 3, 4}),
        departments=None,
    )
    monkeypatch.setattr(
        history, "resolve_document_retrieval_scope", lambda principal: always_true
    )
    payload = _read(client).json()
    assert payload["withheld_turns"] == 0, "恒真闸门下还裁得住，说明裁它的不是这枚谓词"
    blob = _blob(payload)
    for token in (OLD_TURN_BODY, OWN_TURN_BODY, NEW_TURN_BODY, PLAIN_TURN_BODY):
        assert token in blob, "反证失效：" + token + " 在恒真闸门下仍读不回来"
    assert _masked(payload) == []


def test_counter_evidence_tightening_owner_match_goes_red_on_the_document_leg_only(
    history, client, store, monkeypatch, own_document_on_disk
):
    """反证③（判据③）：把 owner_match 那一格一起收紧，红的只有文档腿，回读那张脸一字不变。

    这就是「两格确实被分开了」的证明：两枚判定若共用一套口径，收紧 owner_match 会同时
    改变回读的可见集，本枚当场红。
    """
    from app.common import policy

    store.move(KEEPER, DEPT_RES)
    assert _open_own_file(client, KEEPER).status_code == 200
    before = _read(client).json()

    monkeypatch.setattr(policy, "_OWNER_CONTROLLED_ACTIONS", frozenset())
    refused = _open_own_file(client, KEEPER)
    assert refused.status_code == 403, "反证失效：收紧 owner_match 之后本人还是读得到自己的文件"
    assert refused.json()["detail"] == "department_scope_denied"

    after = _read(client).json()
    assert after == before, "回读那一格不许被 owner_match 带着动：两枚闸门必须分开"
