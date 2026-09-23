"""R178 第 1 格 —— R163 交回的 C 类 retrieval.nodept_account_is_refused。

复现的原文（不抄结论，本树自证）：app/rag/filters.py:102-106 在 raise 之前不落任何审计，
全件唯一的 record_audit 在 :129-139 的 record_retrieval_scope 里，而 :127-128 一进门就把
非 administrator_scope 挡掉 ⇒ 「无部门账号被检索闸门拒了」这件事今天查不到是谁干的。

本件只钉两件事：
- 判据②（审计补齐）：四条 raise 出处（None 主体 / 停用账号 / 无正密级 / 无部门）都必须
  在既有 record_audit 通路上留下一条 outcome=denied 的行，并且沿 observability 读得回来。
- 判据②的牙齿：这条审计行只许写「主体 + 资源标识 + 判定结果」，不许携带别人的文档正文、
  部门实际值、密级实际值。

全进程内：不起服务、不打模型、不连 PG；审计落点由 tests/conftest.py 钉在临时目录。
判定逻辑与过滤顺序本件一个字都不动。
"""
from __future__ import annotations

import json

import pytest

from app.common.audit import get_audit_events
from app.common.identity import Principal

#: 检索面的资源标识：审计行里写的是「哪个面拒的」，不是「哪份文档」。
SURFACE = "document_retrieval"

#: 拒判的封闭码表，与 RetrievalScopeError 的四条出处一一对应。
DENIAL_CODES = frozenset(
    {
        "authentication_required",
        "permission_denied",
        "authorization_unavailable",
    }
)

#: 哨兵值：这一刻它们确实存在于进程里（别人文档的正文/文件名/部门实际值/密级实际值），
#: 所以「把上下文顺手写进审计」这种实现一旦出现在本格上就会当场红。
BODY_TOKEN = "R178T-BODY 这一段正文只属于别人的文档"
SOURCE_TOKEN = "R178-SRC-FOREIGN.docx"
FOREIGN_DEPARTMENT = "r178-foreign-dept-对外部门"
RESOURCE_CLASSIFICATION = "topsecret-r178"

#: 主体自身字段由 record_audit 自己从 principal 投影（username/role/owner_id/
#: actor_clearance/actor_departments），那是「主体」，不是「资源实际值」。
SUBJECT_FIELDS = (
    "username",
    "role",
    "owner_id",
    "auth_source",
    "actor_clearance",
    "actor_departments",
)

AUDIT_BINDINGS = (
    "app.common.audit.record_audit",
    "app.rag.filters.record_audit",
)


def _account(kind: str, **overrides) -> dict:
    user = {
        "id": "u-r178-" + kind,
        "username": "r178-" + kind + "-account",
        "role": "staff",
        "department": "",
    }
    user.update(overrides)
    return user


def _principal(kind: str, **overrides) -> Principal:
    return Principal.from_user(_account(kind, **overrides))


@pytest.fixture()
def audit_sink(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """把 record_audit 包一层：原实现照调（落点已沙箱），顺手把调用参数记下来。"""
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
                "event": dict(event),
                "kwargs": dict(kwargs),
            }
        )
        return event

    for target in AUDIT_BINDINGS:
        monkeypatch.setattr(target, _record)
    return rows


def _refuse(principal) -> str:
    """走真实闸门一次，返回它交出的稳定码。"""
    from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope

    with pytest.raises(RetrievalScopeError) as caught:
        resolve_document_retrieval_scope(principal)
    return str(caught.value.code)


def _denied(rows: list[dict], actor: str) -> list[dict]:
    return [
        row
        for row in rows
        if row["outcome"] == "denied" and row["username"] == actor and row["resource"] == SURFACE
    ]


# ==================== 判据①／②：拒绝必须留账，且查得到是谁干的 ====================


@pytest.mark.parametrize(
    ("kind", "overrides", "expect_code"),
    [
        pytest.param("nodept", {}, "authorization_unavailable", id="nodept"),
        pytest.param("inactive", {"status": "disabled"}, "permission_denied", id="inactive"),
        pytest.param("noclearance", {"clearance": 0}, "authorization_unavailable", id="no-clearance"),
    ],
)
def test_refusal_leaves_one_denied_audit_row_for_that_actor(
    audit_sink, kind, overrides, expect_code
) -> None:
    """三条「有主体」的拒绝：账上必须有一行说得出是谁、在哪个面、因为哪一条。"""
    from app.rag.filters import build_document_retrieval_filter

    principal = _principal(
        kind, department="" if kind == "nodept" else FOREIGN_DEPARTMENT, **overrides
    )
    if kind == "noclearance":
        # from_user 里 ``clearance or clearance_for(role)`` 会把 0 顶回角色默认档，
        # 所以这一支只能直接改模型，不许在账号字典里假装一个走不到的 0。
        principal = principal.model_copy(update={"clearance": 0})
    assert _refuse(principal) == expect_code

    rows = _denied(audit_sink, principal.username)
    assert rows, "检索闸门把 " + kind + " 拒了，审计台账里一行 denied 都没有"
    assert [row["reason"] for row in rows] == [expect_code], (
        "一次拒绝落了 " + str(len(rows)) + " 行，或写了别的码：" + str(rows)
    )
    # 同一个判定只有一处落账：换一条入口（只要 where 子句的那条腿）再来一次，还得留账。
    with pytest.raises(ValueError):
        build_document_retrieval_filter(principal)
    assert len(_denied(audit_sink, principal.username)) == 2, (
        "拒绝落在 resolve_document_retrieval_scope 上，但换 build_document_retrieval_filter "
        "这条入口就查不到——说明补的是分支，不是闸门"
    )


