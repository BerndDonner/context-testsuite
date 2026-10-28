# Frozen pre-migration evidence

Copied without recompilation from the user's original engine runs:

- `basic/`: `math-nobreak-results(1).zip`, 2026-10-27, original upstream vs.
  the original noautobreak fix; 12 pages per engine.
- `extended/`: `hans-extended.zip`, 2026-10-28, original upstream vs. Hans's
  proposed helper; 76 pages per engine. The original `checks.json` contains
  six failures (P03, P15, P17, P20, X02, X10). These remain failures.

Each side contains its actual `cases.tex`, `cases.pdf` and saved Poppler
`cases.txt`. They are test fixtures, not generated build debris.
The regression test replays all 176 pages without ConTeXt or Poppler.
It compares line membership, contents (including hyphenation/empty lines),
change gates and the original extended verdicts.

The existing `../pdf-extraction/` corpus adds 16 real adversarial pages.
The full 779-case replay is documented in `docs/OBSERVER-MIGRATION.md`;
it is deliberately not duplicated as a large corpus here.
