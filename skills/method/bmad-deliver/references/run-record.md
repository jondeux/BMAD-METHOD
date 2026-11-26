# Run a delivery

## Beta capabilities

Use Python 3.11 or later on a POSIX host. For native delivery, use `uv` for workflow dependencies and an authorized workspace agent that can serve native jobs, run workflow tools, and launch workflow review subagents. The prepared native workspace uses the request's language settings and defaults each to English. A trusted executable integration can serve native jobs with `--native-worker`.

| Request kind | Native workflow |
| --- | --- |
| `code` | Build Auto |
| `non-code` | Product Brief |
| `mixed` | Build Auto, then Product Brief |

Native delivery covers these workflows. Review supports their internal steps. For a request requiring another native workflow, agree on a supported route or arrange the additional workflow separately before dispatch.

The controller publishes run-local UTF-8 text files under `artifacts/`. Each complete serialized JSON receipt can be at most 4 MiB, including all artifact contents, paths, and metadata in that receipt. The native helper checks the exact encoded size before submission. Reduce the text or omit optional outputs when the helper reports an oversized receipt. The `--codex` adapter reads up to 8 MiB per job. When it verifies a mixed run, the job includes both builds' artifacts, the original request, and job metadata. Size the combined output for that limit. Binary deliverables, deployment, and integration into an existing worktree require a separate workflow.

## Start, inspect, and resume

Use a new run directory whose parent already exists. For a native run, start the controller in the background so the workspace agent can [serve its jobs](native-host.md). The commands below assume the project has an installed skill and a `request.json` file. In a source checkout, set `delivery` to `skills/method/bmad-deliver/scripts/deliver.py`.

```bash
delivery="$PWD/.agents/skills/bmad-deliver/scripts/deliver.py"
mkdir -p _bmad-output
python3 "$delivery" start _bmad-output/check-in-run --request request.json --codex --native-host &
```

Use `status` while the controller is active or after it stops. It reads one saved snapshot and reports the pending attempt, its job path, the assigned native workflow when present, and the next action. A pending attempt can represent a stopped controller. To continue a native run when its gate permits, resume the same run from the workspace agent and serve its pending jobs.

```bash
python3 "$delivery" status _bmad-output/check-in-run
python3 "$delivery" resume _bmad-output/check-in-run &
```

Choose `--codex` or `--worker /path/to/trusted-executable` to supply a worker, including when using native builds. `--codex` requires the `codex` executable on `PATH` and a configured provider. It opens a fresh read-only session for each stage it handles. Use source material authorized for that provider. Add `--model` or `--effort` when supported by the provider.

The controller dispatches verification after the native builds. Use `--verify-worker /path/to/trusted-checker` for typed executable checks. The trusted local checker receives the job and receipt paths, exercises the artifact snapshot with the required runtime, and consumes one dispatch.

### Usage and support

`status` reports dispatches, elapsed time, recorded retries, and observed model tokens by attempt. For each built-in `--codex` call, the controller reads the latest usable cumulative `turn.completed` counters from the final 1 MiB of the log. New calls save the provider's JSONL event stream in `provider.jsonl` and diagnostics in `worker.log`. Older calls use the combined `worker.log`. Each observed attempt labels its source. Input includes cached reads. The noncached count is input minus cached reads. Cache writes and reasoning are breakdowns of the reported input and output. [Codex usage event implementation](https://github.com/openai/codex/blob/main/codex-rs/exec/src/event_processor_with_jsonl_output.rs)

`usage.coverage` is `observed` when every dispatch has a recognized final event, `partial` when any dispatch lacks one or falls back to an earlier observation, and `unavailable` when no usable counters were captured. Token totals cover the observed events. A missing optional counter is `null` for that attempt and its aggregate. Zero is a reported counter. Nested native usage is `unavailable` once a native workflow has dispatched. Independent checkers and custom workers have no built-in token reporting. Use provider billing for charges.

