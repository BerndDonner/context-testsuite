"""Adversarial exploratory tests for inline-math penalties and following glue.

The case generation is intentionally broader than the normative oracle. Most
outcomes are observations, not claims about the intended ConTeXt design.
No other repository or engine build is imported by this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess


@dataclass(frozen=True)
class Probe:
    id: str
    family: str
    math: str
    marker: str
    glue: str
    setup: str
    expr: str
    width: int
    expectation: str  # protect, force-explicit, force-math-question, force-math-unprotected, observe
    reason: str
    pair: str = ""


MATH = {"long": (r"\math{12345}", "12345"), "short": (r"\math{1}", "1")}


def _glue_expr(kind: str, *, glue_penalty: int | None = None) -> str:
    if kind == "tilde":
        return "~"
    if kind == "normal":
        return r"\space "
    if kind == "nobreakspace":
        return r"\nobreakspace "
    options = {"direct-plain": 0, "direct-protected": 1,
               "direct-space": 4096, "direct-protected-space": 4097,
               "direct-nondiscardable": 128, "direct-protected-nondiscardable": 129,
               "direct-zero": 0, "direct-protected-zero": 1,
               "direct-limit": 8, "direct-protected-limit": 9}[kind]
    width = 0 if "zero" in kind else 3 * 65536
    lua = f"local n=node.new('glue'); n.width={width}; n.options={options}; "
    if glue_penalty is not None:
        lua += f"n.penalty={glue_penalty}; "
    lua += "node.write(n)"
    return r"\directlua{" + lua + "}"


def _protected(glue: str) -> bool:
    return glue in ("tilde", "nobreakspace") or glue.startswith("direct-protected")


def probes() -> list[Probe]:
    """Deterministic reproducible broad matrix; no random or external inputs."""
    cases: list[Probe] = []

    def add(family: str, math: str, glue: str, setup: str, *, width: int = 67,
            prefix: str = "", suffix: str = "", force: str = "", glue_penalty: int | None = None,
            pair: str = "", reason: str = "") -> None:
        formula, marker = MATH[math]
        expr = formula + prefix + force + _glue_expr(glue, glue_penalty=glue_penalty) + suffix + "stelliges"
        # An explicitly inserted penalty node is a textbook force, independently
        # of how math-specific penalty parameters are interpreted.
        if force == r"\penalty-10000 ":
            expected = "force-explicit"
        elif (r"\postinlinepenalty=-10000" in setup or
              (math == "short" and r"\postshortinlinepenalty=-10000" in setup)):
            expected = "force-math-question" if _protected(glue) else "force-math-unprotected"
        elif _protected(glue) and glue_penalty is None and (
            r"\postinlinepenalty=0" in setup or not r"\postinlinepenalty=" in setup
        ) and (math != "short" or r"\postshortinlinepenalty=-10000" not in setup):
            expected = "protect"
        else:
            expected = "observe"
        cases.append(Probe(id=f"A{len(cases)+1:04}", family=family,
                           math=math, marker=marker, glue=glue, setup=setup,
                           expr=expr, width=width, expectation=expected,
                           reason=reason, pair=pair))

    # Factorial sweep of the boundary that Hans's helper explicitly handles.
    glue_types = ("tilde", "normal", "direct-plain", "direct-protected",
                  "direct-space", "direct-protected-space", "direct-nondiscardable",
                  "direct-protected-nondiscardable", "direct-zero", "direct-protected-zero")
    for math in MATH:
        for surround in (0, 3):
            for penalty in (-10000, -500, 0, 500, 10000):
                setup = rf"\mathsurround={surround}pt\postinlinepenalty={penalty}"
                for glue in glue_types:
                    add("post-inline", math, glue, setup,
                        pair=f"inline/{math}/{surround}/{penalty}/{glue.removeprefix('direct-protected').removeprefix('direct-')}",
                        reason="Post-inline penalty vs. following glue/options")

    # Real short-inline path is separate; a long formula won't exercise it.
    for short_penalty in (-10000, -500, 0, 500, 10000):
        for glue in ("tilde", "normal", "direct-plain", "direct-protected", "direct-protected-space"):
            add("post-short", "short", glue,
                rf"\postinlinepenalty=0\postshortinlinepenalty={short_penalty}",
                reason="True short inline math, not a long formula with a short penalty")

    # Factor scaling: do NOT assume the meaning/units of the factor; observe.
    for factor in (0, 1000, 2000, 20000):
        for penalty in (-10000, -500, 500, 10000):
            for glue in ("normal", "tilde", "direct-plain", "direct-protected"):
                add("factor", "long", glue,
                    rf"\postinlinepenalty={penalty}\mathinlinepenaltyfactor={factor}",
                    reason="Inspect interactions with mathinlinepenaltyfactor")

    # Direct penalty node: strong local assertion, different from a math-penalty.
    for math in MATH:
        for glue in ("tilde", "normal", "direct-plain", "direct-protected",
                     "direct-protected-space"):
            for surround in (0, 3):
                add("explicit-force", math, glue, rf"\mathsurround={surround}pt",
                    force=r"\penalty-10000 ",
                    reason="Explicit penalty node -10000 must force a break")

    # Exercise the second field compared in Hans's helper, glue_penalty(next).
    # Kept in its own compilation shards: experimental field availability must
    # never invalidate otherwise usable results from the main matrix.
    for p in (-10000, 0, 10000):
        for math in MATH:
            for glue in ("direct-plain", "direct-protected"):
                for mpenalty in (-10000, 0, 10000):
                    add("glue-penalty-field", math, glue,
                        rf"\postinlinepenalty={mpenalty}", glue_penalty=p,
                        reason="Experimental Lua glue.penalty field; inspect precedence")

    # Dimensional / math-surround branch differences and geometrical robustness.
    for surround_mode in (4, 6):
        for penalty in (-10000, 0, 10000):
            for math in MATH:
                for glue in ("tilde", "normal", "direct-plain", "direct-protected"):
                    add("surround-mode", math, glue,
                        rf"\mathsurroundmode={surround_mode}\mathsurroundskip=2pt\postinlinepenalty={penalty}",
                        reason="Exercise nonzero math glue and surround mode")

    for width in (54, 80):
        for math in MATH:
            for penalty in (-10000, 0, 10000):
                for glue in ("tilde", "normal", "direct-plain", "direct-protected"):
                    add("width", math, glue, rf"\postinlinepenalty={penalty}", width=width,
                        reason="Check whether an apparent rule depends on frame width")

    # Explicit before-math penalties are out of scope of the end-math helper;
    # still useful controls for unanticipated line break changes.
    for penalty in (-10000, 0, 10000):
        for glue in ("tilde", "normal", "direct-protected"):
            add("pre-inline-control", "long", glue,
                rf"\preinlinepenalty={penalty}\postinlinepenalty=0",
                reason="Unrelated pre-inline penalty should be inspected, not inferred")

    # DESIGN-2026-10-28: Comparisons rather than an assumed penalty oracle.
    # Only fixture generation is extended here; compilation, extraction and
    # interpretation code remain unchanged. Existing A0001..A0450 stay stable.
    #
    # A noautobreak glue option inhibits an *automatic glue breakpoint*; it
    # does not logically erase an independent explicit penalty node.  Compare
    # identical neighbors after math, an hbox, and ordinary glyphs.
    def design_probe(family: str, source_kind: str, glue: str, setup: str,
                     *, between: str = "", width: int = 67,
                     glue_penalty: int | None = None, pair: str, reason: str) -> None:
        fragments = {
            "math": r"\math{12345}",
            "hbox": r"\hbox{12345}",
            "text": "12345",
        }
        formula = fragments[source_kind]
        glue_expr = _glue_expr(glue, glue_penalty=glue_penalty)
        if glue_penalty is not None:
            # Some Lua node setters may toggle option bits. Set them AFTER the
            # penalty field so these probes genuinely leave has_penalty unset.
            # This is fixture generation only; existing probes are untouched.
            final_options = 1 if glue == "direct-protected" else 0
            glue_expr = glue_expr.replace("node.write(n)", f"n.options={final_options}; node.write(n)")
        expr = formula + between + glue_expr + "stelliges"
        protected = _protected(glue)
        if between == r"\penalty-10000 ":
            expectation = "force-explicit"
        elif between:
            # A preceding explicit penalty (even zero) may create its OWN
            # breakpoint. No claim about its priority is baked into the test.
            expectation = "observe"
        elif source_kind != "math":
            expectation = "protect" if protected and glue_penalty is None else "observe"
        elif glue_penalty is not None:
            expectation = "observe"
        elif r"\postinlinepenalty=-10000" in setup:
            expectation = "force-math-question" if protected else "force-math-unprotected"
        elif protected and r"\postinlinepenalty=0" in setup:
            expectation = "protect"
        else:
            expectation = "observe"
        cases.append(Probe(
            id=f"A{len(cases)+1:04}", family=family, math=source_kind,
            marker="12345", glue=glue, setup=setup, expr=expr,
            width=width, expectation=expectation, reason=reason, pair=pair,
        ))

    # 1. Control for whether the noautobreak bit acts differently immediately
    #    after math than after a regular box or glyph.  A penalty-0 node before
    #    protected glue tests the key distinction: no AUTO break != no break.
    for source_kind in ("math", "hbox", "text"):
        for intervening, between in (
            ("adjacent", ""),
            ("relax", r"\relax "),
            ("kern0", r"\kern0pt\relax "),
            ("penalty0", r"\penalty0 "),
            ("force", r"\penalty-10000 "),
        ):
            for glue in ("normal", "tilde", "nobreakspace", "direct-plain", "direct-protected"):
                design_probe(
                    "noautobreak-neighbors", source_kind, glue,
                    r"\postinlinepenalty=0", between=between,
                    pair=f"neighbor/{source_kind}/{intervening}/{glue}",
                    reason="Compare automatic glue inhibition after math, box and text; penalty nodes are independent breakpoints",
                )

    # 2. Find discontinuities at the conventional forced/forbidden values
    #    and at their immediate neighbors.  Repeated widths distinguish
    #    conditional line-breaking decisions from unconditional suppression.
    for width in (67, 80):
        for penalty in (-10000, -9999, -1, 0, 1, 9999, 10000):
            for glue in ("normal", "tilde", "direct-plain", "direct-protected"):
                design_probe(
                    "noautobreak-boundaries", "math", glue,
                    rf"\postinlinepenalty={penalty}", width=width,
                    pair=f"boundary/{width}/{penalty}/{glue}",
                    reason="Probe negative/positive penalty boundaries with and without glue noautobreak",
                )

    # 3. Hans's proposed helper reads glue_penalty(next) even when the node's
    #    glue_option_has_penalty flag has not been enabled. The existing
    #    direct Lua glue uses options=0/1, not the has_penalty option. Test
    #    whether this *data field alone* changes behavior after inline math.
    #    As in the first matrix, these are isolated in experimental shards.
    for math_penalty in (-10000, -500, 0, 500):
        for glue_penalty in (-10000, -1, 0, 1, 500, 10000):
            for glue in ("direct-plain", "direct-protected"):
                design_probe(
                    "glue-penalty-field", "math", glue,
                    rf"\postinlinepenalty={math_penalty}",
                    glue_penalty=glue_penalty,
                    pair=f"field/{math_penalty}/{glue_penalty}/{glue}",
                    reason="Does an unmarked glue.penalty field affect the math breakpoint; noautobreak precedence?",
                )

    # 4. In the helper, the glue-penalty-overrides-math branch returns early,
    #    bypassing math_penalty_factor. We do not assume a factor's meaning;
    #    we compare its effect across both sides of the branch condition.
    for factor in (0, 1000, 20000):
        for math_penalty in (-1000, 0, 1000):
            for glue_penalty in (0, 1, 2000):
                for glue in ("direct-plain", "direct-protected"):
                    design_probe(
                        "glue-penalty-field", "math", glue,
                        rf"\postinlinepenalty={math_penalty}\mathinlinepenaltyfactor={factor}",
                        glue_penalty=glue_penalty,
                        pair=f"factor/{math_penalty}/{glue_penalty}/{factor}/{glue}",
                        reason="Does mathinlinepenaltyfactor depend on glue field comparison and noautobreak?",
                    )

    assert len(cases) == len({p.id for p in cases})
    return cases


def _doc(group: list[Probe]) -> str:
    lines = [r"\mainlanguage[de]", r"\setuppapersize[A5]",
             r"\setuplayout[width=110mm,height=175mm,backspace=15mm,topspace=12mm,header=0pt,footer=0pt]",
             r"\starttext"]
    for index, p in enumerate(group):
        if index:
            lines.append(r"\page")
        lines.extend((r"\begingroup", p.setup, r"\subject{" + p.id + "}",
                      rf"\startframedtext[width={p.width}mm]",
                      f"Das digitale Geraet hat ein {p.expr} Display und einen Fehler.",
                      r"\stopframedtext", r"\endgroup"))
    lines.append(r"\stoptext")
    return "\n".join(lines) + "\n"


def _read_pages(pdf: Path, group: list[Probe]) -> list[dict]:
    import pymupdf
    with pymupdf.open(pdf) as doc:
        if len(doc) != len(group):
            raise ValueError(f"Expected {len(group)} PDF pages, found {len(doc)}")
        result = []
        for p, page in zip(group, doc):
            # Consistent with the existing 76-case suite: pdftotext -layout.
            # This second, independent extraction provides a diagnostic backstop
            # if the PDF content cannot be reliably interpreted.
            result.append({"pymupdf_excerpt": page.get_text(sort=True)[:260]})
    return result


def _extract(txt: Path, pdf: Path, group: list[Probe]) -> list[dict]:
    chunks = [x for x in txt.read_text(encoding="utf-8").split("\f") if x.strip()]
    if len(chunks) != len(group):
        raise ValueError(f"Expected {len(group)} text pages, found {len(chunks)}")
    extra = _read_pages(pdf, group)
    rows = []
    for p, chunk, fallback in zip(group, chunks, extra):
        lines = chunk.splitlines()
        if not any(re.search(rf"\b{re.escape(p.id)}\b", s) for s in lines):
            raise ValueError(f"Missing page ID {p.id} in PDF text")
        # The body prefix and math marker need not be on the same line:
        # narrow frames and pre-inline -10000 intentionally separate them.
        body_start = [i for i, line in enumerate(lines) if "Das digitale Geraet" in line]
        if len(body_start) != 1:
            rows.append({"status": "unclassifiable", "reason": "body not uniquely recognized", **fallback})
            continue
        body = lines[body_start[0]:]
        marker_pattern = re.compile(rf"(?<![0-9]){re.escape(p.marker)}(?![0-9])")
        locations = [(line, match) for line in body for match in marker_pattern.finditer(line)]
        if len(locations) != 1:
            rows.append({"status": "unclassifiable", "reason": "math marker not unique in body", **fallback})
            continue
        line, match = locations[0]
        tail = line[match.end():]
        # Classify the relationship immediately AFTER the formula, not a
        # coincidental 'ste' somewhere else on the line.  'stel-' counts as
        # joined: word hyphenation after math is a different breakpoint.
        joined = re.match(r"\s*ste", tail) is not None
        text = "\n".join(body).strip()
        rows.append({"status": "observed", "joined": joined, "body": text, **fallback})
    return rows


def _compile(context: str, group: list[Probe], target: Path, cache_root: Path) -> tuple[list[dict] | None, dict]:
    target.mkdir(parents=True, exist_ok=True)
    tex = target / "cases.tex"
    tex.write_text(_doc(group), encoding="utf-8")
    env = os.environ.copy()
    home = cache_root / "home"
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["TEXMFCACHE"] = str(cache_root / "tex-cache")
    pdf = target / "cases.pdf"
    log = target / "build.log"
    try:
        with log.open("w", encoding="utf-8") as stream:
            proc = subprocess.run([context, "--once", tex.name], cwd=target, env=env,
                                  stdout=stream, stderr=subprocess.STDOUT, check=False,
                                  timeout=600)
        if proc.returncode:
            return None, {"status": "compile-error", "exit_code": proc.returncode, "log": str(log)}
        if not pdf.is_file():
            raise ValueError("PDF missing after successful process")
        txt = target / "cases.txt"
        with txt.open("w", encoding="utf-8") as stream:
            extract = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                                     stdout=stream, stderr=subprocess.PIPE, check=False)
        if extract.returncode:
            raise ValueError("pdftotext failed: " + extract.stderr.decode(errors="replace"))
        return _extract(txt, pdf, group), {"status": "ok", "log": str(log), "pdf": str(pdf), "text": str(txt)}
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\nAdversarial runner error: {exc}\n")
        return None, {"status": "harness-error", "log": str(log), "error": str(exc)}


def _compile_resilient(context: str, group: list[Probe], target: Path,
                       cache_root: Path) -> tuple[list[dict | None], dict]:
    """Bisect a failing shard, preserving all independently buildable cases.

    The first pass remains one combined 40-page PDF. Only an error triggers
    smaller documents. Error logs stay next to their respective source.
    """
    observed, status = _compile(context, group, target, cache_root)
    if observed is not None:
        return observed, status
    if len(group) == 1:
        return [None], {**status, "failed_case": group[0].id}
    pivot = len(group) // 2
    left, ls = _compile_resilient(context, group[:pivot], target / "bisect-left", cache_root)
    right, rs = _compile_resilient(context, group[pivot:], target / "bisect-right", cache_root)
    failures = sum(x is None for x in (*left, *right))
    return left + right, {"status": "partial" if failures < len(group) else "compile-error",
                          "failed_cases": failures, "initial": status,
                          "bisected": [ls, rs]}


def _interpret(p: Probe, candidate: dict | None, baseline: dict | None) -> dict:
    if candidate is None:
        return {"case": asdict(p), "status": "not-run", "flags": [], "candidate": None, "baseline": baseline}
    flags = []
    if candidate["status"] == "unclassifiable":
        flags.append("extraction-uncertain")
    elif p.expectation == "force-explicit" and candidate["joined"]:
        flags.append("explicit-force-violation")
    elif p.expectation == "protect" and not candidate["joined"]:
        flags.append("protected-glue-violation")
    elif p.expectation == "force-math-question" and candidate["joined"]:
        flags.append("math-force-priority-question")
    elif p.expectation == "force-math-unprotected" and candidate["joined"]:
        # High-value case: a forced math penalty is apparently neutralized
        # even by ordinary glue, WITHOUT a noautobreak-priority conflict.
        flags.append("math-force-unprotected-question")
    if baseline is not None and candidate.get("status") == baseline.get("status") == "observed":
        if candidate["joined"] != baseline["joined"]:
            flags.append("break-changed-vs-baseline")
        elif candidate["body"] != baseline["body"]:
            flags.append("text-changed-vs-baseline")
    return {"case": asdict(p), "status": candidate["status"],
            "flags": flags, "candidate": candidate, "baseline": baseline}


def _write_repro(dest: Path, p: Probe) -> None:
    """Independent minimal input, no other fixture sources needed."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{p.id}.tex").write_text(_doc([p]), encoding="utf-8")


