# Install the local BMad delivery beta

Use Python 3.11 or newer, uv for native workflow dependencies, and a Codex workspace agent
with access to the project files, native tools, and your configured model provider.

Extract the ZIP to a new directory. Verify its manifest there with `sha256sum -c SHA256SUMS`.
Then open a terminal in the project that should use the skill, and copy it into that project.

```bash
test ! -e .agents/skills/bmad-deliver &&
test ! -L .agents/skills/bmad-deliver &&
mkdir -p .agents/skills &&
cp -R /absolute/path/to/extracted/bmad-deliver .agents/skills/
```

Open a fresh Codex session in the project and invoke the skill with an idea or source file.

```text
$bmad-deliver Turn my intake notes into an internal decision brief.
Mode C. Use only these notes and keep the draft local.
```

Include the behaviors that the output must demonstrate. For Mode A, approve the proposed deliverable
before any native build. For Mode B, state the delegated outcome and limits. Mode C preserves the
named deliverable.

The beta includes the native Build Auto, Product Brief, and review workflow files. For native runs,
start from the workspace agent so it can serve the jobs and record actual evidence. Use the same skill
with the saved run path to resume. See `bmad-deliver/references/run-record.md` and
`bmad-deliver/references/native-host.md` for the terminal and host interfaces.
