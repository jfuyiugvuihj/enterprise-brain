"""R200 · 「有，但你不能看」 那一枚投影只准有一份实现（全离线：进程内 TestClient，零服务、零模型、零库）。

改前本仓把这个形状手写了**两遍**：``app/api/v1/chat.py::_restricted_summary``（两枚平铺文档出口共用）
与 ``app/api/v1/data.py::list_data_files`` 路由体里内联的一枚 dict。自本单起只剩一处：
``app/api/v1/restricted.py::restricted_summary``，两句人话是它旁边那两枚模板常量，出口只递
「自己被拒清单 + 本腿那句模板」。总控授权前本件交回过一笔「① 不可达」的实证（并一次就把
``tests/test_r186_row_scope_contract.py`` 三枚与 ``tests/test_r201_flat_document_contract.py`` 四枚
打红），授权之后那七枚只换了读点、期望串一字未动，本件因此从「两处不许长歪」的棘轮升级为
「只准有一处」的棘轮 —— 交回里写的「这一行怎么收」就是下面 ① 那一行，已就地收完。

  ① 构造处在 app/** 里只准 **一枚**（AST 扫，不靠 grep 字符串碰运气），且每枚挂载点都必须把构造
     交给它：谁再内联拼一枚 dict、或再立一枚专职函数、或递上不登记在册的句子，当场红；
  ② 那一处产出的键集合与顺序必须等于契约正典那张表，也必须等于数据文件腿那张表（两处读点，一张表）；
  ③ ``reason_codes`` 必须由一次有序去重（``dict.fromkeys``）产出，构造它或挂它的函数里不许再长出
     第二套「手工 in / append」口径；句子里那个数必须与 ``count`` 字段是同一个表达式；
  ④ 每句「有 {count} …存在，但不在当前账号的可见范围内…」在 app/** 里只准出现一次，且必须与契约
     里逐字同一串（代码改了契约没改、契约改了代码没改，都红）；
  ⑤ 三条出口在同一次拒绝场景下的实测读数：documents 与 catalog 的 ``restricted`` 逐字节相同，
     data-files 那枚除句子外逐字段相同，三处都不点名，正向对照（看得见全部的人）三处都不挂键。

判据②要逐字节比读数的人：设 ``R200_DUMP=<路径>`` 再跑本件，⑤会把三条出口的原始响应字节 dump 成
一份 JSON —— 改前改后各跑一次即可 diff（基线值属于测量现场，不属于契约）。
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
CONTRACT = ROOT / "docs" / "api" / "contract-v1.md"

#: 投影的键清单与顺序都是契约（R186 / R201 各钉一头，本件钉的是「只准有一处产出它」）。
TALLY_KEYS = ["count", "reason_codes", "message"]
#: 两句人话共用的那副骨架：认句子只认骨架，整句由契约给。
FRAME = "存在，但不在当前账号的可见范围内"
DOCUMENT_SECTION = "## Document Catalog Visibility"
DATASET_SECTION = "## Dataset Row-Level Visibility"
CANON_SUBHEAD = "`restricted` -> the one shared projection"
CATALOG_SUBHEAD = "`GET /api/v1/data-files` -> `restricted`"

DEPT_OWN = "r200-finance"
DEPT_FOREIGN = "r200-hr"
DOC_NAMES = ["R200-foreign-a.txt", "R200-foreign-b.txt"]
CSV_NAMES = ["consolidated-a.csv", "consolidated-b.csv"]
DOC_BODY = "R200T-BODY 这一段正文只属于别人的文档"
CSV_TEXT = "部门,note\nr200-hr,R200-SECRET\n"

ACCOUNTS = {
    "keeper": {"id": "keeper", "username": "keeper", "role": "manager", "department": DEPT_OWN},
    "xdept": {"id": "xdept", "username": "xdept", "role": "manager", "department": DEPT_FOREIGN},
}


# ============================ 代码侧：AST 现抠，零手抄 ============================


def _sources() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _source(rel: str, mutated: dict[str, str] | None = None) -> str:
    return (mutated or {}).get(rel, _text(ROOT / rel))


def _scan(mutated: dict[str, str] | None = None) -> list[tuple[str, ast.Module]]:
    return [(_rel(path), ast.parse(_source(_rel(path), mutated))) for path in _sources()]


def _functions(tree: ast.Module) -> list[ast.AST]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _is_route(fn: ast.AST) -> bool:
    return any(
        isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in {"get", "post", "put", "delete"}
        for decorator in fn.decorator_list
    )


def _owner_of(fn_list: list[ast.AST], lineno: int):
    """The innermost function whose line span holds this node (a nest belongs to the inside)."""
    holders = [fn for fn in fn_list if fn.lineno <= lineno <= getattr(fn, "end_lineno", fn.lineno)]
    if not holders:
        return None
    return min(holders, key=lambda fn: getattr(fn, "end_lineno", fn.lineno) - fn.lineno)


def _literal_keys(node: ast.Dict) -> list[str]:
    return [
        str(key.value) for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]


def _as_template(node: ast.AST) -> str | None:
    """Rebuild a message literal into its contract template, or None when it is not that sentence.

    三种写法一视同仁，否则本件会替实现手法报假红：改前的 f-string（常量段 + 占位符复原）、
    合并后的模块级模板常量（句子就住在这儿，``{count}`` 已在串里）。
    """
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(str(part.value))
            elif isinstance(part, ast.FormattedValue):
                parts.append("{count}")
            else:
                return None
        text = "".join(parts)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    else:
        return None
    return text if FRAME in text else None


def _render_slot(node: ast.expr) -> str | None:
    """The expression a sentence's ``{count}`` slot is filled with, or None when it is not a render."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        slots = {str(keyword.arg): ast.unparse(keyword.value) for keyword in node.keywords}
        return slots.get("count") if set(slots) == {"count"} else None
    return None


