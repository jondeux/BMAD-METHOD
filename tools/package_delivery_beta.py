#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Package the local BMad delivery beta and its version-matched native assets."""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = "bmad-deliver/assets/native/SOURCE.json"
BRIEF_REVISION = "f033e70a2c0a3751aaab17dfdd29839ac621f541"
PORTABLE_BASELINE = ".ai-context/delivery-beta/autonomous-delivery-beta-0.3.0.zip"
PORTABLE_BASELINE_SHA256 = "2592542ae305445346261cf55cd88d986f9559e0ec29c8fdb2f7748cd7679a2c"

INSTALL = """# Install the local BMad delivery beta

Use Python 3.11 or later on a POSIX host. Native delivery needs `uv` for workflow
dependencies and an authorized workspace agent with access to the project, native
workflow tools, and review subagents. Start native runs from that agent so it can
serve each build job. The standard `--codex` intake launcher uses the `codex`
executable on `PATH` and a signed-in subscription. Signed-in routing was tested
with Codex. Claude Code workspace intake is a preview with deterministic checks
only. Native preparation writes the requested
communication and document languages to the job configuration. Both default
to English.

| Request | Native route |
| --- | --- |
| Code | Build Auto |
| Document | Product Brief |
| Code and document | Build Auto, then Product Brief |

The beta delivers run-local UTF-8 text files. The 4 MiB limit applies to each complete
serialized JSON receipt, including all files and metadata in that receipt. If a
native submission exceeds the limit, reduce the artifact text or omit optional
outputs and resubmit the same job. When `--codex` verifies mixed delivery, its job
must fit both builds' artifacts, the
request, and metadata within 8 MiB. Requests for a binary file or a different
native workflow need a separately agreed route or deliverable before dispatch.

## Install the skill

Verify the ZIP against its separately published SHA-256 digest before extracting
it to a new directory. Use `sha256sum -c SHA256SUMS` in the extracted standalone
archive to verify its contents, or `shasum -a 256 -c SHA256SUMS` if your host has
`shasum`. Run the read-only compatibility checker from the extracted copy. Add
`--native` to check for `uv` and `--codex` to check for the standard launcher.

```bash
python3 -B bmad-deliver/scripts/check_install.py --native --codex
```

Open a terminal in the project that should use the skill, and copy it into that project.

```bash
test ! -L .agents &&
test ! -L .agents/skills &&
mkdir -p .agents/skills &&
mkdir .agents/skills/bmad-deliver &&
cp -R /absolute/path/to/extracted/bmad-deliver/. .agents/skills/bmad-deliver/
```

Run the compatibility checker against the installed copy before opening its first
workspace agent session. Invoke `$bmad-deliver` with the
intended deliverable and observable checks. For Mode A, approve the proposal before
the build. For Mode B, state the delegated outcome and limits. Mode C preserves the
named deliverable.

## Update or roll back

Extract and verify the candidate in a new directory. Use each release's own
checker. To verify a copied install, pass its skill directory as the first argument
to the matching checker.

```bash
python3 -B /path/to/candidate/bmad-deliver/scripts/check_install.py /path/to/candidate-project/.agents/skills/bmad-deliver --native --codex
```

Install the candidate in a separate project or worktree with its own
`.agents/skills` directory. Start a fresh workspace session there for new runs.
Keep existing runs with the installation that started them because saved
worker paths are absolute. To roll back new work, reopen the previous project
and use its saved runtime. Keep the candidate available for runs with raw intake.
From the previous project, verify the original v0.3.0 portable ZIP against its
separately published digest. Extract it into an empty directory and use its
checker to verify the installed skill before opening the saved run.

```bash
archive_dir=/path/to/original/archives
original=$(mktemp -d) &&
(cd "$archive_dir" &&
  sed -n '/  autonomous-delivery-beta-0\\.3\\.0\\.zip$/p' autonomous-delivery-beta-0.3.0.zip.sha256 | sha256sum -c -) &&
python3 -m zipfile -e "$archive_dir/autonomous-delivery-beta-0.3.0.zip" "$original" &&
python3 -B "$original/skills/bmad-deliver/scripts/check_install.py" .agents/skills/bmad-deliver &&
python3 -B .agents/skills/bmad-deliver/scripts/deliver.py status /path/to/saved-run
```

Use `shasum -a 256 -c -` in place of `sha256sum -c -` where needed.

## Rebuild a bundle

From the source checkout, use the allowed working-tree files and the pinned
Product Brief commit. The ZIP records the builder hash, input source paths, and
input hashes in `bmad-deliver/assets/native/SOURCE.json`. Use the same builder and
matching source paths from the project. The archived members supply the original
input bytes, and the manifest distinguishes the working tree from the pinned
history. Pass the manifest from the extracted original when rebuilding.

```bash
python3 -B tools/package_delivery_beta.py /tmp/original-beta.zip
python3 -m zipfile -e /tmp/original-beta.zip /tmp/original-beta
python3 -B tools/package_delivery_beta.py /tmp/rebuilt-beta.zip --inputs /tmp/original-beta/bmad-deliver/assets/native/SOURCE.json
cmp /tmp/original-beta.zip /tmp/rebuilt-beta.zip
```

Use `--plugin` to build the portable plugin layout. It uses the manifest and icon
from the checksum-pinned v0.3.0 archive. The portable build carries the same skill
payload and `SOURCE.json` under `skills/`.

```bash
python3 -B tools/package_delivery_beta.py /tmp/original-plugin.zip --plugin
python3 -m zipfile -e /tmp/original-plugin.zip /tmp/original-plugin
python3 -B tools/package_delivery_beta.py /tmp/rebuilt-plugin.zip --plugin --inputs /tmp/original-plugin/skills/bmad-deliver/assets/native/SOURCE.json
cmp /tmp/original-plugin.zip /tmp/rebuilt-plugin.zip
```

## Try an example

**Supported document.** Expect Product Brief to produce a local Markdown brief.

```text
$bmad-deliver Mode C. Write decision-brief.md for an internal booking trial.
State that the simulation omitted false releases and name the facilities director
as the proposed decision owner. Verify both statements. Keep the brief local.
```

**Supported code.** Expect Build Auto to produce a local Python file. Configure a
[trusted local checker](bmad-deliver/references/run-record.md#acceptance-checks) that
can execute the Python checks before starting.

```text
$bmad-deliver Mode C. Write a local capacity.py that defines remaining(capacity, booked)
for nonnegative integers. Return the remaining seats, floored at zero. Verify that
remaining(10, 6) returns 4 and remaining(4, 6) returns 0.
```

**Outside native scope.** The requested file needs a binary-capable workflow. Choose
a separate workflow for the slide deck or agree to a Markdown outline before starting
a delivery run.

```text
$bmad-deliver Mode C. Deliver a finished slide deck as a .pptx file.
```

To resume, give the same skill the saved run path. See the
[run and receipt contract](bmad-deliver/references/run-record.md) and
[workspace host instructions](bmad-deliver/references/native-host.md).

Each run saves a local `telemetry.json` with shareable diagnostics. From the
extracted bundle, export a fresh copy after a crash or for an older run.

```bash
python3 -B bmad-deliver/scripts/deliver.py telemetry /path/to/run > delivery-telemetry.json
```

See the [U7 evaluation guide](bmad-deliver/references/evaluate-delivery.md) for
checker preflight and the bundled evaluation cases.
"""


