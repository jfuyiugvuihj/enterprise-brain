"""Compatibility import for the canonical Agent contract Principal.

All new code must import Principal from `app.agents.contracts`; this module remains
for existing API and tool callers during the migration window.
"""

from app.agents.contracts import Principal

__all__ = ["Principal"]
