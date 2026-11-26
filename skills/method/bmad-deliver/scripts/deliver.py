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
from contextlib import contextmanager
from pathlib import Path
from time import time
from uuid import uuid4

from run_metrics import run_metrics, support_summary
from run_telemetry import DIAGNOSTIC_CODES, GATES, TELEMETRY_FILE, telemetry_summary, verification_counts

MAX_JSON_BYTES = 4 * 1024 * 1024
ATTEMPT_VERSION = 1
VERIFICATION_VERSION = 2
CHECK_KINDS = ("executable", "source-inspection", "judgment")
REFERENCE_SOURCES = ("artifact", "intake")
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


def native_languages(request):
    require(isinstance(request, dict), "native job request must be an object")
    languages = {}
    for field in ("communication_language", "document_output_language"):
        value = request.get(field, "English")
        require(
            text(value) and value.splitlines() == [value] and not re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value),
            f"{field} must be a nonempty single-line language setting",
        )
        languages[field] = value
    return languages


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


def write_json(path, value, *, replace=True, max_bytes=None):
    data = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    if max_bytes is not None:
        require(
            len(data) <= max_bytes,
            f"{path.name} is {len(data)} bytes. The limit is {max_bytes} bytes. "
            "Reduce the artifact text or omit optional outputs, then resubmit.",
        )
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


def read_state(run):
    state = read_json(run / "state.json", limit=32 * 1024 * 1024)
    require(
        isinstance(state, dict) and state.get("version") in (1, VERIFICATION_VERSION), "unsupported run state version"
    )
    require(state.get("attempt_version", 0) in (0, ATTEMPT_VERSION), "unsupported attempt version")
    attempts = state.get("attempts")
    require(
        isinstance(attempts, list) and all(isinstance(attempt, dict) for attempt in attempts),
        "invalid attempts in run state",
    )
    return state


def pending_attempt(state):
    if state["status"] == "dispatched":
        return state["attempts"][-1]
    if state["status"] in ("interrupted", "budget-exhausted"):
        attempt = state["attempts"][-1]
        if attempt["status"] == "no-receipt":
            return attempt
    return None


