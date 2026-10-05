"""Tests for lib/forge_approvals.py, bin/forge-approve, bin/forge-gate and the guard's gates."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "lib"))
import forge_approvals as fa  # noqa: E402

BRIEF = "---\nstatus: draft            # comment\napproved: null           # comment\n---\n\n# Brief\n\n| SQ-1 | q |\n"


def run(cmd, cwd):
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / cmd[0]), *cmd[1:]], cwd=cwd, capture_output=True, text=True)


def guard(root, agent, tool, ti):
    ev = {"hook_event_name": "PreToolUse", "cwd": str(root), "agent_type": agent, "tool_name": tool, "tool_input": ti}
    r = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "forge-guard.py")], input=json.dumps(ev), capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    hs = out.get("hookSpecificOutput") or {}
    return hs.get("permissionDecision", "pass"), hs.get("permissionDecisionReason", "")


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "p"
        subprocess.run([sys.executable, str(PLUGIN / "bin" / "forge-init"), str(self.root)], check=True, capture_output=True)
        (self.root / "pipeline" / "brief.md").write_text(BRIEF)

    def tearDown(self):
        self.tmp.cleanup()

    def test_approve_and_invalidate(self):
        self.assertFalse(fa.check(self.root, "brief")[0])
        r = run(["forge-approve", "brief"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout)
        text = (self.root / "pipeline" / "brief.md").read_text()
        self.assertRegex(text, r"(?m)^status: approved")
        self.assertRegex(text, r"(?m)^approved: \d{4}-\d\d-\d\d")
        self.assertEqual(run(["forge-gate", "brief"], self.root).returncode, 0)
        (self.root / "pipeline" / "brief.md").write_text(text + "edit\n")
        g = run(["forge-gate", "brief"], self.root)
        self.assertEqual(g.returncode, 1)
        self.assertIn("changed after it was approved", g.stdout)

    def test_gates_chain(self):
        (self.root / "pipeline" / "candidates.md").write_text("x")
        r = run(["forge-approve", "candidates"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("brief.md has not been approved", r.stdout)
        run(["forge-approve", "brief"], self.root)
        self.assertEqual(run(["forge-approve", "candidates"], self.root).returncode, 0)
        self.assertTrue(fa.check(self.root, "candidates")[0])
        (self.root / "pipeline" / "brief.md").write_text("changed")
        self.assertFalse(fa.check(self.root, "candidates")[0])  # an earlier gate going stale blocks later ones

    def test_guard_gates_investigate_agents(self):
        d, why = guard(self.root, "forge:mr-curiosity", "WebSearch", {"query": "x"})
        self.assertEqual(d, "deny")
        self.assertIn("has not been approved", why)
        run(["forge-approve", "brief"], self.root)
        self.assertEqual(guard(self.root, "forge:mr-curiosity", "WebSearch", {"query": "x"})[0], "pass")
        self.assertEqual(guard(self.root, "forge:mr-curiosity", "Bash", {"command": "refs fetch 1"})[0], "deny")
        self.assertEqual(guard(self.root, "forge:mr-curiosity", "Bash", {"command": "refs resolve 2506.19108"})[0], "pass")
        self.assertEqual(guard(self.root, "forge:mr-curiosity", "Write", {"file_path": "pipeline/candidates.md"})[0], "deny")
        hippo = "forge:hungry-hippo"
        self.assertEqual(guard(self.root, hippo, "Bash", {"command": "refs fetch --source brief 2506.19108"})[0], "pass")
        self.assertEqual(guard(self.root, hippo, "Bash", {"command": "refs fetch --source curiosity 2506.19108"})[0], "deny")
        self.assertEqual(guard(self.root, hippo, "Bash", {"command": "forge-approve candidates"})[0], "deny")
        self.assertEqual(guard(self.root, hippo, "Write", {"file_path": "pipeline/candidates.md"})[0], "pass")
        self.assertEqual(guard(self.root, hippo, "Write", {"file_path": "pipeline/approvals/candidates.json"})[0], "deny")
        self.assertEqual(guard(self.root, "forge:pointer", "Read", {"file_path": "references/catalog.md"})[0], "deny")
        (self.root / "pipeline" / "candidates.md").write_text("x")
        run(["forge-approve", "candidates"], self.root)
        self.assertEqual(guard(self.root, hippo, "Bash", {"command": "refs fetch --source curiosity 2506.19108"})[0], "pass")
        self.assertEqual(guard(self.root, "forge:pointer", "Write", {"file_path": "pipeline/index.md"})[0], "pass")

    def test_interrogator_cannot_self_approve(self):
        A = "forge:interrogator"
        self.assertEqual(guard(self.root, A, "Edit", {"file_path": "pipeline/brief.md", "old_string": "status: draft", "new_string": "status: approved"})[0], "deny")
        self.assertEqual(guard(self.root, A, "Write", {"file_path": "pipeline/brief.md", "content": "---\nstatus: approved\n---"})[0], "deny")
        self.assertEqual(guard(self.root, A, "Write", {"file_path": "pipeline/brief.md", "content": "---\nstatus: draft\n---"})[0], "pass")

    def test_plain_session_may_check_gates(self):
        self.assertEqual(guard(self.root, None, "Bash", {"command": "forge-gate brief"})[0], "pass")
        self.assertEqual(guard(self.root, None, "Bash", {"command": "forge-approve brief"})[0], "deny")


if __name__ == "__main__":
    unittest.main()


class PlanStageTests(ApprovalTests):
    def approve_through_index(self):
        run(["forge-approve", "brief"], self.root)
        for name in ("candidates", "index"):
            (self.root / "pipeline" / f"{name}.md").write_text(name)
            self.assertEqual(run(["forge-approve", name], self.root).returncode, 0)

    def test_plan_agents_need_index_and_stay_in_lane(self):
        OZ, JJJ, SM = "forge:ozymandias", "forge:j-jonah-jameson", "forge:smithers"
        self.assertEqual(guard(self.root, OZ, "Read", {"file_path": "pipeline/brief.md"})[0], "deny")
        self.approve_through_index()
        for p in ("pipeline/design.md", "pipeline/plan.md", "pipeline/ledger.md", "tests/test_x.py"):
            self.assertEqual(guard(self.root, OZ, "Write", {"file_path": p})[0], "pass", p)
        for p in ("src/a.py", "pipeline/brief.md", "pipeline/index.md", "pipeline/.tests-locked"):
            self.assertEqual(guard(self.root, OZ, "Write", {"file_path": p})[0], "deny", p)
        self.assertEqual(guard(self.root, OZ, "Bash", {"command": "pytest"})[0], "deny")
        for a in (JJJ, SM):
            self.assertEqual(guard(self.root, a, "Read", {"file_path": "pipeline/plan.md"})[0], "pass")
            self.assertEqual(guard(self.root, a, "Write", {"file_path": "pipeline/ledger.md"})[0], "deny")
            self.assertEqual(guard(self.root, a, "Read", {"file_path": "references/k/k.pdf"})[0], "deny")

    def test_design_approval_locks_tests(self):
        self.approve_through_index()
        (self.root / "pipeline" / "design.md").write_text("design")
        (self.root / "pipeline" / "plan.md").write_text("plan")
        self.assertEqual(guard(self.root, "forge:ozymandias", "Write", {"file_path": "tests/test_x.py"})[0], "pass")
        self.assertEqual(run(["forge-approve", "design"], self.root).returncode, 0)
        self.assertTrue((self.root / "pipeline" / ".tests-locked").exists())
        d, why = guard(self.root, "forge:ozymandias", "Edit", {"file_path": "tests/test_x.py"})
        self.assertEqual(d, "deny")
        self.assertIn("locked", why)
        self.assertEqual(guard(self.root, "forge:ozymandias", "Write", {"file_path": "pipeline/plan.md"})[0], "pass")
