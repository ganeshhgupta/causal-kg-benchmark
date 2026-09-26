# Causal-KG benchmark scorer

Run:

```bash
python scorer.py --gold-dir . --predictions predictions.json
```

Optional JSON report:

```bash
python scorer.py --gold-dir . --predictions predictions.json --json-out score-report.json
```

The scorer is strict by default: every variant, pair, and hyperedge needs a
prediction. `--allow-missing` is for development only.

## Important prediction semantics

For every variant prediction, both fields matter:

```json
{
  "variant_id": "V004ca",
  "proposition_id": "K004c",
  "logical_relation": "EQUAL"
}
```

`proposition_id` is the system's **predicted canonical target**. An ordinary
variant is a correct merge only when:

1. `logical_relation == "EQUAL"`, and
2. `predicted proposition_id == gold proposition_id`.

`EQUAL` to the wrong proposition is a **false merge**, not a correct answer.
The compression calculation also unions against the predicted target, never
the gold target.

For a `deliberate_error` decoy, `EQUAL` to *any* canonical proposition is
unsafe and counts as a decoy false merge.

For non-monotonic pair predictions, `direction_relation` may be omitted when
the gold value is `N/A`; the scorer normalizes that omission to `N/A`.

## Lexicographic headline score (v5)

The headline key is deliberately category-separated so success in one category
cannot hide collapse in another:

1. `1 - decoy_false_merge_rate`
2. `1 - pair_false_merge_rate`
3. `1 - wrong_target_equal_rate`
4. `1 - manufactured_contradiction_rate`
5. `min_supported_class_recall`
6. `macro_supported_class_recall`
7. `correct_merge_rate`
8. `directional_entailment_accuracy`
9. `compression_fraction`

The pooled false-merge rate is still reported for continuity, but is **never**
the sole false-merge gate.

### Manufactured contradiction

A pair is counted as a manufactured contradiction when the system predicts
`CONTRADICTS` but the gold relation is anything other than `CONTRADICTS`.
This makes false conflict creation (precision failure for the CONTRADICTS
class) visible in the headline score rather than burying it in pair-axis
accuracy.

### Per-class recall (v5, generalizes v4's COMPATIBLE-only gate)

v4 added a standalone `compatible_recall` headline gate because a
conservative system could default every uncertain `COMPATIBLE` pair to
`UNRELATED` and still score perfectly on every other metric. v5 generalizes
this: recall is computed for **every** `logical_relation` class that has at
least one gold example (`EQUAL`, `ENTAILS`, `ENTAILED_BY`, `CONTRADICTS`,
`COMPATIBLE`, `UNRELATED` -- whichever actually appear in `pairs.json`), and
the headline carries both:

- **`min_supported_class_recall`** -- the recall of the worst-performing
  class. Catches total collapse in any single class outright, e.g. a system
  that never once predicts `CONTRADICTS` correctly.
- **`macro_supported_class_recall`** -- the average recall across classes.
  Needed alongside min because min alone can't distinguish "everything is
  fine except one class is at 0%" from "everything is uniformly mediocre" --
  min catches the former, macro reflects the latter.

This closes a hole found empirically, not hypothetically: v4's headline had
no gate for a gold `CONTRADICTS` pair being predicted as `COMPATIBLE` (or
anything else), because that failure trips none of the other gates
(`EQUAL`→not a merge, `CONTRADICTS`-predicted→not a manufactured
contradiction). It went unnoticed through v4 only because the physics gold
set had zero real `CONTRADICTS` examples to test with; the first real one
(`ml-ai-dataset/benchmark`'s BatchNorm pair) surfaced it immediately. See
`regression_tests.py` test 6.

`compatible_recall` and the `compatible_recognition` report block are
retained for continuity (now just one entry inside `class_recalls.per_class`)
but are no longer a separate headline slot.

## Hyperedges

The scorer supports both positive and future negative hyperedges.

Current positive-compatible form:

```json
{
  "id": "H01",
  "premises": ["K001", "K010"],
  "conclusion": "K011",
  "relation": "ENTAILS"
}
```

Future negative form:

```json
{
  "id": "H02",
  "premises": ["K001", "K005"],
  "conclusion": "K011",
  "entailed": false
}
```

If `entailed` is present it is authoritative; otherwise
`relation == "ENTAILS"` is treated as positive for v0.2 compatibility.
The scorer reports hyperedge accuracy, precision, recall, and F1.

It also warns when the gold set has no `CONTRADICTS`, no cross-proposition
`EQUAL`, or no negative hyperedge, so unsupported relation classes cannot look
silently "tested".

## Regression suite (v5: made genuinely generic)

`regression_tests.py` takes `--gold-dir` and is meant to run against any
gold set, but tests 2 and 3 previously hardcoded physics-specific IDs
(`V004ca`, `K004m`, `P01`, `P05`) -- they only ever validated correctly
against the physics benchmark despite the `--gold-dir` parameter implying
otherwise. v5 picks targets dynamically from whatever gold set is passed,
and both are now verified to pass against the physics benchmark (repo root)
and `ml-ai-dataset/benchmark`. Test 6 (missing a real `CONTRADICTS` pair)
skips gracefully with a printed note on gold sets that don't have one yet,
rather than failing or silently not testing anything.
