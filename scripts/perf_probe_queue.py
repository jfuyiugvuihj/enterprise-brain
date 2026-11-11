r"""W8 perf probe #3: what MODEL_MAX_CONCURRENCY=1 and a client timeout really cost.

Three questions this answers with numbers, all read-only against Ollama:

  Q1 serialise  N employees ask at once. Ollama holds one model instance, so requests
      queue. How long does the last one wait?
  Q2 ghost_work  Does a client-side timeout actually stop the generation, or does the
      abandoned request keep burning the single CPU slot and push everyone behind it?
      This is the mechanism behind the 5 x 60s / 302s cold-start request seen in the
      backend log at 21:50-21:55 on 2026-09-16.
  Q3 warm_idle   Model load/unload cost, which decides whether a "keep warm" timer is
      worth shipping.

    cd C:/Users/fengx/PycharmProjects/perf-lab
    cmd /c "docker exec -i enterprise-brain-backend-1 python - < scripts/perf_probe_queue.py"
"""
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

OLLAMA = "http://ollama:11434"
MODEL = "qwen3.5:9b"
SMALL = "用一句话说：经销商逾期超过六十天会怎样？"
BIG_PREDICT = int(__import__("os").environ.get("QPREDICT", "200"))


def emit(row):
    print("JSONL " + json.dumps(row, ensure_ascii=False), flush=True)


def chat(prompt, num_predict, timeout=600):
    body = json.dumps({"model": MODEL, "stream": False,
                       "options": {"temperature": 0, "num_predict": num_predict},
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return {
        "wall_s": round(time.monotonic() - started, 3),
        "prompt_eval_count": d.get("prompt_eval_count"),
        "eval_count": d.get("eval_count"),
        "load_s": round((d.get("load_duration", 0) or 0) / 1e9, 3),
        "prefill_s": round((d.get("prompt_eval_duration", 0) or 0) / 1e9, 3),
        "decode_s": round((d.get("eval_duration", 0) or 0) / 1e9, 3),
    }


def chat_abort(prompt, num_predict, abort_after):
    """Open the request and hard-close the socket, like an httpx client timeout does."""
    host, port = "ollama", 11434
    payload = json.dumps({"model": MODEL, "stream": False,
                          "options": {"temperature": 0, "num_predict": num_predict},
                          "messages": [{"role": "user", "content": prompt}]}, ensure_ascii=False)
    raw = ("POST /api/chat HTTP/1.1\r\nHost: ollama:11434\r\nContent-Type: application/json\r\n"
           "Content-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(payload.encode("utf-8")), payload))
    sock = socket.create_connection((host, port))
    started = time.monotonic()
    sock.sendall(raw.encode("utf-8"))
    try:
        sock.settimeout(abort_after)
        sock.recv(4096)
    except socket.timeout:
        pass
    held = time.monotonic() - started
    sock.close()          # RST/FIN: ollama may or may not stop generating here
    return {"abort_after_s": abort_after, "observed_held_s": round(held, 3)}


def suite_serial(n):
    emitted = []

    def worker(i):
        t0 = time.monotonic()
        try:
            row = chat(SMALL + "（第%d位员工）" % i, BIG_PREDICT)
        except Exception as exc:  # noqa: BLE001
            row = {"case_note": repr(exc)[:160], "wall_s": round(time.monotonic() - t0, 3)}
        row["case"] = "serial_client_%d_of_%d" % (i, n)
        row["started_after_t0_s"] = round(t0 - base[0], 3)
        row["finished_after_t0_s"] = round(time.monotonic() - base[0], 3)
        emitted.append(row)

    base = [time.monotonic()]
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for row in sorted(emitted, key=lambda r: r["case"]):
        emit(row)


def suite_ghost():
    emit({"case": "ghost_baseline_small", "note": "模型刚跑完大请求，立刻量一个小请求"})
    emit(dict(case="ghost_warm_small", **chat(SMALL, 1)))
    aborted = chat_abort(SMALL + "（被客户端放弃的长回答）", BIG_PREDICT, 8)
    emit(dict(case="ghost_abort_sent", **aborted))
    for i in range(3):
        emit(dict(case="ghost_probe_%d_after_abort" % i,
                  **chat(SMALL + " 探针%d" % i, 1)))
        time.sleep(1)


SUITES = {"serial2": lambda: suite_serial(2), "serial3": lambda: suite_serial(3),
          "serial5": lambda: suite_serial(5), "ghost": suite_ghost}


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "ghost").split(",")
    print("# probe_start %s suites=%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), which), flush=True)
    for name in which:
        SUITES[name]()
    print("# probe_end %s" % time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())