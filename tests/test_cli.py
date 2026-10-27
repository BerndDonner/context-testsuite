"""Smoke-tests of public command-line interfaces, without ConTeXt or Nix."""
from pathlib import Path
import json
import os
import subprocess
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
CLI = [str(ROOT / "bin/context-testsuite")]


def _pdf(file, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), text)
    doc.save(file)
    doc.close()


def test_list_command():
    res = subprocess.run(CLI + ["list", "--json"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    catalog = json.loads(res.stdout)
    assert {"math-basic", "math-extended", "units-smoke", "units-stress"} == set(catalog)


def test_pdf_direct_paths(tmp_path):
    old = tmp_path / "previous.pdf"
    new = tmp_path / "current.pdf"
    _pdf(old, "before")
    _pdf(new, "after")
    out = tmp_path / "report"
    res = subprocess.run(CLI + ["pdf", "compare", "--reference", str(old),
                                    "--candidate", str(new), "--output", str(out),
                                    "--dpi", "72"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "changed"
    assert report["summary"]["pages_text_changed"] == 1
    assert (out / "report.html").is_file()


def test_pdf_missing_candidate_is_error(tmp_path):
    res = subprocess.run(CLI + ["pdf", "compare", "--reference", str(tmp_path / "old.pdf"),
                                    "--candidate", str(tmp_path / "absent.pdf")],
                         capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 2
    assert "Build-PDF" in res.stderr


def test_units_smoke_runner_with_stub_executable(tmp_path):
    # A fake compiler checks only independent source copying & runner/report wiring.
    # It does not validate ConTeXt typographic output.
    fake = tmp_path / "fake-context"
    fake.write_text("#!/usr/bin/env python3\n"
                    "from pathlib import Path\n"
                    "import sys\n"
                    "p = Path(sys.argv[-1])\n"
                    "assert (Path('include/conventions/units.tex')).is_file()\n"
                    "assert (Path('include/workarounds/lmtx-units-2026.tex')).is_file()\n"
                    "import fitz\n"
                    "doc=fitz.open()\n"
                    "doc.new_page().insert_text((50,100), 'smoke test')\n"
                    "doc.save(p.stem + '.pdf')\n"
                    "doc.close()\n")
    fake.chmod(0o755)
    out = tmp_path / "run-output"
    res = subprocess.run(CLI + ["run", "--context", str(fake), "--suite", "units-smoke",
                                    "--output", str(out)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    summary = json.loads((out / "run-report.json").read_text())
    assert summary["suites"][0]["result"] == "pass_compile_only"
    assert (out / "units-smoke/units-regression/include/conventions/units.tex").is_file()


def test_launcher_uses_explicit_python_even_if_path_contains_wrong_python(tmp_path):
    """Regression: pytest's Python may differ from `python3` on PATH."""
    wrong_python = tmp_path / "python3"
    wrong_python.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    wrong_python.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}{os.pathsep}{env['PATH']}"
    env["CONTEXT_TESTSUITE_PYTHON"] = sys.executable
    result = subprocess.run(CLI + ["list", "--json"],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "math-extended" in json.loads(result.stdout)
