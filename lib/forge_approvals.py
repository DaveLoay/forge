"""Human approval gates, shared by bin/forge-approve, bin/forge-gate, bin/forge-test,
bin/forge-build-status and hooks/forge-guard.py.

An approval is pipeline/approvals/<gate>.json holding the SHA-256 of the approved file(s).
It is valid only while the files still have that exact content, so any edit after
approval withdraws it. Gates form a chain: each needs the one before it.

Gates: brief, candidates, index, design (design.md + plan.md, plus the environment spec in
pipeline/env/ when there is one), slice-1, slice-2, ...
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

# gate -> (files it approves, gate that must already be valid)
GATES: dict[str, tuple[list[str], str | None]] = {
    "brief": (["pipeline/brief.md"], None),
    "candidates": (["pipeline/candidates.md"], "brief"),
    "index": (["pipeline/index.md"], "candidates"),
    "design": (["pipeline/design.md", "pipeline/plan.md"], "index"),
}
SLICE_RE = re.compile(r"^slice-(\d+)$")
ENV_DIR = "pipeline/env"
# Built environments and caches inside pipeline/env/ are not part of the spec.
SKIP_PARTS = {".pixi", "__pycache__", ".DS_Store"}


def gate_spec(gate: str) -> tuple[list[str], str | None]:
    if gate in GATES:
        return GATES[gate]
    m = SLICE_RE.match(gate)
    if m:
        n = int(m.group(1))
        return [f"pipeline/slices/slice-{n}.md"], ("design" if n == 1 else f"slice-{n - 1}")
    raise KeyError(gate)


def gate_files(root: Path, gate: str) -> tuple[list[str], str | None]:
    """gate_spec, plus pipeline/env/ for the design gate when the project has an environment spec."""
    rels, before = gate_spec(gate)
    if gate == "design" and (root / ENV_DIR).is_dir():
        rels = [*rels, ENV_DIR]
    return rels, before


def known_gates() -> str:
    return ", ".join(GATES) + ", slice-N"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dir_sha(root: Path, rel: str) -> str:
    """Fingerprint of the files under a directory (paths and contents), ignoring SKIP_PARTS."""
    h = hashlib.sha256()
    base = root / rel
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and not SKIP_PARTS & set(p.relative_to(base).parts):
                h.update(f"{p.relative_to(root)}:{_sha_file(p)}\n".encode())
    return h.hexdigest()


def _sha(root: Path, rels: list[str]) -> str:
    if len(rels) == 1:  # single file: plain file hash (keeps older approvals valid)
        return _sha_file(root / rels[0])
    h = hashlib.sha256()
    for r in rels:
        h.update(f"{r}:{dir_sha(root, r) if (root / r).is_dir() else _sha_file(root / r)}\n".encode())
    return h.hexdigest()


def tests_sha(root: Path) -> str:
    """Fingerprint of everything under tests/ (paths and contents), ignoring caches."""
    h = hashlib.sha256()
    base = root / "tests"
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store":
                h.update(f"{p.relative_to(root)}:{_sha_file(p)}\n".encode())
    return h.hexdigest()


def tests_lock_state(root: Path) -> tuple[bool, bool, str]:
    """(locked, intact, message). Intact means tests/ still matches the fingerprint taken at lock time."""
    f = root / "pipeline" / ".tests-locked"
    if not f.is_file():
        return False, False, "tests/ is not locked yet (it is locked by /forge:approve design)"
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True, False, ("tests/ was locked by an older forge version without a fingerprint; "
                             "run /forge:approve design again to fingerprint it")
    if data.get("tests_sha256") != tests_sha(root):
        return True, False, "tests/ changed after it was locked"
    return True, True, f"tests/ locked on {data.get('locked_at')} and unchanged"


def approval_file(root: Path, gate: str) -> Path:
    return root / "pipeline" / "approvals" / f"{gate}.json"


def check(root: Path, gate: str) -> tuple[bool, str]:
    """(ok, reason). Checks the gate and, recursively, the gates before it."""
    try:
        rels, before = gate_files(root, gate)
    except KeyError:
        return False, f"unknown gate '{gate}' (known: {known_gates()})"
    if before:
        ok, why = check(root, before)
        if not ok:
            return False, why
    names = " + ".join(rels)
    rec = approval_file(root, gate)
    if not rec.is_file():
        return False, f"{names} has not been approved: run /forge:approve {gate}"
    missing = [r for r in rels if not (root / r).exists()]
    if missing:
        return False, f"{', '.join(missing)} was approved but no longer exists"
    data = json.loads(rec.read_text(encoding="utf-8"))
    if "files" not in data and len(rels) > 1:
        return False, (f"the {gate} approval from {data.get('approved_at')} was made by an older forge version that "
                       f"covered only {data.get('file')}; run /forge:approve {gate} again so it also covers {', '.join(rels[1:])}")
    if data.get("sha256") != _sha(root, rels):
        return False, f"{names} changed after it was approved on {data.get('approved_at')}: review it and run /forge:approve {gate} again"
    return True, f"{names} approved on {data.get('approved_at')}"


def approve(root: Path, gate: str) -> str:
    try:
        rels, before = gate_files(root, gate)
    except KeyError:
        raise ValueError(f"unknown gate '{gate}' (known: {known_gates()})") from None
    if before:
        ok, why = check(root, before)
        if not ok:
            raise ValueError(f"cannot approve {gate} yet: {why}")
    missing = [r for r in rels if not (root / r).exists()]
    if missing:
        raise ValueError(f"{', '.join(missing)} does not exist yet")
    if SLICE_RE.match(gate):
        _require_slice_passed(root, gate)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    if gate == "brief":
        _mark_brief_approved(root / rels[0], stamp[:10])
    if gate == "design":
        # Approving the design locks the tests for the build stage, with a fingerprint
        # that forge-test checks before every run.
        (root / "pipeline" / ".tests-locked").write_text(json.dumps(
            {"locked_at": stamp, "by": "/forge:approve design", "tests_sha256": tests_sha(root)}, indent=1) + "\n",
            encoding="utf-8")
    rec = approval_file(root, gate)
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps({"gate": gate, "files": rels, "sha256": _sha(root, rels), "approved_at": stamp}, indent=1) + "\n",
                   encoding="utf-8")
    extra = " and locked tests/" if gate == "design" else ""
    return f"approved {' + '.join(rels)}{extra} ({stamp})"


def _require_slice_passed(root: Path, gate: str) -> None:
    n = SLICE_RE.match(gate).group(1)
    f = root / "pipeline" / "slices" / f"slice-{n}.tests.json"
    if not f.is_file():
        raise ValueError(f"slice {n} has no test record; /forge:build runs its checkpoint with forge-test")
    data = json.loads(f.read_text(encoding="utf-8"))
    if not data.get("passed"):
        raise ValueError(f"slice {n}'s checkpoint did not pass ({data.get('reason') or 'see ' + str(f.relative_to(root))})")
    locked, intact, why = tests_lock_state(root)
    if not intact:
        raise ValueError(f"cannot approve slice {n}: {why}")


def _mark_brief_approved(path: Path, day: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("pipeline/brief.md has no frontmatter")
    text = re.sub(r"(?m)^status:[^\n#]*", "status: approved ", text, count=1)
    text = re.sub(r"(?m)^approved:[^\n#]*", f"approved: {day} ", text, count=1)
    path.write_text(text, encoding="utf-8")
