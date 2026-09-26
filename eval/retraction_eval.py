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

    # --- epistemic classification macro-F1 over the 4-valued status ---------
    # Over gold after-statuses, not transition classes: this is the
    # supported/refuted/unresolved/inconsistent target.
    statuses = sorted({r[3] for r in rows} | {r[4] for r in rows})
    f1s, status_detail = [], {}
    for st in statuses:
        tp_s = sum(1 for r in rows if r[3] == st and r[4] == st)
        fp_s = sum(1 for r in rows if r[3] != st and r[4] == st)
        fn_s = sum(1 for r in rows if r[3] == st and r[4] != st)
        p = tp_s / (tp_s + fp_s) if tp_s + fp_s else None
        rc = tp_s / (tp_s + fn_s) if tp_s + fn_s else None
        if p is not None and rc is not None and p + rc > 0:
            f1 = 2 * p * rc / (p + rc)
        else:
            f1 = 0.0 if (tp_s + fp_s + fn_s) else None
        status_detail[st] = {"support": tp_s + fn_s, "precision": p,
                            "recall": rc, "f1": f1}
        if tp_s + fn_s:  # only classes with gold support count toward the macro
            f1s.append(f1 or 0.0)
    macro_f1 = sum(f1s) / len(f1s) if f1s else None

    # --- propagation precision/recall on "did this claim lose support?" -----
    gold_lost = {r[0] for r in rows if r[3] != "SUPPORTED"}
    pred_lost = {r[0] for r in rows if r[4] != "SUPPORTED"}
    tp_p = len(gold_lost & pred_lost)
    prop_prec = tp_p / len(pred_lost) if pred_lost else None
    prop_rec = tp_p / len(gold_lost) if gold_lost else None

    return {
        "query": q["id"],
        "n": len(rows),
        "exact_match": exact / len(rows) if rows else None,
        "per_class": per_class,
        "status_detail": status_detail,
        "epistemic_macro_f1": macro_f1,
        "propagation_precision": prop_prec,
        "propagation_recall": prop_rec,
        "propagation_support": len(gold_lost),
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
        for st, m in sorted(r["status_detail"].items()):
            if not m["support"]:
                continue
            print(f"   status {st:17} support={m['support']}  f1={m['f1']:.3f}")
        print(f"   {'epistemic macro-F1':24} {r['epistemic_macro_f1']:.4f}")
        print(f"   {'propagation precision':24} {r['propagation_precision']:.4f}"
              if r["propagation_precision"] is not None else
              f"   {'propagation precision':24} n/a")
        print(f"   {'propagation recall':24} {r['propagation_recall']:.4f}"
              f"   (gold lost-support claims: {r['propagation_support']})"
              if r["propagation_recall"] is not None else
              f"   {'propagation recall':24} n/a")
        print()

    # --- pooled across queries, which is the number that matters ------------
    pooled_n = sum(r["n"] for r in results)
    pooled_macro = sum(r["epistemic_macro_f1"] * r["n"] for r in results) / pooled_n
    p_num = sum((r["propagation_precision"] or 0) * r["n"] for r in results)
    r_num = sum((r["propagation_recall"] or 0) * r["n"] for r in results)
    print("=" * 72)
    print(f"POOLED over {len(results)} queries, {pooled_n} gold claims")
    print(f"   epistemic macro-F1      {pooled_macro:.4f}   target >= 0.95  "
          f"{'PASS' if pooled_macro >= 0.95 else 'FAIL'}")
    print(f"   propagation precision   {p_num / pooled_n:.4f}   target >= 0.95  "
          f"{'PASS' if p_num / pooled_n >= 0.95 else 'FAIL'}")
    print(f"   propagation recall      {r_num / pooled_n:.4f}   target >= 0.95  "
          f"{'PASS' if r_num / pooled_n >= 0.95 else 'FAIL'}")
    print(f"   false collapses         {sum(len(r['false_collapse']) for r in results)}")
    print(f"   missed collapses        {sum(len(r['missed_collapse']) for r in results)}")
    print(f"\n   n={pooled_n} on hand-authored graphs. These measure the reasoner. "
          f"The compiler stage is still unmeasured.")
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
