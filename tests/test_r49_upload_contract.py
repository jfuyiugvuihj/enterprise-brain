"""R49 判据①②③的契约层：上传当场给出原因，被排除的文档留在列表里且状态确定。

这里不测 UI（本单禁改 ``frontend/**``），只把"前端要消费什么"钉成可执行的契约：
状态字段名、原因稳定码字段名、以及"目录里绝不会少一行"这三件事。
"""
import asyncio
import io

import pytest
from fastapi import UploadFile

from pathlib import Path

from app.documents import index_policy
from app.documents.index_policy import (
    INDEX_STATUS_EXCLUDED,
    INDEX_STATUS_INDEXED,
    INDEX_STATUS_UNKNOWN,
    REASON_INDEX_REFUSED,
    REASON_NO_TEXT,
    REASON_OUTLINE_SHELL,
    REASON_PLACEHOLDER_SKELETON,
    REASON_UNCHANGED_CONTENT,
)

# 只有标题、没有正文的草稿骨架。
OUTLINE_SHELL = (
    "# 第一章 总则\n\n# 第二章 适用范围\n\n# 第三章 职责分工\n\n# 第四章 附则\n"
)

BLANK_FORM = (
    "报销申请单（模板）\n\n"
    "报销人：【请填写】\n部门：【请填写】\n报销日期：[日期]\n"
    "金额合计：__________\n附件张数：【待补充】\n审批意见：{{ 此处填写 }}\n"
    "收款账户：【请填写】\n开户银行：【请填写】\n联系人：【请填写】\n"
    "联系电话：__________\n通讯地址：【请填写】\n备注说明：【请填写】\n"
)

# 一份正常长度的制度正文：所有"应当入索引"的用例都用它。
GOOD_BODY = (
    "费用报销管理制度正文。员工发生的差旅费、业务招待费与办公费，须在费用发生后"
    "三十日内通过报销系统提交，逾期不予受理。提交时应附原始发票与审批单据，发票"
    "信息须与国家税务平台查验结果一致。单笔五千元以内的由部门负责人与财务经理审批，"
    "超过五千元的追加总经理审批。财务部每月汇总一次报销数据并出具分析报表。"
)

EMPTY_BODY = "   \n\n。——，！！\n"

#: 上传响应里前端必须能读到的字段。少一个都不行：被排除的上传与已入索引的上传必须
#: 用同一组字段回答，客户端不能靠"某个键不见了"去猜这次到底有没有入索引。
CONTRACT_KEYS = {
    "filename",
    "stored_name",
    "resource_id",
    "version",
    "size_bytes",
    "parse_status",
    "owner_id",
    "department",
    "chunk_count",
    "index_status",
    "index_reason",
    "index_message",
    "index_publication",
    "status",
    "message",
}


class RecordingRetriever:
    """只回答预置结果并记录被调用过没有。

    它故意没有 ``document_chunks``：索引回读于是返回空，``_publish_document_index``
    照旧给出 ``{"status": "skipped", "reason": "no_indexed_chunks"}`` —— 与既有的
    tests/test_document_upload_resilience.py 同一套桩，本单不碰向量库写入语义。
    """

    def __init__(self, result=(True, "已添加 2 个文本块")):
        self.result = result
        self.add_calls = []

    def add_document(self, filename, content, classification, department):
        self.add_calls.append(filename)
        return self.result

    def list_documents(self):
        return list(self.add_calls)


def _wire(monkeypatch, tmp_path, content, retriever, version=1):
    from app.api.v1 import chat
    from app.documents import catalog

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False, raising=False)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(chat, "retriever", retriever)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: version)
    monkeypatch.setattr(chat, "load_document", lambda path: content)
    return chat, catalog


def _upload(chat, filename="policy.txt", body=None):
    payload = body if body is not None else GOOD_BODY.encode("utf-8")
    # classification/department 必须显式给：直接按协程调用时它们的默认值是 FastAPI 的 Form
    # 对象本身，目录行会在 int() 上失败并退回"没有 index_status"的兜底字典。
    return asyncio.run(
        chat.upload_document(
            UploadFile(filename=filename, file=io.BytesIO(payload)),
            classification=1,
            department="",
        )
    )


