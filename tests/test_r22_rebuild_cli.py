"""R22 criterion 3 and 4: the rebuild entry point, and what it must never do on its own.

The command exists because changing the embedder left no way to recompute a single stored
vector. These tests pin the parts that make it safe to hand to an operator: it refuses to run
at all unless a person invoked it, it refuses to delete anything before it has proved the new
embedder really works, it publishes a version bound to the profile it just wrote, and it keeps
the version it replaced.
"""
from __future__ import annotations

import json
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

MODEL = "nomic-embed-text"
NEW_MODEL = "bge-m3"
OLD_DIM = 384
NEW_DIM = 768


def _command():
    return importlib.import_module("scripts.rebuild_index")


def _scope(model, dimension):
    from app.rag.indexing import EmbeddingScope

    return EmbeddingScope(model, dimension)


def _registry(tmp_path, *, model=NEW_MODEL, dimension=NEW_DIM):
    from app.rag.indexing import IndexRegistry

    return IndexRegistry(tmp_path / "indexes.json", scope=_scope(model, dimension))


class _Embeddings:
    """An embedder that either answers with the declared width, or fails in a named way."""

    def __init__(self, width, *, zero=False, broken=False):
        self.width = width
        self.zero = zero
        self.broken = broken
        self.queries = 0

    def embed_query(self, text):
        self.queries += 1
        if self.broken:
            raise RuntimeError("ollama is not reachable")
        if self.zero:
            return [0.0] * self.width
        return [0.5] * self.width

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class _Collection:
    def __init__(self, store):
        self._store = store

    def get(self, where=None, include=None):
        filename = (where or {}).get("filename")
        names = [filename] if filename else list(self._store.records)
        ids, documents, metadatas, vectors = [], [], [], []
        for name in names:
            for ordinal, (content, vector) in enumerate(self._store.records.get(name, ())):
                ids.append(f"{name}_{ordinal}")
                documents.append(content)
                metadatas.append({"filename": name, "chunk_index": ordinal})
                vectors.append(vector)
        result = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if include and "embeddings" in list(include):
            result["embeddings"] = vectors
        return result


class _VectorStore:
    """The pieces of DocumentRetriever the rebuild command actually touches."""

    def __init__(self, embeddings):
        self.embedding = embeddings
        self.records = {}
        self.calls = []

    @property
    def collection(self):
        return _Collection(self)

    def seed(self, filename, contents, vector):
        self.records[filename] = [(content, list(vector)) for content in contents]

    def document_chunks(self, filename):
        return [
            {
                "vector_id": f"{filename}_{ordinal}",
                "content": content,
                "chunk_index": ordinal,
                "classification": 1,
                "department": "finance",
                "hash": "hash-of-stored-content",
            }
            for ordinal, (content, _vector) in enumerate(self.records.get(filename, ()))
        ]

    def delete_document(self, filename):
        self.calls.append(("delete", filename))
        self.records.pop(filename, None)

    def add_document(self, filename, content, classification=1, department=None):
        self.calls.append(("add", filename))
        chunks = [line for line in str(content).splitlines() if line.strip()]
        vectors = self.embedding.embed_documents(chunks)
        self.records[filename] = list(zip(chunks, vectors))
        return True, f"added {len(chunks)} chunks"


def _targets(tmp_path, *names):
    rows = []
    for name in names:
        source = tmp_path / f"{name}.src.txt"
        source.write_text("first line\nsecond line\n", encoding="utf-8")
        rows.append(
            {
                "filename": name,
                "version": 1,
                "owner_id": "alice",
                "classification": 2,
                "department": "finance",
                "storage_path": str(source),
            }
        )
    return rows

# --------------------------------------------- never an automatic path (criterion 3, hard)
def test_nothing_in_the_application_can_reach_the_rebuild_command():
    """No startup hook, no upload hook, no scheduler job may import or call the rebuild.

    A test rather than a git grep in a report, because it keeps being true. Prose that names
    the command is allowed -- app/rag/indexing.py points at it to explain where a new profile
    comes from -- but an import, an attribute call or a subprocess that starts it is the
    automatic path the requirement forbids, and that is what this looks for.
    """
    patterns = (
        "import rebuild_index",
        "from scripts.rebuild_index",
        "from scripts import rebuild_index",
        "importlib.import_module(\"scripts.rebuild_index\"",
        "rebuild_index.main(",
        "rebuild_index.run_rebuild(",
        "run_rebuild(",
    )
    hits = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            if pattern in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")
    assert hits == []


