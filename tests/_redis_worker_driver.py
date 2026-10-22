"""Controllable queue-Worker driver for the authenticated Redis acceptance tests.

Every mode runs the real ``deploy/queue_worker`` reserve/ack/retry code path. Only the
model boundary is replaced with an explicit stand-in so queue recovery can be exercised
without occupying the local inference model. Queue coordinates default to the values the
production worker uses.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.agents.orchestrator as orchestrator  # noqa: E402
import deploy.queue_worker as worker  # noqa: E402
from app.agents.contracts import AgentResult, Evidence  # noqa: E402
from app.common.reliable_queue import connect_reliable_queue  # noqa: E402


def _stand_in(mode: str, seconds: float):
    def run(message, thread_id="", user=None, **_kwargs):
        if mode == "fail":
            raise RuntimeError("acceptance: injected model boundary failure")
        if mode == "crash":
            print("RESERVED", flush=True)
            time.sleep(seconds)
            raise SystemExit("acceptance: the driver was expected to be killed")
        return AgentResult(
            worker="orchestrator",
            status="success",
            answer="acceptance answer for " + str(message)[:48],
            request_id="req-" + uuid.uuid4().hex[:10],
            trace_id="trace-" + uuid.uuid4().hex[:10],
            task_id="task-" + uuid.uuid4().hex[:10],
            evidence=[
                Evidence(
                    source_type="document",
                    source_id="acceptance-doc",
                    document_version_id="acceptance-doc:v1",
                    permission_checked=True,
                    provenance_status="verified",
                )
            ],
        )

    return run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("crash", "fail", "succeed"))
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--name", default="")
    parser.add_argument("--lease-seconds", type=int, default=0)
    parser.add_argument("--max-attempts", type=int, default=0)
    args = parser.parse_args(argv)

    if args.name:
        # Bind the worker to one named queue so concurrent acceptance cases never
        # consume each other's messages.
        worker._queue = connect_reliable_queue(
            os.environ["REDIS_URL"],
            name=args.name,
            lease_seconds=args.lease_seconds or 300,
            max_attempts=args.max_attempts or 3,
        )

    orchestrator.run_orchestrator_result = _stand_in(args.mode, args.seconds)
    for _ in range(args.iterations):
        if not worker.process_one():
            print("IDLE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())