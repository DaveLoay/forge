# forge quick setup

From zero to your first approved brief in about 15 minutes. For what each stage does and why, see the [README](../README.md).

## Part A: once per machine

**1. Install the basics.** You need Python 3.10+, `git`, `curl` and [Claude Code](https://code.claude.com/docs/en/setup), logged in.

**2. Get forge and run its setup script.**

```bash
git clone git@github.com:DaveLoay/forge.git ~/forge
bash ~/forge/scripts/setup.sh --test
```

The script installs Marker (the free, local PDF-to-Markdown converter) into `~/.local/share/forge`, checks your GPU, and with `--test` converts one real paper end to end. Read its output: anything marked `todo` tells you what to do, and it never uses `sudo` itself.

- **NVIDIA GPU (Linux):** Marker runs its model in Docker, so you need Docker and the NVIDIA Container Toolkit. If your driver is older than CUDA 13, the script switches to a compatible image for you.
- **Mac:** `brew install llama.cpp`.
- The first conversion downloads several GB (model and container); later ones are fast.

The script also installs forge as a Claude Code plugin (so plain `claude` loads it everywhere) and puts the `forge` command in `~/.local/bin`.

**3. Turn on Dynamic workflows.** Start `claude`, type `/config`, and switch on **Dynamic workflows**. forge's stages are workflows and won't run without it.

**4. Optional: your paper pool.** If you already have converted papers (for example an Obsidian vault with one folder per paper), register it so forge copies papers from it instead of downloading them again:

```bash
bash ~/forge/scripts/setup.sh --pool "/path/to/your/vault"
```

## Part B: for each new project

Two places to type things:
- **Terminal**: your normal shell prompt (`$`), *outside* Claude Code. The `forge` commands go here.
- **Claude Code**: the session that `forge` opens for you. The `/forge:...` commands go here.

You never need to start `claude` yourself; `forge` does it.

**1. Create it and describe your idea.** In a **terminal** (not inside Claude Code):

```bash
forge new ~/my-project
```

This creates the folder, a git repository and the forge layout, then opens Claude Code with the **Interrogator** (the first line reads `forge · stage 1/5 · Interrogator`). Answer its questions. Got PDFs already? Drop them into `~/my-project/references/inbox/` and tell it. When the brief reads right, type in **Claude Code**:

```
/forge:approve brief
/exit
```

`/exit` closes Claude Code and brings you back to the terminal.

**2. Continue, one command at a time.** Back in the **terminal**:

```bash
cd ~/my-project
forge
```

`forge` opens Claude Code again, set up for where the project stands. In **Claude Code**, you only need two commands, repeated:

```
/forge:next                  runs the next stage
/forge:approve <name>        after you've read what it wrote; /forge:next tells you the name
```

What `/forge:next` runs, in order, and what you approve after each:

| Stage | You read | You approve |
|---|---|---|
| Find papers | `pipeline/candidates.md` (delete the papers you don't want) | `/forge:approve candidates` |
| Index them | `pipeline/index.md` | `/forge:approve index` |
| Design council | `pipeline/design.md` (and `ledger.md` if you want the debate) | `/forge:approve design` |
| Build one slice (repeats) | `pipeline/slices/slice-N.md` | `/forge:approve slice-N` |
| Final review | `pipeline/review.md` | done |

You can stay in this one Claude Code session until the project is done. If you close it, run `forge` in the project folder (terminal) to come back.

Lost? In the **terminal**, `forge status` (inside the project folder) tells you where the project stands and what to type next.

## Good to know

- **Run long stages inside `tmux` or `screen`** on a server, so `/forge:plan` or `/forge:build` keeps going if SSH drops.
- **Changing an approved file cancels its approval.** If you edit `brief.md` after approving it, approve it again before the next stage.
- **A plain session can only look.** Writing in a forge project is done by the stage agents. That is the guard doing its job, not a bug.
- **Paywalled papers** are listed in `references/MISSING.md`. Get the PDF yourself, drop it into `references/inbox/`, and run `~/forge/bin/refs convert` in the project folder.
- **Update forge** with `forge update`.

## When conversion fails

| Symptom | Fix |
|---|---|
| `vllm server failed to become healthy` | Run `bash ~/forge/scripts/setup.sh` again and follow its `todo` lines. It is usually a driver/CUDA mismatch or Docker without the NVIDIA runtime. |
| A conversion seems stuck | The first one downloads several GB. Watch `~/.local/share/forge/marker-server.log`. |
| The GPU stays busy after converting | The model container keeps running: `docker ps`, then `docker stop surya-vllm-<port>`. |
| You changed Marker settings | `~/forge/bin/refs marker stop`; the next conversion starts it with the new settings. |
