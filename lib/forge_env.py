"""The project environment, shared by bin/forge-env, bin/forge-probe and bin/forge-test.

The brief says which environment the user wants; Ozymandias writes its spec in
pipeline/env/ during Plan and builds it with `forge-env create`; approving the design
fingerprints pipeline/env/ together with design.md and plan.md, so the build stage runs
in exactly the environment the plan was made (and probed) in. The first spec found
decides the kind:

  pipeline/env/pixi.toml         pixi    env in pipeline/env/.pixi, commands run with `pixi run`
  pipeline/env/environment.yml   conda   prefix env in .forge-env/conda (conda, mamba or micromamba)
  pipeline/env/Dockerfile        docker  image forge-<project>:<spec hash>, project mounted at /work
  pipeline/env/requirements.txt  venv    .venv, pip install -r
  (no pipeline/env/)             venv    legacy projects: an existing .venv, created by hand

A Dockerfile line `LABEL forge.gpus="all"` adds `--gpus all` to docker run.
pipeline/.env-state.json records the spec fingerprint the environment was built from,
so a spec edited after `forge-env create` reads as out of date.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import uuid
from pathlib import Path

import forge_approvals as fa

ENV_DIR = "pipeline/env"
STATE = "pipeline/.env-state.json"
CONDA_PREFIX = ".forge-env/conda"
SPECS = (("pixi.toml", "pixi"), ("environment.yml", "conda"), ("environment.yaml", "conda"),
         ("Dockerfile", "docker"), ("requirements.txt", "venv"))
VENV_TOOLS = ("python", "python3", "pip", "pytest")
GPU_LABEL_RE = re.compile(r'(?m)^\s*LABEL\s+.*forge\.gpus\s*=\s*"?([\w,=]+)"?')


def detect(root: Path) -> dict:
    """{"kind": pixi|conda|docker|venv, "spec": path relative to root, or None for a legacy .venv}."""
    d = root / ENV_DIR
    for name, kind in SPECS:
        if (d / name).is_file():
            return {"kind": kind, "spec": f"{ENV_DIR}/{name}"}
    return {"kind": "venv", "spec": None}


def spec_sha(root: Path) -> str:
    return fa.dir_sha(root, ENV_DIR)


def _slug(root: Path) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "-", root.name.lower()).strip("-.") or "project"


def docker_tag(root: Path) -> str:
    return f"forge-{_slug(root)}:{spec_sha(root)[:12]}"


def conda_exe() -> str | None:
    for name in ("micromamba", "mamba", "conda"):
        if shutil.which(name):
            return shutil.which(name)
    if os.environ.get("CONDA_EXE") and Path(os.environ["CONDA_EXE"]).is_file():
        return os.environ["CONDA_EXE"]
    for base in ("miniforge3", "miniconda3", "mambaforge", "anaconda3"):
        p = Path.home() / base / "bin" / "conda"
        if p.is_file():
            return str(p)
    return None


def _built(root: Path, env: dict) -> bool:
    kind = env["kind"]
    if kind == "pixi":
        return (root / ENV_DIR / ".pixi").is_dir()
    if kind == "conda":
        return (root / CONDA_PREFIX / "conda-meta").is_dir()
    if kind == "docker":
        return shutil.which("docker") is not None and subprocess.run(
            ["docker", "image", "inspect", docker_tag(root)], capture_output=True).returncode == 0
    return (root / ".venv" / "bin" / "python").exists()


def status(root: Path) -> tuple[bool, str, dict]:
    """(ready, message, env). Ready means built, and built from the current spec."""
    env = detect(root)
    if env["spec"] is None:
        if _built(root, env):
            return True, "legacy .venv (no pipeline/env/ spec)", env
        return False, "no environment: pipeline/env/ has no spec and there is no .venv", env
    if not _built(root, env):
        return False, f"{env['kind']} environment from {env['spec']} is not built: run `forge-env create`", env
    try:
        state = json.loads((root / STATE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("spec_sha256") != spec_sha(root):
        return False, f"{env['spec']} changed since the environment was built: run `forge-env create`", env
    return True, f"{env['kind']} environment from {env['spec']}, built {state.get('created_at')}", env


def create_commands(root: Path, env: dict) -> list[list[str]]:
    kind, spec = env["kind"], env["spec"]
    frozen = fa.check(root, "design")[0]  # once approved, install exactly what was approved
    if kind == "pixi":
        cmd = ["pixi", "install", "--manifest-path", spec]
        if frozen and (root / ENV_DIR / "pixi.lock").is_file():
            cmd.append("--frozen")
        return [cmd]
    if kind == "conda":
        exe = conda_exe() or "conda"
        exists = (root / CONDA_PREFIX / "conda-meta").is_dir()
        if Path(exe).name == "micromamba":
            return [[exe, "install" if exists else "create", "-y", "-p", CONDA_PREFIX, "-f", spec]]
        if exists:
            return [[exe, "env", "update", "-p", CONDA_PREFIX, "-f", spec, "--prune"]]
        return [[exe, "env", "create", "-p", CONDA_PREFIX, "-f", spec]]
    if kind == "docker":
        return [["docker", "build", "-t", docker_tag(root), "-f", spec, ENV_DIR]]
    cmds = [] if (root / ".venv" / "bin" / "python").exists() else [["python3", "-m", "venv", ".venv"]]
    if spec:
        cmds.append([".venv/bin/python", "-m", "pip", "install", "-r", spec])
    return cmds


def missing_tool(env: dict) -> str | None:
    kind = env["kind"]
    if kind == "pixi" and not shutil.which("pixi"):
        return "pixi is not installed (https://pixi.sh)"
    if kind == "conda" and not conda_exe():
        return "no conda, mamba or micromamba found (https://conda-forge.org/download/)"
    if kind == "docker" and not shutil.which("docker"):
        return "docker is not installed"
    return None


def create(root: Path) -> tuple[bool, str]:
    """Build or update the environment from its spec, streaming the tool's output."""
    env = detect(root)
    why = missing_tool(env)
    if why:
        return False, why
    for cmd in create_commands(root, env):
        print("$ " + " ".join(cmd), flush=True)
        if subprocess.run(cmd, cwd=root).returncode != 0:
            return False, f"`{' '.join(cmd)}` failed"
    if env["spec"]:
        (root / STATE).write_text(json.dumps({
            "kind": env["kind"], "spec": env["spec"], "spec_sha256": spec_sha(root),
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        }, indent=1) + "\n", encoding="utf-8")
    return True, f"{env['kind']} environment ready ({env['spec'] or '.venv'})"


