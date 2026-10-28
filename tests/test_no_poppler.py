"""Exercise productive compiler/extractor/report paths with a hostile pdftotext."""
from pathlib import Path
import json
import os
import sys
import subprocess

import pytest

from context_testsuite import adversarial as adv
from context_testsuite.runner import run_suites

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tests/fixtures/math-migration'


@pytest.fixture
def forbidden_poppler(tmp_path, monkeypatch):
    called = tmp_path / 'unexpected-poppler-call'
    trap = tmp_path / 'pdftotext'
    trap.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nPath({str(called)!r}).touch()\nraise SystemExit(97)\n')
    trap.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    monkeypatch.delenv('CTS_TEST_POPPLER', raising=False)
    yield
    assert not called.exists(), 'A productive test tried to call pdftotext'


def compiler(tmp_path, pdf, name):
    script = tmp_path / name
    script.write_text(f'#!{sys.executable}\nfrom pathlib import Path\nimport shutil\n'
                      f'assert Path("cases.tex").is_file()\nshutil.copyfile({str(pdf)!r}, "cases.pdf")\n')
    script.chmod(0o755)
    return str(script)


@pytest.mark.parametrize('suite,status', [('basic', 0), ('extended', 1)])
def test_productive_fixed_suites_without_poppler(tmp_path, forbidden_poppler, suite, status):
    before = compiler(tmp_path, CORPUS / suite / 'before/cases.pdf', 'before-engine')
    after = compiler(tmp_path, CORPUS / suite / 'after/cases.pdf', 'after-engine')
    output = tmp_path / 'result'
    assert run_suites(after, before, 'math-' + suite, output) == status
    report = json.loads((output / 'run-report.json').read_text())
    assert report['suites'][0]['result'] == ('pass' if status == 0 else 'fail')
    assert not list(output.rglob('cases.txt'))
    source = ROOT / f'src/context_testsuite/cases/math/{suite}/compare.sh'
    checked = subprocess.run(['bash', str(source), '--check-only', str(output / ('math-' + suite))],
                             capture_output=True, text=True)
    assert checked.returncode == status, checked.stdout + checked.stderr


def test_productive_adversarial_without_poppler(tmp_path, monkeypatch, forbidden_poppler):
    corpus = ROOT / 'tests/fixtures/pdf-extraction'
    ids = [r['id'] for r in json.loads((corpus / 'expected.json').read_text()) if r['engine'] == 'candidate']
    known = {p.id: p for p in adv.probes()}
    selected = [known[k] for k in ids]
    monkeypatch.setattr(adv, 'probes', lambda: selected)
    # Put all selected real pages in one shard (the production default normally
    # isolates experimental fields). Test the shared process/observation path.
    ref = compiler(tmp_path, corpus / 'reference.pdf', 'ref-engine')
    cand = compiler(tmp_path, corpus / 'candidate.pdf', 'candidate-engine')
    observed_ref, _ = adv._compile(ref, selected, tmp_path / 'ref', tmp_path / 'cache-ref')
    observed_cand, _ = adv._compile(cand, selected, tmp_path / 'cand', tmp_path / 'cache-cand')
    assert observed_ref is not None and observed_cand is not None
    assert all(r['status'] == 'observed' for r in observed_ref + observed_cand)
    rows = [adv._interpret(p, b, a) for p, a, b in zip(selected, observed_ref, observed_cand)]
    out = tmp_path / 'report'
    out.mkdir()
    result = adv._report(out, rows, [], cand, ref)
    assert result['hard_failures'] == 0 and result['total'] == 8
