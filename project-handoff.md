# BMAD-METHOD project handoff

Updated 2026-11-28 for the Autonomous Delivery work on `handoff/autonomous-bmad-pilot-20261125`.

> Read [AGENTS.md](AGENTS.md) and this handoff first. From the repository root, run the clean-checkout checks below. Then prepare the offline, synthetic Ingest slice for Increment 6. The checkout contains the inputs for those steps. Use historical handoffs for evidence about earlier versions.

## Current state

The goal is one saved Autonomous Delivery run from the owner’s raw intake through an eligible BMad workflow, independent verification, and local artifacts. Intake is Delivery’s route phase. It chooses among eight entry points, then the controller checks capability, owner authority, and original acceptance checks before building. [Intake roadmap](.ai-context/intake-router-plan.md) · [Run contract](skills/method/bmad-deliver/references/run-record.md)

| Area | Verified state on 2026-11-28 |
| --- | --- |
| Repository release | The handoff branch packages the v0.4.1 source, manual, two install ZIPs, and SHA-256 manifest. The release commit is `7aa2e8f4`. The 15-case test pack and separate evaluator guide are ready for trial. Use `git log -1 -- .ai-context/delivery-beta/autonomous-delivery-beta-0.4.1.zip` to identify the release commit. |
| Local plugin | v0.4.1 was installed and enabled in the delivery workspace through `bmad-delivery-local`. A fresh workspace exposed its skill and questionnaire. A fresh clone supplies the archives and source. Its plugin installation must be checked in the actual launcher. |
| Private hosted plugin | The existing private release was read back at v0.4.0. Codex Settings reported the newer local installation alongside this older hosted installation. The older entry was uninstalled by its exact hosted identity. After refresh, v0.4.1 was the only installed entry. v0.4.0 remains visible as an uninstalled private listing. The owner authorized removal of that listing. The Codex delete request was rejected because it requires an active workspace, while this listing has personal scope. The rollback archive remains available locally. |
| Intake and execution | Roadmap Increments 1–5 are complete. All eight route IDs are recognized. Native execution covers run-local code, Product Brief, and mixed delivery in that order when both are requested. Unsupported subtypes report a capability gate. |
| v0.4.1 chat behavior | After usable intake, asks for Mode A, B, or C, the available host, model and effort, dispatch budget, and deliverable size. It asks for a trusted checker only where needed. The current chat’s questionnaire is preferred where available, with explicit chat replies as fallback. |
| Saved runs and rollback | v0.4.1 read v0.4.0 raw state without modifying it. Installed tests also replayed v0.3.0 code, brief, and mixed runs. v0.3.0 rejects newer raw state. An in-place marketplace upgrade pruned v0.4.0 locally, and the verified old bytes were restored at their exact path. |

The eight route IDs are `sources`, `unclear`, `thinking`, `trivial`, `small`, `existing`, `epic`, and `project`. The executable subtypes are `thinking/product-brief`, `trivial/run-local-code`, `small/code`, and `small/code-and-product-brief`. A raw document, PDF, recording, video, or literature review can supply context. v0.4.1 uses owner-authorized readable text or excerpts. A task to process the source itself can route to `sources` and pause for its handler. [Route catalog](skills/method/bmad-deliver/references/intake-routes.json) · [User manual](docs/build/autonomous-delivery.md)

## Decisions to carry forward

- The owner approved deliverable **scope** as the questionnaire’s size choice. The existing 512 KiB intake, 4 MiB receipt, and 8 MiB standard Codex job bounds apply. Configurable byte caps and command-line switches are deferred.
- Mode A waits for proposal approval. Mode B delegates within the owner’s stated boundaries. Mode C preserves the named deliverable. Size is saved as an owner decision in the intake, so class-only Mode B keeps its original authority. An unanswered or preselected questionnaire option carries no authority. [Questionnaire contract](skills/method/bmad-deliver/references/intake-questions.md)
- Preserve the saved run path, original typed checks, current proposal revision, and worker paths. Budget and allowance updates alone preserve the intake revision and any eligible pending receipt. A frozen scope change needs a linked new request. Share the allowlisted telemetry export for diagnosis and keep job packets, source excerpts, raw logs, and receipts private. [Recovery and telemetry](skills/method/bmad-deliver/references/run-record.md)
- Live provider work uses an authorized signed-in subscription with included allowance. Check account eligibility and paid continuation separately before confirming a run. The owner chose Codex-only live smoke. Claude Code intake remains a preview with deterministic evidence. The dispatch-cap approval and the subscription allowance confirmation are distinct decisions. [Subscription guard](skills/method/bmad-deliver/scripts/subscription.py)
- The owner’s standing instruction is “Commit and push only when I say ‘commit and push’.” Their approved remote destination is `origin/handoff/autonomous-bmad-pilot-20261125`. Follow `AGENTS.md` for clean-tree and branch rules. The owner approved learning #12 and authorized publication of the current repository changes after reviewing the [15 sample projects](.ai-context/autonomous-delivery-smoke-projects.md). This handoff provides standing context for offline verification and preparation. Live provider dispatch, hosted publication, raw-source retention, and future Git pushes require the applicable explicit authorization.

