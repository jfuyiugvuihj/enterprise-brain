"""R186 · 契约里那两枚成功体字段必须与 data.py 的实际构形同源（全离线：不起服务、不连库、不打模型）。

R180 把行级判定写进了 ``preview.row_scope`` 与 ``GET /data-files`` 的 ``restricted``，却一字未动
``docs/api/contract-v1.md`` —— 那枚文件是前端的唯一真相源，不补就等于让下一个人继续猜。R186 补写
了那一节，本文件钉的是**补的那一节不许漂**。

手法照 ``tests/test_r152_activity_feedback_docs.py``：散文里不许出现任何一处手抄的形状。

  ① 键集合用 AST 从 ``app/api/v1/data.py`` 的**实际构形处**现抠（``_row_scope_status`` 里那个
     dict、``result["restricted"]`` 里那个 dict），与契约文档里的 JSON 块和表格逐键对判，双向：
     文档多列一枚（替后端开洞）与少列一枚（前端无从可读到）都红；
  ② ``code`` 的取值域从 data.py 的常量与 ``app/agents/tools.py`` 那一份唯一翻译层现取，与文档
     那一行取值域对判 —— 不许出现第三枚码，也不许文档写窄了；
  ③ ``message`` 的**有无**钉成不变量：对一批输入过真函数 ``_row_scope_status``，断言
     ``("message" in status) == (status["code"] == row_scope_denied)`` 恒成立，正是文档那句
     「attached under the same condition」；``no_visible_rows`` 那一支后端故意不给，文档与代码同
     时必须哑（判据 2 的后端半格）；
  ④ 端点路径与字段归属从装饰器与 ``main.py`` 的 prefix 现算，文档把哪枚字段挂在哪条路上不许写错；
  ⑤ ``restricted.message`` 那句人话按 f-string 的**字节**复原成模板与文档对判，且文档那条例子
     句必须能被模板现算出来；``restricted`` 的键集合里不许出现任何一枚装得下文件名的键 ——
     「不点名文件」这条裁决既钉散文也钉形状。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"
MAIN_PY = ROOT / "app" / "main.py"
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"

SECTION_HEADING = "## Dataset Row-Level Visibility"
PREVIEW_SUBHEAD = "`GET /api/v1/data-files/{filename}/preview` -> `preview.row_scope`"
CATALOG_SUBHEAD = "`GET /api/v1/data-files` -> `restricted`"
DOMAIN_LINE = re.compile(r"^`?row_scope\.code`? value domain: (.+)$", re.MULTILINE)


def _text(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(ROOT)} 不在了"
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _section() -> str:
    text = _text(CONTRACT)
    start = text.find(SECTION_HEADING)
    assert start != -1, f"契约里找不到 {SECTION_HEADING!r} 这一节：改名可以，请连本钉一起改"
    tail = text[start + len(SECTION_HEADING):]
    end = re.search(r"^## ", tail, re.MULTILINE)
    section = text[start:start + len(SECTION_HEADING) + (end.start() if end else len(tail))]
    assert len(section) > 1500, "这一节短得不对劲，后面每枚钉都会变成空响"
    return section


def _subsections() -> dict[str, str]:
    section = _section()
    chunks = re.split(r"^### ", section, flags=re.MULTILINE)
    out = {}
    for chunk in chunks[1:]:
        head, _, body = chunk.partition("\n")
        out[head.strip()] = body
    assert PREVIEW_SUBHEAD in out and CATALOG_SUBHEAD in out, (
        f"契约的两个子节标题被挪了位置：{sorted(out)}"
    )
    return out


def _json_blocks(body: str) -> list[dict]:
    blocks = re.findall(r"```json\n(.*?)\n```", body, re.DOTALL)
    assert blocks, "这一节里一枚 JSON 块都没有，键集合的钉就是空响"
    return [json.loads(block) for block in blocks]


def _table_keys(body: str) -> list[str]:
    return re.findall(r"^\|\s*`([a-z_]+)`\s*\|", body, re.MULTILINE)


# ==================== 从 app/api/v1/data.py 现抠形状（AST，零手抄） ====================


@pytest.fixture(scope="module")
def data_tree() -> ast.Module:
    return ast.parse(_text(DATA_PY))


def _function(tree: ast.Module, name: str) -> ast.AST:
    found = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"data.py 里 {name} 应当只有一处，实取 {len(found)} 处"
    return found[0]


def _dict_keys(node: ast.Dict) -> list[str]:
    keys = []
    for key in node.keys:
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            "构形处的键必须是字面量字符串，否则本钉读不到形状"
        )
        keys.append(key.value)
    return keys


def _subscript_targets(node: ast.AST, owner: str) -> dict[str, ast.expr]:
    """``owner["key"] = <value>`` 形式的赋值，返回 key -> value 表达式。"""
    out: dict[str, ast.expr] = {}
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign) or not isinstance(sub.targets[0], ast.Subscript):
            continue
        target = sub.targets[0]
        if isinstance(target.value, ast.Name) and target.value.id == owner:
            if isinstance(target.slice, ast.Constant):
                out[target.slice.value] = sub.value
    return out


def _row_scope_shape(tree: ast.Module) -> dict:
    fn = _function(tree, "_row_scope_status")
    base = None
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Dict):
            if isinstance(sub.targets[0], ast.Name) and sub.targets[0].id == "status":
                base = _dict_keys(sub.value)
    assert base, "_row_scope_status 里那个 status dict 找不到了：构形处改了形状请同步本钉"
    optional = _subscript_targets(fn, "status")
    guarded = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If) and _subscript_targets(node, "status")
    ]
    assert len(optional) == 1 and "message" in optional, (
        f"row_scope 的可选键实取 {sorted(optional)}：契约只登记了 message 一枚"
    )
    assert len(guarded) == 1, "message 那一枚键必须且只能被一个条件包着（有才挂，不许无条件挂空串）"
    return {
        "required": base,
        "optional": sorted(optional),
        "guard": ast.unparse(guarded[0].test),
        "value_source": ast.unparse(optional["message"]),
    }


def _restricted_shape(tree: ast.Module) -> dict:
    fn = _function(tree, "list_data_files")
    assigns = _subscript_targets(fn, "result")
    assert "restricted" in assigns, "目录里那枚 result[`restricted`] 构形处不见了"
    payload = assigns["restricted"]
    assert isinstance(payload, ast.Dict), "restricted 不再是 dict 字面量：请同步契约与本钉"
    guarded = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.If) and "restricted" in _subscript_targets(node, "result")
    ]
    assert len(guarded) == 1, "restricted 必须只在真有拒绝时才挂（无拒绝=不挂键，不是挂零）"
    fields = {key.value: value for key, value in zip(payload.keys, payload.values)}
    message = fields["message"]
    assert isinstance(message, ast.JoinedStr), "restricted.message 不再是拼 count 的 f-string"
    template_parts = []
    for part in message.values:
        if isinstance(part, ast.Constant):
            template_parts.append(str(part.value))
        elif isinstance(part, ast.FormattedValue):
            assert ast.unparse(part.value) == "restricted_count", (
                f"句子里插的值换了：{ast.unparse(part.value)}（契约那行模板写的是 count）"
            )
            template_parts.append("{count}")
        else:  # pragma: no cover
            raise AssertionError("restricted.message 出现了读不懂的节点")
    return {
        "keys": _dict_keys(payload),
        "guard": ast.unparse(guarded[0].test),
        "template": "".join(template_parts),
    }


def _route_key(tree: ast.Module, function_name: str) -> tuple[str, str]:
    fn = _function(tree, function_name)
    routes = []
    for decorator in fn.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            if decorator.func.attr in {"get", "post", "put", "delete"} and decorator.args:
                arg = decorator.args[0]
                assert isinstance(arg, ast.Constant), "路由路径不再是字面量：本钉读不到它"
                routes.append((decorator.func.attr, str(arg.value)))
    assert routes, f"{function_name} 上没有路由装饰器了"
    assert len(routes) == 1, f"{function_name} 挂了多条路由：本钉要按条对判"
    return routes[0]


def _prefix(main_tree: ast.Module) -> str:
    for node in ast.walk(main_tree):
        if (
            isinstance(node, ast.Call)
            and ast.unparse(node.func).endswith("include_router")
            and node.args
            and ast.unparse(node.args[0]) == "data.router"
        ):
            for keyword in node.keywords or []:
                if keyword.arg == "prefix":
                    return keyword.value.value
    raise AssertionError("main.py 不再以 include_router(data.router, prefix=...) 挂载数据路由")


# ==================== ① 键集合：文档与构形处双向对判 ====================


def test_documented_row_scope_keys_are_the_keys_the_constructor_builds():
    tree = ast.parse(_text(DATA_PY))
    shape = _row_scope_shape(tree)
    body = _subsections()[PREVIEW_SUBHEAD]

    assert _table_keys(body) == shape["required"] + shape["optional"], (
        "契约表格里 row_scope 的键清单与实际构形处不再是同一串：多列是替后端开洞，少列是前端无从可读"
    )
    blocks = [item["row_scope"] for item in _json_blocks(body) if "row_scope" in item]
    assert len(blocks) >= 2, "至少要有一枚常态块与一枚带 message 的块，否则形状没钉住"
    for block in blocks:
        assert set(block) <= set(shape["required"] + shape["optional"]), (
            f"JSON 例子里出现了构形处不会产出的键：{sorted(set(block) - set(shape['required'] + shape['optional']))}"
        )
    plain = [block for block in blocks if block["code"] == ""]
    assert plain and all(set(block) == set(shape["required"]) for block in plain), (
        "code 为空那一支的例子不许带 message：契约说 message 只跟着 row_scope_denied 走"
    )


def test_documented_restricted_keys_are_the_keys_the_catalog_builds():
    tree = ast.parse(_text(DATA_PY))
    shape = _restricted_shape(tree)
    body = _subsections()[CATALOG_SUBHEAD]

    assert _table_keys(body) == shape["keys"], "restricted 的键清单与目录构形处不同源"
    blocks = [item["restricted"] for item in _json_blocks(body) if "restricted" in item]
    assert blocks, "restricted 没有 JSON 例子块"
    for block in blocks:
        assert set(block) == set(shape["keys"]), f"例子块的键与构形处不等：{sorted(block)}"


# ==================== ② 取值域：与 data.py 常量及唯一翻译层同源 ====================


def test_documented_code_domain_is_exactly_what_the_route_can_emit():
    from app.agents import tools
    from app.api.v1 import data

    line = DOMAIN_LINE.search(_section())
    assert line, "契约里那一行 row_scope.code value domain 不见了：取值域没有唯一出处"
    documented = [item.strip() for item in line.group(1).split("|")]
    documented = [item.replace('""', "") for item in documented]
    assert documented == [data.ROW_SCOPE_DENIED, data.NO_VISIBLE_ROWS, ""], (
        f"文档写的取值域 {documented} 与 data.py 的常量不再是同一串"
    )
    # 取值域的另一半：码不是 data.py 自己发明的，它只能来自 tools.py 那一份翻译层。
    translated = set(tools._ROW_SCOPE_PUBLIC_CODES.values()) | {tools._NO_VISIBLE_ROWS_CODE}
    assert translated == {data.ROW_SCOPE_DENIED, data.NO_VISIBLE_ROWS}, (
        f"翻译层产出的公开码与路由常量脱钩了：{sorted(translated)}"
    )
    assert set(documented) == translated | {""}, "文档、路由、翻译层三方不再是同一串码"


def test_the_message_key_exists_precisely_when_the_code_says_denied():
    from app.api.v1 import data

    shape = _row_scope_shape(ast.parse(_text(DATA_PY)))
    assert shape["guard"] == "message", (
        "message 的挂载条件换了写法：契约那句「present only when there is something to say」要跟着改"
    )
    cases = {
        "foreign_rows": {
            "rows_in": 3, "rows_visible": 0, "reason_code": "department_scope",
            "account_department": "财务", "rows_hidden_by_department": 3,
            "rows_hidden_blank_department": 0, "rows_hidden_account_department": 0,
        },
        "accountless": {"rows_in": 5, "rows_visible": 0, "reason_code": "authorization_unavailable"},
        "legacy_open": {"rows_in": 2, "rows_visible": 0, "reason_code": "legacy_open_department_scope",
                        "rows_hidden_by_department": 2},
        "other_dimension": {"rows_in": 4, "rows_visible": 0, "reason_code": "department_column_missing"},
        "empty_table": {"rows_in": 0, "rows_visible": 0, "reason_code": "department_scope"},
        "partial": {"rows_in": 120, "rows_visible": 40, "reason_code": "department_scope",
                    "rows_hidden_by_department": 80},
        "all_visible": {"rows_in": 7, "rows_visible": 7, "reason_code": "administrator_scope"},
    }
    for name, scope_info in cases.items():
        status = data._row_scope_status(dict(scope_info))
        assert set(status) <= set(shape["required"] + shape["optional"]), (name, status)
        assert ("message" in status) == (status["code"] == data.ROW_SCOPE_DENIED), (
            f"{name}: message 的有无与 code 脱钩了，契约那句「同一条件下才挂」当场是假话 {status}"
        )
        assert status["rows_in"] == scope_info["rows_in"]
        assert status["rows_visible"] == scope_info["rows_visible"]
        if status["code"] == data.NO_VISIBLE_ROWS:
            assert "message" not in status, f"{name}: 后端故意沉默的那一支又被人塞回了因由"
        if name in ("empty_table", "partial", "all_visible"):
            assert status["code"] == "", f"{name}: 真空表/部分可见/全部可见被冒充成行级拒绝"
        if name == "partial":
            assert 0 < status["rows_visible"] < status["rows_in"], (
                "契约那句「rows_in > rows_visible > 0 仍是正常答案」失去事实依据"
            )


# ==================== ④ 端点与字段归属：路径现算，不许写错格子 ====================


def test_documented_endpoints_are_the_registered_routes_that_carry_those_keys():
    tree = ast.parse(_text(DATA_PY))
    prefix = _prefix(ast.parse(_text(MAIN_PY)))

    preview_method, preview_path = _route_key(tree, "preview_data_file")
    catalog_method, catalog_path = _route_key(tree, "list_data_files")
    preview_endpoint = f"{preview_method.upper()} {prefix}{preview_path}"
    catalog_endpoint = f"{catalog_method.upper()} {prefix}{catalog_path}"

    subheads = _subsections()
    assert set(subheads) == {PREVIEW_SUBHEAD, CATALOG_SUBHEAD}, "契约这一节的子节数变了，先看清是谁的格子"
    assert preview_endpoint == f"GET /api/v1/data-files/{'{filename}'}/preview", preview_endpoint
    assert catalog_endpoint == "GET /api/v1/data-files", catalog_endpoint
    assert PREVIEW_SUBHEAD == f"`{preview_endpoint}` -> `preview.row_scope`", (
        f"契约的小节标题不再把 {preview_endpoint} 与 row_scope 绑在同一行上"
    )
    assert CATALOG_SUBHEAD == f"`{catalog_endpoint}` -> `restricted`", (
        f"契约的小节标题不再把 {catalog_endpoint} 与 restricted 绑在同一行上"
    )

    # 字段归属：预览那节只许讲 row_scope，目录那节只许讲 restricted —— 讲串了格子就是又一处真相源。
    assert "restricted" not in subheads[PREVIEW_SUBHEAD], "row_scope 那一节开始替目录说话了"
    assert "row_scope" not in subheads[CATALOG_SUBHEAD], "restricted 那一节开始替预览说话了"


def test_preview_route_attaches_the_field_the_contract_names():
    tree = ast.parse(_text(DATA_PY))
    fn = _function(tree, "preview_data_file")
    attached = _subscript_targets(fn, "preview")
    assert list(attached) == ["row_scope"], f"预览路由挂的键换了：{sorted(attached)}"
    built = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
        and ast.unparse(node.value.func) == "_row_scope_status"
    ]
    assert len(built) == 1, "row_scope 的产出处不再是唯一那一枚调用点"
    assert ast.unparse(built[0].targets[0]) == "row_scope"
    assert ast.unparse(attached["row_scope"]) == "row_scope", (
        "挂上去的值不是刚算出来的那份状态层：中间被人换了一份就前功尽弃"
    )


# ==================== ⑤ restricted 的句子与「不点名文件」 ====================


def test_the_catalog_sentence_in_the_contract_is_the_route_own_bytes():
    tree = ast.parse(_text(DATA_PY))
    shape = _restricted_shape(tree)
    body = _subsections()[CATALOG_SUBHEAD]

    assert shape["guard"] == "restricted_count", (
        "restricted 的挂载条件换了：契约那句「absent entirely when nothing was refused」要重读"
    )
    documented = re.findall(r"`(有 \{count\} [^\n`]+)`", body)
    assert documented == [shape["template"]], (
        f"契约里那行模板与路由 f-string 的字节不再相同：{documented} != {[shape['template']]}"
    )
    for block in [item["restricted"] for item in _json_blocks(body) if "restricted" in item]:
        rendered = shape["template"].replace("{count}", str(block["count"]))
        assert block["message"] == rendered, (
            f"例子句不再是模板现算出来的结果（count={block['count']}）：改了句子没改例子"
        )


def test_restricted_carries_no_name_and_the_contract_says_why():
    tree = ast.parse(_text(DATA_PY))
    shape = _restricted_shape(tree)
    body = _subsections()[CATALOG_SUBHEAD]

    assert shape["keys"] == ["count", "reason_codes", "message"], (
        f"restricted 的键换了：{shape['keys']}。多出一枚装得下文件名的键就是替泄露开门"
    )
    for key in shape["keys"]:
        assert not re.search(r"file|name|dataset|id", key), f"键名 {key} 有可能带出被拒文件名"
    section = _section()
    assert "**Why nothing is named.**" in section, "「为什么不点名文件」那条理由被删了：那是这条边界的一半"
    assert "no filename" in section, "散文不再明说响应里不出现文件名"
