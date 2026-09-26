# Causal-KG Benchmark v0

Seed dataset for the semantic-equality problem underneath the Universal K-IR /
causal knowledge graph design: **can heterogeneous expressions of the same
knowledge be compiled into the correct canonical equivalence classes, without
false-merging specializations, context changes, or merely-related propositions?**

This is deliberately scoped to one small domain (thermal / electrical / material
physics) instead of "all human knowledge" — see the project discussion for why
(Cyc's failure mode, canonicalization being the open research gap vs. mature
infrastructure like e-graphs and provenance semirings for everything downstream).

**v0.2 revision:** round-1 fixed a representation bug and an overloaded
classification schema. Round-2 found the fix didn't propagate to the paraphrase
data (several "equal" variants silently dropped the newly-added restrictions),
plus 5 mislabeled `context_relation` values and two remaining representation
issues (unclear quantification, a wrong replacement proposition). All fixed
here — see CHANGELOG at the bottom.

## Files

```
concepts.json     34 concept nodes (Quantity/Type/Entity/Property/Constant)
propositions.json 22 gold canonical K-IR propositions (the target equivalence classes)
variants.json     57 paraphrases (nl / equation / code) of those propositions,
                   including 8 "deliberate_error" decoys that drop a
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

`context_relation` is computed purely from **context-predicate satisfiability**,
never from topic/subject similarity (fixed in v0.2 — round-2 review caught 5
pairs where "different topic" had been conflated with "incompatible context"):

```
SAME          predicate sets are equivalent
SUBSUMES /    one side's predicates are a strict subset of the other's.
SUBSUMED_BY   An unrestricted context {} always SUBSUMES any non-empty
              context — it trivially holds wherever the specific one does.
OVERLAPS      both sides have non-empty, independent predicates that are
              jointly satisfiable, and neither is a subset of the other
DISJOINT      the two predicate sets are jointly UNsatisfiable — reserved
              for genuine mutual exclusion (disjoint temperature ranges,
              disjoint transport regimes backed by an explicit disjointness
              fact), never merely "these are about different things"
```

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

## Variant equality policy

A prose variant is EQUAL to its `proposition_id` only if it doesn't silently
drop a restriction for which a **real, named counterexample** exists in the
domain (Invar-type low-expansion alloys for K004m, water's 0-4C density
anomaly for K015, altitude for boiling point, non-uniform motion for
instantaneous speed). Where such a counterexample exists, the
generic-sounding phrasing is marked `"deliberate_error": "context_dropped"`
instead of being silently left as a false EQUAL — round-2 review caught
exactly this bug: propositions had been tightened to named regimes, but the
paraphrase variants underneath them hadn't been re-audited, so several
"equal" variants were quietly no longer true. Bare equation-form variants
(no natural-language totalizing claim) are treated as carrying the same
implicit textbook-standard assumptions as their canonical statement.

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

Two review rounds (see CHANGELOG) fixed the representation bugs, the schema
overload, and the variant/context-relation drift that round 1's fixes left
behind. The reviewer's own assessment after round 2: "the benchmark
architecture itself is now sound enough; the remaining problems are
gold-label hygiene rather than another redesign" — so **the scorer is next**,
not another architecture pass. Still worth a light check before scaling past
this seed:

- The `material_regime`/`transport_regime` context fields on K002/K003 are a
  simplification (canonical examples: ordinary metal, intrinsic silicon) —
  fine for v0, but not a general electronic-structure theory.
- `K019`'s Metal/Semiconductor disjointness is flagged as a benchmark-level
  simplifying assumption (see `concepts.json` C14 `scope_note`), not physical
  truth — a full K-IR would model transport regime per-context instead of
  class-level disjointness.
- `K015`/`K016`'s `Water_sample` has the same "individual vs. universally
  quantified schema variable" ambiguity that `K004c` had (fixed in v0.2) —
  left as-is since a fixed liquid sample is a more natural unit there, but
  worth revisiting for full consistency.
- **Not yet a proposition, but should be one in v0.3:** `AverageSpeed(x,
  interval) = DistanceTraveled(x, interval) / Duration(interval)`, always
  true (no `constant_speed` context needed) — this was `K012`'s v0.1
  definition before it was corrected to `InstantaneousSpeed`. Its old variant
  (`"Average speed is distance traveled divided by time taken"`) was removed
  from `variants.json` in v0.2 rather than kept as either an EQUAL or a decoy,
  because it's neither — it's a true, different proposition. Pre-documented
  relation for whoever adds it: `AverageSpeed ENTAILS K012` (under the added
  premise that speed is constant over the interval, average speed and
  instantaneous speed coincide).
- Newton's second law (K007) and the heat-capacity relation (K013) have the
  same "named-regime vs. generic-sounding variant" tension as K002-K004 (e.g.
  relativistic speeds / variable mass for K007; phase transitions for K013).
  Given light-touch qualifiers in v0.2 rather than the full
  variant/decoy treatment K002-K004 got, since they weren't flagged in review
  — worth a closer pass if this domain gets scaled up.

Not yet built (intentionally, pending the scorer being the actual next step):
a paraphrase-generation pipeline to scale past hand-authored examples; wiring
this into egglog / an entailment-graph learner.

## CHANGELOG

**v0.2** (round-2 review fixes):
- Re-audited every variant of K002, K003, K004, K004m, K004c, K015 against
  their (now-tightened) proposition contexts. Found and fixed several
  "equal" variants that silently dropped a load-bearing restriction and were
  therefore no longer true paraphrases — most importantly `V015a` ("Water
  expands when heated"), which the v0.1 draft even annotated as "only true
  above 4C" but left un-flagged. Added 5 new `deliberate_error` decoys
  (V002b, V002d, V003a, V004b, V004ma) and rewrote the corresponding
  positive variants to state their regime explicitly. Net: 8 decoys total
  (was 2).
- Fixed 5 mislabeled `context_relation` values (P09, P10, P12, P13, P14) that
  had conflated "different topic" with "incompatible context" — e.g. K006
  (ideal gas) vs K007 (Newtonian mechanics) is `OVERLAPS`, not `DISJOINT`,
  since a fixed-mass ideal-gas parcel satisfies both. Added an explicit
  satisfiability-based determination rule for the axis (see "Relation
  schema") so this doesn't drift again.
- Fixed K004c's quantification: was written over an undeclared individual
  `Copper_instance`; now `forall x:Copper, ...`, matching the free-variable
  convention every other proposition uses.
- Replaced K020 again: v0.1's replacement ("uniform scaling conserves volume
  iff shape unchanged") was itself wrong — uniform scaling preserves shape
  while volume scales as k^3, so those can never coincide except at k=1. Now
  `Volume(UniformScale(x,k)) = k^3 * Volume(x)`, a clean scaling law with
  matching equation/NL/code variants (V020a-c).
- Removed `V012a` ("Average speed is distance traveled divided by time
  taken") from `variants.json` — it isn't a paraphrase of K012 at all (K012
  is now `InstantaneousSpeed` under `constant_speed`; V012a describes the
  always-true, unconditional `AverageSpeed`). Documented as a future v0.3
  proposition in "Status / next steps" rather than forced into either an
  EQUAL or a decoy slot it doesn't belong in.

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
