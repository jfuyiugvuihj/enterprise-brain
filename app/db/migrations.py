"""Immutable PostgreSQL migration metadata, validation, and execution helpers.

Importing this module only reads checked-in SQL files. Applying migrations remains an
explicit deployment responsibility and must occur under a PostgreSQL advisory lock.

R90a adds one deployment-side duty to ``apply_migrations``. Migration 0010 refuses to guess a
vector width, and until now the only thing that ever told it one was an operator typing ``ALTER
DATABASE`` by hand, which made a clean install stop. The runtime embedding profile is now
declared for the database being migrated, taken from the values ``app.rag.indexing`` already
embeds with, and the runner fails closed when either half of that pair is undeclared.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from app.common.logger import logger


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    checksum: str
    sql: str


_MIGRATION_FILENAME = re.compile(r"(?P<version>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql\Z")
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_MANIFEST_FILENAME = "manifest.json"
_CREATE_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    name TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
_SELECT_LEDGER_SQL = "SELECT version, checksum FROM schema_migrations ORDER BY version"
_INSERT_LEDGER_SQL = """
INSERT INTO schema_migrations (version, name, checksum)
VALUES (%s, %s, %s)
"""

#: Migration 0010 (pgvector chunks) reads a database-level pair and stops when the width is
#: missing, because R22 allows exactly one embedding profile per database: 0010's own comment
#: says the width "is never inferred from what is already stored". The two setting names below
#: are the only spellings it accepts, and their runtime spellings are EMBEDDING_DIMENSION and
#: EMBEDDING_MODEL -- read from app/rag/indexing.py, never re-declared here.
EMBEDDING_PROFILE_MIGRATION_VERSION = "0010"
EMBEDDING_DIMENSION_GUC = "app.embedding_dimension"
EMBEDDING_MODEL_GUC = "app.embedding_model"

#: Where an operator sets the two variables, and what they run afterwards. Each string below is
#: a claim about the shipped deployment layout, so
#: tests/test_r120_clean_install_first_boot.py checks every one against its truth source rather
#: than trusting this prose: the file named must be the env_file of the service that runs
#: scripts/migrate.py, the command must start that service the way the deployment README does,
#: and the sample named must really carry the pair.
#:
#: R90a shipped this guidance pointing at .env.example, which is the *host development* sample.
#: docker-compose.yml reads deploy/.env.server and nothing else, so an operator who followed the
#: pointer edited a file no container ever opens -- and a clean install stayed stopped. That is
#: the same defect class as R90b's wrong database name, which is why it is pinned here.
MIGRATE_ENV_FILE = "deploy/.env.server"
MIGRATE_ENV_SAMPLE_FILE = "deploy/.env.server.example"
HOST_ENV_FILE = ".env"
MIGRATE_COMPOSE_COMMAND = (
    f"docker compose --env-file {MIGRATE_ENV_FILE} -f docker-compose.yml run --rm migrate"
)

#: Who the connection is, and what it already declares. Aliased so a mapping cursor and a
#: tuple cursor read the same three columns.
_PROBE_EMBEDDING_PROFILE_SQL = f"""
SELECT current_database() AS database_name,
       coalesce(current_setting('{EMBEDDING_DIMENSION_GUC}', TRUE), '') AS embedding_dimension,
       coalesce(current_setting('{EMBEDDING_MODEL_GUC}', TRUE), '') AS embedding_model
