"""Offline tests for bin/refs. Run: python3 -m unittest discover -s tests

The OCR step is exercised by pre-seeding the cache with Mistral-shaped responses,
so no API key or network access is needed.
"""

import base64
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

REFS = Path(__file__).resolve().parents[1] / "bin" / "refs"
_loader = importlib.machinery.SourceFileLoader("refs", str(REFS))
_spec = importlib.util.spec_from_loader("refs", _loader)
refs = importlib.util.module_from_spec(_spec)
_loader.exec_module(refs)

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def fake_pdf(tag: str) -> bytes:
    return b"%PDF-1.4\n% " + tag.encode() + b"\n%%EOF\n"


def ocr_response(first_page_md: str, with_assets: bool = True) -> dict:
    page0 = {"index": 0, "markdown": first_page_md, "images": [], "tables": [],
             "header": None, "footer": None}
    page1 = {
        "index": 1,
        "markdown": "## 2 Method\n\nWe minimise $\\mathcal{L}(\\theta)=\\sum_i \\ell_i$.\n\n"
                    "$$\n\\hat{m}_t = \\frac{m_t}{1-\\beta_1^t}\n$$\n\n"
                    "![img-0.jpeg](img-0.jpeg)\n\n[tbl-0.md](tbl-0.md)\n",
        "images": [{"id": "img-0.jpeg", "image_base64": f"data:image/png;base64,{PNG}"}] if with_assets else [],
        "tables": [{"id": "tbl-0.md", "content": "| a | b |\n|---|---|\n| 1 | 2 |", "format": "markdown"}]
        if with_assets else [],
    }
    page2 = {"index": 2, "markdown": "![img-0.jpeg](img-0.jpeg)",
             "images": [{"id": "img-0.jpeg", "image_base64": PNG}] if with_assets else []}
    return {"pages": [page0, page1, page2], "model": "mistral-ocr-test", "usage_info": {"pages_processed": 3}}


class RefsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.cache = Path(self.tmp.name) / "cache"
        (self.root / "references" / "inbox").mkdir(parents=True)
        self._env = {k: os.environ.get(k) for k in
                     ("FORGE_CACHE_DIR", "MISTRAL_API_KEY", "FORGE_OCR_BACKEND", "FORGE_MARKER_URL")}
        os.environ["FORGE_CACHE_DIR"] = str(self.cache)
        os.environ.pop("MISTRAL_API_KEY", None)
        os.environ.pop("FORGE_OCR_BACKEND", None)
        os.environ["FORGE_MARKER_URL"] = "http://127.0.0.1:9"  # never reach a real server
        # no network in tests
        self._orig = {n: getattr(refs, n) for n in ("crossref_meta", "arxiv_meta", "crossref_search_title",
                                                     "MARKER_BIN", "MARKER_PID", "MARKER_LOG")}
        refs.MARKER_BIN = Path(self.tmp.name) / "no-marker-install"  # never start a real server
        refs.MARKER_PID = Path(self.tmp.name) / "marker.pid"
        refs.MARKER_LOG = Path(self.tmp.name) / "marker.log"
        refs.crossref_meta = lambda doi: None
        refs.arxiv_meta = lambda aid: None
        refs.crossref_search_title = lambda title: None

    def tearDown(self):
        for n, f in self._orig.items():
            setattr(refs, n, f)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    @property
    def inbox(self) -> Path:
        return self.root / "references" / "inbox"

    def drop(self, name: str, tag: str, ocr: dict | None, sidecar: dict | None = None) -> Path:
        pdf = self.inbox / name
        pdf.write_bytes(fake_pdf(tag))
        if ocr is not None:
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / f"{refs.sha256_file(pdf)}.json").write_text(json.dumps(ocr))
        if sidecar is not None:
            pdf.with_name(pdf.stem + ".meta.json").write_text(json.dumps(sidecar))
        return pdf

    def run_refs(self, *argv) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = refs.main(["--root", str(self.root), *argv])
        return code, out.getvalue()


ADAM = {"title": "Adam: A Method for Stochastic Optimization", "authors": ["Diederik P. Kingma", "Jimmy Ba"],
        "family": ["Kingma", "Ba"], "year": 2014, "doi": None, "arxiv": "1412.6980",
        "url": "https://arxiv.org/abs/1412.6980", "source": "brief", "verified": True}


