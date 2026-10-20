"""Run inside the deployed backend container; uses only its real Redis connection.

Deletes only keys in a new UUID namespace. No production queue mutation, stubs,
account mutation, model requests, or service stops. Worker retry refusal runs in
an isolated subprocess with a genuinely unreachable PG endpoint.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import uuid

from app.common.reliable_queue import (
    ReliableQueue, QueueExecutionLost, artifact_execution_guard, connect_reliable_queue,
)

name = "v2-queue-acceptance:" + uuid.uuid4().hex
q = connect_reliable_queue(name=name, lease_seconds=2, max_attempts=3)
rows = []

def check(label, condition, **evidence):
    rows.append({"case": label, "passed": bool(condition), **evidence})
    assert condition, json.dumps(rows[-1], ensure_ascii=False)

def new_queue():
    return ReliableQueue(q.redis, name=name, lease_seconds=2, max_attempts=3)

def task(label, payload=None):
    return q.enqueue(payload or {"message": label}, label)

try:
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: new_queue().enqueue({"message": "duplicate"}, "concurrent"), range(32)))
    ids = {r.request_id for r in results}
    check("concurrent_idempotency", len(ids) == 1 and q.pending_depth() == 1, distinct_ids=len(ids), pending=q.pending_depth())
    current = q.reserve()
    check("single_delivery", q.reserve() is None and current.request_id in ids)
    check("done_is_immutable", q.complete(current.request_id, "one report") and q.cancel(current.request_id)
          and q.status(current.request_id) == "done" and q.result(current.request_id) == "one report")
    check("duplicate_completion_refused", not q.complete(current.request_id, "duplicate") and q.result(current.request_id) == "one report")
    check("completed_idempotency", task("concurrent").request_id == current.request_id and q.pending_depth() == 0)

    retry = task("retry-budget")
    states = []
    for expected in range(1, 4):
        message = q.reserve()
        check("retry_attempt_" + str(expected), message.request_id == retry.request_id and message.attempts == expected)
        states.append(q.fail_or_retry(message.request_id, "internal_error"))
    check("retry_budget_terminal", states == ["queued", "queued", "dead"] and q.failure(retry.request_id)["attempts"] == 3,
          states=states, failure=q.failure(retry.request_id), verdict=q.dead_verdict(retry.request_id))
    check("dead_is_immutable", q.fail_or_retry(retry.request_id, "late_error") == "dead" and q.cancel(retry.request_id)
          and q.dead_letter_depth() == 1 and q.dead_verdict(retry.request_id)["reason"] == "internal_error")

    cancel = task("pending-cancel")
    q.cancel(cancel.request_id)
    check("pending_cancel", q.status(cancel.request_id) == "cancelled" and q.reserve() is None and q.result(cancel.request_id) is None)
    cancel = task("processing-cancel")
    q.reserve()
    q.cancel(cancel.request_id)
    time.sleep(2.1)
    check("processing_cancel_survives_lease", not q.complete(cancel.request_id, "forbidden") and q.status(cancel.request_id) == "cancelled"
          and q.result(cancel.request_id) is None)

    expired = task("lease-expiry")
    old = new_queue()
    old.reserve()
    guard = old.execution_guard(expired.request_id)
    time.sleep(2.1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        moved = sum(pool.map(lambda _: new_queue().requeue_expired(), range(4)))
    new = new_queue()
    resumed = new.reserve()
    check("expiry_single_recovery", moved == 1 and resumed.attempts == 2 and q.pending_depth() == 0, moved=moved)
    check("old_lease_fenced", not old.renew_lease(expired.request_id) and not old.complete(expired.request_id, "stale")
          and old.fail_or_retry(expired.request_id, "late_fault") == "processing" and new.owns_execution(expired.request_id))
    denied = False
    try:
        with artifact_execution_guard(guard):
            raise AssertionError("stale artifact guard allowed")
    except QueueExecutionLost:
        denied = True
    check("artifact_guard_fences_old_attempt", denied)
    with artifact_execution_guard(new.execution_guard(expired.request_id)):
        pass
    check("replacement_result_only", new.complete(expired.request_id, "fresh") and not old.complete(expired.request_id, "stale")
          and q.result(expired.request_id) == "fresh")

    orphan = task("reserve-crash")
    q.redis.rpoplpush(q.pending_key, q.processing_key)
    check("crash_before_claim_recovery", q.requeue_expired() == 1 and q.reserve().request_id == orphan.request_id)
    q.complete(orphan.request_id, "recovered")

    from deploy.queue_worker import _process_reserved
    missing = task("missing-owner")
    _process_reserved(q, q.reserve())
    check("worker_nonretryable", q.status(missing.request_id) == "dead" and q.failure(missing.request_id)["attempts"] == 1
          and q.dead_verdict(missing.request_id) == {"reason": "authorization_required", "retryable": False},
          failure=q.failure(missing.request_id), verdict=q.dead_verdict(missing.request_id))

    child = '''import json,sys,os
from app.common.reliable_queue import connect_reliable_queue
from deploy.queue_worker import _process_reserved
os.environ['DATABASE_URL']='postgresql://v2_probe@127.0.0.1:9/none?connect_timeout=1'
q=connect_reliable_queue(name=sys.argv[1],lease_seconds=10,max_attempts=3)
m=q.enqueue({"message":"isolated real dependency fault","username":"v2-probe-user","principal":{"user_id":"v2-probe-user","username":"v2-probe-user"}},"worker-retry")
states=[]
for i in range(3):
 _process_reserved(q,q.reserve())
 states.append(q.status(m.request_id))
print("QUEUE_RESULT="+json.dumps({"states":states,"failure":q.failure(m.request_id),"verdict":q.dead_verdict(m.request_id)}))
'''
    env = dict(os.environ, APP_ENV="production")
    if os.getenv("V2_CHECK_BOOTSTRAP"):
        env["V2_CHECK_QUEUE_ONLY"] = "1"
        child = "exec(open(" + repr(os.environ["V2_CHECK_BOOTSTRAP"]) + ").read())\n" + child
    proc = subprocess.run([sys.executable, "-c", child, name], env=env, capture_output=True, text=True, timeout=60)
    marker = next((line[len("QUEUE_RESULT="):] for line in proc.stdout.splitlines() if line.startswith("QUEUE_RESULT=")), None)
    if marker is None:
        raise RuntimeError("isolated worker failed: " + proc.stdout[-1000:] + proc.stderr[-1000:])
    witness = json.loads(marker)
    check("worker_real_dependency_retry_limit", proc.returncode == 0 and witness["states"] == ["queued", "queued", "dead"]
          and witness["failure"]["attempts"] == 3 and witness["verdict"]["retryable"] is True, **witness)
    print(json.dumps({"namespace": name, "cases": rows, "passed": len(rows)}, ensure_ascii=False, indent=2))
finally:
    keys = list(q.redis.scan_iter(match=name + ":*"))
    if keys:
        q.redis.delete(*keys)
