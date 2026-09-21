"""R76: ``chunk_vectors`` joins the index publication / backfill chain.

R58 left one column unwritten on purpose. ``chunk_vectors.index_version_id`` answers
"which published version do these vectors belong to", and the dual write could not answer
it -- the retriever that performs the write has never heard of index versions. This file
pins the half that was missing: the publication that follows the write binds the rows, and
refuses to bind a generation it did not produce.

What every test here shares: a fake database (the one R58/S4 shipped, extended with the
vector table), a real ``IndexRegistry`` on a temp path, and a real ``IndexPublisher``.
Nothing connects to PostgreSQL, and no migration is applied. The SQL text, the branch the
probe takes and the transaction shape are what is under test -- see
``test_what_this_file_cannot_prove`` for the line this file does not extrapolate across.
"""
import pytest

from app.rag import indexing
from app.rag.indexing import (
    CODE_DIMENSION_DRIFT,
    CODE_MODEL_DRIFT,
    DocumentIndexPublication,
    EmbeddingScope,
    IndexMirrorSession,
    IndexPublicationError,
    IndexPublisher,
    IndexRegistry,
    IndexScopeError,
    PostgresIndexStore,
    VECTOR_MIRROR_TABLE,
    VectorTagging,
    _MIRROR_COLUMNS,
    _MIRROR_REQUIRED_TABLES,
    _MIRROR_TABLES,
)
from tests.test_document_index_publication import FakeIndexDatabase, _Cursor

MODEL_A = "nomic-embed-text"
MODEL_B = "bge-m3"
DIM = 768
DIM_OTHER = 1024
INDEX_ID = "document:policy.txt"


class VectorIndexDatabase(FakeIndexDatabase):
    """The S4 mirror plus the table the dual write owns.

    Two switches matter. ``vectors_migrated`` says whether 0010 ran, which is the only
    thing that turns the binding step on -- the statement must not be sent to a database
    that has no such table, exactly the way the chunk_count counter is skipped when its
    column is missing. ``dict_rows`` flips the row spelling because production reads with
    ``dict_row`` while other fakes in this tree answer with tuples; the step has to survive
    both, and a test that only ever feeds it one proves nothing about the other.
    """

    def __init__(
        self,
        rows=(),
        *,
        vectors_migrated=True,
        counters=True,
        dict_rows=True,
        drift_after_probe=False,
    ):
        super().__init__(migrated=True, counters=counters)
        self.tables[VECTOR_MIRROR_TABLE] = {}
        self.dict_rows = dict_rows
        # Stands in for the one thing a dictionary cannot: another writer landing between
        # the two statements, so the rows the probe counted no longer carry the profile the
        # bind is filtering on. Only the UPDATE notices it, which is what the guard is for.
        self.drift_after_probe = drift_after_probe
        if vectors_migrated:
            for column in _MIRROR_COLUMNS[VECTOR_MIRROR_TABLE]:
                self.columns.add((VECTOR_MIRROR_TABLE, column))
        for row in rows:
            self.add_vector_row(row)

    # ------------------------------------------------------------------- fixtures
    def add_vector_row(self, row):
        stored = {
            "vector_id": row["vector_id"],
            "filename": row.get("filename", "policy.txt"),
            "chunk_index": row.get("chunk_index", 0),
            "embedding_model": row["embedding_model"],
            "embedding_dimension": row["embedding_dimension"],
            "index_version_id": row.get("index_version_id"),
        }
        self.tables[VECTOR_MIRROR_TABLE][stored["vector_id"]] = stored
        return stored

    def vector_rows(self):
        return list(self.tables[VECTOR_MIRROR_TABLE].values())

    def bound_version_ids(self):
        return sorted(str(row["index_version_id"]) for row in self.vector_rows())

    def statements_touching_vectors(self):
        return [sql for sql, _params in self.statements if VECTOR_MIRROR_TABLE in sql]

    # ------------------------------------------------------------------ executor
    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split()).lower()
        if VECTOR_MIRROR_TABLE not in normalized:
            return super().execute(sql, params)
        self.statements.append((normalized, params))
        for fragment, error in self.failures.items():
            if fragment in normalized:
                raise error
        if "select embedding_model" in normalized:
            return self._probe(params)
        if "update " + VECTOR_MIRROR_TABLE in normalized:
            return self._bind(params)
        raise AssertionError(f"unexpected vector statement: {normalized}")

    def _probe(self, params):
        wanted = set(str(item) for item in params[0])
        groups: dict = {}
        for row in self.vector_rows():
            if row["vector_id"] in wanted:
                key = (row["embedding_model"], row["embedding_dimension"])
                groups[key] = groups.get(key, 0) + 1
        rows = [
            {"embedding_model": model, "dimension": width, "row_count": count}
            for (model, width), count in sorted(groups.items())
        ]
        if not self.dict_rows:
            rows = [
                (row["embedding_model"], row["dimension"], row["row_count"]) for row in rows
            ]
        return _Cursor(rows)

    def _bind(self, params):
        index_version_id, vector_ids, model, dimension = params
        if self.drift_after_probe:
            return _Cursor(rowcount=0)
        wanted = set(str(item) for item in vector_ids)
        matched = 0
        for row in self.vector_rows():
            if (
                row["vector_id"] in wanted
                and row["embedding_model"] == model
                and row["embedding_dimension"] == dimension
            ):
                row["index_version_id"] = index_version_id
                matched += 1
        return _Cursor(rowcount=matched)


