# Metamorphe Auswertung

Eine metamorphe Prüfung beschreibt eine gezielte Änderung am Testinput und
prüft die erwartete Beziehung zwischen beiden Ergebnissen. Referenz und
Kandidat werden **jeweils für sich** bewertet; "wie die Referenz" ist keine
Korrektheitsdefinition.

```bash
context-testsuite metamorphic \
  --from results/hans-design-v4 \
  --output results/hans-metamorphic
```

`--from` akzeptiert den Run-Root, das `math-adversarial`-Verzeichnis oder dessen
`observations.json`. Das neue/leere Ziel liegt außerhalb des Suite-Verzeichnisses.
Alte Reports (Schema 1) und neue PyMuPDF-Reports (Schema 2) funktionieren.
Es wird nichts neu kompiliert oder in alten Ergebnissen überschrieben.

Ausgabe: `metamorphic.json` und `metamorphic.md`, separat von den bisherigen
Einzelfall-Assertions. Beide enthalten Fallnummern, Transformation, Erwartung,
Begründung, Einordnung und Ergebnis **jeder** Beziehung. JSON enthält zusätzlich
die gespeicherten Ausgangs-/Folgebeobachtungen sowie die geprüften Quelldefinitionen.
Die Fälle lassen sich anschließend über den vorhandenen `export`-Befehl bündeln.

## Katalog 1: 58 Beziehungen

| IDs | Anzahl | Transformation | Erwartung | Einordnung |
|---|---:|---|---|---|
| M001–M015 | 15 | `\relax` zwischen vollständig abgeschlossener Math/HBox/Text-Expression und unverändertem Glue einfügen | identische Absatzzeilen und Join/Split-Beobachtung | belastbare Invariante |
| M016–M018 | 3 | Nur `noautobreak` am Glue nach einem separaten expliziten `\penalty-10000` aktivieren | Kontrollfall und transformierter Fall müssen beide umbrechen | belastbare Invariante |
| M019–M058 | 40 | Inaktives Glue-Penalty-Feld von 0 auf -10000, -1, 1, 500 bzw. 10000 ändern; Optionsbits unverändert | identisches Layout, **wenn** das inaktive Feld wirkungslos sein soll | offene Designhypothese |

Der dritte Block umfasst vier Math-Penalties und zwei Glue-Optionen
(`options=0` und `options=1`, jeweils ohne `has_penalty`). Seine Erwartung ist
explizit; ihre Verbindlichkeit ist noch mit Hans zu klären. Eine Verletzung
wird deshalb als `question`, nicht als bewiesener Enginefehler, ausgegeben.

Der Katalog überprüft den tatsächlichen Quellenunterschied. Bei der Auswertung
müssen unter anderem Ausdruck, Setup, Breite, Marker und Glue-Kategorie mit den
vorgesehenen Fällen übereinstimmen. Die alten `pair`-Labels allein genügen nicht.
Fehlende Fälle, unbekannte Beobachtungen und abweichende Quellen machen die
betroffenen Beziehungen `inconclusive`. Zwei gleichermaßen falsche erzwungene
Umbrüche können die `both-split`-Prüfung nicht bestehen.

Ein breiterer Rahmen wird nicht als "muss weniger umbrechen" getestet. Ebenso
wird keine einfache Monotonie der Faktor-/Penalty-Wirkung behauptet: TeX
optimiert den gesamten Absatz, und für den Faktor fehlt eine ausreichend
abgesicherte fachliche Regel. `\kern0pt` ist ein Node und kein Ersatz für
`\relax`; Math, HBox und Text werden nicht pauschal gleichgesetzt.

## Ergebnisse und Exit-Codes

- `pass`: Alle Beziehungen erfüllt; Exit 0.
- `questions`: Mindestens eine Designhypothese verletzt, keine starke
  Verletzung/fehlende Evidenz; Exit 0. Das ist **kein** uneingeschränkter PASS.
- `fail`: Mindestens eine belastbare Invariante verletzt; Exit 1.
- `incomplete`: Mindestens eine Beziehung nicht auswertbar; Exit 2.
  Bereits beobachtete Verletzungen bleiben im Bericht sichtbar.

Ohne angeforderte Referenz werden 58 Kandidatenbeziehungen ausgewertet;
mit Referenz sind es 116. Die Bewertung erfolgt nicht automatisch bei jedem
adversarialen Lauf, sondern bewusst als eigener Auswertungsschritt.

## Gegenprüfung am archivierten Hans-v4-Lauf

| Engine | Erfüllt | Starke Verletzungen | Designfragen | Unklar |
|---|---:|---:|---:|---:|
| Referenz | 58 | 0 | 0 | 0 |
| Hans | 54 | 0 | 4 | 0 |

Die vier Fragen sind M023 (A0586/A0592), M033 (A0598/A0604),
M043 (A0610/A0616) und M053 (A0622/A0628): `options=0`, gespeicherte
Glue-Penalty 0 → 10000, Math-Penalty -10000, -500, 0 bzw. 500.
Der Umbruch wechselt jeweils von getrennt zu verbunden. Das bestätigt die
bereits diskutierte Frage zum inaktiven Feld, es sind nicht vier neue Bugs.

Die dafür benötigten Originalbeobachtungen sind als unveränderter Ausschnitt
in `tests/fixtures/metamorphic/hans-v4-observations.json` festgehalten.
Die Selbsttests prüfen außerdem absichtlich verletzte Invarianten, defekte
Kontrollen, fehlende Fälle, falsche Quellen, unbekannte Referenzen und einen
nur im Kandidaten auftretenden Fehler.
