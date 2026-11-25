---
name: bmad-deliver
description: 'Run an idea, research dump, brainstorm, or Forge output through bounded, resumable BMad delivery for code, documents, or both. Use when the user delegates idea-to-deliverable work or asks to resume an existing delivery run.'
---

Use [the command and run contract](references/run-record.md). Start from the user's message or supplied material and create the request JSON for them. When resuming, load the existing run with `status` and follow its visible gate. Never create a new run to bypass a pending decision.

For a new run, capture the intended outcome, original behaviors with observable checks, and the user's choice of authority. A asks for approval of a specific proposal. B delegates within stated limits. C names the deliverable. A and C require actual owner approval for replacement. Intake can be an idea, literature dump, brainstorming result, or Forge handoff. Use the user's input as source material and surface any real authority or acceptance gap. Label reversible assumptions.

Create the request in an authorized working location. Use one new private run directory under the project's output folder. Confirm the user has authorized the selected worker and the material sent to its provider. Use the requested call budget and installed worker. For native delivery, run the controller with `--native-host` and serve the workflow jobs in the workspace agent session. Follow [the workspace host instructions](references/native-host.md). Retain the original checks at every handoff. Start the controller, report required owner decisions or an exhausted budget, and return the verified artifacts and check evidence on completion.
