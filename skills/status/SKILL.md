---
name: status
description: Show where the current project stands in the forge pipeline (brief, references, plan, test lock, build log) and name the next step. Use whenever the user asks for forge status, pipeline status, "where are we", or what to run next in the pipeline.
---

# Forge status

Inspect the current working directory (the project root) and report a compact status. Only read files: never create, move, or edit anything.

Check, in this order:

1. `references/`: count paper folders (a folder `<key>/` containing `<key>.md`), PDFs waiting in `references/inbox/`, and entries listed in `references/MISSING.md`.
2. `pipeline/`: which of `brief.md`, `index.md`, `design.md`, `ledger.md`, `plan.md`, `build-log.md` exist. For `brief.md`, also report its `status:` frontmatter value.
3. Whether `pipeline/.tests-locked` exists.
4. `pipeline/approvals/*.json`: for each gate (brief, candidates, index, design), run `forge-gate <gate>` to say whether its approval is valid, missing, or stale (file changed after approval).
5. If `pipeline/plan.md` exists: run `forge-build-status` and report the test lock and each slice's state (not built, failed, passed awaiting approval, approved).
6. `pipeline/.stage`: which stage ran last (agent, stage label, start time). It is written by the forge guard hook, not by an agent.
7. `pipeline/run-log.md`: the number of actions and of `BLOCKED` lines, and the last 5 lines verbatim. Point out any blocked attempt.

If neither `references/` nor `pipeline/` exists, say the project has not been initialised for forge yet and that `/forge:init` sets it up.

Finish with the single next step: run `forge status` (or `"${CLAUDE_PLUGIN_ROOT}/bin/forge" status` if `forge` is not on the PATH) and repeat its output. It is decided by code from the approvals; don't improvise a different one. When the step is a workflow, tell the user to type `/forge:next`.

Keep the report under 25 lines.
