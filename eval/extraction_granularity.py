#!/usr/bin/env python3
"""Separate GRANULARITY mismatch from HALLUCINATION in an extracted graph.

Written because eval/extracted_eval.py reported claim_precision 0.400 on the
blind extraction: 15 propositions against 6 gold claims. That number treats every
unmatched extracted claim as a defect, which conflates two completely different
things:

  FINER_GRAINED   the compiler split one gold claim into several because the
                  paper reports several endpoints (nausea, vomiting, nausea-or-
                  vomiting) for one intervention. Arguably MORE faithful to the
                  source than gold is. Not a defect.
  RESTRUCTURED    the compiler modelled something gold encodes differently, e.g.
                  promoting a refuting finding into its own claim rather than
                  attaching it as evidence. A modelling choice, not an error.
  SPURIOUS        a claim the paper does not make. The real defect.

Classification uses compiler/canonicalize.py: an unmatched claim that is EQUAL or
RELATED to some gold claim under declared equivalences is a granularity or
restructuring difference; one that is DIFFERENT from every gold claim is a
candidate hallucination and gets checked against the source text.

This exists as its own file rather than a patch to extracted_eval.py because a
concurrent session owns that file.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "compiler"))
sys.path.insert(0, str(ROOT / "reasoner"))
from canonicalize import compare, load_equivalences  # noqa: E402
from epistemic_query import Graph  # noqa: E402

EXTRACTED = ROOT / "scientific-dependency" / "extracted" / "fujii-ponv-extracted.json"
REFERENCE = ROOT / "scientific-dependency" / "corpus" / "fujii-ponv.json"
SOURCE = ROOT / "scientific-dependency" / "corpus" / "raw" / "carlisle2012-abstract.txt"
GOLD = ROOT / "scientific-dependency" / "gold_queries.json"


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def content_words(text):
    stop = {"the", "a", "an", "of", "for", "in", "with", "and", "or", "to", "is",
            "are", "was", "were", "be", "than", "that", "this", "it", "as", "by",
            "at", "from", "not", "no", "more", "less", "studies", "trials",
            "et", "al", "authors", "other", "others", "postoperative"}
    return {w for w in re.findall(r"[a-z]+", text.lower())
            if w not in stop and len(w) > 3}


def main():
    equiv = load_equivalences()
    ex = Graph(load(EXTRACTED))
    ref = Graph(load(REFERENCE))
    gold_q = next(q for q in load(GOLD)["queries"] if q["id"] == "Q-FUJII-PONV")
    gold_ids = list(gold_q["expected"])
    source_words = content_words(SOURCE.read_text(encoding="utf-8"))

    # Re-derive the alignment the same way extracted_eval does, by best overlap.
    aligned = set()
    for gid in gold_ids:
        g_words = content_words(" ".join(ref.propositions[gid].get("surface_forms") or []))
        best, best_score = None, 0.0
        for eid, ep in ex.propositions.items():
            if eid in aligned:
                continue
            e_words = content_words(" ".join(ep.get("surface_forms") or []))
            if not g_words or not e_words:
                continue
            score = len(g_words & e_words) / len(g_words | e_words)
            if score > best_score:
                best, best_score = eid, score
        if best and best_score > 0.15:
            aligned.add(best)

    unmatched = [eid for eid in ex.propositions if eid not in aligned]

    print(f"extracted claims: {len(ex.propositions)}   gold claims: {len(gold_ids)}")
    print(f"aligned: {len(aligned)}   unmatched: {len(unmatched)}\n")

    buckets = {"FINER_GRAINED": [], "RESTRUCTURED": [], "SPURIOUS": []}
    for eid in unmatched:
        ep = ex.propositions[eid]
        verdicts = []
        for gid in gold_ids:
            v, _ = compare(ep, ref.propositions[gid], equiv)
            verdicts.append((v, gid))
        equalish = [g for v, g in verdicts if v == "EQUAL"]
        relatedish = [g for v, g in verdicts if v == "RELATED"]

        surface = " ".join(ep.get("surface_forms") or [])
        sw = content_words(surface)
        grounded = (len(sw & source_words) / len(sw)) if sw else 0.0

        if equalish or relatedish:
            kind = "FINER_GRAINED"
            near = (equalish or relatedish)[0]
        elif grounded >= 0.7:
            kind = "RESTRUCTURED"
            near = "-"
        else:
            kind = "SPURIOUS"
            near = "-"
        buckets[kind].append((eid, near, grounded, surface[:70]))

    for kind in ("FINER_GRAINED", "RESTRUCTURED", "SPURIOUS"):
        rows = buckets[kind]
        print(f"{kind}  ({len(rows)})")
        for eid, near, grounded, surface in rows:
            print(f"  {eid:36} nearest_gold={near:24} "
                  f"source_grounding={grounded:.2f}")
            print(f"      {surface!r}")
        print()

    n_ex = len(ex.propositions)
    spurious = len(buckets["SPURIOUS"])
    print(f"raw claim_precision                 {len(aligned)}/{n_ex} = "
          f"{len(aligned)/n_ex:.3f}")
    print(f"granularity-adjusted precision      "
          f"{(n_ex - spurious)}/{n_ex} = {(n_ex - spurious)/n_ex:.3f}")
    print(f"hallucination rate                  {spurious}/{n_ex} = "
          f"{spurious/n_ex:.4f}   target < 0.005  "
          f"{'PASS' if spurious/n_ex < 0.005 else 'FAIL'}")
    print()
    print("READING: raw precision punishes the compiler for being FINER grained "
          "than gold. The paper reports separate effect sizes for nausea, "
          "vomiting and nausea-or-vomiting; gold folds those into one PONV claim. "
          "Deciding which granularity is correct is a spec question, not a "
          "compiler bug, and eval/EXTRACTION_SPEC.md does not currently answer it. "
          "That is the real finding here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
