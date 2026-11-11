"""R383 腿 A：文档目录在生产不许把「问不出」答成「没有」。

R377 现场实量（本单基点 `96179ff` 复核成立）：PG 在、连上了、`document_versions` 表不在 ⇒
`GET /api/v1/documents` 与 `/documents/catalog` 各答一次 **200 `{"documents": []}`**，
`GET /api/v1/documents/{f}/versions` 答 **404 `resource_not_found`**。生产客户在知识库那一屏
读到的是「这家公司没有文档」——把一次存储拒答翻译成了一句假话，与 `/users`（R356）、
`/dashboard`（R332）、告警（R359）、通知（R299）同一条裁定，文档目录是这条链上最后还在沉默
回空的一环。本件钉住改口之后的四件事：

1. 三张脸三句话：缺表（存储没迁移）/ 库没起（`_db_ready` 为假）/ 权限不足，各答各的。前两格
   共用仓里已有的那一枚 503 `storage_unavailable`（零新增错误码、零新增 reason、零新增 status
   档位），把它们分辨开的是闸那两行不同的日志；权限那张脸（中间件的 401 与按行 withheld 的
   `restricted`）本单一根手指没动。
1b. 效力边界（本单改口过一次，交回的是最终口径）：入口闸只做在三枚写口上，两枚读口不设入口
   闸。「生产 + PG 不在位」读侧仍按设计交 JSON sidecar（catalog 文件头那两本真账），改前改后逐字
   相同，由 `test_a_store_that_never_came_up_still_serves_the_read_leg_by_design` 钉成故意的边界；
   同一枚状态下三枚写口整发拒——读侧那一格回落的是真账，写侧那一格「已经登记」只做成了半件事。
   缺表那一格（R377 现场实量的病灶）读写两扇门都拒，那才是本单真正改脸的地方。
2. 写侧也量出来了（R377 那一格没实量到结论）：改之前 `record_document_version` 交 metadata、
   `delete_document_versions` 交 `None`，两枚都说「成了」；现在两枚都拒。
3. 开发/裸机/离线三条腿一个字都没改：本地台账回落是设计。它由 `test_document_catalog_sync`(6)
   / `test_document_delete_catalog`(12) / `test_document_upload_resilience`(13) /
   `test_r292_catalog_current_version_parity`(15) / `test_offline_runtime_fallbacks`(13) /
   `test_r377_*`(26) 这一族既有钉分头守着；本件另加一枚反向钉（闸不许在非生产咬人），
   「把闸做成对所有环境都咬」写成反证刀 2。
4. 闸只借现成的读数：本模块既有的 `_database_available()`（全模块唯一一枚 `_db_ready` 读者）
   与 `_is_production_environment()`（与 `app/api/v1/alerts.py:61` 同一把尺），一枚都不新造。

🔴 效力边界：本件全部跑在替身台账上——它只对 `to_regclass(...)` 那一次现查作答，不求值任何真实
SQL、不碰真库、不起服务、不 DROP 任何东西。它证明的是「出口在读到缺表时答什么」，不证明
「跑 migrations 真能把那一格补出来」。
"""
from __future__ import annotations

import ast
import asyncio
import io
import re
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.common import auth
from app.documents import catalog
from scripts import r396_anchor_ledger as anchor_ledger
from app.main import app

REPO = Path(__file__).resolve().parents[1]
CATALOG_REL = "app/documents/catalog.py"
STORAGE_CODE = "storage_unavailable"
BARE_500_BODY = "Internal Server Error"
GATE_MISSING_TABLE = "code=storage_unavailable migration="
GATE_NO_STORE = "code=storage_unavailable（PG 未起）"
REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)
PROBE_STATEMENT = "SELECT to_regclass('public.document_versions') AS table_name"
#: 🔴 R396 起这两本账一个行号都不抄：每格是一枚锚点 token（符号名 + 该符号内唯一的语句形状），
#: 行号由 `scripts/r396_anchor_ledger.py` 现读，形状钉见
#: `tests/test_r396_line_numbers_are_derived_not_copied.py`。闸挪位照样绿；闸被复制或被搬走 =
#: 锚点读不到/读多枚，本件当场红并点名锚点（不是静默跳过）。
GATE_EXIT_ANCHORS = ("http_raise:_require_ready_store:503",)
#: 五枚 `_ensure()` 调用点：逐格一 token，记「哪一枚 scope 里的那一枚调用」。
ENSURE_CALL_ANCHORS = (
    "call:peek_next_document_version:_ensure",
    "call:record_document_version:_ensure",
    "call:current_documents:_ensure",
    "call:list_document_versions:_ensure",
    "call:delete_document_versions:_ensure",
)

