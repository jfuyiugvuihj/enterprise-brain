"""R246「改话不改骨」的判据钉：就绪承诺必须与代码同形。

本文件**只读源码、绝不 import `app.common.auth`**：那枚模块在 import 期就向 `DATABASE_URL`
发一次真握手（`tests/conftest.py:41` 把测试期 DSN 钉在保留端口 1 才敢碰它）。而本单判的四件事
——`_get_conn()` 体内不许再有 `_db_ready` 的写点、探针失败那句 warning 必须说实话、
"本文件之外另有 6 处读者"必须与代码同形、把死码塞回副本判器必须报——全都能在 AST 上判，
一次运行都不必发起。

钉与判据的对应：
1. `test_get_conn_body_has_no_db_ready_write`（判据 1 + 3）：可达性证明链的机器化版本。
   走到 `if not _db_ready` 之前必须先过 `if _using_memory_store(): return _FakeConn()`，而后者
   恰在 `_db_ready` 为假时为真 ⇒ 那一段恒不可达；本单删掉它，并用这枚钉钉住"不许再长回来"，
   顺带钉住"不许把建表挪到请求路径上"（那是产品行为变更，本单明令不做）。
2. `test_get_conn_still_shields_the_memory_branch_first` / `test_the_selection_counts_...`
   （判据 1 的"行为零变化"半边）：正面复算 `tests/test_r229_connect_retry.py:155`（调用点
   `_raw_conn` 2 枚 / `_get_conn` 8 枚（R290 加了第 8 枚）与 `:292`（未就绪返回 `_FakeConn`）、
   `tests/test_r230_db_ready_selfheal.py:522`（`_get_conn` 翻不了这枚旗）各自判的那件事，
   证明本单的删除没改变它们，而不是只喊"全绿"。
3. `test_the_two_lies_are_gone_from_the_source` + `test_probe_failure_warning_...` +
   `test_the_comment_above_the_probe_names_the_real_ddl_owner`（判据 2）：原文案换成实话，
   但级别仍是 warning、仍带原异常——降级成 info 就是把问题藏起来。
4. `test_the_six_reader_claim_matches_ast`（判据 4）：`:231` 那句读数由 AST 现算复核。
5. `test_counter_evidence_dead_block_reinserted_gets_reported`（判据 3 的反证）：副本落在工作树外，
   收尾用 sha256 自证工作树没被写脏（写法照 `tests/test_r233_undefined_root_names.py:238`）。
"""
import ast
import hashlib
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTH_REL = "app/common/auth.py"
AUTH = ROOT / AUTH_REL
SCAN_SCOPES = ("app", "scripts", "deploy")
FLAG = "_db_ready"

#: 基点 `2ab2369` 上 `_get_conn()` 的原文，逐字抄下来（反证钉要把它塞回一份临时副本）。
PRE_R246_GET_CONN = '''def _get_conn():
    global _db_ready
    if _using_memory_store():
        return _FakeConn()
    conn = _connect_for_request("user store access")
    if not _db_ready:
        try:
            _create_schema(conn)
            _db_ready = True
        except Exception:
            pass
    return conn
'''

#: `:231` 那句声明的形状：数目 + "各一枚" + 名单。写成人话，判器按话读。
READER_CLAIM = re.compile(r"本文件之外另有\s*(\d+)\s*处读者，各一枚（([^）]*)）")

#: 本单删掉的两句假话的字面片段，任何一条都不许回到源码里。
LIES = (
    "将在首次连接时建表",
    "会重建表",
    "真正的补救在请求路径",
)


# ------------------------------------------------------------------ 判器（AST 半边）
def _auth_source() -> str:
    return AUTH.read_text(encoding="utf-8")


def _top_level_function(source: str, name: str) -> ast.FunctionDef:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"顶层找不到 {name}()：靶子变了，请连本钉一起改，别摘断言")


