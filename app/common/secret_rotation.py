import re
import secrets
from pathlib import Path


def generate_jwt_secret(length: int = 64) -> str:
    return secrets.token_hex(max(32, length // 2))[:length]


def rotate_jwt_secret(env_path: str | Path) -> str:
    path = Path(env_path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    secret = generate_jwt_secret()
    replacement = f"JWT_SECRET_KEY={secret}"
    if re.search(r"^JWT_SECRET_KEY=.*$", content, flags=re.MULTILINE):
        content = re.sub(
            r"^JWT_SECRET_KEY=.*$",
            replacement,
            content,
            flags=re.MULTILINE,
        )
    else:
        content = content.rstrip("\n") + ("\n" if content else "") + replacement + "\n"
    path.write_text(content, encoding="utf-8")
    return secret
