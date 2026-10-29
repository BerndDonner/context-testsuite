context-testsuite document regressions
======================================

The two .patch files implement the SAME final result.
Use only ONE, depending on whether report-xdg-open.patch from the
previous exchange was already applied to regressions/messtechnik-ws25/run.sh.

From the root of context-testsuite:

Case A (original state from unterricht02.zip):
  git apply --check --whitespace=nowarn context-testsuite-document-regressions.patch
  git apply --whitespace=nowarn context-testsuite-document-regressions.patch

Case B (earlier small xdg-open patch already applied):
  git apply --check --whitespace=nowarn context-testsuite-document-regressions-after-xdg.patch
  git apply --whitespace=nowarn context-testsuite-document-regressions-after-xdg.patch

--whitespace=nowarn preserves the original frozen TeX and MetaPost source
files (including their original CRLF line endings/trailing whitespace).
It is not needed for correctness but avoids noisy Git warnings.

Then:
  nix develop
  python -m pytest -q
  context-testsuite regression list
  context-testsuite regression run --context ../NixOS-Config/result-context-patched/bin/context --case all

Outputs: results/<case>/comparison/report.html and results/regression-report.json.
The historical reference PDFs are never rebuilt.
