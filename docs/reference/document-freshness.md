---
title: "Keep repository documentation current"
description: "Check repository references and verify project status against actual evidence."
---

Run this routine after a module or file move, at a milestone, and when a check fails. Run it in the current checkout as part of that work.

1. Run the reference checker and the docs-site link validator.

   ```bash
   python3 -B docs/_checks/check_references.py
   node docs-site/scripts/validate-doc-links.js
   ```

2. Open each flagged file and verify the intended target. Repair local paths and line ranges. For symbol links, prefer a concrete code location and name the symbol in the link label. Add `<!-- freshness-example: path -->` on the same line only for an intentional example or a file generated in another project.
3. Compare current progress claims in `README.md`, `AGENTS.md`, `docs/`, and the Claude memory directories against `git log`, `git status`, and relevant test results. Confirm moved or renamed symbols in source. Update current claims and keep historical records, changelog entries, evaluation results, and trail learnings as recorded.
4. Run the checks again. At a delivery milestone, rerun the full tests and rebuild the affected package before committing authorized changes.

The Python checker runs offline with the standard library. It reads Markdown in the repository docs and Claude memory directories, plus the top-level readme and agent instructions. It checks local links, concrete checkout paths, explicit line bounds, and named Python symbols in source links. Fenced examples and external URLs are outside its static check. Review prose status claims and symbol references in other languages against the repository. The checker and its CI test only read the checkout. A commit still requires the owner's instruction.
