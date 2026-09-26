# Causal-KG Benchmark v0

Seed dataset for the semantic-equality problem underneath the Universal K-IR /
causal knowledge graph design: **can heterogeneous expressions of the same
knowledge be compiled into the correct canonical equivalence classes, without
false-merging specializations, context changes, or merely-related propositions?**

This is deliberately scoped to one small domain (thermal / electrical / material
physics) instead of "all human knowledge" — see the project discussion for why
(Cyc's failure mode, canonicalization being the open research gap vs. mature
infrastructure like e-graphs and provenance semirings for everything downstream).

**v0.1 revision:** round-1 review caught a representation bug (K015 used the
wrong quantity) and an overloaded classification schema (see "Relation schema"
below). Both are fixed in this version — see CHANGELOG at the bottom.

## Files

```
concepts.json     34 concept nodes (Quantity/Type/Entity/Property/Constant)
propositions.json 22 gold canonical K-IR propositions (the target equivalence classes)
variants.json     ~55 paraphrases (nl / equation / code) of those propositions,
                   including a few "deliberate_error" decoys that drop a
                   load-bearing context clause
pairs.json        15 gold cross-proposition relation judgments, weighted toward
                   the failure modes that matter most (see below)
hyperedges.json    1 multi-premise (AND) entailment: {K001,K010} -> K011,
                   split out from pairs.json since neither premise alone entails
                   the conclusion
```

## Relation schema

v0 used a single flat six-way label (EQUAL/ENTAILS/ENTAILED_BY/CONTRADICTS/
OVERLAPS/UNRELATED). Round-1 review found this forces three independent
questions into one field and produces inconsistent calls (a metal/semiconductor
pair that clearly shares structure got mislabeled UNRELATED instead of
OVERLAPS). **v0.1 splits it into three orthogonal axes**, each pair in
`pairs.json` is scored on:

```
logical_relation    EQUAL | ENTAILS | ENTAILED_BY | CONTRADICTS | COMPATIBLE | UNRELATED
schema_relation      SAME | RELATED | DIFFERENT
context_relation     SAME | SUBSUMES | SUBSUMED_BY | OVERLAPS | DISJOINT
direction_relation   SAME | OPPOSITE | N/A   (only for MONOTONIC_* pairs)
```

Only `logical_relation = EQUAL` (with `context_relation = SAME`) may union two
propositions into one e-class (e-graph). `ENTAILS` / `ENTAILED_BY` populate a
separate entailment DAG (ordering/specialization). `COMPATIBLE` / `CONTRADICTS`
/ `UNRELATED` never merge and never order — they feed the causal-admission
layer, not the canonicalizer. `schema_relation` and `context_relation` are
diagnostic: they explain *why* a pair got its logical_relation, and catch a
canonicalizer that over-merges on shared surface structure (`schema_relation
SAME` alone must never imply `EQUAL`) or shared subject (`context_relation
SAME` alone must never imply `EQUAL`).

Example — the two hardest pairs, side by side:

```
K002 vs K003 (metal R rises with T / semiconductor R falls with T)
    logical_relation   = COMPATIBLE
    schema_relation    = SAME       (same MONOTONIC_?(T, R) shape)
    context_relation   = DISJOINT   (metallic_conduction vs semiconducting_NTC)
    direction_relation = OPPOSITE

K015 vs K016 (water volume rises above 4C / falls below 4C)
    logical_relation   = COMPATIBLE
    schema_relation    = SAME       (same MONOTONIC_?(T, V) shape)
    context_relation   = DISJOINT   (4C-boiling vs 0-4C)
    direction_relation = OPPOSITE
```

Structurally identical calls — which is the point: both are "apparent
contradiction, actually compatible once context is preserved," and the schema
now says so directly instead of overloading one label.

## Why these 22 propositions

Every proposition earns its place by stress-testing one specific failure mode:

