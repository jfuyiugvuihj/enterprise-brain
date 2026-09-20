"""Database boundary package for the PostgreSQL target architecture."""

from app.db.connection import DatabaseSettings, parse_database_settings

__all__ = ["DatabaseSettings", "parse_database_settings"]
