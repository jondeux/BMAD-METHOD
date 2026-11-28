import json

from test_delivery import CODE_INTAKE, command, managed_intake_args, start_intake, subscription_provider, update_intake
from test_delivery import workspace as workspace
from test_run_metrics import cli, saved_run


def export_sidecar(run):
    exported = command("telemetry", str(run))
    assert exported == json.loads((run / "telemetry.json").read_text())
    assert (run / "telemetry.json").stat().st_mode & 0o777 == 0o600
    return exported


def test_intake_telemetry_explains_source_failure_and_owner_route_correction(workspace):
    run = workspace / "run"
    initial = {
        **CODE_INTAKE,
        "text": "intake-route-only\nPRIVATE_REQUEST_TEXT",
        "sources": [{"id": "PRIVATE_SOURCE_ID", "readable": False}],
        "authority": {**CODE_INTAKE["authority"], "outcome": "PRIVATE_OUTCOME", "deliverable": "PRIVATE_DELIVERABLE"},
        "checks": {"PRIVATE_CHECK_ID": {"kind": "executable", "behavior": "PRIVATE_ACCEPTANCE_BEHAVIOR"}},
    }
    start_intake(workspace, initial, expect=2)
    blocked = export_sidecar(run)
    assert blocked["intake"]["gate"] == "answer-required"
    assert blocked["intake"]["reason"] == "unreadable-source"
    assert blocked["intake"]["history"][-1]["after_dispatch"] == 0

    update_intake(workspace, {"sources": [{"id": "PRIVATE_SOURCE_ID", "excerpt": "PRIVATE_EXCERPT"}]}, expect=2)
    selected = export_sidecar(run)
    assert selected["intake"]["route_id"] == "small"
    assert selected["intake"]["decision_source"] == "classifier"
    assert selected["intake"]["reason"] == "missing-subtype"

    update_intake(workspace, {"route_id": "trivial", "subtype": "run-local-code"})
    report = export_sidecar(run)
    assert report["status"] == "complete"
    intake = report["intake"]
    assert (
        intake["catalog_version"],
        intake["revision"],
        intake["route_id"],
        intake["subtype"],
        intake["decision_source"],
        intake["gate"],
        intake["reason"],
    ) == (1, 3, "trivial", "run-local-code", "owner", None, None)
    assert any(
        entry["gate"] == "answer-required" and entry["reason"] == "unreadable-source" for entry in intake["history"]
    )
    assert any(
        entry["route_id"] == "small"
        and entry["decision_source"] == "classifier"
        and entry["reason"] == "missing-subtype"
        and entry["after_dispatch"] == 1
        for entry in intake["history"]
    )
    assert any(
        entry["route_id"] == "trivial" and entry["decision_source"] == "owner" and entry["after_dispatch"] == 1
        for entry in intake["history"]
    )
    assert "PRIVATE_" not in json.dumps(report)


def test_intake_telemetry_retains_a_zero_dispatch_provider_pause(workspace, monkeypatch):
    control = subscription_provider(workspace, monkeypatch, "codex", "exhausted")
    worker = str(workspace / "fixture-worker")
    run = workspace / "run"
    command(
        *managed_intake_args(
            workspace,
            CODE_INTAKE,
            "--codex",
            "--native-worker",
            worker,
            "--verify-worker",
            worker,
            "--confirm-plan-only",
        ),
        expect=2,
    )
    paused = export_sidecar(run)["intake"]
    assert (paused["gate"], paused["reason"], paused["subscription_host"]) == (
        "subscription-paused",
        "allowance-exhausted",
        "codex",
    )
    command("resume", str(run), expect=2)
    assert export_sidecar(run)["intake"]["history"] == paused["history"]

    control.write_text("ready")
    command("resume", str(run))
    report = export_sidecar(run)
    assert report["status"] == "complete" and report["usage"]["observed_events"] == 1
    assert report["intake"]["history"][0] == paused["history"][0]
    assert report["intake"]["history"][0]["after_dispatch"] == 0
    assert "PRIVATE_" not in json.dumps(report)


def test_intake_history_keeps_same_gate_on_distinct_dispatches(workspace):
    run = workspace / "run"
    start_intake(workspace, {**CODE_INTAKE, "text": "intake-no-receipt"}, expect=2)
    command("resume", str(run), "--retry", expect=2)
    history = export_sidecar(run)["intake"]["history"]
    assert [row["after_dispatch"] for row in history if row["gate"] == "interrupted"] == [1, 2]
    command("resume", str(run), expect=2)
    assert export_sidecar(run)["intake"]["history"] == history


