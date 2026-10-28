"""Shared, bounded subprocess execution for ConTeXt compilations.

Run the supplied engine with a caller-owned workspace, home, and cache.
Keep stdout/stderr in a file (no unbounded in-memory buffering).  On timeout,
terminate the subprocess group, including mtxrun's child engine.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import time


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    timed_out: bool
    elapsed_seconds: float


def run_context_process(context: str, source_name: str, *, work: Path,
                        home: Path, tex_cache: Path, stdout_log: Path,
                        timeout: float = 600) -> ProcessResult:
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    work.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    tex_cache.mkdir(parents=True, exist_ok=True)
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home.resolve())
    env["TEXMFCACHE"] = str(tex_cache.resolve())
    start = time.monotonic()
    with stdout_log.open("wb") as log:
        try:
            process = subprocess.Popen([context, "--once", source_name], cwd=work,
                                       env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except OSError as exc:
            log.write(f"Unable to launch {context}: {exc}\n".encode())
            return ProcessResult(127, False, time.monotonic() - start)
        try:
            returncode = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            # Kill the entire child process group, not just the mtxrun wrapper.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Exited between timeout and signal
            process.wait()
            timed_out, returncode = True, 124
            log.write(f"\nConTeXt execution timed out after {timeout:g} seconds\n".encode())
    return ProcessResult(returncode, timed_out, time.monotonic() - start)