class TestIdentifiers(unittest.TestCase):
    def test_classify(self):
        cases = {
            "1412.6980": ("arxiv", "1412.6980"),
            "arXiv:2509.23055v2": ("arxiv", "2509.23055"),
            "https://arxiv.org/abs/2510.20270": ("arxiv", "2510.20270"),
            "https://arxiv.org/pdf/2510.20270v1.pdf": ("arxiv", "2510.20270"),
            "hep-th/9901001": ("arxiv", "hep-th/9901001"),
            "10.48550/arXiv.1706.03762": ("arxiv", "1706.03762"),
            "https://doi.org/10.1038/S41586-021-03819-2": ("doi", "10.1038/s41586-021-03819-2"),
            "doi:10.1126/science.aaa8415.": ("doi", "10.1126/science.aaa8415"),
            "https://example.org/paper.pdf": ("url", "https://example.org/paper.pdf"),
            "not an id": ("unknown", "not an id"),
        }
        for raw, want in cases.items():
            self.assertEqual(refs.classify(raw), want, raw)

    def test_key(self):
        self.assertEqual(refs.make_key_base(ADAM, "x"), "kingma2014adam")
        m = {"title": "On the Ünïcode of Things", "family": ["Müller-Šimek"], "year": 2020}
        self.assertEqual(refs.make_key_base(m, "x"), "mullersimek2020unicode")
        self.assertEqual(refs.make_key_base({"title": "", "family": []}, "My Paper (v2).pdf"), "mypaperv2pdf")

    def test_frontmatter_roundtrip(self):
        meta = {k: None for k in refs.FRONTMATTER_FIELDS}
        meta.update(key="k", title='Colon: "quotes" | pipes', authors=["A B", "C D"], year=2020, verified=True)
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(refs.dump_frontmatter(meta) + "\nbody\n")
        try:
            self.assertEqual(refs.read_frontmatter(Path(f.name)), meta)
        finally:
            os.unlink(f.name)


class TestConvertBudget(RefsTestCase):
    def test_budget_defers_uncached_and_reports(self):
        self.drop("a.pdf", "cached", ocr_response("# A"), ADAM)
        self.drop("b.pdf", "uncached", None)
        code, out = self.run_refs("convert", "--budget", "-1")  # budget already spent
        self.assertEqual(code, 3, out)                          # 3 = PDFs still waiting
        self.assertIn("1 PDF(s) not started", out)
        self.assertIn("inbox: 1 PDF(s) still waiting", out)
        self.assertTrue((self.root / "references" / "kingma2014adam").is_dir())  # cached ones still done
        code, out = self.run_refs("status", "--json")
        st = json.loads(out)
        self.assertEqual((st["converted"], st["inbox_waiting"], st["inbox_files"]), (1, 1, ["b.pdf"]))


class TestPool(RefsTestCase):
    def setUp(self):
        super().setUp()
        self.pool = Path(self.tmp.name) / "vault"
        paper = self.pool / "refs-md" / "Kingma and Ba - 2014 - Adam A Method for Stochastic Optimization"
        (paper / "assets").mkdir(parents=True)
        (paper / "assets" / "Kingma fig 1.png").write_bytes(b"png")
        (paper / "Kingma and Ba.md").write_text(
            "arXiv:1412.6980v9 [cs.LG]\n\n# ADAM\n\n![fig](assets/Kingma%20fig%201.png)\n\n$$m_t$$\n")
        (self.pool / "Loose note.md").write_text("not a paper")
        os.environ["FORGE_POOL"] = str(self.pool)
        self._orig_cache = refs.cache_dir
        refs.arxiv_meta = lambda aid: dict(ADAM, family=["Kingma", "Ba"]) if aid == "1412.6980" else None

    def tearDown(self):
        os.environ.pop("FORGE_POOL", None)
        super().tearDown()

    def test_fetch_copies_from_pool(self):
        code, out = self.run_refs("fetch", "--source", "brief", "1412.6980")
        self.assertEqual(code, 0, out)
        self.assertIn("1 from pool", out)
        d = self.root / "references" / "kingma2014adam"
        md = (d / "kingma2014adam.md").read_text()
        fm = refs.read_frontmatter(d / "kingma2014adam.md")
        self.assertEqual((fm["source"], fm["arxiv"]), ("brief", "1412.6980"))
        self.assertTrue(fm["origin"].startswith("pool: "))
        self.assertIn("![[images/Kingma fig 1.png]]", md)
        self.assertIn("$$m_t$$", md)
        self.assertTrue((d / "images" / "Kingma fig 1.png").is_file())
        self.assertEqual(list((self.root / "references" / "inbox").glob("*.pdf")), [])
        self.assertIn("kingma2014adam", (self.root / "references" / "catalog.md").read_text())
        code, out = self.run_refs("fetch", "1412.6980")
        self.assertIn("1 known", out)  # second fetch: already in the project

    def test_title_match_without_ids(self):
        e = refs._pool_entry(self.pool / "refs-md" / "Kingma and Ba - 2014 - Adam A Method for Stochastic Optimization")
        self.assertEqual((e["arxiv"], e["year"]), ("1412.6980", 2014))
        hit = refs.pool_match({"title": "Adam: A Method for Stochastic Optimization", "year": 2015}, [dict(e, arxiv=None)])
        self.assertIsNotNone(hit)
        self.assertIsNone(refs.pool_match({"title": "Adam: A Method for Stochastic Optimization", "year": 2019}, [dict(e, arxiv=None)]))
        self.assertIsNone(refs.pool_match({"title": "Attention is all you need", "year": 2017}, [dict(e, arxiv=None)]))


