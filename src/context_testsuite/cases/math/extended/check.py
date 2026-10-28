#!/usr/bin/env python3
"""Compatibility entry point: recheck saved PDFs with the shared observer."""
import sys
from context_testsuite.math_suites import main

if __name__ == "__main__":
    raise SystemExit(main(["math-extended", "--check-only", *sys.argv[1:]]))
