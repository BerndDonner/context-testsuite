"""Six-page, PDF-first penalty diagnostic; tracing is optional and additive."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pymupdf
import pytest

from context_testsuite.diagnostic_observations import (
    PENALTY_PRECEDENCE, observe_diagnostic_pdf,
)
from context_testsuite.diagnostics import DIAGNOSTIC_ROOT, diagnose, available_diagnostics


def _pdf(tmp_path: Path, *, pages: int = 6) -> Path:
    output = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    for index in range(pages):
        page = doc.new_page()
        name = f"P{index + 1:02d}"
        page.insert_text((50, 40), name + ": controlled test")
        if index % 2 == 0:
            page.insert_text((50, 75), "Das digitale Geraet hat ein 12345 stelliges Display")
        else:
            page.insert_text((50, 75), "Das digitale Geraet hat ein 12345")
            page.insert_text((50, 90), "stelliges Display und einen Fehler.")
    doc.save(output)
    doc.close()
    return output


def _engine(tmp_path: Path, pdf: Path, *, error: bool = False) -> Path:
    import shlex
    source = tmp_path / "fake-context"
    source.write_text(
        "#!/bin/sh\nset -eu\n"
        "test -f source.tex\n"
        "printf '%s\\n' \"$@\" > arguments.txt\n" +
        ("exit 5\n" if error else f"cp {shlex.quote(str(pdf))} source.pdf\n")
    )
    source.chmod(0o755)
    return source


def test_six_cases_are_present_and_distinct():
    src = (DIAGNOSTIC_ROOT / "penalty-precedence.tex").read_text()
    assert "penalty-precedence" in available_diagnostics()
    assert len(PENALTY_PRECEDENCE) == 6
    for item in PENALTY_PRECEDENCE:
        assert f"\\CTScase{{{item['id']}}}" in src
    assert "\\doifmode{trace}{\\tracingparagraphs=2}" in src
    assert "\\CTSinactiveglue{10000}" in src
    assert "\\CTSinactiveglue{0}" in src
    assert "\\hskip 3pt penalty10000" in src
    assert "mathpenaltyfactor 67000" in src


def test_pdf_only_observations_are_page_aligned(tmp_path):
    result = observe_diagnostic_pdf("penalty-precedence", _pdf(tmp_path))
    assert result["summary"] == {"pages": 6, "observed": 6, "unclassifiable": 0}
    assert [row["case_id"] for row in result["pages"]] == [f"P{i:02d}" for i in range(1, 7)]
    assert [row["joined"] for row in result["pages"]] == [True, False, True, False, True, False]
    assert result["pages"][2]["scenario"]["glue"] == "inactive-field-10000"
    assert result["pages"][4]["scenario"]["math_factor"] == 67000
    assert result["pages"][5]["scenario"]["glue"] == "inactive-field-0"
    with pytest.raises(ValueError, match="Expected 6 PDF pages"):
        observe_diagnostic_pdf("penalty-precedence", _pdf(tmp_path, pages=4))


def test_diagnose_without_trace_emits_observations(tmp_path):
    result, out = diagnose("penalty-precedence", str(_engine(tmp_path, _pdf(tmp_path))),
                           tmp_path / "out", observe_pages=True)
    assert result["status"] == "observed"
    assert result["trace_summary"] == {"entries": 0, "decisions": 0, "complete_c_trace": False}
    assert result["page_observations"]["observed"] == 6
    assert (out / "page-observations.json").exists()
    assert (out / "output.pdf").exists()
    assert not (DIAGNOSTIC_ROOT / "penalty-precedence.pdf").exists()
    assert json.loads((out / "page-observations.json").read_text())["pages"][1]["joined"] is False
    assert (out / "work/arguments.txt").read_text().strip().splitlines() == ["--once", "source.tex"]


def test_trace_mode_is_opt_in_and_preserves_existing_trace_report(tmp_path):
    result, out = diagnose("penalty-precedence", str(_engine(tmp_path, _pdf(tmp_path))),
                           tmp_path / "out", observe_pages=True, trace_mode=True)
    assert result["status"] == "observed"
    assert (out / "work/arguments.txt").read_text().strip().splitlines() == [
        "--once", "--mode=trace", "source.tex"]


def test_existing_diagnostics_unchanged_and_invalid_observer_rejected(tmp_path):
    engine = str(_engine(tmp_path, _pdf(tmp_path)))
    result, out = diagnose("glue-option-entry", engine, tmp_path / "ordinary")
    assert result["status"] == "inconclusive"
    assert not (out / "page-observations.json").exists()
    with pytest.raises(ValueError, match="--observe-pages"):
        diagnose("glue-option-entry", engine, tmp_path / "invalid", observe_pages=True)
    assert not (tmp_path / "invalid").exists()


def test_bad_page_count_is_a_compile_or_observer_error(tmp_path):
    result, out = diagnose("penalty-precedence", str(_engine(tmp_path, _pdf(tmp_path, pages=4))),
                           tmp_path / "out", observe_pages=True)
    assert result["status"] == "compile_error"
    assert "Expected 6 PDF pages" in result["pdf_issue"]
    assert not (out / "page-observations.json").exists()


def test_diagnose_cli_optional_flags(tmp_path):
    exe = Path(__file__).resolve().parents[1] / "bin" / "context-testsuite"
    result = subprocess.run([str(exe), "diagnose", "--case", "penalty-precedence",
                             "--context", str(_engine(tmp_path, _pdf(tmp_path))),
                             "--output", str(tmp_path / "run"),
                             "--observe-pages", "--trace-mode"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Diagnosis: observed" in result.stdout
    assert (tmp_path / "run" / "page-observations.json").is_file()