def _builders(mutated: dict[str, str] | None = None) -> list[dict]:
    """Every dict literal in app/** that *is* the projection - with everything it must agree on."""
    found = []
    for rel, tree in _scan(mutated):
        fn_list = _functions(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict) or not set(TALLY_KEYS) <= set(_literal_keys(node)):
                continue
            keys = _literal_keys(node)
            fields = dict(zip(keys, node.values))
            owner = _owner_of(fn_list, node.lineno)
            found.append(
                {
                    "file": rel,
                    "line": node.lineno,
                    "keys": keys,
                    "count": ast.unparse(fields["count"]),
                    "dedup": ast.unparse(fields["reason_codes"]),
                    "message": fields["message"],
                    "slot": _render_slot(fields["message"]) or ast.unparse(fields["message"]),
                    "owner": getattr(owner, "name", "<module>"),
                    "route": bool(owner is not None and _is_route(owner)),
                    "fn": owner,
                }
            )
    return sorted(found, key=lambda item: (item["file"], item["line"]))


def _attach_sites(mutated: dict[str, str] | None = None) -> list[dict]:
    """Every ``x["restricted"] = ...`` in app/**: what it feeds the builder, and from where."""
    found = []
    for rel, tree in _scan(mutated):
        fn_list = _functions(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript)):
                continue
            subscript = node.targets[0]
            if not (isinstance(subscript.slice, ast.Constant) and subscript.slice.value == "restricted"):
                continue
            owner = _owner_of(fn_list, node.lineno)
            args = getattr(node.value, "args", [])
            found.append(
                {
                    "file": rel,
                    "line": node.lineno,
                    "expression": ast.unparse(node.value),
                    "callee": ast.unparse(node.value.func) if isinstance(node.value, ast.Call) else "<inline dict>",
                    "args": [ast.unparse(argument) for argument in args],
                    "owner": getattr(owner, "name", "<module>"),
                    "fn": owner,
                }
            )
    return sorted(found, key=lambda item: (item["file"], item["line"]))


