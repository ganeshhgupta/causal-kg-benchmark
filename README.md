# Causal-KG Benchmark v0

Seed dataset for the semantic-equality problem underneath the Universal K-IR /
causal knowledge graph design: **can heterogeneous expressions of the same
knowledge be compiled into the correct canonical equivalence classes, without
false-merging specializations, context changes, or merely-related propositions?**

This is deliberately scoped to one small domain (thermal / electrical / material
physics) instead of "all human knowledge" — see the project discussion for why
(Cyc's failure mode, canonicalization being the open research gap vs. mature
infrastructure like e-graphs and provenance semirings for everything downstream).

## Files

```
concepts.json     28 concept nodes (Quantity/Type/Entity/Property/Constant)
propositions.json 22 gold canonical K-IR propositions (the target equivalence classes)
variants.json     ~55 paraphrases (nl / equation / code) of those propositions,
                   including a few "deliberate_error" decoys that drop a
                   load-bearing context clause
pairs.json        15 gold cross-proposition relation judgments, weighted toward
                   the failure modes that matter most (see below)
```

## The six-relation calculus

```
EQUAL          A => B  AND  B => A   (same context/assumptions)
ENTAILS        A => B  but not B => A
ENTAILED_BY    B => A  but not A => B
CONTRADICTS    A ^ B is unsatisfiable, under the same context
OVERLAPS       A ^ B satisfiable, neither entails the other, shared structure
UNRELATED      otherwise
```

Only `EQUAL` may union two propositions into one e-class (e-graph). `ENTAILS` /
`ENTAILED_BY` populate a separate entailment DAG (ordering/specialization).
`CONTRADICTS` / `OVERLAPS` / `UNRELATED` never merge and never order — they are
signals for the causal-admission layer, not the canonicalizer.

## Why these 22 propositions

Every proposition earns its place by stress-testing one specific failure mode
from the design discussion:

| Case | Propositions | Tests |
|---|---|---|
| Specialization mistaken for identity | K004 / K004m / K004c | Metal-expands vs Copper-expands must chain as ENTAILS, never EQUAL |
| Apparent contradiction from omitted context | K002 / K003 (+K019) | dR/dT sign flip is UNRELATED (disjoint material types), not CONTRADICTS |
| Real contradiction resolved by context split | K015 / K016 | Water "expands" vs "contracts" when heated — both true, disjoint temperature domains. **The single hardest case in v0.** |
| Context silently dropped in paraphrase | K009/V009c, K012/V012c | A "simpler-sounding" paraphrase that quietly loses a load-bearing condition must not be marked EQUAL |
| Hyperedge (multi-premise) entailment | K001 + K010 -> K011 | Neither single premise alone entails the conclusion; only the pair does |
| Same predicate shape, different domain | K014 vs K004 | Both are `MONOTONIC_*` propositions — must not merge on syntactic shape alone |
| Ontological fact vs causal law, same subject | K018 vs K002 | "Metal is-a Conductor" and "metal resistance rises with T" must not merge just because they share a subject type |
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

This is hand-authored gold data for ~20-30 propositions, per the "I draft, you
review" plan — **please spot-check before we scale to 100-300 propositions**.
Things worth checking in particular:

- Do the `context` fields on K002/K003/K015/K016/K004m/K004c actually capture
  the right conditions, or did I oversimplify the physics?
- Are the `pairs.json` rationales convincing, especially P01 and P05 (the two
  designed to be the hardest)?
- Is the six-relation calculus missing a case you'd expect real scientific
  paraphrase data to hit?

Not yet built (intentionally, pending your review of the data first):
a scorer script that takes a system's predicted relations over all
`propositions x variants x pairs` combinations and computes the four metrics
above; a paraphrase-generation pipeline to scale past hand-authored examples;
wiring this into egglog / an entailment-graph learner.
