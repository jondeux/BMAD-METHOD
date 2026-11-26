import json
import os
import subprocess
import sys
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "deliver.py"
CODEX = ["/usr/bin/python", "/old/install/codex_worker.py", "/usr/bin/codex", "", ""]


def saved_run(run, attempts, **fields):
    run.mkdir()
    record = {
        "version": 1,
        "status": "complete",
        "phase": "publish",
        "budget": len(attempts),
        "worker": CODEX,
        "attempts": attempts,
        **fields,
    }
    (run / "state.json").write_text(json.dumps(record))
    for number in range(1, len(attempts) + 1):
        (run / "attempts" / str(number)).mkdir(parents=True)
    return run


def usage_event(input_tokens, cached, output, reasoning=None):
    return {
        "type": "turn.completed",
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "cache_write_input_tokens": 0,
            "output_tokens": output,
            "reasoning_output_tokens": reasoning,
        },
    }


def append_log(run, attempt, *rows):
    with (run / "attempts" / str(attempt) / "worker.log").open("a") as stream:
        for row in rows:
            stream.write((json.dumps(row) if isinstance(row, dict) else row) + "\n")


def cli(command, run):
    return subprocess.check_output([sys.executable, "-B", str(RUNNER), command, str(run)], text=True, timeout=10)


def test_saved_provider_counts_and_independent_checks(tmp_path):
    document = saved_run(
        tmp_path / "document",
        [{"phase": phase, "status": "ok"} for phase in ("route", "build", "verify")],
    )
    code = saved_run(
        tmp_path / "code",
        [
            {"phase": "route", "status": "ok"},
            {"phase": "build", "status": "ok"},
            {"phase": "verify", "status": "ok", "verifier": "/local/checker"},
            {"phase": "verify", "status": "ok", "verifier": "/local/checker"},
        ],
    )
    for run, observations in [
        (document, [(17926, 10240, 135, 44), (16859, 10240, 108, 53), (16934, 10240, 135, 49)]),
        (code, [(18126, 10240, 178, 87), (34439, 27136, 591, 382)]),
    ]:
        for attempt, values in enumerate(observations, 1):
            append_log(run, attempt, "mixed stderr", {"type": "turn.started"}, usage_event(*values))
    append_log(code, 4, usage_event(999, 100, 999))

    first = json.loads(cli("status", document))
    second = json.loads(cli("support", code))
    assert (first["dispatched"], second["dispatched"]) == (3, 4)
    assert first["usage"]["coverage"] == "observed"
    assert second["usage"]["coverage"] == "partial"
    assert first["usage"]["attempts"][0]["source"] == "legacy-worker-log"
    assert [row["worker"] for row in second["usage"]["attempts"]] == [
        "codex",
        "codex",
        "independent-checker",
        "independent-checker",
    ]
    assert all(row["observed_tokens"] is None for row in second["usage"]["attempts"][2:])
    assert first["usage"]["observed_events"] + second["usage"]["observed_events"] == 5
    assert first["elapsed_seconds"] is second["elapsed_seconds"] is None
    assert second["retries"] == {"recorded": 0, "attempts_without_metadata": 4}
    assert {
        key: first["usage"]["observed_tokens"][key] + second["usage"]["observed_tokens"][key]
        for key in first["usage"]["observed_tokens"]
    } == {
        "input_tokens": 104284,
        "cached_input_tokens": 68096,
        "noncached_input_tokens": 36188,
        "cache_write_input_tokens": 0,
        "output_tokens": 1147,
        "reasoning_output_tokens": 615,
    }
    assert json.loads(cli("support", code)) == second


def test_latest_cumulative_event_and_missing_counters(tmp_path):
    run = saved_run(tmp_path / "run", [{"phase": "route"}, {"phase": "build"}, {"phase": "verify"}])
    append_log(
        run,
        1,
        "x" * (1024 * 1024),
        usage_event(4, 2, 1),
        usage_event(10, 6, 3),
        usage_event(10, 6, 3),
        '{"type":"turn.completed"',
        usage_event("missing", 0, 3),
    )
    append_log(run, 2, usage_event(0, 1, 0))
    append_log(run, 3, usage_event(True, 0, 2))
    data = json.loads(cli("status", run))["usage"]
    assert data["coverage"] == "partial"
    assert data["observed_events"] == 2
    assert data["attempts"][0]["observed_tokens"]["input_tokens"] == 10
    assert data["attempts"][0]["coverage"] == "partial"
    assert data["attempts"][1]["observed_tokens"]["input_tokens"] == 0
    assert data["attempts"][2]["observed_tokens"] is None
    assert data["observed_tokens"] == {
        "input_tokens": 10,
        "cached_input_tokens": None,
        "noncached_input_tokens": None,
        "cache_write_input_tokens": 0,
        "output_tokens": 3,
        "reasoning_output_tokens": None,
    }