def _sentence_literals(mutated: dict[str, str] | None = None) -> list[str]:
    """app/** 里所有长成那两句人话的字面（常量与 f-string 都算，出现两次就是抄了两遍）。"""
    words = []
    for _rel, tree in _scan(mutated):
        for node in ast.walk(tree):
            text = _as_template(node)
            if text:
                words.append(text)
    return words


def _template_names(mutated: dict[str, str] | None = None) -> set[str]:
    """登记在册的句子只能住在模块级常量里：本件拿这个名字集合认出口递的是哪一句。"""
    names = set()
    for _rel, tree in _scan(mutated):
        for node in tree.body:
            if (
                isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and _as_template(node.value)
            ):
                names.add(node.targets[0].id)
    return names


def _hand_dedup(sites) -> list[str]:
    """构造点与挂载点所在函数里的「手工 in / not in 去重」——第二套口径的形迹。"""
    hits = []
    for site in sites:
        fn = site["fn"]
        if fn is None:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare) or not any(
                isinstance(op, (ast.In, ast.NotIn)) for op in node.ops
            ):
                continue
            operands = [ast.unparse(node.left)] + [ast.unparse(item) for item in node.comparators]
            if any(re.search(r"reason|codes|withheld", text, re.IGNORECASE) for text in operands):
                hits.append("%s:%d %s" % (site["file"], node.lineno, " ".join(operands)))
    return hits


# ============================ 契约侧：正典现读，零手抄 ============================


def _contract() -> str:
    return _text(CONTRACT)


def _subsections(heading: str) -> dict[str, str]:
    body = _contract()
    start = re.search(r"(?m)^%s" % re.escape(heading), body)
    assert start, "契约里找不到 %r 这一节：改名可以，请连本钉一起改" % heading
    tail = body[start.end():]
    stop = re.search(r"(?m)^## ", tail)
    chunks = re.split(r"(?m)^### ", tail[: stop.start() if stop else len(tail)])
    out = {}
    for chunk in chunks[1:]:
        head, _, rest = chunk.partition("\n")
        out[head.strip()] = rest
    return out


def _documented_keys(heading: str, subhead: str) -> list[str]:
    return re.findall(r"^\|\s*`([a-z_]+)`\s*\|", _subsections(heading)[subhead], re.MULTILINE)


def _documented_templates() -> list[str]:
    return sorted(re.findall(r"`(有 \{count\} [^\n`]*)`", _contract()))


# ============================ ① 只准一处 ============================


def test_the_projection_is_built_in_exactly_one_place() -> None:
    builders = _builders()
    assert len(builders) == 1, (
        "restricted 的构造处只准一枚，实取 %d 枚：%s —— 一份判定一份投影，多一处就是给漂移开门"
        % (len(builders), [(item["file"], item["line"]) for item in builders])
    )
    builder = builders[0]
    assert not builder["route"], (
        "%s:%d 的构造住在路由体里：构造必须在专职函数里，出口只递料" % (builder["file"], builder["line"])
    )
    attaches = _attach_sites()
    assert len(attaches) == 3, "带 restricted 的出口实取 %d 枚：%s" % (
        len(attaches), [(item["file"], item["line"]) for item in attaches]
    )
    for site in attaches:
        assert site["callee"] == builder["owner"], (
            "%s:%d 不再把构造交给唯一那一处（%s）——就地手拼就是本件要治的病"
            % (site["file"], site["line"], site["expression"])
        )
        assert len(site["args"]) == 2, (
            "%s:%d 递给共用 builder 的参数不再是「被拒清单 + 本腿句子」：%s"
            % (site["file"], site["line"], site["args"])
        )
        assert site["args"][1] in _template_names(), (
            "%s:%d 递的句子不是登记在册的那两句之一：%s" % (site["file"], site["line"], site["args"])
        )


# ============================ ② 键名与键序 ============================


