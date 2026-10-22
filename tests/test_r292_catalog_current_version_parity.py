"""R292 - one leg may not decide "current version" from the filesystem.

The catalog stores several versions of one logical document and lists it once. Which
stored version that one row describes used to be answered twice, differently:

* the database leg let ``ORDER BY filename, version DESC`` push the newest version into
  the first slot of every filename, and ``setdefault``'s first-write-wins collected it;
* the offline leg had no version ordering at all, so first-write-wins collected the first
  row the enumeration happened to hand over - ``name__vN.ext`` in NTFS name order, or the
  sidecar JSON in ``sort_keys`` order. Both put ``v1`` in front of ``v2``, so a deployment
  with no reachable PostgreSQL reported its *oldest* version as current.

Everything here runs offline. The database leg is exercised through its real code path with
the real SQL text on an in-memory engine, so the only emulated thing is the ORDER BY itself.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.documents import catalog

_NAME = "policy.txt"
# 1 / 2 / 10 and not 1 / 2 / 3: name order puts "10" between "1" and "2", so a fix that
# sorted versions as text would still be caught by these rows.
_VERSIONS = (1, 2, 10)


def _stored_file(root: Path, version: int) -> Path:
    path = root / f"resource-{version:04d}.txt"
    path.write_text(f"body of version {version}", encoding="utf-8")
    return path


def _sidecar_payload(root: Path, versions=_VERSIONS) -> dict:
    """Sidecar records for one document in several versions, files written to disk."""
    records = {}
    for version in versions:
        path = _stored_file(root, version)
        records[f"{_NAME}|v{version}"] = {
            "filename": _NAME,
            "version": version,
            "classification": 1,
            "department": "",
            "owner_id": "alice",
            "size_bytes": path.stat().st_size,
            "parse_status": "ready",
            "index_status": "indexed",
            "index_reason": "",
            "created_at": f"2026-01-0{version}T09:00:00+08:00",
            "recorded_path": str(path),
        }
    return records


def _write_sidecar(root: Path, records: dict, key_order=None) -> Path:
    ordered = {key: records[key] for key in (key_order or records)}
    path = root / catalog.LOCAL_CATALOG_FILENAME
    path.write_text(
        json.dumps({"documents": ordered}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """A catalog with no database to ask, rooted in tmp_path."""
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    return tmp_path


class _StandInEngine:
    """Answers the database leg's own SQL, so the leg under test stays the real one.

    ``current_documents`` still takes its database branch, still builds the SELECT out of
    ``_SELECT_COLUMNS``, still issues ``ORDER BY filename, version DESC`` and still dedups
    with the shared arbiter. Only the engine is a substitute, and the property it has to
    share with PostgreSQL is a numeric ``version DESC`` over an integer column.
    """

    def __init__(self, rows):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE document_versions (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                version INTEGER NOT NULL,
                classification INTEGER NOT NULL DEFAULT 1,
                department TEXT,
                storage_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                owner_id TEXT,
                size_bytes INTEGER,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                UNIQUE (filename, version)
            )
            """
        )
        for row in rows:
            self.connection.execute(
                "INSERT INTO document_versions (filename, version, classification, department,"
                " storage_path, created_at, owner_id, size_bytes, parse_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["filename"],
                    row["version"],
                    row["classification"],
                    row["department"],
                    row["storage_path"],
                    row["created_at"],
                    row["owner_id"],
                    row["size_bytes"],
                    row["parse_status"],
                ),
            )
        self.connection.commit()
        self.executions: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executions.append(sql)
        # psycopg spells placeholders ``%s``, sqlite wants ``?``; the SQL text the module
        # sent stays recorded verbatim, only the placeholder is translated.
        return self.connection.execute(sql.replace("%s", "?"), params or ())

    def commit(self):
        self.connection.commit()


def _database_leg(monkeypatch, rows):
    engine = _StandInEngine(rows)
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: engine)
    return engine


def _table_rows(root: Path, versions=_VERSIONS) -> list[dict]:
    return [
        {
            "filename": _NAME,
            "version": version,
            "classification": 1,
            "department": "",
            "storage_path": str(_stored_file(root, version)),
            "created_at": f"2026-01-0{version}T09:00:00+08:00",
            "owner_id": "alice",
            "size_bytes": 19,
            "parse_status": "ready",
        }
        for version in versions
    ]


def _current(rows: list[dict]) -> list[tuple[str, int]]:
    return sorted((row["filename"], row["version"]) for row in rows)


