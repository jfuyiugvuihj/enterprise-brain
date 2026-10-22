from pathlib import Path

import re

import pytest

from app.documents.file_security import (
    _ALLOWED_TYPES,
    UploadSecurityError,
    build_storage_path,
    inspect_upload_header,
    sanitize_upload_filename,
    stream_to_temporary_file,
)
from app.rag.loader import load_document


def test_sanitize_upload_filename_rejects_client_path_segments():
    with pytest.raises(UploadSecurityError, match="path separators"):
        sanitize_upload_filename("../../secrets.pdf")

    with pytest.raises(UploadSecurityError, match="path separators"):
        sanitize_upload_filename(r"..\secrets.pdf")


def test_inspect_upload_header_rejects_extension_and_magic_mismatch():
    with pytest.raises(UploadSecurityError, match="does not match"):
        inspect_upload_header("report.pdf", b"MZ" + b"\x00" * 32)


def test_inspect_upload_header_accepts_a_pdf_signature():
    result = inspect_upload_header("report.pdf", b"%PDF-1.7\n")

    assert result.extension == ".pdf"
    assert result.media_type == "application/pdf"


def test_build_storage_path_uses_resource_id_and_stays_under_root(tmp_path):
    stored = build_storage_path(tmp_path, "e89d2c08-6d74-4e7a-baa5-1f2a7c8b9d0e", ".pdf")

    assert stored.parent == tmp_path.resolve()
    assert stored.name == "e89d2c08-6d74-4e7a-baa5-1f2a7c8b9d0e.pdf"


def test_build_storage_path_rejects_an_invalid_resource_id(tmp_path):
    with pytest.raises(UploadSecurityError, match="resource id"):
        build_storage_path(tmp_path, "../outside", ".pdf")


def test_stream_to_temporary_file_writes_in_chunks_and_returns_a_private_path(tmp_path):
    source = iter([b"first-", b"second"])
    temp_path = stream_to_temporary_file(source, tmp_path, max_bytes=32)

    assert temp_path.parent == tmp_path.resolve()
    assert temp_path.suffix == ".tmp"
    assert temp_path.read_bytes() == b"first-second"


def test_stream_to_temporary_file_removes_partial_content_when_limit_is_exceeded(tmp_path):
    with pytest.raises(UploadSecurityError, match="size limit"):
        stream_to_temporary_file(iter([b"1234", b"5678"]), tmp_path, max_bytes=6)

    assert list(tmp_path.iterdir()) == []


def test_upload_security_error_keeps_the_stable_contract_code():
    assert UploadSecurityError.code == "unsupported_file"


def test_knowledge_base_whitelist_is_limited_to_parsable_document_types():
    # R306 接线：闭集从四格长到六格。这不是放宽——同一把尺（"是个闭集，且一格不多"）原样保留，
    # 只是解析层真长出了 `.xlsx`/`.csv` 这一格；"每一格都必须被分派认得"由
    # tests/test_r306_spreadsheets_in_the_upload_path.py::test_every_whitelisted_extension_is_actually_dispatched
    # 逐格验，摘掉 loader 分派那一格它当场红。
    assert set(_ALLOWED_TYPES) == {".pdf", ".txt", ".md", ".docx", ".xlsx", ".csv"}


def test_inspect_upload_header_rejects_double_extensions():
    with pytest.raises(UploadSecurityError, match="double extensions"):
        inspect_upload_header("policy.pdf.txt", b"%PDF-1.7\n")

    with pytest.raises(UploadSecurityError, match="double extensions"):
        inspect_upload_header("policy.md.exe", b"MZ\x90\x00")


def test_inspect_upload_header_rejects_a_forged_docx_body():
    with pytest.raises(UploadSecurityError, match="does not match"):
        inspect_upload_header("policy.docx", b"%PDF-1.7 not really a docx")


@pytest.mark.parametrize(
    "filename",
    # R306: `sheet.xlsx`/`table.csv` 今天已在名单内，换掉它们；补上来的三枚仍是名单外的真代表，
    # 其中 `legacy.xls` 正是契约里明确拒绝的那一枚。覆盖面 4 -> 5，一把没少。
    ["legacy.xls", "deck.pptx", "archive.zip", "legacy.doc", "payload.exe"],
)
def test_inspect_upload_header_rejects_extensions_outside_the_knowledge_base(filename):
    with pytest.raises(UploadSecurityError, match="unsupported upload extension") as exc_info:
        inspect_upload_header(filename, b"whatever")

    assert exc_info.value.code == "unsupported_file"


