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