# --------------------------------------------------------------------------- (a) forensics


def test_offline_leg_no_longer_reports_the_oldest_version(offline):
    """The production shape: resource-id files listed through the sidecar only."""
    records = _sidecar_payload(offline)
    _write_sidecar(offline, records)

    rows = catalog.current_documents()

    assert _current(rows) == [(_NAME, 10)]


@pytest.mark.parametrize(
    "key_order",
    [
        # What record_local_document_version actually writes: _write_sidecar sorts keys, so
        # v1 lands first and v10 lands between v1 and v2. The oldest version wins the dedup
        # on this order, which is the defect as deployed.
        ["policy.txt|v1", "policy.txt|v10", "policy.txt|v2"],
        # The enumeration deliberately laid out as the exact reverse of version order.
        ["policy.txt|v10", "policy.txt|v2", "policy.txt|v1"],
        # And one that agrees with neither, so no single lucky ordering can carry this test.
        ["policy.txt|v2", "policy.txt|v1", "policy.txt|v10"],
    ],
    ids=["sort_keys_order", "reverse_version_order", "scrambled_order"],
)
def test_the_sidecar_key_order_cannot_move_the_current_version(offline, key_order):
    """判据③: whichever order the records come back in, the newest version is the answer.

    ``json.loads`` keeps the key order of the file and ``_local_version_rows`` walks the
    records in it, so the key list below is the directory enumeration's worst case written
    down by hand instead of left to whatever the filesystem feels like returning.
    """
    records = _sidecar_payload(offline)
    sidecar = _write_sidecar(offline, records, key_order=key_order)

    listed = json.loads(sidecar.read_text(encoding="utf-8"))["documents"]
    assert list(listed) == key_order, "the fixture stopped being the order under test"

    assert _current(catalog.current_documents()) == [(_NAME, 10)]
    # _current sorts before comparing, so the row order itself needs a raw read.
    assert [(row["filename"], row["version"]) for row in catalog._local_version_rows()] == [
        (_NAME, 10),
        (_NAME, 2),
        (_NAME, 1),
    ]


def test_legacy_name_version_scan_ignores_its_own_enumeration_order(offline, monkeypatch):
    """判据①③: the ``name__vN.ext`` scan answers in catalog order, never in readdir order.

    ``iterdir()`` carries no ordering contract - NTFS happens to return names alphabetically,
    other filesystems return directory-hash order - so the enumeration is forced oldest-first
    here instead of being left to luck. That order is exactly the one under which
    first-write-wins collects ``v1`` as the current version, and its lexicographic twin is the
    order under which a text-sorting fix would collect ``v2``. Only a numeric ``version DESC``
    answers 10.
    """
    for version in _VERSIONS:
        (offline / catalog.build_storage_name(_NAME, version)).write_text(
            f"body of version {version}", encoding="utf-8"
        )

    real_iterdir = Path.iterdir

    def oldest_first(self):
        if str(self) != str(offline):
            return real_iterdir(self)
        return iter(sorted(real_iterdir(self), key=lambda path: path.name))

    monkeypatch.setattr(Path, "iterdir", oldest_first)

    enumerated = [path.name for path in offline.iterdir() if path.is_file()]
    assert enumerated == [
        catalog.build_storage_name(_NAME, 1),
        catalog.build_storage_name(_NAME, 10),
        catalog.build_storage_name(_NAME, 2),
    ], "the enumeration stopped being the oldest-first order this pin is about"

    assert [(row["filename"], row["version"]) for row in catalog._local_version_rows()] == [
        (_NAME, 10),
        (_NAME, 2),
        (_NAME, 1),
    ]
    assert _current(catalog.current_documents()) == [(_NAME, 10)]


# ------------------------------------------------------------------------ (b) leg parity


def test_both_legs_answer_the_same_current_version(monkeypatch, tmp_path):
    """判据①: one document, three versions, the same answer with and without a database."""
    records = _sidecar_payload(tmp_path)
    _write_sidecar(tmp_path, records)

    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    offline_rows = catalog.current_documents()

    engine = _database_leg(monkeypatch, _table_rows(tmp_path))
    database_rows = catalog.current_documents()

    assert _current(offline_rows) == _current(database_rows) == [(_NAME, 10)]
    assert [(row["filename"], row["version"]) for row in offline_rows] == [
        (row["filename"], row["version"]) for row in database_rows
    ]
    assert [Path(row["storage_path"]).name for row in offline_rows] == [
        Path(row["storage_path"]).name for row in database_rows
    ], "the two legs agree on the version but resolve a different stored file"
    assert engine.executions, "the database leg never reached its SQL"


