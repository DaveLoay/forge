"""Tests for lib/forge_next.py and bin/forge status (the next step of a project)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]

PLAN = """# Plan

## Slices

### Slice 1: First

- Build: `a.py`
- Checkpoint: `python -c "print(1)"`
- Done when: ok
"""


def run(cmd, cwd):
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / cmd[0]), *cmd[1:]], cwd=cwd, capture_output=True, text=True)


class NextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        subprocess.run([sys.executable, str(PLUGIN / "bin" / "forge-init"), str(self.root)], check=True, capture_output=True)
        self.pl = self.root / "pipeline"

    def tearDown(self):
        self.tmp.cleanup()

    def step(self):
        r = run(["forge", "status", "--json"], self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def write(self, name, text=None):
        (self.pl / name).write_text(text or name)

    def approve(self, gate):
        self.assertEqual(run(["forge-approve", gate], self.root).returncode, 0, gate)

    def test_walks_the_pipeline(self):
        self.assertEqual(self.step()["action"], "interrogator")
        self.write("brief.md", "---\nstatus: draft\napproved: null\n---\n")
        self.assertEqual(self.step()["action"], "interrogator")
        self.approve("brief")
        self.assertEqual((self.step()["action"], self.step()["workflow"]), ("workflow", "investigate"))
        self.write("candidates.md")
        self.assertEqual((self.step()["action"], self.step()["gate"]), ("approve", "candidates"))
        self.approve("candidates")
        self.assertEqual(self.step()["workflow"], "investigate-index")
        self.write("index.md")
        self.assertEqual(self.step()["gate"], "index")
        self.approve("index")
        self.assertEqual(self.step()["workflow"], "plan")
        for f in ("design.md", "ledger.md"):
            self.write(f)
        self.write("plan.md", PLAN)
        self.assertEqual(self.step()["gate"], "design")
        self.approve("design")
        s = self.step()
        self.assertEqual((s["action"], s["workflow"]), ("workflow", "build"))
        self.assertIn("slice 1 of 1", s["say"])

    def test_changed_brief_asks_for_reapproval(self):
        self.write("brief.md", "---\nstatus: draft\napproved: null\n---\n")
        self.approve("brief")
        self.write("brief.md", "---\nstatus: approved\napproved: x\n---\nedited\n")
        s = self.step()
        self.assertEqual((s["action"], s["gate"]), ("approve", "brief"))

    def test_outside_a_project(self):
        r = run(["forge", "status"], self.tmp.name)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("forge new", r.stderr)

    def test_guard_allows_forge_status_in_plain_session(self):
        ev = {"hook_event_name": "PreToolUse", "cwd": str(self.root), "agent_type": "", "tool_name": "Bash",
              "tool_input": {"command": "forge status"}}
        r = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "forge-guard.py")], input=json.dumps(ev),
                           capture_output=True, text=True)
        self.assertNotIn("deny", r.stdout)
        ev["tool_input"] = {"command": "forge new x"}
        r = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "forge-guard.py")], input=json.dumps(ev),
                           capture_output=True, text=True)
        self.assertIn("deny", r.stdout)


if __name__ == "__main__":
    unittest.main()
