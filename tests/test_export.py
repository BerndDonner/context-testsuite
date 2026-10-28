"""Shareable ZIP exports: independent of ConTeXt, Poppler, and Nix."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pymupdf
import pytest

from context_testsuite.export import export_cases, parse_tex


ROOT = Path(__file__).resolve().parents[1]


def make_pdf(dest: Path, labels: list[str]):
    doc = pymupdf.open()
    for label in labels:
        page = doc.new_page()
        page.insert_text((50, 72), label)
        page.insert_text((50, 100), "Das digitale Geraet hat ein 12345 stelliges Display.")
    doc.save(dest)
    doc.close()


def make_source(labels: list[str]):
    return (r"\mainlanguage[de]" + "\n" + r"\starttext" + "\n"
            + "\\page\n".join(
                f"\\begingroup\n\\subject{{{label}}}\nexample {label}\n\\endgroup\n" for label in labels
            ) + r"\stoptext" + "\n")


def make_run(tmp_path: Path, *, suite="math-adversarial", baseline=True):
    root = tmp_path / "run"
    suite_dir = root / suite
    cases = [["A0001", "A0002"], ["A0003", "A0004"]] if suite == "math-adversarial" else [["P03", "L15"]]
    for i, labels in enumerate(cases, 1):
        for role in (["candidate", "reference"] if suite == "math-adversarial" else ["after", "before"]):
            if role in ("reference", "before") and not baseline:
                continue
            path = (suite_dir / f"shard-{i:03}" / role if suite == "math-adversarial"
                    else suite_dir / role)
            path.mkdir(parents=True, exist_ok=True)
            (path / "cases.tex").write_text(make_source(labels), encoding="utf-8")
            make_pdf(path / "cases.pdf", labels)
    root.mkdir(parents=True, exist_ok=True)
    (root / "run-report.json").write_text(json.dumps({
        "schema_version": 1,
        "candidate_context": "/path/to/hans/context",
        "reference_context": "/path/to/original/context" if baseline else None,
        "suites": [{"suite": suite, "result": "fail"}],
    }))
    return root


def pdf_ids(blob: bytes):
    with pymupdf.open(stream=blob, filetype="pdf") as doc:
        return [page.get_text().splitlines()[0] for page in doc]


def test_export_selected_cases_from_shards_in_requested_order(tmp_path):
    root = make_run(tmp_path)
    target = tmp_path / "my-selection.zip"
    export_cases(root, ["A0003", "A0001"], target)
    with ZipFile(target) as archive:
        assert set(archive.namelist()) == {"README.txt", "tests.tex", "result.pdf"}
        src = archive.read("tests.tex").decode()
        _, chunks = parse_tex(src)
        assert [case for case, _ in chunks] == ["A0003", "A0001"]
        assert "example A0004" not in src
        assert pdf_ids(archive.read("result.pdf")) == ["A0003", "A0001"]
        assert "no python" in archive.read("README.txt").decode().lower()


def test_export_failed_math_extended_run_with_baseline(tmp_path):
    root = make_run(tmp_path, suite="math-extended")
    target = tmp_path / "extended.zip"
    export_cases(root, ["L15", "P03"], target, include_baseline=True)
    with ZipFile(target) as archive:
        assert "reference.pdf" in archive.namelist()
        assert pdf_ids(archive.read("result.pdf")) == ["L15", "P03"]
        assert pdf_ids(archive.read("reference.pdf")) == ["L15", "P03"]
        assert [case for case, _ in parse_tex(archive.read("tests.tex").decode())[1]] == ["L15", "P03"]


def test_bad_pdf_page_label_rejected_without_writing_output(tmp_path):
    root = make_run(tmp_path)
    wrong = root / "math-adversarial/shard-001/candidate/cases.pdf"
    make_pdf(wrong, ["A0002", "A0001"])
    output = tmp_path / "wrong.zip"
    with pytest.raises(ValueError, match="does not unambiguously match"):
        export_cases(root, ["A0001"], output)
    assert not output.exists()


def test_page_count_mismatch_rejected(tmp_path):
    root = make_run(tmp_path)
    path = root / "math-adversarial/shard-001/candidate/cases.pdf"
    make_pdf(path, ["A0001"])
    with pytest.raises(ValueError, match="Page count mismatch"):
        export_cases(root, ["A0001"], tmp_path / "wrong.zip")


def test_missing_selected_case_and_unknown_root_rejected(tmp_path):
    root = make_run(tmp_path)
    with pytest.raises(ValueError, match="Cases not found"):
        export_cases(root, ["A1234"], tmp_path / "absent.zip")
    with pytest.raises(ValueError, match="run-report.json"):
        export_cases(tmp_path, ["A0001"], tmp_path / "invalid.zip")


def test_no_implicit_reference_and_no_overwrite(tmp_path):
    root = make_run(tmp_path, baseline=False)
    output = tmp_path / "out.zip"
    with pytest.raises(ValueError, match="No explicitly requested reference"):
        export_cases(root, ["A0001"], output, include_baseline=True)
    export_cases(root, ["A0001"], output)
    original = output.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        export_cases(root, ["A0002"], output)
    assert output.read_bytes() == original


def test_reference_source_drift_rejected(tmp_path):
    root = make_run(tmp_path)
    ref = root / "math-adversarial/shard-001/reference/cases.tex"
    ref.write_text(ref.read_text().replace("example A0001", "modified A0001"))
    with pytest.raises(ValueError, match="Reference TeX differs"):
        export_cases(root, ["A0001"], tmp_path / "out.zip", include_baseline=True)


def test_invalid_and_duplicate_case_lists(tmp_path):
    root = make_run(tmp_path)
    for ids in ([], ["A0001", "A0001"]):
        with pytest.raises(ValueError, match="unique case IDs"):
            export_cases(root, ids, tmp_path / "bad.zip")
    with pytest.raises(ValueError, match=".zip file"):
        export_cases(root, ["A0001"], tmp_path / "bad.pdf")


def test_cli_export_in_subprocess(tmp_path):
    root = make_run(tmp_path)
    output = tmp_path / "shared.zip"
    proc = subprocess.run([sys.executable, "-m", "context_testsuite", "export",
                           "--from", str(root), "--cases", "A0002,A0003",
                           "--include-baseline", "--output", str(output)],
                          text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert "Exported 2 cases" in proc.stdout
    with ZipFile(output) as archive:
        assert pdf_ids(archive.read("result.pdf")) == ["A0002", "A0003"]
    error = subprocess.run([sys.executable, "-m", "context_testsuite", "export",
                            "--from", str(root), "--cases", "A0001,",
                            "--output", str(tmp_path / "no.zip")],
                           text=True, capture_output=True)
    assert error.returncode == 2
    assert "without empty IDs" in error.stderr


def test_current_frozen_case_sources_have_expected_page_counts():
    base = ROOT / "src/context_testsuite/cases/math"
    assert len(parse_tex((base / "basic/cases.tex").read_text())[1]) == 12
    assert len(parse_tex((base / "extended/cases.tex").read_text())[1]) == 76
