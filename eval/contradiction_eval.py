#!/usr/bin/env python3
"""Measure contradiction detection recall and the false-contradiction rate.

Two stated targets:

    contradiction detection recall   >= 95%
    false contradiction rate         <  1%

Two kinds of contradiction exist in a K-IR graph and both are measured:

  EVIDENCE-LEVEL   one proposition carries active supporting AND active refuting
                   evidence, so its computed status is INCONSISTENT.

  STRUCTURAL       two distinct propositions that cannot both hold. The only
                   mechanism v0.3 has for deriving these is Symbol.functional on
                   a relation: two propositions over a functional relation that
                   share the determining argument but differ on the determined
                   one.

The false-contradiction side is where this project has always expected to fail,
so the gold set deliberately includes traps that LOOK contradictory and are not:
the same drug pointing in opposite directions under DIFFERENT contexts
(monotherapy vs versus-placebo), which is the water-at-0-4C lesson, and a pair
over a set-valued relation where differing values are perfectly compatible.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph  # noqa: E402

CORPORA = [
    "scientific-dependency/corpus/fujii-ponv.json",
    "scientific-dependency/corpus/fujii-combination-review.json",
]

# Gold: which propositions are genuinely internally contradicted (evidence-level).
GOLD_INCONSISTENT = {
    "P-SYNERGISM":
        "Fujii trials imply synergism; Carlisle reports no synergism and some "
        "antagonism in other authors' trials. Genuine live conflict.",
    "P-DROPERIDOL-INFERIOR":
        "Fujii trials show droperidol much worse than granisetron; other authors "
        "find rescue rates not different. Genuine conflict.",
    "P-MULTI-RECEPTOR-PRINCIPLE":
        "Fujii's review asserts the combination principle; Carlisle's non-Fujii "
        "pooling refutes it. Genuine conflict.",
    "P-TRAD-ADJUNCT-SUPERIOR":
        "ADDED cycle 10, as a necessary consequence of wiring EV-CARLISLE-TRAD. Fujii's "
        "trials support the 5-HT3-plus-traditional-antiemetic combination; Carlisle's pool "
        "of other authors' trials covering exactly those drugs found no synergism and some "
        "antagonism. Same live conflict as P-SYNERGISM and P-MULTI-RECEPTOR-PRINCIPLE. This "
        "is the second time this gold list has gone stale behind a corrected corpus, which "
        "is itself the argument for deriving it from the graph rather than hand-listing it.",
    "P-GRANI-ALONE-WORSE":
        "ADDED cycle 7, as a necessary consequence of resolving that claim's label. "
        "Carlisle pairs the sentences explicitly ('no synergism ... IN CONTRAST, in "
        "studies by Fujii et al., PONV was more likely if granisetron was administered "
        "alone'), so the non-Fujii null refutes it while the Fujii trials support it. "
        "That is the same live conflict as P-SYNERGISM. This entry was previously "
        "absent because the claim was mis-labelled as having no non-Fujii evidence at "
        "all; once that was corrected the detector was right and this gold list was "
        "stale, not the other way round.",
}

# Gold: pairs that must NOT be reported as contradicting each other.
GOLD_NON_CONTRADICTIONS = [
    (("P-GRANI-EFFECTIVE", "P-GRANI-ALONE-WORSE"),
     "THE TRAP. Same drug, opposite direction, but different CONTEXTS: one is "
     "granisetron versus placebo, the other granisetron as sole agent. Both can "
     "hold. Flagging this is the water-at-0-4C error."),
    (("P-GRANI-EFFECTIVE", "P-RAMO-EFFECTIVE"),
     "Two drugs both effective. Compatible."),
    (("P-DEX-ENHANCES", "P-TRAD-ADJUNCT-SUPERIOR"),
     "Two different adjuncts both beating monotherapy. Compatible, and REDUCES "
     "is set-valued, so differing values imply nothing."),
    (("P-TRAD-COMBO-LIMITED", "P-COMBO-NOT-MORE-TOXIC"),
     "A CNS-toxicity limit on traditional combinations is compatible with "
     "multi-receptor combinations not raising adverse effects. Different scopes."),
    (("P-DEX-ENHANCES", "P-MULTI-RECEPTOR-PRINCIPLE"),
     "A specific instance and the general principle. Entailment, not conflict."),
]


def load_all():
    props, symbols, graphs = {}, {}, []
    for rel in CORPORA:
        data = json.load(open(ROOT / rel, encoding="utf-8"))
        graphs.append(Graph(data))
        for s in data.get("symbols", []):
            symbols.setdefault(s["id"], s)
        for p in data["propositions"]:
            props[p["id"]] = p
    return props, symbols, graphs


def detect_evidence_level(graphs):
    """INCONSISTENT status is the detector. No extra machinery."""
    found = set()
    for g in graphs:
        statuses, _ = g.status_map()
        found |= {pid for pid, st in statuses.items() if st == "INCONSISTENT"}
    return found


def detect_structural(props, symbols):
    """Derive contradictions from Symbol.functional, honouring context.

    Fires only when: the relation is declared functional, the two propositions
    agree on every argument but one, they share the SAME context, and both
    differing fillers are RESOLVED symbols (distinct ids are not distinct
    referents until identity resolution says so).
    """
    flagged = []
    for a, b in itertools.combinations(sorted(props), 2):
        pa, pb = props[a], props[b]
        if pa["predicate"] != pb["predicate"]:
            continue
        rel = symbols.get(pa["predicate"], {})
        if rel.get("functional") is not True:
            continue
        if pa.get("context") != pb.get("context"):
            continue
        if pa.get("polarity") != pb.get("polarity"):
            continue
        aa = {x["role"]: json.dumps(x["term"], sort_keys=True) for x in pa["arguments"]}
        ab = {x["role"]: json.dumps(x["term"], sort_keys=True) for x in pb["arguments"]}
        if set(aa) != set(ab):
            continue
        diff = [r for r in aa if aa[r] != ab[r]]
        if len(diff) != 1:
            continue
        refs = []
        for p, args in ((pa, aa), (pb, ab)):
            term = json.loads(args[diff[0]])
            refs.append(term.get("symbol_ref"))
        if any(r is None for r in refs):
            continue
        if any(symbols.get(r, {}).get("resolution_status") != "RESOLVED" for r in refs):
            continue
        flagged.append((a, b))
    return flagged


def main():
    props, symbols, graphs = load_all()

    missing = [p for p in GOLD_INCONSISTENT if p not in props]
    missing += [p for pair, _ in GOLD_NON_CONTRADICTIONS for p in pair if p not in props]
    if missing:
        print(f"gold names unknown propositions: {sorted(set(missing))}", file=sys.stderr)
        return 2

    detected = detect_evidence_level(graphs)
    structural = detect_structural(props, symbols)

    print(f"claims across {len(CORPORA)} real corpora: {len(props)}")
    print(f"gold internally-contradicted claims: {len(GOLD_INCONSISTENT)}")
    print(f"gold must-not-contradict pairs: {len(GOLD_NON_CONTRADICTIONS)}\n")

    # --- recall on evidence-level contradictions --------------------------
    tp = sorted(set(GOLD_INCONSISTENT) & detected)
    fn = sorted(set(GOLD_INCONSISTENT) - detected)
    fp = sorted(detected - set(GOLD_INCONSISTENT))

    print("evidence-level contradiction detection:")
    for pid in sorted(GOLD_INCONSISTENT):
        mark = "detected" if pid in detected else "MISSED"
        print(f"  {pid:28} {mark}")
    for pid in fp:
        print(f"  {pid:28} FALSE POSITIVE (not in gold)")

    recall = len(tp) / len(GOLD_INCONSISTENT) if GOLD_INCONSISTENT else 0.0

    # --- false contradictions --------------------------------------------
    struct_set = {tuple(sorted(p)) for p in structural}
    print("\nmust-not-contradict pairs:")
    false_contra = []
    for pair, why in GOLD_NON_CONTRADICTIONS:
        key = tuple(sorted(pair))
        bad = key in struct_set
        if bad:
            false_contra.append(key)
        print(f"  {'FLAGGED (WRONG)' if bad else 'clean':16} {pair[0]} + {pair[1]}")
        if bad:
            print(f"                   why it is not a contradiction: {why}")

    if structural:
        print("\nstructural contradictions derived from Symbol.functional:")
        for a, b in structural:
            print(f"  {a} + {b}")
    else:
        print("\nno structural contradictions derived (no functional relation in "
              "these corpora has a same-context, single-argument-difference pair)")

    # Denominator for the false rate: every claim pair considered, since any of
    # them could have been wrongly flagged.
    considered = len(list(itertools.combinations(props, 2)))
    total_false = len(false_contra) + len(fp)
    false_rate = total_false / considered if considered else 0.0

    print()
    print(f"contradiction recall        {len(tp)}/{len(GOLD_INCONSISTENT)} = "
          f"{recall:.4f}   target >= 0.95  {'PASS' if recall >= 0.95 else 'FAIL'}")
    print(f"false contradictions        {total_false} over {considered} pairs "
          f"considered = {false_rate:.4f}   target < 0.01  "
          f"{'PASS' if false_rate < 0.01 else 'FAIL'}")
    print()
    print("HONEST SCOPE: recall here is over EVIDENCE-LEVEL conflict, which is "
          "cheap because INCONSISTENT status already encodes it. The hard kind, "
          "two separately-stated claims that cannot both hold, is only derivable "
          "via Symbol.functional, and neither real corpus contains a functional "
          "relation with a qualifying pair. So structural contradiction detection "
          "is effectively UNTESTED on real data, and the clean false rate partly "
          "reflects a detector that rarely fires rather than one that is precise.")
    return 0 if (recall >= 0.95 and false_rate < 0.01) else 1


if __name__ == "__main__":
    sys.exit(main())
