"""Export selected, already rendered math cases for people without the test runner.

Inputs are the actual .tex and .pdf files in a completed run directory.
The exporter never reruns ConTeXt or reconstructs sources from current fixtures.
It fails closed on missing or ambiguous source-to-page mappings.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import zipfile

import pymupdf


# The three math suites currently produce one page per \subject case.
MATH_SUITES = ("math-basic", "math-extended", "math-adversarial")
SUBJECT = re.compile(r"\\subject\{([A-Z][0-9]{2,4})(?=[\s}])")
START = re.compile(r"(?m)^\\starttext\s*$")
END = re.compile(r"(?m)^\\stoptext\s*$")
BREAK = re.compile(r"(?m)^\\page[ \t]*(?:\r?\n|$)")


@dataclass(frozen=True)
class PageSource:
    suite: str
    case_id: str
    header: str
    body: str
    pdf: Path
    page_number: int
    source: Path


def parse_tex(source: str) -> tuple[str, list[tuple[str, str]]]:
    """Read exact per-page inputs from the saved ConTeXt source.

    Only the frozen math fixture format is accepted: one case heading per
    page, explicit page separators, and one start/stop document.
    """
    starts, ends = list(START.finditer(source)), list(END.finditer(source))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
        raise ValueError("Unsupported TeX source: expected one \\starttext and \\stoptext")
    if source[ends[0].end():].strip():
        raise ValueError("Unsupported TeX source: content after \\stoptext")
    header = source[:starts[0].end()] + "\n"
    content = source[starts[0].end():ends[0].start()]
    blocks = BREAK.split(content)
    cases = []
    for block in blocks:
        ids = SUBJECT.findall(block)
        if len(ids) != 1:
            raise ValueError(f"Expected exactly one case heading per source page, found {ids}")
        cases.append((ids[0], block))
    if len({case_id for case_id, _ in cases}) != len(cases):
        raise ValueError("Duplicate case ID in saved TeX source")
    return header, cases


def _page_contains_id(page: pymupdf.Page, case_id: str, all_ids: set[str]) -> bool:
    text = page.get_text("text", sort=True)
    found = {name for name in all_ids if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text)}
    return found == {case_id}


def _pdf_mapping(suite: str, tex: Path, pdf: Path) -> dict[str, PageSource]:
    header, cases = parse_tex(tex.read_text(encoding="utf-8"))
    result = {}
    with pymupdf.open(pdf) as document:
        if document.needs_pass or len(document) != len(cases):
            raise ValueError(f"Page count mismatch/encrypted PDF: {pdf} (TeX={len(cases)}, PDF={len(document)})")
        names = {case_id for case_id, _ in cases}
        for number, (case_id, body) in enumerate(cases):
            if not _page_contains_id(document[number], case_id, names):
                raise ValueError(f"PDF page {number + 1} does not unambiguously match {case_id}: {pdf}")
            result[case_id] = PageSource(suite, case_id, header, body, pdf, number, tex)
    return result


def _pdfs(suite_dir: Path, suite: str, role: str) -> list[Path]:
    if suite == "math-adversarial":
        path_name = "candidate" if role == "candidate" else "reference"
        # Include fallback bisected shards from partial runs. Duplicates are
        # rejected below instead of silently choosing potentially stale PDFs.
        return sorted(suite_dir.glob(f"shard-*/{path_name}/**/cases.pdf"))
    path_name = "after" if role == "candidate" else "before"
    file = suite_dir / path_name / "cases.pdf"
    return [file] if file.is_file() else []


def _index(suite_dir: Path, suite: str, role: str) -> dict[str, PageSource]:
    result = {}
    for pdf in _pdfs(suite_dir, suite, role):
        tex = pdf.with_suffix(".tex")
        if not tex.is_file():
            raise ValueError(f"PDF without its original TeX source: {pdf}")
        for case_id, source in _pdf_mapping(suite, tex, pdf).items():
            if case_id in result:
                raise ValueError(f"Ambiguous duplicate PDF page for {case_id} ({role})")
            result[case_id] = source
    return result


def _pdf_bytes(pages: list[PageSource]) -> bytes:
    result = pymupdf.open()
    try:
        for page in pages:
            with pymupdf.open(page.pdf) as source:
                result.insert_pdf(source, from_page=page.page_number, to_page=page.page_number)
        return result.tobytes(garbage=4, deflate=True)
    finally:
        result.close()


def export_cases(run_root: Path, case_ids: list[str], output: Path, *, include_baseline: bool = False) -> None:
    """Package one math suite's selected cases without running ConTeXt.

    The run-report is needed to prevent confusing a same-engine control run
    with an actual unpatched baseline. PDF pages are verified against the
    original page headings before they can be exported.
    """
    root = run_root.expanduser().resolve()
    output = output.expanduser().resolve()
    report_file = root / "run-report.json"
    if not report_file.is_file():
        raise ValueError(f"Missing run-report.json: {root} (pass the run root to --from)")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        raise ValueError("Malformed run-report.json")
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("--cases must contain unique case IDs")
    if output.suffix.lower() != ".zip":
        raise ValueError("--output must be a .zip file")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    available = {row.get("suite") for row in report["suites"] if isinstance(row, dict)}
    found = {}
    for suite in MATH_SUITES:
        if suite not in available:
            continue
        for case_id, page in _index(root / suite, suite, "candidate").items():
            if case_id in found:
                raise ValueError(f"Ambiguous case ID across suites: {case_id}")
            found[case_id] = page
    missing = [case_id for case_id in case_ids if case_id not in found]
    if missing:
        raise ValueError(f"Cases not found in complete PDF/TeX pairs: {', '.join(missing)}")
    pages = [found[case_id] for case_id in case_ids]
    suite = pages[0].suite
    if any(page.suite != suite for page in pages):
        raise ValueError("Selected cases must belong to one suite (cannot mix TeX preambles)")
    if any(page.header != pages[0].header for page in pages):
        raise ValueError("TeX preambles differ across the selected shards")

    reference = []
    if include_baseline:
        if not report.get("reference_context"):
            raise ValueError("No explicitly requested reference engine in this run")
        reference_index = _index(root / suite, suite, "reference")
        for page in pages:
            other = reference_index.get(page.case_id)
            if other is None:
                raise ValueError(f"Reference PDF missing for {page.case_id}")
            if other.header != page.header or other.body != page.body:
                raise ValueError(f"Reference TeX differs from candidate for {page.case_id}")
            reference.append(other)

    source_tex = (pages[0].header + "\\page\n".join(page.body for page in pages) + "\\stoptext\n")
    # Check our own output is a valid, correctly ordered selection.
    _, result_cases = parse_tex(source_tex)
    if [case_id for case_id, _ in result_cases] != case_ids:
        raise ValueError("Exported TeX case order does not match requested IDs")

    selected = ", ".join(case_ids)
    candidate_engine = report.get("candidate_context") or "unknown"
    baseline_engine = report.get("reference_context") or "not provided"
    readme = (
        "ConTeXt test selection (existing, already rendered results)\n"
        "=========================================================\n\n"
        f"Suite: {suite}\nCases (in exported page order): {selected}\n"
        f"Candidate engine recorded by runner: {candidate_engine}\n"
        f"Reference engine recorded by runner: {baseline_engine}\n\n"
        "tests.tex     Selected source blocks copied from the saved test run.\n"
        "result.pdf    Corresponding candidate PDF pages, in the same order.\n"
        + ("reference.pdf Same pages from the reference engine.\n" if reference else "")
        + "\nNo Python, Nix, or test suite is needed to view these files.\n"
        "The PDF pages come from the original multi-page test runs.\n"
        "tests.tex is a new selection assembled from those original inputs;\n"
        "recompiling it may not produce byte-identical PDFs.\n"
        "A differing PDF or a failing regression test is not, by itself,\n"
        "proof of an engine bug.\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    # Finish and validate the ZIP in memory before writing anything. The
    # exclusive final create never overwrites an existing selection.
    from io import BytesIO
    memory = BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", readme)
        archive.writestr("tests.tex", source_tex)
        archive.writestr("result.pdf", _pdf_bytes(pages))
        if reference:
            archive.writestr("reference.pdf", _pdf_bytes(reference))
    with output.open("xb") as stream:
        stream.write(memory.getvalue())
