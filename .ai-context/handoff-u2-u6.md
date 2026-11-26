# Autonomous BMAD Delivery · project handoff · 2026-11-25

> Read this handoff and the U7–U8 approval rows in `delivery-review.md`.
> Preserve the owner's authority and original acceptance checks across every resume.
> Configurable size limits are deferred. Start with next action 1 and use the latest owner instruction for scope.

```text
STATE BLOCK · Autonomous BMAD Delivery · 2026-11-25

Goal [V] Deliver verified local code, documents, or both from an idea or intake, with bounded work and recoverable state. See the delivery skill and review.
Success test [V] Mode B enforces delegated scope. Every typed check resolves against its intended artifact. Interrupted runs resume safely. The packaged skill passes its compatibility checker and local tests.
Stage completed [V] U1 documents beta scope. U2 enforces Mode B boundaries. U3 binds typed checks to artifact evidence. U4 adds active status and safer recovery. U5 reports observed usage and offers content-free support output. U6 verifies package inputs and size limits. The five source commits are listed below.
Terms [V] Mode A asks for proposal approval. Mode B delegates within the owner's limits. Mode C keeps the named deliverable. A receipt is a worker's result. A job is a controller dispatch packet. Build Auto and Product Brief are the two native routes.
Goals ranked [I] Preserve delegated authority and acceptance first, make recovery and diagnostics reliable second, and measure owner value before expanding native routes. This order follows the ranked delivery review.
Audience [V] The workspace owner and successor agents. Keep replies concise and report checks actually run. The beta expects POSIX and Python 3.11 or later.
Requirements [V] “try to minimize token spend but at the same time complete all runs”. “Commit and push only when I say "commit and push".” “DO NOT IMPLEMENT IT AS OF YET” applies to configurable size limits. Follow AGENTS.md for Conventional Commits, branch policy, and attribution.
Workflow and rubric [V] Keep original acceptance checks, distinguish rehearsed coverage from native completion, and attach evidence for the exact artifacts checked. Preserve saved receipts and runtime versions when resuming. Use only explicitly approved upgrades.
Decisions [V] D1 keeps the 4 MiB receipt and 8 MiB standard worker job defaults in this release. D2 packages this source as Autonomous Delivery Beta v0.2.0. Keep v0.1.0 alongside it for rollback and legacy runs. See Limit design below.
Rejected alternatives [V] The review rejected treating a workflow name as proof of execution or simulated stakeholders as owner approval. This release defers changing size limits and updating a hosted installation.
Assumptions to confirm [U] Whether the owner needs a real oversized deliverable and which size range would help. Ask for one representative redacted payload or its measured receipt and job sizes after the owner authorizes design or implementation.
Open questions [U] U7 needs the owner's choice of a redacted real task plus synthetic cases or synthetic-only. The owner must approve U7. A separate owner instruction is needed to implement configurable limits.
Verified so far [V] The full repository suite, strict skill validation, package integrity, and packaged compatibility checks are recorded under Verification. Prior v0.1.0 live recovery evidence stays in delivery-beta/LIVE-RECOVERY.md.
Still unverified [U] v0.2.0 launch through the hosted plugin interface, its live field recovery, and owner first-pass acceptance. Verify each in the intended host or with U7 when authorized. Nested native token use remains unavailable from controller evidence.
Next actions [V] 1. Verify the clean branch and package checksum if moving to a fresh checkout. 2. Apply the owner's latest explicit instruction. U7 is the next roadmap item and is awaiting approval. 3. If configurable limits are approved, use the persisted per-run policy described below and test paired-reader boundaries and resume compatibility.
Files and environment [V] See Inventory. This handoff supersedes the status and next actions in the historical .ai-context/handoff.md. The review and prior evidence retain their original meaning.
Risks and rollback [V] A mixed verification job can exceed 8 MiB even when each build receipt fits. Keep v0.1.0 for its saved runs and use separate install directories. Revert the release commit, then any source upgrades in reverse dependency order if a source rollback is authorized. See the packaged install guide for the legacy checksum caveat.
Pending approvals [V] “approve U7” unlocks the U7 evaluation. U8 is separate and follows U7. Configurable caps, paid work, hosted plugin updates, and future pushes each need explicit authorization.
```

## Limit design

- [V] The controller caps complete serialized receipts at 4 MiB. Native submission checks the encoded size before writing a receipt. Escaped JSON text, paths, and metadata all count. Evidence referenced only by digest need not be embedded. [Controller](../skills/method/bmad-deliver/scripts/deliver.py) and [native helper](../skills/method/bmad-deliver/scripts/native_host.py).
- [V] The standard worker reads job JSON up to 8 MiB. A mixed verification job can include artifacts from two builds, the original request, and verification metadata. The native helper's job reader currently allows 16 MiB. [Standard worker](../skills/method/bmad-deliver/scripts/codex_worker.py) and [run record](../skills/method/bmad-deliver/references/run-record.md).
- [I] These bounds limit how much JSON a reader buffers and parses and how large persisted payloads can become. The numeric defaults can be configurable. Suggested switches are `--receipt-max-mib` and `--verification-job-max-mib`, with 4 and 8 as defaults. If approved, persist effective values per run, validate encoded byte counts consistently at readers and writers, and account for both builds' content and metadata when setting the job budget. Resume existing runs with legacy defaults. Review the separate native-job and state reader limits before allowing higher presets.

## Inventory

- [Upgrade plan](delivery-review.md) and [historical handoff](handoff.md) retain the roadmap and baseline evidence.
- [Autonomous Delivery Beta v0.2.0](delivery-beta/autonomous-delivery-beta-0.2.0.zip) is the portable plugin archive. SHA-256 `1c082c88268d3ef88ab6a733fe4ed66e49a0cb7827c32965dbb4a87a592cc980`. [Checksum file](delivery-beta/autonomous-delivery-beta-0.2.0.zip.sha256).
- [Verification bundle](delivery-beta/u2-u6-verification.zip) contains source snapshots, tests, recorded build inputs, verification results, and an internal checksum manifest. SHA-256 `90520dcecf1f7d3324ddb3ddc9f73a3066069699113a48a9cf063845d886382c`.
- [v0.1.0 plugin](delivery-beta/autonomous-delivery-beta.zip), [legacy standalone skill](delivery-beta/bmad-deliver-beta.zip), and their adjacent checksums are the historical baseline.
- [Skill source](../skills/method/bmad-deliver/SKILL.md), [standalone packager and install guide](../tools/package_delivery_beta.py), and [packaging tests](../tools/tests/test_package_delivery_beta.py) are tracked in Git. The plugin contains the payload manifest at `skills/bmad-deliver/assets/native/SOURCE.json`.
- [V] Source commits in order from U2 through U6 are `88746afa`, `38844fb3`, `99ff7432`, `25d99db7`, and `e7dd16cd`.

## Verification

- [V] Strict skill validation passed all 33 skills. `git diff --check` passed.
- [V] `uv run --frozen python -B -m pytest -n 3 -q` exited 0 with one skip for optional `tiktoken`.
- [V] The plugin archive passed ZIP integrity and all 43 skill members matched the new standalone beta build byte for byte. Two plugin wrapper builds were identical. Its extracted checker passed with `--native --codex` and verified 42 installed files. The extracted controller printed CLI help.
- [V] From `.ai-context/delivery-beta`, run `sha256sum -c autonomous-delivery-beta-0.2.0.zip.sha256` to check the plugin, verification bundle, and this handoff.
- [V] Cold-read check resolved which upgrades shipped, how to verify the release, and what still needs an owner decision.
