"""Business metric definitions, read from PostgreSQL with a code fallback.

``metric_definitions`` (migrations/0002_execution_data_lineage.sql:72) is the
authoritative store for what a business metric means, so adding, retuning or retiring
a definition is a data change rather than a code change. The rules at the bottom of
this module are only the fallback for a deployment whose database is offline or whose
catalog has no row yet, and they stay deliberately small.

Two invariants are kept on purpose:

* Provenance never overstates itself. The table has no column that records a
  reconciliation against an uploaded policy document, so every definition - table row
  or code fallback - carries an "未与已上传制度文件核对" warning. Storing a flag inside a
  row's JSONB does not remove it, because a self-declared flag is not evidence.
* Nothing connects at import time. ``_database_available`` and ``_conn`` follow the
  lazy pattern of app/documents/catalog.py but stay closed until the application itself
  reports a ready PostgreSQL, and writes happen only when a caller asks
  (``sync_code_definitions`` / ``register_metric_definition``), never while a question
  is being answered.

The table carries the calculation contract (formula, unit, period, currency, timezone,
source scope, filters, status) but has no column for the display label, the prose
definition, or the business wording a question is matched against. Those travel inside the
``filters`` JSONB under the reserved ``semantics`` key and are stripped from the filters a
caller sees. Promoting them into real columns needs a migration, which this slice does not
own: the draft is left for whoever numbers migrations next.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from app.agents.contracts import MetricContext
from app.common.logger import logger

DEFINITION_VERSION = "semantic-registry-v1"

TABLE_NAME = "metric_definitions"
SOURCE_TABLE = "metric_definitions"
SOURCE_CODE = "code_registry"
SYSTEM_OWNER_ID = "system"
ACTIVE_STATUSES = frozenset({"active", "published", "current"})

# Reserved key inside the ``filters`` JSONB; see the module docstring.
SEMANTICS_KEY = "semantics"

_CODE_WARNING = "定义来自代码语义注册表，未与已上传制度文件核对"
_TABLE_WARNING = "定义来自指标定义表 metric_definitions，未与已上传制度文件核对"
_SEEDED_WARNING = "定义由代码语义注册表同步进 metric_definitions，未与已上传制度文件核对"

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_db_available: bool | None = None
# The last catalog read failure this process reported, so a missing or half-migrated
# table does not add a warning to the log for every single question.
_last_read_failure: str | None = None

_SELECT_COLUMNS = (
    "metric_definition_id",
    "owner_id",
    "metric_id",
    "definition_version",
    "formula",
    "unit",
    "currency",
    "period_type",
    "timezone",
    "source_scope",
    "filters",
    "status",
)

# The table is written with exactly the columns migration 0002 declares; no new
# column, no new migration.
_INSERT_COLUMNS = _SELECT_COLUMNS
_JSON_COLUMNS = frozenset({"source_scope", "filters"})
_UNIQUE_COLUMNS = ("owner_id", "metric_id", "definition_version")
_IMMUTABLE_COLUMNS = frozenset({"metric_definition_id", *_UNIQUE_COLUMNS})

_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_LATIN_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{2,}")
_SPLIT_RE = re.compile(r"[.\s_/]+")


@dataclass(frozen=True)
class MetricDefinition:
    """One definition plus the provenance needed to say where it came from."""

    metric_id: str
    metric_name: str
    definition: str
    definition_version: str
    formula: str
    unit: str
    period_type: str
    timezone: str
    time_granularity: str
    match_terms: tuple[str, ...]
    source: str
    warnings: tuple[str, ...]
    currency: str | None = None
    status: str = "active"
    definition_id: str = ""
    owner_id: str = ""
    origin: str = ""
    source_scope: tuple[str, ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)

    @property
    def verified_against_documents(self) -> bool:
        """False for every definition: the table cannot record such a check."""
        return False

    def to_context(self) -> MetricContext:
        return MetricContext(
            metric_id=self.metric_id,
            metric_name=self.metric_name,
            definition=self.definition,
            definition_version=self.definition_version,
            formula=self.formula,
            unit=self.unit,
            currency=self.currency,
            period_type=self.period_type,
            timezone=self.timezone,
            time_granularity=self.time_granularity,
            source_file="",
            source_scope=list(self.source_scope),
            filters=dict(self.filters),
            warnings=list(self.warnings),
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "origin": self.origin or self.source,
            "definition_id": self.definition_id,
            "owner_id": self.owner_id,
            "definition_version": self.definition_version,
            "status": self.status,
            "verified_against_documents": self.verified_against_documents,
            "warnings": list(self.warnings),
        }

    def to_public(self) -> dict[str, Any]:
        payload = self.to_context().model_dump()
        payload["status"] = self.status
        payload["provenance"] = self.provenance()
        return payload


def default_timezone() -> str:
    return (os.getenv("APP_TIMEZONE") or "Asia/Shanghai").strip() or "UTC"


def default_currency() -> str:
    return (os.getenv("APP_DEFAULT_CURRENCY") or "CNY").strip() or "CNY"


def system_owner_id() -> str:
    """The owner namespace the shared, machine-wide catalog is seeded under."""
    return (os.getenv("METRIC_DEFINITION_OWNER_ID") or SYSTEM_OWNER_ID).strip() or SYSTEM_OWNER_ID


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return list(parsed) if isinstance(parsed, list) else []
    return []


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _dedupe(terms: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        value = str(term or "").strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return tuple(ordered)


def _display_name(metric_id: str) -> str:
    """Best available label for a row that never recorded one."""
    parts = [part for part in _SPLIT_RE.split(str(metric_id or "").strip()) if part]
    return parts[-1] if parts else str(metric_id or "").strip()


def _derived_terms(*texts: Any) -> tuple[str, ...]:
    """Wording a row can be recognised by when nobody listed terms explicitly.

    A metric_id such as ``收入.销售额`` or a formula such as ``销售额合计`` says what it is
    called, so a plain insert stays findable without editing code. Explicit
    ``match_terms`` remain the precise, preferred form.
    """
    terms: list[str] = []
    for text in texts:
        value = str(text or "")
        if not value.strip():
            continue
        terms.extend(_CJK_TERM_RE.findall(value))
        terms.extend(_LATIN_TERM_RE.findall(value))
        terms.extend(part for part in _SPLIT_RE.split(value) if len(part.strip()) >= 2)
    return _dedupe(terms)


_METRIC_RULES = [
    {
        "keywords": ("住宿费", "住宿标准", "住宿费标准"),
        "metric_id": "expense.accommodation.standard",
        "metric_name": "住宿费标准",
        "definition": "公司制度规定的单晚住宿上限",
        "formula": "单晚住宿费用 <= 制度标准",
        "unit": "元/晚",
        "period_type": "single",
        "time_granularity": "单笔",
        "aliases": ("住宿", "差旅住宿", "差旅费"),
    },
    {
        "keywords": ("差旅费", "差旅费用"),
        "metric_id": "expense.travel.total",
        "metric_name": "差旅费",
        "definition": "员工因出差产生的住宿、交通、餐饮等合规费用",
        "formula": "差旅费用合计",
        "unit": "元",
        "period_type": "month",
        "time_granularity": "月",
        "aliases": ("出差",),
    },
]


def _code_definitions() -> list[MetricDefinition]:
    timezone = default_timezone()
    currency = default_currency()
    owner_id = system_owner_id()
    definitions: list[MetricDefinition] = []
    for rule in _METRIC_RULES:
        definitions.append(
            MetricDefinition(
                metric_id=rule["metric_id"],
                metric_name=rule["metric_name"],
                definition=rule["definition"],
                definition_version=DEFINITION_VERSION,
                formula=rule["formula"],
                unit=rule["unit"],
                currency=currency,
                period_type=rule["period_type"],
                timezone=timezone,
                time_granularity=rule.get("time_granularity", ""),
                # The fallback matches on exactly the wording it always matched on.
                match_terms=_dedupe(tuple(rule["keywords"]) + tuple(rule.get("aliases", ()))),
                source=SOURCE_CODE,
                warnings=(_CODE_WARNING,),
                definition_id=f"code:{rule['metric_id']}",
                owner_id=owner_id,
                origin=SOURCE_CODE,
            )
        )
    return definitions


def code_metric_ids() -> tuple[str, ...]:
    """Metric ids the code fallback knows about, in declaration order."""
    return tuple(rule["metric_id"] for rule in _METRIC_RULES)


def _definition_from_row(row: dict[str, Any]) -> MetricDefinition | None:
    metric_id = str(row.get("metric_id") or "").strip()
    if not metric_id:
        logger.warning("[Semantics] ignoring a metric_definitions row without metric_id")
        return None
    stored_filters = _json_object(row.get("filters"))
    semantics = _json_object(stored_filters.get(SEMANTICS_KEY))
    filters = {key: value for key, value in stored_filters.items() if key != SEMANTICS_KEY}
    metric_name = str(semantics.get("metric_name") or "").strip() or _display_name(metric_id)
    formula = str(row.get("formula") or "").strip()
    definition_text = str(semantics.get("definition_text") or "").strip() or formula
    explicit_terms = _dedupe(_json_list(semantics.get("match_terms")))
    origin = str(semantics.get("origin") or "").strip()
    warnings = (_SEEDED_WARNING,) if origin == SOURCE_CODE else (_TABLE_WARNING,)
    return MetricDefinition(
        metric_id=metric_id,
        metric_name=metric_name,
        definition=definition_text,
        definition_version=str(row.get("definition_version") or "").strip(),
        formula=formula,
        unit=str(row.get("unit") or "").strip(),
        currency=str(row.get("currency") or "").strip() or default_currency(),
        period_type=str(row.get("period_type") or "").strip(),
        timezone=str(row.get("timezone") or "").strip() or default_timezone(),
        time_granularity=str(semantics.get("time_granularity") or "").strip(),
        match_terms=explicit_terms or _derived_terms(metric_id, metric_name, definition_text, formula),
        source=SOURCE_TABLE,
        warnings=warnings,
        status=(str(row.get("status") or "").strip() or "active"),
        definition_id=str(row.get("metric_definition_id") or "").strip(),
        owner_id=str(row.get("owner_id") or "").strip(),
        origin=origin or SOURCE_TABLE,
        source_scope=tuple(str(item) for item in _json_list(row.get("source_scope")) if str(item).strip()),
        filters=filters,
    )


def _database_available() -> bool:
    """Report the application's own database health, never a probe of this module's.

    Unlike app/documents/catalog.py this stays closed until the app has said the
    database is ready: a definition catalog is consulted on every question, and neither
    a test run nor an offline caller may open a connection or pay a connect timeout for
    it. The catalog is therefore read only inside a process that already has PostgreSQL.
    """
    if _db_available is False:
        # A connection already failed in this process; stop paying the timeout per question.
        return False
    auth_module = sys.modules.get("app.common.auth")
    if auth_module is not None:
        return bool(getattr(auth_module, "_db_ready", False))
    return False


def _conn():
    """Open a connection on demand. Importing this module never calls this."""
    global _db_available
    import psycopg
    from psycopg.rows import dict_row

    try:
        connection = psycopg.connect(_PG_URL, row_factory=dict_row, connect_timeout=1)
    except Exception:
        _db_available = False
        raise
    _db_available = True
    return connection


def _close(connection: Any) -> None:
    if connection is not None and hasattr(connection, "close"):
        try:
            connection.close()
        except Exception:
            pass


def _query(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Read rows, returning nothing on any failure.

    A definition catalog must never be the reason an answer fails: when the table
    cannot be read the caller falls back to the code rules and the fallback says so.
    """
    global _last_read_failure
    connection = None
    try:
        connection = _conn()
        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows or []]
    except Exception as exc:
        failure = f"{type(exc).__name__}: {exc}"
        if failure != _last_read_failure:
            logger.warning(f"[Semantics] metric_definitions read failed, using code fallback: {failure}")
            _last_read_failure = failure
        return []
    finally:
        _close(connection)


