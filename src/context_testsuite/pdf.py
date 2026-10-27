#!/usr/bin/env python3
"""Compare PDFs by text, page geometry and pixels; emit HTML/JSON reports.

The comparator neither builds nor installs files. Requires PyMuPDF.
"""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import os
import sys
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone

try:
    import fitz
except ImportError:
    sys.exit(
        "Fehler: PyMuPDF fehlt. Starte die angepasste Nix-DevShell "
        "(flake.nix) oder installiere das Python-Paket 'pymupdf'."
    )


def pdf_relpath(raw: str) -> PurePosixPath:
    """PDF is always relative to the repository's build/ or install root."""
    if not raw or "\\" in raw or "\x00" in raw:
        raise ValueError("PDF muss ein nichtleerer, relativer POSIX-Pfad sein")
    path = PurePosixPath(raw)
    if (path.is_absolute() or path.suffix != ".pdf"
            or any(part in ("", ".", "..") for part in raw.split("/"))):
        raise ValueError("PDF muss ein relativer .pdf-Pfad ohne . oder .. sein")
    return path


def contained_path(root: Path, rel: PurePosixPath) -> Path:
    root = root.expanduser().resolve()
    dest = root.joinpath(*rel.parts).resolve()
    if not dest.is_relative_to(root):
        raise ValueError(f"Pfad verlaesst Basisverzeichnis: {dest}")
    return dest


def sha256(path: Path) -> str:
    hash_obj = hashlib.sha256()
    with path.open("rb") as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            hash_obj.update(block)
    return hash_obj.hexdigest()


def rect_props(page: fitz.Page) -> dict:
    r = page.rect
    return {
        "width_pt": round(r.width, 3),
        "height_pt": round(r.height, 3),
        "rotation": page.rotation,
    }


def pixels_diff(before: fitz.Pixmap, after: fitz.Pixmap, threshold: int):
    """Return changed pixel count and a change mask. RGB, alpha=False."""
    if (before.width, before.height) != (after.width, after.height):
        return None, None
    old = before.samples
    new = after.samples
    if old == new:
        return 0, None

    changed = 0
    mask = bytearray(len(new))  # only materialized for actually differing pages
    for i in range(0, len(new), 3):
        if (abs(old[i] - new[i]) > threshold or
                abs(old[i + 1] - new[i + 1]) > threshold or
                abs(old[i + 2] - new[i + 2]) > threshold):
            changed += 1
            mask[i:i + 3] = b"\xff\x30\x30"  # strong red
        else:
            # Lighten the current page to provide a visible location context.
            mask[i] = (new[i] + 255 * 3) // 4
            mask[i + 1] = (new[i + 1] + 255 * 3) // 4
            mask[i + 2] = (new[i + 2] + 255 * 3) // 4
    return changed, mask


