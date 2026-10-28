# Erweiterte Math-Penalty-/Glue-Regressionen (76 Fälle)

Quelle: `NixOS-Config/pkgs/context/tests/math-nobreak/extended/`
(2026-10-27). `cases.json` und `cases.tex` sind unverändert. Die bisherigen
Prüfkriterien liegen nun in `math_suites.py`; `compare.sh` und `check.py`
sind Kompatibilitätswrapper für die PDF-Auswertung. In `SOURCE-README.md` und `RESULTS-de.md` stehen die
historischen Untersuchungsergebnisse und teils überholte Aufrufpfade;
**die aktuelle Bedienungsanleitung ist die Repo-README**.

Verteilung: 35 `protected`, 25 `normal`, 11 `other`, 5 `conflict`.

- `protected`: Kandidat darf die geschützte Verbindung nicht auftrennen;
  dazu zählen direkte Glue-Nodes mit `noautobreak`, auch bei `mathsurround`.
- `normal`: Kandidat und Vergleichsversion müssen unveränderten Text liefern.
- `other`: ebenfalls unverändert, **außer L15**. Die explizite
  `\penalty-10000` muss brechen; genau eine zusätzliche Leerzeile der
  fehlerhaften Referenz darf verschwinden, sonst nichts.
- `conflict`: fünf absichtlich gegensätzliche Konstrukte; **der explizite
  erzwungene Math-Umbruch hat gemäß bisherigem Testvertrag Vorrang vor
  `noautobreak`** (von Hans noch nicht bestätigte Designannahme). P03, P15, P17,
  X02 und X10 müssen getrennt bleiben.

Besonders wichtig: **P17 testet mit `\math{1}` tatsächlich kurze
Inline-Mathematik**, also `\postshortinlinepenalty`. Der ursprüngliche
längere Fixture war ein Testfehler und wurde vor dieser Migration korrigiert.

`gen.py --check` überprüft, dass der eingecheckte TeX-Fixture mit den
76 Fallbeschreibungen übereinstimmt. `check.py` validiert vor allem den
Zeilenumbruch mit dem gemeinsamen PyMuPDF-Observer; Text-/Pixel-Änderungen des übrigen
Layouts werden nicht vollständig geprüft. Mit `--baseline` lassen sich
zusätzliche unbeabsichtigte Änderungen erkennen.

Aufruf: `context-testsuite run --context /pfad/context --suite math-extended`.
