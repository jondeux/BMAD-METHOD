---
title: "Autonomous Delivery plugin manual"
description: "Use Autonomous Delivery Beta v0.4.1 to route raw intake, approve a delivery plan, verify artifacts, and resume saved runs."
---

Use `bmad-deliver` to turn an idea, brainstorm, research excerpt, or other authorized material into verified local files. Intake stays in the same saved run that builds, verifies, and publishes the result. Version 0.4.1 adds a chat questionnaire for owner decisions before dispatch.

:::tip[First run]
Open the project in the coding workspace that has Autonomous Delivery Beta v0.4.1 enabled. Invoke `$bmad-deliver`, give it one small outcome, name the files or deliverable, supply observable checks, and answer the questionnaire. Ask it to return the saved run path, the artifact paths, and the check results.
:::

## 1. Verify your installation

Native delivery requires a POSIX host, Python 3.11 or later, `uv`, and a workspace agent that can run native jobs and their review steps. For subscription-backed Codex intake, the workspace also needs the `codex` CLI and a compatible signed-in subscription session.

1. Open the plugin picker in the workspace you will use. Confirm that **Autonomous Delivery Beta** is enabled at **0.4.1** and that its `bmad-deliver` skill is available. Select it using the name shown by your workspace if it displays a plugin-qualified name.
2. In the Codex CLI, use `codex plugin list --json`. Find the matching delivery entry under `installed` and check its version and `enabled` value. For an entry from this project's local marketplace, use `codex plugin list --marketplace bmad-delivery-local --json`. If the picker lists an earlier release, refresh or reinstall from a source that offers 0.4.1 and verify again in a fresh session.
3. If you need a standalone install, find the v0.4.1 standalone ZIP and checksum in the checkout under `.ai-context/delivery-beta/`. Verify the ZIP, extract it in a new directory, and follow its `INSTALL.md`. The portable plugin ZIP is for hosts that install plugin packages. [v0.4.1 release files](https://github.com/jondeux/BMAD-METHOD/tree/7aa2e8f4491563872a55872632e81f97c04960de/.ai-context/delivery-beta)

With the installed skill directory known, run these commands against that copy. For a project-local standalone install, the skill directory is `.agents/skills/bmad-deliver`. For a plugin install, use the `bmad-deliver` skill directory bundled with the selected plugin.

```bash
DELIVERY_SKILL=/absolute/path/to/bmad-deliver
DELIVERY="$DELIVERY_SKILL/scripts/deliver.py"
python3 -B "$DELIVERY" --version
python3 -B "$DELIVERY_SKILL/scripts/check_install.py" --native --codex
```

Expect `0.4.1` and a compatible install. Omit `--codex` when checking an install you will use without the Codex launcher.

## 2. Give Delivery a usable intake

1. State the immediate outcome. For example, decide whether to trial a policy, produce a working local prototype, or extract cited notes from supplied evidence.
2. Name the deliverable and output class when you know them. Choose `code`, `non-code`, or `mixed`. Say whether a specific filename or document type is required.
3. Choose an authority mode and give the applicable scope limits. State what the agent can decide and which decisions need you.
4. Give at least one observable acceptance check and a positive dispatch cap. Name the trusted local checker if a check must run code, open a browser, or exercise an interface.
5. Include authorized plain-text excerpts or transcripts. Identify the source of each excerpt when a check must cite it. For a PDF, image-based scan, recording, or video, obtain readable excerpts or a transcript through an authorized tool first if the workspace cannot read it.

The input format and the requested outcome can point to different routes. A literature review to summarize goes to `sources`. A Product Brief informed by that review goes to `thinking/product-brief` with the excerpts as context. Source text can inform the result. Your message supplies the actual approval and scope.

:::note[Copyable first prompt]
> `$bmad-deliver` Use Mode C. Deliver a Product Brief on whether to trial an automatic release policy for unused library room bookings. Use only this synthetic note as evidence: “The simulation excluded false releases. The facilities director owns the trial decision.” Verify that the brief states the simulation limitation, identifies the decision owner, and clearly labels the trial as proposed. Keep it as a local draft. Cap the run at three dispatches. Return the saved run path, artifact path, and the evidence for each check.
:::

### Answer the chat questionnaire

Once the outcome and source material are usable, the skill opens the current chat’s questionnaire when the host and interaction mode provide it. Choose a delegation mode and host, then confirm the applicable model and effort, dispatch cap, and deliverable size. A setting you already supplied can be offered as a choice to keep. The run waits for your submitted choices.

Size controls the scope of the returned package within the existing byte limits. Choose required files only, the full agreed package, or a custom size target. If an executable check or the selected host needs a trusted checker and a usable one is missing, the skill asks for it separately. When the host or interaction mode has no questionnaire, the skill presents the choices in chat and waits for your reply.

A saved run keeps its existing decisions. If it pauses, answer only the question shown by its status.

## 3. Read the route and capability before approving work

Delivery uses the immediate goal to select a route and, when needed, a **subtype**. The subtype identifies the kind of work within that route. A classified route can pause at `capability-unavailable` when this release lacks its execution handler.

| Route | Bring this | v0.4 execution |
| --- | --- | --- |
| `sources` | Documents, PDFs, literature reviews, transcripts, or other sources to process | Identifies source ingestion, research synthesis, or a maintained document. Each pauses for a separate workflow. |
| `unclear` | A vague idea, alternatives to explore, or a research gap | Identifies brainstorming, pressure testing, or research. Each pauses for a separate workflow. |
| `thinking` | A decision or a named document to deliver | Runs `product-brief` for an approved Product Brief. PRDs, architecture, UX, and other document types require their own workflows. |
| `trivial` | An exact, low-risk mechanical edit with a simple check | Runs `run-local-code` for an isolated code artifact. Edits applied directly to a worktree require a separate workflow. |
| `small` | A focused implementation that fits one session | Runs `code` or `code-and-product-brief`. The mixed path builds code first, then runs Product Brief. |
| `existing` | A request to establish or inspect repository context | Identifies `project-context`. A focused implementation may instead select `small` and use repository facts as context. |
| `epic` | One outcome that needs several independently verifiable stories | Identifies epic planning or execution. Both require a separate workflow. |
| `project` | Several epics, teams, or shared decisions to coordinate | Identifies initiative planning or execution. Both require a separate workflow. |

A custom guide, PRD, or report paired with code is a different delivery contract from code plus a Product Brief. Agree on any change to the deliverable at the gate. Native outputs are run-local UTF-8 text files. Binary deliverables, deployment, direct worktree integration, and sending files to others require their own authorized workflow. [v0.4.1 route catalog](https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/intake-routes.json)

For a raw idea, use [idea exploration](../plan/explore-and-validate-an-idea.md) to settle the direction where needed. If a decision needs evidence, use [Deep Recon](../plan/research-a-decision.md) to draft a research prompt and process the report you bring back. Take the saved intent and research into the [appropriate planning artifact](../plan/define-requirements-and-a-specification.md). Bring the approved requirements and checks to Delivery when the project is ready to build. In v0.4.1, the discovery, research, and planning handoffs use standalone BMad skills.

## 4. Choose how much to delegate

| Mode | Tell Delivery | What you decide |
| --- | --- | --- |
| **A · Approve a proposal** | “Propose the route, exact deliverable, and check plan, then wait.” | Review the proposal's outcome, output class, scope, and checks. Approve the current proposal ID to authorize the build. |
| **B · Delegate within limits** | “Deliver this outcome within these limits and exact permitted output classes or deliverable names.” | Use exact allowlists for restrictions that the controller must enforce. Review a proposal when the owner's labels and limits leave the choice open. |
| **C · Keep the named deliverable** | “Deliver this specific artifact for this outcome.” | Keep the agreed name and checks. Explicitly approve any eligible change the controller proposes. |

If you supply an intake correction, read the new proposal before approving. The approval is bound to its saved intake revision. Once the request is frozen, use a new linked request for a materially different outcome, scope, or acceptance contract.

:::note[Copyable code prompt]
> `$bmad-deliver` Use Mode A. Propose a run-local Python file named `capacity.py` with `remaining(capacity, booked)` for nonnegative integers. It returns seats remaining, floored at zero. Require executable checks for `remaining(10, 6) == 4` and `remaining(4, 6) == 0`. Ask me for the trusted local checker if none is available. Wait for my approval before the build. Keep the run local and cap it at three dispatches.
:::

:::note[Copyable prompt for an already-scoped mixed package]
> `$bmad-deliver` Use Mode B. Deliver `capacity.py and Product Brief` for a local room-capacity trial. I allow only the `mixed` output class and this exact deliverable label. Implement the capacity function from the code example. The brief must name the facilities director as the decision owner and describe the trial as proposed. Verify the two capacity cases with my trusted local checker and cite the brief lines for the two document checks. Keep all files local and cap the run at four dispatches.
:::

## 5. Write checks that can be verified

Give each check one behavior and a stable name. Delivery binds the verdicts for typed checks to the exact artifact bytes it verified.

| Check type | Example | Evidence to expect |
| --- | --- | --- |
| `executable` | Opening the local game lets a player finish a round, see an accurate score, and restart. | A trusted local checker runs the relevant runtime or browser and reports the command, exit status, and observed result. |
| `source-inspection` | The brief says that false releases were excluded and identifies the named decision owner. | The verifier cites exact artifact lines. If the claim must be traced to original material, include its authorized excerpt and require an intake citation. |
| `judgment` | The recommendation separates observed findings, assumptions, and open questions. | A reasoned assessment against those criteria. The result is labeled as judgment. |

Use a checker you trust to exercise the behavior. A browser can be part of verification when the available local checker can drive it and report what it observed. For a code-server Live Browser test, specify the browser, the launch steps, and the interaction that proves each behavior. [Verification contract][delivery-verification]

## 6. Choose the host, model, budget, and size

**Codex.** Use the existing signed-in ChatGPT subscription session. Run `codex login status` to check sign-in, then verify included allowance, zero purchased-credit balance, and automatic reload off in the account's usage settings before confirming a plan-only run. Repeat that check for the serving workspace and its review agents. A signed-in Codex intake-to-artifact smoke has been recorded. [Codex authentication](https://learn.chatgpt.com/docs/auth) · [OpenAI credit behavior](https://help.openai.com/en/articles/12642688-using-credits-for-flexible-usage-in-chatgpt-personal-plans)

**Claude Code preview.** Use the authorized workspace and a trusted local verifier. Check `/status` and `/usage` in that session and disable usage credits. Use its workspace to serve the intake and native jobs. The v0.4 Claude path has deterministic coverage. [Claude Code commands](https://code.claude.com/docs/en/commands) · [Claude usage credits](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans)

| Control | How to use it |
| --- | --- |
| Model and effort | For the built-in Codex adapter, pass `--model MODEL` and `--effort low\|medium\|high\|xhigh` on start when supported. Confirm the serving workspace model and effort separately if they differ from the settings for the Codex adapter. In Claude Code, choose the model and effort in that session. |
| Dispatch budget | A first-pass run normally needs three dispatches for code or a Product Brief, or four for code plus Product Brief. This includes intake classification and verification. An explicit owner route can skip the classification call. |
| Retries and timeout | Every new dispatch counts, including failed attempts and retries. The default per-call timeout is 600 seconds. Set `timeout_seconds` in the intake envelope when the workflow needs a different limit. |
| Subscription allowance | Included usage is checked separately from the dispatch cap. Failed preflight uses zero dispatches. A refusal after a dispatch still counts. Nested review calls use the serving host's allowance. |
| Payload size | An intake envelope can be up to 512 KiB. A serialized receipt, including metadata and files, can be up to 4 MiB. The standard Codex job reader allows 8 MiB, including the combined artifacts in a mixed verification job. Keep required evidence and reduce optional payload when needed. |
| Language | Set `communication_language` and `document_output_language` in the intake envelope for native workflows. Each defaults to English. |

## 7. Start and inspect a run from the terminal

Most users can invoke the skill in chat. For a controlled terminal launch, record the settings yourself and run the controller from the authorized workspace agent so it can serve its native jobs. Use the installed path from [Verify your installation](#1-verify-your-installation).

Save the following as `library-intake.json`. It leaves route selection to the classifier and gives the owner-authorized scope explicitly.

```json
{
  "text": "Deliver a Product Brief on whether to trial automatic release for unused library room bookings.",
  "sources": [
    {
      "id": "simulation-note",
      "excerpt": "The simulation excluded false releases. The facilities director owns the trial decision."
    }
  ],
  "kind": "non-code",
  "authority": {
    "mode": "C",
    "outcome": "Decide whether to trial automatic release for unused bookings",
    "deliverable": "Product Brief",
    "limits": ["Keep the brief local", "Preserve the simulation limitation"]
  },
  "checks": {
    "limitation": {
      "kind": "source-inspection",
      "behavior": "The brief says the simulation excluded false releases",
      "required_sources": ["artifact", "intake"]
    },
    "owner": {
      "kind": "source-inspection",
      "behavior": "The brief identifies the facilities director as the trial decision owner"
    }
  },
  "budget": 3
}
```

From the project directory, choose an unused run path. Use `--confirm-plan-only` only after verifying the actual serving account and included allowance.

```bash
mkdir -p _bmad-output
RUN="$PWD/_bmad-output/library-delivery-01"
python3 -B "$DELIVERY" start "$RUN" --intake library-intake.json \
  --codex --native-host --confirm-plan-only &
```

After the controller saves the run, inspect its status.

```bash
python3 -B "$DELIVERY" status "$RUN"
```

When a native job appears, the authorized workspace agent serves the workflow named in `pending_attempt.workflow` using `pending_attempt.job`. Let the skill prepare the workspace and submit the result. This example uses source checks that the guarded Codex worker can verify. For an executable check add `--verify-worker /absolute/path/to/trusted-checker` at launch. For the Claude preview use `--intake-host claude` in place of `--codex` and supply the local checker. [Native host instructions][delivery-native-host] <!-- freshness-example: claude -->

For manual selection without a classifier, specify both the authorized `route_id` and `subtype` in the envelope and use trusted local native and verification workers. Plain UTF-8 text is also valid raw intake. JSON is useful for recording exact checks and limits. Use `--request FILE` when you already have a complete structured request in the [legacy request format][delivery-request].

## 8. Resume the same run at a gate

Keep the saved run path. In a fresh workspace session, invoke `$bmad-deliver` and tell it to inspect that path before resuming. From a terminal, run `python3 -B "$DELIVERY" status "$RUN"` and follow the recorded `next_action`.

| Status | What to do in the saved run |
| --- | --- |
| `dispatched` | Let the worker finish. If a native job is waiting, ask the authorized workspace agent to serve the reported job. Resume if the controller stopped. |
| `answer-required` | Answer the controller's question or supply the missing material. Use `resume "$RUN" --answer 'Your answer'` for a reply or `--intake-update owner-update.json` for structured fields before the request freezes. |
| `approval-required` | Check the proposed route, scope, output, and acceptance behaviors. Approve the current ID with `resume "$RUN" --approve PROPOSAL_ID`. |
| `capability-unavailable` | Read the route and reason. Before request freeze, agree on a supported route or use the indicated separate workflow. If a worker is missing, attach the trusted native worker or verifier identified by status. |
| `subscription-paused` | For a managed Codex or Claude run, verify the account settings again and use `resume "$RUN" --confirm-plan-only`. For a pending local intake allowance gate, use an owner intake update after confirming availability. |
| `interrupted` | Use bare `resume "$RUN"` first so the controller can adopt any valid saved receipt. If a new attempt is needed, use `--retry` within the approved budget. |
| `budget-exhausted` | Review what is pending and explicitly approve a higher total if needed. Use `resume "$RUN" --budget NEW_TOTAL`. Extending from three to four authorizes one additional dispatch. |
| `checker-fault` | Fix the independent checker and use `resume "$RUN" --reverify` to verify the saved build again. Add `--budget NEW_TOTAL` if your approved cap needs to grow. |
| `complete` | Open the published files in `artifacts/` and inspect the original check results in status. |

If the proposed subtype is wrong and the request is still pending, supply an authorized update file. For example, `{"route_id":"thinking","subtype":"product-brief"}` selects the Product Brief workflow when it matches the agreed outcome. If the source is unreadable, provide its readable excerpts in the update. Keep the original checks unless you explicitly authorize a new contract.

## 9. Review the result and share diagnostics

At completion, ask for the run path, relative file paths under `artifacts/`, the verdict and evidence for every original check, and dispatches consumed. Open or run the files yourself for the acceptance behaviors that matter most. Record whether the first delivery is usable and name any change you need.

For troubleshooting, refresh the local telemetry and send that JSON to the agent diagnosing the issue.

```bash
python3 -B "$DELIVERY" telemetry "$RUN" > delivery-telemetry.json
```

Telemetry includes route and gate labels, relative timings, dispatch and retry counts, and observed usage where available. It excludes task text, owner answers, raw errors, custom paths, artifact contents and hashes, and credentials. Keep the run directory, raw logs, and receipts private. Telemetry stays local until you share it. [Telemetry contract][delivery-telemetry]

## 10. Update or roll back without losing saved runs

Install each version at a separate path and retain the path used by its saved runs. Saved workers can reference absolute paths. Back up the old runtime before an in-place marketplace upgrade. The local Codex installer can prune older versions from its cache. Verify that the old path still works after upgrading. Check both the local and private hosted entries in fresh Codex Settings. Uninstall older active versions by their exact identities and verify that only the current version is installed. Keep rollback artifacts outside the active plugin list. Verify an archive against its published SHA-256 digest, run that version's own compatibility checker, then open a representative saved run with its controller.

The v0.4.1 controller passed replays of v0.3.0 structured code, Product Brief, and mixed runs. It also read v0.4.0 raw state without changing the saved bytes. Keep the corresponding v0.4 runtime available for each raw-intake run. The v0.3.0 controller refuses the newer raw protocol. To roll back new starts, use the verified v0.3.0 install in a separate project. [Pinned runtime and rollback procedure][delivery-rollback]

[delivery-verification]: https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/run-record.md#acceptance-checks
[delivery-native-host]: https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/native-host.md
[delivery-request]: https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/run-record.md#request
[delivery-telemetry]: https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/run-record.md#shareable-telemetry
[delivery-rollback]: https://github.com/jondeux/BMAD-METHOD/blob/7aa2e8f4491563872a55872632e81f97c04960de/skills/method/bmad-deliver/references/run-record.md#pin-the-runtime-for-saved-runs