@pytest.mark.parametrize("extension", [".xlsx", ".csv", ".xls", ".exe"])
def test_build_storage_path_accepts_the_whitelist_and_refuses_everything_else(tmp_path, extension):
    """R306 接线：这两格从"被拒"翻成"必须落盘"，而拒绝那一半换绑到仍在名单外的两格上。

    原断言：`.xlsx`/`.csv` 一律 `unsupported upload extension`。
    现断言：白名单内的两格必须存成 `uuid + 单一后缀`（并且磁盘名只许一个点——那是双扩展守卫
    的前提，原件没有这条，现在是加严不是放松），名单外的 `.xls`/`.exe` 必须继续被拒。
    摘掉白名单里任意一格 ⇒ 第一句红；把白名单校验整个拆掉 ⇒ 第二句红。
    """
    from app.documents.file_security import _ALLOWED_TYPES as allowed

    if extension in allowed:
        stored = build_storage_path(tmp_path, "resource-0001", extension)

        assert stored.parent == tmp_path.resolve()
        assert stored.name == "resource-0001" + extension
        assert stored.name.count(".") == 1
    else:
        with pytest.raises(UploadSecurityError, match="unsupported upload extension"):
            build_storage_path(tmp_path, "resource-0001", extension)


def test_build_storage_path_normalizes_a_bare_whitelisted_extension(tmp_path):
    stored = build_storage_path(tmp_path, "resource-0001", "md")

    assert stored.parent == tmp_path.resolve()
    assert stored.name == "resource-0001.md"


@pytest.mark.parametrize("extension", sorted(_ALLOWED_TYPES))
def test_every_whitelisted_extension_is_routed_by_load_document(tmp_path, extension):
    """Guard the drift that made an accepted upload fail with an HTTP 500."""
    document = tmp_path / f"policy{extension}"
    document.write_bytes(b"# policy\n\nrevenue grew 12 percent.\n")

    try:
        load_document(str(document))
    except Exception as exc:  # a parser rejecting junk is fine; a dispatch gap is not
        assert "Unsupported file format" not in str(exc), (
            f"{extension} passes the upload whitelist but cannot be parsed"
        )


def test_load_document_reads_markdown_with_encoding_detection(tmp_path):
    document = tmp_path / "policy.md"
    document.write_bytes("# 季度经营分析\n\n营收环比增长 12%。\n".encode("utf-8"))

    assert load_document(str(document)) == "# 季度经营分析\n\n营收环比增长 12%。\n"


def test_load_document_reads_gbk_markdown(tmp_path):
    document = tmp_path / "legacy.md"
    document.write_bytes("# 旧文档\n".encode("gbk"))

    assert "旧文档" in load_document(str(document))


def test_load_document_hands_spreadsheets_to_the_parser(tmp_path):
    """R306 接线：分派不再对 `.xlsx` 说「不认得这格式」，坏内容改由解析层自己出声。

    原断言：`ValueError("Unsupported file format")`——钉的正是「分派那一格不存在」。
    现断言：同一枚假工作簿必须走到解析层（`zipfile.BadZipFile` 是 openpyxl 打不开那坨假 zip
    的真话），而一枚真工作簿必须读出正文。摘掉 loader 分派那一格 ⇒ 第一句拿到的是
    "Unsupported file format"，当场红；把 `.xlsx` 从 SPREADSHEET_SUFFIXES 摘掉 ⇒ 第二句红。
    """
    import zipfile

    import openpyxl

    workbook = tmp_path / "sales.xlsx"
    workbook.write_bytes(b"PK\x03\x04not-a-real-workbook")

    with pytest.raises(zipfile.BadZipFile):
        load_document(str(workbook))

    good = tmp_path / "good.xlsx"
    book = openpyxl.Workbook()
    book.active.title = "一月"
    book.active.append(["部门", "金额"])
    book.active.append(["销售", 10])
    book.save(str(good))

    body = load_document(str(good))
    assert "销售" in body and "Sheet「一月」" in body


