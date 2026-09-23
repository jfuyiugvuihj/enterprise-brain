"""R179 · chat.py 族越权矩阵四格的常驻反证（R163 矩阵 / 跟进单 §87 六认领表）。

钉的是 R163 那 51 格跨域矩阵里最后落在 ``app/api/v1/chat.py`` 的四格：

  B 类 ``legacy_chat.hidden_document_says_no_relevant_document`` —— 旧版 /chat 把
      「命中了资料但一份都不给看」写成一句写死的「暂无相关文档」；
  B 类 ``document_route.nodept_catalog_answers_empty_list`` —— 目录用一个过滤后的
      空列表同时回答「这里没有文档」和「有文档，只是你没权看」；
  C 类 ``session_route.peer_probe_of_anothers_session`` 与 ``.admin_...`` —— 会话
      归属拒绝回 404 是对的（防资源枚举），但「有人拿这个 id 来探过」在审计台账里
      查不到一笔。

第五格 ``alert_route.foreign_manager_reads_scoped_alert`` 不在本件范围内：它是 A 类，
落点是 app/api/v1/alerts.py 的建表与告警归属列（migrations/**），两处都排在 R179 的
禁入清单里，且矩阵自己把它记成「R1 裁定 (c)：保持 staff 403、manager 可读全司」的
已裁遗留。本件不为它编造绿，只在交工报告里原样交回总控。

全部离线：进程内 TestClient，零起服务、零模型、零库；审计落点由 tests/conftest.py 钉进临时目录。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

DEPT_OWN = "r179-finance"
DEPT_FOREIGN = "r179-hr"

#: 哨兵：这一刻它们确实存在于进程里（别人文档的正文、别人的会话正文、别人的文件名）。
BODY_TOKEN = "R179T-BODY 这一段正文只属于别人的文档"
DOC_TOKEN = "R179T-DOC 这一段是别人文档的正文"
SOURCE_NAME = "R179-SRC-foreign-doc.txt"
SOURCE_STEM = "R179-SRC-foreign-doc"

#: 判据②甩锅词表的一个取样：说错脸时必然撞上其中一枚（与矩阵 ABSENCE_BLAME 同族）。
ABSENCE_LIES = ("暂无相关文档", "暂无数据", "没有数据", "no relevant", "no data")
#: 「有但不能看」必须说出的因由。
HONEST_MARKER = "可见范围"
STABLE_CODES = frozenset(
    {
        "department_scope_denied",
        "clearance_insufficient",
        "resource_scope_missing",
        "permission_denied",
    }
)

FOREIGN_SESSION = "r179-session-foreign"
MINE_SESSION = "r179-session-mine"
QUERY = "r179zzq denial probe"

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
    """包一层 chat 模块的 record_audit：原实现照调，顺手取位置参数（沿 R175 的取证件形状）。"""
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


# ================================================ 会话腿：C 类两格 + 五扇门


def _session_registry(monkeypatch, chat, tmp_path):
    from app.agents.contracts import Principal
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "session-meta.json")
    registry.bind(FOREIGN_SESSION, Principal.from_user(ACCOUNTS["keeper"]))
    registry.bind(MINE_SESSION, Principal.from_user(ACCOUNTS["xdept"]))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(
        chat, "_list_sessions", lambda: [{"id": FOREIGN_SESSION}, {"id": MINE_SESSION}]
    )
    monkeypatch.setattr(
        chat,
        "_get_session_messages",
        lambda *_a, **_k: [{"role": "assistant", "content": BODY_TOKEN}],
    )
    return registry


@pytest.mark.parametrize(("caller", "label"), [("xdept", "同级同事"), ("root", "管理员")])
def test_a_probe_of_anothers_session_still_answers_404_and_files_a_denial(
    client, monkeypatch, tmp_path, audit_rows, caller, label
):
    """C 类格：404 那半条一字未动，补的是「拦下人之后在既有通路留一笔」。"""
    import app.api.v1.chat as chat

    _session_registry(monkeypatch, chat, tmp_path)
    _as(client, caller)

    probe = client.get(f"/api/v1/sessions/{FOREIGN_SESSION}")

    assert probe.status_code == 404, "别人的会话仍然必须像不存在一样（防资源枚举）"
    assert probe.json()["detail"] == "resource_not_found"
    assert BODY_TOKEN not in probe.text, "404 不许把别人的会话正文带出来"

    denials = [
        row
        for row in audit_rows
        if row["outcome"] == "denied" and row["resource"] == FOREIGN_SESSION
    ]
    assert denials, f"反证①：{label}的这次越权探测在审计台账里查不到一笔"
    row = denials[0]
    assert row["username"] == ACCOUNTS[caller]["username"], "主体必须是来探测的那个人"
    assert row["reason"] == "permission_denied", "稳定码不许被换成一句人读的话"
    assert row["action"] == "resource:view"
    assert BODY_TOKEN not in _blob(denials), (
        "反证：台账里混进了别人的会话正文——白名单只许主体 / 资源标识 / 判定结果"
    )


def test_the_owner_still_reads_the_same_session_end_to_end(client, monkeypatch, tmp_path):
    """正向对照：绿不是把口子关死刷出来的——本人读自己的会话仍拿得到正文。"""
    import app.api.v1.chat as chat

    _session_registry(monkeypatch, chat, tmp_path)
    _as(client, "xdept")

    mine = client.get(f"/api/v1/sessions/{MINE_SESSION}")
    assert mine.status_code == 200
    assert BODY_TOKEN in mine.text, "本人读不到自己的正文 = 上面那枚哨兵在空转"

    listed = client.get("/api/v1/sessions").json()["sessions"]
    assert [row["id"] for row in listed] == [MINE_SESSION]
    assert FOREIGN_SESSION not in _blob(listed)


@pytest.mark.parametrize(
    ("verb", "url", "json_body", "action"),
    [
        ("delete", "/api/v1/sessions/{sid}", None, "resource:delete"),
        ("post", "/api/v1/ask/{sid}/cancel", None, "resource:delete"),
        ("get", "/api/v1/hitl/pending?session_id={sid}", None, "resource:view"),
        ("post", "/api/v1/approve", "approve", "resource:approve"),
    ],
)
def test_every_session_door_files_the_refusal_under_its_own_verb(
    client, monkeypatch, tmp_path, audit_rows, verb, url, json_body, action
):
    """一处加账、五扇门受益，动词还不许全塞成 view：事后要分得清谁想删、谁想批。"""
    import app.api.v1.chat as chat

    _session_registry(monkeypatch, chat, tmp_path)
    _as(client, "xdept")

    target = url.replace("{sid}", FOREIGN_SESSION)
    if json_body:
        response = client.post(
            target, json={"session_id": FOREIGN_SESSION, "approved": True}
        )
    else:
        response = client.request(verb.upper(), target)

    assert response.status_code == 404, response.text
    denials = [
        row
        for row in audit_rows
        if row["outcome"] == "denied" and row["resource"] == FOREIGN_SESSION
    ]
    assert denials, f"反证①：{target} 这一扇门的拒绝没落账"
    assert [row["action"] for row in denials] == [action]


def test_falsification_the_denial_accounting_runs_on_that_one_pathway(
    client, monkeypatch, tmp_path, audit_rows
):
    """反证①常驻：把 chat 的审计通路摘掉，同一套取证必须一行都查不到。

    如果拒绝记账走了第二条通道（自造事件表、或绑到别的模块名上），这里摘不掉它，
    本枚当场红——R185 那笔「只钉源码形状、当场放行一条断路」的教训钉在这里。
    """
    import app.api.v1.chat as chat

    _session_registry(monkeypatch, chat, tmp_path)
    _as(client, "xdept")
    assert client.get(f"/api/v1/sessions/{FOREIGN_SESSION}").status_code == 404
    assert [row for row in audit_rows if row["outcome"] == "denied"]

    monkeypatch.setattr(chat, "record_audit", lambda *a, **k: {})
    rows_before = len(audit_rows)
    assert client.get(f"/api/v1/sessions/{FOREIGN_SESSION}").status_code == 404
    assert len(audit_rows) == rows_before, "摘掉通路还在长账 = 存在第二套审计形状"


def test_the_ownership_predicate_stays_the_single_source_of_truth(
    client, monkeypatch, tmp_path
):
    """判据③不越界：会话归属只许 app/storage/sessions.py 的 is_owned_by 一处判定。

    两向都验：谓词说「不是你的」就必须 404，说「是你的」就必须放行。chat.py 若自己
    抄一份归属判定，第一向会先放行、被这里判红。
    """
    import app.api.v1.chat as chat
    from app.storage import sessions as session_storage

    seen: list[str] = []

    def _deny(self, session_id, principal):
        seen.append(session_id)
        return False

    monkeypatch.setattr(session_storage.SessionRegistry, "is_owned_by", _deny)
    _as(client, "xdept")
    assert client.get(f"/api/v1/sessions/{MINE_SESSION}").status_code == 404
    assert seen == [MINE_SESSION], "chat.py 没走 is_owned_by：归属判定被就地抄了第二份"

    monkeypatch.setattr(
        session_storage.SessionRegistry, "is_owned_by", lambda self, sid, p: True
    )
    monkeypatch.setattr(chat, "_get_session_messages", lambda *_a, **_k: [])
    assert client.get(f"/api/v1/sessions/{MINE_SESSION}").status_code == 200


# ============================================ 目录腿：B 类假话 + 拒绝落账


def _one_foreign_document(monkeypatch, chat, tmp_path):
    """目录里只放一份「属于 r179-finance、正文带哨兵」的真实文档。"""
    stored = tmp_path / SOURCE_NAME
    stored.write_text(DOC_TOKEN, encoding="utf-8")
    row = {
        "filename": SOURCE_NAME,
        "storage_path": str(stored),
        "department": DEPT_OWN,
        "classification": 1,
        "owner_id": "u-r179-owner",
        "version": 1,
    }
    monkeypatch.setattr(chat, "current_documents", lambda *a, **k: [dict(row)])
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *a, **k: [dict(row)] if name == SOURCE_NAME else [],
    )
    return row


@pytest.mark.parametrize("caller", ["nodept", "xdept"])
def test_the_catalog_says_documents_exist_but_are_not_visible(
    client, monkeypatch, tmp_path, caller
):
    """B 类格：「有但你不能看」不能被说成「这里没有文档」，也不许点名是哪一份。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)
    _as(client, caller)

    body = client.get("/api/v1/documents/catalog").json()

    assert body["documents"] == [], "被拒的文档不许混进可访问列表"
    restricted = body.get("restricted")
    assert restricted, "反证②：目录把「有但你不能看」退回了空列表假话"
    assert restricted["count"] == 1
    assert restricted["reason_codes"], "只报数量不报因由 = 第二张假话"
    assert set(restricted["reason_codes"]) <= STABLE_CODES, "因由必须是稳定码"
    assert HONEST_MARKER in restricted["message"]
    leak = _blob(restricted)
    for secret in (DOC_TOKEN, SOURCE_NAME, SOURCE_STEM):
        assert secret not in leak, f"反证：成功体点名了资源（{secret}）"
    assert set(body) == {"documents", "restricted"}


