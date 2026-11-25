---
name: "project-handoff"
description: "Use when the user asks for a handoff, a STATE BLOCK, a session summary to carry over, or to continue the work in a new chat or another AI agent (often because the context is long). Sizes the handoff to the session, resolves cheap open items first, and writes a verified, privacy-safe state block plus a starter message. Use this instead of context-handoff's handoff-writing for any handoff."
---

# Project handoff

## Purpose

Let a different agent, in a new chat, continue the work as if nothing happened. The handoff is a map of the
current state, not a history of the chat.

**Success test:** a new agent that reads only the handoff (and the files it lists) makes a correct next move in its
first reply, and asks nothing the old chat already answered.

## Step 0. Size the handoff

Pick the smallest tier that carries everything a successor needs. Say which tier you chose in one line.

| Tier | When | Output |
|---|---|---|
| **S, short** | A short session with a few decisions and no deliverables in flight | The short format (section 5a), at most about 20 lines |
| **M, standard** | Real work done, some open items, a few files | The full STATE BLOCK (section 5b), in chat only |
| **L, project** | A long or multi-day project with deliverables, environments, approvals or rules | The STATE BLOCK plus HANDOFF.md, optional file bundle, starter message (section 6) |

If nothing worth handing off happened, say so plainly: "Nothing decision-worthy to hand off from this session."
Do not pad the template.

## Step 1. Harvest (read before you write)

Read the whole conversation and every file the user attached for the handoff. Collect:

- **The latest results the user sent.** These come first. Analyse them before anything else (step 2).
- **Standing rules,** quoted word for word when the user stated them strongly (capitals, "never", "always").
- **Go-words and approvals:** words the user uses to approve things, and what is still waiting for one.
- **Decisions with their reasons,** and **alternatives that were rejected, with why**. The reasoning is the part
  that cannot be re-derived; a rejected path recorded here is a dead end the next agent will not walk again.
- **Preferences:** style, reply order, tone, formats, file limits, the user's skill level, OS and tools.
- **Deliverables:** every file that matters, with its name, version, purpose, location, and SHA256 if one exists.
- **Corrections the user made to you.** These are lessons, and they go into the workflow field.

Leave out: routine back-and-forth that led nowhere (typos, a corrected path), pleasantries, full code or diffs
(reference the file instead), and anything already in the project's CLAUDE.md or README (point to it instead).

## Step 2. Analyse the latest results

If the user attached new results (test output, logs, reports):

1. Compare before and after where both exist.
2. For each failure or warning: give the cause if the evidence shows it. Otherwise write "cause UNKNOWN" and name
   the single command, file or fact that would prove it.
3. Never state a cause the data does not show. "Likely" is allowed only with the reason it is likely.

## Step 3. Resolve what is cheap and safe, before handing off

The user wants as few open items as possible. Close the ones you can close without the user.

- Do it if it is **cheap** (minutes, not a new project), **safe** (no change to the user's live systems, no
  redeploy, nothing irreversible) and **testable here** (you can prove the fix with a test and a negative control).
- Do not start large new work during a handoff. If the user has said to stop spending effort on something, drop it
  and record it as closed or deferred.
- An item that needs the user (a console check, a fact only they have) stays open. Give it the single command or
  one-word answer that would close it.
- An item that needs real work goes in "next actions" for the successor.

## Step 4. Privacy and secrets pass

Before writing the final text:

- Replace the user's domain, host names, IP addresses, account IDs, emails and other personal details with
  placeholders such as `<DOMAIN>`, `<HOST>`, `<IP>`, `<ACCOUNT>`.
- Never include secrets, tokens, keys, passwords or the contents of environment files. Name them, never show them.
- Exception: a file the user's system needs to run may keep real values. List those files by name so the user can
  decide before sharing them with another service.
- **Check mechanically:** search everything you are about to deliver for the real values you know (the actual
  domain, host name and addresses from the conversation). Zero hits outside the listed exceptions.

## Step 5. Write the handoff

Mark every claim with its evidence level:

- `[V]` verified, with the evidence named (file, command, measurement, date).
- `[I]` inferred, with the reason.
- `[U]` UNKNOWN, with what would settle it.

