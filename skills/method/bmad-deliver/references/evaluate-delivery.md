# Evaluate delivery

Use this guide to measure first-delivery acceptance and compare Autonomous Delivery with direct skill use. Freeze requirements before observing outcomes.

## Preflight the checker

Before dispatch, run the trusted checker on a small known-good fixture and a fixture that should fail. Confirm the launcher returns an observed verdict and that its failure output names the failed check. Keep executable checks independent of the build.

For browser checks, exercise the actual preview path and browser API once on the fixture. Confirm the editor viewer is visible if the request requires it. Start and end a recording, resolve and click a control with a decorated label, and assert its visible state change. When diagnosing a checker fault, fix and repeat this preflight before an approved re-verification. Reuse the saved build. [Resume contract](run-record.md#resume-and-verify)

## Compare the same request

1. Save the intake, deliverable names, and original acceptance IDs. Give both arms independent workspaces, the same host and criteria, and the same authorized checker. Run Build Auto directly for code and Product Brief directly for documents. For mixed work, hand the direct build output and its check result to Product Brief and include that handoff in the direct arm's time.
2. Preserve the first delivered artifact hashes, executable observations, and source locators. Record each arm's status, elapsed time to the first version the owner can use, owner interruptions, material rework, and the number of original checks with attributable evidence. Keep checker retries distinct from build rework.
3. Ask the owner whether the first delivery was usable as delivered or needs changes. Report owner acceptance against cases with a verdict, and list missing verdicts and incomplete pairs. Treat catalogue, routing, rehearsal, native completion, and owner acceptance as separate evidence levels. Scope claims to the runs measured.

The first real U7 mixed case was a browser memory game and its player brief. All four checks passed, and the owner accepted the delivered pair. Two local checker faults required recovery of the same build and two extra approved dispatches. The direct-skill comparison remains unmeasured.

## Frozen synthetic cases

The holdout requests cover code, a document, and a mixed package. Find `holdout-cases.json` and `check_holdout_code.py` under `references/` in the installed skill or under `.ai-context/delivery-u7/` in the source checkout. Run the checker in the approved local execution environment on a staged artifact.

```bash
python3 -I -B references/check_holdout_code.py H-CODE /path/to/preview_window.py
python3 -I -B references/check_holdout_code.py H-MIXED /path/to/batch_flag.py
```

Give the verifier wrapper `--check ID` when capturing an individual executable observation. A passing row then has its own successful command exit even when another check fails. For source-inspection checks, quote artifact lines and add intake lines when the request requires them. For the gallery case, check that the brief adds no unsupported timing or improvement claims. [Receipt contract](run-record.md#acceptance-checks)
