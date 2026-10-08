"""R700 判据②（＋判据④②）· 文件名／权限／冲突三件事并进 documents 那本字典，且响应形状一步不许动。

本件管三格：
① 三件边界今天由 app/documents/file_security.py 一处作答——文件名（sanitize_upload_filename）、
   后缀与表头签名（inspect_dataset_upload）、同名冲突（guard_dataset_name_conflict）。同一份文件
   在两条上传路上必须答同一个码，这就是「does not read this dict」那一句的治法。
② upload_excel 的响应形状与状态码不许破：DataPanel.vue 现在就在调这一枚，键集必须还是
   数据画像那五枚 + 台账那四枚，知识库那本回执一个字都不许漏进 HTTP  body。
③ 入库闸门（模型在服务上吗）三格答复各自可失败：服务不答＝ollama_unreachable、
   答了但没有向量腿要调的那枚模型＝model_missing、认不出服务形状＝照走（unknown 永远不等于 skip）。

「摘掉边界检查即红」在本件里是可执行的一句，不是一句声明：每一枚拒绝都配一枚反证——把那一格
的在册检查换成空操作，同一份请求立刻走通。拒绝若是从别处（比如 pandas）顺带掉出来的，反证就红。

全程离线：不连 PostgreSQL、不起服务、不开宿主模型端口、不打模型。写库那一腿用一枚记账替身，
本件要判的是「有没有被叫到」，真命中由 tests/test_r700_dataset_table_reaches_the_index.py 量。
"""
from __future__ import annotations

import asyncio
import io
import os
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.documents import file_security
from app.documents.index_policy import INDEX_STATUS_EXCLUDED, INDEX_STATUS_INDEXED
from app.documents.knowledge_ingest import index_dataset_copy, registry_url_for
from app.rag.retriever import REASON_MODEL_MISSING, REASON_UNREACHABLE

DEPT = "r700-finance"
OWNER = "r700-manager"
CSV_NAME = "台账.csv"
XLSX_NAME = "台账.xlsx"
FORGED_XLSX = b"this is not a zip container at all"
LEGACY_XLS_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512

#: 数据集那一半的在册响应键集：画像五枚 + 台账四枚，一枚不多一枚不少。
PREVIEW_KEYS = {
    "filename",
    "columns",
    "rows",
    "profile",
    "truncated",
    "dataset_id",
    "version_id",
    "classification",
    "owner_id",
}


def _csv_bytes() -> bytes:
    return "部门,预算额度\n研发,3100\n市场,2200\n行政,1800\n".encode("utf-8")


def _xlsx_bytes() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["部门", "预算额度"])
    sheet.append(["研发", 3100])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class _FakeLeg:
    """知识库那条腿的记账替身：add_document 被叫过几次、拿的什么参数，一眼可读。"""

    def __init__(self, *, api_url: str = "http://127.0.0.1:9999/api/embeddings") -> None:
        self.embedding = SimpleNamespace(api_url=api_url, last_error=None)
        self.add_document_calls: list[tuple] = []

    def add_document(self, filename, content, classification=1, department=None):
        self.add_document_calls.append((filename, content, classification, department))
        return True, "已添加 1 个文本块"


class _Brain:
    """DATA_DIR／登记表／账号表／知识库腿四枚注入，形状与在册件 test_r336 的 _wire 一致。"""

    def __init__(self, monkeypatch, tmp_path, *, department: str = DEPT, permissions=None) -> None:
        from app.agents import tools as agent_tools
        from app.api.v1 import chat, data
        from app.common import auth, model_config
        from app.storage import datasets
        from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir()
        from app.documents import catalog
        docs_dir = tmp_path / "documents"
        docs_dir.mkdir()
        monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(docs_dir))
        self.leg = _FakeLeg()
        self.bm25_calls: list[int] = []
        registry = DatasetRegistry(
            root=self.data_dir,
            metadata_path=self.data_dir / ".dataset-metadata.json",
            store=InMemoryDatasetTableStore(),
        )
        account = {
            "id": OWNER,
            "username": OWNER,
            "role": "manager",
            "department": department,
        }
        if permissions is not None:
            account["permissions"] = list(permissions)
        self.account = account
        monkeypatch.setattr(data, "DATA_DIR", str(self.data_dir))
        monkeypatch.setattr(data, "dataset_registry", registry)
        monkeypatch.setattr(datasets, "dataset_registry", registry)
        monkeypatch.setattr(chat, "retriever", self.leg)
        monkeypatch.setattr(auth, "get_user", lambda username: dict(self.account))
        # 闸门这一格按生产分支武装起来：服务答得出、且答的正是那枚 embedding 模型。
        # 于是「一枚块都没写」只能归因于边界检查本身，而不是归因于闸门自己关了。
        monkeypatch.setattr(
            model_config,
            "_fetch_registry",
            lambda url, *args, **kwargs: {"models": [{"name": "nomic-embed-text"}]},
        )
        monkeypatch.setattr(agent_tools, "rebuild_bm25", lambda: self.bm25_calls.append(1))
        self.registry = registry

    def upload(self, name: str, payload: bytes, *, username: str = OWNER):
        from app.common.auth import create_token
        from app.main import app

        return TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/upload-excel",
            headers={"Authorization": "Bearer {0}".format(create_token(username))},
            files={"file": (name, payload, "application/octet-stream")},
        )