@contextmanager
def attempt_decision(directory):
    with (directory / ".receipt.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def commit_receipt(job_path, result):
    """Commit an asynchronous receipt while its attempt still accepts results."""
    job_path = job_path.resolve(strict=True)
    directory = job_path.parent
    require(job_path.name == "job.json" and directory.parent.name == "attempts", "invalid job path")
    with attempt_decision(directory):
        attempt = pending_attempt(read_state(directory.parent.parent))
        require(attempt is not None and directory.name == str(attempt["number"]), "attempt is closed for receipts")
        write_json(job_path.with_name("receipt.json"), result, replace=False, max_bytes=MAX_JSON_BYTES)


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


def validate_checks(checks):
    require(isinstance(checks, dict) and checks, "at least one acceptance check is required")
    require(all(map(text, checks)), "check IDs must be nonempty strings")
    if all(map(text, checks.values())):
        return
    for check in checks.values():
        require(
            isinstance(check, dict) and {"kind", "behavior"} <= check.keys(),
            "checks must use either legacy strings or objects with kind and behavior",
        )
        kind = check["kind"]
        require(kind in CHECK_KINDS, "invalid acceptance check kind")
        require(text(check["behavior"]), "check behavior must be a nonempty string")
        fields = {"kind", "behavior"}
        if kind == "source-inspection":
            fields.add("required_sources")
            sources = check.get("required_sources", ["artifact"])
            require(
                text_list(sources) and sources and all(source in REFERENCE_SOURCES for source in sources),
                "required_sources must list artifact, intake, or both",
            )
        require(check.keys() <= fields, "unexpected field in acceptance check")


def validate_request(request):
    require(isinstance(request, dict), "request must be an object")
    native_languages(request)
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
    validate_checks(checks)
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
    elif status == "checker-fault" and phase == "verify":
        require(text(result.get("error")), "checker fault must describe the failure")
        require("checks" not in result, "checker fault must omit check verdicts")
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


def artifact_hashes(artifacts):
    return {item["path"]: digest(item["content"].encode()) for item in artifacts}


def validate_observation(observation, *, passing):
    require(isinstance(observation, dict), "executable check needs an observed checker result")
    argv = observation.get("argv")
    require(
        isinstance(argv, list)
        and argv
        and text(argv[0])
        and all(isinstance(arg, str) and "\0" not in arg for arg in argv),
        "checker observation needs the executed argument vector",
    )
    exit_code = observation.get("exit_code")
    require(type(exit_code) is int, "checker observation needs an integer exit code")
    require(not passing or exit_code == 0, "passing executable check needs a successful checker exit")
    require(
        all(isinstance(observation.get(stream), str) for stream in ("stdout", "stderr")),
        "checker observation needs captured stdout and stderr",
    )


def validate_references(references, sources, required):
    require(isinstance(references, list) and references, "source-inspection check needs a source or artifact reference")
    observed_sources = set()
    for reference in references:
        require(isinstance(reference, dict), "invalid evidence reference")
        source, path = reference.get("source"), reference.get("path")
        require(
            (source == "intake" and path is None) or (source == "artifact" and text(path) and path in sources),
            "evidence reference does not resolve to intake or an artifact",
        )
        lines = sources[path]
        first = reference.get("line_start")
        last = reference.get("line_end", first)
        require(
            positive_int(first) and positive_int(last) and first <= last <= len(lines),
            "evidence reference line range is outside the referenced text",
        )
        quote = reference.get("quote")
        require(
            text(quote) and quote == "\n".join(lines[first - 1 : last]), "evidence quote differs from referenced text"
        )
        observed_sources.add(source)
    require(set(required) <= observed_sources, "source-inspection pass is missing a required evidence source")


def validate_verification_snapshot(result, artifacts, attempt):
    version = result.get("verification_version")
    require(type(version) is int and version == VERIFICATION_VERSION, "invalid verification receipt version")
    require(
        result.get("verification_id") == attempt["verification_id"], "receipt belongs to a different verification job"
    )
    expected_hashes = attempt["artifact_sha256"]
    require(result.get("artifact_sha256") == expected_hashes, "verification receipt has a different artifact digest")
    validate_artifacts(artifacts)
    require(artifact_hashes(artifacts) == expected_hashes, "build artifacts changed after verification dispatch")


def validate_verification(result, request, artifacts, attempt):
    validate_verification_snapshot(result, artifacts, attempt)
    sources = {item["path"]: item["content"].splitlines() for item in artifacts}
    sources[None] = request["intake"]["text"].splitlines()
    for row in result["checks"]:
        check = request["checks"][row["id"]]
        kind = check["kind"]
        require(row.get("kind") == kind, f"evidence kind differs from acceptance check {row['id']}")
        passing = row["status"] == "pass"
        if kind == "executable" and (passing or "observation" in row):
            require("verifier" in attempt, "executable observations require a trusted --verify-worker")
            validate_observation(row.get("observation"), passing=passing)
        elif kind == "source-inspection" and (passing or "references" in row):
            required = check.get("required_sources", ["artifact"]) if passing else []
            validate_references(row.get("references"), sources, required)


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


def publish(run, artifacts, *, expected_hashes=None):
    """Publish the verified tree once, including recovery after rename."""
    output = run / "artifacts"
    if expected_hashes is not None:
        validate_artifacts(artifacts)
    hashes = artifact_hashes(artifacts)
    if expected_hashes is not None:
        require(hashes == expected_hashes, "publication artifacts differ from the verified snapshot")
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
        self.telemetry_warned = False
        self.settled_usage = {}

    @property
    def request(self):
        return self.state["request"]

    @property
    def versioned_checks(self):
        return self.state["version"] == VERIFICATION_VERSION

    def save(self):
        self.state["attempt_version"] = ATTEMPT_VERSION
        write_json(self.run / "state.json", self.state)
        self.save_telemetry()

    def save_telemetry(self, *, metrics=None):
        try:
            if metrics is None:
                metrics = run_metrics(self.run, self.state, settled_usage=self.settled_usage)
            snapshot = telemetry_summary(self.run, self.state, metrics=metrics)
            write_json(self.run / TELEMETRY_FILE, snapshot)
        except OSError:
            if not self.telemetry_warned:
                print("BMAD delivery: unable to write telemetry snapshot. Use the telemetry command.", file=sys.stderr)
                self.telemetry_warned = True

    def receipt(self, attempt):
        return self.run / "attempts" / str(attempt) / "receipt.json"

    def build_outputs(self, attempts):
        outputs = []
        for num in attempts:
            artifacts = read_json(self.receipt(num))["artifacts"]
            require(isinstance(artifacts, list), "saved build receipt has invalid artifacts")
            outputs.extend(artifacts)
        return outputs

    def build_attempts(self):
        if self.state.get("native_worker"):
            return self.state["native_partial"] or self.state["native_build_attempts"]
        attempt = self.state.get("build_attempt")
        return [attempt] if attempt else []

    def artifacts(self):
        return self.build_outputs(self.build_attempts())

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
        if self.versioned_checks:
            job["verification_version"] = VERIFICATION_VERSION
            if "verification_artifact_sha256" in self.state:
                job["verification_artifact_sha256"] = self.state["verification_artifact_sha256"]
            if phase == "verify":
                validate_artifacts(job["artifacts"])
                expected = {}
                for number in self.build_attempts():
                    expected.update(self.state["attempts"][number - 1]["artifact_sha256"])
                require(artifact_hashes(job["artifacts"]) == expected, "build artifacts changed before verification")
                job["artifact_sha256"] = expected
                job["verification_id"] = uuid4().hex
        if self.state.get("native_worker"):
            workflows = NATIVE_ROUTES[self.request["kind"]]
            job["native_workflows"] = workflows
            if phase == "build":
                job["native_workflow"] = workflows[len(self.state["native_partial"])]
                job["native_languages"] = self.state.get("native_languages", {})
        return job

    def dispatch_retry(self, phase):
        requested = self.state.pop("next_retry", None)
        attempts = self.state["attempts"]
        if requested is not None or not attempts:
            return requested
        previous = attempts[-1]
        if previous["phase"] == "verify" and phase == "build":
            return "artifact-repair"
        if previous["phase"] == phase:
            if previous["status"] in ("no-receipt", "invalid-receipt", "failed", "superseded"):
                return "interrupted"
            if phase == "verify" and previous.get("verifier") and previous["status"] in ("ok", "checker-fault"):
                return "reverify"
        return None

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
        retry = self.dispatch_retry(job["phase"])
        attempt = {"number": num, "phase": job["phase"], "status": "dispatched", "started_at": time(), "retry": retry}
        if "verification_id" in job:
            attempt.update(verification_id=job["verification_id"], artifact_sha256=job["artifact_sha256"])
        if workflow:
            attempt["workflow"] = workflow
        if verifier:
            attempt["verifier"] = verifier[0]
        self.state["attempts"].append(attempt)
        self.state["status"] = "dispatched"
        self.save()
        try:
            log = (path / "worker.log").open("ab")
        except OSError:
            attempt["process_outcome"] = "log-open-error"
            return
        with log:
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
                        exit_code = proc.wait(timeout=job["timeout_seconds"])
                        attempt.update(process_outcome="exited", process_exit_code=exit_code)
                    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                        attempt["process_outcome"] = (
                            "timed-out" if isinstance(exc, subprocess.TimeoutExpired) else "interrupted"
                        )
                        os.killpg(proc.pid, signal.SIGKILL)
                        attempt["process_exit_code"] = proc.wait()
            except OSError as exc:
                attempt.setdefault("process_outcome", "launch-error")
                log.write(f"{exc}\n".encode())

    def propose(self, route, attempt, *, reason=None):
        proposal = {"id": str(attempt), "route": route}
        if reason:
            proposal["reason"] = reason
        self.state["proposals"].append(proposal)
        self.state["status"] = "approval-required"

    def select(self, route):
        self.state.update(phase="build", status="ready", route=route, verification=[])
        self.state.pop("verification_artifact_sha256", None)
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
        if self.versioned_checks:
            hashes = artifact_hashes(result["artifacts"])
            sources = native.get("artifact_sources")
            require(
                isinstance(sources, dict) and sources.keys() == hashes.keys(),
                "native evidence must identify the source of every published artifact",
            )
            require(
                all(
                    text(sources[path]) and native["evidence"].get(sources[path]) == sha for path, sha in hashes.items()
                ),
                "native artifact bytes differ from their evidence files",
            )
            attempt["artifact_sha256"] = hashes
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
        elif status == "checker-fault":
            require("verifier" in attempt, "checker fault is reserved for an independent verifier")
            if self.versioned_checks:
                validate_verification_snapshot(result, self.artifacts(), attempt)
            self.state.update(status="checker-fault", error=result["error"])
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
                if self.versioned_checks:
                    attempt["artifact_sha256"] = artifact_hashes(result["artifacts"])
                self.state.update(phase="verify", status="ready", build_attempt=number)
        else:
            rows = result["checks"]
            if self.versioned_checks:
                validate_verification(result, self.request, self.artifacts(), attempt)
                self.state["verification_artifact_sha256"] = attempt["artifact_sha256"]
            self.state["verification"] = rows
            attempt["verification_counts"] = verification_counts(rows)
            if all(row["status"] == "pass" for row in rows):
                self.state.update(phase="publish", status="ready")
            else:
                self.state.update(phase="build", status="ready")
                if self.state.get("native_worker"):
                    self.state["native_partial"] = []

    def recover_attempt(self, attempt, *, resumed=False):
        """Adopt a receipt or record its absence while holding the attempt lock."""
        receipt = self.receipt(attempt["number"])
        if not receipt.exists():
            if attempt["status"] == "dispatched":
                observed_at = time()
                attempt.update(
                    status="no-receipt", resolved_at=observed_at, receipt_missing_at=observed_at, gate="interrupted"
                )
                self.state.update(status="interrupted", error=f"No durable receipt for attempt {attempt['number']}")
                self.save()
            return False
        try:
            sync_directory(receipt.parent)
            result = read_json(receipt)
            validate_receipt(result, attempt["phase"], self.request["checks"])
            self.state.pop("error", None)
            self.apply(result, attempt)
            if attempt["status"] == "no-receipt":
                attempt["receipt_source"] = "late-receipt"
            else:
                attempt["receipt_source"] = "resumed-controller" if resumed else "current-controller"
            attempt["status"] = result["status"]
            if result["status"] in ("checker-fault", "failed") and result.get("diagnostic_code") in DIAGNOSTIC_CODES:
                attempt["diagnostic_code"] = result["diagnostic_code"]
        except (OSError, ValueError, KeyError) as exc:
            attempt["status"] = "invalid-receipt"
            self.state.update(status="interrupted", error=f"Invalid worker receipt: {exc}")
        attempt["resolved_at"] = time()
        status = self.state["status"]
        if status in GATES:
            attempt["gate"] = status
        self.save()
        return attempt["status"] != "invalid-receipt"

    def recover(self, *, resumed=False):
        attempt = pending_attempt(self.state)
        if attempt is not None:
            with attempt_decision(self.receipt(attempt["number"]).parent):
                return self.recover_attempt(attempt, resumed=resumed)
        return False

    def exhaust_budget(self):
        self.state["status"] = "budget-exhausted"
        if self.state["attempts"]:
            self.state["attempts"][-1]["gate"] = "budget-exhausted"
        self.save()

    def retry(self):
        attempt = self.state["attempts"][-1]
        with attempt_decision(self.receipt(attempt["number"]).parent):
            if attempt["status"] == "no-receipt" and self.recover_attempt(attempt):
                return
            if attempt["status"] == "no-receipt":
                if len(self.state["attempts"]) >= self.state["budget"]:
                    self.exhaust_budget()
                    return
                attempt["status"] = "superseded"
            self.state.pop("error", None)
            self.state.update(status="ready", next_retry="interrupted")
            self.save()

    def advance(self):
        if self.state["status"] == "dispatched":
            self.recover()
        while self.state["status"] == "ready":
            if self.state["phase"] == "publish":
                expected = self.state["verification_artifact_sha256"] if self.versioned_checks else None
                hashes = publish(self.run, self.artifacts(), expected_hashes=expected)
                self.state.update(status="complete", artifact_sha256=hashes, completed_at=time())
                self.save()
                return
            if len(self.state["attempts"]) == self.state["budget"]:
                self.exhaust_budget()
                return
            self.dispatch()
            self.recover()

    def reverify_after_budget_exhaustion(self):
        attempts = self.state["attempts"]
        last_attempt = attempts[-1] if attempts else {}
        return (
            self.state["status"] == "budget-exhausted"
            and self.state["phase"] == "build"
            and last_attempt.get("phase") == "verify"
            and bool(last_attempt.get("verifier"))
        )

    def resume(self, args):
        waiting_for_retry_budget = (
            self.state["status"] == "budget-exhausted" and pending_attempt(self.state) is not None
        )
        recovered = self.recover(resumed=True)
        status = self.state["status"]
        if args.approve is not None:
            require(status == "approval-required", "no proposal is waiting for approval")
            proposal = self.state["proposals"][-1]
            require(args.approve == proposal["id"], f"approval must name proposal {proposal['id']}")
        if args.answer is not None:
            require(status == "answer-required" and text(args.answer), "no owner question or empty answer")
        if args.retry:
            require(recovered or status == "interrupted" or waiting_for_retry_budget, "no interrupted attempt to retry")
        if args.reverify:
            if status == "checker-fault":
                require(
                    args.budget is not None or len(self.state["attempts"]) < self.state["budget"],
                    "--reverify needs available budget or a new total budget",
                )
            else:
                require(
                    self.reverify_after_budget_exhaustion(),
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
            if status == "budget-exhausted" and not waiting_for_retry_budget:
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
        if not recovered and (args.retry or (waiting_for_retry_budget and args.budget is not None)):
            self.retry()
        if args.reverify:
            self.state.pop("error", None)
            self.state.update(phase="verify", status="ready", next_retry="reverify")
        self.save()
        self.advance()

    def summary(self, *, metrics=None):
        state = self.state
        status = state["status"]
        keys = (
            "status",
            "phase",
            "route",
            "question",
            "verification",
            "verification_artifact_sha256",
            "artifact_sha256",
            "error",
        )
        summary = {key: state[key] for key in keys if key in state}
        if status == "checker-fault":
            summary.pop("verification", None)
            summary.pop("verification_artifact_sha256", None)
        summary.update(
            run=str(self.run),
            dispatched=len(state["attempts"]),
            budget=state["budget"],
            verification_version=state["version"],
        )
        if not self.versioned_checks:
            summary["verification_evidence"] = "legacy-prose"
        if state.get("native_worker"):
            summary["native_runs"] = [
                {"attempt": item["number"], **item["native"]} for item in state["attempts"] if "native" in item
            ]
        if status in ("interrupted", "checker-fault"):
            summary["worker_log"] = str(self.receipt(len(state["attempts"])).with_name("worker.log"))
        if status == "approval-required":
            summary["proposal"] = state["proposals"][-1]
        pending = pending_attempt(state)
        if pending is not None:
            summary["pending_attempt"] = {
                key: pending[key] for key in ("number", "phase", "status", "workflow") if key in pending
            }
            summary["pending_attempt"]["job"] = str(self.receipt(pending["number"]).with_name("job.json"))
        summary["next_action"] = self.next_action(status, pending)
        summary.update(run_metrics(self.run, state) if metrics is None else metrics)
        return summary

    def next_action(self, status, pending):
        native_worker = self.state.get("native_worker") or []
        workspace_hosted = native_worker[-1:] == ["wait"]
        if status == "dispatched":
            if "workflow" in pending and workspace_hosted:
                return "Serve the pending workflow from its job path. Run resume if the controller stopped."
            return "Wait for the worker. Run resume if the controller stopped."
        if pending is not None:
            if status == "budget-exhausted":
                retry = "Use resume --budget NEW_TOTAL to fund a replacement."
            elif len(self.state["attempts"]) >= self.state["budget"]:
                retry = "Use resume --retry --budget NEW_TOTAL to fund a replacement."
            else:
                retry = "Use resume --retry to start a new attempt."
            if "workflow" in pending and workspace_hosted:
                return f"Submit any finished native result and run resume. {retry}"
            return f"Run resume to adopt a saved receipt. {retry}"
        if status == "checker-fault":
            if len(self.state["attempts"]) >= self.state["budget"]:
                return "Repair the checker and run resume --reverify --budget NEW_TOTAL."
            return "Repair the checker and run resume --reverify."
        if status == "budget-exhausted" and self.reverify_after_budget_exhaustion():
            return (
                "Use resume --budget NEW_TOTAL to rebuild. "
                "If the checker was repaired, use resume --reverify --budget NEW_TOTAL to check the saved build."
            )
        return {
            "ready": "Run resume if the controller stopped.",
            "interrupted": "Inspect the error and worker log, then run resume --retry when ready.",
            "approval-required": "Review the proposal and use resume --approve after owner approval.",
            "answer-required": "Use resume --answer once the owner responds.",
            "budget-exhausted": "Use resume --budget NEW_TOTAL after the owner extends the cap.",
            "complete": "Read the published artifacts and verification results.",
        }[status]


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
    subcommands.add_parser("support", help="print a content-free support summary").add_argument("run", type=Path)
    subcommands.add_parser("telemetry", help="export a shareable run diagnostic").add_argument("run", type=Path)
    return parser.parse_args()


def trusted_executable(path, flag):
    path = path.resolve(strict=True)
    require(path.is_file() and os.access(path, os.X_OK), f"{flag} must be an executable file")
    return [str(path)]


def initial_state(args):
    request = validate_request(read_json(args.request, limit=512 * 1024))
    versioned = isinstance(next(iter(request["checks"].values())), dict)
    if versioned and any(check["kind"] == "executable" for check in request["checks"].values()):
        require(args.verify_worker, "executable checks require a trusted --verify-worker")
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
        "version": VERIFICATION_VERSION if versioned else 1,
        "started_at": time(),
        "request": request,
        "native_languages": native_languages(request),
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
    try:
        run = args.run.resolve()
        if args.command in ("status", "support", "telemetry"):
            require((run / "state.json").is_file(), "run state not found")
            state = read_state(run)
            if args.command == "telemetry":
                summary = telemetry_summary(run, state)
            elif args.command == "support":
                summary = support_summary(run, state)
            else:
                summary = Delivery(run, state, None).summary()
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
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
                state = read_state(run)
            delivery = Delivery(run, state, lock.fileno())
            if args.command == "start":
                delivery.save()
                delivery.advance()
            elif args.command == "resume":
                delivery.resume(args)
            metrics = run_metrics(run, state)
            delivery.save_telemetry(metrics=metrics)
            print(json.dumps(delivery.summary(metrics=metrics), ensure_ascii=False, indent=2))
            return 0 if state["status"] == "complete" else 2
    except BlockingIOError:
        print("This run has a controller or worker in progress.", file=sys.stderr)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        messages = {
            "support": "unable to read the saved support snapshot",
            "telemetry": "unable to read the saved telemetry snapshot",
        }
        error = messages.get(args.command, str(exc))
        print(f"BMAD delivery: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
