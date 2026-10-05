"""Build-stage helpers shared by bin/forge-test and bin/forge-build-status.

Slices and their checkpoint commands come from the approved pipeline/plan.md:

    ### Slice 2: Derivation document (AC-5)
    - Build: ...
    - Checkpoint: `pytest tests/test_derivation_doc.py` passes T-7

Every backticked command on the Checkpoint line (and its continuation lines) is run.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SLICE_HEAD_RE = re.compile(r"^###\s+Slice\s+(\d+)\s*[:.\-–]\s*(.+?)\s*$")
CMD_RE = re.compile(r"`([^`]+)`")
RUNNABLE = ("pytest", "python", "python3")
# Project files a slice may change; snapshotted after every checkpoint so slices can be diffed.
SNAPSHOT_GLOBS = ("src/**/*", "docs/**/*", "pyproject.toml", "requirements*.txt", "setup.cfg", "setup.py")


def find_root(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    return next((d for d in [here, *here.parents] if (d / "pipeline").is_dir() and (d / "references").is_dir()), None)


def parse_slices(plan_text: str) -> list[dict]:
    slices: list[dict] = []
    cur = None
    in_checkpoint = False
    for line in plan_text.splitlines():
        m = SLICE_HEAD_RE.match(line)
        if m:
            cur = {"n": int(m.group(1)), "name": m.group(2), "checkpoint": "", "commands": []}
            slices.append(cur)
            in_checkpoint = False
            continue
        if cur is None:
            continue
        if line.startswith("## ") or line.startswith("### "):
            cur, in_checkpoint = None, False
            continue
        stripped = line.strip()
        if re.match(r"^-\s*Checkpoint\s*:", stripped):
            in_checkpoint = True
            cur["checkpoint"] = stripped.split(":", 1)[1].strip()
        elif in_checkpoint and stripped and not stripped.startswith("- "):
            cur["checkpoint"] += " " + stripped  # continuation line
        else:
            in_checkpoint = False
            continue
        cur["commands"] = [c.strip() for c in CMD_RE.findall(cur["checkpoint"])
                           if c.strip().split()[0] in RUNNABLE]
    return slices


def snapshot(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for pattern in SNAPSHOT_GLOBS:
        for p in root.glob(pattern):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name not in (".DS_Store", ".gitkeep"):
                files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "changed": sorted(k for k in set(after) & set(before) if after[k] != before[k]),
        "removed": sorted(set(before) - set(after)),
    }


def slices_dir(root: Path) -> Path:
    d = root / "pipeline" / "slices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_record(root: Path, n: int) -> dict | None:
    f = root / "pipeline" / "slices" / f"slice-{n}.tests.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
