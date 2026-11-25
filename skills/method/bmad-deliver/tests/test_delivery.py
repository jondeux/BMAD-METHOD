import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
RUNNER = SCRIPTS / "deliver.py"
FIXTURE = r"""
from pathlib import Path
import os
import subprocess
import sys
import time

from deliver import read_json, write_json

job_file, receipt_file = map(Path, sys.argv[1:])
job = read_json(job_file)
request = job["request"]
phase = job["phase"]
scenario = request["intake"]["text"]
check_id, = request["checks"]
code = request["kind"] == "code"
name = "Booking prototype" if code else "Director decision brief"
route = {
    "deliverable": name,
    "workflows": ["bmad-build-auto" if code else "bmad-product-brief"],
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


if phase == "route":
    result = {"status": "ok", **route}
elif phase == "build":
    if scenario == "stakeholder" and not job["answers"]:
        result = {"status": "blocked", "question": "Who owns the trial decision?"}
    elif scenario == "replacement" and job["route"]["deliverable"] == name:
        result = {"status": "replace", **route, "deliverable": "One-page decision memo"}
    elif scenario == "invalid-path":
        result = {"status": "ok", "artifacts": [{"path": "../escape", "content": "invalid"}]}
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
elif phase == "verify":
    artifact, = job["artifacts"]
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
    worker.write_text(f"#!{sys.executable}\n" + FIXTURE.lstrip())
    worker.chmod(0o700)
    monkeypatch.setenv("PYTHONPATH", str(SCRIPTS))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.delenv("BMAD_TEST_HOLD", raising=False)
    return tmp_path


def prepare(workspace, *, kind="non-code", mode="C", scenario="baseline", budget=3):
    request = workspace / "request.json"
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
                },
                "checks": {
                    "booking" if kind == "code" else "caveat": (
                        "Reject overlap and allow adjacent intervals"
                        if kind == "code"
                        else "State that the simulation omitted false releases"
                    ),
                },
                "budget": budget,
                "timeout_seconds": 15,
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
    result = command(*prepare(workspace, mode=mode, scenario="replacement", budget=4), expect=0 if mode == "B" else 2)
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


@pytest.mark.parametrize("independent_verifier", [False, True])
def test_codex_adapter_dispatches_and_verifies_snapshot_without_provider_access(
    workspace, monkeypatch, independent_verifier
):
    start = prepare(workspace)
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
    result = {"status": "ok", "checks": [{"id": "caveat", "status": "pass", "evidence": observed}]}
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


def test_reverify_reuses_build_after_checker_repair(workspace):
    run = workspace / "run"
    args = prepare(workspace, scenario="checker-repair")
    failed = command(*args, "--verify-worker", str(workspace / "fixture-worker"), expect=2)
    assert failed["status"] == "budget-exhausted"
    assert failed["verification"][0]["status"] == "fail"
    (workspace / "checker-repaired").touch()
    result = command("resume", str(run), "--reverify", "--budget", "4")
    assert result["status"] == "complete"
    assert result["verification"][0]["status"] == "pass"
    record = state(run)
    assert record["build_attempt"] == 2
    assert [attempt["phase"] for attempt in record["attempts"]] == ["route", "build", "verify", "verify"]
    assert json.loads((run / "attempts" / "3" / "receipt.json").read_text())["checks"][0]["status"] == "fail"
