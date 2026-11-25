# Autonomous delivery beta handoff

The branch includes the resumable [BMad delivery skill](../../skills/method/bmad-deliver/SKILL.md), native dispatch for Build Auto and Product Brief, and the [beta packager](../../tools/package_delivery_beta.py). The [tested archive](bmad-deliver-beta.zip) includes the delivery skill, matching Build Auto runtime, pinned Product Brief and the review lenses. Follow the [installation guide](INSTALL.md) to use it in a fresh workspace.

## Verification

- A synthetic live Mode A mixed run stopped before native work. After approval, the controller was killed with the Build Auto receipt saved. The new process reused that receipt and ran Product Brief. Both artifacts passed all six acceptance checks within four controller dispatches.
- A fresh workspace discovered the installed beta. The bundled Build Auto rendered successfully. An independent live Mode C run completed a product brief in three dispatches and passed all four checks. [Synthetic brief](library-trial-brief.md) · [Editorial review](native-editorial-review.md)
- The beta archive rebuilt byte for byte in the development workspace. The extracted member hashes were verified. [Archive checksum](bmad-deliver-beta.zip.sha256)
- The full source suite passed 1,259 tests and 198 subtests. Strict skill and module validation passed.

Native jobs use an authorized workspace agent. The optional BMad Help follow-up requires a separate install.
