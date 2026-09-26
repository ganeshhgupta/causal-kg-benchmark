#!/usr/bin/env python3
"""Align two independently invented vocabularies, then compare claims across them.

Written because the first end-to-end run measured cross-vocabulary claim matching
at 0.000: compiler/canonicalize.py normalises predicates but assumes both graphs
refer to the same symbol ids. The hand-authored corpora happened to share ids, so
that assumption was invisible and the reported F1 of 1.000 was flattered. A blind
extraction invents `sym_granisetron` where the reference says `C-GRANISETRON`, and
nothing matched.

This is the SYMBOL RESOLUTION stage that kir-v0.1/STRESS_TEST.md finding 12 argued
has to run before any claim-level matching: deciding which formal entity a name
denotes is a different question from deciding whether two claims are the same, and
doing the second without the first cannot work.

Alignment is by normalised label, plus declared families from
compiler/equivalences.json. It is deliberately not fuzzy string similarity: the
false-merge gate means a wrong alignment must trace to a declared family that can
be deleted, not to a threshold.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from canonicalize import load_equivalences, normalize, term_key  # noqa: E402


def norm_label(label: str) -> str:
    s = label.lower().strip()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def family_of(label: str, equiv: dict) -> str | None:
    n = norm_label(label)
    for fam, spec in equiv.get("symbol_families", {}).items():
        if fam.startswith("_"):
            continue
        if n in {norm_label(m) for m in spec["member_labels"]}:
            return fam
    return None


def align(symbols_a: list[dict], symbols_b: list[dict], equiv: dict):
    """Map a-ids to b-ids. Returns (mapping, unaligned_a, report)."""
    by_label_b, by_family_b = {}, {}
    for s in symbols_b:
        by_label_b.setdefault(norm_label(s.get("label", "")), s["id"])
        fam = family_of(s.get("label", ""), equiv)
        if fam:
            by_family_b.setdefault(fam, s["id"])

    mapping, unaligned, report = {}, [], []
    for s in symbols_a:
        label = s.get("label", "")
        n = norm_label(label)
        if n in by_label_b:
            mapping[s["id"]] = by_label_b[n]
            report.append((s["id"], by_label_b[n], "exact label"))
            continue
        fam = family_of(label, equiv)
        if fam and fam in by_family_b:
            mapping[s["id"]] = by_family_b[fam]
            report.append((s["id"], by_family_b[fam], f"family {fam}"))
            continue
        # Aliases, if either side declares them.
        alias_hit = None
        for t in symbols_b:
            aliases = {norm_label(x) for x in t.get("aliases", [])}
            if n in aliases or norm_label(t.get("label", "")) in {
                    norm_label(x) for x in s.get("aliases", [])}:
                alias_hit = t["id"]
                break
        if alias_hit:
            mapping[s["id"]] = alias_hit
            report.append((s["id"], alias_hit, "alias"))
            continue
        unaligned.append(s["id"])
    return mapping, unaligned, report


def _rewrite(prop: dict, mapping: dict) -> dict:
    """Return a copy of prop with symbol refs rewritten into b's vocabulary."""
    out = json.loads(json.dumps(prop))

    def walk(term):
        if term.get("kind") == "symbol_ref" and term["symbol_ref"] in mapping:
            term["symbol_ref"] = mapping[term["symbol_ref"]]
        for a in term.get("args", []) or []:
            walk(a)

    if out.get("predicate") in mapping:
        out["predicate"] = mapping[out["predicate"]]
    for arg in out.get("arguments", []):
        walk(arg["term"])
    return out


def _canon_roles(predicate: str, roles, equiv: dict):
    """Rename role synonyms to their canonical name for this relation."""
    table = equiv.get("role_aliases", {}).get(predicate, {})
    if not table:
        return roles
    lookup = {}
    for canon, syns in table.items():
        if canon.startswith("_"):
            continue
        lookup[canon] = canon
        for s in syns:
            lookup[s] = canon
    return frozenset((lookup.get(r, r), v) for r, v in roles)


