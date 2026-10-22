# -*- coding: utf-8 -*-
r"""R391 · 上传这条腿上，存储的具名拒答必须走到 HTTP 出口（治 R383 结转给下一班的那一格）。

## 判据① 取证表（行号一律本树基点 `903765b` 现读；状态码一律 `TestClient(app, raise_server_exceptions=False)` 现场）

链路：`app/api/v1/chat.py::_record_uploaded_version:3644` → `if catalog_database_available():3673`
→ 归属腿 `try: _upsert_document:3674-3684`（`except Exception` + `[Docs] metadata sync failed`）
→ 版本腿 `try: record_document_version:3685-3698` → `except Exception as exc:3699` + `logger.warning:3700`
+ **`return metadata:3701`**。四枚调用点：`:4140`（解析失败支，返回值不进响应）、`:4166`（策略排除支）、
`:4216`（`ok` 支）、`:4305`（索引拒收但保留文件支）；后三枚把返回值当 `version_meta` 拼进
`_document_upload_result:4005`。

🔴 **先更正派工词一格**（量出来的，不是照抄）：派工说"那一闸在上传这条腿上从来没到过 HTTP 出口"，
实测**只对一半**。生产 + 缺 `document_versions`（态 B）与生产 + 库没起（态 C）这两格，上传今天在出口
**就是** 503、且**一个字节都不落**：`chat.py:4087` 的 `peek_next_document_version` 排在落盘之前，而它自己
带着 R383 那道闸（`app/documents/catalog.py:605`，缺表时经 `:617-618` 再进一次）。四枚调用点逐枚实测
503 + 零文件（`test_production_with_a_missing_ledger_...` / `..._postgres_down_...`）。
闸真没接到出口的只有**第三格**：版本腿自己抛出的那一枚。

| 态 | 构造 | `:4140` | `:4166` | `:4216` | `:4305` | 修前 ⇒ 修后 |
| --- | --- | --- | --- | --- | --- | --- |
| A 生产·迁移齐 | `_db_ready=True` + 表在 | 500 parse | 200 skipped/excluded | 200 ok/indexed | 200 skipped/excluded | 逐格同 ⇒ 同（零漂移） |
| B 生产·缺表 | `_db_ready=True` + 表不在 | 503 | 503 | 503 | 503 | 同 ⇒ 同（peek 先拒） |
| C 生产·库没起 | `_db_ready=False` | 503 | 503 | 503 | 503 | 同 ⇒ 同（peek 先拒） |
| **D 生产·版本腿才拒** | peek 那次连接超时 ⇒ 回落本地台账；表却真不在 | **500** | **200 ok** | **200 ok** | **200 skipped** | 🔴 四枚假回执 ⇒ **503 ×4** |
| E 开发·无 PG（裸机/离线） | 非生产 | 500 | 200 | 200 | 200 | 同 ⇒ 同 |
| F 开发·库在表缺 | 非生产 | 500 | 200 | 200 | 200 | 同 ⇒ 同 |
| G 开发·连接超时 | 非生产 | 500 | 200 | 200 | 200 | 同 ⇒ 同 |

D 态不需要 patch 任何 chat 内部量，所以它就是生产现场。旗标竞态**不是**入口条件：`_database_available()`
读 `app/common/auth.py:467` 那枚 `_db_ready`，而 R230 之后运行期只许 False→True、永不反向
（`auth.py:237` 提前 return，注释见 `:231`）——所以"chat 以为库在、catalog 以为库不在"这一格结构上走不到，
本单也不靠它。真开着的是**时间窗**：`peek:4087`（落盘之前）撞上一次连接失败（`catalog._conn` 的
`connect_timeout=1`）⇒ `catalog.py:616-620` 按既有设计回落本地台账推版本号 ⇒ 上传继续（解析＋索引，秒级）
⇒ 版本腿 `catalog.py:733` 的闸放行（旗标仍 True）、`:734` 先写完 sidecar、`:739` `_ensure()` 现查出表不在
⇒ `:769-770` 带 `migrations_missing` 进闸 ⇒ **`:405` 抛出那枚具名 503** ⇒ 落到 `chat.py:3699` 的
`except Exception` 上被吃掉 ⇒ `return metadata:3701` ⇒ 回执 `status:"ok"`。同一发请求里日志连着两句：
闸自己说 `operation=version record code=storage_unavailable`，出口说 `[Docs] version record failed:
503: storage_unavailable`。派工词里那句"仍答成功、版本号是本地台账推出来的"——**版本号那一半对，
`document_versions` 那一半在 D 态对**（sidecar 写了、权威表没写，见
`test_the_refusal_leaves_the_local_mirror_written_...`）。

`:3701` 那份 dict 与真落库那份差哪几格（现测，`chat.py:3666-3672` vs `catalog._version_metadata:640-652`）：
交出 **5** 格（`version / size_bytes / parse_status / index_status / index_reason`），真落库交 **11** 格，
**少 `filename`、`classification`、`department`、`owner_id`、`storage_path`、`created_at` 六格**；共有五格
逐格等值 ⇒ **回执上看不出任何差别**（`_document_upload_result:4038-4040` 只读其中三格）。这就是它能长期
装成功的结构性原因。`:4236` 的 `_document_resource_scope` 确实读少了的那几格（owner/department/classification
⇒ `None`），但它下游 `_document_publication:3782-3791` 只取 `visibility / department_ids / status` 三格，
那三格两份 dict 里都没有、两边同样落默认值 ⇒ **授权投影今天没有被本单改变**（如实记，不冒充战果）。

版本号是谁算的（派工点名要量清的那格）：`version=next_version` 来自 `:4087`；D/E/G 三态里它是
`catalog.py:620` 用 `_local_version_rows()` 现推的 `max+1`（`catalog.py:43-45`）。**本地台账一丢就重号**：
`test_a_locally_derived_version_can_be_written_over_an_older_real_row` 量到——真库里有行时 peek 因一次
连接失败回本地台账 ⇒ 推出 `1` ⇒ `record_document_version` 发的正是 `INSERT ... ON CONFLICT (filename,
version) DO UPDATE`（`catalog.py:743-753`）⇒ 旧版本那行的 `storage_path / created_at / parse_status`
被新版本覆盖。治它要动 `app/documents/catalog.py`（本单禁写域）⇒ **只报不改**（回执⑤）。

## 判据② 改法：只做穿透，不做翻译（`+10 -0`，纯追加）

版本腿加一枚 `except HTTPException: raise`。穿透而非翻译：零新增错误码/reason/status 档位，
`status_code=503` 抛出点仍**恰 6 枚**、归属名单一字不改（`test_the_503_ledger_...`；总控派工给的
`:4745/:4788/:4815` 三枚因本单 +10 行漂到 `:4755/:4798/:4825`，行号不进断言）。归属腿
（`_upsert_document` 那一支）连同它那句 warning **一字未动**：`test_the_three_pre_existing_legs_...`
拿基点 `903765b` 的 blob 现算三支形状再逐支比，被摘/被改当场红。`RuntimeError("db down")` 那种
"台账挂了但文件收了"的既有裁定（`tests/test_document_upload_resilience.py:103`）仍答 200，
反证刀 K2 就是量这一格越界的。

**为什么具名的那一枚是 `HTTPException` 而不是派工词里的 `CatalogStoreNotMigrated`**：全仓
`rg CatalogStoreNotMigrated` **零命中（rc=1）**——R383 回执写了这个名，落树的字节里 `catalog.py` 只有一枚
`raise HTTPException(status_code=503, detail="storage_unavailable")`（`:405`），而它的抛出点唯一性由
`test_the_store_still_raises_its_http_exception_in_exactly_one_place` 钉住；改 `catalog.py` 造一枚具名类
= 撞禁写域。所以"具名穿透"这一格今天只能按字节实现成"接 `HTTPException` 这一种、体内只有 `raise`"，
并额外钉住"catalog 全模块只此一枚 HTTPException"——它保证今天的穿透面恰等于存储拒答面。

**文件留不留：留。** 与 `:4136-4139`（解析失败留文件答 500）同向，与 `:4211-4213`（索引失败删文件并 500）
反向。两枚先例的分界不在"留不留"，在**哪一层失败**：`:4211` 是摄取流水线自己失败，索引里一份都没有，删掉
不损失任何证据；本单这一格是摄取全部成功、只有台账拒绝落行，而 `:4216` 那一支正文已经在索引里 ——
删文件会留下"索引里有、盘上没、两本账里都没行"的三份不一致，并把平台自己的故障成本折进客户的数据。
私有化部署那句"数据不出客户机器"在这里读作"不替客户的机器做删除决定"。代价如实写（回执⑥）：迁移补齐后
重试会在盘上留下前一发的孤儿文件，今天没有任何一条腿会去索引它。钉：`test_the_stored_file_survives_...`。

盘上卫生：本件对被跟踪文件零写口（`tmp_path` 替身台账），变异全部在内存里（R253 口径）。

🔴 R397 追加的更正（不删本件原始读数，只登记它过期）：上面判据②那句「`status_code=503` 抛出点仍**恰
6 枚**」从今天起不再成立——R397 把 `GET /sessions` 与 `GET /sessions/{id}` 两枚读腿折成 503，门账
6 ⇒ 8。本件的口径因此改成**派生**：名单由 AST 现查，钉「R391 的两枚宿主函数不在名单里」加「基点在册
的出口一枚没被拆」，不再钉枚数；K4b 那把也从「变异之后恰 7 枚」换成「变异必须长出一枚词汇表之外的新
detail」这一枚不变式。R391 那一发穿透本身一字未动。
"""
import ast
import re
import subprocess
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from app.agents.contracts import ErrorEnvelope
from app.api.v1 import chat
from app.common import auth
from app.documents import catalog
from app.main import app