ADMIN = "r383-admin"
ACCOUNT = {"id": "u-r383", "username": ADMIN, "role": "admin", "department": "", "status": "active"}


class _Sink:
    """记下模块 logger 的每一行：三张脸必须有两句不同的话，这是唯一的取证面。"""

    def __init__(self):
        self.lines: list[str] = []

    def _log(self, message, *args, **kwargs):
        self.lines.append(str(message))

    debug = info = warning = error = exception = _log

    def containing(self, needle: str) -> list[str]:
        return [line for line in self.lines if needle in line]


class _Store:
    """替身台账：只回答 to_regclass 与那两条 SELECT，并记下每一条语句好数闸排在哪。"""

    def __init__(self, tables=(), version_rows=(), label="store"):
        self.tables = set(tables)
        self.version_rows = list(version_rows)
        self.label = label
        self.statements: list[str] = []
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        found = REGCLASS.search(text)
        if found:
            name = found.group(1)
            self._rows = [{"table_name": name if name in self.tables else None}]
        elif "FROM document_versions" in text:
            self._rows = list(self.version_rows) if "document_versions" in self.tables else []
        else:
            self._rows = []
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        raise AssertionError(f"{self.label}: 生产分支不许在运行期提交 DDL")

    def close(self):
        return None


def _source(relative: str) -> str:
    path = REPO / relative
    assert path.is_file(), f"写域里的文件不见了: {path}"
    return path.read_text(encoding="utf-8")


def _tree(relative: str) -> ast.Module:
    return ast.parse(_source(relative))


def _anchor_lines(cells: tuple[str, ...], relative: str = CATALOG_REL) -> tuple[int, ...]:
    """🔴 行号一律现读：把锚点账喂给 R396 那台机器，交回它与现场相等的那几行（零抄数）。"""
    return anchor_ledger.derive_ledger(anchor_ledger.read_sources(relative), relative, cells)

