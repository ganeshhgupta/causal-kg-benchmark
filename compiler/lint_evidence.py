#!/usr/bin/env python3
"""Lint a compiled K-IR graph for the extraction errors measured as dangerous.

Earned, not invented: eval/robustness_eval.py measured that mis-encoding a null
result as `supports` instead of `refutes` is the single most dangerous compiler
error, because it silently reports a refuted claim as SUPPORTED with no other
symptom. Every other measured error degrades recall, which is visible. This one
degrades safety, which is not.

So this lints exactly that, plus the two other measured failures that make a
graph unusable rather than merely wrong:

  NULL_RESULT_AS_SUPPORT  evidence whose source text reads as a null or negative
                          finding but whose stance is `supports`
  PREBAKED_RETRACTION     evidence already marked retracted, so no before/after
                          question can be asked of this graph
  UNGROUPED_MULTI_SOURCE  several evidence items on one proposition with no
                          independence_group anywhere, so "retract everything
                          from one source" is not expressible

Deliberately NOT linted: false merges and claim splits. Both are real errors, but
they need semantic judgement about whether two claims are the same claim, which a
keyword rule would only pretend to do. They are measured in robustness_eval
instead, and they remain the strongest argument for a canonicalization stage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Phrases that indicate the cited finding is null or negative. Matched against
# Evidence.source, which the extraction spec requires to describe the finding.
NULL_MARKERS = [
    r"\bno\s+evidence\b",
    r"\bno\s+synergism\b",
    r"\bnot\s+different\b",
    r"\bno\s+difference\b",
    r"\bno\s+significant\b",
    r"\bfailed\s+to\b",
    r"\bfailed\s+replication\b",
    r"\bnull\s+result\b",
    r"\bantagonism\b",
    r"\bdid\s+not\b",
]
NULL_RE = re.compile("|".join(NULL_MARKERS), re.IGNORECASE)


def _claim_text(data: dict, prop_id: str) -> str:
    """The claim's own wording, plus its predicate label.

    Needed because the null-marker rule is otherwise proposition-blind: a graph
    may legitimately contain a proposition that ASSERTS a negative finding
    (\"antiemetics are antagonistic\"), and evidence supporting that claim will
    naturally describe antagonism. Found by linting a blind LLM extraction,
    which modelled antagonism as its own claim and tripped a false positive.
    """
    prop = next((p for p in data.get("propositions", []) if p["id"] == prop_id), None)
    if not prop:
        return ""
    parts = list(prop.get("surface_forms") or [])
    pred = prop.get("predicate", "")
    parts.append(pred)
    for s in data.get("symbols", []):
        if s["id"] == pred:
            parts.append(s.get("label", ""))
    return " ".join(parts)


def lint(data: dict) -> list[dict]:
    findings = []
    evidence = data.get("evidence", [])

    by_prop: dict[str, list[dict]] = {}
    for ev in evidence:
        by_prop.setdefault(ev["proposition_id"], []).append(ev)

    for ev in evidence:
        hit = NULL_RE.search(ev.get("source", "") + " " + (ev.get("notes") or ""))
        # Only a mis-encoding if the negative word is NOT part of the claim
        # itself. Evidence describing antagonism legitimately supports a claim
        # that antagonism occurs.
        if hit and re.search(re.escape(hit.group(0)), _claim_text(data, ev["proposition_id"]), re.I):
            hit = None
        if hit and ev["stance"] == "supports":
            findings.append({
                "rule": "NULL_RESULT_AS_SUPPORT",
                "severity": "dangerous",
                "evidence": ev["id"],
                "proposition": ev["proposition_id"],
                "detail": f"source reads as a null/negative finding "
                          f"({hit.group(0)!r}) but stance is 'supports'. If this "
                          f"is wrong, a refuted claim will be reported SUPPORTED.",
            })
        if ev["status"] == "retracted":
            findings.append({
                "rule": "PREBAKED_RETRACTION",
                "severity": "unusable",
                "evidence": ev["id"],
                "proposition": ev["proposition_id"],
                "detail": "evidence is already retracted in the graph, so a "
                          "before/after retraction query cannot be asked. "
                          "Retraction belongs in the query.",
            })

    if evidence and not any(ev.get("independence_group") for ev in evidence):
        multi = [p for p, evs in by_prop.items() if len(evs) > 1]
        if multi:
            findings.append({
                "rule": "UNGROUPED_MULTI_SOURCE",
                "severity": "unusable",
                "evidence": None,
                "proposition": multi[0],
                "detail": f"{len(multi)} proposition(s) carry several evidence "
                          f"items but no evidence has an independence_group, so "
                          f"source-level retraction is not expressible.",
            })
    return findings


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: lint_evidence.py <graph.json> [...]", file=sys.stderr)
        return 2

    total = 0
    for path in argv:
        with open(path, encoding="utf-8") as fh:
            findings = lint(json.load(fh))
        name = Path(path).name
        if not findings:
            print(f"{name}: clean")
            continue
        print(f"{name}: {len(findings)} finding(s)")
        for f in findings:
            tgt = f["evidence"] or f["proposition"]
            print(f"  [{f['severity']:9}] {f['rule']:24} {tgt}")
            print(f"              {f['detail']}")
        total += len(findings)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
