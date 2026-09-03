import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from app.common.logger import logger

_tz = timezone(timedelta(hours=8))


def build_im_payload(title: str, body: str, source: str = "system", severity: str = "info") -> dict:
    return {
        "title": title,
        "body": body,
        "source": source,
        "severity": severity,
        "timestamp": datetime.now(_tz).isoformat(),
    }


def send_im_notification(
    title: str,
    body: str,
    source: str = "system",
    severity: str = "info",
    webhook_url: str | None = None,
) -> bool:
    payload = build_im_payload(title, body, source=source, severity=severity)
    url = (webhook_url or os.getenv("IM_WEBHOOK_URL", "")).strip()
    if not url:
        logger.info(f"[IM] {title}: {body[:120]}")
        return False

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = int(getattr(resp, "status", 200)) < 400
        if ok:
            logger.info(f"[IM] sent: {title}")
        return ok
    except Exception as exc:
        logger.warning(f"[IM] send failed: {exc}")
        return False
