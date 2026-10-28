"""Self-tests of exploratory harness semantics; do not require ConTeXt."""
from collections import Counter
import json
from pathlib import Path

import pymupdf

from context_testsuite import adversarial as adv


def test_generator_is_deterministic_and_isolates_experimental_probe_family():
    a = adv.probes()
    b = adv.probes()
    assert a == b
    assert len(a) == 450
    assert len({p.id for p in a}) == len(a)
    counts = Counter(p.family for p in a)
    assert counts["glue-penalty-field"] == 36
    assert counts["post-short"] == 25
    assert counts["explicit-force"] == 20
    assert all(p.math == "short" and "\\postshortinlinepenalty=" in p.setup
               for p in a if p.family == "post-short")
    assert all(p.expectation == "force-explicit" for p in a if p.family == "explicit-force")


def test_semantic_claims_are_not_mistaken_for_verified_results():
    cases = adv.probes()
    protected = next(p for p in cases if p.expectation == "protect")
    force_math = next(p for p in cases if p.expectation == "force-math-question")
    force_explicit = next(p for p in cases if p.expectation == "force-explicit")
    control = next(p for p in cases if p.expectation == "observe")
    joined = {"status": "observed", "joined": True, "body": "joined"}
    split = {"status": "observed", "joined": False, "body": "split"}
    assert "protected-glue-violation" in adv._interpret(protected, split, None)["flags"]
    assert "math-force-priority-question" in adv._interpret(force_math, joined, None)["flags"]
    assert "explicit-force-violation" in adv._interpret(force_explicit, joined, None)["flags"]
    assert adv._interpret(force_math, split, None)["flags"] == []
    assert adv._interpret(control, joined, split)["flags"] == ["break-changed-vs-baseline"]
    assert adv._interpret(control, joined, None)["flags"] == []


def test_pdf_text_classification_splits_and_joins(tmp_path):
    first, second = adv.probes()[0:2]
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page()
        page.insert_text((50, 100), f"{(first, second)[i].id}")
    pdf = tmp_path / "cases.pdf"
    doc.save(pdf)
    doc.close()
    txt = tmp_path / "cases.txt"
    txt.write_text(
        f"{first.id}\nDas digitale Geraet hat ein 12345 stelliges Display und einen Fehler.\n\f"
        f"{second.id}\nDas digitale Geraet hat ein 12345\n stelliges Display und einen Fehler.\n\f",
        encoding="utf-8")
    result = adv._extract(txt, pdf, [first, second])
    assert result[0]["status"] == "observed" and result[0]["joined"] is True
    assert result[1]["status"] == "observed" and result[1]["joined"] is False


def test_report_generates_standalone_reproduction_and_does_not_upgrade_question(tmp_path):
    p = next(p for p in adv.probes() if p.expectation == "force-math-question")
    joined = {"status": "observed", "joined": True, "body": "joined"}
    data = adv._interpret(p, joined, None)
    report = adv._report(tmp_path, [data], [], "fake-hans", None)
    assert report["hard_failures"] == 0
    assert report["questions"] == 1
    assert (tmp_path / f"repros/{p.id}.tex").read_text().count("\\startframedtext") == 1
    findings = json.loads((tmp_path / "findings.json").read_text())
    assert len(findings) == 1 and findings[0]["case"]["id"] == p.id
    assert "semantic question" in (tmp_path / "findings.md").read_text().lower()


def test_runner_keeps_partial_results_and_returns_incomplete(tmp_path, monkeypatch):
    p = next(p for p in adv.probes() if p.family == "explicit-force")
    monkeypatch.setattr(adv, "probes", lambda: [p])
    monkeypatch.setattr(adv, "_compile", lambda *args: (None, {"status": "compile-error", "log": "failed"}))
    status = adv.run_adversarial("fake", None, tmp_path)
    assert status["result"] == "incomplete" and status["exit_code"] == 2
    report = json.loads((tmp_path / "observations.json").read_text())
    assert report["counts"]["not-run"] == 1
    assert report["shards"][0]["candidate"]["status"] == "compile-error"


def test_failed_shard_is_bisected_to_salvage_good_cases(tmp_path, monkeypatch):
    chosen = adv.probes()[0:4]
    calls = []
    def mock_compile(context, group, target, cache_root):
        calls.append([x.id for x in group])
        if chosen[2] in group:
            return None, {"status": "compile-error", "log": str(target / "build.log")}
        return [{"status": "observed", "joined": True, "body": "fine"} for x in group], {"status": "ok"}
    monkeypatch.setattr(adv, "_compile", mock_compile)
    rows, info = adv._compile_resilient("fake", chosen, tmp_path / "target", tmp_path / "cache")
    assert len(rows) == 4 and rows[2] is None
    assert sum(row is None for row in rows) == 1
    assert info["status"] == "partial" and info["failed_cases"] == 1
    assert any(len(subgroup) == 1 for subgroup in calls)
