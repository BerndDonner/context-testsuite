# Diagnostic/reader-friendly ConTeXt examples

These are source-level diagnostic testcases for the Hans 2026-10-28
`texlinebreak.c` candidate, intentionally separate from the Python runner.
They require only the selected ConTeXt installation and are suitable for
manual reduction and discussion. They have **not** yet been compiled with
Hans's engine in this environment.

- `noautobreak-natural.tex`: natural sentence using `3 1/2`-digit display,
  protected and ordinary glue, with/without forced post-inline math penalty.
- `noautobreak-explicit.tex`: explicit `\\penalty-10000` *node* before `~`,
  separate from math-generated penalties.
- `glue-option-entry.tex`: `glue.penalty=500/10000` x `glue.options=0/1`.
  Produces `CTS-GLUE created ...` lines. The optional C-instrumented engine
  additionally emits `CTS-LB entry ...` and `CTS-LB decision=...`, which
  observe the values and behavior directly inside Hans's helper.

Example:

```sh
/path/to/result-context-hans/bin/context --once glue-option-entry.tex
rg 'CTS-GLUE' glue-option-entry.log
```

The ordinary engine shows only node creation; the separately instrumented
Hans engine is required to verify what reaches the C helper. The engine-entry
trace is stronger evidence than an intermediate Lua processor callback.

## Glue diagnostic: use the C trace, not a Lua processor hook

The three previous Lua callback variants failed on unavailable or incompatible
node APIs. None of those callback failures concerns the linebreaker. The
processor hook is now removed because it is redundant: the separate C trace
already observes the glue flags **at the point of use**. This also avoids
modifying the paragraph node list merely for an additional inspection.

Run `glue-option-entry.tex` with the trace engine and inspect stdout:

```sh
/path/to/result-context-hans-trace/bin/context --once \
    glue-option-entry.tex > glue-trace.stdout 2>&1
grep -aE 'CTS-GLUE|CTS-LB' glue-trace.stdout
```

The four cases have `(penalty, options)` of `(500,0)`, `(10000,0)`,
`(10000,1)`, `(500,1)` in this order. The trace's `haspenalty` value is
computed in C via `tex_has_glue_option`. The confirmed critical observation
is `haspenalty=0 gluepenalty=10000` followed by `glue-overrides`.

## Factor positive control

```sh
/path/to/context --once math-factor-positive-control.tex
rg 'CTS-FACTOR|mathpenaltyfactor|linebreak: specification' math-factor-positive-control.log
```

`math-factor-positive-control.tex` generates 12 paired paragraphs using
`\parpasses` (not `\mathinlinepenaltyfactor`). The math penalty is 500 and
the factor changes from 1000 to 67000: if the factor is active and applied,
the effective penalty crosses the 10000 threshold. Three line widths are
used. The first six paragraphs have `glue.penalty=0, options=0`; the next
six have `glue.penalty=10000, options=0`. In Hans's source the second case
can return before the multiplication. The settings now apply inside each
test paragraph, without an intervening `framedtext` setup. Pretolerance
and tolerance are set to zero to discourage completion in the preliminary
unscaled passes. The compile log's actual pass values and, ideally, the
optional C-entry trace must be checked. **Identical PDF
rows alone do not prove that the factor is ignored**, since other feasible
breakpoints may yield the same layout.

## Optional exact C-entry trace (no changes to the Python runner)

Apply the separate `nixos-config-hans-trace.patch` in `NixOS-Config`.
It adds the named variant `.#context-hans-trace-2026-10-28`, stacking a
**diagnostic-only** C patch after Hans's original patch. The normal Hans
variant and the single-engine devShell are untouched.

```sh
# From NixOS-Config:
nix build .#context-hans-trace-2026-10-28 -o result-context-hans-trace -L

# From this diagnostics directory:
/path/to/NixOS-Config/result-context-hans-trace/bin/context --once \
    glue-option-entry.tex 2>&1 | tee glue-option-entry.stdout
rg 'CTS-GLUE|CTS-LB' glue-option-entry.log glue-option-entry.stdout

/path/to/NixOS-Config/result-context-hans-trace/bin/context --once \
    math-factor-positive-control.tex 2>&1 | tee math-factor-positive-control.stdout
rg 'CTS-FACTOR|CTS-LB|mathpenaltyfactor' \
    math-factor-positive-control.log math-factor-positive-control.stdout
```