@pytest.fixture
def brain(monkeypatch, tmp_path):
    return _Brain(monkeypatch, tmp_path)


# ==================== ① 三件边界出自同一本字典 ====================


def test_the_shared_dict_answers_the_extension_for_both_routes() -> None:
    """后缀这一格：数据集腿问的就是知识库腿那本 _ALLOWED_TYPES，不是第二份名单。"""
    for name in (CSV_NAME, XLSX_NAME):
        inspection = file_security.inspect_dataset_upload(
            name, _csv_bytes() if name.endswith(".csv") else _xlsx_bytes()
        )
        assert inspection.extension == name[name.rindex("."):]
        assert inspection.display_filename == name

    with pytest.raises(file_security.UploadSecurityError) as refused:
        file_security.inspect_dataset_upload("报告.doc", LEGACY_XLS_BYTES)
    assert "unsupported upload extension" in str(refused.value), "后缀判定改口了"
    assert ".doc" not in _ALLOWED_TYPE_NAMES(), "字典里冒出了 .doc：本件的尺子就悬空了"


def test_the_shared_dict_answers_the_header_signature() -> None:
    """表头那一格：伪造的 .xlsx 在写第一个字节之前就被同一本字典拒。"""
    with pytest.raises(file_security.UploadSecurityError) as refused:
        file_security.inspect_dataset_upload(XLSX_NAME, FORGED_XLSX)
    assert "file header does not match extension" in str(refused.value)

    # csv 没有签名可验，走的是 .txt/.md 那一档：空签名元组 ⇒ 跳过验表头。
    assert file_security.inspect_dataset_upload(CSV_NAME, _csv_bytes()).extension == ".csv"


def test_the_conflict_rule_lives_in_the_shared_dict() -> None:
    """同名那一格：规则本身住在 documents 层，且它自己不发明错误码。"""
    assert file_security.guard_dataset_name_conflict(CSV_NAME, None) is None
    with pytest.raises(file_security.DatasetFilenameConflictError) as refused:
        file_security.guard_dataset_name_conflict(CSV_NAME, object())
    assert refused.value.filename == CSV_NAME
    assert not hasattr(refused.value, "code"), (
        "本单不治码表：数据集冲突不许长出一枚新的 code 属性（R306 的零新增错误码口径）"
    )


def test_the_dataset_route_refuses_disguise_and_paths_with_the_documented_code(brain) -> None:
    """文件名这一格并进字典之后：路径分隔、伪装双重后缀、开头点号一律 400 invalid_filename。"""
    for name in ("sub/台账.csv", "policy.pdf.xlsx", ".hidden.csv"):
        response = brain.upload(name, _csv_bytes())
        assert response.status_code == 400, (name, response.text)
        assert response.json()["detail"] == "invalid_filename", name
        assert not (brain.data_dir / name.replace("sub/", "")).exists(), name
    assert brain.leg.add_document_calls == [], "被拒的请求已经把知识库那条腿叫醒了"


