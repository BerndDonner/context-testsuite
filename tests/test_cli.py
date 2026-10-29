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
    assert {"math-basic", "math-extended", "math-adversarial", "units-smoke", "units-stress"} == set(catalog)


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
