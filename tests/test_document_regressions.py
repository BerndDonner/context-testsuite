"""Document regression CLI/runner self-tests; no real ConTeXt needed."""
import hashlib
import json
import shlex
import subprocess
import zipfile
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
    script += 'if [ "${1:-}" = "--version" ]; then echo "ConTeXt 2026.10.25-p1"; exit 0; fi\n'
    script += "test -f assets/example.dat\n"
    script += 'for arg do test "$arg" != "--once" || exit 42; done\n'
    script += "for arg do :; done\n"
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
    assert report["invocation"]["once"] is False
    assert "testsuite_revision" in report
    assert "2026.10.25-p1" in report["engine_version"]
    for name in case_names(root):
        assert (out / name / "work" / "assets" / "example.dat").is_file()
        assert not (out / name / "work" / "reference.pdf").exists()
        assert (out / name / "work" / "source.pdf").is_file()
        assert (out / name / "comparison" / "report.html").is_file()
        assert (out / name / "comparison" / "text.diff").is_file()
    output = capsys.readouterr().out
    assert f"xdg-open {out / 'a-first' / 'comparison' / 'report.html'}" in output
    assert f"xdg-open {out / 'b-extra' / 'comparison' / 'report.html'}" in output

    # Reusing an occupied run directory would mix old and new cases.
    fake_context(engine, old)
    with pytest.raises(ValueError, match="already exists and is not empty"):
        run_regressions(str(engine), "a-first", out, dpi=72, root=root)
    next_run = tmp_path / "results-next"
    assert run_regressions(str(engine), "a-first", next_run, dpi=72, root=root) == 0
    assert not (next_run / "a-first" / "comparison" / "text.diff").exists()
    assert json.loads((next_run / "regression-report.json").read_text())["totals"]["identical"] == 1
    assert (out / "b-extra" / "comparison" / "report.html").is_file()


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
    result = subprocess.run([str(CLI), "list"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert all(f"  {name}" in result.stdout for name in names)
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
    result = subprocess.run([str(CLI), "run", "--suite", "documents", "--context", str(engine),
                             "--case", "mathe-m3a-ws2526", "--output", str(out),
                             "--dpi", "72"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert f"xdg-open {out / 'mathe-m3a-ws2526' / 'comparison' / 'report.html'}" in result.stdout
    assert (out / "mathe-m3a-ws2526" / "work" / "include" / "metapost" / "mymacros.mp").is_file()
    assert (out / "mathe-m3a-ws2526" / "work" / "assets" / "sabel.png").is_file()
    assert json.loads((out / "regression-report.json").read_text())["totals"]["selected"] == 1


def test_review_zip_is_self_contained_and_keeps_unicode(tmp_path):
    old, new = tmp_path / "old.pdf", tmp_path / "new.pdf"
    pdf(old, "reference")
    pdf(new, "candidate")
    root = tmp_path / "cases"
    case = fixture(root, "cmt", old)
    folder = case / "Datenblätter"
    folder.mkdir()
    (folder / "Überblick.txt").write_text("Information", encoding="utf-8")
    engine = fake_context(tmp_path / "context-stub", new)
    output = tmp_path / "runs" / "2026-p1"
    assert run_regressions(str(engine), "all", output, root=root, dpi=72,
                           zip_results=True) == 0
    archive = output.with_name("2026-p1.zip")
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        expected = {"README.md", "manifest.json", "regression-report.json",
                    "cmt/reference.pdf", "cmt/candidate.pdf", "cmt/context-build.log",
                    "cmt/engine-path.txt", "cmt/source/source.tex",
                    "cmt/source/Datenblätter/Überblick.txt",
                    "cmt/comparison/report.html", "cmt/comparison/report.json"}
        assert expected <= names
        assert not any("/cache/" in n or "/home/" in n or ".tuc" in n for n in names)
        assert zf.read("cmt/reference.pdf") == old.read_bytes()
        assert zf.read("cmt/candidate.pdf") == new.read_bytes()
        assert "ConTeXt 2026.10.25-p1" in zf.read("regression-report.json").decode()
        manifest = json.loads(zf.read("manifest.json"))
        import hashlib
        record = next(row for row in manifest["files"] if row["path"] == "cmt/candidate.pdf")
        assert record["sha256"] == hashlib.sha256(new.read_bytes()).hexdigest()
    # Reusing either the archive or the result directory is forbidden.
    with pytest.raises(ValueError, match="already exists"):
        run_regressions(str(engine), "all", output, root=root, zip_results=True)


def test_review_zip_even_when_compiler_fails(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    fixture(root, "first", old)
    fixture(root, "second", old)
    engine = fake_context(tmp_path / "bad-context", old, fail=True)
    output = tmp_path / "out"
    assert run_regressions(str(engine), "all", output, root=root, zip_results=True) == 2
    with zipfile.ZipFile(tmp_path / "out.zip") as zf:
        names = set(zf.namelist())
        assert "first/context-build.log" in names
        assert "second/context-build.log" in names
        assert "first/reference.pdf" in names
        assert "second/reference.pdf" in names
        assert "first/candidate.pdf" not in names
        assert json.loads(zf.read("regression-report.json"))["totals"]["failed"] == 2


def test_output_symlink_rejected(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "reference")
    root = tmp_path / "cases"
    fixture(root, "first", old)
    engine = fake_context(tmp_path / "fake", old)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        run_regressions(str(engine), "all", link, root=root)


def test_cli_zip_option(tmp_path):
    old = tmp_path / "old.pdf"
    pdf(old, "same")
    engine = tmp_path / "mock-context"
    engine.write_text(f'#!/bin/sh\nset -eu\nif [ "${{1:-}}" = "--version" ]; then echo p1; exit 0; fi\n'
                      f'for arg do test "$arg" != "--once" || exit 42; done\n'
                      f'for arg do :; done\ncp {shlex.quote(str(old))} "${{arg%.tex}}.pdf"\n')
    engine.chmod(0o755)
    out = tmp_path / "single-run"
    result = subprocess.run([str(CLI), "run", "--suite", "documents", "--context", str(engine),
                             "--case", "mathe-m3a-ws2526", "--output", str(out),
                             "--dpi", "72", "--zip"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Review ZIP:" in result.stdout
    with zipfile.ZipFile(tmp_path / "single-run.zip") as zf:
        assert "inputs/document-regressions/reference.pdf" in zf.namelist()
        assert "results/run-summary.json" in zf.namelist()


def test_shared_process_can_keep_math_once_and_disable_it_for_documents(tmp_path):
    from context_testsuite.context_process import run_context_process
    engine = tmp_path / "record-argv"
    engine.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > argv.txt\n')
    engine.chmod(0o755)
    for once in (True, False):
        work = tmp_path / ("math" if once else "document")
        result = run_context_process(str(engine), "test.tex", work=work,
                                     home=work / "home", tex_cache=work / "cache",
                                     stdout_log=work / "stdout.log", once=once)
        assert result.exit_code == 0
        assert (work / "argv.txt").read_text().splitlines() == (
            ["--once", "test.tex"] if once else ["test.tex"])


def test_engine_version_ignores_cache_initialization_and_keeps_late_version(tmp_path):
    """The first 8 KiB of `context --version` need not contain ConTeXt's version."""
    from context_testsuite.document_regressions import _engine_version

    engine = tmp_path / "noisy-context"
    engine.write_text(
        '#!/bin/sh\n'
        'printf "mtx-context | local build: 2026.10.25-p1 (math-glue-noautobreak)\\n"\n'
        'printf "Initializing ConTeXt cache ...\\n"\n'
        'i=0\nwhile [ "$i" -lt 200 ]; do\n'
        '  printf "resolvers | resolving | inspecting /nix/store/some-very-long-cache-path-%s\\n" "$i"\n'
        '  i=$((i + 1))\ndone\n'
        'printf "mtx-context | ConTeXt Process Management 1.06\\n"\n'
        'printf "mtx-context | main context file: /nix/store/example/context.mkxl\\n"\n'
        'printf "mtx-context | current version: 2026.10.25 20:06\\n"\n',
        encoding="utf-8",
    )
    engine.chmod(0o755)

    version = _engine_version(str(engine))
    assert version == (
        "mtx-context | local build: 2026.10.25-p1 (math-glue-noautobreak)\n"
        "mtx-context | ConTeXt Process Management 1.06\n"
        "mtx-context | main context file: /nix/store/example/context.mkxl\n"
        "mtx-context | current version: 2026.10.25 20:06"
    )
    assert "resolvers" not in version
    assert "Initializing" not in version


def test_engine_version_fallback_and_missing_metadata(tmp_path):
    from context_testsuite.document_regressions import _engine_version, _version_summary

    assert _version_summary("ConTeXt 2026.10.25-p1\n") == "ConTeXt 2026.10.25-p1"
    assert _version_summary("p1\n") == "p1"  # minimal CLI test stub
    assert _version_summary("Initializing ConTeXt cache ...\nresolvers | resolving | scanning\n") is None

    engine = tmp_path / "broken-version"
    engine.write_text("#!/bin/sh\necho 'mtx-context | current version: broken'\nexit 1\n")
    engine.chmod(0o755)
    assert _engine_version(str(engine)) is None
