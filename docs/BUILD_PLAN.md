# forge: build plan

This is the living spec for the forge Claude Code plugin. A fresh Claude Code session should be able to continue the build from this file alone. Update the checklist in section 7 as each step lands, and record any changed decision in section 2 with the date.

## 1. What forge is

A Claude Code plugin that runs a research-to-code pipeline inside any project:

```
interrogator (you + agent)  →  /forge:investigate  →  /forge:plan  →  you review design.md  →  /forge:build
        brief.md                 references/ + index.md     design.md, plan.md, tests/           code + build-log.md
```

It is installed once from GitHub and used in every project. A project only holds data: its references, the pipeline documents, its tests and its code. The pipeline itself (agents, workflows, hooks, tools) lives in this repo and updates everywhere with one command.

## 2. Locked decisions

| Topic | Decision |
|---|---|
| Distribution | This repo is both the plugin and its own marketplace (`marketplace.json` entry with `"source": "./"`). Install once; `/forge:init` scaffolds each project. |
| References | One `references/` folder per project. Agents read Markdown; the original PDF stays next to it for figures and equations. No Zotero. |
| Conversion | Zero cost is a hard requirement. `refs` sends PDFs to a self-hosted Marker server (`marker_server --port 8001`), which runs the Surya OCR 2 model locally through `llama.cpp` on Metal. Mistral OCR stays as an opt-in backend (`FORGE_OCR_BACKEND=mistral`). Changed 2026-10-04: the user's free Mistral workspace now has an OCR limit of 0 requests/minute. Obsidian is only a viewer: open a project's `references/` folder as a vault. |
| Marker install | `~/.local/share/forge/marker-venv` (marker-pdf 2.0.0 + fastapi, uvicorn, python-multipart), `brew install llama.cpp`. Default mode `balanced`. Never pass `--use_llm` (it calls paid LLM APIs). The Obsidian `marker-api` plugin's "Python API" option points at the same server. |
| API key | Only for the optional Mistral backend: `MISTRAL_API_KEY` in the shell profile. Never committed. |
| OCR cache | `~/.cache/forge/ocr/<sha256>.marker.json` (Marker) or `<sha256>.json` (Mistral), shared across projects; a cached result from either backend is reused, so a paper is never OCR'd twice. |
| Orchestration | Claude Code dynamic workflows (`workflows/*.js`) for investigate, plan and build. Control flow lives in the scripts, never in prompts. |
| Human gates | Workflows can't take user input mid-run, so each gate sits between two workflows: approve brief → investigate + plan → review design → build. |
| Interrogator seed papers | When the idea starts from specific papers, the Interrogator fetches and converts them itself (`refs fetch --source brief`, `refs convert`) and reads only the Markdown, Grep-first, to ask informed questions. The guard allows it exactly those single `refs` commands and blocks reading PDFs (2026-10-04, user request after the first real interview). |
| Paper pool | `refs fetch` looks in the paper pool before downloading: folders of already-converted papers (one folder per paper, one `.md`, `assets/`), such as the user's Obsidian vault. Match by arXiv ID, DOI, or title (similarity ≥ 0.92, year within 1). A hit is copied into `references/<key>/` with forge frontmatter (`origin: pool: <path>`) and images moved to `images/`; no download, no OCR. Pools are listed in `~/.config/forge/config.json` (`refs pool add`), or `FORGE_POOL`, so each machine points to its own copy (2026-10-05, user request). |
| Marker lifecycle | `refs convert` works in time-boxed rounds (`--budget`), reports `busy` when Marker is converting, and starts the local Marker server on demand (detached, pid in `~/.local/share/forge/marker.pid`); `refs marker start|stop|status` controls it. |
| Interrogator | Runs as the main session (`claude --agent forge:interrogator`; plugin agents are namespaced), because subagents can't ask the user questions. It asks in plain chat, not through AskUserQuestion, and starts itself via `initialPrompt`. |
| Critics | Fresh instances every round. Each round receives the ledger of earlier critiques and Ozymandias's rulings. |
| Debate shape | Sequential: J. Jonah Jameson critiques, then Smithers defends against those specific critiques, then Ozymandias rules on each item. |
| Stop rule | No open blocker or major critique, or 3 rounds, whichever comes first. |
| Tests | Written at the end of `/forge:plan`; locked by `/forge:approve design` (`pipeline/.tests-locked`), enforced by the stage guard for every agent. |
| Git (projects) | Paper folders are gitignored by default; `catalog.md` and `references.bib` are committed so `refs fetch` can rebuild the folders on another machine. |
| Control model | The user wants granular, verifiable control: every rule that matters is enforced by code (hooks, workflow checks), not by prompts. Prompts only describe the job (2026-10-04, after the first trial run bypassed the pipeline). |
| Stage identity | Every stage opens with a banner `forge · stage N/5 · <Name>`, and `pipeline/.stage` records which stage is active. An ordinary Claude greeting means the stage did not start. Stages: 1 Interrogator, 2 Investigate, 3 Plan (council), 4 Design review (human), 5 Build. |
| Stage guard | A plugin `PreToolUse` hook reads `pipeline/.stage` and allows only that stage's writes and commands (for example, no `src/` writes outside Build, papers only through `refs`). With no active stage in a forge project, it blocks writes to `src/`, `tests/` and `references/`. Replaces the narrower test-lock-only hook. |
| Run log | Every stage appends to `pipeline/run-log.md`: start and end, agent, files read and written, papers fetched and converted, each critique and ruling, each test run. `/forge:status` summarises it. |
| Human gates | brief → candidates → index → design (→ build slices). `/forge:approve <gate>` runs `bin/forge-approve` through skill shell injection, so it executes only when the user types it (hooks don't see it; the guard blocks agents from running it). It stores the approved file's SHA-256 in `pipeline/approvals/<gate>.json`; `forge-gate <gate>` and the guard treat any later edit, or a stale earlier gate, as not approved. The Interrogator can't write `status: approved`. |
| Investigate shape | Two plugin workflows, because workflows can't wait for input: `/forge:investigate` (gate → seed papers → one Mr. Curiosity per sub-question → `refs resolve` on every ID → `pipeline/candidates.md`) and `/forge:investigate-index` (gate → fetch + convert kept papers → one Pointer per sub-question → `pipeline/index.md`). The scripts build both files from structured agent output; agents only write them out. Workflow agents are launched by `agentType`, so the guard sees `forge:hungry-hippo`, `forge:mr-curiosity`, `forge:pointer`. Dynamic workflows must be enabled in `/config` on the Pro plan. |
| Model aliases and effort | Agent files use `sonnet`, `opus`, `haiku` aliases so they follow the current model versions. Each Sonnet and Opus agent sets `effort` in its frontmatter, which overrides the session effort (2026-10-06): high for Interrogator, Ozymandias and J. Jonah Jameson; medium for Mr. Curiosity, Smithers and Reviewer; low for MF-CODE. The Haiku agents (Hungry-hippo, Pointer) set none because Haiku 4.5 does not support effort. Claude Code ignores frontmatter `effort` when an agent runs as the main session (`--agent`; checked 2026-10-06, v2.1.291), so `bin/forge` reads it from the agent file and passes `--effort` for the Interrogator. |
| `refs` dependencies | Standard library only, no `uv` (2026-10-04). PDF downloads fall back to `curl` when a publisher serves Python an HTML interstitial (Nature does). |
| Open-access lookup | arXiv → Semantic Scholar `openAccessPdf` → Unpaywall (only if `FORGE_EMAIL` is set) → Crossref PDF links (2026-10-04). |
| OCR request | `POST https://api.mistral.ai/v1/ocr`, model `mistral-ocr-latest` (`MISTRAL_OCR_MODEL` overrides), upload to `/v1/files`, OCR a signed URL, then delete the upload (the inline base64 route is rate-limited on the free tier). Same endpoint, model and key as the Obsidian `marker-api` plugin. Cost depends only on the key's Mistral workspace: on the free Experiment tier (no billing card) it costs nothing and is rate-limited; a workspace with a card pays ~$4 per 1,000 pages (checked 2026-10-04). |

## 3. Agents

| Agent file | Model | Stage | Reads | Writes |
|---|---|---|---|---|
| `interrogator.md` | sonnet | main session | the user | `pipeline/brief.md` |
| `hungry-hippo.md` | haiku | investigate | brief, `MISSING.md` | runs `refs fetch` / `refs convert` |
| `mr-curiosity.md` | sonnet, ×N in parallel | investigate | one sub-question, `catalog.md` | candidate list (JSON) |
| `pointer.md` | haiku | investigate | brief, `catalog.md`, `references/*/*.md` | `pipeline/index.md` |
| `ozymandias.md` | opus | plan | brief, index, ledger | `design.md`, `plan.md`, rulings in `ledger.md`, `tests/` |
| `j-jonah-jameson.md` | sonnet | plan | design, plan, index, ledger | critiques (JSON) |
| `smithers.md` | sonnet | plan | plan, this round's critiques, index | rebuttals or concessions + load-bearing list (JSON) |
| `mf-code.md` | sonnet | build | `plan.md` (one slice at a time) | `src/`, `build-log.md` |
| `reviewer.md` | sonnet | build | plan, design, the diff | review notes in `build-log.md` |

## 4. Stage contracts

### Interrogator

Fills `templates/brief.md`: goal, non-goals, hypothesis, acceptance criteria (each one testable), constraints, seed references (DOIs, arXiv IDs, PDF file names), open questions. It keeps asking until the user approves, then writes `pipeline/brief.md` with `status: approved` in its frontmatter. Downstream workflows refuse to start on an unapproved brief.

### /forge:investigate

1. Hungry-hippo runs `refs convert`, which picks up anything the user dropped into `references/inbox/`, then `refs fetch` for the brief's seed references.
2. Mr. Curiosity runs once per sub-question in the brief, in parallel. Each instance checks `catalog.md` first, then searches, and returns candidates as `{id, title, why}`, where `id` is a DOI, arXiv ID or URL.
3. Hungry-hippo runs `refs fetch <ids>`. Every ID must resolve (Crossref or arXiv) or it is dropped and logged. Paywalled papers go to `MISSING.md`. Then `refs convert` again.
4. Pointer writes `pipeline/index.md` as a table: sub-question | key | heading anchor | line range | one-line reason. It locates; it does not evaluate.

### /forge:plan

For round r = 1..3:

1. Ozymandias drafts the plan (round 1) or revises it.
2. J. Jonah Jameson returns critiques, each `{id, severity: blocker|major|minor, claim, evidence}`. Evidence must point to an `index.md` row or a reference key. It may reopen an item already ruled on only with new evidence.
3. Smithers answers each critique by rebutting it with evidence or conceding it, and lists the load-bearing decisions a revision must not break.
4. Ozymandias rules on every item in `ledger.md` (accepted or rejected, with reason and evidence).
5. Stop if no blocker or major critique remains open.

Outputs:
- `design.md`, for the human gate, roughly 200 lines at most: goal, key decisions, ASCII diagram of the solution (not the code), risks.
- `plan.md`, the builder's contract: file tree, full function signatures, data paths, test specs, and vertical slices that each end at a test checkpoint, plus a to-do checklist.
- `tests/`: unit tests plus conceptual tests (known-answer synthetic data, shuffled-label control at chance, invariants, tiny-dataset overfit).
- `pipeline/.tests-locked`.

### /forge:build

For each slice in `plan.md`: MF-CODE implements it, then runs the tests, with up to 3 attempts. If the slice still fails, it writes a blocker report into `build-log.md` and the workflow stops; the report goes back to planning. After the last slice, the reviewer compares the diff against `plan.md` and `design.md`.

Test lock: a `PreToolUse` hook in `hooks/hooks.json` blocks writes under `tests/` while `pipeline/.tests-locked` exists. It covers Edit and Write; Bash commands that write into `tests/` are blocked on a best-effort basis. The hook lives at plugin level because plugin agents ignore `hooks` in their own frontmatter, and it is conditional because plugin hooks fire in every session where the plugin is enabled.

## 5. `refs` CLI spec

A single executable `bin/refs` (Python 3.10+). Because `bin/` is on the Bash tool's PATH while the plugin is enabled, agents call it by name.

| Command | Does |
|---|---|
| `refs convert` | Every PDF in `references/inbox/` → `references/<key>/` containing `<key>.md`, `<key>.pdf`, `images/`, `ocr.json`. Idempotent; uses the OCR cache. |
| `refs fetch ID...` | Resolves DOIs, arXiv IDs or URLs to metadata, downloads open-access PDFs into `inbox/`, writes paywalled ones to `MISSING.md`. |
| `refs catalog` | Rebuilds `references/catalog.md` from each paper's frontmatter. |
| `refs bib` | Rebuilds `references/references.bib`. |
| `refs status` | Counts converted papers, PDFs waiting in the inbox, and missing papers. |

Keys: lowercase ASCII, first author's surname + year + first non-stopword of the title, for example `smith2024transfers`. On a collision, add `b`, `c`, and so on.

Frontmatter of each `<key>.md`: `key, title, authors, year, doi, arxiv, url, source (user|brief|curiosity), verified, converted, ocr_sha256`.

Metadata for a dropped-in PDF without an ID: look for a DOI in the first page of the OCR text; otherwise search Crossref by the title in the first heading; otherwise set `verified: false` and build the key from the file name.

Images are linked Obsidian-style (`![[images/...]]`) so the vault view matches what the Obsidian OCR plugins produce.

## 6. Layouts

Plugin (this repo), target state:

```
forge/
  .claude-plugin/  plugin.json  marketplace.json
  agents/          interrogator  hungry-hippo  mr-curiosity  pointer  ozymandias
                   j-jonah-jameson  smithers  mf-code  reviewer           (.md each)
  workflows/       investigate.js  plan.js  build.js
  skills/          status/  init/
  hooks/           hooks.json  forge-guard.py
  bin/             refs  forge-init  forge-approve  forge-gate  forge-test  forge-build-status
  templates/       brief.md  design.md  plan.md  ledger.md  project.gitignore
  docs/            BUILD_PLAN.md
```

A project after `/forge:init`:

```
my-project/
  references/
    inbox/                       drop PDFs here
    smith2024transfers/          .md  .pdf  images/  ocr.json
    catalog.md  references.bib  MISSING.md
  pipeline/   brief.md  index.md  design.md  ledger.md  plan.md  build-log.md
  tests/                         written during planning, locked during build
  src/
```

## 7. Build order

Each step must work and be checked on its own before the next one starts.

- [x] **1. Skeleton.** Manifest, marketplace entry, `/forge:status` skill. Done when `claude plugin validate .` passes and `/forge:status` answers in a session started with `claude --plugin-dir <path-to-forge>`. *(2026-10-04: validate passes with no warnings after adding marketplace `metadata.description`. `/forge:status` confirmed by the user in a live session.)*
- [x] **2. `refs`.** Convert, fetch, catalog, bib, status. Done when 5–10 real papers, including one math-heavy paper, convert cleanly, re-running costs nothing, and equations and tables survive (checked by hand against the PDFs). *(2026-10-04: `bin/refs` written; offline suite `tests/test_refs.py` passes (10 tests, OCR via a seeded cache). Live `fetch` checked on 6 real papers (4 arXiv incl. Adam and Transformer, AlphaFold via Nature, 1 paywalled to MISSING.md, 1 bogus ID dropped). Live `convert` on local Marker: 5 papers (83 pages) in ~11 min on Apple Silicon, 0 failures; re-run does nothing; offline suite now 12 tests. Spot check: Adam equations and Algorithm 1 come out as clean LaTeX, Transformer Table 2 is a correct Markdown table. User checked the output against the PDFs and approved it.)*
- [x] **3. `/forge:init` + templates.** Done when an empty folder becomes the project layout above, including `.gitignore`. *(2026-10-04: `bin/forge-init` does the work and the `init` skill only runs it. An empty folder becomes the layout above; re-running changes nothing; an existing `.gitignore` gets the forge block once; `git check-ignore` confirms paper folders, PDFs and the inbox are ignored while `catalog.md`, `references.bib`, `MISSING.md`, `pipeline/`, `tests/` and `src/` are tracked (`tests/test_init.py`, 4 tests). Templates written: `brief.md`, `design.md`, `plan.md`, `ledger.md`, `project.gitignore`. `/forge:init` confirmed by the user in a live session.)*
- [x] **3b. Guardrails and observability.** Stage banner, `pipeline/.stage`, stage-guard hook, `run-log.md`, approval files, `/forge:status` reading the log. Done when (a) the Interrogator provably starts as itself (banner, no Bash), (b) a deliberate attempt to write `src/` or fetch a paper outside `refs` during stage 1 is blocked, and (c) the run log shows every action of a stage-1 session. *(Added 2026-10-04. Cause: in the first trial run, `claude --agent forge:interrogator` silently gave a plain session, which reproduced the paper on its own: it read the PDF directly instead of through `refs`, copied the authors' code, wrote no brief, and had no gate or log. That output was moved to `~/Documents/Workspace/afchar-fourier-artifacts_pre-forge-run/` for later comparison. Diagnosis: that session's transcript has no `agentSetting`, while sessions started from the desktop app with the same command and version do; not reproducible here, so the guard must hold whether or not the agent is applied. Built: `hooks/forge-guard.py` + `hooks/hooks.json` (banner via SessionStart `systemMessage`, `pipeline/.stage`, per-agent allowlists keyed on the hook's `agent_type`, read-only policy for sessions without a stage, `pipeline/run-log.md`); `/forge:status` reads both. `initialPrompt` removed: it does not fire in interactive sessions. Verified: 27 offline tests; live, a plain session was blocked from creating a venv, writing `src/`, and fetching an arXiv PDF, while `ls` passed; the Interrogator, made to try, was blocked from writing `src/` and fetching the PDF. (a) confirmed in the user's own terminal: the second Interrogator run has `agentSetting`, 33 logged actions, 0 blocked. Approval files moved to step 4.)*
- [x] **4. Interrogator.** Done when a real small task yields an approved brief whose acceptance criteria are all testable, and the approval is recorded by the user's `/forge:approve brief` (a file with the brief's hash; any later edit invalidates it).
- [x] **5. `/forge:investigate`.** Done when it runs end to end on that brief and `index.md` points to real headings. *(2026-10-04: part 1 ran end to end on a scratch copy of the user's brief (5 sub-questions): gate, seed paper, 5 searchers, verify, `candidates.md`; 52 logged actions, 1 correct block. Fixed during the run: the guard blocked the harness `StructuredOutput` tool (now always allowed), and parallel `refs resolve` calls hit arXiv's rate limit and dropped real papers (now a cross-process 3.1 s arXiv throttle, a metadata cache in `~/.cache/forge/meta`, and "could not check, retry" separate from "does not exist"; the stress test resolves all 4 previously dropped papers). Part 2 on the user's real project exposed a silent failure: the agent's `refs convert` hit the Bash tool's default 2-minute timeout after 2 of 7 papers, a health check then misread the busy Marker server as down, and the workflow built `index.md` from the 3 converted papers anyway. Fixed: `refs convert --budget` (default 300 s) stops starting new papers and exits 3 while PDFs wait; the workflows loop `refs convert` (10-minute Bash timeout) until `refs status --json` reports an empty inbox, and `/forge:investigate-index` stops without indexing if anything stays unconverted; Marker counts as running when its port is open (`busy`). Rerun on the real project: 7 papers converted, index approved; check: 32 rows, all line ranges valid, 29/32 headings exact (3 bold run-in labels). Follow-ups: a deterministic row check in the index step; SONICS fetched but not indexed.)* Open: sub-questions about code (the authors' GitHub repo) can't be answered by a literature search.)*
- [x] **6. `/forge:plan`.** Done when the council runs, the ledger has a ruling for every critique, and the stop rule triggers correctly. *(2026-10-04: built as `workflows/plan.js` + `ozymandias` (opus), `j-jonah-jameson`, `smithers` (sonnet). The script numbers critiques per round (`R<r>-C<n>`), sets aside critiques whose evidence doesn't point to an index row, reference key or brief/plan item, re-asks Ozymandias for any missing ruling and treats a still-missing one as accepted, writes the ledger itself, and applies the stop rule; a final revision handles what the last round accepted, and tests are written last. The guard keeps the critic and defender read-only and Ozymandias to design/plan/ledger/tests; `/forge:approve design` writes `pipeline/.tests-locked`, after which no one can write `tests/`. Index step check on the real project: 32 rows, all line ranges valid, 29/32 headings exact (3 are bold run-in labels), SONICS fetched but not indexed. Live run on a copy of the user's project: 3 rounds, 12 critiques (all with evidence), 11 accepted / 1 rejected, every critique has a response and a ruling in the ledger, stop rule fired at the round limit with 2 accepted majors, which the final revision lists in design.md's Risks as "not re-reviewed"; design.md 140 lines; 9 test files (28 tests, 27 specs) that compile; 0 guard blocks. Note: a `claude -p` test session stops background workflows after 600 s unless `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`; interactive sessions are unaffected.)*
- [ ] **7. `/forge:build`.** Done when a deliberate attempt to edit `tests/` is blocked by the stage guard, and a failing slice produces a blocker report instead of looping. *(2026-10-04: built as `workflows/build.js` + `mf-code`, `reviewer`, `bin/forge-test`, `bin/forge-build-status`, `lib/forge_build.py`. One slice per run, then stop for `/forge:approve slice-N`. `forge-test N` runs the checkpoint commands parsed from the approved plan.md (never the agent's), refuses if the design approval is stale or `tests/` differs from the fingerprint taken at `/forge:approve design` (checked before and after), and writes `pipeline/slices/slice-N.tests.json` with a file snapshot; the workflow's pass/fail verdict comes from that record; at most 3 attempts, then a blocker report; the plan's own stop conditions end the slice. `/forge:approve design` now covers design.md + plan.md; slice approvals chain and require a passing record. Verified: 48 offline tests (guard blocks agent writes to tests/, tampered tests fail forge-test, failing checkpoints can't be approved); live, slice 1 of the user's plan built on a project copy in 1 attempt, 9/9 tests pass (rerun independently), 1 correct block (`ls`). Not yet exercised live: the 3-attempt blocker path and the final review.)*
- [ ] **8. Dry run and publish.** One small real task end to end; push to GitHub; install with `/plugin marketplace add <user>/forge` and `/plugin install forge@forge`.

## 8. Assumptions and open questions

Assumptions: macOS or Linux shell; Python 3.10+; Homebrew and the Marker install above (Apple Silicon recommended); a current Claude Code with dynamic workflows enabled (on the Pro plan they are switched on in `/config`).

Open questions:
- Final plugin name. Renaming is free until step 8; after publishing, a rename breaks existing installs.
- Code references: briefs cite code (e.g. a paper's GitHub repo) that Investigate can't read. Candidate: `refs fetch` of a GitHub URL snapshots the repo's source into `references/<key>/` (no execution) so Pointer can index files and lines.
- `refs fetch` cannot yet rebuild paper folders from a committed `catalog.md` (the git decision assumes it can). Add `refs fetch --from-catalog`; PDFs that came in without an ID can't be refetched and must be copied by hand.
- MF-CODE: start on Sonnet; try Haiku with automatic escalation to Sonnet after 2 failed attempts once the pipeline is stable.

## 9. Sources this design rests on

- Anthropic, multi-agent research system: https://www.anthropic.com/engineering/multi-agent-research-system
- HumanLayer, from Research-Plan-Implement to CRISPY: https://www.zenml.io/llmops-database/evolution-from-rpi-to-crispy-multi-stage-workflow-for-production-coding-agents
- Sycophancy in multi-agent debate: https://arxiv.org/abs/2509.23055 and https://arxiv.org/abs/2509.05396
- ImpossibleBench, agents exploiting test cases: https://arxiv.org/pdf/2510.20270
- Claude Code docs: workflows https://code.claude.com/docs/en/workflows, subagents https://code.claude.com/docs/en/sub-agents.md, plugins https://code.claude.com/docs/en/plugins-reference, marketplaces https://code.claude.com/docs/en/plugin-marketplaces
