#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Run a bounded BMAD delivery with durable worker receipts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_JSON_BYTES = 4 * 1024 * 1024
BUILD_AUTO = "bmad-build-auto"
PRODUCT_BRIEF = "bmad-product-brief"
NATIVE_ROUTES = {"code": [BUILD_AUTO], "non-code": [PRODUCT_BRIEF], "mixed": [BUILD_AUTO, PRODUCT_BRIEF]}
NATIVE_COMPLETION = {BUILD_AUTO: {"built", "done"}, PRODUCT_BRIEF: {"complete"}}
FIELDS = {
    "route": {"deliverable", "workflows", "rationale", "assumptions"},
    "build": {"artifacts"},
    "verify": {"checks"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def text_list(value):
    return isinstance(value, list) and all(map(text, value))


def positive_int(value):
    return type(value) is int and value > 0


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_json(path, limit=MAX_JSON_BYTES):
    with path.open("rb") as source:
        data = source.read(limit + 1)
    require(len(data) <= limit, f"{path.name} exceeds {limit} bytes")
    return json.loads(data)


def write_json(path, value, *, replace=True):
    data = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_boundaries(authority, kind):
    if "boundaries" not in authority:
        return {}
    boundaries = authority["boundaries"]
    require(
        isinstance(boundaries, dict)
        and boundaries
        and boundaries.keys() <= {"allowed_output_classes", "allowed_deliverables"},
        "authority.boundaries must specify allowed_output_classes or allowed_deliverables",
    )
    for field, values in boundaries.items():
        require(text_list(values) and values, f"authority.boundaries.{field} must be a nonempty list of strings")
    if "allowed_output_classes" in boundaries:
        classes = boundaries["allowed_output_classes"]
        require(all(value in NATIVE_ROUTES for value in classes), "invalid allowed output class")
        require(kind in classes, "request kind is outside the allowed output classes")
    return boundaries


def validate_request(request):
    require(isinstance(request, dict), "request must be an object")
    authority = request.get("authority")
    intake = request.get("intake")
    checks = request.get("checks")
    require(isinstance(authority, dict), "authority must be an object")
    require(authority.get("mode") in ("A", "B", "C"), "mode must be A, B, or C")
    require(text(authority.get("outcome")), "authority.outcome is required")
    limits = authority.get("limits", [])
    require(text_list(limits), "authority.limits must be a list of constraints")
    kind = request.get("kind")
    require(kind in ("code", "non-code", "mixed"), "kind must be code, non-code, or mixed")
    if authority["mode"] == "B":
        boundaries = validate_boundaries(authority, kind)
        require(limits or boundaries, "mode B requires explicit delegation limits")
        name = authority.get("deliverable")
        require(name is None or text(name), "authority.deliverable must name a deliverable")
    if authority["mode"] == "C":
        require(text(authority.get("deliverable")), "mode C requires a named deliverable")
    require(isinstance(intake, dict), "intake must be an object")
    require(intake.get("kind") in ("idea", "literature", "brainstorm", "forge"), "invalid intake kind")
    require(text(intake.get("text")), "intake.text is required")
    require(isinstance(checks, dict) and checks, "at least one acceptance check is required")
    require(all(text(key) and text(value) for key, value in checks.items()), "checks must map IDs to behaviors")
    require(positive_int(request.get("budget")), "budget must be a positive number of worker calls")
    timeout = request.get("timeout_seconds", 600)
    require(positive_int(timeout), "timeout_seconds must be positive")
    return request


def validate_route(result):
    require(text(result.get("deliverable")), "route must name its deliverable")
    require(text_list(result.get("workflows")) and result["workflows"], "route must name its BMad workflows")
    require(text(result.get("rationale")), "route must explain its choice")
    require(text_list(result.get("assumptions")), "route must list reversible assumptions")
    return {key: result[key] for key in sorted(FIELDS["route"])}


def validate_artifacts(artifacts):
    require(isinstance(artifacts, list) and artifacts, "build must return artifacts")
    paths = set()
    for artifact in artifacts:
        require(isinstance(artifact, dict), "each artifact must be an object")
        name = artifact.get("path")
        content = artifact.get("content")
        require(isinstance(name, str) and len(name) <= 240, "invalid artifact path")
        parts = tuple(name.split("/"))
        valid_path = all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) for part in parts)
        require(valid_path and parts not in paths, f"invalid or duplicate artifact path: {name}")
        require(isinstance(content, str), f"{name} must have text content")
        content.encode()
        paths.add(parts)
    for parts in paths:
        require(not any(parts[:n] in paths for n in range(1, len(parts))), "artifact file/directory conflict")


