"""R50 判据② 可中断续跑：跑到一半停得下，再跑接得上，最后与一次跑完逐 chunk 相同。

② 用一本假向量库：分块、写入、删除、读回全是确定性的，所以"第一跑到 k 篇停 / 第二跑只做剩下
的 N-k 篇 / 两跑合计 == 单跑"这三行数字是逐条数出来的，不是估的。中断全靠可注入的边界
（stop_after、可注入时钟、会死的 embedding 桩）模拟 —— 没有 SIGKILL，没有真进程，没有真模型。

profile 那一档单独测：换 embedder 之后 add_document 会答"内容未变化"而一个字都不写，所以那条路
必须强制 retire，而强制 retire 现在先花一次"这一篇自己的" embed 证明删得起。embedding 半路死掉
时旧向量原样留在库里，就是这个 pre-flight 换来的东西。

全程 LOCAL_MODEL_NAME=__eb_test_disabled__；这个文件不出网，也不碰 chromadb。
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import inspect

from app.rag import indexing as indexing_module
from app.rag import retriever as retriever_module
from app.rag.indexing import (
    DocumentIndexPublication,
    EmbeddingScope,
    IndexPublisher,
    IndexRegistry,
    document_index_id,
    plan_index_refresh,
)
from app.rag.retriever import DocumentRetriever

MODEL = retriever_module.EMBED_MODEL
WIDTH = retriever_module.EMBEDDING_DIM
SCOPE = EmbeddingScope(MODEL, WIDTH)
SWAPPED = EmbeddingScope("some-other-embedder", WIDTH)
MARKERS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")


def _command():
    return importlib.import_module("scripts.rebuild_index")


def _read(path) -> str:
    return Path(str(path)).read_text(encoding="utf-8")


def _body(marker: str, lines: int) -> str:
    return "\n".join(marker + " 第 " + str(step) + " 行：财务口径说明" for step in range(lines))


class _Splitter:
    """与 _Library.add_document 同一份分块实现；两套分块的话摘要永远对不上。"""

    def split_text(self, text):
        return [line for line in str(text).splitlines() if line.strip()]


class _Embeddings:
    """数得清被打过几次、并且可以在第 N 次开始死的 embedding 桩。"""

    def __init__(self, *, poison_at=None):
        self.texts: list[str] = []
        self.poison_at = poison_at
        self.calls = 0

    def embed_query(self, text):
        self.calls += 1
        if self.poison_at is not None and self.calls > self.poison_at:
            raise RuntimeError("ollama died mid-run")
        self.texts.append(str(text))
        return [0.5] * WIDTH

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class _Collection:
    def __init__(self, library):
        self._library = library

    def get(self, where=None, include=None):
        filename = (where or {}).get("filename")
        names = [filename] if filename else list(self._library.records)
        ids, documents, metadatas, vectors = [], [], [], []
        for name in names:
            for ordinal, (content, vector) in enumerate(self._library.records.get(name, ())):
                ids.append(name + "_" + str(ordinal))
                documents.append(content)
                metadatas.append({"filename": name, "chunk_index": ordinal})
                vectors.append(vector)
        result = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if include and "embeddings" in list(include):
            result["embeddings"] = vectors
        return result


class _Library:
    """DocumentRetriever 里重建命令真正会碰的那几件东西，逐条可预测。"""

    def __init__(self, tmp_path, *, poison_at=None):
        self.embedding = _Embeddings(poison_at=poison_at)
        self.splitter = _Splitter()
        self.records: dict = {}
        self.calls: list = []
        self.dir = tmp_path / "corpus"
        self.dir.mkdir(parents=True)
        self.metadata_path = tmp_path / "index-versions.json"
        self.registry = IndexRegistry(self.metadata_path, scope=SCOPE)
        self.publisher = IndexPublisher(self.registry, store=None)

    # ---- 向量库侧 ----

    @property
    def collection(self):
        return _Collection(self)

    def document_chunks(self, filename):
        return [
            {
                "vector_id": filename + "_" + str(ordinal),
                "content": content,
                "chunk_index": ordinal,
                "classification": 1,
                "department": "finance",
                "hash": "stored",
            }
            for ordinal, (content, _vector) in enumerate(self.records.get(filename, ()))
        ]

    def delete_document(self, filename):
        self.calls.append(("delete", filename))
        self.records.pop(filename, None)

    def add_document(self, filename, content, classification=1, department=None):
        self.calls.append(("add", filename))
        texts = self.splitter.split_text(content)
        vectors = self.embedding.embed_documents(texts)
        self.records[filename] = list(zip(texts, vectors))
        return True, "已添加 " + str(len(texts)) + " 个文本块"

    # ---- 语料与账本 ----

    def embedded_texts(self):
        return len(self.embedding.texts)

    def write(self, filename: str, lines: int) -> str:
        path = self.dir / filename
        path.write_text(_body(filename.split(".")[0], lines), encoding="utf-8")
        return str(path)

    def seed(self, filename: str, lines: int) -> None:
        """入库一篇并登记版本；这段账不算进 embedding 计数。"""
        self.write(filename, lines)
        texts = self.splitter.split_text(_read(self.dir / filename))
        self.records[filename] = [(text, [0.1] * WIDTH) for text in texts]
        self.publisher.apply(
            DocumentIndexPublication(filename=filename, version=1, chunks=tuple(texts))
        )
        self.embedding.texts.clear()

    def rows(self):
        return [
            {
                "filename": name,
                "version": 1,
                "owner_id": "alice",
                "classification": 1,
                "department": "finance",
                "storage_path": str(self.dir / name),
            }
            for name in sorted(self.records)
        ]

    def fingerprints(self):
        """每篇的 (正文块序列, 当前版本摘要, 当前块数)：两跑合一之后要和单跑逐字相同。"""
        out = {}
        for name in sorted(self.records):
            try:
                version = self.registry.current(document_index_id(name))
            except KeyError:
                version = None
            out[name] = (
                tuple(row for row, _vector in self.records[name]),
                version.checksum if version else "",
                version.chunk_count if version else -1,
            )
        return out

    def use_profile(self, scope):
        """操作人换了 embedder 再敲一次命令：同一份元数据文件，新的声明 profile。"""
        self.registry = IndexRegistry(self.metadata_path, scope=scope)
        self.publisher = IndexPublisher(self.registry, store=None)

    def rebuild(self, **kwargs):
        kwargs.setdefault("scope", SCOPE)
        kwargs.setdefault("documents_dir", str(self.dir))
        return _command().run_rebuild(
            targets=self.rows(),
            retriever=self,
            publisher=self.publisher,
            load_text=_read,
            apply=True,
            manual=True,
            **kwargs,
        )


def _content_drift(tmp_path, *, poison_at=None):
    """六篇入库后各加两行：正文变了，profile 没变 —— 增量该只付变化那些。"""
    library = _Library(tmp_path, poison_at=poison_at)
    for name in MARKERS:
        library.seed(name + ".txt", 3)
    for name in MARKERS:
        library.write(name + ".txt", 5)
    return library


def _profile_drift(tmp_path, *, poison_at=None):
    """六篇入库后换了 embedder：正文一字未动，profile 变了 —— 六篇都得重嵌。"""
    library = _Library(tmp_path, poison_at=poison_at)
    for name in MARKERS:
        library.seed(name + ".txt", 3)
    library.use_profile(SWAPPED)
    return library


# ==================== 内容漂移：低峰跑两轮 ====================


def test_the_first_run_stops_at_two_documents_and_reports_the_four_left(tmp_path):
    library = _content_drift(tmp_path)

    report = library.rebuild(incremental=True, stop_after=2)

    assert report["attempted"] == 2
    assert report["rebuilt"] == 2
    assert report["remaining"] == 4
    assert report["stopped_at"] == "stop_after=2"
    # 1 次整轮探针 + 两篇各 5 块。增量那一腿不删旧的，所以没有 pre-flight。
    assert report["embedded_texts"] == 1 + 2 * 5
    assert [row["status"] for row in report["documents"]] == ["rebuilt", "rebuilt"]
    assert library.calls == [("add", "alpha.txt"), ("add", "bravo.txt")]
    print("R50② 第一跑 stop_after=2 -> attempted=2 rebuilt=2 remaining=4 embedded=" + str(report["embedded_texts"]))


def test_the_second_run_only_does_the_remaining_four(tmp_path):
    library = _content_drift(tmp_path)
    library.rebuild(incremental=True, stop_after=2)
    before = library.embedded_texts()

    report = library.rebuild(incremental=True)

    assert report["unchanged"] == 2, "前两篇已由第一篇留下的注册表认定完成"
    assert report["rebuilt"] == 4
    assert report["remaining"] == 0
    assert report["stopped_at"] == ""
    assert library.embedded_texts() - before == 4 * 5 + 1, "第二跑只付剩下四篇"
    print(
        "R50② 第二跑（同一本库同一份注册表）-> unchanged=2 rebuilt=4 remaining=0 "
        "embed 增量=" + str(library.embedded_texts() - before)
    )


def test_two_runs_land_on_exactly_what_one_run_would_have_produced(tmp_path):
    split = _content_drift(tmp_path / "split")
    split.rebuild(incremental=True, stop_after=2)
    split.rebuild(incremental=True)
    single = _content_drift(tmp_path / "single")
    single.rebuild(incremental=True)

    assert split.fingerprints() == single.fingerprints()
    assert sorted(split.records) == sorted(single.records)
    print(
        "R50② 合计：两跑 2+4=6 篇 == 单跑 6 篇，逐 chunk 指纹一致；"
        "embed 两跑=" + str(split.embedded_texts()) + " 单跑=" + str(single.embedded_texts())
    )
    for name in single.records:
        assert split.records[name] == single.records[name]


def test_a_third_run_finds_nothing_to_do_and_knocks_on_no_door(tmp_path):
    library = _content_drift(tmp_path)
    library.rebuild(incremental=True)
    calls_before = list(library.calls)
    embedded_before = library.embedded_texts()
    pointers = {name: library.registry.current(document_index_id(name)) for name in library.records}

    report = library.rebuild(incremental=True)

    assert report["rebuilt"] == 0
    assert report["unchanged"] == 6
    assert report["remaining"] == 0
    assert library.calls == calls_before, "第三次连向量库都不该敲一下"
    assert library.embedded_texts() - embedded_before == 1, "只有整轮探针那一次"
    for name, version in pointers.items():
        assert (
            library.registry.current(document_index_id(name)).index_version_id
            == version.index_version_id
        )


def test_resume_needs_no_manual_cleanup_and_leaves_no_temporary_behind(tmp_path):
    library = _content_drift(tmp_path)
    library.rebuild(incremental=True, stop_after=3)

    home = library.metadata_path.parent
    files = sorted(path.name for path in home.iterdir() if path.is_file())
    assert files == ["index-versions.json"], files
    assert not list(home.glob(".*")) and not list(library.dir.glob("*.tmp"))

    # 第二个进程只重新打开同一份文件，不需要谁去清库、删临时物。
    resumed = IndexRegistry(library.metadata_path, scope=SCOPE)
    plan = _command().plan_index_refresh(
        library.rows(),
        registry=resumed,
        load_text=_read,
        chunk_texts=library.splitter.split_text,
        resolve_path=_command().resolve_storage_path,
        documents_dir=str(library.dir),
        scope=SCOPE,
    )

    assert plan.rebuild_documents == 3
    assert plan.unchanged_documents == 3
    assert plan.embedded_texts == 3 * 5


def test_a_time_budget_stops_between_documents_and_never_inside_one(tmp_path):
    library = _content_drift(tmp_path)
    # 时钟按调用次序走：起始 0.0，第 1 篇前 0.5，第 2 篇前 1.5，第 3 篇前 3.0 -> 预算已耗尽。
    ticks = iter([0.0, 0.5, 1.5, 3.0, 3.0, 3.0, 3.0])

    report = library.rebuild(incremental=True, time_budget_seconds=2.5, clock=lambda: next(ticks))

    assert report["stopped_at"] == "time_budget_seconds=2.5"
    assert report["attempted"] == 2
    assert report["remaining"] == 4
    # 停在边界上：被点名的两篇都完整发布了，没点名的四篇一行业务数据都没动。
    assert library.calls == [("add", name + ".txt") for name in MARKERS[:2]]
    for name in MARKERS[2:]:
        assert len(library.records[name + ".txt"]) == 3, "未轮到的篇还是入库时那三块"
        assert library.registry.current(document_index_id(name + ".txt")).chunk_count == 3


# ==================== profile 漂移：强制 retire 那一腿 ====================


def test_a_forced_retire_pays_one_extra_embedding_per_document(tmp_path):
    library = _profile_drift(tmp_path)

    report = library.rebuild(scope=SWAPPED, incremental=True, stop_after=2)

    assert report["rebuilt"] == 2
    assert report["remaining"] == 4
    # 每篇：1 次 pre-flight + 3 次重嵌（这三行的篇目就是 3 块）；整轮另有 1 次探针。
    assert report["embedded_texts"] == 1 + 2 * 4
    assert library.calls == [
        ("delete", "alpha.txt"), ("add", "alpha.txt"),
        ("delete", "bravo.txt"), ("add", "bravo.txt"),
    ]


def test_an_embedder_that_dies_halfway_leaves_every_document_whole(tmp_path):
    """判据③ 的反面教材：先删后嵌时，embedding 一死就等于把那一删的文档清出库。

    强制 retire 前 pre-flight 先用一次"这一篇自己的"文本；它一死，本篇一个字都不动。
    """
    library = _profile_drift(tmp_path)
    # 探针 1 次 + 前两篇各 (1 pre-flight + 3 重嵌) = 9 次；charlie 的 pre-flight 是第 10 次。
    library.embedding.poison_at = 9

    report = library.rebuild(scope=SWAPPED, incremental=True)

    assert report["rebuilt"] == 2
    assert report["aborted"].startswith("charlie.txt: embed_failed_before_delete")
    assert len(library.records["charlie.txt"]) == 3, "被中止那一篇的旧向量还在原位"
    assert len(library.records["delta.txt"]) == 3
    assert library.registry.current(document_index_id("charlie.txt")).chunk_count == 3
    assert ("delete", "charlie.txt") not in library.calls
    # charlie 被点过名但没做成，所以它和后面三篇一起留在 remaining 里。
    assert report["attempted"] == 3
    assert report["remaining"] == 3, "剩下的还得跑，但不会带着空文档跑完"


def test_the_order_this_command_replaced_would_have_emptied_that_document(tmp_path):
    """对照组：先删后嵌 —— 看板已经栽过一次的那个形态，这里把它钉成可复算的事实。"""
    library = _profile_drift(tmp_path)
    library.embedding.poison_at = 0

    with pytest.raises(RuntimeError):
        library.delete_document("alpha.txt")
        library.add_document("alpha.txt", _read(library.dir / "alpha.txt"))

    assert library.records.get("alpha.txt") is None



# ==================== ③ 不闪断：重建期间读检索始终看到自洽的一套 ====================

AXES = ("alpha", "bravo", "charlie", "delta")
SPARE = len(AXES)
QUERY_PREFIX = "查询："
#: 改正文但保持长度与段数：块数不变，摘要必变。这样"库里有几条"是个常量，
#: 任何一次采样少给一条都是真的空洞，而不是被改出来的差异。
SWAP_WORDS = ("财务口径说明", "预算口径说明")


def _axis_of(text: str) -> int:
    for axis, marker in enumerate(AXES):
        if marker in text:
            return axis
    return SPARE


def _one_hot(axis: int) -> list:
    vector = [0.0] * WIDTH
    vector[axis] = 1.0
    return vector


def _long_body(marker: str, segments: int) -> str:
    """每段约 90 字，段数直接决定真 splitter 会切出几块。"""
    return "\n\n".join(
        marker + " 第 " + str(step) + " 节：" + (SWAP_WORDS[0] * 30) for step in range(segments)
    )


def _edited(body: str) -> str:
    return body.replace(SWAP_WORDS[0], SWAP_WORDS[1])


class _Live:
    """真 chromadb + 真 splitter + 真写库闸门，只把出网那一点换成按文档定轴的桩。

    桩里挂了一个 sampler：每一次 embedding 正在进行的那一刻，它就地发一次查询。旧写序
    "先删后慢慢重嵌"恰好在这里露馅 —— 那一刻这一篇的向量已经被删掉了；新写序必须还给得出
    完整的一套。查询要满全库（k = 库里总块数），所以"少一条"就是真的少一条。
    采样点挑在能被确定性命中的位置，而不是开线程赌 sqlite 的锁时序。
    """

    def __init__(self, tmp_path, monkeypatch):
        self.embedded: list[str] = []
        self.samples: list = []
        self.sampler = None
        self._sampling = False
        live = self

        def fake_call_api(_self, text):
            text = str(text)
            if not text.startswith(QUERY_PREFIX):
                live.embedded.append(text)
                # 只有落在某一篇文档轴上的文本才值得采样：整轮探针那句不属于任何一篇。
                if live.sampler is not None and not live._sampling and _axis_of(text) < len(AXES):
                    live._sampling = True
                    try:
                        live.samples.append(live.sampler(text))
                    finally:
                        live._sampling = False
            return _one_hot(_axis_of(text))

        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api", fake_call_api)
        monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
        monkeypatch.setenv("EMBEDDING_DIMENSION", str(WIDTH))
        self.dir = tmp_path / "docs"
        self.dir.mkdir(parents=True)
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.registry = IndexRegistry(tmp_path / "index-versions.json", scope=SCOPE)
        self.publisher = IndexPublisher(self.registry, store=None)
        self.chunker = self.retriever.splitter.split_text
        self.published: list = []
        self._watch_pointer()

    def _watch_pointer(self):
        """指针每动一次就采一次样：切换点之后的那一读必须是完整的新的一套。"""
        original = self.registry.publish
        live = self

        def spy(index_version_id):
            version = original(index_version_id)
            live.published.append(version.index_id)
            if live.sampler is not None:
                live._sampling = True
                try:
                    live.samples.append(live.sampler(version.index_id))
                finally:
                    live._sampling = False
            return version

        self.registry.publish = spy

    # ---- 语料 ----

    def chunks_of(self, filename: str) -> list:
        return list(self.chunker(_read(self.dir / filename)))

    def write(self, filename: str, segments: int, *, edited: bool = False) -> None:
        body = _long_body(filename.split(".")[0], segments)
        (self.dir / filename).write_text(_edited(body) if edited else body, encoding="utf-8")

    def upload(self, filename: str, segments: int) -> int:
        self.write(filename, segments)
        added, message = self.retriever.add_document(
            filename, _read(self.dir / filename), 1, "finance"
        )
        assert added is True, message
        outcome = self.publisher.apply(
            DocumentIndexPublication(
                filename=filename, version=1, chunks=tuple(self.chunks_of(filename))
            )
        )
        assert outcome is not None
        return len(self.chunks_of(filename))

    def rows(self):
        return [
            {
                "filename": name,
                "version": 1,
                "storage_path": str(self.dir / name),
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
            for name in sorted(path.name for path in self.dir.glob("*.txt"))
        ]

    def stored_chunks(self) -> int:
        return len(self.retriever.collection.get()["ids"])

    def hits(self, marker: str, k: int):
        return self.retriever.search(QUERY_PREFIX + marker, k=k)

    def rebuild(self, **kwargs):
        kwargs.setdefault("scope", SCOPE)
        kwargs.setdefault("documents_dir", str(self.dir))
        return _command().run_rebuild(
            targets=self.rows(),
            retriever=self.retriever,
            publisher=self.publisher,
            load_text=_read,
            apply=True,
            manual=True,
            **kwargs,
        )


@pytest.fixture
def live(tmp_path, monkeypatch):
    brain = _Live(tmp_path, monkeypatch)
    for name, segments in (
        ("alpha.txt", 5),
        ("bravo.txt", 3),
        ("charlie.txt", 4),
        ("delta.txt", 6),
    ):
        brain.upload(name, segments)
    brain.embedded.clear()
    brain.samples.clear()
    brain.published.clear()
    return brain


def _keyed(hits):
    return frozenset((str(hit["source"]), str(hit["content"])) for hit in hits)


def test_a_full_library_query_is_the_ruler_that_cannot_be_faked(live):
    """基线：一次"要满全库"的查询拿回多少条，就是后面每次采样必须拿回的条数。"""
    total = live.stored_chunks()

    assert total == sum(len(live.chunks_of(name)) for name in (
        "alpha.txt", "bravo.txt", "charlie.txt", "delta.txt"))
    assert total == len(live.chunks_of("alpha.txt")) + len(live.chunks_of("bravo.txt")) + (
        len(live.chunks_of("charlie.txt")) + len(live.chunks_of("delta.txt"))
    )
    assert total >= 8, total
    assert len(live.hits("alpha", k=total)) == total
    assert len(live.hits("delta", k=total)) == total
    assert "alpha.txt" in {source for source, _content in _keyed(live.hits("alpha", k=total))}


def test_reads_during_a_rebuild_never_lose_a_single_chunk(live):
    """判据③ 的正身：重建全程每一次采样都拿回与重建前同样多的命中，且大于 0。

    旧写序在这里必红：改文之后先 delete 再慢慢 embed，采样点正落在"已删未写"中间，
    命中数立刻少掉那一整篇的块数。新写序把 embed 放在任何删除之前，采样点读到的还是旧的
    完整一套；切换（指针移动）之后的那一次采样读到的是新的完整一套。
    """
    before = live.stored_chunks()
    old_set = _keyed(live.hits("alpha", k=before))
    live.write("alpha.txt", 5, edited=True)
    assert _edited(_long_body("alpha", 5)) == _read(live.dir / "alpha.txt")
    assert live.stored_chunks() == before, "改文必须守恒，否则下面的条数断言没有意义"

    def sample(source):
        marker = AXES[_axis_of(source)]
        hits = live.hits(marker, k=before)
        return marker, len(hits), _keyed(hits)

    live.sampler = sample
    report = live.rebuild(incremental=True)
    live.sampler = None

    after_set = _keyed(live.hits("alpha", k=before))
    assert report["rebuilt"] == 1 and report["unchanged"] == 3
    expected_samples = len(live.chunks_of("alpha.txt")) + 1  # 每块一次 embed 采样，切换后再一次
    assert len(live.samples) >= expected_samples, (live.samples, expected_samples)
    assert {count for _marker, count, _keyed in live.samples} == {before}, live.samples
    assert min(count for _marker, count, _keyed in live.samples) > 0
    # 自洽：整套命中只能是旧的那一套或者新的那一套，绝不混排、绝不缺一块。
    for marker, _count, keyed in live.samples:
        if marker != "alpha":
            continue
        assert keyed in (old_set, after_set), keyed - old_set
    assert any(keyed == old_set for _m, _c, keyed in live.samples)
    assert any(keyed == after_set for _m, _c, keyed in live.samples)
    assert old_set != after_set
    counts = [count for _marker, count, _keyed in live.samples]
    print(
        "R50③ 重建 alpha 全程采样 " + str(len(live.samples)) + " 次：命中数 重建前=" + str(before)
        + " 采样 min=" + str(min(counts)) + " max=" + str(max(counts)) + "（必须恒等且 >0）"
    )


def test_the_write_order_this_command_replaced_does_make_a_document_vanish(live):
    """同一条采样管道下的对照组：先删后嵌，那一删就是一次货真价实的读空。"""
    before = live.stored_chunks()
    alpha_chunks = len(live.chunks_of("alpha.txt"))

    live.retriever.delete_document("alpha.txt")
    during = live.hits("alpha", k=before)

    assert live.stored_chunks() == before - alpha_chunks
    assert len(during) == before - alpha_chunks
    assert ("alpha.txt", _read(live.dir / "alpha.txt")) not in _keyed(during)
    print(
        "R50③ 对照（旧写序先删后嵌）：同一时刻命中 " + str(len(during)) + " 条，比重建前少 "
        + str(alpha_chunks) + " 条 —— 这一格空洞就是判据③ 要禁的那个忽有忽无"
    )


def test_no_sample_ever_sees_one_document_in_two_generations_at_once(live):
    """三篇连着重嵌：任何一次采样里，同一篇要么整套旧、要么整套新，不许新旧掺一半。

    这条是"忽有忽无"最直白的反命题：掺半套正是"旧块已删、新块只写了一半"的那个形态。
    """
    before = live.stored_chunks()
    #: 三篇要重嵌的（marker -> 段数），外加一篇不碰的 alpha 当参照。
    targets = {"bravo": 3, "charlie": 4, "delta": 6}

    def own(marker, hits):
        return frozenset(
            (source, content) for source, content in _keyed(hits) if source == marker + ".txt"
        )

    old_sets = {marker: own(marker, live.hits(marker, k=before)) for marker in targets}
    for marker, segments in targets.items():
        live.write(marker + ".txt", segments, edited=True)

    def sample(source):
        marker = AXES[_axis_of(source)]
        hits = live.hits(marker, k=before)
        return marker, len(hits), own(marker, hits)

    live.sampler = sample
    report = live.rebuild(incremental=True)
    live.sampler = None

    new_sets = {marker: own(marker, live.hits(marker, k=before)) for marker in targets}
    assert report["rebuilt"] == 3
    assert report["remaining"] == 0
    minimum = sum(len(live.chunks_of(marker + ".txt")) for marker in targets) + len(targets)
    assert len(live.samples) >= minimum, (len(live.samples), minimum)
    for marker, count, keyed in live.samples:
        assert count == before, (marker, count)
        if marker in targets:
            assert keyed in (old_sets[marker], new_sets[marker]), (
                marker, sorted(keyed - old_sets[marker]), sorted(keyed - new_sets[marker])
            )
    assert old_sets != new_sets, "改文没生效的话，上面那条断言就只是在自我确认"
    assert {keyed for marker, _c, keyed in live.samples if marker in targets} - {
        old_sets["bravo"], new_sets["bravo"], old_sets["charlie"], new_sets["charlie"],
        old_sets["delta"], new_sets["delta"],
    } == set()


def test_the_switch_is_one_pointer_move_per_rebuilt_document(live):
    """切的是注册表指针：一个文档一次，向量没写完之前它不许动。"""
    names = ("alpha.txt", "bravo.txt", "charlie.txt", "delta.txt")
    before = {name: live.registry.current(document_index_id(name)) for name in names}
    live.write("alpha.txt", 5, edited=True)
    live.write("charlie.txt", 4, edited=True)

    report = live.rebuild(incremental=True)

    assert report["rebuilt"] == 2
    assert live.published == [document_index_id("alpha.txt"), document_index_id("charlie.txt")]
    print(
        "R50③ 切换点：2 篇重嵌 -> 指针移动 " + str(len(live.published)) + " 次，逐篇一次；"
        "未点名的两篇 current 版本 id 一字未动"
    )
    for name in ("bravo.txt", "delta.txt"):
        assert (
            live.registry.current(document_index_id(name)).index_version_id
            == before[name].index_version_id
        ), "没点名的文档，指针一格都不许动"
    queryable = live.registry.queryable_version_ids(embedding_model=MODEL, dimension=WIDTH)
    for name in ("alpha.txt", "charlie.txt"):
        assert live.registry.current(document_index_id(name)).index_version_id in queryable


def test_a_publish_that_fails_leaves_readers_on_the_old_version(live, monkeypatch):
    """先建新、后切换的另一半：切换失败就退回旧指针，而且照样出一份能看的报告。"""
    old = live.registry.current(document_index_id("alpha.txt"))
    live.write("alpha.txt", 5, edited=True)

    def explode(index_version_id):
        raise RuntimeError("the metadata file went away mid-publish")

    monkeypatch.setattr(live.registry, "publish", explode)

    report = live.rebuild(incremental=True)

    assert report["rebuilt"] == 0
    assert report["failed"] == 1
    assert report["aborted"].startswith("alpha.txt: publish_failed (stage=publish)")
    current = live.registry.current(document_index_id("alpha.txt"))
    assert current.index_version_id == old.index_version_id
    assert current.status == "published"
    assert len(live.registry.history(document_index_id("alpha.txt"))) == 1, "半成品不许留在注册表里"
    assert (
        live.registry.queryable_version(
            document_index_id("alpha.txt"), embedding_model=MODEL, dimension=WIDTH
        ).index_version_id
        == old.index_version_id
    )



def test_the_store_window_between_retire_and_rewrite_holds_no_model_call(live):
    """判据③ 还剩多大的口子：把它量成数字，而不是含糊过去。

    同名重嵌绕不开 chroma 的 id 复用（chunk id 是文件名的纯函数，两代向量无法共存），
    所以"删旧"与"写新"之间确实有一段路。这一条钉的是那段路的成分：R21 的先验后删把所有
    embedding 都推到删除之前，注册表指针又在这段之后才动 —— 窗口里只剩本地写库调用，宽度
    由 chroma 决定，不由模型决定。判据③ 真正禁的是往这段里掺模型往返的旧写序（删完再慢慢
    嵌，一嵌就是 N 次往返），那才是分钟级的忽有忽无。
    """
    trace = []

    embedder = live.retriever.embedding
    original_embed = embedder.embed_documents

    def watched_embed(texts):
        texts = list(texts)
        trace.append(("embed", len(texts)))
        return original_embed(texts)

    embedder.embed_documents = watched_embed

    collection = live.retriever.collection
    for name in ("add", "delete"):
        def watched(*args, _name=name, _original=getattr(collection, name), **kwargs):
            ids = kwargs.get("ids") or (args[0] if args else [])
            trace.append(("store_" + _name, len(list(ids))))
            return _original(*args, **kwargs)

        setattr(collection, name, watched)

    original_publish = live.registry.publish

    def watched_publish(index_version_id):
        trace.append(("publish", 1))
        return original_publish(index_version_id)

    live.registry.publish = watched_publish

    live.write("alpha.txt", 5, edited=True)
    report = live.rebuild(incremental=True)

    assert report["rebuilt"] == 1, report
    kinds = [kind for kind, _payload in trace]
    assert "store_delete" in kinds and "store_add" in kinds and "publish" in kinds, trace
    first_delete = kinds.index("store_delete")
    assert "embed" in kinds[:first_delete], kinds
    last_add = len(kinds) - 1 - kinds[::-1].index("store_add")
    window = kinds[first_delete:last_add + 1]
    assert "embed" not in window, trace
    assert "publish" not in window, trace
    assert kinds.index("publish") > last_add, "指针必须在这段写完之后才动"
    assert window.count("store_delete") == 1 and window.count("store_add") == 1, window
    print(
        "R50③ 残留窗口：删旧到写新之间 store 调用 " + str(len(window)) + " 次、模型往返 0 次、"
        "指针移动 0 次；整轮 trace " + str(len(kinds)) + " 个事件 = 重嵌在前、删旧写新居中、publish 在后"
    )


# ==================== 判据⑤：这一单不建表、不发 SQL ====================


def test_planning_and_resuming_need_no_new_table_and_issue_no_sql():
    """增量计划与续跑只读 index_versions 已有的摘要：没有新表、新列、迁移文件。"""
    indexing_source = Path(str(indexing_module.__file__)).read_text(encoding="utf-8")
    planner_section = indexing_source.split("R50: incremental planning", 1)[1]
    cli_source = Path(str(_command().__file__)).read_text(encoding="utf-8")
    cli_helpers = cli_source.split("def main(", 1)[0]
    parameters = tuple(inspect.signature(plan_index_refresh).parameters)

    for statement in (
        "CREATE TABLE",
        "ALTER TABLE",
        "DROP TABLE",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "SELECT ",
    ):
        assert statement not in planner_section, statement
        assert statement not in cli_helpers, statement
    assert "connection" not in parameters
    assert "store" not in parameters
    assert "database_url" not in parameters


# ==================== 命令行：预算参数的判断顺序 ====================


def test_a_budget_needs_apply_before_anything_is_opened(capsys, monkeypatch):
    """预算只在 --apply 下有意义；空跑带预算是一次打错，不是"先看看"。

    这条同时证明判断发生在注册表、目录与向量库被打开之前：main() 在这几行之后才会去读
    索引元数据与文档目录，而这里连 --apply 都没有，所以任何一处 I/O 都不该发生。
    """
    module = _command()

    assert module.main(["--max-documents", "3"]) == module.EXIT_USAGE
    assert "--apply" in capsys.readouterr().err
    assert module.main(["--time-budget-seconds", "60"]) == module.EXIT_USAGE
    assert "--apply" in capsys.readouterr().err


def test_a_negative_budget_is_refused_as_a_broken_invocation(capsys):
    module = _command()

    assert module.main(["--max-documents", "-1"]) == module.EXIT_USAGE
    assert "must not be negative" in capsys.readouterr().err
    assert module.main(["--time-budget-seconds", "-0.5"]) == module.EXIT_USAGE
    assert "must not be negative" in capsys.readouterr().err


def test_the_new_flags_reach_the_parser():
    """三个新开关都在 parser 上，不然是文档里的一句空话。"""
    parser = _command()._parser()
    flags = {action.option_strings[0] for action in parser._actions}

    for flag in ("--incremental", "--max-documents", "--time-budget-seconds"):
        assert flag in flags, sorted(flags)
    assert parser.parse_args(["--apply", "--confirm-scope", "m/768", "--incremental",
                             "--max-documents", "2", "--time-budget-seconds", "30"]
                             ).max_documents == 2
