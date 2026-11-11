"""Operator-declared department names shared by resource, table and retrieval gates."""

import json
import os


DEPARTMENT_ALIASES_ENV = "DEPARTMENT_ALIASES_JSON"


def department_aliases() -> dict[str, str]:
    """Invalid or absent configuration grants no aliases (the strict legacy behavior)."""
    try:
        payload = json.loads(os.getenv(DEPARTMENT_ALIASES_ENV, "{}"))
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    aliases = {}
    for raw_alias, raw_canonical in payload.items():
        if not isinstance(raw_alias, str) or not isinstance(raw_canonical, str):
            return {}
        alias, canonical = raw_alias.strip(), raw_canonical.strip()
        if not alias or not canonical or alias == canonical:
            return {}
        aliases[alias] = canonical
    # Chained aliases make the effective authorization depend on iteration order.
    if set(aliases).intersection(aliases.values()):
        return {}
    return aliases


def canonical_department(value: str) -> str:
    name = str(value or "").strip()
    return department_aliases().get(name, name)


def department_names(canonical: str) -> set[str]:
    """Names that may identify this one department in a stored document index."""
    name = canonical_department(canonical)
    if not name:
        return set()
    return {name, *(alias for alias, target in department_aliases().items() if target == name)}