def _publication(version: int = 1, *, filename="policy.txt", chunks=("one", "two", "three")):
    return DocumentIndexPublication(
        filename=filename,
        version=version,
        owner_id="alice",
        classification=1,
        department="finance",
        chunks=chunks,
        vector_ids=tuple(f"{filename}_{ordinal}" for ordinal in range(len(chunks))),
    )


def _vector_rows(count, *, model=MODEL_A, dimension=DIM, filename="policy.txt", start=0):
    """Rows in the shape the dual write leaves behind: no version id, its own profile.

    ``start`` keeps the ids apart when one test needs two generations in one table, because
    the primary key really is vector_id and a colliding fixture would quietly be one row.
    """
    return [
        {
            "vector_id": f"{filename}_{ordinal}",
            "filename": filename,
            "chunk_index": ordinal,
            "embedding_model": model,
            "embedding_dimension": dimension,
        }
        for ordinal in range(start, start + count)
    ]


def _publisher(tmp_path, database, *, scope=EmbeddingScope(MODEL_A, DIM)):
    registry = IndexRegistry(tmp_path / "indexes.json", scope=scope)
    store = PostgresIndexStore(connection_factory=database.connection)
    return IndexPublisher(registry, store), registry


# -------------------------------------------------------------------- criterion 1
def test_the_vector_table_is_on_the_list_the_publication_probes():
    """Criterion 1: the mirror's table list names chunk_vectors, and the read reaches it.

    ``chunk_vectors`` is in ``_MIRROR_TABLES``, which is what ``_read_schema`` asks
    information_schema for and what the probe result is built from. It is deliberately not
    in ``_MIRROR_REQUIRED_TABLES``: 0010 is optional while VECTOR_DUAL_WRITE is off, and
    gating all index bookkeeping on it would take the mirror away from every install that
    has not adopted pgvector. That trade-off is why the next test exists.
    """
    assert VECTOR_MIRROR_TABLE in _MIRROR_TABLES
    assert VECTOR_MIRROR_TABLE in _MIRROR_COLUMNS
    assert VECTOR_MIRROR_TABLE not in _MIRROR_REQUIRED_TABLES
    assert _MIRROR_COLUMNS[VECTOR_MIRROR_TABLE] == (
        "vector_id",
        "index_version_id",
        "embedding_model",
        "embedding_dimension",
    )

    database = VectorIndexDatabase()
    session = PostgresIndexStore(connection_factory=database.connection).open()

    assert isinstance(session, IndexMirrorSession)
    assert session.enabled is True
    assert session.vectors_enabled is True
    probed = [params for sql, params in database.statements if "information_schema" in sql]
    assert VECTOR_MIRROR_TABLE in list(probed[0][0])


def test_the_missing_vector_table_degrades_the_step_and_nothing_else():
    """Criterion 1's other half: no 0010 means no binding, and no other loss.

    This is the conditional-send contract that keeps the pre-R76 publication tests green:
    the step is not merely tolerant of a missing table, it issues no statement at all.
    """
    database = VectorIndexDatabase(vectors_migrated=False)
    session = PostgresIndexStore(connection_factory=database.connection).open()

    assert session.enabled is True, "index bookkeeping must survive a missing 0010"
    assert session.degraded_reason == ""
    assert session.vectors_enabled is False


