"""R700 判据①③ · 走真路由上传的 xlsx／csv 必须真进知识库，并能被既有检索腿命中。

被本单接上的那条腿有多长，本件就量多长：夹具现造一份两列表（表头 + 三行）→ 走真路由
POST /api/v1/upload-excel 上传 → 再用在册检索出口 DocumentRetriever.search 按表头词与某一行的值
各查一次，两查都必须交出这一枚文档的块。中间一枚字节都不假：解析走 app/rag/loader.py，
值不值得入走 app/documents/index_policy.py，写库走 retriever.add_document，关键词那一路走
app/agents/tools.rebuild_bm25 —— 这四枚出口就是知识库路由 app/api/v1/chat.py::upload_document
今天已经在用的那四枚（判据①「入库只许复用既有那条腿」）。

判据③「表格通道不复制」在这里是一句可失败的话：写进库的正文必须逐字等于
loader.load_document(path, display_name=名字)，且库里那条命中必须是既有分块器切出来的原块。
谁另起一套渲染或第二套分块，这两句当场对不上。

替身只有四枚，各自都有理由，都不是被测代码的形状：
* OllamaEmbeddings._call_api 换成按词表定向 + L2 归一的假向量 —— 与同族在册件
  tests/test_r50_incremental_index.py 同一手法，让「这一篇在不在名次里」成为可数的事实。
  归一是必需的：遗留向量库缺省按 L2 排，不归一的二值向量会把「块更长」读成「越不像」。
* 模型发现那枚在册离线桩换成「embedding 模型在服务上」——闸门这一格要按生产分支走，
  服务答得出、且答的模型就是向量腿要调的那一枚；闸门自己的两格答复（模型没在／服务不答）
  由 tests/test_r700_dataset_upload_reads_the_document_dict.py 单独钉。
* chat.retriever 换成临时目录里的真 DocumentRetriever（透明替身只多记一本调用账）——
  仓库的 chroma_db 一枚字节都不碰，R134 那道闸门自己守着这句话。
* app.agents.tools.rebuild_bm25 记一笔就走：本件要证明的是「关键词那一路也被同一条腿叫过」，
  真重建读的是仓库 documents/，那是总控窗口的活。

全程离线：不连 PostgreSQL、不起服务、不开宿主模型端口、不打模型。
"""
from __future__ import annotations

import io
import math

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.rag import loader
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

DEPT = "r700-finance"
OWNER = "r700-manager"

HEADER_TERM = "预算额度"
ROW_TERM = "3100"
CSV_NAME = "预算明细表.csv"
XLSX_NAME = "预算明细表.xlsx"

#: 假向量的词表：查的两枚词、表里的列名与三行值，再加上对照文档自己的词。
VOCAB = (HEADER_TERM, ROW_TERM, "部门", "研发", "市场", "行政", "备份", "恢复", "制度")
#: 一枚词都不沾的文本走这一枚备用轴：交回的向量恒为非零，且与词表所有轴正交。
SPARE_AXIS = len(VOCAB)
MODEL = retriever_module.EMBED_MODEL
WIDTH = retriever_module.EMBEDDING_DIM

DECOY_NAME = "客户数据备份制度.txt"
DECOY_BODY = (
    "客户数据备份制度\n\n"
    "本制度规定每日全量备份的窗口与异地恢复演练的负责人，"
    "恢复演练每季度一次，备份介质不得离开本机房的机柜。"
)


# ==================== 夹具：两列表（表头 + 三行） ====================


def _csv_bytes() -> bytes:
    return "部门,预算额度\n研发,3100\n市场,2200\n行政,1800\n".encode("utf-8")


def _xlsx_bytes() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "预算"
    sheet.append(["部门", HEADER_TERM])
    sheet.append(["研发", 3100])
    sheet.append(["市场", 2200])
    sheet.append(["行政", 1800])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _upload_bytes(name: str) -> bytes:
    return _csv_bytes() if name.endswith(".csv") else _xlsx_bytes()


