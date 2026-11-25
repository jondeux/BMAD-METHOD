# Autonomous BMAD Delivery · Tier L · 2026-11-25

> Read this handoff and [the delivery review](delivery-review.md), including the approval table.
> Use [the tested beta](delivery-beta/REPORT.md) for the implemented baseline.
> Check the owner's latest message for explicit upgrade approvals. Carry forward A/B/C authority and the original acceptance checks.
> Start at next action 1. Publication of this handoff authorizes documentation delivery only.

```text
STATE BLOCK · Autonomous BMAD Delivery · 2026-11-25
Goal [V] Take an idea, literature dump, brainstorming result or Forge handoff through applicable BMAD workflows to usable local code, documents or both without continuous owner input.
Success test [V] Retain original checks and owner authority through interruption. Verify delivered artifacts and account for dispatches within budget. See native mixed-run evidence.
Stage completed [V] Breadth pilot, native controller, installable beta and senior review. U1–U8 are proposals awaiting selection.
Terms [V] A requires approval of a proposal. B delegates within limits. C preserves a named deliverable. Simulated stakeholders may challenge assumptions. Only the owner grants authority.
Goals ranked [I] Honor delegation, prove the outcome, reduce unnecessary owner interruptions and spend.
Audience [V] Workspace owner and successor agents. Use concise results, runnable evidence and POSIX/Python 3.11+ for this beta.
Requirements [V] “try to minimize token spend but at the same time complete all runs”; “Commit and push only when I say "commit and push".” Follow AGENTS.md for release and branch policy.
Workflow and rubric [V] Preserve original checks, distinguish inventories and rehearsals from verified native execution, record blockers and compare the final artifact to its intended behavior.
Decisions [V] Keep modes A/B/C, adaptive routing as the goal, two native workflows in the current beta and a separate owner gate for scope or spend changes.
Rejected alternatives [V] Simulated approval for live owner decisions; counting a workflow name as execution; using an unverified relay for private inputs. See review and pilot archive.
Assumptions [I] Reliable delegation and acceptance will improve owner trust more than immediate catalog expansion. U7 tests this with independent owner judgment.
Open questions [U] Owner selects upgrades. For U7, owner selects a redacted real deliverable or synthetic-only assessment. For a later paid run, agent must verify model availability and cost before requesting approval.
Verified [V] Mixed run replayed a saved receipt, produced SQL and a brief, and passed six checks. Fresh-install brief passed four checks. Review reproduced Mode B boundary and weak verification acceptance and traced a retry gap. See delivery-review.md and the evidence archive.
Unverified [U] Real-owner first-pass acceptance, total nested spend and duplicate-free late-receipt recovery. U7, U5 and U4 respectively define proof.
Next actions [V] 1. Read the approval table and check owner's explicit selections. 2. If pending, wait for selections. 3. Once approved, execute only selected upgrades with their dependencies resolved; report proof after each. If scope, risk or cost changes, stop for approval.
Files/environment [V] Audited source 891b0063. See inventory below. This replaces the pilot-era next actions in the prior handoff.
Risks and rollback [V] Audit identifies implementation gaps and preserves historical evidence. Undo this documentation update with a Git revert of its commit. Each proposed code upgrade has its own rollback in the review.
Pending approvals [V] “approve all”, “approve U1, U3, U5”, or “approve all except U4” authorizes the specified selection. “change U2: …” requests revision. No live model spend is included.
```

## Inventory

- [Review and ranked upgrade plan](delivery-review.md) contains the verdict, F1–F11, all eight upgrades, dependencies, risks, budget, and approval table.
- [Review evidence](delivery-review-evidence.zip) contains the cited local reports and specification, plus the handoff test result and a member checksum manifest. Extract beside the review for its links. Links inside historical reports may refer to additional files in the original project's output tree.
- [Checksums](handoff-SHA256SUMS) cover this handoff, review and archive. Run `sha256sum -c handoff-SHA256SUMS` from this directory.
- Earlier evidence remains in [the pilot archive](pilot-evidence.zip) and [beta verification report](delivery-beta/REPORT.md).

[V] Cold-read check: the baseline is 891b0063, native execution covers Build Auto and Product Brief, and implementation awaits the owner's upgrade selection.
