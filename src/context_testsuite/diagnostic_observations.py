"""Optional PDF-only observations for curated one-case-per-page diagnostics.

No C tracing required. A page tells us *what* happened (join/split), not
whether a given penalty precedence rule is correct. Keep the registry explicit
so missing or reordered cases fail closed rather than yielding a false pass.
"""
from __future__ import annotations

from pathlib import Path

from .math_observer import MathCase, observe_pdf

# One semantic scenario per physical page in penalty-precedence.tex.
# Do not infer the number of pages from whatever the engine happened to emit.
PENALTY_PRECEDENCE = (
    {"id": "P01", "math_penalty": -10000, "glue": "ordinary", "math_factor": None},
    {"id": "P02", "math_penalty": -10000, "glue": "active-10000", "math_factor": None},
    {"id": "P03", "math_penalty": 500, "glue": "inactive-field-10000", "math_factor": None},
    {"id": "P04", "math_penalty": 500, "glue": "active-10000", "math_factor": None},
    {"id": "P05", "math_penalty": 500, "glue": "active-10000", "math_factor": 67000},
    {"id": "P06", "math_penalty": 500, "glue": "inactive-field-0", "math_factor": None},
)


def observe_diagnostic_pdf(case: str, pdf_path: Path) -> dict:
    if case != "penalty-precedence":
        raise ValueError(f"No page observer registered for diagnostic: {case}")
    rows = observe_pdf(pdf_path, [MathCase(item["id"]) for item in PENALTY_PRECEDENCE])
    return {"schema_version": 1, "case": case, "method": "pymupdf",
            "purpose": "Observed line breaks, not a penalty semantics oracle",
            "summary": {"pages": len(rows), "observed": sum(r.status == "observed" for r in rows),
                        "unclassifiable": sum(r.status != "observed" for r in rows)},
            "pages": [{"page": page, "scenario": dict(scenario), **row.as_dict()}
                      for page, (scenario, row) in enumerate(zip(PENALTY_PRECEDENCE, rows), 1)]}
