"""Read local attempt metrics and project a support summary."""

import json
import math
import os
import stat
from pathlib import Path

LOG_TAIL_BYTES = 1024 * 1024
PROVIDER_EVENTS_FILE = "provider.jsonl"
PHASES = ("route", "build", "verify", "publish")
RUN_STATUSES = (
    "ready",
    "dispatched",
    "approval-required",
    "answer-required",
    "budget-exhausted",
    "interrupted",
    "checker-fault",
    "complete",
)
ATTEMPT_STATUSES = (
    "dispatched",
    "ok",
    "blocked",
    "replace",
    "failed",
    "checker-fault",
    "no-receipt",
    "invalid-receipt",
    "superseded",
)
WORKFLOWS = ("bmad-build-auto", "bmad-product-brief")
RETRY_REASONS = ("interrupted", "reverify", "artifact-repair")
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "noncached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)


def count(value):
    return value if type(value) is int and value >= 0 else None


def label(value, allowed):
    return value if value in allowed else "unknown"


def timestamp(value):
    if type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def elapsed(start, end):
    if start is None or end is None or end < start:
        return None
    return round(end - start, 3)


def token_counts(usage):
    if not isinstance(usage, dict):
        return None
    input_tokens = count(usage.get("input_tokens"))
    output_tokens = count(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None
    cached = count(usage.get("cached_input_tokens"))
    writes = count(usage.get("cache_write_input_tokens"))
    reasoning = count(usage.get("reasoning_output_tokens"))
    if cached is not None and cached > input_tokens:
        cached = None
    if writes is not None and writes > input_tokens:
        writes = None
    if reasoning is not None and reasoning > output_tokens:
        reasoning = None
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "noncached_input_tokens": input_tokens - cached if cached is not None else None,
        "cache_write_input_tokens": writes,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning,
    }


def provider_usage(directory):
    try:
        if directory.is_symlink() or directory.parent.is_symlink():
            return None, "unavailable", None
        log = directory / PROVIDER_EVENTS_FILE
        source = "provider-stdout"
        if not os.path.lexists(log):
            log = directory / "worker.log"
            source = "legacy-worker-log"
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        with os.fdopen(os.open(log, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return None, "unavailable", None
            start = max(0, info.st_size - LOG_TAIL_BYTES)
            if start:
                stream.seek(start - 1)
            window = stream.read(min(info.st_size, LOG_TAIL_BYTES + 1))
            if start:
                window = window.partition(b"\n")[2]
    except OSError:
        return None, "unavailable", None

    # Each dispatch launches a fresh exec session. Completion counters are cumulative.
    coverage = "observed"
    for line in reversed(window.split(b"\n")):
        if b'"turn.completed"' not in line:
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(event, dict) and event.get("type") == "turn.completed":
            tokens = token_counts(event.get("usage"))
            if tokens is not None:
                return tokens, coverage, source
            coverage = "partial"
    return None, "unavailable", None


def worker_kind(state, attempt):
    if "verifier" in attempt:
        return "independent-checker"
    if "workflow" in attempt:
        native_worker = state.get("native_worker")
        return "native-host" if isinstance(native_worker, list) and native_worker[-1:] == ["wait"] else "native-worker"
    worker = state.get("worker")
    if isinstance(worker, list) and len(worker) == 5 and isinstance(worker[1], str):
        if Path(worker[1]).name == "codex_worker.py":
            return "codex"
    return "custom-worker"


def total_tokens(observed):
    if not observed:
        return None
    totals = {}
    for field in TOKEN_FIELDS:
        values = [tokens[field] for tokens in observed]
        totals[field] = None if None in values else sum(values)
    return totals


def run_metrics(run, state, *, settled_usage=None):
    start = timestamp(state.get("started_at"))
    times = [start, timestamp(state.get("completed_at"))]
    attempts = []
    for number, attempt in enumerate(state["attempts"], 1):
        worker = worker_kind(state, attempt)
        directory = run / "attempts" / str(number)
        tokens, coverage, source = None, "unavailable", None
        if worker == "codex":
            if settled_usage is None:
                tokens, coverage, source = provider_usage(directory)
            elif attempt.get("status") != "dispatched":
                # A controller can reuse final counters for settled attempts until its next invocation.
                if number not in settled_usage:
                    settled_usage[number] = provider_usage(directory)
                tokens, coverage, source = settled_usage[number]
        started = timestamp(attempt.get("started_at"))
        resolved = timestamp(attempt.get("resolved_at"))
        times.extend((started, resolved))
        retry = attempt.get("retry")
        if "retry" not in attempt or (retry is not None and retry not in RETRY_REASONS):
            retry = "unknown"
        row = {
            "number": number,
            "phase": label(attempt.get("phase"), PHASES),
            "status": label(attempt.get("status"), ATTEMPT_STATUSES),
            "worker": worker,
            "coverage": coverage,
            "source": source,
            "observed_events": int(tokens is not None),
            "observed_tokens": tokens,
            "elapsed_seconds": elapsed(started, resolved),
            "retry": retry,
        }
        if "workflow" in attempt:
            row["workflow"] = label(attempt["workflow"], WORKFLOWS)
        attempts.append(row)

    observed = [row["observed_tokens"] for row in attempts if row["observed_tokens"] is not None]
    if not observed:
        coverage = "unavailable"
    else:
        coverage = "observed" if all(row["coverage"] == "observed" for row in attempts) else "partial"
    nested = any(row["worker"] in ("native-host", "native-worker") for row in attempts)
    return {
        "elapsed_basis": "last-saved-activity",
        "elapsed_seconds": elapsed(start, max((value for value in times if value is not None), default=None)),
        "retries": {
            "recorded": sum(row["retry"] in RETRY_REASONS for row in attempts),
            "attempts_without_metadata": sum(row["retry"] == "unknown" for row in attempts),
        },
        "usage": {
            "coverage": coverage,
            "observed_events": len(observed),
            "observed_tokens": total_tokens(observed),
            "native_nested_usage": "unavailable" if nested else "not-applicable",
            "attempts": attempts,
        },
    }


def support_summary(run, state):
    return {
        "schema_version": 1,
        "status": label(state.get("status"), RUN_STATUSES),
        "phase": label(state.get("phase"), PHASES),
        "dispatched": len(state["attempts"]),
        "budget": count(state.get("budget")),
        **run_metrics(run, state),
    }
