"""Document-specific evidence selection for the common offline review archiver."""
from __future__ import annotations

from pathlib import Path

from .review_archive import _files, create_review_archive


def write_regression_archive(output: Path, cases: list, archive: Path) -> Path:
    """Keep the established <case>/... member names for existing consumers."""
    selected = {"regression-report.json": output / "regression-report.json"}
    for case in cases:
        folder = output / case.name
        prefix = case.name
        selected[f"{prefix}/reference.pdf"] = case.reference
        for source in _files(case.folder):
            if source != case.reference:
                selected[f"{prefix}/source/{source.relative_to(case.folder).as_posix()}"] = source
        for filename in ("context-build.log", "engine-path.txt"):
            selected[f"{prefix}/{filename}"] = folder / filename
        selected[f"{prefix}/candidate.pdf"] = folder / "work" / (case.source.stem + ".pdf")
        for ext in (".log", ".tuc"):
            selected[f"{prefix}/context{ext}"] = folder / "work" / (case.source.stem + ext)
        comparison = folder / "comparison"
        if comparison.is_dir():
            for path in _files(comparison):
                selected[f"{prefix}/comparison/{path.relative_to(comparison).as_posix()}"] = path
    return create_review_archive(output, archive, kind="document-regression",
                                 selected_files=selected, result_prefix="",
                                 parameters={"selected_cases": [c.name for c in cases]})