REPO = Path(__file__).resolve().parents[1]
BASE = "903765b"
CHAT_REL = "app/api/v1/chat.py"
CATALOG_REL = "app/documents/catalog.py"
FUNCTION = "_record_uploaded_version"
GATE = "_require_ready_store"

#: R391 自己的两枚宿主函数。本单的口径是「新增的是穿透，不是 503」，所以钉的不是门账今天有几枚，
#: 而是这两枚名字**不许出现在** AST 现查出来的 503 出口名单里（派生口径见下面那格的 docstring）。
#: 为什么不是为了让门绿：`== 6` 是 R391 当天的现场，R397 把两枚会话读腿折成 503 之后门账已是 8 枚，
#: 换成 `== 8` 只是把同一笔债搬到下一单——枚数交给派生，账上只留「谁不许长出口」这句人写的理由。
R391_OWNED_EXIT_HOSTS = {FUNCTION, "upload_document"}
UPLOAD_PATH = "/api/v1/upload"
ADMIN = "r391-admin"
ACCOUNT = {"id": "u-r391", "username": ADMIN, "role": "admin", "department": "finance", "status": "active"}

#: 三支既有 except 各自的日志前缀：这是客户/运维看得见的字面量，钉它等于钉"那一支还在原地容忍"。
#: （同一枚前缀 R384 早已钉过一次，账在 R384 件里那枚 `test_the_upload_metadata_leg_still_answers_200_...`。）
#: 按符号名记这笔账、不抄行号：行号每演进一次红一次，那是 R346/R351 已经点过名的族病。
ATTRIBUTION_WARNING = "metadata sync failed"
VERSION_WARNING = "version record failed"
LOCAL_WARNING = "local version record failed"

