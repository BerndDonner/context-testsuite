"""Real engine outputs, historical gates, and uncertainty during migration."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pymupdf
import pytest

from context_testsuite import adversarial as adv
from context_testsuite.math_observer import MathCase, observe_pdf
from context_testsuite.math_suites import check_pdfs, definitions, descriptors, evaluate, run_fixed
from context_testsuite.observer_audit import audit

CORPUS = Path(__file__).parent / 'fixtures/math-migration'


@pytest.mark.parametrize('suite,pages', [('basic', 24), ('extended', 152)])
def test_all_archived_pages_agree_with_saved_poppler(suite, pages, tmp_path):
    report = audit('math-' + suite, CORPUS / suite, tmp_path / 'audit')
    assert report['counts'] == {'agree': pages}
    assert report['exit_code'] == 0
    current = report['new_checks']
    if suite == 'basic':
        assert current['result'] == 'pass'
        assert [c['id'] for c in current['cases'] if c['changed']] == ['C01', 'C06']
    else:
        old = json.loads((CORPUS / suite / 'checks.json').read_text())
        assert current['result'] == 'fail'
        assert current['errors'] == old['errors']
        for now, then in zip(current['cases'], old['cases']):
            for key in ('id', 'before_join', 'after_join', 'changed', 'error'):
                assert now[key] == then[key]
        # This is observable empty vertical space, not lost PDF text.
        l15 = next(c for c in current['cases'] if c['id'] == 'L15')
        assert '' in l15['before']['layout'] and '' not in l15['after']['layout']


def test_missing_evidence_cannot_pass_fixed_suites():
    cases = definitions('math-extended')
    before = [o.as_dict() for o in observe_pdf(CORPUS / 'extended/before/cases.pdf', descriptors(cases))]
    after = deepcopy(before)
    after[0].update(status='unclassifiable', joined=None)
    assert evaluate('math-extended', cases, before, after)['exit_code'] == 2
    before[0]['case_id'] = 'WRONG'
    with pytest.raises(ValueError, match='ID mismatch'):
        evaluate('math-extended', cases, before, after)


def test_l15_only_one_blank_line_may_disappear():
    report = check_pdfs('math-extended', CORPUS / 'extended')
    cases = definitions('math-extended')
    before = [c['before'] for c in report['cases']]
    after = [c['after'] for c in report['cases']]
    i = next(i for i, c in enumerate(cases) if c['id'] == 'L15')
    before[i]['layout'] = (*before[i]['layout'][:1], '', *before[i]['layout'][1:])
    result = evaluate('math-extended', cases, before, after)
    assert any(e.startswith('L15:') for e in result['errors'])


def test_fraction_observer_rejects_missing_denominator(tmp_path):
    with pymupdf.open(CORPUS / 'basic/after/cases.pdf') as original:
        doc = pymupdf.open()
        doc.insert_pdf(original, from_page=0, to_page=0)
    page = doc[0]
    # Redact precisely the denominator; the whole-number/follower remain.
    glyph = next(c for b in page.get_text('rawdict')['blocks'] for l in b.get('lines', [])
                 for s in l['spans'] for c in s['chars'] if c['c'] == '2')
    x0, y0, x1, y1 = glyph['bbox']
    page.add_redact_annot(pymupdf.Rect(x0, y1 - 1, x1, y1))
    page.apply_redactions()
    path = tmp_path / 'bad.pdf'
    doc.save(path)
    doc.close()
    obs = observe_pdf(path, [MathCase('C01', '3', fraction=True)])[0]
    assert obs.status == 'unclassifiable' and obs.joined is None


def test_audit_does_not_modify_input_or_accept_wrong_sources(tmp_path):
    source = tmp_path / 'saved'
    shutil.copytree(CORPUS / 'basic', source)
    with pytest.raises(ValueError, match='outside'):
        audit('math-basic', source, source / 'audit')
    (source / 'before/cases.tex').write_text('different fixture')
    with pytest.raises(ValueError, match='differs'):
        audit('math-basic', source, tmp_path / 'audit')


def test_successful_process_without_pdf_cannot_reuse_stale_output(tmp_path):
    from context_testsuite.context_process import ProcessResult
    from unittest.mock import patch
    out = tmp_path / 'out'
    for side in ('before', 'after'):
        (out / side).mkdir(parents=True)
        shutil.copy2(CORPUS / 'basic' / side / 'cases.pdf', out / side / 'cases.pdf')
    with patch('context_testsuite.math_suites.run_context_process', return_value=ProcessResult(0, False, 0)):
        result = run_fixed('math-basic', 'fake', 'fake', out)
    assert result['exit_code'] == 2


def test_unknown_reference_is_incomplete_for_adversarial(tmp_path, monkeypatch):
    p = adv.probes()[0]
    monkeypatch.setattr(adv, 'probes', lambda: [p])
    def compile(context, group, target, cache):
        row = {'status': 'unclassifiable', 'reason': 'unknown'} if context == 'reference' else {
            'status': 'observed', 'joined': True, 'body': 'good'}
        return [row], {'status': 'ok'}
    monkeypatch.setattr(adv, '_compile', compile)
    assert adv.run_adversarial('candidate', 'reference', tmp_path)['exit_code'] == 2
