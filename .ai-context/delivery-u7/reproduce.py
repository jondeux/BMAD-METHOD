#!/usr/bin/env python3
"""Reproduce the U7 coverage counts and replay the saved checks offline."""

import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from check_holdout_code import VECTORS

HERE = Path(__file__).resolve().parent
CONTEXT = HERE.parent
RECOVERY_ROOT = "live-recovery-evidence/"
HOLDOUT_SHA256 = "26901df5db3663e8219228f34f86f0bfb3c94f5b18e466cb95111d3fc779a17b"
ARCHIVES = {
    "pilot-evidence.zip": "c0591dc1b1003e9aa3b35c5fff486b686120fb3aa2c9f85dcd49237722acba56",
    "delivery-beta/live-recovery-evidence.zip": "ce3241252a46ce4ba73980913cfd2e2626147632bd6f63028ce6f07f969a9358",
    "delivery-beta/autonomous-delivery-beta-0.2.0.zip": "1c082c88268d3ef88ab6a733fe4ed66e49a0cb7827c32965dbb4a87a592cc980",
}
REHEARSAL_EVIDENCE = {
    "bmad-deliver": "workshop/run/state.json",
    "bmad-build-auto": "workshop/run/attempts/2/workspace/_bmad-output/plan.md",
    "bmad-product-brief": "workshop/run/attempts/3/workspace/native-brief-result.json",
    "bmad-review": (
        "workshop/run/attempts/3/workspace/_bmad-output/planning/briefs/brief-Delivery-2026-11-25/editorial-review.md"
    ),
}
PILOT_REHEARSAL_EVIDENCE = {
    "bmad-build-auto": "delivery/r5-build-auto/handoff-test.log",
    "bmad-code-review": "controls/evidence/review-triage.md",
}
EXECUTABLE_CHECKS = {
    "workshop": {"capacity", "floor", "empty"},
    "inventory": {"below", "equal", "clamp", "zero"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def archive_path(name):
    path = CONTEXT / name
    with path.open("rb") as handle:
        require(hashlib.file_digest(handle, "sha256").hexdigest() == ARCHIVES[name], f"Changed evidence: {name}")
    return path


def verify_members(archive, prefix=""):
    rows = archive.read(f"{prefix}SHA256SUMS").decode().splitlines()
    for row in rows:
        expected, name = row.split("  ", 1)
        require(digest(archive.read(f"{prefix}{name}")) == expected, f"Archive member differs: {name}")
    return len(rows)


def rows(archive, name):
    return list(csv.DictReader(archive.read(name).decode().splitlines(), delimiter="\t"))


def score_saved_run(archive, case, work, checker):
    prefix = f"{RECOVERY_ROOT}{case}/"
    request = json.loads(archive.read(f"{prefix}request.json"))
    state = json.loads(archive.read(f"{prefix}run/state.json"))
    status = json.loads(archive.read(f"{prefix}final-status.json"))
    recovery = json.loads(archive.read(f"{prefix}recovery-event.json"))
    before = json.loads(archive.read(f"{prefix}pre-resume-state.json"))
    attempts = state["attempts"]
    checks = set(request["checks"])

    def require_case(condition, message):
        require(condition, f"{case}: {message}")

    require_case(state["status"] == status["status"] == "complete", "run did not complete")
    phases = [attempt["phase"] for attempt in attempts]
    require_case(phases == ["route", "build", "build", "verify"], "unexpected attempt sequence")
    require_case(len(phases) == status["dispatched"], "dispatch count mismatch")
    require_case(all(attempt["status"] == "ok" for attempt in attempts), "saved attempt failed")
    job_bytes = archive.read(f"{prefix}run/attempts/4/job.json")
    job = json.loads(job_bytes)
    original = json.loads(archive.read(f"{prefix}run/attempts/4/receipt.json"))
    require_case(request == state["request"] == job["request"], "original checks or request changed")
    require_case(original["checks"] == status["verification"] == state["verification"], "saved verdict mismatch")

    expected = status["artifact_sha256"]
    artifacts = {item["path"]: item["content"].encode() for item in job["artifacts"]}
    require_case(expected.keys() == artifacts.keys(), "published and verified artifact inventories differ")
    require_case(state["artifact_sha256"] == expected, "saved artifact hashes differ")
    for name, expected_hash in expected.items():
        artifact = archive.read(f"{prefix}run/artifacts/{name}")
        require_case(artifact == artifacts[name] and digest(artifact) == expected_hash, f"artifact differs: {name}")

    route = status["route"]["workflows"]
    native_runs = status["native_runs"]
    require_case(route == state["route"]["workflows"], "route mismatch")
    require_case([record["workflow"] for record in native_runs] == route, "native workflow differs from route")
    require_case(bool(native_runs), "no native completion records")
    for record in native_runs:
        base = f"{prefix}run/attempts/{record['attempt']}"
        receipt = json.loads(archive.read(f"{base}/receipt.json"))
        native = {key: value for key, value in record.items() if key != "attempt"}
        require_case(native == receipt["native"], "native completion record differs from the receipt")
        require_case(record["status"] in {"built", "complete"}, "native workflow lacks terminal status")
        require_case(bool(record["evidence"]), "native workflow lacks evidence")
        for name, sha256 in record["evidence"].items():
            require_case(digest(archive.read(f"{base}/{name}")) == sha256, f"native evidence differs: {name}")

    pending = before["attempts"][-1]
    accepted = attempts[len(before["attempts"]) - 1]
    require_case(before["request"] == request and before["status"] == "dispatched", "pre-resume state differs")
    require_case(before["attempts"][:-1] == attempts[: len(before["attempts"]) - 1], "earlier attempts changed")
    require_case(
        pending["number"] == accepted["number"] == recovery["build_receipt_attempt"]
        and pending["phase"] == accepted["phase"] == "build"
        and pending["workflow"] == accepted["workflow"]
        and pending["status"] == "dispatched"
        and accepted["status"] == "ok",
        "pending build was not adopted",
    )
    receipt_bytes = archive.read(f"{prefix}run/attempts/{accepted['number']}/receipt.json")
    saved_receipt_hash = digest(receipt_bytes)
    require_case(
        saved_receipt_hash == recovery["receipt_sha256_before_resume"] == recovery["receipt_sha256_after_resume"]
        and recovery["receipt_saved_before_kill"]
        and not recovery["old_controller_consumed_receipt"]
        and recovery["resume_exit_code"] == 0,
        "saved receipt recovery proof differs",
    )
    job_path = work / f"{case}-job.json"
    receipt_path = work / f"{case}-receipt.json"
    job_path.write_bytes(job_bytes)
    subprocess.run(
        [sys.executable, "-B", str(checker), str(job_path), str(receipt_path)],
        cwd=work,
        stdout=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
    replay = json.loads(receipt_path.read_bytes())
    require_case(replay["status"] == original["status"] == "ok", "verification receipt failed")
    require_case(replay["checks"] == original["checks"], "replayed verdicts differ")
    require_case(len(replay["checks"]) == len(checks), "verification check count mismatch")
    require_case({row["id"] for row in replay["checks"] if row["status"] == "pass"} == checks, "missing passes")
    evidenced = {row["id"] for row in replay["checks"] if row["evidence"].strip()}
    executable = EXECUTABLE_CHECKS[case]
    require_case(executable <= checks, "executable check inventory differs")

    return {
        "case": case,
        "route": route,
        "native_completions": [record["workflow"] for record in native_runs],
        "dispatches": status["dispatched"],
        "dispatch_budget": status["budget"],
        "original_checks_passed": len(checks),
        "original_checks_total": len(checks),
        "replayed_evidence": {
            "executable_observations": len(evidenced & executable),
            "legacy_text_checks": len(evidenced - executable),
            "original_checks_with_evidence": len(evidenced),
        },
        "verified_artifacts": expected,
        "first_verification_passed": True,
        "recorded_owner_inputs": len(state["answers"]) + len(state["approvals"]),
        "owner_interruptions": None,
        "controller_recoveries": int(recovery["controller_after"] != recovery["controller_before"]),
        "build_redispatches": phases.count("build") - len(route),
        "owner_first_pass": None,
        "owner_material_rework": None,
        "seconds_to_usable_output": None,
    }


def score_direct_build(pilot, work):
    prefix = "delivery/r5-build-auto/"
    for name in ("duration.py", "test_duration.py"):
        (work / name).write_bytes(pilot.read(f"{prefix}{name}"))
    result = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "-q", "test_duration"],
        cwd=work,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    original = pilot.read(f"{prefix}handoff-test.log").decode()
    replayed_count = re.search(r"Ran (\d+) tests?", result.stderr)
    original_count = re.search(r"Ran (\d+) tests?", original)
    require(replayed_count and original_count and replayed_count[1] == original_count[1], "Direct test count changed")
    return {"case": "R5", "replayed_tests": int(replayed_count[1]), "matched_autonomous_case": None}


def validate_holdouts(plugin, work):
    cases = HERE / "holdout-cases.json"
    payload = cases.read_bytes()
    require(digest(payload) == HOLDOUT_SHA256, "Frozen holdout requests differ")
    for case in json.loads(payload)["cases"]:
        check_ids = {name for name, check in case["request"]["checks"].items() if check["kind"] == "executable"}
        vectors = VECTORS[case["id"]][1] if case["id"] in VECTORS else {}
        require(check_ids == vectors.keys(), f"Missing executable vectors in {case['id']}")
    script_prefix = "skills/bmad-deliver/scripts/"
    for name in ("deliver.py", "run_metrics.py"):
        (work / name).write_bytes(plugin.read(f"{script_prefix}{name}"))
    check = """
import json
import sys
from pathlib import Path
from deliver import NATIVE_ROUTES, validate_request

cases = json.loads(Path(sys.argv[1]).read_bytes())["cases"]
for case in cases:
    request = validate_request(case["request"])
    workflows = NATIVE_ROUTES[request["kind"]]
    if case["direct_workflows"] != workflows or request["budget"] != len(workflows) + 2:
        raise ValueError(f"Invalid direct comparison or first-pass budget: {case['id']}")
print(len(cases))
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", check, str(cases)],
        cwd=work,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {"validated_requests": int(result.stdout), "sha256": digest(payload), "delivery_runs": 0}


def coverage(pilot, recovery, plugin, saved_runs):
    inventory = rows(pilot, "inventory/execution-coverage.tsv")
    names = {row["skill or module record"].strip(): row["source"] for row in inventory}
    require(len(names) == len(inventory), "Duplicate pilot inventory entries")
    require("skills/bmad-deliver/SKILL.md" in plugin.namelist(), "Packaged delivery skill unavailable")
    brief = "skills/bmad-deliver/assets/native/entrypoints/bmad-product-brief.md"
    require(brief in plugin.namelist(), "Packaged Product Brief unavailable")
    names.update({"bmad-deliver": "skills/method/bmad-deliver/SKILL.md", "bmad-product-brief": brief})
    route_names = {name for run in saved_runs for name in run["route"]}
    completed_names = {name for run in saved_runs for name in run["native_completions"]}
    rehearsals = {}
    for archive, collection, prefix in (
        (recovery, REHEARSAL_EVIDENCE, RECOVERY_ROOT),
        (pilot, PILOT_REHEARSAL_EVIDENCE, ""),
    ):
        for name, path in collection.items():
            require(bool(archive.read(f"{prefix}{path}")), f"Missing rehearsal evidence: {path}")
            rehearsals.setdefault(name, []).append(f"{Path(archive.filename).name}!{prefix}{path}")
    require(route_names | completed_names | rehearsals.keys() <= names.keys(), "Uncatalogued workflow evidence")
    return [
        {
            "name": name,
            "catalogued": True,
            "catalog_source": names[name],
            "routed": name in route_names,
            "rehearsed": name in rehearsals,
            "rehearsal_members": rehearsals.get(name, []),
            "natively_completed": name in completed_names,
            "owner_accepted": None,
        }
        for name in sorted(names)
    ]


def main():
    with (
        ZipFile(archive_path("pilot-evidence.zip")) as pilot,
        ZipFile(archive_path("delivery-beta/live-recovery-evidence.zip")) as recovery,
        ZipFile(archive_path("delivery-beta/autonomous-delivery-beta-0.2.0.zip")) as plugin,
        tempfile.TemporaryDirectory(prefix="bmad-u7-") as directory,
    ):
        work = Path(directory)
        member_counts = {"pilot": verify_members(pilot), "recovery": verify_members(recovery, RECOVERY_ROOT)}
        checker = work / "verify-delivery"
        checker.write_bytes(recovery.read(f"{RECOVERY_ROOT}verify-delivery"))
        saved_runs = [score_saved_run(recovery, case, work, checker) for case in ("workshop", "inventory")]
        direct = score_direct_build(pilot, work)
        holdouts = validate_holdouts(plugin, work)
        coverage_rows = coverage(pilot, recovery, plugin, saved_runs)
        scores = rows(pilot, "routing/scored.tsv")
        require(len({row["id"] for row in scores}) == len(scores), "Duplicate routing case IDs")
        routing = {"cases": len(scores), **Counter(row["overall"].strip() for row in scores)}
    totals = {
        field: sum(row[field] is True for row in coverage_rows)
        for field in ("catalogued", "routed", "rehearsed", "natively_completed", "owner_accepted")
    }
    print(
        json.dumps(
            {
                "archive_members": member_counts,
                "coverage_totals": {"catalog_size": len(coverage_rows), **totals, "owner_verdicts_observed": 0},
                "pilot_routing": routing,
                "historical_native_runs": saved_runs,
                "historical_direct_build": direct,
                "fresh_synthetic_holdouts": holdouts,
                "coverage": coverage_rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
