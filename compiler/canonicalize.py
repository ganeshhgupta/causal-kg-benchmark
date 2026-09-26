#!/usr/bin/env python3
"""Canonicalize claims to a normal form, then compare normal forms.

Built because eval/canonicalization_eval.py measured F1 0.000: no structural or
lexical matcher could see a real cross-document duplicate, while the lexical ones
committed false merges on near-miss decoys.

Approach: declared equivalences, not similarity. Two claims are EQUAL only if
they reduce to an identical normal form under rules in compiler/equivalences.json,
each of which carries a justification and may carry a guard. The reason to pay
this cost rather than tune a threshold is the false-merge gate: a wrong merge
here traces to one named rule that can be removed, instead of to a number that
has to be retuned and hoped about.

Three verdicts, and the distinction between the last two is the whole point:

  EQUAL      identical normal form, including context and polarity
  RELATED    same canonical predicate and role set, at least one argument
             differs. NOT a merge. This is where near-miss decoys land: one drug
             swapped, or a specific instance against the general principle it
             instantiates
  DIFFERENT  different canonical predicate or role set

Normalisation maps relations onto a shared canonical predicate and renames roles.
It never weakens an argument, so a specific claim cannot normalise onto the
general one it instantiates. Reporting that as EQUAL would be the Copper-into-
Metal false merge this project has treated as the worst available error.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EQUIV = Path(__file__).parent / "equivalences.json"


def load_equivalences(path=EQUIV):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def term_key(term: dict) -> str:
    if term.get("kind") == "symbol_ref":
        return f"sym:{term['symbol_ref']}"
    if term.get("kind") == "literal":
        return f"lit:{json.dumps(term.get('value'), sort_keys=True)}"
    if term.get("kind") == "variable":
        return f"var:{term['name']}"
    if term.get("kind") == "function":
        inner = ",".join(term_key(a) for a in term.get("args", []))
        return f"fn:{term['name']}({inner})"
    return f"raw:{json.dumps(term, sort_keys=True)}"


def _guard_ok(guard, prop, equiv) -> bool:
    if not guard:
        return True
    role = guard.get("role")
    needed = guard.get("symbol_must_denote")
    allowed = set(equiv.get("symbol_denotations", {}).get(needed, []))
    for arg in prop["arguments"]:
        if arg["role"] != role:
            continue
        ref = arg["term"].get("symbol_ref")
        return ref in allowed
    return False


def normalize(prop: dict, equiv: dict):
    """Return (canonical_predicate, frozenset of (role, term_key), polarity,
    context, rule_applied)."""
    predicate = prop["predicate"]
    roles = {a["role"]: term_key(a["term"]) for a in prop["arguments"]}
    applied = None

    for rule in equiv.get("relation_equivalences", []):
        left, right = rule["left"], rule["right"]
        role_map = rule["role_map"]

        if predicate == left["predicate"]:
            # The guard names RIGHT-side roles, so roles must be renamed BEFORE
            # it is tested. Checking it against the left side's own role names
            # made the guard never match and silently disabled the rule for
            # every left-side claim.
            mapped = {role_map.get(r, r): v for r, v in roles.items()}
            probe = {"arguments": [{"role": r, "term": {"symbol_ref": v[4:]}}
                                   for r, v in mapped.items()
                                   if v.startswith("sym:")]}
            if not _guard_ok(rule.get("guard"), probe, equiv):
                continue
            predicate = rule["canonical_predicate"]
            roles = mapped
            applied = rule["id"]
            break

        if predicate == right["predicate"]:
            if not _guard_ok(rule.get("guard"), prop, equiv):
                continue
            predicate = rule["canonical_predicate"]
            applied = rule["id"]
            break

    return (predicate, frozenset(roles.items()), prop.get("polarity", "assert"),
            prop.get("context"), applied)


def compare(a: dict, b: dict, equiv: dict) -> tuple[str, str]:
    na, nb = normalize(a, equiv), normalize(b, equiv)
    pa, ra, pola, ctxa, rulea = na
    pb, rb, polb, ctxb, ruleb = nb

    if pa == pb and ra == rb and pola == polb and ctxa == ctxb:
        via = f"normal forms identical (rules: {rulea or '-'}, {ruleb or '-'})"
        return "EQUAL", via

    if pa == pb and {r for r, _ in ra} == {r for r, _ in rb}:
        if pola != polb:
            return "DIFFERENT", "same shape but opposite polarity"
        if ctxa != ctxb:
            return "RELATED", f"same shape, different context ({ctxa} vs {ctxb})"
        diff = sorted({r for r, v in ra} &
                      {r for r, v in rb} -
                      {r for r, v in (ra & rb)})
        return "RELATED", f"same canonical predicate {pa}, differing arguments {diff}"

    return "DIFFERENT", f"canonical predicates or roles differ ({pa} vs {pb})"


def load_corpora(paths):
    props, symbols = {}, {}
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        for s in data.get("symbols", []):
            symbols.setdefault(s["id"], s)
        for prop in data["propositions"]:
            props[prop["id"]] = prop
    return props, symbols


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        argv = ["scientific-dependency/corpus/fujii-ponv.json",
                "scientific-dependency/corpus/fujii-combination-review.json"]
    equiv = load_equivalences()
    props, _ = load_corpora([ROOT / a for a in argv])

    print(f"{len(props)} claims, "
          f"{len(equiv.get('relation_equivalences', []))} declared equivalence rule(s)\n")
    print("normal forms:")
    for pid, p in props.items():
        pred, roles, pol, ctx, rule = normalize(p, equiv)
        tag = f"  [via {rule}]" if rule else ""
        args = ", ".join(f"{r}={v}" for r, v in sorted(roles))
        print(f"  {pid:28} {pred}({args}) pol={pol} ctx={ctx}{tag}")

    print("\nEQUAL pairs found:")
    ids = sorted(props)
    found = False
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            verdict, why = compare(props[a], props[b], equiv)
            if verdict == "EQUAL":
                found = True
                print(f"  {a} == {b}   ({why})")
    if not found:
        print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
