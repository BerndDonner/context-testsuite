"""Run frozen document/PDF regressions from a source checkout.

Each immediate directory in tests/regressions is a case: exactly one root .tex,
reference.pdf and arbitrary local dependencies. There is no manifest and no
reference-engine invocation. A changed PDF is evidence, not an automatic fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .context_process import run_context_process
from .pdf import compare_files
from .runner import executable
from .regression_archive import write_regression_archive


REGRESSIONS_ROOT = Path(__file__).resolve().parents[2] / "tests" / "regressions"


@dataclass(frozen=True)
class DocumentCase:
    name: str
    folder: Path
    source: Path
    reference: Path


def case_names(root: Path = REGRESSIONS_ROOT) -> list[str]:
    """Discover every direct subdirectory; never silently skip broken cases."""
    if not root.is_dir():
        raise ValueError(f"Document regression directory not found: {root} (run from a source checkout)")
    names = sorted(path.name for path in root.iterdir() if path.is_dir())
    if not names:
        raise ValueError(f"No document regression cases in {root}")
    return names


def _load_case(root: Path, name: str) -> DocumentCase:
    folder = root / name
    if folder.is_symlink():
        raise ValueError(f"Case directory must not be a symlink: {folder}")
    sources = sorted(folder.glob("*.tex"))
    if len(sources) != 1:
        raise ValueError(f"{name}: expected exactly one root-level .tex file, found {len(sources)}")
    reference = folder / "reference.pdf"
    if not reference.is_file():
        raise ValueError(f"{name}: missing frozen reference.pdf")
    # Do not copy external symlink targets into an ostensibly self-contained fixture.
    for path, directories, files in os.walk(folder, followlinks=False):
        for entry in [*directories, *files]:
            item = Path(path) / entry
            if item.is_symlink():
                raise ValueError(f"{name}: fixture contains symlink: {item}")
    return DocumentCase(name, folder, sources[0], reference)


def _safe_output(root: Path, output: Path) -> Path:
    source_root = root.resolve()
    target = output.expanduser().resolve()
    if target == source_root or target.is_relative_to(source_root) or source_root.is_relative_to(target):
        raise ValueError(f"Output must be separate from tests/regressions/: {target}")
    return target


def _copy_fixture(folder: Path, work: Path) -> None:
    """No baseline/README in the compiler's directory; no stale aux files."""
    if work.is_symlink():
        raise ValueError(f"Refusing to replace symlinked work directory: {work}")
    if work.exists():
        if not work.is_dir():
            raise ValueError(f"Work path exists but is not a directory: {work}")
        shutil.rmtree(work)
    shutil.copytree(folder, work, ignore=lambda parent, names:
                    {name for name in names if Path(parent) == folder and name in ("reference.pdf", "README.md")})


def _run_case(case: DocumentCase, context: str, destination: Path,
              *, timeout: float, dpi: int, pixel_threshold: int) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    work = destination / "work"
    _copy_fixture(case.folder, work)
    log = destination / "context-build.log"
    (destination / "engine-path.txt").write_text(context + "\n", encoding="utf-8")
    print(f"\n[{case.name}] Compiling candidate with selected engine...")
    print(f"  engine:    {context}\n  source:    {case.source}\n"
          f"  reference: {case.reference}\n  output:    {destination}")
    result = run_context_process(context, case.source.name, work=work,
                                 home=destination / "home", tex_cache=destination / "cache",
                                 stdout_log=log, timeout=timeout, once=False)
    candidate = work / f"{case.source.stem}.pdf"
    item = {"case": case.name, "source": str(case.source),
            "reference": str(case.reference), "engine": context,
            "candidate": str(candidate), "log": str(log),
            "exit_code": result.exit_code, "timed_out": result.timed_out,
            "elapsed_seconds": round(result.elapsed_seconds, 3)}
    if result.exit_code != 0:
        item.update(status="compile_error", error=("ConTeXt timed out" if result.timed_out
                                                   else f"ConTeXt exited with code {result.exit_code}"))
    elif not candidate.is_file() or candidate.stat().st_size == 0:
        item.update(status="compile_error", error=f"ConTeXt did not produce PDF: {candidate}")
    else:
        try:
            data, comparison = compare_files(case.reference, candidate, destination / "comparison",
                                             dpi, pixel_threshold, label=case.name)
            item.update(status=data["status"], summary=data["summary"],
                        report_html=str(comparison / "report.html"),
                        report_json=str(comparison / "report.json"))
            print(f"Status: {data['status']} (difference is not automatically a regression)")
            summary = data["summary"]
            print(f"Pages: {summary['baseline_pages']} -> {summary['build_pages']}")
            print(f"Changed: text={summary['pages_text_changed']}, "
                  f"visual={summary['pages_visual_changed']}, "
                  f"geometry={summary['pages_geometry_changed']}")
            print(f"HTML: {item['report_html']}\nJSON: {item['report_json']}")
            print(f"\nTo see the detailed side-by-side report:\n  xdg-open {item['report_html']}")
        except (ValueError, RuntimeError, OSError) as exc:
            item.update(status="comparison_error", error=str(exc))
    if item["status"] in ("compile_error", "comparison_error"):
        print(f"ERROR [{case.name}]: {item['error']} (see {log})")
    return item


