# -*- coding: utf-8 -*-
r"""R384 · `run migrations first` 在 `chat.py` 的三枚调用点：逐格实量之后只治一格。

接单线索来自 R377（`96179ff`）的"只报不改 ③"。它只读到调用链、没跑探针，所以本件的第一交付物
是**现场状态码**：一律取自 ``TestClient(app, raise_server_exceptions=False)``，替身台账只对
「`to_regclass('public.x')` 这一次现查怎么答」与「缺表时 DML 怎么失败」作答，一个字都不求值真 SQL、
不连真库、不起服务、不碰模型端口。三态（库在且迁移齐 / PG 在但表缺 / PG 整个不在）各量一遍。

## 判据① 可达性表（行号在本单基点 `5ba73bd` 现取；形状一律走 AST 派生，不抄数）

| 调用点 | 抛出方 | 谁捕获 | 捕获后交出什么 | 生产·表缺 | 开发 | 离线 | 钉 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `_ensure_documents_table()` @ 模块导入期 | `:878` 现查缺 `documents` | 同一 `try` 的 ``except Exception: pass`` | 什么都不交，导入继续（原注释：上传时再懒建表） | 抛过一次、被吃、`reload` 实测成功（零出口） | 就地建表，不抛 | 外层 `if catalog_database_available()` 根本不进门（实测零语句） | 本件 |
| `_ensure_documents_table()` @ `_upsert_document` 内 | `:878` 同上 | `_record_uploaded_version` 的 ``except Exception as exc`` + `logger.warning` | **200**：文件收下、metadata 那一行没落 | `POST /upload` 实测 **200**，日志一句 `metadata sync failed: ... run migrations first` | 建表后正常落行 | 走 `record_local_document_version` 那一腿 | 本件存档，判据④只报不改 |
| `_ensure_sessions_table()` @ `ask()` | `:878` 现查缺 `sessions` / `session_messages` | **没人**（`app/**` 零 `exception_handler`，本件重新扫过） | —— | 修前实测 **500** `text/plain` `Internal Server Error`；修后 **503** `{"detail":"storage_unavailable"}` | 就地补 DDL 自愈，越过闸（哨兵 418） | 闸第一行 `return`，一次连接都不发 | 本件 |

🔴 R377 踩过的坑写在前面：它原判"这几枚会逃成裸 500"，实测方向是反的（吞掉之后交 200 空集）。
本单不复用那个结论。量下来三枚里**只有一枚今天真会裸 500** —— `ask()` 那一格，所以只治那一格；
另两枚逃不出去，判不可达，一个字不改（连"顺手也折成 503"都不做：那会推翻
`tests/test_document_upload_resilience.py` 钉着的「元数据库挂了也不丢文件」裁定，越出判据）。

## 只报不改（本单量到、但不在判据①那张表里的相邻形状）

- `_ensure_session()` @ `ask()`：把 `_ensure_sessions_table` 换成桩单量一格，生产 + 缺表 ⇒ **500**
  `text/plain`。抛它的是 `INSERT INTO sessions` 的 `UndefinedTable`，不是 `:878` 那句现查，所以不在
  "这一族"的账上；今天它被前面那道闸挡着（闸先抛），本单改完仍是闸先答 503，那一格不会因此露出来。
- `GET /sessions`：生产 + 缺表 ⇒ 实测 **500** `text/plain`（同一个 `UndefinedTable` 族）。它不是
  `_ensure_*` / `_require_migrated_tables` 调用点，不在表里，故只报。
- 效力边界：替身台账只回答"那一次现查怎么答"，所以本件证明的是**出口读到缺表时答什么**，不证明
  "跑 migrations 真能把那一格补出来"。
- 🔴 R391 追加的更正（不删本件原始读数，只登记它过期）：上面可达性表里 `_upsert_document` 那一行写的
  "`POST /upload` 实测 200"，从今天起不再是同一构造下整发上传的脸 —— 那一具替身台账里版本腿也会具名拒答，
  而 R391 不再让 `chat.py::_record_uploaded_version` 吃掉它，出口答 503。归属腿那一支的容忍一字未动
  （本件 `test_the_upload_metadata_leg_still_answers_200_when_documents_is_missing` 仍在数那一句 warning
  恰一枚、现查仍恰好走过 `documents`），改的只有"存储自己报过脸之后不许再盖成功回执"。新的钉：
  `tests/test_r391_upload_refusal_reaches_the_exit.py`（R391，基点即本 commit）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import errors

from app.api.v1 import chat
from app.common import auth
from app.main import app

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
CHAT = REPO / CHAT_REL
PROBE = "_require_migrated_tables"
FAMILY = "ChatSchemaNotMigratedError"
SENTENCE = "run migrations first"
STORAGE_CODE = "storage_unavailable"
BARE_500_BODY = "Internal Server Error"

#: 只在测试里出现的哨兵：证明请求**越过了**那道现查闸，而不是被闸拒答。产品侧一个字节都不认识它
#: （判据③不许新增 status 档位，所以 418 绝对不许出现在 app/** —— 由形状钉复核 503 名单）。
PASSED_GATE = "R384-PAST-THE-GATE"
PASSED_GATE_STATUS = 418

ASK_PATH = "/api/v1/ask"
UPLOAD_PATH = "/api/v1/upload"
ADMIN = "r384-admin"
ACCOUNT = {"id": "u-r384", "username": ADMIN, "role": "admin", "department": "", "status": "active"}

SESSIONS_LEDGER = {"sessions", "session_messages"}
DOCUMENTS_TABLE = "documents"

_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)
_CREATE_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)", re.IGNORECASE)
_DML_TARGET = re.compile(r"(?:FROM|INTO|UPDATE)\s+([A-Za-z_]\w*)", re.IGNORECASE)
#: 替身台账认识的几本账：不在目录里的账，DML 必须像真 PG 一样失败，否则"被宽捕获吃掉"那两格
#: 量到的就不是线上那张脸。
KNOWN_LEDGERS = {"sessions", "session_messages", DOCUMENTS_TABLE, "document_versions", "users"}


def _sentence(table_name: str) -> str:
    """那句现查的话：`<表> table is required in production; run migrations first`。

    拼出来而不是抄源码那一句：抄来的行号/行文本每演进一次红一次（R346/R351 那族病）。这里要钉
    的是「一个字节都没改」，不是那一行的字面量。
    """
    return f"{table_name} table is required in production; {SENTENCE}"


class SubstituteLedger:
    """只对「目录里现在有没有这一枚」作答的替身台账：不连库、不求值真 SQL。

    缺表时对 DML 抛**真的** ``psycopg.errors.UndefinedTable``（与真 PG 同一枚异常类）。
    """

    def __init__(self, tables=(), label="ledger"):
        self.tables = {str(name).lower() for name in tables}
        self.label = label
        self.statements: list[str] = []
        self.commits = 0
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        found = _REGCLASS.search(text)
        if found:
            name = found.group(1).lower()
            self._rows = [{"table_name": name if name in self.tables else None}]
            return self
        created = _CREATE_TABLE.search(text)
        if created:
            self.tables.add(created.group(1).lower())
            self._rows = []
            return self
        referenced = _DML_TARGET.search(text)
        if referenced:
            name = referenced.group(1).lower()
            if name in KNOWN_LEDGERS and name not in self.tables:
                raise errors.UndefinedTable('relation "%s" does not exist' % name)
        self._rows = []
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def close(self):
        return None

    @property
    def probed_tables(self) -> list[str]:
        return [m.group(1) for s in self.statements if (m := _REGCLASS.search(s))]

    @property
    def created_tables(self) -> list[str]:
        return [m.group(1) for s in self.statements if (m := _CREATE_TABLE.search(s))]


class LogRecorder:
    """把出口那几行日志留下来：三格分不分得开，今天只有这一处证据。"""

    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def _record(self, level, message, *args, **kwargs):
        self.lines.append((level, str(message)))

    def debug(self, message, *args, **kwargs):
        self._record("debug", message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._record("info", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._record("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._record("error", message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self._record("exception", message, *args, **kwargs)

    def mentions(self, needle: str) -> list[str]:
        return [text for _level, text in self.lines if needle in text]


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def _pass_the_gate(*args, **kwargs):
    """哨兵：越过闸之后的一切都不在本单判据里，所以让它在下一行就报一枚只有测试认识的码。"""
    raise HTTPException(status_code=PASSED_GATE_STATUS, detail=PASSED_GATE)


def _ask_client(monkeypatch, *, env: str, pg_up: bool, tables, stub_conn: bool = True,
                stub_ensure_session: bool = True):
    """架一具离线的 `/ask`：真中间件、真路由、真闸；只有闸后面那一行是哨兵。"""
    monkeypatch.setattr(
        auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: pg_up)
    ledger = SubstituteLedger(tables)
    if stub_conn:
        monkeypatch.setattr(chat, "_sess_conn", lambda: ledger)
    recorder = LogRecorder()
    monkeypatch.setattr(chat, "logger", recorder)
    if stub_ensure_session:
        monkeypatch.setattr(chat, "_ensure_session", _pass_the_gate)
    monkeypatch.setenv("APP_ENV", env)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        ASK_PATH,
        json={"message": "今年的销售额是多少", "session_id": "s-r384",
              "idempotency_key": f"idem-{env}-{pg_up}-{len(tables)}"},
        headers=_headers(),
    )
    return response, ledger, recorder


# ================= 现场状态码：`/ask` 那一格（本单唯一治的一格） =================
def test_production_with_a_missing_sessions_table_refuses_with_503(monkeypatch):
    """判据①：生产 + 库在 + 表缺 —— 修前实测裸 500 `text/plain`，本单治好这一格。"""
    response, ledger, recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set())

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert ledger.probed_tables == ["sessions"], "现查闸没走到就没资格谈折 503"
    assert recorder.mentions(SENTENCE), "原句折进 503 之后必须还在日志里"


def test_the_refusal_is_no_longer_the_bare_500_plain_text_face(monkeypatch):
    """裸 500 的病灶是「无码 + 纯文本」：这一格两样都不许留下。"""
    response, _ledger, _recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set())

    assert response.status_code != 500
    assert response.text != BARE_500_BODY
    assert "application/json" in response.headers["content-type"]


def test_the_log_line_names_the_missing_table_and_the_code(monkeypatch):
    """判据③：缺表 / 缺列 / 库没起三格排查路要分得开 —— 缺表这一格得说得出缺哪枚。"""
    _response, _ledger, recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set())

    lines = recorder.mentions("code=" + STORAGE_CODE)
    assert len(lines) == 1, lines
    assert "sessions table" in lines[0], lines[0]


def test_a_missing_session_messages_table_is_a_distinct_answer(monkeypatch):
    """两枚账分开查：只有 `sessions` 在、`session_messages` 不在时，指名的必须是后者。"""
    response, ledger, recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables={"sessions"})

    assert response.status_code == 503
    assert ledger.probed_tables == ["sessions", "session_messages"]
    assert recorder.mentions("session_messages table"), recorder.lines


def test_the_refusal_precedes_every_side_effect(monkeypatch):
    """拒答必须排在绑会话、落库、入队、模型之前：留下的是零副作用，不是跑了一半。"""
    calls: list[str] = []

    def _spy(*args, **kwargs):
        calls.append("bind")

    monkeypatch.setattr(
        "app.storage.sessions.SessionRegistry.bind", lambda self, *_a, **_k: _spy())
    response, _ledger, _recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set())

    assert response.status_code == 503
    assert calls == [], "闸拒答之前已经动了会话注册表"


def test_development_still_heals_the_ledgers_and_passes_the_gate(monkeypatch):
    """开发态一个字都不改：就地补 DDL 自愈，闸放行，本单不许把它一起打死。"""
    response, ledger, recorder = _ask_client(
        monkeypatch, env="development", pg_up=True, tables=set())

    assert response.status_code == PASSED_GATE_STATUS, response.text
    assert SESSIONS_LEDGER <= set(ledger.created_tables), ledger.statements
    assert ledger.probed_tables == [], "非生产那一腿不该做现查"
    assert not recorder.mentions(SENTENCE)


def test_the_offline_world_never_opens_a_connection(monkeypatch):
    """库整个不在：闸第一行就 `return`，一次连接都不许发，也就永远不答 503。"""
    response, ledger, _recorder = _ask_client(
        monkeypatch, env="production", pg_up=False, tables=set())

    assert response.status_code == PASSED_GATE_STATUS, response.text
    assert ledger.statements == [], ledger.statements


def test_a_fully_migrated_production_turn_still_passes(monkeypatch):
    """不许过度拒答：两枚账都在位时，闸只查不拒，也不在运行期提交 DDL。"""
    response, ledger, _recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set(SESSIONS_LEDGER))

    assert response.status_code == PASSED_GATE_STATUS, response.text
    assert ledger.probed_tables == ["sessions", "session_messages"]
    assert ledger.created_tables == []


def test_a_missing_driver_is_still_a_bare_500_and_not_a_503(monkeypatch):
    """反洗白：同基类的邻居（驱动缺失）不许被折成 503 —— 那不是「迁移没跑」。"""
    monkeypatch.setattr(chat, "psycopg", None)
    response, _ledger, _recorder = _ask_client(
        monkeypatch, env="production", pg_up=True, tables=set(SESSIONS_LEDGER),
        stub_conn=False)

    assert response.status_code == 500, response.text
    assert response.text == BARE_500_BODY


# ================= 具名化本身：只加一层，话一个字不改 =================
def test_the_family_is_one_layer_over_runtime_error():
    assert issubclass(chat.ChatSchemaNotMigratedError, RuntimeError)
    assert chat.ChatSchemaNotMigratedError is not RuntimeError


@pytest.mark.parametrize("table_name", [DOCUMENTS_TABLE, "sessions", "session_messages"])
def test_the_probe_raises_the_family_with_the_unchanged_sentence(table_name):
    """现查缺表 ⇒ 具名族 + 逐字原句（既有的宽捕获与旧账都还接得住）。"""
    ledger = SubstituteLedger(set())

    with pytest.raises(chat.ChatSchemaNotMigratedError) as caught:
        chat._require_migrated_tables(ledger, table_name)

    assert str(caught.value) == _sentence(table_name)
    assert isinstance(caught.value, RuntimeError), "基类一换就会弄红别人的旧账"


def test_the_probe_says_nothing_when_the_table_is_there():
    ledger = SubstituteLedger({DOCUMENTS_TABLE})

    assert chat._require_migrated_tables(ledger, DOCUMENTS_TABLE) is None


def test_the_documents_probe_still_raises_the_family(monkeypatch):
    """`_ensure_documents_table` 那一格今天也被同一句抛过：本单不改它的回话，但要有钉。"""
    ledger = SubstituteLedger(set())
    monkeypatch.setattr(chat, "_sess_conn", lambda: ledger)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError) as caught:
        chat._ensure_documents_table()

    assert type(caught.value) is chat.ChatSchemaNotMigratedError
    assert str(caught.value) == _sentence(DOCUMENTS_TABLE)


# ================= 判据③：门那一侧的形状（新增一枚，逐枚点名） =================
def _tree() -> ast.Module:
    return ast.parse(CHAT.read_text(encoding="utf-8"))


def _functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function_scopes(tree: ast.Module) -> list[ast.AST]:
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _status_sites(tree: ast.Module, status: int) -> list[tuple[str, ast.Raise]]:
    """`[(所属函数, raise 节点)]`：按 AST 数 `raise HTTPException(status_code=<status>, ...)`。"""
    found: list[tuple[str, ast.Raise]] = []
    for scope in _function_scopes(tree):
        for node in ast.walk(scope):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
                continue
            if getattr(node.exc.func, "id", "") != "HTTPException":
                continue
            for keyword in node.exc.keywords:
                if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant) \
                        and keyword.value.value == status:
                    found.append((scope.name, node))
    return found


def _detail_of(node: ast.Raise):
    """取 detail 的**值/形状**而不是它的字面量写法：单双引号不算改口，值变了才算。

    队列那几枚的 detail 是一枚运行期拼出来的 dict（``{"code": exc.code, ...}``），字面量求值吃不
    下，所以那一支回它的键名集合 —— 本单要分开的正是「同一枚字符串码」与「另一套 dict 信封」。
    """
    for keyword in node.exc.keywords:
        if keyword.arg != "detail":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant):
            return value.value
        if isinstance(value, ast.Dict):
            keys = sorted(ast.literal_eval(key) for key in value.keys)
            return "dict:" + "+".join(keys)
        return ast.unparse(value)
    raise AssertionError("那枚 503 没有 detail")


#: ── R397：下面四本账改成从 `app/api/v1/chat.py` 现场派生，不再抄今天的数 ──────────────
#: 为什么不是为了让门绿：`== 6` 与那份手抄名单是 R384 交付当天的**现场**，抄进钉里就成了下一班的假红
#: ——本仓为同一枚病开过 R346 / R351 / R377 / R396 / R400 一整族单。R397 合法地把两枚会话读腿折成
#: 503，名单因此 6 ⇒ 8；把数改成 8 只是把债从 6 搬到 8。所以名单与枚数一律由 AST 现查，账上只留
#: **每一枚为什么许在这里**那一句人写的理由——理由是人写的，枚数不是。
#: 极性两头都不许溜：长出未登记理由的出口算红，在册出口被拆掉也算红；一枚都数不到 ⇒ 当场红
#: （尺子自己瞎了不是免检理由，K2 形状，R396 刚为这个挨过退单）。
STORAGE_EXIT_REASONS: dict[str, tuple[str, str]] = {
    "_enqueue_ask_turn": ("dict:code+message", "存量：Redis 挂了交 queue_unavailable 的 dict 信封，与存储拒答分家"),
    "ask": (STORAGE_CODE, "R384：写腿缺该由迁移建的表，裸 500 折成已有的那一码"),
    "cancel_queued_request": ("dict:code+message", "存量：队列腿"),
    "hitl_pending": (STORAGE_CODE, "存量：R384 之前本模块唯一那枚 storage_unavailable 出口"),
    "queue_stats": ("dict:code+message", "存量：队列腿"),
    "queue_status": ("dict:code+message", "存量：队列腿"),
    # R397：两枚会话读腿。这里加的是条目与理由，不是某一行的数。
    "get_session": (STORAGE_CODE, "R397：`GET /sessions/{id}` 两条读腿共用一枚窄接法"),
    "list_sessions": (STORAGE_CODE, "R397：`GET /sessions` 缺表那一格从裸 500 折成已有的那一码"),
}
#: 现查闸的在册持有者（子集判：新加一枚持有者不出声，在册那几枚被拆掉算红）。
PROBE_HOLDER_ANCHORS = (
    "_require_sessions_read_schema",  # R397：两枚会话读腿共用那一枚
    "_ensure_documents_table",        # R384 在册
    "_ensure_sessions_table",         # R384 在册
)
#: 接这一族具名错的转换点：R384 起于一枚，R397 给两枚会话读腿各接一枚。
FAMILY_CONVERSION_SITES = ("ask", "get_session", "list_sessions")


def _exits_by_owner(tree: ast.Module | None = None) -> dict[str, list]:
    """现场派生 `{宿主函数名: [那一枚那些 503 的 detail 形状]}`：名单与枚数都从这里来。"""
    by_owner: dict[str, list] = {}
    for name, node in _status_sites(_tree() if tree is None else tree, 503):
        by_owner.setdefault(name, []).append(_detail_of(node))
    return {owner: sorted(shapes, key=str) for owner, shapes in by_owner.items()}


def test_the_module_now_opens_exactly_six_503_raises_each_named():
    """判据③：每一枚 503 出口都得有一枚在册的**理由**，理由来自 R384 / R391 / R397 三单。

    名单与枚数都改成派生（AST 现查 `HTTPException(status_code=503)` 的宿主函数名），账上只留
    「这一枚为什么许在这里」。为什么不是为了让门绿：这格仍然同时钉两头极性——长出一枚没登记
    理由的出口算红，在册那枚被人拆掉也算红；派生一枚都数不到还是红，不搞「没数到所以不判」。
    函数名里的 `exactly_six` 是 R384 当天的读数，留名只因契约按名字指它（改名要总控重登记）。
    """
    sites = _status_sites(_tree(), 503)
    by_owner = _exits_by_owner()

    assert sites, "chat.py 里一枚 503 都数不到：尺子自己瞎了，不是没有出口要判"
    unregistered = sorted(set(by_owner) - set(STORAGE_EXIT_REASONS))
    withdrawn = sorted(set(STORAGE_EXIT_REASONS) - set(by_owner))
    assert not unregistered, f"新长出 503 出口而没有在册理由：{unregistered}"
    assert not withdrawn, f"在册的 503 出口被拆掉了：{withdrawn}"
    assert sorted(by_owner) == sorted(STORAGE_EXIT_REASONS), sorted(by_owner)


def test_the_five_storage_exits_that_predate_this_ticket_are_untouched():
    """在册出口的 `detail` 形状逐枚不许跟着别的单动：只有派生名单里那句理由能解释它。

    为什么不是为了让门绿：把那份手抄 dict 换成一份新抄的四枚名单，只是把债从 6 搬到 8。名字里的
    `five` 同 `exactly_six` 一样是 R384 当天的现场读数，留名只为契约按名指它。真正在
    判的是逐格形状：队列那四枚必须**继续**交 `{"code", "message"}` 那套 dict 信封——「存储问不
    出」与「Redis 不在」是两张脸，不许被这一族折成同一枚字符串码；`ask` / `hitl_pending` 与
    R397 那两枚读腿必须继续交 `storage_unavailable`。比的是**列表**不是集合，所以「同一枚函数
    里再长一门」（反证刀 K8 试出来的那个洞）仍然算改了形状。
    """
    live = _exits_by_owner()

    assert live, "一枚 503 出口都派生不到：尺子瞎了，不许读成「没有要判的出口」"
    for owner, (shape, _why) in STORAGE_EXIT_REASONS.items():
        assert live.get(owner) == [shape], (owner, live.get(owner), shape)
    assert sorted(live) == sorted(STORAGE_EXIT_REASONS), (sorted(live), sorted(STORAGE_EXIT_REASONS))


def test_the_new_exit_reuses_the_existing_code_verbatim():
    """零新增错误码、零新增 reason：新出口的 detail 与既有出口逐字相同。"""
    tree = _tree()
    ask_503 = [node for name, node in _status_sites(tree, 503) if name == "ask"]
    pending_503 = [node for name, node in _status_sites(tree, 503) if name == "hitl_pending"]

    assert len(ask_503) == 1 and len(pending_503) == 1
    assert _detail_of(ask_503[0]) == _detail_of(pending_503[0]) == STORAGE_CODE


def test_no_status_tier_was_invented_in_this_ticket():
    """本单不许长出新的 status 档位：哨兵 418 只许活在测试里，`app/**` 一个字节都不认。"""
    hits: list[str] = []
    for path in (REPO / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PASSED_GATE in text or f"status_code={PASSED_GATE_STATUS}" in text:
            hits.append(str(path))

    assert hits == [], hits


def test_the_ask_conversion_catches_exactly_one_type():
    """宽捕获会把真 bug 一起洗成 503：出口只许接 `ChatSchemaNotMigratedError` 一种。"""
    route = _functions(_tree())["ask"]
    handlers = [node for node in ast.walk(route)
                if isinstance(node, ast.ExceptHandler) and node.type is not None]
    matching = [node for node in handlers if ast.unparse(node.type) == FAMILY]

    assert len(matching) == 1, [ast.unparse(node.type) for node in handlers]
    bodies = [ast.unparse(stmt) for stmt in matching[0].body]
    assert sum("raise HTTPException" in text for text in bodies) == 1, bodies
    assert sum(STORAGE_CODE in text and "raise HTTPException" in text for text in bodies) == 1, bodies
    assert sum("logger.warning" in text for text in bodies) == 1, bodies


def test_only_the_probe_raises_the_family():
    """具名族只有一个抛出方：出口之外不许有人自己举它（否则「只接一种」就失去含义）。"""
    raisers = [
        (scope.name, node.lineno)
        for scope in _function_scopes(_tree())
        for node in ast.walk(scope)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == FAMILY
    ]

    assert len(raisers) == 1, raisers
    assert raisers[0][0] == PROBE, raisers


def test_every_probe_call_site_sits_inside_a_production_branch():
    """调用点由 AST 现数，在册持有者一枚不许丢；每一处仍必须只可能在生产分支被走到。

    为什么不是为了让门绿：`== 2` 是 R384 当天的现场，R397 给两枚会话读腿新接了一枚闸
    （`_require_sessions_read_schema`），调用点因此**合法地**变成 3 枚——写死 3 只是把债搬一格。
    改成两句派生账：持有者名单必须覆盖锚点，以及每一枚调用点都仍走在 `_is_production_environment()`
    里面。加闸不出声（新持有者只要还在生产分支里就不算本格的账），拆闸、把闸搬到非生产、一枚
    调用点都数不到，三样都算红。
    """
    tree = _tree()
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "id", "") == PROBE]
    call_ids = {id(node) for node in calls}
    holders = {scope.name for scope in _function_scopes(tree)
               for node in ast.walk(scope) if id(node) in call_ids}

    assert calls, f"全模块数不到一处 `{PROBE}(` 调用点：闸没了，缺表那一格又变回裸 500"
    missing = sorted(set(PROBE_HOLDER_ANCHORS) - holders)
    assert not missing, f"在册的现查持有者不见了：{missing}"
    for call in calls:
        guards = [node for node in ast.walk(tree)
                  if isinstance(node, ast.If) and node.lineno <= call.lineno <= (node.end_lineno or node.lineno)
                  and "_is_production_environment" in ast.unparse(node.test)]
        assert guards, f"{PROBE} 的调用点 :{call.lineno} 跑出了生产分支"


def test_the_module_still_relies_on_no_global_safety_net():
    """本单结论的前提是「全局没有兜底翻译」：有人真挂一枚 handler，这张表就得重画。

    判的是 AST 上的名字与装饰器，不是源码子串 —— 本单自己在出口写的那句注释里就出现过
    `exception_handler` 这个词，拿子串判会把自己读成假阳性（现场踩过一次，改的就是这里）。
    """
    hits: list[str] = []
    for path in (REPO / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        named = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        if any("exception_handler" in token for token in named):
            hits.append(str(path.relative_to(REPO)))

    assert hits == [], hits


# ================= 判不可达的两格：钉住今天这张脸，一个字不改 =================
def test_the_import_time_probe_sits_inside_a_bare_pass_handler():
    """导入期那一枚调用点被 ``except Exception: pass`` 吃在原地：形状必须留着。

    那枚 `try` 嵌在模块级 `if catalog_database_available():` 里面，所以整棵树扫，不只看 `tree.body`。
    """
    guarded = [
        (node, handler)
        for node in ast.walk(_tree()) if isinstance(node, ast.Try)
        for handler in node.handlers
        if ast.unparse(handler.type) == "Exception"
        and any(isinstance(call, ast.Call)
                and getattr(call.func, "id", "") == "_ensure_documents_table"
                for call in ast.walk(node))
    ]

    assert len(guarded) == 1, guarded
    _node, handler = guarded[0]
    assert len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass), (
        "吃掉它的那一枚不再是 pass：这一格的回话变了，可达性表要重画")


def test_the_upload_metadata_leg_still_answers_200_when_documents_is_missing(monkeypatch, tmp_path):
    """R384 存档、R391 判口：这一格的状态码从 200 变成 503，而 `metadata sync failed` 那一句仍恰好一枚。

    R384 写这枚件时只能登记「今天的样子」（它自己就写着「钉的是今天的样子，不是裁定」），并把真正的病
    报给总控。R391 是治那一格的班：`_record_uploaded_version` 不再吃掉 catalog 具名抛出的那枚 503，
    于是版本腿拒答时出口答 503。函数名里那个 200 保留，是为了对齐 R384 回执与名册，不作数。

    本枚要钉的两件事一件没松：① 归属腿（`_upsert_document` / `documents` 表）的既有容忍一字未动 ——
    下面那条 `metadata sync failed` 仍恰好一枚、现查仍恰好走过 `documents`；② 版本腿自己报出的拒答
    不再被翻译成成功回执。两者是同一发请求里的两支，R391 分得很清，也只折后一支。
    """
    from app.agents import tools

    ledger = SubstituteLedger(set())
    recorder = LogRecorder()
    monkeypatch.setattr(
        auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "catalog_database_available", lambda: True)
    monkeypatch.setattr(chat, "_sess_conn", lambda: ledger)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: "abc")
    monkeypatch.setattr(chat, "logger", recorder)

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

        def list_documents(self):
            return []

    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    monkeypatch.setenv("APP_ENV", "production")

    response = TestClient(app, raise_server_exceptions=False).post(
        UPLOAD_PATH,
        files={"file": ("r384-note.txt", "短文本 不入库".encode("utf-8"), "text/plain")},
        data={"classification": "1", "department": ""},
        headers=_headers(),
    )

    assert response.status_code == 503, response.text  # R391：原为 200（那一枚假回执），见上面 docstring
    assert ledger.probed_tables == [DOCUMENTS_TABLE]
    swallowed = recorder.mentions(SENTENCE)
    assert len(swallowed) == 1, swallowed
    assert swallowed[0].startswith("[Docs] metadata sync failed"), swallowed[0]


def test_the_conversion_is_narrow_at_the_module_level_too():
    """接这一族具名错的转换点也是派生名单：不许多、不许少、每处仍只接一种、只交一个码。

    为什么不是为了让门绿：R384 只有 `ask` 一枚，R397 给两枚会话读腿各接一枚，把
    `[("ask", FAMILY)]` 换成硬写三枚的名单同样是抄现场。名单来自 AST 现查，账上只留锚点名。
    发现那一步用 `FAMILY in ast.unparse(node.type)`，所以宽捕获（`except
    (ChatSchemaNotMigratedError, RuntimeError):` 一类）会被现查一并抓出来而不是被放过——那正是
    判据②要挡的事；一枚都数不到 ⇒ 出口回到裸 500 ⇒ 当场红。
    """
    handlers = [
        (scope.name, node)
        for scope in _function_scopes(_tree())
        for node in ast.walk(scope)
        if isinstance(node, ast.ExceptHandler) and node.type is not None
        and FAMILY in ast.unparse(node.type)
    ]
    names = sorted(owner for owner, _node in handlers)

    assert handlers, f"全模块没有一处接 `{FAMILY}` 的 except：缺表那一格又变回裸 500"
    assert names == sorted(FAMILY_CONVERSION_SITES), names
    for owner, node in handlers:
        assert ast.unparse(node.type) == FAMILY, (owner, ast.unparse(node.type))
        body = " ".join(ast.unparse(stmt) for stmt in node.body)
        assert body.count("raise HTTPException") == 1, (owner, body)
        assert STORAGE_CODE in body, (owner, body)
        assert body.count("logger.warning") == 1, (owner, body)