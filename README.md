# context-testsuite

Eigenständige Regressionstests für ConTeXt LMTX und ein allgemeiner
PDF-Vergleicher. Die Testsuite verwendet **weder** `NixOS-Config` **noch**
`unterrichts-texte` als Abhängigkeit. Sie nimmt ausführbare ConTeXt-Versionen
und beliebige PDF-Pfade als Parameter entgegen.

Stand der Migration: 27. Oktober 2026. Die vorhandenen Tests und ihre
Soll-Aussagen wurden aus den beiden Projektarchiven übernommen; die
Original-Repositories wurden **noch nicht verändert**. Hinweise zur späteren
Bereinigung stehen in [docs/MIGRATION.md](docs/MIGRATION.md).

## Start

Mit Nix (Python-DevShell, **ohne** ConTeXt-Installation):

```sh
nix flake lock               # einmalig; flake.lock anschließend committen
nix develop
pytest -q
context-testsuite list
```

Ohne Nix (Python >= 3.11, `pdftotext` für Math-Tests separat installieren):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
context-testsuite list
```

Aus dem Git-Arbeitsbaum geht auch `./bin/context-testsuite` ohne Installation,
sofern Python/PyMuPDF vorhanden sind. Für Math-Tests wird zusätzlich
`pdftotext` (Poppler) benötigt; `nix develop` liefert es mit. Für eingebaute
ConTeXt-Tests musst du eine **ausführbare** Engine angeben. Die Python-DevShell
stellt selbst keine bereit.

## Eingebaute Testfälle

```sh
# Alle standardmäßig aktivierten Tests gegen die gewünschte ConTeXt-Version
context-testsuite run --context /pfad/zu/context

# Vollständiger Vergleich mit einer zweiten, z. B. ungepatchten Version
context-testsuite run \
  --baseline /pfad/context-upstream \
  --context /pfad/context-patched \
  --suite all --output results/vergleich-oktober

# Nur die 76 Glue-/Penalty-Fälle
context-testsuite run --context /pfad/context-patched --suite math-extended

# Weitere explizite historische Einheiten-Stressdokumente
context-testsuite run --context /pfad/context-patched --suite units-stress
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
| `units-smoke` | `units-regression.tex` + beide benötigten Includes | **Nur Kompilierung und gültiges PDF**, keine garantierte Typografiekorrektheit |
| `units-stress` | drei alte Unit-Stressdokumente | **Nur Kompilierung**, explizit opt-in |

`--suite all` enthält `math-basic`, `math-extended` und `units-smoke`.
`units-stress` bleibt wegen der experimentellen historischen Herkunft opt-in.

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

## Spontan zwei PDFs vergleichen

Das ersetzt den bisher in `unterrichts-texte` über `make compare` gestarteten
Vergleich: **kein Make, kein Manifest, kein Export und keine Repository-Kenntnis**.

```sh
context-testsuite pdf compare \
  --reference /pfad/zu/referenz.pdf \
  --candidate /pfad/zu/neu.pdf \
  --output results/blatt1
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
pkgs/context/tests/check-system-carlito.sh ./result-context-patched/bin/context
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
mit `pdftotext -layout`. Die Einheiten-Fälle besitzen noch **keine freigegebenen
typografischen Referenzen**. Die verfügbaren Python-Tests belegen die
Korrektheit des Testcodes für ausgewählte simulierte Fälle, ersetzen aber
keinen echten Durchlauf gegen deine LMTX-Builds.

Ein neues ConTeXt-Release oder einen neuen Patch darf man nicht allein anhand
eines grünen Compiler-Smoke-Tests freigeben. Diese Suite ist deshalb ein
bewusst gestartetes Werkzeug zur umfangreicheren Bewertung.