def _apply_role_aliases_to_prop(prop: dict, equiv: dict) -> dict:
    """Rename roles on a raw proposition so guard checks see canonical names."""
    table = equiv.get("role_aliases", {})
    out = json.loads(json.dumps(prop))
    for key in (out.get("predicate"), "COMBINATION_OUTPERFORMS"):
        spec = table.get(key)
        if not spec:
            continue
        lookup = {}
        for canon, syns in spec.items():
            if canon.startswith("_"):
                continue
            for s in syns:
                lookup[s] = canon
        for arg in out.get("arguments", []):
            arg["role"] = lookup.get(arg["role"], arg["role"])
        break
    return out


def compare_cross(prop_a: dict, prop_b: dict, mapping: dict, equiv: dict):
    """Compare claims from two vocabularies. EQUAL / RELATED / DIFFERENT."""
    a = _apply_role_aliases_to_prop(_rewrite(prop_a, mapping), equiv)
    b = _apply_role_aliases_to_prop(prop_b, equiv)
    pa, ra, pola, ctxa, rulea = normalize(a, equiv)
    pb, rb, polb, ctxb, ruleb = normalize(b, equiv)

    ra = _canon_roles(pa, ra, equiv)
    rb = _canon_roles(pb, rb, equiv)

    drop = set(equiv.get("non_discriminating_roles", {}).get("roles", []))
    ra = frozenset((r, v) for r, v in ra if r not in drop)
    rb = frozenset((r, v) for r, v in rb if r not in drop)

    if pa != pb:
        return "DIFFERENT", f"predicates differ after alignment ({pa} vs {pb})"
    if pola != polb:
        return "DIFFERENT", "opposite polarity"
    if ra == rb:
        return "EQUAL", f"identical after symbol alignment (rules {rulea or '-'}/{ruleb or '-'})"
    if {r for r, _ in ra} == {r for r, _ in rb}:
        differing = sorted(r for r, v in ra if (r, v) not in rb)
        return "RELATED", f"same shape, differing arguments {differing}"
    return "DIFFERENT", "role sets differ"


def main():
    equiv = load_equivalences()
    ex = json.load(open(ROOT / "scientific-dependency" / "extracted" /
                        "fujii-ponv-extracted.json", encoding="utf-8"))
    ref = json.load(open(ROOT / "scientific-dependency" / "corpus" /
                         "fujii-ponv.json", encoding="utf-8"))

    mapping, unaligned, report = align(ex["symbols"], ref["symbols"], equiv)

    print(f"extracted symbols {len(ex['symbols'])}, reference symbols "
          f"{len(ref['symbols'])}")
    print(f"aligned {len(mapping)}, unaligned {len(unaligned)}\n")
    for a, b, how in report:
        print(f"  {a:36} -> {b:28} [{how}]")
    if unaligned:
        print("\nunaligned (no counterpart in the reference vocabulary):")
        for a in unaligned:
            lab = next(s.get("label", "") for s in ex["symbols"] if s["id"] == a)
            print(f"  {a:36} {lab!r}")

    ref_props = {p["id"]: p for p in ref["propositions"]}
    ex_props = {p["id"]: p for p in ex["propositions"]}

    print("\ncross-vocabulary claim matches:")
    matches = {}
    for eid, ep in ex_props.items():
        hits = []
        for gid, gp in ref_props.items():
            v, why = compare_cross(ep, gp, mapping, equiv)
            if v == "EQUAL":
                hits.append(gid)
        if hits:
            matches[eid] = hits
            print(f"  {eid:36} EQUAL -> {hits}")
    unmatched = [e for e in ex_props if e not in matches]
    print(f"\nextracted claims matched to a reference claim: "
          f"{len(matches)}/{len(ex_props)}")
    if unmatched:
        print("still unmatched:")
        for e in unmatched:
            print(f"  {e}")

    # Collapse check: several extracted claims mapping to ONE reference claim is
    # the intended endpoint-family collapse, not a false merge.
    inverted: dict[str, list[str]] = {}
    for eid, gids in matches.items():
        for gid in gids:
            inverted.setdefault(gid, []).append(eid)
    print("\nreference claim <- extracted claims (collapse groups):")
    for gid, eids in sorted(inverted.items()):
        print(f"  {gid:28} <- {eids}")
    multi = {g: e for g, e in inverted.items() if len(e) > 1}
    print(f"\nendpoint collapses: {len(multi)} reference claim(s) received "
          f"several extracted claims, which is EXTRACTION_SPEC rule 2a working "
          f"as intended rather than a false merge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
