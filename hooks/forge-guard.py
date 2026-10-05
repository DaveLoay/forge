#!/usr/bin/env python3
"""forge-guard: the stage guard and run log for forge projects.

Called by hooks/hooks.json on SessionStart, PreToolUse and PostToolUse. It reads the
hook event from stdin and decides from `agent_type`, which Claude Code sets from
`--agent` (not from anything the model says):

  SessionStart  shows the user which forge stage is running (or that none is), and
                records it in pipeline/.stage
  PreToolUse    allows or blocks the tool call according to the stage's policy
  PostToolUse   appends the action to pipeline/run-log.md

Outside a forge project (no pipeline/ and references/ folder) it does nothing.
Set FORGE_GUARD=off in the environment to disable blocking (logging continues).
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))
import forge_approvals  # noqa: E402

# One entry per stage agent. `write` lists the only project paths it may create or edit
# (globs, relative to the project root). `bash` lists allowed command prefixes; None
# means no shell at all. Tools not listed in `tools` are blocked.
STAGES: dict[str, dict] = {
    "forge:interrogator": {
        "label": "stage 1/5 · Interrogator",
        "tools": {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "Write", "Edit", "ToolSearch", "Bash"},
        "write": ["pipeline/brief.md"],
        # seed papers: fetched and converted through refs, then read as Markdown
        "bash": ["refs fetch", "refs convert", "refs status", "refs marker status"],
        "pdf_downloads": False,
        "read_pdfs": False,
        "no_self_approval": True,
    },
    "forge:hungry-hippo": {
        "label": "stage 2/5 · Investigate · Hungry-hippo",
        "tools": {"Read", "Glob", "Grep", "Write", "Bash", "ToolSearch"},
        "write": ["pipeline/candidates.md"],
        "bash": ["forge-gate", "forge-build-status", "refs fetch", "refs convert", "refs resolve", "refs status", "refs marker status"],
        "pdf_downloads": False,
        "read_pdfs": False,
        "requires": "brief",
        # fetching the searched papers needs the user's approval of the candidate list
        "bash_requires": {"refs fetch --source curiosity": "candidates"},
    },
    "forge:mr-curiosity": {
        "label": "stage 2/5 · Investigate · Mr. Curiosity",
        "tools": {"Read", "Glob", "Grep", "WebSearch", "WebFetch", "Bash", "ToolSearch"},
        "write": [],
        "bash": ["refs resolve"],
        "pdf_downloads": False,
        "read_pdfs": False,
        "requires": "brief",
    },
    "forge:pointer": {
        "label": "stage 2/5 · Investigate · Pointer",
        "tools": {"Read", "Glob", "Grep", "Write", "ToolSearch"},
        "write": ["pipeline/index.md"],
        "bash": None,
        "pdf_downloads": False,
        "read_pdfs": False,
        "requires": "candidates",
    },
    "forge:ozymandias": {
        "label": "stage 3/5 · Plan · Ozymandias",
        "tools": {"Read", "Glob", "Grep", "Write", "Edit"},
        "write": ["pipeline/design.md", "pipeline/plan.md", "pipeline/ledger.md", "tests/**"],
        "bash": None,
        "pdf_downloads": False,
        "read_pdfs": False,
        "requires": "index",
    },
    "forge:j-jonah-jameson": {
        "label": "stage 3/5 · Plan · J. Jonah Jameson",
        "tools": {"Read", "Glob", "Grep"},
        "write": [],
        "bash": None,
        "read_pdfs": False,
        "requires": "index",
    },
    "forge:mf-code": {
        "label": "stage 5/5 · Build · MF-CODE",
        "tools": {"Read", "Glob", "Grep", "Write", "Edit", "Bash"},
        "write": ["src/**", "docs/**", "outputs/**", "pyproject.toml", "requirements*.txt",
                  "pipeline/slices/slice-*.md", "pipeline/build-log.md"],
        "bash": ["python3 -m venv .venv", ".venv/bin/pip install", ".venv/bin/python", "forge-test", "forge-build-status"],
        "pdf_downloads": False,
        "read_pdfs": False,
        "requires": "design",
    },
    "forge:reviewer": {
        "label": "stage 5/5 · Build · Reviewer",
        "tools": {"Read", "Glob", "Grep", "Write", "Bash"},
        "write": ["pipeline/review.md"],
        "bash": ["forge-build-status"],
        "read_pdfs": False,
        "requires": "design",
    },
    "forge:smithers": {
        "label": "stage 3/5 · Plan · Smithers",
        "tools": {"Read", "Glob", "Grep"},
        "write": [],
        "bash": None,
        "read_pdfs": False,
        "requires": "index",
    },
}
APPROVED_STATUS_RE = re.compile(r"(?m)^status:\s*approved")

# A session in a forge project without a stage agent: may look, not touch.
NO_STAGE = {
    "label": "no forge stage active",
    "protected": ["src/**", "tests/**", "references/**", "pipeline/**", "src", "tests", "references", "pipeline"],
    "bash_readonly": {"ls", "cat", "head", "tail", "wc", "find", "grep", "rg", "pwd", "echo", "file",
                      "du", "df", "stat", "tree", "less", "diff", "which", "type", "date", "true"},
    "git_readonly": {"status", "log", "diff", "show", "branch", "remote", "rev-parse", "ls-files"},
}

# Harness tools every agent needs: returning a structured result, loading tool schemas, task bookkeeping.
ALWAYS_ALLOWED = {"StructuredOutput", "ToolSearch", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Delete", "Rename", "CreateFolder"}
PDF_URL_RE = re.compile(r"\.pdf($|[?#])|arxiv\.org/pdf/|/pdf/|[?&]pdf=", re.I)
SHELL_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
SHELL_META_RE = re.compile(r"[;&|<>`\n]|\$\(")


# --------------------------------------------------------------------------- helpers

def project_root(cwd: str) -> Path | None:
    here = Path(cwd or ".").resolve()
    for d in [here, *here.parents]:
        if (d / "pipeline").is_dir() and (d / "references").is_dir():
            return d
    return None


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def rel(root: Path, path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        return str(p.resolve().relative_to(root))
    except ValueError:
        return None  # outside the project


def matches(relpath: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, g) for g in globs)


def log(root: Path, agent: str, tool: str, target: str, outcome: str) -> None:
    f = root / "pipeline" / "run-log.md"
    new = not f.exists()
    target = target.replace("|", "\\|").replace("\n", " ")
    if len(target) > 160:
        target = target[:157] + "..."
    with f.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("# Run log\n\nWritten by the forge guard hook, one line per action. Do not edit.\n\n"
                     "| time | agent | tool | target | outcome |\n|---|---|---|---|---|\n")
        fh.write(f"| {now()} | {agent} | {tool} | {target} | {outcome} |\n")


def describe(root: Path, ti: dict) -> str:
    for k in ("file_path", "notebook_path", "path"):
        if ti.get(k):
            return rel(root, ti[k]) or str(ti[k])
    for k in ("url", "command", "pattern", "query", "skill"):
        if ti.get(k):
            return str(ti[k])
    return json.dumps(ti)[:160] if ti else ""


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"forge guard: {reason}",
    }}))


def allow_silently() -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}))


def bash_is_readonly(cmd: str) -> bool:
    if re.search(r"(^|[^<>&0-9])>{1,2}|\btee\b|`|\$\(", cmd):
        return False
    for part in SHELL_SPLIT_RE.split(cmd.strip()):
        if not part:
            continue
        try:
            words = shlex.split(part)
        except ValueError:
            return False
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]  # VAR=value prefixes
        if not words:
            continue
        exe = os.path.basename(words[0])
        if exe == "git":
            if len(words) < 2 or words[1] not in NO_STAGE["git_readonly"]:
                return False
        elif exe in ("forge-gate", "forge-build-status"):
            continue
        elif exe in ("refs", "forge"):
            if len(words) < 2 or words[1] != "status":
                return False
        elif exe == "find":
            if any(w in ("-delete", "-exec", "-execdir", "-ok", "-fprint") for w in words):
                return False
        elif exe not in NO_STAGE["bash_readonly"]:
            return False
    return True


# --------------------------------------------------------------------------- events

def note_stage(root: Path, agent: str, stage: dict) -> None:
    """Record the stage agent that is acting now, for /forge:status."""
    f = root / "pipeline" / ".stage"
    try:
        if json.loads(f.read_text()).get("agent") == agent:
            return
    except (OSError, json.JSONDecodeError):
        pass
    f.write_text(json.dumps({"agent": agent, "stage": stage["label"], "started": now()}, indent=1) + "\n", encoding="utf-8")


def on_session_start(root: Path, ev: dict) -> None:
    agent = ev.get("agent_type") or ""
    stage = STAGES.get(agent)
    label = stage["label"] if stage else NO_STAGE["label"]
    (root / "pipeline" / ".stage").write_text(json.dumps({
        "agent": agent or None, "stage": label, "session_id": ev.get("session_id"), "started": now(),
    }, indent=1) + "\n", encoding="utf-8")
    log(root, agent or "(none)", "SessionStart", label, "session started")
    if stage:
        msg = f"forge · {label} · type anything to begin"
    else:
        shown = f"agent '{agent}'" if agent else "a plain Claude session"
        msg = (f"forge · {label} · this is {shown}, not a forge stage. The forge guard allows reading only: "
               "no writes to src/, tests/, references/ or pipeline/, no scripts, no paper downloads. "
               "Start a stage, e.g. `claude --agent forge:interrogator`.")
    print(json.dumps({"systemMessage": msg}))


def on_pre_tool_use(root: Path, ev: dict) -> None:
    agent = ev.get("agent_type") or ""
    tool = ev.get("tool_name") or ""
    ti = ev.get("tool_input") or {}
    who = agent or "(none)"
    target = describe(root, ti)
    stage = STAGES.get(agent)

    path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path")
    rp = rel(root, path) if path else None

    def block(reason: str) -> None:
        log(root, who, tool, target, f"BLOCKED: {reason}")
        if os.environ.get("FORGE_GUARD", "").lower() == "off":
            return  # logged, not enforced
        deny(reason)

    # Reading the plugin's own templates is always fine (it lives outside the project).
    if tool in {"Read", "Glob", "Grep"} and path and str(Path(path).resolve()).startswith(str(PLUGIN_ROOT / "templates")):
        allow_silently()
        return

    if tool in ALWAYS_ALLOWED:
        return

    # Tests are locked once the user approves the design: nobody writes tests/ after that.
    if tool in WRITE_TOOLS and rp is not None and matches(rp, ["tests", "tests/**"]) \
            and (root / "pipeline" / ".tests-locked").exists():
        return block("tests/ is locked (the design was approved). Tests can't be changed during the build; "
                     "a wrong test is a blocker for planning, not something to edit.")
    if stage:  # a forge stage agent: allowlist
        note_stage(root, agent, stage)
        if stage.get("requires"):
            ok, why = forge_approvals.check(root, stage["requires"])
            if not ok:
                return block(f"{stage['label']} cannot act yet: {why}.")
        if tool not in stage["tools"] or (tool == "Bash" and not stage["bash"]):
            return block(f"{stage['label']} may not use {tool}.")
        if tool == "Read" and not stage.get("read_pdfs", True) and str(path or "").lower().endswith(".pdf"):
            return block(f"{stage['label']} reads papers as Markdown (references/<key>/<key>.md), not as PDF.")
        if tool in WRITE_TOOLS:
            if rp is None or not matches(rp, stage["write"]):
                allowed = ", ".join(stage["write"]) or "no files"
                return block(f"{stage['label']} may only write {allowed}, not {rp or path}.")
            new_text = str(ti.get("content") or "") + str(ti.get("new_string") or "")
            if stage.get("no_self_approval") and APPROVED_STATUS_RE.search(new_text):
                return block("only the user approves the brief, with /forge:approve brief. Keep `status: draft`.")
        if tool == "Bash":
            cmd = ti.get("command", "").strip()
            words = cmd.split()
            if (SHELL_META_RE.search(cmd)
                    or not any(words[:len(p.split())] == p.split() for p in stage["bash"])):
                return block(f"{stage['label']} may only run single commands starting with: {', '.join(stage['bash'])}.")
            for prefix, gate in (stage.get("bash_requires") or {}).items():
                if words[:len(prefix.split())] == prefix.split() or (words[:2] == ["refs", "fetch"] and "curiosity" in words):
                    ok, why = forge_approvals.check(root, gate)
                    if not ok:
                        return block(f"{stage['label']} may not fetch the searched papers yet: {why}.")
        if tool == "WebFetch" and not stage["pdf_downloads"] and PDF_URL_RE.search(ti.get("url", "")):
            return block(f"{stage['label']} may not download papers; papers enter the project only through `refs`.")
        return

    # No stage agent: read-only inside the project.
    if tool in WRITE_TOOLS and rp is not None and matches(rp, NO_STAGE["protected"]):
        return block(f"no forge stage is active, so {rp} may not be changed. Start the stage that owns it.")
    if tool == "Bash" and not bash_is_readonly(ti.get("command", "")):
        return block("no forge stage is active, so only read-only shell commands are allowed (ls, cat, grep, git status, refs status, ...).")
    if tool == "WebFetch" and PDF_URL_RE.search(ti.get("url", "")):
        return block("papers enter the project only through `refs fetch` during /forge:investigate.")


def on_post_tool_use(root: Path, ev: dict) -> None:
    agent = ev.get("agent_type") or "(none)"
    tool = ev.get("tool_name") or ""
    if tool in {"ToolSearch"}:
        return
    resp = ev.get("tool_response")
    outcome = "ok"
    if isinstance(resp, dict) and (resp.get("is_error") or resp.get("error")):
        outcome = "error"
    log(root, agent, tool, describe(root, ev.get("tool_input") or {}), outcome)


def main() -> int:
    try:
        ev = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    root = project_root(ev.get("cwd", ""))
    if root is None:
        return 0
    name = ev.get("hook_event_name")
    if name == "SessionStart":
        on_session_start(root, ev)
    elif name == "PreToolUse":
        on_pre_tool_use(root, ev)
    elif name == "PostToolUse":
        on_post_tool_use(root, ev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
