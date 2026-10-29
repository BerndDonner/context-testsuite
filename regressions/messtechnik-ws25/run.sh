#!/usr/bin/env bash
# One existing PDF reference vs one explicitly selected ConTeXt engine.
# Does not modify the reference and never runs any reference engine.
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
ROOT=$(cd -- "$HERE/../.." && pwd -P)

if (( $# < 1 || $# > 2 )); then
  echo "Usage: $0 /absolute/path/to/patched/context [output-directory]" >&2
  echo "Run within the context-testsuite Python environment (nix develop)." >&2
  exit 2
fi

ENGINE=$1
if [[ "$ENGINE" != */* ]]; then
  ENGINE=$(command -v -- "$ENGINE" || true)
elif [[ "$ENGINE" != /* ]]; then
  ENGINE="$PWD/$ENGINE"
fi
if [[ -z "$ENGINE" || ! -x "$ENGINE" ]]; then
  echo "Error: ConTeXt executable not found or not executable: $1" >&2
  exit 2
fi

OUTPUT_ARG=${2:-"$ROOT/results/messtechnik-ws25"}
mkdir -p -- "$OUTPUT_ARG"
OUTPUT=$(cd -- "$OUTPUT_ARG" && pwd -P)
if [[ "$OUTPUT" == "$HERE" || "$OUTPUT" == "$ROOT" || "$HERE" == "$OUTPUT"/* ]]; then
  echo "Error: output directory must not be the fixture or contain it" >&2
  exit 2
fi

# Recreate *only* the dedicated candidate workspace.  The reference in
# HERE/reference.pdf is never overwritten or regenerated.
WORK="$OUTPUT/work"
rm -rf -- "$WORK"
mkdir -p -- "$WORK/assets" "$OUTPUT/home" "$OUTPUT/cache"
cp -- "$HERE/Schulaufgabe001_WS25.tex" "$WORK/Schulaufgabe001_WS25.tex"
cp -- "$HERE/assets/sabel.png" "$WORK/assets/sabel.png"

printf '%s\n' "$ENGINE" > "$OUTPUT/engine-path.txt"
printf '%s\n' 'Compiling candidate with selected engine...' \
  "  engine:    $ENGINE" \
  "  source:    $HERE/Schulaufgabe001_WS25.tex" \
  "  reference: $HERE/reference.pdf" \
  "  output:    $OUTPUT"

if ! (
  cd -- "$WORK"
  HOME="$OUTPUT/home" TEXMFCACHE="$OUTPUT/cache" \
    "$ENGINE" Schulaufgabe001_WS25.tex
) > "$OUTPUT/context-build.log" 2>&1; then
  echo "Error: candidate build failed. See $OUTPUT/context-build.log" >&2
  exit 2
fi

CANDIDATE="$WORK/Schulaufgabe001_WS25.pdf"
if [[ ! -s "$CANDIDATE" ]]; then
  echo "Error: engine returned successfully, but PDF is missing: $CANDIDATE" >&2
  exit 2
fi

"$ROOT/bin/context-testsuite" pdf compare \
  --reference "$HERE/reference.pdf" \
  --candidate "$CANDIDATE" \
  --output "$OUTPUT/comparison"

printf '\nSee the detailed side-by-side report:\n  %s\n' "$OUTPUT/comparison/report.html"
# Note: the suite's pdf-compare deliberately reports differences without
# treating all visual changes as errors; exit status 0 means comparison succeeded.