def _class_row(catalog, filename="policy.txt"):
    for row in catalog.current_documents():
        if row["filename"] == filename:
            return row
    return None


def test_an_excluded_upload_answers_with_a_stable_reason_immediately(monkeypatch, tmp_path):
    retriever = RecordingRetriever()
    chat, _catalog = _wire(monkeypatch, tmp_path, OUTLINE_SHELL, retriever)

    response = _upload(chat)

    assert response["status"] == "skipped"
    assert response["index_status"] == INDEX_STATUS_EXCLUDED
    assert response["index_reason"] == REASON_OUTLINE_SHELL
    assert "草稿骨架" in response["index_message"]
    assert response["index_publication"] == {
        "status": "skipped",
        "reason": REASON_OUTLINE_SHELL,
        "index_id": "document:policy.txt",
        "source_version_id": "policy.txt|v1",
        "chunk_count": 0,
        "mirrored": False,
        "warnings": [],
    }
    assert response["chunk_count"] == 0
    assert response["index_metrics"]["headings"] == 4


def test_exclusion_costs_no_indexing_work_at_all(monkeypatch, tmp_path):
    """瘦身的本意：被排除的版本一次都不该去问 embedding、一个字都不该写进向量库。"""
    retriever = RecordingRetriever()
    chat, _catalog = _wire(monkeypatch, tmp_path, BLANK_FORM, retriever)

    response = _upload(chat)

    assert response["index_reason"] == REASON_PLACEHOLDER_SKELETON
    assert retriever.add_calls == []


def test_the_excluded_upload_is_still_written_to_disk_and_listed(monkeypatch, tmp_path):
    retriever = RecordingRetriever()
    chat, catalog = _wire(monkeypatch, tmp_path, OUTLINE_SHELL, retriever)

    response = _upload(chat)

    assert response["stored_name"]
    assert (tmp_path / response["stored_name"]).is_file()
    row = _class_row(catalog)
    assert row is not None, "被排除的文档绝不能从列表里消失"
    assert row["index_status"] == INDEX_STATUS_EXCLUDED
    assert row["index_reason"] == REASON_OUTLINE_SHELL
    assert row["parse_status"] == "ready"
    # size_bytes 记的是落盘文件本身的字节数；测试里 load_document 是被桩换掉的，
    # 所以正文长度与文件字节数本来就两回事。
    assert row["size_bytes"] == (tmp_path / response["stored_name"]).stat().st_size
    assert row["version"] == 1
    assert row["owner_id"] is None
    assert row["ownership"] == "legacy"


def test_an_empty_body_is_explained_instead_of_being_deleted(monkeypatch, tmp_path):
    """判据③：这条路径在 R49 之前是 os.remove(文件) + 一句 skipped，用户的东西就此消失。"""
    retriever = RecordingRetriever()
    chat, catalog = _wire(monkeypatch, tmp_path, EMPTY_BODY, retriever)

    response = _upload(chat)

    assert response["index_reason"] == REASON_NO_TEXT
    assert (tmp_path / response["stored_name"]).is_file()
    row = _class_row(catalog)
    assert row["index_status"] == INDEX_STATUS_EXCLUDED
    assert row["index_reason"] == REASON_NO_TEXT
    assert row["parse_status"] == "failed"
    assert retriever.add_calls == []