def test_history_lists_versions_newest_first_on_both_legs(monkeypatch, tmp_path):
    """判据②: the version history shares that one ordering instead of writing its own key.

    The same three stored versions, asked of each leg in turn: the history is version DESC, so
    the row the catalog calls "current" is the first row of the history on both paths.
    """
    _write_sidecar(tmp_path, _sidecar_payload(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    offline_history = [row["version"] for row in catalog.list_document_versions(_NAME)]

    _database_leg(monkeypatch, _table_rows(tmp_path))
    database_history = [row["version"] for row in catalog.list_document_versions(_NAME)]

    assert offline_history == database_history == [10, 2, 1]


def test_the_two_legs_return_the_same_row_shape(monkeypatch, tmp_path):
    """判据④: closing the version gap may not move the response contract."""
    _write_sidecar(tmp_path, _sidecar_payload(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    offline_keys = sorted(catalog.current_documents()[0])

    _database_leg(monkeypatch, _table_rows(tmp_path))
    database_keys = sorted(catalog.current_documents()[0])

    assert offline_keys == database_keys == [
        "classification",
        "created_at",
        "department",
        "filename",
        "index_reason",
        "index_status",
        "owner_id",
        "ownership",
        "parse_status",
        "size_bytes",
        "storage_path",
        "version",
    ]


# --------------------------------------------------------------------- (c) the ordering rule


def test_local_rows_come_back_in_the_catalog_order(offline):
    """判据①: the offline row list itself no longer carries filesystem order."""
    _write_sidecar(offline, _sidecar_payload(offline))

    rows = catalog._local_version_rows()

    assert [(row["filename"], row["version"]) for row in rows] == [
        (_NAME, 10),
        (_NAME, 2),
        (_NAME, 1),
    ]


@pytest.mark.parametrize("filename", [_NAME, "report.txt"])
def test_writing_through_the_real_offline_writer_matches(filename, monkeypatch, tmp_path):
    """``record_local_document_version`` sorts its keys; the answer must not depend on that."""
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    for version in _VERSIONS:
        path = _stored_file(tmp_path, version)
        catalog.record_local_document_version(
            filename, 1, "", str(path), version, owner_id="alice", parse_status="ready"
        )

    assert _current(catalog.current_documents()) == [(filename, 10)]


def test_the_arbiter_ignores_input_order():
    """反证钉: remove the ordering from ``_current_version_rows`` and this goes red first.

    The dedup runs over the same rows pushed forwards and backwards; if any part of the
    answer still came from input order the two halves would disagree.
    """
    rows = [
        {"filename": _NAME, "version": version, "created_at": f"2026-01-0{version}"}
        for version in _VERSIONS
    ]

    forwards = catalog._current_version_rows(rows)
    backwards = catalog._current_version_rows(list(reversed(rows)))

    assert [(row["filename"], row["version"]) for row in forwards] == [
        (row["filename"], row["version"]) for row in backwards
    ] == [(_NAME, 10)]


def test_versions_compare_as_numbers_not_text():
    """判据②: ``10`` must never win because it sorts before ``2`` as text."""
    rows = [
        {"filename": _NAME, "version": "10", "created_at": "x"},
        {"filename": _NAME, "version": 9, "created_at": "y"},
    ]

    assert catalog._current_version_rows(rows) == [rows[0]]
    assert catalog._version_number({"version": None}) == 0
    assert catalog._version_number({"version": "garbage"}) == 0


# ------------------------------------------------------------------------- (d) one read


def test_current_documents_still_reads_the_offline_catalog_once(monkeypatch, offline):
    """判据④: ``documents`` and ``documents_ready`` share this call, so it stays one read."""
    _write_sidecar(offline, _sidecar_payload(offline))
    reads: list[str] = []
    real_read = catalog._read_sidecar

    def counting_read(path):
        reads.append(str(path))
        return real_read(path)

    monkeypatch.setattr(catalog, "_read_sidecar", counting_read)

    catalog.current_documents()

    assert len(reads) == 1, reads


def test_current_documents_still_issues_one_statement(monkeypatch, tmp_path):
    """判据④: the same promise on the database leg."""
    engine = _database_leg(monkeypatch, _table_rows(tmp_path))

    catalog.current_documents()

    assert len(engine.executions) == 1
    assert "ORDER BY filename, version DESC" in engine.executions[0]
