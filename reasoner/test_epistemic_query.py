#!/usr/bin/env python3
"""Tests for the least-fixpoint support engine.

Each test asserts a property the retraction task actually depends on, so a
regression here is a regression in the headline capability, not a style nit.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from epistemic_query import Graph, materialize  # noqa: E402

FIXTURE = Path(__file__).parent.parent / "scientific-dependency" / "fixtures" / "chain-fixture.json"


def load():
    with open(FIXTURE, encoding="utf-8") as fh:
        return Graph(json.load(fh))


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))
    return cond


def main():
    g = load()
    ok = True

    # --- baseline statuses -------------------------------------------------
    before, _ = g.status_map()
    ok &= check("depth-3 chain all supported before retraction",
                all(before[p] == "SUPPORTED" for p in ("P-ROOT", "P-MID", "P-LEAF")),
                str({p: before[p] for p in ("P-ROOT", "P-MID", "P-LEAF")}))
    ok &= check("refuting-only evidence gives REFUTED", before["P-REFUTED"] == "REFUTED", before["P-REFUTED"])
    ok &= check("no evidence gives UNRESOLVED, not REFUTED",
                before["P-UNTESTED"] == "UNRESOLVED", before["P-UNTESTED"])
    ok &= check("derivation cycle supports nothing (least fixpoint)",
                before["P-CYCLE-1"] == "UNRESOLVED" and before["P-CYCLE-2"] == "UNRESOLVED",
                f"{before['P-CYCLE-1']}/{before['P-CYCLE-2']}")

    # --- the headline capability: unbounded-depth propagation --------------
    rep = g.retract({"EV-ROOT"})
    ok &= check("root loses support", rep["P-ROOT"]["class"] == "LOST_SUPPORT", rep["P-ROOT"]["class"])
    ok &= check("depth-2 claim loses support", rep["P-MID"]["class"] == "LOST_SUPPORT", rep["P-MID"]["class"])
    ok &= check("depth-3 claim loses support (v0.2 could not do this)",
                rep["P-LEAF"]["class"] == "LOST_SUPPORT", rep["P-LEAF"]["class"])
    ok &= check("collapsed claims become UNRESOLVED, never REFUTED",
                all(rep[p]["after"] == "UNRESOLVED" for p in ("P-ROOT", "P-MID", "P-LEAF")),
                str({p: rep[p]["after"] for p in ("P-ROOT", "P-MID", "P-LEAF")}))

    # --- redundant support must absorb the hit, and report it --------------
    ok &= check("independently replicated claim survives",
                rep["P-REDUNDANT"]["after"] == "SUPPORTED", rep["P-REDUNDANT"]["after"])
    ok &= check("but its lost derivation path is reported",
                rep["P-REDUNDANT"]["class"] == "LOST_A_DERIVATION"
                and rep["P-REDUNDANT"]["lost_derivations"] == ["D-REDUNDANT"],
                f"{rep['P-REDUNDANT']['class']} {rep['P-REDUNDANT']['lost_derivations']}")

    # --- no collateral damage ---------------------------------------------
    ok &= check("unrelated claim unaffected",
                rep["P-UNRELATED"]["class"] == "STILL_SUPPORTED", rep["P-UNRELATED"]["class"])
    ok &= check("untested conjecture unaffected",
                rep["P-UNTESTED"]["class"] == "UNAFFECTED", rep["P-UNTESTED"]["class"])

    # --- proof traces ------------------------------------------------------
    trace = g.proof_trace("P-LEAF")
    depth, node = 0, trace
    while node and node.get("via") == "derivation":
        depth += 1
        node = node["premises"][0]
    ok &= check("proof trace bottoms out at ground evidence",
                node and node.get("via") == "ground_evidence" and node["evidence"] == ["EV-ROOT"],
                json.dumps(trace))
    ok &= check("proof trace has the expected depth", depth == 2, f"depth={depth}")
    ok &= check("no proof trace once support is gone",
                g.proof_trace("P-LEAF", retracted={"EV-ROOT"}) is None)
    ok &= check("cyclic claim yields no proof trace",
                g.proof_trace("P-CYCLE-1") is None)

    # --- materialized view -------------------------------------------------
    view = {v["proposition_id"]: v for v in materialize(g)}
    ok &= check("view records the policy and graph version",
                view["P-LEAF"]["computed_from"] == {"policy": "least-fixpoint-v0.3",
                                                    "graph_version": "fixture-1"},
                json.dumps(view["P-LEAF"]["computed_from"]))
    ok &= check("view attributes derived support to a derivation, not fake evidence",
                view["P-LEAF"]["evidence_for"] == []
                and view["P-LEAF"]["derivations_supporting"] == ["D-LEAF"],
                json.dumps(view["P-LEAF"]))

    # --- INVALID derivations carry no warrant ------------------------------
    g2 = load()
    g2.derivations["D-MID"]["validity"] = "INVALID"
    after_invalid, _ = g2.status_map()
    ok &= check("an INVALID step blocks propagation even with supported premises",
                after_invalid["P-ROOT"] == "SUPPORTED"
                and after_invalid["P-MID"] == "UNRESOLVED"
                and after_invalid["P-LEAF"] == "UNRESOLVED",
                str({k: after_invalid[k] for k in ("P-ROOT", "P-MID", "P-LEAF")}))

    # --- unknown ids are an error, not a silent no-op -----------------------
    try:
        g.retract({"EV-DOES-NOT-EXIST"})
        ok &= check("unknown evidence id raises", False, "no exception")
    except KeyError:
        ok &= check("unknown evidence id raises", True)

    print()
    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