def emit_html(data: dict, folder: Path) -> None:
    esc = lambda s: html.escape(str(s), quote=True)
    summary = data["summary"]
    status = data["status"]
    rows = [
        '<!doctype html><html lang="de"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>PDF-Vergleich</title><style>',
        'body{font-family:system-ui,sans-serif;max-width:1350px;margin:2em auto;padding:0 1.2em;line-height:1.5}',
        'h1,h2{line-height:1.2}.meta{color:#555}.notice{border-left:4px solid #be6f00;padding:.5em 1em;background:#fff6e5}',
        '.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1em}',
        '.grid>figure{margin:0;min-width:0}.grid img{max-width:100%;border:1px solid #ccc}',
        'figcaption{font-weight:600;margin:.4em 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:1em}',
        '@media(max-width:750px){.grid{grid-template-columns:1fr}}',
        '</style></head><body>',
        '<h1>PDF-Vergleich</h1>',
        f'<p><strong>Status:</strong> {esc(status.upper())} · {esc(data["pdf"])}<br>',
        f'<span class="meta">Erstellt (UTC): {esc(data["created_utc"])}</span></p>',
        '<p class="notice"><strong>Wichtig:</strong> Unterschied bedeutet nicht automatisch Regression. '
        'Der Vergleich ersetzt keine fachliche oder visuelle Freigabe. '
        'Text aus Formeln, Vektorgrafiken und Bildern kann bei Textextraktion fehlen.</p>',
        f'<p><strong>Referenz:</strong> <code>{esc(data["baseline"]["path"])}</code><br>',
        f'<strong>Build:</strong> <code>{esc(data["build"]["path"])}</code></p>',
    ]
    if status == "baseline_missing":
        rows.append("<h2>Keine Referenz vorhanden</h2><p>Keine Referenz vorhanden: "
                    "Es ist kein Vergleich mit einer bisherigen Fassung moeglich.</p>")
    else:
        rows.append(
            f'<p><strong>Seiten:</strong> {summary["baseline_pages"]} → {summary["build_pages"]} · '
            f'<strong>Seiten mit Texthinweisen:</strong> {summary["pages_text_changed"]} · '
            f'<strong>Seiten mit sichtbaren Änderungen:</strong> {summary["pages_visual_changed"]} · '
            f'<strong>Geometrieänderungen:</strong> {summary["pages_geometry_changed"]}</p>'
        )
        for p in data["pages"]:
            if not any((p["text_changed"], p["visual_changed"], p["geometry_changed"], p["missing_side"])):
                continue
            rows.append(f'<section><hr><h2>Seite {p["number"]}</h2><p>')
            if p["missing_side"]:
                rows.append(f'Fehlt in {esc(p["missing_side"])}. ')
            if p["geometry_changed"]:
                rows.append('Seitengröße/Rotation unterschiedlich. ')
            if p["text_changed"]:
                rows.append('Extrahierter Text unterschiedlich. ')
            if p["visual_changed"]:
                frac = p["changed_pixels_ratio"]
                rows.append(f'Pixeldifferenz: {frac:.3%}. ' if frac is not None else 'Rendering unterschiedlich. ')
            rows.append('</p><div class="grid">')
            for key, label in (("baseline_image", "Referenz"), ("build_image", "Kandidat"), ("diff_image", "Markierte Differenzen")):
                if p.get(key):
                    rows.append(f'<figure><figcaption>{label}</figcaption><a href="{esc(p[key])}"><img loading="lazy" src="{esc(p[key])}" alt="{label}"></a></figure>')
            rows.append('</div></section>')
        if summary["pages_text_changed"]:
            rows.append('<h2>Textunterschiede</h2><p>Der vollständige Unified Diff liegt in '
                        '<a href="text.diff">text.diff</a>.</p>')
    rows.append('<p class="meta">Daten für weitere Auswertung: <a href="report.json">report.json</a>. '
                'Nur Analyse: kein Build und keine Änderungen an den Eingabedateien.</p></body></html>')
    (folder / "report.html").write_text("\n".join(rows), encoding="utf-8")


def compare(pdf: PurePosixPath, build_root: Path, baseline_root: Path,
            output_root: Path, dpi: int, threshold: int) -> tuple[dict, Path]:
    build = contained_path(build_root, pdf)
    baseline = contained_path(baseline_root, pdf)
    output_rel = PurePosixPath(*pdf.parts[:-1], pdf.stem)
    folder = contained_path(output_root, output_rel)
    return compare_files(baseline, build, folder, dpi, threshold, label=pdf.as_posix())


