"""R377 · 「run migrations first」同族另外四枚：逐枚取证之后判定**不折 503**，本单零生产码改动。

R371 把 `app/api/v1/alerts.py` 那三句在 HTTP 出口折成 503 之后，交回「同族那句话在另外六枚模块
各长着一枚」。本单领到其中四枚：`app/common/auth.py`、`app/documents/catalog.py`、
`app/memory/long_term.py`、`app/memory/profile.py`（四枚抛点在哪个符号身上、那句原文怎么写都逐字在册，行号运行时现读）。

四问逐枚答完的结论是：**四枚全部判不可达**——每一枚的抛点都被本模块自己的宽捕获吃在
store 层，没有任何一枚能把这句 RuntimeError 递到 HTTP 出口，四枚模块里 `HTTPException` 与
`status_code=503` 的抛出数都是 **0**（判据 2：模块根本没有拒答闸，就不许现造一枚闸来凑达标）。
现场量到的真实回话一律取自 `TestClient(..., raise_server_exceptions=False)`，逐枚点名:

  · `auth.py:414`（吃掉它的是 `:257` R230 重探、`:478` import 探针）
    ⇒ `POST /api/v1/login` 答 **401** `{"detail":"用户名或密码错误"}`；
      `GET /api/v1/profile` 答 **401** `{"detail":"authentication_required"}`
  · `catalog.py:516`（吃掉它的是 `:552 / :700 / :722 / :754 / :819` 五枚）
    ⇒ `GET /api/v1/documents` 与 `/documents/catalog` 答 **200** `{"documents":[]}`；
      `GET /api/v1/documents/{f}/versions` 答 **404** `resource_not_found`
  · `long_term.py:69`（吃掉它的是 `:176` 写、`:192` 读）
    ⇒ 这一枚压根没有自己的 HTTP 出口: `remember()` 答 `False`、`recall()` 答 `[]`
  · `profile.py:83`（吃掉它的是 `:141` 读、`:190` 写）
    ⇒ `GET /api/v1/profile` 答 **200**（退回 `users` 那一行）；
      `PUT /api/v1/profile` 答 **500** `{"detail":"画像保存失败"}` —— 那枚 500 是**路由层自己
      写的** `HTTPException`（`app/api/v1/auth.py:281`，不在本单写域），不是逃出去的裸 500

🔴 两件必须说清的边界，不许从这份记录里读丢：
1. 「不折 503」不等于「这一族没问题」。catalog 与 profile 那两枚的真症状是**反方向**的：存储现查到
   缺表，出口却答 200 空集 / 200 画像，把「问不出」说成「没有」——那是 R359/R356/R332 同一条裁定
   （存储拒答不许翻译成空集），修它要摘掉 store 层的回落、并给模块配一枚闸，越出本单写域，已进
   回执「只报不改」。
2. 效力边界：本件全部跑在**替身台账**上。替身只求值「`to_regclass('public.x')` 这一次现查怎么答」，
   不求值任何真实 SQL、不碰真库、不起容器。所以本件证明的是「出口在读到缺表时答什么」，
   **不**证明「跑 migrations 真能把那一格补出来」。

🔴 R383 已经把上面那条「只报不改」的 ① 与 ② 落地了（`app/documents/catalog.py` 配了一道自己的
闸——它的 HTTP 出口在 `app/api/v1/chat.py`，那一枚不在 R383 写域；`app/memory/profile.py` 抛具名
拒答、`app/api/v1/auth.py` 做一次窄翻译）。本件里三枚「现场量测」因此改口，台账行号当年一并重取，R396 起改成锚点现读；
R377 当年那句判定（这句错逃不到 HTTP 出口）在 `app/common/auth.py` 与 `app/memory/long_term.py`
两枚上仍然成立，一字未动。逐枚改口清单写在 R383 的回执里，本文件不重写历史。

🔴 R396（纯测试件，零生产码改动）：本文件原来把 `app/documents/catalog.py` 的行号**抄成常量**
（抛点、五枚调用点、五枚 catch-all、那枚 503 出口），于是任何落在这一棵里的修复都得做到「行数中性」
才能并树。现在四本账一律换成锚点 token（符号名 + 该符号内唯一的语句形状），行号由
`scripts/r396_anchor_ledger.py` 现读；形状钉见 `tests/test_r396_line_numbers_are_derived_not_copied.py`。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.common import auth
from app.documents import catalog
from app.main import app
from app.memory import long_term, profile
from scripts import r396_anchor_ledger as anchor_ledger

REPO = Path(__file__).resolve().parents[1]
SENTENCE = "run migrations first"
BARE_500_BODY = "Internal Server Error"

#: 🔴 R396 起这一族账**一个行号都不抄**：每格是一枚锚点 token（符号名 + 该符号内唯一的语句
#: 形状），行号由 `anchor_ledger.anchor_line()` 在运行时现读；这几格里再出现字面行号常量，
#: `tests/test_r396_line_numbers_are_derived_not_copied.py` 那枚形状钉当场红。锚点读不到 = 红并
#: 点名锚点（机器喊 `锚点现读不到`），不是静默跳过。手法照 R346（`00945a9`）。
#: 抛点账：一枚模块一句，登记那句 `raise` 的原文与它长在谁身上（有人改口就红），行号现读。
RAISE_SITES = {
    "app/common/auth.py": (
        'raise:_create_schema:raise RuntimeError("users table is required in production; '
        'run migrations first")',
    ),
    "app/documents/catalog.py": (
        'raise:_ensure:raise RuntimeError("document_versions table is required in production; '
        'run migrations first")',
    ),
    "app/memory/long_term.py": (
        'raise:_init:raise RuntimeError("memories table is required in production; '
        'run migrations first")',
    ),
    "app/memory/profile.py": (
        'raise:_ensure:raise RuntimeError("user_profiles table is required in production; '
        'run migrations first")',
    ),
}

#: 把抛点吃在 store 层的那几行：一枚模块的每一枚 `_ensure()` / `_create_schema()` 调用点，
#: 都必须落在列出的那枚 catch-all handler 的 `try` 里面（AST 判，见下面的形状钉）。
#: 每格 = 那枚 handler 体内唯一的一句日志片段（`guard:` 锚点），行号现读。
GUARD_BY_MODULE = {
    "app/common/auth.py": (
        "guard:R230 重探连上但用户表不可用",
        "guard:Postgres 探针失败",
    ),
    "app/documents/catalog.py": (
        "guard:version lookup fallback",
        "guard:version record not written",
        "guard:current listing fallback",
        "guard:history fallback",
        "guard:version deletion fallback",
    ),
    "app/memory/long_term.py": ("guard:write failed", "guard:read failed"),
    "app/memory/profile.py": ("guard:load skipped", "guard:save failed"),
}

#: 每枚模块里 `_ensure()` / `_create_schema()` 的直接调用点（`app/**` 全仓现读）：
#: 每格 = 「哪一枚 scope 里的那一枚调用」（`call:` 锚点，`-` = 模块顶层 import 期探针），行号现读。
CALL_SITES = {
    "app/common/auth.py": (
        "call:_retry_readiness_probe:_create_schema",
        "call:-:_create_schema",
    ),
    "app/documents/catalog.py": (
        "call:peek_next_document_version:_ensure",
        "call:record_document_version:_ensure",
        "call:current_documents:_ensure",
        "call:list_document_versions:_ensure",
        "call:delete_document_versions:_ensure",
    ),
    "app/memory/long_term.py": ("call:remember:_ensure", "call:recall:_ensure"),
    "app/memory/profile.py": ("call:get_profile:_ensure", "call:upsert_profile:_ensure"),
}

#: `app/api/v1/chat.py` 的迁移闸调用点（两枚不在本单写域的生产尺，只登记事实）：账上记**被调符号**，
#: 落点几枚、在哪几行一律现读——在途 R397 正往那一棵加读腿闸，格数会跟着现实加长（R396 令一）。
CHAT_MIGRATION_GATES = ("calls:_require_migrated_tables",)

GUARDED_FUNCTIONS = frozenset({"_ensure", "_create_schema"})
_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)

ADMIN = "r377-admin"
#: R383 起三枚现读出口都答这一枚码；本件零新增错误码，它来自 `app/agents/contracts.py` 的枚举。
STORAGE_CODE = "storage_unavailable"
ACCOUNT = {"id": "u-r377", "username": ADMIN, "role": "admin", "department": "", "status": "active"}


def _as_authenticated_user(monkeypatch, module) -> None:
    """让中间件与授权层都答得出这个人：本件只判存储那一格，不重开权限的账（判据 4）。"""
    monkeypatch.setattr(
        module, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None
    )


class _Recorder:
    """把出口日志留下来：证明那句 RuntimeError 真的**在请求期间抛过一次**，只是没逃出去。"""

    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def debug(self, message, *args, **kwargs):
        self.lines.append(("debug", str(message)))

    def info(self, message, *args, **kwargs):
        self.lines.append(("info", str(message)))


    def warning(self, message, *args, **kwargs):
        self.lines.append(("warning", str(message)))

    def error(self, message, *args, **kwargs):
        self.lines.append(("error", str(message)))


    def mentions(self, needle: str) -> list[str]:
        return [text for _level, text in self.lines if needle in text]


class _Store:
    """替身台账：只对 `to_regclass('public.x')` 这一枚现查作答，别的语句一律不认。"""

    def __init__(self, tables=(), label="store"):
        self.tables = set(tables)
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
        found = _REGCLASS.search(text)
        if not found:
            self._rows = []
            return self
        name = found.group(1)
        self._rows = [{"table_name": name if name in self.tables else None}]
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
    assert path.is_file(), f"写集里的文件不见了: {path}"
    return path.read_text(encoding="utf-8")


def _tree(relative: str) -> ast.Module:
    return ast.parse(_source(relative))


def _anchor_sites(relative: str, cells: tuple[str, ...]) -> tuple[int, ...]:
    """🔴 同上，但允许一格交多枚落点（`calls:` 锚点）：枚数由现场说，账上只记被调符号。"""
    return anchor_ledger.derive_sites(anchor_ledger.read_sources(relative), relative, cells)
def _anchor_lines(relative: str, cells: tuple[str, ...]) -> tuple[int, ...]:
    """🔴 行号一律现读：把一本锚点账喂给 R396 那台机器，交回它与现场相等的那几行。"""
    return anchor_ledger.derive_ledger(anchor_ledger.read_sources(relative), relative, cells)


def _anchor_one(relative: str, cells: tuple[str, ...]) -> int:
    lines = _anchor_lines(relative, cells)
    assert len(lines) == 1, f"{relative} 这本账只该有一格，实测 {lines}: {cells}"
    return lines[0]


def _function_node(tree: ast.Module, name: str, relative: str) -> ast.FunctionDef:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"{relative} 里的闸函数 {name} 现读 {len(found)} 枚：锚点读不到，或闸被复制了"
    return found[0]


def _is_catch_all(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    dumped = ast.dump(handler.type)
    return "Exception" in dumped


def _guarded_call_lines(tree: ast.Module) -> dict[int, int]:
    """`{调用行: 包住它的 catch-all handler 行}`；没有 catch-all 兜着的调用点不会出现在这里。"""
    guarded: dict[int, int] = {}

    class Walk(ast.NodeVisitor):
        def visit_Try(self, node):  # noqa: N802
            handlers = [handler for handler in node.handlers if _is_catch_all(handler)]
            if handlers:
                inner = min(handler.lineno for handler in handlers)
                for call in ast.walk(node):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id in GUARDED_FUNCTIONS
                    ):
                        guarded[call.lineno] = inner
            self.generic_visit(node)

    Walk().visit(tree)
    return guarded


def _unguarded_call_lines(tree: ast.Module) -> list[int]:
    found = [
        call.lineno
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in GUARDED_FUNCTIONS
    ]
    guarded = _guarded_call_lines(tree)
    return [line for line in sorted(found) if line not in guarded]


def _raise_sites(tree: ast.Module, status_code: str) -> list[int]:
    """按 AST 数 `raise HTTPException(status_code=<status_code>, ...)` 的抛出点。"""
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
                continue  # 参数化的抛出点（`status_code=status_code`）不是本件要数的那一格
            if value == int(status_code):
                lines.append(node.lineno)
    return sorted(lines)


# ======================================= 第 2 节判据 1：抛点逐枚在册，一句不多、一句不少
@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_each_module_carries_exactly_one_of_those_sentences(relative):
    """R371 交回来的「各一枚」在本单基点上复核成立：一枚模块恰好一句，且那句原文逐字未动。

    R396 起这一格是两条腿互校：现场腿数那句话在文件里出现了几次，锚点腿按「哪枚函数里的那句
    原文」现读行号，两条腿必须落在同一行。谁把那句话改了口 ⇒ 锚点读不到；谁多写一句 ⇒ 现场腿
    数出两枚。红的是账与现场对不上，不再是「某个抄下来的数字该改了」。
    """
    source = _source(relative)
    cells = RAISE_SITES[relative]
    line = _anchor_one(relative, cells)
    statement = anchor_ledger.raise_statement_of(cells[0])
    occurrences = [
        number for number, text in enumerate(source.splitlines(), start=1) if SENTENCE in text
    ]

    assert occurrences == [line], f"{relative} 的抛点应当恰好一枚且在 :{line}，实测 {occurrences}"
    assert statement in source, f"{relative}:{line} 那句话被改口了：{statement}"


# ============================ 第 2 节判据 2：没有 HTTP 出口——四枚模块既无 HTTPException 也无 503
#: R383 之后这四枚不再同质：`app/documents/catalog.py` 领到了它自己的那道闸（它的 HTTP 出口在
#: `app/api/v1/chat.py`，本单不许动，所以闸只能长在模块里）。其余三枚仍然一枚 HTTP 出口都不许有。
#: 这一格记的是「那枚 503 的身份」——它长在谁身上、是哪一档码（`http_raise:` 锚点），不是行号。
GATE_503_EXIT = {"app/documents/catalog.py": ("http_raise:_require_ready_store:503",)}
#: 对照件（R371 那道闸）同一条口径：`app/api/v1/alerts.py` 全模块唯一那枚 503 也按身份记账。
ALERTS_GATE_503_EXIT = {"app/api/v1/alerts.py": ("http_raise:_require_ready_store:503",)}


@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_none_of_the_four_modules_owns_an_http_exit(relative):
    """R377 的前提「四枚都是 store 层、闸门一枚都没有」已被 R383 改掉一半：改口逐枚收紧。

    目录那一枚从「不许有 503」改成「全模块恰好一枚 503，且必须抛在 ``_require_ready_store`` 的
    最后一行」——闸只准有一扇，侧门一枚都不许长（同 R359 给 alerts 钉的那条口径）。其余三枚（含
    ``app/memory/profile.py``：它把拒答交回 ``app/api/v1/auth.py`` 翻译，自己一枚 HTTP 异常都不
    发起）逐字保持原判。闸的名字取自账上那枚锚点，不再在断言里第二次抄一遍。
    """
    tree = _tree(relative)

    if relative in GATE_503_EXIT:
        cells = GATE_503_EXIT[relative]
        exits = _raise_sites(tree, "503")
        assert exits == [_anchor_one(relative, cells)], (
            f"{relative} 的 503 抛出点应当恰好一枚，实测 {exits}"
        )
        gate = _function_node(tree, anchor_ledger.anchor_symbol(cells[0]), relative)
        assert gate.lineno <= exits[0] <= gate.end_lineno, "那道 503 不在闸的函数体里：闸被复制了"
        return

    assert "HTTPException" not in _source(relative), f"{relative} 里出现了 HTTPException：本件的判定作废"
    assert _raise_sites(tree, "503") == [], f"{relative} 长出了 503 抛出点：改判前请先重取可达性"


def test_r371_alone_still_owns_the_single_migration_exit():
    """对照：全仓那句「缺迁移答 503」仍然只有 alerts 那一枚闸在答，本单没有把它复制一份。

    R396 起那一枚的行号也是现读的：现场腿全模块扫 503 出口，锚点腿按 alerts 那道闸的名字读它，
    两条腿对不上才红——`app/api/v1/alerts.py` 上方进几行，本件跟着走，不再逼施工方行数中性。
    """
    relative = sorted(ALERTS_GATE_503_EXIT)[0]
    exits = _raise_sites(_tree(relative), "503")

    assert exits == [_anchor_one(relative, ALERTS_GATE_503_EXIT[relative])], (
        f"{relative} 的 503 出口与账上那枚闸对不上，实测 {exits}"
    )


# ================== 第 2 节判据 2 的正面：每一枚调用点都被本模块的 catch-all 吃在 store 层
@pytest.mark.parametrize("relative", sorted(RAISE_SITES))
def test_every_call_site_is_swallowed_by_the_named_handlers(relative):
    """`_ensure()` / `_create_schema()` 的每一枚直接调用点，都必须落在登记过的那枚 catch-all 里。

    🔴 这两本账就是「判不可达」的全部依据：调用点一枚不少（与现场扫出的相等）、且一枚不漏地有
    catch-all 兜着。少一枚 handler、多一枚裸调用点，本件立刻红——那才是「这句错能逃到 HTTP 出口」
    的形状。R396 起两本账只写身份（`call:` / `guard:` 锚点），行号在这里现读：锚点腿按「哪枚 scope
    里的那枚调用」「哪枚 handler 体内躺着那句唯一日志」现算，结构腿 `_guarded_call_lines()` 按
    try/handler 扫现场，两条腿互相算不出对方，所以它们相等是真判据而不是同义反复。
    """
    tree = _tree(relative)
    guarded = _guarded_call_lines(tree)
    ledger_calls = _anchor_lines(relative, CALL_SITES[relative])
    ledger_guards = _anchor_lines(relative, GUARD_BY_MODULE[relative])

    assert list(ledger_calls) == sorted(ledger_calls), (
        f"{relative} 的调用点账不按源码序：{list(ledger_calls)}——逐格配对靠源码序，别打乱"
    )
    assert list(ledger_guards) == sorted(ledger_guards), (
        f"{relative} 的 handler 账不按源码序：{list(ledger_guards)}"
    )
    assert sorted(guarded) == sorted(ledger_calls), (
        f"{relative} 的受保护调用点变了：账上锚点现读 {sorted(ledger_calls)}，实测 {sorted(guarded)}"
    )
    assert sorted(set(guarded.values())) == sorted(ledger_guards), (
        f"{relative} 吃掉它的 handler 变了：账上锚点现读 {sorted(ledger_guards)}，"
        f"实测 {sorted(set(guarded.values()))}"
    )
    assert [guarded[line] for line in ledger_calls] == list(ledger_guards), (
        f"{relative} 的调用点与 handler 交叉接线了：账上第 i 枚调用点没落在第 i 枚 handler 里"
    )
    assert _unguarded_call_lines(tree) == [], (
        f"{relative} 长出没有 catch-all 兜着的调用点：{_unguarded_call_lines(tree)}"
    )


def test_the_two_out_of_write_set_modules_are_still_report_only():
    """`orchestrator.py` / `chat.py` 两枚不在本单写域：这里只登记事实，一根手指都不动。

    R384 改口（只报先行，改的就是下面这一枚断言的口径）：原件把 `chat.py` 那枚 `raise` 的**整行
    原文**抄进断言，正是 R346 / R351 点名的"抄一句源文本当判据"那族病。R384 把那一枚 raise 折成
    同族具名子类 `ChatSchemaNotMigratedError`（消息文本一个字节没改，改的只有类型与换行形状），
    原断言就把一次合法改动判成事故。本件真正要登记的从来不是那行的形状，而是**那一句在 `chat.py`
    里仍然只有一枚**，所以判据换成句子计数。类型与出口形状由 R384 自己的件逐枚钉着
    （`tests/test_r384_migrations_first_refuses_at_the_ask_exit.py`），一条都没松。
    """
    orchestrator = _source("app/agents/orchestrator.py")
    chat_relative = "app/api/v1/chat.py"
    chat = _source(chat_relative)
    checkpoint = "PostgresSaver checkpointer is required in production; run migrations first"

    assert orchestrator.count(checkpoint) == 1, "checkpointer 那一句被复制了：可达性账要重取"
    assert chat.count("table is required in production; run migrations first") == 1, (
        "chat 那一句被复制了：可达性账要重取")
    # 🔴 R396 令一：这半句原来抄的是 `chat.count("_require_migrated_tables(") == 3`。那既不是「哪几枚」
    # 也不是枚数——它把 `_require_migrated_tables` 自己的 def 那一行一起数了进去；在途 R397 往那一棵
    # 加读腿闸（合法地多一枚调用点），这格明天就会被顶成假红。现在账上只记被调符号：落点与枚数两条腿
    # 各自现读并互校，再逐格证每一枚落点仍躺在 `if _is_production_environment():` 的真支里。
    gates = _anchor_sites(chat_relative, CHAT_MIGRATION_GATES)
    callee = anchor_ledger.anchor_symbol(CHAT_MIGRATION_GATES[0])
    textual = [
        number
        for number, row in enumerate(chat.splitlines(), start=1)
        if f"{callee}(" in row and not row.lstrip().startswith("def ")
    ]
    production = anchor_ledger.production_branch_lines(
        anchor_ledger.read_sources(chat_relative), chat_relative
    )

    assert list(gates) == textual, f"chat 的闸调用点两条腿对不上：锚点 {list(gates)} vs 现场 {textual}"
    assert set(gates) <= production, (
        f"chat 的迁移闸调用点长到了生产分支之外：{sorted(set(gates) - production)}"
    )


# ============================================================= 现场量测：auth.py 那一格答 401


@pytest.fixture
def recorder(monkeypatch):
    """把某一枚模块的 logger 换成记账器：证明那句错真的在请求期间抛过一次。"""

    def wire(module):
        sink = _Recorder()
        monkeypatch.setattr(module, "logger", sink)
        return sink

    return wire


@pytest.fixture
def production(monkeypatch):
    """生产态：`APP_ENV=production`；其余口径全走 conftest 的钉，不连真库、不起服务。"""
    monkeypatch.setenv("APP_ENV", "production")


def _login_client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_the_missing_users_table_refuses_login_with_401_not_a_bare_500(
    production, recorder, monkeypatch
):
    """auth.py:414 在请求路径上真抛过一次，被 R230 重探那枚 catch-all 吃掉 ⇒ 客户看到 401。"""
    from app.common import auth as auth_module

    sink = recorder(auth_module)
    monkeypatch.setattr(auth_module, "psycopg", object())
    monkeypatch.setattr(auth_module, "_db_ready", False)
    monkeypatch.setattr(auth_module, "_last_ready_probe_at", None)
    monkeypatch.setattr(auth_module, "_connect_for_request", lambda operation: _Store(label="auth"))

    response = _login_client().post("/api/v1/login", json={"username": ADMIN, "password": "secret123"})

    assert SENTENCE in "".join(sink.mentions("R230 重探连上但用户表不可用")), "抛点没被走到：本件判不了可达性"
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "用户名或密码错误"}
    assert BARE_500_BODY not in response.text


def test_the_missing_users_table_answers_the_profile_route_with_the_middlewares_401(
    production, recorder, monkeypatch
):
    """中间件那一腿同样过这枚闸：`get_user` 被拒 ⇒ 401 `authentication_required`，不是 500。"""
    from app.common import auth as auth_module

    sink = recorder(auth_module)
    monkeypatch.setattr(auth_module, "psycopg", object())
    monkeypatch.setattr(auth_module, "_db_ready", False)
    monkeypatch.setattr(auth_module, "_last_ready_probe_at", None)
    monkeypatch.setattr(auth_module, "_connect_for_request", lambda operation: _Store(label="auth"))

    response = _login_client().get(
        "/api/v1/profile", headers={"Authorization": f"Bearer {auth.create_token(ADMIN)}"}
    )

    assert sink.mentions("R230 重探连上但用户表不可用"), sink.lines
    assert response.status_code == 401, response.text
    assert response.json() == {"detail": "authentication_required"}
    assert BARE_500_BODY not in response.text


# ============================================================ 现场量测：catalog.py 那一格答 200 空
def _catalog_store(monkeypatch, recorder):
    from app.common import auth as auth_module

    sink = recorder(catalog)
    monkeypatch.setattr(auth_module, "_db_ready", True)
    monkeypatch.setattr(auth_module, "_memory_store_denied", lambda operation: False)
    _as_authenticated_user(monkeypatch, auth_module)
    monkeypatch.setattr(catalog, "_initialized", False)
    monkeypatch.setattr(catalog, "_conn", lambda: _Store(label="catalog"))
    return sink


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def test_the_missing_document_versions_table_refuses_503_not_200_empty(
    production, recorder, monkeypatch
):
    """R383 改口（本件基点记的是病灶脸：``:516`` 被 ``:722`` 吃掉 ⇒ 200 空集）。

    从「200 + `{"documents": []}`」改成「503 + `storage_unavailable`」：那句 200 把「这一格问不
    出」说成「这家公司没有知识文档」，是 R359/R356/R332 同一条裁定禁的形状。方向只收紧不放宽——
    两枚出口现在必须逐字答同一枚码，且回落本地台账那一格在生产已经不许发生。
    可达性证据换了承载：R377 用 ``current listing fallback`` 那行 warning 证明抛点走到过，今天
    闸在回落之前就拒了，所以证据换成闸自己那行带 ``migration=`` 的日志（同一枚现查的结论）。
    """
    sink = _catalog_store(monkeypatch, recorder)
    client = _login_client()

    listing = client.get("/api/v1/documents", headers=_headers())
    catalog_view = client.get("/api/v1/documents/catalog", headers=_headers())

    assert listing.status_code == 503, listing.text
    assert catalog_view.status_code == 503, catalog_view.text
    assert listing.json() == {"detail": STORAGE_CODE}
    assert catalog_view.json() == {"detail": STORAGE_CODE}
    assert BARE_500_BODY not in listing.text + catalog_view.text
    assert {"documents": []} not in (listing.json(), catalog_view.json())
    assert sink.mentions("current listing fallback") == [], "生产还回落到本地台账 = 闸没咬住"
    assert sink.mentions("code=storage_unavailable migration="), sink.lines


def test_the_missing_document_versions_table_says_503_not_404_on_version_history(
    production, recorder, monkeypatch
):
    """R383 改口：这一格今天答的是 404 ``resource_not_found``——比空集更像一句确定的假话。

    「这个文档没有版本历史」与「目录问不出」是两件事；`app/api/v1/chat.py:4343` 那句
    `if not versions: raise 404` 只有在本模块交出空表时才会响，而它今天响的原因就是那次回落。
    """
    sink = _catalog_store(monkeypatch, recorder)

    response = _login_client().get("/api/v1/documents/r377-missing.pdf/versions", headers=_headers())

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert "resource_not_found" not in response.text
    assert sink.mentions("history fallback") == [], "生产还回落 = 这一条腿的闸没咬住"
    assert sink.mentions("code=storage_unavailable migration="), sink.lines


# ============================================================ 现场量测：profile.py 读 200 / 写 500(有码)
def _profile_store(monkeypatch, recorder):
    from app.common import auth as auth_module

    sink = recorder(profile)
    monkeypatch.setattr(auth_module, "_db_ready", True)
    monkeypatch.setattr(auth_module, "_memory_store_denied", lambda operation: False)
    _as_authenticated_user(monkeypatch, auth_module)
    monkeypatch.setattr(profile, "_initialized", False)
    monkeypatch.setattr(profile, "_conn", lambda: _Store(label="profile"))
    return sink


def test_the_missing_user_profiles_table_reads_200_without_the_stored_columns(
    production, recorder, monkeypatch
):
    sink = _profile_store(monkeypatch, recorder)

    response = _login_client().get("/api/v1/profile", headers=_headers())

    assert response.status_code == 200, response.text
    assert response.json()["profile"]["username"] == ADMIN
    assert "updated_at" not in response.json()["profile"], "PG 那一腿没读成，不许冒充读成了"
    assert sink.mentions("load skipped"), sink.lines
    assert any(SENTENCE in line for _level, line in sink.lines), sink.lines


def test_the_missing_user_profiles_table_refuses_503_not_the_authored_500(
    production, recorder, monkeypatch
):
    """R383 改口（本件基点记的是病灶脸：路由自己写的那句 500 ``画像保存失败``）。

    那句 500 把「存储没迁移」「存储没起」「真的写砸了」三件事压成一句它自己都不知道原因的话。
    现在前两格各自拒答 503 ``storage_unavailable``（两行日志分头说清排查路），500 只留给第三格。
    store 层仍然一枚 HTTP 异常都不发起：它抛具名拒答，出口那一次窄翻译在 `app/api/v1/auth.py`。
    """
    sink = _profile_store(monkeypatch, recorder)

    response = _login_client().put(
        "/api/v1/profile", json={"position": "boss", "preferences": ["r377"]}, headers=_headers()
    )

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}, "那句 500 还在答：捕获面没换成拒答"
    assert "画像保存失败" not in response.text
    assert BARE_500_BODY not in response.text
    assert sink.mentions("save failed") == [], "缺表那一格还咽下去 = 两格又并回一张脸"
    assert sink.mentions("code=storage_unavailable migration="), sink.lines


# ========================================================== 现场量测：long_term.py 没有 HTTP 脸
def test_the_missing_memories_table_answers_empty_at_the_function_boundary(
    production, recorder, monkeypatch
):
    """`remember()`/`recall()` 是 long_term 唯一的对外形状，两枚都答「空」而不是上抛（:176/:192）。"""
    sink = recorder(long_term)
    monkeypatch.setattr(long_term, "psycopg", object())
    monkeypatch.setattr(long_term, "_initialized", False)
    monkeypatch.setattr(long_term, "_conn", lambda: _Store(label="memory"))
    monkeypatch.setattr(long_term, "_embed", lambda texts: None)

    assert long_term.recall("r377-user", "问题", k=3) == []
    assert long_term.remember("r377-user", "一条记忆") is False
    assert sink.mentions("read failed"), sink.lines
    assert sink.mentions("write failed"), sink.lines
    assert sum(bool(SENTENCE in line) for _level, line in sink.lines) == 2


def _importers_of(dotted: str) -> list[str]:
    """`app/**` 里哪些文件 import 了这一枚模块（按 AST 的 import 边判，不算字符串巧合）。"""
    found: list[str] = []
    for path in sorted((REPO / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            label = str(path.relative_to(REPO)).replace("\\", "/")
            if isinstance(node, ast.ImportFrom) and (node.module or "") == dotted:
                found.append(f"{label}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == dotted:
                        found.append(f"{label}:{node.lineno}")
    return sorted(set(found))


def test_the_memory_legs_have_no_http_exit_of_their_own():
    """`long_term` 在 `app/**` 里只被 graph 节点用，没有任何 API 模块 import 它。

    起图跑模型不在本单许可内（禁模型、禁服务），所以这一枚的 HTTP 脸只取到「函数边界」那一层：
    `remember()`/`recall()` 各自把错咽在 :176/:192。下面那枚 import 边就是「它没有 API 出口」的证据。
    """
    importers = _importers_of("app.memory.long_term")
    api_importers = [edge for edge in importers if edge.startswith("app/api/")]

    assert importers, "app.memory.long_term 的 import 边整个不见了，本件的判据失效"
    assert api_importers == [], f"有人给 long_term 新接了 HTTP 出口：可达性判定要重做 {api_importers}"


# =========================================== 效力边界：源码层继续抛 RuntimeError，本单一个字没改
@pytest.mark.parametrize(
    ("relative", "table", "expected"),
    [
        (
            "app/memory/long_term.py",
            "memories",
            "memories table is required in production; run migrations first",
        ),
        (
            "app/memory/profile.py",
            "user_profiles",
            "user_profiles table is required in production; run migrations first",
        ),
        (
            "app/documents/catalog.py",
            "document_versions",
            "document_versions table is required in production; run migrations first",
        ),
    ],
)
def test_the_source_layer_still_raises_the_named_sentence(monkeypatch, relative, table, expected):
    """既有钉（`tests/test_memory_production_schema.py:83`）打的就是这一层：本单不替换基类语义。"""
    from fastapi import HTTPException

    module = {"app/memory/long_term.py": long_term, "app/memory/profile.py": profile,
              "app/documents/catalog.py": catalog}[relative]
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(module, "_initialized", False, raising=False)
    monkeypatch.setattr(module, "psycopg", object(), raising=False)
    monkeypatch.setattr(module, "_conn", lambda: _Store(tables=(), label=table))

    with pytest.raises(RuntimeError) as caught:
        module._ensure()

    assert str(caught.value) == expected
    assert not isinstance(caught.value, HTTPException)
    assert type(caught.value) is RuntimeError, "本单没给这四枚模块加具名子类：一句都不该有"


def test_the_auth_source_layer_still_raises_the_named_sentence(monkeypatch):
    """`tests/test_bootstrap_admin.py:107` 的家：`_create_schema` 本身照旧抛裸 RuntimeError。"""
    from fastapi import HTTPException

    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError) as caught:
        auth._create_schema(_Store(label="users"))

    assert str(caught.value) == "users table is required in production; run migrations first"
    assert not isinstance(caught.value, HTTPException)
    assert type(caught.value) is RuntimeError
