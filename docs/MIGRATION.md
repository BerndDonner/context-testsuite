# Herkunft und spätere Bereinigung

## Bereits in dieses Repo übernommen

| Quelle (Stand 2026-10-27) | Hier | Vermerk |
| --- | --- | --- |
| `NixOS-Config/pkgs/context/tests/math-nobreak/{cases.tex,compare.sh}` | `src/context_testsuite/cases/math/basic/` | Originalassertions unverändert |
| `NixOS-Config/pkgs/context/tests/math-nobreak/extended/` | `src/context_testsuite/cases/math/extended/` | 76 Fälle, Generator, JSON und Checker unverändert |
| `unterrichts-texte/scripts/pdf_regression.py` | `src/context_testsuite/pdf.py` | Auf unabhängige Dateipfade umgestellt, HTML/JSON/Text/Pixelvergleich erhalten |
| `unterrichts-texte/tests/test_pdf_regression.py` | `tests/test_pdf_regression.py` | 9 Assertions und Untertests erhalten |
| `unterrichts-texte/tests/units-regression.tex` | `src/context_testsuite/cases/units/` | Benötigte Includes eingefroren; **nur Compile-Smoke** |
| `unterrichts-texte/tests/archive/*.tex` | `src/context_testsuite/fixtures/units/archive/` | Experimentaldateien, ohne erfundene Typografiesollwerte |

Originaldokumentationen der beiden Math-Suites wurden als
`SOURCE-README.md` archiviert, um die Testbegründungen zu bewahren. Die dort
genannten Nix-Check- und Pfadbefehle sind **nicht mehr aktuell**.
`RESULTS-de.md` ist ein historischer Untersuchungsbericht, keine aktuelle
Testausführung. Die C-Patches gehören weiterhin nach `NixOS-Config`, nicht
in die Testsuite.

## Wichtig: Die beiden Quell-Repositories sind noch unverändert

Wir verändern `NixOS-Config` und `unterrichts-texte` erst, **nachdem** die
regressionstypischen Math-Tests mit einer echten upstream/patched-Paarung
und der PDF-Vergleicher nach der Migration überprüft wurden.

### In `NixOS-Config` später

- Math-Regressionen/deren `checks` entfernen und auf dieses Repo verweisen.
- Die Build-/Smoke-Tests **behalten**: `smoke.tex`, `filter.tex`, `vim.tex`,
  Native-/Portable-Cache-Lock, `check-system-carlito.sh` samt `.tex`.
- Die README entsprechend der Realität korrigieren: kein globales
  `contextLmtx`/Home-Manager-Paket behaupten, wenn ConTeXt nur aus
  DevShells genutzt wird.
- `check-system-carlito.sh` **in der README deutlich aufführen** – mit
  Kommando, Zweck, Hostvoraussetzungen und dem Hinweis, dass dies ein
  MANUELLER Integrationstest ist. Keine automatische Bindung an Build-Checks.
- `flake.lock` und Patches für längerfristig produktive Stände pinnen;
  Upstream-/Patchvarianten erhalten, damit die vollständige Testsuite
  später gezielt beide prüfen kann.

### In `unterrichts-texte` später

- Die **Default-DevShell** verwendet die gepatchte Version der gepinnten
  ConTeXt-Derivation; keine systemweite ConTeXt-Installation.
- `make compare`, `scripts/pdf_regression.py`, deren Python-Unittests und
  die migrierten Testfixtures erst nach nachgewiesener Parität entfernen.
- `make install` bleibt davon unabhängig und soll weiter funktionieren.
- Dokumentation über DevShell, Includes und Tests korrekt nachführen.
- **Keine** Abhängigkeit auf `context-testsuite` hinzufügen. PDF-Pfade gibt
  der Benutzer bei Bedarf manuell an.

## Validierung dieser ersten Lieferung

- 12 Math-Ausgangsfälle und 76 erweiterte Math-Fälle sind enthalten.
- Ein Generator-Check verifiziert die 76-fache Quelldaten/TeX-Konsistenz.
- Der 76er-Checker wurde mit künstlichen Seiten auf echten PASS und
  absichtliche FAIL (geschützte Verbindung / erzwungene Penalty) geprüft.
- Alle 9 alten Unittests des PDF-Vergleichers sowie zusätzliche CLI-Tests
  laufen erfolgreich in der bereitgestellten Python-Umgebung.
- Ein vollständiger ConTeXt-Testlauf und `nix develop` konnten hier **nicht**
  ausgeführt werden, da im Ausführungscontainer `context` bzw. `nix`
  nicht verfügbar waren. Dazu ist dein NixOS-Host erforderlich.
