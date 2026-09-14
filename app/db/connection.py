"""Offline-safe database configuration and connection boundary.

This module validates configuration and exposes a connection factory contract. It does
not connect or create schema during import; deployment code must call that explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    scheme: str
    host: str
    port: int | None
    database: str
    sslmode: str | None = None

    @property
    def is_postgresql(self) -> bool:
        return self.scheme in {"postgresql", "postgres"}


def parse_database_settings(url: str) -> DatabaseSettings:
    value = (url or "").strip()
    if not value:
        raise ValueError("DATABASE_URL is required")
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"postgresql", "postgres"}:
        raise ValueError("only PostgreSQL URLs are supported by the production boundary")
    if not parsed.hostname:
        raise ValueError("database host is required")
    if not parsed.path or parsed.path == "/":
        raise ValueError("database name is required")
    return DatabaseSettings(
        url=value,
        scheme=scheme,
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/"),
        sslmode=dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair).get("sslmode"),
    )


def open_connection(settings: DatabaseSettings):
    """Create a psycopg connection only when an integration caller explicitly asks."""
    import psycopg

    return psycopg.connect(settings.url)
