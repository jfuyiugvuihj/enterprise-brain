"""R159 —— 阶段 C「越权命中 0 条」验收矩阵（只读取证，不改一行产品代码）。

计划书 docs/handoff/2026-09-17-perf-architecture-plan.md §6 阶段表里，C 线（检索与缓存）
的第一条硬判据是「越权命中 0 条」，§8.5 还写着「阶段 C 未完成前，E 线越权判据不得宣布通过」。
仓库里权限相关测试件有 20+ 枚，但各验各的路由，从来没有一个可宣布的读数。本件把
「身份 x 资源面 x 断言」做成一张表，一格一条参数化用例，跑完就是一条读数。

## 三列断言（每一格自己勾选要验哪几列）

- content（判据①）别人的内容一个字都拿不到：正文令牌、文件名、表格行、图表、导出物
  一律不得出现在响应里。同一格还放正向对照（entitled）：属于本人、该看见的东西必须
  真的出现，否则「谁都拿不到」的空转格子也能刷满分。
- honesty（判据②，R62 的诚实性面）不能把「因权限被隐藏」说成「代码没跑通」或「根本没有
  数据」。钉法：被隐藏的那一格交出的人话里不得出现甩锅词（EXECUTION_BLAME / ABSENCE_BLAME），
  并且必须出现权限因由（AUTHORITY_WORDS，含平台自己的稳定码）；能力性拒绝还得对上
  expect_status / expect_reason（看板 G4 裁定：不得以 200 空列表答复无权限）。
- audit（判据③）越权请求要落审计日志。期望写成 audit_expect，三种形态：
  ("denied", 资源名子串) / ("allowed", 稳定码) / ("none", 书面理由)。
  选 ("none", ...) 时必须写清理由，不许静默跳过。

## R163 接手账（09-23，改的是本件自己，产品代码照旧一字未动）

- 起点两值 21 failed / 31 passed ⇒ 现在 **13 failed / 40 passed**（矩阵 53 条）。
- 其中 7 红是矩阵自己的桩搭错（URL 实名、写读两个 username、令牌只出自写口、默认密级判错轴），
  逐格归因写在格子的 root_cause="matrix" + evidence 里，修完全绿；剩 13 红全是产品侧：
  **A 内容越权 3 / B 说法不诚实 4 / C 审计缺席 6**（每格 finding + 文件:行证据 + 既存件对照）。
- 起点 50 格 → 现在 51 格：只补了一枚正向对照（intelligence_route.xdept_cannot_see_anothers_triples），
  零删格、零维度削减；那枚自相矛盾的死钉改成「按 ast 行区间只剥标记表本身」，牙齿见
  tests/test_r163_matrix_teeth.py（八枚标记逐条注入必红 + 真 pytest 磁盘取证）。

## R193 接手账（09-23，改的还是本件自己，产品代码照旧一字未动）

- 13 枚产品侧红格的**归因位**（新增字段 `Cell.fixed_by`）逐格点名到真实存在的主干并树件：
  R176 `3431053` / R177 `40278eb` / R178 `a6c2710` / R179 `f51576f` / R180 `4f96cb6`，
  每格改前→改后的对照与 sha 真伪校验都在 tests/test_r163_matrix_teeth.py 里，由那件机检。
- 唯一一处产品侧「种子」缺陷修在本件自己里：`_drive_alert` 塞进 `alerts._MEM_ALERTS` 的那行
  从前不带 `department`，而 R176 的读侧口径是「本部门 + 无归属可见」，于是无归属行对任一
  manager 天然可见 ⇒ `alert_route.foreign_manager_reads_scoped_alert` 红在桩不红在产品码
  （跟进单 §90 八 已写明这一条）。现在那行带上 `"department": DEPT_OWN`。
- 各格的 `note` / `evidence` 两栏保留的是 **R159/R163 实测当时的现场**（含已被修掉的甩锅句、
  当时缺失的审计通路），那是归因的凭据，不随修复重写；今日读数一律以复跑为准。
  只有告警那一格的 note 例外——它把「种子不带归属」写成了「表没有归属列」，最易误读，本班改口。

## 本件的边界

- 只读取证：写域只有本文件与新增的 tests/test_r163_*.py。产品代码一个字没改，既存测试件一个字没改。
- 全程进程内：不起服务、不打容器、不连宿主模型端口（conftest 的 R56 闸门仍然生效）。
- 检索腿不依赖 app/rag/retriever.py 的真召回：R158 正在改那一条腿，本件注入假召回器，
  只验「权限谓词能不能被绕过」，因此本件不产出任何时延结论。
- 跑红的格子按任务书口径如实钉红，不 skip、不 xfail、不放宽断言。

## 红格子的三类根因（交工报告用）

- A 类＝内容越权（判据①）：别人的东西真的可达。
- B 类＝诚实性（判据②）：内容挡住但对外的说法是「没有数据 / 代码没跑通」。
- C 类＝审计缺席（判据③）：请求被拒了，但审计日志里查不到这一笔。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable

import pytest


# ==================== 语料与身份 ====================

DEPT_OWN = "r159-own"
DEPT_FOREIGN = "r159-fx"
#: 一条与全仓既有用例都不撞的检索问句：ASCII 生僻串，尽量不触发改写档与术语扩展腿。
QUERY = "r159zzq cross scope probe"
#: 归属轴的固定资源主人：只有 owner 本人能凭 owner_match 拿到（policy.py 里
#: _OWNER_CONTROLLED_ACTIONS 的注释把这条写成了产品明文设计，不是本件新加的规矩）。
RESOURCE_OWNER = "u-r159-resource-owner"


def _chunk(token: str, *, department: str, classification: int | None) -> dict[str, Any]:
    """一块语料：正文与文件名都带唯一令牌，这样「只拿到文件名」也算拿到内容。"""
    hit: dict[str, Any] = {
        "content": "R159T-" + token + " 这一段正文只在授权范围内可见。",
        "source": "R159-SRC-" + token + ".txt",
        "department": department,
    }
    if classification is not None:
        hit["classification"] = classification
    return hit


#: 七块语料，逐块只换一个维度，保证「跨部门」与「跨密级」两根轴的红灯不互相顶包。
CHUNKS: dict[str, dict[str, Any]] = {
    "own_l1": _chunk("OWN-L1", department=DEPT_OWN, classification=1),
    "own_l2": _chunk("OWN-L2", department=DEPT_OWN, classification=2),
    "own_l3": _chunk("OWN-L3", department=DEPT_OWN, classification=3),
    "fx_l1": _chunk("FX-L1", department=DEPT_FOREIGN, classification=1),
    "fx_l3": _chunk("FX-L3", department=DEPT_FOREIGN, classification=3),
    "nodept_l1": _chunk("NODEPT-L1", department="", classification=1),
    "noclass": _chunk("NOCLASS", department=DEPT_OWN, classification=None),
}

#: 判据②的两类不诚实表述。
EXECUTION_BLAME = ("代码", "沙箱", "执行未通过", "运行失败", "调用失败")
ABSENCE_BLAME = (
    "暂无数据",
    "暂无数据文件",
    "暂无相关文档",
    "没有数据",
    "没有可分析的数据行",
    "请先在数据分析面板上传",
    "no data",
    "no relevant",
)
#: 反面：说得出权限因由就算诚实。平台自己的稳定码也是可机读的因由，一并收下。
AUTHORITY_WORDS = (
    "权限",
    "无权",
    "授权",
    "密级",
    "部门",
    "可见范围",
    "不可见",
    "permission_denied",
    "department_scope_denied",
    "clearance_insufficient",
    "authorization_unavailable",
    "authorization_required",
    "resource_scope_missing",
    "authentication_required",
    "principal_inactive",
    "department_override_denied",
    "row_scope_denied",
    "no_visible_rows",
)

_ROLE_OF = {
    "keeper": "manager",
    "xdept": "manager",
    "xclear": "staff",
    "nodept": "staff",
    "peer": "manager",
    "admin": "admin",
    "auditor": "auditor",
}


def _account(kind: str, cell_id: str, **overrides: Any) -> dict[str, Any]:
    """造一个账号字典：username 全局唯一，审计才能按人归因到具体格子。"""
    role = _ROLE_OF[kind]
    department = "" if kind == "nodept" else (DEPT_FOREIGN if kind == "xdept" else DEPT_OWN)
    username = "r159-" + kind + "-" + cell_id
    user: dict[str, Any] = {
        "id": "u-" + username,
        "username": username,
        "role": role,
        "department": department,
    }
    user.update(overrides)
    return user


def _principal(kind: str, cell_id: str, **overrides: Any):
    from app.agents.contracts import Principal

    return Principal.from_user(_account(kind, cell_id, **overrides))


def _tokens(names: tuple[str, ...]) -> tuple[str, ...]:
    """把语料块名翻成「正文令牌 + 文件名主干」两串，缺一串就算漏。

    取 ASCII 主干而不是整句中文正文：任何一条腿把内容转了 URL 编码或 JSON 转义，整句
    可能匹配不上，而主干不会。文件名主干带 .txt 也行、改成 .csv 也行，都能命中。
    """
    out: list[str] = []
    for name in names:
        chunk = CHUNKS[name]
        out.append(str(chunk["content"]).split(" ")[0])
        out.append(str(chunk["source"]).split(".")[0])
    return tuple(out)


def _corpus(names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [dict(CHUNKS[name]) for name in names]


# ==================== 表格结构件 ====================


@dataclass
class Receipt:
    """一格跑完之后拿回来的证据：可见内容、HTTP 状态、稳定码、对外人话。"""

    payload: str = ""
    status: int | None = None
    reason: str = ""
    claim: str = ""
    notes: str = ""


@dataclass
class Cell:
    """矩阵的一格：身份 x 资源面 x 三列断言，外加「既存谁盖过这一格」的对照字段。"""

    cell_id: str
    surface: str
    identity: str
    drive: Callable[["Ctx", "Cell"], Receipt]
    corpus: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    entitled: tuple[str, ...] = ()
    actor_over: dict[str, Any] = field(default_factory=dict)
    check_content: bool = True
    check_honesty: bool = True
    check_audit: bool = True
    #: 这一格是「内容本该被挡住」的格子：判据②的措辞检查只在这种格子里生效。
    withheld: bool = True
    #: 账号本身没有可用作用域（无部门）却被答成 200 空列表时，必须当场说清是因由。
    told_no_scope: bool = False
    expect_status: int | None = None
    expect_reason: str = ""
    #: ("denied", 资源名子串) / ("allowed", 稳定码或空串) / ("none", 书面理由)
    audit_expect: tuple[Any, ...] = ("none", "")
    covered_by: str = ""
    note: str = ""
    #: R163 判据②的归因位：A=内容真越权 / B=挡住了但对外说法不对 / C=审计缺席 / 空=这一格绿
    finding: str = ""
    #: 这一格今天为什么是绿/红：product＝产品真的漏（本单不改，交回清单）；
    #: matrix＝矩阵自己的桩搭错（R163 已修，修完必须绿）。两值都不填＝这一格没被归因过。
    root_cause: str = ""
    #: 归因的产品代码路径证据，必须是「文件:行」，不许写「看起来是测试问题」。
    evidence: str = ""
    #: R193 归因位：这一格的 finding 由哪一枚**已并树**的主干件修掉，格式「R1xx@<sha7>」。
    #: 空 = 今天仍红且没有可修路径。tests/test_r163_matrix_teeth.py 按这一位分名单，并核 sha 真在仓库里。
    fixed_by: str = ""


class Ctx:
    """一格用例的运行现场：桩、临时目录、审计汇聚袋、账号注册表。"""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path
        self.sink: list[dict[str, str]] = []
        self.accounts: dict[str, dict[str, Any]] = {}
        self.username = ""
        self.principal = None
        self.audit_actor = ""
        self._finalizers: list[Callable[[], None]] = []

    # ---- 身份 ----
    def serve(self, cell: Cell) -> str:
        """把本格演员注册进「认证查人」这条缝，返回它的 username。"""
        user = _account(cell.identity, cell.cell_id, **cell.actor_over)
        self.accounts[user["username"]] = user
        self.username = str(user["username"])
        self.principal = _principal(cell.identity, cell.cell_id, **cell.actor_over)
        self.audit_actor = self.username
        return self.username

    def headers(self, username: str = "") -> dict[str, str]:
        from app.common.auth import create_token

        return {"Authorization": "Bearer " + create_token(username or self.username)}

    def client(self):
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app)

    def add_finalizer(self, action: Callable[[], None]) -> None:
        self._finalizers.append(action)

    def run_finalizers(self) -> None:
        while self._finalizers:
            self._finalizers.pop()()

    # ---- 判据③用的审计汇聚袋 ----
    def audit_rows(self) -> list[dict[str, str]]:
        actor = self.audit_actor or self.username
        return [row for row in self.sink if row["username"] == actor]


#: 直接 from app.common.audit import record_audit 的模块（逐个换绑，漏一个就数不到那一腿）。
_AUDIT_BINDINGS = (
    "app.common.audit.record_audit",
    "app.common.authorization.record_audit",
    "app.common.open_platform.record_audit",
    "app.rag.filters.record_audit",
    "app.api.v1.artifacts.record_audit",
    "app.api.v1.chat.record_audit",
    "app.api.v1.data.record_audit",
    "app.api.v1.feedback.record_audit",
    "app.api.v1.intelligence.record_audit",
    "app.api.v1.open_platform.record_audit",
)


def _install_audit_sink(monkeypatch: pytest.MonkeyPatch, sink: list[dict[str, str]]) -> None:
    """把 record_audit 包一层：原实现照调（落点已被 conftest 钉到临时目录），顺手记账。"""
    import app.common.audit as audit_module

    original = audit_module.record_audit

    def _sink_record(principal, action, outcome, resource="", reason="", **kwargs):
        sink.append(
            {
                "username": str(getattr(principal, "username", "") or "anonymous"),
                "role": str(getattr(principal, "role", "") or "unknown"),
                "action": str(action),
                "outcome": str(outcome),
                "resource": str(resource),
                "reason": str(reason),
            }
        )
        return original(principal, action, outcome, resource, reason, **kwargs)

    _sink_record._r159_sink = True  # type: ignore[attr-defined]
    for target in _AUDIT_BINDINGS:
        monkeypatch.setattr(target, _sink_record)


@pytest.fixture()
def ctx(monkeypatch, tmp_path):
    from app.common import auth

    site = Ctx(monkeypatch, tmp_path)
    _install_audit_sink(monkeypatch, site.sink)
    monkeypatch.setattr(auth, "get_user", lambda username: site.accounts.get(username))
    yield site
    site.run_finalizers()


# ==================== HTTP 摊平助手 ====================


def _wire_of(response) -> str:
    """把一次 HTTP 往返摊成一行文本，供判据①在里面搜内容令牌。"""
    try:
        body = json.dumps(response.json(), ensure_ascii=False, default=str)
    except Exception:
        body = response.text
    return str(response.status_code) + " " + body


def _reason_of(response) -> str:
    """稳定码可能在 detail 里，也可能裹在错误信封的 code / details.reason_code 里。"""
    try:
        detail = response.json().get("detail")
    except Exception:
        return ""
    if isinstance(detail, dict):
        code = str(detail.get("code") or "")
        nested = str((detail.get("details") or {}).get("reason_code") or "")
        return nested or code
    return str(detail or "")


# ==================== 资源面驱动：每个 driver 管一条腿 ====================


def _blind_recall_pipeline(monkeypatch, chunks: list[dict[str, Any]]):
    """假检索管线：语义腿**故意无视下推的 where**，全量召回，逼本地 scope.allows 独自挡住。

    这一针是给阶段 C 的判据①准备的：真 Chroma 会执行 where，所以「越权 0 条」在日常
    读数里几乎自动成立；只有当下推失效（R158 正在查的 ANN 返 0 条、store 实现换掉、
    metadata 缺失）时，本地复核才是唯一防线。本件把那条失效态直接摆出来。
    """
    from app.rag.retrieval_pipeline import RetrievalPipeline

    class BlindSemantic:
        def __init__(self) -> None:
            self.where = None

        def search(self, query, k, where):
            self.where = where
            return [dict(chunk) for chunk in chunks]

    class PredicateBm25:
        def __init__(self) -> None:
            self.pred = None

        def search(self, query, k, pred):
            self.pred = pred
            if pred is None:
                return [dict(chunk) for chunk in chunks]
            return [dict(chunk) for chunk in chunks if pred(dict(chunk))]

    class NoRewrite:
        @staticmethod
        def rewrite(question):
            return {"rewrites": [], "sub_questions": []}

    class NoRerank:
        @staticmethod
        def rerank(query, docs, top_k):
            return list(docs)[:top_k]

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = BlindSemantic()
    pipeline.bm25 = PredicateBm25()
    pipeline.rewriter = NoRewrite()
    pipeline.reranker = NoRerank()
    monkeypatch.setenv("RETRIEVAL_TIER", "none")
    return pipeline


def _drive_retrieval(ctx: Ctx, cell: Cell) -> Receipt:
    """检索腿：召回进来之后，还有没有一条越权 chunk 能活着进结果。"""
    from app.rag.filters import RetrievalScopeError

    pipeline = _blind_recall_pipeline(ctx.monkeypatch, _corpus(cell.corpus))
    try:
        docs, _rewrites = pipeline.search_for_principal(QUERY, ctx.principal, top_k=len(cell.corpus) + 8)
    except RetrievalScopeError as exc:
        return Receipt(status=403, reason=exc.code, claim=exc.code, notes="检索前就被拒")
    payload = "\n".join(
        str(doc.get("content")) + "|" + str(doc.get("source")) for doc in docs
    )
    return Receipt(payload=payload, status=200, notes="召回 " + str(len(docs)) + " 条")


def _drive_legacy_chat(ctx: Ctx, cell: Cell) -> Receipt:
    """旧版 POST /api/v1/chat：检索为空时它对外怎么说？（R62 诚实性面的旧腿）"""
    from app.api.v1 import chat

    chunks = _corpus(cell.corpus)

    class BlindRetriever:
        def __init__(self) -> None:
            self.wheres: list[Any] = []

        def search(self, query, k=5, where=None):
            self.wheres.append(where)
            return [dict(chunk) for chunk in chunks]

    class RecordingModel:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def chat(self, messages=None, source=None, stream=True):
            self.prompts.append(messages[0]["content"])
            delta = SimpleNamespace(content="R159-ANSWERED")
            return [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])]

    retriever = BlindRetriever()
    model = RecordingModel()
    ctx.monkeypatch.setattr(chat, "retriever", retriever)
    ctx.monkeypatch.setattr(chat, "model_handler", model)

    response = ctx.client().post("/api/v1/chat", json={"message": QUERY}, headers=ctx.headers())
    prompt = model.prompts[0] if model.prompts else ""
    return Receipt(
        payload=prompt + "\n" + response.text,
        status=response.status_code,
        reason=_reason_of(response),
        claim=prompt,
    )


def _drive_answer_cache(ctx: Ctx, cell: Cell) -> Receipt:
    """答案缓存腿（单元层）：作用域不同的人问同一句话，能不能读回别人那一条。"""
    from app.common import cache

    marker = "R159T-CACHED-ANSWER-BY-KEEPER"
    ctx.monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    writer = _cache_writer(ctx, cell)
    cache.cache_answer(QUERY, marker, scope=cache.answer_cache_scope(writer))
    hit = cache.get_cached_answer(QUERY, scope=cache.answer_cache_scope(ctx.principal))
    return Receipt(payload=str(hit or ""), status=200, claim="")


KEEPER_ANSWER = "R159T-CACHED-ANSWER-BY-KEEPER"
FRESH_ANSWER = "R159T-FRESH-ANSWER-READER-GENERATED"

#: 正向对照格必须「同一个人写、同一个人读」。答案缓存的键里带了身份
#: （app/common/cache.py:161 取 user_id/username 作 user_part），换一个 username 就必然
#: miss —— 那不是越权，那是自己没把缓存喂进去。三格跨作用域的红仍然要换一个账号来写。
SELF_SCOPE_WRITER_CELLS: set[str] = {
    "answer_cache.keeper_reads_own_answer",
    "answer_cache_wire.keeper_hits_own_answer",
}


def _cache_writer(ctx: Ctx, cell: Cell):
    """这一格的缓存写入者：正向对照＝本格演员本人，越权格子＝另一个账号（keeper）。"""
    if cell.cell_id in SELF_SCOPE_WRITER_CELLS:
        return ctx.principal
    return _principal("keeper", cell.cell_id + "-writer")


def _ask_harness(ctx: Ctx, answers: list[str]):
    """把 /ask 挂到一个假 orchestrator 上：answers 每被取走一次就等于打了一次模型。

    桩表照抄 tests/test_answer_cache_scope.py 的 _ask_harness，一处不改，免得两条线
    对同一条接线各自理解。
    """
    from app.api.v1 import chat
    from app.common import cache
    from app.storage.sessions import SessionRegistry

    ctx.monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    remaining = list(answers)

    def fake_stream(*_args, **_kwargs):
        answer = remaining.pop(0)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    ctx.monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    ctx.monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    ctx.monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    ctx.monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    ctx.monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    ctx.monkeypatch.setattr(
        chat,
        "auth",
        type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}),
    )
    ctx.monkeypatch.setattr(
        "app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9)
    )
    ctx.monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    ctx.monkeypatch.setattr(chat, "session_registry", SessionRegistry(ctx.tmp_path / "sessions.json"))

    def ask(principal, message=QUERY, session_id=""):
        import asyncio

        http_request = type(
            "Request",
            (),
            {
                "state": type(
                    "State", (), {"principal": principal, "username": principal.username}
                )()
            },
        )()
        response = asyncio.run(
            chat.ask(chat.AskRequest(message=message, session_id=session_id), http_request=http_request)
        )

        async def consume():
            chunks = [chunk async for chunk in response.body_iterator]
            return "".join(
                chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
            )

        return asyncio.run(consume())

    return ask, remaining


def _drive_answer_cache_wire(ctx: Ctx, cell: Cell) -> Receipt:
    """/ask 接线腿：缓存作用域这条线是不是真的接在生产路径上，而不是只活在单元测试里。"""
    ask, remaining = _ask_harness(ctx, [KEEPER_ANSWER, FRESH_ANSWER])
    keeper = _cache_writer(ctx, cell)
    first = ask(keeper)
    used_before = len(remaining)
    body = ask(ctx.principal)
    regenerated = len(remaining) < used_before
    return Receipt(
        payload=body,
        status=200,
        notes="R159-REGENERATED" if regenerated else "R159-FROM-CACHE",
    )


def _stored_documents(ctx: Ctx, cell: Cell) -> list[dict[str, Any]]:
    """把语料块落成磁盘文件，并造出两份元数据视图（目录用 / 版本用）。"""
    from app.api.v1 import chat

    rows: list[dict[str, Any]] = []
    for name in cell.corpus:
        chunk = dict(CHUNKS[name])
        path = ctx.tmp_path / str(chunk["source"])
        path.write_text(str(chunk["content"]), encoding="utf-8")
        row = {
            "filename": chunk["source"],
            "storage_path": str(path),
            "department": chunk["department"],
            "owner_id": chunk.get("owner_id") or RESOURCE_OWNER,
            "version": 1,
        }
        if "classification" in chunk:
            row["classification"] = chunk["classification"]
        rows.append(row)

    ctx.monkeypatch.setattr(chat, "current_documents", lambda *a, **k: [dict(r) for r in rows])
    ctx.monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *a, **k: [dict(r) for r in rows if r["filename"] == name],
    )
    return rows


def _drive_document(ctx: Ctx, cell: Cell) -> Receipt:
    """文档腿：目录、预览、下载三条口子一起验，最后一次的码作为本格口径。"""
    rows = _stored_documents(ctx, cell)
    client = ctx.client()
    headers = ctx.headers()
    parts = [_wire_of(client.get("/api/v1/documents/catalog", headers=headers))]
    last = None
    for row in rows:
        name = row["filename"]
        last = client.get("/api/v1/documents/" + name + "/preview", headers=headers)
        parts.append(_wire_of(last))
        parts.append(_wire_of(client.get("/api/v1/documents/" + name + "/file", headers=headers)))
    status = last.status_code if last is not None else None
    return Receipt(
        payload="\n".join(parts),
        status=status,
        reason=_reason_of(last) if last is not None else "",
        claim=parts[0],
    )


def _dataset_registry(ctx: Ctx, cell: Cell):
    """临时目录里造一套数据集台账，并把模块级单例换掉（照抄既存路由件的桩法）。"""
    from app.api.v1 import data
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=ctx.tmp_path, metadata_path=ctx.tmp_path / "ds-meta.json")
    ctx.monkeypatch.setattr(data, "DATA_DIR", str(ctx.tmp_path))
    ctx.monkeypatch.setattr(data, "dataset_registry", registry)
    ctx.monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    return registry


def _dataset_files(ctx: Ctx, cell: Cell, registry) -> list[str]:
    """每块语料落一张 CSV，登记时的 principal 部门 = 该块的部门（资源归属照实造）。"""
    names: list[str] = []
    for name in cell.corpus:
        chunk = dict(CHUNKS[name])
        stem = str(chunk["source"]).split(".")[0]
        owner_department = str(chunk["department"]) or DEPT_OWN
        path = ctx.tmp_path / (stem + ".csv")
        body = "department,name,revenue\n" + str(chunk["department"]) + "," + str(chunk["content"]) + ",7\n"
        if cell.cell_id in MIXED_ROW_CELLS:
            body += DEPT_FOREIGN + "," + FOREIGN_ROW_TOKEN + " 别部门的行,9\n"
            body += '""' + "," + BLANK_ROW_TOKEN + " 没有部门标注的行,8\n"
        path.write_text(body, encoding="utf-8")
        registry.register(
            path,
            principal=_principal("keeper", cell.cell_id + "-" + name, department=owner_department),
            # R163 修桩：密级维度必须落到数据集登记上。register 的默认值是 "internal"
            # （app/storage/datasets.py:119），而 policy 把它读成 2 档
            # （app/common/policy.py:20-26）> staff 的 1 档（app/common/rbac.py:31）——
            # 于是「密级 1 的那张表」也被密级挡住，正向对照永远绿不了，跨密级那一格只是
            # 恰好撞对了码。语料块里没有密级时传空串，让 policy 自己按
            # resource_scope_missing 走 fail-closed，不在测试里替它猜一个档位。
            classification="" if chunk.get("classification") is None else str(chunk["classification"]),
        )
        names.append(path.name)
    return names


#: 需要「一张表里混装别部门行」的格子（R17 的行级口径与文件级口径是两件事）。
MIXED_ROW_CELLS: set[str] = set()
#: 只验 preview 这一条结构化出口的格子：原始下载是整文件通道，行级口径管不到它，
#: 拿它当越权证据会把两种不同判据混成一谈，所以那一格明确不请它出场。
PREVIEW_ONLY_CELLS: set[str] = set()

FOREIGN_ROW_TOKEN = "R159T-ROW-FOREIGN"
BLANK_ROW_TOKEN = "R159T-ROW-BLANK"


def _drive_dataset(ctx: Ctx, cell: Cell) -> Receipt:
    """数据集腿：目录过滤 + 预览/下载的码与审计。"""
    registry = _dataset_registry(ctx, cell)
    names = _dataset_files(ctx, cell, registry)
    client = ctx.client()
    headers = ctx.headers()
    parts = [_wire_of(client.get("/api/v1/data-files", headers=headers))]
    last = None
    for filename in names:
        last = client.get("/api/v1/data-files/" + filename + "/preview", headers=headers)
        parts.append(_wire_of(last))
        if cell.cell_id not in PREVIEW_ONLY_CELLS:
            parts.append(
                _wire_of(client.get("/api/v1/data-files/" + filename + "/file", headers=headers))
            )
    return Receipt(
        payload="\n".join(parts),
        status=last.status_code if last is not None else None,
        reason=_reason_of(last) if last is not None else "",
        claim=parts[0],
    )


def _fake_request(principal):
    state = type("State", (), {"principal": principal, "username": getattr(principal, "username", "")})()
    return type("Request", (), {"state": state})()


def _drive_session(ctx: Ctx, cell: Cell) -> Receipt:
    """会话腿：别人的会话像不存在一样（404），但「有人来探过」这一笔有没有留下痕迹？"""
    from app.api.v1 import chat
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(ctx.tmp_path / "session-meta.json")
    keeper = _principal("keeper", cell.cell_id + "-owner")
    registry.bind("r159-session-foreign", keeper)
    registry.bind("r159-session-mine-" + ctx.username, ctx.principal)
    ctx.monkeypatch.setattr(chat, "session_registry", registry)
    ctx.monkeypatch.setattr(
        chat,
        "_list_sessions",
        lambda: [{"id": "r159-session-foreign"}, {"id": "r159-session-mine-" + ctx.username}],
    )
    ctx.monkeypatch.setattr(chat, "_get_session_messages", lambda *_a, **_k: [])

    client = ctx.client()
    headers = ctx.headers()
    listing = client.get("/api/v1/sessions", headers=headers)
    probe = client.get("/api/v1/sessions/r159-session-foreign", headers=headers)
    return Receipt(
        payload=_wire_of(listing) + "\n" + _wire_of(probe),
        status=probe.status_code,
        reason=_reason_of(probe),
        claim=_wire_of(probe),
    )


#: 走「写规则」那条口子的格子（POST /alerts/rules），其余按「读台账」处理。
#: 走「写规则」那条口子的格子（POST /alerts/rules），其余按「读台账」处理。
#: R163 补上 manager 那一格：产品只有 POST /alerts/rules 会交回 {"id","status":"ok"}
#: （app/api/v1/alerts.py:342-368），GET /alerts 与 GET /alerts/rules 两条都不会——
#: 这条正向对照没走写口子时，它钉的那两枚令牌永远不可能出现。
WRITE_ALERT_CELLS: set[str] = set()

#: 告警台账的行级归属（R176 起）：写侧由 alert_owner_department 给每一行落 department 章，
#: 读侧 alert_row_visible 的口径是「administrator 全见 / 其余本部门 + 无归属可见」。⇒ 种子行必须自带
#: 归属，否则一枚无归属行对任一部门的 manager 天然可见，这一格就红在种子上（R193 修）。
FOREIGN_ALERT_MESSAGE = "R159T-ALERT-OWN 部门 r159-own 的营收跌破阈值"


def _drive_alert(ctx: Ctx, cell: Cell) -> Receipt:
    """告警腿：能力性拒绝 + 台账读取。"""
    from app.api.v1 import alerts

    ctx.monkeypatch.setattr(alerts, "_database_available", lambda: False)
    ctx.monkeypatch.setattr(alerts, "_MEM_ALERTS", [])
    ctx.monkeypatch.setattr(alerts, "_MEM_RULES", [])
    alerts._MEM_ALERTS.append(
        {
            "id": 1,
            "rule_id": 1,
            "message": FOREIGN_ALERT_MESSAGE,
            "department": DEPT_OWN,
            "read": False,
        }
    )
    alerts._MEM_RULES.append(
        {"id": 1, "name": "r159-rule", "metric": "revenue", "op": "lt", "threshold": 1.0, "enabled": True}
    )

    client = ctx.client()
    headers = ctx.headers()
    parts = []
    if cell.cell_id in WRITE_ALERT_CELLS:
        response = client.post(
            "/api/v1/alerts/rules",
            headers=headers,
            json={"name": "r159-new-rule", "metric": "cost", "op": "lt", "threshold": 2.0},
        )
    else:
        response = client.get("/api/v1/alerts", headers=headers)
    parts.append(_wire_of(response))
    rules = client.get("/api/v1/alerts/rules", headers=headers)
    parts.append(_wire_of(rules))
    return Receipt(
        payload="\n".join(parts),
        status=response.status_code,
        reason=_reason_of(response),
        claim=_wire_of(response),
    )


def _drive_intelligence(ctx: Ctx, cell: Cell) -> Receipt:
    """情报腿：知识图谱三元组按归属者隔离，能力性拒绝另有一格。"""
    import asyncio

    from app.api.v1 import intelligence as intel
    from app.knowledge_graph.service import KnowledgeGraph

    previous = getattr(intel, "_graph", None)
    ctx.add_finalizer(lambda: setattr(intel, "_graph", previous))
    ctx.monkeypatch.setattr(intel, "_graph", KnowledgeGraph())

    author = ctx.principal if cell.identity == "keeper" else _principal("keeper", cell.cell_id + "-author")
    created = asyncio.run(
        intel.add_relation(
            intel.RelationRequest(
                source_entity="R159-ENT-" + cell.cell_id,
                relation="规定",
                target="R159-TARGET-" + cell.cell_id,
                source="R159-SRC-INTEL-" + cell.cell_id + " 第 1 页",
            ),
            _fake_request(author),
        )
    )
    # 写入这一笔必须真的成功，否则「别人看不见」是空转出来的绿。
    assert created.get("relation_id"), "假图谱没把三元组写进去，本格的负向断言没有意义"
    listing = asyncio.run(intel.list_relations(None, None, _fake_request(ctx.principal)))
    payload = json.dumps({"listing": listing}, ensure_ascii=False, default=str)

    # 再打一枪能力闸门：dashboard 要 analyze，没有这个能力的人必须被顶回来并留下审计。
    from fastapi import HTTPException

    rows = [{"department": DEPT_OWN, "metric": "R159-METRIC", "value": 1}]
    status, reason = 200, ""
    try:
        probe = asyncio.run(intel.dashboard(intel.DashboardRequest(rows=rows, insights=[]), _fake_request(ctx.principal)))
        payload += "\n" + json.dumps(probe, ensure_ascii=False, default=str)
    except HTTPException as exc:
        status, reason = exc.status_code, _reason_of(SimpleNamespace(json=lambda: {"detail": exc.detail}))
        payload += "\n" + str(exc.detail)
    return Receipt(payload=payload, status=status, reason=reason, claim=payload)


#: 工具腿的每条格子要额外挑一份「本轮选中的数据文件」，写在表尾的 TOOL_CONFIG 里。
TOOL_CONFIG: dict[str, dict[str, Any]] = {}


def _drive_row_scope_tools(ctx: Ctx, cell: Cell) -> Receipt:
    """行级 scope 腿（tools）：数据集目录过滤 + 表内行过滤，两条口子一起验。"""
    from app.agents.tools import analyze_data

    registry = _dataset_registry(ctx, cell)
    _dataset_files(ctx, cell, registry)
    ctx.monkeypatch.setattr("app.agents.tools._llm_pandas_code", lambda df, query: "df['revenue'].max()")
    conf: dict[str, Any] = {
        "id": str(ctx.principal.user_id),
        "username": str(ctx.principal.username),
        "role": str(ctx.principal.role),
        "department": str(ctx.principal.department or ""),
    }
    conf.update(TOOL_CONFIG.get(cell.cell_id, {}))
    output = analyze_data.invoke("营收最高是多少", config={"configurable": conf})
    return Receipt(payload=str(output), status=200, reason="", claim=str(output))


def _drive_artifact(ctx: Ctx, cell: Cell) -> Receipt:
    """产物腿：图表/报告这类导出物的列表、取内容、下载。"""
    from app.storage import artifacts as artifact_storage
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(root=ctx.tmp_path, metadata_path=ctx.tmp_path / "art-meta.json")
    ctx.monkeypatch.setattr(artifact_storage, "artifact_registry", registry)
    owner = _principal("keeper", cell.cell_id + "-owner")
    path = ctx.tmp_path / "R159-SRC-ARTIFACT.png"
    path.write_bytes(b"R159T-ARTIFACT-BYTES")
    record = registry.register(path, artifact_type="chart", principal=owner)

    client = ctx.client()
    headers = ctx.headers()
    parts = [
        _wire_of(client.get("/api/v1/artifacts", headers=headers)),
        _wire_of(client.get("/api/v1/artifacts/" + record.artifact_id + "/content", headers=headers)),
        _wire_of(client.get("/api/v1/artifacts/" + record.artifact_id + "/download", headers=headers)),
    ]
    content = client.get("/api/v1/artifacts/" + record.artifact_id + "/content", headers=headers)
    parts.append(_wire_of(content))
    return Receipt(
        payload="\n".join(parts),
        status=content.status_code,
        reason=_reason_of(content),
        claim=parts[0],
    )


def _drive_static_chart(ctx: Ctx, cell: Cell) -> Receipt:
    """产物腿的另一半：静态目录不许成为绕过产物授权的旁路。"""
    import asyncio

    from app.main import StaticFilesWithoutGeneratedArtifacts

    static = StaticFilesWithoutGeneratedArtifacts(directory="static")
    codes = []
    for name in ("charts/R159-KNOWN-CHART.png", "exports/R159-KNOWN-REPORT.pdf"):
        codes.append(str(asyncio.run(static.get_response(name, {})).status_code))
    return Receipt(payload=" ".join(codes), status=200, claim=" ".join(codes))


#: 开放平台腿的格子参数：授了哪些部门、头里自称了哪个部门。
OPEN_CASES: dict[str, dict[str, Any]] = {}


def _drive_open_platform(ctx: Ctx, cell: Cell) -> Receipt:
    """开放平台自报部门头（R67 / R71 面）：签名证明的是应用，不是它替哪个人说话。"""
    from app.common.open_platform import (
        build_request_signature,
        clear_app_registry,
        register_application,
        verify_open_request,
    )
    from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope
    from fastapi import HTTPException

    import app.common.open_platform as open_platform

    previous = dict(open_platform._APP_REGISTRY)
    ctx.add_finalizer(
        lambda: (open_platform._APP_REGISTRY.clear(), open_platform._APP_REGISTRY.update(previous))
    )
    spec = OPEN_CASES[cell.cell_id]
    clear_app_registry()
    app_info = register_application(
        "r159-app-" + cell.cell_id,
        allowed_actions=["approval"],
        allowed_departments=list(spec["granted"]),
    )
    body = json.dumps({"amount": 1, "department": spec.get("body_department", DEPT_FOREIGN)})
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(
            app_info["app_id"], app_info["secret"], body, timestamp
        ),
        "X-Open-Action": "approval",
        "X-Open-User": "r159-victim-user",
    }
    if spec.get("claimed"):
        headers["X-Open-Department"] = str(spec["claimed"])

    try:
        principal, record = verify_open_request(headers, body, "approval")
    except HTTPException as exc:
        detail = exc.detail
        code = str(detail.get("code")) if isinstance(detail, dict) else str(detail)
        ctx.audit_actor = "open-app:" + str(app_info["app_id"])
        return Receipt(payload="", status=exc.status_code, reason=code, claim=str(detail))

    try:
        resolve_document_retrieval_scope(principal)
        scope_note = "R159-SCOPE-RESOLVED"
    except RetrievalScopeError as scope_error:
        scope_note = "R159-SCOPE-" + str(scope_error.code)
    ctx.audit_actor = str(record.get("actor"))
    payload = (
        "R159-OPEN-DEPT=[" + str(principal.department) + "] "
        "R159-OPEN-ACTOR=[" + str(record.get("actor")) + "] " + scope_note
    )
    return Receipt(payload=payload, status=200, reason="", claim=payload)


#: 审计台那两格里先埋一条别人的拒绝记录，.manager 一来就能验它看不看得到。
AUDIT_SEED = "R159SEED-AUDIT-ROW-OF-VICTIM"


def _drive_observability(ctx: Ctx, cell: Cell) -> Receipt:
    """可观测腿：审计事件出口本身也是资源，没有 audit:read 的人不该翻到别人的拒绝记录。"""
    from app.common.audit import record_audit

    record_audit(
        SimpleNamespace(username="r159-victim-account", role="staff", department=DEPT_FOREIGN),
        "resource:view",
        "denied",
        AUDIT_SEED,
        "department_scope_denied",
    )
    # R163 修桩：审计事件出口的实名是 /api/v1/audit/events——observability 路由挂在
    # prefix="/api/v1" 上（app/main.py:87），路由自己写的是 "/audit/events"
    # （app/api/v1/observability.py:1152），既没有 /observability 这一段，也就没有
    # 那一格所谓的「403 变 404」：404 是 FastAPI 在授权闸门之前自己回的。
    response = ctx.client().get("/api/v1/audit/events", headers=ctx.headers())
    return Receipt(
        payload=_wire_of(response),
        status=response.status_code,
        reason=_reason_of(response),
        claim=_wire_of(response),
    )


# ==================== 矩阵表 ====================

ALL_CORPUS: tuple[str, ...] = tuple(CHUNKS)

#: 既存 20+ 枚权限件各自盖了哪一格，写在 covered_by 里；空格＝本件新补的口子。
CELLS: list[Cell] = []

CELLS += [
    # ---------- 检索腿 ----------
    Cell(
        cell_id="retrieval.xdept_sees_only_own_scope",
        surface="retrieval",
        identity="xdept",
        drive=_drive_retrieval,
        corpus=ALL_CORPUS,
        forbidden=_tokens(("own_l1", "own_l2", "own_l3", "fx_l3", "nodept_l1", "noclass")),
        entitled=_tokens(("fx_l1",)),
        audit_expect=("none", "跨部门 chunk 被本地 scope.allows 裁掉，不是一次拒绝事件；平台只在作用域放宽（administrator_scope）时落审计（app/rag/filters.py::record_retrieval_scope）。"),
        covered_by="tests/test_retrieval_permissions.py / tests/test_rag_administrator_scope.py",
        note="语义召回桩故意无视下推的 where，逼本地复核独自挡：这是 R158 那条腿失效时的最坏形态。",
    ),
    Cell(
        cell_id="retrieval.xclear_sees_only_own_level",
        surface="retrieval",
        identity="xclear",
        drive=_drive_retrieval,
        corpus=ALL_CORPUS,
        forbidden=_tokens(("own_l2", "own_l3", "fx_l1", "fx_l3", "nodept_l1", "noclass")),
        entitled=_tokens(("own_l1",)),
        audit_expect=("none", "同上：按档位裁掉不是拒绝事件。"),
        covered_by="tests/test_classification_fail_closed.py（R57 缺密级 fail-closed）",
    ),
    Cell(
        cell_id="retrieval.nodept_account_is_refused",
        fixed_by="R178@a6c2710",
        surface="retrieval",
        identity="nodept",
        drive=_drive_retrieval,
        corpus=ALL_CORPUS,
        forbidden=_tokens(ALL_CORPUS),
        withheld=False,
        expect_status=403,
        expect_reason="authorization_unavailable",
        audit_expect=("denied", ""),
        covered_by="tests/test_rbac_single_scoping_source.py（只验码，没验审计）",
        note="判据③的红：无部门账号在检索前就被拒，码交得出去，但 resolve_document_retrieval_scope 在 raise 之前没有任何 record_audit。",
        finding="C",
        root_cause="product",
        evidence="app/rag/filters.py:102-106（departments 为空 → raise authorization_unavailable）；本文件唯一的 record_audit 在 app/rag/filters.py:129-139 的 record_retrieval_scope 里，且 app/rag/filters.py:127-128 一进门就把非 administrator_scope 挡掉——拒绝路径上没有一次审计写入。",
    ),
    Cell(
        cell_id="retrieval.admin_cross_department_is_audited",
        surface="retrieval",
        identity="admin",
        drive=_drive_retrieval,
        corpus=ALL_CORPUS,
        forbidden=_tokens(("noclass",)),
        entitled=_tokens(("own_l1", "own_l3", "fx_l1", "fx_l3", "nodept_l1")),
        withheld=False,
        audit_expect=("allowed", "administrator_scope"),
        covered_by="tests/test_rag_administrator_scope.py",
        note="管理员跨部门是设计内放行（e2 裁定），但必须留下自己的码，不能被写成普通部门匹配。",
    ),
    # ---------- legacy chat 腿 ----------
    Cell(
        cell_id="legacy_chat.xdept_prompt_has_no_foreign_content",
        surface="legacy_chat",
        identity="xdept",
        drive=_drive_legacy_chat,
        corpus=ALL_CORPUS,
        forbidden=_tokens(("own_l1", "own_l2", "own_l3", "fx_l3", "nodept_l1", "noclass")),
        entitled=_tokens(("fx_l1",)),
        audit_expect=("none", "同检索腿：裁掉 chunk 不是拒绝事件。"),
        covered_by="tests/test_legacy_chat_retrieval_scope.py",
    ),
    Cell(
        cell_id="legacy_chat.hidden_document_says_no_relevant_document",
        fixed_by="R179@f51576f",
        surface="legacy_chat",
        identity="xdept",
        drive=_drive_legacy_chat,
        corpus=("own_l1",),
        forbidden=_tokens(("own_l1",)),
        expect_status=200,
        audit_expect=("none", "请求本身被允许（作用域合法），只是这一轮没有可见文档，不构成一次拒绝。"),
        covered_by="缺口：tests/test_legacy_chat_retrieval_scope.py 的三枚只验「越权命中的文档不进 prompt」（:59）与「内部失败细节不上线」（:104），没有任何一枚站在旧版 /chat 这一轮对外说的那句人话上——R62 的诚实性口径在 legacy 这条腿是空白。",
        note="判据②的红：app/api/v1/chat.py 在检索为空时把上下文写成「暂无相关文档」，而这条腿此刻藏着的是别人部门的一份文档。R62 在数据腿修掉了同形问题，旧版 /chat 这条腿没跟上。",
        finding="B",
        root_cause="product",
        evidence="app/api/v1/chat.py:1313-1317：sources 被 scope.allows 裁空之后，:1317 原样写死「暂无相关文档」进 prompt；/chat 是纯文本流，没有 /ask 那条 sources 事件（app/api/v1/chat.py:324-329 的 scope_reason_code 只挂在 /ask 上），所以这句甩锅就是这一轮唯一的对外说法。",
    ),
    Cell(
        cell_id="legacy_chat.nodept_account_is_refused",
        fixed_by="R178@a6c2710",
        surface="legacy_chat",
        identity="nodept",
        drive=_drive_legacy_chat,
        corpus=ALL_CORPUS,
        forbidden=_tokens(ALL_CORPUS),
        withheld=False,
        expect_status=403,
        expect_reason="authorization_unavailable",
        audit_expect=("denied", ""),
        covered_by="tests/test_legacy_chat_retrieval_scope.py（只验码）",
        note="判据③的红：与 retrieval.nodept 同一根因（旧版 /chat 复用了那条不审计的拒绝路）。",
        finding="C",
        root_cause="product",
        evidence="app/api/v1/chat.py:1300-1305：except RetrievalScopeError 之后只 logger.warning 再 raise HTTPException，中间没有 record_audit；根因同 app/rag/filters.py:102-106。",
    ),
    Cell(
        cell_id="legacy_chat.admin_scoped_retrieval_is_audited",
        surface="legacy_chat",
        identity="admin",
        drive=_drive_legacy_chat,
        corpus=("fx_l3", "own_l1"),
        forbidden=_tokens(()),
        entitled=_tokens(("fx_l3", "own_l1")),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", "administrator_scope"),
        covered_by="tests/test_rag_administrator_scope.py",
    ),
    # ---------- 答案缓存命中腿 ----------
    Cell(
        cell_id="answer_cache.xdept_cannot_read_keepers_answer",
        surface="answer_cache",
        identity="xdept",
        drive=_drive_answer_cache,
        forbidden=(KEEPER_ANSWER,),
        audit_expect=("none", "缓存回读不是授权决策点，跨作用域表现为未命中；平台的授权审计在生成那一轮已经落过。"),
        covered_by="tests/test_answer_cache_scope.py 判据②七组参数化",
    ),
    Cell(
        cell_id="answer_cache.xclear_cannot_read_keepers_answer",
        surface="answer_cache",
        identity="xclear",
        drive=_drive_answer_cache,
        forbidden=(KEEPER_ANSWER,),
        audit_expect=("none", "同上。"),
        covered_by="tests/test_answer_cache_scope.py",
    ),
    Cell(
        cell_id="answer_cache.nodept_cannot_read_keepers_answer",
        surface="answer_cache",
        identity="nodept",
        drive=_drive_answer_cache,
        forbidden=(KEEPER_ANSWER,),
        audit_expect=("none", "同上。"),
        covered_by="tests/test_answer_cache_scope.py（换 owner / 换部门两组）",
    ),
    Cell(
        cell_id="answer_cache.keeper_reads_own_answer",
        surface="answer_cache",
        identity="keeper",
        drive=_drive_answer_cache,
        entitled=(KEEPER_ANSWER,),
        forbidden=(),
        audit_expect=("none", "本人读自己的缓存，不需要审计。"),
        covered_by="既存：tests/test_answer_cache_scope.py::test_repeat_question_inside_a_session_hits_cache_and_is_labelled（:259）已经钉过本人命中；本件把它当反向对照，用来证明上面三格的「0 命中」不是空转。",
        note="正向对照：证明上面三格的「0 命中」不是靠谁都查不到刷出来的假绿。",
        root_cause="matrix",
        evidence=(
            "R159 的桩把写入者写成 _principal(「keeper」, cell_id + \"-writer\")，与本格演员 r159-keeper-<cell_id> "
            "是两个 username；缓存键的 user_part 直接取 user_id/username（app/common/cache.py:161-162），"
            "换 username 必然 miss，与越权无关。R163 改由本人写本人读（SELF_SCOPE_WRITER_CELLS）。"
        ),
    ),
    Cell(
        cell_id="answer_cache_wire.xdept_regenerates_instead_of_hitting",
        surface="answer_cache_wire",
        identity="xdept",
        drive=_drive_answer_cache_wire,
        forbidden=(KEEPER_ANSWER,),
        entitled=("R159-REGENERATED",),
        audit_expect=("none", "同缓存腿：这一层的判据是「不许回读别人的答案」，命中与否不落审计。"),
        covered_by="tests/test_answer_cache_scope.py 判据②接线取证",
        note="entitled 钉的是「模型真的又被打了一次」，否则跨作用域未命中可能只是根本没走缓存。",
    ),
    Cell(
        cell_id="answer_cache_wire.keeper_hits_own_answer",
        surface="answer_cache_wire",
        identity="keeper",
        drive=_drive_answer_cache_wire,
        entitled=(KEEPER_ANSWER, "R159-FROM-CACHE"),
        forbidden=(),
        audit_expect=("none", "本人命中自己的缓存。"),
        covered_by="tests/test_answer_cache_scope.py 判据①",
        note="正向对照：缓存真的在通，上一条格子的未命中才有意义。",
        root_cause="matrix",
        evidence="同一根因：/ask 命中与否只看 answer_cache_scope 相等（app/api/v1/chat.py:1635-1637 取 answer_cache_scope(request_principal, username)），而 R159 的两发 ask 用了两个 username（app/common/cache.py:161-162）⇒ 第二次必然重新生成。改成本人连发两发之后这一格转绿，顺带证明答案缓存在生产接线上确实活着。",
    ),
]


MIXED_ROW_CELLS.add("dataset_route.preview_must_not_leak_foreign_rows")
PREVIEW_ONLY_CELLS.add("dataset_route.preview_must_not_leak_foreign_rows")

CELLS += [
    # ---------- 文档路由 ----------
    Cell(
        cell_id="document_route.xdept_cannot_list_or_open_own_dept_files",
        surface="document_route",
        identity="xdept",
        drive=_drive_document,
        corpus=("own_l1", "own_l2", "fx_l1"),
        forbidden=_tokens(("own_l1", "own_l2")),
        entitled=_tokens(("fx_l1",)),
        expect_status=200,
        audit_expect=("denied", ""),
        covered_by="tests/test_document_route_authorization.py",
    ),
    Cell(
        cell_id="document_route.xclear_cannot_open_higher_classification",
        surface="document_route",
        identity="xclear",
        drive=_drive_document,
        corpus=("own_l1", "own_l2"),
        forbidden=_tokens(("own_l2",)),
        entitled=_tokens(("own_l1",)),
        expect_status=403,
        expect_reason="clearance_insufficient",
        audit_expect=("denied", ""),
        covered_by="tests/test_classification_fail_closed.py",
    ),
    Cell(
        cell_id="document_route.document_without_classification_is_refused",
        surface="document_route",
        identity="keeper",
        drive=_drive_document,
        corpus=("noclass",),
        forbidden=_tokens(("noclass",)),
        expect_status=403,
        expect_reason="resource_scope_missing",
        audit_expect=("denied", ""),
        covered_by="tests/test_classification_fail_closed.py（R57）",
        note="缺密级不是「公开」：这条拒绝必须是能力性拒绝，不能答成 200 空目录。",
    ),
    Cell(
        cell_id="document_route.owner_reads_own_foreign_secret",
        surface="document_route",
        identity="keeper",
        drive=_drive_document,
        corpus=("fx_l3",),
        entitled=_tokens(("fx_l3",)),
        forbidden=(),
        withheld=False,
        actor_over={"id": RESOURCE_OWNER},
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_document_route_authorization.py（owner 轴）",
        note="设计内放行：owner 对自己的东西有 view/download/delete（policy.py 的 _OWNER_CONTROLLED_ACTIONS）。放行的同时不许把别人的部门也带进来，所以下一格是反面对照。",
    ),
    Cell(
        cell_id="document_route.peer_in_same_dept_cannot_read_anothers_secret",
        surface="document_route",
        identity="peer",
        drive=_drive_document,
        corpus=("fx_l3",),
        forbidden=_tokens(("fx_l3",)),
        expect_status=403,
        expect_reason="clearance_insufficient",
        audit_expect=("denied", ""),
        covered_by="缺口：tests/test_document_route_authorization.py::test_owner_may_open_their_own_document_outside_the_resource_department（:128）只验「主人能开自己的」，没有一格反向验「同部门同角色、但不是主人」这一面。",
        note="归属轴：同一个部门、同一个角色，只因为不是主人就拿不到；上一格的绿不是这格的绿。",
    ),
    Cell(
        cell_id="document_route.nodept_catalog_answers_empty_list",
        fixed_by="R179@f51576f",
        surface="document_route",
        identity="nodept",
        drive=_drive_document,
        corpus=("own_l1", "own_l2"),
        forbidden=_tokens(("own_l1", "own_l2")),
        told_no_scope=True,
        audit_expect=("denied", ""),
        covered_by="缺口：既存 tests/test_document_route_authorization.py::test_legacy_unowned_document_is_hidden_from_staff（:263）只验过 staff 看不到 legacy 无主文档，没验过「账号本身没有作用域」时目录怎么答复。",
        note="判据②的红（口径来自平台自身的不一致，不是本件新立的规矩）：同一个无部门账号打 /chat 得 403 authorization_unavailable、打 /upload-excel 得 403 department_scope_required，打 /documents/catalog 却得 200 空列表。诚实性的尺子在 R62（跟进单 §23 第 a 条，判据原文「被权限隐藏的行不能被说成『没有数据』」）；订正 R159 的一处引证——看板 G4 09-16 已重定义（§4F.5 裁 R1 走 (c)：后端零改动、403 保持，判据改到前端渲染口径），它不管这条目录口子。",
        finding="B",
        root_cause="product",
        evidence=(
            "app/api/v1/chat.py:3172-3174 catalog 直接 return _visible_document_rows(...)，"
            "app/api/v1/chat.py:602-616 那份过滤器只做 allowed/not-allowed 二分、不把 reason_code 带出来 ⇒ "
            "出口是 200 + 空数组。同账号在 app/api/v1/chat.py:1300-1305 得 403，"
            "在 app/api/v1/data.py:322-329 + :43 得 403 department_scope_required——三条口子三种说法。"
        ),
    ),
    # ---------- 数据集路由 ----------
    Cell(
        cell_id="dataset_route.xdept_cannot_read_or_download",
        surface="dataset_route",
        identity="xdept",
        drive=_drive_dataset,
        corpus=("own_l1",),
        forbidden=_tokens(("own_l1",)),
        expect_status=403,
        expect_reason="department_scope_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_dataset_route_authorization.py",
    ),
    Cell(
        cell_id="dataset_route.owner_lists_and_previews",
        surface="dataset_route",
        identity="keeper",
        drive=_drive_dataset,
        corpus=("own_l1",),
        entitled=_tokens(("own_l1",)),
        forbidden=(),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_dataset_route_authorization.py",
    ),
    Cell(
        cell_id="dataset_route.xclear_cannot_preview_higher_classification",
        surface="dataset_route",
        identity="xclear",
        drive=_drive_dataset,
        corpus=("own_l1", "own_l2"),
        forbidden=_tokens(("own_l2",)),
        entitled=_tokens(("own_l1",)),
        expect_status=403,
        expect_reason="clearance_insufficient",
        audit_expect=("denied", ""),
        covered_by="缺口：tests/test_dataset_route_authorization.py 五枚全部走部门/注册表那一轴（:34 :79 :125 :145），密级维度从来没被带进数据集路由。",
        root_cause="matrix",
        evidence=(
            "R159 的桩只在 CSV 里写了 department 列，没把语料块的密级交给登记入口，"
            "于是每张表都吃 register 的默认值 classification=\"internal\""
            "（app/storage/datasets.py:113-121），policy 把它读成 2 档"
            "（app/common/policy.py:20-26），staff 只有 1 档（app/common/rbac.py:31）"
            "⇒ 密级 1 那张本该看得见的表也被密级挡住，正向对照永远绿不了。R163 把密级按语料块传进 "
            "register 之后这一格转绿；产品侧的密级判定本身没变（app/common/policy.py:186-189）。"
        ),
    ),
    Cell(
        cell_id="dataset_route.preview_must_not_leak_foreign_rows",
        fixed_by="R180@4f96cb6",
        surface="dataset_route",
        identity="keeper",
        drive=_drive_dataset,
        corpus=("own_l1",),
        forbidden=(FOREIGN_ROW_TOKEN, BLANK_ROW_TOKEN),
        entitled=_tokens(("own_l1",)),
        withheld=False,
        expect_status=200,
        audit_expect=("none", "本人读自己的数据集，文件级授权通过，不构成拒绝事件。"),
        covered_by="缺口：R17/R62 只在工具腿裁行（tests/test_rbac_department_fail_closed.py / tests/test_tools_row_scope_messaging.py），路由侧的结构化预览出口没人拿同一把尺子量过。",
        note="表格行判据（①）：预览是结构化 excerpt 通道，别部门的行与没标部门的行都不许从这里出来。原始下载 /file 是整文件通道，行级口径管不到它，本格明确不请它出场（PREVIEW_ONLY_CELLS）。",
        finding="A",
        root_cause="product",
        evidence=(
            "app/api/v1/data.py:203-218 preview 这一条只过文件级闸门 _authorized_dataset"
            "（app/api/v1/data.py:69-90），拿到帧之后交给 app/api/v1/data.py:104-117 的 "
            "build_dataframe_preview——它对 df 直接 head() 出 rows，一次行级过滤都没有。"
            "同一张帧在工具腿走的是 app/agents/tools.py:964 filter_dataframe_rows_with_scope"
            "（app/common/rbac.py:127-199，R17 甲案口径），所以「这张表里 department=r159-fx 的行"
            "对本账号不可见」是平台自己已经生效的判据，路由侧只是漏了用它。实测这一格 200 正文里"
            "同时出现 R159T-ROW-FOREIGN 与 R159T-ROW-BLANK。"
        ),
    ),
    Cell(
        cell_id="dataset_route.nodept_catalog_answers_empty_list",
        fixed_by="R180@4f96cb6",
        surface="dataset_route",
        identity="nodept",
        drive=_drive_dataset,
        corpus=("own_l1",),
        forbidden=_tokens(("own_l1",)),
        told_no_scope=True,
        audit_expect=("denied", ""),
        covered_by="缺口：同 document_route.nodept_catalog_answers_empty_list——tests/test_dataset_route_authorization.py 与 tests/test_document_route_authorization.py 都只验「部门对不上」，没验「压根没有部门」。",
        note="判据②的红，与文档目录同一根因：作用域都不存在了，还按「你运气好，这轮没有文件」的说法交出去。",
        finding="B",
        root_cause="product",
        evidence=(
            "app/api/v1/data.py:121-163：:133-144 对每条 record 现算 decision，:142-143 不允许就 "
            "`continue`，既不落审计也不带因由 ⇒ 出口 200 {\"files\": []}。"
            "同一条腿的 /upload-excel 走 app/api/v1/data.py:322-329 是 403。"
        ),
    ),
    # ---------- 会话路由 ----------
    Cell(
        cell_id="session_route.peer_probe_of_anothers_session",
        fixed_by="R179@f51576f",
        surface="session_route",
        identity="peer",
        drive=_drive_session,
        forbidden=("r159-session-foreign",),
        entitled=("r159-session-mine",),
        expect_status=404,
        expect_reason="resource_not_found",
        audit_expect=("denied", ""),
        covered_by="tests/test_session_route_authorization.py（只验 404 不漏内容）",
        note="判据③的红：别人的会话像不存在一样是对的（防资源枚举），但「有人拿 id 来探过」这一笔在审计日志里查不到任何痕迹。",
        finding="C",
        root_cause="product",
        evidence=(
            "app/api/v1/chat.py:583-587 _authorize_session_request：is_owned_by 不过就直接 "
            "raise HTTPException(404, resource_not_found)，中间没有 record_audit；"
            "GET /sessions/{id}（app/api/v1/chat.py:2588-2589）与 GET /sessions"
            "（:2576-2577）两条口子都只过这个函数。对照：同文件 :583 之外文档腿的 "
            "_authorize_document_request（app/api/v1/chat.py:619-627）是把判定写进审计台账的。"
        ),
    ),
    Cell(
        cell_id="session_route.admin_cannot_read_anothers_session",
        fixed_by="R179@f51576f",
        surface="session_route",
        identity="admin",
        drive=_drive_session,
        forbidden=("r159-session-foreign",),
        entitled=("r159-session-mine",),
        expect_status=404,
        expect_reason="resource_not_found",
        audit_expect=("denied", ""),
        covered_by="缺口：tests/test_session_route_authorization.py（:18 :37）与 tests/test_session_ownership_guards.py 全部以「非 owner」为敌，没有一格验管理员能不能凭 administrator 身份翻别人的会话。",
        note="会话是归属控制的资源，administrator_scope 在这里不该生效；这一格同时是判据③的第二笔（同根因）。",
        finding="C",
        root_cause="product",
        evidence=(
            "与上一格同一条 raise：app/api/v1/chat.py:583-587。管理员这一格另外证明了归属轴确实拦住了人"
            "（404 且不回正文），拦的谓词是 app/storage/sessions.py:85 is_owned_by，它不认角色。"
        ),
    ),
    Cell(
        cell_id="session_route.keeper_lists_only_own_session",
        surface="session_route",
        identity="keeper",
        drive=_drive_session,
        forbidden=("r159-session-foreign",),
        entitled=("r159-session-mine",),
        withheld=False,
        expect_status=404,
        audit_expect=("none", "列出自己的会话不是越权请求；对别人会话的探测由上一格负责记账。"),
        covered_by="既存：tests/test_session_route_authorization.py::test_session_routes_filter_by_registered_owner（:18）＋ tests/test_session_ownership_guards.py::test_cancel_still_works_for_the_owner（:64）。",
        note="正向对照：本人那一条必须真的出现在列表里。",
    ),
]


WRITE_ALERT_CELLS.add("alert_route.staff_rule_write_is_denied")
#: R163 补：这一格的名字就叫「manager 能写规则」，不 POST 一次它永远只能读台账，
#: 它钉的那两枚令牌（"status": "ok" / r159-new-rule）在产品侧只出自
#: app/api/v1/alerts.py:342-368 那一条 POST 出口。
WRITE_ALERT_CELLS.add("alert_route.manager_rule_write_is_allowed")

CELLS += [
    # ---------- 告警路由 ----------
    Cell(
        cell_id="alert_route.foreign_manager_reads_scoped_alert",
        fixed_by="R176@3431053",
        surface="alert_route",
        identity="xdept",
        drive=_drive_alert,
        forbidden=("R159T-ALERT-OWN",),
        entitled=("r159-rule",),
        audit_expect=("none", "这一格走的是「能力具备、内容可达」的路径，不构成拒绝事件；拒绝那几格另验。"),
        covered_by="缺口：既存两件（tests/test_alert_route_authorization.py / tests/test_alert_scan_scope.py）分别验「staff 被顶回来」与「巡检只扫有权限的文件」，没有任何一枚验过告警台账本身的读取范围。",
        note="判据①的红（R159 实测当时）：告警台账一条归属列都没有，资源级闸门（alerts:manage）过了就把全司告警正文交出去，任一部门的 manager 都能读到别部门的行。R176 `3431053` 起这一格改由两层把关：资源级 _require_alert_management 状态码一字未改，行级 alert_row_visible 让 administrator 之外只看本部门。本格今日复跑为绿；R163 期它还红着一层原因是本件自己的种子不带 department（见 _drive_alert 上方注释），那一处 R193 已补。",
        finding="A",
        root_cause="product",
        evidence=(
            "建表就没有归属列：app/api/v1/alerts.py:76-84（CREATE TABLE alerts 只有 id/rule_id/"
            "message/ai_analysis/read/created_at），写路径 app/api/v1/alerts.py:291 也只 INSERT "
            "(rule_id, message, ai_analysis)；读路径 :397-405 是一条 SELECT * FROM alerts "
            "ORDER BY id DESC LIMIT 100，唯一的门是 :398 复用 :96-107 的能力判定（alerts:manage），"
            "它不看部门也不看归属 ⇒ 任一部门的 manager 拿到全公司告警正文。"
            "设计件把这条记为 R1 裁定 (c) 的待裁残留（docs/handoff/2026-09-15-alert-and-hitl-design.md"
            ":47-67 与 :196：先只保持 403，(a)/(b) 必须等归属列 migration），本件如实钉红、不因已裁免检。"
        ),
    ),
    Cell(
        cell_id="alert_route.staff_read_denial_is_audited",
        fixed_by="R176@3431053",
        surface="alert_route",
        identity="xclear",
        drive=_drive_alert,
        forbidden=("R159T-ALERT-OWN",),
        withheld=False,
        expect_status=403,
        expect_reason="permission_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_alert_route_authorization.py（只验状态码）",
        note="判据③的红：app/api/v1/alerts.py 全文没有一处 record_audit，_require_alert_management 直接 raise 403，能力性拒绝在审计日志里查无此笔。状态码与稳定码本身是对的（看板 G4 已裁：不许以 200 空列表答复无权限）。",
        finding="C",
        root_cause="product",
        evidence=(
            "app/api/v1/alerts.py:96-107：principal 为空 raise 401、decision 不 allowed 就 raise 403，"
            "两条出口都没有 record_audit；全文件 record_audit 命中 0 处，而这条门被 :341/:370/:381/"
            ":395/:406 五个调用点复用 ⇒ 告警面所有能力性拒绝在审计日志里查无此笔。"
            "订正 R159 的一处引证：看板 G4（§4F.5 裁 R1 走 (c)）说的是「后端 403 保持、前端把无权限与"
            "空列表分开渲染」，它没裁「能力性拒绝必须落审计」；审计这一列的尺子是 R159 判据③本身。"
        ),
    ),
    Cell(
        cell_id="alert_route.staff_rule_write_is_denied",
        fixed_by="R176@3431053",
        surface="alert_route",
        identity="xclear",
        drive=_drive_alert,
        forbidden=("r159-new-rule",),
        withheld=False,
        expect_status=403,
        expect_reason="permission_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_alert_route_authorization.py::test_staff_cannot_manage_alert_rules",
        note="判据③的红，与上一格同根因（同一条 raise 路径）：写规则的拒绝同样没有审计。",
        finding="C",
        root_cause="product",
        evidence=(
            "同 app/api/v1/alerts.py:96-107 那条门，写规则只是它的第二个调用点："
            "app/api/v1/alerts.py:342-343（POST /alerts/rules 第一件事就是 _require_alert_management）。"
        ),
    ),
    Cell(
        cell_id="alert_route.manager_rule_write_is_allowed",
        surface="alert_route",
        identity="keeper",
        drive=_drive_alert,
        entitled=('"status": "ok"', "r159-new-rule"),
        forbidden=(),
        withheld=False,
        expect_status=200,
        audit_expect=("none", "告警面的授权判定不落审计（本件实测出来的事实，正是上面两格红的根因），所以这里既不该期待拒绝行，也不该期待放行行。"),
        covered_by="tests/test_alert_route_authorization.py::test_manager_can_manage_alert_rules",
        note="正向对照：manager 在自己作用域里确实能建规则，上面两格的 403 不是「谁都进不去」刷出来的。",
        root_cause="matrix",
        evidence=(
            "R159 把这一格留在读台账那条路上（WRITE_ALERT_CELLS 里只有 staff 那一格），而它钉的两枚令牌"
            "只出自写出口：app/api/v1/alerts.py:342-368 无库时回 {id, status=ok}、有库时同样回 status=ok；"
            "GET /alerts（:397-405）与 GET /alerts/rules（:370-377）两条都不吐这两个字。"
            "补进 WRITE_ALERT_CELLS 之后这一格转绿。"
        ),
    ),
    # ---------- 情报路由 ----------
    Cell(
        cell_id="intelligence_route.peer_cannot_see_anothers_triples",
        fixed_by="R177@40278eb",
        surface="intelligence_route",
        identity="peer",
        drive=_drive_intelligence,
        forbidden=("R159-ENT-", "R159-TARGET-", "R159-SRC-INTEL-"),
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="缺口（订正 R159 的记载）：tests/test_intelligence_route_authorization.py:97 那枚件的名字写着 owner_scoped，实读它只把 author 放研发部、stranger 放市场部（:104-105），证的是部门轴，不是归属轴；同部门不同主人这一格既存件零覆盖。",
        note="判据①的红（A 类）：作者与读数人同部门、同角色，只换了主人，三元组正文照样交回来。产品侧证据：Relation 落库时默认 visibility="
        + '"private"（app/knowledge_graph/service.py:86），这一格实测回来的记录里就带着 '
        + '"visibility": "private"；而这个标签一路被搬进 ResourceScope'
        + "（app/knowledge_graph/service.py:113-118）、再搬进 policy 的属性字典"
        + "（app/common/policy.py:68-71），判定链却一个字都不读它——"
        + "app/common/policy.py:127-213 依次只看 owner_match / action∈permissions / "
        + "legacy 无主文档 / 密级 / 部门交集 / admin 早退，归属只用来「多放行」从不用来"
        + "「拦人」。平台自己的验收方向写着「跨部门、跨密级、非所有者资源不可见」"
        + "（docs/current-functionality-2026-09-10.md:1316 P0-01）。forbidden 用主干匹配三元组名，"
        + "不写死整串；dashboard 那一枪只验能力闸门（manager 具备 analyze 所以 200），提交的行是"
        + "调用方自己带的，不属于越权内容，所以不把 R159-METRIC 列进 forbidden。",
        finding="A",
        root_cause="product",
        evidence=(
            "读侧谓词只到部门+密级为止：app/knowledge_graph/service.py:442-453 can_read 把判定整条委托给 "
            "app/common/policy.py:127-213，那里依次是 owner_match（:143-155，只用于「多放行」主人自己）、"
            "action∈permissions（:157-158）、legacy 无主文档（:170-175）、密级（:186-189）、部门交集"
            "（:191-205）——没有一条按「是不是主人」拦人；落库时写死的 visibility=private 标签"
            "（app/knowledge_graph/service.py:86）被 :113-118 搬进 ResourceScope、再被 "
            "app/common/policy.py:68-71 搬进属性字典，然后判定链一个字都不读它。"
            "平台自己的验收方向写着「跨部门、跨密级、非所有者资源不可见」"
            "（docs/current-functionality-2026-09-10.md:1316 P0-01）。"
        ),
    ),
    Cell(
        cell_id="intelligence_route.xdept_cannot_see_anothers_triples",
        surface="intelligence_route",
        identity="xdept",
        drive=_drive_intelligence,
        forbidden=("R159-ENT-", "R159-TARGET-", "R159-SRC-INTEL-"),
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_intelligence_route_authorization.py::test_knowledge_graph_relations_are_owner_scoped（部门轴那一半）",
        note="R163 补格：上一格红的是归属轴，这一格钉部门轴确实生效——xdept 与作者不同部门，"
        + "一条三元组都不该漏（app/knowledge_graph/service.py:442-453 can_read 走 "
        + "app/common/policy.py:191-205 的部门交集）。没有这一格，上一格的红分不清是「整条腿都不判」"
        + "还是「只漏归属这一个轴」。",
    ),
    Cell(
        cell_id="intelligence_route.author_reads_own_triples",
        surface="intelligence_route",
        identity="keeper",
        drive=_drive_intelligence,
        forbidden=("R159-METRIC-LEAK",),
        entitled=("R159-ENT-", "R159-TARGET-"),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_intelligence_route_authorization.py",
        note="正向对照：上一条的 0 命中不是因为谁都写不进去。",
    ),
    Cell(
        cell_id="intelligence_route.auditor_denied_dashboard_is_audited",
        surface="intelligence_route",
        identity="auditor",
        drive=_drive_intelligence,
        forbidden=("R159-METRIC",),
        withheld=False,
        expect_status=403,
        expect_reason="permission_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_intelligence_route_authorization.py::test_dashboard_requires_an_analyze_permission",
        note="auditor 有 view 没有 analyze：读图谱三元组可以，算仪表盘不行；这一格的审计是绿的，说明告警面那两格红是它自己的缺席，不是平台-wide 的审计缺位。",
    ),
    # ---------- 行级 scope（tools 腿）----------
    Cell(
        cell_id="row_scope_tools.selected_foreign_file_denied_with_code",
        surface="row_scope_tools",
        identity="keeper",
        drive=_drive_row_scope_tools,
        corpus=("fx_l1",),
        forbidden=_tokens(("fx_l1",)),
        expect_status=200,
        audit_expect=("none", "工具腿的拒绝落在 Agent Trace 证据袋（app/agents/tools.py 的 _record_denial），不落审计日志；同一个资源走数据集路由时的拒绝另有格子验（dataset_route.xdept_cannot_read_or_download 是绿的）。"),
        covered_by="tests/test_dataset_route_authorization.py 末条 / tests/test_r64_row_scope_error_codes.py",
        note="选了别人的文件当分析对象：交回来的是稳定码，不是「没有数据」。",
    ),
    Cell(
        cell_id="row_scope_tools.all_datasets_hidden_says_no_data_file",
        fixed_by="R178@a6c2710",
        surface="row_scope_tools",
        identity="xdept",
        drive=_drive_row_scope_tools,
        corpus=("own_l1", "own_l2"),
        forbidden=_tokens(("own_l1", "own_l2")),
        expect_status=200,
        audit_expect=("none", "同上一格。"),
        covered_by="缺口：tests/test_tools_row_scope_messaging.py 那 27 枚（R62）全部站在「文件已选中/行被过滤」那一层说话，没有任何一枚站在「一个文件都没被选中、而唯一存在的文件因为权限不可见」这一层。",
        note="判据②的红：app/agents/tools.py 未选中文件那条分支在 permitted 为空时原样返回「暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。」，而此刻确实存在文件、只是不属于这个账号。R62 修的是同一个形状的另一半。",
        finding="B",
        root_cause="product",
        evidence=(
            "app/agents/tools.py:237-248 未选中文件时逐条算 decision、只把 allowed 的收进 permitted，"
            "全被裁掉就返回空表且不带上任何 reason_code；app/agents/tools.py:952-954 拿到空表就原样吐"
            "「暂无数据文件。请先在数据分析面板上传 Excel/CSV 文件。」（query_data 那条腿同形："
            "app/agents/tools.py:1069-1071）。对照：选中了别人的文件那条分支"
            "（app/agents/tools.py:215-235）是说得出稳定码的，nodept 那一格就是绿的。"
        ),
    ),
    Cell(
        cell_id="row_scope_tools.nodept_account_gets_authority_code",
        surface="row_scope_tools",
        identity="nodept",
        drive=_drive_row_scope_tools,
        corpus=("own_l1",),
        forbidden=_tokens(("own_l1",)),
        expect_status=200,
        audit_expect=("none", "同上一格。"),
        covered_by="tests/test_rbac_department_fail_closed.py（行级）/ 本件补文件级",
        note="fail-closed 账号在工具腿上拿到的是权限因由，不是「没有数据」：这一格绿，说明上面那格红是分支漏了，不是整条腿都不会说因由。",
    ),
    Cell(
        cell_id="row_scope_tools.row_scope_hides_foreign_and_blank_rows",
        surface="row_scope_tools",
        identity="keeper",
        drive=_drive_row_scope_tools,
        corpus=("own_l1",),
        forbidden=(FOREIGN_ROW_TOKEN, BLANK_ROW_TOKEN),
        entitled=_tokens(("own_l1",)),
        withheld=False,
        expect_status=200,
        audit_expect=("none", "行级过滤不是拒绝事件。"),
        covered_by="tests/test_rbac_department_fail_closed.py / tests/test_tools_row_scope_messaging.py",
        note="正向对照：R17 甲案在工具腿上确实生效，别部门的行与没标部门的行都不出来。",
    ),
    Cell(
        cell_id="row_scope_tools.xclear_row_level_clearance",
        surface="row_scope_tools",
        identity="xclear",
        drive=_drive_row_scope_tools,
        corpus=("own_l1", "fx_l1"),
        forbidden=(FOREIGN_ROW_TOKEN, "R159-SRC-FX-L1"),
        entitled=_tokens(("own_l1",)),
        withheld=False,
        expect_status=200,
        audit_expect=("none", "行级过滤不是拒绝事件。"),
        covered_by="tests/test_rbac_department_fail_closed.py",
        note="staff（密级 1）在 tools 腿只看得见本部门密级 1 的那张表；跨部门那张连文件名都不该出现。",
        root_cause="matrix",
        evidence=(
            "与 dataset_route.xclear_cannot_preview_higher_classification 同一根因：桩没把语料块的密级交给 "
            "register（app/storage/datasets.py:113-121 默认 internal=2 档，app/common/policy.py:20-26），"
            "staff 只有 1 档（app/common/rbac.py:31）⇒ 工具腿在 app/agents/tools.py:225-236 连本部门那张"
            "本该看得见的表一起顶回（实测回话「暂无可访问的数据文件（error_code=clearance_insufficient）」）。"
            "修桩之后这一格转绿，回话里既有稳定码、又只剩自己的表。"
        ),
    ),
]

TOOL_CONFIG["row_scope_tools.selected_foreign_file_denied_with_code"] = {
    "data_filename": "R159-SRC-FX-L1.csv"
}
TOOL_CONFIG["row_scope_tools.nodept_account_gets_authority_code"] = {
    "data_filename": "R159-SRC-OWN-L1.csv"
}
MIXED_ROW_CELLS.add("row_scope_tools.row_scope_hides_foreign_and_blank_rows")
TOOL_CONFIG["row_scope_tools.xclear_row_level_clearance"] = {"data_filename": "R159-SRC-OWN-L1.csv"}


ARTIFACT_TOKENS = ("R159-SRC-ARTIFACT", "R159T-ARTIFACT-BYTES")

CELLS += [
    # ---------- 产物 / 导出物 ----------
    Cell(
        cell_id="artifact_surface.xdept_manager_denied_and_audited",
        surface="artifact_surface",
        identity="xdept",
        drive=_drive_artifact,
        forbidden=ARTIFACT_TOKENS,
        expect_status=403,
        expect_reason="department_scope_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_artifact_access.py",
    ),
    Cell(
        cell_id="artifact_surface.same_dept_lower_clearance_denied",
        surface="artifact_surface",
        identity="xclear",
        drive=_drive_artifact,
        forbidden=ARTIFACT_TOKENS,
        expect_status=403,
        audit_expect=("denied", ""),
        covered_by="缺口：tests/test_artifact_access.py 与 tests/test_artifact_list.py 只把「跨部门」和「主人降密级」两轴钉过，同部门低密级拿图表这一格没人验。",
    ),
    Cell(
        cell_id="artifact_surface.owner_lists_and_downloads",
        surface="artifact_surface",
        identity="keeper",
        drive=_drive_artifact,
        entitled=ARTIFACT_TOKENS,
        forbidden=(),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_artifact_access.py",
        note="正向对照：上面两格的 403 不是谁都拿不到产物。",
    ),
    Cell(
        cell_id="artifact_surface.static_generated_paths_are_closed",
        surface="artifact_surface",
        identity="xdept",
        drive=_drive_static_chart,
        forbidden=(),
        entitled=("404",),
        withheld=False,
        audit_expect=("none", "静态目录在授权判定之前就 404，不构成一次授权决策；这条口子是「旁路」而不是「越权」。"),
        covered_by="tests/test_artifact_access.py::test_static_chart_and_export_paths_do_not_bypass_artifact_authorization",
    ),
    # ---------- 开放平台自报部门头（R67 / R71 面）----------
    Cell(
        cell_id="open_platform.foreign_department_header_is_refused",
        surface="open_platform",
        identity="admin",
        drive=_drive_open_platform,
        forbidden=(DEPT_FOREIGN + "]",),
        withheld=False,
        expect_status=403,
        expect_reason="department_override_denied",
        audit_expect=("denied", ""),
        covered_by="tests/test_r71_open_department_convergence.py / tests/test_r67_department_self_report.py",
    ),
    Cell(
        cell_id="open_platform.granted_department_header_is_accepted",
        surface="open_platform",
        identity="admin",
        drive=_drive_open_platform,
        forbidden=(DEPT_FOREIGN, "r159-victim-user]"),
        entitled=("R159-OPEN-DEPT=[" + DEPT_OWN + "]", "R159-SCOPE-RESOLVED"),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_r71_open_department_convergence.py",
    ),
    Cell(
        cell_id="open_platform.no_grant_stays_fail_closed",
        surface="open_platform",
        identity="admin",
        drive=_drive_open_platform,
        forbidden=("R159-SCOPE-RESOLVED", DEPT_OWN + "]"),
        entitled=("R159-OPEN-DEPT=[]", "R159-SCOPE-authorization_unavailable"),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="tests/test_r71_open_department_convergence.py（空授权那一组）",
        note="一个部门都没授的应用，签名的头一个字都不该采信：拿到的作用域是空的，检索腿照 R17 fail-closed 拒。这一格同时是阶段 C 的硬判据之一（缓存/检索链路上的 fail-closed 账号）。",
    ),
    Cell(
        cell_id="open_platform.user_claim_is_not_the_audit_actor",
        surface="open_platform",
        identity="admin",
        drive=_drive_open_platform,
        forbidden=("R159-OPEN-ACTOR=[r159-victim-user]",),
        entitled=("R159-OPEN-ACTOR=[open-app:",),
        withheld=False,
        expect_status=200,
        audit_expect=("allowed", ""),
        covered_by="缺口：tests/test_r71_open_department_convergence.py / tests/test_r67_department_self_report.py 验的是「头不能决定部门」，没有一格验「头也不能决定审计里被记账的人」。",
        note="X-Open-User 没进签名基串，所以它只能是声明，不能是 actor：一个应用冒充某个人的登录名，就等于把审计行的归属写成别人的历史。",
    ),
    # ---------- 可观测 / 审计台 ----------
    Cell(
        cell_id="observability.audit_events_require_audit_read",
        surface="observability_audit",
        identity="xdept",
        drive=_drive_observability,
        forbidden=(AUDIT_SEED, "r159-victim-account"),
        withheld=False,
        expect_status=403,
        expect_reason="permission_denied",
        audit_expect=("denied", ""),
        covered_by="缺口：tests/test_observability_routes.py 的 18 枚管的是 traces / evaluations 的读门（:21 起），审计事件出口对无 audit:read 的人怎么答复此前没有一格钉过。",
        note="没有 audit:read 的人不许翻别人的拒绝记录；这一格同时钉「越权尝试被拒也进审计」。",
        root_cause="matrix",
        evidence=(
            "R159 打的是 /api/v1/observability/audit/events，而这条路由的实名没有 observability 那一段："
            "app/main.py:87 用 prefix=\"/api/v1\" 挂 observability.router，路由自己写的是 "
            "app/api/v1/observability.py:1152 的 @router.get(\"/audit/events\")"
            "（既存件 tests/test_observability_routes.py:21 用的就是 /api/v1/audit/events）。"
            "那枚「期望 403 实取 404」于是是 FastAPI 在授权闸门之前自己回的："
            "app/api/v1/observability.py:165-171 的 _require_action 根本没被走到，审计也不会写。"
            "R163 改实名之后这一格转绿：manager 无 audit:read（app/common/permissions.py:14 与 :16）"
            "⇒ app/api/v1/observability.py:150-163 回 403 permission_denied 并当场落一条 denied 审计。"
        ),
    ),
    Cell(
        cell_id="observability.auditor_reads_the_journal",
        surface="observability_audit",
        identity="auditor",
        drive=_drive_observability,
        entitled=("r159-auditor-", AUDIT_SEED),
        forbidden=(),
        withheld=False,
        expect_status=200,
        audit_expect=("none", "observability.py 的读审计事件出口自带注释说明它不落 allowed 事件，这是设计内事实。"),
        covered_by="缺口：上一格的反面对照（不钉这条，任何人都可以被「看不见」刷成绿）；tests/test_observability_routes.py 与 tests/test_audit_persistence.py 一个只管门、一个只管台账存不存得住。",
        root_cause="matrix",
        evidence=(
            "同一枚 URL 错（app/main.py:87 + app/api/v1/observability.py:1152）。改到实名之后 auditor "
            "拿 200，victim 那笔 R159SEED 拒绝记录确实在 events 里：读侧是整本台账倒序下发"
            "（app/api/v1/observability.py:1152-1186），只按 audit:read 这一道门裁人"
            "（app/common/permissions.py:16 auditor 有 ACTION_AUDIT、:14 manager 没有）。"
        ),
    ),
]

OPEN_CASES["open_platform.foreign_department_header_is_refused"] = {
    "granted": [DEPT_OWN],
    "claimed": DEPT_FOREIGN,
}
OPEN_CASES["open_platform.granted_department_header_is_accepted"] = {
    "granted": [DEPT_OWN],
    "claimed": DEPT_OWN,
}
OPEN_CASES["open_platform.no_grant_stays_fail_closed"] = {
    "granted": [],
    "claimed": DEPT_OWN,
}
OPEN_CASES["open_platform.user_claim_is_not_the_audit_actor"] = {
    "granted": [DEPT_OWN],
    "claimed": DEPT_OWN,
}


# ==================== 读数 ====================

#: 任务书点名的维度：任何一条从表里消失，本件当场变红，而不是悄悄少跑一格。
REQUIRED_IDENTITIES = {"keeper", "xdept", "xclear", "nodept", "peer", "admin", "auditor"}
REQUIRED_SURFACES = {
    "retrieval",
    "legacy_chat",
    "answer_cache",
    "answer_cache_wire",
    "document_route",
    "dataset_route",
    "session_route",
    "alert_route",
    "intelligence_route",
    "row_scope_tools",
    "artifact_surface",
    "open_platform",
    "observability_audit",
}

#: 判据④对照表的口径：covered_by 以这两个字开头＝本件新补；否则必须点到真实存在的既存测试件。
GAP_PREFIX = "缺口"
_CITED_TEST_FILE = re.compile(r"tests/(test_[0-9a-zA-Z_]+\.py)")
_TESTS_DIR = Path(__file__).resolve().parent


def cited_test_files(cell: Cell) -> tuple[str, ...]:
    """这一格声称被哪些既存测试件盖过（只认写成 tests/test_x.py 的实名）。"""
    return tuple(sorted(set(_CITED_TEST_FILE.findall(cell.covered_by))))


def is_gap_cell(cell: Cell) -> bool:
    return cell.covered_by.strip().startswith(GAP_PREFIX)


def gap_cells() -> list[Cell]:
    return [cell for cell in CELLS if is_gap_cell(cell)]


def cells_covering(test_file: str) -> list[Cell]:
    return [cell for cell in CELLS if test_file in cited_test_files(cell)]


def _blame_in(text: str) -> list[str]:
    return [word for word in (*EXECUTION_BLAME, *ABSENCE_BLAME) if word in text]


def _has_authority(text: str) -> bool:
    return any(word in text for word in AUTHORITY_WORDS)


def _describe_audit(ctx: Ctx) -> str:
    rows = ctx.audit_rows()
    if not rows:
        return "该 actor 在审计袋里一行都没有（actor=" + str(ctx.audit_actor or ctx.username) + "）"
    return " | ".join(
        row["outcome"] + "/" + row["resource"] + "/" + row["reason"] for row in rows[:6]
    )


@pytest.mark.parametrize("cell", CELLS, ids=[cell.cell_id for cell in CELLS])
def test_r159_cross_scope_cell(ctx, cell: Cell) -> None:
    """一格一条用例，三列分开报：红了要当场看得出是①②③里的哪一列。"""
    ctx.serve(cell)
    receipt = cell.drive(ctx, cell)
    failures: list[str] = []

    if cell.check_content:
        for token in cell.forbidden:
            if token and token in receipt.payload:
                failures.append("判据①内容越权：令牌「" + token + "」出现在响应里")
        for token in cell.entitled:
            if token and token not in receipt.payload and token not in receipt.notes:
                failures.append(
                    "判据①正向对照不成立：本该看得见的「" + token + "」没出现，"
                    "这一格的绿是空转刷出来的"
                )

    if cell.check_honesty:
        if cell.expect_status is not None and receipt.status != cell.expect_status:
            failures.append(
                "判据②状态口径不符：期望 " + str(cell.expect_status) + "，实际 " + str(receipt.status)
            )
        if cell.expect_reason and receipt.reason != cell.expect_reason:
            failures.append(
                "判据②稳定码不符：期望 " + cell.expect_reason + "，实际 「" + str(receipt.reason) + "」"
            )
        claim = receipt.claim or ""
        if cell.withheld and claim:
            blame = _blame_in(claim)
            if blame:
                failures.append(
                    "判据②把「因权限被隐藏」说成了别的（R62 诚实性面）：命中甩锅词 "
                    + str(blame) + "；原文摘录：" + claim[:240].replace("\n", " ")
                )
        if cell.told_no_scope and claim and not _has_authority(claim):
            failures.append(
                "判据②只交出空结果、没交出因由：账号本身没有可用作用域，"
                "响应里既没有权限码也没有权限话术；原文摘录："
                + claim[:240].replace("\n", " ")
            )

    if cell.check_audit:
        kind = str(cell.audit_expect[0])
        needle = str(cell.audit_expect[1] or "")
        if kind == "none":
            if not needle.strip():
                failures.append("判据③：audit_expect 选了 none 却不写书面理由，等于静默跳过")
        elif kind == "denied":
            rows = [
                row
                for row in ctx.audit_rows()
                if row["outcome"] == "denied" and needle in row["resource"]
            ]
            if not rows:
                failures.append(
                    "判据③审计缺席：这次越权拒绝在审计日志里查不到一笔。实测：" + _describe_audit(ctx)
                )
        elif kind == "allowed":
            rows = [
                row
                for row in ctx.audit_rows()
                if row["outcome"] == "allowed" and needle in row["reason"]
            ]
            if not rows:
                failures.append(
                    "判据③审计口径不符：期望一条 outcome=allowed 且 reason 含「" + needle
                    + "」的行。实测：" + _describe_audit(ctx)
                )
        else:
            failures.append("判据③：audit_expect 形态不认识：" + kind)

    assert not failures, (
        "R159 格子 " + cell.cell_id + "（面=" + cell.surface + "，身份=" + cell.identity + "）红：\n  - "
        + "\n  - ".join(failures)
        + ("\n  note: " + cell.note if cell.note else "")
    )


# ==================== 矩阵自身的守卫 ====================
#
# R159 那版把八枚放宽标记写成模块级常量，再拿全文源码去扫这些常量 ⇒ 字面量永远在
# 自己肚子里，这枚钉永不可能绿（总控 09-23 实测：21 红里就有它一枚）。R163 的改法是
# 「只扫那张表之外」：标记表搬进一枚具名函数，扫描器用 ast 取它的行区间整块剥掉，
# 表外一行都不放过；表本身另外用两道钉守住——族不许缺、总数不许缩。
# 不许删这枚钉、不许把标记从表里摘走、不许降级成只查其中一种，全部由代码判，不靠自觉。

MARKER_TABLE_FUNCTION = "_softening_marker_table"


def _softening_marker_table() -> tuple[str, ...]:
    """放宽手段的字面量表：全件唯一允许写这些东西的地方，扫描器按行区间把它整块跳过。"""
    return (
        "pytest.skip(",
        "@pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "pytest.xfail(",
        'filterwarnings("ignore"',
        "raises=False",
        "strict=False",
    )


#: 表里必须至少留出这几族——只查 skip 不查 skipif / xfail / mark 就是降级，判负。
REQUIRED_MARKER_FAMILIES = ("skip", "skipif", "xfail", "mark", "filterwarnings", "raises", "strict")
#: R159 交工时这张表就是八枚，缩到八枚以下等于偷偷少一种放宽手段。
MIN_MARKER_COUNT = 8
#: 本件现在的格子数；砍格子换绿会直接撞这一条。钉的维度/格数/归因三道闸都读它。
MIN_CELL_COUNT = 51

#: 归因尺子：判「产品漏」还是「矩阵搭错」都必须落到「文件:行」；只写一句「看起来是测试问题」判负。
_PRODUCT_PATH_PATTERN = re.compile(r"(?:app|tests|docs|static|frontend)/[\w./-]+[.:]\d+")
#: root_cause 只认这两值：product＝产品真的漏（A/B/C 红格必须归到这里），matrix＝矩阵桩搭错（修完必须绿）。
ALLOWED_ROOT_CAUSES = {"", "product", "matrix"}

SOFTENING_MARKERS = _softening_marker_table()


def _marker_table_line_span(source: str) -> tuple[int, int]:
    """标记表 own 的行区间（1 起，含头含尾）。表被改名 / 拆走 / 搬出函数 ⇒ 这里直接判红。"""
    import ast

    tree = ast.parse(source)
    spans = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == MARKER_TABLE_FUNCTION
    ]
    if len(spans) != 1:
        raise AssertionError(
            "标记表必须且只能由 " + MARKER_TABLE_FUNCTION + " 一处持有，实取 " + str(len(spans)) + " 处"
        )
    return spans[0]


def find_softening_markers(source: str) -> list[str]:
    """扫「标记表之外」的源码，返回每一处放宽标记的行号与内容。"""
    start, end = _marker_table_line_span(source)
    findings: list[str] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if start <= number <= end:
            continue
        for marker in SOFTENING_MARKERS:
            if marker in line:
                findings.append("第 " + str(number) + " 行出现放宽标记「" + marker + "」：" + line.strip()[:120])
    return findings


def audit_matrix_source(source: str) -> list[str]:
    """这枚钉的全部牙齿，收成一个函数：R163 的反向钉要把改过的源码喂进来验它有没有牙。"""
    findings: list[str] = list(find_softening_markers(source))

    if len(SOFTENING_MARKERS) < MIN_MARKER_COUNT:
        findings.append("标记表被摘薄：现 " + str(len(SOFTENING_MARKERS)) + " 枚，少于 " + str(MIN_MARKER_COUNT))
    for family in REQUIRED_MARKER_FAMILIES:
        if not any(family in marker for marker in SOFTENING_MARKERS):
            findings.append("标记表被降级：整张表里没有一族「" + family + "」的标记")

    identities = {cell.identity for cell in CELLS}
    surfaces = {cell.surface for cell in CELLS}
    if not REQUIRED_IDENTITIES <= identities:
        findings.append("身份维度缺：" + str(sorted(REQUIRED_IDENTITIES - identities)))
    if not REQUIRED_SURFACES <= surfaces:
        findings.append("资源面缺：" + str(sorted(REQUIRED_SURFACES - surfaces)))
    if len(CELLS) < MIN_CELL_COUNT:
        findings.append("格子数掉了：现 " + str(len(CELLS)) + " 格，下限 " + str(MIN_CELL_COUNT))

    ids = [cell.cell_id for cell in CELLS]
    if len(set(ids)) != len(ids):
        findings.append("cell_id 有重复，参数化 id 会撞车")
    for cell in CELLS:
        if not (cell.check_content or cell.check_honesty or cell.check_audit):
            findings.append(cell.cell_id + " 三列全关")
        if str(cell.audit_expect[0]) == "none" and not str(cell.audit_expect[1] or "").strip():
            findings.append(cell.cell_id + " 的 N/A 没写理由")
        if cell.finding and cell.finding not in {"A", "B", "C"}:
            findings.append(cell.cell_id + " 的 finding 不在 A/B/C 里：" + cell.finding)
        if cell.root_cause not in ALLOWED_ROOT_CAUSES:
            findings.append(cell.cell_id + " 的 root_cause 形态不认识：" + repr(cell.root_cause))
        if cell.finding and cell.root_cause != "product":
            findings.append(
                cell.cell_id + " 归了 " + cell.finding + " 类却没写成产品漏（root_cause="
                + repr(cell.root_cause) + "）：A/B/C 红格只能判在产品侧"
            )
        if cell.root_cause == "matrix" and cell.finding:
            findings.append(
                cell.cell_id + " 说矩阵桩搭错却还留着 " + cell.finding + " 归因：桩修完这一格必须绿"
            )
        if (cell.finding or cell.root_cause) and not _PRODUCT_PATH_PATTERN.search(cell.evidence):
            findings.append(
                cell.cell_id + " 归了因却没给「文件:行」级产品证据（矩阵搭错同样要给，判负条件）"
            )
        # 判据④对照表：每一格必须说清「既存谁盖过」或「本件新补」，且引到的既存件得真在盘上。
        if not cell.covered_by.strip():
            findings.append(cell.cell_id + " 的 covered_by 空着：对照表少一格，下一班就得重数一遍")
        cited = cited_test_files(cell)
        if not cited:
            findings.append(
                cell.cell_id + " 的 covered_by 没点到任何一枚 tests/test_x.py 实名：判据④的表回查不动"
            )
        for name in cited:
            if not (_TESTS_DIR / name).exists():
                findings.append(cell.cell_id + " 引了盘上不存在的既存件 tests/" + name)
    return findings


def test_r159_matrix_is_not_softened() -> None:
    """本件不许被改松：标记表之外出现放宽手段、表被摘薄降级、或表被砍掉维度，当场变红。"""
    from pathlib import Path

    findings = audit_matrix_source(Path(__file__).read_text(encoding="utf-8"))
    assert not findings, "矩阵被放宽了：\n  - " + "\n  - ".join(findings)


def test_r159_matrix_reports_the_readout() -> None:
    """把「越权命中多少格」这句读数要用的原始事实摆在测试输出里，读数不靠人复述。"""
    from collections import Counter

    by_surface: Counter[str] = Counter(cell.surface for cell in CELLS)
    by_identity: Counter[str] = Counter(cell.identity for cell in CELLS)
    gaps = [cell.cell_id for cell in gap_cells()]
    cited_files = {name for cell in CELLS for name in cited_test_files(cell)}
    line = (
        "R159 矩阵：" + str(len(CELLS)) + " 格 / " + str(len(by_surface)) + " 个资源面 / "
        + str(len(by_identity)) + " 种身份；引既存权限件 " + str(len(cited_files)) + " 枚；缺口新补 "
        + str(len(gaps)) + " 格"
    )
    print(line)
    assert len(CELLS) == sum(by_surface.values())
    assert line