def source_bytes(name):
    source = ROOT / name
    if source.resolve(strict=True) != source or not source.is_file():
        raise ValueError(f"Expected an ordinary repository file: {name}")
    return source.read_bytes()


def historical_brief_file(name):
    try:
        return subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(ROOT), "show", f"{BRIEF_REVISION}:{name}"],
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ValueError("Git is required to read the pinned Product Brief inputs.") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Cannot read Product Brief input {name} at {BRIEF_REVISION}. "
            "Use a checkout with the pinned commit and its file objects."
        ) from exc


def payload(*, plugin=False):
    spec = importlib.util.spec_from_file_location(
        "delivery_bundle_layout", ROOT / "skills/method/bmad-deliver/scripts/bundle_layout.py"
    )
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    worktree = layout.worktree_inputs()
    historical = layout.historical_inputs()
    files = {"INSTALL.md": INSTALL.encode()}
    files.update({member: source_bytes(name) for member, name in worktree.items()})
    files.update({member: historical_brief_file(name) for member, name in historical.items()})
    files[SOURCE_MANIFEST] = (
        json.dumps(
            {
                "manifest_version": 1,
                "release_version": layout.RELEASE_VERSION,
                "archive_format": "zip-stored-v1",
                "product_brief_revision": BRIEF_REVISION,
                "builder_sha256": hashlib.sha256(source_bytes("tools/package_delivery_beta.py")).hexdigest(),
                "worktree_sources": dict(sorted(worktree.items())),
                "historical_sources": dict(sorted(historical.items())),
                "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())},
            },
            indent=2,
        ).encode()
        + b"\n"
    )
    if plugin:
        return portable_payload(files, layout.SKILL, layout.RELEASE_VERSION)
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(files.items())
    ).encode()
    return files


