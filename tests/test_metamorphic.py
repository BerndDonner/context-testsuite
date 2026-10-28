"""Relations must test the declared transformation, including non-vacuous controls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from context_testsuite import adversarial as adv
from context_testsuite.metamorphic import catalog, evaluate, run


def observations(*, baseline=True):
    relations, sources = catalog()
    forced = {name for r in relations if r.operation == 'both-split' for name in (r.left, r.right)}
    rows = []
    for name, source in sources.items():
        joined = name not in forced
        obs = {'status': 'observed', 'joined': joined,
               'body': 'Das digitale Geraet 12345' + (' ' if joined else '\n') + 'stelliges Display'}
        rows.append({'case': source, 'candidate': obs, 'baseline': deepcopy(obs) if baseline else None})
    return {'schema_version': 2, 'observer': 'pymupdf', 'candidate_context': 'candidate',
            'reference_context': 'reference' if baseline else None, 'cases': rows}


def changed(report, name, side='candidate'):
    return next(row for row in report['cases'] if row['case']['id'] == name)[side]


def test_catalog_has_explicit_independent_transformations():
    relations, sources = catalog()
    assert len(relations) == 58 and len({r.id for r in relations}) == 58
    assert sum(r.severity == 'invariant' for r in relations) == 18
    assert sum(r.severity == 'hypothesis' for r in relations) == 40
    assert all(r.expectation and r.rationale and r.transformation for r in relations)
    assert all(sources[r.left]['width'] == sources[r.right]['width'] for r in relations)
    # A kernel node, math/text replacement, factor or width variation is not
    # silently treated as an inert transformation.
    assert all('kern0' not in sources[r.right]['pair'] for r in relations)


def test_satisfied_relations_and_baseline_are_evaluated_separately():
    report = observations()
    result = evaluate(report)
    assert result['counts'] == {'pass': 116} and result['exit_code'] == 0
    r = catalog()[0][0]
    changed(report, r.right).update(joined=False, body='Das digitale Geraet 12345\nstelliges Display')
    result = evaluate(report)
    failures = [c for c in result['checks'] if c['status'] == 'fail']
    assert len(failures) == 1 and failures[0]['engine_role'] == 'candidate'
    assert result['exit_code'] == 1


def test_equal_but_joined_forced_controls_cannot_pass():
    report = observations(baseline=False)
    relation = next(r for r in catalog()[0] if r.operation == 'both-split')
    for name in (relation.left, relation.right):
        changed(report, name)['joined'] = True
    result = evaluate(report)
    failure = next(c for c in result['checks'] if c['relation']['id'] == relation.id)
    assert failure['status'] == 'fail' and 'control already fails' in failure['explanation']


def test_hypothesis_violation_is_explicit_question_not_hard_failure():
    report = observations()
    relation = next(r for r in catalog()[0] if r.severity == 'hypothesis')
    changed(report, relation.right).update(joined=False, body='Das digitale Geraet 12345\nstelliges Display')
    result = evaluate(report)
    assert result['result'] == 'questions' and result['exit_code'] == 0
    assert result['counts'] == {'pass': 115, 'question': 1}


@pytest.mark.parametrize('defect', ['missing', 'source', 'unknown', 'layout', 'reference'])
def test_missing_or_invalid_preconditions_are_inconclusive(defect):
    report = observations()
    r = catalog()[0][0]
    row = next(c for c in report['cases'] if c['case']['id'] == r.right)
    if defect == 'missing':
        report['cases'].remove(row)
    elif defect == 'source':
        row['case']['width'] += 1
    elif defect == 'unknown':
        row['candidate'].update(status='unclassifiable', joined=None)
    elif defect == 'layout':
        row['candidate']['layout'] = ['inconsistent cached value']
    elif defect == 'reference':
        row['baseline'] = None
    result = evaluate(report)
    assert result['result'] == 'incomplete' and result['exit_code'] == 2
    assert result['counts']['inconclusive'] >= 1


def test_horizontal_extractor_whitespace_is_not_a_metamorphic_violation():
    report = observations(baseline=False)
    r = catalog()[0][0]
    changed(report, r.right)['body'] = '  Das  digitale Geraet 12345    stelliges Display'
    assert evaluate(report)['result'] == 'pass'
    # A real empty line, or downstream line break, still violates same-layout.
    changed(report, r.right)['body'] = 'Das digitale Geraet 12345 stelliges\nDisplay'
    assert evaluate(report)['result'] == 'fail'


def test_duplicate_cases_rejected_and_legacy_schema_supported():
    report = observations(baseline=False)
    report['schema_version'] = 1
    del report['observer']
    result = evaluate(report)
    assert result['source_observer'] == 'legacy-poppler' and result['evaluations'] == 58
    report['cases'].append(report['cases'][0])
    with pytest.raises(ValueError, match='duplicate'):
        evaluate(report)


def test_new_report_is_separate_and_cli_fails_for_incomplete_evidence(tmp_path):
    source = tmp_path / 'old/math-adversarial'
    source.mkdir(parents=True)
    report = observations(baseline=False)
    report['cases'].pop()
    path = source / 'observations.json'
    path.write_text(json.dumps(report))
    original = path.read_bytes()
    with pytest.raises(ValueError, match='outside'):
        run(source, source / 'new')
    output = tmp_path / 'new'
    cmd = [sys.executable, '-m', 'context_testsuite', 'metamorphic', '--from', str(source.parent), '--output', str(output)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert path.read_bytes() == original
    result = json.loads((output / 'metamorphic.json').read_text())
    assert result['result'] == 'incomplete'
    text = (output / 'metamorphic.md').read_text()
    assert 'Explicit expectations' in text and 'inconclusive' in text
    with pytest.raises(ValueError, match='new or empty'):
        run(source, output)


def test_real_archived_hans_run_reproduces_four_design_questions():
    fixture = Path(__file__).parent / 'fixtures/metamorphic/hans-v4-observations.json'
    report = json.loads(fixture.read_text())
    result = evaluate(report)
    assert result['counts'] == {'pass': 112, 'question': 4}
    assert result['result'] == 'questions' and result['exit_code'] == 0
    questions = [c for c in result['checks'] if c['status'] == 'question']
    assert {c['relation']['right'] for c in questions} == {'A0592', 'A0604', 'A0616', 'A0628'}
    assert all(c['engine_role'] == 'candidate' for c in questions)
    assert all(c['relation']['severity'] == 'hypothesis' for c in questions)
    assert all(c['status'] == 'pass' for c in result['checks'] if c['engine_role'] == 'baseline')
