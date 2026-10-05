"""What comes next in a forge project, decided from files only. Shared by bin/forge
(the launcher) and the /forge:next skill, so the next step is chosen by code.

next_step(root) returns a dict:
  action    "interrogator" | "workflow" | "approve" | "done"
  stage     e.g. "stage 2/5 · Investigate"
  workflow  workflow name when action is "workflow" (investigate, investigate-index, plan, build)
  gate      gate name when action is "approve" (brief, candidates, index, design, slice-N)
  read      files to read before approving (approve only)
  say       one plain sentence for the user
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import forge_approvals as fa
import forge_build as fb

_BUILD_STATUS = Path(__file__).resolve().parents[1] / "bin" / "forge-build-status"


def _build_status(root: Path) -> dict:
    # bin/forge-build-status has no .py suffix; load its status() so the logic stays in one place.
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("forge_build_status", str(_BUILD_STATUS))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod.status(root)


def _approve(stage: str, gate: str, read: list[str], why: str) -> dict:
    files = " and ".join(f"`{r}`" for r in read)
    return {"action": "approve", "stage": stage, "gate": gate, "read": read,
            "say": f"{why} Read {files}; if it is right, type `/forge:approve {gate}`."}


def _workflow(stage: str, name: str, why: str) -> dict:
    return {"action": "workflow", "stage": stage, "workflow": name,
            "say": f"{why} Type `/forge:next` to run `/forge:{name}`."}


def next_step(root: Path) -> dict:
    p = root / "pipeline"

    ok, why = fa.check(root, "brief")
    if not ok:
        if (p / "brief.md").is_file() and (p / "approvals" / "brief.json").is_file():
            return _approve("stage 1/5 · Interrogate", "brief", ["pipeline/brief.md"],
                            f"The brief changed after it was approved ({why}).")
        return {"action": "interrogator", "stage": "stage 1/5 · Interrogate",
                "say": "Write the brief with the Interrogator (`forge` in this folder opens it). "
                       "When the brief reads right, type `/forge:approve brief` there."}

    ok, why = fa.check(root, "candidates")
    if not ok:
        if not (p / "candidates.md").is_file():
            return _workflow("stage 2/5 · Investigate", "investigate",
                             "The brief is approved; time to search for papers.")
        return _approve("stage 2/5 · Investigate", "candidates", ["pipeline/candidates.md"],
                        "The candidate papers are listed. Delete the rows you don't want.")

    ok, why = fa.check(root, "index")
    if not ok:
        if not (p / "index.md").is_file():
            return _workflow("stage 2/5 · Investigate", "investigate-index",
                             "The candidate list is approved; time to bring in the papers and index them.")
        return _approve("stage 2/5 · Investigate", "index", ["pipeline/index.md"],
                        "The index of passages is written.")

    ok, why = fa.check(root, "design")
    if not ok:
        if not ((p / "design.md").is_file() and (p / "plan.md").is_file() and (p / "ledger.md").is_file()):
            return _workflow("stage 3/5 · Plan", "plan", "The index is approved; time for the design council.")
        return _approve("stage 4/5 · Review the design", "design", ["pipeline/design.md", "pipeline/plan.md"],
                        "The design is ready (the debate is in `pipeline/ledger.md`). "
                        "Approving it also locks `tests/`.")

    st = _build_status(root)
    if not st["tests_intact"]:
        return {"action": "done", "stage": "stage 5/5 · Build",
                "say": f"Stopped: {st['tests_lock']}. Restore `tests/`, or re-plan and approve the design again."}
    if not st["slices"]:
        return {"action": "done", "stage": "stage 5/5 · Build",
                "say": "`pipeline/plan.md` has no slices, so there is nothing to build. Re-plan with `/forge:plan`."}
    if st["all_approved"]:
        if (p / "review.md").is_file():
            return {"action": "done", "stage": "finished",
                    "say": "Every slice is approved and the final review is written. Read `pipeline/review.md`."}
        return _workflow("stage 5/5 · Build", "build", "Every slice is approved; time for the final review.")
    n = st["next"]
    s = next(x for x in st["slices"] if x["n"] == n)
    total = len(st["slices"])
    if s["tests"] and s["tests"]["passed"] and s["report"]:
        return _approve("stage 5/5 · Build", f"slice-{n}", [f"pipeline/slices/slice-{n}.md"],
                        f"Slice {n} of {total} ({s['name']}) is built and passed its tests.")
    if s["tests"] and s["report"]:
        return _workflow("stage 5/5 · Build", "build",
                         f"Slice {n} of {total} ({s['name']}) did not pass; read its blocker report in "
                         f"`pipeline/slices/slice-{n}.md` first (a planning problem means `/forge:plan` again).")
    return _workflow("stage 5/5 · Build", "build", f"Time to build slice {n} of {total} ({s['name']}).")


def find_root(start: Path | None = None) -> Path | None:
    return fb.find_root(start)
