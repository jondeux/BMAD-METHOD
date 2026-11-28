# Fifteen sample projects to test Autonomous Delivery v0.4.1

Use these projects to evaluate Delivery with synthetic data, local outputs, and observable checks. Projects 1–8 start with a scoped deliverable and exercise the current code or Product Brief routes. Projects 9–15 start with a raw idea and track the planning artifacts through to a verified application. The expected outcomes below are test criteria. Provider-backed trial results are still pending.

## How to test the workflow

Start a fresh workspace session with the enabled v0.4.1 entry. Use a scoped prompt from projects 1–8, a blind intake from projects 9–12, or a simulation prompt from projects 13–15. When a heading names a mode, select it when prompted. Leave host, model and effort, dispatch cap, and size for the questionnaire. A first-pass classified run commonly uses three dispatches for code or a brief and four for mixed. Use a trusted local checker for executable checks. Select the actual authorized serving host after checking included allowance. [User manual](../docs/build/autonomous-delivery.md)

Record the selected route and subtype, the submitted answers, whether a checker was requested, any proposal ID, the run path, dispatch count, published artifacts, and each check’s evidence. At completion, record **usable as delivered** or **changes needed**. Capture any approval, allowance, checker, or budget interruption in the shareable telemetry export. A scoped mixed package must include a real Product Brief within the named outcome. The application journeys below carry an approved planning artifact into the build and deliver the application against that artifact’s checks.

## Code only

### 1. Volunteer sign-in roll-up · Mode A

> `$bmad-deliver` Deliver a run-local Python module named `attendance.py`. Implement `summarize(csv_text)` for two columns, session and volunteer. Trim surrounding whitespace, skip blank rows, and count each volunteer once per session. A header plus the rows `Morning,Ada`, `Morning, Ada`, `Morning,Lee`, and `Afternoon,Ada` must return `{"Morning": 2, "Afternoon": 1}`. A header-only file returns an empty mapping. Use the standard library and verify the behavior with a trusted local checker.

