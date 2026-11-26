import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RUNNER = SCRIPTS / "deliver.py"
NATIVE_HOST = SCRIPTS / "native_host.py"
REPO = SCRIPTS.parents[3]
AVAILABILITY_SQL = (
    "SELECT NOT EXISTS (SELECT 1 FROM bookings WHERE room_id = :room_id "
    "AND starts_at < ends_at AND starts_at < :requested_end AND :requested_start < ends_at);\n"
)
BRIEF_LIMITATION = "The simulation excluded false releases."
SQLITE_CHECK = """\
from pathlib import Path
import sqlite3
import sys

query = Path(sys.argv[1]).read_text()
with sqlite3.connect(":memory:") as db:
    db.execute("CREATE TABLE bookings(room_id TEXT, starts_at INTEGER, ends_at INTEGER)")
    db.execute("INSERT INTO bookings VALUES ('A', 600, 660)")
    db.commit()
    allowed = (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ)
    db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    for start, end, expected in [(630, 690, 0), (540, 600, 1), (660, 720, 1)]:
        actual = db.execute(query, {"room_id": "A", "requested_start": start, "requested_end": end}).fetchone()
        assert actual == (expected,), (start, end, actual)
print("SQLite confirmed overlap and adjacent boundaries")
"""
TYPED_CHECKS = {
    "booking": {"kind": "executable", "behavior": "Reject overlap and allow adjacent intervals"},
    "caveat": {"kind": "source-inspection", "behavior": "State that the simulation excluded false releases"},
    "decision": {"kind": "judgment", "behavior": "Make the proposed decision easy to find"},
}
FIXTURE = r"""
from pathlib import Path
import os
import subprocess
import sys
import time

from deliver import digest, read_json, write_json

job_file, receipt_file = map(Path, sys.argv[1:])
job = read_json(job_file)
request = job["request"]
phase = job["phase"]
scenario = request["intake"]["text"].splitlines()[0]
code = request["kind"] == "code"
name = "Booking prototype" if code else "Director decision brief"
route = {
    "deliverable": name,
    "workflows": job.get("native_workflows", ["bmad-build-auto" if code else "bmad-product-brief"]),
    "rationale": "The local deliverable preserves the specified behavior.",
    "assumptions": [],
}


def hold():
    Path("worker-held").touch()
    for _ in range(500):
        if Path("release").exists():
            return
        time.sleep(.02)
    raise RuntimeError("test never released worker")


def typed_result():
    artifacts = {item["path"]: item["content"] for item in job["artifacts"]}
    hashes = {path: digest(content.encode()) for path, content in artifacts.items()}
    assert job["artifact_sha256"] == hashes
    if scenario == "evidence-checker-fault" and not (job_file.parents[3] / "checker-repaired").is_file():
        return {
            "status": "checker-fault", "error": "The checker configuration is missing.",
            "verification_version": 2, "verification_id": job["verification_id"], "artifact_sha256": hashes,
        }
    rows = []
    for check_id, check in request["checks"].items():
        kind = check["kind"]
        row = {"id": check_id, "kind": kind, "status": "pass"}
        if kind == "executable":
            path = Path("availability.sql")
            path.write_bytes(artifacts[path.name].encode())
            process = subprocess.run(
                [sys.executable, "-B", "-c", SQLITE_CHECK, path.name], capture_output=True, text=True
            )
            row.update(
                status="pass" if process.returncode == 0 else "fail",
                evidence=process.stdout.strip() or process.stderr.strip(),
                observation={"argv": process.args, "exit_code": process.returncode,
                             "stdout": process.stdout, "stderr": process.stderr},
            )
            if scenario == "evidence-prose":
                row.pop("observation")
                row["evidence"] = "OK"
            if scenario == "evidence-failed-exit":
                row["observation"]["exit_code"] = 1
            if scenario == "evidence-repair" and job["attempt"] == 3:
                row.update(status="fail", evidence="Fixture requests a rebuild.")
        elif kind == "source-inspection":
            path, content = next((path, content) for path, content in artifacts.items() if path.endswith(".md"))
            first, quote = next(
                (index, line) for index, line in enumerate(content.splitlines(), 1) if "false releases" in line
            )
            references = [{"source": "artifact", "path": path, "line_start": first, "quote": quote}]
            if scenario.startswith("evidence"):
                references.append({
                    "source": "intake", "line_start": 2, "line_end": 2, "quote": BRIEF_LIMITATION,
                })
            if scenario == "evidence-missing-reference":
                references[0]["path"] = "../brief.md"
            if scenario == "evidence-wrong-quote":
                references[0]["quote"] = "The simulation included false releases."
            if scenario == "evidence-intake-only":
                references = references[1:]
            row.update(evidence="The observed brief preserves the source limitation.", references=references)
        else:
            row["evidence"] = "The proposed decision is the first line of the brief."
        rows.append(row)
    if scenario == "evidence-stale":
        hashes["availability.sql"] = "0" * 64
    verification_id = "previous-verification" if scenario == "evidence-replayed" else job["verification_id"]
    return {
        "status": "ok", "verification_version": 2, "verification_id": verification_id,
        "artifact_sha256": hashes, "checks": rows,
    }


if phase == "route":
    result = {"status": "ok", **route}
    if scenario == "unlisted-initial":
        result["deliverable"] = "Video presentation"
    if scenario == "different-initial-class":
        result["kind"] = "code"
    if scenario == "conflicting-initial-workflow":
        result["workflows"] = ["bmad-build-auto"]
elif phase == "build":
    if scenario == "stakeholder" and not job["answers"]:
        result = {"status": "blocked", "question": "Who owns the trial decision?"}
    elif scenario.startswith("replacement") and job["route"]["deliverable"] == name:
        result = {"status": "replace", **route, "deliverable": "One-page decision memo"}
        if scenario == "replacement-video":
            result["deliverable"] = "Video presentation"
        if scenario == "replacement-class":
            result["kind"] = "code"
        if scenario == "replacement-same-class":
            result["kind"] = request["kind"]
        if scenario == "replacement-workflow":
            result["workflows"] = ["custom-workflow", "bmad-build-auto"]
    elif scenario == "invalid-path":
        result = {"status": "ok", "artifacts": [{"path": "../escape", "content": "invalid"}]}
    elif scenario.startswith("evidence"):
        sql = AVAILABILITY_SQL
        if scenario == "evidence-repair" and job["verification"]:
            sql += "-- Rebuilt from the previous result.\n"
        result = {"status": "ok", "artifacts": [
            {"path": "availability.sql", "content": sql},
            {"path": "brief.md", "content": "Decision: trial manual recovery.\n" + BRIEF_LIMITATION + "\n"},
        ]}
    elif code:
        result = {"status": "ok", "artifacts": [{
            "path": "booking.py",
            "content": "def conflict(first, second):\n    return first[0] < second[1] and second[0] < first[1]\n",
        }]}
    else:
        repaired = bool(job["verification"])
        limitation = "The simulation omitted false releases."
        content = "Decision: trial manual recovery. Proposed owner: facilities director.\n"
        if scenario != "repair" or repaired:
            content += limitation + "\n"
        result = {"status": "ok", "artifacts": [{"path": "decision/brief.md", "content": content}]}
elif phase == "verify" and job.get("verification_version") == 2:
    result = typed_result()
elif phase == "verify":
    check_id, = request["checks"]
    artifact = job["artifacts"][-1]
    content = artifact["content"]
    if code:
        snapshot = Path("booking.py")
        snapshot.write_text(content)
        process = subprocess.run(
            [sys.executable, "-B", "-c",
             "from booking import conflict; "
             "assert conflict((9, 11), (10, 12)); "
             "assert not conflict((9, 11), (11, 12)); print('overlap and adjacency verified')"],
            capture_output=True, text=True,
        )
        observed = process.stdout.strip() or process.stderr.strip()
        verdict = "pass" if process.returncode == 0 else "fail"
    else:
        observed = next((line for line in content.splitlines() if "omitted false releases" in line), "")
        verdict = "pass" if observed else "inapplicable"
        observed = observed or "The fixture found no discussion of false releases."
    if scenario == "checker-repair" and not (job_file.parents[3] / "checker-repaired").is_file():
        verdict, observed = "fail", "The checker needs a configuration repair."
    result = {"status": "ok", "checks": [{"id": check_id, "status": verdict, "evidence": observed}]}
    if scenario == "declared-checker-fault" and not (job_file.parents[3] / "checker-repaired").is_file():
        result = {"status": "checker-fault", "error": "The checker configuration is missing."}
    if scenario == "repair-then-checker-fault":
        if job["attempt"] == 3:
            result["checks"][0].update(status="fail", evidence="The first build needs a repair.")
        elif job["attempt"] == 5:
            result = {"status": "checker-fault", "error": "The repaired build could not be checked."}
else:
    raise AssertionError(phase)

hold_phase = os.environ.get("BMAD_TEST_HOLD")
if hold_phase == f"{phase}:before":
    hold()
    sys.exit(75)
write_json(receipt_file, result)
if hold_phase == f"{phase}:after":
    hold()
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    worker = tmp_path / "fixture-worker"
    worker.write_text(
        f"#!{sys.executable}\n"
        f"AVAILABILITY_SQL = {AVAILABILITY_SQL!r}\n"
        f"BRIEF_LIMITATION = {BRIEF_LIMITATION!r}\n"
        f"SQLITE_CHECK = {SQLITE_CHECK!r}\n" + FIXTURE.lstrip()
    )
    worker.chmod(0o700)
    monkeypatch.setenv("PYTHONPATH", str(SCRIPTS))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.delenv("BMAD_TEST_HOLD", raising=False)
    return tmp_path


def prepare(
    workspace, *, kind="non-code", mode="C", scenario="baseline", budget=3, authority=None, checks=None, timeout=15
):
    request = workspace / "request.json"
    if checks is None:
        checks = (
            {"booking": "Reject overlap and allow adjacent intervals"}
            if kind == "code"
            else {"caveat": "State that the simulation omitted false releases"}
        )
    request.write_text(
        json.dumps(
            {
                "kind": kind,
                "intake": {"kind": "idea" if kind == "code" else "literature", "text": scenario},
                "authority": {
                    "mode": mode,
                    "outcome": "Resolve a booking trial question",
                    "deliverable": "Booking prototype" if kind == "code" else "Director decision brief",
                    "limits": ["Keep artifacts local", "Retain the specified booking behavior or study caveat"],
                    **(authority or {}),
                },
                "checks": checks,
                "budget": budget,
                "timeout_seconds": timeout,
            }
        )
    )
    return ["start", str(workspace / "run"), "--request", str(request), "--worker", str(workspace / "fixture-worker")]


def launch(*args):
    return subprocess.Popen(
        [sys.executable, "-B", str(RUNNER), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def command(*args, expect=0):
    with launch(*args) as process:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == expect, (stdout, stderr)
        return json.loads(stdout) if stdout else stderr


def state(run):
    return json.loads((run / "state.json").read_text())


def wait_for(path):
    deadline = time.monotonic() + 10
    while not path.exists():
        assert time.monotonic() < deadline, path
        time.sleep(0.02)


def test_code_recovers_receipt_without_redispatch_and_enforces_budget(workspace, monkeypatch):
    run = workspace / "run"
    args = prepare(workspace, kind="code", mode="C", budget=2)
    attempt = run / "attempts" / "2"
    monkeypatch.setenv("BMAD_TEST_HOLD", "build:after")
    with launch(*args) as controller:
        try:
            wait_for(attempt / "worker-held")
            active = command("status", str(run))
            assert active["status"] == "dispatched"
            assert active["pending_attempt"]["job"] == str(attempt / "job.json")
            assert "Wait for the worker" in active["next_action"]
            assert "in progress" in command("resume", str(run), expect=1)
            controller.kill()
            controller.wait(timeout=5)
            assert "in progress" in command("resume", str(run), expect=1)
        finally:
            (attempt / "release").touch()
    monkeypatch.delenv("BMAD_TEST_HOLD")
    for _ in range(100):
        with launch("resume", str(run)) as resumed:
            stdout, stderr = resumed.communicate(timeout=5)
        if resumed.returncode != 1:
            break
        assert "in progress" in stderr
        time.sleep(0.02)
    assert resumed.returncode == 2
    paused = json.loads(stdout)
    assert (paused["status"], paused["phase"], paused["dispatched"]) == ("budget-exhausted", "verify", 2)
    assert not (run / "artifacts").exists()

    result = command("resume", str(run), "--budget", "3")
    assert result["status"] == "complete"
    assert result["verification_version"] == 1
    assert result["verification_evidence"] == "legacy-prose"
    assert result["dispatched"] == 3
    assert state(run)["budget_extensions"] == [{"after_dispatch": 2, "total": 3}]
    assert result["verification"][0]["evidence"] == "overlap and adjacency verified"
    assert [row["phase"] for row in state(run)["attempts"]] == ["route", "build", "verify"]
    assert (run / "artifacts" / "booking.py").read_text().startswith("def conflict")
    assert command("resume", str(run))["dispatched"] == 3


def test_document_requires_real_approval_and_explicit_retry_without_a_receipt(workspace, monkeypatch):
    run = workspace / "run"
    pending = command(*prepare(workspace, mode="A", budget=2), expect=2)
    assert (pending["status"], pending["dispatched"]) == ("approval-required", 1)
    assert command("resume", str(run), expect=2)["dispatched"] == 1
    assert "approval must name proposal" in command("resume", str(run), "--approve", "wrong", expect=1)
    attempt = run / "attempts" / "2"
    monkeypatch.setenv("BMAD_TEST_HOLD", "build:before")
    with launch("resume", str(run), "--approve", pending["proposal"]["id"]) as controller:
        try:
            wait_for(attempt / "worker-held")
            controller.kill()
            controller.wait(timeout=5)
        finally:
            (attempt / "release").touch()
    monkeypatch.delenv("BMAD_TEST_HOLD")
    for _ in range(100):
        with launch("resume", str(run)) as resumed:
            stdout, stderr = resumed.communicate(timeout=5)
        if resumed.returncode != 1:
            break
        assert "in progress" in stderr
        time.sleep(0.02)
    assert resumed.returncode == 2
    document = json.loads(stdout)
    assert document["dispatched"] == 2
    assert document["status"] == "interrupted"
    assert not (run / "artifacts").exists()
    paused = command("resume", str(run), "--retry", expect=2)
    assert paused["status"] == "budget-exhausted"
    result = command("resume", str(run), "--budget", "4")
    assert result["status"] == "complete"
    assert result["dispatched"] == 4
    assert result["verification"][0]["evidence"] == "The simulation omitted false releases."
    assert "Proposed owner: facilities director." in (run / "artifacts" / "decision" / "brief.md").read_text()
    assert state(run)["approvals"] == [pending["proposal"]["id"]]


@pytest.mark.parametrize("mode", ["A", "B", "C"])
def test_replacement_preserves_acceptance_and_respects_authority(workspace, mode):
    run = workspace / "run"
    authority = {}
    if mode == "B":
        authority["boundaries"] = {
            "allowed_output_classes": ["non-code"],
            "allowed_deliverables": ["Director decision brief", "One-page decision memo"],
        }
    args = prepare(workspace, mode=mode, scenario="replacement", budget=4, authority=authority)
    result = command(*args, expect=0 if mode == "B" else 2)
    if mode == "A":
        result = command("resume", str(run), "--approve", result["proposal"]["id"], expect=2)
    if mode != "B":
        assert result["status"] == "approval-required"
        assert result["proposal"]["route"]["deliverable"] == "One-page decision memo"
        assert not (run / "artifacts").exists()
        result = command("resume", str(run), "--approve", result["proposal"]["id"])
    assert result["status"] == "complete"
    assert result["route"]["deliverable"] == "One-page decision memo"
    assert result["verification"][0]["id"] == "caveat"
    assert len(state(run)["replacements"]) == (1 if mode == "B" else 0)


@pytest.mark.parametrize(
    ("scenario", "dispatched", "error"),
    [
        ("unlisted-initial", 1, "outside the allowed deliverables"),
        ("replacement-video", 2, "outside the allowed deliverables"),
        ("different-initial-class", 1, "outside the allowed output classes"),
        ("replacement-class", 2, "outside the allowed output classes"),
        ("conflicting-initial-workflow", 1, "workflows conflict with the request output class"),
        ("replacement-workflow", 2, "workflows conflict with the request output class"),
    ],
)
def test_mode_b_rejects_conflicting_routes_without_dispatching_them(workspace, scenario, dispatched, error):
    run = workspace / "run"
    authority = {
        "boundaries": {
            "allowed_output_classes": ["non-code"],
            "allowed_deliverables": ["Director decision brief", "One-page decision memo"],
        }
    }
    args = prepare(workspace, mode="B", scenario=scenario, budget=5, authority=authority)
    result = command(*args, expect=2)
    assert (result["status"], result["dispatched"]) == ("interrupted", dispatched)
    assert error in result["error"]
    assert state(run)["proposals"] == state(run)["replacements"] == []
    assert "no proposal" in command("resume", str(run), "--approve", str(dispatched), expect=1)
    assert command("resume", str(run), expect=2)["dispatched"] == dispatched
    assert not (run / "attempts" / str(dispatched + 1)).exists()
    assert not (run / "artifacts").exists()


@pytest.mark.parametrize(
    ("scenario", "authority", "dispatched", "name"),
    [
        ("baseline", {"deliverable": None}, 1, "Director decision brief"),
        (
            "replacement-video",
            {"boundaries": {"allowed_output_classes": ["non-code"]}, "limits": ["Only a local text brief"]},
            2,
            "Video presentation",
        ),
    ],
)
def test_mode_b_saves_one_proposal_for_ambiguous_routes(workspace, scenario, authority, dispatched, name):
    run = workspace / "run"
    args = prepare(workspace, mode="B", scenario=scenario, budget=4, authority=authority)
    pending = command(*args, expect=2)
    assert (pending["status"], pending["dispatched"]) == ("approval-required", dispatched)
    proposal = pending["proposal"]
    assert proposal["route"]["deliverable"] == name
    assert "Mode B delegation limits" in proposal["reason"]
    assert command("status", str(run))["proposal"] == proposal
    assert command("resume", str(run), expect=2) == pending
    assert state(run)["proposals"] == [proposal]
    assert not (run / "attempts" / str(dispatched + 1)).exists()

    result = command("resume", str(run), "--approve", proposal["id"])
    assert (result["status"], result["dispatched"]) == ("complete", dispatched + 2)
    assert result["route"]["deliverable"] == name
    assert result["verification"][0]["id"] == "caveat"
    record = state(run)
    assert record["approvals"] == [proposal["id"]]
    if scenario == "baseline":
        assert record["replacements"] == []
    else:
        assert record["replacements"] == [
            {"attempt": dispatched, "route": proposal["route"], "approval": proposal["id"]}
        ]
        assert command("resume", str(run)) == result
        assert state(run)["replacements"] == record["replacements"]


@pytest.mark.parametrize(
    "boundaries",
    [
        {"allowed_output_classes": ["non-code"]},
        {"allowed_deliverables": ["Director decision brief", "One-page decision memo"]},
    ],
)
def test_mode_b_can_delegate_with_one_allowlist_and_without_prose(workspace, boundaries):
    authority = {"limits": [], "boundaries": boundaries}
    args = prepare(workspace, mode="B", scenario="replacement-same-class", budget=4, authority=authority)
    result = command(*args)
    assert result["route"]["deliverable"] == "One-page decision memo"
    assert result["route"]["kind"] == "non-code"
    assert state(workspace / "run")["proposals"] == []


def test_mode_b_cannot_switch_the_run_class_even_when_both_classes_are_allowed(workspace):
    authority = {"boundaries": {"allowed_output_classes": ["non-code", "code"]}}
    args = prepare(workspace, mode="B", scenario="replacement-class", budget=4, authority=authority)
    result = command(*args, expect=2)
    assert (result["status"], result["dispatched"]) == ("interrupted", 2)
    assert "route must preserve the request output class" in result["error"]


@pytest.mark.parametrize(
    ("boundaries", "error"),
    [
        ({}, "must specify allowed_output_classes or allowed_deliverables"),
        ({"allowed_deliverables": [], "allowed_output_classes": ["non-code"]}, "must be a nonempty list"),
        ({"allowed_deliverables": "Director decision brief"}, "must be a nonempty list"),
        ({"allowed_output_classes": ["slides"]}, "invalid allowed output class"),
        ({"allowed_output_classes": ["code"]}, "request kind is outside the allowed output classes"),
        (
            {"allowed_output_classes": ["non-code"], "allowed_deliverable": ["Director decision brief"]},
            "must specify allowed_output_classes or allowed_deliverables",
        ),
    ],
)
def test_mode_b_validates_bounds_before_creating_a_run(workspace, boundaries, error):
    args = prepare(workspace, mode="B", authority={"boundaries": boundaries})
    assert error in command(*args, expect=1)
    assert not (workspace / "run").exists()


@pytest.mark.parametrize("name", [" ", 42, ["Director decision brief"]])
def test_mode_b_rejects_invalid_owner_labels_before_creating_a_run(workspace, name):
    args = prepare(workspace, mode="B", authority={"deliverable": name})
    assert "authority.deliverable must name a deliverable" in command(*args, expect=1)
    assert not (workspace / "run").exists()


def test_mode_b_resumes_legacy_selected_route_without_reapproval(workspace):
    run = workspace / "run"
    selected = command(*prepare(workspace, mode="B", budget=1), expect=2)
    assert (selected["status"], selected["phase"]) == ("budget-exhausted", "build")
    record = state(run)
    # A version-1 controller could select a prose-only route without an owner label.
    del record["request"]["authority"]["deliverable"]
    (run / "state.json").write_text(json.dumps(record))
    assert command("status", str(run))["route"] == record["route"]
    result = command("resume", str(run), "--budget", "3")
    assert (result["status"], result["dispatched"]) == ("complete", 3)
    assert state(run)["proposals"] == []


def test_status_reads_legacy_snapshot_without_changing_the_run(workspace):
    run = workspace / "run"
    command(*prepare(workspace))
    record = state(run)
    del record["attempt_version"]
    snapshot = run / "state.json"
    snapshot.write_text(json.dumps(record))
    saved = snapshot.read_bytes()
    (run / ".lock").unlink()
    summary = command("status", str(run))
    assert (summary["status"], summary["verification_evidence"]) == ("complete", "legacy-prose")
    assert snapshot.read_bytes() == saved
    assert not (run / ".lock").exists()


def start_typed(workspace, scenario="evidence", *, budget=3, checks=TYPED_CHECKS):
    return prepare(workspace, kind="mixed", scenario=f"{scenario}\n{BRIEF_LIMITATION}", budget=budget, checks=checks)


def test_typed_acceptance_records_sqlite_citations_and_judgment(workspace):
    run = workspace / "run"
    result = command(*start_typed(workspace), "--verify-worker", str(workspace / "fixture-worker"))
    assert result == command("status", str(run))
    assert result["verification_version"] == 2
    assert result["verification_artifact_sha256"] == result["artifact_sha256"]
    assert result["artifact_sha256"] == {
        str(path.relative_to(run / "artifacts")): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (run / "artifacts").iterdir()
    }
    rows = {row["kind"]: row for row in result["verification"]}
    assert set(rows) == {"executable", "source-inspection", "judgment"}
    assert all(row["status"] == "pass" for row in rows.values())
    observation = rows["executable"]["observation"]
    assert observation["exit_code"] == 0
    assert "SQLite confirmed overlap" in observation["stdout"]
    references = rows["source-inspection"]["references"]
    assert {reference["source"] for reference in references} == {"artifact", "intake"}
    assert all(reference["quote"] == BRIEF_LIMITATION for reference in references)


@pytest.mark.parametrize(
    ("scenario", "error"),
    [
        ("evidence-prose", "needs an observed checker result"),
        ("evidence-failed-exit", "needs a successful checker exit"),
        ("evidence-stale", "different artifact digest"),
        ("evidence-replayed", "receipt belongs to a different verification job"),
        ("evidence-missing-reference", "reference does not resolve"),
        ("evidence-wrong-quote", "quote differs from referenced text"),
        ("evidence-intake-only", "pass is missing a required evidence source"),
    ],
)
def test_typed_acceptance_rejects_unsupported_passes(workspace, scenario, error):
    run = workspace / "run"
    result = command(*start_typed(workspace, scenario), "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert (result["status"], result["dispatched"]) == ("interrupted", 3)
    assert error in result["error"]
    assert not (run / "artifacts").exists()
    assert "verification_artifact_sha256" not in result


def test_executable_acceptance_requires_explicit_trusted_checker(workspace):
    assert "executable checks require a trusted --verify-worker" in command(*start_typed(workspace), expect=1)
    assert not (workspace / "run").exists()


def test_source_only_check_can_explicitly_require_intake(workspace):
    check = {"kind": "source-inspection", "behavior": "Find the intake caveat", "required_sources": ["intake"]}
    result = command(*start_typed(workspace, "evidence-intake-only", checks={"caveat": check}))
    assert result["status"] == "complete"
    assert result["verification"][0]["references"][0]["source"] == "intake"


def test_repair_keeps_earlier_verdicts_bound_to_the_first_snapshot(workspace):
    run = workspace / "run"
    result = command(
        *start_typed(workspace, "evidence-repair", budget=5), "--verify-worker", str(workspace / "fixture-worker")
    )
    first = json.loads((run / "attempts" / "3" / "job.json").read_text())
    repair = json.loads((run / "attempts" / "4" / "job.json").read_text())
    last = json.loads((run / "attempts" / "5" / "job.json").read_text())
    assert repair["verification"][0]["status"] == "fail"
    assert repair["verification_artifact_sha256"] == first["artifact_sha256"]
    assert first["verification_id"] != last["verification_id"]
    assert first["artifact_sha256"] != last["artifact_sha256"]
    assert result["verification_artifact_sha256"] == last["artifact_sha256"] == result["artifact_sha256"]


@pytest.mark.parametrize(
    ("checks", "error"),
    [
        ({"typed": TYPED_CHECKS["caveat"], "legacy": "A prose check"}, "either legacy strings or objects"),
        ({"bad": {"kind": "objective", "behavior": "Check the result"}}, "invalid acceptance check kind"),
        ({"bad": {"kind": "judgment", "behavior": " "}}, "check behavior must be a nonempty string"),
    ],
)
def test_new_requests_validate_the_check_contract(workspace, checks, error):
    assert error in command(*start_typed(workspace, checks=checks), expect=1)
    assert not (workspace / "run").exists()


def test_verification_refuses_changed_build_from_a_saved_run(workspace):
    run = workspace / "run"
    result = command(*start_typed(workspace, budget=2), "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert (result["status"], result["phase"]) == ("budget-exhausted", "verify")
    receipt = run / "attempts" / "2" / "receipt.json"
    build = json.loads(receipt.read_text())
    build["artifacts"][0]["content"] = "SELECT 0;\n"
    receipt.write_text(json.dumps(build))
    error = command("resume", str(run), "--budget", "3", expect=1)
    assert "build artifacts changed before verification" in error
    assert not (run / "attempts" / "3").exists()


def test_publication_recovery_refuses_a_changed_verified_snapshot(workspace):
    run = workspace / "run"
    result = command(*start_typed(workspace), "--verify-worker", str(workspace / "fixture-worker"))
    (run / "artifacts").rename(workspace / "previous-publication")
    record = state(run)
    record.update(status="ready", phase="publish")
    record.pop("artifact_sha256")
    (run / "state.json").write_text(json.dumps(record))
    receipt = run / "attempts" / "2" / "receipt.json"
    original = receipt.read_bytes()
    build = json.loads(original)
    build["artifacts"][0]["content"] = "SELECT 0;\n"
    receipt.write_text(json.dumps(build))
    error = command("resume", str(run), expect=1)
    assert "publication artifacts differ from the verified snapshot" in error
    assert not (run / "artifacts").exists()
    receipt.write_bytes(original)
    assert command("resume", str(run)) == result


def test_inapplicable_check_stays_open_until_repaired(workspace):
    run = workspace / "run"
    blocked = command(*prepare(workspace, scenario="repair", budget=3), expect=2)
    assert blocked["status"] == "budget-exhausted"
    assert blocked["verification"][0]["status"] == "inapplicable"
    assert not (run / "artifacts").exists()
    repaired = command("resume", str(run), "--budget", "5")
    assert repaired["status"] == "complete"
    assert repaired["verification"][0]["status"] == "pass"


def test_stakeholder_questions_pause_for_the_owner(workspace):
    run = workspace / "run"
    blocked = command(*prepare(workspace, scenario="stakeholder", budget=4), expect=2)
    assert blocked["status"] == "answer-required"
    assert "Who owns" in blocked["question"]
    assert command("resume", str(run), expect=2)["dispatched"] == 2
    complete = command("resume", str(run), "--answer", "Facilities director")
    assert complete["status"] == "complete"
    assert state(run)["answers"] == [{"answer": "Facilities director", "question": blocked["question"]}]


def test_artifact_paths_cannot_escape_the_run(workspace):
    result = command(*prepare(workspace, scenario="invalid-path"), expect=2)
    assert result["status"] == "interrupted"
    assert "invalid or duplicate artifact path" in result["error"]
    assert Path(result["worker_log"]).is_file()
    assert not (workspace / "run" / "artifacts").exists()
    assert not (workspace / "run" / "attempts" / "escape").exists()


@pytest.mark.parametrize(("independent_verifier", "typed"), [(False, False), (True, False), (False, True)])
def test_codex_adapter_dispatches_and_verifies_snapshot_without_provider_access(
    workspace, monkeypatch, independent_verifier, typed
):
    start = prepare(workspace, checks={"caveat": TYPED_CHECKS["caveat"]} if typed else None)
    shim = workspace / "codex"
    shim.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
assert args[:5] == ["--ask-for-approval", "never", "exec", "--sandbox", "read-only"]
assert args[args.index("--model") + 1] == "fixture-model"
assert args[args.index("-c") + 1] == 'model_reasoning_effort="medium"'
assert args[-1] == "-"
packet = json.loads(sys.stdin.read().rsplit("\n\n", 1)[1])
typed = packet.get("verification_version") == 2
if typed:
    assert packet["request"]["checks"]["caveat"]["kind"] == "source-inspection"
else:
    assert packet["request"]["checks"] == {"caveat": "State that the simulation omitted false releases"}
assert packet["verification_worker"] == ("independent" if os.environ.get("BMAD_TEST_EXTERNAL_VERIFY") else "default")
phase = packet["phase"]
if phase == "route":
    result = {"status": "ok", "deliverable": "Director decision brief", "workflows": ["bmad-product-brief"],
              "rationale": "The owner specified a brief.", "assumptions": []}
elif phase == "build":
    assert packet["route"]["deliverable"] == "Director decision brief"
    result = {"status": "ok", "artifacts": [{"path": "BRIEF.md", "content": "The simulation omitted false releases.\n"}]}
elif phase == "verify":
    assert not os.environ.get("BMAD_TEST_EXTERNAL_VERIFY")
    snapshot = Path("snapshot/BRIEF.md").read_text()
    assert packet["artifacts"] == [{"path": "BRIEF.md", "content": snapshot}]
    observed = snapshot.strip()
    assert observed == "The simulation omitted false releases."
    row = {"id": "caveat", "status": "pass", "evidence": observed}
    result = {"status": "ok", "checks": [row]}
    if typed:
        row.update(kind="source-inspection", references=[
            {"source": "artifact", "path": "BRIEF.md", "line_start": 1, "quote": observed}
        ])
        result.update(
            verification_version=2, verification_id=packet["verification_id"], artifact_sha256=packet["artifact_sha256"]
        )
else:
    raise AssertionError(phase)
Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result))
"""
    )
    shim.chmod(0o700)
    monkeypatch.setenv("PATH", f"{workspace}{os.pathsep}{os.environ['PATH']}")
    args = [*start[:-2], "--codex", "--model", "fixture-model", "--effort", "medium"]
    if independent_verifier:
        monkeypatch.setenv("BMAD_TEST_EXTERNAL_VERIFY", "1")
        args += ["--verify-worker", str(workspace / "fixture-worker")]
    result = command(*args)
    attempts = state(workspace / "run")["attempts"]
    assert all("verifier" not in attempt for attempt in attempts[:2])
    assert ("verifier" in attempts[2]) == independent_verifier
    assert result["status"] == "complete"
    assert result["dispatched"] == 3
    assert result["verification"][0]["evidence"] == "The simulation omitted false releases."
    if typed:
        assert result["verification_artifact_sha256"] == result["artifact_sha256"]


