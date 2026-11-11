"""R694 走查共享件。

只读产品码：本模块不 import ``app``，不连容器，不开浏览器。它管四件事——
按**键名**从 env 文件取值（值只在内存里流动，永不打印）、账本落盘、
截图逐枚登记（文件名＋字节数＋取图时刻）、控制符与坐标卫生扫描。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ENV_LINE = re.compile(r"^([A-Za-z0-9_]+)=(.*)$")
#: compose 对 env 文件做变量插值，``$$`` 才是字面 ``$``；按键名取值要还原这一步。
COMPOSE_LITERAL_DOLLAR = "$$"

#: 账面里不许出现的 ASCII 控制符（换行之外）。
FORBIDDEN_CONTROLS = (0x00, 0x07, 0x08, 0x0B, 0x0C, 0x1B)

#: 「文件:数字」形态的手抄坐标，判据要求坐标一律 ``文件::符号``。
BARE_LINE_COORDINATE = re.compile(r"[\w./\\-]+\.(?:py|vue|js|ts|md|json|sql|yml|yaml):\d+")


def read_env_keys(path: str | Path) -> dict[str, str]:
    """按行取回 ``KEY=VALUE``，还原 compose 的 ``$$`` 转义；不打印任何值。"""
    out: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        match = ENV_LINE.match(raw.strip())
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        out[key] = value.replace(COMPOSE_LITERAL_DOLLAR, "$")
    return out


def env_key(path: str | Path, name: str) -> str:
    keys = read_env_keys(path)
    if name not in keys:
        raise KeyError("env 文件缺键名 " + name)
    return keys[name].strip()


def stamp() -> str:
    """本地时钟读数，秒级，带时区偏移。写进账本的每一枚时刻都是这个形状。

    偏移直接取系统那枚带符号的读数（``astimezone().utcoffset()`` 走 ``%z``）：
    ``time.timezone`` 用的是「UTC 以西为正」的旧约定，与 ISO-8601 反号，抄错就把
    12:45 记成隔天 04:45——走查的起止秒数全部跟着错。
    """
    now = datetime.now().astimezone()
    zone = now.strftime("%z")
    return "%s%s:%s" % (now.strftime("%Y-%m-%dT%H:%M:%S"), zone[:3], zone[3:])


def epoch() -> float:
    return round(time.time(), 3)


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def is_external(url: str) -> bool:
    """除本站原点与空主机（data:/blob:）之外的一切域名都算外部。"""
    host = host_of(url)
    if not host:
        return False
    return host not in {"localhost", "127.0.0.1", "[::1]", "::1"}


class Ledger:
    """逐环账本：每一环跑完立刻落盘，崩在半路也不丢已经取到的读数。"""

    def __init__(self, path: str | Path, fresh: bool = False) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {"rings": [], "faces": [], "notes": []}
        if self.path.is_file() and not fresh:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def record(self, bucket: str, entry: dict[str, Any]) -> None:
        entry.setdefault("taken_at", stamp())
        ring = entry.get("ring")
        bucket_items = [e for e in self.data.get(bucket, []) if e.get("ring") != ring]
        bucket_items.append(entry)
        self.data[bucket] = sorted(bucket_items, key=lambda e: (e.get("ring") is None, e.get("ring", "")))
        self.data[bucket] = self.data[bucket]
        self.save()

    def note(self, text: str) -> None:
        self.data.setdefault("notes", []).append({"at": stamp(), "text": text})
        self.save()

    def set_root(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


#: 一枚截图的上限。``page.screenshot()`` 默认没有超时：页面卡在半截导航或常亮动画上时，
#: 整场走查就挂在那里，九环交不回任何读数（10-07 13:44 现读，环 7 的对照探针挂死 15 分钟，
#: 账本里没有 rings[7]，屏上其实早就答完了）。取不到图就把这一格明说取不到，不许挂住全场。
SHOT_TIMEOUT_MS = 20000


def register_shot(page: Any, out_dir: str | Path, name: str, **kwargs: Any) -> dict[str, Any]:
    """截图落盘并登记：文件名、字节数、取图时刻、视口；取不到就记 error，不抛、不挂。"""
    timeout = kwargs.pop("timeout", SHOT_TIMEOUT_MS)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / name
    try:
        page.screenshot(path=str(target), timeout=timeout, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 证据少一张只许记账，不许把整场跑挂住
        return {
            "file": name,
            "bytes": target.stat().st_size if target.exists() else 0,
            "sha256_8": "",
            "taken_at": stamp(),
            "error": "%s after %dms" % (type(exc).__name__, timeout),
            "viewport": getattr(page, "viewport_size", None),
        }
    return {
        "file": name,
        "bytes": target.stat().st_size,
        "sha256_8": hashlib.sha256(target.read_bytes()).hexdigest()[:8],
        "taken_at": stamp(),
        "viewport": getattr(page, "viewport_size", None),
    }


def control_char_counts(text: str) -> dict[str, int]:
    return {"0x%02x" % code: text.count(chr(code)) for code in FORBIDDEN_CONTROLS}


def bare_coordinates(text: str) -> list[str]:
    return sorted({m.group(0) for m in BARE_LINE_COORDINATE.finditer(text)})


def seconds_since(t0: float) -> float:
    return round(time.time() - t0, 3)


def wait_for(predicate: Any, timeout_s: float, poll_s: float = 0.25) -> Any:
    """阻塞式等待：谓词返回真值就把它交回来，超时返回 ``None``。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(poll_s)
    return None


__all__ = [
    "Ledger",
    "bare_coordinates",
    "control_char_counts",
    "env_key",
    "epoch",
    "host_of",
    "is_external",
    "read_env_keys",
    "register_shot",
    "seconds_since",
    "stamp",
    "wait_for",
]
