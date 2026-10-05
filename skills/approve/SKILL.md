---
name: approve
description: Record the user's approval of a forge pipeline file (brief, candidates, index, design), so the next stage may start.
disable-model-invocation: true
argument-hint: "brief | candidates | index | design | slice-N"
allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/bin/forge-approve *)
---

# Forge approve

The user typed `/forge:approve $ARGUMENTS`. Claude Code already ran the approval script before you saw this message. Its output:

!`"${CLAUDE_PLUGIN_ROOT}/bin/forge-approve" $ARGUMENTS`

Report that output to the user in one or two lines, verbatim where it matters. Do not run `forge-approve` or `forge-gate` yourself, and do not edit any pipeline file: the approval is recorded only by the line above.

If it says `approved`, name the next step:
- brief → `/exit`, then run `forge` in this folder and type `/forge:next` (it starts the paper search)
- anything else → type `/forge:next` (design: mention that `tests/` is now locked)

If it says `NOT approved`, explain the reason it gives and what the user should do.