def _insert_row(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    """Run one catalog insert and report its RETURNING row, or None when nothing was written.

    Failures reach the caller: unlike a read, a write was explicitly asked for, and
    swallowing it would let an operator believe a definition had been recorded.
    """
    connection = None
    try:
        connection = _conn()
        row = connection.execute(sql, params).fetchone()
        connection.commit()
        return dict(row) if row else None
    except Exception:
        if connection is not None and hasattr(connection, "rollback"):
            try:
                connection.rollback()
            except Exception:
                pass
        raise
    finally:
        _close(connection)


def _owner_ids(owner_id: str | None) -> list[str]:
    system = system_owner_id()
    owners = [system]
    value = str(owner_id or "").strip()
    if value and value != system:
        owners.insert(0, value)
    return owners


def _table_definitions(owner_id: str | None = None) -> list[MetricDefinition]:
    """Catalog rows the caller may use, oldest first, exactly as stored."""
    if not _database_available():
        return []
    owners = _owner_ids(owner_id)
    placeholders = ", ".join(["%s"] * len(owners))
    sql = (
        f"SELECT {', '.join(_SELECT_COLUMNS)} FROM {TABLE_NAME} "
        f"WHERE owner_id IN ({placeholders}) "
        "ORDER BY created_at ASC, metric_definition_id ASC"
    )
    definitions: list[MetricDefinition] = []
    for row in _query(sql, tuple(owners)):
        definition = _definition_from_row(row)
        if definition is not None:
            definitions.append(definition)
    return definitions


def _overrides(candidate: MetricDefinition, current: MetricDefinition) -> bool:
    """A caller's own row beats the shared one; inside one namespace the newer row wins."""
    system = system_owner_id()
    candidate_scope = 0 if candidate.owner_id == system else 1
    current_scope = 0 if current.owner_id == system else 1
    return candidate_scope >= current_scope


def effective_definitions(owner_id: str | None = None) -> list[MetricDefinition]:
    """The catalog a question is answered from: table rows first, code rules as fallback.

    A metric the table knows about is never answered from the code list, not even when
    its status is retired: an explicit row is the operator's answer about that metric,
    and resurrecting it from code would silently undo a curation decision.
    """
    by_metric: dict[str, MetricDefinition] = {}
    for definition in _table_definitions(owner_id):
        current = by_metric.get(definition.metric_id)
        if current is None or _overrides(definition, current):
            by_metric[definition.metric_id] = definition
    active = [item for item in by_metric.values() if item.status in ACTIVE_STATUSES]
    fallback = [item for item in _code_definitions() if item.metric_id not in by_metric]
    return active + fallback


def match_definition(question: str, owner_id: str | None = None) -> MetricDefinition | None:
    """Find the definition whose business wording fits a question best.

    The longest hit wins, so ``住宿费标准`` beats the shorter ``差旅费`` alias the
    accommodation rule carries. Table rows are scanned before fallback rules, so a
    table row and a code rule that tie on term length resolve to the table row.
    """
    haystack = (question or "").strip().lower()
    if not haystack:
        return None
    best: MetricDefinition | None = None
    best_length = 0
    for definition in effective_definitions(owner_id):
        for term in definition.match_terms:
            needle = term.lower()
            if not needle or (best is not None and len(needle) <= best_length):
                continue
            if needle in haystack:
                best = definition
                best_length = len(needle)
    return best


def match_metric_context(question: str, owner_id: str | None = None) -> MetricContext | None:
    """The context the agents and routes already consume, table-backed when possible."""
    definition = match_definition(question, owner_id)
    return definition.to_context() if definition is not None else None


def match_metric_definition(question: str, owner_id: str | None = None) -> dict[str, Any] | None:
    """A match plus its provenance, for callers that must report the source."""
    definition = match_definition(question, owner_id)
    if definition is None:
        return None
    return {"context": definition.to_context(), "definition": definition.to_public()}


def metric_catalog(owner_id: str | None = None) -> dict[str, Any]:
    """The whole definition catalog, so a caller never has to guess a metric word."""
    definitions = effective_definitions(owner_id)
    from_table = sum(1 for item in definitions if item.source == SOURCE_TABLE)
    return {
        "metrics": [item.to_public() for item in definitions],
        "definition_sources": {
            SOURCE_TABLE: from_table,
            SOURCE_CODE: len(definitions) - from_table,
        },
        "definition_versions": sorted(
            {item.definition_version for item in definitions if item.definition_version}
        ),
        "database_available": _database_available(),
        # metric_definitions has no column that records a reconciliation with an
        # uploaded policy document, so no catalog can honestly claim one.
        "verified_against_documents": False,
        "warnings": sorted({warning for item in definitions for warning in item.warnings}),
    }


def _row_values(definition: MetricDefinition, owner_id: str, definition_id: str) -> dict[str, Any]:
    semantics = {
        "metric_name": definition.metric_name,
        "definition_text": definition.definition,
        "time_granularity": definition.time_granularity,
        "match_terms": list(definition.match_terms),
        "origin": definition.origin or definition.source,
    }
    return {
        "metric_definition_id": definition_id,
        "owner_id": owner_id,
        "metric_id": definition.metric_id,
        "definition_version": definition.definition_version,
        "formula": definition.formula,
        "unit": definition.unit,
        "currency": definition.currency,
        "period_type": definition.period_type,
        "timezone": definition.timezone,
        "source_scope": list(definition.source_scope),
        "filters": {**definition.filters, SEMANTICS_KEY: semantics},
        "status": definition.status,
    }


def _insert_statement(overwrite: bool) -> str:
    columns = ", ".join(_INSERT_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_INSERT_COLUMNS))
    conflict = ", ".join(_UNIQUE_COLUMNS)
    if not overwrite:
        # RETURNING comes back empty for a row the conflict rule skipped, which is how the
        # caller tells an insert from a no-op without counting affected rows.
        return (
            f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO NOTHING RETURNING metric_definition_id"
        )
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in _INSERT_COLUMNS
        if column not in _IMMUTABLE_COLUMNS
    )
    return (
        f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {assignments} "
        # xmax = 0 is PostgreSQL's own answer to "did this statement create the row".
        "RETURNING metric_definition_id, (xmax = 0) AS is_new"
    )


