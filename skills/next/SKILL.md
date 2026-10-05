---
name: next
description: Run the next step of the forge pipeline (the right workflow), or say exactly which file to read and what to approve. Use when the user runs /forge:next or asks to continue the forge pipeline.
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/forge status *)
---

# Forge next

The user typed `/forge:next`. Claude Code already ran the next-step check before you saw this message. Its output (JSON, decided by code from the project's files and approvals):

!`"${CLAUDE_PLUGIN_ROOT}/bin/forge" status --json`

Act on its `action`, and only on it:

- `workflow`: run the forge workflow named in `workflow` with the Workflow tool (name `forge:<workflow>`, for example `forge:investigate`; no script, no args). Before it starts, tell the user in one line what is starting (the `stage` and `say`). If the Workflow tool is not available or does not accept the name, tell the user to type `/forge:<workflow>` themselves; if it says Dynamic workflows are off, tell them to turn them on in `/config`. When the workflow finishes, report its result in a few lines and end with: "Read <the file it wrote>, then `/forge:approve <gate>`." (or what the workflow's `next` field says).
- `approve`: do not run anything. Tell the user the `say` sentence: which files to read, and the exact `/forge:approve <gate>` to type. Approving is the user's job; never run `forge-approve` yourself.
- `interrogator`: do not run anything. The brief is written in its own session: tell the user to type `/exit`, then run `forge` in this folder (it opens the Interrogator).
- `done`: report the `say` sentence.

If the output is not JSON (for example "not inside a forge project"), report it and say that `forge new <folder>` starts a project, or `/forge:init` sets up the current folder.

Never edit pipeline files, never run a different workflow than the one named, and never run more than one workflow per `/forge:next`.