def _function(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _raise_sites_with_status(tree: ast.Module, status: int) -> list[int]:
    """按 AST 数 `raise HTTPException(status_code=<status>, ...)`（R377 同一把尺，参数化不计）。"""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "HTTPException":
            continue
        for keyword in node.exc.keywords:
            if keyword.arg != "status_code":
                continue
            try:
                value = ast.literal_eval(keyword.value)
            except ValueError:
                continue
            if value == status:
                lines.append(node.lineno)
    return sorted(lines)


def _raise_details_with_status(tree: ast.Module, status: int) -> list[str]:
    """把 `raise HTTPException(status_code=<status>, detail=...)` 里那句 detail 逐字取出来。"""
    details: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not isinstance(node.exc.func, ast.Name) or node.exc.func.id != "HTTPException":
            continue
        seen_status = seen_detail = None
        for keyword in node.exc.keywords:
            if keyword.arg == "status_code":
                try:
                    seen_status = ast.literal_eval(keyword.value)
                except ValueError:
                    continue
            elif keyword.arg == "detail":
                seen_detail = keyword.value
        if seen_status == status and isinstance(seen_detail, ast.Constant):
            details.append(str(seen_detail.value))
    return details

def _db_ready_reads(source: str) -> list[int]:
    """一行算一处 `_db_ready` 读者：Name/Attribute 载入，或 getattr/hasattr 的常量名（R246 同尺）。"""
    tree = ast.parse(source)
    lines: list[int] = []
    load = ast.Load
    for node in ast.walk(tree):
        attribute = isinstance(node, ast.Attribute) and node.attr == "_db_ready"
        name = isinstance(node, ast.Name) and node.id == "_db_ready"
        if (attribute or name) and isinstance(node.ctx, load):
            lines.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in {"getattr", "hasattr"}:
                continue
            names = [arg.value for arg in node.args[1:] if isinstance(arg, ast.Constant)]
            if "_db_ready" in names:
                lines.append(node.lineno)
    return sorted(set(lines))


@pytest.fixture
def world(monkeypatch, tmp_path):
    """一份「本地台账里躺着 v1」的现场：环境、旗标、替身台账由各用例来拧。"""
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "policy__v1.txt").write_text("hello", encoding="utf-8")
    sink = _Sink()
    monkeypatch.setattr(catalog, "logger", sink)
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(docs), raising=False)
    monkeypatch.setattr(catalog, "_initialized", False)
    monkeypatch.setattr(auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(auth, "_memory_store_denied", lambda operation: False, raising=False)
    return {"docs": docs, "sink": sink, "monkeypatch": monkeypatch}


def _arm(world, *, environment, db_ready, tables, version_rows=()):
    """拧成一枚具体状态，交出那枚替身台账（数它收到的语句 = 数闸有没有抢在现查之前）。"""
    monkeypatch = world["monkeypatch"]
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setattr(auth, "_db_ready", db_ready)
    store = _Store(tables=tables, version_rows=version_rows, label="catalog")
    monkeypatch.setattr(catalog, "_conn", lambda: store)
    return store


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ============================================ 判据①③：缺表那一格现在拒答，不再答空集
def test_missing_table_makes_both_listings_refuse_503(world):
    _arm(world, environment="production", db_ready=True, tables=())
    client = _client()

    listing = client.get("/api/v1/documents", headers=_headers())
    catalog_view = client.get("/api/v1/documents/catalog", headers=_headers())

    assert listing.status_code == 503, listing.text
    assert catalog_view.status_code == 503, catalog_view.text
    assert listing.json() == {"detail": STORAGE_CODE}
    assert catalog_view.json() == {"detail": STORAGE_CODE}
    assert BARE_500_BODY not in listing.text + catalog_view.text


def test_the_refusal_is_never_rendered_as_an_empty_knowledge_base(world):
    """🔴 反证刀 1 的靶子：把闸摘掉，这一枚第一个红（200 + `{"documents": []}` 会回来）。"""
    _arm(world, environment="production", db_ready=True, tables=())

    response = _client().get("/api/v1/documents", headers=_headers())

    assert response.json() != {"documents": []}, "拒答又被翻译成了空集：那正是本单要修的病灶"
    assert "documents" not in response.json(), response.json()


def test_version_history_refuses_503_instead_of_claiming_absence(world):
    """404 `resource_not_found` 比空集更像一句确定的假话：这一格同样必须改口。"""
    _arm(world, environment="production", db_ready=True, tables=())

    response = _client().get("/api/v1/documents/policy.txt/versions", headers=_headers())

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert "resource_not_found" not in response.text


def test_the_local_ledger_is_not_read_at_all_when_production_refuses(world):
    """拒答不许顺手把本地台账读一遍：读了就是两本真相，「回落」还留着半条腿。"""
    reads: list[str] = []
    _arm(world, environment="production", db_ready=True, tables=())
    world["monkeypatch"].setattr(
        catalog,
        "_local_version_rows",
        lambda filename=None: reads.append(str(filename)) or [],
    )

    assert _client().get("/api/v1/documents", headers=_headers()).status_code == 503
    assert reads == [], f"生产拒答还去读了本地台账：{reads}"


# ============================================ 判据①的效力边界：读侧「库没起」那一格不改
def test_a_store_that_never_came_up_still_serves_the_read_leg_by_design(world):
    """本单唯一一处「查完发现不该改」：生产而 PG 不在位，读侧交的是设计内的 sidecar。

    它不是 R377 那一格假话：盘上那枚 `.document-versions.json` 与 `documents/` 目录是真的，
    交出去的行数改前改后逐字相同（alerts 那一族必须拒是因为 `_MEM_ALERTS` 在客户机上恒为空）。
    缺表那一格才是要改的：权威库连着、表却不在，回落本地台账就把「问不出」说成了「没有」。
    """
    _arm(world, environment="production", db_ready=False, tables=())
    client = _client()

    listing = client.get("/api/v1/documents", headers=_headers())
    catalog_view = client.get("/api/v1/documents/catalog", headers=_headers())

    assert (listing.status_code, catalog_view.status_code) == (200, 200)
    rows = catalog_view.json()["documents"]
    assert [row["filename"] for row in rows] == ["policy.txt"], rows
    assert rows[0]["version"] == 1, rows[0]


def test_the_same_missing_store_refuses_the_write_leg_but_not_the_read_leg(world):
    """同一枚状态两张脸：读侧按设计交台账，写侧整发拒——两扇门不许并成一张脸。"""
    _arm(world, environment="production", db_ready=False, tables=())

    assert _client().get("/api/v1/documents/catalog", headers=_headers()).status_code == 200

    with pytest.raises(HTTPException) as peeked:
        catalog.peek_next_document_version("policy.txt")
    assert (peeked.value.status_code, peeked.value.detail) == (503, STORAGE_CODE)
    with pytest.raises(HTTPException) as deleted:
        catalog.delete_document_versions("policy.txt", storage_paths=())
    assert (deleted.value.status_code, deleted.value.detail) == (503, STORAGE_CODE)


def test_the_two_storage_gaps_do_not_share_a_sentence(world):
    """判据③：两格共用一枚码，但必须各说各的排查路——那两行日志就是「三句话」里的两句。"""
    _arm(world, environment="production", db_ready=True, tables=())
    _client().get("/api/v1/documents", headers=_headers())
    missing = world["sink"].containing(GATE_MISSING_TABLE)
    assert missing and not world["sink"].containing(GATE_NO_STORE), world["sink"].lines

    world["sink"].lines.clear()
    _arm(world, environment="production", db_ready=False, tables=())
    with pytest.raises(HTTPException):
        catalog.peek_next_document_version("policy.txt")
    down = world["sink"].containing(GATE_NO_STORE)
    assert down and not world["sink"].containing(GATE_MISSING_TABLE), world["sink"].lines


def test_the_refusal_comes_before_the_module_owns_a_connection(world):
    """库没起那一格（写腿）：闸必须在任何一次连接之前回话，`_conn` 一次都不许被调到。"""
    calls: list[str] = []
    world["monkeypatch"].setattr(catalog, "_conn", lambda: calls.append("conn") or _Store())
    world["monkeypatch"].setenv("APP_ENV", "production")
    world["monkeypatch"].setattr(auth, "_db_ready", False)

    # storage_path 必须是 tmp_path 下的绝对路径：反证刀把闸摘掉时这一枚会真的写盘，
    # 相对路径会落进工作树的 documents/，把评测台账那枚 corpus parity 钉带红（本班实测红过一枚）。
    leak_proof = str(world["docs"] / "policy__v2.txt")
    with pytest.raises(HTTPException) as caught:
        catalog.record_document_version("policy.txt", 1, "", leak_proof)
    assert (caught.value.status_code, caught.value.detail) == (503, STORAGE_CODE)
    assert calls == [], f"拒答抢在连接之后：{calls}"
    assert not (world["docs"] / ".document-versions.json").exists(), "拒答还先把本地那笔记上了"


def test_the_migrations_probe_is_the_only_statement_a_refusal_sends(world):
    """缺表那一格：闸只许问那一次 to_regclass，SELECT document_versions 一条都不许发出去。"""
    store = _arm(world, environment="production", db_ready=True, tables=())

    assert _client().get("/api/v1/documents", headers=_headers()).status_code == 503
    assert store.statements == [PROBE_STATEMENT], store.statements


# ============================================ 判据③：写路径不许「静默吞后回成功」
def test_the_upload_leg_refuses_before_a_single_byte_lands(world):
    """生产缺表时上传整发拒：一字节都不落盘、一次索引都不碰、一条台账都不写。"""
    from app.api.v1 import chat

    _arm(world, environment="production", db_ready=True, tables=())
    added: list[str] = []

    class _Stub:
        def add_document(self, filename, content, classification, department):
            added.append(filename)
            return True, "已添加 1 个文本块"

        def list_documents(self):
            return []

    world["monkeypatch"].setattr(chat, "retriever", _Stub())
    world["monkeypatch"].setattr(chat, "DOCUMENTS_DIR", str(world["docs"]), raising=False)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            chat.upload_document(
                UploadFile(filename="policy.txt", file=io.BytesIO(b"body")),
                classification=1,
                department="",
            )
        )

    assert (caught.value.status_code, caught.value.detail) == (503, STORAGE_CODE)
    assert added == [], "拒答之前已经把它索引进知识库了"
    assert [p.name for p in world["docs"].iterdir()] == ["policy__v1.txt"], "落盘了半件事"


