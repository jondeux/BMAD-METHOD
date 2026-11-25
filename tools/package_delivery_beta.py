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

Use Python 3.11 or newer, uv for native workflow dependencies, and a Codex workspace agent
with access to the project files, native tools, and your configured model provider.

Extract the ZIP to a new directory. Verify its manifest there with `sha256sum -c SHA256SUMS`.
Then open a terminal in the project that should use the skill, and copy it into that project.

```bash
test ! -e .agents/skills/bmad-deliver &&
test ! -L .agents/skills/bmad-deliver &&
mkdir -p .agents/skills &&
cp -R /absolute/path/to/extracted/bmad-deliver .agents/skills/
```

Open a fresh Codex session in the project and invoke the skill with an idea or source file.

```text
$bmad-deliver Turn my intake notes into an internal decision brief.
Mode C. Use only these notes and keep the draft local.
```

Include the behaviors that the output must demonstrate. For Mode A, approve the proposed deliverable
before any native build. For Mode B, state the delegated outcome and limits. Mode C preserves the
named deliverable.

The beta includes the native Build Auto, Product Brief, and review workflow files. For native runs,
start from the workspace agent so it can serve the jobs and record actual evidence. Use the same skill
with the saved run path to resume. See `bmad-deliver/references/run-record.md` and
`bmad-deliver/references/native-host.md` for the terminal and host interfaces.
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
