"""Authenticated Redis acceptance for reliable-queue crash recovery.

A throwaway ``redis-server`` starts with ``requirepass`` taken from a private temporary
configuration file, so the credential never appears in an argv or a log line. The real
``deploy/queue_worker`` reserve/ack/retry code runs in a child process for every case;
only the model boundary is substituted. These tests never contact the long-running
developer Redis service.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from typing import Iterator

import pytest
import redis

from app.common.reliable_queue import connect_reliable_queue

ROOT = Path(__file__).resolve().parents[1]
REDIS_BIN = os.getenv("EB_REDIS_ACCEPTANCE_BIN", "").strip()
DRIVER = Path(__file__).resolve().parent / "_redis_worker_driver.py"

pytestmark = pytest.mark.skipif(
    not REDIS_BIN,
    reason="set EB_REDIS_ACCEPTANCE_BIN to run the authenticated Redis acceptance",
)


def _free_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def _members(client, key: str) -> list[str]:
    return [item.decode() if isinstance(item, bytes) else str(item) for item in client.lrange(key, 0, -1)]


@pytest.fixture(scope="module")
def redis_url(tmp_path_factory) -> Iterator[str]:
    directory = tmp_path_factory.mktemp("redis-acceptance")
    port = _free_port()
    password = secrets.token_urlsafe(24)
    config = directory / "acceptance.conf"
    config.write_text(
        "\n".join(
            [
                "port " + str(port),
                "bind 127.0.0.1",
                "requirepass " + password,
                'save ""',
                "appendonly no",
                "daemonize no",
                "databases 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    process = subprocess.Popen([REDIS_BIN, str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "redis://:" + password + "@127.0.0.1:" + str(port) + "/0"
    client = redis.Redis.from_url(url, socket_connect_timeout=1)
    deadline = time.time() + 30
    while True:
        try:
            client.ping()
            break
        except Exception:
            if time.time() > deadline or process.poll() is not None:
                process.kill()
                raise RuntimeError("the acceptance Redis instance never became reachable")
            time.sleep(0.2)

    anonymous = redis.Redis(host="127.0.0.1", port=port, socket_connect_timeout=1)
    with pytest.raises(redis.AuthenticationError):
        anonymous.ping()

    try:
        yield url
    finally:
        try:
            client.shutdown(now=True, save=False)
        except Exception:
            pass
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        config.unlink(missing_ok=True)


class WorkerHarness:
    """Run the real worker against one named queue on the temporary Redis instance."""

    def __init__(self, redis_url: str, tmp_path: Path, name: str, *, lease_seconds: int, max_attempts: int):
        self.name = name
        self.tmp_path = tmp_path
        self.log = tmp_path / (name.replace(":", "_") + ".worker.log")
        self.env = dict(os.environ)
        self.env.update(
            {
                "REDIS_URL": redis_url,
                "PERSISTENCE_BACKEND": "json",
                "PERSISTENCE_FALLBACK_PATH": str(tmp_path / "persistence.json"),
                "TRACE_STORE_PATH": str(tmp_path / "trace.jsonl"),
                "PYTHONIOENCODING": "utf-8",
            }
        )
        self.args = ("--name", name, "--lease-seconds", str(lease_seconds), "--max-attempts", str(max_attempts))
        self.queue = connect_reliable_queue(
            redis_url, name=name, lease_seconds=lease_seconds, max_attempts=max_attempts
        )

    def _command(self, mode: str) -> list[str]:
        return [sys.executable, str(DRIVER), "--mode", mode, *self.args]

    def launch(self, mode: str):
        handle = self.log.open("w", encoding="utf-8")
        return subprocess.Popen(self._command(mode), cwd=str(ROOT), env=self.env, stdout=handle, stderr=subprocess.STDOUT)

    def run(self, mode: str, timeout: float = 180.0) -> subprocess.CompletedProcess:
        result = subprocess.run(
            self._command(mode),
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        self.log.write_text(result.stdout + result.stderr, encoding="utf-8")
        assert result.returncode == 0, self._log_text()
        assert "IDLE" not in result.stdout, "the worker never received the queued task: " + self._log_text()
        return result

    def wait_for(self, request_id: str, expected: str, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.queue.status(request_id) == expected:
                return
            time.sleep(0.1)
        raise AssertionError("timed out waiting for " + request_id + " to become " + expected + "; log: " + self._log_text())

    def _log_text(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""


def _harness(redis_url, tmp_path, name, *, lease_seconds=10, max_attempts=2) -> WorkerHarness:
    return WorkerHarness(redis_url, tmp_path, name, lease_seconds=lease_seconds, max_attempts=max_attempts)


def _task(harness: WorkerHarness, *, principal=True, **payload) -> str:
    body = {"message": "acceptance task " + harness.name}
    if principal:
        body["principal"] = {"user_id": "owner-" + harness.name.split(":")[-1]}
    body.update(payload)
    return harness.queue.enqueue(body, idempotency_key="idem-" + harness.name).request_id


def test_killed_worker_is_requeued_once_its_lease_expires(redis_url, tmp_path) -> None:
    harness = _harness(redis_url, tmp_path, "accept:crash", lease_seconds=2, max_attempts=3)
    request_id = _task(harness)

    driver = harness.launch("crash")
    try:
        harness.wait_for(request_id, "processing")
    finally:
        driver.kill()
        driver.wait(timeout=20)

    assert _members(harness.queue.redis, harness.queue.processing_key) == [request_id]
    time.sleep(2.5)
    assert harness.queue.requeue_expired() == 1
    assert harness.queue.status(request_id) == "queued"
    assert _members(harness.queue.redis, harness.queue.processing_key) == []

    recovered = harness.queue.reserve(timeout=1)
    assert recovered is not None
    assert recovered.request_id == request_id
    assert recovered.attempts == 2
    assert harness.queue.ack(request_id) is True


def test_repeated_failures_retry_then_land_in_the_dead_letter_list(redis_url, tmp_path) -> None:
    harness = _harness(redis_url, tmp_path, "accept:dead", lease_seconds=10, max_attempts=2)
    request_id = _task(harness)

    harness.run("fail")
    assert harness.queue.status(request_id) == "queued"
    assert harness.queue.failure(request_id)["last_error"] == "acceptance: injected model boundary failure"
    assert harness.queue.result(request_id) is None

    harness.run("fail")
    assert harness.queue.status(request_id) == "dead"
    assert request_id in _members(harness.queue.redis, harness.queue.dead_key)
    assert harness.queue.result(request_id) is None
    assert _members(harness.queue.redis, harness.queue.pending_key) == []


def test_a_successful_task_publishes_a_result_and_one_agent_run(redis_url, tmp_path) -> None:
    harness = _harness(redis_url, tmp_path, "accept:done", lease_seconds=30, max_attempts=2)
    request_id = _task(harness, session_id="accept-session")

    harness.run("succeed")

    assert harness.queue.status(request_id) == "done"
    assert str(harness.queue.result(request_id)).startswith("acceptance answer")
    assert _members(harness.queue.redis, harness.queue.processing_key) == []

    records = json.loads((tmp_path / "persistence.json").read_text(encoding="utf-8"))
    runs = [row for row in records.get("agent_runs", {}).values() if row.get("owner_id") == "owner-done"]
    assert len(runs) == 1
    summary = runs[0]["metadata"]["agent_result"]
    assert summary["status"] == "success"
    assert summary["evidence_count"] == 1
    assert summary["answer_length"] > 0
    assert "acceptance answer" not in json.dumps(runs[0], ensure_ascii=False)


def test_anonymous_task_is_refused_without_publishing_a_conclusion(redis_url, tmp_path) -> None:
    harness = _harness(redis_url, tmp_path, "accept:anon", lease_seconds=10, max_attempts=3)
    request_id = _task(harness, principal=False)

    harness.run("succeed")

    assert harness.queue.status(request_id) == "queued"
    assert harness.queue.result(request_id) is None
    assert harness.queue.failure(request_id) == {
        "attempts": 1,
        "last_error": "authorization_required",
        "max_attempts": 3,
    }
    path = tmp_path / "persistence.json"
    if path.exists():
        records = json.loads(path.read_text(encoding="utf-8"))
        assert not records.get("agent_runs")


def test_enqueue_is_idempotent_and_cancellation_blocks_delivery(redis_url, tmp_path) -> None:
    harness = _harness(redis_url, tmp_path, "accept:idem", lease_seconds=5, max_attempts=2)
    queue = harness.queue
    first = queue.enqueue({"message": "original", "principal": {"user_id": "owner-idem"}}, idempotency_key="accept-idem")
    second = queue.enqueue(
        {"message": "duplicate submission", "principal": {"user_id": "owner-idem"}}, idempotency_key="accept-idem"
    )
    assert first.request_id == second.request_id
    assert second.payload == first.payload
    assert _members(queue.redis, queue.pending_key) == [first.request_id]

    assert queue.cancel(first.request_id) is True
    assert queue.reserve(timeout=1) is None
    assert queue.status(first.request_id) == "cancelled"
    assert _members(queue.redis, queue.processing_key) == []