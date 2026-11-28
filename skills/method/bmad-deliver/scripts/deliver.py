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

import intake_router
import subscription
from bundle_layout import RELEASE_VERSION
from run_metrics import run_metrics, support_summary
from run_telemetry import (
    DIAGNOSTIC_CODES,
    GATES,
    TELEMETRY_FILE,
    record_intake_checkpoint,
    telemetry_summary,
    verification_counts,
)

MAX_JSON_BYTES = 4 * 1024 * 1024
ATTEMPT_VERSION = 1
VERIFICATION_VERSION = 2
CHECK_KINDS = ("executable", "source-inspection", "judgment")
REFERENCE_SOURCES = ("artifact", "intake")
BUILD_AUTO = "bmad-build-auto"
PRODUCT_BRIEF = "bmad-product-brief"
NATIVE_ROUTES = {"code": [BUILD_AUTO], "non-code": [PRODUCT_BRIEF], "mixed": [BUILD_AUTO, PRODUCT_BRIEF]}
NATIVE_DRAFT_LABELS = {
    "code": "Run-local code artifact",
    "non-code": "Product Brief",
    "mixed": "Run-local code artifact and Product Brief",
}
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
    attempt_version = state.get("attempt_version", 0)
    require(attempt_version in (0, ATTEMPT_VERSION, intake_router.ATTEMPT_VERSION), "unsupported attempt version")
    if attempt_version == intake_router.ATTEMPT_VERSION:
        require(state.get("intake_version") == intake_router.INTAKE_VERSION, "unsupported intake version")
    attempts = state.get("attempts")
    require(
        isinstance(attempts, list) and all(isinstance(attempt, dict) for attempt in attempts),
        "invalid attempts in run state",
    )
    return state


