"""Self-tests for the frozen pre-migration oracles (saved text, no Poppler)."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXTENDED = ROOT / "src/context_testsuite/cases/math/extended"
BASIC = ROOT / "src/context_testsuite/cases/math/basic"


def test_fixture_generated_from_76_case_manifest():
    res = subprocess.run([sys.executable, str(EXTENDED / "gen.py"), "--check"],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "76 cases" in res.stdout


def test_expectations_and_edge_cases_retained():
    cases = json.loads((EXTENDED / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == len({c["id"] for c in cases}) == 76
    assert {kind: sum(c["kind"] == kind for c in cases) for kind in
            ("protected", "normal", "other", "conflict")} == {
                "protected": 35, "normal": 25, "other": 11, "conflict": 5}
    by_id = {c["id"]: c for c in cases}
    assert by_id["P17"]["marker"] == "1"  # real short-inline-math regression
    assert by_id["L15"]["kind"] == "other"  # explicit forced break
    assert by_id["L16"]["kind"] == "protected"
    assert {"P03", "P15", "P17", "X02", "X10"} <= {
        c["id"] for c in cases if c["kind"] == "conflict"
    }


def _simulate_pages(cases, *, violation=None):
    pages = []
    for c in cases:
        marker = c.get("marker", "12345")
        joined = c["kind"] == "protected"
        if violation and c["id"] == violation:
            joined = not joined
        first = f"Das digitale Geraet hat ein {marker}"
        if joined:
            body = first + " stelliges Display und einen Fehler."
        else:
            body = first + "\n stelliges Display und einen Fehler."
        pages.append(f"{c['id']} {c['label']}\n{body}\n")
    return "\f".join(pages) + "\f"


def _check_fixture(tmp_path, *, violation=None):
    cases = json.loads((EXTENDED / "cases.json").read_text(encoding="utf-8"))
    (tmp_path / "before").mkdir()
    (tmp_path / "after").mkdir()
    (tmp_path / "before/cases.txt").write_text(_simulate_pages(cases), encoding="utf-8")
    (tmp_path / "after/cases.txt").write_text(_simulate_pages(cases, violation=violation), encoding="utf-8")
    return subprocess.run([sys.executable, str(ROOT / "tests/legacy/extended_check.py"), str(tmp_path)],
                          capture_output=True, text=True)


def test_extended_checker_accepts_expected_behavior(tmp_path):
    result = _check_fixture(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    checks = json.loads((tmp_path / "checks.json").read_text(encoding="utf-8"))
    assert len(checks["cases"]) == 76
    assert checks["errors"] == []
    assert len(checks["conflicts"]) == 5


def test_extended_checker_rejects_protected_break(tmp_path):
    result = _check_fixture(tmp_path, violation="L16")
    assert result.returncode != 0
    assert "L16 protected" in result.stdout and "FAIL protected expression is still split" in result.stdout


def test_extended_checker_rejects_suppressed_forced_break(tmp_path):
    result = _check_fixture(tmp_path, violation="P17")
    assert result.returncode != 0
    assert "P17 conflict" in result.stdout and "FAIL forced inline-math penalty -10000 was suppressed" in result.stdout


def test_basic_fixture_retained():
    text = (BASIC / "cases.tex").read_text(encoding="utf-8")
    assert text.count("\\subject{C") == 12
    assert "\\mathsurround=3pt" in text


def _basic_pages(*, violate=False):
    pages = []
    for index in range(1, 13):
        # C01/C02 and C06/C08 compare normalized line breaks. Only the
        # four protected-math cases need an extractable soft-hyphen marker.
        frac = "3 1⁄2" if index not in (2, 8) else "3 ⁄12"
        first = f"Das digitale Geraet hat ein {frac}"
        if index in (1, 2, 6, 8):
            if index == 1 and violate:
                body = first + "\n  stelliges Display und einen Fehler."
            else:
                body = first + "stel\u00ad\n liges Display und einen Fehler."
        else:
            body = first + "\n  stelliges Display und einen Fehler."
        if index in (4, 5):
            body = body.replace(frac, "3")
        pages.append(f"C{index:02} case\n{body}\n")
    return "\f".join(pages) + "\f"


def test_basic_checker_accepts_12_expected_pages(tmp_path):
    for side in ("before", "after"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "cases.txt").write_text(_basic_pages(), encoding="utf-8")
    res = subprocess.run([sys.executable, str(ROOT / "tests/legacy/basic_check.py"), str(tmp_path)],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PASS:" in res.stdout


def test_basic_checker_rejects_new_unprotected_math_break(tmp_path):
    for side in ("before", "after"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "cases.txt").write_text(_basic_pages(violate=side == "after"),
                                                       encoding="utf-8")
    res = subprocess.run([sys.executable, str(ROOT / "tests/legacy/basic_check.py"), str(tmp_path)],
                         capture_output=True, text=True)
    assert res.returncode != 0
    assert "FAIL" in res.stdout + res.stderr