def test_refutation_dropping_the_filename_guard_lets_a_nested_name_land(monkeypatch, tmp_path) -> None:
    """反证：摘掉文件名那一格（路由侧与字典内部两处同一枚函数），带路径分隔的名字就落得进来。

    上一枚测试里那三声 400 invalid_filename 因此只能来自这一格。注意伪装双重后缀那一名
    字摘掉路由这一格之后仍然被拒：拒它的是同一本字典里的 sanitize_upload_filename——
    inspect_upload_header 自己也要过一遍，这正是判据②要的「一处作答」，不是第二套规则。
    """
    from app.api.v1 import data

    brain = _Brain(monkeypatch, tmp_path)
    strip = lambda value: (value or "").split("/")[-1]
    monkeypatch.setattr(data, "sanitize_upload_filename", strip)
    monkeypatch.setattr(file_security, "sanitize_upload_filename", strip)

    response = brain.upload("sub/台账.csv", _csv_bytes())

    assert response.status_code == 200, (response.status_code, response.text)
    assert (brain.data_dir / "台账.csv").is_file()
    assert len(brain.leg.add_document_calls) == 1


def test_a_knowledge_base_type_the_data_leg_cannot_open_is_still_refused(brain) -> None:
    """两本闸门口径不同这一步不许被并进字典：.txt 在字典里，但数据读腿开不了它。"""
    response = brain.upload("制度.txt", "制度正文\n".encode("utf-8"))

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, dict) and sorted(detail) == ["code", "message"]
    assert detail["code"] == "unsupported_file"
    assert ".txt" in _ALLOWED_TYPE_NAMES(), "字典里少了 .txt：本件的尺子就悬空了"
    assert brain.leg.add_document_calls == []


# ==================== ② 响应形状与状态码一步不许动 ====================


def test_a_clean_upload_answers_the_documented_shape_and_indexes_the_table(brain) -> None:
    """绿路径同一条腿走通：响应键集一字不动，知识库的回执只进日志、不进 body。"""
    response = brain.upload(CSV_NAME, _csv_bytes())

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == PREVIEW_KEYS, sorted(body)
    for leaked in ("status", "reason", "message", "index"):
        assert leaked not in body, "知识库那本回执漏进了数据集的响应里"
    assert body["filename"] == CSV_NAME
    assert body["classification"]
    assert body["owner_id"] == OWNER

    assert len(brain.leg.add_document_calls) == 1, "闸门武装着却没写库：并进知识库这一步没落地"
    stored = brain.leg.add_document_calls[0]
    assert stored[0] == CSV_NAME
    assert isinstance(stored[2], int) and stored[2] >= 1, "写库的密级必须是既有的档位整数"
    assert stored[3] == DEPT, "写库的部门口径必须是上传者的部门"
    assert brain.bm25_calls == [1]


def test_the_conflicting_name_conflicts_and_indexes_nothing(brain) -> None:
    """同名第二次：409 与在册状态码一字不动，且知识库那条腿一枚块都不许多写。"""
    assert brain.upload(CSV_NAME, _csv_bytes()).status_code == 200

    response = brain.upload(CSV_NAME, _csv_bytes())

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "dataset_filename_conflict"
    assert len(brain.leg.add_document_calls) == 1, "冲突那一格没能拦在入库之前"


def test_refutation_no_op_conflict_guard_lets_the_duplicate_in(monkeypatch, tmp_path) -> None:
    """反证：摘掉冲突那一格，同名第二次就不再是 409——上面那枚 409 因此只能来自这一格。"""
    from app.api.v1 import data

    brain = _Brain(monkeypatch, tmp_path)
    monkeypatch.setattr(data, "guard_dataset_name_conflict", lambda *args, **kwargs: None)
    assert brain.upload(CSV_NAME, _csv_bytes()).status_code == 200

    response = brain.upload(CSV_NAME, _csv_bytes())

    assert response.status_code != 409, response.text


def test_a_caller_without_the_upload_grant_is_refused_and_nothing_is_indexed(monkeypatch, tmp_path) -> None:
    """越权那一格：只有 resource:view 的账号拿到 403，磁盘与知识库两条腿都没被动过。"""
    brain = _Brain(monkeypatch, tmp_path, permissions=["resource:view"])

    response = brain.upload(CSV_NAME, _csv_bytes())

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    assert list(brain.data_dir.iterdir()) == []
    assert brain.leg.add_document_calls == []


def test_refutation_the_same_account_with_the_grant_uploads(monkeypatch, tmp_path) -> None:
    """反证：同一枚账号补上 resource:upload 就走通——上一枚 403 来自权限那一格而非别处。"""
    brain = _Brain(monkeypatch, tmp_path, permissions=["resource:view", "resource:upload"])

    assert brain.upload(CSV_NAME, _csv_bytes()).status_code == 200
    assert len(brain.leg.add_document_calls) == 1


