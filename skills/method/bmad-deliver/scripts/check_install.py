#!/usr/bin/env python3
"""Check an extracted or installed BMad delivery beta without executing it."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

SOURCE_MANIFEST = "assets/native/SOURCE.json"


def platform_issues(*, native=False, codex=False):
    issues = []
    if sys.version_info < (3, 11):  # noqa: UP036 - diagnose older installations
        issues.append("Python 3.11 or later is required.")
    if os.name != "posix":
        issues.append("A POSIX host is required.")
    else:
        try:
            import fcntl
        except ImportError:
            issues.append("POSIX file locking is unavailable in this Python installation.")
        else:
            if not hasattr(fcntl, "flock") or any(
                not hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK", "killpg")
            ):
                issues.append("Required POSIX file and process operations are unavailable.")
    if native and not shutil.which("uv"):
        issues.append("Install uv on PATH for native delivery.")
    if codex and not shutil.which("codex"):
        issues.append("Install codex on PATH for the standard launcher.")
    return issues


def check_files(skill):
    try:
        from bundle_layout import SKILL, historical_inputs, worktree_inputs
    except ImportError as exc:
        raise ValueError("The checker is missing its bundle layout. Run it from a complete candidate bundle.") from exc

    path = skill / SOURCE_MANIFEST
    if not path.is_file() or path.resolve() != path:
        raise ValueError("The beta source manifest is missing or redirected. Extract a fresh beta bundle.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("The beta source manifest must be a JSON object.")
    if "manifest_version" not in manifest and "checkout_head" in manifest:
        raise ValueError("Legacy beta install. Keep it for its saved runs and install the candidate side by side.")
    if type(manifest.get("manifest_version")) is not int or manifest["manifest_version"] != 1:
        raise ValueError("Unsupported beta source manifest. Use the compatibility checker from the matching bundle.")
    files = manifest.get("files")
    expected = {"INSTALL.md", *worktree_inputs(), *historical_inputs()}
    if not isinstance(files, dict) or files.keys() != expected:
        raise ValueError("The beta source manifest differs from the required runtime inventory.")
    checked = 0
    for name, sha256 in files.items():
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("The beta source manifest contains an invalid SHA-256.")
        if name == "INSTALL.md":
            continue
        relative = name.removeprefix(f"{SKILL}/")
        installed = skill / relative
        if not installed.is_file() or installed.resolve() != installed:
            raise ValueError(f"Missing or redirected installed file {relative}. Extract a fresh beta bundle.")
        with installed.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != sha256:
            raise ValueError(f"Checksum mismatch for {relative}. Extract a fresh beta bundle.")
        checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--native", action="store_true", help="also check uv on PATH")
    parser.add_argument("--codex", action="store_true", help="also check codex on PATH")
    args = parser.parse_args()
    issues = platform_issues(native=args.native, codex=args.codex)
    if issues:
        parser.exit(1, "\n".join(issues) + "\n")
    sys.dont_write_bytecode = True
    try:
        checked = check_files(args.skill.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Delivery beta: {exc}\n")
    print(f"Compatible beta install. Verified {checked} installed files.")


if __name__ == "__main__":
    main()
