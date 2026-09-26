#!/usr/bin/env python3
"""Validate examples-v0.2.json against kir-schema-v0.2.json.

Unlike v0.1's validator (which only did structural JSON Schema checks -- see
kir-v0.1/STRESS_TEST.md Finding 0 on why that was nearly toothless), this also
runs three semantic checks the schema itself cannot express:

  1. referential integrity   -- every id reference resolves
  2. predicate typing        -- Proposition.predicate points at a kind=RELATION symbol
  3. epistemic recomputation -- independently recompute status from ACTIVE evidence
                                and diff against what the file claims

Check 3 is the important one: it is what makes the non-monotonic retraction case
actually testable instead of merely asserted. Two divergences are EXPECTED and
documented in CHANGELOG.md; any other divergence is a real failure.
"""
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).parent

# Divergences deliberately left in the data to demonstrate unfixed limitations.
EXPECTED_DIVERGENCES = {
    "P-PROTOCOL-Z": "stored status left stale on purpose; nothing recomputes it automatically "
                    "even though the derivation-aware rule can now see the collapse",
    "P-BN-ICS": "INCONSISTENT marker from a derived functional-relation contradiction, "
                "which an evidence-count rule cannot see at all",
}


def load(name):
    with open(ROOT / name, encoding="utf-8") as fh:
        return json.load(fh)


def recompute_status(prop_id, evidence, derivations, derivation_aware):
    """Recompute epistemic status from evidence.

    derivation_aware=False is the naive rule (status=active only). True also
    requires that derivation_result evidence came from a still-valid Derivation,
    which is what the schema now specifies. Running both and diffing them is how
    the one-hop invalidation case is demonstrated rather than asserted.
    """
    admissible = []
    for e in evidence:
        if e["proposition_id"] != prop_id or e["status"] != "active":
            continue
        if derivation_aware and e["kind"] == "derivation_result":
            ref = e.get("derivation_ref")
            if ref and derivations.get(ref, {}).get("status") != "valid":
                continue
        admissible.append(e)
    has_for = any(e["stance"] == "supports" for e in admissible)
    has_against = any(e["stance"] == "refutes" for e in admissible)
    if has_for and has_against:
        return "INCONSISTENT"
    if has_for:
        return "SUPPORTED"
    if has_against:
        return "REFUTED"
    return "UNRESOLVED"


