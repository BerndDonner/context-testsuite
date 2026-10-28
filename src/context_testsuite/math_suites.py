"""Frozen basic/extended assertions over the shared PDF observer.

The extended conflict assertions are the historic regression contract, NOT a
claim that the disputed math-penalty precedence has been settled with upstream.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from .context_process import run_context_process
from .math_observer import MathCase, layout_key, observe_pdf

ROOT = Path(__file__).parent / 'cases' / 'math'


def definitions(suite: str) -> list[dict]:
    if suite == 'math-basic':
        return [{'id': f'C{i:02}', 'marker': '3', 'fraction': i not in (4, 5)}
                for i in range(1, 13)]
    if suite == 'math-extended':
        return json.loads((ROOT / 'extended/cases.json').read_text(encoding='utf-8'))
    raise ValueError(f'Unsupported fixed math suite: {suite}')


def descriptors(cases: list[dict]) -> list[MathCase]:
    return [MathCase(c['id'], c.get('marker', '12345'), fraction=c.get('fraction', False)) for c in cases]


def evaluate(suite: str, cases: list[dict], before: list[dict], after: list[dict]) -> dict:
    """Keep historical gates; missing evidence is incomplete, never pass."""
    if not len(cases) == len(before) == len(after) or not cases:
        raise ValueError('Case/observation count mismatch')
    for c, a, b in zip(cases, before, after):
        if a.get('case_id') != c['id'] or b.get('case_id') != c['id']:
            raise ValueError(f"Observation ID mismatch: {c['id']}")
    if any(r['status'] != 'observed' for r in before + after):
        return {'cases': [{'id': c['id'], 'before': a, 'after': b} for c, a, b in zip(cases, before, after)],
                'errors': [], 'conflicts': [], 'result': 'incomplete', 'exit_code': 2,
                'reason': 'At least one page cannot be classified'}
    errors, rows, conflicts = [], [], []
    changes = [c['id'] for c, a, b in zip(cases, before, after) if layout_key(a) != layout_key(b)]
    if suite == 'math-basic':
        if changes not in ([], ['C01', 'C06']):
            errors.append(f'Unexpected line-layout changes: {changes}; expected [] or [C01, C06]')
        by_id = {c['id']: b for c, b in zip(cases, after)}
        for left, right in [('C01', 'C02'), ('C06', 'C08')]:
            if layout_key(by_id[left]) != layout_key(by_id[right]):
                errors.append(f'{left} differs in line layout from {right}')
            if not by_id[left]['joined']:
                errors.append(f'{left}: protected expression is still split')
            if not by_id[left]['layout'][0].endswith('stel\u00ad'):
                errors.append(f'{left}: expected first line to end with the protected stel- fragment')
        for c, a, b in zip(cases, before, after):
            rows.append({**c, 'before_join': a['joined'], 'after_join': b['joined'],
                         'changed': c['id'] in changes, 'before': a, 'after': b})
    elif suite == 'math-extended':
        for c, a, b in zip(cases, before, after):
            kind, reason, changed = c['kind'], '', c['id'] in changes
            if kind == 'protected':
                if not b['joined']:
                    reason = 'protected expression is still split'
            elif kind in ('normal', 'other'):
                if c['id'] == 'L15':
                    # Exactly the first extra blank line may disappear. Retain
                    # all other line contents, hyphenation and blank lines.
                    old_lines = list(layout_key(a)[0])
                    if '' in old_lines:
                        old_lines.remove('')
                    if b['joined'] or tuple(old_lines) != layout_key(b)[0]:
                        reason = 'explicit forced break changed beyond removing one empty line'
                elif changed:
                    reason = 'unexpected change to unprotected/control case'
            elif kind == 'conflict':
                if b['joined']:
                    reason = 'forced inline-math penalty -10000 was suppressed'
                conflicts.append({'id': c['id'], 'before_join': a['joined'],
                                  'after_join': b['joined'], 'changed': changed})
            else:
                raise ValueError(f'Unknown test category: {kind}')
            if reason:
                errors.append(f"{c['id']}: {reason}")
            rows.append({**c, 'before_join': a['joined'], 'after_join': b['joined'],
                         'changed': changed, 'error': reason, 'before': a, 'after': b})
    else:
        raise ValueError(f'Unsupported fixed math suite: {suite}')
    return {'cases': rows, 'errors': errors, 'conflicts': conflicts,
            'result': 'fail' if errors else 'pass', 'exit_code': int(bool(errors))}


def check_pdfs(suite: str, root: Path, *, output: Path | None = None) -> dict:
    cases = definitions(suite)
    observations = [
        [o.as_dict() for o in observe_pdf(root / side / 'cases.pdf', descriptors(cases))]
        for side in ('before', 'after')]
    report = {'schema_version': 2, 'observer': 'pymupdf', 'suite': suite,
              **evaluate(suite, cases, *observations)}
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        (output / 'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def run_fixed(suite: str, candidate: str, baseline: str, output: Path) -> dict:
    """Compile in copied workspaces with bounded process groups and fresh PDFs."""
    source = ROOT / suite.removeprefix('math-') / 'cases.tex'
    if suite == 'math-extended':
        # Keep the source/manifest drift guard used by the original shell runner.
        import runpy
        generator = runpy.run_path(str(source.parent / 'gen.py'))
        if source.read_text(encoding='utf-8') != generator['generate']():
            raise ValueError('Extended cases.tex differs from cases.json; run gen.py')
    builds = []
    for side, engine in [('before', baseline), ('after', candidate)]:
        work = output / side
        work.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, work / 'cases.tex')
        pdf = work / 'cases.pdf'
        pdf.unlink(missing_ok=True)  # a successful process must produce a new PDF
        result = run_context_process(engine, 'cases.tex', work=work,
                                     home=output / f'home-{side}', tex_cache=output / f'cache-{side}',
                                     stdout_log=work / 'build.log')
        builds.append({'side': side, 'exit_code': result.exit_code,
                       'timed_out': result.timed_out, 'log': str(work / 'build.log')})
    try:
        if any(row['exit_code'] for row in builds):
            raise ValueError('Compilation failed; inspect build logs')
        report = check_pdfs(suite, output)
    except (OSError, ValueError, RuntimeError) as exc:
        report = {'schema_version': 2, 'suite': suite, 'observer': 'pymupdf',
                  'result': 'incomplete', 'exit_code': 2, 'reason': str(exc)}
    report['builds'] = builds
    (output / 'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{report['result'].upper()}: {suite} (see {output / 'checks.json'})")
    return {k: report[k] for k in ('result', 'exit_code')} | {'report': str(output / 'checks.json')}


def main(argv: list[str] | None = None) -> int:
    """Compatibility with compare.sh ENGINE ENGINE [OUT] / --check-only OUT."""
    import sys
    import tempfile
    from .runner import executable
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args or args[0] not in ('math-basic', 'math-extended'):
            raise ValueError('Expected math-basic or math-extended')
        suite, *rest = args
        if len(rest) == 2 and rest[0] == '--check-only':
            root = Path(rest[1]).expanduser().resolve()
            report = check_pdfs(suite, root, output=root)
        elif len(rest) in (2, 3) and not rest[0].startswith('--'):
            root = Path(rest[2] if len(rest) == 3 else tempfile.mkdtemp(prefix=suite + '-')).resolve()
            root.mkdir(parents=True, exist_ok=True)
            report = run_fixed(suite, executable(rest[1]), executable(rest[0]), root)
        else:
            raise ValueError('Usage: compare.sh REFERENCE CANDIDATE [OUT] | --check-only OUT')
        for message in report.get('errors', []):
            print('FAIL: ' + message)
        print(f"{report['result'].upper()}: {suite}")
        return report['exit_code']
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