def test_anonymous_refusal_is_audited_as_an_attempt(audit_sink) -> None:
    """无主体的那次拒绝也要留一笔：查不到「是谁」，但至少查得到「有人撞了这道门」。"""
    assert _refuse(None) == "authentication_required"
    assert _denied(audit_sink, "anonymous"), "无主体的检索拒绝连一行尝试记录都没有"


def test_denied_row_comes_back_through_the_shared_journal() -> None:
    """判据②的反面自查：不许自造第二套事件表——既有通路读得回来才算落了账。"""
    principal = _principal("journal")
    _refuse(principal)
    rows = get_audit_events(username=principal.username, outcome="denied", resource=SURFACE)
    assert rows, "既有审计读口 get_audit_events 读不到这一笔"
    assert rows[-1]["reason"] == "authorization_unavailable"
    assert rows[-1]["action"] == "resource:view"


def test_an_allowed_scope_still_writes_no_denied_row(audit_sink) -> None:
    """正向对照：作用域合法的账号不该被这一格刷出拒绝行，否则「留账」是空转。"""
    from app.rag.filters import resolve_document_retrieval_scope

    principal = _principal("allowed", department=FOREIGN_DEPARTMENT)
    scope = resolve_document_retrieval_scope(principal)
    assert scope.reason_code == "department_scope"
    assert not _denied(audit_sink, principal.username)


# ==================== 判据②的牙齿：审计字段白名单 ====================

#: 允许出现在拒绝行 after/before_summary 与 resource_scope 里的键：一条都不许有。
FORBIDDEN_SUMMARY_KEYS = ("filters", "classification", "department", "content", "source")


def test_denied_row_carries_subject_resource_and_verdict_only(audit_sink) -> None:
    """白名单钉：主体 + 资源标识 + 判定结果，别的一个字段都不许有。"""
    principal = _principal("whitelist", department="")
    _refuse(principal)
    rows = _denied(audit_sink, principal.username)
    assert rows, "先要有行，才谈得上白名单"
    for row in rows:
        assert set(row["kwargs"]) <= {"request_id"}, (
            "拒绝行偷偷带了白名单之外的关键字参数：" + str(sorted(row["kwargs"]))
        )
        assert row["event"]["after_summary"] == {}, "判定结果之外不许写摘要"
        assert row["event"]["before_summary"] == {}, "判定结果之外不许写摘要"
        assert row["event"]["resource_scope"] == {}, (
            "资源实际值（部门、密级）不许进这一条审计行"
        )
        assert row["resource"] == SURFACE, "资源标识只许是检索面，不许是某个文档名"
        assert row["reason"] in DENIAL_CODES, "码表之外不许发明新词"
        for key in FORBIDDEN_SUMMARY_KEYS:
            assert key not in json.dumps(
                {
                    "after": row["event"]["after_summary"],
                    "before": row["event"]["before_summary"],
                    "scope": row["event"]["resource_scope"],
                },
                ensure_ascii=False,
                default=str,
            )


def test_denied_row_never_repeats_the_documents_it_refused(audit_sink) -> None:
    """别人的文档正文、部门实际值、密级实际值——一个字都不许出现在拒绝行里。"""
    principal = _principal("leak")
    _refuse(principal)
    rows = _denied(audit_sink, principal.username)
    assert rows
    sentinels = (BODY_TOKEN, SOURCE_TOKEN, FOREIGN_DEPARTMENT, RESOURCE_CLASSIFICATION)
    for row in rows:
        blob = json.dumps(
            {
                key: value
                for key, value in row["event"].items()
                if key not in {"event_id", "timestamp", "created_at", "expires_at"}
            },
            ensure_ascii=False,
            default=str,
        )
        for sentinel in sentinels:
            assert sentinel not in blob, "审计行里出现了哨兵值 " + sentinel


def test_refusal_path_touches_no_corpus_before_it_refuses(audit_sink) -> None:
    """拒绝发生在召回之前：这一格不许把别人的 chunk 变成审计的输入。"""
    corpus = [
        {"content": BODY_TOKEN, "source": SOURCE_TOKEN, "department": FOREIGN_DEPARTMENT,
         "classification": RESOURCE_CLASSIFICATION},
    ]
    pipeline = _blind_pipeline(corpus)
    principal = _principal("corpus")
    with pytest.raises(ValueError):
        pipeline.search_for_principal("r178 probe", principal, top_k=3)
    rows = _denied(audit_sink, principal.username)
    assert rows, "越权语料在场时，检索拒绝同样要留账"
    blob = json.dumps([row["event"] for row in rows], ensure_ascii=False, default=str)
    for sentinel in (BODY_TOKEN, SOURCE_TOKEN, FOREIGN_DEPARTMENT, RESOURCE_CLASSIFICATION):
        assert sentinel not in blob


def _blind_pipeline(chunks: list[dict]):
    """照 R163 的桩形搭一条最小假召回：语义腿无视 where 全量返回。

    本件的断言只用到「闸门在召回之前就把请求拒了」这一点，所以这条腿不需要真 Chroma。
    """
    from app.rag.retrieval_pipeline import RetrievalPipeline

    class _Semantic:
        def search(self, query, k, where):
            return [dict(chunk) for chunk in chunks]

    class _Bm25:
        def search(self, query, k, pred):
            return [dict(chunk) for chunk in chunks if pred(dict(chunk))]

    class _NoRewrite:
        @staticmethod
        def rewrite(question):
            return {"rewrites": [], "sub_questions": []}

    class _NoRerank:
        @staticmethod
        def rerank(query, docs, top_k):
            return list(docs)[:top_k]

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = _Semantic()
    pipeline.bm25 = _Bm25()
    pipeline.rewriter = _NoRewrite()
    pipeline.reranker = _NoRerank()
    return pipeline