LONG_TEXT = "季度营收与毛利明细 " * 40
SHORT_TEXT = "abc"

_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)
_DML = re.compile(r"(?:FROM|INTO|UPDATE)\s+([A-Za-z_]\w*)", re.IGNORECASE)
_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)

CLAUSE = (
    "        except HTTPException:\r\n"
    "            # 存储自己已经报过脸了（R383 那道闸：生产 + 目录存储没起 = 具名 503）。吃掉它就是把\r\n"
    "            # 「这一版没落账」翻译成 200，所以原样上抛，由出口作答；本模块不新增第二枚 503。\r\n"
    "            raise\r\n"
)


# ------------------------------------------------------------------ 替身台账
class Store:
    """只回答两件事：那一次 `to_regclass` 现查怎么说，以及这一次连接要不要失败。

    不求值真 SQL、不连库、不起服务、不碰模型端口（R384 的口径）。`fail_next_connect` 复现的正是
    `catalog._conn` 那枚 `connect_timeout=1` 在生产高峰偶发的第一次失败 —— D 态的入口。
    """

    def __init__(self, tables=(), fail_next_connect=False):
        self.tables = {str(t).lower() for t in tables}
        self.fail_next_connect = fail_next_connect
        self.statements: list[str] = []
        self.rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        if self.fail_next_connect:
            self.fail_next_connect = False
            raise errors.OperationalError("connection timeout")
        found = _REGCLASS.search(text)
        if found:
            name = found.group(1).lower()
            self.rows = [{"table_name": name if name in self.tables else None}]
            return self
        created = _CREATE.search(text)
        if created:
            self.tables.add(created.group(1).lower())
            self.rows = []
            return self
        referenced = _DML.search(text)
        if referenced and referenced.group(1).lower() not in self.tables:
            raise errors.UndefinedTable('relation "%s" does not exist' % referenced.group(1))
        self.rows = []
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def inserts(self, table: str) -> int:
        needle = ("INSERT INTO " + table).upper()
        return sum(1 for text in self.statements if text.upper().startswith(needle))


class Recorder:
    """出口与 store 的日志共用一具记录器：三张脸分不分得开，今天只有这一处证据。"""

    def __init__(self):
        self.lines: list[str] = []

    def _record(self, message):
        self.lines.append(str(message))

    def debug(self, message, *args, **kwargs):
        self._record(message)

    def info(self, message, *args, **kwargs):
        self._record(message)

    def warning(self, message, *args, **kwargs):
        self._record(message)

    def error(self, message, *args, **kwargs):
        self._record(message)

    def exception(self, message, *args, **kwargs):
        self._record(message)

    def mentions(self, needle: str) -> list[str]:
        return [line for line in self.lines if needle in line]


class FakeRetriever:
    def __init__(self, outcome=(True, "indexed")):
        self.outcome = outcome

    def add_document(self, filename, content, classification, department):
        return self.outcome

    def list_documents(self):
        return []


SITE_PARSE_FAILED = "4140_parse_failed"
SITE_EXCLUDED = "4166_policy_excluded"
SITE_OK = "4216_indexed_ok"
SITE_REFUSED = "4305_index_refused"
SITES = (SITE_PARSE_FAILED, SITE_EXCLUDED, SITE_OK, SITE_REFUSED)

