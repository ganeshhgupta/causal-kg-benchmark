#!/usr/bin/env python3
"""Score the LLM baseline against gold, and report the margin over it.

This closes the row the scorecard has carried as BLOCKED: "must outperform
LLM-only and LLM+RAG baselines materially, e.g. >= 10 percentage points".

SCOPE, stated precisely because the distinction is easy to overclaim:

  The baseline agent is given the full source abstract in context and asked the
  retraction question directly. With a single-document corpus, retrieval is
  trivially perfect, so this is the RAG-equivalent UPPER BOUND, not a weak
  LLM-only strawman. A real LLM+RAG system over a large corpus would have to
  retrieve the right paper first and could only do worse. Beating this number
  is therefore a stronger result than beating a retrieval-limited baseline;
  losing to it would be decisive.

  Both systems are scored on the SAME gold after-statuses, so the comparison is
  like-for-like on the answer, not on internal representation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph, author_groups  # noqa: E402

import argparse

GOLD = ROOT / "scientific-dependency" / "gold_queries.json"
_AP = argparse.ArgumentParser()
_AP.add_argument("--answers", default="eval/baselines/llm/baseline_answers.json")
_AP.add_argument("--queries", nargs="*", default=["Q-FUJII-PONV"])
_ARGS = _AP.parse_args()
ANSWERS = ROOT / _ARGS.answers
QUERY = _ARGS.queries[0]


def metrics(name, pred: dict, expected: dict):
    correct = sum(1 for k, v in expected.items() if pred.get(k) == v)
    fs = [k for k, v in expected.items()
          if v != "SUPPORTED" and pred.get(k) == "SUPPORTED"]
    fc = [k for k, v in expected.items()
          if v == "SUPPORTED" and pred.get(k) not in (None, "SUPPORTED")]
    missing = [k for k in expected if k not in pred]
    # UNRESOLVED reported as REFUTED, or the reverse: the specific confusion
    # this project treats as most misleading, tracked separately from accuracy.
    conflate = [k for k, v in expected.items()
                if pred.get(k) and {v, pred[k]} == {"UNRESOLVED", "REFUTED"}]
    return {"name": name, "n": len(expected), "correct": correct,
            "accuracy": correct / len(expected), "false_survival": fs,
            "false_collapse": fc, "missing": missing, "conflate": conflate}


def main():
    gold = json.load(open(GOLD))
    q = next(x for x in gold["queries"] if x["id"] == QUERY)
    expected = {pid: g["after"] for pid, g in q["expected"].items()}

    if not ANSWERS.exists():
        print(f"no baseline answers at {ANSWERS}", file=sys.stderr)
        return 2
    raw = json.load(open(ANSWERS))
    llm = {a["claim_id"]: a["status"] for a in raw["answers"]}

    graph = Graph(json.load(open(ROOT / "scientific-dependency" / q["graph"])))
    groups = {e.get("independence_group") for e in graph.evidence.values()} - {None}
    targets = {e["id"] for e in graph.evidence.values()
               if e.get("independence_group") in author_groups(groups, "fujii")}
    kir_status, _ = graph.status_map(retracted=targets)
    kir = {pid: kir_status[pid] for pid in expected}

    rows = [metrics("llm_with_source_in_context", llm, expected),
            metrics("kir_reasoner", kir, expected)]

    w = max(len(p) for p in expected) + 2
    print(f"{'claim':{w}} {'GOLD':11} {'LLM':11} {'K-IR':11}")
    print("-" * (w + 36))
    for pid, want in expected.items():
        l, k = llm.get(pid, "MISSING"), kir[pid]
        mark = "" if l == want else "  <-- LLM wrong"
        print(f"{pid:{w}} {want:11} {l:11} {k:11}{mark}")

    print()
    for r in rows:
        print(f"{r['name']:28} accuracy={r['accuracy']:.3f} "
              f"({r['correct']}/{r['n']})  false_survival={len(r['false_survival'])} "
              f" false_collapse={len(r['false_collapse'])} "
              f" UNRESOLVED/REFUTED mixups={len(r['conflate'])}")
        for k in ("false_survival", "conflate", "missing"):
            if r[k]:
                print(f"     {k}: {r[k]}")

    # --- sensitivity to disputed labels ------------------------------------
    # The headline margin must not rest on a label this project itself flags as
    # contested. P-GRANI-ALONE-WORSE is annotated "disputed" in gold: both the
    # blind extractor and this baseline independently answered REFUTED where
    # gold says UNRESOLVED. If they are right, K-IR is wrong on that claim and
    # the LLM is right, which moves the margin by two claims at once.
    disputed = [pid for pid, g in q["expected"].items() if "disputed" in g]
    if disputed:
        print("\nSENSITIVITY (disputed gold labels flipped to the alternative reading):")
        for pid in disputed:
            alt = dict(expected)
            alt[pid] = llm.get(pid)  # the reading both agents independently gave
            a_llm = metrics("llm", llm, alt)["accuracy"]
            a_kir = metrics("kir", kir, alt)["accuracy"]
            print(f"  if {pid} is really {alt[pid]} (not {expected[pid]}):")
            print(f"     llm={a_llm:.3f}  kir={a_kir:.3f}  "
                  f"margin={(a_kir - a_llm) * 100:+.1f} pts")

    margin = (rows[1]["accuracy"] - rows[0]["accuracy"]) * 100
    print(f"\nmargin over LLM baseline: {margin:+.1f} percentage points "
          f"(target >= +10)")
    # A target met only under one reading of a label this project flags as
    # contested is not met. Report NOT ROBUST rather than banking the PASS.
    worst = margin
    for pid in disputed:
        alt = dict(expected); alt[pid] = llm.get(pid)
        worst = min(worst, (metrics("k", kir, alt)["accuracy"]
                            - metrics("l", llm, alt)["accuracy"]) * 100)
    # Contamination check. If the reference graph carries a fix that was
    # prompted by the baseline's own answers, then a margin measured on those
    # same claims is not an independent comparison and must not read as a clean
    # PASS. The marker is written into the corpus at the point of the fix.
    contaminated = [e["id"] for e in graph.evidence.values()
                    if "CONTAMINATION-MARKER" in (e.get("notes") or "")]
    if contaminated:
        print(f"\nCONTAMINATION: the reference graph contains {len(contaminated)} "
              f"fix(es) prompted by this baseline's answers: {contaminated}")
        print("  The margin below is measured on the same six claims that revealed "
              "the bug, so it is NOT an independent comparison. An honest margin "
              "needs unseen claims.")

    if contaminated:
        verdict = (f"CONTAMINATED -- {margin:+.1f} pts, but measured after a "
                   f"baseline-prompted fix to the reference graph. Not independent.")
    elif margin >= 10 and worst < 10:
        verdict = (f"NOT ROBUST -- {margin:+.1f} pts as labelled, but {worst:+.1f} pts "
                   f"if the disputed label goes the other way. Target NOT established.")
    elif margin >= 10:
        verdict = "PASS"
    elif margin <= 0:
        verdict = "TIE/LOSS"
    else:
        verdict = "BELOW TARGET"
    print(f"verdict: {verdict}")
    print(f"\nn={len(expected)} claims on one paper. A margin measured on six "
          f"claims is directional, not a result; each claim is worth 16.7 points.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
