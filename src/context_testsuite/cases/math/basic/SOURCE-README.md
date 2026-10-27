# LuaMetaTeX math/noautobreak regression tests

The regular `.#context` package builds the upstream LuaMetaTeX engine.
The explicit `.#context-patched` package builds the same pinned source with
`patches/luametatex-math-glue-noautobreak.patch`. Both install the same
ConTeXt TeX files, third-party filter/Vim modules and pinned fonts.

## Build both engines (no system switch)

```bash
nix build .#context -o result-context -L
nix build .#context-patched -o result-context-patched -L
```

## Automatic Nix check

```bash
nix build .#checks.x86_64-linux.context-math-nobreak \
  -o result-context-math-nobreak -L
```

The check runs `compare.sh` against both of these derivations, stores their
12-page PDFs and extracted text and checks correctness. It accepts either
(a) the regression is present upstream and only C01/C06 change, or
(b) the upstream engine is already fixed and no cases change. Other changes
fail the test. The patched version must always avoid the forbidden breaks.

## Run the same comparison manually

```bash
nix shell nixpkgs#poppler-utils nixpkgs#python3 -c bash \
  pkgs/context/tests/math-nobreak/compare.sh \
  "$PWD/result-context/bin/context" \
  "$PWD/result-context-patched/bin/context" \
  "$PWD/math-nobreak-results"
```

Recheck prior results without recompiling:

```bash
nix shell nixpkgs#python3 -c bash \
  pkgs/context/tests/math-nobreak/compare.sh \
  --check-only "$PWD/math-nobreak-results"
```

## Twelve cases

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| C01 | Inline math followed by `~` | Must stay together |
| C02 | Math followed by `\nonbreakablespace` | Reference: protected |
| C03 | Math followed by ordinary space | Break remains possible |
| C04 | Plain text followed by `~` | Unchanged |
| C05 | Plain text followed by ordinary space | Unchanged |
| C06 | Math followed by `~`, `\mathsurround=3pt` | Must stay together |
| C07 | Math followed by ordinary space, `\mathsurround=3pt` | Unchanged |
| C08 | Math followed by `\nonbreakablespace`, `\mathsurround=3pt` | Reference: protected |
| C09 | Math followed by `\penalty10000` | Unchanged |
| C10 | Math followed by `\penalty0` | Unchanged |
| C11 | Math followed by `\thinspace` | Unchanged |
| C12 | Math, comma, ordinary space | Unchanged |

`pdftotext` sometimes extracts a stacked fraction with either `3 1⁄2`
or `3 ⁄12`. The comparison normalizes only those two known render-equivalent
forms and still checks line breaks. It is a narrow regression gate, **not**
a proof that all glue and math penalty combinations behave correctly.
Inspect both PDFs visually and use real documents as a final regression check.

For a historical 2024 reference, override `context-src` when building the
regular variant. Do not apply the experimental 2026 C patch to 2024 sources.

## Extended tests

The 74-case experiment is kept in [`extended/`](extended/README.md) and is
run as the separate flake check `context-math-nobreak-extended`. It tests
additional Math-Penalties, `mathsurround` settings, and combinations of
Glue options without modifying either package derivation.