| Case | Propositions | Tests |
|---|---|---|
| Specialization mistaken for identity | K004 / K004m / K004c | Metal-expands vs Copper-expands must chain as ENTAILS (context SUBSUMES), never EQUAL |
| Apparent contradiction from omitted context | K002 / K003 (+K019) | dR/dT sign flip is COMPATIBLE/DISJOINT-context, not CONTRADICTS |
| Real-looking contradiction that's actually context erasure | K015 / K016 | Water volume rises above 4C, falls below it — both true, disjoint temperature domains. **The single hardest case in v0.** Tests context *preservation*, not contradiction *resolution*. |
| Context silently dropped in paraphrase | K009/V009c, K012/V012c | An unqualified-sounding paraphrase is ENTAILED_BY the qualified original, not EQUAL to it |
| Hyperedge (multi-premise) entailment | K001 + K010 -> K011 | Neither single premise alone entails the conclusion; only the pair does (hyperedges.json) |
| Same predicate shape, different domain | K014 vs K004 | Both are `MONOTONIC_*` propositions — `schema_relation SAME` must not force a logical merge |
| Ontological fact vs causal law, same subject | K018 vs K002 | "Metal is-a Conductor" and "metal resistance rises with T" must not merge just because `context_relation SAME` |
| Topically adjacent, logically unrelated | K013 vs K009 | Negative control against embedding-similarity false positives |

## Evaluation priority (lexicographic, not averaged)

```
1. minimize false merges       (DIFFERENT ruled EQUAL — corrupts every downstream proof)
2. maximize correct merges     (SAME correctly ruled EQUAL)
3. preserve directional entailment (ENTAILS/ENTAILED_BY not flattened to EQUAL or UNRELATED)
4. maximize compression        (fewer surviving atoms for the same information)
```

A false merge is scored strictly worse than a false split: a false split just
costs storage (same knowledge kept twice); a false merge corrupts every proof
that later traverses through it.

## Status / next steps

Round-1 review (see CHANGELOG) fixed the representation bug and the schema
overload; the seed is now considered clean enough to build tooling against,
but **not yet clean enough to scale to 100-300 propositions** without another
pass. Still worth checking before scaling:

- The `material_regime`/`transport_regime` context fields on K002/K003 are a
  simplification (canonical examples: ordinary metal, intrinsic silicon) —
  fine for v0, but not a general electronic-structure theory.
- `K019`'s Metal/Semiconductor disjointness is flagged as a benchmark-level
  simplifying assumption (see `concepts.json` C14 `scope_note`), not physical
  truth — a full K-IR would model transport regime per-context instead of
  class-level disjointness.
- `K012` now models `InstantaneousSpeed` under `constant_speed` context,
  distinct from `Velocity` (a vector) — check this split reads correctly.

Not yet built (intentionally, pending further review): a scorer script that
takes a system's predicted axis values over all `propositions x variants x
pairs` combinations and computes the four metrics above; a paraphrase-
generation pipeline to scale past hand-authored examples; wiring this into
egglog / an entailment-graph learner.

## CHANGELOG

**v0.1** (round-1 review fixes):
- Fixed K015: was `LinearExtent`, should be `Volume` (liquid water has no
  stable intrinsic linear dimension) — now K015/K016 form a clean symmetric
  pair over `Volume`.
- Replaced the flat six-way `relation` label in `pairs.json` with three
  orthogonal axes (`logical_relation`, `schema_relation`, `context_relation`,
  `direction_relation`); re-classified all 15 pairs, most notably P01
  (was `UNRELATED`, now `COMPATIBLE`/`SAME`/`DISJOINT` — the old label
  contradicted the benchmark's own OVERLAPS definition).
- Restricted K002 (metal R rises with T), K003 (semiconductor R falls with T),
  and K004 (solid thermal expansion) from universal claims to named regimes
  (`positive_temperature_coefficient`, `semiconducting_NTC` w/ concrete example
  `intrinsic_silicon`, `ordinary_positive_expansion`) — the v0 draft
  overgeneralized past what the physics actually supports.
- Split out `hyperedges.json`: {K001,K010} -> K011 was mislabeled as a binary
  `ENTAILS` pair in v0; it's a 2-premise hyperedge. P08/P09 in `pairs.json`
  now correctly read `COMPATIBLE` for the individual premises.
- `K018`/concepts.json: `instance_of` -> `subtype_of` for all class-to-class
  links (Metal/Material, Copper/Metal, Silicon/Semiconductor, Water/Material,
  Metal/Conductor) — `instance_of` is reserved for individual-to-class links,
  which don't appear in `concepts.json` itself.
- Split K012 into `InstantaneousSpeed` (scalar, `constant_speed` context) vs.
  the existing `Velocity` concept (vector) — v0 conflated average speed,
  instantaneous speed, and velocity into one proposition.
- Fixed P06: label (`ENTAILED_BY`) was correct in v0 but the rationale
  described the opposite direction; rationale rewritten to match the label.
- Added missing concepts referenced by existing propositions but absent from
  `concepts.json`: `Distance`, `Speed`, `AmountOfSubstance`, `GasConstant`,
  `Acceleration`, `Silicon`.