def _document_upload_client(monkeypatch, tmp_path):
    """Serve the real document router on a probe app: no port, no app.main lifespan."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agents import tools
    from app.api.v1 import chat

    class FakeRetriever:
        def __init__(self):
            self.indexed = {}

        def add_document(self, filename, content, classification, department):
            self.indexed = {
                "filename": filename,
                "content": content,
                "classification": classification,
                "department": department,
            }
            return True, "indexed 2 chunks"

    retriever = FakeRetriever()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", retriever)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    probe = FastAPI()
    probe.include_router(chat.router, prefix="/api/v1")
    return TestClient(probe), retriever


def _upload_client_as(monkeypatch, tmp_path, username: str, department: str):
    """Serve the document router with one authenticated subject, no middleware."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common.identity import Principal

    client, retriever = _document_upload_client(monkeypatch, tmp_path)
    principal = Principal.from_user(
        {"id": username, "username": username, "role": "staff", "department": department}
    )

    probe = FastAPI()

    @probe.middleware("http")
    async def _authenticate(request, call_next):
        request.state.principal = principal
        return await call_next(request)

    probe.include_router(chat.router, prefix="/api/v1")
    return TestClient(probe), retriever


def test_upload_route_passes_the_stored_path_and_display_name_to_the_parser(tmp_path, monkeypatch):
    import asyncio
    import io

    from fastapi import HTTPException, UploadFile

    from app.api.v1 import chat

    calls = []

    def recording_parser(path, display_name=None):
        calls.append((path, display_name))
        raise ValueError("stop here: 本件钉的是解析层收到了什么，不是索引那一步")

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "load_document", recording_parser)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)

    workbook = io.BytesIO(b"PK\x03\x04fake workbook body")
    upload = UploadFile(filename="sales.xlsx", file=workbook)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    # 原断言：`.xlsx` 在写第一个字节之前就被拒（400 unsupported_file，磁盘零写入）。
    # 现断言：白名单放开之后解析层必须真被叫到一次，而且拿到的是「落盘的 uuid 名 + 展示名」
    # 两样——施工口四那一行的凭据。摘掉 chat.py 那一行的 `display_name=` ⇒ 第二句红。
    # 「被拒的上传不许碰解析层/索引」这一半没有丢：它换绑在
    # test_upload_route_still_refuses_a_name_the_whitelist_does_not_cover 与
    # test_http_upload_still_rejects_a_disguised_name_with_the_stable_code 上。
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "document_parse_failed"
    assert len(calls) == 1, f"解析层被叫了 {len(calls)} 次：{calls}"
    parsed_path, parsed_display = calls[0]
    assert parsed_display == "sales.xlsx"
    assert Path(parsed_path).parent == tmp_path.resolve()
    assert re.fullmatch(r"[0-9a-f]{32}\.xlsx", Path(parsed_path).name), parsed_path
    assert Path(parsed_path).is_file(), "落盘文件在解析时就该已经存在"
    assert list(tmp_path.glob(".upload-*.tmp")) == []


