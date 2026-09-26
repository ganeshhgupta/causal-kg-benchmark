#!/usr/bin/env python3
"""Baselines for retraction propagation, and the margin K-IR reasoning gets.

IMPORTANT SCOPE NOTE. These are NOT LLM baselines. They are the non-LLM methods
that the published literature actually uses, plus one heuristic that mimics the
specific mistake an LLM reader makes. An LLM-only and an LLM+RAG baseline remain
unmeasured, so the headline "beats LLM+RAG" claim is NOT supported by this file.
What it does support is a margin over the current practice in the field.

  citation_cascade
      The prior art. If a paper cites or contains retracted work, treat its
      claims as affected. This is citation-level and binary, which is exactly
      where the "retraction cascade" literature stops (~5,000 citing articles
      classified dependent vs non-dependent). Implemented here as: any claim
      with at least one retracted evidence item loses support.

  stance_blind_survivors
      Mimics an LLM that checks whether literature on the claim still exists
      without tracking what that literature says. If any non-retracted evidence
      remains, call the claim supported.

  recency_wins
      Mimics an LLM that resolves conflict by trusting the newest source.

  kir_reasoner
      Ours: least fixpoint over stance-typed evidence and derivations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph  # noqa: E402

CORPUS = ROOT / "scientific-dependency" / "corpus" / "fujii-ponv.json"
GOLD = ROOT / "scientific-dependency" / "gold_queries.json"
GROUP = "FUJII-SERIES"


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def targets_for(graph: Graph) -> set[str]:
    return {e["id"] for e in graph.evidence.values()
            if e.get("independence_group") == GROUP}


# --- baselines: each returns {proposition_id: after_status} -----------------

def citation_cascade(graph: Graph, retracted: set[str]):
    out = {}
    for pid in graph.propositions:
        touched = any(e["proposition_id"] == pid and e["id"] in retracted
                      for e in graph.evidence.values())
        out[pid] = "UNRESOLVED" if touched else "SUPPORTED"
    return out


def stance_blind_survivors(graph: Graph, retracted: set[str]):
    out = {}
    for pid in graph.propositions:
        remaining = [e for e in graph.evidence.values()
                     if e["proposition_id"] == pid
                     and e["id"] not in retracted and e["status"] == "active"]
        out[pid] = "SUPPORTED" if remaining else "UNRESOLVED"
    return out


def recency_wins(graph: Graph, retracted: set[str]):
    """Trust the newest surviving assertion about each claim."""
    out = {}
    for pid in graph.propositions:
        live = [a for a in graph.assertions.values()
                if a["proposition_id"] == pid and a["status"] == "active"]
        if not live:
            out[pid] = "UNRESOLVED"
            continue
        newest = max(live, key=lambda a: a.get("year") or 0)
        out[pid] = {"supports": "SUPPORTED", "refutes": "REFUTED",
                    "neutral_report": "UNRESOLVED"}[newest["stance"]]
    return out


def kir_reasoner(graph: Graph, retracted: set[str]):
    statuses, _ = graph.status_map(retracted=retracted)
    return statuses


BASELINES = {
    "citation_cascade": citation_cascade,
    "stance_blind_survivors": stance_blind_survivors,
    "recency_wins": recency_wins,
    "kir_reasoner": kir_reasoner,
}


def main():
    gold_q = next(q for q in load(GOLD)["queries"] if q["id"] == "Q-FUJII-PONV")
    expected = {pid: g["after"] for pid, g in gold_q["expected"].items()}
    graph = Graph(load(CORPUS))
    retracted = targets_for(graph)

    print(f"query: {gold_q['id']}   claims: {len(expected)}   "
          f"retracted evidence: {len(retracted)}\n")

    rows = []
    for name, fn in BASELINES.items():
        pred = fn(graph, retracted)
        correct = sum(1 for pid, want in expected.items() if pred.get(pid) == want)
        # Danger is defined on the answer, same as the scorers.
        false_survival = [pid for pid, want in expected.items()
                          if want != "SUPPORTED" and pred.get(pid) == "SUPPORTED"]
        false_collapse = [pid for pid, want in expected.items()
                          if want == "SUPPORTED" and pred.get(pid) != "SUPPORTED"]
        rows.append((name, correct / len(expected), false_survival, false_collapse, pred))

    hdr = f"{'method':24} {'accuracy':9} {'false_survival':15} {'false_collapse'}"
    print(hdr)
    print("-" * (len(hdr) + 2))
    for name, acc, fs, fc, _ in rows:
        print(f"{name:24} {acc:8.3f}  {len(fs):<15} {len(fc)}")

    print("\nper-claim answers (gold first):")
    width = max(len(p) for p in expected) + 2
    print(f"{'claim':{width}} {'GOLD':11} " +
          " ".join(f"{n[:14]:14}" for n, *_ in rows))
    for pid, want in expected.items():
        cells = " ".join(f"{r[4].get(pid, '-')[:14]:14}" for r in rows)
        print(f"{pid:{width}} {want:11} {cells}")

    best_baseline = max((r for r in rows if r[0] != "kir_reasoner"), key=lambda r: r[1])
    ours = next(r for r in rows if r[0] == "kir_reasoner")
    margin = (ours[1] - best_baseline[1]) * 100
    print(f"\nbest non-LLM baseline: {best_baseline[0]} at {best_baseline[1]:.3f}")
    print(f"k-ir reasoner:         {ours[1]:.3f}")
    print(f"margin:                {margin:+.1f} percentage points")
    print(f"\nfalse survivals -- baselines {sum(len(r[2]) for r in rows if r[0] != 'kir_reasoner')}, "
          f"k-ir {len(ours[2])}")
    print("\nNOT MEASURED: LLM-only and LLM+RAG baselines. The margin above is "
          "over non-LLM methods, which is what the field currently does, and it "
          "does not license any claim about beating an LLM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