Plain English, short sentences. Dates as absolute dates, not "yesterday".

### 5a. Short format (tier S)

```
## [Project name], session handoff ([date])

Decisions:
- [decision] - [reason]

Rejected alternatives:
- [alternative] - [why rejected]

Open / blocked:
- [specific blocker: the actual error, API or pending decision] - next step: [action]

Conventions noted:
- [preference the user stated]

Next: [the first thing to do in the new chat]
```

Omit a section that has nothing in it. Do not write "None".

### 5b. STATE BLOCK (tiers M and L)

One code block. Fill every field below. If a field is truly empty, write "none" and why. Aim for under about
1,800 words: enough to act on, not the history.

```
STATE BLOCK  ([project], [date])

goal:                        the end state of the whole project, in 2-3 lines.
success test:                the checks that prove the goal is met (numbers, commands, expected results).
stage completed:             what is DONE and confirmed, with dates; what is built but not yet applied.
terms I've learned:          a glossary of project words, go-words, IDs and short names, one line each, so the new
                             agent understands the user's vocabulary.
goals (ranked):              priorities in order, used to break ties.
audience:                    who reads the outputs, their skill level, preferred style, reply order, OS and tools.
requirements:                MUST / SHOULD / COULD / NOT NOW, including every standing rule (strict ones quoted).
workflow and rubric:         the working loop step by step, the quality bar each deliverable must pass, and the
                             lessons learned from the user's corrections.
decisions made (and why):    ID, choice, reason, how to undo it.
rejected alternatives:       what was considered and dropped, and why, so it is not tried again.
assumptions to confirm:      what is treated as true but not proven, and how to check each one.
open questions:              ranked. For each: status, evidence so far, the single next action, owner (agent or user).
verified so far / still unverified:
                             two lists. Verified items name their evidence. Unverified items are marked UNKNOWN.
next actions:                the first 3 things the new agent should do, in order.
files and environment:       every file that matters (name, version, purpose, location, SHA256), and key facts about
                             the system (no secrets). Say which older documents this handoff overrides.
risks and rollback:          known residual risks, and the exact undo for each change in flight.
pending approvals:           what is waiting for the user's go-word, and what each word unlocks.
```

## Step 6. Package (tier L)

- **File limit:** at most 4 files, fewer is better. The usual set:
  1. `HANDOFF.md`: the STATE BLOCK, the file inventory, the starter message, the user's next steps.
  2. One archive with the current scripts, tests, test results and build inputs, plus a SHA256 list.
  3-4. Only if something cannot go in the archive.
- Re-run the tests after the last change, and put the results in the archive.
- Write HANDOFF.md where the user can get it: send it with the file-sending tool if there is one; in a repository
  with no other place, use `.ai-context/handoff.md`.
- Keep it portable: plain Markdown, no tool-specific syntax, so any agent (Claude or not) can read it.

### Starter message (put it at the top of HANDOFF.md)

Three to six lines the user can paste into the new chat as-is: what to read, which rules apply, and what to do
first. Example shape:

> I am handing over a project. Read HANDOFF.md fully and unpack the archive. Continue from the STATE BLOCK.
> Rules: [the 3-5 strictest standing rules]. Start with "next actions" item 1.

## Step 7. Check before you send

Run every check. Fix any that fails, then check again.

- [ ] The tier fits the session, and the tier is stated.
- [ ] The latest results were analysed first; no cause is stated without evidence.
- [ ] Every field is filled (tier M/L), or empty sections are omitted (tier S).
- [ ] Every open item has a next action and an owner.
- [ ] Every claim carries `[V]`, `[I]` or `[U]`.
- [ ] Standing rules are present, the strict ones word for word.
- [ ] The mechanical privacy search found no real domain, host, IP or secret outside the listed exceptions.
- [ ] At most 4 files, each with a SHA256; tests re-run after the last change (tier L).
- [ ] **Cold-read test:** read the handoff as the new agent, with no access to this chat. Write down the first 3
      questions you would ask. If the old chat answers any of them, add the answer to the handoff.

## In the chat reply

After delivering: the STATE BLOCK (or short format) as one copyable code block, then at most 3 lines: the tier,
what was resolved during the handoff, and what the user should do first. Nothing else.