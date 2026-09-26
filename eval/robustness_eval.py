#!/usr/bin/env python3
"""Compiler-error sensitivity: which extraction mistakes corrupt the answer?

Cycle 1 of the loop could not use a blind LLM extractor (subagent spawning needs
tmux/WSL here, and a context-inheriting fork would have already seen the gold
labels, making a "blind" result worthless). So instead of faking a blind run,
this measures the thing that would actually make a blind run fail: it applies
each mistake a real compiler plausibly makes to the reference graph and scores
the consequence against gold.

That yields the signal the loop needs -- which failures are dangerous and
therefore worth fixing -- without pretending to a result we did not get.

Each mutation is named for the real extraction error it simulates.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "reasoner"))
from epistemic_query import Graph  # noqa: E402

ROOT = Path(__file__).parent.parent
CORPUS = ROOT / "scientific-dependency" / "corpus" / "fujii-ponv.json"
GOLD = ROOT / "scientific-dependency" / "gold_queries.json"
GROUP = "FUJII-SERIES"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --- mutations -------------------------------------------------------------

def mut_baseline(d):
    return d


def mut_false_merge(d):
    """Compiler decides synergism and droperidol-inferiority are 'one claim
    about antiemetic combinations'. The canonical dangerous false merge."""
    d["propositions"] = [p for p in d["propositions"] if p["id"] != "P-DROPERIDOL-INFERIOR"]
    for e in d["evidence"]:
        if e["proposition_id"] == "P-DROPERIDOL-INFERIOR":
            e["proposition_id"] = "P-SYNERGISM"
    return d


def mut_split_same_claim(d):
    """Compiler treats 'granisetron works (per Fujii)' and 'granisetron works
    (per others)' as two different claims instead of one claim with two
    evidence sources. Rule 3 of the extraction spec exists for this."""
    twin = copy.deepcopy(next(p for p in d["propositions"] if p["id"] == "P-GRANI-EFFECTIVE"))
    twin["id"] = "P-GRANI-EFFECTIVE-FUJII"
    d["propositions"].append(twin)
    for e in d["evidence"]:
        if e["id"] == "EV-FUJII-GRANI":
            e["proposition_id"] = "P-GRANI-EFFECTIVE-FUJII"
    return d


def mut_drop_refuting(d):
    """Compiler reads only the positive findings and omits 'no synergism in
    trials by other authors' / 'some evidence of antagonism'."""
    drop = {"EV-OTHER-ANTAGONISM", "EV-OTHER-NODIFF"}
    d["evidence"] = [e for e in d["evidence"] if e["id"] not in drop]
    return d


def mut_wrong_stance(d):
    """Compiler encodes a null result as weak support instead of refutation."""
    for e in d["evidence"]:
        if e["id"] in {"EV-OTHER-NODIFF", "EV-OTHER-ANTAGONISM"}:
            e["stance"] = "supports"
    return d


def mut_no_independence_group(d):
    """Compiler omits independence_group, so 'retract everything from this
    author' is not expressible as a query at all."""
    for e in d["evidence"]:
        e["independence_group"] = None
    return d


def mut_prebake_retraction(d):
    """Compiler bakes the retraction into the graph instead of leaving it to the
    query, so nothing can be asked about what changed."""
    for e in d["evidence"]:
        if e.get("independence_group") == GROUP:
            e["status"] = "retracted"
    return d


MUTATIONS = {
    "baseline": mut_baseline,
    "false_merge": mut_false_merge,
    "split_same_claim": mut_split_same_claim,
    "drop_refuting_evidence": mut_drop_refuting,
    "wrong_stance_on_null": mut_wrong_stance,
    "no_independence_group": mut_no_independence_group,
    "prebake_retraction": mut_prebake_retraction,
}

# Which mutations SHOULD be survivable (the answer is still right) versus
# which are expected to corrupt it. Stated up front so this is a prediction
# being tested, not a description written after seeing output.
EXPECTED_SURVIVABLE = {"baseline"}