def test_the_two_modules_name_the_same_vector_table():
    """One ruler, two files. pg_store imports indexing, so the literal cannot be shared.

    app/rag/pg_store.py:41 imports this module, so indexing.py importing it back would be a
    cycle; the duplication is therefore deliberate, and is pinned here instead. A rename on
    one side would otherwise leave the publication probing a table that does not exist while
    every test still passed, because both halves would be internally consistent.
    """
    from app.rag import pg_store

    assert indexing.VECTOR_MIRROR_TABLE == pg_store.DEFAULT_VECTOR_TABLE


# -------------------------------------------------------------------- criterion 2
def test_publishing_binds_the_rows_it_was_handed(tmp_path):
    """Criterion 2: NULL before, this publication's own version id after, with a count.

    The count matters as much as the value: ``vector_rows_tagged`` is how a caller knows
    the chain actually reached chunk_vectors, rather than reading a log line that said it
    intended to.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    publisher, registry = _publisher(tmp_path, database)
    publication = _publication()

    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]

    outcome = publisher.publish(publication)

    assert outcome.vector_rows_tagged == 3
    assert outcome.vector_rows_missing == 0
    assert outcome.as_dict()["vector_rows_tagged"] == 3
    assert [row["index_version_id"] for row in database.vector_rows()] == [
        outcome.index_version_id,
        outcome.index_version_id,
        outcome.index_version_id,
    ]
    assert registry.current(INDEX_ID).index_version_id == outcome.index_version_id
    assert database.commits == 1

    binds = [
        params
        for sql, params in database.statements
        if "update " + VECTOR_MIRROR_TABLE in sql
    ]
    assert len(binds) == 1
    index_version_id, vector_ids, model, dimension = binds[0]
    assert index_version_id == outcome.index_version_id
    assert list(vector_ids) == ["policy.txt_0", "policy.txt_1", "policy.txt_2"]
    # The write carries the profile it just read, not the version's own claim: this is the
    # predicate that keeps a generation nobody probed from being stamped by accident.
    assert (model, dimension) == (MODEL_A, DIM)


def test_a_version_that_was_never_published_leaves_the_column_null(tmp_path):
    """Criterion 2, the NULL side: an unpublished vector row belongs to no version.

    The mirror's own row shape is the dual write's business, and R76 deliberately did not
    move the stamp there: the retriever has no index version to name, and inventing one is
    the silent desync R22 refuses. So build_rows still writes NULL, and compare_vector_recall
    keeps counting those rows as "awaiting publication" rather than as an error.
    """
    from app.rag.pg_store import _UPSERT_COLUMNS, VectorMirror, VectorScope

    mirror = VectorMirror(
        None,
        scope=VectorScope(MODEL_A, DIM, "cosine"),
        column_type=f"vector({DIM})",
        vector_table=VECTOR_MIRROR_TABLE,
    )
    rows = mirror.build_rows(
        ids=["policy.txt_0"],
        documents=["body text"],
        metadatas=[{"filename": "policy.txt", "chunk_index": 0, "classification": 1}],
        # A full-width non-zero vector: R21's shared gate refuses an all-zero one, and the
        # width it compares against is the declared profile, not this test's imagination.
        embeddings=[[0.5] * DIM],
    )

    assert len(rows) == 1
    position = _UPSERT_COLUMNS.index("index_version_id")
    assert position == 7, "the dual write's column order moved without this test knowing"
    assert rows[0][position] is None


def test_republishing_moves_the_binding_to_the_new_version(tmp_path):
    """Criterion 2 again, one publication later: the id is this one, not the last one.

    A re-index of the same document re-upserts the same vector ids (the Chroma id is
    ``<filename>_<ordinal>``), so the row has to end up owned by the version that is current
    now. Two ids in the table would mean the mirror was pointing at a superseded version.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    publisher, _registry = _publisher(tmp_path, database)

    first = publisher.publish(_publication(version=1))
    second = publisher.publish(_publication(version=2))

    assert first.index_version_id != second.index_version_id
    assert database.bound_version_ids() == [second.index_version_id] * 3
    assert second.previous_index_version_id == first.index_version_id

# -------------------------------------------------------------------- criterion 3
def _refusal(excinfo):
    """Unwrap what the publisher reports for a failed step down to the scope refusal."""
    error = excinfo.value
    assert isinstance(error, IndexPublicationError)
    assert error.stage == "vector_index_version"
    cause = error.__cause__
    assert isinstance(cause, IndexScopeError)
    return cause


