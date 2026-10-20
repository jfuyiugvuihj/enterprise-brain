"""R306 · 把 R305 那枚零消费者的电子表格出口接进 POST /api/v1/upload。

判据对应（派工词 §三，逐条）：
① 真件带正文 + 同一把尺 -> test_a_real_multi_sheet_workbook_arrives_* /
   test_a_semicolon_gbk_csv_arrives_* / test_the_corpus_* / test_the_new_spreadsheet_exit_*；
② 分派新增两格、带账入口走得到同一事实 -> test_the_report_entry_agrees_with_the_direct_exit_* /
   test_every_whitelisted_extension_is_actually_dispatched；
③ r130 的出口名单与元组加两枚 -> 由 tests/test_r130_..._refusal.py 自己承担，本件不复述；
④ 白名单 + 魔法字节 + 双扩展 -> test_the_upload_whitelist_holds_six_* /
   test_xlsx_still_needs_its_magic_* / test_a_spreadsheet_name_with_a_version_number_* /
   test_spreadsheets_store_under_one_uuid_suffix；
⑤ 注释与契约同一笔改口 -> test_the_comment_above_the_whitelist_no_longer_calls_them_datasets_only /
   test_the_contract_no_longer_claims_both_suffixes_were_removed；
⑥ 预览同格 -> test_a_spreadsheet_previews_as_the_text_the_indexer_stores；
⑦ 零新增错误码 -> test_this_ticket_adds_no_error_code。
施工口四在 loader 这一侧的凭据：test_the_anchor_first_field_follows_the_display_name
（chat.py 那一行撞的是别人的钉，未落笔，见交工回执）。

反证七把逐条写在每枚件自己的 docstring 里。全程离线：不连库、不起服务、不打模型；
xlsx 由 openpyxl 现造进 tmp_path，仓库不因此多出任何二进制；真件只读存量两枚表。
"""
from __future__ import annotations

import datetime
import inspect
import io
import re
from pathlib import Path

import openpyxl
import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.documents.file_security import (
    _ALLOWED_TYPES,
    _DOUBLE_EXTENSION_BLOCKLIST,
    UploadSecurityError,
    build_storage_path,
    inspect_upload_header,
    sanitize_upload_filename,
)
from app.documents.preview import PDF_EXTENSIONS, TEXT_EXTENSIONS, build_document_preview
from app.rag import loader, spreadsheets

REPO = Path(__file__).resolve().parents[1]
SECURITY_SOURCE = REPO / "app" / "documents" / "file_security.py"
LOADER_SOURCE = REPO / "app" / "rag" / "loader.py"
PREVIEW_SOURCE = REPO / "app" / "documents" / "preview.py"
CONTRACT = REPO / "docs" / "api" / "contract-v1.md"

CORPUS_CSV = REPO / "data" / "报销明细表.csv"
CORPUS_XLSX = REPO / "data" / "2026年6月门店经营数据.xlsx"

#: 与 tests/test_r130_... 同一把尺上的那块脏文本（这里不 import 那枚文件：两枚件各自
#: 把常量写死，谁改名都会当场红，而不是靠 import 一起漂）。
NUL = "\x00"
DIRTY_CHUNK = "第一段" + NUL + "第二段"
CLEAN_CHUNK = "第一段第二段"

UUID_NAME = "2f3a9c1e2b4d5f6a7b8c9d0e1f2a3b4c"


def _text(path: Path, display_name: str | None = None) -> str:
    return loader.load_document(str(path), display_name=display_name)


def _loader_source(name: str) -> str:
    """取 loader 里那一格今天的原文——源码账只认它自己，不认记忆。"""
    return inspect.getsource(getattr(loader, name))


