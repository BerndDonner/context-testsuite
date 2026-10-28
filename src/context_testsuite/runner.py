"""Run self-contained ConTeXt regression fixtures against supplied executables.

The suite owns its inputs and expectations; no external project is imported.
"""
from __future__ import annotations

from datetime import datetime, timezone
from .context_process import run_context_process
import json
import os
from pathlib import Path
import shutil



CASE_ROOT = Path(__file__).resolve().parent / "cases"
SUITES = {
    "math-basic": "12 math/noautobreak cases; protected breaks and change gate",
    "math-extended": "76 math penalties/glue cases with category-specific assertions",
    "math-adversarial": "Exploratory penalty/glue grid; explicit claims, hypotheses and repros (opt-in)",
    "units-smoke": "Units and MetaPost fixture: compilation only (NOT typography correctness)",
    "units-stress": "3 archived experimental units documents: compilation only (opt-in)",
}
DEFAULT_SUITES = ("math-basic", "math-extended", "units-smoke")


def available_suites(*, description: bool = False):
    return dict(SUITES) if description else list(SUITES)


def executable(value: str) -> str:
    found = shutil.which(value)
    if found is None:
        raise ValueError(f"ConTeXt executable not found: {value!r}")
    path = Path(found).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"ConTeXt executable is not executable: {path}")
    return str(path)


def _compile(context: str, source: Path, destination: Path) -> dict:
    """Copy all inputs to an independent workspace, then compile once."""
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination / source.name)
    if source.name == "units-regression.tex":
        shutil.copytree(source.parent / "include", destination / "include", dirs_exist_ok=True)
    log = destination / "build.log"
    status = run_context_process(context, source.name, work=destination,
                                 home=destination / "cache-home",
                                 tex_cache=destination / "tex-cache",
                                 stdout_log=log, timeout=600).exit_code
    pdf = destination / f"{source.stem}.pdf"
    if status == 0:
        try:
            import pymupdf
            if not pdf.is_file():
                raise ValueError("Output PDF was not created")
            with pymupdf.open(pdf) as document:
                if document.needs_pass or len(document) == 0:
                    raise ValueError("Output PDF is encrypted or has no pages")
        except (ValueError, RuntimeError, OSError) as exc:
            status = 1
            with log.open("a", encoding="utf-8") as stream:
                stream.write(f"PDF validation failed: {exc}\n")
    return {"source": str(source), "log": str(log), "pdf": str(pdf) if pdf.is_file() else None,
            "result": "pass_compile_only" if status == 0 else "fail", "exit_code": status}


def run_suites(context_arg: str, baseline_arg: str | None, suite: str, output: Path) -> int:
    context = executable(context_arg)
    baseline = executable(baseline_arg) if baseline_arg else context
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = list(DEFAULT_SUITES) if suite == "all" else [suite]
    if not all(name in SUITES for name in selected):
        raise ValueError(f"Unknown suite: {suite}")
    results = []
    for name in selected:
        dest = output / name
        dest.mkdir(parents=True, exist_ok=True)
        print(f"=== {name} ===", flush=True)
        if name == "math-adversarial":
            from .adversarial import run_adversarial
            row = run_adversarial(context, baseline if baseline_arg else None, dest)
            results.append({"suite": name, **row, "output": str(dest),
                            "reference_context": baseline if baseline_arg else None,
                            "candidate_context": context})
        elif name.startswith("math-"):
            from .math_suites import run_fixed
            row = run_fixed(name, context, baseline, dest)
            results.append({"suite": name, **row, "output": str(dest),
                            "reference_context": baseline, "candidate_context": context})
        else:
            if name == "units-smoke":
                sources = [CASE_ROOT / "units/units-regression.tex"]
            else:
                sources = sorted((CASE_ROOT.parent / "fixtures/units/archive").glob("*.tex"))
            steps = [_compile(context, source, dest / source.stem) for source in sources]
            failed = any(row["exit_code"] != 0 for row in steps)
            print(f"{'FAIL' if failed else 'PASS (compilation only)'}: {name}")
            results.append({"suite": name, "result": "fail" if failed else "pass_compile_only",
                            "steps": steps, "output": str(dest)})
    summary = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidate_context": context,
        "reference_context": baseline if baseline_arg else None,
        "reference_note": "If omitted, each math suite runs both sides with candidate; cross-version differences are not checked.",
        "suites": results,
    }
    (output / "run-report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Run report: {output / 'run-report.json'}")
    return 2 if any(item["result"] == "incomplete" for item in results) else int(any(item["result"] == "fail" for item in results))