def _callee_name(call: ast.Call) -> str:
    parts = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _flag_writes(fn: ast.AST) -> list[tuple[int, str]]:
    """函数体内一切能把 `_db_ready` 摆动的写法：赋值 / 注解赋值 / 增量赋值 / 海象 / global。

    只认 `ast.Assign` 是最省事的做法，也是本单最不该省事的地方：R230 那枚死码就是藏在
    `try:` 里的一枚赋值，判器必须按"写法"而不是按"长相"收口（`ast.walk` 自带下钻，嵌套几层都跑不掉）。
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == FLAG:
                    kind = "assign"
                    if isinstance(node, ast.AnnAssign):
                        kind = "annotated_assign"
                    elif isinstance(node, ast.AugAssign):
                        kind = "augmented_assign"
                    found.append((target.lineno, kind))
        elif isinstance(node, ast.NamedExpr):
            if isinstance(node.target, ast.Name) and node.target.id == FLAG:
                found.append((node.target.lineno, "walrus"))
        elif isinstance(node, ast.Global) and FLAG in node.names:
            found.append((node.lineno, "global"))
    return sorted(found)


def _ddl_calls(fn: ast.AST) -> list[int]:
    """函数体内的 `_create_schema(...)` 直接调用点——请求路径建表就是这一枚要拦的写法。"""
    return sorted(
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and _callee_name(node) == "_create_schema"
    )


def _message_parts(node: ast.expr) -> tuple[str, list[str]]:
    """拆一条日志消息：返回（拼起来的字面文本, 插进去的变量名）。"""
    values = node.values if isinstance(node, ast.JoinedStr) else [node]
    text: list[str] = []
    interpolated: list[str] = []
    for value in values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            text.append(value.value)
        elif isinstance(value, ast.FormattedValue):
            inner = value.value
            interpolated.append(inner.id if isinstance(inner, ast.Name) else ast.dump(inner))
    return "".join(text), interpolated


def _import_probe_warning(source: str) -> ast.Call:
    """取 `if psycopg is not None:` 那枚 import 期探针的 `except` 分支里的 `logger.warning` 调用。"""
    for node in ast.parse(source).body:
        if not isinstance(node, ast.If) or ast.unparse(node.test) != "psycopg is not None":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Try):
                continue
            for handler in inner.handlers:
                assert ast.unparse(handler.type) == "Exception", ast.unparse(handler.type)
                assert handler.name == "exc", handler.name
                for statement in handler.body:
                    for call in ast.walk(statement):
                        if isinstance(call, ast.Call):
                            name = _callee_name(call)
                            if name.startswith("logger."):
                                return call
    raise AssertionError("import 期探针的 except 分支里没有 logger.* 调用：日志被删了或被降级藏起来了")


def _read_sites_in(source: str) -> list[int]:
    """一处"读者" = 一行把 `_db_ready` 的值读了出来：Name 载入 / Attribute 载入 / getattr·hasattr 常量名。

    写点（Store）与 `global` 声明都不算读者——`:231` 那句说的是"把它们一起翻正"的下游。
    """
    linenos: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id == FLAG and isinstance(node.ctx, ast.Load):
            linenos.add(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == FLAG and isinstance(node.ctx, ast.Load):
            linenos.add(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "hasattr"}
            and any(isinstance(a, ast.Constant) and a.value == FLAG for a in node.args[1:2])
        ):
            linenos.add(node.lineno)
    return sorted(linenos)


def _reader_inventory() -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """返回（本文件之外的读点，本文件内的读点），范围 = app / scripts / deploy 全量 .py。"""
    outside: list[tuple[str, int]] = []
    inside: list[tuple[str, int]] = []
    for scope in SCAN_SCOPES:
        base = ROOT / scope
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            sites = [(rel, line) for line in _read_sites_in(path.read_text(encoding="utf-8"))]
            if rel == AUTH_REL:
                inside = sites
            else:
                outside.extend(sites)
    return outside, inside


# ------------------------------------------------------------------------ 判据 1 + 3
def test_get_conn_body_has_no_db_ready_write():
    """可达性钉：`_get_conn()` 体内不存在 `_db_ready` 赋值，也不存在 `global` 声明。

    这条就是那三行证明链的机器化版本（行号取基点 `2ab2369`：`:164` 的 `_using_memory_store() = psycopg is None or not
    _db_ready` ⇒ `:487` 的 return 恒在前 ⇒ `:490` 的 `not _db_ready` 恒假）。既然恒不可达，留着它就是在给
    "运行期会自愈"背书，所以判的不是"有没有跑到"，而是"代码里还长不长着"。
    """
    fn = _top_level_function(_auth_source(), "_get_conn")

    writes = _flag_writes(fn)
    assert writes == [], f"`_get_conn()` 体内又长出 `_db_ready` 的写点：{writes}"
    assert _ddl_calls(fn) == [], "`_get_conn()` 不许把建表接回请求路径——那是产品行为变更，本单明令不做"


def test_get_conn_still_shields_the_memory_branch_first():
    """删除是"改话不改骨"：函数体仍是「先挡内存支，再连一枚」，两枚语句一枚不多一枚不少。

    这枚钉同时是 `tests/test_r229_connect_retry.py:292`（未就绪返回 `_FakeConn`）与
    `tests/test_r230_db_ready_selfheal.py:522`（`_get_conn` 翻不了这枚旗）所判那件事的结构性凭据：
    守卫仍在第一句、返回的仍是 `_FakeConn()`，而全函数没有任何写点。
    """
    fn = _top_level_function(_auth_source(), "_get_conn")

    assert [type(statement).__name__ for statement in fn.body] == ["If", "Return"], fn.body
    guard = fn.body[0]
    assert _callee_name(guard.test) == "_using_memory_store", ast.unparse(guard.test)
    assert guard.orelse == [] and len(guard.body) == 1, guard.body
    shield = guard.body[0]
    assert isinstance(shield, ast.Return) and _callee_name(shield.value) == "_FakeConn", ast.unparse(shield)

    tail = fn.body[1]
    assert _callee_name(tail.value) == "_connect_for_request", ast.unparse(tail.value)
    labels = [argument.value for argument in tail.value.args]
    assert labels == ["user store access"], f"建连的 operation 标签必须与基点同字，实到 {labels}"


def test_the_two_lies_are_gone_from_the_source():
    """`:472` 那句"真正的补救在请求路径上（`_get_conn` 会重建表）"与 `:479` 那句"将在首次连接时建表"都不许回来自。"""
    source = _auth_source()

    for lie in LIES:
        assert lie not in source, f"假话回到了源码里：{lie}"


def test_probe_failure_warning_still_warns_and_still_carries_the_exception():
    """判据 2 的下半：文案可以换，级别与异常不能动——warning 仍是 warning，仍带 `exc`。"""
    call = _import_probe_warning(_auth_source())

    assert _callee_name(call) == "logger.warning", _callee_name(call)
    assert len(call.args) == 1, call.args
    text, interpolated = _message_parts(call.args[0])
    assert interpolated == ["exc"], f"原异常必须仍然带在日志里，实插值 {interpolated}"
    assert "不建表" in text, text
    assert "内存表" in text, text
    assert "重启" in text, text
    assert "migrations/0003" in text, text


def test_the_comment_above_the_probe_names_the_real_ddl_owner():
    """判据 2 的上半：探针上方那条注释必须写清"请求路径不补救 + 生产建表归 migrations/0003"。"""
    source = _auth_source()

    comments = [line.strip() for line in source.splitlines() if line.strip().startswith("#")]
    honest = [line for line in comments if "请求路径不补救" in line and "migrations/0003" in line]
    assert honest, "探针失败的注释必须说实话：请求路径不补救，生产建表归 migrations/0003"
    assert [line for line in comments if "不自愈" in line and "重启" in line], (
        "注释还得写清非生产侧不自愈，直到进程重启——这正是运维要知道的那半句"
    )


# ------------------------------------------------------------------------ 判据 4
def test_the_six_reader_claim_matches_ast():
    """`:231` 那句"本文件之外另有 6 处读者，各一枚（…）"必须是 AST 现算能复核的读数。

    名单与数目一起判：多一枚读者而注释没改 = 又一句假话，判红。范围含 scripts / deploy，
    实测那两棵为 0 枚，所以"本文件之外"这句在全仓口径下也成立。
    """
    docstring = ast.get_docstring(_top_level_function(_auth_source(), "_retry_readiness_probe"))
    assert docstring, "`_retry_readiness_probe` 的 docstring 没了，那句读数无处核"
    match = READER_CLAIM.search(" ".join(docstring.split()))
    assert match, "『本文件之外另有 N 处读者，各一枚（…）』这句声明必须还在，且判器读得出它的形状"

    stated = int(match.group(1))
    named = [token.strip() for token in match.group(2).split("/") if token.strip()]
    outside, inside = _reader_inventory()

    assert stated == len(outside), f"声明 {stated} 处读者，AST 实测 {len(outside)} 处：{outside}"
    assert len(named) == len(set(named)) == stated, f"名单自己就对不上：{named}"
    assert sorted(named) == sorted({Path(rel).stem for rel, _ in outside}), (
        f"名单与实测的模块不符：声明 {sorted(named)} 实到 {sorted({Path(rel).stem for rel, _ in outside})}"
    )
    per_file = Counter(rel for rel, _ in outside)
    assert set(per_file.values()) == {1}, f"「各一枚」不成立：{dict(per_file)}"
    assert inside, "本文件内的读点用于对照结论文档；判的是本单不动它的语义"


def test_the_dead_branch_would_have_been_a_seventh_reader_line():
    """删除的读数记账：本文件内的读点此刻是 3 枚（`_using_memory_store` / `user_storage_state` / 重探）。

    基点上是 4 枚——第四枚就是那段恒不可达的 `if not _db_ready:`。这枚钉把"少了一枚读者"这件事
    写在明面上，免得后来人以为本单顺手改了选路。
    """
    _outside, inside = _reader_inventory()

    assert len(inside) == 3, inside


# ------------------------------------------------------------------ 判据 1 的调用点账
def test_the_selection_counts_the_r229_nail_pins_still_hold():
    """正面复算 `tests/test_r229_connect_retry.py:155` 判的那件事：选路依据一枚没动。

    `_raw_conn()` 仍是 2 枚（import 探针 + `_connect_for_request` 内部）、`_get_conn()` 的调用点
    仍是 7 枚（R290 之后为 8 枚：新增 `update_department` 那支归属写口走同一条选路）。本单唯一改动的计数是 `_create_schema` 调用点 3 → 2，函数本体照旧
    留在文件里——`tests/test_bootstrap_admin.py` 十处以上直接调它，删不得。
    """
    tree = ast.parse(_auth_source())
    raw = get = schema = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _callee_name(node)
            raw += name == "_raw_conn"
            get += name == "_get_conn"
            schema += name == "_create_schema"

    assert (raw, get) == (2, 8), f"选路计数漂移，R229 的判据就塌了：_raw_conn={raw} _get_conn={get}"
    assert schema == 2, f"`_create_schema` 调用点应为 2 枚（import 探针 + R230 重探），实测 {schema}"
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "_create_schema" for node in tree.body
    ), "`_create_schema` 本体必须保留：建表与播种都靠它，bootstrap 那族钉直接调它"


# ------------------------------------------------------------------------ 反证钉
def test_counter_evidence_dead_block_reinserted_gets_reported(tmp_path):
    """门仍有牙：把删掉的那段死码塞回一份**工作树外**的副本，判器必须把写点和 DDL 都报出来。

    只判"今天在位"的门是死的——删掉的代码不需要门，能被塞回来的代码才需要。副本落到 `tmp_path`，
    收尾再核一次 `auth.py` 的 sha256 与开头一致：本枚不许改工作树取证（写法照
    `tests/test_r233_undefined_root_names.py:238`）。
    """
    digest_before = hashlib.sha256(AUTH.read_bytes()).hexdigest()
    source = _auth_source()
    assert PRE_R246_GET_CONN.rstrip("\n") not in source, "那段死码又回到工作树里了，本单的删除没落地"

    current = ast.get_source_segment(source, _top_level_function(source, "_get_conn"))
    assert current, "取不到 `_get_conn` 的源码段，反证钉无从下手"
    mutated = source.replace(current, PRE_R246_GET_CONN.rstrip("\n"), 1)
    assert mutated != source, "塞不回去就不是反证"
    ast.parse(mutated)

    copy = tmp_path / "auth_with_the_dead_block_back.py"
    assert not copy.resolve().is_relative_to(ROOT), "副本必须落在工作树之外"
    copy.write_text(mutated, encoding="utf-8")

    reinserted = _top_level_function(copy.read_text(encoding="utf-8"), "_get_conn")
    writes = _flag_writes(reinserted)
    assert sorted(kind for _lineno, kind in writes) == ["assign", "global"], (
        f"塞回原始死码，判器必须报出那枚赋值和那行 global，实到 {writes}"
    )
    assert _ddl_calls(reinserted), "副本里 `_get_conn` 又把建表接回请求路径，判器却哑了"
    assert _flag_writes(_top_level_function(_auth_source(), "_get_conn")) == [], "工作树里那枚写点没被删干净"
    assert hashlib.sha256(AUTH.read_bytes()).hexdigest() == digest_before, "反证钉不许动工作树"


#: 别的写法也要报得出：真把旗摆动的形态不止 `x = True` 一种。
WRITE_SHAPES = (
    ("    _db_ready = True", ["assign"]),
    ("    _db_ready: bool = True", ["annotated_assign"]),
    ("    _db_ready |= True", ["augmented_assign"]),
    ("    if (_db_ready := True):\n        return None", ["walrus"]),
    ("    global _db_ready", ["global"]),
    (
        "    if not _db_ready:\n        try:\n            _create_schema(conn)\n"
            "            _db_ready = True\n        except Exception:\n            pass",
        ["assign"],
    ),
)


@pytest.mark.parametrize("snippet, expected", WRITE_SHAPES)
def test_counter_evidence_every_write_shape_is_caught(snippet, expected):
    """判器按"写法"收口，不按某一行的长相：赋值 / 注解赋值 / 增量赋值 / 海象 / global / 藏在 try 里的赋值。

    这一族是"摘掉修复必照样报"的另一半：本单钉的是 R246 删掉的那一枚具体形状，参数化钉钉的是
    同一件事的其它形状——将来谁换个写法把旗摆回请求路径，照样红。
    """
    source = f"def _get_conn():\n{snippet}\n    return None\n"
    fn = _top_level_function(source, "_get_conn")

    assert [kind for _lineno, kind in _flag_writes(fn)] == expected, _flag_writes(fn)


def test_the_checker_does_not_confuse_a_read_with_a_write():
    """反向的门禁：只读不写的那一行（`if not _db_ready:`）不许被报成写点——否则门是哑的也是吵的。

    `_get_conn` 里那一段恒不可达靠的是"读"，判器如果连读都报，将来正常代码一多就没人信它了。
    """
    source = "def _get_conn():\n    if not _db_ready:\n        return _FakeConn()\n    return None\n"
    fn = _top_level_function(source, "_get_conn")

    assert _flag_writes(fn) == [], _flag_writes(fn)
    assert _read_sites_in(source) == [2], _read_sites_in(source)