def _store_row(values: dict[str, Any], *, overwrite: bool) -> tuple[str, str | None]:
    """Write one catalog row as ``outcome, metric_definition_id``.

    The outcome is ``inserted``, ``updated``, ``unchanged``, ``failed`` or ``skipped``.
    ``overwrite=False`` is what makes the sync idempotent in the strongest sense: a row an
    operator already edited is left exactly as it is.
    """
    if not _database_available():
        return "skipped", None
    params = tuple(
        _dump_json(values[column]) if column in _JSON_COLUMNS else values[column]
        for column in _INSERT_COLUMNS
    )
    try:
        row = _insert_row(_insert_statement(overwrite), params)
    except Exception as exc:
        logger.warning(f"[Semantics] metric_definitions write failed: {type(exc).__name__}: {exc}")
        return "failed", None
    if row is None:
        return "unchanged", None
    stored_id = str(row.get("metric_definition_id") or "").strip() or None
    if "is_new" in row:
        return ("inserted" if row.get("is_new") else "updated"), stored_id
    return "inserted", stored_id


def _counts(outcomes: list[str]) -> dict[str, int]:
    return {
        key: outcomes.count(key)
        for key in ("inserted", "updated", "unchanged", "failed", "skipped")
    }


def sync_code_definitions(*, owner_id: str | None = None) -> dict[str, Any]:
    """Mirror the fallback rules into metric_definitions without clobbering any curation.

    Row ids are derived from (owner, metric, version), and the insert uses
    ``ON CONFLICT DO NOTHING``, so running this twice writes nothing the second time and
    a row recorded under another definition_version stays as history.
    """
    owner = (owner_id or system_owner_id()).strip() or system_owner_id()
    definitions = _code_definitions()
    outcomes: list[str] = []
    stored_ids: dict[str, str | None] = {}
    for definition in definitions:
        definition_id = f"md:{owner}:{definition.metric_id}:{definition.definition_version}"
        outcome, stored_id = _store_row(_row_values(definition, owner, definition_id), overwrite=False)
        outcomes.append(outcome)
        stored_ids[definition.metric_id] = stored_id
    return {
        "owner_id": owner,
        "database_available": _database_available(),
        "total": len(definitions),
        **_counts(outcomes),
        "definition_ids": stored_ids,
    }


