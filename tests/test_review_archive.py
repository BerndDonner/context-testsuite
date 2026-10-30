"""Common review ZIP: complete evidence, no cache leakage, all CLI entry points."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pymupdf
import pytest

from context_testsuite.review_archive import create_review_archive, review_run


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin/context-testsuite"


def _pdf(path: Path, content: str) -> None:
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((70, 100), content)
        pdf.save(path)


def test_archive_includes_unicode_inputs_and_excludes_caches(tmp_path):
    result = tmp_path / "results"
    result.mkdir()
    (result / "checks.json").write_text('{"status":"fail"}', encoding="utf-8")
    (result / "before").mkdir()
    (result / "before/cases.pdf").write_bytes(b"test-evidence")
    (result / "home-before").mkdir()
    (result / "home-before/private-key").write_text("cache")
    inputs = tmp_path / "Datenblätter"
    inputs.mkdir()
    (inputs / "Überblick.tex").write_text("üöä\\math{3}", encoding="utf-8")
    archive = tmp_path / "review.zip"
    create_review_archive(result, archive, kind="run", inputs={"definitions": inputs},
                          engines={"candidate": "/missing/bin/context"},
                          parameters={"suite": "math-basic"})
    with zipfile.ZipFile(archive) as zf:
        files = set(zf.namelist())
        assert "results/before/cases.pdf" in files
        assert "results/checks.json" in files
        assert "inputs/definitions/Überblick.tex" in files
        assert not any("private-key" in name for name in files)
        assert "software/context_testsuite/math_suites.py" in files
        manifest = json.loads(zf.read("manifest.json"))
        row = next(x for x in manifest["files"] if x["path"] == "results/before/cases.pdf")
        assert row["sha256"] == hashlib.sha256(b"test-evidence").hexdigest()
        assert manifest["engines"]["candidate"]["version"] is None
        assert manifest["inputs"]["definitions"]["status"] == "included"


def test_review_zip_written_after_failure_and_does_not_overwrite(tmp_path):
    result = tmp_path / "out"
    with pytest.raises(RuntimeError, match="simulated"):
        with review_run(True, result, kind="diagnose"):
            result.mkdir()
            (result / "error.log").write_text("failed", encoding="utf-8")
            raise RuntimeError("simulated")
    with zipfile.ZipFile(tmp_path / "out.zip") as zf:
        assert zf.read("results/error.log") == b"failed"
        assert "RuntimeError: simulated" in json.loads(zf.read("manifest.json"))["error"]
    with pytest.raises(ValueError, match="already exists"):
        with review_run(True, result, kind="diagnose"):
            pass


def test_cli_zip_options_on_all_report_commands():
    for cmd in (["run"], ["diagnose"],
                ["metamorphic"], ["audit-math"], ["pdf", "compare"]):
        proc = subprocess.run([str(CLI), *cmd, "--help"], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "--zip" in proc.stdout, cmd


def test_cli_run_zip_contains_compiled_pdf_and_source(tmp_path):
    pdf = tmp_path / "mock.pdf"
    _pdf(pdf, "smoke")
    fake = tmp_path / "mock-context"
    fake.write_text("#!/bin/sh\nset -eu\n"
                    "if [ \"${1:-}\" = \"--version\" ]; then echo 'mtx-context | local build: p1'; exit 0; fi\n"
                    "test -f include/conventions/units.tex\n"
                    "for arg do :; done\n"
                    f"cp '{pdf}' \"${{arg%.tex}}.pdf\"\n")
    fake.chmod(0o755)
    out = tmp_path / "math-run"
    proc = subprocess.run([str(CLI), "run", "--context", str(fake),
                           "--suite", "units-smoke", "--output", str(out), "--zip"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    with zipfile.ZipFile(tmp_path / "math-run.zip") as zf:
        assert "results/run-report.json" in zf.namelist()
        assert "results/units-smoke/units-regression/units-regression.pdf" in zf.namelist()
        assert "inputs/units-smoke/units-regression.tex" in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        assert "p1" in manifest["engines"]["candidate"]["version"]


def test_pdf_compare_zip_includes_both_original_pdfs(tmp_path):
    old, new = tmp_path / "old.pdf", tmp_path / "new.pdf"
    _pdf(old, "before")
    _pdf(new, "after")
    out = tmp_path / "comparison"
    proc = subprocess.run([str(CLI), "pdf", "compare", "--reference", str(old),
                           "--candidate", str(new), "--output", str(out),
                           "--zip", "--dpi", "72"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    with zipfile.ZipFile(tmp_path / "comparison.zip") as zf:
        assert zf.read("inputs/reference/old.pdf") == old.read_bytes()
        assert zf.read("inputs/candidate/new.pdf") == new.read_bytes()
        assert "results/report.html" in zf.namelist()
        assert "results/report.json" in zf.namelist()


def test_missing_pdf_reference_is_recorded(tmp_path):
    new = tmp_path / "new.pdf"
    _pdf(new, "after")
    out = tmp_path / "comparison"
    proc = subprocess.run([str(CLI), "pdf", "compare", "--reference", str(tmp_path / "missing.pdf"),
                           "--candidate", str(new), "--output", str(out),
                           "--zip", "--dpi", "72"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    with zipfile.ZipFile(tmp_path / "comparison.zip") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["inputs"]["reference"]["status"] == "missing"
        assert "results/report.json" in zf.namelist()


@pytest.mark.parametrize("suite,expectation", [
    ("math-basic", "inputs/math-basic/cases.tex"),
    ("math-extended", "inputs/math-extended/cases.json"),
])
def test_math_comparison_zip_contains_both_sides_and_expectations(tmp_path, suite, expectation):
    # The mock deliberately cannot provide valid math observations. The result
    # must still include both candidate and baseline PDFs, logs and definitions.
    page = tmp_path / "dummy.pdf"
    _pdf(page, "not a real math suite PDF")
    mock = tmp_path / "context-stub"
    mock.write_text("#!/bin/sh\nset -eu\n"
                    "if [ \"${1:-}\" = \"--version\" ]; then echo 'mtx-context | local build: mock'; exit 0; fi\n"
                    "for arg do :; done\n"
                    f"cp '{page}' \"${{arg%.tex}}.pdf\"\n")
    mock.chmod(0o755)
    output = tmp_path / suite
    command = [str(CLI), "run", "--context", str(mock), "--baseline", str(mock),
               "--suite", suite, "--output", str(output), "--zip"]
    proc = subprocess.run(command, capture_output=True, text=True)
    assert proc.returncode == 2, proc.stderr + proc.stdout  # incomplete by design
    with zipfile.ZipFile(tmp_path / (suite + ".zip")) as zf:
        names = set(zf.namelist())
        assert expectation in names
        assert f"results/{suite}/before/cases.pdf" in names
        assert f"results/{suite}/after/cases.pdf" in names
        assert f"results/{suite}/before/build.log" in names
        assert f"results/{suite}/after/build.log" in names
        assert f"results/{suite}/checks.json" in names
        report = json.loads(zf.read("results/run-report.json"))
        assert report["suites"][0]["result"] == "incomplete"
