"""Contract and real-world golden tests for the prospective shared observer."""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from context_testsuite.math_observer import MathCase, observe_pdf, observe_text

FIXTURES = Path(__file__).parent / "fixtures" / "pdf-extraction"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("engine", ["reference", "candidate"])
def test_golden_pdf_break_observations(engine):
    cases = [row for row in EXPECTED if row["engine"] == engine]
    result = observe_pdf(FIXTURES / f"{engine}.pdf", [MathCase(row["id"]) for row in cases])
    assert [row.case_id for row in result] == [row["id"] for row in cases]
    assert [row.status for row in result] == ["observed"] * len(cases)
    assert [row.joined for row in result] == [row["joined"] for row in cases]


@pytest.mark.parametrize("body,joined", [
    ("Das digitale Geraet hat ein 12345 stelliges Display", True),
    ("Das digitale Geraet hat ein 12345stelliges Display", True),
    ("Das digitale Geraet hat ein 12345 stel-\nliges Display", True),
    ("Das digitale Geraet hat ein 12345\nstelliges Display", False),
    ("Das digitale Geraet hat ein\n12345 stelliges Display", True),
    ("Das digitale Geraet hat\nein 12345\nstelliges Display", False),
])
def test_text_layout_corner_cases(body, joined):
    result = observe_text("A0023\n" + body, MathCase("A0023"))
    assert result.status == "observed" and result.joined is joined


def test_ambiguous_extraction_cannot_be_mistaken_for_a_split():
    no_marker = observe_text("A0001\nDas digitale Geraet hat ein foo stelliges", MathCase("A0001"))
    duplicate = observe_text("A0001\nDas digitale Geraet 12345 12345 stelliges", MathCase("A0001"))
    bad_page = observe_text("A0002\nDas digitale Geraet 12345 stelliges", MathCase("A0001"))
    no_follower = observe_text("A0001\nDas digitale Geraet hat ein 12345", MathCase("A0001"))
    for obs in (no_marker, duplicate, bad_page, no_follower):
        assert obs.status == "unclassifiable" and obs.joined is None and obs.reason


def test_pdf_page_count_is_strict(tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    pdf = tmp_path / "one.pdf"
    doc.save(pdf)
    doc.close()
    with pytest.raises(ValueError, match="Expected 2 PDF pages"):
        observe_pdf(pdf, [MathCase("A0001"), MathCase("A0002")])
