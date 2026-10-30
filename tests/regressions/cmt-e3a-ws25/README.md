# CMT (E3A) – 1. Schulaufgabe WS 2025

This fixture is a frozen snapshot of `unterrichts-texte/GBS-CMT/Schulaufgabe001_WS25.tex`
with its local dependencies. `reference.pdf` is the unchanged, four-page
historical PDF supplied for the regression test (LuaMetaTeX, 2025-12-09).
It is **not** regenerated or replaced during a test run.

The source embeds pages 1 and 2 of the Bosch high-pressure-sensor datasheet.
Its original three-page PDF is stored at the exact relative path expected
by `\externalfigure`, together with the header logo and MetaPost include.
Pages 3 and 4 contain the actual examination questions, including an
inline mathematical fraction, units, a table and cross-references.

Run just this case from the repository root:

```sh
context-testsuite run --suite documents \
  --context ../NixOS-Config/result-context-patched/bin/context \
  --case cmt-e3a-ws25
```

See [`../README.md`](../README.md) for the shared Python runner.
Differences from the historical PDF are observations, not automatic failures.
