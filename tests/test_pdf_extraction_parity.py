"""PDF extraction *test* corpus, not production analyzer or refactoring.

The goldens are eight original pages from the uploaded 2026-10-28
Hans-vs-upstream run. They test PyMuPDF on real line break cases, including
hyphenated words and direct glue nodes, before any Poppler migration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pymupdf
import pytest

ROOT = Path(__file__).parent / "fixtures" / "pdf-extraction"
EXPECTED = json.loads((ROOT / "expected.json").read_text(encoding="utf-8"))


def _same_line_by_text(raw: str) -> bool:
    candidates = [line for line in raw.splitlines() if "12345" in line]
    assert len(candidates) == 1, candidates
    return bool(re.search(r"12345\s+ste", candidates[0]))


def _same_line_by_geometry(page: pymupdf.Page) -> bool:
    """Use the PDF's line indices, not the extracted newline characters."""
    words = page.get_text("words", sort=True)
    marker = [w for w in words if w[4] == "12345"]
    assert len(marker) == 1, marker
    m = marker[0]
    # The 'ste...' portion is on the same geometrical line iff its block and
    # line IDs match. Soft hyphens remain part of the word's text.
    tails = [w for w in words if w[4].startswith("ste")]
    assert len(tails) == 1, tails
    return (m[5], m[6]) == (tails[0][5], tails[0][6])


@pytest.mark.parametrize("engine", ["reference", "candidate"])
def test_real_pdfs_are_correctly_classified_by_pymupdf(engine: str):
    expected = [row for row in EXPECTED if row["engine"] == engine]
    with pymupdf.open(ROOT / f"{engine}.pdf") as pdf:
        assert len(pdf) == len(expected)
        for row in expected:
            page = pdf[row["page"]]
            assert row["id"] in page.get_text()
            text_join = _same_line_by_text(page.get_text(sort=True))
            geometry_join = _same_line_by_geometry(page)
            assert text_join == row["joined"], row
            assert geometry_join == row["joined"], row


@pytest.mark.skipif(os.environ.get("CTS_TEST_POPPLER") != "1" or shutil.which("pdftotext") is None,
                    reason="Optional historical cross-check: CTS_TEST_POPPLER=1 and Poppler required")
@pytest.mark.parametrize("engine", ["reference", "candidate"])
def test_pymupdf_and_poppler_agree_on_real_goldens(engine: str):
    path = ROOT / f"{engine}.pdf"
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, check=True, text=True, encoding="utf-8",
    )
    pages = [page for page in completed.stdout.split("\f") if page.strip()]
    expected = [row for row in EXPECTED if row["engine"] == engine]
    assert len(pages) == len(expected)
    with pymupdf.open(path) as pdf:
        for row, poppler_text in zip(expected, pages):
            assert row["id"] in poppler_text
            assert _same_line_by_text(poppler_text) == row["joined"], row
            assert _same_line_by_geometry(pdf[row["page"]]) == row["joined"], row