def test_record_and_delete_refuse_instead_of_answering_success(world):
    """R377 没量到的那一格今天量出来了：改之前两枚写口都答「成功」，现在都拒。"""
    _arm(world, environment="production", db_ready=True, tables=())
    storage = str(world["docs"] / "policy__v2.txt")
    (world["docs"] / "policy__v2.txt").write_text("again", encoding="utf-8")

    with pytest.raises(HTTPException) as recorded:
        catalog.record_document_version("policy.txt", 1, "", storage, owner_id=ADMIN)
    assert (recorded.value.status_code, recorded.value.detail) == (503, STORAGE_CODE)

    with pytest.raises(HTTPException) as deleted:
        catalog.delete_document_versions("policy.txt", storage_paths=(storage,))
    assert (deleted.value.status_code, deleted.value.detail) == (503, STORAGE_CODE)
    assert (world["docs"] / "policy__v2.txt").is_file(), "拒答却先把本地那一半抹了"


def test_peek_refuses_so_a_refused_upload_cannot_name_a_version(world):
    _arm(world, environment="production", db_ready=True, tables=())

    with pytest.raises(HTTPException) as caught:
        catalog.peek_next_document_version("policy.txt")

    assert (caught.value.status_code, caught.value.detail) == (503, STORAGE_CODE)


