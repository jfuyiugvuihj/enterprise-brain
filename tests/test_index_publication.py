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
