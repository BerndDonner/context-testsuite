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
    assert len(a) == 779
    assert len({p.id for p in a}) == len(a)
    counts = Counter(p.family for p in a)
    assert counts["glue-penalty-field"] == 138
    assert counts["post-short"] == 25
    assert counts["explicit-force"] == 20
    assert all(p.math == "short" and "\\postshortinlinepenalty=" in p.setup
               for p in a if p.family == "post-short")
    assert all(p.expectation == "force-explicit" for p in a if p.family == "explicit-force")


def test_semantic_claims_are_not_mistaken_for_verified_results():
    cases = adv.probes()
    protected = next(p for p in cases if p.expectation == "protect")
    force_math = next(p for p in cases if p.expectation == "force-math-question")
    force_unprotected = next(p for p in cases if p.expectation == "force-math-unprotected")
    force_explicit = next(p for p in cases if p.expectation == "force-explicit")
    control = next(p for p in cases if p.expectation == "observe")
    joined = {"status": "observed", "joined": True, "body": "joined"}
    split = {"status": "observed", "joined": False, "body": "split"}
    assert "protected-glue-violation" in adv._interpret(protected, split, None)["flags"]
    assert "math-force-priority-question" in adv._interpret(force_math, joined, None)["flags"]
    assert "math-force-unprotected-question" in adv._interpret(force_unprotected, joined, None)["flags"]
    assert "explicit-force-violation" in adv._interpret(force_explicit, joined, None)["flags"]
    assert adv._interpret(force_math, split, None)["flags"] == []
    assert adv._interpret(force_unprotected, split, None)["flags"] == []
    assert adv._interpret(control, joined, split)["flags"] == ["break-changed-vs-baseline"]
    assert adv._interpret(control, joined, None)["flags"] == []


def test_pdf_text_classification_splits_and_joins(tmp_path):
    first, second = adv.probes()[0:2]
    doc = pymupdf.open()
    for probe, body in [(first, "Das digitale Geraet hat ein 12345 stelliges Display"),
                        (second, "Das digitale Geraet hat ein 12345\nstelliges Display")]:
        page = doc.new_page()
        page.insert_text((50, 100), probe.id + "\n" + body)
    pdf = tmp_path / "cases.pdf"
    doc.save(pdf)
    doc.close()
    result = adv._extract(pdf, [first, second])
    assert result[0]["status"] == "observed" and result[0]["joined"] is True
    assert result[1]["status"] == "observed" and result[1]["joined"] is False



def test_pdf_extraction_when_prefix_or_math_moves_to_another_line(tmp_path):
    # Both situations occurred in the real 450-probe Hans run.  The old
    # extractor called them "unclassifiable" despite valid PDF pages.
    by_id = {p.id: p for p in adv.probes()}
    selected = [by_id["A0394"], by_id["A0442"], by_id["A0443"]]
    bodies = ["Das digitale Geraet hat\nein 12345 stelliges Display\nund einen Fehler.",
              "Das digitale Geraet hat ein\n12345 stelliges Display und einen\nFehler.",
              "Das digitale Geraet hat ein\n12345\nstelliges Display und einen\nFehler."]
    doc = pymupdf.open()
    for p, body in zip(selected, bodies):
        page = doc.new_page()
        page.insert_text((50, 100), p.id + "\n" + body)
    pdf = tmp_path / "cases.pdf"
    doc.save(pdf)
    doc.close()
    rows = adv._extract(pdf, selected)
    assert [r["status"] for r in rows] == ["observed"] * 3
    assert [r["joined"] for r in rows] == [True, True, False]


def test_unprotected_negative_math_penalty_at_roomy_width_is_high_priority():
    # This is the observed A0419 pattern.  The test verifies the reporting
    # semantics, NOT that Hans's implementation has any particular output.
    p = next(p for p in adv.probes() if p.id == "A0419")
    assert p.glue == "normal" and p.width == 80
    assert p.expectation == "force-math-unprotected"
    joined = {"status": "observed", "joined": True, "body": "joined"}
    split = {"status": "observed", "joined": False, "body": "split"}
    result = adv._interpret(p, joined, split)
    assert result["flags"] == ["math-force-unprotected-question", "break-changed-vs-baseline"]

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


def test_hans_design_probes_preserve_original_ids_and_are_paired():
    cases = adv.probes()
    assert len(cases) == 779
    assert [p.id for p in cases[:450]] == [f"A{i:04}" for i in range(1, 451)]
    assert len({p.id for p in cases}) == len(cases)
    counts = Counter(p.family for p in cases)
    assert counts["noautobreak-neighbors"] == 75
    assert counts["noautobreak-boundaries"] == 56
    assert counts["glue-penalty-field"] == 138  # old 36 + new 48 + new 54
    neighbors = [p for p in cases if p.family == "noautobreak-neighbors"]
    assert {p.math for p in neighbors} == {"math", "hbox", "text"}
    assert any(r"\penalty0 " in p.expr and p.expectation == "observe" for p in neighbors)
    assert all(p.expectation == "force-explicit" for p in neighbors
               if r"\penalty-10000 " in p.expr)
    # No explicit force is silently interpreted as a glue-only invariant.
    assert all(p.expectation == "observe" for p in neighbors if r"\penalty0 " in p.expr)


def test_hans_design_noautobreak_penalty_limits_and_unmarked_field():
    cases = adv.probes()
    boundaries = [p for p in cases if p.family == "noautobreak-boundaries"]
    assert {p.width for p in boundaries} == {67, 80}
    assert all(p.expectation == "force-math-question" for p in boundaries
               if p.glue == "direct-protected" and p.setup == r"\postinlinepenalty=-10000")
    assert all(p.expectation == "force-math-unprotected" for p in boundaries
               if p.glue == "direct-plain" and p.setup == r"\postinlinepenalty=-10000")
    assert all(p.expectation == "observe" for p in boundaries
               if p.setup == r"\postinlinepenalty=-9999")
    fields = [p for p in cases if p.family == "glue-penalty-field"]
    assert all(p.expectation == "observe" for p in fields if p.id > "A0450")
    assert any("n.penalty=500; n.options=0; node.write(n)" in p.expr for p in fields
               if p.id > "A0450")
    assert any("mathinlinepenaltyfactor=20000" in p.setup for p in fields)


def test_real_parpass_factor_probes_are_distinct_from_primitive():
    cases = adv.probes()
    real = [p for p in cases if p.family == "real-parpass-math-factor"]
    assert len(real) == 96
    assert real[0].id == "A0684" and real[-1].id == "A0779"
    assert {p.width for p in real} == {67, 80}
    assert all(r"\parpasses 3" in p.setup and r"\linebreakpasses=1" in p.setup for p in real)
    assert all(p.setup.count("mathpenaltyfactor") == 3 for p in real)
    assert all(r"\mathinlinepenaltyfactor" not in p.setup for p in real)
    assert all(p.expectation == "observe" for p in real)
    assert any("n.penalty=10000; n.options=0" in p.expr for p in real)
