#!/usr/bin/env python3
"""Generate the frozen 76-case ConTeXt fixture or verify it is up to date."""
import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent
cases = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
expected_kinds = {'protected': 35, 'normal': 25, 'other': 11, 'conflict': 5}
assert len(cases) == 76 and len({c['id'] for c in cases}) == 76, 'Unexpected cases / repeated IDs'
assert {k: sum(c['kind'] == k for c in cases) for k in expected_kinds} == expected_kinds, 'Unexpected case kinds'

out = [
    r'\mainlanguage[de]', r'\setuppapersize[A5]',
    r'\setuplayout[width=110mm,height=175mm,backspace=15mm,topspace=12mm,header=0pt,footer=0pt]',
    r'\starttext',
]
for i, c in enumerate(cases):
    if i:
        out.append(r'\page')
    out += [
        r'\begingroup', c['setup'],
        r'\subject{' + c['id'] + ' ' + c['label'].replace('&', r'\&') + '}',
        r'\startframedtext[width=67mm]',
        f"Das digitale Geraet hat ein {c['expr']} Display und einen Fehler.",
        r'\stopframedtext', r'\endgroup',
    ]
out.append(r'\stoptext')
text = '\n'.join(out) + '\n'
fixture = root / 'cases.tex'
if sys.argv[1:] == ['--check']:
    if not fixture.is_file() or fixture.read_text(encoding='utf-8') != text:
        raise SystemExit('FAIL: cases.tex differs from cases.json (run python3 gen.py)')
    print(f'Fixture OK: {len(cases)} cases')
elif len(sys.argv) == 1:
    fixture.write_text(text, encoding='utf-8')
    print(f'Generated: {len(cases)} cases')
else:
    raise SystemExit('Usage: gen.py [--check]')
