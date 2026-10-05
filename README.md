# forge

forge turns a research idea into working, tested code, one checked step at a time. You stay in control: every stage stops for your approval, every action is logged, and the rules each AI agent must follow are enforced by code, not by asking it nicely.

```
 idea ──► 1 Interrogator ──► 2 Investigate ──► 3 Plan ──► 4 You review ──► 5 Build ──► review
          brief.md           papers + index     design,      the design      code, slice
                                                plan, tests                   by slice
```

## What forge is, in plain English

forge is a **plugin for Claude Code**. A plugin is a folder that Claude Code loads to gain new abilities. forge uses five kinds of building blocks that Claude Code understands:

| Building block | What it is | In forge |
|---|---|---|
| **Agents** (`agents/*.md`) | A specialised AI worker: a role description, a model (Opus, Sonnet or Haiku) and a list of tools it may use. | Interrogator, Hungry-hippo, Mr. Curiosity, Pointer, Ozymandias, J. Jonah Jameson, Smithers, MF-CODE, Reviewer |
| **Skills** (`skills/*/SKILL.md`) | Commands you type, such as `/forge:status`. | `/forge:init`, `/forge:status`, `/forge:approve` |
| **Workflows** (`workflows/*.js`) | Small JavaScript programs that run agents in a fixed order. The *script*, not the AI, decides what runs next, so steps can't be skipped. | `/forge:investigate`, `/forge:investigate-index`, `/forge:plan`, `/forge:build` |
| **Hooks** (`hooks/`) | Code that Claude Code runs before and after every action an agent takes. It can block the action. | the **forge guard**: it allows each agent only its own job and writes the logbook |
| **Tools** (`bin/`) | Ordinary command-line programs that agents (and you) can run. | `refs` (papers), `forge-init`, `forge-approve`, `forge-gate`, `forge-test`, `forge-build-status` |

So forge is not one thing. It is a set of agents with narrow jobs, workflows that run them in order, a guard that keeps them in their lane, and tools that do the parts that should be exact (downloading, converting, checking, testing) without AI.

## The pipeline, step by step

Each stage reads the files the previous stage wrote, and refuses to start until you've approved them.

### 1. Interrogator: from idea to brief

You talk with the Interrogator until your idea is precise. If you name papers, it fetches and converts them (through `refs`) and reads them, so its questions are informed. It writes `pipeline/brief.md`: goal, non-goals, hypothesis, acceptance criteria that can be tested, constraints, research sub-questions, seed references.

- Start it: `claude --agent forge:interrogator` (in the project folder)
- Approve: `/forge:approve brief`

### 2. Investigate: from brief to the right passages in the right papers

