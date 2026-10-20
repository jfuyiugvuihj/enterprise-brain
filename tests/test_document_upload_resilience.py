import asyncio
import io
from concurrent.futures import Future
from pathlib import Path

from fastapi import UploadFile
import pytest

# 现场 A（R364）：下面那枚「上传腿」钉原来把 app/api/v1/chat.py 的**一行原文**抄进测试。
# 那是本仓第五枚同族雷（前四枚的形状：抄行号 / 抄迁移尾号 / 抄一行源文本 / 抄一枚十六进制指纹，
# 账见 tests/test_r346_line_ledger_is_derived_not_copied.py 与 tests/test_r351_stale_ledger_teeth.py）。
# 手抄的账每演进一次就红一次（R306 第二棒 6d00d70 给同一处加了 display_name= 就是那一次），而它红的
# 时候看起来像「上传路由坏了」。正解不是把字面量改成今天的样子（那是把雷重新埋一遍），是换成形状判据。
# 尺子用 R298 自己那把，不另造第二把；它的牙与「参数表演进不许多红一枚」由
# tests/test_r364_shape_ruler_teeth.py（常驻反证）与 tests/fixtures/r364_refutation_driver.py（盘上真刀）盯。
from test_r298_ocr_channel import (  # noqa: E402
    CHAT_SOURCE,
    assert_upload_leg_parses_off_the_event_loop,
)