def validate_receipt(result, phase, checks):
    require(isinstance(result, dict), "worker receipt must be an object")
    status = result.get("status")
    if status == "blocked":
        require(text(result.get("question")), "blocked receipt must contain a question for the owner")
    elif status == "replace" and phase == "build":
        validate_route(result)
    elif status == "failed" and phase == "build":
        require(text(result.get("error")), "failed native worker must provide its blocking condition")
    elif status == "ok":
        if phase == "route":
            validate_route(result)
        elif phase == "build":
            validate_artifacts(result.get("artifacts"))
        else:
            rows = result.get("checks")
            require(isinstance(rows, list) and len(rows) == len(checks), "verify must report every acceptance check")
            ids = set()
            for row in rows:
                require(isinstance(row, dict) and isinstance(row.get("id"), str), "invalid check result")
                require(row.get("status") in ("pass", "fail", "inapplicable"), "invalid verification status")
                require(text(row.get("evidence")), "each verification result needs evidence")
                ids.add(row["id"])
            require(ids == set(checks), "verification IDs must exactly match the original acceptance check IDs")
    else:
        raise ValueError(f"invalid worker status for {phase}")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_native_result(result, workflow, attempt_dir):
    native = result.get("native")
    require(isinstance(native, dict) and native.get("workflow") == workflow, "native workflow receipt required")
    status = native.get("status")
    require(isinstance(status, str) and status in NATIVE_COMPLETION[workflow], "native workflow did not complete")
    evidence = native.get("evidence")
    require(isinstance(evidence, dict) and evidence, "native workflow must leave file evidence")
    for name, sha256 in evidence.items():
        path = attempt_dir / name
        require(
            not Path(name).is_absolute()
            and path.is_relative_to(attempt_dir)
            and path.resolve() == path
            and path.is_file(),
            "native evidence must be a regular file within its attempt",
        )
        require(text(sha256) and re.fullmatch(r"[a-f0-9]{64}", sha256), "invalid native evidence SHA-256")
        with path.open("rb") as handle:
            require(
                hashlib.file_digest(handle, "sha256").hexdigest() == sha256, f"native evidence hash mismatch: {name}"
            )
    return native