def test_upload_route_ingests_a_csv_through_the_real_parser(tmp_path, monkeypatch):
    """原断言：`.csv` 拿 400、零写入。现断言：200，且索引到的正文带锚。

    这里**不桩 load_document**：跑的是真分派 + 真解析层，所以摘掉 loader 那一格本件必红
    （解析 raise ⇒ 500）；锚点第一段必须是用户上传的那个名字而不是 uuid ⇒ 摘掉施工口四
    那一行的 `display_name=` 同样必红。
    """
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("expenses.csv", b"month,amount\n2026-01,120\n", "text/csv")},
        data={"classification": "2"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["filename"] == "expenses.csv"
    assert re.fullmatch(r"[0-9a-f]{32}\.csv", payload["stored_name"]), payload["stored_name"]
    assert retriever.indexed["content"].startswith("expenses.csv · 表1"), retriever.indexed["content"]
    assert "| 2026-01 | 120 |" in retriever.indexed["content"]
    assert (tmp_path / payload["stored_name"]).read_bytes() == b"month,amount\n2026-01,120\n"


def test_http_upload_ingests_a_markdown_document(tmp_path, monkeypatch):
    body = "# 库存周转\n\n周转天数 32 天。\n"
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("inventory.md", body.encode("utf-8"), "text/markdown")},
        data={"classification": "2", "department": "operations"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["filename"] == "inventory.md"
    assert payload["message"] == "indexed 2 chunks"
    assert retriever.indexed["content"] == body
    assert retriever.indexed["classification"] == 2
    assert (tmp_path / payload["stored_name"]).read_text(encoding="utf-8") == body


def test_upload_inherits_the_uploader_department_and_not_the_form_one(
    tmp_path, monkeypatch
):
    client, retriever = _upload_client_as(monkeypatch, tmp_path, "warehouse-clerk", "仓储部")

    response = client.post(
        "/api/v1/upload",
        files={"file": ("stock.txt", "库存周转 32 天。".encode("utf-8"), "text/plain")},
        data={"classification": "1", "department": "财务部"},
    )

    assert response.status_code == 200, response.text
    assert retriever.indexed["department"] == "仓储部"
    assert response.json()["department"] == "仓储部"


def test_an_upload_with_no_subject_stays_unscoped(tmp_path, monkeypatch):
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("orphan.txt", "无主文档".encode("utf-8"), "text/plain")},
        data={"classification": "1", "department": "随便填"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["department"] == ""
    assert retriever.indexed["department"] is None


def test_http_upload_ingests_a_fake_workbook_and_keeps_the_file(tmp_path, monkeypatch):
    """R306 接线：假工作簿从 400 unsupported_file 翻成 500 document_parse_failed。

    原断言：`.xlsx` 在写第一个字节之前就被拒——400 + `list(tmp_path.iterdir()) == []`。
    现断言：名字拿到了那一格，内容读不动就必须诚实报 500，而且
      * 错误码是既有的那一枚（本单零新增错误码，判据⑦）；
      * 落盘文件保留、索引一字不写（不把读不懂的内容变成可检索的假象）；
      * 临时文件不许残留。
    拿到的两样东西（uuid 落盘名 / 展示名）由
    test_upload_route_passes_the_stored_path_and_display_name_to_the_parser 钉；
    「名字不在白名单里的上传必须碰不到磁盘」这一半换绑到
    test_upload_route_still_refuses_a_name_the_whitelist_does_not_cover，一字未减。
    """
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={
            "file": (
                "sales.xlsx",
                b"PK\x03\x04fake workbook body",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "document_parse_failed"}
    assert retriever.indexed == {}
    assert len(list(tmp_path.glob("*.xlsx"))) == 1, list(tmp_path.iterdir())
    assert list(tmp_path.glob(".upload-*.tmp")) == []


@pytest.mark.parametrize("filename", ["legacy.xls", "notes.pptx"])
def test_upload_route_still_refuses_a_name_the_whitelist_does_not_cover(
    tmp_path, monkeypatch, filename
):
    """本文件原来靠电子表格顺手钉的那颗「零写入」牙，现在换绑到这里。

    名字不在白名单 => 写第一个字节之前就得结束：400 unsupported_file、目录空、索引空。
    `.xls` 是契约里写死拒绝的那一格（openpyxl 读不了旧二进制格式，xlrd 不在依赖里）。
    把两格丢进白名单的下场是 500，本件同时红。
    """
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": (filename, b"whatever the body is", "application/octet-stream")},
    )

    assert response.status_code == 400, response.text
    assert response.json() == {"detail": "unsupported_file"}
    assert retriever.indexed == {}
    assert list(tmp_path.iterdir()) == []


# ===========================================================================
# R91 —— 上传守卫拒绝的应当是「伪装后缀」，不是「文件名里有两个点」
#
# 立案事实（总控 09-18 22:20 实测）：旧判据 safe.count(".") > 1 把知识库 11 份
# 带版本号的制度文件全部判成 unsupported_file，其中 `费用报销管理制度V2.1.txt`
# 正是评测题 doc-01「住宿费标准是多少？」的答案出处。以下全部是**追加**用例，
# 上面的既有断言（含两条攻击用例与 magic-byte 用例）一行未改。
# ===========================================================================

# 真实语料里被旧规则永久挡在门外的 11 个文件名（逐名列举，不是抽一个代表）。
REAL_VERSIONED_FILENAMES = (
    "IT安全管理制度V3.1.txt",
    "MYBI_V3.1_更新日志.txt",
    "MYBI_部署手册V1.0.txt",
    "MYBI_部署手册V2.0.txt",
    "MYO_V5.3_更新日志.txt",
    "MYO_V5.4_更新日志.txt",
    "MYOps_V2.0_更新日志.txt",
    "员工绩效考核办法V1.0.txt",
    "员工绩效考核办法V2.0.txt",
    "财务管理制度_V2.0.txt",
    "费用报销管理制度V2.1.txt",
)

# 反证用的**独立副本**：这里故意把生产黑名单再抄一遍，而不是 import 进来复用。
# 生产侧摘掉任意一项 ⇒ 集合相等断言红，并且下面按这份副本参数化的行为用例同时红；
# 生产侧多加任意一项 ⇒ 集合相等断言红，放行类的 11 个真名用例也可能红。
# 两条路互为保险，所以「判据是假的」（改了黑名单没人发现）不成立。
EXPECTED_DISGUISE_SUFFIXES = (
    # R306 接线：生产那枚闭集从四格长到六格，这份**独立副本**同步补 `.csv`、`.xlsx` 两格。
    # 注意这不是放宽：新增的两格各自带一条按名参数化的拒绝用例（`ledger.csv.exe.txt` /
    # `book.xlsx.exe.txt` 必须继续被拒），所以副本只会比原来更严。
    ".txt", ".md", ".pdf", ".docx", ".csv", ".xlsx",
    ".doc", ".xls", ".ppt", ".pptx",
    ".exe", ".dll", ".com", ".scr", ".msi", ".lnk", ".jar",
    ".js", ".vbs", ".bat", ".cmd", ".sh", ".ps1",
    ".php", ".html", ".htm", ".svg",
    ".tar", ".gz", ".bz2", ".xz", ".zip", ".rar", ".7z",
)


@pytest.mark.parametrize("filename", REAL_VERSIONED_FILENAMES)
def test_sanitize_upload_filename_accepts_a_version_number_in_the_middle(filename):
    assert sanitize_upload_filename(filename) == filename


def test_the_accept_list_really_holds_the_11_case_filenames():
    """判据 ② 要求逐名放行：名单被缩水的 11 分之一都算不上证据。"""
    assert len(REAL_VERSIONED_FILENAMES) == 11
    assert len(set(REAL_VERSIONED_FILENAMES)) == 11


@pytest.mark.parametrize("filename", REAL_VERSIONED_FILENAMES)
def test_inspect_upload_header_accepts_the_real_corpus_filenames(filename):
    """These 11 names used to answer HTTP 400 unsupported_file at POST /upload."""
    inspection = inspect_upload_header(filename, "住宿费标准：省内出差每晚 300 元。".encode("utf-8"))

    assert inspection.original_filename == filename
    assert inspection.display_filename == filename
    assert inspection.extension == ".txt"
    assert inspection.media_type == "text/plain"


def test_inspect_upload_header_accepts_a_two_digit_version_in_a_pdf_name():
    inspection = inspect_upload_header("报告V10.2.pdf", b"%PDF-1.7\n")

    assert inspection.display_filename == "报告V10.2.pdf"
    assert inspection.extension == ".pdf"


def test_the_rule_judges_the_shape_of_the_name_not_the_number_of_dots():
    """点数不限全放行同样不是本单的判据：三个点的正常名放行，三个点的伪装名拒绝。"""
    assert sanitize_upload_filename("季度.经营.预算V2.1.txt") == "季度.经营.预算V2.1.txt"

    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename("quarter.pdf.exe.txt")


@pytest.mark.parametrize(
    "filename",
    ["a.pdf.txt", "政策.docx.txt", "notes.md.exe", "sheet.xlsx.txt", "a.tar.gz.exe"],
)
def test_sanitize_upload_filename_refuses_a_disguised_middle_segment(filename):
    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename(filename)


@pytest.mark.parametrize("filename", ["a.tar.gz.exe", "payload.pdf.txt"])
def test_inspect_upload_header_refuses_a_disguised_upload(filename):
    with pytest.raises(UploadSecurityError, match="double extensions") as exc_info:
        inspect_upload_header(filename, b"MZ\x90\x00")

    assert exc_info.value.code == "unsupported_file"


@pytest.mark.parametrize("suffix", [".PDF", ".ExE", ".DOCX"])
def test_the_disguise_check_is_case_insensitive(suffix):
    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename(f"report{suffix}.txt")


@pytest.mark.parametrize("filename", [".hidden.txt", "..hidden.txt"])
def test_sanitize_upload_filename_refuses_a_name_that_starts_with_a_dot(filename):
    """旧规则靠点数顺手挡掉的边界情形，现在要有自己的明确判据，不能变成放行。"""
    with pytest.raises(UploadSecurityError, match="must not start with a dot"):
        sanitize_upload_filename(filename)


@pytest.mark.parametrize("filename", [None, "", "   ", ".", ".."])
def test_sanitize_upload_filename_still_requires_a_real_name(filename):
    """判据 ⑤：空名/`.`/`..` 三条检查一条不许弱化。"""
    with pytest.raises(UploadSecurityError, match="filename is required"):
        sanitize_upload_filename(filename)


def test_the_disguise_blocklist_is_the_reviewed_closed_set():
    from app.documents.file_security import _DOUBLE_EXTENSION_BLOCKLIST

    assert _DOUBLE_EXTENSION_BLOCKLIST == frozenset(EXPECTED_DISGUISE_SUFFIXES)
    assert len(EXPECTED_DISGUISE_SUFFIXES) == len(set(EXPECTED_DISGUISE_SUFFIXES))
    assert all(suffix.startswith(".") and suffix == suffix.lower() for suffix in EXPECTED_DISGUISE_SUFFIXES)


@pytest.mark.parametrize("suffix", EXPECTED_DISGUISE_SUFFIXES)
def test_every_entry_in_the_blocklist_is_actually_refused_in_the_middle(suffix):
    """反证锚点：把生产黑名单里这一项摘掉，本用例立刻变红。"""
    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename(f"report{suffix}.txt")


def test_every_whitelisted_type_is_also_refused_as_a_middle_segment():
    """`policy.md.exe` 曾只靠 .exe 不是白名单后缀被兜住；这一条钉住 md/txt 也在黑名单里。"""
    from app.documents.file_security import _DOUBLE_EXTENSION_BLOCKLIST

    assert set(_ALLOWED_TYPES) <= set(_DOUBLE_EXTENSION_BLOCKLIST)


def test_a_versioned_upload_is_still_stored_under_one_uuid_suffix(tmp_path):
    """判据 ⑤：放行的是显示名，磁盘名仍旧是 uuid + 单一白名单后缀。"""
    inspection = inspect_upload_header(
        "费用报销管理制度V2.1.txt", "住宿费标准：300 元。".encode("utf-8")
    )
    stored = build_storage_path(
        tmp_path, "9f2c1d7e5a6b4c8d90e1f2a3b4c5d6e7", inspection.extension
    )

    assert inspection.display_filename == "费用报销管理制度V2.1.txt"
    assert stored.parent == tmp_path.resolve()
    assert stored.name == "9f2c1d7e5a6b4c8d90e1f2a3b4c5d6e7.txt"
    assert stored.name.count(".") == 1


def test_http_upload_accepts_all_11_versioned_corpus_names(tmp_path, monkeypatch):
    """Route-level proof: the names that returned 400 now reach the index."""
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    for filename in REAL_VERSIONED_FILENAMES:
        response = client.post(
            "/api/v1/upload",
            files={
                "file": (
                    filename,
                    "住宿费标准：省内出差每晚不超过 300 元。".encode("utf-8"),
                    "text/plain",
                )
            },
            data={"classification": "1", "department": "财务部"},
        )

        assert response.status_code == 200, f"{filename}: {response.status_code} {response.text}"
        assert response.json()["filename"] == filename
        assert retriever.indexed["filename"] == filename

    # 无 principal ⇒ 沿用既有的 unscoped 语义，本单不碰权限判定
    assert retriever.indexed["department"] is None


def test_http_upload_still_rejects_a_disguised_name_with_the_stable_code(tmp_path, monkeypatch):
    client, retriever = _document_upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("policy.pdf.txt", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "unsupported_file"}
    assert retriever.indexed == {}
    assert list(tmp_path.iterdir()) == []