def test_the_catalog_invents_no_refusal_for_someone_who_sees_everything(
    client, monkeypatch, tmp_path
):
    """正向对照：看得到全部的人不许被凭空造一笔拒绝（keeper 同部门 / root 管理员）。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)

    for caller in ("keeper", "root"):
        _as(client, caller)
        body = client.get("/api/v1/documents/catalog").json()
        assert [row["filename"] for row in body["documents"]] == [SOURCE_NAME]
        assert "restricted" not in body, f"{caller} 看得见的东西不能被写成拒绝"
        assert set(body) == {"documents"}


def test_catalog_denial_is_audited_with_subject_resource_verdict_only(
    client, monkeypatch, tmp_path, audit_rows
):
    """目录的每条拒绝都走同一条 record_audit：主体 / 文件名 / 判定结果，零正文。"""
    import app.api.v1.chat as chat
    from app.common.permissions import ACTION_VIEW

    row = _one_foreign_document(monkeypatch, chat, tmp_path)
    _as(client, "xdept")
    client.get("/api/v1/documents/catalog")

    denials = [r for r in audit_rows if r["outcome"] == "denied" and r["resource"] == SOURCE_NAME]
    assert denials, "反证①：目录的文件级拒绝没落既有审计通路"
    assert len(denials) == 1
    line = denials[0]
    assert line["action"] == ACTION_VIEW
    assert line["username"] == "xdept"
    from app.agents.contracts import Principal

    expected = chat._document_authorization_decision(
        Principal.from_user(ACCOUNTS["xdept"]), SOURCE_NAME, row, ACTION_VIEW
    ).reason_code
    assert line["reason"] == expected, "台账写的原因码必须是这次真正生效的判定，不许另猜一个"
    for secret in (DOC_TOKEN, BODY_TOKEN):
        assert secret not in _blob(denials), f"反证：审计里混进了文档正文（{secret}）"


def test_falsification_catalog_denial_accounting_shares_the_one_pathway(
    client, monkeypatch, tmp_path, audit_rows
):
    """反证①常驻（目录侧）：摘掉通路，目录的拒绝同样一行都长不出来。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)
    _as(client, "xdept")
    assert client.get("/api/v1/documents/catalog").json()["restricted"]
    assert [r for r in audit_rows if r["outcome"] == "denied"]

    monkeypatch.setattr(chat, "record_audit", lambda *a, **k: {})
    rows_before = len(audit_rows)
    body = client.get("/api/v1/documents/catalog").json()
    assert len(audit_rows) == rows_before, "摘掉通路还在长账 = 存在第二套审计形状"
    assert body["restricted"], "说话那半条与留账那半条是两层，摘账不许把话也摘掉"