def _write_workbook(path: Path) -> Path:
    """两张 sheet + 一处合并 + 一处全宽合并说明行（判据①要的"多 sheet 真件"）。"""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "一月"
    sheet.append(["部门", "金额", "发生日期"])
    sheet.append(["销售", 100.0, datetime.date(2026, 2, 1)])
    sheet.append(["研发", 0.1 + 0.2, datetime.datetime(2026, 2, 1, 14, 30, 0)])
    sheet.merge_cells("A4:C4")
    sheet["A4"] = "合计说明"
    second = book.create_sheet("二月")
    second.append(["城市", "门店数"])
    second.append(["杭州", 3])
    book.save(str(path))
    return path


def _write_csv(path: Path, body: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(body.encode(encoding))
    return path


# ------------------------------------------------------------------ ① 正文与同一把尺


def test_a_real_multi_sheet_workbook_arrives_with_anchored_text(tmp_path) -> None:
    """判据①：一份真 .xlsx（多 sheet）从 load_document 出来必须带正文，不是空串。"""
    path = _write_workbook(tmp_path / f"{UUID_NAME}.xlsx")

    body = _text(path)

    assert body.strip(), "load_document 交回了空正文"
    assert "Sheet「一月」" in body and "Sheet「二月」" in body
    assert "| 部门 | 金额 | 发生日期 |" in body
    assert "| 城市 | 门店数 |" in body and "| 杭州 | 3 |" in body
    assert body.count(" · Sheet「") == 2, "两张 sheet 各自成段，共两枚锚"


def test_a_semicolon_gbk_csv_arrives_with_anchored_text(tmp_path) -> None:
    """判据①：一份真 .csv 同上；编码与分隔符走的是既有那两把尺，不是新造的一套。"""
    path = _write_csv(tmp_path / f"{UUID_NAME}.csv", "部门;金额\n研发;300\n", encoding="gbk")

    body = _text(path)

    assert body.strip(), "load_document 交回了空正文"
    assert ".csv · 表1" in body
    assert "| 部门 | 金额 |" in body and "| 研发 | 300 |" in body


def test_the_corpus_spreadsheet_arrives_through_load_document() -> None:
    """判据①：存量真件（仓里那枚 146 行报销明细）端到端可读，且段首一律带锚。"""
    body = loader.load_document(str(CORPUS_CSV))

    assert body.startswith("报销明细表.csv · 表1"), body[:60]
    segments = [part for part in body.split("\n\n") if part.strip()]
    assert len(segments) > 1, "存量那枚件应当被装成多段"
    assert all(segment.startswith("报销明细表.csv · 表1") for segment in segments)
    assert "BX-" in body


def test_the_corpus_workbook_arrives_through_load_document() -> None:
    """判据①：存量真件的另一半是一枚 xlsx（1 sheet / 11 行 / 7 列），同样端到端可读。"""
    body = loader.load_document(str(CORPUS_XLSX))

    assert body.startswith("2026年6月门店经营数据.xlsx · Sheet「"), body[:60]
    assert "| " in body and body.count("\n| ") >= 10


def test_the_new_spreadsheet_exit_cannot_let_a_nul_through(tmp_path, monkeypatch) -> None:
    """判据①的账：R130 那句「每一个 load_* 出口」现在也包括电子表格这一格。

    反证：把 loader.load_spreadsheet 里那层 sanitize_text 摘掉，本件当场红——两枚入口都红，
    因为分派出口与带账出口各自都过尺。
    """
    monkeypatch.setattr(
        spreadsheets, "load_spreadsheet_text", lambda path, display_name=None: DIRTY_CHUNK
    )
    path = _write_csv(tmp_path / "a.csv", "x,y\n1,2\n")

    assert _text(path) == CLEAN_CHUNK
    assert NUL not in _text(path)
    assert loader.extract_document_with_reports(str(path)).text == CLEAN_CHUNK


def test_a_spreadsheet_that_really_holds_a_nul_leaves_none_behind(tmp_path) -> None:
    """不用桩的同一枚钉子：真件里的一枚 NUL，过完整条链路之后必须一个不剩。"""
    path = tmp_path / "dirty.csv"
    path.write_bytes(("部门,金额\n销售" + NUL + ",120\n").encode("utf-8"))

    body = loader.load_document(str(path))

    assert NUL not in body
    assert "销售" in body and "| 120 |" in body


def test_the_spreadsheet_exit_shares_the_one_ruler_by_construction() -> None:
    """源码账：新增这一格与其余五格同法——外面那层 sanitize_text 必须在分派出口上看得见。"""
    for name in ("load_spreadsheet", "load_document"):
        assert "sanitize_text(" in _loader_source(name), f"{name} 没过同一把尺"
    dispatch = _loader_source("load_document")
    assert "SPREADSHEET_SUFFIXES" in dispatch, "分派这一格不再认 spreadsheets 的后缀名单了"
    assert 'if ext in spreadsheet_channel.SPREADSHEET_SUFFIXES:' in dispatch


# ------------------------------------------------------------------ ② 两枚入口一个事实


@pytest.mark.parametrize("suffix", [".xlsx", ".csv"])
def test_the_report_entry_agrees_with_the_direct_exit(tmp_path, suffix) -> None:
    """判据②：R301 那枚带账入口必须走得到电子表格，而且正文逐字相同——不许两套事实。

    反证：把 extract_document_with_reports 里对 load_document 的调用退回不传 display_name，
    第二枚断言当场红；把它整格换成"不支持就 raise"，第一枚当场红。
    """
    path = tmp_path / f"{UUID_NAME}{suffix}"
    if suffix == ".xlsx":
        _write_workbook(path)
    else:
        _write_csv(path, "城市,门店数\n杭州,3\n")
    display = "门店表" + suffix

    reported = loader.extract_document_with_reports(str(path), display_name=display)
    direct = loader.load_document(str(path), display_name=display)

    assert reported.text == direct
    assert reported.text.startswith(display), "两枚入口的锚点第一段必须同一个名字"
    assert reported.file_path == str(path)
    assert reported.pdf is None
    assert reported.tables.source == "", "tables 通道没参与，这一格就该是空串"


def test_every_whitelisted_extension_is_actually_dispatched(monkeypatch) -> None:
    """判据②的防漂移：白名单里的每一格，分派出口都必须认得（400 变 500 就是这里裂的）。

    反证：往 _ALLOWED_TYPES 加一格而不补分派，本件当场红——这条与
    tests/test_file_upload_security.py 那枚按真实文件跑的对照件同一条病灶、不同一把尺。
    """
    for name in ("load_pdf", "load_docx", "load_doc", "load_txt", "load_md"):
        monkeypatch.setattr(loader, name, lambda path: "ok")
    monkeypatch.setattr(loader, "load_spreadsheet", lambda path, display_name=None: "ok")

    for extension in sorted(_ALLOWED_TYPES):
        assert loader.load_document("policy" + extension) == "ok", (
            f"{extension} 在白名单里，却走不出分派这一格：上传会拿到 500 而不是 400"
        )


# ------------------------------------------------------------------ ④ 白名单三格


def test_the_upload_whitelist_holds_six_parsable_types() -> None:
    """判据④：六格，一格不多一格不少——这既是新闭集，也是旧那枚四格钉的替代。

    反证：把 .xlsx 或 .csv 从 _ALLOWED_TYPES 摘掉，本件与路由那两枚件一起红（后者才是要害：
    白名单缩回去，客户的表就又回到 400 unsupported_file）。
    """
    assert set(_ALLOWED_TYPES) == {".pdf", ".txt", ".md", ".docx", ".xlsx", ".csv"}
    assert set(spreadsheets.SPREADSHEET_SUFFIXES) <= set(_ALLOWED_TYPES), (
        "解析层认的后缀必须也在上传白名单里，否则 400 与 500 各说各话"
    )


def test_xlsx_still_needs_its_magic_and_csv_has_nothing_to_verify() -> None:
    """判据④的"不许把校验整个绕过去"：xlsx 的 PK 顶还在，csv 走的是 .txt/.md 那一档。

    反证：给 .csv 也塞一枚签名，最后一行当场红；把 .xlsx 的签名清空，第二行当场红。
    """
    ok = inspect_upload_header("门店.xlsx", b"PK\x03\x04fake workbook body")
    assert ok.extension == ".xlsx"
    assert ok.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    with pytest.raises(UploadSecurityError, match="does not match"):
        inspect_upload_header("门店.xlsx", b"%PDF-1.7 not a workbook")

    with pytest.raises(UploadSecurityError, match="unsupported upload extension"):
        inspect_upload_header("legacy.xls", b"\xd0\xcf\x11\xe0aoledoc")

    text = inspect_upload_header("费用.csv", b"month,amount\n2026-01,120\n")
    assert text.extension == ".csv" and text.media_type == "text/csv"
    assert _ALLOWED_TYPES[".csv"][1] == (), "csv 没有 magic 可验：与 .txt/.md 同一档"
    assert _ALLOWED_TYPES[".txt"][1] == _ALLOWED_TYPES[".md"][1] == ()


@pytest.mark.parametrize("extension", [".xlsx", ".csv"])
def test_spreadsheets_store_under_one_uuid_suffix(tmp_path, extension) -> None:
    """判据④：落盘名仍旧是 uuid + 单一后缀——双扩展守卫的前提不能被白名单冲掉。"""
    stored = build_storage_path(tmp_path, "9f2c1d7e5a6b4c8d90e1f2a3b4c5d6e7", extension.lstrip("."))

    assert stored.parent == tmp_path.resolve()
    assert stored.name == "9f2c1d7e5a6b4c8d90e1f2a3b4c5d6e7" + extension
    assert stored.name.count(".") == 1


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_a_csv_or_xlsx_in_the_middle_of_a_name_is_still_a_disguise(suffix) -> None:
    """判据④：.csv 补进双扩展黑名单；`.xlsx` 本来就在，两格都要能抓住伪装。"""
    assert suffix in _DOUBLE_EXTENSION_BLOCKLIST
    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename(f"report{suffix}.exe")
    with pytest.raises(UploadSecurityError, match="double extensions"):
        sanitize_upload_filename(f"report{suffix}.txt")


def test_a_spreadsheet_name_with_a_version_number_still_passes() -> None:
    """R91 那条口径不许被黑名单稀释：中间那个点是命名习惯，不是文件类型。"""
    for name in ("费用报销明细V2.1.csv", "门店销量2026.6.xlsx", "MYBI_V3.1_更新日志.csv"):
        assert sanitize_upload_filename(name) == name, name


# ------------------------------------------------------------------ .xls：明确不做


def test_xls_is_refused_at_every_layer(tmp_path) -> None:
    """判据④/契约：.xls 三层都出声，而且用的都是既有那句 raise，零新增码。"""
    assert spreadsheets.UNSUPPORTED_SUFFIXES == (".xls",)

    with pytest.raises(UploadSecurityError, match="unsupported upload extension"):
        inspect_upload_header("旧账.xls", b"\xd0\xcf\x11\xe0aoledoc")
    with pytest.raises(ValueError, match="Unsupported file format: .xls"):
        loader.load_document(str(tmp_path / "旧账.xls"))
    with pytest.raises(ValueError, match="xlrd"):
        spreadsheets.load_spreadsheet_text(str(tmp_path / "旧账.xls"))


# ------------------------------------------------------------------ 施工口四：锚点第一段


def test_the_anchor_first_field_follows_the_display_name(tmp_path) -> None:
    """`_anchor_base(display_name, path)` 那一格真的接上了：传什么，锚点第一段就是什么。

    反证：把 load_document 里的 display_name 丢掉，第二枚断言当场红；把 load_spreadsheet 的
    关键字透传丢掉，第一枚断言当场红（uuid 会一路露到客户屏幕上）。
    """
    path = _write_workbook(tmp_path / f"{UUID_NAME}.xlsx")

    default = loader.load_document(str(path))
    renamed = loader.load_document(str(path), display_name="门店销量.xlsx")
    reported = loader.extract_document_with_reports(str(path), display_name="门店销量.xlsx")

    assert default.startswith(f"{UUID_NAME}.xlsx · Sheet「")
    assert renamed.startswith("门店销量.xlsx · Sheet「")
    assert reported.text == renamed, "带账入口与直连入口共用同一格出处名"
    assert spreadsheets._anchor_base("门店销量.xlsx", path) == "门店销量.xlsx"
    assert spreadsheets._anchor_base(None, path) == f"{UUID_NAME}.xlsx"


# ------------------------------------------------------------------ ⑥ 预览


@pytest.mark.parametrize("suffix", [".xlsx", ".csv"])
def test_a_spreadsheet_previews_as_the_text_the_indexer_stores(tmp_path, suffix) -> None:
    """判据⑥：预览与入库读的是同一枚出口——不许"能上传、点开是 415"。"""
    path = tmp_path / f"{UUID_NAME}{suffix}"
    if suffix == ".xlsx":
        _write_workbook(path)
    else:
        _write_csv(path, "部门;金额\n研发;300\n", encoding="gbk")

    result = build_document_preview(str(path), f"门店表{suffix}")

    assert result["kind"] == "text"
    assert result["truncated"] is False
    assert result["filename"] == f"门店表{suffix}"
    assert result["text"] == loader.load_document(str(path))


def test_the_preview_whitelist_covers_every_upload_whitelist_type() -> None:
    """上传白名单不许跑到预览白名单前面（漏一格的后果是干净的 415，不是 500）。"""
    assert set(_ALLOWED_TYPES) <= TEXT_EXTENSIONS | PDF_EXTENSIONS
    assert {".xlsx", ".csv"} <= TEXT_EXTENSIONS


# ------------------------------------------------------------------ 任务本身：路由


def _upload_client(monkeypatch, tmp_path):
    """把真实的路由挂在探针 app 上：不开端口、不跑 app.main 的 lifespan。"""
    from app.agents import tools
    from app.api.v1 import chat

    class FakeRetriever:
        def __init__(self):
            self.indexed = {}

        def add_document(self, filename, content, classification, department):
            self.indexed = {"filename": filename, "content": content}
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


def _workbook_bytes() -> bytes:
    buffer = io.BytesIO()
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "一月"
    sheet.append(["部门", "金额"])
    sheet.append(["销售", 120])
    second = book.create_sheet("二月")
    second.append(["城市", "门店数"])
    second.append(["杭州", 3])
    book.save(buffer)
    return buffer.getvalue()


def test_the_upload_route_indexes_a_real_workbook(tmp_path, monkeypatch) -> None:
    """本单的任务：.xlsx 像 pdf/docx/txt 一样进知识库——路由层端到端，不是单元层自说自话。"""
    client, retriever = _upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("门店销量.xlsx", _workbook_bytes(), "application/vnd.ms-excel")},
        data={"classification": "2"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["filename"] == "门店销量.xlsx"
    assert re.fullmatch(r"[0-9a-f]{32}\.xlsx", payload["stored_name"]), payload["stored_name"]
    assert (tmp_path / payload["stored_name"]).read_bytes()[:4] == b"PK\x03\x04"
    assert "Sheet「一月」" in retriever.indexed["content"]
    assert "| 杭州 | 3 |" in retriever.indexed["content"]
    # 施工口四那一格的路由级凭据：锚点第一段必须是上传的那个名字，不是落盘的 uuid。
    # 摘掉 chat.py 那一行的 `display_name=`，这一句立刻红（第一段变成 stored_name）。
    assert retriever.indexed["content"].startswith("门店销量.xlsx \u00b7 Sheet「"), retriever.indexed["content"]
    assert payload["stored_name"] not in retriever.indexed["content"], "uuid 落盘名漏进了客户可见的锚点"


def test_the_upload_route_indexes_a_real_csv(tmp_path, monkeypatch) -> None:
    """判据①的另一半：.csv 走同一条路由，落盘名同样只剩 uuid + 单一后缀。"""
    client, retriever = _upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("费用明细.csv", "部门;金额\n研发;300\n".encode("gbk"), "text/csv")},
        data={"classification": "1"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert re.fullmatch(r"[0-9a-f]{32}\.csv", payload["stored_name"]), payload["stored_name"]
    assert "| 研发 | 300 |" in retriever.indexed["content"]


def test_a_forged_workbook_body_fails_with_the_existing_parse_code(tmp_path, monkeypatch) -> None:
    """判据⑦：表头过了、内容读不出——沿用既有的 500 document_parse_failed，本单零新增码。

    这一格与 .docx 同法（`PK\\x03\\x04` 顶对得上、zip 却是坏的），不是电子表格特有的洞。
    """
    client, retriever = _upload_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("sales.xlsx", b"PK\x03\x04fake workbook body", "application/vnd.ms-excel")},
    )

    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "document_parse_failed"}
    assert retriever.indexed == {}, "解析没出来的东西不许进索引"
    # 失败版本保留文件（R220 的口径），但那只写了一半的 `.upload-*.tmp` 必须清干净。
    assert len(list(tmp_path.glob("*.xlsx"))) == 1, "上传落盘的文件不许被删掉"
    assert list(tmp_path.glob(".upload-*.tmp")) == [], "临时件留下了"


