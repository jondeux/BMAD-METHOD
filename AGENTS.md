<!-- bmad:context -->
<!-- Verified 2026-10-04 against 3cae711e. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

# BMAD-METHOD

Open source framework for structured, agent-assisted software delivery. Skills live in `skills/`, Python tooling in `tools/`, the Astro docs site in `docs-site/`, and documentation in `docs/`.

## Policy

- Use Conventional Commits for every commit.
- No tool or model attribution, anywhere.
- Push only when explicitly requested. Commit first; the worktree must be clean with no untracked files.
- Pull requests: branch from and target `dev` branch. Verify with `gh pr view` after creating.
- Never push to `main` except by following `tools/release.md`. Legacy npm installer is maintained separately on `V6.12` branch.

## Where things are

- Skill validation rules: `tools/skill-validator.md`.
- Rules shared by every skill that reads or writes the ticket tree: `tools/ticket-tree-rules.md`.
- Documentation conventions: `docs/_STYLE_GUIDE.md`.

## Running and verifying

- To validate skills: `uv run tools/validate_skills.py --strict`.
- To run the Python tests: `uv run --frozen python -B -m pytest`.

## Conventions that differ from defaults

- Skills, workflows, tasks, and agent definitions are prompt text an agent reads in full on every run. Length and ambiguity are paid on every run; a corner case is paid only when it occurs. So do not add instructions for exotic cases — the model usually handles them from context, and the reviewing human can correct it when it does not.
- Write template conditionals as block-level `{% if %}` on their own lines, never inside a sentence; a whitespace-only difference in one rendered variant is an acceptable price for readable source.
- Leave runtime choices as prose: when the model decides a value while running, the alternatives stay in the text. Render-time conditionals are only for values fixed before the render.
- Prefer deleting an instruction to hedging it.
- Automated tests assert outcomes produced by deterministic code. Do not write automated tests for LLM output or for static source text.

<!-- /bmad:context -->

## Documentation freshness

Run the [freshness routine](docs/reference/document-freshness.md) after module moves, milestones, or a failing check. Run it as part of the current work without asking. The checker only reads files and never commits.

## Project handoff

Read the [project handoff](project-handoff.md) before continuing Autonomous Delivery work from a fresh checkout.

## Approved learnings

<learned>

- 2026-11-27 — In BMad workflow maps and onboarding guides, show raw documents, research, and recordings as a distinct entry point. Verify which formats the workflow can read through its host.
- 2026-11-27 — In BMad routing and model-upgrade work, retain the selected-option probability and any confidence statistic as separate signals. Evaluate both on labeled, representative intake before using them as routing gates.
- 2026-11-27 — For subscription-only BMad intake and delivery, verify that the selected host will use the included allowance and can pause before using paid credits. Check this separately from sign-in.
- 2026-11-27 — When the owner places a gate inside a saved Autonomous Delivery workflow, preserve the existing run and authority record. Verify that incompatible older runtimes safely reject new persistence protocols.
- 2026-11-28 — In Codex subscription integrations, verify the first-party ChatGPT inference endpoint separately from the quota probe. Smoke-test the actual worker under the included allowance.
- 2026-11-28 — For subscription preflight, inspect the existing CLI account read-only and pause on an ineligible authentication method. Preserve the stored credentials.
- 2026-11-28 — Treat Autonomous Delivery call-budget and allowance changes as accounting updates. Preserve the intake revision and any eligible pending receipt when those are the only changes.
- 2026-11-28 — For Autonomous Delivery releases, execute the documented rollback against the archived previous release and a representative saved run. Verify the separately published archive digest and use the previous release's compatibility checker.
- 2026-11-28 — Verify the release version and enabled state in the same plugin registry the owner uses, then verify that the installed entry skill is available in a fresh session.
- 2026-11-28 — Before an in-place Autonomous Delivery plugin upgrade, back up the exact active runtime. Verify that the worker paths saved by earlier runs still resolve after installation.
- 2026-11-28 — After installing an Autonomous Delivery upgrade, remove older active installs of that plugin by exact identity across the local and hosted registries. Verify the user-facing installed list contains only the new version. Keep rollback archives and any runtime paths still needed by saved runs.
- 2026-11-28 — Test planning-first Autonomous Delivery with blind intake. Keep expected routes and handoffs in a separate evaluator guide, score the next step from the saved artifact and open decision, and record scoped mixed-package compatibility separately.

</learned>
