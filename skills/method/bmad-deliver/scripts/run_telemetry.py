"""Project a saved delivery run into a shareable diagnostic."""

from collections import deque
from functools import cache

import intake_router
import subscription
from bundle_layout import RELEASE_VERSION
from run_metrics import PHASES, RUN_STATUSES, count, elapsed, label, run_metrics, timestamp

TELEMETRY_FILE = "telemetry.json"
GATES = (
    "approval-required",
    "answer-required",
    "capability-unavailable",
    "subscription-paused",
    "budget-exhausted",
    "interrupted",
    "checker-fault",
)
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
INTAKE_HISTORY_LIMIT = 128
INTAKE_REASONS = (
    "unreadable-source",
    "missing-material",
    "allowance",
    "missing-budget",
    "timeout",
    "invalid-selection",
    "classifier-unavailable",
    "classification-deferred",
    "missing-subtype",
    "unsupported-selection",
    "delivery-contract",
    "document-workflow",
    "output-class",
    "native-unavailable",
    "checker-unavailable",
    "delivery-approval",
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


@cache
def intake_choices():
    try:
        routes = intake_router.read_catalog()["routes"]
        return {route["id"]: tuple(subtype["id"] for subtype in route["subtypes"]) for route in routes}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def intake_fields(row):
    routes = intake_choices() if row.get("route_id") is not None else {}
    route = fixed(row.get("route_id"), routes)
    options = routes.get(route, ())
    subtype = row.get("subtype")
    if subtype is None and len(options) == 1:
        subtype = options[0]
    return {
        "revision": count(row.get("revision")),
        "catalog_version": count(row.get("catalog_version")),
        "route_id": route,
        "subtype": fixed(subtype, options),
        "decision_source": fixed(row.get("decision_source"), ("owner", "classifier")),
        "gate": fixed(row.get("gate"), GATES),
        "reason": fixed(row.get("reason"), (*INTAKE_REASONS, *subscription.PAUSE_REASONS)),
        "subscription_host": fixed(row.get("subscription_host"), subscription.HOSTS),
    }


def intake_snapshot(state):
    if count(state.get("intake_version")) != intake_router.INTAKE_VERSION:
        return intake_fields({})
    decision = mapping(state.get("classification"))
    plan = mapping(state.get("execution_plan"))
    catalog_version = count(plan.get("catalog_version"))
    if catalog_version is None:
        catalog_version = count(state.get("intake_catalog_version"))
    if catalog_version is None:
        catalog_version = next(
            (
                version
                for attempt in reversed(state["attempts"])
                if (version := count(attempt.get("catalog_version"))) is not None
            ),
            None,
        )
    gate = fixed(state.get("status"), GATES)
    pause = mapping(state.get("subscription_pause")) if gate == "subscription-paused" else {}
    intake_gate = mapping(state.get("intake_gate")) if gate else {}
    return intake_fields(
        {
            "revision": state.get("intake_revision"),
            "catalog_version": catalog_version,
            "route_id": plan.get("route_id", decision.get("route_id")),
            "subtype": plan.get("subtype", decision.get("subtype")),
            "decision_source": decision.get("source"),
            "gate": gate,
            "reason": pause.get("reason", intake_gate.get("code")),
            "subscription_host": pause.get("host", state.get("subscription_host")),
        }
    )


def intake_checkpoint(row):
    return {
        **intake_fields(row),
        "phase": fixed(row.get("phase"), PHASES),
        "after_dispatch": count(row.get("after_dispatch")),
    }


def same_intake_checkpoint(previous, current):
    if current["gate"] is None:
        return all(previous[key] == value for key, value in current.items() if key not in ("phase", "after_dispatch"))
    return previous == current


def record_intake_checkpoint(state):
    current = intake_snapshot(state)
    if current["gate"] is None and current["decision_source"] is None:
        return
    checkpoint = {
        **current,
        "phase": fixed(state.get("phase"), PHASES),
        "after_dispatch": len(state["attempts"]),
    }
    history = state.get("intake_history")
    if not isinstance(history, list):
        history = []
    if history and same_intake_checkpoint(intake_checkpoint(mapping(history[-1])), checkpoint):
        return
    if len(history) >= INTAKE_HISTORY_LIMIT:
        state["intake_history_truncated"] = True
    state["intake_history"] = [*history[-(INTAKE_HISTORY_LIMIT - 1) :], checkpoint]


def intake_projection(state):
    version = (
        intake_router.INTAKE_VERSION if count(state.get("intake_version")) == intake_router.INTAKE_VERSION else None
    )
    stored = state.get("intake_history") if version is not None else None
    history = deque(maxlen=INTAKE_HISTORY_LIMIT)
    truncated = version is not None and state.get("intake_history_truncated") is True
    if isinstance(stored, list):
        for row in stored:
            checkpoint = intake_checkpoint(mapping(row))
            if checkpoint["gate"] is None and checkpoint["decision_source"] is None:
                continue
            if history and same_intake_checkpoint(history[-1], checkpoint):
                continue
            truncated |= len(history) == INTAKE_HISTORY_LIMIT
            history.append(checkpoint)
    return {
        "protocol_version": version,
        **intake_snapshot(state),
        "history": list(history),
        "history_truncated": truncated,
    }


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
        "exporter_version": RELEASE_VERSION,
        "status": label(state.get("status"), RUN_STATUSES),
        "phase": label(state.get("phase"), PHASES),
        "authority_mode": fixed(mapping(request.get("authority")).get("mode"), ("A", "B", "C")),
        "output_class": fixed(request.get("kind"), ("code", "non-code", "mixed")),
        "intake_kind": fixed(mapping(request.get("intake")).get("kind"), ("idea", "literature", "brainstorm", "forge")),
        "intake": intake_projection(state),
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