`elapsed_basis: last-saved-activity` measures wall time through the latest recorded dispatch, resolution, or publication. Attempt elapsed time measures from dispatch to the recorded decision, including any wait before a late receipt was adopted. An unresolved attempt or a historical run without a start time reports `null` for its duration. Retries count new dispatches for an interruption, a re-verification, or the start of an artifact repair. A late receipt that avoids the replacement leaves the retry count unchanged. The summary includes the number of attempts missing retry metadata.

Generate a local support summary with fixed status and worker labels, attempt numbers, and accounting figures.

```bash
python3 "$delivery" support _bmad-output/check-in-run > delivery-support.json
```

Keep the rest of the run directory private. It contains the job packets, receipts, raw logs, and artifacts.

### What workers receive

Every dispatched job contains the original request and checks, accumulated owner answers, the current route, any saved artifacts and verification feedback, and the remaining budget and timeout.

| Worker | Access to the job |
| --- | --- |
| `--codex` | The adapter sends the job text to the configured provider. Small artifacts travel inline and the provider session can inspect larger artifacts under `snapshot/`. |
| `--native-host` | The authorized workspace agent reads the job and serves the selected workflow using its configured tools and provider. |
| `--worker`, `--native-worker`, `--verify-worker` | The executable receives local job and receipt paths and inherits the controller's environment. Its downstream tool and provider use depends on its configuration. |

## Request

```json
{
  "kind": "non-code",
  "intake": {
    "kind": "literature",
    "text": "Synthetic trial note: the simulation omitted false releases. Draft a director decision brief."
  },
  "authority": {
    "mode": "C",
    "outcome": "Decide whether to trial a booking release policy",
    "deliverable": "Director decision brief",
    "limits": ["Local draft only", "Preserve the study limitation"]
  },
  "checks": {
    "limitation": {
      "kind": "source-inspection",
      "behavior": "The brief says the simulation omitted false releases"
    },
    "decision": {
      "kind": "source-inspection",
      "behavior": "The brief records a proposed decision and identifies its owner"
    }
  },
  "budget": 5,
  "timeout_seconds": 600
}
```

Use `code`, `non-code`, or `mixed`. The intake kinds are `idea`, `literature`, `brainstorm`, and `forge`. Set a positive worker-call budget and provide at least one acceptance check. The original checks are mandatory. Use stable IDs. For B supply explicit delegation limits. For C supply the named deliverable. For A request a specific proposal and approve it before building. When acceptance or authority requires information from a real stakeholder, the run waits for the owner.

### Native language settings

Set optional top-level `communication_language` and `document_output_language` strings in a new request. Use a nonempty single-line name such as `Français` or `Português (Brasil)`. The controller records the validated settings for native jobs. The native helper writes each value to the `[core]` table of the prepared workspace's `_bmad/config.toml`. An omitted setting defaults to `English`. Saved jobs from before language settings use their original English defaults. Pass the selected languages to native workflows that take their language from the conversation.

### Acceptance checks

Use a `kind` and a `behavior` for each acceptance check in a new request.

| Kind | Evidence for a pass |
| --- | --- |
| `executable` | The trusted checker reports the command it ran, a successful exit, and captured output from exercising the artifact. |
| `source-inspection` | The verifier explains the observation and cites an exact line range in the artifact snapshot. For checks that need the original source text, include it in the intake and set `required_sources` to `["intake"]` or `["artifact", "intake"]` as appropriate. |
| `judgment` | The verifier explains the criteria applied and its assessment. The result is labeled as judgment. |

Typed checks use version 2. Every verdict is tied to the SHA-256 map of the files sent to verification. A request whose checks are all strings still uses version 1, with the earlier prose receipt format. `status` labels version-1 verification as `legacy-prose`. Existing runs keep their version and their original checks. Use the current controller to resume a version-2 run.

### Mode B delegation

Mode B requires prose `limits`, structured `boundaries`, or both. Each allowlist is optional. When supplied, it must contain at least one entry. Use the owner's exact deliverable labels, including case and punctuation.

