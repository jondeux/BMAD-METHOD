# Run a delivery

Use Python 3.11+ on a POSIX host and a new run directory whose parent already exists. The single command supports `start`, `status`, and `resume`. Run the script by its path from the workspace, substituting the installed skill directory as needed.

```bash
python3 skills/method/bmad-deliver/scripts/deliver.py start _bmad-output/check-in-run --request request.json --codex
python3 skills/method/bmad-deliver/scripts/deliver.py status _bmad-output/check-in-run
python3 skills/method/bmad-deliver/scripts/deliver.py resume _bmad-output/check-in-run
```

`--codex` uses the configured Codex CLI provider for a fresh read-only session per stage. Add `--model` or `--effort` if the selected provider supports those values. When the CLI rejects its configured default, select an explicitly supported model. The live test used `--model gpt-5.6-luna --effort medium`. Source text is sent to that provider. Use authorized source material. The selected model and provider configuration are subject to the host. A local integration can instead supply `--worker /path/to/trusted-executable`. Use [native dispatch](native-host.md) when the run must execute Build Auto or Product Brief through an authorized host. Use `--verify-worker /path/to/trusted-checker` to keep routing and building with the main worker while delegating the verification phase to an independent local checker. It receives the same job and receipt paths, checks the actual generated files, and consumes one call. Give the checker an execution environment suitable for the artifact language.

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

## Resume and verify

| Status | Action |
| --- | --- |
| `approval-required` | Review the route and use `resume --approve PROPOSAL_ID` when the owner approves it. |
| `answer-required` | Use `resume --answer 'OWNER ANSWER'` once the owner supplies the answer. |
| `interrupted` | Inspect the saved attempt and use `resume --retry` to spend another worker call. |
| `budget-exhausted` | Use `resume --budget NEW_TOTAL` after the owner extends the cap. |
| `complete` | Read the files under `artifacts/` and the verification results from `status`. |

A bare resume reuses committed receipts and advances stages with available budget. If the run stopped at the cap after an independent checker returned a failed result and you repaired that checker, use `resume --reverify --budget NEW_TOTAL` to test the same build again. The earlier attempt remains in the run record. Every dispatch consumes one unit, including verification, failed attempts and retries. A successful route, build and verification need three calls. The runner enforces the call cap before dispatch and a per-call timeout. Billed tokens are provider usage. The call cap is independent of token count. An executable check records the observed result. Verification failure or inapplicability leaves the check open. The controller allocates a repair attempt if budget remains. It publishes only when every check passes.

## Persisted record and worker interface

The run contains a versioned `state.json`, `attempts/<number>/job.json`, the worker log and any committed `receipt.json`. State stores the original request, current budget and its extensions, phase, dispatches, owner answers and approvals, B replacements, verification results and published file hashes. The run lock also covers a subprocess that outlives the controller. A complete receipt is replayable. A missing or malformed receipt stops for an explicit retry.

A trusted worker receives two arguments, the absolute job path and absolute receipt path, and runs in the attempt directory. It reads the job and writes a single JSON receipt using a temporary file, fsync and atomic rename. Treat the executable and its provider as part of the trusted environment. Limit effects to this delivery. The controller publishes UTF-8 files into the run directory when verified. Each receipt is at most 4 MiB.

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

- For `route`, return `status: ok`, a `deliverable`, `workflows` array, `rationale`, and `assumptions` array. An assumption must be reversible. Cite why a workflow is needed.
- For `build`, return `status: ok` and `artifacts`, each with relative `path` and full `content`. On repair the job contains the prior snapshot and verification. To propose replacement use `status: replace` and the route fields with new evidence in the rationale.
- For `verify`, return `status: ok` and `checks`, with `id`, `status` (pass, fail or inapplicable) and observed `evidence` for every original ID. The verifier executes or inspects the snapshot. The runner validates the receipt and trusts the verifier's reported observations.
- For a question requiring the owner, return `status: blocked` and `question` during any phase. The answer is persisted before a new call.

Exit status 0 indicates completion or a successful status query. Status 2 indicates a run stopped at a gate. Status 1 indicates an invocation, storage or locking error. Only use this prototype for run-local artifacts. Installation, deployment, and integration with an existing worktree are separate actions.


## Native Build setup

A BMad renderer and its skill templates must come from the same BMad revision. In a source checkout, match the checkout's `skills/core-tools/bmad/scripts/render_skill.py` with its own `skills/method/bmad-build` or `skills/method/bmad-build-auto` directory. Use the renderer from the installed suite when running installed templates. Older preview templates use expressions such as `{{.implementation_artifacts}}` and can fail with `unexpected '.'` when paired with the checkout's Jinja renderer.