- `/forge:investigate`: checks your seed papers, runs one **Mr. Curiosity** search per research sub-question, verifies that every paper ID really exists (Crossref or arXiv), and writes `pipeline/candidates.md`. You keep or drop papers there, then `/forge:approve candidates`.
- `/forge:investigate-index`: **Hungry-hippo** brings in the papers you kept (from your paper pool if they're there, otherwise download and convert to Markdown), then **Pointer** agents write `pipeline/index.md`: for each sub-question, which paper, section and lines answer it. Review it, then `/forge:approve index`.

### 3. Plan: a council argues about the design

`/forge:plan` runs up to 3 rounds of:

1. **Ozymandias** (Opus) drafts or revises `pipeline/design.md` (for you) and `pipeline/plan.md` (for the builder).
2. **J. Jonah Jameson** criticises them. Every critique needs evidence: an index row or a paper.
3. **Smithers** rebuts each critique with evidence or concedes it.
4. **Ozymandias** rules on every critique: accepted or rejected, with a reason.

It stops when no accepted major problem remains, or after 3 rounds. Everything is recorded in `pipeline/ledger.md`. Then Ozymandias writes the tests in `tests/`.

### 4. You review the design

Read `pipeline/design.md` (short, written for you) and, if you want the debate, `pipeline/ledger.md`. If you agree: `/forge:approve design`. That also **locks `tests/`**: from then on no agent can change a test.

### 5. Build: one slice at a time

`/forge:build` builds the next slice of the plan. **MF-CODE** writes the code. Then `forge-test` runs the slice's tests exactly as the approved plan states them, and records the result itself, so the agent can't claim a pass. At most 3 attempts; after that it stops with a blocker report instead of looping. Read `pipeline/slices/slice-N.md`, then `/forge:approve slice-N`, then `/forge:build` again. After the last slice, a **Reviewer** compares the code with the plan and writes `pipeline/review.md`.

At any point, `/forge:status` tells you where the project stands and what to do next.

## How forge keeps control

- **One job per agent, enforced.** The guard hook knows which agent is acting (Claude Code tells it) and blocks anything outside that agent's job: the Interrogator can only write the brief, the critic can only read, the builder can't touch `tests/`, and a plain Claude session in a forge project can only look.
- **Approvals are fingerprints.** `/forge:approve` stores a fingerprint of the approved files. If anything changes afterwards, the approval no longer counts and the next stage won't start. Only your typed command can approve; agents are blocked from doing it.
- **The logbook.** Every action of every agent, including blocked attempts, is a line in `pipeline/run-log.md`.
- **Exact work is done by code.** Downloading, converting, checking paper IDs and running tests are done by programs, not by the AI.
- **Visible progress.** Workflows show their phases live in `/workflows`.

## Papers: `refs`, Marker and the paper pool

Agents never read PDFs. Papers are converted to Markdown once, and agents read the Markdown, which saves a lot of tokens.

- `refs fetch <DOI or arXiv ID>`: first looks in your **paper pool**, then downloads open-access PDFs. Paywalled ones go to `references/MISSING.md`; drop the PDF into `references/inbox/` yourself.
- `refs convert`: converts the PDFs in `references/inbox/` to Markdown with **Marker**, a free program that runs on your own computer (no paid service). The Marker server starts automatically. Results are cached, so a paper is never converted twice.
- `refs status`, `refs resolve <IDs>`, `refs catalog`, `refs bib`.

**The paper pool** is a folder of papers you've already converted, such as your Obsidian vault: one folder per paper, with a `.md` file and an `assets/` folder. `refs fetch` copies a paper from the pool when it finds it (by arXiv ID, DOI or title), with no download and no conversion.

```bash
refs pool add "/Users/daveloay/Documents/Obsidian Vault"   # once per machine
refs pool list                                            # what's in it
refs pool find sonics                                     # search by title words
```

## Files in a forge project

```
my-project/
  references/            papers: one folder per paper (<key>.md, images/, maybe <key>.pdf)
    inbox/               drop PDFs here
    catalog.md  references.bib  MISSING.md
  pipeline/
    brief.md  candidates.md  index.md  design.md  plan.md  ledger.md
    slices/              one report and one test record per build slice
    approvals/           your approvals (fingerprints)
    run-log.md           the logbook
    build-log.md  review.md
  tests/                 written by the plan stage, locked when you approve the design
  src/                   the code
```

## Setting up on a new machine

forge needs:

1. **Claude Code**, logged in, with **Dynamic workflows** turned on (`/config` → Dynamic workflows; on the Pro plan it starts switched off).
2. **Python 3.10+** and `curl` (forge itself uses only Python's standard library).
3. **Marker** for converting PDFs (free, local):
   ```bash
   python3 -m venv ~/.local/share/forge/marker-venv
   ~/.local/share/forge/marker-venv/bin/pip install marker-pdf==2.0.0 fastapi uvicorn python-multipart
   ```
   plus `llama.cpp` (`brew install llama.cpp` on macOS; on Linux, see "Running on a server" below).
4. **The forge folder**, then in each project:
   ```bash
   claude --plugin-dir /path/to/forge
   ```
   and `/forge:init` once, to create the project layout.
5. Optional: `refs pool add <folder>` for your paper pool.

## Running on a server

forge has no macOS-specific parts at runtime. On a Linux server:

```bash
git clone git@github.com:DaveLoay/forge.git ~/forge
bash ~/forge/scripts/setup.sh --pool "/path/to/your/vault" --test
```

`setup.sh` checks Python, git and Claude Code, installs Marker, tells you how Marker will use the GPU, registers the paper pool, and with `--test` converts one real paper end to end. It never uses `sudo`; anything that needs root is printed for you to run. Update forge later with `git -C ~/forge pull`. Then, in a project on the server: `claude --plugin-dir ~/forge`.

What else changes on a server:

- **Get forge onto the server.** Simplest: keep forge in a (private) GitHub repository and `git clone` it on the server, then `git pull` to update. Or install it as a plugin (`/plugin marketplace add <you>/forge`, `/plugin install forge@forge`), which updates everywhere with `/plugin marketplace update forge`.
- **Claude Code on the server.** Install it there, log in once, and turn on Dynamic workflows in `/config`. Run it inside `tmux` or `screen`, so a long `/forge:plan` or `/forge:build` keeps running if your SSH connection drops.
- **Marker on the server.** With an NVIDIA GPU, Marker runs its model in a Docker container (vLLM), so the server needs Docker and the NVIDIA Container Toolkit; the first conversion downloads the container and the model (several GB). Without Docker, build `llama.cpp` with CUDA and set `export SURYA_INFERENCE_BACKEND=llamacpp`. `setup.sh` tells you which applies.
- **The paper pool on the server.** Your Obsidian vault lives on your Mac, so the server needs a copy of the papers folder, kept in sync with `rsync`, Syncthing or git. Then run `refs pool add <that folder>` on the server.
- **Data paths.** Plans and tests may name data folders (this project's plan names `/Users/daveloay/Documents/raw_materials`). On the server, keep the data at a path the brief names, or say the server path when you talk to the Interrogator.

## Reference

| Command | What it does |
|---|---|
| `/forge:init` | Create the forge layout in the current folder |
| `/forge:status` | Where the project stands, approvals, last logbook lines, next step |
| `claude --agent forge:interrogator` | Stage 1 |
| `/forge:investigate`, `/forge:investigate-index` | Stage 2 (two parts, with your approval in between) |
| `/forge:plan` | Stage 3 |
| `/forge:build` | Stage 5, one slice per run; final review after the last |
| `/forge:approve <brief, candidates, index, design, slice-N>` | Record your approval |

For developers: the design and its history are in [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md). Run the tests with `python3 -m unittest discover -s tests`, and check the plugin with `claude plugin validate .`.
