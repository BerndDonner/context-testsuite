#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
usage() {
  echo "Usage: $0 UNPATCHED_CONTEXT PATCHED_CONTEXT [RESULT_DIR] | --check-only RESULT_DIR" >&2
  exit 2
}

command -v python3 >/dev/null || { echo 'Missing python3' >&2; exit 2; }
# Do not regenerate the fixture in the Nix store. Fail if cases.json and
# checked-in cases.tex have drifted apart.
python3 "$root/gen.py" --check

if [[ ${1:-} == --check-only ]]; then
  (( $# == 2 )) || usage
  python3 "$root/check.py" "$2"
  exit $?
fi

(( $# >= 2 && $# <= 3 )) || usage
for program in pdftotext realpath; do
  command -v "$program" >/dev/null || { echo "Missing $program" >&2; exit 2; }
done

before=$(realpath "$1")
after=$(realpath "$2")
[[ -x "$before" && -x "$after" ]] || { echo 'ConTeXt executables not found' >&2; exit 2; }

out=${3:-$(mktemp -d "${TMPDIR:-/tmp}/math-nobreak-extended-XXXXXX")}
mkdir -p "$out"
out=$(realpath "$out")
# Nix checks keep caches in $TMPDIR, not in the copied result output.
cache_root=${CONTEXT_TEST_CACHE_ROOT:-$out}
mkdir -p "$cache_root"

for item in before after; do
  mkdir -p "$out/$item" "$cache_root/home-$item"
  cp "$root/cases.tex" "$out/$item/cases.tex"
  engine="$before"
  [[ $item == after ]] && engine="$after"
  echo "Building $item ($engine) ..."
  (
    cd "$out/$item"
    export HOME="$cache_root/home-$item"
    export TEXMFCACHE="$cache_root/cache-$item"
    "$engine" --once cases.tex > build.log 2>&1
  ) || {
    tail -80 "$out/$item/build.log" >&2
    exit 1
  }
  test -s "$out/$item/cases.pdf" || { echo "Missing PDF from $item" >&2; exit 1; }
  pdftotext -layout "$out/$item/cases.pdf" "$out/$item/cases.txt"
done

python3 "$root/check.py" "$out"
