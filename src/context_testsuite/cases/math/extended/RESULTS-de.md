# Erweiterte Regressionstests zu Math/Glue (2026-10-27)

## Was ich tatsächlich ausgeführt habe

- 74 konkrete TeX-Testfälle in **ConTeXt LMTX 2026.10.25 / LuaMetaTeX 2.11.10** kompiliert, 74-seitiges PDF erstellt.
- Dieselben 74 Fälle in einer isolierten ConTeXt-Kopie mit dem *alten* `usepenalties=true`-Verhalten erneut kompiliert.
- PDF-Textextraktion, Vergleich der Zeilenumbrüche und stichprobenartige Sichtprüfung der gerenderten Seiten.
- 17 geänderte Umbruchentscheidungen: 14 geschützte Fälle und 3 Konfliktfälle mit negativen Math-Penalties.
- Unverändert: 24 normale/unmarkierte Glue-Kontrollen sowie 12 weitere Kontrollfälle (Kerns, explizite Penalties, Boxen etc.).
- Der negative Regressionstest war erfolgreich: Ein Checker gegen die nur mit `usepenalties=true` geänderte Version schlägt absichtlich bei **13** mit Lua erzeugten `noautobreak`-Fällen fehl. Diese benötigen den echten C-Patch.

## Kategorisierung

| Klasse | Fälle | Prüfregel |
| --- | ---: | --- |
| protected | 34 | Nach dem C-Patch darf kein Umbruch direkt nach der Formel auftreten. |
| normal | 24 | Exakt derselbe extrahierte Absatz in beiden Engines. |
| other | 11 | Unverändert, insbesondere explizite Penalties oder zusätzliche Nodes. |
| conflict | 5 | Forcierter negativer Math-Penalty kombiniert mit geschütztem Glue; manuell bewerten. |

Die Tests `X01` bis `X20` kombinieren vier Werte von `\postinlinepenalty` (`-10000`, `0`, `50`, `10000`), beide Zustände des Glue-Optionsflags und Einstellungen von `\mathsurround` bzw. `\mathsurroundmode`. `L01` bis `L16` erzeugen Glue-Nodes über `\directlua` und testen Optionskombinationen mit `noautobreak`, `isspace`, `nondiscardable`, `setdiscardable` und `limit` sowie Glue-Breite 0 und dehnbaren Glue.

## Wichtige semantische Frage

`\postinlinepenalty=-10000` und das unmittelbar folgende `noautobreak`-Glue stellen gegensätzliche Anforderungen. Der vorgeschlagene C-Patch unterdrückt in diesem Fall den durch `end_inline_math` ausgelösten Umbruch. Wir sollten **nicht** voreilig behaupten, dass diese Priorität in allen Fällen richtig ist; ein explizit erzwungener Umbruch könnte Vorrang haben sollen.

## Einschränkung

Die tatsächliche gepatchte C-Engine liegt hier nicht vor; es wäre falsch, die 74 Fälle als erfolgreich *gegen den Patch* zu bezeichnen. Der mitgelieferte Checker muss auf dem Rechner des Nutzers gegen `result-context-unpatched` und `result-context-patched` ausgeführt werden. Die hier mitgelieferten PDFs sind Referenzausgaben, **keine** Ausgaben der neuen C-Engine.

## Erste Auswertung des tatsächlichen C-Patches (NixOS, 2026-10-27)

Der Benutzer hat den erweiterten 74-Fälle-Test mit beiden echten C-Engines
ausgeführt. Dabei sind die beiden nicht bestandenen Fälle **L15** und
**L16** aufgetreten. Die Klassifikation von **L16** als `other` war falsch:
der explizit erzeugte Glue enthält `options=1` (`noautobreak`), also muss
der Fall `protected` sein. L16 wechselt erwartungsgemäß von `split` auf
`join`.

L15 enthält `\penalty-10000` **vor** einem durch `options=1` geschützten
Glue. Der Umbruch vor `stelliges` bleibt laut Checker in beiden Versionen
erhalten (`split -> split`); der Textunterschied ist aber nicht erklärt.
Deshalb bleibt L15 absichtlich als strenger Kontrolltest bestehen, und das
Regression Gate meldet weiterhin einen Fehler, bis beide tatsächlichen
PDF-Seiten verglichen wurden. Die Nix-Buildausgabe enthält keine Kopie dieser
fehlgeschlagenen erweiterten PDFs im mitgelieferten 12-Fälle-Archiv.

## Korrektur nach Prüfung der echten PDFs und der Math-Penalties

Die PDF-Sichtprüfung zeigte, dass die zusätzliche Leerzeile bei `L15`
(nach separatem `\penalty-10000`) mit dem C-Patch entfällt, während
der erzwungene Umbruch bestehen bleibt. Der Test erlaubt ausschließlich
diese Änderung und prüft den übrigen Text weiterhin exakt.

Die fünf bisher als `conflict` bezeichneten Fälle sind keine offenen
Prioritätsentscheidungen mehr: Die ausdrücklich erzwungene Math-Penalty
`-10000` muss einen Umbruch erzeugen, auch wenn der folgende Glue das
`noautobreak`-Flag trägt. Beide Pfade für `end_inline_math` wurden
entsprechend eingeschränkt. Der erweiterte Regressionstest schlägt nun
bei einem verschluckten erzwungenen Math-Umbruch fehl, statt ihn nur
als `REVIEW` auszugeben. Ein erneuter Build mit dem neuen C-Patch ist
für die Bestätigung dieser Verhaltensänderung erforderlich.

### Node-Listen-Kontrolle mit ungepatchtem LMTX 2026.10.25

Mit `\showlists` wurden die beiden Fälle auf Node-Ebene überprüft:

- `P03`: `math[endmath], penalty -10000` ist **eine Eigenschaft des
  Math-Nodes**; unmittelbar danach folgt `glue[userskip], options "1"`.
- `L15`: `math[endmath]` enthält **keine** erzwungene Math-Penalty;
  danach folgen `glue[userskip], options "1"` und ein eigener
  `penalty[userpenalty], amount -10000`.

Die C-Korrektur unterscheidet deshalb ausdrücklich die im Math-Node
hinterlegte erzwungene Penalty von einem bloß möglichen automatischen
Umbruch. Die separate Penalty in `L15` bleibt wirksam.

## Korrektur des P17-Tests: Bedeutung von „short inline math"

Der bisherige P17-Fall verwendete `\postshortinlinepenalty=-10000`, aber
`\math{12345}`. `\showlists` zeigt in LMTX 2026.10.25 für
`\math{12345}` am `math[endmath]` **keine** Penalty. Der Umbruch der
ungepatchten Engine kam deshalb vom impliziten Umbruch vor dem geschützten
Glue, nicht von einer expliziten `-10000`-Penalty.

Dagegen enthält `\math{1}` unter derselben Einstellung ein
`math[endmath]` mit `penalty -10000` und `options "1"` (kurze Formel).
P17 wurde auf diese tatsächlich kurze Formel korrigiert und bleibt ein
verbindlicher erzwungener Umbruchtest. Die neuen Kontrollfälle P19
(lange Formel, geschützter Glue) und P20 (kurze Formel, normales Leerzeichen)
sichern beide Varianten ab. Gesamtumfang jetzt **76 Fälle**.
