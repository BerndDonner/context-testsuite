"""Smoke-tests of public command-line interfaces, without ConTeXt or Nix."""
from pathlib import Path
import json
import os
import subprocess
from shlex import quote

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
CLI = [str(ROOT / "bin/context-testsuite")]


def _pdf(file, text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), text)
    doc.save(file)
    doc.close()


def test_cli_python_has_pymupdf():
    """The Python resolved by the CLI must have the PDF dependency.

    pytest itself can run with a different Python than `python` on PATH.
    Catch that shell misconfiguration explicitly instead of reporting
    confusing failures in unrelated CLI tests.
    """
    res = subprocess.run(
        ["python", "-c", "import pymupdf; print(pymupdf.VersionBind)"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, (
        "The shell's `python` cannot import pymupdf. "
        "Re-enter the Nix devShell (nix develop).\n"
        f"stdout: {res.stdout}\nstderr: {res.stderr}"
    )


def test_list_command():
    res = subprocess.run(CLI + ["list", "--json"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.lstrip().startswith("{"), res.stdout
    catalog = json.loads(res.stdout)
    assert {"math-basic", "math-extended", "math-adversarial", "units-smoke", "units-stress", "documents"} == set(catalog)


def test_pdf_direct_paths(tmp_path):
    old = tmp_path / "previous.pdf"
    new = tmp_path / "current.pdf"
    _pdf(old, "before")
    _pdf(new, "after")
    out = tmp_path / "report with spaces"
    res = subprocess.run(CLI + ["pdf", "compare", "--reference", str(old),
                                    "--candidate", str(new), "--output", str(out),
                                    "--dpi", "72"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "changed"
    assert report["summary"]["pages_text_changed"] == 1
    assert (out / "report.html").is_file()
    assert "To see the detailed side-by-side report:" in res.stdout
    assert f"xdg-open {quote(str(out / 'report.html'))}" in res.stdout


def test_pdf_missing_candidate_is_error(tmp_path):
    res = subprocess.run(CLI + ["pdf", "compare", "--reference", str(tmp_path / "old.pdf"),
                                    "--candidate", str(tmp_path / "absent.pdf")],
                         capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 2
    assert "Build-PDF" in res.stderr


def test_units_smoke_runner_with_stub_executable(tmp_path):
    # A fake compiler checks only independent source copying & runner/report wiring.
    # It does not validate ConTeXt typographic output.
    source_pdf = tmp_path / "fixture.pdf"
    _pdf(source_pdf, "smoke test")
    # The fake compiler is deliberately /bin/sh. This is a runner test,
    # not a test of how a second Python resolves dependencies on PATH.
    fake = tmp_path / "fake-context"
    fake.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test -f include/conventions/units.tex\n"
        "test -f include/workarounds/lmtx-units-2026.tex\n"
        "for arg do :; done\n"  # Last arg is the .tex filename.
        f"cp '{source_pdf}' \"${{arg%.tex}}.pdf\"\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    out = tmp_path / "run-output"
    res = subprocess.run(CLI + ["run", "--context", str(fake), "--suite", "units-smoke",
                                    "--output", str(out)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    summary = json.loads((out / "run-report.json").read_text())
    assert summary["suites"][0]["result"] == "pass_compile_only"
    assert (out / "units-smoke/units-regression/include/conventions/units.tex").is_file()


def test_launcher_uses_shell_python_even_if_python3_is_unrelated(tmp_path):
    """CLI uses the same `python` command as the devShell, not `python3`."""
    wrong_python = tmp_path / "python3"
    wrong_python.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    wrong_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    result = subprocess.run(CLI + ["list", "--json"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "math-extended" in json.loads(result.stdout)


def test_human_list_discovers_document_and_diagnostic_cases():
    res = subprocess.run(CLI + ["list"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert "Document cases (run --suite documents --case):" in res.stdout
    assert "cmt-e3a-ws25" in res.stdout
    assert "Diagnostics (diagnose --case):" in res.stdout
    assert "noautobreak-explicit" in res.stdout


def test_help_discovers_zip_and_multipass_policy():
    root = subprocess.run(CLI + ["--help"], capture_output=True, text=True)
    assert root.returncode == 0
    assert "regression run" not in root.stdout
    run = subprocess.run(CLI + ["run", "--help"], capture_output=True, text=True)
    assert run.returncode == 0
    assert "--zip" in run.stdout
    assert "multipass" in run.stdout
    assert "--case" in run.stdout
    assert "default" in run.stdout
    assert "all" in run.stdout


def test_regression_subcommand_is_removed():
    proc = subprocess.run(CLI + ["regression", "run", "--help"], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "invalid choice: 'regression'" in proc.stderr


def test_documents_requires_no_engine_baseline(tmp_path):
    res = subprocess.run(CLI + ["run", "--suite", "documents", "--context", "/bin/true",
                                "--baseline", "/bin/true", "--output", str(tmp_path / "x")],
                         capture_output=True, text=True)
    assert res.returncode == 2
    assert "references are frozen PDFs" in res.stderr
    assert not (tmp_path / "x").exists()


def test_named_case_rejected_for_math(tmp_path):
    res = subprocess.run(CLI + ["run", "--suite", "math-basic", "--case", "messtechnik-ws25",
                                "--context", "/bin/true", "--output", str(tmp_path / "x")],
                         capture_output=True, text=True)
    assert res.returncode == 2
    assert "only valid" in res.stderr


def test_run_summary_and_all_dispatch(monkeypatch, tmp_path):
    """CLI merges reports, not the two specialist test algorithms."""
    from context_testsuite import cli, document_regressions
    calls = []
    engine = tmp_path / "engine"
    engine.write_text("#!/bin/sh\necho 'mtx-context | current version: 2026.10.29'\n")
    engine.chmod(0o755)

    def builtins(context, baseline, suite, output):
        calls.append(("builtins", suite, baseline))
        output.mkdir(parents=True, exist_ok=True)
        from context_testsuite.runner import DEFAULT_SUITES, SUITES
        selected = list(DEFAULT_SUITES) if suite == "default" else list(SUITES) if suite == "all" else [suite]
        (output / "run-report.json").write_text(json.dumps({"suites": [
            {"suite": name, "result": "pass"} for name in selected]}))
        return 0

    def documents(context, case, output, **kwargs):
        calls.append(("documents", case, kwargs["zip_results"] if "zip_results" in kwargs else False))
        output.mkdir(parents=True, exist_ok=True)
        (output / "regression-report.json").write_text(json.dumps({"totals": {
            "selected": 4, "changed": 1, "failed": 0}}))
        return 0

    monkeypatch.setattr(cli, "run_suites", builtins)
    monkeypatch.setattr(document_regressions, "run_regressions", documents)
    default_out = tmp_path / "default"
    assert cli.main(["run", "--context", str(engine), "--output", str(default_out)]) == 0
    assert calls == [("builtins", "default", None)]
    info = json.loads((default_out / "run-summary.json").read_text())
    assert len(info["sections"]) == 3
    assert info["baselines"] == {"builtins": "self_comparison", "documents": None}
    assert info["engines"]["candidate"]["version"] == "mtx-context | current version: 2026.10.29"

    calls.clear()
    all_out = tmp_path / "all"
    assert cli.main(["run", "--context", str(engine), "--baseline", str(engine),
                     "--suite", "all", "--output", str(all_out)]) == 0
    assert calls == [("builtins", "all", str(engine)), ("documents", "all", False)]
    info = json.loads((all_out / "run-summary.json").read_text())
    assert len(info["sections"]) == 6  # all five built-ins, plus documents
    assert info["baselines"] == {"builtins": "explicit_engine", "documents": "frozen_pdf"}
    assert (all_out / "run-report.json").is_file()
    assert (all_out / "documents" / "regression-report.json").is_file()


def test_run_refuses_previously_used_output(tmp_path):
    out = tmp_path / "older"
    out.mkdir()
    (out / "keep.txt").write_text("do not overwrite")
    res = subprocess.run(CLI + ["run", "--suite", "documents", "--context", "/bin/true",
                                "--output", str(out)], capture_output=True, text=True)
    assert res.returncode == 2
    assert (out / "keep.txt").read_text() == "do not overwrite"