## Start here on a clean checkout

1. Run `git status --short --branch` and `git log -3 --oneline`. Use this handoff branch or an isolated worktree based on it. Keep local user changes intact. Verify the two v0.4.1 archive hashes. If those files are absent, check the active branch and fetch the handoff ref before running the v0.4.1 smoke.
2. Exercise the installed package before assuming a launcher or account is configured. The smoke below unpacks the standalone archive in a temp directory and uses a synthetic transcript. Its expected result is `capability-unavailable` at `sources/ingest-note` with zero dispatches. Python 3.11+ and a POSIX shell are required. For later native work also install `uv`. For a Codex install in this workspace, use `codex plugin list --marketplace bmad-delivery-local --json` and verify the skill in a fresh session. Check the local and hosted entries in fresh Codex Settings after an upgrade. Remove lower-version active installs by exact identity and verify only the new version remains installed. Preserve earlier worker paths needed by saved runs.
3. Run the focused tests, freshness checks, and strict reference validation. At a release milestone, run the full suite and rebuild both ZIP layouts against the archived `SOURCE.json`. The pinned Product Brief revision is in this branch’s full Git history. Use a full clone for rebuilds, or fetch the history in a shallow checkout. [Freshness routine](docs/reference/document-freshness.md) · [Builder](tools/package_delivery_beta.py)

```bash
release_dir="$PWD/.ai-context/delivery-beta"
(cd "$release_dir" && sha256sum -c autonomous-delivery-beta-0.4.1.zip.sha256)
work=$(mktemp -d)
python3 -m zipfile -e "$release_dir/bmad-deliver-beta-0.4.1.zip" "$work/unpacked"
delivery="$work/unpacked/bmad-deliver/scripts"
python3 -B "$delivery/check_install.py"
python3 -B "$delivery/deliver.py" --version
cat > "$work/intake.json" <<'JSON'
{
  "text": "Turn the synthetic transcript into a cited note.",
  "route_id": "sources",
  "subtype": "ingest-note",
  "sources": [{"id": "transcript-1", "excerpt": "The team approved the Tuesday trial."}],
  "budget": 1
}
JSON
start_status=0
python3 -B "$delivery/deliver.py" start "$work/run" --intake "$work/intake.json" || start_status=$?
test "$start_status" -eq 2
python3 -B "$delivery/deliver.py" status "$work/run"
```

```bash
uv run --frozen python -B -m pytest -n 3 skills/method/bmad-deliver/tests tools/tests/test_package_delivery_beta.py
python3 -B docs/_checks/check_references.py
node docs-site/scripts/validate-doc-links.js
uv run --frozen python -B tools/validate_skills.py --strict
uv run --frozen python -B tools/validate_file_refs.py --strict
```

If dependencies are already cached, add `--offline` to the `uv run` commands. The archive check, standalone smoke, and freshness checker can run while project dependencies are unavailable. The standalone archive includes `INSTALL.md` and `SHA256SUMS`. On systems without `sha256sum`, the equivalent archive verification is `shasum -a 256 -c`.

## Next work after the baseline passes