def test_reverify_reuses_build_after_checker_repair(workspace):
    run = workspace / "run"
    args = prepare(workspace, scenario="checker-repair")
    failed = command(*args, "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert failed["status"] == "budget-exhausted"
    assert failed["verification"][0]["status"] == "fail"
    assert "resume --reverify --budget NEW_TOTAL" in failed["next_action"]
    (workspace / "checker-repaired").touch()
    result = command("resume", str(run), "--reverify", "--budget", "4")
    assert result["status"] == "complete"
    assert result["verification"][0]["status"] == "pass"
    record = state(run)
    assert record["build_attempt"] == 2
    assert [attempt["phase"] for attempt in record["attempts"]] == ["route", "build", "verify", "verify"]
    assert json.loads((run / "attempts" / "3" / "receipt.json").read_text())["checks"][0]["status"] == "fail"


@pytest.mark.parametrize(("typed", "budget"), [(False, 4), (True, 4), (True, 3)])
def test_checker_fault_pauses_and_reverifies_the_same_build(workspace, typed, budget):
    run = workspace / "run"
    args = (
        start_typed(workspace, "evidence-checker-fault", budget=budget)
        if typed
        else prepare(workspace, scenario="declared-checker-fault", budget=budget)
    )
    fault = command(*args, "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert (fault["status"], fault["phase"], fault["dispatched"]) == ("checker-fault", "verify", 3)
    assert "configuration is missing" in fault["error"]
    assert "resume --reverify" in fault["next_action"]
    assert command("status", str(run)) == fault
    assert command("resume", str(run), expect=2) == fault
    assert "no interrupted attempt" in command("resume", str(run), "--retry", expect=1)
    assert not (run / "attempts" / "4").exists()

    (workspace / "checker-repaired").touch()
    retry = ["resume", str(run), "--reverify"]
    if budget == 3:
        assert "needs available budget" in command(*retry, expect=1)
        retry += ["--budget", "4"]
    result = command(*retry)
    assert (result["status"], result["dispatched"]) == ("complete", 4)
    assert "error" not in result
    attempts = state(run)["attempts"]
    assert [(attempt["phase"], attempt["status"]) for attempt in attempts] == [
        ("route", "ok"),
        ("build", "ok"),
        ("verify", "checker-fault"),
        ("verify", "ok"),
    ]
    if typed:
        assert attempts[2]["verification_id"] != attempts[3]["verification_id"]
        assert attempts[2]["artifact_sha256"] == result["artifact_sha256"]


def test_default_worker_cannot_declare_a_checker_fault(workspace):
    result = command(*prepare(workspace, scenario="declared-checker-fault", budget=4), expect=2)
    assert (result["status"], result["phase"], result["dispatched"]) == ("interrupted", "verify", 3)
    assert "reserved for an independent verifier" in result["error"]


def test_checker_fault_reports_current_failure_after_a_rebuild(workspace):
    run = workspace / "run"
    args = prepare(workspace, scenario="repair-then-checker-fault", budget=6)
    fault = command(*args, "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert (fault["status"], fault["dispatched"]) == ("checker-fault", 5)
    assert "verification" not in fault
    assert state(run)["verification"][0]["evidence"] == "The first build needs a repair."
    result = command("resume", str(run), "--reverify")
    assert result["status"] == "complete"
    assert [attempt["phase"] for attempt in state(run)["attempts"]] == [
        "route",
        "build",
        "verify",
        "build",
        "verify",
        "verify",
    ]


def launch_native(action, job, *args):
    return subprocess.Popen(
        [sys.executable, "-B", str(NATIVE_HOST), action, str(job), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def native_host(action, job, *args, expected=0):
    with launch_native(action, job, *args) as process:
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == expected, stderr
        return stderr


def stage_booking_job(job):
    native_host("prepare", job, "--bmad-root", str(REPO))
    workspace = job.parent / "workspace"
    (workspace / "plan.md").write_text("---\nstatus: built\n---\n## Auto Run Result\n")
    (workspace / "booking.py").write_text(
        "def conflict(first, second):\n    return first[0] < second[1] and second[0] < first[1]\n"
    )
    return ("submit", job, "--terminal", "plan.md", "--artifact", "booking.py=booking.py")


def test_status_guides_controller_managed_native_workers(workspace, monkeypatch):
    run = workspace / "run"
    args = prepare(workspace, kind="code")
    monkeypatch.setenv("BMAD_TEST_HOLD", "build:before")
    attempt = run / "attempts" / "2"
    with launch(*args, "--native-worker", str(workspace / "fixture-worker")) as controller:
        try:
            wait_for(attempt / "worker-held")
            active = command("status", str(run))
            assert active["pending_attempt"]["workflow"] == "bmad-build-auto"
            assert active["next_action"].startswith("Wait for the worker.")
        finally:
            (attempt / "release").touch()
        stdout, stderr = controller.communicate(timeout=10)
        assert controller.returncode == 2, (stdout, stderr)
    paused = json.loads(stdout)
    assert paused["pending_attempt"]["workflow"] == "bmad-build-auto"
    assert paused["next_action"].startswith("Run resume to adopt a saved receipt.")


@pytest.mark.parametrize(("timed_out", "resume_flags"), [(False, []), (True, []), (True, ["--retry"])])
def test_native_receipt_before_and_after_timeout_is_adopted_once(workspace, timed_out, resume_flags):
    run = workspace / "run"
    job = run / "attempts" / "2" / "job.json"
    args = prepare(workspace, kind="code", timeout=2 if timed_out else 15)
    with launch(*args, "--native-host") as controller:
        wait_for(job)
        if timed_out:
            stdout, stderr = controller.communicate(timeout=10)
            assert controller.returncode == 2, (stdout, stderr)
            paused = json.loads(stdout)
            assert (paused["status"], paused["pending_attempt"]["status"]) == ("interrupted", "no-receipt")
            assert paused["pending_attempt"]["workflow"] == "bmad-build-auto"
            assert command("status", str(run)) == paused
            if not resume_flags:
                legacy = state(run)
                del legacy["attempt_version"]
                (run / "state.json").write_text(json.dumps(legacy))
        submission = stage_booking_job(job)
        if not timed_out:
            assert controller.poll() is None
            active = command("status", str(run))
            assert (active["status"], active["pending_attempt"]["workflow"]) == ("dispatched", "bmad-build-auto")
            assert active["pending_attempt"]["job"] == str(job)
            assert "Serve the pending workflow" in active["next_action"]
        native_host(*submission)
        if not timed_out:
            stdout, stderr = controller.communicate(timeout=10)
            assert controller.returncode == 0, (stdout, stderr)
            result = json.loads(stdout)
    if timed_out:
        result = command("resume", str(run), *resume_flags)
    assert (result["status"], result["dispatched"]) == ("complete", 3)
    assert "error" not in result
    assert state(run)["attempt_version"] == 1
    assert [attempt["phase"] for attempt in state(run)["attempts"]] == ["route", "build", "verify"]
    assert [item["attempt"] for item in result["native_runs"]] == [2]
    assert "closed for receipts" in native_host(*submission, expected=1)


@pytest.mark.parametrize("concurrent", [False, True])
def test_native_retry_and_late_submissions_accept_only_one_build(workspace, concurrent):
    run = workspace / "run"
    old_job = run / "attempts" / "2" / "job.json"
    start = command(*prepare(workspace, kind="code", budget=4, timeout=2), "--native-host", expect=2)
    assert (start["status"], start["pending_attempt"]["number"]) == ("interrupted", 2)
    submission = stage_booking_job(old_job)

    if concurrent:
        lock = (old_job.parent / ".receipt.lock").open("a")
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            retry = launch("resume", str(run), "--retry")
            host = launch_native(*submission)
            assert command("status", str(run)) == start
        with retry, host:
            retry_stdout, retry_stderr = retry.communicate(timeout=10)
            _, host_stderr = host.communicate(timeout=10)
            if host.returncode == 0:
                assert retry.returncode == 0, (retry_stdout, retry_stderr)
                result = json.loads(retry_stdout)
            else:
                assert host.returncode == 1 and "closed for receipts" in host_stderr
                assert retry.returncode == 2, (retry_stdout, retry_stderr)
                result = json.loads(retry_stdout)
    else:
        result = command("resume", str(run), "--retry", expect=2)
        assert "closed for receipts" in native_host(*submission, expected=1)
        assert "closed for preparation" in native_host("prepare", old_job, "--bmad-root", str(REPO), expected=1)

    if result["status"] == "complete":
        assert (result["dispatched"], [item["attempt"] for item in result["native_runs"]]) == (3, [2])
    else:
        assert (result["status"], result["pending_attempt"]["number"]) == ("interrupted", 3)
        assert state(run)["attempts"][1]["status"] == "superseded"
        assert not old_job.with_name("receipt.json").exists()
        new_job = run / "attempts" / "3" / "job.json"
        native_host(*stage_booking_job(new_job))
        result = command("resume", str(run))
        assert (result["status"], result["dispatched"]) == ("complete", 4)
        assert [item["attempt"] for item in result["native_runs"]] == [3]
    accepted = [
        attempt for attempt in state(run)["attempts"] if attempt["phase"] == "build" and attempt["status"] == "ok"
    ]
    assert len(accepted) == 1


def test_retry_without_budget_leaves_the_late_receipt_eligible(workspace):
    run = workspace / "run"
    job = run / "attempts" / "2" / "job.json"
    command(*prepare(workspace, kind="code", budget=2, timeout=2), "--native-host", expect=2)
    capped = command("resume", str(run), "--retry", expect=2)
    assert (capped["status"], capped["pending_attempt"]["status"]) == ("budget-exhausted", "no-receipt")
    assert "resume --budget NEW_TOTAL" in capped["next_action"]
    assert not (run / "attempts" / "3").exists()

    native_host(*stage_booking_job(job))
    result = command("resume", str(run), "--budget", "3")
    assert (result["status"], result["dispatched"]) == ("complete", 3)
    assert [attempt["phase"] for attempt in state(run)["attempts"]] == ["route", "build", "verify"]


def test_retry_rechecks_a_receipt_committed_after_its_initial_lookup(workspace):
    run = workspace / "run"
    job = run / "attempts" / "2" / "job.json"
    command(*prepare(workspace, kind="code", budget=4, timeout=2), "--native-host", expect=2)
    submission = stage_booking_job(job)
    barrier = """
import sys
import time
from deliver import Delivery, main

retry = Delivery.retry

def pause_after_initial_recovery(self):
    ready = self.run.parent / "retry-ready"
    ready.touch()
    deadline = time.monotonic() + 10
    while not ready.with_name("retry-release").exists():
        assert time.monotonic() < deadline
        time.sleep(0.02)
    return retry(self)

Delivery.retry = pause_after_initial_recovery
sys.exit(main())
"""
    with subprocess.Popen(
        [sys.executable, "-B", "-c", barrier, "resume", str(run), "--retry"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as controller:
        try:
            wait_for(workspace / "retry-ready")
            native_host(*submission)
        finally:
            (workspace / "retry-release").touch()
        stdout, stderr = controller.communicate(timeout=10)
        assert controller.returncode == 0, (stdout, stderr)
    result = json.loads(stdout)
    assert (result["dispatched"], [item["attempt"] for item in result["native_runs"]]) == (3, [2])


def test_explicit_retry_can_replace_an_invalid_late_receipt(workspace):
    run = workspace / "run"
    old_job = run / "attempts" / "2" / "job.json"
    command(*prepare(workspace, kind="code", budget=4, timeout=2), "--native-host", expect=2)
    old_job.with_name("receipt.json").write_text("{truncated")
    retried = command("resume", str(run), "--retry", expect=2)
    assert (retried["status"], retried["pending_attempt"]["number"]) == ("interrupted", 3)
    assert state(run)["attempts"][1]["status"] == "invalid-receipt"
    native_host(*stage_booking_job(run / "attempts" / "3" / "job.json"))
    result = command("resume", str(run))
    assert (result["status"], [item["attempt"] for item in result["native_runs"]]) == ("complete", [3])


@pytest.mark.parametrize("typed", [False, True])
def test_native_mixed_replays_code_receipt_without_duplicate_work(workspace, typed):
    run = workspace / "run"
    if typed:
        prepared = prepare(
            workspace, kind="mixed", mode="A", budget=4, scenario=f"evidence\n{BRIEF_LIMITATION}", checks=TYPED_CHECKS
        )
        prepared += ["--verify-worker", str(workspace / "fixture-worker")]
    else:
        prepared = prepare(workspace, kind="mixed", mode="A", budget=4)
    route = command(*prepared, "--native-host", expect=2)
    assert route["status"] == "approval-required"
    assert route["native_runs"] == []
    assert not (run / "attempts" / "2").exists()

    code_job = run / "attempts" / "2" / "job.json"
    with launch("resume", str(run), "--approve", route["proposal"]["id"]) as controller:
        wait_for(code_job)
        deadline = time.monotonic() + 5
        while state(run)["status"] != "dispatched":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        controller.kill()
        controller.wait(timeout=5)
    native_host("prepare", code_job, "--bmad-root", str(REPO))
    code_workspace = code_job.parent / "workspace"
    (code_workspace / "plan.md").write_text("---\nstatus: blocked\n---\n## Auto Run Result\n")
    sql_path = "availability.sql" if typed else "query.sql"
    sql_content = AVAILABILITY_SQL.replace("\n", "\r\n") if typed else "select 1;"
    (code_workspace / "query.sql").write_bytes(sql_content.encode())
    args = ("submit", code_job, "--terminal", "plan.md", "--artifact", f"{sql_path}=query.sql")
    native_host(*args, expected=1)
    assert not code_job.with_name("receipt.json").exists()
    (code_workspace / "plan.md").write_text("---\nstatus: built\n---\n## Auto Run Result\n")
    native_host(*args)
    native_host(*args, expected=1)

    brief_job = run / "attempts" / "3" / "job.json"
    deadline = time.monotonic() + 5
    while True:
        resumed = launch("resume", str(run))
        try:
            resumed.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            break
        stdout, stderr = resumed.communicate(timeout=5)
        assert resumed.returncode == 1 and "in progress" in stderr, (stdout, stderr)
        assert time.monotonic() < deadline
        time.sleep(0.03)
    with resumed:
        try:
            wait_for(brief_job)
            packet = json.loads(brief_job.read_text())
            assert packet["native_workflow"] == "bmad-product-brief"
            assert packet["request"]["checks"] == state(run)["request"]["checks"]
            assert packet["artifacts"] == [{"path": sql_path, "content": sql_content}]
            native_host("prepare", brief_job, "--bmad-root", str(REPO))
            document = brief_job.parent / "workspace"
            brief_content = (
                f"Decision: trial manual recovery.\n{BRIEF_LIMITATION}\n"
                if typed
                else "The simulation omitted false releases."
            )
            (document / "brief.md").write_text(brief_content)
            (document / ".memlog.md").write_text("# Memory")
            (document / "native.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "intent": "create",
                        "brief": "brief.md",
                        "memlog": ".memlog.md",
                    }
                )
            )
            native_host("submit", brief_job, "--terminal", "native.json", "--artifact", "brief.md=brief.md")
            stdout, stderr = resumed.communicate(timeout=10)
            assert resumed.returncode == 0, (stdout, stderr)
        finally:
            if resumed.poll() is None:
                resumed.kill()
    final = json.loads(stdout)
    assert final["status"] == "complete"
    assert final["dispatched"] == 4
    assert [item["workflow"] for item in final["native_runs"]] == ["bmad-build-auto", "bmad-product-brief"]
    assert {item.name for item in (run / "artifacts").iterdir()} == {"brief.md", sql_path}
    if typed:
        assert final["verification_artifact_sha256"] == final["artifact_sha256"]
        assert final["native_runs"][0]["artifact_sources"] == {sql_path: "workspace/query.sql"}
        assert final["native_runs"][0]["evidence"]["workspace/query.sql"] == final["artifact_sha256"][sql_path]
        assert (run / "artifacts" / sql_path).read_bytes() == sql_content.encode()