def test_offline_intake_export_revalidates_stored_diagnostics_and_excludes_private_fields(tmp_path):
    corrupt = {
        "revision": "PRIVATE_REVISION",
        "catalog_version": "PRIVATE_CATALOG",
        "route_id": "PRIVATE_ROUTE",
        "subtype": "PRIVATE_SUBTYPE",
        "decision_source": "PRIVATE_SOURCE",
        "gate": "PRIVATE_GATE",
        "reason": "PRIVATE_REASON",
        "subscription_host": "PRIVATE_PROVIDER",
        "phase": "PRIVATE_PHASE",
        "after_dispatch": "PRIVATE_DISPATCH",
        "PRIVATE_KEY": "PRIVATE_VALUE",
    }
    run = saved_run(
        tmp_path / "PRIVATE_RUN_DIRECTORY",
        [
            {
                "phase": "route",
                "status": "ok",
                "error": "PRIVATE_ERROR_TEXT",
                "catalog_version": "PRIVATE_ATTEMPT_CATALOG",
            }
        ],
        intake_version=1,
        intake_revision=4,
        classification={"route_id": "small", "subtype": "product-brief", "source": "owner"},
        request={"intake": {"text": "PRIVATE_PROMPT_AND_ARTIFACT"}, "checks": {"PRIVATE_CHECK_ID": "PRIVATE_BEHAVIOR"}},
        status="subscription-paused",
        intake_gate={"code": "PRIVATE_GATE_CODE", "message": "PRIVATE_QUESTION"},
        subscription_pause={"host": "PRIVATE_PROVIDER_ACCOUNT", "reason": "PRIVATE_PAUSE_REASON"},
        answers=[{"answer": "PRIVATE_ANSWER"}],
        subscription_account="PRIVATE_ACCOUNT_FINGERPRINT",
        run_id="PRIVATE_RUN_ID",
        artifact_sha256={"PRIVATE_PUBLISHED_PATH": "PRIVATE_ARTIFACT_HASH"},
        approvals=["PRIVATE_APPROVAL_ID"],
        intake_history=[
            {"revision": 1, "route_id": "trivial", "decision_source": "classifier"},
            *([corrupt] * 128),
            {**corrupt, "revision": 4, "gate": "subscription-paused"},
            {**corrupt, "revision": 4, "gate": "subscription-paused"},
        ],
    )
    before = (run / "state.json").read_bytes()
    log = run / "attempts/1/provider.jsonl"
    log.write_text(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "output_tokens": 1, "PRIVATE_USAGE_KEY": "PRIVATE_PROVIDER_EVENT"},
                "message": "PRIVATE_RAW_MODEL_RESULT",
            }
        )
        + "\n"
    )
    (log.parent / "receipt.json").write_text(
        json.dumps({"artifacts": [{"path": "PRIVATE_ARTIFACT_PATH", "content": "PRIVATE_ARTIFACT_CONTENT"}]})
    )
    raw = cli("telemetry", run)
    assert "PRIVATE_" not in raw
    report = json.loads(raw)
    intake = report["intake"]
    assert intake["route_id"] == "small" and intake["subtype"] is None
    assert intake["reason"] is None and intake["subscription_host"] is None
    assert intake["history_truncated"] is False
    assert [item["revision"] for item in intake["history"]] == [1, 4]
    assert intake["history"][-1]["phase"] is None and intake["history"][-1]["route_id"] is None
    assert report["usage"]["observed_tokens"]["input_tokens"] == 10
    assert (run / "state.json").read_bytes() == before
    assert not (run / "telemetry.json").exists()


def test_offline_intake_history_retains_the_latest_distinct_checkpoints(tmp_path):
    history = [{"revision": n, "route_id": "small", "decision_source": "owner"} for n in range(1, 131)]
    run = saved_run(tmp_path / "bounded", [], intake_version=1, intake_history=[*history, *history[-1:] * 128])
    intake = json.loads(cli("telemetry", run))["intake"]
    assert intake["history_truncated"] is True
    assert [entry["revision"] for entry in intake["history"]] == list(range(3, 131))


def test_intake_telemetry_reports_resolved_subtype_at_a_capability_gate(workspace):
    result = start_intake(workspace, {**CODE_INTAKE, "route_id": "existing"}, worker=False, expect=2)
    assert result["status"] == "capability-unavailable"
    intake = export_sidecar(workspace / "run")["intake"]
    assert (intake["route_id"], intake["subtype"], intake["reason"]) == (
        "existing",
        "project-context",
        "unsupported-selection",
    )


def test_legacy_offline_telemetry_has_explicit_unknown_intake_fields(tmp_path):
    run = saved_run(tmp_path / "legacy", [], classification={"route_id": "small"}, intake_history=[1])
    before = (run / "state.json").read_bytes()
    intake = json.loads(cli("telemetry", run))["intake"]
    assert intake["history"] == [] and intake["history_truncated"] is False
    assert all(value is None for key, value in intake.items() if key not in ("history", "history_truncated"))
    assert (run / "state.json").read_bytes() == before
    assert not (run / "telemetry.json").exists()