```json
{
  "mode": "B",
  "outcome": "Decide whether to trial a booking release policy",
  "limits": ["Local draft only", "Preserve the study limitation"],
  "boundaries": {
    "allowed_output_classes": ["non-code"],
    "allowed_deliverables": ["Director decision brief", "One-page decision memo"]
  }
}
```

The request's `kind` sets the output class for the whole run. It must be on `allowed_output_classes` when supplied. A route may declare its class with `kind`. Omitted route classes inherit the request class. When the class allowlist is present, the route must also exclude known native workflows for a different class. When both allowlists are present, the route must satisfy both. The controller stops a conflicting route before dispatch and records the error. To change a structured boundary, obtain owner authorization for a new request.

An allowlisted deliverable can proceed automatically. Without a name allowlist, an explicit `authority.deliverable` can identify a route under prose limits. If the proposed name differs from that label or the owner supplied no label, the controller saves a proposal and its reason for owner approval. A class-only boundary without prose permits any deliverable within the fixed class. Workers must follow the prose limits in every phase. The controller checks route fields and cannot infer a deliverable's contents or interpret prose limits from its name. Previously selected routes remain readable and retain their recorded decisions.

## Resume and verify

| Status | Action |
| --- | --- |
| `dispatched` | Use the pending job path to serve a workspace-hosted workflow. If the controller stopped, resume the saved run. |
| `approval-required` | Review the route and use `resume --approve PROPOSAL_ID` when the owner approves it. |
| `answer-required` | Use `resume --answer 'OWNER ANSWER'` once the owner supplies the answer. |
| `interrupted` | Use a bare resume to adopt a saved late receipt. Use `resume --retry` to request a new attempt. |
| `checker-fault` | Repair the checker and use `resume --reverify` to check the saved build. Add `--budget NEW_TOTAL` if the current budget is exhausted. |
| `budget-exhausted` | Use `resume --budget NEW_TOTAL` after the owner extends the cap. |
| `complete` | Read the files under `artifacts/` and the verification results from `status`. |

A bare resume reuses committed receipts and advances stages with available budget. If a valid late receipt has already committed, even `resume --retry` adopts that receipt first. If retry wins and has budget, it closes the old attempt to further submission. At the cap the pending attempt can still accept its receipt. Extending the budget rechecks that attempt before starting a replacement. Each new dispatch uses one unit, including verification, failed attempts, and retries. A native run needs three dispatches for code or documents, or four for mixed delivery, when every stage succeeds on its first attempt. The runner enforces the call cap before dispatch and a per-call timeout. Billed tokens are provider usage. The call cap is independent of token count.

A declared checker fault pauses in verification until the checker is repaired. Re-verification uses the same saved build. For older independent checker receipts that reported a failure as an artifact verdict, `resume --reverify --budget NEW_TOTAL` remains available after the run stops at its cap. Verification failure or inapplicability leaves the check open and the controller allocates a repair attempt if budget remains. It publishes only when every check passes and, in version 2, the files match the verified hashes.

## Persisted record and worker interface

The run contains a versioned `state.json`, `attempts/<number>/job.json`, the worker log and any committed `receipt.json`. State stores the original request, current budget and its extensions, phase, dispatches, owner answers and approvals, B replacements, verification results and published file hashes. An owner-approved Mode B replacement records its proposal ID in `approval`. The run lock covers controller writes and a subprocess that outlives the controller. Status reads the atomically replaced state without taking that lock. `attempt_version: 1` identifies the receipt and retry protocol. Existing records gain the marker on the next controller save. An attempt retired by retry while still missing its receipt is marked `superseded`.

A trusted worker receives two arguments, the absolute job path and absolute receipt path, and runs in the attempt directory. It reads the job and writes a single JSON receipt using a temporary file, fsync and atomic rename. Integrations that submit receipts outside the worker process use `commit_receipt(job_path, result)` from `deliver.py` to coordinate with retry. Treat the executable and its provider as part of the trusted environment. Limit effects to this delivery.

The job has these fields at every phase:

