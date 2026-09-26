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

## Lexicographic headline score

The headline key is deliberately category-separated so success in one category
cannot hide collapse in another:

1. `1 - decoy_false_merge_rate`
2. `1 - pair_false_merge_rate`
3. `1 - wrong_target_equal_rate`
4. `1 - manufactured_contradiction_rate`
5. `compatible_recall`
6. `correct_merge_rate`
7. `directional_entailment_accuracy`
8. `compression_fraction`

The pooled false-merge rate is still reported for continuity, but is **never**
the sole false-merge gate.

### Manufactured contradiction

A pair is counted as a manufactured contradiction when the system predicts
`CONTRADICTS` but the gold relation is anything other than `CONTRADICTS`.
This makes false conflict creation visible in the headline score rather than
burying it in pair-axis accuracy.


### COMPATIBLE recognition

`COMPATIBLE` is also a first-class headline gate. The scorer reports recall over
all gold-COMPATIBLE pairs and places that recall directly in the lexicographic
key. This prevents a conservative `UNRELATED`-by-default system from receiving
a perfect headline score while missing every context-preserving compatibility
case, including P01 and P05.

The report also splits COMPATIBLE misses into those predicted as `UNRELATED`
and those predicted as `CONTRADICTS`.

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