`CTS-LB entry` comes **from inside Hans's** `tex_aux_checked_math_penalty`,
not from a Lua callback. In particular, the trace distinguishes actual
`haspenalty=0/1`, `noauto=0/1`, stored `gluepenalty`, and active `factor`.
A following `CTS-LB decision=...` shows whether the factor was applied or
bypassed. Filter the output by `CTS-LB` because normal paragraph tracing can
be verbose. The original engine code is not modified by these diagnostic
runs; the instrumentation is a separately named package build.

## Acceptance criteria for the two diagnoses

**Glue:** `CTS-LB entry ... haspenalty=0 gluepenalty=10000` followed by
`CTS-LB decision=glue-overrides` is the direct C-level evidence. It has
already been observed in the 2026-10-28 trace; the Lua hook is corroborating
information, not a prerequisite.

**Factor:** The case is **inconclusive** unless at least one `CTS-LB entry`
reports `factor=1000` and another reports `factor=67000`. Earlier runs
showed `factor=0` in all C-level entries. If this persists, investigate
paragraph-pass activation rather than attributing identical PDF output to
a penalty-factor defect. In a successful control, inspect whether the
`glue-overrides` branch returns before applying the active nonzero factor.

## 2026-10-28 C-trace results

From the submitted 2026-10-28 traces:

- `math=500 factor=67000 haspenalty=0 gluepenalty=0` yields
  `decision=scaled-result penalty=33500 factor=67000`.
- For the same math and factor, `haspenalty=0 gluepenalty=10000` yields
  `decision=glue-overrides`, before math scaling.

These establish two control-flow properties directly in C. They do not
establish two independent visible typesetting bugs: 33500 and 10000 both
prohibit a break. The previous `processors/after` Lua hook was optional
corroboration and has been removed to avoid repeated irrelevant failures.

## Six-page penalty precedence document (Hans's max-penalty discussion)

`penalty-precedence.tex` has exactly six labeled cases, one **physical PDF
page** each: P01 ordinary glue after forced math; P02 active glue penalty
10000 after forced math; P03 an inactive stored glue penalty 10000 after
math penalty 500; P04 the matching active glue penalty; P05 P04 plus active
paragraph-pass `mathpenaltyfactor=67000`; P06 is the control for P03,
with the same Math penalty 500, glue width 3pt and options 0, but the
stored glue penalty changed from 10000 to 0. P06 is appended so P01--P05
retain their original page numbers. For the factor case the paragraph
parameters are applied inside the paragraph's own group, without framedtext.

The P03/P06 pair tests whether changing an *inactive* penalty field
changes the output. The hypothesis that it should not is a design
question for Hans, not an asserted ConTeXt contract.

The point is to separate the *observed* line breaks from the question of
which precedence rules are correct. The PDF is the primary automated output;
C tracing is optional and only explains the implementation's path.

From the testsuite root, using either normal or instrumented ConTeXt:

```sh
context-testsuite diagnose \
  --case penalty-precedence \
  --context /path/to/result-context-hans/bin/context \
  --output results/diagnostics/penalty-hans \
  --observe-pages
```

In addition to the **unchanged default** `report.json`, `trace.json`,
`stdout.log` and `output.pdf`, this writes `page-observations.json` with a
strict page-to-case mapping and join/split/layout information. Without a
C trace, an entirely classified 6-page PDF is marked `observed` (not
`passed`: no desired penalty semantics have been asserted). An extra or
missing PDF page is an error rather than silently shifting case IDs.

If the instrumented engine is available, add `--trace-mode` to the above
command. This adds `--mode=trace` to ConTeXt, enabling the existing
`CTS-LB` messages via `\tracingparagraphs=2`; it does **not** change the
format of those messages or require tracing for PDF analysis. The existing
`trace.json` then contains those events as before.

A standalone manual run also works:

```sh
/path/to/context --once penalty-precedence.tex
/path/to/context --once --mode=trace penalty-precedence.tex
```

Do not launch the standalone command in the tracked source directory when
collecting results. Prefer `diagnose`, which isolates the workspace.

**Known limitation:** This file is new and has not yet been compiled against
Hans's ConTeXt installation in this environment; check for six rendered
pages. A nonzero C-level factor on P05 is a separate trace-based validity
check. A correct PDF observation alone does not prove that the factor was
used by the engine.
