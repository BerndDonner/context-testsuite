# Schulaufgabe001_WS25: feste PDF-Referenz

Dieser **manuelle, explizit gestartete Regressionstest** vergleicht das
unveränderte `reference.pdf` mit einem frisch kompilierten Kandidaten.
Die Referenz kommt aus der gelieferten `Schulaufgabe001_WS25.pdf` und wird
**niemals** neu mit einer anderen ConTeXt-Version erzeugt.

Die `.tex`-Quelldatei und `assets/sabel.png` wurden aus dem gelieferten
`unterricht01.zip` kopiert und bewusst eingefroren. So ändert eine spätere
Bearbeitung von `unterrichts-texte` nicht stillschweigend die Testeingabe.
Es gibt **keine Abhängigkeit** von `unterrichts-texte` oder `NixOS-Config`.

## Ausführen

Aus dem Wurzelverzeichnis des Repositories `context-testsuite`:

```sh
nix develop
regressions/messtechnik-ws25/run.sh \
  ../NixOS-Config/result-context-patched/bin/context
```

Der Engine-Pfad muss auf deine gewünschte, *tatsächlich gepatchte*
ConTeXt-Ausführbare zeigen. Die Test-Shell installiert selbst keine Engine.
Alternativ kann als zweites Argument ein eigenes Ergebnisverzeichnis
angegeben werden.

### Ergebnisse

* `results/messtechnik-ws25/context-build.log` – Kompilierlog
* `results/messtechnik-ws25/engine-path.txt` – verwendete Engine
* `results/messtechnik-ws25/work/Schulaufgabe001_WS25.pdf` – Kandidat
* `results/messtechnik-ws25/comparison/report.html` – Vergleich mit
  Original, Kandidat und rot markierten Pixelunterschieden
* `results/messtechnik-ws25/comparison/report.json` – Seitenzahl,
  geänderte Seiten, Pixelanteile, Text- und Geometriebefunde
* `results/messtechnik-ws25/comparison/text.diff` – sofern die Textextraktion
  Unterschiede feststellt

Der Vergleich verwendet die **bereits vorhandene** CLI `pdf compare` der
Testsuite (PyMuPDF), ohne deren Python-Code zu ändern. Ein Status `changed`
ist eine Beobachtung, nicht automatisch ein Fehler des Satzsystems. Auch
Schrift-/Fontunterschiede oder geänderte ConTeXt-Versionen jenseits des
Math-Patches können Pixelunterschiede erzeugen.

**Wichtig:** Der PDF-Comparer liefert auch bei `changed` Exitcode 0. Der
Exitcode signalisiert erfolgreiche Auswertung, nicht visuelle Identität.
Fehlerhafte Builds und unlesbare PDFs führen zu Exitcode 2.

Die zum Vergleich verwendete PDF stammt aus dem übergebenen Archiv, nicht
aus einem neu gebauten ConTeXt-2024-Lauf. Ihr PDF-`CreationDate` lautet
2025-11-19; aus diesem Zeitstempel allein folgt keine Aussage über die
verwendete Engine-Revision.