def test_a_departmentless_owner_is_refused_before_the_knowledge_leg_runs(
    monkeypatch, tmp_path
) -> None:
    """无部门账号：在册的 403 department_scope_required 不许变成 500，也不许留货。"""
    brain = _Brain(monkeypatch, tmp_path, department="")

    response = brain.upload(CSV_NAME, _csv_bytes())

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "department_scope_required"
    assert not (brain.data_dir / CSV_NAME).exists()
    assert brain.leg.add_document_calls == []


# ==================== ③ 闸门：三格答复各自可失败 ====================


def _run(**kwargs):
    return asyncio.run(index_dataset_copy(**kwargs))


def test_the_gate_skips_when_the_server_reports_no_embedding_model(tmp_path) -> None:
    leg = _FakeLeg()
    path = tmp_path / CSV_NAME
    path.write_bytes(_csv_bytes())

    receipt = _run(
        display_filename=CSV_NAME,
        storage_path=path,
        department=DEPT,
        classification="internal",
        retriever=leg,
        registry_fetch=lambda url: {"models": [{"name": "llama3:latest"}]},
    )

    assert receipt["status"] == "unavailable"
    assert receipt["reason"] == REASON_MODEL_MISSING
    assert leg.add_document_calls == [], "模型不在服务上却仍然去烧了 embedding"


def test_the_gate_skips_when_the_model_server_does_not_answer(tmp_path) -> None:
    leg = _FakeLeg()
    path = tmp_path / CSV_NAME
    path.write_bytes(_csv_bytes())

    def refusing(url):
        raise ConnectionRefusedError("nothing is listening")

    receipt = _run(
        display_filename=CSV_NAME,
        storage_path=path,
        department=DEPT,
        classification="internal",
        retriever=leg,
        registry_fetch=refusing,
    )

    assert receipt["status"] == "unavailable"
    assert receipt["reason"] == REASON_UNREACHABLE
    assert leg.add_document_calls == []


def test_the_gate_proceeds_when_the_server_has_the_model(tmp_path) -> None:
    leg = _FakeLeg()
    path = tmp_path / CSV_NAME
    path.write_bytes(_csv_bytes())

    receipt = _run(
        display_filename=CSV_NAME,
        storage_path=path,
        department=DEPT,
        classification="internal",
        retriever=leg,
        registry_fetch=lambda url: {"models": [{"name": "nomic-embed-text:latest"}]},
    )

    assert receipt["status"] == INDEX_STATUS_INDEXED
    assert len(leg.add_document_calls) == 1


def test_an_unrecognisable_server_shape_never_means_skip(tmp_path) -> None:
    """认不出服务形状的 handle 照走：unknown 永远不等于 skip（与 monitoring 同一条口径）。"""
    leg = _FakeLeg(api_url="")
    assert registry_url_for(leg) == ""
    path = tmp_path / CSV_NAME
    path.write_bytes(_csv_bytes())

    receipt = _run(
        display_filename=CSV_NAME,
        storage_path=path,
        department=DEPT,
        classification="internal",
        retriever=leg,
    )

    assert receipt["status"] == INDEX_STATUS_INDEXED, receipt


def test_a_body_below_the_policy_floor_is_excluded_not_indexed(tmp_path) -> None:
    """R49 那枚「值不值得入」的判定也在这条腿上：被排除的正文一枚块都不许多写。"""
    leg = _FakeLeg()
    path = tmp_path / "空表.csv"
    path.write_text("a,b\n", encoding="utf-8")
    # 用运维那枚在册旋钮把下限抬到这份正文之上，而不是去把夹具削成一枚不真实的文件。
    os.environ["DOCUMENT_INDEX_MIN_CHARS"] = "50"
    try:
        receipt = _run(
            display_filename=path.name,
            storage_path=path,
            department=DEPT,
            classification="internal",
            retriever=leg,
            registry_fetch=lambda url: {"models": [{"name": "nomic-embed-text"}]},
        )
    finally:
        del os.environ["DOCUMENT_INDEX_MIN_CHARS"]

    assert receipt["status"] == INDEX_STATUS_EXCLUDED, receipt
    assert receipt["reason"] == "below_minimum_size", receipt
    assert leg.add_document_calls == []


def _ALLOWED_TYPE_NAMES() -> set[str]:
    return set(file_security._ALLOWED_TYPES)
