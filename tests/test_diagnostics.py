"""Test diagnostic orchestration without a local ConTeXt installation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pymupdf
import pytest

from context_testsuite.diagnostics import diagnose, parse_trace


def _engine(tmp_path: Path, *, mode: str) -> Path:
    reference = tmp_path / "fixture.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((60, 60), "diagnostic fixture")
    doc.save(reference)
    doc.close()
    # Use a fake executable that behaves like a ConTeXt wrapper; shell is
    # enough and avoids relying on system Nix/ConTeXt during CI.
    path = tmp_path / "fake-context"
    body = {
        "trace": (f"cp '{reference}' source.pdf\n"
                  "echo 'CTS-GLUE created options=0 penalty=10000'\n"
                  "echo 'CTS-FACTOR case=P08 factor=67000 glue_options=0CTS-LB entry location=1 math=500 factor=67000 haspenalty=0 gluepenalty=10000'\n"
                  "echo 'CTS-LB decision=glue-overrides math=500 factor=67000'\n"
                  "echo 'ConTeXt log content' > source.log\n"),
        "untraced": f"cp '{reference}' source.pdf\necho 'ordinary run'\n",
        "failure": "echo 'engine failed'\nexit 7\n",
        "timeout": "sleep 5\n",
        "no-pdf": "echo 'CTS-LB entry location=1'\necho 'CTS-LB decision=scaled-result'\n",
    }[mode]
    path.write_text("#!/bin/sh\nset -eu\ntest -f source.tex\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_trace_parser_handles_concatenated_lua_and_c_messages():
    result = parse_trace("CTS-FACTOR case=P08 factor=67000CTS-LB entry math=500 factor=67000\n"
                         "CTS-LB decision=glue-overrides math=500\n")
    assert result["summary"]["complete_c_trace"] is True
    assert [(event["kind"], event["type"]) for event in result["events"]] == [
        ("factor", ""), ("lb", "entry"), ("lb", "decision")]
    assert result["events"][1]["fields"]["factor"] == 67000


def test_diagnostic_keeps_inputs_and_traces_in_isolated_workspace(tmp_path):
    output = tmp_path / "results" / "example"
    result, folder = diagnose("glue-option-entry", str(_engine(tmp_path, mode="trace")), output)
    assert result["status"] == "observed"
    assert folder == output
    assert (output / "work/source.tex").is_file()
    assert (output / "context.log").read_text().strip() == "ConTeXt log content"
    assert (output / "output.pdf").is_file()
    assert (output / "stdout.log").is_file()
    trace = json.loads((output / "trace.json").read_text())
    assert trace["summary"] == {"entries": 1, "decisions": 1, "complete_c_trace": True}
    assert trace["events"][2]["fields"]["haspenalty"] == 0
    report = json.loads((output / "report.json").read_text())
    assert report["case"] == "glue-option-entry"
    assert (output / "cache/home").is_dir()
    assert (output / "cache/tex").is_dir()


@pytest.mark.parametrize("mode,status", [("untraced", "inconclusive"),
                                         ("failure", "compile_error"),
                                         ("no-pdf", "compile_error")])
def test_missing_trace_and_failed_builds_are_not_success(tmp_path, mode, status):
    result, output = diagnose("glue-option-entry", str(_engine(tmp_path, mode=mode)),
                              tmp_path / "out")
    assert result["status"] == status
    assert (output / "report.json").is_file()
    assert (output / "trace.json").is_file()


def test_timeout_is_bounded_and_reported(tmp_path):
    result, output = diagnose("glue-option-entry", str(_engine(tmp_path, mode="timeout")),
                              tmp_path / "out", timeout=0.1)
    assert result["status"] == "timeout" and result["exit_code"] == 124
    assert (output / "report.json").is_file()


def test_source_tree_is_protected_and_existing_outputs_are_not_overwritten(tmp_path):
    fake = str(_engine(tmp_path, mode="trace"))
    output = tmp_path / "out"
    diagnose("glue-option-entry", fake, output)
    with pytest.raises(ValueError, match="not empty"):
        diagnose("glue-option-entry", fake, output)
    with pytest.raises(ValueError, match="Unknown diagnostic"):
        diagnose("does-not-exist", fake, tmp_path / "other")
    with pytest.raises(ValueError, match="inside the source diagnostics directory"):
        from context_testsuite.diagnostics import DIAGNOSTIC_ROOT
        diagnose("glue-option-entry", fake, DIAGNOSTIC_ROOT / "generated")


def test_cli_diagnose_outputs_status_and_return_code(tmp_path):
    root = Path(__file__).resolve().parents[1]
    executable = root / "bin" / "context-testsuite"
    traced = tmp_path / "traced"
    res = subprocess.run([str(executable), "diagnose", "--case", "glue-option-entry",
                          "--context", str(_engine(tmp_path, mode="trace")),
                          "--output", str(traced)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr + res.stdout
    assert "Diagnosis: observed" in res.stdout
    plain = tmp_path / "plain"
    res = subprocess.run([str(executable), "diagnose", "--case", "noautobreak-natural",
                          "--context", str(_engine(tmp_path, mode="untraced")),
                          "--output", str(plain)], capture_output=True, text=True)
    assert res.returncode == 2 and "inconclusive" in res.stdout


def test_unpaired_or_out_of_order_c_trace_is_inconclusive():
    for sample in (
        "CTS-LB entry math=500\n",
        "CTS-LB decision=scaled-result\nCTS-LB entry math=500\n",
        "CTS-LB entry math=500\nCTS-LB entry math=600\nCTS-LB decision=scaled-result\nCTS-LB decision=scaled-result\n",
    ):
        assert parse_trace(sample)["summary"]["complete_c_trace"] is False