def test_importing_the_command_does_not_run_anything(tmp_path, monkeypatch):
    module = _command()
    monkeypatch.setattr(module, "run_rebuild", lambda **kwargs: pytest.fail("import ran a rebuild"))
    monkeypatch.setattr(module, "rebuild_document", lambda **kwargs: pytest.fail("import rebuilt a document"))
    assert module.invoked_by_human(str(tmp_path / "uvicorn.py")) is False


def test_a_server_entry_point_is_not_a_human_invocation(monkeypatch):
    module = _command()
    argv0 = str(Path(module.__file__).with_name("server.py"))
    assert module.invoked_by_human(argv0) is False
    assert module.invoked_by_human(Path(module.__file__)) is True


def test_apply_without_a_human_latch_refuses_before_touching_anything(tmp_path):
    from app.rag.indexing import IndexPublisher

    store = _VectorStore(_Embeddings(NEW_DIM))
    store.seed("policy.txt", ["old line"], [0.5] * OLD_DIM)
    registry = _registry(tmp_path)
    module = _command()

    with pytest.raises(module.RebuildRefused, match="manual"):
        module.run_rebuild(
            targets=_targets(tmp_path, "policy.txt"),
            retriever=store,
            publisher=IndexPublisher(registry, store=None),
            scope=_scope(NEW_MODEL, NEW_DIM),
            documents_dir=str(tmp_path),
            load_text=lambda path: Path(path).read_text(encoding="utf-8"),
            apply=True,
            manual=False,
        )

    assert store.calls == []
    assert store.records["policy.txt"], "the refusal must not have deleted live vectors"
    assert registry.index_ids() == ()


# ------------------------------------------------------- a rehearsal must be weightless
def test_a_dry_run_reads_the_library_and_changes_nothing(tmp_path):
    from app.rag.indexing import IndexPublisher

    store = _VectorStore(_Embeddings(NEW_DIM))
    store.seed("policy.txt", ["old line one", "old line two"], [0.5] * OLD_DIM)
    registry = _registry(tmp_path)
    module = _command()

    report = module.run_rebuild(
        targets=_targets(tmp_path, "policy.txt"),
        retriever=store,
        publisher=IndexPublisher(registry, store=None),
        scope=_scope(NEW_MODEL, NEW_DIM),
        documents_dir=str(tmp_path),
        load_text=lambda path: Path(path).read_text(encoding="utf-8"),
        apply=False,
        manual=False,
    )

    assert store.calls == []
    assert registry.index_ids() == ()
    assert report["rebuilt"] == 0
    assert report["planned_only"] == 1
    assert report["documents"][0]["status"] == "planned"
    assert report["cross_dimension_vectors_before"] == 2
    assert report["cross_dimension_vectors_after"] == 0


# ------------------------------------- the embedder is proven before anything is deleted
def _refuse(tmp_path, embeddings, module_scope=None):
    from app.rag.indexing import IndexPublisher

    store = _VectorStore(embeddings)
    store.seed("policy.txt", ["old line"], [0.5] * OLD_DIM)
    registry = _registry(tmp_path)
    module = _command()
    with pytest.raises(module.EmbedderUnavailable) as refused:
        module.run_rebuild(
            targets=_targets(tmp_path, "policy.txt"),
            retriever=store,
            publisher=IndexPublisher(registry, store=None),
            scope=module_scope or _scope(NEW_MODEL, NEW_DIM),
            documents_dir=str(tmp_path),
            load_text=lambda path: Path(path).read_text(encoding="utf-8"),
            apply=True,
            manual=True,
        )
    return refused.value, store, registry


def test_an_all_zero_embedding_refuses_to_rebuild(tmp_path):
    reason, store, registry = _refuse(tmp_path, _Embeddings(NEW_DIM, zero=True))
    assert "all-zero" in str(reason)
    assert store.calls == []
    assert registry.index_ids() == ()


def test_an_unreachable_embedder_refuses_to_rebuild(tmp_path):
    reason, store, _registry_ = _refuse(tmp_path, _Embeddings(NEW_DIM, broken=True))
    assert "RuntimeError" in str(reason)
    assert store.calls == []


def test_a_width_that_is_not_the_declared_one_refuses_to_rebuild(tmp_path):
    reason, store, _registry_ = _refuse(tmp_path, _Embeddings(OLD_DIM))
    assert f"{OLD_DIM} dimensions" in str(reason)
    assert store.calls == []


def test_the_probe_only_runs_when_a_rebuild_is_actually_applied(tmp_path):
    from app.rag.indexing import IndexPublisher

    embeddings = _Embeddings(NEW_DIM)
    module = _command()
    report = module.run_rebuild(
        targets=_targets(tmp_path, "policy.txt"),
        retriever=_VectorStore(embeddings),
        publisher=IndexPublisher(registry=_registry(tmp_path), store=None),
        scope=_scope(NEW_MODEL, NEW_DIM),
        documents_dir=str(tmp_path),
        load_text=lambda path: Path(path).read_text(encoding="utf-8"),
        apply=False,
        manual=False,
    )
    assert embeddings.queries == 0
    assert report["planned_only"] == 1

