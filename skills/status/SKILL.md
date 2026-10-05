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

Finish with the single next step, taken from this order:
interrogator session (`claude --agent forge:interrogator`) → `/forge:approve brief` → `/forge:investigate` → review `pipeline/candidates.md`, `/forge:approve candidates` → `/forge:investigate-index` → review `pipeline/index.md`, `/forge:approve index` → `/forge:plan` → review `pipeline/design.md`, `/forge:approve design` → `/forge:build` per slice, `/forge:approve slice-N` after each → final review in `pipeline/review.md`.
If that step's command is not available yet, say it has not been built yet rather than improvising it.

Keep the report under 25 lines.
