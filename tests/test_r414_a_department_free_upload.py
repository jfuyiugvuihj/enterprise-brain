# -*- coding: utf-8 -*-
r"""R414 (a) · 形状钉：**上传出口今天不因空部门而拒收**，本件钉的就是这一格现状。

这不是「还没做」的记账条，而是一枚会咬人的断言：出口对一枚 ``department`` 为空的主体的实际
行为是 **200 收下 + 回执 ``department=""``**（``test_the_upload_exit_does_not_refuse_a_department_free_principal_today``）。
谁把拒收悄悄加进来，这枚钉当场红，逼他重裁下面那三条件；谁把下面三条件的前提改了（补了部门、
换了上传账号、文档那一节开始自己点名部门），另几枚派生钉同样当场红。

**为什么今天不收**：判据原文在 ``docs/perf/r387-label-lineage-2026-09-27.md`` 的 A2 格（``POST /upload``
在 ``principal.department`` 为空时答 422 ``department_scope_required``，而不是静默落 ``""``）。它的断点
两跳都在册 —— 服务端用主体的部门**覆盖**接口形参（``app/api/v1/chat.py::upload_document`` 形参写着
``department: str = Form("")``，函数体第一句就把它重绑成 ``str(getattr(principal, "department", "") or "")``），
而 ``app/common/auth.py`` 从 ``users.department`` 取到 SQL NULL ⇒ 空值一路放行，落库成 ``department=''``。
但**前置没到位**：前置 = **业主 A1**（给 ``users.department`` 补值），今天没做。派工令写死了停手条件：
三条里只要有一条会被打死，就不许改默认行为。本班与总控各自独立取证，三条件读数一致：

① **种子路径会死** —— ``scripts/seed_workspace.py`` 把管理员那一枚 session 直接交进 ``seed_documents``，
   清单 ``deploy/workspace-seed.json`` 明写管理员**故意不挂部门**（``owners`` 里只有 ``dataowner``/财务部）。
   422 一生效，100 篇语料一篇都灌不进去，而且是当场 ``SeedError``、不是「少传几篇」。
② **下一扇真机跑分窗开不了** —— P-9 的前置就是那 100 篇，同一枚清单同一枚脚本；runbook 又把两条绕行
   路线（改 ``AUTH_DEPARTMENT`` 重启、``docker cp``）明令禁掉。总控 09-28 现读 ``documents`` 105 行里
   **102 行部门为空** —— 语料这一格今天完全靠无部门账号灌进来。
③ **同名重传从「能用」变「不能传」** —— ``_upsert_document`` 的 ``ON CONFLICT (filename) DO UPDATE`` 里带着
   ``department = EXCLUDED.department``，部门跟着**这一次**的上传人走；拒收一生效，连案卷里那 4 枚
   ``server_only`` 残件唯一的修法（文件放回盘上再传一次）一并堵死。

🔴 「顺手把语料改由 ``dataowner`` 上传」**不是解药**，本件也钉这一格：那 100 篇会带上 ``department=财务部``，
而提问账号是 ``admin``/``evalbot``（无部门），检索作用域按部门匹配 ⇒ 语料对提问者不可见、evidence 直接
归零 —— 那是把一个已知缺口换成一次假红。所以这一格的开工条件只有一条：**业主 A1 落地**（生产里每一枚
上传账号都有部门），届时先删本件、再按 A2 原文改出口与契约。

出口形状那一格仍然钉住（``test_the_registered_scope_code_is_not_emitted_from_the_upload_exit``）：这枚码名
唯一的出处是 ``app/api/v1/data.py``，``chat.py`` 里今天一个字节都没有，契约的 ``/upload`` 条目里也没有。 """
import ast
import inspect
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import chat
from app.common import auth
from app.main import app
from scripts import seed_workspace
from test_r391_upload_refusal_reaches_the_exit import FakeRetriever, Store

REPO = Path(__file__).resolve().parents[1]
SEED_SCRIPT = "scripts/seed_workspace.py"
SEED_MANIFEST = "deploy/workspace-seed.json"
UPLOAD_PATH = "/api/v1/upload"
ADMIN = "r414-admin"
ACCOUNT_ID = "u-r414"
LONG_TEXT = "季度营收与毛利明细 " * 40
#: 派工令点名的那枚在册错误码：不许新造，不许改名。
SCOPE_CODE = "department_scope_required"


def _source_of(symbol: str) -> str:
    """按符号名现读一枚函数的源码文本（AST 现取，不抄行号）。"""
    tree = ast.parse(inspect.getsource(chat))
    node = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == symbol
    )
    return ast.unparse(node)


