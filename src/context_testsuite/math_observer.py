"""Engine-independent observations of math/text line breaks in ConTeXt PDFs.

This module describes what the PDF shows; it does not decide whether a
particular breakpoint is legal.  A line break observation is intentionally
separate from the suite-specific semantic oracle.

No Poppler subprocess is needed.  The old suite analyzers remain unchanged
until their independent migration and comparison (phase 3).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable

import pymupdf


@dataclass(frozen=True)
class MathCase:
    id: str
    marker: str = "12345"
    body_prefix: str = "Das digitale Geraet"
    follower_prefix: str = "ste"


@dataclass(frozen=True)
class MathObservation:
    case_id: str
    status: str  # observed or unclassifiable
    joined: bool | None
    body: str
    pymupdf_excerpt: str
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def observe_text(text: str, case: MathCase) -> MathObservation:
    """Classify whether the follower starts on the math marker's line.

    The marker may occur on a later line than the paragraph prefix.  Hyphenated
    `stel-` counts as joined: the question is the break *before* 'stelliges'.
    A missing/multiple marker is unknown, never silently classified as split.
    """
    lines = text.splitlines()
    excerpt = text[:260]
    def unknown(reason: str, body: str = "") -> MathObservation:
        return MathObservation(case.id, "unclassifiable", None, body, excerpt, reason)

    ids = [line for line in lines if re.search(rf"\b{re.escape(case.id)}\b", line)]
    if len(ids) != 1:
        return unknown("page ID missing or ambiguous")
    # PDF extractors may insert multiple spaces between visually adjacent words.
    prefix = re.compile(r"\s+".join(map(re.escape, case.body_prefix.split())))
    starts = [i for i, line in enumerate(lines) if prefix.search(line)]
    if len(starts) != 1:
        return unknown("body not uniquely recognized")
    body_lines = lines[starts[0]:]
    body = "\n".join(body_lines).strip()
    pattern = re.compile(rf"(?<![0-9]){re.escape(case.marker)}(?![0-9])")
    locations = [(line, m) for line in body_lines for m in pattern.finditer(line)]
    if len(locations) != 1:
        return unknown("math marker not unique in body", body)
    line, match = locations[0]
    tail = line[match.end():]
    marker_line_index = next(i for i, candidate in enumerate(body_lines) if candidate is line)
    remaining = "\n".join([tail, *body_lines[marker_line_index + 1:]])
    if case.follower_prefix not in remaining:
        return unknown("following text not found after math marker", body)
    joined = re.match(rf"\s*{re.escape(case.follower_prefix)}", tail) is not None
    return MathObservation(case.id, "observed", joined, body, excerpt)


def observe_pdf(pdf: Path, cases: Iterable[MathCase]) -> list[MathObservation]:
    """One input case per PDF page, preserving case order and uncertainty."""
    expected = list(cases)
    with pymupdf.open(pdf) as document:
        if document.needs_pass:
            raise ValueError(f"Encrypted PDF: {pdf}")
        if len(document) != len(expected):
            raise ValueError(f"Expected {len(expected)} PDF pages, found {len(document)}: {pdf}")
        return [observe_text(page.get_text(sort=True), case)
                for page, case in zip(document, expected)]
