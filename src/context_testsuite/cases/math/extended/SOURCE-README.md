# Extended LuaMetaTeX inline-math / noautobreak regression suite

Tests the pinned ConTeXt LMTX **2026.10.25 20:06** without and with the experimental `texlinebreak.c` fix.

The 76-page `cases.tex` is generated from `cases.json` with `python3 gen.py`.
`compare.sh` validates the fixture via `gen.py --check` so the Nix check
never writes into the read-only store or silently tests outdated cases.
Each case is isolated in a group and a separate PDF page. `pdftotext -layout`
is used for *line-break classification*, not as a byte-perfect mathematical
representation. Every case prints decimal digits `12345`, avoiding the PDF
fraction extraction problem identified in the first 12-case suite.

## Automated Nix check (recommended)

Run directly from the `NixOS-Config` repository root, using the pinned
upstream and experimental C-patched package variants:

```bash
nix build .#checks.x86_64-linux.context-math-nobreak-extended \
  -o result-context-math-nobreak-extended -L
```

The check produces 76-page PDFs, build logs, extracted text and `checks.json`
in the result symlink. The five cases combining `noautobreak` with an explicit math penalty of
`-10000` are mandatory forced-break checks: a suppressed force break fails
the check. Inspect `result-context-math-nobreak-extended/checks.json`.

## Manual run against real patched C engine

From NixOS-Config, with both builds already present:

```bash
nix shell nixpkgs#poppler-utils nixpkgs#python3 -c bash \
  pkgs/context/tests/math-nobreak/extended/compare.sh \
  "$PWD/result-context-unpatched/bin/context" \
  "$PWD/result-context-patched/bin/context" \
  "$PWD/math-nobreak-extended-results"
```

Checks only on existing results:

```bash
python3 pkgs/context/tests/math-nobreak/extended/check.py \
  "$PWD/math-nobreak-extended-results"
```

## Categories

- `protected`: `~`, `\nobreakspace`, and direct `glue.options` with the
  `noautobreak` bit. The patched output must keep the number together with
  the following word, even if ConTeXt chooses to hyphenate the word later.
- `normal`: unprotected glue, spaces and punctuation. The extracted body text
  must stay exactly the same between the two builds.
- `other`: explicit penalties, kerns, boxes and other controls. Must stay
  exactly the same, except `L15`: its explicit `\penalty-10000` must still
  produce precisely one forced break. The pre-fix PDF contains an extra empty
  line before the following word; the checker allows **only** the removal of
  that empty line, checking the rest of the extracted text for equality.
  `L16` is `protected`: it uses `options=1` after math with
  `\mathsurround=3pt`, and must change from split to join.
- `conflict`: retained test fixture name for the five adversarial
  `\postinlinepenalty=-10000` / `\postshortinlinepenalty=-10000`
  cases with protected glue. Their semantics are now checked: an explicit
  forced break has priority over glue's `noautobreak` option. All five must
  remain **split** or the regression check fails.

The direct-glue tests exercise `noautobreak` alone and together with `isspace`,
`nondiscardable`, `setdiscardable`, `limit`, and zero-width/stretchable glue.

## Scope and limitations

`check.py` is a behavioral regression gate, not a proof of engine correctness.
It does not validate every possible LuaMetaTeX node list or user callback.
Visual inspection of pages around modified cases is recommended.

In the separate analysis archive, the baseline PDF was generated with the
**unpatched** bundled LMTX 2026.10.25. Its `penalty-reference` PDF uses an
**unchanged C engine**
with the old ConTeXt `usepenalties=true` workaround. The latter is not the
actual proposed C fix, and notably does not exercise directly written glue
with `noautobreak`. Do not treat comparison to that reference as a test of the C fix.

## What was actually executed in the assistant's sandbox (2026-10-27)

- `unpatched/`: 74 pages compiled successfully using bundled LMTX 2026.10.25, **without** C fix.
- `penalty-reference/`: 74 pages compiled successfully using the same **unpatched C engine**, with `spac-chr.lmt` switched to the historical `usepenalties=true` behavior.
- Of 74 comparisons, 17 change their line-break category with the fallback (14 `protected` cases and three adversarial `conflict` cases); all 24 `normal` and all 12 `other` cases remain unchanged.
- The reference intentionally does **not** fix Lua-inserted glue with `noautobreak`; the checker correctly **fails** on that reference (13 cases) instead of reporting a false PASS.
- The actual patched-C executable was *not* available in this sandbox. A genuine positive result on the C patch must be obtained by running `compare.sh` with the user's `result-context-patched` binary.

## Nix integration

The test files are under `pkgs/context/tests/math-nobreak/extended/`,
not in the LuaMetaTeX engine derivation. The standalone flake check uses
`context` and `context-patched` package outputs without changing either.
The Nix expression references the **whole test directory**, ensuring that
`cases.json`, `cases.tex`, `check.py`, and `gen.py` accompany `compare.sh`.

The C patch itself stays in
`pkgs/context/patches/luametatex-math-glue-noautobreak.patch`.

## Capturing a failed comparison for review

Nix may discard a failed derivation's `$out`. To keep the actual 76-page PDFs
and text for investigation, run the standalone script with a writable output:

```bash
nix shell nixpkgs#poppler-utils nixpkgs#python3 -c bash \
  pkgs/context/tests/math-nobreak/extended/compare.sh \
  "$PWD/result-context/bin/context" \
  "$PWD/result-context-patched/bin/context" \
  "$PWD/math-nobreak-extended-results"
```

The script may return exit code 1 on purpose, but the results persist.
`L15` is on page **55** and `L16` on page **56**. The five forced-math
checks are `P03`, `P15`, `P17`, `X02`, and `X10`.
`P17` deliberately uses single-character inline math (`\math{1}`), because
`\postshortinlinepenalty` applies only when LuaMetaTeX flags the math node
as short. The former `\math{12345}` fixture was not short and did **not**
carry a forced penalty; treating its formerly allowed implicit break as
`-10000` was a test bug. `P19` retains that long formula with protected glue,
and `P20` checks the short formula with ordinary breakable space.

Compare relevant pages visually as well; PDF text extraction is not sufficient
for a proof of all layout properties.