#: 非生产三态逐格实测的脸（基点与现树各跑一遍，两遍同数才能进这张表）。
NONPROD_FACE = {
    SITE_PARSE_FAILED: (500, {"detail": "document_parse_failed"}, None),
    SITE_EXCLUDED: (200, {"status": "skipped", "index_status": "excluded"}, 1),
    SITE_OK: (200, {"status": "ok", "index_status": "indexed"}, 1),
    SITE_REFUSED: (200, {"status": "skipped", "index_status": "excluded"}, None),
}


def world(monkeypatch, tmp_path, *, env, db_ready, versions_present, blip, site):
    """架一具离线的上传：真路由、真中间件、真 catalog 与真 chat 代码；只有台账与 retriever 是替身。"""
    from app.agents import tools

    root = tmp_path / "docs"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(root))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(root), raising=False)
    monkeypatch.setattr(catalog, "_initialized", False, raising=False)
    monkeypatch.setattr(auth, "_db_ready", db_ready, raising=False)
    store = Store({"document_versions"} if versions_present else set(), fail_next_connect=blip)
    monkeypatch.setattr(catalog, "_conn", lambda: store)
    monkeypatch.setattr(chat, "_sess_conn", lambda: Store({"documents", "users"}))
    monkeypatch.setenv("APP_ENV", env)
    log = Recorder()
    monkeypatch.setattr(chat, "logger", log)
    monkeypatch.setattr(catalog, "logger", log, raising=False)
    monkeypatch.setattr(chat, "retriever", FakeRetriever(
        (False, "embedding backend unavailable") if site == SITE_REFUSED else (True, "indexed")))
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    if site == SITE_PARSE_FAILED:
        def boom(path, display_name=None):
            raise RuntimeError("cannot parse this")
        monkeypatch.setattr(chat, "load_document", boom)
    else:
        text = SHORT_TEXT if site == SITE_EXCLUDED else LONG_TEXT
        monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: text)
    return root, store, log


def upload(site, *, token=True):
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": "Bearer " + auth.create_token(ADMIN)} if token else {}
    response = client.post(
        UPLOAD_PATH,
        files={"file": (site + ".txt", b"payload bytes here", "text/plain")},
        data={"classification": "2", "department": ""},
        headers=headers,
    )
    try:
        return response, response.json()
    except Exception:
        return response, None


# ------------------------------------------------------------------ 形状尺（不抄行号、不抄源文本）
def working_text(rel: str) -> str:
    """按盘上字节形读（`newline=""`）：不折叠 CRLF，这样"变异能落进原文"同时是一枚行尾卫生钉。"""
    with open(REPO / rel, encoding="utf-8", newline="") as handle:
        return handle.read()


def base_text(rel: str) -> str:
    """基点 `903765b` 的那一份原文，从对象库现读（git 只读调用，零写 index）。"""
    out = subprocess.run(
        ["git", "-c", "core.pager=cat", "show", BASE + ":" + rel],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def function(tree_: ast.Module, name: str):
    for node in ast.walk(tree_):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError("%s 不在了" % name)


def leg_facts(text: str) -> dict:
    """`_record_uploaded_version` 每一支 except 的形状：类型 + 体内语句（AST 归一，不看引号与空白）。"""
    route = function(ast.parse(text), FUNCTION)
    legs: dict[str, tuple] = {}
    for handler in sorted((h for h in ast.walk(route) if isinstance(h, ast.ExceptHandler)),
                          key=lambda h: h.lineno):
        body = tuple(ast.unparse(stmt) for stmt in handler.body)
        joined = " ".join(body)
        if ATTRIBUTION_WARNING in joined:
            name = "attribution"
        elif LOCAL_WARNING in joined:
            # 判序要紧：LOCAL_WARNING 字面上含着 VERSION_WARNING，先短后长会互相顶替。
            name = "local_tolerance"
        elif VERSION_WARNING in joined:
            name = "version_tolerance"
        elif body == ("raise",):
            name = "passthrough"
        else:
            name = "unknown_%d" % handler.lineno
        assert name not in legs, "同-shaped 的两支：分类器要重画 " + name
        legs[name] = (ast.unparse(handler.type) if handler.type else None, body)
    return legs


def raise_sites(text: str, status: int) -> list[tuple[str, int]]:
    tree_ = ast.parse(text)
    owners: list[tuple[str, int]] = []
    for scope in ast.walk(tree_):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(scope):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                    and getattr(node.exc.func, "id", "") == "HTTPException":
                for keyword in node.exc.keywords:
                    if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant) \
                            and keyword.value.value == status:
                        owners.append((scope.name, node.lineno))
    return owners
