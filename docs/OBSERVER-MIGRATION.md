# Gemeinsame Math-Auswertung (Schritte 3–4)

`math-basic`, `math-extended` und `math-adversarial` verwenden jetzt
`math_observer.observe_pdf`. Beobachtung und suite-spezifische Erwartungen
bleiben getrennt. Kein erfolgreicher Prozess ohne frisches PDF und keine
unlesbare Referenz können einen erfolgreichen Test vortäuschen.

## Was sich technisch geändert hat

- Zahlenmarker: PyMuPDF statt `pdftotext -layout`; Marker dürfen auf einer
  späteren Zeile als der Absatzanfang stehen. Fehlende Marker/Folgetexte
  ergeben `incomplete` (Exit 2), keinen erfundenen Zeilenumbruch.
- Basic-Bruch `3 1/2`: Die Glyphenbaselines bestimmen die Textzeilen.
  Zähler, Bruchstrich und Nenner werden geometrisch geprüft und als `<MATH>`
  normalisiert. Andere/unvollständige Brüche sind nicht stillschweigend gültig.
- Layoutvergleich: Nur horizontale Extraktor-Whitespace-Unterschiede werden
  ignoriert. Zeileninhalt, Trennstriche und Leerzeilen bleiben relevant.
  Bei Brüchen werden zusätzlich relative Baseline-Abstände verglichen.
  Die spezielle erste `stel-`-Zeile in C01/C06 und die Gleichheit mit C02/C08
  bleiben verpflichtend. Dies ist kein allgemeiner Abstand-/Typografietest.
- L15 darf weiterhin genau eine zusätzliche Leerzeile verlieren, aber keine
  weiteren Änderungen. Die fünf alten `conflict`-Assertions bleiben erhalten;
  sie dokumentieren den bisherigen Vertrag, keine inzwischen geklärte
  Prioritätsentscheidung von Hans.
- Basic/Extended schreiben `checks.json`, Adversarial weiterhin
  `observations.json`, `findings.json` und Repros. JSON-Schema nun 2;
  bestehende Kernfelder bleiben bestehen, Beobachtungen kommen hinzu.
  `cases.txt` wird produktiv nicht mehr erzeugt. Export nutzt weiterhin
  die gespeicherten Quellen und PDFs. Alle Compiler verwenden den begrenzten
  Prozessrunner mit getrennten Arbeits- und Cacheverzeichnissen.

## Vollständige Gegenprüfung an gespeicherten Läufen

Keine Engine wurde dafür neu gebaut oder ausgeführt.

| Archiv | Fälle pro Engine | Seiten geprüft | Join/Split + Zeileninhalt |
|---|---:|---:|---|
| math-nobreak-results(1).zip | 12 | 24 | 24 gleich |
| hans-extended.zip | 76 | 152 | 152 gleich |
| hans-design-v4(1).zip | 779 | 1558 | 1558 gleich |
| Gesamt | 867 | 1734 | 1734 gleich |

Basic: unverändert PASS, Änderungen nur C01/C06.
Extended: exakt dieselben sechs Fehler P03, P15, P17, P20, X02, X10;
alle 76 `changed`/`before_join`/`after_join`/`error`-Werte identisch.
Adversarial: alle 779 Flag-Listen identisch, darunter 247 geänderte
Join/Split-Entscheidungen, 57 Prioritätsfragen bei geschütztem Glue und 29
bei ungeschütztem Glue. Keine neue starke Verletzung und keine unklaren Seiten.

Die Rohtexte unterscheiden sich stellenweise durch eingerückte/zusätzliche
Leerzeichen. PyMuPDF sortiert bei C01 den Nenner sogar hinter `stel-`;
der geometrische Bruch-Observer löst diese Extraktionsabweichung auf.
Keine abweichende fachliche Bewertung wurde als "harmlos" ausgenommen.

## Selbst nachprüfen, ohne Engines oder Poppler

`--from` bezeichnet jeweils das **Suite-Verzeichnis**, nicht den Run-Root.
Die alten Dateien werden ausschließlich gelesen. Das Ziel muss neu/leer und
außerhalb dieses Verzeichnisses liegen.

```bash
context-testsuite audit-math --suite math-basic \
  --from /pfad/math-nobreak-results --output results/audit-basic
context-testsuite audit-math --suite math-extended \
  --from /pfad/hans-extended/math-extended --output results/audit-extended
context-testsuite audit-math --suite math-adversarial \
  --from /pfad/hans-design-v4/math-adversarial --output results/audit-adversarial
```

`observer-audit.json` enthält alte/neue Beobachtungen, eine Erklärung pro
Vergleich und (adversarial) alte/neue Flag-Listen. Exit 0 = Auswertungen gleich,
1 = Abweichung, 2 = unvollständige Evidenz. Ein Audit-Exit 0 bedeutet **nicht**,
dass die untersuchte Engine die fachlichen Tests besteht (siehe Extended).

Basic/Extended müssen exakt zu den eingefrorenen Quellen passen.
Adversarial verwendet die gespeicherten Definitionen und PDF/TeX-Zuordnungen,
nicht die aktuelle Probe-Generierung. Fehlende/mehrdeutige Quellen werden
abgewiesen. Der Replay-Bericht ersetzt keinen neuen Lauf mit künftigen Engines.
