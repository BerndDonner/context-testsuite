"""Run named ConTeXt diagnostic documents without touching their source tree."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

import pymupdf

from .context_process import run_context_process
from .runner import CASE_ROOT, executable

DIAGNOSTIC_ROOT = CASE_ROOT / "math" / "diagnostics"
TRACE_MARKER = re.compile(r"CTS-(?:LB|GLUE|FACTOR)\b")
KV = re.compile(r"\b([a-z_]+)=(-?\d+|[A-Za-z][\w-]*)")


def available_diagnostics() -> list[str]:
    return sorted(path.stem for path in DIAGNOSTIC_ROOT.glob("*.tex"))


def parse_trace(stdout: str) -> dict:
    """Capture C-level evidence, retaining unknown fields and raw messages.

    Some ConTeXt Lua logging lacks a terminating newline.  A single output
    line can therefore contain both CTS-FACTOR and CTS-LB; split on markers.
    """
    events = []
    for line in stdout.splitlines():
        matches = list(TRACE_MARKER.finditer(line))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            raw = line[match.start():end].strip()
            kind = match.group()[4:].lower()
            subtype = ""
            if kind == "lb":
                subtype = "entry" if raw.startswith("CTS-LB entry") else (
                    "decision" if raw.startswith("CTS-LB decision") else "other")
            events.append({"kind": kind, "type": subtype, "fields": {
                key: int(value) if value.lstrip("-").isdigit() else value
                for key, value in KV.findall(raw)}, "raw": raw})
    entries = [event for event in events if event["kind"] == "lb" and event["type"] == "entry"]
    decisions = [event for event in events if event["kind"] == "lb" and event["type"] == "decision"]
    # Both number and order matter: a lone trailing entry cannot be paired
    # with a decision emitted by another breakpoint.
    state = "entry"
    complete = bool(entries)
    for event in events:
        if event["kind"] != "lb":
            continue
        if event["type"] != state:
            complete = False
            break
        state = "decision" if state == "entry" else "entry"
    complete = complete and state == "entry" and len(entries) == len(decisions)
    return {"schema_version": 1, "events": events,
            "summary": {"entries": len(entries), "decisions": len(decisions),
                        "complete_c_trace": complete}}


def diagnose(case: str, context_arg: str, output: Path, *, timeout: float = 120,
             observe_pages: bool = False, trace_mode: bool = False) -> tuple[dict, Path]:
    if case not in available_diagnostics():
        raise ValueError(f"Unknown diagnostic {case!r}; choose from: {', '.join(available_diagnostics())}")
    if observe_pages and case != "penalty-precedence":
        raise ValueError("--observe-pages is currently supported only for penalty-precedence")
    context = executable(context_arg)
    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    source = DIAGNOSTIC_ROOT / f"{case}.tex"
    target = output.expanduser().resolve()
    # Explicitly prohibit writing into the tracked diagnostic source folder.
    if target == DIAGNOSTIC_ROOT.resolve() or DIAGNOSTIC_ROOT.resolve() in target.parents:
        raise ValueError("Diagnostic output must not be inside the source diagnostics directory")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError(f"Output already exists and is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    work = target / "work"
    work.mkdir()
    shutil.copyfile(source, work / "source.tex")
    stdout_log = target / "stdout.log"
    result = run_context_process(context, "source.tex", work=work,
                                 home=target / "cache" / "home",
                                 tex_cache=target / "cache" / "tex",
                                 stdout_log=stdout_log, timeout=timeout,
                                 extra_args=("--mode=trace",) if trace_mode else ())
    content = stdout_log.read_text(encoding="utf-8", errors="replace")
    trace = parse_trace(content)
    (target / "trace.json").write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    actual_log = work / "source.log"
    if actual_log.is_file():
        shutil.copyfile(actual_log, target / "context.log")
    actual_pdf = work / "source.pdf"
    pdf_issue = None
    if result.exit_code == 0:
        try:
            if not actual_pdf.is_file():
                raise ValueError("ConTeXt did not produce a PDF")
            with pymupdf.open(actual_pdf) as pdf:
                if pdf.needs_pass or len(pdf) == 0:
                    raise ValueError("ConTeXt produced an unusable PDF")
            shutil.copyfile(actual_pdf, target / "output.pdf")
        except (ValueError, OSError, RuntimeError) as exc:
            pdf_issue = str(exc)
    page_observations = None
    if observe_pages and result.exit_code == 0 and pdf_issue is None and not result.timed_out:
        from .diagnostic_observations import observe_diagnostic_pdf
        try:
            page_observations = observe_diagnostic_pdf(case, actual_pdf)
            (target / "page-observations.json").write_text(
                json.dumps(page_observations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (ValueError, OSError, RuntimeError) as exc:
            pdf_issue = f"Cannot observe diagnostic pages: {exc}"
    if result.timed_out:
        status = "timeout"
    elif result.exit_code != 0 or pdf_issue:
        status = "compile_error"
    elif (trace["summary"]["complete_c_trace"] or
          (observe_pages and page_observations is not None and
           page_observations["summary"]["unclassifiable"] == 0)):
        status = "observed"
    else:
        status = "inconclusive"
    report = {"schema_version": 1,
              "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "case": case, "source": str(source), "context": context,
              "status": status, "exit_code": result.exit_code,
              "elapsed_seconds": round(result.elapsed_seconds, 3),
              "timed_out": result.timed_out, "pdf_issue": pdf_issue,
              "trace_summary": trace["summary"],
              "note": "Trace observation, not a claim about penalty semantics. Missing/incomplete CTS-LB trace is inconclusive."}
    if observe_pages:
        report["page_observations"] = (page_observations["summary"] if page_observations
                                       else {"status": "unavailable"})
        report["note"] = ("PDF observation is descriptive, not a penalty-precedence assertion. "
                          "C tracing is optional; if requested, see trace.json.")
    (target / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, target
