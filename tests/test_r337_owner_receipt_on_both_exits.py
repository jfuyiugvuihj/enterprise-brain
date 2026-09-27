# -*- coding: utf-8 -*-
"""R337 · 预览与上传回执补上 owner：同一类出口不许一处有一处没有（R310 的尾巴）。

病灶（基点 957c7d2 现取，`app/api/v1/data.py`）：R310 给目录列表那一格补了 `owner_id`
（`data.py:268`），同类的另外两枚出口却没跟上 —— 上传回执（`:331-341`）带着 dataset_id /
version_id / classification 三格，独缺 owner，而 `register()` 返回的那枚 record 就在手上；
`GET /data-files/{filename}/preview`（`:381-391`）只带 dataset_id / version_id，owner 更缺。
这正是「同一类字段在一处补了、在另一处漏了」那一族病。

本件的尺子（判据逐枚对位）：
  · 判据① 同源：两处都必须走 `_dataset_row_owner_id`，不许直接摸 `.owner_id`，也不许为它现算
    一次查询 —— `owner_read_shape()` 是这件事唯一的尺子（纯函数，给源码文本就能跑），
    `test_the_three_exits_never_disagree_about_an_owner` 再拿真语料逐枚对答案；
  · 判据② 零额外查询 / 判据③ 逐档行数不变：`tests/test_r337_owner_receipt_cost_and_knives.py`；
  · 判据④ 预览那一格缺 `classification` 不许顺手补：
    `test_the_two_exits_answer_exactly_the_documented_registration_keys` 把它钉成「未决」而不是「遗漏」；
  · 判据⑤ 三张脸不许合并：`test_the_three_faces_stay_three_and_are_never_merged`；
  · 判据⑦ 错误码零新增：本件不造码，全局由 `test_r142_error_code_table_sync` 与
    `test_error_code_vocabulary` 两把扫描器看住。

另有一枚跨单闸门：`test_the_r310_counter_evidence_anchors_still_hit_data_py_exactly_once`。
R310 的四把反证靠「行锚点在 data.py 里恰好命中一处」定位变异，往同一枚文件加行最容易撞的就是它。
这一枚钉把那句话从「希望没撞」变成「撞了就当场红」。

全部离线：不起服务、不连库、不打模型；夹具坐在 `InMemoryDatasetTableStore` 上。
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"
R310_COST_PY = ROOT / "tests" / "test_r310_owner_lookup_cost.py"

DEPT_FINANCE = "r337-finance"
DEPT_HR = "r337-hr"
DEPT_OPS = "r337-ops"
DEPT_HQ = "r337-hq"

MINE = "r337-mine.csv"
THEIRS = "r337-theirs.csv"
LEGACY = "r337-legacy.csv"
UNREGISTERED = "r337-stray.csv"

OWNER_OF = {MINE: "alice", THEIRS: "carol", LEGACY: ""}
DEPT_OF = {MINE: DEPT_FINANCE, THEIRS: DEPT_HR, LEGACY: DEPT_FINANCE}
ROW_OF = {MINE: "row-mine", THEIRS: "row-theirs", LEGACY: "row-legacy"}

ACCOUNTS = {
    "alice": {"id": "alice", "username": "alice", "role": "manager", "department": DEPT_FINANCE},
    "bob": {"id": "bob", "username": "bob", "role": "manager", "department": DEPT_FINANCE},
    "carol": {"id": "carol", "username": "carol", "role": "manager", "department": DEPT_HR},
    "root": {"id": "root", "username": "root", "role": "admin", "department": DEPT_HQ},
    "dave": {"id": "dave", "username": "dave", "role": "staff", "department": DEPT_OPS},
}
#: 非空期望：这四档至少该看得见一枚文件；dave 与所有部门都不相干，专门钉「一行都不许多」。
VIEWERS = ("alice", "bob", "carol", "root")

FRESH = "r337-fresh.csv"
FRESH_BODY = "department,note\n%s,fresh-row\n" % DEPT_FINANCE

#: 两枚出口「应当长什么样」：手上那枚对象的名，与登记字段清单（顺序就是响应里的顺序）。
EXIT_SHAPE = {
    "upload_excel": {
        "source": "dataset",
        "keys": ["dataset_id", "version_id", "classification", "owner_id"],
    },
    "preview_data_file": {"source": "record", "keys": ["dataset_id", "version_id", "owner_id"]},
}


def _body_of(filename: str) -> str:
    return "department,note\n%s,%s\n" % (DEPT_OF[filename], ROW_OF[filename])


def _principal(username: str):
    from app.agents.contracts import Principal

    return Principal.from_user(ACCOUNTS[username])


def _request(username):
    """路由只经 principal_from_request 读 request.state.principal（与 R310 同一枚替身形状）。"""
    return SimpleNamespace(state=SimpleNamespace(principal=_principal(username)))


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": "Bearer %s" % create_token(username)}


def _wire(monkeypatch, tmp_path):
    """两枚入账行 + 一枚无主遗留行 + 一枚没入账的散档：与 R310 同一副语料形状。"""
    from app.api.v1 import data
    from app.common import auth
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

    root = tmp_path / "data"
    root.mkdir()
    registry = DatasetRegistry(
        root=root,
        metadata_path=root / ".dataset-metadata.json",
        store=InMemoryDatasetTableStore(),
    )
    # 无主那一格是生产今天真有的形状：遗留台账里缺失的 owner_id 被读成 ""。
    (root / LEGACY).write_text(_body_of(LEGACY), encoding="utf-8")
    (root / ".dataset-metadata.json").write_text(
        json.dumps({"datasets": [{
            "dataset_id": "r337-legacy",
            "filename": LEGACY,
            "owner_id": "",
            "department_ids": [DEPT_FINANCE],
            "classification": "internal",
            "visibility": "private",
            "storage_path": str(root / LEGACY),
            "status": "active",
            "created_at": "2026-09-20T00:00:00+00:00",
            "version_id": "r337-legacy:v1",
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )
    for filename in (MINE, THEIRS):
        path = root / filename
        path.write_text(_body_of(filename), encoding="utf-8")
        registry.register(path, principal=_principal(OWNER_OF[filename]))
    (root / UNREGISTERED).write_text(
        "department,note\n%s,stray-row\n" % DEPT_OPS, encoding="utf-8"
    )

    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))
    return data, registry, root


def owner_read_shape(source: str) -> dict:
    """纯函数：吃 data.py 的源码文本，吐两枚出口的 owner 取法取证。

    盘上的真身与影子副本里的变异体都能喂进来，所以判据①（只许一枚读法）与判据②（不许为这一格
    现算一次查询）在测试和反证里说的是同一句话，不存在第二把尺子。每枚路由交回四笔账：
    直接摸属性的位置、同源 helper 的调用形状（含参数原文）、owner 这一格填的值、登记字段清单。
    这一枚函数只负责取证，不负责判红（判红在 `owner_shape_violations`）：变异体常常正是
    「helper 一次都没被叫」那一形，取证处一抛就换不来一句人话。
    """
    tree = ast.parse(source)
    out: dict[str, dict] = {}
    for route, expect in EXIT_SHAPE.items():
        function = next(
            (node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == route),
            None,
        )
        assert function is not None, "data.py 里找不到 %s：这把尺子当场失效" % route
        direct = [
            ast.unparse(node) for node in ast.walk(function)
            if isinstance(node, ast.Attribute) and node.attr == "owner_id"
        ]
        helper_calls = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "_dataset_row_owner_id"
        ]
        call = helper_calls[0] if len(helper_calls) == 1 else None
        assignment = None
        if call is not None:
            assignment = next(
                (node for node in ast.walk(function)
                 if isinstance(node, ast.Assign) and node.value is call),
                None,
            )
        dicts = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Dict)
            and any(key is not None and getattr(key, "value", None) == "owner_id" for key in node.keys)
        ]
        one = [dicts[0]] if len(dicts) == 1 else []
        keys = [key.value for key in one[0].keys] if one else []
        owner_value = one[0].values[keys.index("owner_id")] if one and "owner_id" in keys else None
        out[route] = {
            "direct_attribute_reads": direct,
            "helper_call_count": len(helper_calls),
            "owner_key_count": len(dicts),
            "helper_call": ast.unparse(call) if call is not None else None,
            "helper_argument": ast.unparse(call.args[0]) if call is not None and call.args else None,
            "helper_keyword_args": (
                sorted(ast.unparse(k) for k in call.keywords) if call is not None and call.keywords else []
            ),
            "assigned_to": ast.unparse(assignment.targets[0]) if assignment is not None else None,
            "owner_key_value": ast.unparse(owner_value) if owner_value is not None else None,
            "registration_keys": keys,
        }
    return out


def owner_shape_violations(source: str) -> list[str]:
    """判据①②那句话逐条对判：交回违规清单，空表就是合规。

    盘上的交付体与影子根里的变异体走的是同一枚尺子，所以反证里那句「哪一枚红」不必靠手抄断言
    复述一遍 —— 它读的就是这五行判据。
    """
    violations: list[str] = []
    shape = owner_read_shape(source)
    for route, expect in EXIT_SHAPE.items():
        got = shape[route]
        if got["direct_attribute_reads"]:
            violations.append(
                "%s：又在就地读 .owner_id 了（%s）—— 无主 = None 那套口径只许活在 helper 一处"
                % (route, got["direct_attribute_reads"])
            )
        if got["helper_call_count"] != 1:
            violations.append(
                "%s：同源 helper 被叫了 %d 次（要求恰好 1 次）" % (route, got["helper_call_count"])
            )
        elif got["helper_argument"] != expect["source"]:
            violations.append(
                "%s：owner 的来源不是手上那枚 %s，实取 %s —— 换成一次现查就破判据②"
                % (route, expect["source"], got["helper_argument"])
            )
        elif got["helper_keyword_args"]:
            violations.append("%s：helper 长出了关键字参数 %s" % (route, got["helper_keyword_args"]))
        if got["owner_key_count"] != 1:
            violations.append(
                "%s：owner_id 这一格组装了 %d 次（要求恰好 1 次）" % (route, got["owner_key_count"])
            )
        elif got["owner_key_value"] != got["assigned_to"]:
            violations.append(
                "%s：owner_id 这一格填的不是刚读出来的那枚值（填 %r，读给 %r）"
                % (route, got["owner_key_value"], got["assigned_to"])
            )
        if got["registration_keys"] != expect["keys"]:
            violations.append(
                "%s 的登记字段换了：%s（预期 %s）" % (route, got["registration_keys"], expect["keys"])
            )
    return violations


def _document_rule(value):
    """无主口径的唯一出处在文档层：谓词现取，本文件零手抄（与 R310 同一把尺子）。"""
    from app.documents.catalog import _is_unowned

    return None if _is_unowned(value) else str(value)


class _Upload:
    """够用的 UploadFile 替身：路由只读 .filename 与 await .read()。"""

    def __init__(self, name, payload):
        self.filename = name
        self._payload = payload

    async def read(self):
        return self._payload


def _upload(data, username, filename, content: bytes) -> dict:
    return asyncio.run(
        data.upload_excel(request=_request(username) if username else None, file=_Upload(filename, content))
    )


def _preview(data, username, filename) -> dict:
    from fastapi import Response

    request = None if username is None else _request(username)
    return asyncio.run(data.preview_data_file(filename, request=request, response=Response()))


def _catalogue(data, username):
    request = None if username is None else _request(username)
    return asyncio.run(data.list_data_files(request=request))["files"]


def _visible_files(registry, username):
    """既有的那把权限尺子自己再量一遍：这一档账号开得了哪几枚文件。"""
    from app.common.permissions import ACTION_VIEW
    from app.common.policy import authorization_decision

    principal = _principal(username)
    return sorted(
        record.filename
        for record in registry.active_records()
        if authorization_decision(
            principal, record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
        ).allowed
    )


# ================================================= 判据①：两处新出口都带 owner，且只有一枚读法


def test_the_upload_receipt_names_the_uploader_on_the_real_route(monkeypatch, tmp_path):
    """上传回执以前只报 dataset_id / version_id / classification：谁传的没说（判据①）。"""
    from fastapi.testclient import TestClient

    from app.main import app

    data, registry, _root = _wire(monkeypatch, tmp_path)

    response = TestClient(app).post(
        "/api/v1/upload-excel",
        headers=_headers("bob"),
        files={"file": (FRESH, FRESH_BODY.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    record = registry.get_active_by_filename(FRESH)
    assert record is not None, "上传没入账，后面的对账都是空响"
    assert "owner_id" in body, "反证：回执又回到「三枚登记字段有、主人没有」那一格"
    assert body["owner_id"] == "bob", body["owner_id"]
    assert body["owner_id"] == _document_rule(record.owner_id), (
        "回执上的主人和台账上的主人不是一句话：界面 %r，台账 %r" % (body["owner_id"], record.owner_id)
    )
    # 本单只加一格：那三枚登记字段与数据本体原样在位（判据③的正面半边）。
    assert body["dataset_id"] == record.dataset_id
    assert body["version_id"] == record.version_id
    assert body["classification"] == record.classification
    assert [row["note"] for row in body["rows"]] == ["fresh-row"], body["rows"]


def test_the_preview_receipt_names_the_owner_the_registry_holds(monkeypatch, tmp_path):
    data, registry, _root = _wire(monkeypatch, tmp_path)

    checked = 0
    for username in VIEWERS:
        for filename in _visible_files(registry, username):
            body = _preview(data, username, filename)
            record = registry.get_active_by_filename(filename)
            assert "owner_id" in body, "%s 在 %s 眼里开了预览，回执却没有主人" % (filename, username)
            assert body["owner_id"] == _document_rule(record.owner_id), (
                "%s 的预览主人答错了：界面 %r，台账 %r" % (filename, body["owner_id"], record.owner_id)
            )
            checked += 1
    assert checked >= 4, "夹具空转：只对了 %d 格，上面的断言几乎恒真" % checked

    assert _preview(data, "alice", MINE)["owner_id"] == "alice"
    assert _preview(data, "carol", THEIRS)["owner_id"] == "carol", "自己的表也要如实说主人"
    assert _preview(data, "root", THEIRS)["owner_id"] == "carol", (
        "管理员看得见不等于主人变成他：不许改写成当前账号"
    )
    assert _preview(data, "alice", LEGACY)["owner_id"] is None


def test_the_three_exits_never_disagree_about_an_owner(monkeypatch, tmp_path):
    """目录列表、预览、上传回执三枚同类出口：同一枚行只许有一个答案。"""
    data, registry, _root = _wire(monkeypatch, tmp_path)

    for username in VIEWERS:
        rows = {row["filename"]: row for row in _catalogue(data, username)}
        assert rows or username == "dave", "夹具空转：%s 连一行目录都没读到" % username
        for filename, row in rows.items():
            assert "owner_id" in row, filename
            preview = _preview(data, username, filename)
            assert preview["owner_id"] == row["owner_id"], (
                "同一枚表在目录里说主人 %r，在预览里说 %r —— 两枚出口长歪了"
                % (row["owner_id"], preview["owner_id"])
            )

    receipt = _upload(data, "bob", FRESH, FRESH_BODY.encode("utf-8"))
    rows = {row["filename"]: row for row in _catalogue(data, "bob")}
    assert FRESH in rows, sorted(rows)
    assert receipt["owner_id"] == rows[FRESH]["owner_id"], "上传回执与目录列表对同一枚行报了两个主人"
    assert _preview(data, "bob", FRESH)["owner_id"] == receipt["owner_id"]


def test_each_new_exit_reads_the_owner_only_through_the_shared_helper():
    """判据①的形状半边：不许出现第二套 owner 读法（直接摸属性、现算一次查询都不行）。"""
    violations = owner_shape_violations(DATA_PY.read_text(encoding="utf-8"))

    assert violations == [], "交付体不合规：" + "；".join(violations)


# ============================================== 判据④：预览那一格只补 owner，不顺手补密级


def test_the_two_exits_answer_exactly_the_documented_registration_keys():
    """两枚出口各长哪几枚登记字段，逐字钉死（同一枚尺子的另一格判据）。

    预览那一格**没有** `classification` 是本单登记给总控/业主的未决问题，不是遗漏（判据④）：
    它牵到「登记类字段在预览面上要不要摊开」的口径。要补它，请先改这一枚钉并带上裁据。
    """
    shape = owner_read_shape(DATA_PY.read_text(encoding="utf-8"))
    got = shape["preview_data_file"]["registration_keys"]

    assert got == EXIT_SHAPE["preview_data_file"]["keys"], "预览出口的登记字段换了：%s" % got
    assert "classification" not in got, (
        "预览面上的 classification 仍未获裁定：补它要先有总控/业主的口径，再改本钉"
    )


# ================================================== 判据②的正面半边：无主答 None，不许第二套写法


def test_an_unowned_row_answers_none_on_the_wire_not_a_blank(monkeypatch, tmp_path):
    """遗留台账那枚 `owner_id=""` 的行：预览与目录都得答 null，不许答空串或「未分配」。"""
    from fastapi.testclient import TestClient

    from app.main import app

    _data, _registry, _root = _wire(monkeypatch, tmp_path)
    client = TestClient(app)

    preview = client.get("/api/v1/data-files/%s/preview" % LEGACY, headers=_headers("alice"))
    assert preview.status_code == 200, preview.text
    assert preview.json()["owner_id"] is None, repr(preview.json().get("owner_id"))
    assert '"owner_id": ""' not in preview.text, preview.text
    assert "未分配" not in preview.text, "不许自创第二套表示法"

    catalogue = client.get("/api/v1/data-files", headers=_headers("alice"))
    assert catalogue.status_code == 200, catalogue.text
    rows = {row["filename"]: row for row in catalogue.json()["files"]}
    assert rows[LEGACY]["owner_id"] is None
    assert '"owner_id": ""' not in catalogue.text, catalogue.text
    assert rows[MINE]["owner_id"] == "alice"


def test_a_row_object_without_an_owner_column_answers_none_not_a_500(monkeypatch, tmp_path):
    """手搓的行对象没有 owner 这一列（注册表产不出这种形状）：答 None，不许滑成 500。

    这正是 `tests/test_response_hygiene.py:297` 与 `tests/test_r180_row_scope_preview_and_catalog_honesty.py:322`
    递给预览路由的那一枚替身：若 helper 就地摸属性，预览会在 AttributeError 上被 `except Exception`
    包成 `dataset_preview_failed` —— 把一格缺失的归属字段报成服务器故障，而且是本单引入的回归。
    """
    from app.api.v1 import data

    stored = tmp_path / "handbuilt.csv"
    stored.write_text("department,note\n%s,built-row\n" % DEPT_FINANCE, encoding="utf-8")
    record = SimpleNamespace(
        dataset_id="ds-handbuilt",
        version_id="dv-handbuilt",
        filename=stored.name,
        storage_path=str(stored),
        classification="internal",
    )
    assert not hasattr(record, "owner_id"), "夹具变了：这枚替身已经带 owner 列，本钉成了空响"
    monkeypatch.setattr(data, "_authorized_dataset", lambda request, filename, action: record)

    body = _preview(data, "alice", stored.name)

    assert "owner_id" in body
    assert body["owner_id"] is None, repr(body["owner_id"])
    assert body["rows"], "夹具空转：正文一行都没有，None 就成了恒真"


# ================================================== 判据⑤：三张脸分得开，而且不许两两合并


def test_the_three_faces_stay_three_and_are_never_merged(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import app

    data, _registry, _root = _wire(monkeypatch, tmp_path)
    client = TestClient(app)

    # 脸一：有这一行、确实无主 —— 键在，值是 null。
    unowned = client.get("/api/v1/data-files/%s/preview" % LEGACY, headers=_headers("alice")).json()
    face_unowned = ("present", unowned["owner_id"]) if "owner_id" in unowned else ("absent", "<none>")

    # 脸二：调用方无权看到这一行 —— 预览整块回 403，回执里连 owner 这个字都不该出现；
    # 目录那一侧则把它藏进 restricted，不点名、也不带主人。
    refused = client.get("/api/v1/data-files/%s/preview" % THEIRS, headers=_headers("alice"))
    assert refused.status_code == 403, refused.text
    assert "owner_id" not in refused.text, refused.text
    alice_rows = client.get("/api/v1/data-files", headers=_headers("alice")).json()
    assert THEIRS not in {row["filename"] for row in alice_rows["files"]}, sorted(alice_rows["files"])
    assert alice_rows["restricted"]["count"] == 1, alice_rows
    face_refused = ("absent", refused.json()["detail"])

    # 脸三：注册表查无此行 —— 预览 404；无 request 的目录里那一格仍然带键并答 null。
    unregistered = client.get("/api/v1/data-files/%s/preview" % UNREGISTERED, headers=_headers("root"))
    assert unregistered.status_code == 404, unregistered.text
    assert unregistered.json()["detail"] == "resource_not_found"
    stray = {row["filename"]: row for row in _catalogue(data, None)}
    assert UNREGISTERED in stray, sorted(stray)
    assert "owner_id" in stray[UNREGISTERED] and stray[UNREGISTERED]["owner_id"] is None
    face_unregistered = ("present", stray[UNREGISTERED]["owner_id"])

    assert face_unowned == ("present", None), face_unowned
    assert face_refused == ("absent", "department_scope_denied"), face_refused
    # 「确实无主」与「注册表查无此行」在 owner 这一格里今天同答 null（R310 已定的口径），
    # 两者靠 dataset_id 那一格分得开；但它们与「无权看到这一行」绝不相同：那一格是整块缺席。
    assert face_refused != face_unowned and face_refused != face_unregistered


# ================================================ 跨单闸门：别把 R310 的反证锚点撞成两处


def _line_list_constants(path: Path) -> dict[str, list[str]]:
    """读出一枚文件里「模块级的字符串行列表」常量：锚点内容从 R310 现取，本文件零手抄。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if len(names) != 1:
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            out[names[0]] = value
    assert out, "%s 里读不出任何行列表常量：这枚钉就成了空响" % path.name
    return out