def test_support_only_projects_known_labels_and_accounting(tmp_path):
    secrets = [
        f"PRIVATE-{label}-392e"
        for label in (
            "intake",
            "answer",
            "artifact",
            "prompt",
            "log",
            "credential",
            "error",
            "workflow",
            "path",
            "phase",
            "state",
            "retry",
        )
    ]
    intake, answer, artifact, prompt, log, credential, error, workflow, path, phase, state, retry = secrets
    run = saved_run(
        tmp_path / path,
        [
            {
                "phase": phase,
                "status": state,
                "number": path,
                "retry": retry,
                "started_at": credential,
                "process_outcome": error,
                "process_exit_code": error,
                "gate": state,
                "diagnostic_code": credential,
                "receipt_source": log,
                "verification_counts": {"pass": prompt, artifact: 1},
            },
            {"phase": "build", "status": "ok", "workflow": workflow, "retry": None, "native": {"status": workflow}},
        ],
        status=state,
        phase=phase,
        budget=credential,
        started_at=credential,
        request={"kind": error, "authority": {"mode": answer}, "intake": {"kind": intake, "text": intake}},
        budget_extensions=[{"after_dispatch": credential, "total": credential, "reason": error}],
        answers=[answer],
        route={"rationale": prompt},
        native_worker=["/python", credential, "wait"],
        worker=[*CODEX[:4], credential],
        artifact_sha256={artifact: "hash"},
        verification=[{"evidence": prompt}],
        error=error,
    )
    event = usage_event(10, 2, 3)
    event["usage"]["unexpected"] = credential
    append_log(run, 1, event, log)
    append_log(run, 2, usage_event(500, 50, 700), log)
    snapshot = (run / "state.json").read_bytes()
    exported = cli("support", run)
    assert all(secret not in exported for secret in secrets)
    result = json.loads(exported)
    assert result["schema_version"] == 1
    assert result["status"] == result["phase"] == "unknown"
    assert result["budget"] is result["elapsed_seconds"] is None
    assert result["usage"]["observed_events"] == 1
    assert result["usage"]["native_nested_usage"] == "unavailable"
    assert result["usage"]["attempts"][1]["workflow"] == "unknown"
    assert result["usage"]["attempts"][1]["observed_tokens"] is None
    exported = cli("telemetry", run)
    assert all(secret not in exported for secret in secrets)
    telemetry = json.loads(exported)
    assert telemetry["format"] == "bmad-delivery-telemetry"
    assert telemetry["authority_mode"] is telemetry["output_class"] is telemetry["intake_kind"] is None
    assert telemetry["budget_extensions"] == [{"after_dispatch": None, "total": None}]
    assert telemetry["usage"]["attempts"][0]["diagnostic_code"] is None
    assert telemetry["usage"]["attempts"][0]["verification"] == dict.fromkeys(
        ("pass", "fail", "inapplicable", "unknown")
    )
    assert not (run / "telemetry.json").exists()
    assert (run / "state.json").read_bytes() == snapshot
    assert not (run / ".lock").exists()


def test_unavailable_usage_for_symlink_and_fifo_logs(tmp_path):
    run = saved_run(tmp_path / "run", [{"phase": "route"}, {"phase": "build"}])
    outside = tmp_path / "outside.log"
    outside.write_text(json.dumps(usage_event(1000000001, 0, 0)))
    (run / "attempts" / "1" / "worker.log").symlink_to(outside)
    os.mkfifo(run / "attempts" / "2" / "worker.log")
    assert json.loads(cli("support", run))["usage"]["coverage"] == "unavailable"


def test_support_elapsed_time_uses_saved_activity(tmp_path):
    run = saved_run(
        tmp_path / "run",
        [
            {"phase": "route", "status": "ok", "started_at": 100, "resolved_at": 101.5, "retry": None},
            {"phase": "build", "status": "dispatched", "started_at": 104, "retry": "interrupted"},
        ],
        started_at=99.5,
        status="dispatched",
    )
    result = json.loads(cli("support", run))
    assert result["elapsed_basis"] == "last-saved-activity"
    assert result["elapsed_seconds"] == 4.5
    assert [row["elapsed_seconds"] for row in result["usage"]["attempts"]] == [1.5, None]
    assert result["retries"] == {"recorded": 1, "attempts_without_metadata": 0}


def test_telemetry_checkpoint_retains_settled_provider_usage(tmp_path):
    run = saved_run(
        tmp_path / "run",
        [{"phase": "route", "status": "ok"}, {"phase": "build", "status": "dispatched"}],
        status="dispatched",
    )
    append_log(run, 1, usage_event(10, 2, 3))
    append_log(run, 2, usage_event(99, 2, 3))
    script = """
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from deliver import Delivery, read_state
run = Path(sys.argv[2])
Delivery(run, read_state(run), None).save_telemetry()
"""
    subprocess.run([sys.executable, "-B", "-c", script, str(RUNNER.parent), str(run)], check=True, timeout=10)
    telemetry = json.loads((run / "telemetry.json").read_text())
    assert telemetry["usage"]["attempts"][0]["observed_tokens"]["input_tokens"] == 10
    assert telemetry["usage"]["attempts"][1]["observed_tokens"] is None
    assert json.loads(cli("telemetry", run))["usage"]["observed_tokens"]["input_tokens"] == 109


def test_support_survives_unreadable_logs(tmp_path):
    run = saved_run(tmp_path / "run", [{"phase": "route"}])
    append_log(run, 1, usage_event(10, 2, 1))
    directory = run / "attempts"
    directory.chmod(0)
    try:
        result = json.loads(cli("support", run))
        assert result["usage"]["observed_events"] in (0, 1)
    finally:
        directory.chmod(0o700)


def test_shareable_export_errors_omit_private_paths_and_content(tmp_path):
    run = saved_run(tmp_path / "PRIVATE-run-path", [None], request={"text": "PRIVATE-request"})
    for command in ("support", "telemetry"):
        result = subprocess.run(
            [sys.executable, "-B", str(RUNNER), command, str(run)], text=True, capture_output=True, timeout=10
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr == f"BMAD delivery: unable to read the saved {command} snapshot\n"
