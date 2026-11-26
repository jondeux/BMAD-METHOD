#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Collect results from a native BMad workflow in a delivery attempt workspace."""

import argparse
import hashlib
import re
import shutil
import sys
import time
from pathlib import Path

from deliver import (
    BUILD_AUTO,
    MAX_JSON_BYTES,
    NATIVE_COMPLETION,
    VERIFICATION_VERSION,
    read_json,
    require,
    validate_artifacts,
    write_json,
)

BUNDLED_NATIVE = Path(__file__).resolve().parents[1] / "assets/native"
SETUP_SCRIPTS = ("config_utils.py", "memlog.py", "render_skill.py", "resolve_config.py", "resolve_customization.py")


def read_job(path):
    job = read_json(path, limit=MAX_JSON_BYTES * 4)
    require(job.get("phase") == "build" and job.get("native_workflow") in NATIVE_COMPLETION, "not a native build job")
    require(path.name == "job.json" and path.parent.name == str(job["attempt"]), "invalid native attempt path")
    return job


def workspace_file(workspace, name):
    path = workspace / name
    require(
        path.is_relative_to(workspace) and path.resolve() == path and path.is_file(),
        f"expected a regular file in the native workspace: {name}",
    )
    require(path.stat().st_size <= MAX_JSON_BYTES, f"native file exceeds the receipt limit: {name}")
    return path


def setup(job_path, bmad_root):
    read_job(job_path)
    require(not job_path.with_name("receipt.json").exists(), "native job already has a receipt")
    core = bmad_root / "skills/core-tools/bmad/scripts" if bmad_root else BUNDLED_NATIVE / "runtime"
    require(
        all((core / name).is_file() for name in SETUP_SCRIPTS),
        "missing native setup scripts. Use the beta bundle or supply --bmad-root with a matching checkout.",
    )
    workspace = job_path.parent / "workspace"
    scripts = workspace / "_bmad/scripts"
    scripts.mkdir(parents=True)
    for name in SETUP_SCRIPTS:
        shutil.copyfile(core / name, scripts / name)
    (workspace / "_bmad/config.toml").write_text(
        '[core]\nproject_name = "Delivery"\noutput_folder = "{project-root}/_bmad-output"\n'
        'communication_language = "English"\ndocument_output_language = "English"\n'
        '[modules.bmm]\nplanning_artifacts = "{project-root}/_bmad-output/planning"\n'
        'implementation_artifacts = "{project-root}/_bmad-output"\n',
        encoding="utf-8",
    )
    return workspace


def terminal_evidence(workflow, workspace, terminal):
    if workflow == BUILD_AUTO:
        plan = terminal.read_text(encoding="utf-8")
        parts = plan.split("---", 2)
        require(len(parts) == 3 and not parts[0].strip(), "Build Auto plan needs frontmatter")
        match = re.search(r"(?m)^status:\s*['\"]?(built|done)['\"]?\s*$", parts[1])
        require(match and "## Auto Run Result" in parts[2], "Build Auto needs a completed plan and Auto Run Result")
        return match[1], [terminal]
    result = read_json(terminal)
    require(isinstance(result, dict), "Product Brief result must be a JSON object")
    require(
        result.get("status") == "complete" and result.get("intent") == "create",
        "Product Brief needs its native headless completion result",
    )
    brief = workspace_file(workspace, result["brief"])
    memlog = workspace_file(workspace, result["memlog"])
    require(
        memlog.name == ".memlog.md" and brief.name == "brief.md" and brief.parent == memlog.parent,
        "Product Brief and its memlog must belong to the same workspace",
    )
    return result["status"], [terminal, brief, memlog]


def submit(job_path, terminal_name, artifact_specs, evidence_names):
    job = read_job(job_path)
    workspace = job_path.parent / "workspace"
    require(workspace.resolve() == workspace and workspace.is_dir(), "native workspace not initialized")
    terminal = workspace_file(workspace, terminal_name)
    workflow = job["native_workflow"]
    status, evidence = terminal_evidence(workflow, workspace, terminal)
    artifacts = []
    adopted_paths = []
    versioned = job.get("verification_version") == VERIFICATION_VERSION
    for spec in artifact_specs:
        published, separator, source = spec.partition("=")
        require(separator and published and source, "--artifact requires PUBLISHED_PATH=WORKSPACE_PATH")
        path = workspace_file(workspace, source)
        if versioned:
            content = path.read_bytes().decode("utf-8")
        else:
            content = path.read_text(encoding="utf-8")
        artifacts.append({"path": published, "content": content})
        evidence.append(path)
        adopted_paths.append(path)
    if workflow != BUILD_AUTO:
        require(evidence[1] in adopted_paths, "published artifacts must include the native Product Brief")
    validate_artifacts(artifacts)
    evidence.extend(workspace_file(workspace, name) for name in evidence_names)
    files = {str(p.relative_to(job_path.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence}
    receipt = {
        "status": "ok",
        "artifacts": artifacts,
        "native": {"workflow": workflow, "status": status, "evidence": files},
    }
    if versioned:
        receipt["native"]["artifact_sources"] = {
            artifact["path"]: path.relative_to(job_path.parent).as_posix()
            for artifact, path in zip(artifacts, adopted_paths, strict=True)
        }
    write_json(job_path.with_name("receipt.json"), receipt, replace=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    wait = commands.add_parser("wait")
    wait.add_argument("job", type=Path)
    wait.add_argument("receipt", type=Path)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("job", type=Path)
    prepare.add_argument("--bmad-root", type=Path, help="matching source checkout instead of the bundled runtime")
    complete = commands.add_parser("submit")
    complete.add_argument("job", type=Path)
    complete.add_argument("--terminal", required=True)
    complete.add_argument("--artifact", action="append", required=True)
    complete.add_argument("--evidence", action="append", default=[])
    failed = commands.add_parser("fail")
    failed.add_argument("job", type=Path)
    failed.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        job_path = args.job.resolve(strict=True)
        if args.command == "wait":
            job = read_job(job_path)
            require(args.receipt == job_path.with_name("receipt.json"), "invalid receipt path")
            until = time.monotonic() + job["timeout_seconds"]
            while time.monotonic() < until:
                if args.receipt.exists():
                    return 0
                time.sleep(0.15)
            raise ValueError("native host did not submit a result before the timeout")
        if args.command == "prepare":
            print(setup(job_path, args.bmad_root.resolve() if args.bmad_root else None))
        elif args.command == "submit":
            submit(job_path, args.terminal, args.artifact, args.evidence)
        else:
            read_job(job_path)
            require(bool(args.reason.strip()), "native failure reason is required")
            write_json(job_path.with_name("receipt.json"), {"status": "failed", "error": args.reason}, replace=False)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Native BMad host: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
