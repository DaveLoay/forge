"""Tests for hooks/forge-guard.py. Run: python3 -m unittest discover -s tests"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
GUARD = PLUGIN / "hooks" / "forge-guard.py"
INIT = PLUGIN / "bin" / "forge-init"


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        subprocess.run([sys.executable, str(INIT), str(self.root)], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, name, agent=None, tool=None, tool_input=None, cwd=None, env=None):
        ev = {"hook_event_name": name, "session_id": "s1", "cwd": str(cwd or self.root)}
        if agent:
            ev["agent_type"] = agent
        if tool:
            ev["tool_name"] = tool
            ev["tool_input"] = tool_input or {}
        r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(ev), capture_output=True, text=True,
                           env={**os.environ, **(env or {})})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    def decision(self, **kw):
        out = self.event("PreToolUse", **kw)
        return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "pass")

    def log(self):
        return (self.root / "pipeline" / "run-log.md").read_text()


class TestInterrogator(GuardCase):
    A = "forge:interrogator"

    def test_banner_and_stage_file(self):
        out = self.event("SessionStart", agent=self.A)
        self.assertIn("forge · stage 1/5 · Interrogator", out["systemMessage"])
        stage = json.loads((self.root / "pipeline" / ".stage").read_text())
        self.assertEqual(stage["agent"], self.A)
        self.assertIn("SessionStart", self.log())

    def test_may_write_brief_only(self):
        self.assertEqual(self.decision(agent=self.A, tool="Write", tool_input={"file_path": str(self.root / "pipeline/brief.md")}), "pass")
        self.assertEqual(self.decision(agent=self.A, tool="Edit", tool_input={"file_path": "pipeline/brief.md"}), "pass")
        for p in ("src/main.py", "tests/test_x.py", "pipeline/plan.md", "references/catalog.md", "/tmp/elsewhere.txt"):
            self.assertEqual(self.decision(agent=self.A, tool="Write", tool_input={"file_path": p}), "deny", p)

    def test_refs_only_shell_and_no_pdf_reading(self):
        for cmd in ("refs fetch --source brief 2506.19108", "refs convert", "refs status"):
            self.assertEqual(self.decision(agent=self.A, tool="Bash", tool_input={"command": cmd}), "pass", cmd)
        for cmd in ("ls", "refs fetch 1 && rm -rf src", "refs convert; python3 x.py", "refs fetch $(cat ids)",
                    "refs catalog", "refs marker start", "refsfetch x", "python3 refs fetch x", "refs status > pipeline/x"):
            self.assertEqual(self.decision(agent=self.A, tool="Bash", tool_input={"command": cmd}), "deny", cmd)
        self.assertEqual(self.decision(agent=self.A, tool="Read", tool_input={"file_path": "references/k/k.pdf"}), "deny")
        self.assertEqual(self.decision(agent=self.A, tool="Read", tool_input={"file_path": "references/k/k.md"}), "pass")

    def test_no_pdf_downloads(self):
        self.assertEqual(self.decision(agent=self.A, tool="WebFetch", tool_input={"url": "https://arxiv.org/pdf/2506.19108"}), "deny")
        self.assertEqual(self.decision(agent=self.A, tool="WebFetch", tool_input={"url": "https://arxiv.org/abs/2506.19108"}), "pass")
        self.assertIn("BLOCKED", self.log())

    def test_harness_tools_always_allowed(self):
        for agent in (self.A, "forge:hungry-hippo", None):
            self.assertEqual(self.decision(agent=agent, tool="StructuredOutput", tool_input={"ok": True}), "pass")

    def test_reads_plugin_templates(self):
        self.assertEqual(self.decision(agent=self.A, tool="Read", tool_input={"file_path": str(PLUGIN / "templates/brief.md")}), "allow")


class TestNoStage(GuardCase):
    def test_banner_warns(self):
        out = self.event("SessionStart")
        self.assertIn("no forge stage active", out["systemMessage"])
        self.assertIn("plain Claude session", out["systemMessage"])

    def test_blocks_project_writes(self):
        for p in ("src/fakeprint.py", "pipeline/fig5.png", "references/x/x.md", "tests/t.py"):
            self.assertEqual(self.decision(tool="Write", tool_input={"file_path": p}), "deny", p)
        self.assertEqual(self.decision(tool="Write", tool_input={"file_path": "notes.md"}), "pass")

    def test_shell_is_read_only(self):
        for cmd in ("ls -la", "cat references/catalog.md | head", "git status && git log -3", "refs status",
                    "find . -name '*.md'", "grep -r foo src"):
            self.assertEqual(self.decision(tool="Bash", tool_input={"command": cmd}), "pass", cmd)
        for cmd in ("python3 -m venv .venv", "./.venv/bin/python src/plot.py", "pip install numpy",
                    "echo x > src/a.py", "cat a | tee pipeline/b", "refs fetch 2506.19108", "curl -sL https://x/y.pdf -o p.pdf",
                    "find . -delete", "rm -rf src", "mkdir src/x", "echo $(rm -rf src)"):
            self.assertEqual(self.decision(tool="Bash", tool_input={"command": cmd}), "deny", cmd)

    def test_blocks_pdf_fetch(self):
        self.assertEqual(self.decision(tool="WebFetch", tool_input={"url": "https://arxiv.org/pdf/2506.19108"}), "deny")

    def test_unknown_agent_treated_as_no_stage(self):
        self.assertEqual(self.decision(agent="general-purpose", tool="Write", tool_input={"file_path": "src/a.py"}), "deny")

    def test_guard_off_logs_but_allows(self):
        self.assertEqual(self.decision(tool="Bash", tool_input={"command": "pip install x"}, env={"FORGE_GUARD": "off"}), "pass")
        self.assertIn("BLOCKED", self.log())


class TestOutsideForge(unittest.TestCase):
    def test_silent_outside_projects(self):
        with tempfile.TemporaryDirectory() as d:
            ev = {"hook_event_name": "PreToolUse", "cwd": d, "tool_name": "Bash", "tool_input": {"command": "pip install x"}}
            r = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(ev), capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