def test_the_one_builder_emits_the_keys_both_contract_tables_do() -> None:
    for item in _builders():
        assert item["keys"] == TALLY_KEYS, (
            "%s:%d 构造的 restricted 键清单是 %s，与契约那三枚不再是同一串（多一枚键就是多一条泄名的口子）"
            % (item["file"], item["line"], item["keys"])
        )
    assert _documented_keys(DOCUMENT_SECTION, CANON_SUBHEAD) == TALLY_KEYS, "契约正典那张表的键序自己先变了"
    assert _documented_keys(DATASET_SECTION, CATALOG_SUBHEAD) == TALLY_KEYS, "数据文件腿那张表与正典不再是同一串键"


# ============================ ③ 一次有序去重 + 同一个数 ============================


def test_the_reason_codes_come_from_one_ordered_pass_and_nothing_else() -> None:
    for item in _builders():
        assert "dict.fromkeys" in item["dedup"], (
            "%s:%d 的 reason_codes 换了收法（%s）：正典说的是「一次有序去重」，全仓只准这一种"
            % (item["file"], item["line"], item["dedup"])
        )
    hand = _hand_dedup(_builders() + _attach_sites())
    assert not hand, "构造点或挂载点所在函数里长出了第二套手工去重：%s" % hand


def test_the_number_in_the_sentence_is_the_number_in_the_count_field() -> None:
    for item in _builders():
        assert item["slot"] == item["count"], (
            "%s:%d 句子里填的数（%s）与 count 字段（%s）不再是同一个表达式"
            % (item["file"], item["line"], item["slot"], item["count"])
        )


# ============================ ④ 两句人话各一处 ============================


def test_each_sentence_exists_once_in_app_and_is_the_contracts_own_bytes() -> None:
    words = _sentence_literals()
    assert words, "app/** 里一句「有 N 份/个…存在」都没认出来：骨架常量要重读"
    duplicated = sorted({text for text in set(words) if words.count(text) > 1})
    assert not duplicated, "同一句人话在 app/** 里被抄了两遍：%s" % duplicated
    documented = _documented_templates()
    assert sorted(words) == documented, (
        "代码里的手与契约里的手不再是同一批：code=%s\ncontract=%s" % (sorted(words), documented)
    )


# ============================ ⑤ 三条出口同场景实测 ============================


def _principal(username: str, department: str):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": "manager", "department": department}
    )


@pytest.fixture()
def three_exits(monkeypatch, tmp_path):
    """一枚场景喂三条出口：两份登记在册的数据文件 + 两份在册文档，全部属于别的部门。"""
    from app.api.v1 import chat, data
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=tmp_path, metadata_path=tmp_path / "meta.json")
    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    for name in CSV_NAMES:
        path = tmp_path / name
        path.write_text(CSV_TEXT, encoding="utf-8")
        registry.register(path, principal=_principal("owner-finance", DEPT_OWN))

    shelf = []
    for name in DOC_NAMES:
        stored = tmp_path / "docs" / name
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_text(DOC_BODY, encoding="utf-8")
        shelf.append(
            {
                "filename": name,
                "storage_path": str(stored),
                "department": DEPT_OWN,
                "classification": 1,
                "owner_id": "u-r200-owner",
                "version": 1,
            }
        )
    monkeypatch.setattr(chat, "current_documents", lambda *a, **k: [dict(row) for row in shelf])
    monkeypatch.setattr(chat.retriever, "list_documents", lambda: list(DOC_NAMES))
    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))

    return TestClient(app), create_token


def _readings(client, create_token, username) -> dict:
    client.headers.update({"Authorization": "Bearer " + create_token(username)})
    return {
        "data_files": client.get("/api/v1/data-files"),
        "documents": client.get("/api/v1/documents"),
        "catalog": client.get("/api/v1/documents/catalog"),
    }


