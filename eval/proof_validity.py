#!/usr/bin/env python3
"""Measure proof-chain validity and hallucinated-step rate.

Two of the stated success targets are measurable with no LLM and no baseline:

    proof-chain validity            >= 99% of returned proof steps valid
    unsupported/hallucinated steps  <  0.5%

A returned proof step is VALID only if every one of these holds:

  derivation step
    - the named derivation exists in the graph
    - its conclusion is the proposition the step claims to justify
    - its validity is not INVALID
    - the premises listed in the trace are exactly the derivation's premises
    - every premise child is itself a valid sub-proof

  ground-evidence step
    - every named evidence id exists
    - each is status=active, stance=supports
    - each actually attaches to the proposition the step justifies

A step is HALLUCINATED if it names a derivation or evidence id that is not in
the graph, or if it terminates in `UNKNOWN` (the engine claiming support it
cannot account for). Those are counted separately from ordinary invalidity
because a fabricated citation is a different failure from a badly formed one.

Run over every supported proposition in every graph, before and after the
retraction, since a proof that is valid only before the retraction is exactly
the thing that must not be returned afterwards.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "reasoner"))
from epistemic_query import Graph  # noqa: E402


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


class ProofAudit:
    def __init__(self, graph: Graph, retracted: set[str] | None = None):
        self.g = graph
        self.retracted = retracted or set()
        self.steps = 0
        self.invalid: list[str] = []
        self.hallucinated: list[str] = []

    def audit(self, trace, expect_prop: str | None = None):
        if trace is None:
            return
        self.steps += 1
        pid = trace.get("proposition")

        if expect_prop is not None and pid != expect_prop:
            self.invalid.append(
                f"step claims {pid!r} where its parent needed {expect_prop!r}")
            return

        via = trace.get("via")

        if via == "ground_evidence":
            for eid in trace.get("evidence", []):
                ev = self.g.evidence.get(eid)
                if ev is None:
                    self.hallucinated.append(f"{pid}: evidence {eid!r} does not exist")
                    continue
                if ev["proposition_id"] != pid:
                    self.invalid.append(
                        f"{pid}: evidence {eid} attaches to "
                        f"{ev['proposition_id']}, not this proposition")
                if ev["status"] != "active" or eid in self.retracted:
                    self.invalid.append(f"{pid}: evidence {eid} is not active")
                if ev["stance"] != "supports":
                    self.invalid.append(
                        f"{pid}: evidence {eid} has stance {ev['stance']}, "
                        f"cited as support")
            if not trace.get("evidence"):
                self.invalid.append(f"{pid}: ground step cites no evidence")
            return

        if via == "derivation":
            did = trace.get("derivation")
            d = self.g.derivations.get(did)
            if d is None:
                self.hallucinated.append(f"{pid}: derivation {did!r} does not exist")
                return
            if d["conclusion"] != pid:
                self.invalid.append(
                    f"{pid}: derivation {did} concludes {d['conclusion']}")
            if d["validity"] == "INVALID":
                self.invalid.append(f"{pid}: derivation {did} is INVALID")
            children = trace.get("premises") or []
            got = [c.get("proposition") for c in children if c]
            if sorted(got) != sorted(d["premises"]):
                self.invalid.append(
                    f"{pid}: trace premises {sorted(got)} != derivation "
                    f"premises {sorted(d['premises'])}")
            for child in children:
                if child is None:
                    self.invalid.append(f"{pid}: a premise sub-proof is missing")
                    continue
                self.audit(child, expect_prop=child.get("proposition"))
            return

        if via == "CYCLE":
            self.invalid.append(f"{pid}: proof is circular")
            return

        self.hallucinated.append(
            f"{pid}: step type {via!r}, engine claims support it cannot account for")


def run(path: Path, retract_group: str | None):
    data = load(path)
    graph = Graph(data)
    scenarios = [("before", set())]
    if retract_group:
        targets = graph.evidence_from_group(retract_group)
        if targets:
            scenarios.append((f"after retracting {retract_group}", targets))

    out = []
    for label, retracted in scenarios:
        statuses, _ = graph.status_map(retracted=retracted)
        audit = ProofAudit(graph, retracted)
        traced = 0
        # A proof of support legitimately exists for INCONSISTENT claims too:
        # inconsistent means supported AND refuted, so the support side has a
        # real proof. The requirement is that the trace DISCLOSES the conflict,
        # not that it be withheld. Getting this rule wrong was the auditor's own
        # first failure.
        provable = {"SUPPORTED", "INCONSISTENT"}
        for pid, status in statuses.items():
            trace = graph.proof_trace(pid, retracted=retracted or None)
            if status in provable:
                if trace is None:
                    audit.invalid.append(
                        f"{pid}: reported {status} but no proof was returned")
                    continue
                traced += 1
                if status == "INCONSISTENT":
                    if not trace.get("contested"):
                        audit.invalid.append(
                            f"{pid}: INCONSISTENT but the trace does not "
                            f"disclose that it is contested")
                    elif not trace.get("counter_evidence"):
                        audit.invalid.append(
                            f"{pid}: flagged contested but cites no "
                            f"counter-evidence")
                audit.audit(trace, expect_prop=pid)
            elif trace is not None:
                audit.invalid.append(
                    f"{pid}: status {status} yet a proof was returned")
        out.append({
            "graph": path.name, "scenario": label,
            "proved": traced, "steps": audit.steps,
            "invalid": audit.invalid, "hallucinated": audit.hallucinated,
        })
    return out


GRAPHS = [
    ("scientific-dependency/corpus/fujii-ponv.json", "FUJII-SERIES"),
    ("scientific-dependency/corpus/fujii-combination-review.json", "FUJII-SERIES"),
    ("scientific-dependency/fixtures/chain-fixture.json", None),
]


def main():
    results = []
    for rel, group in GRAPHS:
        results.extend(run(ROOT / rel, group))

    total_steps = sum(r["steps"] for r in results)
    total_invalid = sum(len(r["invalid"]) for r in results)
    total_hall = sum(len(r["hallucinated"]) for r in results)

    hdr = f"{'graph':38} {'scenario':34} {'proved':7} {'steps':6} {'invalid':8} {'halluc'}"
    print(hdr)
    print("-" * (len(hdr) + 2))
    for r in results:
        print(f"{r['graph']:38} {r['scenario']:34} {r['proved']:<7} "
              f"{r['steps']:<6} {len(r['invalid']):<8} {len(r['hallucinated'])}")

    for r in results:
        for m in r["invalid"]:
            print(f"  INVALID      [{r['graph']} {r['scenario']}] {m}")
        for m in r["hallucinated"]:
            print(f"  HALLUCINATED [{r['graph']} {r['scenario']}] {m}")

    valid = total_steps - total_invalid - total_hall
    validity = valid / total_steps if total_steps else 0.0
    hall_rate = total_hall / total_steps if total_steps else 0.0

    print()
    print(f"proof steps audited        {total_steps}")
    print(f"proof-chain validity       {validity:.4f}   target >= 0.99  "
          f"{'PASS' if validity >= 0.99 else 'FAIL'}")
    print(f"hallucinated step rate     {hall_rate:.4f}   target <  0.005 "
          f"{'PASS' if hall_rate < 0.005 else 'FAIL'}")
    print()
    print(f"NOTE: n={total_steps} proof steps over 3 graphs. These are real "
          f"measurements of two stated targets, on hand-authored graphs. They say "
          f"the engine does not fabricate or mis-cite its own justifications; they "
          f"say nothing about whether an LLM would build the right graph.")
    return 0 if (validity >= 0.99 and hall_rate < 0.005) else 1


if __name__ == "__main__":
    sys.exit(main())