| Key | Value |
| --- | --- |
| `attempt`, `phase` | Dispatch number starting at 1, and `route`, `build` or `verify`. |
| `request`, `route` | Original request and the selected route, which is `null` before selection. |
| `answers` | Owner responses as objects with `question` and `answer`. |
| `artifacts`, `verification` | The latest build's array of `path` and `content` objects, and the most recent verification results. Both start empty. Custom workers use the array to construct their own snapshot. The Codex adapter writes it to `snapshot/` and includes small snapshots in the prompt for direct inspection. |
| `verification_worker` | `independent` when an explicit checker is attached, else `default`. |
| `verification_version`, `verification_id`, `artifact_sha256` | Typed jobs carry version `2`. A verify job also carries a unique ID and the complete path-to-SHA-256 map for its artifact snapshot. |
| `verification_artifact_sha256` | When present, identifies the earlier snapshot covered by the accompanying `verification` feedback. |
| `native_workflows`, `native_workflow` | With native dispatch enabled, the ordered workflows for this run and the assigned workflow for a build job. |
| `native_languages` | Validated language settings for a native build job. |
| `budget_remaining_after_dispatch`, `timeout_seconds` | Unused calls after the current dispatch, and the time limit for this call. |

Return one of the following receipts:

- For `route`, return `status: ok`, a `deliverable`, `workflows` array, `rationale`, and `assumptions` array. In Mode B, the route can also declare its output class in `kind`. An assumption must be reversible. Cite why a workflow is needed.
- For `build`, return `status: ok` and `artifacts`, each with relative `path` and full `content`. On repair the job contains the prior snapshot and verification. To propose replacement use `status: replace` and the route fields with new evidence in the rationale. In Mode B, a replacement can also declare its output class in `kind`.
- For `verify`, return `status: ok` and `checks`, with `id`, `status` (pass, fail or inapplicable) and explanatory `evidence` for every original ID. For typed checks also include `verification_version: 2`, the job's `verification_id`, and the exact `artifact_sha256` map at the receipt root. Include the check's declared `kind` in every row. Verify the hashes of the actual snapshot before testing or inspecting it.
- For a fault in an independent checker, return `status: checker-fault` and an `error` describing the checker failure. Omit `checks`. For typed checks include the same version, job ID, and artifact hash map as a verification receipt.
- For a question requiring the owner, return `status: blocked` and `question` during any phase. The answer is persisted before a new call.

For a typed executable pass the local checker must record an `observation` object in the check row. It contains the observed argument vector in `argv`, the integer `exit_code`, and captured strings `stdout` and `stderr`. Use empty strings for quiet streams. Keep relevant excerpts when full output would exceed the 4 MiB receipt limit. The checker should exit successfully on the expected behavior, including when it tests an expected failure. The controller treats the owner-configured checker as the source of execution observations.

For a typed source-inspection pass, add a nonempty `references` array to the row. Each reference uses `source: intake` for the original intake text or `source: artifact` with the exact artifact `path`. Specify the one-based `line_start`, optional inclusive `line_end`, and the verbatim `quote` with lines joined by LF. The controller resolves the range and matches the quote exactly. The verifier explains how the cited text supports the behavior. A failed or inapplicable check may omit its observation or references. A judgment row carries its evidence explanation and kind.

The status summary's `verification_artifact_sha256` identifies the snapshot for the latest typed verification rows. At completion it matches `artifact_sha256`, the manifest recorded at publication. Use that manifest to check any files edited after publication.

Exit status 0 indicates completion or a successful status query. Status 2 indicates a run stopped at a gate. Status 1 indicates an invocation, storage or locking error. Only use this prototype for run-local artifacts. Installation, deployment, and integration with an existing worktree are separate actions.


## Native Build setup

A BMad renderer and its skill templates must come from the same BMad revision. In a source checkout, match the checkout's `skills/core-tools/bmad/scripts/render_skill.py` with its own `skills/method/bmad-build` or `skills/method/bmad-build-auto` directory. Use the renderer from the installed suite when running installed templates. Older preview templates use expressions such as `{{.implementation_artifacts}}` and can fail with `unexpected '.'` when paired with the checkout's Jinja renderer.