def test_a_stale_generation_is_refused_rather_than_relabelled(tmp_path):
    """Criterion 3, and the knife the ticket asks for.

    The mirror holds vectors that MODEL_B produced; the registry publishes under MODEL_A. The
    only honest answers are "bind both" and "publish neither", and this slice cannot rewrite
    vectors -- it never calls an embedder. So it refuses, and refuses *before* stamping: the
    rows must still be NULL afterwards, because a row tagged with a version that never became
    current is a lie a filtered search would believe.

    Remove the disagreement check in tag_vector_index_version and this test goes red while
    every other test in this file stays green -- that is the point of it.
    """
    database = VectorIndexDatabase(_vector_rows(3, model=MODEL_B))
    publisher, registry = _publisher(tmp_path, database)

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    cause = _refusal(excinfo)
    assert cause.code == CODE_MODEL_DRIFT
    assert cause.codes == (CODE_MODEL_DRIFT,)
    assert cause.version_scope.embedding_model == MODEL_B
    assert cause.configured_scope.embedding_model == MODEL_A
    assert "policy.txt" in str(cause)

    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]
    assert [sql for sql, _ in database.statements if "update " + VECTOR_MIRROR_TABLE in sql] == []
    with pytest.raises(KeyError):
        registry.current(INDEX_ID)
    assert registry._versions == {}
    assert database.commits == 0
    assert database.rollbacks == 1


def test_a_different_width_is_refused_by_its_own_name(tmp_path):
    """Criterion 3, other axis: a model swap and a width change are different diagnoses.

    R22 keeps these codes apart so an operator knows whether to re-embed or to re-migrate,
    and the mirror is where a width change first becomes visible: the vectors are already
    there, 1024 wide, in a table this publication is about to call 768.
    """
    database = VectorIndexDatabase(_vector_rows(3, dimension=DIM_OTHER))
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    cause = _refusal(excinfo)
    assert cause.code == CODE_DIMENSION_DRIFT
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]


def test_a_half_rebuilt_mirror_refuses_the_whole_publication(tmp_path):
    """Criterion 3: a mirror that agrees only for some rows is not a mirror to publish on.

    Two groups means the rebuild stopped partway. Binding every row to one version would
    erase the evidence and present the mixed table as a finished one, so the refusal covers
    the batch -- and every axis that moved is named, not only the first one found.
    """
    rows = (
        _vector_rows(2, model=MODEL_A, dimension=DIM_OTHER)
        + _vector_rows(1, model=MODEL_B, start=2)
    )
    database = VectorIndexDatabase(rows)
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    cause = _refusal(excinfo)
    assert set(cause.codes) == {CODE_MODEL_DRIFT, CODE_DIMENSION_DRIFT}
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]


def test_the_binding_works_once_the_mirror_was_rebuilt_with_it(tmp_path):
    """Criterion 3 must not become a ban on model changes: rebuild both, then publish.

    This is the shape a real embedding-model change takes: the rebuild re-embeds the
    document under the new profile -- the dual write produces the new rows -- and only then
    does the publication bind them. The gate asks that the two agree, never that the table
    stay frozen on the first profile it ever held.
    """
    database = VectorIndexDatabase(_vector_rows(3, model=MODEL_B))
    stale_publisher, _registry = _publisher(tmp_path, database)
    with pytest.raises(IndexPublicationError):
        stale_publisher.publish(_publication(version=1))

    rebuilt = VectorIndexDatabase(
        _vector_rows(3, model=MODEL_A), counters=True
    )
    publisher, registry = _publisher(tmp_path, rebuilt)
    outcome = publisher.publish(_publication(version=1))

    assert outcome.vector_rows_tagged == 3
    assert rebuilt.bound_version_ids() == [outcome.index_version_id] * 3
    assert registry.current(INDEX_ID).embedding_model == MODEL_A


def test_an_unlabelled_generation_is_refused_as_unknown_not_as_agreement(tmp_path):
    """Criterion 3, fail-closed edge: an empty model name is not the configured model.

    ``EmbeddingScope.disagreement`` reports embedding_scope_unknown for a record that never
    named its embedder, which is evidence nobody was keeping score. Treating that as a match
    would let an unlabelled row be published as if it had been produced by this build.
    """
    database = VectorIndexDatabase(_vector_rows(3, model=""))
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    cause = _refusal(excinfo)
    assert cause.code == indexing.CODE_SCOPE_UNKNOWN
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]