def _read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def _account(department: str) -> dict:
    return {
        "id": ACCOUNT_ID,
        "username": ADMIN,
        "role": "admin",
        "department": department,
        "status": "active",
    }


def make_client(monkeypatch, tmp_path, department: str) -> TestClient:
    """架一具离线的上传腿：真路由、真 catalog 代码，台账与 retriever 是替身。

    替身直接复用 R391 那套件（同一具假 store，不复制第二套平行实现）。一发模型都不打。
    """
    root = tmp_path / "docs"
    root.mkdir(parents=True, exist_ok=True)
    from app.agents import tools
    from app.documents import catalog

    monkeypatch.setattr(auth, "get_user", lambda username: _account(department) if username == ADMIN else None)
    monkeypatch.setattr(auth, "_db_ready", True, raising=False)
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(root))
    monkeypatch.setattr(chat, "_sess_conn", lambda: Store({"documents", "users"}))
    monkeypatch.setattr(chat, "retriever", FakeRetriever((True, "indexed")))
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: LONG_TEXT)
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root), raising=False)
    monkeypatch.setattr(catalog, "_initialized", False, raising=False)
    monkeypatch.setattr(catalog, "_conn", lambda: Store({"document_versions"}))
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    return TestClient(app, raise_server_exceptions=False)


def post_upload(client: TestClient, filename: str):
    """表单里**故意**写一枚空 department：出口该认的是主体，不是这一格。"""
    return client.post(
        UPLOAD_PATH,
        files={"file": (filename, b"payload bytes here", "text/plain")},
        data={"classification": "1", "department": ""},
        headers={"Authorization": "Bearer " + auth.create_token(ADMIN)},
    )


# ==================== 停手条件①：种子那条路会当场死 ====================


class _RefusingResponse:
    status_code = 422
    text = '{"detail":"department_scope_required"}'


class _RefusingSession:
    """只回答一件事：出口对这一发上传答 422。循环交给真 ``seed_documents`` 去跑。"""

    def __init__(self):
        self.posted = []

    def post(self, url, **kwargs):
        self.posted.append(url)
        return _RefusingResponse()


def test_the_seed_route_dies_the_day_the_upload_exit_answers_422(tmp_path):
    """反证形状：出口一旦拒收空部门，``seed_documents`` 就是 SeedError，不是「少传几篇」。"""
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    names = ["2026年Q1经营分析报告.txt", "员工手册_2025正式版.txt"]
    for name in names:
        (corpus / name).write_bytes("正文待上传".encode("utf-8"))
    session = _RefusingSession()

    with pytest.raises(seed_workspace.SeedError) as raised:
        seed_workspace.seed_documents(
            session, "http://seed.test", [corpus / name for name in names], 1, False
        )

    message = str(raised.value)
    assert "422" in message, message
    assert SCOPE_CODE in message, "拒收要讓跑分窗看得见为什么被拒：" + message
    assert session.posted == ["http://seed.test/api/v1/upload"], (
        "第一枚就该死在这里；传了两枚说明 SeedError 不是当场抛的：" + repr(session.posted))