def test_upload_rejects_a_client_path_before_writing_files(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from fastapi import HTTPException

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    upload = UploadFile(filename="nested/policy.txt", file=io.BytesIO(b"policy"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_upload_enforces_size_limit_and_removes_partial_file(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools
    from fastapi import HTTPException

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "MAX_DOCUMENT_UPLOAD_BYTES", 4)
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="policy.txt", file=io.BytesIO(b"12345"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_embedding_failure_skips_remaining_chunks_during_cooldown(monkeypatch):
    from app.rag import retriever

    calls = 0

    def unavailable(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("Ollama unavailable")

    monkeypatch.setattr(retriever.urllib.request, "urlopen", unavailable)

    embeddings = retriever.OllamaEmbeddings()
    result = embeddings.embed_documents(["first chunk", "second chunk"])

    assert calls == 1
    assert len(result) == 2
    assert all(vector == [0.0] * 768 for vector in result)


def test_embedding_timeout_default_is_bounded_and_overridable(monkeypatch):
    """钉住“有界且可覆盖”这个契约本身，而不是某个具体秒数。

    原断言是 `timeout == 1.0`（上传期防止无限挂死钉下的）。R21 把默认值换成有界常量
    EMBED_TIMEOUT_DEFAULT_SECONDS：模型冷加载时 1 秒必然不够（跟进单 §17 实测点），
    而“不许无限等”这条原意由“等于导出的常量 + 落在 1~60 秒之间 + 可被环境变量覆盖”
    三句继续守住，没有放宽。
    """
    from app.rag import retriever as rag_retriever
    from app.rag.retriever import OllamaEmbeddings

    monkeypatch.delenv("OLLAMA_EMBED_TIMEOUT", raising=False)
    default = OllamaEmbeddings().timeout

    assert default == rag_retriever.EMBED_TIMEOUT_DEFAULT_SECONDS
    assert 1.0 < default <= 60.0, "超时必须有界：不许退化成 None 或无限等待"

    monkeypatch.setenv("OLLAMA_EMBED_TIMEOUT", "0.5")
    assert OllamaEmbeddings().timeout == 0.5


def test_upload_keeps_document_when_optional_metadata_store_is_down(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: "document content")
    monkeypatch.setattr(chat, "_upsert_document", lambda *args: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(chat, "record_document_version", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="policy.txt", file=io.BytesIO(b"policy"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert response["stored_name"] != "policy__v1.txt"
    assert (tmp_path / response["stored_name"]).exists()


def test_upload_moves_blocking_parsing_and_indexing_off_the_event_loop():
    """上传腿的阻塞解析必须离开事件循环：形状判据，参数表允许演进（R364 现场 A）。

    三件事同时成立才算绿：① 上传路由里**恰好一枚** ``await asyncio.to_thread(load_document, ...)``；
    ② 交给解析器的路径是本函数里 ``str(...)`` 绑出来的落盘路径；③ 被调的 ``load_document`` 真出自
    ``app.rag.loader``（AST 判模块级导入，不是子串）。摘掉 to_thread（退回同步解析）、把被调符号换成
    loader 以外的东西、多长一枚第二处调用，三样都当场红；给那一行加一枚新 kwarg 或换掉变量名不红。
    """
    assert_upload_leg_parses_off_the_event_loop(CHAT_SOURCE)
    # 最粗的一条兜底，与上面三件事无关：整本 chat.py 连线程出口都没了就是彻底跑偏。
    # 这条子串不指名任何被调符号，因此它不随参数表演进——抄写不在它身上。
    assert "await asyncio.to_thread(" in CHAT_SOURCE


def test_upload_schedules_bm25_rebuild_without_waiting_for_it(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    class FakeExecutor:
        def __init__(self):
            self.submitted = []

        def submit(self, function, *args):
            self.submitted.append((function, args))
            return Future()

    executor = FakeExecutor()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False)
    monkeypatch.setattr(chat, "_executor", executor)

    upload = UploadFile(filename="async-index.txt", file=io.BytesIO(b"async index"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert executor.submitted == [(tools.rebuild_bm25, ())]


def test_document_version_uses_local_files_when_postgres_is_offline(tmp_path, monkeypatch):
    from app.documents import catalog

    (tmp_path / "policy__v1.txt").write_text("first", encoding="utf-8")
    (tmp_path / "policy__v2.txt").write_text("second", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False, raising=False)
    monkeypatch.setattr(
        catalog,
        "_conn",
        lambda: (_ for _ in ()).throw(AssertionError("offline mode must not connect to PostgreSQL")),
    )

    assert catalog.peek_next_document_version("policy.txt") == 3
    metadata = catalog.record_document_version(
        "policy.txt",
        classification=1,
        department="",
        storage_path=str(tmp_path / "policy__v3.txt"),
        version=3,
    )

    assert metadata["version"] == 3


def test_upload_skips_optional_metadata_sync_when_postgres_is_offline(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from app.agents import tools

    class FakeRetriever:
        def add_document(self, filename, content, classification, department):
            return True, "indexed"

    metadata_synced = False

    def unexpected_metadata_sync(*args, **kwargs):
        nonlocal metadata_synced
        metadata_synced = True
        raise AssertionError("offline upload must not attempt metadata sync")

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", FakeRetriever())
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: "document content")
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(chat, "_upsert_document", unexpected_metadata_sync)
    monkeypatch.setattr(chat, "record_document_version", unexpected_metadata_sync)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    upload = UploadFile(filename="offline.txt", file=io.BytesIO(b"offline"))
    response = asyncio.run(chat.upload_document(upload))

    assert response["status"] == "ok"
    assert metadata_synced is False


def test_document_retriever_batches_large_collection_writes():
    from app.rag.retriever import DocumentRetriever, EMBEDDING_DIM

    class FakeCollection:
        def __init__(self):
            self.calls = []

        def get(self, where=None):
            return {"ids": [], "metadatas": []}

        def add(self, **kwargs):
            self.calls.append(kwargs)

    class FakeSplitter:
        def split_text(self, content):
            return [f"chunk-{i}" for i in range(4500)]

    class FakeEmbedding:
        def embed_documents(self, texts):
            # 桩必须满足 R21 写库闸门的合法形状（维度 EMBEDDING_DIM、非全零）：这条用例
            # 测的是分批边界，闸门另有它自己的用例，别让断言变成在测闸门。
            template = [0.5] + [0.0] * (EMBEDDING_DIM - 1)
            return [list(template) for _ in texts]

    retriever = DocumentRetriever.__new__(DocumentRetriever)
    retriever.collection = FakeCollection()
    retriever.splitter = FakeSplitter()
    retriever.embedding = FakeEmbedding()

    ok, msg = DocumentRetriever.add_document(retriever, "big.txt", "x" * 10)

    assert ok is True
    assert "4500" in msg
    assert len(retriever.collection.calls) == 3
    assert [len(call["ids"]) for call in retriever.collection.calls] == [2000, 2000, 500]


def test_pdf_loader_uses_local_pypdf_extraction(monkeypatch):
    from app.rag import loader

    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, path):
            self.path = path
            self.pages = [FakePage("第一页"), FakePage("第二页")]

    monkeypatch.setattr(loader, "PdfReader", FakeReader)

    assert loader.load_pdf("demo.pdf") == "第一页\n\n第二页"


def test_upload_returns_clear_error_when_pdf_parse_fails(tmp_path, monkeypatch):
    from app.api.v1 import chat
    from fastapi import HTTPException

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(chat, "build_storage_name", lambda filename, version: f"{Path(filename).stem}__v{version}.pdf")
    monkeypatch.setattr(chat, "load_document", lambda path, display_name=None: (_ for _ in ()).throw(ValueError("boom")))

    upload = UploadFile(filename="policy.pdf", file=io.BytesIO(b"%PDF-1.4 test"))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(chat.upload_document(upload))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "document_parse_failed"
    assert "\\" not in exc_info.value.detail and ":" not in exc_info.value.detail

def test_api_error_details_are_stable_codes():
    """P2-8 防漂移：主 thread 负责的路由只能返回稳定 code。

    允许三种形式：
    1. `detail="snake_case_ascii_code"`；
    2. `detail={"code": ..., "message": ...}` 结构体（必须显式带 code 键）；
    3. 来自授权决策/作用域错误的变量表达式（reason_code、scope_error.code 等）。
    禁止 f-string 拼接与任何含中文/空格的句子。
    """
    import ast
    import io
    import re

    code_pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    offenders = []

    for module in ("app/api/v1/chat.py", "app/api/v1/intelligence.py"):
        source = io.open(module, encoding="utf-8-sig").read()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "HTTPException":
                continue
            detail = next((kw.value for kw in node.keywords if kw.arg == "detail"), None)
            location = f"{module}:{node.lineno}"
            if isinstance(detail, ast.JoinedStr):
                offenders.append((location, "interpolated detail string"))
                continue
            if isinstance(detail, ast.Dict):
                keys = [key.value for key in detail.keys if isinstance(key, ast.Constant)]
                if "code" not in keys:
                    offenders.append((location, "envelope without code"))
                continue
            if isinstance(detail, ast.Constant):
                value = detail.value
                if not isinstance(value, str) or not code_pattern.match(value) or not value.isascii():
                    offenders.append((location, value))

    assert offenders == []
