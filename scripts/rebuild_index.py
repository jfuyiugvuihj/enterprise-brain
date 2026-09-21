"""Rebuild every document's vectors under the embedding profile this build is configured for.

跟进单 R22 (docs/handoff/2026-09-15-backend-followup-requests.md section 18). The problem this
command exists for: EMBED_MODEL is a module-level constant, so changing it -- or upgrading the
model -- leaves vectors that a different embedder computed, and nothing in the system can
recompute them. Retrieval then pairs a new query vector against old document vectors and
quality collapses silently.

WHAT THIS COMMAND GUARANTEES

1. It refuses to write anything until the embedder has actually produced one vector of the
   declared width that is not all zeros. A rebuild that could not embed would otherwise
   delete live vectors and leave an empty knowledge base behind.
2. It never deletes a document's vectors to make room for new ones it has not produced
   yet. When the text moved, add_document embeds and vets the new vectors before it retires
   the old ones, so the document keeps answering from its old vectors for the whole
   re-embedding. When only the embedding profile moved -- the one case where the store would
   otherwise answer "content unchanged" and write nothing -- the command first asks the
   embedder for one of that document's own chunks and checks the answer, and only then
   deletes. An embedder that dies half-way through a library used to leave every document it
   had reached with no vectors at all; now it leaves them as they were.
3. It publishes one new index version per rebuilt document, bound to the embedding profile
   that produced the vectors, and it keeps every previous version so the operator can still
   name and roll back to it.
4. With --incremental it re-embeds only the documents whose stored chunks no longer match
   their source, which is also what makes an interrupted run resumable: the next run plans
   from the versions the previous one published, so there is no journal to clear, nothing to
   delete by hand, and no window in which the library is half-gone. Run it once per off-peak
   window with --time-budget-seconds until it reports remaining=0.

    python scripts/rebuild_index.py --apply --incremental --time-budget-seconds 1800

WHY IT IS MANUAL ONLY

Nothing in app/ imports or calls this module: no startup hook, no upload hook, no scheduler
job (verified with git grep on the commit that added this file). A rebuild rewrites the whole
knowledge base, so it runs when a human says so -- and it takes both --apply and an exact
--confirm-scope string to do anything at all, because the operator must have read which
profile is about to be written.

    python scripts/rebuild_index.py --status
    python scripts/rebuild_index.py --apply --confirm-scope "nomic-embed-text/768"

WHAT ``--status`` ANSWERS

The profile questions come out of the index registry, and the vector questions come out of the
store: ``zero_vectors_before`` counts the stored vectors that are all zeros, and
``cross_dimension_vectors_before`` counts the ones whose width is not the declared dimension.
Those two are the Chroma half of the mirror gate in the pgvector runbook, so they are reported
by the command the operator is told to run rather than only by a rebuild. The store is read a
page at a time (``--census-page-size``) with no embedder and no model call, and a store that
cannot be read comes back as ``census_measurable: false`` with both counters null: an
unmeasured gate never prints like a passed one.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.rag.indexing import (
    CODE_SCOPE_MISMATCH,
    CODE_SCOPE_UNKNOWN,
    PLAN_REASON_FORCED,
    PLAN_REASON_INDEX_RETIRED,
    PLAN_REASON_MATCHES,
    SCOPE_UNKNOWN,
    DocumentIndexPublication,
    EmbeddingScope,
    IndexPlanEntry,
    IndexPublicationError,
    IndexPublisher,
    IndexRegistry,
    PostgresIndexStore,
    configured_embedding_scope,
    default_metadata_path,
    plan_index_refresh,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_EMBEDDER_UNUSABLE = 3
EXIT_REBUILD_FAILED = 4

PROBE_TEXT = "enterprise brain index rebuild probe"

# Which physical swap a document's rebuild used, reported per document so the difference is
# auditable instead of implied: an incremental add, a retire that had to be proven first,
# or nothing at all.
SWAP_NONE = "none"
SWAP_INCREMENTAL = "add-only"
SWAP_FORCED_RETIRE = "verified-retire-then-add"
SWAP_PUBLISH_ONLY = "publish-only"

#: The reasons that mean "the stored vectors are not usable under this profile", so the
#: document has to be re-embedded even when its text never moved. Everything else that
#: schedules work -- a moved catalog version, changed content, a document that was never
#: published -- is a case where `add_document` produces the vectors itself before it retires
#: anything, which is the order that keeps the document readable while the work runs.
FORCED_RETIRE_REASONS = frozenset(
    {
        CODE_SCOPE_MISMATCH,
        CODE_SCOPE_UNKNOWN,
        PLAN_REASON_FORCED,
        PLAN_REASON_INDEX_RETIRED,
    }
)


class RebuildRefused(RuntimeError):
    """The rebuild stopped before it wrote anything, with a reason an operator can act on."""


class EmbedderUnavailable(RebuildRefused):
    """The current embedding profile could not be satisfied, so nothing may be rewritten."""


def scope_from_text(value: str) -> EmbeddingScope:
    """Parse the "<model>/<dimension>" form the operator confirms, or refuse."""
    model, separator, dimension = str(value or "").rpartition("/")
    if not separator or not model.strip():
        raise RebuildRefused(
            f"--confirm-scope must look like <model>/<dimension>, got {value!r}"
        )
    try:
        width = int(dimension.strip())
    except ValueError:
        raise RebuildRefused(f"--confirm-scope dimension is not an integer: {value!r}") from None
    return EmbeddingScope(model.strip(), width)


def invoked_by_human(argv0: str | None = None) -> bool:
    """True only when this file is running as a program.

    An import is not an invocation, and the difference has to be checkable rather than
    merely intended: this command deletes vectors. Application code that imported the module
    and reached for run_rebuild() would see argv[0] pointing at the server entry point, which
    is exactly the automatic path the requirement forbids. A symlinked or renamed copy is
    refused too -- a false refusal is an operator typing one more flag, a false acceptance is
    a knowledge base rewritten by something nobody ran.
    """
    candidate = str(argv0 if argv0 is not None else (sys.argv[0] if sys.argv else ""))
    try:
        return Path(candidate).name == Path(__file__).name
    except OSError:  # pragma: no cover - unreadable argv[0]
        return False


def resolve_storage_path(row: dict, documents_dir: str) -> str:
    """Find the stored file behind one catalog row.

    The catalog publishes its paths relative to the working directory and falls back to a bare
    file name when no relative form exists, so neither value can be trusted as-is. Every
    candidate is tried in turn and the first real file wins; a document whose source cannot be
    found is skipped rather than rebuilt, because rebuilding from nothing would delete vectors
    that still work.
    """
    candidates: list[str] = []
    declared = str(row.get("storage_path") or "").strip()
    if declared:
        candidates.append(declared)
        candidates.append(str(Path(documents_dir) / Path(declared.replace("\\", "/")).name))
    elif row.get("filename") and row.get("version"):
        from app.documents.catalog import build_storage_name

        candidates.append(str(Path(documents_dir) / build_storage_name(str(row["filename"]), int(row["version"]))))
    for candidate in candidates:
        try:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        except OSError:
            continue
    return ""


def vector_census(retriever, filename: str, dimension: int) -> dict:
    """Count the stored vectors of one document by width, and flag the all-zero ones.

    Read-only, and it degrades to ``measurable: false`` when the vector store cannot be
    inspected: an unavailable census is reported as unavailable rather than as zero, because
    "we could not look" and "there is nothing wrong" are different answers.
    """
    collection = getattr(retriever, "collection", None)
    getter = getattr(collection, "get", None)
    census = {"measurable": False, "total": 0, "wrong_dimension": 0, "zero_vectors": 0, "widths": []}
    if not callable(getter):
        return census
    try:
        try:
            stored = getter(where={"filename": filename}, include=["embeddings"]) or {}
        except TypeError:
            stored = getter(where={"filename": filename}) or {}
    except Exception:
        return census
    embeddings = stored.get("embeddings")
    if embeddings is None:
        return census
    widths = []
    for vector in embeddings:
        try:
            width = len(vector)
        except TypeError:
            continue
        widths.append(int(width))
    census["measurable"] = True
    census["total"] = len(widths)
    census["widths"] = widths
    census["wrong_dimension"] = sum(1 for width in widths if width != int(dimension))
    census["zero_vectors"] = sum(1 for vector in embeddings if _is_zero_vector(vector))
    return census


def _is_zero_vector(vector) -> bool:
    try:
        return len(vector) > 0 and not any(float(value) for value in vector)
    except (TypeError, ValueError):
        return False


#: How many stored vectors one census page reads. The census is what lets ``--status`` answer
#: the mirror gate in the pgvector runbook (跟进单 §61 / R125), and a stored vector is
#: ``dimension`` floats: asking a whole library for its embeddings in one call is how a
#: read-only report turns into a memory incident, so the store is walked a page at a time.
CENSUS_PAGE_SIZE = 200

#: How many named documents of each census list reach stdout. The full lists go to the report
#: file named by ``census_report_path``, outside the repository.
CENSUS_LIST_LIMIT = 10

#: Bucket for stored vectors whose metadata carries no filename, so they are named by what
#: they are instead of quietly missing from the per-document lists.
CENSUS_NO_FILENAME = "(vectors with no filename in their metadata)"

#: Name under which a census that could not read the store at all reports itself, so "the
#: whole store was unmeasurable" is not repeated as a hundred complaints about documents.
CENSUS_NO_STORE = "(the whole vector store)"


class _CensusCollection:
    """A vector collection with the write half hidden.

    The census is advertised as something an operator may run against a live library, so the
    handle it is given must not be able to write even if the code above it changes its mind:
    ``get`` and ``count``, and anything else is an error rather than a call.
    """

    def __init__(self, collection):
        self._collection = collection

    def get(self, **kwargs):
        return self._collection.get(**kwargs)

    def count(self):
        return self._collection.count()

    def __getattr__(self, name):
        raise AttributeError(
            f"{type(self).__name__} exposes get() and count() only; {name!r} would be a write"
        )


class CensusStore:
    """A vector store opened for a census: one read-only collection, and where it came from."""

    def __init__(self, collection, *, source: str = ""):
        self.collection = collection if isinstance(collection, _CensusCollection) else _CensusCollection(collection)
        self.source = str(source)


def open_census_store(chroma_dir: str | None = None,
                      collection_name: str | None = None) -> tuple:
    """Open the live vector store for a census, or come back with why it stayed shut.

    Deliberately not ``DocumentRetriever()``: that constructor makes the directory when it is
    missing and calls ``get_or_create_collection``, so a command whose whole job is to report
    what is already stored would be able to add to it. The store is also opened without
    touching the embedder, because ``--status`` has to answer on a machine where the model is
    not configured, and an unopenable store is an unmeasurable census, not a crash.
    """
    directory = str(chroma_dir or os.getenv("CHROMA_DIR") or (ROOT / "chroma_db"))
    name = str(collection_name or os.getenv("CHROMA_COLLECTION") or "enterprise_docs")
    if not Path(directory).is_dir():
        return None, f"there is no vector store directory at {directory}"
    try:
        import chromadb
        from chromadb.config import Settings
    except ModuleNotFoundError as exc:
        return None, f"chromadb is not importable here ({exc})"
    try:
        client = chromadb.PersistentClient(
            path=directory, settings=Settings(anonymized_telemetry=False)
        )
        collection = client.get_collection(name=name)
    except Exception as exc:
        # Chroma is one writer per directory, so "the application is writing right now" has
        # to arrive as a reason an operator can read, not as a traceback.
        return None, f"{type(exc).__name__}: {exc}"
    return CensusStore(collection, source=f"{directory}#{name}"), ""


def _tally_stored_vector(documents: dict, vector, metadata, dimension: int) -> bool:
    """Add one stored vector to its document's tally; False when the row is not a vector.

    The zero rule is the one the write gate uses (``_is_zero_vector``), so a vector the
    rebuild would refuse is the same vector the census counts. Two answers to "is this
    vector all zeros" is how a gate gets passed by looking at the wrong sheet.
    """
    try:
        width = len(vector)
    except TypeError:
        return False
    row = documents.setdefault(
        str((metadata or {}).get("filename") or "") or CENSUS_NO_FILENAME,
        {"vectors": 0, "zero_vectors": 0, "cross_dimension_vectors": 0, "widths": set()},
    )
    row["vectors"] += 1
    if _is_zero_vector(vector):
        row["zero_vectors"] += 1
    if width != int(dimension):
        row["cross_dimension_vectors"] += 1
        row["widths"].add(int(width))
    return True


def library_vector_census(retriever, dimension: int, *, page_size: int = CENSUS_PAGE_SIZE,
                          catalog_filenames=(), unavailable_reason: str = "",
                          clock: Callable[[], float] = time.monotonic) -> dict:
    """Every stored vector in the library, counted by document, read a page at a time.

    ``vector_census()`` counts one document because a rebuild needs that answer twice per
    document, while the operator's question is bigger than one document: "is there any
    unusable vector in this store". Asking it document by document is one request per
    document and a total nobody can check against the store's own count, so this walks the
    store itself -- ``get(limit=window, offset=n)`` -- classifies each vector, drops the
    floats, and keeps only the tallies.

    It only ever reads (``get`` and ``count``), and it refuses to answer a question it could
    not ask: a store that will not open, a page that raises, a window the store ignores, or a
    scan that did not cover ``collection.count()`` vectors comes back ``measurable: false``
    with both counters null and a reason naming what happened. A document the catalog knows
    about but the store holds nothing for is listed as "nothing to look at", which is not the
    same answer as "looked, nothing wrong".
    """
    census = {
        "measurable": False,
        "reason": unavailable_reason or "no vector store was opened",
        "source": str(getattr(retriever, "source", "")),
        "dimension": int(dimension),
        "page_size": int(page_size),
        "pages_read": 0,
        "vectors_read": 0,
        "store_vectors": None,
        "non_sequence_vectors": 0,
        "zero_vectors": None,
        "cross_dimension_vectors": None,
        "documents": 0,
        "elapsed_seconds": 0.0,
        "zero_vector_documents": [],
        "cross_dimension_vector_documents": [],
        "unmeasurable_documents": [],
    }
    collection = getattr(retriever, "collection", None)
    getter = getattr(collection, "get", None)
    if int(page_size) < 1:
        census["reason"] = unavailable_reason or f"--census-page-size must be at least 1, not {page_size}"
        return census
    if not callable(getter):
        return census
    started = clock()
    window = int(page_size)
    documents: dict[str, dict] = {}
    counter = getattr(collection, "count", None)
    if callable(counter):
        try:
            census["store_vectors"] = int(counter())
        except Exception:
            census["store_vectors"] = None
    offset = 0
    previous_ids: frozenset = frozenset()
    reached_end = False
    honoured_window = True
    while True:
        try:
            page = getter(include=["embeddings", "metadatas"], limit=window, offset=offset) or {}
        except TypeError as exc:
            census["reason"] = f"this store's get() cannot take a page window ({exc})"
            break
        except Exception as exc:
            census["reason"] = f"the vector store raised {type(exc).__name__} while paging"
            break
        vectors = page.get("embeddings")
        ids = page.get("ids")
        if vectors is None or ids is None:
            census["reason"] = "the vector store returned a page with no embeddings or ids in it"
            break
        page_ids = frozenset(str(item) for item in ids)
        if page_ids and page_ids == previous_ids:
            honoured_window = False
            break
        previous_ids = page_ids
        rows = list(vectors)
        metadatas = list(page.get("metadatas") or [])
        for position, vector in enumerate(rows):
            metadata = metadatas[position] if position < len(metadatas) else None
            if not _tally_stored_vector(documents, vector, metadata, dimension):
                census["non_sequence_vectors"] += 1
        census["pages_read"] += 1
        census["vectors_read"] += len(rows)
        offset += len(rows)
        if len(rows) < window:
            reached_end = True
            break
    rows_by_name = sorted(documents.items())
    census["documents"] = len(rows_by_name)
    census["zero_vector_documents"] = [
        {"filename": name, "zero_vectors": row["zero_vectors"], "vectors": row["vectors"]}
        for name, row in rows_by_name
        if row["zero_vectors"]
    ]
    census["cross_dimension_vector_documents"] = [
        {
            "filename": name,
            "cross_dimension_vectors": row["cross_dimension_vectors"],
            "vectors": row["vectors"],
            "widths": sorted(row["widths"]),
        }
        for name, row in rows_by_name
        if row["cross_dimension_vectors"]
    ]
    stored = census["store_vectors"]
    if not honoured_window:
        census["reason"] = (
            "the store handed back the same page twice, so it does not honour the read "
            f"window; the scan stopped after {census['vectors_read']} vectors"
        )
    elif not reached_end:
        pass  # The reason was already set where the read failed.
    elif stored is not None and stored != census["vectors_read"]:
        census["reason"] = (
            f"the scan read {census['vectors_read']} vectors, the store counts {stored}"
        )
    else:
        census["measurable"] = True
        census["reason"] = ""
        census["zero_vectors"] = sum(row["zero_vectors"] for _name, row in rows_by_name)
        census["cross_dimension_vectors"] = sum(
            row["cross_dimension_vectors"] for _name, row in rows_by_name
        )
    wanted = sorted({str(item) for item in catalog_filenames if str(item)})
    if census["pages_read"]:
        # The store was read, so a catalog document with no rows in it is a document there was
        # nothing to look at -- which is a different answer from "looked, found nothing wrong".
        census["unmeasurable_documents"] = [
            {
                "filename": name,
                "reason": "the store holds no vectors for this document, so there is nothing to census",
            }
            for name in wanted
            if not documents.get(name)
        ]
    else:
        # Nothing could be read at all, so say so once instead of blaming every document in
        # the catalog for the store being shut.
        census["unmeasurable_documents"] = [{"filename": CENSUS_NO_STORE, "reason": census["reason"]}]
    census["elapsed_seconds"] = round(max(0.0, clock() - started), 3)
    return census


def write_census_report(census: dict, *, path: str | None = None) -> str:
    """Put the full census lists outside the repository, where an operator can open them.

    stdout carries the first ``CENSUS_LIST_LIMIT`` named documents of each list and nothing
    else, because ``--status --json`` gets pasted into a ticket and a hundred-document library
    would print a screen of names to repeat what the two counters already say. The whole lists
    land here instead; an empty path means the file could not be written, which is never a
    reason to lose the counters on stdout.
    """
    target = Path(path or Path(tempfile.gettempdir()) / "enterprise-brain-vector-census.json")
    try:
        target.write_text(
            json.dumps(census, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return ""
    return str(target)


def probe_embedder(embeddings, scope: EmbeddingScope) -> str:
    """Prove this build can produce a vector of the declared width before anything is deleted.

    Returns "" when the probe passed, otherwise the reason it did not. Both failures are
    refused: the wrong width means the declared profile is simply not what the running model
    produces, and an all-zero vector is R21's silent fallback -- rebuilding with it would
    replace old-but-real vectors with uniform noise and report success.
    """
    embed = getattr(embeddings, "embed_query", None)
    if not callable(embed):
        return "the embedder exposes no embed_query()"
    try:
        vector = embed(PROBE_TEXT)
    except Exception as exc:
        return f"the embedder raised {type(exc).__name__}: {exc}"
    try:
        len(vector)
    except TypeError:
        return "the embedder did not return a sequence"
    return verify_embedding_set([vector], scope, 1)


def verify_embedding_set(vectors, scope: EmbeddingScope, expected_count: int | None = None) -> str:
    """Why this set of vectors may not be trusted, or "" when it may.

    One rule, read in two places: the probe that opens a run, and the per-document pre-flight
    a forced retire runs before it is allowed to delete anything. Count, width and all-zero
    are the three ways an embedder lies -- a stub that answers nothing, a model that is not
    the one declared, and R21's silent zero fallback. The wording is part of the contract: it
    is what an operator reads after ``refusing to rebuild:``.
    """
    rows = list(vectors or ())
    if expected_count is not None and len(rows) != int(expected_count):
        return f"the embedder returned {len(rows)} vectors for {expected_count} chunks"
    for position, vector in enumerate(rows):
        try:
            width = len(vector)
        except TypeError:
            return f"the embedder returned a non-sequence at position {position}"
        if width != scope.dimension:
            return f"the embedder returned {width} dimensions, the profile declares {scope.dimension}"
        if _is_zero_vector(vector):
            return "the embedder returned an all-zero vector (embedding is not really working)"
    if not rows:
        return "the embedder returned no vectors"
    return ""


def splitter_chunk_texts(retriever):
    """The chunker the write path actually uses, or None when this store does not have one.

    An incremental plan is worth as much as its digest, and the digest is computed over chunk
    texts -- so there is exactly one acceptable source for the split: the splitter the
    retriever embeds with. A lookalike would report 'content_changed' on every run, which is not a safe
    failure, it is a full rebuild wearing an incremental flag.
    """
    splitter = getattr(retriever, "splitter", None)
    chunker = getattr(splitter, "split_text", None)
    return chunker if callable(chunker) else None


def documents_to_rebuild(current_documents, *, only_names=None) -> list[dict]:
    rows = list(current_documents() or [])
    if only_names:
        wanted = {str(name) for name in only_names}
        rows = [row for row in rows if str(row.get("filename")) in wanted]
    return sorted(rows, key=lambda row: str(row.get("filename") or ""))



def rebuild_document(*, row: dict, retriever, publisher, scope: EmbeddingScope,
                     load_text: Callable[[str], str], documents_dir: str, apply: bool,
                     planned: IndexPlanEntry | None = None,
                     chunk_texts: Callable[[str], list] | None = None) -> dict:
    """Re-embed one document and publish the version that describes it.

    Two jobs used to be run as one, and they want opposite orders.

    * The text moved, so new vectors are wanted. 'add_document' is the only sanctioned writer
      and it embeds and vets the new vectors before it retires the old ones, so calling it
      alone keeps the document answering from its old vectors for the whole re-embedding. The
      unconditional delete this function used to issue first took that property away and
      bought nothing: 'add_document' already retires every id the document holds.
    * Only the embedding profile moved. Then the text has not changed, and 'add_document'
      would answer the store's own "内容未变化" and write nothing -- published as a version
      bound to the new profile, that would be a claim this build cannot honour. So the retire
      stays forced, but only after the embedder has been asked for one of this document's own
      chunks and the answer has been checked. That costs one extra embedding per rebuilt
      document, and it is the price of not retiring live vectors on the strength of a probe
      that ran once, possibly hours earlier.

    An interrupted document is therefore never left with fewer vectors than it started with
    by anything this function does: the delete is reached only with the replacement verified
    in hand, and the publish only after the store has been counted. The window this command
    cannot close from outside 'app/rag/retriever.py' is inside 'add_document' itself: there a
    chunk id is a pure function of the filename, so two generations of one document cannot
    coexist, and the retire and the write are two calls rather than one transaction. That
    window carries no model call, and it is one document wide.

    With 'apply' false this is read-only by construction: it resolves the source, counts what
    is stored today and reports what it would do. It never deletes, never embeds and never
    publishes, because a rehearsal that damages the library is not a rehearsal.
    """
    filename = str(row.get("filename") or "").strip()
    result = {
        "filename": filename,
        "status": "planned" if not apply else "failed",
        "reason": "",
        "index_version_id": "",
        "previous_index_version_id": "",
        "chunk_count": 0,
        "embedded_texts": 0,
        "swap": SWAP_NONE,
        "before": {},
        "after": {},
    }
    if planned is not None and planned.reason == PLAN_REASON_MATCHES:
        # The published digest already equals the source. Neither the store nor the embedder
        # is asked for anything, which is the entire point of planning before acting.
        result["status"] = "unchanged"
        result["reason"] = planned.reason
        result["chunk_count"] = planned.chunk_count
        result["index_version_id"] = planned.current_index_version_id
        result["previous_index_version_id"] = planned.current_index_version_id
        return result

    forced_retire = planned is None or planned.reason in FORCED_RETIRE_REASONS
    chunker = chunk_texts if callable(chunk_texts) else splitter_chunk_texts(retriever)
    pre_flight = forced_retire and chunker is not None
    path = resolve_storage_path(row, documents_dir)
    if not path:
        result["reason"] = "source_missing"
        result["status"] = "skipped"
        return result
    try:
        content = load_text(path)
    except Exception as exc:
        result["reason"] = f"parse_failed ({type(exc).__name__})"
        return result
    if not str(content or "").strip():
        result["reason"] = "source_empty"
        return result

    reader = getattr(retriever, "document_chunks", None)
    before = vector_census(retriever, filename, scope.dimension)
    result["before"] = before
    result["previous_index_version_id"] = _current_version_id(publisher, filename)
    if not apply:
        # Report the size of the job without starting it.
        rows = list(reader(filename)) if callable(reader) else []
        predicted = planned.chunk_count if planned is not None else len(rows)
        result["chunk_count"] = predicted
        result["embedded_texts"] = predicted + (1 if pre_flight else 0)
        result["after"] = {"measurable": False, "total": 0, "wrong_dimension": 0, "zero_vectors": 0}
        return result
    if pre_flight:
        # Prove the embedder is alive and at the declared width for *this* document, while
        # its vectors are still in the store. One text is enough for that: what is being
        # checked is not "will all N chunks come out right" -- add_document embeds those
        # itself and is the only sanctioned writer -- but "am I about to delete a document
        # I cannot rebuild". Without this, an embedder that dies at document 400 of 900 is
        # discovered after document 400 has already been deleted, and with the vector mirror
        # off (the default) there is nothing to put back.
        try:
            texts = list(chunker(content))
        except Exception as exc:
            result["reason"] = f"chunk_failed ({type(exc).__name__})"
            return result
        if not texts:
            result["reason"] = "chunk_failed (the chunker returned no text)"
            return result
        try:
            vectors = retriever.embedding.embed_documents(texts[:1])
        except Exception as exc:
            result["reason"] = f"embed_failed_before_delete ({type(exc).__name__})"
            return result
        bad = verify_embedding_set(vectors, scope, 1)
        if bad:
            result["reason"] = f"embed_failed_before_delete ({bad})"
            return result
        result["embedded_texts"] = 1

    if forced_retire:
        deleter = getattr(retriever, "delete_document", None)
        if not callable(deleter):
            result["reason"] = "vector store cannot retire"
            return result
        try:
            deleter(filename)
        except Exception as exc:
            # Refuse to continue: adding on top of a dimension this build cannot retire is
            # exactly the mixed-dimension library the version gate is meant to prevent.
            result["reason"] = f"delete_failed ({type(exc).__name__})"
            return result
    try:
        added, message = retriever.add_document(
            filename,
            content,
            int(row.get("classification") or 1),
            (row.get("department") or None),
        )
    except Exception as exc:
        result["reason"] = f"embed_failed ({type(exc).__name__})"
        return result
    if added is False and "未变化" not in str(message):
        result["reason"] = f"add_rejected ({message})"
        return result
    # The store answered that the content is unchanged: it wrote nothing, so it embedded
    # nothing. The vectors still in there are the ones that produced that answer, which is
    # why the publish below may describe them -- and why a profile change must not take this
    # branch quietly, which is what forced_retire is for.
    wrote_vectors = not (added is False and "未变化" in str(message))

    rows = list(reader(filename)) if callable(reader) else []
    after = vector_census(retriever, filename, scope.dimension)
    result["after"] = after
    if after.get("measurable") and (
        after.get("wrong_dimension") or after.get("zero_vectors") or not after.get("total")
    ):
        result["reason"] = (
            f"verify_failed (wrong_dimension={after.get('wrong_dimension')}, "
            f"zero_vectors={after.get('zero_vectors')}, total={after.get('total')})"
        )
        return result
    if not rows:
        result["reason"] = "verify_failed (no chunks came back)"
        return result
    if planned is not None and planned.chunk_count and len(rows) != planned.chunk_count:
        # The plan counted the source and the store holds something else: a swap that stopped
        # halfway, or a second writer. Publishing either number would describe an index the
        # store does not have, so the document is reported and the run stops below.
        result["reason"] = (
            "verify_failed (the store holds " + str(len(rows)) + " chunks, the plan read "
            + str(planned.chunk_count) + ")"
        )
        return result

    publication = DocumentIndexPublication(
        filename=filename,
        version=int(row.get("version") or 1),
        owner_id=row.get("owner_id"),
        classification=int(row.get("classification") or 1),
        department=str(row.get("department") or ""),
        chunks=tuple(str(item.get("content") or "") for item in rows),
        vector_ids=tuple(str(item.get("vector_id") or "") for item in rows),
        content_hash=str((rows[0] if rows else {}).get("hash") or ""),
    )
    try:
        outcome = publisher.apply(publication)
    except IndexPublicationError as exc:
        # The publication refused, so the pointer never moved: readers are still on the
        # version that was current before this document was rewritten, and the publisher has
        # already rolled it back and forgotten the half-built version. Report it as this
        # document's failure instead of letting a traceback end the run with no report at all.
        result["reason"] = "publish_failed (stage=" + str(exc.stage) + ")"
        return result
    if outcome is None:
        result["reason"] = "verify_failed (the vector store holds no chunks)"
        return result
    result["status"] = "rebuilt"
    result["reason"] = ""
    result["index_version_id"] = outcome.index_version_id
    result["chunk_count"] = outcome.chunk_count
    if wrote_vectors:
        result["embedded_texts"] += len(rows)
    if not wrote_vectors:
        result["swap"] = SWAP_PUBLISH_ONLY
    elif forced_retire:
        result["swap"] = SWAP_FORCED_RETIRE
    else:
        result["swap"] = SWAP_INCREMENTAL
    return result


def _current_version_id(publisher, filename: str) -> str:
    from app.rag.indexing import document_index_id

    try:
        return publisher.registry.current(document_index_id(filename)).index_version_id
    except KeyError:
        return ""


def run_rebuild(*, targets, retriever, publisher, scope: EmbeddingScope,
                documents_dir: str, load_text: Callable[[str], str], apply: bool, manual: bool,
                incremental: bool = False, stop_after: int | None = None,
                time_budget_seconds: float | None = None,
                clock: Callable[[], float] = time.monotonic,
                chunk_texts: Callable[[str], list] | None = None) -> dict:
    """Drive a rebuild, or refuse. 'manual' is the human-trigger latch.

    'manual=False' cannot write, whatever else is true of the arguments. That is what keeps
    "only a person runs this" checkable in code rather than a comment: an automated caller
    would have to pass the flag, and the only place that passes it is main(), after --apply
    and an exactly matching --confirm-scope were both given.

    Three further arguments exist because a library rebuild is measured in hours, not in one
    sitting, and every one of them is honoured only *between* documents -- never inside one.
    A document is the unit an interruption has to leave whole:

    'incremental'
        Plan from the registry first -- read each source, split it with the live chunker,
        compare digests -- and leave alone every document whose published digest still equals
        its source. That is the difference between "one document was edited" costing one
        document's embeddings and costing the library's. It is also the resume mechanism: the
        next run plans from what the previous one published, so it picks up at the first
        document still behind, with no journal file to find and no partial state to clear.
    'stop_after' / 'time_budget_seconds'
        Spend at most N documents' worth of work, or S seconds of wall clock, then report how
        many are left. An off-peak window is a number of seconds, and a rebuild that cannot
        stop on a boundary is a rebuild somebody has to finish by hand.
    'clock'
        Injected so the budget above is testable without waiting for it. Default monotonic.
    """
    report = {
        "scope": str(scope),
        "embedding_model": scope.embedding_model or SCOPE_UNKNOWN,
        "dimension": scope.dimension if scope.dimension else SCOPE_UNKNOWN,
        "apply": bool(apply),
        "incremental": bool(incremental),
        "planned": 0,
        "rebuilt": 0,
        "skipped": 0,
        "failed": 0,
        "planned_only": 0,
        "unchanged": 0,
        "attempted": 0,
        "remaining": 0,
        "stopped_at": "",
        "embedded_texts": 0,
        "planned_documents": 0,
        "planned_embeddings": 0,
        "cross_dimension_vectors_before": 0,
        "cross_dimension_vectors_after": 0,
        "zero_vectors_before": 0,
        "documents": [],
        "retained": [],
        "codes": [],
        "aborted": "",
    }
    if apply and not manual:
        raise RebuildRefused(
            "an index rebuild is a manual operation: manual=True is only passed by a human "
            "invoking scripts/rebuild_index.py with --apply and --confirm-scope"
        )
    if apply:
        reason = probe_embedder(retriever.embedding, scope)
        if reason:
            raise EmbedderUnavailable(f"refusing to rebuild: {reason}")
        # The probe is one text the embedder really was asked for. Counting it keeps
        # embedded_texts an answer rather than an estimate: it is what a deterministic
        # embedder will have been handed by the end of this run, probe included.
        report["embedded_texts"] += 1

    chunker = chunk_texts if callable(chunk_texts) else splitter_chunk_texts(retriever)
    entries: dict = {}
    if incremental:
        if chunker is None:
            raise RebuildRefused(
                "an incremental rebuild needs the chunker the write path uses so its digests "
                "are comparable, and this vector store exposes none: run it without "
                "--incremental, which rebuilds everything it is pointed at"
            )
        plan = plan_index_refresh(
            targets,
            registry=publisher.registry,
            load_text=load_text,
            chunk_texts=chunker,
            resolve_path=resolve_storage_path,
            documents_dir=documents_dir,
            scope=scope,
        )
        entries = plan.by_filename()
        report["planned_documents"] = plan.rebuild_documents
        report["planned_embeddings"] = plan.embedded_texts

    report["planned"] = len(targets)
    started = clock()
    for row in targets:
        filename = str(row.get("filename") or "")
        entry = entries.get(filename) if incremental else None
        if entry is not None and entry.reason == PLAN_REASON_MATCHES:
            # A document that needs nothing is not allowed to spend the budget either: the
            # point of planning is that the cheap answer is the common one.
            planned_result = rebuild_document(
                row=row,
                retriever=retriever,
                publisher=publisher,
                scope=scope,
                load_text=load_text,
                documents_dir=documents_dir,
                apply=apply,
                planned=entry,
                chunk_texts=chunk_texts,
            )
            report["documents"].append(planned_result)
            report["unchanged"] += 1
            continue
        if stop_after is not None and report["attempted"] >= int(stop_after):
            report["stopped_at"] = "stop_after=" + str(stop_after)
            break
        if time_budget_seconds is not None and (clock() - started) >= float(time_budget_seconds):
            report["stopped_at"] = "time_budget_seconds=" + str(time_budget_seconds)
            break
        report["attempted"] += 1
        result = rebuild_document(
            row=row,
            retriever=retriever,
            publisher=publisher,
            scope=scope,
            load_text=load_text,
            documents_dir=documents_dir,
            apply=apply,
            planned=entry,
            chunk_texts=chunk_texts,
        )
        report["documents"].append(result)
        report["embedded_texts"] += int(result.get("embedded_texts") or 0)
        before = result.get("before") or {}
        after = result.get("after") or {}
        report["cross_dimension_vectors_before"] += int(before.get("wrong_dimension") or 0)
        report["cross_dimension_vectors_after"] += int(after.get("wrong_dimension") or 0)
        report["zero_vectors_before"] += int(before.get("zero_vectors") or 0)
        if not apply:
            if result["status"] == "skipped":
                report["skipped"] += 1
            else:
                report["planned_only"] += 1
            continue
        if result["status"] == "rebuilt":
            report["rebuilt"] += 1
            continue
        report["failed"] += 1
        if result["reason"] != "source_missing":
            # A document whose source cannot be found was never touched, so it is not a
            # rebuild failure. Anything else means the store is now in a state nobody asked
            # for -- usually its vectors deleted and not replaced -- and the run stops there
            # rather than doing the same to the remaining documents.
            report["aborted"] = filename + ": " + result["reason"]
            break
    # What a resume has to do next. Documents that were planned as unchanged are already
    # finished, and a document that failed counts as remaining, because it is.
    report["remaining"] = max(0, len(targets) - report["attempted"] - report["unchanged"])
    filenames = [str(row.get("filename")) for row in targets]
    report["retained"] = retained_versions(publisher.registry, filenames)
    report["codes"] = list(publisher.registry.embedding_drift().codes)
    return report


def retained_versions(registry: IndexRegistry, filenames) -> list[dict]:
    """What is live now, and what is still on disk behind it.

    A rebuild that destroyed its own rollback point would be indistinguishable from a
    migration, so the report answers this question whether or not anyone thinks to ask it:
    a superseded version that is gone is a rebuild that cannot be undone.
    """
    from app.rag.indexing import document_index_id

    retained: list[dict] = []
    for filename in filenames:
        history = registry.history(document_index_id(str(filename)))
        published = [version for version in history if version.status == "published"]
        retained.append(
            {
                "filename": str(filename),
                "versions": len(history),
                "superseded": sum(1 for version in history if version.status == "superseded"),
                "current": published[0].index_version_id if published else "",
                "current_scope": str(published[0].scope) if published else SCOPE_UNKNOWN,
            }
        )
    return retained


def _census_fields(census: dict | None, *, list_limit: int = CENSUS_LIST_LIMIT) -> dict:
    """The census half of a ``--status`` report: two counters, and which documents are behind them.

    The named lists are cut to ``list_limit`` because this dict is what gets printed --
    ``write_census_report`` keeps the whole of them -- while the two counters always cover
    whatever the scan covered. ``census_measurable`` is deliberately *not* another spelling of
    "the counters read zero": a census that could not look leaves both counters null, so the
    two cannot be printed as one line and read as the other.
    """
    seen = dict(census) if census else library_vector_census(None, 0)
    zero_rows = list(seen.get("zero_vector_documents") or [])
    cross_rows = list(seen.get("cross_dimension_vector_documents") or [])
    unmeasurable = list(seen.get("unmeasurable_documents") or [])
    limit = max(0, int(list_limit))
    return {
        "zero_vectors_before": seen.get("zero_vectors"),
        "cross_dimension_vectors_before": seen.get("cross_dimension_vectors"),
        "census_measurable": bool(seen.get("measurable")),
        "census_documents": int(seen.get("documents") or 0),
        "census_vectors_read": int(seen.get("vectors_read") or 0),
        "census_store_vectors": seen.get("store_vectors"),
        "census_page_size": int(seen.get("page_size") or 0),
        "census_pages_read": int(seen.get("pages_read") or 0),
        "census_non_sequence_vectors": int(seen.get("non_sequence_vectors") or 0),
        "census_elapsed_seconds": seen.get("elapsed_seconds"),
        "census_source": str(seen.get("source") or ""),
        "census_reason": str(seen.get("reason") or ""),
        "census_report_path": "",
        "zero_vector_documents": zero_rows[:limit],
        "zero_vector_documents_total": len(zero_rows),
        "cross_dimension_vector_documents": cross_rows[:limit],
        "cross_dimension_vector_documents_total": len(cross_rows),
        "unmeasurable_documents": unmeasurable[:limit],
        "unmeasurable_documents_total": len(unmeasurable),
    }


def status_report(*, registry: IndexRegistry, scope: EmbeddingScope, targets,
                  census: dict | None = None, list_limit: int = CENSUS_LIST_LIMIT) -> dict:
    """The read-only answer: what is current, under which profile, and what would change.

    The vector census rides along with it (跟进单 §61 / R125), because this is the entry point
    the operator is told to run. The counting has been in this file since R22 -- it lives in
    ``vector_census``, reached once per document from ``rebuild_document`` -- but nothing
    connected it to ``--status``, so the runbook's U3 step took two fields that were never
    there, and the printed report answered them with the ``0`` that an absent key defaults to.

    The existing keys, in the existing order, are untouched: the runbook and the board read
    this shape, and 跟进单 R22's test pins several of them by name.
    """
    drift = registry.embedding_drift()
    stale = []
    for row in targets:
        from app.rag.indexing import document_index_id

        index_id = document_index_id(str(row.get("filename")))
        try:
            current = registry.current(index_id)
        except KeyError:
            stale.append(str(row.get("filename")))
            continue
        if current.scope != scope:
            stale.append(str(row.get("filename")))
    report = {
        "scope": str(scope),
        "drifted": drift.drifted,
        "codes": list(drift.codes),
        "unknown_scope_versions": list(drift.unknown_index_version_ids),
        "indexes": len(registry.index_ids()),
        "documents": len(targets),
        "documents_needing_rebuild": len(stale),
        "stale_documents": sorted(stale),
    }
    report.update(_census_fields(census, list_limit=list_limit))
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rebuild_index.py",
        description="Rebuild document vectors under the configured embedding profile (manual only).",
    )
    parser.add_argument("--status", action="store_true", help="report only; never writes")
    parser.add_argument("--apply", action="store_true", help="actually rebuild; requires --confirm-scope")
    parser.add_argument(
        "--confirm-scope",
        default="",
        help='exactly the "<model>/<dimension>" that will be written, e.g. "nomic-embed-text/768"',
    )
    parser.add_argument("--document", action="append", default=[], help="limit the rebuild to one filename (repeatable)")
    parser.add_argument("--only-stale", action="store_true", help="skip documents whose current version already matches the profile")
    parser.add_argument("--metadata-path", default=None, help="index metadata file (defaults to INDEX_METADATA_PATH)")
    parser.add_argument("--documents-dir", default=None, help="where stored documents live (defaults to DOCUMENTS_DIR)")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="re-embed only the documents whose stored chunks no longer match their source; "
        "also how an interrupted rebuild resumes, since the plan reads what is published now",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=None,
        help="stop after this many documents have been started (requires --apply)",
    )
    parser.add_argument(
        "--time-budget-seconds",
        type=float,
        default=None,
        help="stop once this many seconds of work have been spent; the boundary is between "
        "documents, so the run is never left half-done (requires --apply)",
    )
    parser.add_argument(
        "--census-page-size",
        type=int,
        default=CENSUS_PAGE_SIZE,
        help="stored vectors read per page by the --status vector census; smaller pages use "
        "less memory and send more requests (default: %(default)s)",
    )
    parser.add_argument(
        "--census-list-limit",
        type=int,
        default=CENSUS_LIST_LIMIT,
        help="how many named documents of each census list reach stdout; the full lists are "
        "written to --census-report (default: %(default)s)",
    )
    parser.add_argument(
        "--census-report",
        default=None,
        help="where the full census lists are written (defaults to a file in the system temp "
        "directory, i.e. outside the repository)",
    )
    parser.add_argument(
        "--chroma-dir",
        default=None,
        help="vector store directory the --status census reads (defaults to CHROMA_DIR, then ./chroma_db)",
    )
    parser.add_argument(
        "--chroma-collection",
        default=None,
        help="collection the --status census reads (defaults to CHROMA_COLLECTION, then enterprise_docs)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scope = configured_embedding_scope()
    manual = False

    # Every argument is judged before a registry, a catalog or a vector store is opened: a
    # mistyped invocation must be a non-event, not a half-run rebuild.
    if args.apply:
        try:
            confirmed = scope_from_text(args.confirm_scope)
        except RebuildRefused as exc:
            print(f"refusing: {exc}", file=sys.stderr)
            return EXIT_USAGE
        if confirmed.key != scope.key:
            print(
                f"refusing: --confirm-scope {confirmed} is not the configured profile {scope}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        if not invoked_by_human():
            print(
                "refusing: the rebuild only runs when scripts/rebuild_index.py is invoked as a "
                f"command (argv[0]={sys.argv[0] if sys.argv else ''})",
                file=sys.stderr,
            )
            return EXIT_USAGE
        manual = True
    elif args.confirm_scope:
        print("refusing: --confirm-scope only means anything together with --apply", file=sys.stderr)
        return EXIT_USAGE
    for name, value in (("--max-documents", args.max_documents),
                        ("--time-budget-seconds", args.time_budget_seconds)):
        if value is None:
            continue
        # Judged in this order on purpose: a negative budget is a broken invocation whether
        # or not --apply came with it, and it must never reach a store.
        if value < 0:
            print(f"refusing: {name} must not be negative", file=sys.stderr)
            return EXIT_USAGE
        if not args.apply:
            print(f"refusing: {name} only means anything together with --apply", file=sys.stderr)
            return EXIT_USAGE
    if args.census_page_size < 1:
        print("refusing: --census-page-size must be at least 1", file=sys.stderr)
        return EXIT_USAGE
    if args.census_list_limit < 0:
        print("refusing: --census-list-limit must not be negative", file=sys.stderr)
        return EXIT_USAGE

    metadata_path = args.metadata_path or default_metadata_path()
    registry = IndexRegistry(metadata_path, scope=scope)

    from app.documents.catalog import DOCUMENTS_DIR, current_documents

    documents_dir = args.documents_dir or DOCUMENTS_DIR
    targets = documents_to_rebuild(current_documents, only_names=args.document or None)

    if args.status:
        # The census is read off the live store, a page at a time, and it is the only thing
        # this path asks of it: no embedder, no publisher, no model call. A store that will
        # not open leaves the counters null and says why, which is the difference between an
        # unmeasured gate and a passed one.
        store, open_reason = open_census_store(args.chroma_dir, args.chroma_collection)
        census = library_vector_census(
            store,
            scope.dimension,
            page_size=args.census_page_size,
            catalog_filenames=[row.get("filename") for row in targets],
            unavailable_reason=open_reason,
        )
        report = status_report(
            registry=registry, scope=scope, targets=targets, census=census,
            list_limit=args.census_list_limit,
        )
        report["census_report_path"] = write_census_report(census, path=args.census_report)
        _emit(report, as_json=args.json)
        return EXIT_OK

    if args.only_stale:
        from app.rag.indexing import document_index_id

        keep = []
        for row in targets:
            try:
                current = registry.current(document_index_id(str(row.get("filename"))))
            except KeyError:
                keep.append(row)
                continue
            if current.scope != scope:
                keep.append(row)
        targets = keep

    from app.rag.loader import load_document
    from app.rag.retriever import DocumentRetriever

    retriever = DocumentRetriever()
    publisher = IndexPublisher(registry, store=PostgresIndexStore(available=lambda: True))
    try:
        report = run_rebuild(
            targets=targets,
            retriever=retriever,
            publisher=publisher,
            scope=scope,
            documents_dir=documents_dir,
            load_text=load_document,
            apply=bool(args.apply),
            manual=manual,
            incremental=bool(args.incremental),
            stop_after=args.max_documents,
            time_budget_seconds=args.time_budget_seconds,
        )
    except RebuildRefused as exc:
        print(f"rebuild refused: {exc}", file=sys.stderr)
        return EXIT_EMBEDDER_UNUSABLE
    report["scope"] = str(scope)
    _emit(report, as_json=args.json)
    if report["aborted"]:
        print(f"rebuild stopped early: {report['aborted']}", file=sys.stderr)
        return EXIT_REBUILD_FAILED
    if report["failed"]:
        return EXIT_REBUILD_FAILED
    return EXIT_OK


def _emit(report: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return
    for line in report_lines(report):
        print(line)


def _count_text(value) -> str:
    """How a counter that was never measured reads, so it cannot be mistaken for a zero.

    Before the census was wired in, ``--status`` printed ``zero_vectors_before=0`` purely
    because the key was absent and the line had a default: an unmeasured gate reading exactly
    like a passed one. Null now means nobody looked, and it prints that way.
    """
    return "unmeasurable" if value is None else str(value)


def _census_list_lines(report: dict) -> list[str]:
    """The named documents behind each census counter, one line each, preview only.

    The full lists are in the file ``census_full_lists`` names; these lines exist so the
    answer is readable without opening it, and so a document that could not be measured is
    named as unmeasurable instead of being missing from a list that looks complete.
    """
    lines: list[str] = []
    for row in report.get("zero_vector_documents") or []:
        lines.append(
            f"  zero_vectors {row['filename']}: {row['zero_vectors']} of "
            f"{row['vectors']} stored vectors"
        )
    for row in report.get("cross_dimension_vector_documents") or []:
        lines.append(
            f"  cross_dimension {row['filename']}: {row['cross_dimension_vectors']} of "
            f"{row['vectors']} stored vectors, widths={row.get('widths')}"
        )
    for row in report.get("unmeasurable_documents") or []:
        lines.append(f"  unmeasurable {row['filename']}: {row['reason']}")
    for key in (
        "zero_vector_documents",
        "cross_dimension_vector_documents",
        "unmeasurable_documents",
    ):
        shown = len(report.get(key) or [])
        total = int(report.get(f"{key}_total") or 0)
        if total > shown:
            lines.append(f"  {key}: {total} in total, the first {shown} are shown above")
    return lines


def report_lines(report: dict) -> list[str]:
    """The completion criteria, in the order an operator asks for them.

    How much was rebuilt, which version is in effect now, and whether the previous versions
    are still there: these three questions are why this command exists, so they are printed
    rather than left to be inferred from a stack of ids.
    """
    lines = [
        f"scope={report.get('scope')}",
        f"mode={'apply' if report.get('apply') else 'dry-run'}",
        f"planned={report.get('planned', 0)} rebuilt={report.get('rebuilt', 0)} "
        f"skipped={report.get('skipped', 0)} failed={report.get('failed', 0)}",
        f"planned_only={report.get('planned_only', 0)}",
        f"cross_dimension_vectors before={_count_text(report.get('cross_dimension_vectors_before', 0))} "
        f"after={_count_text(report.get('cross_dimension_vectors_after', 0))}",
        f"zero_vectors_before={_count_text(report.get('zero_vectors_before', 0))}",
        f"embedded_texts={report.get('embedded_texts', 0)} "
        f"attempted={report.get('attempted', 0)} remaining={report.get('remaining', 0)} "
        f"stopped_at={report.get('stopped_at') or 'end'}",
    ]
    if report.get("census_measurable") is not None:
        # The census half of a --status report, printed apart from the two lines above: a
        # rebuild report carries no census of its own, and the coverage numbers are what tell
        # an operator whether those two counters measured the library or gave up on it.
        lines.append(
            f"drift={'yes' if report.get('drifted') else 'no'} "
            f"indexes={report.get('indexes', 0)} "
            f"catalog_documents={report.get('documents', 0)} "
            f"needs_rebuild={report.get('documents_needing_rebuild', 0)}"
        )
        stale = list(report.get("stale_documents") or [])
        for name in stale[:CENSUS_LIST_LIMIT]:
            lines.append(f"  needs_rebuild {name}")
        if len(stale) > CENSUS_LIST_LIMIT:
            lines.append(
                f"  needs_rebuild: {len(stale)} in total, the first {CENSUS_LIST_LIMIT} are shown above"
            )
        lines.append(
            f"census={'measurable' if report['census_measurable'] else 'UNMEASURABLE'} "
            f"vectors_read={report.get('census_vectors_read', 0)}"
            f"/{_count_text(report.get('census_store_vectors'))} "
            f"pages={report.get('census_pages_read', 0)} "
            f"page_size={report.get('census_page_size', 0)} "
            f"documents={report.get('census_documents', 0)} "
            f"elapsed={report.get('census_elapsed_seconds', 0)}s"
        )
        if report.get("census_reason"):
            lines.append(f"census_reason={report['census_reason']}")
        if report.get("census_source"):
            lines.append(f"census_source={report['census_source']}")
        lines.extend(_census_list_lines(report))
        if report.get("census_report_path"):
            lines.append(f"census_full_lists={report['census_report_path']}")
    if report.get("incremental"):
        # The incremental answer is the one an operator needs before starting a long job: how
        # much of the library this run really re-embeds, and what that will cost in vectors.
        lines.append(
            f"incremental=on documents={report.get('planned', 0)} "
            f"to_rebuild={report.get('planned_documents', 0)} "
            f"unchanged={report.get('unchanged', 0)} "
            f"predicted_embeddings={report.get('planned_embeddings', 0)}"
        )
    if report.get("codes") is not None:
        lines.append(f"drift_codes={','.join(report['codes']) or 'none'}")
    # A --status report answers "documents" with a count and a rebuild report with the
    # per-document list, and this loop belongs to the rebuild shape. Before R125 the printed
    # --status died right here -- TypeError: 'int' object is not iterable, reproduced on the
    # owner's build at rev 27c676f -- which is also why §8.4's promise that dropping --json
    # still prints the two counters could never have been true.
    stored = report.get("documents")
    for document in stored if isinstance(stored, list) else []:
        detail = f"  {document['filename']}: {document['status']}"
        if document.get("index_version_id"):
            detail += f" current={document['index_version_id']}"
        if document.get("previous_index_version_id"):
            detail += f" previous={document['previous_index_version_id']}"
        if document.get("chunk_count"):
            detail += f" chunks={document['chunk_count']}"
        if document.get("reason"):
            detail += f" reason={document['reason']}"
        lines.append(detail)
    for document in report.get("retained", []):
        detail = (
            f"  {document['filename']}: versions={document['versions']} "
            f"superseded={document['superseded']}"
        )
        if document.get("current"):
            detail += f" current={document['current']} current_scope={document['current_scope']}"
        else:
            detail += " current=none"
        lines.append(detail)
    if report.get("aborted"):
        lines.append(f"aborted={report['aborted']}")
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