# -------------------------------------------------------------------- criterion 4
def test_a_binding_that_fails_undoes_the_index_half_too(tmp_path):
    """Criterion 4: the binding is not a second ledger, it is the same transaction.

    Injecting a failure into the UPDATE itself has to leave the chunk rows, the version rows
    and the vector rows in the state they were in before the publication started. An
    "either whole batch visible or whole batch invisible" claim only means something if a
    failure in the new step can be shown to roll the *old* steps back as well.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    database.failures["update " + VECTOR_MIRROR_TABLE] = RuntimeError("the vector leg died")
    publisher, registry = _publisher(tmp_path, database)

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    assert excinfo.value.stage == "vector_index_version"
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]
    assert database.chunk_rows() == []
    assert database.version_rows() == []
    assert database.tables["resource_versions"] == {}
    with pytest.raises(KeyError):
        registry.current(INDEX_ID)
    assert database.commits == 0


def test_a_failure_after_the_binding_undoes_the_binding(tmp_path):
    """Criterion 4, the other ordering: stamping first and failing later is no better.

    mark_published is the step after the binding, so a crash there proves the bind is inside
    the transaction rather than merely before it: the rows go back to NULL and nothing in the
    mirror claims to belong to a version that never published.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    database.failures["update index_registry"] = RuntimeError("the registry row is locked")
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    assert excinfo.value.stage == "publish"
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]
    assert database.chunk_rows() == []
    assert database.commits == 0
    assert database.rollbacks == 1