def test_the_seed_plan_still_counts_a_hundred_documents(tmp_path):
    """``plan_documents`` 现读：清单点名的 100 篇全落在「盘上有、服务上没有」那一桶。

    这一桶就是拒收一旦生效要死的那 100 篇 —— 种子不会带着 422 继续往下灌，它当场抛。
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    for name in _manifest()["documents"]["files"]:
        (corpus / name).write_bytes("正文待上传".encode("utf-8"))

    wanted, absent, already, server_only = seed_workspace.plan_documents(_manifest(), corpus, set())

    assert len(wanted) == 100, (len(wanted), absent[:3], already[:3])
    assert absent == [] and already == [] and server_only == []


def _manifest() -> dict:
    return json.loads((REPO / SEED_MANIFEST).read_text(encoding="utf-8"))


# ==================== 停手条件①的结构前提：种子走的就是无部门的管理员 ====================


def _main_function() -> ast.FunctionDef:
    tree = ast.parse(_read(SEED_SCRIPT))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )


def test_the_corpus_is_uploaded_by_the_administrator_session():
    """AST 现读：``seed_documents`` 吃的那枚 session，正是 ``_admin_token`` 那一条腿建起来的。"""
    main = _main_function()
    admin_sessions = {
        node.targets[0].id
        for node in ast.walk(main)
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", "") == "_session"
        and any(
            isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "_admin_token"
            for arg in node.value.args
        )
    }
    assert admin_sessions, "读不到「管理员 session」那一行：种子的凭据路线变了"

    seeded = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "seed_documents"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in admin_sessions
    ]
    assert seeded, "语料不再由管理员 session 上传：停手条件①的前提变了，本单要重裁"


def test_the_manifest_keeps_the_administrator_department_free():
    """清单现读：管理员不在 ``owners`` 里，文档那一节也不点名任何属主或部门。"""
    manifest = _manifest()

    assert "department-free" in manifest["_comment"], (
        "清单不再声明「管理员故意不挂部门」：停手条件①的前提变了，本单要重裁")
    assert "财务部" in {spec.get("department") for spec in manifest["owners"]}
    assert ADMIN not in {spec.get("username") for spec in manifest["owners"]}
    assert not ({"owner", "department"} & set(manifest["documents"])), (
        "文档那一节开始点名部门了：种子不再依赖上传人的部门，本单判据要重写")
    assert len(manifest["documents"]["files"]) == 100, (
        "语料枚数漂了：跑分窗 P-9 的门牌要跟着改")


# ==================== 停手条件③：同名重传今天能用，部门跟着这一次上传人走 ====================


def test_the_documents_upsert_overwrites_the_department_per_upload():
    """``_upsert_document`` 的 ON CONFLICT 里带着 ``department = EXCLUDED.department``。

    也就是说 ``documents.department`` 记的是**最后一次把它传上来的那个人**的部门：拒收一旦生效，
    无部门管理员连「把既有文档再传一遍」都做不到，而不只是「新增不了」。
    """
    source = _source_of("_upsert_document")

    assert "ON CONFLICT (filename) DO UPDATE" in source, source[:400]
    assert "department = EXCLUDED.department" in source, source[:400]


def test_the_upload_exit_does_not_refuse_a_department_free_principal_today(monkeypatch, tmp_path):
    """现状读数：出口对空部门主体答 200，回执那一格就是空串。

    这一枚钉的是今天的事实，不是替它背书：它红起来的唯一方式就是有人真把拒收加了进来，那时候
    本件那三条开工条件必须一起重裁（``test_the_seed_route_dies_...`` 会先它一步红）。
    """
    client = make_client(monkeypatch, tmp_path, department="")

    response = post_upload(client, "r414-empty-department.txt")

    assert response.status_code == 200, (response.status_code, response.text[:240])
    assert response.json()["department"] == "", response.json()
    assert SCOPE_CODE not in response.text, "出口偷偷兜住了那一格：拒收其实落地了"


def test_the_same_name_can_be_uploaded_twice_by_that_principal(monkeypatch, tmp_path):
    """停手条件③的另一半：同名重传今天是通的（版本号往上走，不被部门那一格拦住）。"""
    client = make_client(monkeypatch, tmp_path, department="")

    first = post_upload(client, "r414-reupload.txt")
    second = post_upload(client, "r414-reupload.txt")

    assert first.status_code == 200 and second.status_code == 200, (
        first.status_code, first.text[:200], second.status_code, second.text[:200])
    first_body, second_body = first.json(), second.json()
    assert first_body["filename"] == second_body["filename"] == "r414-reupload.txt"
    assert second_body["stored_name"] and second_body["stored_name"] != first_body["stored_name"], (
        "第二发同名上传没有落成新的一版：停手条件③的现场没了"
    )
    assert first_body["department"] == "" and second_body["department"] == ""


# ==================== 出口形状：真落地时必须走具名码，不许造第二枚 ====================


def test_the_registered_scope_code_is_not_emitted_from_the_upload_exit():
    """在册码名唯一的出处仍是 ``app/api/v1/data.py``；本件没在 ``chat.py`` 里新增任何吐口。

    这一枚红起来只有两种可能：有人落地了 A2（那得先过本单三条停手条件），或者有人在这枚文件里
    造了第二枚同族码名 —— 派工令明令不许新造码、不许改码名。
    """
    from app.agents import contracts

    assert SCOPE_CODE in _read("app/agents/contracts.py"), "封闭枚举里不该丢掉这枚码"
    assert SCOPE_CODE in _read("app/api/v1/data.py"), "在册出处被人摘了：追认表要红"
    assert SCOPE_CODE not in _read("app/api/v1/chat.py"), (
        "chat.py 里出现了这枚码名：说明 A2 绕开本单落地了")

    contract = _read("docs/api/contract-v1.md")
    assert contract.count(SCOPE_CODE) == 1, (
        "这枚码在契约里多了一处出处：/upload 那一条今天不许登记拒收")
    line = next(one for one in contract.splitlines() if SCOPE_CODE in one)
    assert line.strip() == "- `" + SCOPE_CODE + "`", (
        "那唯一一处也不是封闭枚举里的码名，而是别处：" + line)
