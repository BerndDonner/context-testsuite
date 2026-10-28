#!/usr/bin/env python3
"""Compare page-by-page ConTeXt line breaks for experimental noautobreak fix.

Unlike byte-level PDF/text comparison, we verify the exact requested break property
without treating innocent hyphenation downstream as a regression.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))


def load(root: Path, which: str):
    file = root / which / "cases.txt"
    if not file.is_file():
        raise SystemExit(f"Missing {file}; run compare.sh first")
    pages = [p for p in file.read_text(encoding="utf-8").split("\f") if p.strip()]
    if len(pages) != len(CASES):
        raise SystemExit(f"FAIL: {which}: expected {len(CASES)} pages, got {len(pages)}")
    result = []
    for case, page in zip(CASES, pages):
        lines = page.splitlines()
        if not any(line.strip().startswith(case["id"] + " ") for line in lines):
            raise SystemExit(f"FAIL: PDF page ID does not match {case['id']} in {which}")
        ids = [i for i, s in enumerate(lines) if "Das digitale Geraet hat ein" in s]
        if len(ids) != 1:
            raise SystemExit(f"FAIL: cannot locate body in {which} case {case['id']}")
        text = "\n".join(lines[ids[0]:]).strip()
        first = lines[ids[0]]
        marker = case.get("marker", "12345")
        if marker not in first:
            raise SystemExit(f"FAIL: math marker {marker!r} disappeared in {which} case {case['id']}")
        # 'stelliges' may be hyphenated into 'stel-' + 'liges'.
        # Short math tests use the marker '1'; all existing tests use '12345'.
        join = "ste" in first.split(marker, 1)[1]
        result.append({"joined": join, "text": text})
    return result


def check(root: Path):
    before = load(root, "before")
    after = load(root, "after")
    rows = []
    errors = []
    conflicts = []
    for case, a, b in zip(CASES, before, after):
        kind = case["kind"]
        if kind not in ("protected", "normal", "other", "conflict"):
            raise SystemExit(f"FAIL: unknown test category {kind!r} in {case['id']}")
        changed = a["text"] != b["text"]
        reason = ""
        if kind == "protected":
            if not b["joined"]:
                reason = "protected expression is still split"
        elif kind == "normal":
            if changed:
                reason = "unexpected change to unprotected/control case"
        elif kind == "other":
            if case["id"] == "L15":
                # A separate explicit \penalty-10000 must still force exactly
                # one break. Before the fix the math/glue combination produced
                # an extra empty line; removing just that empty line is allowed.
                expected = a["text"].replace("\n\n", "\n", 1)
                if b["joined"] or b["text"] != expected:
                    reason = "explicit forced break changed beyond removing one empty line"
            elif changed:
                reason = "unexpected change to unprotected/control case"
        elif kind == "conflict":
            # This is not an undecidable conflict: TeX penalty -10000 forces
            # a break. noautobreak must only inhibit an implicit breakpoint,
            # not an explicitly forced inline-math penalty.
            if b["joined"]:
                reason = "forced inline-math penalty -10000 was suppressed"
            conflicts.append({"id":case["id"], "before_join":a["joined"], "after_join":b["joined"], "changed":changed})
        if reason:
            errors.append(f"{case['id']}: {reason}")
        rows.append({**case, "before_join":a["joined"], "after_join":b["joined"], "changed":changed, "error":reason})
        change_label = "CHANGED" if changed else "unchanged"
        print(f"{case['id']} {kind:9s} {'join' if a['joined'] else 'split'} -> {'join' if b['joined'] else 'split'} {change_label:9s} {'FAIL '+reason if reason else ''}")
        if reason and changed:
            # Report precisely what differs, rather than weakening an invariant.
            # In particular L15 has an explicit \penalty-10000 before protected glue;
            # we cannot assume that every changed line is harmless.
            import difflib
            for line in difflib.unified_diff(
                a["text"].splitlines(), b["text"].splitlines(),
                fromfile=f"before/{case['id']}", tofile=f"after/{case['id']}",
                lineterm="",
            ):
                print('    ' + line)
    (root / "checks.json").write_text(json.dumps({"cases":rows,"errors":errors,"conflicts":conflicts},ensure_ascii=False,indent=2)+"\n")
    for x in conflicts:
        print(f"FORCED: {x['id']}: math penalty -10000 must still break; {x['before_join']} -> {x['after_join']}")
    if errors:
        print(f"FAIL: {len(errors)} regression checks failed (see checks.json)")
        return 1
    print(f"PASS: {len(rows)} cases; protected glue, forced breaks and controls satisfied.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 check.py OUTPUT_DIR")
    raise SystemExit(check(Path(sys.argv[1]).resolve()))
