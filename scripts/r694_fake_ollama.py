"""R694 · 一次性 Ollama 门面：只把算力那一格改成 CPU，其余原样转发。

产品码判算力走两枚读数：``/api/ps``（在飞模型）与 ``/api/version``（启动答复），
设备词只在 ``device_type``/``library``/``processor``/``provider``/``compute``/``device_id``
这几枚键上认（``app/common/model_capabilities.py::_DEVICE_KEYS``），显存只在
``size_vram``/``vram_bytes`` 上认。本件就按那两枚键名交回 CPU 说法，并把 ``size_vram``
整枚省掉——交回一枚 ``size_vram: 0`` 会被读成「显存键在位」，那是另一种形状的证据。

推理本身不打这里过：临时 backend 的 ``LOCAL_MODEL_BASE_URL`` 仍指真 ollama，
所以「屏上文案」拿的是真回答，只有算力档位是伪的。

只用标准库，跑在 ``enterprise-brain:local`` 镜像里（容器内 11434）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("R694_UPSTREAM", "http://ollama:11434").rstrip("/")
LISTEN_PORT = int(os.environ.get("R694_PORT", "11434"))
MODEL_NAME = os.environ.get("R694_MODEL", "qwen3.5:9b")

#: 只让 ``/api/embeddings`` 与 ``/v1/embeddings`` 交回 503：embedding 腿断，其余原样转发。
BREAK_EMBEDDINGS = os.environ.get("R694_BREAK_EMBEDDINGS") == "1"
#: ``/api/ps`` 原样转发（不伪装算力）：给 embedding 那一案用，算力档位保持真实。
PASSTHROUGH_PS = os.environ.get("R694_PASSTHROUGH_PS") == "1"
EMBED_PATHS = ("/api/embeddings", "/v1/embeddings")

#: 伪装的 /api/ps：一枚常驻模型，设备写 cpu，显存键整枚不给。
PS_PAYLOAD = {
    "models": [
        {
            "name": MODEL_NAME,
            "model": MODEL_NAME,
            "size": 5_500_000_000,
            "digest": "r694-fake-cpu-digest",
            "details": {"family": "qwen2", "parameter_size": "9B", "quantization_level": "Q4_K_M"},
            "processor": "cpu",
            "device_type": "cpu",
            "expiry": "1970-01-01T00:00:00.000000Z",
            "used_memory": 5_500_000_000,
        }
    ]
}

#: 伪装的 /api/version：num_gpus 不给正数，设备词仍写 cpu。
VERSION_PAYLOAD = {"version": "0.0.0-r694-fake", "num_gpus": 0, "device_type": "cpu"}


def _rewrite(path: str) -> dict | None:
    if path.startswith("/api/ps"):
        return None if PASSTHROUGH_PS else PS_PAYLOAD
    if path.startswith("/api/version"):
        return VERSION_PAYLOAD
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, method: str, body: bytes | None) -> None:
        if BREAK_EMBEDDINGS and self.path.split("?")[0] in EMBED_PATHS:
            payload = json.dumps({
                "error": "r694-injected: embedding backend unreachable",
                "code": "embedding_unreachable",
            }).encode("utf-8")
            self._send(503, payload, "application/json")
            return
        fake = _rewrite(self.path)
        if fake is not None and method == "GET":
            self._send(200, json.dumps(fake).encode("utf-8"), "application/json")
            return
        request = urllib.request.Request(UPSTREAM + self.path, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}:
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=900) as upstream:  # noqa: S310
                payload = upstream.read()
                self._send(upstream.status, payload,
                           upstream.headers.get("Content-Type", "application/octet-stream"))
        except urllib.error.HTTPError as exc:  # 上游的 4xx/5xx 原样转给产品
            self._send(exc.code, exc.read(),
                       exc.headers.get("Content-Type", "application/json") if exc.headers else "application/json")
        except Exception as exc:  # noqa: BLE001 - 门面坏了要说得出，不许让产品侧挂成超时
            self._send(502, json.dumps({"error": type(exc).__name__, "detail": str(exc)}).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 的命名
        self._proxy("GET", None)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self._proxy("POST", self.rfile.read(length) if length else None)

    def log_message(self, *args) -> None:  # 门面不进日志，容器日志只留给产品码那一行声明
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
