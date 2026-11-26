# U7 Autonomous Delivery scorecard

The offline evaluation reproduced **13/13 original checks** across two saved v0.1.0 mixed runs. Both completed on the first verification attempt. Three new v0.2.0 synthetic requests passed schema validation. Their delivery outcomes, owner acceptance, and paired results against direct skills are unmeasured. The owner accepted **The Lantern House**, the real v0.2.0 mixed case, as delivered.

## Coverage

The denominator is the 32 entries from the pilot inventory, plus the repository's BMad Deliver skill and the bundled Product Brief entrypoint. The [offline replay](reproduce.py) emits all 34 rows with separate columns. A false flag means the scored archive supplied no evidence at that tier for that entry. The portable evidence cut includes the tracked pilot and live recovery archives and the v0.2.0 plugin archive.

| Tier | Observed | Evidence rule |
| --- | ---: | --- |
| Catalogued | 34/34 entries | Present in the original inventory or the verified v0.2.0 bundle additions. |
| Routed | 2/34 entries | Explicitly selected by name in a saved autonomous route. Build Auto and Product Brief. |
| Rehearsed | 5/34 entries | Workflow-specific records for Delivery, Build Auto, Product Brief, BMad Review, and the pilot's standalone Quick code review. The per-entry output names the archive member. |
| Natively completed | 2/34 entries | A terminal native dispatch through Autonomous Delivery with matching receipt and evidence file hashes. Build Auto and Product Brief. |
| Owner-accepted | 0 verdicts in these archives | A real owner judged the specific delivered version usable. The live workspace verdict is recorded below. |

The original blind pilot independently scored route predictions for **43 cases**. It recorded 40 passes and three partials. Its three targeted rechecks reused the partial cases. Route predictions use a case denominator. The table above counts catalog entries with explicitly named evidence. [Pilot archive](../pilot-evidence.zip) · [Live recovery archive](../delivery-beta/live-recovery-evidence.zip)

## Saved outputs

| Historical v0.1.0 case | Original checks passed | Checks with attributable replay evidence | First verifier passed | Dispatches | Owner inputs recorded | Controller resumes / build redispatches |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| Workshop capacity query and pilot brief | 6/6 | 6/6 (3 executed, 3 legacy text checks) | Yes | 4/4 | 0 | 1 / 0 |
| Inventory reorder rule and pilot brief | 7/7 | 7/7 (4 executed, 3 legacy text checks) | Yes | 4/4 | 0 | 1 / 0 |

The archived requests, controller states, and verification jobs agreed on every original check. The replay reproduced both verdict receipts and matched the published files, the native evidence hashes, and the pending build later accepted on the same attempt. Both cases used legacy receipts with no typed location fields. In each archived brief, line 12 supports the owner and pilot checks, and line 20 supports the excluded behavior check. Owner interruptions outside the controller, first-pass acceptance, material rework, and time to usable output remain unmeasured for both. [Trial report](../delivery-beta/LIVE-RECOVERY.md)

The pilot's direct Build Auto case **R5** passed three archived CLI tests again. It provides an unpaired code example. The portable evidence has zero matched direct-versus-autonomous pairs and no measured timing difference. The historical fresh-install library brief supplies an additional reported document example with 4/4 checks. It is outside the two-case replay denominator. [Direct example in pilot archive](../pilot-evidence.zip) · [Library brief report](../delivery-beta/REPORT.md)

## Frozen synthetic holdouts

The [requests and original criteria](holdout-cases.json) were frozen on 2026-11-26 at SHA-256 `26901df5db3663e8219228f34f86f0bfb3c94f5b18e466cb95111d3fc779a17b`. Review added a source-only check for the gallery brief before any holdout output was observed. All three requests passed v0.2.0 validation, and zero holdout delivery trials had started at this evidence cut.

| Case | Output | Original check count | Direct comparison | Delivery measurements |
| --- | --- | ---: | --- | --- |
| H-CODE | `preview_window.py` | 4 executable | Build Auto | Unmeasured |
| H-DOC | `gallery-label-pilot.md` | 5 source-inspection | Product Brief | Unmeasured |
| H-MIXED | `batch_flag.py` and `batch-review-pilot.md` | 2 executable + 3 source-inspection | Build Auto then Product Brief | Unmeasured |