def portable_payload(files, skill, version):
    baseline = source_bytes(PORTABLE_BASELINE)
    if hashlib.sha256(baseline).hexdigest() != PORTABLE_BASELINE_SHA256:
        raise ValueError("The pinned v0.3.0 plugin archive checksum differs. Restore the original archive.")
    with ZipFile(BytesIO(baseline)) as archive:
        manifest = json.loads(archive.read("plugin.json"))
        icon = archive.read("assets/delivery.svg")
    manifest["version"] = version
    manifest["extensions"]["com.openai"]["interface"]["longDescription"] = (
        "Route ideas, research, and brainstorms through eight intake entry points in one saved run. "
        "Native delivery covers run-local code, Product Briefs, and compatible mixed work. "
        "The Codex intake adapter has signed-in smoke evidence. Claude Code workspace intake is a preview "
        "with deterministic checks only. Requires Python 3.11 or later on a POSIX host and uv for native workflows."
    )
    return {
        "plugin.json": (json.dumps(manifest, indent=2) + "\n").encode(),
        "assets/delivery.svg": icon,
        **{f"skills/{name}": content for name, content in files.items() if name.startswith(f"{skill}/")},
    }


def verify_inputs(path, generated):
    expected = json.loads(path.read_bytes())
    actual = json.loads(generated)
    if expected == actual:
        return
    if not isinstance(expected, dict) or not isinstance(expected.get("files"), dict):
        raise ValueError("Supply the SOURCE.json from the original reproducible beta bundle.")
    changed = [name for name, checksum in actual["files"].items() if expected["files"].get(name) != checksum]
    fields = [key for key in actual if key != "files" and expected.get(key) != actual[key]]
    summary = ", ".join([*fields, *changed]) or "input inventory"
    raise ValueError(f"Build inputs differ from the supplied SOURCE.json ({summary}). Restore the matching sources.")


def write_archive(path, files):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}-", delete=False) as output:
            temporary = Path(output.name)
            with ZipFile(output, "w", compression=ZIP_STORED) as archive:
                for name, content in sorted(files.items()):
                    member = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                    member.create_system = 3
                    member.external_attr = 0o100644 << 16
                    archive.writestr(member, content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--plugin", action="store_true", help="build a portable plugin archive")
    parser.add_argument("--inputs", type=Path, help="require the same SOURCE.json as a previous build")
    args = parser.parse_args()
    try:
        files = payload(plugin=args.plugin)
        if args.inputs is not None:
            source = f"skills/{SOURCE_MANIFEST}" if args.plugin else SOURCE_MANIFEST
            verify_inputs(args.inputs, files[source])
        write_archive(args.archive, files)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Delivery beta: {exc}\n")
    print(f"{args.archive}: {len(files)} members")


if __name__ == "__main__":
    main()