# ------------------------------------------------------------------ ⑤⑦ 账：注释、契约、码表


def test_the_comment_above_the_whitelist_no_longer_calls_them_datasets_only() -> None:
    """判据⑤：白名单上方那段注释不许再留"电子表格只属于 upload-excel"这半句假话。"""
    header = SECURITY_SOURCE.read_text(encoding="utf-8").split("_ALLOWED_TYPES = {", 1)[0]
    block = "\n".join(line for line in header.splitlines() if line.startswith("#"))[-1200:]

    assert "belong to POST /api/v1/upload-excel" not in block
    assert "Spreadsheets are datasets, not" not in block
    assert "spreadsheets.py" in block, "注释必须点名真正产出正文的那枚模块"
    assert "must be handled by" in block, "那条不变量本身还在"


def test_the_contract_no_longer_claims_both_suffixes_were_removed() -> None:
    """判据⑤：契约里那句"removed from the knowledge-base whitelist"必须与注释同一笔改口。"""
    contract = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert "`.xlsx` and `.csv` were removed from the knowledge-base whitelist" not in contract
    assert "`.xlsx`/`.csv` had been taken off the knowledge-base" in contract, "改口要留在原处"
    assert "## Knowledge-Base Spreadsheets (2026-09-26, R306)" in contract
    section = contract.split("## Knowledge-Base Spreadsheets (2026-09-26, R306)", 1)[1]
    for token in ("rows:", "cols:", "sheets:", "budget:", "time:"):
        assert token in section, f"五道截断码少点名了这一道：{token}"
    assert "xlrd" in section and "`.xls`" in section, ".xls 的拒绝要写进契约"
    assert "first field" in section, "锚点第一段怎么算，必须写在契约里"


def test_this_ticket_adds_no_error_code() -> None:
    """判据⑦：本单不治码表，所以三枚改动过的模块里一枚新码都不许多出来。"""
    for source in (LOADER_SOURCE, PREVIEW_SOURCE):
        text = source.read_text(encoding="utf-8")
        assert "HTTPException" not in text and 'detail="' not in text
    security = SECURITY_SOURCE.read_text(encoding="utf-8")
    assert set(re.findall(r'^\s*code = "([a-z_]+)"', security, re.M)) == {"unsupported_file"}
    assert "raise HTTPException" not in security
    assert 'detail="document_parse_failed"' not in security, "那一枚码的发射点在 chat.py，本单不搬动它"
