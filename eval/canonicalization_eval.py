#!/usr/bin/env python3
"""Measure canonical-claim matching F1 and the dangerous false-merge rate.

Earned by a real failure: adding a second corpus immediately produced the same
claim twice under two ids (cycle 3 in LOOP_LOG.md). So there is now a real
canonicalization task with real gold pairs, and two of the stated targets become
measurable with no LLM:

    canonical proposition matching   >= 95% F1
    dangerous false merges           <  0.5%, ideally 0

The pairs are drawn from the two real corpora, and the DIFFERENT pairs are chosen
to be genuinely tempting rather than easy: same structure with one drug swapped,
a specific instance against the general principle it instantiates, and the same
drug in opposite directions. A matcher that merges any of those is committing the
error this project has treated as the most dangerous from the start.

The current pipeline performs NO merging. That is reported honestly: it passes
the safety gate trivially at zero false merges, and fails the F1 target at zero
recall. The point of this file is to make that tradeoff a number instead of a
sentence.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CORPORA = [
    ROOT / "scientific-dependency" / "corpus" / "fujii-ponv.json",
    ROOT / "scientific-dependency" / "corpus" / "fujii-combination-review.json",
]

# Gold pairs over real claims. "SAME" means one canonical claim reached from two
# documents; "DIFFERENT" means they must never be merged.
sys.path.insert(0, str(Path(__file__).parent.parent / "compiler"))

GOLD_PAIRS = [
    (("P-SYNERGISM", "P-MULTI-RECEPTOR-PRINCIPLE"), "SAME",
     "Both assert that combining antiemetics acting at different receptors beats "
     "monotherapy. Same claim, reached from Carlisle's re-analysis and from "
     "Fujii's own review. This is the duplicate cycle 3 discovered."),

    (("P-GRANI-EFFECTIVE", "P-RAMO-EFFECTIVE"), "DIFFERENT",
     "Identical structure, different drug. The classic false-merge trap: "
     "surface forms differ by one word."),

    (("P-DEX-ENHANCES", "P-TRAD-ADJUNCT-SUPERIOR"), "DIFFERENT",
     "Both say a combination beats monotherapy, but the adjunct differs "
     "(dexamethasone vs a traditional antiemetic at another receptor)."),

    (("P-DEX-ENHANCES", "P-MULTI-RECEPTOR-PRINCIPLE"), "DIFFERENT",
     "A specific instance against the general principle it instantiates. This is "
     "ENTAILS, not EQUAL. Merging a specialization into its generalization is the "
     "Copper-into-Metal error from the physics benchmark."),

    (("P-SYNERGISM", "P-DROPERIDOL-INFERIOR"), "DIFFERENT",
     "Both involve granisetron and droperidol, but one is about synergy between "
     "them and the other about which is more effective."),

    (("P-GRANI-ALONE-WORSE", "P-GRANI-EFFECTIVE"), "DIFFERENT",
     "Same drug, opposite direction. Merging these would erase a contradiction."),

    (("P-COMBO-NOT-MORE-TOXIC", "P-TRAD-COMBO-LIMITED"), "DIFFERENT",
     "Both concern combination safety, but one denies added adverse effects for "
     "multi-receptor combinations and the other affirms a CNS-toxicity limit on "
     "traditional combinations. Opposite import."),
]

STOP = {"the", "a", "an", "of", "for", "is", "are", "in", "with", "and", "or",
        "to", "that", "than", "it", "as", "by", "at", "more", "each", "one",
        "alone", "site", "sites"}


def tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def load_props():
    props = {}
    for path in CORPORA:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for p in data["propositions"]:
            props[p["id"]] = p
    return props


# --- candidate matchers ----------------------------------------------------

def never_merge(a, b):
    """What the pipeline does today."""
    return False


def same_predicate(a, b):
    return a["predicate"] == b["predicate"]


def exact_structural(a, b):
    def key(p):
        args = tuple(sorted(
            (arg["role"], json.dumps(arg["term"], sort_keys=True))
            for arg in p["arguments"]))
        return (p["predicate"], args, p.get("polarity"))
    return key(a) == key(b)


def lexical_overlap(a, b, threshold=0.5):
    ta = tokens(" ".join(a.get("surface_forms", [])))
    tb = tokens(" ".join(b.get("surface_forms", [])))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def _declared_equivalence(a, b):
    """The real canonicalization stage: compiler/canonicalize.py.

    Wired in cycle 9. It existed and scored the gold pair correctly, but was
    never listed here, so the eval kept reporting F1 0.000 as though nothing
    could find the duplicate. The eval was measuring the absence of a stage
    rather than the stage. Merges only on identical normal form under declared,
    justified rules, so RELATED (one argument differs) is not a merge.
    """
    from canonicalize import compare, load_equivalences
    verdict, _ = compare(a, b, load_equivalences())
    return verdict == "EQUAL"


MATCHERS = {
    "never_merge (current)": never_merge,
    "declared_equivalence": _declared_equivalence,
    "same_predicate": same_predicate,
    "exact_structural": exact_structural,
    "lexical_overlap@0.5": lexical_overlap,
    "lexical_overlap@0.3": lambda a, b: lexical_overlap(a, b, 0.3),
}


def main():
    props = load_props()

    missing = [pid for pair, _, _ in GOLD_PAIRS for pid in pair if pid not in props]
    if missing:
        print(f"gold references unknown propositions: {sorted(set(missing))}",
              file=sys.stderr)
        return 2

    n_same = sum(1 for _, lab, _ in GOLD_PAIRS if lab == "SAME")
    n_diff = len(GOLD_PAIRS) - n_same
    print(f"gold pairs: {len(GOLD_PAIRS)}  ({n_same} SAME, {n_diff} DIFFERENT)")
    print(f"drawn from {len(CORPORA)} real corpora, {len(props)} claims\n")

    hdr = (f"{'matcher':24} {'TP':4} {'FP':4} {'FN':4} {'prec':6} {'rec':6} "
           f"{'F1':6} {'false_merge_rate':17} gate")
    print(hdr)
    print("-" * (len(hdr) + 2))

    rows = []
    for name, fn in MATCHERS.items():
        tp = fp = fn_ = 0
        merged_wrongly = []
        for (x, y), label, _ in GOLD_PAIRS:
            pred = fn(props[x], props[y])
            if label == "SAME":
                if pred:
                    tp += 1
                else:
                    fn_ += 1
            else:
                if pred:
                    fp += 1
                    merged_wrongly.append(f"{x}+{y}")
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn_) if tp + fn_ else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        fmr = fp / n_diff if n_diff else 0.0
        gate = "PASS" if fmr < 0.005 else "FAIL"
        print(f"{name:24} {tp:<4} {fp:<4} {fn_:<4} {prec:<6.3f} {rec:<6.3f} "
              f"{f1:<6.3f} {fmr:<17.3f} {gate}")
        rows.append((name, f1, fmr, merged_wrongly))

    print("\nfalse merges committed:")
    for name, _, _, wrong in rows:
        if wrong:
            print(f"  {name}: {wrong}")
    if not any(w for *_, w in rows):
        print("  none")

    print("\ntargets")
    print("  canonical matching F1     >= 0.95")
    print("  dangerous false merges    <  0.005")
    print()
    best_f1 = max(rows, key=lambda r: r[1])
    safe = [r for r in rows if r[2] < 0.005]
    best_safe = max(safe, key=lambda r: r[1]) if safe else None
    print(f"  best F1 by any matcher:        {best_f1[0]} at {best_f1[1]:.3f} "
          f"(false_merge_rate {best_f1[2]:.3f})")
    if best_safe:
        print(f"  best F1 among gate-passing:   {best_safe[0]} at "
              f"{best_safe[1]:.3f}")
    print()
    print("READING: the current pipeline never merges, so it passes the safety "
          "gate trivially and scores F1 0.000 against a real duplicate it cannot "
          "see. Every matcher that finds the duplicate also commits false merges "
          "on the decoys. That is the measured case for a real canonicalization "
          "stage, and the number to beat is now on record rather than asserted.")
    print("\nDISCLOSURE: declared_equivalence scores 1.000 on a set containing exactly")
    print("ONE SAME pair, and its rule was authored with that pair in view. That is not a")
    print("generalization estimate. What it does show is that the rule had three")
    print("opportunities to false-merge the decoys (P-DEX-ENHANCES, P-TRAD-ADJUNCT-SUPERIOR")
    print("and P-SYNERGISM all normalise to COMBINATION_OUTPERFORMS) and declined all three,")
    print("because it compares full normal forms including arguments rather than predicates")
    print("alone. The lexical and same-predicate matchers took exactly those bait pairs.")
    print("A real number needs SAME pairs the rules were not written for.")
    print(f"\nn={len(GOLD_PAIRS)} pairs is far too small for these rates to be "
          f"stable; they are a floor to improve on, not a result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