def details_of_503(text: str) -> set[str]:
    """现查 `chat.py` 全部 503 出口的 detail 形状（字面量取值，非常量取 AST 归一文面）。

    为什么不是为了让门绿：反证刀 K4b 的旧口径是「变异之后门账 == 7」，那是一枚绝对数，R397 之后
    门账已是 8 枚——写 9 也只是把债搬到下一单。改成派生集合的差：变异必须**长出一枚新的 detail**，
    而那枚新 detail 必须落在 `ErrorEnvelope` 已批准词汇表之外，否则这枚哨兵就是哑的。派生数不到
    东西时当场红，不静默免检。
    """
    tree_ = ast.parse(text)
    shapes: set[str] = set()
    for scope in ast.walk(tree_):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(scope):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            if getattr(node.exc.func, "id", "") != "HTTPException":
                continue
            keywords = {kw.arg: kw.value for kw in node.exc.keywords}
            status = keywords.get("status_code")
            if not (isinstance(status, ast.Constant) and status.value == 503):
                continue
            detail = keywords.get("detail")
            if detail is None:
                shapes.add("<no-detail>")
            elif isinstance(detail, ast.Constant):
                shapes.add(str(detail.value))
            else:
                shapes.add(ast.unparse(detail))
    return shapes


def store_gate_detail() -> str:
    """那一枚 503 的 detail 从 `catalog._require_ready_store` 现场取（R366 的口径，不抄字面量）。"""
    gate = function(ast.parse(working_text(CATALOG_REL)), GATE)
    for node in ast.walk(gate):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) \
                and getattr(node.exc.func, "id", "") == "HTTPException":
            for keyword in node.exc.keywords:
                if keyword.arg == "detail":
                    return keyword.value.value
    raise AssertionError("catalog 的闸不再抛 detail 了：本单的前提变了")


BASE_LEGS = leg_facts(base_text(CHAT_REL))
HONEST = leg_facts(working_text(CHAT_REL))
#: 基点那三支的形状快照。本单唯一允许多出来的一支叫 `passthrough`。
PRE_EXISTING_LEGS = ("attribution", "version_tolerance", "local_tolerance")


# ================================================================== 判据①：三张脸
@pytest.mark.parametrize("site", SITES)
def test_production_with_a_missing_ledger_refuses_before_a_single_byte(site, monkeypatch, tmp_path):
    """态 B：生产 + 缺表。`peek` 排在落盘之前 ⇒ 今天就是 503 且零文件（修前修后同脸，不许退）。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=False, blip=False, site=site)
    response, body = upload(site)
    assert response.status_code == 503, response.text
    assert body == {"detail": store_gate_detail()}, body
    assert list(root.iterdir()) == [], "这一态必须一字节不落"
    assert log.mentions("operation=version peek"), log.lines


@pytest.mark.parametrize("site", SITES)
def test_production_with_postgres_down_refuses_before_a_single_byte(site, monkeypatch, tmp_path):
    """态 C：生产 + 库没起。同一道闸的另一张脸，句子是"PG 未起"而不是"缺表"。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=False,
                             versions_present=False, blip=False, site=site)
    response, body = upload(site)
    assert response.status_code == 503, response.text
    assert list(root.iterdir()) == [], "这一态必须一字节不落"
    assert log.mentions("（PG 未起）"), log.lines


@pytest.mark.parametrize("site", SITES)
def test_a_migrated_production_upload_still_lands_and_still_answers(site, monkeypatch, tmp_path):
    """态 A：生产 + 迁移齐。这一格今天就好，本单一个字不许动它。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=True, blip=False, site=site)
    response, body = upload(site)
    assert store.inserts("document_versions") == 1, store.statements
    if site == SITE_PARSE_FAILED:
        assert (response.status_code, body) == (500, {"detail": "document_parse_failed"}), body
        return
    expected = {"status": NONPROD_FACE[site][1]["status"], "index_status": NONPROD_FACE[site][1]["index_status"]}
    assert response.status_code == 200, response.text
    assert {key: body[key] for key in expected} == expected, body
    assert body["version"] == 1, body
    assert not log.mentions(GATE), log.lines


# ------------------------------------------------- 判据①/②：D 态，本单治的那一格
@pytest.mark.parametrize("site", SITES)
def test_the_store_refusal_at_the_version_leg_reaches_the_exit_at_every_call_site(site, monkeypatch, tmp_path):
    """🔴 本单第一交付物：修前 `:4166/:4216` 答 200 ok、`:4305` 答 200 skipped、`:4140` 答 500。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=False, blip=True, site=site)
    response, body = upload(site)

    assert log.mentions("operation=version record"), log.lines
    assert response.status_code == 503, (site, response.text)
    assert body == {"detail": store_gate_detail()}, body
    assert store.inserts("document_versions") == 0, store.statements
    assert "version" not in body and "stored_name" not in body, "503 不许带一份版本号回执"
    assert not log.mentions(VERSION_WARNING), "被吃掉那一句必须消失：闸的脸不再进容忍腿"