def wrap(root: Path, argv: list[str], env_vars: dict[str, str] | None = None,
         name: str | None = None) -> tuple[list[str], dict[str, str]]:
    """(command, process environment) that runs argv inside the project environment, from the project root."""
    env = detect(root)
    proc_env = {**os.environ, **(env_vars or {})}
    kind = env["kind"]
    if kind == "pixi":
        return ["pixi", "run", "--manifest-path", env["spec"], *argv], proc_env
    if kind == "conda":
        exe = conda_exe() or "conda"
        extra = [] if Path(exe).name == "micromamba" else ["--no-capture-output"]
        return [exe, "run", *extra, "-p", str(root / CONDA_PREFIX), *argv], proc_env
    if kind == "docker":
        cmd = ["docker", "run", "--rm", "--name", name or f"forge-run-{uuid.uuid4().hex[:8]}",
               "-v", f"{root}:/work", "-w", "/work", "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
        for k, v in (env_vars or {}).items():
            cmd += ["-e", f"{k}={v}"]
        m = GPU_LABEL_RE.search((root / env["spec"]).read_text(encoding="utf-8"))
        if m:
            cmd += ["--gpus", m.group(1)]
        return [*cmd, docker_tag(root), *argv], proc_env
    venv_bin = root / ".venv" / "bin"
    proc_env["PATH"] = f"{venv_bin}{os.pathsep}{proc_env.get('PATH', '')}"
    proc_env["VIRTUAL_ENV"] = str(root / ".venv")
    if argv and argv[0] in VENV_TOOLS and (venv_bin / argv[0]).exists():
        argv = [str(venv_bin / argv[0]), *argv[1:]]
    return list(argv), proc_env


def run(root: Path, argv: list[str], timeout: float, env_vars: dict[str, str] | None = None) -> tuple[int, str, bool]:
    """Run argv inside the environment with a wall-clock limit. (exit code, output, timed out)."""
    name = f"forge-run-{uuid.uuid4().hex[:8]}"
    cmd, proc_env = wrap(root, argv, env_vars, name)
    p = subprocess.Popen(cmd, cwd=root, env=proc_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace", start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        if detect(root)["kind"] == "docker":
            subprocess.run(["docker", "kill", name], capture_output=True)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return 124, (out or "") + f"\n[forge] timed out after {timeout:.0f}s and was stopped", True