class TestMarkerShape(unittest.TestCase):
    def test_marker_to_pages(self):
        sep = "-" * 48
        out = {
            "success": True,
            "output": f"\n\n{{0}}{sep}\n\n# Title\n\n$$x^2$$\n\n{{1}}{sep}\n\n"
                      "![](_page_1_Picture_0.jpeg)\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
            "images": {"_page_1_Picture_0.jpeg": PNG},
            "metadata": {"page_stats": []},
        }
        resp = refs.marker_to_pages(out)
        self.assertEqual([p["index"] for p in resp["pages"]], [0, 1])
        self.assertIn("$$x^2$$", resp["pages"][0]["markdown"])
        self.assertEqual(resp["pages"][0]["images"], [])
        self.assertEqual(resp["pages"][1]["images"][0]["id"], "_page_1_Picture_0.jpeg")
        with tempfile.TemporaryDirectory() as d:
            md = refs.render_markdown(resp, Path(d) / "images")
            self.assertIn("![[images/_page_1_Picture_0.jpeg]]", md)
            self.assertIn("<!-- page 2 -->", md)
            self.assertTrue((Path(d) / "images" / "_page_1_Picture_0.jpeg").is_file())


class TestConvert(RefsTestCase):
    def test_convert_with_sidecar(self):
        self.drop("kingma2014adam.pdf", "adam", ocr_response("# Adam: A Method for Stochastic Optimization\n\nAbstract."), ADAM)
        code, out = self.run_refs("convert")
        self.assertEqual(code, 0, out)
        self.assertIn("0 OCR call", out)
        d = self.root / "references" / "kingma2014adam"
        for f in ("kingma2014adam.md", "kingma2014adam.pdf", "ocr.json", "images/img-0.jpeg", "images/p3-img-0.jpeg"):
            self.assertTrue((d / f).exists(), f)
        self.assertEqual(list(self.inbox.iterdir()), [])
        md = (d / "kingma2014adam.md").read_text()
        fm = refs.read_frontmatter(d / "kingma2014adam.md")
        self.assertEqual(fm["key"], "kingma2014adam")
        self.assertEqual(fm["arxiv"], "1412.6980")
        self.assertEqual(fm["source"], "brief")
        self.assertTrue(fm["verified"])
        self.assertEqual(list(fm), refs.FRONTMATTER_FIELDS)
        # equations survive verbatim, images become Obsidian embeds, tables are inlined
        self.assertIn("$$\n\\hat{m}_t = \\frac{m_t}{1-\\beta_1^t}\n$$", md)
        self.assertIn("![[images/img-0.jpeg]]", md)
        self.assertIn("![[images/p3-img-0.jpeg]]", md)
        self.assertIn("| a | b |\n|---|---|\n| 1 | 2 |", md)
        self.assertNotIn("tbl-0.md", md)
        self.assertIn("<!-- page 2 -->", md)
        self.assertNotIn("image_base64", (d / "ocr.json").read_text())
        catalog = (self.root / "references" / "catalog.md").read_text()
        self.assertIn("kingma2014adam", catalog)
        bib = (self.root / "references" / "references.bib").read_text()
        self.assertIn("@misc{kingma2014adam,", bib)
        self.assertIn("eprint = {1412.6980}", bib)
        self.assertIn("author = {Diederik P. Kingma and Jimmy Ba}", bib)

    def test_rerun_is_free_and_idempotent(self):
        self.drop("a.pdf", "adam", ocr_response("# Adam"), ADAM)
        self.run_refs("convert")
        snapshot = sorted(p.relative_to(self.root) for p in self.root.rglob("*"))
        code, out = self.run_refs("convert")
        self.assertEqual(code, 0)
        self.assertIn("nothing to convert", out)
        self.assertEqual(sorted(p.relative_to(self.root) for p in self.root.rglob("*")), snapshot)
        # dropping the identical file again is recognised by hash, not converted twice
        self.drop("again.pdf", "adam", None)
        code, out = self.run_refs("convert")
        self.assertIn("identical to kingma2014adam/", out)
        self.assertFalse((self.root / "references" / "kingma2014adamb").exists())

    def test_uncached_without_backend_fails_cleanly(self):
        self.drop("x.pdf", "nocache", None)
        for backend in ("marker", "mistral"):  # no server / no key
            os.environ["FORGE_OCR_BACKEND"] = backend
            with self.assertRaises(SystemExit):
                self.run_refs("convert")
            self.assertTrue((self.inbox / "x.pdf").exists())

    def test_marker_cache_is_reused(self):
        pdf = self.drop("kingma2014adam.pdf", "adam", None, ADAM)
        self.cache.mkdir(parents=True, exist_ok=True)
        (self.cache / f"{refs.sha256_file(pdf)}.marker.json").write_text(json.dumps(ocr_response("# Adam")))
        os.environ["FORGE_OCR_BACKEND"] = "mistral"  # a cached result from either backend is used
        code, out = self.run_refs("convert")
        self.assertEqual(code, 0, out)
        self.assertIn("0 OCR call", out)
        self.assertTrue((self.root / "references" / "kingma2014adam" / "kingma2014adam.md").is_file())

    def test_key_collision(self):
        other = dict(ADAM, arxiv="9999.99999", title="Adam revisited")
        self.drop("1.pdf", "one", ocr_response("# One"), ADAM)
        self.drop("2.pdf", "two", ocr_response("# Two"), other)
        self.run_refs("convert")
        self.assertTrue((self.root / "references" / "kingma2014adam").is_dir())
        self.assertTrue((self.root / "references" / "kingma2014adamb" / "kingma2014adamb.md").is_file())

    def test_dropin_doi_lookup_and_missing_cleanup(self):
        seen = []

        def fake_crossref(doi):
            seen.append(doi)
            return {"title": "Highly accurate protein structure prediction with AlphaFold",
                    "authors": ["John Jumper"], "family": ["Jumper"], "year": 2021,
                    "doi": doi, "arxiv": None, "url": f"https://doi.org/{doi}"}

        refs.crossref_meta = fake_crossref
        refs.write_missing(refs.Project(self.root), [("10.1038/s41586-021-03819-2", "AlphaFold", "paywalled"),
                                                     ("10.1/other", "Other", "paywalled")])
        self.drop("downloaded from nature.pdf", "af2",
                  ocr_response("# Highly accurate protein structure prediction\n\ndoi: 10.1038/s41586-021-03819-2."))
        code, out = self.run_refs("convert")
        self.assertEqual(code, 0, out)
        self.assertEqual(seen, ["10.1038/s41586-021-03819-2"])
        fm = refs.read_frontmatter(self.root / "references" / "jumper2021highly" / "jumper2021highly.md")
        self.assertEqual(fm["source"], "user")
        self.assertTrue(fm["verified"])
        rows = refs.read_missing(refs.Project(self.root))
        self.assertEqual([r[0] for r in rows], ["10.1/other"])

    def test_dropin_unverified_uses_filename(self):
        self.drop("Some Notes 2023.pdf", "notes", ocr_response("plain text, no heading"))
        self.run_refs("convert")
        d = self.root / "references" / "somenotes2023"
        fm = refs.read_frontmatter(d / "somenotes2023.md")
        self.assertFalse(fm["verified"])
        code, out = self.run_refs("status")
        self.assertIn("1 unverified: somenotes2023", out)

    def test_status_counts(self):
        self.drop("kingma2014adam.pdf", "adam", ocr_response("# Adam"), ADAM)
        self.drop("waiting.pdf", "w", None)
        refs.write_missing(refs.Project(self.root), [("10.1/x", "X", "paywalled")])
        code, out = self.run_refs("status")
        self.assertIn("converted:  0", out)
        self.assertIn("inbox:      2 PDF(s) waiting, 1 already in OCR cache", out)
        self.assertIn("missing:    1", out)


if __name__ == "__main__":
    unittest.main()
