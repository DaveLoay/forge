"""Tests for lib/forge_env.py, bin/forge-env, bin/forge-probe, the design gate over pipeline/env/,
and the guard rules for environments and probes. Run: python3 -m unittest discover -s tests"""

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
import forge_env as fe  # noqa: E402

HEAD = "# claim: two plus two is four\n# settles: D-1\n# pass if: the sum printed is 4\n"


def run(cmd, cwd):
    return subprocess.run([sys.executable, str(PLUGIN / "bin" / cmd[0]), *cmd[1:]], cwd=cwd, capture_output=True, text=True)


def guard(root, agent, tool, ti):
    ev = {"hook_event_name": "PreToolUse", "cwd": str(root), "agent_type": agent, "tool_name": tool, "tool_input": ti}
    r = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "forge-guard.py")], input=json.dumps(ev), capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "pass")


class EnvCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "My Project"
        subprocess.run([sys.executable, str(PLUGIN / "bin" / "forge-init"), str(self.root)], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def spec(self, name, text=""):
        d = self.root / "pipeline" / "env"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)

    def legacy_venv(self):
        (self.root / ".venv" / "bin").mkdir(parents=True)
        os.symlink(sys.executable, self.root / ".venv" / "bin" / "python")


class TestDetectAndWrap(EnvCase):
    def test_detect_order_and_legacy(self):
        self.assertEqual(fe.detect(self.root), {"kind": "venv", "spec": None})
        self.spec("requirements.txt")
        self.assertEqual(fe.detect(self.root)["kind"], "venv")
        self.spec("Dockerfile", "FROM python:3.12\n")
        self.assertEqual(fe.detect(self.root), {"kind": "docker", "spec": "pipeline/env/Dockerfile"})
        self.spec("environment.yml", "name: x\n")
        self.assertEqual(fe.detect(self.root)["kind"], "conda")
        self.spec("pixi.toml", "[project]\n")
        self.assertEqual(fe.detect(self.root), {"kind": "pixi", "spec": "pipeline/env/pixi.toml"})

    def test_wrap_commands(self):
        self.spec("pixi.toml", "[project]\n")
        cmd, _ = fe.wrap(self.root, ["python", "p.py"])
        self.assertEqual(cmd, ["pixi", "run", "--manifest-path", "pipeline/env/pixi.toml", "python", "p.py"])
        (self.root / "pipeline/env/pixi.toml").unlink()
        self.spec("Dockerfile", 'FROM python:3.12\nLABEL forge.gpus="all"\n')
        cmd, _ = fe.wrap(self.root, ["python", "p.py"], {"FORGE_PROBE_OUT": "o"}, name="n1")
        self.assertEqual(cmd[:4], ["docker", "run", "--rm", "--name"])
        self.assertIn(f"{self.root}:/work", cmd)
        self.assertIn("FORGE_PROBE_OUT=o", cmd)
        self.assertEqual(cmd[cmd.index("--gpus") + 1], "all")
        self.assertTrue(cmd[-3].startswith("forge-my-project:"), cmd[-3])
        self.assertEqual(cmd[-2:], ["python", "p.py"])

    def test_pixi_installs_frozen_only_after_design_approval(self):
        self.spec("pixi.toml", "[project]\n")
        self.spec("pixi.lock", "lock\n")
        self.assertNotIn("--frozen", fe.create_commands(self.root, fe.detect(self.root))[0])

    def test_venv_create_status_and_run(self):
        self.spec("requirements.txt", "# nothing\n")
        ready, msg, _ = fe.status(self.root)
        self.assertFalse(ready)
        self.assertIn("not built", msg)
        r = run(["forge-env", "create"], self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(run(["forge-env", "status"], self.root).returncode, 0)
        r = run(["forge-env", "run", "python", "-c", "import sys; print(sys.prefix)"], self.root)
        self.assertIn(".venv", r.stdout)
        self.spec("requirements.txt", "# changed\n")
        r = run(["forge-env", "status"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed since", r.stdout)
        self.assertEqual(run(["forge-env", "run", "python", "-c", "1"], self.root).returncode, 1)

    def test_design_gate_covers_env_spec(self):
        (self.root / "pipeline/brief.md").write_text("---\nstatus: draft\napproved: null\n---\n")
        for g in ("brief", "candidates", "index"):
            if g != "brief":
                (self.root / f"pipeline/{g}.md").write_text(g)
            self.assertEqual(run(["forge-approve", g], self.root).returncode, 0, g)
        (self.root / "pipeline/design.md").write_text("d")
        (self.root / "pipeline/plan.md").write_text("p")
        self.spec("pixi.toml", "[project]\n")
        self.spec("pixi.lock", "lock\n")  # forge-env create writes it during Plan, before approval
        self.assertEqual(run(["forge-approve", "design"], self.root).returncode, 0)
        self.assertTrue(fa.check(self.root, "design")[0])
        (self.root / "pipeline/env/.pixi/envs").mkdir(parents=True)
        (self.root / "pipeline/env/.pixi/envs/f").write_text("built env, not spec")
        self.assertTrue(fa.check(self.root, "design")[0])
        self.assertIn("--frozen", fe.create_commands(self.root, fe.detect(self.root))[0])
        self.spec("pixi.toml", "[project]\nnew = 1\n")
        ok, why = fa.check(self.root, "design")
        self.assertFalse(ok)
        self.assertIn("pipeline/env", why)


class TestProbe(EnvCase):
    def setUp(self):
        super().setUp()
        self.legacy_venv()
        (self.root / "pipeline/probes").mkdir()

    def probe(self, name, body):
        (self.root / "pipeline/probes" / name).write_text(body)
        return run(["forge-probe", f"pipeline/probes/{name}"], self.root)

    def record(self, n):
        return json.loads((self.root / f"pipeline/probes/P-{n}.json").read_text())

    def test_pass_writes_record_index_and_outputs(self):
        r = self.probe("P-1_sum.py", HEAD + "import os, pathlib\n"
                       "pathlib.Path(os.environ['FORGE_PROBE_OUT'], 'table.csv').write_text('a,b')\n"
                       "print('RESULT: PASS sum is', 2 + 2)\n")
        self.assertEqual(r.returncode, 0, r.stdout)
        rec = self.record(1)
        self.assertEqual(rec["verdict"], "PASS")
        self.assertEqual(rec["settles"], "D-1")
        self.assertEqual(rec["outputs"], ["pipeline/probes/out/P-1/table.csv"])
        md = (self.root / "pipeline/probes/probes.md").read_text()
        self.assertIn("| P-1 | PASS | two plus two is four | D-1 |", md)

    def test_fail_error_and_no_result(self):
        self.assertEqual(self.probe("P-2_f.py", HEAD + "print('RESULT: FAIL got 5')\n").returncode, 1)
        self.assertEqual(self.record(2)["verdict"], "FAIL")
        self.probe("P-3_e.py", HEAD + "raise SystemExit(3)\n")
        self.assertEqual(self.record(3)["verdict"], "ERROR")
        self.probe("P-4_n.sh", HEAD + "echo hello\n")
        self.assertEqual(self.record(4)["verdict"], "NO RESULT")
        md = (self.root / "pipeline/probes/probes.md").read_text()
        self.assertLess(md.index("| P-2 |"), md.index("| P-4 |"))

    def test_changing_project_files_is_invalid(self):
        self.probe("P-5_bad.py", HEAD + "open('src/x.py', 'w').write('x')\nprint('RESULT: PASS')\n")
        rec = self.record(5)
        self.assertEqual(rec["verdict"], "INVALID")
        self.assertEqual(rec["changed_files"], ["src/x.py"])

    def test_timeout(self):
        (self.root / "pipeline/probes/P-6_slow.py").write_text(HEAD + "import time\ntime.sleep(30)\n")
        r = run(["forge-probe", "pipeline/probes/P-6_slow.py", "--timeout", "1"], self.root)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.record(6)["verdict"], "TIMEOUT")
        self.assertEqual(run(["forge-probe", "pipeline/probes/P-6_slow.py", "--timeout", "601"], self.root).returncode, 2)

    def test_refuses_without_header_or_outside_probes(self):
        r = self.probe("P-7_x.py", "# claim: something\nprint('RESULT: PASS')\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("# settles:", r.stdout)
        self.assertFalse((self.root / "pipeline/probes/P-7.json").exists())
        (self.root / "src/P-8_x.py").write_text(HEAD)
        self.assertEqual(run(["forge-probe", "src/P-8_x.py"], self.root).returncode, 2)
        self.assertEqual(self.probe("probe.py", HEAD).returncode, 2)

    def test_needs_a_ready_environment(self):
        os.unlink(self.root / ".venv/bin/python")
        r = self.probe("P-9_x.py", HEAD + "print('RESULT: PASS')\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("environment is not ready", r.stdout)


class TestGuard(EnvCase):
    def setUp(self):
        super().setUp()
        (self.root / "pipeline/brief.md").write_text("---\nstatus: draft\napproved: null\n---\n")
        run(["forge-approve", "brief"], self.root)
        for g in ("candidates", "index"):
            (self.root / f"pipeline/{g}.md").write_text(g)
            run(["forge-approve", g], self.root)

    def test_ozymandias_env_and_probes(self):
        OZ = "forge:ozymandias"
        for p in ("pipeline/env/pixi.toml", "pipeline/env/Dockerfile", "pipeline/probes/P-1_rate.py", "pipeline/probes/P-12_x.sh"):
            self.assertEqual(guard(self.root, OZ, "Write", {"file_path": p}), "pass", p)
        for p in ("pipeline/probes/P-1.json", "pipeline/probes/probes.md", "pipeline/probes/out/P-1/a.png", "src/a.py", "data/x.wav"):
            self.assertEqual(guard(self.root, OZ, "Write", {"file_path": p}), "deny", p)
        for c in ("forge-env create", "forge-env status", "forge-probe pipeline/probes/P-1_rate.py", "forge-probe pipeline/probes/P-1_rate.py --timeout 60"):
            self.assertEqual(guard(self.root, OZ, "Bash", {"command": c}), "pass", c)
        for c in ("python pipeline/probes/P-1_rate.py", "ffprobe data/a.wav", "forge-env run python x.py", "pytest",
                  "forge-probe pipeline/probes/P-1_rate.py > pipeline/probes/P-1.json"):
            self.assertEqual(guard(self.root, OZ, "Bash", {"command": c}), "deny", c)

    def test_mf_code_uses_the_env(self):
        (self.root / "pipeline/design.md").write_text("d")
        (self.root / "pipeline/plan.md").write_text("p")
        run(["forge-approve", "design"], self.root)
        MF = "forge:mf-code"
        for c in ("forge-env run python -m pytest tests -q", "forge-env status", "forge-env create", "forge-test 1"):
            self.assertEqual(guard(self.root, MF, "Bash", {"command": c}), "pass", c)
        for c in ("python3 -m venv .venv", ".venv/bin/pip install numpy", "pip install numpy", "pixi add numpy", "forge-probe x"):
            self.assertEqual(guard(self.root, MF, "Bash", {"command": c}), "deny", c)
        for p in ("pipeline/env/pixi.toml", "pipeline/probes/P-1_x.py"):
            self.assertEqual(guard(self.root, MF, "Write", {"file_path": p}), "deny", p)

    def test_plain_session_may_check_env_status_only(self):
        self.assertEqual(guard(self.root, None, "Bash", {"command": "forge-env status"}), "pass")
        for c in ("forge-env create", "forge-env run python x.py", "forge-probe pipeline/probes/P-1_x.py"):
            self.assertEqual(guard(self.root, None, "Bash", {"command": c}), "deny", c)


if __name__ == "__main__":
    unittest.main()