# ============================================ 判据④：开发/裸机/离线三条腿一个字没改
@pytest.mark.parametrize("environment", [None, "development", "dev", "staging", "test", "local"])
def test_the_gate_never_bites_outside_a_production_environment(world, environment):
    """🔴 反证刀 2 的靶子：把闸做成对所有环境都咬，这一枚与那一族既有钉一起红。"""
    _arm(world, environment=environment, db_ready=False, tables=())

    listing = _client().get("/api/v1/documents", headers=_headers())
    catalog_view = _client().get("/api/v1/documents/catalog", headers=_headers())

    assert listing.status_code == 200, listing.text
    assert catalog_view.status_code == 200, catalog_view.text
    rows = catalog_view.json()["documents"]
    assert [row["filename"] for row in rows] == ["policy.txt"], rows
    assert rows[0]["version"] == 1, rows[0]


def test_development_still_self_heals_its_table_and_answers_from_postgres(world):
    """开发态那条「就地补 DDL」的自愈支路一个字没动：非生产仍然建表、仍然答 200。"""
    statements: list[str] = []
    store = _arm(world, environment="development", db_ready=True, tables=())
    world["monkeypatch"].setattr(
        catalog, "_conn", lambda: statements.extend(store.statements) or store
    )

    assert _client().get("/api/v1/documents", headers=_headers()).status_code == 200
    joined = " ".join(store.statements).upper()
    assert "CREATE TABLE IF NOT EXISTS DOCUMENT_VERSIONS" in joined, store.statements


def test_production_with_its_table_answers_normally_from_the_store(world):
    """闸不是「生产一律 503」：库在、表在，两枚出口照旧从 PG 作答，一字节都不落本地台账。"""
    row = {
        "filename": "ledger.txt", "version": 1, "classification": 1, "department": "",
        "storage_path": "documents/ledger.txt", "created_at": "2026-09-27T10:00:00+08:00",
        "owner_id": ADMIN, "size_bytes": 4, "parse_status": "ready",
    }
    _arm(
        world, environment="production", db_ready=True,
        tables=("document_versions",), version_rows=[row],
    )
    client = _client()

    catalog_view = client.get("/api/v1/documents/catalog", headers=_headers())

    assert catalog_view.status_code == 200, catalog_view.text
    assert [item["filename"] for item in catalog_view.json()["documents"]] == ["ledger.txt"]


def test_an_anonymous_caller_never_meets_the_storage_answer(world):
    """权限那张脸没被并进存储那张：匿名拿到的仍然是中间件那一句 401。"""
    _arm(world, environment="production", db_ready=True, tables=())

    response = _client().get("/api/v1/documents")

    assert response.status_code == 401, response.text
    assert STORAGE_CODE not in response.text


# ============================================ 判据②：闸只借现成的，形状一枚都不许多长
def test_the_module_owns_exactly_one_storage_exit():
    """全模块恰好一枚 503，且它就是账上那枚锚点读出来的闸里那一格。"""
    tree = _tree(CATALOG_REL)
    exits = _raise_sites_with_status(tree, 503)

    assert exits == list(_anchor_lines(GATE_EXIT_ANCHORS)), (
        f"目录模块那道 503 应当恰好一枚且在闸里，实测 {exits}"
    )
    gate = _function(tree, anchor_ledger.anchor_symbol(GATE_EXIT_ANCHORS[0]))
    assert gate is not None and gate.lineno <= exits[0] <= gate.end_lineno, "那道 503 不在闸的函数体里"
    assert _raise_sites_with_status(tree, 500) == [], "目录模块不许自己写 500"


