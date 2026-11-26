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


def prepare(workspace, *, kind="non-code", mode="C", scenario="baseline", budget=3, authority=None):
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
                    **(authority or {}),
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


def native_host(action, job, *args, expected=0):
    result = subprocess.run(
        [sys.executable, "-B", str(NATIVE_HOST), action, str(job), *args],
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == expected, result.stderr


def test_native_mixed_replays_code_receipt_without_duplicate_work(workspace):
    run = workspace / "run"
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
    (code_workspace / "query.sql").write_text("select 1;")
    args = ("submit", code_job, "--terminal", "plan.md", "--artifact", "query.sql=query.sql")
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
            assert packet["artifacts"] == [{"path": "query.sql", "content": "select 1;"}]
            native_host("prepare", brief_job, "--bmad-root", str(REPO))
            document = brief_job.parent / "workspace"
            (document / "brief.md").write_text("The simulation omitted false releases.")
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
    assert {item.name for item in (run / "artifacts").iterdir()} == {"brief.md", "query.sql"}
