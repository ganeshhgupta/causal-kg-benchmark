#!/usr/bin/env python3
"""Flag claims that are RELATED but whose evidence coverage is asymmetric.

The error class, stated generally: if a body of evidence bears on a claim, it
normally also bears on claims that share the same canonical predicate and differ
only in which specific agents or comparators are named. When a piece of evidence
is attached to one and not the other, that is either a real scope distinction
(the study simply did not test that drug) or a curation gap.

The checker cannot tell those apart, and does not try. It reports the asymmetry
and demands that each one be either wired up or justified. The point is that the
gap becomes VISIBLE, rather than depending on someone noticing by hand.

Why this exists rather than a one-line patch: this class of error has now been
found twice by external readers rather than by the pipeline, both times in
hand-curated graphs. A detector generalises; a patch does not.

Usage:
    python3 compiler/check_evidence_coverage.py <graph.json> [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from canonicalize import compare, load_equivalences  # noqa: E402

# Evidence sources naming a drug/agent the related claim does not involve are
# expected to be scoped; this is only used to soften the report, never to hide.
def _scope_hint(ev_source: str, prop_text: str) -> str:
    return ""


def _src_tokens(x: str) -> set:
    import re
    stop = {"by", "the", "of", "in", "and", "et", "al", "trials", "authors", "other",
            "than", "pooled", "some", "evidence", "between", "no"}
    return {t for t in re.findall(r"[a-z0-9]+", x.lower()) if t not in stop and len(t) > 2}


def same_evidence(a: str, b: str, thresh: float = 0.5) -> bool:
    """Whether two source strings plausibly denote the SAME underlying study.

    Needed because one corpus records Carlisle's pooled non-Fujii result as
    "trials by other authors: no synergism, some evidence of antagonism
    (Carlisle 2012)" and another as "trials by authors other than Fujii, pooled
    by Carlisle 2012: no synergism between antiemetics, some evidence of
    antagonism". Same study, two strings. This is evidence-level identity, the
    exact analogue of the claim-level canonicalization problem, and it is
    currently solved by lexical overlap rather than by declared identity, which
    is a known weakness recorded rather than hidden.
    """
    ta, tb = _src_tokens(a), _src_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= thresh


def claim_text(p: dict) -> str:
    return " ".join(p.get("surface_forms") or []) or p["id"]


def check(graphs: list[tuple[str, dict]]):
    equiv = load_equivalences()
    props, ev_by_prop, origin = {}, {}, {}
    for name, g in graphs:
        for p in g.get("propositions", []):
            props[p["id"]] = p
            origin[p["id"]] = name
        for e in g.get("evidence", []):
            ev_by_prop.setdefault(e["proposition_id"], []).append(e)

    findings = []
    ids = sorted(props)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            verdict, why = compare(props[a], props[b], equiv)
            if verdict != "RELATED":
                continue
            ea, eb = ev_by_prop.get(a, []), ev_by_prop.get(b, [])
            # Compare only evidence that is NOT from the author under suspicion,
            # i.e. evidence that would survive a retraction and therefore
            # determines REFUTED vs UNRESOLVED.
            def independent(evs):
                return {e["id"]: e for e in evs
                        if (e.get("independence_group") or "").upper().startswith("NON-")}
            ia, ib = independent(ea), independent(eb)
            for side, (have, lack, hp, lp) in (
                    ("a", (ia, ib, a, b)), ("b", (ib, ia, b, a))):
                lack_notes = (props[lp].get("notes") or "")
                for eid, e in have.items():
                    if any(o["source"] == e["source"] for o in lack.values()):
                        continue
                    if any(same_evidence(o["source"], e["source"]) for o in lack.values()):
                        continue  # same study recorded under a different string
                    # An asymmetry explicitly adjudicated in the claim's notes is a
                    # recorded decision, not an oversight. Convention:
                    #   EVIDENCE-SCOPE: <evidence id>, ... do NOT apply. <reason>
                    if "EVIDENCE-SCOPE:" in lack_notes and eid in lack_notes:
                        continue
                    findings.append({
                        "evidence": eid,
                        "attached_to": hp,
                        "missing_from": lp,
                        "stance": e["stance"],
                        "why_related": why,
                        "source": e["source"],
                        "graphs": (origin[hp], origin[lp]),
                    })
    return findings


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        root = Path(__file__).parent.parent / "scientific-dependency" / "corpus"
        argv = [str(p) for p in sorted(root.glob("*.json"))]
    graphs = []
    for a in argv:
        with open(a, encoding="utf-8") as fh:
            graphs.append((Path(a).name, json.load(fh)))

    findings = check(graphs)
    print(f"graphs: {len(graphs)}   asymmetries found: {len(findings)}\n")
    for f in findings:
        same = f["graphs"][0] == f["graphs"][1]
        print(f"  {f['evidence']}  ({f['stance']})")
        print(f"     attached to  {f['attached_to']}   [{f['graphs'][0]}]")
        print(f"     MISSING from {f['missing_from']}   [{f['graphs'][1]}]"
              f"{'' if same else '   (cross-graph)'}")
        print(f"     related because: {f['why_related']}")
        print(f"     source: {f['source'][:88]}")
        print()
    if findings:
        print("Each of these must be either wired up or justified in the claim's notes. "
              "An asymmetry is not automatically a bug: the study may genuinely not have "
              "tested the other agent. But it must be a decision, not an oversight.")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
