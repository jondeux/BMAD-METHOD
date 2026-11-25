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


def write_json(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


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
    require(authority["mode"] != "B" or limits, "mode B requires explicit delegation limits")
    if authority["mode"] == "C":
        require(text(authority.get("deliverable")), "mode C requires a named deliverable")
    require(request.get("kind") in ("code", "non-code", "mixed"), "kind must be code, non-code, or mixed")
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

    def artifacts(self):
        attempt = self.state.get("build_attempt")
        return read_json(self.receipt(attempt))["artifacts"] if attempt else []

    def job(self, num):
        return {
            "attempt": num,
            "phase": self.state["phase"],
            "request": self.request,
            "route": self.state.get("route"),
            "answers": self.state["answers"],
            "verification": self.state.get("verification", []),
            "verification_worker": "independent" if self.state.get("verifier") else "default",
            "artifacts": self.artifacts(),
            "budget_remaining_after_dispatch": self.state["budget"] - num,
            "timeout_seconds": self.request.get("timeout_seconds", 600),
        }

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
        worker = verifier or self.state["worker"]
        attempt = {"number": num, "phase": job["phase"], "status": "dispatched"}
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

    def propose(self, route, attempt):
        proposal = {"id": str(attempt), "route": route}
        self.state["proposals"].append(proposal)
        self.state["status"] = "approval-required"

    def select(self, route):
        self.state.update(phase="build", status="ready", route=route, verification=[])
        self.state.pop("build_attempt", None)

    def apply(self, result, attempt):
        status, phase = result["status"], attempt["phase"]
        number = attempt["number"]
        mode = self.request["authority"]["mode"]
        if status == "blocked":
            self.state.update(status="answer-required", question=result["question"])
        elif status == "replace":
            route = validate_route(result)
            require(
                route["deliverable"] != self.state["route"]["deliverable"], "replacement must change the deliverable"
            )
            if mode == "B":
                self.state["replacements"].append({"attempt": number, "route": route})
                self.select(route)
            else:
                self.propose(route, number)
        elif phase == "route":
            route = validate_route(result)
            if mode == "A" or (mode == "C" and route["deliverable"] != self.request["authority"]["deliverable"]):
                self.propose(route, number)
            else:
                self.select(route)
        elif phase == "build":
            self.state.update(phase="verify", status="ready", build_attempt=number)
        else:
            rows = result["checks"]
            self.state["verification"] = rows
            if all(row["status"] == "pass" for row in rows):
                self.state.update(phase="publish", status="ready")
            else:
                self.state.update(phase="build", status="ready")

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
    return {
        "version": 1,
        "request": request,
        "worker": worker,
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
