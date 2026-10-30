"""Create a self-contained review ZIP from a completed document-regression run.

Use the frozen fixtures as source of truth: compiler work directories also hold
temporary auxiliary/cache files and must not be archived wholesale.
"""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

from .pdf import sha256


def _files(root: Path):
    """Yield files in deterministic order, refusing symlinks."""
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink in review archive: {path}")
        if path.is_file():
            yield path


def write_regression_archive(output: Path, cases: list, archive: Path) -> Path:
    """Archive references, candidates, logs, reports and original source assets.

    Does not copy HOME/TEXMFCACHE or transient ConTeXt auxiliary files.
    Also works after a compilation failure, when no candidate PDF is available.
    """
    if archive.exists():
        raise ValueError(f"Review ZIP already exists: {archive}")
    if archive.resolve().is_relative_to(output.resolve()):
        raise ValueError("Review ZIP must be outside the result directory")

    manifest = {"schema_version": 1, "kind": "context-testsuite-document-regression-review",
                "files": []}
    readme = ("# ConTeXt document regression review\n\n"
              "Open <case>/comparison/report.html for the visual comparison.\n"
              "Each case has reference.pdf (frozen), candidate.pdf (if built), "
              "context-build.log, and source/ with its original inputs.\n"
              "regression-report.json contains the run parameters, statuses and engine version.\n"
              "Paths in JSON/HTML may refer to the original machine; "
              "the included page images and PDFs work offline.\n"
              "`changed` denotes a difference, not necessarily a regression.\n"
              "Compiler HOME, TEXMFCACHE and transient auxiliary files are omitted.\n")
    # Exclusive creation avoids accidentally overwriting an earlier review.
    with zipfile.ZipFile(archive, mode="x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, strict_timestamps=False) as zf:
        def add(path: Path, member: str):
            zf.write(path, arcname=member)
            manifest["files"].append({"path": member, "sha256": sha256(path),
                                      "size": path.stat().st_size})

        zf.writestr("README.md", readme)
        add(output / "regression-report.json", "regression-report.json")
        for case in cases:
            folder = output / case.name
            prefix = case.name
            add(case.reference, f"{prefix}/reference.pdf")
            for source in _files(case.folder):
                if source == case.reference:
                    continue
                add(source, f"{prefix}/source/{source.relative_to(case.folder).as_posix()}")
            for filename in ("context-build.log", "engine-path.txt"):
                path = folder / filename
                if path.is_file():
                    add(path, f"{prefix}/{filename}")
            candidate = folder / "work" / (case.source.stem + ".pdf")
            if candidate.is_file():
                add(candidate, f"{prefix}/candidate.pdf")
            # ConTeXt's own log and multipass reference database are useful
            # for diagnosing unresolved references; they are not caches.
            for ext in (".log", ".tuc"):
                artifact = folder / "work" / (case.source.stem + ext)
                if artifact.is_file():
                    add(artifact, f"{prefix}/context{ext}")
            comparison = folder / "comparison"
            if comparison.is_dir():
                for artifact in _files(comparison):
                    add(artifact, f"{prefix}/comparison/{artifact.relative_to(comparison).as_posix()}")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return archive
