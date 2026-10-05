---
name: init
description: Turn the current folder into a forge project (references/, pipeline/, tests/, src/, .gitignore). Use when the user runs /forge:init or asks to set up a project for the forge pipeline.
disable-model-invocation: true
---

# Forge init

Run this command from the project root, exactly once:

```bash
forge-init
```

If `forge-init` is not found on the PATH, run `"${CLAUDE_PLUGIN_ROOT}/bin/forge-init"` instead.

The script does all the work and is safe to re-run: it never overwrites existing files, and it adds its block to an existing `.gitignore` only once. Do not create, move or edit any project files yourself.

Then report what it printed, in a few lines. If the folder is not a git repository, mention that `git init` is optional, and that the `.gitignore` keeps paper folders out of git while `catalog.md`, `references.bib` and `MISSING.md` are committed.

End with the next step: drop PDFs into `references/inbox/`, or write the brief with the interrogator session.
