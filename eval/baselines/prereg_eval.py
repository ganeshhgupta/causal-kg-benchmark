#!/usr/bin/env python3
"""Single-shot, pre-registered margin. Verifies the pre-registration in git.

The cycle 6-8 margins were void because gold was corrected three times after
seeing baseline answers. The defence here is procedural: the gold labels are
committed to git BEFORE the baseline is given the claims, so the ordering is a
matter of record rather than of trust.

This script refuses to report a margin unless it can confirm that ordering, and
refuses any graph carrying a CONTAMINATION-MARKER.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph  # noqa: E402

QUERY = "Q-HONESTY-PLEDGE"
ANSWERS = ROOT / "eval" / "baselines" / "llm" / "honesty_answers.json"
GOLD = ROOT / "scientific-dependency" / "gold_queries.json"


def prereg_ok() -> tuple[bool, str]:
    """Gold must be committed, and the answers file must NOT be in that commit."""
    try:
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%H %ct", "--", "scientific-dependency/gold_queries.json"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        if not commit:
            return False, "gold_queries.json has no commit history"
        sha = commit[0]
        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", sha],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
        rel = "eval/baselines/llm/honesty_answers.json"
        if rel in tracked:
            return False, f"answers file already existed in the gold commit {sha[:8]}"
        return True, (f"gold committed at {sha[:8]}; answers file absent from that tree, "
                      f"so labels predate the measurement")
    except subprocess.CalledProcessError as exc:
        return False, f"git check failed: {exc}"


def main():
    ok, why = prereg_ok()
    print(f"pre-registration check: {'OK' if ok else 'FAILED'}\n  {why}\n")
    if not ok:
        print("REFUSING to report a margin: the pre-registration cannot be verified.")
        return 2

    gold = json.load(open(GOLD))
    q = next(x for x in gold["queries"] if x["id"] == QUERY)
    graph = Graph(json.load(open(ROOT / "scientific-dependency" / q["graph"])))
    marked = [e["id"] for e in graph.evidence.values()
              if "CONTAMINATION-MARKER" in (e.get("notes") or "")]
    if marked:
        print(f"REFUSING: graph carries contamination marker {marked}")
        return 2

    expected = {pid: g["after"] for pid, g in q["expected"].items()}
    llm = {a["claim_id"]: a["status"] for a in json.load(open(ANSWERS))["answers"]}
    targets = {e["id"] for e in graph.evidence.values()
               if e.get("independence_group") == q["retract_independence_group"]}
    kir_all, _ = graph.status_map(retracted=targets)
    kir = {pid: kir_all[pid] for pid in expected}

    w = max(len(p) for p in expected) + 2
    print(f"{'claim':{w}} {'GOLD':11} {'LLM':11} {'K-IR':11}")
    print("-" * (w + 36))
    for pid, want in expected.items():
        l, k = llm.get(pid, "MISSING"), kir[pid]
        tag = ""
        if l != want and k == want:
            tag = "  K-IR only"
        elif l == want and k != want:
            tag = "  LLM only"
        elif l != want:
            tag = "  both wrong"
        print(f"{pid:{w}} {want:11} {l:11} {k:11}{tag}")

    n = len(expected)
    a_l = sum(1 for p, v in expected.items() if llm.get(p) == v) / n
    a_k = sum(1 for p, v in expected.items() if kir[p] == v) / n
    fs_l = [p for p, v in expected.items() if v != "SUPPORTED" and llm.get(p) == "SUPPORTED"]
    fs_k = [p for p, v in expected.items() if v != "SUPPORTED" and kir[p] == "SUPPORTED"]
    print()
    print(f"llm_with_source_in_context   accuracy={a_l:.3f}  false_survival={len(fs_l)}")
    print(f"kir_reasoner                 accuracy={a_k:.3f}  false_survival={len(fs_k)}")
    # --- diagnostic: is any K-IR "win" load-bearing on a known limitation? -----
    # The engine cannot propagate REFUTATION through a derivation (see
    # reasoner/epistemic_query.py line ~30). So for a derived claim with no
    # ground evidence whose premise is REFUTED, K-IR can only ever answer
    # UNRESOLVED. If gold also says UNRESOLVED, K-IR scores a point without
    # having reasoned, and a disagreement there is not evidence it was right.
    suspect = []
    for d in graph.derivations.values():
        c = d["conclusion"]
        if c not in expected:
            continue
        own = [e for e in graph.evidence.values() if e["proposition_id"] == c]
        prem_refuted = any(kir_all.get(pr) == "REFUTED" for pr in d["premises"])
        if not own and prem_refuted and kir[c] == "UNRESOLVED":
            suspect.append((c, d["id"], [pr for pr in d["premises"]]))
    if suspect:
        print("\nDIAGNOSTIC -- answers constrained by a known engine limitation:")
        for c, did, prem in suspect:
            agree = "matches gold" if kir[c] == expected[c] else "differs from gold"
            print(f"  {c}: derived via {did} from {prem}, whose premise is REFUTED.")
            print(f"     The engine cannot derive REFUTED for a conclusion, so UNRESOLVED is")
            print(f"     the only answer available to it. It {agree}, but not by reasoning.")
            alt = dict(expected); alt[c] = "REFUTED"
            aa_l = sum(1 for pp, v in alt.items() if llm.get(pp) == v) / n
            aa_k = sum(1 for pp, v in alt.items() if kir[pp] == v) / n
            print(f"     If gold for this claim is really REFUTED: llm={aa_l:.3f} "
                  f"kir={aa_k:.3f} margin={(aa_k - aa_l) * 100:+.1f} pts")

    margin = (a_k - a_l) * 100
    print(f"\nPRE-REGISTERED margin: {margin:+.1f} pts (target >= +10)")
    print("verdict:", "PASS" if margin >= 10 else ("TIE/LOSS" if margin <= 0 else "BELOW TARGET"))
    print(f"\nn={n} claims on one chain. Each claim is worth {100/n:.0f} points. This is a "
          f"single-shot result on a pre-registered set, which removes the iterate-until-favourable "
          f"flaw but NOT the small-sample problem, and not the fact that the gold was authored by "
          f"the system's author.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