def test_a_republished_document_rebinds_the_same_rows_without_duplicates(tmp_path):
    """Criterion 4, idempotency: the second run is a re-stamp, not a second insert.

    The step issues one UPDATE and no INSERT: the row already exists because the dual write
    owns its creation, and re-running a publication that was interrupted after the commit
    must not multiply rows or fail on the primary key. The fake enforces that by refusing
    any statement whose text is not the two it knows.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    first = publisher.publish(_publication(version=1))
    second = publisher.publish(_publication(version=2))

    assert len(database.vector_rows()) == 3
    assert first.vector_rows_tagged == second.vector_rows_tagged == 3
    assert database.bound_version_ids() == [second.index_version_id] * 3
    inserts = [
        sql for sql, _ in database.statements if "insert into " + VECTOR_MIRROR_TABLE in sql
    ]
    assert inserts == []


# --------------------------------------------------------------- degradation paths
def test_ids_the_mirror_does_not_hold_are_counted_and_named(tmp_path):
    """Criteria 1 and 4 meet here: a partial mirror is reported, never guessed at.

    One row exists, two do not. The step could have derived the missing ids from
    ``<filename>_<ordinal>`` and stamped the row it found while pretending about the rest;
    instead it reports carried/existing/tagged and lets the caller see the gap. Deriving ids
    here would be a second ruler for the same fact -- the retriever owns that spelling, and
    a publication that guessed it could bind a version to rows no dual write ever made.
    """
    database = VectorIndexDatabase(_vector_rows(1))
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    outcome = publisher.publish(_publication())

    assert outcome.vector_rows_tagged == 1
    assert outcome.vector_rows_missing == 2
    assert outcome.mirrored is True
    assert any(
        "2 of 3" in warning and VECTOR_MIRROR_TABLE in warning for warning in outcome.warnings
    ), outcome.warnings
    assert database.bound_version_ids() == [outcome.index_version_id]


def test_a_database_without_0010_publishes_and_says_why_it_bound_nothing(tmp_path):
    """Criterion 1's degradation, end to end: no vector statements, one named warning.

    This is the shape every publication test in this tree had before R76, and it has to stay
    green: the mirror keeps doing bookkeeping, the binding step is skipped rather than
    attempted, and the warning names the migration to run.
    """
    database = VectorIndexDatabase(vectors_migrated=False)
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    outcome = publisher.publish(_publication())

    assert outcome.vector_rows_tagged == 0
    assert outcome.vector_rows_missing == 0
    assert database.statements_touching_vectors() == []
    assert any(
        VECTOR_MIRROR_TABLE in warning and "0010" in warning for warning in outcome.warnings
    ), outcome.warnings


def test_tuple_rows_are_read_the_same_way_as_dict_rows(tmp_path):
    """A probe that only ever answered with dicts would miss a plain-tuple connection.

    indexing.py reads rows as dicts because production passes ``row_factory=dict_row``; the
    vector mirror in this same tree went out of its way to accept both spellings. The binding
    step is one function, so it has to survive both as well.
    """
    database = VectorIndexDatabase(_vector_rows(3), dict_rows=False)
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "indexes.json", scope=EmbeddingScope(MODEL_A, DIM)),
        PostgresIndexStore(connection_factory=database.connection),
    )

    outcome = publisher.publish(_publication())

    assert outcome.vector_rows_tagged == 3
    assert database.bound_version_ids() == [outcome.index_version_id] * 3


def test_a_retirement_names_no_vectors_and_binds_nothing(tmp_path):
    """Retiring a document is not a chance to stamp the mirror with a tombstone version.

    A retirement publication carries no chunks and no vector ids, so the step is handed
    nothing and must issue nothing. The vector rows themselves go away in the delete leg
    (app/rag/retriever.py), which is the transaction that owns that table.
    """
    database = VectorIndexDatabase(_vector_rows(3))
    publisher, _registry = _publisher(tmp_path, database)
    publisher.publish(_publication(version=1))
    before = database.statements_touching_vectors()

    retirement = DocumentIndexPublication(
        filename="policy.txt", version=1, owner_id="alice", retirement=True
    )
    outcome = publisher.publish(retirement)

    assert outcome.vector_rows_tagged == 0
    assert outcome.as_dict()["vector_rows_tagged"] == 0
    assert outcome.status == "retired"
    assert database.statements_touching_vectors() == before


def test_the_tagging_numbers_add_up_the_way_the_outcome_reports_them():
    """The three counters are the diagnosis, so their arithmetic is pinned on its own.

    ``missing`` is carried minus existing, and nothing else: a caller comparing an upload
    against the mirror has to be able to tell "no row for this id" apart from "a row that
    was bound", and a number that mixed the two would hide the difference.
    """
    assert VectorTagging().missing == 0
    assert VectorTagging(carried=3, existing=1, tagged=1).missing == 2
    assert VectorTagging(carried=3, existing=3, tagged=3).missing == 0
    assert VectorTagging(carried=3, existing=3, tagged=3).as_dict()["tagged"] == 3


def test_rows_that_move_between_the_probe_and_the_bind_are_refused(tmp_path):
    """Criterion 4, narrowest case: the read and the write disagreed.

    The probe said three rows carry this profile; the UPDATE, which carries that same
    profile in its predicate, matched none. Something re-embedded the document in between.
    The honest answer is "I did not bind what I claimed I would", so the step refuses and
    the publication rolls back; reporting vector_rows_tagged=3 on a rowcount of 0 would be
    the mirror certifying a fact the database never confirmed.
    """
    database = VectorIndexDatabase(_vector_rows(3), drift_after_probe=True)
    publisher, registry = _publisher(tmp_path, database)

    with pytest.raises(IndexPublicationError) as excinfo:
        publisher.publish(_publication())

    assert excinfo.value.stage == "vector_index_version"
    assert "bound 0 of 3" in str(excinfo.value.__cause__)
    assert [row["index_version_id"] for row in database.vector_rows()] == [None, None, None]
    assert database.chunk_rows() == []
    with pytest.raises(KeyError):
        registry.current(INDEX_ID)
    assert database.commits == 0
    assert database.rollbacks == 1


def test_what_this_file_cannot_prove():
    """Criterion 5: the boundary of an offline fake, stated rather than implied.

    Kept as a test so the sentence cannot rot into being forgotten:

    * Real PostgreSQL concurrency is not modelled. Two publications racing on one document,
      or a dual write committing between the probe and the UPDATE, are argued from the
      transaction boundary and the scope predicate, not demonstrated. The fake answers both
      statements from the same dictionary and cannot interleave.
    * Real chromadb behaviour on duplicate ids is not modelled either. Whether a re-add of an
      existing id replaces the vector is the assumption that ``<filename>_<ordinal>`` stays
      one row, taken from app/rag/retriever.py and migrations/0010, not tested against the
      engine -- the lesson KNIFE-3 left behind.
    * The column types, the NOT NULL constraints and chunk_vectors_index_version_idx come
      from migrations/0010_pgvector_chunks.sql as read, never from applying it.
    """
    assert True