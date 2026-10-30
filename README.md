# context-testsuite

Eigenständige Regressionstests für ConTeXt LMTX und ein allgemeiner
PDF-Vergleicher. Die Testsuite verwendet **weder** `NixOS-Config` **noch**
`unterrichts-texte` als Abhängigkeit. Sie nimmt ausführbare ConTeXt-Versionen
und beliebige PDF-Pfade als Parameter entgegen.

Die Testsuite wurde aus früheren Projektarchiven ausgelagert. Hinweise zur
Migration und zur Bereinigung der ursprünglichen Repositories stehen in
[docs/MIGRATION.md](docs/MIGRATION.md).

## Schnellstart

Nach der [Einrichtung](#installation-und-selbsttests) können drei voneinander
unabhängige Funktionen verwendet werden:

```sh
# Zwei beliebige vorhandene PDFs vergleichen (ohne ConTeXt)
context-testsuite pdf compare \
  --reference alt.pdf --candidate neu.pdf --output results/pdf-vergleich

# Historische Schulaufgaben gegen ihre feste Referenz vergleichen (mit ConTeXt)
context-testsuite regression list
context-testsuite regression run --context /pfad/zu/context --case all --output results/dokumente-p1 --zip

# Gezielte Math-Tests mit einer bestimmten ConTeXt-Engine ausführen
context-testsuite run --context /pfad/zu/context --suite math-extended
```

Der freie PDF-Vergleich schreibt seinen HTML-Bericht nach
`results/pdf-vergleich/report.html`. Die CLI gibt dafür einen direkt
kopierbaren `xdg-open`-Befehl aus, öffnet aber keinen Browser automatisch.
Weitere Erläuterungen: [PDF-Vergleich](#zwei-beliebige-pdfs-vergleichen),
[Dokument-Regressionen](#dokument-regressionen-gegen-unveränderte-pdf-referenzen)
und [eingebaute Testfälle](#eingebaute-testfälle).

## Installation und Selbsttests

Mit Nix (Python-DevShell, **ohne** ConTeXt-Installation):

```sh
nix develop
python -m pytest -q
context-testsuite list
context-testsuite --help
context-testsuite regression run --help
```

Ohne Nix (Python >= 3.11; keine Poppler-Abhängigkeit):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
context-testsuite list
```

Die DevShell ist bewusst eine normale, eigenständige `pkgs.mkShell` mit
`pkgs.python3.withPackages`: `python`, `pytest` und `pymupdf` stammen aus
derselben Nix-Python-Umgebung. Die DevShell stellt `${python}/bin` explizit
an den Anfang von `PATH`, damit die CLI nicht versehentlich einen anderen
Python-Interpreter verwendet. Es gibt **keine** zusätzliche
Interpreter-Auswahl per Umgebungsvariable. Der CLI-Starter führt schlicht
`python -m context_testsuite` aus. Auf NixOS verwenden wir für die
Selbsttests bewusst **`python -m pytest`** statt des separat gestarteten
`pytest`: Bei dir hatten beide Aufrufarten verschiedene wirksame
Python-Paketpfade, obwohl ihre Programme im selben Nix-Environment lagen.
PyMuPDF wird über die aktuelle API
`import pymupdf` importiert (nicht über das veraltete `fitz`).

Zur Diagnose bei Python-Pfadproblemen:

```sh
command -v python
python -c 'import sys, pymupdf; print(sys.executable, pymupdf.__doc__.splitlines()[0])'
```

Aus dem Git-Arbeitsbaum geht auch `./bin/context-testsuite` ohne Installation,
sofern Python/PyMuPDF vorhanden sind. Für Math-Tests wird zusätzlich
PyMuPDF benötigt; `nix develop` liefert es mit. Poppler wird nicht benötigt. Für eingebaute
ConTeXt-Tests musst du eine **ausführbare** Engine angeben. Die Python-DevShell
stellt selbst keine bereit.

## Eingebaute Testfälle

```sh
# Alle standardmäßig aktivierten Tests gegen die gewünschte ConTeXt-Version
context-testsuite run --context /pfad/zu/context

# Vollständiger Vergleich mit einer zweiten, z. B. ungepatchten Version
context-testsuite run \
  --baseline ../NixOS-Config/result-context-upstream/bin/context \
  --context ../NixOS-Config/result-context/bin/context \
  --suite all --output results/vergleich-oktober

# Nur die 76 Glue-/Penalty-Fälle
context-testsuite run --context ../NixOS-Config/result-context/bin/context --suite math-extended

# Adversarial-Forschung: große, optionale Testmatrix und reproduzierbare Fälle
context-testsuite run \
  --baseline ../NixOS-Config/result-context-upstream/bin/context \
  --context /pfad/zu/einem-instrumentierten-context \
  --suite math-adversarial --output results/hans-adversarial

# Weitere explizite historische Einheiten-Stressdokumente
context-testsuite run --context ../NixOS-Config/result-context/bin/context --suite units-stress
```

ConTeXt-Ausführbare dürfen auch als `context` aus `PATH` angegeben werden.
Alle Ergebnisse, PDF-Dateien, Logs und `run-report.json` landen unter
`results/run/` (oder `--output`). Die Eingabedateien bleiben unverändert.
Die Gesamtsuite läuft **nur auf ausdrücklichen Aufruf**. Sie ist kein
Build-Hook, kein Nix-Check und nicht Teil eines anderen Repositories.

| Suite | Übernommener Bestand | Tatsächliche Aussage |
| --- | --- | --- |
| `math-basic` | 12 Fälle aus `NixOS-Config` | No-break-Invarianten und Kontrolle unerwarteter Änderungen |
| `math-extended` | 76 Fälle aus `NixOS-Config` | Protected Glue, Penalty `-10000`, kontrollierte Änderungen |
| `math-adversarial` (opt-in) | generierte Parameter-Matrix | **Explorativ**: verdächtige Umbrüche, Hypothesen und vollständige Reproducer; keine automatische Interpretation jedes Unterschieds als Regression |
| `units-smoke` | `units-regression.tex` + beide benötigten Includes | **Nur Kompilierung und gültiges PDF**, keine garantierte Typografiekorrektheit |
| `units-stress` | drei alte Unit-Stressdokumente | **Nur Kompilierung**, explizit opt-in |

`--suite all` enthält `math-basic`, `math-extended` und `units-smoke`.
`units-stress` bleibt wegen der experimentellen historischen Herkunft opt-in.
`math-adversarial` ist eine weitere bewusste, **nicht in `all` enthaltene**
Untersuchung. Sie dokumentiert verifizierbare Grenzbedingungen getrennt von
Fragen zur Priorität von expliziten Math-Penalties und `noautobreak`. Jeder
Verdachtsfall erhält eine eigenständige kleine `.tex`-Datei, PDF-Belege und
Textauszüge. Siehe [Adversarial-README](src/context_testsuite/cases/math/adversarial/README.md).
Insbesondere wird der Verlust einer `\postinlinepenalty=-10000` bei
gewöhnlichem Glue gesondert von `noautobreak`-Prioritätsfragen ausgewiesen
(z. B. A0419). Veränderte Umbrüche gegenüber einer Referenz sind allein
kein Bugnachweis.

**Wichtig zur Referenz:** Wird `--baseline` ausgelassen, laufen die beiden
Math-Vergleichsskripte technisch mit **derselben Kandidatenversion auf beiden
Seiten**. Ihre Verhaltensassertions bleiben aktiv; die Kontrolle *unbeabsichtigter
Änderungen gegenüber einer anderen Engine* entfällt. Für die Entscheidung,
ob ein lokaler Patch noch notwendig ist, stets zwei echte Varianten prüfen.
Ein PASS gegen beide Varianten ist ein Indiz, kein Beweis für die völlige
Entbehrlichkeit eines Patches.

Die originalen Tests mit ihren Erwartungen und bekannten Grenzen stehen in
[math-basic](src/context_testsuite/cases/math/basic/README.md),
[math-extended](src/context_testsuite/cases/math/extended/README.md) und
[units-smoke](src/context_testsuite/cases/units/README.md).

## Echte LMTX-Regression: gepatcht gegen Upstream

Die Python-Selbsttests (`python -m pytest -q`) prüfen **nicht**, ob die
migrierten Math-Tests mit echten ConTeXt-Versionen bestehen. Diese
Validierung muss einmal auf einem Rechner mit den gepinnten Builds
stattfinden, **bevor** die ursprünglichen Math-Tests aus `NixOS-Config`
entfernt werden. Die folgenden Pfade sind nur ein konkretes Beispiel; die
Testsuite kennt das Repository `NixOS-Config` nicht und verlangt lediglich
zwei ausführbare `context`-Dateien.

**1. Beide Versionen bauen** (im Repository `NixOS-Config`):

```sh
nix build .#context-upstream -o result-context-upstream -L
nix build .#context -o result-context -L
```

Das sind die getrennt gepinnten Varianten: `context` ist der gepatchte Standard (2026.10.25-p1), `context-upstream` ein neuerer ungepatchter Vergleichsstand. Ihre
Paket-Build-/Smoke-Tests laufen wie bisher beim Build; die vollständige
`context-testsuite` wird dabei **nicht** gestartet.

**2. Vergleich ausführen** (im Repository `context-testsuite`, nach `nix develop`):

```sh
context-testsuite run \
  --baseline ../NixOS-Config/result-context-upstream/bin/context \
  --context ../NixOS-Config/result-context/bin/context \
  --suite all \
  --output results/lmtx-patch-validation
```

Die relative Pfadangabe setzt voraus, dass die beiden Repositories
nebeneinander liegen. Andernfalls die ausführbaren Dateien mit ihren
absoluten Pfaden angeben. `--baseline` ist **ungepatcht**, `--context`
ist **gepatcht**; ein Vertauschen ändert die Testaussage. Der Exitcode
ist `0`, wenn alle gewählten Suites bestehen, sonst `1`.

**3. Ergebnisse kontrollieren:**

```sh
cat results/lmtx-patch-validation/run-report.json
cat results/lmtx-patch-validation/math-basic/runner.log
cat results/lmtx-patch-validation/math-extended/runner.log
```

Die Berichte enthalten die Prüfresultate und die verwendeten Executable-
Pfade. Bei Fehlschlägen zusätzlich die erzeugten `build.log`-Dateien
unter den jeweiligen `before/`- und `after/`-Ordnern untersuchen.

**4. Optional feststellen, ob Upstream das Sollverhalten schon erfüllt:**

```sh
context-testsuite run \
  --context ../NixOS-Config/result-context-upstream/bin/context \
  --suite math-extended \
  --output results/lmtx-upstream-only
```

Dieser Lauf darf **FAIL** ergeben, solange der Bug im ungepatchten
Upstream vorhanden ist. Ein **PASS** ist ein Hinweis darauf, dass der
Patch möglicherweise unnötig geworden ist, aber noch kein Beweis:
Dann zusätzlich die vollständig ungepatchte Version gegen die übrigen
Testfälle und produktive Dokumente prüfen. Auch wenn ein Patch nicht
mehr sauber auf neue Quellen anwendbar ist, folgt daraus allein nicht,
dass der Fehler behoben wurde.

Erwartungen der alten Math-Suiten sind derzeit absichtlich unverändert:
`math-basic` umfasst 12, `math-extended` 76 Fälle. `units-smoke` prüft
**nur erfolgreiche Kompilierung und PDF-Gültigkeit**, keine visuellen
Sollwerte. Erst nach einem nachweisbar erfolgreichen Vergleich der
Testsuite dürfen die alten Math-Checks im anderen Repository entfernt
werden. Die Testartefakte liegen unter `results/` und sind per
`.gitignore` ausgeschlossen.

## Dokument-Regressionen gegen unveränderte PDF-Referenzen

Jedes direkte Unterverzeichnis von [`tests/regressions/`](tests/regressions/)
wird als Testfall erkannt. Aktuell liegen dort vier Schulaufgaben aus 2025:
Messtechnik, Computergestützte Messtechnik (CMT) sowie zwei
Mathematikarbeiten. Jedes Verzeichnis enthält genau eine `.tex`-Quelle,
`reference.pdf` und eventuell benötigte Assets/Includes.
Weitere Dokumente sind durch Anlegen eines Verzeichnisses sofort testbar,
ohne Registrierung in Python oder Shell-Skripte. Unvollständige Fälle werden
**nicht stillschweigend ignoriert**, sondern als Fehler gemeldet.

```sh
context-testsuite regression list
context-testsuite regression run \
  --context ../NixOS-Config/result-context/bin/context --case all \
  --output results/dokumente-p1 --zip
context-testsuite regression run \
  --context ../NixOS-Config/result-context/bin/context --case messtechnik-ws25 \
  --output results/messtechnik-p1
```

Die Quellen und Referenzen werden nicht modifiziert; nur der Kandidat wird
gebaut. Anders als die gezielten Math-/Diagnostiktests laufen **vollständige
Dokument-Regressionen ohne `--once`**. Damit kann ConTeXt mehrere Durchläufe
für Querverweise, Inhaltsverzeichnisse und weitere Mehrfachlaufdaten selbst
steuern. Die HTML-Vergleiche entstehen in
`<output>/<case>/comparison/report.html`, der Gesamtbericht in
`<output>/regression-report.json`. Ohne `--output` gilt
`results/regression-run` als Standard. **Ein vorhandenes, nicht leeres
Ergebnisverzeichnis wird abgelehnt**, damit sich zwei Durchläufe nicht
vermischen. Für einen weiteren Lauf einen neuen Ordner wählen.

Mit `--zip` entsteht zusätzlich `<output>.zip` (z. B.
`results/dokumente-p1.zip`). Das Offline-Archiv enthält die unveränderten
Referenz-PDFs, neue PDFs soweit erstellt, Quelldateien einschließlich
lokaler Assets, Compiler-Logs, die Vergleichsberichte und Differenzbilder
sowie `regression-report.json` mit Engine-Version und Laufparametern.
Die Archive sind auch bei **Kompilierungs- oder Vergleichsfehlern** verfügbar,
sofern der Lauf regulär einen Bericht schreiben konnte. HOME/TEXMFCACHE und
temporäre Hilfsdateien werden nicht archiviert. Bestehende ZIPs werden
nicht überschrieben. Das ursprüngliche Verzeichnis bleibt zur lokalen
Analyse erhalten. Zur Anzeige erscheint
jeweils eine kopierbare Zeile `xdg-open /absoluter/pfad/report.html`.
Unterschiede (`changed`) sind ein Befund und **kein automatischer FAIL**.
Kompilier-/Vergleichsfehler führen zu Exitcode 2. Details einschließlich
Hinweisen zum Hinzufügen von Tests stehen in
[`tests/regressions/README.md`](tests/regressions/README.md).

Die Dokumentfälle sind bewusst **kein** automatischer Teil von `pytest` oder
`context-testsuite run --suite all`: Sie benötigen eine explizit gewählte
ConTeXt-Engine und dienen der manuellen Layoutanalyse. Die Referenz-PDFs
sind historische Dateien, kein nachweislicher Output der Engine von 2024.

## Befehlsübersicht

`context-testsuite --help` zeigt alle Oberbefehle, Unterbefehle jeweils
`context-testsuite <befehl> --help` (z. B. `regression run --help`).
Die menschenlesbare `context-testsuite list` zeigt eingebaute Suites,
Dokument-Regressionen und Diagnostik-Fälle. `list --json` bleibt für
bestehende Verbraucher unverändert und liefert nur den alten Suite-Katalog.
`regression list` zeigt ausschließlich die Dokumentfälle.

`run --suite all` bedeutet **die drei standardmäßig freigegebenen Suites**
(`math-basic`, `math-extended`, `units-smoke`), nicht die optionalen
Forschungssuites. `math-adversarial` und `units-stress` müssen explizit
gewählt werden. Die Befehle `diagnose`, `metamorphic`, `audit-math` und
`export` haben eigene Hilfen; `export` bleibt der gezielte Math-Reproducer-
Export, `regression run --zip` ist das vollständige Dokument-Review.

## Zwei beliebige PDFs vergleichen

Das ersetzt den bisher in `unterrichts-texte` über `make compare` gestarteten
Vergleich: **kein Make, kein Manifest, kein Export und keine Repository-Kenntnis**.

```sh
context-testsuite pdf compare \
  --reference /pfad/zu/referenz.pdf \
  --candidate /pfad/zu/neu.pdf \
  --output results/blatt1
```

Die CLI gibt einen kopierbaren `xdg-open`-Befehl mit dem absoluten Pfad
zur HTML-Datei aus. Der Browser wird nicht automatisch gestartet.
Alternativ kannst du im Repository direkt Folgendes aufrufen:

```sh
xdg-open results/blatt1/report.html
```

Beispiel mit beliebigen Unterrichtsdateien:

```sh
context-testsuite pdf compare \
  --reference "$HOME/RClone/sabel/Sabel/GBS-Messtechnik/Blatt.pdf" \
  --candidate "$HOME/GitHub/unterrichts-texte/build/GBS-Messtechnik/Blatt.pdf" \
  --output results/messtechnik-blatt
```

Es entstehen `report.html`, `report.json`, bei Bedarf `text.diff` und
markierte PNG-Seiten. Der Vergleich betrachtet Text, Seitengröße und
Rasterbilder und verändert keine Eingabe-PDF. Die Vergleichsauflösung kann
mit `--dpi` (72–300), die Kanal-Toleranz mit `--pixel-threshold` (0–254)
beeinflusst werden. Bei fehlender Referenz wird
`status = baseline_missing` gemeldet, bei fehlendem Kandidaten ein Fehler.

**CHANGED ist ein Befund, kein Testfehler.** Der Befehl liefert auch bei
gefundenen Unterschieden Exitcode 0; echte Verarbeitungsfehler liefern 2.
Eine visuelle Änderung darf nicht automatisch als Layoutregression gelten.
PDF-Text-Extraktion bildet mathematische Formeln nicht immer zuverlässig ab.

## Wie die Tests von den anderen Repositories getrennt sind

- `NixOS-Config` verwaltet Paketierung, Patches und automatische
  Build-/Smoke-Tests. Das Testframework wird dort **nicht eingebunden**.
- `unterrichts-texte` baut und installiert seine Dokumente wie bisher,
  **ohne Abhängigkeit** zur Testsuite. Die perspektivische Entfernung des
  alten `make compare` ist in der Migrationscheckliste beschrieben.
- Für zusätzliche Untersuchungen genügt es, Pfade an diese CLI zu übergeben.
  Exporter, CSV-/JSON-Manifeste und automatische Repo-Suche sind absichtlich
  **nicht implementiert**.

### Wichtig: manueller Carlito-Hosttest

Der Test `NixOS-Config/pkgs/context/tests/check-system-carlito.sh` **bleibt
in NixOS-Config** und darf beim Auslagern der Math-Tests nicht verschwinden.
Er testet die Fontsuche des tatsächlich installierten/wrappenden NixOS
gegen `/run/current-system/sw/share/{X11/fonts,fonts}`. Diese Host-Pfade
sind in einem isolierten Nix-Build nicht zugänglich.

Vom Verzeichnis `NixOS-Config/` aus nach dem Build des gewünschten Pakets:

```sh
pkgs/context/tests/check-system-carlito.sh ./result-context/bin/context
```

Voraussetzung: Carlito muss auf dem Host systemweit vorhanden sein. Der
Test isoliert HOME/Cache und setzt `OSFONTDIR` zurück. **Er wird weder beim
normalen Paketbuild noch mit `context-testsuite run` ausgeführt.**
Der Aufruf gehört zusätzlich gut sichtbar in die README von `NixOS-Config`,
sobald wir dieses Repo im nächsten Migrationsschritt anpassen.

## Grenzen der bisherigen Absicherung

Die Math-Checker sind unverändert migriert, um ihre bewährten Soll-Aussagen
nicht unbemerkt zu verändern. Die 12er-Suite prüft einige Kontrollen nur als
Differenz zur Referenz, und die 76er-Suite erfasst Zeilenumbrüche vor allem
mit dem gemeinsamen PyMuPDF-Observer. Die alten Rohtexte werden nur im
optionalen `audit-math`-Replay als gespeicherte Evidenz gelesen. Die Einheiten-Fälle besitzen noch **keine freigegebenen
typografischen Referenzen**. Die verfügbaren Python-Tests belegen die
Korrektheit des Testcodes für ausgewählte simulierte Fälle, ersetzen aber
keinen echten Durchlauf gegen deine LMTX-Builds.

Ein neues ConTeXt-Release oder einen neuen Patch darf man nicht allein anhand
eines grünen Compiler-Smoke-Tests freigeben. Diese Suite ist deshalb ein
bewusst gestartetes Werkzeug zur umfangreicheren Bewertung.

## Einzelne Testfälle für Hans oder andere Entwickler exportieren

Der Export verwendet **gespeicherte Ergebnisse eines vorhandenen Testlaufs**.
Der Empfänger benötigt weder Nix noch Python noch die Testsuite. Es wird
**kein ConTeXt neu gestartet**; damit lassen sich auch ausgewählte Fälle aus
einem fachlich fehlgeschlagenen `math-extended`-Lauf verschicken.

```sh
context-testsuite export \
  --from results/hans-adversarial-v2 \
  --cases A0419,A0202,A0395 \
  --include-baseline \
  --output hans-tests.zip
```

Das ZIP enthält `README.txt`, `tests.tex` (alle ausgewählten Fälle hintereinander),
`result.pdf` und optional `reference.pdf`. Die Reihenfolge entspricht exakt
`--cases`. Ohne `--include-baseline` wird kein Referenz-PDF aufgenommen.
`--include-baseline` setzt voraus, dass der ursprüngliche Testlauf eine
**explizite** Referenz-Engine hatte (`--baseline`).

Unterstützt werden `math-basic`, `math-extended` und `math-adversarial`.
Innerhalb eines ZIP müssen die gewählten Fälle aus derselben Suite stammen.
Die ZIP-Datei darf noch nicht existieren. Der Export prüft Original-TeX,
PDF-Seitenanzahl und Test-ID auf **jeder** Quellseite. Fehlende, doppelte oder
uneindeutige Zuordnungen führen zu einer Fehlermeldung, nicht zu einem
scheinbar vollständigen Paket.

Die PDFs enthalten die **Originalseiten** des gespeicherten Testlaufs;
`tests.tex` wird aus den damals tatsächlich verwendeten Eingaben neu
zusammengestellt. Ein erneutes Kompilieren des Ausschnitts muss daher nicht
byteidentische PDF-Dateien ergeben. Der Export selbst wertet Unterschiede
nicht als Fehler des Satzsystems.

## Gemeinsamer Math-PDF-Observer

`context_testsuite.math_observer` provides a shared, **PyMuPDF-only** observer
(`observe_pdf`, `MathCase`, `MathObservation`). It checks page IDs and counts,
recognizes a marker even if the paragraph begins on another line, and returns
`unclassifiable` rather than guessing when extraction is ambiguous. It reports
only *what the PDF shows*; the suites retain their separate semantic rules.

All three math suites now use this observer. Historical gates were ported
and verified against the archived output; see `docs/OBSERVER-MIGRATION.md`.
The shared observations are included in schema-2 reports.

Golden test pages and synthetic corner cases cover missing/duplicated markers,
line breaks preceding the marker, hyphenation and words extracted as a single
token. Run `python -m pytest tests/test_math_observer.py` without Poppler.

## Isolated diagnostic runs (migration phase 2)

Run a named standalone `.tex` diagnostic with an **explicit** engine binary;
compilation never happens in the tracked source folder:

```sh
context-testsuite diagnose \
  --case glue-option-entry \
  --context /path/to/instrumented-context/bin/context \
  --output results/diagnostics/glue-2026-10-28
```

The destination must be empty. The command retains `work/source.tex` and the
underlying ConTeXt scratch outputs, `stdout.log`, optionally `context.log`,
`output.pdf`, `trace.json` (including raw `CTS-LB`, `CTS-GLUE`, `CTS-FACTOR`
events), and `report.json`. A separate `HOME` and `TEXMFCACHE` are used. The
process group is killed on timeout (`--timeout`, default 120 seconds).

`observed` means that matching C-level `CTS-LB entry` and `decision` records
were captured, **not** that the implementation is correct. A normal engine
without these markers yields `inconclusive` (exit status 2); compile failures
and timeouts are also errors. The tool neither patches nor builds any engine.
Do not run experiments with redirected output inside `cases/math/diagnostics`.


## Gemeinsame PDF-Auswertung ohne Poppler

Alle produktiven Befehle, einschließlich der `compare.sh`-Kompatibilitätsskripte,
verwenden PyMuPDF. Die normale DevShell enthält kein `poppler-utils` mehr.
`--check-only` liest jetzt `before/cases.pdf` und `after/cases.pdf`.
Die Wrapper benötigen die installierte Python-Anwendung bzw. die DevShell.

Die Umstellung ist an 1734 archivierten PDF-Seiten gegengeprüft; Details,
Abweichungserklärungen und Replay-Befehle: [OBSERVER-MIGRATION.md](docs/OBSERVER-MIGRATION.md).
Das reguläre `python -m pytest -q` braucht weder ConTeXt noch Poppler.
Zwei optionale historische Cross-Checks kann man bei separat installiertem
Poppler mit `CTS_TEST_POPPLER=1 python -m pytest tests/test_pdf_extraction_parity.py -q`
aktivieren. Sie sind kein Laufzeitbestandteil der Testsuite.

## Metamorphe Tests als eigene Auswertung

```bash
context-testsuite metamorphic \
  --from results/hans-design-v4 \
  --output results/hans-metamorphic
```

58 explizite Beziehungen pro Engine prüfen `\relax`, unabhängige erzwungene
Penalty-Nodes und die Hypothese zum inaktiven Glue-Penalty-Feld. Der Befehl
wertet vorhandene adversariale Beobachtungen aus; er erzeugt keine zusätzlichen
ConTeXt-Testfälle. Belastbare Invarianten und Designfragen bleiben getrennt.
Erwartungen, Voraussetzungen, Ergebnisse und Exit-Codes stehen in
[METAMORPHIC.md](docs/METAMORPHIC.md).
