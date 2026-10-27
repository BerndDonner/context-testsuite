# Unit-/MetaPost-Übersetzbarkeit (keine typografische Assertion)

Aus `unterrichts-texte/tests/units-regression.tex` übernommen;
`include/conventions/units.tex` und
`include/workarounds/lmtx-units-2026.tex` stammen aus demselben
Repository und sind für den Testfall **eingefrorene lokale Kopien**.
So gibt es keine externe Input-Pfad-Abhängigkeit.

Die Zielvorgabe des bisherigen Make-Targets war, dass ein PDF mit Zahlen,
Einheiten und einem MetaPost-`textext` erfolgreich erstellt werden kann.
Ein erfolgreicher Lauf bedeutet **nur** erfolgreiches Kompilieren mit
vorhandenem PDF. Insbesondere Dezimalkomma, Abstände und Einheitenlayout
werden mangels freigegebener Referenz **noch nicht** als korrekt bewertet.

Aufruf: `context-testsuite run --context /pfad/context --suite units-smoke`.
Die experimentellen Stressdokumente befinden sich unter
`../../fixtures/units/archive/` und laufen nur explizit mit `--suite units-stress`.