def _fake_vector(text: str) -> list[float]:
    """文本 → 词表上的定向单位向量（同 tests/test_r50_incremental_index.py 的手法）。

    一篇文档的每一块都拿到「这块里出现了哪些词」，所以表头词那一问把带表头的块排到第一，
    行值那一问把带那一行的块排到第一，对照文档在两问上都与查询向量正交。
    """
    axes = [index for index, term in enumerate(VOCAB) if term in text] or [SPARE_AXIS]
    vector = [0.0] * WIDTH
    weight = 1.0 / math.sqrt(len(axes))
    for axis in axes:
        vector[axis] = weight
    return vector


class _RecordingHandle:
    """真 handle 的透明替身：只多记一本「add_document 被谁叫过」的账，行为一个字不改。"""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.add_document_calls: list[tuple] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def add_document(self, *args, **kwargs):
        self.add_document_calls.append(args)
        return self._inner.add_document(*args, **kwargs)


class _Brain:
    """一副盘面：tmp 里的真向量库 + 真路由 + 数得清的替身 + 记账的关键词腿。"""

    def __init__(self, monkeypatch, tmp_path) -> None:
        from app.agents import tools as agent_tools
        from app.api.v1 import chat, data
        from app.common import auth, model_config
        from app.storage import datasets
        from app.storage.datasets import DatasetRegistry, InMemoryDatasetTableStore

        self.data_dir = tmp_path / "data"
        self.data_dir.mkdir()
        self.retriever = _RecordingHandle(
            DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        )
        self.bm25_calls: list[int] = []
        registry = DatasetRegistry(
            root=self.data_dir,
            metadata_path=self.data_dir / ".dataset-metadata.json",
            store=InMemoryDatasetTableStore(),
        )
        monkeypatch.setattr(data, "DATA_DIR", str(self.data_dir))
        monkeypatch.setattr(data, "dataset_registry", registry)
        monkeypatch.setattr(datasets, "dataset_registry", registry)
        monkeypatch.setattr(chat, "retriever", self.retriever)
        monkeypatch.setattr(
            auth,
            "get_user",
            lambda username: {
                "id": username,
                "username": username,
                "role": "manager",
                "department": DEPT,
            },
        )
        # 闸门按生产分支走：服务答得出，且答的正是向量腿要调的那一枚 embedding 模型。
        monkeypatch.setattr(
            model_config,
            "_fetch_registry",
            lambda url, *args, **kwargs: {"models": [{"name": MODEL}]},
        )
        monkeypatch.setattr(
            retriever_module.OllamaEmbeddings,
            "_call_api",
            lambda self, text: _fake_vector(str(text)),
        )
        monkeypatch.setattr(agent_tools, "rebuild_bm25", lambda: self.bm25_calls.append(1))
        self.registry = registry

    # ---- 路由侧的便利 ----

    def client(self):
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def headers(self, username: str = OWNER) -> dict[str, str]:
        from app.common.auth import create_token

        return {"Authorization": "Bearer {0}".format(create_token(username))}

    def upload(self, name: str, payload: bytes):
        return self.client().post(
            "/api/v1/upload-excel",
            headers=self.headers(),
            files={"file": (name, payload, "application/octet-stream")},
        )

    def stored_path(self, name: str):
        return self.data_dir / name

    @property
    def handle(self):
        return self.retriever


@pytest.fixture(params=[CSV_NAME, XLSX_NAME], ids=["csv", "xlsx"])
def table_upload(request, monkeypatch, tmp_path):
    """同一副夹具跑两形：csv 与 xlsx 都必须走通同一条腿。"""
    return _Brain(monkeypatch, tmp_path), request.param, _upload_bytes(request.param)


# ==================== 判据①：两查都必须交出这一枚文档的块 ====================


