# ML/AI Canonicalization Benchmark Layer

The canonicalization-benchmark layer for `../dataset.json` (500 ML/AI paper
claims), built the same way as the physics benchmark at the repo root:
`propositions.json` + `variants.json` (with decoys) + `pairs.json` (4-axis
gold relations) + `hyperedges.json`, scored with `../../scorer/scorer.py`.

## What this is (and isn't)

Not exhaustive coverage of all 500 claims — that's not how the physics
benchmark worked either (15 curated pairs across 22 propositions, not
22-choose-2). This is 18 curated propositions, 23 variants (4 decoys), 11
pairs, and 1 hyperedge, chosen specifically because they exhibit the same
failure patterns the physics benchmark was built to catch, using **real**
ML technique relationships rather than invented ones:

| Physics pattern | ML/AI analog used here |
|---|---|
| Metal/semiconductor resistance (P01): apparent contradiction from missing regime context | BERT (bidirectional MLM) vs GPT (causal LM) — both valid, mutually exclusive pretraining paradigms |
| Metal→Copper specialization trap (P02-P04) | DropConnect (general) → Dropout (special case: zeroing all weights out of one unit = zeroing that unit's activation) |
| **Water 0-4C anomaly (P05): the flagship "context erasure manufactures a fake contradiction" case** | **Dropout training phase (zeroes activations) vs inference phase (disabled) — same mechanism, opposite-looking behavior, reconciled by phase, not a real conflict** |
| (no physics analog — same pattern, 2nd instance) | Full self-attention O(n^2) vs sparse/windowed attention (sub-quadratic) — reconciled by attention_type, not a real conflict |
| K001+K010→K011 hyperedge | Momentum + RMSProp → Adam (neither alone entails Adam) |
| (v0.2 had **zero** real contradiction examples — flagged as an open gap) | **BN_ORIG (Ioffe & Szegedy 2015: batch norm works via reducing internal covariate shift) vs BN_REVISED (Santurkar et al. 2018: it's actually landscape smoothing) — a genuine, unreconciled CONTRADICTS, not an apparent one. First real gold CONTRADICTS pair in this project.** |

## Fact-check pass

Before building this layer, ran an adversarial spot-check of the 15
highest-risk claims in `../dataset.json` (contested findings stated as flat
fact, attribution years, "who did X first" claims) via web search. Result:
13/15 correct, 2 real issues found and fixed directly in `../dataset.json`:

- **M116**: overstated RoBERTa's actual finding ("NSP is unnecessary or
  harmful" → corrected to "removing NSP, combined with full-sentence input
  packing, matched or improved performance" — the original wording implied
  a cleaner causal claim than RoBERTa's paper actually supports).
- **M493**: speculative decoding was credited only to Leviathan et al.
  (Google) — corrected to co-credit Chen et al. (DeepMind), who
  independently discovered the same technique around the same time.

This is a spot-check of the highest-risk subset, not exhaustive
verification of all 500 entries — see `../README.md`'s limitations section.

## Scored against the real v4 scorer (not simulated)

Ran `../../scorer/scorer.py` (the same verified scorer from the physics
benchmark work) against this layer with `make_predictions.py`-generated
fixtures:

```
Perfect (gold-matching) predictions:
    [1, 1, 1, 1, 1, 1, 1, 0.4634]   <- clean, all 8 headline gates pass
    41 source nodes -> 22 surviving e-classes (matches hand-computed expectation)

Adversarial probe: miss the one real CONTRADICTS (predict COMPATIBLE for P05)
    [1, 1, 1, 1, 1, 1, 1, 0.4634]   <- headline UNCHANGED. CONTRADICTS recall
                                         buried at 0% in pair_axes, invisible
                                         at the headline level.

Adversarial probe: manufacture a false contradiction (P03, dropout phases)
    [1, 1, 1, 0.9, 0.857, 1, 1, 0.4634]  <- correctly caught on BOTH the
                                              manufactured_contradiction gate
                                              AND compatible_recall (P03 is
                                              gold-COMPATIBLE)

Adversarial probe: decoy V-M041b ("dropout at both train and test")
wrongly marked EQUAL
    [0.75, 1, 1, 1, 1, 1, 1, 0.488]  <- correctly caught as a decoy false
                                          merge (1 of 4 decoys wrongly merged)
```

## New finding: the "missed CONTRADICTS" gap

The scorer's existing gates (`manufactured_contradiction_rate`,
`compatible_recall`) correctly catch a system that invents a false conflict
or misses a real compatibility. But a system that has the **opposite**
failure — missing a real contradiction by calling it `COMPATIBLE` or
`UNRELATED` — passes with a perfect headline score, because there is no
dedicated `contradicts_recall` gate. This exact gap was found and fixed for
`COMPATIBLE` earlier in this project; it was never visible for `CONTRADICTS`
before because v0.2 had zero real gold contradiction examples to test with.
This is now a concrete, reproducible finding (not hypothetical) for whoever
picks up the "class-balanced macro-recall" scorer generalization already
proposed as v0.3 follow-up work.

## Files

```
propositions.json   18 propositions (reusing ../dataset.json claim text
                     via source_id, plus 2 new BN_ORIG/BN_REVISED entries)
variants.json        23 variants, 4 deliberate_error decoys
pairs.json           11 gold pairs across the 4-axis schema
hyperedges.json       1 hyperedge (Momentum + RMSProp -> Adam)
make_predictions.py  generates the perfect + 3 adversarial prediction fixtures
```