# ------------------------------------------------------------- the rebuild itself
def _run(tmp_path, *, module, store, registry, targets, apply=True, manual=True, dimension=NEW_DIM,
         model=NEW_MODEL):
    from app.rag.indexing import IndexPublisher

    return module.run_rebuild(
        targets=targets,
        retriever=store,
        publisher=IndexPublisher(registry, store=None),
        scope=_scope(model, dimension),
        documents_dir=str(tmp_path),
        load_text=lambda path: Path(path).read_text(encoding="utf-8"),
        apply=apply,
        manual=manual,
    )


def test_a_rebuild_replaces_the_vectors_and_publishes_a_version_bound_to_the_new_profile(tmp_path):
    from app.rag.indexing import IndexPublisher, document_index_id

    module = _command()
    registry = _registry(tmp_path, model=MODEL, dimension=OLD_DIM)
    stale = registry.create_version(
        index_id=document_index_id("policy.txt"),
        source_version_id="policy.txt|v1",
        backend="chroma",
        chunk_count=1,
        checksum="a" * 64,
    )
    registry.publish(stale.index_version_id)
    # The operator changed the embedder. Nothing else has happened yet.
    registry._fixed_scope = _scope(NEW_MODEL, NEW_DIM)

    store = _VectorStore(_Embeddings(NEW_DIM))
    store.seed("policy.txt", ["an old 384-wide row"], [0.5] * OLD_DIM)
    report = _run(tmp_path, module=module, store=store, registry=registry,
                  targets=_targets(tmp_path, "policy.txt"))

    assert store.calls == [("delete", "policy.txt"), ("add", "policy.txt")]
    assert report["rebuilt"] == 1
    assert report["failed"] == 0
    assert report["cross_dimension_vectors_before"] == 1
    assert report["cross_dimension_vectors_after"] == 0
    assert {len(vector) for _content, vector in store.records["policy.txt"]} == {NEW_DIM}

    current = registry.current(document_index_id("policy.txt"))
    assert current.index_version_id != stale.index_version_id
    assert (current.embedding_model, current.dimension) == (NEW_MODEL, NEW_DIM)
    assert registry._versions[stale.index_version_id].status == "superseded"
    assert report["codes"] == []
    retained = report["retained"][0]
    assert retained["versions"] == 2 and retained["superseded"] == 1
    assert retained["current"] == current.index_version_id
    assert retained["current_scope"] == f"{NEW_MODEL}/{NEW_DIM}"
    assert report["documents"][0]["previous_index_version_id"] == stale.index_version_id


def test_a_document_whose_source_is_gone_is_skipped_and_left_alone(tmp_path):
    module = _command()
    registry = _registry(tmp_path)
    store = _VectorStore(_Embeddings(NEW_DIM))
    store.seed("policy.txt", ["still retrievable"], [0.5] * NEW_DIM)
    row = {"filename": "policy.txt", "version": 1, "storage_path": str(tmp_path / "nope.txt")}

    report = _run(tmp_path, module=module, store=store, registry=registry, targets=[row])

    assert report["documents"][0]["status"] == "skipped"
    assert report["documents"][0]["reason"] == "source_missing"
    assert store.calls == []
    assert store.records["policy.txt"]


class _StaleAddStore(_VectorStore):
    """A store that answers the new model on query but writes old-width rows."""

    def add_document(self, filename, content, classification=1, department=None):
        self.calls.append(("add", filename))
        chunks = [line for line in str(content).splitlines() if line.strip()]
        self.records[filename] = [(line, [0.5] * OLD_DIM) for line in chunks]
        return True, "added"


def test_a_rebuild_that_cannot_verify_its_own_output_stops_before_the_next_document(tmp_path):
    from app.rag.indexing import document_index_id

    module = _command()
    registry = _registry(tmp_path)
    store = _StaleAddStore(_Embeddings(NEW_DIM))
    targets = _targets(tmp_path, "a-policy.txt", "b-finance.txt")

    report = _run(tmp_path, module=module, store=store, registry=registry, targets=targets)

    assert report["failed"] == 1
    assert report["rebuilt"] == 0
    assert report["aborted"].startswith("a-policy.txt: verify_failed")
    # The unverified document never became a published version: the registry still holds
    # nothing, so the index cannot claim an index the vector store does not have.
    assert registry.index_ids() == ()
    assert document_index_id("a-policy.txt") not in registry._current
    # ...and the run stopped, so the second document was never deleted.
    assert ("delete", "b-finance.txt") not in store.calls


