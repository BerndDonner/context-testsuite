"""Read-only replay of archived Poppler observations against the shared observer.

No engine or pdftotext is run. The archived cases.txt / observations.json are
required evidence; this command never regenerates an alleged old result.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

from .export import _index
from .math_observer import canonical_layout, observe_pdf
from .math_suites import ROOT, definitions, descriptors, check_pdfs


def _old_fixed(root: Path, suite: str, side: str, cases: list[dict]) -> list[dict]:
    chunks = [s for s in (root / side / 'cases.txt').read_text(encoding='utf-8').split('\f') if s.strip()]
    if len(chunks) != len(cases):
        raise ValueError(f'Archived text page count mismatch: {side}')
    rows = []
    for c, chunk in zip(cases, chunks):
        if not re.search(rf"\b{re.escape(c['id'])}\b", chunk):
            raise ValueError(f"Archived text page ID mismatch: {c['id']}")
        lines = chunk.splitlines()
        starts = [i for i, line in enumerate(lines) if 'Das digitale Geraet' in line]
        if len(starts) != 1:
            raise ValueError(f"Archived body not uniquely recognized: {c['id']}")
        body = '\n'.join(lines[starts[0]:]).strip()
        if c.get('fraction'):
            variants = ('3 1⁄2', '3 ⁄12')
            if sum(body.count(v) for v in variants) != 1:
                raise ValueError(f"Unknown archived fraction encoding: {c['id']}")
            for variant in variants:
                body = body.replace(variant, '<MATH>')
            marker = '<MATH>'
        else:
            marker = c.get('marker', '12345')
        # Reproduce the archived fixed suites' first-body-line restriction.
        first = body.splitlines()[0]
        if marker not in first:
            raise ValueError(f"Legacy observer cannot locate marker on first line: {c['id']}")
        joined = bool(re.match(r'\s*ste', first.split(marker, 1)[1]))
        rows.append({'case_id': c['id'], 'status': 'observed', 'joined': joined, 'body': body})
    return rows


def _compare(case_id: str, side: str, old: dict | None, new: dict | None) -> dict:
    record = {'id': case_id, 'side': side, 'old': old, 'new': new}
    if old is None or new is None or old.get('status') != 'observed' or new.get('status') != 'observed':
        return {**record, 'status': 'incomplete', 'explanation': 'Missing or unclassifiable observation'}
    if old['joined'] != new['joined']:
        return {**record, 'status': 'different', 'explanation': 'Join/split disagreement; inspect PDF'}
    if canonical_layout(old['body']) != tuple(new['layout']):
        return {**record, 'status': 'different', 'explanation': 'Line contents or blank lines disagree; inspect PDF'}
    explanation = ('Same line contents; horizontal extractor whitespace normalized'
                   if old['body'] != new['body'] else 'Same observation')
    return {**record, 'status': 'agree', 'explanation': explanation}


def audit(suite: str, root: Path, output: Path) -> dict:
    root, output = root.expanduser().resolve(), output.expanduser().resolve()
    if output == root or root in output.parents:
        raise ValueError('Audit output must be outside the archived suite directory')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Audit output must be new or empty')
    rows = []
    checks = None
    flag_comparisons = []
    if suite == 'math-adversarial':
        original = json.loads((root / 'observations.json').read_text(encoding='utf-8'))
        if original.get('observer') == 'pymupdf':
            raise ValueError('Need an old Poppler run, not a new observer run')
        # Exact saved definitions and sources, never today's generated probes.
        cases = [row['case'] for row in original['cases']]
        if not cases or len({c['id'] for c in cases}) != len(cases):
            raise ValueError('Archived case list is empty or ambiguous')
        for side in ('candidate', 'baseline'):
            if side == 'baseline' and not original.get('reference_context'):
                continue
            mapping = _index(root, suite, 'candidate' if side == 'candidate' else 'reference')
            by_pdf = {}
            for c in cases:
                if c['id'] in mapping:
                    page = mapping[c['id']]
                    by_pdf.setdefault(page.pdf, []).append((page.page_number, c))
            fresh = {}
            for pdf, items in by_pdf.items():
                ordered = [c for _, c in sorted(items)]
                fresh.update((r.case_id, r.as_dict()) for r in observe_pdf(pdf, descriptors(ordered)))
            rows.extend(_compare(c['id'], side, old.get(side), fresh.get(c['id']))
                        for c, old in zip(cases, original['cases']))
        from .adversarial import Probe, _interpret
        fresh_by_id = {(r['id'], r['side']): r['new'] for r in rows}
        for old in original['cases']:
            c = old['case']
            new = _interpret(Probe(**c), fresh_by_id.get((c['id'], 'candidate')),
                             fresh_by_id.get((c['id'], 'baseline')))
            flag_comparisons.append({'id': c['id'], 'old': old['flags'], 'new': new['flags'],
                                     'equal': old['flags'] == new['flags']})
    else:
        cases = definitions(suite)
        expected_source = (ROOT / suite.removeprefix('math-') / 'cases.tex').read_bytes()
        for side in ('before', 'after'):
            if (root / side / 'cases.tex').read_bytes() != expected_source:
                raise ValueError(f'{side}/cases.tex differs from the frozen fixture')
            old = _old_fixed(root, suite, side, cases)
            new = observe_pdf(root / side / 'cases.pdf', descriptors(cases))
            rows.extend(_compare(c['id'], side, a, b.as_dict()) for c, a, b in zip(cases, old, new))
        checks = check_pdfs(suite, root)
    counts = dict(Counter(row['status'] for row in rows))
    report = {'schema_version': 1, 'suite': suite, 'source': str(root),
              'observer': 'pymupdf', 'counts': counts, 'comparisons': rows,
              'new_checks': checks, 'flag_comparisons': flag_comparisons, 'note': 'Archive replay only; no new ConTeXt compilation.'}
    report['exit_code'] = 2 if counts.get('incomplete') else int(bool(counts.get('different')) or any(not c['equal'] for c in flag_comparisons))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'observer-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report