def _report(out: Path, results: list[dict], shards: list[dict], candidate: str, baseline: str | None) -> dict:
    counts = Counter(flag for row in results for flag in row["flags"])
    counts["not-run"] += sum(row["status"] == "not-run" for row in results)
    counts["unclassifiable"] += sum(row["status"] == "unclassifiable" for row in results)
    counts["reference-not-run"] += sum(baseline is not None and row["baseline"] is None for row in results)
    hard = counts["explicit-force-violation"] + counts["protected-glue-violation"]
    suspicious = counts["math-force-priority-question"] + counts["math-force-unprotected-question"]
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "candidate_context": candidate, "reference_context": baseline,
              "note": "Adversarial exploration: math-force priority is a QUESTION, not a proven defect. Only explicit force/protected glue are provisional hard invariants; PDF extraction can misclassify.",
              "total": len(results), "counts": dict(counts), "hard_failures": hard,
              "questions": suspicious, "shards": shards, "cases": results}
    (out / "observations.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidates = [row for row in results if row["flags"]]
    (out / "findings.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    repro = out / "repros"
    for row in candidates:
        # Reproduction is generated only for positive findings.
        _write_repro(repro, Probe(**row["case"]))
    priority = ("explicit-force-violation", "protected-glue-violation",
                "math-force-unprotected-question", "math-force-priority-question",
                "break-changed-vs-baseline", "text-changed-vs-baseline", "extraction-uncertain")
    sorted_cases = sorted(candidates, key=lambda row: (next((i for i, flag in enumerate(priority) if flag in row["flags"]), 99), row["case"]["id"]))
    lines = ["# Math-adversarial findings", "",
             f"Total probes: {len(results)}; incomplete: {counts['not-run']}; reference incomplete: {counts['reference-not-run']}; unclassifiable: {counts['unclassifiable']}",
             f"Strong-invariant candidates: {hard}; semantic questions: {suspicious}.", "",
             "Interpretation: forced math penalties lost even with *ordinary, unprotected glue* are separate from the disputed noautobreak-precedence cases. Both are questions pending semantic verification; output differences alone do not establish a bug.",
             "", "## Findings (sorted by priority)", ""]
    for row in sorted_cases:
        p = row["case"]
        a = row["baseline"]
        b = row["candidate"]
        def desc(v):
            if v is None: return "not-run"
            if v.get("status") != "observed": return v.get("status", "unknown")
            return "join" if v["joined"] else "split"
        lines.append(f"- **{p['id']}** ({p['family']}): {desc(a)} → {desc(b)}; {', '.join(row['flags'])}; repro: `repros/{p['id']}.tex`")
    if not sorted_cases:
        lines.append("No semantic flags from completed cases. This is not proof of correctness.")
    lines.append("\n## Compilation shards\n")
    for shard in shards:
        lines.append(f"- {shard['id']}: {shard['first']}…{shard['last']} / reference={shard['reference']['status']} / candidate={shard['candidate']['status']}")
    (out / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def run_adversarial(candidate: str, baseline: str | None, output: Path, *, shard_size: int = 40) -> dict:
    """Run all cases, retaining partial results even after compile errors.

    The glue-penalty-field experiments run in their OWN shards, to make
    incompatibilities visible without discarding the main experiment.
    """
    if shard_size < 1:
        raise ValueError("shard_size must be >=1")
    out = output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    all_cases = probes()
    (out / "case-index.json").write_text(
        json.dumps([asdict(p) for p in all_cases], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    buckets: dict[str, list[Probe]] = defaultdict(list)
    for p in all_cases:
        buckets["experimental" if p.family == "glue-penalty-field" else "main"].append(p)
    chunks = [part[i:i+shard_size] for part in buckets.values() for i in range(0, len(part), shard_size)]
    rows = []
    shards = []
    for i, part in enumerate(chunks, 1):
        name = f"shard-{i:03}"
        folder = out / name
        ref, refstatus = (None, {"status": "not-requested"})
        if baseline:
            ref, refstatus = _compile_resilient(baseline, part, folder / "reference", out / "cache" / "reference")
        cand, candstatus = _compile_resilient(candidate, part, folder / "candidate", out / "cache" / "candidate")
        print(f"{name} {part[0].id}..{part[-1].id}: reference={refstatus['status']} candidate={candstatus['status']}", flush=True)
        shards.append({"id": name, "first": part[0].id, "last": part[-1].id,
                       "reference": refstatus, "candidate": candstatus})
        rows.extend(_interpret(p, cand[j], (ref[j] if ref is not None else None)) for j, p in enumerate(part))
    result = _report(out, rows, shards, candidate, baseline)
    print(f"Math adversarial: {len(rows)} probes, {result['hard_failures']} strong-invariant candidates, {result['questions']} semantic questions", flush=True)
    print(f"Findings: {out / 'findings.md'}", flush=True)
    # Warnings and observed baseline changes are NOT made into hard failures.
    # Incomplete runs are reported as errors (not a spurious successful test).
    if (result["counts"].get("not-run", 0) or result["counts"].get("reference-not-run", 0)
            or result["counts"].get("unclassifiable", 0)):
        return {"result": "incomplete", "exit_code": 2, "report": str(out / "observations.json")}
    if result["hard_failures"]:
        return {"result": "fail", "exit_code": 1, "report": str(out / "observations.json")}
    return {"result": "pass_observational", "exit_code": 0, "report": str(out / "observations.json")}