def publish(run, artifacts):
    """Publish the verified tree once, including recovery after rename."""
    output = run / "artifacts"
    hashes = {item["path"]: digest(item["content"].encode()) for item in artifacts}
    if not output.exists():
        stage = Path(tempfile.mkdtemp(dir=run, prefix=".artifacts-"))
        try:
            for item in artifacts:
                path = stage / item["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as handle:
                    handle.write(item["content"].encode())
                    handle.flush()
                    os.fsync(handle.fileno())
            directories = [p for p in stage.rglob("*") if p.is_dir()]
            for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
                sync_directory(directory)
            sync_directory(stage)
            stage.rename(output)
            sync_directory(run)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    require(output.is_dir() and not output.is_symlink(), "artifact output is not a run directory")
    files = list(output.rglob("*"))
    require(
        all(not path.is_symlink() and (path.is_file() or path.is_dir()) for path in files),
        "artifact output contains an unexpected path",
    )
    actual = {p.relative_to(output).as_posix(): digest(p.read_bytes()) for p in files if p.is_file()}
    expected_dirs = {str(parent) for name in hashes for parent in Path(name).parents if parent != Path(".")}
    dirs = {p.relative_to(output).as_posix() for p in files if p.is_dir()}
    require(actual == hashes and dirs == expected_dirs, "artifact output differs from the verified build")
    return hashes


class Delivery:
    def __init__(self, run, state, lock_fd):
        self.run = run
        self.state = state
        self.lock_fd = lock_fd

    @property
    def request(self):
        return self.state["request"]

    def save(self):
        write_json(self.run / "state.json", self.state)

    def receipt(self, attempt):
        return self.run / "attempts" / str(attempt) / "receipt.json"

    def build_outputs(self, attempts):
        return [artifact for num in attempts for artifact in read_json(self.receipt(num))["artifacts"]]

    def artifacts(self):
        if self.state.get("native_worker"):
            attempts = self.state["native_partial"] or self.state["native_build_attempts"]
            return self.build_outputs(attempts)
        attempt = self.state.get("build_attempt")
        return self.build_outputs([attempt]) if attempt else []

    def job(self, num):
        phase = self.state["phase"]
        job = {
            "attempt": num,
            "phase": phase,
            "request": self.request,
            "route": self.state.get("route"),
            "answers": self.state["answers"],
            "verification": self.state.get("verification", []),
            "verification_worker": "independent" if self.state.get("verifier") else "default",
            "artifacts": self.artifacts(),
            "budget_remaining_after_dispatch": self.state["budget"] - num,
            "timeout_seconds": self.request.get("timeout_seconds", 600),
        }
        if self.state.get("native_worker"):
            workflows = NATIVE_ROUTES[self.request["kind"]]
            job["native_workflows"] = workflows
            if phase == "build":
                job["native_workflow"] = workflows[len(self.state["native_partial"])]
        return job

    def dispatch(self):
        num = len(self.state["attempts"]) + 1
        path = self.receipt(num).parent
        job = self.job(num)
        if path.exists():
            require(not self.receipt(num).exists(), "untracked worker receipt needs inspection")
        else:
            path.mkdir()
            sync_directory(path.parent)
        write_json(path / "job.json", job)
        verifier = self.state.get("verifier") if job["phase"] == "verify" else None
        workflow = job.get("native_workflow")
        worker = self.state["native_worker"] if workflow else verifier or self.state["worker"]
        attempt = {"number": num, "phase": job["phase"], "status": "dispatched"}
        if workflow:
            attempt["workflow"] = workflow
        if verifier:
            attempt["verifier"] = verifier[0]
        self.state["attempts"].append(attempt)
        self.state["status"] = "dispatched"
        self.save()
        with (path / "worker.log").open("ab") as log:
            try:
                with subprocess.Popen(
                    [*worker, str(path / "job.json"), str(self.receipt(num))],
                    cwd=path,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                    pass_fds=(self.lock_fd,),
                ) as proc:
                    try:
                        proc.wait(timeout=job["timeout_seconds"])
                    except (subprocess.TimeoutExpired, KeyboardInterrupt):
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
            except OSError as exc:
                log.write(f"{exc}\n".encode())

    def propose(self, route, attempt, *, reason=None):
        proposal = {"id": str(attempt), "route": route}
        if reason:
            proposal["reason"] = reason
        self.state["proposals"].append(proposal)
        self.state["status"] = "approval-required"

    def select(self, route):
        self.state.update(phase="build", status="ready", route=route, verification=[])
        self.state.pop("build_attempt", None)
        if self.state.get("native_worker"):
            self.state.update(native_partial=[], native_build_attempts=[])

    def check_route(self, result):
        route = validate_route(result)
        if self.state.get("native_worker"):
            require(
                route["workflows"] == NATIVE_ROUTES[self.request["kind"]],
                "route must preserve the configured native workflow order",
            )
        authority = self.request["authority"]
        if authority["mode"] != "B":
            return route, None

        request_kind = self.request["kind"]
        boundaries = validate_boundaries(authority, request_kind)
        kind = result.get("kind", request_kind)
        require(kind in ("code", "non-code", "mixed"), "invalid route output class")
        classes = boundaries.get("allowed_output_classes")
        require(classes is None or kind in classes, "route output class is outside the allowed output classes")
        require(kind == request_kind, "route must preserve the request output class")
        if classes is not None:
            incompatible = NATIVE_COMPLETION.keys() - NATIVE_ROUTES[kind]
            require(
                incompatible.isdisjoint(route["workflows"]), "route workflows conflict with the request output class"
            )
        if "kind" in result:
            route["kind"] = kind
        names = boundaries.get("allowed_deliverables")
        if names is not None:
            require(route["deliverable"] in names, "route deliverable is outside the allowed deliverables")
        elif authority.get("limits") and route["deliverable"] != authority.get("deliverable"):
            return route, "The proposed name needs owner approval under the Mode B delegation limits."
        return route, None

    def adopt_native(self, result, attempt):
        number, workflow = attempt["number"], attempt["workflow"]
        native = validate_native_result(result, workflow, self.receipt(number).parent)
        partial = [*self.state["native_partial"], number]
        validate_artifacts(self.build_outputs(partial))
        attempt["native"] = native
        self.state.update(native_partial=partial, status="ready")
        if len(partial) == len(NATIVE_ROUTES[self.request["kind"]]):
            self.state.update(native_build_attempts=partial, phase="verify")

    def apply(self, result, attempt):
        status, phase = result["status"], attempt["phase"]
        number = attempt["number"]
        mode = self.request["authority"]["mode"]
        if status == "blocked":
            self.state.update(status="answer-required", question=result["question"])
        elif status == "failed":
            require("workflow" in attempt, "failed receipt is reserved for native workers")
            self.state.update(status="interrupted", error=result["error"])
        elif status == "replace" or phase == "route":
            route, reason = self.check_route(result)
            replacing = status == "replace"
            if replacing:
                require(
                    route["deliverable"] != self.state["route"]["deliverable"],
                    "replacement must change the deliverable",
                )
            if (
                reason
                or mode == "A"
                or (mode == "C" and (replacing or route["deliverable"] != self.request["authority"]["deliverable"]))
            ):
                self.propose(route, number, reason=reason)
            else:
                if replacing:
                    self.state["replacements"].append({"attempt": number, "route": route})
                self.select(route)
        elif phase == "build":
            if attempt.get("workflow"):
                self.adopt_native(result, attempt)
            else:
                self.state.update(phase="verify", status="ready", build_attempt=number)
        else:
            rows = result["checks"]
            self.state["verification"] = rows
            if all(row["status"] == "pass" for row in rows):
                self.state.update(phase="publish", status="ready")
            else:
                self.state.update(phase="build", status="ready")
                if self.state.get("native_worker"):
                    self.state["native_partial"] = []

    def recover(self):
        attempt = self.state["attempts"][-1]
        receipt = self.receipt(attempt["number"])
        if not receipt.exists():
            attempt["status"] = "no-receipt"
            self.state.update(status="interrupted", error=f"No durable receipt for attempt {attempt['number']}")
        else:
            try:
                result = read_json(receipt)
                validate_receipt(result, attempt["phase"], self.request["checks"])
                self.apply(result, attempt)
                attempt["status"] = result["status"]
            except (OSError, ValueError, KeyError) as exc:
                attempt["status"] = "invalid-receipt"
                self.state.update(status="interrupted", error=f"Invalid worker receipt: {exc}")
        self.save()

    def advance(self):
        if self.state["status"] == "dispatched":
            self.recover()
        while self.state["status"] == "ready":
            if self.state["phase"] == "publish":
                self.state.update(status="complete", artifact_sha256=publish(self.run, self.artifacts()))
                self.save()
                return
            if len(self.state["attempts"]) == self.state["budget"]:
                self.state["status"] = "budget-exhausted"
                self.save()
                return
            self.dispatch()
            self.recover()

    def resume(self, args):
        status = self.state["status"]
        if self.state["status"] == "dispatched":
            self.recover()
            status = self.state["status"]
        if args.approve is not None:
            require(status == "approval-required", "no proposal is waiting for approval")
            proposal = self.state["proposals"][-1]
            require(args.approve == proposal["id"], f"approval must name proposal {proposal['id']}")
        if args.answer is not None:
            require(status == "answer-required" and text(args.answer), "no owner question or empty answer")
        if args.retry:
            require(status == "interrupted", "no interrupted attempt to retry")
        if args.reverify:
            last_attempt = next(iter(self.state["attempts"][-1:]), {})
            require(
                status == "budget-exhausted"
                and self.state["phase"] == "build"
                and last_attempt.get("phase") == "verify"
                and last_attempt.get("verifier"),
                "no failed independent verification awaiting repair",
            )
            require(args.budget is not None, "--reverify requires a new total budget")
        if args.budget is not None:
            require(
                args.budget > self.state["budget"] and status != "complete",
                "new budget must increase an open run's budget",
            )
            self.state.setdefault("budget_extensions", []).append(
                {"after_dispatch": len(self.state["attempts"]), "total": args.budget}
            )
            self.state["budget"] = args.budget
            if status == "budget-exhausted":
                self.state["status"] = "ready"
        if args.approve is not None:
            self.state["approvals"].append(proposal["id"])
            if self.request["authority"]["mode"] == "B" and self.state["phase"] == "build":
                self.state["replacements"].append(
                    {"attempt": int(proposal["id"]), "route": proposal["route"], "approval": proposal["id"]}
                )
            self.select(proposal["route"])
        if args.answer is not None:
            self.state["answers"].append({"question": self.state.pop("question"), "answer": args.answer})
            self.state["status"] = "ready"
        if args.retry:
            self.state.pop("error", None)
            self.state["status"] = "ready"
        if args.reverify:
            self.state["phase"] = "verify"
        self.save()
        self.advance()

    def summary(self):
        state = self.state
        keys = ("status", "phase", "route", "question", "verification", "artifact_sha256", "error")
        summary = {key: state[key] for key in keys if key in state}
        summary.update(run=str(self.run), dispatched=len(state["attempts"]), budget=state["budget"])
        if state.get("native_worker"):
            summary["native_runs"] = [
                {"attempt": item["number"], **item["native"]} for item in state["attempts"] if "native" in item
            ]
        if state["status"] == "interrupted":
            summary["worker_log"] = str(self.receipt(len(state["attempts"])).with_name("worker.log"))
        if state["status"] == "approval-required":
            summary["proposal"] = state["proposals"][-1]
        return summary


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start")
    start.add_argument("run", type=Path)
    start.add_argument("--request", type=Path, required=True)
    workers = start.add_mutually_exclusive_group()
    workers.add_argument("--worker", type=Path, help="trusted local executable taking job and receipt paths")
    workers.add_argument("--codex", action="store_true", help="use the configured Codex CLI provider")
    native = start.add_mutually_exclusive_group()
    native.add_argument("--native-worker", type=Path, help="trusted executable that invokes the native BMAD workflows")
    native.add_argument(
        "--native-host", action="store_true", help="dispatch native workflow jobs to the workspace agent"
    )
    start.add_argument("--verify-worker", type=Path, help="trusted local executable for the verification phase")
    start.add_argument("--model")
    start.add_argument("--effort", choices=("low", "medium", "high", "xhigh"))
    resume = subcommands.add_parser("resume")
    resume.add_argument("run", type=Path)
    actions = resume.add_mutually_exclusive_group()
    actions.add_argument("--approve", metavar="PROPOSAL_ID")
    actions.add_argument("--answer")
    actions.add_argument("--retry", action="store_true")
    actions.add_argument(
        "--reverify", action="store_true", help="rerun a repaired independent checker on the same build"
    )
    resume.add_argument("--budget", type=int, metavar="NEW_TOTAL")
    subcommands.add_parser("status").add_argument("run", type=Path)
    return parser.parse_args()


def trusted_executable(path, flag):
    path = path.resolve(strict=True)
    require(path.is_file() and os.access(path, os.X_OK), f"{flag} must be an executable file")
    return [str(path)]


def initial_state(args):
    request = validate_request(read_json(args.request, limit=512 * 1024))
    if args.worker:
        require(args.model is None and args.effort is None, "--model and --effort require --codex")
        worker = trusted_executable(args.worker, "--worker")
    else:
        require(args.codex, "select --codex or provide a trusted --worker")
        codex = shutil.which("codex")
        require(codex, "codex is unavailable on PATH")
        adapter = Path(__file__).with_name("codex_worker.py").resolve()
        worker = [sys.executable, str(adapter), str(Path(codex).resolve()), args.model or "", args.effort or ""]
    native_worker = None
    if args.native_host:
        host = Path(__file__).with_name("native_host.py").resolve()
        native_worker = [sys.executable, str(host), "wait"]
    elif args.native_worker:
        native_worker = trusted_executable(args.native_worker, "--native-worker")
    return {
        "version": 1,
        "request": request,
        "worker": worker,
        "native_worker": native_worker,
        "native_partial": [],
        "native_build_attempts": [],
        "verifier": trusted_executable(args.verify_worker, "--verify-worker") if args.verify_worker else None,
        "budget": request["budget"],
        "budget_extensions": [],
        "phase": "route",
        "status": "ready",
        "attempts": [],
        "answers": [],
        "proposals": [],
        "approvals": [],
        "replacements": [],
    }


def main():
    args = parse_args()
    run = args.run.resolve()
    try:
        if args.command == "start":
            state = initial_state(args)
            run.mkdir(mode=0o700)
            sync_directory(run.parent)
            (run / "attempts").mkdir()
            sync_directory(run)
        else:
            require((run / "state.json").is_file(), "run state not found")
        with (run / ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command != "start":
                state = read_json(run / "state.json", limit=32 * 1024 * 1024)
                require(state.get("version") == 1, "unsupported run state version")
            delivery = Delivery(run, state, lock.fileno())
            if args.command == "start":
                delivery.save()
                delivery.advance()
            elif args.command == "resume":
                delivery.resume(args)
            print(json.dumps(delivery.summary(), ensure_ascii=False, indent=2))
            return 0 if args.command == "status" or state["status"] == "complete" else 2
    except BlockingIOError:
        print("This run has a controller or worker in progress.", file=sys.stderr)
    except (OSError, ValueError, KeyError) as exc:
        print(f"BMAD delivery: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
