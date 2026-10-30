"""Command-line interface to independent ConTeXt behavior and PDF tests."""
from __future__ import annotations

import argparse
import json
from shlex import quote
from datetime import datetime, timezone
from pathlib import Path
import sys

from .runner import available_suites, run_suites
from .review_archive import review_run


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-testsuite", description=__doc__,
        epilog=("Examples: context-testsuite list | "
                "context-testsuite run --context context --suite documents --case all --zip | "
                "context-testsuite pdf compare --reference old.pdf --candidate new.pdf --zip | "
                "Add --zip to any result-producing command for an offline review bundle."))
    actions = parser.add_subparsers(dest="command", required=True)

    run = actions.add_parser("run", help="Run built-in suites and/or frozen document regressions",
                             description="Run math/units cases or multipass document regressions. "
                             "Use --suite default for the three safe suites; "
                             "--suite all for EVERY suite including exploratory and document tests.")
    run.add_argument("--context", required=True, help="Candidate ConTeXt executable (path or PATH command)")
    run.add_argument("--baseline", help="Second ConTeXt engine for math comparisons; omitted = self-comparison. Document suites use frozen PDFs.")
    run.add_argument("--suite", choices=["default", "all", *available_suites()], default="default",
                     help="default = math-basic, math-extended, units-smoke; all = all suites "
                     "including exploratory suites and documents; documents = frozen PDF cases")
    run.add_argument("--case", default="all", help="Document case name or all (with --suite documents/all)")
    run.add_argument("--timeout", type=float, default=600, help="Document compilation timeout in seconds per case (default 600)")
    run.add_argument("--dpi", type=int, default=144, help="Document PDF comparison DPI (72..300)")
    run.add_argument("--pixel-threshold", type=int, default=16, help="Document RGB difference threshold (0..254)")
    run.add_argument("--output", type=Path, default=Path("results/run"), help="Root for logs, PDFs and reports")
    run.add_argument("--zip", action="store_true", help="Create a complete offline review ZIP beside --output, with PDFs, expectations, references, logs and reports")

    export = actions.add_parser("export", help="Share selected already-rendered math cases as a ZIP")
    export.add_argument("--from", dest="source_run", type=Path, required=True,
                        help="Existing run directory containing run-report.json")
    export.add_argument("--cases", required=True, help="Comma-separated case IDs, in export order")
    export.add_argument("--output", type=Path, required=True, help="New .zip file")
    export.add_argument("--include-baseline", action="store_true",
                        help="Include reference.pdf from a run with an explicit reference engine")

    diagnostics = actions.add_parser("diagnose", help="Run a standalone diagnostic in an isolated workspace")
    diagnostics.add_argument("--case", required=True, help="Named fixture; see context-testsuite list")
    diagnostics.add_argument("--context", required=True, help="Explicitly selected (optionally instrumented) ConTeXt executable")
    diagnostics.add_argument("--output", type=Path, required=True, help="New empty report directory")
    diagnostics.add_argument("--observe-pages", action="store_true",
                              help="Write page-observations.json from PDF (penalty-precedence only; no C trace needed)")
    diagnostics.add_argument("--trace-mode", action="store_true",
                              help="Enable the source's optional ConTeXt trace mode (requires instrumented engine for CTS-LB)")
    diagnostics.add_argument("--timeout", type=float, default=120, help="Wall-clock limit in seconds (default 120)")
    diagnostics.add_argument("--zip", action="store_true", help="Archive complete diagnosis for offline review")

    metamorphic = actions.add_parser("metamorphic", help="Evaluate explicit relations in saved adversarial results")
    metamorphic.add_argument("--from", dest="source_run", required=True, type=Path,
                             help="Run root, math-adversarial directory, or observations.json")
    metamorphic.add_argument("--output", required=True, type=Path, help="New separate report directory")
    metamorphic.add_argument("--zip", action="store_true", help="Archive report and original observation inputs")

    audit = actions.add_parser("audit-math", help="Replay saved Poppler observations without recompilation")
    audit.add_argument("--suite", required=True, choices=["math-basic", "math-extended", "math-adversarial"])
    audit.add_argument("--from", dest="source_run", required=True, type=Path, help="Old suite directory")
    audit.add_argument("--output", required=True, type=Path, help="New audit directory outside the old suite")
    audit.add_argument("--zip", action="store_true", help="Archive report and original PDF/observation inputs")

    suites = actions.add_parser("list", help="List test suites, document regressions and diagnostic fixtures")
    suites.add_argument("--json", action="store_true", help="Machine-readable suite list")

    pdf = actions.add_parser("pdf", help="Explore arbitrary PDF differences")
    pdf_actions = pdf.add_subparsers(dest="pdf_command", required=True)
    comp = pdf_actions.add_parser("compare", help="Compare two PDF paths without project dependencies")
    comp.add_argument("--reference", type=Path, required=True, help="Existing/reference PDF (may be missing)")
    comp.add_argument("--candidate", type=Path, required=True, help="New PDF")
    comp.add_argument("--output", type=Path, help="Report directory (default: results/pdf/<candidate-stem>)")
    comp.add_argument("--dpi", type=int, default=144, help="Raster DPI (72..300)")
    comp.add_argument("--pixel-threshold", type=int, default=16, help="RGB threshold (0..254)")
    comp.add_argument("--zip", action="store_true", help="Archive both PDFs (if present), reports and diff images")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.command == "list":
        catalog = available_suites(description=True)
        if args.json:
            print(json.dumps(catalog, indent=2, ensure_ascii=False))
        else:
            from .document_regressions import case_names
            from .diagnostics import available_diagnostics
            print("Test suites (run --suite):")
            print("  default           math-basic, math-extended, units-smoke (default)")
            print("  all               all suites, including exploratory and documents")
            for key, description in catalog.items():
                print(f"  {key:17} {description}")
            print("\nDocument cases (run --suite documents --case):")
            try:
                for name in case_names():
                    print(f"  {name}")
            except ValueError as exc:
                print(f"  unavailable: {exc}")
            print("\nDiagnostics (diagnose --case):")
            for name in available_diagnostics():
                print(f"  {name}")
        return 0
    if args.command == "metamorphic":
        try:
            from .metamorphic import run
            with review_run(args.zip, args.output, kind="metamorphic",
                            inputs={"observations": args.source_run},
                            parameters={"command": "metamorphic"}):
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
            with review_run(args.zip, args.output, kind="audit-math",
                            inputs={"source-run": args.source_run},
                            parameters={"suite": args.suite}):
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
            from .diagnostics import DIAGNOSTIC_ROOT
            with review_run(args.zip, args.output, kind="diagnose",
                            inputs={"fixture": DIAGNOSTIC_ROOT / f"{args.case}.tex"},
                            engines={"candidate": args.context},
                            parameters={"case": args.case, "observe_pages": args.observe_pages,
                                        "trace_mode": args.trace_mode, "timeout": args.timeout}):
                report, folder = diagnose(args.case, args.context, args.output, timeout=args.timeout,
                                          observe_pages=args.observe_pages, trace_mode=args.trace_mode)
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
            from .runner import CASE_ROOT, DEFAULT_SUITES, SUITES, DOCUMENT_SUITE, executable
            from .document_regressions import (REGRESSIONS_ROOT, case_names, run_regressions,
                                               _engine_version, _testsuite_revision)
            # Validate arguments before running anything or touching an output tree.
            docs = args.suite in (DOCUMENT_SUITE, "all")
            builtins = (list(DEFAULT_SUITES) if args.suite == "default" else
                        list(SUITES) if args.suite == "all" else
                        [] if docs else [args.suite])
            if args.case != "all" and not docs:
                raise ValueError("--case is only valid with --suite documents or --suite all")
            if args.suite == DOCUMENT_SUITE and args.baseline:
                raise ValueError("--baseline is not used by documents: references are frozen PDFs")
            if docs:
                fixtures = REGRESSIONS_ROOT.resolve()
                target = args.output.expanduser().resolve()
                if target == fixtures or target.is_relative_to(fixtures) or fixtures.is_relative_to(target):
                    raise ValueError(f"Output must be separate from tests/regressions/: {target}")
                if args.case != "all" and args.case not in case_names():
                    raise ValueError(f"Unknown document case: {args.case!r}")
            if docs and args.timeout <= 0:
                raise ValueError("--timeout must be positive")
            if docs and not 72 <= args.dpi <= 300:
                raise ValueError("--dpi must be between 72 and 300")
            if docs and not 0 <= args.pixel_threshold <= 254:
                raise ValueError("--pixel-threshold must be between 0 and 254")
            if args.output.is_symlink():
                raise ValueError(f"Refusing symlinked output directory: {args.output}")
            output = args.output.expanduser().resolve()
            if output.exists() and (not output.is_dir() or any(output.iterdir())):
                raise ValueError(f"Output already exists and is not empty: {output}; choose a new --output")
            context = executable(args.context)
            baseline = executable(args.baseline) if args.baseline else None
            if builtins and baseline is None:
                print("Note: no --baseline supplied; math suites use candidate on both sides. "
                      "Assertions still run, but this is NOT a cross-version comparison.", flush=True)
            sources = {}
            for name in builtins:
                if name.startswith("math-"):
                    sources[name] = CASE_ROOT / "math" / name.removeprefix("math-")
                elif name == "units-smoke":
                    sources[name] = CASE_ROOT / "units"
                elif name == "units-stress":
                    sources[name] = CASE_ROOT.parent / "fixtures" / "units" / "archive"
            if docs:
                # Include the original reference PDFs and local source/assets in
                # the common archive, not just compiled candidates.
                sources["document-regressions"] = (REGRESSIONS_ROOT if args.case == "all"
                                                    else REGRESSIONS_ROOT / args.case)
            with review_run(args.zip, output, kind="run", inputs=sources,
                            engines={"candidate": context, "baseline": baseline},
                            parameters={"suite": args.suite, "case": args.case,
                                        "baseline_supplied": baseline is not None,
                                        "timeout": args.timeout if docs else None,
                                        "dpi": args.dpi if docs else None,
                                        "pixel_threshold": args.pixel_threshold if docs else None}):
                output.mkdir(parents=True, exist_ok=True)
                sections = []
                exit_codes = []
                if builtins:
                    # One built-in runner invocation produces one run-report.json.
                    selection = ("default" if args.suite == "default" else
                                 "all" if args.suite == "all" else builtins[0])
                    status = run_suites(context, baseline, selection, output)
                    exit_codes.append(status)
                    suite_report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
                    sections.extend({"suite": r["suite"], "kind": "built-in",
                                     "result": r["result"], "report": "run-report.json"}
                                    for r in suite_report["suites"])
                if docs:
                    # Keep the multipass document runner and frozen-PDF semantics.
                    doc_root = output if not builtins else output / "documents"
                    status = run_regressions(context, args.case, doc_root,
                                             timeout=args.timeout, dpi=args.dpi,
                                             pixel_threshold=args.pixel_threshold)
                    exit_codes.append(status)
                    document_report = json.loads((doc_root / "regression-report.json").read_text(encoding="utf-8"))
                    sections.append({"suite": "documents", "kind": "frozen-pdf",
                                     "result": "fail" if status else "pass",
                                     "report": ("documents/" if builtins else "") + "regression-report.json",
                                     "selected": document_report["totals"]["selected"],
                                     "changed": document_report["totals"]["changed"],
                                     "failed": document_report["totals"]["failed"]})
                # Small common envelope; existing detailed report schemas remain untouched.
                summary = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "command": "run", "selection": {"suite": args.suite, "case": args.case},
                           "testsuite_revision": _testsuite_revision(),
                           "engines": {"candidate": {"path": context, "version": _engine_version(context)},
                                       "baseline": ({"path": baseline, "version": _engine_version(baseline)}
                                                    if baseline else None)},
                           "baselines": {"builtins": ("explicit_engine" if baseline else "self_comparison")
                                                     if builtins else None,
                                         "documents": "frozen_pdf" if docs else None},
                           "notes": {"builtins": ("No cross-version comparison; math candidate is compared to itself."
                                                 if builtins and baseline is None else
                                                 "Math suites compare two engines." if builtins else None),
                                     "documents": "Frozen reference PDFs; ordinary multipass ConTeXt (no --once)." if docs else None},
                           "sections": sections,
                           "status": "fail" if any(exit_codes) else "pass"}
                (output / "run-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"Unified run summary: {output / 'run-summary.json'}", flush=True)
                return max(exit_codes, default=0)
        except (ValueError, OSError, RuntimeError) as exc:
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
            with review_run(args.zip, folder, kind="pdf-compare",
                            inputs={"reference": args.reference, "candidate": args.candidate},
                            parameters={"dpi": args.dpi, "pixel_threshold": args.pixel_threshold}):
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
        print(f"\nTo see the detailed side-by-side report:\n  xdg-open {quote(str((folder / 'report.html').resolve()))}")
        return 0
    return 2
