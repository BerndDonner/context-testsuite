# Math/noautobreak: 12 Ausgangstests

Quelle: `NixOS-Config/pkgs/context/tests/math-nobreak/` (2026-10-27).
Unveränderte Test-Eingaben: `cases.tex`. Die Prüfkriterien wurden in
`math_suites.py` übertragen; `compare.sh` ist ein Kompatibilitätswrapper.
Die ursprüngliche Dokumentation mit ihrer Nix-Integration liegt in
`SOURCE-README.md` und ist **historisch**, nicht die aktuelle Bedienungsanleitung.

## Fachliche Soll-Eigenschaften

| Fall | Soll-Eigenschaft |
| --- | --- |
| C01 | `\math{…}~stelliges` darf nicht getrennt werden |
| C02 | Explizites `\nonbreakablespace` schützt die Wortverbindung |
| C03 | Normales Leerzeichen bleibt potentiell trennbar |
| C04 | `3~stelliges` (Text) bleibt zusammen |
| C05 | Normales Textleerzeichen darf umbrechen |
| C06 | C01 gilt auch mit `\mathsurround=3pt` |
| C07 | Normales Math-Leerzeichen mit `mathsurround` bleibt unverändert |
| C08 | C02 mit `mathsurround` bleibt geschützt |
| C09 | `\penalty10000` wird nicht beeinflusst |
| C10 | `\penalty0` wird nicht beeinflusst |
| C11 | `\thinspace` wird nicht beeinflusst |
| C12 | Satzzeichen mit nachfolgendem Leerzeichen unverändert |

Der ursprüngliche Checker setzt C01/C06 konkret durch, vergleicht C01 mit
C02 und C06 mit C08 und erlaubt zwischen Kandidat und Referenz nur
Änderungen bei C01/C06 (oder überhaupt keine). Die übrigen Soll-Angaben
sind **teils Differenzkontrollen**, keine isolierten vollwertigen Assertions.
Die PDF-Textextraktion für die Bruchdarstellung wird eng normalisiert.
Das ist eine bekannte Grenze; sie wird nicht als umfassender Nachweis verkauft.

Aufruf aus dem Repo: `context-testsuite run --context /pfad/context --suite math-basic`.
Optional `--baseline /pfad/context-upstream` für die Differenzkontrollen.
