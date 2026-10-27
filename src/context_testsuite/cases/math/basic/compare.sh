#!/usr/bin/env bash
set -euo pipefail

# Usage: ./compare.sh UNPATCHED_CONTEXT PATCHED_CONTEXT [OUTPUT_DIR]
#        ./compare.sh --check-only EXISTING_OUTPUT_DIR
for exe in python3 realpath; do
  command -v "$exe" >/dev/null || { echo "Missing command: $exe" >&2; exit 2; }
done

if [[ ${1:-} == --check-only ]]; then
  if (( $# != 2 )); then
    echo "Usage: $0 --check-only EXISTING_OUTPUT_DIR" >&2
    exit 2
  fi
  outdir=$(realpath "$2")
else
  if (( $# < 2 || $# > 3 )); then
    echo "Usage: $0 UNPATCHED_CONTEXT PATCHED_CONTEXT [OUTPUT_DIR]" >&2
    exit 2
  fi
  command -v pdftotext >/dev/null || { echo 'Missing command: pdftotext' >&2; exit 2; }
  unpatched=$(realpath "$1")
  patched=$(realpath "$2")
  [[ -x "$unpatched" && -x "$patched" ]] || { echo 'Context executables not found' >&2; exit 2; }
  outdir=${3:-$(mktemp -d "${TMPDIR:-/tmp}/math-nobreak-XXXXXX")}
  mkdir -p "$outdir"
  outdir=$(realpath "$outdir")
  scripts_dir=$(cd "$(dirname "$0")" && pwd)
  # Nix checks keep font/format caches outside their result to avoid storing
  # large, host-specific temporary caches. Manual runs keep the old default.
  cache_root=${CONTEXT_TEST_CACHE_ROOT:-$outdir}
  mkdir -p "$cache_root"

  for version in before after; do
    mkdir -p "$outdir/$version" "$cache_root/home-$version"
    cp "$scripts_dir/cases.tex" "$outdir/$version/cases.tex"
    if [[ $version = before ]]; then engine=$unpatched; else engine=$patched; fi
    ( cd "$outdir/$version"
      export HOME="$cache_root/home-$version"
      export TEXMFCACHE="$cache_root/cache-$version"
      "$engine" --once cases.tex > build.log 2>&1
    ) || {
      tail -80 "$outdir/$version/build.log" >&2
      exit 1
    }
    test -s "$outdir/$version/cases.pdf" || { echo "No PDF from $version" >&2; exit 1; }
    pdftotext -layout "$outdir/$version/cases.pdf" "$outdir/$version/cases.txt"
  done
fi

for version in before after; do
  [[ -s "$outdir/$version/cases.txt" ]] || {
    echo "Missing $outdir/$version/cases.txt" >&2
    exit 2
  }
done

python3 - "$outdir" <<'PYCODE'
from pathlib import Path
import sys
root = Path(sys.argv[1]); before = (root/'before/cases.txt').read_text(); after = (root/'after/cases.txt').read_text()
def pages(text):
    return [p for p in text.split('\f') if p.strip()]
def body(page):
    lines = page.splitlines()
    starts = [i for i,l in enumerate(lines) if 'Das digitale Geraet' in l]
    if len(starts)!=1: raise ValueError(f'Cannot find body: {page!r}')
    return '\n'.join(lines[starts[0]:]).strip()
bef=[body(p) for p in pages(before)]; aft=[body(p) for p in pages(after)]
if len(bef)!=12 or len(aft)!=12:
    raise SystemExit(f'FAIL: Expected 12 pages, got before={len(bef)} after={len(aft)}')
changes=[]
for idx,(b,a) in enumerate(zip(bef,aft),start=1):
    if b!=a: changes.append(idx)
    print(f"C{idx:02}: {'CHANGED' if a != b else 'unchanged'}")
# A not-yet-fixed upstream version changes precisely C01 and C06.
# Once upstream fixes the problem, both variants may be identical. Neither
# outcome is a regression; any other changed case requires investigation.
if changes not in ([], [1,6]):
    raise SystemExit(f'FAIL: Unexpected line-layout changes: {changes}; expected [] or [1,6]')

# pdftotext -layout does not reliably order numerator/denominator glyphs
# in an inline fraction. In the same rendered math, it may extract
# "3 1⁄2" on one page and "3 ⁄12" on another. Normalize ONLY these
# two observed encodings, keeping spaces and line breaks untouched.
def normalized_fraction(s):
    variants = ('3 1⁄2', '3 ⁄12')
    if sum(s.count(v) for v in variants) != 1:
        raise SystemExit(f'FAIL: Unexpected math extraction: {s!r}')
    return s.replace(variants[0], '<MATH>').replace(variants[1], '<MATH>')

if normalized_fraction(aft[0]) != normalized_fraction(aft[1]):
    raise SystemExit('FAIL: C01 (~) differs in line breaks from C02 (explicit penalty)')
if normalized_fraction(aft[5]) != normalized_fraction(aft[7]):
    raise SystemExit('FAIL: C06 (mathsurround + ~) differs in line breaks from C08 (explicit penalty)')

# At the chosen line width "stel-" must remain on the math line,
# not begin a fresh line as "stelliges" (the original regression).
for case in (0,5):
    first_line = aft[case].splitlines()[0]
    if not first_line.endswith('stel\u00ad'):
        raise SystemExit(f'FAIL: C{case+1:02} not tied to following word: {first_line!r}')
print('PASS: patched variant protects math spacing; ten controls unchanged.')
print('Artifacts:', root)
PYCODE