def test_the_three_exits_answer_one_refusal_with_one_projection(three_exits) -> None:
    client, token = three_exits
    readings = _readings(client, token, "xdept")

    tallies = {}
    for name, response in readings.items():
        assert response.status_code == 200, (name, response.text)
        body = response.json()
        assert "restricted" in body, "%s 把「有但你不能看」退回了空列表假话" % name
        tallies[name] = body["restricted"]
        blob = json.dumps(body, ensure_ascii=False, default=str)
        for secret in [DOC_BODY] + DOC_NAMES + CSV_NAMES:
            assert secret not in blob, "%s 开始点名被挡的资源：%s" % (name, secret)

    assert {tuple(item) for item in tallies.values()} == {tuple(TALLY_KEYS)}, (
        "三处出口的键清单或键序不再同一串：%s" % {name: list(item) for name, item in tallies.items()}
    )
    dumped = {name: json.dumps(item, ensure_ascii=False) for name, item in tallies.items()}
    assert dumped["documents"] == dumped["catalog"], (
        "文档那两张脸又长歪了：%s != %s" % (dumped["documents"], dumped["catalog"])
    )
    for key in ("count", "reason_codes"):
        assert tallies["data_files"][key] == tallies["documents"][key], (
            "%s 这一格两条腿不再是同一个口径：%s vs %s"
            % (key, tallies["data_files"][key], tallies["documents"][key])
        )
    assert tallies["data_files"]["count"] == len(CSV_NAMES)
    assert tallies["documents"]["count"] == len(DOC_NAMES)
    assert tallies["data_files"]["reason_codes"] == ["department_scope_denied"], (
        "两笔同因拒绝被数成两串码：一次有序去重漏了这一腿"
    )

    def rendered(count: int) -> set[str]:
        return {text.replace("{count}", str(count)) for text in _sentence_literals()}

    assert tallies["data_files"]["message"] in rendered(tallies["data_files"]["count"])
    assert tallies["documents"]["message"] in rendered(tallies["documents"]["count"])
    assert tallies["data_files"]["message"] != tallies["documents"]["message"], (
        "两句同人话 = 合并时把数据文件那一句换成了文档那一句，判据④当场破"
    )

    target = os.environ.get("R200_DUMP")
    if target:
        raw = {name: response.content.decode("utf-8") for name, response in readings.items()}
        Path(target).write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def test_a_viewer_who_sees_everything_gets_no_tally(three_exits) -> None:
    # 正向对照：绿不是场景本身刷出来的——看得见全部的人，三条出口都不许挂这一枚键。
    client, token = three_exits
    readings = _readings(client, token, "keeper")
    assert [name for name, response in readings.items() if "restricted" in response.json()] == []
    assert len(readings["data_files"].json()["files"]) == len(CSV_NAMES)
    assert len(readings["catalog"].json()["documents"]) == len(DOC_NAMES)


# ============================ 反证：本件的牙不是装饰品 ============================


RESTRICTED_REL = "app/api/v1/restricted.py"
DATA_REL = "app/api/v1/data.py"


def test_falsification_a_renamed_letter_in_a_template_turns_the_sentence_nail_red() -> None:
    """总控点名要试的那一枚：模板常量改一个字 → 红的必须是句子那枚钉（④）。"""
    source = _source(RESTRICTED_REL).replace("有 {count} 个数据文件存在", "有 {count} 个数据文件被藏起来", 1)
    assert source != _source(RESTRICTED_REL), "反证落不进 restricted.py"
    assert _sentence_literals({RESTRICTED_REL: source}) and sorted(_sentence_literals({RESTRICTED_REL: source})) != _documented_templates(), (
        "改了句子没被契约对出来：④是空响"
    )
    assert sorted(_sentence_literals()) == _documented_templates(), "盘上的句子自己先与契约脱钩了"


