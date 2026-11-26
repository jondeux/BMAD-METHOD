"""Project a saved delivery run into a shareable diagnostic."""

from run_metrics import PHASES, RUN_STATUSES, count, elapsed, label, run_metrics, timestamp

TELEMETRY_FILE = "telemetry.json"
CONTROLLER_VERSION = "0.3.0"
GATES = ("approval-required", "answer-required", "budget-exhausted", "interrupted", "checker-fault")
PROCESS_OUTCOMES = ("exited", "timed-out", "interrupted", "launch-error", "log-open-error")
RECEIPT_SOURCES = ("current-controller", "resumed-controller", "late-receipt")
DIAGNOSTIC_CODES = (
    "configuration",
    "dependency-unavailable",
    "execution-error",
    "preview-unreachable",
    "selector-mismatch",
    "timeout",
)
CHECK_KINDS = ("executable", "source-inspection", "judgment", "legacy-prose", "unknown")
VERDICTS = ("pass", "fail", "inapplicable", "unknown")


def mapping(value):
    return value if isinstance(value, dict) else {}


def size(value, expected_type):
    return len(value) if isinstance(value, expected_type) else None


def fixed(value, choices):
    return value if type(value) is str and value in choices else None


def verification_counts(rows):
    if not isinstance(rows, list):
        return None
    counts = dict.fromkeys(VERDICTS, 0)
    for row in rows:
        counts[label(mapping(row).get("status"), VERDICTS)] += 1
    return counts


def saved_verdict_counts(value):
    if not isinstance(value, dict):
        return None
    return {name: count(value.get(name)) for name in VERDICTS}


def requested_checks(request):
    checks = request.get("checks")
    if not isinstance(checks, dict):
        return None
    totals = dict.fromkeys(CHECK_KINDS, 0)
    for check in checks.values():
        kind = "legacy-prose" if type(check) is str else label(mapping(check).get("kind"), CHECK_KINDS)
        totals[kind] += 1
    return totals


def process_exit_code(value):
    return value if type(value) is int and -255 <= value <= 255 else None


def budget_changes(state):
    changes = state.get("budget_extensions")
    if not isinstance(changes, list):
        return None
    return [
        {"after_dispatch": count(item.get("after_dispatch")), "total": count(item.get("total"))}
        for item in changes
        if isinstance(item, dict)
    ]


def telemetry_summary(run, state, *, metrics=None):
    metrics = run_metrics(run, state) if metrics is None else metrics
    request = mapping(state.get("request"))
    started = timestamp(state.get("started_at"))
    attempts = []
    for row, attempt in zip(metrics["usage"]["attempts"], state["attempts"], strict=True):
        attempts.append(
            {
                **row,
                "dispatched_after_seconds": elapsed(started, timestamp(attempt.get("started_at"))),
                "resolved_after_seconds": elapsed(started, timestamp(attempt.get("resolved_at"))),
                "receipt_missing_after_seconds": elapsed(started, timestamp(attempt.get("receipt_missing_at"))),
                "process_outcome": fixed(attempt.get("process_outcome"), PROCESS_OUTCOMES),
                "process_exit_code": process_exit_code(attempt.get("process_exit_code")),
                "receipt_source": fixed(attempt.get("receipt_source"), RECEIPT_SOURCES),
                "gate": fixed(attempt.get("gate"), GATES),
                "diagnostic_code": fixed(attempt.get("diagnostic_code"), DIAGNOSTIC_CODES),
                "native_result": fixed(mapping(attempt.get("native")).get("status"), ("built", "done", "complete")),
                "verification": saved_verdict_counts(attempt.get("verification_counts")),
            }
        )
    return {
        "format": "bmad-delivery-telemetry",
        "schema_version": 1,
        "exporter_version": CONTROLLER_VERSION,
        "status": label(state.get("status"), RUN_STATUSES),
        "phase": label(state.get("phase"), PHASES),
        "authority_mode": fixed(mapping(request.get("authority")).get("mode"), ("A", "B", "C")),
        "output_class": fixed(request.get("kind"), ("code", "non-code", "mixed")),
        "intake_kind": fixed(mapping(request.get("intake")).get("kind"), ("idea", "literature", "brainstorm", "forge")),
        "verification_version": count(state.get("version")),
        "dispatched": len(attempts),
        "initial_budget": count(request.get("budget")),
        "budget": count(state.get("budget")),
        "budget_extensions": budget_changes(state),
        "owner_inputs": {field: size(state.get(field), list) for field in ("answers", "approvals", "proposals")},
        "required_checks_by_kind": requested_checks(request),
        "latest_verification": verification_counts(state.get("verification")),
        "published_artifacts": size(state.get("artifact_sha256"), dict),
        **metrics,
        "usage": {**metrics["usage"], "attempts": attempts},
    }