def test_the_refusal_reuses_a_code_the_enumeration_already_ratifies():
    codes: list[str] = []
    for node in ast.walk(ast.parse(_source("app/agents/contracts.py"))):
        if isinstance(node, ast.ClassDef) and node.name == "ErrorEnvelope":
            for stmt in node.body:
                annotation = getattr(stmt, "annotation", None)
                annotation_is_literal = isinstance(annotation, ast.Subscript) and (
                    getattr(annotation.value, "id", "") == "Literal"
                )
                if annotation_is_literal:
                    values = [e.value for e in annotation.slice.elts if isinstance(e, ast.Constant)]
                    codes.extend(values)

    assert codes, "contracts.py 里读不到 ErrorEnvelope.code 的 Literal，判器不许降级成恒真"
    assert STORAGE_CODE in codes, "本单不许为了「存储拒答」新造一枚码"
    # 🔴 反证刀 4b 的收口（R383 自钉收紧）：闸交出去的那一句必须逐字是上面那枚已批准的码。
    details = _raise_details_with_status(_tree(CATALOG_REL), 503)
    assert details == [STORAGE_CODE], f"目录模块那枚 503 交出的不是已批准的码，或不止一枚：{details}"


def test_the_module_did_not_grow_a_second_store_probe():
    """`_db_ready` 的读者总数由 R246 按 AST 管：本模块仍然只有 `_database_available()` 那一条。"""
    readers = _db_ready_reads(_source(CATALOG_REL))

    assert len(readers) == 1, f"目录模块里长出了第二枚 `_db_ready` 读者：{readers}"


def test_the_production_ruler_did_not_gain_a_definition_anywhere():
    """全仓那八枚 `_is_production_environment` 定义一枚都不许多长（R367/R376 借的同一把尺）。"""
    found = [
        str(path.relative_to(REPO)).replace("\\", "/")
        for path in sorted((REPO / "app").rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name == "_is_production_environment"
    ]

    assert len(found) == 8, f"生产判定尺多长了一枚：{found}"


def test_the_migrations_first_conversion_is_narrow():
    """只认本模块那一句前缀：把任何异常都翻成 503 = 替真正的 bug 打掩护（R371 的裁定）。"""
    body = ast.dump(_function(_tree(CATALOG_REL), "_schema_needs_migrations"))

    assert "startswith" in body, "判定不再只认那句前缀：捕获面被放宽了"
    assert "MIGRATION_REQUIRED_PREFIX" in _source(CATALOG_REL)


def test_every_ensure_call_site_still_ends_in_a_named_refusal():
    """五枚调用点仍然一枚不少地被 catch-all 兜着，且每枚都排好了「现查到缺表就先拒」。

    🔴 R396 起这本账不抄行号：`ENSURE_CALL_ANCHORS` 逐格记「哪一枚 scope 里的那枚 `_ensure()`」，
    行号在这里现读，再与 `_ensure` 落点所在 try 的 catch-all 逐格配对。少一枚调用点、多一枚裸调用点、
    闸没抢在回落之前，三样都当场红——只是红的依据从「数字对不上」换成了「账与现场对不上」。
    """
    tree = _tree(CATALOG_REL)
    guarded: dict[int, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handlers = [h for h in node.handlers if h.type is None or "Exception" in ast.dump(h.type)]
        if not handlers:
            continue
        inner = min(h.lineno for h in handlers)
        for call in ast.walk(node):
            direct = isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            if direct and call.func.id == "_ensure":
                guarded[call.lineno] = inner

    ledger_calls = _anchor_lines(ENSURE_CALL_ANCHORS)
    assert list(ledger_calls) == sorted(ledger_calls), (
        f"调用点账不按源码序：{list(ledger_calls)}——逐格配对靠源码序，别打乱"
    )
    assert sorted(guarded) == sorted(ledger_calls), {
        "锚点现读": sorted(ledger_calls),
        "现场扫出": sorted(guarded),
    }
    refusing: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.lineno in set(guarded.values()):
            names = {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
            if {"_schema_needs_migrations", "_require_ready_store"} <= names:
                refusing.append(node.lineno)

    assert sorted(refusing) == sorted(set(guarded.values())), refusing
    assert [guarded[line] for line in ledger_calls] == sorted(refusing), (
        "调用点与拒答 handler 交叉接线了：账上第 i 枚调用点没落在第 i 枚拒答 handler 里"
    )
