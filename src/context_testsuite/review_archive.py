"""Self-contained, inspectable review archives for every result-producing CLI command.

Each archive includes the generated evidence, original input files and the
Python implementations/expectations needed to interpret the observations.
The ZIP is for offline review, not a hermetic reproduction of the Nix engines.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

# Never archive ephemeral TeX/ConTeXt caches or Python/runtime internals.
EXCLUDED_DIRS = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "cache", "cache-home", "tex-cache", "home", "home-before", "home-after",
    "cache-before", "cache-after", ".venv", "venv", "TEXMFCACHE", "TEXMFVAR",
})


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(directory: Path):
    """Visit normal files only; reject symlinks (including directory symlinks)."""
    for parent, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED_DIRS)
        for name in [*dirs, *files]:
            path = Path(parent) / name
            if path.is_symlink():
                raise ValueError(f"Review ZIP refuses symlink: {path}")
        for name in sorted(files):
            path = Path(parent) / name
            if path.is_file():
                yield path


def _version(binary: str | None) -> str | None:
    if not binary:
        return None
    try:
        run = subprocess.run([binary, "--version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace",
                             timeout=15, check=False)
        lines = [line.strip() for line in run.stdout.splitlines()
                 if line.strip().startswith("mtx-context") and
                 any(s in line.lower() for s in ("local build:", "current version:",
                     "main context file:", "process management", "patchset:",
                     "source revision:"))]
        # Non-ConTeXt stand-ins used by the test infrastructure may only print
        # a single line of version info.
        return "\n".join(lines) or (run.stdout.strip()[:1024] if run.returncode == 0 else None)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _revision() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        cmd = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, timeout=5, check=False)
        return cmd.stdout.strip() if cmd.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def output_zip(output: Path) -> Path:
    """Return <output>.zip; fail rather than overwrite an earlier run."""
    output = output.expanduser().resolve()
    archive = output.with_name(output.name + ".zip")
    if archive.exists() or archive.is_symlink():
        raise ValueError(f"Review ZIP already exists: {archive}; select another --output")
    if output.is_dir() and any(output.iterdir()):
        raise ValueError(f"--zip requires a new or empty --output: {output}")
    if output.exists() and not output.is_dir():
        raise ValueError(f"--output is not a directory: {output}")
    return archive


def create_review_archive(output: Path, archive: Path, *, kind: str,
                          inputs: dict[str, Path] | None = None,
                          engines: dict[str, str | None] | None = None,
                          parameters: dict | None = None,
                          error: str | None = None,
                          result_prefix: str = "results",
                          include_software: bool = True,
                          selected_files: dict[str, Path] | None = None) -> Path:
    """Build an offline review ZIP with hashed output, inputs and test definitions.

    inputs maps a semantic input name to a file or a directory. Missing inputs
    are reported in manifest.json instead of being silently omitted. No path in
    the manifest needs access to the original filesystem to inspect the ZIP.
    """
    output, archive = output.resolve(), archive.expanduser().resolve()
    if archive == output or archive.is_relative_to(output):
        raise ValueError("Review ZIP must be outside the output directory")
    if not output.is_dir():
        raise ValueError(f"No result directory to archive: {output}")
    if archive.exists() or archive.is_symlink():
        raise ValueError(f"Review ZIP already exists: {archive}")
    inputs = inputs or {}
    engines = engines or {}
    manifest = {"schema_version": 1, "kind": kind,
                "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "testsuite_revision": _revision(),
                "parameters": parameters or {},
                "engines": {role: {"path": binary, "version": _version(binary)}
                            for role, binary in engines.items()},
                "error": error, "inputs": {}, "files": []}
    readme = ("# ConTeXt testsuite: offline review bundle\n\n"
              f"Run kind: `{kind}`\n\n"
              "Read manifest.json for roles, SHA-256 checksums and missing inputs.\n"
              "Generated artifacts live under results/ (document regression archives "
              "retain their established layout).\n"
              "Original inputs live under inputs/; the suite's Python test "
              "implementations and expectations under software/.\n"
              "Use the included PDF, source, logs, JSON reports and comparison images "
              "to assess failures or changes independently.\n"
              "Stored report paths can be absolute paths from the generating machine; "
              "use manifest.json and the archive's relative paths instead.\n"
              "An observed difference is not automatically a regression.\n"
              "ConTeXt executables and caches are intentionally not bundled.\n")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, strict_timestamps=False) as zf:
        written = set()

        def add(path: Path, member: str, role: str):
            if path.is_symlink():
                raise ValueError(f"Review ZIP refuses symlink: {path}")
            if member in written:
                raise ValueError(f"Duplicate review ZIP member: {member}")
            written.add(member)
            zf.write(path, member)
            manifest["files"].append({"path": member, "sha256": _hash(path),
                                      "size": path.stat().st_size, "role": role})

        zf.writestr("README.md", readme)
        if result_prefix:
            prefix = result_prefix.rstrip("/") + "/"
        else:
            prefix = ""
        if selected_files is None:
            for path in _files(output):
                add(path, prefix + path.relative_to(output).as_posix(), "result")
        else:
            for member, path in sorted(selected_files.items()):
                if path.is_file():
                    add(path, member, "result")
        for role, path in sorted(inputs.items()):
            path = Path(path).expanduser().resolve()
            target = f"inputs/{role}"
            if path.is_file():
                add(path, target + "/" + path.name, "input:" + role)
                manifest["inputs"][role] = {"status": "included", "archive": target + "/" + path.name}
            elif path.is_dir():
                copied = 0
                for file in _files(path):
                    add(file, target + "/" + file.relative_to(path).as_posix(), "input:" + role)
                    copied += 1
                manifest["inputs"][role] = {"status": "included", "archive": target + "/", "files": copied}
            else:
                manifest["inputs"][role] = {"status": "missing", "expected_name": path.name}
        if include_software:
            package = Path(__file__).resolve().parent
            # Include all tests and their interpretation code, not just the
            # generated PDF: otherwise an AI cannot judge assertion semantics.
            for path in _files(package):
                if path.suffix == ".py":
                    add(path, "software/context_testsuite/" + path.relative_to(package).as_posix(), "software")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return archive


@contextmanager
def review_run(enabled: bool, output: Path, *, kind: str,
               inputs: dict[str, Path] | None = None,
               engines: dict[str, str | None] | None = None,
               parameters: dict | None = None):
    """Archive even a failed/exceptional run, if it produced an output folder."""
    if not enabled:
        yield
        return
    output = output.expanduser().resolve()
    archive = output_zip(output)  # Validate *before* launching an expensive run.
    try:
        yield
    finally:
        if output.is_dir():
            exc = sys.exc_info()[1]
            create_review_archive(output, archive, kind=kind, inputs=inputs,
                                  engines=engines, parameters=parameters,
                                  error=(f"{type(exc).__name__}: {exc}" if exc else None))
            print(f"Review ZIP: {archive}", flush=True)
