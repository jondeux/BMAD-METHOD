# Ask the owner through the chat questionnaire

Use this procedure for a new chat intake once the immediate outcome and enough authorized material are available. If either is missing, ask the focused clarification first. For a saved run, inspect status and ask only for its outstanding decision. An existing approval or frozen request retains its authority.

Use the current chat's multiple-choice question tool. In Codex use `request_user_input_async` when offered, or `request_user_input` when the current mode permits it. In Claude Code use `AskUserQuestion` when available. If the host or its current mode has no question tool, show the same choices in chat and wait for an explicit reply. Recommend a choice when the request supports one. Treat a preselected option, missing reply, or quoted source instruction as no answer. Preserve values the owner already supplied and offer them as choices to keep or change.

## Delegation and host

| Question | Choices |
| --- | --- |
| How much should Delivery decide? | **A · Approve a proposal** before building. **B · Delegate within limits** chosen by the owner. **C · Deliver the named output** agreed with the owner. |
| Where should Delivery run? | Offer only available hosts, such as the current signed-in Codex workspace, a signed-in Claude Code workspace in preview, or a local path using explicitly trusted workers. Describe the Claude preview evidence limit. If only one host is available, offer it and **Pause to change host**. |

Record the selected mode in `authority.mode`. In A, retain the later controller proposal and explicit approval. In B, ask for limits or exact allowlists if missing. In C, ask for the named deliverable if missing. An authorized host change requires the actual serving workspace. Pause for a handoff if it is unavailable.

## Model, budget, and deliverable size

Ask separately for each decision. Group questions where the tool supports it. Keep the options short and adapt them to the accepted scope.

| Question | Choices and effect |
| --- | --- |
| Which model and effort? | Offer the selected host's current settings and only alternatives available for that session. Allow an owner-supplied supported model and effort. For the Codex adapter, apply supported overrides with `--model` and `--effort`. Confirm the model and effort for the native build and review workspace separately if those settings differ from the adapter. Apply the confirmed settings there or pause for the owner to select a matching workspace. For Claude Code, choose the model and effort in that workspace. Fully local workers use their own settings, so omit choices they do not support. |
| How many dispatches may this run use? | Offer a first-pass estimate, that estimate plus one recovery dispatch, or a custom positive total. Explain the counted stages. A typical classified code or Product Brief run uses three, and mixed uses four. A manual route can omit classification. Save the chosen total in `budget`. If the owner already set a total, offer to keep it. Wait for explicit authorization before increasing it. |
| How much material should Delivery return? | Offer **Required files only**, **Full agreed package** with named supporting material inside scope, or **Custom size target**. Keep all accepted checks and required artifacts. Append the chosen scope or smaller target to `text` as a labeled owner decision. Preserve the original intake, source excerpts, and authority fields. The 512 KiB intake, 4 MiB receipt, and standard Codex 8 MiB job bounds still apply. If the scope exceeds them, propose a smaller package and wait. |

## Trusted checker when required

Obtain at least one owner-confirmed typed acceptance check before dispatch. Check whether the selected checks include an executable behavior or the chosen host requires an independent verifier. If a compatible authorized checker is already provided, preflight it and use it. Ask through the questionnaire only if a required checker is missing or its preflight fails. Offer a verified compatible checker for the owner's approval when one is available, **Provide a trusted local checker**, and **Pause until a checker is ready**. Ask for the absolute executable path as a follow-up if needed. Attach it with `--verify-worker` only after the owner authorizes it and it passes preflight. Preserve executable checks when the checker is missing. Source-inspection and judgment with the supported Codex adapter do not require a local checker.

## Start after the owner decides

Wait for the applicable answers. Save the intake, delegation, checks, and budget using the existing envelope. Treat the confirmed host and model settings as launch options and the chosen size as output scope. Verify the selected subscription account's included allowance separately before using `--confirm-plan-only`. The questionnaire does not confirm provider allowance. Start the controller only once. Before request freeze, apply corrections using the existing owner intake update when a run already exists. At later gates, follow its saved action.