def compare_files(baseline: Path, build: Path, folder: Path, dpi: int,
                  threshold: int, *, label: str | None = None) -> tuple[dict, Path]:
    """Compare two explicit PDF paths. Write reports to exactly ``folder``.

    The reference may not exist (status ``baseline_missing``); the candidate
    must exist. A changed PDF is a finding, not automatically a failed test.
    """
    baseline, build, folder = (p.expanduser().resolve() for p in (baseline, build, folder))
    if folder in (baseline, build):
        raise ValueError("Der Ausgabeordner darf keine PDF-Datei sein")
    if not build.is_file():
        raise FileNotFoundError(f"Build-PDF fehlt: {build}")
    if not os.access(build, os.R_OK):
        raise PermissionError(f"Build-PDF nicht lesbar: {build}")

    # Check both PDFs before invalidating any previous report. Corrupt PDFs
    # should not destroy a useful report from an earlier run.
    for candidate in (build, baseline):
        if candidate == baseline and not baseline.is_file():
            continue
        with fitz.open(candidate) as checked:
            if checked.needs_pass:
                raise ValueError(f"PDF ist passwortgeschuetzt: {candidate}")

    # A repeated comparison must not leave stale images or a stale text.diff.
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        if old.is_file() and (old.name in ("report.html", "report.json", "text.diff")
                               or (old.name.startswith("page-") and old.suffix == ".png")):
            old.unlink()

    data = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pdf": label if label is not None else build.name,
        "settings": {"dpi": dpi, "pixel_threshold_rgb": threshold,
                     "comparison": "page-by-page, index-aligned"},
        "build": {"path": str(build), "sha256": sha256(build)},
        "baseline": {"path": str(baseline), "sha256": None},
        "status": "baseline_missing",
        "pages": [],
        "summary": {"baseline_pages": 0, "build_pages": 0,
                    "pages_text_changed": 0, "pages_visual_changed": 0,
                    "pages_geometry_changed": 0},
    }
    if not baseline.is_file():
        # Still check the new document is a valid PDF.
        with fitz.open(build) as doc:
            if doc.needs_pass:
                raise ValueError("Build-PDF ist passwortgeschuetzt")
            data["summary"]["build_pages"] = len(doc)
        emit_html(data, folder)
        (folder / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return data, folder

    data["baseline"]["sha256"] = sha256(baseline)
    with fitz.open(baseline) as old_doc, fitz.open(build) as new_doc:
        if old_doc.needs_pass or new_doc.needs_pass:
            raise ValueError("Mindestens eines der PDFs ist passwortgeschuetzt")
        old_count, new_count = len(old_doc), len(new_doc)
        data["summary"]["baseline_pages"] = old_count
        data["summary"]["build_pages"] = new_count
        text_diff = []
        for num in range(max(old_count, new_count)):
            old_page = old_doc[num] if num < old_count else None
            new_page = new_doc[num] if num < new_count else None
            props_old = rect_props(old_page) if old_page else None
            props_new = rect_props(new_page) if new_page else None
            geometry_changed = props_old != props_new
            old_text = old_page.get_text("text", sort=True) if old_page else ""
            new_text = new_page.get_text("text", sort=True) if new_page else ""
            text_changed = old_text != new_text
            if text_changed:
                text_diff.extend(difflib.unified_diff(
                    old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                    fromfile=f"referenz/Seite-{num+1}", tofile=f"kandidat/Seite-{num+1}"))
            old_pix = old_page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False) if old_page else None
            new_pix = new_page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False) if new_page else None
            pix_changed = None
            diff_samples = None
            if old_pix and new_pix:
                pix_changed, diff_samples = pixels_diff(old_pix, new_pix, threshold)
            visual_changed = (old_pix is None or new_pix is None or pix_changed is None or pix_changed > 0)
            denom = old_pix.width * old_pix.height if old_pix and new_pix and pix_changed is not None else 0
            entry = {
                "number": num + 1, "baseline_geometry": props_old, "build_geometry": props_new,
                "missing_side": "Referenz" if old_page is None else ("Build" if new_page is None else None),
                "geometry_changed": geometry_changed,
                "text_changed": text_changed,
                "visual_changed": visual_changed,
                "changed_pixels": pix_changed,
                "changed_pixels_ratio": round(pix_changed / denom, 8) if denom else None,
                "baseline_image": None, "build_image": None, "diff_image": None,
            }
            if visual_changed or text_changed or geometry_changed:
                for pix, attr, suffix in ((old_pix, "baseline_image", "installed"),
                                          (new_pix, "build_image", "built")):
                    if pix:
                        name = f"page-{num+1:03d}-{suffix}.png"
                        pix.save(folder / name)
                        entry[attr] = name
                if diff_samples is not None and pix_changed:
                    name = f"page-{num+1:03d}-diff.png"
                    fitz.Pixmap(fitz.csRGB, old_pix.width, old_pix.height, diff_samples, False).save(folder / name)
                    entry["diff_image"] = name
            data["summary"]["pages_text_changed"] += int(text_changed)
            data["summary"]["pages_visual_changed"] += int(visual_changed)
            data["summary"]["pages_geometry_changed"] += int(geometry_changed)
            data["pages"].append(entry)
        if text_diff:
            (folder / "text.diff").write_text("".join(text_diff), encoding="utf-8")

    s = data["summary"]
    data["status"] = "changed" if (
        s["baseline_pages"] != s["build_pages"] or
        s["pages_text_changed"] or s["pages_visual_changed"] or
        s["pages_geometry_changed"]
    ) else "identical"
    emit_html(data, folder)
    (folder / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data, folder


