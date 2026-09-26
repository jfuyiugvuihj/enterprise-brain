# -*- coding: utf-8 -*-
"""R310 · 数据文件列表必须说得出「这表是谁传的」（V2 明列：资源有稳定 ID、owner 与生命周期）。

病灶（基点 9344028 现取）：`app/api/v1/data.py::list_data_files` 组装文件行只给 filename /
size / size_label / modified_at / extension 五格，`record is not None` 时再补 dataset_id /
version_id / classification —— 手上那枚 `DatasetRecord.owner_id`
（`app/storage/datasets.py:121`）一个字都没往界面上给，员工在数据面板里永远看不出这表是谁传的。
同一类产品在文档侧早有口径：`app/documents/catalog.py:236`
`public["owner_id"] = None if _is_unowned(...) else str(...)`。本单把数据行接到同一口径上。

钉与判据：
  · 判据 1 —— `test_every_row_carries_the_owner_the_registry_already_holds`（每一行都带，
    值就是手上那枚 record）＋ `test_an_unregistered_row_still_answers_an_owner_key`
    （`record is None` 那一格也必须带，语义是 `None`，不许悄悄漏成一格都不存在）；
  · 判据 2 —— `test_unowned_rows_answer_none_not_an_empty_string` ＋
    `test_the_unowned_rule_is_the_document_rule_on_the_same_corpus`：拿
    `app.documents.catalog._is_unowned` 这枚真函数在语料上逐枚对答案，两边不许长歪；
  · 判据 3 —— `test_owner_travels_only_for_rows_the_policy_already_showed`：每档账号可见的文件名
    与 `authorization_decision` 现算的集合逐枚相等，owner 只给本来就看得见的行。
    「改前改后每档 `len(files)` 逐枚相等」与「零次额外查询、零条额外权限链」在
    `tests/test_r310_owner_lookup_cost.py`，四把反证也在那一枚件的末尾；
  · 判据 4 —— `test_the_owner_is_a_login_name_and_nothing_else_travels`；
  · 判据 3 的副作用闸门 —— `test_data_py_import_face_stays_the_baseline_set`：补一枚字段不许
    长出新的 import 面，也不许把文档层的私有谓词直接 import 进来。

全部离线：进程内直接 await 路由协程，不起服务、不连库、不碰模型；夹具坐在
`InMemoryDatasetTableStore` 上，一条真库连接都不发。
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DATA_PY = ROOT / "app" / "api" / "v1" / "data.py"

DEPT_FINANCE = "r310-finance"
DEPT_HR = "r310-hr"
DEPT_OPS = "r310-ops"

LEGACY = "legacy.csv"
UNREGISTERED = "unregistered.csv"
REGISTERED = ("mine.csv", "team.csv", "hr.csv")
OWNER_OF = {"mine.csv": "alice", "team.csv": "bob", "hr.csv": "carol", LEGACY: ""}
DEPT_OF = {"mine.csv": DEPT_FINANCE, "team.csv": DEPT_FINANCE, "hr.csv": DEPT_HR}
BODY_OF = {
    "mine.csv": "MINE-BODY",
    "team.csv": "TEAM-BODY",
    "hr.csv": "HR-BODY",
    LEGACY: "LEGACY-BODY",
    UNREGISTERED: "STRAY-BODY",
}

ACCOUNTS = {
    "alice": {"id": "alice", "username": "alice", "role": "manager", "department": DEPT_FINANCE},
    "bob": {"id": "bob", "username": "bob", "role": "manager", "department": DEPT_FINANCE},
    "carol": {"id": "carol", "username": "carol", "role": "manager", "department": DEPT_HR},
    "root": {"id": "root", "username": "root", "role": "admin", "department": "r310-hq"},
    "dave": {"id": "dave", "username": "dave", "role": "staff", "department": DEPT_OPS},
}
#: 非空期望：这四档至少该看见一行；dave 与所有部门都不相干，专门钉「一行都不许多」。
VIEWERS = ("alice", "bob", "carol", "root")

#: 行的键清单，取 wire 上的出现顺序。owner_id 与 filename 同族：入账与没入账两形态都得带着它。
BASE_KEYS = ["filename", "owner_id", "size", "size_label", "modified_at", "extension"]
REGISTERED_KEYS = BASE_KEYS + ["dataset_id", "version_id", "classification"]

#: 基点 9344028 现取的 import 面（含函数体内那枚懒加载的 app.agents.tools）。本单只补字段，
#: 一枚都不许多 —— 判据 3 的「不许新增 import 面」由下面那枚棘轮钉住。
IMPORT_FACE = frozenset({
    "asyncio", "datetime", "fastapi", "fastapi.responses", "mimetypes", "os", "pandas",
    "pathlib", "pydantic",
    "app.agents.tools", "app.api.v1.restricted", "app.common.audit", "app.common.authorization",
    "app.common.logger", "app.common.no_store", "app.common.permissions", "app.common.policy",
    "app.common.rbac", "app.storage", "app.storage.datasets",
    "app.tools.chart", "app.tools.excel", "app.tools.export", "app.tools.visualize",
})


def _principal(username):
    from app.agents.contracts import Principal

    return Principal.from_user(ACCOUNTS[username])


def _request(username):
    """一枚够用的 request 替身：路由只经 principal_from_request 读 request.state.principal。"""
    return SimpleNamespace(state=SimpleNamespace(principal=_principal(username)))


def _wire(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

    root = tmp_path / "data"
    root.mkdir()
    registry = DatasetRegistry(
        root=root,
        metadata_path=root / ".dataset-metadata.json",
        store=InMemoryDatasetTableStore(),
    )
    # 无主那一档不是用例编出来的形状：遗留台账里缺失的 owner_id 由 _legacy_rows 落成 ""，
    # _dataset_from_row 再把它读成 ""。生产里今天就是这么一枚行，本件走真导入通路。
    (root / LEGACY).write_text(
        "department,note\n%s,LEGACY-BODY\n" % DEPT_FINANCE, encoding="utf-8"
    )
    (root / ".dataset-metadata.json").write_text(
        json.dumps({"datasets": [{
            "dataset_id": "r310-legacy",
            "filename": LEGACY,
            "owner_id": "",
            "department_ids": [DEPT_FINANCE],
            "classification": "internal",
            "visibility": "private",
            "storage_path": str(root / LEGACY),
            "status": "active",
            "created_at": "2026-09-20T00:00:00+00:00",
            "version_id": "r310-legacy:v1",
        }]}, ensure_ascii=False),
        encoding="utf-8",
    )
    for filename in REGISTERED:
        path = root / filename
        path.write_text(
            "department,note\n%s,%s\n" % (DEPT_OF[filename], BODY_OF[filename]), encoding="utf-8"
        )
        registry.register(path, principal=_principal(OWNER_OF[filename]))
    (root / UNREGISTERED).write_text(
        "department,note\n%s,STRAY-BODY\n" % DEPT_OPS, encoding="utf-8"
    )
    (root / "notes.txt").write_text("not a dataset", encoding="utf-8")

    monkeypatch.setattr(data, "DATA_DIR", str(root))
    monkeypatch.setattr(data, "dataset_registry", registry)
    return data, registry, root


def _payload(data, username=None):
    if username is None:
        return asyncio.run(data.list_data_files())
    return asyncio.run(data.list_data_files(request=_request(username)))


def _rows_by_name(payload):
    return {row["filename"]: row for row in payload["files"]}


def _visible_and_refused(registry, username):
    """既有的那把权限尺子自己再量一遍：本单的 owner 不许挪动它量出的行数。"""
    from app.common.permissions import ACTION_VIEW
    from app.common.policy import authorization_decision

    principal = _principal(username)
    visible, refused = [], []
    for record in registry.active_records():
        decision = authorization_decision(
            principal, record.resource_scope, action=ACTION_VIEW, require_resource_scope=True
        )
        (visible if decision.allowed else refused).append(record.filename)
    return sorted(visible), sorted(refused)


def _document_rule(value):
    """`app/documents/catalog.py:236` 那一行的口径，谓词从文档层现取，本文件零手抄。"""
    from app.documents.catalog import _is_unowned

    return None if _is_unowned(value) else str(value)


# ===================================================================== 判据 1：每一行都带 owner


def test_every_row_carries_the_owner_the_registry_already_holds(monkeypatch, tmp_path):
    data, registry, _root = _wire(monkeypatch, tmp_path)

    for username in VIEWERS:
        payload = _payload(data, username)
        assert payload["files"], "夹具空转：账号 %s 一行都没读到，下面的断言就成了恒真" % username
        for row in payload["files"]:
            assert "owner_id" in row, (
                "反证 (a)：%s 在账号 %s 眼里根本没有 owner_id 这一格 —— 赋值被摘掉了" % (
                    row["filename"], username
                )
            )
            record = registry.get_active_by_filename(row["filename"])
            assert record is not None, row["filename"]
            assert row["owner_id"] == _document_rule(record.owner_id), (
                "%s 的 owner 不是手上那枚 record.owner_id：界面上 %r，台账里 %r" % (
                    row["filename"], row["owner_id"], record.owner_id
                )
            )

    alice = _rows_by_name(_payload(data, "alice"))
    assert alice["mine.csv"]["owner_id"] == "alice"
    assert alice["team.csv"]["owner_id"] == "bob", "别人的行如实说别人传的，不许改写成当前账号"


def test_an_unregistered_row_still_answers_an_owner_key(monkeypatch, tmp_path):
    # record is None 那一格（磁盘有文件但没入账）只在 request is None 时出得来：带 request 时
    # 它连目录都进不来，那是改前就有的行为，本单一个字没动。这一枚件把那一格钉死成 None。
    data, _registry, _root = _wire(monkeypatch, tmp_path)
    rows = _rows_by_name(_payload(data))

    assert UNREGISTERED in rows, sorted(rows)
    stray = rows[UNREGISTERED]
    assert "owner_id" in stray, (
        "反证 (d)：没入账的行整格 owner_id 都不存在 —— 「没有人」和「这一类产品不谈主人」是两句话"
    )
    assert stray["owner_id"] is None, repr(stray["owner_id"])
    assert list(stray.keys()) == BASE_KEYS, list(stray.keys())
    assert rows["mine.csv"]["owner_id"] == "alice"
    assert list(rows["mine.csv"].keys()) == REGISTERED_KEYS, list(rows["mine.csv"].keys())


def test_the_row_key_set_is_the_documented_one(monkeypatch, tmp_path):
    data, _registry, _root = _wire(monkeypatch, tmp_path)

    for username in VIEWERS:
        for row in _payload(data, username)["files"]:
            assert list(row.keys()) == REGISTERED_KEYS, (username, list(row.keys()))
            assert "_modified_timestamp" not in row


# ================================================================== 判据 2：无主口径逐字同文档侧


def test_unowned_rows_answer_none_not_an_empty_string(monkeypatch, tmp_path):
    data, _registry, _root = _wire(monkeypatch, tmp_path)

    for username in ("alice", "root"):
        payload = _payload(data, username)
        rows = _rows_by_name(payload)
        assert LEGACY in rows, sorted(rows)
        assert rows[LEGACY]["owner_id"] is None, (
            "反证 (b)：无主的数据行答了 %r —— 文档侧那一格答的是 None" % (rows[LEGACY]["owner_id"],)
        )
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        assert '"owner_id": ""' not in blob, blob
        assert "未分配" not in blob, "不许自创第二套表示法"


def test_the_unowned_rule_is_the_document_rule_on_the_same_corpus():
    from app.api.v1.data import _dataset_row_owner_id

    corpus = [None, "", "   ", "\t", "alice", "  bob  ", "u-17", "未分配"]
    for value in corpus:
        got = _dataset_row_owner_id(SimpleNamespace(owner_id=value))
        expected = _document_rule(value)
        assert got == expected, (
            "无主口径与文档侧长歪了：owner_id=%r 数据侧答 %r，文档侧答 %r" % (value, got, expected)
        )
        assert (got is None) == (expected is None), "%r：一边 None 一边空串就是两套口径" % (value,)
    assert _dataset_row_owner_id(None) is None, "record is None 必须答 None"


# ===================================================================== 判据 3：可见集合一字不动


def test_owner_travels_only_for_rows_the_policy_already_showed(monkeypatch, tmp_path):
    data, registry, _root = _wire(monkeypatch, tmp_path)

    for username in ACCOUNTS:
        payload = _payload(data, username)
        visible, refused = _visible_and_refused(registry, username)
        got = sorted(row["filename"] for row in payload["files"])
        assert got == visible, (
            "反证 (c)：账号 %s 的行集与既有权限尺子量出的不是一回事：界面上 %s，尺子上 %s" % (
                username, got, visible
            )
        )
        assert len(payload["files"]) == len(visible)
        if refused:
            assert payload["restricted"]["count"] == len(refused), (username, payload.get("restricted"))
        else:
            assert "restricted" not in payload, (username, payload)

    assert _payload(data, "dave")["files"] == [], "与所有部门都不相干的账号不该多看见一行"


# ============================================================================ 判据 4：只带登录名


def test_the_owner_is_a_login_name_and_nothing_else_travels(monkeypatch, tmp_path):
    data, _registry, root = _wire(monkeypatch, tmp_path)
    payload = _payload(data, "carol")
    blob = json.dumps(payload, ensure_ascii=False, default=str)

    assert _rows_by_name(payload)["hr.csv"]["owner_id"] == "carol"
    for name in ("alice", "bob", "dave"):
        assert name not in blob, "反证 (c)：越权的行替她带了主人，%s 泄漏进她的响应" % name
    for token in BODY_OF.values():
        assert token not in blob, "正文跟着目录出来了：%s" % token
    assert str(root) not in blob, "内部路径不许出现在目录里"
    for word in ("Bearer", "token", "password", "secret"):
        assert word.lower() not in blob.lower(), word


# ================================================================ 判据 3 的副作用闸门：import 面


def test_data_py_import_face_stays_the_baseline_set():
    tree = ast.parse(DATA_PY.read_text(encoding="utf-8"), filename=str(DATA_PY))
    face = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            face.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            face.add(("." * node.level) + (node.module or ""))

    assert face == IMPORT_FACE, (
        "补一枚 owner_id 不该长出新的 import 面：多了 %s，少了 %s" % (
            sorted(face - IMPORT_FACE), sorted(IMPORT_FACE - face)
        )
    )
    assert "app.documents.catalog" not in face, (
        "无主口径在本层复述并由同源钉看住，不许把文档层的私有谓词 import 进来"
    )


# ============================================================ 真路由表：字段确实上了 wire


def test_the_owner_field_arrives_on_the_http_wire(monkeypatch, tmp_path):
    """上面几枚走协程直调；这一枚走 FastAPI 的路由表与 JSON 序列化，证明界面上真收得到。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    data, _registry, _root = _wire(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: ACCOUNTS.get(username))

    client = TestClient(app)
    response = client.get(
        "/api/v1/data-files", headers={"Authorization": "Bearer " + create_token("alice")}
    )

    assert response.status_code == 200, response.text
    rows = _rows_by_name(response.json())
    assert rows["mine.csv"]["owner_id"] == "alice"
    assert rows["team.csv"]["owner_id"] == "bob"
    assert rows[LEGACY]["owner_id"] is None, "无主在 wire 上必须是 null，不是空串"
    assert '"owner_id": ""' not in response.text, response.text
    assert '"owner_id": "未分配"' not in response.text, response.text
    assert UNREGISTERED not in rows, "没入账的文件在 HTTP 上仍然进不来（改前就有的行为，本单没动）"
