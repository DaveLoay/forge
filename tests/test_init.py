"""Tests for bin/forge-init. Run: python3 -m unittest discover -s tests"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
INIT = PLUGIN / "bin" / "forge-init"


def run_init(root: Path) -> str:
    r = subprocess.run([sys.executable, str(INIT), str(root)], capture_output=True, text=True, check=True)
    return r.stdout


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if ".git" not in p.relative_to(root).parts)


class TestInit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "my-project"

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_folder_becomes_layout(self):
        self.root.mkdir()
        out = run_init(self.root)
        self.assertIn("forge project initialised", out)
        for rel in ("references/inbox", "pipeline", "tests", "src"):
            self.assertTrue((self.root / rel).is_dir(), rel)
        for rel in ("references/catalog.md", "references/references.bib", "references/MISSING.md", ".gitignore"):
            self.assertTrue((self.root / rel).is_file(), rel)
        self.assertIn("| key | year | title |", (self.root / "references/catalog.md").read_text())
        self.assertIn("| id | title | reason |", (self.root / "references/MISSING.md").read_text())
        # refs recognises the result as a project
        st = subprocess.run([sys.executable, str(PLUGIN / "bin" / "refs"), "--root", str(self.root), "status"],
                            capture_output=True, text=True, env={"FORGE_MARKER_URL": "http://127.0.0.1:9", "PATH": "/usr/bin:/bin"})
        self.assertIn("converted:  0", st.stdout)

    def test_rerun_changes_nothing(self):
        run_init(self.root)
        (self.root / "pipeline" / "brief.md").write_text("mine")
        before = {p: (self.root / p).read_bytes() for p in tree(self.root) if (self.root / p).is_file()}
        out = run_init(self.root)
        self.assertIn("already a forge project", out)
        after = {p: (self.root / p).read_bytes() for p in tree(self.root) if (self.root / p).is_file()}
        self.assertEqual(before, after)

    def test_existing_gitignore_appended_once(self):
        self.root.mkdir()
        (self.root / ".gitignore").write_text("node_modules/\n")
        run_init(self.root)
        run_init(self.root)
        text = (self.root / ".gitignore").read_text()
        self.assertTrue(text.startswith("node_modules/\n"))
        self.assertEqual(text.count("# >>> forge >>>"), 1)

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_gitignore_keeps_papers_out_and_catalog_in(self):
        run_init(self.root)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        paper = self.root / "references" / "smith2024transfers"
        paper.mkdir()
        (paper / "smith2024transfers.md").write_text("x")
        (paper / "smith2024transfers.pdf").write_bytes(b"%PDF")
        (self.root / "references" / "inbox" / "new.pdf").write_bytes(b"%PDF")
        (self.root / "src" / "main.py").write_text("")

        def ignored(rel: str) -> bool:
            return subprocess.run(["git", "-C", str(self.root), "check-ignore", "-q", rel]).returncode == 0

        for rel in ("references/smith2024transfers/smith2024transfers.pdf",
                    "references/smith2024transfers/smith2024transfers.md",
                    "references/inbox/new.pdf", "references/fetch.log"):
            self.assertTrue(ignored(rel), rel)
        for rel in ("references/catalog.md", "references/references.bib", "references/MISSING.md",
                    "pipeline/.gitkeep", "tests/.gitkeep", "src/main.py", ".gitignore"):
            self.assertFalse(ignored(rel), rel)


if __name__ == "__main__":
    unittest.main()
