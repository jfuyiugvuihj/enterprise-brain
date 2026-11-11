r"""Calibrate the model throughput constants in app/common/model_budget.py. R99, 2026-09-19.

WHY THIS EXISTS
---------------
``MODEL_PREFILL_TOKENS_PER_SECOND`` / ``MODEL_DECODE_TOKENS_PER_SECOND`` /
``MODEL_MIN_ANSWER_TOKENS`` are measurements of one machine, and every budget decision --
how long a request may take, how long an answer may be, and whether a tier is affordable
at all -- is arithmetic on them. They were last calibrated on a CPU-only box (2026-09-16)
while the shipping container answers from a GPU, so the constants and the ceiling now
contradict each other. Nobody may fix that by picking a number. This script produces one.

WHAT IT SEPARATES
-----------------
Three candidate causes were on the table for "the model answered in 4 s but our client
spent the whole 120 s ceiling", and they need different fixes, so they are measured
separately rather than argued about:

  (a) the constants are a CPU-only calibration -- answered by the rate columns;
  (b) a thinking model spends the budget on a hidden chain of thought, so the wall clock
      is minutes while the visible answer is empty -- answered by comparing
      ``visible_chars`` against ``completion_tokens`` in the same row, and by the
      ``think``-spelling cases below;
  (c) the OpenAI-compatible leg and the native leg are simply different speeds --
      answered by running the SAME prompt through both, at the same output caps.

Because a non-streaming response cannot tell prefill from decode, each leg also runs a
``max_tokens=1`` case: that wall clock is prompt processing plus load, so prefill rate
comes from it and decode rate comes from the difference against the full-cap runs.

BASELINE -- MEASURED BY THE COORDINATOR, NOT BY THIS SCRIPT
-----------------------------------------------------------
Taken 2026-09-19 22:3x +08:00 inside the live container (image ``78b8507``, model
qwen3.5:9b, ``ollama ps`` = 100% GPU, ~37 tok/s) with one prompt, non-streaming. These
four groups are the reference this script is expected to reproduce or contradict; they are
NOT this script's own output, and if a rerun here disagrees, **the rerun wins** and these
numbers become history:

  A. /v1/chat/completions, stream=false
       max_tokens=1024 -> 38.3 s, completion_tokens not reported (None), 0 chars visible,
                          finish_reason=length
       max_tokens=4096 -> 80.4 s, 439 chars visible, finish_reason=stop
  B. /api/chat, stream=false, options.num_predict, same prompt
       num_predict=1024            -> 28.3 s, eval_count=1024, 0 chars, done_reason=length
       num_predict=1536            -> 43.1 s, eval_count=1536, thinking field 0 chars,
                                    0 chars visible, done_reason=length
       num_predict=1536 + options.think=False -> 41.6 s, eval_count=1536, 0 chars, length
       num_predict=1536 + options.think=True  -> 40.9 s, eval_count=1536, 0 chars, length

  Read that the ticket's first revision corrected: the three legs differ by well under one
  order of magnitude (28-41 s for 1024-1536 tokens), so (c) is NOT the main cause and must
  not be designed around. What the numbers show is that 1536 output tokens buys **zero
  visible characters** on this model -- the cap itself is under the thinking floor -- and
  that ``think`` inside ``options`` does nothing: on current Ollama ``think`` is a
  top-level request field. This script therefore sends BOTH spellings and reports which
  one produced visible text, instead of assuming either.

USAGE
-----
    python scripts/bench_model_throughput.py                      # defaults from the env
    python scripts/bench_model_throughput.py --repeats 5 --json D:/tmp/r99.json
    python scripts/bench_model_throughput.py --caps 1024 4096 --prompt-file q.txt

Results go to stdout and nowhere else. ``--json`` writes a file, and it refuses any path
inside this repository: a calibration artefact is a measurement of one machine at one
moment, and committing it would turn today's number into next week's unexamined default.

Exit codes are explicit because a skip must never look like a pass:
    0 measured (some cases may still have failed, the table says which)
    2 usage error (bad argument, or --json inside the repository)
    3 skipped: the model server was not reachable, or the model is not on it
    4 every measured case failed, so there is nothing to conclude
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

#: The caps the production tiers actually use, and the two the coordinator measured at.
DEFAULT_CAPS = (1024, 4096)
#: One token of output isolates prompt processing from generation.
PREFILL_PROBE_CAP = 1
DEFAULT_PROMPT = (
    "我们经销商的标准回款周期是多少天？超期多久会停发新货？请用完整的制度原文回答。"
)
SALT_PREFIX = "【标定校验码 {salt}】\n"

EXIT_MEASURED = 0
EXIT_USAGE = 2
EXIT_SKIPPED = 3
EXIT_NO_DATA = 4


def log(message: str = "") -> None:
    print(message, flush=True)


def compat_base(base_url: str) -> str:
    """Accept either ``http://host:11434`` or ``http://host:11434/v1`` and normalise."""
    trimmed = base_url.rstrip("/")
    return trimmed[:-3] if trimmed.endswith("/v1") else trimmed