def test_the_index_state_survives_a_catalog_table_without_the_column(monkeypatch, tmp_path):
    """生产形态：目录行读自 PostgreSQL，而那张表还没有 index_status 列。

    sidecar 是这两列当前唯一不需要迁移就能落地的持久处，读路径必须把它补回来，否则
    判据②只在"库不可用"的分支上成立。
    """
    from app.documents import catalog

    retriever = RecordingRetriever()
    chat, offline_catalog = _wire(monkeypatch, tmp_path, OUTLINE_SHELL, retriever)
    response = _upload(chat)
    assert response["index_reason"] == REASON_OUTLINE_SHELL

    stored = tmp_path / response["stored_name"]

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            return _FakeResult(
                [
                    {
                        "filename": "policy.txt",
                        "version": 1,
                        "classification": 1,
                        "department": "",
                        "storage_path": str(stored),
                        "created_at": "2026-09-18T10:00:00+08:00",
                        "owner_id": None,
                        "size_bytes": stored.stat().st_size,
                        "parse_status": "ready",
                    }
                ]
            )

    monkeypatch.setattr(catalog, "_database_available", lambda: True, raising=False)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: _FakeConnection())

    rows = catalog.current_documents()

    assert len(rows) == 1
    assert rows[0]["index_status"] == INDEX_STATUS_EXCLUDED
    assert rows[0]["index_reason"] == REASON_OUTLINE_SHELL
    assert catalog.list_document_versions("policy.txt")[0]["index_status"] == INDEX_STATUS_EXCLUDED


def test_an_indexed_upload_reports_indexed_with_no_reason(monkeypatch, tmp_path):
    retriever = RecordingRetriever()
    chat, catalog = _wire(monkeypatch, tmp_path, GOOD_BODY, retriever)

    response = _upload(chat)

    assert response["status"] == "ok"
    assert response["index_status"] == INDEX_STATUS_INDEXED
    assert response["index_reason"] == ""
    assert response["parse_status"] == "ready"
    assert retriever.add_calls == ["policy.txt"]
    row = _class_row(catalog)
    assert row["index_status"] == INDEX_STATUS_INDEXED
    assert row["index_reason"] == ""


def test_a_duplicate_upload_says_unchanged_and_does_not_fork_a_phantom_row(monkeypatch, tmp_path):
    """同名同内容的重复上传：正文已经在索引里，状态是 indexed，但不是"又入了一份"。

    这是唯一允许不留物理副本的情形（droppable_upload），所以它也必须把稳定码回给调用方，
    并且不许凭空写一行指向已删文件的目录记录。
    """
    retriever = RecordingRetriever(result=(False, "文件内容未变化，已跳过"))
    chat, catalog = _wire(monkeypatch, tmp_path, GOOD_BODY, retriever)

    response = _upload(chat)

    assert response["status"] == "skipped"
    assert response["index_status"] == INDEX_STATUS_INDEXED
    assert response["index_publication"]["reason"] == REASON_UNCHANGED_CONTENT
    assert "未发生变化" in response["message"]
    assert catalog.current_documents() == []


def test_a_refusal_nobody_predicted_cannot_delete_an_upload(monkeypatch, tmp_path):
    """反证锚点：将来索引层新增任何一句拒绝理由，都走"留文件+留目录行+给稳定码"。"""
    retriever = RecordingRetriever(result=(False, "向量库这一版不收"))
    chat, catalog = _wire(monkeypatch, tmp_path, GOOD_BODY, retriever)

    response = _upload(chat)

    assert response["status"] == "skipped"
    assert response["index_status"] == INDEX_STATUS_EXCLUDED
    assert response["index_reason"] == REASON_INDEX_REFUSED
    assert response["stored_name"]
    assert (tmp_path / response["stored_name"]).is_file()
    row = _class_row(catalog)
    assert row["index_status"] == INDEX_STATUS_EXCLUDED
    assert row["index_reason"] == REASON_INDEX_REFUSED


def test_the_upload_response_always_carries_the_index_contract_fields(monkeypatch, tmp_path):
    outcomes = [
        (OUTLINE_SHELL, RecordingRetriever()),
        (BLANK_FORM, RecordingRetriever()),
        (EMPTY_BODY, RecordingRetriever()),
        (GOOD_BODY, RecordingRetriever()),
        (GOOD_BODY, RecordingRetriever(result=(False, "文件内容未变化，已跳过"))),
        (GOOD_BODY, RecordingRetriever(result=(False, "向量库这一版不收"))),
    ]

    for index, (content, retriever) in enumerate(outcomes):
        directory = tmp_path / f"case-{index}"
        directory.mkdir()
        chat, _catalog = _wire(monkeypatch, directory, content, retriever)

        response = _upload(chat)

        assert CONTRACT_KEYS <= set(response), set(response)
        assert response["index_status"] in index_policy.INDEX_STATUSES
        assert isinstance(response["index_message"], str)
        assert {"status", "reason", "index_id", "source_version_id", "chunk_count"} <= set(
            response["index_publication"]
        )