def test_a_real_bug_in_the_version_leg_still_answers_the_pinned_200(monkeypatch, tmp_path):
    """真 bug 不许被折成拒答：版本腿抛非具名异常时，既有容忍原样保住（`test_document_upload_resilience:103` 那条裁定）。

    这一枚是刀2 的面级牙：把穿透的类型从 `HTTPException` 放宽成 `Exception`，出口立刻从 200 变成
    一发无码无 reason 的裸 500（`app/**` 零 `exception_handler`）—— 那就是 R381 说的"替真正的 bug 打掩护"。
    """
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=True, blip=False, site=SITE_OK)

    def real_bug(*args, **kwargs):
        raise KeyError("somebody indexed an empty catalog row")

    monkeypatch.setattr(chat, "record_document_version", real_bug)
    response, body = upload(SITE_OK)

    assert response.status_code == 200, response.text
    assert body["status"] == "ok" and body["version"] == 1, body
    assert len(log.mentions(VERSION_WARNING)) == 1, log.lines
    assert not log.mentions("storage_unavailable"), "真 bug 不许长出一张拒答的脸"


@pytest.mark.parametrize("site", SITES)
def test_the_stored_file_survives_the_refusal(site, monkeypatch, tmp_path):
    """裁定：拒答不许删文件。四枚调用点全部留文件（理由与两枚相反先例的分界见文件头）。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=False, blip=True, site=site)
    upload(site)
    stored = [p for p in root.iterdir() if p.suffix == ".txt"]
    assert len(stored) == 1, [p.name for p in root.iterdir()]
    assert stored[0].name != site + ".txt", "留的是落盘名，不是客户路径"


def test_the_refusal_leaves_the_local_mirror_written_but_no_authoritative_row(monkeypatch, tmp_path):
    """半态如实登记：sidecar 那一行写了（`catalog.py:734` 排在现查之前），权威表没写。

    这一格不是本单造成的，本单只是不再给它盖一份回执。生产读侧走 `document_versions`，
    所以"文件收了、账没落"从今天起是拒答，而不是一句 ok。
    """
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=False, blip=True, site=SITE_OK)
    upload(SITE_OK)
    assert (root / ".document-versions.json").exists(), "sidecar 落在闸之前，今天就是这样"
    assert store.inserts("document_versions") == 0


def test_the_swallowed_receipt_dropped_six_fields_that_the_honest_one_carries():
    """两枚 return 的差格逐枚点名（`chat.py:3666-3672` vs `catalog._version_metadata:640-652`）。"""
    honest = catalog._version_metadata(
        "policy.txt", 2, "finance", "nowhere.txt", 4, None, "u-1", 720, "ready", "indexed", "")
    carried = {"version", "size_bytes", "parse_status", "index_status", "index_reason"}
    assert carried <= set(honest)
    assert sorted(set(honest) - carried) == [
        "classification", "created_at", "department", "filename", "owner_id", "storage_path",
    ]


def test_a_locally_derived_version_can_be_written_over_an_older_real_row(monkeypatch, tmp_path):
    """只报不改（治它要动禁写域）：peek 回落本地台账 ⇒ 号从 1 重来 ⇒ ON CONFLICT 覆盖旧行。"""
    root, store, log = world(monkeypatch, tmp_path, env="production", db_ready=True,
                             versions_present=True, blip=True, site=SITE_OK)
    assert catalog.peek_next_document_version("policy.txt") == 1, log.lines
    assert log.mentions("version lookup fallback"), log.lines
    catalog.record_document_version("policy.txt", classification=2, department="finance",
                                    storage_path=str(root / "x.txt"), version=1)
    assert any("ON CONFLICT (filename, version) DO UPDATE" in text for text in store.statements), store.statements


# ============================================================ 判据②：三条腿一字未变
@pytest.mark.parametrize("env,db_ready,versions_present,blip", [
    ("development", False, False, False),   # E 裸机/离线
    ("development", True, False, False),    # F 库在表缺
    ("development", True, False, True),     # G 连接超时
])
@pytest.mark.parametrize("site", SITES)
def test_the_non_production_faces_are_the_same_table_as_before(env, db_ready, versions_present, blip,
                                                               site, monkeypatch, tmp_path):
    """开发/裸机/离线三态：状态码与回执逐格等于基点实测，一格都不许漂。"""
    root, store, log = world(monkeypatch, tmp_path, env=env, db_ready=db_ready,
                             versions_present=versions_present, blip=blip, site=site)
    response, body = upload(site)
    status, subset, _ = NONPROD_FACE[site]
    assert response.status_code == status, (site, response.text)
    assert response.headers["content-type"].startswith("application/json")
    if status == 500:
        assert body == subset, body
    else:
        assert {key: body[key] for key in subset} == subset, body
    assert not log.mentions(GATE), "非生产一条腿都不许进闸"
    assert len([p for p in root.iterdir() if p.suffix == ".txt"]) == 1, "非生产不许删文件"


def test_the_offline_world_records_through_the_sidecar_and_never_opens_the_gate(monkeypatch, tmp_path):
    """离线：`chat.py:3673` 那扇门外的那条腿（本地台账）连一行 SQL 都不该发。"""
    root, store, log = world(monkeypatch, tmp_path, env="development", db_ready=False,
                             versions_present=False, blip=False, site=SITE_OK)
    response, body = upload(SITE_OK)
    assert response.status_code == 200, response.text
    assert store.statements == [], store.statements
    assert body["version"] == 1


# ================================================== 判据②/③：形状与门账
def test_the_three_pre_existing_legs_keep_their_exact_base_shape():
    """三支既有 except 与基点逐支相等；本单唯一允许多出来的一支是穿透。"""
    assert BASE_LEGS["attribution"][0] == "Exception", "归属腿本来接的不是 Exception？前提变了"
    assert HONEST["attribution"] == BASE_LEGS["attribution"], "归属腿那支容忍被动了（本单明令一字不许动）"
    assert HONEST["version_tolerance"] == BASE_LEGS["version_tolerance"], "版本腿的宽捕获兜底被摘掉了"
    assert HONEST["local_tolerance"] == BASE_LEGS["local_tolerance"], "本地腿（离线）被顺手改了"
    assert sorted(HONEST) == sorted(list(BASE_LEGS) + ["passthrough"]), (sorted(BASE_LEGS), sorted(HONEST))


def test_the_passthrough_catches_exactly_one_named_type_and_only_raises():
    """出口只多一种"不接"：类型具名，体内只有 `raise`，不 new 信封、不补日志。"""
    assert HONEST["passthrough"] == ("HTTPException", ("raise",)), HONEST.get("passthrough")
    route = function(ast.parse(working_text(CHAT_REL)), FUNCTION)
    passthrough = [h for h in ast.walk(route) if isinstance(h, ast.ExceptHandler)
                   and h.type is not None and ast.unparse(h.type) == "HTTPException"]
    assert len(passthrough) == 1
    assert not [n for n in ast.walk(passthrough[0])
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "HTTPException"], "穿透里不许造信封"
    assert "logger." not in " ".join(HONEST["passthrough"][1]), "穿透里不许写日志（那是第二张脸）"


def test_the_attribution_warning_line_is_still_there_verbatim():
    """那句 warning 还在原地、还是一枚：它是 R384 存档钉的对象，也是"两支分得开"的字面证据。"""
    lines = working_text(CHAT_REL).splitlines()
    hits = [i + 1 for i, line in enumerate(lines) if ATTRIBUTION_WARNING in line]
    assert len(hits) == 1, hits
    assert "logger.warning" in lines[hits[0] - 1], lines[hits[0] - 1]


def test_the_503_ledger_stays_at_six_with_the_same_owners():
    """判据③：R391 不新增 503 出口——钉的是「名单里没有我」，不是名单今天有几枚。

    为什么不是为了让门绿：`== 6` 是 R391 当天的现场，R397 合法把两枚会话读腿折成 503 之后它必然
    过期，换成 `== 8` 只是把债搬到下一单。这格因此改成两句派生账：① 本单自己的两枚宿主函数
    （`R391_OWNED_EXIT_HOSTS`）在派生名单里一枚都不许出现——那才是「新增的是穿透，不是 503」；
    ② 名单只许变长不许变短，基点在册的出口被拆掉 = 有人顺手动了别人的出口。两头派生到空集都当场
    红，不搞「没数到所以免检」。函数名里的 `at_six` 是旧读数，留名只因契约按名字指它（改名要总控重登记）。
    """
    live = {name for name, _line in raise_sites(working_text(CHAT_REL), 503)}
    base = {name for name, _line in raise_sites(base_text(CHAT_REL), 503)}

    assert live, "chat.py 一枚 503 都数不到：尺子自己瞎了，不是没有出口要判"
    assert base, f"基点 {BASE} 的 chat.py 一枚 503 都数不到：派生的另一头也瞎了"
    owned = sorted(live & R391_OWNED_EXIT_HOSTS)
    assert not owned, f"R391 的腿自己长出了 503 出口：{owned}"
    withdrawn = sorted(base - live)
    assert not withdrawn, f"R391 那天在册的出口被拆掉了：{withdrawn}"


def test_no_error_code_or_status_tier_was_invented():
    """零新增码：出口那一句与仓里已批准的那一枚逐字相等，且新支里没有第二枚 detail。"""
    code = store_gate_detail()
    approved = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert code in approved, code
    route = function(ast.parse(working_text(CHAT_REL)), FUNCTION)
    details = [n for h in ast.walk(route) if isinstance(h, ast.ExceptHandler)
               and ast.unparse(h.type) == "HTTPException"
               for n in ast.walk(h) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert details == [], details


def test_the_store_still_raises_its_http_exception_in_exactly_one_place():
    """穿透面今天恰等于存储拒答面，因为 catalog 全模块只有一枚 HTTPException 抛出点、且长在闸里。

    哪天 catalog 长出第二种 HTTPException，这枚钉当场红，逼着下一班重读"穿透"的范围 ——
    那是 `except HTTPException: raise` 不退化成第二把宽捕获的唯一凭据。
    """
    tree_ = ast.parse(working_text(CATALOG_REL))
    raisers = [
        (scope.name, node.lineno)
        for scope in ast.walk(tree_) if isinstance(scope, ast.FunctionDef)
        for node in ast.walk(scope)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == "HTTPException"
    ]
    assert len(raisers) == 1, raisers
    assert raisers[0][0] == GATE, raisers


def test_the_module_defines_no_ninth_production_ruler():
    """`_is_production_environment` 全仓定义数仍为 8（有钉的账）；本单一个字都不新增。"""
    total = 0
    for path in (REPO / "app").rglob("*.py"):
        tree_ = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(1 for node in ast.walk(tree_)
                     if isinstance(node, ast.FunctionDef) and node.name == "_is_production_environment")
    assert total == 8, total


# ============================================== 常驻反证牙：形状尺必须真能咬（内存变异）
def _replace_clause(text: str, replacement: str) -> str:
    assert CLAUSE in text, "本单的穿透支不在原位：先重读，再改这把刀"
    return text.replace(CLAUSE, replacement, 1)


def mutate_removed(text: str) -> str:
    """刀1：摘掉刚加的具名穿透（= 退回修前）。"""
    return _replace_clause(text, "")


def mutate_widened(text: str) -> str:
    """刀2：把穿透的类型放宽成 `Exception`（= 任何 bug 都不再走容忍腿）。"""
    return _replace_clause(text, CLAUSE.replace("except HTTPException:", "except Exception:", 1))


def mutate_log_only(text: str) -> str:
    """假修复其一：只补一句 `logger.error`，脸不改，照旧回落成功回执。"""
    return _replace_clause(text, (
        "        except HTTPException as exc:\r\n"
        "            logger.error(f\"[Docs] catalog refused the version row: {exc}\")\r\n"
        "            return metadata\r\n"
    ))


def mutate_invented_code(text: str) -> str:
    """假修复其二：现造一枚新错误码（R380/R381/R383/R384 四连先例否掉的那件事）。"""
    return _replace_clause(text, (
        "        except HTTPException as exc:\r\n"
        "            raise HTTPException(status_code=503, detail=\"catalog_store_not_migrated\") from exc\r\n"
    ))


MUTATIONS = {
    "K1_removed": (mutate_removed, "passthrough"),
    "K2_widened": (mutate_widened, "passthrough"),
    "K4a_log_only": (mutate_log_only, "passthrough"),
    "K4b_new_code": (mutate_invented_code, "passthrough"),
}


@pytest.mark.parametrize("label", sorted(MUTATIONS))
def test_the_ruler_sees_every_way_this_fix_could_be_faked(label):
    """常驻反证：四枚变异各自必须把尺子判红，否则本单的钉是哑的（R351/R364 的口径）。"""
    mutate, key = MUTATIONS[label]
    facts = leg_facts(mutate(working_text(CHAT_REL)))
    # 尺子的判据是"那一支必须逐格等于具名 + 裸 raise"：类型被放宽成 Exception 也算不等，
    # 否则刀2（只改类型不改体）正好从"键在不在"这个洞漏出去。
    assert facts.get(key) != HONEST[key], "%s 没有被尺子看见：本单的钉咬不住它" % label
    assert facts["attribution"] == BASE_LEGS["attribution"], label + " 顺手改了归属腿"
    if label == "K2_widened":
        assert facts["version_tolerance"][0] == "Exception", facts["version_tolerance"]
    if label == "K4b_new_code":
        # 派生不变式，不抄绝对数：门账今天 8 枚，写死 7 或 9 都会随下一次加出口假红。
        # 要的是两件事：这把刀确实改出了新出口，且改出来的那枚 detail 不在已批准词汇表里。
        before = working_text(CHAT_REL)
        after = mutate(before)
        assert len(raise_sites(after, 503)) > len(raise_sites(before, 503)), "门账没长说明变异没落地"
        invented = details_of_503(after) - details_of_503(before)
        assert invented, "变异落地却没带出新 detail：这把刀没咬到东西"
        approved = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
        assert approved, "已批准词汇表派生到空集：尺子瞎了，不是没有码要判"
        assert invented - approved, (
            f"K4b 造出来的 detail 全在已批准词汇表里（{sorted(invented)}）："
            "这枚哨兵已经证不了「零新增错误码」，换一把没在册的码，别删格"
        )


def test_the_ruler_is_not_vacuous_on_the_honest_source():
    """尺子在真源码上必须给出那四支；少一支就是尺子自己瞎了。"""
    assert sorted(HONEST) == ["attribution", "local_tolerance", "passthrough", "version_tolerance"]