Use the [executable checker](check_holdout_code.py) in the same approved local execution sandbox for both arms. SHA-256 `4864773dbe0064615daa9ccb8cc78520356ae9dc73a78bf0cc74955d3813b420`. It exercises the frozen vectors and accepts `--check ID` to record one executable observation with its own exit status. Configure a trusted `--verify-worker` to call it, save its actual observations, and attach the source-inspection verdicts required for mixed delivery. [Verifier receipt contract](../../skills/method/bmad-deliver/references/run-record.md#acceptance-checks)

```bash
python3 -I -B .ai-context/delivery-u7/check_holdout_code.py H-CODE /path/to/preview_window.py
python3 -I -B .ai-context/delivery-u7/check_holdout_code.py H-MIXED /path/to/batch_flag.py
```

For both arms, mark a source-inspection check as passing only when all its stated conditions are present and supported. Quote artifact lines for each claim. When the check also requires intake evidence, quote the matching input lines. For `source_only`, inspect the full brief for outcome, performance, and timing claims. Cite the input note and the artifact lines that delimit what was measured and what is proposed. Save missing or contradicted conditions as failed checks.

## Real mixed case

The owner's requirement is **“a memory palace game all built and can be run in browser.”** The owner chose a mixed code and document package. No existing run or game files accompanied the request.

Proposed package for the owner to confirm before a scored run. An original, self-contained `index.html` opens locally in the agreed browser. A `memory-palace-brief.md` contains the matching quick-start and player rules. The brief also names the game scope so the owner can judge whether the package is complete.

| Proposed check ID | First-delivery condition |
| --- | --- |
| `browser_start` | Open the delivered `index.html` in the agreed browser, start a new game, and enter its practice phase without a build step. |
| `recall_round` | Inspect a sequence of objects in named locations, advance to recall, submit answers, and see a score that agrees with the correct and incorrect answers entered. |
| `restart` | Restart after scoring and verify the score and progress reset for a new round. |
| `guide_matches` | The brief tells a new player how to launch, learn, recall, score, and restart, with controls that match the delivered game. |

Use a trusted local browser checker for the three behavior checks, and source-inspection evidence for the guide. Give both comparison arms the same approved brief, check IDs, browser, and artifact names. Direct delivery uses Build Auto for the game followed by Product Brief for the matching guide. The live workspace result records the owner's first-delivery verdict. The offline U7 replay starts zero provider calls.

### Live workspace result

On 2026-11-26, Autonomous Delivery v0.2.0 completed one native mixed run for **The Lantern House**. Build Auto produced the five-room game and Product Brief produced its guide. The independent checker confirmed the code-server embedded viewer was visible, completed all five rooms, deliberately missed one answer, verified the 4/5 score and correction, and restarted at the Entrance Hall. The guide matched the observed controls. **4/4 checks passed** with evidence bound to the published file hashes.

The run used six controller dispatches, including two local checker retries after harness faults. The owner approved each budget extension. The saved game and guide carried through both retries with zero rebuilds. First-verification success was 0/1 and eventual technical completion was 1/1. The local run is `_bmad-output/delivery-u7-memory-palace-INuxbC/run`. Its `artifacts/` contains the game and guide, and `attempts/6/browser-evidence.json` records the browser checks.

On 2026-11-26 the owner gave the verdict **“usable as delivered.”** First-delivery acceptance was **1/1** among cases with a real owner verdict. The verdict covers the published `index.html` and `memory-palace-brief.md` identified by the hashes in the run's `state.json`. The owner requested zero material changes. A matched direct run remains unmeasured.

## How to score a matched pair

1. Record the brief, original check IDs, allowed scope, host, browser or runtime, and worker settings before either arm starts. Give both arms fresh workspaces and the same input. For a direct mixed case, pass the code and its check result to Product Brief inside that arm and include this handoff in elapsed time. Keep either arm's output out of the other arm's input.
2. Run the same trusted checker and source-inspection rubric on both first deliveries. Save the artifact hashes, actual checker commands and exits, and exact source locators. Evidence coverage is the number of original checks with attributable evidence divided by all original checks. Record passing checks separately from evidence coverage.
3. Ask the real owner whether the **first delivered version** is usable as-is and what must change before use. Log each material fix required and each approval or clarification request between intake and delivery. Record whether the complete version needed any later rework. Controller retries and operator recoveries get their own counts.
4. Measure wall-clock time from submission of the frozen request to delivery of the first version the owner judges usable. Preserve start and delivery timestamps and record waits. Pause status, checker duration, and controller dispatch count cannot establish this time alone.
5. Record each arm's state as complete, failed, stopped, or pending. Report completed pairs out of all started pairs and identify both arms' outcomes for partial pairs. Report owner acceptance out of cases with a real owner verdict, and report how many eligible deliveries lacked one. Keep missing fields unmeasured and keep historical pilot results separate from holdouts.

For the memory palace case, retain the game and brief versions, browser and launch steps, final status, original check verdicts, and the owner's response **usable as delivered / changes needed**, with the required changes if any. Redacted excerpts and the content-free `support` summary can travel separately from the raw run directory. [Support contract](../../skills/method/bmad-deliver/references/run-record.md#usage-and-support)

## Reproduce this evidence cut

From the repository root, use Python 3.11 or later to run `python3 -B .ai-context/delivery-u7/reproduce.py`. It verifies the pinned archive digests and 84 archived member hashes, reruns the two saved verifications and the direct CLI tests in temporary directories, validates the three holdout requests against the packaged v0.2.0 controller, and prints JSON with the full coverage rows and saved-run metrics.
