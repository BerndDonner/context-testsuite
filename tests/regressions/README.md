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
  --context ../NixOS-Config/result-context/bin/context \
  --case all --output results/dokumente-p1 --zip
context-testsuite regression run \
  --context ../NixOS-Config/result-context/bin/context \
  --case mathe-m3a-ws2526 --output results/mathe-p1
```

The default output root is `results/regression-run/`. Every case gets:

- `<output>/<case>/work/`: frozen TeX inputs and candidate build artifacts
- `<output>/<case>/context-build.log` and `engine-path.txt`
- `<output>/<case>/comparison/report.html`, `report.json`, optional `text.diff`

There is also `<output>/regression-report.json` summarizing the selected run.
The CLI prints a directly copyable `xdg-open <absolute path>` for each HTML
report, but does **not** start a browser by itself. The output root must not
be inside the fixtures or contain them.

A visual status of `changed` is **not automatically a regression** and does
not cause a nonzero exit code. A build or comparison error does; inspect the
log and the aggregate report in this case. Reference PDFs are never modified.

This is source-checkout functionality: installed wheels do not bundle `tests/`.


## Laufmodus und Review-Archiv

Echte Dokument-Regressionen werden **ohne `--once`** aufgerufen. ConTeXt
steuert seine normalen Mehrfachläufe für Referenzen und Inhaltsverzeichnisse.
Die kleinen Math- und Diagnostiktests verwenden weiterhin `--once`.

```sh
context-testsuite regression run \
  --context ../NixOS-Config/result-context/bin/context \
  --case all --output results/dokumente-p1 --zip
```

Das Ergebnisverzeichnis muss neu oder leer sein; kein Lauf überschreibt
ungefragt die Daten eines früheren. `--zip` legt `results/dokumente-p1.zip`
neben dem Ergebnisordner an. Referenz- und Kandidaten-PDFs, Quellen/Assets,
Build-Logs und HTML-/JSON-/Bildvergleiche sind enthalten; Cache und
Hilfsdateien nicht. Auch bei einem Kompilierungsfehler wird soweit möglich
ein ZIP mit den Fehler-Logs angelegt. Version und Aufrufparameter stehen in
`regression-report.json`.