def test_the_r310_counter_evidence_anchors_still_hit_data_py_exactly_once():
    """R310 的四把反证按「锚点恰好命中一处」定位变异；本单往同一枚文件加行，撞了就当场红。

    命中两处不是把 R310 的判据放宽，而是让它的反证窗根本不落地（`assert hits == 1` 当场抛），
    于是「字段被摘掉也没人发现」那一族病重新变成无人看管。变异文本（`*_AS_BLANK` / `*_OFF` /
    `CLASSIFICATION_CARRYING_OWNER`）在盘上的 data.py 里必须是 0 处，所以这里只要求「不超过一处」，
    外加把四枚真锚点钉成恰好一处。
    """
    text = DATA_PY.read_text(encoding="utf-8")
    newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
    constants = _line_list_constants(R310_COST_PY)
    counts = {name: text.count(newline.join(lines)) for name, lines in constants.items()}

    doubled = {name: hits for name, hits in counts.items() if hits > 1}
    assert not doubled, (
        "R310 的行锚点在 data.py 里命中了不止一处：%s —— 它的反证窗会拒绝落变异。"
        "改法：把本单新增那一行的缩进或表达式错开，别造出第二枚同形行" % doubled
    )
    for name in ("OWNER_LINE", "UNOWNED_BRANCH", "FILTER_GUARD", "CLASSIFICATION_LINE"):
        assert counts.get(name) == 1, (
            "R310 的锚点 %s 在 data.py 里命中 %r 处（要求恰好 1 处）：那一把刀今天起砍不动了"
            % (name, counts.get(name))
        )