# ==================================== 旧版 /chat 腿：B 类假话的两张脸


class _BlindRetriever:
    """无视 where 全量召回：把「检索层有没有裁」与「本地闸门裁不裁」分开。"""

    def __init__(self, chunks):
        self.chunks = chunks

    def search(self, query, k=5, where=None):
        return [dict(chunk) for chunk in self.chunks]


class _RecordingModel:
    def __init__(self):
        self.prompts: list[str] = []

    def chat(self, messages=None, source=None, stream=True):
        self.prompts.append(messages[0]["content"])
        delta = SimpleNamespace(content="R179-ANSWERED")
        return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]


def _legacy_chat_prompt(client, monkeypatch, chat, chunks):
    model = _RecordingModel()
    monkeypatch.setattr(chat, "retriever", _BlindRetriever(chunks))
    monkeypatch.setattr(chat, "model_handler", model)
    _as(client, "keeper")
    response = client.post("/api/v1/chat", json={"message": QUERY})
    assert response.status_code == 200, response.text
    return model.prompts[0], response.text


def test_the_absence_face_still_speaks_when_nothing_was_recalled(
    client, monkeypatch, tmp_path
):
    """两张脸之一：检索真没命中，「暂无相关文档」这句必须留着（不许一刀切成权限话术）。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)
    prompt, wire = _legacy_chat_prompt(client, monkeypatch, chat, [])

    assert "暂无相关文档" in prompt
    assert HONEST_MARKER not in prompt, "什么都没命中时凭空造一笔权限拒绝，同样是假话"
    assert "R179-ANSWERED" in wire


@pytest.mark.parametrize(
    ("chunk", "code", "why"),
    [
        ({"content": DOC_TOKEN, "source": SOURCE_NAME, "department": DEPT_FOREIGN, "classification": 1},
         "department_scope_denied", "同密级、跨部门"),
        ({"content": DOC_TOKEN, "source": SOURCE_NAME, "department": DEPT_OWN, "classification": 3},
         "clearance_insufficient", "同部门、越密级"),
        ({"content": DOC_TOKEN, "source": SOURCE_NAME, "department": DEPT_OWN, "classification": None},
         "resource_scope_missing", "元数据读不出来，按 fail-closed 收"),
    ],
)
def test_the_hidden_face_names_the_authority_instead_of_the_absence(
    client, monkeypatch, tmp_path, chunk, code, why
):
    """两张脸之二（B 类格的病灶）：命中了资料却一份都不给看，不能说成「暂无相关文档」。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)
    prompt, wire = _legacy_chat_prompt(client, monkeypatch, chat, [chunk])

    for lie in ABSENCE_LIES:
        assert lie not in prompt, f"反证②：{why} 被说成了「{lie}」"
    assert HONEST_MARKER in prompt, f"{why}：说不出权限因由就是第二张假话"
    assert code in prompt, f"{why}：稳定码 {code} 必须随话一起给"
    for secret in (DOC_TOKEN, SOURCE_NAME, SOURCE_STEM):
        assert secret not in prompt, f"反证：提示词点名了被裁掉的文档（{secret}）"
        assert secret not in wire