def post_json(url: str, payload: dict, timeout: float):
    """POST one request and return ``(status, parsed-or-lines, seconds, error)``.

    Streaming is read line by line and every chunk is timed, because the two things under
    test -- when the first byte arrived and how long the tokens took after that -- are both
    invisible in a response that has already finished.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    started = time.monotonic()
    first_token_at = None
    chunks: list[dict] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if "text/event-stream" in str(response.headers.get("content-type", "")):
                for raw in response:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    if first_token_at is None:
                        first_token_at = time.monotonic() - started
                    payload_text = line[5:].strip() if line.startswith("data:") else line
                    if payload_text in ("", "[DONE]"):
                        continue
                    try:
                        chunks.append(json.loads(payload_text))
                    except json.JSONDecodeError:
                        continue
                return 200, chunks, time.monotonic() - started, first_token_at, None
            text = response.read().decode("utf-8", "replace")
            try:
                return 200, json.loads(text), time.monotonic() - started, None, None
            except json.JSONDecodeError as exc:
                return 200, None, time.monotonic() - started, None, f"unparsable body: {exc}"
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001 - the body is a courtesy, not the finding
            pass
        return exc.code, None, time.monotonic() - started, None, detail or str(exc)
    except Exception as exc:  # noqa: BLE001 - a refused socket is a result, not a crash
        return 0, None, time.monotonic() - started, None, f"{type(exc).__name__}: {exc}"


def collect_stream(chunks: list[dict], native: bool) -> tuple[str, str, dict, str]:
    """Fold streamed chunks into (visible text, reasoning text, usage, finish reason)."""
    visible: list[str] = []
    reasoning: list[str] = []
    usage: dict = {}
    finish = ""
    for chunk in chunks:
        if native:
            message = chunk.get("message") or {}
            visible.append(message.get("content") or "")
            reasoning.append(message.get("thinking") or "")
            if chunk.get("done"):
                finish = str(chunk.get("done_reason") or "")
                usage = {
                    "prompt_tokens": chunk.get("prompt_eval_count"),
                    "completion_tokens": chunk.get("eval_count"),
                    "load_seconds": chunk.get("load_duration"),
                }
        else:
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                visible.append(delta.get("content") or "")
                reasoning.append(delta.get("reasoning") or delta.get("reasoning_content") or "")
                if choice.get("finish_reason"):
                    finish = str(choice.get("finish_reason"))
            if chunk.get("usage"):
                usage = dict(chunk["usage"])
    return "".join(visible), "".join(reasoning), usage, finish


def run_case(base_url: str, model: str, *, native: bool, cap: int, stream: bool,
             think: str, timeout: float, salt: str) -> dict:
    """One measured request, described in the words the budget code uses."""
    prompt = SALT_PREFIX.format(salt=salt) + DEFAULT_PROMPT
    messages = [{"role": "user", "content": prompt}]
    if native:
        url = f"{compat_base(base_url)}/api/chat"
        options = {"temperature": 0, "num_predict": cap}
        payload = {"model": model, "stream": stream, "options": options, "messages": messages}
        if think == "body":
            # The spelling current Ollama documents: a sibling of "model", not of "options".
            payload["think"] = False
        elif think == "options":
            options["think"] = False
    else:
        url = f"{compat_base(base_url)}/v1/chat/completions"
        payload = {"model": model, "stream": stream, "max_tokens": cap,
                   "temperature": 0, "messages": messages}
        if think == "body":
            payload["think"] = False

    status, parsed, wall, first_token, error = post_json(url, payload, timeout)
    row = {
        "leg": "native" if native else "compat",
        "stream": stream,
        "cap": cap,
        "think": think,
        "status": status,
        "wall_s": round(wall, 3),
        "first_token_s": round(first_token, 3) if first_token else None,
        "error": error,
    }
    if error is not None:
        return row

    if native:
        chunks = parsed if stream else []
        final = parsed if not stream else None
        visible, reasoning, usage, finish = collect_stream(chunks, native=True)
        if not stream and isinstance(final, dict):
            message = final.get("message") or {}
            visible = message.get("content") or ""
            reasoning = message.get("thinking") or ""
            usage = {
                "prompt_tokens": final.get("prompt_eval_count"),
                "completion_tokens": final.get("eval_count"),
            }
            finish = str(final.get("done_reason") or "")
    else:
        chunks = parsed if stream else []
        final = parsed if not stream else None
        visible, reasoning, usage, finish = collect_stream(chunks, native=False)
        if not stream and isinstance(final, dict):
            choice = (final.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            visible = message.get("content") or ""
            reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
            usage = dict(final.get("usage") or {})
            finish = str(choice.get("finish_reason") or "")

    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens")
    generated = completion_tokens if completion_tokens is not None else 0
    decode_window = (wall - first_token) if (stream and first_token) else wall
    row.update({
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "visible_chars": len(visible.strip()),
        "reasoning_chars": len(reasoning.strip()),
        "finish_reason": finish,
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "prefill_tokens_per_second": (
            round(prompt_tokens / first_token, 2) if stream and first_token and prompt_tokens else None
        ),
        "decode_tokens_per_second": (
            round(generated / decode_window, 2)
            if generated and decode_window > 0 and (not stream or first_token)
            else None
        ),
    })
    return row


def probe_server(base_url: str, model: str, timeout: float) -> tuple[bool, bool, str]:
    """``(reachable, model_present, detail)`` from metadata only -- no generation.

    A calibration run that is not pointed at a server must say so and leave. Guessing from
    an empty table is how a benchmark quietly becomes a pass.
    """
    root = compat_base(base_url)
    try:
        with urllib.request.urlopen(f"{root}/api/version", timeout=min(timeout, 5)) as response:
            version = json.loads(response.read().decode("utf-8", "replace")).get("version", "?")
    except Exception as exc:  # noqa: BLE001
        return False, False, f"{type(exc).__name__}: {exc}"
    try:
        with urllib.request.urlopen(f"{root}/api/tags", timeout=min(timeout, 5)) as response:
            names = [m.get("name", "") for m in json.loads(
                response.read().decode("utf-8", "replace")).get("models", [])]
    except Exception:  # noqa: BLE001 - a server without /api/tags is still a server
        return True, True, f"ollama {version}, model list unreadable"
    present = any(name == model or name.split(":")[0] == model.split(":")[0] for name in names)
    return True, present, f"ollama {version}, models={names or 'none'}"


def summarise(rows: list[dict]) -> dict:
    """p50/p95 wall clock plus the rate columns, grouped by case identity."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["leg"], row["stream"], row["cap"], row["think"]), []).append(row)
    summary = []
    for (leg, stream, cap, think), group in sorted(groups.items()):
        ok = [row for row in group if row.get("error") is None]
        walls = sorted(row["wall_s"] for row in ok)
        decodes = [row["decode_tokens_per_second"] for row in ok if row.get("decode_tokens_per_second")]
        prefills = [row["prefill_tokens_per_second"] for row in ok if row.get("prefill_tokens_per_second")]
        summary.append({
            "leg": leg,
            "stream": stream,
            "cap": cap,
            "think": think,
            "runs": len(group),
            "ok": len(ok),
            "p50_wall_s": walls[len(walls) // 2] if walls else None,
            "p95_wall_s": walls[max(0, int(len(walls) * 0.95) - 1)] if walls else None,
            "median_decode_tokens_per_second": statistics.median(decodes) if decodes else None,
            "median_prefill_tokens_per_second": statistics.median(prefills) if prefills else None,
            "median_visible_chars": statistics.median([row["visible_chars"] for row in ok]) if ok else None,
            "finish_reasons": sorted({str(row.get("finish_reason")) for row in ok}),
            "errors": sorted({str(row.get("error"))[:120] for row in group if row.get("error")}),
        })
    return {"cases": summary, "model": None, "base_url": None}


def render(rows: list[dict]) -> None:
    header = (
        f"{'leg':<7}{'stream':<8}{'cap':>6}{'think':>9}{'wall_s':>9}{'1st_s':>8}"
        f"{'in':>6}{'out':>6}{'vis':>6}{'reas':>6}  finish   prefill/decode tok/s"
    )
    log(header)
    log("-" * len(header))
    for row in rows:
        if row.get("error") is not None:
            log(f"{row['leg']:<7}{str(row['stream']):<8}{row['cap']:>6}{row['think']:>9}"
                f"{row['wall_s']:>9}     -     -     -     -     -  error: {row['error']}")
            continue
        log(
            f"{row['leg']:<7}{str(row['stream']):<8}{row['cap']:>6}{row['think']:>9}"
            f"{row['wall_s']:>9}"
            f"{(row['first_token_s'] if row['first_token_s'] is not None else '-'):>8}"
            f"{row.get('prompt_tokens', '-'):>6}{row.get('completion_tokens') or '-':>6}"
            f"{row.get('visible_chars', '-'):>6}{row.get('reasoning_chars', '-'):>6}"
            f"  {str(row.get('finish_reason') or '-'):<8}"
            f" {row.get('prefill_tokens_per_second') or '-'}/{row.get('decode_tokens_per_second') or '-'}"
            f"{'  cached=' + str(row['cached_tokens']) if row.get('cached_tokens') else ''}"
        )


def resolve_base_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in ("LOCAL_MODEL_BASE_URL", "OLLAMA_BASE_URL"):
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return "http://127.0.0.1:11434"


def resolve_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in ("LOCAL_MODEL_NAME", "OLLAMA_MODEL"):
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return "qwen3.5:9b"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Sends no request at all -- and exits 3, not 0 -- when the server is unreachable, "
            "so a machine without Ollama can never 'pass' a calibration it did not perform."
        ),
    )
    parser.add_argument("--base-url", default=None, help="default: $LOCAL_MODEL_BASE_URL / $OLLAMA_BASE_URL")
    parser.add_argument("--model", default=None, help="default: $LOCAL_MODEL_NAME / $OLLAMA_MODEL")
    parser.add_argument("--caps", type=int, nargs="+", default=list(DEFAULT_CAPS),
                        help="output caps to sweep; each is run as max_tokens and num_predict")
    parser.add_argument("--repeats", type=int, default=3, help="runs per case, for p50/p95")
    parser.add_argument("--timeout", type=float, default=600.0, help="per-request wall clock ceiling")
    parser.add_argument("--json", default=None, metavar="PATH",
                        help="write the rows as JSON outside this repository")
    parser.add_argument("--force", action="store_true", help="bench even if the model is absent from /api/tags")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_url = resolve_base_url(args.base_url)
    model = resolve_model(args.model)

    if args.json:
        target = Path(args.json).resolve()
        if REPOSITORY_ROOT in target.parents or target == REPOSITORY_ROOT:
            log(f"RESULT: FAIL -- --json refuses to write inside the repository ({REPOSITORY_ROOT});")
            log("          a calibration is a measurement of one machine at one moment.")
            return EXIT_USAGE
    if args.repeats < 1:
        log("RESULT: FAIL -- --repeats must be at least 1")
        return EXIT_USAGE

    reachable, present, detail = probe_server(base_url, model, args.timeout)
    log(f"target  {base_url}  model={model}")
    log(f"server  {'reachable' if reachable else 'unreachable'}: {detail}")
    if not reachable:
        log("RESULT: SKIP -- no model server was reached, so nothing was measured.")
        log("        This is not a pass: the constants in app/common/model_budget.py are")
        log("        untouched and still need a calibration run on the machine that ships.")
        return EXIT_SKIPPED
    if not present and not args.force:
        log("RESULT: SKIP -- the model is not registered on that server (use --force to bench anyway).")
        return EXIT_SKIPPED

    caps = sorted(set([PREFILL_PROBE_CAP] + [int(cap) for cap in args.caps]))
    rows: list[dict] = []
    for repeat in range(args.repeats):
        salt = f"r99-{repeat + 1}-{int(time.time()) % 100000}"
        for cap in caps:
            for native in (False, True):
                for stream in (True, False):
                    think_variants = ["none"]
                    if not stream and cap != PREFILL_PROBE_CAP:
                        # Both spellings of the thinking switch, because the spelling that
                        # shipped is measured to do nothing (options.think) and this script
                        # must not repeat that mistake on either leg.
                        think_variants = ["none", "options", "body"] if native else ["none", "body"]
                    case = run_case(base_url, model, native=native, cap=cap, stream=stream,
                                    think="none" if cap == PREFILL_PROBE_CAP else think_variants[0],
                                    timeout=args.timeout, salt=salt)
                    rows.append(case)
                    log(f"  run {repeat + 1}/{args.repeats} {case['leg']:<7}"
                        f" stream={str(stream):<5} cap={cap:<5} {case['wall_s']}s"
                        f" visible={case.get('visible_chars', '-')}"
                        f" tokens={case.get('completion_tokens', '-')}"
                        f" finish={case.get('finish_reason', '-')}{' ' + str(case['error'])[:60] if case['error'] else ''}")
                    for variant in think_variants[1:]:
                        if cap == PREFILL_PROBE_CAP:
                            continue
                        extra = run_case(base_url, model, native=native, cap=cap, stream=stream,
                                         think=variant, timeout=args.timeout, salt=salt)
                        rows.append(extra)
                        log(f"  run {repeat + 1}/{args.repeats} {extra['leg']:<7}"
                            f" stream={str(stream):<5} cap={cap:<5} think={variant:<8}"
                            f" {extra['wall_s']}s visible={extra.get('visible_chars', '-')}"
                            f" tokens={extra.get('completion_tokens', '-')}"
                            f" finish={extra.get('finish_reason', '-')}")

    measured = [row for row in rows if row.get("error") is None]
    log("")
    render(rows)
    summary = summarise(rows)
    summary["model"] = model
    summary["base_url"] = compat_base(base_url)
    summary["rows"] = len(rows)
    log("")
    log("How to read this: prefill tok/s comes from the max_tokens=1 row and from streaming")
    log("time-to-first-token; decode tok/s is generated tokens over the window after the first")
    log("token. A row with a large token count and visible=0 is the thinking floor, not a slow")
    log("machine -- that is case (b), and it is fixed by the cap or the thinking switch, never")
    log("by a timeout. Write the medians into MODEL_PREFILL/DECODE_TOKENS_PER_SECOND and")
    log("MODEL_MIN_ANSWER_TOKENS as environment overrides; do not edit the code defaults.")
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rows": rows},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"json      {args.json}")

    if not measured:
        log("RESULT: FAIL -- every case errored; nothing was measured.")
        return EXIT_NO_DATA
    empty_visible = [row for row in measured if row["cap"] != PREFILL_PROBE_CAP and not row["visible_chars"]]
    if empty_visible:
        log(f"note      {len(empty_visible)} case(s) returned no visible text at all; that is the")
        log("          thinking floor, and it is what MODEL_MIN_ANSWER_TOKENS is for.")
    log(f"RESULT: PASS -- {len(measured)}/{len(rows)} cases measured on {model} at {compat_base(base_url)}.")
    return EXIT_MEASURED


if __name__ == "__main__":
    sys.exit(main())