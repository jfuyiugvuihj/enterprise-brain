"""R700: a spreadsheet uploaded as a dataset also becomes a knowledge-base document.

The file that arrives at POST /api/v1/upload-excel has always been a knowledge-base
*type*: `.xlsx` and `.csv` sit in the whitelist of `app/documents/file_security.py`, and
`app/rag/loader.py` reads both through `app/rag/spreadsheets.py`. What never happened is
the ingest: the dataset route registered the file as a dataset and stopped there, so a
table uploaded from the data entry point was invisible to retrieval.

This module closes that gap without building a second ingest leg. Every exit it uses is
one the knowledge-base route (`app/api/v1/chat.py::upload_document`) already walks, in
the same order and with the same arguments:

1. `app.rag.loader.load_document()` -- the repository's only document-text exit. Its
   spreadsheet blocks are `app/rag/tables.py` `TableBlock` objects rendered by
   `tables.render_tables()`, so the table channel stays one implementation (R700
   judgement 3: no parallel renderer).
2. `app.documents.index_policy.evaluate_index_eligibility()` -- the R49 "is this worth
   indexing" judgment, asked before any embedding is spent, exactly where the
   knowledge-base route asks it.
3. `DocumentRetriever.add_document()` -- the sanctioned vector write point. This module
   opens no store, no client and no new write call: the switch in `app/rag/indexing.py`
   decides which engine receives the rows, so the legacy directory gets no new writer
   here (R700 judgement 1, and AGENTS.md's standing rule).
4. `app.agents.tools.rebuild_bm25()` -- the keyword corpus the same route rebuilds, so
   the document is visible to the keyword leg and not only to the vector leg.

One deliberate difference from the knowledge-base route: this one asks the model
server's own registry whether the embedding model the vector leg is about to call is on
it, and skips with an existing reason code when it is not. The knowledge-base route can
afford a 500 at that point; this route cannot, because the dataset half of the upload
has already succeeded and its documented response shape must not change (R700
judgement 2). The skip goes to the server log with the code the embedding client itself
would have produced.

What this module deliberately does NOT do: write a document-catalogue row or publish an
index version. Those belong to the knowledge-base route's persistence helpers, whose
storage coordinates are the knowledge directory, while a dataset file lives in `DATA_DIR`
-- deciding which root owns the bytes is ticket R687's zero-copy question, not this
ticket's to settle. Recorded in docs/testing/r700-2026-10-06.md.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from app.common.logger import logger
from app.common.monitoring import (
    _embedding_model_name,
    _model_tags_match,
    _registered_local_models,
)
from app.common.policy import _classification_level
from app.documents.index_policy import (
    INDEX_STATUS_EXCLUDED,
    INDEX_STATUS_INDEXED,
    classify_index_refusal,
    evaluate_index_eligibility,
    index_notice,
)

#: The knowledge-base half of one dataset upload, reported to the log only: the dataset
#: response carries none of it, because a second life for the file must not become a
#: second contract for the route. `indexed` and `excluded` are the catalogue's own
#: index-status spellings, imported rather than restated.
STATUS_INDEXED = INDEX_STATUS_INDEXED
STATUS_EXCLUDED = INDEX_STATUS_EXCLUDED
STATUS_SKIPPED = "skipped"
STATUS_UNAVAILABLE = "unavailable"
STATUS_FAILED = "failed"

#: The level an unlabelled upload is indexed at -- the ratified R467 default the
#: knowledge-base route takes from its own form field, not a value invented here.
DEFAULT_CLASSIFICATION_LEVEL = 1

#: The two endpoint names this module has to know to ask the vector leg's own server
#: what is installed on it. Read off the embedding client, never re-resolved from env.
EMBEDDINGS_PATH_SUFFIX = "/api/embeddings"
REGISTRY_PATH_SUFFIX = "/api/tags"


def _receipt(status: str, reason: str = "", message: str = "") -> dict[str, str]:
    return {"status": status, "reason": reason, "message": message}


def classification_level_for(value: Any) -> int:
    """One dataset classification -> the level the retrieval filters compare against.

    `_classification_level` in `app/common/policy.py` is the platform's single ranking of
    those words (a dataset record spells them `internal`, a document row spells them 1-4);
    restating the table here is exactly the drift R472 registered against.
    """
    level = _classification_level(value)
    return DEFAULT_CLASSIFICATION_LEVEL if level is None else int(level)


def registry_url_for(retriever: Any) -> str:
    """The registry endpoint of the server the vector leg would call, or "" if unknown.

    Read from the embedding client's own `api_url` instead of resolving environment
    variables a second time: "is the model installed" has to be asked of the same server
    `add_document` is about to bother. An unrecognisable shape answers "", and "" means
    unknown -- which, per the rule `monitoring._embedding_model_name` already follows,
    is never allowed to mean "skip".
    """
    api_url = str(getattr(getattr(retriever, "embedding", None), "api_url", "") or "")
    base = api_url.removesuffix(EMBEDDINGS_PATH_SUFFIX)
    return f"{base}{REGISTRY_PATH_SUFFIX}" if base else ""


def embedding_leg_refusal_reason(model_name: str, registered: list[str]) -> str:
    """Pure predicate over one registry reading: "" when the leg can be used.

    Names are compared with `_model_tags_match`, the health report's own rule for matching
    a pinned model name against a reported tag (`nomic-embed-text` versus
    `nomic-embed-text:latest`), so this cannot answer differently from the health page.
    """
    if not model_name:
        return ""
    if any(_model_tags_match(model_name, name) for name in registered):
        return ""
    from app.rag.retriever import REASON_MODEL_MISSING

    return REASON_MODEL_MISSING


def _last_embedding_reason(retriever: Any) -> str:
    """The reason code the embedding client last produced, "" when it has none."""
    last = getattr(getattr(retriever, "embedding", None), "last_error", None) or {}
    return str(last.get("reason") or "")


def _registry_refusal_reason(retriever: Any, registry_fetch: Callable[[str], dict] | None) -> str:
    """Ask the local model server what it has, the way model discovery already asks.

    The transport is `app/common/model_config._fetch_registry` -- one request, its own
    timeout, no socket when nothing is listening -- injectable because the answer decides
    whether an upload spends embedding time. Two answers, both already in the
    vocabulary: the server did not answer (`ollama_unreachable`), or it answered and the
    embedding model is not on it (`model_missing`).
    """
    url = registry_url_for(retriever)
    if not url:
        return ""
    from app.rag.retriever import REASON_UNREACHABLE

    fetch = registry_fetch
    if fetch is None:
        from app.common.model_config import _fetch_registry

        fetch = _fetch_registry
    try:
        payload = fetch(url)
    except Exception as exc:  # noqa: BLE001 - a silent skip is not an option, so name it
        logger.warning(f"[Data] embedding registry unreadable: {type(exc).__name__}")
        return REASON_UNREACHABLE
    return embedding_leg_refusal_reason(_embedding_model_name(), _registered_local_models(payload))


def _load_body(storage_path: str, display_filename: str) -> str:
    """One call into the repository's only document-text exit.

    The import is inside the function on purpose: `app.documents` stays off the pdf/ocr
    import graph until an upload actually needs a parser, and the exit stays the one the
    knowledge-base route calls -- same `display_name` argument, so the anchor's first
    field is the name the customer used, not the stored uuid.
    """
    from app.rag.loader import load_document

    return load_document(storage_path, display_name=display_filename)


async def _rebuild_keyword_corpus() -> None:
    """Rebuild the keyword corpus through the same call the knowledge-base route submits.

    That route hands it to a background executor; awaiting it here means one dataset
    upload leaves one observable state behind -- indexed, or the log says which of the
    two legs failed -- and no task is still running when the response is already sent.
    A corpus failure never retracts the dataset: the rows are in the index either way.
    """
    from app.agents.tools import rebuild_bm25

    try:
        await asyncio.to_thread(rebuild_bm25)
    except Exception as exc:  # noqa: BLE001 - logged, because the index itself took the rows
        logger.warning(f"[Data] keyword corpus rebuild failed: {exc}")


async def index_dataset_copy(
    *,
    display_filename: str,
    storage_path: str | Path,
    department: str,
    classification: Any,
    retriever: Any,
    registry_fetch: Callable[[str], dict] | None = None,
) -> dict[str, str]:
    """Send one already-stored dataset file down the knowledge-base leg.

    Nothing here rolls the dataset back and nothing here changes what the route answers:
    the return value is for the log and for the operator who has to explain why a table
    is not findable. Every branch returns a receipt, so the caller cannot mistake "not
    attempted" for "attempted and accepted".
    """
    try:
        size_bytes = Path(storage_path).stat().st_size
        content = await asyncio.to_thread(_load_body, str(storage_path), display_filename)
    except Exception as exc:  # noqa: BLE001 - a dataset stays registered even if it cannot be read
        logger.warning(f"[Data] knowledge-base parse failed: {display_filename}: {exc}")
        return _receipt(STATUS_FAILED, "parse_failed", str(exc))

    eligibility = evaluate_index_eligibility(content, size_bytes=size_bytes)
    if not eligibility.eligible:
        logger.warning(
            f"[Data] knowledge-base index excluded: {display_filename} "
            f"reason={eligibility.reason} metrics={eligibility.metrics}"
        )
        return _receipt(STATUS_EXCLUDED, eligibility.reason, eligibility.message)

    refusal = _registry_refusal_reason(retriever, registry_fetch)
    if refusal:
        logger.warning(
            f"[Data] knowledge-base index not attempted for {display_filename}: "
            f"embedding leg answers {refusal}; the dataset registration stands"
        )
        return _receipt(STATUS_UNAVAILABLE, refusal, "")

    level = classification_level_for(classification)
    try:
        accepted, message = await asyncio.to_thread(
            retriever.add_document, display_filename, content, level, department or None
        )
    except Exception as exc:  # noqa: BLE001 - the vector leg fails closed with a reason code
        reason = _last_embedding_reason(retriever) or type(exc).__name__
        logger.error(f"[Data] knowledge-base index failed: {display_filename} reason={reason}")
        return _receipt(STATUS_FAILED, reason, str(exc))

    if not accepted:
        skipped = classify_index_refusal(message)
        logger.info(f"[Data] knowledge-base index skipped: {display_filename} reason={skipped}")
        return _receipt(STATUS_SKIPPED, skipped, index_notice(skipped))

    await _rebuild_keyword_corpus()
    logger.info(f"[Data] knowledge-base index accepted: {display_filename} level={level}")
    return _receipt(STATUS_INDEXED, "", str(message))
