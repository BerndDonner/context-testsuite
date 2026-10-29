# Frozen document regressions

Each **immediate subdirectory** is automatically discovered as a document test.
No registry, manifest or shell script is needed. Put in each directory:

- **Exactly one** root-level `*.tex` document (any file name).
- **`reference.pdf`**, an existing, frozen historical PDF. The runner never
  builds this reference; missing references cause an error.
- Any extra files referenced relative to the document, e.g. `assets/` or
  `include/metapost/`. All dependencies must be kept locally in the test.

All candidates are built with the **explicitly chosen** ConTeXt executable.
The runner will not install or select a ConTeXt version for you, nor pull
inputs from `unterrichts-texte` or `NixOS-Config`.

From the repo root (after `nix develop`):

```sh
context-testsuite regression list
context-testsuite regression run \
  --context ../NixOS-Config/result-context-patched/bin/context \
  --case all
context-testsuite regression run \
  --context ../NixOS-Config/result-context-patched/bin/context \
  --case mathe-m3a-ws2526
```

The default output root is `results/`. Every case gets:

- `results/<case>/work/`: frozen TeX inputs and candidate build artifacts
- `results/<case>/context-build.log` and `engine-path.txt`
- `results/<case>/comparison/report.html`, `report.json`, optional `text.diff`

There is also `results/regression-report.json` summarizing the selected run.
The CLI prints a directly copyable `xdg-open <absolute path>` for each HTML
report, but does **not** start a browser by itself. The output root must not
be inside the fixtures or contain them.

A visual status of `changed` is **not automatically a regression** and does
not cause a nonzero exit code. A build or comparison error does; inspect the
log and the aggregate report in this case. Reference PDFs are never modified.

This is source-checkout functionality: installed wheels do not bundle `tests/`.