def test_the_two_faces_are_not_the_same_sentence(client, monkeypatch, tmp_path):
    """反证②常驻：把两张脸重新合成一句，这一枚当场红。"""
    import app.api.v1.chat as chat

    _one_foreign_document(monkeypatch, chat, tmp_path)
    absent, _ = _legacy_chat_prompt(client, monkeypatch, chat, [])
    hidden = {
        "content": DOC_TOKEN,
        "source": SOURCE_NAME,
        "department": DEPT_FOREIGN,
        "classification": 1,
    }
    withheld_prompt, _ = _legacy_chat_prompt(client, monkeypatch, chat, [hidden])

    def _context_of(prompt: str) -> str:
        return prompt.split("## 参考文档", 1)[1].split("## 用户问题", 1)[0]

    assert _context_of(absent) != _context_of(withheld_prompt), (
        "反证②：「检索没命中」与「命中了但一份都不给看」又长成同一句了"
    )


# ============================== 归因器与判定不得长成两套口径


@pytest.mark.parametrize("role", ["staff", "manager", "admin"])
@pytest.mark.parametrize("classification", [1, 2, 3, None, "x"])
def test_refusal_code_agrees_with_allows_on_every_combination(role, classification):
    """判据③不越界：refusal_code 只对 allows 已经裁掉的块说话，且只报封闭码。

    账号一律带部门（无部门账号在闸门处直接被拒，那一支由 R178 的常驻件钉），
    变的只有块的两个维度：部门对不对、密级读不读得出来。
    """
    from app.agents.contracts import Principal
    from app.rag.filters import resolve_document_retrieval_scope

    scope = resolve_document_retrieval_scope(
        Principal.from_user(
            {"id": f"u-{role}", "username": role, "role": role, "department": DEPT_OWN}
        )
    )
    checked = 0
    rejected = 0
    for department in (DEPT_OWN, DEPT_FOREIGN, ""):
        hit = {
            "content": "x",
            "source": "s.txt",
            "department": department,
            "classification": classification,
        }
        if scope.allows(hit):
            assert scope.refusal_code(hit) == "", (
                "被放行的块不许有拒绝码：判定与解释必须同出一个口径"
            )
        else:
            rejected += 1
            assert scope.refusal_code(hit) in STABLE_CODES, (
                f"归因器造出了词表外的码：{scope.refusal_code(hit)!r}"
            )
        checked += 1
    assert checked == 3
    if scope.reason_code != "administrator_scope":
        # 管理员那一档本来就该全放行，没有拒绝可验；其余档一次都没裁过东西 = 这枚钉在空转。
        assert rejected, "整个参数化一次都没裁过东西 = 这枚钉在空转"