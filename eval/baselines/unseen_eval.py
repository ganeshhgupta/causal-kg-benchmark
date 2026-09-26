#!/usr/bin/env python3
"""Independent margin: LLM baseline vs K-IR on claims NEITHER has been tuned on.

Why this file exists. The first baseline run (cycle 6) measured a margin on the
six claims that then revealed two bugs in the hand-built artefacts. Fixing those
bugs and re-measuring on the same six is not an independent comparison, and the
corpus carries a CONTAMINATION-MARKER saying so. This run uses two different
chains the baseline has never seen, in two different domains, neither carrying a
contamination marker.

Refuses to score any query whose graph carries a contamination marker.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph, author_groups  # noqa: E402

GOLD = json.load(open(ROOT / "scientific-dependency" / "gold_queries.json"))
ANSWERS = json.load(open(ROOT / "eval" / "baselines" / "llm" / "fair_answers.json"))
QUERIES = ["Q-SATO-BISPHOSPHONATE", "Q-FUJII-COMBO-REVIEW"]

llm = {a["claim_id"]: a["status"] for a in ANSWERS["answers"]}
expected, kir, per_chain = {}, {}, []

for qid in QUERIES:
    q = next(x for x in GOLD["queries"] if x["id"] == qid)
    data = json.load(open(ROOT / "scientific-dependency" / q["graph"]))
    graph = Graph(data)
    marked = [e["id"] for e in graph.evidence.values()
              if "CONTAMINATION-MARKER" in (e.get("notes") or "")]
    if marked:
        sys.exit(f"REFUSING {qid}: graph carries contamination marker {marked}")
    groups = {e.get("independence_group") for e in graph.evidence.values()} - {None}
    author = q["retract_independence_group"]
    targets = {e["id"] for e in graph.evidence.values()
               if e.get("independence_group") == author}
    if not targets:
        key = "sato" if "SATO" in qid else "fujii"
        targets = {e["id"] for e in graph.evidence.values()
                   if e.get("independence_group") in author_groups(groups, key)}
    st, _ = graph.status_map(retracted=targets)
    chain_exp = {pid: g["after"] for pid, g in q["expected"].items()}
    expected.update(chain_exp)
    for pid in chain_exp:
        kir[pid] = st[pid]
    ok_l = sum(1 for p, v in chain_exp.items() if llm.get(p) == v)
    ok_k = sum(1 for p, v in chain_exp.items() if kir[p] == v)
    per_chain.append((qid, len(chain_exp), ok_l, ok_k))

w = max(len(p) for p in expected) + 2
print(f"{'claim':{w}} {'GOLD':11} {'LLM':11} {'K-IR':11}")
print("-" * (w + 36))
for pid, want in expected.items():
    l, k = llm.get(pid, "MISSING"), kir[pid]
    flag = ""
    if l != want and k == want:
        flag = "  K-IR only"
    elif l == want and k != want:
        flag = "  LLM only"
    elif l != want and k != want:
        flag = "  both wrong"
    print(f"{pid:{w}} {want:11} {l:11} {k:11}{flag}")

n = len(expected)
a_l = sum(1 for p, v in expected.items() if llm.get(p) == v) / n
a_k = sum(1 for p, v in expected.items() if kir[p] == v) / n
fs_l = [p for p, v in expected.items() if v != "SUPPORTED" and llm.get(p) == "SUPPORTED"]
fs_k = [p for p, v in expected.items() if v != "SUPPORTED" and kir[p] == "SUPPORTED"]

print()
for qid, cn, ok_l, ok_k in per_chain:
    print(f"  {qid:26} n={cn}  llm={ok_l}/{cn}  kir={ok_k}/{cn}")
print()
print(f"llm_with_source_in_context   accuracy={a_l:.3f}  false_survival={len(fs_l)} {fs_l}")
print(f"kir_reasoner                 accuracy={a_k:.3f}  false_survival={len(fs_k)} {fs_k}")
margin = (a_k - a_l) * 100
print(f"\nINDEPENDENT margin on unseen claims: {margin:+.1f} pts (target >= +10)")
print("verdict:", "PASS" if margin >= 10 else ("TIE/LOSS" if margin <= 0 else "BELOW TARGET"))
print(f"\nn={n} claims across 2 chains and 2 domains, no contamination markers. "
      f"Each claim is worth {100/n:.1f} points, so this is still directional.")
