"""Document regression CLI/runner self-tests; no real ConTeXt needed."""
import hashlib
import json
import shlex
import subprocess
from pathlib import Path

import pymupdf
import pytest

from context_testsuite.document_regressions import case_names, run_regressions


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "context-testsuite"


def pdf(path: Path, text: str):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 100), text)
        doc.save(path)


def fake_context(path: Path, source_pdf: Path, *, fail: bool = False):
    script = "#!/bin/sh\nset -eu\n"
    script += "test -f assets/example.dat\n"
    script += "for arg do :; done\n"  # --once precedes .tex
    if fail:
        script += "exit 4\n"
    else:
        script += f"cp {shlex.quote(str(source_pdf))} \"${{arg%.tex}}.pdf\"\n"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def fixture(root: Path, name: str, source_pdf: Path):
    case = root / name
    (case / "assets").mkdir(parents=True)
    (case / "source.tex").write_text("\\starttext Hello\\stoptext\n", encoding="utf-8")
    (case / "assets" / "example.dat").write_text("dependency")
    (case / "reference.pdf").write_bytes(source_pdf.read_bytes())
    return case


def test_auto_discovery_and_independent_workspaces(tmp_path, capsys):
    old = tmp_path / "old.pdf"
    new = tmp_path / "new.pdf"
    pdf(old, "reference")
    pdf(new, "changed")
    root = tmp_path / "tests" / "regressions"
    case_b = fixture(root, "b-extra", old)
    fixture(root, "a-first", old)
    engine = fake_context(tmp_path / "context-stub", new)
    out = tmp_path / "results"
    ref_hash = hashlib.sha256((case_b / "reference.pdf").read_bytes()).hexdigest()

    assert case_names(root) == ["a-first", "b-extra"]
    assert run_regressions(str(engine), "all", out, dpi=72, root=root) == 0
    assert hashlib.sha256((case_b / "reference.pdf").read_bytes()).hexdigest() == ref_hash
    report = json.loads((out / "regression-report.json").read_text())
    assert [item["case"] for item in report["cases"]] == ["a-first", "b-extra"]
    assert report["totals"] == {"selected": 2, "changed": 2, "identical": 0, "failed": 0}
    for name in case_names(root):
        assert (out / name / "work" / "assets" / "example.dat").is_file()
        assert not (out / name / "work" / "reference.pdf").exists()
        assert (out / name / "work" / "source.pdf").is_file()
        assert (out / name / "comparison" / "report.html").is_file()
        assert (out / name / "comparison" / "text.diff").is_file()
    output = capsys.readouterr().out
    assert f"xdg-open {out / 'a-first' / 'comparison' / 'report.html'}" in output
    assert f"xdg-open {out / 'b-extra' / 'comparison' / 'report.html'}" in output

    # Repeat with an identical candidate. Existing text.diff is removed; candidate work reset.
    fake_context(engine, old)
    assert run_regressions(str(engine), "a-first", out, dpi=72, root=root) == 0
    assert not (out / "a-first" / "comparison" / "text.diff").exists()
    assert json.loads((out / "regression-report.json").read_text())["totals"]["identical"] == 1


def test_compile_failure_continues_and_is_reported(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    fixture(root, "a", old)
    fixture(root, "b", old)
    engine = fake_context(tmp_path / "fake", old, fail=True)
    out = tmp_path / "out"
    assert run_regressions(str(engine), "all", out, root=root) == 2
    data = json.loads((out / "regression-report.json").read_text())
    assert data["totals"]["failed"] == 2
    assert [case["status"] for case in data["cases"]] == ["compile_error", "compile_error"]
    assert not (out / "a" / "comparison" / "report.html").exists()


def test_invalid_fixture_is_not_silently_skipped(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    fixture(root, "good", old)
    broken = fixture(root, "broken", old)
    (broken / "reference.pdf").unlink()
    engine = fake_context(tmp_path / "fake", old)
    with pytest.raises(ValueError, match="missing frozen reference.pdf"):
        run_regressions(str(engine), "all", tmp_path / "output", root=root)
    assert not (tmp_path / "output").exists()  # validation precedes execution


def test_invalid_source_and_symlink(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    case = fixture(root, "broken", old)
    (case / "other.tex").write_text("second")
    engine = fake_context(tmp_path / "fake", old)
    with pytest.raises(ValueError, match="exactly one root-level"):
        run_regressions(str(engine), "all", tmp_path / "out", root=root)
    (case / "other.tex").unlink()
    (case / "assets" / "link.dat").symlink_to(old)
    with pytest.raises(ValueError, match="contains symlink"):
        run_regressions(str(engine), "all", tmp_path / "out", root=root)


def test_disallows_output_inside_or_above_fixtures(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    fixture(root, "case", old)
    engine = fake_context(tmp_path / "fake", old)
    for unsafe in (root, root / "case" / "build", tmp_path):
        with pytest.raises(ValueError, match="Output must be separate"):
            run_regressions(str(engine), "case", unsafe, root=root)
    with pytest.raises(ValueError, match="Unknown regression"):
        run_regressions(str(engine), "absent", tmp_path / "out", root=root)


def test_real_fixture_discovery_and_cli_list():
    names = ["cmt-e3a-ws25", "mathe-m3a-ws2526", "mathe-m3a-ws2526-nachtermin", "messtechnik-ws25"]
    result = subprocess.run([str(CLI), "regression", "list"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == names
    root = ROOT / "tests" / "regressions"
    for name in names:
        case = root / name
        assert len(list(case.glob("*.tex"))) == 1
        assert (case / "reference.pdf").is_file()

    cmt = root / "cmt-e3a-ws25"
    assert (cmt / "assets" / "sabel.png").is_file()
    assert (cmt / "include" / "metapost" / "mymacros.mp").is_file()
    datasheet = cmt / "GBS-CMT" / "Datenblätter" / "Datenblatt_Hochdrucksensoren.pdf"
    with pymupdf.open(datasheet) as doc:
        assert len(doc) >= 2
    with pymupdf.open(cmt / "reference.pdf") as doc:
        assert len(doc) == 4


def test_cli_single_case_standalone_without_real_engine(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "does not match")
    engine = tmp_path / "stub"
    # This CLI test runs a real bundled fixture; the mock compiler ignores ConTeXt source.
    engine.write_text(f"#!/bin/sh\nset -eu\nfor arg do :; done\ncp {shlex.quote(str(old))} \"${{arg%.tex}}.pdf\"\n")
    engine.chmod(0o755)
    out = tmp_path / "out"
    result = subprocess.run([str(CLI), "regression", "run", "--context", str(engine),
                             "--case", "mathe-m3a-ws2526", "--output", str(out),
                             "--dpi", "72"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert f"xdg-open {out / 'mathe-m3a-ws2526' / 'comparison' / 'report.html'}" in result.stdout
    assert (out / "mathe-m3a-ws2526" / "work" / "include" / "metapost" / "mymacros.mp").is_file()
    assert (out / "mathe-m3a-ws2526" / "work" / "assets" / "sabel.png").is_file()
    assert json.loads((out / "regression-report.json").read_text())["totals"]["selected"] == 1
