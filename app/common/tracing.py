import os

_SENSITIVE_KEYS = {"password", "passwd", "jwt", "token", "api_key", "apikey", "secret"}


def sanitize_trace_event(event: dict) -> dict:
    def clean(value):
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(event or {})


def build_tracing_config() -> dict:
    enabled = os.getenv("LANGSMITH_TRACING", "false").lower() in {"1", "true", "yes", "on"}
    return {
        "enabled": enabled,
        "project": os.getenv("LANGSMITH_PROJECT", "enterprise-brain"),
        "api_url": os.getenv("LANGSMITH_ENDPOINT", ""),
    }