1. **Prepare Increment 6, first Ingest handler.** Read the [Ingest skill](skills/core-tools/bmad-ingest/SKILL.md) and [native host contract](skills/method/bmad-deliver/references/native-host.md). Use plain UTF-8 synthetic material, such as the transcript above. Plan a single `sources/ingest-note` path and save the plan under `_bmad-output/`. Use the existing route and saved run. Describe how the headless Ingest result binds its cited note to the approved source snapshot. Define the receipt, where the note and temporary raw evidence are kept, and how the verifier checks citations against the source.
2. **Write the offline acceptance cases in the plan.** Require a cited note bound to the source, correct handling of an unreadable source, refusal of a missing or mismatched source binding, and safe resume with an eligible saved receipt. Keep the other source subtypes at their existing gate. Give each fixture an expected route, gate, artifact and verification result. Confirm what must be added to the allowlist and package tests before any new handler is advertised. This preparation can proceed without live credentials or owner-supplied files. [Increment 6 roadmap](.ai-context/intake-router-plan.md#5-implementation-and-plugin-upgrade-sequence)
3. **Keep live evidence and release actions separate.** When an owner authorizes a fresh v0.4.1 interactive dry run, use the manual’s Product Brief prompt for a source-check path and the code prompt for a required-checker path. Observe actual questionnaire replies, unchanged approval state, applied model and dispatch settings, publication, and telemetry. For a private promotion, verify the existing identity and scope, retain the old exact runtime, then verify the new hosted read-back. Jev or another System One classifier is a later, separately approved increment. [User manual and test prompts](docs/build/autonomous-delivery.md)

The revised [sample projects](.ai-context/autonomous-delivery-smoke-projects.md) include planning-first application journeys and a non-code handoff. For projects 9–12, send only the quoted intake to Delivery and keep the [evaluator guide](.ai-context/autonomous-delivery-smoke-evaluator.md) in a separate workspace. Record the inferred route and any capability gate before continuing through manual artifact handoffs. Preserve the build-first mixed route as a separate regression. When extending orchestration, route from the latest stage artifact and its unresolved decision, including the Deep Recon report return. The samples are ready for evaluation. Results from provider-backed runs of this pack are still pending.

## Evidence and file map

- The v0.4.1 full Python suite passed 1,402 tests and 198 subtests. One optional `tiktoken` test was skipped. Seven final packaging tests and five tests against the enabled installed runtime passed. The checker verified 50 bundled files. Both ZIPs rebuilt byte for byte, and the unconfirmed managed launcher paused at zero dispatches. The complete live v0.4.1 questionnaire-to-artifact flow remains untested. The earlier signed-in Codex booking smoke covers the v0.4.0 adapter. [Release evidence levels](skills/method/bmad-deliver/references/evaluate-delivery.md)
- The historical Lantern House game and guide passed 4/4 embedded-browser checks and were accepted by the owner as usable as delivered. That result is evidence for the earlier mixed delivery, separate from v0.4.1 questionnaire verification. [U7 scorecard](.ai-context/delivery-u7/scorecard.md)
- **Install inputs** — [v0.4.1 portable plugin](.ai-context/delivery-beta/autonomous-delivery-beta-0.4.1.zip), [standalone skill](.ai-context/delivery-beta/bmad-deliver-beta-0.4.1.zip), and [SHA-256 manifest](.ai-context/delivery-beta/autonomous-delivery-beta-0.4.1.zip.sha256). [v0.4.0 rollback package](.ai-context/delivery-beta/autonomous-delivery-beta-0.4.0.zip) · [v0.4.0 checksums](.ai-context/delivery-beta/autonomous-delivery-beta-0.4.0.zip.sha256)
- **Runtime** — [Skill entry](skills/method/bmad-deliver/SKILL.md), [controller](skills/method/bmad-deliver/scripts/deliver.py), [intake classifier contract](skills/method/bmad-deliver/scripts/intake_router.py), [native host helper](skills/method/bmad-deliver/scripts/native_host.py), [telemetry](skills/method/bmad-deliver/scripts/run_telemetry.py), and [package layout](skills/method/bmad-deliver/scripts/bundle_layout.py).
- **Checks and fixtures** — [Delivery tests](skills/method/bmad-deliver/tests/test_delivery.py), [intake fixtures](skills/method/bmad-deliver/tests/fixtures/intake-route-cases.json), [telemetry tests](skills/method/bmad-deliver/tests/test_intake_telemetry.py), and [package tests](tools/tests/test_package_delivery_beta.py).
- **Project memory** — [Approved learnings](AGENTS.md#approved-learnings), [candidates](CANDIDATES.md), [earlier handoff and evidence](.ai-context/handoff.md), and the [original handoff-writing procedure](.ai-context/project-handoff-procedure.md). Transient working paths and local plugin caches are machine-specific. The [tracked BMAD route map](_bmad-output/autonomous-delivery-route-map/bmad-method-route-map.html) is available in a clean clone. Everything required to start the offline work is linked here from the tracked tree.
