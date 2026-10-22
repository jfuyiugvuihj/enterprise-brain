from __future__ import annotations

import pytest


def test_index_registry_publishes_validated_version_and_rolls_back(tmp_path):
    from app.rag.indexing import IndexRegistry

    registry = IndexRegistry(tmp_path / "indexes.json")
    first = registry.create_version(
        index_id="knowledge-base",
        source_version_id="document:v1",
        backend="chroma",
        chunk_count=3,
        checksum="a" * 64,
    )
    registry.publish(first.index_version_id)
    second = registry.create_version(
        index_id="knowledge-base",
        source_version_id="document:v2",
        backend="pgvector",
        chunk_count=4,
        checksum="b" * 64,
    )
    registry.publish(second.index_version_id)

    assert registry.current("knowledge-base").index_version_id == second.index_version_id
    registry.rollback("knowledge-base", first.index_version_id)
    assert registry.current("knowledge-base").index_version_id == first.index_version_id


def test_index_registry_rejects_unvalidated_or_invalid_versions(tmp_path):
    from app.rag.indexing import IndexRegistry

    registry = IndexRegistry(tmp_path / "indexes.json")
    version = registry.create_version(
        index_id="knowledge-base",
        source_version_id="document:v1",
        backend="chroma",
        chunk_count=0,
        checksum="c" * 64,
    )
    with pytest.raises(ValueError, match="chunk_count"):
        registry.publish(version.index_version_id)
    with pytest.raises(KeyError):
        registry.rollback("knowledge-base", "missing")


# ---------------------------------------------------------------- retirement versions
def test_a_retirement_version_publishes_zero_chunks_and_supersedes_the_current(tmp_path):
    from app.rag.indexing import IndexRegistry

    registry = IndexRegistry(tmp_path / "indexes.json")
    current = registry.create_version(
        index_id="document:policy.txt",
        source_version_id="policy.txt|v1",
        backend="chroma",
        chunk_count=3,
        checksum="d" * 64,
    )
    registry.publish(current.index_version_id)

    tombstone = registry.create_version(
        index_id="document:policy.txt",
        source_version_id="policy.txt|v1",
        backend="chroma",
        chunk_count=0,
        checksum="e" * 64,
        retirement=True,
    )
    registry.publish(tombstone.index_version_id)

    assert registry.current("document:policy.txt").index_version_id == tombstone.index_version_id
    assert registry.current("document:policy.txt").retirement is True
    assert registry._versions[current.index_version_id].status == "superseded"


def test_a_retirement_version_may_not_carry_chunks(tmp_path):
    from app.rag.indexing import IndexRegistry

    registry = IndexRegistry(tmp_path / "indexes.json")
    with pytest.raises(ValueError, match="zero chunks"):
        registry.create_version(
            index_id="document:policy.txt",
            source_version_id="policy.txt|v1",
            backend="chroma",
            chunk_count=2,
            checksum="f" * 64,
            retirement=True,
        )


def test_discard_forgets_a_version_that_never_published(tmp_path):
    from app.rag.indexing import IndexRegistry

    registry = IndexRegistry(tmp_path / "indexes.json")
    building = registry.create_version(
        index_id="document:policy.txt",
        source_version_id="policy.txt|v1",
        backend="chroma",
        chunk_count=1,
        checksum="a" * 64,
    )

    registry.discard(building.index_version_id)

    assert building.index_version_id not in registry._versions
    with pytest.raises(KeyError):
        registry.current("document:policy.txt")


# ----------------------------------------------------------------- the publisher
def test_the_publisher_rolls_back_when_a_later_step_fails(tmp_path, monkeypatch):
    from app.rag.indexing import (
        DocumentIndexPublication,
        IndexPublicationError,
        IndexPublisher,
        IndexRegistry,
        document_index_id,
    )

    registry = IndexRegistry(tmp_path / "indexes.json")
    index_id = document_index_id("policy.txt")
    first = registry.create_version(
        index_id=index_id,
        source_version_id="policy.txt|v1",
        backend="chroma",
        chunk_count=2,
        checksum="a" * 64,
    )
    registry.publish(first.index_version_id)
    publisher = IndexPublisher(registry, store=None)

    def refuse(index_version_id):
        raise RuntimeError("the index metadata file is read only")

    monkeypatch.setattr(registry, "publish", refuse)
    publication = DocumentIndexPublication(
        filename="policy.txt",
        version=2,
        owner_id="alice",
        classification=1,
        department="finance",
        chunks=("one", "two"),
    )

    with pytest.raises(IndexPublicationError) as exc_info:
        publisher.publish(publication)

    assert exc_info.value.stage == "publish"
    assert registry.current(index_id).index_version_id == first.index_version_id
    assert registry._versions[first.index_version_id].status == "published"
    assert len(registry._versions) == 1


def test_the_publisher_replaces_the_previous_version_when_every_step_succeeds(tmp_path):
    from app.rag.indexing import (
        DocumentIndexPublication,
        IndexPublisher,
        IndexRegistry,
        document_index_id,
    )

    registry = IndexRegistry(tmp_path / "indexes.json")
    publisher = IndexPublisher(registry, store=None)
    index_id = document_index_id("policy.txt")

    first = publisher.publish(
        DocumentIndexPublication(filename="policy.txt", version=1, chunks=("one",))
    )
    second = publisher.publish(
        DocumentIndexPublication(filename="policy.txt", version=2, chunks=("one", "two"))
    )

    assert second.previous_index_version_id == first.index_version_id
    assert second.chunk_count == 2
    assert second.status == "published"
    assert second.mirrored is False
    assert registry.current(index_id).index_version_id == second.index_version_id
    assert registry._versions[first.index_version_id].status == "superseded"
    assert second.as_dict()["checksum"] == second.checksum


def test_apply_publishes_neither_an_empty_index_nor_a_pending_retirement(tmp_path):
    from app.rag.indexing import DocumentIndexPublication, IndexPublisher, IndexRegistry

    publisher = IndexPublisher(IndexRegistry(tmp_path / "indexes.json"), store=None)

    empty = DocumentIndexPublication(filename="policy.txt", version=1, chunks=())
    retirement = DocumentIndexPublication(
        filename="policy.txt", version=1, chunks=(), retirement=True
    )

    assert publisher.apply(empty) is None
    assert publisher.apply(retirement) is None
    assert publisher.registry._versions == {}
