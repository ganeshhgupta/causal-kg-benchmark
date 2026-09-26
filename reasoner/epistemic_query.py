#!/usr/bin/env python3
"""Least-fixpoint support engine over a K-IR v0.3 graph.

This is one algorithm serving two purposes:

  * the v0.3 definition of epistemic status (replacing v0.2's evidence-count
    rule, which could not see past one hop), and
  * the retraction-propagation reasoner ("paper X was retracted, which claims
    lose support?").

Definition
----------
    supported(P)  <==  some ACTIVE ground Evidence with stance=supports for P
    supported(P)  <==  some Derivation D with validity != INVALID,
                       conclusion(D) = P, and every premise of D supported

    refuted(P)    <==  some ACTIVE ground Evidence with stance=refutes for P

    status(P) = INCONSISTENT  if supported and refuted
                SUPPORTED     if supported only
                REFUTED       if refuted only
                UNRESOLVED    if neither

Computed as a least fixpoint, so a derivation cycle supports nothing, which is
the correct answer rather than an accident. Depth is unbounded: a chain
P -> Q -> R -> S collapses entirely when P's evidence is retracted, which was
exactly v0.2's documented one-hop limitation.

Known limitation, deliberately not fixed until a real task fails on it: derived
REFUTATION is not modelled. Refutation comes only from ground evidence, because
deriving "not P" needs negation handling that nothing has yet demanded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

POLICY = "least-fixpoint-v0.3"


class Graph:
    def __init__(self, data: dict):
        self.data = data
        self.propositions = {p["id"]: p for p in data.get("propositions", [])}
        self.evidence = {e["id"]: e for e in data.get("evidence", [])}
        self.assertions = {a["id"]: a for a in data.get("assertions", [])}
        self.derivations = {d["id"]: d for d in data.get("derivations", [])}
        self.rules = {r["id"]: r for r in data.get("rules", [])}

    # ---- core fixpoint ---------------------------------------------------
    def ground_support(self, retracted: set[str] | None = None):
        """Propositions with active ground supporting/refuting evidence."""
        retracted = retracted or set()
        sup, ref = set(), set()
        for ev in self.evidence.values():
            if ev["id"] in retracted or ev["status"] != "active":
                continue
            target = sup if ev["stance"] == "supports" else ref
            target.add(ev["proposition_id"])
        return sup, ref

    def solve(self, retracted: set[str] | None = None):
        """Least fixpoint. Returns (supported, refuted, warranted_derivations)."""
        supported, refuted = self.ground_support(retracted)
        usable = [d for d in self.derivations.values() if d["validity"] != "INVALID"]

        changed = True
        while changed:
            changed = False
            for d in usable:
                if d["conclusion"] in supported:
                    continue
                if all(prem in supported for prem in d["premises"]):
                    supported.add(d["conclusion"])
                    changed = True

        warranted = {
            d["id"]
            for d in usable
            if all(prem in supported for prem in d["premises"])
        }
        return supported, refuted, warranted

    def status_map(self, retracted: set[str] | None = None):
        supported, refuted, warranted = self.solve(retracted)
        out = {}
        for pid in self.propositions:
            s, r = pid in supported, pid in refuted
            if s and r:
                out[pid] = "INCONSISTENT"
            elif s:
                out[pid] = "SUPPORTED"
            elif r:
                out[pid] = "REFUTED"
            else:
                out[pid] = "UNRESOLVED"
        return out, warranted

    # ---- retraction query ------------------------------------------------
    def evidence_from_group(self, group: str) -> set[str]:
        return {e["id"] for e in self.evidence.values()
                if e.get("independence_group") == group}

    def evidence_from_source(self, source_substring: str) -> set[str]:
        """Select evidence by source text. UNSAFE and deliberately strict.

        Found by the Fujii combination-review corpus: matching 'Fujii' also
        matched evidence whose source reads 'trials by authors OTHER THAN Fujii',
        so the refuting evidence was retracted alongside the fraudulent evidence
        and a REFUTED answer silently became UNRESOLVED. Re-analysis papers
        routinely describe their evidence by contrast to the author under
        suspicion, so this is the normal case, not an edge case.

        Selection that spans more than one independence_group is therefore
        refused rather than guessed at. Use a group selector for real queries.
        """
        needle = source_substring.lower()
        hits = [e for e in self.evidence.values()
                if needle in e.get("source", "").lower()]
        groups = {e.get("independence_group") for e in hits}
        if len(groups) > 1:
            detail = "\n".join(
                f"    {e['id']}  group={e.get('independence_group')!r}  "
                f"source={e.get('source', '')[:70]!r}" for e in hits)
            raise ValueError(
                f"source match {source_substring!r} spans {len(groups)} "
                f"independence groups {sorted(map(str, groups))}, so it cannot "
                f"be what you meant. Matched:\n{detail}\n"
                f"  Use --retract-group instead.")
        return {e["id"] for e in hits}

    def retract(self, evidence_ids: set[str]):
        """Classify every proposition's fate when `evidence_ids` are retracted.

        Classes mirror what the task actually needs distinguished:
          STILL_SUPPORTED        supported before and after
          LOST_SUPPORT           was SUPPORTED, no longer is
          RESOLVED_INCONSISTENCY was INCONSISTENT, now has a definite status.
                                 Earned by the real Fujii/PONV chain: antiemetic
                                 synergism was supported only by the retracted
                                 trials while other authors found antagonism, so
                                 the retraction RESOLVES a conflict rather than
                                 destroying support. Not a class the original
                                 spec anticipated.
          LOST_A_DERIVATION      status unchanged, but at least one supporting
                                 derivation stopped carrying warrant (fragility
                                 signal: redundant support absorbed the hit)
          UNAFFECTED             nothing changed for this proposition
        """
        unknown = evidence_ids - set(self.evidence)
        if unknown:
            raise KeyError(f"unknown evidence ids: {sorted(unknown)}")

        before, warr_before = self.status_map()
        after, warr_after = self.status_map(retracted=evidence_ids)
        lost_derivations = warr_before - warr_after

        supporting_dervs: dict[str, set[str]] = {}
        for did in lost_derivations:
            concl = self.derivations[did]["conclusion"]
            supporting_dervs.setdefault(concl, set()).add(did)

        report = {}
        for pid in self.propositions:
            b, a = before[pid], after[pid]
            if b != a:
                if b == "SUPPORTED":
                    cls = "LOST_SUPPORT"
                elif b == "INCONSISTENT":
                    cls = "RESOLVED_INCONSISTENCY"
                else:
                    cls = "CHANGED"
            elif pid in supporting_dervs:
                cls = "LOST_A_DERIVATION"
            elif b == "SUPPORTED":
                cls = "STILL_SUPPORTED"
            else:
                cls = "UNAFFECTED"
            report[pid] = {
                "before": b,
                "after": a,
                "class": cls,
                "lost_derivations": sorted(supporting_dervs.get(pid, ())),
            }
        return report

    # ---- proof traces ----------------------------------------------------
    def proof_trace(self, pid: str, retracted: set[str] | None = None, _seen=None):
        """Why is pid supported? Returns a nested trace, or None if unsupported.

        Every returned step is one that actually carries warrant, which is what
        makes proof-step validity measurable rather than asserted.

        Every node carries the proposition's epistemic status and, when it is
        contested, the counter-evidence. Found by eval/proof_validity.py: the
        engine previously returned a clean, entirely valid support-proof for a
        claim whose status was INCONSISTENT, with nothing in the output saying
        so. Asking "why is this true" and getting an unqualified proof of a
        contested claim is misleading even when every step checks out, and a
        contested PREMISE deep in a chain is worse, because the weakness is
        invisible at the top.
        """
        supported, refuted, warranted = self.solve(retracted)
        if pid not in supported:
            return None
        _seen = _seen or set()
        if pid in _seen:
            return {"proposition": pid, "via": "CYCLE"}
        _seen = _seen | {pid}

        retracted = retracted or set()
        contested = pid in refuted
        node = {
            "proposition": pid,
            "status": "INCONSISTENT" if contested else "SUPPORTED",
            "contested": contested,
        }
        if contested:
            node["counter_evidence"] = sorted(
                e["id"] for e in self.evidence.values()
                if e["proposition_id"] == pid and e["status"] == "active"
                and e["id"] not in retracted and e["stance"] == "refutes")

        ground = [
            e["id"] for e in self.evidence.values()
            if e["proposition_id"] == pid and e["status"] == "active"
            and e["id"] not in retracted and e["stance"] == "supports"
        ]
        if ground:
            return {**node, "via": "ground_evidence", "evidence": ground}

        for d in self.derivations.values():
            if d["conclusion"] != pid or d["id"] not in warranted:
                continue
            premises = [self.proof_trace(p, retracted, _seen) for p in d["premises"]]
            return {
                **node,
                "via": "derivation",
                "derivation": d["id"],
                "rule": d.get("rule_id"),
                "relation": d.get("relation"),
                # True if this proof rests on a contested claim at any depth.
                "rests_on_contested": any(
                    p and (p.get("contested") or p.get("rests_on_contested"))
                    for p in premises),
                "premises": premises,
            }
        return {**node, "via": "UNKNOWN"}


def materialize(graph: Graph) -> list[dict]:
    """Recompute the epistemic_status view from scratch."""
    statuses, warranted = graph.status_map()
    version = graph.data.get("graph_version")
    out = []
    for pid, status in statuses.items():
        ev_for, ev_against = [], []
        for e in graph.evidence.values():
            if e["proposition_id"] != pid or e["status"] != "active":
                continue
            (ev_for if e["stance"] == "supports" else ev_against).append(e["id"])
        out.append({
            "proposition_id": pid,
            "status": status,
            "computed_from": {"policy": POLICY, "graph_version": version},
            "evidence_for": sorted(ev_for),
            "evidence_against": sorted(ev_against),
            "derivations_supporting": sorted(
                d["id"] for d in graph.derivations.values()
                if d["conclusion"] == pid and d["id"] in warranted
            ),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("graph", type=Path)
    ap.add_argument("--retract-evidence", nargs="*", default=None,
                    help="Evidence ids to retract.")
    ap.add_argument("--retract-group", default=None,
                    help="Retract every evidence in this independence_group. "
                         "The safe selector; prefer it.")
    ap.add_argument("--retract-source", default=None,
                    help="Retract every evidence whose source matches this "
                         "substring. Unsafe: refuses if the match spans several "
                         "independence groups.")
    ap.add_argument("--trace", default=None, help="Print the proof trace for a proposition id.")
    ap.add_argument("--materialize", action="store_true",
                    help="Print the recomputed epistemic_status view.")
    args = ap.parse_args(argv)

    with open(args.graph, encoding="utf-8") as fh:
        graph = Graph(json.load(fh))

    if args.materialize:
        print(json.dumps(materialize(graph), indent=2))
        return 0

    if args.trace:
        print(json.dumps(graph.proof_trace(args.trace), indent=2))
        return 0

    targets: set[str] = set(args.retract_evidence or ())
    if args.retract_group:
        matched = graph.evidence_from_group(args.retract_group)
        if not matched:
            print(f"no evidence in group '{args.retract_group}'", file=sys.stderr)
            return 2
        targets |= matched
    if args.retract_source:
        try:
            matched = graph.evidence_from_source(args.retract_source)
        except ValueError as exc:
            print(f"refusing ambiguous selection: {exc}", file=sys.stderr)
            return 2
        if not matched:
            print(f"no evidence matched source '{args.retract_source}'", file=sys.stderr)
            return 2
        targets |= matched

    if not targets:
        statuses, _ = graph.status_map()
        for pid, st in sorted(statuses.items()):
            print(f"{st:13} {pid}")
        return 0

    report = graph.retract(targets)
    print(f"retracting {len(targets)} evidence object(s): {sorted(targets)}\n")
    order = {"LOST_SUPPORT": 0, "RESOLVED_INCONSISTENCY": 1, "CHANGED": 2,
             "LOST_A_DERIVATION": 3, "STILL_SUPPORTED": 4, "UNAFFECTED": 5}
    for pid, r in sorted(report.items(), key=lambda kv: (order[kv[1]["class"]], kv[0])):
        extra = f"  lost_derivations={r['lost_derivations']}" if r["lost_derivations"] else ""
        print(f"{r['class']:18} {pid:28} {r['before']} -> {r['after']}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def author_groups(groups, author: str) -> set[str]:
    """Independence groups attributable to `author`, excluding NEGATED groups.

    Recurrence-driven. The reasoner CLI already refuses a source-substring
    selection that spans several independence groups, because matching 'Fujii'
    also matched evidence described as 'trials by authors other than Fujii'.
    The identical bug then reappeared in eval/extracted_eval.py, where a group
    named 'ig_non_fujii_trials' matched a naive `'fujii' in name` test and the
    refuting evidence was retracted along with the fraudulent evidence.

    Two sites, same mistake, so the guard lives here rather than at each call
    site. Corpora name the contrast group after the author under suspicion
    ('non-Fujii', 'non_fujii', 'other than Fujii'), so that is the normal case.
    """
    import re
    a = re.escape(author)
    # NB: no \b before 'non' -- underscore is a word character, so \b never
    # fires in 'ig_non_fujii_trials'. That near-miss is why this is tested.
    negated = re.compile(
        rf"(non|other[_\-\s]?than|excluding|without|minus)[_\-\s]*{a}", re.I)
    return {g for g in groups
            if g and re.search(a, g, re.I) and not negated.search(g)}
