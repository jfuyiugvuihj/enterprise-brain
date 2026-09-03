import os
import secrets

ALLOWED_ROLES = {"staff", "manager", "admin"}


def sso_enabled() -> bool:
    return os.getenv("SSO_ENABLED", "0").lower() in {"1", "true", "yes", "on"}


def normalize_role(role: str | None) -> str:
    role = (role or "staff").strip().lower()
    return role if role in ALLOWED_ROLES else "staff"


def validate_sso_headers(headers: dict) -> bool:
    if not sso_enabled():
        return False
    expected = os.getenv("SSO_SHARED_TOKEN", "").strip()
    if not expected:
        return True
    provided = (
        headers.get("X-SSO-Token")
        or headers.get("x-sso-token")
        or headers.get("X-Auth-Request-Token")
        or headers.get("x-auth-request-token")
        or ""
    )
    return secrets.compare_digest(provided, expected)


def extract_sso_identity(headers: dict) -> dict | None:
    username = (
        headers.get("X-SSO-User")
        or headers.get("x-sso-user")
        or headers.get("X-Forwarded-User")
        or headers.get("x-forwarded-user")
        or ""
    ).strip()
    if not username:
        return None

    return {
        "username": username,
        "role": normalize_role(headers.get("X-SSO-Role") or headers.get("x-sso-role")),
        "department": (
            headers.get("X-SSO-Department")
            or headers.get("x-sso-department")
            or ""
        ).strip(),
        "display_name": (
            headers.get("X-SSO-Display-Name")
            or headers.get("x-sso-display-name")
            or username
        ).strip(),
    }
