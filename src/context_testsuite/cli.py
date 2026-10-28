"""Command-line interface to independent ConTeXt behavior and PDF tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from .runner import available_suites, run_suites


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-testsuite", description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)

    run = actions.add_parser("run", help="Run built-in ConTeXt regression cases")
    run.add_argument("--context", required=True, help="Candidate ConTeXt executable (path or PATH command)")
    run.add_argument("--baseline", help="Optional upstream/reference ConTeXt executable")
    run.add_argument("--suite", choices=["all", *available_suites()], default="all")
    run.add_argument("--output", type=Path, default=Path("results/run"), help="Root for logs, PDFs and reports")

    export = actions.add_parser("export", help="Share selected already-rendered math cases as a ZIP")
    export.add_argument("--from", dest="source_run", type=Path, required=True,
                        help="Existing run directory containing run-report.json")
    export.add_argument("--cases", required=True, help="Comma-separated case IDs, in export order")
    export.add_argument("--output", type=Path, required=True, help="New .zip file")
    export.add_argument("--include-baseline", action="store_true",
                        help="Include reference.pdf from a run with an explicit reference engine")

    diagnostics = actions.add_parser("diagnose", help="Run a standalone diagnostic in an isolated workspace")
    diagnostics.add_argument("--case", required=True, help="Named fixture from cases/math/diagnostics")
    diagnostics.add_argument("--context", required=True, help="Explicitly selected (optionally instrumented) ConTeXt executable")
    diagnostics.add_argument("--output", type=Path, required=True, help="New empty report directory")
    diagnostics.add_argument("--timeout", type=float, default=120, help="Wall-clock limit in seconds (default 120)")

    metamorphic = actions.add_parser("metamorphic", help="Evaluate explicit relations in saved adversarial results")
    metamorphic.add_argument("--from", dest="source_run", required=True, type=Path,
                             help="Run root, math-adversarial directory, or observations.json")
    metamorphic.add_argument("--output", required=True, type=Path, help="New separate report directory")

    audit = actions.add_parser("audit-math", help="Replay saved Poppler observations without recompilation")
    audit.add_argument("--suite", required=True, choices=["math-basic", "math-extended", "math-adversarial"])
    audit.add_argument("--from", dest="source_run", required=True, type=Path, help="Old suite directory")
    audit.add_argument("--output", required=True, type=Path, help="New audit directory outside the old suite")

    suites = actions.add_parser("list", help="Describe the built-in test suites")
    suites.add_argument("--json", action="store_true", help="Machine-readable suite list")

    pdf = actions.add_parser("pdf", help="Explore arbitrary PDF differences")
    pdf_actions = pdf.add_subparsers(dest="pdf_command", required=True)
    comp = pdf_actions.add_parser("compare", help="Compare two PDF paths without project dependencies")
    comp.add_argument("--reference", type=Path, required=True, help="Existing/reference PDF (may be missing)")
    comp.add_argument("--candidate", type=Path, required=True, help="New PDF")
    comp.add_argument("--output", type=Path, help="Report directory (default: results/pdf/<candidate-stem>)")
    comp.add_argument("--dpi", type=int, default=144, help="Raster DPI (72..300)")
    comp.add_argument("--pixel-threshold", type=int, default=16, help="RGB threshold (0..254)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.command == "list":
        catalog = available_suites(description=True)
        if args.json:
            print(json.dumps(catalog, indent=2, ensure_ascii=False))
        else:
            for key, description in catalog.items():
                print(f"{key:17} {description}")
        return 0
    if args.command == "metamorphic":
        try:
            from .metamorphic import run
            report = run(args.source_run, args.output)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Metamorphic: {report['result']} ({report['counts']})")
        print(f"Report: {args.output / 'metamorphic.md'}")
        return report['exit_code']
    if args.command == "audit-math":
        try:
            from .observer_audit import audit
            report = audit(args.suite, args.source_run, args.output)
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Observer parity: {report['counts']}")
        print(f"Report: {args.output / 'observer-audit.json'}")
        return report['exit_code']
    if args.command == "diagnose":
        try:
            from .diagnostics import diagnose
            report, folder = diagnose(args.case, args.context, args.output, timeout=args.timeout)
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Diagnosis: {report['status']} (trace entries={report['trace_summary']['entries']}, "
              f"decisions={report['trace_summary']['decisions']})")
        print(f"Report: {folder / 'report.json'}")
        return 0 if report["status"] == "observed" else 2
    if args.command == "export":
        try:
            from .export import export_cases
            case_ids = [case.strip() for case in args.cases.split(",")]
            if any(not case for case in case_ids):
                raise ValueError("--cases must be a comma-separated list without empty IDs")
            export_cases(args.source_run, case_ids, args.output,
                         include_baseline=args.include_baseline)
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Exported {len(case_ids)} cases to {args.output}")
        return 0
    if args.command == "run":
        try:
            return run_suites(args.context, args.baseline, args.suite, args.output)
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    if args.command == "pdf" and args.pdf_command == "compare":
        try:
            if not 72 <= args.dpi <= 300:
                raise ValueError("--dpi must be between 72 and 300")
            if not 0 <= args.pixel_threshold <= 254:
                raise ValueError("--pixel-threshold must be between 0 and 254")
            folder = args.output or Path("results/pdf") / args.candidate.stem
            from .pdf import compare_files
            data, folder = compare_files(args.reference, args.candidate, folder, args.dpi, args.pixel_threshold)
        except (ValueError, OSError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        s = data["summary"]
        print(f"Status: {data['status']} (difference is not automatically a regression)")
        print(f"Pages: {s['baseline_pages']} -> {s['build_pages']}")
        print(f"Changed: text={s['pages_text_changed']}, visual={s['pages_visual_changed']}, geometry={s['pages_geometry_changed']}")
        print(f"HTML: {folder / 'report.html'}")
        print(f"JSON: {folder / 'report.json'}")
        return 0
    return 2
