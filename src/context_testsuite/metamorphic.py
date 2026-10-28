"""Explicit relations between saved adversarial probes, evaluated per engine.

No inference that old == correct, no monotonicity assumption for global TeX
line breaking, and no hidden promotion of a design hypothesis to a hard rule.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .adversarial import Probe, probes
from .math_observer import canonical_layout, layout_key


@dataclass(frozen=True)
class Relation:
    id: str
    left: str
    right: str
    operation: str  # same-layout, both-split
    severity: str  # invariant, hypothesis
    transformation: str
    expectation: str
    rationale: str


SOURCE_FIELDS = ('id', 'family', 'math', 'marker', 'glue', 'setup', 'expr', 'width', 'pair')


def catalog() -> tuple[list[Relation], dict[str, dict]]:
    """Curated pairs; each change is verified against the actual source strings.

    The pre-existing Probe.pair field is only an index into the frozen inputs.
    It does not itself assert equality and is not used to group unrelated cases.
    """
    known = probes()
    by_pair = {p.pair: p for p in known if p.pair.startswith(('neighbor/', 'field/'))}
    relations = []

    def add(left: Probe, right: Probe, operation: str, severity: str,
            transformation: str, expectation: str, rationale: str) -> None:
        if any(getattr(left, key) != getattr(right, key)
               for key in ('family', 'math', 'marker', 'setup', 'width')):
            raise ValueError('Relation changes an unrelated source parameter')
        if operation == 'same-layout' and left.glue != right.glue:
            raise ValueError('Layout relation changes the glue kind')
        relations.append(Relation(f'M{len(relations)+1:03}', left.id, right.id,
                                  operation, severity, transformation, expectation, rationale))

    for source in ('math', 'hbox', 'text'):
        for glue in ('normal', 'tilde', 'nobreakspace', 'direct-plain', 'direct-protected'):
            left = by_pair[f'neighbor/{source}/adjacent/{glue}']
            right = by_pair[f'neighbor/{source}/relax/{glue}']
            if right.expr.replace(r'\relax ', '', 1) != left.expr or left.setup != right.setup:
                raise ValueError('Relax relation no longer changes only the inert token')
            add(left, right, 'same-layout', 'invariant',
                r'Insert \relax after the expression; retain glue, setup and width.',
                'Identical paragraph line contents and join/split observation.',
                r'\relax adds no node at this fully delimited position. No parameter scan is pending.')

    for source in ('math', 'hbox', 'text'):
        left = by_pair[f'neighbor/{source}/force/direct-plain']
        right = by_pair[f'neighbor/{source}/force/direct-protected']
        if (left.expr.replace('n.options=0;', 'n.options=1;') != right.expr or
                r'\penalty-10000 ' not in left.expr):
            raise ValueError('Force relation no longer changes only the noautobreak bit')
        add(left, right, 'both-split', 'invariant',
            'Enable noautobreak on the glue after a separate explicit penalty node -10000.',
            'Both control and transformed case split after the marker.',
            'The explicit penalty node supplies its own forced break. The following glue option '
            'inhibits automatic glue breaks; this relation does not assert a math-penalty priority.')

    for penalty in (-10000, -500, 0, 500):
        for glue in ('direct-plain', 'direct-protected'):
            left = by_pair[f'field/{penalty}/0/{glue}']
            for value in (-10000, -1, 1, 500, 10000):
                right = by_pair[f'field/{penalty}/{value}/{glue}']
                if left.expr.replace('n.penalty=0;', f'n.penalty={value};') != right.expr:
                    raise ValueError('Inactive-field relation changes more than the stored value')
                add(left, right, 'same-layout', 'hypothesis',
                    f'Change stored glue penalty 0 to {value}; leave has_penalty unset and all other inputs fixed.',
                    'Identical paragraph line contents and join/split if an inactive field has no effect.',
                    'Explicit design hypothesis: an inactive glue penalty is ignored. '
                    'The regular glue path supports this reading; math-helper semantics await upstream clarification. '
                    'A violation is a design question, not an automatically proven engine defect.')
    wanted = {name for relation in relations for name in (relation.left, relation.right)}
    return relations, {p.id: asdict(p) for p in known if p.id in wanted}


def _observation(row: dict | None, side: str, expected: dict) -> tuple[dict | None, str]:
    if row is None:
        return None, 'Case is absent from the saved report'
    actual_source = row.get('case', {})
    if any(actual_source.get(key) != expected[key] for key in SOURCE_FIELDS):
        return None, 'Saved source does not match the relation preconditions'
    obs = row.get(side)
    if not isinstance(obs, dict) or obs.get('status') != 'observed' or type(obs.get('joined')) is not bool:
        return None, 'Observation is missing, incomplete or unclassifiable'
    if not isinstance(obs.get('body'), str) or not obs['body'].strip():
        return None, 'Observation has no paragraph body'
    if 'layout' in obs and (not isinstance(obs['layout'], (list, tuple)) or
                           not obs['layout'] or not all(isinstance(s, str) for s in obs['layout'])):
        return None, 'Invalid saved line-layout signature'
    if 'layout' in obs and tuple(obs['layout']) != canonical_layout(obs['body']):
        return None, 'Saved layout signature disagrees with its paragraph body'
    return obs, ''


def evaluate(report: dict) -> dict:
    if report.get('schema_version') not in (1, 2):
        raise ValueError('Unsupported adversarial observation schema')
    saved = report.get('cases')
    if not isinstance(saved, list) or not saved:
        raise ValueError('Need a nonempty adversarial observations.json')
    by_id = {}
    for row in saved:
        if not isinstance(row, dict) or not isinstance(row.get('case'), dict):
            raise ValueError('Invalid case record in observation report')
        case_id = row.get('case', {}).get('id')
        if not case_id or case_id in by_id:
            raise ValueError('Missing or duplicate case ID in observation report')
        by_id[case_id] = row
    relations, sources = catalog()
    sides = ['candidate'] + (['baseline'] if report.get('reference_context') else [])
    results = []
    for side in sides:
        for relation in relations:
            left, why_left = _observation(by_id.get(relation.left), side, sources[relation.left])
            right, why_right = _observation(by_id.get(relation.right), side, sources[relation.right])
            why = '; '.join(filter(None, [why_left, why_right]))
            if why:
                status = 'inconclusive'
            else:
                if relation.operation == 'same-layout':
                    satisfied = left['joined'] == right['joined'] and layout_key(left) == layout_key(right)
                elif relation.operation == 'both-split':
                    satisfied = not left['joined'] and not right['joined']
                else:
                    raise ValueError(f'Unknown relation operation: {relation.operation}')
                status = 'pass' if satisfied else ('fail' if relation.severity == 'invariant' else 'question')
                why = ('Expected relation holds for these observations.' if satisfied else
                       'Expected relation is violated; inspect both case observations.')
                if relation.operation == 'both-split' and left['joined']:
                    why += ' The unprotected control already fails to force a break.'
            results.append({'relation': asdict(relation), 'engine_role': side,
                            'status': status, 'explanation': why, 'left': left, 'right': right})
    counts = dict(Counter(r['status'] for r in results))
    state = ('incomplete' if counts.get('inconclusive') else 'fail' if counts.get('fail') else
             'questions' if counts.get('question') else 'pass')
    return {'schema_version': 1, 'evaluation': 'metamorphic', 'catalog_version': 1,
            'source_observer': report.get('observer', 'legacy-poppler'),
            'candidate_context': report.get('candidate_context'),
            'reference_context': report.get('reference_context'),
            'relations': len(relations), 'evaluations': len(results), 'counts': counts,
            'result': state, 'exit_code': 2 if state == 'incomplete' else int(state == 'fail'),
            'note': 'Per-engine relations, not a baseline-is-correct oracle. Hypotheses remain questions. '
                    'No engine was compiled; only recorded observations were evaluated.',
            'case_sources': sources, 'checks': results}


def run(source: Path, output: Path) -> dict:
    source, output = source.expanduser().resolve(), output.expanduser().resolve()
    if source.is_dir():
        direct = source / 'observations.json'
        source = direct if direct.is_file() else source / 'math-adversarial/observations.json'
    if output == source.parent or source.parent in output.parents:
        raise ValueError('Metamorphic output must be outside the source suite directory')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Metamorphic output must be new or empty')
    result = evaluate(json.loads(source.read_text(encoding='utf-8')))
    result['source_report'] = str(source)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'metamorphic.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Metamorphic math checks', '',
             f"Result: **{result['result']}**; counts: {result['counts']}", '',
             result['note'], '',
             '| Engine | Relation | Cases | Severity | Result |',
             '|---|---|---|---|---|']
    for check in result['checks']:
        r = check['relation']
        lines.append(f"| {check['engine_role']} | {r['id']} | {r['left']} → {r['right']} | {r['severity']} | {check['status']} |")
    lines.extend(['', '## Explicit expectations', ''])
    seen = set()
    for check in result['checks']:
        r = check['relation']
        if r['id'] in seen:
            continue
        seen.add(r['id'])
        lines.extend([f"### {r['id']}: {r['left']} → {r['right']} ({r['severity']})", '',
                      r['transformation'], '', '**Expected:** ' + r['expectation'], '',
                      '**Reason:** ' + r['rationale'], ''])
    lines.extend(['## Findings and missing evidence', ''])
    for check in result['checks']:
        if check['status'] != 'pass':
            r = check['relation']
            lines.append(f"- {check['engine_role']} {r['id']} ({r['left']}/{r['right']}): "
                         f"{check['status']} — {check['explanation']}")
    (output / 'metamorphic.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return result
