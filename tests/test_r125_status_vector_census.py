"""跟进单 §61 / R125: the vector census has to be reachable from ``--status``.

The counting is not new: ``vector_census`` has answered "how many of this document's stored
vectors are all zeros, and how many are not the declared width" since R22. What was missing is
a connection to the command an operator is actually told to run. The pgvector plan's §8.6 sent
the owner to ``rebuild_index.py --status --json`` for the U3 gate, where those two fields do
not exist: the JSON came back without them, and the printed report said ``zero_vectors_before=0``
because an absent key defaults to zero. A gate nobody had looked at printed like a gate that
had passed.

So these tests are the wiring, and the first one is the proof that the wiring is load bearing:
it runs ``main(["--status", "--json"])`` and reads the counters off stdout, so no field can
come back from a call site that never asked the vector store.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import re

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "handoff" / "2026-09-17-pgvector-adoption-plan.md"

MODEL = "nomic-embed-text"
DIMENSION = 768
OTHER_DIMENSION = 384

#: The status fields that existed before R125. The runbook, the board and the image
#: provenance check read this shape, so a census may only ever be appended to it.
BEFORE_R125 = (
    "scope",
    "drifted",
    "codes",
    "unknown_scope_versions",
    "indexes",
    "documents",
    "documents_needing_rebuild",
    "stale_documents",
)


def _command():
    return importlib.import_module("scripts.rebuild_index")


def _vector(width, *, value=0.25):
    return [float(value)] * int(width)


def _zero(width=DIMENSION):
    return _vector(width, value=0.0)


def _rows(*names, count=1, width=DIMENSION):
    return [(name, _vector(width)) for name in names for _ in range(count)]


class _Collection:
    """A vector collection that remembers every call it was asked to make.

    It answers ``get`` the way Chroma does -- a page of ids, embeddings and metadatas, with
    ``offset`` and ``limit`` honoured -- and it records write attempts by name, so "the census
    only read" is a fact a test can check rather than a promise in a docstring.
    """

    def __init__(self, rows=(), *, paging=True, offset_is_dead=False, failing=None):
        self.rows = list(rows)
        self.calls = []
        self.gets = []
        self.paging = paging
        self.offset_is_dead = offset_is_dead
        self.failing = failing

    def get(self, where=None, include=None, limit=None, offset=None):
        self.calls.append("get")
        self.gets.append((offset, limit))
        if self.failing is not None:
            raise self.failing
        if not self.paging and (limit is not None or offset is not None):
            raise TypeError("get() got an unexpected keyword argument limit")
        rows = self.rows
        if where:
            wanted = where.get("filename")
            rows = [row for row in rows if row[0] == wanted]
        start = 0 if self.offset_is_dead else int(offset or 0)
        taken = rows[start:] if limit is None else rows[start:start + int(limit)]
        asked = list(include or [])
        return {
            "ids": [f"row-{start + position}" for position in range(len(taken))],
            "embeddings": [vector for _name, vector in taken] if "embeddings" in asked else None,
            "metadatas": [{"filename": name} for name, _vector in taken] if "metadatas" in asked else [],
        }

    def count(self):
        self.calls.append("count")
        return len(self.rows)

    def add(self, **kwargs):
        self.calls.append("add")

    def upsert(self, **kwargs):
        self.calls.append("upsert")

    def delete(self, **kwargs):
        self.calls.append("delete")

    def modify(self, **kwargs):
        self.calls.append("modify")


class _Store:
    """The shape of DocumentRetriever a census reads: a collection, and where it came from."""

    def __init__(self, collection, source="fake/enterprise_docs"):
        self.collection = collection
        self.source = source


def _census(collection, *, dimension=DIMENSION, page_size=200, catalog_filenames=()):
    module = _command()
    return module.library_vector_census(
        _Store(collection), dimension, page_size=page_size, catalog_filenames=catalog_filenames
    )


def _status(tmp_path, *, targets=(), census=None):
    from app.rag.indexing import IndexRegistry

    module = _command()
    return module.status_report(
        registry=IndexRegistry(tmp_path / "indexes.json", scope=_scope()),
        scope=_scope(),
        targets=list(targets),
        census=census,
    )


def _scope(model=MODEL, dimension=DIMENSION):
    from app.rag.indexing import EmbeddingScope

    return EmbeddingScope(model, dimension)


def _section_8_6():
    text = RUNBOOK.read_bytes().decode("utf-8").replace("\r\n", "\n")
    match = re.search(r"^### 8\.6 .*?(?=^### )", text, re.S | re.M)
    assert match, "pgvector 方案里没有 §8.6 这一节，R125 判据③无处可查"
    return match.group(0)


def _catalog(monkeypatch, *filenames):
    import app.documents.catalog as catalog

    monkeypatch.setattr(
        catalog,
        "current_documents",
        lambda: [{"filename": name, "version": 1} for name in filenames],
    )


# ------------------------------------------------- the wiring itself (判据 ① / §61 a)
def test_the_status_command_itself_reports_the_two_census_counters(tmp_path, monkeypatch, capsys):
    """``--status --json`` answers U3, and answers it out of the store rather than a default.

    This is the test that makes the wiring load bearing. It goes through ``main()`` with no
    rebuild and no publisher, so the only way the counters can come back is the status path
    having asked the vector store; take that call out and the first assert is the red one.
    """
    module = _command()
    store = _Store(
        _Collection(
            [
                ("clean.txt", _vector(DIMENSION)),
                ("all-zero.txt", _zero(DIMENSION)),
                ("old-model.txt", _vector(OTHER_DIMENSION)),
            ]
        )
    )
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("EMBEDDING_DIMENSION", str(DIMENSION))
    monkeypatch.setattr(module, "open_census_store", lambda *args, **kwargs: (store, ""))
    _catalog(monkeypatch, "clean.txt", "all-zero.txt", "never-indexed.txt")
    detail = tmp_path / "census-detail.json"

    code = module.main(
        [
            "--status", "--json",
            "--metadata-path", str(tmp_path / "indexes.json"),
            "--census-report", str(detail),
        ]
    )

    assert code == module.EXIT_OK
    report = json.loads(capsys.readouterr().out.strip())
    assert report.get("zero_vectors_before") == 1, (
        "R125 判据①：--status --json 必须交出 zero_vectors_before（§8.6 让业主抄的就是它）。"
        "摘掉 main() 里 census=... 那一行，这个字段就退回 " + repr(report.get("zero_vectors_before"))
        + "，业主照手册跑 U3 会取到空并误判成没有全零向量。"
    )
    assert report.get("cross_dimension_vectors_before") == 1, (
        "R125 判据①：--status --json 必须交出 cross_dimension_vectors_before，实拿 "
        + repr(report.get("cross_dimension_vectors_before"))
    )
    assert report.get("census_measurable") is True
    assert report.get("zero_vector_documents") == [
        {"filename": "all-zero.txt", "zero_vectors": 1, "vectors": 1}
    ]
    assert [row["filename"] for row in report["cross_dimension_vector_documents"]] == ["old-model.txt"]
    assert report["cross_dimension_vector_documents"][0]["widths"] == [OTHER_DIMENSION]
    # A catalog document the store holds nothing for is named, not silently read as fine.
    assert [row["filename"] for row in report["unmeasurable_documents"]] == ["never-indexed.txt"]
    # Three are stored -- one of them a filename the catalog no longer lists, which a
    # document-by-document census would never have looked at.
    assert report["census_documents"] == 3 and report["documents"] == 3
    assert Path(report["census_report_path"]) == detail
    dumped = json.loads(detail.read_text(encoding="utf-8"))
    assert dumped["zero_vector_documents"][0]["filename"] == "all-zero.txt"
    assert set(store.collection.calls) <= {"get", "count"}, store.collection.calls


def test_the_status_command_never_asks_the_store_to_write(tmp_path, monkeypatch, capsys):
    """判据 ① / §61 a: the status path may read, and reading is all it may do.

    The fake collection records every method name it is called with, so this catches a write
    that was reached by accident -- a shared helper, a later refactor -- not only one that
    someone typed on purpose.
    """
    module = _command()
    collection = _Collection([("a.txt", _zero(DIMENSION)), ("b.txt", _vector(DIMENSION))])
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("EMBEDDING_DIMENSION", str(DIMENSION))
    monkeypatch.setattr(module, "open_census_store", lambda *args, **kwargs: (_Store(collection), ""))
    _catalog(monkeypatch, "a.txt")

    assert module.main(["--status", "--metadata-path", str(tmp_path / "indexes.json")]) == module.EXIT_OK
    printed = capsys.readouterr().out
    writes = [name for name in collection.calls if name not in {"get", "count"}]
    assert writes == [], "R125 判据①要求 --status 只读，实发到向量库的写是 " + repr(writes)
    assert "zero_vectors_before=1" in printed
    assert "census=measurable" in printed


# ------------------------------------------------------------------ counting rules (§61 b)
def test_each_kind_of_unusable_vector_lands_in_its_own_counter():
    """§61 d①: one exact zero, one cross-dimension, one clean -- three different answers."""
    census = _census(
        _Collection(
            [
                ("clean.txt", _vector(DIMENSION)),
                ("clean.txt", _vector(DIMENSION)),
                ("all-zero.txt", _zero(DIMENSION)),
                ("old-model.txt", _vector(OTHER_DIMENSION)),
            ]
        )
    )
    assert census["measurable"] is True and census["reason"] == ""
    assert census["zero_vectors"] == 1
    assert census["cross_dimension_vectors"] == 1
    assert census["vectors_read"] == 4 and census["documents"] == 3
    # A vector can be both kinds at once: R21's zero placeholder is also the wrong width when
    # the model that made it is not the declared one, and both gates have to see it.
    both = _census(_Collection([("a.txt", _zero(OTHER_DIMENSION))]))
    assert both["zero_vectors"] == 1 and both["cross_dimension_vectors"] == 1


def test_a_vector_that_is_not_a_vector_is_counted_as_unreadable_not_as_clean():
    census = _census(_Collection([("a.txt", None)]))
    assert census["measurable"] is True
    assert census["non_sequence_vectors"] == 1
    assert census["documents"] == 0
    assert census["vectors_read"] == 1


def test_a_store_that_cannot_be_read_leaves_both_counters_null_instead_of_zero(tmp_path):
    """§61 b / d②: could-not-look may not arrive in the same shape as looked-and-clear.

    The counters are null here on purpose. They used to be an absent key, which printed as
    ``zero_vectors_before=0``; the day anyone prints ``census_measurable`` and the counter as
    one line, the last assertion is the one that goes red.
    """
    module = _command()
    census = _census(_Collection([("a.txt", _zero(DIMENSION))], failing=RuntimeError("locked")))
    assert census["measurable"] is False
    assert census["zero_vectors"] is None and census["cross_dimension_vectors"] is None
    assert "RuntimeError" in census["reason"]

    report = _status(tmp_path, census=census, targets=[{"filename": "a.txt"}])
    assert report["census_measurable"] is False
    assert report["zero_vectors_before"] is None
    lines = "\n".join(module.report_lines(report))
    assert "zero_vectors_before=unmeasurable" in lines
    assert "zero_vectors_before=0" not in lines, (
        "R125 判据①的反证：没普查过的 --status 又印出 0，业主会把看不了读成没有全零向量。"
    )


def test_a_document_the_store_holds_nothing_for_is_named_not_assumed_clean(tmp_path):
    """§61 b: an absent document is nothing-to-look-at, and it has to be listed that way."""
    census = _census(
        _Collection([("here.txt", _zero(DIMENSION))]),
        catalog_filenames=["here.txt", "gone.txt", "also-gone.txt"],
    )
    report = _status(tmp_path, census=census, targets=[{"filename": "here.txt"}])
    assert report["zero_vectors_before"] == 1
    assert report["unmeasurable_documents_total"] == 2
    assert [row["filename"] for row in report["unmeasurable_documents"]] == ["also-gone.txt", "gone.txt"]
    assert all("nothing to census" in row["reason"] for row in report["unmeasurable_documents"])


# ------------------------------------------------------------------ the read window (§61 c)
def test_the_census_walks_the_store_one_window_at_a_time():
    """§61 c: a hundred documents is not a licence to hold the whole library's embeddings."""
    rows = [("doc-%03d.txt" % (index // 5), _vector(DIMENSION)) for index in range(500)]
    collection = _Collection(rows)
    census = _census(collection, page_size=200)
    assert census["measurable"] is True
    assert census["vectors_read"] == 500 and census["pages_read"] == 3
    assert [limit for _offset, limit in collection.gets] == [200, 200, 200]
    assert [offset for offset, _limit in collection.gets] == [0, 200, 400]


def test_a_store_that_ignores_the_window_is_unmeasurable_rather_than_double_counted():
    collection = _Collection(_rows("a.txt", "b.txt", count=3), offset_is_dead=True)
    census = _census(collection, page_size=2)
    assert census["measurable"] is False
    assert "window" in census["reason"]
    assert census["zero_vectors"] is None and census["cross_dimension_vectors"] is None


def test_a_store_that_cannot_page_says_so_instead_of_loading_the_library():
    census = _census(_Collection(_rows("a.txt"), paging=False))
    assert census["measurable"] is False
    assert "page window" in census["reason"]


def test_a_scan_that_did_not_cover_the_stores_own_count_is_unmeasurable():
    """A read that stopped early must not be reported as a clean library."""
    module = _command()
    collection = _Collection(_rows("a.txt", count=4))
    original = collection.get

    def truncated(where=None, include=None, limit=None, offset=None):
        page = original(where=where, include=include, limit=limit, offset=offset)
        if offset:
            page["ids"] = []
            page["embeddings"] = []
        return page

    collection.get = truncated
    census = module.library_vector_census(_Store(collection), DIMENSION, page_size=2)
    assert census["store_vectors"] == 4 and census["vectors_read"] == 2
    assert census["measurable"] is False
    assert "the store counts 4" in census["reason"]
    assert census["zero_vectors"] is None


def test_the_census_handle_exposes_no_way_to_write():
    """The read-only promise is held by the handle, not by the caller's discipline."""
    module = _command()
    inner = _Collection([("a.txt", _vector(DIMENSION))])
    store = module.CensusStore(inner)
    for name in ("add", "upsert", "delete", "modify"):
        with pytest.raises(AttributeError):
            getattr(store.collection, name)(ids=["x"], embeddings=[_vector(DIMENSION)])
    assert store.collection.get(limit=1, offset=0)["ids"] == ["row-0"]
    assert set(inner.calls) == {"get"}, inner.calls


def test_the_census_reads_a_real_chroma_store_with_the_windows_it_asks_for(tmp_path):
    """A hand-written fake cannot catch a keyword real Chroma does not accept.

    The window read is written against chromadb's own ``get``, so it has to be run against
    chromadb: the store here is real, built in a temporary directory, and fed explicit vectors
    so no embedder and no model is involved. Same dimension, same three answers as the fake.
    """
    chromadb = pytest.importorskip("chromadb")
    from chromadb.config import Settings

    module = _command()
    directory = tmp_path / "chroma_db"
    client = chromadb.PersistentClient(path=str(directory), settings=Settings(anonymized_telemetry=False))
    collection = client.create_collection("enterprise_docs")
    for index in range(6):
        collection.add(
            ids=[f"v{index}"],
            documents=[f"chunk {index}"],
            metadatas=[{"filename": "doc-%d.txt" % (index // 2)}],
            embeddings=[[0.0] * 4 if index == 0 else [0.1] * 4],
        )

    store, reason = module.open_census_store(str(directory), "enterprise_docs")
    assert reason == "" and store is not None
    census = module.library_vector_census(
        store, 4, page_size=2, catalog_filenames=["doc-0.txt", "doc-1.txt", "gone.txt"]
    )

    assert census["measurable"] is True, census["reason"]
    assert census["store_vectors"] == 6 and census["vectors_read"] == 6
    assert census["zero_vectors"] == 1 and census["cross_dimension_vectors"] == 0
    # Real Chroma answers exactly `page_size` rows and only signals the end with one empty
    # page, so 6 vectors over a window of 2 is three full reads plus the read that says stop.
    assert census["pages_read"] == 4
    assert [row["filename"] for row in census["unmeasurable_documents"]] == ["gone.txt"]
    assert [row["filename"] for row in census["zero_vector_documents"]] == ["doc-0.txt"]


# ------------------------------------------------- the old shape may not move (判据 ④)
def test_the_status_report_keeps_the_pre_r125_field_names_and_order(tmp_path):
    module = _command()
    report = _status(
        tmp_path,
        targets=[{"filename": "a.txt", "version": 1}, {"filename": "b.txt", "version": 1}],
    )
    assert tuple(list(report)[: len(BEFORE_R125)]) == BEFORE_R125
    assert report["documents"] == 2
    assert report["documents_needing_rebuild"] == 2
    assert report["stale_documents"] == ["a.txt", "b.txt"]
    assert report["indexes"] == 0 and report["drifted"] is False
    added = set(report) - set(BEFORE_R125)
    assert added and added.isdisjoint(BEFORE_R125)
    # With no census at all the new fields say they did not measure, instead of saying zero.
    assert report["census_measurable"] is False
    assert report["zero_vectors_before"] is None
    assert report["cross_dimension_vectors_before"] is None
    assert "no vector store was opened" in report["census_reason"]


def test_a_rebuild_report_prints_the_lines_it_always_printed():
    """The census lines belong to --status; a rebuild report must not grow them."""
    module = _command()
    lines = module.report_lines(
        {
            "scope": f"{MODEL}/{DIMENSION}",
            "cross_dimension_vectors_before": 0,
            "cross_dimension_vectors_after": 0,
            "zero_vectors_before": 0,
            "codes": [],
        }
    )
    assert "cross_dimension_vectors before=0 after=0" in lines
    assert "zero_vectors_before=0" in lines
    assert not [line for line in lines if line.startswith("census")]


# ------------------------------------------------ §8.6 matches what really runs (判据 ③)
def test_the_plan_section_8_6_names_only_what_the_status_command_prints(tmp_path):
    """The defect was a runbook pointing at fields that did not exist; keep the two in step.

    Both directions are pinned: every field §8.6 tells an operator to read has to be in the
    real report, and §8.6 has to describe the census that produces it -- the read window, the
    measurable flag, and where the full lists land. Put R120's paragraph back and the missing
    half of that list turns this red.
    """
    module = _command()
    census = _census(_Collection([("a.txt", _zero(DIMENSION))]), catalog_filenames=["a.txt"])
    report = _status(tmp_path, census=census)
    section = _section_8_6()
    fields = (
        "zero_vectors_before",
        "cross_dimension_vectors_before",
        "census_measurable",
        "census_reason",
        "census_report_path",
    )
    missing_from_doc = [name for name in fields if name not in section]
    assert not missing_from_doc, "§8.6 少了业主照着跑要用到的东西：" + repr(missing_from_doc)
    missing_from_report = [name for name in fields if name not in report]
    assert not missing_from_report, (
        "§8.6 让业主读的字段 --status --json 并没有交出：" + repr(missing_from_report)
    )
    for handle in ("--census-page-size", "library_vector_census()"):
        assert handle in section, "§8.6 没有交代 " + handle
    for name in re.findall(r"`([a-z_]+)\(\)`", section):
        assert hasattr(module, name), "§8.6 点名的 " + name + "() 在 scripts/rebuild_index.py 里不存在"
    assert "176-210" not in section, "§8.6 还钉着一个行号区间，R125 之后它已经不指 vector_census 了"