def test_a_row_that_never_recorded_a_decision_stays_silent(monkeypatch, tmp_path):
    """历史行的契约：不记着就什么都不透出，绝不被读成"未索引"。

    排除状态必须由字段自己说出来，"没这个字段"只能意味着"这一行在本单之前入库"，
    它不是"未索引"，也不是"已索引"。前端按这个三分支渲染，才不会出现一份老文档
    莫名变成灰色的情况。
    """
    from app.documents import catalog

    row = catalog.public_document_row({"filename": "old.txt", "version": 1, "storage_path": ""})

    assert "index_status" not in row
    assert "index_reason" not in row
    assert row["parse_status"] == "pending"
    assert row["ownership"] == "legacy"
    # 行内已有的键一个不少、一个不多：目录响应是既有契约，新增字段只随判定一起出现。
    assert set(row) == {"filename", "version", "storage_path", "owner_id", "size_bytes",
                        "parse_status", "ownership"}


def test_an_indexed_row_does_not_keep_an_old_reason(monkeypatch, tmp_path):
    from app.documents import catalog

    row = catalog.public_document_row(
        {
            "filename": "old.txt",
            "version": 2,
            "storage_path": "",
            "index_status": INDEX_STATUS_INDEXED,
            "index_reason": REASON_PLACEHOLDER_SKELETON,
        }
    )

    assert row["index_status"] == INDEX_STATUS_INDEXED
    assert row["index_reason"] == ""


def test_a_recorded_row_carries_the_status_and_only_an_excluded_one_carries_a_reason():
    from app.documents import catalog

    indexed = catalog._apply_index_policy(
        [{"filename": "a.txt", "version": 1, "storage_path": "", "index_status": INDEX_STATUS_INDEXED,
          "index_reason": REASON_PLACEHOLDER_SKELETON}]
    )[0]
    assert indexed["index_status"] == INDEX_STATUS_INDEXED
    assert indexed["index_reason"] == ""

    unknown = catalog._apply_index_policy(
        [{"filename": "b.txt", "version": 1, "storage_path": "", "index_status": None}]
    )[0]
    assert "index_status" not in unknown


def test_a_row_written_without_an_index_state_is_not_reported_as_indexed(monkeypatch, tmp_path):
    """三值里不许少一个：既不能把"没记着"读成"已索引"，也不能读成"未索引"。"""
    from app.documents import catalog

    assert INDEX_STATUS_UNKNOWN in index_policy.INDEX_STATUSES
    assert catalog._normalise_index_status(None) == INDEX_STATUS_UNKNOWN
    assert catalog._normalise_index_status("indexed") == INDEX_STATUS_INDEXED
    assert catalog._normalise_index_status("excluded") == INDEX_STATUS_EXCLUDED
    assert catalog._normalise_index_status("ExClUdEd") == INDEX_STATUS_EXCLUDED
    assert catalog._normalise_index_status("nonsense") == INDEX_STATUS_UNKNOWN


def test_the_parse_status_vocabulary_is_left_alone(monkeypatch, tmp_path):
    """本单不新增 parse_status 取值：那四个值之上压着数据库 CHECK 约束。

    点名 migrations/0006 的约束，是为了让"把 excluded 塞进 parse_status"这种省事写法
    在评审时就能被看见——它在开发库上能过，在跑过迁移的生产库上会让上传直接 500。
    """
    from app.documents import catalog

    assert catalog.PARSE_STATUSES == ("pending", "parsing", "ready", "failed")
    migration = (Path(__file__).resolve().parents[1] / "migrations" / "0006_document_ownership.sql").read_text(
        encoding="utf-8"
    )

    assert "document_versions_parse_status_check" in migration
    assert "excluded" not in migration
    assert catalog._normalise_parse_status("excluded") == "pending"
