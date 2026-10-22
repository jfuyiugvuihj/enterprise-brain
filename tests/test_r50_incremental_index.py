"""R50 判据① 增量：库里已有 N 篇时改 1 篇，只许重嵌那一篇。

这里的向量库是真的 chromadb（tmp_path 下独立 PersistentClient），分块用 DocumentRetriever
自己的 splitter，写库走 add_document 那条 R21 闸门，一个字都没绕。被替换的只有
OllamaEmbeddings._call_api 这一个出网点：它返回按文档名定轴的 one-hot 向量，同一篇的每块
向量相同、不同篇互相正交，所以"这一篇在不在结果里"是可数的事实，不是余弦距离的噪声。

embed 条数是记账出来的，不是估出来的：桩把每一次 _call_api 收到的文本原样存下来，测试断言
"被问过的文本条数"。查询文本以"查询："开头、重建探针用重建命令自己的 PROBE_TEXT 辨认，三者
分账，谁也没有替谁数。

关于计划书那句"单文档增量 <2 s"：本文件测的是**不含模型推理**的那一半 —— 规划要读多少文件、
发多少次 embed、整轮墙钟多少毫秒，全部离线可复算。含真模型推理的那一半留给总控真机。
"""
from __future__ import annotations

import importlib
from pathlib import Path
import time

import pytest

from app.rag import indexing as indexing_module
from app.rag import retriever as retriever_module
from app.rag.indexing import (
    CODE_SCOPE_MISMATCH,
    CODE_SCOPE_UNKNOWN,
    PLAN_REASON_CONTENT_MOVED,
    PLAN_REASON_MATCHES,
    PLAN_REASON_NEVER_PUBLISHED,
    DocumentIndexPublication,
    EmbeddingScope,
    IndexPublisher,
    IndexRegistry,
    configured_embedding_scope,
    document_index_id,
    plan_index_refresh,
    publication_checksum,
)
from app.rag.retriever import DocumentRetriever

MODEL = retriever_module.EMBED_MODEL
WIDTH = retriever_module.EMBEDDING_DIM
QUERY_PREFIX = "查询："

#: 每篇文档占一个轴。文档正文里带着自己的名字，所以"这一条属于哪一篇"能从文本本身读出来。
MARKERS = ("alpha", "bravo", "charlie", "delta", "echo")
SPARE_AXIS = len(MARKERS)


def _command():
    return importlib.import_module("scripts.rebuild_index")


def _read(path) -> str:
    return Path(str(path)).read_text(encoding="utf-8")


def _axis_of(text: str) -> int:
    for axis, marker in enumerate(MARKERS):
        if marker in text:
            return axis
    return SPARE_AXIS


def _one_hot(axis: int) -> list:
    vector = [0.0] * WIDTH
    vector[axis] = 1.0
    return vector


def _body(marker: str, segments: int) -> str:
    """每段约 90 字，段数直接决定 splitter 会切出几块。"""
    return "\n\n".join(
        marker + " 第 " + str(step) + " 节：" + ("财务口径说明" * 12) for step in range(segments)
    )


