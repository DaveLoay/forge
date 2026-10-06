"""Tests for the build stage: lib/forge_build.py, bin/forge-test, bin/forge-build-status, slice gates, guard."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "lib"))
import forge_build as fb  # noqa: E402

PLAN = """---
round: 1
---
# Plan

## Slices

### Slice 1: First (AC-1)

- Build: `a.py`
- Checkpoint: `python -c "print(1)"` passes T-1
- Done when: ok

### Slice 2: Second

- Build: `b.py`
- Checkpoint: `python -c "import sys; sys.exit(3)"`; then
  `python -c "print(2)"` and `pytest -q tests/x.py`
- Done when: ok

## To-do
"""


def run(cmd, cwd):
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / cmd[0]), *cmd[1:]], cwd=cwd, capture_output=True, text=True)


def guard(root, agent, tool, ti):
    ev = {"hook_event_name": "PreToolUse", "cwd": str(root), "agent_type": agent, "tool_name": tool, "tool_input": ti}
    r = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "forge-guard.py")], input=json.dumps(ev), capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "pass")


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        subprocess.run([sys.executable, str(PLUGIN / "bin" / "forge-init"), str(self.root)], check=True, capture_output=True)
        pl = self.root / "pipeline"
        (pl / "brief.md").write_text("---\nstatus: draft\napproved: null\n---\n")
        for f in ("candidates", "index", "design"):
            (pl / f"{f}.md").write_text(f)
        (pl / "plan.md").write_text(PLAN)
        (self.root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
        for g in ("brief", "candidates", "index", "design"):
            self.assertEqual(run(["forge-approve", g], self.root).returncode, 0, g)
        (self.root / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, self.root / ".venv" / "bin" / "python")

    def tearDown(self):
        self.tmp.cleanup()

    def status(self):
        return json.loads(run(["forge-build-status", "--json"], self.root).stdout)

    def test_parse_slices(self):
        s = fb.parse_slices(PLAN)
        self.assertEqual([x["n"] for x in s], [1, 2])
        self.assertEqual(s[0]["commands"], ['python -c "print(1)"'])
        self.assertEqual(s[1]["commands"], ['python -c "import sys; sys.exit(3)"', 'python -c "print(2)"', "pytest -q tests/x.py"])

    def test_pass_record_and_slice_approval(self):
        st = self.status()
        self.assertTrue(st["design_ok"] and st["tests_intact"])
        self.assertEqual(st["next"], 1)
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src" / "a.py").write_text("x = 1\n")
        r = run(["forge-test", "1"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout)
        rec = json.loads((self.root / "pipeline/slices/slice-1.tests.json").read_text())
        self.assertTrue(rec["passed"])
        self.assertIn("src/a.py", rec["files"])
        # approval needs the report file too
        self.assertEqual(run(["forge-approve", "slice-1"], self.root).returncode, 1)
        (self.root / "pipeline/slices/slice-1.md").write_text("report")
        self.assertEqual(run(["forge-approve", "slice-1"], self.root).returncode, 0)
        st = self.status()
        self.assertEqual(st["next"], 2)
        self.assertEqual(st["slices"][0]["changes"]["added"], ["src/a.py"])

    def test_failure_is_recorded_and_blocks_approval(self):
        self.assertEqual(run(["forge-test", "1"], self.root).returncode, 0)
        (self.root / "pipeline/slices/slice-1.md").write_text("r")
        run(["forge-approve", "slice-1"], self.root)
        r = run(["forge-test", "2"], self.root)
        self.assertEqual(r.returncode, 1)
        rec = json.loads((self.root / "pipeline/slices/slice-2.tests.json").read_text())
        self.assertFalse(rec["passed"])
        self.assertEqual([c["exit"] for c in rec["commands"]], [3])  # stops at the first failing command
        (self.root / "pipeline/slices/slice-2.md").write_text("r")
        out = run(["forge-approve", "slice-2"], self.root)
        self.assertEqual(out.returncode, 1)
        self.assertIn("did not pass", out.stdout)

    def test_tampered_tests_fail_the_checkpoint(self):
        (self.root / "tests" / "test_x.py").write_text("def test_x():\n    pass  # loosened\n")
        r = run(["forge-test", "1"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/ changed after it was locked", r.stdout)
        self.assertFalse(self.status()["tests_intact"])

    def test_slice_gates_chain(self):
        (self.root / "pipeline/slices").mkdir(parents=True, exist_ok=True)
        (self.root / "pipeline/slices/slice-2.md").write_text("r")
        out = run(["forge-approve", "slice-2"], self.root)
        self.assertEqual(out.returncode, 1)
        self.assertIn("slice-1", out.stdout)

    def test_guard_for_build_agents(self):
        MF = "forge:mf-code"
        for p in ("src/fourier_artifacts/x.py", "docs/derivation.md", "pyproject.toml", "pipeline/slices/slice-1.md", "pipeline/build-log.md"):
            self.assertEqual(guard(self.root, MF, "Write", {"file_path": p}), "pass", p)
        for p in ("tests/test_x.py", "pipeline/plan.md", "pipeline/slices/slice-1.tests.json", "pipeline/approvals/slice-1.json", "references/x.md"):
            self.assertEqual(guard(self.root, MF, "Write", {"file_path": p}), "deny", p)
        for c in ("forge-env run python -m pytest tests/test_x.py -q", "forge-env status", "forge-test 1", "forge-build-status --json"):
            self.assertEqual(guard(self.root, MF, "Bash", {"command": c}), "pass", c)
        for c in ("pip install numpy", "forge-approve slice-1", "forge-env run python x.py > tests/a", "rm -rf tests", "python3 x.py",
                  "python3 -m venv .venv", ".venv/bin/pip install numpy"):
            self.assertEqual(guard(self.root, MF, "Bash", {"command": c}), "deny", c)
        self.assertEqual(guard(self.root, "forge:reviewer", "Write", {"file_path": "pipeline/review.md"}), "pass")
        self.assertEqual(guard(self.root, "forge:reviewer", "Write", {"file_path": "src/a.py"}), "deny")


if __name__ == "__main__":
    unittest.main()
