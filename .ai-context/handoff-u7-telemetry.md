# Autonomous BMAD Delivery · project handoff · 2026-11-26

> Read this handoff and the U7 scorecard. Keep technical checks and owner verdicts distinct.
> Use v0.3.0 for new runs. Return local telemetry and preserve saved routes and original check IDs on resume.
> Publish to the handoff branch. Run the freshness routine after module moves, milestones, or a failing check.

```text
STATE BLOCK · Autonomous BMAD Delivery · 2026-11-26

Goal [V] Deliver local code, documents, or both through bounded, resumable work. Give the owner evidence for the artifacts and a shareable diagnostic. See the delivery skill and scorecard.
Success test [V] A completed run publishes only after its original checks pass. The packaged smoke run generated a diagnostic identical to an explicit export with zero planted private strings. See the verification bundle.
Stage completed [V] U1–U6 and the real U7 workspace run are verified. The owner accepted The Lantern House as delivered. v0.3.0 includes U7's evaluation guide, frozen cases, per-check checker, and automatic telemetry. The private release and local Codex installation were verified.
Terms [V] A waits for approval. B delegates within stated limits. C preserves a named deliverable. A job sends work and a receipt returns its result. A checker fault requires verifier repair. The canonical checkpoint is state.json. Telemetry projects selected fields from it.
Goals ranked [I] Preserve authority and original checks, make faults diagnosable without sharing task content, and measure owner value before growing native coverage. See the approval plan and scorecard.
Audience [V] Workspace owner and successor agents. Use concise results and concrete paths. Use POSIX and Python 3.11 or later for the beta.
Requirements [V] “try to minimize token spend but at the same time complete all runs”. “Commit and push only when I say "commit and push".” “DO NOT IMPLEMENT IT AS OF YET” covers configurable caps. The latest branch choice was “Push handoff branch only”. The sweep covers docs and memory plus its requested checker and CI test. See AGENTS.md.
Workflow and rubric [V] Freeze original checks and compare delivered versions. Preflight the actual browser viewer, recording command, and a decorated button before dispatch. Run the freshness routine after module moves, milestones, or failed checks. Compare status claims with Git and test results.
Decisions made [V] D1 keeps telemetry local and allowlisted. New runs write telemetry.json. Use the read-only telemetry command for a fresh export or an older run. D2 uses the private v0.3.0 release and verified local marketplace installation. v0.2.0 remains available for saved runs. D3 leaves the release branch at its existing revision per owner direction.
Rejected alternatives [V] Whole-run diagnostic sharing would expose inputs and artifacts. The two comparison arms use the same requirements and checker while keeping their outputs separate. Configurable caps remain deferred.
Assumptions to confirm [U] The real game supplied one owner verdict. A fresh matched direct run would measure incremental overhead and usefulness on this case.
Open questions [U] The owner can authorize the matched comparison and decide on U8 from that evidence. The operator can verify v0.3.0 launch through the account plugin interface in a fresh authorized session.
Verified [V] Full Python suite passed with one optional tiktoken skip. Node 24 built and tested the docs site. All three reference tests, the 52-document scan, docs-site link and sidebar checks, and all 33 strict skill validations passed. The plugin ZIP rebuilt byte for byte. Compatibility verified 46 installed files and hosted read-back matched 50 files. The earlier game completed 4/4 checks in six dispatches with two verifier retries and zero rebuilds. The owner requested zero material changes.
Still unverified [U] v0.3.0 account-interface launch, a matched direct comparison, and total nested native token usage. See the verification bundle and U7 scorecard.
Next actions [V] 1. Verify the handoff and release checksums. 2. Use v0.3.0 for new runs and share telemetry.json when diagnosing one. 3. If authorized, run the same game brief and check IDs through direct Build Auto and Product Brief in an isolated workspace before choosing U8.
Files and environment [V] See Inventory. This supersedes the live status in handoff-u2-u6.md. Its historical release, audit, and saved run evidence remain references.
Risks and rollback [V] A crash between the state save and diagnostic write can leave a stale sidecar. The read-only export reconstructs the saved state. Resume older runs with their original absolute runtime paths. Source rollback uses authorized Git reverts. Hosted rollback needs a separately authorized release.
Pending approvals [V] U8, live model use for the matched comparison, configurable caps, and further pushes are separate decisions. This handoff branch publication was authorized.
```

## Inventory

- [V] Portable v0.3.0, SHA-256 `2592542ae305445346261cf55cd88d986f9559e0ec29c8fdb2f7748cd7679a2c`. [Plugin archive](delivery-beta/autonomous-delivery-beta-0.3.0.zip)
- [V] Source inputs, test results, build manifest, and a redacted sample export, SHA-256 `1cfcf1d8997714c6eb6315dd0d98c7b865c7359dd609e03705c7b257470b31e2`. [Verification bundle](delivery-beta/u7-telemetry-verification.zip)
- [V] From `.ai-context/delivery-beta`, run `sha256sum -c autonomous-delivery-beta-0.3.0.zip.sha256` to verify both archives and this handoff. [Checksums](delivery-beta/autonomous-delivery-beta-0.3.0.zip.sha256)
- [V] The Lantern House verdict and comparison procedure are recorded with the frozen cases. [U7 scorecard](delivery-u7/scorecard.md)
- [V] The repository checker and human status review run after the specified events. [Freshness routine](../docs/reference/document-freshness.md)
- [V] The automatic telemetry file, fields, and read-only command are documented. [Telemetry contract](../skills/method/bmad-deliver/references/run-record.md#shareable-telemetry)
- [V] Cold read located the release, verification evidence, and approved branch. The next unresolved project decision is the comparison.