def test_the_header_word_finds_the_uploaded_table(table_upload) -> None:
    """判据①前半：表头词一问，第一枚命中就是这份表格，块里带着那一行表头。"""
    brain, name, payload = table_upload

    response = brain.upload(name, payload)

    assert response.status_code == 200, response.text
    assert brain.retriever.add_document_calls, "上传成功了，但知识库那条腿一枚块都没写"

    hits = brain.handle.search(HEADER_TERM, k=3)

    assert hits, "表头词查不到任何命中：这份表格没有真进知识库"
    assert hits[0]["source"] == name, [item["source"] for item in hits]
    assert HEADER_TERM in hits[0]["content"]
    assert hits[0]["retrieval_mode"] == DocumentRetriever.MODE_SEMANTIC, "这条名次是降级腿蒙的"


def test_a_row_value_finds_the_same_document(table_upload) -> None:
    """判据①后半：换成某一行的值再问一次，交回来的还是同一枚文档的块。"""
    brain, name, payload = table_upload

    response = brain.upload(name, payload)

    assert response.status_code == 200, response.text

    hits = brain.handle.search(ROW_TERM, k=3)

    assert hits, "行值查不到任何命中：这份表格没有真进知识库"
    assert hits[0]["source"] == name, [item["source"] for item in hits]
    assert ROW_TERM in hits[0]["content"]
    assert hits[0]["retrieval_mode"] == DocumentRetriever.MODE_SEMANTIC


def test_the_decoy_document_loses_both_queries(table_upload) -> None:
    """对照文档同时在场：两枚名次都不是「库里只有一篇所以必然命中」挣来的。"""
    brain, name, payload = table_upload
    accepted, message = brain.handle.add_document(DECOY_NAME, DECOY_BODY, 2, DEPT)
    assert accepted, message

    response = brain.upload(name, payload)

    assert response.status_code == 200, response.text
    for term in (HEADER_TERM, ROW_TERM):
        hits = brain.handle.search(term, k=2)
        assert hits, term
        assert hits[0]["source"] == name, (term, [item["source"] for item in hits])
        assert all(item["source"] != DECOY_NAME for item in hits[:1]), (
            "对照文档在表头词/行值两问上都该排在表格之后，第一枚就不许是它"
        )
    # 权限口径同一条腿：部门过滤交给同一枚 search 的 where，别人的部门查不到这一枚表格。
    assert brain.handle.search(HEADER_TERM, k=3, where={"department": "r700-hr"}) == []


# ==================== 判据③：表格通道只有既有那一套 ====================


def test_the_indexed_body_is_the_existing_loader_exit_verbatim(table_upload) -> None:
    """判据③：写进库的正文与块，都出自既有那两枚出口，没有第二套渲染或分块。"""
    brain, name, payload = table_upload

    response = brain.upload(name, payload)

    assert response.status_code == 200, response.text
    stored = brain.retriever.add_document_calls[0]
    assert stored[0] == name, "入库用的文档名不是客户上传的那个名字"

    expected_body = loader.load_document(str(brain.stored_path(name)), display_name=name)
    chunks = brain.handle.splitter.split_text(expected_body)

    assert stored[1] == expected_body, "写库正文不是既有通道交回的那一段"
    assert "| 部门 | {0} |".format(HEADER_TERM) in stored[1], "表格没按在册的 markdown 形状渲染"
    assert any(ROW_TERM in chunk for chunk in chunks), "既有分块器切不出带行值的那块"

    hits = brain.handle.search(ROW_TERM, k=5)
    assert hits, "行值查不到命中"
    assert hits[0]["content"] in chunks, "库里的块不是既有分块器切出来的原块"


def test_the_keyword_leg_is_rebuilt_through_the_same_exit(table_upload) -> None:
    """入库四枚出口里那枚关键词腿也必须被叫到，且只叫一次——它同样是复用不是另起。"""
    brain, name, payload = table_upload

    response = brain.upload(name, payload)

    assert response.status_code == 200, response.text
    assert brain.bm25_calls == [1], "关键词那一路没走在册的 rebuild_bm25 出口"
    assert len(brain.retriever.add_document_calls) == 1