"""

#: ``ALTER DATABASE ... SET`` binds neither the setting name nor its value as a parameter, so
#: the statement has to arrive as text. PostgreSQL composes that text: ``format()`` quotes its
#: own ``current_database()`` as an identifier and the value as a literal. The database name is
#: therefore never assembled in Python, not even to add a space.
#:
#: The two ::text casts are load-bearing, not decoration. psycopg's default cursor binds on
#: the server, so this reaches PostgreSQL as ``SELECT format($1, current_database(), $2)``
#: with no parameter types declared, and the parser can only name a type it reads off a
#: signature: ``format(text, "any")`` forces its *first* argument to text and says nothing
#: about the rest, so the value parameter stays indeterminate and the whole statement is
#: refused at Parse time with ``could not determine data type of parameter $2``. A real
#: PostgreSQL did exactly that to this ticket's first draft -- the run stopped here, before
#: 0010 and before anything at all was declared. Naming the type on the parameter is the fix,
#: and it moves no quoting into Python: %I and %L are still resolved by the server. The
#: statement below needs no cast because set_config(text, text, boolean) declares the type
#: of every parameter it takes.
_FORMAT_ALTER_DATABASE_SQL = "SELECT format(%s::text, current_database(), %s::text) AS statement"

#: A database-level default applies when a session *starts* -- the ALTER DATABASE page says so
#: ("Whenever a new session is subsequently started in that database, the specified value
#: becomes the session default value") -- so the session that is migrating would still read an
#: unset width and watch 0010 raise. The same two values are therefore also declared for this
#: transaction. No new number enters through this statement, and no RESET exists anywhere in
#: this module: overruling a declared profile stays 0010's job alone.
_DECLARE_PROFILE_FOR_TRANSACTION_SQL = "SELECT set_config(%s, %s, TRUE), set_config(%s, %s, TRUE)"


class EmbeddingProfileError(ValueError):
    """The embedding profile cannot be declared, so migration 0010 must not be attempted.

    Every message names the variable at fault. Guessing is the failure this type exists to
    prevent, so none of them offers a width to try instead.
    """


def _load_manifest(migrations_dir: Path) -> dict[str, str]:
    manifest_path = migrations_dir / _MANIFEST_FILENAME
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"migration manifest does not exist: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"migration manifest is invalid JSON: {manifest_path}") from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError("migration manifest must be a non-empty object")

    manifest: dict[str, str] = {}
    for filename, checksum in raw.items():
        if not isinstance(filename, str) or not isinstance(checksum, str):
            raise ValueError("migration manifest entries must be string filename/checksum pairs")
        if _MIGRATION_FILENAME.fullmatch(filename) is None:
            raise ValueError(f"invalid migration filename in manifest: {filename}")
        if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise ValueError(f"invalid migration checksum in manifest: {filename}")
        manifest[filename] = checksum
    return manifest


def discover_migrations(directory: str | Path | None = None) -> tuple[Migration, ...]:
    """Read immutable, manifest-verified SQL migrations without opening a connection."""
    migrations_dir = Path(directory) if directory is not None else _DEFAULT_MIGRATIONS_DIR
    if not migrations_dir.is_dir():
        raise ValueError(f"migration directory does not exist: {migrations_dir}")

    manifest = _load_manifest(migrations_dir)
    sql_files = sorted(migrations_dir.glob("*.sql"))
    actual_filenames = {path.name for path in sql_files}
    manifest_filenames = set(manifest)
    if actual_filenames != manifest_filenames:
        missing = sorted(manifest_filenames - actual_filenames)
        untracked = sorted(actual_filenames - manifest_filenames)
        details = []
        if missing:
            details.append(f"missing files: {', '.join(missing)}")
        if untracked:
            details.append(f"untracked files: {', '.join(untracked)}")
        raise ValueError(f"migration manifest mismatch ({'; '.join(details)})")

    migrations: list[Migration] = []
    seen_versions: set[str] = set()
    for path in sql_files:
        match = _MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"invalid migration filename: {path.name}")

        version = match.group("version")
        if version in seen_versions:
            raise ValueError(f"duplicate migration version: {version}")
        seen_versions.add(version)

        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise ValueError(f"migration SQL must not be empty: {path.name}")
        checksum = sha256(sql.encode("utf-8")).hexdigest()
        if checksum != manifest[path.name]:
            raise ValueError(f"migration manifest checksum mismatch: {path.name}")
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                checksum=checksum,
                sql=sql,
            )
        )
    return tuple(migrations)


MIGRATIONS = discover_migrations()


def migration_plan(
    applied_versions: Mapping[str, str] | None = None,
    *,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> list[Migration]:
    """Return pending migrations and reject missing or drifted ledger checksums."""
    if applied_versions is None:
        checksums: dict[str, str] = {}
    elif not isinstance(applied_versions, Mapping):
        raise TypeError("applied migration checksums must be a mapping")
    else:
        checksums = dict(applied_versions)

    known_versions = {migration.version for migration in migrations}
    unknown_versions = sorted(set(checksums) - known_versions)
    if unknown_versions:
        joined = ", ".join(unknown_versions)
        raise ValueError(f"applied migration is missing from the catalog: {joined}")

    pending: list[Migration] = []
    for migration in migrations:
        if migration.version not in checksums:
            pending.append(migration)
            continue
        applied_checksum = checksums[migration.version]
        if not isinstance(applied_checksum, str) or applied_checksum != migration.checksum:
            raise ValueError(f"migration checksum mismatch: {migration.version}")
    return pending


def migration_lock_key(database_name: str) -> str:
    value = (database_name or "").strip()
    if not value:
        raise ValueError("database name is required for migration lock")
    return f"enterprise-brain:migrations:{value}"


def _ledger_checksums(rows: list[Any]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for row in rows:
        if isinstance(row, Mapping):
            version, checksum = row["version"], row["checksum"]
        else:
            version, checksum = row[0], row[1]
        checksums[str(version)] = str(checksum)
    return checksums


def _indexing():
    """Read app.rag.indexing at call time, so importing app.db stays free of the RAG stack.

    The embedding profile means one thing in this repository and that module says it: the
    environment variable names, the defaults, and the question of what the process actually
    embeds with. Nothing here parses the environment independently of it.
    """
    from app.rag import indexing

    return indexing


def _row_value(row: Any, position: int, key: str) -> str:
    """One column of a probe row, whether the cursor hands back tuples or mappings."""
    value = row.get(key) if isinstance(row, Mapping) else row[position]
    return "" if value is None else str(value)


def _remediation(database_name: str = "") -> str:
    """Where to set the pair, what to re-run, and which database this refusal is about.

    The database name arrives from ``current_database()`` -- see
    :func:`provision_embedding_scope`, the only caller that knows it. R90b exists because a
    PL/pgSQL ``RAISE`` printed ``current_database()`` through ``%I`` and told operators to alter
    a database called ``enterprise_brainI``; an ``I`` is not a type of database. Nothing here
    composes a name, and the two paths and the command below are pinned against
    ``docker-compose.yml`` by tests/test_r120_clean_install_first_boot.py, because R90a's own
    pointer to ``.env.example`` was a second instance of the same mistake: the Compose stack
    never opens that file, so the advice was true and useless at once.
    """
    named = f"The database this run is on is {database_name!r}. " if database_name else ""
    return " " + (
        f"Set both variables in {MIGRATE_ENV_FILE} -- the only env_file the Compose stack reads "
        f"-- or in {HOST_ENV_FILE} for a run that starts without Docker; "
        f"{MIGRATE_ENV_SAMPLE_FILE} carries the pair and says why it travels together, since R22 "
        f"binds every index version to model + width. {named}Then migrate again: "
        f"{MIGRATE_COMPOSE_COMMAND}."
    )


def declared_embedding_profile(database_name: str = "") -> EmbeddingScope:
    """The profile this process runs under, or a refusal that names the missing variable.

    Both halves come out of ``app.rag.indexing.configured_embedding_scope()``, the same reader
    that binds every index version to model + width, so a migration can never declare a width
    that the application then refuses to write. That reader describes what this build ships with
    when nothing declares a value at all, which is precisely the guess 0010 refuses to make, so
    the declaration is checked first: an unset, empty, or unparseable variable stops here rather
    than degrading into ``DEFAULT_EMBEDDING_DIMENSION = 768``.

    ``database_name`` is passed by :func:`provision_embedding_scope`, which has already asked
    the server who it is. It appears in prose only, and never as part of a statement.
    """
    indexing = _indexing()
    names = (indexing.EMBEDDING_MODEL_ENV, indexing.EMBEDDING_DIMENSION_ENV)
    declared = {name: str(os.getenv(name, "") or "").strip() for name in names}
    missing = [name for name in names if not declared[name]]
    if missing:
        stated = [f"{name}={declared[name]}" for name in names if declared[name]]
        pair = ", ".join(missing)
        raise EmbeddingProfileError(
            f"Migration {EMBEDDING_PROFILE_MIGRATION_VERSION} needs a declared embedding "
            f"profile, and {pair} {'is' if len(missing) == 1 else 'are'} not declared. "
            + (f"Declared so far: {', '.join(stated)}. " if stated else "")
            + "This runner will not guess a vector width either, so "
            "DEFAULT_EMBEDDING_DIMENSION is not substituted for the missing value."
            + _remediation(database_name)
        )

    scope = indexing.configured_embedding_scope()
    if not scope.known:
        raise EmbeddingProfileError(
            f"configured_embedding_scope() reports an unknown profile ({scope}); migration "
            f"{EMBEDDING_PROFILE_MIGRATION_VERSION} needs a model and a positive width."
        )
    try:
        dimension = int(declared[indexing.EMBEDDING_DIMENSION_ENV])
    except ValueError:
        dimension = -1
    if dimension <= 0:
        raise EmbeddingProfileError(
            f"{indexing.EMBEDDING_DIMENSION_ENV} is declared as "
            f"{declared[indexing.EMBEDDING_DIMENSION_ENV]!r}, which is not a positive integer. "
            f"Migration {EMBEDDING_PROFILE_MIGRATION_VERSION} stores vectors at exactly the width "
            "it is given, so an unusable value stops here instead of falling back to the "
            "shipped default." + _remediation(database_name)
        )
    if dimension != scope.dimension:
        raise EmbeddingProfileError(
            f"{indexing.EMBEDDING_DIMENSION_ENV} declares {dimension} but "
            f"configured_embedding_scope() reports {scope.dimension}: the declared value did not "
            f"reach the profile this process embeds with, and provisioning either one would be a "
            f"guess. Migration {EMBEDDING_PROFILE_MIGRATION_VERSION} stops until they agree."
        )
    if declared[indexing.EMBEDDING_MODEL_ENV] != scope.embedding_model:
        raise EmbeddingProfileError(
            f"{indexing.EMBEDDING_MODEL_ENV} declares "
            f"{declared[indexing.EMBEDDING_MODEL_ENV]!r} but configured_embedding_scope() reports "
            f"{scope.embedding_model!r}: the declared value did not reach the profile this "
            f"process embeds with. Migration {EMBEDDING_PROFILE_MIGRATION_VERSION} stops until "
            "they agree."
        )
    return scope


def _alter_database_statement(connection: Any, guc_name: str, value: str) -> str:
    """Ask the server to write out the ALTER DATABASE statement that declares one setting.

    ``guc_name`` is one of the two literals this module defines and nothing else; the database
    name and the value are quoted by PostgreSQL itself, so a name that contains a quote, a space
    or a semicolon cannot break out of the statement it appears in.
    """
    if guc_name not in (EMBEDDING_DIMENSION_GUC, EMBEDDING_MODEL_GUC):
        raise ValueError(f"unsupported embedding profile setting: {guc_name}")
    rows = connection.execute(
        _FORMAT_ALTER_DATABASE_SQL,
        (f"ALTER DATABASE %I SET {guc_name} = %L", value),
    ).fetchall()
    if not rows:
        raise EmbeddingProfileError(
            f"the server did not compose the statement that declares {guc_name}"
        )
    statement = _row_value(rows[0], 0, "statement")
    if not statement.upper().startswith("ALTER DATABASE "):
        raise EmbeddingProfileError(
            f"unexpected statement returned for {guc_name}: {statement!r}"
        )
    return statement


def provision_embedding_scope(connection: Any) -> tuple[str, int, str] | None:
    """Declare the runtime embedding profile on the database that is being migrated.

    This is the runbook command, issued by the runner: ``ALTER DATABASE <current_database()>
    SET app.embedding_dimension = ...``, together with the matching ``app.embedding_model``,
    because R22 binds a database to one model + width pair and 0010 refuses a width that arrives
    without a model to go with it.

    The durable half serves every session after this one; the transaction-local half serves the
    session that is about to run 0010, since database-level defaults only apply when a session
    starts. Returns ``(database_name, dimension, model)``.

    A connection that cannot answer ``SELECT current_database()`` is not a PostgreSQL session --
    that is how the offline fake-connection tests reach 0010's SQL at all -- so the function
    warns and returns ``None`` instead of provisioning. A live server always answers, which is
    what keeps the fail-closed checks in :func:`declared_embedding_profile` unavoidable there.
    That fail-open shape is accepted on those terms and not one wider: a live server always
    answers ``current_database()``, and a database that really is missing a width still stops,
    because refusing it is written into 0010 itself. The warning serves an offline fake
    connection; it is not an escape hatch for a deployment.

    Where the database already declares a different value, what this function changes is the
    declaration, not the data: it rewrites the database-level pair to the runtime profile and
    warns. Vectors already stored are guarded by 0010's own type check on ``chunks.embedding``,
    which refuses a second width in one database. The GUC is not that line of defence, so this
    function neither revalidates nor rewrites what is already embedded.
    """
    rows = connection.execute(_PROBE_EMBEDDING_PROFILE_SQL).fetchall()
    if not rows:
        logger.warning(
            "[Migrations] this connection did not answer current_database(), so the embedding "
            f"profile was not declared for migration {EMBEDDING_PROFILE_MIGRATION_VERSION}. "
            "Nothing was guessed: that migration still refuses a live database whose width is "
            "undeclared."
        )
        return None

    probe = rows[0]
    database_name = _row_value(probe, 0, "database_name")
    if not database_name:
        raise EmbeddingProfileError(
            "current_database() returned an empty name, so no ALTER DATABASE statement is safe "
            f"to issue for migration {EMBEDDING_PROFILE_MIGRATION_VERSION}"
        )

    scope = declared_embedding_profile(database_name)
    profile = (
        (EMBEDDING_DIMENSION_GUC, str(scope.dimension), "embedding_dimension"),
        (EMBEDDING_MODEL_GUC, str(scope.embedding_model), "embedding_model"),
    )
    for position, (guc_name, value, column) in enumerate(profile, start=1):
        existing = _row_value(probe, position, column)
        if existing and existing != value:
            logger.warning(
                f"[Migrations] {guc_name} on database {database_name} was {existing!r}; the "
                f"runtime profile declares {value!r}, which is the profile migration "
                f"{EMBEDDING_PROFILE_MIGRATION_VERSION} will be applied under. Vectors already "
                "stored are policed by that migration, not relabelled here."
            )
        connection.execute(_alter_database_statement(connection, guc_name, value))

    connection.execute(
        _DECLARE_PROFILE_FOR_TRANSACTION_SQL,
        (
            EMBEDDING_DIMENSION_GUC,
            str(scope.dimension),
            EMBEDDING_MODEL_GUC,
            str(scope.embedding_model),
        ),
    )

    visible_rows = connection.execute(_PROBE_EMBEDDING_PROFILE_SQL).fetchall()
    if not visible_rows:
        raise EmbeddingProfileError(
            f"this connection stopped answering current_setting() after {EMBEDDING_DIMENSION_GUC} "
            f"and {EMBEDDING_MODEL_GUC} were declared; refusing to start migration "
            f"{EMBEDDING_PROFILE_MIGRATION_VERSION} with a profile it cannot read back"
        )
    visible = visible_rows[0]
    width = _row_value(visible, 1, "embedding_dimension")
    model = _row_value(visible, 2, "embedding_model")
    if width != str(scope.dimension) or model != str(scope.embedding_model):
        raise EmbeddingProfileError(
            f"the declared profile is not visible to the session that migrates: "
            f"{EMBEDDING_DIMENSION_GUC} reads {width!r} and {EMBEDDING_MODEL_GUC} reads "
            f"{model!r}, expected {scope.dimension} and {scope.embedding_model!r}. Refusing to "
            f"start migration {EMBEDDING_PROFILE_MIGRATION_VERSION} on a database it cannot see "
            "the profile of."
        )
    return database_name, scope.dimension, scope.embedding_model


def apply_migrations(
    connection: Any,
    database_name: str,
    *,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> list[Migration]:
    """Apply pending migrations in one explicit transaction and record checksums.

    The caller owns connection creation and error reporting. PostgreSQL's
    transaction-scoped advisory lock prevents concurrent deployment runners from
    applying the same migration set at once.

    Migration 0010 is preceded by :func:`provision_embedding_scope` because it cannot pick a
    vector width out of thin air. That happens once per application of 0010, so re-running the
    runner against the same database declares nothing and changes nothing. Both the ledger work
    and the declaration sit inside the advisory lock and this one transaction, so a run that
    stops leaves the database no further along than it found it.
    """
    lock_key = migration_lock_key(database_name)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
        connection.execute(_CREATE_LEDGER_SQL)
        result = connection.execute(_SELECT_LEDGER_SQL)
        pending = migration_plan(_ledger_checksums(result.fetchall()), migrations=migrations)
        for migration in pending:
            if migration.version == EMBEDDING_PROFILE_MIGRATION_VERSION:
                provision_embedding_scope(connection)
            connection.execute(migration.sql)
            connection.execute(
                _INSERT_LEDGER_SQL,
                (migration.version, migration.name, migration.checksum),
            )
    return pending
