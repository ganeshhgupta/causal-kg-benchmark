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

## Scored against the real scorer (not simulated)

Ran `../../scorer/scorer.py` against this layer with
`make_predictions.py`-generated fixtures. Numbers below are post-fix,
against the v5 scorer (9-component headline: see
`../../scorer/README-scorer.md`):

```
Perfect (gold-matching) predictions:
    [1, 1, 1, 1, 1, 1, 1, 1, 0.4634]   <- clean, all 9 headline gates pass
    41 source nodes -> 22 surviving e-classes (matches hand-computed expectation)

Adversarial probe: miss the one real CONTRADICTS (predict COMPATIBLE for P05)
    [1, 1, 1, 1, 0, 0.75, 1, 1, 0.4634]  <- NOW CAUGHT (v5): min_supported_
                                              class_recall drops to exactly 0,
                                              macro to 0.75. Was invisible
                                              under v4's 8-component headline
                                              (see "round 2 review" below).

Adversarial probe: manufacture a false contradiction (P03, dropout phases)
    [1, 1, 1, 0.9, 0.857, ..., 1, 1, 0.4634]  <- correctly caught on BOTH the
                                                   manufactured_contradiction
                                                   gate AND min class recall
                                                   (P03 is gold-COMPATIBLE)

Adversarial probe: decoy V-M041b ("dropout at both train and test")
wrongly marked EQUAL
    [0.75, 1, 1, 1, 1, 1, 1, 1, 0.488]  <- correctly caught as a decoy false
                                            merge (1 of 4 decoys wrongly merged)
```

## Round 2 review: 3 real fixes applied, 1 scorer generalization shipped

A follow-up review (verified via web search before applying) found and fixed:

1. **M042 was factually muddled.** Confirmed via search: the original 2014
   Dropout paper scales *outgoing weights* at *test time*; "inverted dropout"
   (the modern standard in PyTorch/TF/JAX) instead scales *surviving
   activations* during *training*, making test time the identity operation.
   The v0 wording conflated the two. Fixed in both `../dataset.json` and
   here, since this is the flagship context-preservation pair (P03).
2. **M116 still overstated BERT's claim after the first fix.** Confirmed via
   search: BERT's ablation shows NSP removal hurts QNLI/MNLI/SQuAD, framed
   as NSP being *beneficial* -- BERT never claims NSP is "necessary." Fixed
   the residual overclaim in `../dataset.json`.
3. **P02 (DropConnect ENTAILS Dropout) and H01 (Momentum+RMSProp ENTAILS
   Adam) both overclaimed logical entailment for what are really
   method-lineage/composition relations.** M041 is a conjunction (masking +
   co-adaptation prevention + implicit ensemble) that M053's mechanism-level
   claim doesn't strictly, formally entail on its own; Adam's bias
   correction is a third design element neither Momentum nor RMSProp
   provides or implies. Both are now annotated with explicit caveats
   documenting this as a known simplification (P02 stays ENTAILS, the
   nearest available axis value, with a note that a future schema needs a
   dedicated `GENERALIZES_METHOD` relation; H01's `relation` field is
   relabeled `COMPOSES_TO` with `entailed: true` preserved so the scorer
   still treats it as a positive hyperedge -- `relation` is descriptive
   only, `entailed` is what the scorer actually reads).
4. Added a `scope_note` to M009/M010 (BERT/GPT) clarifying that treating
   `pretraining_paradigm` as mutually exclusive is a benchmark-scoped
   simplification, not a universal claim -- same pattern as the physics
   benchmark's Metal/Semiconductor `scope_note`.
5. Added a **provenance caveat** to BN_REVISED: the CONTRADICTS relation
   (P05) holds between the *embedded scientific hypotheses*
   (`mechanism(BN)=ICS` vs `mechanism(BN)!=ICS`), not between the historical
   facts that each paper made its claim -- those provenance facts don't
   conflict at all. A future K-IR needs to keep "paper X claims Y" separate
   from "Y."

**Bigger finding: the relation vocabulary itself has a gap.** Points 3-4
above surfaced that `ENTAILS`/`COMPATIBLE`/etc. can't cleanly represent
method-lineage relations (`GENERALIZES`, `COMPOSES_TO`) without overclaiming
formal logical entailment for what's really a taxonomy/engineering-design
relationship. The physics benchmark's mostly-equality/entailment/context
claims didn't expose this; ML claims about method lineage did. Documented as
known simplifications rather than implemented as a new schema value, since
that's a real vocabulary-design question for a future round, not a quick fix.

**Scorer generalization shipped (not just documented):** the scorer itself
was upgraded (`../../scorer/scorer.py`, v5) to compute per-class recall for
every gold-supported `logical_relation` class, headlined as
`min_supported_class_recall` + `macro_supported_class_recall`. This
generalizes v4's one-off `compatible_recall` gate and directly closes the
"missed CONTRADICTS" finding below. `regression_tests.py` was also fixed to
be genuinely generic (it previously hardcoded physics-specific IDs despite
taking `--gold-dir`) and now passes against both this benchmark and the
physics one, including a new test 6 for this exact case.

## RESOLVED: the "missed CONTRADICTS" gap

Originally found here as an open gap, now closed in `../../scorer/scorer.py`
v5 (see "round 2 review" above) rather than left as a proposed follow-up.

The v4 scorer's gates (`manufactured_contradiction_rate`, `compatible_recall`)
correctly caught a system that invents a false conflict or misses a real
compatibility. But a system with the **opposite** failure — missing a real
contradiction by calling it `COMPATIBLE` or `UNRELATED` — passed with a
perfect headline score, because there was no dedicated `contradicts_recall`
gate. The same gap was found and fixed for `COMPATIBLE` earlier in this
project; it was never visible for `CONTRADICTS` before because v0.2 had zero
real gold contradiction examples to test with. `min_supported_class_recall`
+ `macro_supported_class_recall` now generalize this to every class with
gold support, so the same category of gap can't silently reopen for
`EQUAL`/`ENTAILS`/`UNRELATED` either, once real gold examples for those
exist. Verified via `regression_tests.py` test 6.

## Files

```
propositions.json   18 propositions (reusing ../dataset.json claim text
                     via source_id, plus 2 new BN_ORIG/BN_REVISED entries)
variants.json        23 variants, 4 deliberate_error decoys
pairs.json           11 gold pairs across the 4-axis schema
hyperedges.json       1 hyperedge (Momentum + RMSProp -> Adam)
make_predictions.py  generates the perfect + 3 adversarial prediction fixtures
```