def main():
    schema = load("kir-schema-v0.2.json")
    data = load("examples-v0.2.json")

    errors = []

    # --- 1. structural validation -------------------------------------------
    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    for err in schema_errors:
        path = "/".join(str(p) for p in err.path)
        errors.append(f"[schema] at '{path}': {err.message}")
    print(f"structural validation: {len(schema_errors)} error(s)")

    symbols = {s["id"]: s for s in data["symbols"]}
    contexts = {c["id"] for c in data["contexts"]}
    props = {p["id"]: p for p in data["propositions"]}
    evidence = data["evidence"]
    ev_ids = {e["id"] for e in evidence}
    derivations = {d["id"]: d for d in data.get("derivations", [])}

    # --- 2. referential integrity + predicate typing -------------------------
    def walk_term(term, where):
        if term["kind"] == "symbol_ref":
            if term["symbol_ref"] not in symbols:
                errors.append(f"[ref] {where}: unknown symbol '{term['symbol_ref']}'")
        elif term["kind"] == "function":
            for arg in term["args"]:
                walk_term(arg, where)

    for pid, p in props.items():
        pred = p["predicate"]
        if pred not in symbols:
            errors.append(f"[ref] {pid}: predicate '{pred}' is not a registered symbol")
        elif symbols[pred]["kind"] != "RELATION":
            errors.append(f"[type] {pid}: predicate '{pred}' is kind={symbols[pred]['kind']}, expected RELATION")
        for arg in p["arguments"]:
            walk_term(arg["term"], pid)
        for q in p.get("quantification", []):
            if q["type"] not in symbols:
                errors.append(f"[ref] {pid}: quantifier type '{q['type']}' is not a registered symbol")
        if p.get("context") and p["context"] not in contexts:
            errors.append(f"[ref] {pid}: unknown context '{p['context']}'")

    for a in data["assertions"]:
        if a["proposition_id"] not in props:
            errors.append(f"[ref] assertion {a['id']}: unknown proposition '{a['proposition_id']}'")
    for e in evidence:
        if e["proposition_id"] not in props:
            errors.append(f"[ref] evidence {e['id']}: unknown proposition '{e['proposition_id']}'")
        if e.get("derivation_ref") and e["derivation_ref"] not in derivations:
            errors.append(f"[ref] evidence {e['id']}: unknown derivation '{e['derivation_ref']}'")
    for d in derivations.values():
        for prem in d["premises"]:
            if prem not in props:
                errors.append(f"[ref] derivation {d['id']}: unknown premise '{prem}'")
        if d["conclusion"] not in props:
            errors.append(f"[ref] derivation {d['id']}: unknown conclusion '{d['conclusion']}'")
        if d.get("context") and d["context"] not in contexts:
            errors.append(f"[ref] derivation {d['id']}: unknown context '{d['context']}'")
    for r in data.get("revisions", []):
        known = set(symbols) | set(props) | {a["id"] for a in data["assertions"]} | ev_ids | set(derivations)
        for rid in r["old_ids"] + r["new_ids"]:
            if rid not in known:
                errors.append(f"[ref] revision {r['id']}: unknown id '{rid}'")

    print(f"referential integrity + predicate typing: checked "
          f"{len(props)} propositions, {len(data['assertions'])} assertions, "
          f"{len(evidence)} evidence, {len(derivations)} derivations, "
          f"{len(data.get('revisions', []))} revisions")

    # --- 3. epistemic status recomputation ----------------------------------
    divergences = []
    stale = []
    for entry in data.get("epistemic_status", []):
        pid = entry["proposition_id"]
        if pid not in props:
            errors.append(f"[ref] epistemic_status: unknown proposition '{pid}'")
            continue
        naive = recompute_status(pid, evidence, derivations, derivation_aware=False)
        strict = recompute_status(pid, evidence, derivations, derivation_aware=True)
        if entry["status"] != strict:
            divergences.append((pid, entry["status"], strict))
        if naive != strict:
            stale.append((pid, naive, strict))
        for ref in entry["evidence_for"] + entry["evidence_against"]:
            if ref not in ev_ids:
                errors.append(f"[ref] epistemic_status {pid}: unknown evidence '{ref}'")
        if entry.get("proof_for") and entry["proof_for"] not in derivations:
            errors.append(f"[ref] epistemic_status {pid}: unknown proof '{entry['proof_for']}'")

    print(f"one-hop invalidation detected on {len(stale)} proposition(s) "
          f"(naive active-evidence rule vs derivation-aware rule):")
    for pid, naive, strict in stale:
        print(f"   {pid}: naive rule says {naive}, derivation-aware rule says {strict}")

    print(f"epistemic recomputation: {len(divergences)} divergence(s) from the "
          f"derivation-aware rule")
    for pid, claimed, expected in divergences:
        if pid in EXPECTED_DIVERGENCES:
            print(f"   EXPECTED  {pid}: file says {claimed}, rule says {expected} "
                  f"-- {EXPECTED_DIVERGENCES[pid]}")
        else:
            errors.append(f"[epistemic] {pid}: file says {claimed}, active-evidence rule says {expected}")

    missing = set(EXPECTED_DIVERGENCES) - {d[0] for d in divergences}
    for pid in sorted(missing):
        errors.append(f"[epistemic] {pid} was expected to diverge but does not -- "
                      f"the documented limitation is no longer demonstrated by the data")

    # --- report -------------------------------------------------------------
    print()
    if errors:
        print(f"FAIL: {len(errors)} problem(s)")
        for e in errors:
            print(f"  {e}")
        return 1
    print("PASS: structure, references, predicate typing and epistemic recomputation all clean "
          "(the 2 divergences above are deliberate, documented limitations, not bugs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