def score(data, expected):
    graph = Graph(data)
    targets = {e["id"] for e in graph.evidence.values()
               if e.get("independence_group") == GROUP}
    if not targets:
        return {"queryable": False, "exact": 0.0, "precision": 0.0,
                "spurious": [], "n_matched": 0,
                "mismatches": ["QUERY IMPOSSIBLE: no evidence carries the "
                               "independence group, so the retraction cannot "
                               "be expressed"],
                "false_survival": [], "false_collapse": []}

    report = graph.retract(targets)
    matched, mismatches, false_survival, false_collapse = 0, [], [], []
    for pid, gold in expected.items():
        if pid not in report:
            mismatches.append(f"{pid}: MISSING from graph (claim lost or merged away)")
            # A claim the graph cannot even represent is not "surviving"; it is
            # unanswerable. Counted as neither danger class, only as a miss.
            continue
        pred = report[pid]
        if pred["class"] == gold["class"] and pred["after"] == gold["after"]:
            matched += 1
        else:
            mismatches.append(
                f"{pid}: gold {gold['class']}/{gold['after']} "
                f"got {pred['class']}/{pred['after']}")

        # Danger is defined on the ANSWER (the after-status), not on the
        # transition class. Found by this harness: mutation wrong_stance_on_null
        # reports SUPPORTED for a claim gold says is REFUTED, which is the most
        # misleading error possible, and a class-based rule scored it as safe
        # because neither class was in a hardcoded "collapse" set.
        gold_stands = gold["after"] == "SUPPORTED"
        pred_stands = pred["after"] == "SUPPORTED"
        if pred_stands and not gold_stands:
            false_survival.append(pid)
        if gold_stands and not pred_stands:
            false_collapse.append(pid)

    # Spurious propositions are a canonicalization PRECISION failure and must
    # cost something. Found by this harness: split_same_claim scored a perfect
    # 1.00 because the metric only counted gold claims matched, so inventing a
    # phantom twin claim that absorbs half the real evidence was free.
    extra = [p["id"] for p in data["propositions"] if p["id"] not in expected]
    if extra:
        mismatches.append(f"spurious propositions not in gold: {extra}")

    n = len(expected)
    return {"queryable": True,
            "exact": matched / n,
            "precision": matched / (matched + len(extra)) if matched + len(extra) else 0.0,
            "spurious": extra,
            "n_matched": matched, "mismatches": mismatches,
            "false_survival": false_survival, "false_collapse": false_collapse}


def main():
    gold_q = next(q for q in load(GOLD)["queries"] if q["id"] == "Q-FUJII-PONV")
    expected = gold_q["expected"]
    base = load(CORPUS)

    results = {}
    for name, fn in MUTATIONS.items():
        results[name] = score(fn(copy.deepcopy(base)), expected)

    print(f"Gold claims: {len(expected)}   corpus: {CORPUS.name}\n")
    hdr = (f"{'simulated compiler error':24} {'queryable':10} {'recall':7} "
           f"{'prec':6} {'spurious':9} {'false_surv':11} {'false_coll'}")
    print(hdr)
    print("-" * (len(hdr) + 4))
    for name, r in results.items():
        print(f"{name:24} {str(r['queryable']):10} "
              f"{r['exact']:.2f}    {r['precision']:.2f}   "
              f"{len(r['spurious']):<9} {len(r['false_survival']):<11} "
              f"{len(r['false_collapse'])}")

    print("\ndetail:")
    for name, r in results.items():
        if name == "baseline" and not r["mismatches"]:
            continue
        if not r["mismatches"]:
            continue
        print(f"\n  {name}:")
        for m in r["mismatches"]:
            print(f"    - {m}")

    print()
    survived = {n for n, r in results.items()
                if r["queryable"] and r["exact"] == 1.0 and not r["spurious"]}
    print(f"survived intact: {sorted(survived)}")
    print(f"predicted survivable: {sorted(EXPECTED_SURVIVABLE)}")
    if survived != EXPECTED_SURVIVABLE:
        unexpected_ok = survived - EXPECTED_SURVIVABLE
        unexpected_bad = EXPECTED_SURVIVABLE - survived
        if unexpected_ok:
            print(f"  SURPRISE, tolerated after all: {sorted(unexpected_ok)}")
        if unexpected_bad:
            print(f"  SURPRISE, broke when predicted safe: {sorted(unexpected_bad)}")

    dangerous = {n: r for n, r in results.items() if r["false_survival"]}
    print()
    if dangerous:
        print("DANGEROUS (a real finding reported as surviving when it does not):")
        for n, r in dangerous.items():
            print(f"  {n}: {r['false_survival']}")
    else:
        print("no mutation produced a false survival")
    return 0


if __name__ == "__main__":
    sys.exit(main())
