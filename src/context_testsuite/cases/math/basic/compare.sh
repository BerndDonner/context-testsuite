#!/usr/bin/env bash
set -euo pipefail
# Compatibility entry point; use the same Python as the devShell/installed CLI.
exec python -m context_testsuite.math_suites math-basic "$@"
