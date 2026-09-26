#!/usr/bin/env python3
"""Score a BLIND LLM-extracted K-IR graph against gold.

The reasoner scorers (retraction_eval.py) assume the graph already uses gold
proposition ids. A blindly extracted graph does not: the compiler invents its
own ids, its own predicates, and its own claim boundaries. Aligning those to
gold IS the canonicalization problem, so it is measured here rather than
assumed away.

Two stages:

  1. ALIGNMENT. Each gold claim is matched to at most one extracted
     proposition by content-word overlap between surface forms. Reported
     explicitly so a human can see and override it via an alignment JSON
     ({"gold_id": "extracted_id" | null}). Overrides change only WHICH
     extracted claim answers a gold claim, never the gold LABEL.

  2. ANSWER SCORING. The reasoner runs on the extracted graph, retracting the
     extracted graph's own Fujii-group evidence, and the resulting statuses are
     compared to gold.

Metrics:
  claim_recall      fraction of gold claims the compiler represented at all
  claim_precision   fraction of extracted claims that correspond to a gold claim
                    (the rest are spurious or over-split)
  answer_accuracy   of the aligned claims, fraction with the right after-status
  false_survival    gold says not SUPPORTED, system says SUPPORTED  (dangerous)
  false_collapse    gold says SUPPORTED, system says otherwise
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph, author_groups  # noqa: E402

STOP = set("""a an the of for in on with and or to is are was were be been being
that this these those it its as at by from not no than then so such can could
which who whom whose if while during after before more most less least very
there here when where how why all any both each few other some own same s t
prevention postoperative patients studies trials study trial authors et al
evidence effect effects results result use used using compared comparison
""".split())


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9-]+", text.lower())
            if w not in STOP and len(w) > 2}


def prop_text(p: dict) -> str:
    parts = list(p.get("surface_forms") or [])
    parts.append(p.get("predicate", ""))
    for a in p.get("arguments", []):
        t = a.get("term", {})
        parts.append(str(t.get("symbol_ref") or t.get("value") or t.get("name") or ""))
    return " ".join(parts)


def symbol_expand(p: dict, symbols: dict) -> str:
    """Include symbol LABELS, not just ids, so matching is not id-format bound."""
    extra = []
    for a in p.get("arguments", []):
        ref = a.get("term", {}).get("symbol_ref")
        if ref and ref in symbols:
            extra.append(symbols[ref].get("label", ""))
    pred = p.get("predicate")
    if pred in symbols:
        extra.append(symbols[pred].get("label", ""))
    return prop_text(p) + " " + " ".join(extra)


def align(gold_props: dict, ex_graph: Graph, threshold: float = 0.22):
    ex_symbols = {s["id"]: s for s in ex_graph.data.get("symbols", [])}
    scores = []
    for gid, gp in gold_props.items():
        gw = words(symbol_expand(gp, {}))
        for eid, ep in ex_graph.propositions.items():
            ew = words(symbol_expand(ep, ex_symbols))
            if not gw or not ew:
                continue
            jac = len(gw & ew) / len(gw | ew)
            cov = len(gw & ew) / len(gw)
            scores.append((max(jac, cov * 0.75), gid, eid))
    scores.sort(reverse=True)

    mapping, used_g, used_e = {}, set(), set()
    for sc, gid, eid in scores:
        if sc < threshold or gid in used_g or eid in used_e:
            continue
        mapping[gid] = eid
        used_g.add(gid)
        used_e.add(eid)
    for gid in gold_props:
        mapping.setdefault(gid, None)
    return mapping, scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extracted", default="scientific-dependency/extracted/fujii-ponv-extracted.json")
    ap.add_argument("--query", default="Q-FUJII-PONV")
    ap.add_argument("--alignment", default=None, help="JSON overriding the auto alignment")
    args = ap.parse_args()

    gold_all = json.load(open(ROOT / "scientific-dependency" / "gold_queries.json"))
    q = next(x for x in gold_all["queries"] if x["id"] == args.query)
    ref = Graph(json.load(open(ROOT / "scientific-dependency" / q["graph"])))
    gold_props = {pid: ref.propositions[pid] for pid in q["expected"]}
    expected = {pid: g["after"] for pid, g in q["expected"].items()}

    ex = Graph(json.load(open(ROOT / args.extracted)))

    mapping, _ = align(gold_props, ex)
    if args.alignment:
        mapping.update(json.load(open(ROOT / args.alignment)))

    # Retract the extracted graph's OWN Fujii group. If the compiler grouped
    # nothing, fall back to source-substring, and record that it did so.
    groups = {e.get("independence_group") for e in ex.evidence.values()} - {None}
    fujii_groups = sorted(author_groups(groups, "fujii"))
    how = None
    if fujii_groups:
        targets = {e["id"] for e in ex.evidence.values()
                   if e.get("independence_group") in fujii_groups}
        how = f"independence_group in {fujii_groups}"
    else:
        targets = {e["id"] for e in ex.evidence.values()
                   if "fujii" in e.get("source", "").lower()}
        how = "SOURCE SUBSTRING FALLBACK (compiler emitted no usable group)"

    statuses, _ = ex.status_map(retracted=targets)

    print(f"extracted graph: {args.extracted}")
    print(f"  propositions={len(ex.propositions)} evidence={len(ex.evidence)} "
          f"derivations={len(ex.derivations)}")
    print(f"  retraction selector: {how}  -> {len(targets)} evidence\n")

    print("alignment (gold claim -> extracted claim):")
    for gid, eid in mapping.items():
        if eid:
            sf = (ex.propositions[eid].get("surface_forms") or [""])[0][:58]
            print(f"  {gid:26} -> {eid:28} {sf!r}")
        else:
            print(f"  {gid:26} -> NONE  (compiler did not represent this claim)")
    matched_e = {e for e in mapping.values() if e}
    spurious = [e for e in ex.propositions if e not in matched_e]
    if spurious:
        print("\nextracted claims with no gold counterpart:")
        for eid in spurious:
            sf = (ex.propositions[eid].get("surface_forms") or [""])[0][:64]
            print(f"  {eid:28} {sf!r}")

    print("\nanswers:")
    hdr = f"{'gold claim':26} {'gold':11} {'predicted':11}"
    print(hdr); print("-" * len(hdr))
    correct = fs = fc = 0
    for gid, want in expected.items():
        eid = mapping.get(gid)
        got = statuses.get(eid) if eid else "MISSING"
        ok = got == want
        correct += ok
        if got == "SUPPORTED" and want != "SUPPORTED":
            fs += 1
        if want == "SUPPORTED" and got != "SUPPORTED":
            fc += 1
        print(f"{gid:26} {want:11} {str(got):11} {'' if ok else '  <-- MISMATCH'}")

    n = len(expected)
    found = sum(1 for v in mapping.values() if v)
    print()
    print(f"claim_recall      {found}/{n} = {found/n:.3f}")
    print(f"claim_precision   {found}/{len(ex.propositions)} = "
          f"{found/len(ex.propositions):.3f}" if ex.propositions else "n/a")
    print(f"answer_accuracy   {correct}/{n} = {correct/n:.3f}")
    print(f"false_survival    {fs}   (DANGEROUS: reported standing when it does not)")
    print(f"false_collapse    {fc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