def test_falsification_an_inline_hand_build_turns_the_single_source_nail_red() -> None:
    """总控点名要试的那一枚：把一处 attach 退回就地手拼 → 红的必须是 ① 那枚 ``== 1`` 钉，不是别的格。

    反证只做「搬家」这一件事：内联那三枚键、``dict.fromkeys`` 的收法、句子里的数全部照抄唯一那一处，
    溢到 ②③④ 去就不叫 ① 的牙了（教训 #46）。
    """
    attach = '        result["restricted"] = restricted_summary(restricted_withheld, DATA_FILE_TEMPLATE)\n'
    inline = (
        '        result["restricted"] = {\n'
        '            "count": len(restricted_withheld),\n'
        '            "reason_codes": list(dict.fromkeys(code for _name, code in restricted_withheld)),\n'
        '            "message": DATA_FILE_TEMPLATE.format(count=len(restricted_withheld)),\n'
        "        }\n"
    )
    disk = _source(DATA_REL)
    assert disk.count(attach) == 1, "反证落不进 data.py：那枚 attach 现场变了，先重读"
    mutated = {DATA_REL: disk.replace(attach, inline, 1)}
    builders = _builders(mutated)
    assert len(builders) == 2, "第二枚构造处没有转红：①是空响"
    assert sorted(item["file"] for item in builders) == sorted([DATA_REL, RESTRICTED_REL]), (
        "多出来的那一枚不在被反证的出口上：%s" % [(item["file"], item["line"]) for item in builders]
    )
    assert all(item["keys"] == TALLY_KEYS for item in builders), "②跟着红了：反证溢到键名格"
    assert all("dict.fromkeys" in item["dedup"] for item in builders), "③的去重格跟着红了：反证溢格"
    assert all(item["slot"] == item["count"] for item in builders), "③的数格跟着红了：反证溢格"
    assert not _hand_dedup(builders + _attach_sites(mutated)), "③的手工去重格跟着红了：反证溢格"
    assert sorted(_sentence_literals(mutated)) == _documented_templates(), "④跟着红了：反证溢格"
    shared = _builders()[0]["owner"]
    attaches = _attach_sites(mutated)
    assert len(attaches) == 3, "挂载点计数被这一改动动了：反证溢格"
    assert sorted(item["callee"] for item in attaches) == sorted(["<inline dict>", shared, shared]), (
        "退回就地手拼的那枚 attach 不再指向共用 builder：①的挂载分支没牙（%s）"
        % [item["callee"] for item in attaches]
    )
    assert len(_builders()) == 1 and len(_attach_sites()) == 3, "盘上的 ① 自己先不成立，反证作废"


def test_falsification_a_second_dedup_rule_turns_the_dedup_nail_red() -> None:
    source = _source(RESTRICTED_REL).replace(
        "list(dict.fromkeys(code for _name, code in withheld))",
        "sorted(set(code for _name, code in withheld))",
        1,
    )
    assert source != _source(RESTRICTED_REL), "反证落不进 restricted.py"
    assert [item for item in _builders({RESTRICTED_REL: source}) if "dict.fromkeys" not in item["dedup"]], (
        "换掉去重口径没有转红：③是空响"
    )
    assert not [item for item in _builders() if "dict.fromkeys" not in item["dedup"]], "盘上的代码自己先不干净了"


def test_falsification_a_hand_dedup_at_an_exit_turns_the_second_rule_nail_red() -> None:
    source = _source(DATA_REL).replace(
        "                restricted_withheld.append((record.dataset_id, decision.reason_code))\n",
        "                if record.dataset_id not in [name for name, _code in restricted_withheld]:\n"
        "                    restricted_withheld.append((record.dataset_id, decision.reason_code))\n",
        1,
    )
    assert source != _source(DATA_REL), "反证落不进 data.py"
    assert _hand_dedup(_attach_sites({DATA_REL: source})), "出口自己先裁了一遍去重却没转红：③的另一半是空响"
    assert not _hand_dedup(_builders() + _attach_sites()), "盘上的代码自己先长了第二套口径"


def test_falsification_a_number_not_in_the_count_field_turns_the_number_nail_red() -> None:
    source = _source(RESTRICTED_REL).replace(
        '"message": template.format(count=len(withheld)),',
        '"message": template.format(count=len(withheld) + 0 if False else 1),',
        1,
    )
    assert source != _source(RESTRICTED_REL), "反证落不进 restricted.py"
    offenders = [item for item in _builders({RESTRICTED_REL: source}) if item["slot"] != item["count"]]
    assert offenders, "句子里的数换了来源却没转红：③的数那一半是空响"
    assert not [item for item in _builders() if item["slot"] != item["count"]], "盘上的数自己先脱钩了"