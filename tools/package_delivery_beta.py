#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Package the local BMad delivery beta and its version-matched native assets."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SKILL = "bmad-deliver"
NATIVE = f"{SKILL}/assets/native"
BRIEF_REVISION = "f033e70a2c0a3751aaab17dfdd29839ac621f541"

DELIVERY_FILES = (
    "SKILL.md",
    "bmod.toml",
    "references/native-host.md",
    "references/run-record.md",
    "scripts/codex_worker.py",
    "scripts/deliver.py",
    "scripts/native_host.py",
)
RUNTIME_FILES = ("config_utils.py", "memlog.py", "render_skill.py", "resolve_config.py", "resolve_customization.py")
BUILD_FILES = (
    "customize.toml",
    "plan-template.md",
    "references/claims-check.md",
    "references/deletion-check.md",
    "review-prompts/edge-case-hunter.md",
    "review-prompts/verification-gap.md",
    "step-01-clarify-and-route.md",
    "step-02-plan.md",
    "step-03-implement.md",
    "step-04-review.md",
    "workflow.md",
)
BRIEF_FILES = ("assets/brief-template.md", "customize.toml")
REVIEW_FILES = (
    "customize.toml",
    "references/editorial-common.md",
    "references/lens-adversarial.md",
    "references/lens-edge-case-hunter.md",
    "references/lens-prose.md",
    "references/lens-structure.md",
    "references/lens-verification-gap.md",
    "references/structure-models.md",
    "scripts/word_metrics.py",
)

INSTALL = """# Install the local BMad delivery beta

Use Python 3.11 or later on a POSIX host. Native delivery needs `uv` for workflow
dependencies and an authorized workspace agent with access to the project, native
workflow tools, and review subagents. Start native runs from that agent so it can
serve each build job. The standard `--codex` launcher needs the `codex` executable
on `PATH` and a configured model provider. Prepared native jobs use English for
communication and documents.

| Request | Native route |
| --- | --- |
| Code | Build Auto |
| Document | Product Brief |
| Code and document | Build Auto, then Product Brief |

The beta delivers run-local UTF-8 text files. The 4 MiB limit applies to each complete
serialized JSON receipt, including all files and metadata in that receipt. When
`--codex` verifies mixed delivery, its job must fit both builds' artifacts, the
request, and metadata within 8 MiB. Requests for a binary file or a different
native workflow need a separately agreed route or deliverable before dispatch.

## Install the skill

Extract the ZIP to a new directory. Use `sha256sum -c SHA256SUMS` there to verify
the manifest, or `shasum -a 256 -c SHA256SUMS` if your host has `shasum`. Then open
a terminal in the project that should use the skill, and copy it into that project.

```bash
test ! -e .agents/skills/bmad-deliver &&
test ! -L .agents/skills/bmad-deliver &&
mkdir -p .agents/skills &&
cp -R /absolute/path/to/extracted/bmad-deliver .agents/skills/
```

Open a fresh workspace agent session in the project. Invoke `$bmad-deliver` with the
intended deliverable and observable checks. For Mode A, approve the proposal before
the build. For Mode B, state the delegated outcome and limits. Mode C preserves the
named deliverable.

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
"""


def source_bytes(name):
    source = ROOT / name
    if source.resolve(strict=True) != source or not source.is_file():
        raise ValueError(f"Expected an ordinary repository file: {name}")
    return source.read_bytes()


def historical_brief_file(name):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{BRIEF_REVISION}:skills/bmad-product-brief/{name}"],
    )


def payload():
    files = {"INSTALL.md": INSTALL.encode()}
    for name in ("LICENSE", "CONTRIBUTORS.md"):
        files[f"{SKILL}/{name}"] = source_bytes(name)
    for name in DELIVERY_FILES:
        files[f"{SKILL}/{name}"] = source_bytes(f"skills/method/{SKILL}/{name}")
    for name in RUNTIME_FILES:
        files[f"{NATIVE}/runtime/{name}"] = source_bytes(f"skills/core-tools/bmad/scripts/{name}")
    for workflow, source, members in (
        ("bmad-build-auto", "skills/method", BUILD_FILES),
        ("bmad-review", "skills/core-tools", REVIEW_FILES),
    ):
        files[f"{NATIVE}/entrypoints/{workflow}.md"] = source_bytes(f"{source}/{workflow}/SKILL.md")
        for name in members:
            files[f"{NATIVE}/workflows/{workflow}/{name}"] = source_bytes(f"{source}/{workflow}/{name}")
    files[f"{NATIVE}/entrypoints/bmad-product-brief.md"] = historical_brief_file("SKILL.md")
    for name in BRIEF_FILES:
        files[f"{NATIVE}/workflows/bmad-product-brief/{name}"] = historical_brief_file(name)
    files[f"{NATIVE}/SOURCE.json"] = (
        json.dumps(
            {
                "checkout_head": subprocess.check_output(
                    ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
                ).strip(),
                "checkout_files": "working tree",
                "product_brief_revision": BRIEF_REVISION,
            },
            indent=2,
        ).encode()
        + b"\n"
    )
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n" for name, content in sorted(files.items())
    ).encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    files = payload()
    with ZipFile(args.archive, "x") as archive:
        for name, content in sorted(files.items()):
            member = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            member.external_attr = 0o100644 << 16
            archive.writestr(member, content, compress_type=ZIP_DEFLATED)
    print(f"{args.archive}: {len(files)} members")


if __name__ == "__main__":
    main()