class _Brain:
    """一个用例一套临时向量库、一份临时索引元数据、一本会数数的 embedding 桩。"""

    def __init__(self, tmp_path, monkeypatch, *, fixed_scope=True):
        self.documents: list[str] = []
        self.probe_calls = 0
        self.query_calls: list[str] = []
        self.scope = EmbeddingScope(MODEL, WIDTH)
        self.probe_text = _command().PROBE_TEXT
        monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
        monkeypatch.setenv("EMBEDDING_DIMENSION", str(WIDTH))
        monkeypatch.delenv(indexing_module.INDEX_METADATA_ENV, raising=False)
        brain = self

        def fake_call_api(_self, text):
            text = str(text)
            if text.startswith(QUERY_PREFIX):
                brain.query_calls.append(text)
            elif text == brain.probe_text:
                brain.probe_calls += 1
            else:
                brain.documents.append(text)
            return _one_hot(_axis_of(text))

        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api", fake_call_api)
        self.dir = tmp_path / "docs"
        self.dir.mkdir()
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.registry = IndexRegistry(
            tmp_path / "index-versions.json", scope=self.scope if fixed_scope else None
        )
        self.publisher = IndexPublisher(self.registry, store=None)
        self.chunker = self.retriever.splitter.split_text

    # ---- 语料与账本 ----

    @property
    def embed_count(self) -> int:
        """真正被送去嵌入的文本条数，探针与查询各算各的，不混进来。"""
        return len(self.documents)

    def reset_ledger(self) -> None:
        self.documents.clear()
        self.query_calls.clear()
        self.probe_calls = 0

    def write(self, filename: str, segments: int = 3) -> str:
        path = self.dir / filename
        path.write_text(_body(filename.split(".")[0], segments), encoding="utf-8")
        return str(path)

    def paths(self) -> dict:
        return {path.name: str(path) for path in self.dir.glob("*.txt")}

    def rows(self) -> list:
        return [
            {
                "filename": name,
                "version": 1,
                "storage_path": path,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
            for name, path in sorted(self.paths().items())
        ]

    def chunks_of(self, filename: str) -> list:
        return list(self.chunker(_read(self.dir / filename)))

    def publish(self, filename: str, version: int = 1):
        """只登记注册表，不碰向量库：用于造"库里已经有这些块"的前置态。"""
        outcome = self.publisher.apply(
            DocumentIndexPublication(
                filename=filename, version=version, chunks=tuple(self.chunks_of(filename))
            )
        )
        assert outcome is not None
        return outcome

    def upload(self, filename: str, version: int = 1):
        """真上传：add_document 写向量库，再发布描述它的版本。"""
        added, message = self.retriever.add_document(
            filename, _read(self.dir / filename), 1, "finance"
        )
        assert added is True, message
        return self.publish(filename, version)

    def search(self, marker: str, k: int = 3) -> list:
        return self.retriever.search(QUERY_PREFIX + marker, k=k)

    def plan(self, rows=None, **kwargs):
        kwargs.setdefault("scope", self.scope)
        return plan_index_refresh(
            rows if rows is not None else self.rows(),
            registry=self.registry,
            load_text=_read,
            chunk_texts=self.chunker,
            **kwargs,
        )

    def rebuild(self, rows=None, **kwargs):
        kwargs.setdefault("scope", self.scope)
        kwargs.setdefault("documents_dir", str(self.dir))
        return _command().run_rebuild(
            targets=rows if rows is not None else self.rows(),
            retriever=self.retriever,
            publisher=self.publisher,
            load_text=_read,
            apply=True,
            manual=True,
            **kwargs,
        )


@pytest.fixture
def brain(tmp_path, monkeypatch):
    return _Brain(tmp_path, monkeypatch)


@pytest.fixture
def library(brain):
    """四篇已入库的文档，块数互不相同，任何一篇都不等于全库。"""
    for name, segments in (
        ("alpha.txt", 5),
        ("bravo.txt", 3),
        ("charlie.txt", 4),
        ("delta.txt", 6),
    ):
        brain.write(name, segments)
        brain.upload(name)
    assert len({len(brain.chunks_of(name)) for name in brain.paths()}) > 1
    brain.reset_ledger()
    return brain


def _edit(brain, filename: str, segments: int = 9) -> int:
    """改一篇的正文，返回它改完后的块数。"""
    (brain.dir / filename).write_text(
        _body(filename.split(".")[0], segments) + " 这里改过了", encoding="utf-8"
    )
    return len(brain.chunks_of(filename))


# ==================== 规划本身一次 embed 都不发 ====================

def test_the_plan_decides_without_asking_the_embedder_for_anything(library):
    plan = library.plan()

    assert library.embed_count == 0, "规划阶段碰了 embedding，增量就成了空话"
    assert plan.documents == 4
    assert plan.rebuild_documents == 0
    assert plan.embedded_texts == 0
    assert [entry.reason for entry in plan.entries] == [PLAN_REASON_MATCHES] * 4


def test_the_plan_digest_is_the_digest_the_publisher_records(library):
    """规划用的摘要必须就是发布记录里的同一个函数算出来的，否则没有一轮会收敛。

    这是整条增量与续跑路的地基：两边各算一套摘要的话，计划永远说"内容变了"，
    --incremental 就退化成全库重嵌，还看不出来。
    """
    entry = library.plan().by_filename()["alpha.txt"]
    recorded = library.registry.current(document_index_id("alpha.txt"))
    recomputed = publication_checksum(
        DocumentIndexPublication(
            filename="alpha.txt", version=1, chunks=tuple(library.chunks_of("alpha.txt"))
        )
    )

    assert entry.reason == PLAN_REASON_MATCHES
    assert entry.checksum == recomputed == recorded.checksum
    assert entry.chunk_count == recorded.chunk_count

def test_a_never_published_document_is_scheduled_rather_than_assumed_clean(library):
    library.write("echo.txt", 3)

    plan = library.plan()

    assert plan.rebuild_documents == 1
    assert plan.by_filename()["echo.txt"].reason == PLAN_REASON_NEVER_PUBLISHED
    assert plan.embedded_texts == len(library.chunks_of("echo.txt"))
    assert library.embed_count == 0


# ==================== 判据①：改一篇只嵌一篇 ====================

def test_editing_one_document_in_a_library_of_four_re_embeds_only_that_document(library):
    new_chunks = _edit(library, "bravo.txt")
    others = sum(
        len(library.chunks_of(name)) for name in ("alpha.txt", "charlie.txt", "delta.txt")
    )
    assert new_chunks != others
    assert library.plan().by_filename()["bravo.txt"].reason == PLAN_REASON_CONTENT_MOVED

    report = library.rebuild(incremental=True)

    assert report["rebuilt"] == 1
    assert report["unchanged"] == 3
    assert report["remaining"] == 0
    assert report["failed"] == 0
    # 「被 embed 的文本条数 == 该篇的 chunk 数」，这条是判据①的正文。
    assert library.embed_count == new_chunks, library.documents
    assert report["embedded_texts"] == new_chunks + 1, "报告里的那一个 +1 是重建探针"
    assert report["planned_documents"] == 1
    assert report["planned_embeddings"] == new_chunks
    assert report["unchanged"] + report["rebuilt"] == 4
    assert library.embed_count < others
    print(
        "R50① 增量：库 4 篇 / 改 1 篇(bravo) -> 该篇块数 "
        + str(new_chunks)
        + "，被 embed 文本条数 "
        + str(library.embed_count)
        + "，其余三篇合计 "
        + str(others)
        + "，报告 embedded_texts="
        + str(report["embedded_texts"])
    )


def test_the_same_run_without_planning_re_embeds_the_whole_library(library):
    """旧行为的对照数：不规划就是一把梭，改一篇也要付全库的 embed。"""
    _edit(library, "bravo.txt")
    total = sum(len(library.chunks_of(name)) for name in library.paths())

    report = library.rebuild()

    assert report["rebuilt"] == 4
    # 未规划的一律按"profile 可能变了"处理：每篇先付一次 pre-flight（证明此刻删得起），
    # 再付本来的 N 次重嵌，整轮另有一次探针。账是 T + 4 + 1。
    assert library.embed_count == total + 4, library.documents
    assert report["embedded_texts"] == total + 5
    print(
        "R50① 对照：同一本库不加 --incremental 一把梭 -> 全库块数 "
        + str(total)
        + "，被 embed 文本条数 "
        + str(library.embed_count)
        + "（含每篇一次 pre-flight）"
    )
    assert report["planned_embeddings"] == 0, "没有 --incremental 就没有计划，全库都是活儿"


def test_an_unchanged_document_costs_no_store_read_either(library, monkeypatch):
    """「不得触发全库重扫」要拿得出凭据：没被点名的那几篇，一次 collection.get 都没有。"""
    seen: list[str] = []
    original = library.retriever.collection.get

    def spy(*args, **kwargs):
        where = (args[0] if args else kwargs.get("where")) or {}
        seen.append(str(where.get("filename") or "*"))
        return original(*args, **kwargs)

    monkeypatch.setattr(library.retriever.collection, "get", spy)
    _edit(library, "charlie.txt", 11)

    library.rebuild(incremental=True)

    assert set(seen) == {"charlie.txt"}, seen


def test_a_second_incremental_run_costs_nothing_and_moves_no_pointer(library):
    _edit(library, "bravo.txt")
    library.rebuild(incremental=True)
    library.reset_ledger()
    pointers = {name: library.registry.current(document_index_id(name)) for name in library.paths()}

    report = library.rebuild(incremental=True)

    assert report["rebuilt"] == 0
    assert report["unchanged"] == 4
    assert library.embed_count == 0
    assert library.probe_calls == 1, "探针是每轮一次，不是每篇一次"
    assert report["embedded_texts"] == 1
    for name, version in pointers.items():
        assert library.registry.current(document_index_id(name)) is version or (
            library.registry.current(document_index_id(name)).index_version_id
            == version.index_version_id
        )


def test_a_version_bump_with_identical_bytes_publishes_without_re_embedding(library):
    """目录版本动了、字节没动：注册表要跟上 v2，但不该为此多问一次模型。"""
    outcome = library.registry.current(document_index_id("alpha.txt"))
    before = library.embed_count

    report = library.rebuild(
        [
            row if row["filename"] != "alpha.txt" else dict(row, version=2)
            for row in library.rows()
        ],
        incremental=True,
    )

    assert report["rebuilt"] == 1
    assert library.embed_count == before, library.documents
    current = library.registry.current(document_index_id("alpha.txt"))
    assert current.index_version_id != outcome.index_version_id
    assert current.source_version_id == "alpha.txt|v2"
    assert report["documents"][0]["swap"] == "publish-only"


# ==================== 判据④：宽度与模型只认 configured_embedding_scope() ====================

def test_the_plan_asks_the_one_configured_reader_and_no_second_one(tmp_path, monkeypatch):
    """没有 --scope 时，计划用的 profile 就是 configured_embedding_scope() 那一个读法。

    这里刻意用 scope=None 建 IndexRegistry：应用侧声明入口（R90a）之后，注册表每次问的都是
    configured_embedding_scope()，测试把它和规划器对一遍，确认规划器没有第二套读法。
    """
    scope = configured_embedding_scope()
    registry = IndexRegistry(tmp_path / "indexes.json")
    plan = plan_index_refresh(
        [{"filename": "alpha.txt", "version": 1, "storage_path": ""}],
        registry=registry,
        load_text=_read,
        chunk_texts=lambda text: [text],
    )

    assert registry.scope == scope
    assert plan.scope == scope
    assert (plan.scope.embedding_model, plan.scope.dimension) == (MODEL, WIDTH)


def test_moving_the_configured_model_moves_the_plan_not_a_local_guess(library, monkeypatch):
    """EMBEDDING_MODEL 一改，全库都排上工，而且理由点名是"profile 不一致"。

    如果规划器自己另读一份常量、或者拿 DEFAULT_EMBEDDING_DIMENSION 猜一个宽度，这里就会露出来：
    计划会说"没事，不用重嵌"。
    """
    monkeypatch.setenv("EMBEDDING_MODEL", "some-other-embedder")
    moved = configured_embedding_scope()
    assert moved.embedding_model == "some-other-embedder"

    plan = library.plan(scope=moved)

    assert plan.rebuild_documents == 4
    assert {entry.reason for entry in plan.entries} == {CODE_SCOPE_MISMATCH}
    assert {entry.current_scope for entry in plan.entries} == {str(EmbeddingScope(MODEL, WIDTH))}


def test_a_declared_width_that_is_not_the_stored_one_is_never_rescued_by_the_default(
    library, monkeypatch
):
    """768 是"这套构建随包的模型"的描述，不是"猜一个宽度当它一致"的许可证。"""
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    plan = library.plan(scope=configured_embedding_scope())

    assert plan.rebuild_documents == 4
    assert {entry.reason for entry in plan.entries} == {CODE_SCOPE_MISMATCH}
    assert plan.embedded_texts == sum(len(library.chunks_of(name)) for name in library.paths())


def test_an_unknown_profile_refuses_to_plan_rather_than_assuming_anything(library):
    with pytest.raises(ValueError, match="usable embedding profile"):
        library.plan(scope=EmbeddingScope(MODEL, None))
    with pytest.raises(ValueError, match="usable embedding profile"):
        library.plan(scope=EmbeddingScope("", WIDTH))


def test_a_version_that_never_recorded_a_profile_is_not_treated_as_a_match(tmp_path, monkeypatch):
    """R22 的 unknown 语义原样保留：没记 profile 的老记录一律排工，理由是不知，不是相符。"""
    path = tmp_path / "indexes.json"
    path.write_text(
        __import__("json").dumps(
            {
                "current": {"document:alpha.txt": "document:alpha.txt:legacy"},
                "versions": [
                    {
                        "index_version_id": "document:alpha.txt:legacy",
                        "index_id": "document:alpha.txt",
                        "source_version_id": "alpha.txt|v1",
                        "backend": "chroma",
                        "chunk_count": 3,
                        "checksum": "a" * 64,
                        "status": "published",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = IndexRegistry(path, scope=EmbeddingScope(MODEL, WIDTH))
    (tmp_path / "docs").mkdir()
    rows = [{"filename": "alpha.txt", "version": 1, "storage_path": str(tmp_path / "x.txt")}]
    (tmp_path / "x.txt").write_text(_body("alpha", 3), encoding="utf-8")

    plan = plan_index_refresh(
        rows, registry=registry, load_text=_read,
        chunk_texts=lambda text: [line for line in text.splitlines() if line.strip()],
        scope=EmbeddingScope(MODEL, WIDTH),
    )

    assert [entry.reason for entry in plan.entries] == [CODE_SCOPE_UNKNOWN]
    assert plan.rebuild_documents == 1


def test_a_rebuilt_version_is_still_bound_to_the_profile_and_keeps_its_predecessor(library, monkeypatch):
    """版本绑定 model+width 的既有语义没动：换 profile 重嵌，新版本记新 profile，旧版本留档。

    注册表按重建命令自己的方式重建（同一份 metadata 文件，scope 取 configured_embedding_scope()），
    断言的因此是线上真实那一条声明路径，不是测试里凑出来的第二套读法。
    """
    old = library.registry.current(document_index_id("alpha.txt"))
    monkeypatch.setenv("EMBEDDING_MODEL", "some-other-embedder")
    moved = configured_embedding_scope()
    registry = IndexRegistry(library.registry.metadata_path, scope=moved)
    rows = [row for row in library.rows() if row["filename"] == "alpha.txt"]

    report = _command().run_rebuild(
        targets=rows,
        retriever=library.retriever,
        publisher=IndexPublisher(registry, store=None),
        scope=moved,
        documents_dir=str(library.dir),
        load_text=_read,
        apply=True,
        manual=True,
        incremental=True,
    )

    assert report["rebuilt"] == 1
    current = registry.current(document_index_id("alpha.txt"))
    assert (current.embedding_model, current.dimension) == ("some-other-embedder", WIDTH)
    assert current.index_version_id != old.index_version_id
    history = registry.history(document_index_id("alpha.txt"))
    assert [version.status for version in history] == ["superseded", "published"]
    assert history[0].index_version_id == old.index_version_id

# ==================== 单文档增量的耗时：分母不含模型推理 ====================

def test_one_document_incremental_step_stays_under_two_seconds_offline(library):
    """计划书口径 <2 s。这里测的是不含推理的那一半，含推理的那一半归总控真机。"""
    _edit(library, "delta.txt", 13)
    rows = library.rows()
    # 预热一次：墙钟要量的是算法本身，不是进程第一次读盘/第一次 import 的开机税。
    library.plan(rows)

    started = time.perf_counter()
    plan = library.plan(rows)
    planned_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    report = library.rebuild(rows, incremental=True)
    total_ms = (time.perf_counter() - started) * 1000

    assert report["rebuilt"] == 1
    assert planned_ms < 2000, planned_ms
    assert total_ms < 2000, total_ms
    print(
        "R50① 4 篇库改 1 篇：规划 "
        + format(planned_ms, ".1f")
        + " ms / 整轮（含真写库，不含模型推理）"
        + format(total_ms, ".1f")
        + " ms，embed "
        + str(report["embedded_texts"] - 1)
        + " 条（另有探针 1 条）"
    )
