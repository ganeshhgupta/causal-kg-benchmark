#!/usr/bin/env python3
"""Score the K-IR reasoner against gold retraction-propagation labels.

Reports per-class precision/recall plus two hard safety gates that matter more
than average accuracy:

  * false_collapse_rate   -- claims reported as losing support that actually
                             survive. This is the dangerous direction: it would
                             have us tell a clinician a supported finding is
                             void.
  * missed_collapse_rate  -- claims that really lost support but were reported
                             as fine. Dangerous the other way.

Also checks the UNRESOLVED-is-not-REFUTED invariant explicitly, since collapsing
those two would look fine on aggregate accuracy while being the single most
misleading error the system could make.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "reasoner"))
from epistemic_query import Graph  # noqa: E402

ROOT = Path(__file__).parent.parent
GOLD = ROOT / "scientific-dependency" / "gold_queries.json"

COLLAPSE_CLASSES = {"LOST_SUPPORT", "CHANGED"}


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def evidence_in_group(graph: Graph, group: str) -> set[str]:
    return {e["id"] for e in graph.evidence.values()
            if e.get("independence_group") == group}


def score_query(q, verbose=True):
    graph_path = ROOT / "scientific-dependency" / q["graph"]
    graph = Graph(load_json(graph_path))

    if "retract_independence_group" in q:
        targets = evidence_in_group(graph, q["retract_independence_group"])
        if not targets:
            raise SystemExit(f"{q['id']}: no evidence in group "
                             f"{q['retract_independence_group']}")
    else:
        targets = set(q["retract_evidence"])

    predicted = graph.retract(targets)
    expected = q["expected"]

    unknown = set(expected) - set(predicted)
    if unknown:
        raise SystemExit(f"{q['id']}: gold names unknown propositions {sorted(unknown)}")

    rows, exact = [], 0
    for pid, gold in expected.items():
        pred = predicted[pid]
        class_ok = pred["class"] == gold["class"]
        after_ok = pred["after"] == gold["after"]
        if class_ok and after_ok:
            exact += 1
        rows.append((pid, gold["class"], pred["class"], gold["after"], pred["after"],
                     class_ok, after_ok))

    if verbose:
        print(f"=== {q['id']} ===")
        print(f"retracted {len(targets)} evidence object(s) "
              f"(group {q.get('retract_independence_group', 'explicit')})\n")
        hdr = f"{'claim':26} {'gold class':22} {'pred class':22} {'gold':11} {'pred':11}"
        print(hdr)
        print("-" * len(hdr))
        for pid, gc, pc, ga, pa, cok, aok in rows:
            flag = "" if (cok and aok) else "   <-- MISMATCH"
            print(f"{pid:26} {gc:22} {pc:22} {ga:11} {pa:11}{flag}")
        print()

    # --- per-class precision / recall -------------------------------------
    classes = sorted({r[1] for r in rows} | {r[2] for r in rows})
    per_class = {}
    for cls in classes:
        tp = sum(1 for r in rows if r[1] == cls and r[2] == cls)
        fp = sum(1 for r in rows if r[1] != cls and r[2] == cls)
        fn = sum(1 for r in rows if r[1] == cls and r[2] != cls)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        per_class[cls] = {"support": tp + fn, "precision": prec, "recall": rec}

    # --- safety gates ------------------------------------------------------
    # Defined on the ANSWER (after-status), not the transition class. A
    # class-based rule scored "gold REFUTED, reported SUPPORTED" as safe, which
    # is the single most misleading error the system can make. Found by
    # eval/robustness_eval.py mutation wrong_stance_on_null.
    false_collapse = {r[0] for r in rows if r[3] == "SUPPORTED" and r[4] != "SUPPORTED"}
    missed_collapse = {r[0] for r in rows if r[3] != "SUPPORTED" and r[4] == "SUPPORTED"}

    # UNRESOLVED must never be reported as REFUTED, or vice versa
    conflations = [r[0] for r in rows
                   if {r[3], r[4]} == {"UNRESOLVED", "REFUTED"}]

    return {
        "query": q["id"],
        "n": len(rows),
        "exact_match": exact / len(rows) if rows else None,
        "per_class": per_class,
        "false_collapse_rate": len(false_collapse) / len(rows) if rows else None,
        "missed_collapse_rate": len(missed_collapse) / len(rows) if rows else None,
        "false_collapse": sorted(false_collapse),
        "missed_collapse": sorted(missed_collapse),
        "unresolved_refuted_conflations": conflations,
    }


def main():
    gold = load_json(GOLD)
    results = [score_query(q) for q in gold["queries"]]

    print("=" * 72)
    for r in results:
        print(f"{r['query']}  n={r['n']}  exact_match={r['exact_match']:.3f}")
        for cls, m in sorted(r["per_class"].items()):
            p = "n/a" if m["precision"] is None else f"{m['precision']:.3f}"
            rc = "n/a" if m["recall"] is None else f"{m['recall']:.3f}"
            print(f"   {cls:24} support={m['support']}  precision={p}  recall={rc}")
        print(f"   {'false_collapse_rate':24} {r['false_collapse_rate']:.3f}  {r['false_collapse']}")
        print(f"   {'missed_collapse_rate':24} {r['missed_collapse_rate']:.3f}  {r['missed_collapse']}")
        print(f"   {'UNRESOLVED/REFUTED mixups':24} {r['unresolved_refuted_conflations']}")
        print()

    pending = gold.get("pending", [])
    if pending:
        print(f"{len(pending)} query/queries pending label verification:")
        for p in pending:
            print(f"   {p['id']}: {p['status']}")
        print()

    failed = [r for r in results
              if r["exact_match"] < 1.0 or r["unresolved_refuted_conflations"]]
    if failed:
        print(f"FAIL: {len(failed)} query/queries did not match gold exactly")
        return 1
    print("PASS: all gold labels reproduced, no UNRESOLVED/REFUTED conflation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
