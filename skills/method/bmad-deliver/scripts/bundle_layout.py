"""Allowlisted BMad delivery beta archive inputs."""

SKILL = "bmad-deliver"
NATIVE = f"{SKILL}/assets/native"
DELIVERY_FILES = (
    "SKILL.md",
    "bmod.toml",
    "references/native-host.md",
    "references/run-record.md",
    "scripts/bundle_layout.py",
    "scripts/check_install.py",
    "scripts/codex_worker.py",
    "scripts/deliver.py",
    "scripts/native_host.py",
    "scripts/run_metrics.py",
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


def worktree_inputs():
    files = {f"{SKILL}/{name}": name for name in ("LICENSE", "CONTRIBUTORS.md")}
    files.update({f"{SKILL}/{name}": f"skills/method/{SKILL}/{name}" for name in DELIVERY_FILES})
    files.update({f"{NATIVE}/runtime/{name}": f"skills/core-tools/bmad/scripts/{name}" for name in RUNTIME_FILES})
    for workflow, source, members in (
        ("bmad-build-auto", "skills/method", BUILD_FILES),
        ("bmad-review", "skills/core-tools", REVIEW_FILES),
    ):
        files[f"{NATIVE}/entrypoints/{workflow}.md"] = f"{source}/{workflow}/SKILL.md"
        for name in members:
            files[f"{NATIVE}/workflows/{workflow}/{name}"] = f"{source}/{workflow}/{name}"
    return files


def historical_inputs():
    files = {f"{NATIVE}/entrypoints/bmad-product-brief.md": "skills/bmad-product-brief/SKILL.md"}
    files.update(
        {f"{NATIVE}/workflows/bmad-product-brief/{name}": f"skills/bmad-product-brief/{name}" for name in BRIEF_FILES}
    )
    return files
