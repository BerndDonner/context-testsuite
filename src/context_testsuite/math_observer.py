"""Engine-independent observations of math/text line breaks in ConTeXt PDFs.

This module describes what the PDF shows; it does not decide whether a
particular breakpoint is legal.  A line break observation is intentionally
separate from the suite-specific semantic oracle.

All math suites use this observer. Fraction fixtures use glyph baselines, not
PDF text stream order. Neither extraction route invokes an external program.
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
    fraction: bool = False  # frozen basic fixture: 3 followed by a stacked 1/2


@dataclass(frozen=True)
class MathObservation:
    case_id: str
    status: str  # observed or unclassifiable
    joined: bool | None
    body: str
    pymupdf_excerpt: str
    reason: str = ""
    layout: tuple[str, ...] = ()
    line_gaps: tuple[float, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def canonical_layout(body: str) -> tuple[str, ...]:
    """Line contents, ignoring extractor-added horizontal whitespace only.

    Empty lines and hyphenation are retained. This is a line-layout signature,
    not a typography/spacing assertion or a PDF equality test.
    """
    return tuple(re.sub(r"\s+", "", line) for line in body.strip().splitlines())


def layout_key(row: dict) -> tuple:
    return (tuple(row.get("layout", canonical_layout(row["body"]))),
            tuple(row.get("line_gaps", ())))


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
    return MathObservation(case.id, "observed", joined, body, excerpt,
                           layout=canonical_layout(body))


def _observe_fraction(page: pymupdf.Page, case: MathCase) -> MathObservation:
    """Recognize ONLY the frozen 3 1/2 fixture, fail closed on other formulas.

    Numerator, slash and denominator sit on three different baselines. Sorted
    extraction can move the denominator behind the following word. Full-sized
    glyph origins determine paragraph lines; the three smaller fraction glyphs
    must form the expected stack directly beside the full-sized 3.
    """
    excerpt = page.get_text(sort=True)[:260]
    def unknown(reason):
        return MathObservation(case.id, "unclassifiable", None, "", excerpt, reason)
    if len(re.findall(rf"\b{re.escape(case.id)}\b", page.get_text())) != 1:
        return unknown("page ID missing or ambiguous")
    spans = [s for b in page.get_text("rawdict")["blocks"]
             for line in b.get("lines", []) for s in line["spans"]]
    anchors = [s for s in spans if case.body_prefix in "".join(c["c"] for c in s["chars"])]
    if len(anchors) != 1:
        return unknown("body not uniquely recognized")
    anchor = anchors[0]
    size, top = anchor["size"], anchor["origin"][1]
    glyphs, small = [], []
    for span in spans:
        for c in span["chars"]:
            if c["c"].isspace() or c["origin"][1] < top - size * .6:
                continue
            if abs(span["size"] - size) < size * .05:
                glyphs.append(c)
            else:
                small.append(c)
    lines: list[tuple[float, list[dict]]] = []
    for c in sorted(glyphs, key=lambda c: (c["origin"][1], c["origin"][0])):
        if not lines or abs(c["origin"][1] - lines[-1][0]) > .5:
            lines.append((c["origin"][1], []))
        lines[-1][1].append(c)
    for _, chars in lines:
        chars.sort(key=lambda c: c["origin"][0])
    markers = [(i, c) for i, (_, chars) in enumerate(lines) for c in chars if c["c"] == "3"]
    if len(markers) != 1 or sorted(c["c"] for c in small) != sorted("1⁄2"):
        return unknown("expected one whole digit and the stacked fraction 1/2")
    index, marker = markers[0]
    mx, my = marker["origin"]
    if any(not (mx < c["origin"][0] < mx + 2 * size and
                abs(c["origin"][1] - my) < size) for c in small):
        return unknown("fraction glyphs not adjacent to whole digit")
    parts = {c["c"]: c for c in small}
    if not parts["1"]["origin"][1] < parts["⁄"]["origin"][1] < parts["2"]["origin"][1]:
        return unknown("fraction glyph order is not 1 over 2")
    bodies = ["".join(c["c"] for c in chars) for _, chars in lines]
    body = "\n".join(bodies)
    # Reuse marker/follower validation and uncertainty handling.
    plain = MathCase(case.id, "3", case.body_prefix, case.follower_prefix)
    # The geometrical lines are compact (spaces do not carry line semantics).
    plain = MathCase(plain.id, plain.marker, re.sub(r"\s+", "", plain.body_prefix), plain.follower_prefix)
    result = observe_text(case.id + "\n" + body, plain)
    if result.status != "observed":
        return unknown(result.reason)
    normalized = body.replace("3", "<MATH>", 1)
    gaps = tuple(round((b[0] - a[0]) / size, 3) for a, b in zip(lines, lines[1:]))
    return MathObservation(case.id, "observed", result.joined, normalized, excerpt,
                           layout=canonical_layout(normalized), line_gaps=gaps)


def observe_pdf(pdf: Path, cases: Iterable[MathCase]) -> list[MathObservation]:
    """One input case per PDF page, preserving case order and uncertainty."""
    expected = list(cases)
    if not expected or len({c.id for c in expected}) != len(expected):
        raise ValueError("Expected nonempty, unique case IDs")
    with pymupdf.open(pdf) as document:
        if document.needs_pass:
            raise ValueError(f"Encrypted PDF: {pdf}")
        if len(document) != len(expected):
            raise ValueError(f"Expected {len(expected)} PDF pages, found {len(document)}: {pdf}")
        return [(_observe_fraction(page, case) if case.fraction else
                 observe_text(page.get_text(sort=True), case))
                for page, case in zip(document, expected)]