Expected `small/code`. Confirm the Mode A proposal stops before Build Auto and the checker reports both executable results. [Harvard CS50P CSV exercise](https://cs50.harvard.edu/python/psets/6/scourgify/) · [Python CSV reference](https://docs.python.org/3/library/csv.html)

### 2. Library hold pickup date · Mode C

> `$bmad-deliver` Deliver `hold_deadline.py` with `pickup_due(start, business_days)`. Use ISO dates and count Monday through Friday after the start date. This prototype ignores holidays. Verify that one business day after 2026-03-06 is 2026-03-09 and that zero business days returns the start date. Keep it local and use the standard library.

Expected `small/code`. Check that the filename survives Mode C and both boundary values are verified by execution. [Python date arithmetic](https://docs.python.org/3/library/datetime.html)

### 3. Workshop stock threshold fix · Mode B

> `$bmad-deliver` Make this one change to the standalone function `def needs_order(available, minimum): return available < minimum`. Deliver the corrected `supply.py` as an isolated file. The allowed output class is code, and the exact permitted deliverable label is `supply.py`. The new function must return true at or below the minimum. Verify `needs_order(4, 5)` and `needs_order(5, 5)` are true, and `needs_order(6, 5)` is false.

Expected `trivial/run-local-code`. Check exact delegation, an explicit size choice, and no edits to the repository worktree. [Python comparison expressions](https://docs.python.org/3/reference/expressions.html#comparisons)

### 4. Pop-up tool checkout form · Mode A

> `$bmad-deliver` Deliver an offline `index.html` with labeled borrower and tool fields and a checkout button. A valid submission displays a confirmation containing both values. An empty required field prevents confirmation and identifies the missing field. Verify keyboard-only entry and submission in code-server’s embedded Live Browser through a trusted browser checker. Use one HTML file without external assets.

Expected `small/code`. Confirm the required-checker question appears if no trusted browser checker is configured. Verify both valid and invalid submission paths. [MDN client-side form validation](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Form_validation) · [W3C form labels](https://www.w3.org/WAI/tutorials/forms/labels/)

## Product Brief only

### 5. Workshop self-check-in pilot · Mode A

> `$bmad-deliver` Deliver a Product Brief about whether to pilot self-check-in at one workshop. Use this synthetic note as source material. “Six volunteer check-ins were simulated. No walkthrough with real participants has occurred. The workshop lead owns the trial decision.” Verify that the brief cites those facts and states one proposed success metric. Mark the proposed target as a target.

Expected `thinking/product-brief`. Inspect citations to the input and artifact. On the supported Codex verification path these source and judgment checks can proceed without a local executable checker. [GOV.UK beta phase guidance](https://www.gov.uk/service-manual/agile-delivery/how-the-beta-phase-works)

### 6. Quiet-hour pickup queue · Mode B

> `$bmad-deliver` Deliver a Product Brief on testing numbered slips at a library pickup desk. Allow only the non-code class and the exact deliverable label `Product Brief`. Use these two synthetic notes. “Staff log A: the line bunched at the entrance during the quiet-hour pickup window.” “Staff log B: nobody counted waiting times.” Verify that the brief cites both notes and proposes measuring wait time before and during a trial. Keep distribution local.

Expected `thinking/product-brief`. Confirm that attachment-like excerpts support the brief and that “nobody counted” remains an explicit limitation. [GOV.UK measuring service success](https://www.gov.uk/service-manual/measuring-success/measuring-the-success-of-your-service)

### 7. Large-print wayfinding cards · Mode C

> `$bmad-deliver` Deliver a Product Brief about trialing a large-print welcome-desk sign. A synthetic observation says that two of five mock participants could not read the old sign from the entrance. The facilities coordinator owns the proposed trial. Verify that the brief distinguishes the observation from a proposed success target of four out of five participants finding the desk unaided. Verify that the plan includes an alternative way to ask for directions.

Expected `thinking/product-brief`. Check source-inspection evidence and judgment about the difference between observed evidence and the proposed target. [GOV.UK user research in beta](https://www.gov.uk/service-manual/user-research/user-research-in-beta)

### 8. Tool-return reminder pilot · Mode B

> `$bmad-deliver` Deliver a Product Brief on whether to trial tool-return reminders. Limit delegation to the non-code class and the exact label `Product Brief`. Use this synthetic enrollment note. “Eight of twenty returns were late. Reminders were never sent. The tool coordinator owns the pilot decision.” Verify those three claims and a proposed on-time-return metric. Keep it a local decision draft.

Expected `thinking/product-brief`. Check that the brief preserves the limitations of the synthetic source and makes the proposed metric measurable. [GOV.UK measuring service benefits](https://www.gov.uk/service-manual/measuring-success/measuring-service-benefits)

## Blind idea-to-application prompts

Start a fresh Delivery session with only the chosen project’s quoted prompt, including its `$bmad-deliver` callout. Answer the questionnaire and factual follow-up questions as the owner. Keep the [evaluator guide](autonomous-delivery-smoke-evaluator.md) outside the Delivery session. Record the workflow that Delivery proposes and any capability gate it reaches.

### 9. Community-room supply budget

> `$bmad-deliver` We keep running short of supplies in the community room, and sometimes we buy more than we need. We have a small trial budget. I’d like help figuring out a better way to decide what to buy.

### 10. Rainfall log summary

> `$bmad-deliver` Our garden rain log has blank entries for days when nobody checked the gauge. I want a useful weekly summary. Before we settle how to handle blanks, I’d like evidence about how comparable rain logs distinguish missing readings from a day with no rain.

### 11. Repair café queue ticket board

> `$bmad-deliver` Visitors at our repair café lose track of whose turn it is. I’d like people at the check-in desk to see who’s next and understand how the order was decided.

### 12. Equipment reservation overlap guard

> `$bmad-deliver` We keep double-booking shared equipment. I want a local way to spot a conflict before I accept a booking. We’ve agreed that back-to-back reservations are fine and that a booking for one item should never block another item.

## Advanced WebGL2 simulation projects

Start with the raw prompt. Use the planning artifact to agree on the visual and physical behavior, the supported browser and performance target, and the checks that would prove the result is usable. Save the agreed checks before building. Deliver the simulation as one self-contained HTML file and open the delivered file in code-server’s embedded Live Browser for verification.

### 13. Ray-traced water balloon burst · Mode A at delivery

> `$bmad-deliver` Make a WebGL2 ray-tracing simulation of a bullet piercing a water balloon. Show the balloon popping and the water briefly retaining its shape, then deforming, breaking into droplets, falling, and splashing on the ground. Make the water motion and lighting as realistic and physically accurate as practical in a browser. Let me freeze or scrub the animation at any point and orbit the scene freely, including while paused. Add sliders for the simulated bullet speed, balloon size, lighting, gravity, surface tension, and playback speed. Deliver one self-contained HTML file with inline JavaScript, CSS, and WebGL2 shaders.

**What to verify.** Inspect frames before contact, during the burst, and after the water reaches the ground. Confirm that orbiting while paused leaves the simulation time fixed. Change the gravity and lighting and check that each changes the intended part of the scene. Record the chosen simulation and rendering approximations in the planning artifact.

### 14. Humpback breach and ocean splash · Mode C at delivery

> `$bmad-deliver` Build a browser simulation of a humpback whale surfacing, breaching above the water, and splashing back into the ocean. Generate the whale, moving water, and spray in code. After the whale lands, show the impact ripples spreading and the foam fading. Let me trigger a breach, pause or scrub the animation, and orbit from the waterline to an overhead view. Give me sliders for wave height, sunlight direction, and playback speed. Deliver one offline HTML file with inline JavaScript, CSS, and WebGL2 shaders.

**What to verify.** Trigger a breach and observe the leap, splash, ripples, and fading foam in order. Freeze the landing and change camera angle without advancing time. Test a low and high wave setting. Adapted for offline WebGL2 delivery. [Spring Prompt whale-breach benchmark](https://springprompt.com/playground/whale-breach)

### 15. Ink diffusion and mixing lab · Mode B at delivery

> `$bmad-deliver` Make a real-time WebGL2 simulation of ink mixing in water, viewed from above. Let me place colored drops and stir the fluid with the pointer. Show the dye moving in curls and gradually dispersing. Add sliders for viscosity, diffusion, and stir strength, plus a color picker, pause, single-step, and reset controls. Deliver one self-contained HTML file with the shaders, JavaScript, and CSS embedded. It should open offline.

**What to verify.** Add two drops and stir the fluid. Confirm that pausing holds the pattern, single-step advances one step, and reset restores a clear tank. Compare two diffusion settings from the same starting state. Adapted from a published standalone simulation prompt. [PumpyDumpy ink-in-water prompt](https://ai.pumpydumpy2visual.com/en/ink-in-water#prompts-for-your-own-ink)