def register_metric_definition(
    *,
    metric_id: str,
    definition_version: str,
    formula: str,
    unit: str,
    period_type: str,
    metric_name: str = "",
    definition_text: str = "",
    match_terms: Any = (),
    currency: str | None = None,
    timezone: str | None = None,
    time_granularity: str = "",
    source_scope: Any = (),
    filters: dict[str, Any] | None = None,
    status: str = "active",
    owner_id: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Add or revise one catalog row: the no-code path for a new metric.

    The row is written with ``origin=operator``, which is what distinguishes a curated
    definition from one this module seeded from its own fallback rules.
    """
    metric = str(metric_id or "").strip()
    if not metric:
        raise ValueError("metric_id is required")
    owner = (owner_id or system_owner_id()).strip() or system_owner_id()
    version = str(definition_version or "").strip()
    terms = _dedupe(match_terms)
    definition = MetricDefinition(
        metric_id=metric,
        metric_name=str(metric_name or "").strip() or _display_name(metric),
        definition=str(definition_text or "").strip() or str(formula or "").strip(),
        definition_version=version,
        formula=str(formula or "").strip(),
        unit=str(unit or "").strip(),
        currency=str(currency or "").strip() or default_currency(),
        period_type=str(period_type or "").strip(),
        timezone=str(timezone or "").strip() or default_timezone(),
        time_granularity=str(time_granularity or "").strip(),
        match_terms=terms or _derived_terms(metric, metric_name, definition_text, formula),
        source=SOURCE_TABLE,
        warnings=(_TABLE_WARNING,),
        status=str(status or "active").strip() or "active",
        owner_id=owner,
        origin="operator",
        source_scope=tuple(str(item) for item in _json_list(source_scope) if str(item).strip()),
        filters={key: value for key, value in _json_object(filters).items() if key != SEMANTICS_KEY},
    )
    candidate_id = f"md:{uuid4().hex}"
    outcome, stored_id = _store_row(_row_values(definition, owner, candidate_id), overwrite=overwrite)
    return {
        "result": outcome,
        "owner_id": owner,
        # The id the table actually holds: the new row for an insert, the existing row's
        # own key when a revision updated it in place, None when nothing was written.
        "definition_id": stored_id,
        "definition": replace(definition, definition_id=stored_id or "").to_public(),
    }
