# Run a delivery

## Beta capabilities

Use Python 3.11 or later on a POSIX host. For native delivery, use `uv` for workflow dependencies and an authorized workspace agent that can serve native jobs, run workflow tools, and launch workflow review subagents. The prepared native workspace uses English for communication and documents. A trusted executable integration can serve native jobs with `--native-worker`.

| Request kind | Native workflow |
| --- | --- |
| `code` | Build Auto |
| `non-code` | Product Brief |
| `mixed` | Build Auto, then Product Brief |

Native delivery covers these workflows. Review supports their internal steps. For a request requiring another native workflow, agree on a supported route or arrange the additional workflow separately before dispatch.

The controller publishes run-local UTF-8 text files under `artifacts/`. Each complete serialized JSON receipt can be at most 4 MiB, including all artifact contents, paths, and metadata in that receipt. Leave room for JSON escaping. The `--codex` adapter reads up to 8 MiB per job. When it verifies a mixed run, the job includes both builds' artifacts, the original request, and job metadata. Size the combined output for that limit. Binary deliverables, deployment, and integration into an existing worktree require a separate workflow.

## Start, inspect, and resume

Use a new run directory whose parent already exists. For a native run, start the controller in the background so the workspace agent can [serve its jobs](native-host.md). The commands below assume the project has an installed skill and a `request.json` file. In a source checkout, set `delivery` to `skills/method/bmad-deliver/scripts/deliver.py`.

```bash
delivery="$PWD/.agents/skills/bmad-deliver/scripts/deliver.py"
mkdir -p _bmad-output
python3 "$delivery" start _bmad-output/check-in-run --request request.json --codex --native-host &
```

Once the controller and workers stop, use `status` to read the saved result. To continue a native run when its gate permits, resume the same run from the workspace agent and serve its pending jobs.

```bash
python3 "$delivery" status _bmad-output/check-in-run
python3 "$delivery" resume _bmad-output/check-in-run &
```

Choose `--codex` or `--worker /path/to/trusted-executable` to supply a worker, including when using native builds. `--codex` requires the `codex` executable on `PATH` and a configured provider. It opens a fresh read-only session for each stage it handles. Use source material authorized for that provider. Add `--model` or `--effort` when supported by the provider.

The controller dispatches verification after the native builds. For executable checks, ensure the verifier can run the required commands. Use `--verify-worker /path/to/trusted-checker` to delegate verification to an independent local checker with access to the required runtime. It receives the job and receipt paths, checks the generated files, and consumes one dispatch.

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
    "limitation": "The brief says the simulation omitted false releases",
    "decision": "The brief records a proposed decision and identifies its owner"
  },
  "budget": 5,
  "timeout_seconds": 600
}
```

Use `code`, `non-code`, or `mixed`. The intake kinds are `idea`, `literature`, `brainstorm`, and `forge`. Set a positive worker-call budget and provide at least one acceptance check. The original checks are mandatory. Use stable IDs. For B supply explicit delegation limits. For C supply the named deliverable. For A request a specific proposal and approve it before building. When acceptance or authority requires information from a real stakeholder, the run waits for the owner.

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
| `approval-required` | Review the route and use `resume --approve PROPOSAL_ID` when the owner approves it. |
| `answer-required` | Use `resume --answer 'OWNER ANSWER'` once the owner supplies the answer. |
| `interrupted` | Inspect the saved attempt and use `resume --retry` to spend another worker call. |
| `budget-exhausted` | Use `resume --budget NEW_TOTAL` after the owner extends the cap. |
| `complete` | Read the files under `artifacts/` and the verification results from `status`. |

A bare resume reuses committed receipts and advances stages with available budget. If the run stopped at the cap after an independent checker returned a failed result and you repaired that checker, use `resume --reverify --budget NEW_TOTAL` to test the same build again. The earlier attempt remains in the run record. Every dispatch consumes one unit, including verification, failed attempts, and retries. A native run needs three dispatches for code or documents, or four for mixed delivery, when every stage succeeds on its first attempt. The runner enforces the call cap before dispatch and a per-call timeout. Billed tokens are provider usage. The call cap is independent of token count. An executable check records the observed result. Verification failure or inapplicability leaves the check open. The controller allocates a repair attempt if budget remains. It publishes only when every check passes.

## Persisted record and worker interface

The run contains a versioned `state.json`, `attempts/<number>/job.json`, the worker log and any committed `receipt.json`. State stores the original request, current budget and its extensions, phase, dispatches, owner answers and approvals, B replacements, verification results and published file hashes. An owner-approved Mode B replacement records its proposal ID in `approval`. The run lock also covers a subprocess that outlives the controller. A complete receipt is replayable. A missing or malformed receipt stops for an explicit retry.

A trusted worker receives two arguments, the absolute job path and absolute receipt path, and runs in the attempt directory. It reads the job and writes a single JSON receipt using a temporary file, fsync and atomic rename. Treat the executable and its provider as part of the trusted environment. Limit effects to this delivery.

The job has these fields at every phase:

| Key | Value |
| --- | --- |
| `attempt`, `phase` | Dispatch number starting at 1, and `route`, `build` or `verify`. |
| `request`, `route` | Original request and the selected route, which is `null` before selection. |
| `answers` | Owner responses as objects with `question` and `answer`. |
| `artifacts`, `verification` | The latest build's array of `path` and `content` objects, and the most recent verification results. Both start empty. Custom workers use the array to construct their own snapshot. The Codex adapter writes it to `snapshot/` and includes small snapshots in the prompt for direct inspection. |
| `verification_worker` | `independent` when an explicit checker is attached, else `default`. |
| `native_workflows`, `native_workflow` | With native dispatch enabled, the ordered workflows for this run and the assigned workflow for a build job. |
| `budget_remaining_after_dispatch`, `timeout_seconds` | Unused calls after the current dispatch, and the time limit for this call. |

Return one of the following receipts:

- For `route`, return `status: ok`, a `deliverable`, `workflows` array, `rationale`, and `assumptions` array. In Mode B, the route can also declare its output class in `kind`. An assumption must be reversible. Cite why a workflow is needed.
- For `build`, return `status: ok` and `artifacts`, each with relative `path` and full `content`. On repair the job contains the prior snapshot and verification. To propose replacement use `status: replace` and the route fields with new evidence in the rationale. In Mode B, a replacement can also declare its output class in `kind`.
- For `verify`, return `status: ok` and `checks`, with `id`, `status` (pass, fail or inapplicable) and observed `evidence` for every original ID. The verifier executes or inspects the snapshot. The runner validates the receipt and trusts the verifier's reported observations.
- For a question requiring the owner, return `status: blocked` and `question` during any phase. The answer is persisted before a new call.

Exit status 0 indicates completion or a successful status query. Status 2 indicates a run stopped at a gate. Status 1 indicates an invocation, storage or locking error. Only use this prototype for run-local artifacts. Installation, deployment, and integration with an existing worktree are separate actions.


## Native Build setup

A BMad renderer and its skill templates must come from the same BMad revision. In a source checkout, match the checkout's `skills/core-tools/bmad/scripts/render_skill.py` with its own `skills/method/bmad-build` or `skills/method/bmad-build-auto` directory. Use the renderer from the installed suite when running installed templates. Older preview templates use expressions such as `{{.implementation_artifacts}}` and can fail with `unexpected '.'` when paired with the checkout's Jinja renderer.