def run_regressions(context_arg: str, case_name: str, output: Path, *,
                    timeout: float = 600, dpi: int = 144, pixel_threshold: int = 16,
                    zip_results: bool = False, root: Path = REGRESSIONS_ROOT) -> int:
    """Return 2 on configuration, compilation or comparison errors; not on visual changes."""
    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    if not 72 <= dpi <= 300:
        raise ValueError("--dpi must be between 72 and 300")
    if not 0 <= pixel_threshold <= 254:
        raise ValueError("--pixel-threshold must be between 0 and 254")
    names = case_names(root)
    if case_name != "all" and case_name not in names:
        raise ValueError(f"Unknown regression case {case_name!r}; available: {', '.join(names)}")
    selected = names if case_name == "all" else [case_name]
    if output.is_symlink():
        raise ValueError(f"Refusing symlinked output directory: {output}")
    output = _safe_output(root, output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output already exists and is not empty: {output}; choose a new --output")
    archive = output.with_name(output.name + ".zip") if zip_results else None
    if archive is not None and archive.exists():
        raise ValueError(f"Review ZIP already exists: {archive}; choose a new --output")
    context = executable(context_arg)
    # Validate all selected fixtures before launching anything. Incomplete cases fail visibly.
    cases = [_load_case(root, name) for name in selected]
    output.mkdir(parents=True, exist_ok=True)
    engine_version = _engine_version(context)
    testsuite_revision = _testsuite_revision()
    results = [_run_case(case, context, output / case.name, timeout=timeout, dpi=dpi,
                         pixel_threshold=pixel_threshold) for case in cases]
    failed = sum(item["status"] in ("compile_error", "comparison_error") for item in results)
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "engine": context, "engine_version": engine_version,
              "testsuite_revision": testsuite_revision,
              "invocation": {"once": False, "case": case_name, "timeout_seconds": timeout,
                             "dpi": dpi, "pixel_threshold": pixel_threshold},
              "cases": results,
              "totals": {"selected": len(results), "changed": sum(r["status"] == "changed" for r in results),
                         "identical": sum(r["status"] == "identical" for r in results), "failed": failed}}
    path = output / "regression-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDocument regressions: {len(results)} cases, {failed} failed, "
          f"{report['totals']['changed']} changed, {report['totals']['identical']} identical")
    print(f"Aggregate report: {path}")
    if archive is not None:
        write_regression_archive(output, cases, archive)
        print(f"Review ZIP: {archive}")
    return 2 if failed else 0


def _engine_version(context: str) -> str | None:
    """Record --version for review; failure must not prevent regression runs."""
    try:
        with tempfile.TemporaryDirectory(prefix="cts-version-") as tmp:
            result = subprocess.run([context, "--version"], cwd=tmp,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace", timeout=10, check=False)
            if result.returncode == 0:
                return result.stdout.strip()[:8192] or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _testsuite_revision() -> str | None:
    """Best-effort source revision for archived checkouts and installed wheels."""
    repo = Path(__file__).resolve().parents[2]
    try:
        result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=5, check=False)
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