def test_the_report_answers_how_much_failed_and_what_is_live_now(tmp_path):
    module = _command()
    registry = _registry(tmp_path)
    store = _VectorStore(_Embeddings(NEW_DIM))
    report = _run(tmp_path, module=module, store=store, registry=registry,
                  targets=_targets(tmp_path, "policy.txt"))
    lines = "\n".join(module.report_lines(report))

    assert "scope=bge-m3/768" in lines
    assert "planned=1 rebuilt=1 skipped=0 failed=0" in lines
    assert "cross_dimension_vectors before=0 after=0" in lines
    assert "current=" in lines and "versions=2" not in lines
    # One version exists, so nothing has been retained yet; the line still has to say what is
    # live, because that is the question an operator asks after a rebuild.
    assert "versions=1" in lines


def test_the_status_report_names_every_document_that_is_not_on_the_current_profile(tmp_path):
    from app.rag.indexing import IndexRegistry, document_index_id

    module = _command()
    path = tmp_path / "indexes.json"
    path.write_text(
        json.dumps(
            {
                "current": {"document:legacy.txt": "document:legacy.txt:vx"},
                "versions": [
                    {
                        "index_version_id": "document:legacy.txt:vx",
                        "index_id": "document:legacy.txt",
                        "source_version_id": "legacy.txt|v1",
                        "backend": "chroma",
                        "chunk_count": 1,
                        "checksum": "a" * 64,
                        "status": "published",
                        "created_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = IndexRegistry(path, scope=_scope(NEW_MODEL, NEW_DIM))
    store = _VectorStore(_Embeddings(NEW_DIM))
    targets = [
        {"filename": "legacy.txt", "version": 1},
        {"filename": "fresh.txt", "version": 1},
        {"filename": "unversioned.txt", "version": 1},
    ]
    fresh = registry.create_version(
        index_id=document_index_id("fresh.txt"),
        source_version_id="fresh.txt|v1",
        backend="chroma",
        chunk_count=1,
        checksum="b" * 64,
    )
    registry.publish(fresh.index_version_id)

    report = module.status_report(registry=registry, scope=_scope(NEW_MODEL, NEW_DIM), targets=targets)

    assert report["drifted"] is True
    assert "embedding_scope_unknown" in report["codes"]
    assert report["indexes"] == 2
    # The version that never existed and the one with no profile both need a rebuild; the one
    # already bound to this profile does not.
    assert report["stale_documents"] == ["legacy.txt", "unversioned.txt"]
    assert report["documents_needing_rebuild"] == 2


# --------------------------------------------------------------- command line refusals
def test_the_confirm_string_has_to_name_a_model_and_a_width():
    module = _command()

    assert module.scope_from_text("bge-m3/768").key == (NEW_MODEL, NEW_DIM)
    for bad in ("", "bge-m3", "/768", "bge-m3/wide"):
        with pytest.raises(module.RebuildRefused):
            module.scope_from_text(bad)


def test_apply_refuses_a_confirm_string_that_is_not_the_configured_profile(tmp_path, capsys, monkeypatch):
    module = _command()
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("EMBEDDING_DIMENSION", str(NEW_DIM))

    assert module.main(["--apply", "--confirm-scope", "someone-elses-model/1024"]) == module.EXIT_USAGE
    assert "is not the configured profile" in capsys.readouterr().err


def test_confirm_scope_without_apply_is_a_usage_error(tmp_path, capsys):
    module = _command()

    assert module.main(["--confirm-scope", "bge-m3/768"]) == module.EXIT_USAGE
    assert "only means anything together with --apply" in capsys.readouterr().err


def test_a_matching_confirm_string_still_needs_a_real_invocation(tmp_path, capsys, monkeypatch):
    """Typing the profile is necessary but not sufficient.

    Under pytest argv[0] is the runner, not this script, so the run is refused before any
    registry, catalog or vector store is opened -- which is exactly the shape an automated
    caller would have.
    """
    module = _command()
    monkeypatch.setenv("EMBEDDING_MODEL", MODEL)
    monkeypatch.setenv("EMBEDDING_DIMENSION", str(NEW_DIM))

    assert module.main(["--apply", "--confirm-scope", f"{MODEL}/{NEW_DIM}"]) == module.EXIT_USAGE
    assert "only runs when scripts/rebuild_index.py is invoked as a command" in capsys.readouterr().err


def test_the_metadata_file_the_app_reads_is_the_one_the_command_writes(tmp_path, monkeypatch):
    from app.rag.indexing import default_metadata_path

    monkeypatch.setenv("INDEX_METADATA_PATH", str(tmp_path / "index-versions.json"))

    assert default_metadata_path() == str(tmp_path / "index-versions.json")