def pending_attempt(state):
    if not state["attempts"]:
        return None
    if state["status"] == "dispatched":
        return state["attempts"][-1]
    if state["status"] in ("interrupted", "budget-exhausted", subscription.PAUSE_STATUS):
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

    @property
    def pending_intake(self):
        return self.state.get("intake_version") == intake_router.INTAKE_VERSION and self.request is None

    @property
    def workflows(self):
        if "execution_plan" in self.state:
            return self.state["execution_plan"]["workflows"]
        return NATIVE_ROUTES[self.request["kind"]]

    def save(self):
        self.state.setdefault("attempt_version", ATTEMPT_VERSION)
        if self.state["attempt_version"] == 0:
            self.state["attempt_version"] = ATTEMPT_VERSION
        record_intake_checkpoint(self.state)
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
        if self.pending_intake:
            catalog = intake_router.read_catalog()
            return {
                "phase": "route",
                "attempt": num,
                "attempt_version": intake_router.ATTEMPT_VERSION,
                "intake_version": intake_router.INTAKE_VERSION,
                "intake_revision": self.state["intake_revision"],
                "run_id": self.state["run_id"],
                "intake": intake_router.material(self.state["intake"]),
                "answers": self.state["answers"],
                "catalog_version": catalog["catalog_version"],
                "routes": intake_router.classifier_catalog(catalog),
                "budget_remaining_after_dispatch": self.state["budget"] - num,
                "timeout_seconds": self.state["intake"].get("timeout_seconds", 600),
            }
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
            workflows = self.workflows
            job["native_workflows"] = workflows
            if phase == "build":
                job["native_workflow"] = workflows[len(self.state["native_partial"])]
                job["native_languages"] = self.state.get("native_languages", {})
        return job

    def managed_stage(self):
        host = self.state.get("subscription_host")
        phase = self.state["phase"]
        if phase == "build":
            return host if (self.state.get("native_worker") or [])[-1:] == ["wait"] else None
        if phase == "verify":
            return host if host == "codex" and not self.state.get("verifier") else None
        return host if self.pending_intake and self.state.get("worker") else None

    def pause_for_subscription(self, host, reason):
        self.state.update(status=subscription.PAUSE_STATUS, subscription_pause={"host": host, "reason": reason})

    @property
    def intake_allowance(self):
        return self.state.get("subscription_allowance", self.state["intake"].get("allowance", "available"))

    def confirm_plan_only(self, allowance):
        self.state.update(plan_only_confirmed=True, subscription_allowance=allowance)
        self.state.pop("subscription_account", None)

    def check_subscription(self):
        host = self.managed_stage()
        if host is not None:
            worker = self.state.get("worker")
            reason, identity = subscription.preflight(
                host,
                confirmed=self.state["plan_only_confirmed"],
                allowance=self.intake_allowance,
                codex=worker[2] if host == "codex" else None,
            )
            previous = self.state.get("subscription_account")
            if identity and previous and identity != previous:
                self.state["plan_only_confirmed"] = False
                reason = "account-changed"
            elif identity:
                self.state["subscription_account"] = identity
            elif not previous:
                self.state["plan_only_confirmed"] = False
            if reason is not None:
                self.pause_for_subscription(host, reason)
                self.save()
                return False
        self.state.pop("subscription_pause", None)
        return True

    def dispatch_retry(self, phase):
        requested = self.state.pop("next_retry", None)
        attempts = self.state["attempts"]
        if requested is not None or not attempts:
            return requested
        previous = attempts[-1]
        if previous["phase"] == "verify" and phase == "build":
            return "artifact-repair"
        if previous["phase"] == phase:
            if previous["status"] in (
                "no-receipt",
                "invalid-receipt",
                "failed",
                "superseded",
                subscription.PAUSE_STATUS,
            ):
                return "interrupted"
            if phase == "verify" and previous.get("verifier") and previous["status"] in ("ok", "checker-fault"):
                return "reverify"
        return None

    def dispatch(self):
        num = len(self.state["attempts"]) + 1
        path = self.receipt(num).parent
        job = self.job(num)
        host = self.managed_stage()
        if host:
            job.update(
                subscription_host=host,
                run_id=self.state["run_id"],
                intake_revision=self.state["intake_revision"],
            )
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
        if self.pending_intake:
            attempt.update(intake_revision=job["intake_revision"], catalog_version=job["catalog_version"])
        if host:
            attempt["subscription_host"] = host
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

    def stop_intake(self, status, code, message):
        self.state.update(status=status, intake_gate={"code": code, "message": message})
        if status == "answer-required":
            self.state["question"] = message
        return False

    def freeze_intake(self, request, route, plan):
        self.state.update(request=request, execution_plan=plan, native_languages=native_languages(request))
        self.state.pop("intake_gate", None)
        self.state.pop("intake_proposal", None)
        self.select(route)
        record_intake_checkpoint(self.state)

    def check_unmanaged_intake_allowance(self):
        if "subscription_host" not in self.state and self.intake_allowance != "available":
            return self.stop_intake(
                "subscription-paused", "allowance", "Confirm available allowance with an owner intake update."
            )
        return True

    def prepare_intake(self):
        envelope = self.state["intake"]
        self.state.pop("intake_gate", None)
        self.state.pop("question", None)
        material = intake_router.material(envelope)
        if any(not source.get("readable", True) or not text(source.get("excerpt")) for source in material["sources"]):
            return self.stop_intake("answer-required", "unreadable-source", "Supply readable excerpts for the sources.")
        if not text(material["text"]) and not material["sources"]:
            return self.stop_intake("answer-required", "missing-material", "What would you like this run to deliver?")
        if not self.check_unmanaged_intake_allowance():
            return False
        if not positive_int(self.state["budget"]):
            return self.stop_intake("answer-required", "missing-budget", "Supply a positive worker-call budget.")
        timeout = envelope.get("timeout_seconds", 600)
        if not positive_int(timeout) or timeout > intake_router.MAX_TIMEOUT_SECONDS:
            return self.stop_intake("answer-required", "timeout", "Supply a per-call timeout from 1 to 86400 seconds.")

        catalog = intake_router.read_catalog()
        self.state["intake_catalog_version"] = catalog["catalog_version"]
        revision = self.state["intake_revision"]
        route_id, subtype = envelope.get("route_id"), envelope.get("subtype")
        classification = self.state.get("classification")
        if route_id is not None or subtype is not None:
            try:
                intake_router.select(catalog, route_id, subtype)
            except ValueError as exc:
                return self.stop_intake("answer-required", "invalid-selection", str(exc))
            classification = {"route_id": route_id, "subtype": subtype, "source": "owner", "intake_revision": revision}
            self.state["classification"] = classification
        if classification is None:
            if not self.state["worker"]:
                return self.stop_intake(
                    "capability-unavailable",
                    "classifier-unavailable",
                    "Choose a route and subtype in an owner intake update.",
                )
            return True
        if classification["route_id"] is None:
            return self.stop_intake(
                "answer-required", "classification-deferred", "What is the intended deliverable or immediate next step?"
            )

        return self.compile_intake(envelope, catalog, classification)

    def compile_intake(self, envelope, catalog, classification):
        entry, subtype = intake_router.select(catalog, classification["route_id"], classification["subtype"])
        if subtype is None:
            return self.stop_intake("answer-required", "missing-subtype", "Choose a subtype for the selected route.")
        capability = subtype["native_execution"]
        if capability is None:
            return self.stop_intake(
                "capability-unavailable",
                "unsupported-selection",
                "The selected route and subtype have no local delivery handler.",
            )

        request = {
            "kind": envelope.get("kind", capability["output_class"]),
            "intake": {
                "kind": envelope.get("intake_kind", "literature" if envelope.get("sources") else "idea"),
                "text": intake_router.canonical_text(envelope),
            },
            "authority": envelope.get("authority"),
            "checks": envelope.get("checks"),
            "budget": envelope["budget"] if positive_int(envelope.get("budget")) else self.state["budget"],
            "timeout_seconds": envelope.get("timeout_seconds", 600),
        }
        for language in ("communication_language", "document_output_language"):
            if language in envelope:
                request[language] = envelope[language]
        try:
            validate_request(request)
            require(
                all(isinstance(check, dict) for check in request["checks"].values()), "intake requires typed checks"
            )
            require(
                request["kind"] == capability["output_class"],
                "the selected subtype does not match the owner output class",
            )
            authority = request["authority"]
            mode = authority["mode"]
            deliverable = envelope.get("deliverable", authority.get("deliverable"))
            if deliverable is None and mode == "A":
                deliverable = NATIVE_DRAFT_LABELS[request["kind"]]
            if deliverable is None and mode == "B":
                names = authority.get("boundaries", {}).get("allowed_deliverables", [])
                if len(names) == 1:
                    deliverable = names[0]
            require(text(deliverable), "supply the owner-approved deliverable name")
            route, reason = self.check_route(
                {
                    "deliverable": deliverable,
                    "kind": request["kind"],
                    "workflows": capability["workflows"],
                    "rationale": "The selected intake subtype uses the catalog's native workflow sequence.",
                    "assumptions": [],
                },
                request=request,
            )
        except ValueError as exc:
            return self.stop_intake("answer-required", "delivery-contract", str(exc))

        if mode == "A":
            reason = "Mode A requires approval of the proposed delivery."
        elif mode == "C" and deliverable != authority["deliverable"]:
            reason = "The proposed deliverable differs from the owner-named deliverable."
        if classification["source"] == "classifier":
            owner_kind = envelope.get("kind")
            kind = request["kind"]
            standalone_brief = kind == "non-code" and deliverable == "Product Brief"
            mixed_brief = owner_kind == "mixed" and deliverable.endswith(" and Product Brief")
            if PRODUCT_BRIEF in route["workflows"] and not (standalone_brief or mixed_brief or reason):
                return self.stop_intake(
                    "answer-required",
                    "document-workflow",
                    "Confirm the Product Brief workflow by selecting its route and subtype.",
                )
            classes = authority.get("boundaries", {}).get("allowed_output_classes", []) if mode == "B" else []
            if not (owner_kind or standalone_brief or set(classes) == {kind} or reason):
                return self.stop_intake(
                    "answer-required", "output-class", "Confirm the output class or select a route and subtype."
                )
        if not self.state["native_worker"]:
            return self.stop_intake(
                "capability-unavailable", "native-unavailable", "A native worker or host is required."
            )
        if not self.state["verifier"] and (
            not self.state["worker"] or any(check["kind"] == "executable" for check in request["checks"].values())
        ):
            return self.stop_intake(
                "capability-unavailable", "checker-unavailable", "A trusted --verify-worker is required."
            )

        plan = {
            "catalog_version": catalog["catalog_version"],
            "intake_revision": self.state["intake_revision"],
            "route_id": entry["id"],
            "subtype": subtype["id"],
            "kind": request["kind"],
            "workflows": route["workflows"],
            "check_ids": sorted(request["checks"]),
            "source_snapshot_sha256": digest(request["intake"]["text"].encode()),
        }
        if reason:
            self.state["proposals"].append(
                {"id": uuid4().hex, "route": route, "reason": reason, "intake_revision": plan["intake_revision"]}
            )
            self.state["intake_proposal"] = {"request": request, "execution_plan": plan}
            return self.stop_intake("approval-required", "delivery-approval", reason)
        self.freeze_intake(request, route, plan)
        return True

    def select(self, route):
        self.state.update(phase="build", status="ready", route=route, verification=[])
        self.state.pop("verification_artifact_sha256", None)
        self.state.pop("build_attempt", None)
        if self.state.get("native_worker"):
            self.state.update(native_partial=[], native_build_attempts=[])

    def check_route(self, result, *, request=None):
        request = self.request if request is None else request
        route = validate_route(result)
        if self.state.get("native_worker"):
            require(
                route["workflows"] == NATIVE_ROUTES[request["kind"]],
                "route must preserve the configured native workflow order",
            )
        authority = request["authority"]
        if authority["mode"] != "B":
            return route, None

        request_kind = request["kind"]
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
        if len(partial) == len(self.workflows):
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
            require("execution_plan" not in self.state, "the frozen intake delivery cannot be replaced")
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
            self.state.pop("error", None)
            self.state.pop("subscription_pause", None)
            if isinstance(result, dict) and result.get("status") == subscription.PAUSE_STATUS:
                host = attempt.get("subscription_host")
                binding = {
                    "subscription_host": host,
                    "phase": attempt["phase"],
                    "attempt": attempt["number"],
                    "run_id": self.state.get("run_id"),
                    "intake_revision": self.state.get("intake_revision"),
                }
                reason = subscription.validate_pause(result, binding)
                self.pause_for_subscription(host, reason)
                self.state["plan_only_confirmed"] = False
            elif "intake_revision" in attempt:
                catalog = intake_router.read_catalog()
                self.state["classification"] = intake_router.validate_classification(
                    result, attempt, self.state, catalog
                )
                self.state["status"] = "ready"
            else:
                validate_receipt(result, attempt["phase"], self.request["checks"])
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
                return False
            checked_retry = False
            if attempt["status"] == "no-receipt":
                if len(self.state["attempts"]) >= self.state["budget"]:
                    self.exhaust_budget()
                    return False
                if self.pending_intake and not self.check_unmanaged_intake_allowance():
                    self.save()
                    return False
                if self.managed_stage():
                    if not self.check_subscription():
                        return False
                    checked_retry = True
                attempt["status"] = "superseded"
            self.state.pop("error", None)
            self.state.update(status="ready", next_retry="interrupted")
            self.save()
            return checked_retry

    def advance(self, *, checked_retry=False):
        if self.state["status"] == "dispatched":
            self.recover()
        while self.state["status"] == "ready":
            if self.pending_intake and not self.prepare_intake():
                self.save()
                return
            if self.state["phase"] == "publish":
                expected = self.state["verification_artifact_sha256"] if self.versioned_checks else None
                hashes = publish(self.run, self.artifacts(), expected_hashes=expected)
                self.state.update(status="complete", artifact_sha256=hashes, completed_at=time())
                self.save()
                return
            if len(self.state["attempts"]) >= self.state["budget"]:
                self.exhaust_budget()
                return
            if not checked_retry and not self.check_subscription():
                return
            checked_retry = False
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

    def extend_budget(self, budget):
        self.state.setdefault("budget_extensions", []).append(
            {"after_dispatch": len(self.state["attempts"]), "total": budget}
        )
        self.state["budget"] = budget

    def update_intake_limits(self, updates):
        if "budget" in updates:
            budget = updates["budget"]
            require(
                positive_int(budget) and budget >= self.state["budget"], "intake update cannot reduce the call budget"
            )
            if budget > self.state["budget"]:
                self.extend_budget(budget)
                if self.state["status"] == "budget-exhausted":
                    self.state["status"] = "interrupted" if pending_attempt(self.state) is not None else "ready"
                elif self.state.get("intake_gate", {}).get("code") == "missing-budget":
                    self.state["status"] = "ready"
        if "allowance" in updates:
            self.state["subscription_allowance"] = updates["allowance"]
            if "intake_proposal" in self.state and "subscription_host" not in self.state:
                if self.check_unmanaged_intake_allowance():
                    self.stop_intake("approval-required", "delivery-approval", self.state["proposals"][-1]["reason"])
            elif self.state.get("intake_gate", {}).get("code") == "allowance":
                self.state["status"] = "interrupted" if pending_attempt(self.state) is not None else "ready"
                self.state.pop("intake_gate")

    def apply_intake_update(self, updates, *, answer=None):
        if updates and updates.keys() <= {"budget", "allowance"}:
            self.update_intake_limits(updates)
            return False
        current = self.state["intake"]
        envelope = {**current, **updates}
        if "subtype" in updates and "route_id" not in updates and not current.get("route_id"):
            saved_route = (self.state.get("classification") or {}).get("route_id")
            if saved_route:
                envelope["route_id"] = saved_route
        if "route_id" in updates and updates["route_id"] != current.get("route_id") and "subtype" not in updates:
            envelope.pop("subtype", None)
        intake_router.validate_material(envelope)
        allowance_changed = "allowance" in updates and updates["allowance"] != self.intake_allowance
        if envelope == current and answer is None and not allowance_changed:
            return False
        budget = self.state["budget"]
        if "budget" in updates:
            budget = updates["budget"]
            require(
                positive_int(budget) and budget >= self.state["budget"], "intake update cannot reduce the call budget"
            )
        answers = self.state["answers"]
        if answer is not None:
            answers = [*answers, {"question": self.state["question"], "answer": answer}]
            require(
                len(json.dumps(answers, ensure_ascii=False).encode()) <= intake_router.MAX_INPUT_BYTES,
                "owner answers exceed 512 KiB",
            )

        def replace_intake():
            if allowance_changed:
                self.state["subscription_allowance"] = updates["allowance"]
            if budget > self.state["budget"]:
                self.extend_budget(budget)
            if (
                intake_router.material(envelope) != intake_router.material(current)
                or any(key in updates for key in ("route_id", "subtype"))
                or answer is not None
            ):
                self.state.pop("classification", None)
            self.state.update(
                intake=envelope,
                intake_revision=self.state["intake_revision"] + 1,
                answers=answers,
                budget=budget,
                status="ready",
            )
            for key in ("error", "question", "intake_gate", "intake_proposal", "next_retry", "subscription_pause"):
                self.state.pop(key, None)
            self.save()

        attempt = pending_attempt(self.state)
        if attempt is not None:
            with attempt_decision(self.receipt(attempt["number"]).parent):
                self.recover_attempt(attempt, resumed=True)
                if attempt["status"] == "no-receipt":
                    attempt["status"] = "superseded"
                replace_intake()
        else:
            replace_intake()
        return True

    def attach_intake_workers(self, args):
        if not (args.native_host or args.native_worker or args.verify_worker):
            return
        code = self.state.get("intake_gate", {}).get("code")
        paused = self.state["status"] == subscription.PAUSE_STATUS and "subscription_host" in self.state
        require(
            paused or (self.pending_intake and code in ("native-unavailable", "checker-unavailable")),
            "worker options require a pending intake capability gate or a managed subscription pause",
        )
        if args.native_host or args.native_worker:
            native = self.state["native_worker"] or []
            require(
                not native or (paused and args.native_worker and native[-1:] == ["wait"]),
                "a native worker is already configured",
            )
            self.state["native_worker"] = native_command(args)
        if args.verify_worker:
            require(not self.state["verifier"], "a verifier is already configured")
            self.state["verifier"] = trusted_executable(args.verify_worker, "--verify-worker")
        if not paused:
            self.state["status"] = "ready"

    def resume(self, args):
        confirmed_allowance = "available"
        if args.confirm_plan_only:
            require("subscription_host" in self.state, "--confirm-plan-only requires a managed intake run")
        self.attach_intake_workers(args)
        if args.intake_update:
            require(self.pending_intake, "intake updates require a pending canonical request")
            require(args.budget is None, "supply a budget in the intake update or use --budget separately")
            updates = intake_router.read_envelope(args.intake_update, update=True)
            confirmed_allowance = updates.get("allowance", confirmed_allowance)
            if self.apply_intake_update(updates):
                if args.confirm_plan_only:
                    self.confirm_plan_only(confirmed_allowance)
                    self.save()
                self.advance()
                return
        waiting_for_retry_budget = (
            self.state["status"] == "budget-exhausted" and pending_attempt(self.state) is not None
        )
        recovered = self.recover(resumed=True)
        status = self.state["status"]
        managed_pause = status == subscription.PAUSE_STATUS and "subscription_host" in self.state
        if args.confirm_plan_only and status != "complete":
            self.confirm_plan_only(confirmed_allowance)
        if args.approve is not None:
            require(status == "approval-required", "no proposal is waiting for approval")
            proposal = self.state["proposals"][-1]
            require(args.approve == proposal["id"], f"approval must name proposal {proposal['id']}")
            if self.pending_intake:
                require(
                    proposal["intake_revision"] == self.state["intake_revision"],
                    "approval must name a proposal for the current intake revision",
                )
        if args.answer is not None:
            require(status == "answer-required" and text(args.answer), "no owner question or empty answer")
            if self.pending_intake:
                code = self.state["intake_gate"]["code"]
                require(
                    code in ("missing-material", "classification-deferred"),
                    "use --intake-update for this owner decision",
                )
                require(args.budget is None, "supply the answer and budget in separate resume commands")
                updates = {"text": args.answer} if code == "missing-material" else {}
                self.apply_intake_update(updates, answer=args.answer)
                self.advance()
                return
        if args.retry:
            require(
                recovered or status == "interrupted" or waiting_for_retry_budget or managed_pause,
                "no interrupted attempt to retry",
            )
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
            self.extend_budget(args.budget)
            if status == "budget-exhausted" and not waiting_for_retry_budget:
                self.state["status"] = "ready"
            if self.pending_intake and self.state.get("intake_gate", {}).get("code") == "missing-budget":
                self.state["status"] = "ready"
        if args.approve is not None:
            self.state["approvals"].append(proposal["id"])
            if self.pending_intake:
                draft = self.state["intake_proposal"]
                self.freeze_intake(draft["request"], proposal["route"], draft["execution_plan"])
            else:
                if self.request["authority"]["mode"] == "B" and self.state["phase"] == "build":
                    self.state["replacements"].append(
                        {"attempt": int(proposal["id"]), "route": proposal["route"], "approval": proposal["id"]}
                    )
                self.select(proposal["route"])
        if args.answer is not None:
            self.state["answers"].append({"question": self.state.pop("question"), "answer": args.answer})
            self.state["status"] = "ready"
        checked_retry = False
        if managed_pause:
            if self.state["plan_only_confirmed"] or self.managed_stage() is None:
                if pending_attempt(self.state) is None:
                    self.state["status"] = "ready"
                elif args.retry or (args.intake_update is None and args.budget is None):
                    checked_retry = self.retry()
        elif not recovered and (args.retry or (waiting_for_retry_budget and args.budget is not None)):
            checked_retry = self.retry()
        if args.reverify:
            self.state.pop("error", None)
            self.state.update(phase="verify", status="ready", next_retry="reverify")
        if args.confirm_plan_only and status == "complete":
            return
        self.save()
        self.advance(checked_retry=checked_retry)

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
            "subscription_pause",
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
        if "intake_version" in state:
            summary.update(
                {
                    key: state[key]
                    for key in ("intake_version", "intake_revision", "classification", "intake_gate", "execution_plan")
                    if key in state
                },
                canonical_request_pending=self.pending_intake,
            )
        if state.get("native_worker"):
            summary["native_runs"] = [
                {"attempt": item["number"], **item["native"]} for item in state["attempts"] if "native" in item
            ]
        if status in ("interrupted", "checker-fault"):
            summary["worker_log"] = str(self.receipt(len(state["attempts"])).with_name("worker.log"))
        if status == "approval-required":
            proposal = state["proposals"][-1]
            if self.pending_intake:
                draft = state["intake_proposal"]
                proposal = {
                    **proposal,
                    "request": {key: value for key, value in draft["request"].items() if key != "intake"},
                    "execution_plan": draft["execution_plan"],
                }
            summary["proposal"] = proposal
        pending = pending_attempt(state)
        if pending is not None:
            summary["pending_attempt"] = {
                key: pending[key]
                for key in ("number", "phase", "status", "workflow", "subscription_host")
                if key in pending
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
            if pending["phase"] == "route" and pending.get("subscription_host") == "claude":
                return "Classify the pending intake from the authorized Claude workspace and submit its decision."
            return "Wait for the worker. Run resume if the controller stopped."
        if status == subscription.PAUSE_STATUS and "subscription_pause" in self.state:
            reason = self.state["subscription_pause"]["reason"]
            action = "Use resume --confirm-plan-only after checking the selected host's included allowance."
            if self.pending_intake:
                action += " To select a manual route with trusted local workers, use resume --intake-update."
            return f"{subscription.PAUSE_REASONS[reason]} {action}"
        if status == subscription.PAUSE_STATUS and self.state.get("intake_gate", {}).get("code") == "allowance":
            action = "Supply available allowance with resume --intake-update."
            if pending is not None:
                action = "Run resume to adopt any saved receipt. " + action
            return action
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
        if self.pending_intake:
            code = self.state.get("intake_gate", {}).get("code")
            if status in ("answer-required", "capability-unavailable", "subscription-paused"):
                if code in ("missing-material", "classification-deferred"):
                    return "Use resume --answer or supply a route and owner data with --intake-update."
                if code == "native-unavailable":
                    return (
                        "Use resume --native-worker PATH or resume --native-host to attach the trusted native handler."
                    )
                if code == "checker-unavailable":
                    return "Use resume --verify-worker PATH to attach the trusted verifier."
                return "Supply the owner decision with resume --intake-update."
            if status == "interrupted":
                return "Inspect the classifier error and retry, or select a route with resume --intake-update."
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
    parser.add_argument("--version", action="version", version=RELEASE_VERSION)
    subcommands = parser.add_subparsers(dest="command", required=True)
    start = subcommands.add_parser("start")
    start.add_argument("run", type=Path)
    inputs = start.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--request", type=Path)
    inputs.add_argument("--intake", type=Path, help="raw text or owner intake envelope")
    workers = start.add_mutually_exclusive_group()
    workers.add_argument("--worker", type=Path, help="trusted local executable taking job and receipt paths")
    workers.add_argument("--codex", action="store_true", help="use the Codex CLI")
    workers.add_argument(
        "--intake-host", choices=("claude",), help="serve intake in the signed-in Claude Code workspace"
    )
    start.add_argument("--model")
    start.add_argument("--effort", choices=("low", "medium", "high", "xhigh"))
    resume = subcommands.add_parser("resume")
    resume.add_argument("run", type=Path)
    actions = resume.add_mutually_exclusive_group()
    actions.add_argument("--approve", metavar="PROPOSAL_ID")
    actions.add_argument("--answer")
    actions.add_argument("--intake-update", type=Path, help="apply an owner decision before the intake request freezes")
    actions.add_argument("--retry", action="store_true")
    actions.add_argument(
        "--reverify", action="store_true", help="rerun a repaired independent checker on the same build"
    )
    resume.add_argument("--budget", type=int, metavar="NEW_TOTAL")
    for command in (start, resume):
        command.add_argument(
            "--confirm-plan-only",
            action="store_true",
            help="confirm included allowance and disabled paid continuation and reload on the selected host",
        )
        native = command.add_mutually_exclusive_group()
        native.add_argument(
            "--native-worker", type=Path, help="trusted executable that invokes the native BMAD workflows"
        )
        native.add_argument(
            "--native-host", action="store_true", help="dispatch native workflow jobs to the workspace agent"
        )
        command.add_argument("--verify-worker", type=Path, help="trusted local executable for the verification phase")
    subcommands.add_parser("status").add_argument("run", type=Path)
    subcommands.add_parser("support", help="print a content-free support summary").add_argument("run", type=Path)
    subcommands.add_parser("telemetry", help="export a shareable run diagnostic").add_argument("run", type=Path)
    return parser.parse_args()


def trusted_executable(path, flag):
    path = path.resolve(strict=True)
    require(path.is_file() and os.access(path, os.X_OK), f"{flag} must be an executable file")
    return [str(path)]


def workspace_command():
    host = Path(__file__).with_name("native_host.py").resolve()
    return [sys.executable, str(host), "wait"]


def native_command(args):
    if args.native_host:
        return workspace_command()
    if args.native_worker:
        return trusted_executable(args.native_worker, "--native-worker")
    return None


def initial_state(args):
    envelope = None
    if args.intake:
        envelope = intake_router.read_envelope(args.intake)
        intake_router.validate_material(envelope)
    require(not args.intake_host or envelope is not None, "--intake-host requires --intake")
    if args.intake_host:
        require(args.verify_worker, "--intake-host requires a trusted --verify-worker")
    host = ("codex" if args.codex else args.intake_host) if envelope is not None else None
    require(not args.confirm_plan_only or host is not None, "--confirm-plan-only requires managed raw intake")
    request = None if args.intake else validate_request(read_json(args.request, limit=512 * 1024))
    versioned = request is None or isinstance(next(iter(request["checks"].values())), dict)
    if request and versioned and any(check["kind"] == "executable" for check in request["checks"].values()):
        require(args.verify_worker, "executable checks require a trusted --verify-worker")
    worker = None
    require(args.codex or (args.model is None and args.effort is None), "--model and --effort require --codex")
    if args.worker:
        worker = trusted_executable(args.worker, "--worker")
    elif args.codex:
        codex = shutil.which("codex")
        require(codex or host == "codex", "codex is unavailable on PATH")
        adapter = Path(__file__).with_name("codex_worker.py").resolve()
        executable = str(Path(codex).resolve()) if codex else "codex"
        worker = [sys.executable, str(adapter), executable, args.model or "", args.effort or ""]
    elif args.intake_host:
        worker = workspace_command()
    else:
        require(envelope is not None, "select --codex or provide a trusted --worker")
    state = {
        "version": VERIFICATION_VERSION if versioned else 1,
        "started_at": time(),
        "request": request,
        "worker": worker,
        "native_worker": native_command(args),
        "native_partial": [],
        "native_build_attempts": [],
        "verifier": trusted_executable(args.verify_worker, "--verify-worker") if args.verify_worker else None,
        "budget_extensions": [],
        "phase": "route",
        "status": "ready",
        "attempts": [],
        "answers": [],
        "proposals": [],
        "approvals": [],
        "replacements": [],
    }
    if envelope is None:
        state.update(native_languages=native_languages(request), budget=request["budget"])
    else:
        budget = envelope.get("budget")
        state.update(
            run_id=uuid4().hex,
            attempt_version=intake_router.ATTEMPT_VERSION,
            intake_version=intake_router.INTAKE_VERSION,
            intake_revision=1,
            intake=envelope,
            budget=budget if positive_int(budget) else 0,
        )
    if host:
        state.update(subscription_host=host, plan_only_confirmed=args.confirm_plan_only)
    return state


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
            repeated_confirmation = (
                args.command == "resume" and args.confirm_plan_only and state["status"] == "complete"
            )
            delivery = Delivery(run, state, lock.fileno())
            if args.command == "start":
                delivery.save()
                delivery.advance()
            elif args.command == "resume":
                delivery.resume(args)
            metrics = run_metrics(run, state)
            if not repeated_confirmation:
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
